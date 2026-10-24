#!/usr/bin/env python3
# HOW DO THE MINUTE-HOLD WINNERS TRADE? (read-only, R3 tapes). Per wallet, per position (first buy -> last sell on the curve):
# entry: token age, curve SOL (market-cap proxy), price change in the 10 s / 60 s before the entry, a >= 1 SOL dump right before?,
#        is the wallet the dev / in the create slot?, buyers in the 10 s before entry
# scale-in: buys, time from first to last buy, avg price vs first buy
# exit: sells, exit return (SOL out / SOL in), best price seen while holding (MFE) and worst (MAE), exit price vs that peak,
#       dev sold before the exit?, flow in the 10 s before the exit (net SOL, sells count)
import os, sys, json, gzip, glob, collections, statistics
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
SL = 0.212
WL = [l.strip() for l in open("short22.txt") if l.strip()] + ["3hXxYe8XrxSn38RRE3u8xhB3d1rEhjYUTFRTx1Qr9r9A"]
WS = set(WL)
L = rp.load_launches()
mints = collections.defaultdict(set)
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/R3_*.jsonl.gz"):
    for line in gzip.open(f, "rt"):
        if line[2:46].rstrip('"') in WS or any(w in line[:60] for w in WS):
            r = json.loads(line)
            if r[0] in WS: mints[r[1]].add(r[0])
byb = collections.defaultdict(set)
for m in mints: byb[("R3", rp.bucket(m))].add(m)
def px(t): return t["vsol"] / t["vtok"] if t["vtok"] else 0
def work(key):
    out = []
    for m, tr in rp.read_bucket(key[0], key[1], byb[key]).items():
        c = L[m]; S0 = c["slot"]; dev = c.get("creator")
        for w in mints[m]:
            ks = [k for k, t in enumerate(tr) if t["user"] == w]
            bk = [k for k in ks if tr[k]["buy"]]; sk = [k for k in ks if not tr[k]["buy"]]
            if not bk: continue
            sk = [k for k in sk if k > bk[0]]
            if not sk: continue
            b0 = tr[bk[0]]; e_end = tr[sk[-1]]
            sin = sum(tr[k]["sol"] for k in bk); sout = sum(tr[k]["sol"] for k in sk); tin = sum(tr[k]["tok"] for k in bk); tout = sum(tr[k]["tok"] for k in sk)
            if tout < 0.95 * tin: continue
            p0 = px(tr[bk[0] - 1]) if bk[0] > 0 else px(b0)
            def back(sec):
                j = bk[0]
                while j > 0 and (b0["s"] - tr[j - 1]["s"]) * SL <= sec: j -= 1
                return tr[j - 1] if j > 0 else tr[0]
            pre10 = back(10); pre60 = back(60)
            win10 = [t for t in tr[:bk[0]] if (b0["s"] - t["s"]) * SL <= 10]
            dump = any((not t["buy"]) and t["sol"] >= 1e9 for t in tr[max(0, bk[0] - 3):bk[0]])
            hold = tr[bk[0]:sk[-1] + 1]
            avgp = sin / tin if tin else 0
            prices = [px(t) for t in hold]
            mfe = max(prices) / avgp if avgp else 0; mae = min(prices) / avgp if avgp else 0
            ex_px = px(tr[sk[0] - 1]) if sk[0] > 0 else px(tr[sk[0]])
            peak_before_exit = max(px(t) for t in tr[bk[0]:sk[0]]) if sk[0] > bk[0] else ex_px
            devsold = any(t["user"] == dev and not t["buy"] for t in tr[bk[0]:sk[0]])
            exw = [t for t in tr[:sk[0]] if (tr[sk[0]]["s"] - t["s"]) * SL <= 10 and t["user"] != w]
            out.append(dict(w=w, m=m, age=(b0["s"] - S0) * SL, vsol=b0["vsol"] / 1e9, ch10=px(b0) / px(pre10) - 1 if px(pre10) else 0, ch60=px(b0) / px(pre60) - 1 if px(pre60) else 0,
                            dump=dump, isdev=w == dev, create_slot=b0["s"] == S0, buyers10=len({t["user"] for t in win10 if t["buy"]}), nb=len(bk), ns=len(sk),
                            spread=(tr[bk[-1]]["s"] - b0["s"]) * SL, avg_vs_first=avgp / (b0["sol"] / b0["tok"]) if b0["tok"] else 1, ret=sout / sin if sin else 0,
                            mfe=mfe, mae=mae, exit_vs_peak=ex_px / peak_before_exit if peak_before_exit else 1, hold=(e_end["s"] - b0["s"]) * SL,
                            devsold=devsold, ex_net10=sum((t["sol"] if t["buy"] else -t["sol"]) for t in exw) / 1e9, ex_sells10=sum(1 for t in exw if not t["buy"]),
                            exit_ret_at_first_sell=ex_px / avgp if avgp else 0, sin=sin / 1e9, pnl=(sout - sin) / 1e9))
    return out
if __name__ == "__main__":
    P = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=2): P += o
    json.dump(P, open("style.json", "w"))
    med = lambda v: statistics.median(v) if v else float("nan")
    print("wallet    pos  age-at-entry  curveSOL  chg10s chg60s dump-before  buyers10s | buys spread avg/first | hold  ret   MFE   MAE  exit/peak  devsold  first-sell@ | 10s-before-exit net/sells")
    for w in WL:
        v = [x for x in P if x["w"] == w]
        if not v: print(w[:8], "no closed positions in tapes"); continue
        print(f"{w[:8]} {len(v):4d}  {med([x['age'] for x in v]):7.0f}s  {med([x['vsol'] for x in v]):6.1f}  {med([x['ch10'] for x in v]):+6.0%} {med([x['ch60'] for x in v]):+6.0%}   {sum(x['dump'] for x in v)/len(v):4.0%}  "
              f"{med([x['buyers10'] for x in v]):5.0f}     | {med([x['nb'] for x in v]):3.0f} {med([x['spread'] for x in v]):5.0f}s {med([x['avg_vs_first'] for x in v]):5.2f}   | {med([x['hold'] for x in v])/60:4.1f}m {med([x['ret'] for x in v]):5.2f} "
              f"{med([x['mfe'] for x in v]):5.2f} {med([x['mae'] for x in v]):5.2f}  {med([x['exit_vs_peak'] for x in v]):5.2f}    {sum(x['devsold'] for x in v)/len(v):4.0%}   {med([x['exit_ret_at_first_sell'] for x in v]):5.2f}x  | "
              f"{med([x['ex_net10'] for x in v]):+6.2f} {med([x['ex_sells10'] for x in v]):3.0f}   dev? {sum(x['isdev'] for x in v)} create-slot {sum(x['create_slot'] for x in v)}")

#!/usr/bin/env python3
# S4 evidence rows for the report: every S3 launch in the forward window with, per landing time, our modeled place
# (the tx we land right after), the guard check, our fill and sell prices, the tx our sell lands before, and the PnL.
import sys, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
exec(open("/home/moiz/sniper/ops/overnight/core/ana_rate_wf.py").read().split("for name, f in")[0])
S3 = {r["mint"]: state[r["mint"]] for r in rows if (lambda a, n: a >= 2 and (n == 0 or a / n >= 0.10))(*state[r["mint"]])}
O = rp.load_obs()
byb = collections.defaultdict(set)
for m in S3: byb[rp.bucket(m)].add(m)
EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5), rp.R("hold1s", [(1.0, ("t", 1))], 2)]
def work(b):
    tra = rp.read_bucket("R2", b, byb[b]); fa = rp.read_failed("R2", b, byb[b]); out = []
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; mc = lambda p: p * 1e9 * 1e6 / 1e9   # SOL market cap (1B supply, 6 decimals)
        row = dict(mint=m, name=c.get("name"), symbol=c.get("symbol"), deployer=c["user"], creator_field=c.get("creator"), bt=c["bt"], create_sig=c.get("sig"),
                   dev_buy=round(sum(t["sol"] for t in tr if t["sig"] == c.get("sig") and t["buy"]) / 1e9, 3), bundle=[t["sig"] for t in st["glued"]],
                   bundle_sol=round(sum(t["sol"] for t in st["glued"]) / 1e9, 3), mc_bundle_sol=round(mc(p_b), 2), att_before=S3[m][0], launches_before=S3[m][1], land={})
        for Lm in (45, 60, 75):
            ib, na = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib < 1: continue
            pf = tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]; ratio = pf / p_b
            d = dict(after_sig=tr[ib - 1]["sig"], after_user=tr[ib - 1]["user"], ahead=na, ratio=round(ratio, 4), filled=ratio <= 1.01, mc_fill_sol=round(mc(pf), 2))
            if d["filled"]:
                o = rp.sim(tr, c, st, ib, 0.5, EX, fill_pen=0.015)
                # where the 1 s sell lands: first trade at/after buy slot + ceil(1 s / slot)
                bs = max(c["slot"], tr[ib - 1]["s"]); due = bs + 2          # eos1: our sell lands right after the end of slot (buy slot + 1)
                ks = next((k for k in range(ib, len(tr)) if tr[k]["s"] >= due), len(tr))
                d.update(pnl=o["eos1"]["pnl"] if o else None, pnl_hold1s=o["hold1s"]["pnl"] if o else None, sell_before_sig=tr[ks]["sig"] if ks < len(tr) else None,
                         sell_after_sig=tr[ks - 1]["sig"], mc_sell_sol=round(mc(tr[ks - 1]["vsol"] / tr[ks - 1]["vtok"]), 2),
                         buys_after=sum(1 for t in tr[ib:ks] if t["buy"]), sells_after=sum(1 for t in tr[ib:ks] if not t["buy"]))
            else: d.update(pnl=-0.005)
            row["land"][str(Lm)] = d
        out.append(row)
    return out
if __name__ == "__main__":
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    res.sort(key=lambda r: r["bt"])
    json.dump(res, open("/home/moiz/sniper/ops/overnight/report/s4_forward.json", "w"))
    for Lm in ("45", "60", "75"):
        v = [r["land"][Lm]["pnl"] for r in res if Lm in r["land"] and r["land"][Lm]["pnl"] is not None]
        print(f"L{Lm}: attempts {len(v)}, fills {sum(1 for r in res if Lm in r['land'] and r['land'][Lm]['filled'])}, total {sum(v):+.3f} SOL")

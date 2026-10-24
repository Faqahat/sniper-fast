#!/usr/bin/env python3
# HOW DOES A WALLET WIN WHILE LANDING LATE? (local collector data, run R3 = 10-23 19:26 PKT -> now, read-only)
# Positions per token (all its buys and sells on the curve, FIFO by token): entry trigger (what came right before its first buy),
# delay after that trigger (block-position ms), token age, size, adds, hold, P&L (pump fees ~1.25% each way counted via SOL legs),
# profit concentration, P&L by entry delay / token age / size, and flow after its buy (who buys after it, how much).
import os, sys, json, collections, statistics
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
W = sys.argv[1]
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def arr(t): return t["s"] * 212.0 + t["i"] / max(SS.get(t["s"], 400), t["i"] + 1) * 212.0
COH = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))
L = rp.load_launches(); byb = collections.defaultdict(set)
for m, c in L.items():
    if c["run"] == "R3": byb[("R3", rp.bucket(m))].add(m)
def work(key):
    out = []
    for m, tr in rp.read_bucket(key[0], key[1], byb[key]).items():
        mine = [k for k, t in enumerate(tr) if t["user"] == W]
        if not mine: continue
        S0 = L[m]["slot"]; k0 = mine[0]; t0 = tr[k0]
        if not t0["buy"]: continue
        pv = tr[k0 - 1] if k0 else None
        trig = "launch/bundle" if k0 < 3 else ("dump>=1" if (pv and not pv["buy"] and pv["sol"] >= 1e9) else ("small sell" if pv and not pv["buy"] else "after buys"))
        fr = lambda t: ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
        sin = sum(tr[k]["sol"] * (1 + fr(tr[k])) for k in mine if tr[k]["buy"]) / 1e9
        sout = sum(tr[k]["sol"] * (1 - fr(tr[k])) for k in mine if not tr[k]["buy"]) / 1e9
        tok = sum(tr[k]["tok"] * (1 if tr[k]["buy"] else -1) for k in mine)
        last = tr[-1]; mark = max(tok, 0) * (last["vsol"] / last["vtok"]) * 0.9875 / 1e9 if last["vsol"] < 110e9 else 0
        ls = max((k for k in mine if not tr[k]["buy"]), default=None)
        after = [t for t in tr[k0 + 1:] if arr(t) - arr(t0) <= 3000 and t["user"] != W]
        out.append(dict(m=m, trig=trig, delay=round(arr(t0) - arr(pv), 1) if pv else None, age=round((t0["s"] - S0) * 0.212, 1), size=t0["sol"] / 1e9,
                        nbuys=sum(1 for k in mine if tr[k]["buy"]), nsells=sum(1 for k in mine if not tr[k]["buy"]), cost=sin, back=sout + mark, pnl=sout + mark - sin,
                        hold=round((tr[ls]["s"] - t0["s"]) * 0.212, 1) if ls is not None else None, open=tok > 0,
                        after_buy_sol=sum(t["sol"] for t in after if t["buy"]) / 1e9, after_sell_sol=sum(t["sol"] for t in after if not t["buy"]) / 1e9,
                        after_coh=len({t["user"] for t in after if t["buy"] and t["user"] in COH}), vsol=t0["vsol"] / 1e9, prev_sell=(pv["sol"] / 1e9 if pv and not pv["buy"] else 0)))
    return out
if __name__ == "__main__":
    P = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=4): P += o
    json.dump(P, open(f"/home/moiz/sniper/ops/overnight/wallets/howwins_{W[:8]}.json", "w"))
    med = lambda v: statistics.median(v) if v else float("nan")
    n = len(P); tot = sum(p["pnl"] for p in P)
    print(f"{W[:8]}: {n} token positions in R3, total P&L {tot:+.2f} SOL (curve legs incl. pump fees, open ones marked), {sum(1 for p in P if p['pnl'] > 0) / n:.0%} positive")
    print(f"  size first buy median {med([p['size'] for p in P]):.3f} SOL | buys per token median {med([p['nbuys'] for p in P])} (max {max(p['nbuys'] for p in P)}) | hold median {med([p['hold'] for p in P if p['hold'] is not None]):.1f} s")
    s = sorted((p["pnl"] for p in P), reverse=True); k = max(1, n // 20)
    print(f"  profit concentration: top 5% positions {sum(s[:k]):+.2f} SOL, the other 95% {sum(s[k:]):+.2f} | median position {med(s):+.4f} | avg win {med([x for x in s if x > 0]):+.4f} vs avg loss {med([x for x in s if x <= 0]):+.4f}")
    print("  by what came right before its first buy:")
    for t, c in collections.Counter(p["trig"] for p in P).most_common():
        v = [p for p in P if p["trig"] == t]
        print(f"     {t:14s} n {len(v):5d} P&L {sum(p['pnl'] for p in v):+8.2f} | win {sum(1 for p in v if p['pnl'] > 0) / len(v):.0%} | delay med {med([p['delay'] for p in v if p['delay'] is not None]):.0f} ms | age med {med([p['age'] for p in v]):.1f} s")
    print("  by delay after the trigger (block-position ms):")
    for lo, hi in ((0, 35), (35, 75), (75, 150), (150, 300), (300, 1000), (1000, 1e9)):
        v = [p for p in P if p["delay"] is not None and lo <= p["delay"] < hi]
        if v: print(f"     {lo:5.0f}-{hi if hi < 1e9 else 'inf':>5} ms n {len(v):5d} P&L {sum(p['pnl'] for p in v):+8.2f} | win {sum(1 for p in v if p['pnl'] > 0) / len(v):.0%} | per position {sum(p['pnl'] for p in v) / len(v):+.4f}")
    print("  by token age at its first buy:")
    for lo, hi in ((0, 2), (2, 5), (5, 15), (15, 60), (60, 300), (300, 1e9)):
        v = [p for p in P if lo <= p["age"] < hi]
        if v: print(f"     {lo:4.0f}-{hi if hi < 1e9 else 'inf':>4} s n {len(v):5d} P&L {sum(p['pnl'] for p in v):+8.2f} | win {sum(1 for p in v if p['pnl'] > 0) / len(v):.0%}")
    print("  by number of buys on the token (adding / averaging):")
    for lo, hi in ((1, 2), (2, 3), (3, 6), (6, 1e9)):
        v = [p for p in P if lo <= p["nbuys"] < hi]
        if v: print(f"     {lo}-{hi if hi < 1e9 else 'inf'} buys n {len(v):5d} P&L {sum(p['pnl'] for p in v):+8.2f} | win {sum(1 for p in v if p['pnl'] > 0) / len(v):.0%} | SOL in med {med([p['cost'] for p in v]):.2f}")
    print("  flow in the 3 s after its first buy, winners vs losers:")
    for lab, v in (("winners", [p for p in P if p["pnl"] > 0]), ("losers", [p for p in P if p["pnl"] <= 0])):
        print(f"     {lab}: buys after {med([p['after_buy_sol'] for p in v]):.2f} SOL, sells after {med([p['after_sell_sol'] for p in v]):.2f} SOL, profitable bots buying after {med([p['after_coh'] for p in v])}")

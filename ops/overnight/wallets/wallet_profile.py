#!/usr/bin/env python3
# What does a wallet do on pump.fun curves? (local collector data, R2 + R3, read-only). For each of its buys: token age, size,
# what happened just before (big sell = dip buy? buys = momentum?), delay after that trade (block-position ms), its position
# in the slot vs the create, and its round trips (FIFO per token): hold, return, P&L.
# usage: python3 -I wallet_profile.py WALLET
import os, sys, json, collections, statistics, time
os.environ.setdefault("RP_PHASEA_R2", "phaseA_sel"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
W = sys.argv[1]
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def arr(t): return t["s"] * rp.SLOT_MS + t["i"] / max(SS.get(t["s"], 400), t["i"] + 1) * rp.SLOT_MS
L = rp.load_launches()
byb = collections.defaultdict(set)
for m, c in L.items():
    if c["run"] in ("R2", "R3"): byb[(c["run"], rp.bucket(m))].add(m)
def work(key):
    out = []
    for m, tr in rp.read_bucket(key[0], key[1], byb[key]).items():
        if not any(t["user"] == W for t in tr): continue
        S0 = L[m]["slot"]; pos = []
        for k, t in enumerate(tr):
            if t["user"] != W: continue
            pv = tr[k - 1] if k else None
            out.append(dict(m=m, bt=L[m]["bt"], k=k, buy=t["buy"], sol=t["sol"] / 1e9, age=(t["s"] - S0) * 0.212, s=t["s"],
                            prev=(("B" if pv["buy"] else "S"), round(pv["sol"] / 1e9, 3), pv["user"][:8]) if pv else None,
                            dt=round(arr(t) - arr(pv), 1) if pv else None, vsol=t["vsol"] / 1e9, n_before=k))
    return out
if __name__ == "__main__":
    R = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=4): R += o
    R.sort(key=lambda r: (r["m"], r["k"]))
    buys = [r for r in R if r["buy"]]; sells = [r for r in R if not r["buy"]]
    print(f"{W[:8]}: {len(buys)} buys, {len(sells)} sells on {len(set(r['m'] for r in R))} tokens in our data (R2 10-22 20:43 -> 10-23 18:31, R3 19:26 -> now)")
    if not buys: sys.exit()
    q = lambda v, p: sorted(v)[int(p * (len(v) - 1))]
    ag = [r["age"] for r in buys]; sz = [r["sol"] for r in buys]
    print(f"  buy size SOL: median {statistics.median(sz):.3f} p10 {q(sz,.1):.3f} p90 {q(sz,.9):.3f} | token age at buy s: p10 {q(ag,.1):.1f} median {statistics.median(ag):.1f} p90 {q(ag,.9):.1f}")
    print(f"  buys in the create slot: {sum(1 for r in buys if r['age'] == 0) / len(buys):.0%}; within 1 s: {sum(1 for r in buys if r['age'] <= 1) / len(buys):.0%} | trades before its buy: median {statistics.median(r['n_before'] for r in buys)}")
    pv = collections.Counter(r["prev"][0] for r in buys if r["prev"]); big = [r for r in buys if r["prev"] and r["prev"][0] == "S" and r["prev"][1] >= 1]
    print(f"  trade right before its buy: sells {pv['S'] / len(buys):.0%} (>=1 SOL sells {len(big) / len(buys):.0%}), buys {pv['B'] / len(buys):.0%}")
    if big: print(f"  after >=1 SOL sells: delay ms median {statistics.median(r['dt'] for r in big):.0f}")
    vs = [r["vsol"] for r in buys]; print(f"  curve SOL at buy: p10 {q(vs,.1):.1f} median {statistics.median(vs):.1f} p90 {q(vs,.9):.1f}")
    # round trips FIFO by token
    trips = []; op = collections.defaultdict(list)
    for r in R:
        if r["buy"]: op[r["m"]].append(r)
        elif op[r["m"]]:
            b = op[r["m"]].pop(0); trips.append(dict(hold=(r["s"] - b["s"]) * 0.212, ret=r["sol"] / b["sol"] if b["sol"] else 0, pnl=r["sol"] - b["sol"]))
    if trips:
        h = [t["hold"] for t in trips]
        print(f"  round trips {len(trips)}: hold s p25 {q(h,.25):.1f} median {statistics.median(h):.1f} p75 {q(h,.75):.1f} | win {sum(1 for t in trips if t['pnl'] > 0) / len(trips):.0%} | "
              f"gross SOL (before fees) {sum(t['pnl'] for t in trips):+.2f}, median return {statistics.median(t['ret'] for t in trips):.3f}")
    hrs = collections.Counter(time.gmtime(r["bt"] + r["age"] + 18000).tm_hour for r in buys); print("  buys by PKT hour:", dict(sorted(hrs.items())))
    ex = sorted(buys, key=lambda r: -r["bt"])[:3]
    for r in ex: print(f"  e.g. https://gmgn.ai/sol/token/{r['m']} buy {r['sol']:.2f} SOL at age {r['age']:.1f} s, prev {r['prev']}")

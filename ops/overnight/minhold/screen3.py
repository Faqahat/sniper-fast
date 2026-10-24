#!/usr/bin/env python3
# MORE "GROUP 1" WALLETS (read-only, census R1/R2/R3): picky minute-holders like 3hXxYe8X / Fsb6Ns75 / pXGQ6J2z / 4vw54BmA.
# Style filter (on R2+R3 combined, closed positions only): 8-200 positions/day, median hold 1-10 min, win >= 55%,
# median first buy >= 10 s after the create, < 20% of first buys in the create slot, never/rarely the token's creator.
# Profit: realized SOL/day over R2+R3 (~46 h) >= 3, both days > 0, still > 0 without its best 5 tokens. R1 shown as an extra check.
import os, sys, gzip, glob, json, collections, statistics
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
HRS = {"R1": 14.88, "R2": 21.79, "R3": 24.0}; SL = 0.212; AG = {"BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"}
CRE = {m: c.get("creator") for m, c in rp.load_launches().items()}
W = collections.defaultdict(lambda: collections.defaultdict(list))
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"):
    for line in gzip.open(f, "rt"):
        r = json.loads(line)
        if r[0] not in AG: W[r[0]][r[2]].append(r)
med = lambda v: statistics.median(v) if v else float("nan")
out = []
for u, runs in W.items():
    both = runs.get("R2", []) + runs.get("R3", [])
    if len(both) < 15: continue
    cl = [r for r in both if not r[16] and r[13]]
    if len(cl) < 12: continue
    hrs = sum(HRS[k] for k in ("R2", "R3") if runs.get(k))
    real = sum(r[11] for r in cl); day = real / hrs * 24
    if day < 3: continue
    holds = [(r[14] - r[4]) * SL / 60 for r in cl]; mh = med(holds)
    pn = [r[11] for r in cl]; win = sum(p > 0 for p in pn) / len(pn)
    perday = len(both) / hrs * 24
    entry = med([r[4] * SL for r in cl]); cs = sum(1 for r in both if r[4] == 0) / len(both); dev = sum(1 for r in both if CRE.get(r[1]) == u)
    style = 8 <= perday <= 200 and 1 <= mh <= 10 and win >= 0.55 and entry >= 10 and cs < 0.2 and dev <= 1
    if not style: continue
    dd = {k: sum(r[11] for r in runs.get(k, []) if not r[16] and r[13]) for k in ("R1", "R2", "R3")}
    top5 = sum(sorted(pn, reverse=True)[:5])
    ok = all(dd[k] > 0 for k in ("R2", "R3") if runs.get(k)) and real - top5 > 0
    out.append(dict(w=u, ok=ok, day=day, wo5=(real - top5) / hrs * 24, r1=dd["R1"] / HRS["R1"] * 24 if runs.get("R1") else None, r2=dd["R2"] / HRS["R2"] * 24 if runs.get("R2") else None,
                    r3=dd["R3"] / HRS["R3"] * 24 if runs.get("R3") else None, perday=perday, hold=mh, win=win, avgw=statistics.mean([p for p in pn if p > 0]), avgl=statistics.mean([p for p in pn if p <= 0] or [0]),
                    size=med([r[7] for r in cl]), entry=entry, nb=med([r[12] for r in cl]), ns=med([r[13] for r in cl]), open=sum(1 for r in both if r[16]), n=len(both)))
json.dump(out, open("screen3.json", "w"))
P = sorted([r for r in out if r["ok"]], key=lambda r: -r["day"])
print(f"picky minute-holders with >= 3 SOL/day realized over R2+R3: {len(out)}; consistent (both days > 0, > 0 without top 5): {len(P)}")
print(f"  of those >= 10 SOL/day: {sum(r['day'] >= 10 for r in P)} | 5-10: {sum(5 <= r['day'] < 10 for r in P)} | 3-5: {sum(r['day'] < 5 for r in P)}\n")
f = lambda x: f"{x:+6.1f}" if x is not None else "    - "
print("wallet                                        SOL/day w/o-top5   R2/day R3/day R1/day | pos/day hold   win  avgW/avgL    size entry buys sells open")
for r in P:
    print(f"{r['w']:44s} {r['day']:+7.1f} {r['wo5']:+7.1f}   {f(r['r2'])} {f(r['r3'])} {f(r['r1'])} | {r['perday']:6.0f} {r['hold']:4.1f}m {r['win']:4.0%} {r['avgw']:+.2f}/{r['avgl']:+.2f}  {r['size']:5.2f} {r['entry']:4.0f}s {r['nb']:4.0f} {r['ns']:4.0f} {r['open']:4d}")

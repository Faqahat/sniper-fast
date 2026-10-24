#!/usr/bin/env python3
# STRICT pass over screen.py's population: realized (closed positions only) >= 10 SOL/day in R3, still > 0 without its best 5
# tokens, both 12 h halves realized > 0, median hold 1-60 min, and R2 (previous day) realized > 0 when the wallet traded there.
import gzip, glob, json, collections, statistics
HRS = {"R1": 14.88, "R2": 21.79, "R3": 24.0}; SL = 0.212; AG = {"BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"}
W = collections.defaultdict(lambda: collections.defaultdict(list))
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"):
    for line in gzip.open(f, "rt"):
        r = json.loads(line)
        if r[0] in AG: continue
        W[r[0]][r[2]].append(r)
med = lambda v: statistics.median(v) if v else float("nan")
out = []
for u, runs in W.items():
    r3 = runs.get("R3", [])
    if len(r3) < 15: continue
    cl = [r for r in r3 if not r[16] and r[13]]
    real = sum(r[11] for r in cl)
    if real / HRS["R3"] * 24 < 10: continue
    holds = [(r[14] - r[4]) * SL / 60 for r in cl]
    mh = med(holds)
    if not 1 <= mh <= 60: continue
    t0 = min(r[3] for r in r3); h1 = sum(r[11] for r in cl if r[3] - t0 < 12 * 3600); h2 = real - h1
    top5 = sum(sorted((r[11] for r in cl), reverse=True)[:5])
    r2 = [r for r in runs.get("R2", []) if not r[16] and r[13]]; r2d = sum(r[11] for r in r2) / HRS["R2"] * 24 if r2 else None
    r1 = [r for r in runs.get("R1", []) if not r[16] and r[13]]; r1d = sum(r[11] for r in r1) / HRS["R1"] * 24 if r1 else None
    ok = h1 > 0 and h2 > 0 and real - top5 > 0 and (r2d is None or r2d > 0)
    pn = [r[11] for r in cl]
    out.append(dict(w=u, ok=ok, n=len(r3), closed=len(cl), real_day=real / HRS["R3"] * 24, wo5_day=(real - top5) / HRS["R3"] * 24, h1=h1, h2=h2, r2d=r2d, r1d=r1d, hold=mh,
                    hold_p25=statistics.quantiles(holds, n=4)[0] if len(holds) > 3 else mh, hold_p75=statistics.quantiles(holds, n=4)[2] if len(holds) > 3 else mh,
                    win=sum(p > 0 for p in pn) / len(pn), avgw=statistics.mean([p for p in pn if p > 0] or [0]), avgl=statistics.mean([p for p in pn if p <= 0] or [0]),
                    size=med([r[7] for r in cl]), entry=med([r[4] * SL for r in cl]), nb=med([r[12] for r in cl]), ns=med([r[13] for r in cl]),
                    open_n=sum(1 for r in r3 if r[16]), grad=sum(1 for r in r3 if r[15])))
json.dump(out, open("screen2.json", "w"))
P = [r for r in out if r["ok"]]
print(f"realized >= 10 SOL/day + median hold 1-60 min: {len(out)} wallets; passing all consistency checks: {len(P)}\n")
print("wallet                                        pos/day realized/day w/o-top5  12h halves    R2/day  R1/day | hold med (p25-p75)  win  avgW/avgL    size  entry  buys sells")
for r in sorted(P, key=lambda r: -r["real_day"]):
    f = lambda x: f"{x:+7.1f}" if x is not None else "     - "
    print(f"{r['w']:44s} {r['n']:6d} {r['real_day']:+9.1f} {r['wo5_day']:+9.1f}  {r['h1']:+6.1f}/{r['h2']:+6.1f} {f(r['r2d'])} {f(r['r1d'])} | {r['hold']:5.1f}m ({r['hold_p25']:4.1f}-{r['hold_p75']:5.1f}) "
          f"{r['win']:4.0%} {r['avgw']:+.2f}/{r['avgl']:+.2f}  {r['size']:5.2f} {r['entry']:6.0f}s {r['nb']:4.0f} {r['ns']:4.0f}")

#!/usr/bin/env python3
"""SMARTEXIT step 10 (POST-HOC, designed AFTER VAL/HOLD were seen -> NOT eligible as a pass; forward test only):
ADAPTIVE TIMER = causal online choice among exact timers {75,100,125,160}: before each fill, re-price the last K completed fills
(fill rx + 3.5 s < now, so their hold tapes are complete; each priced at its own measured lag, like the engine could from its own
tapes) under every arm; use the arm with the best trailing sum if it beats 125 by > margin SOL, else 125.  History runs across runs
in time order from r37.  Reports gain vs t125 per split / run, own lag + fc20 (choice made on fc0 history)."""
import sys, collections, bisect
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/smartexit")
import slib as L, spol as P
ALL, J, _ = L.load_fills(); ALL.sort(key=lambda f: f.t0)
ARMS = (75, 100, 125, 160)
E0 = [L.events(f) for f in ALL]; E2 = [L.events(f, 0.2) for f in ALL]
V0 = [{H: P.run_policy(f, e, P.p_timer(H)) for H in ARMS} for f, e in zip(ALL, E0)]
V2 = [{H: P.run_policy(f, e, P.p_timer(H), 0.2) for H in ARMS} for f, e in zip(ALL, E2)]
T = [f.t0 for f in ALL]
def run(K, margin):
    pick = []
    for i, f in enumerate(ALL):
        j = bisect.bisect_left(T, f.t0 - int(3.5e9))      # fills complete before now
        lo = max(0, j - K)
        if j - lo < K // 2: pick.append(125); continue
        s = {H: sum(V0[k][H] for k in range(lo, j)) for H in ARMS}
        best = max(ARMS, key=lambda H: s[H])
        pick.append(best if s[best] - s[125] > margin else 125)
    return pick
for K, m in ((100, 0.0), (200, 0.0), (400, 0.0), (200, 0.1), (400, 0.1)):
    pk = run(K, m)
    agg = collections.defaultdict(lambda: [0, 0.0, 0.0, 0.0, collections.Counter()])
    for i, f in enumerate(ALL):
        for key in (f.split, f"r{f.run}"):
            a = agg[key]; a[0] += 1; a[1] += V0[i][125]; a[2] += V0[i][pk[i]] - V0[i][125]; a[3] += V2[i][pk[i]] - V2[i][125]; a[4][pk[i]] += 1
    print(f"K={K} margin={m}: " + " | ".join(f"{sp} n{agg[sp][0]} gain {agg[sp][2]:+.3f} fc20 {agg[sp][3]:+.3f} picks {dict(agg[sp][4])}" for sp in ("dev", "val", "hold")))
    if (K, m) == (200, 0.0):
        for r in sorted({f.run for f in ALL}):
            a = agg[f"r{r}"]; print(f"    r{r}: n {a[0]:4} t125 {a[1]:+.3f} gain {a[2]:+.3f} fc20 {a[3]:+.3f} picks {dict(a[4])}")

#!/usr/bin/env python3
"""PRESEND FILTER: robustness of the frozen candidates (rules.py).
  * permutation test (stratified by run): the fills a rule removes vs the same number of fills drawn at random from the same runs;
    p = share of 20,000 draws whose removed SOL is <= the rule's (a lower removed sum = a better rule). Done per group (DEV, VAL-prim,
    VAL-all), each one separately.
  * time blocks: the gain per run and per 1-hour block (PKT) of each run; the count of blocks better / worse.
  * neighbours of C5 (stop at trigger + N if < M other trades) to show it is not a knife-edge."""
import collections, time
import numpy as np
import sim, rules

DEV = ["ams:r24", "ams:r25"]; VP = ["fra:r23", "fra:r24"]; VS = ["ams:r19", "ams:r20", "fra:r21", "fra:r22"]
W = sim.load()
rng = np.random.default_rng(27)


def removed_fills(arm, send):
    out = []
    for w in W:
        if not w["filled"]: continue
        if arm is not None and not arm(w): out.append(w); continue
        if send is not None:
            ft = [k for k, t in enumerate(w["X"]["tries"]) if t[4]]
            if ft and not send(w, ft[0]): out.append(w)
    return out


def perm(rem, runs, n=20000):
    rem = [w for w in rem if w["run"] in runs]
    obs = sum(w["net"] for w in rem) / 1e9
    by = collections.Counter(w["run"] for w in rem)
    pools = {r: np.array([w["net"] for w in W if w["run"] == r and w["filled"]]) / 1e9 for r in runs}
    sims = np.zeros(n)
    for r, c in by.items():
        P = pools[r]
        idx = np.argsort(rng.random((n, len(P))), axis=1)[:, :c]
        sims += P[idx].sum(1)
    return obs, float((sims <= obs).mean()), float(sims.mean())


for name, kind, arm, send in rules.CANDIDATES + rules.POSTHOC:
    rem = removed_fills(arm, send)
    print(f"=== {name}")
    for g, runs in (("DEV", DEV), ("VAL-prim", VP), ("VAL-all", VP + VS)):
        obs, p, mu = perm(rem, runs)
        print(f"   {g:9s} removed fills {sum(1 for w in rem if w['run'] in runs):3d}: their net {obs:+.3f} vs random {mu:+.3f}  p = {p:.4f}")
    # time blocks: 1 h blocks of each run
    res_w = sim.evaluate(W, arm=arm, send=send)
    blocks = collections.defaultdict(lambda: [0.0, 0.0])
    for w in W:
        b = (w["run"], time.strftime("%m-%d %H", time.gmtime(w["t"] / 1e9 + 18000)))
        r1 = sim.evaluate([w], arm=arm, send=send)["ALL"]
        blocks[b][0] += r1["before"]; blocks[b][1] += r1["after"]
    g = [v[1] - v[0] for v in blocks.values()]
    gd = [v[1] - v[0] for k, v in blocks.items() if k[0] in DEV]
    print(f"   1-h blocks: all {len(g)}: better {sum(1 for x in g if x > 1e-9)}, worse {sum(1 for x in g if x < -1e-9)}, same {sum(1 for x in g if abs(x) <= 1e-9)} | "
          f"dev {len(gd)}: better {sum(1 for x in gd if x > 1e-9)}, worse {sum(1 for x in gd if x < -1e-9)}")
import sys
if "--no-neighbours" in sys.argv: sys.exit(0)
print("\nC5 neighbours (stop at trigger + N if < M other trades since the trigger): gain DEV / VAL-prim / VAL-all, winners removed all")
for N in (4, 5, 6, 7, 8):
    for M in (1, 2, 3):
        res = sim.evaluate(W, send=lambda w, k, N=N, M=M: not (w["X"]["tries"][k][0] >= w["trig_slot"] + N and rules.oth_since(w, k) < M))
        g = lambda runs: sum(res[r]["gain"] for r in runs)
        wr = sum(res[r].get("win_rm", 0) for r in DEV + VP + VS)
        print(f"   N={N} M={M}: {g(DEV):+.3f} / {g(VP):+.3f} / {g(VP + VS):+.3f}   winners removed {int(wr)}")

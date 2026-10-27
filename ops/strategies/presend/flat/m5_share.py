#!/usr/bin/env python3
"""FLAT study (MEASURED): flat share, cost and their weight in each run's losses; QUIET vs no QUIET and size groups with
Wilson 95% intervals. usage: m5_share.py r24 r25 r26 r27 r28"""
import sys, math, collections
import flatlib as FL, evalcore as EC

def wilson(k, n, z=1.96):
    if n == 0: return (0, 0)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d * 100, (c + h) / d * 100)

def main():
    runs = sys.argv[1:]
    groups = collections.defaultdict(lambda: [0, 0, 0.0, 0.0])
    print(f"{'run':4s} {'size':>5s} {'hours':>5s} {'fills':>5s} {'flats':>5s} {'share (95%)':>18s} {'flat net':>8s} {'/fill':>7s} {'%size':>6s} {'losers net':>10s} {'flat share of losses':>20s} {'flats/h':>7s} {'flat SOL/h':>10s}")
    for run in runs:
        B = FL.load_base(run); W = B["W"]; F = [w for w in W if w["filled"]]
        fl = [w for w in F if w["flat"]]
        t0 = min(w["t"] for w in W) / 1e9; t1 = max(w["t"] for w in W) / 1e9; h = (t1 - t0) / 3600
        size = F[0]["spend"] / 1e9 if F else 0
        lo, hi = wilson(len(fl), len(F))
        fn = sum(w["net"] for w in fl) / 1e9; ln = sum(w["net"] for w in F if w["net"] <= 0) / 1e9
        print(f"{run:4s} {size:5.2f} {h:5.1f} {len(F):5d} {len(fl):5d} {len(fl)/len(F)*100:5.1f}% ({lo:4.1f}-{hi:4.1f}) {fn:+8.4f} {fn/len(fl):+7.4f} {fn/len(fl)/size*100:+6.2f} {ln:+10.4f} {fn/ln*100:19.0f}% {len(fl)/h:7.1f} {fn/h:+10.4f}")
        q = "QUIET live (r27, r28)" if run in ("r27", "r28") else "no QUIET (r24-r26)"
        s = "0.50" if size >= 0.45 else "0.34-0.35"
        for g in (q, "size " + s, "all"):
            groups[g][0] += len(fl); groups[g][1] += len(F); groups[g][2] += fn; groups[g][3] += h
    # dev with QUIET replayed
    C = FL.Chain((1,)); O = EC.Others(C)
    k = n = 0
    for run in ("r24", "r25", "r26"):
        for w in FL.load_base(run)["W"]:
            if not w["filled"]: continue
            b = EC.run_rules(w, O, skip=bool(w.get("quiet_skip_replay")), stops=[(6, 2)])
            if b["fill_kept"]: n += 1; k += bool(w["flat"])
    groups["dev with QUIET replayed"] = [k, n, float("nan"), float("nan")]
    print()
    for g, (k, n, fn, h) in groups.items():
        lo, hi = wilson(k, n)
        print(f"{g:28s} flats {k:3d} / fills {n:4d} = {k/n*100:5.1f}% (95% {lo:4.1f}-{hi:4.1f})" + (f", flat net {fn:+.3f} SOL, {fn/h:+.4f} SOL/h" if fn == fn else ""))
main()

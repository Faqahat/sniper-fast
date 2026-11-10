#!/usr/bin/env python3
"""BUNDLEWAL step 4: score each feature as a SKIP filter (skip when feature >= threshold) on real live fills.
Threshold choice uses DEV ONLY (rule fixed here before any VAL/HOLD number is printed):
  candidates = DEV quantiles 50..98% of the feature (cutoff A); keep those blocking >= 10 DEV fills;
  pick the one with the best DEV "net saved without the top-5 |pnl| blocked trades"; ties -> higher net saved.
Then VAL and HOLDOUT are scored once with the frozen thresholds (cutoff A, and the same threshold at cutoff F = fill-1).
Money: blocking a fill saves exactly its realized P&L (net saved = -sum blocked pnl). Re-fills of the same window not modelled.
-20% followers row: ESTIMATE, crude: blocked winners' P&L x 0.8, losers unchanged (no follower replay)."""
import json, collections, sys
OUT = "/home/it/sniper-data/filters3/bundlewal"
VARS = ["nl", "cs", "nrecv", "precv", "eqbal", "fam"]
DEVONLY = "--dev-only" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]
FEAT = args[0] if args else "features2.jsonl"
P = [json.loads(l) for l in open(f"{OUT}/{FEAT}")]
C = [p for p in P if p["cov"]]


def stats(v):
    s = sorted(v, key=lambda x: -abs(x))
    n = len(v); W = sum(x > 0 for x in v)
    net = sum(v)
    return dict(n=n, W=W, L=n - W, net=net, saved=-net, saved_no5=-sum(s[5:]),
                saved_f20=-sum(x * 0.8 if x > 0 else x for x in v))


def fmt(st, tot=None):
    return (f"blocked {st['n']:4d}  W/L {st['W']:3d}/{st['L']:3d}  blocked net {st['net']:+7.3f}  saved {st['saved']:+7.3f}"
            f"  no-top5 {st['saved_no5']:+7.3f}  f-20% {st['saved_f20']:+7.3f}")


def blocked(rows, v, thr, cut="A"):
    return [p["pnl"] for p in rows if p[cut][v] >= thr]


def choose(v):
    dev = [p for p in C if p["split"] == "DEV"]
    xs = sorted(p["A"][v] for p in dev)
    best = None
    for q in range(50, 99):
        thr = xs[int(len(xs) * q / 100)]
        if thr <= 0: continue
        b = blocked(dev, v, thr)
        if len(b) < 10: continue
        st = stats(b)
        key = (round(st["saved_no5"], 6), st["saved"])
        if best is None or key > best[0]: best = (key, thr, q)
    return best


if __name__ == "__main__":
    print("coverage (positions with full history):", collections.Counter((p["split"], p["cov"]) for p in P))
    for sp in (("DEV",) if DEVONLY else ("DEV", "VAL", "HOLD")):
        r = [p["pnl"] for p in C if p["split"] == sp]
        print(f"  {sp}: covered fills {len(r)} net {sum(r):+.3f}")
    frozen = {}
    for v in VARS:
        b = choose(v)
        frozen[v] = None if b is None else dict(thr=b[1], q=b[2])
    json.dump(dict(rule="skip if feature >= thr (cutoff A = arm/trigger)", features=FEAT, params=dict(MINSOL=0.02, TOL=0.05, KMIN=3, MINH_pct=0.05),
                   thresholds=frozen), open(f"{OUT}/frozen_thresholds.json" if DEVONLY else "/dev/null", "w"), indent=1)
    for v in VARS:
        fz = frozen[v]
        print(f"\n=== {v}  frozen thr {fz}")
        if not fz: continue
        for cut in ("A", "F"):
            for sp in (("DEV",) if DEVONLY else ("DEV", "VAL", "HOLD")):
                rows = [p for p in C if p["split"] == sp]
                print(f"  {cut} {sp:4s} n={len(rows):4d} | " + fmt(stats(blocked(rows, v, fz['thr'], cut))))
        for sp in (("DEV",) if DEVONLY else ("DEV", "VAL", "HOLD")):
            runs = sorted({p["run"] for p in C if p["split"] == sp})
            line = []
            for rn in runs:
                rows = [p for p in C if p["split"] == sp and p["run"] == rn]
                b = blocked(rows, v, fz["thr"]); line.append(f"r{rn}:{len(b)}/{-sum(b):+.3f}")
            print(f"    per run {sp}: " + "  ".join(line))
        for sp in (("DEV",) if DEVONLY else ("DEV", "VAL", "HOLD")):
            for k in ("t2", "rearm"):
                rows = [p for p in C if p["split"] == sp and p["kind"] == k]
                print(f"    kind {sp:4s} {k:5s} n={len(rows):4d} | " + fmt(stats(blocked(rows, v, fz['thr']))))
    if DEVONLY: sys.exit(0)
    print("\nBnx6XibY case:")
    for p in P:
        if p["mint"].startswith("Bnx6XibY"):
            print(json.dumps({k: p.get(k) for k in ("run", "w", "pnl", "kind", "age", "cov", "A", "F")}))

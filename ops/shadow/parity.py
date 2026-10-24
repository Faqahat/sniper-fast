#!/usr/bin/env python3
# PARITY (read-only, offline): live shadow features/scores vs the offline pipeline (same frozen model, same mints)
import sys, json, gzip, math, collections
import numpy as np
SH, TAB, MODEL = sys.argv[1:4]
M = json.load(open(MODEL))
live = {}
for l in open(SH):
    r = json.loads(l)
    if r.get("type") == "decide" and r.get("quote", "sol") == "sol": live[r["mint"]] = r      # SOL-quoted launches only (what we buy)
off = {}
for l in gzip.open(TAB, "rt"):
    r = json.loads(l)
    if r["mint"] in live: off[r["mint"]] = r
common = [m for m in live if m in off]
print(f"live scored {len(live)}; also in offline table {len(common)}")
def val(r, k):
    if "==" in k:
        a, v = k.split("==", 1); return 1.0 if str(r.get(a)) == v else 0.0
    v = r.get(k); return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else (float(v) if isinstance(v, bool) else float("nan"))
rows = []
for k in M["features"]:
    a = np.array([val(live[m]["features"], k) for m in common]); b = np.array([val(off[m], k) for m in common])
    both = ~np.isnan(a) & ~np.isnan(b)
    eq = np.mean(np.isclose(a[both], b[both], rtol=1e-3, atol=1e-6)) if both.any() else float("nan")
    nan_mis = np.mean(np.isnan(a) != np.isnan(b))
    rows.append((eq, k, nan_mis, np.nanmean(a) if (~np.isnan(a)).any() else float("nan"), np.nanmean(b) if (~np.isnan(b)).any() else float("nan")))
print(f"{'feature':48} {'match%':>7} {'NaN mismatch':>12} {'live mean':>11} {'offline mean':>12}")
for eq, k, nm, ma, mb in sorted(rows, key=lambda x: (x[0] if not math.isnan(x[0]) else -1)):
    print(f"{k:48} {eq * 100:6.1f}% {nm * 100:11.1f}% {ma:11.4g} {mb:12.4g}")

#!/usr/bin/env python3
# sssssDdM EXIT HAZARD (read-only): over every non-fleet trade while it holds (its own trips, R2/R3), the probability that this
# trade is its exit trigger (its sell <= 2 slots later), by bands of: the trade's 1-slot price change (ret1), the trade's own
# move, side and size, position multiple, drawdown from peak, slots held, sells this slot, and 2-way combos. -> printed
import sys, json, zlib, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p4_eval as E
OUT = "/home/moiz/sniper-data/strategies/sssss"
UID = zlib.crc32(b"sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d")
SIBS = ["ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E", "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi", "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ"]
FLEET = np.array([UID] + [zlib.crc32(s.encode()) for s in SIBS], np.int64)
run = sys.argv[1] if len(sys.argv) > 1 else "R2"
E.load([run]); d = E.DAYS[run]; F = d["F"]; FI = d["FI"]; isfleet = np.isin(d["uid"], FLEET)
T = [t for t in json.load(open(f"{OUT}/trips_{run}.json")) if t["closed"] and t["sells"]]
R = []
for t in T:
    k0 = t["k0"]; ks = t["sells"][-1]["k"]; s0 = d["s"][k0]; p_in = t["p_in"]; pk = 1.0
    rows = []
    for q in range(k0 + 1, ks):
        if isfleet[q]: continue
        m = float(d["vsol"][q] / d["vtok"][q]) / p_in; pk = max(pk, m)
        rows.append([q, m, pk, 1 - m / pk, int(d["s"][q] - s0), 0])
    if rows and d["s"][ks] - d["s"][rows[-1][0]] <= 2: rows[-1][5] = 1
    R += rows
R = np.array(R, float); q = R[:, 0].astype(np.int64); y = R[:, 5]
X = dict(ret1=F[q, FI["ret1"]], move=F[q, FI["move"]], side=d["buy"][q].astype(float), sol=d["sol"][q] / 1e9, mult=R[:, 1], dd=R[:, 3], held=R[:, 4],
         curve=d["vsol"][q] / 1e9, athr=F[q, FI["ath_r"]], age=F[q, FI["age"]], devs=F[q, FI["dev_s30"]], fams=F[q, FI["fam_s10"]], wt=d["wt"][q].astype(float),
         ns1=F[q, FI["ns1"]], nb1=F[q, FI["nb1"]], ssol1=F[q, FI["ssol1"]], bsol1=F[q, FI["bsol1"]], ret3=F[q, FI["ret3"]], net3=F[q, FI["net3"]])
print(f"{run}: {len(y)} decision rows, {int(y.sum())} exits; base hazard {y.mean():.3%}")
def band(name, edges):
    x = X[name]; out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (x >= lo) & (x < hi)
        if m.sum() >= 50: out.append(f"[{lo:g},{hi:g}) n{int(m.sum())} {y[m].mean():.2%}")
    print(f"  {name}: " + " | ".join(out))
band("ret1", [-100, -15, -10, -7, -5, -3, -2, -1, -0.01, 0.01, 1, 2, 3, 5, 10, 1000])
band("move", [-100, -10, -5, -3, -2, -1, -0.3, 0, 0.3, 1, 2, 3, 5, 1000])
band("mult", [0, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.2, 1.3, 1.5, 2, 100])
band("dd", [0, 0.001, 0.02, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 1.01])
band("held", [0, 2, 5, 10, 20, 50, 100, 200, 400, 800, 1600, 100000])
band("ns1", [0, 1, 2, 3, 4, 6, 100]); band("ssol1", [0, 0.01, 0.3, 0.6, 1, 2, 4, 100]); band("nb1", [0, 1, 2, 3, 5, 100])
band("ret3", [-100, -15, -10, -5, -2, 0, 2, 5, 10, 1000]); band("curve", [30, 40, 50, 60, 70, 80, 85, 90, 95, 100, 105, 110, 120])
band("athr", [0, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 1.01]); band("devs", [0, 0.001, 0.5, 2, 100]); band("fams", [0, 1, 2, 4, 100]); band("wt", [0, 1, 2, 3, 4, 5, 11, 19, 20, 21]); band("net3", [-100, -4, -2, -1, -0.3, 0.3, 1, 2, 4, 100])
# 2-way: ret1 x mult
print("  ret1 x mult (hazard %):")
for lo, hi in ((-100, -5), (-5, -2), (-2, -0.01), (-0.01, 0.01), (0.01, 2), (2, 1000)):
    cells = []
    for mlo, mhi in ((0, 0.9), (0.9, 1.0), (1.0, 1.1), (1.1, 1.3), (1.3, 100)):
        m = (X["ret1"] >= lo) & (X["ret1"] < hi) & (X["mult"] >= mlo) & (X["mult"] < mhi)
        cells.append(f"m[{mlo},{mhi}) {y[m].mean():.1%}(n{int(m.sum())})" if m.sum() >= 30 else f"m[{mlo},{mhi}) -")
    print(f"    ret1[{lo},{hi}): " + "  ".join(cells))
print("  side x ret1 (hazard %):")
for sd in (0, 1):
    cells = []
    for lo, hi in ((-100, -5), (-5, -2), (-2, -0.01), (-0.01, 0.01), (0.01, 2), (2, 5), (5, 1000)):
        m = (X["side"] == sd) & (X["ret1"] >= lo) & (X["ret1"] < hi)
        cells.append(f"[{lo},{hi}) {y[m].mean():.1%}(n{int(m.sum())})" if m.sum() >= 30 else f"[{lo},{hi}) -")
    print(f"    {'BUY ' if sd else 'SELL'}: " + "  ".join(cells))

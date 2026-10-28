#!/usr/bin/env python3
"""VERIFY v6: is the fresh-hour re-arm result consistent with the in-sample claim? Null = in-sample per-window results resampled to
the fresh window count. (a) G2's rsim: re windows of res_D1..5_h2 (draw 0), per window: fill P&L - NOW cost - failed tries; fresh =
fwd2 (mean of 3 draws). (b) my re-implementation: D2-D5 seed-averaged windows vs fresh2. One-sided P(null sum <= fresh)."""
import pickle, collections, sys, numpy as np
FWD = sys.argv[1] if len(sys.argv) > 1 else "fwd2"; MA = sys.argv[2] if len(sys.argv) > 2 else "v2b_fresh2"; MF = sys.argv[3] if len(sys.argv) > 3 else "v2b_fresh2fra"
COST = 5120 + 200_000 + 605_000 + 1_200_000 + 5020; FAIL = 5120
R = "/home/moiz/sniper-data/haqq_dissect/rearm"; D = "/home/moiz/sniper-data/haqq_dissect/verify"
name = "any:20:30:8:2"; rng = np.random.default_rng(11)
def rewin(rows):
    out = []
    for r in rows:
        if not r[1] or r[0][0] != "re": continue
        out.append(((r[8][2]["base"][0] - COST) if r[3] else 0) / 1e9 - r[4] * FAIL / 1e9)
    return out
ins = []
for d in range(1, 6): ins += rewin(pickle.load(open(f"{R}/res_D{d}_h2.pkl", "rb"))["out"][name][0])
F = pickle.load(open(f"{D}/{FWD}_res.pkl", "rb"))["out"][name]
fr = [np.sum(rewin(x)) for x in F]; nf = len(rewin(F[0]))
ins = np.array(ins); null = np.array([ins[rng.integers(0, len(ins), nf)].sum() for _ in range(20000)])
print(f"(a) G2 rsim: in-sample re windows {len(ins):,} mean {1e3 * ins.mean():+.3f} mSOL/window; fresh re windows {nf}, re-window net per draw {np.round(fr, 3)} mean {np.mean(fr):+.3f}")
print(f"    null sum for {nf} windows: mean {null.mean():+.3f}, 5-95% [{np.percentile(null, 5):+.3f}, {np.percentile(null, 95):+.3f}]; P(null <= fresh mean) = {np.mean(null <= np.mean(fr)):.3f}")
def mine(pkl):
    Z = pickle.load(open(pkl, "rb")); W = collections.defaultdict(float)
    for r in Z["rows"]:
        v = -r["fees"] / 1e9
        if r["fill"] is not None and not r["base_has"]: v += (r["fill"]["ex"]["live"] - COST) / 1e9
        W[(r["mint"], r["s"])] += v / Z["seeds"]
    return np.array(list(W.values()))
for tag, a, b in (("AMS-mix landing", "v2b_d2345.pkl", f"{MA}.pkl"), ("FRA landing", "v2b_d2345fra.pkl", f"{MF}.pkl")):
    I = mine(f"{D}/{a}"); Fw = mine(f"{D}/{b}")
    null = np.array([I[rng.integers(0, len(I), len(Fw))].sum() for _ in range(20000)])
    print(f"(b) mine, {tag}: in-sample {len(I):,} windows mean {1e3 * I.mean():+.3f} mSOL/window; fresh {len(Fw)} windows sum {Fw.sum():+.3f}; null mean {null.mean():+.3f} "
          f"[{np.percentile(null, 5):+.3f}, {np.percentile(null, 95):+.3f}]; P(null <= fresh) = {np.mean(null <= Fw.sum()):.3f}")

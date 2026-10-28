#!/usr/bin/env python3
"""EXIT step 13 (read-only): do 'wave' exits reproduce haqq's own exit P&L on HIS lots? Exact replay of each non-DEAD lot alone
(vx / vx9), his reaction delay (MEASURED quantiles of his DIP buys), his minimum hold (slot buy+2).
  RIDE t1 S tmax : from t1 on, sell once no outside buy has landed for S ms (if none landed in the last S ms at t1: sell at t1)
  STALL S tmax   : after the first outside buy following his buy, the first gap of S ms with no outside buy (not before slot+2)
Out: haqq_dissect/exit/x13.txt"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
QS = (5, 15, 25, 35, 45, 55, 65, 75, 85, 95)
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
Z = pickle.load(open(f"{X.OUT}/haqq.pkl", "rb")); LOTS = Z["lots"]
A = np.load(f"{X.OUT}/paths.npz"); off = A["off"]; ex = A["lot_exit"]; DCC = A["dcc"]; BU = A["buy"]; SO = A["sol"]; VX = A["vx"]; VX9 = A["vx9"]
dmy = np.percentile([L["d_ms"] for L in LOTS if L["t"] == "DIP" and L.get("d_ms") is not None], QS)
pols = [("ACT",)] + [("RIDE", s, tm) for s in (100, 150, 300, 500, 1000) for tm in (1000, 2000, 5000, 10000, 20000)] + [("STALL", s, tm) for s in (150, 300, 500) for tm in (2000, 5000, 10000)]
def hb(h):
    s = h / 1000
    return "<2 s" if s < 2 else "2-15 s" if s < 15 else "15-60 s" if s < 60 else ">60 s"
res = collections.defaultdict(float); res9 = collections.defaultdict(float); n_g = collections.Counter(); per_day = collections.defaultdict(float)
for i, L in enumerate(LOTS):
    if L["t"] == "DEAD" or L["close_cc"] is None: continue
    a, b = off[i], off[i + 1]; n = b - a
    if n == 0: continue
    e = ex[i]; inside = 0 < e < n; xt = L["close_cc"] - L["cc"]; g = hb(xt); n_g[g] += 1
    dc = DCC[a:b].astype(np.float64); bu = BU[a:b]; so = SO[a:b].astype(np.float64)
    t2 = 2 * X.SMS - (L["cc"] - L["slot"] * X.SMS)
    bt = dc[bu]
    for fol, V, R in ((1.0, VX, res), (0.9, VX9, res9)):
        v = V[a:b].astype(np.float64)
        def at(t): return float(np.mean([v[q] if q >= 0 else 0.975 for q in (np.searchsorted(dc, t + dmy, side="right") - 1)]))
        for pol in pols:
            if pol[0] == "ACT": val = (v[e - 1] - 1) * L["cost"] if inside else L["pnl"]
            else:
                _, s, tm = pol
                if pol[0] == "RIDE":
                    rec = bt[(bt <= t2) & (bt > t2 - s)]
                    if not len(rec): tt = t2
                    else:
                        later = bt[bt > t2 - s]; gaps = np.diff(np.concatenate([later, [np.inf]])); j = int(np.argmax(gaps >= s)); tt = max(later[j] + s, t2)
                else:
                    if not len(bt): tt = tm
                    else:
                        gaps = np.diff(np.concatenate([bt, [np.inf]])); j = int(np.argmax(gaps >= s)); tt = max(bt[j] + s, t2)
                val = (at(min(tt, tm)) - 1) * L["cost"]
            R[(pol, g)] += val; R[(pol, "all")] += val
            if fol == 1.0: per_day[(pol, L["day"])] += val
hg = ("<2 s", "2-15 s", "15-60 s", ">60 s")
P("# Wave exits on haqq's own non-DEAD lots (exact replay of each lot alone, his delay + min hold), SOL 10-22..10-28")
P("| policy | " + " | ".join(f"{g} ({n_g[g]:,})" for g in hg) + " | all | all 0.9 fol | " + " | ".join(f"D{d}" for d in range(7)) + " |")
P("|---|" + "---|" * (len(hg) + 2 + 7))
order = sorted(pols, key=lambda p: -res[(p, "all")])
for pol in order[:20] + ([("ACT",)] if ("ACT",) not in order[:20] else []):
    P(f"| {pol} | " + " | ".join(f"{res[(pol, g)]:+.1f}" for g in hg) + f" | {res[(pol, 'all')]:+.1f} | {res9[(pol, 'all')]:+.1f} | " + " | ".join(f"{per_day[(pol, d)]:+.1f}" for d in range(7)) + " |")
open(f"{X.OUT}/x13.txt", "w").write("\n".join(out) + "\n")

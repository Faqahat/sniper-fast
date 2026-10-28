#!/usr/bin/env python3
"""REARM step 12 (read-only; G2): VALUE-DEPENDENT fill rate (analyst H's correction) applied to the re-arm replay.
1. MEASURED check first (val_<run>.pkl, AMS r24-r33 + FRA r26, 40 replay draws per live window): live fill share vs THIS replay's
   fill share per bucket of the replay's value of the window (mSOL when filled). If the replay already fills high-value dumps as
   rarely as live does, H's thinning (built against a crossing model that fills 84 %) must not be applied on top of it.
2. ADDED re-arm value (any:20:30:8:2 and analyst A's 0.02:50:120:2:0) per day under three weightings of every fill (base and re):
   model = 1; VD = this replay's measured live/replay fill ratio of the fill's value bucket (capped at 1.0, so never upweighted);
   H-PF = analyst H's f9 PF_b (live fill share vs a crossing model; WORST CASE here, double counting the replay's own contention),
   buckets on the fill's gross WAVE value as H did. Failed-try fees unchanged. Out: r12.txt"""
import sys, os, pickle, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r8_report as R8
import dv8lib as L
OUT = R8.OUT
B = [-1e18, -10, 0, 10, 30, 60, 1e18]
HPF = [0.571, 0.678, 0.623, 0.495, 0.415, 0.225]
Lo = []
def P(s=""): print(s, flush=True); Lo.append(s)

# 1. measured check
agg = collections.defaultdict(lambda: np.zeros(5))
for r in ["a24", "a25", "a26", "a27", "a28", "a29", "a30", "a31", "a32", "a33", "f26"]:
    Z = pickle.load(open(f"{OUT}/val_{r}.pkl", "rb")); M = Z["meta"]
    lv = {x["w"]: x["live"] for x in M["live"]}
    for w in lv:
        f = np.array([by[w][1] for _, by in Z["out"]]); p = np.array([by[w][2] for _, by in Z["out"]]) / 1e6
        if f.sum() == 0: continue
        b = int(np.searchsorted(B, p[f > 0].mean()) - 1)
        lf = lv[w]["filled"] > 0
        agg[b] += [1, lf, f.mean(), ((lv[w]["pnl"] + lv[w].get("rb", 0)) / 1e6 if lf else 0.0), (p * f).sum() / len(f)]
P("# Value-dependent fill rate: is the replay's fill rate right per value bucket? (live MEASURED vs replay INFERRED, 40 draws, 1,092 live windows the replay fills)")
P("| Replay value of the window when filled (mSOL) | Windows | Live fill share | Replay fill share | Live / replay fill | Live P&L SOL | Replay P&L SOL | H's PF_b (vs a crossing model) |")
P("|---|---|---|---|---|---|---|---|")
VD = []
for b in range(6):
    n, lf, rf, lp, rp = agg[b]
    VD.append(min(lf / max(rf, 1e-9), 1.0))
    P(f"| {B[b]:.0f}..{B[b + 1]:.0f} | {n:.0f} | {lf / n:.3f} | {rf / n:.3f} | {lf / max(rf, 1e-9):.2f} | {lp / 1e3:+.3f} | {rp / 1e3:+.3f} | {HPF[b]} |")
T = agg_all = np.sum([agg[b] for b in range(6)], axis=0)
P(f"| all | {T[0]:.0f} | {T[1] / T[0]:.3f} | {T[2] / T[0]:.3f} | {T[1] / T[2]:.2f} | {T[3] / 1e3:+.3f} | {T[4] / 1e3:+.3f} | |")
P(f"VD weights used (capped at 1): {[round(x, 2) for x in VD]}")


def wsum(rows, wfun):
    pf = fee = 0.0; nf = 0
    for r in rows:
        if not r[1]: continue
        fee += r[4] * R8.FAIL
        if r[3]:
            g = r[8][2]["base"][0] - R8.COST["NOW"]; gw = r[8][2]["wave"][0]
            pf += wfun(g / 1e6, gw / 1e6) * g; nf += 1
    return pf / 1e9, fee / 1e9


def wf_model(g, gw): return 1.0
def wf_vd(g, gw): return VD[int(np.searchsorted(B, g) - 1)]
def wf_h(g, gw): return HPF[int(np.searchsorted(B, gw) - 1)]


for C in ("any:20:30:8:2", "0.02:50:120:2:0"):
    P(f"\n## {C}: ADDED vs base per day (SOL), fills weighted by value bucket")
    P("| Day | model | VD (measured residual) | VD x 0.81 | H-PF (worst case) |")
    P("|---|---|---|---|---|")
    S = collections.defaultdict(float)
    for d in range(7):
        res = R8.load_day(d, ["g2", "h2"])
        if res is None or C not in res: continue
        out = []
        for nm, wf in (("m", wf_model), ("vd", wf_vd), ("h", wf_h)):
            pc, fc = wsum(res[C], wf); pb, fb = wsum(res["base"], wf)
            out.append((nm, (pc - pb) - (fc - fb), pc - pb, fc - fb))
        m, vd, h = out
        vd81 = (0.81 * vd[2] if vd[2] > 0 else vd[2]) - vd[3]
        P(f"| {L.day_name(d)} | {m[1]:+.2f} | {vd[1]:+.2f} | {vd81:+.2f} | {h[1]:+.2f} |")
        for k, v in (("m", m[1]), ("vd", vd[1]), ("vd81", vd81), ("h", h[1])): S[k] += v
    P(f"| **Sum** | {S['m']:+.2f} | {S['vd']:+.2f} | {S['vd81']:+.2f} | {S['h']:+.2f} |")
open(f"{OUT}/r12.txt", "w").write("\n".join(Lo) + "\n")

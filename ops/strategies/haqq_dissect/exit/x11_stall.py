#!/usr/bin/env python3
"""EXIT step 11 (read-only): is haqq's exit a 'wave-end' exit? At his exit (and at a random time in the same hold, seeded):
ms since the last outside buy / last outside trade (rows landed before his sell), outside buys landed in the last 400 ms,
number of outside buys since his buy, and whether the last outside trade was a sell. MEASURED on the tape.
Out: haqq_dissect/exit/x11.txt"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
Z = pickle.load(open(f"{X.OUT}/haqq.pkl", "rb")); LOTS = Z["lots"]
A = np.load(f"{X.OUT}/paths.npz"); off = A["off"]; ex = A["lot_exit"]; DCC = A["dcc"]; BU = A["buy"]; SO = A["sol"]; VA = A["va"]
rng = np.random.default_rng(11)
R = collections.defaultdict(lambda: collections.defaultdict(list))
def hb(h):
    s = h / 1000
    return "<2 s" if s < 2 else "2-15 s" if s < 15 else "15-60 s" if s < 60 else ">60 s"
for i, L in enumerate(LOTS):
    if L["t"] == "DEAD" or L["close_cc"] is None: continue
    a, b = off[i], off[i + 1]; n = b - a; e = ex[i]
    if not (0 < e < n): continue
    dc = DCC[a:b].astype(np.float64); bu = BU[a:b]; so = SO[a:b].astype(np.float64); va = VA[a:b].astype(np.float64)
    xt = L["close_cc"] - L["cc"]; g = hb(xt)
    lo = 2 * X.SMS - (L["cc"] - L["slot"] * X.SMS)
    rt = rng.uniform(max(lo, 0), max(xt, lo + 1))
    for tag, t0 in (("exit", xt - 1e-6), ("random", rt)):
        q = np.searchsorted(dc, t0, side="left")           # rows strictly before t0
        if q == 0: continue
        bq = np.flatnonzero(bu[:q])
        R[(g, tag)]["since_buy"].append(t0 - dc[bq[-1]] if len(bq) else np.nan)
        R[(g, tag)]["since_any"].append(t0 - dc[q - 1])
        R[(g, tag)]["last_sell"].append(float(not bu[q - 1]))
        R[(g, tag)]["nbuy"].append(len(bq))
        w = (dc[:q] > t0 - 400) & bu[:q]
        R[(g, tag)]["b400"].append(float(so[:q][w].sum()))
        R[(g, tag)]["ret"].append(va[q - 1] - 1)
        # wave ended: >= 1 buy since his entry and none in the last 150 ms
        R[(g, tag)]["stall150"].append(float(len(bq) > 0 and t0 - dc[bq[-1]] >= 150))
P("# haqq's exits: the moment he sells vs a random moment in the same hold (MEASURED). Medians unless marked")
P("| hold | at | n | ms since last outside buy p25/50/75 | ms since last outside trade p50 | last trade a sell % | buys since his buy p50 | buy SOL last 400 ms mean | ret now p50 | no buy for >=150 ms after >=1 buy % |")
P("|---|---|---|---|---|---|---|---|---|---|")
for g in ("<2 s", "2-15 s", "15-60 s"):
    for tag in ("exit", "random"):
        r = R[(g, tag)]
        if not r: continue
        sb = np.array(r["since_buy"]); sb = sb[np.isfinite(sb)]
        P(f"| {g} | {tag} | {len(r['since_any']):,} | " + " / ".join(f"{x:.0f}" for x in np.percentile(sb, [25, 50, 75])) +
          f" | {np.median(r['since_any']):.0f} | {100 * np.mean(r['last_sell']):.0f} | {np.median(r['nbuy']):.0f} | {np.mean(r['b400']):.2f} | {100 * np.median(r['ret']):+.1f}% | {100 * np.mean(r['stall150']):.0f} |")
open(f"{X.OUT}/x11.txt", "w").write("\n".join(out) + "\n")

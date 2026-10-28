#!/usr/bin/env python3
"""EXIT step 10 (read-only): the lot's replayed value (vx, exact, his later trades removed) around haqq's exit:
value at his exit + d ms for d in -1000..+3000, vs the same around a RANDOM time in the same lot's hold (seeded), and big outside
sells landing just after his exit vs after the random time. MEASURED on the tape (replay values INFERRED).
Out: haqq_dissect/exit/x10.txt"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
Z = pickle.load(open(f"{X.OUT}/haqq.pkl", "rb")); LOTS = Z["lots"]
A = np.load(f"{X.OUT}/paths.npz"); off = A["off"]; ex = A["lot_exit"]; DCC = A["dcc"]; VX = A["vx"]; BU = A["buy"]; SO = A["sol"]
DS = (-1000, -400, -200, -100, -50, 0, 50, 100, 200, 400, 1000, 3000)
rng = np.random.default_rng(11)
acc = collections.defaultdict(lambda: collections.defaultdict(list))
bigs = collections.defaultdict(lambda: collections.Counter())
def hb(h):
    s = h / 1000
    return "<2 s" if s < 2 else "2-15 s" if s < 15 else "15-60 s" if s < 60 else ">60 s"
for i, L in enumerate(LOTS):
    if L["t"] == "DEAD" or L["close_cc"] is None: continue
    a, b = off[i], off[i + 1]; n = b - a; e = ex[i]
    if not (0 < e < n): continue
    dc = DCC[a:b].astype(np.float64); v = VX[a:b].astype(np.float64); bu = BU[a:b]; so = SO[a:b].astype(np.float64)
    xt = L["close_cc"] - L["cc"]
    if dc[-1] < xt + 3000: continue                      # need 3 s of path after the exit
    lo = 2 * X.SMS - (L["cc"] - L["slot"] * X.SMS)
    rt = rng.uniform(max(lo, 0), max(xt, lo + 1))
    g = hb(xt)
    for tag, t0 in (("exit", xt - 1e-6), ("random", rt)):
        # value just before his sell (rows strictly before t0), then at t0 + d
        base_q = np.searchsorted(dc, t0, side="left") - 1
        if base_q < 0: continue
        vb = v[base_q]
        for d in DS:
            q = np.searchsorted(dc, t0 + d, side="right") - 1 if d != 0 else base_q
            acc[(g, tag)][d].append((v[max(q, 0)] - vb) * L["cost"])
        w = (dc > t0) & (dc <= t0 + 424)
        bigs[(g, tag)]["n"] += 1
        bigs[(g, tag)]["sell>=1"] += int((w & ~bu & (so >= 1)).any())
        bigs[(g, tag)]["buy>=1"] += int((w & bu & (so >= 1)).any())
        bigs[(g, tag)]["netflow"] += 0
        acc[(g, tag)]["flow"].append(float(so[w & bu].sum() - so[w & ~bu].sum()))
P("# Around haqq's exits: replayed lot value change vs the value just before his sell (mSOL per lot), exit vs a random time in the same hold")
P("| hold group | at | lots | " + " | ".join(f"{d:+d} ms" for d in DS) + " | big sell >=1 SOL in next 424 ms | big buy >=1 | net outside flow next 424 ms (SOL) |")
P("|---|---|---|" + "---|" * len(DS) + "---|---|---|")
for g in ("<2 s", "2-15 s", "15-60 s", ">60 s"):
    for tag in ("exit", "random"):
        A_ = acc[(g, tag)]; B_ = bigs[(g, tag)]
        if not A_: continue
        P(f"| {g} | {tag} | {len(A_[0]):,} | " + " | ".join(f"{1000 * np.mean(A_[d]):+.1f}" for d in DS) + f" | {100 * B_['sell>=1'] / B_['n']:.0f}% | {100 * B_['buy>=1'] / B_['n']:.0f}% | {np.mean(A_['flow']):+.2f} |")
open(f"{X.OUT}/x10.txt", "w").write("\n".join(out) + "\n")

#!/usr/bin/env python3
"""pos step 13 (read-only): landing stress for the re-arm rule set (p12 set: prev whale dump paid >= +5%, gap 3-52 slots, age <= 120 s).
Our position k after the dump = round(m x q x N_w), q drawn from the p8c pre-send model (live pre-send fills), m = 1, 2, 3; and the
REACTIVE rank model (uni rank draws, our M2 landing) for comparison. Fill if entry price <= 0.88 x pre-dump. 2-slot exit. Out: p13.txt"""
import sys, json, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import p6_rules as R6
import dv8lib as L
from plib import Out, OUT
P = Out(f"{OUT}/p13.txt")
Z = np.load(f"{L.D}/uni.npz"); X = Z["X"]; M = Z["M"]; RR = Z["R"]
hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
bt = M["bt"].astype(np.int64); usable = np.isin((bt + 18000) // 3600 * 3600 - 18000, list(good)) & ~np.load(f"{L.D}/mayhem.npy")
day = ((bt - L.DAY0) // 86400).astype(int)
C = np.load(f"{OUT}/p8c.npz"); ideal2 = C["ideal2"]
wh = np.flatnonzero(X[:, 2] >= 6.0); o = wh[np.lexsort((M["cc"][wh], M["mint"][wh]))]
prev = {}; last = None
for i in o:
    m = int(M["mint"][i])
    if last is not None and last[0] == m: prev[i] = last[1]
    last = (m, i)
g = [i for i in wh if usable[i] and i in prev and ideal2[prev[i]] >= 0.02 and 3 <= M["slot"][i] - M["slot"][prev[i]] <= 52 and M["age"][prev[i]] * 0.212 <= 120]
# p8c q model (re-fit identically is slow; use its summary: k/N_w by bucket from live fills -- reload)
lp = pickle.load(open(f"{L.D}/live_presend.pkl", "rb"))
tape = R6.Tape(); rng = np.random.default_rng(4)
qs_all = None
txt = open(f"{OUT}/p8c.txt").read().splitlines()[0]
P(f"# landing stress on the re-arm rule set: {len(g):,} dumps; p8c model: {txt[2:]}")
EDG = (0, 1, 2, 3, 5, 8, 13, 10 ** 6); QM = {0: 0.0, 1: 0.24, 2: 0.26, 3: 0.21, 4: 0.22, 5: 0.17, 6: 0.13}   # bucket means from p8c
def run(mult=None, reactive=False):
    vals = []; fills = 0; n = 0
    for i in g:
        jd = int(M["row"][i]); end = int(M["end"][i]); s0 = int(M["slot"][i]); pre = tape.vs[jd - 1] / tape.vt[jd - 1]
        nwin = int(np.searchsorted(tape.sl[jd + 1:end], s0 + 1, side="right"))
        for d in range(4):
            if reactive: r = int(RR[i, 2 + d])
            else:
                b = int(np.searchsorted(EDG, nwin, side="right") - 1)
                q = rng.exponential(QM[b]) if QM[b] > 0 else 0.0          # exponential with the bucket mean (shape INFERRED)
                r = min(jd + 1 + int(round(min(mult * q, 1.0) * nwin)), end)
            n += 1
            px = tape.vs[r - 1] / tape.vt[r - 1]
            if not (px <= 0.88 * pre): continue
            es = int(tape.sl[r - 1]) if r - 1 > jd else s0
            qq = tape.qrow(r, end, es, 2); vals.append(tape.joint([(r, qq)])[0]); fills += 1
    v = np.array(vals); return fills / n, v.mean() if len(v) else float("nan"), v
for nm, kw in (("pre-send model x1", dict(mult=1)), ("x2 trades ahead", dict(mult=2)), ("x3 trades ahead", dict(mult=3)), ("reactive rank model (our M2 landing), 2-slot exit", dict(reactive=True))):
    fr, mv, v = run(**kw)
    P(f"- {nm}: fill {100 * fr:.0f}%, per fill {1000 * mv:+.2f} mSOL, win {100 * np.mean(v > 0):.0f}%")
P.save()

#!/usr/bin/env python3
# PRE-SEND V2 step c12: does the replay's SIZE effect (price impact + followers our buy prices out) match what REAL buyers got?
# For every T2 window (base filter) and every >= 12% sudden drop inside it (the crossing our order fills on), take the first
# real buy by another wallet 0-100 ms after the crossing (block clock), size s. Compare:
#   REAL  = that buyer's own mark-to-market 2 slots later (75 ms into slot + 2, sold on the real curve then, pump fees both sides):
#           the tape holds the market's real reaction to that buy;
#   MODEL = the replay's path() for a hypothetical buy of the same size at the same spot, with that real buy REMOVED from the tape
#           (followers whose slippage the hypothetical buy breaks are dropped, exactly as for our fills).
# By size bucket: mean return (% of size).
# RESULT (10-25): MODEL == REAL to the last digit. This is BY CONSTRUCTION: the real followers' token amounts already hold that buy,
# so the same size at the same spot breaks no follower's slippage. The check is therefore only a parity test of path().
# What stays informative: the REAL returns by size bucket (different buyers, confounded by who buys big):
# 0-0.3 SOL +5.8%, 0.3-0.7 +4.6%, 0.7-1.5 +4.25% -> about -1.5 pp from small to ~1 SOL, close to the replay's slope for our fills
# (-1.0 pp from 0.2 to 1.0 SOL at 4/slot). The >= 1.5 SOL bucket (+15.6%) is a different crowd (seller tools / informed).
import sys, os, json, bisect
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V, v2lib as L, v2eng as E
SMS = 212.0; EXI = L.EXN.index("c2_tpnone_slnone")
B = [(0.0, 0.3), (0.3, 0.7), (0.7, 1.5), (1.5, 1e9)]
out = {}
for day in ("R2", "R3", "R4"):
    d = V.load_day(day); D = E.load(day)
    f = lambda k: E.wf(D, k)
    sel = np.flatnonzero((D["w_fam"] == 0) & (f("htype") == 3) & (f("hpct") >= 5) & (f("cslot") == 0) & D["w_in"])
    P = d["vsol"] / d["vtok"]
    rows = []
    for w in sel.tolist():
        t = int(D["w_tok"][w]); o = int(d["off"][t]); n = int(d["cnt"][t])
        A = d["arr"][o:o + n]; st = D["w_start"][w]; en = min(D["w_end"][w], st + 10 * SMS)
        rix = np.searchsorted(A, A - 50.0, side="right") - 1
        REF = np.where(rix >= 0, P[o + np.maximum(rix, 0)], d["ppre"][o]); RAT = P[o:o + n] / REF
        i0 = bisect.bisect_left(A.tolist(), st); iE = bisect.bisect_left(A.tolist(), en)
        cand = np.flatnonzero(RAT[i0:iE] <= 0.88) + i0
        if not len(cand): continue
        x = int(cand[0])
        uid_x = d["uid"][o + x]
        b = None
        for j in range(x + 1, n):
            if A[j] - A[x] > 100.0: break
            if d["buy"][o + j] and d["uid"][o + j] != uid_x: b = j; break
        if b is None: continue
        s_b = d["sol"][o + b] / 1e9
        if s_b < 0.05: continue
        # REAL: the buyer's tokens valued 75 ms into slot S[b] + 2 on the real curve (pump fee on the sell)
        S = d["s"][o:o + n]; Vv = d["vsol"][o:o + n]; Tt = d["vtok"][o:o + n]; fr = d["fr"][o:o + n].astype(float)
        q = d["tokn"][o + b]; s_exit = int(S[b]) + 2; t_exit = s_exit * SMS + 75.0
        k = bisect.bisect_right(A.tolist(), t_exit) - 1
        if k < b: continue
        val = Vv[k] * q / (Tt[k] + q) * (1 - fr[k]) / 1e9
        real = (val - s_b * (1 + fr[b])) / (s_b * (1 + fr[b]))
        # MODEL: same spot, that buy removed, our path() with size s_b
        keep = [j for j in range(n) if j != b]
        Lt = dict(S=[int(S[j]) for j in keep], A=[float(A[j]) for j in keep], B=[bool(d["buy"][o + j]) for j in keep], SOL=[float(d["sol"][o + j]) for j in keep],
                  TK=[float(d["tokn"][o + j]) for j in keep], V=[float(Vv[j]) for j in keep], T=[float(Tt[j]) for j in keep], FR=[float(fr[j]) for j in keep],
                  SK=[float(d["slack"][o + j]) for j in keep])
        r = L.path(Lt, n - 1, b - 1, float(A[b]), s_b * (1 + fr[b]))
        if r is None: continue
        model = r[1][EXI] / (s_b * (1 + fr[b]))
        rows.append((s_b, real, model))
    out[day] = rows
    print(f"{day}: {len(rows)} first buyers after a T2 crossing", flush=True)
allr = [r for v in out.values() for r in v]
print("size bucket (SOL) | n | REAL mean return 2 slots later | MODEL mean | REAL median | MODEL median   (pump fees in, tx costs out)")
res = {}
for lo, hi in B:
    v = [(re, mo) for s, re, mo in allr if lo <= s < hi]
    if not v: continue
    re = np.array([a for a, _ in v]); mo = np.array([b for _, b in v])
    res[f"{lo}-{hi}"] = dict(n=len(v), real=float(re.mean()), model=float(mo.mean()), real_med=float(np.median(re)), model_med=float(np.median(mo)))
    print(f"  {lo:4.1f}-{hi if hi < 1e8 else 'inf':>4} | {len(v):4d} | {100 * re.mean():+6.2f}% | {100 * mo.mean():+6.2f}% | {100 * np.median(re):+6.2f}% | {100 * np.median(mo):+6.2f}%")
json.dump(dict(rows={k: v for k, v in out.items()}, buckets=res), open(f"{V.OUT}/c12_sizecheck.json", "w"))

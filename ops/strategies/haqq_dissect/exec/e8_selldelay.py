#!/usr/bin/env python3
"""What a slower sell would cost us (MEASURED tape + exact constant-product curve): for each of our landed sells, re-price the same token
amount at the curve state D ms later on the chain clock (all outside trades in the mint up to our landing time + D applied), net of the
1.25% pump fee. Also the same for haqq's sells. Out: sniper-data/haqq_dissect/exec/t8_selldelay.txt"""
import sys, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
D = "/home/moiz/sniper-data/haqq_dissect/exec"
T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
sl = np.asarray(T["slot"], np.int64); ix = np.asarray(T["idx"], np.int64); mint = np.asarray(T["mint"]); sg = np.asarray(T["signer"]); us = np.asarray(T["user"])
buy = np.asarray(T["buy"]); tok = np.asarray(T["tok"], np.float64); vs = np.asarray(T["vsol"], np.float64); vt = np.asarray(T["vtok"], np.float64)
ids, idx = L.ids_map()
o = np.lexsort((T["j"], ix, sl, mint)); ms = L.cc(sl, ix)
mo, so, go, uo, bo, to, vso, vto, mso = mint[o], sl[o], sg[o], us[o], buy[o], tok[o], vs[o], vt[o], ms[o]
F = L.FEE
def out_sol(vs_, vt_, k): return vs_ * k / (vt_ + k) * (1 - F)
out = []
def P(*a): out.append(" ".join(str(x) for x in a))
DEL = (10, 20, 30, 50, 100, 212)
for who, wal in (("FRA", L.WAL["FRA"]), ("AMS", L.WAL["AMS"]), ("haqq", L.HAQQ)):
    wid = idx[wal]; mine = (go == wid) | (uo == wid)
    res = collections.defaultdict(list)
    for p in np.nonzero(mine & (bo == 0))[0]:
        q = p - 1
        if q < 0 or mo[q] != mo[p]: continue
        # pre-state = post-state of previous trade; our sell value at that state
        k = to[p]; v0 = out_sol(vso[q], vto[q], k)
        if v0 <= 0: continue
        for dms in DEL:
            # state after all OUTSIDE trades landing within (our time, our time + dms], applied on top of pre-state with their own deltas
            s_vs, s_vt = vso[q], vto[q]; r = p + 1
            dsol = 0.0; dtk = 0.0
            while r < len(mo) and mo[r] == mo[p] and mso[r] <= mso[p] + dms:
                if not mine[r]:
                    # replay the outside trade's reserve change (post - pre)
                    dsol += vso[r] - vso[r - 1]; dtk += vto[r] - vto[r - 1]
                r += 1
            v1 = out_sol(s_vs + dsol, s_vt + dtk, k)
            res[dms].append((v1 - v0) * 1e-9)
    P(f"===== {who}: sells {len(res[DEL[0]])}; mean change in sell proceeds if the sell landed D ms later (mSOL per sell; + = later is better)")
    for dms in DEL:
        x = np.array(res[dms]) * 1e3
        bs = [np.mean(np.random.default_rng(i).choice(x, len(x))) for i in range(300)]
        P(f"  +{dms:3} ms: mean {x.mean():+.3f} mSOL (90% {np.percentile(bs,5):+.3f}..{np.percentile(bs,95):+.3f}), median {np.median(x):+.3f}, share worse {100*np.mean(x<0):.0f}%")
open(f"{D}/t8_selldelay.txt", "w").write("\n".join(out) + "\n")
print("\n".join(out))

#!/usr/bin/env python3
# MODEL CHECK: corrected replay. Same as dd1 path() (mc_lib.replay grid mode) with optional, MEASURED corrections:
#  follow = "model" : every follower buy dropped iff tokens < real tokens / (1 + a8 slack)       (dd1 as is)
#           "tol"   : target-bot buys within the dump slot .. +3 keep with prob S_w(p') / S_w(p)   (m6 curves, price only)
#           "comp"  : as "tol" but S_w conditional on a competing bot being ahead: S_w(p' | ahead) / S_w(p | real ahead)
#  others = "model" : non-target followers keep the a8 slack rule                                  (dd1 as is)
#           "keep"  : non-target followers keep (their measured success does not fall for pushes up to ~10%)
#  phantom: a follower whose buy is dropped no longer sells those tokens later; a kept follower that got fewer tokens sells
#           at most what it holds in the replay (dd1 applies every real sell in full)
#  sell_lat: ms into the exit slot where our sell lands (dd1 75; real bot sells median 93 block-position ms)
#  crowd: fraction of OUR SOL removed from later (> 60 ms) non-target follower buys, spread pro rata over the hold (INFERRED
#         sensitivity from the 2-bots-vs-1 comparison; 0 = off)
# keep draws: deterministic uniform from crc32(row key, follower index) so variants share the same random numbers.
import zlib, json
import numpy as np
import mc_lib as M

class Curves:
    def __init__(self, path):
        C = json.load(open(path)); self.C = {}
        for k, v in C.items():
            if k == "_n": continue
            self.C[k] = (np.array(v[0]), np.array(v[1]))
        self.U = {zlib.crc32(k.split("|")[0].encode()): k.split("|")[0] for k in C if not k.startswith("_")}
    def S(self, w, p, cond=None):
        key = None
        if cond is not None and f"{w}|{cond}" in self.C: key = f"{w}|{cond}"
        elif w in self.C: key = w
        elif cond is not None: key = f"_targets|{cond}"
        else: key = "_targets"
        cx, fy = self.C[key]
        return float(np.interp(p, cx, fy))

def replay_corr(tp, j0, size, L, guard=1.05, follow="model", others="model", phantom=False, sell_lat=75.0, crowd=0.0,
                CV=None, rowkey=0, hmax=M.HMAX, win_slots=3, full=False):
    S, A, Bb, SOL, TK, V_, T_, FR, SK, U = tp.S, tp.A, tp.B, tp.SOL, tp.TK, tp.V, tp.T, tp.FR, tp.SK, tp.U
    n = tp.n
    a0 = A[j0]; fr0 = FR[j0]; p_after = V_[j0] / T_[j0]
    ke = j0 + 1
    while ke < n and A[ke] < a0 + L: ke += 1
    s_land = int((a0 + L) // M.SMS)
    Vb = V_[ke - 1]; Tb = T_[ke - 1]
    ratio = (Vb / Tb) / p_after
    res = dict(status=0, ratio=ratio)
    if Vb >= 100e9: res["status"] = 2; return res
    if ratio > guard: res["status"] = 1; return res
    X = size * 1e9 / (1 + fr0); cost = size
    q = Tb * X / (Vb + X); V = Vb + X; T = Tb - q
    s_in = max(S[ke - 1], s_land); frs = fr0
    # real "a target bot already bought since the dump" state, for the "comp" mode
    tg_real = any(Bb[x] and U[x] in CV.U for x in range(j0 + 1, ke)) if (CV is not None and follow == "comp") else False
    cur = V * q / (T + q) * (1 - frs) / 1e9 - cost
    poff = [None] * (hmax + 2); dn = 0
    ftp = [None] * len(M.TPS); fsl = [None] * len(M.SLS)
    s_cut = s_in + hmax + 1
    deficit = {}; nd = 0; crowd_left = crowd * X
    win_end = S[j0] + win_slots
    # crowd-out: total later non-target follower SOL in the hold (to spread the reduction pro rata)
    if crowd > 0:
        fol = sum(SOL[x] for x in range(ke, n) if S[x] <= s_in + 4 and Bb[x] and A[x] - a0 > 60 and not (CV and U[x] in CV.U))
        cfrac = min(1.0, crowd_left / fol) if fol > 0 else 0.0
    for j in range(ke, n):
        sj = S[j]; pos = A[j] - sj * M.SMS
        kj = 2 * sj + (1 if pos >= sell_lat else 0)
        while dn <= hmax + 1 and 2 * (s_in + dn) + 1 <= kj: poff[dn] = cur; dn += 1
        if sj > s_cut or dn > hmax + 1: break
        applied = True; u = U[j]
        if Bb[j]:
            sol = SOL[j]
            if crowd > 0 and sj <= s_in + 4 and A[j] - a0 > 60 and not (CV and u in CV.U): sol = sol * (1 - cfrac)
            dt = T * sol / (V + sol)
            is_t = CV is not None and u in CV.U
            if follow == "drop" and is_t and sj <= win_end:
                keep = False
            elif follow in ("tol", "comp") and is_t and sj <= win_end:
                w = CV.U[u]
                p_real = (V_[j - 1] / T_[j - 1]) / p_after; p_mod = (V / T) / p_after
                if follow == "tol": kp = CV.S(w, p_mod) / max(CV.S(w, p_real), 1e-6)
                else:
                    tg_before = tg_real or any(Bb[x] and U[x] in CV.U for x in range(ke, j))
                    kp = CV.S(w, p_mod, 1) / max(CV.S(w, p_real, 1 if tg_before else 0), 1e-6)
                kp = min(1.0, kp)
                uu = (zlib.crc32(f"{rowkey}:{j}".encode()) & 0xffffffff) / 2 ** 32
                keep = uu < kp
            elif (not is_t) and others == "keep":
                keep = True
            else:
                keep = not (dt < TK[j] / (1.0 + SK[j]))
            if not keep:
                applied = False; nd += 1
                if phantom: deficit[u] = deficit.get(u, 0.0) + TK[j]
            else:
                V += sol; T -= dt
                if phantom and dt < TK[j]: deficit[u] = deficit.get(u, 0.0) + (TK[j] - dt)
        else:
            tk = TK[j]
            if phantom and deficit.get(u, 0.0) > 0:
                cut = min(tk, deficit[u]); deficit[u] -= cut; tk -= cut
            if tk > 0:
                so = V * tk / (T + tk); V -= so; T += tk
            else: applied = False
        if applied: frs = FR[j]
        cur = V * q / (T + q) * (1 - frs) / 1e9 - cost
        if V >= M.GRADV: break
        if applied:
            val = (cur + cost) / cost
            for a in range(1, len(M.TPS)):
                if ftp[a] is None and val >= 1 + M.TPS[a]: ftp[a] = sj
            for b in range(1, len(M.SLS)):
                if fsl[b] is None and val <= 1 - M.SLS[b]: fsl[b] = sj
    while dn <= hmax + 1: poff[dn] = cur; dn += 1
    pn = {}; of = {}
    for e in (range(len(M.EXITS)) if full else (M.E4, M.E6)):
        c, tp_, sl_ = M.EXITS[e]
        co = s_in + c; a = ftp[M.TPS.index(tp_)] if tp_ is not None else None; b = fsl[M.SLS.index(sl_)] if sl_ is not None else None
        if a is not None and a + 1 >= co: a = None
        if b is not None and b + 1 >= co: b = None
        if a is None and b is None: so_ = co
        elif b is None: so_ = a + 1
        elif a is None: so_ = b + 1
        else: so_ = min(a, b) + 1
        dd = so_ - s_in; pn[e] = poff[dd]; of[e] = dd
    res.update(s_in=s_in, pnl=pn, off=of, ndrop=nd)
    return res

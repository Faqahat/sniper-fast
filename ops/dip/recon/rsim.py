#!/usr/bin/env python3
# Replay engine for the reconciliation (ops/dip/recon). Same mechanics as dipdetect/dd1_build.path() (block-position clock,
# trades ahead of us, +5% guard vs the post-dump price, follower slack model, sells applied as tokens in, pump fee both sides),
# plus what the reconciliation needs:
#   - our own wallets' trades can be removed from the tape (the recording contains our real buys/sells),
#   - entry at a latency L (block-position ms) OR at an exact chain position (slot, idx) = where our real tx landed,
#   - the whole value path is kept, so any exit can be valued: time limit (slot offset + position inside the slot),
#     stop-loss with a lag, or the exact (slot, idx) where our real sell landed.
import os, sys, json, zlib
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R

SMS = 212.0; GRADV = 110e9; HMAX = 40


def pos_idx(ms):
    """position inside a slot (block-position ms) -> first tx index at/after it (400-tx block)"""
    return int(np.ceil(ms / SMS * 400.0))


class Tapes:
    def __init__(self, tag):
        d = f"{R.WORK}/{tag}"
        z = np.load(f"{d}/day_{tag}.npz")
        self.tag = tag
        self.c = {k: z[k] for k in ("tok", "s", "i", "arr", "buy", "sol", "tokn", "vsol", "vtok", "fr", "slack", "uid")}
        self.meta = json.load(open(f"{d}/day_{tag}_meta.json"))["meta"]
        nt = len(self.meta); cnt = np.bincount(self.c["tok"], minlength=nt)
        self.off = np.concatenate([[0], np.cumsum(cnt)[:-1]]).astype(np.int64); self.cnt = cnt
        self.mint2t = {m["m"]: t for t, m in enumerate(self.meta)}
        self.ours = np.isin(self.c["uid"], np.array(sorted(R.WAL_UID), np.int64))
        self._cache = {}

    def token(self, t):
        tp = self._cache.get(t)
        if tp is None:
            o = int(self.off[t]); n = int(self.cnt[t]); sl = slice(o, o + n)
            tp = {k: v[sl] for k, v in self.c.items()}; tp["ours"] = self.ours[sl]; tp["n"] = n; tp["o"] = o
            tp["SI"] = tp["s"].astype(np.int64) * 100000 + tp["i"].astype(np.int64)
            self._cache[t] = tp
            if len(self._cache) > 4000: self._cache.clear()
        return tp

    def find(self, mint, slot, idx, sell_sol=None):
        """tape row of a trade (the dump) by mint + slot + tx index (closest sell size if several events)"""
        t = self.mint2t.get(mint)
        if t is None: return None, None
        tp = self.token(t)
        m = np.flatnonzero((tp["s"] == slot) & (tp["i"] == idx) & (tp["buy"] == 0))
        if len(m) == 0: return t, None
        if len(m) > 1 and sell_sol is not None:
            m = m[np.argsort(np.abs(tp["sol"][m] / 1e9 - sell_sol))]
        return t, int(m[0])


def run_path(tp, j0, size, L=None, at=None, guard=1.05, drop_ours=True, slack=True, hmax=HMAX, keep_ours_after=False):
    """our buy after the dump at tape row j0, either L block-position ms later (L) or exactly at chain position at=(slot, idx).
    Returns dict: st (0 fill, 1 guard fail, 2 untradeable), ratio, ahead (trades / buys), s_in, q (tokens), X (SOL in curve),
    v0 (value right after our buy), traj: list of (key=slot*100000+idx, value_after) for every applied trade after us,
    dropped (followers removed by the slack model), fr (fee of the last applied trade per traj point)."""
    S = tp["s"]; I = tp["i"]; A = tp["arr"]; B = tp["buy"]; SOL = tp["sol"]; TK = tp["tokn"]; V_ = tp["vsol"]; T_ = tp["vtok"]
    FR = tp["fr"]; SK = tp["slack"]; OU = tp["ours"] if drop_ours else np.zeros(tp["n"], bool); n = tp["n"]; SI = tp["SI"]
    a0 = A[j0]; fr0 = float(FR[j0]); p_after = V_[j0] / T_[j0]
    V = float(V_[j0]); T = float(T_[j0]); removed = False
    j = j0 + 1; ahead = 0; ab = 0
    lim = None if at is None else at[0] * 100000 + at[1]
    while j < n:
        if OU[j]:
            removed = True; j += 1; continue
        if lim is None:
            if A[j] >= a0 + L: break
        elif SI[j] >= lim: break
        if not removed:
            V = float(V_[j]); T = float(T_[j])
        else:
            if B[j]:
                dt = T * SOL[j] / (V + SOL[j]); V += SOL[j]; T -= dt
            else:
                so = V * TK[j] / (T + TK[j]); V -= so; T += TK[j]
        ahead += 1; ab += int(B[j]); j += 1
    ke = j
    ratio = (V / T) / p_after
    res = dict(ratio=ratio, ahead=ahead, ahead_buys=ab, ke=ke)
    if V >= 100e9: res["st"] = 2; return res
    if ratio > guard: res["st"] = 1; return res
    X = size * 1e9 / (1 + fr0); q = T * X / (V + X); V += X; T -= q
    s_land = (int((a0 + L) // SMS) if lim is None else at[0])
    s_in = max(int(S[ke - 1]), s_land) if lim is None else at[0]
    frs = fr0
    v_entry = V * q / (T + q) * (1 - frs) / 1e9
    V_entry = V; T_entry = T
    traj = []; dropped = 0; s_cut = s_in + hmax + 1
    for j in range(ke, n):
        if OU[j] and not keep_ours_after: continue
        sj = int(S[j])
        if sj > s_cut: break
        if B[j]:
            sol = SOL[j]; dt = T * sol / (V + sol)
            if slack and dt < TK[j] / (1.0 + SK[j]):
                dropped += 1; continue
            V += sol; T -= dt
        else:
            tk = TK[j]; so = V * tk / (T + tk); V -= so; T += tk
        frs = float(FR[j])
        cur = V * q / (T + q) * (1 - frs) / 1e9
        traj.append((int(SI[j]), cur, V, T, frs, int(B[j]), int(OU[j])))
        if V >= GRADV: break
    res.update(st=0, s_in=s_in, q=q, X=X, v_entry=v_entry, V_entry=V_entry, T_entry=T_entry, size=size, traj=traj, dropped=dropped, fr0=fr0)
    return res


def value_at(res, key, v_entry=None):
    """position value (SOL, after the sell fee) just before chain position key=slot*100000+idx"""
    v = res["v_entry"] if v_entry is None else v_entry
    for p in res["traj"]:
        if p[0] >= key: break
        v = p[1]
    return v


def value_at_q(res, key, q):
    """value of q tokens (instead of the model's own) just before chain position key, on the same replayed curve"""
    V, T, fr = res["V_entry"], res["T_entry"], res["fr0"]
    for p in res["traj"]:
        if p[0] >= key: break
        V, T, fr = p[2], p[3], p[4]
    # the curve state includes the model's own buy of res["q"] tokens; swap it for q (same SOL-side approximation)
    return V * q / (T + q) * (1 - fr) / 1e9


def exits(res, cap, sell_idx=142, sl=None, sl_lag_slots=1, tp_=None):
    """dd1-style exit on the value path: time limit = sell at slot s_in + cap, tx index sell_idx (142 = 75 ms into the slot);
    stop-loss / take-profit trigger on the value after an applied trade in slot S -> sell at slot S + lag, index sell_idx
    (if that is not before the time-limit sell). Returns (value, sell slot offset, why)."""
    s_in = res["s_in"]; size = res["size"]
    co = s_in + cap
    trig = None; why = "time"
    if sl is not None or tp_ is not None:
        for p in res["traj"]:
            k, val = p[0], p[1]
            sj = k // 100000
            if sj + sl_lag_slots >= co: break
            r = val / size
            if sl is not None and r <= 1 - sl: trig = sj; why = "sl"; break
            if tp_ is not None and r >= 1 + tp_: trig = sj; why = "tp"; break
    so = (trig + sl_lag_slots) if trig is not None else co
    key = so * 100000 + sell_idx
    return value_at(res, key, res["v_entry"]), so - s_in, why


def key2arr(key):
    s = key // 100000; i = key % 100000
    return s * SMS + i / max(400, i + 1) * SMS


def arr2key(a):
    s = int(a // SMS); pos = a - s * SMS
    i = int(np.ceil(pos / SMS * 400.0))
    return s * 100000 + min(i, 399)


def exits_live(res, hold, sl=None, tl_idx=148, sl_lat_ms=42.0):
    """CORRECTED exit = what the engine really does (MEASURED on 129 live fills, r12/r07):
    time limit: our sell lands in slot s_in + hold - 1 (96 of 107), median index 148 in that slot;
    stop-loss: the sell lands ~42 block-position ms after the trade that crossed the stop (median of 20), not the next slot."""
    s_in = res["s_in"]; size = res["size"]
    k_tl = (s_in + hold - 1) * 100000 + tl_idx
    k_sell = k_tl; why = "time"
    if sl is not None:
        for p in res["traj"]:
            if p[0] >= k_tl: break
            if p[1] / size <= 1 - sl:
                k = arr2key(key2arr(p[0]) + sl_lat_ms)
                if k < k_tl: k_sell = k; why = "sl"
                break
    return value_at(res, k_sell), k_sell, why

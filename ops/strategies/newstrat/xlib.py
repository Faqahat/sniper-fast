"""NEWSTRAT exit/entry machinery on one Mint (nlib.Mint). All times chain-clock ms. Read-only."""
import numpy as np
import nlib as L

SL = L.SMS

def value_series(M, e, x, tok):
    """liquidation value (lamports, after fee) of our tok after each row e..x-1, our tokens out of the curve"""
    c = M.CQ[e:x] if M.adj is None else M.CQ[e:x] + M.adj[e:x]
    return L.sell_sol(np.maximum(c - tok, 206.9e12 - 1e12), tok)

def entry(M, t_in, size=L.SIZE):
    e = int(M.idx(t_in)); cb = float(M.cbal(e)); tok = L.buy_tok(cb, size)
    return e, tok

def ex_fix(M, t_in, H_slots): return t_in + H_slots * SL

def ex_next(evt_cc, t_in, d, cap_ms):
    j = np.searchsorted(evt_cc, t_in, side="right")
    if j < len(evt_cc) and evt_cc[j] <= t_in + cap_ms: return evt_cc[j] + d, 1
    return t_in + cap_ms, 0

def ex_trail(M, t_in, e, tok, dd, d, cap_ms, size=L.SIZE):
    x = int(M.idx(t_in + cap_ms))
    if x <= e: return t_in + cap_ms, 0
    v = value_series(M, e, x, tok)
    pk = np.maximum.accumulate(np.maximum(v, size * (1 - 2 * L.FEE)))
    h = np.nonzero(v <= pk * (1 - dd))[0]
    if len(h): return M.CC[e + h[0]] + d, 1
    return t_in + cap_ms, 0

def ex_tp(M, t_in, e, tok, tp, d, cap_ms, size=L.SIZE, sl=None):
    """reactive take-profit with min-out (fails and keeps holding if the price fell back below target by landing);
    optional stop-loss sl (market, reactive). cost tag 1 = tp, 2 = sl, 0 = cap"""
    x = int(M.idx(t_in + cap_ms))
    if x <= e: return t_in + cap_ms, 0
    v = value_series(M, e, x, tok)
    tgt = size * (1 + tp)
    cand = np.nonzero(v >= tgt)[0]
    sh = np.nonzero(v <= size * (1 - sl))[0] if sl else np.array([], int)
    s_first = M.CC[e + sh[0]] + d if len(sh) else np.inf
    for k in cand[:50]:
        tl = M.CC[e + k] + d
        if tl >= s_first: break
        y = int(M.idx(tl))
        c = M.cbal(y)
        if L.sell_sol(max(float(c) - tok, 206.9e12 - 1e12), tok) >= tgt: return tl, 1
    if s_first < np.inf: return s_first, 2
    return t_in + cap_ms, 0

def ex_attn(evt_cc, t_in, N_slots, cap_ms):
    """timer: sell when the watched wallet has made no trade on the mint for N slots (counted from max(t_in, its last trade))"""
    gap = N_slots * SL
    j = np.searchsorted(evt_cc, t_in, side="right")
    last = evt_cc[j - 1] if j > 0 else t_in
    last = max(last, t_in)
    while j < len(evt_cc) and evt_cc[j] - last <= gap and evt_cc[j] <= t_in + cap_ms:
        last = evt_cc[j]; j += 1
    return min(last + gap, t_in + cap_ms)

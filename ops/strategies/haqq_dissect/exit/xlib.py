"""EXIT analyst shared helpers (read-only). Tape cut = /home/moiz/sniper-data/haqq_dissect/exit/tape.npy (x1_tape.py)."""
import pickle, sys, time, functools
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/exit"
SMS = 212.0
DAY0 = L.DAY0
pkt = L.pkt
FEE = 0.0125


def day_of(bt): return int((bt - DAY0) // 86400)


@functools.lru_cache(None)
def tape():
    R = np.load(f"{OUT}/tape.npy")
    M = pickle.load(open(f"{OUT}/mints.pkl", "rb"))
    um, st = np.unique(R["mint"], return_index=True); en = np.append(st[1:], len(R))
    span = {int(m): (int(a), int(b)) for m, a, b in zip(um, st, en)}
    cc = L.cc(R["slot"], R["idx"])
    return R, M, span, cc


class Mint:
    """arrays of one mint, chain order; px = price AFTER the trade, pxp = price BEFORE it"""
    def __init__(self, m):
        R, M, span, CC = tape()
        a, b = span[m]; self.a = a; X = R[a:b]
        self.m = m; self.n = b - a
        self.sl = X["slot"].astype(np.int64); self.ix = X["idx"].astype(np.int64); self.us = X["user"].astype(np.int64)
        self.bu = X["buy"].astype(bool); self.so = X["sol"].astype(np.float64) / 1e9; self.tk = X["tok"].astype(np.float64)
        self.vs = X["vsol"].astype(np.float64) / 1e9; self.vt = X["vtok"].astype(np.float64); self.bt = X["bt"].astype(np.int64)
        self.fee = (X["fee_bps"].astype(np.float64) + X["cfee_bps"].astype(np.float64)) / 1e4
        self.cc = CC[a:b]
        info = M["info"][m]
        v_c = (info.get("vsol") or 30e9) / 1e9; t_c = float(info.get("vtok") or 1.073e15)
        self.px = self.vs / np.maximum(self.vt, 1)
        self.pxp = np.empty(self.n); self.pxp[0] = v_c / t_c; self.pxp[1:] = self.px[:-1]
        self.vsp = np.empty(self.n); self.vsp[0] = v_c; self.vsp[1:] = self.vs[:-1]
        self.vtp = np.empty(self.n); self.vtp[0] = t_c; self.vtp[1:] = self.vt[:-1]
        self.cs = info.get("cs"); self.creator = info.get("creator")


def sell_value(v, t, tok, fee=FEE):
    """SOL out (net of pump fee) for selling tok tokens into a curve with reserves (v SOL, t tokens)"""
    K = v * t
    return (v - K / (t + tok)) * (1 - fee)


def boot_sum(v, n=2000, seed=1):
    v = np.asarray(v, float)
    if not len(v): return (0.0, 0.0)
    g = np.random.default_rng(seed); s = np.array([v[g.integers(0, len(v), len(v))].sum() for _ in range(n)])
    return float(np.percentile(s, 5)), float(np.percentile(s, 95))


def boot_mean(v, n=2000, seed=1):
    v = np.asarray(v, float)
    if not len(v): return (0.0, 0.0)
    g = np.random.default_rng(seed); s = np.array([v[g.integers(0, len(v), len(v))].mean() for _ in range(n)])
    return float(np.percentile(s, 5)), float(np.percentile(s, 95))

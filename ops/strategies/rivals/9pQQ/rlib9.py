"""9pQQ paper-replay core (read-only).  Chain clock = slot*212 ms + idx/blocksize*212 ms, blocksize = max landed pump-tx index seen
in the slot + 1 (from the step-0 tape, curve + AMM rows).  Curve maths: vtok = cbal + 73e12, vsol = 30e9*1073e12/vtok (lamports).
Our simulated trade: buy SIZE SOL (fee FEE on the way in), tokens out of the curve; our tokens are taken out of the curve for every
later price; sell all at the exit state (fee FEE), minus COST lamports per round trip.  Options: drop 9pQQ's own trades (when we
REPLACE it), and 'fol' = share of outside token buys between our entry and exit that we remove (fewer followers row)."""
import os, glob
import numpy as np
import tlib9 as L

SMS = 212.0
K = 30e9 * 1073e12
VT = 73e12
FEE = 0.0125
COST = 4.5e6

def blocksizes(run):
    pk = f"{L.OUT}/bsz_{run}.npz"
    if os.path.exists(pk):
        z = np.load(pk); return int(z["s0"]), z["b"]
    s0, s1 = None, None; parts = []
    for fn in sorted(glob.glob(f"{L.TAPE}/{run}/*.npz")):
        a = np.load(fn)["a"]
        if len(a): parts.append(a[:, :2].copy())
    a = np.concatenate(parts); s0 = int(a[:, 0].min()); b = np.zeros(int(a[:, 0].max()) - s0 + 1, np.int32)
    np.maximum.at(b, a[:, 0] - s0, a[:, 1].astype(np.int32) + 1)
    b[b == 0] = 400
    np.savez(pk, s0=s0, b=b)
    return s0, b

class Mint:
    """one token's tape slice with chain clock and 9pQQ-removed curve balances"""
    def __init__(self, t, mi, s0, bsz, wid):
        a0, a1 = t.mstart[mi], t.mstart[mi + 1]
        self.S = t.s[a0:a1]; self.I = t.i[a0:a1]; self.U = t.u[a0:a1]; self.TK = t.tok[a0:a1].astype(np.float64)
        self.SL = t.sol[a0:a1]; self.CP = t.cpre[a0:a1].astype(np.float64); self.CQ = t.cpost[a0:a1].astype(np.float64)
        b = bsz[np.clip(self.S - s0, 0, len(bsz) - 1)].astype(np.float64)
        self.CC = self.S * SMS + self.I / np.maximum(b, self.I + 1.0) * SMS
        is9 = self.U == wid
        self.h9 = np.cumsum(np.where(is9, self.TK, 0.0))          # 9pQQ's net tokens after each row
        self.is9 = is9
        self.obuy = np.cumsum(np.where(~is9 & (self.TK > 0), self.TK, 0.0))   # outside token buys (cumulative)
    def state_before(self, tcc, drop9):
        """index of the first trade landing after time tcc, and the curve balance we would trade against"""
        e = int(np.searchsorted(self.CC, tcc, side="right"))
        if e == 0: c = self.CP[0]; h = 0.0
        else: c = self.CQ[e - 1]; h = self.h9[e - 1]
        return e, (c + h if drop9 else c)

def buy(cbal, spend):
    vt = cbal + VT; vs = K / vt
    x = spend / (1 + FEE)
    return vt - K / (vs + x)

def sell(cbal, tok):
    vt = cbal + VT; vs = K / vt
    return (vs - K / (vt + tok)) * (1 - FEE)

def trip(M, t_in, t_out, size=0.55e9, drop9=False, fol=0.0, cost=COST, fol_slots=3):
    """paper round trip: buy at chain time t_in, sell at t_out.  Returns net lamports.
    fol: share of OUTSIDE token buys in the first fol_slots slots after our entry that we remove (they would not have come)."""
    e, cb = M.state_before(t_in, drop9)
    tok = buy(cb, size)
    x, cx = M.state_before(t_out, drop9)
    cx = cx - tok                                             # our tokens are out of the curve
    if fol and x > e:
        se = M.S[e] if e < len(M.S) else M.S[-1]
        xf = min(x, int(np.searchsorted(M.S, se + fol_slots, side="right")))
        ob = (M.obuy[xf - 1] - (M.obuy[e - 1] if e > 0 else 0.0)) if xf > e else 0.0
        cx = cx + fol * ob                                    # fewer follower buys -> more tokens left in the curve
    cx = max(cx, 206.9e12 - 1e12)
    return sell(cx, tok) - size - cost

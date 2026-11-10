"""LANES paper replay. Chain clock = slot*212 ms + idx/blocksize*212 ms (blocksize = max landed curve-trade index in the slot + 1).
Curve: vtok = cbal + 73e12, vsol = K/vtok. 9pQQ removed (its held tokens added back to the curve). Our trade: spend 0.7 SOL incl. 1.25 %
pump fee in, sell all with 1.25 % fee out, tx cost 1.46 mSOL per round trip (its recipe) -> ~18-19 mSOL round-trip cost at 0.7 SOL.
'fol' removes that share of outside token BUYS in the first 3 slots after our entry (fewer followers row)."""
import numpy as np, sys
sys.path.insert(0, "/home/it/sniper/ops/strategies/rivals/9pQQ/lanes/code")
import llib
K, V = llib.K, llib.V; FEE = 0.0125; COST = 1.46e6; SIZE = 0.7e9; SMS = 212.0
class Tape:
    def __init__(self, run):
        t = llib.load(run); self.t = t
        s0 = int(t.s.min()); b = np.zeros(int(t.s.max()) - s0 + 1, np.int32); np.maximum.at(b, t.s - s0, t.i.astype(np.int32) + 1)
        b[b == 0] = 400; self.s0 = s0; self.bsz = b
        own = np.where(t.u == t.wid, t.tok.astype(float), 0.0); cum = np.cumsum(own); st = t.ms[t.m]
        base = np.where(st > 0, cum[np.maximum(st - 1, 0)], 0.0); self.held = cum - base     # 9pQQ tokens held after each row (per mint)
        self.c9 = t.cpost.astype(float) + self.held                                         # curve balance with 9pQQ removed
        self.cc = t.s * SMS + t.i / np.maximum(self.bsz[t.s - s0], t.i + 1.0) * SMS
        self.isbuy_out = (t.u != t.wid) & (t.tok > 0); self.tokbuy = np.where(self.isbuy_out, t.tok.astype(float), 0.0)
        self.cumbuy = np.cumsum(self.tokbuy)
    def state_at(self, m, tcc):
        """last row of mint m landing at or before chain time tcc -> (row, curve balance 9pQQ-removed)"""
        a, b = self.t.ms[m], self.t.ms[m + 1]
        e = a + int(np.searchsorted(self.cc[a:b], tcc, side="right")) - 1
        return e, (self.c9[e] if e >= a else float(llib.TOTAL))
    def trip(self, m, t_in, t_out, fol=0.0, size=SIZE, cost=COST):
        e, cb = self.state_at(m, t_in); vt = cb + V; vs = K / vt; x = size / (1 + FEE); tok = vt - K / (vs + x)
        f, cx = self.state_at(m, t_out); cx -= tok
        if fol and f > e:   # remove `fol` share of outside token buys in the first 3 slots after our entry (rlib9 definition)
            a, b = self.t.ms[m], self.t.ms[m + 1]
            se = self.t.s[min(e + 1, b - 1)]
            xf = min(f, a + int(np.searchsorted(self.t.s[a:b], se + 3, side="right")) - 1)
            if xf > e: cx += fol * (self.cumbuy[xf] - self.cumbuy[e])
        vt = cx + V; vs = K / vt; got = (vs - K / (vt + tok)) * (1 - FEE)
        return got - size - cost

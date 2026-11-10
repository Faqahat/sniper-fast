#!/usr/bin/env python3
"""NEWSTRAT idea LAUNCH-AGE: 9pQQ never buys before age 8 slots and its LAUNCH lane (age 10-50) is +85 SOL / 4 days.
We know the mint at create, so we can PRE-SIGN a buy that lands at a fixed age A (no race: nobody needs to be beaten).
Entry: chain time = start of slot create+A + D (D = 0/50/70/90 ms into the slot, sweeping how deep in the block we land).
Signing-time features (from rows landed before slot create+A-1, i.e. known one slot before our tx lands):
  vs8 (vSOL), nb8 (# distinct buyers), cs (SOL bought in the create slot by non-creators), dev (creator's buy SOL),
  nf8 (net SOL flow), sold8 (SOL sold so far), top (largest single non-creator holder's SOL)
Exits: fixed 5/25/150 slots, trailing 15 % (cap 600 s), its own 'drought' rule (sell when no outside buy for 10 slots, cap 600 s).
-> OUT/la_<run>.npz (one row per launch x A)"""
import sys
import numpy as np
import nlib as L
import xlib as X

AS = [8, 10, 20, 50]
DS = [0, 50, 70, 90]

def drought(M, t_in, e, n_slots, d, cap):
    x = int(M.idx(t_in + cap))
    if x <= e: return t_in + cap
    b = np.nonzero(M.TK[e:x] > 0)[0]
    cc = np.r_[t_in, M.CC[e:x][b], t_in + cap]
    g = np.nonzero(np.diff(cc) > n_slots * L.SMS)[0]
    if len(g): return cc[g[0]] + n_slots * L.SMS + d
    return t_in + cap

def main(run):
    t = L.load(run)
    la = L.launches(run)
    t0 = float(t.cc.min()) + 600e3
    rows = []
    for mint, lv in la.items():
        if lv["may"]: continue
        mi = t.mix.get(mint)
        if mi is None: continue
        M = L.Mint(t, mi)
        s0 = lv["slot"]
        if s0 * L.SMS < t0: continue
        cr = t.uix.get(lv["creator"], -1)
        for A in AS:
            known = M.S < s0 + A - 1
            kk = np.nonzero(known)[0]
            if len(kk) == 0: continue
            last = kk[-1]
            vs8 = L.vsol(M.CQ[last]) / 1e9
            spend = -M.SL[kk].astype(np.float64) / 1e9
            isb = M.TK[kk] > 0
            nb8 = len(np.unique(M.U[kk][isb]))
            cs = spend[isb & (M.S[kk] == s0) & (M.U[kk] != cr)].sum()
            dev = spend[isb & (M.U[kk] == cr)].sum()
            nf8 = spend.sum(); sold8 = -spend[~isb].sum()
            # largest non-creator holder (tokens) -> SOL at current price
            hold = {}
            for u, tk in zip(M.U[kk], M.TK[kk]):
                if u != cr: hold[u] = hold.get(u, 0.0) + tk
            top = max(hold.values()) * L.price(M.CQ[last]) / 1e9 if hold else 0.0
            r = [mi, A, vs8, nb8, cs, dev, nf8, sold8, top]
            for D in DS:
                t_in = (s0 + A) * L.SMS + D
                e, tok = X.entry(M, t_in)
                outs = [t_in + 5 * L.SMS, t_in + 25 * L.SMS, t_in + 150 * L.SMS,
                        X.ex_trail(M, t_in, e, tok, 0.15, D, 600e3)[0], drought(M, t_in, e, 10, D, 600e3)]
                v = L.trip(M, np.full(len(outs), t_in), np.array(outs))
                r += list(v)
                if D == 70:
                    r += list(L.trip(M, np.full(len(outs), t_in), np.array(outs), fol=L.FOLSHARE))
            rows.append(r)
    a = np.array(rows, np.float64)
    np.savez(f"{L.OUT}/la_{run}.npz", a=a, hours=np.array([L.hours(t) - 600 / 3600]))
    print(run, "launch rows", len(a), flush=True)

if __name__ == "__main__":
    for r in sys.argv[1:]: main(r)

#!/usr/bin/env python3
"""NEWSTRAT LEADER-LADDER pre-send (owner follow-up 11-03).
A wallet 'ladders' when its FIRST buy on a mint (no own buy there in the previous 50 slots) is followed by its own SECOND buy within
10 slots.  Pre-send form: when we see such a wallet's first buy we arm a pre-signed buy stream (max price = its post-buy price x 1.05);
the first try lands D ms after its buy (D 50/70/90; arming after a visible trigger lands like a reactive send, so D is the same
distribution as our reactive landing).  We want to be in before its second buy and the copiers that follow it.
Per run -> OUT/n10_<run>.npz: one row per first-buy event of every wallet with >= 10 first buys in the run:
  u, m, cc, ladder (1 if 2nd buy within 10 slots), gap2 (ms to 2nd buy or -1), and P&L for D x exits
  exits: S6 (6 slots), S25 (25 slots), H200 (200 ms), NB2 (sell 70 ms after its 2nd buy, else 25 slots), guard 5 %.
usage: n10_ladder.py RUN [RUN...]"""
import sys
import numpy as np
import nlib as L

DS = [50, 70, 90]
EX = ["S6", "S25", "H200", "NB2"]

def main(run):
    t = L.load(run); la = L.launches(run)
    t0 = float(t.cc.min()) + 2 * 3600e3
    okm = np.zeros(len(t.mints), bool)
    for m, v in la.items():
        mi = t.mix.get(m)
        if mi is not None and not v["may"]: okm[mi] = True
    b = np.nonzero((t.tok > 0) & (-t.sol >= 0.05e9) & okm[t.m])[0]
    o = np.lexsort((t.cc[b], t.m[b], t.u[b])); b = b[o]
    u, m, cc, s = t.u[b], t.m[b], t.cc[b], t.s[b]
    same_prev = np.r_[False, (u[1:] == u[:-1]) & (m[1:] == m[:-1])]
    same_next = np.r_[same_prev[1:], False]
    gprev = np.r_[np.inf, s[1:] - s[:-1]]; gprev[~same_prev] = np.inf
    gnext_ms = np.r_[cc[1:] - cc[:-1], np.inf]; gnext_ms[~same_next] = np.inf
    gnext_sl = np.r_[s[1:] - s[:-1], np.inf]; gnext_sl[~same_next] = np.inf
    first = (gprev > 50) & (cc >= t0)
    fu = u[first]
    cnt = np.bincount(fu, minlength=len(t.users))
    keep = first & (cnt[u] >= 10)
    idx = np.nonzero(keep)[0]
    lad = (gnext_sl[idx] <= 10).astype(np.int8)
    g2 = np.where(lad == 1, gnext_ms[idx], -1.0)
    rows = b[idx]
    res = {f"d{D}{e}": np.zeros(len(idx), np.float32) for D in DS for e in EX}
    res["f20_d70S25"] = np.zeros(len(idx), np.float32); res["skip5_d70"] = np.zeros(len(idx), np.int8)
    order = np.argsort(t.m[rows], kind="stable")
    mm = t.m[rows][order]
    starts = np.r_[0, np.nonzero(np.diff(mm))[0] + 1, len(mm)]
    for a0, a1 in zip(starts[:-1], starts[1:]):
        ev = order[a0:a1]; mi = int(mm[a0])
        M = L.Mint(t, mi)
        tc = t.cc[rows[ev]]; p_post = L.price(t.cpost[rows[ev]].astype(np.float64))
        nb = np.where(lad[ev] == 1, tc + g2[ev], np.inf)
        for D in DS:
            tin = tc + D
            e = M.idx(tin); p_in = L.price(M.cbal(e))
            skip = p_in > p_post * 1.05
            outs = {"S6": tin + 6 * L.SMS, "S25": tin + 25 * L.SMS, "H200": tin + 200,
                    "NB2": np.where(np.isfinite(nb) & (nb + 70 > tin), nb + 70, tin + 25 * L.SMS)}
            for ex, to in outs.items():
                v = L.trip(M, tin, to)
                res[f"d{D}{ex}"][ev] = np.where(skip, -5120.0, v)
            if D == 70:
                res["skip5_d70"][ev] = skip
                res["f20_d70S25"][ev] = np.where(skip, -5120.0, L.trip(M, tin, outs["S25"], fol=L.FOLSHARE))
    np.savez(f"{L.OUT}/n10_{run}.npz", u=t.users[u[idx]], m=m[idx], cc=cc[idx], lad=lad, g2=g2, hours=np.array([L.hours(t) - 2]), **res)
    print(run, "first-buy events", len(idx), "ladder share", round(float(lad.mean()), 3), flush=True)

if __name__ == "__main__":
    for r in sys.argv[1:]: main(r)

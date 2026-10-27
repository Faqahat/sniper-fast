#!/usr/bin/env python3
"""HAQQ_SIZE step 4 (read-only): did haqq's sizing pay for HIM? Closed lots (FIFO, a1_buys.py), P&L gross of tx fees/tips.
  * per-SOL return by regime (curve <= 30.52 'dead curve' vs normal) and tier, all days and the held-out day;
  * his actual P&L vs the same lots at one flat size with the same total SOL (return x mean size; first-order, ignores the
    price impact of a different size): positive = his size choice added P&L.
Ranges = 5-95% bootstrap over lots."""
import pickle, json, collections
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_size"
W0 = 1793038500
Z = pickle.load(open(f"{OUT}/buys.pkl", "rb")); B = Z["buys"]; LOTS = Z["lots"]
rng = np.random.default_rng(4)
TXC = 0.0                         # tx fee per lot not on tape; sensitivity below with 0.001 SOL per buy+sell


def boot(f, n, nb=2000):
    v = [f(rng.integers(0, n, n)) for _ in range(nb)]
    return float(np.percentile(v, 5)), float(np.percentile(v, 95))


if __name__ == "__main__":
    rows = []
    for b in B:
        L = LOTS[b["lot_ix"]]
        if L["close_bt"] is None: continue
        rows.append((b["size"], L["out"] - L["cost"], b["vsol_pre"], b["bt"], b["add"], (L["close_bt"] - b["bt"])))
    A = np.array(rows); sz, pn, vs, bt, add, hold = A.T
    R = {}
    for per, m0 in (("all days", np.ones(len(A), bool)), ("held-out day", (bt >= W0) & (bt < W0 + 86400))):
        print(f"\n== {per} ==")
        nz = m0 & (sz > 0.05)
        for reg, m in (("dead curve (<=30.52)", nz & (vs <= 30.52)), ("normal (>31.06)", nz & (vs > 31.06)), ("all non-probe", nz)):
            n = m.sum(); s = sz[m]; p = pn[m]
            lo, hi = boot(lambda ix: p[ix].sum() / s[ix].sum(), n)
            print(f"  {reg:22s} lots {n:5d} SOL in {s.sum():7.0f} P&L {p.sum():+7.2f} per SOL {p.sum() / s.sum():+.4f} [{lo:+.4f},{hi:+.4f}] "
                  f"win {100 * (p > 0).mean():.0f}% mean size {s.mean():.3f} median hold {np.median(hold[m]):.0f}s")
            R[f"{per}|{reg}"] = dict(n=int(n), sol=float(s.sum()), pnl=float(p.sum()), per_sol=float(p.sum() / s.sum()), lo=lo, hi=hi, win=float((p > 0).mean()))
            if reg.startswith("all") or reg.startswith("normal"):
                tt = np.round(s, 2)
                for k in sorted(set(tt)):
                    mk = tt == k
                    if mk.sum() < 30: continue
                    print(f"      tier {k:.2f}: lots {mk.sum():5d} per SOL {p[mk].sum() / s[mk].sum():+.4f} win {100 * (p[mk] > 0).mean():.0f}%")
            # sizing value: actual vs flat at the same total SOL
            r = p / s; flat = s.mean()
            val = p.sum() - (r * flat).sum()
            lo, hi = boot(lambda ix: p[ix].sum() - (r[ix] * s[ix].mean()).sum(), n)
            print(f"      sizing value vs flat {flat:.3f}: {val:+.2f} SOL [{lo:+.2f},{hi:+.2f}]  (actual {p.sum():+.2f}, flat {(r * flat).sum():+.2f})")
            R[f"{per}|{reg}"]["sizing_value"] = dict(v=float(val), lo=lo, hi=hi, flat=float(flat))
            # with a tx cost per lot (buy + sell ~0.001 SOL each side, INFERRED): fixed costs favour bigger lots
            pc = p - 0.002
            print(f"      with 0.002 SOL tx cost per lot: per SOL {pc.sum() / s.sum():+.4f}; dead/normal split below")
        # with tx costs by regime
        for reg, m in (("dead", nz & (vs <= 30.52)), ("normal", nz & (vs > 31.06))):
            print(f"  {reg}: per SOL after 0.002/lot {(pn[m] - 0.002).sum() / sz[m].sum():+.4f}")
    json.dump(R, open(f"{OUT}/paid.json", "w"), indent=1)

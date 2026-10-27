#!/usr/bin/env python3
"""DV8 step 2e (read-only): the 'buy every dump = +70 SOL/day' contradiction. ALL candidates (no gate), guard 1.05, 0.40 SOL,
NOW costs, timer 30 (the old VAL choice) and timer 8, K=1 and no cap, on the full test days D2-D5. Steps from the old replay to ours:
  a  s7 method: independent ms landing, vshift followers, candidates with no trade after the exit target DROPPED
  b  a but keeping those candidates (exit = state after our own buy)
  c  b with the exact follower model (later sells keep their tokens)
  d  c with the contention-aware rank landing (+ far-leader delay)
  e  d calibrated to live (a x curve P&L + b per fire)
Out: dv8/g2.txt"""
import sys, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
from g1_walkforward import load, Rep, calib_boot, COST
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)


def main():
    dm = load(keep_mayhem=True); Rm = Rep(dm)
    P("# 'Buy every dump' INCLUDING mayhem tokens, s7 method (a), timer 30, SOL/day per test day:")
    cb_, cs_, cf_ = COST["NOW"]; hi_ = list(dm["HS"]).index(30)
    for K in (1, None):
        row = []
        for D in (2, 3, 4, 5):
            m = dm["usable"] & (dm["day"] == D) & ~(dm["LASTSL"] < dm["ES"][:, 1] + 30)
            rr = Rm.run(m, hi_, K=K, model="ms")
            row.append(np.mean([np.nansum(np.where(r["fill"], dm["VS7"][r["idx"], hi_], 0)) - r["fill"].sum() * (cb_ + cs_) - (~r["fill"]).sum() * cf_ for r in rr]))
        P(f"  K={K}: " + ", ".join(f"D{D} {v:+.1f}" for D, v in zip((2, 3, 4, 5), row)))
    mm = dm["usable"] & np.isin(dm["day"], (2, 3, 4, 5)) & dm["mayhem"]
    P(f"  mayhem share of candidates {100 * dm['mayhem'][dm['usable']].mean():.1f}%; mayhem fills, timer 30: vshift mean {1000 * np.nanmean(np.where(dm['FILL'][mm, 1], dm['VS7'][mm, hi_], np.nan)):+.1f} mSOL "
      f"(max {np.nanmax(dm['VS7'][mm, hi_]):+.1f} SOL on a 0.40 SOL buy) vs exact {1000 * np.nanmean(np.where(dm['FILL'][mm, 2], dm['PN'][mm, 2, hi_, 0], np.nan)):+.1f} mSOL")
    P("Below: mayhem EXCLUDED (as in DV8).\n")
    d = load(); R = Rep(d); M = d["M"]; (A0, B0), _ = calib_boot()
    HS = list(d["HS"]); ES = d["ES"]; LAST = d["LASTSL"]
    cb, cs, cf = COST["NOW"]
    full = [k for k in (2, 3, 4, 5)]
    P("# 'Buy every dump' (all DV8-entry dumps, no gate), SOL/day, mean of D2-D5 (usable hours), NOW costs")
    P("| exit | K | a s7 method | b keep no-trade exits | c exact followers | d rank landing | e calibrated | fires/day (d) | fill % (d) |"); P("|---|---|---|---|---|---|---|---|---|")
    for hi in (HS.index(30), HS.index(8)):
        for K in (1, None):
            vals = {k: [] for k in "abcde"}; nf = []; fr = []
            for D in full:
                m = d["usable"] & (d["day"] == D)
                # a/b: ms landing + vshift
                fill = d["FILL"][:, 1]; v7 = d["VS7"][:, hi]
                drop = LAST < ES[:, 1] + HS[hi]
                for key, msk in (("a", m & ~drop), ("b", m)):
                    rr = R.run(msk, hi, K=K, model="ms")
                    # replace exact pn with vshift pn for these
                    tot = 0
                    for r in rr:
                        f = r["fill"]; pn = np.where(f, v7[r["idx"]], 0.0)
                        tot += np.nansum(pn) - f.sum() * (cb + cs) - (~f).sum() * cf
                    vals[key].append(tot / len(rr))
                rr = R.run(m, hi, K=K, model="ms"); vals["c"].append(R.money(rr, "NOW"))
                rr = R.run(m, hi, K=K, model="rank"); vals["d"].append(R.money(rr, "NOW")); vals["e"].append(R.money(rr, "NOW", A0, B0, True))
                c = R.counts(rr); nf.append(c["fires"]); fr.append(c["fills"] / max(c["fires"], 1))
            P(f"| timer {HS[hi]} | {K or 'none'} | " + " | ".join(f"{np.mean(vals[k]):+.1f}" for k in "abcde") + f" | {np.mean(nf):,.0f} | {100 * np.mean(fr):.0f} |")
    # why K=1 flips: under the s7 method, mean P&L of K=1-taken fires vs all fires, and the share of dropped candidates
    hi = HS.index(30); m = d["usable"] & np.isin(d["day"], full)
    drop = LAST < ES[:, 1] + 30
    P(f"\nTimer 30, s7 method: share of candidates DROPPED for no trade after the exit target: {100 * drop[m].mean():.1f}%; "
      f"their P&L if kept (vshift, fills) mean {1000 * np.nanmean(np.where(d['FILL'][m & drop, 1], d['VS7'][m & drop, hi], np.nan)):+.2f} mSOL vs kept others "
      f"{1000 * np.nanmean(np.where(d['FILL'][m & ~drop, 1], d['VS7'][m & ~drop, hi], np.nan)):+.2f}")
    for K in (1, None):
        rr = R.run(m & ~drop, hi, K=K, model="ms")
        pn = np.concatenate([np.where(r["fill"], d["VS7"][r["idx"], hi], np.nan) for r in rr])
        P(f"  K={K}: fires {len(pn) / 4:,.0f}/day, curve P&L per fill (vshift) {1000 * np.nanmean(pn):+.2f} mSOL, fills {100 * np.mean(np.isfinite(pn)):.0f}%")
    # K=1 picks: position in the dump cascade (first dump on the mint within 30 slots?)
    sl = M["slot"].astype(np.int64); mint = M["mint"].astype(np.int64)
    o = np.lexsort((sl, mint)); prev_same = np.zeros(len(M), bool)
    prev_same[o[1:]] = (mint[o[1:]] == mint[o[:-1]]) & (sl[o[1:]] - sl[o[:-1]] <= 30)
    rr = R.run(m & ~drop, hi, K=1, model="ms")[0]
    P(f"  share of fires that are a repeat dump (another dump on the same mint <= 30 slots before): all candidates {100 * prev_same[m & ~drop].mean():.0f}%, K=1 fires {100 * prev_same[rr['idx']].mean():.0f}%")
    pv = np.where(d["FILL"][:, 1], d["VS7"][:, hi], np.nan)
    P(f"  s7 curve P&L per fill: first dumps {1000 * np.nanmean(pv[m & ~drop & ~prev_same]):+.2f} mSOL, repeat dumps {1000 * np.nanmean(pv[m & ~drop & prev_same]):+.2f} mSOL")
    open(f"{L.D}/g2.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

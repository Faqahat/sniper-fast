#!/usr/bin/env python3
"""GAP step 11b (read-only): tables from g11_res.pkl (30 % sample, scaled x1/0.30 to SOL/day). INFERRED replay.
ps entry: x0.45 fill (MEASURED), 2.51 mSOL per fill (MEASURED pre-send fill episode), 0.198 mSOL per unfilled armed window (MEASURED).
Arming cost (INFERRED lower bound): to land in the dump's own slot the pre-send must already be firing k=4 tries/slot at 5,120 lamports
each (MEASURED failed-try cost) = 0.0205 mSOL per armed slot; armed from the seller's first buy to the dump = arm_slots x 0.0205 mSOL.
Whales that never dump, and windows that overlap, are not counted (so the true arming cost is higher).
reg entry: calibrated 0.61 x curve - 1.17 mSOL/fire, NOW costs.
Out: gap/g11_tables.txt"""
import pickle, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
from g1_walkforward import calib_boot
OUT = "/home/moiz/sniper-data/haqq_dissect/gap"
PSF = 0.45; FILLC = 0.00251; XC = 0.000198; ARM = 4 * 5120 / 1e9


def main():
    Z = pickle.load(open(f"{OUT}/g11_res.pkl", "rb")); meta = Z["meta"]; res = Z["res"]; PL = Z["PL"]; FOLS = Z["FOLS"]; fr = Z["frac"]
    (A, B), _ = calib_boot()
    ids = [n for n in res]
    n_ = len(ids); nP = len(PL); nF = len(FOLS)
    ps = np.zeros((n_, nF, nP)); psf = np.zeros(n_); rg = np.zeros((n_, nF, nP)); rgf = np.zeros(n_)
    for a, n in enumerate(ids):
        rr = res[n]["res"]; P_ = [x for x in rr if x[0] == "ps"]; R_ = [x for x in rr if x[0] == "reg"]
        for x in P_:
            if x[1]: ps[a] += np.nan_to_num(x[2]) / len(P_)
        for x in R_:
            if x[1]: rg[a] += np.nan_to_num(x[2]) / len(R_)
        psf[a] = np.mean([x[1] for x in P_]) if P_ else 0; rgf[a] = np.mean([x[1] for x in R_]) if R_ else 0
    day = np.array([meta[n]["day"] for n in ids]); dev = np.array([meta[n]["dev"] for n in ids]); hq = np.array([meta[n]["hq"] for n in ids])
    bal = np.array([res[n]["bal"] for n in ids]); arm = np.array([res[n]["arm"] for n in ids], float)
    def psm(m, pol, fi=0, armc=False):
        c = ps[m, fi, PL.index(pol)]; f = psf[m] * PSF
        v = PSF * c - f * FILLC - (1 - f) * XC
        if armc: v = v - np.clip(arm[m], 0, None) * ARM
        return float(v.sum()) / fr
    def rgm(m, pol, fi=0):
        c = rg[m, fi, PL.index(pol)]; f = rgf[m]
        return float((A * c + B - f * 0.00352 - (1 - f) * 0.00053).sum()) / fr
    out = []
    def P(*x):
        s = " ".join(str(y) for y in x); print(s); out.append(s)
    W = ("RIDE", 150, 150, 1000); W2 = ("RIDE", 200, 300, 2000)
    P(f"# CAUSAL universe: dumps by the creator or a creation-slot buyer (no haqq information), D0-D5, {n_:,} sampled events (x{1 / fr:.2f} -> SOL/day)")
    P("ps = pre-send-style entry in the dump's own slot (x0.45 fill, MEASURED costs, NO arming cost) ; arm = minus arming from the seller's first buy (lower bound)")
    sets = [("all creation-slot sellers", np.ones(n_, bool)), ("seller held >= 6 % before", bal >= 6), ("seller held < 6 %", bal < 6),
            ("creator (dev) >= 6 %", dev & (bal >= 6)), ("bundle buyer >= 6 %", ~dev & (bal >= 6)),
            (">= 6 %, haqq bought it", (bal >= 6) & hq), (">= 6 %, haqq did NOT buy", (bal >= 6) & ~hq)]
    P("\n| set | events/day | " + " | ".join(f"D{d}" for d in range(6)) + " | days > 0 at 0.9 fol | median arm slots | per event mSOL: ps WAVE_PS / arm cost |")
    P("|---|---|" + "---|" * 6 + "---|---|---|")
    for nm, sm in sets:
        cells = []; pos = 0
        for d in range(6):
            m = sm & (day == d)
            v = [psm(m, W, fi) for fi in range(nF)]; pos += v[1] > 0
            cells.append(f"{v[0]:+.1f} / {v[1]:+.1f} / {v[2]:+.1f} / arm {psm(m, W, 0, True):+.1f}")
        pe = 1000 * psm(sm, W) * fr / max(sm.sum(), 1); ac = 1000 * float(np.clip(arm[sm], 0, None).mean()) * ARM
        P(f"| {nm} | {sm.sum() / fr / 6:,.0f} | " + " | ".join(cells) + f" | {pos}/6 | {np.median(arm[sm & (arm >= 0)]):.0f} | {pe:+.2f} / {ac:.2f} |")
    P("cells: ps + WAVE_PS at NOW costs, full / 0.9 / 0.8 followers / full minus arming cost (SOL/day)")
    P("\nExit comparison, ps entry, seller >= 6 %, mean SOL/day D0-D5 (full / 0.9 / 0.8 followers):")
    sm = bal >= 6
    for pol in PL: P(f"- {pol}: " + " / ".join(f"{psm(sm, pol, fi) / 6:+.2f}" for fi in range(nF)))
    P("\nRegular landing (rank model, calibrated, NOW) on the same seller >= 6 % dumps, mean SOL/day D0-D5 (full / 0.9 followers):")
    for pol in (("T", 5), ("RIDE", 150, 300, 2000)): P(f"- {pol}: " + " / ".join(f"{rgm(sm, pol, fi) / 6:+.2f}" for fi in range(2)))
    # arming-slot distribution and break-even
    a6 = arm[sm & (arm >= 0)]
    P(f"\nArm slots (seller's first buy -> dump) for >= 6 % sellers: p10/50/90 {np.percentile(a6, [10, 50, 90]).round(0)}; "
      f"share dumping within 10 slots {np.mean(a6 <= 10):.2f}, within 50 {np.mean(a6 <= 50):.2f}, within 200 {np.mean(a6 <= 200):.2f}")
    for cap in (10, 25, 50, 100, 200):
        m = sm & (arm >= 0) & (arm <= cap)
        P(f"- only dumps within {cap} slots of the seller's first buy: {m.sum() / fr / 6:,.0f} events/day, ps WAVE_PS net {psm(m, W) / 6:+.2f} SOL/day, "
          f"minus arming {psm(m, W, 0, True) / 6:+.2f} (0.9 fol {psm(m, W, 1) / 6:+.2f}); days > 0 with arming: "
          f"{sum(psm(m & (day == d), W, 0, True) > 0 for d in range(6))}/6")
    open(f"{OUT}/g11_tables.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

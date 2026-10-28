#!/usr/bin/env python3
"""SELECT step 7 (read-only): do 247/248 follow WALLET LISTS? If a bot keyed on identity (a list of dev / bundler wallets, or creators), the
follow rate per seller (or per creator) would be far more dispersed than the market model predicts (overdispersion), and a seller's
PAST follow rate (other mints, known before) would predict its next dump beyond the market model. Measured on the envelope with the s4
MKT OOS probabilities (D2-D6).
  1. dispersion: per seller with >= 5 envelope sells on D2-D6: observed y1 vs expected sum(p_MKT); chi-square-like ratio vs a binomial
     simulation from p_MKT (seeded); share of sellers with obs/exp > 3 and > 0 obs, share never followed although exp >= 2.
  2. same per creator (all dumps on that creator's tokens).
  3. walk-forward 'memory' rule: for a sell, the seller's (creator's) y1 rate on EARLIER days (other mints) -> lift over p_MKT, per day.
Out: select/s7.txt"""
import sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/select")
from s4_wf import load_scores
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/select")
OUT = "/home/moiz/sniper-data/haqq_dissect/select"


def main():
    Z = np.load(f"{OUT}/env.npz"); A = {k: Z[k] for k in ("y247", "y248", "sel", "cr", "day", "m", "f_sel_ncreates", "f_sel_dev", "f_sel_cs")}
    S = load_scores()["MKT"]; p = 1 / (1 + np.exp(-S))
    y = (A["y247"] | A["y248"]).astype(bool); day = A["day"].astype(int)
    ok = np.isfinite(p)
    out = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)
    rng = np.random.default_rng(3)
    for key, nm in (("sel", "seller"), ("cr", "creator")):
        g = A[key].astype(np.int64)[ok]; yy = y[ok].astype(float); pp = p[ok]
        u, inv, cnt = np.unique(g, return_inverse=True, return_counts=True)
        obs = np.bincount(inv, yy); exp = np.bincount(inv, pp); var = np.bincount(inv, pp * (1 - pp))
        big = cnt >= 5
        # simulated null: draw y ~ Bernoulli(p) per sell, recompute the same stats
        sim = np.bincount(inv, (rng.random(len(pp)) < pp).astype(float))
        def stats(o):
            z = (o - exp) / np.sqrt(np.maximum(var, 1e-9))
            return dict(chi=float(np.mean(z[big] ** 2)), hi=float(np.mean((o[big] > 3 * exp[big]) & (o[big] >= 3))),
                        zero=float(np.mean((o[big] == 0) & (exp[big] >= 2)) / max(np.mean(exp[big] >= 2), 1e-9)),
                        top=float(np.sort(o[big])[::-1][:int(0.05 * big.sum())].sum() / max(o[big].sum(), 1)))
        so, ss = stats(obs), stats(sim)
        P(f"\n## {nm}s with >= 5 envelope sells on D2-D6: {big.sum():,} ({cnt[big].sum():,} sells, y1 {int(obs[big].sum()):,}, MKT-expected {exp[big].sum():,.0f})")
        P("| statistic | observed | binomial null from p_MKT |"); P("|---|---|---|")
        P(f"| mean z^2 per {nm} (1 = no extra dispersion) | {so['chi']:.2f} | {ss['chi']:.2f} |")
        P(f"| share with obs > 3 x expected (and >= 3) | {so['hi']:.3f} | {ss['hi']:.3f} |")
        P(f"| share never followed among expected >= 2 | {so['zero']:.3f} | {ss['zero']:.3f} |")
        P(f"| share of y1 in the top 5 % {nm}s | {so['top']:.3f} | {ss['top']:.3f} |")
        # walk-forward memory: rate on earlier days (any mint) vs p_MKT
        P(f"\n### {nm} memory, walk-forward: sells grouped by the {nm}'s y1 rate on EARLIER days (obs/MKT-expected on the test day)")
        P("| test day | no history | hist rate 0 | (0, 5 %] | (5, 20 %] | > 20 % |"); P("|---|---|---|---|---|---|")
        G_ = A[key].astype(np.int64)
        for D in range(2, 7):
            past = day < D; te = (day == D) & ok
            up, ip = np.unique(G_[past], return_inverse=True)
            r_obs = np.bincount(ip, y[past].astype(float)); r_n = np.bincount(ip, minlength=len(up)).astype(float)
            pos = np.searchsorted(up, G_[te]); pos = np.clip(pos, 0, len(up) - 1); has = up[pos] == G_[te]
            rate = np.where(has, r_obs[pos] / np.maximum(r_n[pos], 1), -1); nn = np.where(has, r_n[pos], 0)
            cells = []
            for lo, hi in ((-2, -0.5), (-0.5, 1e-9), (1e-9, 0.05), (0.05, 0.2), (0.2, 1.1)):
                if lo < -1: m = ~has | (nn < 3)
                else: m = has & (nn >= 3) & (rate > lo) & (rate <= hi) if lo >= 0 else has & (nn >= 3) & (rate == 0)
                yt = y[te][m]; pt = p[te][m]
                cells.append(f"{int(m.sum()):,} sells, y1 {int(yt.sum())}, obs/MKT {yt.sum() / max(pt.sum(), 1e-9):.2f}")
            P(f"| D{D} | " + " | ".join(cells) + " |")
    open(f"{OUT}/s7.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

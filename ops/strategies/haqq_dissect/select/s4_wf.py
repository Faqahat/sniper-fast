#!/usr/bin/env python3
"""SELECT step 4 (read-only): does anything BEYOND market features predict which envelope dumps bots 247/248 buy? Walk-forward GBDT
(numpy, dipdetect/dd_gbdt): test day D scored by a model fitted on days < D (early stop on a random 20 % of those days' MINTS; negatives
subsampled 6 %, unweighted fit, logit shifted by log(0.06) so scores are probabilities on the full envelope). Feature sets:
  MKT   market (34)                       ALL  = MKT + CRE + SEL + CTX + STR + TIM  (everything we could see; no haqq state)
  +CRE creator history  +SEL seller history  +CTX create-tx strings/shape  +STR mint structure  +TIM time/activity
  ALLX  = ALL minus the memory of haqq's past picks (sel_prev_y/rate, cr_hq*)
  HQ    = ALL + HQS (haqq's own state)    PRE  = ALL minus the dump's own size/drop (what a pre-send armed BEFORE the dump can use)
Label y1 = 247 or 248 bought within 2 slots (MEASURED). Metrics per test day: AUC, precision at recall 10/25/50 %, rate-matched precision.
Out: select/s4_scores.npz (OOS scores per set), s4.txt"""
import sys, time, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import dd_gbdt as G
OUT = "/home/moiz/sniper-data/haqq_dissect/select"
MKT = ["drop", "dd10", "sell_sol", "sell_pct", "vpost", "age_s", "n_tr", "n_wal", "sel_dev", "sel_cs", "sel_early", "sel_bal", "sel_frac", "sel_arm",
       "ch10", "ch30", "devsold", "devb", "b3", "s3", "b10s", "s10s", "b30s", "s30s", "b10", "s10", "b30r", "ntr10", "ath_dd", "vs_launch",
       "last_dump_s", "n_dumps", "bundle_sol", "nd_buy"]
CRE = ["cr_prev", "cr_prev24", "cr_peak_max", "cr_peak_mean", "cr_peak50", "cr_dumped", "cr_hq", "cr_hqbig", "cr_hqnet", "cr_gap_s", "cr_nmay", "cr_ntr", "cr_nmint", "cr_mfol", "cr_nfol"]
SEL = ["sel_ntr", "sel_nmint", "sel_nsell", "sel_prev_env", "sel_prev_y", "sel_prev_rate", "sel_ncreates", "sel_mfol", "sel_nfol"]
STR = ["n_bund", "n_early", "early_sol", "sg_diff"]
TIM = ["t_hour", "t_creates10m", "t_env60"]
HQS = ["h_open247", "h_open248", "h_open244", "h_open226", "h_since247", "h_since248", "h_since244", "h_since226", "h_n60_247", "h_n60_248",
       "h_n60_244", "h_n60_226", "h_open_all", "h_open_tok", "h_open_tok_big", "h_prev_lots", "h_prev_net"]
HQMEM = ["sel_prev_y", "sel_prev_rate", "cr_hq", "cr_hqbig", "cr_hqnet"]      # memory of haqq's own past picks
DUMP_ONLY = ["drop", "dd10", "sell_sol", "sell_pct", "sel_frac", "vpost", "ath_dd", "vs_launch"]


def load():
    A = dict(np.load(f"{OUT}/env.npz"))
    C = np.load(f"{OUT}/ctx.npz"); cx = C["X"]; ccols = [str(c) for c in C["cols"]]
    m = A["m"].astype(np.int64)
    for k, c in enumerate(ccols): A["f_" + c] = cx[m, k]
    A["f_vpre"] = A["f_vpost"] + A["f_sell_sol"]
    A["c_have"] = C["have"][m]
    return A, ccols


def auc(s, y):
    o = np.argsort(s, kind="stable"); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / max(n1 * n0, 1))


def prec_at_recall(s, y, rec):
    o = np.argsort(-s); yy = y[o]; cp = np.cumsum(yy); k = int(np.searchsorted(cp, rec * yy.sum())) + 1
    return float(cp[k - 1] / k), k


def main():
    t0 = time.time()
    A, ccols = load()
    CTX = [c for c in ccols]
    sets = {"MKT": MKT, "MKT+CRE": MKT + CRE, "MKT+SEL": MKT + SEL, "MKT+CTX": MKT + CTX, "MKT+STR": MKT + STR, "MKT+TIM": MKT + TIM,
            "ALL": MKT + CRE + SEL + CTX + STR + TIM, "HQ": MKT + CRE + SEL + CTX + STR + TIM + HQS, "MKT+HQS": MKT + HQS,
            "PRE": [f for f in MKT + CRE + SEL + CTX + STR + TIM if f not in DUMP_ONLY] + ["vpre"],
            "ALLX": [f for f in MKT + CRE + SEL + CTX + STR + TIM if f not in HQMEM]}
    only = sys.argv[1].split(",") if len(sys.argv) > 1 else list(sets)
    import os
    LAB = os.environ.get("LABEL", "both")
    y = (A["y247"] | A["y248"]).astype(bool) if LAB == "both" else A[f"y{LAB}"].astype(bool)
    day = A["day"].astype(int); m = A["m"].astype(np.int64)
    N = len(y)
    rng = np.random.default_rng(5)
    RNEG = 0.06
    sub = y | (rng.random(N) < RNEG); w = np.where(y, 1.0, 1 / RNEG)
    mval = (np.random.default_rng(6).random(int(m.max()) + 1) < 0.2)[m]
    days = [d for d in range(2, 7) if (day == d).any()]
    lines = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s, flush=True); lines.append(s)
    P(f"# label {LAB}. Walk-forward imitation of 247/248 dump picks: envelope {N:,} sells, y1 positives {y.sum():,} ({y.mean():.4f}); per day " +
      ", ".join(f"D{d} {int((day == d).sum()):,}/{int(y[day == d].sum()):,}" for d in range(7)))
    SC = {}
    for nm in only:
        fs = sets[nm]
        Xf = np.column_stack([A["f_" + f].astype(np.float64) for f in fs])
        S = np.full(N, np.nan)
        imps = np.zeros(len(fs))
        for D in days:
            tr = sub & (day < D); fit = tr & ~mval; val = tr & mval
            te = day == D
            E = G.edges_of(Xf, fit, nb=32)
            rows = np.flatnonzero(fit | val)
            B = G.binize(Xf[rows], E); yy = y[rows].astype(np.float64); ww = w[rows]
            mod = G.fit(B, yy, fit[rows], val[rows], loss="logistic", rounds=400, lr=0.1, depth=4, min_n=100, lam=10.0, sub=0.6, fsub=0.5,
                        seed=D, patience=40, w=None)
            S[te] = G.predict(mod, G.binize(Xf[te], E)) + np.log(RNEG)      # unweighted fit on the subsample -> shift logit back
            P(f"   {nm} D{D}: best round {mod['best_round']}")
            imps += G.importance(mod, len(fs))
        SC[nm + ("" if LAB == "both" else f"_y{LAB}")] = S
        P(f"\n## {nm} ({len(fs)} features) ({time.time() - t0:.0f}s)")
        P("| test day | sells | y1 | AUC | prec@rec10 | prec@rec25 | prec@rec50 | rate-matched prec |"); P("|---|---|---|---|---|---|---|---|")
        for D in days:
            te = (day == D) & np.isfinite(S); s = S[te]; yy = y[te]
            p10, _ = prec_at_recall(s, yy, 0.10); p25, _ = prec_at_recall(s, yy, 0.25); p50, _ = prec_at_recall(s, yy, 0.50)
            k = int(yy.sum()); top = np.argsort(-s)[:k]
            P(f"| D{D} | {te.sum():,} | {k:,} | {auc(s, yy):.3f} | {p10:.3f} | {p25:.3f} | {p50:.3f} | {yy[top].mean():.3f} |")
        o = np.argsort(-imps)[:15]
        P("importance (sum over days): " + ", ".join(f"{fs[i]} {imps[i] / imps.sum():.3f}" for i in o))
    tag = "_".join(only).replace("+", "p") + ("" if LAB == "both" else f"_y{LAB}")
    np.savez(f"{OUT}/s4_scores_{tag}.npz", **SC)
    with open(f"{OUT}/s4_{tag}.txt", "w") as f: f.write("\n".join(lines) + "\n")


def load_scores():
    import glob
    SC = {}
    for f in sorted(glob.glob(f"{OUT}/s4_scores_*.npz")): SC.update(dict(np.load(f)))
    return SC


if __name__ == "__main__":
    main()

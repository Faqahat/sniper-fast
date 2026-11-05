"""QUIET3-A overlap (post-freeze, FROZEN_FLAT.json unchanged). Dev runs where QUIET3-A was NOT live (r37-r48, r52-r54).
FP-NOBOT decision per position: QUIET3-A positions -> frozen models + frozen thr (never in training);
other positions -> leave-one-block-out decisions (same scheme as fp5). No chain coverage -> never blocked."""
import sys, json, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatperfect")
import numpy as np, lightgbm as lgb, ftab
from fp5_freeze import q3a, fitpred, PRM, f20
OUTD = "/home/moiz/sniper-data/flatperfect"
FR = json.load(open("FROZEN_FLAT.json"))
P, cols, X = ftab.table(f"{OUTD}/dev_chain_full.pkl"); ci = {c: i for i, c in enumerate(cols)}
fj = [ci[c] for c in FR["features"]]; Xa = X[:, fj]
lab = X[:, ci["L_bot2"]]; y = (lab == 0).astype(int); cov = X[:, ci["cov"]] == 1
kd = np.array([p["kind"] for p in P]); pn = np.array([p["pnl"] for p in P]); cl = np.array([p["cls"] for p in P])
BL = {"r37": 1, "r38": 1, "r39": 1, "r40": 1, "r41": 1, "r42": 2}
blk = np.array([BL.get(p["run"], 3 if p["run"] <= "r48" else 4) for p in P])
Q3 = np.array([q3a(p) for p in P]); el = ~Q3 & ~np.isnan(lab)
fp = np.zeros(len(P), bool); score = np.full(len(P), np.nan)
for kind, v in FR["kinds"].items():
    m = Q3 & (kd == kind) & cov
    if m.any():
        s = np.mean([lgb.Booster(model_file=f"{OUTD}/{fn}").predict(Xa[m]) for fn in sorted(v["models"])], 0)
        score[m] = s; fp[np.nonzero(m)[0]] = s >= v["thr"]
    mk = el & (kd == kind)
    for b in (1, 2, 3, 4):
        tr = mk & (blk != b); te = mk & (blk == b)
        ii = np.nonzero(tr)[0]; hh = len(ii) // 2; o2 = np.empty(len(ii))
        for a_, b_ in ((ii[:hh], ii[hh:]), (ii[hh:], ii[:hh])):
            o2[np.searchsorted(ii, b_)] = fitpred(Xa[a_], y[a_], Xa[b_], seeds=(0,))
        t_b = np.quantile(o2, 1 - FR["q"][kind])
        fp[np.nonzero(te)[0]] = fitpred(Xa[tr], y[tr], Xa[te]) >= t_b
NOTLIVE = {"r37","r38","r39","r40","r41","r42","r43","r44","r45","r46","r47","r48","r52","r53","r54"}
base = np.array([p["run"] in NOTLIVE for p in P])
def S(name, B, U):
    sv = sorted(-pn[B], reverse=True)
    g = lambda c: f"{(cl[B]==c).sum()}({pn[B&(cl==c)].sum():+.2f})"
    print(f"{name:44s} universe {U.sum():5d} net {pn[U].sum():+.2f} | blocked {B.sum():4d} flats {g('flat')} smalls {g('small')} wins {g('win')} bigl {g('bigloss')} | saved {sum(sv):+.3f} w/o5 {sum(sv[5:]):+.3f} f20 {-sum(f20(x) for x in pn[B]):+.3f}")
for kind in ("T2", "all"):
    K = base & ((kd == kind) if kind != "all" else True)
    print(f"--- {kind}: dev runs without live QUIET3-A ({len({p['run'] for p,k in zip(P,K) if k})} runs)")
    U = K & Q3
    S("QUIET3-A positions (all)", U, U)
    S("QUIET3-A positions, chain-covered", U & cov, U & cov)
    S("  of which FP-NOBOT blocks", U & fp, U & cov)
    S("  of which FP-NOBOT passes", U & cov & ~fp, U & cov)
    Uc = K & cov
    S("(a) QUIET3-A + FP-NOBOT  [chain-covered]", Uc & (Q3 | fp), Uc)
    S("(b) FP-NOBOT only        [chain-covered]", Uc & fp, Uc)
    S("(c) QUIET3-A only        [chain-covered]", Uc & Q3, Uc)
    S("(a)-(c) = FP on top of QUIET3-A", Uc & fp & ~Q3, Uc)

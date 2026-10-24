# overlap / union of IMIT1 wider tier and the cohort-trained young-dip model at 60 ms (dip60 dataset, exit hold 4 slots and TP8/SL5/1.3s)
import sys, json, gzip, time, calendar, os
import numpy as np
os.environ["SELV"] = "3r"; sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import sel_lib as S, gbdt_np as G
M = json.load(open("IMIT1.json")); sc = np.load("x4_score_imit1_3r.npy")
imit = {(S.EV[i]["m"], S.EV[i]["age"]) for i in np.where(S.spaced(sc >= M["thresholds"]["top4"]))[0]}
sys.argv = ["x", "dip60", "c", "1", "344", "coh2"]; exec(open("sel_strat.py").read().split("base = spaced")[0])
thr = np.quantile(f[VA], 1 - 0.08); coh = spaced(f >= thr)
key = [(r["m"], r["age"]) for r in EV]; im = np.array([k in imit for k in key])
for e_name in (("H", 4), ("T", 0.08, 0.05, 6, 1)):
    e = GRID.index(e_name); p = pnl(0, e); p75 = pnl(1, e)
    for nm, m in (("IMIT1 top4", im), ("cohort top8", coh), ("both (overlap)", im & coh), ("UNION", im | coh)):
        mm = m & TE; fl = mm & FILL[:, 0]
        print(f"{str(e_name):24s} {nm:15s} TEST picks {int(mm.sum()):5d} | 60 ms {p[mm].sum():+6.2f} ({p[mm].sum() / HTE:+.2f}/h, win {((p[fl] > 0).mean() if fl.any() else 0):.0%}) | 75 ms {p75[mm].sum() / HTE:+.2f}/h")

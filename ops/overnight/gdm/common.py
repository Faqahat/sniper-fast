# GDM shared helpers (read-only, offline): data loading, GBDT (exec'd from ops/select/e_model.py), replay-outcome arrays,
# FINAL-2 offline scorer.
import json, math
import numpy as np
OUT = "/home/moiz/sniper/ops/overnight/gdm"; CORE = "/home/moiz/sniper/ops/overnight/core"; P = "/home/moiz/sniper-data/collect/paper"
_src = open("/home/moiz/sniper/ops/select/e_model.py").read()
exec(_src[_src.index("def binize"):_src.index("def stats")])          # binize, NB, build, pred, imp, auc, fit
EXITS = ["eos1", "t3", "t5", "t8", "t10", "t15"]
def load():
    Z = np.load(f"{OUT}/feats.npz"); M = json.load(open(f"{OUT}/feats_meta.json"))
    return Z, M
def outcomes(mints):
    """per landing (30/45/75) and variant (base/slip/ps/ns): array [n_rows, n_exits] of pnl (NaN = no data / not filled) and
    status: 1 fill, 0 guard failed (we were not first), -1 no data"""
    A = json.load(open(f"{CORE}/allres_bt.json"))["res"]; B = json.load(open(f"{OUT}/labels.json"))["res"]
    res = {}
    for L, src in (("30", B), ("45", A), ("75", A)):
        st = np.full(len(mints), -1); pn = {v: np.full((len(mints), len(EXITS)), np.nan) for v in ("base", "slip", "ps", "ns")}
        for i, m in enumerate(mints):
            r = src.get(m)
            if r is None or L not in r: continue
            if r[L] is None: st[i] = 0; continue
            if "ps" not in r[L]: continue
            st[i] = 1
            for v in pn: pn[v][i] = r[L][v]
        res[L] = (st, pn)
    return res
def book(sel, OC, L="45", var="ps", ex="t10", pro=True):
    """total SOL of the launches in `sel` (bool mask): fills' pnl (+0.007 pro overhead) and -0.003 (pro) / -0.005 per guard fail"""
    st, pn = OC[L]; xi = EXITS.index(ex)
    f = sel & (st == 1); g = sel & (st == 0)
    v = pn[var][f, xi] + (0.007 if pro else 0.0)
    return float(v.sum() - (0.003 if pro else 0.005) * g.sum()), int(f.sum()), int(g.sum()), v
def f2_scorer():
    C = json.load(open("/home/moiz/sniper/ops/shadow/final_config2.json"))
    M = json.load(open(f"{P}/{C['model_file']}")); MV = json.load(open(f"{P}/{C['veto_file']}")); THR = M["thresholds"][C["top"]]
    src = open("/home/moiz/sniper/ops/shadow/paper_live.py").read()
    g = {"math": math, "M": M}; exec(src[src.index("def score(x, M=M):"):src.index("# ---- shadow engine timeline")], g)
    return g["score"], M, MV, THR, C["veto_cut"]

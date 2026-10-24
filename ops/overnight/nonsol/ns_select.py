#!/usr/bin/env python3
# Task 3: create-time selection for non-SOL launches (no look-ahead): features known when the dev's glued bundle closes
# (curve facts from the create tx + bundle, the live engine's decision-time history features from the paper feature
# table - the ones the shadow logs at decide time; metadata / funder lookups / post-create flow are EXCLUDED), plus
# walk-forward non-SOL history (creator's and quote token's earlier launches, only those >= 60 s old).
# Model: L2 logistic regression (numpy), label = generic buy >= 3 SOL-eq in 2-10 s after the create. Train R1 -> test R2
# and the reverse; thresholds = train-score quantiles (top 2/5/10/20%) -> replayed with our mechanics. Also a small rule
# grid chosen on train by the strict replay PnL. -> select.txt, data/select_res.json
import sys, os, json, gzip, math, collections, statistics, itertools
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/nonsol")
from ns_lib import *
import ns
rows = sorted([r for r in load_rows() if tradeable(r)], key=lambda r: r["bt"])
allrows = sorted([r for r in load_rows() if not r.get("mayhem") and r.get("rate")], key=lambda r: r["bt"])
ms = {r["m"] for r in rows}
TD = {}
for l in gzip.open("/home/moiz/sniper-data/collect/paper/table_dump.jsonl.gz", "rt"):
    x = json.loads(l)
    if x["mint"] in ms: TD[x["mint"]] = x
LIVE = ["cr_creates_window", "cr_min_since_prev_create", "h_cr_n", "h_cr_wins", "h_name_n", "h_name_wins", "h_bund_seen", "h_bund_launches", "h_bund_wins",
        "heat_launches_10m", "heat_win_rate_60m", "wave_name_10m", "wave_name_60m", "wave_sym_60m", "name_len", "sym_len", "name_upper", "name_digits", "name_nonascii", "sym_eq_name"]
def qcls(q):
    n = ns.qname(q)
    if n in ("PUMP", "USDC"): return n
    if q.endswith("pump"): return "pump-token"
    if q.startswith("Xs"): return "xStock"
    return "other"
# ---- walk-forward non-SOL history (outcomes known 60 s after a launch)
def demand(r): return (r.get("flow") or {}).get("gen_w2_b", 0.0)
hist_cr = collections.defaultdict(list); hist_q = collections.defaultdict(list); WF = {}
pend = []; j = 0
for r in allrows:
    while j < len(allrows) and allrows[j]["bt"] + 60 <= r["bt"]:
        x = allrows[j]; hist_cr[x.get("creator")].append(demand(x)); hist_q[x["quote"]].append((x["bt"], demand(x))); j += 1
    hc = hist_cr.get(r.get("creator"), []); hq = [d for t, d in hist_q.get(r["quote"], []) if t >= r["bt"] - 3600]
    WF[r["m"]] = dict(cr_ns_n=len(hc), cr_ns_dem=(sum(hc) / len(hc)) if hc else -1, cr_ns_hit=(sum(1 for d in hc if d >= 3) / len(hc)) if hc else -1,
                      q_n60=len(hq), q_dem60=(sum(hq) / len(hq)) if hq else 0.0, q_hit60=(sum(1 for d in hq if d >= 3) / len(hq)) if hq else 0.0)
def feats(r):
    t = TD.get(r["m"], {}); w = WF[r["m"]]; qc = qcls(r["quote"])
    f = dict(q_pump=qc == "PUMP", q_usdc=qc == "USDC", q_x=qc == "xStock", q_pt=qc == "pump-token", q_oth=qc == "other",
             ldev=math.log1p(r["dev_sol"]), dev_share=r.get("dev_tok_share") or 0, glued=min(r["n_glued"], 5), gw=min(r["glued_w"], 5), lglued=math.log1p(r["glued_sol"]),
             cb=r["cbps"] / 100, shallow=r["vq0_sol"] < 25, pic=r["payer_is_creator"], tips=1 if r.get("create_tips") else 0, lfee=math.log10(max(r.get("create_fee") or 5000, 5000)),
             cv2=r.get("cvar") == "CreateV2", cr_ns_n=math.log1p(w["cr_ns_n"]), cr_ns_dem=math.log1p(max(w["cr_ns_dem"], 0)), cr_ns_new=w["cr_ns_n"] == 0,
             cr_ns_hit=max(w["cr_ns_hit"], 0), q_n60=math.log1p(w["q_n60"]), q_dem60=math.log1p(w["q_dem60"]), q_hit60=w["q_hit60"])
    for k in LIVE:
        v = t.get(k); f["t_" + k] = float(v) if isinstance(v, (int, float)) and v is not None else float("nan")
    for k in ("cr_creates_window", "h_cr_n", "h_name_n", "heat_launches_10m", "wave_name_60m", "wave_sym_60m", "h_bund_seen", "h_bund_launches"):
        if not math.isnan(f["t_" + k]): f["t_" + k] = math.log1p(max(f["t_" + k], 0))
    return {k: float(v) for k, v in f.items()}
FN = list(feats(rows[0]).keys())
def mat(rs):
    X = np.array([[feats(r)[k] for k in FN] for r in rs], dtype=float); return X
def fit(X, y, lam=1.0, it=600, lr=0.1):
    mu = np.nanmean(X, 0); X = np.where(np.isnan(X), mu, X); sd = X.std(0); sd[sd == 0] = 1; Z = (X - mu) / sd
    w = np.zeros(Z.shape[1]); b = math.log((y.mean() + 1e-6) / (1 - y.mean() + 1e-6))
    for _ in range(it):
        p = 1 / (1 + np.exp(-(Z @ w + b))); g = Z.T @ (p - y) / len(y) + lam * w / len(y); gb = (p - y).mean()
        w -= lr * g * 10; b -= lr * gb * 10
    return dict(mu=mu, sd=sd, w=w, b=b)
def score(m, X):
    X = np.where(np.isnan(X), m["mu"], X); return ((X - m["mu"]) / m["sd"]) @ m["w"] + m["b"]
def auc(s, y):
    o = np.argsort(s); rk = np.empty(len(s)); rk[o] = np.arange(len(s)); n1 = y.sum(); n0 = len(y) - n1
    return (rk[y == 1].sum() - n1 * (n1 - 1) / 2) / (n1 * n0) if n1 and n0 else float("nan")
out = []; RES = {}
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1])
EXS = ("5.0", "8.0", "10.0")
def report(tag, sel_tr, sel_te):
    cells = {}
    for nm, sel in (("train", sel_tr), ("TEST", sel_te)):
        for Lm in (30, 45, 75):
            for var in ("base", "strict"):
                for ex in EXS:
                    cells[(nm, Lm, var, ex)] = summ(sel, Lm, var, ex)
    return cells
for tr_run, te_run in (("R1", "R2"), ("R2", "R1")):
    TR_ = [r for r in rows if r["run"] == tr_run]; TE_ = [r for r in rows if r["run"] == te_run]
    Xtr, Xte = mat(TR_), mat(TE_)
    ytr = np.array([1.0 if demand(r) >= 3 else 0.0 for r in TR_]); yte = np.array([1.0 if demand(r) >= 3 else 0.0 for r in TE_])
    m = fit(Xtr, ytr); s_tr = score(m, Xtr); s_te = score(m, Xte)
    P(f"\n=== train {tr_run} (n={len(TR_)}, label rate {ytr.mean():.1%}) -> test {te_run} (n={len(TE_)}, label rate {yte.mean():.1%}); AUC train {auc(s_tr, ytr):.3f} test {auc(s_te, yte):.3f}")
    top = sorted(zip(FN, m["w"]), key=lambda x: -abs(x[1]))[:10]
    P("   top weights: " + ", ".join(f"{k} {v:+.2f}" for k, v in top))
    for qq in (0.02, 0.05, 0.10, 0.20):
        thr = np.quantile(s_tr, 1 - qq)
        sel_tr = [r for r, s in zip(TR_, s_tr) if s >= thr]; sel_te = [r for r, s in zip(TE_, s_te) if s >= thr]
        c = report(f"{tr_run}top{qq}", sel_tr, sel_te)
        P(f"   top {qq:.0%} by train score: train picks {len(sel_tr)}, test picks {len(sel_te)} (test label rate {np.mean([demand(r)>=3 for r in sel_te]) if sel_te else 0:.0%})")
        for Lm in (30, 45, 75):
            for var in ("base", "strict"):
                P(f"      L{Lm} {var:6s} " + " | ".join(f"t{ex[:-2]} tr {c[('train',Lm,var,ex)]['tot']:+6.2f} TE {c[('TEST',Lm,var,ex)]['tot']:+6.2f} ({c[('TEST',Lm,var,ex)]['fills']}f, med {c[('TEST',Lm,var,ex)]['med'] if c[('TEST',Lm,var,ex)]['med'] is not None else 0:+.3f}, win {c[('TEST',Lm,var,ex)]['win'] or 0:.0%})" for ex in EXS))
        RES[f"logit_{tr_run}_top{qq}"] = dict(test=[r["m"] for r in sel_te], train=[r["m"] for r in sel_tr], thr=float(thr),
                                              cells={"|".join(map(str, k)): v for k, v in c.items()})
    # ---- small rule grid on train (strict replay PnL, L45, t8), min 40 train fills
    grid = []
    for dmin, gmin, cbmax, qset, wf in itertools.product((0, 0.5, 1, 2, 3), (0, 1, 2, 3), (30, 100, 300), ("all", "noPT", "PUMP+X+oth"), ("any", "cr_new", "q_hot")):
        def ok(r, dmin=dmin, gmin=gmin, cbmax=cbmax, qset=qset, wf=wf):
            qc = qcls(r["quote"]); w = WF[r["m"]]
            if r["dev_sol"] < dmin or r["n_glued"] < gmin or r["cbps"] > cbmax: return False
            if qset == "noPT" and qc == "pump-token": return False
            if qset == "PUMP+X+oth" and qc not in ("PUMP", "xStock", "other"): return False
            if wf == "cr_new" and w["cr_ns_n"] > 0: return False
            if wf == "q_hot" and w["q_hit60"] < 0.25: return False
            return True
        st = [r for r in TR_ if ok(r)]
        s = summ(st, 45, "strict", "8.0")
        if s["fills"] >= 40: grid.append((s["tot"], (dmin, gmin, cbmax, qset, wf), ok))
    grid.sort(key=lambda x: -x[0])
    P(f"   rule grid (chosen on {tr_run} by strict L45 t8 total, >= 40 fills): best 5 ->")
    for tot, prm, ok in grid[:5]:
        se = [r for r in TE_ if ok(r)]; st = [r for r in TR_ if ok(r)]
        P(f"      dev>={prm[0]} glued>={prm[1]} cbps<={prm[2]} quotes={prm[3]} hist={prm[4]}: train {fmt(summ(st,45,'strict','8.0'))}")
        P(f"         TEST {te_run}: " + " | ".join(f"L{Lm} t{ex[:-2]} {summ(se,Lm,'strict',ex)['tot']:+6.2f} ({summ(se,Lm,'strict',ex)['fills']}f)" for Lm in (30, 45, 75) for ex in ("5.0", "8.0")))
        RES[f"rule_{tr_run}_{prm}"] = dict(test=[r["m"] for r in se], train=[r["m"] for r in st])
json.dump(RES, open(os.path.join(DATA, "select_res.json"), "w"))
open(os.path.join(HERE, "select.txt"), "w").write("\n".join(out) + "\n")

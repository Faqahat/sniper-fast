#!/usr/bin/env python3
# ROUND 2 (read-only, offline): boosted-tree pump classifier per entry, strictly time-ordered.
# label y = best gross return reachable within 10 min AFTER the entry >= +50% (L<entry>_best >= 0.5)
# features limited to the entry's availability tiers; histogram GBDT (logistic) in numpy; early stop on validation.
# reports AUC, precision@top-k (pump rate, graduation rate), trading results of the top-k with an exit chosen on
# VALIDATION, by period, plus a walk-forward (train periods <p, test period p) and feature importance.
# usage: python3 e_model.py <table.jsonl.gz> <out dir> [FIX_SOL]
import sys, os, json, gzip, re, collections
import numpy as np
T, OUT = sys.argv[1], sys.argv[2]; FIX = float(sys.argv[3]) if len(sys.argv) > 3 else 0.015; SIZE = 0.5
os.makedirs(OUT, exist_ok=True)
R = [json.loads(l) for l in gzip.open(T, "rt")]
R = [r for r in R if r.get("quote_sol") == 1 and (r.get("max_vsol") or 0) <= 200 and r.get("bt")]
R.sort(key=lambda r: (r["bt"], r["S"])); N = len(R)
bt = np.array([r["bt"] for r in R], float); period = ((bt - bt.min()) // (3 * 3600)).astype(int)
idx = np.arange(N); TR = idx < int(N * .5); VA = (idx >= int(N * .5)) & (idx < int(N * .75)); TE = idx >= int(N * .75)
T0 = {"dev_buy", "create_cup", "create_cul", "create_tips", "create_cu", "create_idx", "create_fee", "mayhem", "name_len", "sym_len", "name_upper", "name_digits",
      "name_nonascii", "sym_eq_name", "payer_is_creator", "hour_utc", "heat_launches_10m", "wave_name_10m", "wave_name_60m", "wave_sym_60m", "cr_creates_window",
      "cr_min_since_prev_create"}
T1 = {"cr_prior_n", "cr_prior_fail", "cr_age_s", "cr_last_tx_s", "cr_recent_creates", "cr_same_name_before", "fund_amt", "fd_creators_so_far", "fd_is_creator"}
T2 = {"meta_ok", "desc_len", "has_tw", "has_tg", "has_web", "tw_status", "tw_community", "web_same_as_tw", "meta_keys"}
def tier(k):
    if k in T0: return "T0"
    if k in T1: return "T1"
    if k in T2: return "T2"
    if k.startswith("glued_") or k in ("P0_mc_sol", "dev_share", "bundle_avg"): return "T0b"
    if k.startswith("h_") or k.startswith("hd_") or k == "heat_win_rate_60m": return "H"
    if k.startswith("slot_") or k.startswith("fslot_"): return "Fslot"
    if k.startswith("f1s_"): return "F1"
    if k.startswith("f5s_"): return "F5"
    if k.startswith("eb1s_"): return "EB1"
    if k.startswith("eb5s_"): return "EB5"
    return None
CAT = {"create_variant": "T0", "uri_host": "T0", "fp": "T0", "web_host": "T2", "img_host": "T2", "created_on": "T2"}
ENT = {"E_bundle": {"T0", "T0b", "T1", "H"}, "E_k1": {"T0", "T0b", "T1", "H"}, "E_k2": {"T0", "T0b", "T1", "H"}, "E_k3": {"T0", "T0b", "T1", "H"}, "E_slot": {"T0", "T0b", "T1", "H", "Fslot"}, "E_s1": {"T0", "T0b", "T1", "H", "Fslot"},
       "E_1s": {"T0", "T0b", "T1", "H", "Fslot", "F1"}, "E_5s": {"T0", "T0b", "T1", "H", "Fslot", "F1", "T2", "EB1"},
       "E_15s": {"T0", "T0b", "T1", "H", "Fslot", "F1", "F5", "T2", "EB1", "EB5"}}
num = sorted({k for r in R for k, v in r.items() if isinstance(v, (int, float)) and not isinstance(v, bool) and tier(k)})
cols = {k: (tier(k), np.array([r.get(k) if isinstance(r.get(k), (int, float)) else np.nan for r in R], float)) for k in num}
for k, tt in CAT.items():
    top = [v for v, c in collections.Counter(r.get(k) or "" for r, t in zip(R, TR) if t).most_common(15) if c >= 100]
    for v in top: cols[f"{k}=={v}"] = (tt, np.array([float((r.get(k) or "") == v) for r in R]))
g = lambda k: np.array([r.get(k) if isinstance(r.get(k), (int, float)) else np.nan for r in R], float)
GRAD = g("graduated")

def binize(X, tr):
    B = np.zeros(X.shape, np.int16); edges = []
    for j in range(X.shape[1]):
        x = X[:, j]; xt = x[tr & ~np.isnan(x)]
        e = np.unique(np.quantile(xt, np.linspace(0, 1, 33)[1:-1])) if len(xt) else np.array([])
        edges.append(e); b = np.searchsorted(e, x, side="right") + 1; b[np.isnan(x)] = 0; B[:, j] = b
    return B
NB = 34
def build(Bm, gr, he, rows, depth, lam=1.0, min_n=60, fsub=None):
    """returns tree as nested dict; histogram split search over all features at once"""
    G, H = gr[rows].sum(), he[rows].sum()
    if depth == 0 or len(rows) < 2 * min_n: return {"w": -G / (H + lam)}
    F = Bm.shape[1]; sub = Bm[rows][:, fsub]
    flat = (sub + NB * np.arange(len(fsub))).ravel()
    hg = np.bincount(flat, np.repeat(gr[rows], len(fsub)), NB * len(fsub)).reshape(len(fsub), NB)
    hh = np.bincount(flat, np.repeat(he[rows], len(fsub)), NB * len(fsub)).reshape(len(fsub), NB)
    hn = np.bincount(flat, None, NB * len(fsub)).reshape(len(fsub), NB)
    cg, ch, cn = hg.cumsum(1), hh.cumsum(1), hn.cumsum(1)
    gain = cg ** 2 / (ch + lam) + (G - cg) ** 2 / (H - ch + lam) - G ** 2 / (H + lam)
    gain[(cn < min_n) | (len(rows) - cn < min_n)] = -1; gain[:, -1] = -1
    j, b = np.unravel_index(np.argmax(gain), gain.shape)
    if gain[j, b] <= 0: return {"w": -G / (H + lam)}
    f = fsub[j]; left = rows[Bm[rows, f] <= b]; right = rows[Bm[rows, f] > b]
    return {"f": int(f), "b": int(b), "gain": float(gain[j, b]), "l": build(Bm, gr, he, left, depth - 1, lam, min_n, fsub), "r": build(Bm, gr, he, right, depth - 1, lam, min_n, fsub)}
def pred(t, Bm):
    out = np.zeros(len(Bm)); stack = [(t, np.arange(len(Bm)))]
    while stack:
        n, ix = stack.pop()
        if "w" in n: out[ix] = n["w"]; continue
        m = Bm[ix, n["f"]] <= n["b"]; stack.append((n["l"], ix[m])); stack.append((n["r"], ix[~m]))
    return out
def imp(t, acc):
    if "w" in t: return
    acc[t["f"]] += t["gain"]; imp(t["l"], acc); imp(t["r"], acc)
def auc(y, s):
    o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1); p = y.sum(); n = len(y) - p
    return float((r[y == 1].sum() - p * (p + 1) / 2) / (p * n)) if p and n else float("nan")
def fit(Bm, y, tr, va, rounds=600, lr=0.05, depth=3, seed=0):
    rng = np.random.default_rng(seed); p0 = y[tr].mean(); F0 = np.log(p0 / (1 - p0)); f = np.full(len(y), F0); trees = []
    best = (1e9, 0); trn = np.where(tr)[0]
    for k in range(rounds):
        p = 1 / (1 + np.exp(-f)); gr = p - y; he = p * (1 - p)
        rows = rng.choice(trn, int(len(trn) * .8), replace=False); fsub = np.sort(rng.choice(Bm.shape[1], max(1, int(Bm.shape[1] * .8)), replace=False))
        t = build(Bm, gr, he, rows, depth, fsub=fsub); f += lr * pred(t, Bm); trees.append(t)
        pv = np.clip(1 / (1 + np.exp(-f[va])), 1e-6, 1 - 1e-6); ll = -np.mean(y[va] * np.log(pv) + (1 - y[va]) * np.log(1 - pv))
        if ll < best[0] - 1e-5: best = (ll, k + 1)
        elif k + 1 - best[1] > 50: break
    trees = trees[:best[1]]; f = np.full(len(y), F0)
    for t in trees: f += lr * pred(t, Bm)
    return trees, f
def stats(v):
    v = v[~np.isnan(v)]
    if len(v) == 0: return None
    pnl = v * SIZE; pos, neg = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum(); cum = np.concatenate([[0], np.cumsum(pnl)])
    return dict(n=int(len(v)), win=float((v > 0).mean()), mean=float(v.mean()), median=float(np.median(v)), pf=float(pos / neg) if neg else None,
                exp_sol=float(pnl.mean()), total_sol=float(pnl.sum()), maxdd_sol=float(np.max(np.maximum.accumulate(cum) - cum)), winners=int((v > 0).sum()), losers=int((v <= 0).sum()))
REPORT = {}
for en, tiers in ENT.items():
    fk = [k for k, (tt, _) in cols.items() if tt in tiers]; X = np.column_stack([cols[k][1] for k in fk]); Bm = binize(X, TR)
    best_ret = g(f"L{en}_best"); y = (best_ret >= 0.5).astype(float); ok = ~np.isnan(best_ret)
    exits = [k for k in R[0] if k.startswith(en + "_") and not k.endswith("entry_px")] or [k for k in {kk for r in R[:50] for kk in r} if k.startswith(en + "_") and not k.endswith("entry_px")]
    trees, f = fit(Bm, y, TR & ok, VA & ok)
    res = dict(features=len(fk), trees=len(trees), base_pump_rate_test=float(y[TE & ok].mean()), base_grad_rate_test=float(np.nanmean(GRAD[TE])),
               auc_val=auc(y[VA & ok], f[VA & ok]), auc_test=auc(y[TE & ok], f[TE & ok]))
    acc = np.zeros(len(fk))
    for t in trees: imp(t, acc)
    res["importance"] = [(fk[j], round(float(acc[j] / acc.sum()), 4)) for j in np.argsort(-acc)[:15] if acc[j] > 0]
    res["topk"] = {}
    for q in (0.01, 0.02, 0.05, 0.10):
        thr_v = np.quantile(f[VA & ok], 1 - q)                         # score threshold fixed on VALIDATION
        sel_v = VA & ok & (f >= thr_v); sel_t = TE & ok & (f >= thr_v)
        ex_best = max(exits, key=lambda k: np.nanmean(g(k)[sel_v]) if sel_v.sum() else -9)   # exit chosen on validation
        rv = g(ex_best) - FIX / SIZE
        per = {int(p): stats(rv[sel_t & (period == p)]) for p in np.unique(period[TE])}
        res["topk"][f"{q:.0%}"] = dict(threshold=float(thr_v), exit=ex_best, n_test=int(sel_t.sum()), pump_rate_test=float(y[sel_t].mean()) if sel_t.sum() else None,
                                      grad_rate_test=float(np.nanmean(GRAD[sel_t])) if sel_t.sum() else None, val=stats(rv[sel_v]), test=stats(rv[sel_t]), by_period=per)
    # walk-forward: train on periods < p (last 20% of that as early-stop holdout), test period p, top 5% by that model
    wf = {}
    for p in range(2, int(period.max()) + 1):
        past = (period < p) & ok; cut = np.quantile(idx[past], .8); trw = past & (idx < cut); vaw = past & (idx >= cut); tew = (period == p) & ok
        tw, fw = fit(Bm, y, trw, vaw, seed=p)
        thr = np.quantile(fw[vaw], .95); sel = tew & (fw >= thr)
        ex = max(exits, key=lambda k: np.nanmean(g(k)[vaw & (fw >= thr)]))
        rv = g(ex) - FIX / SIZE
        wf[p] = dict(auc=auc(y[tew], fw[tew]), base=float(y[tew].mean()), n=int(sel.sum()), pump_rate=float(y[sel].mean()) if sel.sum() else None, exit=ex, trade=stats(rv[sel]))
    res["walk_forward_top5"] = wf
    REPORT[en] = res
    t5 = res["topk"]["5%"]; tt = t5["test"] or {}
    print(f"{en:8} AUC val {res['auc_val']:.3f} test {res['auc_test']:.3f} | base pump {res['base_pump_rate_test']:.1%} | top5% pump {t5['pump_rate_test'] or 0:.1%} "
          f"grad {t5['grad_rate_test'] or 0:.1%} | trade n={tt.get('n')} mean={tt.get('mean', 0):+.3f} med={tt.get('median', 0):+.3f} pf={tt.get('pf') or 0:.2f} ({t5['exit']})", flush=True)
    for p, w in wf.items():
        tr_ = w["trade"] or {}
        print(f"     walk-forward period {p}: AUC {w['auc']:.3f} base {w['base']:.1%} top5% pump {w['pump_rate'] or 0:.1%} trade n={tr_.get('n')} mean={tr_.get('mean', 0):+.3f} pf={tr_.get('pf') or 0:.2f}", flush=True)
    print("     top features:", ", ".join(f"{k} {v:.0%}" for k, v in res["importance"][:8]), flush=True)
json.dump(REPORT, open(os.path.join(OUT, f"model_fix{FIX}.json"), "w"), indent=1, default=str)

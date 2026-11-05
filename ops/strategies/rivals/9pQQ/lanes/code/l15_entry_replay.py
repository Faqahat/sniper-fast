#!/usr/bin/env python3
"""LANES step 14: replicated P&L of the per-module imitation rules (entry GBDT + exit GBDT), at HIS speed (+46 ms after the trigger trade,
sell +46 ms after the exit-trigger trade), plus +0 ms, +70 ms (info only) and -20 % followers rows. Thresholds chosen on 10-31, test 11-02.
Picks are the sampled decision moments (negatives sampled 4 %, weighted x25), each evaluated independently (no position interaction).
Rows also: his own picks + model exit (exit-only crack test).  -> lanes/replay.json"""
import sys, json, pickle, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/rivals/9pQQ/lanes/code")
import gbw, llib, sim, xfeat, tlib
RUNS = llib.RUNS; CH, TE = "run_20261031_1350", "run_20261102_1250"
# ---- exit model with stored bin edges
Z = [np.load(f"{llib.D}/xmom_{r}.npz") for r in RUNS[:4]]
X = np.concatenate([z["X"] for z in Z]); y = np.concatenate([z["y"] for z in Z]).astype(float); w = np.concatenate([z["w"] for z in Z]).astype(float)
part = np.concatenate([np.full(len(z["y"]), k) for k, z in enumerate(Z)]); tr = part <= 2; va = part == 3
edges = []
for j in range(X.shape[1]):
    xt = X[tr, j]; xt = xt[~np.isnan(xt)]; edges.append(np.unique(np.quantile(xt, np.linspace(0, 1, 33)[1:-1])))
def bz(Xn):
    B = np.zeros(Xn.shape, np.int16)
    for j, e in enumerate(edges):
        b = np.searchsorted(e, Xn[:, j], side="right") + 1; b[np.isnan(Xn[:, j])] = 0; B[:, j] = b
    return B
trees, _ = gbw.fit(bz(X), y, tr, va, rounds=500, lr=0.08, depth=4, w=w, min_n=80)
def xscore(Xn):
    f = np.zeros(len(Xn)); Bn = bz(Xn)
    for t_ in trees: f += 0.08 * gbw.pred(t_, Bn)
    return f
del X, Z
def trip_scores(T, m, tin, ctx):
    """entry at chain time tin; returns (exit-candidate rows, their exit scores, cap chain time) or None"""
    t = T.t; a, b = t.ms[m], t.ms[m + 1]
    e, cb = T.state_at(m, tin)
    if e < a: return None
    vt = cb + llib.V; p_entry = (llib.K / vt) / vt
    x = sim.SIZE / (1 + sim.FEE); tok = vt - llib.K / (llib.K / vt + x)
    s_e = int(t.s[e]); bt_e = int(t.bt[e])
    hi = a + int(np.searchsorted(t.bt[a:b], bt_e + 600, side="right"))
    tcap = (T.cc[hi] - 1e-6) if hi < b else T.cc[b - 1] + 1   # state just before the first trade after the cap (no look-ahead)
    if hi <= e + 1: return (np.zeros(0, int), np.zeros(0), tcap)
    F, rows = xfeat.feats(T, e + 1, hi, s_e, bt_e, p_entry, p_entry, ctx, extra_tok=tok)
    ok = F[:, 0] >= 2
    return (rows[ok], xscore(F[ok]) if ok.any() else np.zeros(0), tcap)
def exit_time(T, ts, thr_x, dsell):
    rows, sc, tcap = ts
    hit = np.nonzero(sc >= thr_x)[0]
    return T.cc[rows[hit[0]]] + dsell if len(hit) else tcap
def run_trip(T, m, tin, ctx, thr_x, dsell, fol=0.0):
    ts = trip_scores(T, m, tin, ctx)
    if ts is None: return None
    return T.trip(m, tin, exit_time(T, ts, thr_x, dsell), fol=fol)
EXIT_THR = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
res = {}
qs = {"NEW": (0.999, 0.997, 0.99), "TRK": (0.99, 0.97, 0.9)}
thr = {}
for nm in ("NEW", "TRK"):
    sc = np.load(f"{llib.D}/score_{nm}_{CH}.npy"); w_ = np.load(f"{llib.D}/mom_{CH}.npz")["w"]; ok = ~np.isnan(sc)
    o = np.argsort(sc[ok]); cw = np.cumsum(w_[ok][o]); cw /= cw[-1]
    thr[nm] = {q: float(sc[ok][o][np.searchsorted(cw, q)]) for q in qs[nm]}
print("entry thresholds (weighted score quantiles chosen on 10-31):", thr, flush=True)
for run in (CH, TE):
    T = sim.Tape(run); t = T.t
    z = np.load(f"{llib.D}/mom_{run}.npz"); fn = list(z["fn"]); ids = z["ids"]; yy = z["y"]; ww = z["w"]; mo = z["mod"]; XX = z["X"]
    hrs = tlib.hours(run); out = {}
    for nm in ("NEW", "TRK"):
        sc = np.load(f"{llib.D}/score_{nm}_{run}.npy")
        for q, th in thr[nm].items():
            sel = np.nonzero(~np.isnan(sc) & (sc >= th))[0]
            rng = np.random.default_rng(1)
            if len(sel) > 1500: sel = rng.choice(sel, 1500, replace=False); fac = (~np.isnan(sc) & (sc >= th)).sum() / 1500
            else: fac = 1.0
            W_ = ww[sel] * fac
            prec = float((yy[sel] * W_).sum() / W_.sum()); npick = float(W_.sum())
            rows = {}; dump = dict(w=W_, y=yy[sel], k=sel)
            for lab_, d, fol, ex in (("his_speed_46ms", 46, 0.0, "model"), ("best_0ms", 0, 0.0, "model"), ("info_70ms", 70, 0.0, "model"), ("his_speed_fol20", 46, 0.2, "model"), ("his_speed_hold80", 46, 0.0, "h80")):
                v = []
                for k in sel:
                    m, j = int(ids[k, 0]), int(ids[k, 1]); tin = T.cc[j] + d
                    c = dict(age=float(XX[k, fn.index("age")]), k_prev=float(XX[k, fn.index("k_prev")]), mod=float(mo[k]), nopen=float(XX[k, fn.index("nopen")]), hour=float(XX[k, fn.index("hour")]))
                    if ex == "model": p = run_trip(T, m, tin, c, EXIT_THR, d, fol=fol)
                    else:
                        a, b = t.ms[m], t.ms[m + 1]; s_out = t.s[j] + 80; e2 = a + int(np.searchsorted(t.s[a:b], s_out, side="right"))
                        p = T.trip(m, tin, (t.s[j] + 80) * sim.SMS + sim.SMS - 1e-3, fol=fol)
                    v.append(0.0 if p is None else p)
                v = np.array(v); dump[lab_] = v
                rows[lab_] = dict(sol_day=round(float((v * W_).sum() / 1e9 * 24 / hrs), 2), msol_trip=round(float((v * W_).sum() / W_.sum() / 1e6), 2),
                                  tp_msol=round(float((v * W_)[yy[sel]].sum() / max(W_[yy[sel]].sum(), 1) / 1e6), 2), fp_msol=round(float((v * W_)[~yy[sel]].sum() / max(W_[~yy[sel]].sum(), 1) / 1e6), 2))
            np.savez(f"{llib.D}/picks_{run}_{nm}_q{q}_x{EXIT_THR}.npz", **dump)
            out[f"{nm}_q{q}"] = dict(picks_day=round(npick * 24 / hrs, 0), precision=round(prec, 3), **rows)
            print(run, nm, q, json.dumps(out[f"{nm}_q{q}"]), flush=True)
    res[run] = out
    del T
json.dump(dict(exit_thr=EXIT_THR, entry_thr=thr, res=res), open(f"/home/moiz/sniper/ops/strategies/rivals/9pQQ/lanes/replay_entry_x{EXIT_THR}.json", "w"), indent=1)

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
res = {}
for run in (CH, TE):
    T = sim.Tape(run); t = T.t
    z = np.load(f"{llib.D}/mom_{run}.npz"); fn = list(z["fn"]); ids = z["ids"]; yy = z["y"]; ww = z["w"]; mo = z["mod"]; XX = z["X"]
    on = np.load(f"{llib.D}/momon_{run}.npy")
    def ctx_of(k): return dict(age=float(XX[k, fn.index("age")]), k_prev=float(XX[k, fn.index("k_prev")]), mod=float(mo[k]), nopen=float(XX[k, fn.index("nopen")]), hour=float(XX[k, fn.index("hour")]))
    R = tlib.trips(run); out = {}
    # (A) his picks + model exit, thresholds sweep
    his = []
    for r in R:
        if r["amm_exit"] or r["mint"] not in t.mix: continue
        m = t.mix[r["mint"]]; a, b = t.ms[m], t.ms[m + 1]
        key = t.s[a:b].astype(np.int64) * 100000 + t.i[a:b]; jb = a + int(np.searchsorted(key, r["bs"] * 100000 + r["bi"]))
        if jb >= b or t.u[jb] != t.wid: continue
        his.append((m, T.cc[jb] - 1e-6, dict(age=float(r["age"]), k_prev=float(r["k_prev"]), mod=0.0 if (r["k_prev"] == 0 or r["since_sell"] > 20000) else 1.0, nopen=float(r["nopen"]), hour=float(((r["bbt"] + 18000) % 86400) // 3600)), r))
    rng = np.random.default_rng(3); sub = [his[k] for k in rng.choice(len(his), min(2500, len(his)), replace=False)]
    scale = len(his) / len(sub) * 24 / tlib.hours(run)
    TS = [trip_scores(T, m, tin, c) for m, tin, c, r in sub]
    def his_exit(m, r):
        a_, b_ = t.ms[m], t.ms[m + 1]; key = t.s[a_:b_].astype(np.int64) * 100000 + t.i[a_:b_]
        return T.cc[a_ + int(np.searchsorted(key, r["ss"] * 100000 + r["si"]))] - 1e-6
    out["his_picks_his_exit_sim"] = round(float(sum(T.trip(m, tin, his_exit(m, r)) for m, tin, c, r in sub) / 1e9 * scale), 2)
    out["his_picks_his_exit_sim_fol20"] = round(float(sum(T.trip(m, tin, his_exit(m, r), fol=0.2) for m, tin, c, r in sub) / 1e9 * scale), 2)
    for thr_x in (-1.0, 0.0, 0.5, 1.0, 1.5, 99.0):
        v = [T.trip(m, tin, exit_time(T, ts, thr_x, 46)) for (m, tin, c, r), ts in zip(sub, TS) if ts is not None]
        out[f"his_picks_model_exit_thr{thr_x}"] = round(float(np.sum(v) / 1e9 * scale), 2)
    for hold in (6, 30, 80, 250):
        v = []
        for m, tin, c, r in sub:
            a_, b_ = t.ms[m], t.ms[m + 1]; e, _ = T.state_at(m, tin); e2 = a_ + int(np.searchsorted(t.s[a_:b_], t.s[max(e, a_)] + hold, side="right"))
            v.append(T.trip(m, tin, (t.s[max(e, a_)] + hold) * sim.SMS + sim.SMS - 1e-3))
        out[f"his_picks_fixed_hold{hold}"] = round(float(np.sum(v) / 1e9 * scale), 2)
    print(run, json.dumps(out), flush=True)
    res[run] = out
    pickle.dump(res, open(f"{llib.D}/replay_partial.pkl", "wb"))
    del T
json.dump(res, open("/home/moiz/sniper/ops/strategies/rivals/9pQQ/lanes/replay_exit_%s.json" % "v3", "w"), indent=1)

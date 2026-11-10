"""TIMING library: online per-wallet timer hazard from the position table (t3 pos.npy) + the scoring helpers (pass bar)."""
import json, pickle
import numpy as np
D = "/home/it/sniper-data/prevent/timing"
I = json.load(open(f"{D}/hist_ids.json")); Ui = {x: k for k, x in enumerate(I["user"])}; Mi = {x: k for k, x in enumerate(I["mint"])}
P = np.load(f"{D}/pos.npy"); P = P[np.lexsort((P["b0"], P["u"]))]
UB = np.searchsorted(P["u"], np.arange(len(I["user"]) + 1))
_cache = {}


def hz(wallet, S, mint, h, H, min_risk=5):
    """P(first sell in [h, h+H] | at risk at h) from the wallet's positions on other mints first-bought before slot S (online).
    returns (hz or None if < min_risk at risk, n_at_risk)"""
    key = (wallet, S, mint, h, H)
    if key in _cache: return _cache[key]
    u = Ui.get(wallet)
    if u is None or h is None: _cache[key] = (None, 0); return _cache[key]
    a, e = UB[u], UB[u + 1]
    X = P[a:e]; k = np.searchsorted(X["b0"], S); X = X[:k]
    mid = Mi.get(mint, -1); X = X[X["m"] != mid]
    if len(X) == 0: _cache[key] = (None, 0); return _cache[key]
    done = (X["s1"] >= 0) & (X["s1"] < S)
    dt = np.where(done, X["s1"] - X["b0"], S - X["b0"])
    risk = (dt >= h) & (done | (dt >= h + H)); ev = done & (dt >= h) & (dt <= h + H)
    n = int(risk.sum())
    out = ((ev.sum() + 0.05) / (n + 1.0) if n >= min_risk else None, n)
    _cache[key] = out
    return out


def hour_of(t_ns): return int(t_ns // 3_600_000_000_000)


def score(rows, gain_key="gain", runs_pick=None, test="A37", r38="A38", B=2000, seed=0):
    """rows: list of dict(run, t, gain, blocked(bool), p696). gain = SOL saved/gained @0.696 (0 when the rule does nothing).
    returns dict of the pass-bar stats"""
    import collections
    rng = np.random.default_rng(seed)
    per = collections.defaultdict(float)
    for r in rows: per[r["run"]] += r[gain_key]
    pick = [r for r in rows if r["run"] not in (test, r38)]
    tst = [r for r in rows if r["run"] == test]
    pt = pick + tst
    g_pick = sum(r[gain_key] for r in pick); g_test = sum(r[gain_key] for r in tst); g_r38 = per.get(r38, 0.0)
    runs = sorted({r["run"] for r in pick})
    up = sum(1 for x in runs if per[x] > 1e-12); dn = sum(1 for x in runs if per[x] < -1e-12)
    # block bootstrap over clock hours
    hb = collections.defaultdict(float)
    for r in pt: hb[hour_of(r["t"])] += r[gain_key]
    hv = np.array(list(hb.values()))
    bs = [hv[rng.integers(len(hv), size=len(hv))].sum() for _ in range(B)] if len(hv) else [0]
    ci = (float(np.percentile(bs, 5)), float(np.percentile(bs, 95)))
    gs = sorted((r[gain_key] for r in pt), reverse=True)
    tot = sum(gs)
    w1 = tot - (gs[0] if gs else 0); w5 = tot - sum(gs[:5])
    blk = [r for r in pt if r.get("blocked")]
    win_sk = sum(r["p696"] for r in blk if r["p696"] > 0); los_sk = -sum(r["p696"] for r in blk if r["p696"] <= 0)
    return dict(pick=g_pick, test=g_test, r38=g_r38, runs_up=up, runs_dn=dn, ci=ci, wo1=w1, wo5=w5, n_blk_pick=sum(1 for r in pick if r.get("blocked")),
                n_blk_test=sum(1 for r in tst if r.get("blocked")), n_blk_r38=sum(1 for r in rows if r["run"] == r38 and r.get("blocked")),
                win_sk=win_sk, los_sk=los_sk, per=dict(per))


def verdict(s, need_cut=None):
    c1 = s["test"] > 0; c2 = s["runs_up"] > s["runs_dn"]; c3 = s["ci"][0] > 0; c4 = s["wo1"] > 0; c5 = s["win_sk"] <= s["los_sk"]
    c6 = True if need_cut is None else need_cut >= 0
    if c1 and c2 and c3 and c4 and c5 and c6: return "PASS"
    if c1 and c4: return "LEAD"
    return "FAIL"

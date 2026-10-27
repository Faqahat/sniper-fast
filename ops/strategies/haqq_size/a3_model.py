#!/usr/bin/env python3
"""HAQQ_SIZE step 3 (read-only): what drives haqq's buy size. Features knowable at his buy (a1_buys.py) + his own state (running
realized P&L, recent win rate, open positions) from his earlier closed lots.
Split by time: train 10-23 19:28 -> 10-25 23:15, validate 10-25 23:15 -> 10-26 23:15, TEST (held out) 10-26 23:15 -> 10-27 23:05 PKT.
Target: gross buy SOL (0.01 probes excluded; reported separately). Classes for tier accuracy: S < 0.33, M 0.33-0.6, L >= 0.7.
Models: (a) one-threshold rule on curve SOL; (b) a depth-3 regression tree (exhaustive split search); (c) GBDT on all features
(upper bound). Out: OUT/model.json, OUT/buyfeat.pkl"""
import sys, pickle, json, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import dd_gbdt as G
OUT = "/home/moiz/sniper-data/haqq_size"
W0 = 1793038500; TR1 = W0 - 86400; TE1 = W0 + 86400 - 600
Z = pickle.load(open(f"{OUT}/buys.pkl", "rb")); B = Z["buys"]; LOTS = Z["lots"]; TRIPS = Z["trips"]
FEAT = ["age", "vsol_pre", "nd_early", "nd_before", "sell_before", "dev_buy", "dev_sold", "bundle_n", "bundle_sol", "n_trades", "n_traders",
        "big_sell3", "drop_sell3", "drop10", "fb_n", "coh_n", "hour", "s0", "s14c", "add", "prev_mine", "pnl30", "pnl120", "win20", "open_n", "since_last"]


def own_state():
    """his state at each buy from earlier closed lots / open trips (all strictly before the buy's block time)"""
    ev = sorted((L["close_bt"], L["out"] - L["cost"]) for L in LOTS if L["close_bt"] is not None)
    cb = np.array([e[0] for e in ev], np.int64); cp = np.concatenate([[0.0], np.cumsum([e[1] for e in ev])]); win = np.array([e[1] > 0 for e in ev])
    t0s = np.sort(np.array([t["bt0"] for t in TRIPS], np.int64)); t1s = np.sort(np.array([t["close_bt"] if t["close_bt"] else 2 ** 40 for t in TRIPS], np.int64))
    bts = np.sort(np.array([b["bt"] for b in B], np.int64))
    for b in B:
        x = b["bt"]; i = int(np.searchsorted(cb, x))           # lots closed strictly before x
        b["pnl30"] = float(cp[i] - cp[int(np.searchsorted(cb, x - 1800))]); b["pnl120"] = float(cp[i] - cp[int(np.searchsorted(cb, x - 7200))])
        b["win20"] = float(win[max(i - 20, 0):i].mean()) if i > 0 else 0.5
        b["open_n"] = float(np.searchsorted(t0s, x) - np.searchsorted(t1s, x, side="right"))
        j = int(np.searchsorted(bts, x)); b["since_last"] = float(x - bts[j - 1]) if j > 0 else 1e4
        b["s14c"] = b["s14"] if b["s14_ok"] else np.nan


def cls(s): return np.where(s < 0.33, 0, np.where(s < 0.6, 1, 2))


def r2(y, p): return 1 - float(((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def tree(X, y, depth, min_n=200, qs=np.linspace(0.02, 0.98, 49)):
    """exhaustive L2 regression tree (quantile candidate splits); returns nested dict"""
    node = dict(n=len(y), v=float(y.mean()))
    if depth == 0 or len(y) < 2 * min_n: return node
    best = None; base = ((y - y.mean()) ** 2).sum()
    for j in range(X.shape[1]):
        x = X[:, j]; ok = ~np.isnan(x)
        for q in np.unique(np.nanquantile(x[ok], qs)) if ok.any() else []:
            l = ok & (x <= q); r = ~l
            if l.sum() < min_n or r.sum() < min_n: continue
            sse = ((y[l] - y[l].mean()) ** 2).sum() + ((y[r] - y[r].mean()) ** 2).sum()
            if best is None or sse < best[0]: best = (sse, j, float(q))
    if best is None or best[0] > base * 0.995: return node
    _, j, q = best; l = ~np.isnan(X[:, j]) & (X[:, j] <= q)
    node.update(f=j, q=q, L=tree(X[l], y[l], depth - 1, min_n), R=tree(X[~l], y[~l], depth - 1, min_n))
    return node


def tpred(node, X):
    out = np.empty(len(X))
    for i, x in enumerate(X):
        n = node
        while "f" in n: n = n["L"] if (not np.isnan(x[n["f"]]) and x[n["f"]] <= n["q"]) else n["R"]
        out[i] = n["v"]
    return out


def tshow(node, names, ind=""):
    if "f" not in node: return [f"{ind}-> {node['v']:.3f} SOL (n={node['n']})"]
    return ([f"{ind}if {names[node['f']]} <= {node['q']:.4g}:"] + tshow(node["L"], names, ind + "  ") + [f"{ind}else:"] + tshow(node["R"], names, ind + "  "))


if __name__ == "__main__":
    own_state()
    X = np.array([[float(b[f]) for f in FEAT] for b in B]); y = np.array([b["size"] for b in B]); bt = np.array([b["bt"] for b in B])
    pickle.dump(dict(X=X, y=y, bt=bt, FEAT=FEAT, mint=[b["mint"] for b in B], slot=[b["slot"] for b in B]), open(f"{OUT}/buyfeat.pkl", "wb"))
    nz = y > 0.05
    tr = nz & (bt < TR1); va = nz & (bt >= TR1) & (bt < W0); te = nz & (bt >= W0) & (bt < TE1); tv = tr | va
    print(f"rows (excl. 0.01 probes): train {tr.sum()}, val {va.sum()}, test {te.sum()}")
    R = {}
    yt = y[te]; ct = cls(yt)
    def rep(name, p):
        acc = float((cls(p) == ct).mean()); r = r2(yt, p)
        cm = np.zeros((3, 3), int)
        for a, b_ in zip(ct, cls(p)): cm[a, b_] += 1
        R[name] = dict(r2=r, acc=acc, cm=cm.tolist(), mae=float(np.abs(yt - p).mean()))
        print(f"{name:42s} TEST R2 {r:+.3f}  tier acc {100 * acc:.1f}%  MAE {np.abs(yt - p).mean():.3f}  confusion(S,M,L) {cm.tolist()}")
    rep("constant (train+val mean)", np.full(te.sum(), y[tv].mean()))
    rep("constant (val mean)", np.full(te.sum(), y[va].mean()))
    # (a) one threshold on curve SOL, values = val-day means
    v = X[:, FEAT.index("vsol_pre")]
    for thr in (30.3, 30.5, 30.6, 31.0, 31.5):
        lo = va & (v <= thr); hi = va & (v > thr)
        p = np.where(v[te] <= thr, y[lo].mean(), y[hi].mean())
        rep(f"rule curve<= {thr}: {y[lo].mean():.2f} else {y[hi].mean():.2f} (val means)", p)
    # (b) trees fit on the last pre-test day (val), and on train+val
    for nm, fitm in (("val day", va), ("train+val", tv)):
        for d in (1, 2, 3):
            T_ = tree(X[fitm], y[fitm], d, min_n=150)
            p = tpred(T_, X[te]); rep(f"tree depth {d} fit on {nm}", p)
            if d >= 2: print("\n".join(tshow(T_, FEAT, "    ")))
            R[f"tree depth {d} fit on {nm}"]["tree"] = tshow(T_, FEAT)
    # (c) GBDT (fit on train, early stop on val)
    E = G.edges_of(X, tr, nb=32); Bn = G.binize(X, E)
    M = G.fit(Bn, y, tr, va, loss="l2", rounds=1500, lr=0.05, depth=4, min_n=100, lam=5.0, sub=0.8, fsub=0.8, seed=1, patience=100)
    p = G.predict(M, Bn); rep("GBDT all features (train, early-stop val)", p[te])
    imp = G.importance(M, len(FEAT)); oi = np.argsort(imp)[::-1]
    R["gbdt_imp"] = [(FEAT[j], round(float(imp[j]), 4)) for j in oi]
    print("GBDT importance:", R["gbdt_imp"][:12])
    # GBDT without his own state features (Kelly check) and without curve SOL
    for drop in (("pnl30", "pnl120", "win20", "open_n", "since_last"), ("vsol_pre",)):
        keep = [j for j, f in enumerate(FEAT) if f not in drop]
        E2 = G.edges_of(X[:, keep], tr, nb=32); B2 = G.binize(X[:, keep], E2)
        M2 = G.fit(B2, y, tr, va, loss="l2", rounds=1500, lr=0.05, depth=4, min_n=100, lam=5.0, sub=0.8, fsub=0.8, seed=1, patience=100)
        rep(f"GBDT without {','.join(drop)[:28]}", G.predict(M2, B2)[te])
    # Kelly-like: correlation of the residual (after the curve rule) with his own state, on all non-probe rows
    thr = 30.6
    res = y - np.where(v <= thr, np.nan, 0)
    nn = nz & (v > thr)
    for f in ("pnl30", "pnl120", "win20", "open_n", "since_last", "hour", "s0", "drop10", "dev_buy", "add"):
        x = X[nn, FEAT.index(f)]; ok = ~np.isnan(x)
        rk = lambda a: np.argsort(np.argsort(a))
        R.setdefault("spearman_normal", {})[f] = float(np.corrcoef(rk(x[ok]), rk(y[nn][ok]))[0, 1])
    print("Spearman with size, normal-curve buys (curve > 30.6):", {k: round(v_, 3) for k, v_ in R["spearman_normal"].items()})
    # probes (0.01): what are they?
    pr = y <= 0.05
    print(f"0.01 probes: {pr.sum()}; median curve {np.median(v[pr]):.1f} vs {np.median(v[~pr]):.1f}; median drop10 {np.median(X[pr, FEAT.index('drop10')]):.3f} "
          f"vs {np.median(X[~pr, FEAT.index('drop10')]):.3f}; add share {X[pr, FEAT.index('add')].mean():.2f}")
    json.dump(R, open(f"{OUT}/model.json", "w"), indent=1, default=float)

#!/usr/bin/env python3
# sssssDdM SELECTION MODEL (read-only; adapted from bukp/bk3_select.py, not modified). Decision points = every NON-FLEET trade
# on a standard curve (curve 30-113 SOL, age >= 5 slots, >= 5 trades so far) while sssssDdM is active (it sent a buy within
# +-10 min) and does NOT hold that token. Label 1 = this trade is the last non-fleet trade before one of its BUY ATTEMPTS
# (landed OR failed on slippage, from the raw scan: its full decision set) landing <= 2 slots later; 0 = skipped.
# Features = the causal features at that trade (patterns/p1_build.py) except identities. numpy GBDT trained on R2,
# early-stopped on an R2 holdout, tested on R3 and R1 (AUC, precision/recall, lift) + taken-rate bands of the top features.
# Also: the same with the sibling's state (ssssswdk holds the token) as an extra feature, to measure fleet coupling.
# -> sssss/select.json, sssss/select_model.json
import sys, json, zlib
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import p4_eval as E
import gbdt_np as G
OUT = "/home/moiz/sniper-data/strategies/sssss"
W = "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d"; UID = zlib.crc32(W.encode())
SIBS = ["ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E", "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi", "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ"]
FLEET = np.array([UID] + [zlib.crc32(s.encode()) for s in SIBS], np.int64); WDK = zlib.crc32(SIBS[0].encode())
DROP = {"bid", "w_first"}

def holding_mask(d, uid):
    """per trade: does wallet uid hold this token right now (after its entry, up to and including its exit)?"""
    n = len(d["s"]); hold = np.zeros(n, bool); tok = d["tok"]
    by_tok = {}
    for k in np.flatnonzero(d["uid"] == uid): by_tok.setdefault(int(tok[k]), []).append(int(k))
    for t, ks in by_tok.items():
        p = 0.0; pk = 0.0; start = None
        for k in ks:
            if d["buy"][k]:
                if start is None: start = k
                p += d["tokn"][k]; pk = max(pk, p)
            else:
                p -= d["tokn"][k]
                if p <= 0.01 * pk and start is not None: hold[start:k + 1] = True; start = None; p = 0.0; pk = 0.0
        if start is not None: hold[start:int(d["tend"][start])] = True
    return hold

def points(d, run, rng, neg_rate):
    F = d["F"]; FI = d["FI"]; n = len(d["s"])
    isfleet = np.isin(d["uid"], FLEET)
    att = json.load(open(f"{OUT}/att_{run}.json"))
    pos_label = np.zeros(n, bool); t_att = []
    for a in att:
        t_att.append(a["s"] * 212.0)
        if a["dslot"] <= 2: pos_label[a["j"]] = True
    t_att = np.sort(np.array(t_att))
    p = np.searchsorted(t_att, d["arr"]); l = np.abs(d["arr"] - t_att[np.maximum(p - 1, 0)]); r = np.abs(t_att[np.minimum(p, len(t_att) - 1)] - d["arr"])
    online = np.minimum(l, r) <= 600_000
    hold = holding_mask(d, UID)
    base = (~isfleet) & (~hold) & (F[:, FI["curve"]] >= 30) & (F[:, FI["curve"]] < 113) & (F[:, FI["age"]] >= 5) & (F[:, FI["ntr"]] >= 5) & online
    pos_idx = np.flatnonzero(base & pos_label); neg_idx = np.flatnonzero(base & ~pos_label)
    if neg_rate < 1: neg_idx = np.sort(rng.choice(neg_idx, int(len(neg_idx) * neg_rate), replace=False))
    wdk_hold = holding_mask(d, WDK)
    return pos_idx, neg_idx, int(base.sum()), int((base & pos_label).sum()), wdk_hold

def fit_eval(tag, FEATS, getX, data, rng):
    pi, ni = data["R2"][0], data["R2"][1]
    idx = np.concatenate([pi, ni]); y = np.concatenate([np.ones(len(pi)), np.zeros(len(ni))])
    X = getX("R2", idx); tr = rng.random(len(idx)) < 0.8
    edges = []
    for j in range(X.shape[1]):
        x = X[:, j]; xt = x[tr & ~np.isnan(x)]
        edges.append(np.unique(np.quantile(xt, np.linspace(0, 1, 33)[1:-1])) if len(xt) else np.array([]))
    def binm(X):
        B = np.zeros(X.shape, np.int16)
        for j in range(X.shape[1]):
            b = np.searchsorted(edges[j], X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; B[:, j] = b
        return B
    trees, f = G.fit(binm(X), y, tr, ~tr, rounds=500, lr=0.08, depth=4, seed=1)
    gains = np.zeros(X.shape[1])
    for t in trees: G.imp(t, gains)
    order = np.argsort(-gains)
    print(f"[{tag}] trees {len(trees)}; R2 holdout AUC {G.auc(y[~tr], f[~tr]):.3f}", flush=True)
    print(f"[{tag}] top features by gain:", [(FEATS[j], round(float(gains[j] / gains.sum()), 3)) for j in order[:20]], flush=True)
    res = {"features": [(FEATS[j], round(float(gains[j] / gains.sum()), 4)) for j in order], "days": {}}
    for run in [r for r in data if r != "R2"]:
        pi, ni = data[run][0], data[run][1]
        idx = np.concatenate([pi, ni]); yy = np.concatenate([np.ones(len(pi)), np.zeros(len(ni))])
        s = np.zeros(len(idx)); B = binm(getX(run, idx))
        for t in trees: s += 0.08 * G.pred(t, B)
        a = G.auc(yy, s); o = np.argsort(-s); cum = np.cumsum(yy[o]); rows = []
        for top in (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1):
            k = max(1, int(top * len(s)))
            rows.append(dict(top=top, flagged=k, precision=round(float(cum[k - 1] / k), 4), recall=round(float(cum[k - 1] / yy.sum()), 3)))
        res["days"][run] = dict(auc=round(a, 3), base_rate=round(float(yy.mean()), 5), pr=rows)
        print(f"[{tag}] {run}: AUC {a:.3f}; base rate {yy.mean():.4%}; " + "; ".join(f"top {r['top']:.1%}: prec {r['precision']:.1%} rec {r['recall']:.0%}" for r in rows), flush=True)
    return res, trees, edges, order

if __name__ == "__main__":
    days = ["R2", "R3", "R1"]
    rng = np.random.default_rng(3); data = {}; DD = {}
    for run in days:
        E.load([run]); d = E.DAYS[run]
        pi, ni, nbase, npos, wh = points(d, run, rng, 0.12 if run == "R2" else 0.5)
        data[run] = (pi, ni)
        print(f"{run}: decision points {nbase}, taken (attempted) {npos} ({npos / max(1, nbase):.3%})", flush=True)
        FEATS = [f for f in d["M"]["feats"] if f not in DROP]; FIX = [d["FI"][f] for f in FEATS]
        idx = np.concatenate([pi, ni])
        DD[run] = dict(idx=idx, X=d["F"][idx][:, FIX].astype(float), wh=wh[idx].astype(float), F=None)
        if run == "R2": DD["bands"] = (d["F"][pi], d["F"][ni], d["FI"])
        del E.DAYS[run]
    def getX(run, idx):
        pos = {int(k): n for n, k in enumerate(DD[run]["idx"])}; rows = [pos[int(k)] for k in idx]
        return DD[run]["X"][rows]
    def getXw(run, idx):
        pos = {int(k): n for n, k in enumerate(DD[run]["idx"])}; rows = [pos[int(k)] for k in idx]
        return np.concatenate([DD[run]["X"][rows], DD[run]["wh"][rows][:, None]], axis=1)
    res, trees, edges, order = fit_eval("public", FEATS, getX, data, rng)
    res_w, _, _, _ = fit_eval("public+wdk_holds", FEATS + ["wdk_holds"], getXw, data, rng)
    # taken rate by bands of the top features on R2 (all points; negatives were subsampled at 12%)
    Fp, Fn, FI = DD["bands"]; bands = {}
    for j in order[:12]:
        fname = FEATS[j]; xp = Fp[:, FI[fname]]; xn = Fn[:, FI[fname]]
        qs = np.unique(np.quantile(np.concatenate([xp, xn]), [0, .1, .25, .5, .75, .9, .97, 1]))
        rowsb = []
        for lo, hi in zip(qs[:-1], qs[1:]):
            np_ = ((xp >= lo) & (xp <= hi)).sum(); nn = ((xn >= lo) & (xn <= hi)).sum() / 0.12
            rowsb.append((round(float(lo), 3), round(float(hi), 3), int(np_), round(float(np_ / max(1, np_ + nn)), 4)))
        bands[fname] = rowsb
        print(f"  {fname}: attempted rate by band [lo, hi, attempted, rate]: {rowsb}", flush=True)
    res["bands_R2"] = bands; res["with_wdk"] = res_w
    json.dump(res, open(f"{OUT}/select.json", "w"), indent=1)
    json.dump(dict(edges=[e.tolist() for e in edges], feats=FEATS, trees=trees, lr=0.08), open(f"{OUT}/select_model.json", "w"))

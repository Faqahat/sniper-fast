#!/usr/bin/env python3
# BUkpShoE SELECTION MODEL (read-only). Decision points = every other-wallet trade on a standard curve (curve 30-113 SOL,
# age >= 5 slots, >= 5 trades so far) while BUkpShoE is active (it traded within +-10 min) and does NOT already hold that
# token. Label 1 = this trade is the last other-wallet trade before one of its buys landing <= 2 slots later (taken);
# 0 = skipped. Features = the causal features at that trade (patterns/p1_build.py) except identities. numpy GBDT
# (sel/gbdt_np.py) trained on R2, early-stopped on an R2 holdout, tested on R3 and R1 (AUC, precision/recall, lift).
# -> bukp/select.json (+ feature gains, score thresholds)
import sys, json, zlib
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import p4_eval as E
import gbdt_np as G
OUT = "/home/moiz/sniper-data/strategies/bukp"
W = "BUkpShoEWRiPckdFs3kzYGjBPfUhL6G39ufo84QeogPP"; UID = zlib.crc32(W.encode())
DROP = {"bid", "w_first"}
def points(d, rng, neg_rate):
    F = d["F"]; FI = d["FI"]; n = len(d["s"])
    me = d["uid"] == UID
    t_me = np.sort(d["arr"][me])
    def online(t):
        p = np.searchsorted(t_me, t); l = np.abs(t - t_me[np.maximum(p - 1, 0)]); r = np.abs(t_me[np.minimum(p, len(t_me) - 1)] - t)
        return np.minimum(l, r) <= 600_000
    # holding mask: per trade, does BUkp hold this token right now (bought, not yet fully sold)?
    hold = np.zeros(n, bool); tok = d["tok"]
    idx_me = np.flatnonzero(me)
    pos = {}; last = {}
    # walk his trades per token: mark trades strictly between his entry and his exit as "holding"
    by_tok = {}
    for k in idx_me: by_tok.setdefault(int(tok[k]), []).append(int(k))
    pos_label = np.zeros(n, bool)
    for t, ks in by_tok.items():
        p = 0.0; pk = 0.0; start = None
        for k in ks:
            if d["buy"][k]:
                if p <= 0.01 * max(pk, 1):
                    # the trigger = last other-wallet trade before this buy, within 2 slots
                    j = k - 1
                    while j >= 0 and tok[j] == t and d["uid"][j] == UID: j -= 1
                    if j >= 0 and tok[j] == t and d["s"][k] - d["s"][j] <= 2: pos_label[j] = True
                    start = k
                p += d["tokn"][k]; pk = max(pk, p)
            else:
                p -= d["tokn"][k]
                if p <= 0.01 * pk and start is not None: hold[start:k + 1] = True; start = None; p = 0.0; pk = 0.0
        if start is not None: hold[start:int(d["tend"][start])] = True
    base = (~me) & (~hold) & (F[:, FI["curve"]] >= 30) & (F[:, FI["curve"]] < 113) & (F[:, FI["age"]] >= 5) & (F[:, FI["ntr"]] >= 5)
    base &= online(d["arr"])
    pos_idx = np.flatnonzero(base & pos_label); neg_idx = np.flatnonzero(base & ~pos_label)
    if neg_rate < 1: neg_idx = np.sort(rng.choice(neg_idx, int(len(neg_idx) * neg_rate), replace=False))
    return pos_idx, neg_idx, int(base.sum()), int((base & pos_label).sum())

if __name__ == "__main__":
    E.load(["R1", "R2", "R3"])
    FEATS = [f for f in E.DAYS["R2"]["M"]["feats"] if f not in DROP]; FIX = [E.DAYS["R2"]["FI"][f] for f in FEATS]
    rng = np.random.default_rng(3)
    data = {}
    for run in ("R2", "R3", "R1"):
        d = E.DAYS[run]
        pi, ni, nbase, npos = points(d, rng, 0.15 if run == "R2" else 1.0)
        data[run] = (pi, ni, nbase, npos)
        print(f"{run}: decision points {nbase}, taken {npos} ({npos / max(1, nbase):.3%})", flush=True)
    # train on R2 (subsampled negatives), holdout 20% for early stopping
    pi, ni, _, _ = data["R2"]; d = E.DAYS["R2"]
    idx = np.concatenate([pi, ni]); y = np.concatenate([np.ones(len(pi)), np.zeros(len(ni))])
    X = d["F"][idx][:, FIX].astype(float)
    tr = rng.random(len(idx)) < 0.8
    Bm_edges = []
    # binize with R2-train edges; keep edges to apply on test days
    edges = []
    for j in range(X.shape[1]):
        x = X[:, j]; xt = x[tr & ~np.isnan(x)]
        edges.append(np.unique(np.quantile(xt, np.linspace(0, 1, 33)[1:-1])) if len(xt) else np.array([]))
    def binm(X):
        B = np.zeros(X.shape, np.int16)
        for j in range(X.shape[1]):
            b = np.searchsorted(edges[j], X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; B[:, j] = b
        return B
    Bm = binm(X)
    trees, f = G.fit(Bm, y, tr, ~tr, rounds=500, lr=0.08, depth=4, seed=1)
    gains = np.zeros(X.shape[1])
    for t in trees: G.imp(t, gains)
    order = np.argsort(-gains)
    print(f"trees {len(trees)}; R2 holdout AUC {G.auc(y[~tr], f[~tr]):.3f}")
    print("top features by gain:", [(FEATS[j], round(float(gains[j] / gains.sum()), 3)) for j in order[:20]])
    res = {"features": [(FEATS[j], round(float(gains[j] / gains.sum()), 4)) for j in order], "days": {}}
    def score(run):
        d = E.DAYS[run]; pi, ni, nbase, npos = data[run]
        idx = np.concatenate([pi, ni]); yy = np.concatenate([np.ones(len(pi)), np.zeros(len(ni))])
        B = binm(d["F"][idx][:, FIX].astype(float))
        s = np.zeros(len(idx))
        for t in trees: s += 0.08 * G.pred(t, B)
        return idx, yy, s
    for run in ("R3", "R1"):
        idx, yy, s = score(run)
        a = G.auc(yy, s); o = np.argsort(-s); cum = np.cumsum(yy[o])
        rows = []
        for top in (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1):
            k = max(1, int(top * len(s)))
            rows.append(dict(top=top, flagged=k, precision=round(float(cum[k - 1] / k), 4), recall=round(float(cum[k - 1] / yy.sum()), 3)))
        res["days"][run] = dict(auc=round(a, 3), base_rate=round(float(yy.mean()), 5), pr=rows)
        print(f"{run}: AUC {a:.3f}; base rate {yy.mean():.4%}; " + "; ".join(f"top {r['top']:.1%}: precision {r['precision']:.2%} recall {r['recall']:.0%}" for r in rows))
    # partial dependence-ish: taken rate by bands of the top features on R2 (all points)
    d = E.DAYS["R2"]; pi, ni, _, _ = data["R2"]; FI = d["FI"]
    bands = {}
    for j in order[:10]:
        fname = FEATS[j]; xp = d["F"][pi, FI[fname]]; xn = d["F"][ni, FI[fname]]
        qs = np.unique(np.quantile(np.concatenate([xp, xn]), [0, .1, .25, .5, .75, .9, 1]))
        rowsb = []
        for lo, hi in zip(qs[:-1], qs[1:]):
            np_ = ((xp >= lo) & (xp <= hi)).sum(); nn = ((xn >= lo) & (xn <= hi)).sum() / 0.15
            rowsb.append((round(float(lo), 3), round(float(hi), 3), int(np_), round(float(np_ / max(1, np_ + nn)), 4)))
        bands[fname] = rowsb
        print(f"  {fname}: taken rate by band [lo, hi, taken, rate]: {rowsb}")
    res["bands_R2"] = bands
    json.dump(res, open(f"{OUT}/select.json", "w"), indent=1)
    json.dump(dict(edges=[e.tolist() for e in edges], feats=FEATS, trees=trees, lr=0.08), open(f"{OUT}/select_model.json", "w"))

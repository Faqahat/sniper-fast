#!/usr/bin/env python3
# GRADUATION MODEL (read-only). Candidate moments = other-wallet trades on standard curves (curve 30-100 SOL, age >= 5,
# >= 5 trades so far), BUkpShoE's entry triggers included. Label = the curve completes (vsol >= 113 SOL) within N minutes
# of that trade (N = 2, 5, 10). Causal features only (patterns/p1_build.py feature row at that trade: age, curve, flows,
# wallets, bots holding, dev/insider sold, momentum, launch labels; no identities). numpy GBDT per N trained on R2
# (negatives subsampled), tested on R3 / R1: AUC, lift and precision at the top-k. Also: P(graduate) at its own entries.
# -> bukp/grad_model_N{2,5,10}.json, bukp/grad.json
import sys, json, zlib
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import p4_eval as E
import gbdt_np as G
OUT = "/home/moiz/sniper-data/strategies/bukp"
UID = zlib.crc32(b"BUkpShoEWRiPckdFs3kzYGjBPfUhL6G39ufo84QeogPP")
DROP = {"bid", "w_first", "wt", "hour"}
NS = {2: 566, 5: 1415, 10: 2830}

def grad_slot(d):
    """per trade: slot at which its token's curve completes (huge if never)"""
    tok = d["tok"]; nt = int(tok.max()) + 1; gs = np.full(nt, 10 ** 12, np.int64)
    g = np.flatnonzero(d["vsol"] >= 113e9)
    for k in g[::-1]: gs[tok[k]] = d["s"][k]        # earliest (iterate reversed so the first one wins)
    return gs[tok]

def cands(d):
    F = d["F"]; FI = d["FI"]
    gs = grad_slot(d)
    m = (d["uid"] != UID) & (F[:, FI["curve"]] >= 30) & (F[:, FI["curve"]] < 100) & (F[:, FI["age"]] >= 5) & (F[:, FI["ntr"]] >= 5) & (d["s"] < gs)
    return np.flatnonzero(m), gs

def its_triggers(d):
    T = [t for t in json.load(open(f"{OUT}/trips_{d['run']}.json"))]
    out = []
    for t in T:
        j = t["k0"] - 1
        while j >= 0 and d["uid"][j] == UID: j -= 1
        if j >= 0 and d["tok"][j] == d["tok"][t["k0"]] and d["s"][t["k0"]] - d["s"][j] <= 2: out.append(j)
    return np.array(sorted(set(out)), np.int64)

def binm(X, edges):
    B = np.zeros(X.shape, np.int16)
    for j, e in enumerate(edges):
        b = np.searchsorted(e, X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; B[:, j] = b
    return B

def predict(trees, lr, B):
    s = np.zeros(len(B))
    for t in trees: s += lr * G.pred(t, B)
    return s

if __name__ == "__main__":
    days = ["R2", "R3", "R1"]; E.load(days)
    for r in days: E.DAYS[r]["run"] = r
    FEATS = [f for f in E.DAYS["R2"]["M"]["feats"] if f not in DROP]; FIX = [E.DAYS["R2"]["FI"][f] for f in FEATS]
    C = {r: cands(E.DAYS[r]) for r in days}
    out = {"feats": FEATS, "N": {}}
    rng = np.random.default_rng(4)
    for N, slots in NS.items():
        d = E.DAYS["R2"]; idx, gs = C["R2"]; y = ((gs[idx] - d["s"][idx]) <= slots).astype(float)
        pos = idx[y == 1]; neg = idx[y == 0]; neg = np.sort(rng.choice(neg, min(len(neg), 400000), replace=False))
        ii = np.concatenate([pos, neg]); yy = np.concatenate([np.ones(len(pos)), np.zeros(len(neg))]); w_neg = (y == 0).sum() / len(neg)
        X = d["F"][ii][:, FIX].astype(float); tr = rng.random(len(ii)) < 0.8
        edges = [np.unique(np.quantile(X[tr, j][~np.isnan(X[tr, j])], np.linspace(0, 1, 33)[1:-1])) for j in range(X.shape[1])]
        trees, f = G.fit(binm(X, edges), yy, tr, ~tr, rounds=500, lr=0.08, depth=4, seed=N)
        gains = np.zeros(X.shape[1])
        for t in trees: G.imp(t, gains)
        o = np.argsort(-gains)
        res = dict(base_R2=round(float(y.mean()), 4), auc_R2_holdout=round(G.auc(yy[~tr], f[~tr]), 3), top_features=[(FEATS[j], round(float(gains[j] / gains.sum()), 3)) for j in o[:12]], days={})
        json.dump(dict(edges=[e.tolist() for e in edges], trees=trees, lr=0.08, feats=FEATS), open(f"{OUT}/grad_model_N{N}.json", "w"))
        for r in ("R2", "R3", "R1"):
            d = E.DAYS[r]; idx, gs = C[r]; yt = ((gs[idx] - d["s"][idx]) <= slots).astype(float)
            s = predict(trees, 0.08, binm(d["F"][idx][:, FIX].astype(float), edges))
            o2 = np.argsort(-s); cum = np.cumsum(yt[o2])
            pr = []
            for top in (0.001, 0.005, 0.01, 0.02, 0.05, 0.1):
                k = max(1, int(top * len(s))); pr.append((top, round(float(cum[k - 1] / k), 4), round(float(cum[k - 1] / k / yt.mean()), 1), round(float(cum[k - 1] / yt.sum()), 3)))
            # its entries: graduation rate and model score percentile
            trg = its_triggers(d); trg = trg[np.isin(trg, idx)]
            yi = ((gs[trg] - d["s"][trg]) <= slots).astype(float)
            si = predict(trees, 0.08, binm(d["F"][trg][:, FIX].astype(float), edges))
            pct = float(np.mean(si[:, None] > s[None, :1].T[:0].T)) if False else float(np.mean(np.searchsorted(np.sort(s), si) / len(s)))
            res["days"][r] = dict(base=round(float(yt.mean()), 4), auc=round(G.auc(yt, s), 3), top=pr, its_entries=int(len(trg)), its_grad_rate=round(float(yi.mean()), 4),
                                  its_lift=round(float(yi.mean() / yt.mean()), 2), its_score_pctile=round(pct, 3))
        out["N"][N] = res
        print(f"N={N} min: R2 base {res['base_R2']:.2%}, holdout AUC {res['auc_R2_holdout']}; top features {res['top_features'][:8]}")
        for r, v in res["days"].items():
            print(f"   {r}: AUC {v['auc']}, base {v['base']:.2%}; top 1% precision {v['top'][2][1]:.1%} (lift x{v['top'][2][2]}, recall {v['top'][2][3]:.0%}); top 0.1% precision {v['top'][0][1]:.1%} (x{v['top'][0][2]})"
                  f" | ITS entries {v['its_entries']}: graduate within {N} min {v['its_grad_rate']:.2%} (x{v['its_lift']} vs base), model score pctile {v['its_score_pctile']}", flush=True)
    json.dump(out, open(f"{OUT}/grad.json", "w"), indent=1)

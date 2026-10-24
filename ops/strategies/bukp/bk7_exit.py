#!/usr/bin/env python3
# BUkpShoE EXIT MODEL (read-only). While it holds, every other-wallet trade is an exit decision point; label 1 = the last
# other-wallet trade before its sell (sell <= 2 slots later), 0 = it kept holding. Features = causal token features at that
# trade + position features (price vs its entry fill, peak since entry, slots held, drawdown from peak, other-wallet sell /
# buy SOL since entry and in the last 3 slots). numpy GBDT trained on R2, tested on R3/R1 (AUC).
# Then the REPLICA: its own entries re-timed to OUR landing (35 / 50 ms after its trigger, +5% guard, size 0.6 SOL capped
# version and its 2%-of-curve size), our exit = first trade whose exit score >= threshold (chosen on R2) or the 1,417-slot
# timeout; our sell lands 35 ms after that trade (same-slot fill model); follower slippage limits; our costs.
# -> bukp/exit_model.json, bukp/exit_replica.json
import sys, json, zlib, math
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import p4_eval as E
import gbdt_np as G
OUT = "/home/moiz/sniper-data/strategies/bukp"
UID = zlib.crc32(b"BUkpShoEWRiPckdFs3kzYGjBPfUhL6G39ufo84QeogPP")
TF = ["ev_buy", "sol", "move", "wt", "age", "curve", "ath_r", "ret1", "ret3", "ret10", "ret30", "nb3", "ns3", "bsol3", "ssol3", "net3", "nw3", "bigs3", "maxs3", "dd3",
      "nb10", "ns10", "net10", "bigs10", "dd10", "fam_s10", "dev_s30", "ins_s30", "nbot_hold", "fam_hold", "hour"]
PF = ["mult", "peak", "held", "dd_peak", "sell_since", "buy_since", "n_sell_since"]
FIX = 0.0035; FAIL = 0.0005; GUARD = 1.05; GRADV = 113e9; TOUT = 1417

def trip_rows(d, t, p_in=None):
    """decision rows for one trip (its own path): indices of other-wallet trades between entry and exit + position features"""
    FI = d["FI"]; k0 = t["k0"]; ks = t["sells"][-1]["k"]; s0 = d["s"][k0]
    if p_in is None: p_in = t["buys"][0]["sol"] * 1e9 / t["buys"][0]["tok"]
    rows = []; pk = 1.0; ssum = bsum = 0.0; nsell = 0
    for q in range(k0 + 1, ks):
        if d["uid"][q] == UID: continue
        price = d["vsol"][q] / d["vtok"][q]; m = price / p_in; pk = max(pk, m)
        if d["buy"][q]: bsum += d["sol"][q] / 1e9
        else: ssum += d["sol"][q] / 1e9; nsell += 1
        rows.append((q, m, pk, int(d["s"][q] - s0), 1 - m / pk, ssum, bsum, nsell))
    return rows

def features(d, rows):
    FI = d["FI"]; idx = np.array([r[0] for r in rows], np.int64)
    X = np.concatenate([d["F"][idx][:, [FI[f] for f in TF]].astype(float), np.array([r[1:] for r in rows], float)], axis=1)
    return idx, X

def binm(X, edges):
    B = np.zeros(X.shape, np.int16)
    for j, e in enumerate(edges):
        b = np.searchsorted(e, X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; B[:, j] = b
    return B

def predict(trees, lr, B):
    s = np.zeros(len(B))
    for t in trees: s += lr * G.pred(t, B)
    return s

def build_set(run):
    d = E.DAYS[run]; T = [t for t in json.load(open(f"{OUT}/trips_{run}.json")) if t["closed"] and t["sells"]]
    Xs = []; ys = []
    for t in T:
        rows = trip_rows(d, t)
        if not rows: continue
        idx, X = features(d, rows)
        ks = t["sells"][-1]["k"]
        y = np.zeros(len(rows));
        if d["s"][ks] - d["s"][idx[-1]] <= 2 and t["hold"] < 1380: y[-1] = 1        # timeouts are not decisions
        Xs.append(X); ys.append(y)
    return np.concatenate(Xs), np.concatenate(ys), T

def replica(d, t, lat, size_mode, trees, lr, edges, thr):
    """its entry re-timed to our landing; exit by our exit model (score >= thr) with a same-slot fill 35 ms after the trigger"""
    k0 = t["k0"]; a = k0 - int(d["F"][k0, d["FI"]["ntr"]]) + 1; end = int(d["tend"][k0])
    j = k0 - 1
    while j >= a and d["uid"][j] == UID: j -= 1
    if j < a or d["s"][k0] - d["s"][j] > 2: return None
    fr = float(d["fr"][k0])
    B = t["buys"][0]["sol"] * (1 + fr) if size_mode == "own" else 0.6
    ta = d["arr"][j] + lat; land = j + 1
    while land < end and (d["arr"][land] < ta or d["uid"][land] == UID): land += 1
    q = land - 1
    while q >= a and d["uid"][q] == UID: q -= 1
    Vb, Tb = float(d["vsol"][q]), float(d["vtok"][q])
    if Vb >= GRADV: return None
    if (Vb / Tb) / (float(d["vsol"][j]) / float(d["vtok"][j])) > GUARD: return dict(fail=1, pnl=-FAIL, B=B)
    X = B * 1e9 / (1 + fr); qt = Tb * X / (Vb + X); V = Vb + X; T = Tb - qt; p_in = X / qt
    s_land = int(ta // 212.0)
    # walk the path (its own trades removed), compute our position features on the fly, score in chunks
    path = [m for m in range(land, end) if d["uid"][m] != UID and d["s"][m] <= s_land + TOUT + 1]
    if not path:
        got = V * qt / (T + qt) * (1 - fr) / 1e9; return dict(fail=0, pnl=got - B - FIX, B=B, hold=0, why="end")
    # first pass: our curve after each trade (follower limits)
    Vs = []; Ts = []; keep = []
    for m in path:
        if d["buy"][m]:
            sol = float(d["sol"][m]); dt = T * sol / (V + sol)
            if dt < float(d["tokn"][m]) / (1.0 + float(d["slack"][m])): Vs.append(V); Ts.append(T); keep.append(False); continue
            V += sol; T -= dt
        else:
            tk = float(d["tokn"][m]); so = V * tk / (T + tk); V -= so; T += tk
        Vs.append(V); Ts.append(T); keep.append(True)
        if V >= GRADV: break
    path = path[:len(Vs)]
    pk = 1.0; ssum = bsum = 0.0; nsell = 0; rows = []
    for n, m in enumerate(path):
        price = Vs[n] / Ts[n]; mlt = price / p_in; pk = max(pk, mlt)
        if keep[n]:
            if d["buy"][m]: bsum += d["sol"][m] / 1e9
            else: ssum += d["sol"][m] / 1e9; nsell += 1
        rows.append((m, mlt, pk, int(d["s"][m] - s_land), 1 - mlt / pk, ssum, bsum, nsell))
    idx, Xf = features(d, rows)
    sc = predict(trees, lr, binm(Xf, edges))
    hit = np.flatnonzero((sc >= thr) & (np.array([r[3] for r in rows]) >= 0))
    if len(hit):
        n = int(hit[0]); m = path[n]; ta2 = d["arr"][m] + lat
        # our sell lands after the trades that arrive before ta2
        nn = n
        while nn + 1 < len(path) and d["arr"][path[nn + 1]] < ta2: nn += 1
        Vx, Tx = Vs[nn], Ts[nn]; hold = int(d["s"][m] - s_land); why = "model"
    else:
        # timeout: last state at or before s_land + TOUT
        nn = len(path) - 1
        while nn > 0 and d["s"][path[nn]] > s_land + TOUT: nn -= 1
        Vx, Tx = Vs[nn], Ts[nn]; hold = TOUT; why = "timeout"
    got = Vx * qt / (Tx + qt) * (1 - fr) / 1e9
    return dict(fail=0, pnl=got - B - FIX, B=B, hold=hold, why=why)

if __name__ == "__main__":
    days = ["R2", "R3", "R1"]
    E.load(days)
    X2, y2, T2 = build_set("R2")
    rng = np.random.default_rng(5); tr = rng.random(len(y2)) < 0.8
    edges = [np.unique(np.quantile(X2[tr, j][~np.isnan(X2[tr, j])], np.linspace(0, 1, 33)[1:-1])) for j in range(X2.shape[1])]
    B2 = binm(X2, edges)
    trees, f = G.fit(B2, y2, tr, ~tr, rounds=400, lr=0.08, depth=4, seed=2)
    gains = np.zeros(X2.shape[1])
    for t in trees: G.imp(t, gains)
    names = TF + PF; order = np.argsort(-gains)
    print(f"exit model: R2 rows {len(y2)}, exits {int(y2.sum())}; trees {len(trees)}; R2 holdout AUC {G.auc(y2[~tr], f[~tr]):.3f}")
    print("top exit features:", [(names[j], round(float(gains[j] / gains.sum()), 3)) for j in order[:14]])
    out = dict(features=[(names[j], round(float(gains[j] / gains.sum()), 4)) for j in order], auc={})
    for run in ("R3", "R1"):
        X, y, _ = build_set(run); s = predict(trees, 0.08, binm(X, edges)); out["auc"][run] = round(G.auc(y, s), 3)
        print(f"{run}: exit AUC {out['auc'][run]}")
    json.dump(dict(edges=[e.tolist() for e in edges], trees=trees, lr=0.08, names=names), open(f"{OUT}/exit_model_trees.json", "w"))
    json.dump(dict(edges=[e.tolist() for e in edges], trees=trees, lr=0.08, names=names, thr={str(q): float(np.quantile(f, q)) for q in (0.95, 0.97, 0.98, 0.99, 0.995)}), open(f"{OUT}/exit_model_trees.json", "w"))
    json.dump(out, open(f"{OUT}/exit_model.json", "w"), indent=1)

#!/usr/bin/env python3
# sssssDdM EXIT MODEL (read-only; adapted from bukp/bk7_exit.py, not modified). While it holds, every NON-FLEET trade is an
# exit decision point; label 1 = the last non-fleet trade before its sell (sell <= 2 slots later), 0 = it kept holding.
# Features = causal token features at that trade + position features (price vs its entry fill, peak since entry, slots
# held, drawdown from peak, other-wallet sell / buy SOL and sell count since entry). Sibling (ssssswdk) trades are NOT
# features (they are the operator's own co-exit, not observable before our decision). numpy GBDT trained on R2, tested on
# R3/R1 (AUC). Then the REPLICA: its own entries re-timed to OUR landing (35 / 50 ms after its trigger, +5% guard, size
# 1.88% of curve capped 0.35-0.75 SOL), our exit = first trade whose exit score >= threshold (chosen on R2) or 3,000 slots;
# our sell lands after the trades arriving within our latency after that trade; follower slippage limits; our costs.
# -> sssss/exit_model.json, sssss/exit_model_trees.json
import sys, json, zlib
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import p4_eval as E
import gbdt_np as G
OUT = "/home/moiz/sniper-data/strategies/sssss"
UID = zlib.crc32(b"sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d")
SIBS = ["ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E", "sssssCUP5wgSW3sxjtQNa7u88ytE4st2Z7goX5kKNwi", "sssssyv2q57u9sJrL1BB7Ep71X6YBY71iYt7CtHB5zJ"]
FLEET = np.array([UID] + [zlib.crc32(s.encode()) for s in SIBS], np.int64)
TF = ["ev_buy", "sol", "move", "wt", "age", "curve", "ath_r", "ret1", "ret3", "ret10", "ret30", "nb1", "ns1", "bsol1", "ssol1", "nb3", "ns3", "bsol3", "ssol3", "net3", "nw3",
      "bigs3", "maxs3", "dd3", "nb10", "ns10", "bsol10", "ssol10", "net10", "bigs10", "dd10", "fam_s10", "fam_b10", "dev_s30", "ins_s30", "nbot_hold", "fam_hold", "hour"]
PF = ["mult", "peak", "held", "dd_peak", "sell_since", "buy_since", "n_sell_since"]
FIX = 0.0035; FAIL = 0.0005; GUARD = 1.05; GRADV = 113e9; TOUT = 3000

def trip_rows(d, t, isfleet):
    k0 = t["k0"]; ks = t["sells"][-1]["k"]; s0 = d["s"][k0]; p_in = t["p_in"]
    rows = []; pk = 1.0; ssum = bsum = 0.0; nsell = 0
    for q in range(k0 + 1, ks):
        if isfleet[q]: continue
        m = float(d["vsol"][q] / d["vtok"][q]) / p_in; pk = max(pk, m)
        if d["buy"][q]: bsum += d["sol"][q] / 1e9
        else: ssum += d["sol"][q] / 1e9; nsell += 1
        rows.append((q, m, pk, int(d["s"][q] - s0), 1 - m / pk, ssum, bsum, nsell))
    return rows

def features(d, rows):
    FI = d["FI"]; idx = np.array([r[0] for r in rows], np.int64)
    return idx, np.concatenate([d["F"][idx][:, [FI[f] for f in TF]].astype(float), np.array([r[1:] for r in rows], float)], axis=1)

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
    d = E.DAYS[run]; isfleet = np.isin(d["uid"], FLEET)
    T = [t for t in json.load(open(f"{OUT}/trips_{run}.json")) if t["closed"] and t["sells"]]
    Xs = []; ys = []
    for t in T:
        rows = trip_rows(d, t, isfleet)
        if not rows: continue
        idx, X = features(d, rows); ks = t["sells"][-1]["k"]
        y = np.zeros(len(rows))
        if d["s"][ks] - d["s"][idx[-1]] <= 2: y[-1] = 1
        Xs.append(X); ys.append(y)
    return np.concatenate(Xs), np.concatenate(ys), T

def replica(d, t, lat, trees, lr, edges, thrs, isfleet):
    k0 = t["k0"]; a = k0 - int(d["F"][k0, d["FI"]["ntr"]]) + 1; end = int(d["tend"][k0])
    j = k0 - 1
    while j >= a and isfleet[j]: j -= 1
    if j < a or d["s"][k0] - d["s"][j] > 2: return None
    fr = float(d["fr"][k0])
    ta = d["arr"][j] + lat; land = j + 1
    while land < end and (d["arr"][land] < ta or d["uid"][land] == UID): land += 1
    q = land - 1
    while q >= a and d["uid"][q] == UID: q -= 1
    Vb, Tb = float(d["vsol"][q]), float(d["vtok"][q])
    if Vb >= GRADV: return None
    if (Vb / Tb) / (float(d["vsol"][j]) / float(d["vtok"][j])) > GUARD: return {q: dict(fail=1, pnl=-FAIL, B=0.5) for q in thrs}
    B = min(max(0.0188 * Vb / 1e9, 0.35), 0.75)
    X = B * 1e9 / (1 + fr); qt = Tb * X / (Vb + X); V = Vb + X; T = Tb - qt; p_in = X / qt
    s_land = int(ta // 212.0)
    path = [m for m in range(land, end) if d["uid"][m] != UID and d["s"][m] <= s_land + TOUT + 1]
    if not path:
        got = V * qt / (T + qt) * (1 - fr) / 1e9; return {q: dict(fail=0, pnl=got - B - FIX, B=B, hold=0, why="end") for q in thrs}
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
    pk = 1.0; ssum = bsum = 0.0; nsell = 0; rows = []; ridx = []
    for n, m in enumerate(path):
        mlt = (Vs[n] / Ts[n]) / p_in; pk = max(pk, mlt)
        if keep[n] and not isfleet[m]:
            if d["buy"][m]: bsum += d["sol"][m] / 1e9
            else: ssum += d["sol"][m] / 1e9; nsell += 1
        if isfleet[m]: continue
        rows.append((m, mlt, pk, int(d["s"][m] - s_land), 1 - mlt / pk, ssum, bsum, nsell)); ridx.append(n)
    sc = predict(trees, lr, binm(features(d, rows)[1], edges)) if rows else np.zeros(0)
    out = {}
    for q, thr in thrs.items():
        hit = np.flatnonzero(sc >= thr)
        if len(hit):
            n = ridx[int(hit[0])]; m = path[n]; ta2 = d["arr"][m] + lat; nn = n
            while nn + 1 < len(path) and d["arr"][path[nn + 1]] < ta2: nn += 1
            Vx, Tx = Vs[nn], Ts[nn]; hold = int(d["s"][m] - s_land); why = "model"
        else:
            nn = len(path) - 1
            while nn > 0 and d["s"][path[nn]] > s_land + TOUT: nn -= 1
            Vx, Tx = Vs[nn], Ts[nn]; hold = TOUT; why = "timeout"
        got = Vx * qt / (Tx + qt) * (1 - fr) / 1e9
        out[q] = dict(fail=0, pnl=got - B - FIX, B=B, hold=hold, why=why)
    return out

def rep_task(args):
    run, lat = args
    d = E.DAYS[run]; isfleet = np.isin(d["uid"], FLEET); M = G_["M"]
    T = [t for t in json.load(open(f"{OUT}/trips_{run}.json")) if t["closed"] and t["sells"]]
    res = {}
    rs = [replica(d, t, lat, M["trees"], 0.08, M["edges"], G_["thrs"], isfleet) for t in T]
    rs = [r for r in rs if r]
    for q in G_["thrs"]:
        x = [r[q] for r in rs]; p = [r["pnl"] for r in x]; srt = sorted(p)
        res[f"q{q}|{run}|{lat}"] = dict(n=len(x), pnl=round(sum(p), 2), mean=round(float(np.mean(p)), 4), win=round(float(np.mean([v > 0 for v in p])), 3),
                                       wo_top1=round(sum(srt[:-max(1, len(srt) // 100)]), 2), hold_med=float(np.median([r["hold"] for r in x if not r.get("fail")])),
                                       timeouts=sum(1 for r in x if r.get("why") == "timeout"), fails=sum(1 for r in x if r.get("fail")),
                                       pnl_lowfee=round(sum(p) + 0.00325 * sum(1 for r in x if not r.get("fail")), 2))
    return res

G_ = {}
if __name__ == "__main__":
    import os
    from multiprocessing import get_context
    days = ["R2", "R3", "R1"]
    E.load(days)
    if os.path.exists(f"{OUT}/exit_model_trees.json") and os.environ.get("REFIT") != "1":
        M = json.load(open(f"{OUT}/exit_model_trees.json")); M["edges"] = [np.array(e) for e in M["edges"]]
        out = json.load(open(f"{OUT}/exit_model.json")) if os.path.exists(f"{OUT}/exit_model.json") else {}
        X2, y2, T2 = build_set("R2"); f = predict(M["trees"], 0.08, binm(X2, M["edges"]))
    else:
        X2, y2, T2 = build_set("R2")
        rng = np.random.default_rng(5); tr = rng.random(len(y2)) < 0.8
        edges = [np.unique(np.quantile(X2[tr, j][~np.isnan(X2[tr, j])], np.linspace(0, 1, 33)[1:-1])) for j in range(X2.shape[1])]
        trees, f = G.fit(binm(X2, edges), y2, tr, ~tr, rounds=400, lr=0.08, depth=4, seed=2)
        gains = np.zeros(X2.shape[1])
        for t in trees: G.imp(t, gains)
        names = TF + PF; order = np.argsort(-gains)
        print(f"exit model: R2 rows {len(y2)}, exits {int(y2.sum())}; trees {len(trees)}; R2 holdout AUC {G.auc(y2[~tr], f[~tr]):.3f}", flush=True)
        out = dict(features=[(names[j], round(float(gains[j] / gains.sum()), 4)) for j in order], auc={})
        for run in ("R3", "R1"):
            X, y, _ = build_set(run); s_ = predict(trees, 0.08, binm(X, edges)); out["auc"][run] = round(G.auc(y, s_), 3)
            print(f"{run}: exit AUC {out['auc'][run]}", flush=True)
        json.dump(dict(edges=[e.tolist() for e in edges], trees=trees, lr=0.08, names=names), open(f"{OUT}/exit_model_trees.json", "w"))
        M = dict(edges=edges, trees=trees)
    G_["M"] = M
    G_["thrs"] = {q: float(np.quantile(f, q)) for q in (0.95, 0.97, 0.98, 0.99, 0.995)}
    res = {}
    with get_context("fork").Pool(int(os.environ.get("PROCS", "3"))) as p:
        for r in p.imap_unordered(rep_task, [(run, lat) for run in days for lat in (35, 50)]): res.update(r)
    for q in G_["thrs"]:
        print(f"thr q{q}: " + " | ".join(f"{run} 35ms {res[f'q{q}|{run}|35']['pnl']:+.1f} (mean {res[f'q{q}|{run}|35']['mean']:+.4f}, hold {res[f'q{q}|{run}|35']['hold_med']:.0f}, w/o top1% {res[f'q{q}|{run}|35']['wo_top1']:+.1f}, lowfee {res[f'q{q}|{run}|35']['pnl_lowfee']:+.1f}); 50ms {res[f'q{q}|{run}|50']['pnl']:+.1f}" for run in days), flush=True)
    out["replica"] = res; out["thr"] = G_["thrs"]
    json.dump(out, open(f"{OUT}/exit_model.json", "w"), indent=1)

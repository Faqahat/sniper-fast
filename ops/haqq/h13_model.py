#!/usr/bin/env python3
# haqq SELL study, step 13: slot hazard model of its first sell per lot (dip lots). TRAIN = R1+R2 (10-22 03:09 -> 10-23 18:31 PKT),
# TEST = R3 (10-23 19:28 -> 10-24 20:20 PKT), FORWARD = R4 (10-24 20:20 -> 10-25 06:15 PKT; R4 lots before R3's end excluded).
# Models: TIMER (slot / profile / size only) vs FULL (+ price, flow, entry). Match rates of the predicted exit slot.
import sys, json, collections, numpy as np, pickle
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H, h_gbdt as G
Z = np.load(f"{H.OUT}/ds.npz"); X, y, L, D, RUN = Z["X"], Z["y"].astype(float), Z["L"], Z["d"], Z["run"]
M = json.load(open(f"{H.OUT}/ds_meta.json")); F = M["feats"]; FI = {k: i for i, k in enumerate(F)}
lots = json.load(open(f"{H.OUT}/lots.json"))
tr = (RUN == 1) | (RUN == 2); te = RUN == 3; fw = RUN == 4
rng = np.random.default_rng(0)
ul = np.unique(L[tr]); va_l = set(rng.choice(ul, int(len(ul) * 0.15), replace=False).tolist())
va = tr & np.isin(L, list(va_l)); trn = tr & ~va
TIMER = ["d", "d_buy", "dmod8", "dmod5", "prof", "size"]
def fitm(cols, rounds=500, depth=4):
    idx = [FI[c] for c in cols]
    B = G.binize(X[:, idx], trn)
    trees, f = G.fit(B, y, trn, va, rounds=rounds, lr=0.08, depth=depth)
    p = 1 / (1 + np.exp(-f))
    imp = np.zeros(len(idx))
    for t in trees: G.imp(t, imp)
    return p, dict(zip(cols, (imp / imp.sum()).round(3).tolist())), len(trees)
res = {}
for name, cols in (("TIMER", TIMER), ("FULL", F)):
    p, imp, nt = fitm(cols)
    ll = lambda m: float(-np.mean(y[m] * np.log(np.clip(p[m], 1e-7, 1)) + (1 - y[m]) * np.log(np.clip(1 - p[m], 1e-7, 1))))
    res[name] = p
    print(f"{name}: trees {nt}; logloss TRAIN {ll(trn):.4f} VAL {ll(va):.4f} TEST {ll(te):.4f} FWD {ll(fw):.4f} | AUC TEST {G.auc(y[te], p[te]):.3f} FWD {G.auc(y[fw], p[fw]):.3f}")
    print("   importance:", sorted(imp.items(), key=lambda kv: -kv[1])[:14])
np.savez(f"{H.OUT}/h13_pred.npz", TIMER=res["TIMER"], FULL=res["FULL"])
# ---------- predicted exit per lot and match rates
def per_lot(p, mask):
    out = {}
    idx = np.flatnonzero(mask)
    order = np.lexsort((D[idx], L[idx])); idx = idx[order]
    cur = None; seq = []
    for r in idx.tolist():
        if L[r] != cur:
            if cur is not None: out[cur] = seq
            cur = L[r]; seq = []
        seq.append((int(D[r]), float(p[r]), int(y[r])))
    if cur is not None: out[cur] = seq
    return out
def pred_exit(seq, how, tau):
    S = 1.0; best = (-1, None); cum = 0.0
    for d, h, _ in seq:
        if how == "thr" and h >= tau: return d
        pm = S * h
        if how == "mode" and pm > best[0]: best = (pm, d)
        cum += pm
        if how == "med" and cum >= tau: return d
        S *= (1 - h)
    if how == "mode": return best[1]
    return seq[-1][0] + 1 if seq else None
def match(seqs, how, tau):
    c = np.zeros(4); n = 0
    for li, seq in seqs.items():
        act = lots[li]["sells"][0]["s"] - (lots[li]["buy"]["s"] - lots[li]["buy"]["trig_ds"])
        pr = pred_exit(seq, how, tau)
        if pr is None: continue
        n += 1; e = abs(pr - act)
        c += [e == 0, e <= 1, e <= 2, e <= 5]
    return c / max(n, 1), n
for name in ("TIMER", "FULL"):
    p = res[name]
    S_tr = per_lot(p, tr); S_te = per_lot(p, te); S_fw = per_lot(p, fw)
    best = None
    for how, taus in (("thr", (0.05, 0.08, 0.1, 0.12, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5)), ("med", (0.3, 0.4, 0.5, 0.6, 0.7)), ("mode", (0,))):
        for tau in taus:
            m, n = match(S_tr, how, tau)
            if best is None or m[1] > best[0][1]: best = (m, how, tau)
    m_tr, how, tau = best
    m_te, n_te = match(S_te, how, tau); m_fw, n_fw = match(S_fw, how, tau)
    print(f"\n{name} exit rule = {how} tau {tau} (chosen on TRAIN): exact / +-1 / +-2 / +-5 slots")
    print(f"   TRAIN {' / '.join(f'{x:.0%}' for x in m_tr)} | TEST (R3, n {n_te}) {' / '.join(f'{x:.0%}' for x in m_te)} | FWD (R4, n {n_fw}) {' / '.join(f'{x:.0%}' for x in m_fw)}")

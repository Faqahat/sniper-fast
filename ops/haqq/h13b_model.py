#!/usr/bin/env python3
# haqq SELL study, step 13b: hazard models of each dip lot's FIRST sell + honest exit-slot match rates.
# TRAIN = R1+R2 lots (10-22 03:09 -> 10-23 18:31 PKT); TEST = R3 lots (10-23 19:28 -> 10-24 20:20); FWD = R4 lots (10-24 20:20 -> 10-25 06:15).
# Training rows stop at the real exit; evaluation rows continue to exit+12 slots, so a rule that never fires is a miss.
# Models: TIMER (slot count / profile / size), FULL (+ price, flow, entry). Baselines: fixed hold, TP/SL/time, stall, checkpoint rule.
import sys, json, pickle, collections, itertools, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H, h_gbdt as G
M = json.load(open(f"{H.OUT}/ds_meta.json")); F = M["feats"]; FI = {k: i for i, k in enumerate(F)}
Z = np.load(f"{H.OUT}/ds.npz"); X, y, L, RUN = Z["X"], Z["y"].astype(float), Z["L"], Z["run"]
E = np.load(f"{H.OUT}/ds_eval.npz"); XE, yE, LE, DE, RUNE = E["X"], E["y"], E["L"], E["d"], E["run"]
lots = json.load(open(f"{H.OUT}/lots.json"))
tr = (RUN == 1) | (RUN == 2)
rng = np.random.default_rng(0)
ul = np.unique(L[tr]); va_l = rng.choice(ul, int(len(ul) * 0.15), replace=False)
va = tr & np.isin(L, va_l); trn = tr & ~va
keep = (y == 1) | (rng.random(len(y)) < 0.35); w = np.where(y == 1, 1.0, 1 / 0.35)
trn_s = trn & keep
TIMER = ["d", "d_buy", "dmod8", "dmod5", "prof", "size"]
MODELS = {}
for name, cols in (("TIMER", TIMER), ("FULL", F)):
    idx = [FI[c] for c in cols]
    edges = G.binize_edges(X[:, idx], trn)
    B = G.apply_edges(X[:, idx], edges)
    trees, F0 = G.fit_w(B, y, w, trn_s, va, rounds=400, lr=0.1, depth=4, patience=40)
    BE = G.apply_edges(XE[:, idx], edges)
    pE = G.predict(trees, F0, BE, 0.1)
    imp = np.zeros(len(idx))
    for t in trees: G.imp(t, imp)
    MODELS[name] = dict(cols=cols, edges=edges, trees=trees, F0=F0, lr=0.1)
    m_te = RUNE == 3; m_fw = RUNE == 4
    print(f"{name}: trees {len(trees)} | AUC eval-rows TEST {G.auc(yE[m_te].astype(float), pE[m_te]):.3f} FWD {G.auc(yE[m_fw].astype(float), pE[m_fw]):.3f}", flush=True)
    print("   importance:", sorted(zip(cols, (imp / imp.sum()).round(3)), key=lambda kv: -kv[1])[:12], flush=True)
    MODELS[name]["pE"] = pE
pickle.dump({k: {kk: vv for kk, vv in v.items() if kk != "pE"} for k, v in MODELS.items()}, open(f"{H.OUT}/h13b_models.pkl", "wb"))
# ---- per-lot sequences on eval rows
o = np.lexsort((DE, LE)); LE_, DE_ = LE[o], DE[o]
starts = np.flatnonzero(np.r_[True, LE_[1:] != LE_[:-1]]); ends = np.r_[starts[1:], len(LE_)]
LOT = [(int(LE_[a]), a, b) for a, b in zip(starts, ends)]
def actual(li): return lots[li]["sells"][0]["s"] - (lots[li]["buy"]["s"] - lots[li]["buy"]["trig_ds"])
ACT = {li: actual(li) for li, _, _ in LOT}
RUNL = {li: lots[li]["run"] for li, _, _ in LOT}
XEo = XE[o]
def pred_from_h(h, d, how, tau):
    if how == "thr":
        j = np.flatnonzero(h >= tau)
        return int(d[j[0]]) if len(j) else None
    S = np.cumprod(np.r_[1.0, 1 - h[:-1]]); pm = S * h
    if how == "mode": return int(d[np.argmax(pm)]) if len(pm) and pm.max() > 0.05 else None
    cum = np.cumsum(pm); j = np.flatnonzero(cum >= tau)
    return int(d[j[0]]) if len(j) else None
def rates(preds, sel):
    c = np.zeros(4); n = 0
    for li in sel:
        pr = preds.get(li); a = ACT[li]; n += 1
        if pr is None: continue
        e = abs(pr - a); c += [e == 0, e <= 1, e <= 2, e <= 5]
    return c / max(n, 1), n
SETS = {"TRAIN": [li for li, _, _ in LOT if RUNL[li] in ("R1", "R2")], "TEST": [li for li, _, _ in LOT if RUNL[li] == "R3"], "FWD": [li for li, _, _ in LOT if RUNL[li] == "R4"]}
PRED = {}
def show(name, preds):
    out = []
    for k in ("TRAIN", "TEST", "FWD"):
        r, n = rates(preds, SETS[k]); out.append(f"{k} {' / '.join(f'{x:.0%}' for x in r)} (n {n})")
    print(f"{name:34s} exact / +-1 / +-2 / +-5:  " + " | ".join(out), flush=True)
for name in ("TIMER", "FULL"):
    pE = MODELS[name]["pE"][o]
    best = None
    for how, taus in (("thr", (0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6)), ("med", (0.3, 0.4, 0.5, 0.6)), ("mode", (0,))):
        for tau in taus:
            preds = {li: pred_from_h(pE[a:b], DE_[a:b], how, tau) for li, a, b in LOT if RUNL[li] in ("R1", "R2")}
            r, _ = rates(preds, SETS["TRAIN"])
            if best is None or r[1] > best[0]: best = (r[1], how, tau)
    _, how, tau = best
    preds = {li: pred_from_h(pE[a:b], DE_[a:b], how, tau) for li, a, b in LOT}
    PRED[name] = preds; show(f"{name} model ({how} {tau})", preds)
# ---- baselines (rules chosen on TRAIN by +-1 match)
def rule_preds(fn):
    out = {}
    for li, a, b in LOT:
        Xl = XEo[a:b]; dl = DE_[a:b]; out[li] = None
        for r_, d in zip(Xl, dl):
            if fn(r_, int(d)): out[li] = int(d); break
    return out
def pick(cands, label):
    best = None
    for params, fn in cands:
        p = rule_preds(fn); r, _ = rates(p, SETS["TRAIN"])
        if best is None or r[1] > best[0]: best = (r[1], params, p)
    PRED[label] = best[2]; show(f"{label} {best[1]}", best[2]); return best[1]
pf = FI["prof"]; dd = FI["d"]
# fixed hold per profile
fix_best = {}
for pid in range(8):
    sel = [li for li in SETS["TRAIN"] if XEo[[a for l_, a, b in LOT if l_ == li][0], pf] == pid] if False else None
H_ = {}
cnt = collections.defaultdict(collections.Counter)
for li, a, b in LOT:
    if RUNL[li] in ("R1", "R2"): cnt[int(XEo[a, pf])][ACT[li]] += 1
for pid, c in cnt.items():
    sc = {h: c[h - 1] + c[h] + c[h + 1] for h in range(1, 300)}
    H_[pid] = max(sc, key=sc.get)
print("fixed hold per profile id (TRAIN best):", H_)
PRED["FIXED"] = {li: max(H_.get(int(XEo[a, pf]), 20), int(DE_[a])) for li, a, b in LOT}; show("FIXED per-profile hold", PRED["FIXED"])
ri = FI["ret"]; sb = FI["since_b"]
pick([((tp, sl, T), (lambda tp, sl, T: (lambda r, d: r[ri] >= tp or r[ri] <= -sl or d >= T))(tp, sl, T))
      for tp, sl, T in itertools.product((0.1, 0.2, 0.3, 0.5, 9), (0.1, 0.2, 0.3, 9), (10, 15, 20, 25, 30, 40, 65))], "TP/SL/TIME (tp, sl, T)")
pick([((g, T), (lambda g, T: (lambda r, d: r[sb] >= g or d >= T))(g, T)) for g, T in itertools.product((2, 3, 4, 6, 8, 12, 16), (20, 30, 40, 65, 100))], "STALL (no >=0.1 buy for g slots, cap T)")
CP8 = {9, 17, 25, 33, 41, 49, 57, 65}; CP5 = {10, 12, 15, 20, 25, 30, 40, 50, 60, 65}
FAM = {0: CP8, 2: CP8, 5: CP8, 1: CP5, 3: CP5}
def cp_rule(g, tp, tpd, cap5, cap8):
    def fn(r, d):
        p = int(r[pf]); cps = FAM.get(p)
        if p == 4: return d >= 3 and (r[ri] >= tp or d >= 20)
        if cps is None: return d >= 65
        if r[ri] >= tp and d <= tpd: return True
        if d in cps and r[sb] >= g: return True
        return d >= (cap8 if cps is CP8 else cap5)
    return fn
pick([((g, tp, tpd, c5, c8), cp_rule(g, tp, tpd, c5, c8)) for g, tp, tpd, c5, c8 in itertools.product((1, 2, 3, 4, 6, 8), (0.2, 0.3, 0.5, 9), (8, 15), (60, 65), (65,))],
     "CHECKPOINT RULE (quiet g, tp, tp_until, caps)")
pickle.dump(dict(PRED=PRED, ACT=ACT, RUNL=RUNL), open(f"{H.OUT}/h13b_preds.pkl", "wb"))

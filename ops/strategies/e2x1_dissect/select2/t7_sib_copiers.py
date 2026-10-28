#!/usr/bin/env python3
"""select2 t7: (1) Is Grozoe2L's selection the same rule? event-level overlap, E2x1-model transfer to Grozoe-only picks,
feature-distribution comparison. (2) Do the copier wallets filter? For each E2x1 buy (universe positives), did copier c buy on
the mint within 2 slots after him; model 'copier followed' from the event features (AUC ~0.5 => no filter)."""
import sys, json, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect"); import dd_gbdt as G
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select2"); from lib import *
t0 = time.time()
U = dict(np.load(f"{OUT}/U2.npz")); MN, US = names()
tmax = int(U["bt"].max()); TCUT = tmax - 86400; VCUT = TCUT - 12 * 3600
TE = U["bt"] >= TCUT; VA = (U["bt"] >= VCUT) & ~TE; TR = ~TE & ~VA
y = U["y"].astype(bool); ys = U["ysib"].astype(bool); samp = U["samp"].astype(bool)
out = {}
# ---- (1a) event overlap ----
out["events"] = dict(e2x1=int(y.sum()), sib=int(ys.sum()), both=int((y & ys).sum()), sib_only=int((ys & ~y).sum()), e2x1_only=int((y & ~ys).sum()),
                     sib_is_trigger_of_e2x1=int((y & (U["u_is_sib"] > 0)).sum()))
# mint-level: tokens
my = set(U["mint"][y].tolist()); ms = set(U["mint"][ys].tolist()); out["mints"] = dict(e2x1=len(my), sib=len(ms), both=len(my & ms))
# ---- (1b) model transfer: fit on y (train rows: samp|y), score sib-only picks on TEST ----
import os
s = np.full(len(y), np.nan)
if os.path.exists(f"{OUT}/t6_scores_main.npz"): SC = np.load(f"{OUT}/t6_scores_main.npz"); s[SC["rows"]] = SC["s"]
def wauc(sc, pos, neg, w):
    a = sc[pos]; b = sc[neg]; wb = w[neg]; o = np.argsort(b); b = b[o]; wb = wb[o]; cw = np.cumsum(wb)
    k = np.searchsorted(b, a, side="left"); return float((cw[np.maximum(k - 1, 0)] * (k > 0)).sum() / (len(a) * cw[-1]))
w = np.where(y, 1.0, 25.0)
neg = samp & ~y & ~ys & TE & np.isfinite(s)
if neg.any(): out["transfer_auc_test"] = dict(e2x1_picks=wauc(s, y & TE & np.isfinite(s), neg, w), sib_only_picks=wauc(s, ys & ~y & TE & np.isfinite(s), neg, w) if (ys & ~y & TE & np.isfinite(s)).any() else None,
                                both=wauc(s, y & ys & TE & np.isfinite(s), neg, w))
# score quantiles
for nm, m in (("e2x1_only", y & ~ys & TE), ("both", y & ys & TE), ("sib_only", ys & ~y & TE), ("neg", neg)):
    v = s[m & np.isfinite(s)]; out[f"score_q_{nm}"] = np.quantile(v, [0.1, 0.25, 0.5, 0.75, 0.9]).round(3).tolist() if len(v) else None
# ---- (1c) feature comparison ----
KEYF = ["age_s", "is_buy", "sol", "imp", "vsol", "u_follow_rate_sm", "u_ntr", "u_trips", "u_ret_per_sol", "u_cw541", "tx_cup", "tx_relay", "tx_f_routed", "n_cw_in", "my_buys", "hour", "cr_prev", "dev_buy0", "bundle_n0"]
cmp_ = {}
for f in KEYF:
    cmp_[f] = {nm: [float(np.nanmedian(U[f][m])), float(np.nanmean(U[f][m]))] for nm, m in (("e2x1_only", y & ~ys), ("both", y & ys), ("sib_only", ys & ~y), ("neg", samp & ~y & ~ys))}
out["feature_medians_means"] = cmp_
# sib-only vs e2x1-only separability (can a model tell their picks apart?)
rows = (y | ys)
FE = [k for k in U if k not in ("row", "y", "ysib", "samp", "mint", "slot", "idx", "bt", "user", "nxt_row", "nxt_sib", "sigh", "lp", "vt", "seg_a", "u_is_sib", "sib_buys", "sib_open", "sib_trades_60", "u_sibfollow_n") and not k.startswith(("f", "g"))]
X = np.column_stack([np.nan_to_num(U[f].astype(np.float64), nan=0, posinf=1e9, neginf=-1e9) for f in FE])[rows]
lab = (ys & ~y)[rows].astype(float); tr = TR[rows]; va = VA[rows]; te = TE[rows]
E = G.edges_of(X, tr); B = G.binize(X, E); M = G.fit(B, lab, tr, va, loss="log", rounds=300, lr=0.08, depth=4, min_n=100, lam=5.0, seed=3, patience=40)
sc = G.predict(M, B); imp = G.importance(M, len(FE))
o = np.argsort(sc[te]); r = np.empty(te.sum()); r[o] = np.arange(1, te.sum() + 1); p = lab[te].sum(); n_ = te.sum() - p
out["sib_only_vs_e2x1_auc_test"] = float((r[lab[te] == 1].sum() - p * (p + 1) / 2) / (p * n_)) if p and n_ else None
out["sib_only_vs_e2x1_top_feats"] = sorted(zip(FE, imp.round(4).tolist()), key=lambda z: -z[1])[:12]
print(json.dumps({k: v for k, v in out.items() if k != "feature_medians_means"}, default=float), flush=True)
# ---- (2) copiers ----
D = load(); sl = D["slot"].astype(np.int64); us = D["user"].astype(np.int64); bu = D["buy"].astype(bool); mi = D["mint"].astype(np.int64)
uid = {u: i for i, u in enumerate(US)}
cops = {p: [u for u in US if u.startswith(p)] for p in ("4mYySb7Z", "Hj4uACn8", "2QGfyorL", "8T4XX", "6nH3j")}
cops = {p: v[0] for p, v in cops.items() if len(v) == 1}
print("copiers", cops)
pos = np.flatnonzero(y); his_rows = U["nxt_row"][pos]; m_ = mi[his_rows]; s_ = sl[his_rows]
cres = {}
Xp = np.column_stack([np.nan_to_num(U[f].astype(np.float64), nan=0, posinf=1e9, neginf=-1e9) for f in FE])[pos]
# his buy size and whether it is a first buy
for p, u in cops.items():
    ci = uid[u]; crow = np.flatnonzero((us == ci) & bu); ck = (mi[crow] << 32) | (sl[crow] - sl.min())
    ck.sort()
    lo = np.searchsorted(ck, (m_ << 32) | (s_ - sl.min())); hi = np.searchsorted(ck, (m_ << 32) | (s_ - sl.min() + 2), side="right")
    fol = (hi > lo)
    d = dict(wallet=u, n_his_buys=int(len(pos)), followed=int(fol.sum()), rate=float(fol.mean()))
    # by his buy context
    for nm, m in (("first_buy", U["my_buys"][pos] == 0), ("re_entry", U["my_buys"][pos] > 0), ("age<30", U["age_s"][pos] < 30), ("age>=120", U["age_s"][pos] >= 120), ("test_day", TE[pos])):
        d["rate_" + nm] = float(fol[m].mean()) if m.any() else None
    # model: can features predict which of his buys the copier follows? (time split)
    lab = fol.astype(float); trp = TR[pos]; vap = VA[pos]; tep = TE[pos]
    if lab[trp].sum() > 50 and lab[tep].sum() > 10 and (1 - lab[tep]).sum() > 10:
        E = G.edges_of(Xp, trp); B = G.binize(Xp, E); M = G.fit(B, lab, trp, vap, loss="log", rounds=200, lr=0.08, depth=3, min_n=50, lam=5.0, seed=4, patience=30)
        sc = G.predict(M, B); o = np.argsort(sc[tep]); r = np.empty(tep.sum()); r[o] = np.arange(1, tep.sum() + 1); pp = lab[tep].sum(); nn = tep.sum() - pp
        d["follow_model_auc_test"] = float((r[lab[tep] == 1].sum() - pp * (pp + 1) / 2) / (pp * nn)); imp = G.importance(M, len(FE))
        d["follow_top_feats"] = sorted(zip(FE, imp.round(4).tolist()), key=lambda z: -z[1])[:8]
        # active-time control: follow rate when the copier traded anything in the last 5 min (is 'not following' just downtime?)
    cb = np.sort(D["bt"][crow]); act = (np.searchsorted(cb, U["bt"][pos]) - np.searchsorted(cb, U["bt"][pos] - 300)) > 0
    d["rate_when_active_5min"] = float(fol[act].mean()) if act.any() else None; d["share_active"] = float(act.mean())
    # size: copier's buy SOL vs his
    cres[p] = d; print(p, json.dumps(d, default=float), flush=True)
out["copiers"] = cres
json.dump(out, open(f"{OUT}/t7.json", "w"), indent=1, default=float); print("done", time.time() - t0)

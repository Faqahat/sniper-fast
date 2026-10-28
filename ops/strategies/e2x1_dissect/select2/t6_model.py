#!/usr/bin/env python3
"""select2 t6: models + rules on the universe (U2) with the five new feature families.
TRAIN = tape start .. 10-27 18:41 PKT (days 1-5), TEST = the last 24 h (nothing chosen on it). Val = last 12 h of train (early stop).
(a) GBDT all families -> AUC, precision/recall, gain importance, family ablation (drop-one / MKT+one)
(b) depth<=4 decision tree + greedy rule list (human-readable) tuned on train for >= 60 % recall
Evaluation on TEST: recall, precision, forward returns g24/g94/g160 (market, entry 1 slot after e) and the 66 ms sim P&L for
(i) rule & his, (ii) rule & NOT his (acid test), (iii) his & NOT rule. Usage: t6_model.py [label: y|ysib] [tag]"""
import sys, json, time, os
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect"); import dd_gbdt as G
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select2"); from lib import *
LAB = sys.argv[1] if len(sys.argv) > 1 else "y"; TAG = sys.argv[2] if len(sys.argv) > 2 else LAB
NOSIB = os.environ.get("NOSIB")        # drop the Grozoe-is-trigger feature and Grozoe rows as triggers
t0 = time.time()
U = dict(np.load(f"{OUT}/U2.npz")); SIM = dict(np.load(f"{OUT}/sim_66.npz"))
LD = np.load(f"{OUT}/leaders.npz"); LM = json.load(open(f"{OUT}/leader_meta.json"))
tmax = int(U["bt"].max()); TCUT = tmax - 86400; VCUT = TCUT - 12 * 3600
y = U[LAB].astype(bool); samp = U["samp"].astype(bool)
rows = samp | y
if NOSIB: rows &= U["u_is_sib"] == 0
wt = np.where(y, 1.0, 25.0)
TE = U["bt"] >= TCUT; VA = (U["bt"] >= VCUT) & ~TE; TR = ~TE & ~VA
# ---- leader features ----
lid = LD["win"][(U["slot"] - int(LD["s_lo"])) // 4]
cli = np.array([str(m["client"] or "?") for m in LM] + ["?"]); ccs = np.array([str(m["cc"] or "?") for m in LM] + ["?"]); rtt = np.array([(m["rtt"] or -1) for m in LM] + [-1.0], float)
lidx = np.where(lid >= 0, lid, len(LM))
U["ld_rtt"] = rtt[lidx].astype(np.float32)
def te_cat(cat, name, prior_n=50):
    """target-encode a categorical on TRAIN rows only (smoothed take rate per category); also returns the dict"""
    c = cat.astype(np.int64); base = wt[TR & rows]; pr = (y[TR & rows]).sum() / base.sum()
    n = np.bincount(c[TR & rows], weights=wt[TR & rows]); h = np.bincount(c[TR & rows], weights=y[TR & rows].astype(float))
    n = np.r_[n, np.zeros(max(c.max() + 1 - len(n), 0))]; h = np.r_[h, np.zeros(max(c.max() + 1 - len(h), 0))]
    U[name] = ((h[c] + prior_n * pr) / (n[c] + prior_n)).astype(np.float32)
    return n, h, pr
CLI = {k: i for i, k in enumerate(sorted(set(cli)))}; CC = {k: i for i, k in enumerate(sorted(set(ccs)))}
U["ld_client"] = np.array([CLI[k] for k in cli[lidx]], np.float32); U["ld_cc"] = np.array([CC[k] for k in ccs[lidx]], np.float32)
te_cat(lidx, "ld_rate"); te_cat(U["ld_client"], "ld_client_rate"); te_cat(U["ld_cc"], "ld_cc_rate")
te_cat(np.maximum(U["tx_route"], 0) + 1, "tx_route_rate"); te_cat((U["tx_ixh"].astype(np.int64) % 100003), "tx_ixh_rate")
te_cat(np.maximum(U["tx_relay"], 0), "tx_relay_rate"); te_cat(U["meta_host"], "host_rate")
te_cat(np.minimum(np.maximum(U["tx_cup"], 0), 50_000_000) // 1000, "tx_cup_rate")
U["tx_cup_log"] = np.log10(np.maximum(U["tx_cup"], 1)); U["tx_tip_log"] = np.log10(np.maximum(U["tx_tip"], 1))
U["sol_log"] = np.log10(np.maximum(U["sol"], 1e-4)); U["imp_abs"] = np.abs(U["imp"])
FAM = {
 "MKT": ["age_s", "vsol", "is_buy", "sol", "sol_log", "imp", "imp_abs", "by_creator", "ret_1s", "ret_5s", "ret_30s", "ret_120s", "dd_peak", "mult", "peak_mult",
         "nb_cur", "ns_cur", "solin_cur", "solout_cur", "nb_1s", "ns_1s", "solin_1s", "solout_1s", "nb_5s", "ns_5s", "solin_5s", "solout_5s",
         "nb_30s", "ns_30s", "solin_30s", "solout_30s", "ntr", "nusers", "dev_sells", "dev_buy_sol", "tot_in", "tot_out", "bundle_sol", "bundle_n", "gap_prev_sl",
         "circ_share", "maxbuy_share", "dev_share"],
 "WAL": ["u_ntr", "u_nbuy", "u_nsell", "u_solin", "u_solout", "u_nmint", "u_create_buys", "u_first_slot_buys", "u_age_s", "u_follow_n", "u_follow_rate",
         "u_follow_rate_sm", "u_prior_n2", "u_sibfollow_n", "u_trips", "u_trip_pnl", "u_trip_cost", "u_wins", "u_winrate", "u_ret_per_sol", "u_open_mints",
         "u_hold_mean_sl", "u_mean_size", "u_cw541", "u_pro53", "u_sniper66", "u_census_tot", "u_census_win", "u_is_creator", "u_ncreates"] + ([] if NOSIB else ["u_is_sib"]),
 "TX": ["tx_cup", "tx_cup_log", "tx_cul", "tx_cu", "tx_fee", "tx_tip", "tx_tip_log", "tx_nsign", "tx_ntips", "tx_relay", "tx_hit", "tx_prio_sol", "tx_fee_per_sol",
        "tx_f_cb", "tx_f_nonce", "tx_f_create", "tx_f_close", "tx_f_routed", "tx_f_extend", "tx_f_v2", "tx_route_rate", "tx_ixh_rate", "tx_relay_rate", "tx_cup_rate"],
 "TOK": ["n_cw_in", "n_pro_in", "n_snip_in", "n_good_in", "n_follow_in", "sib_buys", "sib_open"],
 "OWN": ["my_buys", "my_open", "my_net", "my_since_sell_sl", "my_since_buy_sl", "my_px_vs_last_fill"],
 "CRE": ["cr_prev", "cr_prev_grad", "cr_prev_rug", "cr_prev_peakv", "cr_prev_gradrate", "cr_age_s", "dev_buy0", "bundle_n0", "bundle_sol0", "bundle_max0", "bundle_cw0",
         "in_create_slot", "cashback", "holder", "cfee_bps", "host_rate", "name_len", "sym_len", "sym_upper", "name_nonascii", "name_words", "vanity_pump",
         "name_digit", "name_eq_sym", "uri_len", "name_lower"],
 "TIM": ["hour", "dow", "minute", "slot_in_win", "my_buys_60", "my_sells_60", "my_buys_300", "my_sells_300", "my_gap_s", "my_open_n", "sib_trades_60",
         "ld_rtt", "ld_client", "ld_cc", "ld_rate", "ld_client_rate", "ld_cc_rate"],
}
if NOSIB:
    SIBF = {"u_is_sib", "u_sibfollow_n", "sib_buys", "sib_open", "sib_trades_60"}
    FAM = {k: [f for f in v if f not in SIBF] for k, v in FAM.items()}
ALL = [f for v in FAM.values() for f in v]
def auc(s, yy, ww):
    o = np.argsort(s); s2 = s[o]; y2 = yy[o]; w2 = ww[o]
    # weighted AUC: P(score pos > score neg) with weights
    cw_neg = np.cumsum(np.where(~y2, w2, 0)); tot_neg = cw_neg[-1]
    # ties: approximate by midrank (fine for continuous scores)
    return float((np.where(y2, w2, 0) * cw_neg).sum() / (ww[yy].sum() * tot_neg))
def fit(feats, tag, rounds=500, depth=4, lr=0.08, min_n=200):
    X = np.column_stack([np.nan_to_num(U[f].astype(np.float64), nan=0, posinf=1e9, neginf=-1e9) for f in feats])[rows]
    yy = y[rows].astype(float); ww = wt[rows]; tr = TR[rows]; va = VA[rows]; te = TE[rows]
    E = G.edges_of(X, tr); B = G.binize(X, E)
    M = G.fit(B, yy, tr, va, loss="log", rounds=rounds, lr=lr, depth=depth, min_n=min_n, lam=5.0, seed=1, patience=50)   # unweighted: negatives are a uniform 4 % sample, ranking unaffected
    s = G.predict(M, B)
    res = dict(tag=tag, n_feats=len(feats), rounds=M["best_round"], auc_va=auc(s[va], yy[va] > 0, ww[va]), auc_te=auc(s[te], yy[te] > 0, ww[te]),
               pos_tr=int(yy[tr].sum()), pos_te=int(yy[te].sum()))
    st, yt, w_ = s[te], yy[te] > 0, ww[te]; o = np.argsort(-st); cy = np.cumsum(yt[o]); cw = np.cumsum(w_[o]); base = yt.sum() / w_.sum()
    res["prec_at_recall"] = [(r, float(cy[k] / cw[k]), float(cy[k] / cw[k] / base)) for r in (0.25, 0.5, 0.6, 0.75) for k in [np.searchsorted(cy, r * yt.sum())]]
    imp = G.importance(M, len(feats)); res["imp"] = sorted(zip(feats, imp.round(4).tolist()), key=lambda z: -z[1])
    return res, s, M, E
R = {}
ABL = os.environ.get("ABL")
if ABL:   # one family's ablation pair in its own process (driver: t6_abl.sh)
    fam = ABL
    if fam == "MKT": r1, _, _, _ = fit(FAM["MKT"], "MKT only", rounds=250, lr=0.12); R["MKT"] = r1
    else:
        r1, _, _, _ = fit(FAM["MKT"] + FAM[fam], f"MKT+{fam}", rounds=250, lr=0.12); R[f"MKT+{fam}"] = r1
        r2, _, _, _ = fit([f for k, v in FAM.items() if k != fam for f in v], f"ALL-{fam}", rounds=250, lr=0.12); R[f"ALL-{fam}"] = r2
    json.dump(R, open(f"{OUT}/t6_abl_{TAG}_{fam}.json", "w"), indent=1, default=float); print("abl done", fam, time.time() - t0); sys.exit(0)
res, s_all, M_all, E_all = fit(ALL, "ALL"); R["ALL"] = res; print(json.dumps({k: v for k, v in res.items() if k != "imp"}), flush=True)
print("top 25 features (gain share):", res["imp"][:25], flush=True)
# ---------------------------------------------------------------- evaluation helper ----------------------------------------------
def m_(x, w_):
    k = np.isfinite(x); return 100 * np.average(np.clip(x[k], -1, 5), weights=w_[k]) if k.any() else np.nan
def evaluate(sel, name):
    """sel: bool over U rows (universe rows only count). TEST numbers for (i) sel&y (ii) sel&~y (iii) ~sel&y"""
    out = {"name": name}
    te = TE & rows
    for grp, m in (("i_rule_and_his", sel & y & te), ("ii_rule_not_his", sel & ~y & te), ("iii_his_not_rule", ~sel & y & te), ("all_his_test", y & te)):
        w_ = wt[m]; d = dict(n=int(m.sum()), n_w=float(w_.sum()))
        for k in ("g24", "g94", "g160"): d[k] = m_(U[k][m], w_)
        for ex in ("5s", "20s", "34s", "band"):
            for phi in (0.0, 0.2):
                fl = SIM[f"tier|{ex}|{phi}|fill"][m]; p = SIM[f"tier|{ex}|{phi}|pnl"][m]
                d[f"sim_{ex}_phi{phi}"] = (float(np.average(fl, weights=w_)) if len(w_) else np.nan, float(np.average(p, weights=w_) * 1000) if len(w_) else np.nan)
        d["sim_fix_34s_phi0.2"] = float(np.average(SIM["fix|34s|0.2|pnl"][m], weights=w_) * 1000) if len(w_) else np.nan
        d["S_mean"] = float(np.average(SIM["tier|S"][m], weights=w_)) if len(w_) else np.nan
        out[grp] = d
    out["recall_te"] = float((sel & y & te).sum() / max((y & te).sum(), 1))
    nb = np.unique(U["nxt_row"][y & te]); nbs = np.unique(U["nxt_row"][sel & y & te]); out["recall_buys_te"] = float(len(nbs) / max(len(nb), 1)); out["his_buys_te"] = int(len(nb)); out["prec_te"] = float((sel & y & te).sum() / max(wt[sel & te].sum(), 1))
    out["picks_per_day_te"] = float(wt[sel & te].sum()); out["base_te"] = float((y & te).sum() / wt[te].sum())
    tr = TR & rows; out["recall_tr"] = float((sel & y & tr).sum() / max((y & tr).sum(), 1)); out["prec_tr"] = float((sel & y & tr).sum() / max(wt[sel & tr].sum(), 1))
    out["ii_train_g94"] = m_(U["g94"][sel & ~y & tr], wt[sel & ~y & tr]); out["ii_train_sim34"] = float(np.average(SIM["tier|34s|0.2|pnl"][sel & ~y & tr], weights=wt[sel & ~y & tr]) * 1000) if (sel & ~y & tr).any() else np.nan
    return out
# GBDT at thresholds giving 60 % / 40 % train recall
EV = []
str_ = s_all[TR[rows]]; ytr = y[rows][TR[rows]]
for rec in (0.6, 0.4):
    thr = np.quantile(str_[ytr], 1 - rec); sel = np.zeros(len(y), bool); sel[np.flatnonzero(rows)] = s_all >= thr
    EV.append(evaluate(sel & rows, f"GBDT-ALL @train-recall {rec}"))
# ---------------------------------------------------------------- (b) readable rules ----------------------------------------------
Xall = {f: np.nan_to_num(U[f].astype(np.float64), nan=0, posinf=1e9, neginf=-1e9) for f in ALL}
def best_split(idx, feats, min_w=2000.0):
    """weighted gini gain over 31 quantile thresholds per feature on rows idx (train)"""
    yy = y[idx]; ww = wt[idx]; W = ww.sum(); P = (ww * yy).sum()
    if P == 0 or W == 0: return None
    g0 = P / W * (1 - P / W); best = None
    for f in feats:
        x = Xall[f][idx]; qs = np.unique(np.quantile(x, np.linspace(0.02, 0.98, 31)))
        for q in qs:
            L = x <= q; WL = ww[L].sum(); PL = (ww * yy)[L].sum(); WR = W - WL; PR = P - PL
            if WL < min_w or WR < min_w: continue
            gl = PL / WL * (1 - PL / WL); gr = PR / WR * (1 - PR / WR)
            gain = g0 - (WL * gl + WR * gr) / W
            if best is None or gain > best[0]: best = (gain, f, float(q), WL, PL, WR, PR)
    return best
def grow(idx, feats, depth, path):
    yy = y[idx]; ww = wt[idx]; rate = (ww * yy).sum() / max(ww.sum(), 1e-9)
    node = dict(path=path, n_w=float(ww.sum()), pos=int(yy.sum()), rate=float(rate))
    if depth == 0 or yy.sum() < 100: return node
    b = best_split(idx, feats)
    if b is None or b[0] <= 1e-6: return node
    _, f, q, *_ = b
    x = Xall[f][idx]
    node["split"] = (f, q); node["L"] = grow(idx[x <= q], feats, depth - 1, path + [(f, "<=", q)]); node["R"] = grow(idx[x > q], feats, depth - 1, path + [(f, ">", q)])
    return node
def leaves(node):
    return [node] if "split" not in node else leaves(node["L"]) + leaves(node["R"])
def sel_of(path, idx=None):
    m = np.ones(len(y), bool)
    for f, op, q in path: m &= (Xall[f] <= q) if op == "<=" else (Xall[f] > q)
    return m
tr_idx = np.flatnonzero(TR & rows)
RULES = {}
for tag, feats in (("tree-ALL", ALL), ("tree-noWAL", [f for k, v in FAM.items() if k != "WAL" for f in v])):
    t1 = time.time(); tree = grow(tr_idx, feats, 4, []); lv = sorted(leaves(tree), key=lambda l: -l["rate"])
    # take leaves by decreasing rate until >= 60 % train recall
    P = y[tr_idx].sum(); acc = 0; chosen = []
    for l in lv:
        chosen.append(l); acc += l["pos"]
        if acc >= 0.6 * P: break
    sel = np.zeros(len(y), bool)
    for l in chosen: sel |= sel_of(l["path"])
    RULES[tag] = dict(leaves=[dict(path=l["path"], n_w=l["n_w"], pos=l["pos"], rate=l["rate"]) for l in chosen], all_leaves=[dict(path=l["path"], n_w=l["n_w"], pos=l["pos"], rate=l["rate"]) for l in lv])
    EV.append(evaluate(sel & rows, f"{tag} (leaves to 60% train recall)")); print(tag, "built", round(time.time() - t1), "s; leaves", len(lv), flush=True)
    # also the single best leaf
    sel1 = sel_of(lv[0]["path"]); EV.append(evaluate(sel1 & rows, f"{tag} best leaf"))
# greedy conjunction (s17 style) on ALL features keeping >= 60 % train recall
def greedy(feats, target=0.6, steps=4):
    cur = TR & rows; conds = []
    for _ in range(steps):
        best = None
        for f in feats:
            x = Xall[f]; xp = x[cur & y]
            for op, qs in ((">=", np.unique(np.quantile(xp, np.linspace(0.02, 1 - target, 12)))), ("<=", np.unique(np.quantile(xp, np.linspace(target, 0.98, 12))))):
                for q in qs:
                    sel = cur & ((x >= q) if op == ">=" else (x <= q))
                    rec = (sel & y).sum() / (TR & rows & y).sum()
                    if rec < target: continue
                    prec = (sel & y).sum() / max(wt[sel].sum(), 1)
                    if best is None or prec > best[0]: best = (prec, rec, f, op, float(q), sel)
        if best is None: break
        conds.append((best[2], best[3], best[4])); cur = best[5]
    sel = rows.copy()
    for f, op, q in conds: sel &= (Xall[f] >= q) if op == ">=" else (Xall[f] <= q)
    return conds, sel
t1 = time.time(); conds, sel = greedy(ALL); RULES["greedy-ALL"] = conds; EV.append(evaluate(sel, "greedy-ALL conj (>=60% train recall)")); print("greedy", conds, round(time.time() - t1), "s", flush=True)
conds, sel = greedy(FAM["MKT"] + FAM["TX"] + FAM["CRE"] + FAM["TIM"] + FAM["TOK"]); RULES["greedy-noWAL"] = conds; EV.append(evaluate(sel, "greedy-noWAL conj"))
json.dump(dict(models=R, evals=EV, rules=RULES, TCUT=TCUT, lab=LAB, nosib=bool(NOSIB)), open(f"{OUT}/t6_{TAG}.json", "w"), indent=1, default=float)
np.savez(f"{OUT}/t6_scores_{TAG}.npz", s=s_all, rows=np.flatnonzero(rows))
print("done", time.time() - t0)

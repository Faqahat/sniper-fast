#!/usr/bin/env python3
"""QUIET2 step 5: the rule search. TRAIN = AMS r28-r33 + FRA r27, TEST = FRA r28 + AMS r34 (never used for choosing).
A rule only REMOVES armed windows (on top of the live QUIET). Gain of a rule on a run = sum over the removed windows of
(failed-try fees saved - the fill's net), MEASURED. Pre-registered selection (written before any test number was looked at):
  * candidates: single thresholds on arm-time features at train deciles, both directions; ANDs of the 25 best singles;
  * constraints on TRAIN: removes >= 40% of the flat fills, removes <= 15% of the winners' P&L, gain > 0 on BOTH big train runs
    (AMS r28, FRA r27) and pooled;
  * pick = the highest pooled train gain among them; ties -> the simpler rule (fewer terms).
Also: a greedy depth-3 tree and a small numpy GBDT (comparison), the (d) threshold / no-history sweep, the C5 stop sweep."""
import sys, json, collections, itertools, math
import numpy as np
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/quiet2")
import q2lib as Q
rng = np.random.default_rng(7)
F = json.load(open(f"{Q.D}/features.json")); W = [r for r in F["windows"] if r["f"].get("chain_ok")]; SK = F["skips"]
TRAIN = [r for r in W if r["role"] == "train"]; TEST = [r for r in W if r["role"] == "test"]
BIG = {"a28", "f27"}

# ---- arm-time feature table (engine-implementable)
FEATS = ["n_tr", "token_age_s", "n_tr_10s", "n_tr_30s", "n_buyers_30s", "n_tr_60s", "n_buyers_60s", "n_tr_120s", "n_buyers_120s", "n_tr_300s", "n_buyers_300s",
         "buy_sol_60s", "sell_sol_60s", "buy_sol_120s", "coh_60s", "fb_60s", "coh_120s", "fb_120s", "coh_300s", "fb_300s", "trades_per_s_60", "since_last_s", "since_last_chain",
         "coh_hold_chain", "fb_n_chain", "coh_ever", "n_wallets", "n_holders", "holders_gt1pct", "holders_gt0_5pct", "top_holder_pct", "whale_pct_after_buy",
         "pump_pct", "ret_30s", "ret_60s", "ret_120s", "maxdd_60s", "maxdd_120s", "buy_vs_curve", "vsol_pre", "same_slot_before", "wd_n", "wd_mean", "wd_last", "wd_max", "wd_n_1h", "wd_last_age_s"]
RECF = ["whale_sol", "whale_pct", "vsol", "age_slots", "hour", "prior_arms", "prior_whale_arms", "wh_dumps", "wh_fol", "fb_n", "coh_hold", "since_last"]


def X_of(rows):
    X = np.zeros((len(rows), len(FEATS) + len(RECF)))
    for i, r in enumerate(rows):
        X[i, :len(FEATS)] = [r["f"].get(k, 0) for k in FEATS]
        X[i, len(FEATS):] = [(r.get(k) if r.get(k) is not None else -1) for k in RECF]
    return X


NAMES = FEATS + RECF
Xtr, Xte = X_of(TRAIN), X_of(TEST)
net = lambda rows: np.array([(r["net"] or 0.0) if r["filled"] else 0.0 for r in rows])
fee = lambda rows: np.array([r["fee_fail"] for r in rows])
lab = lambda rows: np.array([r.get("lab", "NOFILL") for r in rows])
run = lambda rows: np.array([r["run"] for r in rows])
Ntr, Fe_tr, Ltr, Rtr = net(TRAIN), fee(TRAIN), lab(TRAIN), run(TRAIN)
Nte, Fe_te, Lte, Rte = net(TEST), fee(TEST), lab(TEST), run(TEST)


def evaluate(mask, N, Fe, L, R):
    """mask = windows REMOVED. returns dict"""
    d = {}
    d["gain"] = float(Fe[mask].sum() - N[mask].sum())
    d["flat_rm"] = int((mask & (L == "FLAT")).sum()); d["flat_n"] = int((L == "FLAT").sum())
    d["win_rm"] = int((mask & (L == "WIN")).sum()); d["win_pnl_rm"] = float(N[mask & (L == "WIN")].sum()); d["win_pnl"] = float(N[L == "WIN"].sum())
    d["loss_rm"] = int((mask & (L == "LOSS")).sum()); d["loss_pnl_rm"] = float(N[mask & (L == "LOSS")].sum())
    d["fills_rm"] = int((mask & (L != "NOFILL")).sum()); d["fills"] = int((L != "NOFILL").sum()); d["wins_rm"] = int((mask & (L != "NOFILL")).sum())
    d["win_rm_pct"] = 100 * d["win_pnl_rm"] / d["win_pnl"] if d["win_pnl"] else 0
    d["flat_rm_pct"] = 100 * d["flat_rm"] / d["flat_n"] if d["flat_n"] else 0
    d["per_run"] = {rr: float(Fe[mask & (R == rr)].sum() - N[mask & (R == rr)].sum()) for rr in sorted(set(R.tolist()))}
    d["removed"] = int(mask.sum())
    return d


def ok_train(d):
    return d["flat_rm_pct"] >= 40 and d["win_rm_pct"] <= 15 and all(d["per_run"][b] > 0 for b in BIG) and d["gain"] > 0


# ---- single thresholds
cands = []
for j, name in enumerate(NAMES):
    v = Xtr[:, j]; qs = np.unique(np.quantile(v, np.linspace(0.05, 0.95, 19)))
    for t in qs:
        for sgn in ("<=", ">="):
            m = (v <= t) if sgn == "<=" else (v >= t)
            if m.sum() < 10 or m.sum() > len(v) - 10: continue
            d = evaluate(m, Ntr, Fe_tr, Ltr, Rtr)
            cands.append((d["gain"], f"{name} {sgn} {t:.4g}", (j, sgn, float(t)), d))
n_single = len(cands)
cands.sort(key=lambda x: -x[0])
print(f"single rules tried: {n_single}")
print("top 15 singles by TRAIN gain (gain | flat rm % | win pnl rm % | AMS r28 | FRA r27 | removed windows):")
for g, nm, _, d in cands[:15]:
    print(f"  {nm:34s} {g:+.3f} | {d['flat_rm_pct']:5.1f}% | {d['win_rm_pct']:5.1f}% | {d['per_run']['a28']:+.3f} | {d['per_run']['f27']:+.3f} | {d['removed']}")
okc = [c for c in cands if ok_train(c[3])]
print(f"singles meeting the train constraints: {len(okc)}")
for g, nm, _, d in okc[:10]:
    print(f"  {nm:34s} {g:+.3f} | flat {d['flat_rm']}/{d['flat_n']} | win {d['win_rm']} ({d['win_pnl_rm']:+.3f}, {d['win_rm_pct']:.1f}%) | loss {d['loss_rm']} ({d['loss_pnl_rm']:+.3f}) | {d['per_run']}")


def mask_of(rule, X):
    m = np.ones(len(X), bool)
    for j, sgn, t in rule:
        m &= (X[:, j] <= t) if sgn == "<=" else (X[:, j] >= t)
    return m


# ---- pairs (AND) of the 25 best singles (by gain), distinct features
top = []
seenf = set()
for g, nm, rule, d in cands:
    if rule[0] in seenf: continue
    top.append((nm, rule)); seenf.add(rule[0])
    if len(top) >= 25: break
pairs = []
for (n1, r1), (n2, r2) in itertools.combinations(top, 2):
    m = mask_of([r1, r2], Xtr)
    if m.sum() < 10: continue
    d = evaluate(m, Ntr, Fe_tr, Ltr, Rtr)
    pairs.append((d["gain"], f"{n1} AND {n2}", [r1, r2], d))
pairs.sort(key=lambda x: -x[0])
print(f"\npairs tried: {len(pairs)}; top 10 by TRAIN gain:")
for g, nm, _, d in pairs[:10]:
    print(f"  {nm:60s} {g:+.3f} | flat {d['flat_rm_pct']:5.1f}% | win pnl {d['win_rm_pct']:5.1f}% | a28 {d['per_run']['a28']:+.3f} f27 {d['per_run']['f27']:+.3f} | rm {d['removed']}")
okp = [c for c in pairs if ok_train(c[3])]
print(f"pairs meeting the train constraints: {len(okp)}")
for g, nm, _, d in okp[:10]:
    print(f"  {nm:60s} {g:+.3f} | flat {d['flat_rm']}/{d['flat_n']} | win {d['win_rm']} ({d['win_pnl_rm']:+.3f}, {d['win_rm_pct']:.1f}%) | loss {d['loss_rm']} ({d['loss_pnl_rm']:+.3f}) | {d['per_run']}")

# ---- the pick (pre-registered): highest train gain among constrained rules, singles and pairs; simpler wins ties
pool = [(g, nm, [rule] if not isinstance(rule, list) else rule, d) for g, nm, rule, d in okc] + [(g, nm, rule, d) for g, nm, rule, d in okp]
pool.sort(key=lambda x: (-round(x[0], 3), len(x[2])))
PICK = pool[0] if pool else None
print("\n=== PICK (train):", PICK[1] if PICK else None)


def report(name, m_tr, m_te, extra=""):
    dtr = evaluate(m_tr, Ntr, Fe_tr, Ltr, Rtr); dte = evaluate(m_te, Nte, Fe_te, Lte, Rte)
    print(f"\n### {name} {extra}")
    for tag, d, rows, N, Fe, L, R, m in (("TRAIN", dtr, TRAIN, Ntr, Fe_tr, Ltr, Rtr, m_tr), ("TEST", dte, TEST, Nte, Fe_te, Lte, Rte, m_te)):
        print(f"{tag}: gain {d['gain']:+.3f} | windows removed {d['removed']}/{len(rows)} | fills removed {d['fills_rm']}/{d['fills']} = flat {d['flat_rm']}/{d['flat_n']} ({d['flat_rm_pct']:.0f}%), "
              f"win {d['win_rm']} ({d['win_pnl_rm']:+.3f} = {d['win_rm_pct']:.1f}% of win P&L), loss {d['loss_rm']} ({d['loss_pnl_rm']:+.3f}) | fees saved {Fe[m].sum():.3f}")
        for rr in sorted(set(R.tolist())):
            mm = R == rr; hours = (max(r["t"] for r in rows if r["run"] == rr) - min(r["t"] for r in rows if r["run"] == rr)) / 3.6e12
            actual = N[mm].sum() - Fe[mm].sum(); v2 = N[mm & ~m].sum() - Fe[mm & ~m].sum()
            kept = (mm & ~m & (L != "NOFILL")).sum()
            print(f"   {Q.RUNS[rr]['name']:8s} actual {actual:+.3f} -> v2 {v2:+.3f} ({v2-actual:+.3f}) | fills {int((mm & (L!='NOFILL')).sum())} -> {int(kept)} ({int((mm & (L!='NOFILL')).sum())/hours:.1f} -> {kept/hours:.1f}/h) | flats {int((mm & (L=='FLAT')).sum())} -> {int((mm & ~m & (L=='FLAT')).sum())}")
        # bootstrap 90% CI of the gain over windows, pooled
        g = Fe * m - N * m; bs = [g[rng.integers(0, len(g), len(g))].sum() for _ in range(2000)]
        print(f"   pooled gain {g.sum():+.3f} 90% CI [{np.percentile(bs,5):+.3f}, {np.percentile(bs,95):+.3f}] ; P(gain>0) {np.mean(np.array(bs)>0):.2f}")
        keptN = N[~m & (L != "NOFILL")]; top5 = np.sort(keptN)[-5:].sum() if len(keptN) else 0
        print(f"   top-5 share of kept fills' net: {100*top5/max(keptN.sum(),1e-9):.0f}% (actual {100*np.sort(N[L!='NOFILL'])[-5:].sum()/max(N[L!='NOFILL'].sum(),1e-9):.0f}%)")
    return dtr, dte


if PICK:
    report("QUIET v2 pick: " + PICK[1], mask_of(PICK[2], Xtr), mask_of(PICK[2], Xte))
    # the examples
    m_te = mask_of(PICK[2], Xte)
    print("removed TEST fills (label, net, token, pkt):")
    for r, mm in zip(TEST, m_te):
        if mm and r["filled"]: print(f"   {r['lab']:4s} {r['net']:+.4f} {r['name']} {r['pkt']} https://gmgn.ai/sol/token/{r['mint']}  n_buyers_60s={r['f']['n_buyers_60s']} fb_n={r['fb_n']} coh_hold={r['coh_hold']}")

# ---- also show the 2nd-5th constrained picks on test (information only; multiple testing)
print("\n=== runners-up (train gain -> test gain), information only")
for g, nm, rule, d in pool[1:8]:
    dte = evaluate(mask_of(rule, Xte), Nte, Fe_te, Lte, Rte)
    print(f"  {nm:60s} train {g:+.3f} -> test {dte['gain']:+.3f} (flat {dte['flat_rm']}/{dte['flat_n']}, win pnl rm {dte['win_rm_pct']:.0f}%, {dte['per_run']})")


# ---- greedy depth-3 tree on the economic objective: a leaf is REMOVED if its train sum(net - fee) < 0 and it has >= 20 windows
def best_split(idx, X, y, depth):
    best = None
    for j in range(X.shape[1]):
        v = X[idx, j]
        for t in np.unique(np.quantile(v, np.linspace(0.1, 0.9, 9))):
            l = idx[v <= t]; r = idx[v > t]
            if len(l) < 20 or len(r) < 20: continue
            # objective: the value of removing the worse side (min of the two sums, if negative)
            sl, sr = y[l].sum(), y[r].sum(); sc = min(sl, sr)
            if best is None or sc < best[0]: best = (sc, j, t)
    return best


def grow(idx, X, y, depth):
    if depth == 0 or len(idx) < 40: return ("leaf", y[idx].sum() < 0 and len(idx) >= 20, len(idx), y[idx].sum())
    b = best_split(idx, X, y, depth)
    if b is None: return ("leaf", y[idx].sum() < 0 and len(idx) >= 20, len(idx), y[idx].sum())
    _, j, t = b
    return ("node", j, t, grow(idx[X[idx, j] <= t], X, y, depth - 1), grow(idx[X[idx, j] > t], X, y, depth - 1))


def apply(tree, X):
    m = np.zeros(len(X), bool)
    def rec(node, idx):
        if node[0] == "leaf":
            if node[1]: m[idx] = True
            return
        _, j, t, l, r = node
        rec(l, idx[X[idx, j] <= t]); rec(r, idx[X[idx, j] > t])
    rec(tree, np.arange(len(X))); return m


def show(node, ind=""):
    if node[0] == "leaf": print(f"{ind}leaf n={node[2]} sum={node[3]:+.3f} -> {'REMOVE' if node[1] else 'keep'}"); return
    _, j, t, l, r = node
    print(f"{ind}{NAMES[j]} <= {t:.4g}:"); show(l, ind + "  "); print(f"{ind}{NAMES[j]} > {t:.4g}:"); show(r, ind + "  ")


y_tr = Ntr - Fe_tr
tree = grow(np.arange(len(Xtr)), Xtr, y_tr, 3)
print("\n=== depth-3 tree (economic objective, train):"); show(tree)
report("depth-3 tree", apply(tree, Xtr), apply(tree, Xte))


# ---- GBDT comparison (numpy): depth-2 regression trees on y = (net - fee)/spend, 120 rounds, lr 0.05, min leaf 15
def fit_stump2(X, g, minleaf=15):
    best = None
    for j in range(X.shape[1]):
        v = X[:, j]
        for t in np.unique(np.quantile(v, np.linspace(0.1, 0.9, 9))):
            l = v <= t
            if l.sum() < minleaf or (~l).sum() < minleaf: continue
            sse = -(g[l].sum() ** 2 / l.sum() + g[~l].sum() ** 2 / (~l).sum())
            if best is None or sse < best[0]: best = (sse, j, t, g[l].mean(), g[~l].mean())
    return best


def gbdt(X, y, rounds=120, lr=0.05):
    pred = np.full(len(y), y.mean()); model = [y.mean()]
    for _ in range(rounds):
        g = y - pred
        s = fit_stump2(X, g)
        if s is None: break
        _, j, t, vl, vr = s
        l = X[:, j] <= t
        # depth 2: split each side once more
        sub = []
        for side in (l, ~l):
            s2 = fit_stump2(X[side], g[side]) if side.sum() >= 30 else None
            sub.append(s2)
        node = (j, t, sub, vl, vr); model.append(node)
        pred += lr * predict_node(node, X)
    return model


def predict_node(node, X):
    j, t, sub, vl, vr = node; out = np.empty(len(X)); l = X[:, j] <= t
    for side, s2, v in ((l, sub[0], vl), (~l, sub[1], vr)):
        if s2 is None: out[side] = v
        else:
            _, j2, t2, v2l, v2r = s2; l2 = X[side, j2] <= t2; o = np.where(l2, v2l, v2r); out[side] = o
    return out


def predict(model, X):
    p = np.full(len(X), model[0])
    for node in model[1:]: p += 0.05 * predict_node(node, X)
    return p


sp_tr = np.array([r["spend"] for r in TRAIN]); sp_te = np.array([r["spend"] for r in TEST])
model = gbdt(Xtr, y_tr / sp_tr)
p_tr, p_te = predict(model, Xtr), predict(model, Xte)
# threshold chosen on train by the same constraints: remove windows with predicted profit per SOL below c
bestc = None
for c in np.quantile(p_tr, np.linspace(0.05, 0.6, 23)):
    d = evaluate(p_tr <= c, Ntr, Fe_tr, Ltr, Rtr)
    if ok_train(d) and (bestc is None or d["gain"] > bestc[1]["gain"]): bestc = (c, d)
if bestc:
    print(f"\n=== GBDT: threshold {bestc[0]:+.4f} (train-constrained)")
    report("GBDT", p_tr <= bestc[0], p_te <= bestc[0])
else:
    print("\n=== GBDT: no threshold meets the train constraints")
    c = np.quantile(p_tr, 0.2); report("GBDT (remove lowest 20% predicted, no constraint)", p_tr <= c, p_te <= c)

json.dump(dict(pick=PICK[1] if PICK else None, pick_rule=[(NAMES[j], s, t) for j, s, t in PICK[2]] if PICK else None, n_single=n_single, n_pairs=len(pairs),
               n_ok_single=len(okc), n_ok_pairs=len(okp)), open(f"{Q.D}/pick.json", "w"))

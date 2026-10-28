#!/usr/bin/env python3
"""exit2 step 3: GBDT (depth 4) + one depth-4 tree on the candidate events; train = trips entered before the TEST day,
TEST = trips entered 10-27 18:41 -> 10-28 18:41 PKT. Score = P(he sells in this slot or the next | event).
Firing rule: first event of a trip with p >= thr (thr picked on the validation slice so that the fire rate ~ matches).
Reports: AUC, importance, the tree, match (fire within +-1 / +-3 slots of his real first sell), wallet-identity rules.
Out: e3.txt, e3_scores.npz (per event score), e3_model.pkl"""
import sys, pickle, time, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect"); import dd_gbdt as G
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel"); import gbdt_np as GB
OUT = "/home/moiz/sniper-data/e2x1_dissect/exit2"
TEST0 = 1793113200 - 79 * 60; TEST1 = TEST0 + 86400   # 10-27 18:41 -> 10-28 18:41 PKT
Z = np.load(f"{OUT}/ev.npz"); X = Z["X"].astype(np.float64); y = Z["y1"].astype(np.float64); y3 = Z["y3"]; M = Z["meta"]; F = list(Z["feats"]); FI = {f: k for k, f in enumerate(F)}
TR = pickle.load(open(f"{OUT}/trips.pkl", "rb"))
trip = M[:, 0]; ev_slot = M[:, 2]; ev_bt = M[:, 6]
t_bt = np.array([t["bt"] for t in TR])
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
# per-trip sell slot (first sell) from tape
tape = np.load(f"{OUT}/tape_his.npz"); tslot = tape["slot"].astype(np.int64); tidx = tape["idx"].astype(np.int64)
t_ss = np.array([tslot[t["sells"][0]] if t["sells"] else -1 for t in TR]); t_si = np.array([tidx[t["sells"][0]] if t["sells"] else -1 for t in TR])
t_s0 = np.array([t["s"] for t in TR])
is_test_trip = (t_bt >= TEST0) & (t_bt < TEST1); is_train_trip = t_bt < TEST0
vcut = np.quantile(t_bt[is_train_trip], 0.85)
is_val_trip = is_train_trip & (t_bt >= vcut); is_fit_trip = is_train_trip & (t_bt < vcut)
te = is_test_trip[trip]; va = is_val_trip[trip]; fi = is_fit_trip[trip]
P(f"events {len(y)}  trips {len(TR)}  test trips {is_test_trip.sum()}  fit trips {is_fit_trip.sum()}  val trips {is_val_trip.sum()}")
P(f"positives (y1) fit {int(y[fi].sum())} / {fi.sum()}  test {int(y[te].sum())} / {te.sum()}   base rate {y.mean():.4f}")
# negative subsampling for speed
rng = np.random.default_rng(0)
keep = (y == 1) | (rng.random(len(y)) < 0.25) | te
w = np.where(y == 1, 1.0, 4.0)
fit_rows = fi & keep; val_rows = va & keep
t0 = time.time()
E = G.edges_of(X, fit_rows); B = G.binize(X, E)
model = G.fit(B, y, fit_rows, val_rows, loss="log", rounds=500, lr=0.08, depth=4, min_n=200, lam=5.0, seed=1, w=w)
s = G.predict(model, B); p = 1 / (1 + np.exp(-s))
P(f"GBDT rounds {model['best_round']}  {time.time()-t0:.0f}s")
P(f"AUC fit {GB.auc(y[fit_rows], s[fit_rows]):.3f}  val {GB.auc(y[val_rows], s[val_rows]):.3f}  TEST {GB.auc(y[te], s[te]):.3f}")
imp = G.importance(model, len(F)); P("importance:", ", ".join(f"{F[k]} {imp[k]:.3f}" for k in np.argsort(-imp)[:20]))
# ---- precision/recall on test events ----
for q in (0.99, 0.98, 0.95, 0.9):
    thr = np.quantile(p[te], q); sel = te & (p >= thr)
    P(f"  test events top {100*(1-q):.0f}%: thr {thr:.3f} precision {y[sel].mean():.3f} recall {y[sel].sum()/y[te].sum():.3f}")

# ---- firing: first event with p >= thr per trip ----
def fires(score, thr, rows):
    """rows: boolean mask of events to consider. returns dict trip -> (slot, idx, event row) of the first event with score >= thr"""
    ok = np.flatnonzero(rows & (score >= thr))
    first = {}
    for k in ok:
        t = trip[k]
        if t not in first: first[t] = k
    return first
def match(first, trips_mask, name):
    tt = np.flatnonzero(trips_mask & (t_ss >= 0)); n = len(tt)
    d = np.array([ (ev_slot[first[t]] - t_ss[t]) if t in first else np.nan for t in tt ], float)
    fired = np.isfinite(d)
    m1 = np.nanmean(np.abs(d) <= 1) if fired.any() else 0; m3 = np.nanmean(np.abs(d) <= 3) if fired.any() else 0
    early = np.nanmean(d < -1) if fired.any() else 0; late = np.nanmean(d > 1) if fired.any() else 0
    P(f"  {name:44} fires {fired.mean()*100:5.1f}% of {n} trips | of fired: +-1 slot {100*m1:5.1f}%  +-3 {100*m3:5.1f}%  earlier {100*early:4.1f}%  later {100*late:4.1f}% | all trips +-1 {100*np.sum(np.abs(d[fired])<=1)/n:5.1f}%")
    return d
# choose thr on val: the one maximising +-1 match over ALL val trips
P("\n== firing thresholds (chosen on validation) ==")
best = None
for thr in np.quantile(p[va], [0.5, 0.7, 0.8, 0.9, 0.95, 0.97, 0.98, 0.99, 0.995]):
    fr = fires(p, thr, va); tt = np.flatnonzero(is_val_trip & (t_ss >= 0))
    d = np.array([(ev_slot[fr[t]] - t_ss[t]) if t in fr else 99 for t in tt]); sc = np.mean(np.abs(d) <= 1)
    P(f"  val thr {thr:.4f}: +-1 match {100*sc:.1f}%  fired {100*np.mean(d!=99):.1f}%")
    if best is None or sc > best[0]: best = (sc, thr)
THR = best[1]; P(f"chosen thr {THR:.4f}")
P("\n== TEST firing ==")
d_gbdt = match(fires(p, THR, te), is_test_trip, f"GBDT thr {THR:.3f}")
for q in (0.9, 0.95, 0.98):
    thr = np.quantile(p[va], q); match(fires(p, thr, te), is_test_trip, f"GBDT thr {thr:.3f} (val q{q})")
# ---- wallet-identity / simple rules (fire at the first event satisfying) ----
P("\n== identity / simple rules on TEST (first event that satisfies) ==")
rules = {
    "sibling sold (<=2 slots before, incl. same slot)": X[:, FI["sib_sold_2"]] > 0,
    "sibling sells in this very slot (non-causal twin)": X[:, FI["sib_sold_slot"]] > 0,
    "event = sibling SELL": (X[:, FI["ev_sib"]] > 0) & (X[:, FI["ev_buy"]] == 0),
    "trigger wallet sells": (X[:, FI["ev_trig"]] > 0) & (X[:, FI["ev_buy"]] == 0),
    "creator sells": (X[:, FI["ev_creator"]] > 0) & (X[:, FI["ev_buy"]] == 0),
    "a copier sells": (X[:, FI["ev_copier"]] > 0) & (X[:, FI["ev_buy"]] == 0),
    "a co-reactor bot sells": (X[:, FI["ev_lead"]] > 0) & (X[:, FI["ev_buy"]] == 0),
    "first outside sell after entry": X[:, FI["ev_first_outside_sell"]] > 0,
    "any outside sell": X[:, FI["ev_buy"]] == 0,
    "any outside sell >= 0.3 SOL": (X[:, FI["ev_buy"]] == 0) & (X[:, FI["ev_sol"]] >= 0.3),
    "a follower (bought after him) sells": (X[:, FI["ev_buy"]] == 0) & (X[:, FI["ev_follower"]] > 0),
    "a pre-buyer sells": (X[:, FI["ev_buy"]] == 0) & (X[:, FI["ev_prebuyer"]] > 0),
    "top-3 holder sells": (X[:, FI["ev_buy"]] == 0) & (X[:, FI["ev_rank"]] <= 2),
    "sell by a wallet that bought in the last 5 s": (X[:, FI["ev_buy"]] == 0) & (X[:, FI["ev_user_bought_5s"]] > 0),
    "price <= 0.8 x entry": X[:, FI["r"]] <= 0.8,
    "drawdown from peak >= 20%": X[:, FI["dd"]] <= 0.8,
    "no outside buy for 10 slots": X[:, FI["since_buy"]] >= 10,
    "hold >= 160 slots (34 s)": X[:, FI["dslots"]] >= 160,
}
for nm, mask in rules.items():
    match(fires(mask.astype(float), 0.5, te), is_test_trip, nm)
# conditional probabilities on test: P(he sells within 1 slot | rule event)
P("\n== P(exit within <=1 slot | event type), TEST events ==")
for nm, mask in rules.items():
    sel = te & mask
    P(f"  {nm:44} n {sel.sum():7d}  P(exit) {100*y[sel].mean() if sel.any() else 0:5.1f}%  share of positives {100*y[sel].sum()/y[te].sum():5.1f}%")

# ---- one depth-4 tree (rule list) ----
P("\n== single depth-4 tree on fit rows (logistic Newton step) ==")
p0 = y[fit_rows].mean(); gr = (p0 - y) * w; he = p0 * (1 - p0) * w
tree = GB.build(B, gr, he, np.flatnonzero(fit_rows), 4, lam=5.0, min_n=500, fsub=np.arange(len(F)))
def show(t, ind=0, cond="root"):
    if "w" in t:
        P("  " * ind + f"{cond}: leaf logit shift {t['w']:+.2f}"); return
    f = F[t["f"]]; b = t["b"]; e = E[t["f"]]; thr = e[b - 1] if 0 < b <= len(e) else float("nan")
    P("  " * ind + f"{cond}:  split {f} <= {thr:.4g}")
    show(t["l"], ind + 1, f"{f} <= {thr:.4g}"); show(t["r"], ind + 1, f"{f} > {thr:.4g}")
show(tree)
st = GB.pred(tree, B); P(f"tree AUC test {GB.auc(y[te], st[te]):.3f}")
# tree leaves as rules: evaluate the leaf with the highest lift as a firing rule
leaf = np.full(len(y), -1);
def assign(t, ix, lid=[0]):
    if "w" in t: leaf[ix] = lid[0]; lid[0] += 1; return
    m = B[ix, t["f"]] <= t["b"]; assign(t["l"], ix[m]); assign(t["r"], ix[~m])
assign(tree, np.arange(len(y)))
for l in np.unique(leaf):
    sel = te & (leaf == l)
    if sel.sum(): P(f"  leaf {l}: test n {sel.sum():7d} P(exit) {100*y[sel].mean():5.1f}% share {100*y[sel].sum()/y[te].sum():5.1f}%")
np.savez(f"{OUT}/e3_scores.npz", p=p.astype(np.float32), thr=THR, test=te, val=va, leaf=leaf, tree_score=st.astype(np.float32))
pickle.dump(dict(model=model, E=E, feats=F, thr=THR, tree=tree), open(f"{OUT}/e3_model.pkl", "wb"))
open(f"{OUT}/e3.txt", "w").write("\n".join(out) + "\n")

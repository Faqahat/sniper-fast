#!/usr/bin/env python3
"""migpaper freeze: (1) re-fit the m2 predictors (p30, p120) with the same code on all entrable non-edge rows of migrate's
feat.pkl with block time < CUT (10-28 20:00 PKT); (2) re-fit m3's continuation model the same way; (3) also fit the
train-only versions (m2/m3 exactly) for the scorer validation and check they reproduce feat_p.pkl; (4) export every model to
numpy JSON (checked against sklearn predict_proba), freeze the landing quantiles, build the wallet / creator stores from
migrate's wallets.npz + grad's meta.pkl; (5) write FROZEN_SHA.md. Run ONCE. Needs sklearn (scratchpad pylib) only here."""
import sys, os, json, pickle, time, hashlib
import numpy as np
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/e2x1_migrate/pylib")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mplib
from mplib import D, MIG, GRAD, export_hgb, NPModel, ck_feats, h64, sha256, CKS, pkt
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

CUT = 1793199600            # 10-28 20:00 PKT
TRAIN = ["10-24", "10-25", "10-26"]; TEST = ["10-27", "10-28"]
MD = D + "/models"; os.makedirs(MD, exist_ok=True)
t0 = time.time()
F = pickle.load(open(MIG + "/feat.pkl", "rb")); X = F["X"]; names = F["names"]; meta = F["meta"]
PP = pickle.load(open(MIG + "/feat_p.pkl", "rb"))
day = np.array([r["day"] for r in meta]); ent = np.array([r["ent"] for r in meta]) == 1; edge = np.array([r["edge"] for r in meta])
tc = np.array([r["t_complete"] for r in meta]); bt = np.array([r["bt"] for r in meta])
use = ent & ~edge
tr = use & np.isin(day, TRAIN); te = use & np.isin(day, TEST)
frz = use & (bt < CUT)
print(f"rows {len(X)} entrable&clean {use.sum()} train {tr.sum()} test {te.sum()} frozen-fit rows (< 10-28 20:00 PKT) {frz.sum()}")
print("frozen-fit rows per day:", {d: int((frz & (day == d)).sum()) for d in sorted(set(day))})
def gb(): return HistGradientBoostingClassifier(max_depth=4, learning_rate=0.04, max_iter=400, min_samples_leaf=40, l2_regularization=1.0, random_state=0)
def cont(): return HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=200, min_samples_leaf=50, random_state=0)
SHA = []
def save_model(model, fn, extra=None):
    j = export_hgb(model); j["names"] = names if extra is None else extra
    json.dump(j, open(fn, "w"))
    return j

LOG = []
def log(s): print(s, flush=True); LOG.append(s)

# ---- (3) validation models = m2 exactly (fit on TRAIN) ------------------------------------------------------------
VAL = {}
for pk, H in (("p30", 30), ("p120", 120)):
    y = (tc <= H).astype(int)
    m = gb().fit(X[tr], y[tr]); p = m.predict_proba(X[te])[:, 1]
    diff = np.abs(p - PP[pk][te]).max()
    fn = f"{MD}/val_{pk}.json"; save_model(m, fn); npm = NPModel(fn); d2 = np.abs(npm.proba(X[te]) - p).max()
    log(f"VAL {pk}: n_iter {m.n_iter_} AUC test {roc_auc_score(y[te], p):.4f} | max|p - feat_p.pkl| = {diff:.2e} | numpy export max diff {d2:.2e}")
    VAL[pk] = npm
# ---- (1) frozen predictors ---------------------------------------------------------------------------------------
FRZ = {}; OOF = {}
for pk, H in (("p30", 30), ("p120", 120)):
    y = (tc <= H).astype(int)
    m = gb().fit(X[frz], y[frz])
    fn = f"{MD}/{pk}.json"; save_model(m, fn); npm = NPModel(fn)
    p_all = m.predict_proba(X)[:, 1]; d2 = np.abs(npm.proba(X) - p_all).max()
    log(f"FROZEN {pk}: fit rows {frz.sum()} n_iter {m.n_iter_} in-sample AUC {roc_auc_score(y[frz], p_all[frz]):.4f} | numpy export max diff {d2:.2e} | sha256 {sha256(fn)}")
    SHA.append((os.path.basename(fn), sha256(fn), f"{pk} predictor, {frz.sum()} rows, {m.n_iter_} iterations"))
    FRZ[pk] = npm
    # leave-one-day-out OOF (needed as the continuation model's p120 feature)
    oof = np.full(len(X), np.nan)
    for d in sorted(set(day[frz])):
        fit = frz & (day != d); pred = frz & (day == d)
        if fit.sum() < 100 or pred.sum() == 0: continue
        oof[pred] = gb().fit(X[fit], y[fit]).predict_proba(X[pred])[:, 1]
    OOF[pk] = oof
    log(f"   OOF {pk} AUC over frozen rows {roc_auc_score(y[frz & ~np.isnan(oof)], oof[frz & ~np.isnan(oof)]):.4f}")
# ---- (2) continuation models (m3 code) -------------------------------------------------------------------------------
from glib import Tape
T = Tape(); hour_ix = names.index("hour")
rows_cache = {}
def feats_for(i, p0):
    r = meta[i]; m = r["mint"]
    return ck_feats(T.trades(m), r["k"], r["V"], float(p0), float(X[i, hour_ix]))
# validation continuation model: TRAIN rows, p0 = feat_p.pkl p120 (OOF on train) -- exactly m3
XX, YY = [], []
for i in np.nonzero(tr)[0]:
    for sec, v in feats_for(i, PP["p120"][i]).items():
        if v is not None: XX.append(v[0]); YY.append(v[1])
cm = cont().fit(np.array(XX), np.array(YY)); fn = f"{MD}/val_cont.json"
save_model(cm, fn, extra=["V", "vsol", "vs_ratio", "sol_left", "net10", "net30", "nb10", "nb30", "sec", "p120", "hour", "ddmax"])
npm = NPModel(fn); d2 = np.abs(npm.proba(np.array(XX)) - cm.predict_proba(np.array(XX))[:, 1]).max()
log(f"VAL cont: {len(XX)} checkpoints (train rows) n_iter {cm.n_iter_} | numpy export max diff {d2:.2e}")
# frozen continuation model: rows < CUT, p0 = leave-one-day-out p120
XX, YY = [], []
for i in np.nonzero(frz)[0]:
    p0 = OOF["p120"][i]
    if np.isnan(p0): continue
    for sec, v in feats_for(i, p0).items():
        if v is not None: XX.append(v[0]); YY.append(v[1])
cm = cont().fit(np.array(XX), np.array(YY)); fn = f"{MD}/cont.json"
save_model(cm, fn, extra=["V", "vsol", "vs_ratio", "sol_left", "net10", "net30", "nb10", "nb30", "sec", "p120", "hour", "ddmax"])
npm = NPModel(fn); d2 = np.abs(npm.proba(np.array(XX)) - cm.predict_proba(np.array(XX))[:, 1]).max()
log(f"FROZEN cont: {len(XX)} checkpoints n_iter {cm.n_iter_} | numpy export max diff {d2:.2e} | sha256 {sha256(fn)}")
SHA.append(("cont.json", sha256(fn), f"continuation model (pd stop), {len(XX)} checkpoints, {cm.n_iter_} iterations"))
# ---- (4) landing quantiles ----------------------------------------------------------------------------------------------
lc = json.load(open("/home/moiz/sniper-data/dipml/livecal.json"))
d = np.array(lc["deltas"], float); d = d * (66.0 / (np.median(d) * mplib.SLOT_MS))
DLY = np.quantile(d, (np.arange(10) + 0.5) / 10)
json.dump(dict(dly_slots=DLY.tolist(), dly_ms=(DLY * mplib.SLOT_MS).tolist(), source="/home/moiz/sniper-data/dipml/livecal.json deltas, rescaled to median 66 ms (m3)"), open(f"{MD}/dly.json", "w"))
SHA.append(("dly.json", sha256(f"{MD}/dly.json"), "landing delays (slots): " + ", ".join(f"{x:.4f}" for x in DLY)))
# ---- stores -------------------------------------------------------------------------------------------------------------
M = T.M; users = M["users"]; mints = M["mints"]
Wn = np.load(MIG + "/wallets.npz")
uh = np.array([h64(users[k]) for k in Wn["user"]], np.uint64); mh = np.array([h64(mints[k]) for k in Wn["mint"]], np.uint64)
cmp_bt = {m: c["bt"] for m, c in M["cmp"].items()}
cb = np.array([cmp_bt.get(mints[k], 0) for k in Wn["mint"]], np.int64)
W_ = np.zeros(len(uh), mplib.WDT)
W_["u"] = uh; W_["m"] = mh; W_["t_end"] = Wn["t_end"]; W_["t_first"] = Wn["t_first"]; W_["pnl"] = Wn["pnl"]; W_["sol_in"] = Wn["sol_in"]
W_["flags"] = (Wn["grad"] * mplib.F_GRAD + Wn["neargrad"] * mplib.F_NEAR + Wn["poolopen"] * mplib.F_PO + Wn["completer"] * mplib.F_CP + Wn["compslot"] * mplib.F_CS).astype(np.uint8)
W_["ntr"] = np.minimum(Wn["ntr"], 65535); W_["cmp_bt"] = cb
np.savez_compressed(D + "/wstore.npz", W=W_)
log(f"wstore: {len(W_)} trips, {len(np.unique(uh))} wallets, t_end max {pkt(int(W_['t_end'].max())).strftime('%m-%d %H:%M')} PKT, {os.path.getsize(D + '/wstore.npz') / 1e6:.0f} MB")
# check: store lookups reproduce m1's wallet features on a sample of rows
ws = mplib.WStore(D + "/wstore.npz")
rng = np.random.default_rng(0); samp = rng.choice(np.nonzero(use)[0], 300, replace=False); worst = 0.0
for i in samp:
    r = meta[i]; rows = T.trades(r["mint"]); k = r["k"]; t = int(rows["bt"][k])
    uu = [h64(users[int(rows["user"][k])])]
    st = ws.wstats(uu, t, h64(r["mint"]))
    for kk, nm in (("n", "cx_n"), ("pnl", "cx_pnl"), ("ng", "cx_ng"), ("ngg", "cx_ngg"), ("cp", "cx_cp"), ("po", "cx_po")):
        worst = max(worst, abs(float(st[kk][0]) - float(X[i, names.index(nm)])))
log(f"wstore check vs m1 crossing-wallet features on 300 rows: max abs diff {worst:.4f}")
crs = []
for m, d_ in M["cr"].items():
    c = M["cmp"].get(m); crs.append((h64(m), h64(d_["creator"]), d_["bt"], int(M["mx"].get(m, 0) >= 78e9), c["bt"] if c else 0))
Cr = np.array(crs, mplib.CDT); np.savez_compressed(D + "/cstore.npz", C=Cr)
cs = mplib.CStore(D + "/cstore.npz"); worst = 0
for i in samp:
    r = meta[i]; cr = M["cr"][r["mint"]]; a = cs.cstats(cr["creator"], cr["bt"])
    b = tuple(int(X[i, names.index(nm)]) for nm in ("dev_prior_n", "dev_prior_near", "dev_prior_grad"))
    worst = max(worst, max(abs(x - y) for x, y in zip(a, b)))
log(f"cstore: {len(Cr)} creates; check vs m1 creator features on 300 rows: max abs diff {worst}")
SHA.append(("../wstore.npz", sha256(D + "/wstore.npz"), f"initial wallet store, {len(W_)} trips (migrate wallets.npz, through 10-28 21:26 PKT)"))
SHA.append(("../cstore.npz", sha256(D + "/cstore.npz"), f"initial creator store, {len(Cr)} creates"))
# ---- feature-level check of mplib.features vs m1 on the grad tape (same tape -> must be identical) ---------------------
class GT:  # adapter: grad Tape with the WTape attributes features() needs
    pass
worst = 0.0; nchk = 0
for i in samp[:120]:
    r = meta[i]
    if r["V"] != mplib.V or r["ncross"] != 0: continue
    rows = T.trades(r["mint"])
    T.strings = np.array(users, dtype=object); T.M = M
    f = mplib.features(T, r["mint"], rows, r["k"], ws, cs)
    v = np.array([float(f[q]) for q in names], np.float32)
    worst = max(worst, float(np.abs(v - X[i]).max())); nchk += 1
log(f"features check (mplib.features vs feat.pkl on {nchk} V=105 first-crossing rows of the grad tape): max abs diff {worst:.4g}")
with open(os.path.dirname(os.path.abspath(__file__)) + "/FROZEN_SHA.md", "w") as f:
    f.write(f"# migpaper frozen artefacts ({pkt(int(time.time())).strftime('%m-%d %H:%M')} PKT) — never refit during the run\n\n")
    f.write("| file (data/migpaper/models/) | sha256 | what |\n|---|---|---|\n")
    for a, b, c in SHA: f.write(f"| {a} | {b} | {c} |\n")
    f.write("\nFit log:\n```\n" + "\n".join(LOG) + "\n```\n")
print("done", f"{time.time() - t0:.0f}s")

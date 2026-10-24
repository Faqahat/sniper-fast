#!/usr/bin/env python3
# GDM step 6: FREEZE the chosen rule (decided on validation only; see RESULTS.md). Model = label yc (>= 10 distinct generic
# buyers 2-10 s after the create), feature set LM (liveh3 minus hour + GDM walk-forward history + metadata), histogram GBDT
# trained on ALL rows (R1 + R2 until 10-23 05:34 PKT) in time order: first 80% train, last 20% early stop; pick threshold =
# top 3% of that last-20% slice. 5-seed bag (mean raw score). Fallback model L (no metadata) frozen the same way. Rule = FINAL-2 pick OR GDM pick.
# Nothing after 10-23 08:50 PKT exists in the inputs (latest input file: 08:35 PKT; feature table ends 05:34 PKT).
import sys, json, hashlib, time, datetime
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/gdm")
import numpy as np, common
from common import binize, fit, pred
Z, M = common.load(); X = Z["X"]; bt = Z["bt"]; names = M["names"]; G = M["groups"]
FS = {"LM": G["live"] + G["gdm"] + G["meta"], "L": G["live"] + G["gdm"]}
y = (Z["y_c210"] >= 10).astype(float)
o = np.argsort(bt, kind="stable"); cut = bt[o[int(len(o) * 0.8)]]; TR = bt < cut; VA = bt >= cut
def edges_of(Xs, tr):
    E = []
    for j in range(Xs.shape[1]):
        x = Xs[:, j]; xt = x[tr & ~np.isnan(x)]
        E.append(np.unique(np.quantile(xt, np.linspace(0, 1, 33)[1:-1])).tolist() if len(xt) else [])
    return E
def score_frozen(F, xrow):
    """same semantics as the live FINAL-2 scorer (ops/shadow/paper_live.py score): NaN -> bin 0, else 1 + #edges <= value"""
    f = F["F0"]; bins = []
    for v, e in zip(xrow, F["edges"]):
        if v is None or (isinstance(v, float) and np.isnan(v)): bins.append(0); continue
        lo, hi = 0, len(e)
        while lo < hi:
            mid = (lo + hi) // 2
            if e[mid] <= v: lo = mid + 1
            else: hi = mid
        bins.append(lo + 1)
    for t in F["trees"]:
        n = t
        while "w" not in n: n = n["l"] if bins[n["f"]] <= n["b"] else n["r"]
        f += F["lr"] * n["w"]
    return f
models = {}
SEEDS = (0, 1, 2, 3, 4)                      # 5-seed bag: the GDM score is the MEAN of the 5 raw scores
for nm, fl in FS.items():
    cols = [names.index(k) for k in fl]; Xs = X[:, cols]; Bm = binize(Xs, TR); E = edges_of(Xs, TR); bag = []; fs_ = []
    for sd in SEEDS:
        trees, f = fit(Bm, y, TR, VA, rounds=600, lr=0.05, depth=3, seed=sd); fs_.append(f)
        bag.append(dict(trees=trees, n_trees=len(trees)))
    f = np.mean(fs_, 0); thr = float(np.quantile(f[VA], 0.97))
    F = dict(features=fl, edges=E, F0=float(np.log(y[TR].mean() / (1 - y[TR].mean()))), lr=0.05, bag=bag, threshold_top3=thr,
             val_rows=int(VA.sum()), train_rows=int(TR.sum()), score="mean over bag of (F0 + lr * sum of tree leaves)")
    chk = np.array([np.mean([score_frozen(dict(F0=F["F0"], lr=0.05, edges=E, trees=b["trees"]), Xs[i]) for b in bag]) for i in range(0, len(Xs), 97)])
    assert np.allclose(chk, f[::97], atol=1e-9), "frozen scorer mismatch"
    F["pick_rate_val"] = float((f[VA] >= thr).mean()); F["pick_rate_all"] = float((f >= thr).mean())
    models[nm] = F
    np.save(f"{common.OUT}/models/frozen_{nm}_score.npy", f)
    print(f"{nm}: trees {[b['n_trees'] for b in bag]}, threshold {thr:+.4f}, pick rate val {F['pick_rate_val']:.3f} all {F['pick_rate_all']:.3f}; scorer check ok")
W = json.load(open(f"{common.CORE}/gf_wallets.json"))
SNIPER = sorted(u for u, v in W.items() if v[1] >= 5 and v[1] >= 0.5 * v[0]); PRO = []
for p_ in ("9Sh2fd", "DGmspi", "D24ipY", "dKMjeG", "CWiNFA", "9qz7cW", "FiFawH", "AHwJSn", "4yFAz"):
    c = [u for u in W if u.startswith(p_)]
    if c: PRO.append(max(c, key=lambda u: W[u][0]))
def sha(fn): return hashlib.sha256(open(fn, "rb").read()).hexdigest()
PKT = datetime.timezone(datetime.timedelta(hours=5)); now = time.time()
fz = dict(
    id="FRZ-GDM-U", frozen_at_unix=int(now), frozen_at_pkt=datetime.datetime.fromtimestamp(now, PKT).strftime("%Y-%m-%d %H:%M PKT"),
    data_cutoff="inputs end 10-23 05:34:51 PKT (feature table) / 07:57 PKT (trades); nothing after 08:50 PKT was read",
    rule="BUY if (FINAL-2 live pick: ops/shadow/final_config2.json, unchanged) OR (GDM score >= threshold_top3 AND guards); then the become-them mechanics",
    primary_model="LM", fallback_model="L (use when token metadata is not available at bundle close)",
    guards=["payer_is_creator == 1", "not (glued_n == 0 and dev_buy < 1 SOL)", "SOL-quoted, not mayhem"],
    mechanics=dict(size_sol=0.5, entry="right after the dev's glued bundle, only if first: price before our buy <= post-bundle price x 1.005",
                   exit_primary="sell all at 8 s (rp t8)", exit_secondary="10 s (t10)", landings_to_report_ms=[30, 45, 75],
                   variants_to_report=["slip", "proafter_slip", "nosnip"], costs=["today: 2% overhead, -0.005 per failed buy", "pro: 0.6% overhead (+0.007 per 0.5 SOL fill), -0.003 per failed buy"]),
    label="yc: >= 10 distinct generic buyers (not one of the 321 sniper / 9 pro wallets, not dev/bundle) 2-10 s after the create",
    features_code="gdm/features.py (gdm_feats: walk-forward history from launches >= 10 min older; labels from gdm/labels_pass.py)",
    selection="config + cut chosen by the minimum over 4 time-ordered validation folds (R1 60-80%, R1 80-100%, R2 60-80%, R2 80-100%) of the mean "
              "(30/45 ms x t8/t10 x ps/ns) PRO-cost total: yc / LM / top 3% (gdm/cv_rows.json); then a 5-seed bag for stability (gdm/bag_eval.py)",
    replay_evidence_pro_costs_t8_45ms_proafter_slip=dict(R2_union_bag_trainR1=8.17, R2_final2=4.82, R1_union_bag_trainR2=4.27, R1_final2_partly_in_sample=3.42, source="gdm/fin_R2.json, gdm/fin_R1.json"),
    final2_files_sha256={f: sha(f) for f in ("/home/moiz/sniper/ops/shadow/final_config2.json", f"{common.P}/frozen_live3_fsell.json", f"{common.P}/frozen_dump2.json")},
    wallet_lists=dict(note="used by the label and the walk-forward history features (generic = not these, not dev/bundle)", sniper=SNIPER, pro=sorted(PRO)),
    forward_test="1) labels_pass.py + features.py on the new launches (history = everything >= 10 min older, incl. R1/R2); "
                 "2) GDM score = bag mean with models[primary]; pick if score >= threshold_top3 and guards; 3) UNION with FINAL-2's live picks; "
                 "4) core/become_eval.py LANDS=30,45,75 guard 1.005, report slip / proafter_slip / nosnip at t8 (and t10), today + pro costs",
    models=models)
fn = "/home/moiz/sniper/ops/overnight/dryrun/frozen_gdm.json"
s = json.dumps(fz, separators=(",", ":"))
open(fn, "w").write(s)
h = hashlib.sha256(s.encode()).hexdigest(); open(fn + ".sha256", "w").write(h + "\n")
open("/home/moiz/sniper/ops/overnight/gdm/frozen_gdm.sha256", "w").write(f"{h}  {fn}\n")
print("frozen ->", fn, "sha256", h)

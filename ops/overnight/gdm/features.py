#!/usr/bin/env python3
# GDM step 2 (read-only, offline): feature matrix, one row per launch, everything known at BUNDLE CLOSE.
#  - liveh3: FINAL-2's 61 live features (same extraction as core/bt_train.py)
#  - rpc:    creator / funder lookups (need an RPC call at the create): cr_prior_n, cr_age_s, cr_last_tx_s, fund_amt, ...
#  - meta:   token metadata (needs a fast URI fetch): has_tw, has_web, desc_len, tw_status, ...
#  - gdm:    our own create stream + WALK-FORWARD generic-demand history (only launches >= 10 min older than this one):
#            deployer's previous launches (count, relaunch gap, their market label a10 / generic buyers), bundle wallets'
#            previous launches, same-name launches (count in the last hour = "first of name"; their outcomes),
#            fingerprint / uri-host target rates (10 min .. 3 h old), market heat (share of launches 10-70 min old with
#            generic demand), dev+bundle SOL, pro hint flags.
# Look-ahead columns (slot_*, fslot_*, f1s_/f5s_/f15s_, eb1s_/eb5s_, px_*, peak_*, y_*, vol_sol, holders_proxy, n_trades,
# max_vsol, graduated, ...) are never used. hour_utc is dropped (R1 and R2 cover disjoint UTC hours).
# usage: python3 -I features.py -> gdm/feats.npz + gdm/feats_meta.json
import json, gzip, bisect, collections, math, re
import numpy as np
P = "/home/moiz/sniper-data/collect/paper"; CORE = "/home/moiz/sniper/ops/overnight/core"; OUT = "/home/moiz/sniper/ops/overnight/gdm"
LIVE = json.load(open(f"{P}/frozen_live3_fsell.json"))["features"]
import os
SFX = os.environ.get("GDM_SUFFIX", "")
LAB = json.load(open(f"{OUT}/labels{SFX}.json"))["res"]; LS = json.load(open(f"{CORE}/gf_launches.json"))
RPC = ["cr_prior_n", "cr_prior_fail", "cr_age_s", "cr_last_tx_s", "cr_recent_creates", "cr_same_name_before", "fund_amt", "fd_creators_so_far", "fd_is_creator", "h_fd_n", "h_fd_wins"]
META = ["meta_ok", "desc_len", "has_tw", "has_tg", "has_web", "tw_status", "tw_community", "web_same_as_tw", "meta_keys", "created_on==https://pump.fun", "created_on==pump.fun",
        "created_on==", "show_name==True", "show_name==None"]
T = {}
for l in gzip.open(f"{P}/table_dump.jsonl.gz", "rt"):
    r = json.loads(l)
    if r["mint"] in LAB and r["mint"] in LS and r.get("quote_sol") == 1 and not r.get("mayhem"): T[r["mint"]] = r
def fval(r, k):
    if "==" in k: c, v = k.split("==", 1); return float(str(r.get(c) if r.get(c) is not None else "None") == v) if c != "fp" else float(str(r.get(c)) == v)
    x = r.get(k); return np.nan if x is None or isinstance(x, (str, list)) else float(x)
# ---- walk-forward history over ALL labelled launches (R1 + R2, incl. those after the table ends: never used for rows)
ALL = sorted(LAB, key=lambda m: LAB[m]["bt"])
bts = np.array([LAB[m]["bt"] for m in ALL], float)
def nm(s): return re.sub(r"\s+", " ", (s or "").strip().lower())
name_of = {m: nm(T[m]["name"]) if m in T else None for m in ALL}
# names for launches outside the table (needed only as history): from the run's launches.jsonl
import os
for run in ("run_20261021_2207", "run_20261022_1543"):
    for l in open(f"/home/moiz/sniper-data/collect/{run}/launches.jsonl"):
        try: c = json.loads(l)
        except Exception: continue
        if c.get("mint") in LAB and name_of.get(c["mint"]) is None: name_of[c["mint"]] = nm(c.get("name"))
ya = {m: float(LAB[m]["a"][3] >= 1.05) for m in ALL}; a10 = {m: LAB[m]["a"][3] for m in ALL}; cg = {m: LAB[m]["c"][0] for m in ALL}
byd = collections.defaultdict(list); byn = collections.defaultdict(list); byw = collections.defaultdict(list)
byfp = collections.defaultdict(list); byuh = collections.defaultdict(list)
for m in ALL:
    bt = LAB[m]["bt"]; byd[LS[m]["dep"]].append((bt, m)); byn[name_of.get(m)].append((bt, m))
    for w in LAB[m]["bw"]: byw[w].append((bt, m))
    if m in T: byfp[T[m]["fp"]].append((bt, m)); byuh[T[m]["uri_host"]].append((bt, m))
def older(lst, bt, lag, span=None):
    """entries with time <= bt - lag (and >= bt - span)"""
    k = bisect.bisect_right(lst, (bt - lag, "~")); j = bisect.bisect_left(lst, (bt - span, "")) if span else 0
    return lst[j:k]
def before(lst, bt, m):
    k = bisect.bisect_left(lst, (bt, m)); return lst[:k]
LAG = 600
GEN = ["dep_n_all", "dep_gap_s", "dep_n10", "dep_ya_last", "dep_a10_last", "dep_ya_rate", "dep_a10_mean", "dep_c_mean", "dep_raw10_last",
       "bw_n10", "bw_ya_rate", "bw_a10_mean", "bw_c_mean", "name_n1h", "name_n10", "name_ya_rate", "name_c_mean",
       "fp_n3h", "fp_te", "uh_n3h", "uh_te", "heat_ya_60", "heat_c_60", "heat_n_60", "dev_plus_bundle", "dpb_2_20", "glued_1", "fresh_dep", "fp_fifaw", "relaunch_lt60"]
PRIOR_K = 20.0
def gdm_feats(m):
    r = T[m]; bt = LAB[m]["bt"]; d = LS[m]["dep"]; f = {}
    dl = before(byd[d], bt, m); f["dep_n_all"] = len(dl); f["dep_gap_s"] = min(bt - dl[-1][0], 86400) if dl else np.nan
    d10 = older(dl, bt, LAG); f["dep_n10"] = len(d10)
    f["dep_ya_last"] = ya[d10[-1][1]] if d10 else np.nan; f["dep_a10_last"] = min(a10[d10[-1][1]], 5) if d10 else np.nan
    f["dep_ya_rate"] = np.mean([ya[x] for _, x in d10]) if d10 else np.nan; f["dep_a10_mean"] = np.mean([min(a10[x], 5) for _, x in d10]) if d10 else np.nan
    f["dep_c_mean"] = np.mean([cg[x] for _, x in d10]) if d10 else np.nan; f["dep_raw10_last"] = min(LS[d10[-1][1]]["m10"], 5) if d10 else np.nan
    bw = set(LAB[m]["bw"]); seen = {}
    for w in bw:
        for t, x in older(byw[w], bt, LAG): seen[x] = t
    xs = list(seen); f["bw_n10"] = len(xs)
    f["bw_ya_rate"] = np.mean([ya[x] for x in xs]) if xs else np.nan; f["bw_a10_mean"] = np.mean([min(a10[x], 5) for x in xs]) if xs else np.nan
    f["bw_c_mean"] = np.mean([cg[x] for x in xs]) if xs else np.nan
    nl = before(byn[name_of[m]], bt, m)
    f["name_n1h"] = sum(1 for t, _ in nl if t >= bt - 3600); n10 = older(nl, bt, LAG, 86400); f["name_n10"] = len(n10)
    f["name_ya_rate"] = np.mean([ya[x] for _, x in n10]) if n10 else np.nan; f["name_c_mean"] = np.mean([cg[x] for _, x in n10]) if n10 else np.nan
    G0 = HEAT.get(m, (np.nan, np.nan, 0))
    for key, lst, nmk in ((r["fp"], byfp, "fp"), (r["uri_host"], byuh, "uh")):
        h = older(lst[key], bt, LAG, 3 * 3600); f[f"{nmk}_n3h"] = len(h)
        base = G0[0] if not np.isnan(G0[0]) else 0.2
        f[f"{nmk}_te"] = (sum(ya[x] for _, x in h) + PRIOR_K * base) / (len(h) + PRIOR_K)
    f["heat_ya_60"], f["heat_c_60"], f["heat_n_60"] = G0
    dpb = (r.get("dev_buy") or 0) + (r.get("glued_sol") or 0); f["dev_plus_bundle"] = dpb; f["dpb_2_20"] = float(2 <= dpb <= 20)
    f["glued_1"] = float((r.get("glued_n") or 0) == 1); f["fresh_dep"] = float(len(dl) == 0); f["fp_fifaw"] = float(r["fp"] == "10000|600000|0")
    f["relaunch_lt60"] = float(bool(dl) and bt - dl[-1][0] < 60)
    return f
# market heat: launches 10..70 min older
HEAT = {}
cy = np.cumsum([0] + [ya[m] for m in ALL]); cc = np.cumsum([0] + [cg[m] for m in ALL])
for m in T:
    bt = LAB[m]["bt"]; j = bisect.bisect_left(bts, bt - 4200); k = bisect.bisect_right(bts, bt - LAG); n = k - j
    HEAT[m] = ((cy[k] - cy[j]) / n, (cc[k] - cc[j]) / n, n) if n >= 30 else (np.nan, np.nan, n)
rows = sorted(T, key=lambda m: (LAB[m]["bt"], T[m].get("S") or 0))
LIVE_NOHR = [k for k in LIVE if k != "hour_utc"]
names = LIVE_NOHR + RPC + META + GEN
X = np.full((len(rows), len(names)), np.nan, np.float64)
for i, m in enumerate(rows):
    r = T[m]; g = gdm_feats(m)
    X[i] = [fval(r, k) for k in LIVE_NOHR + RPC + META] + [g[k] for k in GEN]
lab = LAB
Y = dict(a10=np.array([lab[m]["a"][3] for m in rows]), a8=np.array([lab[m]["a"][2] for m in rows]), a5=np.array([lab[m]["a"][1] for m in rows]),
         c210=np.array([lab[m]["c"][0] for m in rows], float), amax10=np.array([lab[m]["amax10"] for m in rows]))
guard = np.array([float(T[m].get("payer_is_creator") == 1 and not ((T[m].get("glued_n") or 0) == 0 and (T[m].get("dev_buy") or 0) < 1)) for m in rows])
np.savez_compressed(f"{OUT}/feats{SFX}.npz", X=X, bt=np.array([LAB[m]["bt"] for m in rows], float), run=np.array([LAB[m]["run"] for m in rows]),
                    guard=guard, **{f"y_{k}": v for k, v in Y.items()})
json.dump(dict(mints=rows, names=names, groups=dict(live=LIVE_NOHR, rpc=RPC, meta=META, gdm=GEN)), open(f"{OUT}/feats_meta{SFX}.json", "w"))
print("rows", len(rows), "features", len(names), {k: int(sum(1 for m in rows if LAB[m]['run'] == k)) for k in ("R1", "R2")})
for k in GEN: 
    j = names.index(k); v = X[:, j]; print(f"  {k:16s} nan {np.isnan(v).mean():.2f} mean {np.nanmean(v):.3f}")

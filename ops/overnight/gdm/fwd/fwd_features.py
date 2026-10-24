#!/usr/bin/env python3
# GDM forward test, step 4: the frozen model's feature rows for launches created in [lo, hi), with the SAME code as
# gdm/features.py (liveh3 minus hour + rpc + meta + walk-forward GDM history). History = every labelled launch >= 10 min
# older: R1 + R2 (gdm/labels.json, core/gf_launches.json, until lab_cut) + forward (fwd/labels_fwd.json from lab_cut on).
# usage: python3 -I fwd_features.py <table.jsonl.gz> <labels_fwd.json> <lab_cut> <lo> <hi> <out prefix>
import sys, json, gzip, bisect, collections, re, os
import numpy as np
TAB, LFWD, LAB_CUT, LO, HI, OUTP = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), sys.argv[6]
P = "/home/moiz/sniper-data/collect/paper"; CORE = "/home/moiz/sniper/ops/overnight/core"; GDM = "/home/moiz/sniper/ops/overnight/gdm"
META0 = json.load(open(f"{GDM}/feats_meta.json")); NAMES = META0["names"]; G0 = META0["groups"]
LAB = {m: v for m, v in json.load(open(f"{GDM}/labels.json"))["res"].items() if v["bt"] < LAB_CUT}
LS = {m: v for m, v in json.load(open(f"{CORE}/gf_launches.json")).items() if v["bt"] < LAB_CUT}
FW = json.load(open(LFWD))
LAB.update({m: v for m, v in FW["res"].items() if v["bt"] >= LAB_CUT}); LS.update({m: v for m, v in FW["ls"].items() if v["bt"] >= LAB_CUT})
T = {}
for l in gzip.open(TAB, "rt"):
    r = json.loads(l)
    if r["mint"] in LAB and r["mint"] in LS and r.get("quote_sol") == 1 and not r.get("mayhem"): T[r["mint"]] = r
def fval(r, k):
    if "==" in k: c, v = k.split("==", 1); return float(str(r.get(c) if r.get(c) is not None else "None") == v) if c != "fp" else float(str(r.get(c)) == v)
    x = r.get(k); return np.nan if x is None or isinstance(x, (str, list)) else float(x)
# ---- identical to gdm/features.py from here (history over ALL labelled launches) ----
ALL = sorted(LAB, key=lambda m: LAB[m]["bt"])
bts = np.array([LAB[m]["bt"] for m in ALL], float)
def nm(s): return re.sub(r"\s+", " ", (s or "").strip().lower())
name_of = {m: nm(T[m]["name"]) if m in T else None for m in ALL}
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
    k = bisect.bisect_right(lst, (bt - lag, "~")); j = bisect.bisect_left(lst, (bt - span, "")) if span else 0
    return lst[j:k]
def before(lst, bt, m):
    k = bisect.bisect_left(lst, (bt, m)); return lst[:k]
LAG = 600; PRIOR_K = 20.0
GEN = G0["gdm"]
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
    G = HEAT.get(m, (np.nan, np.nan, 0))
    for key, lst, nmk in ((r["fp"], byfp, "fp"), (r["uri_host"], byuh, "uh")):
        h = older(lst[key], bt, LAG, 3 * 3600); f[f"{nmk}_n3h"] = len(h)
        base = G[0] if not np.isnan(G[0]) else 0.2
        f[f"{nmk}_te"] = (sum(ya[x] for _, x in h) + PRIOR_K * base) / (len(h) + PRIOR_K)
    f["heat_ya_60"], f["heat_c_60"], f["heat_n_60"] = G
    dpb = (r.get("dev_buy") or 0) + (r.get("glued_sol") or 0); f["dev_plus_bundle"] = dpb; f["dpb_2_20"] = float(2 <= dpb <= 20)
    f["glued_1"] = float((r.get("glued_n") or 0) == 1); f["fresh_dep"] = float(len(dl) == 0); f["fp_fifaw"] = float(r["fp"] == "10000|600000|0")
    f["relaunch_lt60"] = float(bool(dl) and bt - dl[-1][0] < 60)
    return f
rows = sorted((m for m in T if LO <= LAB[m]["bt"] < HI), key=lambda m: (LAB[m]["bt"], T[m].get("S") or 0))
HEAT = {}
cy = np.cumsum([0] + [ya[m] for m in ALL]); cc = np.cumsum([0] + [cg[m] for m in ALL])
for m in rows:
    bt = LAB[m]["bt"]; j = bisect.bisect_left(bts, bt - 4200); k = bisect.bisect_right(bts, bt - LAG); n = k - j
    HEAT[m] = ((cy[k] - cy[j]) / n, (cc[k] - cc[j]) / n, n) if n >= 30 else (np.nan, np.nan, n)
BASE = G0["live"] + G0["rpc"] + G0["meta"]
assert NAMES == BASE + GEN
X = np.full((len(rows), len(NAMES)), np.nan, np.float64)
for i, m in enumerate(rows):
    r = T[m]; g = gdm_feats(m); X[i] = [fval(r, k) for k in BASE] + [g[k] for k in GEN]
guard = np.array([float(T[m].get("payer_is_creator") == 1 and not ((T[m].get("glued_n") or 0) == 0 and (T[m].get("dev_buy") or 0) < 1)) for m in rows])
np.savez_compressed(OUTP + ".npz", X=X, bt=np.array([LAB[m]["bt"] for m in rows], float), guard=guard)
json.dump(dict(mints=rows, names=NAMES), open(OUTP + "_meta.json", "w"))
print(f"forward feature rows: {len(rows)} (bt in [{LO:.0f}, {HI:.0f})), history launches {len(ALL)}", flush=True)

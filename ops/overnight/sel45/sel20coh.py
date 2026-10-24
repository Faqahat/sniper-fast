#!/usr/bin/env python3
# Snipe-side analog of the dip model: per launch, value of a 0.5 SOL buy first after the bundle at LAT ms (guard 0.5%, pros'
# later buys removed, follower slippage) with exit EX, or -0.005 if the guard refuses. Features: FINAL-2's 61 create-time
# features (paper table_dump, to 10-23 05:34 PKT). 6-block time CV, top-k by score; FINAL-2 picks on the same blocks; and the
# same selections with the bot cohort's later buys removed (nocw).
import sys, os, json, gzip, math
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
import gbdt_np as G
P = "/home/moiz/sniper-data/collect/paper"; CORE = "/home/moiz/sniper/ops/overnight/core"
LAT = os.environ.get("LAT", "20"); EX = os.environ.get("EX", "s4"); K = 4
C = json.load(open("/home/moiz/sniper/ops/shadow/final_config2.json"))
M = json.load(open(f"{P}/{C['model_file']}")); MV = json.load(open(f"{P}/{C['veto_file']}")); THR = M["thresholds"][C["top"]]
src = open("/home/moiz/sniper/ops/shadow/paper_live.py").read()
g = {"math": math, "M": M}; exec(src[src.index("def score(x, M=M):"):src.index("# ---- shadow engine timeline")], g); score = g["score"]
FK = M["features"]
def fval(x, k):
    if "==" in k: a, v = k.split("==", 1); return 1.0 if str(x.get(a)) == v else 0.0
    v = x.get(k); return float(v) if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)) else float("nan")
def guard_ok(r): return r.get("payer_is_creator") == 1 and not ((r.get("glued_n") or 0) == 0 and (r.get("dev_buy") or 0) < 1)
AB = json.load(open(f"{CORE}/allbe20.json"))
import glob, collections
COH = set(json.load(open("/home/moiz/sniper/ops/overnight/dip/cohort_R1.json")))
early = collections.defaultdict(set)
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"):
    for line in gzip.open(f, "rt"):
        q = json.loads(line)
        if q[0] in COH and q[4] is not None and q[4] <= 47: early[q[1]].add(q[0])
bydep = collections.defaultdict(list)
for r_ in (json.loads(l) for l in gzip.open(f"{P}/table_dump.jsonl.gz", "rt")):
    if r_.get("bt"): bydep[r_.get("creator")].append((r_["bt"], r_["mint"]))
for d in bydep: bydep[d].sort()
def coh_hist(r):
    prev = [m for bt, m in bydep.get(r.get("creator"), []) if bt < r["bt"] - 60]
    return float(len(set().union(*[early.get(m, set()) for m in prev]))) if prev else -1.0
rows = []
for l in gzip.open(f"{P}/table_dump.jsonl.gz", "rt"):
    r = json.loads(l)
    if r.get("quote_sol") != 1 or not r.get("bt") or r.get("mayhem") or r["mint"] not in AB or not guard_ok(r): continue
    a = AB[r["mint"]][LAT]
    if a["pa"] is None or AB[r["mint"]]["run"] != "R2": continue
    v = a["pa"]["p"][EX] if a["pa"]["f"] else -0.005
    vc = (a["nocw"]["p"][EX] if a["nocw"]["f"] else -0.005) if a.get("nocw") else v
    rows.append((r, v, vc))
rows.sort(key=lambda t: t[0]["bt"])
X = np.array([[fval(r, k) for k in FK] + ([coh_hist(r)] if os.environ.get("COHF") else []) for r, _, _ in rows]); V = np.array([t[1] for t in rows]); VC = np.array([t[2] for t in rows]); y = (V > 0).astype(float)
f2 = np.array([score(r) >= THR and score(r, MV) < C["veto_cut"] for r, _, _ in rows])
n = len(rows); blk = np.minimum((np.arange(n) * K) // n, K - 1); rng = np.random.default_rng(3)
print(f"LAT {LAT} ms exit {EX}: {n} guarded launches; base mean {V.mean():+.4f}")
tot = {q: [0.0, 0.0] for q in (0.02, 0.05)}; f2t = [0.0, 0.0]
for b in range(K):
    trall = blk != b; va = trall & (rng.random(n) < 0.15); tr = trall & ~va; te = blk == b
    Bm = G.binize(X, tr); trees, f = G.fit(Bm, y, tr, va, rounds=300, lr=0.05, depth=3)
    cells = []
    for q in (0.02, 0.05):
        thr = np.quantile(f[va], 1 - q); st = te & (f >= thr)
        tot[q][0] += V[st].sum(); tot[q][1] += VC[st].sum()
        cells.append(f"top{q:.0%} n {st.sum():3d} {V[st].sum():+6.2f} (no cohort {VC[st].sum():+6.2f})")
    sf = te & f2; f2t[0] += V[sf].sum(); f2t[1] += VC[sf].sum()
    print(f"  block {b}: AUC {G.auc(y[te], f[te]):.3f} | " + " | ".join(cells) + f" | FINAL-2 n {sf.sum():3d} {V[sf].sum():+6.2f} (no cohort {VC[sf].sum():+6.2f})")
print("  totals: " + " | ".join(f"top{q:.0%} {v[0]:+.2f} (no cohort {v[1]:+.2f})" for q, v in tot.items()) + f" | FINAL-2 {f2t[0]:+.2f} (no cohort {f2t[1]:+.2f})")

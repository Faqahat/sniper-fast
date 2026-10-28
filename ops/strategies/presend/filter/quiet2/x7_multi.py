#!/usr/bin/env python3
"""QUIET2 step 7: multiple testing. Of every candidate that met the TRAIN constraints, how many also meet the TEST pass bar
(>= 40% of test flats removed, <= 15% of test win P&L removed, net >= actual on BOTH test runs)? Versus a null: random removals of
the same number of test windows. Plus the per-day effect at the observed fill rates for the few named rules."""
import sys, json, itertools
import numpy as np
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/quiet2")
exec(open("x5_rules.py").read().split("# ---- the pick (pre-registered)")[0].replace('print(', 'pass; _p=(').replace('pass; _p=(f"', '_p=(f"'))
rng = np.random.default_rng(11)
def test_pass(m_te):
    d = evaluate(m_te, Nte, Fe_te, Lte, Rte)
    both = all(d["per_run"][rr] >= 0 for rr in ("f28", "a34"))
    return d, (d["flat_rm_pct"] >= 40 and d["win_rm_pct"] <= 15 and both)
allc = [(g, nm, [rule], d) for g, nm, rule, d in cands if ok_train(d)] + [(g, nm, rule, d) for g, nm, rule, d in pairs if ok_train(d)]
print(f"train-constrained candidates: {len(allc)} (singles {len([1 for c in cands if ok_train(c[3])])}, pairs {len([1 for c in pairs if ok_train(c[3])])}); all candidates tried: {len(cands)+len(pairs)}")
passed = []; gains = []
for g, nm, rule, d in allc:
    dte, ok = test_pass(mask_of(rule, Xte)); gains.append(dte["gain"])
    if ok: passed.append((nm, g, dte))
print(f"meet the TEST pass bar: {len(passed)} of {len(allc)}; test gain of the constrained candidates: mean {np.mean(gains):+.3f}, median {np.median(gains):+.3f}, >0: {np.mean(np.array(gains)>0):.0%}")
for nm, g, dte in passed: print(f"   {nm:60s} train {g:+.3f} test {dte['gain']:+.3f} flat {dte['flat_rm']}/{dte['flat_n']} win pnl rm {dte['win_rm_pct']:.0f}% {dte['per_run']}")
# null: random masks removing the same share of TEST windows as the candidates do (median share)
share = np.median([mask_of(rule, Xte).mean() for _, _, rule, _ in allc]); k = int(round(share * len(Xte)))
nul = []; npass = 0
for _ in range(3000):
    m = np.zeros(len(Xte), bool); m[rng.choice(len(Xte), k, replace=False)] = True
    d, ok = test_pass(m); nul.append(d["gain"]); npass += ok
print(f"null (random removal of {k} of {len(Xte)} test windows, 3000 draws): gain mean {np.mean(nul):+.3f}, p90 {np.percentile(nul,90):+.3f}, p95 {np.percentile(nul,95):+.3f}; pass the bar {npass/3000:.1%}")
# null with the attention structure: random rules = the SAME candidate family but with train/test roles shuffled? -> simpler: the candidates' test gains vs the null
print(f"candidates' test gains above the null p95: {np.mean(np.array(gains) > np.percentile(nul,95)):.0%}")
# per-day effect at observed fill rates for the named rules
hours = {"f28": (max(r["t"] for r in TEST if r["run"]=="f28") - min(r["t"] for r in TEST if r["run"]=="f28"))/3.6e12, "a34": (max(r["t"] for r in TEST if r["run"]=="a34") - min(r["t"] for r in TEST if r["run"]=="a34"))/3.6e12}
print("test hours", {k: round(v,2) for k, v in hours.items()}, "train hours", round(sum((max(r["t"] for r in TRAIN if r["run"]==rr) - min(r["t"] for r in TRAIN if r["run"]==rr))/3.6e12 for rr in set(r["run"] for r in TRAIN)),2))
for nm, rule in (("holders_gt0_5pct <= 2 (pick)", [(NAMES.index("holders_gt0_5pct"), "<=", 2.0)]), ("n_tr_60s <= 6 AND maxdd_120s >= -0.2191 (runner-up, post hoc)", [(NAMES.index("n_tr_60s"), "<=", 6.0), (NAMES.index("maxdd_120s"), ">=", -0.2191)])):
    for tag, X, N, Fe, L, R, hrs in (("train", Xtr, Ntr, Fe_tr, Ltr, Rtr, None), ("test", Xte, Nte, Fe_te, Lte, Rte, sum(hours.values()))):
        m = mask_of(rule, X); d = evaluate(m, N, Fe, L, R)
        h = hrs or sum((max(r["t"] for r in TRAIN if r["run"]==rr) - min(r["t"] for r in TRAIN if r["run"]==rr))/3.6e12 for rr in set(r["run"] for r in TRAIN))
        print(f"   {nm:58s} {tag:5s}: gain {d['gain']:+.3f} over {h:.1f} h = {24*d['gain']/h:+.2f} SOL/day (one server); fills kept {d['fills']-d['fills_rm']}/{d['fills']}")
# bootstrap CI for the runner-up on test
rule = [(NAMES.index("n_tr_60s"), "<=", 6.0), (NAMES.index("maxdd_120s"), ">=", -0.2191)]
m = mask_of(rule, Xte); g = Fe_te * m - Nte * m; bs = [g[rng.integers(0, len(g), len(g))].sum() for _ in range(3000)]
print(f"runner-up test gain {g.sum():+.3f} 90% CI [{np.percentile(bs,5):+.3f}, {np.percentile(bs,95):+.3f}]")
for r, mm in zip(TEST, m):
    if mm and r["filled"]: print(f"     {r['lab']:4s} {r['net']:+.4f} {r['name']} {r['pkt'][6:]} https://gmgn.ai/sol/token/{r['mint']}")

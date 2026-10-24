#!/usr/bin/env python3
# GDM report helpers: (1) additivity: FINAL-2-only / both / GDM-only picks (become_eval outputs, PRO costs, t8);
# (2) what the picks look like (label / feature means); (3) frozen model feature importance.
import sys, json, statistics, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/gdm")
import numpy as np, common
from common import imp
PK = f"{common.OUT}/picks"
def load_be(fns): return {r["m"]: r for fn in fns for r in json.load(open(f"{PK}/{fn}"))}
def tot(R, sub, L, var, ex="t8"):
    v = [R[m][L][var] for m in sub if m in R and R[m].get(L, {}).get(var)]
    fl = [x for x in v if x["fill"]]; nf = len(v) - len(fl)
    return sum(x["pnl"][ex] + 0.007 for x in fl) - 0.003 * nf, len(fl), len(v)
J = lambda f: set(json.load(open(f"{PK}/{f}")))
print("(1) additivity, PRO costs, t8: total SOL (fills/attempts) for proafter_slip | nosnip")
for per, be, f2, g, t0, t1 in (("R2 22:09-05:34", ("cand_R2_become_B0.5_x.json", "cand2_R2_become_B0.5_x.json"), "F2off_R2.json", "bag_fwd_yc_LM_q0.03.json", 1792688940, 1792715691),
                                ("R1 03:07-18:00", ("cand_R1_become_B0.5_x.json", "cand2_R1_become_B0.5_x.json"), "F2off_R1.json", "bag_rev_yc_LM_q0.03.json", 1792620420, 1792674000)):
    R = load_be(be); R = {m: r for m, r in R.items() if t0 <= r["bt"] <= t1}; A, B = J(f2), J(g)
    for nm, sub in (("FINAL-2 only", A - B), ("both", A & B), ("GDM only", B - A)):
        cells = []
        for L in ("75", "45", "30"):
            a = tot(R, sub, L, "proafter_slip"); b = tot(R, sub, L, "nosnip"); cells.append(f"L{L} {a[0]:+5.2f} ({a[1]}/{a[2]}) | {b[0]:+5.2f}")
        print(f"  {per} {nm:13s} n {len(sub):3d}: " + "   ".join(cells))
Z, M = common.load(); mints = M["mints"]; names = M["names"]; X = Z["X"]; ix = {m: i for i, m in enumerate(mints)}
print("\n(2) pick profiles in the test periods (mean; generic buyers = label c, a10 = market label a)")
cols = ["dev_plus_bundle", "dpb_2_20", "P0_mc_sol", "glued_n", "glued_sol", "fresh_dep", "dep_n_all", "dep_c_mean", "has_web", "has_tw", "desc_len", "name_n1h", "relaunch_lt60"]
for per, sets in (("R2", (("FINAL-2", "F2off_R2.json"), ("GDM bag", "bag_fwd_yc_LM_q0.03.json"))), ("R1", (("FINAL-2", "F2off_R1.json"), ("GDM bag", "bag_rev_yc_LM_q0.03.json")))):
    allr = [i for i, r in enumerate(Z["run"]) if r == per]
    for nm, f in sets + (("all launches", None),):
        I = [ix[m] for m in J(f) if m in ix] if f else allr
        c = Z["y_c210"][I]; a = Z["y_a10"][I]
        s = f"  {per} {nm:12s} n {len(I):5d} | generic buyers 2-10 s mean {c.mean():5.1f} median {np.median(c):4.0f} | a10>=1.05 {np.mean(a >= 1.05):.0%} median a10 {np.median(a):.3f} | "
        s += " ".join(f"{k} {np.nanmean(X[I, names.index(k)]):.3g}" for k in cols)
        print(s)
F = json.load(open("/home/moiz/sniper/ops/overnight/dryrun/frozen_gdm.json"))
for nm in ("LM",):
    Mo = F["models"][nm]; acc = np.zeros(len(Mo["features"]))
    for b in Mo["bag"]:
        for t in b["trees"]: imp(t, acc)
    print(f"\n(3) frozen {nm} feature importance (gain share, 5-seed bag): " + ", ".join(f"{Mo['features'][j]} {acc[j] / acc.sum():.1%}" for j in np.argsort(-acc)[:15]))

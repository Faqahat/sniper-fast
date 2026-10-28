#!/usr/bin/env python3
"""migrate agent, step 4: aggregate the replays (sim_*.pkl) into variants = (mode, size, V, exit, selection p>=theta, re-entry),
choose on TRAIN only, report TEST. Pass bar: >= +2 SOL/day on test, 90% CI excluding 0, positive each test day, train >= 0."""
import sys, glob, pickle, collections, numpy as np
from mlib import D, TRAIN, TEST
F = pickle.load(open(D + "/feat.pkl", "rb")); meta = F["meta"]; PP = pickle.load(open(D + "/feat_p.pkl", "rb"))
SIMS = {}
for fn in sorted(glob.glob(D + "/sim_*.pkl")):
    tag = fn.split("sim_")[1][:-4]
    if tag.endswith("ms") and "--all" not in sys.argv: continue
    SIMS[tag] = pickle.load(open(fn, "rb"))
THETAS = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9]; HORS = ["p30", "p120", "p600"]
ename = lambda e: f"mig+{e[0]}|stop {e[1] if e[1] is not None else 'none'}|to {e[2]}s"

def build(tag):
    S = SIMS[tag]; R = S["R"]; EX = S["EXITS"]
    I = np.array([r["i"] for r in R]); res = np.array([r["res"] for r in R]); fill = np.array([r["fill"] for r in R])
    V = np.array([meta[i]["V"] for i in I]); day = np.array([meta[i]["day"] for i in I]); grad = np.array([meta[i]["grad"] for i in I])
    nc = np.array([meta[i]["ncross"] for i in I]); sn = np.array([r.get("sniped", False) for r in R]); gx = np.array([r["gradexit"] for r in R])
    p = {h: PP[h][I] for h in HORS}
    return dict(I=I, res=res, fill=fill, V=V, day=day, grad=grad, nc=nc, sn=sn, gx=gx, p=p, EX=EX, tries=np.array([r["tries"] for r in R]),
                pre=np.array([r.get("pre_share", 0) for r in R]), fvs=np.array([r.get("fill_vs", np.nan) for r in R]))

def stats(B, sel, xi, days):
    s = sel & np.isin(B["day"], days); r = B["res"][s, xi]; fl = B["fill"][s]; g = B["grad"][s]; d = B["day"][s]
    n = len(days); tot = np.nansum(r) / n
    byday = {dd: np.nansum(r[d == dd]) for dd in days}
    rng = np.random.default_rng(0); bs = [np.nansum(r[rng.integers(0, len(r), len(r))]) / n for _ in range(1000)] if len(r) else [0]
    srt = np.sort(r[~np.isnan(r)])[::-1]
    return dict(sol_day=tot, entries_day=fl.sum() / n, n=len(r), grad_rate=(fl * g).sum() / max(fl.sum(), 1e-9),
                pnl_grad=np.nansum(r[g]) / n, pnl_fail=np.nansum(r[~g]) / n, per_trade=np.nansum(r) / max(fl.sum(), 1e-9),
                ci=(np.percentile(bs, 5), np.percentile(bs, 95)), wo_top5=(srt[5:].sum()) / n if len(srt) > 5 else 0.0,
                worst=min(byday.values()), byday=byday, sniped=((B["sn"][s] & g) * fl).sum() / max((g * fl).sum(), 1e-9),
                gradexit=float((B["gx"][s, xi] * 1).sum() / max(fl.sum(), 1e-9)))

variants = []; nvar = 0
for tag, S in SIMS.items():
    B = build(tag); EX = B["EX"]
    for V in sorted(set(B["V"])):
        for reent in (0, 1):
            base = (B["V"] == V) & ((B["nc"] == 0) if reent == 0 else (B["nc"] <= 2))
            for h in HORS:
                for th in THETAS:
                    if th == 0 and h != "p120": continue
                    sel = base & (B["p"][h] >= th)
                    for xi in range(len(EX)):
                        nvar += 1
                        tr = np.isin(B["day"], TRAIN) & sel; te = np.isin(B["day"], TEST) & sel
                        if tr.sum() < 30: continue
                        strain = np.nansum(B["res"][tr, xi]) / len(TRAIN)
                        variants.append((strain, tag, V, reent, h, th, xi))
print(f"variants evaluated: {nvar} (with >=30 train entries: {len(variants)})")
variants.sort(reverse=True)
def show(v, label=""):
    strain, tag, V, reent, h, th, xi = v; B = build(tag); EX = B["EX"]
    base = (B["V"] == V) & ((B["nc"] == 0) if reent == 0 else (B["nc"] <= 2)); sel = base & (B["p"][h] >= th)
    a = stats(B, sel, xi, TRAIN); b = stats(B, sel, xi, TEST)
    ok = b["sol_day"] >= 2 and b["ci"][0] > 0 and all(x > 0 for x in b["byday"].values()) and a["sol_day"] >= 0
    print(f"{label}{tag} V={V} reent={reent} {h}>={th} {ename(EX[xi])}")
    for nm, s in (("train", a), ("test", b)):
        print(f"   {nm}: {s['sol_day']:+6.2f}/day  entries/day {s['entries_day']:5.1f}  grad {s['grad_rate']:.0%}  P&L grad {s['pnl_grad']:+6.2f} fail {s['pnl_fail']:+6.2f}"
              f"  per-trade {s['per_trade']:+.4f}  CI90 [{s['ci'][0]:+.2f},{s['ci'][1]:+.2f}]  w/o top5 {s['wo_top5']:+.2f}  worst day {s['worst']:+.2f}"
              f"  sniped@open {s['sniped']:.0%}  days " + " ".join(f"{k[3:]}:{x:+.1f}" for k, x in s["byday"].items()))
    print(f"   PASS BAR: {'PASS' if ok else 'fail'}")
    return a, b, ok
print("\n== TOP 12 ON TRAIN (test shown, nothing chosen on test) ==")
npass = 0
for v in variants[:12]: a, b, ok = show(v); npass += ok
print("\n== PASS-BAR CHECK over all variants with train >= 0: how many pass on test? ==")
cnt = 0; passed = []
for v in variants:
    if v[0] < 0: break
    strain, tag, V, reent, h, th, xi = v; B = build(tag); EX = B["EX"]
    base = (B["V"] == V) & ((B["nc"] == 0) if reent == 0 else (B["nc"] <= 2)); sel = base & (B["p"][h] >= th)
    b = stats(B, sel, xi, TEST); cnt += 1
    if b["sol_day"] >= 2 and b["ci"][0] > 0 and all(x > 0 for x in b["byday"].values()): passed.append((b["sol_day"], v))
print(f"variants with train >= 0: {cnt}; of those passing the test bar: {len(passed)}")
passed.sort(reverse=True)
for sd, v in passed[:8]: show(v, label="PASSED: ")

# fixed-structure tables (not chosen): per V, mode, size, with the best train exit for that cell and theta=0 vs 0.7 on p120
print("\n== GRID: per (mode,size,V): best-train exit, theta 0 vs p120>=0.7 (first crossings): train | test SOL/day (entries/day) ==")
for tag in SIMS:
    B = build(tag); EX = B["EX"]
    for V in sorted(set(B["V"])):
        line = f"{tag:9s} V={V:3d}: "
        for th in (0.0, 0.7, 0.85):
            sel = (B["V"] == V) & (B["nc"] == 0) & (B["p"]["p120"] >= th)
            tr = np.isin(B["day"], TRAIN) & sel
            if tr.sum() < 30: line += f"p>={th}: n/a | "; continue
            sc = [np.nansum(B["res"][tr, xi]) / len(TRAIN) for xi in range(len(EX))]; xi = int(np.argmax(sc))
            b = stats(B, sel, xi, TEST)
            line += f"p>={th}: {sc[xi]:+5.1f} | {b['sol_day']:+5.1f} ({b['entries_day']:.0f}/d) [{ename(EX[xi])}]   "
        print(line)
pickle.dump(dict(variants=variants[:200], passed=passed), open(D + "/m4.pkl", "wb"))

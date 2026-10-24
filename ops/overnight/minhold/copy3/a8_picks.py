#!/usr/bin/env python3
# WHAT DO THEY PICK vs SKIP? Each first buy vs a 25% random sample of other live launches of the same run seen at the same age
# (nearest age-grid point; control = had a trade in the last 120 s, not mayhem, curve not complete). Features from the tape only, plus
# off-chain metadata (twitter / website / telegram / description) from the collector's enrich files.
# AUC = chance that a pick has a higher value than a control (0.5 = no difference). Then a look-alike box built on R2 picks is
# applied to R3 (and R1) controls: how many tokens a day match, and do they go up afterwards (no insertion, plain price path)?
import os, sys, json, gzip, collections, statistics, bisect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib3
G = [5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 300, 420, 600, 900, 1200, 1800]
P = [p for p in json.load(open(os.path.join(lib3.HERE, "out/pos3.json"))) if not p.get("nobuy") and not p["mayhem"]]
CT = collections.defaultdict(list)
for l in gzip.open(os.path.join(lib3.HERE, "out/snap_ctl.jsonl.gz"), "rt"):
    r = json.loads(l); CT[(r["run"], r["g"])].append(r)
FE = ["vsol", "ch3", "ch10", "ch60", "dd_peak", "n_tr", "n_buyers", "gap", "b10", "s10", "n10", "u10", "b60", "s60", "bigsell10", "bigbuy10", "dev_sol", "bundle_n", "cs_n", "dev_sold", "peak_vsol"]
# off-chain metadata for picks + controls
need = {p["m"] for p in P} | {r["m"] for v in CT.values() for r in v}
META = {}
for run in ("run_20261021_2207", "run_20261022_1543", "run_20261023_1426"):
    for l in open(f"/home/moiz/sniper-data/collect/{run}/enrich.jsonl"):
        i = l.find('"mint":"')
        if i < 0: continue
        m = l[i + 8:i + 52].split('"')[0]
        if m not in need or m in META: continue
        try: r = json.loads(l)
        except Exception: continue
        j = (r.get("meta") or {}).get("json")
        if not isinstance(j, dict): continue
        tw = str(j.get("twitter") or "")
        META[m] = dict(has_tw=1.0 if tw else 0.0, tw_status=1.0 if "/status/" in tw else 0.0, has_web=1.0 if j.get("website") else 0.0, has_tg=1.0 if j.get("telegram") else 0.0,
                       desc_len=float(len(str(j.get("description") or ""))))
MF = ["has_tw", "tw_status", "has_web", "has_tg", "desc_len"]
def gnear(a):
    i = bisect.bisect_left(G, a)
    if i == 0: return G[0]
    if i >= len(G): return G[-1]
    return G[i] if G[i] - a < a - G[i - 1] else G[i - 1]
def auc(xs, ys):
    if not xs or not ys: return float("nan")
    ys = sorted(ys); n = len(ys); s = 0.0
    for x in xs:
        lo = bisect.bisect_left(ys, x); hi = bisect.bisect_right(ys, x); s += (lo + 0.5 * (hi - lo)) / n
    return s / len(xs)
med = lambda v: statistics.median(v) if v else float("nan")
out = {}; L = []
pr = lambda *a: L.append(" ".join(str(x) for x in a))
for w8 in lib3.W3:
    v = [p for p in P if p["w"] == w8]
    rows = []
    for f in FE + MF:
        xs = []; ys = []
        for p in v:
            g = gnear(p["e_age"]); ctl = CT.get((p["run"], g), [])
            if f in MF:
                if p["m"] in META: xs.append(META[p["m"]][f])
                ys += [META[r["m"]][f] for r in ctl[:400] if r["m"] in META]
            else:
                xs.append(p["e_" + f]); ys += [r[f] for r in ctl[:400]]
        a = auc(xs, ys); rows.append((f, a, med(xs), med(ys), len(xs), len(ys)))
    rows.sort(key=lambda r: -abs(r[1] - 0.5))
    out[w8] = dict(features=[dict(f=f, auc=a, pick_med=x, ctl_med=y, n_pick=nx, n_ctl=ny) for f, a, x, y, nx, ny in rows])
    pr(f"\n## {w8}: {len(v)} first buys vs same-age live launches (feature: AUC | pick median vs control median)")
    for f, a, x, y, nx, ny in rows[:14]:
        pr(f"  {f:10s} AUC {a:.2f} | picks {x:8.2f} vs others {y:8.2f}   (n {nx} / {ny})")
    # look-alike box from R2 picks on the 4 most separating tape features (R2 AUCs only)
    tr2 = [p for p in v if p["run"] == "R2"]
    if len(tr2) < 15: continue
    a2 = []
    for f in FE:
        ys = [r[f] for p in tr2 for r in CT.get(("R2", gnear(p["e_age"])), [])[:200]]
        a2.append((abs(auc([p["e_" + f] for p in tr2], ys) - 0.5), f))
    top = [f for _, f in sorted(a2, reverse=True)[:4]]
    box = {f: (statistics.quantiles([p["e_" + f] for p in tr2], n=10)[0], statistics.quantiles([p["e_" + f] for p in tr2], n=10)[-1]) for f in top}
    ages = (statistics.quantiles([p["e_age"] for p in tr2], n=10)[0], statistics.quantiles([p["e_age"] for p in tr2], n=10)[-1])
    def inbox(r, age): return ages[0] <= age <= ages[1] and all(lo <= r[f] <= hi for f, (lo, hi) in box.items())
    pr(f"  look-alike box from R2 picks (10-90% ranges): age {ages[0]:.0f}-{ages[1]:.0f} s, " + ", ".join(f"{f} {lo:.2f}..{hi:.2f}" for f, (lo, hi) in box.items()))
    res = {}
    for run in ("R2", "R3", "R1"):
        picks = [p for p in v if p["run"] == run]
        pin = sum(1 for p in picks if inbox({f: p["e_" + f] for f in top}, p["e_age"]))
        allc = [r for (rr, g), lst in CT.items() if rr == run for r in lst]
        inb = [r for r in allc if inbox(r, r["age"])]
        # one snapshot per token (first time it is in the box) so a token is not counted at every age
        first = {}
        for r in sorted(inb, key=lambda r: r["age"]): first.setdefault(r["m"], r)
        fb = list(first.values())
        hrs = {"R1": 14.9, "R2": 21.8, "R3": 24.0}[run]
        res[run] = dict(picks=len(picks), picks_in_box=pin, ctl_tokens_in_box=len(fb), per_day=len(fb) / 0.25 / hrs * 24,
                        f30=med([r["f30"] for r in fb]), f60=med([r["f60"] for r in fb]), mx60=med([r["mx60"] for r in fb]), up10_60=sum(1 for r in fb if r["mx60"] >= 1.10) / len(fb) if fb else None,
                        all_f60=med([r["f60"] for r in allc]), all_mx60=med([r["mx60"] for r in allc]))
        x = res[run]
        pr(f"   {run}: their picks inside the box {pin}/{len(picks)} | other tokens inside the box ~{x['per_day']:.0f}/day (sample x4) | after: price at +30 s {x['f30'] or float('nan'):.2f}x, +60 s {x['f60'] or float('nan'):.2f}x, max within 60 s {x['mx60'] or float('nan'):.2f}x, "
           f">=+10% within 60 s {x['up10_60'] or 0:.0%} | all live tokens: +60 s {x['all_f60']:.2f}x, max 60 s {x['all_mx60']:.2f}x")
    out[w8]["box"] = dict(features=top, ranges=box, ages=ages, results=res)
json.dump(out, open(os.path.join(lib3.HERE, "out/picks.json"), "w"), indent=1, default=str)
open(os.path.join(lib3.HERE, "out/picks.txt"), "w").write("\n".join(L) + "\n")
print("\n".join(L))

#!/usr/bin/env python3
"""FLAT study, IDEA B (read-only, offline): the try-time stop grid (B1) and the arm-time single-feature / pair skip grid (B2) of
prereg.py on the DEV runs, against the primary baseline (dev with QUIET replayed). Selection exactly as pre-registered.
Writes /home/moiz/sniper-data/presend_flat/b_dev.json (every config) and prints the table + the selected config.
usage: b_eval.py"""
import sys, json, collections
import numpy as np
import flatlib as FL, evalcore as EC, prereg as PR

RUNS = PR.DEV


def summ(per):
    tot = collections.Counter()
    for run, S in per.items():
        for k, v in S.items():
            if isinstance(v, (int, float)): tot[k] += v
    return dict(tot)


def ok_sel(per, tot):
    no_worse = all(S["gain"] >= -1e-12 for S in per.values())
    savings = -tot.get("lose_rm_sol", 0) + tot.get("fees_saved", 0)
    winners_ok = tot.get("win_rm_sol", 0) <= 0.5 * savings + 1e-12
    return no_worse, winners_ok


def main():
    C = FL.Chain((1,)); O = EC.Others(C)
    B = {r: FL.load_base(r) for r in RUNS}
    configs = []
    # ---- B1: try-time stops
    for (N, M) in PR.GRID_B1:
        configs.append(dict(kind="B1", name=f"B1 stop at +{N} if < {M} others", stops=[(N, M)], skip=None))
    # ---- B2: singles at the dev deciles of the baseline-kept windows
    kept = [w for r in RUNS for w in B[r]["W"] if not w.get("quiet_skip_replay")]
    singles = []
    for f in PR.FEATURES_B2:
        vals = np.array([w["f"][f] for w in kept if w["f"] is not None], float)
        thr = sorted(set(float(x) for x in np.percentile(vals, [10, 20, 30, 40, 50, 60, 70, 80, 90])))
        for d in ("le", "ge"):
            for t in thr:
                singles.append((f, d, t))
    for (f, d, t) in singles:
        fn = (lambda w, f=f, d=d, t=t: w["f"] is not None and (w["f"][f] <= t if d == "le" else w["f"][f] >= t))
        configs.append(dict(kind="B2", name=f"B2 skip if {f} {'<=' if d == 'le' else '>='} {t:g}", stops=[], skip=fn, spec=[(f, d, t)]))
    res = []
    for cf in configs:
        per = {}
        for r in RUNS:
            _, S = EC.evaluate(B[r]["W"], O, r, mode="primary", extra_skip=cf["skip"], extra_stops=cf["stops"])
            per[r] = S
        tot = summ(per)
        nw, wo = ok_sel(per, tot)
        res.append(dict(kind=cf["kind"], name=cf["name"], spec=cf.get("spec"), stops=cf["stops"], per={r: {k: v for k, v in S.items()} for r, S in per.items()},
                        tot=tot, no_worse=nw, winners_ok=wo))
    # ---- pairs: AND of the best single rule of each of the 5 best features (dev gain > 0)
    best_by_f = {}
    for x in res:
        if x["kind"] != "B2" or x["tot"]["gain"] <= 0: continue
        f = x["spec"][0][0]
        if f not in best_by_f or x["tot"]["gain"] > best_by_f[f]["tot"]["gain"]: best_by_f[f] = x
    top5 = sorted(best_by_f.values(), key=lambda x: -x["tot"]["gain"])[:5]
    for a in range(len(top5)):
        for b in range(a + 1, len(top5)):
            sa, sb = top5[a]["spec"][0], top5[b]["spec"][0]
            def fn(w, sa=sa, sb=sb):
                if w["f"] is None: return False
                c1 = w["f"][sa[0]] <= sa[2] if sa[1] == "le" else w["f"][sa[0]] >= sa[2]
                c2 = w["f"][sb[0]] <= sb[2] if sb[1] == "le" else w["f"][sb[0]] >= sb[2]
                return c1 and c2
            per = {}
            for r in RUNS:
                _, S = EC.evaluate(B[r]["W"], O, r, mode="primary", extra_skip=fn)
                per[r] = S
            tot = summ(per); nw, wo = ok_sel(per, tot)
            res.append(dict(kind="B2pair", name=f"B2 skip if {top5[a]['name'][10:]} AND {top5[b]['name'][10:]}", spec=[sa, sb], stops=[], per=per, tot=tot,
                            no_worse=nw, winners_ok=wo))
    json.dump(res, open(f"{FL.D}/b_dev.json", "w"))
    n_cfg = len(res)
    qual = [x for x in res if x["no_worse"] and x["winners_ok"] and x["tot"]["gain"] > 0]
    def line(x):
        t = x["tot"]
        return (f"{x['name'][:64]:64s} " + " ".join(f"{x['per'][r]['gain']:+.4f}" for r in RUNS) + f" | {t['gain']:+.4f} | fills rm win {int(t['win_rm'])} "
                f"({t['win_rm_sol']:+.3f}) lose {int(t['lose_rm'])} ({t['lose_rm_sol']:+.3f}) flat {int(t['flat_rm'])} | fees saved {t['fees_saved']:.4f} | "
                f"skipped {int(t['skipped'])} | {'Q' if (x['no_worse'] and x['winners_ok']) else ('w' if x['no_worse'] else '-')}")
    print(f"configs evaluated: {n_cfg} (B1 {sum(1 for x in res if x['kind']=='B1')}, singles {sum(1 for x in res if x['kind']=='B2')}, pairs {sum(1 for x in res if x['kind']=='B2pair')})")
    print(f"\n{'config':64s} " + " ".join(f"{r:>7s}" for r in RUNS) + " |  total")
    print("-- B1 (all):")
    for x in res:
        if x["kind"] == "B1": print(line(x))
    print("-- B2 singles, top 25 by dev gain:")
    for x in sorted([x for x in res if x["kind"] == "B2"], key=lambda x: -x["tot"]["gain"])[:25]: print(line(x))
    print("-- B2 pairs:")
    for x in res:
        if x["kind"] == "B2pair": print(line(x))
    print(f"\nqualifying (gain > 0, no dev run worse, winners removed <= 0.5 x savings): {len(qual)}")
    for x in sorted(qual, key=lambda x: -x["tot"]["gain"])[:10]: print(line(x))
    if qual:
        best = max(qual, key=lambda x: x["tot"]["gain"])
        print("\nSELECTED:", best["name"])


if __name__ == "__main__":
    main()

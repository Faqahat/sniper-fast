#!/usr/bin/env python3
"""T2-WINDOWS step 9: per-run view of the main variants (same scorers; each run scored alone as one 'period'; gap = its period's)."""
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/t2windows")
import t2lib as L, t2score as S, e6_rearm as A, e7_wide as B

if __name__ == "__main__":
    X, P = S.load()
    merged = S.coverage(P); sh = S.seg_hours(P, merged)
    ga = A.gaps_of(X, P); gb = B.t2_gaps(X, P); cr_of, led = B.creator_ledger(X, P)
    segs = [(39, "fit"), (40, "fit"), (41, "fit"), (42, "fit"), (42, "choose"), (44, "choose"), (45, "choose"), (46, "choose"), (47, "final"), (48, "final"), (49, "final")]
    VA = {"H0 no holder": {"h": 0}, "H3 holder>=3%": {"h": 3}, "age<=600": {"amax": 600}, "R5 on": {"r5": True}, "size 0.65": {"size": 0.65}}
    VB = {"W5 5-6%": {"band": (5, 6)}, "W4 4-5%": {"band": (4, 5)}}
    out = {}
    for r, per in segs:
        Xs = [dict(x, per="fit") for x in X if x["run"] == r and x["per"] == per]
        hrs = {"fit": sh.get((r, per), 0.0), "choose": 1e-9, "final": 1e-9}
        g1 = {"fit": ga[per], "choose": 0, "final": 0}; g2 = {"fit": gb[per], "choose": 0, "final": 0}
        row = {}
        for k, v in VA.items(): row[k] = A.score(Xs, P, v, g1, hrs)["fit"]
        for k, v in VB.items(): row[k] = B.score(Xs, P, v, g2, hrs, cr_of, led)["fit"]
        out[f"r{r}{'b' if (r == 42 and per == 'choose') else ''}"] = row
        print(f"r{r}{'b' if r == 42 and per == 'choose' else ' '} {per:6s} {hrs['fit']:5.1f}h " + " | ".join(f"{k} {o.get('net_cal', o.get('cal')):+6.3f} ({o['day_cal']:+6.2f}/d)" for k, o in row.items()))
    json.dump(out, open(f"{L.D}/perrun.json", "w"), indent=1)

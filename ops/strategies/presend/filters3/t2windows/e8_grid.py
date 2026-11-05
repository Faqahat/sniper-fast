#!/usr/bin/env python3
"""T2-WINDOWS step 8: the proof protocol over a grid of ADD-ONLY variants (live windows kept as they were; only new windows added).
  A grid: holder needed (6 / 3 / none) x age max (141 / 300 / 1200 slots) x dump band (6-10 / 10-15 / >=15 / all) x dip bots (any / on token / not)
  B grid: whale band (4-5 / 5-6 / 5.5-6 / 4-6 %) x min age (2 / 10 / 30) x QUIET3-A (on / off), every other live filter on
FIT (r39-r41 + r42 < 11-01 12:00 PKT) passes when calibrated net > 0, w/o top 5 > 0 and the -20 % followers row > 0;
CHOOSE (rest of r42 + r44-r46) ranks the fit passers by the same three; FINAL (r47-r49) is read once for the chosen ones.
Out: /home/moiz/sniper-data/filters3/t2windows/grid.json"""
import sys, json, itertools, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/t2windows")
import t2lib as L, t2score as S, e6_rearm as A, e7_wide as B


def ok(o): return o["net_cal" if "net_cal" in o else "cal"] > 0 and o["wo5_cal" if "wo5_cal" in o else "wo5"] > 0 and o["stress20_cal" if "stress20_cal" in o else "stress20"] > 0


if __name__ == "__main__":
    X, P = S.load()
    merged = S.coverage(P); sh = S.seg_hours(P, merged)
    hours = collections.defaultdict(float)
    for (r, per), h in sh.items():
        if per in ("fit", "choose", "final"): hours[per] += h
    hoursB = collections.defaultdict(float)
    for (r, per), h in sh.items():
        if per in ("fit", "choose", "final") and r >= 41: hoursB[per] += h     # the wide shadow exists from r41
    ga = A.gaps_of(X, P); gb = B.t2_gaps(X, P); cr_of, led = B.creator_ledger(X, P)
    res = {}
    for h, amax, band, bots in itertools.product((6, 3, 0), (141, 300, 1200), ((6, 10), (10, 15), (15, 999), (0, 999)), (None, "tok", "notok")):
        if h == 6 and amax == 141: continue
        v = {"h": h, "amax": amax, "band": band, "keep_live": True}
        if bots: v["bots"] = bots
        name = f"A h{h} age<={amax} dump{band[0]}-{band[1]} bots:{bots or 'any'}"
        res[name] = A.score(X, P, v, ga, hours)
    for band, amin, q3a in itertools.product(((4, 5), (5, 6), (5.5, 6), (4, 6)), (2, 10, 30), (True, False)):
        v = {"band": band, "amin": amin, "q3a": q3a}
        name = f"B whale{band[0]}-{band[1]} age>={amin} q3a:{'on' if q3a else 'off'}"
        res[name] = B.score(X, P, v, gb, hoursB, cr_of, led)
    fitpass = [k for k, o in res.items() if ok(o["fit"])]
    both = [k for k in fitpass if ok(res[k]["choose"])]
    def day(o): return o.get("day_cal")
    print(f"variants {len(res)} | fit pass {len(fitpass)} | fit+choose pass {len(both)}")
    for k in sorted(fitpass, key=lambda k: -day(res[k]["choose"])):
        o = res[k]
        print(f"{'*' if k in both else ' '} {k:48s} " + " | ".join(f"{p}: {day(o[p]):+6.2f}/d w/o5 {o[p].get('wo5_cal', o[p].get('wo5')):+6.3f} -20% {o[p]['day_stress']:+6.2f}/d"
                                                            for p in (("fit", "choose", "final") if k in both else ("fit", "choose"))))
    json.dump({"res": res, "fit_pass": fitpass, "fit_choose_pass": both}, open(f"{L.D}/grid.json", "w"), indent=1)

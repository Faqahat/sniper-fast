#!/usr/bin/env python3
"""FLAT study (descriptive, after the freeze): can a flat fill be told apart at arm time or at the fill try? For every fill of the
runs: the arm-time features (f4_features.py) and the other trades the engine had seen when it signed the filling try; AUC of
each for 'flat' vs 'not flat', and for 'flat' vs 'winner' (realized + rent back > 0). MEASURED inputs.
usage: m3_separability.py r24 r25 r26 r27 r28"""
import sys
import numpy as np
import flatlib as FL, evalcore as EC, prereg as PR

def auc(pos, neg):
    pos = np.asarray(pos, float); neg = np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0: return float("nan")
    allv = np.concatenate([pos, neg]); r = allv.argsort().argsort().astype(float) + 1
    # average ranks for ties
    import collections
    d = collections.defaultdict(list)
    for k, v in enumerate(allv): d[v].append(k)
    for v, ks in d.items():
        if len(ks) > 1: r[ks] = r[ks].mean()
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))

def main():
    runs = sys.argv[1:]
    phases = sorted(set(p for r in runs for p in FL.RUN_PHASES[r]))
    C = FL.Chain(phases); O = EC.Others(C)
    rows = []
    for run in runs:
        for w in FL.load_base(run)["W"]:
            if not w["filled"] or w.get("flat") is None or w["f"] is None: continue
            ft = next((t for t in w["tries"] if t["fill"]), None)
            oth = O.upto(w, ft["pos"]) if ft else 0
            rows.append(dict(run=run, flat=w["flat"], win=w["net"] > 0, f=dict(w["f"], oth_at_fill_try=oth, fill_slot_after_trig=(w["fill"]["slot"] - w["trig"]["slot"]))))
    fl = [x for x in rows if x["flat"]]; nf = [x for x in rows if not x["flat"]]; wn = [x for x in rows if x["win"]]
    print(f"fills {len(rows)}: flat {len(fl)}, not flat {len(nf)}, winners {len(wn)}")
    print(f"{'feature':22s} {'AUC flat vs other':>18s} {'AUC flat vs winner':>19s}   flat median / other median")
    for f in PR.FEATURES_B2 + ["oth_at_fill_try", "fill_slot_after_trig"]:
        a = auc([x["f"][f] for x in fl], [x["f"][f] for x in nf]); b = auc([x["f"][f] for x in fl], [x["f"][f] for x in wn])
        print(f"{f:22s} {a:18.3f} {b:19.3f}   {np.median([x['f'][f] for x in fl]):g} / {np.median([x['f'][f] for x in nf]):g}")
    # fill timing (slots after the trigger) of flats vs others
    import collections
    print("fill slot after trigger, flats :", sorted(collections.Counter(x["f"]["fill_slot_after_trig"] for x in fl).items()))
    print("fill slot after trigger, others:", sorted(collections.Counter(x["f"]["fill_slot_after_trig"] for x in nf).items()))
    print("other trades seen at the filling try, flats :", sorted(collections.Counter(min(x["f"]["oth_at_fill_try"], 5) for x in fl).items()))
    print("other trades seen at the filling try, others:", sorted(collections.Counter(min(x["f"]["oth_at_fill_try"], 5) for x in nf).items()))
main()

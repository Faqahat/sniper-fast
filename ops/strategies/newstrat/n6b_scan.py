#!/usr/bin/env python3
"""scan LAUNCH-AGE rows: per A x exit x simple filter cells; fit-positive on all 3 fit days -> show 10-31"""
import numpy as np, itertools, json
import nlib as L
FIT = L.RUNS[:3]; CH = L.RUNS[3]
Z = {r: np.load(f"{L.OUT}/la_{r}.npz") for r in FIT + [CH]}
EXN = ["fix5", "fix25", "fix150", "trail15", "drought10"]
def col(D, j): return {0: 9, 50: 14, 70: 19, 90: 29}[D] + j
filters = {"all": lambda a: np.ones(len(a), bool)}
for v0, v1 in ((30, 35), (35, 45), (45, 60), (60, 200)): filters[f"vs{v0}-{v1}"] = (lambda v0, v1: lambda a: (a[:, 2] >= v0) & (a[:, 2] < v1))(v0, v1)
for nb in (5, 15, 30): filters[f"nb>={nb}"] = (lambda nb: lambda a: a[:, 3] >= nb)(nb)
for cs in (1, 3): filters[f"cs>={cs}"] = (lambda cs: lambda a: a[:, 4] >= cs)(cs)
filters["cs<0.5"] = lambda a: a[:, 4] < 0.5
for dv in (1, 3): filters[f"dev>={dv}"] = (lambda dv: lambda a: a[:, 5] >= dv)(dv)
filters["nf>=3"] = lambda a: a[:, 6] >= 3
filters["sold>=2"] = lambda a: a[:, 7] >= 2
filters["top<1"] = lambda a: a[:, 8] < 1
cells = []
for A in (8, 10, 20, 50):
    for fn, (f1, f2) in itertools.product(filters, [(None, None)]):
        for j, ex in enumerate(EXN):
            row = {"A": A, "filt": fn, "exit": ex}
            ok = True
            for r in FIT + [CH]:
                a = Z[r]["a"]; hrs = float(Z[r]["hours"][0])
                m = (a[:, 1] == A) & filters[fn](a)
                v = a[m, col(70, j)]
                s = L.stats(v); s["per_day"] = round(s["net"] / hrs * 24, 2)
                s["D0_day"] = round(a[m, col(0, j)].sum() / 1e9 / hrs * 24, 2)
                s["f20_day"] = round(a[m, 24 + j].sum() / 1e9 / hrs * 24, 2)
                row[L.DAY[r]] = s
                if r in FIT and s["net"] <= 0: ok = False
            row["fit_ok"] = ok; cells.append(row)
print("cells", len(cells), "fit-positive", sum(c["fit_ok"] for c in cells))
best = sorted(cells, key=lambda c: sum(c[L.DAY[r]]["per_day"] for r in FIT), reverse=True)
for c in best[:15]:
    print(c["A"], c["filt"], c["exit"], c["fit_ok"], " | ".join(f"{L.DAY[r]} {c[L.DAY[r]]['per_day']:+.1f}/d n{c[L.DAY[r]]['n']} {c[L.DAY[r]]['per']:+.1f} wo5 {c[L.DAY[r]]['wo5']:+.2f} D0 {c[L.DAY[r]]['D0_day']:+.1f}" for r in FIT + [CH]))
print("--- 'all' filter per A/exit (10-31 /day, mSOL/trip)")
for c in cells:
    if c["filt"] == "all": print(c["A"], c["exit"], [(L.DAY[r], c[L.DAY[r]]['per_day'], c[L.DAY[r]]['per']) for r in FIT + [CH]])
json.dump(cells, open(f"{L.OUT}/n6b.json", "w"))

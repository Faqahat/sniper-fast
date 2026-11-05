import pickle, numpy as np, collections
D = "/home/moiz/sniper-data/rivals/9pQQ/lanes"
RUNS = ["run_20261028_1405", "run_20261029_1400", "run_20261030_1355", "run_20261031_1350", "run_20261102_1250"]
DAY = dict(zip(RUNS, ["10-28", "10-29", "10-30", "10-31", "11-02"]))
_c = {}
def trips(run):
    if run not in _c: _c[run] = pickle.load(open(f"{D}/trips_{run}.pkl", "rb"))
    return _c[run]["rows"]
def hours(run): trips(run); return _c[run]["hours"]
def cap(r): return r["hold_s"] >= (295 if r["bs"] < 0 else 0) and (r["hold_s"] >= 297 and r["hold_s"] <= 303 or r["hold_s"] >= 597)
def table(groups, fmt="%-28s"):
    """groups: dict name -> predicate(r). Prints n / net / mSOL per trip / win per day."""
    print(fmt % "group", " | ".join("%-24s" % DAY[r] for r in RUNS), "| total")
    for name, f in groups.items():
        cells = []; N = 0; S = 0
        for run in RUNS:
            R = [r for r in trips(run) if f(r)]; n = len(R); s = sum(r["net"] for r in R)
            N += n; S += s
            cells.append("%5d %+7.2f %+6.1f %2.0f%%" % (n, s, 1e3 * s / max(n, 1), 100 * np.mean([r["net"] > 0 for r in R]) if R else 0))
        print(fmt % name, " | ".join(cells), "| %d %+.2f" % (N, S))

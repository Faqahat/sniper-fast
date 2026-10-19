import sys, pickle, statistics
sys.path.insert(0, "/root/strat")
from sim import EXITS
rows, meta = pickle.load(open("/root/strat/table.pkl", "rb"))
def s(v):
    v = [a for a in v if a is not None]
    if len(v) < 5: return "n=%d" % len(v)
    sv = sorted(v)
    return "n=%d %+.1f/%+.1f/ex3 %+.1f" % (len(v), 100 * sum(v) / len(v), 100 * statistics.median(v), 100 * sum(sv[:-3]) / (len(sv) - 3))
for mh in (0, 1):
    R = [r for r in rows if r["f"]["mh"] == mh]
    first = {}
    for r in sorted(R, key=lambda r: r["dk"]): first.setdefault(r["mint"], r)
    F = list(first.values())
    print("== mayhem", mh, "tokens", len(F), "rows", len(R))
    for e in [("time", 10), ("time", 30), ("time", 120), ("time", 300), ("trail", 0.25, 300), ("tpsl", 1.5, 0.7, 300)]:
        print("  ", e, "first:", s([r["pn"][(1.0, e)] for r in F]), "| all-ck:", s([r["pn"][(1.0, e)] for r in R]), "| shift first:", s([r["pn2"][(1.0, e)] for r in F]))
    for T in (15, 30, 60, 90, 120, 180, 240):
        print("    T", T, s([r["pn"][(1.0, ("time", 120))] for r in R if r["f"]["T"] == T]), " v>=60:", s([r["pn"][(1.0, ("time", 120))] for r in R if r["f"]["T"] == T and r["f"]["v"] >= 60]))

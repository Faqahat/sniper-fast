import sys, pickle, statistics
sys.path.insert(0, "/root/strat")
from sim import EXITS
rows, meta = pickle.load(open("/root/strat/table.pkl", "rb"))
first = {}
for r in sorted(rows, key=lambda r: r["dk"]):
    first.setdefault(r["mint"], r)
F = list(first.values())
def s(v):
    v = [a for a in v if a is not None]
    if len(v) < 5: return "n=%d" % len(v)
    sv = sorted(v)
    return "n=%d mean %+.1f med %+.1f ex3 %+.1f" % (len(v), 100 * sum(v) / len(v), 100 * statistics.median(v), 100 * sum(sv[:-3]) / (len(sv) - 3))
for name, sel in [("first entries", F), ("dd<0.7 all-ck", [r for r in rows if r["f"]["dd"] < 0.7]), ("v>=85 all-ck", [r for r in rows if r["f"]["v"] >= 85]),
                  ("T>=120 v>=50 dd>=.9 all", [r for r in rows if r["f"]["T"] >= 120 and r["f"]["v"] >= 50 and r["f"]["dd"] >= 0.9])]:
    print("==", name)
    for X in (1.0,):
        for e in EXITS:
            print("  ", e, "double:", s([r["pn"][(X, e)] for r in sel]), "| shift:", s([r["pn2"][(X, e)] for r in sel]))

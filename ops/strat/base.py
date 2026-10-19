import sys, pickle, statistics as stt, collections
sys.path.insert(0, "/root/strat")
from sim import EXITS
rows, meta = pickle.load(open("/root/strat/table.pkl", "rb"))
def summ(v):
    v = [a for a in v if a is not None]
    if not v: return "n=0"
    s = sorted(v); ex3 = s[:-3] if len(s) > 3 else []
    return "n=%d mean=%+.1f%% med=%+.1f%% ex3=%+.1f%% win=%.0f%%" % (len(v), 100 * sum(v) / len(v), 100 * stt.median(v), 100 * sum(ex3) / max(1, len(ex3)), 100 * sum(1 for a in v if a > 0) / len(v))
first = {}
for r in rows:
    if r["mint"] not in first or r["dk"] < first[r["mint"]]["dk"]: first[r["mint"]] = r
F = list(first.values())
print("tokens with entry", len(F), "launches", len(meta), collections.Counter((m[1], m[3], m[4]) for m in meta))
for X in (1.0, 2.0):
    for e in EXITS:
        print(X, e, summ([r["pn"][(X, e)] for r in F]))
print("by T (first entry), X=1, time60")
for T in sorted({r["f"]["T"] for r in F}):
    print(T, summ([r["pn"][(1.0, ("time", 60))] for r in F if r["f"]["T"] == T]))
print("all checkpoints, by v bucket X=1 time60/trail.25/300")
for lo, hi in [(36, 40), (40, 45), (45, 55), (55, 70), (70, 90), (90, 200)]:
    s = [r for r in rows if lo <= r["f"]["v"] < hi]
    print(lo, hi, summ([r["pn"][(1.0, ("time", 60))] for r in s]), "|", summ([r["pn"][(1.0, ("trail", 0.25, 300))] for r in s]))

# Baseline by fold: every first screened entry (no selection), non-mayhem / mayhem, a few exits, both models.
import sys, pickle, statistics, collections
sys.path.insert(0, "/root/strat")
from sim import DS_W
rows, meta = pickle.load(open(sys.argv[1], "rb"))
ds_bt = sorted(m[2] for m in meta if m[1] == "ds" and not m[4]); cut = ds_bt[int(0.6 * len(ds_bt))]
fold = lambda src, bt: (0 if bt < cut else 1) if src == "ds" else 2
first = {}
for r in sorted(rows, key=lambda r: r["dk"]): first.setdefault(r["mint"], r)
F = list(first.values())
EXS = []
for k in rows[0]["pn"]:
    if k[1] not in EXS: EXS.append(k[1])
def st(v):
    v = [a for a in v if a is not None]
    if len(v) < 4: return "n<4"
    s = sorted(v); return "n=%4d mean %+6.1f%% med %+6.1f%% ex3 %+6.1f%%" % (len(v), 100 * sum(v) / len(v), 100 * statistics.median(v), 100 * sum(s[:-3]) / (len(s) - 3))
for mh in (0, 1):
    print("== mayhem=%d, first screened entry per token, 1 SOL" % mh)
    for e in EXS:
        line = []
        for f in (0, 1, 2):
            G = [r for r in F if r["f"]["mh"] == mh and fold(r["src"], r["bt"]) == f]
            line.append("F%d %s" % (f, st([r["pn"][(1.0, e)] for r in G])))
        G = [r for r in F if r["f"]["mh"] == mh]
        print("  %-28s %s | all shift: %s" % (str(e), " | ".join(line), st([r["pn2"][(1.0, e)] for r in G])))

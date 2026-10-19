# Rolling time folds for a rule given as python lambda over f; usage: folds.py table.pkl "<lambda f: ...>" model
import sys, pickle, statistics, json
sys.path.insert(0, "/root/strat")
from sim import EXITS, DS_W
rows, meta = pickle.load(open(sys.argv[1], "rb"))
rule = eval(sys.argv[2]); MODEL = sys.argv[3] if len(sys.argv) > 3 else "pn"
EXL = sorted({k for r in rows for k in r[MODEL]}, key=str)
ds_bt = sorted(m[2] for m in meta if m[1] == "ds" and not m[4]); tr_bt = sorted(m[2] for m in meta if m[1] == "truth" and not m[4])
q = [ds_bt[0], ds_bt[len(ds_bt) // 3], ds_bt[2 * len(ds_bt) // 3], ds_bt[-1] + 1]
tq = [tr_bt[0], tr_bt[len(tr_bt) // 2], tr_bt[-1] + 1]
def fold(src, bt):
    if src == "ds":
        for i in range(3):
            if q[i] <= bt < q[i + 1]: return "ds%d" % i
    else:
        for i in range(2):
            if tq[i] <= bt < tq[i + 1]: return "tr%d" % i
    return None
names = ["ds0", "ds1", "ds2", "tr0", "tr1"]
hours = {}; launches = {}
for nm in names:
    b = [m[2] for m in meta if not m[4] and fold(m[1], m[2]) == nm]
    hours[nm] = (max(b) - min(b)) / 3600; launches[nm] = len(b)
W = {"ds0": DS_W, "ds1": DS_W, "ds2": DS_W, "tr0": 1, "tr1": 1}
rows.sort(key=lambda r: (r["mint"], r["dk"]))
sel = []; last = None
for r in rows:
    if r["mint"] == last: continue
    if rule(r["f"]): sel.append(r); last = r["mint"]
def st(v):
    v = [a for a in v if a is not None]
    if len(v) < 2: return "n=%d" % len(v)
    s = sorted(v)
    return "n=%3d mean %+6.1f%% med %+6.1f%% ex3 %+6.1f%% win %3.0f%%" % (len(v), 100 * sum(v) / len(v), 100 * statistics.median(v), 100 * sum(s[:-3]) / max(1, len(s) - 3), 100 * sum(1 for a in v if a > 0) / len(v))
print("hours", {k: round(v, 1) for k, v in hours.items()}, "launches", launches)
for ex in EXL:
    X = ex[0]
    line = []
    for nm in names:
        v = [r[MODEL][ex] for r in sel if fold(r["src"], r["bt"]) == nm]
        v2 = [a for a in v if a is not None]
        tpd = len(v2) * W[nm] / hours[nm] * 24 if hours[nm] else 0
        line.append("%s %s [%.0f/d %+.1f SOL/d]" % (nm, st(v), tpd, tpd * X * (sum(v2) / len(v2) if v2 else 0)))
    print(ex, "\n   " + "\n   ".join(line))

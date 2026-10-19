# Rule search (pure python): fit on train fold, judge on test folds. Paper/offline.
import sys, os, pickle, itertools, collections, json, statistics, heapq
sys.path.insert(0, "/root/strat")
from sim import EXITS, DS_W
rows, meta = pickle.load(open(sys.argv[1] if len(sys.argv) > 1 else "/root/strat/table.pkl", "rb"))
MODEL = sys.argv[2] if len(sys.argv) > 2 else "pn"
SPLIT = sys.argv[3] if len(sys.argv) > 3 else "A"
rows.sort(key=lambda r: (r["mint"], r["dk"]))
ds_bt = sorted(m[2] for m in meta if m[1] == "ds" and not m[4])
cut_ds = ds_bt[int(0.6 * len(ds_bt))]
tr_bt = sorted(m[2] for m in meta if m[1] == "truth" and not m[4])
cut_tr = tr_bt[int(0.5 * len(tr_bt))]
def fold(src, bt):
    if SPLIT == "A":   # ds first 60% = train(0); ds last 40% = test_ds(1); truth census = test_tr(2)
        if src == "ds": return 0 if bt < cut_ds else 1
        return 2
    else:              # B: ds early 60% = test(1), ds late 40% = train(0) (reverse), truth = (2)
        if src == "ds": return 1 if bt < cut_ds else 0
        return 2
for r in rows: r["fold"] = fold(r["src"], r["bt"])
L = collections.Counter(); fb = collections.defaultdict(list)
for m in meta:
    if m[4]: continue
    f = fold(m[1], m[2]); L[f] += 1; fb[f].append(m[2])
H = {f: (max(v) - min(v)) / 3600 for f, v in fb.items()}
W = {0: DS_W, 1: DS_W, 2: 1.0}
print("SPLIT", SPLIT, "MODEL", MODEL, "launches/fold", dict(L), "hours", {k: round(v, 1) for k, v in H.items()})
EXS = []
for k in rows[0][MODEL]:
    if k[1] not in EXS: EXS.append(k[1])
EX = [(X, e) for X in (1.0, 2.0) for e in EXS]
import os
LATE = os.environ.get("LATE") == "1"
for r in rows: r["pv"] = [r[MODEL].get(k) for k in EX]
def stats(v):
    v = [a for a in v if a is not None]
    if not v: return dict(n=0)
    s = sorted(v)
    return dict(n=len(v), mean=sum(v) / len(v), med=statistics.median(v), ex3=(sum(s[:-3]) / (len(s) - 3)) if len(s) > 3 else float("nan"), win=sum(1 for a in v if a > 0) / len(v))
def fmt(d, f=None, X=None):
    if not d.get("n"): return "n=0"
    s = "n=%d mean=%+.1f%% med=%+.1f%% ex3=%+.1f%% win=%.0f%%" % (d["n"], 100 * d["mean"], 100 * d["med"], 100 * d["ex3"], 100 * d["win"])
    if f is not None and H.get(f):
        tpd = d["n"] * W[f] / H[f] * 24
        s += " [%.0f/day %+.1f SOL/day@%g]" % (tpd, tpd * d["mean"] * X, X)
    return s
grid = dict(
    T=([("any", lambda a: True), ("<=420", lambda a: a <= 420), (">=600", lambda a: a >= 600), (">=900", lambda a: a >= 900)] if os.environ.get("LATE") == "1" else
       [("any", lambda a: True), ("<=30", lambda a: a <= 30), (">=60", lambda a: a >= 60), (">=120", lambda a: a >= 120)]),
    v=[(36, 45), (36, 55), (36, 999), (40, 55), (40, 70), (45, 70), (45, 999), (55, 90), (55, 999), (70, 999), (85, 999)],
    n15=([3, 10, 25, 50] if os.environ.get("LATE") == "1" else [0, 10, 25, 50, 100]), mom=[("any", None), ("dv>=0", ("dv", 0)), ("dv>=3", ("dv", 3)), ("dv>=6", ("dv", 6)), ("dd<=.85", ("dd", 0.85)), ("dd<=.7", ("dd", 0.7))],
    dsell=["any", "0", ">=1"], dev=["any", "<=1.5", ">=1.5"], gap=["any", "<=2"], mh=["any", "0", "1"])
def ok(f, key):
    (tn, tf), (vlo, vhi), n15, (mn, mm), ds_, dv_, gp, mh = key
    if mh == "0" and f["mh"]: return False
    if mh == "1" and not f["mh"]: return False
    if not tf(f["T"]): return False
    if not (vlo <= f["v"] < vhi): return False
    if f["n15"] < n15: return False
    if mm:
        if mm[0] == "dv" and f["dv"] < mm[1]: return False
        if mm[0] == "dd" and f["dd"] > mm[1]: return False
    if ds_ == "0" and f["dsell"] != 0: return False
    if ds_ == ">=1" and f["dsell"] < 1: return False
    if dv_ == "<=1.5" and f["dev"] > 1.5: return False
    if dv_ == ">=1.5" and f["dev"] < 1.5: return False
    if gp == "<=2" and f["gap"] > 2: return False
    return True
def select(key, fset=None):
    out = []; last = None
    for r in rows:
        if r["mint"] == last: continue
        if fset is not None and r["fold"] not in fset: continue
        if ok(r["f"], key):
            out.append(r); last = r["mint"]
    return out
keys = list(itertools.product(grid["T"], grid["v"], grid["n15"], grid["mom"], grid["dsell"], grid["dev"], grid["gap"], grid["mh"]))
print("rule filters", len(keys), "x exits", len(EX), "=", len(keys) * len(EX), flush=True)
res = []
trrows = [r for r in rows if r["fold"] == 0]
for key in keys:
    sel = []; last = None
    for r in trrows:
        if r["mint"] == last: continue
        if ok(r["f"], key):
            sel.append(r["pv"]); last = r["mint"]
    if len(sel) < 30: continue
    for j in range(len(EX)):
        v = [s[j] for s in sel if s[j] is not None]
        if len(v) < 30: continue
        tot = sum(v); top3 = sum(heapq.nlargest(3, v))
        res.append(((tot - top3) / (len(v) - 3), tot / len(v), len(v), key, j))
res.sort(key=lambda r: -r[0])
print("combos with n_train>=30:", len(res), " train ex3>0:", sum(1 for r in res if r[0] > 0), " train mean>0:", sum(1 for r in res if r[1] > 0), flush=True)
K = 30; seen = set(); top = []
for ex3, mean, n, key, j in res:
    sig = (key[1], key[2], key[3], key[7], EX[j][0])
    if sig in seen: continue
    seen.add(sig); top.append((key, j))
    if len(top) >= K: break
pos = 0
for key, j in top:
    sel = select(key); X = EX[j][0]
    nm = "T%s v%s-%s n15>=%d %s dsell:%s dev:%s gap:%s mh:%s" % (key[0][0], key[1][0], key[1][1], key[2], key[3][0], key[4], key[5], key[6], key[7])
    line = [nm, str(EX[j])]
    for f in (0, 1, 2):
        line.append("F%d %s" % (f, fmt(stats([r["pv"][j] for r in sel if r["fold"] == f]), f, X)))
    d = stats([r["pv"][j] for r in sel if r["fold"] > 0])
    line.append("TEST " + fmt(d))
    if d.get("n", 0) >= 40 and d["mean"] > 0 and d["ex3"] > 0: pos += 1
    print("\n  ".join(line))
print("top-%d by train ex3: test-positive (n>=40, mean>0, ex3>0): %d" % (K, pos))
pickle.dump([(a, b, c, (k[0][0],) + tuple(k[1:]), j) for a, b, c, k, j in res[:3000]], open("/root/strat/search_%s_%s.pkl" % (MODEL, SPLIT), "wb"))
# ---- robustness scan: every filter x exit, stats on train (F0), ds-test (F1), truth (F2) ----
print("\n== robustness scan (all filters, all exits): combos positive (mean>0 & ex3>0) in each fold, n>=30 per fold ==", flush=True)
cnt = collections.Counter(); keep = []
for key in keys:
    sel = {0: [], 1: [], 2: []}; last = None
    for r in rows:
        if r["mint"] == last: continue
        if ok(r["f"], key):
            sel[r["fold"]].append(r["pv"]); last = r["mint"]
    if min(len(sel[0]), len(sel[1]) + len(sel[2])) < 30: continue
    for j in range(len(EX)):
        res3 = []
        for f in (0, 1, 2):
            v = [s[j] for s in sel[f] if s[j] is not None]
            if len(v) < 4: res3.append(None); continue
            tot = sum(v); top3 = sum(heapq.nlargest(3, v))
            res3.append((len(v), tot / len(v), (tot - top3) / (len(v) - 3)))
        te = [s[j] for f in (1, 2) for s in sel[f] if s[j] is not None]
        if len(te) < 40 or res3[0] is None or res3[0][0] < 30: continue
        tt = sum(te); t3 = sum(heapq.nlargest(3, te))
        tr_ok = res3[0][1] > 0 and res3[0][2] > 0
        te_ok = tt / len(te) > 0 and (tt - t3) / (len(te) - 3) > 0
        cnt["evaluated"] += 1
        cnt["train+"] += tr_ok; cnt["test+"] += te_ok; cnt["both+"] += tr_ok and te_ok
        if te_ok: keep.append((tt / len(te), len(te), key, j, res3))
print(dict(cnt))
keep.sort(key=lambda r: -r[0])
for m, n, key, j, res3 in keep[:15]:
    nm = "T%s v%s-%s n15>=%d %s dsell:%s dev:%s gap:%s mh:%s" % (key[0][0], key[1][0], key[1][1], key[2], key[3][0], key[4], key[5], key[6], key[7])
    print("test+ %s %s TEST n=%d mean %+.1f%% | per fold (n, mean, ex3): %s" % (nm, EX[j], n, 100 * m, [(a[0], round(100 * a[1], 1), round(100 * a[2], 1)) if a else None for a in res3]))

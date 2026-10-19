# Per-family: pick best variant on TRAIN (F0, ds early) by ex-top3 mean, report TEST (F1 ds late + F2 truth). Paper/offline.
import sys, pickle, itertools, collections, statistics, heapq, os
sys.path.insert(0, "/root/strat")
from sim import DS_W
MIN_TR = int(os.environ.get("MIN_TR", "20"))
TAB = sys.argv[1]; MODEL = sys.argv[2] if len(sys.argv) > 2 else "pn"
rows, meta = pickle.load(open(TAB, "rb"))
rows.sort(key=lambda r: (r["mint"], r["dk"]))
ds_bt = sorted(m[2] for m in meta if m[1] == "ds" and not m[4]); cut = ds_bt[int(0.6 * len(ds_bt))]
fold = lambda src, bt: (0 if bt < cut else 1) if src == "ds" else 2
for r in rows: r["fold"] = fold(r["src"], r["bt"])
fb = collections.defaultdict(list)
for m in meta:
    if not m[4]: fb[fold(m[1], m[2])].append(m[2])
H = {f: (max(v) - min(v)) / 3600 for f, v in fb.items()}; W = {0: DS_W, 1: DS_W, 2: 1.0}
EXS = []
for k in rows[0][MODEL]:
    if k[1] not in EXS: EXS.append(k[1])
def st(v):
    v = [a for a in v if a is not None]
    if len(v) < 4: return None
    s = sorted(v); return dict(n=len(v), mean=sum(v) / len(v), med=statistics.median(v), ex3=sum(s[:-3]) / (len(s) - 3), win=sum(1 for a in v if a > 0) / len(v))
def fmt(d, f=None, X=1.0):
    if not d: return "n<4"
    s = "n=%d mean %+.1f%% med %+.1f%% ex3 %+.1f%% win %.0f%%" % (d["n"], 100 * d["mean"], 100 * d["med"], 100 * d["ex3"], 100 * d["win"])
    if f is not None:
        tpd = d["n"] * W[f] / H[f] * 24; s += " [%.0f/day, %+.1f SOL/day @%gSOL]" % (tpd, tpd * d["mean"] * X, X)
    return s
def sel(rule):
    out = []; last = None
    for r in rows:
        if r["mint"] == last: continue
        if rule(r["f"]): out.append(r); last = r["mint"]
    return out
FAM = {}
mhs = [("non-mayhem", lambda f: f["mh"] == 0), ("mayhem", lambda f: f["mh"] == 1), ("all", lambda f: True)]
# 1 momentum: activity + rising vsol
FAM["1 momentum"] = [("%s n15>=%d dv>=%g v>=%d T%s" % (mn, n15, dv, vlo, tn), (lambda m, n15, dv, vlo, tf: (lambda f: m(f) and f["n15"] >= n15 and f["dv"] >= dv and f["v"] >= vlo and tf(f["T"])))(m, n15, dv, vlo, tf))
                     for (mn, m), n15, dv, vlo, (tn, tf) in itertools.product(mhs, [10, 25, 50, 100], [0, 3, 6, 10], [36, 45, 55], [("any", lambda t: True), ("<=30", lambda t: t <= 30), (">=60", lambda t: t >= 60), (">=120", lambda t: t >= 120), (">=600", lambda t: t >= 600)])]
# 2 graduation / high curve
FAM["2 high-curve/graduation"] = [("%s v>=%d n15>=%d" % (mn, vlo, n15), (lambda m, vlo, n15: (lambda f: m(f) and f["v"] >= vlo and f["n15"] >= n15))(m, vlo, n15))
                                  for (mn, m), vlo, n15 in itertools.product(mhs, [70, 80, 90, 100], [0, 10, 25])]
# 3 dip / second wave
FAM["3 dip/second-wave"] = [("%s dd<=%.2f vmax>=%d n15>=%d T%s" % (mn, dd, vm, n15, tn), (lambda m, dd, vm, n15, tf: (lambda f: m(f) and f["dd"] <= dd and f["vmax"] >= vm and f["n15"] >= n15 and tf(f["T"])))(m, dd, vm, n15, tf))
                            for (mn, m), dd, vm, n15, (tn, tf) in itertools.product(mhs, [0.5, 0.7, 0.85], [45, 60, 80], [0, 10, 25], [("any", lambda t: True), (">=60", lambda t: t >= 60), (">=300", lambda t: t >= 300)])]
# 4 dev behaviour
FAM["4 dev"] = [("%s dsell==0 dev%s n15>=%d T%s" % (mn, dn, n15, tn), (lambda m, dvf, n15, tf: (lambda f: m(f) and f["dsell"] == 0 and dvf(f["dev"]) and f["n15"] >= n15 and tf(f["T"])))(m, dvf, n15, tf))
                for (mn, m), (dn, dvf), n15, (tn, tf) in itertools.product(mhs, [("any", lambda d: True), ("<=0.5", lambda d: d <= 0.5), (">=1", lambda d: d >= 1), (">=3", lambda d: d >= 3)], [0, 10, 25], [("any", lambda t: True), (">=60", lambda t: t >= 60), (">=120", lambda t: t >= 120)])]
ntried = 0
for fam, rules in FAM.items():
    best = None; cand = 0
    for name, rule in rules:
        s = sel(rule); tr = [r for r in s if r["fold"] == 0]
        for X in (1.0, 2.0):
            for e in EXS:
                v = [r[MODEL][(X, e)] for r in tr if r[MODEL].get((X, e)) is not None]
                if len(v) < MIN_TR: continue
                cand += 1
                d = st(v)
                if best is None or d["ex3"] > best[0]: best = (d["ex3"], name, rule, X, e)
    ntried += cand
    print("\n## %s: %d rule x exit x size variants with n_train>=%d" % (fam, cand, MIN_TR))
    if not best: print("   none with n_train>=30"); continue
    _, name, rule, X, e = best
    s = sel(rule)
    print("   best on train: %s | exit %s | size %g SOL" % (name, e, X))
    for f, lab in ((0, "train F0 ds-early"), (1, "test F1 ds-late"), (2, "test F2 truth")):
        print("     %-18s %s" % (lab, fmt(st([r[MODEL][(X, e)] for r in s if r["fold"] == f]), f, X)))
    print("     %-18s %s" % ("TEST F1+F2", fmt(st([r[MODEL][(X, e)] for r in s if r["fold"] > 0]))))
print("\ntotal variants scored in this file:", ntried)

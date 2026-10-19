# Post-migration (PumpSwap) strategy test. Census of migrations; time split 60/40. Paper/offline.
import sys, json, statistics, itertools, collections, heapq
FEE = float(sys.argv[1]) if len(sys.argv) > 1 else 0.012   # per side: lp 0.20% + protocol 0.05% + creator 0.80-0.95%
PRIO = 0.000305
R = []
for l in open("/root/strat/grad.jsonl"):
    x = json.loads(l)
    if not x.get("pts") or not x.get("sol0") or x["sol0"] < 40e9: continue
    st = {}; last = None
    for d, p in x["pts"]:
        if p and p[2] and p[3]: last = (p[2], p[3])
        st[d] = last
    x["st"] = st; R.append(x)
R.sort(key=lambda x: x["bt"])
print("graduations with pool SOL >= 40 at migration:", len(R), "hours", round((R[-1]["bt"] - R[0]["bt"]) / 3600, 1))
print("sol0 quantiles", [round(q / 1e9, 1) for q in statistics.quantiles([x["sol0"] for x in R], n=5)])
cut = R[int(0.6 * len(R))]["bt"]
H = {0: (cut - R[0]["bt"]) / 3600, 1: (R[-1]["bt"] - cut) / 3600}
def pnl(x, de, dx, X, double=True):
    a, b = x["st"].get(de), x["st"].get(dx)
    if not a or not b: return None
    Q, B = a; aa = X * 1e9 / (1 + FEE); q = B * aa / (Q + aa)
    Q2, B2 = b
    if not double: Q2 = Q2 + aa; B2 = b[0] * b[1] / Q2
    out = Q2 * q / (B2 + q) * (1 - FEE) / 1e9
    return (out - X - 2 * PRIO) / X
def st(v):
    v = [a for a in v if a is not None]
    if len(v) < 4: return "n<4"
    s = sorted(v); return "n=%3d mean %+6.1f%% med %+6.1f%% ex3 %+6.1f%% win %3.0f%%" % (len(v), 100 * sum(v) / len(v), 100 * statistics.median(v), 100 * sum(s[:-3]) / (len(s) - 3), 100 * sum(1 for a in v if a > 0) / len(v))
DE = [2, 5, 15, 30, 60]; DX = [30, 60, 120, 300, 600, 1200, 1800, 3600]
print("\n== baseline: buy every graduation at +de s, sell at +dx s, 1 SOL, double impact; train (first 60%) | test (last 40%)")
for de in DE:
    for dx in DX:
        if dx <= de: continue
        tr = [pnl(x, de, dx, 1.0) for x in R if x["bt"] < cut]; te = [pnl(x, de, dx, 1.0) for x in R if x["bt"] >= cut]
        print("  in %3ds out %4ds  TRAIN %s | TEST %s" % (de, dx, st(tr), st(te)))
# selection grid on train
feats = dict(sol0=lambda x: x["sol0"] / 1e9, n60=lambda x: x.get("pre_n60") or 0, n300=lambda x: x.get("pre_n300") or 0,
             mom=lambda x: (x["st"][2][0] / x["st"][2][1]) / (x["sol0"] / x["tok0"]) if x["st"].get(2) and x["tok0"] else 1.0)
grid = list(itertools.product([("any", lambda x: True), ("sol0>=70", lambda x: x["sol0"] >= 70e9), ("sol0<70", lambda x: x["sol0"] < 70e9)],
                              [0, 50, 150, 300], [0, 200, 600], [("any", lambda m: True), ("up@2s", lambda m: m > 1.05), ("flat@2s", lambda m: m <= 1.05)]))
res = []
ntried = 0
for (sn, sf), n60, n300, (mn, mf) in grid:
    sel = [x for x in R if sf(x) and (x.get("pre_n60") or 0) >= n60 and (x.get("pre_n300") or 0) >= n300 and mf(feats["mom"](x))]
    tr = [x for x in sel if x["bt"] < cut]
    if len(tr) < 25: continue
    for de in DE:
        for dx in DX:
            if dx <= de: continue
            for X in (1.0, 2.0):
                v = [pnl(x, de, dx, X) for x in tr]; v = [a for a in v if a is not None]
                if len(v) < 25: continue
                ntried += 1
                s = sorted(v); ex3 = sum(s[:-3]) / (len(s) - 3)
                res.append((ex3, sn, n60, n300, mn, de, dx, X))
res.sort(key=lambda r: -r[0])
print("\n== selection: %d combos (n_train>=25); train ex3>0: %d" % (ntried, sum(1 for r in res if r[0] > 0)))
pos = 0
for r in res[:15]:
    ex3, sn, n60, n300, mn, de, dx, X = r
    sel = [x for x in R if dict(grid_lookup := {})] if False else None
    sf = {"any": lambda x: True, "sol0>=70": lambda x: x["sol0"] >= 70e9, "sol0<70": lambda x: x["sol0"] < 70e9}[sn]
    mf = {"any": lambda m: True, "up@2s": lambda m: m > 1.05, "flat@2s": lambda m: m <= 1.05}[mn]
    sel = [x for x in R if sf(x) and (x.get("pre_n60") or 0) >= n60 and (x.get("pre_n300") or 0) >= n300 and mf(feats["mom"](x))]
    tr = [pnl(x, de, dx, X) for x in sel if x["bt"] < cut]; te = [pnl(x, de, dx, X) for x in sel if x["bt"] >= cut]
    tev = [a for a in te if a is not None]
    if len(tev) >= 40 and sum(tev) > 0 and sum(sorted(tev)[:-3]) > 0: pos += 1
    tpd = len(tev) / H[1] * 24
    print("  %s n60>=%d n300>=%d %s in %ds out %ds %gSOL\n     TRAIN %s\n     TEST  %s  [%.0f/day, %+.1f SOL/day]" % (sn, n60, n300, mn, de, dx, X, st(tr), st(te), tpd, tpd * X * (sum(tev) / len(tev) if tev else 0)))
print("top-15 test-positive (n>=40, mean>0, ex3>0):", pos)

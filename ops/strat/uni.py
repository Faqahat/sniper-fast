# univariate look (pooled; exploration only)
import sys, pickle, statistics
sys.path.insert(0, "/root/strat")
rows, meta = pickle.load(open("/root/strat/table.pkl", "rb"))
first = {}
for r in sorted(rows, key=lambda r: r["dk"]):
    first.setdefault(r["mint"], r)
F = list(first.values())
E = [(1.0, ("time", 30)), (1.0, ("time", 120)), (1.0, ("trail", 0.25, 300)), (1.0, ("tpsl", 1.5, 0.7, 300))]
def s(v):
    v = [a for a in v if a is not None]
    if len(v) < 5: return "n=%d" % len(v)
    return "n=%d %+.1f/%+.1f" % (len(v), 100 * sum(v) / len(v), 100 * statistics.median(v))
print("MFE quantiles (first entries):", [round(q, 2) for q in statistics.quantiles([r["mfe"] for r in F if r["mfe"]], n=10)])
for key, cuts in [("T", [15, 30, 60, 90, 120, 180, 240]), ("v", [36, 40, 45, 55, 70, 90, 200]), ("n15", [0, 10, 25, 50, 100, 200, 9999]), ("n", [0, 25, 50, 100, 200, 400, 99999]),
                  ("dv", [-99, 0, 2, 4, 8, 15, 99]), ("dd", [0, 0.7, 0.85, 0.95, 1.01]), ("dsell", [0, 1, 2, 5, 99]), ("dev", [-1, 0.2, 1, 2, 4, 9]), ("gap", [0, 0.5, 2, 5, 15, 999]), ("nerr", [0, 1, 5, 20, 9999])]:
    print("==", key)
    for lo, hi in zip(cuts, cuts[1:]):
        sel = [r for r in rows if lo <= r["f"][key] < hi] if key == "T" or True else []
        print("  [%s,%s) all-ck" % (lo, hi), " | ".join("%s %s" % (e[1][0][:2] + str(e[1][1]), s([r["pn"][e] for r in sel])) for e in E), " | mfe med %.2f" % (statistics.median([r["mfe"] for r in sel if r["mfe"]]) if sel else 0))

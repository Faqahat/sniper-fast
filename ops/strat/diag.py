# Diagnostics: what happens after a checkpoint entry (non-mayhem vs mayhem), first entry per token. Paper.
import sys, pickle, statistics, collections
sys.path.insert(0, "/root/strat")
rows, meta = pickle.load(open(sys.argv[1] if len(sys.argv) > 1 else "/root/strat/table.pkl", "rb"))
first = {}
for r in sorted(rows, key=lambda r: r["dk"]): first.setdefault(r["mint"], r)
F = list(first.values())
for mh in (0, 1):
    G = [r for r in F if r["f"]["mh"] == mh]
    if not G: continue
    m = sorted(r["mfe"] for r in G if r.get("mfe"))
    print("mayhem=%d tokens=%d  MFE (max price within 300 s / entry) p25 %.2f p50 %.2f p75 %.2f p90 %.2f  share MFE>=2x %.1f%%" % (
        mh, len(G), m[len(m) // 4], m[len(m) // 2], m[3 * len(m) // 4], m[9 * len(m) // 10], 100 * sum(1 for a in m if a >= 2) / len(m)))
    for ex in [(1.0, ("time", 60)), (1.0, ("time", 300))]:
        v = sorted(r["pn2"][ex] for r in G if r["pn2"].get(ex) is not None)
        print("   %s shift-model return quantiles p10 %+.0f%% p25 %+.0f%% p50 %+.0f%% p75 %+.0f%% p90 %+.0f%%  share <= -30%%: %.0f%%" % (
            ex[1], 100 * v[len(v) // 10], 100 * v[len(v) // 4], 100 * v[len(v) // 2], 100 * v[3 * len(v) // 4], 100 * v[9 * len(v) // 10], 100 * sum(1 for a in v if a <= -0.3) / len(v)))

import json, collections, sys
d = sys.argv[1]
A = [json.loads(l) for l in open(f"{d}/arrivals.jsonl") if l.strip()]
q = lambda v, p: sorted(v)[int((len(v) - 1) * p)] if v else float('nan')
t_lo = min(min(a["arrivals"].values()) for a in A); t_hi = max(min(a["arrivals"].values()) for a in A)
print(f"triggers {len(A)} over {(t_hi - t_lo) / 6e10:.1f} min")
def table(rows, title):
    seen = collections.Counter(); first = collections.Counter(); lag = collections.defaultdict(list)
    for a in rows:
        arr = a["arrivals"]; t0 = min(arr.values()); f0 = min(arr, key=arr.get); first[f0] += 1
        for f, t in arr.items(): seen[f] += 1; lag[f].append((t - t0) / 1e6)
    print(f"{title} ({len(rows)} triggers)")
    for f in sorted(lag, key=lambda f: q(lag[f], .5)):
        v = lag[f]
        print(f"  {f:18s} saw {seen[f]*100/len(rows):5.1f}%  first {first[f]*100/len(rows):5.1f}%  behind first p50 {q(v,.5):6.2f} p90 {q(v,.9):6.2f} ms")
table(A, "all triggers")
raiden_live = [a for a in A if "raiden" in a["arrivals"]]
table(raiden_live, "while Raiden was live")
table([a for a in A if "raiden" not in a["arrivals"]], "after Raiden expired")

import json, gzip, collections, sys
B = "/home/moiz/sniper/ops/agents/topearners/work/"
TOP = [l.strip() for l in open(B + sys.argv[1]) if l.strip()]
by = collections.defaultdict(list)
for line in gzip.open(B + "buys.jsonl.gz", "rt"):
    r = json.loads(line)
    if r["w"] in TOP and r.get("ds") is not None: by[r["w"]].append(r)
def med(v):
    v = sorted(v); return v[len(v)//2] if v else None
def stats(R):
    n = len(R)
    ss = sum(1 for r in R if r["ds"] == 0) / n
    di = med([r["di"] for r in R if r["di"] is not None])
    r0 = sum(1 for r in R if r.get("rank") == 0) / n
    pn = [r["pnl"] if r["pnl"] is not None else r["pnl_mtm"] for r in R]
    pn = [p for p in pn if p is not None]
    ret = sum(pn) / max(1, sum(r["sol"] for r in R)) * 100
    return f"n={n:5d} same-slot={ss:5.2f} med_di={di} first={r0:4.2f} ret%={ret:5.2f}"
for w in TOP:
    R = by[w]
    if not R: continue
    print("=" * 30, w[:10], "dip buys", len(R), stats(R))
    g = collections.defaultdict(list)
    for r in R: g["+".join(r.get("relays") or []) or "(none)"].append(r)
    for k, v in sorted(g.items(), key=lambda kv: -len(kv[1]))[:8]:
        if len(v) >= 30: print(f"   relay {k:22s} {stats(v)}")
    g = collections.defaultdict(list)
    for r in R:
        if r["run"] == "R2" and r.get("cls0"): g[r["cls0"]].append(r)
    for k, v in sorted(g.items(), key=lambda kv: -len(kv[1]))[:7]:
        if len(v) >= 30: print(f"   dump-leader {k:16s} {stats(v)}")

#!/usr/bin/env python3
# What decides which launches of a followed deployer the case-study wallets attempt? Within-deployer comparison
# (each deployer's own attempt rate as baseline -> lift) over both collector runs, create-time + bundle features only.
import sys, os, json, gzip, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches(); A = json.load(open("attempts.json"))
T = {}
for l in gzip.open("/home/moiz/sniper-data/collect/paper/table_dump.jsonl.gz", "rt"):
    r = json.loads(l); T[r["mint"]] = r
byd = collections.defaultdict(list)
for m, c in L.items(): byd[c["user"]].append(m)
def feats(m):
    t = T.get(m, {}); c = L[m]
    tot = (t.get("dev_buy") or 0) + (t.get("glued_sol") or 0)
    return dict(dev_buy=t.get("dev_buy"), glued_n=t.get("glued_n"), glued_sol=t.get("glued_sol"), devside_sol=tot, mayhem=t.get("mayhem"),
                variant=(c.get("ixn") or ["?"])[0], quote_sol=1 if (t.get("max_vsol") or 0) >= 25 else 0, host=t.get("uri_host"), created_on=t.get("created_on"),
                gap_min=t.get("cr_min_since_prev_create"), payer_is_creator=t.get("payer_is_creator"), tw=t.get("has_tw"), hour=t.get("hour_utc"))
BINS = dict(dev_buy=[0, 1e-9, 0.5, 1, 2, 3, 5, 10], glued_n=[0, 1, 2, 3, 5], glued_sol=[0, 1e-9, 1, 3, 6, 12], devside_sol=[0, 1, 2, 3, 4, 5, 7, 10, 15, 25],
            gap_min=[0, 1, 5, 15, 60])
def lab(k, v):
    if k not in BINS: return str(v)[:24]
    if v is None: return "None"
    b = BINS[k]; i = max(j for j in range(len(b)) if v >= b[j]); return f">={b[i]}"
for w in ("9Sh2fd", "DGmspi", "D24ipY"):
    deps = collections.Counter(L[m]["user"] for m, v in A.items() if w in v and m in L)
    deps = [d for d, n in deps.items() if n >= 3]
    rows = []
    for d in deps:
        ms = byd[d]; rate = sum(1 for m in ms if w in A.get(m, {})) / len(ms)
        for m in ms: rows.append((int(w in A.get(m, {})), rate, feats(m)))
    print(f"\n== {w}: {len(deps)} deployers with >= 3 attempts, {len(rows)} launches, attempted {sum(r[0] for r in rows)}")
    for k in ["devside_sol", "dev_buy", "glued_n", "glued_sol", "variant", "quote_sol", "mayhem", "host", "created_on", "gap_min", "payer_is_creator"]:
        g = collections.defaultdict(lambda: [0, 0.0, 0])
        for a, rate, f in rows:
            x = g[lab(k, f[k])]; x[0] += a; x[1] += rate; x[2] += 1
        items = sorted(g.items(), key=lambda kv: -kv[1][2])[:9]
        print(f"   {k:16}" + " | ".join(f"{lb}: {a}/{n} lift {a / max(1e-9, e):.2f}" for lb, (a, e, n) in items))

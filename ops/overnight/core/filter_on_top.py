#!/usr/bin/env python3
# READ-ONLY, offline: inside each deployer (create signer) a case-study wallet follows, which launches did it ATTEMPT
# (bought or failed) and which did it skip? Compare create-time features to find the filter on top of the dev list.
import sys, os, json, gzip, collections, statistics
D = "/home/moiz/sniper-data/collect"; W = sys.argv[1] if len(sys.argv) > 1 else "9Sh2fd"
A = json.load(open("attempts.json"))
L = {}
for r in ["run_20261021_2207", "run_20261022_1543"]:
    for l in open(os.path.join(D, r, "launches.jsonl")):
        try: c = json.loads(l)
        except Exception: continue
        L.setdefault(c["mint"], c)
T = {}
for l in gzip.open(os.path.join(D, "paper", "table_dump.jsonl.gz"), "rt"):
    r = json.loads(l); T[r["mint"]] = r
by_dep = collections.defaultdict(list)
for m, c in L.items():
    by_dep[c["user"]].append(m)
att_dep = collections.Counter(L[m]["user"] for m, v in A.items() if W in v and m in L)
deps = [d for d, n in att_dep.items() if n >= 3]
print(f"{W}: deployers with >= 3 attempts in the two runs: {len(deps)}")
rows = []
for d in deps:
    ms = by_dep[d]; att = [m for m in ms if W in A.get(m, {})]
    print(f"   {d[:8]}: launches {len(ms):4}, attempted {len(att):3} ({len(att) / len(ms):.0%}), bought {sum(1 for m in att if A[m][W][0]):3}")
    for m in ms:
        t = T.get(m, {}); rows.append(dict(dep=d, att=int(m in att), **{k: t.get(k) for k in ["dev_buy", "glued_n", "glued_sol", "P0_mc_sol", "quote_sol", "mayhem", "create_variant", "uri_host", "created_on", "has_tw", "has_tg", "has_web", "name_len", "cr_min_since_prev_create", "payer_is_creator", "create_cup", "create_tips", "glued_wallets", "slot_buys", "n_trades"]}, name=L[m].get("name"), sym=L[m].get("symbol"), ixn=",".join(L[m].get("ixn") or [])[:60]))
def show(k, bins=None):
    g = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        v = r.get(k)
        if bins:
            if v is None: lab = "None"
            else: lab = next((b[2] for b in bins if b[0] <= v < b[1]), "other")
        else: lab = str(v)[:30]
        g[lab][0] += r["att"]; g[lab][1] += 1
    print(f"   {k}: " + " | ".join(f"{lab}: {a}/{n} ({a / n:.0%})" for lab, (a, n) in sorted(g.items(), key=lambda kv: -kv[1][1])[:12]))
print(f"\nall launches of those deployers: {len(rows)}, attempted {sum(r['att'] for r in rows)}")
show("dev_buy", [(0, 1e-9, "0"), (1e-9, 0.5, "<0.5"), (0.5, 1, "0.5-1"), (1, 2, "1-2"), (2, 3, "2-3"), (3, 5, "3-5"), (5, 10, "5-10"), (10, 1e9, "10+")])
show("glued_n", [(0, 1, "0"), (1, 2, "1"), (2, 3, "2"), (3, 5, "3-4"), (5, 99, "5+")])
show("glued_sol", [(0, 1e-9, "0"), (1e-9, 1, "<1"), (1, 3, "1-3"), (3, 6, "3-6"), (6, 12, "6-12"), (12, 1e9, "12+")])
show("P0_mc_sol", [(0, 30, "<30"), (30, 35, "30-35"), (35, 40, "35-40"), (40, 50, "40-50"), (50, 70, "50-70"), (70, 1e9, "70+")])
for k in ["quote_sol", "mayhem", "create_variant", "uri_host", "created_on", "has_tw", "payer_is_creator", "glued_wallets", "ixn"]: show(k)
show("cr_min_since_prev_create", [(0, 1, "<1m"), (1, 5, "1-5m"), (5, 15, "5-15m"), (15, 60, "15-60m"), (60, 1e9, "60m+")])
show("create_tips", [(0, 1e-12, "0"), (1e-12, 0.001, "<0.001"), (0.001, 0.01, "0.001-0.01"), (0.01, 1e9, "0.01+")])
json.dump(rows, open(f"fot_{W}.json", "w"))

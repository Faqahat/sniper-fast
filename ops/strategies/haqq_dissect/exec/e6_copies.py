#!/usr/bin/env python3
"""haqq on-chain txs per decision + path by leader client (MEASURED from the raw recordings).
Decision cluster = haqq buy txs (landed or failed) on the same mint within 2 slots of the previous one.
Losing copies that share the durable nonce never reach the chain, so on-chain txs per cluster = separate decisions (separate nonces).
Out: sniper-data/haqq_dissect/exec/t6_copies.txt"""
import pickle, collections, sys
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
D = "/home/moiz/sniper-data/haqq_dissect/exec"
rows = pickle.load(open(f"{D}/txs.pkl", "rb"))
out = []
def P(*a): out.append(" ".join(str(x) for x in a))
H = sorted([r for r in rows if r["w"] == "haqq" and r["kind"] == "buy"], key=lambda r: (r["mint"] or "", r["s"], r["i"]))
cl = []; cur = None
for r in H:
    if cur and r["mint"] == cur[-1]["mint"] and r["s"] - cur[-1]["s"] <= 2: cur.append(r)
    else:
        cur = [r]; cl.append(cur)
P("## haqq buy clusters (same mint, <=2 slots apart). On-chain txs per cluster:")
c = collections.Counter(len(x) for x in cl); P(dict(sorted(c.items())[:10]), "clusters", len(cl))
c2 = collections.Counter((sum(1 for r in x if r["ok"]), sum(1 for r in x if not r["ok"])) for x in cl)
P("(landed, failed) per cluster:", c2.most_common(10))
# after a failed buy: does a new buy follow on the same mint within 1..10 slots?
F = [r for r in H if not r["ok"]]
bym = collections.defaultdict(list)
for r in H: bym[r["mint"]].append(r)
retry = collections.Counter()
for r in F:
    later = [x for x in bym[r["mint"]] if (x["s"], x["i"]) > (r["s"], r["i"]) and x["s"] - r["s"] <= 10]
    k = "none" if not later else ("ok<=1slot" if later[0]["ok"] and later[0]["s"] - r["s"] <= 1 else "ok<=10" if later[0]["ok"] else "fail-again")
    retry[k] += 1
P("after a FAILED buy, next haqq buy on the same mint within 10 slots:", dict(retry), f"(failed buys {len(F)})")
P("")
P("## haqq landed path share by leader client (all days; buys and sells)")
cnt = collections.defaultdict(collections.Counter); fails = collections.defaultdict(collections.Counter)
for r in rows:
    if r["w"] != "haqq" or r["kind"] not in ("buy", "sell"): continue
    _, cc, _ = L.leader_info(r["s"])
    if r["ok"]: cnt[(cc, r["kind"])][r["path"]] += 1
    elif r["kind"] == "buy": fails[cc]["tier_" + ("hi" if r["fee"] >= 60000 else "lo") + "_ix" + str(r["eidx"])] += 1
for k in sorted(cnt):
    n = sum(cnt[k].values())
    P(f"{k[0]:9} {k[1]:4} n={n:6} " + " ".join(f"{p}:{100*v/n:.0f}%" for p, v in cnt[k].most_common(6)))
P("failed buys by client:", {k: dict(v) for k, v in fails.items()})
P("")
P("## our landed regular-fill path by client (on chain)")
oc = collections.defaultdict(collections.Counter)
for r in rows:
    if r["w"] in ("FRA", "AMS") and r["kind"] == "buy" and r["fee"] >= 400000:
        _, cc, _ = L.leader_info(r["s"], r["w"])
        oc[(cc, "fill" if r["ok"] else "fail")][r["path"] if r["ok"] else "n/a"] += 1
for k in sorted(oc):
    n = sum(oc[k].values()); P(f"{k[0]:9} {k[1]:4} n={n:5} " + " ".join(f"{p}:{100*v/n:.0f}%" for p, v in oc[k].most_common(5)))
open(f"{D}/t6_copies.txt", "w").write("\n".join(out) + "\n")
print("\n".join(out))

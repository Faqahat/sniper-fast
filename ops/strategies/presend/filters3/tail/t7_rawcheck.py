#!/usr/bin/env python3
"""TAIL t7: check the signing-time holder approximation (fill ann holders + crossing sellers added back) against EXACT holder state
rebuilt from the raw recording (botpnl p2 rows: every pump trade on our mints) at the filled attempt's signing position (slot, idx),
for fills inside recorded hours. Compares: max other holder (vs the engine's exact ob6 too), sum of others, same-first-buy-slot group."""
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/tail")
from tlib import *; from tfeat import feats
S = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/f3_tail"
P = [d for d in load() if d["run"] in (37, 40, 41, 42)]
lim = collections.defaultdict(int)
for d in P: lim[d["mint"]] = max(lim[d["mint"]], d["fill"]["slot"])
tr = collections.defaultdict(list); first = {}
for fn in ("p2_a", "p2_b", "p2_c"):
    for l in open(f"{S}/{fn}.jsonl"):
        r = json.loads(l)
        if r["err"] or r["s"] > lim.get(r["mint"], 0): continue
        tr[r["mint"]].append((r["s"], r["i"] or 0, r["u"], r["tok"], r["cpre"]))
out = []
for d in P:
    t = sorted(tr.get(d["mint"], []))
    if not t or t[0][4] not in (0, None) and False: continue
    # need the create (first trade with cpre == 0 or the curve's full balance) to trust balances
    created = any(x[4] in (0, None) or x[4] >= 793e12 for x in t[:3])
    if not created: continue
    pos = tuple((d["att"].get("pos") or [0, 0])[:2])
    bal = collections.defaultdict(int); fb = {}
    for s, i, u, tok, c in t:
        if (s, i) > pos: break
        bal[u] += tok
        if tok > 0 and u not in fb: fb[u] = s
    F = feats(d)
    if not F["has_ann"]: continue
    wh = F["whale"]
    hs = [(u, b / 1e13, fb.get(u)) for u, b in bal.items() if b / 1e13 >= 2 and u not in OURS]
    oth = [h for h in hs if h[0] != wh]
    g = collections.defaultdict(float)
    for h in oth: g[h[2]] += h[1]
    ex = {"max_oth": max([h[1] for h in oth], default=0), "sum_oth": sum(h[1] for h in oth), "samage": max(g.values(), default=0),
          "n_oth6": sum(1 for h in oth if h[1] >= 6), "sum_oth4": sum(h[1] for h in oth if h[1] >= 4)}
    out.append({"rk": d["rk"], "pnl": d["pnl"], "ob6": F["ob6"], "ex": ex, "ap": {k: F[k] for k in ex}})
json.dump(out, open(f"{T}/rawcheck.json", "w"))
print("fills checked", len(out), collections.Counter(o["rk"] for o in out))
import statistics as stt
for k in ("max_oth", "sum_oth", "samage", "n_oth6", "sum_oth4"):
    dif = [o["ap"][k] - o["ex"][k] for o in out]
    print(f"{k}: approx - exact median {stt.median(dif):+.2f} p10 {sorted(dif)[len(dif)//10]:+.2f} p90 {sorted(dif)[9*len(dif)//10]:+.2f} | |diff|<=1: {sum(1 for x in dif if abs(x)<=1)/len(dif):.2f}")
dif = [o["ob6"] - o["ex"]["max_oth"] for o in out if o["ob6"] is not None]
print(f"engine ob6 - exact max_oth: median {stt.median(dif):+.2f} |diff|<=1: {sum(1 for x in dif if abs(x)<=1)/len(dif):.2f}")
for k, x in (("samage", 20), ("sum_oth", 35), ("n_oth6", 3), ("sum_oth4", 25)):
    a = [o["ap"][k] >= x for o in out]; e = [o["ex"][k] >= x for o in out]
    print(f"{k}>={x}: approx {sum(a)} exact {sum(e)} both {sum(1 for p, q in zip(a, e) if p and q)}")

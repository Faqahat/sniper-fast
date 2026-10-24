#!/usr/bin/env python3
# READ-ONLY, offline: what separates the launches each wallet bought from all launches in the same hours (sel.json).
import sys, json, collections, statistics, re
S = json.load(open(sys.argv[1])); F = S["features"]; C = S["creators"]; NU = S["n_universe_total"]
U = [F[s] for s in S["universe"] if s in F]
BW = collections.defaultdict(list)
for b in S["bought"]:
    f = F.get(b["create_sig"])
    if f: BW[b["w"]].append(dict(f, size=b["size"], delta=b["delta"]))
ALL = [x for v in BW.values() for x in v]
print(f"universe sample {len(U)} of {NU} creates in the window; bought snipes with features: {({k: len(v) for k, v in BW.items()})}")
def dev_b(x):
    d = x["dev_sol"]
    for lo, hi, n in ((0, 0.0001, "0"), (0.0001, 0.5, "<0.5"), (0.5, 1, "0.5-1"), (1, 2, "1-2"), (2, 3, "2-3"), (3, 5, "3-5"), (5, 8, "5-8"), (8, 1e9, "8+")):
        if lo <= d < hi: return n
def tx_b(x):
    d = x["tx_buy_sol"]
    for lo, hi, n in ((0, 0.0001, "0"), (0.0001, 1, "<1"), (1, 3, "1-3"), (3, 6, "3-6"), (6, 10, "6-10"), (10, 1e9, "10+")):
        if lo <= d < hi: return n
def act_b(x):
    a = C.get(x["creator"]) or {}; n = a.get("n24_before", 0)
    return "0" if n == 0 else ("1-5" if n <= 5 else ("6-50" if n <= 50 else ("51-500" if n <= 500 else "500+")))
def age_b(x):
    a = C.get(x["creator"]) or {}
    if a.get("n_total", 0) >= 1000: return "busy (1000+ txs)"
    ob = a.get("oldest_bt"); 
    if not ob or not x["bt"]: return "?"
    h = (x["bt"] - ob) / 3600
    return "new (<1 h)" if h < 1 else ("<24 h" if h < 24 else ("1-7 d" if h < 168 else "7 d+"))
tipl = lambda x: ",".join(sorted({t[0] for t in x["tips"]})) or "no tip"
FEATS = {"quote": lambda x: x["quote"], "dev buy SOL": dev_b, "SOL bought in create tx": tx_b, "wallets buying in create tx": lambda x: str(min(x["n_buy_wallets"], 4)) + ("+" if x["n_buy_wallets"] >= 4 else ""),
         "launcher program": lambda x: x["launcher"][:10], "create instruction": lambda x: x["create_ix"], "metadata host": lambda x: x["host"][:28],
         "tip service in create tx": tipl, "creator txs in prior 24 h": act_b, "creator wallet age": age_b, "payer is creator": lambda x: str(x["payer_is_creator"]),
         "symbol all caps": lambda x: str(x["symbol"].isupper()), "name has non-ASCII": lambda x: str(bool(re.search(r"[^\x00-\x7f]", x["name"])))}
groups = {"ALL 3": ALL, **BW}
for fn, fx in FEATS.items():
    cu = collections.Counter(fx(x) for x in U); n = len(U)
    vals = sorted(cu, key=lambda v: -cu[v])[:9]
    cb = {g: collections.Counter(fx(x) for x in v) for g, v in groups.items()}
    allv = set(vals) | {v for g in cb.values() for v, _ in g.most_common(4)}
    print(f"\n== {fn}")
    print(f"   {'value':30} {'all launches':>12} " + " ".join(f"{g:>13}" for g in groups))
    for v in sorted(allv, key=lambda v: -(cu.get(v, 0) + 1000 * cb['ALL 3'].get(v, 0)))[:10]:
        line = f"   {str(v)[:30]:30} {cu.get(v, 0) / n:12.1%} "
        for g, c in cb.items():
            tot = sum(c.values()); line += f" {c.get(v, 0) / tot if tot else 0:12.1%}"
        print(line)

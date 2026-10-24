#!/usr/bin/env python3
# READ-ONLY, offline: CWiNFA's ledger PnL per token (after tips / fees, rent refunded) split by its place in line and
# landing (collector windows), by arrival ms in our engine's clock, by the launch's dev buy / bundle, by sell type.
import os, json, statistics, collections
HERE = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(os.path.join(HERE, "pnl.json")))["tokens"]; C = json.load(open(os.path.join(HERE, "coll_cw.json")))
A = {r["m"]: r["ms"] for r in json.load(open(os.path.join(HERE, "arrival_ms.json")))}
rows = [(m, P[m]["net"], C[m]) for m in P if m in C and C[m].get("buy")]
out = [f"tokens with ledger PnL and collector rows: {len(rows)} (sum {sum(p for _, p, _ in rows):+.3f} SOL)"]
def grp(name, f, order=None):
    g = collections.defaultdict(list)
    for m, p, c in rows:
        k = f(m, c)
        if k is not None: g[k].append(p)
    ks = order or sorted(g, key=str)
    out.append(f"by {name}: " + " | ".join(f"{k}: n {len(g[k])} {sum(g[k]):+.2f} SOL (mean {statistics.mean(g[k]):+.4f}, win {sum(x > 0 for x in g[k]) / len(g[k]):.0%})" for k in ks if k in g))
grp("outside buys ahead", lambda m, c: min(c["buy"]["ahead_tx"], 3), [0, 1, 2, 3])
grp("slot delta", lambda m, c: min(c["buy"]["ds"], 2), [0, 1, 2])
grp("arrival ms (our clock, R2)", lambda m, c: None if m not in A else ("<25" if A[m] < 25 else ("25-45" if A[m] < 45 else ("45-75" if A[m] < 75 else ("75-150" if A[m] < 150 else ">=150")))), ["<25", "25-45", "45-75", "75-150", ">=150"])
grp("entry price vs post-bundle", lambda m, c: None if not c["buy"]["mult_vs_bundle"] else ("<=1.02" if c["buy"]["mult_vs_bundle"] <= 1.02 else ("1.02-1.06" if c["buy"]["mult_vs_bundle"] <= 1.06 else ("1.06-1.15" if c["buy"]["mult_vs_bundle"] <= 1.15 else ">1.15"))), ["<=1.02", "1.02-1.06", "1.06-1.15", ">1.15"])
grp("dev buy SOL", lambda m, c: "<1" if c["dev"] < 0.9 else ("~1" if c["dev"] < 1.5 else ("1.5-3.5" if c["dev"] < 3.6 else ">3.5")), ["<1", "~1", "1.5-3.5", ">3.5"])
grp("glued bundle txs", lambda m, c: min(c["glued"], 3), [0, 1, 2, 3])
grp("run", lambda m, c: c["run"], ["R1", "R2"])
open(os.path.join(HERE, "bypos.txt"), "w").write("\n".join(out) + "\n"); print("\n".join(out))

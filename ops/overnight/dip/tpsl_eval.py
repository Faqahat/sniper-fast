#!/usr/bin/env python3
# Stop-loss / take-profit exits on the SAME trades: the out-of-fold picks of the 2-slot model (sel_final_none.jsonl, real follower
# limits), priced with every exit in the event file. Unguarded and with the 2% guard. Local data only.
# usage: python3 -I tpsl_eval.py EV_FILE SEL_FILE
import sys, json, gzip, collections
EVF, SELF = sys.argv[1], sys.argv[2]
EV = {}
for l in gzip.open(EVF, "rt"):
    r = json.loads(l); EV[(r["m"], r["age"])] = r
P = collections.defaultdict(list)
for l in open(SELF):
    r = json.loads(l); P[r["LAT"]].append(r)
for L in ("35", "50", "75"):
    keys = [(p["m"], p["age"]) for p in P[L] if (p["m"], p["age"]) in EV and L in EV[(p["m"], p["age"])]["pnl"]]
    exits = sorted(EV[keys[0]]["pnl"][L].keys(), key=lambda x: (not x.isdigit(), x))
    res = []
    for x in exits:
        un = sum(EV[k]["pnl"][L].get(x, 0) for k in keys)
        gu = sum((EV[k]["pnl"][L].get(x, 0) if EV[k]["px"].get(L, 1) <= 1.02 else -0.0002) for k in keys)
        res.append((gu, un, x))
    res.sort(reverse=True)
    print(f'\n"{L} ms": {len(keys)} picks of the 2-slot model, SOL over the data period (guarded / unguarded), best first:')
    for gu, un, x in res[:12]: print(f"   {x:16s} guarded {gu:+7.2f} | unguarded {un:+7.2f}")
    base = next(r for r in res if r[2] == "2")
    print(f"   baseline sell-at-2-slots: guarded {base[0]:+.2f} | unguarded {base[1]:+.2f}")

#!/usr/bin/env python3
"""WHALEFLIP step 9: re-arm fills split by "another >= 6% holder still holds at our fill". EXACT (tape, w4: the arm's holder list,
balances at our landing) where covered; ENGINE PROXY for all fills (presend_live_fill ann.holders >= 6%, not the trigger seller, just
before our buy). Live realized P&L. usage: w9_rearm.py"""
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/whaleflip")
import wlib as W
F = [f for f in W.load() if f["kind"] == "rearm"]
EX = {(r["run"], r["ses"], r["w"]): r for r in json.load(open(f"{W.D}/exact.json"))}
h, hp, P = W.hours(W.load())
g = collections.defaultdict(list); ge = collections.defaultdict(list); agree = collections.Counter()
for f in F:
    ann = f["fills"][0].get("ann") or {}
    sel = (f.get("dump") or {}).get("seller")
    prox = any(z["pct"] >= 6.0 and z["w"] != sel for z in ann.get("holders", []))
    g[(f["period"], prox)].append(f["pnl"])
    e = EX.get((f["run"], f["ses"], f["w"]))
    if e and e["covered"]:
        ge[(f["period"], bool(e.get("holder6_still")))].append(f["pnl"]); agree[(prox, bool(e.get("holder6_still")))] += 1
print("proxy vs exact (proxy, exact):", dict(agree))
for per in ("DEV", "VAL", "HOLD"):
    print(f"{per}: ENGINE PROXY all fills: still holds {W.fmt(W.st(g[(per, True)], hp[per]))} | none left {W.fmt(W.st(g[(per, False)], hp[per]))}")
    print(f"{per}: EXACT covered fills:   still holds {W.fmt(W.st(ge[(per, True)]))} | none left {W.fmt(W.st(ge[(per, False)]))}")

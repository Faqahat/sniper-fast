#!/usr/bin/env python3
# FINAL LOCKBOX (read-only). Every rule in the registry (all rounds, deduped by signature) is evaluated once on R3 (test day,
# never shown to the model); rules positive on BOTH R2 and R3 with >= 30 test trades are re-checked on R1 (10-22, a third
# day) and grouped when their R3 trades overlap (near-duplicates). Multiple-testing context: how often an R2-positive rule
# stays positive on R3 vs an R2-negative one. -> patterns/final.json + printed table
import sys, json, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p4_eval as E
PO = "/home/moiz/sniper-data/strategies/patterns"
reg = json.load(open(f"{PO}/registry.json")); rules = reg["rules"]
todo = [R for R in rules if "R3_35" not in R.get("res", {})]
if todo:
    res = E.evaluate_rules(todo, ("R3",), procs=9)
    for i, R in enumerate(todo): R.setdefault("res", {}).update(res[i])
json.dump(reg, open(f"{PO}/registry.json", "w"))
def g(R, day, lat=35): return R.get("res", {}).get(f"{day}_{lat}", {})
rows = [R for R in rules if g(R, "R2").get("n", 0) >= 20]
p2 = [R for R in rows if g(R, "R2")["pnl"] > 0]; n2 = [R for R in rows if g(R, "R2")["pnl"] <= 0]
ctx = dict(rules_total=len(rules), with_20_train_trades=len(rows), train_positive=len(p2),
           test_positive_given_train_positive=round(sum(1 for R in p2 if g(R, "R3").get("pnl", -1) > 0) / max(1, len(p2)), 3),
           test_positive_given_train_negative=round(sum(1 for R in n2 if g(R, "R3").get("pnl", -1) > 0) / max(1, len(n2)), 3))
print("context:", ctx)
passed = [R for R in p2 if g(R, "R3").get("n", 0) >= 30 and g(R, "R3")["pnl"] > 0]
print(f"positive on BOTH days with >= 30 test trades: {len(passed)}")
if passed:
    res = E.evaluate_rules(passed, ("R1", "R2", "R3"), procs=9, keep=True)
    for i, R in enumerate(passed): R["final"] = res[i]
# group near-duplicates by overlap of accepted R3 trades
groups = []
for R in sorted(passed, key=lambda R: -R["final"]["R3_35"]["pnl"]):
    ks = set(R["final"]["R3_35"].get("ks", []))
    for gp in groups:
        if len(ks & gp["ks"]) / max(1, min(len(ks), len(gp["ks"]))) >= 0.5: gp["members"].append(R["id"]); break
    else: groups.append(dict(lead=R["id"], ks=ks, members=[R["id"]]))
byid = {R["id"]: R for R in passed}
out = dict(context=ctx, groups=[])
for gp in groups:
    R = byid[gp["lead"]]; F = R["final"]
    o = dict(id=R["id"], name=R["name"], round=R["round"], event=R["event"], idle=R["idle"], mode=R["mode"], race=R["race"], size=R["size"],
             when=R["raw"].get("when"), exit=R["raw"].get("exit"), why=R["why"], members=gp["members"],
             res={k: {kk: vv for kk, vv in v.items() if kk not in ("ks", "pnls")} for k, v in F.items()})
    out["groups"].append(o)
json.dump(out, open(f"{PO}/final.json", "w"), indent=1)
for o in out["groups"]:
    r = o["res"]
    def f(k):
        x = r.get(k, {})
        return f"n {x.get('n', 0):5d} pnl {x.get('pnl', 0):+8.2f} mean {x.get('mean', 0):+.4f} win {x.get('win', 0):.0%} t {x.get('t', 0):5.2f}" if x.get("n") else "n 0"
    print(f"\n[{o['id']}] r{o['round']} {o['name']} | {o['event']} {o['mode']} race={o['race']} size={o['size']} | group {o['members']}")
    print(f"   when {json.dumps(o['when'])} exit {json.dumps(o['exit'])}")
    for day in ("R2", "R3", "R1"):
        for lat in ((35, 50) if o["race"] else (35,)):
            k = f"{day}_{lat}"
            if k in r: print(f"   {k}: {f(k)} | per_hour {r[k].get('per_hour')} trig {r[k].get('trig')} ahead {r[k].get('ahead_med')} dip {r[k].get('dip_overlap')} f7 {r[k].get('f7_overlap')} ex1 {r[k].get('ex1')}")

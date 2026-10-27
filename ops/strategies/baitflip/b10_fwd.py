#!/usr/bin/env python3
# FORWARD test on R5 (10-24 19:25 -> 10-25 PKT, recorded after every bait rule was frozen on 10-24 ~15:35 PKT):
# frozen bait rules unchanged, plus the same rules restricted to FRESH baiters (w_first == 1: the wallet's first trade
# of the day), which is how rotated bait wallets would look. All four days shown.
import sys, json, copy
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns")
import p4_eval as E
reg = json.load(open(f"{E.PO}/registry.json"))["rules"]
IDS = [336, 291, 370, 353]
rules = []
for i in IDS:
    R = copy.deepcopy(reg[i]); R.pop("res", None); R.pop("final", None); R["name"] = f"[{i}] " + R["name"]; rules.append(R)
    F = copy.deepcopy(R); F["name"] += " +FRESH"; F["conds"] = R["conds"] + [["w_first", "==", 1.0]]; rules.append(F)
DAYS = ("R1", "R2", "R3", "R5")
res = E.evaluate_rules(rules, DAYS, procs=8)
for i, R in enumerate(rules):
    print(f"\n{R['name']}\n   when {R['conds']}  exit tp {R['tp']} sl {R['sl']} max {R['max_slots']} on {R['on']}")
    for d in DAYS:
        v = res[i].get(f"{d}_35", {})
        if not v.get("n"): print(f"   {d}: none"); continue
        print(f"   {d}: n {v['n']:5d}  pnl {v['pnl']:+8.2f}  per trade {v['mean']:+.4f}  per SOL {v['per_sol']:+.4f}  win {100*v['win']:.0f}%  "
              f"med {v['med']:+.4f}  t {v['t']:5.2f}  w/o top1% {v['ex1']:+7.2f}  {v.get('per_hour',0):.0f}/h")

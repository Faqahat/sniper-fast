#!/usr/bin/env python3
"""Collect every result into exact.json."""
import json, glob, os
X = "/home/it/sniper-data/rivals/9pQQ/exact"
J = lambda f: json.load(open(f)) if os.path.exists(f) else None
out = dict(
    hard_rules=J("h0_hard.json"), fingerprint_slippage=J("h2_fp.json"), timer_vs_reactive=J("t1_timer.json"),
    H1_leader_wallets=J("h1_test.json"), H1b_route_classes={d: {k: v for k, v in x.items()} for d, x in (J("p3_route.json") or {}).items()},
    H3_simple_exit_rules={d: sorted(v.items(), key=lambda kv: -kv[1]["hit"])[:10] for d, v in (J("e1_rules.json") or {}).items()},
    H4_tree_buy_frozen=J("b1_tree_frozen.json"), H3_tree_sell_frozen=J("s1_tree_frozen.json"),
    gbdt_bound_buy=J("g1_b_rt_nog_final.json"), gbdt_bound_sell=J("g1_s_rt_nog_final.json"),
    calibration={d: J(f"c1_calib_{d}.json") for d in ("10-28", "10-30", "10-31", "11-02")},
    replica_sim=[{k: v for k, v in json.load(open(f)).items() if k != "trips"} for f in sorted(glob.glob(f"{X}/sim/sim_*.json"))])
json.dump(out, open("exact.json", "w"), indent=1, default=str); print("ok", os.path.getsize("exact.json"))

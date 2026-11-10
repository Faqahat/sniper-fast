#!/usr/bin/env python3
"""Collect the headline numbers of the 9pQQ dissection into 9pqq.json (reads this folder's json outputs)."""
import json, os
H = os.path.dirname(os.path.abspath(__file__))
def j(n):
    p = f"{H}/{n}"; return json.load(open(p)) if os.path.exists(p) else None
cl = j("clusters.json")
out = {
    "wallet": "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN",
    "windows_pkt": {"10-28": "10-28 19:05 -> 10-29 19:25 (24.3 h)", "10-30": "10-30 18:55 -> 10-31 19:14 (24.3 h)",
                    "10-31": "10-31 18:50 -> 11-01 19:09 (24.3 h)", "11-02": "11-02 17:50 -> 11-03 09:59 (16.1 h)"},
    "money_closed_trips": {"10-28": {"n": 4235, "net": 19.61, "per_day": 19.4, "wo_top5": 12.39, "wo_top20": -1.69},
                           "10-30": {"n": 8867, "net": 87.32, "per_day": 86.2, "wo_top5": 79.41, "wo_top20": 65.34},
                           "10-31": {"n": 7218, "net": 68.63, "per_day": 67.7, "wo_top5": 58.48, "wo_top20": 41.14},
                           "11-02": {"n": 7730, "net": 61.62, "per_day": 91.7, "wo_top5": 50.96, "wo_top20": 32.44},
                           "note": "fees+tips included, token-account rent refunded by CloseAccount credited per trip; failed txs cost 0.06-0.13 SOL/day extra"},
    "clusters": {k: v for k, v in (cl or {}).items() if k.split("|")[0] in ("entry", "entry x reentry", "entry x exit", "exit", "version x size", "hold band")},
    "buyins": j("buyins.json"), "reentry_grad": j("reentry_grad.json"), "interact": j("interact.json"), "ours_by_9pqq_history": j("ours_k.json"),
    "imitation": j("imitate.json"), "replica_our_landing": j("replica.json"), "exit_rules_70ms": j("exitrule_70.json"),
    "exit_learned_70ms": {k: v for k, v in (j("exitml_70.json") or {}).items()}, "exit_shift": j("exitshift.json"),
}
json.dump(out, open(f"{H}/9pqq.json", "w"), indent=1, default=str)
print("wrote", f"{H}/9pqq.json", os.path.getsize(f"{H}/9pqq.json"))

#!/usr/bin/env python3
"""Merge all verification outputs into verify.json (run after verify_main.py, arrival_bounds.py,
placement_consistency.py, rpc_check.py, rpc_missing2.py, patch_missing.py)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import replay as R  # noqa: E402

V = json.load(open(os.path.join(HERE, "verify.json")))
W = os.path.join(HERE, "work")


def load(name):
    p = os.path.join(W, name)
    return json.load(open(p)) if os.path.exists(p) else None


ab = load("arrival_bounds_unique.json")
pc = load("placement_consistency.json")
rc = load("rpc_check.json")
rm = load("rpc_missing2.json")
pm = load("patch_missing.json")

S = V["summary"]
if ab:
    S["placement_arrival_bounds_unique_anchors"] = {
        "monotonicity": ab["monotonicity"],
        **{L: {k: ab[L][k] for k in ab[L] if k != "rows"} for L in ("45", "60", "75")},
        "misplaced_rows": {L: [{"mint": r["mint"], "file_pnl": round(r["pnl"], 6), "fixed": r.get("fixed"),
                                "misplaced": r["misplaced"]} for r in ab[L]["rows"] if r["misplaced"]] for L in ("45", "60", "75")}}
if pc:
    S["placement_two_sided_correction"] = {L: {k: pc[L][k] for k in pc[L] if k != "changes"} | {"changes": pc[L]["changes"]}
                                           for L in ("45", "60", "75")}
if rc:
    S["rpc_spot_check"] = {"launches": [{"mint": e["mint"], "L": e["L"], "file_pnl": e["file_pnl"],
                                         "txs": {k: {kk: v.get(kk) for kk in ("sig", "ok", "all_fields_equal", "slot_rpc", "slot_raw", "err_rpc",
                                                                             "n_events_rpc", "n_events_raw", "rpc_reserves", "raw_reserves")}
                                                 for k, v in e["checks"].items()}} for e in rc["spot"]],
                           "block_order": rc["block_order"], "rpc_calls": rc.get("rpc_calls")}
    S["raw_data_gaps_found_on_chain"] = rc["missing_trades"] + (rm or [])
if pm:
    S["raw_data_gaps_pnl_effect"] = pm

# hold-length sensitivity under the literal (SPEC) rule
sens = {}
for H in (4, 5, 6, 8, 10, 12):
    R.HOLD_SLOTS = H
    _, rows = R.main({"buy_slot_mode": "after"}, write=False)
    sens[str(H)] = {L: round(sum(r["land"][L]["pnl"] for r in rows), 4) for L in ("45", "60", "75")}
R.HOLD_SLOTS = 5
S["hold_sensitivity_spec_rule_total_sol"] = sens
_, rows = R.main({"buy_slot_mode": "next"}, write=False)
S["max_replayed_vsol_during_holds_sol"] = round(max(r["land"][L].get("max_v", 0) for r in rows for L in ("45", "60", "75")) / 1e9, 3)

json.dump(V, open(os.path.join(HERE, "verify.json"), "w"), indent=1, default=str)
print("hold sensitivity", sens)
print("max replayed vsol", S["max_replayed_vsol_during_holds_sol"])
print("rpc", json.dumps([(e["mint"][:8], {k: v["all_fields_equal"] for k, v in e["txs"].items()}) for e in S.get("rpc_spot_check", {}).get("launches", [])]))
print("block order", [b.get("all_equal") for b in S.get("rpc_spot_check", {}).get("block_order", [])])

#!/usr/bin/env python3
"""Re-run the 4 launches whose raw data misses trades, with the missing trades (found on chain via RPC,
see work/rpc_check.json + work/rpc_missing2.json) inserted at their slot in reserve-continuity order."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import replay as R
res = {x["mint"]: x for x in json.load(open(R.RESULT))}
chain = R.load_chain(); obs = R.load_obs(set(res)); L0 = R.load_launches(set(res))
rc = json.load(open(os.path.join(HERE, "work", "rpc_check.json")))
rm = json.load(open(os.path.join(HERE, "work", "rpc_missing2.json")))
found = {}
for e in rc["missing_trades"]:
    found[e["mint"]] = [dict(f, slot=f["slot"]) for f in e["found_trade_events"]]
for e in rm:
    cs = chain[e["mint"]]["trades"][0]["s"]
    found[e["mint"]] = [dict(f, slot=cs + f["slot_off"]) for f in e["found"]]
out = {}
for m, fl in found.items():
    tr = [dict(t) for t in chain[m]["trades"]]
    base_fee = (tr[0]["fee_bps"], tr[0]["cfee_bps"])
    # order inserted events by their post-trade vsol consistent with continuity: sort by (slot, vsol_after for buys asc)
    ins = []
    for f in fl:
        tok = None
        ins.append({"s": f["slot"], "i": -1, "k": 0, "sig": f["sig"], "is_buy": f["is_buy"], "sol": round(f["sol"] * 1e9),
                    "user": f["user"], "vsol": f["vsol_after"], "vtok": f["vtok_after"], "fee_bps": base_fee[0], "cfee_bps": base_fee[1],
                    "signers": [f["user"]], "err": None})
    # derive token amounts from continuity with neighbours after merge
    merged = sorted(tr + ins, key=lambda d: (d["s"], d["i"], d["k"]))
    # fix order inside the same slot for inserted ones by vsol path
    merged.sort(key=lambda d: (d["s"], d["i"] if d["i"] >= 0 else -1, d["vsol"] if d["i"] < 0 and d["is_buy"] else -d["vsol"] if d["i"] < 0 else 0))
    for j, d in enumerate(merged):
        if d["i"] < 0:
            prev = merged[j - 1]
            d["tok"] = abs(prev["vtok"] - d["vtok"])
    # continuity re-check
    breaks = R.continuity(merged, len(merged) - 1)
    info = dict(L0[m][0]); cr = chain[m]["creates"][0]; info["vsol0"], info["vtok0"] = cr["vsol0"], cr["vtok0"]
    outs = R.parse_outs(obs[m][0][1]["outs"])
    o = {"inserted": len(ins), "continuity_breaks_after_patch_first": breaks[:2]}
    for L in ("45", "60", "75"):
        rr = R.simulate(m, info, merged, outs, int(L), {"buy_slot_mode": "next"})
        o[L] = {"file_pnl": res[m]["land"][L]["pnl"], "patched_pnl": round(rr["pnl"], 6), "patched_filled": rr["filled"],
                "patched_ratio": round(rr["ratio"], 4), "delta": round(rr["pnl"] - res[m]["land"][L]["pnl"], 6)}
    out[m] = o
    print(m[:10], json.dumps(o))
tot = {L: round(sum(v[L]["delta"] for v in out.values()), 6) for L in ("45", "60", "75")}
print("total delta from raw-data gaps", tot)
json.dump({"per_mint": out, "total_delta": tot}, open(os.path.join(HERE, "work", "patch_missing.json"), "w"), indent=1)

#!/usr/bin/env python3
"""READ-ONLY: deeper search for the trades missing from raw data (Hc5sxDEh, 4RzBrX3M): page through
getSignaturesForAddress(bonding curve) between the break bounds and decode every unknown successful tx."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rpc_check as C
import replay as R
res = {x["mint"]: x for x in json.load(open(R.RESULT))}
chain = R.load_chain()
out = []
for pre in ("Hc5sxDEh", "4RzBrX3M"):
    m = next(k for k in res if k.startswith(pre))
    tr = chain[m]["trades"]; bc = chain[m]["creates"][0]["bonding_curve"]
    brk = next(j for j in range(1, len(tr)) if ((tr[j]["vsol"] - tr[j]["sol"] if tr[j]["is_buy"] else tr[j]["vsol"] + tr[j]["sol"]),
               (tr[j]["vtok"] + tr[j]["tok"] if tr[j]["is_buy"] else tr[j]["vtok"] - tr[j]["tok"])) != (tr[j-1]["vsol"], tr[j-1]["vtok"]))
    lo, hi = tr[brk - 1], tr[brk]
    known = {t["sig"] for t in tr}
    before = hi["sig"]; cands = []; pages = 0
    while pages < 6:
        r = C.rpc("getSignaturesForAddress", [bc, {"before": before, "limit": 1000, "commitment": "confirmed"}]); pages += 1
        lst = (r.get("result") or [])
        if not lst: break
        stop = False
        for e in lst:
            if e["slot"] < lo["s"]:
                stop = True; break
            if e["signature"] not in known and e.get("err") is None:
                cands.append(e)
        if stop: break
        before = lst[-1]["signature"]
    found = []
    for e in cands[:40]:
        t = C.get_tx(e["signature"])
        if "error" in t or not t.get("result"):
            continue
        evs, nlog, ncpi = C.trade_events_from_tx(t["result"], m)
        for ev in evs:
            found.append({"sig": e["signature"], "slot_off": e["slot"] - tr[0]["s"], "is_buy": ev["is_buy"], "sol": ev["sol"] / 1e9,
                          "user": ev["user"], "vsol_after": ev["vsol"], "vtok_after": ev["vtok"]})
    out.append({"mint": m, "break_slots_off": [lo["s"] - tr[0]["s"], hi["s"] - tr[0]["s"]], "unknown_successful_candidates": len(cands),
                "decoded_candidates": min(40, len(cands)), "found": found})
    print(pre, "candidates", len(cands), "found", json.dumps(found)[:800], flush=True)
json.dump(out, open(os.path.join(HERE, "work", "rpc_missing2.json"), "w"), indent=1)
print("calls", C.NCALLS[0])

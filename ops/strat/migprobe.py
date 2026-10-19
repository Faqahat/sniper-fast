import sys, json
sys.path.insert(0, "/root/strat")
from srpc import rpc
from pev import events
MIG = "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg"
AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
r = rpc("getSignaturesForAddress", [MIG, {"limit": 1000}])
print("n", len(r), r[0]["slot"], r[-1]["slot"], r[0].get("blockTime") - r[-1].get("blockTime"), "s span", sum(1 for x in r if x.get("err")), "errs")
for x in r[:3]:
    t = rpc("getTransaction", [x["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    m = t["transaction"]["message"]; keys = m["accountKeys"] + (t["meta"].get("loadedAddresses") or {}).get("writable", []) + (t["meta"].get("loadedAddresses") or {}).get("readonly", [])
    logs = t["meta"]["logMessages"]
    print("---", x["signature"][:12], x["slot"], "AMM in keys", AMM in keys, "nlogs", len(logs))
    for l in logs[:40]:
        if "Instruction" in l or "invoke" in l: print("   ", l[:120])
    tr, cr = events(logs)
    print("   trade events", [(e["mint"][:8], e["buy"], e["sol"], e["vsol"], e["rsol"]) for e in tr][:3])
    for b in t["meta"].get("postTokenBalances", [])[:8]:
        print("   ptb", b.get("mint")[:8], b.get("owner", "")[:8], b["uiTokenAmount"]["amount"])

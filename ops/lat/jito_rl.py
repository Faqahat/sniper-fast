#!/usr/bin/env python3
"""Zero-cost: does Jito's JSON-RPC rate limit count keep-alive calls (getTipAccounts/getHealth) in the same bucket as
sendBundle/sendTransaction? Only junk (undecodable) transactions are submitted: they cannot land, nothing is paid.
No UUID / auth is used (the default per-IP limit)."""
import json, time, http.client, ssl
H = "frankfurt.mainnet.block-engine.jito.wtf"
ctx = ssl.create_default_context(); ctx.set_alpn_protocols(["http/1.1"])
c = http.client.HTTPSConnection(H, 443, timeout=5, context=ctx)
def call(path, method, params):
    t = time.perf_counter()
    c.request("POST", path, body=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}), headers={"content-type": "application/json"})
    r = c.getresponse(); b = r.read()
    return r.status, round((time.perf_counter() - t) * 1e3, 2), b[:110].decode("utf-8", "replace")
JUNK = "AQID"   # base64 of 3 bytes: not a transaction
def show(tag, x): print(f"{tag:42} status={x[0]} ms={x[1]} {x[2]!r}", flush=True)
show("warm getTipAccounts", call("/api/v1/getTipAccounts", "getTipAccounts", []))
time.sleep(2.5)
print("--- A: junk sendBundle alone (after 2.5 s idle)")
show("sendBundle junk", call("/api/v1/bundles", "sendBundle", [[JUNK], {"encoding": "base64"}]))
time.sleep(2.5)
print("--- B: getTipAccounts then junk sendBundle 50 ms later")
show("getTipAccounts", call("/api/v1/getTipAccounts", "getTipAccounts", []))
time.sleep(0.05)
show("sendBundle junk", call("/api/v1/bundles", "sendBundle", [[JUNK], {"encoding": "base64"}]))
time.sleep(2.5)
print("--- C: junk sendTransaction then junk sendBundle 50 ms later")
show("sendTransaction junk", call("/api/v1/transactions", "sendTransaction", [JUNK, {"encoding": "base64"}]))
time.sleep(0.05)
show("sendBundle junk", call("/api/v1/bundles", "sendBundle", [[JUNK], {"encoding": "base64"}]))
time.sleep(2.5)
print("--- D: getHealth on /api/v1/transactions (the engine's jito-tx keep-alive) then junk sendTransaction")
show("getHealth", call("/api/v1/transactions", "getHealth", []))
time.sleep(0.05)
show("sendTransaction junk", call("/api/v1/transactions", "sendTransaction", [JUNK, {"encoding": "base64"}]))
time.sleep(2.5)
print("--- E: 4 junk sendTransaction in 200 ms")
for i in range(4):
    show(f"sendTransaction junk #{i}", call("/api/v1/transactions", "sendTransaction", [JUNK, {"encoding": "base64"}])); time.sleep(0.05)

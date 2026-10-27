#!/usr/bin/env python3
"""Fetch a few REAL pump.fun transactions (legacy + v0) as wire bytes via getTransaction(base64) and record the RPC's own
JSON decode (static keys, lookups, instructions) as the expected values for the Rust parser test. The RPC URL is read from
~/.config/sniper/ck_rpc_url and never printed. Output: tests/fixtures/real_txs.json (public chain data only)."""
import base64, glob, gzip, json, os, sys, urllib.request

url = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(method, params):
    req = urllib.request.Request(url, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read()).get("result")
    except Exception as e:
        print("rpc error:", type(e).__name__); return None

runs = sorted(glob.glob("/home/moiz/sniper-data/collect/run_*/txs/*.jsonl.gz"))
cands = []
with gzip.open(runs[-2], "rt") as f:
    for line in f:
        d = json.loads(line)
        if d.get("err") is None and "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P" in d.get("progs", []):
            cands.append(d["sig"])
        if len(cands) >= 400: break
want = {"legacy": 3, 0: 3}; out = []
for sig in cands[::7]:
    if all(v <= 0 for v in want.values()): break
    b = rpc("getTransaction", [sig, {"encoding": "base64", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
    if not b: continue
    ver = b.get("version")
    if want.get(ver, 0) <= 0: continue
    j = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
    if not j: continue
    msg = j["transaction"]["message"]
    out.append({"sig": sig, "version": -1 if ver == "legacy" else 0, "b64": b["transaction"][0],
                "static_keys": msg["accountKeys"], "n_lookups": len(msg.get("addressTableLookups") or []),
                "instructions": [{"program": msg["accountKeys"][ix["programIdIndex"]], "accounts": ix["accounts"], "data_b58": ix["data"]}
                                 for ix in msg["instructions"]],
                "header": [msg["header"]["numRequiredSignatures"], msg["header"]["numReadonlySignedAccounts"], msg["header"]["numReadonlyUnsignedAccounts"]],
                "slot": j["slot"]})
    want[ver] -= 1
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "real_txs.json"), "w"), indent=0)
print("fixtures:", [(o["version"], o["n_lookups"], len(o["instructions"])) for o in out])

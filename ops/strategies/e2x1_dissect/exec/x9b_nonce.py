#!/usr/bin/env python3
"""Q5: who created the nonce accounts (public RPC). For 3 E2x1 nonce accounts + the 2 Grozoe nonce accounts: oldest signature ->
getTransaction -> createAccount 'source' (funder) and nonce authority. Out: nonce_origin.json"""
import sys, json, time
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/recon")
import rpc
rpc.MIN_GAP = 2.0
O = "/home/moiz/sniper-data/e2x1_dissect/exec"
ACC = {"E2x1": ["BFt8cy5qb8RvdukY7q8GyRmXUH5qNfrViza9zF5xLdxX", "4gnz1exRSWFd2U9pmndq1TLkRUG4hELtyURsKVarZcbe", "HUAorniMLfX9WRVqc8AV22hC1shruUCu9Sw4ZeGPYbg1"],
       "Grozoe": ["4KBJQ6yDQPHTWGLVEp8aikUyJA2xCiJKVFBRu4kk5YSP", "8yzgfZptfHPffRh4jKyYapUdBHmAfmWTM7n3ABFNgytk"]}
out = {}
for who, accs in ACC.items():
    for a in accs:
        before = None; last = None; n = 0
        for page in range(40):
            p = {"limit": 1000}
            if before: p["before"] = before
            r = rpc.call("getSignaturesForAddress", [a, p]).get("result") or []
            n += len(r)
            if not r: break
            last = r[-1]; before = last["signature"]
            if len(r) < 1000: break
        d = dict(who=who, nsigs=n, oldest=last)
        if last:
            tx = rpc.call("getTransaction", [last["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]).get("result")
            if tx:
                ixs = tx["transaction"]["message"]["instructions"]
                d["ixs"] = [(i.get("program"), (i.get("parsed") or {}).get("type"), (i.get("parsed") or {}).get("info")) for i in ixs]
                d["payer"] = tx["transaction"]["message"]["accountKeys"][0]["pubkey"]; d["bt"] = tx.get("blockTime")
        out[a] = d; print(who, a, json.dumps(d)[:700], flush=True)
        json.dump(out, open(f"{O}/nonce_origin.json", "w"))

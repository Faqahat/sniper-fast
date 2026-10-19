#!/usr/bin/env python3
# READ-ONLY: router v3 create: is account [2] the quote mint (WSOL for SOL curves)? + holder byte check.
import sys, json, collections as C
sys.path.insert(0, "/root/det")
from dlib import *
ROUTER = "6Vo3245eszAb5wuqEMw8mGdbfRUdKbHhDHP5LcaGuTAB"
R = [json.loads(l) for l in open(sys.argv[1])]
cnt = C.Counter()
for r in [r for r in R if r.get("top") is False and not r.get("err")]:
    t = rpc("getTransaction", [r["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    for ix in msg["instructions"]:
        if keys[ix["programIdIndex"]] != ROUTER:
            continue
        d = b58dec(ix["data"])
        if d[:8].hex() != "7aba70893251ee63":
            continue
        q = (r.get("ev") or {}).get("quote_mint")
        a2 = keys[ix["accounts"][2]] if ix["accounts"][2] < len(msg["accountKeys"]) else "ALT"
        cnt[("acct2", "WSOL" if a2 == WSOL else a2[:6], "quote", "SOL" if q == "11111111111111111111111111111111" else (q or "")[:6], "acct2==quote", a2 == q)] += 1
for k, v in cnt.items():
    print(k, v)

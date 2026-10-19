#!/usr/bin/env python3
# READ-ONLY: decode pump router (6Vo3245e...) create ix layout against truth (dev SOL, tokens, quote).
import sys, json
sys.path.insert(0, "/root/det")
from dlib import *
R = [json.loads(l) for l in open(sys.argv[1])]
cpi = [r for r in R if r.get("top") is False and not r.get("err")][:10]
for r in cpi:
    t = rpc("getTransaction", [r["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    for ix in msg["instructions"]:
        if not keys[ix["programIdIndex"]].startswith("6Vo3245e"):
            continue
        d = b58dec(ix["data"])
        p = 8; strs = []
        try:
            for _ in range(3):
                n = int.from_bytes(d[p:p + 4], "little"); strs.append(d[p + 4:p + 4 + n][:20]); p += 4 + n
        except Exception:
            pass
        rest = d[p:]
        u64s = [int.from_bytes(rest[i:i + 8], "little") for i in range(0, len(rest) - 7, 1)]
        acc = [keys[i] for i in ix["accounts"]]
        print(r["mint"][:8], "disc", d[:8].hex(), "strs", strs, "rest_len", len(rest), "true_dev", r["true_dev"], "tok", r["true_dev_tok"],
              "quote", (r.get("ev") or {}).get("quote_mint", "")[:6], "bc_in_acc", (r.get("ev") or {}).get("bonding_curve") in acc,
              "mint_idx", acc.index(r["mint"]) if r["mint"] in acc else None)
        print("    rest hex", rest.hex())

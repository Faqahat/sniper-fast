#!/usr/bin/env python3
# READ-ONLY: raw trailing create_v2 arg bytes vs CreateEvent flags, by trailing length; CPI-router dev amount search.
import sys, json, collections as C
sys.path.insert(0, "/root/det")
from dlib import *
R = [json.loads(l) for l in open(sys.argv[1])]
ev = [r for r in R if r.get("ev") and r.get("kind") == "create_v2" and not r.get("err") and r.get("top")]
seen = C.Counter()
for r in ev:
    tl = r["args"]["trailing"]
    e = r["ev"]
    flag = (e.get("mayhem"), e.get("cashback"), e.get("fee_bps"), e.get("holder"))
    key = (tl, flag)
    if seen[key] >= 1 or tl in (11,) and seen[(tl, None)] > 6:
        continue
    seen[key] += 1; seen[(tl, None)] += 1
    t = rpc("getTransaction", [r["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    for ix in msg["instructions"]:
        if keys[ix["programIdIndex"]] == PUMP:
            d = b58dec(ix["data"])
            if d[:8] == CREATE_V2:
                print(f"trailing={tl:2} raw={d[len(d)-tl:].hex():24} ev(mayhem,cashback,fee,holder)={flag} quote={e.get('quote_mint','')[:6]}")
cpi = [r for r in R if r.get("top") is False and not r.get("err") and r.get("true_dev")]
for r in cpi[:8]:
    t = rpc("getTransaction", [r["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    for ix in msg["instructions"]:
        if keys[ix["programIdIndex"]].startswith("6Vo3245e"):
            d = b58dec(ix["data"])
            hits = []
            for o in range(8, len(d) - 7):
                v = int.from_bytes(d[o:o + 8], "little")
                if v and abs(v - r["true_dev"]) / r["true_dev"] < 0.03:
                    hits.append((o, len(d) - o, v))
            tok = r.get("true_dev_tok") or 0
            thits = [(o, len(d) - o) for o in range(8, len(d) - 7) if tok and int.from_bytes(d[o:o + 8], "little") == tok]
            print(f"CPI {r['mint'][:8]} disc={d[:8].hex()} len={len(d)} true_dev={r['true_dev']} tok={tok} sol_hits(off,from_end,v)={hits[:3]} tok_hits={thits[:3]} tail={d[-24:].hex()}")

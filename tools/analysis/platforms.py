#!/usr/bin/env python3
"""Long run: whose trades do the winners backrun? For up to N wins per top bot (wins.jsonl.gz) fetch the TRIGGER
transaction (RPC, run on Cherry) and fingerprint where it came from: its top-level router program (Jupiter, a
trading terminal's program, the venue itself) and the accounts it paid SOL to (platform fee wallets, sender tips).
A bot whose triggers concentrate on one platform far beyond the field's mix likely sees that platform's flow before
it executes. Input: runs/trigs.json {bot: [trigger sigs]}; output: runs/platforms.json. usage: platforms.py"""
import json, urllib.request, collections, time, os, concurrent.futures as cf

os.chdir("/root/arb-lab")
env = dict(l.strip().split("=", 1) for l in open(".env") if "=" in l and not l.startswith("#"))
U = env["RMR_RPC_URL"]
NEUTRAL = ("ComputeBudget111111111111111111111111111111", "11111111111111111111111111111111", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
           "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")

def tx(s):
    for i in range(3):
        try:
            r = urllib.request.Request(U, json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [s, {"encoding": "json", "maxSupportedTransactionVersion": 1}]}).encode(), {"content-type": "application/json"})
            return json.load(urllib.request.urlopen(r, timeout=30)).get("result")
        except Exception: time.sleep(1 + i)

def fp(s):
    t = tx(s)
    if not t: return None
    m = t["transaction"]["message"]
    keys = m["accountKeys"] + t["meta"].get("loadedAddresses", {}).get("writable", []) + t["meta"].get("loadedAddresses", {}).get("readonly", [])
    top = sorted({keys[ix["programIdIndex"]] for ix in m["instructions"]} - set(NEUTRAL))
    pre, post = t["meta"]["preBalances"], t["meta"]["postBalances"]
    paid = [keys[i] for i in range(1, len(pre)) if 0 < post[i] - pre[i] < 5e8 and i < len(m["accountKeys"])]
    return {"signer": keys[0], "router": top, "paid": paid, "ok": t["meta"]["err"] is None}

trigs = json.load(open("runs/trigs.json"))
out = {}
with cf.ThreadPoolExecutor(6) as ex:
    for bot, sigs in trigs.items():
        rows = [r for r in ex.map(fp, sigs) if r]
        routers = collections.Counter(r["router"][0] if r["router"] else "(venue only)" for r in rows)
        paid = collections.Counter(p for r in rows for p in set(r["paid"]))
        out[bot] = {"n": len(rows), "routers": routers.most_common(10), "paid_to": paid.most_common(12), "distinct_signers": len({r["signer"] for r in rows})}
        print(bot[:8], len(rows), "routers", routers.most_common(4), "paid", [(k[:8], v) for k, v in paid.most_common(5)], flush=True)
json.dump(out, open("runs/platforms.json", "w"), indent=1)

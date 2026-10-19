import sys, json, hashlib
sys.path.insert(0, "/root/strat"); sys.path.insert(0, "/root/indep")
from srpc import rpc
from common import b58dec
AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
TAG = bytes.fromhex("e445a52e51cb9a1d")
BUY = hashlib.sha256(b"event:BuyEvent").digest()[:8]; SELL = hashlib.sha256(b"event:SellEvent").digest()[:8]
n = 0
for l in open("/root/strat/grad.jsonl"):
    x = json.loads(l)
    for p in x.get("pts") or []:
        if not p[1]: continue
        t = rpc("getTransaction", [p[1][0], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
        if not isinstance(t, dict): continue
        keys = t["transaction"]["message"]["accountKeys"] + (t["meta"].get("loadedAddresses") or {}).get("writable", []) + (t["meta"].get("loadedAddresses") or {}).get("readonly", [])
        for inn in t["meta"].get("innerInstructions") or []:
            for ix in inn["instructions"]:
                if keys[ix["programIdIndex"]] != AMM: continue
                raw = b58dec(ix["data"])
                if raw[:8] != TAG: continue
                d = raw[8:16]; body = raw[16:]
                u = [int.from_bytes(body[8 * i:8 * i + 8], "little") for i in range(14)]
                off = 14 * 8 + 6 * 32 + 32
                cc = [int.from_bytes(body[off + 8 * i: off + 8 * i + 8], "little") for i in range(2)]
                kind = "BUY" if d == BUY else ("SELL" if d == SELL else d.hex())
                print(kind, "pool_base", u[5], "pool_quote", u[6], "lp_bps", u[8], "proto_bps", u[10], "creator_bps", cc[0], "sol0", x["sol0"])
                n += 1
        if n >= 8: break
    if n >= 8: break

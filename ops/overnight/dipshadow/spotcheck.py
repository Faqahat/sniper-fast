#!/usr/bin/env python3
# Spot-check of forward picks against the chain (READ-ONLY RPC): the trigger sell (size, seller, direct or routed) and the
# trades in the 2 slots after it, from our data; then the trigger tx fetched from the chain to confirm it.
import os, sys, json, base64, time, urllib.request
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
import dipbuy4 as D
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58enc(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def rpc(m, p):
    for i in range(5):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=30))
            if "result" in r and r["result"]: return r["result"]
        except Exception: pass
        time.sleep(1)
PICKS = [("HdH5VFXbjQiuzpMeMkwxaW3k6ZX6cGafiuRxgmBsMASa", 9.54, "2YDnmMQt"), ("9SG2qekYbDFUNLjZsADFc1cWr6j15f4qWz78fqZ7pump", 3.82, "7mheYx9E"),
         ("9DS6BMGa19hmLcBvdNm9tK7u8zqe7w5b84UGqQbkpump", 12.3, "2i8Qwski"), ("bWVX1QQt4sBoQgdjmF8GD2ekDeGgGXb8QvYXnRbpump", 3.18, "4HXb7ivg")]
out = []
for m, age, seller in PICKS:
    tr = D.rp.read_bucket(D.L[m]["run"], D.rp.bucket(m), {m}).get(m, [])
    S0 = D.L[m]["slot"]
    k = next((k for k, t in enumerate(tr) if not t["buy"] and t["user"].startswith(seller) and round((t["s"] - S0) * D.SMS / 1000, 2) == age), None)
    if k is None: print("not found", m, age); continue
    t = tr[k]; nxt = [x for x in tr[k + 1:k + 40] if x["s"] <= t["s"] + 2]
    tx = rpc("getTransaction", [t["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    chain = None
    if tx:
        msg = tx["transaction"]["message"]; la = tx["meta"].get("loadedAddresses") or {}; keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
        top = any(keys[ix["programIdIndex"]] == PUMP and m in [keys[a] for a in ix["accounts"]] for ix in msg["instructions"])
        ev = None
        for l in tx["meta"].get("logMessages") or []:
            if l.startswith("Program data: "):
                x = l[14:].split()[0]; x += "=" * (-len(x) % 4)
                try: raw = base64.b64decode(x)
                except Exception: continue
                if raw[:8] == TD and b58enc(raw[8:40]) == m and raw[56] == 0: ev = (int.from_bytes(raw[40:48], "little") / 1e9, b58enc(raw[57:89]))
        chain = dict(ok=tx["meta"]["err"] is None, direct=top, sell_sol=ev[0] if ev else None, seller=ev[1][:8] if ev else None, slot=tx["slot"])
    row = dict(m=m, age=age, sig=t["sig"], sol=round(t["sol"] / 1e9, 3), seller=t["user"][:8], slot=t["s"], chain=chain,
               after=[(x["user"][:8], "buy" if x["buy"] else "sell", round(x["sol"] / 1e9, 3), x["s"] - t["s"]) for x in nxt[:12]],
               buys_after=round(sum(x["sol"] for x in nxt if x["buy"]) / 1e9, 2), sells_after=round(sum(x["sol"] for x in nxt if not x["buy"]) / 1e9, 2))
    out.append(row)
    print(json.dumps(row)[:700])
json.dump(out, open("spotcheck.json", "w"), indent=1)

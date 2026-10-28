#!/usr/bin/env python3
"""LIM step 1b (read-only, PUBLIC RPC only, <= ~3 req/s, resumable): getTransaction for the sampled haqq buy txs; keep
only the decoded instruction data of his router (haqqqMGN...) and of the pump.fun buy CPI, plus pump error log lines.
Out: data/lim/rpc_args.jsonl"""
import json, os, sys, time, urllib.request
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
EP = "https://api.mainnet-beta.solana.com"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; ROUTER = "haqqqMGN35ehCftXca3KWxJFXTBcWTWeNHNtUHLGQdh"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for ch in s: n = n * 58 + B58.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw
def rpc(sig):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}]}).encode()
    for k in range(6):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=body, headers={"content-type": "application/json"}), timeout=25))
            if r.get("result"): return r["result"]
            if "error" in r: time.sleep(2 + 3 * k); continue
            return None
        except Exception as e:
            time.sleep(2 + 3 * k)
    return None
todo = json.load(open(f"{OUT}/rpc_todo.json"))
done = set()
fn = f"{OUT}/rpc_args.jsonl"
if os.path.exists(fn):
    for l in open(fn): done.add(json.loads(l)["sig"])
f = open(fn, "a"); n = 0; t0 = time.time()
for x in todo:
    if x["sig"] in done: continue
    ts = time.time()
    t = rpc(x["sig"])
    rec = dict(x)
    if not t: rec["fetch"] = False
    else:
        msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
        keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
        rec["outer"] = [b58d(ix["data"]).hex() for ix in msg["instructions"] if keys[ix["programIdIndex"]] == ROUTER]
        rec["pump"] = [b58d(ix["data"]).hex()[:120] for inn in (t["meta"].get("innerInstructions") or []) for ix in inn["instructions"]
                       if keys[ix["programIdIndex"]] == PUMP and not b58d(ix["data"]).hex().startswith("e445a52e")]
        rec["logs"] = [l for l in (t["meta"].get("logMessages") or []) if ("Error" in l or "Left" in l or "Right" in l or "slippage" in l.lower())][:8]
        rec["err"] = t["meta"].get("err")
    f.write(json.dumps(rec) + "\n"); n += 1
    if n % 100 == 0: f.flush(); print(n, f"{time.time() - t0:.0f}s", flush=True)
    dt = time.time() - ts
    if dt < 0.36: time.sleep(0.36 - dt)
f.close(); print("done", n, f"{time.time() - t0:.0f}s")

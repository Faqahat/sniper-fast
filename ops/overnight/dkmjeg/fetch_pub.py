#!/usr/bin/env python3
# READ-ONLY helper fetcher on the PUBLIC mainnet-beta RPC (separate from the owner's CK RPC), oldest signatures first,
# paced ~2.5 req/s, writing into the same resumable cache (txc/). Runs alongside fetch.py (which goes newest first).
import os, sys, json, time, threading, urllib.request, concurrent.futures as cf
HERE = os.path.dirname(os.path.abspath(__file__)); C = os.path.join(HERE, "txc")
PUB = "https://api.mainnet-beta.solana.com"
sigs = json.load(open(os.path.join(HERE, "sigs.json")))
todo = [s["signature"] for s in reversed(sigs) if s["slot"] >= 459_300_000]
lock = threading.Lock(); nxt = [0.0]; done = [0]; RPS = float(os.environ.get("PUB_RPS", "2.5"))
def one(sig):
    p = os.path.join(C, sig + ".json")
    if os.path.exists(p): return
    for i in range(6):
        with lock:
            w = nxt[0] - time.time(); nxt[0] = max(time.time(), nxt[0]) + 1 / RPS
        if w > 0: time.sleep(w)
        if os.path.exists(p): return
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(PUB, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}]}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if r.get("result"):
                tmp = p + ".tmp"; json.dump(r["result"], open(tmp, "w")); os.replace(tmp, p); break
        except Exception: time.sleep(2 + 2 * i)
    with lock:
        done[0] += 1
        if done[0] % 250 == 0: print(f"pub {done[0]}", flush=True)
with cf.ThreadPoolExecutor(3) as ex: list(ex.map(one, todo))
print("pub done", flush=True)

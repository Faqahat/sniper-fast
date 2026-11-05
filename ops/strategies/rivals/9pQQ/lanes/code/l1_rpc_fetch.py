#!/usr/bin/env python3
"""LANES step 1: fetch full txs (instruction data) of a stratified random sample of 9pQQ txs via PUBLIC RPC, <=2 req/s.
usage: l1_rpc_fetch.py SIGLIST OUT.jsonl   (SIGLIST lines: run sig kind s i). Resumable (skips sigs already in OUT)."""
import sys, json, time, urllib.request, os
URL = "https://api.mainnet-beta.solana.com"
src, out = sys.argv[1], sys.argv[2]
done = set()
if os.path.exists(out):
    for l in open(out):
        try: done.add(json.loads(l)["sig"])
        except Exception: pass
todo = [l.split() for l in open(src) if l.strip()]
todo = [t for t in todo if t[1] not in done]
fo = open(out, "a"); last = 0; n = 0
for t in todo:
    run, sig, kind, s, i = t[:5]
    for att in range(6):
        dt = time.time() - last
        if dt < 0.55: time.sleep(0.55 - dt)
        last = time.time()
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}]}).encode()
        try:
            req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=30))
            if "result" in r and r["result"] is not None:
                res = r["result"]; res.get("meta", {}).pop("logMessages", None)
                fo.write(json.dumps(dict(run=run, sig=sig, kind=kind, s=int(s), i=int(i), tx=res)) + "\n"); fo.flush(); n += 1
                break
            time.sleep(2 + 3 * att)
        except Exception as e:
            time.sleep(3 + 5 * att)
    if n % 200 == 0: print(n, len(todo), flush=True)
print("done", n, flush=True)

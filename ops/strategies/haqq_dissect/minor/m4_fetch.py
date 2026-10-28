#!/usr/bin/env python3
"""MINOR step 4 (read-only, PUBLIC RPC, 1 call / 1.6 s, resumable): getTransaction for a small sample of minor-bot buy txs
(filled and failed, recent days first) to decode his router's trade_v3 arguments (amount_in, min_out, expected_out).
Out: minor/rpc/<sig>.json"""
import json, os, pickle, random, time, urllib.request
OUT = "/home/moiz/sniper-data/haqq_dissect/minor/rpc"
os.makedirs(OUT, exist_ok=True)
URL = "https://api.mainnet-beta.solana.com"
random.seed(3)
X = pickle.load(open("/home/moiz/sniper-data/haqq_dissect/exec/txs.pkl", "rb"))
H = [r for r in X if r["w"] == "haqq" and r["kind"] == "buy"]
want = {(226, True): 8, (226, False): 8, (231, True): 6, (231, False): 6, (234, True): 6, (234, False): 6, (244, True): 4,
        (249, True): 3, (251, True): 3, (252, True): 3}
pick = []
for (c, ok), n in want.items():
    pool = [r for r in H if (r["cup"] or 0) % 1000 == c and r["ok"] == ok]
    pool.sort(key=lambda r: -r["bt"]); pool = pool[:200]; random.shuffle(pool)
    if c == 244: pool = [r for r in pool if r["sol"] and r["sol"] < 2e7] or pool
    pick += [(c, r) for r in pool[:n]]
print(len(pick), "to fetch", flush=True)
for c, r in pick:
    o = f"{OUT}/{r['sig']}.json"
    if os.path.exists(o): continue
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [r["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}]}).encode()
    for t in range(3):
        try:
            j = json.load(urllib.request.urlopen(urllib.request.Request(URL, data=data, headers={"content-type": "application/json"}), timeout=30))
            if j.get("result"):
                j["_rec"] = dict(code=c, ok=r["ok"], s=r["s"], i=r["i"], mint=r["mint"], bt=r["bt"]); json.dump(j, open(o, "w")); break
            print("noresult", r["sig"][:10], str(j)[:100], flush=True)
        except Exception as e: print("err", e, flush=True)
        time.sleep(4)
    time.sleep(1.6)
print("done", len(os.listdir(OUT)))

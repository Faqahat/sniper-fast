#!/usr/bin/env python3
# READ-ONLY: fetch DGmspi's OLD (pre-CK-window) SOL-quoted BUY txs from the public RPC, slowly (1 request / 2.5 s, backoff on 429),
# to get the token creator (TradeEvent.creator) and the exact curve state. Caches into cache/txc_DGmspi/.
import sys, os, json, time, urllib.request, urllib.error
EX = os.path.dirname(os.path.abspath(__file__)); L = "/home/moiz/sniper/ops/snipers/ledger"; OUT = os.path.join(EX, "cache", "txc_DGmspi")
PUB = "https://api.mainnet-beta.solana.com"
D = json.load(open(f"{L}/ledger_DGmspi.json"))
have = set(os.listdir(f"{L}/txc_DGmspi")) | set(os.listdir(OUT))
need = [x for x in D["txs"] if not x.get("missing") and not x.get("err") and any(t["buy"] and t["sol"] > 0 for t in x["trades"]) and x["sig"] + ".json" not in have]
print("to fetch", len(need), flush=True)
n = 0; gap = 2.5
for x in need:
    for i in range(8):
        try:
            req = urllib.request.Request(PUB, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [x["sig"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}]}).encode(), headers={"content-type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=60))
            if r.get("result"):
                json.dump(r["result"], open(os.path.join(OUT, x["sig"] + ".json"), "w")); n += 1; break
            if "error" in r: time.sleep(gap * (i + 2)); continue
            break
        except urllib.error.HTTPError as e:
            time.sleep(10 * (i + 1) if e.code == 429 else gap * (i + 1))
        except Exception:
            time.sleep(gap * (i + 1))
    time.sleep(gap)
    if n % 20 == 0: print("fetched", n, flush=True)
print("DONE fetched", n, "of", len(need), flush=True)

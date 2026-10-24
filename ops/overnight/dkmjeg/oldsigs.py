#!/usr/bin/env python3
# READ-ONLY: the wallet's signature history OLDER than the CK window, from public mainnet-beta (paced ~0.7 page/s),
# then its first 40 transactions (funding). -> sigs_old.json, txc_old/<sig>.json
import os, sys, json, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); PUB = "https://api.mainnet-beta.solana.com"
W = "dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK"
def post(m, p):
    for i in range(8):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(PUB, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(2 + 3 * i)
    return None
OF = os.path.join(HERE, "sigs_old.json")
old = json.load(open(OF)) if os.path.exists(OF) else []
before = old[-1]["signature"] if old else json.load(open(os.path.join(HERE, "sigs.json")))[-1]["signature"]
while True:
    r = post("getSignaturesForAddress", [W, {"limit": 1000, "before": before}])
    if not r: break
    old += r; before = r[-1]["signature"]
    json.dump(old, open(OF, "w"))
    print(f"old sigs {len(old)} oldest slot {r[-1]['slot']} bt {r[-1].get('blockTime')}", flush=True)
    if len(r) < 1000: break
    time.sleep(1.4)
os.makedirs(os.path.join(HERE, "txc_old"), exist_ok=True)
for s in old[-40:]:
    p = os.path.join(HERE, "txc_old", s["signature"] + ".json")
    if os.path.exists(p): continue
    t = post("getTransaction", [s["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
    if t: json.dump(t, open(p, "w"))
    time.sleep(0.5)
print("done", len(old), flush=True)

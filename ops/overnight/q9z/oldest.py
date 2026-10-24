#!/usr/bin/env python3
# READ-ONLY: page 9qz7cW's signature history back past the owner's RPC horizon on PUBLIC mainnet-beta (slow, 1 call / 2 s,
# backs off on 429) to find its first transactions (creation / first funding). -> oldest_sigs.json (count + oldest 1000)
import sys, os, json, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); PUB = "https://api.mainnet-beta.solana.com"
W = sys.argv[1] if len(sys.argv) > 1 else "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"; MAXP = int(sys.argv[2]) if len(sys.argv) > 2 else 400
S = json.load(open(os.path.join(HERE, "sigs.json"))); before = S[-1]["signature"]; n = 0; last = []; pages = 0
while pages < MAXP:
    for i in range(8):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(PUB, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [W, {"before": before, "limit": 1000}]}).encode(), headers={"content-type": "application/json"}), timeout=60)).get("result")
            break
        except Exception as e:
            time.sleep(5 + 10 * i); r = None
    if r is None: print("gave up at page", pages, flush=True); break
    pages += 1; n += len(r)
    if r: last = r; before = r[-1]["signature"]
    if pages % 20 == 0: print(pages, n, r[-1]["slot"] if r else None, r[-1].get("blockTime") if r else None, flush=True)
    json.dump(dict(pages=pages, n_older=n, oldest=last[-50:], done=len(r) < 1000), open(os.path.join(HERE, "oldest_sigs.json"), "w"))
    if len(r) < 1000: print("reached the first tx", n, r[-1]["slot"] if r else None, r[-1].get("blockTime") if r else None, flush=True); break
    time.sleep(2)

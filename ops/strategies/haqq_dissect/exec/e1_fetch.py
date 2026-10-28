#!/usr/bin/env python3
"""Read-only: fetch a small stratified sample of haqq txs with getTransaction from the PUBLIC RPC (1 call / 1.6 s).
Saves raw responses to sniper-data/haqq_dissect/exec/rpc/<sig>.json. Usage: e1_fetch.py N_PER_CLASS"""
import json, random, collections, time, urllib.request, os, sys
random.seed(7)
D = "/home/moiz/sniper-data/haqq_dissect/exec/rpc"; H = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
URL = "https://api.mainnet-beta.solana.com"
rows = [json.loads(l) for l in open("/home/moiz/sniper-data/haqq_strat/haqq_raw.jsonl")]
rows = [r for r in rows if r["signers"][0] == H]
def path(r):
    if not r["tips"]: return "notip"
    k = r["tips"][0][0]; return TIP.get(k, "noz" if k.startswith("noz") else k[:6])
def kind(r):
    ix = [x for x in r["ixn"] if x.startswith(("Buy", "Sell"))]
    return ix[0] if ix else "none"
cls = collections.defaultdict(list)
for r in rows: cls[(kind(r), r["err"] is None, path(r))].append(r)
want = [("BuyExactQuoteInV3", True, p, 2) for p in ("helius", "notip", "0slot", "nozomi", "astralane", "jito", "falcon", "bloxroute", "temporal")] + \
       [("BuyExactQuoteInV3", False, "notip", 10), ("SellV3", True, "helius", 3), ("SellV3", True, "notip", 2), ("SellV3", True, "0slot", 1),
        ("SellV3", False, "notip", 1), ("none", True, None, 3), ("SellV2", True, None, 1)]
pick = []
for k, ok, p, n in want:
    pool = [r for (kk, oo, pp), v in cls.items() if kk == k and oo == ok and (p is None or pp == p) for r in v]
    random.shuffle(pool); pick += pool[:n]
print(len(pick), "to fetch")
for r in pick:
    o = f"{D}/{r['sig']}.json"
    if os.path.exists(o): continue
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [r["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}]}).encode()
    for t in range(3):
        try:
            j = json.load(urllib.request.urlopen(urllib.request.Request(URL, data=data, headers={"content-type": "application/json"}), timeout=30))
            if j.get("result"):
                j["_rec"] = dict(kind=kind(r), ok=r["err"] is None, path=path(r), s=r["s"], i=r["i"]); json.dump(j, open(o, "w")); break
            print("noresult", r["sig"][:10], str(j)[:120])
        except Exception as e: print("err", e)
        time.sleep(4)
    time.sleep(3)
print("done", len(os.listdir(D)))

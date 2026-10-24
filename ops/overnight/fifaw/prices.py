#!/usr/bin/env python3
# READ-ONLY: current USD prices (Jupiter lite price API v3) for every mint the wallet holds now or moved in the window
import json, urllib.request, time
H = json.load(open("holdings_now.json")); L = json.load(open("ledger_FiFawH.json"))
W = "FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W"
mints = {a["mint"] for a in H["accounts"]} | {m for x in L if x["signer"] == W for m in x["tok"]}
mints = sorted(mints); out = {}
for i in range(0, len(mints), 50):
    ids = ",".join(mints[i:i + 50])
    for k in range(4):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request("https://lite-api.jup.ag/price/v3?ids=" + ids, headers={"user-agent": "study"}), timeout=30)); break
        except Exception as e: time.sleep(2 + 2 * k); r = {}
    for m, v in r.items():
        if v and v.get("usdPrice") is not None: out[m] = dict(usd=v["usdPrice"], liq=v.get("liquidity"), dec=v.get("decimals"))
    time.sleep(0.6)
json.dump(out, open("prices_now.json", "w"), indent=0)
print("mints", len(mints), "priced", len(out))

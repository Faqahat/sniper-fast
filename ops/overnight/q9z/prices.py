#!/usr/bin/env python3
# READ-ONLY: current USD prices (Jupiter public price API v3) of SOL and every non-SOL quote / stable mint 9qz7cW holds or
# trades, to value quote-token legs and inventories in SOL. -> prices.json {mint: usd}
import os, json, gzip, glob, urllib.request, time
HERE = os.path.dirname(os.path.abspath(__file__))
H = json.load(open(os.path.join(HERE, "holdings_now.json")))
Q = json.load(open(os.path.join(HERE, "quote_by_mint.json")))
mints = {"So11111111111111111111111111111111111111112", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB"}
mints |= {q for q in Q.values() if q not in ("SOL", "old-event")}
mints |= {h["mint"] for h in H["tokens"] if h["ui"]}
mints = sorted(mints); P = {}
for i in range(0, len(mints), 50):
    ids = ",".join(mints[i:i + 50])
    for k in range(4):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(f"https://lite-api.jup.ag/price/v3?ids={ids}", headers={"user-agent": "Mozilla/5.0"}), timeout=30))
            for m, v in r.items():
                if isinstance(v, dict) and v.get("usdPrice") is not None: P[m] = dict(usd=v["usdPrice"], liq=v.get("liquidity"), dec=v.get("decimals"))
            break
        except Exception: time.sleep(2 + 2 * k)
    time.sleep(0.5)
json.dump(dict(t=time.time(), sol_usd=P.get("So11111111111111111111111111111111111111112", {}).get("usd"), prices=P), open(os.path.join(HERE, "prices.json"), "w"))
print("mints asked", len(mints), "priced", len(P), "SOL", P.get("So11111111111111111111111111111111111111112"))

#!/usr/bin/env python3
# READ-ONLY: 9qz7cW's withdrawals to its 3 treasury wallets in the OLDER period (before the fully read 36 h window), so the
# older period's SOL-side result = SOL balance change (hourly checkpoints) + withdrawals. Takes each treasury's signature list,
# keeps the ones 9qz7cW signed before FULL_FROM, fetches them (owner's RPC, slow) and sums the SOL sent. -> older_wd.json
import sys, os, json, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
os.environ.setdefault("Q9Z_RATE", "0.6")
from rpcq import rpc
W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"; FULL_FROM = 1792594800
DEST = ["9BhkaAybG824w5Hk2A1Np22ZwYN74f6kisJtLEK9C6Ns", "GBXnrHXZENJZrpCHjSX177XR78e9Pmjmawp2ZukiJcv6", "3UEJbmddD8zWDKUKZQieGQwTEXrHhyy3MXbsNk6pZFnq"]
mine = {s["signature"] for s in json.load(open(os.path.join(HERE, "sigs.json")))}
out = []
for a in DEST:
    sg = rpc("getSignaturesForAddress", [a, {"limit": 100}]) or []
    for s in sg:
        if s["signature"] not in mine or (s.get("blockTime") or 0) >= FULL_FROM or s.get("err"): continue
        tx = rpc("getTransaction", [s["signature"], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])
        if not tx: continue
        amt = sum(ix["parsed"]["info"]["lamports"] for ix in tx["transaction"]["message"]["instructions"]
                  if isinstance(ix.get("parsed"), dict) and ix["parsed"].get("type") == "transfer" and ix["parsed"]["info"].get("source") == W and ix["parsed"]["info"].get("destination") == a) / 1e9
        out.append(dict(dest=a, sig=s["signature"], bt=s["blockTime"], utc=datetime.datetime.fromtimestamp(s["blockTime"], datetime.timezone.utc).strftime("%m-%d %H:%M"), sol=amt))
        print(out[-1], flush=True)
json.dump(out, open(os.path.join(HERE, "older_wd.json"), "w"), indent=1)
print("older withdrawals to treasuries:", len(out), round(sum(x["sol"] for x in out), 3), "SOL")

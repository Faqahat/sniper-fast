#!/usr/bin/env python3
# READ-ONLY: all signatures of the wallet, owner's RPC first, then public mainnet-beta for anything older (paced).
import sys, os, json, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import rpcu
W = sys.argv[1] if len(sys.argv) > 1 else rpcu.W; OUT = sys.argv[2] if len(sys.argv) > 2 else f"sigs_{W[:6]}.json"
MAXPUB = int(os.environ.get("MAXPUB", "50"))
sigs, before, src = [], None, "owner"
while True:
    p = {"limit": 1000}
    if before: p["before"] = before
    try: r = rpcu.rpc("getSignaturesForAddress", [W, p], ep=None if src == "owner" else rpcu.PUB)
    except RuntimeError as e: print("stop:", e); break
    if not r:
        if src == "owner" and MAXPUB > 0: src = "public"; print("owner RPC exhausted at", len(sigs), "-> public", flush=True); continue
        break
    for x in r: x["src"] = src
    sigs += r; before = r[-1]["signature"]
    ts = lambda b: datetime.datetime.fromtimestamp(b, datetime.timezone.utc).strftime("%m-%d %H:%M") if b else "?"
    print(f"{len(sigs)} sigs, oldest slot {r[-1]['slot']} {ts(r[-1].get('blockTime'))} ({src})", flush=True)
    if src == "public":
        MAXPUB -= 1; time.sleep(1.0)
        if MAXPUB <= 0: print("public page cap reached"); break
    if len(r) < 1000 and src == "public": break
    if len(r) < 1000 and src == "owner": src = "public" if MAXPUB > 0 else None
    if src is None: break
json.dump(sigs, open(OUT, "w"))
print("saved", len(sigs), "->", OUT)

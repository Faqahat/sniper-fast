#!/usr/bin/env python3
# READ-ONLY: continue the signature crawl on public mainnet-beta from the oldest known sig until the wallet's first tx.
import sys, os, json, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import rpcu
W = rpcu.W; S = json.load(open("sigs_FiFawH.json")); before = S[-1]["signature"]; out = []
OUT = "sigs_FiFawH_old.json"
if os.path.exists(OUT): out = json.load(open(OUT)); before = out[-1]["signature"] if out else before
while True:
    try: r = rpcu.rpc("getSignaturesForAddress", [W, {"limit": 1000, "before": before}], ep=rpcu.PUB, tries=10)
    except RuntimeError as e: print("stop:", e); break
    if not r: break
    for x in r: x["src"] = "public"
    out += r; before = r[-1]["signature"]
    print(f"{len(out)} older sigs, oldest slot {r[-1]['slot']} {datetime.datetime.fromtimestamp(r[-1].get('blockTime') or 0, datetime.timezone.utc):%m-%d %H:%M}", flush=True)
    json.dump(out, open(OUT, "w"))
    if len(r) < 1000: break
    time.sleep(1.0)
print("done", len(out))

#!/usr/bin/env python3
# -I isolated. Build buy_slot, create_slot, delta per token.
import json, os, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

TOKEN = os.environ["CONSTANTK_TOKEN"]
RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOKEN}"

def rpc(method, params, tries=5):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    last=None
    for a in range(tries):
        try:
            req=urllib.request.Request(RPC, data=body, headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                j=json.loads(r.read())
            if "error" in j:
                last=j["error"]
                # slot skipped / missing block -> don't retry forever
                time.sleep(0.4*(a+1)); continue
            return j["result"]
        except Exception as e:
            last=str(e); time.sleep(0.5*(a+1))
    return {"__err__": last}

rt = json.load(open("/root/roundtrips.json"))["roundtrips"]
raw = json.load(open("/root/expanded_raw.json"))

buy_slot = {x["mint"]: x["buy_slot"] for x in rt if x.get("buy_slot")}

# mints that have both a buy_slot and a create_sig
tasks=[]
for mint, meta in raw.items():
    if meta.get("status")!="ok": continue
    sig=meta.get("create_sig")
    if not sig: continue
    if mint not in buy_slot: continue
    tasks.append((mint, sig))

print(f"tokens with buy_slot: {len(buy_slot)}; with create_sig+buy_slot: {len(tasks)}", file=sys.stderr)

def get_create_slot(args):
    mint, sig = args
    r = rpc("getTransaction", [sig, {"maxSupportedTransactionVersion":0,"commitment":"confirmed"}])
    if isinstance(r, dict) and "__err__" in r:
        return mint, None, r["__err__"]
    if not r:
        return mint, None, "null"
    return mint, r.get("slot"), None

out={}
errs=0
with ThreadPoolExecutor(max_workers=16) as ex:
    futs=[ex.submit(get_create_slot,t) for t in tasks]
    for f in as_completed(futs):
        mint, cslot, err = f.result()
        if cslot is None:
            errs+=1; continue
        out[mint]={"mint":mint,"create_slot":cslot,"buy_slot":buy_slot[mint],
                   "delta":buy_slot[mint]-cslot}

print(f"resolved create_slot for {len(out)} tokens; errors {errs}", file=sys.stderr)
json.dump(out, open("/root/geo_slots.json","w"), indent=0)

# summary of deltas
from collections import Counter
c=Counter(v["delta"] for v in out.values())
print("delta distribution (buy_slot - create_slot):", file=sys.stderr)
for d in sorted(c):
    print(f"  delta={d}: {c[d]}", file=sys.stderr)

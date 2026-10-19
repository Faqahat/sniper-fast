#!/usr/bin/env python3
import json, os, urllib.request, time

TOKEN=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOKEN}"

def rpc(method,params,tries=5):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    last=None
    for a in range(tries):
        try:
            req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=40) as r:
                j=json.loads(r.read())
            if "error" in j:
                last=j["error"]; time.sleep(0.4*(a+1)); continue
            return j["result"]
        except Exception as e:
            last=str(e); time.sleep(0.5*(a+1))
    return {"__err__":last}

slots=json.load(open("/root/geo_slots.json"))
sample=[v["buy_slot"] for v in list(slots.values())[:3]]
print("sample buy slots:",sample)

# current epoch info
ei=rpc("getEpochInfo",[])
print("epochInfo:",ei)

def leader_from_block(slot):
    b=rpc("getBlock",[slot,{"rewards":True,"transactionDetails":"none","maxSupportedTransactionVersion":0,"commitment":"confirmed"}])
    if isinstance(b,dict) and "__err__" in b: return None,b["__err__"]
    if not b: return None,"null block"
    rws=b.get("rewards") or []
    for rw in rws:
        if rw.get("rewardType")=="Fee":
            return rw.get("pubkey"),None
    # fallback: any reward
    if rws: return rws[0].get("pubkey"),"no-Fee-reward"
    return None,"no rewards"

for s in sample:
    lead,err=leader_from_block(s)
    print(f"slot {s} -> leader {lead} (err={err})")

# cross-check with getSlotLeaders if within range
abs_slot=ei.get("absoluteSlot")
for s in sample:
    if abs_slot and 0 <= abs_slot - s < 400000:
        sl=rpc("getSlotLeaders",[s,1])
        print(f"getSlotLeaders({s}) -> {sl}")
    else:
        print(f"slot {s} out of getSlotLeaders range (abs {abs_slot})")

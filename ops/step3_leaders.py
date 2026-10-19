#!/usr/bin/env python3
import json, os, urllib.request, time, random
from concurrent.futures import ThreadPoolExecutor, as_completed

TOKEN=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOKEN}"

def rpc(method,params,tries=6):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    last=None
    for a in range(tries):
        try:
            req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=40) as r:
                j=json.loads(r.read())
            if "error" in j:
                last=j["error"]; time.sleep(0.3*(a+1)); continue
            return j["result"]
        except Exception as e:
            last=str(e); time.sleep(0.4*(a+1))
    return {"__err__":last}

def leader_of(slot):
    b=rpc("getBlock",[slot,{"rewards":True,"transactionDetails":"none","maxSupportedTransactionVersion":0,"commitment":"confirmed"}])
    if isinstance(b,dict) and "__err__" in b: return slot,None
    if not b: return slot,None
    for rw in (b.get("rewards") or []):
        if rw.get("rewardType")=="Fee":
            return slot,rw.get("pubkey")
    return slot,None

slots=json.load(open("/root/geo_slots.json"))
# his slots: buy_slots (where he landed) - the key set
buy_slots=sorted({v["buy_slot"] for v in slots.values()})

# baseline: random slots spread across his trading range
lo=min(buy_slots); hi=max(buy_slots)
random.seed(42)
baseline_slots=sorted(set(random.randint(lo,hi) for _ in range(500)))

all_slots=sorted(set(buy_slots)|set(baseline_slots))
print(f"buy_slots {len(buy_slots)}, baseline {len(baseline_slots)}, union {len(all_slots)}, range {lo}-{hi}")

leaders={}
with ThreadPoolExecutor(max_workers=24) as ex:
    futs=[ex.submit(leader_of,s) for s in all_slots]
    for f in as_completed(futs):
        s,l=f.result()
        if l: leaders[s]=l
print(f"resolved leaders for {len(leaders)}/{len(all_slots)} slots")

# cluster nodes -> identity -> ip
cn=rpc("getClusterNodes",[])
id2ip={}
id2tpu={}
for n in cn:
    pk=n.get("pubkey")
    # gossip ip preferred, fallback tpu
    ip=None
    for field in ("gossip","tpu","rpc","tvu"):
        v=n.get(field)
        if v and ":" in v:
            ip=v.rsplit(":",1)[0]; break
    if pk and ip:
        id2ip[pk]=ip
print(f"cluster nodes: {len(cn)}, with ip: {len(id2ip)}")

json.dump({"leaders":{str(k):v for k,v in leaders.items()},
           "buy_slots":buy_slots,
           "baseline_slots":baseline_slots,
           "id2ip":id2ip}, open("/root/geo_leaders.json","w"))

# how many leader identities not found in cluster nodes
lead_ids=set(leaders.values())
missing=[x for x in lead_ids if x not in id2ip]
print(f"unique leader identities: {len(lead_ids)}, not in clusterNodes: {len(missing)}")

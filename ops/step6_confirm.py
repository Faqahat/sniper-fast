#!/usr/bin/env python3
import json, os, urllib.request, time
TOKEN=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOKEN}"
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
def rpc(m,p,tries=5):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for a in range(tries):
        try:
            req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=60) as r:
                j=json.loads(r.read())
            if "error" in j: time.sleep(0.4*(a+1)); continue
            return j["result"]
        except Exception as e: time.sleep(0.5*(a+1))
    return None

# Confirm his wallet appears in these far same-slot blocks (buy landed there)
cases=[("Japan/Tokyo",457732449),("US/Ashburn",457504321),("Japan/Tokyo",457390879),("US/Secaucus",457468065)]
for label,slot in cases:
    b=rpc("getBlock",[slot,{"transactionDetails":"accounts","rewards":False,"maxSupportedTransactionVersion":0,"commitment":"confirmed"}])
    if not b: print(f"{label} slot {slot}: block null"); continue
    found=False
    ntx=0
    for tx in b.get("transactions",[]):
        ntx+=1
        accts=[a.get("pubkey") for a in tx.get("transaction",{}).get("accountKeys",[])]
        if WALLET in accts: found=True
    print(f"{label} slot {slot}: wallet_in_block={found} ntx={ntx}")

# Statistical check: is his same-slot non-EU rate consistent with baseline (i.e. global, not EU-limited)?
geo=json.load(open("/root/geo_ip.json"))
d=json.load(open("/root/geo_leaders.json"))
leaders={int(k):v for k,v in d["leaders"].items()}; id2ip=d["id2ip"]
sm=json.load(open("/root/geo_slots.json"))
EU={"DE","NL","FR","GB","FI","LT","LV","EE","PL","IE","AT","CH","SE","NO","DK","BE","ES","IT","CZ","RO","BG","PT","LU","UA","RU","MD","HU","SK","SI","HR","RS","GR","IS"}
def isEU(slot):
    lid=leaders.get(slot); g=geo.get(id2ip.get(lid,""),{})
    cc=g.get("countryCode")
    if cc is None: return None
    return cc in EU
same=[v["buy_slot"] for v in sm.values() if v["delta"]<=0]
se=[isEU(s) for s in same]; se=[x for x in se if x is not None]
noneu=se.count(False)
print(f"\nSame-slot: n={len(se)} non-EU={noneu} ({100*noneu/len(se):.1f}%)")
base=[isEU(s) for s in d["baseline_slots"]]; base=[x for x in base if x is not None]
bnoneu=base.count(False)
print(f"Baseline: n={len(base)} non-EU={bnoneu} ({100*bnoneu/len(base):.1f}%)")
# binomial: if he were geo-limited we'd expect ~0% non-EU; observed 22%. test vs 0 trivially rejects.
# also test his same-slot non-EU vs baseline rate (are they different?)
p=bnoneu/len(base)
import math
exp=p*len(se); sd=math.sqrt(len(se)*p*(1-p))
z=(noneu-exp)/sd
print(f"If same-slot drew from baseline geo: expected non-EU={exp:.1f}, observed={noneu}, z={z:.2f}")
# Asia specifically
ASIA={"JP","SG","KR","HK","CN","IN","TW","ID","TH","VN","MY","AE","IL","TR","KZ","PH","GE"}
def isAsia(slot):
    lid=leaders.get(slot); g=geo.get(id2ip.get(lid,""),{}); return g.get("countryCode") in ASIA
sa=sum(1 for s in same if isAsia(s)); ba=sum(1 for s in d["baseline_slots"] if isAsia(s))
print(f"Same-slot Asia={sa}/{len(same)} ({100*sa/len(same):.1f}%) vs baseline Asia={ba}/{len(d['baseline_slots'])} ({100*ba/len(d['baseline_slots']):.1f}%)")

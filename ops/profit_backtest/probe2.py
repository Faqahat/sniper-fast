#!/usr/bin/env python3
import os, json, urllib.request, urllib.error, time
from collections import Counter
RPC=os.environ["RPC"]
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
_B58="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58dec(s):
    n=0
    for c in s: n=n*58+_B58.index(c)
    return (b"\x00"*(len(s)-len(s.lstrip("1"))))+(n.to_bytes((n.bit_length()+7)//8,"big") if n else b"")
def rpc(m,pr):
    r=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":pr}).encode(),headers={"Content-Type":"application/json"})
    for a in range(5):
        try: return json.load(urllib.request.urlopen(r,timeout=60)).get("result")
        except urllib.error.HTTPError as e: time.sleep(1.2*(a+1) if e.code==429 else 0.5)
        except Exception: time.sleep(0.5)
    return None
disc_top=Counter(); disc_inner=Counter(); pump_top=0; pump_inner=0
s0=rpc("getSlot",[{"commitment":"finalized"}])
nblk=0
for i in range(60):
    sl=s0-800-i*7
    b=rpc("getBlock",[sl,{"maxSupportedTransactionVersion":1,"transactionDetails":"full","encoding":"json","rewards":False}])
    if not b: continue
    nblk+=1
    for tx in b["transactions"]:
        msg=tx["transaction"]["message"]; keys=list(msg["accountKeys"])
        la=tx.get("meta",{}).get("loadedAddresses") or {}
        keys=keys+la.get("writable",[])+la.get("readonly",[])
        for ix in msg.get("instructions",[]):
            pidx=ix.get("programIdIndex")
            if pidx is None or pidx>=len(keys): continue
            if keys[pidx]==PUMP:
                pump_top+=1
                try: disc_top[b58dec(ix.get("data",""))[:8].hex()]+=1
                except: pass
        for inn in tx.get("meta",{}).get("innerInstructions",[]) or []:
            for ix in inn.get("instructions",[]):
                pidx=ix.get("programIdIndex")
                if pidx is None or pidx>=len(keys): continue
                if keys[pidx]==PUMP:
                    pump_inner+=1
                    try: disc_inner[b58dec(ix.get("data",""))[:8].hex()]+=1
                    except: pass
print(f"scanned {nblk} blocks  pump_top={pump_top} pump_inner={pump_inner}")
print("TOP disc:", disc_top.most_common(12))
print("INNER disc:", disc_inner.most_common(12))

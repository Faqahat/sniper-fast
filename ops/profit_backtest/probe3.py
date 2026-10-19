#!/usr/bin/env python3
import os, json, urllib.request, urllib.error, time
RPC=os.environ["RPC"]
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CREATE_V2="d6904cec5f8b31b4"; CREATE="181ec828051c0777"
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
# find a few creates, print account[0..6]
s0=rpc("getSlot",[{"commitment":"finalized"}])
found=[]
i=0
while len(found)<3 and i<400:
    sl=s0-800-i
    i+=1
    b=rpc("getBlock",[sl,{"maxSupportedTransactionVersion":1,"transactionDetails":"full","encoding":"json","rewards":False}])
    if not b: continue
    for tx in b["transactions"]:
        msg=tx["transaction"]["message"]; keys=list(msg["accountKeys"])
        la=tx.get("meta",{}).get("loadedAddresses") or {}
        keys=keys+la.get("writable",[])+la.get("readonly",[])
        for ix in msg.get("instructions",[]):
            pidx=ix.get("programIdIndex")
            if pidx is None or pidx>=len(keys) or keys[pidx]!=PUMP: continue
            try: disc=b58dec(ix.get("data",""))[:8].hex()
            except: continue
            if disc in (CREATE_V2,CREATE):
                acc=[keys[a] for a in ix["accounts"][:8] if a<len(keys)]
                found.append((sl,disc,acc,tx["transaction"]["signatures"][0]))
print("creates found:",len(found))
for sl,disc,acc,sig in found:
    print("slot",sl,"disc",disc)
    for j,a in enumerate(acc): print("  acct[%d]=%s"%(j,a))
    print("  sig",sig)
# test: is acct[1] (mint_authority) a create-only stream?
if found:
    ma=found[0][2][1]
    print("\n=== getSignaturesForAddress on acct[1]=%s (limit 20) ==="%ma)
    sigs=rpc("getSignaturesForAddress",[ma,{"limit":20}])
    if sigs:
        print("got",len(sigs),"sigs; sampling 5 txs for their pump disc:")
        for s in sigs[:5]:
            tx=rpc("getTransaction",[s["signature"],{"maxSupportedTransactionVersion":1,"encoding":"json"}])
            if not tx: print("  ",s["signature"][:12],"no tx"); continue
            msg=tx["transaction"]["message"]; keys=list(msg["accountKeys"])
            la=tx.get("meta",{}).get("loadedAddresses") or {}; keys=keys+la.get("writable",[])+la.get("readonly",[])
            ds=[]
            for ix in msg.get("instructions",[]):
                pidx=ix.get("programIdIndex")
                if pidx is not None and pidx<len(keys) and keys[pidx]==PUMP:
                    try: ds.append(b58dec(ix.get("data",""))[:8].hex())
                    except: pass
            print("  slot",s["slot"],"err",bool(s["err"]),"pumpdisc",ds)

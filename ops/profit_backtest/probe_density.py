#!/usr/bin/env python3
import sys, os, json, urllib.request, urllib.error, time
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
        except urllib.error.HTTPError as e:
            time.sleep(1.2*(a+1) if e.code==429 else 0.5)
        except Exception as ex:
            time.sleep(0.5)
    return None
def scan_block(slot):
    b=rpc("getBlock",[slot,{"maxSupportedTransactionVersion":1,"transactionDetails":"full","encoding":"json","rewards":False}])
    if not b: return None
    nc=0; ntx=len(b.get("transactions",[]))
    for tx in b["transactions"]:
        msg=tx["transaction"]["message"]; keys=msg["accountKeys"]
        for ix in msg.get("instructions",[]):
            pid=keys[ix["programIdIndex"]] if ix.get("programIdIndex") is not None else None
            if pid==PUMP:
                d=ix.get("data","")
                try: disc=b58dec(d)[:8].hex()
                except: continue
                if disc in (CREATE_V2,CREATE): nc+=1
    return nc,ntx,b.get("blockTime")
s0=rpc("getSlot",[{"commitment":"finalized"}])
print("finalized slot",s0)
tot=0; blk=0
for i in range(15):
    sl=s0-500-i
    r=scan_block(sl)
    if r is None: print(sl,"skipped"); continue
    nc,ntx,bt=r; tot+=nc; blk+=1
    print(f"slot={sl} txs={ntx} creates={nc} bt={bt}")
print(f"TOTAL creates={tot} over {blk} blocks -> {tot/max(blk,1):.2f} creates/block")

import json, sys, threading, time
import concurrent.futures as cf
sys.path.insert(0,'/root/last30')
import rpc
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CB="ComputeBudget111111111111111111111111111111"
CREATE=bytes([0xd6,0x90,0x4c,0xec,0x5f,0x8b,0x31,0xb4])
BUYS={"e1f7501ed5b38488","c2ab1c46684d5b2f","38fc74089edfcd5f","66063d1201daebea","b817ee6167c5d33d","07051dc4f5176550"}
JITO={"96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5","HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe","Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY","ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49","DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh","ADuUkR4vqLUMWXxW9gh6D6L8pGAyzx4q8tY7s9Z6bK7","DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL","3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT"}
_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s: n=n*58+_A.index(c)
    o=bytearray()
    while n>0: o.append(n&0xff); n>>=8
    o.reverse(); return bytes(len(s)-len(s.lstrip('1')))+bytes(o)

def parse_create_meta(d):
    # d = create instruction data (after b58 decode). layout: disc(8)+name:str+symbol:str+uri:str+creator:pk
    try:
        p=8
        def rstr():
            nonlocal p
            ln=int.from_bytes(d[p:p+4],'little'); p+=4
            s=d[p:p+ln].decode('utf-8','replace'); p+=ln
            return s
        name=rstr(); sym=rstr(); uri=rstr()
        return {"name":name,"symbol":sym,"uri":uri}
    except Exception:
        return None

def parse_block(slot, mint):
    b=rpc.call("getBlock",[slot,{"encoding":"json","transactionDetails":"full","maxSupportedTransactionVersion":1,"rewards":False}])
    if not b: return None, None
    bt=b.get("blockTime")
    rows=[]
    for idx,tx in enumerate(b["transactions"]):
        msg=tx["transaction"]["message"]; keys=msg["accountKeys"]
        meta=tx.get("meta") or {}
        la=meta.get("loadedAddresses",{}) or {}
        allk=keys+la.get("writable",[])+la.get("readonly",[])
        if PUMP not in allk or mint not in allk: continue
        signer=keys[0]
        iscre=False; isbuy=None; vanilla=None; cmeta=None; cup=0
        allins=list(msg["instructions"])
        for inner in meta.get("innerInstructions",[]):
            allins+=inner.get("instructions",[])
        for ins in allins:
            prog=allk[ins["programIdIndex"]]
            if prog!=PUMP and prog!=CB: continue
            try: d=b58d(ins["data"])
            except: continue
            if prog==CB and d and d[0]==3 and len(d)>=9: cup=int.from_bytes(d[1:9],'little')
            if prog==PUMP:
                if d[:8]==CREATE:
                    iscre=True
                    vanilla=(len(d)>=11) and all(x==0 for x in d[-11:])
                    cmeta=parse_create_meta(d)
                elif d[:8].hex() in BUYS: isbuy=d[:8].hex()
        if not iscre and not isbuy: continue
        # curve sol inflow (positive = buy into curve)
        preT={x["accountIndex"]:int(x["uiTokenAmount"]["amount"]) for x in meta.get("preTokenBalances",[]) if x["mint"]==mint}
        postT={x["accountIndex"]:int(x["uiTokenAmount"]["amount"]) for x in meta.get("postTokenBalances",[]) if x["mint"]==mint}
        owners={}
        for x in meta.get("preTokenBalances",[])+meta.get("postTokenBalances",[]):
            if x["mint"]==mint: owners[x["accountIndex"]]=x.get("owner")
        cowners=set(o for i,o in owners.items() if o and o!=signer)
        csol=0
        for i,k in enumerate(allk):
            if k in cowners: csol+=meta["postBalances"][i]-meta["preBalances"][i]
        tip=sum(max(0,meta["postBalances"][i]-meta["preBalances"][i]) for i,k in enumerate(allk) if k in JITO)
        ok=meta.get("err") is None
        rows.append(dict(idx=idx,signer=signer,iscre=iscre,isbuy=isbuy,vanilla=vanilla,
                         csol=csol,cu_price=cup,jito_tip=tip,ok=ok,meta=cmeta))
    return bt, rows

tape=json.load(open('/root/mirror/his_tape.json'))
tape=[d for d in tape if d.get('create_slot') is not None]
print(f"collecting create-slot blocks for {len(tape)} tokens", file=sys.stderr)
out={}; lock=threading.Lock(); done=[0]
def work(d):
    mint=d['mint']; cslot=d['create_slot']
    try:
        bt, rows = parse_block(cslot, mint)
    except Exception as e:
        rows=None; bt=None
    with lock:
        done[0]+=1
        if done[0]%20==0: print(f"  {done[0]}/{len(tape)}", file=sys.stderr)
    return mint, dict(create_slot=cslot, buy_slot=d['buy_slot'], delta=d['delta'],
                      blocktime=bt, rows=rows, creator=d['creator'],
                      peak_r=d.get('peak_r'), r5=d.get('r5'), r10=d.get('r10'), r20=d.get('r20'),
                      realized_R=d.get('realized_R'), sol_in=d.get('sol_in'), dev_buy_sol=d.get('dev_buy_sol'))
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    for mint, rec in ex.map(work, tape):
        out[mint]=rec
nfail=sum(1 for v in out.values() if v['rows'] is None)
print(f"done. {len(out)} tokens, {nfail} block-fetch failures", file=sys.stderr)
json.dump(out, open('/root/every_angle/slotdata.json','w'))

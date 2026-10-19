import json, sys, threading
import concurrent.futures as cf
sys.path.insert(0,'/root/last30')
import rpc
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CB="ComputeBudget111111111111111111111111111111"
CREATE=bytes([0xd6,0x90,0x4c,0xec,0x5f,0x8b,0x31,0xb4])
BUYS={"e1f7501ed5b38488","c2ab1c46684d5b2f","38fc74089edfcd5f","66063d1201daebea","b817ee6167c5d33d","07051dc4f5176550"}
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s: n=n*58+_A.index(c)
    o=bytearray()
    while n>0: o.append(n&0xff); n>>=8
    o.reverse(); return bytes(len(s)-len(s.lstrip('1')))+bytes(o)
def parse_block(slot, mint):
    b=rpc.call("getBlock",[slot,{"encoding":"json","transactionDetails":"full","maxSupportedTransactionVersion":1,"rewards":False}])
    if not b: return None
    rows=[]
    for tx in b["transactions"]:
        msg=tx["transaction"]["message"]; keys=msg["accountKeys"]; meta=tx.get("meta") or {}
        la=meta.get("loadedAddresses",{}) or {}
        allk=keys+la.get("writable",[])+la.get("readonly",[])
        if PUMP not in allk or mint not in allk: continue
        signer=keys[0]; iscre=False; isbuy=None
        allins=list(msg["instructions"])
        for inner in meta.get("innerInstructions",[]): allins+=inner.get("instructions",[])
        for ins in allins:
            prog=allk[ins["programIdIndex"]]
            if prog!=PUMP: continue
            try: d=b58d(ins["data"])
            except: continue
            if d[:8]==CREATE: iscre=True
            elif d[:8].hex() in BUYS: isbuy=True
        if not iscre and not isbuy: continue
        owners={}
        for x in meta.get("preTokenBalances",[])+meta.get("postTokenBalances",[]):
            if x["mint"]==mint: owners[x["accountIndex"]]=x.get("owner")
        cowners=set(o for i,o in owners.items() if o and o!=signer)
        csol=0
        for i,k in enumerate(allk):
            if k in cowners: csol+=meta["postBalances"][i]-meta["preBalances"][i]
        rows.append(dict(signer=signer,iscre=iscre,isbuy=bool(isbuy),csol=csol,ok=meta.get("err") is None))
    return rows
tape=json.load(open('/root/mirror/his_tape.json'))
tape=[d for d in tape if d.get('create_slot') is not None and d.get('peak_r') is not None]
print(f"collecting slots 0-3 for {len(tape)} tokens",file=sys.stderr)
out={}; lock=threading.Lock(); done=[0]
def work(d):
    mint=d['mint']; cs=d['create_slot']; per={}
    for off in (0,1,2,3):
        rows=None
        try: rows=parse_block(cs+off, mint)
        except Exception: rows=None
        if rows is None: per[off]=None; continue
        cre=[r for r in rows if r['iscre']]
        dev=cre[0]['signer'] if cre else d.get('creator')
        buys=[r for r in rows if r['isbuy'] and r['ok'] and r['signer']!=dev and r['signer']!=WALLET]
        sells=[r for r in rows if (not r['isbuy']) and (not r['iscre'])]
        per[off]=dict(nbuy=len(buys), ndistinct=len(set(r['signer'] for r in buys)),
                      sol=sum(max(0,r['csol']) for r in buys)/1e9, nsell=len(sells))
    with lock:
        done[0]+=1
        if done[0]%25==0: print(f"  {done[0]}/{len(tape)}",file=sys.stderr)
    return mint, dict(per=per, peak=d['peak_r'], rr=d['realized_R'], slot=cs)
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    for m,r in ex.map(work, tape): out[m]=r
json.dump(out, open('/root/every_angle/early_flow.json','w'))
print(f"done {len(out)}",file=sys.stderr)

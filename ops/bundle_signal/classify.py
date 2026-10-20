#!/usr/bin/env python3
"""Slot-0 insider-bundle classifier. For each filter-passing launch, getBlock(create_slot) and classify:
  jito_tip_on_create, create_cu_price, adjacent_zero_fee_buys (this-mint buys cu_price==0 at create_idx+1..+4),
  max_competitor_cu_price, n_buys_in_create_slot. BUNDLED = tip>0 OR adjacent_zero_fee_buys>=1.
Caches compact per-mint result JSON (not raw blocks). Threaded, block fetch deduped by slot."""
import os, json, sys, time, urllib.request, threading
from concurrent.futures import ThreadPoolExecutor

tok=[l.split('=',1)[1].strip().strip('"').strip("'") for l in open('/root/sniper/deploy/.env') if l.startswith('CONSTANTK_TOKEN')][0]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={tok}"
def rpc(m,p):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for a in range(6):
        try:
            r=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            return json.loads(urllib.request.urlopen(r,timeout=120).read())
        except Exception as e:
            time.sleep(0.5*(a+1))
    return {"error":"retries_exhausted"}

_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s: n=n*58+_A.index(c)
    o=bytearray()
    while n>0: o.append(n&0xff); n>>=8
    o.reverse(); return bytes(len(s)-len(s.lstrip('1')))+bytes(o)

PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; CB="ComputeBudget111111111111111111111111111111"
CREATE=bytes([0xd6,0x90,0x4c,0xec,0x5f,0x8b,0x31,0xb4])
CREATE_V1=bytes.fromhex("181ec828051c0777")
BUYS={"e1f7501ed5b38488","c2ab1c46684d5b2f","38fc74089edfcd5f","66063d1201daebea","b817ee6167c5d33d","07051dc4f5176550"}
JITO={"96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5","HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe","Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY","ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49","DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh","ADuUkR4vqLUMWXxW9gh6D6L8pGAyzx4q8tY7s9Z6bK7","DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL","3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT"}

CACHE="/root/bundle_signal/blockfeat"; os.makedirs(CACHE,exist_ok=True)
_block_cache={}; _lock=threading.Lock()

def get_block(slot):
    with _lock:
        if slot in _block_cache: return _block_cache[slot]
    b=rpc("getBlock",[slot,{"encoding":"json","transactionDetails":"full","maxSupportedTransactionVersion":1,"rewards":False}])
    res=b.get("result")
    with _lock:
        _block_cache[slot]=res
    return res

def decode_tx(tx):
    """return dict: is_create, is_buy, cu_price, jito_tip, mint_in (set membership tested by caller via allk)."""
    msg=tx['transaction']['message']; keys=msg['accountKeys']
    la=tx.get('meta',{}).get('loadedAddresses',{}) or {}
    allk=keys+la.get('writable',[])+la.get('readonly',[])
    cup=0; iscre=False; isbuy=False
    for ins in msg['instructions']:
        prog=allk[ins['programIdIndex']]
        if prog!=PUMP and prog!=CB: continue
        try: d=b58d(ins['data'])
        except: continue
        if prog==CB and d:
            if d[0]==3 and len(d)>=9: cup=int.from_bytes(d[1:9],'little')
        elif prog==PUMP:
            if d[:8]==CREATE or d[:8]==CREATE_V1: iscre=True
            elif d[:8].hex() in BUYS: isbuy=True
    tip=0
    meta=tx.get('meta',{})
    pre=meta.get('preBalances',[]); post=meta.get('postBalances',[])
    for i,k in enumerate(allk):
        if k in JITO and i<len(pre) and i<len(post):
            tip+=max(0,post[i]-pre[i])
    err=meta.get('err') is not None
    return {"allk":allk,"cu_price":cup,"is_create":iscre,"is_buy":isbuy,"jito_tip":tip,"err":err}

def classify(c):
    mint=c["mint"]; slot=c["create_slot"]; sig=c["sig"]
    fp=os.path.join(CACHE,mint+".json")
    if os.path.exists(fp):
        try: return json.load(open(fp))
        except: pass
    blk=get_block(slot)
    if not blk:
        out={"mint":mint,"create_slot":slot,"error":"noblock"}
        json.dump(out,open(fp,"w")); return out
    txs=blk["transactions"]
    # locate create tx by signature
    create_idx=None
    for idx,tx in enumerate(txs):
        s=tx['transaction'].get('signatures',[])
        if s and s[0]==sig: create_idx=idx; break
    # decode all txs once
    dec=[decode_tx(tx) for tx in txs]
    if create_idx is None:
        # fallback: find create tx for this mint
        for idx,d in enumerate(dec):
            if d["is_create"] and mint in d["allk"]: create_idx=idx; break
    if create_idx is None:
        out={"mint":mint,"create_slot":slot,"error":"nocreate","n_txs":len(txs)}
        json.dump(out,open(fp,"w")); return out
    cd=dec[create_idx]
    jito_tip=cd["jito_tip"]; create_cu=cd["cu_price"]
    # adjacent zero-fee buys of THIS mint at create_idx+1..+4
    adj_zero=0; adj_zero_anymint=0
    for j in range(create_idx+1, min(create_idx+5, len(txs))):
        dj=dec[j]
        if dj["is_buy"] and dj["cu_price"]==0 and not dj["err"]:
            adj_zero_anymint+=1
            if mint in dj["allk"]: adj_zero+=1
    # competitor buys of THIS mint in the slot (exclude the create tx itself)
    comp_cu=[]; n_buys=0
    for idx,d in enumerate(dec):
        if idx==create_idx: continue
        if d["is_buy"] and (mint in d["allk"]) and not d["err"]:
            n_buys+=1; comp_cu.append(d["cu_price"])
    max_comp=max(comp_cu) if comp_cu else 0
    bundled = (jito_tip>0) or (adj_zero>=1)
    out={"mint":mint,"create_slot":slot,"create_idx":create_idx,"n_txs":len(txs),
         "jito_tip_on_create":jito_tip,"create_cu_price":create_cu,
         "adjacent_zero_fee_buys":adj_zero,"adjacent_zero_fee_buys_anymint":adj_zero_anymint,
         "max_competitor_cu_price":max_comp,"n_buys_in_create_slot":n_buys,"bundled":bundled}
    json.dump(out,open(fp,"w")); return out

if __name__=="__main__":
    sys.path.insert(0,"/root/econ_102"); import econ102 as E
    rows=E.load_backtest()
    rows=[c for c in rows if E.passes_shipped(c) and c["traj"].get("entry_px")]
    print(f"launches to classify: {len(rows)}",flush=True)
    done=0; errs=0; t0=time.time()
    results=[]
    def work(c):
        return classify(c)
    with ThreadPoolExecutor(max_workers=16) as ex:
        for r in ex.map(work, rows):
            results.append(r); done+=1
            if r.get("error"): errs+=1
            if done%50==0: print(f"  {done}/{len(rows)} errs={errs} {time.time()-t0:.0f}s",flush=True)
    json.dump(results,open("/root/bundle_signal/classify.json","w"),indent=0)
    print(f"done {done} errs={errs} in {time.time()-t0:.0f}s -> /root/bundle_signal/classify.json")
    bundled=sum(1 for r in results if r.get("bundled"))
    tipd=sum(1 for r in results if r.get("jito_tip_on_create",0)>0)
    adjd=sum(1 for r in results if r.get("adjacent_zero_fee_buys",0)>=1)
    print(f"BUNDLED={bundled}/{len(results)} ({100*bundled/len(results):.1f}%)  tip>0={tipd}  adj_zero>=1={adjd}")

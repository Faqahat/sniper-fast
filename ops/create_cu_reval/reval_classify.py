#!/usr/bin/env python3
"""Disjoint-window re-validation of the create_cu_price>0 slot-0 signal.
Primary disjoint set = paper window (slots 456878173-456911074), later/disjoint from the mined
656 (456604917-456820114). Optionally extend with a freshly harvested newer window.
For each surviving launch: fetch create block, read create_cu_price (ComputeBudget tag3 u64) +
creator_fee_bps + dev_buy(curve delta) from the create tx; apply base filter creator_fee==0.
Outcome = econ102 net model (entry=floor*1.02, shipped ladder, SIZE=0.5)."""
import os, json, sys, time, urllib.request, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,"/root/econ_102"); import econ102 as E

tok=[l.split('=',1)[1].strip().strip('"').strip("'") for l in open('/root/arbx/deploy/.env') if l.startswith('CONSTANTK_TOKEN')][0]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={tok}"
def rpc(m,p):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for a in range(6):
        try:
            r=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            return json.loads(urllib.request.urlopen(r,timeout=120).read())
        except Exception:
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
CREATE_V2=bytes.fromhex("d6904cec5f8b31b4"); CREATE_V1=bytes.fromhex("181ec828051c0777")
DEV8={"e1f7501ed5b38488","c2ab1c46684d5b2f","38fc74089edfcd5f"}
DEV16={"66063d1201daebea","b817ee6167c5d33d","07051dc4f5176550"}

CACHE="/root/create_cu_reval/blockcache"; os.makedirs(CACHE,exist_ok=True)
_bc={}; _lock=threading.Lock()
def get_block(slot):
    fp=os.path.join(CACHE,f"{slot}.json")
    with _lock:
        if slot in _bc: return _bc[slot]
    if os.path.exists(fp):
        try:
            r=json.load(open(fp))
            with _lock: _bc[slot]=r
            return r
        except: pass
    b=rpc("getBlock",[slot,{"encoding":"json","transactionDetails":"full","maxSupportedTransactionVersion":1,"rewards":False}])
    res=b.get("result")
    try: json.dump(res,open(fp,"w"))
    except: pass
    with _lock: _bc[slot]=res
    return res

def allkeys(tx):
    msg=tx['transaction']['message']; keys=msg['accountKeys']
    la=tx.get('meta',{}).get('loadedAddresses',{}) or {}
    return keys+la.get('writable',[])+la.get('readonly',[])

def parse_create_in_block(slot, mint):
    """Find the create tx for `mint` in block at `slot`. Return create_cu, creator_fee_bps,
    dev_buy(curve SOL), dev_buy_wire(SOL)."""
    blk=get_block(slot)
    if not blk: return {"error":"noblock"}
    for tx in blk["transactions"]:
        msg=tx['transaction']['message']; allk=allkeys(tx)
        meta=tx.get('meta',{})
        if meta.get('err') is not None: continue
        # locate create ix
        cre=None
        for ins in msg['instructions']:
            if allk[ins['programIdIndex']]!=PUMP: continue
            try: d=b58d(ins['data'])
            except: continue
            if d[:8]==CREATE_V2 or d[:8]==CREATE_V1:
                cre=(ins,d); break
        if not cre: continue
        ins,d=cre
        accs=ins['accounts']
        if len(accs)<6: continue
        tx_mint=allk[accs[0]]
        if tx_mint!=mint: continue
        bonding_curve=allk[accs[2]]
        # creator_fee_bps (v2 offsets)
        is_v2 = d[:8]==CREATE_V2; feebps=0
        if is_v2:
            try:
                q=8
                for _ in range(3):
                    ln=int.from_bytes(d[q:q+4],'little'); q+=4+ln
                q+=32
                feebps=int.from_bytes(d[q+2:q+10],'little')
            except: pass
        # create_cu: ComputeBudget tag3 in this tx
        cu=0
        for ins2 in msg['instructions']:
            if allk[ins2['programIdIndex']]!=CB: continue
            try: d2=b58d(ins2['data'])
            except: continue
            if d2 and d2[0]==3 and len(d2)>=9: cu=int.from_bytes(d2[1:9],'little')
        # dev_buy (curve lamports delta)
        dev=0.0
        if bonding_curve in allk:
            i=allk.index(bonding_curve)
            pre=meta.get('preBalances',[]); post=meta.get('postBalances',[])
            if i<len(pre) and i<len(post): dev=max(0.0,(post[i]-pre[i])/1e9)
        # dev_buy_wire from bundled buy ix
        wire=0.0; unb=False
        for ins2 in msg['instructions']:
            if allk[ins2['programIdIndex']]!=PUMP: continue
            try: d2=b58d(ins2['data'])
            except: continue
            disc=d2[:8].hex(); off=8 if disc in DEV8 else (16 if disc in DEV16 else None)
            if off is None: continue
            v=int.from_bytes(d2[off:off+8],'little') if len(d2)>=off+8 else 0
            if v==0xFFFFFFFFFFFFFFFF: unb=True
            else: wire=max(wire,v/1e9)
        return {"create_cu_price":cu,"creator_fee_bps":feebps,"dev_buy":dev,
                "dev_buy_wire":(1e18 if unb else wire),"is_v2":is_v2}
    return {"error":"nocreate"}

if __name__=="__main__":
    PT=json.load(open("/root/profit_ourfill/paper_traj.json"))
    # base: sized dev_buy>=2 SOL (wire), usable trajectory
    cand=[r for r in PT if r["dev_buy_wire_lamports"]/1e9>=2.0 and r.get("n") and r.get("entry_px")]
    print(f"paper launches: total={len(PT)} after dev_wire>=2 & usable = {len(cand)}",flush=True)
    t0=time.time(); out=[]
    def work(r):
        pc=parse_create_in_block(r["create_slot"], r["mint"])
        if pc.get("error"): return {"mint":r["mint"],"error":pc["error"]}
        if pc["creator_fee_bps"]!=0: return {"mint":r["mint"],"error":"fee!=0"}
        entry=r["entry_px"]*E.ENTRY_MULT
        net,gross,legs=E.simulate(entry,r["create_slot"],[(s,p) for s,p in r["series"]],E.SHIP,0.5)
        gnet=E.gross_only(entry,r["create_slot"],[(s,p) for s,p in r["series"]],E.SHIP)
        return {"mint":r["mint"],"slot":r["create_slot"],"net":net,"gross":gnet,
                "create_cu":pc["create_cu_price"],"dev_buy":pc["dev_buy"],
                "dev_buy_wire":min(pc["dev_buy_wire"],r["dev_buy_wire_lamports"]/1e9),
                "cosnip":r["cosnipers"]}
    errs={}
    with ThreadPoolExecutor(max_workers=16) as ex:
        for i,r in enumerate(ex.map(work,cand),1):
            if r.get("error"): errs[r["error"]]=errs.get(r["error"],0)+1
            else: out.append(r)
            if i%50==0: print(f"  {i}/{len(cand)} kept={len(out)} errs={errs} {time.time()-t0:.0f}s",flush=True)
    json.dump(out,open("/root/create_cu_reval/paper_feat.json","w"),indent=0)
    print(f"DONE kept={len(out)} errs={errs} in {time.time()-t0:.0f}s -> paper_feat.json",flush=True)
    slots=[r["slot"] for r in out]
    print(f"slot range {min(slots)}..{max(slots)}")

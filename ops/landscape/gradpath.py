#!/usr/bin/env python3
"""Post-graduation price path + ladder EV. Entry = first PumpSwap trade after migration (market px, lag-tolerant)."""
import os,json,urllib.request,time,threading,statistics
tok=[l.split("=",1)[1].strip() for l in open("/root/arbx/deploy/.env") if l.startswith("CONSTANTK_TOKEN")][0]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={tok}"
CACHE="/root/landscape/gcache"; os.makedirs(CACHE,exist_ok=True)
WSOL="So11111111111111111111111111111111111111112"
PUMPSWAP="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
def rpc(m,p,timeout=60):
    b=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for a in range(6):
        try:
            r=json.load(urllib.request.urlopen(urllib.request.Request(RPC,data=b,headers={"Content-Type":"application/json"}),timeout=timeout))
            if "result" in r: return r["result"]
            return None
        except Exception: time.sleep(0.4*(a+1))
    return None
def gettx(sig):
    f=f"{CACHE}/{sig}.json"
    if os.path.exists(f):
        try: return json.load(open(f))
        except: pass
    tx=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":1,"encoding":"jsonParsed"}])
    try: json.dump(tx,open(f,"w"))
    except: pass
    return tx
def keys(tx):
    msg=tx["transaction"]["message"]
    ks=[k["pubkey"] if isinstance(k,dict) else k for k in msg["accountKeys"]]
    la=tx.get("meta",{}).get("loadedAddresses") or {}
    return ks+list(la.get("writable",[]))+list(la.get("readonly",[]))

def find_vault(migsig,mint):
    tx=gettx(migsig)
    if not tx or not tx.get("meta"): return None
    ks=keys(tx); meta=tx["meta"]
    best=None;bestamt=0
    for t in (meta.get("postTokenBalances") or []):
        if t.get("mint")==mint:
            amt=float(t["uiTokenAmount"]["uiAmountString"] or 0)
            if amt>bestamt: bestamt=amt; best=t.get("accountIndex")
    if best is None: return None
    return ks[best] if best<len(ks) else None

def path(vault,mint,start_slot,win=600,maxtr=60,maxpages=4):
    sigs=[];before=None;pages=0
    while pages<maxpages:
        pr=[vault,{"limit":1000}]
        if before: pr[1]["before"]=before
        ch=rpc("getSignaturesForAddress",pr)
        if not ch: break
        sigs+=ch; before=ch[-1]["signature"]; pages+=1
        if len(ch)<1000: break
        if ch[-1]["slot"]<start_slot: break
    sigs=[s for s in sigs if not s.get("err") and start_slot<=s["slot"]<=start_slot+win]
    sigs.sort(key=lambda s:(s["slot"],s["signature"]))
    series=[]
    for s in sigs[:maxtr]:
        tx=gettx(s["signature"])
        if not tx or not tx.get("meta"): continue
        meta=tx["meta"]
        # price = dWSOL_pool / dTOKEN_pool using vault owner (pool) token deltas
        # compute pool token delta for mint and pool wsol delta
        pre={};post={}
        for t in (meta.get("preTokenBalances") or []):
            post.setdefault("pre",{}); 
        # simpler: sum deltas across token accounts for mint and for WSOL where owner is the pool
        # identify pool = owner of vault
        # delta token (mint) in vault account specifically
        dtok=0.0;dwsol=0.0
        # map accountIndex via preTokenBalances/postTokenBalances by matching the vault account
        ks=keys(tx)
        vidx=ks.index(vault) if vault in ks else None
        def amt_at(lst,idx,m):
            for t in lst:
                if t.get("accountIndex")==idx and t.get("mint")==m: return float(t["uiTokenAmount"]["uiAmountString"] or 0)
            return None
        if vidx is not None:
            a=amt_at(meta.get("preTokenBalances") or [],vidx,mint); b=amt_at(meta.get("postTokenBalances") or [],vidx,mint)
            if a is not None and b is not None: dtok=b-a
        # wsol pool delta: find wsol token account with same owner as vault (pool); approximate via largest wsol delta among token accts owned by pool
        # get pool owner
        poolowner=None
        for t in (meta.get("postTokenBalances") or []):
            if t.get("accountIndex")==vidx: poolowner=t.get("owner")
        if poolowner:
            prew=sum(float(t["uiTokenAmount"]["uiAmountString"] or 0) for t in (meta.get("preTokenBalances") or []) if t.get("owner")==poolowner and t.get("mint")==WSOL)
            postw=sum(float(t["uiTokenAmount"]["uiAmountString"] or 0) for t in (meta.get("postTokenBalances") or []) if t.get("owner")==poolowner and t.get("mint")==WSOL)
            dwsol=postw-prew
        if abs(dtok)>1e-9 and abs(dwsol)>1e-9:
            series.append((s["slot"],abs(dwsol)/abs(dtok)))
    return series

FEE=0.0025 # pumpswap ~0.25%/leg (lower than bonding curve 1%)
SLIP=0.004;PRIO=0.00037
def ladder(entry,fwd,size=0.5,ride=1.4,trail=0.92,cut=0.9,cap=40):
    if not fwd: return -(2*FEE+2*SLIP+2*PRIO/size)
    peak=entry;legs=1;armed=False
    for i,(sl,px) in enumerate(fwd[:cap]):
        r=px/entry
        if px>peak: peak=px
        if r>=ride: armed=True
        stop=(peak/entry)*trail
        ex=False
        if r<=cut and not armed: ex=True
        elif armed and r<=stop: ex=True
        elif i==min(cap,len(fwd))-1: ex=True
        if ex:
            legs+=1; gross=r-1.0
            return gross-(FEE+SLIP)*legs-PRIO*legs/size
    legs+=1; gross=fwd[min(cap,len(fwd))-1][1]/entry-1.0
    return gross-(FEE+SLIP)*legs-PRIO*legs/size

grads=json.load(open("/root/landscape/grads.json"))
import sys
SAMPLE=int(sys.argv[1]) if len(sys.argv)>1 else 70
grads=grads[-SAMPLE:]
res=[];lock=threading.Lock()
def work(g):
    v=find_vault(g["sig"],g["mint"])
    if not v: return
    s=path(v,g["mint"],g["slot"])
    if len(s)<2: 
        with lock: res.append({"mint":g["mint"],"n":len(s),"R":None}); return
    entry=s[0][1]; fwd=s[1:]
    R=ladder(entry,fwd)
    peak=max(p for _,p in s)/entry
    with lock: res.append({"mint":g["mint"],"n":len(s),"entry":entry,"peak_mult":round(peak,3),"R":round(R,4)})
ths=[]
for g in grads:
    t=threading.Thread(target=work,args=(g,));t.start();ths.append(t)
    if len(ths)>=12:
        for t in ths:t.join()
        ths=[]
for t in ths:t.join()
good=[r for r in res if r.get("R") is not None]
json.dump(res,open("/root/landscape/gradpath.json","w"))
print("graduations measured:",len(res),"with usable path:",len(good))
if good:
    Rs=sorted(r["R"] for r in good)
    n=len(Rs)
    print("mean R=%+.4f med=%+.4f win=%.0f%% tot=%+.2f"%(statistics.mean(Rs),statistics.median(Rs),100*sum(1 for r in Rs if r>0)/n,sum(Rs)))
    pk=sorted(r["peak_mult"] for r in good)
    print("post-grad peak mult: med=%.2fx p75=%.2fx p90=%.2fx frac_reach_1.4=%.0f%%"%(statistics.median(pk),pk[int(.75*n)],pk[int(.9*n)],100*sum(1 for p in pk if p>=1.4)/n))
    print("R dist: p10=%+.3f p25=%+.3f p75=%+.3f p90=%+.3f"%(Rs[int(.1*n)],Rs[int(.25*n)],Rs[int(.75*n)],Rs[int(.9*n)]))

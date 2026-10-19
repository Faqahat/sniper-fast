import rpc,json,concurrent.futures as cf,threading,time
W=rpc.WALLET
snipes=json.load(open("/root/snipe_study50/snipes200.json"))["snipes"]

def parse_trade(tx,mint):
    m=tx["meta"]
    keys=[k["pubkey"] if isinstance(k,dict) else k for k in tx["transaction"]["message"]["accountKeys"]]
    pre=m["preBalances"]; post=m["postBalances"]
    preT={b["accountIndex"]:int(b["uiTokenAmount"]["amount"]) for b in m.get("preTokenBalances",[]) if b["mint"]==mint}
    postT={b["accountIndex"]:int(b["uiTokenAmount"]["amount"]) for b in m.get("postTokenBalances",[]) if b["mint"]==mint}
    owners={}
    for b in m.get("preTokenBalances",[])+m.get("postTokenBalances",[]):
        if b["mint"]==mint: owners[b["accountIndex"]]=b.get("owner")
    wal_idx=[i for i,o in owners.items() if o==W]
    curve_idx=[i for i,o in owners.items() if o and o!=W]
    def td(i): return postT.get(i,0)-preT.get(i,0)
    wtok=sum(td(i) for i in wal_idx)
    curve_owner=owners[curve_idx[0]] if curve_idx else None
    csol=0
    if curve_owner:
        for i,k in enumerate(keys):
            if k==curve_owner: csol=post[i]-pre[i]; break
    wsol=post[0]-pre[0]
    ataidx=[b["accountIndex"] for b in m.get("postTokenBalances",[])+m.get("preTokenBalances",[]) if b["mint"]==mint and b.get("owner")==W]
    ata=keys[ataidx[0]] if ataidx else None
    return dict(slot=tx["slot"],bt=tx.get("blockTime"),wtok=wtok,csol=csol,wsol=wsol,curve=curve_owner,ata=ata,feepayer=keys[0])

def all_sigs(addr):
    out=[];before=None
    while True:
        page=rpc.getsigs(addr,before=before,limit=1000)
        if not page: break
        out+=page
        if len(page)<1000: break
        before=page[-1]["signature"]
    return out

lock=threading.Lock();done=[0]
def work(d):
    mint=d["mint"]
    try:
        btx=rpc.gettx(d["sig"])
        bt=parse_trade(btx,mint)
        ata=bt["ata"]; curve=bt["curve"]
        sigs=all_sigs(ata)
        trades=[]
        for s in sigs:
            if s.get("err"): continue
            tx=rpc.gettx(s["signature"])
            if tx is None: continue
            tr=parse_trade(tx,mint)
            tr["sig"]=s["signature"]
            trades.append(tr)
        trades.sort(key=lambda t:(t["slot"],))
        res=dict(mint=mint,buy_sig=d["sig"],buy_slot=d["slot"],buy_lamports=d["buy_lamports"],
                 ata=ata,curve=curve,entry=bt,trades=trades)
    except Exception as e:
        res=dict(mint=mint,buy_sig=d["sig"],buy_slot=d["slot"],error=str(e))
    with lock:
        done[0]+=1
        if done[0]%20==0: print("done",done[0],flush=True)
    return res

t0=time.time()
results=[None]*len(snipes)
with cf.ThreadPoolExecutor(max_workers=16) as ex:
    futs={ex.submit(work,d):i for i,d in enumerate(snipes)}
    for f in cf.as_completed(futs):
        results[futs[f]]=f.result()
json.dump(results,open("trades.json","w"))
errs=[r for r in results if r.get("error")]
print("TOTAL",len(results),"errors",len(errs),"elapsed",round(time.time()-t0,1))
for e in errs[:10]: print("ERR",e["mint"][:10],e["error"][:80])

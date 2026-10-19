import rpc,json,concurrent.futures as cf,threading,time
rows=json.load(open("rows.json"))
res={r["mint"]:r for r in json.load(open("trades.json")) if not r.get("error")}
LAM=1e9
def curve_px(tx,mint,curve):
    m=tx["meta"]
    if m.get("err"): return None
    keys=[k["pubkey"] if isinstance(k,dict) else k for k in tx["transaction"]["message"]["accountKeys"]]
    preT={b["accountIndex"]:int(b["uiTokenAmount"]["amount"]) for b in m.get("preTokenBalances",[]) if b["mint"]==mint and b.get("owner")==curve}
    postT={b["accountIndex"]:int(b["uiTokenAmount"]["amount"]) for b in m.get("postTokenBalances",[]) if b["mint"]==mint and b.get("owner")==curve}
    idxs=set(preT)|set(postT)
    ctok=sum(postT.get(i,0)-preT.get(i,0) for i in idxs)
    csol=0
    for i,k in enumerate(keys):
        if k==curve: csol=m["postBalances"][i]-m["preBalances"][i]; break
    if ctok==0 or csol==0: return None
    return abs(csol)/abs(ctok)
def all_sigs_window(addr,lo,hi):
    out=[];before=None;cap=1200
    while True:
        page=rpc.getsigs(addr,before=before,limit=1000)
        if not page: break
        for s in page:
            if s["slot"]<=hi: out.append(s)
        before=page[-1]["signature"]
        if page[-1]["slot"]<lo: break
        if len(out)>cap: break
    return [s for s in out if lo<=s["slot"]<=hi]
lock=threading.Lock();done=[0]
def work(r):
    mint=r["mint"]; curve=res[mint]["curve"]; bslot=r["bslot"]
    last=bslot+(r["last_dslot"] or 0)
    hi=last
    try:
        sigs=all_sigs_window(curve,bslot,hi)
        pts=[]
        for s in sigs:
            if s.get("err"): continue
            tx=rpc.gettx(s["signature"])
            if not tx: continue
            px=curve_px(tx,mint,curve)
            if px: pts.append((tx["slot"],px))
        pts.sort()
        out=dict(mint=mint,npts=len(pts),pts=pts)
    except Exception as e:
        out=dict(mint=mint,error=str(e))
    with lock:
        done[0]+=1
        if done[0]%25==0: print("done",done[0],flush=True)
    return out
t0=time.time()
paths={}
with cf.ThreadPoolExecutor(max_workers=16) as ex:
    futs=[ex.submit(work,r) for r in rows]
    for f in cf.as_completed(futs):
        o=f.result(); paths[o["mint"]]=o
json.dump(paths,open("paths.json","w"))
errs=[o for o in paths.values() if o.get("error")]
print("done",len(paths),"errs",len(errs),"elapsed",round(time.time()-t0,1))
tot=sum(o.get("npts",0) for o in paths.values()); print("total curve pts",tot)

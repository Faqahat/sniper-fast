#!/usr/bin/env python3
"""build_label.py <mints.json> <out.json>  -- mints.json = list of mint strings OR list of
{mint:...}. For each: find pump create_v2 (oldest mint sig), parse_create (entry_px, features),
reconstruct create-slot trajectory, apply baseline exit ladder -> flip net R / win. Same label
and feature extraction as the unbiased population. Threaded + resumable."""
import sys,os,json,threading
from concurrent.futures import ThreadPoolExecutor,as_completed
sys.path.insert(0,"/root/profit_backtest"); import common as C
sys.path.insert(0,"/root/selection_study")
import backtest_shim as BS   # provides simulate + BASE_EXIT
INP,OUT=sys.argv[1],sys.argv[2]
raw=json.load(open(INP))
mints=[(m if isinstance(m,str) else m["mint"]) for m in raw]
mints=list(dict.fromkeys(mints))
done={}
if os.path.exists(OUT):
    try: done={r["mint"]:r for r in json.load(open(OUT))}
    except: done={}
todo=[m for m in mints if m not in done]
print(f"mints={len(mints)} done={len(done)} todo={len(todo)}",flush=True)
CREATE_V2=C.CREATE_V2; CREATE=C.CREATE; PUMP=C.PUMP_B58
def find_create_tx(mint,maxpages=16):
    out=[];before=None;pages=0
    while pages<maxpages:
        pr=[mint,{"limit":1000}]
        if before: pr[1]["before"]=before
        r=C.rpc("getSignaturesForAddress",pr)
        if not r: break
        out+=r; pages+=1
        if len(r)<1000: break
        before=r[-1]["signature"]
    if not out: return None
    min_slot=min(s["slot"] for s in out)
    for s in [x for x in out if x["slot"]==min_slot and not x.get("err")]:
        tx=C.gettx(s["signature"])
        if not tx or not tx.get("transaction"): continue
        msg=tx["transaction"]["message"]
        for ix in msg.get("instructions",[]):
            if ix.get("programId")!=PUMP: continue
            if C.b58dec(ix.get("data",""))[:8].hex() in (CREATE_V2,CREATE): return tx
    return None
def work(mint):
    tx=find_create_tx(mint)
    if tx is None: return {"mint":mint,"ok":False,"why":"no_create"}
    pc=C.parse_create(tx)
    if not pc: return {"mint":mint,"ok":False,"why":"parse_fail"}
    cs=pc["create_slot"]
    tr=C.trajectory(mint,cs)
    ser=tr["series"]
    epx=pc.get("entry_px")
    if not epx or not tr["reached_floor"]:
        epx=ser[0][2] if ser else None
    if not epx: return {"mint":mint,"ok":False,"why":"no_entry_px","create_slot":cs,
                        "dev_buy":pc["dev_buy"],"creator":pc["creator"]}
    series=[(s,p) for (s,_b,p) in ser]
    net,gross,legs=BS.simulate(epx,cs,series,BS.BASE_EXIT)
    peak=max([p/epx for (s,p) in series],default=1.0)
    return {"mint":mint,"ok":True,"create_slot":cs,"entry_px":epx,"dev_buy":pc["dev_buy"],
            "dev_buy_wire":pc["dev_buy_wire"],"creator":pc["creator"],"creator_fee_bps":pc["creator_fee_bps"],
            "mayhem":pc["mayhem"],"holder_reward":pc["holder_reward"],"cashback":pc["cashback"],
            "cosnipers":tr["cosnipers_slot0"],"n_trades":len(ser),"reached":tr["reached_floor"],
            "net":net,"win":net>0,"peak":peak}
res=list(done.values()); lock=threading.Lock(); cnt=0
with ThreadPoolExecutor(max_workers=20) as ex:
    futs={ex.submit(work,m):m for m in todo}
    for fu in as_completed(futs):
        r=fu.result()
        with lock:
            res.append(r); cnt+=1
            if cnt%50==0:
                json.dump(res,open(OUT,"w")); print(f"  {cnt}/{len(todo)} ok={sum(1 for x in res if x.get(chr(111)+chr(107)))}",flush=True)
json.dump(res,open(OUT,"w"))
ok=[r for r in res if r.get("ok")]
w=sum(1 for r in ok if r["win"])
print(f"DONE {len(res)} ok={len(ok)} flip_win={w}/{len(ok)}={w/max(1,len(ok))*100:.1f}% -> {OUT}",flush=True)

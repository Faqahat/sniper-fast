import rpc, json, sys, concurrent.futures as cf, threading
from enrich import parse_block_buys, W

pos=json.load(open("/root/last30/positions.json"))["positions"]
enr={x["mint"]:x for x in json.load(open("/root/last30/enriched.json"))}

lock=threading.Lock(); done=[0]
def work(p):
    mint=p["mint"]; buy_slot=p["slot"]
    e=enr.get(mint,{})
    cslot=e.get("create_slot")
    out={"mint":mint}
    try:
        slots=sorted(set([s for s in [cslot,buy_slot] if s]))
        rows=[]
        dev_signer=None; vanilla=None
        for sl in slots:
            br=parse_block_buys(sl,mint) or []
            for x in br: x["slot"]=sl
            # dev signer = create tx signer (prefer create slot)
            cre=[x for x in br if x["iscre"]]
            if cre and dev_signer is None:
                dev_signer=cre[0]["signer"]; vanilla=cre[0].get("vanilla")
            rows+=br
        out["vanilla"]=vanilla
        buys=[x for x in rows if x["isbuy"] and x["ok"]]
        buys.sort(key=lambda x:(x["slot"],x["idx"]))
        ext=[x for x in buys if x["signer"]!=dev_signer]
        def px(x):
            if x["tok_in"]>0 and x["csol"]!=0: return abs(x["csol"])/abs(x["tok_in"])
            return None
        floor=None
        for x in ext:
            p0=px(x)
            if p0: floor=p0; break
        his=[i for i,x in enumerate(ext) if x["signer"]==W]
        out["n_ext_buys_cumulative"]=len(ext)
        out["dev_signer"]=dev_signer
        if his:
            hi=his[0]; hp=px(ext[hi])
            out["his_rank_xslot"]=hi+1
            out["his_px"]=hp; out["floor_px"]=floor
            out["fill_ratio_xslot"]=(hp/floor) if (hp and floor) else None
            out["his_slot"]=ext[hi]["slot"]; out["his_blkidx"]=ext[hi]["idx"]
        else:
            out["his_rank_xslot"]=None; out["fill_ratio_xslot"]=None
            out["his_px"]=None; out["floor_px"]=floor
    except Exception as ex:
        import traceback
        out["error"]=repr(ex); out["tb"]=traceback.format_exc()[-300:]
    with lock:
        done[0]+=1
        print("done",done[0],mint[:8],"rank",out.get("his_rank_xslot"),"ratio",out.get("fill_ratio_xslot"),file=sys.stderr)
    return out

res=[None]*len(pos)
with cf.ThreadPoolExecutor(max_workers=4) as ex:
    futs={ex.submit(work,p):i for i,p in enumerate(pos)}
    for f in cf.as_completed(futs):
        res[futs[f]]=f.result()
json.dump(res,open("/root/last30/fill2.json","w"),indent=1)
print("errs",len([x for x in res if x.get("error")]),file=sys.stderr)

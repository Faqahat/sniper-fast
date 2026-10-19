#!/usr/bin/env python3
import sys, json, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,"/root/create_cu_reval"); import reval_classify as R
sys.path.insert(0,"/root/econ_102"); import econ102 as E

T=json.load(open("/root/create_cu_reval/fresh_traj.json"))
cand=[r for r in T if r.get("n") and r.get("entry_px") and r["dev_buy_wire_sol"]>=2.0 and r["creator_fee_bps"]==0]
print(f"fresh candidates: {len(cand)}",flush=True)
t0=time.time(); out=[]; errs={}
def work(r):
    pc=R.parse_create_in_block(r["create_slot"], r["mint"])
    if pc.get("error"): return {"error":pc["error"]}
    if pc["creator_fee_bps"]!=0: return {"error":"fee!=0"}
    entry=r["entry_px"]*E.ENTRY_MULT
    net,_,_=E.simulate(entry,r["create_slot"],[(s,p) for s,p in r["series"]],E.SHIP,0.5)
    gnet=E.gross_only(entry,r["create_slot"],[(s,p) for s,p in r["series"]],E.SHIP)
    return {"mint":r["mint"],"slot":r["create_slot"],"net":net,"gross":gnet,
            "create_cu":pc["create_cu_price"],"dev_buy":pc["dev_buy"],
            "dev_buy_wire":r["dev_buy_wire_sol"],"cosnip":r["cosnipers"]}
with ThreadPoolExecutor(max_workers=16) as ex:
    for i,r in enumerate(ex.map(work,cand),1):
        if r.get("error"): errs[r["error"]]=errs.get(r["error"],0)+1
        else: out.append(r)
json.dump(out,open("/root/create_cu_reval/fresh_feat.json","w"),indent=0)
ss=[r["slot"] for r in out]
print(f"DONE kept={len(out)} errs={errs} {time.time()-t0:.0f}s slot {min(ss)}..{max(ss)}",flush=True)

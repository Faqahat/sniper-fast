import os, sys, json, time
sys.path.insert(0,"/root/tmp_creator")
from analyze import rpc, CREATOR

allsigs=[]
before=None
for page in range(8):
    params=[CREATOR,{"limit":1000}]
    if before: params[1]["before"]=before
    res=rpc("getSignaturesForAddress",params)
    if not res: break
    allsigs.extend(res)
    before=res[-1]["signature"]
    if len(res)<1000: break
with open("/root/tmp_creator/sigs.json","w") as f:
    json.dump(allsigs,f)
print("total sigs:", len(allsigs))
if allsigs:
    t0=allsigs[0].get("blockTime"); t1=allsigs[-1].get("blockTime")
    import datetime
    print("newest:", datetime.datetime.utcfromtimestamp(t0) if t0 else None)
    print("oldest:", datetime.datetime.utcfromtimestamp(t1) if t1 else None)
    errs=sum(1 for s in allsigs if s.get("err"))
    print("with err:", errs)

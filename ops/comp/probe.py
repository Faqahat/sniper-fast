import json,sys,time
sys.path.insert(0,"/root/indep")
from common import rpc
BOT = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}
rows=[]
for l in open("/root/race/fresh2_onchain.jsonl"):
    r=json.loads(l); b=r.get("b") or {}
    if "dev" not in b: continue
    if 2.95<=b.get("gsol",0)/1e9<=5.05 and any(str(x[2]).startswith("moon") for x in b.get("tips",[])):
        rows.append(r)
for r in rows[:4]:
    b=r["b"]; t0=time.time(); allsig=[]; before=None; pages=0
    while True:
        p={"limit":1000,"until":b["csig"]}
        if before: p["before"]=before
        x=rpc("getSignaturesForAddress",[r["mint"],p]); pages+=1
        if not isinstance(x,list) or not x: break
        allsig+=x; before=x[-1]["signature"]
        if len(x)<1000: break
    S=b["slot"]
    n150=sum(1 for s in allsig if s["slot"]<=S+150); n300=sum(1 for s in allsig if s["slot"]<=S+300)
    ok150=sum(1 for s in allsig if s["slot"]<=S+150 and s["err"] is None)
    print(r["mint"][:8],"total",len(allsig),"pages",pages,"<=S+150",n150,"ok",ok150,"<=S+300",n300,"dt %.1f"%(time.time()-t0), "later in S", b["nlater"])

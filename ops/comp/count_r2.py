import json,glob,sys
BOT = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}
seen={}
for fn in sorted(glob.glob("/root/race/*_onchain.jsonl"))+glob.glob("/root/race/s1.jsonl"):
    n=r2=c2=0
    for l in open(fn):
        try: r=json.loads(l)
        except: continue
        b=r.get("b") or {}
        if not b or "dev" not in b: continue
        n+=1
        host=(b.get("uri") or "").split("://")[-1].split("/")[0]
        dev=b["dev"]/1e9; gs=b.get("gsol",0)/1e9
        moon=any(str(x[2]).startswith("moon") for x in b.get("tips",[]))
        base= 0.49<=dev<=8.1 and not (host in BOT or host.endswith(".trycloudflare.com")) and "CreateV2" in (b.get("ins") or [])
        isr2= base and 2.95<=gs<=5.05 and moon
        isc= base and gs>=2
        if isr2: r2+=1
        if isc: c2+=1
        seen.setdefault(r["mint"],(fn,b.get("bt"),isr2,isc,r.get("slot")))
    print(fn,n,"r2",r2,"contested",c2)
v=list(seen.values())
print("unique",len(v),"r2",sum(x[2] for x in v),"contested",sum(x[3] for x in v))
import time
bts=[x[1] for x in v if x[1]]
print(time.strftime("%m-%d %H:%M",time.gmtime(min(bts))),time.strftime("%m-%d %H:%M",time.gmtime(max(bts))))

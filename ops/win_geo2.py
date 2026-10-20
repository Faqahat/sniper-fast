import json, urllib.request, os, subprocess, statistics, time, re, random
from concurrent.futures import ThreadPoolExecutor
TOK=os.environ["CONSTANTK_TOKEN"]; RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for _ in range(3):
        try: return json.load(urllib.request.urlopen(req,timeout=20)).get("result")
        except: time.sleep(0.3)
    return None
m2s={}
for lg in ["paper_collect.log","paper_newcfg.log"]:
    try:
        for ln in open("/root/sniper-fast/"+lg):
            mo=re.search(r"slot=(\d+) mint=([1-9A-HJ-NP-Za-km-z]+)",ln)
            if mo: m2s.setdefault(mo.group(2),int(mo.group(1)))
    except: pass
wins=[]; losers=[]
for ln in open("/root/gs_clean/paths.jsonl"):
    try: d=json.loads(ln)
    except: continue
    if not isinstance(d,dict): continue
    mint=d.get("mint"); peak=d.get("peak",1.0); path=d.get("path")
    if mint not in m2s: continue
    if isinstance(path,list) and path and path[0][1]>=2.0: continue
    (wins if peak>=2.0 else losers).append((mint,m2s[mint]))
print(f"joined wins={len(wins)} losers={len(losers)}",flush=True)
random.seed(1); random.shuffle(wins); random.shuffle(losers)
wins=wins[:150]; losers=losers[:150]
nodes=rpc("getClusterNodes",[]) or []
ip_of={n["pubkey"]:(n.get("gossip") or n.get("tpu") or "").split(":")[0] for n in nodes}
# resolve leaders (parallel RPC)
slots=list({s for _,s in wins+losers})
def getld(s):
    r=rpc("getSlotLeaders",[s,1]); return (s, r[0] if r else None)
ldr=dict(ThreadPoolExecutor(20).map(getld, slots))
ips=list({ip_of.get(ldr.get(s)) for _,s in wins+losers if ip_of.get(ldr.get(s))})
def png(ip):
    try:
        out=subprocess.run(["ping","-c","2","-W","1",ip],capture_output=True,text=True,timeout=4).stdout
        for l in out.splitlines():
            if "/" in l and ("avg" in l or "round-trip" in l): return (ip,float(l.split("=")[1].strip().split("/")[1]))
    except: pass
    return (ip,None)
rtt=dict(ThreadPoolExecutor(40).map(png, ips))
def rep(rows,tag):
    rts=[rtt.get(ip_of.get(ldr.get(s))) for _,s in rows]; rts=[r for r in rts if r is not None]
    if not rts: print(f"{tag}: no rtt"); return
    close=sum(1 for r in rts if r<20); far=sum(1 for r in rts if r>50)
    print(f"{tag}: n={len(rows)} resolved={len(rts)} medianRTT={statistics.median(rts):.1f}ms CLOSE(<20ms)={100*close/len(rts):.0f}% FAR(>50ms)={100*far/len(rts):.0f}%",flush=True)
rep(wins,"WINS (peak>=2 runners)")
rep(losers,"LOSERS (peak<2)")

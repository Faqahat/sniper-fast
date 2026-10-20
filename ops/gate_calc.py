import json, urllib.request, os, subprocess, time
from concurrent.futures import ThreadPoolExecutor
TOK=os.environ["CONSTANTK_TOKEN"]; RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for _ in range(3):
        try: return json.load(urllib.request.urlopen(req,timeout=20)).get("result")
        except: time.sleep(0.3)
    return None
shots=[json.loads(l) for l in open("/root/sniper-fast/shots.jsonl") if l.strip()]
nodes=rpc("getClusterNodes",[]) or []
ip_of={n["pubkey"]:(n.get("gossip") or n.get("tpu") or "").split(":")[0] for n in nodes}
slots=list({s["create"] for s in shots})
ldr=dict(ThreadPoolExecutor(20).map(lambda s:(s,(rpc("getSlotLeaders",[s,1]) or [None])[0]), slots))
ips=list({ip_of.get(ldr.get(s["create"])) for s in shots if ip_of.get(ldr.get(s["create"]))})
def png(ip):
    try:
        o=subprocess.run(["ping","-c","2","-W","1",ip],capture_output=True,text=True,timeout=4).stdout
        for l in o.splitlines():
            if "/" in l and ("avg" in l or "round-trip" in l): return (ip,float(l.split("=")[1].strip().split("/")[1]))
    except: pass
    return (ip,None)
rtt=dict(ThreadPoolExecutor(40).map(png,ips))
def band(s):
    r=rtt.get(ip_of.get(ldr.get(s["create"])))
    return r
for lo,hi,tag in [(0,20,"CLOSE(<20ms)"),(20,50,"MID(20-50)"),(50,1e9,"FAR(>50ms)"),(0,1e9,"ALL")]:
    sel=[s for s in shots if (r:=band(s)) is not None and lo<=r<hi]
    if not sel: print(f"{tag}: n=0"); continue
    d0=sum(1 for s in sel if s["delta"]<=0)
    print(f"{tag}: n={len(sel)} same-slot(delta<=0)={100*d0/len(sel):.0f}%  +1orMore={100*(len(sel)-d0)/len(sel):.0f}%")
# what fraction of all fires are close (= how many we'd still fire on with the gate)
res=[s for s in shots if band(s) is not None]
closen=sum(1 for s in res if band(s)<20)
print(f"\nGATE KEEPS {closen}/{len(res)} = {100*closen/len(res):.0f}% of launches (close-leader only)")

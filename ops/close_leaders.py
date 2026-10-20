import json, urllib.request, os, subprocess, time
from concurrent.futures import ThreadPoolExecutor
TOK=os.environ["CONSTANTK_TOKEN"]; RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
nodes=rpc("getClusterNodes",[]) or []
pk_ip=[(n["pubkey"],(n.get("gossip") or n.get("tpu") or "").split(":")[0]) for n in nodes if (n.get("gossip") or n.get("tpu"))]
print(f"cluster nodes with ip: {len(pk_ip)}",flush=True)
THRESH=float(os.environ.get("CLOSE_MS","20"))
def png(pk_ip):
    pk,ip=pk_ip
    try:
        o=subprocess.run(["ping","-c","2","-W","1",ip],capture_output=True,text=True,timeout=4).stdout
        for l in o.splitlines():
            if "/" in l and ("avg" in l or "round-trip" in l):
                return (pk, float(l.split("=")[1].strip().split("/")[1]))
    except: pass
    return (pk, None)
res=list(ThreadPoolExecutor(80).map(png, pk_ip))
close=[pk for pk,r in res if r is not None and r<THRESH]
resolved=[r for pk,r in res if r is not None]
with open("/root/sniper-fast/close_leaders.txt","w") as f:
    f.write("\n".join(close)+"\n")
print(f"pinged={len(res)} resolved={len(resolved)} CLOSE(<{THRESH}ms)={len(close)} -> close_leaders.txt",flush=True)

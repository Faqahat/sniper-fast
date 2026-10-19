import json, urllib.request, os, subprocess, statistics, time
TOK=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for _ in range(3):
        try: return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
        except: time.sleep(0.4)
    return None
shots=[json.loads(l) for l in open("/root/arbx-fast/shots.jsonl") if l.strip()]
print(f"shots={len(shots)}  delta hist:", {d:sum(1 for s in shots if s['delta']==d) for d in sorted(set(s['delta'] for s in shots))})
nodes=rpc("getClusterNodes",[]) or []
ip_of={}
for n in nodes:
    ip=(n.get("gossip") or n.get("tpu") or "")
    ip_of[n["pubkey"]]= ip.split(":")[0] if ip else None
# leader per unique create slot
uniq=sorted(set(s["create"] for s in shots))
leader={}
for c in uniq:
    r=rpc("getSlotLeaders",[c,1]); leader[c]=r[0] if r else None
rttc={}
def rtt(ip):
    if not ip: return None
    if ip in rttc: return rttc[ip]
    try:
        out=subprocess.run(["ping","-c","3","-W","1",ip],capture_output=True,text=True,timeout=7).stdout
        for ln in out.splitlines():
            if "/" in ln and ("min/avg" in ln or "rtt" in ln or "round-trip" in ln):
                rttc[ip]=float(ln.split("=")[1].strip().split("/")[1]); return rttc[ip]
    except: pass
    rttc[ip]=None; return None
rows=[]
for s in shots:
    lead=leader.get(s["create"]); ip=ip_of.get(lead); r=rtt(ip)
    rows.append((s["delta"], s["poh"], lead[:6] if lead else "?", ip, r))
def summ(tag, sel):
    rs=[r for d,p,l,ip,r in rows if sel(d) and r is not None]
    pohs=[p for d,p,l,ip,r in rows if sel(d) and p>=0]
    n=sum(1 for d,p,l,ip,r in rows if sel(d))
    res=f"{tag}: n={n} rtt_resolved={len(rs)}"
    if rs: res+=f" rtt_ms median={statistics.median(rs):.1f} min={min(rs):.1f} max={max(rs):.1f}"
    if pohs: res+=f" | poh median={statistics.median(pohs):.0f}"
    return res
print(summ("SAME-SLOT (delta<=0)", lambda d:d<=0))
print(summ("LATE +1/more (delta>=1)", lambda d:d>=1))
print("\nper-shot (delta, poh, leader, ip, rtt_ms):")
for r in sorted(rows): print(f"  d={r[0]:+d} poh={r[1]:6.0f} {r[2]:7} {str(r[3]):16} rtt={r[4]}")

import json, urllib.request, os, subprocess, statistics, time, re, glob
TOK=os.environ["CONSTANTK_TOKEN"]; RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for _ in range(3):
        try: return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
        except: time.sleep(0.4)
    return None
# mint -> slot from logs
m2s={}
for lg in ["paper_collect.log","paper_newcfg.log"]:
    try:
        for ln in open("/root/arbx-fast/"+lg):
            mo=re.search(r"slot=(\d+) mint=([1-9A-HJ-NP-Za-km-z]+)",ln)
            if mo: m2s.setdefault(mo.group(2),int(mo.group(1)))
    except: pass
# mint -> peak from clean paths; "win" = peak>=2 (would-be runner we profit on at floor)
wins=[]; losers=[]
for ln in open("/root/gs_clean/paths.jsonl"):
    try: d=json.loads(ln)
    except: continue
    if not isinstance(d,dict): continue
    mint=d.get("mint"); peak=d.get("peak",1.0); path=d.get("path")
    if mint not in m2s: continue
    if isinstance(path,list) and path and path[0][1]>=2.0: continue  # misread
    (wins if peak>=2.0 else losers).append((mint,m2s[mint],peak))
print(f"joined: wins(peak>=2)={len(wins)} losers={len(losers)}")
# leaders + IPs
nodes=rpc("getClusterNodes",[]) or []
ip_of={n["pubkey"]:(n.get("gossip") or n.get("tpu") or "").split(":")[0] for n in nodes}
ldr={}
def leader(slot):
    if slot in ldr: return ldr[slot]
    r=rpc("getSlotLeaders",[slot,1]); ldr[slot]=r[0] if r else None; return ldr[slot]
rttc={}
def rtt(ip):
    if not ip: return None
    if ip in rttc: return rttc[ip]
    try:
        out=subprocess.run(["ping","-c","2","-W","1",ip],capture_output=True,text=True,timeout=5).stdout
        for l in out.splitlines():
            if "/" in l and ("avg" in l or "round-trip" in l): rttc[ip]=float(l.split("=")[1].strip().split("/")[1]); return rttc[ip]
    except: pass
    rttc[ip]=None; return None
import random
def analyze(rows, tag, cap=250):
    random.shuffle(rows); rows=rows[:cap]
    rts=[]
    for mint,slot,peak in rows:
        r=rtt(ip_of.get(leader(slot))); 
        if r is not None: rts.append(r)
    if not rts: print(f"{tag}: no rtt"); return
    close=sum(1 for r in rts if r<20); far=sum(1 for r in rts if r>50)
    print(f"{tag}: n={len(rows)} rtt_resolved={len(rts)} median={statistics.median(rts):.1f}ms  CLOSE(<20ms)={100*close/len(rts):.0f}%  FAR(>50ms)={100*far/len(rts):.0f}%")
analyze(wins,"WINS (peak>=2, the runners)")
analyze(losers,"LOSERS (peak<2)")

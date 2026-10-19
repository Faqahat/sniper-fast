import re, json
from collections import Counter
LOG="/root/arbx-fast/paper_blacklist.log"
launches={}; done={}; order=0
for ln in open(LOG):
    m=re.search(r"PAPER launch #(\d+) slot=(\d+) mint=(\w+) dev_buy=(\d+)(?:\s+vanilla=(\w+))?", ln)
    if m:
        order+=1
        launches[m.group(3)]={"launch_no":int(m.group(1)),"slot":int(m.group(2)),"dev":int(m.group(4)),"vanilla":(m.group(5)=="true"),"order":order}
        continue
    m=re.search(r"PAPER done mint=(\w+) entry=([0-9.eE\-]+) fill=([0-9.]+)x peak_r=([0-9.]+) legs=(\d+) pnl_R=([+\-0-9.]+) pnl_NET @1\.00=([+\-0-9.]+)", ln)
    if m:
        done[m.group(1)]={"entry":float(m.group(2)),"fill":float(m.group(3)),"peak":float(m.group(4)),"legs":int(m.group(5)),"pnlR":float(m.group(6)),"floor":float(m.group(7))}
rows=[]
for mint,L in launches.items():
    if mint not in done: continue
    D=done[mint]
    peak,floor=D["peak"],D["floor"]
    if peak>=1.5: lab="WIN"
    elif peak<1.3 and floor<=0.05: lab="LOSE"
    else: lab="MID"
    rows.append({"mint":mint,"slot":L["slot"],"order":L["order"],"launch_no":L["launch_no"],"dev":L["dev"],"dev_sol":L["dev"]/1e9,"vanilla":L["vanilla"],"peak":peak,"floor":floor,"pnlR":D["pnlR"],"legs":D["legs"],"entry":D["entry"],"fill":D["fill"],"label":lab})
rows.sort(key=lambda r:r["slot"])
json.dump(rows,open("/root/sep2/labels.json","w"),indent=0)
c=Counter(r["label"] for r in rows)
print("TOTAL launches=%d  with-done=%d  no-done=%d"%(len(launches),len(rows),len(launches)-len(rows)))
print("LABELS:",dict(c))
nod=[m for m in launches if m not in done]
print("no-done mints:",len(nod))

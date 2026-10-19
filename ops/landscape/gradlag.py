#!/usr/bin/env python3
import json,statistics,threading
import importlib.util
spec=importlib.util.spec_from_file_location("gp","/root/landscape/gradpath.py")
# reuse funcs by exec of needed parts: simpler to re-import path/find_vault/ladder via exec
ns={}
src=open("/root/landscape/gradpath.py").read().split("grads=json.load")[0]
exec(src,ns)
find_vault=ns["find_vault"]; path=ns["path"]; ladder=ns["ladder"]
grads=json.load(open("/root/landscape/grads.json"))[-70:]
paths={};lock=threading.Lock()
def work(g):
    v=find_vault(g["sig"],g["mint"])
    if not v: return
    s=path(v,g["mint"],g["slot"])
    with lock: paths[g["mint"]]=s
ths=[]
for g in grads:
    t=threading.Thread(target=work,args=(g,));t.start();ths.append(t)
    if len(ths)>=12:
        for t in ths:t.join()
        ths=[]
for t in ths:t.join()
print("paths:",len(paths))
for K in [0,1,2,3,5]:
    Rs=[]
    for m,s in paths.items():
        if len(s)<K+2: continue
        entry=s[K][1]; fwd=s[K+1:]
        Rs.append(ladder(entry,fwd))
    if not Rs: continue
    Rs.sort();n=len(Rs)
    ex2=statistics.mean(Rs[:-2]) if n>2 else 0
    print("Kentry=%d n=%d mean=%+.4f med=%+.4f win=%.0f%% meanEx2=%+.4f tot=%+.2f"%(K,n,statistics.mean(Rs),statistics.median(Rs),100*sum(1 for r in Rs if r>0)/n,ex2,sum(Rs)))

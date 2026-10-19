import sys, json, time, bisect
sys.path.insert(0,"/root/strat")
import srpc
srpc.SEM = __import__("threading").Semaphore(1)
from srpc import rpc
anc=[]
for l in open("/root/nob/csigs.jsonl"):
    x=json.loads(l); anc.append((x["slot"],x["signature"]))
anc.sort(); asl=[a[0] for a in anc]
rows=[json.loads(l) for l in open("/root/nob/ds.jsonl")]
for x in rows[:400:100]:
    S=x["slot"]; i=bisect.bisect_left(asl,S+2782)
    t=time.time(); r=rpc("getSignaturesForAddress",[x["mint"],{"limit":1000,"before":anc[i][1]}],tries=1,timeout=30)
    print(S, time.time()-t, len(r) if isinstance(r,list) else r)
    t=time.time(); r=rpc("getSignaturesForAddress",[x["mint"],{"limit":1000}],tries=1,timeout=30)
    print(" nobefore", time.time()-t, len(r) if isinstance(r,list) else r, r[-1]["slot"]-S if isinstance(r,list) and r else None)

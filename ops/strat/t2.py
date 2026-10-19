import sys, json, time, bisect
sys.path.insert(0,"/root/strat")
from srpc import rpc
anc=[]
for l in open("/root/nob/csigs.jsonl"):
    x=json.loads(l); anc.append((x["slot"],x["signature"]))
anc.sort(); asl=[a[0] for a in anc]
lo,hi=0,len(anc)-1
def ok(i):
    r=rpc("getTransaction",[anc[i][1],{"encoding":"json","maxSupportedTransactionVersion":1}],tries=2,timeout=30)
    return isinstance(r,dict) and "meta" in r
print(ok(lo), ok(hi))
while hi-lo>200:
    m=(lo+hi)//2
    if ok(m): hi=m
    else: lo=m
print("boundary slot", anc[hi][0])

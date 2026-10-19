import rpc,json,concurrent.futures as cf,threading,time
# override gettx to support versioned txs
def gettx2(sig):
    return rpc.call("getTransaction",[sig,{"maxSupportedTransactionVersion":1,"encoding":"jsonParsed","commitment":"confirmed"}])
rpc.gettx=gettx2
import pricepath as pp
pp.rpc.gettx=gettx2
paths=json.load(open("paths.json"))
rows=json.load(open("rows.json"))
rowmap={r["mint"]:r for r in rows}
todo=[rowmap[m] for m,o in paths.items() if o.get("error")]
print("redo",len(todo))
lock=threading.Lock();done=[0]
def work(r):
    o=pp.work(r); 
    return o
with cf.ThreadPoolExecutor(max_workers=12) as ex:
    futs=[ex.submit(work,r) for r in todo]
    for f in cf.as_completed(futs):
        o=f.result(); paths[o["mint"]]=o
json.dump(paths,open("paths.json","w"))
errs=[o for o in paths.values() if o.get("error")]
print("errs now",len(errs))
tot=sum(o.get("npts",0) for o in paths.values()); print("total pts",tot)
for e in errs[:5]: print(e["mint"][:10],e["error"][:70])

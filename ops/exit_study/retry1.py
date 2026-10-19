import rpc,json
from collect_trades import work,snipes
res=json.load(open("trades.json"))
for i,r in enumerate(res):
    if r.get("error"):
        d=next(d for d in snipes if d["mint"]==r["mint"])
        print("retry",r["mint"][:10])
        res[i]=work(d)
json.dump(res,open("trades.json","w"))
print("errors now",sum(1 for r in res if r.get("error")))

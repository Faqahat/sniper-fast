import sys,json
sys.path.insert(0,"/root/profit_backtest"); import common as C
sys.path.insert(0,"/root/econ_102"); import econ102 as E
from concurrent.futures import ThreadPoolExecutor
raw=json.load(open("/root/attempt_filter/attempted_feat.json"))
att=[r for r in raw if r.get("create_found") and r.get("create_slot")]
print("building trajectories for",len(att),"attempted mints",flush=True)
def work(c):
    try:
        t=C.trajectory(c["mint"],c["create_slot"])
    except Exception as e:
        return (c["mint"],None)
    return (c["mint"],t)
res={}
with ThreadPoolExecutor(max_workers=16) as ex:
    for i,(m,t) in enumerate(ex.map(work,att)):
        res[m]=t
        if (i+1)%40==0: print("  ",i+1,flush=True)
# compute econ outcome per mint (shipped ladder, SIZE=0.5)
out=[]
for c in att:
    t=res.get(c["mint"])
    rec={k:c.get(k) for k in ("mint","creator","dev_buy","create_slot","n_buys","n_landed","create_cu_price","mayhem","holder_reward","cashback","creator_fee_bps")}
    if t and t.get("entry_px"):
        floor=t["entry_px"]; entry=floor*E.ENTRY_MULT
        series=[(s,p) for s,p in t["series"]]
        net,gross,legs=E.simulate(entry,t["create_slot"],series,E.SHIP,SIZE=0.5)
        g=E.gross_only(entry,t["create_slot"],series,E.SHIP)
        rec.update({"net_R":net,"gross_R":g,"cosnipers":t.get("cosnipers"),"peak_r":max([p/floor for s,p in series],default=1.0)})
    else:
        rec.update({"net_R":None,"gross_R":None})
    out.append(rec)
json.dump(out,open("/root/attempt_filter/att_outcomes.json","w"),indent=0)
hav=[r for r in out if r.get("net_R") is not None]
print(f"done: {len(hav)}/{len(out)} with outcome -> att_outcomes.json",flush=True)

import sys,json
sys.path.insert(0,"/root/profit_backtest"); import common as C
sys.path.insert(0,"/root/econ_102"); import econ102 as E
from concurrent.futures import ThreadPoolExecutor
raw=json.load(open("/root/attempt_filter/attempted_feat.json"))
att=[r for r in raw if r.get("create_found") and r.get("create_slot")]
print("building trajectories for",len(att),flush=True)
def work(c):
    try: tr=C.trajectory(c["mint"],c["create_slot"])
    except Exception: return (c["mint"],None)
    return (c["mint"],tr)
res={}
with ThreadPoolExecutor(max_workers=24) as ex:
    for i,(m,tr) in enumerate(ex.map(work,att)):
        res[m]=tr
        if (i+1)%50==0: print("  ",i+1,flush=True)
out=[]
for c in att:
    tr=res.get(c["mint"])
    rec={k:c.get(k) for k in ("mint","creator","dev_buy","create_slot","n_buys","n_landed","create_cu_price","mayhem","holder_reward","cashback","creator_fee_bps")}
    epx=None; series=[]
    if tr and tr.get("series") is not None:
        series=[(s,p) for (s,_bt,p) in tr["series"]]
        epx=c.get("entry_px")
        if not epx or not tr.get("reached_floor"):
            if series: epx=series[0][1]
        rec["cosnipers"]=tr.get("cosnipers_slot0")
    if epx and series:
        entry=epx*E.ENTRY_MULT
        net,gross,legs=E.simulate(entry,c["create_slot"],series,E.SHIP,SIZE=0.5)
        g=E.gross_only(entry,c["create_slot"],series,E.SHIP)
        rec.update({"net_R":net,"gross_R":g,"peak_r":max([p/epx for s,p in series],default=1.0),"n_trades":len(series)})
    else:
        rec.update({"net_R":None,"gross_R":None,"n_trades":len(series)})
    out.append(rec)
json.dump(out,open("/root/attempt_filter/att_outcomes.json","w"),indent=0)
hav=[r for r in out if r.get("net_R") is not None]
print(f"done: {len(hav)}/{len(out)} with outcome",flush=True)

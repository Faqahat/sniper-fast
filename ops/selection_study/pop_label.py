#!/usr/bin/env python3
"""Label the unbiased population with the SAME flip outcome used by the backtest:
net R>0 under the baseline exit ladder on the create-slot-anchored series. Also attach
slot-0 features. Writes pop_labeled.json and prints anchor win-rates."""
import sys,json
sys.path.insert(0,"/root/profit_backtest")
import backtest as B
from backtest import simulate, passes, ROWS
BASE_EXIT={"derisk_frac":0.40,"ride_mult":1.6,"trail_frac":0.85,"cut_r":0.85,"ladder_frac":0.30,"cap_slots":20}
BASE_FILT={"dev_min":0.3,"dev_max":1e9,"vanilla":False}
# creator in-window launch frequency + ordered prior-outcome
CRE=B.CRE
REP={}
for c in CRE: REP[c["creator"]]=REP.get(c["creator"],0)+1
# label each ROW (row = create joined with traj)
def label(c):
    t=c["traj"]
    net,gross,legs=simulate(t["entry_px"],t["create_slot"],[(s,p) for s,p in t["series"]],BASE_EXIT)
    # peak r (descriptive)
    peak=max([p/t["entry_px"] for s,p in t["series"]],default=1.0)
    return net,(net>0),peak
rows=[]
for c in ROWS:
    net,win,peak=label(c)
    rows.append({**{k:c[k] for k in ("mint","creator","create_slot","dev_buy","dev_buy_wire",
        "creator_fee_bps","mayhem","holder_reward","cashback","is_v2")},
        "cosnipers":c["traj"]["cosnipers"],"n_trades":c["traj"]["n"],"reached":c["traj"]["reached_floor"],
        "net":net,"win":win,"peak":peak,"rep":REP.get(c["creator"],1),
        "pass":passes(c,BASE_FILT)})
json.dump(rows,open("/root/selection_study/pop_labeled.json","w"))
import statistics as st
def wr(sub): 
    n=len(sub); return (n, sum(1 for r in sub if r["win"])/n if n else 0, sum(r["net"] for r in sub)/n if n else 0)
allr=rows; passr=[r for r in rows if r["pass"]]
print("POPULATION ANCHORS (flip = net R>0 under baseline ladder, create-slot anchored)")
print(f" full pop:        n={wr(allr)[0]} win={wr(allr)[1]*100:.1f}% meanR={wr(allr)[2]:+.4f}")
print(f" filter-pass:     n={wr(passr)[0]} win={wr(passr)[1]*100:.1f}% meanR={wr(passr)[2]:+.4f}  (<-- the ~28% anchor)")

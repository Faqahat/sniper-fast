#!/usr/bin/env python3
"""Temporal OOS: paper-window mints (slots 456878173-456911074, DISJOINT & later than the 456604-456820
backtest window). Reconstruct our-fill entry + forward path, replay shipped + grid-best exits with
zero-cost (reproduce paper) vs realistic cost."""
import sys, os, json, statistics as st
sys.path.insert(0,"/root/profit_ourfill"); import ourfill as O
os.environ["SIZE"]="0.165"; O.SIZE=0.165

T=json.load(open("/root/profit_ourfill/paper_traj.json"))
# build feats; filter dev>=2 (wire) & our-fill from series
FEAT=[]
for r in T:
    if r["dev_buy_wire_lamports"]/1e9 < 2.0: continue
    if not r["n"] or not r.get("entry_px"): continue
    traj={"create_slot":r["create_slot"],"entry_px":r["entry_px"],"series":[(s,p) for s,p in r["series"]]}
    e,slot,path=O.ourfill_entry(traj)
    if not e: continue
    FEAT.append({"e":e,"slot":slot,"path":path,"vanilla":r["vanilla"],"co":r["cosnipers"]})
print(f"paper-window OOS feats (dev>=2, usable): n={len(FEAT)}")

SHIP={"derisk_frac":0.30,"ride_mult":1.40,"trail_frac":0.92,"cut_r":0.95,"ladder_frac":0.25,"cap_slots":40}
BEST={"derisk_frac":0.0,"ride_mult":1.2,"trail_frac":0.85,"cut_r":0.95,"ladder_frac":0.25,"cap_slots":10}
def run(sub,E,pump,impact):
    O.PUMP_FEE=pump; O.BASE_FEE=0.000005 if pump>0 else 0.0; O.IMPACT_K=impact
    return O.stats([O.simulate(x["e"],x["slot"],x["path"],E)[0] for x in sub])
def l(tag,S):
    print(f"  {tag:46s} n={S['n']:3d} mean={S['mean']:+.4f} med={S['median']:+.4f} win={S['win']*100:3.0f}% drop2={S['mean_drop2']:+.4f}")

van=[x for x in FEAT if x["vanilla"]]
print("\n--- shipped ladder ---")
l("ZERO cost (reproduce paper +0.0187)", run(FEAT,SHIP,0.0,0.0))
l("REALISTIC cost (pump1%+base+impact)", run(FEAT,SHIP,0.01,1.0))
print("\n--- grid-best config (derisk0,ride1.2,cap10) ---")
l("ZERO cost", run(FEAT,BEST,0.0,0.0))
l("REALISTIC cost", run(FEAT,BEST,0.01,1.0))
print("\n--- vanilla subset, realistic cost ---")
l("shipped", run(van,SHIP,0.01,1.0))
l("grid-best", run(van,BEST,0.01,1.0))

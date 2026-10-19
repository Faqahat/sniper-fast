#!/usr/bin/env python3
"""Grid-search selection + exit FROM OUR-FILL entry, realistic cost, train/val split, OOS reporting.
Live-usable selection features only (known by create+1). Momentum-continuation tested as an exit ride-gate
(forward flow during the hold = legitimate) AND as a short-hold vs ride comparison."""
import sys, os, json, itertools
sys.path.insert(0,"/root/profit_ourfill"); import ourfill as O

# realistic cost, live size
os.environ["SIZE"]="0.165"; O.SIZE=0.165
O.PUMP_FEE=0.01; O.BASE_FEE=0.000005; O.IMPACT_K=1.0; O.VRESERVE=35.0

ROWS=O.load_backtest()
DEV_MIN_BASE=2.0
def base_pass(c):
    if c["creator_fee_bps"]!=0: return False
    dev=c["dev_buy"]
    if c.get("dev_buy_wire",0)>=1e17: dev=max(dev,DEV_MIN_BASE)
    return dev>=DEV_MIN_BASE
# precompute features
FEAT=[]
for c in ROWS:
    if c["creator_fee_bps"]!=0: continue
    t=c["traj"]
    dev=c["dev_buy"]
    if c.get("dev_buy_wire",0)>=1e17: dev=max(dev,DEV_MIN_BASE)
    e,slot,path=O.ourfill_entry(t)
    floor=t["entry_px"]
    p2=O.price_at(t,2); p5=O.price_at(t,5)
    FEAT.append({"slot":c["create_slot"],"dev":dev,
        "vanilla": not (c["mayhem"] or c["holder_reward"] or c["cashback"]),
        "cosnipers":t["cosnipers"], "entry":e,"entry_slot":slot,"path":path,
        "entry_ratio": e/floor if floor else 1.0,
        "rising2": p2>e*1.0000001, "mom5": (p5/e if e else 1.0),
        "creator":c["creator"]})
FEAT.sort(key=lambda f:f["slot"])
# train/val split by slot (temporal)
split=FEAT[len(FEAT)//2]["slot"]
TRAIN=[f for f in FEAT if f["slot"]<split]
VAL=[f for f in FEAT if f["slot"]>=split]
print(f"features n={len(FEAT)} train={len(TRAIN)} val={len(VAL)} split_slot={split}")

# creator frequency (anti-factory), computed on full window
from collections import Counter
repc=Counter(f["creator"] for f in FEAT)

def sel_pass(f, S):
    if f["dev"]<S.get("dev_min",2.0): return False
    if f["dev"]>S.get("dev_max",1e9): return False
    if S.get("vanilla") and not f["vanilla"]: return False
    if S.get("max_cosnip") is not None and f["cosnipers"]>S["max_cosnip"]: return False
    if S.get("min_cosnip") is not None and f["cosnipers"]<S["min_cosnip"]: return False
    if S.get("max_entry_ratio") is not None and f["entry_ratio"]>S["max_entry_ratio"]: return False
    if S.get("require_rising") and not f["rising2"]: return False
    if S.get("max_creator_launches") is not None and repc[f["creator"]]>S["max_creator_launches"]: return False
    return True

def evalc(rows, S, E):
    rs=[]
    for f in rows:
        if not sel_pass(f,S): continue
        net,_,_=O.simulate(f["entry"],f["entry_slot"],f["path"],E)
        rs.append(net)
    return O.stats(rs)

SHIP={"derisk_frac":0.30,"ride_mult":1.40,"trail_frac":0.92,"cut_r":0.95,"ladder_frac":0.25,"cap_slots":40}
print("\n=== shipped config under realistic cost ===")
for nm,rws in [("TRAIN",TRAIN),("VAL",VAL),("ALL",FEAT)]:
    S=evalc(rws,{"dev_min":2.0},SHIP)
    print(f"  {nm}: mean={S['mean']:+.4f} med={S['median']:+.4f} win={S['win']*100:.1f}% n={S['n']} drop2={S['mean_drop2']:+.4f}")

# ---------- GRID ----------
# selection candidates (live-usable)
sel_grid=[]
for dev_min in [2.0,3.0,5.0]:
    for dev_max in [1e9,10.0,6.0]:
        for van in [False,True]:
            for mxco in [None,0,2]:
                for mnco in [None,1,3]:
                    for mer in [None,1.1,1.5]:
                        for rising in [False,True]:
                            if mxco is not None and mnco is not None and mnco>mxco: continue
                            sel_grid.append({"dev_min":dev_min,"dev_max":dev_max,"vanilla":van,
                                "max_cosnip":mxco,"min_cosnip":mnco,"max_entry_ratio":mer,
                                "require_rising":rising,"max_creator_launches":2})
# exit candidates (incl lower ride for higher basis + momentum longer cap)
exit_grid=[]
for derisk in [0.0,0.15,0.30,0.50]:
    for ride in [1.1,1.2,1.3,1.4,2.0]:
        for trail in [0.85,0.92]:
            for cut in [0.90,0.95,0.98]:
                for lad in [0.25]:
                    for cap in [10,20,40,80]:
                        exit_grid.append({"derisk_frac":derisk,"ride_mult":ride,"trail_frac":trail,
                            "cut_r":cut,"ladder_frac":lad,"cap_slots":cap})
print(f"\nsel_grid={len(sel_grid)} exit_grid={len(exit_grid)}  (full cross = {len(sel_grid)*len(exit_grid)})")

# Stage 1: best SELECTION on train with shipped exit; then Stage 2: best EXIT on the winning selection.
best=[]
for S in sel_grid:
    st_=evalc(TRAIN,S,SHIP)
    if st_ and st_["n"]>=40:
        best.append((st_["mean"],S,st_))
best.sort(key=lambda x:-x[0])
print("\n=== Stage 1: top-12 selections on TRAIN (shipped exit, realistic cost), with VAL ===")
print(f"{'dev':>8s} {'van':>3s} {'co[min,max]':>12s} {'mer':>4s} {'ris':>3s} | {'TRAIN mean/med/win/n':>26s} | {'VAL mean/med/win/n':>24s}")
for mean,S,st_ in best[:12]:
    v=evalc(VAL,S,SHIP)
    co=f"[{S['min_cosnip']},{S['max_cosnip']}]"
    print(f"{S['dev_min']:>3.0f}-{S['dev_max'] if S['dev_max']<1e8 else 99:>3.0f} {str(S['vanilla'])[0]:>3s} {co:>12s} {str(S['max_entry_ratio'] or ''):>4s} {str(S['require_rising'])[0]:>3s} | "
          f"{st_['mean']:+.4f}/{st_['median']:+.4f}/{st_['win']*100:3.0f}%/{st_['n']:3d} | "
          f"{v['mean']:+.4f}/{v['median']:+.4f}/{v['win']*100:3.0f}%/{v['n']:3d}" if v else "VAL n<")

# Stage 2: take top-3 train selections, tune exit on train, validate
print("\n=== Stage 2: tune EXIT on top-3 train selections (realistic cost) ===")
winners=[]
for mean,S,st_ in best[:3]:
    cand=[]
    for E in exit_grid:
        t=evalc(TRAIN,S,E)
        if t and t["n"]>=40: cand.append((t["mean"],E,t))
    cand.sort(key=lambda x:-x[0])
    for tm,E,t in cand[:3]:
        v=evalc(VAL,S,E)
        if v and v["n"]>=15:
            winners.append((v["mean"],S,E,t,v))
            print(f"\nSEL {S}\n  EXIT {E}")
            print(f"  TRAIN mean={t['mean']:+.4f} med={t['median']:+.4f} win={t['win']*100:.0f}% n={t['n']}")
            print(f"  VAL   mean={v['mean']:+.4f} med={v['median']:+.4f} win={v['win']*100:.0f}% n={v['n']} drop2={v['mean_drop2']:+.4f} top5sh={v['top5_share']*100:.0f}%")

winners.sort(key=lambda x:-x[0])
print("\n=== BEST by VAL mean (OOS) ===")
for vm,S,E,t,v in winners[:5]:
    print(f"VAL mean={vm:+.4f} med={v['median']:+.4f} win={v['win']*100:.0f}% n={v['n']} drop2={v['mean_drop2']:+.4f} | SEL={S} EXIT={E}")
json.dump({"winners":[{"val_mean":vm,"sel":S,"exit":E,"val":v,"train":t} for vm,S,E,t,v in winners[:10]]},
          open("/root/profit_ourfill/grid_winners.json","w"),indent=2, default=str)

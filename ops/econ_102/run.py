#!/usr/bin/env python3
import sys, json
sys.path.insert(0,"/root/econ_102")
import econ102 as E

SIZES=[0.05,0.1,0.5,2.0]
ROWS=E.load_backtest()
FEAT=E.build_feats(ROWS)
# temporal train/val split by slot
split=FEAT[len(FEAT)//2]["slot"]
TRAIN=[f for f in FEAT if f["slot"]<split]
VAL=[f for f in FEAT if f["slot"]>=split]
CO=[f for f in FEAT if f["cosnip"]>=1]
CO_TRAIN=[f for f in TRAIN if f["cosnip"]>=1]
CO_VAL=[f for f in VAL if f["cosnip"]>=1]

out={}
print("="*100)
print(f"ENTRY = floor * {E.ENTRY_MULT} (priority-fee fill, cu_price=3M)  |  shipped ladder {E.SHIP}")
print(f"sample (unbiased backtest, shipped filter dev>=2 fee==0): n={len(FEAT)}  co-sniped(>=1): n={len(CO)}")
print(f"train/val split slot={split}  train={len(TRAIN)} val={len(VAL)}  co: train={len(CO_TRAIN)} val={len(CO_VAL)}")
print("="*100)

# gross ceiling (zero cost) at this entry basis
g_all=E.evalc_gross(FEAT,E.SHIP); g_co=E.evalc_gross(CO,E.SHIP)
print(f"\nGROSS ceiling (ZERO cost) shipped ladder @ {E.ENTRY_MULT}x:")
print(f"  ALL : mean={g_all['mean']:+.4f} med={g_all['median']:+.4f} win={g_all['win']*100:.1f}% n={g_all['n']}")
print(f"  CO  : mean={g_co['mean']:+.4f} med={g_co['median']:+.4f} win={g_co['win']*100:.1f}% n={g_co['n']}")
out["gross_all"]=g_all; out["gross_co"]=g_co

def block(tag, feats):
    print(f"\n--- SHIPPED config, NET of all costs: {tag} (n={len(feats)}) ---")
    rec={}
    for sz in SIZES:
        S=E.evalc(feats,E.SHIP,sz)
        rec[sz]=S
        print(f"  SIZE={sz:>4} SOL: mean={S['mean']:+.4f} med={S['median']:+.4f} win={S['win']*100:4.1f}% "
              f"totR={S['tot']:+7.2f} top5sh={S['top5_share']*100:5.0f}% mean_ex2={S['mean_ex_top2']:+.4f}")
    return rec

out["ship_all"]=block("FULL sample (actionable)",FEAT)
out["ship_val"]=block("FULL sample VAL (OOS)",VAL)
out["ship_co"]=block("CO-SNIPED subset (ceiling, not pre-buy knowable)",CO)
out["ship_co_val"]=block("CO-SNIPED VAL (OOS)",CO_VAL)

# ---- GRID SEARCH: re-tune EXIT on the 1.02 basis, shipped filter, OOS by slot ----
exit_grid=[]
for derisk in [0.0,0.15,0.30,0.50]:
    for ride in [1.1,1.2,1.3,1.4,2.0]:
        for trail in [0.85,0.92]:
            for cut in [0.90,0.95,0.98]:
                for lad in [0.25]:
                    for cap in [10,20,40,80]:
                        exit_grid.append({"derisk_frac":derisk,"ride_mult":ride,"trail_frac":trail,
                            "cut_r":cut,"ladder_frac":lad,"cap_slots":cap})
print(f"\n{'='*100}\nGRID: re-tune EXIT for the {E.ENTRY_MULT}x basis (shipped filter), train->val OOS. exit_grid={len(exit_grid)}")
print("="*100)
# tune at the actionable mid size 0.5 SOL, report best OOS val cell; also show at all 3 sizes
best_by_size={}
for sz in SIZES:
    cand=[]
    for Ex in exit_grid:
        t=E.evalc(TRAIN,Ex,sz)
        if t and t["n"]>=40: cand.append((t["mean"],Ex,t))
    cand.sort(key=lambda x:-x[0])
    # validate top-15 train cells, pick best VAL
    vbest=None
    for tm,Ex,t in cand[:15]:
        v=E.evalc(VAL,Ex,sz)
        if v and v["n"]>=15:
            if vbest is None or v["mean"]>vbest[0]:
                vbest=(v["mean"],Ex,t,v)
    best_by_size[sz]=vbest
    if vbest:
        vm,Ex,t,v=vbest
        print(f"\nSIZE={sz} SOL best-OOS exit: {Ex}")
        print(f"  TRAIN mean={t['mean']:+.4f} med={t['median']:+.4f} win={t['win']*100:.0f}% n={t['n']}")
        print(f"  VAL   mean={v['mean']:+.4f} med={v['median']:+.4f} win={v['win']*100:.0f}% n={v['n']} "
              f"top5sh={v['top5_share']*100:.0f}% mean_ex2={v['mean_ex_top2']:+.4f} totR={v['tot']:+.2f}")
out["grid_best"]={str(k):({"exit":b[1],"train":b[2],"val":b[3]} if b else None) for k,b in best_by_size.items()}

# ---- PAPER WINDOW (disjoint later OOS) ----
print(f"\n{'='*100}\nPAPER-WINDOW OOS (disjoint later slots) @ {E.ENTRY_MULT}x, shipped ladder, net cost")
print("="*100)
PT=json.load(open("/root/profit_ourfill/paper_traj.json"))
PF=[]
for r in PT:
    if r["dev_buy_wire_lamports"]/1e9 < 2.0: continue
    if not r["n"] or not r.get("entry_px"): continue
    floor=r["entry_px"]; entry=floor*E.ENTRY_MULT
    series=[(s,p) for s,p in r["series"]]
    PF.append({"slot":r["create_slot"],"entry":entry,"entry_slot":r["create_slot"],
               "path":series,"cosnip":r["cosnipers"]})
PCO=[f for f in PF if f["cosnip"]>=1]
print(f"paper feats n={len(PF)} co-sniped={len(PCO)}")
gp=E.evalc_gross(PF,E.SHIP)
print(f"  GROSS ceiling: mean={gp['mean']:+.4f} win={gp['win']*100:.1f}% n={gp['n']}")
for sz in SIZES:
    S=E.evalc(PF,E.SHIP,sz)
    print(f"  ALL SIZE={sz}: mean={S['mean']:+.4f} med={S['median']:+.4f} win={S['win']*100:.1f}% top5sh={S['top5_share']*100:.0f}%")
for sz in SIZES:
    S=E.evalc(PCO,E.SHIP,sz)
    print(f"  CO  SIZE={sz}: mean={S['mean']:+.4f} med={S['median']:+.4f} win={S['win']*100:.1f}% n={S['n']}")
out["paper_all"]={str(sz):E.evalc(PF,E.SHIP,sz) for sz in SIZES}
out["paper_co"]={str(sz):E.evalc(PCO,E.SHIP,sz) for sz in SIZES}
out["paper_gross"]=gp

# ---- COMPARE to old 1.33x fill (co-sniped fill basis that was -EV) ----
print(f"\n{'='*100}\nCOMPARISON: old ~1.33x fill vs new {E.ENTRY_MULT}x fill (FULL sample, shipped, net, 0.5 SOL)")
print("="*100)
for mult in [1.02,1.12,1.33]:
    feats=[{**f,"entry":f["path"] and (f["entry"]/E.ENTRY_MULT*mult) or f["entry"]} for f in FEAT]
    # rebuild entry = floor*mult; floor = entry/ENTRY_MULT
    feats=[{"entry":f["entry"]/E.ENTRY_MULT*mult,"entry_slot":f["entry_slot"],"path":f["path"],"slot":f["slot"],"cosnip":f["cosnip"]} for f in FEAT]
    S=E.evalc(feats,E.SHIP,0.5)
    g=E.evalc_gross(feats,E.SHIP)
    print(f"  fill={mult:.2f}x: NET(0.5SOL) mean={S['mean']:+.4f} win={S['win']*100:.1f}%  |  GROSS mean={g['mean']:+.4f}")

json.dump(out, open("/root/econ_102/results.json","w"), indent=2, default=str)
print("\nwrote /root/econ_102/results.json")

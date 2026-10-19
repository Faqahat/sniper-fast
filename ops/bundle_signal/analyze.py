#!/usr/bin/env python3
"""Merge slot-0 bundle classification with the econ102 net-cost outcome model.
BUNDLED vs OPEN: win% and net-R, full + OOS (train/val by slot). Within OPEN: create_cu_price &
max_competitor_cu_price predictiveness. Plus gross check (do BUNDLED launches pump more?)."""
import json, sys, statistics as st, math
sys.path.insert(0,"/root/econ_102"); import econ102 as E

SIZE=0.5
CLS={r["mint"]:r for r in json.load(open("/root/bundle_signal/classify.json")) if not r.get("error")}

rows=E.load_backtest()
FEAT=[]
for c in rows:
    if not E.passes_shipped(c): continue
    t=c["traj"]
    if not t.get("entry_px"): continue
    cl=CLS.get(c["mint"])
    if not cl: continue
    floor=t["entry_px"]; entry=floor*E.ENTRY_MULT
    series=[(s,p) for s,p in t["series"]]
    net,gross,legs=E.simulate(entry,t["create_slot"],series,E.SHIP,SIZE)
    gnet=E.gross_only(entry,t["create_slot"],series,E.SHIP)  # zero-cost gross ceiling
    FEAT.append({"mint":c["mint"],"slot":c["create_slot"],"net":net,"gross_ceiling":gnet,
                 "bundled":cl["bundled"],"jito_tip":cl["jito_tip_on_create"],
                 "adj_zero":cl["adjacent_zero_fee_buys"],"create_cu":cl["create_cu_price"],
                 "max_comp_cu":cl["max_competitor_cu_price"],"n_buys":cl["n_buys_in_create_slot"],
                 "cosnip":c["traj"]["cosnipers"]})
FEAT.sort(key=lambda f:f["slot"])
print(f"merged FEAT (shipped filter + classified + traj): n={len(FEAT)}  SIZE={SIZE} SOL")

def summ(fs):
    if not fs: return None
    nets=[f["net"] for f in fs]; n=len(nets)
    win=sum(1 for x in nets if x>0)/n
    mean=sum(nets)/n; tot=sum(nets); med=st.median(nets)
    sd=st.pstdev(nets) if n>1 else 0
    gmean=sum(f["gross_ceiling"] for f in fs)/n
    gwin=sum(1 for f in fs if f["gross_ceiling"]>0)/n
    # bootstrap 95% CI on mean net
    import random; random.seed(1)
    bs=[]
    for _ in range(2000):
        s=[nets[random.randrange(n)] for _ in range(n)]
        bs.append(sum(s)/n)
    bs.sort(); lo=bs[int(.025*2000)]; hi=bs[int(.975*2000)]
    return {"n":n,"win":win,"mean":mean,"med":med,"tot":tot,"sd":sd,"ci_lo":lo,"ci_hi":hi,
            "gross_mean":gmean if False else gmean,"gross_win":gwin} if False else {
            "n":n,"win":win,"mean":mean,"med":med,"tot":tot,"sd":sd,"ci_lo":lo,"ci_hi":hi,
            "gross_mean":gmean,"gross_win":gwin}

# fix: compute gross aggregates cleanly
def summ(fs):
    if not fs: return None
    nets=[f["net"] for f in fs]; n=len(nets)
    win=sum(1 for x in nets if x>0)/n
    mean=sum(nets)/n; tot=sum(nets); med=st.median(nets)
    sd=st.pstdev(nets) if n>1 else 0
    gmean=sum(f["gross_ceiling"] for f in fs)/n
    gwin=sum(1 for f in fs if f["gross_ceiling"]>0)/n
    import random; random.seed(1)
    bs=[]
    for _ in range(2000):
        s=[nets[random.randrange(n)] for _ in range(n)]; bs.append(sum(s)/n)
    bs.sort(); lo=bs[int(.025*2000)]; hi=bs[int(.975*2000)]
    return {"n":n,"win":win,"mean":mean,"med":med,"tot":tot,"sd":sd,"ci_lo":lo,"ci_hi":hi,
            "gross_mean":gmean,"gross_win":gwin}

def line(tag,S):
    if not S: print(f"  {tag:28s} n=0"); return
    print(f"  {tag:28s} n={S['n']:4d}  win={S['win']*100:5.1f}%  netR_mean={S['mean']:+.4f} "
          f"[95%CI {S['ci_lo']:+.3f},{S['ci_hi']:+.3f}]  med={S['med']:+.4f}  totR={S['tot']:+7.2f}  "
          f"grossWin={S['gross_win']*100:4.1f}% grossMean={S['gross_mean']:+.3f}")

ALL=FEAT; BUN=[f for f in FEAT if f["bundled"]]; OPEN=[f for f in FEAT if not f["bundled"]]
print("\n===== FULL SAMPLE (in-sample) =====")
line("ALL (baseline)",summ(ALL))
line("BUNDLED (skip candidate)",summ(BUN))
line("OPEN (keep)",summ(OPEN))

# OOS temporal split by slot (median slot)
split=FEAT[len(FEAT)//2]["slot"]
TR=[f for f in FEAT if f["slot"]<split]; VA=[f for f in FEAT if f["slot"]>=split]
print(f"\n===== OUT-OF-SAMPLE (validation half, slot>={split}, n={len(VA)}) =====")
line("ALL val",summ(VA))
line("BUNDLED val",summ([f for f in VA if f['bundled']]))
line("OPEN val",summ([f for f in VA if not f['bundled']]))
print(f"\n----- (train half, slot<{split}, n={len(TR)}) for reference -----")
line("ALL train",summ(TR))
line("BUNDLED train",summ([f for f in TR if f['bundled']]))
line("OPEN train",summ([f for f in TR if not f['bundled']]))

# component breakdown
print("\n===== BUNDLE COMPONENTS (full) =====")
line("jito_tip>0",summ([f for f in FEAT if f['jito_tip']>0]))
line("adj_zero_buys>=1",summ([f for f in FEAT if f['adj_zero']>=1]))
line("tip>0 AND no adj",summ([f for f in FEAT if f['jito_tip']>0 and f['adj_zero']==0]))

# within OPEN: create_cu_price predictive?
print("\n===== WITHIN OPEN: create_cu_price (serious-launch proxy) =====")
ocu=sorted([f["create_cu"] for f in OPEN])
if ocu:
    medcu=ocu[len(ocu)//2]
    line(f"OPEN create_cu<=median({medcu})",summ([f for f in OPEN if f["create_cu"]<=medcu]))
    line(f"OPEN create_cu>median",summ([f for f in OPEN if f["create_cu"]>medcu]))
    line("OPEN create_cu==0",summ([f for f in OPEN if f["create_cu"]==0]))
    line("OPEN create_cu>0",summ([f for f in OPEN if f["create_cu"]>0]))

print("\n===== WHALE: max_competitor_cu_price (full sample, predicts loss?) =====")
allc=sorted([f["max_comp_cu"] for f in FEAT]); medc=allc[len(allc)//2] if allc else 0
q75=allc[int(.75*len(allc))] if allc else 0
line(f"max_comp_cu<=med({medc})",summ([f for f in FEAT if f["max_comp_cu"]<=medc]))
line(f"max_comp_cu>med",summ([f for f in FEAT if f["max_comp_cu"]>medc]))
line(f"max_comp_cu>=p75({q75})",summ([f for f in FEAT if f["max_comp_cu"]>=q75]))
# within OPEN too
print("  -- within OPEN --")
line("OPEN max_comp_cu<=med",summ([f for f in OPEN if f["max_comp_cu"]<=medc]))
line("OPEN max_comp_cu>med",summ([f for f in OPEN if f["max_comp_cu"]>medc]))

# confounding: do BUNDLED launches pump MORE (gross ceiling)?
print("\n===== CONFOUNDING CHECK: gross ceiling (pump magnitude, zero-cost) BUNDLED vs OPEN =====")
def gstat(fs):
    g=[f["gross_ceiling"] for f in fs]; n=len(g)
    return n,sum(g)/n,sum(1 for x in g if x>0)/n,st.median(g)
for tag,fs in [("BUNDLED",BUN),("OPEN",OPEN)]:
    n,gm,gw,gmd=gstat(fs); print(f"  {tag:10s} n={n} gross_mean={gm:+.4f} gross_win={gw*100:.1f}% gross_med={gmd:+.4f}")

json.dump({
 "size":SIZE,"n":len(FEAT),
 "all":summ(ALL),"bundled":summ(BUN),"open":summ(OPEN),
 "val_all":summ(VA),"val_bundled":summ([f for f in VA if f['bundled']]),"val_open":summ([f for f in VA if not f['bundled']]),
 "train_all":summ(TR),"train_bundled":summ([f for f in TR if f['bundled']]),"train_open":summ([f for f in TR if not f['bundled']]),
 "jito_only":summ([f for f in FEAT if f['jito_tip']>0]),"adj_only":summ([f for f in FEAT if f['adj_zero']>=1]),
 "split_slot":split,
}, open("/root/bundle_signal/analysis.json","w"),indent=2,default=str)
print("\nwrote /root/bundle_signal/analysis.json")

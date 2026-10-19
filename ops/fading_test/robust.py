#!/usr/bin/env python3
import sys, random, statistics as st
sys.path.insert(0,"/root/fading_test")
from fading import simulate, stats, FEATS, E
SIZE=0.5; BASE=dict(E.SHIP)
def mk(**kw):
    p=dict(BASE); p.update(kw); return p
V={
 "CURRENT":        mk(fade_mode="instant"),
 "NO-FADING":      mk(fade_mode="off"),
 "PATIENT3(.90)":  mk(fade_mode="patient",fade_consec_n=3,fade_deep=0.90),
 "NOFADE cut.80 ride1.4": mk(fade_mode="off",cut_r=0.80,ride_mult=1.4,cap_slots=70),
}
def pnls(feats,P): return [simulate(f["entry"],f["entry_slot"],f["path"],P,SIZE) for f in feats]
def subset(feats,P,lo=None,hi=None):
    sel=[f for f in feats if (lo is None or f["peak"]>=lo) and (hi is None or f["peak"]<hi)]
    return stats(pnls(sel,P))

print("==== FULL SAMPLE (n=%d) — most stable ===="%len(FEATS))
print("%-24s | mean    | median  | win   | totR   | run>=1.5x(201) | run>=2x(92) | dud<1.1x(258)"%"variant")
for n,P in V.items():
    s=stats(pnls(FEATS,P)); r15=subset(FEATS,P,lo=1.5); r20=subset(FEATS,P,lo=2.0); d=subset(FEATS,P,hi=1.1)
    print("%-24s | %+.4f | %+.4f | %4.1f%% | %+6.2f | %+.4f | %+.4f | %+.4f"%(
        n,s["mean"],s["median"],s["win"]*100,s["tot"],r15["mean"],r20["mean"],d["mean"]))

# slot split both directions
FEATS.sort(key=lambda f:f["slot"]); mid=len(FEATS)//2
A=FEATS[:mid]; B=FEATS[mid:]
print("\n==== SLOT-SPLIT, train->val direction matters (mean netR) ====")
print("%-24s | val=LATER | val=EARLIER | full"%"variant")
for n,P in V.items():
    print("%-24s | %+.4f    | %+.4f      | %+.4f"%(n,stats(pnls(B,P))["mean"],stats(pnls(A,P))["mean"],stats(pnls(FEATS,P))["mean"]))

# random 50/50 splits: distribution of (variant mean on held-out)
print("\n==== 200 random 50/50 splits: held-out mean netR (mean +/- sd across splits) ====")
rng=random.Random(7)
agg={n:[] for n in V}
for _ in range(200):
    idx=list(range(len(FEATS))); rng.shuffle(idx); ho=[FEATS[i] for i in idx[len(idx)//2:]]
    for n,P in V.items(): agg[n].append(stats(pnls(ho,P))["mean"])
for n in V:
    a=agg[n]; print("%-24s | %+.4f  +/- %.4f   [p10 %+.4f, p90 %+.4f]"%(
        n,sum(a)/len(a),st.pstdev(a),sorted(a)[20],sorted(a)[180]))

# paired: NO-FADING minus CURRENT, per split (is the difference ever reliably positive?)
print("\n==== paired delta over 200 splits (variant - CURRENT), held-out mean ====")
cur=agg["CURRENT"]
for n in V:
    if n=="CURRENT": continue
    d=[agg[n][i]-cur[i] for i in range(200)]
    pos=sum(1 for x in d if x>0)/len(d)
    print("%-24s | mean delta %+.4f  | P(delta>0)=%4.1f%%"%(n,sum(d)/len(d),pos*100))

# per-token: how often does NO-FADING beat CURRENT, and the tail contribution
print("\n==== per-token NO-FADING vs CURRENT (full sample) ====")
cp=pnls(FEATS,V["CURRENT"]); nf=pnls(FEATS,V["NO-FADING"])
diff=[nf[i]-cp[i] for i in range(len(FEATS))]
better=sum(1 for d in diff if d>1e-9); worse=sum(1 for d in diff if d<-1e-9)
print("NO-FADING better on %d tokens, worse on %d, same %d"%(better,worse,len(diff)-better-worse))
print("sum of gains where better: %+.2f ; sum of losses where worse: %+.2f ; net %+.2f"%(
    sum(d for d in diff if d>0),sum(d for d in diff if d<0),sum(diff)))
# runner vs dud decomposition of the delta
rg=sum(diff[i] for i in range(len(FEATS)) if FEATS[i]["peak"]>=1.5)
dd=sum(diff[i] for i in range(len(FEATS)) if FEATS[i]["peak"]<1.1)
mid=sum(diff[i] for i in range(len(FEATS)) if 1.1<=FEATS[i]["peak"]<1.5)
print("delta from runners(>=1.5x): %+.2f ; mid(1.1-1.5x): %+.2f ; duds(<1.1x): %+.2f"%(rg,mid,dd))

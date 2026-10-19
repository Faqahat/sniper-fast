#!/usr/bin/env python3
"""Slot-0 feature tests on the labeled unbiased population + enrichment check on his landed picks.
For each candidate feature: bucket win-rate/meanR + lift; time-split TRAIN/VAL rule fit (OOS)."""
import json,statistics as st,math
POP=json.load(open("/root/selection_study/pop_labeled.json"))
try: HIS=[r for r in json.load(open("/root/selection_study/his_landed_labeled.json")) if r.get("ok")]
except Exception: HIS=[]
def wr(sub):
    n=len(sub)
    if not n: return (0,0.0,0.0)
    return (n,sum(1 for r in sub if r[\"win\"])/n,sum(r[\"net\"] for r in sub)/n)
def unbounded(r): return r.get(\"dev_buy_wire\",0)>=1e17
def vanilla(r): return not (r.get(\"mayhem\") or r.get(\"holder_reward\") or r.get(\"cashback\"))
base_n,base_w,base_m=wr(POP)
print(f\"# SLOT-0 FEATURE ANALYSIS  (unbiased pop n={base_n}, flip-win base {base_w*100:.1f}%, meanR {base_m:+.4f})\")
print(f\"# his landed labeled n={len(HIS)}  flip-win {wr(HIS)[1]*100:.1f}% meanR {wr(HIS)[2]:+.4f}\\n\")

def feat_report(name,buckets,hisfn=None):
    print(f\"## {name}\")
    print(f\"{bucket:>22} | {n:>5} {win%:>6} {meanR:>8} {lift:>6} | {HISshare:>9}\")
    for label,fn in buckets:
        sub=[r for r in POP if fn(r)]; n,w,m=wr(sub)
        hs=\"\"
        if HIS:
            hn=sum(1 for r in HIS if fn(r)); hs=f\"{hn}/{len(HIS)}={hn/len(HIS)*100:.0f}%\"
        print(f\"{label:>22} | {n:>5} {w*100:>5.1f}% {m:>+8.4f} {(w-base_w)*100:>+5.1f} | {hs:>9}\")
    print()

feat_report(\"dev_buy size (curve truth, SOL)\",[
    (\"<0.3\",lambda r:r[\"dev_buy\"]<0.3),
    (\"0.3-0.5\",lambda r:0.3<=r[\"dev_buy\"]<0.5),
    (\"0.5-1.0\",lambda r:0.5<=r[\"dev_buy\"]<1.0),
    (\"1.0-2.0\",lambda r:1.0<=r[\"dev_buy\"]<2.0),
    (\"2.0-5.0\",lambda r:2.0<=r[\"dev_buy\"]<5.0),
    (\">=5.0\",lambda r:r[\"dev_buy\"]>=5.0),
])
feat_report(\"dev_buy sized vs unbounded(u64MAX cap)\",[
    (\"sized (finite)\",lambda r:not unbounded(r)),
    (\"unbounded cap\",unbounded),
])
feat_report(\"vanilla vs non-vanilla\",[
    (\"vanilla\",vanilla),
    (\"non-vanilla\",lambda r:not vanilla(r)),
])
feat_report(\"same-create-slot co-snipers (slot-0 knowable)\",[
    (\"0\",lambda r:r[\"cosnipers\"]==0),
    (\"1\",lambda r:r[\"cosnipers\"]==1),
    (\"2\",lambda r:r[\"cosnipers\"]==2),
    (\">=3\",lambda r:r[\"cosnipers\"]>=3),
])
feat_report(\"creator in-window launch freq (rep)\",[
    (\"1 (fresh)\",lambda r:r[\"rep\"]==1),
    (\"2\",lambda r:r[\"rep\"]==2),
    (\">=3 (factory)\",lambda r:r[\"rep\"]>=3),
])

# creator prior spiking launch (ordered by slot, in-window) -- slot-0 knowable from creator history
POPs=sorted(POP,key=lambda r:r[\"create_slot\"])
seen={}  # creator -> list of prior peaks
for r in POPs:
    pri=seen.get(r[\"creator\"],[])
    r[\"_prior_n\"]=len(pri)
    r[\"_prior_spike\"]=any(p>=1.5 for p in pri)
    seen.setdefault(r[\"creator\"],[]).append(r[\"peak\"])
feat_report(\"creator had PRIOR in-window launch\",[
    (\"no prior (first)\",lambda r:r.get(\"_prior_n\",0)==0),
    (\"has prior\",lambda r:r.get(\"_prior_n\",0)>=1),
    (\"prior spiked(>=1.5x)\",lambda r:r.get(\"_prior_spike\",False)),
    (\"prior no-spike\",lambda r:r.get(\"_prior_n\",0)>=1 and not r.get(\"_prior_spike\",False)),
])

# congestion: creates within +-10 slots
slots=sorted(r[\"create_slot\"] for r in POP)
import bisect
def density(r):
    s=r[\"create_slot\"]; lo=bisect.bisect_left(slots,s-10); hi=bisect.bisect_right(slots,s+10); return hi-lo
for r in POP: r[\"_dens\"]=density(r)
dvals=sorted(r[\"_dens\"] for r in POP); med=dvals[len(dvals)//2]
feat_report(f\"launch congestion (creates within +-10 slots, med={med})\",[
    (\"low (<=med)\",lambda r:r[\"_dens\"]<=med),
    (\"high (>med)\",lambda r:r[\"_dens\"]>med),
])
# dead-on-arrival (0 post-create trades) -- NOT slot-0 knowable but diagnostic
feat_report(\"post-create trade count (OUTCOME, not slot-0)\",[
    (\"0 trades (DOA)\",lambda r:r[\"n_trades\"]==0),
    (\">=1 trade\",lambda r:r[\"n_trades\"]>=1),
    (\">=5 trades\",lambda r:r[\"n_trades\"]>=5),
])

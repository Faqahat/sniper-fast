import json, statistics as st
tape=json.load(open("/root/mirror/his_tape.json"))
d500=json.load(open("/root/last500/his_500.json"))
tb={r["mint"]:r for r in tape}
M={}
for r in d500:
    rec=dict(r); t=tb.get(r["mint"])
    if t:
        rec["realized_sol"]=t.get("realized_sol")
        if t.get("peak_r"): rec["peak_r"]=max(rec.get("peak_r") or 0,t["peak_r"])
    M[r["mint"]]=rec
recs=[r for r in M.values() if r.get("peak_r")]
N=len(recs)
def runner(r): return r["peak_r"]>=1.5
def dump(r): return r["peak_r"]<1.1

print("=== FLAGS (binary) vs outcome ===")
for f in ["vanilla","holder_reward","creator_fee_bps","has_image","mayhem"]:
    for val,lbl in [(0,"=0/false"),(1,">0/true")]:
        b=[r for r in recs if (r.get(f) or 0)>0]==None and []  # placeholder
    yes=[r for r in recs if (r.get(f) or 0)>0]
    no=[r for r in recs if (r.get(f) or 0)==0]
    for lbl,b in [("TRUE",yes),("FALSE",no)]:
        if b:
            print("  %-16s %-5s n=%-3d runner%%=%4.1f dump%%=%4.1f meanPeak=%.3f"%(
                f,lbl,len(b),100*sum(1 for r in b if runner(r))/len(b),
                100*sum(1 for r in b if dump(r))/len(b),st.mean([r["peak_r"] for r in b])))
print()

# his realized P&L by n_trades_0_3 bucket (tape overlap only)
print("=== HIS REALIZED P&L by n_trades_0_3 (overlap w/ tape) ===")
ov=[r for r in recs if r.get("realized_sol") is not None and r.get("n_trades_0_3") is not None]
print("  overlap n=%d"%len(ov))
for lbl,lo,hi in [("0-1",0,2),("2",2,3),("3-4",3,5),("5-9",5,10),("10+",10,1e9)]:
    b=[r for r in ov if lo<=r["n_trades_0_3"]<hi]
    if b:
        p=[r["realized_sol"] for r in b]
        print("  %-5s n=%-3d meanPnL=%+.4f medPnL=%+.4f win%%=%.0f totalPnL=%+.3f"%(
            lbl,len(b),st.mean(p),st.median(p),100*sum(1 for x in p if x>0)/len(b),sum(p)))
print()

# does HE filter n_trades_0_3? his buy distribution
print("=== Does HE filter? his buy-count per n_trades_0_3 bucket ===")
for lbl,lo,hi in [("0-1",0,2),("2",2,3),("3-4",3,5),("5-9",5,10),("10+",10,1e9)]:
    b=[r for r in recs if r.get("n_trades_0_3") is not None and lo<=r["n_trades_0_3"]<hi]
    print("  %-5s: %d buys (%.1f%% of his trades)"%(lbl,len(b),100*len(b)/N))
print()

# creator repeat within dataset
print("=== CREATOR repeat (within his buys) ===")
from collections import Counter
cc=Counter(r.get("creator") for r in recs if r.get("creator"))
multi=[c for c,n in cc.items() if n>1]
print("  distinct creators=%d, creators he bought >once=%d"%(len(cc),len(multi)))
rep=[r for r in recs if cc.get(r.get("creator"),0)>1]
single=[r for r in recs if cc.get(r.get("creator"),0)==1]
for lbl,b in [("repeat-creator",rep),("one-off creator",single)]:
    if b: print("  %-16s n=%d runner%%=%.1f dump%%=%.1f meanPeak=%.3f"%(
        lbl,len(b),100*sum(1 for r in b if runner(r))/len(b),100*sum(1 for r in b if dump(r))/len(b),st.mean([r["peak_r"] for r in b])))
print()

# name/symbol length pattern
print("=== NAME/SYMBOL patterns ===")
named=[r for r in recs if r.get("symbol")]
for lbl,fn in [("sym<=3char",lambda r:len(r["symbol"])<=3),("sym4-6",lambda r:4<=len(r["symbol"])<=6),("sym7+",lambda r:len(r["symbol"])>=7)]:
    b=[r for r in named if fn(r)]
    if b: print("  %-12s n=%d runner%%=%.1f dump%%=%.1f meanPeak=%.3f"%(lbl,len(b),100*sum(1 for r in b if runner(r))/len(b),100*sum(1 for r in b if dump(r))/len(b),st.mean([r["peak_r"] for r in b])))

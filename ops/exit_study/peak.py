import json,statistics as st
rows=json.load(open("rows.json"))
paths=json.load(open("paths.json"))
res={r["mint"]:r for r in json.load(open("trades.json")) if not r.get("error")}
def pct(xs,p):
    xs=sorted(xs); i=min(len(xs)-1,int(round(p*(len(xs)-1)))); return xs[i]
def summ(xs,nd=3):
    xs=[x for x in xs if x is not None]
    if not xs: return "n=0"
    return f"n={len(xs)} p10={round(pct(xs,.1),nd)} p25={round(pct(xs,.25),nd)} med={round(st.median(xs),nd)} p75={round(pct(xs,.75),nd)} p90={round(pct(xs,.9),nd)} max={round(max(xs),nd)}"
# build px_entry per mint from primary buy: use rows px_entry (lamports/raw tok)
for r in rows:
    m=r["mint"]; r["px_entry"]=r["px_entry"]
# attach peak r & r@offset
for r in rows:
    m=r["mint"]; p=paths.get(m,{})
    pts=p.get("pts",[]); r["peak_r"]=None; r["r5"]=None; r["r10"]=None; r["r20"]=None
    if pts and r["px_entry"]:
        pe=r["px_entry"]; bslot=r["bslot"]
        rs=[(s,px/pe) for s,px in pts]
        r["peak_r"]=max(x[1] for x in rs)
        def rat(off):
            cand=[x[1] for x in rs if x[0]<=bslot+off]
            return cand[-1] if cand else None
        r["r5"]=rat(5); r["r10"]=rat(10); r["r20"]=rat(20)
    # frac-weighted exit r
    if r["sells"]:
        tot=sum(s["frac"] for s in r["sells"])
        r["wexit_r"]=sum(s["r"]*s["frac"] for s in r["sells"])/tot if tot else None
        r["max_sell_r"]=max(s["r"] for s in r["sells"])
    else: r["wexit_r"]=None; r["max_sell_r"]=None
json.dump(rows,open("rows2.json","w"))
W=[r for r in rows if r["realized"]>0]; L=[r for r in rows if r["realized"]<=0]
print("=== PEAK / TRAILING (market price path) ===")
for name,G in [("WIN",W),("LOSE",L)]:
    pk=[r["peak_r"] for r in G if r["peak_r"]]
    print(f"[{name}] peak_r             :",summ(pk))
    trail=[r["wexit_r"]/r["peak_r"] for r in G if r.get("peak_r") and r["wexit_r"]]
    print(f"[{name}] exit_r/peak_r(trail):",summ(trail))
    maxtrail=[r["max_sell_r"]/r["peak_r"] for r in G if r.get("peak_r") and r["max_sell_r"]]
    print(f"[{name}] bestsell_r/peak_r  :",summ(maxtrail))
print("\n=== PREDICTIVE: early market r vs outcome ===")
for off,key in [(5,"r5"),(10,"r10"),(20,"r20")]:
    wv=[r[key] for r in W if r[key]]; lv=[r[key] for r in L if r[key]]
    print(f" r@+{off}: WIN med {round(st.median(wv),3)} (n{len(wv)}) | LOSE med {round(st.median(lv),3)} (n{len(lv)})")
# rule test: if r@+10 >= X then win?
import itertools
print("\n rule: r@+10 >= thr -> predict WIN")
for thr in [1.03,1.05,1.08,1.1,1.15]:
    tp=sum(1 for r in W if r["r10"] and r["r10"]>=thr)
    fp=sum(1 for r in L if r["r10"] and r["r10"]>=thr)
    tn=sum(1 for r in L if r["r10"] and r["r10"]<thr)
    fn=sum(1 for r in W if r["r10"] and r["r10"]<thr)
    tot=tp+fp+tn+fn
    prec=tp/(tp+fp) if tp+fp else 0
    print(f"  thr {thr}: accept {tp+fp} (win {tp}/{tp+fp}={round(prec,2)}) | reject {tn+fn} (loss correctly {tn})  acc={round((tp+tn)/tot,3)}")

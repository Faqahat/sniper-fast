import json,itertools
from collections import Counter
rows=json.load(open("/root/sep2/rows_enriched.json"))
WL=[r for r in rows if r["label"] in ("WIN","LOSE")]
WL.sort(key=lambda r:r["slot"])
def g(r,k,d=0): 
    v=r.get(k); return d if v is None else v
# keep_fn => True = predict WINNER (keep)
RULES={
 "demand:n_cobuy01>=3": lambda r: g(r,"n_cobuy_slot01")>=3,
 "demand:n_cobuy01>=2": lambda r: g(r,"n_cobuy_slot01")>=2,
 "demand:sol_cobuy01>=1.0": lambda r: g(r,"sol_cobuy_slot01")>=1.0,
 "demand:sol_cobuy01>=0.5": lambda r: g(r,"sol_cobuy_slot01")>=0.5,
 "demand:sol_cobuy01>=2.0": lambda r: g(r,"sol_cobuy_slot01")>=2.0,
 "demand:dev_share<0.80": lambda r: g(r,"dev_share_slot01",1)<0.80,
 "demand:dev_share<0.90": lambda r: g(r,"dev_share_slot01",1)<0.90,
 "demand:max_cobuy>=0.5": lambda r: g(r,"max_cobuy_slot01")>=0.5,
 "demand:cobuy_to_dev>=0.5": lambda r: g(r,"cobuy_to_dev")>=0.5,
 "slot0:n_cobuy0>=1": lambda r: g(r,"n_cobuy_slot0")>=1,
 "slot0:sol_cobuy0>=1.0": lambda r: g(r,"sol_cobuy_slot0")>=1.0,
 "host:not_md.sdfg": lambda r: r.get("uri_host")!="md.sdfgsdfsdf.uk",
 "creator:count<=3": lambda r: g(r,"creator_mint_count")<=3,
 "vanilla:false": lambda r: r.get("vanilla")==False,
}
def ev(keep,subset):
    kw=sum(1 for r in subset if keep(r) and r["label"]=="WIN")
    kl=sum(1 for r in subset if keep(r) and r["label"]=="LOSE")
    rw=sum(1 for r in subset if not keep(r) and r["label"]=="WIN")
    rl=sum(1 for r in subset if not keep(r) and r["label"]=="LOSE")
    W=kw+rw; L=kl+rl
    prec=kw/(kw+kl) if (kw+kl) else float("nan")
    rec=kw/W if W else float("nan")
    lrem=rl/L if L else float("nan")
    return dict(kw=kw,kl=kl,rw=rw,rl=rl,prec=prec,rec=rec,lrem=lrem)
baseW=sum(1 for r in WL if r["label"]=="WIN"); baseL=len(WL)-baseW
print("FULL WL: WIN=%d LOSE=%d  base winP=%.3f"%(baseW,baseL,baseW/len(WL)))
print("\n===== SINGLE RULES (full in-sample) =====")
print("%-28s keepW keepL rejW rejL  winP  recall Lremoved"%"rule")
singles=[]
for nm,fn in RULES.items():
    e=ev(fn,WL); singles.append((nm,fn,e))
    print("%-28s %4d %5d %5d %5d  %.2f  %.2f   %.2f"%(nm,e["kw"],e["kl"],e["rw"],e["rl"],e["prec"],e["rec"],e["lrem"]))

# temporal split
half=len(WL)//2; train=WL[:half]; test=WL[half:]
print("\nTEMPORAL: train n=%d %s (slots<=%d) | test n=%d %s (slots>=%d)"%(
    len(train),dict(Counter(r["label"] for r in train)),train[-1]["slot"],
    len(test),dict(Counter(r["label"] for r in test)),test[0]["slot"]))
def oos(nm,fn):
    et=ev(fn,train); ev2=ev(fn,test)
    print("  %-26s TRAIN winP=%.2f rec=%.2f Lrem=%.2f (kW%d kL%d) | TEST winP=%.2f rec=%.2f Lrem=%.2f (kW%d kL%d)"%(
        nm,et["prec"],et["rec"],et["lrem"],et["kw"],et["kl"],ev2["prec"],ev2["rec"],ev2["lrem"],ev2["kw"],ev2["kl"]))
print("\n===== TEMPORAL OOS (single rules) =====")
for nm,fn in RULES.items(): oos(nm,fn)

# pair/triple combos (reject if ANY sub-rule rejects => keep = AND of keeps)
print("\n===== BEST COMBINATIONS (keep = AND; maximize kw-3*kl) =====")
items=list(RULES.items())
combos=[]
for r in (1,2,3):
    for cmb in itertools.combinations(items,r):
        keep=lambda x,cmb=cmb: all(f(x) for _,f in cmb)
        e=ev(keep,WL)
        combos.append((" & ".join(n for n,_ in cmb),e,cmb))
combos.sort(key=lambda x:(x[1]["kw"]-3*x[1]["kl"], x[1]["lrem"]),reverse=True)
seen=set();shown=0
print("%-60s keepW keepL winP rec Lrem"%"combo")
for nm,e,cmb in combos:
    if shown>=14: break
    print("%-60s %4d %4d %.2f %.2f %.2f"%(nm[:60],e["kw"],e["kl"],e["prec"],e["rec"],e["lrem"]))
    shown+=1

# detailed look at best demand rule errors
print("\n===== ERROR ANALYSIS: keep if n_cobuy_slot01>=2 =====")
kf=lambda r: g(r,"n_cobuy_slot01")>=2
print("KEPT-LOSERS (false pos):",[(r["mint"][:7],r.get("uri_host"),r.get("n_cobuy_slot01"),round(g(r,"sol_cobuy_slot01"),2),round(g(r,"dev_share_slot01",1),2)) for r in WL if kf(r) and r["label"]=="LOSE"])
print("REJECTED-WINNERS (false neg):",[(r["mint"][:7],r.get("uri_host"),r.get("n_cobuy_slot01"),round(g(r,"sol_cobuy_slot01"),2)) for r in WL if not kf(r) and r["label"]=="WIN"])

print("\n===== OOS for top combos =====")
for keepname,keep in [("n_cobuy01>=2 & host!=md.sdfg", lambda r: g(r,"n_cobuy_slot01")>=2 and r.get("uri_host")!="md.sdfgsdfsdf.uk"),
                       ("dev_share<0.90 & n_cobuy01>=2", lambda r: g(r,"dev_share_slot01",1)<0.90 and g(r,"n_cobuy_slot01")>=2),
                       ("sol_cobuy01>=0.5", lambda r: g(r,"sol_cobuy_slot01")>=0.5)]:
    oos(keepname,keep)

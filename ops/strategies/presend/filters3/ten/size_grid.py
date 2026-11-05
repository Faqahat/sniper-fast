import json, sys, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/ten")
from sizesim import pnl_at
D="/home/moiz/sniper-data/filters3/ten/"
pos=json.load(open(D+"pos.json")); H=json.load(open(D+"hours.json"))
def nb(p): return p["nb"] if p["nb"] is not None else (p["ann"] or {}).get("nb50")
def n60(p): return (p["v2"] or {}).get("n_tr_60s")
def coh(p): return (p["q"] or {}).get("coh_hold")
rules={}
for T in (8,10,12,15,18,22,26): rules[f"nb50>={T}"]=lambda p,T=T: (nb(p) or -1)>=T
for T in (10,15,20,30,47): rules[f"t2 n60>={T}"]=lambda p,T=T: p["kind"]=="t2" and (n60(p) or -1)>=T
rules["t2 coh>=3"]=lambda p: p["kind"]=="t2" and (coh(p) or 0)>=3
rules["t2 n60>=15 & nb>=12"]=lambda p: p["kind"]=="t2" and (n60(p) or -1)>=15 and (nb(p) or -1)>=12
cache={}
def val(p,m,beta,ds):
    k=(id(p),m,beta,ds)
    if k not in cache: cache[k]=pnl_at(p,p["spend"]*m,ds,7,beta)[0]
    return cache[k]
print("Delta SOL/day vs today (same trades, size x m on rule-true trades), rows: beta 0 / 3 / 9 and beta3 + flat -20% followers on all")
for name,f in rules.items():
    for m in (1.5,2.0):
        line=f"{name:22s} x{m}"
        for sg in ("DEV","VAL"):
            P=[p for p in pos if p["seg"]==sg]
            hit=[p for p in P if f(p)]
            line+=f" | {sg} n {len(hit):4d} base {sum(p['pnl'] for p in hit)/H[sg]*24:+5.2f}:"
            for beta,ds in ((0,0),(3,0),(9,0),(3,0.2)):
                d=sum(val(p,m,beta,ds)-val(p,1.0,0,ds) for p in hit)
                line+=f" {d/H[sg]*24:+5.2f}"
        print(line)

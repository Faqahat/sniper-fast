import json,statistics as st
rows=json.load(open("rows.json"))
def pct(xs,p):
    xs=sorted(xs); 
    if not xs: return None
    i=min(len(xs)-1,int(round(p*(len(xs)-1)))); return xs[i]
def summ(xs,nd=3):
    xs=[x for x in xs if x is not None]
    if not xs: return "n=0"
    return f"n={len(xs)} p10={round(pct(xs,.1),nd)} p25={round(pct(xs,.25),nd)} med={round(st.median(xs),nd)} p75={round(pct(xs,.75),nd)} p90={round(pct(xs,.9),nd)} max={round(max(xs),nd)}"
W=[r for r in rows if r["realized"]>0]
L=[r for r in rows if r["realized"]<=0]
print("WINNERS",len(W),"LOSERS",len(L))
for name,G in [("ALL",rows),("WIN",W),("LOSE",L)]:
    fs=[r["sells"][0] for r in G if r["sells"]]
    print(f"\n=== {name} (n={len(G)}) ===")
    print(" first-sell dslot:",summ([s["dslot"] for s in fs],0))
    print(" first-sell frac :",summ([s["frac"] for s in fs]))
    print(" first-sell r    :",summ([s["r"] for s in fs]))
    print(" nsells          :",summ([r["nsells"] for r in G],0))
    print(" last-sell dslot :",summ([r["last_dslot"] for r in G],0))
    print(" max r (his sells):",summ([max(s["r"] for s in r["sells"]) for r in G if r["sells"]]))
    print(" realized PnL    :",summ([r["realized"] for r in G]))
    # weighted avg exit r (fraction-weighted)
    war=[]
    for r in G:
        if r["sells"]:
            tot=sum(s["frac"] for s in r["sells"])
            if tot>0: war.append(sum(s["r"]*s["frac"] for s in r["sells"])/tot)
    print(" frac-weighted exit r:",summ(war))

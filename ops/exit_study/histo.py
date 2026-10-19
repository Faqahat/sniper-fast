import json,statistics as st
rows=json.load(open("rows.json"))
W=[r for r in rows if r["realized"]>0]; L=[r for r in rows if r["realized"]<=0]
# histogram of (r at sell, fraction sold) across all sells, weighted by fraction
def hist(G,label):
    bins=[(0,0.9),(0.9,1.0),(1.0,1.1),(1.1,1.25),(1.25,1.5),(1.5,2.0),(2.0,99)]
    agg={b:[0.0,0] for b in bins}  # [sum frac, count]
    for r in G:
        for s in r["sells"]:
            for b in bins:
                if b[0]<=s["r"]<b[1]:
                    agg[b][0]+=s["frac"]; agg[b][1]+=1; break
    tot=sum(v[0] for v in agg.values())
    print(f"\n[{label}] r-bucket : share-of-all-tokens-sold | n-sells")
    for b in bins:
        f,c=agg[b]
        print(f"  r[{b[0]:.2f}-{b[1]:.2f}): {100*f/tot:5.1f}%  ({c} sells)")
hist(rows,"ALL"); hist(W,"WINNERS"); hist(L,"LOSERS")
# scale-out chunk size: fraction per sell among multi-sell positions
chunks=[s["frac"] for r in rows if r["nsells"]>=2 for s in r["sells"]]
print("\nchunk size (frac per sell, multi-sell pos): med",round(st.median(chunks),3),"mean",round(sum(chunks)/len(chunks),3))
firstchunk=[r["sells"][0]["frac"] for r in rows if r["nsells"]>=2]
print("first chunk (multi-sell): med",round(st.median(firstchunk),3))
# winners with runners: distribution of nsells and whether last sell is biggest

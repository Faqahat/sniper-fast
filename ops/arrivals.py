import json,sys,collections,statistics
first=collections.Counter(); lead=collections.defaultdict(list); n=0; cov=collections.Counter()
for l in sys.stdin:
    d=json.loads(l)
    if "arrivals" not in d: continue
    a=d["arrivals"]; n+=1; first[d.get("first_feed")]+=1
    for f in a: cov[f]+=1
    h=a.get("haan-deshred")
    if h is None: continue
    for f,t in a.items():
        if f!="haan-deshred": lead[f].append((h-t)/1e6)
def pct(v,p): v=sorted(v); return v[min(len(v)-1,int(len(v)*p))]
print("records",n)
print("first feed share:",{k:f"{v/n*100:.1f}%" for k,v in first.most_common()})
print("coverage (seen by feed):",{k:f"{v/n*100:.1f}%" for k,v in cov.most_common()})
for f,v in lead.items():
    print(f"{f:20s} ahead of haan-deshred: p10 {pct(v,.1):.2f} p50 {pct(v,.5):.2f} p90 {pct(v,.9):.2f} ms; ahead in {sum(1 for x in v if x>0)/len(v)*100:.0f}%  (n={len(v)})")

import json
rows=[]
for ln in open("/root/gs_clean/paths.jsonl"):
    try: d=json.loads(ln)
    except: continue
    if not isinstance(d,dict): continue
    p=d.get("path")
    if not isinstance(p,list) or len(p)<2 or p[0][1]>=2.0: continue
    rows.append((d.get("dev",0.0), p, d.get("peak",1.0), p[0][1]))
FEE=0.0125; FIX=0.000365
def pnl(path, entry_r, ride=1.3, trail=0.95, cap_ms=3200):
    peak=entry_r; riding=False; exit_r=None
    for t,r in path:
        if t>cap_ms: break
        if r>peak: peak=r
        if not riding and r/entry_r>=ride: riding=True
        if riding and r<=peak*trail: exit_r=r; break
    if exit_r is None:
        w=[r for t,r in path if t<=cap_ms]; exit_r=w[-1] if w else entry_r
    return (exit_r/entry_r)*(1-FEE)-(1+FEE)-2*FIX
def report(lo,hi,tag):
    sub=[r for r in rows if lo<=r[0]<hi]
    if not sub: print(f"{tag}: n=0"); return
    for mode,efn in [("FLOOR(r=1.0)",lambda s:1.0),("FIRST-READABLE",lambda s:s[3])]:
        v=sorted(pnl(p,efn((dev,p,pk,e))) for dev,p,pk,e in sub); n=len(v); k=max(1,n//10)
        print(f"  {tag} dev{lo}-{hi} n={n} [{mode}]: mean={sum(v)/n:+.4f} med={v[n//2]:+.4f} win={100*sum(1 for x in v if x>0)/n:.0f}% exT10={sum(v[:-k])/(n-k):+.4f}")
    # median first-readable entry multiple (how far above floor is our realistic entry?)
    es=sorted(e for dev,p,pk,e in sub)
    print(f"      median first-readable entry = {es[len(es)//2]:.3f}x floor (deeper dev should be closer to 1.0)")
for lo,hi,t in [(0,0.001,"DEAD"),(0.5,1.0,"MID"),(1.0,8.0,"BIG"),(0.5,8.0,"dev>=0.5")]:
    report(lo,hi,t)

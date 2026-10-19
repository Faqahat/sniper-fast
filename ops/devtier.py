import json, statistics
rows=[]
for ln in open("/root/gs_clean/paths.jsonl"):
    try: d=json.loads(ln)
    except: continue
    if not isinstance(d,dict): continue
    p=d.get("path"); 
    if not isinstance(p,list) or len(p)<2: continue
    if p[0][1]>=2.0: continue  # graduated misread
    rows.append((d.get("dev",0.0), p, d.get("peak",1.0)))
FEE=0.0125; FIX=0.000365
def pnl(path, entry_r, ride=1.3, trail=0.95, cap_ms=3200):
    # entry at entry_r (first-readable, NO floor assumption); ride/trail on r/entry
    peak=entry_r; riding=False; exit_r=None
    for t,r in path:
        if t>cap_ms: break
        if r>peak: peak=r
        if not riding and r/entry_r>=ride: riding=True
        if riding and r<=peak*trail: exit_r=r; break
    if exit_r is None:
        w=[r for t,r in path if t<=cap_ms]; exit_r=w[-1] if w else entry_r
    return (exit_r/entry_r)*(1-FEE) - (1+FEE) - 2*FIX
def report(lo,hi,tag):
    sub=[(dev,p,pk) for dev,p,pk in rows if lo<=dev<hi]
    if not sub: print(f"{tag}: n=0"); return
    # entry WITHOUT floor = first-readable price = path[0] r
    vals=[pnl(p, p[0][1]) for dev,p,pk in sub]
    vals.sort(); n=len(vals)
    k=max(1,n//10)
    runners=sum(1 for dev,p,pk in sub if pk>=2.0)
    print(f"{tag} (dev {lo}-{hi} SOL): n={n} mean={sum(vals)/n:+.4f} median={vals[n//2]:+.4f} win={100*sum(1 for x in vals if x>0)/n:.0f}% exT10={sum(vals[:-k])/(n-k):+.4f} runners(peak>=2)={runners}({100*runners/n:.0f}%)")
print("=== ENTRY WITHOUT FLOOR (first-readable), ride1.3/trail0.95 ===")
report(0,0.001,"DEAD dev~0")
report(0.001,0.5,"tiny 0-0.5")
report(0.5,1.0,"MID 0.5-1")
report(1.0,8.0,"BIG 1-8")
report(0.5,8.0,"ALL dev>=0.5")
report(1.0,8.0,"ALL dev>=1")

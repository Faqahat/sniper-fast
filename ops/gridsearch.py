import json, sys, itertools
PATHS="/root/arbx-fast/paths.jsonl"
rows=[]
for line in open(PATHS):
    try: d=json.loads(line)
    except: continue
    rows.append((d.get("vanilla",True), d.get("peak",1.0), d["path"]))
N=len(rows)
if N<50: print(f"only {N} paths — need more, re-run later"); sys.exit()

FEE=0.0125; FIXED_LEG=0.000365; CAP=3200.0
def sim(path, ride, trail, add_thr, add_size, dead_on, vanilla):
    tokens=1.0; cost=1.0; proceeds=0.0; peak=1.0; riding=False; added=False; last_r=1.0
    for ms,r in path:
        if tokens<=1e-9: break
        last_r=r
        if r>peak: peak=r
        if add_thr>1.0 and not added and r>=add_thr: tokens+=add_size/r; cost+=add_size; added=True
        if not riding and r>=ride: riding=True
        sell = (riding and r<=peak*trail) or (dead_on and vanilla and ms>=650 and peak<1.01) or (ms>=CAP)
        if sell: proceeds+=tokens*r; tokens=0.0; break
    if tokens>1e-9: proceeds+=tokens*last_r
    legs=3 if added else 2
    return (1-FEE)**2*proceeds - cost - FIXED_LEG*legs, cost

RIDE=[1.15,1.3,1.5,2.0]; TRAIL=[0.90,0.95]; DEAD=[False,True]; ADD=[0.0,1.1,1.2,1.5,2.0]; ADDSZ=[2.0]
results=[]
for ride,trail,dead,addthr,addsz in itertools.product(RIDE,TRAIL,DEAD,ADD,ADDSZ):
    nets=[]; dep=0.0
    for van,peak,path in rows:
        net,cost=sim(path,ride,trail,addthr,addsz,dead,van)
        nets.append(net); dep+=cost
    nets_s=sorted(nets); n=len(nets)
    tot=sum(nets); nps=tot/dep
    e10=(tot-sum(nets_s[-10:]))/(n-10) if n>10 else 0
    win=100*sum(1 for x in nets if x>0)/n
    results.append((nps, tot/n, nets_s[n//2], e10, win, ride,trail,dead,addthr,addsz))
results.sort(reverse=True)
print(f"paths={N}   TOP configs by net-per-SOL (robust = ex-top10 > 0):")
print(f"{'nps':>7} {'mean/t':>7} {'med':>7} {'exT10':>7} {'win':>4}  ride trail dead addThr addSz")
for r in results[:12]:
    nps,mn,md,e10,win,ride,trail,dead,addthr,addsz=r
    flag=" <-ROBUST" if e10>0 and nps>0 else ""
    print(f"{nps:+7.3f} {mn:+7.3f} {md:+7.3f} {e10:+7.3f} {win:3.0f}%  {ride:.2f} {trail:.2f} {str(dead)[0]}  {addthr:.1f}  {addsz:.0f}{flag}")
# base reference: ride1.3 trail0.9 no dead no scale
for r in results:
    if r[5]==1.3 and r[6]==0.90 and not r[7] and r[8]==0.0:
        print(f"\nBASE (ride1.3,trail0.9,no-dead,no-scale): nps={r[0]:+.3f} mean/t={r[1]:+.3f} exT10={r[3]:+.3f} win={r[4]:.0f}%")

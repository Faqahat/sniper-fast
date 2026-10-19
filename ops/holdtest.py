import json,re,statistics,os
CACHE="/root/series_cache.json"
cache=json.load(open(CACHE))
dev={}
for ln in open("/root/arbx-fast/paper_sel.log"):
    m=re.search(r"mint=([1-9A-HJ-NP-Za-km-z]+) dev_buy=(\d+)",ln)
    if m: dev[m.group(1)]=int(m.group(2))
def fp(d): return (30e9+d)**2/(30e9*1.073e15)
K=30e9*1.073e15
def build(mint):
    pts=cache.get(mint,[])
    if len(pts)<3: return None
    pts=sorted(pts,key=lambda x:x[0]); base=min(l for _,l in pts); f=fp(dev.get(mint,0)); t0=pts[0][0]
    series=[((bt-t0),((l-base+30e9)**2/K)/f) for bt,l in pts]
    entry=None
    for t,r in series:
        if t<=10 and r>=1.05: entry=(t,r);break
    if not entry: return None
    et,er=entry
    return er,[(t-et,r) for t,r in series if t>=et]
# FAST (current): derisk30 @entry; ride arms at 1.15; trail 0.95; hard cap 40s
def fast(fwd,er):
    rem=0.70;real=0.0;peak=er;armed=False
    for t,r in fwd:
        if t>40: real+=rem*(r/er-1);rem=0;break
        if r>peak:peak=r
        if r>=1.15*er:armed=True
        if armed and r<=0.95*peak: real+=rem*(r/er-1);rem=0;break
    if rem>0: real+=rem*((fwd[-1][1] if fwd else er)/er-1)
    return real
# HOLD-SMART: derisk15 @entry; DUD-CUT if not >=1.3x by 30s -> exit; else ride LOOSE trail 0.70 no cap
def hold(fwd,er,ride=1.30,dudT=30,trail=0.70):
    rem=0.85;real=0.0;peak=er;armed=False
    for t,r in fwd:
        if r>peak:peak=r
        if r>=ride*er:armed=True
        if not armed and t>=dudT:   # dud-cut
            real+=rem*(r/er-1);rem=0;break
        if armed and r<=trail*peak: # loose runner trail
            real+=rem*(r/er-1);rem=0;break
    if rem>0: real+=rem*((fwd[-1][1] if fwd else er)/er-1)
    return real
rows=[]
for mint in cache:
    b=build(mint)
    if not b: continue
    er,fwd=b; peak=max(r for _,r in fwd)
    rows.append((mint[:8],er,peak,fast(fwd,er),hold(fwd,er)))
rows.sort(key=lambda x:-x[2])
print(f"{'mint':9} {'entry':>5} {'peak':>5} {'FAST':>8} {'HOLD':>8}")
for m,er,pk,fa,ho in rows:
    flag=" RUNNER" if pk>=1.5 else ""
    print(f"{m:9} {er:>5.2f} {pk:>5.2f} {fa:>+8.3f} {ho:>+8.3f}{flag}")
F=[r[3] for r in rows];H=[r[4] for r in rows];n=len(rows)
print(f"\nn={n}")
print(f"FAST: total={sum(F):+.3f} mean={sum(F)/n:+.3f} median={statistics.median(F):+.3f} win%={sum(1 for x in F if x>0)/n*100:.0f}")
print(f"HOLD: total={sum(H):+.3f} mean={sum(H)/n:+.3f} median={statistics.median(H):+.3f} win%={sum(1 for x in H if x>0)/n*100:.0f}")
run=[r for r in rows if r[2]>=1.5]
if run:
    print(f"on {len(run)} RUNNERS (peak>=1.5x): FAST captured {sum(r[3] for r in run):+.3f}, HOLD captured {sum(r[4] for r in run):+.3f}")

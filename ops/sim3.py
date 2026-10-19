import json,statistics as st
PATHS="/root/arbx-fast/paths.jsonl"
FEE=0.0125; FIXED=0.000365; CAP=3200.0; RCAP=20.0
kept=[]
for line in open(PATHS):
    try: d=json.loads(line)
    except: continue
    if not isinstance(d,dict): continue
    p=d.get("path"); pk=d.get("peak")
    if not isinstance(p,list) or not isinstance(pk,(int,float)) or len(p)<2: continue
    if not all(isinstance(pt,list) and len(pt)==2 and all(isinstance(x,(int,float)) for x in pt) for pt in p): continue
    if p[0][1]>=2.0 or pk>=RCAP-1e-6: continue
    kept.append((float(pk),[(float(a),float(b)) for a,b in p]))
N=len(kept)
def ride_exit(path):
    peak=1.0;riding=False;last=path[0][1]
    for ms,r in path:
        last=r
        if r>peak:peak=r
        if not riding and r>=1.3:riding=True
        if (riding and r<=peak*0.95) or ms>=CAP:return r
    return last
def bn(path,size):
    return (size*ride_exit(path))*(1-FEE)-size-FEE*size-FIXED*2
full=sorted((bn(p,1.0) for pk,p in kept),reverse=True)
tot=sum(full)
print(f"FULL-on-all total={tot:+.2f}")
for k in [1,5,10,20,50]:
    print(f"  top {k:2} launches = {sum(full[:k]):+8.2f}  ({100*sum(full[:k])/tot:4.1f}% of net)   rest={sum(full[k:]):+8.2f}")
print(f"  median net/launch={st.median(full):+.5f}")
print("\nUniform-tiny size sweep (net/SOL shows fixed-fee floor):")
for sz in [0.02,0.05,0.1,0.15,0.2,0.3,0.5,1.0]:
    t=sum(bn(p,sz) for pk,p in kept)
    print(f"  size={sz:4.2f}  tot={t:+8.2f}  net/SOL={t/(N*sz):+.4f}  capT0/l={sz}")

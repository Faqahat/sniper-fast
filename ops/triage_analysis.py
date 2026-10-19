import json, statistics as st
PATHS="/root/arbx-fast/paths.jsonl"

# ---------- load, dedupe, parse-robust ----------
rows=[]; mints=set(); bad=0; dup=0
for line in open(PATHS):
    try: d=json.loads(line)
    except: bad+=1; continue
    if "mint" not in d or "path" not in d or not d["path"]: continue
    if d["mint"] in mints: dup+=1; continue
    mints.add(d["mint"]); rows.append(d)

# ---------- misread flag ----------
# cap=20 flat-from-t0 => graduated-token misread. Flag peak>=20 OR r0>=10 (impossible genuine floor-entry same-slot).
def is_misread(r):
    p=r["path"]; peak=r.get("peak",1.0); r0=p[0][1]
    return peak>=19.999 or r0>=10.0

clean=[r for r in rows if not is_misread(r)]
misreads=[r for r in rows if is_misread(r)]

# ---------- exit replay (entry at floor=1.0, ride1.3 trail0.95, no scale, no dead-cut) ----------
FEE=0.0125; FIXED_LEG=0.000365; TIMECAP_MS=3200.0
def net_floor(path, ride=1.3, trail=0.95, entry=1.0):
    # buy 1 SOL worth at 'entry' price-ratio; tokens = 1/entry (in r-units proceeds)
    tokens=1.0/entry; cost=1.0; proceeds=0.0; peak=entry; riding=False; last=path[0][1]
    for ms,r in path:
        last=r
        if r>peak: peak=r
        if not riding and r>=ride: riding=True
        if (riding and r<=peak*trail) or ms>=TIMECAP_MS:
            proceeds+=tokens*r; tokens=0.0; break
    if tokens>1e-9: proceeds+=tokens*last
    return (1-FEE)**2*proceeds - cost - FIXED_LEG*2

def peak_of(r): return r.get("peak",1.0)

for r in rows:
    r["_net"]=net_floor(r["path"])
    r["_peak"]=peak_of(r)
    r["_r0"]=r["path"][0][1]
    # 1-slot peek feature: r at ~250-400ms (second point)
    r["_peek"]=r["path"][1][1] if len(r["path"])>1 else r["path"][0][1]

def stats(subset,label):
    nets=[r["_net"] for r in subset]; n=len(nets)
    if n==0: print(f"{label}: EMPTY"); return
    tot=sum(nets); mean=tot/n; med=st.median(nets)
    win=100*sum(1 for x in nets if x>0)/n
    nets_s=sorted(nets)
    k=max(1,n//10)
    exT=sum(nets_s[:-k])/(n-k) if n>k else 0
    print(f"{label:34s} n={n:4d} tot={tot:+8.2f} mean={mean:+.3f} med={med:+.3f} win={win:4.1f}% exTop10%mean={exT:+.3f}")

print("=== PARSE ===")
print(f"raw unique={len(rows)} bad={bad} dup={dup} | misreads(cap20/r0>=10)={len(misreads)} clean={len(clean)}")
print()
print("=== WINNER BASE RATES & FAT TAIL (clean universe, floor-entry ride1.3/trail0.95) ===")
cn=[r for r in clean]
nets=sorted((r["_net"] for r in cn))
N=len(cn); TOT=sum(nets)
w_net=[r for r in cn if r["_net"]>0]
w_pk2=[r for r in cn if r["_peak"]>=2.0]
print(f"clean N={N}  total net={TOT:+.2f}")
print(f"winner by net>0 : {len(w_net)} ({100*len(w_net)/N:.1f}%)  carry net={sum(r['_net'] for r in w_net):+.2f}")
print(f"winner by peak>=2: {len(w_pk2)} ({100*len(w_pk2)/N:.1f}%)")
# fat tail: share of total POSITIVE net from top decile of winners
pos=sorted((r["_net"] for r in cn if r["_net"]>0),reverse=True)
tp=sum(pos); top10=sum(pos[:max(1,len(pos)//10)])
print(f"top 10% of winners carry {100*top10/tp:.0f}% of gross positive net  (gross pos={tp:+.2f})")
print()
stats(rows,"ALL raw (incl misreads)")
stats(clean,"CLEAN (misreads removed)")
print()

# ---------- t=0 feature: dev buckets x vanilla ----------
print("=== t=0 FEATURES on CLEAN universe ===")
def bucket_dev(d):
    if d==0: return "dev=0"
    if d<=2: return "0<dev<=2"
    if d<=5: return "2<dev<=5"
    return "5<dev<=8"
from collections import defaultdict
for van in (True,False):
    print(f"-- vanilla={van} --")
    for b in ("dev=0","0<dev<=2","2<dev<=5","5<dev<=8"):
        sub=[r for r in clean if r.get("vanilla",True)==van and bucket_dev(r.get("dev",0))==b]
        stats(sub,f"   {b}")
print()

# ---------- RANKING TEST: can t=0 features rank winners? ----------
# candidate scores computable at t=0 (NO path). We test ordering vs winner(net>0).
def gini_lift(score_fn,label,universe):
    # sort desc by score, sweep: fire on top X%, measure winner-retention & net captured
    uni=sorted(universe,key=score_fn,reverse=True)
    totw=sum(1 for r in uni if r["_net"]>0)
    totnet=sum(r["_net"] for r in uni)
    N=len(uni)
    print(f"  [{label}] N={N} winners={totw} totnet={totnet:+.2f}")
    for frac in (0.25,0.5,0.75):
        k=int(N*frac)
        fired=uni[:k]
        wr=sum(1 for r in fired if r["_net"]>0)
        nt=sum(r["_net"] for r in fired)
        print(f"     fire top {int(frac*100):3d}% (n={k:4d}): winner-retain={100*wr/totw:5.1f}%  net-capture={100*nt/totnet if totnet else 0:5.1f}%  mean={nt/k if k else 0:+.3f}")

import random
rnd=random.Random(42)
print("=== RANKING by t=0 score (winner=net>0), clean universe ===")
# score A: dev amount (higher dev first)
gini_lift(lambda r:(r.get("dev",0), rnd.random()),"dev desc",clean)
# score B: vanilla==0 preferred then dev
gini_lift(lambda r:(0 if r.get("vanilla",True) else 1, r.get("dev",0), rnd.random()),"nonvanilla-first then dev",clean)
# score C: random baseline
gini_lift(lambda r:rnd.random(),"RANDOM baseline",clean)
print()

# ---------- 1-slot peek variant ----------
print("=== 1-SLOT DEMAND PEEK variant (observe r at ~250ms = path[1]) ===")
# If we wait 1 slot we FORFEIT floor entry: entry = r at peek time (we pay the elevated price).
for r in rows:
    r["_net_peek"]=net_floor(r["path"], entry=max(1.0,r["_peek"]))
# ranking by peek value, but net uses the WORSE entry
uni=sorted(clean,key=lambda r:(r["_peek"],rnd.random()),reverse=True)
totw_floor=sum(1 for r in clean if r["_net"]>0)
print("  Ranking power of peek (does early r separate eventual winners? using FLOOR net as truth):")
N=len(uni)
for frac in (0.25,0.5,0.75):
    k=int(N*frac); fired=uni[:k]
    wr=sum(1 for r in fired if r["_net"]>0)
    print(f"     peek-rank top {int(frac*100)}%: winner-retain(floor-truth)={100*wr/totw_floor:.1f}%")
print("  Cost of waiting 1 slot (entry at peek price instead of floor):")
stats_fn_net=[r["_net"] for r in clean]
stats_fn_peek=[r["_net_peek"] for r in clean]
print(f"     floor-entry  total={sum(stats_fn_net):+.2f} mean={sum(stats_fn_net)/len(clean):+.3f}")
print(f"     peek-entry(+1 slot) total={sum(stats_fn_peek):+.2f} mean={sum(stats_fn_peek)/len(clean):+.3f}")
print(f"     peek-entry win%={100*sum(1 for x in stats_fn_peek if x>0)/len(clean):.1f}%  vs floor win%={100*sum(1 for x in stats_fn_net if x>0)/len(clean):.1f}%")

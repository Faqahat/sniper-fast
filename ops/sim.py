import json, itertools, random, statistics as st

PATHS="/root/arbx-fast/paths.jsonl"
FEE=0.0125            # 1% pump + 0.25% slip per leg (%-fee)
FIXED=0.000365        # fixed base+prio per leg (SOL)
CAP=3200.0            # 3.2s cap
RCAP=20.0             # r-cap sentinel

# ---------- CLEAN ----------
raw=0; kept=[]
corrupt=0; misread=0
for line in open(PATHS):
    raw+=1
    try: d=json.loads(line)
    except: corrupt+=1; continue
    if not isinstance(d,dict): corrupt+=1; continue
    p=d.get("path"); pk=d.get("peak")
    if not isinstance(p,list) or not isinstance(pk,(int,float)) or len(p)<2: corrupt+=1; continue
    ok=True
    for pt in p:
        if not (isinstance(pt,list) and len(pt)==2 and isinstance(pt[0],(int,float)) and isinstance(pt[1],(int,float))): ok=False; break
    if not ok: corrupt+=1; continue
    r0=p[0][1]
    # graduated-token misread: starts high or pinned at cap from t=0
    if r0>=2.0 or r0>=RCAP-1e-6 or pk>=RCAP-1e-6: misread+=1; continue
    kept.append((bool(d.get("vanilla",True)), float(pk), [(float(a),float(b)) for a,b in p], float(d.get("dev",0.0))))
N=len(kept)
print(f"RAW lines={raw}  corrupt/invalid={corrupt}  graduated-misreads={misread}  CLEAN N={N}")
runners2=sum(1 for v,pk,p,dv in kept if pk>=2.0)
runners3=sum(1 for v,pk,p,dv in kept if pk>=3.0)
print(f"runners peak>=2: {runners2} ({100*runners2/N:.1f}%)   peak>=3: {runners3} ({100*runners3/N:.1f}%)")

# ---------- EXIT REPLAY on a position with given entry tokens/cost ----------
def ride_exit(path, ride, trail):
    """return (exit_r, exit_ms) given ride/trail ladder + cap. peak tracked from t0."""
    peak=1.0; riding=False; last=path[0][1]
    for ms,r in path:
        last=r
        if r>peak: peak=r
        if not riding and r>=ride: riding=True
        if (riding and r<=peak*trail) or ms>=CAP:
            return r, ms
    return last, path[-1][0]

def r_at(path, t):
    """first sample r at ms>=t; None if none."""
    for ms,r in path:
        if ms>=t: return r,ms
    return None,None

# ---------- BASELINE: buy 1.0 at floor, exit ride/trail ----------
def baseline_net(path, size=1.0, ride=1.3, trail=0.95):
    tokens=size/1.0
    exr,_=ride_exit(path,ride,trail)
    gross=tokens*exr
    legs=2
    net = gross*(1-FEE) - size - FEE*size - FIXED*legs
    return net

# ---------- SCOUT-THEN-ADD ----------
def scout_net(path, scout, add_thr, add_t, add_sz, slot_ms, ride=1.3, trail=0.95):
    # scout buy at floor t=0
    tokens=scout/1.0
    cost=scout
    buy_notional=scout
    legs=1  # scout buy
    added=False
    # decide exit first? exit may happen before add_t. Simulate sequential.
    peak=1.0; riding=False; last=path[0][1]; exr=None
    # peek r at add_t
    rp,_=r_at(path, add_t)
    # add entry price = r observed one slot later (landing +1)
    r_entry_add,_=r_at(path, add_t+slot_ms)
    for ms,r in path:
        last=r
        if r>peak: peak=r
        # add decision at add_t
        if (not added) and ms>=add_t and rp is not None and rp>=add_thr and r_entry_add is not None:
            tokens+=add_sz/r_entry_add
            cost+=add_sz; buy_notional+=add_sz; legs+=1; added=True
        if not riding and r>=ride: riding=True
        if (riding and r<=peak*trail) or ms>=CAP:
            exr=r; break
    if exr is None: exr=last
    legs+=1  # sell leg
    gross=tokens*exr
    net = gross*(1-FEE) - cost - FEE*buy_notional - FIXED*legs
    return net, added, cost

# ---------- run baseline ----------
base_nets=[baseline_net(p) for v,pk,p,dv in kept]
base_tot=sum(base_nets)
print(f"\nBASELINE buy-1.0-on-all ride1.3/trail0.95:")
print(f"  total net={base_tot:+.3f}  mean/launch={base_tot/N:+.4f}  median={st.median(base_nets):+.4f}  win%={100*sum(1 for x in base_nets if x>0)/N:.1f}")
print(f"  capital deployed total={N*1.0:.0f} SOL   peak-at-t0 per launch=1.0 SOL")
# runner capture baseline = 100% (buys all)

# ---------- SWEEP scout-then-add ----------
print(f"\nSCOUT-THEN-ADD sweep (ride1.3/trail0.95, slot=250ms):")
print(f"{'scout':>5} {'thr':>5} {'addt':>5} {'addsz':>5} | {'totnet':>8} {'mean/l':>8} {'med':>7} {'win%':>5} {'added%':>6} {'drag':>7} {'cap@t0':>7} {'totcap':>7} {'capR2%':>6} {'capR3%':>6}")
configs=[]
for scout in [0.05,0.1,0.15,0.2]:
 for add_thr in [1.03,1.05,1.1,1.2]:
  for add_t in [250,400]:
   for add_sz in [1.0,2.0,3.0]:
    nets=[]; added_ct=0; drag=0.0; totcap=0.0
    capr2=0; capr3=0  # runners captured (scout present = always); but count runners that we ADDED on
    r2_added=0; r3_added=0
    for v,pk,p,dv in kept:
        net,added,cost=scout_net(p,scout,add_thr,add_t,add_sz,250)
        nets.append(net); totcap+=cost
        if added: added_ct+=1
        else: drag+=net  # fee drag = net of scouts that never added (mostly negative)
        if pk>=2.0 and added: r2_added+=1
        if pk>=3.0 and added: r3_added+=1
    tot=sum(nets)
    capt0=scout  # per-launch t=0 commitment
    # runners captured: ALL runners get a scout (100%); fraction we ADDED on:
    capr2=100*r2_added/runners2 if runners2 else 0
    capr3=100*r3_added/runners3 if runners3 else 0
    configs.append((tot, tot/N, st.median(nets), 100*sum(1 for x in nets if x>0)/N, 100*added_ct/N, drag, capt0, totcap, capr2, capr3, scout,add_thr,add_t,add_sz))
configs.sort(reverse=True)
for c in configs[:15]:
    tot,mn,md,win,addp,drag,capt0,totcap,cr2,cr3,scout,thr,addt,addsz=c
    print(f"{scout:5.2f} {thr:5.2f} {addt:5.0f} {addsz:5.1f} | {tot:+8.2f} {mn:+8.4f} {md:+7.4f} {win:5.1f} {addp:6.1f} {drag:+7.2f} {capt0:7.2f} {totcap:7.0f} {cr2:6.1f} {cr3:6.1f}")

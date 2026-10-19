#!/usr/bin/env python3
"""STEP 2-4 — mirror simulator. Runs SELECTION-MIRROR and COPY-TRADE against his exact 200-token tape.
Reanchors the market price path to OUR entry, applies the CURRENT shipped exit ladder (cut .80, NO fade),
nets pump fee + curve slip + fixed priority. Decomposes the gap: selection / fill / exit / lag."""
import json, statistics as st
from collections import Counter

TAPE = json.load(open("/root/mirror/his_tape.json"))
REPEAT = set(json.load(open("/root/mirror/his_creators.json"))["repeat_creators"])

# ---- cost model (econ_102, agreed) ----
PUMP_FEE=0.01; CURVE_SLIP=0.0025          # per leg
PRIO_LAM=360_000; BASE_LAM=5_000; LSOL=1e9 # 3M cu * 120k / 1e6 ; fixed per leg

# ---- CURRENT SHIPPED ladder (snipe_engine.rs defaults) ----
SHIP=dict(derisk=0.30, ride=1.40, trail=0.92, cut=0.80, ladder=0.25, cap=40)

def reanchor(path, his_fill, buy_slot, entry_dslot):
    """Return seq [(dslot_from_our_entry, r_vs_our_entry)] seeded at entry. path pts are [slot,px]."""
    # r vs his fill first
    pts=sorted(path, key=lambda x:x[0])
    # our entry price = market r at entry_dslot (relative to his fill). lag=0 -> his fill level.
    # build r-vs-his-fill series clamped to sane range
    ser=[]
    for s,px in pts:
        d=s-buy_slot
        r=px/his_fill
        # PREBUY-RAMP FIX: drop same-slot points below his fill (create-slot ramp printed BEFORE his buy)
        if d>=1 and 0.3<=r<=200: ser.append((d,r))
        elif d==0 and 1.0<=r<=200: ser.append((d,r))
    # entry r (our fill level) = interpolate/last r at entry_dslot, default 1.0 at lag 0
    entry_r=1.0
    for d,r in ser:
        if d<=entry_dslot: entry_r=r
        else: break
    if entry_dslot==0: entry_r=1.0
    # seq from our entry onward, reanchored to our entry_r
    seq=[(0,1.0)]
    for d,r in ser:
        if d>=entry_dslot:
            seq.append((d-entry_dslot, r/entry_r))
    seq.sort()
    return seq, entry_r

def ladder(seq, P):
    remaining=1.0; peak=1.0; riding=False; first=True; last_sell=0; legs=[]
    for (d,rr) in seq:
        if remaining<=1e-9: break
        if rr>peak: peak=rr
        if not riding and rr>=P["ride"]: riding=True
        if first:
            first=False; q=min(P["derisk"],remaining); legs.append((rr,q,"derisk")); remaining-=q; last_sell=d; continue
        if rr<=P["cut"]: legs.append((rr,remaining,"cut")); remaining=0; break
        if riding and rr<=peak*P["trail"]: legs.append((rr,remaining,"trail")); remaining=0; break
        if d>=P["cap"]: legs.append((rr,remaining,"cap")); remaining=0; break
        # NO fade leg (shipped engine removed it)
        if (not riding) and 1.0<=rr<P["ride"] and (d-last_sell)>=4:
            q=min(remaining*P["ladder"],remaining); legs.append((rr,q,"ladder")); remaining-=q; last_sell=d
    if remaining>1e-9: legs.append((seq[-1][1],remaining,"end")); remaining=0
    return legs

def net_R(legs, size):
    sell_hair=PUMP_FEE+CURVE_SLIP
    proceeds=sum(f*rr*(1-sell_hair) for rr,f,_ in legs)
    buy_cost=1.0+PUMP_FEE+CURVE_SLIP
    gross=proceeds-buy_cost
    n_legs=1+len(legs)
    fixed=n_legs*(PRIO_LAM+BASE_LAM)/LSOL/size
    return gross-fixed, gross

def sim_token(t, P, entry_dslot, size):
    if not t["has_path"]: return None
    seq,entry_r=reanchor(t["path"], t["his_fill_px"], t["buy_slot"], entry_dslot)
    if len(seq)<1: return None
    legs=ladder(seq,P)
    net,gross=net_R(legs,size)
    return {"net":net,"gross":gross,"entry_r":entry_r,"legs":legs,"term":legs[-1][2] if legs else None}

def agg(vals):
    v=[x for x in vals if x is not None]
    if not v: return None
    n=len(v); tot=sum(v); win=sum(1 for x in v if x>0)/n
    return dict(n=n, total=tot, mean=tot/n, median=st.median(v), win=win)

def corr(a,b):
    pairs=[(x,y) for x,y in zip(a,b) if x is not None and y is not None]
    if len(pairs)<3: return None
    xs,ys=zip(*pairs)
    mx,my=sum(xs)/len(xs),sum(ys)/len(ys)
    num=sum((x-mx)*(y-my) for x,y in pairs)
    dx=sum((x-mx)**2 for x in xs)**.5; dy=sum((y-my)**2 for y in ys)**.5
    return num/(dx*dy) if dx and dy else None

SIZE=0.5
tape_path=[t for t in TAPE if t["has_path"]]
print(f"tape with path: {len(tape_path)}/{len(TAPE)}")

# his per-token R and SOL
his_R={t["mint"]: t["realized_R"] for t in TAPE}
his_SOL={t["mint"]: t["realized_sol"] for t in TAPE}
his_sol_in={t["mint"]: t["sol_in"] for t in TAPE}

# ============ SELECTION-MIRROR (independent same-slot entry = his fill moment) ============
print("\n"+"="*78)
print("MODE A: SELECTION-MIRROR  (enter same-slot at his fill level; OUR shipped ladder)")
print("="*78)
mirA={}
for t in tape_path:
    r=sim_token(t,SHIP,0,SIZE)
    mirA[t["mint"]]=r["net"] if r else None
# aggregate over ALL his tokens (we pick every one of his)
his_on_path=[his_R[t["mint"]] for t in tape_path]
ourA=[mirA[t["mint"]] for t in tape_path]
# size-normalized R comparison and SOL at 0.5
print("  (per-token net R, size=0.5 SOL)")
print("  HIS  :", agg(his_on_path))
print("  OURS :", agg(ourA))
print("  corr(his_R, our_R) =", round(corr(his_on_path,ourA),3))
sign=sum(1 for h,o in zip(his_on_path,ourA) if h is not None and o is not None and (h>0)==(o>0))
print("  sign agreement =", round(sign/len(tape_path),3))
# SOL terms: his actual SOL vs our SOL at 0.5 size
our_sol=[mirA[t["mint"]]*SIZE for t in tape_path if mirA[t["mint"]] is not None]
his_sol=[his_SOL[t["mint"]] for t in tape_path]
print(f"  HIS total SOL (actual sizes, on-path n={len(his_sol)}): {sum(his_sol):+.2f}")
print(f"  OUR total SOL @0.5 each: {sum(our_sol):+.2f}   (his would be {sum(0.5*his_R[t['mint']] for t in tape_path):+.2f} at 0.5 flat)")

# ============ creator-selection vs generic dev-filter subsets ============
print("\n"+"-"*78)
print("SELECTION SUBSETS (which of his tokens each rule would independently pick)")
print("-"*78)
def subset_report(name, members):
    ms=[t for t in members if t["has_path"]]
    hh=[his_R[t["mint"]] for t in ms]
    oo=[mirA[t["mint"]] for t in ms]
    a_h=agg(hh); a_o=agg(oo)
    hisSOL=sum(his_SOL[t["mint"]] for t in ms)
    print(f"  {name:28s} picks={len(members):3d} (on-path {len(ms)})  HISsol={hisSOL:+7.2f}  "
          f"HIS meanR={a_h['mean']:+.3f} win={a_h['win']:.2f} | OUR meanR={a_o['mean']:+.3f} "
          f"OURtotSOL@0.5={a_o['total']*SIZE:+.2f} win={a_o['win']:.2f}")
    return len(members), hisSOL, a_o["total"]*SIZE if a_o else 0

allpicks=TAPE
repeat_pick=[t for t in TAPE if t["creator"] in REPEAT]
dev2_pick=[t for t in TAPE if (t["dev_buy_sol"] or 0)>=2.0 and t.get("vanilla")!=False or (t["wire_dev_sol"] or 0)>=2.0]
dev2_strict=[t for t in TAPE if (t["dev_buy_sol"] or 0)>=2.0]
dev03_pick=[t for t in TAPE if (t["dev_buy_sol"] or 0)>=0.3]
subset_report("ALL his tokens (pick all)", allpicks)
subset_report("CREATOR-match (repeat devs)", repeat_pick)
subset_report("generic dev_buy>=2.0", dev2_strict)
subset_report("generic dev_buy>=0.3", dev03_pick)

# ============ MODE B: COPY-TRADE (lag 0/1/2) ============
print("\n"+"="*78)
print("MODE B: COPY-TRADE  (observe his buy, fire after lag slots at curve price then; OUR ladder)")
print("="*78)
for lag in (0,1,2):
    vals=[]; entr=[]
    for t in tape_path:
        r=sim_token(t,SHIP,lag,SIZE)
        vals.append(r["net"] if r else None)
        if r: entr.append(r["entry_r"])
    a=agg(vals)
    print(f"  lag={lag}: OUR meanR={a['mean']:+.4f} win={a['win']:.3f} totR={a['total']:+.2f} "
          f"totSOL@0.5={a['total']*SIZE:+.2f}  median entry_r(vs his fill)={st.median(entr):.3f}  n={a['n']}")
print(f"  HIS (same n): meanR={agg(his_on_path)['mean']:+.4f} totSOL(actual)={sum(his_sol):+.2f}")

json.dump({"mirrorA":mirA}, open("/root/mirror/mirror_results.json","w"))
print("\nwrote /root/mirror/mirror_results.json")

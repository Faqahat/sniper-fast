#!/usr/bin/env python3
"""fading_test: does the exit ladder's eager 'fading' trigger (dump-all the first slot price
ticks below entry) clip dip-then-rip RUNNERS? Replay exit variants on the SAME unbiased entries
(entry=floor*1.02, net of all costs), out-of-sample (train/val split by slot).

Generalized simulate() = faithful port of econ_102.simulate with a CONFIGURABLE fading rule.
fade_mode: 'instant' (== shipped), 'off', 'patient' (consec-slots>=N or r<deep)."""
import json, statistics as st, sys
sys.path.insert(0, "/root/econ_102")
import econ102 as E

PUMP_FEE, CURVE_SLIP_LEG = E.PUMP_FEE, E.CURVE_SLIP_LEG
PRIO_LAMPORTS, BASE_LAMPORTS, LAMPORTS_SOL = E.PRIO_LAMPORTS, E.BASE_LAMPORTS, E.LAMPORTS_SOL
STEP_SLOTS = E.STEP_SLOTS

def simulate(entry_px, entry_slot, series, P, SIZE):
    """P keys: derisk_frac, ride_mult, trail_frac, cut_r, ladder_frac, cap_slots,
    fade_mode in {instant,off,patient}, fade_consec_n, fade_deep."""
    fade_mode = P.get("fade_mode", "instant")
    fade_n    = P.get("fade_consec_n", 1)
    fade_deep = P.get("fade_deep", -1.0)
    amount=1.0; remaining=amount; peak_r=1.0; riding=False; first=True
    last_sell_slot=entry_slot; sol_out=0.0; legs=0
    sell_haircut = PUMP_FEE + CURVE_SLIP_LEG
    below_slots=set()
    def do_sell(frac, px):
        nonlocal sol_out
        sol_out += frac*(px/entry_px)*(1-sell_haircut)
    polls = [(entry_slot, entry_px)] + [(s,p) for (s,p) in series]
    for (slot,px) in polls:
        if remaining <= amount*1e-6: break
        r = px/entry_px
        if r>peak_r: peak_r=r
        if not riding and r>=P["ride_mult"]: riding=True
        age = slot-entry_slot
        # consecutive distinct-slots-below-entry tracker
        if r>=1.0: below_slots=set()
        else: below_slots.add(slot)
        consec = len(below_slots)
        # fading trigger (configurable)
        if fade_mode=="off":
            fade_fire=False
        elif fade_mode=="patient":
            fade_fire = (not riding) and r<1.0 and (consec>=fade_n or r<fade_deep)
        else:  # instant == shipped
            fade_fire = (not riding) and r<1.0 and slot>last_sell_slot
        if first:
            qty=amount*P["derisk_frac"]; final=False; first=False
        elif r<=P["cut_r"]:
            qty=remaining; final=True
        elif riding and r<=peak_r*P["trail_frac"]:
            qty=remaining; final=True
        elif age>=P["cap_slots"]:
            qty=remaining; final=True
        elif fade_fire:
            qty=remaining; final=True
        elif (not riding) and 1.0<=r<P["ride_mult"] and (slot-last_sell_slot)>=STEP_SLOTS:
            qty=remaining*P["ladder_frac"]; final=False
        else:
            qty=0.0; final=False
        qty=min(qty,remaining)
        if qty>0:
            do_sell(qty,px); remaining-=qty; last_sell_slot=slot; legs+=1
            if final or remaining<=amount*1e-6: break
    if remaining>amount*1e-6:
        lastpx = series[-1][1] if series else entry_px
        do_sell(remaining,lastpx); legs+=1
    buy_cost = 1.0 + PUMP_FEE + CURVE_SLIP_LEG
    gross = sol_out - buy_cost
    n_legs_total = 1 + legs
    fixed_frac = n_legs_total*(PRIO_LAMPORTS+BASE_LAMPORTS)/LAMPORTS_SOL/SIZE
    net = gross - fixed_frac
    return net

def peak_of(f):
    e=f["entry"]; ser=f["path"]
    return (max([p[1] for p in ser], default=e))/e

def stats(pnls):
    if not pnls: return None
    n=len(pnls); s=sorted(pnls)
    mean=sum(pnls)/n; tot=sum(pnls); win=sum(1 for p in pnls if p>0)/n
    return {"n":n,"mean":mean,"median":st.median(pnls),"win":win,"tot":tot}

def evalc(feats, P, SIZE=0.5):
    return [simulate(f["entry"],f["entry_slot"],f["path"],P,SIZE) for f in feats]

# ---------------- load + split ----------------
rows=E.load_backtest(); FEATS=E.build_feats(rows)
for f in FEATS: f["peak"]=peak_of(f)
FEATS.sort(key=lambda f:f["slot"])
mid=len(FEATS)//2
TRAIN=FEATS[:mid]; VAL=FEATS[mid:]

# sanity: reproduce econ102 current baseline (instant fade) exactly
SHIP=dict(E.SHIP); SHIP["fade_mode"]="instant"
mine=evalc(FEATS, SHIP, 0.5)
ref =[E.simulate(f["entry"],f["entry_slot"],f["path"],E.SHIP,0.5)[0] for f in FEATS]
maxdiff=max(abs(a-b) for a,b in zip(mine,ref))
print("SANITY max|mine-econ102| =", maxdiff, "(should be ~0)")
print("current full-sample:", {k:round(v,4) for k,v in stats(mine).items()})

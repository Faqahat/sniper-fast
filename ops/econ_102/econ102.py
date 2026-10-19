#!/usr/bin/env python3
"""econ_102: Is the pump.fun sniper net +EV at our REAL priority-fee fill (floor*1.02)?
Entry = floor_price * 1.02 (measured live, cu_price=3M, median fill ratio). r defined at THIS entry.
Path = full create-slot-anchored trade series (we land in the create slot ~first; the whole path is our sell path).
Reuses the shipped exit ladder (faithful port) + the proven cost-model reconciliation:
  - pump protocol fee  : 1%/leg  (buy + each sell leg)             -> ~2% round-trip, size-independent %
  - curve slippage     : 0.25%/leg flat                            -> ~0.5% round-trip (recon: small-size)
  - priority fee       : 3M cu_price * 120k cu_limit = 360k lamports/leg FIXED (buy + each sell leg)
  - base tx fee        : 5000 lamports/leg FIXED
Fixed lamport costs divided by position SIZE -> their % drag depends on size (the point of the 3-size sweep).
Historical/paper replay only. No live trading."""
import json, statistics as st, itertools, sys

PUMP_FEE        = 0.01       # 1%/leg protocol fee
CURVE_SLIP_LEG  = 0.0025     # 0.25%/leg curve slippage -> ~0.5% round-trip (per recon, small size)
PRIO_LAMPORTS   = 360_000    # 3M cu_price * 120k cu_limit / 1e6
BASE_LAMPORTS   = 5_000
LAMPORTS_SOL    = 1e9
ENTRY_MULT      = 1.02       # our measured priority-fee fill ratio vs floor (median of 1.010/1.381/1.021)

SHIP = {"derisk_frac":0.30,"ride_mult":1.40,"trail_frac":0.92,"cut_r":0.95,"ladder_frac":0.25,"cap_slots":40}
STEP_SLOTS = 4
DEV_MIN = 2.0

def simulate(entry_px, entry_slot, series, P, SIZE,
             pump_fee=PUMP_FEE, curve_slip=CURVE_SLIP_LEG,
             prio_lam=PRIO_LAMPORTS, base_lam=BASE_LAMPORTS):
    """Faithful shipped exit_ladder. entry_px already includes the *1.02 fill premium; r is relative to it.
    Returns (net_R, gross_R, n_sell_legs)."""
    amount=1.0; remaining=amount; peak_r=1.0; riding=False; first=True
    last_sell_slot=entry_slot; sol_out=0.0; legs=0
    sell_haircut = pump_fee + curve_slip
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
        if first:
            qty=amount*P["derisk_frac"]; final=False; first=False
        elif r<=P["cut_r"]:
            qty=remaining; final=True
        elif riding and r<=peak_r*P["trail_frac"]:
            qty=remaining; final=True
        elif age>=P["cap_slots"]:
            qty=remaining; final=True
        elif (not riding) and r<1.0 and slot>last_sell_slot:
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
    buy_cost = 1.0 + pump_fee + curve_slip                 # % cost on entry
    gross = sol_out - buy_cost
    n_legs_total = 1 + legs                                # 1 buy + sell legs, each a tx paying fixed lamports
    fixed_frac = n_legs_total*(prio_lam+base_lam)/LAMPORTS_SOL/SIZE
    net = gross - fixed_frac
    return net, gross, legs

def gross_only(entry_px, entry_slot, series, P):
    return simulate(entry_px,entry_slot,series,P,SIZE=1e9,pump_fee=0.0,curve_slip=0.0,prio_lam=0,base_lam=0)[0]

def stats(pnls):
    if not pnls: return None
    n=len(pnls); s=sorted(pnls)
    def q(x): return s[min(n-1,int(x*n))]
    mean=sum(pnls)/n; tot=sum(pnls); win=sum(1 for p in pnls if p>0)/n
    top5=sum(sorted(pnls,reverse=True)[:max(1,n//20)])
    sd=st.pstdev(pnls) if n>1 else 0.0
    mean_ex2 = (sum(sorted(pnls,reverse=True)[2:])/n) if n>2 else mean
    return {"n":n,"mean":mean,"median":st.median(pnls),"win":win,"sd":sd,"tot":tot,
            "p10":q(.10),"p90":q(.90),"top5_share":(top5/tot if tot else float('nan')),
            "mean_ex_top2":mean_ex2}

# ---- load unbiased backtest sample ----
def load_backtest():
    CRE=json.load(open("/root/profit_backtest/creates.json"))
    TRAJ={t["mint"]:t for t in json.load(open("/root/profit_backtest/trajectories.json"))}
    rows=[]
    for c in CRE:
        t=TRAJ.get(c["mint"])
        if not t or not t.get("entry_px"): continue
        rows.append({**c,"traj":t})
    return rows

def passes_shipped(c):
    if c["creator_fee_bps"]!=0: return False
    dev=c["dev_buy"]
    if c.get("dev_buy_wire",0)>=1e17: dev=max(dev,DEV_MIN)
    return dev>=DEV_MIN

def build_feats(rows):
    F=[]
    for c in rows:
        if not passes_shipped(c): continue
        t=c["traj"]
        floor=t["entry_px"]
        entry=floor*ENTRY_MULT
        series=[(s,p) for s,p in t["series"]]
        F.append({"slot":c["create_slot"],"entry":entry,"entry_slot":t["create_slot"],
                  "path":series,"cosnip":t["cosnipers"]})
    F.sort(key=lambda f:f["slot"])
    return F

def evalc(feats, P, SIZE):
    return stats([simulate(f["entry"],f["entry_slot"],f["path"],P,SIZE)[0] for f in feats])

def evalc_gross(feats,P):
    return stats([gross_only(f["entry"],f["entry_slot"],f["path"],P) for f in feats])

#!/usr/bin/env python3
"""Core engine for the OUR-FILL expectancy study. Entry = our realized fill (= curve price at create+1,
the first observable/fillable price, ~1.1-1.33x floor per the fill probe). Exit = ladder on the forward
path. REALISTIC cost model (both prior studies omitted the pump 1%/leg protocol fee):
   - pump protocol fee  : PUMP_FEE per leg (buy+each sell), size-independent %.  Default 0.01 (1%).
   - curve-impact slip  : our own price impact selling into the bonding curve, size-dependent.
   - base tx fee        : 5000 lamports/leg fixed (warm TPU path, cu-price=0, no tip).
R = net return as a fraction of position size. size in SOL set by SIZE."""
import os, json, statistics as st

SIZE      = float(os.environ.get("SIZE", "0.165"))   # live cap ~0.165 SOL (canary 0.01); NOT the 2.0 backtest size
PUMP_FEE  = float(os.environ.get("PUMP_FEE", "0.01")) # pump.fun 1%/leg protocol fee
BASE_FEE  = float(os.environ.get("BASE_FEE", "0.000005")) # 5000 lamports/leg
IMPACT_K  = float(os.environ.get("IMPACT_K", "0.0"))  # curve-impact coeff: slip_leg = IMPACT_K * SIZE / reserve. 0 = off
VRESERVE  = float(os.environ.get("VRESERVE", "35.0")) # effective SOL reserve near entry (30 virtual + ~5 real)
STEP_SLOTS = 4

def simulate(entry_px, entry_slot, series, P, extra_slip=0.0):
    """Faithful port of snipe_engine exit_ladder + realistic cost. extra_slip adds a flat per-sell price haircut
    on top of pump fee + curve impact (use for stress)."""
    amount = 1.0; remaining = amount
    peak_r = 1.0; riding = False; first = True
    last_sell_slot = entry_slot; sol_out = 0.0; legs = 0
    # per-sell slippage: pump fee + own curve impact + extra
    impact = (IMPACT_K * SIZE / VRESERVE) if IMPACT_K > 0 else 0.0
    sell_slip = PUMP_FEE + impact + extra_slip
    def do_sell(frac, px):
        nonlocal sol_out
        sol_out += frac * (px/entry_px) * (1 - sell_slip)
    polls = [(entry_slot, entry_px)] + [(s, p) for (s, p) in series]
    for (slot, px) in polls:
        if remaining <= amount*1e-6: break
        r = px/entry_px
        if r > peak_r: peak_r = r
        if not riding and r >= P["ride_mult"]: riding = True
        age = slot - entry_slot
        if first:
            qty = amount*P["derisk_frac"]; final = False; first = False
        elif r <= P["cut_r"]:
            qty = remaining; final = True
        elif riding and r <= peak_r*P["trail_frac"]:
            qty = remaining; final = True
        elif age >= P["cap_slots"]:
            qty = remaining; final = True
        elif (not riding) and r < 1.0 and slot > last_sell_slot:
            qty = remaining; final = True
        elif (not riding) and 1.0 <= r < P["ride_mult"] and (slot-last_sell_slot) >= STEP_SLOTS:
            qty = remaining*P["ladder_frac"]; final = False
        else:
            qty = 0.0; final = False
        qty = min(qty, remaining)
        if qty > 0:
            do_sell(qty, px); remaining -= qty; last_sell_slot = slot; legs += 1
            if final or remaining <= amount*1e-6: break
    if remaining > amount*1e-6:
        lastpx = series[-1][1] if series else entry_px
        do_sell(remaining, lastpx); legs += 1
    # buy-side pump fee: we pay (1+PUMP_FEE) to acquire 1.0 unit worth -> cost basis grows by PUMP_FEE
    buy_cost = 1.0 + PUMP_FEE
    gross = sol_out - buy_cost
    fee_frac = (1 + legs) * BASE_FEE / SIZE
    return gross - fee_frac, gross, legs

def stats(pnls):
    if not pnls: return None
    n=len(pnls); s=sorted(pnls)
    def q(x): return s[min(n-1,int(x*n))]
    mean=sum(pnls)/n; tot=sum(pnls); win=sum(1 for p in pnls if p>0)/n
    top5=sum(sorted(pnls,reverse=True)[:max(1,n//20)])
    sd=st.pstdev(pnls) if n>1 else 0.0
    # tail robustness: mean dropping the top 2 winners
    drop2 = (sum(sorted(pnls,reverse=True)[2:]))/n if n>2 else mean
    return {"n":n,"mean":mean,"median":st.median(pnls),"win":win,"sd":sd,"tot":tot,
            "p10":q(.10),"p90":q(.90),"top5_share":(top5/tot if tot else float('nan')),
            "mean_drop2":drop2,"sharpe":mean/sd if sd>0 else 0.0}

# ---- data loaders ----
def load_backtest():
    CRE=json.load(open("/root/profit_backtest/creates.json"))
    TRAJ={t["mint"]:t for t in json.load(open("/root/profit_backtest/trajectories.json"))}
    rows=[]
    for c in CRE:
        t=TRAJ.get(c["mint"])
        if not t or not t.get("entry_px"): continue
        rows.append({**c,"traj":t})
    return rows

def price_at(traj,k):
    C=traj["create_slot"]; px=traj["entry_px"]
    for s,p in traj["series"]:
        if s<=C+k: px=p
        else: break
    return px
def path_after(traj,k):
    C=traj["create_slot"]; return [(s,p) for s,p in traj["series"] if s>C+k]
def ourfill_entry(traj):
    """entry = curve price at create+1 (our realized fill proxy), path = trades strictly after C+1."""
    return price_at(traj,1), traj["create_slot"]+1, path_after(traj,1)

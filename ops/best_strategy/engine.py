#!/usr/bin/env python3
"""best_strategy unified engine: lot-based sim supporting exit-grid, momentum scale-in,
two-regime (fast-cut/deep-ride), dynamic-hold, re-entry, and position sizing.
Replays the SAME unbiased paths as econ_102 (entry=floor*1.02), net of all costs.
R is measured in units where a full-size position = 1.0 (econ102 convention)."""
import json, statistics as st, sys, random
sys.path.insert(0, "/root/econ_102")
import econ102 as E

PUMP_FEE, CURVE_SLIP = E.PUMP_FEE, E.CURVE_SLIP_LEG     # 0.01 / 0.0025 per leg
PRIO_LAM, BASE_LAM, LAM_SOL = E.PRIO_LAMPORTS, E.BASE_LAMPORTS, E.LAMPORTS_SOL
HAIRCUT = PUMP_FEE + CURVE_SLIP                          # per-leg % (buy adds, sell subtracts)
STEP_SLOTS = E.STEP_SLOTS                                # 4

def simulate(entry_px, entry_slot, series, P, SIZE):
    """Generalized lot-based exit ladder.
    P keys (all optional, default to shipped-like):
      derisk_frac, ride_mult, trail_frac, cut_r, ladder_frac, cap_slots
      fade (bool, default False)
      # scale-in:
      s0 (initial stake units, default 1.0), add_units (default 0.0),
      add_thresh (ratio to trigger add), add_by (max age slots to add),
      # two-regime (applied once riding==True):
      trail_ride (override trail_frac when riding), cap_ride (override cap when riding),
      cut_small (cut_r for the small pre-confirmation stake, if scale-in)
      # dynamic hold:
      dynhold (bool): once riding, exit on first lower-high (new poll's r < peak_r by eps)
      dyn_eps (default 0.0)
    Returns dict: net (R), legs, deployed (max units held * their cost ~ capital), units_bought.
    """
    s0        = P.get("s0", 1.0)
    add_units = P.get("add_units", 0.0)
    add_thresh= P.get("add_thresh", 1.3)
    add_by    = P.get("add_by", 4)
    derisk    = P.get("derisk_frac", 0.0)
    ride_mult = P.get("ride_mult", 1.40)
    trail     = P.get("trail_frac", 0.92)
    cut_r     = P.get("cut_r", 0.80)
    ladder    = P.get("ladder_frac", 0.25)
    cap       = P.get("cap_slots", 40)
    fade      = P.get("fade", False)
    trail_ride= P.get("trail_ride", trail)
    cap_ride  = P.get("cap_ride", cap)
    cut_small = P.get("cut_small", cut_r)
    dynhold   = P.get("dynhold", False)
    dyn_eps   = P.get("dyn_eps", 0.0)

    remaining = s0
    sol_in    = s0 * 1.0 * (1+HAIRCUT)     # initial buy at r=1
    sol_out   = 0.0
    legs      = 1                          # initial buy leg
    units_bought = s0
    added     = (add_units <= 0)           # if no add configured, treat as done
    peak_r    = 1.0
    prev_r    = 1.0
    riding    = False
    first     = True
    last_sell_slot = entry_slot

    def sell(frac_units, r):
        nonlocal sol_out, remaining, legs, last_sell_slot
        q = min(frac_units, remaining)
        if q <= 1e-9: return False
        sol_out += q * r * (1-HAIRCUT)
        remaining -= q
        legs += 1
        return True

    polls = [(entry_slot, entry_px)] + [(s,p) for (s,p) in series]
    for (slot, px) in polls:
        if remaining <= 1e-9: break
        r = px/entry_px
        if r > peak_r: peak_r = r
        age = slot - entry_slot
        if not riding and r >= ride_mult: riding = True

        # effective cut: use cut_small while un-confirmed and still holding only the small stake
        eff_cut = cut_small if (add_units>0 and not added and not riding) else cut_r
        eff_trail = trail_ride if riding else trail
        eff_cap   = cap_ride if riding else cap

        if first:
            first = False
            if derisk > 0:
                sell(remaining*derisk, r)
            prev_r = r
            continue

        # scale-in add (momentum confirmation) -- buy BEFORE exit checks this poll
        if (not added) and r >= add_thresh and age <= add_by:
            q = add_units
            sol_in += q * r * (1+HAIRCUT)
            remaining += q
            units_bought += q
            legs += 1
            added = True
            last_sell_slot = slot
            prev_r = r
            continue   # don't also exit same poll we entered

        final = False
        if r <= eff_cut:
            sell(remaining, r); final = True
        elif riding and r <= peak_r*eff_trail:
            sell(remaining, r); final = True
        elif dynhold and riding and r < prev_r - dyn_eps:
            sell(remaining, r); final = True
        elif age >= eff_cap:
            sell(remaining, r); final = True
        elif fade and (not riding) and r < 1.0 and slot > last_sell_slot:
            sell(remaining, r); final = True
        elif (not riding) and 1.0 <= r < ride_mult and (slot-last_sell_slot) >= STEP_SLOTS:
            sell(remaining*ladder, r)
        prev_r = r
        if final or remaining <= 1e-9: break

    if remaining > 1e-9:
        lastr = (series[-1][1]/entry_px) if series else 1.0
        sell(remaining, lastr)

    fixed = legs*(PRIO_LAM+BASE_LAM)/LAM_SOL/SIZE
    net = sol_out - sol_in - fixed
    return {"net": net, "legs": legs, "units": units_bought,
            "cap_deployed": sol_in}   # SOL-in in nominal units (approx capital tied up)

# ---------- load + features ----------
rows = E.load_backtest(); FEATS = E.build_feats(rows)
for f in FEATS:
    e=f["entry"]; ser=f["path"]
    f["peak"] = (max([p[1] for p in ser], default=e))/e
FEATS.sort(key=lambda f: f["slot"])

def peakof(f): return f["peak"]

def run(feats, P, SIZE=0.5):
    return [simulate(f["entry"],f["entry_slot"],f["path"],P,SIZE) for f in feats]

def stats(res, feats=None):
    pnls=[r["net"] for r in res]
    n=len(pnls); srt=sorted(pnls)
    mean=sum(pnls)/n; tot=sum(pnls); win=sum(1 for p in pnls if p>0)/n
    med=st.median(pnls)
    sd=st.pstdev(pnls) if n>1 else 0.0
    # max drawdown of cumulative equity in trade order
    cum=0.0; peak=0.0; mdd=0.0
    for p in pnls:
        cum+=p; peak=max(peak,cum); mdd=min(mdd,cum-peak)
    mean_ex2 = (sum(sorted(pnls,reverse=True)[2:])/n) if n>2 else mean
    out={"n":n,"mean":mean,"median":med,"win":win,"sd":sd,"tot":tot,"mdd":mdd,
         "mean_ex_top2":mean_ex2,"sharpe":(mean/sd if sd else 0.0),
         "avg_legs":sum(r["legs"] for r in res)/n,
         "avg_cap":sum(r["cap_deployed"] for r in res)/n}
    if feats is not None:
        # runner capture: fraction of theoretical >=2x upside captured
        up=0.0; cap=0.0
        for r,f in zip(res,feats):
            if f["peak"]>=2.0:
                avail=f["peak"]-1.0           # gross upside over entry
                up+=avail
                cap+=max(0.0, r["net"])       # net we booked (floored at 0 for capture ratio)
        out["runner_capture"]=(cap/up if up else 0.0)
        # dump bleed: mean net on <1.1x duds
        duds=[r["net"] for r,f in zip(res,feats) if f["peak"]<1.1]
        out["dump_bleed"]=(sum(duds)/len(duds) if duds else 0.0)
    return out

def fnum(x): return f"{x:+.4f}"

if __name__=="__main__":
    # sanity vs fading NOFADE cut0.80 ride1.4 (current best)
    CUR=dict(s0=1.0,add_units=0.0,derisk_frac=0.0,ride_mult=1.40,trail_frac=0.92,
             cut_r=0.80,ladder_frac=0.25,cap_slots=40,fade=False)
    s=stats(run(FEATS,CUR,0.5),FEATS)
    print("CURRENT(no-fade cut0.80) full n=%d"%s["n"])
    print({k:(round(v,4) if isinstance(v,float) else v) for k,v in s.items()})

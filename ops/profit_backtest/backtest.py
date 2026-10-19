#!/usr/bin/env python3
"""Backtest: filter (src/snipe.rs) + same-slot entry + exit ladder (src/bin/snipe_engine.rs exit_ladder),
replayed over the unbiased create-slot-anchored price series. Train/val split, grid search, honest stats."""
import sys, os, json, statistics as st, itertools

CRE = json.load(open("/root/profit_backtest/creates.json"))
TRAJ = {t["mint"]: t for t in json.load(open("/root/profit_backtest/trajectories.json"))}
# join: keep creates that have a usable trajectory entry px
ROWS = []
for c in CRE:
    t = TRAJ.get(c["mint"])
    if not t or not t.get("entry_px"):
        continue
    ROWS.append({**c, "traj": t})
ROWS.sort(key=lambda r: r["create_slot"])

SLIP = float(os.environ.get("SLIP", "0.08"))     # flat per-leg price slippage
FEE_LEG = float(os.environ.get("FEE_LEG", "0.0008"))  # SOL per leg (priority+base), applied at SIZE
SIZE = float(os.environ.get("SIZE", "2.0"))      # SOL position size (for SOL figures; frac is size-indep)
ENTRY_MULT = float(os.environ.get("ENTRY_MULT", "1.0"))  # >1 = we fill ABOVE the create-slot floor (co-snipers)
STEP_SLOTS = 4

# ---------- exit ladder (faithful port of snipe_engine.rs exit_ladder) ----------
def simulate(entry_px, entry_slot, series, P):
    """Returns (net_return_fraction, gross_return_fraction, n_sell_legs). De-risk fires at entry."""
    amount = 1.0                      # work in token-fraction units; size cancels
    remaining = amount
    peak_r = 1.0; riding = False; first = True
    last_sell_slot = entry_slot
    sol_out = 0.0; legs = 0
    def do_sell(frac_of_amount, px):
        nonlocal sol_out
        # we paid entry_px*ENTRY_MULT per token; proceeds at curve px less slippage
        sol_out += frac_of_amount * (px/(entry_px*ENTRY_MULT)) * (1-SLIP)
    # Walk price polls. Prepend an entry-slot poll at r=1 so de-risk fires at the floor (live polls immediately).
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
    if remaining > amount*1e-6:   # ran out of polls: flush remainder at last seen px (or entry if none)
        lastpx = series[-1][1] if series else entry_px
        do_sell(remaining, lastpx); legs += 1
    gross = sol_out - 1.0                      # return as fraction of size (slippage only)
    fee_frac = (1 + legs) * FEE_LEG / SIZE     # buy leg + sell legs, as fraction of size
    net = gross - fee_frac
    return net, gross, legs

# ---------- filter (src/snipe.rs is_snipeable + --min-dev-buy, plus optional extras) ----------
def passes(c, f):
    if c["creator_fee_bps"] != 0:          # is_snipeable: skip only creator-fee launches
        return False
    dev = c["dev_buy"]                     # curve-delta truth (SOL into curve)
    if c.get("dev_buy_wire", 0) >= 1e17:   # u64::MAX sentinel -> unbounded dev buy passes any threshold
        dev = max(dev, f.get("dev_min", 0))
    if dev < f.get("dev_min", 0): return False
    if dev > f.get("dev_max", 1e9): return False
    if f.get("vanilla") and (c["mayhem"] or c["holder_reward"] or c["cashback"]): return False
    if f.get("max_cosnipers") is not None and c["traj"]["cosnipers"] > f["max_cosnipers"]: return False
    rep = f.get("rep")   # dict mint->creator freq; deny creators with >max_launches in window
    if rep is not None and f.get("max_creator_launches") is not None:
        if rep.get(c["creator"], 0) > f["max_creator_launches"]: return False
    return True

def run(rows, filt, exitp):
    pnls = []
    for c in rows:
        if not passes(c, filt): continue
        t = c["traj"]
        net, gross, legs = simulate(t["entry_px"], t["create_slot"], [(s, p) for s, p in t["series"]], exitp)
        pnls.append(net)
    return pnls

def stats(pnls):
    if not pnls: return None
    n = len(pnls); s = sorted(pnls)
    def q(x): return s[min(n-1, int(x*n))]
    mean = sum(pnls)/n
    wins = sum(1 for p in pnls if p > 0)/n
    tot = sum(pnls)
    top5 = sum(sorted(pnls, reverse=True)[:max(1, n//20)])
    sd = st.pstdev(pnls) if n > 1 else 0.0
    return {"n": n, "mean": mean, "median": st.median(pnls), "win": wins, "sd": sd,
            "p10": q(.10), "p25": q(.25), "p50": q(.50), "p75": q(.75), "p90": q(.90), "p99": q(.99),
            "tot": tot, "top5_share": (top5/tot if tot != 0 else float("nan")),
            "sharpe": mean/sd if sd > 0 else 0.0}

if __name__ == "__main__":
    print(f"rows with usable trajectory: {len(ROWS)}  (SLIP={SLIP} FEE_LEG={FEE_LEG} SIZE={SIZE})")
    base_exit = {"derisk_frac": 0.40, "ride_mult": 1.6, "trail_frac": 0.85, "cut_r": 0.85,
                 "ladder_frac": 0.30, "cap_slots": 20}   # 8s cap ~ 20 slots
    base_filt = {"dev_min": 0.3, "dev_max": 1e9, "vanilla": False}
    p = run(ROWS, base_filt, base_exit)
    S = stats(p)
    print("\n=== BASELINE (current config) over full unbiased sample ===")
    print(S)

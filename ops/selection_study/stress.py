#!/usr/bin/env python3
"""Realistic-fill stress of the winning slot-0 rules on the unbiased VAL split.
Recomputes net R per launch under degraded fills (slip, fee, entry above floor)."""
import os, sys, json, statistics as st
sys.path.insert(0, "/root/profit_backtest")
import backtest as B
rows = sorted(B.ROWS, key=lambda r: r["create_slot"])
cut = int(len(rows) * 0.70)
VA = rows[cut:]
EXIT = {"derisk_frac": 0.40, "ride_mult": 1.6, "trail_frac": 0.85, "cut_r": 0.85, "ladder_frac": 0.30, "cap_slots": 20}


def ub(c):
    return c.get("dev_buy_wire", 0) >= 1e17


def vanilla(c):
    return not (c["mayhem"] or c["holder_reward"] or c["cashback"])


RULES = [
    ("baseline (fee0 & dev>=0.3)", lambda c: c["creator_fee_bps"] == 0 and (max(c["dev_buy"], 0.3) if ub(c) else c["dev_buy"]) >= 0.3),
    ("sized dev>=2.0 (any flags)", lambda c: not ub(c) and c["dev_buy"] >= 2.0),
    ("cosnipers>=2", lambda c: c["traj"]["cosnipers"] >= 2),
    ("sized dev>=2 OR cosnipers>=2", lambda c: (not ub(c) and c["dev_buy"] >= 2.0) or c["traj"]["cosnipers"] >= 2),
]
# (slip, fee_leg, entry_mult)
FILLS = [("optimistic floor", 0.08, 0.0008, 1.00),
         ("moderate", 0.10, 0.003, 1.00),
         ("realistic same-slot", 0.12, 0.005, 1.05),
         ("harsh", 0.12, 0.008, 1.10)]


def simulate(entry_px, entry_slot, series, slip, fee_leg, emult, size=2.0):
    remaining = 1.0; peak_r = 1.0; riding = False; first = True
    last = entry_slot; sol_out = 0.0; legs = 0; P = EXIT

    def sell(frac, px):
        nonlocal sol_out
        sol_out += frac * (px / (entry_px * emult)) * (1 - slip)
    polls = [(entry_slot, entry_px)] + list(series)
    for (slot, px) in polls:
        if remaining <= 1e-6:
            break
        r = px / entry_px
        if r > peak_r:
            peak_r = r
        if not riding and r >= P["ride_mult"]:
            riding = True
        age = slot - entry_slot
        if first:
            qty = P["derisk_frac"]; final = False; first = False
        elif r <= P["cut_r"]:
            qty = remaining; final = True
        elif riding and r <= peak_r * P["trail_frac"]:
            qty = remaining; final = True
        elif age >= P["cap_slots"]:
            qty = remaining; final = True
        elif (not riding) and r < 1.0 and slot > last:
            qty = remaining; final = True
        elif (not riding) and 1.0 <= r < P["ride_mult"] and (slot - last) >= 4:
            qty = remaining * P["ladder_frac"]; final = False
        else:
            qty = 0.0; final = False
        qty = min(qty, remaining)
        if qty > 0:
            sell(qty, px); remaining -= qty; last = slot; legs += 1
            if final or remaining <= 1e-6:
                break
    if remaining > 1e-6:
        sell(remaining, series[-1][1] if series else entry_px); legs += 1
    net = (sol_out - 1.0) - (1 + legs) * fee_leg / size
    return net


print("Realistic-fill stress on unbiased VAL (n_total=%d). win%% / meanR / medR per rule x fill:" % len(VA))
for rname, rfn in RULES:
    sub = [c for c in VA if rfn(c)]
    print("\n## %s  (n=%d, %.0f%% of VAL)" % (rname, len(sub), len(sub) / len(VA) * 100))
    for fname, slip, fee, em in FILLS:
        nets = [simulate(c["traj"]["entry_px"], c["traj"]["create_slot"],
                         [(s, p) for s, p in c["traj"]["series"]], slip, fee, em) for c in sub]
        if not nets:
            continue
        w = sum(1 for x in nets if x > 0) / len(nets) * 100
        print("   %-22s win=%5.1f%%  meanR=%+.4f  medR=%+.4f  SOL@2=%+.4f" % (
            fname, w, sum(nets) / len(nets), st.median(nets), sum(nets) / len(nets) * 2))

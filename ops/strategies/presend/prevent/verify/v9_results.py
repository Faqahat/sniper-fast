#!/usr/bin/env python3
"""VERIFY step 9: RESULTS.txt / RESULTS.json (verdicts + the tables of steps 3, 4, 7, 8)."""
import json, subprocess
OUT = "/home/it/sniper-data/prevent/verify"
L = json.load(open(f"{OUT}/locks.json")); S = json.load(open(f"{OUT}/score.json"))
V = {
 "1_regime_lock": dict(verdict="CONFIRMED (scaled = INFERRED)", agent=dict(pick_cost_065=-6.36, trips=["F27", "F28", "A24", "A26"]),
   verifier=dict(pick_cost_065_regime_formula=-6.357, pick_cost_065_correct_fixed=-6.785, trips=["F27 03:32 -2.81", "F28 18:01 -0.98", "A24 22:34 -3.11", "A26 14:00 +0.11"],
                 g08_trips=["F28 -0.98", "A26 -0.00", "A28 -0.52 (extra run)"], g10_trips=[], g15_trips=[], real_size_065_trips=["A26 cost 0.00", "A38 (live)"],
                 max_scaled_drawdown=0.876, worst_trade_scaled=-0.484, scaling_bug="REGIME FIX 2.0 mSOL omits the 1.514 mSOL ATA rent inside realized pnl on ATA runs -> scaled P&L too low by 1.5 mSOL x (k-1) per trade; conclusion unchanged",
                 after_drop_04=dict(events=8, next60_mean=0.579, next60_n=4, next60_pos=4, base_hour_mean=0.307, base_hour_pos="54/69"),
                 cooldown_spotcheck={"C1 big->15m": [-9.06, "agent -8.52"], "C4 4 losses->15m": [-3.40, "agent -3.18"], "C5 15m<-0.25->15m": [-1.59, "agent -1.17"]})),
 "2_state_nbuyers50": dict(verdict="CONFIRMED (small)", feature_reproduces="skip counts identical in all 26 runs; tape for 10-29+ from a different decode than STATE's",
   verifier=dict(raw26_scaled=S["S1 nbuyers50<=1, all live T2 windows as they ran, 26 runs (scaled 0.696)"], raw26_real=S["S1r same, REAL SOL (no scaling)"],
                 current_like=S["S1d closest to current config: QUIET-on runs (A28 A31-A36) + r37/r38, age >= 2"]),
   bias="STATE window values omit the ATA rent refund (1.509 mSOL/fill) and scale fixed costs -> savings inflated by ~1.5-4 mSOL per skipped fill (~0.1 SOL on PICK)"),
 "3_guards_ctx085": dict(verdict="PLAUSIBLE (LEAD) - direct reproduces, refills not re-modelled; replay with refills fails CI",
   verifier=dict(direct20=S["G1 direct, 20 runs, scaled (fills only; failed-try fees unchanged)"], direct20_real=S["G1r direct, 20 runs, REAL SOL"], d18=S["G2 direct, 18% variant (20 runs)"]),
   note="effect is the holder condition: depth 12-15% with other 6% holder n 303 sum -3.11; without +6.92; a plain 0.85 limit loses (-3.13 PICK, -1.20 r37)"),
 "4_who_gcr": dict(verdict="PLAUSIBLE (post-hoc, PICK <= 0) - log only / forward test",
   verifier=dict(m2S005=S["W1 G-cr m2 S0.05, 20 runs, T2 + re-arm windows"], m2S02=S["W1 G-cr m2 S0.2, 20 runs, T2 + re-arm windows"]),
   note="2 creators (dtrzJPj7 +0.53, 9wRuFPJZ +0.31) carry it; PICK -0.12 (w/o1 -0.21); CI lower ~0.00"),
}
json.dump(V, open(f"{OUT}/RESULTS.json", "w"), indent=1, default=str)
txt = ["VERIFY results (prevent program verifier, 10-30 PKT). Code /home/it/sniper/ops/strategies/presend/prevent/verify (v1..v9). Own extraction + own tape.",
       "Verdicts: 1 REGIME lock CONFIRMED (scaled, INFERRED) | 2 STATE nbuyers50 CONFIRMED (small) | 3 GUARDS ctx 0.85 PLAUSIBLE/LEAD | 4 WHO G-cr PLAUSIBLE (post-hoc)", ""]
for f in ("locks.txt", "score.txt", "combined.txt"):
    txt.append(f"######## {f}"); txt.append(open(f"{OUT}/{f}").read())
open(f"{OUT}/RESULTS.txt", "w").write("\n".join(txt))
print("written", f"{OUT}/RESULTS.txt", f"{OUT}/RESULTS.json")

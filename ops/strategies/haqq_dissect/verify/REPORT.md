# Verifier V: adversarial check of the re-arm rule and the wave exit (10-28 ~05:55 PKT)
Saved by the main session from the agent's reply. Code: this folder:
- v1_rsim_fwd.py: G2's frozen rule through rsim on the fresh tape;
- v2b_reimpl.py: independent re-implementation;
- v4_wave_live.py: wave exit on live fills;
- v5_validate.py; v6b_blocks.py;
- v9_final.sh re-runs all forward tests in ~25 s.

Data: /home/moiz/sniper-data/haqq_dissect/verify/ (final_*.txt, insample_*.txt, tab/ = fresh tape, live/dip_r27.jsonl).

**Fresh data:** 10-28 01:10–05:45 PKT, 4.51 usable hours (one night).

## 1. Code audit (rsim, r4_days, r3/r3b/r8)
- **No lookahead.** Arm and holder check use the tape through dump+2; stops are causal.
- **Fill pricing reproduces live:**
  - 740/740 live fills and ~73k 6042 failures (dv8 tape);
  - 114/114 fills and ~18k tries (fresh tape).
- Costs, knock-on, rate caps and the same-draw baseline are all correct.
- **The only bug:** r8 used draw 0 only; the 3-draw mean is +14.09 vs +14.43 (−0.34 over 6 days).
- Mayhem and non-SOL exclusions are clean. Leaving our own rows in the tape adds no optimistic bias.

## 2. Independent re-implementation, in-sample D2–D5

| Model | SOL |
|---|---|
| G2 | +10.80 |
| Mine, AMS-mix landing | +9.55 [+7.45, +11.78] |
| Mine, FRA k8 landing | +7.76 |

Positive every day. Calibrated: +8.42 / +7.51 / +6.03. **REPRODUCES.**

## 3. Forward test of the re-arm on fresh hours

| Replay | Total (4.5 h) | Rate | Note |
|---|---|---|---|
| G2's rsim, frozen rule, 5 draws | **+0.368** (cal +0.272; draws +0.05..+0.65) | +1.45/day calibrated, ≈ 65% of the claim | the 48th percentile of in-sample 4.5 h blocks (ordinary) |
| Mine, 10 seeds | **−0.01 [−0.58, +0.57]** (FRA landing −0.20) | ≈ 0 | the 0–1.3th percentile of its in-sample blocks |

- **Per re-arm fill:** +4.5 mSOL fresh vs +10.4 in-sample.
- **Fewer followers:** 10% fewer → G2 +0.07 cal / mine −0.19..−0.34; 20% fewer → negative in both.
- The holder gate still beats no gate (−0.39).
- **Why the two replays diverge:** crowded next-whale dumps that only rsim fills (14 windows, +0.20). Example 526mBQ: fast buyers land 10 / 12 / 18 ms after the dump and our first try 21 ms after it, 0.8% above the limit.
- **Live ground truth for the fresh hours (FRA r26 + r27):**
  - live net +0.846 (114 fills) vs G2's base replay +1.585 (189 fills), ratio 0.53;
  - FRA first try after a crossing drop: 95 ms (vs 56 ms in the dv8 period), fills 37%;
  - fill by trades ahead 0 / 1 / 2–3 / 4–7 / 8+ = 100 / 43 / 10 / 5 / 0%.

**VERDICT Claim 1: WEAKENED** (−35% to −100% forward). The +2.25/day is not supported forward; the range is 0..+1.5/day. Next: dry shadow, then a capped A/B on AMS; pass = live P&L > 0 plus a measured live fill rate on next-whale dumps.

## 4. Forward test of the wave exit on fresh LIVE fills (fills MEASURED, counterfactual INFERRED)

| Fills | n | Actual | Wave − actual [90%] | mSOL/fill |
|---|---|---|---|---|
| r26 pre-send | 43 | +0.797 | −0.094 | −2.2 |
| r27 pre-send | 84 | +0.891 | +0.611 [+0.21, +1.15] | +7.3 |
| **Pre-send after 01:10 (fresh)** | 114 | +1.353 | **+0.587 [+0.16, +1.16]** | **+5.2** |
| Regular r26 | 11 | −0.357 | +0.158 | +14.3 |

- **A plain 200 ms timer:** +0.632 [+0.21, +1.21], as good as or better than the wave rule; 300 ms: +0.469. **The gain is from selling earlier;** tracking outside buys adds nothing measurable.
- **Concentrated:** without the best 1 / 3 fills, +0.31 / +0.19 (≈ +1.0 SOL/day). The largest is G3badS9g: actual −288, wave −11 mSOL.
- The wave exit was better on 16% of fills and worse on 9%.

**VERDICT Claim 2: CONFIRMED** in direction and at least the claimed size (≈ +1.0 to +3 SOL/day at ~600 fills/day). **Build the simpler "sell ~200 ms after the fill" timer.**

## Refresh (main session, 10-28 ~08:20 PKT): v9_final.sh on 6.9 fresh hours (01:10 → 08:00); first run kept in data/run1_0555/
- **Claim 1 (re-arm):**
  - G2's rsim ADDED +0.453 model / +0.333 cal (+1.57 / +1.15 per day); with 10% fewer followers +0.011; with 20% fewer −0.291;
  - V's independent replay −0.02 (AMS-mix) / −0.03 (FRA);
  - no-holder variant −0.405 (−1.40/day).

  **Still WEAKENED: 0..+1.2/day.**
- **Claim 2 (exit), 148 fresh live pre-send fills:**

  | Exit | Gain vs actual [90%] | Per fill |
  |---|---|---|
  | Fixed 200 ms | **+0.758 [+0.292, +1.333]** | +5.1 mSOL |
  | Wave 150 / 1 s | +0.713 [+0.272, +1.292] | +4.8 mSOL |
  | Wave without its top 3 fills | +0.313 | |

  **CONFIRMED again; build the 200 ms timer (engine dip22).**
- **Live landing (fresh):** first try after a crossing drop, median 94 ms. Fill by trades ahead 0 / 1 / 2–3 / 4–7 / 8+ = 100 / 49 / 10 / 5 / 0%.

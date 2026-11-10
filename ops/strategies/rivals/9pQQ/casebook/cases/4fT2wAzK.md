# Case 04 — 4fT2wAzK (run 10-30, launch 10-30 ~20:25 PKT, "PumpPerps", X + web) — stratum B multi-loss, era V2 (300 s cap)
14 trips 20:43–22:20, −0.14 SOL. A quiet token (836 trades over 2 h); first entry at age 220.

## What happened
- **Buys on a quiet token are pure momentum**: 13/14 behind an outside BUY; ch10 +5.9 % (skipped 0), nf10 +1.69 SOL (skipped 0),
  **no outside sells in the 10-slot window** (ns10 q75 = 0), and at the 450-slot high (dd450 +0.2 vs −6.9 %). Opposite of the dip
  entries on the busy tokens 1–3. → the buy rule is relative to the token's regime, or there are two buy sub-strategies.
- Biggest skipped: 2–3 SOL buys that came after a long pause (ch10 = 0, gap large) – it took 0.3–1 SOL buys in a small ramp instead.
- **Exits (V2): 7/14 capped at 300 s; the 7 signal exits are all on an outside SELL (0/7 buys) after a long buying pause**:
  since_ob at sell 59–337 slots (median 237) vs 23 for non-sell moments. Return at sell ≈ −0.5 %.
  Teacher-forced "first outside sell after ≥ 60 slots without an outside buy": exact 2/7, early 3, never 1 on this token;
  on the cap trips the same rule would have fired during the hold → not the rule as stated.
- Quit when the token went quiet (18 trades after its last exit).

## Hypotheses
| id | cat | hypothesis | here |
|---|---|---|---|
| HB20 | buy | On quiet tokens: momentum entry = small ramp of outside buys with no sells in the last 10 slots, at the local high. | support |
| HS13 | sell | (V2) signal exit = an outside SELL after a long buying pause (since_ob ≥ ~60 slots). | partial (2/7 exact) |
| HB17 | buy | below recent high | contradict |
| HB19 | buy | volatility (|ch10| ≥ 5) | support (+5.9) |

# Case 02 — HntohC4m (run 10-30, launch 10-31 15:04 PKT, "股票", has X + website) — stratum A multi-win, era V3 (300 s cap)
16 trips in 18 min, +1.30 SOL, 13 wins. 2,389 trades; 9pQQ stopped at +4994 while the token kept pumping to MC 411 (13 outside buys ≥0.5 after).

## What happened
- First entry at age 17 in a launch pump (ch10 +86 %, nf10 +12.6 SOL), right after a 5.9 SOL sniper dump and haqq/2VggY buys. Sold 35 slots later +9.9 %.
- **Exits look like two modes (V3):**
  - **burst exit**: sells into a wave of outside BUYS that just spiked the price: T1 (2.78+1.33+1.30 SOL buys, ch3 +29.6 %), T4 (41Pr4 buy wave,
    ch3 +43.7 %, dd 0), T8 (DFFXH 2.96), T12 (two 1.95 SOL FLASH buys, dd 0), T13 (ET5Vq 3.91, dd 0). Exit at the in-hold peak.
  - **stale exit**: sells on a small trade after outside buying paused: T2 (since_ob 27), T3 (30), T10 (46), T6 (18).
  - rest ambiguous (since_ob 0–14, small trades).
- Sold-on vs not (hold moments): ret 9.9 vs 4.3 %, dd from peak −2.4 vs −5.3, since_ob 8 vs 2, trigger size 0.46 vs 0.13. In V3 the exit is not
  return-blind on this token: it sells high.
- Buys: mixed: dips (T2, T5, T7, T10, T12, T14, T15: ch10 −4..−11 %) and breakouts (T1, T4, T8, T9, T11, T13: ch10 +3..+86 %). Taken triggers are
  bigger (0.42 vs 0.12 SOL), sit in busy slots (gap 0 vs 1), at lower MC than skipped (128 vs 247; dd450 −13 vs −9).
- Skipped: the largest flat triggers (15.6 SOL buy at MC 411, 5.9–6.9 SOL buys/sells at MC 250–280) — again no chasing at highs, and it quit
  the token while it was still pumping (age +5149, MC 411). It does not follow the token into higher MC (all buys MC 70–273).
- 41Pr4 wave present in T4/T8 windows (enrichment visible). Failed txs: 0 signal.

## Hypotheses
| id | cat | hypothesis | here |
|---|---|---|---|
| HS10 | sell | (V3) burst exit: sells into outside buy burst (buy SOL in last 1–3 slots ≥ ~2 SOL / ch3 ≥ +9 %) while in profit, at the in-hold peak | support (5/16) |
| HS11 | sell | (V3) stale exit: sells on the next trade once outside buying paused ≥ ~10 slots | support (4/16) |
| HB18 | buy | Two buy modes: DIP-bounce and BREAKOUT (ch10 ≥ +3 % with ≥1 SOL of buys in the window) | support (7 dip / 6 breakout) |
| HK03 | skip | Stops trading a token above some MC (~250–300 SOL MC here) even while it is still active | support |
| HB14 | buy | dip+bounce | partial (7/16) |
| HB17 | buy | below recent high | support |
| HS09 | sell | V3 exits near peak | support |

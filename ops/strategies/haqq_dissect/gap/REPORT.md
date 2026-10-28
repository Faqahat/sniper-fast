# Analyst E (gap ledger): where his ~31 SOL/day gap comes from (10-28 ~02:50 PKT)
Saved by the main session from the agent's reply. Code: this folder (g0–g8). Tables: /home/moiz/sniper-data/haqq_dissect/gap/ (g3_haqq, g4_ours, g4_waterfall, g5_evening, g6_capture, g6b_bucket_means, g7_guard, g8_summary, g9_compact, g0_runs .txt; rows g3_rows.pkl).

## How it was built (MEASURED)
- Every haqq lot on the tape (36,778 lots, 10-22 → 10-28), each in exactly one bucket.
- Each lot's P&L goes to its buy day. 10-27 reproduces haqq_strat: +28.16 vs +28.07.
- Our side: all 142,172 wallet txs, matching the daily totals (+0.554 / −0.173 / +1.283 / +3.178).
- No engine ran on 10-22 or 10-23.

## Waterfall: his net to our wallet (SOL/day, mean of 10-24..10-27; residual 0.0000 on every day)

| Step | SOL/day |
|---|---|
| haqq net | **+32.38** (+48.87 / +21.54 / +30.94 / +28.16) |
| Run gaps | −4.79 |
| NOCOV (unusable tape hours) | −0.57 |
| ADD lots (a type we never trade) | **−7.56** |
| DIP_LATE / DEAD / other types | −4.25 |
| Gate refused (M2/IMIT1) | **−10.03** |
| Far leader | −0.66 |
| One-position / QUIET | +0.06 |
| Thresholds / old / cooldown / fee budget / other | −2.52 |
| Guard failures (his P&L) | −2.59 |
| Shared trades: size | +0.24 |
| Shared trades: return per SOL | **+2.29 in OUR favour every day** |
| Shared trades: tx costs | −0.21 |
| Our fills he skipped | −0.38 |
| Our failed-fire and try costs | −0.28 |
| Other txs | +0.08 |
| **= our wallet** | **+1.21** |

**Groups:**
- refusals 13.2;
- types we don't trade 11.8 (ADD 7.6);
- run gaps + NOCOV 5.4;
- guard failures 2.6;
- shared trades −2.3 (we already beat him there).

## KEY: our style on HIS events (INFERRED, validated DV8 replay)

| Case | SOL/day |
|---|---|
| His result on his 2,952 dump events per day | +24.6 |
| Our style, ideal landing | +82.7 |
| Our style, our landing, uncalibrated | +15.5 |
| Same, calibrated, current costs | **−1.2** |
| Same, calibrated, cheap tx recipe | +4.7..+5.9 |

So even knowing all his picks, our style makes ~0..+6/day. **About 19–26 SOL/day of the gap is HOW he trades each event** (adds, holds, exits, limits, size), not which events.

## 10-27 evening, 18:00–22:00 PKT
- **Totals:** haqq +6.88 SOL (1,211 lots). Our wallet +0.34 (only AMS r28 ran, 18:20–22:03). We were not losing.
- **Where his profit came from:**
  - M2-refused dev/bundler dumps +2.84;
  - before r28 started +1.15;
  - types we don't trade +1.31.
- **Dumpers pre-send can't arm on:**
  - creation-slot buyers +2.98;
  - ≥6% holders never seen as a trigger +2.56.
- **By number of buys:** tokens bought 2+ times +7.60; tokens bought once −0.72. The same holds every day, but it is not causal.

## Ranked recoverable (INFERRED)

| # | Bucket | First estimate for us |
|---|---|---|
| 1 | His trade style on his events | ceiling ~19–26, depends on the pos/exit work |
| 2 | ADD / repeat dumps | +0.7 now, +1.9 cheap |
| 3 | Gate refusals | 0..+0.5 |
| 4 | Run gaps | +0.1..+0.5 |
| 5 | Costs | +0.3..+0.4 with his tx recipe (owner OK) |
| 6–8 | Late / launch / far / guard / DEAD | ≤ 0.3 each or negative |

**Realistic with our current style:** +2..+4 SOL/day on top of today. The rest needs his trade style proven causally.

## Follow-up (10-28 ~03:05 PKT): wave exit and pre-send entry on his events (code g10*, g11*; tables g10a, g10_tables, g10_tables_nohaqq, g11_tables)
- **Regular landing** (rank model, calibrated NOW, mean SOL/day 10-24..27): the wave exit doesn't rescue his events and is WORSE than T5 on them.

  | Events | T5 | WAVE_REG | WAVE_REG, cheap tx |
  |---|---|---|---|
  | All his events | −4.9 | −6.1 | −0.1 |
  | Gate-refused | −0.65 | −1.9 | +0.4 |
  | Gate-refused, walk-forward | | | +3.07 / +2.01 / +1.79 / −0.48 |
  | ADD dumps, walk-forward | | | +0.66/day |

  The ADD walk-forward goes negative with 10% fewer followers. The guard-fail bucket is not real: we fired and failed there.
- **Pre-send-style entry (dump's own slot, MEASURED landing: 70% with no trade between, 28 ms) on his large-holder dumps:**

  | Set | SOL/day |
  |---|---|
  | Creation-slot buyers | +10.8 (6/6 days positive) |
  | Same, his own trades removed | +6.6 |
  | Of which gate-refused | +3.9 |
  | Other ≥ 6% holders | +3.75 |

- **Without his selection:** all ≥ 6%-holder creation-slot dumps lose −3.6 mSOL/event (−17..−72/day, negative 6/6 days).

  | Subset | Per event |
  |---|---|
  | haqq bought | +9.3 mSOL |
  | haqq did not buy | −6.1 mSOL |

  No exit rescues the full set. Only dumps within 10 slots of the whale's first buy (today's design) are positive: +0.28/day.
- **Conclusion:** the money is in WHICH large-holder dumps get followed (16% base rate; ~40% precision needed to break even). Next: a causal "will-be-followed" selector. The re-arm rule (pos §5) is one candidate.

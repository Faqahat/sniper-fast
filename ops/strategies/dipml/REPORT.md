# DIPML — dip-buy model (reactive + pre-send), target 40 SOL/day ($4k)

Split by time: TRAIN 85.9 h (10-21..10-24) · VAL 23.9 h (10-25) · TEST 29.4 h (10-26 19:40 → 10-28 01:10 PKT), holes excluded.
626k dumps; GBDT, 28 features at/before the dump; cut+size frozen on VAL; TEST scored once. Data: sniper-data/dipml (results.json, calib.json, frozen_L*.json).

## Replay vs live (1,422 real reactive fires, MEASURED)
Replay − live per attempt: TRAIN +9.0, VAL +4.6, frozen penalty +6.9 mSOL; TEST −0.9 (gap unstable → truth between raw and penalised).
Live landing median 56 ms (TEST 55; p25 35, p75 95).

## Combined on TEST, SOL/day (reactive 0.5 SOL + pre-send live +4.0)
| Latency | Penalised | Raw | −20% followers |
|---|---|---|---|
| 35 ms | +2.3 | +36.8 | ≈ −35 |
| 50 ms | +1.9 | +23.2 | ≈ −20 |
| **58 ms (ours)** | **+6.5** | **+10.4** | ≈ −0.6 |
| 75 ms | +4.3 | +8.1 | ≈ −2 |

- Reactive 58 ms/0.5 SOL: 462 attempts, 210 fills/day, 50% win, +2.5 pen / +6.4 raw. Selection real: random picks lose −23..−238/day.
- 1.0 SOL rows look better only because the replay keeps followers our big buy prices out; all lose with −20% followers. Honest size 0.35–0.5.
- Pre-send TEST (live, MEASURED): +4.04/day (night +7.4, day +0.85); with QUIET replayed +4.9 (INFERRED).

## Verdict
At our speed ≈ +6.5..+10 SOL/day ($650–1,000). 40 SOL/day appears only in the uncalibrated 35 ms 0.75–1.0 SOL replay. No calibrated row reaches it.

## Levers
1. Real ~35 ms landing: +0..+60/day (INFERRED; only lever that can reach 40; needs a live probe).
2. Cheaper trips 4.6 → 1.7 mSOL: +0.6/day now, +4..8 at fast-row volume.
3. Pre-send 0.5 SOL + QUIET: +1..+3/day, fragile to followers.

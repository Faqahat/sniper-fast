# FLATPERFECT (11-04 PKT): a filter that skips our flat pre-send trades
Code: this folder | data: /home/it/sniper-data/flatperfect/ | local, read-only. MEASURED unless marked EST/PAPER.
Flat = −0.025..0, small = 0..+0.025, win ≥ +0.025, big loss < −0.025 SOL.

## Short answer
- No perfect flat filter is possible with what we know before our buy lands. The owner's idea holds: on flats, follower bots stay away.
- FP-NOBOT was frozen before r55 was opened (FROZEN_FLAT.json, 11-04 23:58:44 PKT, sha 285acb7f…). It **PASSES** on r55:
  - saved +1.25 SOL (+1.77/day)
  - +0.70 without the top 5
- It blocks 73 of 195 flats (37%), but it also blocks 9 winners (+0.70) and 12 smalls (+0.14).
- T2 passes alone. The re-arm part fails alone without the top 5 (−0.11).

## Mechanism (dev, after the fact)
No cohort or named bot buying within 2 slots after our fill:
- T2 without a bot: 233 positions, 137 flats, 13 wins, −5.2 SOL.
- T2 with a bot: 810 positions, 155 flats, 362 wins.

## Frozen rule FP-NOBOT
- **Score:** P(no follower bot ≤2 slots after our fill), the mean of 3 LightGBM models per kind (4 leaves, 200 trees).
- **Inputs:** 153 causal inputs.
- **Thresholds:** block T2 at ≥0.388, re-arm at ≥0.5005 (85th / 80th percentile of dev out-of-fold scores).
- **No-data rule:** a position with no chain data is never blocked.
- **Strongest inputs:** activity from the trigger to fill slot − 2: trades/buyers, bot failed buys, bot buys, max price. Then the whale's hold clock, bot holdings, top holder %, and our last results.
- **Gate type:** a per-send gate (data up to the send slot − 1), not only an arm-time skip.

## Dev (4 time blocks, each scored by a model trained on the other 3)

| kind | blocked | flats | wins lost | saved | w/o top 5 | blocks saved > 0 | blocks w/o 5 ≥ 0 |
|---|---|---|---|---|---|---|---|
| T2 | 247 | 132 | 30 (+2.09) | +3.06 | +0.99 | 4/4 | 4/4 |
| re-arm | 174 | 101 | 13 (+0.81) | +2.33 | +0.88 | 4/4 | 3/4 |

- r42: T2 +0.93 (w/o 5 +0.38); re-arm +0.14 (w/o 5 −0.03).
- All dev: +5.39 saved, 43 wins lost (+2.91).

## r55 proof (copy 07:00→23:58 PKT, 17 h, 487 positions)

| | blocked | flats (SOL) | smalls lost | wins lost | big losses blocked | saved | per day | w/o top 5 | f20 EST |
|---|---|---|---|---|---|---|---|---|---|
| all | 106 | 73 (−1.19) | 12 (+0.14) | 9 (+0.70) | 12 (−0.91) | **+1.25** | +1.77 | **+0.70** | +1.53 |
| T2 | 57 | 43 (−0.77) | 5 (+0.07) | 3 (+0.22) | 6 (−0.43) | +0.91 | +1.28 | +0.53 | +1.01 |
| re-arm | 49 | 30 (−0.42) | 7 (+0.07) | 6 (+0.48) | 6 (−0.48) | +0.35 | +0.49 | −0.11 | +0.52 |

- Both halves of the run are positive.
- Blocked trades average −11.8 mSOL; kept trades average +4.6 mSOL.

## Caveats
- r55 is partial. Re-score the final copy with fp4_chain_extend.py, then `fp6_score.py <final> final`.
- 15 positions had no chain data and were passed.
- A withheld send could still fill on a later dip; the replay counts it as no trade.

## Engine (log-only) needs
Log on every pre-send try:
- **At arm:** token flow over 20/100/500 slots; holder structure; cohort holdings, trades and failed buys; the whale's hold clock; market cohort activity over 1/5/30 min; our recent results.
- **At each send (data up to slot − 1):** since the trigger, trades, buyers, cohort buys/failed buys, whale sells, price max/min/last.

The frozen models are small enough to evaluate in Rust; otherwise log the inputs and score offline.

(Report text written by the study agent; the harness blocked the agent from writing it, so it was saved by the main session.)

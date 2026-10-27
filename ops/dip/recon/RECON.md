# Paper vs live: trade-by-trade reconciliation

Dip bot, Frankfurt runs 10–15 and Amsterdam runs 9–14.
Window: 10-24 16:59 → 10-25 07:50 PKT. That is 309 buys over 27.6 server-hours (13.8 h of both servers).
FRA 15 and AMS 14 were still running; their records were copied ~07:50.
Labels: **MEASURED** = chain or recording data. **Replayed** = replay output on the recorded tape. **INFERRED** = reading.

## Verdict

- **Speed is the main cost.** The replay's mechanics are right; it was fed the wrong landing time.
- The rows that looked good assumed our buy lands **35 ms** after the dump (on the replay's block-position clock).
- MEASURED on chain, our buys land at a **median of 58 ms**. The middle half falls between 33 and 101 ms, and 22% land in a later block. Only 29% land within 35 ms. The nonce runs are no faster (median 61).
- Put our **real landing** into the replay and it reproduces live. Corrected replay **−0.44 SOL**, live **−0.37 SOL**, on the same 309 buys. The difference is +0.07 (90% CI −0.24 to +0.37).
- **We are late exactly where the money is.** On dumps that bounce, rivals land ahead of us, the price passes our +5% limit, and our buy fails.
  - Live fill rate: 29% on the best third of dumps, 65% on the worst third.
  - The 35-ms paper profit comes from dumps where our buy failed live (+2.0 SOL).
  - Our 129 fills are about break-even even at 35 ms (+0.01).
- **Second cost: the 4-second hold** on Frankfurt runs 10–11. MEASURED on the real tape, the same 31 fills sold at slot +5 (~1 s) would have brought back **+0.98 SOL more**.
- **Structural cost: pump fees.** They took 1.41 SOL, which is 85% of the fills' gross bounce (+1.66).

## The numbers (SOL, these runs)

| Row | 35 ms | 50 ms | 75 ms | At our real landing |
|---|---|---|---|---|
| Paper as it was made (both servers all hours, 0.55 SOL, 1.3 s exit) | +2.74 | +0.89 | +0.42 | – |
| Paper for exactly what ran live | +1.84 | +0.54 | −0.19 | **−0.72** |
| Corrected replay | +1.98 | +0.85 | +0.27 | **−0.47** (−0.44 on the 309 real buys) |
| **Live (chain)** | | | | **−0.37** |

- Live split: 129 fills −0.260, 180 failed buys −0.111.
- 178 of the 180 failed buys hit the +5% guard (pump error 6042). One was 6001, one ran out of compute.

## Where "10 SOL in 30 h" went (these 15 h)

The owner's rate pro-rated to these 15 h is about +5 SOL.
Its source is INFERRED: "8–12 SOL/day at a real 35 ms" (10-23 study) or the 24 h replay at 35 ms (+10.8/day).

| Step | SOL | Change |
|---|---|---|
| Owner's expectation pro-rated (INFERRED) | ~+5 | – |
| Paper as it was made, these hours, at 35 ms | +2.74 | ~−2.2 (other days, older study) |
| Only the hours each server ran | +2.85 | +0.11 |
| The engine's own picks | +2.46 | −0.39 |
| The runs' real sizes (0.35; FRA 10–11 0.55/0.75) | +2.33 | −0.13 |
| The runs' exits (FRA 4 s hold) | +1.52 | −0.81 |
| Our own trades removed from the tape | +1.84 | +0.32 |
| **35 ms → our measured landing** | **−0.72** | **−2.56** |
| Model fixes (real exit timing, real costs) | −0.47 | +0.25 |
| Only the dumps live really fired on | −0.44 | +0.03 |
| Live | −0.37 | +0.07 (noise) |

- Biggest step: **landing time, −2.56 SOL**.
- Next: the FRA 4 s exit (−0.81 at 35 ms; −0.98 MEASURED on the real tape).
- For these hours, the old paper method itself said only ~4.4 SOL/day at 35 ms. About half the remembered rate came from other days and from the older study's assumptions: 0.5 SOL, all leaders, no one-position limit (INFERRED).
- Leaving our own trades in the tape did not inflate the paper. It deflated it slightly (−0.32 at 35 ms).

The M2 shadow grading the owner saw covered 01:42–05:40 (FRA r14 + AMS r13). Here are the same two runs (01:42–06:08):

| Row (FRA r14 + AMS r13) | 35 ms | 50 ms | 75 ms | At our landing |
|---|---|---|---|---|
| Grading as reported (IMIT1, 1.3 s, 0.55 SOL) | +1.34 | +0.54 | +0.26 | – |
| Paper for what ran (0.35 SOL) | +0.87 | +0.44 | +0.24 | −0.10 |
| Corrected replay | +1.03 | +0.66 | +0.43 | −0.01 |
| **Live** | | | | **+0.03** |

## Price of speed (corrected replay, same 309 dumps, SOL per day for both servers)

| Landing | As the runs were set | Today's exit (sell at slot +4, no SL, 0.35 SOL) |
|---|---|---|
| **Our real landing (measured)** | **−0.77** | **+1.06** |
| 5 ms faster (real time, our feed clock) | +4.1 | +4.9 |
| 10 ms faster | +5.6 | +6.4 |
| 20 ms faster | +7.2 | +8.7 |
| 30 ms faster | +7.5 | +9.3 |
| 50 ms faster | +10.6 | +10.7 |
| First in line after every dump | +13.0 | +13.2 |
| Block clock, fixed 0 / 10 / 20 ms | +13.2 / +12.3 / +9.7 | +13.4 / +12.2 / +9.9 |
| Block clock, fixed 35 / 50 / 75 ms | +3.5 / +1.5 / +0.4 | +5.2 / +3.3 / +2.0 |
| Live (as run) | −0.65 | – |

How to read the "faster" rows:
- "X ms faster" means our buy lands ahead of every trade on that token that our own feed showed in the last X ms before our buy. The order is MEASURED; the outcome is replayed.
- These rows keep the same picks and assume rivals behave the same (INFERRED).
- Below ~5 ms the result is about ordering inside one feed batch, not speed. Half our fills had a rival ≤1 ms ahead of us on the feed.
- This covers one night and morning (13.8 h). Use it to rank options, not as a forecast.

## What else costs, and what does not

| Item | SOL | Note |
|---|---|---|
| Landing later than 35 ms | −2.56 | landing MEASURED, outcome replayed |
| FRA runs 10–11, 4 s hold | −0.98 | real tape, same 31 fills: 19.65 vs 18.67 SOL back |
| Pump fees (~1.25% each way) | −1.41 | 85% of the fills' gross bounce (+1.66) |
| Tips | −0.35 | before nonce, 2–3 tips per buy: buy cost 0.0030 vs 0.0015 with nonce |
| Hold 6 instead of hold 5 (runs with hold 6) | −0.29 | replayed at our landing; today's runs use hold 5 |
| Failed-buy fees | −0.11 | 15M priority on AMS 12–13 made each one cost 3x (0.0015) |

NOT the cause (all MEASURED):
- **Entry math.** Replay tokens equal live tokens on all 128 fills (ratio 1.000000).
- **Guard.** The replay matches live on 308 of 309 buys. The miss was a borderline price ratio of 1.0501.
- **Followers.** At our real landing, the slack model drops 111 real followers across 80 fills, worth +0.04 SOL. Real followers did come.
- **Recording.** All 309 buys were found in it. 4,442 of 4,444 trades the engine logged around our buys are in it. There is no 16:30–19:25 gap.
- **Picks / engine.** The replay takes every live buy, plus 15 dumps live skipped (13 spacing, 2 other), worth −0.09.
- **Feed gaps.** The engine saw every one of the 334 offline picks on near leaders while it ran. It skipped 19 of them on purpose: 15 sat just outside its own envelope (logged as M2-extra), and 4 were rejected by the M2 gate on FRA 15.
- **Near-leader filter.** The epoch schedules plus each server's list reproduce every far-leader skip and every fire.
- **Costs.** The paper's 0.0051 per fill was higher than real (0.0027–0.0047).
- **The guard.** It is right at our speed. Without it, the 180 failed buys would have lost 2.8 SOL more (replayed).

## What to work on (INFERRED from the above)

1. **Land earlier on crowded dumps.** The first 10 ms faster is worth about +5–6 SOL/day here; the next 10 ms another +1.6–2.3. The race is a few ms against rivals in the same batch, on the dumps that matter.
2. **Keep the ~1 s exit.** No more 4 s holds. Hold 5 beats hold 6 at our speed.
3. **Keep nonce (one tip). Avoid 15M priority on failed buys.**
4. **Until landing improves, expect little.** Today's exit on these 309 buys replays at about +1 SOL/day for both servers: thin, and not yet seen live (FRA 15 + AMS 14 so far: −0.08 on 41 buys).

---

## Evidence

### A. Where our buys really land (MEASURED, 309 buys)

The replay's block-position clock: slot × 212 ms + (index in block ÷ 400) × 212 ms. The replay's "35 ms" means ~66 transactions after the dump in the same block.

| Group | n | p10 / p25 / median / p75 / p90 (ms) | Same block | ≤35 ms | ≤50 ms | ≤75 ms |
|---|---|---|---|---|---|---|
| All buys | 309 | 21 / 33 / 58 / 101 / 162 | 78% | 29% | 42% | 60% |
| Fills | 129 | 21 / 29 / 45 / 79 / 150 | 78% | 38% | 55% | 72% |
| Failed buys | 180 | 25 / 41 / 74 / 107 / 164 | 77% | 23% | 33% | 51% |
| Nonce runs (FRA 11+, AMS 11+) | 173 | 23 / 35 / 61 / 104 / 170 | 75% | 25% | – | – |
| Jito leaders | 92 | 21 / 44 / 82 / 119 / 174 | 65% | 20% | 30% | 45% |
| BAM | 89 | 21 / 26 / 40 / 76 / 95 | 90% | 47% | 62% | 74% |
| Harmonic | 68 | 24 / 33 / 51 / 82 / 135 | 81% | 31% | 46% | 71% |
| Harmonic-FD | 32 | 32 / 47 / 74 / 106 / 160 | 81% | 16% | 31% | 50% |
| Rakurai | 8 | 177 / 229 / 252 / 259 / 272 | 12% | 0% | 0% | 0% |

On our own feed clock (executed feed, MEASURED):
- Our buy shows up a median of **41 ms** after the dump (p25 31, p75 74, p90 142).
- The first rival buy shows up a median of **18 ms** after the dump (p25 3, p75 33). A rival landed before us on 273 of 309 dumps.
- Median trades on the token between the dump and our buy: 3. None on 10% of buys.

### B. The replay at our real landing reproduces live

| Run | Hours | Buys / fills | Paper 35 ms | Paper 50 ms | Paper 75 ms | Paper at our landing | Corrected at our landing | **Live** |
|---|---|---|---|---|---|---|---|---|
| FRA r10 (4 s hold, 0.55/0.75) | 6.0 | 73 / 29 | +0.24 | −0.34 | −0.69 | −0.232 | −0.159 | **−0.073** |
| FRA r11 (4 s hold) | 0.4 | 5 / 2 | −0.08 | −0.13 | −0.14 | −0.069 | −0.078 | **−0.072** |
| FRA r13 | 0.7 | 23 / 5 | +0.23 | +0.12 | +0.11 | +0.038 | +0.021 | **+0.015** |
| FRA r14 | 4.4 | 63 / 27 | +0.43 | +0.30 | +0.23 | +0.055 | −0.001 | **+0.048** |
| FRA r15 (M2 gate, hold 5) | 1.7 | 38 / 14 | +0.32 | +0.14 | +0.10 | −0.042 | −0.013 | **−0.025** |
| AMS r9 | 1.3 | 7 / 2 | +0.11 | +0.11 | +0.11 | −0.081 | −0.054 | **−0.057** |
| AMS r10 | 6.0 | 56 / 30 | +0.29 | +0.27 | +0.18 | −0.181 | −0.095 | **−0.138** |
| AMS r11 | 0.4 | 3 / 1 | −0.03 | −0.04 | −0.04 | −0.022 | −0.020 | **−0.020** |
| AMS r12 (15M prio) | 0.7 | 7 / 1 | −0.08 | +0.00 | −0.03 | +0.026 | +0.022 | **+0.022** |
| AMS r13 (15M prio) | 4.4 | 31 / 17 | +0.44 | +0.14 | +0.01 | −0.156 | −0.008 | **−0.014** |
| AMS r14 (hold 5, no-BAM list) | 1.6 | 3 / 1 | −0.05 | −0.05 | −0.05 | −0.058 | −0.056 | **−0.056** |
| **All** | 27.6 | 309 / 129 | **+1.84** | **+0.54** | **−0.19** | **−0.72** | **−0.44** | **−0.37** |

- The paper columns use the old model with engine rules. The corrected column is per buy, at the exact chain position.
- Per-buy correlation of corrected vs live on fills: 0.96.
- Exit type agrees on 126 of 129 fills.

### C. Fills, gap split (128 fills; the 129th is the borderline guard case)

| Step | SOL |
|---|---|
| Replay at our exact landing (old model: paper exit, FIX 0.0051) | −0.538 |
| (a) Entry: model tokens → live tokens | 0.000 |
| (b) Exit: paper sell slot → our real sell position | +0.094 |
| (c) Followers / tape: model tape → what our sell really got | +0.038 |
| (d) Costs: FIX → real fees + tips | +0.147 |
| (e) Other (rent, rounding) | −0.003 |
| **Live fills (chain)** | **−0.262** |

Exit (b), split by exit type:
- **Time-limit sells:** the engine sells at slot s_in + hold − 1 (96 of 107), not s_in + hold. That is +0.24 on hold-6 runs.
- **Stop-loss sells:** these land ~42 ms after the trigger trade, while the paper sold in the next slot. The paper was slightly optimistic here (−0.17 on 22 stop-loss fills).
- Stop-loss fills lost −1.44 SOL in total. Time-limit fills made +1.18.

Failed buys: the model charged 0.090, real was 0.111. The extra came from 15M priority on AMS 12–13.

### D. Being late filters out the good dumps (replayed + MEASURED)

| Dumps by replay value if first in line | Buys | Our landing (block / feed ms) | Rival trades ahead | **Live fill rate** |
|---|---|---|---|---|
| Worst third | 102 | 45 / 38 | 2.5 | **65%** |
| Middle third | 105 | 62 / 40 | 3.6 | 31% |
| Best third | 102 | 64 / 44 | 4.1 | **29%** |

- Live-failed buys (180):
  - at 35 ms, the replay fills 74 of them, worth **+2.0 SOL**;
  - at 50 ms, 47 of them (+1.2);
  - at 20 ms, 124 of them (+5.6).
- Live fills (129) at 35 ms: +0.01. The 35-ms profit sits in the dumps we lost the race on.
- Shuffle test, same 309 dumps (corrected replay):
  - our real landings: −0.44;
  - landings shuffled at random across dumps: **+1.56**;
  - shuffled within leader type or block position: +0.75 to +0.99.
  - So our lateness is concentrated on the dumps that pay. That crowding is not explained by leader or block position alone.
- Live by landing bucket (MEASURED): our fastest buys did not earn more. 0–35 ms −0.46 SOL on 90 buys; 50–150 ms +0.23 on 142. These are different dumps (selection). The replay at our exact landing tracks each bucket.

### E. Real rivals on the same 309 dumps (MEASURED, real tape)

Each rival buy ≥0.05 SOL is valued with our exit (its tokens at its landing slot +5), after pump fees, before tx fees.

| Rival landed after the dump | Buys | With our exit | Win | With its own exit |
|---|---|---|---|---|
| 0–10 ms | 110 | +4.5% | 64% | +4.8% |
| 10–20 ms | 123 | +6.8% | 72% | +9.0% |
| 20–35 ms | 279 | +5.5% | 56% | +4.2% |
| 35–50 ms | 258 | +4.5% | 57% | +8.3% |
| 50–75 ms | 269 | +0.7% | 48% | +1.4% |
| 75–100 ms | 212 | −0.8% | 40% | +0.7% |
| 100–150 ms | 273 | −0.3% | 39% | +0.1% |
| 150–300 ms | 391 | −1.9% | 34% | +1.0% |

Real positions in the first 50 ms made about +4.5–7%. After 50 ms they made about 0.
This is the replay's speed curve, seen in real money. Our own fills at 20–50 ms made ~0% because the guard filters out the good dumps (D).

### F. Exits at our real landing (corrected replay, same 309 buys)

| Exit (sell slot) | No stop-loss | SL 10% | SL 20% | At 35 ms (no SL) |
|---|---|---|---|---|
| hold 3 (+2) | +0.75 | +0.73 | +0.75 | +4.59 |
| hold 4 (+3) | +0.70 | +0.72 | +0.74 | +4.02 |
| **hold 5 (+4)** | **+1.04** | +1.10 | +1.13 | +3.95 |
| hold 6 (+5) | +0.54 | +0.60 | +0.65 | +3.22 |
| hold 8 (+7) | −0.06 | 0.00 | −0.04 | +3.18 |
| hold 12 (+11) | −1.40 | −1.10 | −1.34 | +2.12 |
| hold 19 (+18) | −2.15 | −1.75 | −2.12 | +0.73 |

The runs' own exits gave −0.44 in total. A ~1 s exit (hold 5) everywhere: +1.04 to +1.13.
- FRA r10: −0.16 as run vs +0.91 with hold 5.
- MEASURED check on the real tape: FRA 10–11 fills sold at slot +5 instead of +18 bring back +0.98 SOL.

### G. Where the live money went (MEASURED, chain)

| | Fills | Curve gain | Pump fees | Tx fees | Tips | Fills net | Failed buys | **Total** |
|---|---|---|---|---|---|---|---|---|
| FRA | 77 | +1.109 | −0.872 | −0.086 | −0.196 | −0.044 | −0.063 (125) | **−0.108** |
| AMS | 52 | +0.555 | −0.541 | −0.076 | −0.151 | −0.216 | −0.048 (55) | **−0.263** |
| All | 129 | +1.664 | −1.412 | −0.162 | −0.347 | −0.260 | −0.111 (180) | **−0.371** |

FRA runs 1–9 (10-24 02:15–18:15, +0.43 SOL by the run index) are not in the copied records and are not reconciled here.

## Model corrections (made in a copy, ops/dip/recon/rsim.py)

1. **Exit timing (MEASURED).** The time-limit sell lands in slot s_in + hold − 1 at a median index of 148, not slot s_in + hold. Stop-loss sells land ~42 block-ms after the trigger trade, not in the next slot at 75 ms.
2. **Costs (MEASURED per run).** Per fill: 0.0027–0.0047 instead of FIX 0.0051. Per failed buy: 0.000505 (5M priority) or 0.001505 (15M) instead of 0.0005.
3. **Busy time after a failed buy:** 0.2 s, not 0.8 s. Live median is 45 ms; this barely matters.
4. **Our own trades** are removed from the tape for every counterfactual.
5. **Unchanged, because verified:** entry math (exact), the +5% guard (308/309), and the follower slack model (+0.04 effect at our landing).

Result: corrected replay at our measured landing −0.44 vs live −0.37. Per-buy residual mean +0.0002 SOL, sd 0.010. 90% bootstrap CI of the total residual: −0.24 to +0.37. **Within noise.**

## Method

- **Live records (read-only):** /home/moiz/sniper-data/recon/live (FRA dip_r10–r15, AMS dip_ams_r9–r14). Fires are linked to land / exit / sell / close records and to REALIZED lines.
- **Chain:** raw recordings run_20261024_1425 (19:25→07:56) and run_20261023_1426 (to 20:26), grepped for our two wallets.
  - Every fire's landed copy was found, through nonce per-path signatures or the buy signature: 309 of 309.
  - Live P&L = our wallet's SOL change in those txs. It equals the REALIZED lines (−0.2599 vs −0.2600 on fills).
- **Tape:** the study's own pipeline, imported unchanged (dd20 stage_extract → p1_build → dd1_build). Output: WORK/NEW, WORK/OLD.
  - rsim.run_path reproduces dd1_build.path() exactly when our trades are kept: 0 mismatches on 18,000 status checks and 51,810 P&L checks.
- **Landing:** our tx (slot, index) vs the dump (slot, index) on the replay clock.
  - Feed clock: the engine's tape records give the rx time of all 1,041 trades between the dumps and our buys.
- **Leaders:** epoch schedules 1066/1067 plus the servers' near lists (AMS 14 uses the no-BAM list). These reproduce every far-leader skip of the engine.
- **Scripts** (ops/dip/recon/):

| Script | What it does |
|---|---|
| r01 | grep for our txs |
| r02 | fires ↔ chain |
| r03 | tape build |
| r04 | landing |
| r05 | self-test |
| r06 | recording completeness |
| r07 | per buy + gap split |
| r08 | live-config forecast |
| r09 | by landing |
| r10 | our trades in the tape |
| r11 | waterfall |
| r12 | sell latency |
| r13 | corrected model |
| r14 | shifts / shuffle |
| r15 | strata |
| r16 / r17 | feed clock / real time |
| r18 | rivals |
| r19 | guard |
| r20 / r21 / r22 | money / exits / FRA 4 s check |
| r23 | price of speed |
| r24 | replay vs live sets |
| r25 | tables |
| r26 | offline picks vs engine picks (feed gaps) |

- **Data:** /home/moiz/sniper-data/recon/work (pertrade.json, pertrade_table.csv, price.json, …).
- **Limits:**
  - One night and morning. FRA r15 and AMS r14 are partial.
  - The block clock assumes 400 txs per block.
  - The "X ms faster" rows assume the same picks and the same rival behaviour.
  - Rivals' tx fees are excluded in E.

## Appendix: every live buy (309)

Columns:
- **Land ms:** our landing on the block clock / on our feed clock.
- **Ahead:** trades on the token between the dump and us.
- **Model@ours:** corrected replay at our exact landing.
- **@35 / @50:** replay (old model) if we had landed 35 / 50 ms after the dump. "fail" means the guard would have blocked the buy.

Times are PKT. Full CSV: /home/moiz/sniper-data/recon/work/pertrade_table.csv.

| # | Time | Srv r | Token | SOL | Leader | Land ms (blk / feed) | Ahead | Live | Live P&L | Model@ours | @35 | @50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 18:39:51 | F10 | 9yJrLW | 0.75 | Harmonic | 54 / 18 | 1 | fill time | +0.2740 | +0.2478 | +0.3533 | +0.3234 |
| 2 | 18:43:44 | F10 | 7gRYtM | 0.75 | HarmonicFD | 58 / 40 | 2 | fail | -0.0005 | -0.0005 | +0.0561 | fail |
| 3 | 18:44:53 | F10 | 3pQoFA | 0.55 | Bam | 58 / 40 | 1 | fill time | -0.0773 | -0.0777 | -0.0726 | -0.0781 |
| 4 | 18:54:43 | F10 | AuqgMZ | 0.75 | Bam | 35 / 23 | 4 | fail | -0.0005 | -0.0005 | fail | fail |
| 5 | 19:09:52 | F10 | 73ybJ9 | 0.75 | FD | 107 / 24 | 5 | fail | -0.0005 | -0.0005 | -0.0439 | -0.0525 |
| 6 | 19:21:13 | F10 | J9rqoR | 0.75 | Harmonic | 58 / 75 | 8 | fail | -0.0005 | -0.0005 | -0.0064 | fail |
| 7 | 19:24:09 | F10 | Av5zAP | 0.75 | HarmonicFD | 62 / 35 | 2 | fill time | -0.0090 | -0.0093 | +0.0154 | +0.0154 |
| 8 | 19:25:40 | F10 | DMG2yC | 0.75 | FD | 72 / 152 | 1 | fill time | -0.1079 | -0.1083 | -0.0839 | -0.0839 |
| 9 | 19:27:20 | F10 | Accbf1 | 0.75 | FD | 119 / 105 | 2 | fail | -0.0005 | -0.0005 | -0.0245 | fail |
| 10 | 19:29:59 | F10 | 6uJLG1 | 0.55 | FireBAM | 73 / 37 | 3 | fail | -0.0005 | -0.0005 | -0.0875 | -0.0875 |
| 11 | 19:32:37 | F10 | 3CkG8F | 0.75 | Bam | 29 / 23 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 12 | 19:33:32 | F10 | 9MrJk2 | 0.55 | Jito | 70 / 88 | 2 | fail | -0.0005 | -0.0005 | fail | fail |
| 13 | 19:38:57 | F10 | 5C9n5A | 0.75 | Bam | 68 / 44 | 7 | fail | -0.0005 | -0.0005 | fail | fail |
| 14 | 19:41:03 | F10 | 31NzeW | 0.75 | Bam | 45 / 25 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 15 | 19:43:26 | F10 | E4SB4t | 0.75 | Jito | 78 / 21 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 16 | 19:43:49 | F10 | 8Toe1m | 0.75 | Bam | 62 / 34 | 7 | fail | -0.0005 | -0.0005 | -0.0002 | -0.0002 |
| 17 | 19:44:32 | F10 | mhdaBD | 0.75 | Jito | 0 / 26 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 18 | 19:45:59 | F10 | GhJqiV | 0.55 | Harmonic | 56 / 36 | 2 | fill time | +0.0319 | +0.0315 | +0.0499 | +0.0342 |
| 19 | 19:49:19 | F10 | AqiZrp | 0.75 | Harmonic | 50 / 42 | 2 | fail | -0.0005 | -0.0005 | fail | fail |
| 20 | 19:50:15 | F10 | 2dfqZo | 0.55 | Harmonic | 36 / 42 | 2 | fill time | -0.0652 | -0.0655 | -0.0660 | fail |
| 21 | 19:56:54 | F10 | BJYXKr | 0.55 | Jito | 11 / 24 | 0 | fill time | -0.0141 | -0.0137 | -0.1029 | -0.1031 |
| 22 | 20:03:55 | F10 | 4j2zFU | 0.75 | Harmonic | 34 / 38 | 1 | fill time | -0.0535 | -0.0539 | -0.0412 | fail |
| 23 | 20:09:32 | F10 | 3ASKsS | 0.55 | Harmonic | 29 / 36 | 2 | fill time | +0.0120 | +0.0116 | -0.0344 | -0.0121 |
| 24 | 20:20:16 | F10 | 3yEGBB | 0.55 | HarmonicFD | 34 / 26 | 1 | fill time | +0.1477 | +0.0447 | +0.1469 | +0.1369 |
| 25 | 20:21:25 | F10 | HviocW | 0.55 | Jito | 73 / 58 | 4 | fail | -0.0005 | -0.0005 | fail | fail |
| 26 | 20:28:41 | F10 | AGQsio | 0.55 | Jito | 131 / 162 | 4 | fill time | -0.0049 | -0.0045 | -0.0043 | -0.0076 |
| 27 | 20:31:47 | F10 | 52zSqi | 0.55 | Harmonic | 82 / 120 | 1 | fill time | +0.0092 | +0.0089 | +0.0847 | +0.0847 |
| 28 | 20:41:06 | F10 | 2ZxDfX | 0.55 | Jito | 106 / 92 | 5 | fail | -0.0005 | -0.0005 | -0.0216 | fail |
| 29 | 21:07:55 | F10 | B8LJEK | 0.55 | HarmonicFD | 206 / 64 | 5 | fail | -0.0005 | -0.0005 | +0.0818 | +0.0818 |
| 30 | 21:10:45 | F10 | GsxThS | 0.55 | Jito | 21 / 16 | 1 | fill stop | -0.1304 | -0.1300 | -0.1304 | -0.1304 |
| 31 | 21:14:18 | F10 | 2quvaC | 0.55 | Harmonic | 48 / 43 | 6 | fail | -0.0005 | -0.0005 | fail | fail |
| 32 | 21:15:29 | F10 | 2pFWgK | 0.55 | Jito | 180 / 119 | 4 | fail | -0.0005 | -0.0005 | +0.0182 | fail |
| 33 | 21:18:52 | F10 | FPXcFJ | 0.75 | Jito | 313 / 128 | 3 | fail | -0.0005 | -0.0005 | -0.0234 | -0.0234 |
| 34 | 21:19:37 | F10 | CcQN8v | 0.55 | Jito | 39 / 22 | 0 | fill time | -0.0931 | -0.0926 | -0.0762 | -0.0762 |
| 35 | 21:30:36 | F10 | 9wgKeh | 0.55 | Jito | 86 / 29 | 7 | fail | -0.0005 | -0.0005 | -0.1236 | -0.1236 |
| 36 | 21:34:12 | F10 | 4r3KsK | 0.75 | Bam | 47 / 16 | 0 | fill time | -0.0772 | -0.0758 | -0.0712 | -0.0712 |
| 37 | 21:41:27 | F10 | Ba5uvU | 0.55 | FD | 33 / 29 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 38 | 21:41:50 | F10 | 9p9XvH | 0.55 | FireBAM | 37 / 39 | 3 | fill time | +0.0326 | +0.0322 | +0.0446 | fail |
| 39 | 21:42:13 | F10 | HAWDeL | 0.75 | Bam | 10 / 77 | 2 | fail | -0.0005 | -0.0005 | fail | fail |
| 40 | 21:42:19 | F10 | FnBz44 | 0.55 | HarmonicFD | 99 / 109 | 7 | fail | -0.0005 | -0.0005 | +0.1652 | +0.1652 |
| 41 | 21:57:11 | F10 | 4bqLVg | 0.75 | Jito | 19 / 19 | 0 | fill time | +0.0886 | +0.0890 | -0.0021 | -0.0021 |
| 42 | 22:14:01 | F10 | CT2u9m | 0.55 | Harmonic | 51 / 38 | 2 | fail | -0.0005 | -0.0005 | fail | fail |
| 43 | 22:16:56 | F10 | EYkp6m | 0.55 | Rakurai | 220 / 190 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 44 | 22:20:58 | F10 | 8bTZh3 | 0.55 | Jito | 93 / 117 | 2 | fail | -0.0005 | -0.0005 | fail | fail |
| 45 | 22:21:10 | F10 | 5R85Af | 0.75 | HarmonicFD | 53 / 39 | 7 | fail | -0.0005 | -0.0005 | fail | fail |
| 46 | 22:24:37 | F10 | HT1iHU | 0.55 | FireBAM | 41 / 26 | 0 | fill time | +0.0232 | +0.0246 | -0.0465 | fail |
| 47 | 22:28:42 | F10 | HT1iHU | 0.55 | Harmonic | 34 / 37 | 1 | fill time | +0.2325 | +0.2321 | +0.2435 | fail |
| 48 | 22:30:30 | F10 | DvihJS | 0.75 | Jito | 84 / 51 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 49 | 22:30:56 | F10 | GSczhd | 0.55 | Bam | 26 / 22 | 4 | fail | -0.0005 | -0.0005 | fail | fail |
| 50 | 22:31:27 | F10 | BhUEc9 | 0.75 | Bam | 20 / 22 | 1 | fill stop | -0.1259 | -0.0496 | fail | fail |
| 51 | 22:32:49 | F10 | vbVL5z | 0.75 | Bam | 16 / 50 | 7 | fail | -0.0005 | -0.0005 | fail | fail |
| 52 | 22:37:28 | F10 | G4joZZ | 0.55 | Harmonic | 31 / 35 | 1 | fill time | -0.0644 | -0.0648 | -0.0929 | -0.0929 |
| 53 | 22:47:07 | F10 | 8KifAw | 0.55 | Jito | 44 / 66 | 4 | fill time | +0.0950 | +0.0964 | +0.1012 | fail |
| 54 | 22:54:51 | F10 | FggJtT | 0.55 | Jito | 24 / 44 | 0 | fill time | -0.0355 | -0.0351 | -0.0597 | -0.0597 |
| 55 | 22:55:19 | F10 | BnH2vi | 0.55 | Rakurai | 259 / 218 | 2 | fill time | +0.0371 | +0.0367 | +0.0542 | +0.0542 |
| 56 | 23:06:31 | F10 | CEjhQz | 0.55 | Jito | 66 / 57 | 7 | fail | -0.0005 | -0.0005 | fail | fail |
| 57 | 23:06:57 | F10 | icFbVj | 0.55 | Harmonic | 125 / 50 | 5 | fail | -0.0005 | -0.0005 | +0.1001 | +0.1001 |
| 58 | 23:13:33 | F10 | hg6Xcu | 0.55 | Harmonic | 91 / 36 | 13 | fail | -0.0005 | -0.0005 | fail | fail |
| 59 | 23:13:39 | F10 | hg6Xcu | 0.55 | HarmonicFD | 81 / 50 | 7 | fail | -0.0005 | -0.0005 | +0.0300 | +0.0300 |
| 60 | 23:22:46 | F10 | 9BuQe6 | 0.55 | Rakurai | 255 / 222 | 8 | fail | -0.0005 | -0.0005 | fail | fail |
| 61 | 23:23:24 | F10 | 7ikRmb | 0.55 | Jito | 84 / 31 | 6 | fail | -0.0005 | -0.0005 | +0.0031 | fail |
| 62 | 23:34:31 | F10 | EEeM95 | 0.75 | HarmonicFD | 30 / 45 | 2 | fill time | -0.0399 | -0.0403 | -0.0407 | -0.0407 |
| 63 | 23:37:03 | F10 | DqZM5q | 0.55 | Bam | 80 / 39 | 1 | fill time | +0.0415 | +0.0411 | +0.0346 | +0.0346 |
| 64 | 23:40:10 | F10 | G8w8pL | 0.75 | Jito | 67 / 52 | 6 | fail | -0.0005 | -0.0005 | fail | fail |
| 65 | 23:46:45 | F10 | H1q9uz | 0.75 | Bam | 41 / 40 | 6 | fail | -0.0005 | -0.0005 | fail | fail |
| 66 | 23:50:07 | F10 | EaH5RF | 0.75 | Jito | 18 / 13 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 67 | 23:54:07 | F10 | g6suz6 | 0.75 | Bam | 25 / 24 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 68 | 23:54:18 | F10 | g6suz6 | 0.75 | FireBAM | 54 / 29 | 5 | fail | -0.0005 | -0.0005 | +0.2556 | fail |
| 69 | 00:00:44 | F10 | 2K7w4Y | 0.55 | Jito | 106 / 91 | 8 | fail | -0.0005 | -0.0005 | fail | fail |
| 70 | 00:02:36 | F10 | EESKwE | 0.55 | HarmonicFD | 162 / 135 | 10 | fill time | -0.0344 | -0.0348 | -0.0157 | -0.0157 |
| 71 | 00:05:54 | F10 | DmtjsW | 0.55 | HarmonicFD | 104 / 161 | 4 | fail | -0.0005 | -0.0005 | +0.0315 | +0.0315 |
| 72 | 00:08:03 | F10 | 237yvo | 0.55 | FD | 108 / 18 | 0 | fill stop | -0.1113 | -0.1457 | -0.1330 | -0.1330 |
| 73 | 00:10:39 | F10 | 2djKVZ | 0.55 | Jito | 21 / 41 | 1 | fill time | -0.0321 | -0.0317 | -0.0321 | -0.0321 |
| 74 | 00:38:00 | F11 | 9QKaSS | 0.75 | Bam | 74 / 45 | 6 | fail | -0.0005 | -0.0005 | fail | fail |
| 75 | 00:40:11 | F11 | FHfq6g | 0.75 | Jito | 28 / 38 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 76 | 00:48:44 | F11 | 8Ub8f4 | 0.55 | Harmonic | 44 / 37 | 1 | fill time | +0.0639 | +0.0578 | +0.0755 | fail |
| 77 | 00:48:51 | F11 | 8SytCS | 0.55 | Jito | 77 / 53 | 1 | fill stop | -0.1343 | -0.1343 | -0.1245 | -0.1245 |
| 78 | 00:49:01 | F11 | EkXjwZ | 0.75 | HarmonicFD | 106 / 38 | 5 | fail | -0.0005 | -0.0005 | -0.0286 | fail |
| 79 | 00:59:27 | F13 | GudTWM | 0.35 | Jito | 42 / 42 | 2 | fill time | +0.0710 | +0.0704 | +0.0798 | fail |
| 80 | 00:59:55 | F13 | 65Xh5J | 0.35 | Harmonic | 34 / 39 | 1 | fill time | -0.0003 | +0.0001 | -0.0023 | -0.0023 |
| 81 | 01:01:09 | F13 | GvMhGu | 0.35 | Jito | 116 / 246 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 82 | 01:01:39 | F13 | 5Vyhzr | 0.35 | Jito | 163 / 50 | 3 | fail | -0.0005 | -0.0005 | +0.0144 | +0.0144 |
| 83 | 01:03:42 | F13 | CGhzAy | 0.35 | Harmonic | 181 / 158 | 6 | fail | -0.0005 | -0.0005 | +0.0473 | +0.0473 |
| 84 | 01:07:59 | F13 | 3QYw3G | 0.35 | FireBAM | 103 / 36 | 7 | fail | -0.0005 | -0.0005 | +0.0283 | +0.0283 |
| 85 | 01:11:36 | F13 | FYaXon | 0.35 | Bam | 23 / 30 | 6 | fail | -0.0005 | -0.0005 | fail | fail |
| 86 | 01:16:58 | F13 | 4xtwhV | 0.35 | HarmonicFD | 91 / 73 | 2 | fail | -0.0005 | -0.0005 | -0.0120 | fail |
| 87 | 01:24:55 | F13 | A1WKnK | 0.35 | Jito | 323 / 119 | 1 | fill time | +0.0090 | +0.0094 | +0.0065 | +0.0065 |
| 88 | 01:25:39 | F13 | 9jo3kZ | 0.35 | Harmonic | 0 / 11 | 1 | fail | -0.0005 | -0.0005 | fail | fail |
| 89 | 01:25:59 | F13 | FHuWQy | 0.35 | Harmonic | 2 / 39 | 4 | fail | -0.0005 | -0.0005 | fail | fail |
| 90 | 01:26:10 | F13 | A3N4Dc | 0.35 | Bam | 32 / 28 | 8 | fail | -0.0005 | -0.0005 | fail | fail |
| 91 | 01:26:20 | F13 | EiQ74g | 0.35 | Harmonic | 187 / 44 | 8 | fail | -0.0005 | -0.0005 | fail | fail |
| 92 | 01:27:20 | F13 | 4iSKaa | 0.35 | Harmonic | 71 / 323 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 93 | 01:27:25 | F13 | E7o1Ft | 0.35 | HarmonicFD | 49 / 44 | 5 | fail | -0.0005 | -0.0005 | +0.0211 | fail |
| 94 | 01:27:29 | F13 | FHuWQy | 0.35 | Bam | 40 / 21 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 95 | 01:28:10 | F13 | Aw88TK | 0.35 | Jito | 166 / 236 | 4 | fail | -0.0005 | -0.0005 | +0.0163 | +0.0092 |
| 96 | 01:28:48 | F13 | AwdLBu | 0.35 | Bam | 92 / 39 | 1 | fail | -0.0005 | -0.0005 | fail | fail |
| 97 | 01:30:48 | F13 | GNBsvY | 0.35 | Bam | 23 / 33 | 0 | fill stop | -0.0547 | -0.0499 | fail | fail |
| 98 | 01:31:17 | F13 | 2megwG | 0.35 | Harmonic | 119 / 129 | 1 | fail | -0.0005 | -0.0005 | +0.0210 | +0.0210 |
| 99 | 01:34:02 | F13 | 5eFE4a | 0.35 | Jito | 42 / 40 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 100 | 01:34:44 | F13 | GhksrL | 0.35 | Harmonic | 57 / 47 | 2 | fail | -0.0005 | -0.0005 | +0.0190 | fail |
| 101 | 01:39:31 | F13 | 6bKjj2 | 0.35 | Jito | 163 / 176 | 8 | fill time | -0.0006 | -0.0002 | fail | fail |
| 102 | 01:43:43 | F14 | 2EiGAC | 0.35 | Harmonic | 82 / 141 | 6 | fill time | +0.0089 | +0.0139 | +0.0232 | +0.0232 |
| 103 | 01:53:18 | F14 | 2vnSUU | 0.35 | HarmonicFD | 70 / 43 | 5 | fill time | +0.0100 | +0.0100 | -0.0311 | -0.0311 |
| 104 | 02:00:33 | F14 | 6y38hn | 0.35 | FireBAM | 176 / 82 | 5 | fill time | -0.0378 | -0.0366 | -0.0461 | -0.0461 |
| 105 | 02:04:06 | F14 | DaWdz2 | 0.35 | HarmonicFD | 31 / 192 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 106 | 02:04:14 | F14 | DaWdz2 | 0.35 | Jito | 309 / 141 | 4 | fill time | +0.1159 | +0.1149 | +0.1273 | +0.1273 |
| 107 | 02:05:04 | F14 | DaWdz2 | 0.35 | HarmonicFD | 42 / 34 | 8 | fill time | +0.0147 | +0.0190 | +0.0357 | -0.0073 |
| 108 | 02:11:47 | F14 | GrJNQg | 0.35 | Bam | 35 / 33 | 1 | fill time | +0.0476 | +0.0476 | +0.0456 | +0.0340 |
| 109 | 02:12:13 | F14 | GKCXhq | 0.35 | Jito | 80 / 43 | 5 | fail | -0.0005 | -0.0005 | +0.0338 | +0.0338 |
| 110 | 02:12:20 | F14 | GrJNQg | 0.35 | HarmonicFD | 212 / 164 | 6 | fail | -0.0005 | -0.0005 | fail | +0.0039 |
| 111 | 02:14:10 | F14 | BjCCdA | 0.35 | HarmonicFD | 37 / 45 | 2 | fill stop | -0.0470 | -0.0629 | -0.0371 | -0.0371 |
| 112 | 02:16:36 | F14 | BjCCdA | 0.35 | Harmonic | 45 / 25 | 5 | fill time | +0.0077 | +0.0078 | +0.0106 | fail |
| 113 | 02:18:05 | F14 | EunKeo | 0.35 | HarmonicFD | 141 / 148 | 3 | fail | -0.0005 | -0.0005 | +0.0120 | +0.0120 |
| 114 | 02:20:57 | F14 | 6Y1phM | 0.35 | Bam | 66 / 43 | 0 | fill time | -0.0076 | -0.0236 | -0.0095 | -0.0095 |
| 115 | 02:27:14 | F14 | 2nQXUn | 0.35 | Jito | 44 / 47 | 0 | fill stop | -0.0182 | -0.0264 | -0.0375 | -0.0375 |
| 116 | 02:33:46 | F14 | 6M8tUF | 0.35 | Jito | 25 / 14 | 4 | fail | -0.0005 | -0.0005 | fail | fail |
| 117 | 02:33:49 | F14 | 6ADR8g | 0.35 | Jito | 331 / 138 | 0 | fill time | -0.0041 | -0.0040 | -0.0060 | -0.0060 |
| 118 | 02:34:52 | F14 | 2i6JMW | 0.35 | Harmonic | 37 / 36 | 1 | fill time | +0.0074 | +0.0075 | +0.0054 | fail |
| 119 | 02:39:12 | F14 | GJuS1Y | 0.35 | Jito | 33 / 28 | 0 | fill time | -0.0015 | -0.0014 | -0.0226 | fail |
| 120 | 02:46:54 | F14 | 2HUyjP | 0.35 | Jito | 132 / 139 | 6 | fill time | +0.0219 | +0.0219 | +0.0314 | +0.0304 |
| 121 | 02:50:42 | F14 | DAvnee | 0.35 | FD | 20 / 29 | 4 | fail | -0.0005 | -0.0005 | fail | fail |
| 122 | 02:56:05 | F14 | 3KmUfH | 0.35 | Jito | 85 / 43 | 4 | fail | -0.0005 | -0.0005 | fail | fail |
| 123 | 02:58:04 | F14 | 4o1drX | 0.35 | Jito | 80 / 54 | 9 | fail | -0.0005 | -0.0005 | fail | fail |
| 124 | 03:01:04 | F14 | 2x9K6j | 0.35 | FD | 116 / 18 | 7 | fail | -0.0005 | -0.0005 | +0.0119 | fail |
| 125 | 03:01:41 | F14 | 5WDsNf | 0.35 | FD | 157 / 42 | 6 | fail | -0.0005 | -0.0005 | +0.0229 | fail |
| 126 | 03:08:22 | F14 | DnEcoP | 0.35 | HarmonicFD | 21 / 32 | 1 | fill time | +0.0187 | +0.0171 | fail | fail |
| 127 | 03:09:46 | F14 | CkjNR3 | 0.35 | Jito | 65 / 64 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 128 | 03:13:00 | F14 | CxS5LW | 0.35 | Jito | 174 / 190 | 6 | fail | -0.0005 | -0.0005 | +0.0065 | +0.0065 |
| 129 | 03:13:19 | F14 | DsBjEX | 0.35 | Jito | 817 / 692 | 6 | fail | -0.0005 | -0.0005 | +0.0118 | +0.0118 |
| 130 | 03:14:31 | F14 | 2vFbLD | 0.35 | Jito | 25 / 42 | 2 | fill time | +0.0021 | -0.0005 | fail | fail |
| 131 | 03:14:51 | F14 | 2Memge | 0.35 | Jito | 62 / 39 | 8 | fail | -0.0005 | -0.0005 | +0.0116 | fail |
| 132 | 03:19:28 | F14 | 7hb9VC | 0.35 | Jito | 288 / 134 | 1 | fill stop | -0.0397 | -0.0468 | -0.0096 | -0.0096 |
| 133 | 03:22:00 | F14 | 5eV1K7 | 0.35 | Bam | 86 / 41 | 4 | fail | -0.0005 | -0.0005 | fail | fail |
| 134 | 03:28:11 | F14 | 345gnr | 0.35 | Harmonic | 68 / 31 | 0 | fill stop | -0.0276 | -0.0368 | -0.0231 | -0.0231 |
| 135 | 03:30:25 | F14 | 2xhyMi | 0.35 | Bam | 21 / 33 | 1 | fill stop | -0.0471 | -0.0471 | -0.0534 | -0.0553 |
| 136 | 03:31:09 | F14 | 3pC52p | 0.35 | Jito | 153 / 73 | 4 | fail | -0.0005 | -0.0005 | +0.0079 | fail |
| 137 | 03:41:23 | F14 | 6YuXTu | 0.35 | Bam | 37 / 57 | 1 | fill time | -0.0126 | -0.0126 | -0.0234 | -0.0234 |
| 138 | 03:42:46 | F14 | 9YgsXm | 0.35 | FireBAM | 17 / 37 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 139 | 03:44:24 | F14 | 7oVimM | 0.35 | Harmonic | 51 / 31 | 2 | fill time | +0.0288 | +0.0288 | +0.0324 | +0.0406 |
| 140 | 03:45:27 | F14 | 3UqWUK | 0.35 | FD | 52 / 39 | 1 | fill time | -0.0105 | -0.0105 | -0.0069 | -0.0069 |
| 141 | 03:46:57 | F14 | 5vwH7y | 0.35 | Jito | 58 / 61 | 4 | fail | -0.0005 | -0.0005 | +0.0586 | +0.0423 |
| 142 | 03:55:03 | F14 | H2859o | 0.35 | FD | 36 / 24 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 143 | 03:58:48 | F14 | FeU7N6 | 0.35 | HarmonicFD | 176 / 147 | 5 | fail | -0.0005 | -0.0005 | +0.0300 | +0.0300 |
| 144 | 04:01:18 | F14 | 92kMHH | 0.35 | Bam | 92 / 32 | 1 | fill time | +0.0204 | +0.0148 | +0.0128 | +0.0128 |
| 145 | 04:03:08 | F14 | 8kJDFF | 0.35 | FireBAM | 33 / 30 | 2 | fail | -0.0005 | -0.0005 | fail | fail |
| 146 | 04:05:53 | F14 | 3g25Ko | 0.35 | Harmonic | 89 / 54 | 7 | fail | -0.0005 | -0.0005 | -0.0055 | -0.0055 |
| 147 | 04:07:36 | F14 | GBH3Lu | 0.35 | Jito | 101 / 125 | 4 | fail | -0.0005 | -0.0005 | fail | fail |
| 148 | 04:13:58 | F14 | 7a4tdC | 0.35 | Bam | 30 / 36 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 149 | 04:14:42 | F14 | Bk32JA | 0.35 | Bam | 41 / 34 | 2 | fail | -0.0005 | -0.0005 | fail | fail |
| 150 | 04:23:57 | F14 | 5sj3VR | 0.35 | HarmonicFD | 32 / 39 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 151 | 04:27:26 | F14 | CiqNUY | 0.35 | HarmonicFD | 62 / 76 | 3 | fail | -0.0005 | -0.0005 | -0.0207 | -0.0207 |
| 152 | 04:37:37 | F14 | Gfg6yj | 0.35 | Jito | 34 / 45 | 1 | fail | -0.0005 | -0.0005 | fail | fail |
| 153 | 04:40:16 | F14 | J4UCBh | 0.35 | Harmonic | 171 / 138 | 2 | fail | -0.0005 | -0.0005 | +0.0125 | +0.0125 |
| 154 | 04:49:44 | F14 | 128N5P | 0.35 | Bam | 25 / 15 | 1 | fill time | +0.0396 | +0.0397 | fail | fail |
| 155 | 04:52:57 | F14 | 8mwDEi | 0.35 | HarmonicFD | 49 / 39 | 4 | fail | -0.0005 | -0.0005 | fail | fail |
| 156 | 05:07:21 | F14 | CBmgZD | 0.35 | HarmonicFD | 90 / 36 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 157 | 05:09:53 | F14 | 5GTpzD | 0.35 | Harmonic | 52 / 33 | 1 | fill time | -0.0031 | -0.0030 | +0.0079 | -0.0051 |
| 158 | 05:11:53 | F14 | HBjNaR | 0.35 | Jito | 99 / 183 | 7 | fail | -0.0005 | -0.0005 | fail | fail |
| 159 | 05:15:10 | F14 | MbyosB | 0.35 | Jito | 44 / 50 | 2 | fail | -0.0005 | -0.0005 | -0.0167 | fail |
| 160 | 05:22:41 | F14 | DU7LpR | 0.35 | HarmonicFD | 106 / 150 | 5 | fail | -0.0005 | -0.0005 | +0.1048 | +0.1048 |
| 161 | 05:38:24 | F14 | 3xu825 | 0.35 | Jito | 95 / 46 | 3 | fill time | -0.0163 | -0.0082 | -0.0057 | -0.0057 |
| 162 | 05:44:24 | F14 | CqKSKX | 0.35 | Harmonic | 29 / 36 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 163 | 05:57:06 | F14 | wqDA8J | 0.35 | Harmonic | 150 / 145 | 4 | fill time | -0.0049 | -0.0048 | +0.0231 | +0.0231 |
| 164 | 05:57:20 | F14 | 6fkJjU | 0.35 | Rakurai | 250 / 217 | 8 | fail | -0.0005 | -0.0005 | +0.0173 | fail |
| 165 | 06:12:07 | F15 | 3bam7k | 0.35 | Harmonic | 61 / 43 | 2 | fill time | +0.0556 | +0.0557 | +0.0589 | +0.0589 |
| 166 | 06:12:15 | F15 | 6NVyns | 0.35 | Bam | 76 / 80 | 0 | fill time | -0.0018 | +0.0047 | +0.0026 | +0.0026 |
| 167 | 06:12:53 | F15 | E4TMRb | 0.35 | Harmonic | 77 / 36 | 3 | fail | -0.0005 | -0.0005 | +0.0110 | +0.0110 |
| 168 | 06:15:34 | F15 | Ez39gv | 0.35 | Bam | 28 / 21 | 1 | fill time | -0.0384 | -0.0384 | fail | fail |
| 169 | 06:17:32 | F15 | Ejgwrr | 0.35 | Bam | 29 / 23 | 6 | fail | -0.0005 | -0.0005 | fail | fail |
| 170 | 06:19:21 | F15 | GTabiB | 0.35 | Jito | 104 / 73 | 7 | fail | -0.0005 | -0.0005 | +0.0492 | +0.0492 |
| 171 | 06:29:08 | F15 | 8D9Xss | 0.35 | Harmonic | 108 / 149 | 9 | fail | -0.0005 | -0.0005 | fail | fail |
| 172 | 06:30:27 | F15 | 2XqFe8 | 0.35 | Bam | 56 / 60 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 173 | 06:30:55 | F15 | 2vx7Sz | 0.35 | Jito | 94 / 92 | 11 | fail | -0.0005 | -0.0005 | +0.0369 | fail |
| 174 | 06:32:04 | F15 | FB7xku | 0.35 | HarmonicFD | 56 / 50 | 2 | fill time | +0.0180 | +0.0180 | +0.0324 | +0.0220 |
| 175 | 06:33:42 | F15 | JBTvRA | 0.35 | Jito | 127 / 127 | 4 | fail | -0.0005 | -0.0005 | -0.0014 | -0.0014 |
| 176 | 06:36:57 | F15 | 8ExCVE | 0.35 | Jito | 104 / 117 | 4 | fail | -0.0005 | -0.0005 | fail | fail |
| 177 | 06:37:21 | F15 | 127avc | 0.35 | Jito | 39 / 40 | 4 | fail | -0.0005 | -0.0005 | fail | fail |
| 178 | 06:38:23 | F15 | 6Te7vL | 0.35 | Bam | 56 / 36 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 179 | 06:38:45 | F15 | ARbV5E | 0.35 | Bam | 95 / 151 | 5 | fail | -0.0005 | -0.0005 | +0.0793 | +0.0793 |
| 180 | 06:39:00 | F15 | E9jEzy | 0.35 | Bam | 95 / 45 | 6 | fill time | -0.0306 | -0.0305 | +0.0212 | -0.0018 |
| 181 | 06:39:33 | F15 | EfKB6n | 0.35 | Bam | 18 / 19 | 0 | fill time | -0.0201 | -0.0200 | -0.0247 | -0.0234 |
| 182 | 06:40:20 | F15 | FzeP2j | 0.35 | Harmonic | 28 / 39 | 3 | fill time | +0.1519 | +0.1520 | +0.1536 | +0.1492 |
| 183 | 06:42:08 | F15 | 8HHRyn | 0.35 | Jito | 44 / 19 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 184 | 06:42:10 | F15 | LTAdFg | 0.35 | Harmonic | 54 / 27 | 2 | fill time | -0.0083 | -0.0093 | fail | -0.0113 |
| 185 | 06:42:30 | F15 | LTAdFg | 0.35 | Jito | 62 / 44 | 7 | fail | -0.0005 | -0.0005 | fail | fail |
| 186 | 06:43:04 | F15 | 6rvBYF | 0.35 | Harmonic | 50 / 41 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 187 | 07:01:01 | F15 | 42ef2A | 0.35 | Rakurai | 233 / 204 | 7 | fail | -0.0005 | -0.0005 | fail | fail |
| 188 | 07:02:02 | F15 | 8zsFH5 | 0.35 | Jito | 56 / 74 | 6 | fail | -0.0005 | -0.0005 | +0.0682 | fail |
| 189 | 07:06:18 | F15 | 3jPcVT | 0.35 | FD | 53 / 24 | 2 | fail | -0.0005 | -0.0005 | fail | fail |
| 190 | 07:09:54 | F15 | 4oHteQ | 0.35 | HarmonicFD | 102 / 96 | 4 | fail | -0.0005 | -0.0005 | -0.0118 | -0.0241 |
| 191 | 07:10:06 | F15 | 32yah1 | 0.35 | Harmonic | 62 / 54 | 1 | fill time | -0.0283 | -0.0283 | -0.0303 | -0.0303 |
| 192 | 07:19:57 | F15 | Fnhsze | 0.35 | Harmonic | 41 / 45 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 193 | 07:20:00 | F15 | Fnhsze | 0.35 | HarmonicFD | 78 / 78 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 194 | 07:20:01 | F15 | Fnhsze | 0.35 | Jito | 92 / 86 | 4 | fail | -0.0005 | -0.0005 | +0.0412 | +0.0364 |
| 195 | 07:21:08 | F15 | 6bJZTc | 0.35 | FD | 74 / 11 | 1 | fill time | -0.0248 | -0.0248 | -0.0268 | -0.0268 |
| 196 | 07:22:52 | F15 | rUzSLB | 0.35 | Bam | 29 / 22 | 0 | fill time | -0.0161 | -0.0161 | -0.0239 | -0.0239 |
| 197 | 07:31:48 | F15 | 33D1NN | 0.35 | Harmonic | 34 / 34 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 198 | 07:37:54 | F15 | 8hGKQA | 0.35 | Jito | 31 / 27 | 1 | fill time | +0.0166 | +0.0167 | fail | fail |
| 199 | 07:39:42 | F15 | 33V5Ee | 0.35 | Rakurai | 297 / 224 | 10 | fill time | -0.0739 | -0.0679 | -0.0937 | -0.0937 |
| 200 | 07:40:35 | F15 | 33kLyL | 0.35 | HarmonicFD | 39 / 31 | 0 | fill time | -0.0126 | -0.0125 | -0.0146 | -0.0232 |
| 201 | 07:43:36 | F15 | HVL4QH | 0.35 | Harmonic | 42 / 35 | 4 | fail | -0.0005 | -0.0005 | fail | fail |
| 202 | 07:49:22 | F15 | 9LepYg | 0.35 | Bam | 31 / 33 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 203 | 17:22:56 | A9 | 5G5Gei | 0.55 | Jito | 207 / 138 | 3 | fail | -0.0005 | -0.0005 | -0.0425 | -0.0425 |
| 204 | 17:24:39 | A9 | 6GgVYW | 0.55 | Bam | 60 / 24 | 2 | fill stop | -0.0571 | -0.0542 | -0.0610 | -0.0694 |
| 205 | 17:25:50 | A9 | AMZp4f | 0.55 | Harmonic | 43 / 33 | 3 | fill time | +0.0030 | +0.0030 | -0.0088 | fail |
| 206 | 17:33:19 | A9 | 9A3Zaz | 0.55 | Jito | 74 / 114 | 7 | fail | -0.0005 | -0.0005 | fail | fail |
| 207 | 17:56:29 | A9 | 3adKQ6 | 0.35 | Bam | 21 / 19 | 2 | fail | -0.0005 | -0.0005 | fail | fail |
| 208 | 17:59:06 | A9 | GMYFgs | 0.55 | HarmonicFD | 130 / 55 | 3 | fail | -0.0005 | -0.0005 | +0.2281 | +0.2281 |
| 209 | 18:09:47 | A9 | B8gesX | 0.55 | Bam | 33 / 24 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 210 | 18:25:26 | A10 | DPuSnf | 0.55 | Jito | 107 / 116 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 211 | 18:32:40 | A10 | 8cCv3o | 0.55 | Jito | 86 / 114 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 212 | 18:38:43 | A10 | fbsPyx | 0.35 | Bam | 33 / 23 | 2 | fill time | -0.0023 | -0.0090 | -0.0120 | -0.0300 |
| 213 | 18:39:55 | A10 | 9yJrLW | 0.55 | Jito | 96 / 42 | 0 | fill time | +0.0593 | +0.0590 | +0.0585 | +0.0585 |
| 214 | 18:42:37 | A10 | J5SxQW | 0.55 | Bam | 101 / 25 | 1 | fill time | +0.0572 | +0.0568 | +0.0536 | +0.0530 |
| 215 | 18:42:48 | A10 | J5SxQW | 0.55 | Jito | 150 / 47 | 0 | fill time | +0.0763 | +0.0829 | +0.0897 | +0.0897 |
| 216 | 18:45:12 | A10 | q2rc3D | 0.35 | Harmonic | 21 / 35 | 1 | fill time | -0.0327 | -0.0324 | -0.0423 | fail |
| 217 | 18:50:42 | A10 | 5JkWRU | 0.55 | Harmonic | 26 / 20 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 218 | 19:13:25 | A10 | 7xwA1c | 0.35 | Harmonic | 25 / 34 | 2 | fill time | +0.0374 | +0.0370 | fail | fail |
| 219 | 19:18:26 | A10 | HQPvWy | 0.55 | Bam | 44 / 19 | 1 | fail | -0.0005 | -0.0005 | -0.0084 | fail |
| 220 | 19:47:09 | A10 | 3TBYys | 0.35 | Bam | 46 / 49 | 1 | fill time | -0.0217 | -0.0221 | -0.0102 | -0.0260 |
| 221 | 19:53:56 | A10 | 5WE4sG | 0.35 | Harmonic | 47 / 33 | 1 | fill time | +0.0252 | +0.0248 | +0.0384 | +0.0244 |
| 222 | 19:55:01 | A10 | ASQ547 | 0.35 | Harmonic | 26 / 37 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 223 | 20:01:32 | A10 | 2bxA5g | 0.35 | Jito | 80 / 52 | 0 | fill time | +0.0016 | +0.0020 | +0.0014 | +0.0014 |
| 224 | 20:07:36 | A10 | 7Q8tE4 | 0.35 | Harmonic | 30 / 20 | 1 | fill time | +0.0124 | +0.0120 | fail | fail |
| 225 | 20:07:45 | A10 | 33kwaU | 0.55 | Bam | 21 / 24 | 2 | fill time | +0.0149 | +0.0145 | fail | fail |
| 226 | 20:08:42 | A10 | 4Qfvov | 0.35 | Bam | 87 / 24 | 1 | fill time | -0.0175 | -0.0045 | -0.0183 | -0.0183 |
| 227 | 20:12:19 | A10 | AerZ3P | 0.35 | Harmonic | 59 / 40 | 4 | fail | -0.0005 | -0.0005 | +0.0065 | fail |
| 228 | 20:24:37 | A10 | FaqVnx | 0.35 | Jito | 27 / 50 | 0 | fill time | +0.0343 | +0.0358 | +0.0353 | +0.0353 |
| 229 | 20:26:25 | A10 | Bx7KvW | 0.35 | HarmonicFD | 143 / 48 | 2 | fill time | +0.0044 | +0.0040 | +0.0175 | +0.0175 |
| 230 | 20:43:33 | A10 | 3PUat8 | 0.55 | Jito | 117 / 112 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 231 | 20:48:55 | A10 | DqEFHn | 0.55 | Jito | 18 / 16 | 1 | fill time | +0.0447 | +0.0452 | +0.0084 | fail |
| 232 | 20:51:20 | A10 | HW6kpL | 0.55 | Harmonic | 129 / 145 | 3 | fill time | +0.0248 | +0.0244 | +0.0240 | +0.0240 |
| 233 | 21:02:48 | A10 | GDfCeA | 0.35 | Bam | 111 / 40 | 3 | fail | -0.0005 | -0.0005 | -0.0385 | -0.0385 |
| 234 | 21:05:40 | A10 | BvWHG7 | 0.55 | Harmonic | 122 / 147 | 6 | fail | -0.0005 | -0.0005 | fail | fail |
| 235 | 21:10:14 | A10 | 6DnbHR | 0.35 | Harmonic | 196 / 160 | 5 | fill time | -0.0130 | -0.0133 | +0.0180 | +0.0180 |
| 236 | 21:14:01 | A10 | BP5nHp | 0.35 | Bam | 58 / 39 | 0 | fill stop | -0.0429 | -0.0432 | -0.0412 | -0.0412 |
| 237 | 21:14:29 | A10 | 3qcqSK | 0.35 | Rakurai | 261 / 212 | 17 | fill stop | +0.0528 | -0.0028 | +0.0503 | -0.0268 |
| 238 | 21:16:55 | A10 | BiemY3 | 0.55 | Bam | 30 / 16 | 2 | fill stop | -0.0738 | -0.0415 | -0.0603 | fail |
| 239 | 21:17:25 | A10 | HLq7FS | 0.35 | Bam | 23 / 14 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 240 | 21:18:06 | A10 | Hrd5ou | 0.55 | Bam | 101 / 32 | 6 | fail | -0.0005 | -0.0005 | +0.0684 | +0.0684 |
| 241 | 21:24:32 | A10 | FKCvXB | 0.55 | Bam | 101 / 31 | 5 | fail | -0.0005 | -0.0005 | +0.0059 | fail |
| 242 | 21:26:16 | A10 | HHxYuY | 0.55 | Harmonic | 81 / 74 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 243 | 21:28:12 | A10 | GaJ7Ra | 0.35 | Bam | 127 / 22 | 6 | fail | -0.0005 | -0.0005 | +0.0993 | +0.0993 |
| 244 | 21:38:42 | A10 | GGwiF6 | 0.55 | Bam | 85 / 40 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 245 | 21:57:31 | A10 | 37Ty3X | 0.35 | Bam | 22 / 18 | 1 | fill stop | -0.0382 | -0.0390 | -0.0394 | -0.0394 |
| 246 | 22:01:46 | A10 | 4mzRCQ | 0.55 | Jito | 44 / 49 | 3 | fail | -0.0005 | -0.0005 | +0.0480 | fail |
| 247 | 22:01:48 | A10 | 4mzRCQ | 0.55 | Bam | 30 / 35 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 248 | 22:30:39 | A10 | CrSnZn | 0.35 | Bam | 39 / 17 | 0 | fill stop | -0.0486 | -0.0427 | -0.0431 | -0.0431 |
| 249 | 22:32:33 | A10 | AzawiR | 0.35 | Bam | 25 / 18 | 3 | fill time | +0.0149 | +0.0145 | fail | fail |
| 250 | 22:34:59 | A10 | 8TSrKU | 0.35 | Bam | 23 / 13 | 1 | fail | -0.0005 | -0.0005 | fail | fail |
| 251 | 22:47:24 | A10 | A43RQh | 0.55 | Bam | 29 / 19 | 1 | fill time | +0.0240 | +0.0237 | +0.0232 | +0.0232 |
| 252 | 22:47:26 | A10 | A43RQh | 0.55 | Jito | 19 / 24 | 2 | fail | -0.0005 | -0.0005 | fail | fail |
| 253 | 22:52:18 | A10 | pgHbEP | 0.35 | Bam | 85 / 54 | 2 | fill time | +0.0035 | -0.0046 | +0.0092 | +0.0092 |
| 254 | 22:58:26 | A10 | ArWBsC | 0.35 | Bam | 16 / 13 | 1 | fill stop | -0.1121 | -0.1114 | fail | fail |
| 255 | 23:04:44 | A10 | FN6Kxw | 0.35 | Jito | 95 / 146 | 5 | fail | -0.0005 | -0.0005 | fail | fail |
| 256 | 23:05:58 | A10 | 7qLou7 | 0.35 | Bam | 84 / 42 | 5 | fail | -0.0005 | -0.0005 | -0.0217 | -0.0217 |
| 257 | 23:19:30 | A10 | FZFeDV | 0.35 | Jito | 58 / 35 | 5 | fail | -0.0005 | -0.0005 | +0.0003 | +0.0003 |
| 258 | 23:29:54 | A10 | CeHg2R | 0.55 | Bam | 83 / 44 | 4 | fail | -0.0005 | -0.0005 | +0.0749 | fail |
| 259 | 23:40:03 | A10 | G8w8pL | 0.55 | Jito | 47 / 47 | 2 | fill time | -0.0204 | -0.0199 | -0.0204 | -0.0204 |
| 260 | 23:45:48 | A10 | 8LW2Qh | 0.35 | Harmonic | 29 / 35 | 2 | fail | -0.0005 | -0.0005 | fail | fail |
| 261 | 00:01:26 | A10 | EvH1D2 | 0.55 | Bam | 26 / 22 | 3 | fail | -0.0005 | -0.0005 | fail | fail |
| 262 | 00:08:06 | A10 | 237yvo | 0.35 | Bam | 30 / 14 | 0 | fill time | -0.0138 | -0.0046 | -0.0051 | -0.0209 |
| 263 | 00:11:01 | A10 | EPEa7b | 0.55 | Bam | 164 / 46 | 4 | fail | -0.0005 | -0.0005 | +0.0902 | +0.0902 |
| 264 | 00:11:05 | A10 | EPEa7b | 0.55 | Bam | 34 / 19 | 1 | fill stop | -0.0776 | -0.1175 | -0.1179 | fail |
| 265 | 00:11:07 | A10 | CYm1Hg | 0.55 | Bam | 34 / 23 | 1 | fill stop | -0.0984 | -0.0105 | -0.0109 | fail |
| 266 | 00:38:38 | A11 | 8P8TcE | 0.55 | Harmonic | 313 / 250 | 9 | fail | -0.0005 | -0.0005 | fail | fail |
| 267 | 00:46:54 | A11 | BUQvqA | 0.35 | Bam | 49 / 30 | 2 | fill time | -0.0192 | -0.0192 | -0.0113 | -0.0211 |
| 268 | 00:50:18 | A11 | 2DSXKT | 0.35 | Jito | 127 / 115 | 2 | fail | -0.0005 | -0.0005 | -0.0141 | -0.0141 |
| 269 | 01:10:20 | A12 | 2EpmqZ | 0.55 | Harmonic | 46 / 34 | 3 | fail | -0.0015 | -0.0015 | fail | fail |
| 270 | 01:19:56 | A12 | 8yFPX6 | 0.35 | Bam | 50 / 39 | 3 | fill time | +0.0310 | +0.0310 | fail | +0.0290 |
| 271 | 01:22:54 | A12 | BuAv5r | 0.55 | Harmonic | 117 / 43 | 6 | fail | -0.0015 | -0.0015 | fail | fail |
| 272 | 01:24:08 | A12 | 2vLJvd | 0.35 | Harmonic | 6 / 36 | 2 | fail | -0.0015 | -0.0015 | fail | fail |
| 273 | 01:24:30 | A12 | C45TDX | 0.35 | Bam | 89 / 35 | 4 | fail | -0.0015 | -0.0015 | -0.0234 | -0.0222 |
| 274 | 01:25:20 | A12 | APueiv | 0.35 | Bam | 130 / 56 | 22 | fail | -0.0015 | -0.0015 | fail | fail |
| 275 | 01:35:01 | A12 | GhksrL | 0.35 | Bam | 45 / 24 | 3 | fail | -0.0015 | -0.0015 | -0.0511 | fail |
| 276 | 01:45:32 | A13 | 3zw6oJ | 0.35 | Bam | 40 / 24 | 4 | fail | -0.0015 | -0.0015 | +0.0054 | fail |
| 277 | 01:58:32 | A13 | 7VseVe | 0.35 | Jito | 252 / 141 | 7 | fail | -0.0015 | -0.0015 | +0.1123 | +0.1123 |
| 278 | 02:16:32 | A13 | D9B1MJ | 0.55 | Jito | 18 / 37 | 3 | fail | -0.0015 | -0.0015 | fail | fail |
| 279 | 02:30:34 | A13 | 2L3z93 | 0.35 | Bam | 58 / 32 | 1 | fail | -0.0015 | -0.0015 | fail | fail |
| 280 | 02:32:06 | A13 | 9ERTTs | 0.35 | Harmonic | 19 / 33 | 1 | fill time | +0.0004 | +0.0004 | -0.0030 | -0.0057 |
| 281 | 02:32:18 | A13 | D13fKW | 0.35 | Bam | 21 / 22 | 0 | fill time | -0.0258 | -0.0258 | -0.0339 | -0.0339 |
| 282 | 02:32:23 | A13 | EsF6HT | 0.35 | Jito | 124 / 46 | 0 | fill time | +0.0126 | +0.0126 | +0.0116 | +0.0116 |
| 283 | 02:33:53 | A13 | 8t2i4S | 0.35 | Harmonic | 149 / 137 | 2 | fail | -0.0015 | -0.0015 | -0.0133 | -0.0133 |
| 284 | 02:35:20 | A13 | CAp2hi | 0.35 | Bam | 79 / 42 | 2 | fill time | +0.0328 | +0.0328 | +0.0439 | +0.0315 |
| 285 | 02:39:11 | A13 | GJuS1Y | 0.35 | Bam | 48 / 29 | 0 | fill time | -0.0032 | -0.0032 | -0.0051 | -0.0324 |
| 286 | 02:47:05 | A13 | 8mEoNt | 0.55 | Jito | 124 / 124 | 3 | fail | -0.0015 | -0.0015 | fail | fail |
| 287 | 03:13:42 | A13 | GAb255 | 0.35 | Jito | 101 / 124 | 1 | fail | -0.0015 | -0.0015 | fail | fail |
| 288 | 03:20:06 | A13 | CL6z8N | 0.55 | Harmonic | 29 / 35 | 1 | fail | -0.0015 | -0.0015 | fail | fail |
| 289 | 03:20:10 | A13 | 8z1BJr | 0.55 | Harmonic | 72 / 140 | 1 | fill time | +0.0245 | +0.0245 | +0.0225 | +0.0225 |
| 290 | 03:36:53 | A13 | 2xtw6U | 0.35 | Bam | 23 / 128 | 0 | fill stop | -0.0415 | -0.0408 | -0.0742 | -0.0700 |
| 291 | 03:46:11 | A13 | 6oDUwk | 0.55 | Harmonic | 51 / 69 | 1 | fill time | -0.0097 | -0.0097 | +0.0087 | -0.0076 |
| 292 | 03:48:29 | A13 | 3qm28y | 0.35 | Harmonic | 19 / 36 | 1 | fill time | +0.0214 | +0.0214 | +0.0041 | fail |
| 293 | 03:52:41 | A13 | 9TsqZX | 0.55 | Bam | 19 / 20 | 2 | fail | -0.0015 | -0.0015 | fail | fail |
| 294 | 04:10:01 | A13 | BY8wNe | 0.55 | Bam | 12 / 21 | 1 | fill stop | -0.1141 | -0.1141 | fail | fail |
| 295 | 04:11:18 | A13 | 2d2epN | 0.55 | Bam | 120 / 45 | 6 | fail | -0.0015 | -0.0015 | +0.1115 | +0.0744 |
| 296 | 04:11:28 | A13 | 21Hfvr | 0.55 | Bam | 0 / 24 | 2 | fail | -0.0015 | -0.0015 | fail | fail |
| 297 | 04:13:40 | A13 | 3F1AVD | 0.55 | Jito | 111 / 118 | 2 | fail | -0.0015 | -0.0015 | +0.1711 | fail |
| 298 | 04:13:49 | A13 | DJasC1 | 0.35 | Bam | 29 / 20 | 0 | fill stop | -0.0523 | -0.0663 | -0.0596 | -0.0596 |
| 299 | 04:34:15 | A13 | GiybNi | 0.35 | Jito | 171 / 139 | 1 | fill time | -0.0236 | -0.0184 | -0.0191 | -0.0191 |
| 300 | 05:07:17 | A13 | 8WAAk1 | 0.35 | Bam | 77 / 38 | 1 | fill time | +0.0305 | +0.0305 | +0.0133 | +0.0133 |
| 301 | 05:09:52 | A13 | 9XLLD5 | 0.55 | Harmonic | 90 / 105 | 7 | fill time | +0.1364 | +0.1510 | +0.0921 | +0.0921 |
| 302 | 05:15:34 | A13 | 8EBkFi | 0.55 | Jito | 70 / 71 | 5 | fail | -0.0015 | -0.0015 | +0.0357 | fail |
| 303 | 05:32:34 | A13 | DHzCgi | 0.35 | Harmonic | 23 / 72 | 2 | fill time | +0.0176 | +0.0176 | -0.0058 | -0.0126 |
| 304 | 05:35:17 | A13 | 3xu825 | 0.35 | Rakurai | 77 / 64 | 5 | fail | -0.0015 | -0.0015 | +0.0453 | +0.0453 |
| 305 | 05:42:07 | A13 | 6feP82 | 0.35 | Bam | 13 / 43 | 0 | fill time | -0.0049 | -0.0049 | -0.0172 | -0.0172 |
| 306 | 05:44:16 | A13 | FrbS2P | 0.35 | Jito | 56 / 53 | 1 | fill time | +0.0059 | +0.0059 | +0.0182 | +0.0182 |
| 307 | 06:17:36 | A14 | 3uxMAY | 0.55 | Jito | 113 / 131 | 4 | fail | -0.0005 | -0.0005 | fail | fail |
| 308 | 06:33:09 | A14 | 2XqFe8 | 0.35 | Jito | 155 / 64 | 3 | fail | -0.0005 | -0.0005 | +0.0079 | +0.0079 |
| 309 | 06:44:32 | A14 | HDoame | 0.35 | Jito | 18 / 39 | 0 | fill time | -0.0550 | -0.0550 | -0.0570 | -0.0570 |

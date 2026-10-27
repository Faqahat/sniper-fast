# Exit that "holds the winners" — learned exit study (10-25, PKT)

Read-only, local recording only, no servers, no transactions.
Data: raw recording 10-24 09:45 → 10-25 09:45 PKT (24 h). TRAIN = first 15.25 h (to 10-25 01:00). TEST = last 8.75 h.
**MEASURED** = computed from the data or the corrected replay. **INFERRED** = my reading.

## Verdict
- **Holding the winners does NOT beat today's exit out of sample.** MEASURED.
  - The learned model's "hold longer" decisions earn +1.6 SOL/day on M2 in TRAIN.
  - Out of sample they earn: M2 +0.4 (CI −0.1 to +1.0), IMIT1 −0.03, our 62 real test-hour fills −0.001 SOL, and 0 in a second, time-reversed fold.
  - The best "hold while buying continues" rule chosen on TRAIN (positive in all 6 TRAIN cells): TEST M2 +0.6, IMIT1 −0.4, real fills −0.04 SOL.
  - INFERRED: the model learned a few rare big winners. At our landing they cannot be told apart from the feed: the model explains only 0.5–2% of the "hold or sell" variance.
- **A learned exit can beat today's a little, but by selling EARLIER, not by holding.** MEASURED.
  - Learned exit (3 GBDTs, fixed threshold), TEST: M2 **+1.6 SOL/day** (90% CI +0.7 to +2.8), IMIT1 +0.2 (CI −0.6 to +1.1), real fills +0.16 SOL (CI −0.07 to +0.39).
  - Its sell-earlier half alone: M2 +1.2 (CI +0.2 to +2.3). Its hold-longer half alone: +0.4.
  - Second fold (fit on the later 15 h, test 10-24 09:45–18:30): M2 −0.05, IMIT1 +0.18. No gain in the daytime.
- **The threshold is fragile.** Following the plan (threshold picked on the 21:00–01:00 validation window), 3 of 5 learned runs chose to hold far longer (threshold −4 to −6 mSOL). On TEST they lost 1.2–2.3 SOL/day (M2) and 2.8–4.3 (IMIT1) vs today. That window was the one evening where holding paid.
- **On which dumps:** holding pays only on crowded dumps (3+ fast bots buy in the dump's slot to +3): +4 to +14 mSOL per fill (M2 replay, real fills). It loses about as much on quiet and medium dumps; on IMIT1's crowded dumps it does not pay at all.
- **Longer holds lose out of sample on IMIT1 and on our real fills:** haqq-like checkpoints, HkQ7-like timer, 8-slot cap, trailing stop, 2-slot stall.
- **Runs 10–14's exit (hold 6, SL −10%) was worse than today's:** IMIT1 −0.5 SOL/day (CI −0.9 to −0.2), real fills −0.23 SOL. Keeping hold 5 was right.

## What to do (INFERRED; engine changes need your OK)
1. **Keep today's exit (hold 5, no TP/SL).** Do not switch to a "hold the winners" exit.
2. **Optional tiny add-on:** if the token had no outside buy in the 2 slots after our buy's slot, sell one slot early (slot +3 instead of +4).
   - Small but positive in every period total: TRAIN M2 +0.07 / IMIT1 +0.10; TEST M2 +0.15 / IMIT1 +0.13 (CI +0.04 to +0.24); real fills +0.02 / +0.06 SOL.
   - The strict TRAIN criterion (no TRAIN cell worse than today) prefers "no change": one cell was −0.06 SOL/day.
3. **The learned exit: shadow only, if at all.** Log its decision each slot while trading as today. Its gain is one night and mostly "sell earlier".
4. **Holding winners needs a faster landing, not a smarter exit.** On crowded TEST dumps the look-ahead best exit makes +77–83 mSOL per fill; today's makes +22–25.
5. **One idea to test with more days:** holding paid in the 21:00–01:00 PKT window (M2: 30-slot cap +11.9 vs +9.9 SOL/day). One evening only; not testable on this data.

## SOL per day, both servers' near leaders (MEASURED replay)
TEST = 10-25 01:00–09:45 PKT. "meas" = our measured landing per leader client. "Learned" = 3-GBDT ensemble, threshold +0.5 mSOL.

**M2 picks**

| Exit | TRAIN meas | TEST meas | TEST 35 / 50 / 75 ms | TEST vs today [90% CI] |
|---|---|---|---|---|
| Today (hold 5 = c4) | +4.71 | +3.46 | +6.56 / +3.48 / +1.86 | – |
| Runs 10–14 (hold 6, SL −10%) | +4.63 | +3.77 | +6.65 / +3.86 / +2.21 | +0.30 [−0.56, +1.24] |
| Stall 2 slots (hold while buying) | +6.36 | +4.92 | +8.54 / +5.97 / +3.75 | +1.46 [−0.19, +3.26] |
| Best hold rule chosen on TRAIN | +5.64 | +4.03 | +7.36 / +3.87 / +2.25 | +0.57 [−0.80, +2.16] |
| **Learned** | +6.39 | **+5.10** | +8.61 / +4.72 / +2.70 | **+1.64 [+0.65, +2.76]** |
| Learned, hold-longer half only | +6.33 | +3.88 | +6.98 / +3.80 / +2.28 | +0.41 [−0.10, +0.97] |
| Learned, sell-earlier half only | +4.77 | +4.69 | +8.19 / +4.40 / +2.27 | +1.22 [+0.23, +2.25] |
| Add-on #2 (dead-tape cut) | +4.78 | +3.62 | +6.78 / +3.57 / +1.94 | +0.15 [−0.17, +0.44] |
| Look-ahead best (upper bound) | +15.69 | +22.16 | +31.35 / +24.61 / +17.65 | +18.7 |

**IMIT1 picks**

| Exit | TRAIN meas | TEST meas | TEST 35 / 50 / 75 ms | TEST vs today [90% CI] |
|---|---|---|---|---|
| Today (hold 5 = c4) | +1.83 | +2.05 | +3.62 / +2.45 / +1.61 | – |
| Runs 10–14 (hold 6, SL −10%) | +1.38 | +1.51 | +2.81 / +1.72 / +1.02 | **−0.54 [−0.92, −0.20]** |
| Stall 2 slots | +2.53 | +0.64 | +2.66 / +1.44 / +0.54 | **−1.41 [−2.80, −0.09]** |
| Best hold rule chosen on TRAIN | +2.46 | +1.67 | +3.22 / +1.89 / +1.19 | −0.37 [−0.88, +0.07] |
| **Learned** | +3.10 | **+2.27** | +4.24 / +2.34 / +1.82 | +0.22 [−0.56, +1.09] |
| Learned, hold-longer half only | +2.53 | +2.02 | +3.75 / +2.44 / +1.66 | −0.03 [−0.42, +0.31] |
| Learned, sell-earlier half only | +2.42 | +2.30 | +4.11 / +2.35 / +1.76 | +0.25 [−0.42, +0.98] |
| Add-on #2 (dead-tape cut) | +1.93 | +2.18 | +3.83 / +2.53 / +1.68 | **+0.13 [+0.04, +0.24]** |

- The learned exit's TRAIN numbers are in-sample.
- Sell-landing rows (sell lands 35 / 50 / 75 ms after the decision instead of our measured spread) move each TEST number by ≤ 0.5 SOL/day. The learned exit stays above today's in every row.
- Drawing our landing per crowd level (closer to live on crowded dumps) changes the learned exit's TEST difference by < 0.05 and every other by ≤ 0.25.
- **Absolute SOL/day here is optimistic.** The landing draw is independent of the dump: it fills 40% of crowded dumps; live we fill 30%. Our real fills with today's exit made ≈0 in the TEST hours (+0.015 SOL on 62 fills). Read the differences, not the levels.
- Stress "+crowd" (later non-bot buyers buy 40% less after us, INFERRED): learned exit still +1.6 (M2) / +0.25 (IMIT1).

## The threshold (MEASURED, TEST, learned minus today, SOL/day)
The model predicts the SOL gain of holding. "Threshold" = the minimum predicted gain needed to hold.

| Threshold (mSOL) | −2 | −1 | −0.5 | 0 | +0.5 (used) | +1 | +2 |
|---|---|---|---|---|---|---|---|
| M2 | +0.53 | +0.55 | +0.77 | +1.71 | +1.74 | +1.50 | +1.72 |
| IMIT1 | −0.99 | −0.43 | −0.14 | +0.07 | +0.27 | +0.44 | +0.51 |
| Real fills, TEST hours (SOL) | −0.39 | −0.15 | +0.07 | +0.12 | +0.16 | +0.13 | +0.14 |
| Mean sell slot | 9.7 | 6.7 | 5.5 | 4.5 | 3.8 | 3.1 | 2.3 |

- 16 landing draws here, so ±0.1 vs the main table.
- Holding more than the model's own estimate (threshold < 0) loses on IMIT1 and on the real fills.
- The +0.5 mSOL threshold came from the first runs' validation. After a bug fix (below) the same validation picked −4 or −6 in 3 of 5 runs.
- Those 3 runs (M2 / IMIT1 vs today on TEST): −1.20 / −3.42, −1.28 / −2.76, −2.26 / −4.26 SOL/day. The other 2: +1.63 / +0.18 and +2.01 / +0.16.

## Our real live fills (MEASURED: exact chain landing, no landing model)
128 fills from FRA r10–r15 and AMS r9–r14, replayed at 0.35 SOL with each exit. The replay reproduces live within noise (RECON).

| Exit | TRAIN hours (66 fills) vs today | TEST hours (62 fills) vs today |
|---|---|---|
| Runs 10–14 (hold 6, SL −10%) | −0.11 [−0.29, +0.09] | **−0.23 [−0.42, −0.04]** |
| Fixed 8 slots | **−0.40 [−0.68, −0.12]** | **−0.61 [−1.01, −0.23]** |
| Stall 2 slots | +0.35 [−0.28, +1.15] | **−0.69 [−1.09, −0.31]** |
| haqq-like checkpoints | −0.09 [−0.90, +0.81] | **−1.14 [−1.77, −0.50]** |
| Best hold rule chosen on TRAIN | +0.39 [−0.26, +1.17] | −0.04 [−0.32, +0.19] |
| **Learned** | +0.10 [−0.25, +0.44] | +0.16 [−0.07, +0.39] |
| Learned, hold-longer half | +0.07 [−0.07, +0.24] | −0.001 [−0.002, 0.000] |
| Add-on #2 (dead-tape cut) | +0.02 [−0.09, +0.12] | +0.06 [−0.00, +0.11] |

- Stall 2 slots on the real fills, per fill vs today: crowded +4.2 mSOL, medium −7.2, quiet −7.7.

## Which dumps (MEASURED, TEST, mSOL per fill)
Crowd = distinct fast dip bots (75-bot list) buying in the dump's slot to +3 (real tape; only used to split results).

| Exit | M2 quiet 0–1 | M2 2 | M2 crowded 3+ | IMIT1 quiet | IMIT1 2 | IMIT1 crowded |
|---|---|---|---|---|---|---|
| Today | −12.5 | +10.6 | +22.1 | −22.3 | +21.4 | +24.7 |
| Stall 2 slots | −13.3 | +8.8 | **+36.4** | −27.4 | +15.1 | +20.7 |
| Learned | **−9.2** | **+15.5** | +26.8 | −18.9 | +22.7 | +25.1 |
| Look-ahead best | +19.5 | +50.8 | +83.4 | −10.8 | +46.0 | +77.1 |

- Fills: M2 513 / 465 / 768, IMIT1 262 / 171 / 423 (10 landing draws per dump).
- Holding from slot 4 to slot 8 on picks: −2.0 mSOL per fill in TRAIN, −3.1 in TEST. Always negative when ≤ 2 fast bots bought by slot 4; with 3+ the sign flips between periods.

## Hour bands and by server (MEASURED)
SOL per band (not per day), TEST bands, today → learned:

| PKT band | 01–03 | 03–05 | 05–07 | 07–09:45 |
|---|---|---|---|---|
| M2 | +0.86 → +0.88 | +0.13 → +0.42 | +0.49 → +0.66 | −0.23 → −0.09 |
| IMIT1 | +0.50 → +0.41 | −0.01 → +0.12 | +0.22 → +0.25 | +0.04 → +0.04 |

- By server, M2 TEST: FRA +3.28 → +4.58; AMS +0.18 → +0.52 (AMS no-BAM list +0.85 → +1.13).
- By server, IMIT1 TEST: FRA +1.83 → +2.07; AMS +0.21 → +0.20.
- Second fold (fit 10-24 18:30 → 10-25 09:45, test 10-24 09:45 → 18:30): learned −0.05 (M2), +0.18 (IMIT1); hold-longer half −0.04 / 0.00.

## The exact rules
**Decision timing (both):** at the first feed trade of each slot after our buy, the same hook as today's time-limit check. The sell lands like today's time-limit sells: median 94 ms into the slot (MEASURED, 107 live sells).

**Add-on #2, dead-tape cut:**
- At slot s_in + 3: SELL if no outside buy on the token landed in slots s_in + 1 and s_in + 2.
- Otherwise sell at slot s_in + 4 (today, hold 5).
- Uses only our own trade feed for the token. Same decisions as the study rule on 99.95% of paths (the rest: our buy at index 0 of its slot).

**Learned exit (shadow only):** bundle `/home/moiz/sniper-data/exits/exit_learned_ens3.json`.
- Contents: 53 features with definitions, 3 × ~275 depth-3 trees, bin edges as exact floats.
- At each slot k = 1–19 after our buy: score = mean of the 3 models = predicted SOL gain from holding. SELL if ≤ 0.0005 SOL. Forced sell at slot 20.
- Features, all from our own feed (no RPC):
  - position: return now, peak, drawdown, change over 1 / 2 / 4 slots;
  - flow: outside buy and sell SOL and counts in the last 1 / 2 / 4 slots and since entry; distinct buyers;
  - bots: fast-bot (75 list) and cohort buys and sells, distinct fast bots since the dump, bots still holding;
  - stall: time since the last outside buy (ms and slots), and since the last buy ≥ 0.1 SOL;
  - other: largest buy and sell in the last 2 slots, sells ≥ 1 SOL, creator sells, curve SOL, token age;
  - entry: M2 score, dump size and drop, entry price ratio, trades ahead, landing ms, leader client of the dump slot and of the current slot.
- What it does (depth-3 tree fit to its label, MEASURED):
  - hold while an outside buy landed in the last ~190 ms;
  - if the tape is quiet: hold for the bounce after a ≥ 0.7 SOL sell in the last 2 slots (unless up ≥ 18%), otherwise sell.
  - It sells before today's timer on ~73% of fills and later on ~19%.
  - The held fills earned +31 to +36 mSOL each in TRAIN and +0.5 to +5.5 in TEST (M2 / IMIT1, per fill, no engine).
- Re-scoring from the JSON reproduces the study's predictions exactly.

## How it was done (short)
- **Tapes:** the study pipeline, unchanged (dd20 stages → day arrays → dd1 rows).
  - Two recordings: run_20261023_1426 for tokens created before 19:25 PKT, run_20261024_1425 after.
  - 227,570 dumps; 37,318 in the envelope.
  - M2 picks 1,476 (all leaders; 800 on near leaders). IMIT1 top4 picks 760; IMIT1 scores exist for 79% of envelope dumps.
  - Both pick models were fit before this window (M2 on 10-22/23, IMIT1 before 10-23 06:00).
- **Replay:** the model check's corrected model, re-implemented to keep every trade after our buy.
  - Matches `modelcheck/mc_corr.replay_corr` exactly: 0 mismatches on 1,491 fills, with and without "+crowd".
  - Our own wallets' trades removed. 0.35 SOL, +5% guard.
  - Entry at the 10 deciles of our measured landing for the slot leader's client (309 live buys), plus 35 / 50 / 75 ms.
  - Sell: time-limit sells at the measured offsets (median 94 ms); trigger sells (TP/SL/trail) at the measured stop-loss delay (median ~48 ms).
- **Learning:** numpy GBDT, depth 3.
  - Label: average SOL gain from holding 1, 2, 4 or 8 more slots versus selling now.
  - Trained on 7,818 envelope dumps (M2 ≥ −0.005 plus all picks) in TRAIN, 13 landing points each, slots 1–20.
  - 3 seeds averaged. A first policy-iteration model collapsed to "hold everything" on its own validation and was dropped.
- **Engine replay:** one position per server, busy until the sell lands + 0.3 s, 0.2 s after a failed buy, 5 slots between picks on a token.
  - Costs: 0.0045 SOL per round trip, 0.000505 per failed buy.
  - 24 landing draws per dump, the same draws for every exit.
  - CIs: paired bootstrap over 30-minute blocks.
- **Bug fixed during the study:** when our own live trade sat right before the landing cut, the entry slot came from that removed trade.
  - It hit 0.3% of paths (24 near-pick dumps). Everything above was rebuilt after the fix.
  - The recon's `rsim.run_path` has the same pattern for its fixed-ms rows (its exact-landing replays are not affected). Not changed (not my file).

## Caveats
- **24 hours only.** TEST is one night and morning; the reversed fold is one day. The exit effect changes with the hour; expect ±1 SOL/day swings.
- **The landing draw ignores that we are late exactly on the contested dumps** (40% vs 30% crowded fill rate). The real-fill check removes this but has only 62 TEST fills.
- **Bot dependence:** every exit's profit, holding most of all, depends on the ~75 fast bots buying after us.
- **Decisions once per slot:** trade-by-trade triggers were only tried as TP / SL / trailing stops (all ≈ or worse than today).

## Files
- **Code:** `/home/moiz/sniper/ops/dip/exits/` (`run_all.sh` rebuilds models and tables).
  - e00 build + selftest, e01 dumps, e02 paths, e03 baselines, e04 / e04b / e04c learned models, e05 report;
  - e06 / e07 live fills, e08 crowd-hold rules, e09 trees, e10 hold-rule choice, e11 thresholds;
  - e12 +crowd, e13 halves, e14 cut choice, e15 reversed fold, e16 final tables, e17 export;
  - libraries: `exit_lib.py`, `e_eval.py`, `e_apply.py`, `e_gbdt.py`, `gbdt_np.py`, `e04b_learn_labels.py`.
- **Data:** `/home/moiz/sniper-data/exits/`
  - tapes A/ and B/, dumps.npz; paths/ (paths2.npz, paths2_crowd.npz, paths_live.npz);
  - models: e04b_*_model.pkl, e04b_ENS3_model.pkl, exit_learned_ens3.json;
  - printouts: e16_final.txt (the tables above), e05_report.txt, e07_live.txt, e11_theta.txt, e13_split.txt, e15_reverse.txt, e03_baselines.txt, e08_rules.txt, e09_h1248.txt, e10_select.txt, e12_crowd.txt, e14_cut.txt.

# VM1 independent verification (10-25, started ~17:10 PKT)

Status: done 10-25 ~17:35 PKT. Section 0, the pre-registration, is unchanged from before any result was computed.
The summary was added above it after the results.
MEASURED = replay or chain data. INFERRED = my reading.

## Summary (added after the results)
- **Verdict: VM1 DOES NOT HOLD UP** under the pre-registered rules, so **no shadow was built**.
- **The claim reproduces only under its own rules and window** (MEASURED).
  - The copy's own code gives exactly its 184 picks and +0.0141/trade.
  - On the same window, my own code picks the same dumps wherever both token sets contain them (164 of 165).
  - 20 of its 184 picks (11%) are Mayhem-mode or non-standard tokens, and they carry 23% of its profit. The engine does
    not trade Mayhem tokens.
  - Over all 68.7 unseen hours, with the copy's own rules: 19.8 picks/h, +9.0 mSOL/trade, **+4.3 SOL/day**, not +11.7.
- **At our real landing and costs, VM1 is about zero** (MEASURED replay, all unseen hours).
  - Setup: landing = our live delay distribution (median 53 ms, 23% next block), 4.5 mSOL per trip, 20% follower cut,
    FRA near leaders, 1 position.
  - Result: **+0.16 SOL/day** (+1.2 mSOL/trade, 5.5 trades/h). The halves are −0.01 / +0.48 SOL.
  - With the live-calibration correction: **−0.53 SOL/day**.
- **Live calibration is the deciding evidence** (MEASURED on our real fires).
  - Any "landing distribution" replay over-predicts our real fires by **+5.3 mSOL per fire** (90%: +2.7 to +7.8).
  - The copy's paper rule on our 496 real fires predicts +4.96 SOL. Reality was **+0.11 SOL**.
  - VM1 picked only 12 of those 496 dumps, too few to judge.
- **M2 beats VM1 on the same unseen hours** with the same simulator: U3+U4 M2 +1.43 SOL vs VM1 +0.39 (IMIT1 +0.78).
  M2 is ahead in both blocks.
- **VM1 does pick better than chance:** +1.2 mSOL/trade vs −12.1 for random picks and for all dumps. But that edge is
  smaller than the landing and fee drag at our speed.

## Pass / fail (rules of section 0)
| Rule | Result (MEASURED) | |
|---|---|---|
| A1 all unseen, main row | +0.47 SOL raw; **−1.53 after the (C) correction** | FAIL |
| A2 forward block U4 | +0.19 raw; −0.13 corrected | FAIL |
| A3 both halves | **−0.01** / +0.48 raw; −1.01 / −0.52 corrected | FAIL |
| A4 vs 200 random sets | +1.24 vs random median −12.05 (95th pct −10.31); beats 100%; all dumps −12.10 | pass |
| B vs M2 on U3+U4 | VM1 +0.39 vs M2 +1.43; U3 +0.29 vs +0.86; U4 +0.10 vs +0.57 | FAIL |
| C live calibration | sim optimistic **+5.27 mSOL/fire** (90%: +2.68 to +7.77) → correction applies | — |

- The correction is not what decides it.
  - With the size-matched bias (0.35 SOL fires: +2.89), the main row is −1.65 mSOL/trade.
  - With M2-like picks' bias (+1.92), it is −0.68.
  - With no correction at all, it is +0.16 SOL/day and the first half is negative.

## 0. Pre-registration (written 10-25 ~17:15 PKT, before looking at any result of my own)

### What is tested
- The ONLY artifact taken from the copy is the frozen model: `sniper-landfix/ops/landfix/vm1.json`
  (sha256 55197e30…, same trees/edges/F0/cut as `ops/dip/speed/night/vm_frozen.pkl`, checked structurally).
- Everything else of the copy (hq2.py, race_extract.py, vm_paper.py, its rows/labels, its replay, its reports) is a
  CLAIM UNDER TEST. I do not use it as a tool. My code: `ops/dip/vm1/` (own decoder, curve math, features, simulator).
- After my own numbers exist, hq2.vm_feats is compared with my features as a cross-check only.

### Data and windows (all times PKT)
- Raw recordings run_20261021_2207, run_20261022_1543, run_20261023_1426, run_20261024_1425. Only successful txs.
- VM1 training windows (from the copy's extraction logs; I re-derive their PKT times from block times):
  T1 = slots 460,476,411–460,595,437 (10-23 ~19:26 → 10-24 ~02:26), T2 = slots 460,883,322–461,001,668
  (10-24 ~19:25 → 10-25 ~02:24). The cut was set on T1+T2.
- Unseen = every recorded slot outside T1/T2 minus a 10-minute guard band on each side, minus recording holes.
  - U1 = run_20261021_2207 (10-22). U2 = run_20261022_1543 (10-22/23). U3 = between T1 and T2 (10-24 day).
  - U4 = after T2 (10-25, the forward block; the only block after the freeze).
  - IMIT1 trained before 10-23 06:00 and M2 trained on 10-22 20:43–10-23 18:19, so the head-to-head uses U3+U4 only.
- Every unseen hour is scored. No hour is dropped after the fact.
  - A dump is dropped only for a mechanical reason, counted in the tables:
    - a recording hole inside its 60 s feature window or its trade window;
    - its token history starts at the recording start (no creation seen, so age/ntr/dev_like are unknown).

### Envelope (VM1's stated one)
- A sell of at least 1 SOL on a normal SOL-quoted pump.fun bonding curve.
  - Normal = vsol × vtok = 30 SOL × 1.073e15 within 0.5%.
- Post-dump virtual SOL between 25 and 200 SOL.

### Simulator (my own; parameters fixed now)
- **Size:** 0.3 SOL (VM1's size).
- **Entry landing rows:**
  - **L-live:** the block-clock delay from the dump to our buy's chain position, measured on every live fire whose buy
    landed on chain (filled or reverted) in the current era (FRA r10–r16, AMS r10–r17).
    - Each candidate dump is evaluated at every measured delay, and the results are averaged (expected value).
    - Block clock = slot + index / block size. Block size = the highest tx index the recorder saw in that slot, + 1.
    - So next-slot spills happen when the dump's position plus the delay crosses its block end.
  - **F40 / F80 / F150:** fixed +40/+80/+150 block txs after the dump, spill-aware (txs past the block end go into the
    next slot).
  - **CLAIM row (reproduction only):** the copy's own rule. +80 txs, never leaving the dump's slot.
- **Guard:** the buy reverts if the price just before our position is more than 1.05× the post-dump price.
- **Buy:** constant product on the reserves just before our position, after the pump fee of that token
  (fee_bps + creator fee_bps from its events, about 1.25%).
- **Exit:**
  - Primary: our sell lands at the live-measured sell position (slots after our buy's slot plus block position, from
    live fills of hold-5/6 runs), averaged over that distribution.
  - Sensitivity row: the copy's rule (end of the dump's slot + 6).
  - Sale = (V + x) · q / T on the reserves just before the sell (our buy's impact kept), minus the pump fee.
- **Tx costs per filled round trip:** 4.5 mSOL (live), plus 2.0 and 0.6 rows. A reverted buy costs the live-measured
  mean revert cost in the 4.5 row, scaled by cost/4.5 in the other rows.
- **Follower cut:** the trade's P&L after pump fees and before tx costs, if positive, × (1 − c), c = 20% and 35%.
- **Positions:** 1 open (today's engine) and 3 open.
  - A position is busy from the dump's slot until its sell lands, or until the revert.
  - Picks arriving while full, or on a token already held, are skipped.
- **Leaders:**
  - all leaders;
  - FRA near list (the 198-leader file FRA uses);
  - AMS near list (the 54-leader nobam file). Leader of the dump's slot, from getLeaderSchedule.
- **SOL/day** = total over the scored hours ÷ scored hours × 24.

### Pass / fail rules
The MAIN ROW is L-live entry, 4.5 mSOL per trip with the live revert cost, 20% follower cut, 1 open position and
FRA near leaders.

- **(A) Absolute.** All four must pass:
  - **A1:** the main-row total over all unseen hours (U1–U4) is > 0.
  - **A2:** the forward block U4 alone is > 0 on the main row.
  - **A3:** both chronological halves of the pooled unseen picks are > 0 on the main row (split at the median pick time).
  - **A4 (null check):** VM1's per-trade value beats at least 95% of 200 random pick sets.
    - Each set has the same number of picks per hour, from the same envelope, leaders and hours, through the same
      simulator.
    - VM1 must also beat the all-dumps baseline.
- **(B) Relative.** On U3+U4, with the same simulator and the main row:
  - VM1 SOL/day > M2 (gate cut as live, 0.010095) SOL/day;
  - and VM1 ≥ M2 in each of U3 and U4.
  - IMIT1 is shown too.
- **(C) Live calibration (deciding).**
  - On our live fills (FRA r10–r16, AMS r10–r17), compare my simulator with REALIZED P&L.
    - The simulator runs at each fill's ACTUAL chain buy position and ACTUAL sell position, with its real size and real
      tx costs.
  - If the simulator is optimistic by more than 2 mSOL per fill (and the 90% interval excludes 0), every replay number
    is reduced by that bias before (A) and (B) are judged.
  - VM1-picked vs not-picked live fills (realized): reported. It is not decisive below 20 picked fills.
- **Verdict:**
  - **HOLDS UP** = (A) or (B) passes after (C).
  - **BORDERLINE** = A1 > 0 on the main row but A2, A3 or A4 fails, or A1 > 0 only at the 2.0 mSOL row.
  - **DOES NOT HOLD UP** = otherwise.
  - Phase 2 (the shadow build) only for HOLDS UP or BORDERLINE.

### Leakage / bias hunt (checked explicitly, results in section 5)
1. Features or labels using any trade at or after the dump's own position.
2. The dump itself counted in flow/buyers/ch15. 'curve' = post-dump.
3. The cut chosen on test data.
4. Train/test overlap: trained_until_slot is checked against the slot of every scored dump.
5. Survivorship: reverted or unfillable picks dropped.
6. Overlapping positions double-counted.
7. Follower-cut definition games.
8. Hours selected after the fact.
9. Recording holes and history truncation.

## 1. Data, windows, hours (MEASURED)
- My decoder read 1,014 raw files and found 12.9 M TradeEvents from successful txs.
  - Reserve chaining is consistent on 99.8% of consecutive trades.
  - 6 older files ended early, but the next file overlaps them, so no data is lost.
  - 2 recording holes exist, between recordings. Dumps near holes are dropped (1,149).
- Token set: normal SOL curves only (k = 30 SOL × 1.073e15).
  - Mayhem-mode tokens are dropped: any trade by the Mayhem agent BwWK17…, a fee-free trade, or vsol < 29.9 SOL.
  - The token's creation must be in the recording; dumps without it are dropped (3,591).
- Envelope dumps (≥ 1 SOL sell, vsol 25–200): 361,449 in total.

| Block | PKT | Hours | Dumps | VM1 picks (all leaders) |
|---|---|---|---|---|
| U1 unseen | 10-22 03:08 → 18:59 | 15.8 | 62,063 | 320 (20.2/h) |
| U2 unseen | 10-22 20:43 → 10-23 18:31 | 21.8 | 101,211 | 536 (24.6/h) |
| T1 train | 10-23 19:26 → 10-24 02:26 | 7.0 | 44,539 | 336 (48/h) |
| U3 unseen | 10-24 02:36 → 19:15 | 16.6 | 64,444 | 286 (17.2/h) |
| T2 train | 10-24 19:25 → 10-25 02:23 | 7.0 | 38,137 | 328 (47/h) |
| U4 unseen (forward) | 10-25 02:33 → 16:59 | 14.4 | 42,556 | 217 (15.1/h) |

- trained_until_slot 461,001,660 = 10-25 02:23 PKT. Every U4 dump is after it, plus a 10-minute guard band.
- The same cut picks 47–48/h in-sample and only 15–25/h on unseen hours.

## 2. Live-measured inputs (MEASURED, chain)
- **Landing:** our 371 buys in FRA r10–r16 and AMS r10–r17, all of which landed on chain. Block clock = slot + index /
  block size.

  | | Median | p25 | p75 | p90 | Next block |
  |---|---|---|---|---|---|
  | All r10+ | 53.2 ms | 33.6 | 85.5 | 143.1 | 23% |
  | FRA r10–16 | 55.5 ms | | | | 22% |
  | AMS r10–17 | 44.6 ms | | | | 24% |

  - Fill rate 42%.
  - My block sizes are within 1–4% of the engine's clock2 counts.
  - The model's predicted next-block share on these fires is 24.1%, vs 22.4% real.
- **Costs:**
  - Filled round trip: mean 3.79 mSOL (median 3.51). FRA 3.51, AMS 4.38; recent FRA runs 3.1–3.3.
  - Reverted buy: mean 0.60 mSOL (median 0.505). No tip is paid on a revert.
  - Chain P&L equals the logs' REALIZED on all 154 fills (max difference 0.0000005 SOL).
- **Exit:** live sells land 4 slots after the buy slot (hold 5) or 5 slots after (hold 6), median block position 0.39.
- **Realized live P&L, r10+ (370 fires):** −0.261 SOL (154 fills −0.132, 217 reverts −0.130). All runs: +0.111 SOL
  on 498 fires.

## 3. Claim reproduction
The copy's rules, my code and data: +80 txs never leaving the dump's slot, exit at the end of the dump's slot + 6,
0.3 SOL, cut 20% on positive net, no position limit, all leaders.

| Window | Picks/h | mSOL/trade (2.0 / 0.6 mSOL) | SOL/day (2.0 / 0.6) |
|---|---|---|---|
| Copy's 5.3 h, its own code (its claim) | 34 | +14.1 / +15.1 | +11.7 / +12.5 |
| Same window, my code (after the 10-min band) | 26.9 | +11.8 / +12.7 | +7.6 / +8.2 |
| U4, all 14.4 h | 15.1 | +11.4 / +12.3 | +4.1 / +4.5 |
| U3 | 17.2 | +8.4 / +9.3 | +3.5 / +3.9 |
| U2 | 24.6 | +9.2 / +10.2 | +5.4 / +6.0 |
| U1 | 20.2 | +7.5 / +8.6 | +3.7 / +4.2 |
| **All unseen, 68.7 h** | 19.8 | **+9.0 / +10.0** | **+4.3 / +4.7** |
| Training T1+T2 (in-sample) | 47.6 | +16.1 / +17.1 | +18.4 / +19.5 |

- Buying every dump under the same rules: −9.8 mSOL/trade on unseen hours. The copy claimed −8.9 on its window, and I
  get −8.7 there.
- With FRA near leaders only, the claim rule gives +1.2 SOL/day (7.2 mSOL/trade).

## 4. Live reality
All rows: all unseen hours (68.7 h), VM1 picks, 0.3 SOL. The value in [ ] has the pre-registered −5.27 mSOL/trade
calibration correction.

**Landing × cost** (FRA near, 1 position, cut 20%), SOL/day:

| Landing | 4.5 mSOL (pre-reg) | 3.8 (measured) | 2.0 | 0.6 |
|---|---|---|---|---|
| **L-live** (our distribution) | **+0.16 [−0.53]** | +0.22 [−0.48] | +0.38 [−0.32] | +0.50 [−0.20] |
| F40 (~24 ms, faster than us) | +1.06 [+0.36] | +1.14 [+0.44] | +1.35 [+0.66] | +1.52 [+0.82] |
| F80 (~49 ms, fixed, spill-aware) | +0.40 [−0.30] | +0.46 [−0.24] | +0.63 [−0.07] | +0.77 [+0.07] |
| F150 (~91 ms) | −0.08 [−0.78] | −0.03 [−0.73] | +0.11 [−0.59] | +0.22 [−0.48] |

- Per trade at 4.5 mSOL: L-live +1.24, F40 +8.01, F80 +2.98, F150 −0.60 mSOL.
- Fill: L-live 59%, F40 86%, F80 67%, F150 51%.
- 1 tx is about 0.61 ms (median block 349 txs per 212 ms).

**Leaders × positions × follower cut** (L-live, 4.5 mSOL), SOL/day:

| Leaders | Open | Cut 20% | Cut 35% | Trades/h |
|---|---|---|---|---|
| all | 1 | +1.04 [−0.83] | +0.46 [−0.66] | 14.7 |
| all | 3 | +1.04 [−0.86] | +0.45 [−0.68] | 15.0 |
| FRA near | 1 | +0.16 [−0.53] | −0.02 [−0.44] | 5.5 |
| FRA near | 3 | +0.16 [−0.55] | −0.03 [−0.45] | 5.6 |
| AMS near | 1 | +0.14 [−0.10] | +0.06 [−0.09] | 1.9 |
| AMS near | 3 | +0.14 [−0.10] | +0.06 [−0.09] | 2.0 |

- A 3rd open position adds nothing: picks rarely overlap.
- With no follower cut, the main row is +0.42/day.
- The best case at our landing (all leaders, 3 open, 0.6 mSOL, no follower cut) is +2.77/day raw.

**Main row per block** (L-live, 4.5, FRA, 1 position, cut 20%):

| Block | SOL total | SOL/day | mSOL/trade |
|---|---|---|---|
| U1 | +0.080 | +0.12 | +0.83 |
| U2 | −0.066 | −0.07 | −0.44 |
| U3 | +0.267 | +0.39 | +3.66 |
| U4 | +0.190 | +0.32 | +3.16 |
| T1 (train) | +0.325 | +1.11 | +3.61 |
| T2 (train) | +0.524 | +1.81 | +6.09 |

- Halves of the pooled unseen trades: −0.011 / +0.483 SOL.
- Hours with a trade: 63, of which 40 are positive. The median hour is +0.009 SOL.
- **Size:** at 1.0 SOL, the L-live / 4.5 / cut-20% row gives FRA +1.33/day, all leaders +5.59/day (raw).
  - The calibration bias grows with size: +8.3 mSOL per SOL of spend at 0.35, +14.9 at 0.55, +20.6 at 0.75.
  - So at 1.0 SOL the correction would wipe it out (INFERRED; the bigger-size fires are mostly dev-list tokens).
- **VM1 on my plain-reading features** (ch15/ch60 against the price at the window start): 1.4 trades/h, −0.07/day.

## 5. Null check (A4)
- 200 random pick sets, each with the same picks per hour, envelope, FRA leaders, simulator and position limit.
- VM1 +1.24 mSOL/trade. Random sets: median −12.05, 95th pct −10.31. VM1 beats 100% of them.
- All dumps: −12.10 mSOL/trade (96,065 dumps).
- **So VM1's selection is real, but it does not clear our landing and costs.**

## 6. Head-to-head
Hours where all three models are unseen and M2/IMIT1 are known:
- U3, 10-24 02:36 → 16:26: M2/IMIT1 from the dipdetect R3 rows (M2 = Stage A gate ≥ 0.010095; IMIT1 = top4).
- U4, 10-25 02:33 → 16:59: the live engines' own dump records (M2 = m2_pick and launch_ok; IMIT1 = imit_pass).

Same simulator, main row. SOL totals:

| Model | U3 | U4 | U3+U4 | Trades | mSOL/trade | Positive hours |
|---|---|---|---|---|---|---|
| VM1 | +0.288 | +0.102 | +0.390 | 122 | +3.20 | 20 / 27 |
| **M2 (gate as live)** | **+0.864** | **+0.570** | **+1.434** | 434 | +3.30 | 21 / 30 |
| IMIT1 | +0.641 | +0.139 | +0.780 | 156 | +5.00 | 14 / 19 |
| VM1 or M2 | +0.930 | +0.470 | +1.400 | 516 | +2.71 | |

- Hour by hour, M2 beats VM1 in 19 hours and VM1 beats M2 in 11.
- **Overlap** (FRA near, covered): VM1 156, M2 485, IMIT1 161. VM1&M2 37, VM1&IMIT1 3, M2&IMIT1 78.
- **Who adds value** (no position limit):
  - VM1 only: +2.76 mSOL/trade (119).
  - M2 only: +2.94 (448).
  - **Both: +13.06 (37).**
  - VM1 as a size-up signal on M2 picks is a HYPOTHESIS only: n=37, found after looking. It would need its own
    pre-registered test.
- **Calibration bias differs by model** (MEASURED on live fires): M2-gate fires +1.92 mSOL/fire (n=107), IMIT1 fires
  +6.63 (n=263). With these, M2 stays positive (~+0.60) and IMIT1 turns negative.

## 7. Live calibration (C)
Our real fires, chain truth, tape without our own trades.
- **(a) Math at the actual chain positions:**
  - The guard call matches the chain on 495 of 496 fires.
  - On 204 fills, the simulator gives +0.308 SOL vs +0.279 real (no follower cut). The curve and fee math is right.
- **(b) L-live landing distribution on the same dumps** (r10+, 370 fires, 3.79 / 0.60 mSOL):

  | Follower cut | Simulator | Realized |
  |---|---|---|
  | 0% | +2.73 SOL | −0.26 |
  | 20% | +1.69 SOL | −0.26 |
  | 35% | +0.91 SOL | −0.26 |

  - The bias is +5.27 mSOL/fire (90%: +2.68 to +7.77).
  - Why (MEASURED): on the dumps that bounce, our landing is later than average, so the replay hands us fills we never
    get. Predicted fill is 47.5% vs 41.6% real.
- **(c) The copy's paper rule** on all 496 fires: +4.96 SOL (2 mSOL) and +5.56 (0.6 mSOL), vs **+0.11 realized**. Paper
  fill is 60% vs 41% real.
- **(d) VM1 on our fired dumps:**
  - VM1 picked 12 of 496 (6 fills). Realized: +0.96 mSOL/fire, vs +0.21 for fires it did not pick. Too few to judge
    (< 20).
  - By VM1 score quartile there is no consistent link: the top 9% realized −1.24 mSOL/fire, the top 25% +0.79.

## 8. Leakage / bias hunt
1. **Trades at or after the dump in the features: none (MEASURED).**
   - My own implementation of the trained feature semantics equals hq2.vm_feats on 20,000 / 20,000 dumps, with 0
     mismatches in all 16 features.
   - All windows end strictly before the dump.
   - drop, curve and max_curve use the dump's own post-trade state, which is known when we decide.
2. **Definition mismatch (not leakage):** ch15/ch60 compare the post-dump price with the price after the FIRST trade
   inside the window, and return 0 when the window has no trade.
   - The plain meaning is "the price 15/60 s ago".
   - VM1 is fragile to this: with the plain reading it picks 5× fewer dumps and loses.
   - Small mismatches (0.2126 vs the measured 0.21207 s/slot; buyers5 over 24 vs 23 slots) flip ≤ 69 of 2,074 picks.
3. **The cut** was not chosen on test data. But it was chosen in-sample (~48 picks/h there), and unseen hours give
   15–25/h.
4. **No train/test overlap** in the copy's forward test.
   - But its window started at the freeze, and its first 10 minutes were an unusual burst: 1,624 dumps and 25 picks,
     vs about 1–10 picks per 10 min.
   - That burst is +0.354 SOL, 14% of its total.
5. **Survivorship:** reverts are counted.
   - But "+80 txs" never leaves the dump's slot, so a late-block dump enters at the block end, ahead of next-slot rivals.
   - At our real landing, 32% of VM1 entries spill into the next block.
6. **Overlapping positions:** unlimited in the copy. Harmless at these rates (1 vs 3 open: same result).
7. **Follower cut:** the copy applies 20% to positive NET after costs, which is milder. At 35% on gross, the main row is
   −0.02/day.
8. **Hours:** the copy used all 5.3 h it had. I scored all 68.7 unseen hours. Its 34 picks/h was not typical; unseen
   hours average 19.8/h.
9. **Token set:** 20 of the copy's 184 forward picks are Mayhem-mode or non-standard tokens. They make +0.600 of its
   +2.597 SOL (+30 mSOL/trade).
   - On these tokens the Mayhem agent moves the reserves, and the engine skips Mayhem tokens.
10. **History truncation** in the copy's forward rows: checked. No pick changed.

## 9. Claims contradicted (quoted)
- "forward test on 5.3 h recorded AFTER it was frozen: 34 picks/h, +0.0141 SOL/trade at 0.3 SOL = +11.7 SOL/day"
  (MORNING_REPORT.md summary).
  - Its own code reproduces it, but 23% of the profit is Mayhem/non-standard tokens and 14% is the first 10 minutes.
  - All 68.7 unseen hours under the same rules: +4.3/day. At our landing and costs: +0.16/day raw, −0.53 corrected.
- "with cheap sends +12.5/day":
  - Cheap sends are not proven live.
  - At 0.6 mSOL and our landing: +0.50/day raw, −0.20 corrected.
- "the replay is an estimate (earlier it was conservative against real fills)" (MORNING_REPORT.md §E), and "Replay is
  conservative (+0.04 vs real +0.29 on fired picks)" (NIGHT_LOG 04:35).
  - On all 496 of our real fires, the +80-tx paper rule says +4.96 SOL; reality was +0.11.
  - A landing-distribution replay is optimistic by +5.3 mSOL/fire.
- "at 0.5/0.75/1.0 SOL: +20.9/+31.4/+41.7 per day" (brief, from the copy).
  - At our landing, 1.0 SOL gives +1.3/day on FRA leaders raw.
  - The live bias grows with size (INFERRED: negative after correction).
- "Rust matched Python 544/544": not tested, since no shadow was built.

## Files
- **Code** (`ops/dip/vm1/`):
  - decode.py: raw → TradeEvents.
  - build.py: merge.
  - core.py: token set, block clock, leaders, features, model evaluator.
  - dumps.py: dump table.
  - live.py: our fires + chain.
  - livecal.py: calibration.
  - sim.py: simulator.
  - expect.py: per-dump expected values.
  - h2h_picks.py: M2/IMIT1 picks.
  - report.py: all tables.
- **Data** (`/home/moiz/sniper-data/vm1/`):
  - trades.npy, dumps.npz, live_fires.json, livecal.json, expect_0.3.npz, expect_1.0.npz, h2h_picks.npz,
    report_v1.txt.
  - Leader schedules from getLeaderSchedule, epochs 1064–1067.

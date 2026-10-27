# haqq (haqqiUUX…) — what makes it sell

10-25 PKT. Read-only study of the local collector recording, 10-22 03:08 → 10-25 06:15 PKT (74 h). Send paths are covered separately in `PATHS.md`.

Labels: MEASURED = counted from the recording. INFERRED = my reading of the numbers.

## 1. Verdict

- **It sells LOTS, not positions.** MEASURED:
  - Each buy is its own lot with its own exit. 97% of sells equal exactly one lot's tokens, or exactly half of one.
  - Two lots in the same token sell in different slots 96% of the time.
  - So adds never change when an earlier lot is sold.
- **Its exit is mainly a slot timer, counted from the dump's slot.** MEASURED:
  - 71–72% of the 0.27 and 0.40 SOL lots sell exactly at one of the slots 10, 12, 15, 20, 25, 30, 40, 50, 60 or 65 after the dump (or one slot later).
  - The 0.25 and 0.30 SOL lots check every 8 slots (9, 17, 25 … 57) and are forced out at 65.
  - Between checks the sell rate is only 0–3% per slot.
- **Which check a lot exits at looks random.** MEASURED:
  - At a check, the lot's return hardly matters: for 0.40 lots at slot 30 the sell rate is 20–31% in every return bucket.
  - Neighbouring lots in time don't share a value. P(same check as the previous lot) is 11.6%, and pure chance gives 11.3%.
  - INFERRED: each lot draws its hold time from a fixed menu, perhaps as an A/B test.
- **Small nudges on top of the timer.** MEASURED:
  - A quiet tape (no outside buy in the last 8 slots) roughly doubles the sell rate at a check: 27% against 14–19% for 0.40 lots.
  - Lots up 25% or more in slots 3–8 sell at 10–21% per slot, against mostly 0–8% for the rest.
  - None of these trigger a sell: dev sells (×1.0–1.3), dumps of 1 SOL or more (×1.1–1.4), other bots' sells in the previous 2 slots (×0.94), or the number of follower buys.
- **One exception: 0.49 SOL is a scalp add.** MEASURED:
  - 80% of these lots are adds.
  - Its sell lands within 150 ms of an outside buy of 1 SOL or more 44% of the time (×2.6 the base rate).
  - When the lot is up 25% or more, that rises to 76%.
- **How well it can be reproduced (causal rules, out of sample).** MEASURED:
  - Best model: within ±1 slot of its real first sell 17% on TEST and 16% on FWD; within ±2 slots 23% and 21%.
  - Simple rules (TP/SL/time, stall, fixed hold) reach only 10–16% within ±1.
  - The model's exits earn 65% of its real P&L on TEST: +33.2 against +50.8 SOL.
- **Exit vs entry.** MEASURED, dip lots, +116.7 SOL in total:
  - Drawing each exit slot at random from its own hold distribution still earns +76.9. So the entry carries about two thirds (66%) of the P&L and exit timing about one third (+39.8, 34%).
  - The best single fixed hold (30 slots after the dump) earns +97.6.
- **For us: keep our 1.3 s exit.** MEASURED replay:
  - On our 116 live fills, our rule makes +1.03 SOL at 35 ms. haqq's timer menu makes −0.92 and its best-fit model +0.18.
  - On 271 IMIT1 shadow picks, the model and our rule are even (+7.42 vs +7.05 at 35 ms). Its timer menu is worse (+4.95).

## 2. Evidence tables

### Its P&L in the recording

Costs: pump fees, tx fees and tips in. ATA rent is left out because it reclaims it in batches (202 close-account txs, +17.4 SOL).

| run (PKT) | hours | buys | P&L SOL | per day |
|---|---|---|---|---|
| R1 10-22 03:09–18:51 | 15.7 | 4,412 | +28.5 | +43 |
| R2 10-22 20:43 – 10-23 18:31 | 21.8 | 6,318 | +35.7 | +39 |
| R3 10-23 19:28 – 10-24 20:20 | ~25 | 7,370 | +62.4 | +53 to +60 |
| R4 10-24 19:26 – 10-25 06:45 | 11.3 | 3,666 | +19.9 | +42 |

- MEASURED: the recording holds 99.2% of the txs in the RPC ledger (`ledger24_haqqiUUX.json`) over the shared 21.8 h. What is missing are tokens the collector did not track, plus withdrawals.
- Only about 40% of lots win. The winners are bigger than the losers.

### Profiles = buy sizes (clean closed lots, all entries)

| buy SOL | lots | dip entry | median age at buy | exit style | P&L SOL |
|---|---|---|---|---|---|
| 0.25 | 4,892 | 55% | 3.9 s | check every 8 slots, big exit at 65 | +31.6 |
| 0.27 | 2,596 | 69% | 3.2 s | checks 10–60, out by about 65 | +22.6 |
| 0.30 | 3,453 | 76% | 4.7 s | mostly spread out; small spikes at 49 / 57 / 65 | +35.5 |
| 0.40 | 3,797 | 80% | 3.2 s | checks 10–60, out at 65 / 201 | +39.2 |
| 0.49 | 1,081 | 76% | 3.5 s | scalp into buys, out at ~20 | +10.1 |
| 0.01 | 2,345 | 30% | 5.3 s | probe; out at 201 | +0.3 |
| 0.74–1.23 | 2,891 | 54% | 11–16 s | dead-curve snipe; out at 100 or 9,000 slots | +2.8 |

- MEASURED: the mix changes by day. 0.25 SOL: 1,587 → 2,136 → 978 → 191 lots per run. 0.30 SOL: 16 → 364 → 2,142 → 931.
- The 0.25 and 0.30 lots share the 8-slot schedule, so the schedule carries across days even when the size changes.

### Sell rate per slot for 0.40 lots (by slot after the dump; MEASURED)

| slot | 10 | 12 | 15 | 20 | 25 | 30 | 40 | 50 | 60 | 65 | 201 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sell rate | 8% | 9% | 13% | 16% | 19% | 25% | 23% | 27% | 51% | 22% | 88% |

- Slots in between: 0–3%.
- At slot 30, by the lot's return one slot earlier:

| return | <−10% | −10…−3% | −3…0% | 0…3% | 3…10% | 10…25% | >25% |
|---|---|---|---|---|---|---|---|
| sell rate | 26% | 29% | 20% | 31% | 24% | 20% | 27% |

### What comes right before a sell (MEASURED)

| | before its sells | at random moments while it holds |
|---|---|---|
| last outside trade, ms before (median) | 368 | 79 |
| last trade was a buy | 44% | 58% |
| last trade, if a buy: 1 SOL or more | 11% | 12% |

- It sells into quiet. It does not sell into a big buy, except in the 0.49 profile.
- Reaction to events: P(this lot sells within 150 ms after an outside trade), relative to the profile's base rate:

| event | 0.25 | 0.30 | 0.40 | 0.49 |
|---|---|---|---|---|
| sell ≥ 1 SOL | ×1.1 | ×1.2 | ×1.3 | ×0.9 |
| dev (creator) sell | ×1.3 | ×1.0 | ×1.0 | ×0.7 |
| buy ≥ 1 SOL | ×1.6 | ×1.2 | ×1.3 | ×2.6 |
| price +10% in one trade | ×2.5 | ×2.1 | ×2.0 | ×3.1 |
| lot up ≥ 25% | ×1.4 | ×1.3 | ×1.8 | ×4.4 |

- Other dip buyers on the same dump ("co-buyers"), adjusted for profile and slot: a co-buyer sell in the previous 2 slots gives ×0.94. A co-buyer sell in the same slot gives ×2.1. INFERRED: the same-slot link is probably shared timers or an in-slot reaction; this data cannot separate the two.

### Partial sells and adds (MEASURED)

- Adds: 6,805 of 21,766 buys. They are sold on their own timer, P&L +54.0 SOL (+8.1 mSOL per lot, against +6.1 for first lots).
- Two-piece exits: 4% of dip lots, mostly 0.25 and 0.01. The first half sells at a median 46 slots after the dump, the second half 25 slots later. These lots earn less (+6.7 vs +9.4 mSOL).

### Reproducing its sell slot, out of sample (dip lots, first sell of each lot)

- TRAIN = R1+R2 (10-22 03:09 → 10-23 18:31 PKT), TEST = R3 (10-23 19:28 → 10-24 20:20), FWD = R4 (tokens launched 10-24 19:25 → 10-25 06:15).
- Causal means the rule decides each slot from data up to the end of the previous slot.

| rule (chosen on TRAIN) | TEST exact / ±1 / ±2 / ±5 | FWD exact / ±1 / ±2 / ±5 |
|---|---|---|
| hazard model, all features (sell at hazard ≥ 0.15) | 10 / 17 / 23 / 34% | 8 / 16 / 21 / 32% |
| hazard model, timer features only | 6 / 13 / 17 / 31% | 4 / 11 / 16 / 29% |
| fixed hold per profile | 6 / 16 / 21 / 32% | 4 / 14 / 21 / 31% |
| TP +10% / SL −30% / 25 slots | 5 / 10 / 14 / 27% | 5 / 11 / 15 / 27% |
| stall: 3 slots with no buy ≥ 0.1 SOL, cap 20 | 4 / 10 / 15 / 28% | 3 / 9 / 14 / 27% |
| checks + quiet tape + TP rule | 5 / 10 / 14 / 23% | 6 / 10 / 14 / 24% |

- TEST lots: 4,398. FWD lots: 1,980.
- The model's top features: profile, slot count, slot mod 8 and mod 5, size; then time since the last ≥ 0.3 SOL sell, the lot's return, and time since the last trade.
- By size on TEST+FWD, ±1: 0.49 → 41%, 0.40 → 19%, 0.30 → 14%, 0.25 / 0.27 → 8%.
- By PKT hour band: 14–18% everywhere. By token age: 15–19%.
- Leaving out the 2.9% of lots whose window touches a listed feed-gap slot: TEST ±1 = 19%.

### P&L of the simulated exits vs its real exits (same dip lots, SOL)

| | real | model rule | timer rule | replay at its real slot |
|---|---|---|---|---|
| TRAIN | +52.5 | +33.5 | +29.1 | +46.7 |
| TEST | +50.8 | +33.2 | +29.4 | +46.9 |
| FWD | +20.2 | +10.8 | +8.2 | +17.1 |

INFERRED: even the exact slot (last column) misses about 8%. That is in-slot timing and the two-piece exits.

### Exit vs entry, all dip lots (impact-free replay; SOL)

| exit used | P&L |
|---|---|
| its real exits | +116.7 |
| best fixed hold: 30 slots after the dump | +97.6 |
| fixed 20 / 15 / 10 slots | +95.3 / +94.5 / +90.1 |
| its own hold distribution, drawn at random | +76.9 |
| our 1.3 s exit (6 slots) | +64.2 |

- Exit timing = +39.8 (34%). Entry = +76.9 (66%).
- Dropping the 2.9% of lots that touch a gap slot: 33% / 67%.
- By token age (dip lots, real vs random draw): under 2 s +33.4 vs +19.4; 2–5 s +59.1 vs +38.4; 5–30 s +24.4 vs +18.5; 30 s or older −0.2 vs +0.7.
- Non-dip lots: +22.5 real vs +2.1 random. For them the exit is most of the profit.

## 3. What it means for us

### Replay on OUR live fills (116 sold fills, FRA + AMS runs 9+; our own sell removed from the curve; SOL)

| exit | 35 ms | 50 ms | 75 ms |
|---|---|---|---|
| our 1.3 s rule (5–6 slots, SL −10%) | **+1.03** (58% win) | +0.87 | +0.84 |
| haqq model rule (as a 0.40 lot) | +0.18 | +0.07 | +0.15 |
| haqq timer menu, 0.30 profile | −0.80 | −0.82 | −0.84 |
| haqq timer menu, 0.40 profile | −0.92 | −0.95 | −0.97 |
| fixed 15 / 20 / 30 slots | −1.53 / −0.89 / −1.44 | similar | similar |

- The same 116 fills as actually run: −0.24 SOL. Run 10 used an 18-slot time limit.

### Replay on IMIT1 shadow picks (271 unique picks with a tape)

Assumptions: 0.35 SOL landing 40 ms after the dump, +5% guard. Of 584 unique picks, 207 guard misses and 106 without a usable tape were skipped.

| exit | 35 ms | 50 ms | 75 ms |
|---|---|---|---|
| our 1.3 s rule | +7.05 (73% win) | +7.07 | +6.81 |
| haqq model rule | +7.42 (76%) | +7.21 | +7.06 |
| haqq timer menu, 0.40 profile | +4.95 | +4.93 | +4.88 |
| fixed 6 / 10 / 20 / 30 slots | +6.42 / +5.56 / +3.98 / +3.49 | similar | similar |

**Reading** (INFERRED):
- haqq's long timers (15–65 slots) pay on its own entries: tokens under 5 s old, where buying keeps coming after the dump.
- On our entries they lose. Longer holds earn less on both our fills and the shadow picks.
- Its model rule ties with ours on shadow picks and loses on live fills.
- **Do not switch.** The one transferable signal: when a lot is up 25% or more in its first ~8 slots, haqq tends to sell at once. Our 1.3 s limit already gets out about then.

### What our engine would need for haqq's model rule (if ever tested)

All of it comes from our trade feed per open position. No RPC is needed.
- Per slot:
  - slots since the dump and since our buy;
  - the position's net value (curve after fees), and its peak and low;
  - return change over 1, 4 and 8 slots;
  - outside buy and sell SOL and counts over 1, 2, 4 and 8 slots and since entry;
  - slots since the last outside buy of 0.1 SOL or more, the last buy of 0.3 SOL or more, and the last sell of 0.3 SOL or more;
  - the biggest buy and sell in 4 slots.
- At entry: dump size, drop %, token age, curve SOL, delay, PKT hour.
- The model: 182 trees, `sniper-data/haqq/h13b_models.pkl`. Sell when the hazard is 0.15 or more.

## 4. Method, data, caveats

- **Data:**
  - all 891 recording chunks of runs `run_20261021_2207`, `_20261022_1543`, `_20261023_1426`, `_20261024_1425` (the last 30 min of R4 dropped);
  - haqq's txs, failed ones included: 45,043 landed trades and 3,375 failed;
  - full tapes of the 12,687 tokens it touched.
- **Ledger:**
  - lots matched by exact token amounts (21,441 full and 1,657 half matches; 170 unmatched sells fall back to FIFO);
  - excluded: censored positions (191 episodes) and episodes with a reserve break (138, i.e. missing trades);
  - lots touching listed gap slots kept, but checked separately: no material change;
  - P&L uses pump and creator fees from the events plus tx fee and tips from the recording.
- **Time:** block position, slot × 212 ms + index ÷ block size × 212 ms. It is a proxy, not a clock. The "dump slot" is the slot of the outside sell of 1 SOL or more right before its buy (dip lots, 62% of first buys). Non-dip lots are not in the match-rate tables.
- **Train/test:** by run as above. Profiles shift between days, so TEST is truly forward.
- **Counterfactual exits:** the curve is replayed with that lot's own sell removed. Others' trades are kept as they happened (no follower reactions modelled). Each counterfactual sell is charged one tx of 0.000325 SOL.
- **Our fills:** runs 9–15 (FRA) and 9–14 (AMS) in the local copies. FRA 15 and AMS 14 are partial. Shadow picks: `dump` events with `pass=true` in the same logs.
- **Not covered:**
  - haqq's 15 failed sells (0.1%), which are too few to matter;
  - off-chain inputs, which could be the hidden variable behind which timer a lot draws.
- **Scripts:** `ops/haqq/h1_txs.py` … `h23`, with the pass-2 extraction in `h2_tapes.py`. Outputs and logs: `sniper-data/haqq/` (`h6.txt`, `h7.txt`, `h9_*.txt`, `h11.txt`, `h15.txt`, `h16.txt`, `h17.txt`, `h18.txt`, `h19.txt`, `h20.txt`, `h22_split.txt`, `h23_gapcheck.txt`).

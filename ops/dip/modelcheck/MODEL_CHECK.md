# Model check: does the dip replay predict real trades? (10-25, 08:30 PKT)

Independent check of the paper replay (`dd1_build.py` `path()` + `dd_lib.sim`), using **125,918 real dip buys by 75 fast bots**.
Read-only, local data only (R1–R4 day arrays and the raw recording, 10-22 03:07 → 10-24 22:42 PKT). No servers, no transactions.
**MEASURED** = computed from the data. **INFERRED** = judgement on top of it.
All latencies are on the model's own clock (block position, ms after the dump). P&L in SOL, pump fees included.

## Verdict
- **The replay mechanics are right. MEASURED.**
  - I removed each bot's buy and its sells from the tape and put "ours" in the same spot with the same SOL.
  - The model then reproduced the bot's real P&L to −0.02 mSOL per trade on average (125,394 closed lots, median error 0).
  - 99.4% of trades were within 0.1 mSOL.
- **What the model assumes about us, as an extra buyer, is close: slightly optimistic in two places and slightly pessimistic in two.**

  | Assumption | Effect on the paper | Label |
  |---|---|---|
  | Fast bots behind us still buy | Optimistic. The model keeps 91.5% of them; the measured rate is 84.5% | MEASURED |
  | Other wallets behind us still buy | Pessimistic. The model drops ~9%; really almost none fail | MEASURED |
  | Dropped buyers still sell later ("phantom sells") | Pessimistic | MEASURED (code) |
  | Our sell lands 75 ms into the slot | Optimistic by +0.2 to +1.4 mSOL per trade (real sells land at a median 93 ms) | MEASURED |
  | Later buyers don't buy less when an early buyer is present | Maybe optimistic by 6–8% | INFERRED |

- **Net: the corrected model is within −1.3 to +1.0 mSOL per fill of the paper at every latency row** (−9% to +20%; the larger percentages are at 75 ms, where the totals are small). **The model is not why live is break-even.**
- **Real bots that land 35–75 ms after the dump on our pick dumps make money.**
  - These are their buys within our +5% guard, valued with our c4 exit.
  - Result: +4.2% per SOL. At 0.35 SOL that is +14.7 mSOL gross, or **+9.6 mSOL net per fill after our 5.1 mSOL costs**. MEASURED.
  - Live we make −2.0 mSOL net per fill (haqq agent, runs 9–14).
- **So the gap is our execution, not the model.** INFERRED from the above plus the haqq agent's numbers:
  - We land late on the contested dumps and fail the guard (58% of attempts).
  - The dumps we do fill are the quiet ones.
  - We pay 4.3 mSOL per round trip; most of these bots pay 0.2–2.4.
- **Warning: all the paper profit comes from the 75 fast bots buying after us.**
  - If none of them bought within 3 slots of the dump, every pick set loses 3.0–4.6 SOL at every latency. MEASURED (replay bound).

## Re-stated: our picks under the corrected model
Same scoring as `dd24_guard_eval.py`: 0.35 SOL, guard +5%, FIX 0.0051 per fill, FRA + AMS near leaders, R1–R4 IMIT1 windows (60.8 h).
- **Corrected** = measured bot tolerance + other wallets kept + no phantom sells + sell at 93 ms.
- **+crowd** = corrected, plus later buyers cut by 40% of our SOL (INFERRED sensitivity).

SOL at 35 / 50 / 75 ms:

| Picks, exit | Paper (now) | Corrected | +crowd |
|---|---|---|---|
| M2, c4 | +24.36 / +14.84 / +7.51 | +24.59 / +15.28 / +8.31 | +22.45 / +13.62 / +7.06 |
| M2, c6 SL10 | +20.29 / +11.59 / +5.38 | +21.66 / +12.81 / +6.30 | +19.69 / +11.33 / +5.14 |
| IMIT1 top4, c4 | +14.66 / +8.45 / +3.40 | +15.09 / +9.07 / +3.84 | +13.74 / +8.10 / +3.20 |
| IMIT1 top4, c6 SL10 | +11.62 / +6.16 / +1.98 | +12.48 / +7.13 / +2.38 | +11.29 / +6.30 / +1.81 |

- **Per fill** (mSOL, 35 / 50 / 75):
  - M2 c4: paper +16.1 / +12.3 / +8.1 → corrected +16.2 / +12.7 / +8.9 → +crowd +14.8 / +11.3 / +7.6.
  - IMIT1 top4 c4: paper +15.9 / +12.4 / +7.0 → corrected +16.3 / +13.4 / +7.9 → +crowd +14.9 / +11.9 / +6.6.
  - Fill counts are unchanged; the guard check is the same.
- **Clean holdouts only, SOL per 24 h** (35 / 50 / 75 ms). R2 is excluded because it is M2's training day.
  - M2 c4 (R1 + R3 + R4, 39.2 h): paper +7.3 / +4.2 / +1.6; corrected +7.4 / +4.4 / +1.9; +crowd +6.6 / +3.8 / +1.5.
  - IMIT1 top4 c4 (R3 + R4, 24.3 h): paper +3.3 / +1.5 / +0.6; corrected +3.5 / +1.8 / +0.75; +crowd +3.1 / +1.5 / +0.55.
- **By day (R1–R4), c4 at 35 ms:** corrected is within ±8% of the paper on every day; +crowd is 3–18% below. At 50 / 75 ms the corrected model is equal or higher (small totals). Tolerance curves fit on R1 + R2 only give the same totals (+15.77 vs +15.87, IMIT1 c4 35 ms). MEASURED (`m7_byday.txt`).
- **These rows assume a FIXED landing time on every dump.**
  - The model's 35 ms row is about a real 28 ms: block-position gaps run about 7 ms longer than real ones (VERIFY_DIP, INFERRED).
  - Our live landing is a spread of times, not one value. The recon agent owns that part.

## 1. Identity check: the model replaying real bot trades (MEASURED)
- **Data:**
  - 75 wallets: the fast-backrunner list, the census wallets with ≥ 100 trips, the top earners, plus CZ77onJz and ETwEAQPL.
  - The trade: each wallet's first buy within 400 ms after a dump (sell ≥ 1 SOL, price −2% or more, curve under 100 SOL).
  - Real lots: matched by exact token amount (else first-in-first-out), as in `ops/haqq/h7`.
- **Checks on the "real" P&L:**
  - Against the wallets' exact SOL balance changes, the difference is a median −0.4 to −3 mSOL per lot = their fees and tips. One exception: ssssswdk's balance changes include other money flows.
  - haqq's 11,176 lots match the haqq agent's lots. The 0.7 mSOL gap per lot is exactly haqq's tx cost.
- **Result** (mSOL per trade, model − real):

  | Part | Mean | Median |
  |---|---|---|
  | Entry (tokens model / real 1.000002) | −0.02 | 0.00 |
  | Whole trade, same sell rows | −0.02 | 0.00 |
  | Real P&L, for scale | +9.70 | −4.25 |

- **The bots' own exits** beat the model's exits on average by 5.3 mSOL against c4 and 5.4 against c6 SL10, because they ride the winners. On the median trade, c4 is better (+1.3).

## 2. Followers: what happens when a buyer lands in front of a bot (MEASURED)
- **Data:** 975,573 (dump, wallet) buy attempts in the dump's slot + 3 slots. That includes 9.0M failed txs of the 75 bots and 29.5M failed pump txs overall.
- **Measure:** success vs the price at the attempt, relative to the price just after the dump.

**Share of attempts that land a buy, by price vs post-dump:**

| Wallet | <1.002 | 1.02–1.03 | 1.03–1.05 | 1.05–1.10 | 1.10–1.20 |
|---|---|---|---|---|---|
| HkQ7hMjy | 56% | 32% | 25% | 10% | 8% |
| DYXDDrZC | 90% | 91% | 90% | 28% | 20% |
| sssssDdM | 77% | 75% | 70% | 28% | 21% |
| ETwEAQPL | 65% | 68% | 71% | 7% | 6% |
| EMKY7r6U | 78% | 81% | 72% | 28% | 25% |
| haqqiUUX | 85% | 86% | 80% | 76% | 57% |
| 9pQQc1xy | 94% | 96% | 94% | 94% | 73% |
| other wallets | 58% | 78% | 76% | 72% | 70% |

- **The model** drops a follower only when our push exceeds a random slack. At pushes of 1 / 2 / 3 / 5% it drops 5 / 9 / 12 / 17%, the same for everyone.
- **Our 0.35 SOL buy pushes the price about 2%** (median 2.2% at the bots' sizes).
- **Keep rate when an extra buyer lands right in front** (model → measured):

  | Wallet | Model | Measured |
  |---|---|---|
  | HkQ7hMjy | 90% | 46% |
  | ETwEAQPL | 85% | 47% |
  | E6JasdE8 | 90% | 19% |
  | DYXDDrZC | 88% | 68% |
  | sssssDdM | 86% | 67% |
  | haqqiUUX | 93% | 86% |
  | 9pQQc1xy | 89% | 94% |
  | All 75 bots | 91.5% | 84.5% |

- **Credit for the bot's buy:** the model credits the extra buyer with +7.2 mSOL per bot trade from the bot's buy (c4 exit).
  - The keep-rate gap makes +2.4 mSOL of that too much (+1.7 on our pick dumps).
  - It is 1.8–3.3 mSOL in every latency band and 2.3–2.8 for every leader client.
- **Natural experiment A: does it matter who moved the price?** At the same price, a bot lands less often when another bot landed ahead of it.
  - HkQ7 at +2–3%: 61% → 24%. ETwEAQPL at +1–2%: 82% → 61%. EMKY7r6U: 94% → 78%.
  - Pooled over all bots there is no difference. The corrected model includes this effect ("comp").
- **Natural experiment B: do later buyers buy less after early buyers?**
  - Envelope dumps, 113,636 of them. Follower SOL = buys from 60 ms to 4 slots after the dump. Split by the number of fast bots landing within 60 ms.
  - Top M2-score band (q4): **3.37 → 3.09 → 2.50 SOL** for 0 / 1 / 2+ early bots. q3: 2.41 → 2.19 → 2.17.
  - Low-score bands go the other way (bots pick the better dumps).
  - Stratified by M2 quintile × dump size × token age (`m5b_strat.txt`): in the top M2 quintile, follower SOL changes by −0.42 per early SOL (0 → 1 early bot) and −0.31 (1 → 2+). Over all quintiles: +0.14 and −0.13.
  - If this is causal, an extra early buyer on our kind of dump crowds out ~30–40% of its SOL in later buys. INFERRED (selection is not fully removed). The "+crowd" column uses 40%.
- **Bots keep the same SOL whatever the push** (HkQ7 0.50, haqq 0.30–0.40, DYXDDrZC ~0.85–0.95 in every price bin). The model's same-SOL rule holds. MEASURED.

## 3. Exit landing (MEASURED)
- **Where real bot sells land** in the slot (block-position ms): p10 / 25 / 50 / 75 / 90 = 17 / 46 / **93** / 153 / 211.
- **Selling in the same slot as the bot, at a fixed position** (mSOL per trade, vs the real row):

  | Position | All trades | Our pick dumps |
  |---|---|---|
  | 0 ms | +3.86 | |
  | 75 ms (the model) | +1.38 | +0.18 |
  | 150 ms | −0.79 | |

  The price drifts down inside exit slots.
- **The sell price itself matches** the real proceeds (identity check above).
- **Moving our sell to 93 ms** changes our picks by at most 0.25 SOL in total.

## 4. Real results by latency band (all bot dip buys; mSOL per trade)

| Band | n | Real (own exit) | Net of their tx | Exit error | Follower error |
|---|---|---|---|---|---|
| 0–10 | 7,360 | +26.4 | +24.5 | −0.1 | +1.8 |
| 10–35 | 24,166 | +10.8 | +9.2 | +0.9 | +3.3 |
| 35–50 | 16,250 | +9.4 | +8.1 | +0.8 | +2.7 |
| 50–75 | 18,073 | +9.5 | +8.3 | +1.4 | +2.4 |
| 75+ | 59,545 | +7.4 | +6.3 | +1.9 | +2.0 |

- **The entry error is under 0.06 mSOL in every band.**
- **Medians:** the median error is 0 for entry, exit and followers in every band, client and wallet. Most trades have no follower or exit effect; the bias sits in the means.
- **By leader client** (AgaveBam, JitoLabs, HarmonicAgave, Firedancer, …): exit error +0.6 to +1.8 and follower error +2.3 to +2.8. There is no client-specific bias.
- **By wallet:** the follower error is largest for the tight-limit bots: ETwEAQPL +9.9, sssssDdM +7.9, DYXDDrZC +6.4, E6JasdE8 +5.9, HkQ7 +3.8.
- **On our pick dumps**, guard-passing bot spots, % of SOL:

  | Band | n | Its spot, c4 | Paper (extra buyer) | Corrected |
  |---|---|---|---|---|
  | 35–50 | 1,343 | +4.3% | +5.6% | +5.1% |
  | 50–75 | 1,177 | +4.1% | +5.5% | +4.9% |

## 5. Corrected model (code in this folder)
- **`mc_corr.py`, `replay_corr()`:** the `path()` replay with the corrections as switches.
  - With them all off it reproduces the stored dd1 output exactly (0 mismatches).
- **`dd1_corr_build.py`:** runs `dd1_build.py` unchanged, with `path()` swapped for the corrected one.
  - Output goes to `/home/moiz/sniper-data/modelcheck/dd1corr/`.
  - Tested on R4. IMIT1 top4 c4 at 0.55 SOL: +1.03 / +0.64 / +0.37 now → +1.12 / +0.60 / +0.39.
- **Curves:** `curves_all.json` (and `curves_r12.json` for the out-of-sample check).

## What this means
- **The replay is right at a given landing spot, for bots and for us.**
  - The haqq agent replayed our own 116 live fills at their real spots: +0.311 SOL, vs +0.244 real before tx costs (`/home/moiz/sniper-data/haqq/h31.txt`). That is +0.6 mSOL per fill. MEASURED (their file).
- **The paper's optimism is in WHERE it assumes we land.** It assumes a fixed 35 / 50 / 75 ms on every dump.
  - Live, our landing varies (all attempts p25 / 50 / 75 = 33 / 52 / 90 ms, haqq agent).
  - We fail on the contested dumps that pay (instant landing there would give +37 mSOL each) and fill the quiet ones (+1.7 even at instant landing).
  - So the fix belongs in the execution model (landing spread per dump, fill selection, costs), not in `path()`. INFERRED.
- **Exits are a lever.** The bots' own exits beat c4 by 5.3 mSOL per trade on average by riding winners. The haqq agent found the same on contested dumps. MEASURED.
- **Risk:** the profit depends on ~75 fast bots buying after us. If they tighten their limits or skip dumps where someone is ahead, the edge shrinks. Tight-limit bots already drop to 19–47% when pushed. INFERRED.

## Caveats and what I could not check
- **Clock:** latency is block position. The real-time mapping is not measured here: on-chain data has no arrival times.
- **Tolerance only shows where bots land failed txs.** A wallet whose failures never land (e.g. Jito bundles) looks more tolerant than it is. All the big bots land failures, so this mainly affects small wallets.
- **Crowd-out (natural experiment B) is not causal.** Dumps with more early bots can differ in other ways.
- **The bots' trades are the dumps bots chose.** Dumps no bot buys are only in the paper rows, not in the real-trade checks.

## Files
- **Code** (`/home/moiz/sniper/ops/dip/modelcheck/`):
  - Extraction: `m0_raw.py`, `m0b_txcost.py`, `m0c_tgfail.py`.
  - Real trades and replays: `m1_trades.py`.
  - Analysis: `m2_analyze.py`, `m3_attempts.py`, `m4_tolerance.py`, `m5_natural.py`, `m6_curves.py`, `m8_errsplit.py`.
  - Restated picks: `m7_restate.py`.
  - Library and checks: `mc_lib.py` (exact `path()` mirror; `mc_selftest.py` 0 mismatches), `mc_corr.py`, `dd1_corr_build.py`, `targets.txt`.
- **Data** (`/home/moiz/sniper-data/modelcheck/`):
  - `trades_R*.jsonl.gz`, `att_R*.npz`, `txc_R*.npz`, `curves_*.json`, `m7_R*.pkl`.
  - Printouts: `m2_tx.txt`, `m4_tolerance.txt`, `m5_natural.txt`, `m5b_strat.txt`, `m7_summary.txt`, `m7_byday.txt`, `m7_holdout.txt`, `m8_errsplit.txt`, `m9_validate.txt`, `m10_spots.txt` (its last line multiplied by 3.5 instead of 0.35: read +14.7 mSOL gross, +9.6 net).
  - `dd1corr/`: corrected dd1 arrays for R4 (from `dd1_corr_build.py`).
  - `raw/`: 2.9 GB of extracted failed txs and target-wallet txs. It can be deleted once the report has been read.

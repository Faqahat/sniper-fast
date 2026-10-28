# OMEN check: arm pre-send only when a wallet's learned habit says it will dump soon (10-29 ~03:45 PKT)

Analyst task. Offline replay only: nothing sent, no server writes, no engine or config change.
- MEASURED = chain recording or live records.
- INFERRED = replay output.
- Times are PKT. Days run 23:15 → 23:15.
- Code + full tables: /home/moiz/sniper/ops/strategies/presend/omen/ (tables.md). Working data: scratchpad omen/.

## Verdict: the claim does not hold up. Do not build OMEN as proposed.
- **"Up to 2× fills":** no. Adding habit-predicted windows on 2–6% holders adds +29% to +46% fills on the TEST days (696 → 901 / 990 / 1,013 fills/day for X = 4 / 3 / 2). Using OMEN to skip today's arms (the full proposal) gives *fewer* fills (696 → 399–729).
- **"Extra fills earn only a little":** right, and in fact it is worse than that. The added fills make +4.6 to +5.6 mSOL each with all followers. With 20% fewer followers they make −3.3 to −4.6 mSOL each. Their median is negative and they win only 45–49%. Today's fills make +16.0 / +5.6 mSOL.
- **No variant passes** the pre-registered bar: on TEST, Δ at −20% followers ≥ +0.5 SOL/day with the 90% CI above 0, and > 0 on each test day.
  - The full OMEN rule chosen on TRAIN loses on TEST for every X: C2 −3.1, C3 −1.7, C4 −1.3, C6 −0.3 SOL/day (at −20% followers).
- **(a) Fewer wasted tries on today's 6% arms: no value.**
  - Skipping the 6% arms of wallets whose habit says "no dump soon" cuts tries by 74% (142k → 37k/day).
  - But it throws away ~290 fills/day that earn +10 mSOL each with all followers. That is −2.8 SOL/day raw on TEST, and ≈ 0 at −20% followers.
  - The tries it saves are worth only ~0.5 SOL/day (5,120 lamports each), and the 40/s cap is already almost never binding (~3% of seconds).
  - Re-timing the window to the predicted slot does nothing: −0.13 [−0.40, +0.12]. Today's 10-slot window already covers the habitual dumps.
- **(b) New fills on 2–6% holders: the only part with a positive raw sign, and it is follower money.**
  - B_t4 (today's rule plus habit-predicted 4–6% holders): TRAIN +2.50 [+1.70, +3.34] raw / +0.79 at −20%. TEST: **+0.91 [−0.17, +2.02] raw / −0.89 [−1.91, +0.13] at −20%**.
  - B3 and B2 give the same picture (TEST raw +1.2 / +0.9, at −20% −1.3 / −1.8).
  - This is the same signature as re-arm and WIDEN. The pattern is "raw looks good, −20% followers kills it".
- **Worth an engine shadow?** Only (b), as **log-only** fields in the observatory build, so we can measure the real fill rate and per-fill P&L on habit-predicted 4–6% holders. No live arming. Skip (a) entirely.

## Pre-registered bar (set before the TEST days were scored)
- TRAIN = 10-24, 10-25, 10-26 (habits learned causally from 10-22 onward). TEST = 10-27, 10-28. The thresholds per X were chosen on TRAIN only: the best pooled TRAIN Δ at −20% followers out of 16 settings.
- PASS: TEST pooled Δ at −20% ≥ +0.5 SOL/day with CI > 0, and Δ > 0 on each test day.

## 1. Habit measurement (MEASURED on the chain tape, 10-22 → 10-28)
**Position** = the first buy that takes a wallet to ≥ 2% of supply on a token whose create is on the tape (mayhem excluded). **Hold** = slots to that wallet's first sell on the token (censored at 150 slots). "Eligible" = what the engine could arm on: not the creator or create signer, not a create-slot buyer, not in the create slot, curve < 100 SOL.
- **Volume:** 80,000 eligible ≥ 2% positions/day. By size: 49k at 2–3%, 15.7k at 3–4%, 10.9k at 4–6%, 4.5k at ≥ 6%. 61,669 wallets. 58% of them have a single position. 7,843 have ≥ 10. The top 1% of wallets hold 40% of the positions.
- **Predictability per wallet (≥ 10 positions):**
  - 3,736 of 7,843 mostly never sell within 150 slots (holders).
  - Of the 4,107 that do sell, only **356 (9%) have a hold IQR ≤ 5 slots**. 302 of those have a median hold of 1–10 slots.
  - Across sellers, the median wallet first-sells within 30 slots in only 26% of its positions.
  - The clockwork ones are dip/backrun bots that hold small lots: FfW5e8gK (1,026 positions, median 2 slots, IQR 1, 3.5% holding), CvHEVC7S, CRjYEJow, 9K5QgBKa, HK9K6ZMM, CZ77onJz.
  - 8yYMhu is **not** clockwork as one wallet: 3,646 positions, holds p25 / p50 / p75 = 6 / 16 / 61 slots. It mixes timers.
- **Causal habit at the moment of the buy** (≥ 10 earlier positions already closed, IQR ≤ 5, median ≤ 150 slots):
  - 6.5% of eligible positions (5,200/day). 91% of them have a median of ≤ 10 slots.
  - The first sell lands within the median ±1 slot 70% of the time, ±2 81%, ±3 88%, ±5 93%. **The habits are real and predict timing well.**
- **Do they make dumps we can fill on?** "Own big dump" = a sell of ≥ 1 SOL that drops the price ≥ 12% in slots 1..10 (TRAIN days):

| Holding at the buy | positions/day | own big dump, all | habit-predicted (median 1–10) | unknown wallet (< 3 prior) | known, not habitual |
|---|---|---|---|---|---|
| 2–3% | 47,506 | 0.0% | 1,824/day → **0.2%** | 0.0% | 0.0% |
| 3–4% | 14,965 | 0.2% | 780/day → **2.2%** | 0.3% | 0.1% |
| 4–6% | 10,404 | 3.2% | 848/day → **28%** | 1.3% | 0.9% |
| ≥ 6% (today) | 4,352 | 12.9% | 657/day → **54%** | 7.0% | 5.2% |

- **Physical ceiling:** one sell of a 2–3% holding cannot drop the price 12% on a normal curve. It needs about 5–7% of the curve's tokens. So a 2–3% habit, however regular, does not produce a fill by itself. Extra 2–3% fills only come from *other* sellers dumping in the same window.
- **Dumps** (≥ 1 SOL, ≥ 12% drop, curve < 100 SOL; 10,516/day):
  - 96% come from a wallet that had a ≥ 2% position. 72% are that wallet's first sell after the position. 38% are the creator.
  - **Only 16% (13% of dumped SOL) come from wallets that were habitual at that moment.** 9.9% of all dumps are habitual *and* on time (within the median ±3).
  - So ~84–90% of the dumps we feed on are not predictable from wallet habit.

## 2. Rules replayed
- **Simulator:** rearm2 `wsim2.py`, the engine-faithful pre-send replay, with one change (omsim.py): a T2 window can start at a later slot and end at a set slot.
- **Settings as live AMS r35:** 0.65 SOL, limit 0.88×, k 8, deadline +1, QUIET skip + stop 6:2, one position, create-slot skip, 40/s helius-ps caps, TP 20% / SL 20%. Exit = the MEASURED live 200 ms fill → sell-landing delays (r28 / r34 / r35).
- **Costs (MEASURED, SLIPPAGE.md):** 2.015 mSOL per fill, 5,120 lamports per landed failed try. 10 draws per day with common random numbers, so Δ is paired. CI = 90%, resampling hours and draws.
- **Base = today:** first ≥ 3% crossing that holds ≥ 6%, 10-slot window. It reproduces rearm2's base exactly (D2 draw 0: 593 fills). Its calibration vs live is inherited from REARM2: AMS pooled −21%, FRA +80%.
- **OMEN predictor** (causal wallet features at the trigger): ≥ N closed positions, share of them big-sold (≥ 50%) within 30 slots ≥ q, hold IQR ≤ I, median hold 1..10 slots (K = 10). The window runs from (predicted slot − M) to (predicted slot + M), where predicted slot = position open + median, and it starts no earlier than the trigger.
- **Variants:**
  - **A:** today's 6% arms. Predicted wallets get the OMEN window. Known wallets (≥ N) with no prediction are not armed. Unknown wallets keep today's window.
  - **Askip / Atime:** only the skip, or only the re-timing.
  - **B_X:** today's rule, plus OMEN windows for predicted holders with X ≤ pct < 6. For X = 2 these are first 2% crossings; for X = 3 / 4, first 3% crossings.
  - **C_X:** A + B_X (the full proposal).
- **TRAIN choice** (16 settings per X; N ∈ {5, 10}, q ∈ {0.5, 0.8}, I ∈ {5, ∞}, M ∈ {2, 4}):
  - X = 2: N10 q0.8 I5 M2.
  - X = 3 / 4: N10 q0.8 I5 M4.
  - X = 6: N5 q0.8 I5 M4.
  - No TRAIN setting had a CI above 0. The best was C4 at +0.96 [−0.28, +2.14] at −20%.

## 3. Results (INFERRED; 0.65 SOL; SOL/day scaled to 24 h)
**TEST days. "OMEN fills alone" = fills from added windows only, net of their failed tries.**
| Variant | Day | arms/day | tries/day | fills/day | OMEN-added fills/day | OMEN fills alone | total | Δ vs today [90% CI] | Δ −20% followers [CI] | Δ w/o top-5 | sends/s | cap-bound s % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| today (6%) | 10-27 | 2,825 | 141,971 | 756 | – | – | +11.64 | – | – | – | 1.64 | 3.7 |
| today (6%) | 10-28 | 2,361 | 118,593 | 636 | – | – | +9.25 | – | – | – | 1.37 | 3.2 |
| C2 (full, ≥ 2%) | 10-27 | 4,294 | 96,462 | 777 | 402 | +2.11 | +8.07 | −3.57 [−6.26, −0.72] | −3.80 [−6.48, −1.31] | −4.99 | 1.12 | 2.9 |
| C2 | 10-28 | 4,033 | 91,024 | 678 | 347 | +0.70 | +6.26 | −2.99 [−5.76, −0.16] | −2.42 [−4.88, −0.07] | −4.74 | 1.05 | 2.3 |
| C3 (full, ≥ 3%) | 10-27 | 2,522 | 72,856 | 770 | 348 | +2.25 | +9.49 | −2.15 [−4.92, +0.48] | −2.40 [−5.00, −0.07] | −3.59 | 0.84 | 2.2 |
| C3 | 10-28 | 2,378 | 69,525 | 688 | 321 | +1.11 | +8.23 | −1.02 [−3.70, +1.54] | −0.94 [−3.48, +1.31] | −2.76 | 0.80 | 1.8 |
| C4 (full, ≥ 4%) | 10-27 | 1,705 | 53,544 | 670 | 243 | +1.86 | +9.14 | −2.51 [−5.30, +0.20] | −1.82 [−4.31, +0.45] | −3.93 | 0.62 | 2.1 |
| C4 | 10-28 | 1,622 | 50,460 | 595 | 225 | +0.58 | +7.80 | −1.45 [−3.62, +0.70] | −0.68 [−2.57, +1.15] | −3.09 | 0.58 | 1.2 |
| C6 (= A, 6% only) | 10-27 | 885 | 32,452 | 424 | 0 | – | +7.21 | −4.43 [−6.78, −2.10] | −1.28 [−3.18, +0.63] | −5.80 | 0.38 | 1.2 |
| C6 | 10-28 | 822 | 29,211 | 374 | 0 | – | +7.42 | −1.83 [−3.30, −0.29] | +0.77 [−0.62, +2.31] | −3.33 | 0.34 | 0.5 |
| B_t4 (today + 4–6%) | 10-27 | 3,535 | 157,127 | 970 | 225 | +1.51 | +12.89 | +1.25 [−0.06, +2.58] | −0.75 [−2.06, +0.46] | −0.42 | 1.82 | 4.3 |
| B_t4 | 10-28 | 3,071 | 135,278 | 833 | 209 | +0.76 | +9.81 | +0.56 [−1.09, +2.22] | −1.02 [−2.63, +0.53] | −1.18 | 1.57 | 3.6 |

**Pooled.**
| Variant | TRAIN Δ raw | TRAIN Δ −20% | **TEST Δ raw** | **TEST Δ −20%** | TEST w/o top-5 | TEST fills/day (today → variant) | TEST added fills/day, own SOL/day |
|---|---|---|---|---|---|---|---|
| C2 | −1.50 [−3.02, +0.03] | −1.37 | **−3.28 [−5.29, −1.31]** | **−3.11 [−4.90, −1.37]** | −4.87 | 696 → 727 | 374, +1.41 |
| C3 | +0.15 [−1.26, +1.64] | +0.06 | **−1.59 [−3.50, +0.27]** | **−1.67 [−3.40, +0.05]** | −3.18 | 696 → 729 | 335, +1.68 |
| C4 | +0.47 [−0.84, +1.77] | +0.99 | **−1.98 [−3.81, −0.23]** | **−1.25 [−2.77, +0.33]** | −3.51 | 696 → 632 | 234, +1.22 |
| C6 / A | −2.51 [−3.73, −1.31] | +0.10 | **−3.13 [−4.55, −1.73]** | **−0.25 [−1.46, +0.99]** | −4.56 | 696 → 399 | – |
| Askip (θ4) | −2.35 | +0.10 | −2.83 [−4.22, −1.48] | −0.13 [−1.32, +1.04] | −4.26 | 696 → 415 | – |
| Atime (θ4) | −0.13 | −0.10 | −0.13 [−0.40, +0.12] | −0.05 [−0.28, +0.17] | −1.78 | 696 → 690 | – |
| **B_t4** | **+2.50 [+1.70, +3.34]** | +0.79 [+0.10, +1.52] | **+0.91 [−0.17, +2.02]** | **−0.89 [−1.91, +0.13]** | −0.80 | 696 → 901 | 217, +1.14 |
| B3 | +2.09 | −0.13 | +1.20 [−0.13, +2.50] | −1.32 [−2.54, −0.17] | −0.54 | 696 → 990 | 311, +1.53 |
| B2 | +1.24 | −1.11 | +0.91 [−0.56, +2.34] | −1.84 [−3.33, −0.44] | −0.83 | 696 → 1,013 | 349, +1.35 |

**Per fill on TEST** (mSOL after costs; all followers / −20%):
| Fill group | Per fill (all / −20%) | Median | Win |
|---|---|---|---|
| Today's fills | +16.0 / +5.6 | +7.4 | 56% |
| OMEN-timed 6% fills (A) | +20–21 / +9–10 | +10 | 60–61% |
| Remaining unknown-wallet fills (A) | +3.5–7 / −3 to −6 | | |
| Added 4–6% (B_t4) | +5.6 / −3.3 | −1.6 | 49% |
| Added 3–6% (B3) | +5.5 / −3.3 | | 47% |
| Added 2–6% (B2) | +4.7 / −4.2 | −7.5 | 45% |

- OMEN does pick the best of today's fills (+21 mSOL). But today's rule already catches them in its 10-slot window. Skipping the rest removes fills that are positive raw.
- Send rate is never the constraint. Today sends 1.4–1.6 tries/s on average, and 3–4% of sending seconds hit the 40/s cap. B2 raises that to 2.0–2.3/s and 5%.

## 4. Why the claim fails (INFERRED from §1 + §3)
1. **Habit predicts timing well (88% within ±3 slots), but only for ~16% of the dumps.** Most dumps we profit from come from creators and one-off wallets with no history.
2. **The habitual wallets that matter are already in today's 6% window.** Their median holds are 2–5 slots. Re-timing adds nothing, and skipping the "unpredicted" 6% arms loses real fills.
3. **Small holders can't dump 12% themselves.** Below ~4%, the habit-predicted sell is a small exit (often a dip bot closing a 3.5% lot). Our fills there come from whoever else sells, at about +5 mSOL raw and negative after followers.

## 5. What to log live (observatory / module 8 SELECTION census, next build)
To test OMEN (b) for real without arming, per holder event:
- **Every ≥ 2% crossing, not just ≥ 3%:** wallet, mint, slot/idx, pct before → after, creator / create-signer / create-slot flags, curve vsol, token age.
- **The wallet's live habit state at that moment** (the engine's own causal view): number of closed positions, median and IQR of the hold, share big-sold within 30 slots, last-10 holds, predicted dump slot, and the OMEN flags (would arm A / B_X under the θ above).
- **Outcome:** the wallet's first sell (slot/idx, fraction sold, price drop, SOL), its first ≥ 1 SOL / ≥ 12% sell, and any other ≥ 12% drop on the token in trigger +1..+15 slots, with the seller and the seller's habit state.
- **For our real windows:** arm slot, predicted slot, which try filled or failed, and the result. This lets the live fill rate on predicted windows be compared with this replay.
- **Rolling per-wallet history:** the engine has to persist it across restarts (a map wallet → last ~50 holds). It can be pre-seeded from the tape. Today's engine has none of this.

## 6. Caveats
- All P&L is INFERRED. Base calibration is inherited (AMS −21%, FRA +80%). Deltas are paired draws.
- Habits are learned from 10-22 onward only (2 warm-up days). Tokens created before a tape day are invisible, so positions on them are missing.
- 64 TRAIN settings were tried. TEST was used only to score the four chosen ones plus the decomposition variants, which use the C4 setting.
- The per-holder window uses the wallet's first sell to stop (as live T2). An OMEN window that opens after an early sell never sends.

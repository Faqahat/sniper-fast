# Analyst A (positions): haqq = ~7 bots in one wallet; multi-buys = several bots; NEW rule = re-arm pre-send after a paid whale dump (10-28 ~02:57 PKT)
Saved by the main session from the agent's reply. Code: this folder (p1_build, p1b_codes, p2–p15, plib). Tables: /home/moiz/sniper-data/haqq_dissect/pos/ (rules p10.txt, stress p13.txt, bot codes codes.pkl + p4.txt). p6 (reactive rule walk-forward D5–D6) was still running when saved.

## 1. haqq is ~7 bots in one wallet (MEASURED)
The last 3 digits of the CU price are a bot code. Each buy and the sells of that lot share it (99.97% of sold tokens).

| Code | Lots (6 days) | Size | Net SOL | mSOL/lot | Hold p50 | Days > 0 |
|---|---|---|---|---|---|---|
| **247** | 8,531 | 0.40 | **+89.9** | +10.5 | 4.1 s | 6/6 |
| **248** | 11,080 | 0.30 | **+83.6** | +7.5 | 4.2 s | 6/6 |
| 244 | 8,425 | 0.25 | +20.5 | +2.4 | 9.0 s | 6/6 |
| 226 | 1,901 | 0.50 | +12.2 | +6.4 | 0.9 s | 6/6 |
| 234 (dead curve) | 4,847 | 0.79 | +5.2 | +1.1 | 1,198 s | 4/6 |
| 231 | 369 | 0.25 | +3.6 | +9.8 | 1.5 s | 6/6 |

- 247 and 248 are dump-reactive (75–77% of buys within 2 slots of a ≥5% dump) and make ~80% of his profit.
- A bot almost never adds to its own lot (546 lots, −3.2 mSOL/lot). "Multi-buy" = different bots on the same token (247→248 1,753×, 248→244, 244→248).

## 2. Trips and the GMGN view (MEASURED)
- **3+ buy trips** are 71–140% of each day's net.
- **Token level** (how GMGN groups trades):

  | His buys on the token | Tokens | Net SOL | Win |
  |---|---|---|---|
  | 1 | 9,327 | −67.6 | 30% |
  | 2 | 4,230 | −24.6 | 39% |
  | 3–4 | 3,299 | +106.2 | 50% |
  | 5–8 | 880 | +165.5 | 69% |
  | 9+ | 83 | +35.8 | 86% |

- **This is OUTCOME SELECTION.** By other bots joining AFTER the lot: +0.6 / +12.2 / +31.8 mSOL. By bots ALREADY holding at decision time: +5.5 / +6.5 / +7.7.

## 3. The ladder (code-matched)
- **Adds earn like first lots over 6 days:**

  | k-th buy | 1st | 2nd | 3rd | 4th | 5th | 6th+ |
  |---|---|---|---|---|---|---|
  | mSOL/lot | +6.2 | +6.4 | +6.9 | +4.9 | +13.2 | +17.4 |

  10-27 (the main session's "2nd lot ≈ 0") was a weak day for adds.
- **Good adds:** 10–35% below the 10-slot high (+10); after outside net flow < −3 SOL (+12.6); a new dump while in profit (+9.3). Momentum adds are weak.
- **Same bot re-entering after a ≥+15% lot:** +8.8 mSOL (6/6 days).

## 4. For US: reactive adds / holds / bursts don't work (INFERRED replays)
- Buying every dump loses in every k-th-dump bucket, calibrated −10..−12 mSOL/attempt.
- **Position rules, walk-forward, calibrated** (D2 / D3 / D4):

  | Rule | D2 | D3 | D4 |
  |---|---|---|---|
  | REPEAT (= DV8) | −0.20 | −0.25 | +1.59 |
  | ADD | −0.14 | −0.69 | +1.48 |
  | ONCE | +0.42 | +0.22 | +1.23 |

  ADD is worse with 10% fewer followers.
- **Causal hold/add at the 5-slot mark:** adding loses in every state. B's "+27 SOL added-to lots" is outcome-conditioned and does not reproduce causally.
- **Burst signal multi-day:** 10-27 was an outlier. As a rule for us it is −6..−20 mSOL/fill (pre-send style) and −9..−13 (reactive); walk-forward +0.77 over D2–D5. Not robust alone.

## 5. THE RULE: re-arm pre-send on whale battlegrounds (INFERRED replay)
- **Trigger:** a whale dump (one sell ≥ 6% of supply, non-mayhem, token ≤ 120 s old) whose 2-slot result is ≥ +0.02 SOL on a 0.40 buy (≈ +5%), known at the end of slot dump+2.
- **Action:** arm pre-send for slots dump+3..+52, 2 tries/slot; buy the next whale dump in the same slot; 2-slot exit. Contention-aware landing fitted on our 1,144 live pre-send fills; fill if the entry is ≤ 0.88 × the pre-dump price.

| Test day | Fills | Model, NOW | Calibrated NOW | Calibrated CHEAP | −10% followers |
|---|---|---|---|---|---|
| D2 | 236 | +11.71 | **+6.27** | +6.95 | +5.06 |
| D3 | 164 | +4.67 | **+2.24** | +2.70 | +1.56 |
| D4 | 298 | +10.40 | **+5.34** | +6.19 | +4.08 |
| D5 | 302 | +14.45 | **+7.77** | +8.63 | +6.34 |

- **Sum D2–D5:** calibrated NOW **+21.6 SOL (≈ +5.4/day)**; +17.0 with 10% fewer followers. Parameters chosen on the previous day were stable.
- **Per fill:** +28.4 mSOL [+26.4..+30.2] on re-dumps after a paid one; first whale dumps −3.3; re-dumps within 2 slots −30 (must wait for the previous window to close).
- **Stress (mSOL/fill):**

  | Landing | Per fill | Fill |
  |---|---|---|
  | Measured model | +41.5 | 75% |
  | 2× trades ahead | +32.1 | |
  | 3× trades ahead | +26.7 | |
  | Our reactive landing | +16.9 | 50% |

- haqq buys only 7.7% of these dumps: a gap he leaves open.
- **Caveats:** the trigger is a proxy (whale-size sells, not the engine's whale-buy arming); the 0.88 limit is assumed; the landing model was fitted on calmer tokens; the calibration is borrowed; concurrency and rate limits were not simulated.
- **Engine needs:** per-token whale dump tracking + 2-slot result; second+ pre-send windows per token; re-arm 3–52 slots after a paid dump, age ≤ 120 s, 2 tries/slot, 2-slot exit, never inside the previous 2-slot window; mayhem skip; logs. Shadow first.

## Addendum (D5 in): reactive position rules (calibrated NOW; D2 / D3 / D4 / D5; sum)

| Rule | D2 | D3 | D4 | D5 | Sum | 10% fewer followers |
|---|---|---|---|---|---|---|
| REPEAT | −0.20 | −0.25 | +1.59 | +0.15 | +1.29 | negative all 4 days |
| ADD | −0.14 | −0.69 | +1.48 | +1.44 | +2.09 | negative all 4 days |
| ONCE | +0.42 | +0.22 | +1.23 | +0.26 | +2.13 | negative all 4 days |
| Battleground rule, no gate | | | | | −8.4 | |

ADD's D5 lead comes from the exit chosen on the previous day, not from adding. Reactive position rules are worth ≤ +0.5/day, flip sign between days and are not worth an engine change. The pre-send re-arm (§5) remains the rule to test. Full tables: p6.txt / p6.json.

## MAIN-SESSION VERIFICATION of the bot codes (verify_main_codes.py; own code on exec/ext raw txs)
- All 19,056 mints, 39,770 sells: 99.98% of sells carry a code that an earlier haqq buy on the same mint carried. A shuffled-code control gives 76.53%.
- Mints with ≥2 codes (8,084 mints, 26,822 sells): 99.99%, against 65.95% shuffled.
- Every code individually: 100.0%.

**CONFIRMED.**

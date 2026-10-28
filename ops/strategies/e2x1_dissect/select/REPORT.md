# E2X1 — SELECTION (agent "select", 10-28 PKT)

Wallet **E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb** ([GMGN](https://gmgn.ai/sol/address/E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb)).
Code: this folder (s0–s22). Data: /home/moiz/sniper-data/e2x1_dissect/select/ (s*.txt are the raw outputs quoted here).

## Data
- **Tape:** every pump.fun trade, 10-22 03:13 → 10-28 18:41 PKT (**6.64 days**).
  - Source: the haqqml "fresh" tape, decoded from the recorder.
  - Creates and names come from the raw chunks (s0).
- **His trades:** 8,069 buys on 4,990 tokens (all SOL-quoted, no mayhem).
  - On the overlap with recon's exact lot table (10-26 20:00 → 10-28 18:41), my buys match recon's lots **2,579 / 2,579** by (slot, idx). MEASURED.
- **P&L basis (s2):**
  - Trip-based lots, valued at curve SOL.
  - Unclosed trips are marked at the last curve price. These are mostly graduated tokens sold later on PumpSwap, which is outside the tape.
  - On recon's 34 PumpSwap lots, the marks give +30.87 vs recon's exact +30.82 SOL.
  - Non-PumpSwap lots differ from recon only by the pump fees (corr 0.99).
- **Totals:**
  - Gross **+372 SOL**.
  - Pump fees (from fee_bps per row) 81 SOL, so **+294 SOL net of pump fees ≈ 44 SOL/day**. Tx fees and tips are not included.
  - Recon's exact result (all costs): D0 +52.7, D1 +59.3 SOL.
- **Days (gross / net of pump fees, SOL):**

| Day | Gross | Net of pump fees |
|---|---|---|
| 10-22 | 24.0 | 17.5 |
| 10-23 | 55.1 | 45.6 |
| 10-24 | 44.7 | 35.8 |
| 10-25 | 50.5 | 41.5 |
| 10-26 | 71.9 | 56.0 |
| 10-27 | 77.8 | 60.5 |
| 10-28 (to 18:41) | 47.9 | 37.2 |

- **Size:** 0.25 SOL until 10-25. Since then sizes are tiered: about 0.3–0.45 SOL for young tokens and **1.000 SOL** for tokens older than 2 min.
  - Recon's size code: buy = f × curve vSOL after the trigger trade.
- **Owner's GMGN note on "13–31 min old" tokens:** that is most likely the age at viewing time. At his buys the age is a median **13 s** (first buys).

## 1. What triggers his buys (MEASURED)
- **He reacts to a single trade.**
  - **99.8 %** of his buys land ≤ 1 slot after the previous trade on that token; 80 % are in the same slot.
  - Recon's exact trigger (the size equation) is in the same slot 61 % of the time and the next slot 38 %.
  - The trigger trade is a **buy 65–67 %** of the time and a sell 33–35 %.
- **Token stage at his first buy:**
  - 44 % of first buys come at age < 10 s.
  - 46 % at 10–120 s.
  - 10 % later.
  - 34 % of all his buys are **re-entries** (a new round trip on a token he already traded). This is what GMGN shows as 2/2, 3/3, 4/4.
- **His result is flat across tape contexts (s22, first buys, mean return per lot):**
  - Every bucket earns +7 % to +17 %, whatever the drawdown from peak, the last 5 s / 30 s move, the curve vSOL, the SOL bought by others, whether the dev sold, the bundle size, or the top-5 share.
  - Only two contexts are weak:
    - top-5 holders ≥ 90 % (+3.6 %, n = 717);
    - vSOL ≥ 70 (+3.3 %, n = 210).
  - So no visible context explains the profit. The selection is orthogonal to the obvious tape state.

### Trigger families
Naming:
- **Stage:** LAUNCH < 10 s, EARLY 10–120 s, LATE 2–30 min.
- **Trigger:** the biggest-impact trade in the 3 slots before him is a sell ≤ −5 % (DIP), a buy ≥ +5 % (RIP), or smaller (FLOW).
- **Buy kind:** RE-ENTRY is a buy after a closed trip (split by price vs his previous fill); ADD is a buy while still holding.

Per-family results, 6.64 days (s15). Net = gross minus pump fees.

| Family | Buys | Share | Gross SOL | Net SOL | % of P&L | Net/day | ret/lot | win | age p50 s | hold p50 s |
|---|---|---|---|---|---|---|---|---|---|---|
| LAUNCH-DIP | 1022 | 12.7 % | 36.9 | 29.3 | 9.9 | 4.42 | 12.1 % | .56 | 4 | 14 |
| LAUNCH-RIP | 620 | 7.7 % | 25.6 | 20.9 | 6.9 | 3.14 | 14.6 % | .57 | 5 | 11 |
| LAUNCH-FLOW | 460 | 5.7 % | 6.9 | 3.3 | 1.8 | 0.50 | 4.9 % | .50 | 5 | 42 |
| EARLY-DIP | 627 | 7.8 % | 28.6 | 23.5 | 7.7 | 3.54 | 13.7 % | .55 | 19 | 22 |
| EARLY-RIP | 925 | 11.5 % | 33.5 | 25.9 | 9.0 | 3.89 | 11.1 % | .52 | 27 | 25 |
| EARLY-FLOW | 731 | 9.1 % | 26.3 | 19.9 | 7.1 | 3.00 | 10.9 % | .50 | 29 | 44 |
| LATE-DIP | 86 | 1.1 % | 9.6 | 8.6 | 2.6 | 1.29 | 16.6 % | .60 | 214 | 56 |
| LATE-RIP | 249 | 3.1 % | 14.6 | 11.9 | 3.9 | 1.80 | 14.8 % | .50 | 316 | 80 |
| LATE-FLOW | 270 | 3.3 % | 13.4 | 10.1 | 3.6 | 1.52 | 9.8 % | .51 | 212 | 96 |
| RE-ENTRY-DIP (< −10 % vs prev fill) | 828 | 10.3 % | 53.7 | 44.4 | 14.4 | 6.69 | 13.8 % | .53 | 208 | 58 |
| RE-ENTRY-FLAT (±10 %) | 570 | 7.1 % | 23.5 | 17.1 | 6.3 | 2.58 | 9.2 % | .49 | 98 | 33 |
| RE-ENTRY-HIGHER (> +10 %) | 1359 | 16.8 % | 89.6 | 71.3 | 24.1 | 10.73 | 13.0 % | .57 | 169 | 44 |
| ADD-HOLDING | 322 | 4.0 % | 9.7 | 7.8 | 2.6 | 1.17 | 12.3 % | .53 | 79 | 67 |

Recon's exact P&L (all costs) for the same families, D0+D1 (s19, 2,579 lots): **total +112.1 SOL**, and every family except LATE-RIP is positive.

| Family | Exact P&L (SOL) | mSOL/lot |
|---|---|---|
| RE-ENTRY-HIGHER | +30.7 | +66 |
| RE-ENTRY-DIP | +23.9 | +94 |
| EARLY-DIP | +12.3 | +58 |
| LAUNCH-DIP | +8.7 | +26 |
| EARLY-RIP | +8.7 | +27 |
| RE-ENTRY-FLAT | +7.0 | +38 |
| LAUNCH-RIP | +6.1 | +28 |
| EARLY-FLOW | +5.7 | +23 |
| LATE-DIP | +5.3 | +203 |
| LATE-FLOW | +1.7 | +21 |
| LAUNCH-FLOW | +1.4 | +9 |
| LATE-RIP | −1.3 | −20 |

- His P&L has a fat tail. Recon: the top 5 % of lots make 73–138 % of a bot-day's P&L.
- His first-buy picks later reach 2× from the trigger price 32–35 % of the time; skipped look-alike moments do so 11–24 % of the time (s20).

## 2. How he chooses: take vs skip (test = newest 6 h, 10-28 12:41–18:41, never used for choices)
**Universe (s3).** Every outside trade on a non-mayhem SOL curve aged 0–30 min: 13.9 M events.
- Label: he buys within 1 slot (s4) or within 3 slots with nothing held yet (s9).
- Features use the event and the rows before it only.
- Negatives are a 4 % hash sample (weight 25).

**Event level (s4, GBDT on 39 tape features):**
- Test AUC **0.91**, but precision is only 3.3 % at 50 % recall (base 0.33 %).
- The model mostly finds "active young token right now"; age, SOL in the current slot, and SOL in the last 1 s dominate.

**Inside each trigger family (s9).** Forward returns are market price, no fees, measured from the end of the slot after the trigger (≈ our entry). g24 / g141 = the move over the next 24 / 141 slots (about 5 s / 30 s).

| Envelope | His take rate | His picks g24 / g141 | Skipped g24 / g141 | GBDT test AUC | Model's test picks (×3 rate) that are NOT his: g24 / g141 |
|---|---|---|---|---|---|
| LDUMP (age < 10 s, sell ≤ −5 %) | 1.25 % | **+7.5 / +4.3 %** | −1.4 / −5.4 % | 0.83 | −6.6 / −5.3 % |
| LPUMP (age < 10 s, buy ≥ +5 %) | 0.79 % | **+6.5 / +5.4 %** | −1.6 / −8.4 % | 0.95 | −10.4 / −17.8 % |
| EDUMP (10–120 s, sell ≤ −5 %) | 0.63 % | **+4.3 / +4.4 %** | −1.4 / −3.4 % | 0.79 | −6.8 / +10.7 % (n tiny) |
| EPUMP (10–120 s, buy ≥ +5 %) | 1.95 % | **+3.3 / +1.1 %** | −1.0 / −3.4 % | 0.78 | −8.5 / −18.9 % |
| MFLOW (2–30 min, \|impact\| ≥ 2 %) | 0.22 % | **+2.6 / +5.9 %** | −0.5 / −1.5 % | 0.81 | −3.4 / −5.4 % |

- **His picks beat the look-alikes he skips in every family**, even when entering one slot after him.
- A model that **finds his kind of moments well** (AUC 0.78–0.95) **does not find his outcomes**. Its rate-matched picks that he did not take **lose**.
- Adding create-time metadata did not change this (s16 + s9 META=1: URI host / launch tool, name and symbol shape, vanity suffix). AUC moved by ±0.01 and the non-his picks still lose.
- Test-window caveat: only 22–73 of his first-buy picks fall in the 6-h test per family. Test numbers are noisy; the direction is the same in train and test.

**Simple rules (s17).** Up to 3 thresholds per family, fitted on train to keep 50 % of his picks:

| Family | Test recall | Test precision | Lift |
|---|---|---|---|
| LDUMP | 0.37 | 0.051 | 3.0× |
| LPUMP | 0.42 | 0.029 | 4.3× |
| EDUMP | 0.24 | 0.015 | 2.1× |
| EPUMP | 0.42 | 0.032 | 1.4× |
| MFLOW | 0.27 | 0.003 | 2.4× |

- The rules' picks that are not his lose even **in sample**: g141 from −3.6 % to −10.5 % on train.
- **No simple rule reproduces ≥ 50 % of his picks with similar forward returns.**

**Is he copying someone? (s11, s13, MEASURED)**
- There is no outside leader.
- The most frequent outside wallets before the cluster's first buy cover ≤ 1.8 % each.
- A union of 102 "lift ≥ 5" wallets precedes 55 % of anchors, but also 10 % of random moments. These are co-reactors (other dip/snipe bots, including our AMS wallet), not leaders.

**His cluster (s7, s8, s12, s21; MEASURED; same operator vs same signal is INFERRED):**
- **Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ is a twin.**
  - 91 % of its 3,197 tokens are his; same 0.296 sizes.
  - It is first 43 % of the time, median gap 0 slots.
  - Net of pump fees: +108 SOL / 6.6 d.
  - The cluster's first buyer per token is E2x1 on 3,638 tokens and Grozoe2L on 1,220.
- **Pure copiers:**
  - 4mYySb7Z74EK9c6AzSmRRbsd5NjRKeU2yjMF6nfz8ctD (1,120 tokens) and Hj4uACn8Jp2QvbMFhkhWWCdHPzC2SEXg7fhpZayYVcyL (588 tokens).
  - 100 % of their tokens are his, and they are never first.
- **Wider copy cohort:** 16 wallets, chosen on train only.
  - They follow 81 % of his buys within 2 slots, but with little SOL: 0.23 SOL vs 1.39 SOL from everyone else.
  - Removing their flow (constant-product counterfactual, INFERRED) cuts his P&L by only about **10 %** (231 → 208 SOL on train).
  - **So copiers do not make his edge.**

## 3. Entry speed: selection or speed?
**Lag to recon's exact trigger (s19, D0+D1, chain clock = slot × 212 ms + index share of block):**

| Bot | Same slot | Next slot | Lag median | p75 | p90 | Trades between trigger and him (median) |
|---|---|---|---|---|---|---|
| FRESH | 61 % | 38 % | **50 ms** | 82 ms | 125 ms | 2 |
| MINUTE | 61 % | 37 % | **53 ms** | 88 ms | 130 ms | 1 |

His block position: median 53 % into the block.

- **Ours:** reactive landing median ~58 ms (measured 10-25), pre-send ~20 ms.
- **So his speed is about the same as ours.** Speed is not what separates him from us.

**Later entry (s5, his exits kept, price from the tape, no own impact):**

| Entry | Mean return/lot | Total at his sizes (6.64 d) |
|---|---|---|
| His fill | +11.96 % | 372 SOL gross |
| +1 slot | +8.47 % | 268 SOL (−28 %) |
| +2 slots | +8.10 % | 257 SOL |

- Most of what is left after a slot's delay is his **selection plus his exits**.
- Fixed-horizon market return from his fill is +4.5 % at 30 s versus his realised +12 %. So exit timing adds about +5 to +7 points (exits are only roughly attributed).

## 4. Multi-buys (s14, s15)
- **GMGN's 2/2, 3/3, 4/4 are round trips, not pyramiding.**
  - Only 322 buys (4 %) add while he still holds: +12.3 %/lot, +9.7 SOL gross.
  - 2,757 buys (34 %) are re-entries after a closed trip: **+167 SOL gross, 45 % of P&L**.
- **Re-entries pay on their own** (each lot is measured from its own fill to the sells of its own trip; causal):

| Re-entry type | Buys | Gross SOL | ret/lot | Recent exact (D0+D1) |
|---|---|---|---|---|
| Into a dip (< −10 % vs his previous fill) | 828 | 53.7 | 13.8 % | — |
| Higher (> +10 %) | 1359 | 89.6 | 13.0 % | +30.7 SOL, mostly OLD-bot 1 SOL lots |

## 5. Exits (only as far as P&L attribution needs)
- **Every sell closes the whole position.** Hold median 34 s.
- **He sells after other sellers appear.**
  - 70 % of his sells come ≤ 1 slot after an outside sell (57 % small < 1 SOL, 13 % ≥ 1 SOL).
  - The baseline on the same tokens during his holds is 44 %.
- Rarely right after a cluster buy (52 / 7,626).
- **By hold time:**
  - Sells within 0–2 s: median +1 %.
  - Holds of 60–300 s: median +11 %.
  - Holds over 300 s are bag-holds (median −22 %, 15 % of sells), except graduations, which are the fat-tail winners.

## 6. Overlap with us (s10, our wallets on the same tape; his P&L = his lots bought within ±60 s of our buy)

| Region | Our buys | Shared episodes | First | Our P&L | His P&L |
|---|---|---|---|---|---|
| FRA | 939 | 182 (19 %) | we 100, he 77 | +4.5 SOL | **+19.0 SOL** |
| AMS | 1,089 | 183 | we 122, he 57 | +5.0 SOL | **+13.0 SOL** |

- We are usually first on these: our pre-send fills land on the dump.
- He makes 2–4× more on the same tokens. INFERRED: because he holds about 34 s and exits on seller flow, while we exit at 200 ms. His sizes are also similar or larger.

## Candidate selection rule for us — verdict
- **His selection is NOT reproducible from on-chain market data**, exactly as with haqq.
  - Within each trigger family his picks earn +3 to +7.5 % (5 s, at our entry) while look-alikes lose.
  - The best models and rules fitted to imitate him pick moments that lose.
  - Metadata (launch tool / URI, name, symbol) and copy/leader wallets do not explain it.
- **What is missing (INFERRED):**
  - The signal sits outside the tape context we can compute: off-chain token info (socials, X/Telegram calls), or a private model shared by the E2x1 + Grozoe2L pair.
  - The twin acts on the same moments within 0 slots, with the same size code.
  - Untested: trigger-wallet memory (haqq: small gain); token socials via a URI fetch (needs owner OK).
- **The only on-chain route is to follow the cluster itself.** Its real value is MEASURED from wallets that already do it (s21; net of pump fees only, PumpSwap exits not counted, so a lower bound):

| Copier | Net | Net/day | Return on SOL in | Notes |
|---|---|---|---|---|
| 4mYySb7Z | +14.6 SOL / 6.6 d | **+2.2** | 2.8 % | |
| 2QGfyorL | +26.7 SOL | +4.0 | 4.7 % | |
| Hj4uACn8 | +1.1 SOL | +0.2 | — | |
| 8T4XX, 6nH3j | — | ≈ 0 / negative | — | tiny sizes |
| E2x1 itself, same basis | | +24.3 | 5.2 % | |

  - Copying one slot behind keeps about half of his per-SOL return, and only with his exit signal.
  - **My recommendation:** a **paper test** of "buy when E2x1 or Grozoe2L buys (shred-detected, our ~20–60 ms), sell when he sells or at the first outside sell after +30 s", at 0.3 SOL. Expect about +2–4 SOL/day before tx costs. It needs the owner's OK before any live run.
  - Our existing pre-send can also **hold longer on tokens where E2x1 is in** (overlap: he +19 vs our +4.5 SOL). This needs an exit study first.

## Examples (6 per family: 3 winners + 3 losers, seeded random; GMGN token + solscan buy / closing-sell tx)
- "trigger" = biggest-impact trade in the 3 slots before him (s5); "lag" = slots / chain-clock ms to it.
- Lot P&L is gross of pump fees, trip-based. Hold = s to the closing sell (−1 = not closed in the tape).

### ADD-HOLDING
| time PKT | token | age s | trigger (3 slots before) | lag | buy SOL | lot P&L | hold s | buy tx | sell tx |
|---|---|---|---|---|---|---|---|---|---|
| 10-23 12:12:38 | [croc](https://gmgn.ai/sol/token/274EV8JCRmt4crSZC7zcTjmjJ4zRWYq418kwvPdWpump) | 53 | buy 0.53 SOL (+2%) | 0 sl / 140 ms | 0.247 | +0.0266 | 46 | [buy](https://solscan.io/tx/2TsZ4upAphjWdCeyiPSNxRD3GMBjPA3J9R9vaMRFSgfb9iHj3DWuW2Be6MqWTWZWu3CrPcZz1G5B97peF6ye4as9) | [sell](https://solscan.io/tx/2KaGGHpkfZmeXhXcuWn1fixbkgCYcrShEMRA1iGwz62swbm146DRV5XeKBtLuuCWjvDAbWFkqQMUBoXyeDHy8Mzw) |
| 10-23 03:43:34 | [kimchai](https://gmgn.ai/sol/token/AEihANkHBEVaYqQEXSCVPZb4Bc2HdBnANRa9fQXHpump) | 726 | buy 0.49 SOL (+2%) | 1 sl / 48 ms | 0.247 | +0.0060 | 1751 | [buy](https://solscan.io/tx/4v14wev2LXJvNgirRiE3bMBLFESUDycDm7Lq6DfxFesdrUmbogCUXSkcr9tFMDA4Vz34hqsbS7pJG7z714vJZTG8) | [sell](https://solscan.io/tx/3xNC8AUQ3vbpzHvCLNJgPGX1JtGk6nCMCn6Sr3iWkwtkLoE5PmXekSMq7Gq1otEJzc2AqEuHgWNxefUCafr3edsP) |
| 10-23 04:45:05 | [MARBLES](https://gmgn.ai/sol/token/46TUwfm6eT4VdBbytLsG3fhsgYqCk33dA6nt1EJPpump) | 32 | buy 0.99 SOL (+5%) | 0 sl / 49 ms | 0.247 | +0.0384 | 172 | [buy](https://solscan.io/tx/388YoB4RKz1RD4b46s2gmQ6Fg7r6myvSG8MJwo8cuAm9h7yzv9NHhigywd1QxQH2UBWNAkKiurA2oFjZspRAdJ8Q) | [sell](https://solscan.io/tx/3Ue6zCCFqiXrkFWV4uSxTfELGsrquZfrMeLtDovPYszQw1uSi5LJyeRwVxqjNPE9WERE9MpVuD8a6YURu49Bsneg) |
| 10-23 10:22:26 | [PETECOOPER](https://gmgn.ai/sol/token/283wmFkVaJRpKgKWV1bY78nth4SUraJ45tUZzjNTpump) | 1502 | sell 1.22 SOL (-5%) | 0 sl / 26 ms | 0.247 | -0.0625 | 45 | [buy](https://solscan.io/tx/qkD1PjHC3gmb3g4dQq9udrwX8bxT3Px8epiDZqVh9ZDjcS5d8MwJRrmsgvMDSqajMuuArsYRCxDuyAZiLLt1EJH) | [sell](https://solscan.io/tx/4SCSwAy4CMyrfPgfgXeTtmSPGxJbZXKhffkQS9AsXkR9Pb6u99FSuAYYEwEpqKHoBw1gzCH71NYGvVgnzEYD3mCh) |
| 10-22 12:32:40 | [ ](https://gmgn.ai/sol/token/273QZuN6Pvv3My9EeAiNyQTQsMALhkzXhSerHEyepump) | 300 | buy 1.28 SOL (+5%) | 0 sl / 49 ms | 0.247 | -0.0313 | 34 | [buy](https://solscan.io/tx/5kW3BVrNAnv4raTWRxA7Rs165eQcfoxbojrZcBUbtMhEu9GyxRQDGDxNyL4xSfw9XaxPmsKtX7EArVnMuxYr4LfL) | [sell](https://solscan.io/tx/5AA9EREuJou15QhwN3TkLxyWX9KyChHVDifvvPjPyDPasErs2KJYnnpLDAgz4hop35dHkSKxyT4Cbqm4yC3ocNMz) |
| 10-23 07:21:11 | [salvage](https://gmgn.ai/sol/token/32jysFW2noAnZNVEXyf176SsBJJdsmN51Anjqozdpump) | 131 | buy 0.30 SOL (+1%) | 0 sl / 30 ms | 0.247 | -0.0061 | 263 | [buy](https://solscan.io/tx/MYuTamPRNLoYnFd4bfMcYmRLAVJpBrq3S5BtZtKqHQtdL9aLxEYAWWiafKnYNZ6D7ybuXtuEBmGe5DAjeMmeRwh) | [sell](https://solscan.io/tx/3Z8DzcPbnCtFNznoM4Wky6kj4DfWZfX5MfXYAU98D7rHeEWYdsw8wabfTYarBc1yeD3sBngvEtNbqckZeSab6Ec6) |

### EARLY-DIP
| time PKT | token | age s | trigger (3 slots before) | lag | buy SOL | lot P&L | hold s | buy tx | sell tx |
|---|---|---|---|---|---|---|---|---|---|
| 10-27 23:01:07 | [BUY](https://gmgn.ai/sol/token/7KbkEbLiNBLwpDi315bYGt6UiFdMPtVzt3UY6XAxpump) | 30 | sell 4.73 SOL (-14%) | 1 sl / 183 ms | 0.402 | +0.0692 | 0 | [buy](https://solscan.io/tx/T8rhNreDHHuMPqcKvsPuG3tEAJG1urBG34kV8atbm8TDQfHMgMSc8AUtXpntkGHwAHANsRbiEWaemp49L8agSFN) | [sell](https://solscan.io/tx/3bqhiqBXAtMLJdXvwxJDHG1BeeF327h1wBto5qPSLeVtx4N8qSzkHQ8ARkXuypdPfj88C9sKwcgnFTynYRMxf5vR) |
| 10-28 03:44:07 | [SHOGGOTH](https://gmgn.ai/sol/token/G3B1EL3pQqUew4VogGdTCv9GteusaGHh5WrsSeaFKd7s) | 26 | sell 4.16 SOL (-11%) | 0 sl / 66 ms | 0.451 | +0.1866 | 17 | [buy](https://solscan.io/tx/471SmTAR73CqCFDrES99fV9JHwZAN4BN5f9mseXw43We8Fq1WZkEA61K2qGVcKyF21imjUB8W4w6kcH6JL5d6ngF) | [sell](https://solscan.io/tx/5LLNQzvregW3X9HtadKx4Ju6KNPgMzL8H6PDG8S17VZoP8vrZ3QPmPSURvfjuDjxQwTgRycBSDeFEFmtmp3xryqt) |
| 10-24 02:13:06 | [PoR](https://gmgn.ai/sol/token/8VHjFaHJm9RxJNhGHvd1B2bZ4pyxZrDjMYMNstU4pump) | 10 | sell 5.86 SOL (-25%) | 1 sl / 8 ms | 0.296 | +0.0680 | 218 | [buy](https://solscan.io/tx/4tqrMSuoUXe1yFNdAhgqWr7nGTSMUndgfF1qKoeNKbDYrY6Pqd5C4syTCqHkbtDFTjVLGr6G3G7YeFxajbFomeNQ) | [sell](https://solscan.io/tx/4AQmdBrKWrzCwmYfqw1joX2U6LHSCQimdz96mMX4e7NxoYv3a3EbwngGAp5ZFqHytPTTYj2sJEe49tLrg3kYmY12) |
| 10-23 00:28:32 | [FOMO](https://gmgn.ai/sol/token/94j9jcDamFeouZxfQaTH2RpVfMqmd7qXsK7B9BwZpump) | 23 | sell 2.12 SOL (-9%) | 0 sl / 39 ms | 0.247 | -0.1133 | 4 | [buy](https://solscan.io/tx/2U3FSgQGXJvVN5VeNDLKfyRBvt7WFS8dhfNDUTLMsqCmQpVzqo4c1MKtpcwYUWS3dttZKzEZQMei3XjyBFmtZKs4) | [sell](https://solscan.io/tx/3uiXYtmHCkyJw34q28ja6kCRDFjMfnYCV3eTKkuEhveTkZqp98S1peW73ZEXGEpShjyjoUcHZCvkNY48mnQMvvsP) |
| 10-27 17:18:46 | [MINGMING](https://gmgn.ai/sol/token/7u8p3eymTVS9hyFeCWZbDNcQkKVzMMcUjSFXnhJXpump) | 34 | sell 3.24 SOL (-15%) | 1 sl / 120 ms | 0.395 | -0.0209 | 58 | [buy](https://solscan.io/tx/4MjuFMfAvBdw2Bt9RfWbMa9hCMBXPqwjM5Uqq6z2QqS6CRNrFzBe5B14zKUVpNPY7NBR7R8H33Lbb2u9o45SvG4a) | [sell](https://solscan.io/tx/3szdt8qaiLBXFTRtogSFSqK29AZGXMhnvnaFfoh5NvAm474tYK79vRYibcsbT2HikADrShZHwHRjNTaKB3vokttU) |
| 10-27 21:01:06 | [Wealth](https://gmgn.ai/sol/token/Ah348T1X2kezHikedyTpnMEZjNohWPZGC645ZR6Apump) | 44 | sell 1.41 SOL (-7%) | 0 sl / 34 ms | 0.352 | -0.1155 | 531 | [buy](https://solscan.io/tx/4RK6aznMqsegRyVeRvvaQ3BVhdEtXYRyH1Yj2UN3r9Fg6LtxrEcvLYr3zYQho8KjdXWRkaGLzxQN9ebhq6cMhen2) | [sell](https://solscan.io/tx/48qe1ZN1ZN1wCuLSD3VMJGzUAtXp8GEH9dQqDefJzaTfidsctBocKw7krxr4gG7uKMssm4hCcNxgLEg47vxq1jeX) |

### EARLY-FLOW
| time PKT | token | age s | trigger (3 slots before) | lag | buy SOL | lot P&L | hold s | buy tx | sell tx |
|---|---|---|---|---|---|---|---|---|---|
| 10-24 11:28:24 | [HoweyCoins](https://gmgn.ai/sol/token/7RjDr1QjV3GdiwufDwh7PRDeByZ6tV4kaFLbhh4dpump) | 19 | sell 0.26 SOL (-1%) | 1 sl / 106 ms | 0.296 | +0.0194 | 33 | [buy](https://solscan.io/tx/SSEhFKGg94cLM3gckQMN2nBk6eQgk4JnDFsz3B9M7LkCZ7bL7vRMdpQKSpT5CMyf12QUtMJYmpawqRgfx9cdHUS) | [sell](https://solscan.io/tx/3mjLSfgP6kuSSNPZcM1Az4oYifzK7iSn4rA6Q3DV5uJ1SVaboez7cWBcerNFknJ7p1sZAbpzWj4TwmLE8eJyjPVc) |
| 10-24 05:26:43 | [Jaxo](https://gmgn.ai/sol/token/peobd6CK8TvGBqLadDg64ZJhPyTumZgH7KJYHkzpump) | 18 | sell 0.71 SOL (-2%) | 1 sl / 168 ms | 0.296 | +0.0432 | 3 | [buy](https://solscan.io/tx/3YUjR9QpCg7cSWNg6nywM8E5A21BJ5tiTY43FLVRSpZ8WxZgn3M5tfXdhRUEGpw3oz8eLUQTj72nq52XJaBhJcDu) | [sell](https://solscan.io/tx/4ox2eV86Z8gG11WCpFUf4How2m4tJyBxhrPm6XGABx6dRH6NFMFxJDyrkohqs1eugJWuitWPip9SGHCuLyLFThmc) |
| 10-27 10:51:58 | [PILOT ](https://gmgn.ai/sol/token/HSz8Lhz4RCzFHdqZ7Nm7S15CYUvGiuv1pRPopVowpump) | 38 | buy 0.35 SOL (+2%) | 1 sl / 108 ms | 0.330 | +0.0325 | 145 | [buy](https://solscan.io/tx/3v7x3PBbB3SsZegmstnRmpz9smXA6pYLdYWhZGsw1ygHvZMfMj2B6vHTWAB4A87g8LuBmLXZpQzbusyqp1A24uEc) | [sell](https://solscan.io/tx/Ff1WVVi7QpSTj7i2gQuMQAb5oarpb16KbzbJYWFhhh93eVficHNbJ6AuaCtDMTWbNk3mqJB6KMJyHEhutJZe94H) |
| 10-23 22:31:26 | [LQT](https://gmgn.ai/sol/token/HtkfyU6m7BDJzi4HThsHAxmsmKRSQgX7nTWuYpC4aqBZ) | 20 | buy 0.55 SOL (+3%) | 0 sl / 98 ms | 0.296 | -0.0114 | 27 | [buy](https://solscan.io/tx/4xbcwFkhSgoazXsofyp9PqG3BKpTT6gSTJ5F5wpmvWcabsveduHuNcDrTwxLmdAs7LQqVCPrkNugKzyfLUnS4y4M) | [sell](https://solscan.io/tx/Qzr2RZiBA3cLBFEKJaCyCPB9WbfP4SaE5H1PTKvmTFm9wfSvFuRDRvbMP7XrwFWUQbo6irfaEPD1S9qy7tWwRza) |
| 10-25 05:15:26 | [Patch](https://gmgn.ai/sol/token/Fy475G7wisa2rteMtakauYyuAqVZ5eny9By3f8iPpump) | 71 | buy 0.01 SOL (+0%) | 0 sl / 42 ms | 0.386 | -0.0530 | 210 | [buy](https://solscan.io/tx/h6BvAFoqSCnkacvGcu3xg4bqP6sPWhkdoWasiesYHs8T56Sud8r81tC393nAAF9iebP4G17brbWjzpv9CsUPuev) | [sell](https://solscan.io/tx/5XB5eivTNkpsn1z1r8tRkDs6B8w4xjoxjqtGrWQyFbE4rNVXTexRutsKiMauww7zvFxqLShEuqcMq5Rq6VcQiyTK) |
| 10-28 16:39:19 | [KOHLER](https://gmgn.ai/sol/token/BCMfJ7hpon5zWwXxf9Yv4gCC9x38jLxiEo5fRYvtpump) | 74 | buy 0.02 SOL (+0%) | 3 sl / 626 ms | 0.440 | -0.2335 | 2 | [buy](https://solscan.io/tx/UjrWmky9eoiusvPs42JxwjMuDPEEYowjyKALom1eNowhjFvuxNPZ3UFTdG8MTbgzJfz1K7P67b8f9s6yJBXoG2b) | [sell](https://solscan.io/tx/32cncohjZNxJhf3S3rRShKXWRMttAtDFFxELdr2NAkv3LBwFRbgZTsnQbKGz9PLQdR8odt6rVA56vmSzZZBLiqLd) |

### EARLY-RIP
| time PKT | token | age s | trigger (3 slots before) | lag | buy SOL | lot P&L | hold s | buy tx | sell tx |
|---|---|---|---|---|---|---|---|---|---|
| 10-26 07:49:28 | [pumpfun](https://gmgn.ai/sol/token/3SmKitXBbLKJBwoVECssNCL3fXokGfvvr21LyGnqpump) | 34 | buy 0.96 SOL (+6%) | 0 sl / 88 ms | 0.353 | +0.3983 | 152 | [buy](https://solscan.io/tx/4qZLkh164AUXgVWtDp9nLzE2MrK3Q2BRwPWJQQYoMU3KmLoUXBY6WWofwZn5aY8W3EE9AokncsT8sGD3r8pCSs8o) | [sell](https://solscan.io/tx/5yQHTN6FUmwufEDukEvkWeXqww1qvgBpVXeGosCSfUvS9AdGzPTYsLSNQK9g1hVwXJ3Wqg7FGqcU6tjkUpCdDvdi) |
| 10-26 01:55:53 | [Hou](https://gmgn.ai/sol/token/21wBPdpTzvFZv6ADr1pkyNJSg7vZepAF9KTZg3jypump) | 22 | buy 1.47 SOL (+7%) | 1 sl / 119 ms | 0.306 | +0.0160 | 22 | [buy](https://solscan.io/tx/2fPDG2p1sPJoWV8vAtd3PpNhYdsUf4bu8VUGzhYwxnrwLDiozcEHKUz6wm8ic3aSRngG7XP59Wcpcfep8kFsBokT) | [sell](https://solscan.io/tx/2gzPdif3sYJ9dyt7RhH5SVRnMz5i1P8gTawW3QrVEkh2SpKEbRz3evJcrjDG2QAJZxSDe4pHv1j5JrDmQcNE2cHc) |
| 10-25 11:36:08 | [420](https://gmgn.ai/sol/token/7fMU88S4P9zwXfYdWZY1mpwp8RyojFm5Lfv2pCYBpump) | 20 | buy 1.98 SOL (+8%) | 0 sl / 151 ms | 0.296 | +0.0221 | 13 | [buy](https://solscan.io/tx/CwSsaCcw6Uw9rPkwZ5mKNsAGnzSq9pjDbu64NgoPkTWox5sME2A32BiNS71TFMyCfjphMNmEFmy7tmNceApzsSS) | [sell](https://solscan.io/tx/4GwKDFff7zoSoRLc56i63gcoA26p65a3HZuxppF5LVgTw8i7ydhBqkwg6PWcjpCuy2LyF9txtjjodC7YsoPjgqKx) |
| 10-27 13:54:55 | [LIGHTSOUT](https://gmgn.ai/sol/token/3R6WtTHKAo13ps8FFJCuJjCFe3iAqSAFC2d7d5C3pump) | 51 | buy 2.19 SOL (+12%) | 1 sl / 251 ms | 0.386 | -0.0408 | 5 | [buy](https://solscan.io/tx/3zXnng3K2SSYd9wS2tUxys3TDz5NXUG4Bja9H2F9ZDxe28Yj852enwGWMauznYP1wHWkQP18HPf6SFooieGmoD6j) | [sell](https://solscan.io/tx/4YnUza5BjrKN8dBDKYU6L4vrGaJT5dgA5Tb2cyteDZzYpMtb25new65XSwajcNf8iyMeKE6VHgH95FyrCgSmAPXM) |
| 10-26 17:18:59 | [DANDY](https://gmgn.ai/sol/token/By2QspwGkKaNSSpZC2rpEvoDuRqHHdXQo7Av16vzaHPU) | 67 | buy 1.07 SOL (+6%) | 0 sl / 129 ms | 0.607 | -0.0716 | 14 | [buy](https://solscan.io/tx/3kAnyZmyGU3hDxdodAJ2XhveEGjXo2cQEnCyLtsZwUS69YpTR3FdUed9TR55oK5f91yDBQ1RvrfG239DFoZqKgw5) | [sell](https://solscan.io/tx/5QkxiBuDAAd2shZEKYTyL7DTg7SuhMP1oFsSSUgsbg1NzBqvM9GXdLUBhFfDtWvjDGoTjWnszASegwx9xBFQn1bN) |
| 10-27 00:16:55 | [DeepHat](https://gmgn.ai/sol/token/3oKLNdom7Jkpga5qetSP4xjgULwVdwYQmhr89e7Zpump) | 12 | buy 1.40 SOL (+9%) | 0 sl / 56 ms | 0.438 | -0.0576 | 10 | [buy](https://solscan.io/tx/yQisCpvWF61ekHfDD7r9PHviqXe3pwvQ2bRajmCsr5AYADqfteXtcosVT46NiQb9BHSzKkDojUMsKhoxvXfGv6y) | [sell](https://solscan.io/tx/4xJwx89LwhWzdYCiBXWbeMLw3FSmYSkZc7jpZZZ5pBhRd2rDJzFiWHdKAfpc3j9KR6cfLCZfby39ptmKS2NUhGvV) |

### LATE-DIP
| time PKT | token | age s | trigger (3 slots before) | lag | buy SOL | lot P&L | hold s | buy tx | sell tx |
|---|---|---|---|---|---|---|---|---|---|
| 10-27 17:24:28 | [MINGMING](https://gmgn.ai/sol/token/485gMDZzozxPxNEbKMCZVRmGvmSHqE79Y3vfaZBNpump) | 332 | sell 1.28 SOL (-6%) | 1 sl / 273 ms | 0.988 | +0.3522 | 81 | [buy](https://solscan.io/tx/5hrmdwxakHrrBrE1rzHYaCJBXPWU3aB1rwiu5ynWwTsRvxDZkXDLVAnE75vXtAQ2Pd1JJfph7E86iBAkfTGovJ3a) | [sell](https://solscan.io/tx/2PGcvdNVTyYGxDEbBcmTRv4JCL7gZxKWLmDyczAtMUnVPULaoLy6yB39mb4SnPP89VukRwihCcZj5V2Smm6kwGp4) |
| 10-23 06:32:38 | [cb](https://gmgn.ai/sol/token/9sXzh7SxN77Ko8p5DrsgTXTRMsqBKxQo64qSKQf6pump) | 133 | sell 3.69 SOL (-13%) | 1 sl / 198 ms | 0.247 | +0.1099 | 19 | [buy](https://solscan.io/tx/3L8vMye1Q5SgjkQuR7SJeJfGhpzAxds2gefpnZvAuLMYnXdgKMw3SGwRQGpQTBbqJNza7sQqtJqqCVinSjBxxQVp) | [sell](https://solscan.io/tx/4mfQV1SzGahr9uYdiv3DoYpgJjvdid7YrxLAC5dpQR2XLueHHFez7keEUiTZpfmeSxzRVaXuuVweW4HYBwxyodBa) |
| 10-24 16:09:42 | [Tstache](https://gmgn.ai/sol/token/4ncMDZy5cGqEQ6QjSgReCTcyKXMphcrjDWW9eztWpump) | 311 | sell 4.49 SOL (-22%) | 0 sl / 160 ms | 0.404 | +0.0299 | 11 | [buy](https://solscan.io/tx/4roJZXcNGUL35sdtp3izt4QSWZPosJtvV6YsfnmgqLMuyPBHq9N4PRzQEYCvBLwvf16YyYMwGr5gQtoVBzNV1Y7j) | [sell](https://solscan.io/tx/28XGgoneuhokxyxzJBWBrvvp2TBSzXLupCbDLSxPZZPqZ92hhWJUEnYEZDrkyHouvSuRFe3kVtZRiudrJ2jHZYao) |
| 10-22 08:50:50 | [BO](https://gmgn.ai/sol/token/91V1DmzapiK2mEEhdBeWepZoGbb1zQ79H8b7rgxwjJ8W) | 183 | sell 0.93 SOL (-5%) | 0 sl / 98 ms | 0.247 | -0.0401 | 1800 | [buy](https://solscan.io/tx/GraeNDyHEsGU5PRbVjqDDRrgqVQpNVamJ7SUV4aD49eRyz3HVUJepCWCVXZqse55nFHQNB7YqUcnQYBPfKf6cF3) | [sell](https://solscan.io/tx/nvXsvneofG8AfjZ5Gpc7zXqRb3YtfWuCSj6XANqWhXgjb6WcVmeLaYFZoHmwH9UAsfok4ZeJJ6jp6hLd28SBSMw) |
| 10-25 23:51:56 | [SatRush](https://gmgn.ai/sol/token/CoYRC8vvPfLEfXHQ9zoDbxxWRaYuAQ9WU89WJXXHpump) | 1286 | sell 3.30 SOL (-18%) | 0 sl / 141 ms | 0.233 | -0.0178 | 118 | [buy](https://solscan.io/tx/2vzyfJTNX2Q2gb245F6ehfaCXobbB5MYetkCmd8GJvECGWJojaA834pUunkhmjbJkSquXteL3v5UC9xUCH4rXz9Q) | [sell](https://solscan.io/tx/LXL7Qsh7pDYeCmUwY19pna4ptpQNfiKmCt4WSDhGkSUTehovyTz5CT4oBfkZ1uAk8BVUvk48ejd53sTeGinVY87) |
| 10-22 10:01:34 | [fartless](https://gmgn.ai/sol/token/7TA3x4JrrC7bsnBTnWkMvws5CJL8dQ1tEtKW7DDHpump) | 528 | sell 1.27 SOL (-7%) | 1 sl / 144 ms | 0.247 | -0.0450 | 1800 | [buy](https://solscan.io/tx/4hxfjg2Z9vdpAR9uZiFwQ5ES3S7D5sEY9mqTwUkDhd8TWYnby7wgXHiYa1Sh4Hb82pYU5CkhXYjrwFmWmj738enc) | [sell](https://solscan.io/tx/4j8TrBhaUTqHWEfvuzwhPYvMQa6cJ4PPedgVtRHDsoHcdQXCkzUjMTbPW5b7mk8npwGpB2Uzp3nWMDLeAPXaQtij) |

### LATE-FLOW
| time PKT | token | age s | trigger (3 slots before) | lag | buy SOL | lot P&L | hold s | buy tx | sell tx |
|---|---|---|---|---|---|---|---|---|---|
| 10-23 12:12:35 | [Rosalind](https://gmgn.ai/sol/token/4eWHVRRUMA4YxfoYrFWbkctU13zdnzbqqJ3hXWyLpump) | 4877 | buy 0.92 SOL (+4%) | 0 sl / 63 ms | 0.247 | +0.0087 | 161 | [buy](https://solscan.io/tx/5WejyAq86v9wCMJN3VeGKyuxhSc1Q5Dr9S7aRFJdhBLgwSJJqcjiEoKuqwbdR56zH4SM62e5mFzti4W2JRbE3shD) | [sell](https://solscan.io/tx/YRqv49BFiKcxufMBzQGQeCmE1kaiddBVeH18QyDNnhBpvGnFgVcKYHdDXujBKm5ekjKd4LdWUVj6A8jMzfYYZpR) |
| 10-28 14:19:40 | [KIT](https://gmgn.ai/sol/token/HhDLhdM1CozLjr2yfsjDK7H58EewyCprWRkwbCxCgk7w) | 149 | buy 0.27 SOL (+1%) | 0 sl / 26 ms | 0.477 | +0.5555 | 189 | [buy](https://solscan.io/tx/DoWiid2SdgeSVR4mUo7PD2jjZYjY35yT8WWrAECKazxRv4vXwcU6vWv1r8QPiyjAjYtDrMoSWfBXSDYtW2nqQPT) | [sell](https://solscan.io/tx/2mbUqFqehMs9K6mDi64c4wdkVR4xbx7k3fF6hvoSUrHLJf6GaroP3ExVwxmXJZiCKrWjfbqVcnHbqKGGWaibRjDe) |
| 10-25 17:27:02 | [민수](https://gmgn.ai/sol/token/UWyjbgh65Mk2VvGN5TtvtCb1uvGwarjc8VbACx1pump) | 147 | sell 0.15 SOL (-1%) | 0 sl / 34 ms | 0.296 | +0.0954 | 54 | [buy](https://solscan.io/tx/4BUiVgwNLwY1ZjwENEjZmWAsDCERppADcUJjG8JXvA6YAyvS62i7PRTguEH6mehkG4xpH62YLJSYBsGpuW6eahjF) | [sell](https://solscan.io/tx/2kKsd7hzcHxEayhdozK29RSQqfcrUP79z4KdvasVfhBBJVFRcG1awbu2BqVsFcoJAkVPqDgzfgUQKMSk7omVCLq8) |
| 10-28 02:00:02 | [Chungus](https://gmgn.ai/sol/token/6xC31cak7HnFsoaez9U3ELowUWMT589k2eh9wj3ypump) | 685 | sell 0.41 SOL (-1%) | 0 sl / 30 ms | 0.988 | -0.2220 | 160 | [buy](https://solscan.io/tx/218MWDEVr6y8HVGS7evFmNNP9vqjqLV64iB4EEMeQLFF2QfxRFy7czLL9e87pXZGdXK3eDCp5ajh31xueQD5N79Y) | [sell](https://solscan.io/tx/ccguggMXMoCw754pfFrpex62sxtpcd33aFcNYkGaiRQoNuSVxixhXJevEiATUrfv1Wxj5bemea3BpmnJYwqHurU) |
| 10-26 08:36:11 | [EASY](https://gmgn.ai/sol/token/A7NvjiHogu2ed533XRJzHLzd1YxNe1oW65Q6JPKhpump) | 188 | sell 0.98 SOL (-4%) | 0 sl / 37 ms | 0.988 | -0.3025 | 63 | [buy](https://solscan.io/tx/5EqPQJL9KNzcPwdqrY5gde6FLbPdZPP8wqiUB9r9Z8w7e6uKQP9B6ooin8ew63SgtoUBweMQv7TowtqtZCZBFdBa) | [sell](https://solscan.io/tx/4GM8BpnHCK8rg8xvpdckZtngpmTVHrudiiMSDSdFCuGhHHnAEgRGd4VL3sXHKdB6hWhqDuvk5BEPyhbCLzEG3XCm) |
| 10-27 19:47:51 | [KOTH](https://gmgn.ai/sol/token/3i9KN4Y4G92sXWryovuLnJ9VzLfzojwSBVRuRwf5SEVh) | 357 | buy 0.74 SOL (+4%) | 1 sl / 42 ms | 0.399 | -0.0526 | 272 | [buy](https://solscan.io/tx/4oBqQQKMWYh6XBPEHQ2i7QnYZeNaUckHeDgDZu5VFw4J1dBbNEMKweM7ipTsw92sQgADHjDnyo7PJSDW3XGhbA1P) | [sell](https://solscan.io/tx/5KHHncAZRYmjw2NKxgAYJMMJoCD1N9QFw8MMegvioZKQrc1mmFBCf8HbuSmGAVZwnXEjY2jrYz1qYQ9vuWhMnuvp) |

### LATE-RIP
| time PKT | token | age s | trigger (3 slots before) | lag | buy SOL | lot P&L | hold s | buy tx | sell tx |
|---|---|---|---|---|---|---|---|---|---|
| 10-24 01:41:59 | [simulator](https://gmgn.ai/sol/token/7dSNW3s4jWKg3wfMwmA26qr4QGDJ6vzFKMHsqwRipump) | 379 | buy 1.04 SOL (+6%) | 1 sl / 94 ms | 0.296 | +0.0323 | 81 | [buy](https://solscan.io/tx/4qzvMN7V8P6WDZVgpRA2EAnCMiEgDp79D3xogyyKnyVVSGnzeu9kQtMMRmnwCxNWpYJ6eQzrL154YJsGTEEwfZpr) | [sell](https://solscan.io/tx/2sPJixyA4N8jymEfgTki8e4ZHYmCXsbQhf2YAhQuuqvx3VVJnGe7keW3vq3fXHteN88TxqTt9FnJLFUDedLhwWMX) |
| 10-24 13:15:37 | [dylan](https://gmgn.ai/sol/token/Dg1pVJvU1GP2p4FUbqxQnEvZpy87BgDxQYsbt6nTpump) | 414 | buy 0.88 SOL (+5%) | 1 sl / 108 ms | 0.296 | +0.0262 | 5 | [buy](https://solscan.io/tx/4UZ3HDx1BYZRiCbkG24wqmf75uYbhdoCi39fy4PT2SLUcaFU8JofC7hJqyLT8UpqdyQ3d1d8Age5M9V7ryfnggwe) | [sell](https://solscan.io/tx/5UfUHCMNcViPMwndM7A7BJ3LK4Gk68Aaiwth1tZB4YNp67N2jarm6o8QARyUE6jrb5wBiH596zXatQGXEyyWzo2Z) |
| 10-23 16:04:36 | [F&T](https://gmgn.ai/sol/token/7V8fZNzjESEqHHadksFSzTocf9EShYLTQaDpHi8Vpump) | 565 | buy 0.98 SOL (+6%) | 0 sl / 86 ms | 0.247 | +0.0419 | 20 | [buy](https://solscan.io/tx/Gwrs5ttWsme9fmBfuWXDKE81KrXt3xLuutzNC5hs5wuWKD65MXLDtr9hPiYruntY1fNwaMqRFu1LJTGpDhSX5D1) | [sell](https://solscan.io/tx/3pnPWW2GShnMoBF4dPMwwWWBbVYk3LciX22MomSaHAFLnEvGcFFjEXNkAiEeyKBeVTJAkcBi8NdKh1hv39Ln6Tyx) |
| 10-22 03:23:22 | [RYAN](https://gmgn.ai/sol/token/H5QyN66aA623xyk1dzYrbkqGFYvDRVvTNLL7HFB7pump) | 149 | buy 9.13 SOL (+35%) | 0 sl / 31 ms | 0.247 | -0.1430 | 33 | [buy](https://solscan.io/tx/4qVoCoDos9yZXy9mXjPh8VRoQcrzRDppeuvZyVug7fAMga5jTJMLcXyCwjBx69yfmtPbmzk5hoZD1aoy2shjAZiq) | [sell](https://solscan.io/tx/5wxueJ2n6FBvUKneRGF7x9AXL1o3gPWSQnKbn1aTkakL3DoHDtq4rP7EGi9L8vM1qq8DufoPF9GjYgjKcn2BPW3M) |
| 10-22 10:58:02 | [afk](https://gmgn.ai/sol/token/4yGRjWjRQ7zfeZ4BCuEFiXScsCEhu1P5RwUBwAPdpump) | 252 | buy 4.92 SOL (+11%) | 0 sl / 85 ms | 0.247 | -0.0642 | 73 | [buy](https://solscan.io/tx/NsRLFYrJqRSNWjg5b6ejC9ZUQ1HQrTYmcaQDhnARLJ4SvYBWrc3ecDKSSdJchK3Lcx5aXV1mztAdsRgMeS6Tbqc) | [sell](https://solscan.io/tx/5Fag7cNuyhTHiFmPPcksVHV4GAwpy1HmzX9hZNvSCk7XTwAaYESDzZn5xpaLrNkpoMLkADLAj3WsSngcgwbTD9hQ) |
| 10-23 06:38:35 | [SNEP](https://gmgn.ai/sol/token/Hgo2mHzxeMNpW4c4rjferHDkj3E8LEuJ6eLtxtXpump) | 3371 | buy 1.00 SOL (+6%) | 1 sl / 145 ms | 0.247 | -0.0563 | 1800 | [buy](https://solscan.io/tx/462yogHuywqx6aTymojWiN3GrRqgd8PL6RohRc1KNHZce5AZg3fjuh4dha9UXu9YY727d8wdrUr6pcmU7hGxtHJj) | [sell](https://solscan.io/tx/5RWJFxt4tt6nuCrkuXka5hbgFDCjXUnTMSgccZtDdYJ9rNbfhoPVV7FyiLgEzepbkdMMTztBS2a45LymUmB8dZ8d) |

### LAUNCH-DIP
| time PKT | token | age s | trigger (3 slots before) | lag | buy SOL | lot P&L | hold s | buy tx | sell tx |
|---|---|---|---|---|---|---|---|---|---|
| 10-27 00:08:18 | [promote](https://gmgn.ai/sol/token/2BzgiyPYArWFXwyqwewpXWH7eFzcT48o98AUDkwUpump) | 5 | sell 1.64 SOL (-9%) | 0 sl / 66 ms | 0.233 | +0.0950 | 96 | [buy](https://solscan.io/tx/3meiNwXJRHQVtfBmKVAGRZsVKC4s4G58bKSb6Qnr15ALSf5yGLHcSsEvYNhe6Mc4hNnjXzcnkE31s7AG7SV3Bw9s) | [sell](https://solscan.io/tx/3u5e3EiDqbE3m3j7fixXkY9M12JBpC4h7naDCapWaiPm1dtFnBh9RrvEGHzLaXJHPAvVEzP7stMjFmXA32nqFKkx) |
| 10-28 02:00:52 | [4](https://gmgn.ai/sol/token/5UDrgx9iJtTq2QyfNvfeRxtcL8bFF8T1A2e6LhpMFg8u) | 2 | sell 4.58 SOL (-24%) | 1 sl / 62 ms | 0.215 | +0.0021 | 0 | [buy](https://solscan.io/tx/3hFYP7ow3xv7Ujvo6XD6ptcJsgWsDaGaLyAFwRPRNH88ZYPzUPrnyAeXKBijTtU2dwbRcBRnRLsgMfftAe4qkxm3) | [sell](https://solscan.io/tx/3w59P3Pe6cpcrFW6fUqD9xmbpKKq2Fc8tmPyCD5BDCyhf8rYRixZXfjJvuN2VYBtzSNthNoEjstpwS7ZwtCPMTB2) |
| 10-23 13:11:18 | [GABRIELA](https://gmgn.ai/sol/token/81yE5oA4bE4iuShVGajX5EUfAqvULZr1SmZvMVhvpump) | 3 | sell 1.39 SOL (-7%) | 2 sl / 428 ms | 0.247 | +0.0293 | 221 | [buy](https://solscan.io/tx/2a8ddk5BhDHWM9kSyMToewrK7vBuTuq8eUt49Ujnp5xkEwhn8uNRemW4V34eTLZeGQcfwMaEXkjngdruKTPJnAsR) | [sell](https://solscan.io/tx/5bHeqnAtqccrnWo8X9TmBeZ4EBjQQJDapo3CRNNZUdF8cPNAWAEFgRst7ij5Fb3xp9LECsneAnxNcJRpGGAoqCn3) |
| 10-27 16:45:57 | [NeoClouds](https://gmgn.ai/sol/token/4B9Y4B3UxQLraeUv2Tgiiq9V6h9pZMXb3fv6adxspump) | 5 | sell 1.48 SOL (-8%) | 3 sl / 653 ms | 0.240 | -0.0618 | 1800 | [buy](https://solscan.io/tx/3yQk7dCKu4PTNN8WK4No3ro5HfbeKmgFyHAA9gLM5RE1UCmuAhVdzTdjqqPtZ4CtiRzPQXpk9G3QV9ZrEJEyAeqr) | [sell](https://solscan.io/tx/3rpizYjffHpM48K8zteSmnVWiCDdmFxhF6JDJWhD8qRrnbRCiryhYGy3CgNXqA9hkavmVEvB47wJN37W7Z6DjVfE) |
| 10-22 03:28:47 | [CI](https://gmgn.ai/sol/token/9kX1YM5ZSJwajjggkv8VQHXZE2ApeP7U6QCvEaqapump) | 3 | sell 5.05 SOL (-17%) | 3 sl / 776 ms | 0.247 | -0.0943 | 20 | [buy](https://solscan.io/tx/525RXCAKbuXDpMMvcHeMDxxaN6XuCLSp9RaHinpxLw5cXmub2F9hhhZ569GHgNA6ihHVH8QLmzNGKr8qBDHhoxow) | [sell](https://solscan.io/tx/5CTm2FhryHG6Q6xZBoZWHgEPUT2peK9Wv8tKaRvv7ChHgAwRV1m4d489hwsKpEahQbkhuu7S9E4xeSw5HHeQVFYX) |
| 10-26 09:06:31 | [Oscar](https://gmgn.ai/sol/token/XgAXjF8MLfHZdWdvRB4QWW1hJWFoz1JpKri4JQJpump) | 9 | sell 2.48 SOL (-8%) | 1 sl / 63 ms | 0.388 | -0.1287 | 29 | [buy](https://solscan.io/tx/19aHFCYJ1ECXgGQc9HL41KNefLcGSR8e1c4Q1oNuDfY9kvYNV5VZCvReC5gcmbkhoN5TDSZebjdH4Jeie7RoXf9) | [sell](https://solscan.io/tx/4KTX1aqPbqwvJ4RdrZr13MNDfgW8xibxLLQLo8QaYsYAKdEzYkfotWL7ppSXMcRo6nmneLBTQMNpL2MGqZnGwKgn) |

### LAUNCH-FLOW
| time PKT | token | age s | trigger (3 slots before) | lag | buy SOL | lot P&L | hold s | buy tx | sell tx |
|---|---|---|---|---|---|---|---|---|---|
| 10-23 17:35:36 | [CHAMPCHI](https://gmgn.ai/sol/token/2TSpHfN4qctpcisVkSh2kFGPidLPovwS4uwCDtadpump) | 3 | buy 0.69 SOL (+1%) | 0 sl / 1 ms | 0.296 | +0.0495 | 19 | [buy](https://solscan.io/tx/49iX1C2WXSnbtT1DafH1uhj2TfLSQNwRCx6kftEPMQiaTYfh6hWd4hsDr5DpLGceBDNPGEm7H4PZTsz8PU4d18Pw) | [sell](https://solscan.io/tx/4HP5wDUrvUjsXjJhRY316DZjNzTemhYLJYcTLX6ZoGiU3qz8rqRLTiCmoahcXHeH25a3BPK9HDjG9JYmBWNKPTwn) |
| 10-25 20:32:41 | [BLUEBALLS](https://gmgn.ai/sol/token/6ntvzCspQAEzYZQZuLRMEZqtCyfXrxk187i8nPjPpump) | 7 | buy 0.51 SOL (+3%) | 3 sl / 602 ms | 0.258 | +0.2296 | 112 | [buy](https://solscan.io/tx/4R7S8Gv5VX1rhWCLjSsjyRTk5wKKuKjV9XTpMnhFK34YsfZyzoXZxAEucWPspc9sQkWfvfszaStEJWtMYs3EFQaP) | [sell](https://solscan.io/tx/5k4amY4Bx2pwEn9SDE9EpeKwqwcUqaj4G21vx5ERbSLwYrmyDkZ6AGod2oXrbPukBJZiGn4jB9whCy5eAfFhLNuQ) |
| 10-28 09:06:46 | [$](https://gmgn.ai/sol/token/GnCSPmtz3cFKjGEcFtYEyjSdyb1PhNvoquVz43eVpump) | 3 | buy 0.07 SOL (+0%) | 0 sl / 42 ms | 0.311 | +0.0280 | 40 | [buy](https://solscan.io/tx/2wiK4rFgBDNEJNBPhN3bVreZMP8oZuik8fVJnMsV2aWTSCXBb7RGGFLrbdpnG8E7BvXsBQ3xX5yiPgHGBqHVHgwE) | [sell](https://solscan.io/tx/3FGG4KGJfYyPvaXCyKtXTPWgxion8yqbTkkCcYbg7gYYaph1aeSUwZEkzFsNWSXiA6bQReP3ukHZxVoDvpkSrctz) |
| 10-25 07:21:18 | [CardDesk](https://gmgn.ai/sol/token/7W3jCCaw2DUgnkxT9c6Gs71iZWP5kP5YirbWRyWTpump) | 4 | sell 0.71 SOL (-4%) | 1 sl / 208 ms | 0.296 | -0.0849 | 1800 | [buy](https://solscan.io/tx/2xc4Wjx5Kq6y58VHGJh7G7E14qTsJmtWBAp3g6L8tVUZSQRB4Aiur5wGEiMfzcFHUJnhNUhSEotk8p19xEjDTaoj) | [sell](https://solscan.io/tx/3wPHq9EqitbFP31WQVDz9DbbjLmXYtZXq1KKgb78NPgUZ3eDJpiJEnSgr3V63dh2oV5UkTz9qLgUdXfyx29pYQZ6) |
| 10-28 11:09:28 | [SI](https://gmgn.ai/sol/token/BcVh6q2CjtmmEKENnqT6bwCgy7y7rMVqHHBWJBTopump) | 8 | sell 0.35 SOL (-2%) | 3 sl / 781 ms | 0.299 | -0.0297 | 6 | [buy](https://solscan.io/tx/3Kmt1cpENd35oMM5HwxsTf2UqVLJeGNNYVxRPCQYtnf4bgbanav8p9h71pVTz2SemXT7dvng5wYkkWuQC76dPVi3) | [sell](https://solscan.io/tx/4q6E6Eo1P3PgGhfUxzRsnNZ8j9nGtSP6KWKiEnTY99LskmeNxpXyNmspgyojLxCEMocZoLMTEFsT3EZEHrVAGucT) |
| 10-28 02:56:41 | [GYRALIS](https://gmgn.ai/sol/token/DbNN8ocpzsNHapKSE88f8qcmUewRPXa1da5ekCUdpump) | 7 | sell 0.83 SOL (-5%) | 0 sl / 45 ms | 0.229 | -0.0240 | 2 | [buy](https://solscan.io/tx/5miuzf1kyfNKFzXC7ZwfrGbKANE339LjNKe81kCNACAu7a299b47oNK7AyuZABboNnFS3Q325ohY1FQ4HS32AdJY) | [sell](https://solscan.io/tx/3BAZjQSvRus3VWSg5Bs3ytTwN1QuRQpMsPvmZZCKgY8W4QtAXM75hQTNGmLmDbsfh83oY1RPDifcvyoZuu8PzsLC) |

### LAUNCH-RIP
| time PKT | token | age s | trigger (3 slots before) | lag | buy SOL | lot P&L | hold s | buy tx | sell tx |
|---|---|---|---|---|---|---|---|---|---|
| 10-27 03:59:41 | [PRINTPAD](https://gmgn.ai/sol/token/5AW6TuBtehqCbCUKzf6U9jFPWxcpaBfWSTUUPsEKpump) | 6 | buy 1.31 SOL (+7%) | 1 sl / 39 ms | 0.245 | +0.1162 | 426 | [buy](https://solscan.io/tx/2egszgjLhBuohGqoTvmTbZrFzd1vvLSD9rFwdnuxVbNurB8BLuqJVsV4Dhv7mDJxfdQjwzxGuUhXtxUNgAyThcRK) | [sell](https://solscan.io/tx/465xY9UQHAaPZb9HEKmKwJGD6MsD4PLASRiRvJrE1oCUnNsmgp62kT1FSS1xp2xkZpTsMqtxkMbAwxkuQdft6Npu) |
| 10-25 15:19:51 | [CAMILA](https://gmgn.ai/sol/token/6vnyoXtS8h47bXBqre6zyuVVEXDcQtVMXFhCDQcspump) | 3 | buy 1.49 SOL (+7%) | 1 sl / 313 ms | 0.296 | +0.0350 | 48 | [buy](https://solscan.io/tx/2zYEzg3TkHvj81JVJzYcZvT5RhTGBk1JEfZ8ccX6e6z4j19o6CVAmsptwvqXPLEbTewDMWC8nbxvvwJPK3vZTSuC) | [sell](https://solscan.io/tx/4LTKELtSzfgPZE1ihtYLuf9roRNxwmzmym293WHaD2RmeGNH6LWvX7p3bYv3xmQ5Ysfk5ToVrNc9dMMXGDrkUpiX) |
| 10-22 09:13:28 | [HUMAN](https://gmgn.ai/sol/token/DU4sBuPBVygPPZNeecpDt55cAbYrZC9ahZB7n8AMpump) | 8 | buy 1.96 SOL (+12%) | 1 sl / 63 ms | 0.247 | +0.0745 | 69 | [buy](https://solscan.io/tx/4YYyfJfnP19Fc9c3z7pTm9NwJA8tdmHbE11qAmkjCvUpUnhKHJ9bYrgYoFHXkW2hpKuicrGKkfugaiZMd6JHFTKz) | [sell](https://solscan.io/tx/AAiMr1rFnSJsYwmTgADiYoTd7rVTDU14LzshRy8oLiFRhbFggj4kWPTnhn5dsrXdzHXFN5hVLRAmUPTHErb4SA9) |
| 10-26 00:16:52 | [S&P493](https://gmgn.ai/sol/token/5HYwM5yJzzPLmj5WJwcUYXXhw5n1dsJaeYQcWv3Rpump) | 9 | buy 6.91 SOL (+35%) | 1 sl / 196 ms | 0.308 | -0.0166 | 3 | [buy](https://solscan.io/tx/5D5nfvsDcj2WKui5UEPPK25MGZh1BNUvx8N3iwD8V4yGrKhp2tCi3LJ7rxW5jh1L4J8HTge9YVKrdc9hYVdVDC4u) | [sell](https://solscan.io/tx/2yHt2Ve6ykGk6r1JVBohroVrESF99vBPfJ5q9AJXx5CicMtkmwF5pWmKp7iwvMscq2E6ts6WMquEx2heFQ5wfrW5) |
| 10-25 15:58:26 | [LVC](https://gmgn.ai/sol/token/8uNfPfgGW4SfhX8qCm9MUSpSEbfd6qNPSY7yHUS3pump) | 6 | buy 0.99 SOL (+6%) | 2 sl / 346 ms | 0.296 | -0.0099 | 977 | [buy](https://solscan.io/tx/5FDzZnZxkdf3LeRxp6ogGGQ6G6eCdw1TBBphwb2PUKFTwzxk7zznUagVRndXDBEfzZZydoqrqnLvyZcxydYB4P7c) | [sell](https://solscan.io/tx/2TCTQyAdBUcr5wbZjpKvRxXGxEDhm3ekfW9GdG5o8rb6RUkjxu938sZkyyd87B9GJX3Jpsz9GRREp17zJQbsuYki) |
| 10-27 06:49:33 | [FUNDR](https://gmgn.ai/sol/token/58FpkGNWesNxwXpshVaFHmNkb39yct1YC8f7Pkphpump) | 2 | buy 2.57 SOL (+14%) | 1 sl / 335 ms | 0.289 | -0.0418 | 67 | [buy](https://solscan.io/tx/2ce4UrUzGRaymJVr8VHKYtPzUob7CxSbDoxe6vFdcev7CYionEuRPKpn4Qzwo7LCbGVDazqSdGqi8p7K5iUFUvZb) | [sell](https://solscan.io/tx/5TEJiQXJVh32qy28GvHjUTBKcoz141HUF8Ktdu1mesUUqpVxQVZjrrPyQickQKsfzDhx2ozVCnYdXepnTeB6pPN3) |

### RE-ENTRY-DIP
| time PKT | token | age s | trigger (3 slots before) | lag | buy SOL | lot P&L | hold s | buy tx | sell tx |
|---|---|---|---|---|---|---|---|---|---|
| 10-26 08:57:50 | [FOMO](https://gmgn.ai/sol/token/BXnLS8gsS1fNauqco3fgPz6vL5SLLdAg2vMArZLMpump) | 88 | sell 1.37 SOL (-6%) | 0 sl / 32 ms | 0.422 | +0.1916 | 23 | [buy](https://solscan.io/tx/5Ybtv2PEFf1Md4pgMTW5aLbc82dPDG28pg2ggjq8qAn7JWC2DF6s1F7bzwBHStytJpBGXZbxUoZuirnaJ8QnHkqt) | [sell](https://solscan.io/tx/4QztVZwQN8yhKd8HbisGsCsFZT9nBCp36yieCdA9Hf3dddkmu12WVvZPc8aweaNYAqt1uiBHZvBi5ZxqJtUxgk2L) |
| 10-26 18:45:46 | [WINGPILL](https://gmgn.ai/sol/token/6keTTK7M1Fj9pcuQ2xZ2FBEr5k9aEGv5fe5stcKbpump) | 935 | sell 1.24 SOL (-4%) | 2 sl / 526 ms | 0.988 | +0.1211 | 667 | [buy](https://solscan.io/tx/KqVbBcSfv9B7aVnmiDV87WX7J2nz7gsvx66oDE7QkwmVMcxP1udEnYFi3LFiqHzDPEeuskbYS1xF64SD4fo6faF) | [sell](https://solscan.io/tx/RiQXJ5NQy6tpbQrJSbPXq4uiaiFWZyB2CtXcGduRei9MT9v89Fh2ap4zMFX5iHB49CXb7AqozvrXwqYe7DZgnrA) |
| 10-24 04:34:07 | [2Shell](https://gmgn.ai/sol/token/HKr9wgrnjeHBDdtio7AbZCE2KHLBgPqgUbfJvJsNpump) | 111 | buy 1.76 SOL (+8%) | 0 sl / 73 ms | 0.296 | +0.0182 | 70 | [buy](https://solscan.io/tx/5LvdhGLc7YphWF4g8WnjpNn4PCd1hYkTAvy5N8CppsTE89b2Ltx7d3avJ1J2MAhvzvFzkcYVDBTsbcH3SkMhW1dY) | [sell](https://solscan.io/tx/2eaJepF7GyznbyNS54XdMJjnTnzEgtDNSXBktPqez31sN7rKFyF5Hgr4aKP9bdZeZVA8b65nUW8XojRLw7sxi6yA) |
| 10-24 07:52:49 | [GGG](https://gmgn.ai/sol/token/5RGiEtXJs4nqzDxXNN6ZKBhfQj3CTHpbdmEBErG4pump) | 168 | buy 3.25 SOL (+17%) | 2 sl / 330 ms | 0.296 | -0.0094 | 53 | [buy](https://solscan.io/tx/8uUcGLC8C4usjiCroVGMTDssbpd3AAdguqq4FTuMoJngrdgWMkqs8DyBxbDMZVrXrCU773MqHcuonsmXNZ7hBfd) | [sell](https://solscan.io/tx/5581R7dAjhnTCdb8FxRNd1Fhg8LVELGdWuUxXNoLjWgyiv4ZU4b2XLDBV69ZJVNqEqjJ8gwDChqStfakddmh6NZA) |
| 10-22 10:49:00 | [PauseAI](https://gmgn.ai/sol/token/FmUbDE87tyGNeuWFxVG8YGgc8EjC3baPYk15QScjpump) | 4899 | buy 0.30 SOL (+1%) | 0 sl / 22 ms | 0.247 | -0.0606 | 1800 | [buy](https://solscan.io/tx/3nAFKeJpnEfWmMuWn31DP6sfdMhE4JrHCmE2ANkPKbqrQx3G4WgKFdxmZTPoadYqFCkCVmfAF1kAE9A1aoLyjmkm) | [sell](https://solscan.io/tx/2QjvyGSdzDDA8RuwADq7ejdmqAuf5ZBHAwFboPgrJUqsw2TDRXccrDATJsHBa75DpBSWUmHmC6BqfBFnYvcqok1d) |
| 10-26 12:41:37 | [BUBBLE](https://gmgn.ai/sol/token/3X33aEMRzMmUPZcAeGuUQMCyqZEgN4UsofwFUsGspump) | 42 | sell 1.12 SOL (-6%) | 2 sl / 443 ms | 0.351 | -0.0062 | 45 | [buy](https://solscan.io/tx/3wio7PJ4wbgv4GFgbisJN1gNxy2Cq15A48uiPZ4q5W4HuHfd2Lu1HuoAYXLowN11BgTADFjqvrnDmDKnp3PWyzte) | [sell](https://solscan.io/tx/3FjL2KyYuxkNJENFZ8ZGG4T9CXJ5cdnvU6dbgRXNo243PMpER5TE1pF9c8ECn7ir4B5RSKTXXRftjnZxBACYB4TM) |

### RE-ENTRY-FLAT
| time PKT | token | age s | trigger (3 slots before) | lag | buy SOL | lot P&L | hold s | buy tx | sell tx |
|---|---|---|---|---|---|---|---|---|---|
| 10-23 07:12:43 | [SNOWMEI](https://gmgn.ai/sol/token/2nEwN3ZLGWfTmG8AsRt47WDQTvc6QLP9poQVJ7a7pump) | 257 | sell 1.29 SOL (-5%) | 0 sl / 134 ms | 0.247 | +0.0494 | 44 | [buy](https://solscan.io/tx/5SKvqvvZ9QF4EQ6XjWGz5gi6HkSbvF5QcXmMxdo2VCsq9FWWbdZD88fRz4gZsDq6mxyMy9cdSu311MFkUHv3HmGt) | [sell](https://solscan.io/tx/3RXfgPPCXUDUMQhxkJYVtH2pd4AaG5wBXQQSZ1fi8uk9JXdtCcjNJkuGCEhdqEV8gigxGf7b6BksewsciLy15jKk) |
| 10-23 19:39:11 | [Dell](https://gmgn.ai/sol/token/Dzc7sQZWMyJ2x6aa692swVRBK4Yi2YGW84KSYp7opump) | 277 | sell 0.58 SOL (-2%) | 3 sl / 614 ms | 0.296 | +0.0160 | 50 | [buy](https://solscan.io/tx/3gthDVdCS2pwCBfvr9MnvfunTyzUewiBuETHJySeiqbtEo2t6jHxu9RrGNnuuCRgD9KJM6U4HmKFpXPEFwe8avVC) | [sell](https://solscan.io/tx/c6EfPoMmtmonWS4DZ1vDJ3hyuiwrUdPHNq9fxS3LMMWSXKUH6Xt4aL8QrJD3GiPbAMp1Wss5FnZGaA8NinMosjd) |
| 10-24 23:55:32 | [gary](https://gmgn.ai/sol/token/mxu4oR58nMrrbpaivM9fzXBuJhLFMpfNFA8QZatpump) | 258 | sell 0.77 SOL (-3%) | 3 sl / 499 ms | 0.634 | +0.2936 | 113 | [buy](https://solscan.io/tx/5pNhwyt7yYbNXh39SVY2gFhktmJmEX9ZZTRM5BkQgLdaQNHe8VWG3m83bm5iNwFzrK8L7Kn5WXQDMpcRTwLGQP5W) | [sell](https://solscan.io/tx/5Zd7hGTF7ZATLMiJd35zyW1u7JdZpjoaajspsNWghT3Mvuddxi4kQbSPQXAvkGbwLSHYurBkps8Dk53ntx5VvZWf) |
| 10-24 10:13:27 | [non](https://gmgn.ai/sol/token/9fc9dMxqxW9gVDRmZYxZhRnhJxc8RoecrzWSMuPqpump) | 60 | sell 1.74 SOL (-9%) | 3 sl / 646 ms | 0.296 | -0.1623 | 1801 | [buy](https://solscan.io/tx/5kVDibgkpbBufeH5NJ9mHnHajAvHPMTfVkK7nGUdPWTWd1YMLii9tRZWnoeou39zfq369i1Lt7t4FibZbfdEoR3v) | [sell](https://solscan.io/tx/2VwJufThbNGKrXujPTFE7zDQ1gZhcQTBMaw8qM4cjfDgYdAVvbuCjzor3GfHZwcpmLxgMq8hbJPqDT5bBNW5t6Mv) |
| 10-28 12:37:30 | [🐈/acc](https://gmgn.ai/sol/token/5Jj2YyxLoYJPKW2wdRzkpXUd4CByEYNAtSUTbJ8RDENZ) | 3 | sell 14.19 SOL (-52%) | 3 sl / 768 ms | 0.241 | -0.0000 | 0 | [buy](https://solscan.io/tx/24ghH87XzR9Zo1mTrm4nq8Q7TZmteMjGxnYfwwv13YGtPQLPEpLWsMq7QNvM2peKwZ7yUwrqei5bS84V8QW3CDTw) | [sell](https://solscan.io/tx/yG3jHbAMEo8syEjrseEhUBdkeFtdZsfbFVSsW4n675JaCfRoQ7JWPe7vFZpZ7qF6pAze7zQV65cGGSLTShmqm2d) |
| 10-26 03:38:41 | [FLOKI](https://gmgn.ai/sol/token/m1HCn3WZQwGCc9EXyZgvjp2dTUuwNpK5R89FwvQpump) | 67 | sell 2.78 SOL (-8%) | 1 sl / 161 ms | 0.623 | -0.0886 | 0 | [buy](https://solscan.io/tx/1fH2uJdRCJPhq2n4FCQNjcsPCL3bLjYx4pLSr2Uo5bXkb4FJ9ZVdhtwNqB8iazvKfwrzA3hLwU6gqMswi77Zqyw) | [sell](https://solscan.io/tx/3oWG1QfdzqvpcxowDhfEGNZEVQWEyzJj5J7f2r8fpzQErGYwceXFyAGRSdSLYKgJP5VPXTnaJosh4agvKug84kMs) |

### RE-ENTRY-HIGHER
| time PKT | token | age s | trigger (3 slots before) | lag | buy SOL | lot P&L | hold s | buy tx | sell tx |
|---|---|---|---|---|---|---|---|---|---|
| 10-25 01:59:25 | [Jewnu](https://gmgn.ai/sol/token/8BHyhku4Hbs3Y6v92gcJ4gUeJW1WphdePzRV1vCmpump) | 82 | buy 3.99 SOL (+18%) | 1 sl / 243 ms | 0.296 | +0.0873 | 33 | [buy](https://solscan.io/tx/5wpfiUe6bSL9jbysykxVXbWSkakK5JEGdGB82J4F1JyeHPx2kNSCAHRRLpLBa2MFba9VmDm2dmtxMWEqsMi28RSw) | [sell](https://solscan.io/tx/2XAYBpEYKXhLXQ41oc7wAbAhvzffY7vFuCMVHUagxnuyYnnLbKwJnuHkXqZ4jXgFHsC41UKpW9TFRYgy4SeFnsnD) |
| 10-25 02:53:37 | [WILDWOOD](https://gmgn.ai/sol/token/H6mPEvkaPmMQ2zFubQQbytA7i7Yup7n9WfT6SJprpump) | 1164 | buy 1.30 SOL (+4%) | 1 sl / 41 ms | 0.296 | +0.1565 | 54 | [buy](https://solscan.io/tx/51D61BTQtVio3YFke3YUKUw3VGYToQ1s3QpFtGMDTyN51Xq2sVCJYyVhtAqHnL9bnJWNQ7da7tCJ3nxE5tkGyR6q) | [sell](https://solscan.io/tx/33NHGiFxUEBrL2b38paoNPGRwfFGvc8EauYr7hUsQ4qWT2bKhacWwqcg6pK3jJzznuEmmiTuCbS6fmngTU51cqCB) |
| 10-26 07:55:59 | [MOSS](https://gmgn.ai/sol/token/3Sy89myNVgnNsjqgh2XNtyXv5uSC7CZ7sVHvvpZ8pump) | 24 | buy 3.46 SOL (+15%) | 1 sl / 288 ms | 0.322 | +0.0224 | 24 | [buy](https://solscan.io/tx/2SFm8BpcZAHDaReFVzsJ6HgPybz5i6syKRgCDuUbyF3kWsq99Cuo8YXvDK5cbM5yCFqY9gFkCh6yxASvQZkXypwp) | [sell](https://solscan.io/tx/62rdgxrjLVaM8o9ihjJ32F1sJiD5C2kiYFLx2UN4Mx7j2AYf3nQhy1Z2jde1GAGr7LVBtWePiNzMxVyuejWhiKo5) |
| 10-23 07:39:28 | [AI](https://gmgn.ai/sol/token/6kY7FoGCzKkVxf9HMfjenvy3rKn9VT9c4ZYJnzL5pump) | 53 | buy 0.99 SOL (+4%) | 0 sl / 42 ms | 0.247 | -0.0114 | 60 | [buy](https://solscan.io/tx/2oWgDBKbsYrSdrBHWpXVQ3k2qrVMS4SrEMuqQ4e62xy5m9Rz2SztZDHZxFMGa6r2e3vnJ55aT162QM6ih4CyXLaR) | [sell](https://solscan.io/tx/54nkYEb8J6CwcfYGDPxpGxf4N5rDJAhp6QjTSu1FJjgdtm2LG7zNpSk1JcpRfr1GUk6nZjUFA8XjiiLFLh7SLgWq) |
| 10-26 22:47:26 | [CABAL](https://gmgn.ai/sol/token/EshLEdxEjuoWjMYy7FJrMPfas6Cb11i2v5UYBGocpump) | 480 | buy 2.96 SOL (+11%) | 1 sl / 85 ms | 0.988 | -0.2356 | 121 | [buy](https://solscan.io/tx/34S9QoXFrK441EtedZLTB2UgfLBTDbBTTNYqd3yinP4MHNx5SJiJhYG8NALHLrdKVHRo8hVBwyw7nC8e9kQMYUcT) | [sell](https://solscan.io/tx/2dgLUjBWTRUahnPMRFkh9c9A1GZ6X9kwi3XDcdyRDrXqj8ohCW7kihvqaVHrQdiAGp9obsEYrU1XF9ESTqQ4sWMB) |
| 10-28 11:22:57 | [SummonSi](https://gmgn.ai/sol/token/5mzy2oEPEneJ47T2pb21FqGewjKY9TtGxGZUjVdNpump) | 5288 | buy 0.80 SOL (+3%) | 1 sl / 162 ms | 0.988 | -0.0065 | 1184 | [buy](https://solscan.io/tx/45JyUr5Ev1rSkubvqDotX54JGwm6qQnnkA1BcLmMgL2fQhmbuVTusBk6gQPGhX7cNhDfKBYH7LK9pcYd6mvWn3nF) | [sell](https://solscan.io/tx/4XaTq8WbWiiSu2b6D4fhahnMZjPJx3rbYTC5AyVvCzbKDqHgVgJAGcxFdtXJyGLhyo3thZqPNggU1q6yaR2s7Fpw) |
## Files
- **Code:** s0_creates (creates + names + URI), s1_build (sorted tape), s2_feats (per-buy context + trip P&L), s3_universe (event universe), s4_model (event GBDT), s5_speed, s6_eval, s7_followers, s8_cohort, s9_envelope (take vs skip per family; META=1 adds metadata), s10_overlap, s11_leaders, s12_siblings, s13_cluster_leaders, s14_adds_exits, s15_families, s16_meta, s17_rules, s18_examples, s19_recon_join, s20_grad, s21_copiers, plus lib/tl/show helpers.
- **Data:** buys.pkl (per-buy features + P&L), U.npz (event universe), family.npy, examples.md/json, s*.txt.
  - tape.npz was deleted to save disk; regenerate it with s1_build.py.

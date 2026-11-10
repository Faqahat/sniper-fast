# 9pQQ: reference document (all findings to 2026-11-03 evening)

> **11-03 evening update:** two more studies (CASEBOOK, token by token; LANES, fingerprints). See **section 11**: the bot's two code paths are now PROVEN (slippage pricing), its version history and off periods are mapped, the exact slippage is 15 % on buys and ~50 % on sells, and the "pre-landing order flow" lead was tested and rejected. Its entry choice and its exit are still **not cracked**. Owner rule (11-03): speed is a separate question; rows at our speed are information only, never a verdict.

Wallet: `9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN` ("9pQQ"). Written 11-03 from the study files listed in section 10.
All times are PKT (UTC+5). SOL figures are net of pump fees, tx fees and tips unless a row says otherwise.
Nothing here is new analysis. Every number is copied from a source file, or is simple arithmetic on one (marked "arith").

**Tags used on every fact**
- **[M]** MEASURED on chain or on the recordings.
- **[I]** INFERRED: a reading of measured facts, not proven.
- **[E]** ESTIMATE: paper replay or extrapolation.

**Source keys**
- **R**: `ops/strategies/rivals/9pQQ/REPORT.md`, the first dissection (11-03 ~05:50).
- **J**: `9pqq.json` and the per-test JSONs in the same folder (clusters, takerate, replica, interact, ours_k, k9filter, exitshift, ...).
- **X**: `exact/REPORT.md`, the exact-rules study (11-03 ~06:55).
- **XJ**: `exact/exact.json` and the `exact/*.json` files (h0_hard, h1_test, h2_fp, p3_route, t1_timer, e1_rules, g1_*, c1_calib_*).
- **C1**: `cases/PHASE1.md` + `PHASE2.md`. Blind case study of T1 `D2496au7…` and T2 `7aFTe3Sq…` (11-03 ~07:40).
- **C3**: `cases3/PHASE1.md` + `PHASE2.md`. Blind case study of T3 `CsGVEXJD…` (11-03 ~07:55).
- **MEM**: memory note `wallet-9pqq.md`. It holds the botpnl measurements, census history and observatory notes. Other memory notes are named where used.
- **CSV**: `/home/it/sniper-data/rivals/9pQQ/cases/*.csv|txt` and `cases3/*`.
- **CB**: `casebook/FINAL.txt`, `ledger.txt`, `ledger.json`, `final_1102.txt`, `cases/`. Token-by-token casebook, 64 tokens, 51 hypotheses (11-03 ~20:30).
- **L**: `lanes/lanes.json`, `FROZEN.json`, `calib.json`, `replay_*.json`. Lane separation by tx fingerprints and slippage pricing (11-03 ~21:15).

Recording windows (J), PKT:
- **"10-28":** 10-28 19:05 → 10-29 19:25 (24.3 h).
- **"10-30":** 10-30 18:55 → 10-31 19:14 (24.3 h).
- **"10-31":** 10-31 18:50 → 11-01 19:09 (24.3 h).
- **"11-02":** 11-02 17:50 → 11-03 09:59 (16.1 h; X uses 16.49 h for its window).

Not recorded: 10-29 19:25 → 10-30 18:55 and 11-01 19:09 → 11-02 17:50.
Per-day figures for 11-02 are scaled from 16.1 h.

---

## 1. Identity and summary

### Who it is
- A single fully automated pump.fun bonding-curve trader. One wallet, one code path, one tx fingerprint **[M, X H2: "one fingerprint", no sister wallet with the same fee fingerprint, R]**.
- It trades only the pump.fun curve, calling pump.fun directly with no router or wrapper program **[M, C1]**. The rare AMM exits are the graduation trips (section 2).
- Size: a fixed **0.70 SOL per buy**, including pump fees. It was 0.48 SOL for 5,250 buys on 10-30/31 **[M, XJ]**.
- Volume: **4–9k round trips a day**, up to 25–32 open positions at once (on different tokens) **[M, J, XJ]**.
- Classed by the 10-22/23 census as a "high-volume late bot" (sssss*, BUkpShoE, 9pQQc1xy, DYXDDrZC) **[M then, MEM / wallet-census.md]**. That old picture ("profit sits in scale-ins and graduations, small trades lose") **no longer holds**: it never scales in, and graduations are a small share (section 2) **[M, R]**.
- Other names for it in our notes:
  - r42 observatory: "#4 first backrunner (2,525 in 55 h)" **[M, MEM]**.
  - 10-24 pattern search: bait responder "B301" **[M, MEM / strategy-families.md]**.
  - 10-29 Astralane census: "9pQQ 100 % Astralane" **[M, MEM / astralane-vip1.md]**.

### How much it makes (closed round trips; fees and tips in; token-account rent credited back)
| recording | trips | net SOL | SOL/day | without top 5 | without top 20 | source |
|---|---|---|---|---|---|---|
| 10-28 | 4,235 | **+19.61** | +19.4 | +12.39 | −1.69 | J [M] |
| 10-30 | 8,867 | **+87.32** | +86.2 | +79.41 | +65.34 | J [M] |
| 10-31 | 7,218 | **+68.63** | +67.7 | +58.48 | +41.14 | J [M] |
| 11-02 (16.1 h) | 7,730 | **+61.62** | **+91.7** | +50.96 | +32.44 | J [M] |
| all 4 | 28,050 | **+237.18** | | top 20 = +36.45, top 100 = +119.39, bottom 100 = −52.41 | | a3.txt [M] |

- Later spot check, 11-03 09:31–12:40 (3.15 h): 1,145 closed trips, +8.52 SOL before ~1.3 SOL of rent refunds **[M, C3]**. That is about +65/day without rent and about +75/day with rent **[E, arith]**.
- **Trend:** +14..+19/day on 10-28, then **+60..+92/day from 10-30 on**. It is still growing or steady on 11-02/03 **[M]**.

### How it works (one paragraph)
9pQQ watches every pump.fun token it considers live. That means non-mayhem, at least 8 slots old, curve between ~30 and ~112 SOL, and a busy token.
It reacts to individual outside trades on that token, inside the same slot or at the top of the next one.
For about 0.3 % of those trades it sends one buy of exactly 0.7 SOL. The tx carries a fixed recipe: CU price 1,500,001, Astralane tip 1 mSOL, Jito tip 17,500 lamports.
It then holds a single full position. It sells the whole bag in one SellV3, again as an in-slot reaction to a later outside trade (more often a sell).
The sell becomes more likely as outside buying pauses, but there is no take-profit and no stop-loss. A hard cap forces the sell at 300 s (600 s since 10-31 14:03).
It re-enters the same token again and again while the token stays busy: 68 % of all trips are re-entries, and 94–97 % on single hot tokens.
The money comes from a fat tail: a few rides held 250–1,300 slots make most of it, while the average trip is near break-even.
Forced time-cap exits on dying tokens are its main loss.

### What is proven and what is unknown
| proven [M] (held on 100 % of trades, all 4 recordings + 3 case tokens) | not proven / unknown |
|---|---|
| Fixed tx recipe, size, instructions, tips (section 3) | **Which** trade it buys after: it skips ~90–99 % of qualifying trades. Rule lists hit 8–17 % precision. The rebuilt bot loses (section 4.9, 8.3) |
| One buy + one full sell per position; one position per token | **When** it sells. Exit rules hit its sell slot ±1 only 16–27 %. The learned exit loses when we run it (section 5) |
| Never mayhem (0/28,240); never buys before age 8 slots | Why it waits ≥ 8–10 slots after launch |
| Never sells before buy slot + 2; never re-buys before own sell + 2 | Whether it reads pending/failed txs or a pre-confirmation feed (**[I]** it must react inside the slot; see 9.3). The "decides before the trigger lands" version was tested and **rejected** (section 11.5) |
| Hold cap 300 s, then 600 s from 10-31 14:03 | ~~Its slippage limit~~ **now PROVEN [M, L]:** buys min_out = expected ÷ 1.15 (15 %), sells ~0.48 of expected (section 11.2) |
| Every buy and ~79–100 % of sells come right after an outside trade on the token (same or previous slot) | How much of its trading is on old revived tokens the recorder does not track (T2 case; section 9.4) |
| Profit is real and closed: rent refunds are not profit (section 2) | |

---

## 2. P&L history (all measured windows)

### 2.1 Three versions of the same P&L, reconciled
The sources show three different numbers per recording. All three are correct; they count different things.

| recording | botpnl closed trips, **rent NOT credited** (MEM) | dissection, **rent credited** (R/J) | replay "real" set, **excludes graduation (AMM-sold) trips** (J replica, XJ calib) | rent refunded per CloseAccount (J buyins) | graduation trips n / net (J) |
|---|---|---|---|---|---|
| 10-28 | +14.3 | +19.61 | +18.84 | 5.657 SOL (3,670 accounts in 1,900 txs) | 7 / +0.76 |
| 10-30 | +77.5 | +87.32 | +79.85 | 10.557 (6,952 / 3,286) | 13 / +7.47 |
| 10-31 | +60.7 | +68.63 | +63.66 | 8.537 (5,622 / 2,794) | 8 / +4.97 |
| 11-02 | +53.2 (= +79/day) | +61.62 (= +91.7/day) | +52.76 | 9.227 (6,097 / 2,439) | 11 / +8.86 |

- **R − MEM** = 5.3 / 9.8 / 7.9 / 8.4 SOL. This equals the accounts its buys created (3,442 / 6,461 / 5,226 / 5,573) × the average refund per closed account (~1.52–1.54 mSOL) **[M/arith]**. So the only difference is rent, and the rent refund only returns the rent the buy paid. **The rent is not profit; R's number is the fair trading P&L.**
- **R − replay "real"** = 0.77 / 7.47 / 4.97 / 8.86 SOL. This equals the graduation-trip P&L exactly **[arith]**. The replay can only price curve trades.
- **"Non-trade" SOL inflows** of 5.7–10.6 SOL/recording are these CloseAccount rent refunds, not hidden profit **[M, R]**.
- **CloseAccount behaviour [M, C1, C3]:**
  - ATAs are closed by separate batched txs, 5–20 s after the sells, 1 to 7 accounts each, sometimes other tokens' ATAs too.
  - The rent on Token-2022 ATAs is 1,513,840 lamports per account **[M, C1]**.
  - The average refund per closed account is ~1.54 mSOL **[arith]**. **[I]** That is a mix of Token-2022 and older SPL-token accounts.
- **Failed txs [M, J buyins]:**

| recording | failed txs | cost SOL | main errors | buy-fail share of buy attempts (arith) |
|---|---|---|---|---|
| 10-28 | 399 | 0.076 | Buy 6042 ×349, SellV3 6003 ×30, SellV3 6005 ×15 | 351/4,599 = 7.6 % |
| 10-30 | 691 | 0.134 | Buy 6042 ×628, SellV3 6005 ×26, 6003 ×25 | 629/9,499 = 6.6 % |
| 10-31 | 285 | 0.056 | Buy 6042 ×261 | 261/7,485 = 3.5 % |
| 11-02 | 287 | 0.056 | Buy 6042 ×271 | 271/8,006 = 3.4 % |

  - R's wording "4–8 % of buys" matches 3.4–7.6 %.
  - 6042 = slippage. 6003/6005 = sell-side errors, few.
  - It never retries in duplicate; it re-decides on the next trigger.
  - For comparison, **we had 59,442 failed txs in the same 16 h of 11-02 (~197 per trip)** **[M, R]**.

### 2.2 Shape of the P&L [M, J clusters / MEM]
- Win rate 40–45 % on every recording (overall ~42 % [arith]). Median trip is negative (−11.6 mSOL on signal exits) and the mean is positive: a **fat tail**.
- **Hold (slots) p25/p50/p75/p90 ≈ 22 / 80 / 250 / 900**, a median of ~30 s **[M, MEM]**.
- By exit type:
  - **Signal exits** (all non-cap): n 25,862, **+331.04 SOL**, +12.8 mSOL/trip, win 44 %, hold p50 66 slots. Per recording: +42.4 / +107.7 / +91.8 / +89.1.
  - **Forced cap exits** (hold exactly 299–302 s or 599–602 s): n 2,188, **−93.86 SOL**, −42.9 mSOL/trip, win 21 %, hold p50 1,408 slots. Per recording: −22.8 / −20.4 / −23.2 / −27.5. These are tokens that went dead under it.
- **By hold band (slots):**

| hold band | n | net | mSOL/trip | win | 10-28 | 10-30 | 10-31 | 11-02 |
|---|---|---|---|---|---|---|---|---|
| < 6 | 1,660 | +27.42 | +16.52 | 49 % | +8.0 | +7.7 | +3.9 | +7.8 |
| 6–50 | 9,487 | −16.05 | −1.69 | 40 % | +0.5 | −11.2 | −4.7 | −0.6 |
| 50–250 | 9,368 | +96.50 | +10.30 | 44 % | +5.0 | +29.9 | +28.9 | +32.7 |
| **250–1,300** | 4,932 | **+210.36** | +42.65 | 49 % | +29.3 | +77.0 | +60.0 | +44.1 |
| ≥ 1,300 | 2,603 | −81.05 | −31.14 | 25 % | −23.1 | −16.1 | −19.4 | −22.4 |

- **Top 20 trades per recording [M, J reentry_grad]:**
  - Sums: +21.3 / +21.98 / +27.49 / +29.18. On 10-28 that is more than the whole day.
  - Median hold of the top 20: 189 / 545 / 451 / 273 slots.
  - Entry lane mix: LAUNCH 11/8/4/4, DIP 5/6/7/10, other 4/6/9/6.
  - Graduated: 0/3/1/2. Median token age at entry: 40/94/88/155 slots.
  - Biggest single trips: +1.643 / +2.015 / +3.924 / +2.848 SOL.
  - R: "Top 20/day (+21..+29) = LAUNCH/DIP held 190–545 slots."
- **Version × size [M, J]:**

| version | size | n | net | mSOL/trip | win | recordings |
|---|---|---|---|---|---|---|
| V300 (300 s cap) | 0.7 | 5,940 | +36.35 | +6.12 | 44 % | 10-28 +19.6, 10-30 +16.7 |
| V300 | "0.5" (= 0.48 quote, see 3.2) | 5,250 | +40.05 | +7.63 | 42 % | 10-30 only |
| V600 (600 s cap) | 0.7 | 16,860 | +160.78 | +9.54 | 41 % | 10-30 +30.5, 10-31 +68.6, 11-02 +61.6 |

### 2.3 Census history [M then, MEM]
- **10-22/23 census:** n 3,596, +79.6 SOL **marked** / +22 **closed**. Marked P&L counted open positions at mark; only the closed figure is real.
- **11-03 botpnl:** +14.3 → +77.5 → +60.7 → +53.2 closed (rent not credited), described as "growing".
- **Case tokens** (net of fees/tips, rent not counted as a cost):
  - T1 `D2496au7`: 34 trips, +1.479.
  - T2 `7aFTe3Sq`: 27 closed trips, +1.453.
  - T3 `CsGVEXJD`: 16 trips, +0.9998.

---

## 3. Exact mechanics (hard rules)

### 3.1 Tx recipe (identical on 100 % of txs: 4 recordings, 2,307 txs on 338 tokens 11-03 09:31–12:40, the 124 txs of T1/T2) [M, X, XJ, C1, C3, J buyins]
| item | BUY | SELL |
|---|---|---|
| Program call | `BuyExactQuoteInV3` (pump.fun, direct; no router) | `SellV3` of the whole balance (`SellV2` rare: 7/12/8/11 per recording, with CU limit 200,000) |
| Amount | quote in = **700,000,000 lamports incl. pump fees** = 691,358,023 to the curve + 6,567,902 protocol fee (0.95 %) + 2,074,075 creator fee | token amount = exactly the amount bought (61/61 on T1/T2) |
| ATA | created idempotently in the buy when missing. Inner ixs: GetAccountDataSize, InitializeImmutableOwner, InitializeAccount3. That is 3,442/6,461/5,226/5,573 creating buys per recording. The others reuse a not-yet-closed ATA | closed later by a separate batched CloseAccount tx |
| CU price | **1,500,001** micro-lamports | 1,500,001 |
| CU limit | **130,000** (~75k used) | **80,000** (~53k used) |
| Tx fee | **200,001** lamports (5,000 base + 195,001 priority, arith) | **125,001** (5,000 + 120,001) |
| Tips (both in every tx) | **Astralane 1,000,000** (`astra4uej…`) + **Jito 17,500** (rotating standard tip accounts) | **Astralane 100,000** + **Jito 17,500** |
| Cost per tx | 1,217,501 lamports | 242,501 lamports |
| **Cost per round trip** | **1,460,002 lamports ≈ 1.46 mSOL**, plus pump fees. **Ours ≈ 4.5 mSOL** | |
| Signatures | 1 signer, 1 tx per decision. No duplicate copies, no durable nonce, no retries beyond the next decision | same |

- No token-specific send lanes: every tx goes to Astralane and Jito together **[M, C3]**.
- Astralane is used on 100 % of its txs **[M, MEM / astralane-vip1.md]**. Our own r38 A/B found Astralane **not faster** for us (p50 +4.7 ms, same-slot −1.9 pts) **[M, astralane-vip1.md]**. So the recipe's value to us is its cost, not its speed **[I]**.

### 3.2 Size history [M]
| period | quote in per buy | source |
|---|---|---|
| ≤ 10-30 ~18:55 and after ~10-31 10:00 | 700,000,000 lamports (0.70 SOL) | XJ fingerprint, C1, C3 |
| 10-30 18:55 → 10-31 07:00, mixed to ~10:00 | **480,000,000** lamports, for 5,250 buys | XJ (10-30 recording: 5,250 × 480 M + 3,620 × 700 M) |

- **Reconciled contradiction:** C1 flagged "R says 0.5 SOL, X says 0.48; one is wrong". **Both are right.** R's cluster label rounds the wallet outlay to one decimal (`round(spend/1e9, 1)` in a3_clusters.py). A 0.48 quote plus fees, tips and sometimes rent is about 0.483–0.485, which rounds to "0.5". The exact quote is 480,000,000 lamports (X).

### 3.3 Position rules [M, XJ h0_hard + cases]
| rule | 10-28 | 10-30 | 10-31 | 11-02 | cases |
|---|---|---|---|---|---|
| Buys | 4,248 | 8,870 | 7,224 | 7,898 (X window) | |
| **Mayhem buys** | **0** | **0** | **0** | **0** (0 / 28,240) | none are mayhem |
| **Min token age at buy (slots)** | 8 | 9 | 8 | 8 | T1 first buy age 10; T3 age 19; window 11-03: min 8, peak at 11 |
| buys at age < 9 slots | 1 | 0 | 1 | 3 | |
| **Min hold (slots)** | 2 | 2 | 2 | 2 | T1 shortest 71 slots, T2 13, T3 11 (token-specific, not a rule; C3 corrected itself) |
| **Min re-entry gap after own sell (slots)** | 2 | 2 | 2 | 2 | a T1 failed re-buy fired at exactly sell + 2 |
| Re-entry gap p1/p5/p10 (slots) | 2/4/7 | 2/5/8 | 2/4/7 | 2/4/8 | |
| **Max hold (s)** | 301 | 601 | 601 | 601 | T2: two exits at exactly 600 s; window 11-03: 61 holds at 590–601 s |
| Holds at the cap (count by second) | 300 s ×473 (+299 ×28, 301 ×23) | 300 ×711, 600 ×65 | 600 ×290 | 600 ×412 | |
| Curve (virtual SOL) at buy, min–max | 30.0–111.7 | 30.0–98.0 | 30.0–97.1 | 30.0–97.5 | T1 35.2–91.2; T2 32.4–78.1; T3 38.8–89.3 |
| Two positions on one mint | 0 | 0 | 0 | 0 | strict B,S,B,S on all 338 tokens (C3) |
| Open positions at buy, p50 / p90 / p99 / max | 6/17/25/28 | 13/20/25/29 | 10/14/20/26 | 17/22/28/32 | 2 at once across T1/T2; 5–12, up to 17, in the 11-03 window |

- **Hold-cap change:** **300 s until 10-31 14:03 PKT, 600 s after** **[M, R, X]**.
- **No scale-ins, no partial sells, no pyramiding** **[M]**. One position per token, but many tokens at once.
- **Slippage [I, X]:** about 10–15 %. Supporting data from XJ fingerprint_slippage on 11-02, using the token shortfall against the best curve state in the trigger window:
  - Failed buys: 208 of 271 sit at a −15 % to −40 % shortfall, and 34 at −10..−15 %.
  - Landed buys: only 5 % are worse than −15 %.
  - Case failures came after adverse moves of +17 % and +21 % (T1) and +17..+24 % (T3) from the decision state to the landing state **[M, C1, C3]**.
- **Re-entry timing [M, J]:** gap from own sell to the next buy on the same token, p10/25/50/75/90 = 7 / 22 / 77 / 276 / 1,103 slots.

### 3.4 What it never does [M, all sources]
- **Mayhem tokens:** 0 buys on 1.5 M mayhem decision moments (J takerate). Mayhem tokens in each recording: touched 0.0 %.
- **Buys in the first 8 slots:** take rate at age < 10 slots is 0.026 % (129 buys over 4 recordings, almost all at age 8–9).
- **Size changes:** only the 0.48 period. No second buy while holding. No partial sell.
- **Holds past the cap:** none.
- **Small trades as buy triggers:** < 0.05 SOL trades get a 0.065 % take rate. Tiny trades **do** trigger its sells (6/58 on T1/T2, 3/16 on T3) **[M, C1, C3]**.
- **Sends without the tip pair:** none.

---

## 4. Entries

### 4.1 Trigger: always an outside trade on the token [M]
| measure | 10-28 | 10-30 | 10-31 | 11-02 | source |
|---|---|---|---|---|---|
| Buy has an outside trade on the mint in the same or previous slot | 97.8 % | 97.9 % | 97.8 % | 97.9 % | XJ t1_timer |
| … same check for a random slot in [buy−50, buy+50] while flat | 36.5 % | 36.6 % | 38.3 % | 38.0 % | XJ |
| Immediately preceding outside trade is in the **same** slot | 82.3 % | 82.6 % | 82.8 % | 83.6 % | XJ |
| … random-slot baseline | 25.4 % | 24.0 % | 25.2 % | 26.4 % | XJ |
| "Trade it reacts to" is in the same slot (R definition) | 67.3 % | 68.2 % | 67.5 % | 69.0 % | J buyins |

Case tokens:
- **T1:** 33/33 buys plus both failed buys follow an outside trade in the same or previous slot. Only 12 % of T1's active slots had one **[M, C1]**.
- **T2:** 28/28 **[M, C1]**.
- **T3:** 16/16 plus 1 failed. **0 buys in 934 flat slots with no outside trade**, against 16 in 1,033 slots with one **[M, C3]**.

### 4.2 Reaction time and in-block position [M, J buyins; C1; C3]
- **Chain-clock ms from the trigger to its buy** (block-position model, R's method), p10 / p25 / p50 / p75 / p90:

| recording | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|
| 10-28 | 7.7 | 21.8 | **46.9** | 88.1 | 161.6 |
| 10-30 | 7.6 | 21.7 | **46.3** | 84.8 | 159.2 |
| 10-31 | 8.0 | 21.2 | **46.1** | 83.9 | 161.6 |
| 11-02 | 6.7 | 20.6 | **44.3** | 82.4 | 157.0 |

- **On dumps** (DIP entries) it is **slow**:
  - Delay p10/25/50/75/90 ≈ 41–44 / 67–69 / **130–152** / 275–346 / 553–573 ms.
  - It is the **first outside buyer after the dump in only 36.8 / 32.9 / 34.3 / 32.7 %** of cases.
  - Outside buys before it on the dump, p25/50/75/90: 0 / 1 / 3 / 5–6.
  - We land at ~50–90 ms.
- **Same-slot share on case tokens:**
  - T1: 23/33 (70 %), median **50 block positions** after the trigger.
  - T2: 20/28 (71 %), median **73** positions.
  - T3: 8/16 (**50 %**), median ~36 positions (range 8–235).
  - Buys that land in the next slot land early in it: median index 57 (T1) / 80 (T2); T3 positions 1–96.
- **[I]** Landing in the trigger's own slot, tens of positions later, needs a shred or pre-confirmation feed. A plain RPC/Geyser follower cannot do it (C1).

### 4.3 Lanes: R's entry classes (first match wins)
Definitions (a3_clusters.py):
- **LAUNCH:** token age ≤ 50 slots (~10 s) at its buy.
- **DIP:** another wallet sold ≥ 0.5 SOL in the 3 slots up to its buy.
- **MOMO:** others' net buy flow over the previous 10 slots ≥ +1 SOL, and the last outside trade was a buy.
- **DRIFT:** everything else.

| lane | n | net | mSOL/trip | win | median mSOL | net w/o top 20 | hold p50 (slots) | 10-28 | 10-30 | 10-31 | 11-02 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DIP | 9,294 | **+87.61** | +9.43 | 43 % | −12.92 | +60.47 | 66 | +12.6 | +33.8 | +12.6 | +28.6 |
| LAUNCH | 6,168 | **+84.63** | **+13.72** | 45 % | −13.65 | +56.79 | 31 | +15.7 | +19.5 | +27.5 | +21.9 |
| DRIFT | 6,732 | +33.85 | +5.03 | 40 % | −13.80 | +12.81 | 141 | −11.2 | +19.2 | +19.0 | +6.9 |
| MOMO | 5,856 | +31.09 | +5.31 | 39 % | −16.59 | +6.66 | 125 | +2.5 | +14.8 | +9.6 | +4.2 |

- **Lane × first entry vs re-entry [M, J]:**

| lane, entry | n | net | mSOL/trip | win | hold p50 |
|---|---|---|---|---|---|
| LAUNCH FIRST | 5,403 | +72.16 | +13.35 | 44 % | 34 |
| DIP RE | 8,044 | +61.78 | +7.68 | 43 % | 62 |
| DRIFT RE | 5,283 | +38.19 | +7.23 | 42 % | 120 |
| MOMO RE | 4,873 | +28.75 | +5.90 | 39 % | 117 |
| **DIP FIRST** | 1,250 | +25.83 | **+20.66** | 42 % | 102 |
| LAUNCH RE | 765 | +12.47 | +16.30 | 48 % | 17 |
| MOMO FIRST | 983 | +2.34 | +2.38 | 39 % | 177 |
| **DRIFT FIRST** | 1,449 | **−4.34** | −2.99 | 36 % | 225 |

- **Lane × exit type [M, J]:**

| lane | SIGNAL n / net / mSOL | TIMER n / net / mSOL |
|---|---|---|
| LAUNCH | 5,805 / **+124.32** / +21.42 (win 48 %) | 363 / −39.69 / **−109.33** (win 4 %) |
| DIP | 8,785 / +106.10 / +12.08 | 509 / −18.49 / −36.33 |
| MOMO | 5,287 / +51.11 / +9.67 | 569 / −20.02 / −35.19 |
| DRIFT | 5,985 / +49.51 / +8.27 | 747 / −15.66 / −20.96 |

- **Lane × hold band [M, J]:**

| lane | < 50 slots | 50–250 | 250–1,300 | ≥ 1,300 |
|---|---|---|---|---|
| DIP | 4,017 / +5.87 (+1.46) | 3,255 / +35.62 (+10.94) | 1,430 / **+65.18** (+45.58) | 592 / −19.06 (−32.20) |
| LAUNCH | 3,745 / **+51.52** (+13.76) | 1,434 / +35.92 (+25.05) | 603 / +34.66 (+57.48) | 386 / −37.47 (−97.08) |
| DRIFT | 1,712 / −25.79 (−15.06) | 2,587 / +11.18 (+4.32) | 1,526 / +56.35 (+36.93) | 907 / −7.89 (−8.70) |
| MOMO | 1,673 / −20.23 (−12.09) | 2,092 / +13.79 (+6.59) | 1,373 / +54.16 (+39.45) | 718 / −16.63 (−23.16) |

  Cells are n / net SOL (mSOL per trip).

- **The lane ranking depends on the token (case studies; see section 6):**
  - T1: DIP +2.0 mSOL/trip (n 13), MOMO +61 (n 8), DRIFT +90 (n 11) **[M, C1]**.
  - T2: DIP −41.5 (n 5), MOMO +38.5 (n 13), DRIFT +129 (n 9) **[M, C1]**.
  - T3: LAUNCH +1,047 (n 1), MOMO +9.9 (n 2), DIP −5.2 (n 13) **[M, C3]**.
  - **"DIP best" is an aggregate fact, not "9pQQ is a dip bot."**

### 4.4 Re-entries [M]
- Re-entries are **68 %** of all trips (J). On single hot tokens: T1 33/34, T2 27/28, T3 15/16 **[M, C1, C3]**.
- **By gap from its own sell [J]:**

| gap (slots) | n | net | mSOL/trip |
|---|---|---|---|
| < 25 | 5,067 | +64.66 | **+12.76** |
| 25–150 | 7,097 | +36.09 | +5.09 |
| 150–1,000 | 4,785 | +26.90 | +5.62 |
| ≥ 1,000 | 2,016 | +13.53 | +6.71 |

- **After its previous trip on the token [J]:**
  - after a win: n 9,341, +93.63, +10.02 mSOL/trip;
  - after a loss: n 9,624, +47.56, +4.94 mSOL/trip.
- **Re-entry price vs its previous exit, p10/25/50/75/90 [J]:** −27.5 / −13.6 / −2.6 / +8.2 / +21.7 %. It does **not** wait for a pullback. On T1, 16 re-entries were above its exit and 16 below **[M, C1]**.
- It farms one live token for 12 min to 2 h, with 16–34 round trips. It stops when outside volume dies: on T3 outside buys fell from ~30 to 2 per 150 slots **[M, C1, C3]**.

### 4.5 Selection: what it buys and what it skips [M, J takerate: 27,228 buys of 8,493,300 decision moments = 0.321 %]
A decision moment is an outside landed curve trade on a token launched inside the recording.
"its net" is 9pQQ's realised mSOL per trip for the trips it took in that bucket.

| feature | bucket: take rate (its net mSOL/trip) |
|---|---|
| side of trigger | sell 0.185 % (+7.9); **buy 0.434 %** (+8.2) |
| trigger size SOL | <0.05 **0.065 %** (−2.2); 0.05–0.2 0.219 % (+8.6); 0.2–0.5 0.587 % (+7.2); **0.5–1 0.663 %** (+10.4); 1–2 0.638 % (+10.1); 2–5 0.571 % (+9.8); ≥5 0.182 % (+22.0) |
| token age (slots) | **<10 0.026 %** (+37.1); **10–50 0.679 %** (+13.1); 50–150 0.316 % (+11.0); 150–450 0.245 % (+3.0); 450–1.5k 0.263 % (+5.5); 1.5k–5k 0.310 % (+4.8); 5k–20k 0.412 % (+7.8); ≥20k 0.443 % (+10.7) |
| curve virtual SOL | **<32 0.086 %** (+9.3); 32–35 0.423 %; 35–40 0.485 %; 40–50 0.477 % (+10.3); 50–60 0.378 %; 60–70 0.289 %; 70–80 0.250 %; **≥80 0.130 %** (+5.2) |
| mayhem | non-mayhem 0.389 %; **mayhem 0.000 %** |
| net flow 10 slots (SOL) | <−5 0.404 %; −5..−2 0.573 %; −2..−0.5 0.371 % (+11.6); **−0.5..+0.5 (quiet) 0.124 %** (+1.2); 0.5–2 0.519 %; 2–5 0.575 %; 5–10 0.380 % (+21.5); ≥10 0.262 % (+16.6) |
| net flow 75 slots | <−5 0.360 %; −5..−1 0.359 %; −1..1 0.147 %; 1–5 0.491 %; 5–10 0.431 %; 10–20 0.444 % (+15.0); ≥20 0.341 % (+22.2) |
| outside buys in 10 slots | <1 0.111 % (+2.2); 1–2 0.310 %; 3–5 0.442 %; 6–9 0.388 % (+12.7); 10–19 0.385 % (+13.2); ≥20 0.325 % (+15.6) |
| trades in 150 slots | <5 0.189 % (−0.5); 5–19 0.416 %; 20–49 0.395 % (+11.4); 50–99 0.336 %; 100–199 0.253 %; ≥200 0.216 % (+0.1) |
| price change 10 slots | <−20 % 0.316 %; −20..−10 % 0.562 %; −10..−3 % 0.410 %; ±3 % 0.194 % (+4.6); 3–10 % 0.503 %; 10–20 % 0.527 %; ≥20 % 0.331 % (+22.7) |
| drawdown from 450-slot high | <−50 % 0.254 %; −50..−30 % 0.338 %; −30..−20 % 0.419 %; −20..−10 % 0.451 % (+11.2); −10..−3 % 0.311 % (+14.1); −3..0 % 0.150 % (−2.8); at high 0.285 % |
| trades so far on token | <10 0.162 % (−3.3); 10–49 0.416 % (+11.0); 50–199 0.324 % (+11.3); 200–999 0.325 %; 1k–3k 0.304 %; ≥3k 0.309 % (+0.5) |
| trigger wallet's trade count (bot-ness) | <10 0.204 % (−1.2); 10–99 0.217 %; 100–999 0.296 %; **1k–10k 0.593 %**; ≥10k 0.433 % |
| creator sold | no 0.337 %; yes 0.298 % (no effect) |
| **its own round trips on this token** | 0: **0.129 %**; 1: 0.934 %; 2–3: 1.144 %; 4–7: 1.257 %; ≥8: **1.337 %** |
| **slots since its own sell here** | <5 1.176 %; **5–24 1.934 %** (+13.4); 25–99 1.515 %; 100–399 1.112 %; 400–1,499 0.790 %; ≥1,500 0.533 % |
| hour (PKT) | 0–3 0.303 %; 3–6 0.296 %; 6–9 0.406 %; 9–12 0.409 %; 12–15 0.306 %; 15–18 0.285 %; 18–21 0.317 %; 21–24 0.284 % (no strong effect) |

- **Token-level coverage [M, J s2]:**
  - Share of non-mayhem tokens it touched at all, by trades per token, on 11-02: [1,10) 0.9 %, [10,50) 12.0 %, [50,200) 34.8 %, [200,1000) 38.0 %, ≥1,000 24.9 %. The other days are similar (10-28: 1.2 / 8.9 / 19.5 / 29.2 / 34.0 %).
  - Mayhem tokens: 0.0 % in every bucket.
- **Case-token selectivity [M]:**
  - **T1:** while flat it let 90 outside buys ≥ 0.5 SOL and 56 sells ≥ 1 SOL pass, and acted on 32. Taken and skipped triggers look alike: median size 0.53 vs 0.98 SOL, price vs its last exit +2 % vs +4 % (C1).
  - **T3:** ~170 flat slots had a ≥ 1 SOL outside trade in the window; it bought after 11. Buy hazard **~6.5 % for any ≥ 1 SOL trade, buy or sell**: buy ≥ 1 SOL 6.6 %, sell ≥ 1 SOL 6.4 %, buy 0.3–1 2.2 %, sell 0.3–1 0.7 %, buy < 0.3 0.3 %, sell < 0.3 0 %, no trade 0 % (C3).

### 4.6 Trigger side: contradictions between sources
| source | buys behind an outside BUY | which side made money |
|---|---|---|
| R/J aggregate | take rate on buys 0.434 % vs sells 0.185 % | about equal: +8.2 vs +7.9 mSOL/trip |
| C1 T1 | 24/33 (12 behind ≥ 0.5 SOL) | after a buy **+1.564** (14/24 won); after a sell −0.120 (4/9) |
| C1 T2 | 23/28 (15 behind ≥ 0.5 SOL) | after a buy **+1.660** (11/22); after a sell −0.207 (2/5) |
| C3 T3 | 9/16 = base rate (57 % of outside trades are buys) | **reversed:** after a buy −0.150 (3/9); after a sell **+1.151** (6/7; +0.104 without trip 1). Net flow negative before the buy: +1.144 (6/10). Positive: −0.143 (2/6) |

- **Verdict:** in aggregate it leans toward trades that move price up, and on T3 it reacts to **size, not side**. Which side pays is token-dependent. **Do not generalise from any one case [M+I, C3].**

### 4.7 What is NOT the buy rule
- **Leader wallets: REJECTED [M, X H1, XJ h1_test]:**
  - 3,054 trigger wallets. The top 1 = 4 % of its buys, the top 10 = 21 %.
  - Leader list ≥ 2 % conversion (1,014 wallets, train 10-28+10-30): recall 10.1 % / 9.1 %, precision 1.47 % / 1.89 % vs base 0.33 % / 0.42 % (10-31 / 11-02).
  - ≥ 5 % list (119 wallets): recall 0.4 % / 0.2 %.
  - ≥ 10 % list (9 wallets): recall 0.11 % / 0.04 %, precision 7.5 % / 4.8 %.
  - Day-to-day rank correlation 0.36.
  - Case tokens: 23 distinct trigger wallets for 33 T1 buys, 24 for 28 on T2, 15 for 16 on T3. No wallet tops two tokens' lists **[M, C1, C3]**.
  - Top-converting training wallets (for reference): 92kQGvkm 25/309 (8.1 %), DVi9JfGV 6.1 %, 8fYBnyM8 5.0 %, Bpcrqu2K 5.0 %, CaAEN3Mb 4.9 %.
- **Several bots in one wallet: REJECTED** (single fingerprint) **[M, X H2]**.
- **Trigger program 41Pr4XqE: an enrichment, not the rule [M, X H1b, XJ p3_route]:**
  - Triggers routed through `41Pr4XqE` (alone, with `6gY1osmP`, or with `L2TExMFK`) are followed by its buy **7.5× / 12.3× / 11.0× / 10.6×** the base rate (arith on p3_route; per class 5.7–14.5×).
  - In count: 364 / 947 / 607 / 532 of its buys = 8.6 / 10.7 / 8.4 / 6.7 % of all buys. X rounds this to "6–9 %".
  - Case tokens: T1 2/33 (both behind wallet 8aVt via 41Pr4+6gY1o), T2 0/28, T3 2/16 windows (12.5 % vs 0.7 % of outside trades) **[M, C1, C3]**.
  - Other trigger classes per recording (lift vs base):
    - `L2TExMFK` alone 2.0–3.5×; `7xdwTaV5` 6.5–8.6×; `haqqqMGN` 2.7–5.0×; `tRunsb6N` 1.8–4.6×; `2Emmffdg` 18.7× (10-28, n 31);
    - FLASHX8D ~0.9–1.05×; `6Vo3245e` (6Vo32 terminal) 0.43–0.54×; GMGN 0.41–0.6×; term9 0.5–1.2×; Jupiter 0.86–1.2×; no extra program 1.6–1.8×.
  - Triggers carrying **2 tips: lift 1.66 / 2.37 / 2.57 / 2.11** vs 0.85–0.88 for 0 tips and 1.11–1.18 for 1 tip.

### 4.8 Model and rule-list results for buys (chronological: train 10-28 + 10-30, choose 10-31, test 11-02)
| attempt | result on test 11-02 | source |
|---|---|---|
| R imitation GBDT (23 features) | AUC 0.952 train / 0.951 (10-31) / 0.941 (11-02). Top 0.1 % of scores: precision **14.3 %**, recall 3.5 %. Top 1 %: 9.9 % / 24 %. Top 3 %: 6.5 % / 47.3 %. Top feature: slots since its own sell (0.268), then trades so far 0.085, size 0.083, age 0.072 | J imitation [M] |
| X frozen 7-rule tree (depth 6) | precision **8.4 %**, recall **24.7 %** (base 0.42 %). Every rule starts "since_own_sell < 891 AND impact ≥ 0.0038 …" | XJ H4 [M] |
| X GBDT ceiling (84 features, 490 trees) | AUC 0.952. **Precision 15.9 % at 5 % recall**, 14.7 % at 10 %, **11.6 % at 25 %**, 7.5 % at 50 %. Top features: since_own_sell, price vs its own last buy, impact, trades so far, buy SOL in the slot, age | XJ gbdt_bound_buy [M] |

- **Soft drivers (X):**
  - a recent own sell on the token (re-entry);
  - price vs its last buy/sell there;
  - a price-moving trigger (impact);
  - trade count, trigger size, age;
  - a trigger from a high-volume bot;
  - the trigger's program.
- **Conclusion:** no on-chain rule for **which** trade it takes. **[I, X]** It reacts to information not in landed trades: pending or failed txs early in the block stream, longer wallet histories, or a model with randomness.

---

## 5. Exits

### 5.1 Sell triggers [M]
| measure | 10-28 | 10-30 | 10-31 | 11-02 | source |
|---|---|---|---|---|---|
| Sell has an outside trade in the same or previous slot | 78.5 % | 86.9 % | 91.9 % | 90.9 % | XJ t1_timer |
| … same check for a random slot inside the hold (timer baseline) | 40.9 % | 37.2 % | 38.0 % | 38.0 % | XJ |
| Preceding outside trade in the same slot | 65.1 % | 69.6 % | 74.8 % | 74.0 % | XJ |
| Next outside trade after its sell is a SELL | 61.6 % | 63.7 % | 63.4 % | 62.9 % | J exit_next_trade_side (arith) |

- **R:**
  - 86 % of sells come within 1 slot of an outside trade, and 70 % of those trades are sells.
  - The rest are time-cap exits: 79–92 % reactive, the remainder cap (X).
- **Case tokens:**
  - T1/T2: 58/60 sells follow an outside trade within 1 slot (97 %). The 2 exceptions are exactly the 600 s cap. T1: 21/33 sells had a trade **only** in the same slot (in-slot reaction) **[M, C1]**.
  - T3: 16/16. **0 sells in 469 hold slots with no outside trade.** 11 of 16 landed in the same slot, 6–148 positions later **[M, C3]**.
- **Trigger side of sells:**
  - T1: 25/33 behind an outside sell. T2: 20/25. T3: 10/16 (63 % vs a 43 % base).
  - Any size: from 0.005 up to 4.8 SOL. Some exits go into a big outside **buy**: T1 11:00:57 into a 7.87 SOL buy, +29.6 %; 11:57:12 into a 6.45 SOL buy **[M, C1, C3]**.
- **Next trade after its sell:** T1 22/33 sells, T3 12/16 **[M]**.

### 5.2 Hazard factors (what makes a sell more likely)
| factor | finding | source |
|---|---|---|
| Return since entry | **flat**: 2–4 % per outside trade whatever the return (R). T1: 1–5 % with no level pattern. T3: 1.9 / 2.4 / 1.7 / 2.0 / 1.1 % for < −5 %, −5..0, 0..5, 5..15, > 15 % | R, C1, C3 [M] |
| Pause in outside buying | R: 1.4 % → **13 %** after 300+ slots with no outside buy. T1 (s since last outside buy): <1 s 1.5 %, 1–3 s 0.5 %, 3–10 s 2.6 %, **10–30 s 7.3 %**, >30 s 1/3. T3 (slots): ≤2 0.8 %, 3–7 2.4 %, **8–25 6.7 %**, 26–75 0/4 | R, C1, C3 [M] |
| Big outside print | R: a high-volume bot sells, 7.5–11 %. T1: events ≥ 3 SOL 14 % (3/21). T3: sells ≥ 1 SOL 2.6 %, lower than 0.3–1 SOL sells (4.3 %) | R, C1, C3 [M] |
| Followers gone | 8–10 % when the wallets that bought after it have all left | R [M] |
| Side | T1: 5.0 % on an outside sell vs 0.8 % on an outside buy | C1 [M] |
| Net flow over 10 slots | T1: 5.4 % when −0.5..−2 SOL, 0.3–0.8 % when positive | C1 [M] |
| Time held | T1: 0 % in the first 15 s (250 events), then 2.5–3.5 %. T3: none in the first 10 hold slots. Window 11-03: min hold 2 slots, so the T3 "11-slot minimum" is token-specific | C1, C3 [M] |
| Recurring neighbours | T3: 3qvuM3 sold just before 3 of its sells (20 % hazard vs a 1.7 % base). sssssw / 3qvuM3 sell 2–4 positions after it. **[I]** A cohort of similar bots reacting to the same events | C3 [M/I] |

- **Time scale of the pause is token-dependent:**
  - R says "300+ slots".
  - X says "3–10 slots", but C1 calls that too short for T1.
  - C1 (T1): 10–30 s ≈ 25–75 slots.
  - C3 (T3): 3–10 s ≈ 8–25 slots.
  - **[I]** Busy tokens show a shorter pause. The direction is the same everywhere.

### 5.3 No TP/SL; the time cap [M]
- No fixed take-profit, stop-loss or trailing stop.
  - **T2 06:32:50 → 06:38:52:** it held while MC fell **−61 %** across 144 outside trades (~42 SOL of sells, ~23 SOL of buys) and sold at −50 %, P&L −0.354 **[M, C1]**.
  - **T3:** rode trip 15 down −35 % and trip 16 down −31 %, and let trip 1 run to +208 % before selling at +159 % **[M, C3]**.
  - **T1:** median exit +6 % MC. Median giveback from the in-hold peak ~5 points; up to 46 points on big runs **[M, C1]**.
- **Simple exit rules teacher-forced on its real trips** (hit = predicted sell slot within ±1 of its real sell) **[M, XJ e1_rules / X H3]**:
  - The best is "drawdown from peak since buy ≥ 3 %": hit 18.6 / 19.4 / 20.6 / **21.9 %**, early 50–55 %, late 24–28 %.
  - "First outside sell ≥ X SOL": X 0.05–0.5 hits 14–18 %, but fires early 60–80 %.
  - "No outside buy for K slots": K 5 hits 9.6–15.7 %.
  - "Stop −2 %": 13.4–15.7 %.
  - X sums it up: best rule ~22 %; "first outside sell ≥ X" 16–18 % and 72–78 % too early.
- **Frozen 13-rule sell tree:** test precision **16.9 %**, recall **17.2 %** (base 2.9 %) **[M, XJ H3_tree_sell_frozen]**.
- **GBDT ceiling for sells:** AUC 0.84. Precision **30.7 % at 5 % recall**, 26.8 % at 10 %, **20.5 % at 25 %**. Top features: buy SOL in the last 3 slots, buys in the last 3 slots, time since its buy **[M, XJ gbdt_bound_sell]**.
- **Time cap:** forced exits are the loss bucket. TIMER n 2,188, **−93.86 SOL**, LAUNCH at the cap −109 mSOL/trip with a 4 % win rate **[M, J]**. **[I]** These are tokens that died under it, with no outside trade to sell into.

### 5.4 How much its exit timing is worth [E, J exitshift: its picks, us entering 70 ms after its trigger, 9pQQ removed, sell at its real sell time + shift; SOL per recording]
| shift | −5 s | −2 s | −1 s | −424 ms | **−212 ms (1 slot early)** | −100 ms | **0** | +50 ms | +100 ms | +212 ms | +424 ms | +1 s | +2 s | +5 s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10-28 | −17.9 | +1.6 | +15.7 | +23.0 | **+26.9** | +25.9 | −5.7 | −12.0 | −14.0 | −16.3 | −20.4 | −33.7 | −40.9 | −55.8 |
| 10-30 | +37.0 | +71.1 | +92.3 | +109.2 | **+115.0** | +110.9 | +32.3 | +8.1 | +5.7 | +3.2 | +1.9 | −9.4 | −23.2 | −34.0 |
| 10-31 | +8.6 | +31.9 | +49.7 | +65.9 | **+70.4** | +68.1 | +13.5 | −3.3 | −3.3 | −2.1 | −3.9 | −8.1 | −17.8 | −30.0 |
| 11-02 | −1.4 | +22.8 | +42.1 | +64.7 | **+70.1** | +67.7 | +0.1 | −18.7 | −16.6 | −12.0 | −14.2 | −18.5 | −30.8 | −41.9 |

- **Sharp peak just before its real sell:** selling 1 slot earlier is worth +70..+115 SOL per recording (+27 on 10-28), against ~0..+32 at its actual time. Landing 50–212 ms later costs 12–19 SOL on 11-02.
- **[I]** Its sell lands on, or right after, the start of a fall: it sells on the first sign of one, in the same slot.
- **After its sell the price keeps falling [M, J]:**
  - mean move 25 slots later: −2.0 / −1.0 / −0.7 / −0.6 %;
  - 150 slots later: −4.1 / −3.4 / −2.1 / −3.6 %;
  - medians: 0 and −1.0..−2.1 %.

### 5.5 Why its exit cannot be reproduced [M/E]
- **R learned exit** (GBDT "sells next", 13 on-chain features). AUC 0.81 train / 0.82 (10-31) / 0.80 (11-02). As our exit on its picks at 70 ms (θ = 0.05 chosen on 10-31): **−21.2 / −11.4 / −11.7 / −11.8 mSOL/trip**, against its real exit at our delay: −2.6 / +1.4 / −0.5 / −2.3 **[E, J exit_learned_70ms]**.
- **R simple rule family** ("drought N slots / big sell ≥ X / cap C"). Best on train = (12 slots, 2.0 SOL, 150 slots): −15.1 / −8.8 / −10.7 / **−10.5** mSOL/trip **[E, J exit_rules_70ms]**.
- **Fixed holds** at 70 ms on its picks (mSOL/trip) **[E, J replica]**:
  - 1 slot −14.7..−15.3;
  - 6 slots −11.0..−11.7;
  - 30 slots −9.4..−16.0;
  - 150 slots −14.6..−25.4.
- **[I]** Its sell reacts in-slot to the first trade of a fall. By the time a 50–90 ms follower sees that trade, the useful moment has passed (table 5.4). Any rule we compute from landed trades lands at least one event too late.

---

## 6. Case studies (blind; each agent wrote PHASE1 before reading any study, then checked the claims in PHASE2)

### 6.1 The tokens
| | T1 `D2496au7NBgTdd6AHA7kTEMgBc3K7BE9dGoqkkjKpump` "0xUNKNOWN" | T2 `7aFTe3SqvpW1ogwo2ss8wecfQcofenEgy7cQvPDdpump` "Ascend" | T3 `CsGVEXJD7kebRoyJG4Hkt6SjDYZuwnAraC9hnAz5pump` "out of memes" |
|---|---|---|---|
| Created | 11-03 10:33:05, slot 464782356 | 10-29 16:28, slot 462864189; dead, then revived 11-03 06:00–08:00 | 11-03 11:40:14, slot 464801232, CreateV2, creator EHGCR9gy |
| Data | local recorder run_20261102_1250: 2,521 trades, 237 errored txs to 12:10:15; public RPC for the tail | **recorder has none of the revival** (only 10 launch-hour trades). All from public RPC: 76 txs on its ATA `BiLcCTHf…`, trades in s−3..s+3 (s−10..s+3 in PHASE2) around each action, full tapes for 3 holds | local recorder, whole life: 15,952 txs, 2,569 successful trades, **13,102 failed** (spam from tejiF 7,059, 74NEdB 1,952, …, mostly error 6001) |
| 9pQQ activity | 34 buys + 34 sells, 2 failed buys (6042), 24 CloseAccount txs | 28 buys + 27 sells (last buy 12:09:32 open), 0 failed, 21 cleanup txs. First trade at token age 109.5 h | 16 trips + 1 failed buy (6042), 11:40:18 → 11:52:16 |
| Net P&L | **+1.479** (19/34 won) | **+1.453** (13/27); +0.99 from one trip (06:05:48 → 06:08:03, MC 38.7 → 91.2) | **+0.9998** (8/16 won); trip 1 alone +1.047, the other 15 **−0.047** |
| Hold | median 64 s, 15–397 s | median 74 s, 3–**600** s | 2–56 s (11–262 slots), median ~12 s |
| Median MC return | +6.4 % | −0.1 % | trip median +0.009 SOL |
| Our bot (EgxfY…) | one shared dump (6.4) | absent | **zero txs** |

### 6.2 Claim-by-claim verdicts (R and X claims, checked on T1/T2 by C1 and on T3 by C3)
| # | claim (source) | T1/T2 (C1) | T3 (C3) | net verdict |
|---|---|---|---|---|
| 1 | One buy + one full sell; one position per token (R, X) | HOLDS (61/61 sells = exact bought amount) | HOLDS (strict B,S on all 338 tokens) | **proven** |
| 2 | BuyExactQuoteInV3 700,000,000 incl. pump fees (X) | HOLDS 62/62 | HOLDS 16/16; 1,157/1,157 in the window | **proven** |
| 3 | CU 1,500,001; 130k/80k; Astralane 1M/0.1M + Jito 17.5k; 1.46 mSOL/trip | HOLDS, 124 txs | HOLDS, 2,307 txs | **proven** |
| 4 | One tx per decision, no copies, no nonce (R) | HOLDS | HOLDS | **proven** |
| 5 | Failed buys 4–8 %, mostly 6042 (R) | HOLDS: T1 2/36 (5.6 %), T2 0 | HOLDS: 1/17 (5.9 %) | holds |
| 6 | Never mayhem | holds (weak: neither token is mayhem) | holds (weak) | proven on population (0/28,240) |
| 7 | Never buy before age 8; most at 10–11 (X) | HOLDS (T1 first buy at 10) | HOLDS (19). In the window min 8, peak 11, but 89/313 first buys came after ≥ 60 slots | "most at 10–11" only among early entries |
| 8 | +2-slot spacing (X) | HOLDS (a failed re-buy at exactly sell + 2) | HOLDS (window min hold 2, min gap 2) | **proven** |
| 9 | Cap 300 → 600 s; forced exits lose | HOLDS (two 600 s exits, both lost: −0.151, −0.065) | HOLDS (61 holds at 590–601 s in the window) | **proven** |
| 10 | 98 % of buys follow an outside trade (same/prev slot) | HOLDS 61/61 (base 12 %) | HOLDS 16/16; 0/934 empty flat slots | **proven** |
| 11 | Sells follow an outside trade, rest = cap | HOLDS 58/60, 2 = cap | HOLDS 16/16; 0/469 | **proven** |
| 12 | ~70 % of reactive sells follow an outside sell | HOLDS (~78 %) | holds, weaker (63 % vs 43 % base) | holds |
| 13 | Buy ~45 ms, 67–69 % same slot | holds (~70 % same slot; median 50/73 positions) | **PARTLY** (50 %; ~36 positions) | token-dependent share |
| 14 | Slow on dumps; first outside buyer 33–37 % | **mixed:** slow vs us on the one shared dump, but first after the dump on 13/18 of its own dip buys (7 in the dump's slot) | **NOT CONFIRMED** without us: first on 4/9 (44 %), 2nd on 2, 3rd–5th on 3 | aggregate 33–37 % (R) is the best-supported number |
| 15 | No TP/SL; flat hazard by return | HOLDS (2.2 % over 1,489 events) | HOLDS | **proven** |
| 16 | Sell chance rises when buying pauses | HOLDS; peak at 10–30 s | HOLDS; peak at 3–10 s | direction proven; scale is token-dependent |
| 17 | Rises on big prints / high-volume bot sells | holds by size (≥ 3 SOL 14 %) | not testable / weak | R aggregate only |
| 18 | Next trade after its sell is a sell 63 % | HOLDS (T1 22/33) | HOLDS (12/16) | **proven** |
| 19 | Ignores < 0.05 SOL trades | HOLDS for buys only; 6/58 sells triggered by < 0.05 | HOLDS for buys; 3/16 sells by 0.005–0.048 | **buy-side filter only** |
| 20 | Follows buys more than sells | HOLDS (24/33, 23/28) | **CONTRADICTED** (9/16 = base; size matters, not side) | token-dependent |
| 21 | Curve 32–50 preferred, ≥ 80 avoided; 30–112 range | range holds; 6/33 T1 buys ≥ 80 (net +0.044) | range holds; 4/16 ≥ 80; most buys at 57–78 | preference, not a rule |
| 22 | Skips quiet flow | soft (8/33, 5/28 quiet) | soft (1/16) | soft |
| 23 | Re-entry dominates (68 %) | HOLDS, more extreme (60/62) | HOLDS (15/16) | **proven** |
| 24 | Re-entry within 25 slots is best | not testable (n 5: −15 mSOL; n 4: +337 from one trip) | not testable (n 1) | aggregate only |
| 25 | Lanes: DIP best | **CONTRADICTED** (MOMO/DRIFT won) | **CONTRADICTED** (LAUNCH > MOMO > DIP; DIP −5.2 mSOL) | **lane ranking is token-dependent** |
| 26 | Not a leader-wallet copier | HOLDS | HOLDS | **proven** |
| 27 | 41Pr4XqE enriched, 6–9 % of buys | holds (T1 2/33, T2 0) | holds (2/16 windows) | lead only |
| 28 | Followers 2.0–2.4 wallets / 0.8–1.1 SOL in 3 slots | lower (T1 1.09 / 0.49; T2 0.54 / 0.09) | higher (4.4 / 1.23, a busy token) | token-dependent |
| 29 | Up to 25–32 open positions | not testable (2 at once) | consistent (5–12, up to 17) | X aggregate |
| 30 | Slippage ~10–15 % (inferred) | consistent (+17 %, +21 % adverse moves) | consistent (+17..+24 %) | inferred |
| 31 | 0.5 vs 0.48 SOL period | reports disagree | not testable | **resolved in 3.2: 0.48 quote, 0.5 = rounded label** |

### 6.3 What the case studies added
- **Sells are in-slot reactions too:** 21/33 T1 sells had a trade only in the same slot, typically 30–100 positions earlier. **[I]** The same feed drives buys and sells **[M/I, C1]**.
- **The edge is a few big rides held through a flat-hazard exit.** On T2 and T3, one trip made nearly all the money and the other trips netted about 0. Across the 11-03 window: 1,145 trips, +8.5 SOL in 3.15 h, win 40 %, median trip −0.018 **[M, C3]**.
- **A copy-bot follows 9pQQ:** `8d1YSS1uVDWg6SdpGudUAMzHzp569ksrYFtvFzixMwgL` **[M, C3]**.
  - It buys 0.049 SOL after 15 of 16 of its T3 buys, in the same slot (61–225 positions later) or the next.
  - It sells **13–15 slots after each 9pQQ sell** (14/15).
  - Its economic effect is nil, but it shows 9pQQ's fills are visible and copied.
- **The recorder misses revived old tokens.** T2 has 0 recorded trades on 11-03 **[M, C1]**. Studies built only on the recordings undercount this part of its trading.
- **Contradictions between the cases:**
  - buy behind a buy (T1/T2) vs behind either side (T3);
  - which side pays (momentum on T1/T2, dips on T3);
  - same-slot share 70 % vs 50 %;
  - pause scale 10–30 s vs 3–10 s;
  - fast on dumps without us: 13/18 (T1/T2) vs 4/9 (T3).
  - **Read all of these as token-dependent.**

### 6.4 T1: 9pQQ vs our bot on the one shared dump [M, C1]
| slot / idx | who | what |
|---|---|---|
| 464782537–540 | us | 26 pre-sent buys fail with 6042 (price not yet down to our limit) |
| 464782540 / 157 | 8GgR | dumps 3.81 SOL |
| 464782540 / 173 | **us** | **buy 0.543 SOL at MC 42.96, in the dump slot, 16 positions after it** |
| 464782541 / 1, 33 | 5KcK (41Pr4 bot), E2x1 | buy 1.68 and 0.36 |
| 464782541 / 85 | **9pQQ** | **buy fails 6042, one slot late; price already rebounded** |
| 464782541 / 185 | us | sell at MC 46.51, ~+0.06 SOL gross |
| 464782634 / 95 | 9pQQ | first successful re-entry (dip-buy behind 5KcK's 1.14 SOL sell). Then 33 more trips, +1.48 total. We did not trade T1 again |

### 6.5 Per-trip tables [M, C1 PHASE1, C3 PHASE1; CSV t1_actions.csv / t2_actions.csv, cases3/trips.json]
**T1** (age in slots, or h; trigger = last outside trade before its tx: wallet, side, SOL, Δslot, block idx trigger → its tx)
| # | buy | slot/idx | age | buy MC | buy trigger | sell | sell trigger | hold s | MC ret % | P&L |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 10:33:08 | 464782366/227 | 10 sl | 38.4 | HZxQ S 1.67 (Δ0, 174→227) | 10:33:36 | 5MD7 S 1.02 (Δ1) | 28 | −9.9 | −0.0617 |
| – | 10:33:45 FAILED (6042) | 464782541/85 | | | E2x1 B 0.36 (Δ0) | | | | | |
| 2 | 10:34:05 | 464782634/95 | 278 sl | 43.4 | 5KcK S 1.14 (Δ0) | 10:36:39 | J6YE S 0.41 (Δ1) | 154 | −13.5 | −0.0892 |
| 3 | 10:36:42 | 464783376/665 | 1020 sl | 43.2 | 8aVt B 1.24 (Δ0) | 10:37:45 | EMKY S 0.20 (Δ0) | 63 | +6.8 | +0.0566 |
| 4 | 10:38:18 | 464783827/220 | 1471 sl | 53.1 | BUkp B 0.75 (Δ0) | 10:39:34 | EMKY S 0.52 (Δ1) | 76 | +19.6 | +0.1447 |
| 5 | 10:40:56 | 464784566/109 | 2210 sl | 68.2 | 4vgK B 1.78 (Δ0) | 10:41:17 | 4vgK S 0.23 (Δ1) | 21 | +13.9 | +0.1006 |
| – | 10:41:17 FAILED (6042) | 464784663/192 | | | E2x1 B 0.99 (Δ0) | | | | | |
| 6 | 10:41:34 | 464784737/268 | 2381 sl | 68.8 | ssss B 0.82 (Δ0) | 10:42:30 | 47du S 0.03 (Δ0) | 56 | −21.6 | −0.1508 |
| 7 | 10:42:39 | 464785044/270 | 2688 sl | 58.5 | ssss B 0.23 (Δ0) | 10:43:45 | STor S 0.67 (Δ0) | 66 | +6.4 | +0.0493 |
| 8 | 10:44:06 | 464785452/47 | 3096 sl | 64.9 | EyQg B 0.49 (Δ1) | 10:46:43 | JDFD S 3.43 (Δ0) | 157 | +31.6 | +0.2273 |
| 9 | 10:46:48 | 464786208/256 | 3852 sl | 71.3 | ERwF S 0.16 (Δ0) | 10:47:21 | 9QLF B 0.11 (Δ0) | 33 | +20.3 | +0.1456 |
| 10 | 10:48:03 | 464786565/233 | 4209 sl | 78.9 | GaBq B 0.30 (Δ1) | 10:48:34 | ssss S 0.76 (Δ0) | 31 | −9.1 | −0.0639 |
| 11 | 10:48:40 | 464786733/89 | 4377 sl | 73.3 | ssss B 0.25 (Δ0) | 10:51:07 | BUkp S 0.80 (Δ1) | 147 | −6.7 | −0.0460 |
| 12 | 10:51:12 | 464787443/69 | 0.3 h | 73.6 | ssss B 0.26 (Δ1) | 10:55:03 | G4Nv S 1.67 (Δ1) | 231 | −2.0 | −0.0127 |
| 13 | 10:55:38 | 464788689/136 | 0.4 h | 93.1 | 8aVt B 2.45 (Δ0) | 10:55:53 | ARu4 S 0.34 (Δ0) | 15 | −2.1 | −0.0160 |
| 14 | 10:57:39 | 464789258/63 | 0.4 h | 107.5 | 8aVt S 2.32 (Δ1) | 10:58:06 | BbZG B 0.27 (Δ0) | 27 | +8.6 | +0.0579 |
| 15 | 10:58:41 | 464789549/155 | 0.4 h | 122.9 | ssss B 0.33 (Δ0) | 10:59:04 | 6F6w S 0.40 (Δ1) | 23 | +1.0 | +0.0035 |
| 16 | 10:59:57 | 464789906/77 | 0.4 h | 160.6 | 8PgC B 1.30 (Δ0) | 11:00:57 | J1Pz B 0.40 (Δ0) | 60 | +29.6 | +0.2021 |
| 17 | 11:01:47 | 464790422/137 | 0.5 h | 170.6 | HcSY S 0.55 (Δ0) | 11:02:04 | ssss S 0.44 (Δ0) | 17 | +7.9 | +0.0491 |
| 18 | 11:03:37 | 464790943/141 | 0.5 h | 182.0 | 7aai B 1.98 (Δ0) | 11:04:39 | GKd5 S 0.42 (Δ0) | 62 | −5.1 | −0.0420 |
| 19 | 11:04:40 | 464791234/98 | 0.5 h | 170.3 | 4qqD B 1.07 (Δ0) | 11:06:29 | ssss S 0.41 (Δ0) | 109 | −2.0 | −0.0196 |
| 20 | 11:07:03 | 464791904/519 | 0.6 h | 176.7 | 9rjq B 2.15 (Δ0) | 11:08:07 | 5pw5 S 1.70 (Δ1) | 64 | −4.5 | −0.0372 |
| 21 | 11:09:04 | 464792469/246 | 0.6 h | 181.4 | ssss B 0.41 (Δ0) | 11:09:44 | 8KQs S 0.10 (Δ0) | 40 | −2.5 | −0.0235 |
| 22 | 11:13:15 | 464793647/29 | 0.7 h | 153.0 | GbtR B 0.88 (Δ1) | 11:13:58 | X7NM S 4.79 (Δ0) | 43 | −10.8 | −0.0808 |
| 23 | 11:22:13 | 464796180/7 | 0.8 h | 121.1 | Eavv B 0.24 (Δ1) | 11:25:54 | Gbgr S 0.40 (Δ0) | 221 | +30.9 | +0.2138 |
| 24 | 11:29:07 | 464798115/179 | 0.9 h | 171.8 | omeg B 1.05 (Δ0) | 11:34:38 | FmrN S 0.08 (Δ0) | 331 | +44.7 | +0.3069 |
| 25 | 11:35:12 | 464799822/13 | 1.0 h | 216.2 | 9H17 B 0.12 (Δ1) | 11:37:45 | 5S6X B 0.11 (Δ0) | 153 | +9.2 | +0.0570 |
| 26 | 11:39:05 | 464800913/9 | 1.1 h | 225.4 | 56o9 S 3.03 (Δ1) | 11:45:42 | FWtt B 0.01 (Δ1) | 397 | −23.7 | −0.1727 |
| 27 | 11:45:47 | 464802787/200 | 1.2 h | 166.8 | Aw9P S 1.81 (Δ1) | 11:47:35 | ssss S 1.36 (Δ0) | 108 | −6.8 | −0.0534 |
| 28 | 11:48:09 | 464803444/254 | 1.3 h | 165.3 | 5Qs4 B 0.38 (Δ0) | 11:50:46 | G4L7 B 0.14 (Δ1) | 157 | +67.1 | +0.4648 |
| 29 | 11:51:53 | 464804494/220 | 1.3 h | 258.3 | Aw9P S 2.41 (Δ0) | 11:52:45 | 4faD S 0.62 (Δ0) | 52 | −4.5 | −0.0394 |
| 30 | 11:53:03 | 464804831/111 | 1.3 h | 230.3 | 9H17 B 0.06 (Δ1) | 11:54:19 | FGfn S 0.14 (Δ0) | 76 | +10.8 | +0.0676 |
| 31 | 11:54:27 | 464805226/273 | 1.4 h | 203.8 | 9H17 S 3.89 (Δ0) | 11:56:00 | W9zs B 0.00 (Δ1) | 93 | +7.2 | +0.0436 |
| 32 | 11:56:41 | 464805860/329 | 1.4 h | 204.6 | 5H9e B 0.57 (Δ0) | 11:57:12 | 6G8C B 6.45 (Δ0) | 31 | +13.6 | +0.0883 |
| 33 | 12:01:00 | 464807076/69 | 1.5 h | 194.0 | ssss B 0.42 (Δ0) | 12:04:38 | 3vKC S 0.16 (Δ0) | 218 | +11.6 | +0.0742 |
| 34 | 12:11:03 | 464809885/544 | 1.6 h | 162.3 | (RPC tail) | 12:13:30 | (RPC tail) | 147 | +5.8 | +0.0349 |

**T2** (age in hours since the 10-29 create)
| # | buy | slot/idx | age h | buy MC | buy trigger | sell | sell trigger | hold s | MC ret % | P&L |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 06:00:35 | 464705835/166 | 109.5 | 32.7 | E4zA B 0.21 (Δ0) | 06:05:45 | 6E8m B 0.00 (Δ0) | 310 | +11.4 | +0.0937 |
| 2 | 06:05:48 | 464707305/161 | 109.6 | 38.7 | 3DVM B 0.37 (Δ0) | 06:08:03 | HANc S 0.33 (Δ1) | 135 | +135.8 | **+0.9923** |
| 3 | 06:08:52 | 464708173/127 | 109.7 | 116.2 | 8tjE B 1.59 (Δ0) | 06:10:06 | HUrr S 0.34 (Δ1) | 74 | −7.2 | −0.0537 |
| 4 | 06:11:10 | 464708825/405 | 109.7 | 63.1 | FTKT B 0.98 (Δ0) | 06:11:13 | G1qG S 1.45 (Δ0) | 3 | −15.4 | −0.1061 |
| 5 | 06:11:15 | 464708844/97 | 109.7 | 62.4 | 9nW5 B 1.98 (Δ1) | 06:11:51 | BzpJ S 0.97 (Δ0) | 36 | +5.1 | +0.0392 |
| 6 | 06:13:46 | 464709553/93 | 109.8 | 83.1 | 94Jp B 0.87 (Δ0) | 06:14:44 | D6Ra S 0.36 (Δ1) | 58 | −13.4 | −0.0944 |
| 7 | 06:14:57 | 464709878/186 | 109.8 | 78.6 | J1Pz B 0.40 (Δ0) | 06:15:15 | 3vKC B 0.11 (Δ1) | 18 | +58.7 | +0.4168 |
| 8 | 06:15:19 | 464709983/88 | 109.8 | 122.8 | 7XLv S 3.48 (Δ1) | 06:18:00 | feky S 0.48 (Δ1) | 161 | +35.1 | +0.2437 |
| 9 | 06:18:29 | 464710865/113 | 109.8 | 121.4 | DVWD B 0.09 (Δ0) | 06:19:39 | 2PFs B 0.10 (Δ0) | 70 | −9.9 | −0.0726 |
| 10 | 06:20:07 | 464711323/428 | 109.9 | 118.3 | 9dr7 B 2.68 (Δ0) | 06:20:56 | G715 S 2.79 (Δ0) | 49 | −14.3 | −0.1032 |
| 11 | 06:21:00 | 464711577/407 | 109.9 | 90.8 | ARu4 B 0.78 (Δ0) | 06:22:14 | 5vtL S 1.07 (Δ0) | 74 | +10.3 | +0.0719 |
| 12 | 06:22:31 | 464712006/172 | 109.9 | 117.4 | HfmT B 1.98 (Δ1) | 06:24:59 | DVWD S 0.10 (Δ1) | 148 | +25.7 | +0.1774 |
| 13 | 06:25:14 | 464712757/144 | 110.0 | 164.4 | 3zUd B 2.95 (Δ0) | 06:25:22 | J1Pz B 0.40 (Δ0) | 8 | +3.1 | +0.0160 |
| 14 | 06:26:14 | 464713039/245 | 110.0 | 189.6 | J1Pz B 0.40 (Δ0) | 06:27:34 | 6KCr S 0.43 (Δ0) | 80 | −21.9 | −0.1595 |
| 15 | 06:27:47 | 464713469/181 | 110.0 | 162.3 | J1Pz B 0.40 (Δ0) | 06:28:17 | J1Pz S 0.68 (Δ0) | 30 | +11.4 | +0.0743 |
| 16 | 06:28:42 | 464713728/243 | 110.0 | 182.9 | 4vgK B 1.78 (Δ0) | 06:29:01 | 67Pt S 0.06 (Δ1) | 19 | −2.0 | −0.0199 |
| 17 | 06:29:14 | 464713875/28 | 110.0 | 186.2 | H1aF B 0.53 (Δ0) | 06:29:42 | 3vKC S 0.63 (Δ0) | 28 | −3.6 | −0.0318 |
| 18 | 06:31:11 | 464714420/84 | 110.0 | 144.3 | 4vgK S 1.46 (Δ1) | 06:31:35 | 3zUd S 2.76 (Δ0) | 24 | −5.5 | −0.0434 |
| 19 | 06:32:50 | 464714878/261 | 110.1 | 119.1 | 33EK S 1.20 (Δ0) | 06:38:52 | 8quZ S 0.91 (Δ0) | 362 | **−50.1** | **−0.3542** |
| 20 | 06:38:59 | 464716614/146 | 110.2 | 63.3 | 2MEp B 1.86 (Δ0) | 06:39:50 | BrfJ S 0.05 (Δ0) | 51 | +26.6 | +0.1922 |
| 21 | 06:40:15 | 464716970/50 | 110.2 | 56.7 | DVWD B 0.09 (Δ1) | 06:43:37 | 7n93 S 0.07 (Δ1) | 202 | +59.2 | +0.4265 |
| 22 | 06:47:45 | 464719076/437 | 110.3 | 86.7 | 7YoC B 0.98 (Δ0) | 06:48:49 | 9t6R S 0.85 (Δ1) | 64 | +2.5 | +0.0174 |
| 23 | 06:54:32 | 464720978/245 | 110.4 | 81.7 | 9hsH B 0.49 (Δ0) | 06:56:45 | DyxF S 0.69 (Δ1) | 133 | −0.1 | −0.0002 |
| 24 | 06:59:40 | 464722431/90 | 110.5 | 53.6 | 2tzv S 1.14 (Δ1) | 07:02:29 | 8ez9 S 0.03 (Δ0) | 169 | −10.7 | −0.0717 |
| 25 | 07:15:15 | 464726809/61 | 110.8 | 55.5 | F2on B 0.66 (Δ0) | 07:25:15 | none in 3 slots (**cap**) | **600** | −21.8 | −0.1508 |
| 26 | 07:47:44 | 464735914/45 | 111.3 | 46.5 | 676a B 1.47 (Δ1) | 07:57:44 | none in 3 slots (**cap**) | **600** | −10.1 | −0.0652 |
| 27 | 11:55:09 | 464805422/176 | 115.4 | 37.8 | 766H S 0.84 (Δ0) | 11:59:41 | B1aX B 0.22 (Δ0) | 272 | +1.2 | +0.0183 |
| open | 12:09:32 | 464809462/71 | | 43.4 | 9eCe B 1.08 (Δ1) | (open at data end) | | | | |

**T3** (slot = +N slots after create; MC in SOL; pos = block position)
| # | buy | buy slot/pos | entry MC | last outside trade before buy | sell slot/pos | last outside trade before sell | hold s (slots) | MC move | hold hi/lo | net SOL |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 11:40:18 | +19/398 | 48.5 | S 0.185 B7A4wo, same slot −33 pos | +190/36 | S 1.195 sssssD, same slot −14 | 37 (171) | +158.9 % | +208.3/0.0 % | **+1.0474** |
| 2 | 11:41:40 | +397/102 | 149.6 | B 1.246 8PgC4n, same slot −8 | +408/414 | S 0.747 46x7gJ, same slot −15 | 2 (11) | −0.6 % | +1.6/−0.6 % | −0.0227 |
| 3 | 11:42:15 | +560/1 | 118.0 | B 1.956 kjcByy (terminal), prev slot | +597/4 | B 0.01 2ZcPMx, prev slot | 8 (37) | −2.7 % | +0.9/−7.2 % | −0.0372 |
| 4 | 11:42:33 | +646/24 | 105.8 | B 0.099 AEgTuy, prev slot | +661/8 | S 0.267 EVHyQo, prev slot | 3 (15) | +2.6 % | +3.5/0.0 % | −0.0014 |
| 5 | 11:42:51 | +728/279 | 104.2 | S 5.011 HNGC6P, same slot −235 | +744/62 | B 0.005 6EGAmV, prev slot | 3 (16) | +8.3 % | +8.3/0.0 % | +0.0376 |
| 6 | 11:43:36 | +939/11 | 207.6 | B 0.393 EMKY7r, prev slot | +1089/260 | B 0.107 CZqUKy, same slot −72 | 31 (150) | +28.1 % | +28.1/−0.2 % | +0.1721 |
| 7 | 11:44:12 | +1111/47 | 251.8 | B 0.988 4GCtzC, same slot −38 | +1142/55 | S 0.488 sssssw, prev slot | 6 (31) | −2.2 % | +2.2/−10.2 % | −0.0324 |
| 8 | 11:44:55 | +1314/155 | 210.9 | B 0.435 sssssw, same slot −17 | +1365/105 | S 0.011 ATi4gb, same slot −69 | 11 (51) | −5.5 % | +4.9/−5.5 % | −0.0562 |
| 9 | 11:45:11 | +1390/15 | 145.1 | S 4.312 AGqjiv, prev slot | +1510/178 | B 0.196 BVcDry, same slot −86 | 26 (120) | +23.4 % | +27.8/−6.1 % | +0.1401 |
| 10 | 11:45:50 | +1568/80 | 146.9 | B 0.132 BffUuV, same slot −58 | +1605/176 | B 0.054 FhNfLj, same slot −14 | 8 (37) | +12.0 % | +13.2/−10.9 % | +0.0627 |
| 11 | 11:46:16 | +1686/42 | 161.2 | B 0.127 C1q5U6, prev slot | +1859/286 | S 0.425 3qvuM3, same slot −22 | 37 (173) | +9.0 % | +14.1/−2.3 % | +0.0426 |
| 12 | 11:47:19 | +1978/210 | 190.3 | S 0.071 6Qt8a3, same slot −33 | +2114/76 | S 0.482 3qvuM3, same slot −12 | 29 (136) | +8.1 % | +18.3/0.0 % | +0.0366 |
| 13 | 11:48:22 | +2274/74 | 233.8 | B 1.59 8PgC4n, prev slot | +2536/318 | S 1.495 8PgC4n, same slot −6 | 56 (262) | −10.8 % | +3.5/−12.0 % | −0.0919 |
| 14 | 11:49:57 | +2721/96 | 171.5 | S 1.296 3coRw7, prev slot | +2769/142 | S 0.364 3qvuM3, same slot −88 | 11 (48) | +5.6 % | +6.6/−2.5 % | +0.0193 |
| 15 | 11:51:26 | +3140/5 | 101.7 | S 0.601 2UMRu7, prev slot | +3230/167 | S 0.048 AEzWaG, prev slot | 19 (90) | −16.4 % | +0.0/−34.9 % | −0.1302 |
| 16 | 11:52:03 | +3315/159 | 72.7 | B 0.491 ARnjeA, same slot −94 | +3372/222 | B 0.098 55JY6a (terminal), same slot −148 | 13 (57) | −24.7 % | +0.0/−30.8 % | −0.1866 |

- **T3 failed buy:** slot +934, position 144, error 6042. Slots +932/+933 had no trades. Slot +934 opened with buys of 6.84 SOL (pos 0), 5.93 (pos 76) and 1.48 (pos 86), moving MC 147 → 215 before its tx. It re-bought 5 slots later (trip 6). This is clean evidence of an **in-slot reaction** to a trade-driven spike **[M, C3]**.

---

## 7. Interactions

### 7.1 With us (our wallet EgxfYgEb, the AMS pre-send engine)
**On shared dumps it is our FOLLOWER [M, J interact]**. Counts are its DIP entries where our buy on the same dump (within 3 slots) came before vs after its buy:

| recording | its DIP trips | we bought before it | we bought after it |
|---|---|---|---|
| 10-28 | 2,173 | 34 | 2 |
| 10-30 | 4,218 | 64 | 7 |
| 10-31 | 3,454 | 52 | 6 |
| 11-02 | 3,801 | 27 | 3 |

**Our real round trips split by what 9pQQ did around them [M, J interact "ours"; real P&L incl. fees; mSOL per trip]**
| recording | 9pQQ absent | 9pQQ bought ≤ 10 slots BEFORE us | 9pQQ SOLD inside our hold | **9pQQ bought AFTER us inside our hold** |
|---|---|---|---|---|
| 10-28 | 566 / +9.79 | 7 / +1.15 | 6 / −12.93 | **19 / +15.47** |
| 10-30 | 417 / +9.48 | 28 / +24.55 | 8 / +24.98 | **47 / +45.64** |
| 10-31 | 435 / +10.84 | 29 / +8.10 | 13 / −21.80 | **21 / +38.58** |
| 11-02 | 281 / −1.53 | 13 / **−26.74** | 4 / −34.03 | **15 / +59.35** |

Cells are n / mSOL per trip.

- **Second measurement (MEM, botpnl method):**
  - When it buys **after** us we make **+22..+35 mSOL/trip** (10-28..11-02; +24 on 11-02), on 40–100 of our trades a day.
  - When it bought **before** us on 11-02: **−31 mSOL/trip (n 12)**.
  - The tape method above gives +15.5 / +45.6 / +38.6 / +59.4 (after) and −26.7 (before, n 13). Both agree on direction: **it is one of our last paying followers**, and when it is ahead of us we lose.
- **It selling in our hold:** only 31 trips over 4 recordings. −13 / −22 / −34 mSOL on three, +25 on 10-30 **[M, R]**.
- **Speed vs us:**
  - On dumps it lands 130–152 ms after (p50); we land at 50–90 ms.
  - On T1's shared dump we landed in the dump slot (i 173) and it failed one slot later (section 6.4) **[M, J, C1]**.
  - **Do not assume** it is slow everywhere: without us it was first after the dump on 13/18 dip buys (T1/T2) but only 4/9 (T3) **[M, C1, C3]**.
- **Our trips by 9pQQ's history on the token** (at our buy; mSOL/trip; "came" = share where it then bought in our hold) **[M, J ours_k]**:

| recording | never traded by 9pQQ | traded before (not holding) | holding now |
|---|---|---|---|
| 10-28 | 500 / +8.8 / came 3 % | **80 / +19.4** / 5 % | 12 / −9.0 |
| 10-30 | 360 / +8.9 / 5.6 % | **94 / +29.5** / 28.7 % | 38 / +21.1 |
| 10-31 | 377 / +12.2 / 2.1 % | **75 / +17.1** / 17.3 % | 33 / −4.1 |
| 11-02 | 247 / −1.9 / 2.4 % | **43 / +15.5** / 20.9 % | 19 / −4.9 |
| quieter tokens (< 200 trades), never vs traded-before | +8.6 / +8.7 / +11.7 / −3.2 vs **+15.1 / +31.0 / +12.2 / −0.3** | | |
| busy tokens (≥ 200 trades), traded-before | +27.9 (n 27) / +25.6 (27) / +40.3 (13) / +75.1 (9) | | |

- **Overlap with our own concerns:**
  - It is part of the follower cohort that pays our dip trades (MEM / profit-source-bot-cohort, BRIEF: "trades where a bot buys in our slot or after us made +20..+25 mSOL").
  - Our BRIEF (11-03) notes several paying followers (DF7eRX, HLU8QbLd, DSvgfynk, CvHEVC7S, 6VzXcLk9) stopped by 11-02. **9pQQ has not stopped.** Its P&L grew 10-28 → 11-02 **[M]**.
- **Observatory:** haqq6qnV and 9pQQc1xy were added to the AMS observatory watch list on 11-03 (`/root/sniper-dip/obs_watch.txt` md5 7f5f0214, backup `.pre-1103`; local `ops/obs/watch_default.txt`). Effective from the next run start **[M, MEM]**.

### 7.2 With other dump bots (who bought the same dump before / after its DIP entries, within 3 slots) [M, J interact dip_same_dump]
| bot | 10-28 before / after | 10-30 | 10-31 | 11-02 |
|---|---|---|---|---|
| 8yYMhu | 104 / 41 | 215 / 50 | 164 / 38 | **163 / 29** |
| haqq (haqqiUUX on 10-28, haqq6qnV from 10-31; 2VggYpPu, the 10-30 wallet, was not in the list) | 207 / 141 | – | 155 / 86 | **331 / 209** |
| E2x1 | 43 / 59 | 66 / 73 | 82 / 62 | **93 / 91** |
| Grozoe | 22 / 26 | 33 / 38 | 30 / 18 | 33 / 27 |
| OURS | 34 / 2 | 64 / 7 | 52 / 6 | 27 / 3 |

- **8yYMhu** is mostly ahead of it (in-slot reaction 33–37 ms; memory rival-8yymhu).
- **haqq** (one bot across wallets haqqiUUX → 2VggYpPu → haqq6qnV; BRIEF) is ahead more often than behind.
- **E2x1** is about even. It is also the top **sell-leader** in X's H1 sells list: E2x1's sells are followed by 9pQQ's sell at 10.8 % (118/1,093) **[M, XJ h1_test]**.
- The 41Pr4 bot 5KcK (`41Pr4XqE` program) is an enriched buy trigger (4.7).

### 7.3 Its followers and co-traders [M, J interact]
| recording | wallets buying within 3 slots after its buy (per trip) | SOL (per trip) | top follower (count, share of its trips) | other frequent |
|---|---|---|---|---|
| 10-28 | 2.40 | 1.11 | ssssswdk 422 (10.0 %) | haqqiUUX 145, sssssDdM 133, 6irYUcN2 112, EMKY 107, E2x1 80 |
| 10-30 | 2.02 | 0.85 | ssssswdk 1,020 (11.5 %) | 6irYUcN2 419, sssssDdM 272, 2VggYpPu 265, 6Qt8a3Y6 256 |
| 10-31 | 2.15 | 0.83 | ssssswdk 617 (8.5 %) | 3qvuM3U5 447, 6irYUcN2 281, 6Qt8a3Y6 235 |
| 11-02 | 2.20 | 0.92 | ssssswdk 839 (10.9 %) | 3qvuM3U5 525, sssssDdM 274, 2Dd3TRSd 233, EMKY 231, haqq6qnV 197, E2x1 179 |

- **First buyer after its sell:**
  - omegoMAe1A: 14 / 55 / 40 / 50 per recording;
  - ssssswdk: 23 / 43 / 42 / 77.
- **Wallets whose sell precedes its sell:** ssssswdk 73 / 307 / 197 / 279, then 3qvuM3U5, 8PgC4ngp, 6irYUcN2, E2x1, sssssDdM, STorreSu.
- **Case tokens:**
  - ssssswdk bought within 3 slots **after** 8/33 of its T1 buys and **before** 7/33. It is a **co-trader** as often as a follower **[M, C1]**. The same pattern holds on T3 (2 after / 3 before) **[M, C3]**.
  - Followers per buy: T1 1.09 wallets / 0.49 SOL, T2 0.54 / 0.09, T3 4.4 / 1.23 (busy token) **[M]**.
- **Copy-bot `8d1YSS1uVDWg6SdpGudUAMzHzp569ksrYFtvFzixMwgL`:**
  - Buys 0.049 SOL after 15/16 of its T3 buys (same or next slot).
  - Sells 13–15 slots after its sells (14/15).
  - Tiny size, no economic effect. It proves 9pQQ is watched and copied **[M, C3]**. Not checked on other tokens.
- **Bait responder:** in the 10-24 pattern search, 9pQQc1xy (B301) and ssssswdk were the responders to "quiet bait" first-buys **[M then, MEM / strategy-families.md]**.

---

## 8. Copy and replication attempts (none reproduces it: verdict "not cracked"; the +70 ms rows are information only, owner rule 11-03)

The replay machinery is calibrated **[M, J replica; XJ c1_calib]**:
- Curve maths: vtok = curve balance + 73e12; chain clock = slot × 212 ms + position / block size × 212 ms (rlib9.py).
- Its own trips replayed at its exact times give 18.91 / 79.90 / 63.70 / 52.78 against real 18.84 / 79.85 / 63.66 / 52.76, with correlation 1.0 (r1_replica, using its real spend).
- X's sim (fixed 0.7 SOL) misses 10-30 (100.56 vs 79.85). **[I]** That is because it used 0.7 SOL for the 5,250 buys of 0.48. X therefore quotes only the other three days.

### 8.1 Its picks + its real exit, us late by delta [E, J replica]
Setup: we land delta ms after the trade it reacted to and sell (delta − 45) ms after its sell. 0.55 SOL, 4.5 mSOL/trip, 9pQQ removed from the curve. Values are **SOL/day**; mSOL/trip in brackets for key rows.

| row | 10-28 | 10-30 | 10-31 | 11-02 |
|---|---|---|---|---|
| 0 ms, its exit | +0.7 (+0.17) | +51.8 (+5.92) | +27.0 (+3.80) | +25.2 (+2.20) |
| 0 ms, −20 % followers | −20.7 | +15.3 | −1.8 | −25.9 |
| 0 ms, at its 1.5 mSOL cost | +13.3 | +78.0 | +48.4 | +59.7 |
| 50 ms | −7.2 | +28.6 | +9.6 | −9.1 |
| 50 ms, −20 % followers | −29.4 | −9.2 | −19.4 | −61.9 |
| 50 ms, its cost | +5.3 | +54.9 | +30.9 | +25.3 |
| **70 ms** | **−10.8** (−2.59) | **+12.4** (+1.41) | **−3.3** (−0.47) | **−26.5** (−2.31) |
| 70 ms, −20 % followers | −33.4 | −25.6 | −33.2 | −79.8 |
| 70 ms, its cost | +1.7 | +38.6 | +18.0 | +7.9 |
| 90 ms | −13.4 | +4.1 | −7.6 | −34.6 |
| 90 ms, −20 % followers | −36.1 | −34.3 | −37.8 | −88.2 |
| 90 ms, its cost | −0.8 | +30.4 | +13.8 | −0.1 |
| 70 ms, net without top 5 (SOL per recording) | −16.61 | +5.96 | −10.88 | −24.77 |

**By lane and hold band at 70 ms, its exit [E, J replica; SOL/day]**
| subset | 10-28 | 10-30 | 10-31 | 11-02 |
|---|---|---|---|---|
| LAUNCH (all) | +5.1 | +1.1 | +9.2 | +5.3 |
| … w/o top 5 (SOL per recording) | −0.21 | −3.54 | +4.54 | −2.28 |
| LAUNCH SIGNAL exits only | +12.6 | +11.8 | +15.7 | +20.3 |
| LAUNCH TIMER | −7.5 | −10.6 | −6.4 | −15.0 |
| DIP | +0.5 | +6.4 | −11.8 | −4.7 |
| DIP SIGNAL | +4.2 | +11.1 | −7.1 | +1.0 |
| MOMO | −3.0 | −3.1 | −5.2 | −18.5 |
| DRIFT | −13.5 | +7.9 | +4.4 | −8.7 |
| hold < 50 slots | −6.2 | −29.3 | −22.2 | −31.4 |
| hold 50–250 | −3.3 | +4.6 | +0.9 | +4.4 |
| hold 250–1,300 | +18.4 | +56.9 | +34.9 | +32.5 |
| hold ≥ 1,300 | −19.8 | −19.9 | −17.0 | −32.0 |

- **Fixed exits on its picks at 70 ms** (SOL/day): 1 slot −63.9 / −128.8 / −105.6 / −170.2; 6 slots −47.4 / −101.0 / −83.3 / −126.5; 30 slots −66.8 / −88.6 / −80.1 / −108.1; 150 slots −106.2 / −171.5 / −103.5 / −249.6 **[E, J]**.
- **Only** "LAUNCH with its signal exit" stays positive at 70 ms (+12..+20/day). It needs its exit, which we cannot reproduce (5.5). **The LAUNCH lane alone, without its top 5, is not proven** **[E, R]**.

### 8.2 X calibration rows (its real trips through X's sim; SOL per recording) [E, XJ c1_calib]
| | 10-28 | 10-30 | 10-31 | 11-02 |
|---|---|---|---|---|
| real | +18.84 | +79.85 | +63.66 | +52.76 |
| at its exact times | +18.91 | +100.56 (miss, see above) | +63.70 | +52.78 |
| its speed (+45 ms, 0.7 SOL, 1.46 mSOL) | **+11.12** | **+79.90** | **+46.49** | **+28.76** |
| our speed (+70 ms, 0.55 SOL, 4.5 mSOL) | **−9.13** | **+18.29** | **+2.58** | **−12.50** |
| our speed, −20 % followers | −32.1 | −20.2 | −27.8 | −48.4 |

- Note: X's "+45 ms" row (+11.1 / +79.9 / +46.5 / +28.8) differs from R's "0 ms" row (+0.7 / +51.8 / +27.0 / +25.2). X uses its size and cost (0.7 SOL, 1.46 mSOL); R uses ours (0.55 SOL, 4.5 mSOL). Both are right for their setup.

### 8.3 Rebuilt bot (learned buy score + learned sell score + all hard rules, free-running on the tape) [E, X / XJ replica_sim]
TBQ = buy-score quantile threshold; TS = sell-probability threshold; CAP = hold cap (s).

| recording | role | TBQ / TS / CAP | bot buys / his buys | buy precision | recall | sell within ±1 slot | P&L at his speed | at our speed | ours −20 % fol. | his real |
|---|---|---|---|---|---|---|---|---|---|---|
| 10-28 | train | .997 / .3 / 300 | 9,711 / 4,248 | 7.6 % | 17.4 % | 26 % | −90.5 | −128.7 | −167.2 | +19.6 |
| 10-30 | train | .997 / .3 / 300 | 9,150 / 8,870 | 18.6 % | 19.2 % | 30 % | −61.7 | −104.7 | −139.9 | +87.3 |
| 10-31 | choose | .997 / .3 / 600 | 9,800 / 7,224 | 12.4 % | 16.8 % | 26 % | −90.4 | −129.7 | −169.0 | +68.6 |
| 10-31 | variants | .99 / .3 | 24,644 | 9.1 % | 31.2 % | 25 % | −251.4 | −339.1 | −437.6 | |
| 10-31 | | .999 / .2 | 4,005 | 12.4 % | 6.9 % | 22 % | −35.4 | −49.4 | −63.2 | |
| 10-31 | | .999 / .5 | 1,506 | 16.7 % | 3.5 % | 18 % | −57.9 | −54.0 | −59.4 | |
| 10-31 | pickier | .9995 / .3 | 1,253 | 15.2 % | 2.6 % | 25 % | −23.3 | −24.4 | −29.0 | |
| **11-02** | **TEST (16.5 h)** | .997 / .3 / 600 | 8,367 / 7,898 | 13.6 % | 14.5 % | 27 % | **−59.8** (−87/day) | **−97.6** | −134.8 | +61.6 |
| 11-02 | pickier | .9995 / .3 | 1,218 | 20.3 % | 3.1 % | 29 % | +4.1 (w/o top 5 −5.6) | −3.6 | −9.1 | |

- With the same hard rules but its choices guessed from landed trades, the bot **loses 60–90 SOL a day even at its own speed**, while 9pQQ makes 60–90. **[I]** Its edge is in the choices (which trigger, which moment to sell), and those are not visible in landed on-chain data.

### 8.4 Generic reactive dip, split by 9pQQ's state on the token (does "9pQQ attention" rescue a generic dip buy?) [E, J k9filter]
Setup: universe = outside sell ≥ 1 SOL, drop ≥ 5 %, non-mayhem, age ≥ 5 slots, curve < 85 SOL. 0.55 SOL, 4.5 mSOL, 9pQQ kept. mSOL/trip at 70 ms:

| hold | 9pQQ state | 10-28 | 10-30 | 10-31 | 11-02 |
|---|---|---|---|---|---|
| 1 slot | never | −17.4 (n 65,445) | −16.0 | −15.9 | −16.5 |
| 1 slot | traded before | −18.2 (n 12,596) | −16.3 | −16.3 | −16.6 |
| 1 slot | holding now | −19.9 (n 4,670) | −17.1 | −17.0 | −17.6 |
| 6 slots | never | −19.1 | −17.5 | −16.2 | −18.3 |
| 6 slots | traded before | −20.6 | −18.8 | −19.0 | −20.0 |
| 6 slots | holding now | −17.9 | −17.4 | −17.1 | −17.9 |

- All lose −16..−21 mSOL/trip, whatever 9pQQ's state. The 50 and 90 ms rows and the −20 % follower rows are the same or worse.
- **"9pQQ traded this token" does not help a generic reactive dip at 70 ms** **[E, R]**. It only helps our own pre-sent fills (7.1).

---

## 9. What we can use (for our engine)

Our engine (BRIEF):
- Trigger: a T2 "whale" buy ≥ 6 % of supply.
- Pre-signed buys at a 0.88× price limit (12 % dip), filled when a dump drops through the limit.
- Exit ~200 ms after the fill; TP/SL 20 %.
- Size 0.55–0.65 SOL; landing ~50–90 ms; ~4.5 mSOL per round trip.
- Wallet EgxfYgEb (AMS).

| # | idea | status | numbers | what it needs |
|---|---|---|---|---|
| A | **Copy 9pQQ** (its picks, its exit, or a rebuilt bot) | **NO, failed** | 70 ms: −10.8 / +12.4 / −3.3 / −26.5 SOL/day; −20 % followers −33 / −26 / −33 / −80. Rebuilt bot −98 on test. Fixed exits −9..−25 mSOL/trip | nothing; closed |
| B | **Its cheap send recipe**: single tx, no copies, CU price 1,500,001 on a tight CU limit (130k / 80k), Astralane 1 mSOL buy / 0.1 mSOL sell + Jito 17.5k | **lead, untested on us** | 1.46 vs our ~4.5 mSOL/trip = +3 mSOL/trip ≈ **+0.9..+1.5 SOL/day** for our 300–500 trips/day **[E, arith proven, landing not]**. Replay at its cost shows how much cost matters (70 ms: +1.7 / +38.6 / +18.0 / +7.9 vs −10.8 / +12.4 / −3.3 / −26.5) **[E]** | **Send-path change: owner's explicit OK.** Live A/B (single copy vs our copies). Risk: our pre-send fill rate may need several copies/tries (we had ~197 failed txs per trip on 11-02); Astralane is not faster for us (r38) |
| C | **"9pQQ round-tripped this token before"** as a pre-send priority / annotation signal | **lead, log-only first** | our trips +19.4 / +29.5 / +17.1 / +15.5 mSOL (n 80 / 94 / 75 / 43) vs never-touched +8.8 / +8.9 / +12.2 / −1.9 (n 500 / 360 / 377 / 247). It re-enters our hold 5–29 % vs 2–6 %. Quieter tokens: +15.1 / +31.0 / +12.2 / **−0.3** vs +8.6 / +8.7 / +11.7 / −3.2 (the edge shrinks on 11-02) **[M]** | log-only annotation (state of 9pQQ per mint at arm time), then a forward test. Not for a generic reactive dip (8.4). Small n per day |
| D | Its **LAUNCH lane** (age 10–50 slots) at our speed with its exit | **not proven** | +5.1 / +1.1 / +9.2 / +5.3 SOL/day; w/o top 5 −0.2 / −3.5 / +4.5 / −2.3 **[E]** | its exit (not reproducible); drop |
| E | **Never mayhem; no entries in the first ~8–10 slots; ignore < 0.05 SOL trades as buy triggers** | **sanity rules; mostly already ours** | 0 of 28,240 mayhem buys; age < 10 take rate 0.026 %; < 0.05 SOL trades 0.065 % (its net on those −2.2 mSOL) **[M]**. We already have create_slot / young_age / min_age_slots 2 (BRIEF) | check our floor vs its 8-slot floor in a log-only count; no live change implied |
| F | **Triggers routed through program `41Pr4XqE`** (± 6gY1osmP / L2TExMFK) | **lead, log-only** | its buy rate 7.5–12.3× base on all 4 recordings, but only 7–11 % of its buys **[M]**. 2-tip triggers 1.7–2.6× | log-only check: do 41Pr4-routed dumps / buys draw more followers into **our** holds? |
| G | 9pQQ **buying after us** = paying follower | **observation (can't control)** | +15.5..+59.4 mSOL/trip (tape) or +22..+35 (botpnl) when it comes; −26.7..−31 when it is ahead of us (11-02) **[M]** | observatory watch list (added 11-03) to track it live; feeds the regime/follower gauge |
| H | Its **exit insight**: price keeps falling after its sell (−0.6..−2 % in 25 slots, −2..−4 % in 150) | **context** | **[M]** | our 200 ms exit is far shorter than its holds; no direct use |
| I | **Time cap on dead tokens** | **context** | its forced exits −42.9 mSOL/trip, LAUNCH −109 **[M]** | ours already exits in ~200 ms; no use |

### 9.1 Open questions
1. **What drives its choice of trigger and sell moment?** Landed trades explain 8–17 % precision (rules) and 16 % (GBDT ceiling) for buys, 17–31 % for sells.
2. **Why the ≥ 8–10 slot age floor?** **[I]** It avoids the launch/sniper block.
3. **Does its single-copy 1.46 mSOL recipe keep our pre-send fill rate?** Not testable offline.
4. **How much of its trading is on old revived tokens** (T2 type) that our recorders never see?
5. ~~What is the exact slippage limit?~~ **Answered [M, L]:** 15 % on buys (min_out = expected ÷ 1.15 at the state it priced on), ~50 % on sells.
6. **Does the copy-bot 8d1YSS1u follow it on every token, and are there bigger copiers?**

### 9.2 Next tests (proposed; none started)
| test | purpose | cost / approval |
|---|---|---|
| **Pending/failed-tx events** | Add failed (and, if the feed allows, pending) pump.fun txs as decision events and re-run X's buy/sell ceilings. Hypothesis (X): it reacts to information early in the block stream that is not in landed trades. The recordings hold failed txs (T3: 13,102 failed vs 2,569 landed; error field in p2 rows) | offline, read-only |
| **Recorder blind spot** | Count its trades on mints not in the recording (tape_ok = False share) and fetch a sample via public RPC, as C1 did for T2 | offline + public RPC |
| **Log-only "9pQQ state" annotation** (lead C) | Forward evidence on new runs | engine log-only change: owner OK |
| **41Pr4XqE follower check** (lead F) | Do these triggers bring more paying followers to our fills? | offline |
| **Single-copy send A/B** (lead B) | Real cost vs fill-rate trade-off | **send-path change: owner's explicit OK, live** |
| **Observatory** | Live record of its co-trading with us (watch list since 11-03) | already deployed (next run start) |

### 9.3 Inference about its feed (labelled)
- **[M]** It lands in the trigger's own slot 50–84 % of the time, tens of positions later. It reacts to trades it cannot have seen confirmed.
- **[M]** It fails on slippage exactly when the in-slot price moved +17..+24 % before its tx.
- **[I]** It reads shreds or another pre-confirmation stream and sends within the slot. It does **not** need to be faster than us on dumps (it is not, in aggregate). Its edge is choice, not speed.

### 9.4 Recorder blind spot (labelled)
- **[M]** The local recorders only track coins launched during their own run.
- **[M]** T2's 11-03 revival (28 buys, +1.45 SOL) has 0 recorded trades.
- **[I]** All recording-based totals here (R, X) **undercount** its trading on old revived tokens. The P&L in section 2 is a lower bound for the wallet as a whole on those days. The botpnl (MEM) P&L is also recording-based; its size is unknown.

---

## 10. Data and files index

**Study folders (scripts + JSON results; all read-only analyses)**
- `/home/it/sniper/ops/strategies/rivals/9pQQ/`: first dissection.
  - `REPORT.md`; `9pqq.json` (summary, built by `z_summary.py`); `run_all.sh` (rebuild order).
  - Steps: `t0_tape.py` (compact tape of every curve trade, 4 recordings) → `a1_own.py` (its signed txs, from botpnl9 pass 1) → `a2_trips.py` (round trips + context; Net = buy + sell + rent if the buy created the ATA).
  - Lanes and re-entry: `a3_clusters.py` → `clusters.json`; `a4_reentry_grad.py` → `reentry_grad.json`.
  - Tx anatomy: `b1_buyins.py` → `buyins.json`.
  - Exits: `e1_exit.py`, `e2_who.py`, `e3_sellers.py` (exit state rows and hazards; output only in R).
  - Selection: `s1_universe.py`, `s2_takerate.py` → `takerate.json`; `s3_imitate.py` → `imitate.json`.
  - Interactions: `i1_interact.py` → `interact.json`; `i2_ours_k.py` → `ours_k.json`.
  - Replays: `r1_replica.py` → `replica.json`; `r2_exitrule.py` → `exitrule_70.json`; `r3_exitml.py` → `exitml_70.json`; `r4_exitshift.py` → `exitshift.json`; `r5_k9filter.py` → `k9filter.json`.
  - Libraries: `tlib9.py` (tape loader, constants: RUNS, DAY, W, OURS), `rlib9.py` (paper-replay core), `gbdt_np.py` (numpy GBDT).
- `/home/it/sniper/ops/strategies/rivals/9pQQ/exact/`: exact-rules study.
  - `REPORT.md`; `exact.json` (built by `z_exact.py`); `run_all.sh`.
  - Decision moments and tx metadata: `dm_build.py`, `dm_route.py`, `p0_peek.py`, `p1_txmeta.py`, `p2_join.py`, `p3_route.py` → `p3_route.json`.
  - Hard rules: `h0_hard.py` → `h0_hard.json`; `b0_bounds.py`.
  - Hypotheses: `h1_leaders.py`, `h1_test.py` → `h1_test.json`; `h2_fp.py` → `h2_fp.json`; `t1_timer.py` → `t1_timer.json`.
  - Exit rules: `e1_rules.py` → `e1_rules.json`; `ev_dec.py`.
  - Trees: `b1_tree.py` / `s1_tree.py` → `b1_tree.txt`, `s1_tree.txt`, `b1_tree_frozen.json`, `s1_tree_frozen.json`; `cart.py`, `s2_split.py`.
  - GBDT ceilings: `g1_bound.py` → `g1_b.json`, `g1_s.json`, `g1_b_rt_nog*.json`, `g1_s_rt_nog*.json`, `*.log`; `fgb.py`.
  - Calibration and sim: `c1_calib.py` → `c1_calib_<day>.json`; `sim.py` (rebuilt bot); `xlib.py`.
- `/home/it/sniper/ops/strategies/rivals/9pQQ/cases/`: `PHASE1.md`, `PHASE2.md` (T1, T2).
- `/home/it/sniper/ops/strategies/rivals/9pQQ/cases3/`: `PHASE1.md`, `PHASE2.md` (T3).
- This file: `/home/it/sniper/ops/strategies/rivals/9pQQ/9PQQ_REFERENCE.md`.

**Data** (under `/home/it/sniper-data/rivals/9pQQ/`)
- Text outputs kept:
  - `a3.txt`: lane tables plus 4-recording totals (28,050 trips, +237.18).
  - `s2.txt`: take-rate tables plus token-level coverage.
  - `r1.txt`: replica rows.
  - `t0.log`: tape build.
- Large numeric/binary files, **being deleted**: `tape/`, `tape_*.npz`, `uni_*.npz`, `exits_*.npy`, `own_*.pkl`, `trips_*.pkl`, `bsz_*.npz`, `exact/dm_*.npz`, `h1_*.npz`, `rt_*.npz`, `tm_*.npz`, `g1_*.pkl`. They can be rebuilt with the two `run_all.sh` scripts from the raw recordings, if those still exist.
- `exact/sim/sim_<day>_<TBQ>_<TS>.json`: per-config rebuilt-bot results (9 files). `exact/txmeta/<run>/`: per-tx metadata.
- `cases/`:
  - CSV and text: `t1_actions.csv`, `t2_actions.csv` (per action: time, slot, idx, side, SOL, MC, curve, age, neighbours, hold, return, P&L, sig); `t1_tl.txt` (full T1 tape); `t2_windows_tl.txt`, `t2_tape_partial_tl.txt`; `t1_sell_hazard.txt`; `t1_trailing_test.txt`; `phase2_checks_t1.txt`, `phase2_checks_t2.txt`; `t1_ata_sigs.json`, `t2_ata_sigs.json`.
  - Gz files (being deleted): `t1_all_trades.json.gz`, `t1_local_raw.jsonl.gz`, `t2_rpc_rows*.jsonl.gz`.
  - `scripts/`: an, ata, blkidx, conv, csv, ctx, fetchtx, haz, insl, mdtab, p2, p2b, parse, pfun, rpc, sellwho, skip, summ, tl, trail, trig (.py).
- `cases3/`: `trades.json` (decoded TradeEvents on T3), `trips.json`, `ctx.txt` (every 9pQQ trade with neighbours), `t3_parsed.jsonl.gz` (being deleted); `code/` (ctx, hazard, hazard2, hazard3, parse, phase2, trips, wallets .py).
- botpnl measurements (MEM): data `/home/it/sniper-data/botpnl9`; scripts were in the scratchpad (`p1_9pqq`, `an_9pqq`), likely gone.

**Raw inputs:** recordings `/data/tapes/collect/run_20261028_1405`, `run_20261030_1355`, `run_20261031_1350`, `run_20261102_1250` (txs/*.jsonl.gz).

**Related memory notes:**
- `wallet-9pqq.md` (this wallet);
- `wallet-census.md`, `strategy-families.md`, `astralane-vip1.md`;
- `rival-8yymhu.md`, `haqq6-dissect.md`, `e2x1-dissect.md`, `wallet-8pgc.md`;
- `profit-source-bot-cohort.md`, `presend-fade.md`.

**Our engine context:** `/home/it/sniper/ops/strategies/presend/filters3/BRIEF.md`.

---

## 11. Evening studies 11-03: CASEBOOK and LANES

Both studies apply the owner's 11-03 rules:
- Main numbers are at 9pQQ's own fills and timing. +70 ms rows are information only.
- A failed reconstruction is reported as "not cracked", never as "doesn't work for us".

Overall verdict: the structure is now proven, but **entry choice and exit are still not cracked**.

### 11.1 Version history and off periods [M, CB, L]
| period (PKT) | version | notes |
|---|---|---|
| 10-28 → 10-29 ~18:00 | V1 | — |
| 10-29 ~18:00 → 10-31 00:10 | **V2** | 15–35 % of trips end on the time cap; P&L ≈ 0. 10-29 = +3.8 SOL/day; 27 % of NEW trips capped |
| 10-31 00:10–00:30 | redeploy | 15-minute hole in its trading |
| 10-31 00:30 → | **V3** | ~5 % cap exits; +2..+7 SOL per half hour |
| 10-31 06:30–10:00 (to ~10:50 in CB) | migration | 0.48 and 0.70 SOL processes ran side by side on almost disjoint tokens. 204/209 multi-trip tokens used one size; 5 were handed 0.48 → 0.70, never back. Shared recent blockhashes within 1–2 slots (likely one host). Same pricing (117/117), speed and mSOL/trip (13.7 vs 13.6). A version migration, not two strategies |

- **Multi-hour off periods:** ~6.5 h on 10-28, ~7 h on 10-29, ~1.5 h on 10-31.
- Earlier studies counted those hours as "skipped" decision moments, which deflated take rates and precision.

### 11.2 Two code paths, proven by slippage pricing [M, L; classifier frozen in `lanes/FROZEN.json`]
Instruction data was fetched with the public RPC: 1,467 txs, of which 953 were classifiable buys. That is a 2.5 % random sample plus every trade in one dense 10-minute window.

**BUY:** `min_tokens_out = E_buy(s) ÷ 1.15` (15 % slippage) for the curve state `s` it priced on.
- E_buy = 691,358,023 lamports net into vtok = curve balance + 73e12, vsol = 30e9 × 1073e12 / vtok.
- For the 0.48 config, E_buy = 474,074,074.
- When `s` is a landed state, the match is exact to ~1e-10.

**SELL:** `min_sol_out` ≈ 0.48 of expected proceeds (~50 %, effectively a market sell). It matches no landed state at any fixed constant.

**The two modules:**
- **NEW** = first entry on a token (or more than 20,000 slots since its last sell). Priced on an exact landed state: 288/301.
  - About half the time that state is the trigger's own post-state.
  - Otherwise it is 1–10 trades back, because other trades landed before it.
- **TRK** = re-entry on a token it is tracking. Priced on its own internal state, which never landed: 649/652.
  - The gap to the real price has a median of ~1 % and reaches ±12 %.

**Agreement with behaviour:**

| day | agreement |
|---|---|
| 10-28 | 98.2 % (215/219) |
| 10-30 | 99.4 % (313/315) |
| 10-31 | 97.6 % (207/212) |
| **11-02 (held out)** | **97.6 % (202/207)** |

- 10-29 is not in the RPC sample. Overall 937/953.
- The exceptions fit the rule: NEW-priced re-entries came after 31,834 and 142,707 idle slots (tracking expired). 13 first entries were TRK-priced because the token was already tracked.

**What does NOT separate it [M, L]:**
- **Fee and tip recipe:** identical on every landed buy and sell, all 5 days, both modules, before and after the redeploy.
  - Buys: CU price 1,500,001, limit 130,000, Astralane 1,000,000 + Jito 17,500.
  - Sells: CU limit 80,000 (200,000 on rare SellV2), Astralane 100,000 + Jito 17,500.
  - Jito tip accounts are spread uniformly over all 8.
  - No module pays more for speed.
  - The owner's screenshots (11-03 ~21:00 PKT) confirm it: YQyMvY68… buy, 5iMYacVM… / 35MnvCXY… sells.
- **Speed:** same-slot buy share 66–69 % in both modules.
- **Exit:** one exit module is shared. A sell model trained on one module scores AUC 0.775 vs 0.807 and 0.749 vs 0.761 on the other.

### 11.3 P&L by module and lane (its real trips; SOL/day scaled to 24 h; rent excluded) [M, L lane_table]
| module | 10-28 | 10-29 | 10-30 | 10-31 | 11-02 | share of trips | mSOL/trip 11-02 |
|---|---|---|---|---|---|---|---|
| NEW | +8.6 | −15.0 | +26.6 | +32.7 | +25.3 | ~33 % | +8.2 |
| · NEW age ≤ 50 slots | +12.1 | +2.3 | +16.1 | +23.2 | +17.4 | | +9.3 |
| · NEW age > 50 slots | −3.5 | −17.3 | +10.5 | +9.5 | +7.8 | | +6.5 |
| TRK | +10.6 | +18.9 | +59.5 | +35.0 | +45.5 | ~67 % | +6.4 |
| · TRK gap < 25 slots since own sell | +1.9 | +10.0 | +25.9 | +13.2 | +28.0 | | +13.9 |
| · TRK gap 25–150 | +3.4 | +7.2 | +10.6 | +15.9 | +8.7 | | +3.2 |
| · TRK gap ≥ 150 | +5.3 | +1.7 | +23.0 | +5.9 | +8.8 | | +3.7 |
| ALL | +19.2 | +3.8 | +86.1 | +67.7 | +70.8 | | +6.9 |

- The age and gap cuts are descriptive only. Age is one continuous curve peaking at 10–11 slots, with no second mode.

**CASEBOOK lanes on 11-02** (10,362 trips, +71.76 SOL) **[M, CB]**:

| lane | entry pattern | trips | net SOL | mSOL/trip |
|---|---|---|---|---|
| LAUNCH | first entry ≤ 60 slots, behind big launch-rush trades | 2,013 | +22.1 (w/o top 5 +13.7) | +11.0 |
| RE-DIP | re-entry after a −3 % drop, behind a bounce buy | 2,645 | +20.4 | +7.7 |
| RE-MOMO | re-entry behind a +3 % buying ramp | 2,294 | +13.1 | +5.7 |
| RE-FLAT | re-entry, no clear move | 1,957 | +12.1 | |
| FIRST at age > 60 | — | 880 | +5.1 | |
| WAKE | first trade after a long silence on a dead token | 251 | −2.2 | 45 % capped |

- LAUNCH holds about 30 slots. It has rugs of −50..−80 % and rides of +190..+270 %.

**Replay calibration [M, L]:**
- Its own trips replayed at its own times match its real net (correlation ≥ 0.998).
- 11-02: NEW +23.2, TRK +36.4 SOL/day.
- At +70 ms (information only): NEW +7.1, TRK 0.0.
- With 20 % fewer followers: NEW −6.8, TRK −1.9.

### 11.4 Hard rules re-confirmed on all 5 days; casebook ledger [M, CB, L]
**Hard rules:**
- Never mayhem.
- First entry at age ≥ 8 slots.
- Curve between 30 and ~112 SOL.
- Re-entry ≥ own sell + 2 slots; minimum hold 2 slots.
- 97 % of buys follow an outside trade in the same or previous slot.
- One position per token.

**CASEBOOK ledger** (64 tokens: 16 read trade by trade, 48 with automatic checks plus every trip read) — 51 hypotheses:

| status | count | what |
|---|---|---|
| hard (held on every trade) | 5 | the rules above |
| strong (soft drivers) | 29 | raise its buy/sell rate but don't decide it |
| killed | 9 | quits when volume dies; slot-leader gating; global position cap; below-recent-high entries; sells when its trigger wallets sell; sells near the peak; sells into buy bursts; wake-up as a buy driver; sells when followers leave |
| weak | 4 | other wallets' failed txs; repeat traders; coordinated groups; dropped sends explaining randomness |
| open | 4 | |

**When it stops on a token:** at the top of the curve, not out of boredom.
- P(another trip) is 0.94–0.99 at exit MC 60–200, falling to 0.40–0.55 above MC 300 (vsol ~98).
- No tilt: 0.93 after a win vs 0.89–0.90 after a loss.
- Tokens are traded independently.

**Entry drivers on 11-02** (base buy rate 1.91 %) **[M, CB]**:

| condition | rate vs base | share of its buys |
|---|---|---|
| trigger routed via 41Pr4XqE | 6.4× | 7 % |
| high-volume bot wallet (≥1k trades/day), trade ≥0.3 SOL, after a ≥5 % move | 2.95× | 18 % |
| buying ramp | 2.6× | 12 % |
| high-volume bot wallet | 2.0× | 42 % |
| dip with a bounce starting | 1.9× | 25 % |
| trade ≥ 0.3 SOL | 1.56× | 63 % |
| retail terminal trade (FLASH, Axiom, GMGN, Jupiter) | 0.51× | — |
| quiet flow | 0.62× | — |
| curve vsol ≥ 80 | 0.36× | — |

- A trigger wallet that was profitable the day before gives 2.2× (10-30).

**Exit drivers [M, CB, L]:**
- An outside sell after a 15+ slot pause in outside buying: 10–15 % sell chance per event, 3.5–5.8× normal.
- Up 20 % or more: sell chance 0.6× (it lets winners run).
- Buy bursts do NOT trigger sells (0.73–0.83× at scale).
- L's exit model top features: 1-slot price change, outside sells in the slot, hold time, slots since the last outside buy.

### 11.5 Reconstruction attempts (all failed: "not cracked") [E, CB, L]
**Entries:**
- CB best combined score: 6.1 % precision at 29.9 % recall on 11-02 (base 0.47 %). The same ceiling as R and X.
- **NEW imitation:** 10.9 % precision at 10 % recall (base 0.8 %). Its exact trigger trades (53 % buys, 47 % sells, median 0.73 SOL) look like the trades it skipped.

  | score band | picks/day | precision | his speed SOL/day | 0 ms | −20 % followers |
  |---|---|---|---|---|---|
  | top 0.1 % | 1,881 | 10 % | −26.9 (w/o top 5 −53) | −10.2 | −39.6 |
  | top 0.3 % | 5,645 | 11 % | −86.5 | −32.7 | −126.9 |

- **TRK imitation:** 44.7 % precision at 5 % recall, 37.7 % at 10 %, 31.3 % at 25 % (base 5.5 %).
  - Top features: same-slot landed buy SOL, 1-slot price change, slots since own sell, trigger size, price vs its last exit.
  - There is no discrete re-entry limit price: decision price / last exit spreads 0.73–1.14.
  - Top 1 %: 5,946 picks/day, 38 % precision. His speed −84.0 SOL/day; 0 ms +5.9 (w/o top 5 −19.2); −20 % followers −115.6. Not robust.

**Exit, on its own picks with its own fills** (fixed-size subsample, so the totals are noisy):

| exit used | 10-31 SOL/day | 11-02 SOL/day |
|---|---|---|
| **its real exit** | **+69** | **+122** |
| learned exit (best threshold) | −55 | −70 |
| fixed hold 6 slots | −59 | −87 |
| fixed hold 80 slots | −69 | −70 |
| fixed hold 250 slots | −114 | −258 |

- On train (10-31), every CB exit variant on its entries made −21..−163, against +39 for its real exits.
- **The edge is in the exit.**

**Replays:**
- CB replay of his entries + his exits on 11-02: +50.1, vs real +71.8. The gap comes from sells with no outside trade just before them in the data, which the replay holds to the cap.
- At his speed (modelled) +33.3; −20 % followers +11.8; +70 ms (information only) +11.5.
- His entries + our best simple exit: −88.1. Our rule bot (2,454 trips): −28.9 SOL, −11.8 mSOL/trip. Only 2.6 % of its buys land on his trigger trades.

**Pre-landing order flow lead (main session hypothesis), tested and REJECTED [M, L]:**
- For 662 TRK buys, the internal-state gap has no correlation with later landed outside flow: −0.06 same slot, −0.02 next slot, +0.01 at 3 slots.
- Around failed outside buys the internal state lags: median −3.6 %.
- A search over stale states plus subsets of nearby trades (including up to 6 trades landing after its tx) found 0 matches.
- So **its decision is not earlier than the landed trigger**, and its real fills need no re-pricing.
- The "its own picks lose at 46 ms" rows used the learned exit and a fill assumption, not its exit.

### 11.6 What we can use (adds to section 9)
- **Log-only "9pQQ is tracking this token"** (it round-tripped the token within ~20,000 slots), as an annotation for our pre-send arms.
- **Log-only "don't" filters:** no mayhem; first buy ≥ 8 slots; curve vsol below ~80–95; skip quiet flow.
- **Log-only trigger-quality score:** a bot-wallet or 41Pr4 trade ≥ 0.3 SOL after a ≥ 5 % move.
- **Exit signal to log only:** an outside sell after a 15+ slot buy pause, while letting +20 % positions run. As a full exit it lost on his entries.
- **The LAUNCH lane is its best per trip.** Copying it at his speed is untested, not ruled out.

### 11.7 Still open (updates 9.1)
1. **Its exit logic.** It is worth +60..+120 SOL/day on its own picks, and nothing reproduces it. This is the main item.
2. How the TRK internal state is built. It is not a past landed state, a missing or extra trade, a constant per-token offset, or failed txs.
3. Which 1–3 % of qualifying triggers it takes; whether TRK's 31–45 % precision gap is randomness or hidden inputs. A randomness test has not been run.
4. Whether it runs several same-size processes on disjoint tokens outside the 10-31 migration (blockhash age; needs block headers via RPC).
5. Not tried: a long wallet-history model.

### 11.8 Files (11-03 evening)
**CASEBOOK:** `/home/it/sniper/ops/strategies/rivals/9pQQ/casebook/`
- `FINAL.txt`, `ledger.txt`, `ledger.json`, `final_1102.txt`.
- `cases/`: 10 case files.
- `code/`: c0–c19 and `ledger.py`.

**LANES:** `/home/it/sniper/ops/strategies/rivals/9pQQ/lanes/`
- `lanes.json`.
- `FROZEN.json`: classifier and scorer hashes. `code/l6_decjoin.py` sha256 1bec94c6…
- `calib.json`, `followers.json`, `replay_exit_v3.json`, `replay_entry_x0.0.json`.
- `entry_gbdt*.json`, `exit_gbdt.json`: result summaries only.
- `code/`: l0–l16.

**Data kept** (`/home/it/sniper-data/rivals/9pQQ/`):
- `lanes/`: `rpc1.jsonl`, `rpc_mixed.jsonl` (public-RPC instruction data, slow to refetch), `dec1.jsonl`, `lane_table.*`, logs.
- `casebook/`: logs, `final_1102.txt`, `pick_b*.tsv`, `tokens_*.tsv`, `points.json`.

**Deleted 11-03 ~21:30 PKT (owner request):** 9.2 GB of rebuildable tapes, scale tables, per-run trips/own/picks/score/momentum arrays, and the ML model pickles (`entry_gbdt_*.pkl`, `replay_partial.pkl`, `decjoin*.pkl`). They can be rebuilt with the CB/L `code/` scripts from the raw recordings.

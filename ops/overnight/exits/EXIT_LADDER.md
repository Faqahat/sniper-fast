# How 9Sh2fd and DGmspi exit (AKbot exit ladder), 2026-10-23

READ-ONLY study. No transactions sent, nothing changed on the server.
Every claim is labelled **MEASURED** (counted from chain data) or **INFERRED** (my reading of it).

Data:
- **Their trades:** full ledgers 10-17 → 10-22 20:15 UTC, plus their newer txs to 10-23 ~01:00 UTC (fetched read-only from Constant-K).
- **Their raw txs:** every TradeEvent decoded, so prices are exact curve states, not estimates.
- **Market paths (everyone's trades on the token):**
  - 95 tokens from our collector (R1/R2);
  - 79 tokens fetched read-only from CK, only the successful txs from their buy to their last sell.
- **Scope:** SOL-quoted pump.fun tokens only (USDC/PUMP-quoted and LaunchLab are excluded).

## 1. Bottom line

**Every exit is an AKbot preset (MEASURED).** There is one preset per followed dev ("config"). We found ~20 configs, and all have the same shape:

1. **Lightning sell.** A fixed 10–90% of the position, 0–2 slots (≈0.2–0.4 s) or 5–8 slots (≈1–1.7 s) after the buy, at whatever price. 98% of tokens.
   - The median price is ×1.10 of entry, because they are the first buyer after the dev's bundle and the next snipers push the price up.
2. **Take-profit steps at new highs.** The first at ×1.2–1.45 of entry, then every +15–25%. Each sells a fixed 10–60% of what is left.
   - 65% of these land in the same slot as the buy that made the high.
3. **Down-sells.** 5–25% of what is left on each ~5–10% pullback (AKbot's "drawdown").
4. **The clear.**
   - Below entry, usually at ×0.86–0.89 (INFERRED: a stop near −10..−12%).
   - Or on the dev's dump: 71% land in the same slot as the dev's sell.
   - Or a 60 s timeout (DGmspi's biggest config, 5ZdusG).

**Where the profit comes from (MEASURED, 10-17..10-22, 9Sh2fd / DGmspi):**

| | 9Sh2fd | DGmspi |
|---|---|---|
| lightning sells | +13.8 | +8.8 |
| take-profit sells | +21.6 | +19.8 |
| down-sells | +8.2 | +4.6 |
| clears | −32.5 | −16.8 |
| **total** | **+11.05** | **+16.46** |

- **Price level:** 74–80% of the winners' profit was sold at ×1.3 or higher, but only 13–16% at ×2 or higher. The money is in ×1.15–2, sold fast.
- **Timing (replay):** dumping everything 1 slot after the buy loses 13.5 SOL more than dumping at 6 slots (174 tokens). The first ~1 s of follow-on buying is what they sell into.

**Best explicit rule (INFERRED).** This is the single rule that best reproduces their per-token PnL:
- lightning 35% at 6 slots;
- take-profit at +25% selling 25%, then every +15% selling 25% of the rest;
- after +20%, sell 10% on each 8% pullback;
- clear 60 s after the last take-profit;
- mirror the dev's sells.

**How well it matches their real results (replay on their own entries, 174 tokens with market paths):**

| rule | correlation per token | same sign | total, real vs replay |
|---|---|---|---|
| best single rule | 0.87 | 87% | +2.99 vs −5.86 SOL |
| fitted per config | 0.92 | 90% | +2.99 vs −4.99 SOL |

- **Complete paths only (95 collector tokens):** the per-config rules give corr 0.92, the same sign 97% of the time, and a total of −4.22 replay vs −2.43 real.
- **The gap:** the real ladders let more of the big winners run. On the 113 tokens whose config has its own fit, replay is within 1.7 SOL of real.
- **No generic rule beats them (out of sample):** a rule tuned on one wallet loses about 4 SOL vs real on the other wallet.

**For us (INFERRED):**
- A fast, 1-slot, all-in dump would have lost money on their exact entries.
- Their edge is selling *into* the next ~1–2 s of follow-on buying (lightning plus same-slot take-profit), and reacting to dumps in the same slot.
- That needs reaction inside the slot, not our measured ~74 ms landing. Untested for us.

## 2. What they hold and what they made (MEASURED)

| | 9Sh2fd | DGmspi |
|---|---|---|
| SOL-quoted pump round trips, 10-17..10-22 | 322 | 215 |
| PnL after every cost (curve, 1.25% pump fee, priority, tips, AKbot 0.99% sell fee, AKbot 1% buy fee billed later) | **+11.05 SOL** | **+16.46 SOL** |
| after the ledger (10-22 20:15 → 10-23 01:00) | 28 tokens, −0.90 | 16 tokens, −4.64 |
| buys per token | always 1 | always 1 |
| buy size (SOL incl. pump fee) | 1.8 (168), 3.0 (81), 1.2 (27), 2.0, 5.0, 2.5 | 1.8 (80), 3.0 (54), 1.2 (41), 4.0, 2.0, 5.0 |
| sells per token | 4.2 | 4.6 |
| tokens sold in exactly 2 pieces | 159 → −23.07 SOL | 93 → −16.20 SOL |
| tokens sold in 6+ pieces | 86 → +23.12 SOL | 71 → +27.75 SOL |
| buys ≥ 2.4 SOL | 106 → +13.28 SOL | 86 → +14.10 SOL |
| hold (first buy → last sell), median / 90th pct | 30 slots ≈ 7 s / 218 s | 62 slots ≈ 14 s / 105 s |

- **Slot time:** 1 slot = 0.212 s. Measured as 283 slots = 60 s on the DGmspi timeouts below.
- **PnL check:** ground truth was +14–15 / +17–20 for the whole wallets, which also includes USDC-quoted trades, failed-tx fees (2.9 / 1.9 SOL) and so on.
- **Sell transactions:**
  - fee 0.000223 SOL;
  - tip 0.0002 SOL, mostly to Astralane (AsTRAE…), then LandX6, DiTmWE and ste11e;
  - durable nonce;
  - routed through program AKbotMAGJ….
- **Failed sells are rare:** about 96 failed sell txs (all quotes) vs 1,345 landed SOL-quoted sells for 9Sh2fd.

## 3. The exit, piece by piece (MEASURED)

### 3.1 Lightning sell: a fixed % sold right after the buy, at any price
- **Timing:** 98% of tokens have a first sell within 8 slots (≤1.7 s) of the buy. Two clusters:
  - 0–2 slots (≈0–0.4 s): 180 of 322 (9Sh2fd) and 192 of 215 (DGmspi). This is AKbot's "lightning sell ~300 ms".
  - 3–8 slots (mostly 5–7, ≈1.1–1.5 s): 136 (9Sh2fd) and 21 (DGmspi).
- **Size:** fixed per copy-trade config: 10, 20, 35, 50, 60, 65, 75, 80 or 90% of the position.
  - Median 60% for 9Sh2fd and 25% for DGmspi.
- **Price at that sell:** median ×1.10 of the entry price. Only 0–3% of first sells were below entry.
  - They are the first outside buyer after the dev's bundle, and later snipers push the price up within 1–2 s.
- **Position in the slot:** in 58% of cases the lightning sell is the token's first trade in its slot.

### 3.2 Take-profit steps: sells at new highs
- **Levels:** first step at ×1.19–1.44 of entry (config median ×1.25–1.37). Later steps every +15–25%, so ×1.4–1.6, ×1.6–1.9, and so on.
- **Size:** each step sells a fixed % of what is left: 10, 15, 25, 33 or 60%, or a rising ladder (DGmspi/5ZdusG: 25 → 33 → 44 → 55 → 66%).
- **Speed:** 85 of 130 TP sells (65%) land in the **same slot** as the buy that set the new high; 31 (24%) land in the next slot.

### 3.3 Down-sells: small trims on pullbacks
- **Size:** 5–25% of what is left, fixed per config. Median 15%.
- **When:** on each ~5–10% drop from the last high or the last trigger. This matches AKbot's documented "drawdown" rule.
  - Example, DGmspi 3bdaWh: 25% at ×1.60, 1.51, 1.41, 1.31 and 1.20, each about 6–8% below the previous one.
- **Size of the effect:** 299 of 775 sells on path tokens, but only about 10% of all tokens bought.

### 3.4 The clear: the last sell
- **Below entry:** median ×0.87–0.89 of entry in most 9Sh2fd configs (q25–q75 ≈ ×0.86–0.89). INFERRED: a stop loss near −10..−12% of the entry price, with fills slipping past it.
- **Dev dump:** the clear often lands in the **same slot** as the dev's sell (see 3.5).
- **Timeout (one config):** DGmspi/5ZdusG clears at exactly 270–286 slots = **60 s** after the buy, or 60 s after its last take-profit step, when nothing else fired.
  - Examples: 4wpwMz 281, AMvtRs 283, BuBobJ 274; H58fCK 49+282; 5ZVdBe 48+278; EUvQ9b 214+278.
- **Dust:** remainders below a minimum sell amount are cleared, so some last sells are tiny.
- **Price after a losing clear (MEASURED, 51 path tokens):** 5 minutes later the median price was ×0.80 of the clear price (q75 ×0.92). The stop usually saved about 20% of what was left.
- **Price after a winning clear (68 tokens):** median ×0.84 five minutes later. In a quarter of cases it later went ≥ ×1.44 higher.

### 3.5 Reaction to the dev and to price (MEASURED, 174 path tokens, 775 sells)
- **When the dev sells:** a sell of theirs follows within ≤2 slots in 120 cases.
  - Lag: 0 slots in 85 (71%), 1 slot in 31, 2 slots in 4.
  - Same-slot gap: median 105 tx positions after the dev's tx.
  - In 54 cases no other trade of the token came in between.
- **Dev's full exit (95 collector tokens):** when the dev sells his last tokens, they sell within ≤2 slots 70% of the time and clear 52% of the time.
- **Dev's partial sell:** they sell within ≤2 slots 31–33% of the time and clear 8–10%.
- **Big non-dev sells (impact ≥8%, same 95 tokens):** they sell within ≤2 slots 64% of the time and clear 25%.
- **Reading (INFERRED):** most dev reactions are price-driven (the stop or the down-sell fires on the dump). Some configs also mirror the dev's sell %.
- **Reaction to the dev's bundle wallets (152 path tokens):** 9Sh2fd sold within ≤1 slot after 65% of create-slot (bundle) wallets' sells, vs 29% after other sellers. DGmspi: 17% vs 19%. INFERRED: some 9Sh2fd configs use AKbot "group follow sell".

**Label of every sell on path tokens (INFERRED from context):**

| | lightning | down-sell | take-profit | dev-triggered | stop | timeout | other |
|---|---|---|---|---|---|---|---|
| all sells | 159 | 299 | 130 | 120 | 48 | 7 | 12 |
| final clears | — | 74 | 10 | 50 | 32 | 7 | 1 |

### 3.6 Settings per copy-trade config (MEASURED from their own sells, all tokens)
A config is one wallet × one followed dev, the "smart wallet" AKbot watches. Settings were sometimes edited over time. For example, 49fAsU's lightning sell changed 10% → 35% → 20% → 80%.

| wallet | dev (followed) | tokens | PnL SOL | buy SOL | lightning sell (most common: % of position, slots after buy) | take-profit steps (price x entry, sell % of rest) | down-sell | clear below entry (median) | final sell (median slots) |
|---|---|---|---|---|---|---|---|---|---|
| 9Sh2fd | 49fAsU | 50 | -0.74 | 1.8/3.0 | 20% after 6 slots | #1: x1.27 sell 15% (n=15); #2: x1.43 sell 25% (n=3); #3: x1.72 sell 25% (n=1) | 10% | x0.88 (n=33) | 521.0 |
| 9Sh2fd | 8HeDT7 | 50 | +5.46 | 3.0/1.8 | 60% after 6 slots | #1: x1.37 sell 60% (n=13); #2: x1.58 sell 40% (n=6); #3: x1.73 sell 50% (n=4) | 15% | x0.88 (n=30) | 27.0 |
| 9Sh2fd | 8NJ7Uj | 30 | -0.26 | 1.8 | 65% after 1 slots | #1: x1.25 sell 60% (n=16); #2: x1.45 sell 60% (n=3); #3: x1.52 sell 60% (n=3) | 15% | x0.89 (n=17) | 24.0 |
| 9Sh2fd | 6aoG8G | 24 | -0.72 | 2.0/3.0 | 70% after 7 slots | #1: x1.18 sell 10% (n=9); #2: x1.26 sell 15% (n=3); #3: x1.36 sell 15% (n=1) | 15% | x0.91 (n=9) | 158.0 |
| 9Sh2fd | DfyGFR | 19 | -2.68 | 5.0/3.0 | 10% after 0 slots | #1: x1.27 sell 10% (n=12); #2: x1.39 sell 10% (n=8); #3: x1.60 sell 10% (n=3) | 5% | x0.89 (n=9) | 791 |
| 9Sh2fd | DWHEZ8 | 18 | +2.72 | 1.8/3.0 | 60% after 1 slots | #1: x1.44 sell 33% (n=11); #2: x1.63 sell 55% (n=7); #3: x1.85 sell 77% (n=5) | 15% | x0.87 (n=8) | 37.0 |
| 9Sh2fd | 8YcbyX | 16 | -3.84 | 4.9/2.5 | 75% after 8 slots | #1: x1.33 sell 95% (n=2) | 50% | x0.80 (n=10) | 7.5 |
| 9Sh2fd | E4FPgg | 15 | +0.38 | 1.2/0.8 | 10% after 2 slots | #1: x1.31 sell 60% (n=5); #2: x1.51 sell 60% (n=5); #3: x1.71 sell 60% (n=3) | 25% | x0.79 (n=8) | 24 |
| 9Sh2fd | HF2EGx | 10 | -1.45 | 1.8 | 65% after 1 slots | #1: x1.26 sell 60% (n=3); #2: x1.36 sell 60% (n=3); #3: x1.61 sell 60% (n=3) | 25% | x0.83 (n=6) | 11.0 |
| 9Sh2fd | FiwwHe | 9 | +2.83 | 3.0/0.8 | 50% after 5 slots | #1: x1.40 sell 50% (n=4); #2: x1.70 sell 55% (n=3); #3: x1.66 sell 50% (n=1) | 20% | x0.87 (n=4) | 27 |
| 9Sh2fd | 6gAgy3 | 8 | +1.48 | 1.8 | 70% after 0 slots | #1: x1.25 sell 60% (n=7); #2: x1.39 sell 60% (n=5); #3: x1.45 sell 20% (n=4) | 20% | - | 29.0 |
| 9Sh2fd | GpTXmk | 8 | -0.74 | 1.8 | 65% after 2 slots | #1: x1.31 sell 33% (n=1); #2: x1.51 sell 44% (n=1); #3: x1.71 sell 66% (n=1) | 65% | x0.84 (n=5) | 23.0 |
| 9Sh2fd | Hp34go | 7 | -0.18 | 3.0/1.8 | 50% after 2 slots | #1: x1.19 sell 20% (n=4); #2: x1.24 sell 33% (n=1); #3: x1.40 sell 44% (n=1) | 20% | x0.77 (n=3) | 47 |
| 9Sh2fd | 29yFze | 6 | -0.06 | 1.8/3.0 | 80% after 1 slots | #1: x1.76 sell 25% (n=2); #2: x1.47 sell 44% (n=1) | 15% | x0.81 (n=4) | 18.0 |
| DGmspi | 5ZdusG | 87 | +3.10 | 1.2/1.8 | 10% after 2 slots | #1: x1.19 sell 25% (n=38); #2: x1.37 sell 33% (n=15); #3: x1.65 sell 44% (n=7) | 25% | x0.97 (n=34) | 276 |
| DGmspi | AAPgis | 9 | +4.34 | 3.0/1.8 | 35% after 1 slots | #1: x1.41 sell 33% (n=7); #2: x1.60 sell 33% (n=4); #3: x1.70 sell 33% (n=3) | 33% | x0.80 (n=3) | 74 |
| DGmspi | 46qTwe | 6 | -0.16 | 2.0/1.8 | 50% after 2 slots | #1: x1.16 sell 60% (n=2) | 25% | x0.89 (n=4) | 11.0 |
| DGmspi | 5pUgxQ | 6 | -0.13 | 1.8 | 20% after 0 slots | - | 21% | x0.99 (n=3) | 299.0 |
| DGmspi | 7Ua7QX | 5 | +0.09 | 5.0 | 70% after 1 slots | #1: x1.36 sell 25% (n=2); #2: x1.54 sell 45% (n=2); #3: x1.75 sell 55% (n=2) | 25% | x0.62 (n=2) | 20 |
| DGmspi | C2TFei | 5 | -1.02 | 3.0 | 65% after 3 slots | #1: x1.29 sell 25% (n=1); #2: x1.43 sell 33% (n=1); #3: x1.47 sell 33% (n=1) | 20% | x0.78 (n=3) | 68 |

- **Table notes:**
  - Take-profit steps list the median price ×entry of the 1st, 2nd and 3rd sell at a new high, and the most common % of the rest sold.
  - "Clear below entry" is the median price of final sells under entry. Most are stop-loss fills; some are dev dumps.

## 4. Where the profit comes from (MEASURED, 10-17..10-22)
Each sell's PnL = SOL received net of all its costs − the all-in cost of the tokens it sold.

| piece | 9Sh2fd | DGmspi |
|---|---|---|
| lightning sell (first sell ≤8 slots, partial) | **+13.78** (45% of all tokens bought) | **+8.83** (35%) |
| take-profit sells (at new highs) | **+21.61** (10%) | **+19.82** (12%) |
| down-sells (pullback trims) | +8.16 (9%) | +4.63 (11%) |
| clear at or above entry | +5.96 (11%) | +2.46 (20%) |
| clear below entry (stop, dev dump) | **−38.47** (25%) | **−19.29** (21%) |
| total | +11.05 | +16.46 |

- **Price bands:** pieces sold at ≥ ×1.15 made +55.8 (9Sh2fd) and +43.0 (DGmspi). Pieces sold below ×1.0 lost −42.6 and −24.8. The ×1.0–1.15 band is about break-even after fees (−2.2 / −1.7).
- **Winners' profit by sale price:**

  | | 9Sh2fd | DGmspi |
  |---|---|---|
  | winners' total | +52.78 | +40.11 |
  | from pieces sold ≥ ×2 | +8.52 (16%) | +5.27 (13%) |
  | from pieces sold ≥ ×1.5 | +26.70 (51%) | +15.26 (38%) |
  | from pieces sold ≥ ×1.3 | +42.26 (80%) | +29.76 (74%) |

  The money is made at **×1.15–2**, not on moonshots.

## 5. The exit as an explicit rule (INFERRED) and its replay against their real results

### 5.1 The rule (AKbot semantics)
**Conventions:**
- **Entry** = the buy's curve exec price (SOL into the curve ÷ tokens).
- **When rules run:** after every market trade on the token.
- **Fractions** are of what is left.
- **Execution:** right after the trade that triggered it, in the same slot. MEASURED: 65–71% of their reactions land in the same slot.

**The rule:**
1. **Lightning:** sell `L` of the position `D` slots after the buy, at any price.
2. **Take-profit ladder:** at entry×(1+`g1`) sell `s1`. Then at every further +`step` (cumulative from entry) sell `s`. One sell per trade, even if several steps are crossed at once.
3. **Down-sells:**
   - armed once price ≥ entry×(1+`act`);
   - the reference moves only on a new peak;
   - when price ≤ reference×(1−`dd`), sell `dd_f`, and the reference resets to that price;
   - repeatable.
4. **Stop:** price ≤ entry×(1−`sl`) → sell 100%.
5. **Timeout:** `T` s after the buy, or after the last take-profit sell → sell 100%.
6. **Dev:** mirror the dev's sold %, or clear when the dev has sold out.
7. **Dust:** a partial sell that would leave less than 0.01 SOL clears the position.

| parameter | MEASURED range over their configs | best single rule (fitted, all 174 tokens) | consensus (token-weighted median of config fits) |
|---|---|---|---|
| `L`, lightning size | 10–90% (median 60% 9Sh2fd, 25% DGmspi) | 35% | 50% |
| `D`, lightning delay | 0–2 slots or 5–8 slots | 6 slots | 2 slots |
| `g1`, first take-profit | +19..+44% (config medians ×1.19–1.44) | +25% | +25% |
| `s1`, first take-profit size | 10–60% of the rest | 25% | 33% |
| `step`, then every | +15..+25% | +15% | +10% |
| `s`, later sizes | 10–66% of the rest (fixed, or rising 25→66%) | 25% | 33% |
| `act` / `dd` / `dd_f`, down-sells | after +10..+30% / 5–12% pullback / 5–25% | +20% / 8% / 10% | +20% / 8% / 15% |
| `sl`, stop | clears at ×0.86–0.89 (≈ −10..−12%) | none (the timeout does the job) | −6% |
| `T`, timeout | 60 s (DGmspi/5ZdusG) | 60 s after the last take-profit | 60 s |
| dev | same-slot reaction; some configs mirror | mirror | none |

`exit_rules.json` has every rule in machine-readable form, with these semantics.

### 5.2 Replay on their own entries vs their real per-token PnL
**Setup:**
- 174 tokens with full market paths: 95 from R1/R2 and 79 fetched. Their real PnL on these tokens is +2.99 SOL.
- **Same entry:** same buy SOL, same tokens, same slot.
- **Other traders:** their intents are kept and re-priced on the replayed curve (constant-product pump.fun curve).
- **Costs:** the same as theirs.

| rule | corr per token | MAE SOL/token | same sign | real | replay | corr 9Sh2fd / DGmspi | buys ≥2.4 SOL, real → replay |
|---|---|---|---|---|---|---|---|
| sanity: their ACTUAL sells replayed | 0.999 | — | — | +2.99 | +3.72 | — | — |
| fitted per config (wallet × dev, ≥4 tokens; else per wallet) | 0.915 | 0.134 | 90% | +2.99 | -4.99 | 0.95 / 0.85 | +3.11 → -4.43 |
| fitted per wallet | 0.884 | 0.176 | 88% | +2.99 | -3.92 | 0.92 / 0.82 | +3.11 → -3.60 |
| **best single rule** (global fit) | 0.873 | 0.203 | 87% | +2.99 | -5.86 | 0.92 / 0.81 | +3.11 → -4.42 |
| consensus (median of config fits) | 0.780 | 0.246 | 84% | +2.99 | -6.57 | 0.84 / 0.72 | +3.11 → -5.66 |

**By path source.** The 79 fetched paths stop ≤150 slots (~32 s) after their real last sell. A replayed position still open then is closed at that last price ("end-of-path"). The 95 collector paths are complete.

| rule | collector paths (95, complete): corr / MAE / same sign / real → replay | fetched paths (79, cut ~32 s after their exit) |
|---|---|---|
| fitted per config | 0.921 / 0.100 / 97% / −2.43 → −4.22 | 0.910 / 0.175 / 81% / +5.42 → −0.77 (47 positions closed at path end) |
| best single rule | 0.872 / 0.182 / 91% / −2.43 → −4.09 | 0.876 / 0.229 / 82% / +5.42 → −1.77 |
| consensus | 0.822 / 0.228 / 86% / −2.43 → −3.86 | 0.737 / 0.269 / 82% / +5.42 → −2.71 |
| their actual sells | 1.000 / 0.003 / 100% / −2.43 → −2.13 | 0.998 / 0.010 / 100% / +5.42 → +5.85 |

**Reading:**
- **MEASURED (replay):** on complete paths the per-config rules match real per-token PnL at corr 0.92 with the same sign 97% of the time, and the total is within 1.8 SOL. Most of the remaining gap is on the cut-off fetched paths.
- **MEASURED (replay):** within the configs that have their own fit (113 tokens), replay is within 1.7 SOL of real. The 61 tokens of thin configs carry 6.0 SOL of the gap. Real winners carry +8.5 SOL of it: the real ladders let more of the big winners run.
- **INFERRED:** the shape of the exit is fully captured. The exact per-config numbers matter for the tails.

**Rules fitted per config** (parameters are not unique; different combinations give similar PnL):

| fit | tokens | lightning | take-profit | down-sells | stop | timeout | dev | corr | MAE | real | replay |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 9Sh2fd:8HeDT7 | 31 | 50% at 6 slots | +20%: 25%, then every +20%: 15% | after +20%, each −12%: 15% | −15% | 60 s (after buy) | none | 0.968 | 0.081 | +1.22 | +0.02 |
| DGmspi:5ZdusG | 24 | 10% at 1 slots | +25%: 75%, then every +10%: 33% | after +30%, each −5%: 10% | −6% | 60 s (after last TP) | mirror dev % | 0.987 | 0.006 | -0.37 | -0.29 |
| 9Sh2fd:6aoG8G | 14 | 90% at 2 slots | +30%: 75%, then every +10%: 60% | after +20%, each −8%: 25% | −6% | 60 s (after buy) | none | 0.852 | 0.046 | +0.01 | +0.30 |
| 9Sh2fd:8YcbyX | 12 | 10% at 6 slots | +30%: 15%, then every +10%: 60% | after +10%, each −5%: 10% | none | 60 s (after buy) | none | 0.982 | 0.120 | -4.38 | -5.15 |
| 9Sh2fd:DWHEZ8 | 11 | 50% at 1 slots | +25%: 33%, then every +15%: 50% | after +20%, each −5%: 10% | −8% | none | none | 0.990 | 0.023 | +0.12 | -0.03 |
| DGmspi:AAPgis | 8 | none | +25%: 33%, then every +10%: 50% | after +20%, each −12%: 15% | −6% | none | none | 0.978 | 0.063 | +3.50 | +3.18 |
| 9Sh2fd:FiwwHe | 5 | 50% at 2 slots | +30%: 15%, then every +15%: 60% | after +20%, each −8%: 15% | none | 60 s (after buy) | none | 0.993 | 0.037 | +1.31 | +1.19 |
| DGmspi:5pUgxQ | 4 | 10% at 6 slots | +25%: 33%, then every +10%: 10% | after +10%, each −8%: 15% | −6% | 60 s (after buy) | none | 0.999 | 0.007 | +0.13 | +0.10 |
| 9Sh2fd:DfyGFR | 4 | 10% at 1 slots | +25%: 33%, then every +10%: 10% | after +10%, each −5%: 5% | −10% | 60 s (after buy) | none | 1.000 | 0.052 | -0.48 | -0.46 |
| global | 174 | 35% at 6 slots | +25%: 25%, then every +15%: 25% | after +20%, each −8%: 10% | none | 60 s (after last TP) | mirror dev % | 0.873 | 0.203 | +2.99 | -5.86 |
| wallet:9Sh2fd | 94 | 50% at 6 slots | +25%: 25%, then every +30%: 25% | after +30%, each −8%: 25% | −15% | 60 s (after last TP) | none | 0.923 | 0.177 | +3.47 | -1.32 |
| wallet:DGmspi | 80 | 25% at 2 slots | +20%: 33%, then every +15%: 33% | after +20%, each −5%: 25% | none | 60 s (after last TP) | mirror dev % | 0.819 | 0.174 | -0.49 | -2.60 |

**Biggest mismatches** (config rule set; PnL in SOL; the mint prefix is shown):

| wallet | token | config | real | replay | sells real / replay | links |
|---|---|---|---|---|---|---|
| DGmspi | 2rgb1DzS | BLbAr8 | +2.209 | +0.682 | 10 / 18 | [buy](https://solscan.io/tx/UKhb7FnBwhpQTwxAr8TB2WjigHfKgiGJZmpdwCm6ArKiKRbRnj9YCrg1bLgATE39CFry6NJbXem1WmfaMQ8SuoQ) · [last sell](https://solscan.io/tx/5TVoaDPqgjFJSzG8rEp73TUisYbP9d42mvSz6rBcd1ALKwDGYyb3ZJL1yZL4am6RUQQFX2V4L1XwRNmSAswNj2Kh) · [gmgn](https://gmgn.ai/sol/token/2rgb1DzSMZefoej3rg7EkbXpgFpTE5gV7puVdE7kpump) |
| DGmspi | EyYAEWJL | BLbAr8 | -1.402 | -0.150 | 2 / 9 | [buy](https://solscan.io/tx/5skTC4JzfNqnHZgHCqxfQqTCpuWg5E9zDrYHTFSyazWtsko1RrUvev8GEknYrEgB3KFnHaTCTJQ1jQho8As8Mbtg) · [last sell](https://solscan.io/tx/4e4Ef9F45d6nguYHQWzsLeDwmJtTbPCeqmoUdSZgAcM79jS8MxhYomkNCd4fLe92sDbgFL34bdgC1i6G3y4zH34Y) · [gmgn](https://gmgn.ai/sol/token/EyYAEWJLRiUdpSZgJJZUmV5zKH1tnq9JpJzYFwEipump) |
| DGmspi | 9ABYMq6R | 7hbihg | +0.459 | -0.748 | 12 / 5 | [buy](https://solscan.io/tx/59FoWqnCk4AHrehFfsKYvFgpVvyHcWqFqVtyr2GZ4KLHepDwhbkikXzmn2QCfvLiXFkvjexGiV5nczYC2FWpjQU9) · [last sell](https://solscan.io/tx/osjL7pukxRyxtthm3tebgxsUdNfE1h7ydKBtoL978ahkUug1yheSCMYydpcBe7QMAvPktHHthVQ3q6k4cACdYeR) · [gmgn](https://gmgn.ai/sol/token/9ABYMq6Rfnw5QqpLWZMcFbAS7yuryx9XHP87JpKfpump) |
| DGmspi | 7EAFMo9C | BLbAr8 | -1.925 | -0.801 | 1 / 2 | [buy](https://solscan.io/tx/4hWNertvyPzzY9NPUKDVRSeDojFhNeHxZD5JuLNTvCPsUgj6KkbA5RfL61ZCoKddfd6wzurVxSpWFywKh5S2YTSj) · [last sell](https://solscan.io/tx/2zeCyrTDkmGmQWBUvEoWUJ5P47bX9JQD4womvWCsoPVjdgVKrM9pNVcAvYQdwku6ZxXvVxopK6ShBKKZDpVdXveA) · [gmgn](https://gmgn.ai/sol/token/7EAFMo9CL5snvyLJPoyWBUda3T1tCQF7GEqGYjbupump) |
| 9Sh2fd | G9WuTdRa | 111111 | +2.231 | +1.155 | 21 / 18 | [buy](https://solscan.io/tx/3DBHScruJEAnADF1dF399gWWrJvCSwqgig4gNC1YjoGf6fprKwdWvh5LyLGmL2vSsmRRy1Ruga2cmMFAxdFcNrwx) · [last sell](https://solscan.io/tx/y3jem5tbXwFesHKz1bSFYuNpp7UbQ35oDkFKtyLrZqurdrvmhmUMZHmbbEiaGczxDt7PUsTMYbkQrhxqyMTRUs5) · [gmgn](https://gmgn.ai/sol/token/G9WuTdRa3UErXAAZaF6gpkA4g4bQ6vcqPqs1YB6kTKXB) |
| 9Sh2fd | 6gaAau8U | GEKZWL | +2.598 | +1.637 | 5 / 7 | [buy](https://solscan.io/tx/FC7cq9KDVGYYC7XfFKEDjCyha3BiWNEcGmtpXkgYf5KST3VxuaiuK1EjdzJhTZrBoEzpJ6X3zndBDNKG9Gr17hk) · [last sell](https://solscan.io/tx/5bYEgvmUEUtCyEij5aVpQZrsBoCh3tpYaJzZq64Z8JF5w12ZEGLTqFuxU83zvdwWymyBAmguUgHe8BgFuEZb4g8P) · [gmgn](https://gmgn.ai/sol/token/6gaAau8UJR3BPtLn9VqPueAW3NM95Kxd97Rsmjqupump) |
| 9Sh2fd | DXwUMy2A | 8YcbyX | -0.721 | -1.480 | 2 / 8 | [buy](https://solscan.io/tx/dy6nSrV221pxKNFidmYGRmCByhhxvxHfFEsHP4tMnBrzguq1WhBfLyVPWqKPizGRsRvME7HFxqvXjrv9iiGpgiY) · [last sell](https://solscan.io/tx/4MEtq1DRYGaBNPKAX8SPFxn1T82B3U6KoNK9fqaWcoegHwE2qGq1N1iwNMpGZZ5jHJgM88c6QqRBwWwxZirFSqja) · [gmgn](https://gmgn.ai/sol/token/DXwUMy2AX4YefBjtDdUpwKx2Q97r3xo4qMGtJR3vpump) |
| 9Sh2fd | [masked] | 4WwuoF | +0.447 | -0.197 | 4 / 2 | [buy](https://solscan.io/tx/Vz6cGhD2UnfaERhm9yNou6eGgf5v5jQAXyorXYY6dr7fJvUjqcaNDVwotzAXgJhyHCzp7VuSZTR6gP5x52TbufC) · [last sell](https://solscan.io/tx/5xGuRz7VHyqrr1Ps9b8xJuqfjXLN24hBZs15w3QChJWZZoBtKzin41qPYJsd1M4JDm6dSxzpx4witLMk2BeSARCD) · [gmgn](https://gmgn.ai/sol/token/ASSu5P37ZJHF7kjBUnd9G2E4jpFBpzKVNZXt8LPRpump) |

- **Where the mismatches come from (MEASURED):**
  - BLbAr8 (DGmspi) has no tight stop. It held 7EAFMo9C to ×0.60 and EyYAEW to ×0.66, so real losses exceed the replay's.
  - Big real winners (2rgb1D, 6gaAau, G9WuTd) rode further than any fitted ladder.

### 5.3 Is a different exit better on their entries? (INFERRED, in-sample with a cross-check)
- **In-sample best:** the rule in this family that maximizes replay PnL on all 174 tokens makes +3.19 SOL vs real +2.99. That is no real gain.
- **Per wallet, in-sample:** +6.30 (9Sh2fd) and +2.25 (DGmspi).
- **Cross-wallet (out of sample):** applied to the other wallet, those rules make
  - 9Sh2fd's best on DGmspi: -4.97 vs real -0.49;
  - DGmspi's best on 9Sh2fd: -0.55 vs real +3.48.
- **Conclusion:** no generic rule beats their per-dev presets out of sample.

## 6. Which pieces carry the profit: replay ablation (174 path tokens)
Each token is replayed with one piece of its rule switched off. Changes are vs the full rule.

| replay on their entries (real result +2.99 SOL) | config rule set | consensus rule |
|---|---|---|
| full rule | −4.99 (corr 0.915) | −6.57 (corr 0.780) |
| without lightning sell | −5.03 (−0.04; buys ≥2.4 SOL −0.36) | −5.63 (+0.94; ≥2.4: −0.80) |
| without take-profit ladder | −1.58 (+3.41; ≥2.4: −0.71) | −0.66 (+5.91; ≥2.4: +5.37) |
| without down-sells | −6.55 (−1.56; ≥2.4: −1.48) | −6.17 (+0.40) |
| without stop | −4.29 (+0.70; ≥2.4: −0.17) | −4.65 (+1.91; ≥2.4: −0.07) |
| without dev reaction | −5.43 (−0.44) | −6.57 (0) |
| without timeout | −6.25 (−1.26; ≥2.4: −0.82) | −6.38 (+0.18) |
| replay PnL of each piece, by trigger | take-profit +24.6, lightning +1.4, down-sells −1.1, timeout −6.4, dev −6.9, stop −7.3, end-of-path −9.3 | take-profit +17.6, lightning +1.6, down-sells −0.7, timeout −0.9, stop −24.2 |

**Simple baselines on the same entries:**

| baseline | replay PnL |
|---|---|
| sell 100% 1 slot after the buy | −17.95 SOL |
| sell 100% 6 slots after the buy | −4.41 SOL |
| −10% stop only, else hold to the end of the path | −49.56 SOL |
| 60 s timeout only | −15.22 SOL |

**Reading:**
- **Sell timing is the big lever (MEASURED, replay).** Selling everything 1 slot after the buy: −17.95 SOL. Waiting 6 slots (≈1.3 s): −4.41. Their real exits: +2.99.
  - Holding with only a −10% stop: −49.6.
  - A 60 s timeout alone: −15.2.
- **Lightning sell vs its counterfactual (MEASURED):**
  - As a piece of PnL it is strongly positive: +13.8 / +8.8 SOL in section 4.
  - The counterfactual is much smaller. Without it, the same tokens are sold a bit later by the other rules at similar prices: −0.04 SOL overall, −0.36 on buys ≥2.4 SOL.
  - What it really does is lock in the first ~1 s pop on a large chunk before the dev can dump.
- **The stop (MEASURED):**
  - Losing clears were followed by a median further −20% within 5 minutes, so each clear saved about 20% of the remaining value.
  - In the replays the stop's net effect is small (+0.7 / +1.9 SOL without it). The timeout, the down-sells and the dev reaction already catch most of those losers.
  - INFERRED: the stop only matters when a config has no timeout. The BLbAr8 losses are what happens without one.
- **Take-profit ladder:** the config-level ladders are worth +24 SOL in replay (piece PnL by trigger). Switching the ladder off changes the 174-token total by +3.4 / +5.9 SOL, but it hurts the ≥2.4 SOL buys in the config set (−0.71).
  - INFERRED: early, small take-profit steps cost money on quiet tokens and pay on runners. Their real ladders differ per config, and the generic ones are worse than theirs.


## 7. Files (ops/overnight/exits/)
- `roundtrips_9Sh2fd.json`, `roundtrips_DGmspi.json`: every token's buy and sell legs:
  - slot, slots and seconds after the buy;
  - fraction of the position sold;
  - price ×entry before the sell and at the fill;
  - SOL, fees and tips;
  - PnL; `period` = ledger or recent.
- `exit_rules.json`: machine-readable rules (consensus, per config, per wallet, global) with their exact semantics and replay-vs-real match.
- **Scripts:**
  - `roundtrips.py`: legs and PnL;
  - `analyze.py`, `attribution.py`, `config_table.py`: measured behaviour;
  - `align.py`, `triggers.py`, `after_clear.py`: market alignment;
  - `sim.py`, `replay.py`: replay engine;
  - `fit.py`, `fit_all.py`, `compare.py`, `ablate.py`: rule fitting and tests;
  - `fetch_*.py`, `rpc.py`: read-only RPC.
- **Outputs:** `analyze.txt`, `attribution.txt`, `triggers.txt`, `after_clear.txt`, `config_table.md`, `fits/`, `compare_*.txt`, `ablate_*.txt`.

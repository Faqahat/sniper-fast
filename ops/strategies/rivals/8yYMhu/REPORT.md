# 8yYMhu ("INSLOT"): independent check of the shared analysis (10-29 ~03:30 PKT)

Wallet **8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3** ([GMGN](https://gmgn.ai/sol/address/8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3)).

Offline and read-only: no sends, no server writes, no engine changes. Times are PKT. M = MEASURED, I = INFERRED.

Code: `/home/moiz/sniper/ops/strategies/rivals/8yYMhu/` (`run_all.sh` rebuilds every table). Data: `/home/moiz/sniper-data/rivals/8yYMhu/`.

Sources:
- **Signatures:** all 33,361 of the wallet's (public RPC; first tx 10-25 11:28 PKT).
- **Recordings:** every recorded line that mentions it, 33,161 txs.
- **RPC transactions:** 767 getTransaction calls:
  - the 141 txs the recorder missed;
  - 12 window-boundary txs;
  - 537 buy or failed txs and 123 sells, for instruction data.
- **Market tape:** the haqqml tape of every pump.fun curve trade, up to 10-29 00:55 PKT.
- **Our runs:** FRA r27/r28 and AMS r34, plus AMS r35 fill events copied read-only from the AMS server at 10-29 02:10.

Clock: chain clock = slot × 212 ms + position in the block, the same convention as the E2x1 report.

## 1. Claim-by-claim verdicts

| Claim | Measured | Verdict |
|---|---|---|
| +365 SOL gross in ~3.5 days, ≈ +100/day before his fees | Curve gross (sell SOL − buy SOL, before pump and creator fees), 10-25 11:36 → 10-29 00:00 (3.52 days): **+364.5 SOL = +103.5/day**. Pump + creator fees −204.4; tx fees, tips and rent −15.4; failed txs −1.5 → **NET +143.3 SOL (+40.7/day)** | TRUE as stated; the NET is 39 % of it |
| 7,357 tokens traded (~2,000/day) | 7,357 mints on the tape to 10-29 00:55 (7,545 to 02:00). Per full day: 2,244 / 2,328 / 2,053 tokens and 3,412 / 3,568 / 3,158 buys | TRUE |
| Buy size 0.75 SOL fixed | Spend including 1.25 % pump fees, p5/25/50/75/95: 0.506 / 0.731 / **0.759** / 0.780 / 0.809. Two bots: MAIN-75 (10,028 lots, 0.75 SOL target) and TIMER6-50 (1,433 lots, 0.5 SOL). The buy instruction (BuyV3) asks for a fixed token amount, so the SOL spent varies | MOSTLY |
| Same slot as a ≥1 SOL sell, 97 % | **98.6 %** (11,035 of 11,194). Enforced on chain: a slot ≤ dump-slot check in 529 of 529 decoded buys | TRUE, by design |
| Hold median 9 slots, middle half 6–31 | **6 / 8 / 26** slots (p25/50/75). 10-25 alone: 6/10/31. MAIN-75: 6/10/32. TIMER6-50: 6/6/6. Max 73 | CLOSE |
| 57 % of tokens win, +50 mSOL per token | Before pump fees **56.9 %, +49.4**; after pump fees 44.9 %, +21.4; after all costs **44.1 %, +19.2** | TRUE before fees only |
| 24/7, busiest 19:00–23:00 PKT | Every PKT hour has ≥ 288 buys over 3.7 days. The 19:00–01:00 hours have 628–884 buys each. Net is positive in 23 of 24 hours | TRUE |

## 2. Money (M)

### 2a. 24 h window, 10-27 20:00 → 10-28 20:00 PKT
- 9,919 signatures, of which 3,062 failed. 9,907 came from the recordings and 12 from RPC; none missing.
- Start balance is the preBalance of the first tx, [4nCaMCJG](https://solscan.io/tx/4nCaMCJG1fNTWTd4PXdmLsnPfhwdKuGXuKpWFh5CzcmAWrFLrUwfb2wVA9Em5vpYK5zBDW1gJw8NQ1ExPSi2AU9K): **95.904112571**.
- End balance is the postBalance of the last tx, [3jJ4iUBL](https://solscan.io/tx/3jJ4iUBLzU4tgpNBoeFZNvGRJ66sQfnqf4TnczzPa2YsCkBQyV2UC8b92aqLhQjJKDpHjQPB7mhsMkUpAwBvbmku): **126.862879935**.

| Line | n | SOL |
|---|---|---|
| Curve SOL into buys | 3,426 | −2,472.616613696 |
| Curve SOL out of sells | 3,426 | +2,570.979194235 |
| **Curve gross** | | **+98.362580539** |
| Pump fee | | −47.914163644 |
| Creator fee | | −15.130790823 |
| PumpSwap sell (after graduation) | 1 | +0.891741347 |
| Tx fees on landed txs | | −0.962830327 |
| Tips | | −3.782536715 |
| Failed-tx fees | 3,062 | −0.455766010 |
| Token-account rent paid | | −6.986573280 |
| Token-account rent returned | | +6.986573280 |
| Other lamports inside trade txs (curve realloc rent, small unlisted tips) | | −0.049488427 |
| **Trading NET** | | **+30.958745940** |
| Dust transfers in | 4 | +0.000021424 |
| **Predicted change = chain change** | | **+30.958767364** |
| **Residual** | | **0 lamports** |

### 2b. Whole life by PKT day (cash basis)
The ledger is the sum of exact per-tx deltas from the first tx, whose preBalance is 0. It matches the RPC balance at 12 boundary txs to 0 lamports.

| Day | Buys | Failed | Curve gross | Pump + creator fees | **Trading NET** | Other flows | End balance |
|---|---|---|---|---|---|---|---|
| 10-25 (from 11:28) | 950 | 989 | +31.431 | −16.975 | **+13.105** | funding +10.481, nonce rent −0.087 | 23.499 |
| 10-26 | 3,412 | 3,009 | +114.842 | −62.826 | **+48.860** | **withdrawal −16.000**, nonce rent −0.087 | 56.272 |
| 10-27 | 3,568 | 3,140 | +117.414 | −66.125 | **+46.543** | | 102.815 |
| 10-28 | 3,158 | 2,765 | +97.145 | −58.459 | **+34.760** | | 137.575 |
| Life (to 10-29 02:00) | | | | | **+144.055** | | 138.362 |

- **Funding:** from DScDQ1zV at 10-25 11:28–11:29: [0.957 SOL](https://solscan.io/tx/3zmPDbwpCdt6DrNRUpfPQsfAL8RR9vbNsd8ExbbeyCbYouJa7xau5JBoPCod7Pkq6smJxwtrtH3ijkW9nDJZ73jj) and [9.524 SOL](https://solscan.io/tx/dsn3iQDCaJhQkQtMNr3MythxpPtsAK71YKaeaQRJVQgSnW3ZPoo5c1myDAyNDcBQkzMsPWq2ff8M4ufbiLX6Ybk).
- **Withdrawal:** [16.000 SOL to 441gE75X…](https://solscan.io/tx/2daJ2itrLyL27mHNsrsKQL2nxxNnQWcU5CsUxGiudSYCgFoGSz6BZVi6fTdHhyrUjZ85NDWkpecaZ7j8jC43oFzr) on 10-26 17:20.

### 2c. The two bots, 24 h exact split
Every in-window lamport is assigned to a bot through its position; the lines sum to the trading NET to the lamport.

| Bot | 24 h cash NET | Lots | mSOL/lot | Return on SOL | Win | Hold p25/50/75 | Exits at 3 / 6 / 60–62 slots |
|---|---|---|---|---|---|---|---|
| **MAIN-75** (0.75 SOL) | **+23.724877477** | 2,999 | +7.9 | +1.04 % | 44 % | 6/10/32 | 12 % / 12 % / 16 % |
| **TIMER6-50** (0.5 SOL) | **+7.450123405** | 427 | +17.4 | +3.47 % | 56 % | 6/6/6 | 0 % / 95 % / 0 % |
| Failed attempts that never filled | −0.216254942 | 1,450 txs | | | | | |
| **Sum = trading NET** | **+30.958745940** (0 lamports off) | | | | | | |

- Both bots use the same signer, nonce pool and send paths.
- TIMER6-50 takes deeper dumps: price drop p50 12 % vs 10 %, seller's share of supply 5.1 % vs 4.2 %.
- 624 dumps were bought by both bots, about 4 txs apart.
- Per day, MAIN-75 / TIMER6-50:

| Day | MAIN-75 | TIMER6-50 |
|---|---|---|
| 10-26 | +44.4 | +6.4 |
| 10-27 | +39.2 | +5.8 |
| 10-28 | +27.3 | +7.6 |

## 3. How it lands (M unless marked)

### 3a. What every buy contains
537 decoded buys ([example](https://solscan.io/tx/4fbqmHHiSPEW737jT72NEwHc1ndX46RFuzP7i6DEnmZoT1EkJFrNxpXgPEcFKYefMBQ9aXiMGCuCLf5pjpFiiqyR)).

1. **Durable-nonce advance.**
   - A position's sell uses the same nonce account as its buy (33 of 33).
   - The pool has 120 nonce accounts:
     - 24 seeded `inslot-nonce-NN`, 24 `inslot-ult-nonce-NN` and 12 `inslot-dm-nonce-NN`, created 10-25;
     - 60 with random seeds, created 10-26 17:27, seven minutes after the withdrawal.
   - The seeds carry no region tags (E2x1's do).
2. **Compute budget.** CU limit 51–60k. CU price p10/50/90 2.35 / 2.54 / 2.67 M µL/CU, about 0.14 mSOL per tx.
3. **Lighthouse slot check: slot ≤ D.**
   - D equals the dump's own slot in 507 of 529 decoded buys; the rest are trigger mismatches on my side.
   - All 322 decoded landed buys sit exactly in slot D.
   - Late copies land at D+1 (62) or D+2 (2) and fail with **6001**.
4. **Lighthouse price band on the bonding curve.** It checks the curve's virtual SOL reserves (offset 16):
   - **Lower bound:** 0.8805 × the level right after the dump (p5–p95 0.866–0.965). This refuses the buy if a second dump lands first.
   - **Upper bound:** 1.040 × that level (p5–p95 1.018–1.197). This refuses the buy if others already bought the bounce.
   - Failing either bound gives **6401**.
   - Landed buys sat at 0.81 of the band (median).
5. **A fresh token account per position** (createAccountWithSeed). A duplicate copy fails with Custom 0 ("account already in use").
6. **pump BuyV3:** an exact token amount for about 0.75 (or 0.5) SOL, with max SOL = 1.08 × the spend. When the cost is higher it fails with **6002** ("TooMuchSolRequired").
7. **Tip, which depends on the copy:**

| Path | Tip p50 (lamports) | Decoded buy txs |
|---|---|---|
| nozomi | 1,087,452 | 227 |
| no tip | 0 | 120 |
| helius | 330,532 | 42 |
| soyas | 1,066,582 | 40 |
| 0slot | 328,221 | 31 |
| flashblock | 321,706 | 26 |
| falcon | 1,076,559 | 18 |
| stellium | 1,071,693 | 16 |
| blockrazor | 317,547 | 13 |
| jito | 336,693 | 4 |

- Copies of one order mostly use different nonce accounts (12 of 15 sampled), so a second copy can still land. It then fails on the band or slippage check (1,538 such failed copies on filled orders).
- **Sells:** sell the full balance with a minimum SOL out of about 0.76 × the fill, use the same nonce account as the buy, and mostly tip helius 0.3 mSOL.

### 3b. Timing of landed buys

| Measure | Value |
|---|---|
| Index gap dump → buy, p10/25/50/75/90 | 32 / 47 / **73** / 115 / 187 txs |
| Chain-clock delay, p10/25/50/75/90 | 17 / 25 / **37** / 54 / 79 ms |
| Lands within 10 txs of the dump | 0.7 % |
| Lands within 25 txs | 5.6 % |
| Is the first outside buyer after the dump | 58 % |

Same definition as the E2x1 report (previous outside trade = a sell ≥ 0.5 SOL within 2 slots):

| Wallet | Delay p50 |
|---|---|
| **8yYMhu** | **33 ms** (p25 23, p75 49; n 6,106) |
| E2x1 | 44 ms |
| haqq | 45 ms |
| **Our pre-send fills** | **20 ms** |

By leader location (8yYMhu): DE 33 ms, NL 30, other EU 39, N. America 59 (n 24).

### 3c. Fill rate vs where the dump sits in its block
18,264 orders (attempts grouped by token and dump), 57.8 % filled.

| Dump position in its block | 0–0.2 | 0.2–0.4 | 0.4–0.6 | 0.6–0.8 | 0.8–0.9 | 0.9–1.0 |
|---|---|---|---|---|---|---|
| Orders | 4,278 | 3,678 | 3,609 | 3,303 | 1,663 | 1,733 |
| Filled | 69 % | 70 % | 68 % | 60 % | 30 % | **7 %** |
| Only a late copy reached the chain | 6 % | 6 % | 10 % | 23 % | 64 % | **91 %** |

- How often it tries does not depend on the dump's position (4.1–4.5 %); only the fill rate collapses.
- So it needs about 35–40 ms of block left after the dump. That fits a feed that shows the slot while it is being built (I: shreds or preconfirmations).

### 3d. Failed transactions

| | All days | 24 h |
|---|---|---|
| Failed txs | 10,286 (0.90 per fill) | 3,062 (0.89 per fill) |
| 6001 late (slot check) | 5,146 | 1,561 |
| 6401 / 6400 price band | 3,361 | 1,011 |
| 6002 pump slippage | 1,503 | 406 |
| Custom 0 duplicate | 205 | 72 |
| Other | 71 | 12 |
| Fee | 1.518 SOL (0.148 mSOL each) | 0.456 SOL |

- No 6042 errors at all.
- Ours, from run records: FRA r27 173, FRA r28 144, AMS r34 148 failed tries per fill (mostly 6042), costing 0.73–0.86 mSOL per fill.

### 3e. Which copy lands, by leader client

| Leader client | n | Landed copy |
|---|---|---|
| Harmonic | 4,160 | nozomi 89 % |
| BAM | 3,131 | nozomi 80 % |
| Jito | 3,371 | nozomi 28 %, helius 26 %, no tip 19 %, soyas 11 % |
| Firedancer | 531 | no tip 42 %, nozomi 25 % |
| Agave | 141 | stellium 67 % |

**Region:** buy slots by leader location are DE 5,099, NL 3,540, other EU 2,743, N. America 54, Asia 25. It takes 5.7–5.8 % of dumps on EU leaders but only 0.21 % on N. America and 0.32 % on Asia leaders. So it runs one European engine.

**Verdict:** it lands by reacting inside the slot. The mechanism is measured; the feed type is inferred.
- It is not faster than our pre-send (20 ms vs its 33–37 ms).
- It reacts to any dump on any token, while our pre-send must be armed beforehand on whale tokens.

## 4. Selection

Universe: 421,693 outside curve sells ≥ 1 SOL from 10-25 13:00 to 10-29 00:50 (about 120–140k a day). It took 4.31 % and filled 10,507. Full tables are in `s2.txt`.

| Feature | Take rate |
|---|---|
| Sell size | 1.8 % at 1–1.5 SOL → 12.2 % at 3–5 → 16 % at 5–15 |
| Price drop | 0.05 % under 3 % → 8.0 % at 8–12 % → **14.5–15 % at 12–25 %** |
| Seller's share of supply sold | 0.02 % under 0.5 % → 13–15 % at ≥ 5 % |
| Token age | **11.8 % at 5–25 slots** → 0.5–0.7 % over 1,000 slots |
| Curve SOL after the dump | 9.0 % under 32 → 0.3 % over 100 |
| Seller type | creator 7.4 %; create-slot buyer 7.5 % (47 % of its takes); others 3.1 % |
| Mayhem tokens | **0 of 24,446** |

- **Paper P&L (inferred):** a 0.75 SOL buy about 37 ms after the dump, sold at +9 slots, with its own trades removed, after pump fees:
  - sells it took: **+17.1 mSOL** a trade;
  - sells it skipped: **−19.8**.
- **Model check:** at its exact entries and exits the model says +179.1 SOL vs its real +160.5, so the model is about 11 % optimistic.

Can a rule copy its picks? Trained 10-25 → 10-27 20:00, tested on 10-27 20:00 → 10-29 00:50 (unseen), with a cost of 3.5 mSOL per trade.

| Selector (test window) | Picks/day | Its share of picks | Paper mSOL/pick | Picks it did not take |
|---|---|---|---|---|
| Best simple rule (drop ≥ 18 %, curve ≤ 50 SOL, buy10 ≥ 5, EU) | 1,043 | 33 % | −6.7 | **−17 SOL/day** |
| GBDT imitation, top 1 % (AUC 0.963) | 1,341 | 76 % | +7.1 | **−9.9 mSOL** |
| GBDT profit model, top 1 % (AUC 0.707) | 1,267 | 30 % | +29.3 | +28.1 at 37 ms |

- *buy10* = outside buy volume in the 10 slots before the sell.
- The imitation model's top features: drop, EU leader, seller's supply share, trades in the last 10 slots, seller hold time, curve level.
- The profit model's own picks:
  - 64 % are far-leader dumps;
  - their tokens are older (age p50 116 slots).

How the profit model's picks do at later landings (picks it did not take, test, +9 slot exit, mSOL):

| Landing | All leaders | EU leaders only |
|---|---|---|
| ~37 ms | +28.1 | +18.4 |
| ~75 ms | +19.1 | +8.7 |
| First in next slot | +5.5 | −1.0 |
| **Our reactive landing** | **−11.7** | −12.9 |

Speed decides everything (inferred; test window, mSOL per 0.75 SOL trade, +9 slot exit):

| Set | Right after the dump | ~37 ms | ~75 ms | Next slot | Next slot +150 txs |
|---|---|---|---|---|---|
| Its fills | +19.5 | +6.2 | −5.8 | −13.4 | −15.1 |
| Its takes (incl. unfilled) | +37.2 | +13.0 | +1.0 | −7.2 | −15.5 |

**Who buys right after it:** within 3 slots there are about 4.1 wallets and 1.97 SOL per lot.
- haqqiUUX 17.1 % of lots, 3MHgGwdL 12.5 %, ssssswdk 12.0 %, 9pQQc1xy 11.2 %, 8PgC4ngp 6.4 %, EMKY7r6U 5.0 %, GKd5EMzR 4.8 %, sssssDdM 4.7 %, E2x1 2.2 %.
- These are the known dip-buying bots arriving on the same dump, not copy-traders.

## 5. Exit

**MAIN-75 (9,786 lots on the tape):**
- Hold p10/25/50/75/90 = 3 / 6 / 10 / 30 / 61 slots.
- Most common holds: 61 slots (1,270), 6 slots (1,162), 3 slots (1,158). It never sells before slot 3.
- Chance of selling at each slot, given it is still holding:

| Slot | 3 | 4 | 5 | 6 | 7–8 | 10 | 20 | 40 | **61** |
|---|---|---|---|---|---|---|---|---|---|
| Sell rate | 12 % | 7 % | 6 % | 15 % | 9 % | 6 % | 3 % | 1 % | **97 % (timeout ≈ 13 s)** |

- In slots 7–59 the sell rate rises with the position's return at the end of the previous slot:

| Return | < −8 % | −8 to −2 % | ±2 % | +2 to +8 % | > +8 % |
|---|---|---|---|---|---|
| Sell next slot | 2.8 % | 1.7 % | 4.4 % | 8.0 % | 11.7 % |

- **Timeouts:** 1,428 lots (15 %), net −71.2 SOL, 6 % win; all other lots +195.3.
- Cutting losers earlier would have made less: selling at slot 10 if below −5 % → −18.5 SOL; at slot 20 → −9.5; at slot 30 → −5.9.

**TIMER6-50:** 86 % sold at exactly 6 slots.

**Not exit triggers:**
- Follower flow: the sell rate is the same with or without outside buys in the previous slot (5.4 % vs 5.9 %).
- Other sellers: after a ≥ 1 SOL outside sell it is 4.6 % vs 5.9 %.
- No fixed take-profit, stop-loss, no-buy or timer rule matches more than 33 % of its exits.

**Value of its exit on its own entries (inferred):** its exit makes +179 SOL vs +103 for a 1–2 slot exit.

## 6. Head-to-head with us

Our 447 pre-send fills on the tape: FRA r27 200, FRA r28 78, AMS r34 120, AMS r35 49.

**On the 72 dumps we both bought:**
- **We landed first 69 times.**
- Ours realized **+2.694 SOL** (+37.4 mSOL per fill at 0.45 SOL). Its lots made **+0.308 SOL** (+4.3 mSOL per lot at 0.78 SOL), with a median hold of 10 slots.
- Our same 72 fills re-priced at other exits:

| Our exit | Real 200 ms | End of slot +1 | +2 | +5 | +9 | +31 | At its exit |
|---|---|---|---|---|---|---|---|
| SOL | **+2.783** | +3.266 | +3.238 | +2.315 | +1.690 | +0.351 | +2.421 |

**All 447 of our fills re-priced (inferred).** The model reproduces our real sells to the lamport.

| Exit | Real | +1 slot | +2 | +5 | +9 | +31 |
|---|---|---|---|---|---|---|
| SOL | **+2.982** | +4.602 | +3.617 | +2.203 | +2.094 | −0.668 |

| Run | Real | +1 slot | +9 slots |
|---|---|---|---|
| FRA r27 | +1.67 | +3.17 | +1.06 |
| FRA r28 | +0.55 | +0.48 | +0.02 |
| AMS r34 | +0.58 | +0.73 | +1.08 |
| AMS r35 | +0.18 | +0.22 | −0.07 |

**Its attempts on our filled dumps:**
- It did not try 308 of the 447. On the 139 it tried, we landed first 132 times.
- Its outcomes on those 139: landed 72, late 35, price band 18, slippage 14.
- Our fill lifts the price toward its band ceiling and its max SOL, so we likely cause some of its band and slippage failures (inferred).

**Earlier runs:** in FRA r16 and AMS r17/r19 (our old reactive engine, 60–90 ms) it was listed ahead of us.

## 7. What we could copy

**(a) Hold our pre-send fills longer: no.**
- At 9 slots we would make −0.89 SOL less over 447 fills, and at 31 slots −3.65 SOL less.
- One small lead: selling 1–2 slots after the fill instead of at 200 ms re-prices +0.6 to +1.6 SOL better (mostly FRA r27). Check with the exit200 tool before changing anything.

**(b) Widen pre-send arming: not to "any ≥ 1 SOL seller"** (inferred replay, `w1.txt`).
- Arm when a wallet's position first crosses X % of supply. Each arm costs 0.153 mSOL in failed tries (measured, FRA r28).
- A fill is a ≥ 1 SOL dump that drops the price ≥ 12 % within 10 slots.

| Arm threshold | Arms/day | Fills/day | Paper SOL/day after try cost |
|---|---|---|---|
| ≥ 6 % | 39k | 1,048 | +14.1 |
| ≥ 4 % | 66k | 1,430 | **+19.6** |
| ≥ 3 % | 99k | 1,473 | +15.6 |
| ≥ 2 % | 162k | 1,474 | +7.2 |
| ≥ 1 % (≈ any ≥ 1 SOL seller) | 310k | 1,472 | **−15.9** |

- Filling on smaller drops (≥ 5 %) loses below a 3 % arm.
- **Caveat:** the replay counts about 24× more arms than our live engine sends, because live filters remove most of them. Treat only the direction as meaningful. A ≥ 4 % whale threshold is the one lead, worth a shadow test.

**(c) Reactive same-slot buy like its own: not at our speed** (inferred, `c3.txt`). Its 11,191 lots replayed with the same exits but later entries:

| Its buy lands at | Total (SOL) | Per lot (mSOL) |
|---|---|---|
| Its real position | +179.1 | +16.0 |
| +73 txs (~37 ms later) | −35.8 | −3.2 |
| +150 txs | −64.9 | −5.8 |
| First in next slot | −81.5 | −7.3 |
| Next slot +150 txs (our ~58 ms reactive) | −109.8 | −9.8 |

**Cheap pieces (need your OK, since they touch the send path or engine):**
1. A slot ≤ dump-slot check on reactive buys. A late landing then fails for about 0.15 mSOL instead of filling stale; its own next-slot entries would lose −13 mSOL a trade.
2. A lower price band at 0.88× the post-dump curve, to skip a second dump that lands before our fill.
3. Send paths by leader client: nozomi first on Harmonic and BAM; helius or no-tip on Jito; stellium on Agave.
4. TIMER6-50 (0.5 SOL, fixed 6-slot exit) is its best bot per SOL, but only at its 37 ms entries. It is not a standalone strategy for us.

## 8. Example trades

### A. P&L, 24 h window (net including fees, tips and failed copies)

| Token | Buy | Sell | Net SOL | Hold (slots) |
|---|---|---|---|---|
| [G3B1EL3p](https://gmgn.ai/sol/token/G3B1EL3pQqUew4VogGdTCv9GteusaGHh5WrsSeaFKd7s) | [5kvyo6L3](https://solscan.io/tx/5kvyo6L3SHM6Ho8b745qqUpqqMaF2dup7ujKuSY3LwtV74Du3GWi1zLdvDnBvoEh81ngGwEuk5ZU5dRh1EUnWLSz) | [4WofxTBT](https://solscan.io/tx/4WofxTBTxBBd4tKkbv8pQQsQZpUha3cmAbHxkodBRYCAnXFAJAJ5V287B5yp2AgsHGoVMsL79QmVNxV7iPK7eXFu) | +0.938 | 3 |
| [3SHoWT1U](https://gmgn.ai/sol/token/3SHoWT1UKJ9ZwD68VQ6H6i1WLEQu98LKW5qDKaRQET5D) | [5hw9BNpF](https://solscan.io/tx/5hw9BNpFHPpvjWXsBCptSyzve4Jp8HsE4zQa3hhuHDjGTFebJQj7vn9DEvqA26ZBdNp5zvA6jnVNovTfN7ZQ57rB) | [3UxX2K4R](https://solscan.io/tx/3UxX2K4Rym35xMtjeRBv947mxeuCueXyC3c6FJG7e2BknHTXHGeronE7P4e7RjsJc7zWdTcGyQfWkGjbAEkygWyE) | +0.907 | 26 |
| [7T93VHF6](https://gmgn.ai/sol/token/7T93VHF6hGEUuuGrDmWD5Y5b43pWWPbNVH465yx9QWxg) | [3K1xArgp](https://solscan.io/tx/3K1xArgpwS79S3u8cQQU6ZnrMNnPx2tntmUWScL5RiiCrcCPPWbPhkMK6NqaRRbZFnSBuoqeoDPqkndvJZ3j1kMG) | [5UqEckpM](https://solscan.io/tx/5UqEckpMaX52ToihT7BBSbGxWGGcH99qPGyM4siv4oxUcttXWGqkYZ6ooEB4BmUoLeT3TCeYiEHG6nUiMuzgWhHk) | +0.898 | 19 |
| [4Wr6ruvV](https://gmgn.ai/sol/token/4Wr6ruvVChKxLerziDFLNUrK2XKVGDjdLjFxqukxpump) | [5EPocfzS](https://solscan.io/tx/5EPocfzSmzfW8pdKwZpPojoezyjy8ELmTCBPwmtouhXitpzRDAgMmaPA8KAYH2nX1JViugmLFhjs5LHLL6bAr79f) | [5stQ66xy](https://solscan.io/tx/5stQ66xy6M7bXdh3jcQM4DTk7cLkdvpfX8uNcpMyGL7zok2Z3MfaeHiKVvqeWCaN6EuBLHHWSnvCJqFTwnd9Ebm3) | −0.559 | 26 |
| [ELJoJQjJ](https://gmgn.ai/sol/token/ELJoJQjJ2CXfjypbfbbXv9rTiiDn7QHWDSPDd9GPpump) | [ksPN3geM](https://solscan.io/tx/ksPN3geMh3eUXagBjenc7nqyaEUR2WYjubeD5XoUSFRcSrjyrZP6YdUomroWaULv259ixSrHbgwYA1QTk1ndLhT) | [2BEkmW5Q](https://solscan.io/tx/2BEkmW5QwhkavuxwvF3z6Qy4s1ivbkrAoT24xdW1FEvv8VyCkRz5CbccAXTKsJpAjEDaaTzpVhRWaumJTETrq4Vx) | −0.545 | 33 |
| [C346fUM6](https://gmgn.ai/sol/token/C346fUM6AUXViu9H3GeMf8sQwdku7CYLRkCvtbWNbZhX) | [4sJwBVU6](https://solscan.io/tx/4sJwBVU6uz5F5SkbYhLxAUeaZ1PZtJASXnaoP2yPDotRKhrtgdFmFBZP4fF6zL9y8xd3WuHaDYgbeCchT2iyEv1e) | [3fqTfNE2](https://solscan.io/tx/3fqTfNE2UpCUahfDGngCTuJkYHmio9LJrkuDYtdQHqUWBrL2Bkn9bLBhkJ3cpMtRRNmbsMMio2UmLs1WR4FWTDzC) | +0.039 | 3 |

### B. Same slot as the dump (dump → its buy)

| Token | Its buy | Dump | Gap |
|---|---|---|---|
| [CNS9ZgYk](https://gmgn.ai/sol/token/CNS9ZgYkJ3mA3UQSZfuoYe1ZyA4rWo9zRMu1ziEupump) | [5yh1An5A](https://solscan.io/tx/5yh1An5AFDVWUNk8pBUbx3Eu85DJD5EZ7juZ2F63Q8dSHNUwicfg6WUWPMT79nYQiEa6rj97J4DN9dzdzEcNWqSb) | 4.48 SOL sell | 14 txs, 12 ms |
| [nnXpxNiB](https://gmgn.ai/sol/token/nnXpxNiBqg2cn8fYwj6JVFFR6pZ98vyCQ3i2t62QXMg) | [3QG7ZENP](https://solscan.io/tx/3QG7ZENPdrXAVvz3nJHa9rvxtmUKmgfunLgEbtTVJ8dAtpHxphFxN7Gm8SXB6fg6JjdSQy8VYSaVUUAYLo1amA9A) | 2.60 SOL | 34 txs, 27 ms |
| [7kqiZiiT](https://gmgn.ai/sol/token/7kqiZiiTrUFYkA4giB5ZhYpr8JTiKREbEwMMyVrFpump) | [xRVoGX1s](https://solscan.io/tx/xRVoGX1saBtQJejjLCPMzopo5ypPYzUd9vhUQNhSAmmUQ6XhgZ5WqokbNkfHrUTFqfNxa1RCwR6WyxcK2rv9PeU) | 1.55 SOL | 74 txs, 46 ms |
| [A1s541wQ](https://gmgn.ai/sol/token/A1s541wQbXRzrJMyygkE4r4dJeWAKua3qBfY6iv6pump) | [5zzHp2q1](https://solscan.io/tx/5zzHp2q1utRdVjumDR58p7LqZ2c4tzjgYDRXTJTudVBfiSz2CQYMWVmokXxaQnd93sYeH49gWMmVj9zbTC723hoQ) | 2.92 SOL | 174 txs, 65 ms |
| [Ckyxm6qw](https://gmgn.ai/sol/token/Ckyxm6qwgG9yKHEfyLUgYdXaBdeEmr3mxzUfj3PGFyhg) | [4wLKHqVv](https://solscan.io/tx/4wLKHqVvs42KkC46jZ1y9YU8DtLZnQhCBiHEUCwpiXm24BEWUeYHRcCRsBX8UqAGgTdLTt368SLUbJGkaSfrCBQc) | 1.48 SOL | 66 txs, 60 ms |
| [DsTbv7oB](https://gmgn.ai/sol/token/DsTbv7oBTLoEBvL4qyUyDqc7kCD29ShtpAc6WqHipump) | [2HFfE6Fj](https://solscan.io/tx/2HFfE6Fj8CmkWYVrrkeA4Jewt9mtP3NmCpNDjPJ5R7HBTfZGhtuC2Sc5XCkhAdsS7Q2LJmUDnPmdLa4CA5FzDK8x) | 3.55 SOL | 119 txs, 44 ms |

### C. Decoded checks in its buys

| Tx | Result | Check detail |
|---|---|---|
| [cMkHsVqZ](https://solscan.io/tx/cMkHsVqZSUBnL3AVNgCcbhPdyf6j5tTMrsurJYtoYH7ZKbFcaQjnq39LzruqesbxSjsoEFCecHPRjtmo2MxwR1D) | landed | deadline = dump slot 462171731; band 29.37–34.13 around 33.11 |
| [3d3bC4ja](https://solscan.io/tx/3d3bC4jageC55huS6j6kPTa6ypf5iw4XkNQwiQZQTtyE6wJDbYMFVsXNL2YhSDgs5XqKA8S9kG2s6SGZrNBBGv3j) | landed | band 26.44–31.36 around 30.15 |
| [4cZH1tCW](https://solscan.io/tx/4cZH1tCWKpg238Wm77DwhfzjNUfBA76WKumajxgY7GLF9GBbiinAebbSdqePw1KLj6ErdNpPGJoCHmjusnn81SMo) | landed | band 33.57–39.63 around 38.48 |
| [2orxbgGL](https://solscan.io/tx/2orxbgGLLov6fGajJr9PFnFB33jnyDK3bBF9kZTpYaxpb2JcZ8QB9szRk6Qrsp6en79dJaTrr32WigYsmqZu4N78) | 6001 | landed in slot 462113225, deadline 462113224 |
| [5YJJESVt](https://solscan.io/tx/5YJJESVtdujco2V5HRQBw1JkKJQMYC1dHQkUTTCYjwPavEyjNmYLvoWNqxUYXf4r5FwhLyFRoTxa86cwRD7e95va) | 6001 | landed one slot after the deadline |
| [2F4dqFut](https://solscan.io/tx/2F4dqFut8KDsuFYE2vGwN6ZddDZMwbiRmsiB4sRci4BEQF1DSq5jHwNWt5xDcFWjimXxbKNamXmrhS8qzRKU43uQ) | 6401 | price band |
| [9LGiDVPx](https://solscan.io/tx/9LGiDVPxM3jQwdh65r3FdVLBtN24cJm9ekCNuSjLbixTdrCC1izcep5ncfuVf2Q8g3qTsiwRNzR2cnovPonX65f) | 6002 | slippage |
| [5zfn9dqd](https://solscan.io/tx/5zfn9dqdiPJXCFtavQEvGiijs4K4P9idpGJvQiZ6JpRePdvv798ASLuxRoBsLVG2J1SED1hSjTzfn7EdtvTocTcX) | Custom 0 | duplicate account |

### D. Late failures (6001) when the dump sat late in its block

| Token | Failed tx | Dump position |
|---|---|---|
| [J6NTA5Fa](https://gmgn.ai/sol/token/J6NTA5Fa2Y9M3LBgtr5ib9Dote7Ub5wCdFzJ5EBEpump) | [4fkStL3q](https://solscan.io/tx/4fkStL3qG6Etk8JfBHZE28dn9GMVeXjykpvjKWoq5uWfB6tqLUTHnfkYixxPiNmSmtpaCq7znjef874MHAd4JsiQ) | 0.98 |
| [8jmfAHCf](https://gmgn.ai/sol/token/8jmfAHCfRXw6Fa1pYQGSDPAV1R7pT8kCbNxDiLz57nDz) | [6SuYJwSm](https://solscan.io/tx/6SuYJwSmHNsvAumZPVvDvneM6nuQccZrmwfUUNK2w6gW3mscMmmtnqHFqnb4xbgFLhFvoUgZTkT5iiMnJdJMnrc) | 0.99 |
| [4bGboPxr](https://gmgn.ai/sol/token/4bGboPxrAvEFWeWPAdKNShbfYAxmQHbUAVhrMkmopump) | [p6nRFL5a](https://solscan.io/tx/p6nRFL5antwqWVMzbSsin767N1wsWMTjNk2Yn6b4eSdEA7rR7bM4yDfstY9Zh5rRBr5sXMBsi7sthtqk29jsm3q) | 0.95 |
| [9rdw2ukP](https://gmgn.ai/sol/token/9rdw2ukP4gW5rQFS1RZrFdmpmB9tBFdngsYXP5NLpump) | [4zvEBf45](https://solscan.io/tx/4zvEBf45LAnVQ8UKNBaZSdR8ScjW6asPsXCXYVt6m4JMuR2629UpCZxhcigkVPxq5p8Sy9rhfLuv9GbYikM6Sv3Z) | 0.68 |
| [Dfp2Ag2n](https://gmgn.ai/sol/token/Dfp2Ag2n74JyqeyzHGgTQ32JvAApaSbqCo1HsYRFpump) | [2XCteFSs](https://solscan.io/tx/2XCteFSsRdtAe8hGo6MCLTSU8EEywSpgK3j7Km8JHV6NYZP53GeTTky8hhECvpYMui2h1uqPSxr6HPfa8Rr2VseM) | 0.66 |

### E. Exits

**MAIN-75 sold at slot 3**

| Token | Buy | Sell |
|---|---|---|
| [5uguBxBT](https://gmgn.ai/sol/token/5uguBxBT1gdNZDJEpA7iiLoP3BUnwDQkRkmh8Hnhpump) | [4vDTxbk4](https://solscan.io/tx/4vDTxbk4X3q9ciqF4vwx6zEXcvaVvKHVDP9ohz685ctFMAePm8pyxR98Q3AryJ2AA2hP7J9zmsCknqyWo1AMXL8u) | [2SXjQJCx](https://solscan.io/tx/2SXjQJCxHnLFAgPxkLWrzBmUt6Ry7ok1DyM6YSFpr4VQG2YkgYKRRcM7CEGrzwAGccnMewtPiHbT1ZrxooTRyf44) |
| [BAgTHtGA](https://gmgn.ai/sol/token/BAgTHtGAWadtrEzYA3YVa7y2LSsUoDuSf4CT9AQFpump) | [2VuiuSNk](https://solscan.io/tx/2VuiuSNkMRYGZW8xS3uH7LVZdq8iCEipHebsG7AsGA2Vx596vQLmbQRGL7J3EgLvYpaSEPNdfEhLvpuR8Qua6Y1U) | [5shPDmtz](https://solscan.io/tx/5shPDmtzfPUpRfwGnikyjX6xPUyoJwDRKvPqi7Q5EDbPiGTxiSAra1w8WeLpB3HycK2PzV4Njxf86QydyYhnZrCV) |
| [BeKBHfmo](https://gmgn.ai/sol/token/BeKBHfmoLUm6JdJzjHrBti3c5mWmEqEUh8fnCL54pump) | [oUyYLuPu](https://solscan.io/tx/oUyYLuPuaup5ms4JJwasA8bLPk6qMejSDHXepjvSUwboc5dRuAFEep41mJTCmQyN6mZUC8ghbD2sne1gHx7GsBj) | [5sUrGR1B](https://solscan.io/tx/5sUrGR1BKr3schXRY7k2XWqBfJsDWsAduobw9XF27QqqS7vxizaq4bFkjYUCBSeQYhA7jxsL5utbZC2JLfHWfFBF) |
| [ALdmcMyj](https://gmgn.ai/sol/token/ALdmcMyj32eN7f9oJsCwtSYmoC4NDHJbdngABqFFpump) | [2ha7TyXW](https://solscan.io/tx/2ha7TyXWtC8zLo1E3DNDcN5dDp92nis9DnLyP1Dp9dw128YQJTj7mXLm4FQCb4rG2K8F3RE8P4xjfYdW6gX5mdX9) | [2nzoamf4](https://solscan.io/tx/2nzoamf4f6QpW6pvyhexaAo9xaXdP2jY6vduZf9h4vT4qekXT9fS2ReF6oichfbFSdeP9hJhj15m9oYT8Q4jVj9x) |
| [2Z2w5Pzk](https://gmgn.ai/sol/token/2Z2w5PzknRY1hNkuUNsuJCU28m5hJ5ffzeZth8Bepump) | [58TeVnAy](https://solscan.io/tx/58TeVnAyjKFVVX2q3zrmjVFeiJF2FE9S3XyPhFzwdxt8CzFQyH6XereRK5XcYLwULD1XhCgDLny2ZBAPMTd9EJ61) | [2jd4jtir](https://solscan.io/tx/2jd4jtircT8KgBrgEt8MqMTPqkdcEeY4JrbfCcP5Jr1MQFFXPJq7NCd3H1bM1dBh2jrack9WWesGD1JuDgtX8qp6) |

**MAIN-75 sold at the 61-slot timeout**

| Token | Buy | Sell |
|---|---|---|
| [51FdvJDj](https://gmgn.ai/sol/token/51FdvJDjsHzhRc2cZCEdu2w8NewYbQwazp3L1KLFpump) | [47z2m77z](https://solscan.io/tx/47z2m77z5Wi34g5RdpVHgNBKkefthMR8tMs496icG74ZyLXfEymHZhXPngLyLvUaiU2CzqjjHfHF9hbPoTich6yM) | [2U8tYsoF](https://solscan.io/tx/2U8tYsoFv1cAXU59bFmvNTny4iqN2bNxd8PNKPgeQrHpda1RmwmSVbdUW9msHww99MHA5fM2etuzhvnAUCTuKN7g) |
| [8J53ZMQG](https://gmgn.ai/sol/token/8J53ZMQGV5GG6Y8aqZHZMwUeVnNwWJZ7pfNE8HJ3pump) | [3fApj1VG](https://solscan.io/tx/3fApj1VGskkTcsyTXNSKuSLB7XcowBjmLPiCmw1Be6prksShhcnA2ETC2mDYSwxNkiPZMH2Jk16YXcc8uy4Zn4Cr) | [V4bGdBpD](https://solscan.io/tx/V4bGdBpDXC1sLyg6B7jkwZqx4boC9AehtVCDpvAtffgdTNdKLcDjmVmKrJzkn4HvSkiH4guDarW4UBX5p7bMt5x) |
| [63BDRy38](https://gmgn.ai/sol/token/63BDRy38xxbVY4opPUunp4UfQhkaaGKRYGvgkk9Dpump) | [4dxkMy2K](https://solscan.io/tx/4dxkMy2KckqCR8hNVokJinQmkHvKezqyDaU5rrD4BUum9N2nvAAeH5HznD7gaP2PT5Cefm2RZpJUJxqGR1TkcZmk) | [Je1HoLEi](https://solscan.io/tx/Je1HoLEiHfHd3537gy6QfwLoJqEBWLFKUqgNR1KRZkgmMiVjBognMVakbEiqF1SpkGA8xPKMXMDGpjeqXuDzddi) |
| [68AhMNiF](https://gmgn.ai/sol/token/68AhMNiFwsqivgdhKQJ5tvZw5dng9RnE9qGTsPc1pump) | [5kzdvnpR](https://solscan.io/tx/5kzdvnpRUaJvt2MLUnj1kKzrYcNHpW3nrqrUjeVd6nT2MufLM1u5NhMAv8Vyz4NkdBK3MUd937vCdkkhFNqQm8is) | [3aBP8tmQ](https://solscan.io/tx/3aBP8tmQWa1dHKJD6ss7dRnhrFMVUyL59DrqcsYAC27FSQ1NotECPhWzQgu6g33St1udyKcWrDGSxsSoKYVrforz) |
| [Ez6LPmJZ](https://gmgn.ai/sol/token/Ez6LPmJZNDW5zwcBe3norHR2EJAdsDkdmcjvjEyopump) | [2rcAgN5H](https://solscan.io/tx/2rcAgN5HEcJg3SNqXcrLMYwVSZAH8aQXRV83JnoFxNsdT6NNMJjyL3nqgX67FzddtArB9q7bBbt2BjWfV8LvGpEk) | [5zH2hwXF](https://solscan.io/tx/5zH2hwXFw7W4uGcrNmCRBhSh6HBs9w8ABTZdcMSKn7gZAswy1nsmPZ1fhehWLRXoKz9XkZZmSybTqRp8HLguq7ZB) |

**TIMER6-50 (0.5 SOL), sold at 6 slots**

| Token | Buy | Sell |
|---|---|---|
| [nnXpxNiB](https://gmgn.ai/sol/token/nnXpxNiBqg2cn8fYwj6JVFFR6pZ98vyCQ3i2t62QXMg) | [4PA9JrRB](https://solscan.io/tx/4PA9JrRBdRGZQjHoJTiQHea1aCfQu2ieEj5AeLQ2c34b2U75UezpEz4nbp1XGNHBVAmJNkYnLHmggcsnSdUaAojz) | [6jDN4ecw](https://solscan.io/tx/6jDN4ecwDt4jKoGchFre1tV6SfTfWAD5q2fFC69d9E8prruKnY8Mj9mGGLkMxbKL68C3UmWvaF2v3NpVdoyXfHg) |
| [stughB58](https://gmgn.ai/sol/token/stughB58ux8NTVL5rtKHdo534FL3Fxnw6aJcHE8pump) | [4auHH8yn](https://solscan.io/tx/4auHH8yn5bsPVydGDQhEX1tRjFqmAy8h3Accm6n6E5KuwfyrkCYAY37A47SFWuSKCmra4zU7eyc8Mc6QLG2uUNbD) | [29cpT9yD](https://solscan.io/tx/29cpT9yD4meZZv3YMwdVSvm9QfHeBvqxSgzeAtdG3b5LbJQbycmcN2BdZEi4xQdrsNGSiJHVkeGSpjssH1n3KNTY) |
| [DWrZG5QN](https://gmgn.ai/sol/token/DWrZG5QNTDGF7EPzvYxYCdWXTJJJyH164iTJ525gpump) | [2WhGRpZ1](https://solscan.io/tx/2WhGRpZ1MZAhxcDNPz5fEMSL7Ydvz4XytXXnTp74dXp3rJQD71gecaAeThMKyHAdMXMDzbMbp7XwBbcs6Vk7xK6C) | [3oQbcwEc](https://solscan.io/tx/3oQbcwEcJaFDK4rLX21WXikXvHzbnqSnT6ckD4jUcgnBDbiG4Vpt7vY742GuU95Nba2xvLiDhcUVebD1WrV6oCpN) |
| [B9D3XKPB](https://gmgn.ai/sol/token/B9D3XKPBVCVHJ7tZrngQxUh4KWYBeWdr6uynSVsdpump) | [24qvxBbh](https://solscan.io/tx/24qvxBbhA94AGpnqjnP6mgc43QqADrCR4eRcG3or3AKbnL2SbagJ8aLXt3GH2wcEmEH6NkvrwMkgeDdHVkNVXL1H) | [5WRZdtUU](https://solscan.io/tx/5WRZdtUUHHStt3HB96mpJmwUYieEa9hnb9ay7sKvx6Avfnx9DcTQV8uu2YfkK6paduu49UbfZTAngYspMiRykE48) |
| [6PdkwLa3](https://gmgn.ai/sol/token/6PdkwLa3LqijWczg1TmJ8sZxyMLzaHmw7FDLEP4urGgf) | [4UDSEk56](https://solscan.io/tx/4UDSEk562rLmh8hPY7rsPXoLc5pr6u2cEvdKSnXkYsiyadj5gp3wV9N9PBC426J7Hhi6jkPK8sdyTrENacpqSCkq) | [2GjgpJDN](https://solscan.io/tx/2GjgpJDNaSJf4JVsSUcmW8hvFzYcZXsNxyM52XJ7JYdFicdRUhP2nMsJbdp7nbYQ8DQ9L1eCpNpVSyf8pEwiYuWz) |

**0.75 SOL size examples (spend 0.7594)**

| Token | Buy |
|---|---|
| [PvNStrme](https://gmgn.ai/sol/token/PvNStrmeAbKxcESEkarZkVwKdT77ggHGqP4hu5Jpump) | [2SzLMUtd](https://solscan.io/tx/2SzLMUtdRJnNW2mDn72THgP9Y5FbtqsAw3to66JH9UbwHCKeNSpTxjSHWDTLfncQH827ZBPCjKtppy4Vic7JXi7a) |
| [Q814ixzY](https://gmgn.ai/sol/token/Q814ixzYiEvfRbh4CK1zWSbLp5VqaH6ge9A4bwHpump) | [2SaeXen4](https://solscan.io/tx/2SaeXen4zYPfyjTmLo3XXSUU9buDzxAHLiZp6wzcFUkM7Nbyqkmhu9kjNCM9hrozKgay9atUpZKLAqg5V6qncei1) |
| [bLTBewq6](https://gmgn.ai/sol/token/bLTBewq68D49YC7kmnBpmFz8wK7DSELJuHRGkWRrDMv) | [Qu12vBcJ](https://solscan.io/tx/Qu12vBcJZSUtZAyLCUr8EruNTzZ5VsmWRDCEub4sMmYf26dURafgtZDaZYunRCQxoZXnZy44p3DCJkDEZdwXQk3) |

### F. Same dump, our fill vs its buy

| Token | Our fill (run, P&L) | Its buy (P&L, hold) | First |
|---|---|---|---|
| [DjCL2426](https://gmgn.ai/sol/token/DjCL2426vMgLB6qKPQV5TanErPpJidEJKxMh3koypump) | [2bj4qa6R](https://solscan.io/tx/2bj4qa6RGQsE5mwCQznBFhVQHDXg1eRJQcTdQ9qNZBcCCKgzXWiXET9gn2bAiAE1LF8KGbkyiUzaEYue1cXvUA4H) idx 153 (FRA r27, +0.351) | [3FwxHGjg](https://solscan.io/tx/3FwxHGjgLvaU4jPXKR3fa8ksm812oFrhjYzTFUERLJPxTwCmtcjCZuZZ21RV4FrSEx5zNkugA4yRZ1LitLX5V35y) idx 181 (+0.708, 3 slots) | us |
| [EJ5Bs2kK](https://gmgn.ai/sol/token/EJ5Bs2kKqWNSW3vst3V7FCoG43s2BW45gKwq1bFzpump) | [34sSGL4G](https://solscan.io/tx/34sSGL4Gint2TqKHnXEWbSuuaWckarbC2RhLBjJ6k59ZGVvaY8KJH69tz4WzjLSAdpNCcvtfZiRumJ24Rwntasv6) (+0.010) | [2PUPqJuu](https://solscan.io/tx/2PUPqJuuCXwubgVrjScLaEx8rqE9R2YHJkN6cXokygVzMr7B5KD2mBbEeB1z2z1A6yrAUCiKQZSj8S4wRnHjm4bZ) (−0.031) | us |
| [DoYybck8](https://gmgn.ai/sol/token/DoYybck8jzLLgBiGLD5oq7CU28LTKpG1oNA4gJnwpump) | [5KfrnBGD](https://solscan.io/tx/5KfrnBGD9PGcKYTbJL1g1Lod8UV2TvhqPNfBKFYeSNqkRzFs3x6eTszuyhncvianqJwXM47ofA1dxLhcSkxBgWMQ) (+0.028) | [5u4iTuFT](https://solscan.io/tx/5u4iTuFTRBZ8HWR6KYfY3XxEHrg55Aef48PvFcTujhxpsaWDgSmwPzMcFRssmEc17EDhwbMyE2rkp36f4gm2xZYa) (−0.049) | us |
| [69vWAawY](https://gmgn.ai/sol/token/69vWAawYPiuAycNvdRMqa59id9zctBQViRxXNJQupump) | [2Ty3fd6K](https://solscan.io/tx/2Ty3fd6KxX5E6b6KSg9x4eN99uvSRjUeP3hH7E1SFn8AJdn2xyqFca9vsPox5E2zBPYHnVj9KnH3TgTDxpnApgx) (+0.029) | [4MSLe1Zj](https://solscan.io/tx/4MSLe1ZjWZBUrrnETSJVN6BMysAG5a5EoTFRbNNJjGHsdyaD8EGcc3Cq2qcBTfmhEDSDJ9drBk7gNEB11RF7YH93) (+0.144) | us |
| [hareCzts](https://gmgn.ai/sol/token/hareCzts65Q9wMRoxKtkNn1iuRRJTmE9hSn1UDRpump) | [YMwceJDu](https://solscan.io/tx/YMwceJDuNPcsYL6qPgqG59D7PwaiVGm8VgQ9mj3STXQMBWVNQuqn1m1wSsWv2j8qGMvPwu5sDyZMNtrtai3w9un) (+0.021) | [2fPmxZgC](https://solscan.io/tx/2fPmxZgCQWrnX6iuVpjaCeK6ckU7hcfGQXnighfYic9KmwXh37w7N4rmC1njqC5eD6fZBqsmMLiL4YLwkqXk9iPY) (−0.006) | us |
| [H2q3QhbY](https://gmgn.ai/sol/token/H2q3QhbY9KZTDMUBTS8C3JQHRRxFmfQNspgFUw5Jpump) | [38q3TJ3d](https://solscan.io/tx/38q3TJ3dgWQWRdCDuyUHxhtGqxRczmstPMZsiQu22QCHYhDEneWSPRHCTErBt2TNnLE3UeSD3Xqge82xp7aDCbhJ) (+0.087) | [25sQUb21](https://solscan.io/tx/25sQUb21NXRgv58m5oeAhHA7eiyPaNu6UpTbhapsrqdcZNXtwg4ba2hjr9sFwZdgG8GqG9pTR2jrrCB5ADSKJ53V) (+0.343) | it |

Its failed attempts behind our fills:

| Token | Its attempt | Our fill | Failure |
|---|---|---|---|
| [H1xvejvb](https://gmgn.ai/sol/token/H1xvejvbsWNexJ2xq2SHqPSuAh6p5er8ZvRmNa5Kpump) | [2HPm59u6](https://solscan.io/tx/2HPm59u6NdqpwcmEWGBKLgCxNWysERvHgKFKWv9TZUekhznH7EP3FBvQ3wc4hb1V6T1CotTJdtT2nCceu5CeWcFv) | [5pSXb5dn](https://solscan.io/tx/5pSXb5dnewL5XPSV9NvHrUcfPuWWNoMhZrXh1TBvYewwXo95Mi1rADt7iCHdZs1vd4DHo1ZooZQSSAG3H2MZKseK) | price band |
| [HEwMEYbW](https://gmgn.ai/sol/token/HEwMEYbWfM6rQ4NVhYCk18LhywxefjsHbRuRHSj4pump) | [3LVYoUyW](https://solscan.io/tx/3LVYoUyWPMm5KTVMntSuxDqyH9iwodXHRP8esZqLubkeFtdeBULyaQGmcPV1uvxVkCvEXNNJHJH8YyhaunMNNQsX) | | slippage |
| [7jfRatD7](https://gmgn.ai/sol/token/7jfRatD7fHCcACfCRuXcayPUX1g3v8fHyRCHfAS6pump) | [DAppoJTh](https://solscan.io/tx/DAppoJThLvYmRYrejX4siTC7DLU6NkqDDqjdjRBPiZW4yP2HgPVCeuBqHFszTTF2mcMXzv6wWdmy7d6oBENu4sx) | | late |

More examples are in `x1.txt` and `o3.txt` in the data folder.

## 9. Files and caveats

| File | Contents |
|---|---|
| `r6.txt` | 24 h reconciliation |
| `r7.txt` | Whole-life ledger and boundary checks |
| `r8.txt` | Per-bot split |
| `a1.txt` | Claim checks |
| `a4.txt` | Landing and orders |
| `a5.txt` | Decoded instructions |
| `a6.txt` | Timing vs E2x1, haqq, us |
| `e1.txt`, `e2.txt`, `e3.txt` | Exits |
| `c1.txt` | Who buys after it |
| `s2.txt` | Take rates |
| `s3.txt` | Rules and GBDT |
| `s4.txt` | Speed |
| `c2.txt` | Model check |
| `c3.txt` | Delayed replay |
| `o2.txt`, `o3.txt` | Head-to-head |
| `w1.txt` | Pre-send widening |
| `x1.txt` | Examples |

Caveats:
- The paper results in §4 and §7 remove its own trades from the curve. Because they keep other traders' SOL amounts unchanged, they overstate its own result by about 11 %.
- The widening replay in §7b does not apply our live arm filters.
- AMS r35 fills are re-priced only up to 10-29 00:55, where the market tape ends.
- The recorder missed 141 of its txs; I fetched all of them from public RPC.
- To save disk I deleted two rebuildable files: `mtape.npy` (877 MB) and `uni.npz`. `run_all.sh` rebuilds them.
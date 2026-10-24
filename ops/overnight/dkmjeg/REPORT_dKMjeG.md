# dKMjeGJ4…2CTK ("dKMjeG"): full dissection

Read-only study, 2026-10-23. Nothing was sent, traded or changed on any server. Times are PKT (UTC+5). Every claim is labelled **MEASURED** (counted from chain data) or **INFERRED** (my reading of it). Wallet: [dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK](https://gmgn.ai/sol/address/dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK) · [Solscan](https://solscan.io/account/dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK).

**Data**
- **Full ledger** from the owner's RPC: every transaction it signed, failed ones too: 7,233 txs, slots 459,255,439 → 460,288,723 (10-20 19:00 → 10-23 08:24 PKT, 61 h). The RPC keeps no older history.
- **Older history** (signatures only, public RPC): 301,000 more signatures, back to 2025-09-26 PKT. Paging stopped there, and the wallet is older still.
- **Collector:** R1 (10-22 03:07 → 18:00 PKT) and R2 (10-22 20:43 → 10-23 05:35 PKT). This covers 36,423 launches, their exact block order, and our engine's arrival timeline (obs) for R2.

## Verdict

1. **Custom bot, not commercial (MEASURED).**
   - Every buy goes through its own on-chain router [ENFJAV…Dve8](https://solscan.io/account/ENFJAVp6hQWbzCbdRm69pUnuAmLgKPy18DiNg8fEDve8). The router's upgrade authority is the wallet itself, and the router was last deployed 10-14 17:36 PKT.
   - Its last 1,000 calls are all this wallet's.
   - It pays no bot fee: no AKbot-style 1% transfers.
2. **It wins the race with a ~20-way relay fan-out (MEASURED).**
   - **One buy, many signed copies.** Each buy is signed once per landing service: Jito, Helius, Nozomi, SpeedLanding, Bolt, Astralane, Flashblock, 0slot, bloXroute, NextBlock, Everstake, Stellium, Soyas, BlockRazor, Falcon, P2P/Syncro, plus plain priority-fee copies.
   - **A tag per service.** Each copy carries its own tip and a service tag in the last digits of the buy amount (Jito …042, Helius …108, Nozomi …168, SpeedLanding …178).
   - **Only one copy can execute.** INFERRED: all copies share one of 3 durable-nonce accounts. Evidence: every landed buy uses one of those 3 accounts, and only 1 launch in the whole ledger shows two landed buy txs.
   - **Jito wins most often** (386 of 1207 fills = 32%; 41% in R1+R2). That copy pays no priority fee, carries `jitodontfront`, and tips ≈ 3% of the buy.
   - **Landing cost** (tip + priority of filled buys): 102.1 SOL = 2.4% of the 4,257 SOL it bought with.
   - **Result in R1 + R2:** first outside buyer on 65% of its SOL-quoted fills, 66% of fills in the create block, median arrival 42 ms in our feed.
3. **Profit (ground truth, MEASURED).**
   - **Total:** +197.1 SOL after every cost over 61 h (+77.0 SOL/day).
   - **Not a thin tail:** without its best 10 tokens it is still +117.5 SOL. Win rate 42%, median token -0.046 SOL.
   - **Where the money is:** tokens it sold in 6+ pieces made +220 SOL; tokens sold in 1–2 pieces lost −30 SOL. By size, 8 SOL buys made +83 SOL and 1.8 SOL buys only +11 SOL (ROI +1%).
   - **Cash-outs:** 35 withdrawals of 5 SOL each, swapped to USDC (18,380 USDC), all to one wallet [HunS7E…HFLn](https://gmgn.ai/sol/address/HunS7Ek5kTnRNc6QYB76PeLw5zQ3X26sCyHTYV91HFLn).
4. **Selection (MEASURED).** A logistic model on 27 public create-time features predicts its attempts out of sample (AUC 0.87 / 0.83). It is not a dev list.
   - It prefers: new deployers, a glued bundle, dev + bundle of 2–20 SOL, a website, and a creator who has not launched in the last ~15 min.
   - Its picks attract about 2× the generic buying of similar launches.
5. **Exits are time-driven, not price-driven (MEASURED timing; the rule is INFERRED).**
   - **First sell, median 1.7 s after the buy (slot 8):** usually half the position, or all of it at ~2 s when follow-on buying is weak.
   - **Big buys (5–8 SOL):** 30% is sold already ~0.4 s in, at ×1.24.
   - **Then:** pieces at ~4, ~6, ~9 and ~12 s. Median hold 4.7 s.
   - **What does and doesn't trigger a sell:** new highs and drops below entry do not change its sell rate. A dev/bundle sell raises it ~1.9×.
   - **Unlike AKbot (DGmspi):** no take-profit steps, no stop, no 60 s timeout.
6. **For us: rejected (MEASURED).** All three copy ideas lose money once the fast snipers' buys after our entry are removed: its picks, a walk-forward list of its deployers, and a model of its picks.
   - **The three ideas** (0.5 SOL, 75 ms, 1% guard, sell at the end of the next slot) made +2.0 to +6.2 SOL in R2.
   - **Without the fast snipers' buys after our entry** (374 wallets, dKMjeG among them) every one is negative: −1.1 to −3.7 SOL at 75 ms, −1.6 to −4.5 SOL at 45 ms.
   - **Only 5–8% of the copy fills** (14–36% for the model) have no outside buy before our sell.
   - **Front-running it:** its own buy, landing after ours, carries almost all of the oracle profit on the launches where it does.
   - **What is generic and reusable:** the shared-nonce multi-relay send design (send-path change, needs the owner's OK), its selection features, and a 5–15 s exit window that matches generic net buying.

## Earlier claims, checked

| claim (source) | now (MEASURED) |
|---|---|
| +99.8 SOL/day (10-19 study) | +77.0 SOL/day over 61 h (+31 / +97 / +50 / +19 by PKT day, first and last partial) |
| 8.4 buys/h | 19.7 buys/h: a cheaper 1.8 SOL tier was added on 10-21 |
| size 4.94 or 7.90 SOL | exactly so on 10-20 (5 / 8 SOL spend); since 10-21 also 1.8, 3.6, 4.2, 6, 7, 12 SOL |
| tip 0.10/0.20 SOL via Helius Sender | its Helius copy tips 0.003 SOL, or 0.1–0.2 SOL on big buys (tag …117). Most fills now land through the Jito copy (≈ 3% of size) |
| median position +51 txs, 80% in the create slot | 66% in the create slot, median 0 outside buys ahead (R1+R2) |
| exit 30% at ~1 s (×1.21), then ~15% every ~3 s, out by ~18 s | on 5–8 SOL buys: 30% at ~0.4 s (×1.24), then pieces at ~4/6/9/12 s; p90 hold ~18 s; 1.8 SOL buys sell half or all at ~2 s |
| collector windows: 492 snipes, +45.39 SOL | ledger, same launch windows: +59.5 SOL incl. non-SOL-quoted tokens and all failed copies; SOL-quoted only +53.6 |
| usually first outside buyer, ~2 sells within ~4 s | 65% first; 2–3 sells, median hold 4.7 s |
| fee+tip ~1.1% of size | landing cost (tip + priority) 2.4% of the SOL bought (median buy 0.7%; Jito copies ~3%) |
| 189 failed-only attempts cost 4.14 SOL | R1+R2: 246 never-filled launches cost 6.5 SOL; whole ledger 540 cost 15.3 SOL, plus 2.1 SOL of router soft-skips |
| its deployer list: +3.15 SOL at 75 ms (replay), −0.89 older run | +3.18 (R2) / +0.18 (R1, proxy). It is −1.76 once the fast snipers' buys after us are removed, so rejected |

## 1. Infrastructure and bot identity

**A buy, instruction by instruction (MEASURED)** — example [3b4zRdSj…](https://solscan.io/tx/3b4zRdSjAjay6chhwZNTVkvpcX6XkXdUGogcjNoTCx9rhPLsYSSxawZd8T96CGyAZk4YTFwsKxgWaxjsPtYB4UTa) (v1, 58,175 CU, single signer):
1. `advanceNonce` on a durable-nonce account. Three accounts rotate for all buys: [Bju2Fi…fVUX](https://solscan.io/account/Bju2FiJsyHn7z1a3Fctgeu2usvRfNGLrYAPhPsmNfVUX) (681), [Dhbne8…w8WX](https://solscan.io/account/Dhbne8fKWSUyib29JX7W3v5LPBFW62Wug7kqhA6zw8WX) (579), [5eQpzF…MPM6](https://solscan.io/account/5eQpzFYHKJVqsrN7GgVHALufdBJNgJkYE2ZBvtSsMPM6) (489).
   - The tx uses no recent blockhash, so it can be signed instantly and sent everywhere.
2. `createAccountWithSeed` for its Token-2022 token account (seed derived; rent 0.00204 SOL). This is the same trick as AKbot: no ATA program.
3. **Its own router** [ENFJAV…Dve8](https://solscan.io/account/ENFJAVp6hQWbzCbdRm69pUnuAmLgKPy18DiNg8fEDve8).
   - Data: 17 bytes = opcode `07` + u64 SOL to spend + u64 min tokens out.
   - It CPIs `initializeAccount3`, then pump.fun `BuyExactQuoteInV3` (discriminator `e1f7501ed5b38488`) with the same two numbers.
   - In 18 landed txs it returned success without buying, using ~990 CU (a built-in check). These soft-skips cost 2.10 SOL.
4. Tip transfer to the landing service of that copy.
   - **Jito copy:** no priority fee (fee = 5,000 lamports). 370 of its 413 landed Jito copies carry the `jitodontfront` account, which marks a tx that must be first in its bundle, so it cannot be sandwiched.
   - **Other copies:** a 0.003 SOL tip plus ~0.01 SOL priority. Big buys use a second, 0.1–0.35 SOL tip variant with its own tag.
- **v1 transactions:** fee set in the header, no compute-budget instructions, ~55k CU per buy (about half of ours, like 9Sh2fd).
- **Non-SOL-quoted launches** (USDC, PUMP, xStocks, …): v0 tx with compute budget. It swaps SOL → quote on Orca Whirlpool, Raydium CLMM or Meteora DLMM, then calls pump `BuyExactQuoteInV2`. It sells into the quote token and swaps back to SOL in a separate tx.
- **Sells:** v1 `advanceNonce` + pump `SellV3`. They use 16 other nonce accounts, never shared with buys.
   - Tip mix: astralane 1595, none 1560, jito 638, 0slot 223. Tips are 0.001 (Astralane) or 0.00011 SOL; median priority ~0.00014 SOL.
   - Sell-side landing cost in total: 2.37 SOL.
- **Rent recovery:** after selling it closes the token account (burning dust first) and gets the rent back.

**The fan-out, as seen from the copies that landed (MEASURED).**
- **Tag** = last 3 digits of the lamport amount it spends. Each service has its own fixed tag(s): a normal variant plus a big-tip variant for big buys.
- **landed / failed / skip:** landed = buy filled; failed = the copy that landed failed (slippage); skip = router soft-skip.

| route | landing service | txs | landed / failed / skip | tag(s) | tip (median) | priority (median) |
|---|---|---|---|---|---|---|
| pump direct | none | 477 | 173 / 304 / 0 | …010, …329, …029 | 0.0000 | 0.0100 |
| ENFJAV | jito | 413 | 386 / 20 / 7 | …042, …068, …417 | 0.0976 | 0.0000 |
| ENFJAV | speedlanding | 177 | 165 / 9 / 3 | …178, …377 | 0.0030 | 0.0100 |
| ENFJAV | helius | 129 | 126 / 2 / 1 | …108, …117 | 0.0030 | 0.0100 |
| ENFJAV | nozomi | 116 | 89 / 24 / 3 | …168, …367 | 0.0030 | 0.0100 |
| swap+pump (non-SOL quote) | none | 73 | 11 / 62 / 0 | – | 0.0000 | 0.0360 |
| ENFJAV | bolt | 64 | 60 / 2 / 2 | …128, …137 | 0.0030 | 0.0053 |
| ENFJAV | none | 47 | 38 / 8 / 1 | …085, …308, …497 | 0.0000 | 0.0708 |
| ENFJAV | astralane | 41 | 36 / 5 / 0 | …148, …157 | 0.0030 | 0.0100 |
| ENFJAV | flashblock | 39 | 20 / 19 / 0 | …208, …397 | 0.0030 | 0.0100 |
| ENFJAV | stellium | 29 | 19 / 10 / 0 | …228, …437 | 0.0030 | 0.0070 |
| swap+pump (non-SOL quote) | speedlanding | 26 | 18 / 8 / 0 | – | 0.0104 | 0.0392 |
| swap+pump (non-SOL quote) | bolt | 23 | 22 / 1 / 0 | – | 0.0103 | 0.0337 |
| ENFJAV | p2p_syncro_sender | 22 | 12 / 10 / 0 | …268, …277 | 0.0030 | 0.0100 |
| ENFJAV | everstake | 15 | 7 / 8 / 0 | …258, …467 | 0.0030 | 0.0100 |
| ENFJAV | blockrazor | 10 | 4 / 6 / 0 | …248, …457 | 0.0030 | 0.0001 |
| ENFJAV | soyas | 9 | 6 / 3 / 0 | …188, …387 | 0.0030 | 0.0500 |
| ENFJAV | bloxroute | 7 | 2 / 5 / 0 | …198, …338, …347 | 0.0030 | 0.0100 |

- **One copy per decision (MEASURED).** Of all launches it touched, only 1 shows two landed buy txs: two failed attempts in consecutive slots on the same nonce. That fits shared-nonce copies; the copies that did not land leave no trace.
- **Who usually lands (MEASURED).**
  - **Jito copy:** 32% of all fills (41% in R1+R2), and the best place. In R1+R2 it was the first outside buyer 71% of the time, at a median 53 ms in our feed.
  - **Helius and priority-only copies:** arrive earlier in our feed (27 ms) but rank first only 55–58% of the time.
  - **Plain no-tip copies** (direct pump call, ~0.01 SOL priority): 304 of their 477 landed txs failed (64%). They land when the tipped relays did not, i.e. when it is already late. INFERRED: Jito and most relays drop failing transactions.
  - **One unidentified service:** tip account SpWrza9E… (tags …308/…497), 7 landed buys.
- **Why buys fail (MEASURED):** BuySlippageBelowMinTokensOut 472, other 18, BondingCurveComplete 16, MintDoesNotMatchBondingCurve 6, AmountInAboveMaximum 4 (of 524).
   - Failed and skipped buys cost 15.26 SOL: fees of the failed copies (their tips are reverted), plus fees and tips of the soft-skips.
- **Its slippage limit (MEASURED; ≈ approximation of the curve state).** min_tokens_out allows an average fill of ~1.24× the fill it would get right after the dev's bundle (median; p25 1.18, p75 1.39).
   - That is a loose guard, far looser than our 1%. It fails only when 1–3 snipers have already pushed the price up 20–30%.
- **Third-party txs on its address (MEASURED).** 2434 txs by [DeFG8i…fe2S](https://gmgn.ai/sol/address/DeFG8i8zoJ3hN155nmvLq266ZVxWmNgRaTz5KQVHfe2S) reference its address; 2417 of them failed.
   - They go through program [F7hMV9…D62r](https://solscan.io/account/F7hMV94qDyUXuv5HirXYJhU59AjuPfJMFaZFbwzLD62r) (upgrade authority [3ct4z3…fh5J](https://solscan.io/account/3ct4z3q2XHEGTb4Noe3Wh5iySA8e5UZawUXkWAnkfh5J)).
   - They hit its tokens 2–16 slots after its buy.
   - INFERRED: a copy-trader that follows it, and nearly always fails (996 of the program's last 1,000 txs failed).

**Compared with 9Sh2fd (AKbot user):**

| | 9Sh2fd (AKbot) | dKMjeG |
|---|---|---|
| bot | commercial AKbot (router akbotssn…, 1% fee to AKbotZVF…) | own router ENFJAV (authority = itself), no bot fee |
| landing | one LandX tip per buy (~2% of size) + 0.0025–0.005 priority | ~20 copies, one per service; Jito copy wins most (tip ≈ 3% of size, no priority) |
| nonce | 1 durable-nonce account | 3 for buys (rotating), 16 for sells |
| tx | v1, createAccountWithSeed, ~50k CU | v1, createAccountWithSeed, ~55k CU (incl. router) |
| sizes | 1.78 / 2.96 SOL | 1.8 / 3.6 / 4.2 / 5 / 6 / 7 / 8 / 12 SOL (changes by day) |
| place | first outside buyer 42/43 | first outside buyer 65% (R1+R2) |

## 2. Profit (ground truth)

Method: every tx it signed in the window (failed ones too) is in `ledger.json`.
- **Value** = SOL + WSOL + quote tokens (USDC, PUMP, xStocks…). Quote tokens are valued at the SOL rate of its own nearest quote → SOL swap.
- **PnL per token** = every SOL change of every tx on that mint: buy, sells, failed copies, soft-skips, tips, fees, account rent and its refund.
- **Cross-check 1:** raw SOL flow plus the net quote tokens left = +198.17 -1.15 = +197.03 SOL (vs +197.06 from the per-tx valuation).
- **Cross-check 2 (no missing txs):** start balance plus every SOL change equals the balance after the last tx: 14.718 +11.253 = 25.971 vs 25.971.

- **Result (MEASURED): +197.06 SOL after all costs in 61 h = +77.0 SOL/day.**
  - 1,207 tokens bought (one buy each), 19.7 buys/h.
  - Best tokens: [91n7QU…](https://gmgn.ai/sol/token/91n7QUvuqzm6rdJBiqnZMmAU6bgCSdkgigB8nZkVpump) +25.59 SOL (8.0 SOL buy, 8 sells, [buy tx](https://solscan.io/tx/561fQ3tk4dqa9JbLe2kqB81pMzBRSycoiQFGoHFEwBDhUD2GMcNm6mj6kbydwCn7p2xpocEKevLG1dFMKxTDKres)); [CZeDLL…](https://gmgn.ai/sol/token/CZeDLLXqSU8MFzvpcHBYDzn7BinUNmTfnrENd8gjpump) +10.20 SOL (8.0 SOL buy, 6 sells, [buy tx](https://solscan.io/tx/3egPGyZQ5g4WTTSTDsJSg6CK6RZhQ3WgJDB6QV1eo5nC11tJxdBMG7zhpSC2ygzkmSg97NNei3waFGEGgaYWVTmM)); [O DOT](https://gmgn.ai/sol/token/DoLPaV8VqtSxtoHprtRxsSuWjWTUvYsgF1Fcbgshpump) +8.50 SOL (3.6 SOL buy, 4 sells, [buy tx](https://solscan.io/tx/2z77UGomh9QCv4jdjpZSFTAPq6dFMh2PSmUsrWPoihqxdMZH5JDz1f8KM64MrmFfccvUuAckd7gX3xVZe1trxXST)).
  - Spent 4,670 SOL in total, so ROI +4.2% of the SOL spent.
  - Win rate 42%, median token -0.046 SOL.
  - Best 5: +25.59, +10.20, +8.50, +8.20, +7.94. Worst 5: -3.08, -3.25, -3.45, -3.56, -3.90.
  - Without the best 2: +176.53. Without the best 10: +117.53.
- Launches it tried but never filled: 540 → -15.26 SOL (fees and tips of failed copies).

**Per day (PKT calendar days):**

| PKT day | trading PnL | tokens bought | buys | failed buys | SOL spent |
|---|---|---|---|---|---|
| 10-20 | +31.17 | 82 | 82 | 33 | 480 |
| 10-21 | +96.61 | 414 | 414 | 150 | 1660 |
| 10-22 | +50.38 | 519 | 519 | 250 | 1604 |
| 10-23 | +18.90 | 192 | 192 | 91 | 512 |

Days 10-20 (from 19:00) and 10-23 (to 08:24) are partial.

**By venue (MEASURED):**

| venue | tokens | PnL SOL | SOL spent | win | median |
|---|---|---|---|---|---|
| pump SOL-quoted | 1147 | +199.14 | 4358 | 42% | -0.046 |
| pump other-quote (xStocks etc.) | 36 | +8.25 | 202 | 47% | -0.008 |
| pump PUMP-quoted | 23 | +5.00 | 106 | 48% | -0.154 |
| pump USDC-quoted | 1 | -0.07 | 4 | 0% | -0.075 |

No AMM-pool trading of older tokens was found. Its AMM txs are only quote-token swaps.

**By size tier, SOL-quoted, spend incl. pump fee (MEASURED):**

| tier SOL | tokens | PnL | ROI | win |
|---|---|---|---|---|
| 1.8 | 558 | +11.09 | +1.1% | 40% |
| 2.1 | 7 | -0.03 | -0.2% | 29% |
| 3.6 | 88 | +24.61 | +7.8% | 45% |
| 4.2 | 52 | +25.59 | +11.7% | 46% |
| 5.0 | 228 | +22.94 | +2.0% | 41% |
| 6.0 | 11 | -3.51 | -5.3% | 27% |
| 7.0 | 12 | +13.98 | +16.7% | 58% |
| 8.0 | 143 | +83.04 | +7.3% | 45% |
| 12.0 | 4 | +4.87 | +10.2% | 25% |
| other | 44 | +16.55 | +7.5% | 55% |

**Costs (MEASURED, whole window):**
- **pump.fun fees** (protocol 0.95% + creator 0.30% per side): 110.2 SOL on SOL-quoted tokens.
- **Tips** (landed txs): 80.5 SOL (jito 58.8, helius 8.2, speedlanding 5.7, bolt 4.8, astralane 1.9, nozomi 0.3).
- **Priority** (landed txs): 26.1 SOL. **Base fees:** 0.04 SOL.
- **Failed txs** (their fees; failed tips are reverted): 13.17 SOL. **Router soft-skips:** 2.10 SOL.
- **Landing cost of filled buys** (tip + priority): 102.1 SOL = 2.4% of the 4,257 SOL it bought with.
  - It is ~3% on Jito copies (0.058 SOL on 1.8 SOL; 0.33 on 8 SOL).
  - Extremes: a 4.27 SOL Jito tip and a 3.5 SOL priority fee, both on 12 SOL buys.

**Cash flow (MEASURED).**
- **Deposits:** none in the window.
- **Withdrawals:** 35. Each one wraps 5 SOL, swaps it to USDC on Jupiter, and sends the USDC to [HunS7E…HFLn](https://gmgn.ai/sol/address/HunS7Ek5kTnRNc6QYB76PeLw5zQ3X26sCyHTYV91HFLn) (18,380 USDC, 174.2 SOL in total).
- **Balance now:** 25.90 SOL + 23.68 WSOL ≈ 50 SOL of working capital.
  - Its other 80 token accounts are dust left from sold tokens or airdropped spam tokens it never bought: no open positions.

**Check against the collector numbers (wallets.json), same launch windows:**

| window | ledger: tokens bought → PnL (all costs) | collector: snipes → PnL |
|---|---|---|
| R1 (10-22 03:07 → 18:00 PKT) | 276 → +12.75 | 245 → +7.19 |
| R2 (10-22 20:43 → 10-23 05:35 PKT) | 267 → +46.74 | 247 → +38.20 |

- **Why the ledger is higher:** it also counts non-SOL-quoted tokens and every failed copy.
- **SOL-quoted tokens only:** ledger R1 +8.53 / R2 +45.07 vs collector +7.19 / +38.20.
- **What this verifies:** the collector's +45.4 SOL is the right size, slightly low.

## 3. Funding and relations

- **Age (MEASURED).** At least 310,608 signatures. Paging the public RPC back stopped at 2025-09-26 PKT, and more history exists before that.
  - So its **first funder was not reached** in the time budget.
  - **Activity by week:** bursts in Sep–Oct 2025, Jan–Feb 2026, Apr–May 2026 and Jul 2026; quiet in Aug–Sep 2026; continuous since 2026-09-28 (~10–20k txs/week). Data: `sigs_old.json`.
- **Deposits in the 60 h ledger (MEASURED):** none. No SOL came in from anyone.
- **Withdrawals (MEASURED):** only to [HunS7Ek5kTnRNc6QYB76PeLw5zQ3X26sCyHTYV91HFLn](https://gmgn.ai/sol/address/HunS7Ek5kTnRNc6QYB76PeLw5zQ3X26sCyHTYV91HFLn), as USDC to its token account [DAQwcY…eTPVJ](https://solscan.io/account/DAQwcYDY8h6V4BFmbQsWDy2hrkVjMYzYLxUHjG3eTPVJ).
  - **What that account holds:** 58,424 USDC and 12.19 SOL.
  - **Who pays into it:** in the RPC window its USDC account was paid only by dKMjeG (35 txs, 18,380 USDC).
  - **It never signs.** The wallet itself had no signature in the window.
  - INFERRED: the owner's cold/treasury wallet.
- **Programs and accounts it controls (MEASURED):** router ENFJAV (upgrade authority = dKMjeG), 3 buy nonce accounts and 16 sell nonce accounts (nonce authority = dKMjeG).
- **Follower, not a sibling (INFERRED).** [DeFG8i…fe2S](https://gmgn.ai/sol/address/DeFG8i8zoJ3hN155nmvLq266ZVxWmNgRaTz5KQVHfe2S) uses program F7hMV9…D62r to act on its tokens 2–16 slots after its buys.
  - It almost always fails.
  - The program's authority is a different wallet, and there are no transfers between them.
- **No link to the AKbot cluster (MEASURED, window only).** No transfers with 5tzFki…, DKoJUt… or AKbotZ…
  - Its router is used by no other wallet.
  - Nothing else ties it to the AKbot wallets: they use AKbot's router, one LandX tip and a single nonce account.

## 4. Selection: what it tries vs skips

**Data.** All 25,248 non-mayhem launches of R1 + R2 with create-time features (`paper/table_dump.jsonl.gz`), plus walk-forward deployer history from our own data. An attempt is a landed buy or a failed buy of the wallet (collector rows).

- **Base rate (MEASURED):** 782 attempts (3.1%), 543 filled.
  - It never buys mayhem launches.
  - It was active in every hour of both windows (no downtime).
  - Not a dev list: ~420 deployers, the top one is ~4% of its buys.
- **Attempt rate by feature (MEASURED, univariate):**

| feature | attempt rate |
|---|---|
| dev + bundle SOL: < 0.5 / 2–3 / 3–5 / 5–8 / 8–12 / 12–20 / > 20 | 1.1% / 7.3% / 6.7% / 7.3% / 7.0% / 8.6% / 4.1% |
| glued bundle: none / 1 tx / 2 / 3+ | 1.6% / 7.7% / 5.4% / 5.9% |
| website: yes / no · Twitter: yes / no | 4.6% / 1.8% · 3.6% / 1.6% |
| creator's previous create was < 1 min / 1–5 / 5–15 / 15–60 / 60+ min ago | 0.4% / 1.1% / 1.6% / 4.4% / 4.7–5.0% |
| deployer new to our data / seen 1–20+ times before | 4.9% / 1.7–2.1% |
| deployer it attempted before: 0 / 1 / 2–4 / 5+ | 2.4% / 8.0% / 13.3% / 11.8% |
| creator reused a name / name is in a 60-min copy wave | 0.5% / 1.2–2.1% (vs 3.4–4.0%) |
| SOL-quoted / other quote | 3.9% / 1.3% |
| metadata host: ipfs.io / j7tracker / uxento / rapidlaunch / pinata etc. | 3.1% / 2.8% / 4.2% / 3.7% / 0–1.9% |
| image host now.myfilebase.com / twimg (tweet image) | 9.6% / 0.8% |
| create priority ≥ 1M µlamports | 12.3% |
| hour, creator age, funding size, description length, tips on the create | flat (AUC 0.47–0.53) |

- **Model (MEASURED).** Logistic regression on 27 create-time features.
  - Trained on R1 → R2: **AUC 0.87**. Trained on R2 → R1: AUC 0.83.
  - **Top-ranked R2 launches:** top 1% → 38% attempted (base 3.4%); top 10% → 19%, holding 56% of its attempts.
  - **Weights (standardized):** deployer's launches already seen in our window −1.3; deployer it attempted before +0.9; glued bundle present +0.7; minutes since the creator's last create +0.5; creator's older all-time creates +0.4; dev + bundle SOL +0.3; website +0.3.
  - INFERRED: it likes established creators who launch rarely and with money behind the launch, and skips serial spammers and name reruns.
  - INFERRED: the rest of the choice (AUC < 1) is likely off-chain checks of the socials.
- **Do its picks beat average? Yes, in demand (MEASURED).** Generic = not the creator or bundle, not one of the 374 fast snipers (§6), not dKMjeG. Mean SOL per launch:

| after the create | its picks: generic buy / net | similar launches it skipped (dev+bundle ≥ 2 SOL + website): buy / net | all skipped: buy / net |
|---|---|---|---|
| 0–1 s | 3.84 / +3.27 | 1.19 / +1.00 | 0.56 / +0.46 |
| 1–5 s | 8.17 / +4.92 | 4.12 / +2.78 | 1.78 / +1.18 |
| 5–15 s | 9.75 / +3.11 | 5.30 / +2.08 | 2.28 / +0.89 |
| 15–60 s | 13.22 / +0.38 | 7.73 / +0.43 | 3.37 / +0.21 |

  - INFERRED caveat: some of this "generic" buying reacts to its own big buy. Copy bots that are not fast, such as DeFG8i8z, count as generic here.
  - Net generic buying lasts ~15 s, then goes flat.
- **Size tier (MEASURED).** Public features explain little of the size.
  - Spearman correlation with its spend: own slot −0.23 (bigger buys land earlier), dev + bundle +0.08 (R2: +0.20), market cap after the bundle +0.08 (R2: +0.19), website +0.09 (R2: +0.20), deployer attempted before +0.06 (R2: +0.20).
  - The tier set changed by day (ledger, UTC days): only 5 and 8 SOL on 10-20; 1.8/5/8 on 10-21; 1.8/3.6/4.2/5/7/8 on 10-22; 1.8/3.6/4.2/7 on 10-23.
  - The 10-19 note ("4.94 or 7.90 SOL") matches 10-20 exactly; the cheaper tiers were added later.
  - INFERRED: the size is the bot's own confidence score, not market-cap sizing.

## 5. Entry and exits

**Entry (MEASURED, collector R1 + R2, 543 fills).**
- **Slot:** 66% land in the create block, 33% in the next one.
- **Outside buys ahead:** median 0. 65% are the first outside buyer; 29% have 1–3 ahead.
- **Price:** the price just before its buy is median 1.00× the post-bundle price (p75 1.10, p90 1.21). Its own average fill is 1.11× because of its own size.
- **Arrival in our engine's feed:** median 42 ms after the create (p25 21, p75 131; n = 194, R2). We land at ~75 ms.
- **Sizes** (spend incl. pump fee, ledger, SOL-quoted): 1.8 SOL (558 tokens), 5 (228), 8 (143), 3.6 (88), 4.2 (52), plus 7, 6, 12 and 2.1.
- **Failed-only launches (239):**
  - when: 137 in the create block, 97 in the next;
  - the price before its failed tx was median 1.30× the post-bundle price (p25 1.15);
  - 1–3 outside buys landed first;
  - reason: BuySlippageBelowMinTokensOut.

**Place by the landing service of the copy that landed (MEASURED, R1 + R2):**

| service | buys | first outside buyer | in create block | outside buys ahead (median) | arrival ms (median, n) |
|---|---|---|---|---|---|
| jito | 222 | 71% | 59% | 0 | 52.8 (103) |
| none (priority only) | 92 | 55% | 77% | 0 | 26.9 (41) |
| speedlanding | 69 | 48% | 57% | 0 | 70.8 (7) |
| bolt | 49 | 27% | 55% | 1 | 157.9 (15) |
| helius | 45 | 58% | 84% | 0 | 27.4 (14) |
| nozomi | 30 | 47% | 80% | 0 | 50.1 (5) |
| astralane | 19 | 53% | 89% | 0 | 34.5 (4) |
| flashblock | 5 | 20% | 40% | 1 | 59.7 (3) |
| soyas | 3 | 33% | 67% | 1 | - |
| p2p_syncro_sender | 3 | 67% | 33% | 0 | - |
| 0slot | 2 | 50% | 50% | 0.5 | 50.2 (1) |
| bloxroute | 1 | 0% | 0% | 2 | - |
| stellium | 1 | 100% | 100% | 0 | - |
| blockrazor | 1 | 0% | 0% | 1 | - |
| everstake | 1 | 100% | 100% | 0 | 8.2 (1) |

**Exits (MEASURED, ledger, SOL-quoted tokens).**
- **Sells per token:** 1: 202, 2: 293, 3: 320, 4: 106, 5: 47, 6: 54, 7: 30, 8: 73, 9: 15, 10: 5, 11: 1, 12: 1.
- **Hold, buy → last sell:** median 22 slots ≈ 4.7 s (p75 9.8 s, p90 17.6 s).

| sell # | n | slots after buy, p25/med/p75 | share of the position, median | price × its entry, p25/med/p75 |
|---|---|---|---|---|
| 1 | 1147 | 3/8/11 | 50% | 1.00/1.07/1.22 |
| 2 | 945 | 14/19/22 | 25% | 0.92/1.02/1.21 |
| 3 | 652 | 21/30/34 | 16% | 0.89/0.99/1.20 |
| 4 | 332 | 36/44/53 | 14% | 0.87/1.00/1.27 |
| 5 | 226 | 52/55/66 | 11% | 0.86/0.99/1.25 |

| first sell | tokens | PnL SOL | first-sell slot (median) | price × entry (median) | typical size |
|---|---|---|---|---|---|
| other | 455 | +25.29 | 8 | 1.08 | 2.1 |
| 50% | 249 | +44.83 | 11 | 1.06 | 1.8 |
| 100% | 202 | -19.62 | 9 | 1.00 | 1.8 |
| 30% | 198 | +177.67 | 2 | 1.24 | 5.0 |
| 15% | 43 | -29.02 | 15 | 0.98 | 5.0 |

| sells per token | tokens | PnL SOL | win |
|---|---|---|---|
| 1 | 202 | -19.62 | 24% |
| 2 | 293 | -10.55 | 41% |
| 3 | 320 | +14.54 | 43% |
| 4–5 | 153 | -5.40 | 44% |
| 6+ | 179 | +220.18 | 60% |

**What triggers a sell (MEASURED).** Per-slot sell rate in the 40 slots after its buy (R1 + R2, 482 tokens):
- **Dev or bundle sell** in that slot or the one before: **8.8%** per slot vs 4.6% otherwise, ≈ 1.9×.
- **Outside sell** in that slot: 7.1% vs 4.5%.
- **New price high:** 5.4% vs 5.0%. No effect, so no take-profit trigger.
- **Price below its entry:** 5.2% vs 4.9%. No effect, so no stop-loss.
- **Dump all vs half at ~2 s:** when it dumps everything at slot 7–12, other wallets had bought only 3 times / 0.97 SOL in the 8 slots after it. When it sells ~half instead, they had bought 5 times / 1.60 SOL.
- INFERRED rule: at ~2 s, exit all if follow-on demand is weak, else take ~half. On 5–12 SOL buys it takes 30% (or 15%) earlier and at a higher multiple. Then it sells pieces on a clock (~4, ~6, ~9, ~12 s).

**Compared with DGmspi's AKbot ladder** (`overnight/exits/EXIT_LADDER.md`):

| | DGmspi (AKbot preset) | dKMjeG |
|---|---|---|
| first sell | "lightning" 10–90% at 0–2 or 5–8 slots | ~50% at a median 8 slots (~1.7 s); all if weak flow; 30% at ~2 slots on 5–8 SOL buys |
| take-profit | steps at ×1.2–1.45, then every +15–25% | none (new highs do not change the sell rate) |
| stop | clear at ×0.86–0.89, or the dev's dump (71% same slot) | no price stop; dev/bundle sell raises sell rate ~1.9× |
| timeout | 60 s on its biggest config | none seen; out by 4.7 s median, p90 ~18 s |
| sells per token | 4.6 | 2–3 (median) |

## 6. Can we use it? (our mechanics, owner's rule)

**Our mechanics.**
- 0.5 SOL per buy, landing 75 ms after the create (45 ms after the planned upgrade).
- 1% price guard vs the post-bundle price: a failed buy costs 0.005 SOL.
- Sell everything at the end of the next slot.
- Replay: `core/rp.py`, block-order placement with failed-tx anchors (`place_bo2` + `read_failed`).
- Window: R2 launches with our engine's timeline, 10-22 22:10 → 10-23 05:35 PKT. Halves are shown as (first/second).

**Owner's rule (2026-10-23).** A strategy must make money from generic flow, not from landing just ahead of specific bots and selling into their buys. So every idea is re-scored four ways:
1. without the buys, after our entry, of all **374 fast sniper wallets**. Fast = ≥ 5 launches bought within 2 slots of the create and ≥ 50% of their launches; dKMjeG is one of them;
2. without the **top-10 most frequent buyers after us**;
3. with **follower slippage limits** (`rp.sim(..., slip=rp.load_slip())`: a follower our buy prices out fails). Snapshot of `core/slip_args.jsonl` from 08:20 PKT with 34,182 limits; that fetch was still running. To refresh: `python3 -I rescore.py > rescore.txt && python3 -I make_report.py && python3 -I make_summary.py && python3 -I render.py` in this folder;
4. by the **share of fills with no outside buy** between our buy and our sell.

| idea | land | fills / tries | replay SOL (halves) | + slip limits | no fast snipers | slip + no fast snipers | no top-10 buyers | no dKMjeG buy after us | fills with no outside buy before our sell |
|---|---|---|---|---|---|---|---|---|---|
| (a) oracle: its attempted launches | 45 ms | 121/276 | +10.12 (+5.47/+4.65) | +9.04 | **-3.29** (-1.54/-1.75) | -3.74 | +1.72 | +3.61 | 6% |
| (a) oracle: its attempted launches | 75 ms | 87/276 | +6.24 (+3.53/+2.71) | +5.31 | **-2.57** (-1.32/-1.26) | -3.03 | +0.39 | +1.94 | 8% |
| (b) walk-forward deployer list | 45 ms | 78/178 | +4.94 (+2.17/+2.77) | +3.58 | **-1.91** (-1.13/-0.78) | -2.40 | +1.96 | +3.72 | 5% |
| (b) walk-forward deployer list | 75 ms | 53/178 | +2.86 (+1.08/+1.78) | +1.76 | **-1.76** (-0.93/-0.82) | -2.20 | +1.09 | +2.20 | 8% |
| (b) list + quality gate | 45 ms | 74/170 | +4.81 (+2.07/+2.74) | +3.50 | **-1.80** (-1.03/-0.76) | -2.28 | +2.01 | +3.77 | 5% |
| (b) list + quality gate | 75 ms | 50/170 | +2.80 (+1.05/+1.75) | +1.74 | **-1.67** (-0.86/-0.81) | -2.11 | +1.12 | +2.22 | 8% |
| (m) model of its picks, top 2% | 45 ms | 69/155 | +4.37 (+2.04/+2.34) | +3.49 | **-1.59** (-0.69/-0.90) | -1.99 | +1.72 | +3.30 | 14% |
| (m) model of its picks, top 2% | 75 ms | 47/155 | +2.42 (+1.15/+1.27) | +1.67 | **-1.13** (-0.46/-0.67) | -1.50 | +0.79 | +1.89 | 21% |
| (m) model of its picks, top 5% | 45 ms | 193/389 | +5.24 (+1.99/+3.24) | +2.80 | **-4.48** (-2.71/-1.77) | -5.75 | +1.49 | +3.55 | 28% |
| (m) model of its picks, top 5% | 75 ms | 151/389 | +2.03 (+0.23/+1.80) | -0.09 | **-3.71** (-2.42/-1.29) | -4.87 | -0.23 | +1.20 | 36% |

- **Top-10 after-us buyers at 75 ms:** [67LwNG…RtQ7](https://gmgn.ai/sol/address/67LwNGrukVFFcA1XZQ9U8ddZGCBuPvPHgMxw81AeRtQ7), [9qz7cW…hWpw](https://gmgn.ai/sol/address/9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw), [AJ5snx…rRpr](https://gmgn.ai/sol/address/AJ5snxaH5Gdvxi6CRTwN7c7467eNjfwGAP2htaMSrRpr), [AMDEmV…rMXg](https://gmgn.ai/sol/address/AMDEmVocLtN5ji2gBY7BrmSHEyM5vt6TGszBbg4crMXg), [Ake3Lc…YRbr](https://gmgn.ai/sol/address/Ake3LcHTM8jUGNQVewyVnDtRiy9YNBGHegynCbxTYRbr), [Anubis…HF5w](https://gmgn.ai/sol/address/Anubis512ho5t7S6LNSwoxUWdeQmX2kf3RvZ8ApHHF5w), [CxyKYm…zph8](https://gmgn.ai/sol/address/CxyKYmQoaYLCds6puxSbWndk6ktqax8PwAeq8enRzph8), [DpBUrt…tffV](https://gmgn.ai/sol/address/DpBUrt6HsNvdPXV7eXGvfDZsUD9QLQZvYdno52YqtffV), [G9sQPg…j7ob](https://gmgn.ai/sol/address/G9sQPg9Eimkwe72w1xH1tPUc9RFNuK6Ufw5AyWy6j7ob), [dKMjeG…2CTK](https://gmgn.ai/sol/address/dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK). dKMjeG is one of them.
- **Label for every row: "rejected: depends on the 374 fast snipers"** (MEASURED). The ones it depends on most are the top-10 above.
  - Every idea is positive with them and negative without them (−1.1 to −4.5 SOL).
  - Removing just the 10 most frequent after-us buyers removes 60% to all of the profit.
  - Only 5–8% of the copy fills (14–36% for the model) have no outside buy before our sell.
  - **Slip limits** (followers our buy prices out fail) cut the replay further at 75 ms: oracle +6.24 → +5.31, list +2.86 → +1.76, model top 2% +2.42 → +1.67.
  - **With slip limits and no fast snipers:** -3.03 / -2.20 / -1.50.
- **Front-running dKMjeG itself (MEASURED, `copy_d.py`, 75 ms, oracle set, before fail fees).**
  - We fill on 83 of its launches. On 58 of them its own buy lands after ours: +4.41 SOL, but only **+0.29** with its trades removed.
  - Over all 83 fills: +7.19 with it vs +3.07 without it.
  - With our size at 1.8 SOL we would also price out 9–18 of its buys (`copy_f.py`).
  - This is exactly the "sell into the pro bot's own buy" pattern the owner rejects.
- **First-pass numbers** (from `core/allres.json`, R2 to 10-23 07:39 PKT, plus R1 with the older block-position proxy), for reference only.
  - **Oracle at 75 ms:** R2 +6.24, R1 +7.26.
  - **Walk-forward list at 75 ms:** R2 +3.18, R1 +0.18; with the gate R2 +3.12, R1 +0.57.
  - **Same list at 45 ms:** R2 +5.92, R1 +2.30.
  - **Model of its picks, top 2%** (trained R1 → tested R2): 75 ms +2.42, 45 ms +4.37.
  - **Reversed** (trained R2 → tested R1, proxy): top 2% at 75 ms −0.96, top 1% +0.28. Not robust even before the owner's rule.
  - **All launches** with the same mechanics: R2 -134.90 at 75 ms.
- **(c) Its size and exit on our entries (MEASURED, oracle set, R2 at 75 ms, before the fast-sniper removal):**
  - 0.5 SOL, eos1 (ours): +6.24 SOL (+3.53/+2.71), fills 83/272
  - 0.5 SOL, all at ~2 s (slot 9): +6.32 SOL (+4.40/+1.93), fills 83/272
  - 0.5 SOL, dK ladder 50%@2.1s 25%@3.8s rest@6.4s: +5.53 SOL (+3.87/+1.66), fills 83/272
  - 0.5 SOL, dK big-size ladder 30%@1.3s 25%@3.2s 25%@6.4s rest@12.7s: +6.20 SOL (+4.11/+2.10), fills 83/272
  - 0.5 SOL, hold ~4.5 s (its median last sell): +4.05 SOL (+2.81/+1.24), fills 83/272
  - 1.8 SOL, eos1 (ours): +22.91 SOL (+13.13/+9.78), fills 83/272
  - 1.8 SOL, dK ladder 50%@2.1s 25%@3.8s rest@6.4s: +18.94 SOL (+13.58/+5.36), fills 83/272
  - Its ladder does not beat our quick sell on our entries. Holding to its median ~4.5 s is worse.
  - Size 1.8 SOL scales the replay nearly 4×, but it is the same bot-dependent set.
- **A generic version (MEASURED, `gentry.py`).** Buy after the sniper burst (first trade after the create slot +1 or +2) on the launches its model would pick; exit at +2/+5/+15 s; remove the fast snipers.
  - Result: −4% to −6% per trade on its pick types, and −3% to −5% on all launches, even with all flow kept.
  - The generic demand on its picks is real (§4), but it arrives too early and too thin to pay a late entry.

**What we can learn from it (generic, INFERRED from the measurements above):**
1. **Send path.** One signed buy per landing service, all on the same durable nonce, each with its own tip and a tag in the amount.
   - It fans out to every relay at once and pays only for the copy that lands.
   - It also tells you which relay won.
   - This is a send-path change: not proposed for build without the owner's OK.
2. **Selection features that predict broad demand:**
   - a new deployer in our window, with an older creator history;
   - a glued bundle, and dev + bundle 2–20 SOL;
   - a website;
   - ≥ 15 min since the creator's last create;
   - not a reused name, not in a 60-min name wave.
   - These double the generic buying in the first 15 s vs similar launches.
3. **Exit timing.** Generic net buying is positive for ~15 s and flat after.
   - Its time-based pieces (~2/4/7/11 s), its dump-all on weak follow-on demand at ~2 s, and its partial reaction to dev sells fit that window.
   - Price-based take-profits add nothing in its data.
4. **No sizing by market cap.** Size correlates only weakly with market cap (≤ 0.2).

## Files (ops/overnight/dkmjeg/)

- **Fetch:** `rpc.py` (rate-limited CK client, URL never printed), `fetch.py` / `fetch_pub.py` (resumable tx cache `txc/`), `sigs.json`, `sigs_old.json`.
- **Parse:** `parse.py` → `rows.json`.
- **Ground truth:** `ledger_an.py` → `ledger.json`; `final.py` → `final.json`; `crosscheck.py`.
- **Infrastructure:** `infra.py`, `buy_args.json`, `svc_slip.py`, `enfjav_sigs.json`.
- **Collector side:** `coll.py` → `coll.json`; `exits.py` → `exits_rows.json`; `exit_trig.py`.
- **Selection:** `sel.py` / `sel2.py` → `sel_rows.json`; `gflow.py` → `gflow.json`.
- **Copyability:** `fast_snipers.py` → `fast_snipers.json` (374 wallets); `copy.py` → `copy_ab.json`, `copy_c.py`, `copy_d.py`, `copy_e.py`, `copy_f.py`, `rescore.py` → `rescore.json`, `gentry.py`.
- **Page:** `render.py` + `make_summary.py` → `dKMjeG_snipes.html`; `make_report.py` → this report.
- Every `.txt` file holds the printed output of the script with the same name.

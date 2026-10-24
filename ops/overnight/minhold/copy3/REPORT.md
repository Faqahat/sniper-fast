# Copying 3 minute-hold wallets (copy3)

10-24 ~22:30 PKT. Read-only: nothing was traded or sent, and no server was touched. MEASURED = counted from chain data or tapes; INFERRED = a reading of them. All times are PKT. The data is in out/ (summary.json, headline.txt, guard.txt).

## Verdict
1. **All three are real traders, not arbs or insiders (MEASURED).**
   - No buy and sell in the same tx, no flash loans, no atomic multi-venue arbitrage.
   - They don't create the tokens they buy, don't buy in the create slot and aren't in bundles.
   - They trade through retail terminals: Fsb6 uses GMGN and Padre, pXGQ uses a USDC app, 4vw54 uses Axiom.
2. **They make money on chain (MEASURED; native SOL + WSOL + USDC).**

   | Wallet | Curve PnL | Per day |
   |---|---|---|
   | Fsb6Ns75 | +109 SOL in 67 h | ≈ +39 |
   | pXGQ6J2z | +86 SOL in 63 h | ≈ +33 |
   | 4vw54BmA | +92 SOL in 63 h | ≈ +35 |

3. **Copying every first buy loses at our speed (MEASURED replay).**
   - At 75 ms: −6.1 SOL over 61 h at 1 SOL a copy, about −2.4 SOL/day. The conservative follower variant gives −11.3.
   - At 150 and 300 ms it loses more.
   - At 35 ms it is +8.9, but only because of curve-completion marks. Without them it is −5.0.
4. **Copy bots already race these wallets (MEASURED).**
   - 4vw54: 2–4 other buys carrying 8–9 SOL land before we can (35–75 ms). Our price is about 1.3x theirs.
   - pXGQ: one copy bot (2TZonxx5) follows 68% of its first buys. Two 3-SOL bots land 27–32 ms after it.
5. **One version stays positive: a tight price guard.** The guard level was looked at on all three runs, so this is not a clean out-of-sample result.
   - Rule: buy only if our fill is at most 2–5% above their fill; otherwise the buy fails for 0.0005 SOL. Sell 75 ms after their first sell.
   - Result: +9.4 to +9.8 SOL over 61 h at 1 SOL, about +3.7–3.9 SOL/day, positive on every run.
   - With the conservative follower drop: about +2.9 SOL/day.
   - It almost never fills on 4vw54, so in practice this means copying Fsb6 and pXGQ.
6. **Why it is not "go":**
   - The best 5 of 85 fills make +7.6 of the +9.6 SOL. The median fill is about 0.
   - A guard chosen on R2 only (+8%) gives just +2.3 on R3 and +0.1 on R1.
   - About 4–6 SOL/day at 1–2 SOL a copy, below the 10–20 SOL/day goal.
   - It needs their sells detected in real time too.

## Data notes
- **Run windows (PKT):**
  - R1: 10-22 03:07 → 18:00 (14.9 h)
  - R2: 10-22 20:43 → 10-23 18:31 (21.8 h)
  - R3: 10-23 19:26 → 10-24 19:26 (24 h)
- **Tapes:** 395 positions: Fsb6 198, pXGQ 95, 4vw54 102. No mayhem tokens. Only tokens launched inside the runs are covered.
- **Chain history:**
  - Fsb6: full, 3,997 txs.
  - pXGQ: full, 3,208 txs.
  - 4vw54: its address gets about 100 txs a second from other bots, mostly failing. It was not paged. Used instead: its 473 trades from the tapes plus its own 91 token-account txs, which include its PumpSwap sells after the curve completed.
- **pXGQ trades in USDC** (607 of 610 trades). Converted at ~103.9 USDC/SOL, implied by its own buys and sells.
- **Curve completion is at 115.0 SOL, not 110 (measured).** 11 tokens touched 110 SOL and came back, so a 110 cut-off would book wins that didn't happen.

## 1. Real-trader checks

| Check | Fsb6Ns75 | pXGQ6J2z | 4vw54BmA |
|---|---|---|---|
| Buy and sell in one tx | 0 | 0 | 0 |
| Flash-loan programs | 0 | 0 | 0 |
| Creator / create slot / bundle | 0 / 0 / 0 | 2 / 2 / 2 (its own launches) | 0 / 0 / 0 |
| Router | GMGN + Padre | USDC router 6Vo3245e + Jupiter | Axiom (program FLASHX8D) |
| Fee payer | itself | relayer FHpcNSe6 | itself |

- **Other venues (all one-way swaps, not arbitrage):**
  - Fsb6: about 62 curve trades on tokens priced in another token; the router swaps that token to SOL. Also 140 separate trades on AMMs after the curve completed, net −7.3 SOL.
  - pXGQ: swaps USDC to SOL through Jupiter in the same tx as the curve buy, and back on sells.
  - 4vw54: none.
- **Fees and tips:**
  - Fsb6: about 1% platform fee per side (GMGN 0.99%, Padre 1.02%). Mostly no tip; sometimes 0.001 SOL to Helius, Jito or Stellium. 575 failed txs cost it 0.011 SOL in total.
  - pXGQ: 0.45% USDC to KfHbT5Jr plus about 0.16% to the relayer. About 1.3% round-trip conversion cost.
  - 4vw54: 0.005 SOL fee plus a 0.01 SOL tip on every tx. The tip goes to rotating accounts that are not in our tip map. It uses a durable nonce plus Jito's don't-front marker, which is a setup for sending one tx through many routes.
- **Links to creators:**
  - Sampled 12 creators per wallet. None was funded by the wallet or by anyone the wallet transacts with, and no funder repeats.
  - The only direct SOL moves between wallets and creators are pump.fun fee-sharing payouts to holders.
  - Exception: pXGQ swapped funds with HRduFFnK, which launched 4 tokens. pXGQ bought one of them 8 s after launch (−0.24 SOL). pXGQ also launched 10 tokens itself and traded 2 of them (+1.1 SOL). That is 3 of its 95 positions; same owner is an inference.
- **Wash trading:** no token transfers between its own wallets. The top repeat followers are not funded by the wallets (for big bots only their oldest 3,000 txs could be checked).
- **Money in and out:**
  - Fsb6 sent 167.6 SOL out to Aza3Lv3T and received 42.9 SOL from 69SNcRC8 (which holds 333 SOL). Both look like custom ("vanity") addresses in pairs. Inference: the owner's own wallets.
  - pXGQ works in USDC and also buys gacha-style NFT packs with it.
  - 4vw54 went from 626 to 842 SOL during our window and now holds about 853 SOL. No withdrawals seen; where its funds come from is unknown.
- **Human or bot:** probably humans using terminals (inference). Each wallet stops for a long block every day: Fsb6 06–12, pXGQ 15–19, 4vw54 10–17.

## 2. Profiles

**Fsb6Ns75 buys dips on busy tokens.**
- Positions per day: R1 82, R2 44, R3 107. 361 tokens on chain; win rate 60%; average win +0.75, average loss −0.37 SOL.
- Best PKT hours: 04 (+25 SOL), 01 (+16). No trading 06–12.
- Entry:
  - Token about 82 s old, curve 41 SOL.
  - Price down 10% in the last 10 s and 45% below its peak; 54% of buys come right after a sell of 1 SOL or more.
  - Busy tokens: about 149 buyers before it.
  - First buy 1.76 SOL. 53% of tokens get one buy; when it adds, the next buy comes about 77 s later.
- Exit:
  - First sell after about 15 s (spread 2–83 s, so not a timer), selling 36% of its tokens.
  - It sells at 1.14x its entry and 0.97 of the peak, while others are still buying (+1.2 SOL net in the 10 s before).
  - Holds about 65 s.

**pXGQ6J2z buys first on quiet tokens ("quiet-token bait").**
- 228 tokens; win rate 69%; average win +0.66, average loss −0.25 SOL.
- Fixed size of 1.63–1.68 SOL.
- Entry: curve 34 SOL, last trade about 5 s before, almost no buying in the previous 10 s.
- Exit: first sell after 6 s (30% of its tokens) at 1.25x; it is almost never under water (MAE 1.01x).
- 100% of its first buys get followers within 1 slot (median 3.95 SOL).

**4vw54BmA buys momentum, adds more, holds through curve completion.**
- Entry: token about 20 s old, curve 47 SOL, price +64% in the last 60 s.
- Sizes 1.96 or 2.93 SOL; usually 3 buys per token.
- Exit: sells everything after about 81 s, once selling takes over (27 sells in the 10 s before). It sells at only 0.62 of the peak; best paper gain (MFE) is 2.05x.
- 11 of its 102 tokens completed the curve while it held them. Selling those on PumpSwap made +51 SOL real; the tape mark at the last curve price said +74.
- Copy crowd within 1 slot of its first buy: 16 buys and 12.6 SOL. About 106 failed copy txs land in the 2 slots after each first buy.

**Profit from followers.** Their own positions, replayed with other people's buys removed:

| Removed | Fsb6 | pXGQ | 4vw54 |
|---|---|---|---|
| Nothing | +90 | +52 | +54 |
| First slot of outside buys | +72 | +34 | +41 |
| First 5 s of outside buys | +53 | +28 | +23 |

Followers are 41–57% of their profit, but they stay profitable without them.

**Token picks.**
- What separates their picks from other tokens of the same age:
  - Fsb6: busy, dipped tokens.
  - 4vw54: hot tokens.
  - pXGQ: quiet tokens near the start of the curve.
- A look-alike filter built from their R2 picks matches 1,000–13,000 tokens a day, and those tokens are flat or fall afterwards. Simple tape features don't explain their picks.
- An X-post link is slightly more common in Fsb6 and 4vw54 picks.

## 3. Copy replay (first buy only)
- **Setup:**
  - Our buy goes after every trade within T ms of theirs, with our price impact included.
  - Costs: pump fee plus 0.0015 SOL per tx, on both buy and sell.
  - Exit: sell T ms after their first sell. Size 1 SOL. Totals cover 60.7 h.
- **Follower variants:**
  - "slip" drops follower buys whose own slippage limit fails at the new price (6,257 of 6,513 decoded).
  - "drop2" (conservative) drops every outside buy within 2 slots after us.

**Who is ahead of us at 75 ms (median):**
- Fsb6: 2 buys, 0.8 SOL, price +4%.
- pXGQ: 2 buys, 3.4 SOL, +19%.
- 4vw54: 4 buys, 9.1 SOL, +34%.
- The share of the first 5 s of follower SOL still landing after us: 76% (Fsb6), 42% (pXGQ), 65% (4vw54).
- The copy-trigger spam is counted: the spam txs that land show up on the tapes as buys ahead of us.

**Copy every first buy (slip, 1 SOL):**

| T | R2 | R3 | R1 | Total |
|---|---|---|---|---|
| 35 ms | +2.6 | +9.7 | −3.4 | +8.9 |
| 75 ms | −3.1 | +2.1 | −5.0 | −6.1 |
| 150 ms | −5.4 | −1.8 | −6.3 | −13.4 |
| 300 ms | −6.7 | −4.0 | −6.4 | −17.0 |

- Selling on their last sell is worse at every latency.
- 349 take-profit, stop-loss, time-limit and trailing rules were tested, choosing on R2. At 75 ms the best one gave +2.8 on R2, then −8.0 on R3 and −2.2 on R1.

**Copy with the price guard (75 ms):**

| Guard / variant | Fills | Total | PF | Max DD | Per day | R2 / R3 / R1 |
|---|---|---|---|---|---|---|
| 2%, slip | 85 of 394 | +9.4 | 2.6 | 1.4 | +3.7 | +2.1 / +5.0 / +2.3 |
| 5%, slip | 143 | +9.8 | 1.8 | 2.6 | +3.9 | +4.7 / +4.2 / +0.9 |
| 2%, drop2 | 85 | +7.3 | 2.0 | 1.7 | +2.9 | +1.4 / +4.0 / +1.9 |

- At 35 ms with a 2% guard: +14.1 (+5.6/day). At 2 SOL a copy (75 ms, 2%): +13.9 (+5.5/day).
- By wallet (75 ms, 2%): Fsb6 66 fills, +5.1; pXGQ 17 fills, +4.8; 4vw54 2 fills, −0.5.
- The exit matters: with the same guard, selling after 60 s gives +5.1, and selling on their last sell gives +0.2.
- The big winners are real: the wallets themselves made +2.7 to +4.2 SOL on those same tokens on chain.

**What would have to be true for copying to work:**
- A 2–5% guard on every copy.
- Skip 4vw54.
- Detect their sells live and land our sell within about 75 ms.
- Accept about 34 fills a day with a median of about 0, carried by a few runners.
- The copy bots must not get faster on Fsb6 and pXGQ.
- A live test needs the owner's explicit OK; none was run.

**Caveats:**
- R2 and R3 block sizes are an estimate (largest tx index seen + 1), so positions inside a slot read slightly late.
- Fsb6's tape PnL is 20% above its chain PnL because of the ~1% GMGN/Padre fee.
- pXGQ's SOL figures depend on the USDC rate.

## Files
Everything is in this folder; key numbers are in out/summary.json.
- **Copy replay:** a3_copy.py, then a3f_headline.py and a3e_guard.py for the main tables. Results in out/headline.txt and out/guard.txt.
- **Chain checks:** a1_parse.py, a4_chain.py, a4b_4vw.py, a9_direct.py. Results in out/chain_summary.txt, out/4vw_tokens.json, out/links.txt, out/direct_links.json.
- **Profiles and picks:** a6_profile.py, a5_followers.py, a7_folcf.py, a8_picks.py. Results in out/profile.txt, out/followers.json, out/folcf.json, out/picks.txt.

## 4. Own exits only (owner's question, 10-24 late): copy their first buy, never look at their sells
Script own_exit.py → out/own_exit.txt / own_exit.json. 332 own-exit rules (TP/SL/time up to 10 min, trailing, idle, follower flow, outside sells). B = 1 SOL, slip variant.
- **75 ms, no guard:**
  - 0 of 332 rules are positive on all 3 runs.
  - The median rule loses −5 to −7 SOL per run.
  - The best rule on R2 (+2.8) gives −8.0 on R3 and −2.2 on R1. The best on R3 gives −13.4 on R2.
- **75 ms + 5% price guard:** still 0 of 332 are positive on all runs for all wallets. Every pick loses on R1 (−3 to −5).
  - Only pXGQ alone has a rule that is barely positive everywhere: time600, +0.5 / +0.1 / +0.3 SOL.
- **35 ms:** still 0 of 332 are positive on all runs.
- **Holding minutes destroys copies** (75 ms, all 394 copies):

  | Hold | Total SOL | Median per copy | Share up |
  |---|---|---|---|
  | 20 s | −6.9 | −0.03 | 44% |
  | 1 min | −14.6 | −0.08 | 41% |
  | 2 min | −22.3 | −0.20 | 33% |
  | 5 min | −39.6 | −0.33 | 27% |
  | 10 min | −69.5 | −0.41 | 19% |

- **Reading:** their minute holds work for them because they buy first and cheaper, and their sell timing carries information. Copying their sell (mirror + guard) was the only version positive on every run; replacing it with our own exit loses.

## 5. Why copies lose although many buyers come (why_minus.py → out/why_minus.txt)
395 copies, 75 ms after their first buy. Per window after our fill, summed over all copies:

| Window | Others buy | Others sell | Net |
|---|---|---|---|
| 0–5 s | 2,658 SOL | 2,573 SOL | +85 |
| 5–30 s | 6,017 SOL | 5,876 SOL | +142 |
| 30–120 s | 12,273 SOL | 12,994 SOL | −721 |
| 2–10 min | 23,134 SOL | 25,132 SOL | −1,998 |

- **Buyers ≠ net buying.** Many buyers come (median 9 / 21 / 41 per token in the first three windows), but almost all the buy volume is matched by sells: fast bots buy and sell within seconds. The net inflow is only ~+0.2–0.4 SOL per token in the first 30 s, and selling wins after that.
- **Who sells:** mostly other bots. The copiers who got in before us sell 618 SOL in the first 5 s (into us and the followers). The wallet itself sells 120 SOL in that window.
- **We pay more than they do:** median +9% (Fsb6 +4%, pXGQ +19%, 4vw54 +35%), behind ~2 copiers holding 1.7 SOL (4vw54: 4 copiers, 9 SOL).
- **Price vs our entry (median):**

  | After | Price | Copies up |
  |---|---|---|
  | 5 s | 1.00x | 39% |
  | 30 s | 1.03x | 51% |
  | 1 min | 0.98x | |
  | 2 min | 0.85x | |
  | 5 min | 0.71x | 29% |

  The round trip costs ~2.8%.
- **The peak is there but hard to catch:** a median of 1.37x our price at ~49 s, but its timing varies so much that no fixed take-profit catches it reliably. The same peak is 1.62x against their price; that gap is their edge.

## 6. Speed needed: copy their first buy, sell on a short timer (speed_sweep.py → out/speed_sweep.txt; out/short_hold.txt)
1 SOL. Slip variant (followers whose slippage limit breaks are dropped). Fsb6 + pXGQ + 4vw54, 60.7 h. Figures are total SOL; the 0.5 s column also shows per-run results R2 / R3 / R1.

| Behind them | 0.5 s hold (R2 / R3 / R1) | 1 s hold | 2 s hold | 3 s hold |
|---|---|---|---|---|
| Next tx | +35.2 (+15.6 / +14.3 / +5.3) | +35.5 | +31.5 | +28.7 |
| 5 ms | +16.4 (+6.1 / +7.9 / +2.4) | +16.7 | +12.3 | +9.3 |
| 10 ms | +12.2 (+4.6 / +6.0 / +1.6) | +12.2 | +8.0 | +5.1 |
| 15 ms | +9.4 (+3.4 / +4.8 / +1.3) | +9.2 | +5.1 | +2.0 |
| 20 ms | +6.9 (+1.6 / +4.0 / +1.3) | +6.6 | +2.5 | −0.5 |
| 25 ms | +3.9 (+0.5 / +2.9 / +0.5) | +3.3 | −0.6 | −4.0 |
| 35 ms | −1.1 (−0.5 / +0.0 / −0.6) | −1.7 | −5.8 | −9.2 |
| End of their slot | −8.4 | −9.7 | −13.7 | −17.1 |
| 75 ms | −9.6 | −10.6 | −14.5 | −18.1 |

- **Rule:** copy positive needs landing ≤ ~20 ms behind their buy with a 0.5–1 s hold. Next tx ≈ +14 SOL/day; 10 ms ≈ +4.8/day; 20 ms ≈ +2.7/day.
- **Being in the same slot is not enough:** end-of-slot loses.
- **Holding longer than 1–2 s always hurts.**

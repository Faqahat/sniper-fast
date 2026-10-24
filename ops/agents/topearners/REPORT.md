# How the top dip earners send — independent agent report, 10-24 ~08:20 PKT

(Saved from the agent's final message; scripts in ./scripts/, intermediate data in ./work/ — 837 MB; read-only, no RPC.)

## Summary
1. **Who earns most (MEASURED, ~33 h, conservative FIFO dip P&L, fees included):** haqqiUUX +76.6 SOL, ssssswdk +63.9, 9pQQc1xy +63.4, sssssDdMN +55.0, DYXDDrZC +45.9, HkQ7hMjy +32.1, E2x1ewwX +25.6, BUkpShoE +24.8, omegoMAe +18.2, EMKY7r6U +17.4. All ten profitable in both recording runs and in 20-31 of 35 hours. The two "sssss" wallets are one operator (same tokens, often the same slot; +328 SOL together across all their trades).
2. **We are not slow vs most reactive bots (MEASURED):** on European leaders we land in the dump's own slot in 71% of fires (DYXD 72%, HkQ7 77%). In shared slots we are level with haqqi / DYXD / EMKY, ahead of sssss / 9pQQ / BUkp, ~11 positions behind HkQ7.
3. **What beats us is position inside the block:** on our fired dumps a buy passes the +5% guard ~90% of the time at 50 positions after the dump, 66% at 100, 44% at 150; our median is 143 positions and 39% of our buys land in the next slot → our ~31-35% fill rate. In our 42 failed buys ~95 SOL was bought ahead of us, half by dip bots.
4. **Fees, tips and relays barely change the order (MEASURED):** within a block the higher priority fee came first in only 52-64% of pairs (by leader software), the higher tip 50-62%. We already pay 3-5x the top bots' priority fee and 3-20x their tips. Switching relay inside one wallet moves it ~10-30 places. Exception: on Firedancer leaders haqqi's untipped direct sends land in the dump slot 79% of the time vs 9% via Helius.
5. **Extra copies do not help (MEASURED):** HkQ7, BUkp, haqqi sometimes send 2-6 txs per decision; the first copy lands no earlier (HkQ7 position 98 with copies, 90 without).
6. **How the top bots send (MEASURED):** one signer (the trading wallet itself); usually one relay tip per tx, chosen by leader software; tips 0-0.0011 SOL, 18-75% of buys untipped; priority fee 0.00006-0.0002 SOL; tight CU limits. HkQ7 uses the same guard program as us (`L2TEx…`) with the deadline in the dump's own slot, and fires only when the dump is on a European leader.
7. **A second group gets in earlier by PRE-SENDING (MEASURED):** nine wallets flood conditional buys onto fresh tokens right after a large buy (up to 190 txs per slot per token, each failing or doing nothing for ~5-25 millionths of a SOL); when the creator or early buyer dumps, one of the queued buys executes 7-46 positions after the dump. First in 34-56% of their races; +1.5 to +7.4 SOL each per 33 h.
8. **The biggest gap with the top earners is volume and cost, not speed (MEASURED):** they act on 120-700 dumps/hour vs our 14 (haqqi also bought after 40 of our 69 dumps); HkQ7 fills 35% of its decisions like us; a buy + sell costs them 0.15-0.3% of the position in fees and tips vs our 1.4-2.0%; they hold a median 9-109 slots and earn on the right tail (we ~2 slots); most accept fills up to +9-15% over the post-dump price (we +5%).

**Ranked recommendations**
1. One relay tip per tx at the level the top bots pay (0.0002-0.001 SOL); priority fee ~1.5-2M µL/CU; CU limit close to actual use; keep the same signed tx on the untipped staked path; direct / staked path for Firedancer leaders. Expected saving 0.0035-0.005 SOL per round trip ≈ +25-35% on current realized profit, no measurable loss of position (INFERRED).
2. Faster reaction will not reach the positions that fill reliably — only pre-sent conditional buys reach positions < 25. Test a cheap pre-sending window for predictable creator / early-buyer dumps in shadow first (strategy change, needs the owner's OK).
3. Scale the number of decisions at small size.
4. Widen the price limit to +10-15%: on our 61 fired dumps 2-2.5x the fills and +14-27% replay profit before costs (INFERRED; the replay overstates absolute profit ~2x).
5. Lengthen holds (outside the sending question but explains most of their edge).

**Checked and not mattering:** fee and tip levels, which relay, extra copies, separate fee payers (none use one), our software reaction (3 ms median), position vs profit per fill (flat at 2-3% from position 25 through the next slot). Durable nonces, lookup tables and tx size are not in the recordings (not measurable).

## 0. Method
- Data: decoded tapes phaseA_selfwd (10-22 20:43 → 10-23 18:33 PKT) and phaseA_r3day (10-23 19:26 → 10-24 06:27 PKT; 35 clock hours) + raw tx chunks incl. failed; 179,355 sells ≥ 1 SOL.
- Dip buy = a buy ≤ 5 slots after a ≥ 1 SOL sell by a different wallet on the same token. P&L FIFO per wallet and token incl. pump fees, the wallet's share of tx fees and tips, and the fees of its failed txs. Open positions: only mark-to-market losses count (conservative); cross-checked against each wallet's net SOL change.
- Leaders from leaders_book.json (epoch 1065, first run only); locations from leader_geo.json.

## 1. Top dip earners (MEASURED)
| Wallet | Dip P&L (cons.) | All txs net SOL | Dip buys | Avg size | Hours + | Run 1 / Run 2 | Day / night SOL/h (PKT) |
|---|---|---|---|---|---|---|---|
| haqqiUUX | +76.6 | +62.6* | 8,274 | 0.33 | 31/35 | +33.6 / +43.1 | 1.38 / 2.67 |
| ssssswdk | +63.9 | +152.2 | 11,779 | 0.30 | 30/35 | +38.4 / +26.6 | 1.56 / 2.03 |
| 9pQQc1xy | +63.4 | +116.4 | 6,954 | 0.57 | 26/34 | +31.1 / +33.7 | 2.34 / 1.56 |
| sssssDdMN | +55.0 | +175.9 | 2,774 | 1.03 | 26/35 | +44.7 / +11.1 | 1.31 / 1.77 |
| DYXDDrZC | +45.9 | +75.7 | 3,346 | 0.96 | 23/34 | +24.8 / +26.0 | 0.93 / 1.76 |
| HkQ7hMjy | +32.1 | +34.8 | 2,216 | 0.50 | 28/32 | +20.2 / +12.8 | 0.62 / 1.13 |
| E2x1ewwX | +25.6 | +61.6 | 946 | 0.27 | 29/35 | +17.0 / +9.2 | 0.66 / 0.81 |
| BUkpShoE | +24.8 | +114.7 | 2,975 | 0.88 | 26/35 | +14.2 / +12.2 | 0.90 / 0.67 |
| omegoMAe | +18.2 | +37.5 | 1,764 | 0.67 | 20/34 | +14.2 / +4.3 | 0.27 / 0.68 |
| EMKY7r6U | +17.4 | +23.2 | 4,996 | 0.25 | 20/35 | +8.0 / +10.6 | 0.24 / 0.70 |
| us (2g7r…) | +0.36 realized | +0.38 | 24 fills / 69 fires | 0.25-0.35 | ~5 h | — | — |
*haqqi's net SOL change is below its trade P&L because of unreclaimed token-account rent. Day = 09-21 PKT (13 covered hours), night = 21-09 (22 h). Pre-sending group (CZ77onJz, 9K5QgBKa, FNuoWSQc, FUru6V3L, A9KKBdLy, CVPz447t, 8g1w4PNC, 5ZKd8DNB, CatkiNiJ): +1.5 to +8.0 SOL each, ~+43 SOL together.

## 2. How they send (MEASURED from raw txs)
- **haqqi:** own program `haqqqMGN…` calling pump BuyExactQuoteInV3; 1.8-2.06M µL/CU, CU limit 58-76k, priority ~0.00012 SOL; one tip per tx — 58% Helius 0.0002, 27% untipped (Firedancer leaders 66% untipped; Harmonic 78% Helius); in ~9% of decisions 2-4 buys land in the same slot with the fee nudged so each signature differs (scale-in); 13% of buys fail (6042), failed-fee cost 0.06 SOL total. Its 0.002 SOL astralane / nozomi buys are a separate slow strategy (0.74 SOL, held ~9,000 slots).
- **sssss pair (one operator):** pump Buy directly, 1.0M µL/CU, CU 95-115k; 75% untipped, the rest Helius 0.00006; 21% / 58% of buys fail (6002).
- **9pQQ:** pump directly; every buy carries two tips (astralane 0.001 + Jito 0.0000175: one tx accepted by two relays); 1.5M µL/CU, CU 130k; 10% fail.
- **DYXD:** pump Buy directly; one tip 0.001-0.0011 rotating by leader software (speedlanding on 88-90% of Harmonic-leader buys, astralane on 61% of AgaveBam); 1.6M µL/CU, CU 115k; 30% fail. Also 41,245 failed sells on 17 tokens it never held (~7.8 SOL burned; looks like a bug, not its edge).
- **HkQ7:** via `L2TExMFK…` (our guard program); deadline = the dump's own slot (all 1,723 next-slot landings fail cheaply with 6001; in-slot fails 6400/6401 early check or 6002); CU limit = CU used; priority 0.00013 SOL; nozomi 0.001 on 69-76% of BAM/Harmonic-leader buys, untipped on 69% of Firedancer-leader buys, soyas or Helius on Jito leaders (earliest, median positions 50-55); 1-2 txs per decision; lands only in European-leader slots (1,623 of 1,634 in run 1); 71% of attempts fail at 0.00013 SOL each.
- **E2x1:** astralane 0.0011 or Helius (Helius on AgaveBam 94%), 1M µL/CU, CU 145k, ~1% fail.
- **BUkp:** 0.00021 tip via astralane / Helius / blockrazor / 0slot / Jito; 2-6 variant txs per decision, extras fail on chain (57% fail overall).
- **omego:** own program, no compute-budget ix, 85% untipped.
- **EMKY:** astralane 0.00005 on 86-96% of buys, 0.75-1.75M µL/CU, 39% fail.
- **Pre-sending group:** own programs that stop after ~700-2,000 CU (failing: FUru, CZ77, 9K5Q, FNuo, 8g1w; or no-op success: 2Xyi, 144k no-op txs at 5,000 lamports); A9KK / CVPz send plain pump buys with a tight price limit; 75k-260k txs per wallet per 33 h; window opens 0-15 slots after launch right after a ≥ 1 SOL buy; fills mostly right after the creator dumps (FUru 124 of 130) or after the window-opening buyer dumps (A9KK 61 of 68).
- **All:** one signer = fee payer.

## 3. Where they land (MEASURED)
- Same-slot share on European leaders: HkQ7 0.77, DYXD 0.72, BUkp 0.61, haqqi 0.60, EMKY 0.53, 9pQQ / omego 0.50, sssss 0.43-0.48, E2x1 0.46; us 0.71 (37/52). North American leaders 0.17-0.54 (haqqi highest); Asian 0.07-0.18; us 3 of 16 on NA + Asia.
- Median position after the dump (same-slot attempts): HkQ7 94 (76 for successful buys), DYXD 96, haqqi 105, EMKY 115, sssss 117-124, 9pQQ 124, BUkp / E2x1 137; us 143 (38 attempts); pre-senders 7-58.
- Head-to-head in our 61 races (earliest attempts incl. failed; they earlier / total): HkQ7 24/45, haqqi 17/42, DYXD 11/29, A9KK 19/23, CVPz 13/16, ssssswdk 3/23, 9pQQ 5/22.
- Profit per fill by landing position (top + pre-sending wallets pooled): < 25 +4.7%, 25-50 +2.9%, 50-100 +2.3%, 100-200 +2.6%, > 200 +1.7%, next slot +3.2%.
- Our timing chain: reaction 3.1 ms median (p90 6.9); writing all send paths ~0.1 ms; fire → our tx seen 37 ms median when in the dump slot, 144 ms in the next.
- Positions → ms (INFERRED, our 31 same-slot fires): ~1.5-3 positions per ms; HkQ7's 11-position lead ≈ 4-7 ms; reaching position 50 reliably needs ~15-30 ms less end to end.

## 4. Side by side with us
| Aspect | Top reactive bots | Us | Measured effect |
|---|---|---|---|
| Txs per decision | 1 (HkQ7 1-2, BUkp 2-6) | 1 signature to 3-5 paths | copies land no earlier |
| Tips | 1 per tx, 0-0.0011 SOL | 2-4 per tx, 0.002-0.004 SOL | tips decide order only 50-62% |
| Priority fee | 0.00006-0.0002 SOL | 0.0005 SOL | higher fee first only 52-64% |
| Firedancer leaders | direct / staked, no relay | a relay + the staked path | haqqi 0.79 same-slot direct vs 0.09 via Helius |
| Deadline | HkQ7: the dump's own slot | dump slot + 1 | next-slot fills earn +3.2% → +1 is fine |
| Price limit | fills up to +9-15% (HkQ7 +5%) | +5% | +10% → 2x fills, +14% replay profit |
| Failed-buy cost | 0.00002-0.0002 SOL | 0.0005 SOL | — |
| Buy + sell cost | 0.15-0.3% of position | 1.4-2.0% | ~1.2 percentage points per trade |
| Decisions / hour | 120-700 | 14 | profit scales with count |
| Median hold | 9-109 slots | 2 slots | their profit is the right tail (top 10% of trades +20-35%) |

## 6. Checked and not mattering / not measurable
Fee and tip escalation (we are already the highest payer); relay identity (±10-30 places within a wallet and leader type; no relay dominates except the Firedancer direct-path case); extra copies; fee payers / signers; our software latency; landing later vs profit per fill (being later mostly costs fills under a tight price limit, not profit per fill). Durable nonces, lookup tables, tx size: not in the recordings.

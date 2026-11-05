# 9pQQ case study 3, PHASE 1 (blind): token T3

Written before opening any earlier 9pQQ report, case study or memory file.

- Wallet: 9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN
- Token T3: CsGVEXJD7kebRoyJG4Hkt6SjDYZuwnAraC9hnAz5pump ("out of memes"). Created at slot 464801232, 2026-11-03 11:40:14 PKT. Normal CreateV2 launch, not mayhem. Creator EHGCR9gy.
- Source: local recorder run_20261102_1250. It covered the whole life of T3, from creation to slot +16342 (12:38 PKT). There are no recorder gaps in the active window (the only gaps are 4 skipped slots before creation). No public RPC was needed.
- Tape: 15,952 txs on T3. 2,569 of them are successful pump trades. 13,102 failed: spam from tejiF (7,059), 74NEdB (1,952) and others, mostly error 6001.
- Data: /home/moiz/sniper-data/rivals/9pQQ/cases3/ holds trades.json (decoded TradeEvents), trips.json, ctx.txt (every 9pQQ trade with its neighbours), t3_parsed.jsonl.gz and code/.
- Market cap (MC) is in SOL, computed from the event's virtual reserves (vsol/vtok × 1e6). The slot is shown as "+N", meaning N slots after creation.

## What 9pQQ did on T3

- **16 round trips, all closed, plus 1 failed buy.** It is never in more than one position on T3 at a time. The trades alternate strictly B,S,B,S. The same held on all 338 tokens it traded in the 3 h window.
- **Active only while the token was busy.** It traded from age +19 to +3372 slots (11:40:18 to 11:52:16 PKT, 12 min). In the next 150-slot bucket after its last sell, outside buying fell from about 30/bucket to 2/bucket, and 9pQQ never came back. The token then drifted from MC 52 to 31.
- **P&L (net of all fees, tips and the refunded ATA rent):** +0.9998 SOL. 8 trips won and 8 lost. Trip 1 alone made +1.047. The other 15 trips added up to **-0.047**. Median trip +0.009.
- **Sizes:** every buy is BuyExactQuoteInV3 with 0.691358 SOL to the curve. That costs 0.70273 SOL from the wallet (0.70122 after the 0.00151 ATA rent comes back in a later CloseAccount tx). Every sell is SellV3 of the whole bag.
- **Hold time:** 2 to 56 s (11 to 262 slots), median about 12 s.

### Per-trip table

Each row shows the last outside successful trade before 9pQQ's tx.

| # | buy PKT | buy slot/pos | entry MC | last outside trade before buy | sell slot/pos | last outside trade before sell | hold s (slots) | MC move at sell | hold hi/lo | net SOL |
|--|--|--|--|--|--|--|--|--|--|--|
| 1 | 11:40:18 | +19/398 | 48.5 | S 0.185 B7A4wo (pump), same slot -33 pos | +190/36 | S 1.195 sssssD (pump), same slot -14 pos | 37 (171) | +158.9% | +208.3/0.0% | +1.0474 |
| 2 | 11:41:40 | +397/102 | 149.6 | B 1.246 8PgC4n (pump), same slot -8 pos | +408/414 | S 0.747 46x7gJ (pump), same slot -15 pos | 2 (11) | -0.6% | +1.6/-0.6% | -0.0227 |
| 3 | 11:42:15 | +560/1 | 118.0 | B 1.956 kjcByy (terminal), prev slot | +597/4 | B 0.01 2ZcPMx, prev slot | 8 (37) | -2.7% | +0.9/-7.2% | -0.0372 |
| 4 | 11:42:33 | +646/24 | 105.8 | B 0.099 AEgTuy, prev slot | +661/8 | S 0.267 EVHyQo, prev slot | 3 (15) | +2.6% | +3.5/0.0% | -0.0014 |
| 5 | 11:42:51 | +728/279 | 104.2 | S 5.011 HNGC6P, same slot -235 pos | +744/62 | B 0.005 6EGAmV, prev slot | 3 (16) | +8.3% | +8.3/0.0% | +0.0376 |
| 6 | 11:43:36 | +939/11 | 207.6 | B 0.393 EMKY7r, prev slot | +1089/260 | B 0.107 CZqUKy, same slot -72 pos | 31 (150) | +28.1% | +28.1/-0.2% | +0.1721 |
| 7 | 11:44:12 | +1111/47 | 251.8 | B 0.988 4GCtzC, same slot -38 pos | +1142/55 | S 0.488 sssssw, prev slot | 6 (31) | -2.2% | +2.2/-10.2% | -0.0324 |
| 8 | 11:44:55 | +1314/155 | 210.9 | B 0.435 sssssw, same slot -17 pos | +1365/105 | S 0.011 ATi4gb, same slot -69 pos | 11 (51) | -5.5% | +4.9/-5.5% | -0.0562 |
| 9 | 11:45:11 | +1390/15 | 145.1 | S 4.312 AGqjiv, prev slot | +1510/178 | B 0.196 BVcDry, same slot -86 pos | 26 (120) | +23.4% | +27.8/-6.1% | +0.1401 |
| 10 | 11:45:50 | +1568/80 | 146.9 | B 0.132 BffUuV, same slot -58 pos | +1605/176 | B 0.054 FhNfLj, same slot -14 pos | 8 (37) | +12.0% | +13.2/-10.9% | +0.0627 |
| 11 | 11:46:16 | +1686/42 | 161.2 | B 0.127 C1q5U6, prev slot | +1859/286 | S 0.425 3qvuM3, same slot -22 pos | 37 (173) | +9.0% | +14.1/-2.3% | +0.0426 |
| 12 | 11:47:19 | +1978/210 | 190.3 | S 0.071 6Qt8a3, same slot -33 pos | +2114/76 | S 0.482 3qvuM3, same slot -12 pos | 29 (136) | +8.1% | +18.3/0.0% | +0.0366 |
| 13 | 11:48:22 | +2274/74 | 233.8 | B 1.59 8PgC4n, prev slot | +2536/318 | S 1.495 8PgC4n, same slot -6 pos | 56 (262) | -10.8% | +3.5/-12.0% | -0.0919 |
| 14 | 11:49:57 | +2721/96 | 171.5 | S 1.296 3coRw7, prev slot | +2769/142 | S 0.364 3qvuM3, same slot -88 pos | 11 (48) | +5.6% | +6.6/-2.5% | +0.0193 |
| 15 | 11:51:26 | +3140/5 | 101.7 | S 0.601 2UMRu7, prev slot | +3230/167 | S 0.048 AEzWaG, prev slot | 19 (90) | -16.4% | +0.0/-34.9% | -0.1302 |
| 16 | 11:52:03 | +3315/159 | 72.7 | B 0.491 ARnjeA, same slot -94 pos | +3372/222 | B 0.098 55JY6a (terminal), same slot -148 pos | 13 (57) | -24.7% | +0.0/-30.8% | -0.1866 |

Failed buy: slot +934, pos 144, pump error 6042 (most likely slippage). Slots +932 and +933 had no trades at all. Slot +934 opened with buys of 6.84 SOL (pos 0), 5.93 (pos 76) and 1.48 (pos 86), which moved MC from 147 to 215 before 9pQQ's tx, and its buy failed. It bought again 5 slots later at +939/11 (trip 6). This failure is clean evidence of an **in-slot reaction to a trade-driven price spike**: there was nothing in the previous slot to react to.

Full neighbour lists (up to 8 trades before and 6 after, within 3 slots) are in ctx.txt.

## Tx recipe

The recipe was identical on T3 and on all 338 tokens 9pQQ traded between 09:31 and 12:40 PKT (1,157 buys, 1,150 sells):

- **Compute-unit (CU) price:** 1,500,001 micro-lamports.
- **CU limit:** 130,000 for a buy (about 75k used), 80,000 for a sell (about 53k used).
- **Priority fee:** 0.000200001 SOL per buy, 0.000125001 SOL per sell.
- **Tips, paid in every tx:**
  - Astralane (astra4uej…): 0.001 SOL per buy, 0.0001 per sell.
  - Jito: 17,500 lamports to a rotating Jito tip account.
  - So every tx goes to both lanes. I found no token-specific lane variation in this window.
- **Instructions:** for a buy, create the ATA (when it doesn't already exist) + BuyExactQuoteInV3. For a sell, SellV3. ATAs are closed later in batched CloseAccount txs (1 to 7 accounts each).
- **Fixed cost per round trip** (outside pump fees): about 0.00146 SOL.

## What triggers the buys

These numbers come from a per-slot hazard over the 1,967 slots in which it was flat. The trigger window is the previous slot plus the same slot before 9pQQ's position.

- **16 of 16 buys came right after an outside trade.** None of 934 flat slots without an outside trade led to a buy. 8 buys landed in the same slot as an outside trade, 8 to 235 positions later (median about 38). The other 8 landed early in the next slot, at positions 5 to 96 (often 1 to 24): one-slot reaction to the previous slot's activity.
- **Bigger trades trigger it more, on either side.** Buy hazard by the largest outside trade in the window:

  | largest outside trade in the window | flat slots | buys | hazard |
  |--|--|--|--|
  | buy ≥ 1 SOL | 61 | 4 | 6.6% |
  | sell ≥ 1 SOL | 109 | 7 | 6.4% |
  | buy 0.3–1 SOL | 134 | 3 | 2.2% |
  | sell 0.3–1 SOL | 135 | 1 | 0.7% |
  | buy < 0.3 SOL | 346 | 1 | 0.3% |
  | sell < 0.3 SOL | 248 | 0 | 0% |
  | no trade | 934 | 0 | 0% |

  In 11 of 16 buys the largest outside trade in the window was ≥ 1 SOL.
- **Side of the trigger:**
  - Last outside trade before the buy: 9 buys, 7 sells. That matches the 57% buy share of all outside trades in the window, so there is no buy preference.
  - Net outside flow in the window was negative (a dip) before 10 buys and positive before 6.
- **It is not deterministic. It lets most big trades go.** About 170 flat slots had an outside trade ≥ 1 SOL in the window, and 9pQQ bought after only 11 of them. Examples:
  - Flat stretch +408→+560: 23 trades ≥ 1 SOL passed before it entered.
  - Flat stretch +1142→+1314: 16 passed, including a 6.04 SOL sell.
  - Flat stretch +2769→+3140: an 11-trade dump passed (4.06, 2.69, 3.78…) before it bought the tail of the dump.
- **No visible cooldown after a sell.** Flat gaps were 3 to 77 s; the shortest were 3 s and 5 s.
- **Re-entry:** 15 of 16 buys (94%) were re-entries on a token it had already traded. Entry MC ranged from 48 to 252, and it re-bought both after pumps (trip 6: MC +43% in the previous 10 slots) and in dumps (trip 15: -29% in 10 slots).
- **Age:** first buy at age 19 slots (about 4 s), MC 48.5. Across 334 tokens in the window, its first buy came at age ≥ 8 slots (minimum 8, median 32).

### P&L by what came before the buy

| what came before the buy | trips | total net SOL | won |
|--|--|--|--|
| Last outside trade a SELL | 7 | +1.151 (+0.104 without trip 1) | 6 of 7 |
| Last outside trade a BUY | 9 | -0.150 | 3 of 9 |
| Net flow negative (dip) | 10 | +1.144 (+0.097 without trip 1) | 6 of 10 |
| Net flow positive | 6 | -0.143 | 2 of 6 |

On T3, buying into selling made the money and buying after buying lost, but the samples are small.

## What triggers the sells

These numbers come from a per-slot hazard over 1,405 hold slots.

- **16 of 16 sells came right after an outside trade.** None of 469 hold slots without an outside trade led to a sell. 11 sells landed in the same slot as the trigger (6 to 148 positions later), 5 early in the next slot (positions 4 to 167).
- **Side of the trigger:** the last outside trade before the sell was a sell 10 times and a buy 6 times. Sell hazard by the largest outside trade in the window:

  | largest outside trade in the window | sell hazard |
  |--|--|
  | sell 0.3–1 SOL | 4.3% |
  | sell ≥ 1 SOL | 2.6% |
  | buy < 0.3 SOL | 1.5% |
  | buy ≥ 1 SOL | 1.4% |
  | sell < 0.3 SOL | 1.1% |
  | buy 0.3–1 SOL | 0% |
  | no trade | 0% |

  So it leans toward reacting to an outside sell, but any trade can fire it.
- **No take-profit or stop-loss.** Sell hazard was flat against return:

  | return since entry | sell hazard |
  |--|--|
  | < -5% | 1.9% |
  | -5% to 0% | 2.4% |
  | 0% to +5% | 1.7% |
  | +5% to +15% | 2.0% |
  | > +15% | 1.1% |

  It rode trip 15 down -35% and trip 16 down -31%, and let trip 1 run to +208%.
- **Minimum hold of about 11 slots.** No sell in the first 10 hold slots (0 of 119). Afterwards the hazard was roughly constant (1.3–2.5% per active slot), so it looks like a **trade-gated, memoryless exit**.
- **Max hold:** 56 s on T3. Across all tokens in the window, 61 of 1,145 holds ended at 590–601 s and the longest was 601 s, which points to a **600 s cap**.
- **Sells do not wait for buying to pause.** On this very busy token, the last outside buy before each sell was only 0 to 13 slots (≤ 2 s) earlier.
- **Recurring neighbours** (small samples):
  - 3qvuM3 (a 0.3–0.5 SOL trader) sold just before 3 of 9pQQ's sells: 20% hazard against a 1.7% base.
  - In several other cases 3qvuM3 or sssssw sold 2 to 4 positions just after 9pQQ.
  - This looks like a cohort of similar bots reacting to the same events.

## New on T3: a copy-trader of 9pQQ

8d1YSS1uVDWg6SdpGudUAMzHzp569ksrYFtvFzixMwgL bought 0.049 SOL:
- after 15 of 16 of 9pQQ's buys (all except trip 6);
- in the same slot (61 to 225 positions later) or in the next slot.

It sold almost exactly 14 slots after each 9pQQ sell (13 to 15 slots, in 14 of 15 cases). The size is tiny, so the economic effect is nil, but 9pQQ is being copied.

## 9pQQ across all tokens in the window (context)

- 09:31–12:40 PKT: 338 tokens traded, 1,145 closed trips.
- Net from buy and sell legs: +8.52 SOL, before about 1.3 SOL of ATA rent refunds.
- Win rate 40%, median trip -0.018, mean trip +0.0074.
- Positions on different tokens overlap freely (often 5 to 12 open at once). The one-position limit is per token.

## In my own words

9pQQ is an event-driven bot:
- **Buys:** it checks each outside trade on a token it watches (busy, age ≥ 8 slots) and sometimes buys a fixed 0.69 SOL. Bigger trades make a buy far more likely, buy or sell alike. It reacts in the same slot (tens of positions later) or at the top of the next slot.
- **Sells:** while holding, any outside trade (somewhat more often a sell) after a minimum of about 11 slots can trigger the sell of the whole bag. There is no take-profit or stop-loss, and the cap is 600 s.
- **Re-entry:** it re-enters the same token over and over while the token stays busy, and stops when trading dries up. It passes on most triggers. With only 16 trips I cannot tell what decides which triggers it takes; trip direction and price state didn't separate them.
- **Where the money came from:** almost all of the T3 profit was one early ride (age 19 slots to 190, MC 48→125). The other 15 trips roughly broke even (-0.047 SOL).

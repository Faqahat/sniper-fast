# 9pQQ case study — PHASE 1 (blind; written before reading any 9pQQ study file)

Wallet `9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN`. All times PKT (UTC+5), 2026-11-03 unless noted.

- **T1** `D2496au7NBgTdd6AHA7kTEMgBc3K7BE9dGoqkkjKpump` ("0xUNKNOWN"), created 10:33:05, slot 464782356.
- **T2** `7aFTe3SqvpW1ogwo2ss8wecfQcofenEgy7cQvPDdpump` ("Ascend"), created 10-29 16:28 PKT, slot 462864189. It was dead, then came back this morning (11-03, 06:00–08:00) and was quiet after that.

## Data and coverage (measured)
- **T1:** the local recorder `run_20261102_1250` has every T1 trade from the launch to 12:10:15 (2,521 trades, 237 errored txs). The public RPC filled the tail: 9pQQ's last round trip (12:11:03 → 12:13:30).
- **T2:** the local recorders only track coins launched during their own run. They hold just 10 trades from the launch hour, and none of the 11-03 revival. Everything for T2 comes from the public RPC:
  - all 76 txs that touch 9pQQ's T2 token account (Token-2022 ATA `BiLcCTHfDaQMgUfsbNkkyNa6fXH6x4FGFsuU9dBoYcnz`);
  - every T2 tx in slots s−3..s+3 around each of his actions, with block positions from getBlock;
  - every tx inside 3 key holds (06:32–06:38, 07:15–07:25, 07:47–07:57).
  - So T2 trigger windows are complete. Hold-period stats for T2 are complete only for those 3 holds.
- **9pQQ on T2:** no trade on launch day (10-29). The first T2 trade is 11-03 06:00:35, at token age 109.5 h.
- **Counts:**
  - T1: 34 buys, 34 sells, 2 failed buys (error 6042 = slippage), 24 "CloseAccount" cleanup txs.
  - T2: 28 buys, 27 sells (the last buy, 12:09:32, was still open when the data was pulled), 0 failed, 21 cleanup txs.
  - The owner's "~27 buys+sells" undercounts: on-chain it is 28 + 27 on T2.
- **Files:**
  - per-action tables: `/home/it/sniper-data/rivals/9pQQ/cases/t1_actions.csv` and `t2_actions.csv`. Columns: time, slot, block index, SOL, MC after, curve real SOL, age, trades before (same slot / previous 3 slots), trades after (same slot / next 3 slots), hold, MC return, net P&L.
  - full T1 tape: `t1_tl.txt`; T2 windows: `t2_windows_tl.txt`.
  - scripts: `cases/scripts/`.

## Execution fingerprint (measured, identical on every tx, both tokens)
- **Buy:** `BuyExactQuoteInV3`, quote in = exactly **700,000,000 lamports including pump fees** (691,358,023 to the curve + 0.95% protocol fee + creator fee).
  - On top of that: tx fee 200,001, CU price **1,500,001**, CU limit 130,000.
  - Two tips: **1,000,000 lamports to an Astralane tip account** (`astra4uej…`) and **17,500 lamports to a Jito tip account**. Both tips are in every tx.
  - The ATA is created idempotently in the buy (rent 1,513,840).
- **Sell:** `SellV3` of the **full position**; the token amount equals the bought amount on 61 of 61 sells.
  - Tx fee 125,001, CU price 1,500,001, CU limit 80,000, Astralane tip 100,000, Jito tip 17,500.
- **Cleanup:** a separate batched tx closes the empty ATAs (and ATAs of other tokens) 5–20 s after the sells.
- **Programs:** no router or wrapper program; pump.fun is called directly. The only extras are ComputeBudget, System, ATA and Token-2022.
- **Positions:** exactly one position per token at a time: buy → full sell → (later) buy again. He does hold T1 and T2 at the same moment (11:54–12:00), so positions are per token, not one global position.

## Results
| token | trips | net P&L (after fees/tips, rent excluded) | wins | median hold | hold min–max | median MC return |
|---|---|---|---|---|---|---|
| T1 | 34 | **+1.479 SOL** | 19/34 | 64 s | 15–397 s | +6.4 % |
| T2 | 27 closed | **+1.453 SOL** | 13/27 | 74 s | 3–**600** s | −0.1 % |

Most of T2's profit is one trip: 06:05:48 → 06:08:03, MC 38.7 → 91.2, +0.99 SOL.

## What triggers his BUYS (measured counts; "trigger" = the last outside trade before his tx)
1. **Every buy with a full window (61/61: T1 33 + T2 28, plus both failed T1 buys; the T1 12:11 tail buy was not checked) lands right after an outside trade on the same token.** The trade is either earlier in the same slot or in the previous slot.
   - Base rate: on T1, only 12 % of slots have any outside trade in that slot or the one before.
   - On T1: 23 buys had the trigger in the same slot and 10 in the previous slot. Seven buys had a trade only in the same slot and nothing in the 3 slots before.
   - On T2: 16 of 28 buys were "same-slot only".
2. **He reacts inside the slot.** When the trigger is in the same slot, his tx lands a median 50 (T1) / 73 (T2) block positions after it. When the trigger is in the previous slot, he lands early in the next block (median index 57 / 80).
   - *Inference, not measured:* he probably reads shreds or another pre-confirmation feed, because a plain RPC/Geyser follower cannot be in the same slot.
3. **Mostly momentum: he buys behind an outside BUY.**
   - T1: 24/33 buys (12 of them behind a buy ≥ 0.5 SOL). T2: 23/28 (15 behind ≥ 0.5 SOL).
   - Typical triggers are 0.4–3 SOL buys, often sent through terminals: `term9`, `6Vo32`, `FLASH`, `GMgnV`, `JUP6L`, the 41Pr4 bot.
   - The rest come right after a big outside SELL (T1 9, T2 5), i.e. a dip-buy. Examples:
     - T1 10:34:05 after 5KcK −1.14; 11:39:05 after −3.03; 11:54:27 after 9H17 −3.89.
     - T2 06:15:19 after −3.48; 06:59:40 after −2.35.
4. **The momentum buys make the money; the dip buys lose.**
   - After an outside buy: T1 +1.564 SOL (14/24 wins), T2 +1.660 (11/22).
   - After an outside sell: T1 −0.120 (4/9), T2 −0.207 (2/5).
5. **He is very selective.** On T1, while flat, he let **90 outside buys ≥ 0.5 SOL and 56 sells ≥ 1 SOL pass** and acted on 32 triggers.
   - Taken and skipped triggers look the same on size (median 0.53 vs 0.98 SOL), time since his last exit and price vs his last exit (+2 % vs +4 %).
   - **Which triggers he takes is not explained by any simple size/side/price rule I could find.** It is probably a score or model, or a constraint outside this token.
6. **Token age does not matter.**
   - T1: first buy at age **10 slots**, right behind a 1.67 SOL sniper sell (HZxQ). He did not take part in the slot-0 launch block.
   - T2: entries at age 109–111 h, only once volume came back.

## What triggers his SELLS (measured)
1. **58 of 60 sells with a full window land right after an outside trade on the token**: same slot (T1 22, T2 15) or previous slot (T1 11, T2 10).
   - On T1, 21 sells had an outside trade *only* in the same slot and none in the 3 slots before, so this is in-slot reaction again.
2. **The 2 exceptions are a hold cap.** T2 07:15:15 → 07:25:15 and 07:47:44 → 07:57:44 are both **exactly 600 s**. No outside trade came in the 26 s / 212 s before them. Max hold on T1 is 397 s.
3. **The trigger is mostly an outside SELL** (T1 25/33, T2 20/25), of any size: from 0.03 SOL up to 4.8 SOL.
   - Some exits are into a large outside BUY: T1 11:00:57 after a 7.87 SOL buy, +29.6 %; 11:57:12 after a 6.45 SOL buy, +13.6 %. Others follow tiny buys of 0.001–0.1 SOL.
4. **No price rule (measured on all 34 T1 holds and the 3 complete T2 holds):**
   - There is no fixed take-profit, stop-loss or trailing stop. He often held through larger drawdowns than the one he finally sold on.
   - T2 06:32:50 → 06:38:52: he held while the MC fell **−61 %** (144 outside trades: ~42 SOL of sells, ~23 SOL of buys) and sold at −50 %, P&L −0.354 SOL.
   - Sell hazard per outside event on T1 (1,489 events, 33 sells):
     - by trigger side: 5.0 % on an outside sell vs 0.8 % on an outside buy;
     - by size: 14 % for events ≥ 3 SOL;
     - by buying pause: **7.3 % when the last outside buy was 10–30 s ago**, vs 0.5–1.5 % within 3 s of a buy;
     - by net flow over the last 10 slots: 5.4 % when it is −0.5..−2 SOL, vs 0.3–0.8 % when it is positive;
     - by hold time: **0 % in the first 15 s on T1** (on T2 he did sell after 3 s and 8 s, both into a dump).
   - In plain words: he exits on an outside sell, more readily once outside buying has paused, or when a big dump or big buy appears. It looks like a flow score, not a price level.
5. Profile: median MC return at exit +6 % (T1). He gives back a median ~5 points from the in-hold peak. The peak giveback on the big runs reached 46 points.

## Re-entry
- On T1, 33 of 34 buys are re-entries into a token he just exited; on T2, 27 of 28.
- Gap from own sell to next buy, T1 (slots): min 4, median ~160, max 2,327. One extra failed buy came just **2 slots** after a sell (10:41:17).
- T2 shortest gaps: 2 s (06:11:13 → 06:11:15), 3 s (06:05:45 → 06:05:48), 4 s (06:15:15 → 06:15:19). Several gaps are 6–30 s.
- He re-enters at a higher price than his own exit about as often as at a lower one (T1: 16 above, 16 below, range −20 % .. +30 %). So he does not wait for a pullback.
- The re-entry trigger is the same as any entry: an outside trade, mostly a buy.

## What he avoids (observed)
- He never buys in the creation slot or the first ~10 slots.
- He never pyramids: no second buy while holding.
- He never does partial sells.
- He never holds past 600 s.
- He never changes size (always 0.7 SOL including fees).
- He never sends a buy without a tip pair. No retries were seen beyond 2 slippage failures on T1. He uses tight slippage and fails rather than chases.
- He skips most large trades, including the launch-hour whale activity on T1 (10:33:44, 8GgR 3.34 SOL).

## T1: where 9pQQ was relative to OUR bot (EgxfY…)
- **Slots 464782537–540 (10:33:44–45):** our pre-sent buys fired: 26 failed txs (6042 slippage).
- **Slot 464782540, i=157:** 8GgR dumped 3.81 SOL.
- **Slot 464782540, i=173:** our buy landed at i=173, **in the dump slot, 16 positions after it**, 0.543 SOL at MC 42.96.
- **Slot 464782541, i=1:** the 41Pr4 bot 5KcK bought 1.68 SOL, then E2x1 bought 0.36.
- **Slot 464782541, i=85:** 9pQQ's buy landed **1 slot after the dump** and **failed on slippage**, because the price had already rebounded.
- **Slot 464782541, i=185:** we sold at MC 46.51 (+0.06 SOL gross).
- Conclusion on this dump: we were ~1 slot faster than 9pQQ. He did not trade T1 again until 10:34:05 (slot 464782634), a dip-buy after 5KcK sold 1.14.
- We did not trade T1 again. He went on to 34 round trips, +1.48 SOL, mostly behind outside buys.

## One-paragraph summary (my words)
9pQQ is a single-token, one-position-at-a-time flow trader with fixed size (0.7 SOL) and fixed execution (CU price 1,500,001, Astralane plus Jito tips). Every action reacts to an outside trade on the same token, mostly inside the same slot. He buys behind outside buys (momentum); dip-buys are rarer and lose. He sells into the next outside trade once flow turns: an outside sell, a pause in outside buying, or a very large print. There are no price stops, the cap is 600 s, and he re-enters repeatedly while the token stays active. Which of the many triggers he takes is selective, and these two tokens do not explain it.

## Trip tables
### T1
| # | buy time | slot/idx | age | buy mc | buy trigger | sell time | sell trigger | hold s | mc ret % | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 10:33:08 | 464782366/227 | 10 sl | 38.4 | HZxQ S 1.67 (Δslot 0, i174→227) | 10:33:36 | 5MD7 S 1.02 (Δslot 1, i293→7) | 28 | -9.9 | -0.0617 |
| – | 10:33:45 FAILED BUY (6042 slippage) | 464782541/85 | | | E2x1 B 0.36 (Δslot 0, i33→85) | | | | | |
| 2 | 10:34:05 | 464782634/95 | 278 sl | 43.4 | 5KcK S 1.14 (Δslot 0, i52→95) | 10:36:39 | J6YE S 0.41 (Δslot 1, i144→130) | 154 | -13.5 | -0.0892 |
| 3 | 10:36:42 | 464783376/665 | 1020 sl | 43.2 | 8aVt B 1.24 (Δslot 0, i621→665) | 10:37:45 | EMKY S 0.20 (Δslot 0, i137→233) | 63 | +6.8 | +0.0566 |
| 4 | 10:38:18 | 464783827/220 | 1471 sl | 53.1 | BUkp B 0.75 (Δslot 0, i126→220) | 10:39:34 | EMKY S 0.52 (Δslot 1, i218→105) | 76 | +19.6 | +0.1447 |
| 5 | 10:40:56 | 464784566/109 | 2210 sl | 68.2 | 4vgK B 1.78 (Δslot 0, i97→109) | 10:41:17 | 4vgK S 0.23 (Δslot 1, i486→30) | 21 | +13.9 | +0.1006 |
| – | 10:41:17 FAILED BUY (6042 slippage) | 464784663/192 | | | E2x1 B 0.99 (Δslot 0, i189→192) | | | | | |
| 6 | 10:41:34 | 464784737/268 | 2381 sl | 68.8 | ssss B 0.82 (Δslot 0, i231→268) | 10:42:30 | 47du S 0.03 (Δslot 0, i53→162) | 56 | -21.6 | -0.1508 |
| 7 | 10:42:39 | 464785044/270 | 2688 sl | 58.5 | ssss B 0.23 (Δslot 0, i248→270) | 10:43:45 | STor S 0.67 (Δslot 0, i80→88) | 66 | +6.4 | +0.0493 |
| 8 | 10:44:06 | 464785452/47 | 3096 sl | 64.9 | EyQg B 0.49 (Δslot 1, i47→47) | 10:46:43 | JDFD S 3.43 (Δslot 0, i190→222) | 157 | +31.6 | +0.2273 |
| 9 | 10:46:48 | 464786208/256 | 3852 sl | 71.3 | ERwF S 0.16 (Δslot 0, i242→256) | 10:47:21 | 9QLF B 0.11 (Δslot 0, i101→178) | 33 | +20.3 | +0.1456 |
| 10 | 10:48:03 | 464786565/233 | 4209 sl | 78.9 | GaBq B 0.30 (Δslot 1, i521→233) | 10:48:34 | ssss S 0.76 (Δslot 0, i165→169) | 31 | -9.1 | -0.0639 |
| 11 | 10:48:40 | 464786733/89 | 4377 sl | 73.3 | ssss B 0.25 (Δslot 0, i19→89) | 10:51:07 | BUkp S 0.80 (Δslot 1, i195→49) | 147 | -6.7 | -0.0460 |
| 12 | 10:51:12 | 464787443/69 | 0.3 h | 73.6 | ssss B 0.26 (Δslot 1, i197→69) | 10:55:03 | G4Nv S 1.67 (Δslot 1, i158→58) | 231 | -2.0 | -0.0127 |
| 13 | 10:55:38 | 464788689/136 | 0.4 h | 93.1 | 8aVt B 2.45 (Δslot 0, i111→136) | 10:55:53 | ARu4 S 0.34 (Δslot 0, i64→112) | 15 | -2.1 | -0.0160 |
| 14 | 10:57:39 | 464789258/63 | 0.4 h | 107.5 | 8aVt S 2.32 (Δslot 1, i242→63) | 10:58:06 | BbZG B 0.27 (Δslot 0, i20→70) | 27 | +8.6 | +0.0579 |
| 15 | 10:58:41 | 464789549/155 | 0.4 h | 122.9 | ssss B 0.33 (Δslot 0, i143→155) | 10:59:04 | 6F6w S 0.40 (Δslot 1, i327→67) | 23 | +1.0 | +0.0035 |
| 16 | 10:59:57 | 464789906/77 | 0.4 h | 160.6 | 8PgC B 1.30 (Δslot 0, i74→77) | 11:00:57 | J1Pz B 0.40 (Δslot 0, i184→234) | 60 | +29.6 | +0.2021 |
| 17 | 11:01:47 | 464790422/137 | 0.5 h | 170.6 | HcSY S 0.55 (Δslot 0, i7→137) | 11:02:04 | ssss S 0.44 (Δslot 0, i167→169) | 17 | +7.9 | +0.0491 |
| 18 | 11:03:37 | 464790943/141 | 0.5 h | 182.0 | 7aai B 1.98 (Δslot 0, i66→141) | 11:04:39 | GKd5 S 0.42 (Δslot 0, i229→241) | 62 | -5.1 | -0.0420 |
| 19 | 11:04:40 | 464791234/98 | 0.5 h | 170.3 | 4qqD B 1.07 (Δslot 0, i68→98) | 11:06:29 | ssss S 0.41 (Δslot 0, i571→609) | 109 | -2.0 | -0.0196 |
| 20 | 11:07:03 | 464791904/519 | 0.6 h | 176.7 | 9rjq B 2.15 (Δslot 0, i403→519) | 11:08:07 | 5pw5 S 1.70 (Δslot 1, i633→61) | 64 | -4.5 | -0.0372 |
| 21 | 11:09:04 | 464792469/246 | 0.6 h | 181.4 | ssss B 0.41 (Δslot 0, i231→246) | 11:09:44 | 8KQs S 0.10 (Δslot 0, i181→320) | 40 | -2.5 | -0.0235 |
| 22 | 11:13:15 | 464793647/29 | 0.7 h | 153.0 | GbtR B 0.88 (Δslot 1, i99→29) | 11:13:58 | X7NM S 4.79 (Δslot 0, i157→229) | 43 | -10.8 | -0.0808 |
| 23 | 11:22:13 | 464796180/7 | 0.8 h | 121.1 | Eavv B 0.24 (Δslot 1, i208→7) | 11:25:54 | Gbgr S 0.40 (Δslot 0, i8→76) | 221 | +30.9 | +0.2138 |
| 24 | 11:29:07 | 464798115/179 | 0.9 h | 171.8 | omeg B 1.05 (Δslot 0, i21→179) | 11:34:38 | FmrN S 0.08 (Δslot 0, i34→136) | 331 | +44.7 | +0.3069 |
| 25 | 11:35:12 | 464799822/13 | 1.0 h | 216.2 | 9H17 B 0.12 (Δslot 1, i226→13) | 11:37:45 | 5S6X B 0.11 (Δslot 0, i17→115) | 153 | +9.2 | +0.0570 |
| 26 | 11:39:05 | 464800913/9 | 1.1 h | 225.4 | 56o9 S 3.03 (Δslot 1, i92→9) | 11:45:42 | FWtt B 0.01 (Δslot 1, i188→28) | 397 | -23.7 | -0.1727 |
| 27 | 11:45:47 | 464802787/200 | 1.2 h | 166.8 | Aw9P S 1.81 (Δslot 1, i181→200) | 11:47:35 | ssss S 1.36 (Δslot 0, i106→134) | 108 | -6.8 | -0.0534 |
| 28 | 11:48:09 | 464803444/254 | 1.3 h | 165.3 | 5Qs4 B 0.38 (Δslot 0, i222→254) | 11:50:46 | G4L7 B 0.14 (Δslot 1, i247→57) | 157 | +67.1 | +0.4648 |
| 29 | 11:51:53 | 464804494/220 | 1.3 h | 258.3 | Aw9P S 2.41 (Δslot 0, i122→220) | 11:52:45 | 4faD S 0.62 (Δslot 0, i99→205) | 52 | -4.5 | -0.0394 |
| 30 | 11:53:03 | 464804831/111 | 1.3 h | 230.3 | 9H17 B 0.06 (Δslot 1, i272→111) | 11:54:19 | FGfn S 0.14 (Δslot 0, i61→111) | 76 | +10.8 | +0.0676 |
| 31 | 11:54:27 | 464805226/273 | 1.4 h | 203.8 | 9H17 S 3.89 (Δslot 0, i216→273) | 11:56:00 | W9zs B 0.00 (Δslot 1, i308→24) | 93 | +7.2 | +0.0436 |
| 32 | 11:56:41 | 464805860/329 | 1.4 h | 204.6 | 5H9e B 0.57 (Δslot 0, i74→329) | 11:57:12 | 6G8C B 6.45 (Δslot 0, i57→119) | 31 | +13.6 | +0.0883 |
| 33 | 12:01:00 | 464807076/69 | 1.5 h | 194.0 | ssss B 0.42 (Δslot 0, i57→69) | 12:04:38 | 3vKC S 0.16 (Δslot 0, i141→166) | 218 | +11.6 | +0.0742 |
| 34 | 12:11:03 | 464809885/544 | 1.6 h | 162.3 | (RPC tail; neighbours not fetched) | 12:13:30 | (RPC tail) | 147 | +5.8 | +0.0349 |

### T2 (trigger windows complete; age in hours since 10-29 create)
| # | buy time | slot/idx | age | buy mc | buy trigger | sell time | sell trigger | hold s | mc ret % | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 06:00:35 | 464705835/166 | 109.5 h | 32.7 | E4zA B 0.21 (Δslot 0, i81→166) | 06:05:45 | 6E8m B 0.00 (Δslot 0, i190→302) | 310 | +11.4 | +0.0937 |
| 2 | 06:05:48 | 464707305/161 | 109.6 h | 38.7 | 3DVM B 0.37 (Δslot 0, i85→161) | 06:08:03 | HANc S 0.33 (Δslot 1, i326→76) | 135 | +135.8 | +0.9923 |
| 3 | 06:08:52 | 464708173/127 | 109.7 h | 116.2 | 8tjE B 1.59 (Δslot 0, i46→127) | 06:10:06 | HUrr S 0.34 (Δslot 1, i189→318) | 74 | -7.2 | -0.0537 |
| 4 | 06:11:10 | 464708825/405 | 109.7 h | 63.1 | FTKT B 0.98 (Δslot 0, i284→405) | 06:11:13 | G1qG S 1.45 (Δslot 0, i221→255) | 3 | -15.4 | -0.1061 |
| 5 | 06:11:15 | 464708844/97 | 109.7 h | 62.4 | 9nW5 B 1.98 (Δslot 1, i443→97) | 06:11:51 | BzpJ S 0.97 (Δslot 0, i72→146) | 36 | +5.1 | +0.0392 |
| 6 | 06:13:46 | 464709553/93 | 109.8 h | 83.1 | 94Jp B 0.87 (Δslot 0, i47→93) | 06:14:44 | D6Ra S 0.36 (Δslot 1, i38→72) | 58 | -13.4 | -0.0944 |
| 7 | 06:14:57 | 464709878/186 | 109.8 h | 78.6 | J1Pz B 0.40 (Δslot 0, i151→186) | 06:15:15 | 3vKC B 0.11 (Δslot 1, i421→27) | 18 | +58.7 | +0.4168 |
| 8 | 06:15:19 | 464709983/88 | 109.8 h | 122.8 | 7XLv S 3.48 (Δslot 1, i303→88) | 06:18:00 | feky S 0.48 (Δslot 1, i140→101) | 161 | +35.1 | +0.2437 |
| 9 | 06:18:29 | 464710865/113 | 109.8 h | 121.4 | DVWD B 0.09 (Δslot 0, i46→113) | 06:19:39 | 2PFs B 0.10 (Δslot 0, i72→114) | 70 | -9.9 | -0.0726 |
| 10 | 06:20:07 | 464711323/428 | 109.9 h | 118.3 | 9dr7 B 2.68 (Δslot 0, i253→428) | 06:20:56 | G715 S 2.79 (Δslot 0, i55→301) | 49 | -14.3 | -0.1032 |
| 11 | 06:21:00 | 464711577/407 | 109.9 h | 90.8 | ARu4 B 0.78 (Δslot 0, i181→407) | 06:22:14 | 5vtL S 1.07 (Δslot 0, i156→359) | 74 | +10.3 | +0.0719 |
| 12 | 06:22:31 | 464712006/172 | 109.9 h | 117.4 | HfmT B 1.98 (Δslot 1, i276→172) | 06:24:59 | DVWD S 0.10 (Δslot 1, i184→156) | 148 | +25.7 | +0.1774 |
| 13 | 06:25:14 | 464712757/144 | 110.0 h | 164.4 | 3zUd B 2.95 (Δslot 0, i71→144) | 06:25:22 | J1Pz B 0.40 (Δslot 0, i116→142) | 8 | +3.1 | +0.0160 |
| 14 | 06:26:14 | 464713039/245 | 110.0 h | 189.6 | J1Pz B 0.40 (Δslot 0, i134→245) | 06:27:34 | 6KCr S 0.43 (Δslot 0, i176→229) | 80 | -21.9 | -0.1595 |
| 15 | 06:27:47 | 464713469/181 | 110.0 h | 162.3 | J1Pz B 0.40 (Δslot 0, i165→181) | 06:28:17 | J1Pz S 0.68 (Δslot 0, i84→135) | 30 | +11.4 | +0.0743 |
| 16 | 06:28:42 | 464713728/243 | 110.0 h | 182.9 | 4vgK B 1.78 (Δslot 0, i188→243) | 06:29:01 | 67Pt S 0.06 (Δslot 1, i243→51) | 19 | -2.0 | -0.0199 |
| 17 | 06:29:14 | 464713875/28 | 110.0 h | 186.2 | H1aF B 0.53 (Δslot 0, i15→28) | 06:29:42 | 3vKC S 0.63 (Δslot 0, i179→195) | 28 | -3.6 | -0.0318 |
| 18 | 06:31:11 | 464714420/84 | 110.0 h | 144.3 | 4vgK S 1.46 (Δslot 1, i300→84) | 06:31:35 | 3zUd S 2.76 (Δslot 0, i155→300) | 24 | -5.5 | -0.0434 |
| 19 | 06:32:50 | 464714878/261 | 110.1 h | 119.1 | 33EK S 1.20 (Δslot 0, i161→261) | 06:38:52 | 8quZ S 0.91 (Δslot 0, i28→90) | 362 | -50.1 | -0.3542 |
| 20 | 06:38:59 | 464716614/146 | 110.2 h | 63.3 | 2MEp B 1.86 (Δslot 0, i33→146) | 06:39:50 | BrfJ S 0.05 (Δslot 0, i154→209) | 51 | +26.6 | +0.1922 |
| 21 | 06:40:15 | 464716970/50 | 110.2 h | 56.7 | DVWD B 0.09 (Δslot 1, i250→50) | 06:43:37 | 7n93 S 0.07 (Δslot 1, i282→15) | 202 | +59.2 | +0.4265 |
| 22 | 06:47:45 | 464719076/437 | 110.3 h | 86.7 | 7YoC B 0.98 (Δslot 0, i370→437) | 06:48:49 | 9t6R S 0.85 (Δslot 1, i493→134) | 64 | +2.5 | +0.0174 |
| 23 | 06:54:32 | 464720978/245 | 110.4 h | 81.7 | 9hsH B 0.49 (Δslot 0, i204→245) | 06:56:45 | DyxF S 0.69 (Δslot 1, i221→6) | 133 | -0.1 | -0.0002 |
| 24 | 06:59:40 | 464722431/90 | 110.5 h | 53.6 | 2tzv S 1.14 (Δslot 1, i186→90) | 07:02:29 | 8ez9 S 0.03 (Δslot 0, i337→515) | 169 | -10.7 | -0.0717 |
| 25 | 07:15:15 | 464726809/61 | 110.8 h | 55.5 | F2on B 0.66 (Δslot 0, i14→61) | 07:25:15 | none in 3 slots | 600 | -21.8 | -0.1508 |
| 26 | 07:47:44 | 464735914/45 | 111.3 h | 46.5 | 676a B 1.47 (Δslot 1, i195→45) | 07:57:44 | none in 3 slots | 600 | -10.1 | -0.0652 |
| 27 | 11:55:09 | 464805422/176 | 115.4 h | 37.8 | 766H S 0.84 (Δslot 0, i97→176) | 11:59:41 | B1aX B 0.22 (Δslot 0, i74→170) | 272 | +1.2 | +0.0183 |
| open | 12:09:32 | 464809462/71 | | 43.4 | 9eCe B 1.08 (Δslot 1, i293→71) | (open at data end) | | | | |

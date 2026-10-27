# Pre-sent conditional buys (agent study, 10-25 00:55 → 01:50 PKT)

Offline replay on the recorded tapes. Read-only, $0, no servers touched, nothing traded.
MEASURED = chain data, tapes, and replays on them. INFERRED = my reading.
Scripts: ops/strategies/presend/ (ps1–ps10). Data (0.7 GB): /home/moiz/sniper-data/strategies/presend/.
(Saved by the main session: the study agent could not write this file itself.)

## Verdict
- **Yes, but only in one form: the "whale buy" trigger (T2).**
  - A wallet that is not the creator and did not buy in the create slot buys up to ≥ 5% of supply.
  - For the next 10 slots (~2 s) we keep a 0.55 SOL conditional buy alive. It fills only on a sudden drop of ≥ 12% vs the price 50 ms earlier.
  - We sell 2 slots after entry, take-profit +10%, stop-loss −20%.
- **Results on the test days.** The config was chosen on R2 only, then run unchanged on R3 + R4 + R1 (39 h) with cheap attempts:
  - **+5.8 SOL/24h** when we land within 10 ms after the dump (20 attempts per slot). The 90% interval is +2.6 to +9.0.
  - **+3.6 to +4.4 SOL/24h** with 4 attempts per slot (landing 0–53 ms after).
  - **It loses with 1 attempt per slot.**
- **It ADDS to today's reactive bot; it does not replace it.**
  - Only 2–8% of its fills are on a dump the reactive bot also fills.
  - With both sharing the 2 servers, the total beats the reactive bot alone on every test day: **+3.6 / +4.7 / +5.3 SOL/24h** at 35 / 50 / 75 ms (pooled test).
- **Attempts must be cheap.**
  - At what we pay now per tx (100k CU × 5M µL/CU ≈ 0.0005 SOL), every variant loses 4–870 SOL/24h.
  - T2 breaks even at about 10,000 lamports per failed attempt. The cheap row uses 5,060.
- **Copying the real pre-placers does not pay for us.**
  - They catch serial creators' dev dumps 3–20 s after launch and land 2–10 ms after the dump.
  - In the replay that target pays only if we are first in line (+6.9/24h). At 5–10 ms behind it loses 1–9 SOL/24h.
- **"Wait for a further drop after a dump" (T1) is about zero.** The trailing version (T1t) is small but steady: +3.6/24h at 4 attempts per slot.
- **Weak spots:**
  - R3 alone is not clearly positive for T2: +3.25 SOL over 21 h, 90% interval −0.6 to +7.0 SOL.
  - Without the top 1% of fills, the pooled result drops to +2.4/24h.
  - Shadow-test before any money.

## Key table – T2 "whale buy", one config, SOL per 24 h (MEASURED replay, cheap attempts)
Config: non-creator, non-create-slot wallet reaching ≥ 5% of supply. Window 10 slots. y = 12% sudden drop. 0.55 SOL. Exit c2_tp10_sl20.

| Where we land after the dump (attempts per armed slot) | R2 train | R3 test | R4 test | R1 test | Pooled test |
|---|---|---|---|---|---|
| (a) right after it (20) | +19.7 | +9.2 | +14.6 | +15.9 | +12.2 |
| (b) after trades within 5 ms (20) | +13.4 | +3.7 | +8.3 | +9.1 | +6.1 |
| (c) after trades within 10 ms (20) | +13.1 | +3.7 | +8.6 | +8.2 | **+5.8** |
| 20 per slot → 0–11 ms after | +13.7 | +3.2 | +8.8 | +10.3 | +6.3 |
| 4 per slot → 0–53 ms after | +11.7 | +4.1 | +4.9 | +4.8 | +4.4 |
| 1 per slot → 0–212 ms after | +3.1 | −1.2 | +0.7 | −1.6 | −1.2 |

The same config at (c), with other cost rows (pooled test, per 24 h):

| Cost row | Pooled test |
|---|---|
| Sell also tipped 0.001 | +4.4 |
| Only 1 attempt per slot charged (optimistic, does not match a 10 ms landing) | +11.2 |
| Today's fees (100k CU × 5M µL/CU) | −549 |

Fill details:
- About 1,350–1,600 fills per 24 h, from about 6,000 armed windows per day.
- Net +0.0028 / +0.0064 / +0.0053 per fill on R3 / R4 / R1. Win rate 51–55%.

## All triggers (each row's config chosen on R2 for that row; SOL per 24 h, pooled test, cheap)
| Trigger | (c) +10 ms, 20/slot | 4/slot | 1/slot | Notes |
|---|---|---|---|---|
| T2 whale buy (above) | **+5.8** [+2.6, +9.0] | +3.6 [+0.5, +6.9] | −2.7 | positive on all 3 test days at (b) / (c) / 20 per slot |
| T2, "any holder ≥ 10%" version | −4.7 | +0.3 | +0.2 | +18.5 only if first in line (a); not usable |
| T1t trailing: after a ≥ 4.65% dump on a serial-creator token, the next sudden ≥ 12% drop within 5 slots | +2.2 | +3.6 [+1.9, +5.3] | −0.1 | small and steady; being first is worse (falling knife) |
| T1 fixed: a further drop of y after a dump | +0.3 | −1.6 | −0.2 | about zero |
| T3 the pre-placers' target (serial creators' launches) | −1.2 | +0.8 [−1.1, +2.9] | +0.3 | +6.9 only if first in line (a) |

## What the real pre-placers do (step 1, MEASURED from chain rows + tapes)
How they were found:
- Scanned all raw chunks of R1–R4, failed txs included.
- A pre-placer has many cheap failed buys and fills landing right after a ≥ 2% same-slot dump.
- 16 wallets were checked. 4 are not dip catchers: GG5ATPW7, 4A1AVd1m, FCcH6Now and 4PLea6xQ hold for minutes and lose 1–114 SOL/24h on the curve.

| Wallet | Fills/24h | Catches | Lands after dump (proxy ms p25/50/75) | Failed attempts per fill | Exit | Net SOL/24h R2 / R3 / R4 / R1 |
|---|---|---|---|---|---|---|
| FUru6V3L | ~125–205 | creator dump (90%), drop ~12%, token 5–12 s old | 1.6 / 4.8 / 12.7 | 630–940 (own check program) | 2–4 slots | +2.8 / +7.4 / +2.5 / +5.4 |
| 5ZKd8DNB | ~150–250 | creator 42% / insider 9%, drop ~17%, token 3–11 s | 2.8 / 9.5 / 28 | 18–44 (pump slippage + check) | 1–3 slots | +2.2 / +8.5 / +2.8 / +4.1 |
| 8g1w4PNC (same program as 5ZKd8) | ~110–235 | same | 3.1 / 9.5 / 26 | 14–19 | 1–2 slots | +4.7 / +4.7 / +0.2 / +5.1 |
| CVPz447t | ~175–300 | creator 35% / insider 15%, drop ~12%, token 3–8 s | 10 / 21 / 40 | 150–245 (pump slippage 6042, no tip, no priority) | 19 slots | +2.9 / +1.9 / +7.3 / +0.9 |
| 2KtcBC | ~40–220 (new) | creator 46%, drop ~24%, token 0–6 s | 4 / 13 / 39 | 4–530 (L2TExMFK check, 6001) | 3 slots | −0.8 / +1.3 / +6.9 / — |
| 5k2Ckkiu | ~150–380 | creator 26% / insider 14%, token 7–20 s | 11 / 25 / 49 | 240–400 | 2 slots | −0.2 / +1.5 / −2.2 / +2.8 |

Note (main session): L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95 is the Lighthouse assertion program — the same program our
engine already uses for the slot-deadline guard. So 2KtcBC's "check program" is a Lighthouse assertion, not custom code.

How they pick tokens:
- They go after serial creators whose launches nearly always get an early creator dump.
- Examples: ENskGQev 132 of 132 launches, 2F6p8TXy 68/68, bwamJzzt 456/483, timeworn 175/175. Over all launches the rate is 22%.
- 26–86% of their target mints come from repeat creators.

When they start sending:
- 0–7 s after the create (median).
- For about 4–14 slots, at 2–29 attempts per slot (FUru6V3L ~24 per slot), until the dump.

What they catch:
- Usually the second sell of a fast cascade: another ≥ 2% sell came 1–4 slots earlier in 64–100% of their fills.
- For the top five, the dumper was the biggest holder 72–97% of the time. It held ~9–13% of supply and had bought 8–30 slots earlier.

Three ultra-fast wallets (9K5QgBKa, CZ77onJz, FNuoWSQc) land within 10 ms of dumps 70–88% of the time with few failed txs. They are not pre-placers, but they sit in the same spot (INFERRED: shred-level reaction).

## Costs per fill (pooled test)
| Config | Attempts per fill | Attempt cost per fill (cheap) | Fill + sell | Net per fill | Attempt cost per fill at today's fees |
|---|---|---|---|---|---|
| T2 (c), 20 per slot | 778 | 0.0039 | 0.0010 | +0.0041 | 0.39 SOL |
| T2, 4 per slot | 323 | 0.0016 | 0.0010 | +0.0027 | 0.16 SOL |
| T1t, 4 per slot | 267 | 0.0013 | 0.0010 | +0.0058 | 0.13 SOL |

- Every armed slot is charged, including windows that never fill (about 80% of T2 windows expire without a fill).
- A failed attempt costs 5,000 base + 60k CU × 1,000 µL/CU = 5,060 lamports. A fill pays tip 0.001 + base + priority. The sell is one more tx.
- The real pre-placers pay 0.0002–0.013 SOL per fill in failed fees.

## Compared with today's reactive bot (same hours; IMIT1 top4 inside the envelope)
| Day | Reactive alone, c4 exit, 35 / 50 / 75 ms | Reactive + T2, shared 2 servers | Gain per 24 h |
|---|---|---|---|
| R3 | +4.33 / +1.99 / +0.80 | +5.77 / +4.26 / +3.19 | +1.6 / +2.6 / +2.7 |
| R4 | +1.03 / +0.64 / +0.37 | +1.46 / +1.49 / +1.28 | +3.2 / +6.3 / +6.7 |
| R1 | +6.12 / +3.93 / +1.54 | +10.10 / +8.52 / +6.88 | +6.4 / +7.4 / +8.5 |

- The c6_tpnone_sl10 exit gives the same picture: +1.8 to +7.9 per 24 h.
- Only 2–8% of the T2 fills are on a dump the reactive bot also fills, so T2 adds trades rather than replacing them.
- On those shared dumps the pre-sent order lands first and the reactive buy is skipped. They are among the reactive bot's best, so the gain is less than the two results added together.
- Holding the shared dumps with the reactive exit did not help.

## Robustness (T2 at (c))
- **Hour-block bootstrap, 90% intervals:**
  - Day totals: R3 −0.6 to +7.0 SOL (21 h), R4 −0.4 to +2.7 SOL (3.3 h), R1 +2.5 to +8.1 SOL (15 h).
  - Pooled: +2.6 to +9.0 per 24 h.
- **Without the top 1% of fills:**
  - Pooled +2.4/24h.
  - R3 +0.25 SOL (≈ 0), R4 +0.65, R1 +3.0.
- **Positive hours:** 64% pooled.
- **Spread:** about 1,000 tokens per day, at most 3–4 fills per token.
- **Falling knife:** 11–16% of fills see a further ≥ 10% drop within the 2-slot hold. The −20% stop caps it.
- **What a fill looks like:** the whale buys a median 3 SOL (7% of supply) at token age 3–31 s (median 8 s), and the ≥ 12% drop comes ~4 slots later.
  - 55% of the time the whale itself sells: +0.0126 per fill.
  - 45% of the time it is someone else: +0.0057 per fill.
  - Under (c), a pre-placer was ahead of us in only 1% of fills.
- **Selection:**
  - About 130k configs were tried on R2.
  - The same T2 filter was picked under 5 of the 6 queue rows.
  - The y grid was extended to 16/20/25% because R2's best sat at the 12% edge. This is labelled as an extension, and it did not change T2.

## Risks
- **Queue position is a model.**
  - The tape gives block position × slot time, not network time.
  - Rows (a)–(c) are assumptions. The "k per slot" rows assume evenly spaced attempts.
  - INFERRED: the pre-placers' 3–10 ms landings with tiny priority fees show it is doable.
- **Thin margin:**
  - About +0.004 SOL per fill net.
  - Twice the attempt cost, or a 0.002 tip, wipes most of it out.
  - The top 1% of fills carry about 60% of the profit.
- **Double fills.** Several copies can succeed while the price stays low. A guard is needed (check program "not holding", or wallet SOL for one position only).
- **Send load:**
  - About 13 attempts/s on average.
  - Bursts reach about 130/s (99th percentile) and up to about 450/s with 5–7 windows armed. Relay limits may bite.
- **Competition can move in.** The dev-dump catchers could add whale-buy targets, and flippers can change timing.
- **Follower model.** The follower slippage model is generic. Our buy ahead of the reactive dip bots may break their +5% guards and weaken the bounce more than modelled.
- **Data.** R4 is only 3.3 h. Results vary a lot by hour.

## What an engine version would need
1. **Trigger.**
   - Track per-token wallet balances from the trade feed.
   - Arm when a buy takes a non-creator, non-create-slot wallet to ≥ 5% of supply.
   - Disarm after 10 slots, or 30 ms after that wallet's first sell.
   - Arming speed is not critical: the dump comes a median ~4 slots later.
2. **Send stream while armed.**
   - 4–20 conditional buys per slot, each signed with the latest price × 0.88 as the limit, 0.55 SOL.
   - Pause while both servers hold a position.
3. **Condition.** Either option works:
   - pump's slippage check (BuyExactQuoteInV3 with min tokens out at the limit; fails with 6042);
   - a small check program (e.g. a Lighthouse assertion) that fails early on price > limit, slot > expiry, or already holding. This also blocks double fills.
4. **Fees.**
   - CU limit ≤ ~60k, priority ≤ 1,000 µL/CU (the pre-placers use 0–90).
   - One 0.001 tip inside the tx, so a failed attempt reverts the tip.
   - No tip fan-out per attempt.
   - Break-even is about 10,000 lamports per failed attempt.
5. **Exit.**
   - Sell 2 slots after entry, TP +10% / SL −20%.
   - Pre-sending the sell (as 2KtcBC does) would shave time. Not modelled.
6. **Servers.** Either server can run the stream; no near leader is needed. Each server holds one position. On a shared dump the pre-sent fill wins over the reactive buy.
7. **Shadow test first.**
   - Log every T2 arm/disarm and the would-be fill for 24 h on both servers, and replay it.
   - Pass if ≥ +0.003 SOL per fill after attempt costs and ≥ 15% of windows fill.
   - Then a small live probe (owner OK) to measure where cheap attempts really land.

## Method (short)
- **Replay (ps4):**
  - The order goes live 50 ms after the trigger.
  - It fills at the first trade that puts the price at or below the limit. We are placed after the trades within D ms, and fill only if the price there is still at or below the limit.
  - The reference price is either fixed (the post-dump price) or trailing (the price 50 ms before).
  - After the fill, dd1_build's path mechanics apply. They were checked to match dd1 exactly on 1,600 rows: followers whose slippage our buy breaks are dropped, pump fee on both sides, exits at 75 ms into the slot.
- **Engine (ps5):**
  - One armed window per token at a time.
  - 2 servers with one position each; any free server takes a fill.
  - Attempts are charged for every armed slot, except while both servers are busy.
- **Selection (ps6):** R2 only. Then ps7 runs the choices unchanged on R3 / R4 / R1.
- **Comparison (ps8):** dd_lib.sim with IMIT1 top4 inside the envelope, 35 / 50 / 75 ms, exits c4_tpnone_slnone and c6_tpnone_sl10, the same eval windows as dipdetect.

Output files:
- ps3d_summary.txt and ps3g_costs.txt (pre-placers).
- ps6_select.txt (R2 choice).
- ps7_test.txt, ps7b_cross.txt and ps7d_pooled.txt (tests).
- ps8_compare.txt (reactive comparison).
- ps10_costs.txt.

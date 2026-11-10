# 9pQQ case study 3, PHASE 2: do the earlier claims hold on T3?

Sources checked:
- `../REPORT.md` (R)
- `../exact/REPORT.md` (X)
- `../cases/PHASE1.md` + `PHASE2.md` (C1 = the first case study, on T1 D2496au7 and T2 7aFTe3Sq)

Evidence comes from PHASE1.md here and from `/home/it/sniper-data/rivals/9pQQ/cases3/`. Scripts are in `code/`; phase2.py and hazard*.py produce every number below.

Sample sizes:
- **T3:** 16 trips plus 1 failed buy, complete tape, 11:40 to 11:52 PKT, 11-03.
- **Window:** 9pQQ's txs on all 338 tokens it traded from 09:31 to 12:40 PKT (1,157 buys, 1,145 closed trips). I used these for the hard rules.

T3 is very busy. 58% of its active slots have an outside trade in the slot or the one before; on T1 that figure was 12%. So "follows an outside trade" is checked with a per-slot hazard instead of a raw share. Our bot (EgxfY…) has **zero** txs on T3, failed ones included.

## Claim by claim

| # | claim (source) | T3 verdict | evidence |
|---|---|---|---|
| 1 | One buy + one full sell; never 2 positions on one token (R, X, C1) | **HOLDS** | T3 is strictly B,S ×16, with full-bag SellV3. All 338 tokens in the window alternate B/S. Positions on different tokens overlap freely. |
| 2 | Buy = BuyExactQuoteInV3 for exactly 700,000,000 lamports incl. pump fees (X, C1) | **HOLDS** | 16 of 16 buys: 691,358,023 to the curve + 6,567,902 protocol fee + 2,074,075 creator fee = 700,000,000. In the window, 1,157 of 1,157 buys were 0.70 SOL, with the ATA created when missing. |
| 3 | CU price 1,500,001; CU limit 130k/80k; Astralane 1,000,000/100,000 + Jito 17,500; 1.46 mSOL per trip (R, X, C1) | **HOLDS** | All 2,307 trade txs in the window, T3 included. Jito recipients rotate. |
| 4 | One tx per decision, no copies, no nonce (R, C1) | **HOLDS** | 17 buy attempts on T3, each a single tx. No duplicates. |
| 5 | Failed buys 4–8%, mostly 6042 (R, C1) | **HOLDS** | 1 of 17 attempts (5.9%), error 6042, at +934 after a 6.84 SOL buy moved MC +46% in-slot. It re-bought 5 slots later. |
| 6 | Never mayhem (R, X) | holds (weak) | T3 is not mayhem. |
| 7 | Never buy before age 8 slots; most at 10–11 (X, C1) | **HOLDS**; "most at 10–11" only partly | T3's first buy came at age 19. Across 313 tokens launched in the window, the first buy was at age ≥ 8 (minimum 8, 1 token at 8, peak at 11). But 89 of 313 first buys came after ≥ 60 slots, so "most at 10–11" holds only among the early entries. |
| 8 | Never sell before buy + 2; never re-buy before own sell + 2 (X, C1) | **HOLDS** | Window minimum hold = 2 slots; minimum re-buy gap = 2 slots (several of each). On T3: minimum hold 11, minimum gap 22. **Correction to my PHASE1:** the "minimum hold ~11 slots" is specific to T3, not a rule. |
| 9 | 600 s hold cap; forced exits lose (R, X, C1) | **HOLDS** | T3's longest hold is 56 s, so the cap never applied there. In the window, 61 holds ended at 590–601 s; maximum 601 s. |
| 10 | 98–100% of buys have an outside trade in the same/previous slot (X, C1) | **HOLDS** | 16 of 16 buys + 1 of 1 failed. Buy hazard is **0 of 934** flat slots with no outside trade in the window, vs 16 of 1,033 with one. |
| 11 | Sells follow an outside trade (79–97%), the rest = time cap (R, X, C1) | **HOLDS** | 16 of 16 sells. Sell hazard is **0 of 469** hold slots with no trade, vs 16 of 936 with one. |
| 12 | About 70% of reactive sells follow an outside SELL (R, C1 78%) | **holds, weaker** | 10 of 16 (63%), against a 43% sell share of all outside trades. Sell hazard: 4.3% after a 0.3–1 SOL outside sell, 2.6% after ≥ 1 SOL, 1.1–1.5% after small buys or sells. |
| 13 | Buys: ~70% in the trigger's same slot, ~50–73 positions later (R 67–69%, C1) | **PARTLY** | 8 of 16 buys in the same slot (9 of 17 with the failed one) = **50–53%**, a median ~36 positions later (range 8–235). The other 8 landed early in the next slot (pos 1–96). Sells: 11 of 16 (69%) in the same slot, 6–148 positions later. |
| 14 | On dumps it is slow / our follower; first outside buyer only 33–37% (R). C1: "slow only when we are there", first after the dump 13 of 18 | **NOT CONFIRMED** (we were absent) | We were not on T3. On its 9 dip-buys (an outside sell ≥ 1 SOL in the window), it was the first outside buyer after the dump in **4 of 9** (44%), second in 2, and 3rd–5th in 3. Example: after a 4.32 SOL dump at +1110/213, 7PedQZ (1.62), EJX629 and 4GCtzC (41Pr) all bought before it in +1111. That is between R's 33–37% and C1's 72%, so it is not fast on dumps here even without us. |
| 15 | No TP/SL; flat sell hazard whatever the return (R, X, C1) | **HOLDS** | Hazard by return since entry: 1.9 / 2.4 / 1.7 / 2.0 / 1.1% for < −5%, −5..0, 0..5, 5..15 and > 15%. It held trip 15 through −35% and trip 16 through −31%, and let trip 1 run to +208% before selling at +159%. |
| 16 | Sell chance rises when outside buying pauses (R: 300+ slots; X: 3–10 slots; C1: 10–30 s) | **HOLDS in direction, at a shorter time scale** | Sell hazard by slots since the last outside buy: ≤ 2 slots 0.8% (604 slots), 3–7 slots 2.4% (253), **8–25 slots 6.7% (75)**, 26–75 slots 0 of 4. On a busy token the pause that matters is about 3–10 s; 10–30 s pauses almost never happen during its holds. **Correction to my PHASE1** ("sells don't wait for a pause"): the sell came 0–13 slots after the last buy, but the hazard does rise as the pause grows. |
| 17 | Sell chance rises after big prints / high-volume bot sells (R; C1: 14% for ≥ 3 SOL) | not testable / weak | Only 3 hold slots had a ≥ 3 SOL trade in the window (0 sells). Outside sells ≥ 1 SOL gave 2.6%, *lower* than 0.3–1 SOL sells (4.3%). |
| 18 | The next trade after its sell is a sell 63% (R, C1 67%) | **HOLDS** | 12 of 16 (75%). |
| 19 | Ignores trades < 0.05 SOL for buys; tiny trades can trigger sells (R, C1) | **HOLDS** | Buy hazard: 0.3% when the largest trade in the window is a buy < 0.3 SOL, 0% for a sell < 0.3. No buy with only tiny trades in the window. 3 of 16 sells followed trades of 0.005, 0.01 and 0.048 SOL. |
| 20 | Follows buys more than sells (R; C1: T1 24/33, T2 23/28) | **CONTRADICTED on T3** | Last outside trade before its buy: 9 buys, 7 sells (56% buys), the same as the 57% base. Hazard by the largest trade in the window: buy ≥ 1 SOL 6.6% ≈ sell ≥ 1 SOL 6.4%. Only 0.3–1 SOL trades favour buys (2.2% vs 0.7%). On T3 it reacts to **size**, not side. |
| 21 | Curve 32–50 SOL preferred, ≥ 80 avoided; buys at 30–112 (R, X) | range holds; "≥ 80 avoided" weak | Virtual SOL at its buys: 38.8–89.3. 4 of 16 buys were at ≥ 80 (net −0.008). Most buys were at 57–78, above the "preferred" band. |
| 22 | Skips quiet flow (\|net 10 slots\| < 0.5 SOL) (R) | holds (soft) | 1 of 16 buys came in quiet flow (net 0.10). |
| 23 | Re-entry dominates (R 68%; C1 60/62) | **HOLDS** | 15 of 16 (94%). It farmed T3 for 12 min and stopped when volume died (outside buys fell from ~30 to 2 per 150 slots). |
| 24 | Re-entry within 25 slots of its own sell is best (R) | not testable | n = 1 (trip 7, gap 22 slots, −0.032). |
| 25 | Lanes: DIP best (R); C1: "lane ranking depends on the token" (MOMO/DRIFT won on T1/T2) | **"depends on the token" HOLDS**; "DIP best" CONTRADICTED again | Using R's definitions on T3: LAUNCH 1 trip +1.047, MOMO 2 trips +9.9 mSOL/trip, **DIP 13 trips −5.2 mSOL/trip** (−0.068). DRIFT 0. The ranking differs from both R and C1. |
| 26 | Not a copy-trader of leader wallets (X H1, C1) | **HOLDS** | 15 distinct trigger wallets for 16 buys (8PgC4n twice). Some cohort wallets recur across tokens (8PgC, sssssw, EMKY, GKd5, ARu4 also appear on T1), but none drives a large share. |
| 27 | Trigger program 41Pr4XqE is enriched but only 6–9% of buys (X, C1) | holds (tiny n) | 41Pr was in 2 of 16 buy windows (12.5%), against 17 of 2,537 outside trades (0.7%). |
| 28 | Followers 2.0–2.4 wallets / 0.8–1.1 SOL within 3 slots; ssssswdk ~10% (R); C1 lower | **higher on T3**; sssssw is a co-trader | Mean 4.4 wallets / 1.23 SOL (median 4 / 0.65). That reflects the busy token, not a follower effect. sssssw bought within 3 slots after 2 of its buys and before 3 (same as C1: co-trader). **NEW: a real copy-bot, 8d1YSS1u**, see below. |
| 29 | Up to 25–32 open positions (X) | consistent | In the window it often held 5–12 positions, up to 17 (the upper values may be inflated by sells the recorder missed). |
| 30 | Slippage ~10–15% (X, inferred) | consistent | The one failure came after a +17..+24% move from the likely decision state (the 6.84 SOL buy at pos 0) to its landing at pos 144. |
| 31 | 0.5 SOL period (R) vs 0.48 (X) | not testable | T3 and the whole window: 0.70. |
| 32 | Hold cap / forced exits lose (R) | not testable on T3 | No forced exit on T3. |

## C1's sharper findings, one by one

| C1 finding | T3 |
|---|---|
| Buys follow an outside trade in the same/previous slot (~100%) | **CONFIRMED** (16/16 + 1 failed; 0 buys in 934 trade-free flat slots) |
| Mostly behind an outside BUY | **CONTRADICTED** (9/16 = base rate; equal hazard for ≥ 1 SOL buys and sells) |
| ~70% in the same slot, ~50–73 positions later | **PARTLY**: 50% same slot, ~36 positions later; the rest early in the next slot |
| Buys after an outside buy make the money, after a sell lose | **REVERSED on T3**: after a buy −0.150 (3 of 9 won); after a sell +1.151 (+0.104 without trip 1; 6 of 7 won). Same split by net flow: dip side +1.144, buy side −0.143. |
| Sells react to an outside trade in the same slot, often a sell, any size | **CONFIRMED** (16/16 within a slot; 11 in the same slot; 10 behind a sell; trigger size 0.005–1.5 SOL) |
| Sell hazard rises when buying pauses 10–30 s | **DIRECTION CONFIRMED, scale shorter** (rises from 0.8% to 6.7% at 8–25 slots ≈ 3–10 s) |
| No TP/SL, 600 s cap | **CONFIRMED** (flat hazard by return; cap seen across the window) |
| ~97% re-entries | **CONFIRMED** (94%) |
| One position per token | **CONFIRMED** |
| 0.7 SOL incl. fees | **CONFIRMED** (exactly 700,000,000) |
| CU 1,500,001 + Astralane/Jito tips | **CONFIRMED** (identical on all 338 tokens, so no token-specific send lanes) |
| Never before age 8 slots | **CONFIRMED** (T3 19; window minimum 8) |
| "Lanes depend on the token" | **CONFIRMED** (third ranking: LAUNCH > MOMO > DIP; DIP loses) |
| "Slow on dumps only when we are there" | **NOT CONFIRMED**: we were absent and it was still first after the dump only 4 of 9 times |

## New on T3
1. **A copy-bot follows 9pQQ:** 8d1YSS1uVDWg6SdpGudUAMzHzp569ksrYFtvFzixMwgL.
   - It buys 0.049 SOL after 15 of 16 of 9pQQ's buys, in the same slot (61–225 positions later) or the next one.
   - It sells **exactly 13–15 slots after each 9pQQ sell** (14 of 15).
   - The size is too small to matter, but it shows 9pQQ's fills are visible and copied.
2. **Trigger size matters more than side.**
   - Buy hazard is ~6.5% for any outside trade ≥ 1 SOL, 0.3–2.2% for 0.3–1 SOL, and ~0% for smaller trades.
   - It still let ~94% of the ≥ 1 SOL triggers go by, so which triggers it takes remains unexplained (same as X and C1).
3. **The same pattern is worth very different amounts on different tokens.**
   - On T3 the P&L is one early ride (+1.047, age 19 to 190 slots, MC 48→125). The other 15 trips net −0.047.
   - T2 in C1 looked the same (one +0.99 trip). The edge is in rare big runs held through a flat-hazard exit, not in the average re-entry.
   - Across the whole window: 1,145 trips, +8.5 SOL in 3.15 h, 40% win rate, median trip −0.018.
4. It stopped trading T3 when outside volume collapsed, with no forced exit.

## Verdict: what holds across all three tokens (T1, T2, T3)

**Confirmed on all three, high confidence:**
- the fixed execution recipe (0.70 SOL, CU 1,500,001, 130k/80k, Astralane + Jito tips);
- one position per token, full-bag sells;
- repeated re-entry while the token is busy (94–97%);
- every buy and every sell is gated by an outside trade in the same or previous slot;
- no TP/SL (flat hazard by return);
- 600 s cap;
- age ≥ 8 slots;
- sell hazard rises as outside buying pauses.

**Token-dependent (do not generalise):**
- the trigger side for buys (behind buys on T1/T2, either side on T3);
- which entries make money (momentum on T1/T2, dips on T3; R's lane ranking differs on every token);
- the same-slot share for buys (70% vs 50%);
- the pause time scale (10–30 s on T1, 3–10 s on T3).

**Still unexplained:** which of the many qualifying trades it acts on (it skips ~90%+), and what fires a given sell beyond "an outside trade, more likely a sell, more likely after a buying pause".

**Not confirmed:** "fast on dumps when we are absent". On T3, without us, it was first after only 4 of 9 dumps.

# 9pQQ case study — PHASE 2: study claims checked against T1 / T2 (11-03, PKT)

Sources checked:
- `ops/strategies/rivals/9pQQ/REPORT.md` (R)
- `ops/strategies/rivals/9pQQ/exact/REPORT.md` (X)

Evidence comes from PHASE1.md and `/home/moiz/sniper-data/rivals/9pQQ/cases/` (CSV tables, tapes, scripts).

Sample sizes and coverage:
- **T1:** 34 trips plus 2 failed buys. The tape is complete.
- **T2:** 28 buys and 27 sells. All of 9pQQ's txs are included, plus every T2 tx in slots s−10..s+3 around each action. Full hold tapes exist for 3 holds only.
- Two tokens on one day is a **case check, not a population test**.

## Claim by claim
| # | claim (source) | verdict | evidence on T1/T2 |
|---|---|---|---|
| 1 | One buy + one full sell per position; never 2 positions on one token (R, X) | **HOLDS** | All 61 sells sold the exact bought amount. Positions on a token never overlap. He did hold T1 and T2 at the same time (11:55–11:57), which fits "many open positions". |
| 2 | Buy = BuyExactQuoteInV3 for exactly 700,000,000 lamports incl. pump fees; creates ATA (X) | **HOLDS** | 62/62 buys: curve SOL + protocol fee + creator fee = 700,000,000 (691,358,023 + 6,567,902 + 2,074,075). The ATA is created idempotently and its rent (1,513,840) comes back via separate batched CloseAccount txs 5–20 s after the sells. |
| 3 | CU price 1,500,001; CU limit 130k buy / 80k sell; tips Astralane 1,000,000 / 100,000 + Jito 17,500; 1.46 mSOL per round trip (R, X) | **HOLDS** | All 124 trade txs. Buy fee 200,001 + 1,000,000 + 17,500; sell 125,001 + 100,000 + 17,500; total 1,460,002 lamports per trip. The Jito recipients rotate among the standard tip accounts. |
| 4 | One tx per decision, no copies, no durable nonce (R) | **HOLDS** | No duplicate sends, no nonce instructions. Only failures: 2 single slippage failures on T1 (6042). |
| 5 | Failed txs 4–8 % of buys, mostly 6042 (R) | **HOLDS** | T1: 2 of 36 buy attempts (5.6 %), both 6042. T2: 0. |
| 6 | Never mayhem (R, X) | holds (weak test) | Neither token is mayhem. |
| 7 | Never buy before token age 8 slots; most at 10–11 (X) | **HOLDS** | T1 first buy at **age 10 slots**, right behind a 1.67 SOL sniper sell. He skipped the slot-0 launch block. T2 is not testable (bought at 109 h). |
| 8 | Never sell before buy slot + 2; never re-buy before own sell + 2 (X) | **HOLDS, and the +2 limit is visible** | Shortest hold: 71 slots (T1), 13 slots (T2). Shortest successful re-buy: 4 slots (T1), 6 slots (T2). One T1 re-buy attempt fired at **exactly own sell + 2** (sell 464784661, buy 464784663, failed 6042). |
| 9 | Hold cap 300 s, 600 s since 10-31 14:03; forced exits lose (R, X) | **HOLDS** | T2 has two exits at **exactly 600 s** with no outside trade in the 26 s / 212 s before them. Both lost: −0.151 and −0.065 SOL. T1's longest hold is 397 s, so not 300. |
| 10 | 98 % of buys have an outside trade on the token in the same/previous slot; random 37–38 % (X) | **HOLDS (stronger here)** | **61/61** buys plus 2/2 failed buys. Base rate over T1's active period: **12 %** of slots. The study's 37–38 % uses another denominator; the conclusion is the same. |
| 11 | Sells: 79–92 % follow an outside trade, the rest are time cap (R 86 %, X) | **HOLDS (stronger here)** | **58/60** sells (97 %) are within 1 slot of an outside trade. The other 2 are exactly the 600 s cap. |
| 12 | Of reactive sells, ~70 % follow an outside sell (R) | **HOLDS** | T1 25/33, T2 20/25, about 78 %. |
| 13 | Buy-in ~45 ms median, 67–69 % same slot (R) | holds (slot share only) | Trigger in the same slot: T1 23/33, T2 20/28, about 70 %. Median position after the trigger: 50 (T1) / 73 (T2) txs. Milliseconds are not measurable from the recordings. |
| 14 | On dumps he is SLOW (130–152 ms) and our follower; first outside buyer only 33–37 % (R) | **mixed** | Against **us**: holds. On the one shared T1 dump (8GgR −3.81 SOL, slot 464782540 i157), our buy landed in the dump slot at i173. 9pQQ came one slot later (464782541 i85) and **failed on slippage**. On his own 18 dip buys, though, he was the **first outside buyer after the dump 13/18 times**, 7 of them in the dump's own slot. So "first buyer only 33–37 %" is contradicted here; on these tokens he is fast on dumps when we are not present. |
| 15 | No TP/SL; flat 2–4 % sell chance per outside trade, whatever the return (R); simple exit rule rejected (X H3) | **HOLDS** | T1: 33 sells over 1,489 outside events = 2.2 %. Hazard by return bucket is 1–5 % with no level pattern. Trailing-stop and TP tests fail: he held through deeper drawdowns than the ones he sold on. T2 06:32:50 trip: held through **−61 %** for 362 s and sold at −50 % (−0.354 SOL). |
| 16 | Sell chance rises when outside buying stops (R: 1.4 % → 13 % after 300+ slots; X: "dries up 3–10 slots") | **HOLDS (R); X's time scale is too short** | T1 hazard by time since last outside buy: <1 s 1.5 %, 1–3 s 0.5 %, 3–10 s 2.6 %, **10–30 s 7.3 %**, >30 s 1 of 3. The rise starts around 25–75 slots, not 3–10. Also net flow over 10 slots of −0.5..−2 SOL gives 5.4 %, vs 0.3–0.8 % when flow is positive. |
| 17 | Sell chance rises when a high-volume bot sells (R 7.5–11 %) | holds (by size) | Outside events ≥ 3 SOL: hazard 14 % (3 of 21). Wallet identity was not tested. |
| 18 | Next trade after his sell is a sell 63 % (R) | **HOLDS** | T1 22/33 (67 %). T2 is unreliable (gaps in the tape). |
| 19 | Ignores trades < 0.05 SOL; sweet spot 0.2–2 SOL (R) | **HOLDS for buys only** | Smallest buy trigger: 0.06 (T1) / 0.09 (T2) SOL; most are 0.2–3. But **6 of 58 sells were triggered by trades < 0.05 SOL** (0.001–0.048). The size floor is a buy-side rule. |
| 20 | Follows buys more than sells (R) | **HOLDS** | Last trade before his buy is an outside buy in T1 24/33, T2 23/28. |
| 21 | Curve 32–50 SOL preferred; < 32 and ≥ 80 avoided (R); buys at curve 30–112 SOL (X) | range holds; "≥ 80 avoided" **weak here** | Buy curves: T1 35.2–91.2 SOL, T2 32.4–78.1. On hot T1, **6/33 buys were at ≥ 80 SOL** (net +0.044 vs +1.40 for the other 27). It is a preference, not a rule. |
| 22 | Skips quiet flow, \|net 10 slots\| < 0.5 SOL (R) | soft | 8/33 (T1) and 5/28 (T2) buys came in quiet flow. |
| 23 | Own history matters most; re-entry; 68 % of trips are re-entries (R, X) | **HOLDS (more extreme)** | 60 of 62 buys are re-entries into a token he just exited: T1 33/34, T2 27/28. He farms one live token for 1.5–2 h with 28–34 round trips. |
| 24 | Re-entry within 25 slots of own sell is best (+12.8 mSOL) (R) | not testable | n = 5 (T1, −15 mSOL/trip) and n = 4 (T2, +337 mSOL/trip, driven by one +0.99 SOL trip). |
| 25 | Lanes: DIP best (+9.4 mSOL/trip), LAUNCH +13.7, DRIFT +5.0, MOMO +5.3 (R) | **CONTRADICTED on these tokens** | With the study's own definitions: <br>• T1: DIP 13 trips **+2.0 mSOL/trip** (+0.026); MOMO 8 trips +61; DRIFT 11 trips +90; LAUNCH 1 trip −62. <br>• T2: DIP 5 trips **−41.5** (−0.207); MOMO 13 +38.5; DRIFT 9 +129. <br>• By trigger side: entries behind an outside buy made +1.56 (T1) / +1.66 (T2); entries behind an outside sell lost −0.12 / −0.21. <br>The profit here is in the follow-the-buyer entries, not the dip entries. Two tokens cannot overturn a 28k-trip aggregate, but the lane ranking clearly depends on the token. |
| 26 | Not a copy-trader of leader wallets (X H1 rejected) | **HOLDS** | 23 distinct trigger wallets for 33 T1 buys (top: `ssssswdk…` 6, 8aVt 3, 9H17 3). 24 distinct for 28 T2 buys (top 3). No wallet appears on both tokens' top lists. |
| 27 | Trigger program 41Pr4XqE: 8–14× his buy rate but only 6–9 % of buys (X H1b) | holds (minor) | T1 2/33 buys (6 %, both behind wallet 8aVt via 41Pr4+6gY1o). T2 0/28. Not a driver on these tokens. |
| 28 | His followers: 2.0–2.4 wallets / 0.8–1.1 SOL within 3 slots; `ssssswdk` follows ~10 % (R) | **lower here** | Outside buys within 3 slots after his buy: T1 1.09 wallets / 0.49 SOL on average (median 1 / 0.0); T2 0.54 / 0.09. On T1, `ssssswdk` bought within 3 slots **after** 8/33 of his buys and **before** 7/33, so on T1 it is a co-trader as often as a follower. T2: 0/28. |
| 29 | Up to 25–32 open positions (X) | not testable | Consistent: 2 open at once across these tokens. |
| 30 | Slippage ~10–15 % (X, inferred) | consistent (inferred) | His 2 failed buys came after adverse moves of about +17 % and +21 % from the likely decision state to the landing state. |
| 31 | Size 0.5 SOL 10-30 18:55 → 10-31 07:00 (R) vs 480,000,000 lamports on 10-30 (X) | not testable; **the two reports disagree** | All 11-03 buys are 0.70 SOL. R says 0.5, X says 0.48; one of them is wrong. |
| 32 | Token age < 10 slots 0.026 %, 10–50 slots 0.68 % (R) | holds | T1 entry at 10 slots, no earlier attempts (not even failed ones). |

## What the study missed or got wrong (from these cases)
1. **Sells are in-slot reactions too, not just "within 1 slot".**
   - 21 of 33 T1 sells had an outside trade earlier in the **same** slot and none in the 3 slots before.
   - So the exit fires within the block, typically 30–100 positions after a sell of any size, often a tiny one.
   - Whatever feed drives his buys also drives his sells. The time-scale of exit features should be "this slot", not "1–3 slots". (Inference: a shred or pre-confirmation feed.)
2. **Lane ranking.** On these two live tokens all the profit came from entries behind outside buys (MOMO/DRIFT). DIP entries were ~0 / negative. The study's "DIP best" is an aggregate statement; it should not be read as "9pQQ is a dip bot".
3. **"Slow on dumps" needs scoping.**
   - True against us: on the one shared T1 dump we landed in the dump slot and he failed a slot later.
   - But when we are not there, he is the first buyer after the dump in 13 of 18 cases.
4. **The exit-hazard time scale.** "Buying dries up 3–10 slots" (X) is too short. On T1 the hazard peaks 10–30 s (about 25–75 slots) after the last outside buy.
5. **No stop at all, with large tails.** He held a −61 % drawdown (T2, 06:32–06:38) through 144 outside trades. The 600 s cap and the in-slot flow exit are his only protection.
6. **Tiny trades trigger his exits.** The < 0.05 SOL filter is buy-only.
7. **Selection is still unexplained**, which agrees with X's "not proven".
   - While flat on T1, he passed on 90 outside buys ≥ 0.5 SOL and 56 sells ≥ 1 SOL, and took 32 triggers.
   - Taken and skipped triggers do not differ in size, side or price vs his last exit.
8. **Owner's count.** T2 has 28 buys + 27 sells, not ~27 in total; T1 has 34 + 34.
   - The T2 activity is all from 11-03 06:00–08:00 and 11:55–12:09 PKT. He did not trade T2 on its launch day.
   - The local recorder does not track old revived coins (T2 has 0 recorded trades on 11-03), so studies built only on the recordings miss this kind of trading.
9. **Report inconsistency:** 0.5 SOL (R) vs 480,000,000 lamports (X) for the 10-30 size period.

## T1: him vs our bot (EgxfY…), one shared moment
| slot / idx | who | what |
|---|---|---|
| 464782537–540 | us | 26 pre-sent buys fail with 6042 (price not yet down to our limit) |
| 464782540 / 157 | 8GgR | sells 3.81 SOL (the dump) |
| 464782540 / 173 | **us** | **buy 0.543 SOL at MC 42.96 (in the dump slot)** |
| 464782541 / 1, 33 | 5KcK (41Pr4 bot), E2x1 | buy 1.68 and 0.36 |
| 464782541 / 85 | **9pQQ** | **buy fails 6042 (one slot late; price already rebounded)** |
| 464782541 / 185 | us | sell at MC 46.51, about +0.06 SOL gross |
| 464782634 / 95 | 9pQQ | first successful re-entry: dip-buy behind 5KcK's 1.14 SOL sell; then 33 more trips, +1.48 SOL total |

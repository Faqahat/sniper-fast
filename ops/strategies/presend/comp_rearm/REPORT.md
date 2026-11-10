# Re-arm on competitors' tokens (owner idea 10-29 ~16:25 PKT) — offline test, 10-29 PKT

Verdict: **NO for A, B and C.** None of them adds SOL on the frozen test once followers are cut 20%. Not worth an engine build.
An observatory shadow is optional and low value. The only candidate would be A3 (see the end).

MEASURED = chain tape or live records. INFERRED = replay. All times PKT. Size 0.696 SOL, TP 20%, SL 50%, live 200 ms exit.
Costs: 2.9 mSOL per trip, 5,120 lamports per landed failed try. One position, QUIET skip + stop 6:2, 40/s cap, our wallets removed.

## 1. Physics (MEASURED, 245,790 competitor buys, 10-24 -> 10-29 16h)
| bot | buys | buy SOL p50 | curve SOL p50 | own sell: delay p10/p50/p90 ms | own sell SOL p50 | price drop of own sell p50/p90 | own sell alone >= 12% | any >= 12% one-slot drop in next 10 slots |
|---|---|---|---|---|---|---|---|---|
| all | 245,790 | 0.31 | 48 | 970 / 5,768 / 32,604 | 0.47 | 2.1% / 3.4% | 0.0% | 8.3% |
| 8yYMhu | 12,795 | 0.75 | 38 | 633 / 1,529 / 12,774 | 0.76 | 3.8% / 4.8% | 0.0% | 15.9% |
| haqq | 33,760 | 0.40 | 40 | 655 / 2,697 / 12,564 | 0.38 | 1.7% / 2.6% | 0.0% | 21.3% |
| CZ77 | 619 | 1.98 | 45 | 426 / 579 / 679 | 2.06 | 8.9% / 10.9% | 3.6% | 43.0% |
| A2kcamqs | 130 | 0.81 | 37 | 517 / 604 / 739 | 0.84 | 4.1% / 7.4% | 0.0% | 22.3% |
| ssss / GKd5 / omego | 177k | 0.28-0.69 | 50 | 1.1-15.6 s median | | 1-3% | 0.0% | 2-6% |
Full table: /home/it/sniper-data/comp_rearm/phys.md
- A 12% drop needs a sell of about 6% of the curve SOL: ~2.5-3 SOL on a 40-50 SOL curve. Competitor sells are 0.3-0.8 SOL (2-4% drop). **Their own sells almost never make the 12% drop** (0.0%; CZ77 3.6%).
- Their sell is never in the buy's slot (0-3%). Median hold 0.6 s (CZ77, A2kcamqs) to 1.5-15 s (others). Most exits come after our 10-slot (2.1 s) window.
- So the 12% drops near competitor buys come from **other big sellers**, not the competitor. Most are the same whale dumps the base T2 rule already arms on.
- When more competitors pile in, drops get rarer: 1 bot in the token 14%, 4+ bots 4%.

## 2. Check against live (r37, MEASURED vs INFERRED, same 9 hours 08-16)
Live: 129 fills, curve gross +4.07 SOL, realized +2.51. Replay base: 142 fills, gross +2.50, net about +1.95. The replay is **about 22% lower than live**, so it is conservative. Earlier AMS checks: -21% (REARM2).

## 3. Results (INFERRED, 10 draws; rules picked on TRAIN 10-24..10-27, frozen on TEST 10-28 -> 10-29 16h incl. r37 hours)
Rules: A0 = any competitor buy >= 0.7 SOL. A1 = buy by 8yYMhu/haqq/HkQ7/CZ77/6VzX/A2kcamqs. A2 = A1 with <= 2 bots in the token. A3 = CZ77/A2kcamqs/6VzX only. A4 = haqq + 8yYMhu.
B0 = any competitor buy 10-40 slots after our base window on that token. B1 = B0 with the A1 bots. C1 = >= 2 bots bought in the last 2 slots. C2 = A2 + buy >= 0.5 SOL with no big sell just before.
Each rule arms a 10-slot pre-send window (8 tries/slot, limit 0.88x) at the competitor's buy (token age >= 2 slots).
Base level on TEST: +7.3 SOL/day all followers, +0.9 at -20%.

TEST, SOL/day added over today's base (lost base fills and cap pressure included):
| rule | windows/day | fills added/day | base fills lost/day | all followers [90% CI] | **-20% followers [90% CI]** | -20% w/o top 5 |
|---|---|---|---|---|---|---|
| A0 | 4,379 | 246 | 27 | +0.12 [-0.89, +1.17] | **-1.76 [-2.72, -0.76]** | -2.95 |
| A1 | 7,697 | 540 | 40 | +1.74 [-0.78, +4.17] | **-3.26 [-5.89, -0.55]** | -5.00 |
| A2 | 5,951 | 454 | 30 | +1.43 [-1.03, +3.82] | **-2.70 [-5.16, -0.16]** | -4.25 |
| A3 | 255 | 39 | 3 | +0.51 [+0.14, +0.96] | **+0.16 [-0.21, +0.63]** | -0.43 |
| A4 | 7,442 | 528 | 40 | +1.55 [-1.00, +4.07] | **-3.36 [-6.07, -0.58]** | -5.11 |
| B0 | 2,578 | 150 | 11 | +1.44 [+0.19, +2.78] | **+0.02 [-1.13, +1.23]** | -1.12 |
| B1 | 1,417 | 110 | 8 | +0.92 [-0.13, +1.99] | **-0.03 [-1.02, +0.94]** | -1.09 |
| C1 | 5,536 | 225 | 33 | -0.84 [-1.88, +0.13] | **-2.70 [-3.68, -1.81]** | -3.66 |
| C2 | 20 | 0 | 0 | -0.01 | -0.01 | -0.01 |
TRAIN looks the same (A1 +1.77 raw, -4.08 at -20%; B1 +1.52 raw, -0.20 at -20%; A3 +0.69 raw, +0.09 at -20%).

Per day at -20% (10-28 / 10-29 00-01h / r37 08-16h) and day (09-21) vs night:
- A3: -0.02 / -0.81 / +0.84; day +0.45, night -0.26.
- B0: +0.50 / -6.51 / +0.27; day +0.39, night -0.49. B1: +0.60 / -6.65 / -0.16.
- A0/A1/A2/A4/C1: negative on every test day.

Why it fails (TEST, all followers): competitor windows fill only 5-11% of the time (base T2 ~27%), and each fill earns +4 to +7 mSOL (base ~+14). Each armed window pays ~0.33 mSOL of failed tries. B windows earn more per fill (+12 to +14 mSOL) but that money is follower money: it is gone at -20%. A1/A4 triple our sends and push the 40/s cap, costing ~40 base fills/day.

## 4. Verdict per idea
- **(A) arm on competitor buys: FAIL.** -1.8 to -3.4 SOL/day at -20% (CI below 0) for every broad form. Physics says why: their sells are too small to make a 12% drop, and their exits mostly fall after our window.
  A3 (CZ77 / A2kcamqs / 6VzX only, ~255 windows, ~39 fills/day): +0.16 [-0.21, +0.63] at -20%, -0.43 without top 5. Too small and not proven.
- **(B) re-arm after our window when competitors buy in: FAIL.** About 0 at -20% (+0.02 / -0.03), negative without top 5. Like the whale re-arm (REARM2), it is follower money.
- **(C) other variants: FAIL.** Bot swarms (>= 2 bots) are worse (-2.7). Bot buys with no dump just before almost never fill.

## 5. Build / shadow?
- No engine build.
- If the owner still wants a look: a log-only observatory flag for **A3** only (arm when CZ77, A2kcamqs or 6VzX buys into a token aged >= 2 slots, 10 slots, k 8, limit 0.88x), logging would-fill and the price path. It is ~255 windows/day, so cheap. Expected value is about +0 to +0.5 SOL/day. Low priority.

## Caveats
- The 10-24..10-27 tapes lost their wallet name list. Competitor and our wallets were mapped back through matching tx signatures (mapids.py). A2kcamqs is missing on those days, and HkQ7/DYXD/DF7e are missing on some. TRAIN is slightly undercounted for them. TEST tapes are complete.
- The A2kcamqs full key is the only tape wallet with that prefix (INFERRED).
- QUIET book for the r37 hours is from 10-29 01h (slightly stale).
- Window = 10 slots, as the base. Their exits are later (median 1.5-15 s), so a longer window would cost more failed tries for drops that their sells do not make.

Files: code /home/it/sniper/ops/strategies/presend/comp_rearm/ (phys.py, phys_rep.py, mapids.py, ev.py, run.py, rep.py, calib.py, comps.py); data and tables /home/it/sniper-data/comp_rearm/ (phys.md, tables.md, res_*.pkl, comp_buys_*.pkl).

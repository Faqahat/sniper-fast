# Pre-send filter research (agent, 10-27 PKT): fills that don't break even

Owner request 10-27 ~07:30 PKT: change the pre-send setup to skip fills that can't cover their fees (flat or no-trade
fills) without removing good trades, and beat the current setup overall. Dev = AMS r24 + r25. Validation = FRA r23 + r24
(primary); AMS r19, AMS r20, FRA r21, FRA r22 (secondary). Holdout = AMS r26 (never read by the agent; tested by the main
session). Read-only; nothing deployed.
MEASURED = live records, the chain recording, or the exact replay. INFERRED = a model or scaling step.

## Short answer
**Final config "QUIET": two rules**
1. **Don't arm** when all four of these hold at the trigger:
   - no other trade earlier in the trigger's slot;
   - no wallet from the engine's bot list (`cohort_train.json`, 462 wallets) holds the token;
   - fewer than 2 of 297 known follower bots (`fbots_frozen.json`) ever traded it;
   - the whale's dumps in the last 24 h drew on average fewer than 2.24 other buyers within 2 slots, or it has no dumps.
2. **Stop the window** at trigger + 6 slots if fewer than 2 other trades (not the whale, not us) have happened since the
   trigger.

Results at the live size (MEASURED; net = realized + rent back − failed-try fees):

| | Before → after | Change | Winners removed | Losers removed |
|---|---|---|---|---|
| AMS r24 | +1.168 → +1.190 | +0.022 | 1 | 3 |
| AMS r25 | +1.042 → +1.067 | +0.025 | 3 | 5 |
| **Dev total** | **+2.210 → +2.257** | **+0.047** | **4 (+0.070 SOL)** | **8 (−0.088 SOL)** |
| FRA r23 + r24 | +0.598 → +1.407 | +0.809 | 9 (+0.079) | 43 (−0.850) |
| **All 6 validation runs** | **+1.077 → +2.499** | **+1.422** | **11 (+0.125 SOL)** | **70 (−1.481 SOL)** |

- Every one of the 8 runs gets better.
- At 0.50 SOL: dev +0.046 (exact replay), validation about +1.80 (INFERRED by scaling).
- No-trade fills removed: 2 of 32 on dev, 30 of 57 on validation.

**It could not beat the current config without removing some winners.**
- The only config with zero winners removed anywhere is **C5a**: stop at +6 slots if no other wallet traded at all.
  It gives dev +0.009 and validation +0.176.
- The strictly pre-registered pick is **C5** alone: dev +0.017 (1 winner, +0.011) and validation +0.417 (7 winners,
  +0.115).
- QUIET was assembled after the first look at validation, so its validation number is optimistic. Its four signals and
  the stop rule were fixed before; the 24 h history window and the combination came after.

**The owner's competitor hypothesis:**
- **Rival pre-senders: no.** 22 rival pre-sender wallets try on about half our windows, but our fills are no better or
  worse when they are there (+0.0078 vs +0.0086 SOL per fill).
- **Follower bots: yes.** Tokens that no follower bot watches lose, at least in the validation hours.

**Confidence: medium.**
- On validation the effect is clearly real: the removed fills lose versus random fills with p < 0.0001, and 22 of 28
  one-hour blocks get better (3 worse).
- On dev it is noise-level (p = 0.10). On AMS 24/25 the quiet-token fills roughly broke even, so the gain depends on the
  market period.

## 0. Pre-registration
The scoring rule and pass bar are in the `score.py` docstring, written at 10-27 07:21 PKT before any filter was tried.
- **Unit:** one armed window.
- **Score:** fill realized + rent back − failed-try fees, MEASURED at the live size.
- **Winner:** realized + rent back > 0.
- **Pass bar:**
  1. Dev improves, and neither dev run gets worse.
  2. Winners removed are worth less than what is saved.
  3. Validation improves, on the primary pair and pooled.
  4. Robustness: leave-one-run-out, time blocks, and a permutation test with p < 0.05.
  5. Simple monotone rules, with the number of configs reported.
  6. Results at 0.34 and at 0.50 SOL.
- `lv.py` refuses AMS r26 files.

## 1. What is knowable when (MEASURED, `check_time.py`)
- **Arm rule:**
  - It reads only chain rows strictly before the trigger transaction, plus the trigger itself.
  - The whale's dump history uses only dumps closed (dump slot + 2) before the trigger slot: 105,663 of 105,663.
  - The engine arms on the trigger's arrival. The first try goes out 50.9 ms later (p1 50.4, p99 421 ms).
- **Stop rule:**
  - It uses each try's logged `pos`, the engine's own record of the latest token trade it had seen when it signed that
    try.
  - 0 of 78,284 tries have a `pos` after their own send slot.
  - 665 of 665 filling tries were decided before our fill.
- **Labels** (trades after our buy) are only used to score outcomes, never in a rule.

## 2. Results and robustness
`final_table.py` prints per-run tables for C5a, C5 and QUIET.
- **FRA r22:** the double-fill window w51 (engine P&L wrong) is removed by none of the configs, so its error does not
  change any gain.
- **QUIET robustness:**
  - Permutation test: dev p = 0.10 (12 fills removed; fails the pre-registered p < 0.05), FRA r23+r24 p = 0.0001, all
    validation p < 0.0001.
  - One-hour blocks: 22 better, 3 worse, 3 same (dev 8 better, 2 worse).
  - All 8 runs better.
  - Whale-history window from 1 to 24 h: validation +1.15 to +1.36, dev −0.02 to +0.14.
- **C5 neighbours** (stop at +N slots if fewer than M other trades): positive on validation for every N from 4 to 8 and M
  from 1 to 3. On dev the range is −0.17 to +0.02.
- **Second-order effect:** only 3 live "blocked_armed" triggers (AMS r24) fall after a C5 stop on the same token and
  could have armed instead.

**Frozen candidates** (`rules.py`, frozen 07:54 PKT): dev change / all-validation change / winners removed on validation

| | Rule | Dev | Validation | Winners removed (val) |
|---|---|---|---|---|
| C1 | send tries only after ≥ 2 other trades | +0.088 | +0.757 | 27 |
| C2 | skip if last trade before trigger is > 5 slots old | +0.172 (r25 −0.186) | +0.967 | 14 |
| C3 | skip if no trade in 50 slots before trigger | +0.099 (r25 −0.087) | +0.041 | 6 |
| C5 | stop at +6 slots if < 2 other trades | +0.017 | +0.417 | 7 |
| C8 | skip if no cohort or follower bot ever traded it | +0.013 (r25 −0.176) | +1.115 | 39 |
| C10 | skip if 3+ quiet signals and whale buy < 3 SOL | +0.005 (r25 −0.161) | +0.751 | 15 |
| C11 | skip if all 4 quiet signals | −0.018 | +1.284 | 7 |

C5 is the only frozen candidate that passed bars 1–3; bar 4 fails on dev (too few removed fills: p = 0.28).

**Configs tried:** about 335 on dev; 34 were looked at on validation (7 frozen, 3 post-hoc, 3 combinations, 6 history
windows, 15 C5 neighbours).

## 3. Tried and failed (dev unless noted)
- **Single arm-time features** (208 configs): they remove about equal SOL of winners and losers. Some help one dev run and
  hurt the other.
- **Bot-attention score ≥ 3:** −0.169.
- **Waiting for activity before sending tries:** at best +0.088, and that removes 25 winners.
- **Rival pre-senders present:** no difference in outcome. A rule that only sends once a rival is seen loses −0.72.
- **Competitor failed-transaction activity:** weak (+0.0106 vs +0.0025 SOL per fill), and the engine cannot see others'
  failed transactions today.
- **On-chain checks:**
  - the whale's balance at our fill: no separation;
  - dumps of only 12–14%: about 0 net over 59 fills, with 24 winners among them.
- **Logistic model on 26 features:** held-out AUC 0.63–0.66, but skipping the bottom 10–30% gains nothing.
- **Exits** (36 configs, exact replay):
  - no take-profit: +0.26 (r25 −0.09);
  - exit one slot earlier: +0.03;
  - exit one slot later: −0.57;
  - none helps both dev runs.
- **Cheaper, slower time-exit sells:** landing 212 ms later costs about 1.1 mSOL per exit, about the 1.2 mSOL tip saved. No
  gain.
- **Pausing after losing streaks:** no gain.
- **Leader-client filters:** every client is positive per fill.
- **Lead only, not validated:** size 1.00 SOL on high-attention tokens and 0.50 on the rest gives dev +0.77/+0.84 in the
  replay (INFERRED). There is no replay for the FRA runs, so it could not be validated.

## 4. Engine change list (not edited; owner OK needed)
1. **Stop rule** (`pslive.rs`):
   - Add `others: u32` to `Win`.
   - In `on_exec`'s armed-window block, increment it when `e.user != w.whale && e.user != self.user`.
   - In `tick()`, disarm the window with reason `"quiet"` when `slot_now >= w.trig_slot + N && others < M`.
   - New flag `--presend-live-quiet-stop 6:2`.
2. **Arm rule:**
   - Change `presend_live::Detector::trade` to return the token's previous `last_slot` and expose its wallet map.
   - Load the cohort list (already loaded by the engine) and a new list `--presend-live-fbots /root/dip/fbots_frozen.json`.
   - Add a new global DumpBook:
     - a dump is a sell ≥ 0.3 SOL with the curve under 100 SOL and post price ≤ 0.92 × pre price;
     - after each dump, collect the distinct buyers other than the seller over the next 2 slots;
     - keep each seller's history for 24 h.
   - In `trigger()`, add skip reason `"quiet"` when all four signals hold.
   - New flags `--presend-live-quiet-skip on`, `--presend-live-quiet-hist-h 24`, `--presend-live-quiet-fol 2.24`.
   - Log the four signal values in the arm and skip records.
3. **Latency:** none on the send path.
   - The trigger check scans the token's wallets: roughly 10 µs.
   - The DumpBook update is O(1) per trade.
   - Memory is under 5 MB for 24 h.
4. **Risks:**
   - **Engine start:** the dump history starts empty. Proposal: keep the arm rule off for the first 60 minutes. With no
     history it acts like a 3-signal rule that removed 26 validation winners.
   - **Arrival order:** the engine sees trades in arrival order; the replay used chain order.
   - **Aging lists:** the frozen bot lists (10-23 and 10-25) will age.
   - **Other region's wallet:** the replay counted both AMS and FRA wallets as ours; the engine knows only its own.
   - **Market period:** on AMS 24/25 the rule is about neutral.

## 5. Files
- **Code:** this folder
  - `apply_filter.py`, `rules.py`, `sim.py`, `score.py`, `lv.py`, `feat.py`, `chainlib.py`;
  - pipeline: `g1`, `g2`, `g2b`, `e1`, `f1`–`f3`;
  - analysis: `a1`–`a3`, `x2`–`x9`, `v1`–`v4`, `check_time.py`, `final_table.py`, `fbots_frozen.json`.
- **Data:** `/home/moiz/sniper-data/presend_filter/`, 2.2 GB. The 35 GB of intermediate chunks were deleted.
- **Holdout test command:** `python3 apply_filter.py --run ams:r26 --list`, run by the main session.

## 6. Main session's own test (10-27 ~08:15 PKT, `apply_filter.py --list`, MEASURED at each run's live size)
Reproduced the dev numbers exactly, then ran the holdout AMS r26 (06:59 → ~08:15 PKT, 0.50 SOL, 35 pre-send fills;
9 of 155 triggers were not yet on the chain recording and were kept as live).

| Run | C5a (no winner ever removed) | C5 | QUIET |
|---|---|---|---|
| AMS r24 | +0.0065 (0 winners removed) | +0.0125 (0) | +0.0220 (1 winner +0.038, 3 losers) |
| AMS r25 | +0.0023 (0) | +0.0041 (1 winner +0.011) | +0.0254 (3 winners +0.033, 5 losers) |
| **AMS r26 holdout** | **+0.0144 (0)** | **+0.0158 (0)** | **+0.0925 (1 winner +0.061, 7 losers −0.145)** |
| Total of the three | +0.023, 0 winners removed | +0.032, 1 winner | +0.140, 5 winners (+0.131) |

- On the holdout QUIET raised pre-send net from +0.300 to +0.392 (+31%); C5 and C5a removed no winner there.
- The owner's strict rule (never remove a good trade) is met only by C5a, and its gain is small.

## 7. Daily estimate with QUIET, 24/7 on one server (main session, 10-27 ~15:30 PKT)
Basis: every live pre-send window of the 9 runs AMS r19, r20, r24, r25, r26 and FRA r21–r24 (10-25 22:22 → 10-27 14:03 PKT;
25.3 active pre-send hours, 808 fills). Net = realized + rent back − failed-try fees, at each run's live size (0.34–0.50, average
about 0.40). Code `daily/` (perwin8.py, perwin26.py, daily.py), data `/home/moiz/sniper-data/presend_filter/daily/`.

| | Without QUIET (MEASURED live) | With QUIET (exact replay of the same live fills) |
|---|---|---|
| Pooled, per 24 h | +3.35 SOL | +5.21 SOL |
| Weighted by hour of day (14–16 and 20–22 PKT not covered) | +3.40 | +5.04 |
| One-hour-block bootstrap p10 / p50 / p90 | +2.0 / +3.5 / +4.9 | +3.8 / +5.2 / +6.5 |
| Night 10-25/26 (r19–r23, incl. 40 min both servers) | +1.09 /day | +4.94 /day |
| Day 10-26 16–20 (FRA r24) | +4.84 | +6.40 |
| Night 10-26/27 (AMS r24, r25) | +7.40 | +7.56 |
| Day 10-27 07–14 (AMS r26, 0.50) | +0.85 | +2.49 |

- QUIET's gain by role: dev +0.16/day, validation +3.09/day (optimistic: rules set after a first look), holdout +1.65/day.
  The conservative case (the pre-registered C5 alone on validation) is +4.25/day.
- **Realistic planning figure: about +4 to +5 SOL/day at ~0.40 SOL** (INFERRED: per-day scaling of ~1 day of history).
- At 0.50, linear scaling says +6.9/day (INFERRED, not proven). The only 0.50 run was the weakest stretch, and bigger buys
  price out followers.
- Regular M2 buys since 10-26 16:10 ≈ 0 overall (FRA −0.66, AMS about +0.7); not counted.
- Biggest risk: followers. In the AMS 24/25 replay, 20% fewer later buyers cut pre-send from +1.93 to +0.21.
- Fills about 770/day before QUIET and ~650 with it, so the 1000-fill cap fits a day.
- Failed-try fees about 0.46/day, so set the fee budget to at least 0.5 for a 24 h run.

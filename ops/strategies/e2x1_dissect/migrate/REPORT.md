## 12-line summary

1. **Best rule (stated exactly):** non-mayhem pump.fun token; trigger = the first curve buy that takes vSOL to ≥105 without completing the curve; score it with a depth-4 GBDT for "curve completes within 30 s" (84 causal features: vSOL, SOL left, age, 1–120 s flow, holder/dev/buyer-wallet history, hour) and enter only if **p30 ≥ 0.8**; buy **2 SOL** (pre-sent tries armed at vSOL ≥100 with a Lighthouse assertion vSOL ∈ [105,115], or reactive with +5 % guard); if the curve completes, **sell everything into PumpSwap 2 slots after the migration tx**; otherwise sell on the curve at **−20 % mark-to-market or after 120 s**.
2. **Numbers (pre-send 2 SOL, −20 % stop):** train +2.56 SOL/day [90 % CI +1.5, +3.8], test **+2.54 [+1.0, +4.2]**, test days +1.4 / +3.7, +1.2 without top-5 trades, 28 entries/day, 95 % of entries graduate, +0.092 SOL per trade (4.6 %); with the predictor-drop stop train +2.95 / test +3.19 [+1.4, +5.0].
3. **Reactive (no engine change):** 2 SOL −20 % stop train +2.85 / test +1.73 [+0.3, +3.3]; with predictor-drop stop train +3.21 / test +2.64 [+1.0, +4.1] (passes the bar). 1 SOL versions ≈ half.
4. **Variants tried: 79,200** (+1 landing-speed replay). The pre-registered best-on-train (react 2 SOL, V=100, p120≥0.6, mig+100) makes +8.7 train / +10.2 test but CI [−5.9, +31] and −5.6 without top-5 → **fails**; all top-12-on-train are mig+100 fat-tail variants.
5. **Honesty:** the headline cell was chosen after seeing test. Its support: every neighbour (V 95–105, 0.5/1/2 SOL, threshold 0.8–0.9, react/pre, −20 % or predictor stop, mig+0/+2) is positive on both periods; looser thresholds (0.6/0.7), the 2-min model, V=108 and no-stop are not. 46 of 186 train-robust top-200 variants pass on test. Needs a ≥3-day forward paper run.
6. **Predictor:** test AUC 0.868 (30 s), 0.786 (2 min), 0.713 (10 min); calibration good below 0.5, over-confident at the top (0.88 → 0.79). Within V=105 AUC only 0.73: the lift is mostly "where the curve is and how fast it moves" (vSOL, SOL left, age, buys); wallet-quality features add little.
7. **EV threshold:** measured G/L per entry gives p* ≈ 0.87 (V=105, −20 % stop), 0.77–0.82 (V=100), 0.68–0.73 (V=95); only the 30-s model reaches those reliably.
8. **Entry mechanics:** at V=105 reactive fills 82 % (11 % land after completion, 7 % guard reverts); pre-send fills 86 % (54 % of fills from resting tries, guard reverts 2.4 %), recovers only 1.5 pts of the "completed before we land" cases (same-slot completions); 95 landed tries per arm at the measured 0.005 mSOL each (0.3 mSOL/try would cost just −0.14/day). The 49 % self-completing crossings stay unreachable.
9. **Exits:** premium is the step — mig+0/+2 capture it (+0.11 per 1 SOL graduated entry at V=105); mig+100 only looks better on test (post-open pumps, CI includes 0). 34–35 % of graduated entries open below our entry (sniped/dumped at open). No stop → train CI includes 0; −10 % stop kills graduated P&L.
10. **Speed:** at 35 ms landing the same rule is ~+40 % better (react 1 SOL: +3.1/+2.7 vs +2.2/+1.8) — helpful, not required.
11. **Caveats:** our 2 SOL completes the curve itself in 7 % of entries (modelled as graduated); the other 93 % assume the completing buyer still comes; pool sell landing on a dumped open is modelled at 66 ms only; continuation model is in-sample on train (test is OOS); recorder blind spots as in grad.
12. **Paper rule:** steps 1–5 above, log landing vs crossing, fill vSOL, migration slot, pool reserves at sell, fill vs replay; pass = ≥ +1.5 SOL/day over 3 days with each day ≥ 0. No live sends made; nothing deployed.

---

# MIGRATE: our own near-graduation strategy (agent migrate, 10-28 ~17:30 PKT)

Code: `/home/moiz/sniper/ops/strategies/e2x1_dissect/migrate/` (`m0_wallets.py` wallet history, `m1_features.py`, `m2_model.py` predictor, `m3_sim.py` replay, `m4_report.py` variant grid, `m5_ev.py` mechanics/EV, `m6_examples.py`, `mlib.py`). Data/logs: `/home/moiz/sniper-data/e2x1_dissect/migrate/` (feat.pkl, feat_p.pkl, wallets.npz, sim_*.pkl, m2/m4/m5/m6/m7_family/m8_headline logs; 355 MB). Reuses grad's decoded tape (all curve trades of every token that reached 78 vSOL + all PumpSwap events; pool reserve derived from trade amounts). Train = 10-24..10-26 PKT, TEST = 10-27/10-28; nothing chosen on test except where stated. M = measured on the tape, I = inferred/modelled. **Variants tried: 79,200** (6 entry modes×sizes × 6 V × 2 re-entry × 13 selection thresholds × 75 exits) plus one 35 ms landing sensitivity replay.

## 0. Result in one paragraph

A graduation predictor works (test AUC 0.87 for "completes within 30 s"), and buying at vSOL ≥105 only when it says ≥0.8 turns the grad agent's losing universe into a small, steady earner: **pre-send 2 SOL, sell 2 slots after migration, −20 % curve stop / 120 s timeout: train +2.56 SOL/day [90 % CI +1.5, +3.8], test +2.54 [+1.0, +4.2], both test days positive (+1.4, +3.7), +1.2 without its top-5 trades, 28 entries/day, 95 % of entries graduate, +0.092 SOL per trade (4.6 %).** The reactive version (no engine change) makes train +2.85 / test +1.73 [+0.3, +3.3] with the −20 % stop and train +3.21 / test +2.64 [+1.0, +4.1] with the predictor-drop stop. This passes the pass bar, BUT the (p30, 0.8, mig+2, 2 SOL) cell was picked after seeing test: the pre-registered best-on-train variant (react 2 SOL, V=100, p120 ≥0.6, mig+100) makes +8.7 train / +10.2 test with a test CI [−5.9, +31] and −5.6 without its top-5 trades, so it fails. What supports the headline rule is that every neighbour (V 95–105, 0.5/1/2 SOL, threshold 0.8/0.9, react/pre, −20 % or predictor stop) is positive on both periods (section 5). It needs a forward paper run before any live use.

## 1. Universe and the "can't enter" problem (M)

Entrable moment = a curve buy that takes vSOL to ≥V without completing the curve. First crossings per V over the 5 days: 3,513 (V=85) … 2,585 (V=108).

| V | first crossings | crossing trade itself completes (not entrable) | reactive fill | lands after completion | guard revert | entries that graduate |
|---|---|---|---|---|---|---|
| 85 | 3,513 | 33 % | 73 % | 11.5 % | 15.5 % | 46 % |
| 95 | 3,051 | 41 % | 82 % | 10.8 % | 7.2 % | 61 % |
| 100 | 2,860 | 44 % | 82.5 % | 10.8 % | 6.7 % | 69 % |
| 105 | 2,669 | 49 % | 82 % | 11.1 % | 6.7 % | 80 % |
| 108 | 2,585 | 52 % | 80 % | 14.8 % | 5.1 % | 85 % |

- Of the graduating entrable crossings at V=105, 22 % complete within 1 slot, 57 % within 30 s, 81 % within 2 min (median 19 s). At V=100: 21 % / 45 % / 70 %.
- Our own 2 SOL buy completes the curve itself in 7 % of V=105 entries (4 % at 1 SOL); the sim then treats us as graduated (we are in; pool reserves are fixed by the program).
- SOL left to complete at V=105: median 9.4 SOL.

## 2. Graduation predictor (m2, M on test)

Rows: 21,836 entrable, non-edge crossings (first + re-crossings), 84 causal features: V, vSOL, SOL left, flow 1/5/10/30/120 s (net, buy, sell, #buys, #sells, unique buyers, max buy), token age, time since 50/80 vSOL, drawdown from max, holder top-1/top-5 share, dev share, dev sold, create-slot sniper share, creator's prior tokens / prior near-grad / prior graduations, buyer quality of the last-10 s buyers and of the current holders (prior trips, prior P&L, prior near-grad graduation rate, pool-open-bot count, completer-bot count; trips count only once resolved before the entry time, the current token's own trip excluded), PKT hour, weekday. Pool-ATA pre-creation is not in the tape (proxied by "known pool-open bots holding now"). GBDT = sklearn HistGradientBoosting depth 4; train probabilities are out-of-fold by day.

| label | base rate test | AUC train (OOF) | AUC test | AUC test within V=100 / 105 / 108 |
|---|---|---|---|---|
| completes within 30 s | 21 % | 0.875 | **0.868** | 0.81 / 0.73 / 0.71 |
| within 2 min | 39 % | 0.805 | 0.786 | 0.68 / 0.66 / 0.65 |
| within 10 min | 57 % | 0.727 | 0.713 | 0.63 / 0.63 / 0.59 |

- Calibration on test (30 s): decile means 0.005→0.002 … 0.341→0.333, 0.532→0.438, 0.880→0.785: slightly over-confident at the top. 2-min model top decile 0.939→0.837.
- Most of the lift is "where the curve is and how fast it moves": permutation importance (2-min label, scored on 10-26): vSOL +0.045, SOL left +0.026, age +0.026, n_buys +0.008, dev prior tokens +0.008, known-wallet holder share +0.007, hour +0.006, dev share +0.006, then 120 s flow. Wallet-quality features help only marginally.
- Depth-4 rules (2-min label; train rate → test rate): vSOL >100.85 & time since 50 vSOL ≤190 s & 5 s buy >75 SOL & drawdown >1.20 → 100 % (524) → 100 % (267); same but 5 s buy ≤75 & vSOL >106 → 83 % → 78 %; vSOL ≤100.85 & age >240 s & vSOL ≤96 → 10 % → 10 %; vSOL >100.85 & slow (t50 >190 s) & ≤4 buyers in 10 s → 19 % → 23 %. Rules-only AUC on test 0.785.
- EV threshold (m5, react 1 SOL, sell mig+2, train): mean P&L per graduated entry G and per failed entry L give p* = L/(G+L): V=105 no stop/120 s G +0.070 L −0.52 → p* 0.88; −20 % stop/120 s G +0.046 L −0.31 → p* 0.87; −10 % stop G +0.017 L −0.20 → p* 0.92. At V=100: 0.77–0.82. At V=95: 0.68–0.73. The 2-min model rarely reaches these (its 0.94 top decile realises 0.84), which is why the 30-s model, used at 0.8, is the one that works: it isolates tokens whose completion is seconds away.

## 3. Entry mechanics at our speed (m5, 1 SOL, first crossings)

| mode | V | fill | late (completed before we land) | guard revert | pre-send miss | share of fills from pre-sent tries | mean fill vSOL | landed tries / arm |
|---|---|---|---|---|---|---|---|---|
| react | 105 | 82.2 % | 11.1 % | 6.7 % | – | – | 106.5 | 0 |
| pre (arm V−5, 5 tries/slot, window [V, V+10], 47 slots) | 105 | 86.4 % | 9.6 % | 2.4 % | 1.6 % | 54 % | 106.8 | 95 |
| react | 100 | 82.5 % | 10.8 % | 6.7 % | – | – | 102.0 | 0 |
| pre | 100 | 86.2 % | 10.1 % | 2.3 % | 1.3 % | 52 % | 102.3 | 89 |

- Pre-send (tries evenly spaced in the slot; fill = first try that lands while the curve is in [V, V+10] and not complete) adds ~4 pts of fill, mostly by removing guard reverts; it recovers only 1.5 pts of the "completed before we land" cases, because those completions sit in the same slot a few indexes after the crossing, or the V−5 and V crossings are the same trade (then the first try lands like a reactive buy). It does not touch the 49 % self-completing crossings (atomic).
- Try cost: measured 0.005 mSOL per landed-and-reverted try (FRA r27: 0.863 mSOL / 169 tries per fill; the tip is paid only on a fill). At 95 tries per arm that is 0.5 mSOL per entry. With the brief's 0.3 mSOL per try the headline rule drops from +3.19 to +3.05/day (test), i.e. still fine (short windows).
- Engine note: our pre-send attempt already carries a Lighthouse slot-deadline assertion (`src/presend_live.rs`); the "vSOL in [V, V+10]" condition is one more Lighthouse account-data assertion on the bonding curve (I: small build change, not done here).
- Size: 0.5 / 1 / 2 SOL fill 0.47 / 0.94 / 1.88 % above spot at V=105 and the pool sell costs 0.7 / 1.4 / 2.7 % impact; P&L scales almost linearly with size up to 2 SOL (section 5), so 2 SOL is more exposure, not a better edge. Not tested above 2 SOL.
- Landing speed: at 35 ms median instead of 66 the same rule (react 1 SOL, V=105, p30 ≥0.8, mig+2, pd stop) goes from +2.17/+1.78 to +3.13/+2.74 (train/test). Speed helps ~+40 % but is not required for a positive result.

## 4. Exits (M)

- Graduated entries, react 1 SOL, V=105, no stop: mean P&L per entry at mig+0 / +2 / +5 / +20 / +100 = +0.110 / +0.110 / +0.103 / +0.102 / +0.112 on train but +0.119 / +0.126 / +0.125 / +0.115 / +0.129 on test; V=100: +0.200 / +0.200 / +0.195 / +0.194 / +0.200 (train) vs +0.212 … +0.256 (test). The premium is the step; mig+2 captures it (the pool-open buys of the first slots, median 13 buys / 32 SOL, are already in the price at mig+2).
- mig+100 (21 s after migration) is where every "best on train" variant lands and where test explodes (+10 to +16/day) with CIs that include 0 and negative without top-5: that is the post-open pump of a few tokens on the test days, not the premium. We do not rely on it.
- Pool-open sniped share (price at mig+2 below the open price) among graduated entries: 34–35 % for the headline rule (28–31 % over all V).
- Failure exits (headline rule, pre 2 SOL, test): no stop −1.33/day on failed entries, −20 % stop −0.36, predictor-drop (continuation model P(complete within next 120 s) <0.3 at 10/20/30/60/120 s checkpoints) −0.78 but higher graduated P&L (it also sells slow graduators early at a small gain). −10 % stops cut graduated P&L too much (p* 0.92–0.98).

## 5. Variant grid, choice on train, test (m4/m7/m8)

Pre-registered pick = best train SOL/day over all 79,200 variants: **react 2 SOL, V=100, re-entry, p120 ≥0.6, mig+100, predictor stop 0.3, 600 s**: train +8.68/day [+2.2, +15.5], test +10.15 [−5.9, +31.0], −5.56 without top-5, 127 entries/day. **Fails the bar (CI, concentration).** The other 11 of the top-12 on train look the same: mig+100 exits, fat tails. Choosing by train lower-CI instead gives react 2 SOL V=105 p120 ≥0.8 mig+100: test +2.83 [−4.5, +10.4], also fails.

Of the 200 best-on-train variants, 186 are "train-robust" (train CI >0 and every train day >0); 46 of those also pass the test bar. All 46 are V=100–105, p30 ≥0.7–0.8 (the 30-s model), 2 SOL, mig+100. Restricting to the premium exit (mig+2) gives the family below (first crossings, V=105, p30 ≥0.8, sell mig+2, 120 s timeout; SOL/day, 90 % CI, (without top-5), per day):

| mode / size | stop | train | test | test days | entries/d | graduate | per trade |
|---|---|---|---|---|---|---|---|
| react 0.5 | −20 % | +1.13 [+0.8,+1.5] (+0.9) | +0.67 [+0.2,+1.1] (+0.4) | +0.4 / +1.0 | 23 | 94 % | +0.029 |
| react 1 | −20 % | +1.97 [+1.4,+2.6] (+1.5) | +1.24 [+0.4,+2.1] (+0.7) | +0.7 / +1.8 | 24 | 94 % | +0.053 |
| react 2 | −20 % | +2.85 [+1.8,+4.0] (+2.0) | +1.73 [+0.3,+3.3] (+0.7) | +0.6 / +2.9 | 24 | 94 % | +0.073 |
| react 2 | pd 0.3 | +3.21 [+2.3,+4.3] (+2.4) | **+2.64 [+1.0,+4.1] (+1.6)** | +1.4 / +3.9 | 24 | 94 % | +0.112 |
| pre 1 | −20 % | +1.82 [+1.2,+2.5] (+1.4) | +1.71 [+0.8,+2.6] (+1.0) | +1.2 / +2.2 | 28 | 95 % | +0.062 |
| pre 1 | pd 0.3 | +2.04 [+1.5,+2.7] (+1.6) | +2.12 [+1.2,+3.1] (+1.4) | +1.4 / +2.9 | 28 | 95 % | +0.077 |
| **pre 2** | **−20 %** | **+2.56 [+1.5,+3.8] (+1.8)** | **+2.54 [+1.0,+4.2] (+1.2)** | +1.4 / +3.7 | 28 | 95 % | +0.092 |
| pre 2 | pd 0.3 | +2.95 [+2.0,+4.1] (+2.2) | +3.19 [+1.4,+5.0] (+1.9) | +1.8 / +4.6 | 28 | 95 % | +0.116 |
| pre 2 | none | +1.56 [−0.5,+3.4] (+0.8) | +2.84 [+0.6,+4.8] (+1.5) | +0.7 / +5.0 | 28 | 95 % | +0.103 |

Train days for pre 2 / −20 %: +1.9, +4.4, +1.4 (worst +1.4). Graduated P&L +2.91/day vs failed −0.36 (test). Top-5 test trades = +2.65 of +6.39 total (pd variant). Neighbours (react 2 SOL, −20 %, mig+2): V=95 train +2.33 / test +2.15 [+1.4,+2.9] (12/d), V=100 +2.44 / +2.16 [+1.3,+3.0] (12/d), V=108 +0.79 / +1.53 [−0.3,+3.3]; threshold 0.9: +2.51 / +1.63 [+0.8,+2.4] (14/d); threshold 0.6: +2.51 / −0.43; 2-min model at 0.8: +0.98 / −1.22 (57/d), at 0.9: +1.12 / +2.08. So: V 95–105, 30-s model ≥0.8–0.9, premium exit, any size — positive on both periods; looser thresholds or the 2-min model — not.

**Pass bar (≥+2/day test, CI excluding 0, each test day positive, train ≥0):** passed by pre 2 SOL −20 % (+2.54), pre 2 SOL pd0.3 (+3.19), react 2 SOL pd0.3 (+2.64), pre 1 SOL pd0.3 (+2.12); failed on the +2 level (not on sign) by react 2 SOL −20 % (+1.73) and every 0.5/1 SOL −20 % cell.

Test examples (pre 2 SOL, V=105, p30 ≥0.8, mig+2, pd0.3; expected P&L over 10 landing samples):
- +0.758 [GFrEnNVc](https://gmgn.ai/sol/token/GFrEnNVcq8hRJSfovDZzJHKiSMwf6zMqc1g5DZ8pump) 10-28 03:29 PKT, p 0.93, completed 1 slot later.
- +0.703 [JDzUd2tc](https://gmgn.ai/sol/token/JDzUd2tcvsijFkjZNEChkxvPAzK5kJpsWBuEAEmopump) 10-28 01:28, p 0.81, completed 5.5 s later.
- +0.504 [AR81dQhB](https://gmgn.ai/sol/token/AR81dQhBwnRkPx37vGQkUQvzYfewZrzxHrTRQNdgpump) 10-27 07:25, p 0.84, 2 slots.
- +0.329 [8Pfnwe4Q](https://gmgn.ai/sol/token/8Pfnwe4QabMZSdo5PuSnmG99tyoUiTpr6cPAsKvdpump) 10-27 21:21, p 0.81, 1.9 s.
- −0.285 [7cmnCXuv](https://gmgn.ai/sol/token/7cmnCXuvhPm5khhNwmi6MF7uecFdTYQf4STqq1Xopump) 10-27 21:33, p 0.94, never completed (stop).
- −1.222 [7yHQxj8H](https://gmgn.ai/sol/token/7yHQxj8H1z5A1LMTTHZoziZxbqsTUWzpftDG4v6Cpump) 10-27 21:16, p 0.83, never completed; crashed before the first checkpoint (worst test trade).
- −0.450 [EWvJizG3](https://gmgn.ai/sol/token/EWvJizG3mwr3U4Z2UwXUgFuKsyFvaH5tnxDh1cXqpump) 10-28 06:45, p 0.91, graduated after 19 s but the pool opened below our entry (dumped at open).

## 6. Honest caveats

1. **Post-hoc cell.** The pre-registered train pick fails; the headline cell was chosen after looking at test. Its defence is the neighbourhood (section 5) and that it is the simplest reading of the EV analysis (only the 30-s model reaches p* ≈0.87 at V=105). Two test days, ~55 trades: a forward paper run of ≥3 days is the real test. Expectation if real: +1.5 to +3 SOL/day at 2 SOL, 25–30 trades/day.
2. **What we are doing:** buying the last ~10 SOL of a curve seconds before someone else completes it, and selling the graduation step into the pool. 5 % of entries never complete and cost −0.3 to −1.2 SOL each; the stop is what keeps the strategy positive (no stop: train CI includes 0).
3. **Our buy changes the completion** (7 % of entries at 2 SOL complete the curve themselves). Modelled as graduated with the real pool; fine for us, but the other 93 % assume the completing buyer still comes after our 2 SOL raised the price ~1.9 % — reasonable at this distance (I).
4. **Competition:** 49 % of V=105 crossings are self-completing bundles we never see; pool-open buyers (13 buys / 32 SOL in 5 slots) sit in front of our sell, and 34–35 % of our graduated entries open below our entry price. Both are in the replay (real pool state at our sell), but the pool sell landing is modelled with the same 66 ms distribution; a late pool sell on a dumped open costs more than modelled.
5. **Pre-send** needs the vSOL-range Lighthouse assertion (engine change) and 5 landed tries/slot (COVERAGE.md says a window really gets 4–6); reactive gives +1.7 to +2.6/day without any engine change.
6. The continuation model (pd stop) is in-sample on train days (its test numbers are out-of-sample); the −20 % stop variant has no such issue and is the one quoted as the headline.
7. Recorder blind spots as in grad (3.5 % version-1 txs missing; 48 completions without a recorded migration excluded; recording-edge rows excluded).

## 7. Paper rule to test (not started; owner OK needed)

1. Non-mayhem token; trigger = first curve buy that takes vSOL to ≥105 without completing the curve.
2. Score with the 30-s GBDT (m2 features; re-fit with the same code on data up to the run start); enter only if p30 ≥ 0.8.
3. Buy 2 SOL reactive with +5 % guard (phase 1); phase 2 = pre-sent tries armed at vSOL ≥100 with a Lighthouse assertion vSOL ∈ [105, 115].
4. If the curve completes: sell everything on PumpSwap 2 slots after the migration tx (pre-build the sell on seeing the CompleteEvent).
5. Else: sell on the curve at −20 % mark-to-market or after 120 s.
6. Log: landing slot/index vs the crossing trade, whether we landed before completion, our fill vSOL, migration slot, pool reserves at our sell, fill vs replay.
Pass on paper: ≥ +1.5 SOL/day over 3 days with each day ≥ 0 and the replay of the same days within 30 % of paper.
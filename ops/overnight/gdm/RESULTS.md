# GDM: our own generic-demand selection model vs FINAL-2

2026-10-23, times PKT (UTC+5). Research only, offline replay; nothing was traded. **MEASURED** = replay or data; **INFERRED** = reasoning.

## Update 10-23 09:30 PKT: a third, unseen window went against GDM

I checked a third, unseen window: launches created 05:35–09:10 PKT, 3.6 h. It is after the training table ended and was never used for training or selection. It was scored with the frozen file through the new forward pipeline (MEASURED). Totals in SOL at pro costs, 8 s hold:

| List | Fills/tries (45 ms) | 45 ms, pro buys after us removed | 45 ms, all sniper buys removed | 75 ms | 30 ms |
|---|---|---|---|---|---|
| FINAL-2 live picks | 37/81 | **+0.79** | +0.58 | +1.23 | +0.87 |
| GDM, LM model | 51/79 | **−0.58** | −0.93 | −0.47 | −0.35 |
| GDM, L model (no metadata) | 50/78 | −0.95 | −1.29 | −1.02 | −0.62 |
| UNION, FINAL-2 + GDM LM | 85/151 | **−0.56** | −1.09 | −0.01 | −0.70 |

- In this window GDM lost and pulled the union below FINAL-2. The loss is broad, not one bad token: median per fill −0.022 SOL, win 43%.
- Follower slippage limits are known for almost none of these trades (0–2%), so "slip" ≈ the real path for every list here.
- The window is 00:35–04:10 UTC (US evening/night). R2, where GDM did best, was 17:09–00:34 UTC (US daytime). INFERRED, unproven: GDM's edge may depend on US daytime hours.
- **Confidence lowered to Low.** The verdict below held in R1 and R2 but failed in this window. The forward test decides: `gdm/fwd/fwd_gdm.sh` → `gdm/fwd/forward_gdm.txt`.
- The forward pipeline reproduces the training features exactly: 1,469 rows from 03:30–05:30, all 115 features identical, and identical scores and picks (`gdm/fwd/parity.py`).
- Full numbers: `gdm/fwd/smoke/prefreeze_check.txt`.
- **First forward run (09:40 PKT).** It covers launches 09:10–09:28, 121 launches, too few to judge (MEASURED). GDM made 4 picks (LM and L picked the same), FINAL-2 live made 7, with 1 overlap.
  - GDM: **+0.32** at 45 ms, 8 s, pro buys after us removed (2 fills out of 4 tries).
  - FINAL-2: **−0.22** (4 fills out of 7 tries).
  - Union: **+0.16**.
- **Bias warning for the forward test.**
  - Another job fetches follower slippage limits only for FINAL-2's live picks: 61% of their follower buys are covered vs 18% for GDM's.
  - So "slip" and "pro-after" favour GDM-only picks.
  - Compare GDM and FINAL-2 on "no-snipers" or "base". The report now prints base too.

## Verdict

**Alone, GDM does not beat FINAL-2 on total SOL at our target speeds (30–45 ms, 8 s hold).** It buys less than half as many launches.
- R2 at 45 ms, pro buys after us removed: **+3.87 vs +4.82 SOL**.
- R1 at 45 ms: **+2.04 vs +3.42 SOL**.
- Both MEASURED, pro costs.

It does beat FINAL-2 in four places (MEASURED):
- **Per fill:** R2 at 45 ms, median **+0.018 vs −0.027 SOL** per 0.5 SOL fill; win **57% vs 38%**.
- **Without the best 5 fills:** **+0.60 vs −0.62**.
- **At 75 ms with a 10 s hold:** R2 **+2.98 vs +1.51**; R1 **+2.82 vs +1.59**.
- **Strictest test, 10 s hold:** with every sniper buy after us removed, it wins in both periods at 45 and 75 ms.

**As an addition to FINAL-2, yes, it beats FINAL-2.** The rule is UNION: buy if FINAL-2 picks it OR GDM picks it.

R2 is fully out of sample for both models (10-22 22:09 → 10-23 05:34, 7.4 h). At 8 s, pro costs:

| Landing | Pro buys after us removed: UNION / FINAL-2 | All sniper buys after us removed: UNION / FINAL-2 |
|---|---|---|
| 75 ms | **+4.84 / +2.64** (+2.20) | **+4.12 / +2.12** |
| 45 ms | **+8.17 / +4.82** (+3.35, +70%) | **+6.73 / +3.72** |
| 30 ms | **+10.65 / +7.46** (+3.19) | **+8.66 / +5.90** |

- Without the top 5 fills (45 ms): **+2.14 vs −0.62**.
- Halves (45 ms): **+4.85 / +3.32 vs +3.29 / +1.53**.
- On FINAL-2's real live-pick window (23:36 → 05:34), live picks + GDM gives **+5.57 vs +3.17** at 45 ms.

R1 (10-22 03:07 → 18:00) used models trained on R2. FINAL-2 has seen R1 before 14:58: it is in its training data.

| Comparison | UNION | FINAL-2 |
|---|---|---|
| 45 ms, 8 s | **+4.27** | +3.42 |
| 45 ms, 10 s | **+6.84** | +4.19 |
| 30 ms, 10 s | **+7.69** | +5.66 |
| 75 ms, all sniper buys after us removed, 8 s | −0.70 | −0.50 |
| Second half of R1, 45 ms, 8 s | −0.50 | −1.16 |
| R1 14:58–18:00 only (unseen by FINAL-2), 45 ms, 8 s | +0.17 | −0.40 |
| R1 14:58–18:00 only, 45 ms, 10 s | +1.11 | −0.00 |

- In R2 the union is ahead in all 18 cells (3 landings × 3 variants × 8/10 s).
- In R1 it is ahead in 16 of 18. It is behind only with all sniper buys removed at 8 s: 75 ms (−0.70 vs −0.50) and 30 ms (+1.12 vs +1.69).

**The gain survives the checks (MEASURED):**
- **5 random seeds:** union > FINAL-2 in 9 of 10 single-seed runs (stored replay outcomes).
- **No wallet-list look-ahead:** with sniper wallets taken from R1 only, R2 at 45 ms gives **+7.22 vs +4.82**.
- **No token metadata (model L):** the union still beats FINAL-2 (stored replay outcomes).
- **Two clean choices:** the GDM model chosen on validation for each direction separately gives the same result: R2 **+7.96**; R1 **+4.81** at 8 s, **+6.88** at 10 s.

**Why it adds money (MEASURED):**
- GDM's picks overlap FINAL-2's only a little (27 of 312 R2 picks).
- The GDM-only picks earn on their own: R2 **+3.35** at 45 ms with pro buys after us removed, and **+3.01** with all sniper buys removed.
- In R1 they are weaker: **+0.86 / +0.25** at 8 s.
- GDM's picks draw **about 2× the generic buyers** of FINAL-2's picks in 2–10 s (R2 median 28 vs 9).

**Size of the gain, INFERRED:** at 45 ms and 0.5 SOL, the extra over FINAL-2 is +3.35 SOL in 7.4 h (R2) but only +0.85 in 15 h (R1, 8 s; +2.65 at 10 s). That is about **+1 to +11 SOL/day** on replay, depending on the period. It rests on one night of fully out-of-sample data, with fat tails.

**Confidence: Low–Medium. Lowered to Low after the 09:30 check above.**

**Frozen for a forward test:** `dryrun/frozen_gdm.json`, id **FRZ-GDM-U**, sha256 `54b13b8095dd41787794b3246b582d2c25b2c3fdddfa7946b0a6147e2127b0a2`, frozen 2026-10-23 09:10 PKT. No data after 08:50 PKT was read; the inputs end at 07:57 PKT.

## What was frozen (FRZ-GDM-U)
- **Rule:** buy if FINAL-2 picks it (unchanged live config) **OR** GDM score ≥ threshold, then the same guards. The guards are: payer is the creator; no "no bundle and dev buy < 1 SOL"; SOL-quoted; not mayhem.
- **Mechanics:** become-them.
  - 0.5 SOL.
  - Buy right after the dev's glued bundle, only if first: price ≤ post-bundle × 1.005.
  - Sell all at 8 s (10 s is the secondary exit).
- **GDM model:**
  - **Label:** "≥ 10 distinct generic buyers 2–10 s after the create". Generic means none of the 321 sniper or 9 pro wallets, and not the dev or bundle.
  - **Model:** 5-seed bag of histogram GBDTs (e_model.py code).
  - **Features:** feature set LM (below).
  - **Training:** all R1 + R2 rows until 05:34. First 80% by time to train, last 20% to early-stop.
  - **Threshold:** top 3% of that last slice (score ≥ 1.2355). It picks 3.0% of launches.
- **Fallback:** model L, the same without token metadata (threshold 1.2407). Use it if the engine cannot read the metadata at bundle close.
- **Scoring:** `gdm/gdm_score.py` scores feature rows with the frozen file and checks the sha.
- **Forward-test recipe:** stored in the JSON. Run `labels_pass.py` + `features.py` on the new launches, score, take the union with FINAL-2's live picks, then run `become_eval` at 30/45/75 ms.

## Method

### Labels
Script `gdm/labels_pass.py` → `labels.json`: 18,673 launches, R1 + R2 until 07:57, one pass, ~1 min.
- **(a) Market label.** The price 10 s after the create (also 3/5/8/15 s) divided by the post-bundle price.
  - Every trade (buy and sell) by the 321 sniper and 9 pro wallets after the bundle is removed, and the reserves are rebased.
  - 20% of launches reach ≥ 1.05.
  - MEASURED: at 45 ms, our fills on those launches average **+0.12 to +0.13 SOL**. The rest average **−0.054 to −0.056** (pro buys after us removed, 10 s, R1 / R2).
- **(b) Our own replay at 30 ms.** Same mechanics as `core/precompute_bt.py`. 45/75 ms come from `allres_bt.json`. Label: PnL with pro buys after us removed, 10 s hold, > 0.
- **(c) Generic buyers.** Distinct buyers 2–10 s after the create that are not snipers, pros, the dev or the bundle. Label: ≥ 10, which holds for 19% of launches.

### Features
Script `gdm/features.py` → `feats.npz`. 17,037 launches: SOL-quoted, not mayhem, in the feature table until 05:34. Everything is known at bundle close.
- **live:** FINAL-2's 61 live features minus `hour_utc` (R1 and R2 cover disjoint UTC hours).
- **gdm (30), walk-forward:** history uses only launches ≥ 10 min older; creates are counted at once.
  - **Deployer:** number of earlier launches, gap since the last one, relaunch < 60 s.
  - **Deployer's earlier launches:** their label-a outcome, share ≥ 1.05, and mean generic buyers.
  - **Bundle wallets:** the same for the launches where they were glued before.
  - **Same name:** count in the last hour (0 = first of its name) and those launches' outcomes.
  - **Walk-forward rates:** share of label-a hits for the fingerprint and for the URI host, 10 min to 3 h old.
  - **Market heat:** share of launches 10–70 min old with generic demand.
  - **Hint flags:** dev+bundle SOL, dK's 2–20 SOL band, exactly 1 glued tx, fresh deployer, FiFawH's fingerprint.
- **meta (14):** Twitter / website / Telegram, tw_status, description length, created_on, show_name.
- **rpc (11), tested but not used:** creator and funder lookups.
- **Excluded as look-ahead:** slot_*, fslot_*, f1s_/f5s_/f15s_, eb1s_/eb5s_, px_*, peak_*, y_*, vol_sol, holders_proxy, n_trades, max_vsol, graduated.

### Training
Script `gdm/train.py`, using the GBDT from `ops/select/e_model.py` (depth 3, learning rate 0.05, early stop).
- **fwd:** train on R1's first 80% by time, early-stop on R1's last 20%, test on R2.
- **rev:** train on R2's first 80%, test on R1.
- **Test AUC:**
  - Label (a) model: 0.77–0.78 in both directions.
  - Label (c) model: 0.89–0.90 on its own label, 0.75 on label (a).
  - Label (b) model: 0.77.
  - Details in `logs/train_summary.txt`.
- **Most important features:**
  - post-bundle market cap;
  - dev+bundle SOL;
  - dK's 2–20 SOL band;
  - the deployer's earlier generic demand;
  - the Twitter fields.

### Cut chosen on validation only
Script `gdm/train_cv.py`, results in `cv_rows.json`.
- **Cut:** top q% of validation scores, q ∈ {2, 3, 5, 7.5, 10}%. Guards are applied after the cut.
- **Criterion:** mean PRO-cost total over 30/45 ms × 8/10 s × {pro buys after us removed, all sniper buys removed}.
- **Folds:** two time-ordered folds per direction (60–80% and 80–100% of the training period).
- **Validation picks:**
  - fwd: **label c, LM, top 2%**;
  - rev: **ensemble of (a≥1.10, b, c), LM, top 7.5%**.
- **Frozen recipe:** the configuration whose worst of all 4 folds is highest and positive: **label c, LM, top 3%**. Then a 5-seed bag for stability (`bag_eval.py`).

### Trading
- **Evaluator:** `core/become_eval.py` (copy `gdm/become_eval6.py`, only `Pool(8)`→`Pool(6)`).
- **Settings:** LANDS=30,45,75, guard 1.005, 0.5 SOL.
- **Summary:** `gdm/gsum.py`, using lab_sum's metrics over a common time window per period.
- **Pro costs:** +0.007 per fill, −0.003 per failed buy.
- **Halves:** split at the window's midpoint.

## Results
"Pro-after" = pro buys after us removed, with follower slippage. "No-snipers" = all sniper and pro buys after us removed. Totals are SOL at pro costs. The detailed tables also show today's costs.

**R2 = 10-22 22:09 -> 10-23 05:34 PKT, fully out of sample for every list** (PRO-cost totals, SOL; fills/tries at the 45 ms landing)

| List | Tries | 75 ms 8 s: slip / pro-after / no-snipers | 45 ms 8 s | 30 ms 8 s | 75 ms 10 s | 45 ms 10 s | 30 ms 10 s |
|---|---|---|---|---|---|---|---|
| FINAL-2 offline | 127/208 | +3.41 / +2.64 / +2.12 | +6.37 / +4.82 / +3.72 | +9.81 / +7.46 / +5.90 | +2.23 / +1.51 / +1.04 | +4.54 / +3.14 / +2.17 | +8.53 / +6.39 / +4.97 |
| GDM, validation-chosen (yc 2%) | 42/73 | +2.54 / +2.34 / +2.04 | +3.60 / +3.29 / +2.83 | +4.13 / +3.59 / +2.95 | +3.05 / +2.83 / +2.60 | +3.96 / +3.61 / +3.25 | +4.37 / +3.83 / +3.30 |
| GDM bag (yc 3%) | 51/92 | +3.01 / +2.64 / +2.25 | +4.44 / +3.87 / +3.24 | +5.29 / +4.40 / +3.51 | +3.35 / +2.98 / +2.68 | +4.62 / +4.07 / +3.58 | +5.43 / +4.59 / +3.86 |
| GDM bag, R1-only sniper list | 46/84 | +2.41 / +2.04 / +1.63 | +3.41 / +2.95 / +2.38 | +4.26 / +3.48 / +2.64 | +2.71 / +2.35 / +2.02 | +3.67 / +3.21 / +2.75 | +4.48 / +3.73 / +3.03 |
| UNION F2 + GDM val-chosen | 155/259 | +5.90 / +5.05 / +4.42 | +9.59 / +7.96 / +6.67 | +12.88 / +10.44 / +8.63 | +5.24 / +4.44 / +3.91 | +8.07 / +6.59 / +5.48 | +11.90 / +9.68 / +8.06 |
| UNION F2 + GDM bag | 163/276 | +5.71 / +4.84 / +4.12 | +9.87 / +8.17 / +6.73 | +13.21 / +10.65 / +8.66 | +4.91 / +4.10 / +3.49 | +8.26 / +6.73 / +5.50 | +12.11 / +9.79 / +8.03 |
| UNION F2 + GDM bag, R1-only snipers | 159/270 | +5.26 / +4.39 / +3.69 | +8.86 / +7.22 / +5.85 | +12.20 / +9.70 / +7.78 | +4.42 / +3.62 / +3.02 | +7.26 / +5.78 / +4.60 | +11.11 / +8.83 / +7.13 |
| FINAL-2 minus GDM bottom half | 108/180 | +3.75 / +2.98 / +2.49 | +7.02 / +5.51 / +4.48 | +10.39 / +8.14 / +6.71 | +2.56 / +1.84 / +1.41 | +5.29 / +3.94 / +3.02 | +9.21 / +7.17 / +5.87 |

**R2 live-pick window 23:36 -> 05:34 PKT** (PRO-cost totals, SOL; fills/tries at the 45 ms landing)

| List | Tries | 75 ms 8 s: slip / pro-after / no-snipers | 45 ms 8 s | 30 ms 8 s | 75 ms 10 s | 45 ms 10 s | 30 ms 10 s |
|---|---|---|---|---|---|---|---|
| FINAL-2 LIVE picks | 108/176 | +2.04 / +1.57 / +1.24 | +4.28 / +3.17 / +2.57 | +7.18 / +5.28 / +4.31 | +1.86 / +1.40 / +1.08 | +3.45 / +2.43 / +1.87 | +6.63 / +4.87 / +3.95 |
| FINAL-2 offline | 96/159 | +1.64 / +1.19 / +0.96 | +4.32 / +3.19 / +2.59 | +7.30 / +5.43 / +4.46 | +1.51 / +1.07 / +0.86 | +3.48 / +2.45 / +1.92 | +6.98 / +5.27 / +4.39 |
| GDM bag | 38/70 | +2.68 / +2.32 / +2.04 | +3.58 / +3.08 / +2.65 | +3.95 / +3.12 / +2.44 | +3.47 / +3.12 / +2.90 | +4.14 / +3.64 / +3.31 | +4.57 / +3.78 / +3.21 |
| UNION F2 live + GDM bag | 135/229 | +3.98 / +3.41 / +2.93 | +6.77 / +5.57 / +4.71 | +9.37 / +7.27 / +5.90 | +4.57 / +4.03 / +3.60 | +6.49 / +5.38 / +4.62 | +9.53 / +7.58 / +6.34 |

**R1 = 10-22 03:07 -> 18:00 PKT (models trained on R2)** (PRO-cost totals, SOL; fills/tries at the 45 ms landing)

| List | Tries | 75 ms 8 s: slip / pro-after / no-snipers | 45 ms 8 s | 30 ms 8 s | 75 ms 10 s | 45 ms 10 s | 30 ms 10 s |
|---|---|---|---|---|---|---|---|
| FINAL-2 offline (in-sample < 14:58) | 172/342 | +1.88 / +0.99 / -0.50 | +5.49 / +3.42 / +1.05 | +8.05 / +5.24 / +1.69 | +2.42 / +1.59 / +0.20 | +6.11 / +4.19 / +1.98 | +8.22 / +5.66 / +2.34 |
| GDM, validation-chosen (E3 7.5%) | 140/303 | +2.06 / +1.30 / +0.34 | +3.99 / +2.48 / +0.85 | +6.09 / +4.08 / +1.76 | +3.35 / +2.58 / +1.74 | +5.74 / +4.22 / +2.78 | +7.22 / +5.21 / +3.19 |
| GDM bag (yc 3%) | 97/186 | +2.15 / +1.65 / +1.04 | +3.04 / +2.04 / +1.05 | +3.52 / +2.17 / +0.88 | +3.33 / +2.82 / +2.28 | +4.89 / +3.87 / +2.98 | +5.04 / +3.67 / +2.55 |
| UNION F2 + GDM val-chosen | 277/553 | +2.32 / +1.04 / -0.97 | +7.80 / +4.81 / +1.45 | +10.82 / +6.84 / +1.81 | +4.02 / +2.74 / +0.91 | +9.77 / +6.88 / +3.81 | +12.11 / +8.30 / +3.71 |
| UNION F2 + GDM bag | 248/471 | +2.26 / +1.12 / -0.70 | +7.02 / +4.27 / +1.31 | +9.15 / +5.50 / +1.12 | +4.04 / +2.89 / +1.22 | +9.49 / +6.84 / +4.09 | +11.19 / +7.69 / +3.64 |
| FINAL-2 minus GDM bottom half | 168/335 | +1.81 / +0.93 / -0.42 | +5.42 / +3.38 / +1.17 | +7.98 / +5.20 / +1.81 | +2.35 / +1.52 / +0.28 | +6.04 / +4.16 / +2.10 | +8.15 / +5.62 / +2.45 |

**R1 14:58 -> 18:00 PKT only (FINAL-2's early-stop holdout: the only R1 slice unseen by its training)** (PRO-cost totals, SOL; fills/tries at the 45 ms landing)

| List | Tries | 75 ms 8 s: slip / pro-after / no-snipers | 45 ms 8 s | 30 ms 8 s | 75 ms 10 s | 45 ms 10 s | 30 ms 10 s |
|---|---|---|---|---|---|---|---|
| FINAL-2 offline | 28/63 | -0.15 / -0.24 / -0.56 | -0.19 / -0.40 / -0.78 | +0.14 / -0.14 / -0.80 | +0.31 / +0.23 / -0.07 | +0.19 / -0.00 / -0.35 | +0.73 / +0.48 / -0.15 |
| GDM val-chosen | 31/61 | +1.35 / +1.22 / +0.95 | +1.28 / +1.01 / +0.66 | +1.48 / +1.11 / +0.65 | +1.81 / +1.69 / +1.46 | +1.79 / +1.53 / +1.23 | +1.86 / +1.53 / +1.13 |
| GDM bag | 24/40 | +0.65 / +0.55 / +0.40 | +0.45 / +0.28 / +0.12 | +0.19 / -0.02 / -0.20 | +0.84 / +0.74 / +0.61 | +0.94 / +0.78 / +0.63 | +0.62 / +0.43 / +0.27 |
| UNION val-chosen | 53/107 | +1.19 / +0.99 / +0.48 | +1.29 / +0.83 / +0.19 | +1.48 / +0.85 / -0.15 | +2.00 / +1.81 / +1.35 | +2.07 / +1.64 / +1.07 | +2.33 / +1.76 / +0.85 |
| UNION bag | 49/94 | +0.56 / +0.38 / -0.06 | +0.53 / +0.17 / -0.34 | +0.61 / +0.14 / -0.67 | +1.25 / +1.08 / +0.68 | +1.44 / +1.11 / +0.64 | +1.67 / +1.24 / +0.48 |

### Full detail at 8 s (fills, today and pro costs, median per fill in SOL at today's costs, win rate, without the best 5, halves)

**R2 full detail** (exit t8; PRO = pro costs; w/o top5, halves at PRO costs)

| List | Landing | Variant | Fills/tries | Today SOL | PRO SOL | Median/fill | Win | PRO w/o top 5 | PRO halves |
|---|---|---|---|---|---|---|---|---|---|
| FINAL-2 (offline picks) | 75 ms | slip | 87/208 | +2.56 | **+3.41** | -0.025 | 38% | -0.66 | +1.90 / +1.51 |
| FINAL-2 (offline picks) | 75 ms | pro-after | 87/208 | +1.79 | **+2.64** | -0.026 | 37% | -1.34 | +1.34 / +1.30 |
| FINAL-2 (offline picks) | 75 ms | no-snipers | 87/208 | +1.26 | **+2.12** | -0.028 | 32% | -1.71 | +0.78 / +1.33 |
| FINAL-2 (offline picks) | 45 ms | slip | 127/208 | +5.32 | **+6.37** | -0.026 | 39% | +0.53 | +4.53 / +1.84 |
| FINAL-2 (offline picks) | 45 ms | pro-after | 127/208 | +3.77 | **+4.82** | -0.027 | 38% | -0.62 | +3.29 / +1.53 |
| FINAL-2 (offline picks) | 45 ms | no-snipers | 127/208 | +2.67 | **+3.72** | -0.030 | 35% | -1.52 | +2.31 / +1.41 |
| FINAL-2 (offline picks) | 30 ms | slip | 158/208 | +8.60 | **+9.81** | -0.015 | 45% | +3.84 | +6.15 / +3.67 |
| FINAL-2 (offline picks) | 30 ms | pro-after | 158/208 | +6.25 | **+7.46** | -0.018 | 40% | +1.91 | +4.61 / +2.84 |
| FINAL-2 (offline picks) | 30 ms | no-snipers | 158/208 | +4.69 | **+5.90** | -0.028 | 37% | +0.54 | +3.37 / +2.53 |
| GDM alone (frozen recipe, trained R1) | 75 ms | slip | 34/92 | +2.65 | **+3.01** | +0.023 | 59% | -0.20 | +1.90 / +1.11 |
| GDM alone (frozen recipe, trained R1) | 75 ms | pro-after | 34/92 | +2.29 | **+2.64** | +0.015 | 59% | -0.39 | +1.67 / +0.97 |
| GDM alone (frozen recipe, trained R1) | 75 ms | no-snipers | 34/92 | +1.90 | **+2.25** | +0.013 | 56% | -0.65 | +1.36 / +0.89 |
| GDM alone (frozen recipe, trained R1) | 45 ms | slip | 51/92 | +4.00 | **+4.44** | +0.036 | 59% | +1.04 | +2.62 / +1.82 |
| GDM alone (frozen recipe, trained R1) | 45 ms | pro-after | 51/92 | +3.44 | **+3.87** | +0.018 | 57% | +0.60 | +2.19 / +1.68 |
| GDM alone (frozen recipe, trained R1) | 45 ms | no-snipers | 51/92 | +2.81 | **+3.24** | +0.012 | 55% | +0.22 | +1.75 / +1.49 |
| GDM alone (frozen recipe, trained R1) | 30 ms | slip | 67/92 | +4.77 | **+5.29** | +0.029 | 55% | +1.84 | +2.96 / +2.33 |
| GDM alone (frozen recipe, trained R1) | 30 ms | pro-after | 67/92 | +3.88 | **+4.40** | +0.006 | 52% | +1.05 | +2.42 / +1.98 |
| GDM alone (frozen recipe, trained R1) | 30 ms | no-snipers | 67/92 | +2.99 | **+3.51** | +0.002 | 51% | +0.37 | +1.81 / +1.70 |
| UNION FINAL-2 + GDM | 75 ms | slip | 113/276 | +4.59 | **+5.71** | -0.016 | 43% | +0.83 | +2.83 / +2.88 |
| UNION FINAL-2 + GDM | 75 ms | pro-after | 113/276 | +3.72 | **+4.84** | -0.016 | 42% | +0.02 | +2.23 / +2.61 |
| UNION FINAL-2 + GDM | 75 ms | no-snipers | 113/276 | +3.00 | **+4.12** | -0.027 | 39% | -0.60 | +1.51 / +2.61 |
| UNION FINAL-2 + GDM | 45 ms | slip | 163/276 | +8.50 | **+9.87** | -0.018 | 44% | +3.48 | +6.19 / +3.68 |
| UNION FINAL-2 + GDM | 45 ms | pro-after | 163/276 | +6.80 | **+8.17** | -0.025 | 43% | +2.14 | +4.85 / +3.32 |
| UNION FINAL-2 + GDM | 45 ms | no-snipers | 163/276 | +5.36 | **+6.73** | -0.027 | 40% | +0.89 | +3.64 / +3.08 |
| UNION FINAL-2 + GDM | 30 ms | slip | 206/276 | +11.63 | **+13.21** | -0.014 | 47% | +6.74 | +7.80 / +5.41 |
| UNION FINAL-2 + GDM | 30 ms | pro-after | 206/276 | +9.07 | **+10.65** | -0.015 | 43% | +4.61 | +6.13 / +4.53 |
| UNION FINAL-2 + GDM | 30 ms | no-snipers | 206/276 | +7.07 | **+8.66** | -0.027 | 41% | +2.76 | +4.58 / +4.08 |

**R1 full detail** (exit t8; PRO = pro costs; w/o top5, halves at PRO costs)

| List | Landing | Variant | Fills/tries | Today SOL | PRO SOL | Median/fill | Win | PRO w/o top 5 | PRO halves |
|---|---|---|---|---|---|---|---|---|---|
| FINAL-2 (offline; in-sample < 14:58) | 75 ms | slip | 114/342 | +0.63 | **+1.88** | -0.000 | 49% | -0.06 | +1.86 / +0.03 |
| FINAL-2 (offline; in-sample < 14:58) | 75 ms | pro-after | 114/342 | -0.26 | **+0.99** | -0.017 | 46% | -0.87 | +1.23 / -0.23 |
| FINAL-2 (offline; in-sample < 14:58) | 75 ms | no-snipers | 114/342 | -1.75 | **-0.50** | -0.025 | 39% | -2.22 | +0.47 / -0.97 |
| FINAL-2 (offline; in-sample < 14:58) | 45 ms | slip | 172/342 | +3.95 | **+5.49** | +0.004 | 52% | +1.78 | +6.11 / -0.62 |
| FINAL-2 (offline; in-sample < 14:58) | 45 ms | pro-after | 172/342 | +1.87 | **+3.42** | -0.012 | 45% | -0.05 | +4.57 / -1.16 |
| FINAL-2 (offline; in-sample < 14:58) | 45 ms | no-snipers | 172/342 | -0.49 | **+1.05** | -0.027 | 38% | -2.31 | +3.18 / -2.13 |
| FINAL-2 (offline; in-sample < 14:58) | 30 ms | slip | 218/342 | +6.28 | **+8.05** | +0.012 | 54% | +4.21 | +6.74 / +1.32 |
| FINAL-2 (offline; in-sample < 14:58) | 30 ms | pro-after | 218/342 | +3.46 | **+5.24** | -0.007 | 47% | +1.60 | +4.72 / +0.51 |
| FINAL-2 (offline; in-sample < 14:58) | 30 ms | no-snipers | 218/342 | -0.08 | **+1.69** | -0.027 | 39% | -1.82 | +2.75 / -1.05 |
| GDM alone (frozen recipe, trained R2) | 75 ms | slip | 69/186 | +1.43 | **+2.15** | -0.023 | 48% | -0.53 | +1.12 / +1.02 |
| GDM alone (frozen recipe, trained R2) | 75 ms | pro-after | 69/186 | +0.93 | **+1.65** | -0.023 | 48% | -1.02 | +0.80 / +0.84 |
| GDM alone (frozen recipe, trained R2) | 75 ms | no-snipers | 69/186 | +0.32 | **+1.04** | -0.024 | 44% | -1.57 | +0.55 / +0.49 |
| GDM alone (frozen recipe, trained R2) | 45 ms | slip | 97/186 | +2.18 | **+3.04** | -0.022 | 46% | -0.29 | +2.31 / +0.73 |
| GDM alone (frozen recipe, trained R2) | 45 ms | pro-after | 97/186 | +1.18 | **+2.04** | -0.024 | 45% | -1.01 | +1.58 / +0.46 |
| GDM alone (frozen recipe, trained R2) | 45 ms | no-snipers | 97/186 | +0.19 | **+1.05** | -0.027 | 42% | -1.93 | +1.03 / +0.01 |
| GDM alone (frozen recipe, trained R2) | 30 ms | slip | 118/186 | +2.56 | **+3.52** | -0.022 | 45% | +0.05 | +2.52 / +1.00 |
| GDM alone (frozen recipe, trained R2) | 30 ms | pro-after | 118/186 | +1.21 | **+2.17** | -0.030 | 43% | -1.00 | +1.54 / +0.63 |
| GDM alone (frozen recipe, trained R2) | 30 ms | no-snipers | 118/186 | -0.09 | **+0.88** | -0.035 | 41% | -2.25 | +0.86 / +0.02 |
| UNION FINAL-2 + GDM | 75 ms | slip | 169/471 | +0.47 | **+2.26** | -0.018 | 46% | -0.54 | +1.54 / +0.72 |
| UNION FINAL-2 + GDM | 75 ms | pro-after | 169/471 | -0.67 | **+1.12** | -0.022 | 43% | -1.64 | +0.82 / +0.30 |
| UNION FINAL-2 + GDM | 75 ms | no-snipers | 169/471 | -2.48 | **-0.70** | -0.030 | 37% | -3.33 | -0.04 / -0.66 |
| UNION FINAL-2 + GDM | 45 ms | slip | 248/471 | +4.84 | **+7.02** | -0.013 | 48% | +2.44 | +6.76 / +0.26 |
| UNION FINAL-2 + GDM | 45 ms | pro-after | 248/471 | +2.09 | **+4.27** | -0.020 | 43% | -0.03 | +4.77 / -0.50 |
| UNION FINAL-2 + GDM | 45 ms | no-snipers | 248/471 | -0.88 | **+1.31** | -0.030 | 37% | -2.92 | +3.07 / -1.76 |
| UNION FINAL-2 + GDM | 30 ms | slip | 310/471 | +6.66 | **+9.15** | -0.010 | 48% | +4.57 | +7.49 / +1.67 |
| UNION FINAL-2 + GDM | 30 ms | pro-after | 310/471 | +3.01 | **+5.50** | -0.019 | 43% | +1.21 | +4.93 / +0.57 |
| UNION FINAL-2 + GDM | 30 ms | no-snipers | 310/471 | -1.37 | **+1.12** | -0.030 | 37% | -3.10 | +2.52 / -1.40 |

The same detail at 10 s and for every other list is in `fin_R2.txt`, `fin_R2live.txt`, `fin_R1.txt` and `fin_R1h.txt`.

### Other ensembles and variants
- **Intersections are not robust** (`logs/ens_f2.txt`, stored outcomes):
  - FINAL-2 ∩ GDM top 10–30% is mostly below FINAL-2 for the chosen models. R2 with label c: +1.8 to +2.3 vs +4.6.
  - It is above FINAL-2 for some other models, e.g. the R2 label-a model's top 20%: +6.9 vs +4.6.
  - Dropping FINAL-2 picks in GDM's bottom half: R2 **+5.51 vs +4.82** at 45 ms, 8 s, pro buys after us removed. R1 **+3.38 vs +3.42**. About neutral.
  - The dropped picks are small and lose in every check (`logs/ens_f2.txt`, "bottom 50%" rows).
- **Labels compared** (`logs/select_cut.txt`, `logs/ens_eval.txt`, stored outcomes):
  - (a) rank well (AUC 0.78) but their top picks are noisier.
  - (b), our own replay outcome, behaves like the earlier `bt_train.py` result.
  - (c), generic buyer count, was the most stable across the 4 validation folds.
  - Ensembles of (a)+(b)+(c) did not beat (c) consistently.
- **RPC features:** they add nothing measurable (AUC +0.00–0.01), so they are dropped. They would need an RPC call at the create.

### What GDM buys (MEASURED, test periods; `logs/describe.txt`)
| Test period | Picks | Generic buyers 2–10 s (mean / median) | Label a ≥ 1.05 | dev+bundle SOL | In 2–20 SOL band | Fresh deployer | Deployer's earlier mean generic buyers |
|---|---|---|---|---|---|---|---|
| R2 FINAL-2 | 239 | 17.0 / 9 | 51% | 6.3 | 91% | 23% | 15.2 |
| R2 GDM | 100 | **33.5 / 28** | 58% | 9.3 | 99% | **2%** | **28.1** |
| R2 all launches | 7,789 | 6.3 / 0 | 20% | 5.4 | 41% | 45% | 6.8 |
| R1 FINAL-2 | 342 | 15.2 / 10 | 58% | 5.8 | 91% | 15% | 15.6 |
| R1 GDM | 186 | **25.5 / 20** | 56% | 9.3 | 99% | **5%** | **29.7** |

- GDM buys **serial deployers whose earlier launches drew broad generic buying**: about a 9 SOL dev+bundle, a Twitter link, a higher post-bundle market cap. That is close to CW's "hot devs" and the opposite of dK's "new deployer" hint.
- **Where the union's money comes from** (45 ms, 8 s; pro buys after us removed | all sniper buys removed):

| Period | FINAL-2 only | Both | GDM only |
|---|---|---|---|
| R2 | +4.30 \| +3.48 (184 tries) | +0.52 \| +0.24 (24) | **+3.35 \| +3.01** (68) |
| R1 | +2.24 \| +0.26 (285) | +1.18 \| +0.79 (57) | +0.86 \| +0.25 (129) |

## Robustness checks
| Check | Union | FINAL-2 | Note |
|---|---|---|---|
| R1-only sniper list (220 wallets) for labels and history | **+7.22** | +4.82 | Removes look-ahead in the 321-wallet list. R2, 45 ms, 8 s, pro buys after us removed (`logs/leak_check.txt`, `fin_R2.json`). GDM alone: +2.95 vs +3.87 with the full list. |
| Seeds 0–4, single models (stored outcomes) | wins 9 of 10 | | GDM-alone totals swing about ±1.2 SOL by seed, hence the bag (`logs/robust.txt`). |
| Ablation: label-derived history features removed (stored outcomes) | R2 +2.42 / R1 +2.68 | R2 +4.64 / R1 +3.11 | The union falls below FINAL-2 and GDM alone goes flat to negative. The deployer and bundle-wallet "earlier generic demand" features carry the gain (`logs/robust.txt`). |

## Caveats
1. **Replay only.**
   - R2 places our buy using our engine's timelines.
   - R1 has no timelines and uses a position proxy (pessimistic).
   - Nothing here was traded.
2. **FINAL-2's R1 numbers are partly in-sample.**
   - FINAL-2 was trained on the run-1 table's first 80%, which ends at **10-22 14:58:38 PKT**. MEASURED: 20,302 rows; the holdout count matches the frozen file.
   - `core/f2_offline.py` splits R1 at 10:00 PKT, not at that cut.
   - So the R1 "offline picks" from 08:24 to 14:58 are FINAL-2 training data. BECOME_THEM §2b calls them "nearly unseen"; that holds only for 14:58–18:00.
   - Unseen R1 slice: FINAL-2 −0.40 vs union +0.17 vs GDM +0.28 (45 ms, 8 s).
3. **I saw test numbers for several setups while building.** Mitigations:
   - The clean out-of-sample numbers are the setups chosen on each direction's own validation ("validation-chosen" rows). They give the same verdict.
   - The frozen recipe (c / LM / top 3% / bag) was chosen with validation folds that include R2's own training folds, so its R2 numbers are slightly optimistic.
4. **Small samples and fat tails.**
   - R2 is one night of 7.4 h with about 100 GDM tries.
   - The validation slices are about 3 h each.
   - R1's afternoon (14:58–18:00) is weak for every list: −0.4 to +1.0 SOL at 45 ms, 8 s.
5. **Live feasibility (INFERRED).** GDM needs at bundle close:
   - token metadata (the L fallback is frozen for when it can't be read in time);
   - a history table: each deployer's and bundle wallet's earlier generic-buyer counts, ≥ 10 min old, refreshed by a sidecar like FINAL-2's history features;
   - the same ≤ 45 ms landing as FINAL-2 to be first after the bundle.
   - At 75 ms everything is much smaller.
6. **Exit not re-optimized.** The 8/10 s exit comes from the earlier study. The 10 s hold is better in R1, 8 s in R2.

## Files (`ops/overnight/gdm/`)
- **Labels and features:**
  - `labels_pass.py` → `labels.json`, and `labels_r1s.json` for the R1-only sniper check;
  - `features.py` → `feats.npz`, `feats_meta.json`;
  - `f2_scores.py` → `f2.npz` (FINAL-2 offline scores; 100% parity with `core/f2_off_*`).
- **Models:**
  - `train.py`, `select_cut.py`, `ens_eval.py`, `train_cv.py` (→ `cv_rows.json`);
  - `bag_eval.py`, `robust.py`, `leak_check.py`, `wallets_r1.py`;
  - `models/` holds scores and trees.
- **Trading:**
  - `make_picks.py` → `picks/*.json`;
  - `become_eval6.py` → `picks/cand*_become_B0.5_x.json`;
  - `gsum.py` → `fin_R2*.json` / `fin_R1*.json` / `*.txt`;
  - `compact.py`, `mdtables.py`, `describe.py`.
- **Freeze:**
  - `freeze.py` → `../dryrun/frozen_gdm.json` + `.sha256`;
  - `gdm_score.py` scores with the frozen rule.
- **Logs:** `logs/*.txt`, the console output of each step.
- **Forward test (`gdm/fwd/`):**
  - **Run:** `fwd_gdm.sh`. Any time; read-only, offline, nice, at most 6 workers, lock-protected. It appends a timestamped report to `forward_gdm.txt` for launches created after the freeze (09:10:56 PKT) and at least 6 min old.
  - **Steps:**
    - `gdm_pha.py`: incremental phase A from the synced raw R2 chunks since 04:57 PKT, into the new dir `phaseA_gdmfwd`.
    - `b_launch.py`: into `phaseB_gdmfwd`.
    - `c_join_gdm.py`: phase-B rows before 04:59 from a one-time copy of `phaseB_fwd` (`phaseB_gdmhist`), ours after.
    - `f_dump6.py` and `merge_dump.py`: into `paper/table_gdmfwd.jsonl.gz`.
    - `fwd_labels.py`: from 07:50 on. `fwd_features.py`: the same code as training. History is everything ≥ 10 min older: R1 + R2 + forward.
    - `fwd_eval.py`: frozen LM and L scores (sha checked), FINAL-2 live picks from `shadow/scores_v3.jsonl`, the unions, and `become_eval6.py` on `phaseA_gdmfwd`. It reports LANDS 30/45/75, guard 1.005, 8/10 s, the three variants, today and pro costs, and slippage-limit coverage.
  - **Checks:** `parity.py`. `smoke/prefreeze_check.txt` holds the 05:35–09:10 check.
  - **Runtime:** about 2.5 min per run. `phaseA_gdmfwd` grows by about 0.28 GB per hour of data.

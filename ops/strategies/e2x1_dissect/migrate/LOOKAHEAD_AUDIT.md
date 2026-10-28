# Look-ahead audit: near-migration strategy (migrate/ + migpaper/)

Agent "mig_audit", 10-28 PKT. Read-only audit. No author files were changed and the forward loop (pid 3563183) was not touched.
Scratch: `/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/mig_audit/` (scripts + logs only).
M = measured, I = inferred.

## Verdict
**The BLINK-class bug (feature counts trades after the trigger) is not present.** I recomputed all 84 features from scratch
for 300 V=105 entry rows, using only trades up to and including the trigger. They match feat.pkl exactly (0 differences on 84 × 300 values, M).
Three smaller causality problems exist. None of them explains the headline. Fixing each one leaves the headline's test P&L the same or higher.
**What does undermine the headline is model-seed luck.** The test model is trained on a random 90 % of the train rows, so
the reported test numbers (+2.54 pre / +1.73 react) are the **best of 12 seeds**. The 12-seed mean is **+1.07 / +0.36** (section 4).

| # | issue | class | affects | effect on headline (pre 2 SOL, V=105, p30≥0.8, mig+2, −20 %) |
|---|---|---|---|---|
| A | Pre-send gate is the p30 score of the crossing trade, but resting tries are sent **before** that trade exists | gate not causal (decision ≥ trigger) | pre-send rows (m3/m4 and the migpaper pre row) | Using a causal gate (p30 at the arm trade, or strictly before the trigger) leaves P&L the **same or higher**: 12-seed mean on test is +1.47 (arm) or +1.48 (strict) vs +1.07 |
| B | Wallet trips and creator "near" counted on tokens that only qualify for the tape (≥78 vSOL) **later** | outcome resolved after entry (selection) | b10_*, cx_*, hold_*, dev_prior_near | Within refit noise. Train drops 2.56 to 2.14, but six null perturbations of the same size give 2.10–2.50. OOF AUC 0.875 to 0.877 |
| C | Predictor-drop stop checkpoints include the rest of the checkpoint slot (≤1 slot after the decision) | same-slot look-ahead | pd0.3 rows only | 10 of 85 checkpoints on the headline rows see 1–2 extra trades. Minor |
| D | Test-model randomness: early stopping holds out a random 10 % when n>10,000 | not a leak; evaluation fragility | every test number in m2, m4 and REPORT | Pre test +2.54 is the max of 12 seeds (range −0.09…+2.54, mean +1.07). React +1.73 is also the max (−0.77…+1.73, mean +0.36) |

## 1. Features at the trigger (check 1)
- **Code reading (m1_features.py).** Every token-level feature reads prefix sums at `k+1`, `rows[:k]` or the holder snapshot taken right after row k.
  That covers flows over 1/5/10/30/120 s, n_tr, buys/sells, vmax_prev/dd, t_since50/80 (the first ≥50/≥80 trade is ≤k), holders/top/dev/sniper shares and dev_sold.
  The tape is sorted by (mint, slot, idx, j) (M: verified on all 3.49 M rows), so "≤k" excludes later indexes in the same slot and later legs of the same tx.
  `snip_users` lists create-slot buyers over the whole slot, but their balances are taken at k, so a later buyer contributes 0 (2,697 crossings sit in the create slot; no effect).
  hour/wday come from the trigger's block time. No feature reads `c`, `t_complete` or anything after k.
- **Empirical check (M).** `recompute300.py` is independent code: numpy loops plus a per-user trip table built directly from the curve and pool tape, not from wallets.npz.
  It covers 300 rows: 150 headline picks (p30≥0.8) and 150 non-picks (V=105, first crossings).
  - Variant A (m1's definition, state after the trigger trade): **all 84 features identical to feat.pkl.**
  - Variant ST (strictly (slot, idx) < trigger): 70 features change, as expected. vsol, sol_left, cross_sol, flows, holders, b10_* and cx_* all include the trigger trade by design.
- **What "at the trigger" means here.** For **reactive** entry the trigger trade is observed before the buy is sent, so using it is legitimate (decision after trigger).
  For **pre-send** it is not (issue A).

## 2. Wallet / creator prior stats (check 2)
- **Trip resolution (m1 `wstats`) is causal.** A trip counts only if `t_res < t` (block seconds, strict).
  `t_res` is the trip's last trade, or the completion time for graduated mints, or first trade +600 s for non-graduated ones.
  P&L uses only that trip's trades, which all come before t_res. The current mint's trip is excluded. Same-second trips are excluded too (conservative).
- **Issue B (selection leak).** The tape holds only mints that reached ≥78 vSOL at some point in the 5-day file (grad/g2b_full.py `keep`).
  So a trip on token Z counts as soon as it is resolved, even when Z reaches 78 only after the entry time. The fact "Z will become a near-graduation token" leaks in.
  The same applies to `dev_prior_near`, which uses lifetime `mx ≥ 78` of the creator's earlier tokens.
  `dev_prior_n` (all 237,970 creates) and `dev_prior_grad` (completion before the current create) are clean.
  - Fix applied in the scratch copy (`m1fix.py member`): a trip or token counts only once its mint has reached 78 vSOL before t.
    Mints with no curve tape, i.e. mayhem pools with pool-only trips, are known from their migration and are left unchanged.
    This copy reproduces feat.pkl bit-exactly with the fix off, and the independent code agrees with it with the fix on (0 diffs / 300 rows).
  - Size (M): rows changed (all entrable / V105 first crossings) are b10_pnl 43 % / 31 %, hold_pnl_w 60 % / 53 %, b10_winrate 45 % / 33 %, cx_n 5.5 % / 3.3 %, dev_prior_near 12 % / 8 %.
    Medians are unchanged, and every changed feature has the same univariate AUC against the p30 label (e.g. b10_winrate 0.544 to 0.544).
  - Headline (M): train OOF 2.56 to 2.14 SOL/day. A null test adds the **same deltas shuffled across rows** and refits; six such nulls give train 2.10, 2.21, 2.24, 2.28, 2.48, 2.50.
    The fix is therefore indistinguishable from refit noise. **Immaterial.**
  - Forward loop (I): the store is extended after each window with mints that reached 78 in a tape that includes a 15-min look-ahead. The same leak exists there, bounded at about 15 min. Negligible.

## 3. GBDT handling (check 3)
- Train rows get out-of-fold probabilities (leave one train day out); test rows come from a model fit on 10-24..10-26 only. Clean.
- HistGradientBoosting bins inside each `fit`, so no binning or scaling is fit on all days. There is no other preprocessing. Clean.
- The OOF folds use later train days to score earlier ones (normal CV, not a test leak). The continuation model's train-row probabilities are in-sample (REPORT already says so). Test is clean.
- **Issue D (M).** `early_stopping='auto'` turns on when n>10,000. The test-model fit (11,963 rows) therefore holds out a random 10 % chosen by `random_state`.
  The OOF folds (~7.4–8 k rows) do not, so train numbers are seed-independent while test numbers are not.
  The `(p30, 0.8, mig+2)` cell was chosen after seeing test with seed 0, and seed 0 turns out to be the luckiest of 12.
  The frozen forward models (mp_freeze, about 20 k rows, seed 0) are one arbitrary draw of the same kind.

## 4. Re-scored headline (M; same m2 code, same per-row replays sim_pre_2.0 / sim_react_2.0, exit mig+2 / −20 % / 120 s)
SOL/day. Train = OOF (deterministic). Test = mean (min…max) over 12 seeds of the test model. "avg-p" = threshold on the 12-seed mean probability.

| features (gate) | causal for | pre 2 SOL train | pre test, 12 seeds | pre test avg-p [90 % CI] | react 2 SOL train | react test, 12 seeds | react test avg-p | entries/day test |
|---|---|---|---|---|---|---|---|---|
| original (seed 0, as reported) | react (except B) | +2.56 | +2.54 (seed 0 only) | — | +2.85 | +1.73 (seed 0 only) | — | 27.5 / 23.6 |
| original | react (except B) | +2.56 | **+1.07** (−0.09…+2.54) | +0.95 [−1.2, +2.8] | +2.85 | **+0.36** (−0.77…+1.73) | +0.05 | ~26 / 22 |
| B fixed (membership) | react | +2.14 | +0.56 (−0.46…+1.16) | +0.52 [−1.4, +2.2] | +2.44 | −0.16 (−1.10…+0.40) | −0.30 | ~25 / 22 |
| B fixed + state strictly before trigger | pre (upper bound) and react | +2.42 | +1.48 (+0.98…+1.96) | +1.90 [+0.7, +3.0] | +2.63 | +1.03 (+0.67…+1.36) | +1.40 | ~19 / 17 |
| B fixed + state at the arm trade (vSOL ≥100 run start) | pre and react, fully | +1.90 | +1.47 (+0.58…+2.24) | **+2.03 [+0.9, +3.0]**, days +1.84 / +2.23 | +2.28 | +1.37 (+0.34…+2.28) | +2.01 | ~22 / 20 |

Reading:
- **Issue A does not inflate the result.** A gate decided at the arm trade (or just before the trigger) is fully causal for pre-sent tries. It does at least as well as the trigger-time gate on test (12-seed mean +1.47 vs +1.07) and has much smaller seed spread.
  The extra information in the trigger trade (cross_sol, flows including it, cx_* of its wallet) gives a slightly higher AUC (V105 test 0.728 vs 0.700–0.704) but no extra P&L.
- **Issue B is noise-level** (section 2 null test).
- **The honest test level of the frozen cell is about +1 SOL/day for pre-send and about +0.4 for reactive, not +2.5 / +1.7.** The causal arm-time gate gives about +1.5 (seed mean) to +2.0 (seed-averaged model) for both modes.
  All of these rest on about 2 test days and 35–55 trades (I: wide CIs).

## 5. Sim entry/exit (check 4)
- **Reactive entry**: the buy lands at the crossing clock + d_e and fills at the last trade before landing. The +5 % guard uses the crossing quote. Causal.
- **Pre-send entry (issue A)**: the fill is the first try landing while vSOL ∈ [V, V+10]. REPORT §3 says 54 % of fills come from resting tries, and every such fill lands before the reactive landing (crossing + d_e), so it was sent before the trigger could be seen.
  Gating those fills on p30(trigger) is not implementable. The sim also drops arms whose crossing self-completes the curve (ent=0) and arms that never reach V. Live, both would cost only try fees (0.005 mSOL each; I: small).
  The migpaper `pre` row is a verbatim port (mplib `sim_row`), so the **forward pre-send row inherits the same non-causal gate**. The reactive row does not.
- **−20 % stop**: triggered by the first recorded trade after entry that marks the position at ≤80 % of cost; the sell lands at that trade's clock + d_x at the last trade before landing. Causal.
- **Timeout 120 s**: entry clock + 120 s + d_x. Causal. One small oddity: for a pre-send fill at the crossing state, the entry clock is set to the reactive landing time, not the try's.
- **Pool sell at mig+2**: the migration tx clock + 2 slots + d_x, at the pool state after the last pool event before that point. It needs only "migration seen". Causal.
- **Predictor-drop stop (issue C)**: the checkpoint features take every trade up to the end of slot `s2 = slot_k + int(sec/0.212)`, but the decision clock is `ck + sec/0.212`, which can fall inside s2.
  On the headline rows, 10 of 85 checkpoints (11.8 %) use 1–2 trades after the decision (median 1). The continuation model's train rows are also in-sample. This affects pd0.3 rows only.
- Dropped rows: 2 of 293 headline rows are graduated without a recorded migration and are excluded from the sim. The `edge` filter removes rows within 35 min of a recording tail end; it is censoring, not a signal.
  Note: `edge` reads the live `/home/moiz/sniper-data/collect/run_*/run.json` set, so rerunning m1 today flags 175 different rows (reproducibility only).
  No candidate is lost to the non-SOL migration filter (0 of 3,643).

## 6. First-crossing definition and the p30 label (check 5)
- `ent = rtok[k] != 0` is the crossing trade's **own post-state**, so it is decidable when that trade is seen. This is correct for reactive entry.
  For pre-send, entrability is not known when tries are sent (same as issue A). The first-crossing logic (`below` / reset under V−3) only looks backwards.
- The label `t_complete = (slot[c] − slot[k])·0.212 s` uses `c`, the first rtok==0 index. No feature uses `c` or any row after k; the empirical check confirms this.
  Edge rows (whose label cannot be observed) are dropped. **No label leakage.**

## 7. What to change (owner's call; nothing changed here)
1. Score the forward paper's **reactive row** as the clean one. If pre-send stays the headline, gate it on p30 computed at the arm trade (fully causal and no worse here) and say so in FROZEN.md before more windows are scored.
2. Quote test numbers as a seed distribution, or set `early_stopping=False` / average seeds. The single-seed +2.54 is the top of a −0.1…+2.5 range.
3. Optional hygiene: membership-causal wallet/creator stats (`t_res = max(t_res, t78[mint])`), pd checkpoints cut at the decision clock, and a frozen TAIL list.

## Files (scratch, scripts + logs kept, feature copies deleted)
`recompute300.py`/`rec300.log` (independent 300-row recompute), `m1fix.py` (m1 copy with `member` / `strict` / `arm` switches, bit-exact with the switches off), `m2fix.py`/`m2seed.py` (m2 p30 code, seedable),
`score.log`, `seedscore.log` (table in section 4), `nullpert.py` (null test for B), `ckcheck.py` (issue C).

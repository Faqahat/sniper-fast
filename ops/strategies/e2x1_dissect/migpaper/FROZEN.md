# migpaper — FROZEN rule (written 10-28 23:35 PKT, before any scoring)

PAPER ONLY, LOCAL ONLY. No live sends, no server writes, no engine changes. Agent "migpaper".
Code: `/home/moiz/sniper/ops/strategies/e2x1_dissect/migpaper/` (mplib.py, mp_freeze.py, mp_score.py, mp_table.py, loop.sh).
Data: `/home/moiz/sniper-data/e2x1_dissect/migpaper/` (models/, wstore.npz, cstore.npz, cache/, out/results.jsonl, out/trades.jsonl, out/loop.log, val/).
Source rule: migrate/REPORT.md §7 (headline cell of §5). Nothing not written here is part of the test.

## Rule (exactly as REPORT.md §7)
1. Universe: pump.fun token whose CreateEvent is in the loaded tape and is **not mayhem**; SOL-quoted (a non-SOL migration is excluded).
2. Trigger: the **first** curve buy that takes vSOL to **≥ 105** without completing the curve (first crossing only, no re-entry; a crossing whose own trade completes the curve is not entrable). The crossing is the first recorded trade with vSOL ≥ 105 — if that trade is a sell (crossing trade missed by the recorder) the token is not entered (same as the replay).
3. Score with the **30-s graduation GBDT** (m2 code, 84 causal features, HistGradientBoosting depth 4 / lr 0.04 / 400 iter / min_leaf 40 / l2 1.0 / seed 0), **re-fit once** on every entrable non-edge crossing row of migrate's feat.pkl with block time **< 10-28 20:00 PKT** (= all tape rows before the cut; the tape runs 10-23 19:34 → 10-28 21:26 PKT). Enter only if **p30 ≥ 0.8**. The 2-min model (p120) is re-fit the same way because the predictor-drop stop uses it as a feature. Models are exported to plain numpy JSON (verified equal to sklearn's predict_proba), sha256 in the table below, **never refit during the run**.
4. Size **2 SOL**, both entry modes reported:
   - **reactive**: buy sent on seeing the crossing trade, lands d_e later (d_e = our live landing shape, livecal.json deltas rescaled to median 66 ms, 10 stratified quantiles: 23.3 / 32.5 / 41.3 / 50.4 / 60.2 / 73.8 / 89.2 / 113.2 / 143.3 / 216.9 ms), **+5 % guard** vs the crossing price; a late (curve already complete) or guard-reverted buy costs 0.3 mSOL.
   - **pre-send**: tries armed on the crossing of vSOL ≥ 100 (V−5), 5 tries per slot evenly spaced, 47-slot window, a try fills when it lands while the curve is in [105, 115] and not complete; every other landed try costs 0.005 mSOL; if the window expires before 105 is reached → reactive fallback (exactly m3_sim.py `pre`).
   - Each row is the **expected value over the 10 landing samples** (entry/exit delays paired as m3: (j, (3j+1) mod 10)).
5. Exit: if the curve completes → sell everything into **PumpSwap 2 slots after the migration tx** (+ d_x; pool state = reserves derived from the trade amounts, grad/glib.py rule, pool fee of the nearest sell). Else sell on the curve at **−20 % mark-to-market** (first recorded trade marking the position ≤ 80 % of cost, + d_x) or after **120 s** (+ d_x). A curve sell that lands after completion is held into the pool. If we complete the curve ourselves (2 SOL ≥ SOL left) we are graduated (fixed opening reserves if no migration recorded).
6. **Second row: predictor-drop stop** (`pd0.3`): sell when the continuation model (m3 code: GBDT depth 4 / lr 0.05 / 200 iter / min_leaf 50 / seed 0 on 12 checkpoint features incl. p120) says P(complete within 120 s) < 0.3 at the 10 / 20 / 30 / 60 / 120 s checkpoints; else the same 120-s timeout. Frozen with the other models (sha256 below); fit on the same rows (< 10-28 20:00 PKT) with leave-one-day-out p120 as its feature, as m3 did on train.
7. Costs: **2.9 mSOL per filled round trip** + the try costs above (= "as the replay models it"). Also shown: (a) **0.3 mSOL per landed try** for pre-send tries, (b) 0.005 mSOL per reactive revert (information).
8. Window mechanics (paper): every 2 h the loop decodes the recorder chunks covering [window − 3 h look-back, window + 15 min look-ahead], builds one tape, scores the crossings whose block time is inside the window. A token whose create is older than the 3-h look-back is not in the universe (0.7 % of the replay's entries were older than 2 h). Wallet / creator history features come from a store initialised from migrate's wallets.npz + grad's meta (through 10-28 21:26 PKT) and extended after each window with the trips of that window's tape (causal: only trips resolved before the crossing count, as m1). Positions still open at the tape end are marked at the last trade and flagged `unresolved`.

## Pass bar (REPORT.md §7)
≥ **+1.5 SOL/day over 3 PKT days (10-29, 10-30, 10-31) with each day ≥ 0**, on the headline row (pre-send 2 SOL, −20 % stop, replay costs); AND the replay of the same days within 30 % of paper. In this local test "paper" is the windowed scorer above; the "replay" check = the same days re-scored with the migrate pipeline on one continuous tape (no windowing, full token history) once disk allows (~1 GB temporary; deferred, see RUNNING.md). Reactive and the pd-stop rows are reported alongside, not part of the bar.

## Run
START 10-29 00:00 PKT (1793214000), 72 h → END 11-01 00:00 PKT (1793473200). Windows 2 h. Scoring of a window starts ≥ 25 min after it closes. Disk: footprint < 500 MB (cache pruned to the look-back), no scoring below 15 GB free, no server fetch below 20 GB free. STOP file: `touch migpaper/STOP`. Pid: `out/loop.pid`.

## Frozen artefacts (filled by mp_freeze.py before the first scoring)
(see FROZEN_SHA.md next to this file)

## Addendum (10-28 23:50 PKT, after the validation, before the first forward scoring)
- Feature vectors are cast to float32 before prediction (m1 stored float32; without the cast one validation row flipped at p30 0.7997 vs 0.8115).
- Artefact hashes: FROZEN_SHA.md (p30.json e2a35cf3…, p120.json 0abd92e9…, cont.json db313fdc…, dly.json, wstore.npz, cstore.npz).
- Validation of the scorer on 10-28: VALIDATION.md (per-row identical to the replay on all 52 shared entries).

## 10-29 00:30 PKT addendum: pre-send ARM-gate row (written before any scoring of it; no window of the run scored yet)
Owner OK 10-29 00:35 PKT. Motivation: migrate/LOOKAHEAD_AUDIT.md issue A — the existing pre-send row gates on p30 at the **crossing** trade,
but its resting tries are sent from the **arm** trade (before the crossing exists), so that gate is not implementable live (timing leak).
The existing rows (reactive / pre-send, −20 % / pd0.3), the models, the pass bar and the costs are **unchanged**. The new row is reported
alongside as **"pre 2 SOL ARM-gate"**, label `pre_arm`.
1. Universe and attribution: exactly the existing rows' — first entrable crossing of vSOL ≥ 105 (not mayhem, SOL-quoted, crossing trade
   a buy that does not complete the curve), counted in the window that contains the **crossing** block time.
2. Arm trade `a`: the first trade of the run of trades with vSOL ≥ 100 (= V − 5) that ends at the crossing (walk back from the crossing
   while the previous trade has vSOL ≥ 100) — the same index as `arm_k` in mplib `sim_row` / m3 `pre`, i.e. the pre-send arm point.
   If `a` = the crossing (vSOL jumped from < 100 to ≥ 105 in one trade) no tries are armed, the sim falls back to reactive and the gate
   is the crossing gate (causal for a reactive buy).
3. Gate: the same frozen p30 model (`models/p30.json`, seed 0, sha256 e2a35cf3… in FROZEN_SHA.md), evaluated on the 84 m1 features computed
   by `mplib.features` **at trade `a`** (strictly causal: only trades up to and including `a`; wallet / creator stores queried at the
   block time of `a`; V feature = 105, ncross = 0; float32 cast as in the 23:50 addendum). Enter iff **p30_arm ≥ 0.8**.
4. Everything else = the existing pre-send 2 SOL −20 % row: `sim_row(..., "pre")` (5 tries/slot from `a`, 47 slots, fill in [105, 115],
   reactive fallback), 2 SOL, exit mig+2 / −20 % / 120 s, 2.9 mSOL per round trip + 0.005 mSOL per landed try; 10 landing samples.
   Only the −20 % column is the row (the pd0.3 column of the same sim is stored but not reported: its p120 feature is crossing-time).
5. Known simplification (same as the existing pre row): arms that never reach an entrable 105 crossing (curve falls back, or the
   crossing trade completes the curve) are not scored; live they would cost only tries (0.005 mSOL each).
6. Not part of the pass bar (the bar stays on the existing headline row). Code: mp_score.py sha256 548d1d2c… (ARM-gate added, existing rows unchanged), mp_table.py 5ca12d8c…; validated on 10-28 vs the audit code (VALIDATION.md, ARM-gate section). RUNNING.md marks: reactive row = clean; pre-send (crossing-gate)
   row = known timing leak (LOOKAHEAD_AUDIT.md); ARM-gate row = clean pre-send.

# /root/strat: non-race pump.fun strategy search (PAPER / OFFLINE only)

> **STATUS — 2026-10-19 ~03:10 UTC. VERDICT: NOTHING IS POSITIVE OUT OF SAMPLE.**
> - **Tested:** every family in the brief (momentum, graduation on curve and after migration, dip/second wave, dev behaviour), plus late entries (5-20 min) and mayhem tokens.
> - **Bar:** test-fold mean > 0, ex-top3 > 0, n >= 40, at realistic cost.
> - **Result:** no rule meets it.
>   - Of 160,820 rule x exit combos with enough data, **0 are positive on both the train and the test fold** under the conservative cost model.
>   - Under the optimistic model, 12 are, all on mayhem tokens, where the curve's virtual SOL is not backed by real SOL. They are artefacts.
>   - The best rule selected on train in each family loses -4% to -13% per trade on test.
> - **Do not run any of these live.** No forward watcher was written, because there is nothing to forward-test. The closest candidates are listed at the end.
> - Nothing was sent. No `--live`, no keys touched, `.env` only sourced. RPC use: <= 4 concurrent requests with 429 backoff, ~117k calls in total.

## Bottom line
1. **Buying after launch is a structural loser at our cost.**
   - Take a screened entry at a fixed checkpoint (15-240 s after the create; vsol >= 36 SOL and >= 2 SOL of outside inflow). It loses on average **-8% to -25% per trade**, depending on the exit.
   - The median token is **-19% one minute later and -36% five minutes later**; 69% are down >= 30% by 5 min.
   - The visible momentum is the snipers' and bundles' exit liquidity.
   - The fee alone is 2.5% per round trip, and own impact adds 2-10%.
2. **Graduation after migration is not better.**
   - PumpSwap now charges **~1.2% per side** (LP 0.20% + protocol 0.05% + creator 0.80-0.95%, read from the swap events).
   - Graduates drift flat-to-up for 2-5 min, then most die: median **-80% to -99% within 20-60 min**.
   - Buying every graduation and selling at +2-5 min returns about **-2% to -3%** in both folds.
   - **"Single-tx graduations"** (~245/day; the whole curve bought in one tx, the pool pumped from 67 to 200+ SOL in 2 s) win 70-77% of the time, median **+2 to +14%**. But 18% are rugged by 5 min, so the **mean is -1% to -5% in every fold.**
3. **Mayhem-mode launches (~45% of all creates) are a separate regime.**
   - An AI-agent wallet trades them, the curve's k is not conserved, and the price often goes to ~0.
   - Their results have huge tails and flip sign between folds: e.g. train +84% -> test -13%.
   - **Their apparent upside is not real:** at vsol 85-120 SOL the curve holds only 0.0-0.6 SOL of real reserves (checked on chain).
   - The only combos that passed train and test under the optimistic cost model are mayhem rules, so they are artefacts.
4. **The only test-positive patterns are one-window flukes.**
   - Example: "vsol >= 70 at >= 60 s, rising, dev buy <= 1.5 SOL, TP 2x / SL 0.7x".
   - It is negative on train (-7%), and in the rolling folds positive only in one 1.3-h window (+25%; the other four folds run -6% to +0.5%).
5. **Trades/day is not the constraint.** Most rules fire 200-2,000 times a day, because launches are now ~2,200/h.
   - **The problem is the sign:** at -5% x 1 SOL x 1,000/day, that is about -50 SOL/day.
   - Even the "few good trades a day" version (tight filters, n 15-40) never held up in test.

## Data (all on chain, constant-k RPC, cached in this folder)
- **Universe A, "ds" (uniform, spread over time):** the uniform-random SOL-quoted launches of `/root/nob/ds.jsonl` with create slot >= 457.78M. That is 1,796 launches over ~38 h (2026-10-16 21:03 to 2026-10-18 10:58 UTC). Each one stands for ~30 creates.
  - The ledger no longer reaches the start of `ds.jsonl`: transactions before slot ~457.70M return "not found" (-32020). The real window is ~2.2 days, not 4.4.
- **Universe B, "truth" (complete census):** every create in `/root/det/truth_run.jsonl` (slots 458.540M-458.581M, 2.5 h, 2026-10-18 18:48-21:18 UTC): 5,536 creates (5,065 SOL-quoted). That is about 2,200 creates/h, ~93% SOL-quoted.
- **Per launch** (`pipe.py` -> `pipe.jsonl`):
  1. all signatures of the mint from the create to +600 s (`getSignaturesForAddress`, paged, anchored with a create signature at S+2780 slots);
  2. if >= 10 ok txs by 240 s: the create tx (dev buy, creator, SOL-quote check), then the curve state at 7 fixed checkpoints, 15/30/60/90/120/180/240 s after the create (state after the last ok tx at or before each checkpoint);
  3. if a checkpoint passes the screen (vsol >= 36 SOL and >= 2 SOL above the post-create state): the curve-state path from that checkpoint to +300 s after the last passing checkpoint. The path is the state after the last tx of every 5-slot bucket for ~28 s, then every 14 slots (~3 s). It always has the exact state at checkpoint+1 and +2 slots (our entry). Plus the creator's txs on the mint (dev sells).
- **Late extension** (`ext.py` -> `ext.jsonl`): launches still active around 5, 7 or 9-10 min get signatures to +30 min, checkpoints at 300/420/600/900/1200 s and 5-s-bucket paths to +600 s.
- **Price** = vsol/vtok from the pump TradeEvent after each tx. The fee is read from the events: **fee 95 bps + creator fee 30 bps = 1.25% per side** on every trade seen.
- **Mayhem-mode launches are ~45% of all creates now.** In them, one AI-agent wallet (`BwWK17cb...`) trades, and the curve's k does **not** stay constant: vsol falls to 0.03-20 SOL and the price collapses toward zero within minutes. They are flagged (`mh`) and analysed separately.

## Cost model (as specified)
- **Decision** only at the fixed checkpoints, using data at or before the checkpoint slot.
- **Entry** = the curve state after the last tx in slot checkpoint+2 (we land 2 slots later, behind every tx in that slot).
- **Exit decision** at an observed path point. It executes at the first observed state >= 2 slots later, or at the same state if no tx happened in between.
- **Fees and priority:** pump fee 1.25% on both legs; priority 0.0003 SOL + 5000 lamports base per tx.
- **Own impact, two models:**
  - **`pn` (primary, conservative, as the brief asks):** buy into the historical state, sell into the historical exit state. Own impact is paid on both legs. Round-trip floor at 1 SOL is ~-7.3% at vsol 40 and ~-4.5% at vsol 80; at 2 SOL, ~-11.5% at vsol 40.
  - **`pn2` ("shift", optimistic bound):** our buy stays in the curve. The exit state is the historical vsol plus our SOL. A token whose price did not move returns -2.56% (fees and priority only).
  - The truth lies between the two, closer to `pn2` when other traders size in SOL.
- **Exits tested** (17 in the main table):
  - time 10/20/30/60/120/180/300 s;
  - trailing stop 15/25/35% (max hold 120/300 s);
  - TP/SL 1.3x/0.8x (120 s), 1.5x/0.8x, 1.5x/0.7x, 2x/0.7x (300 s);
  - trailing stop armed after +30/50% with a hard stop.
- **Late table:** time 30/60/120/300/600 s, trail 20/30% (600 s), TP/SL 1.5x/0.75x and 2x/0.7x, trail-after-TP.

## Validation
- **Split A (primary, by time):**
  - fit on the earliest 60% of ds (~21 h, F0);
  - test on the last 40% of ds (~16 h, F1) plus the later truth census (2.5 h, F2).
  - "TEST" = F1 + F2.
- **Split B (reverse):** fit on ds-late, test on ds-early plus truth. A robustness check only.
- **Rolling folds:** ds in 3 time-thirds plus truth in 2 halves.
- **Trades/day** = fires in the fold x sampling weight (ds 30.25, truth 1) / fold hours x 24.
- **One position per token:** the first checkpoint at which the rule fires.
- **Rule grammar** (`search.py`): checkpoint window x vsol band x recent activity (txs in the last 15 s) x momentum (vsol change vs the previous checkpoint) or dip (vsol / max checkpoint vsol so far) x dev sold yet x dev-buy size x time since the last tx x mayhem flag. That is 71,280 filters x 34 exit/size variants = **2.4M combos**.
- **Selection:**
  - rank by the train-fold mean excluding the top 3 trades (n_train >= 30);
  - take the top 30 distinct;
  - count how many are positive in TEST (n >= 40, mean > 0, ex-top3 > 0).
## Results (all 1 SOL unless stated; "pn" = conservative two-leg impact, "shift" = optimistic bound)

### 0. Baseline: buy every screened launch at its first passing checkpoint (no selection)
Non-mayhem tokens: 610 (108 / 67 / 435 in F0 / F1 / F2). Mean return per trade:

| exit | F0 ds-early | F1 ds-late | F2 truth | all, shift model |
|---|---|---|---|---|
| time 10 s | -7.6% | -11.6% | -9.9% | -5.5% |
| time 60 s | -12.2% | -13.2% | -16.6% | -11.4% |
| time 300 s | -19.1% | -26.1% | -25.4% | -20.6% |
| trail 15% / 120 s | -10.8% | -16.0% | -14.3% | -9.8% |
| TP 1.3x / SL 0.8x / 120 s | -9.9% | -16.2% | -14.7% | -9.9% |

- **What happens after the entry** (shift model, non-mayhem):
  - the median token is at **-19% after 60 s** and **-36% after 300 s**;
  - **69% have lost >= 30% by 5 min**;
  - 11% reach 2x at some point within 300 s, but trailing stops and take-profits do not catch enough of that, after latency and costs, to pay for the rest.
- **The structure:** by the time a launch shows buying at a checkpoint, the creation-slot snipers and bundles hold large gains and sell into the new demand. The "momentum" we can see is mostly their exit liquidity.

### 1. Momentum continuation
- **Best on train** (of 7,854 variants with n_train >= 20): non-mayhem, >= 50 txs in the last 15 s, vsol rising, vsol >= 45, exit TP 1.3x / SL 0.8x / 120 s.
  - train **+4.5%** (n=30, median +22%);
  - **TEST -11.5%** (n=167, median -25%, ex-top3 -12.8%).
  - Shift model: train +8.2% -> TEST -8.2%.
- **Late version (entries at 5-20 min, `ext`):** the best on train (+4.9%, n=15) gives **TEST -13.4%** (n=70).

### 2. High curve / graduation
- **On the curve** (vsol >= 70-100 SOL at a checkpoint):
  - best on train: vsol >= 70, TP 1.3x / SL 0.8x;
  - train -6.1% (n=65) -> **TEST -4.2%** (n=247, median -5.0%); shift model -2.2%.
  - The price mostly goes nowhere, so the trade loses the fees.
  - "all" includes mayhem tokens, whose vsol >= 70 is mostly virtual (see section 7). Non-mayhem high-curve entries alone are no better.
  - Late version: TEST -8.9% (n=39).
- **After migration (PumpSwap):** see section 6.

### 3. Dip-buy / second wave
- **Best on train:** mayhem, vsol <= 0.85 x the max checkpoint vsol so far, max >= 45, TP 1.5x / SL 0.7x / 300 s.
  - train +25.4% (n=23, ex-top3 +7.8%);
  - **TEST -0.5%** (n=78, median -6.5%, ex-top3 -7.7%).
  - The test is +22.9% on ds-late (n=18) but -7.6% on the truth census (n=60). Shift model: TEST +2.7% mean but ex-top3 -4.4%.
- **Late version:** TEST -4.3% (n=89).
- **Non-mayhem dips** are worse.

### 4. Dev / creator behaviour
- **Best on train:** mayhem, the dev has not sold, time 60 s.
  - train +84% mean (n=41; ex-top3 +2.6%; one huge outlier);
  - **TEST -13.1%** (n=201, median -47%).
- **Non-mayhem rules** "dev has not sold" or dev buy <= 0.5 / >= 1 / >= 3 SOL never beat the baseline by more than a few points in any fold.
- **Not tested:** creator wallet history (prior launches, idle time). The race study found it useful for picking races at create time, which is the race problem, not this one.

### 5. Exhaustive rule search (multiple testing made explicit)
- **Searched:** 71,280 filters x 34 exit/size variants = **2.42M combos**. 160,820 had n_train >= 30 and n_test >= 40.
- **Conservative model:**
  - 340 were positive on train (mean > 0 and ex-top3 > 0);
  - 7 were positive on TEST;
  - **0 were positive on both**;
  - of the top 30 by train ex-top3, 0 were positive on test.
- **Shift model** (optimistic):
  - 2,040 positive on train; of the top 30 by train, 0 positive on test.
  - Robustness scan: 313 test-positive, **12 positive on both**.
  - All 12 are **mayhem** variants of 2 rules:
    - **M1:** mayhem, checkpoint <= 30 s, vsol >= 45, dev buy <= 1.5 SOL, sell after 10 s. TEST +3.0%, ex-top3 +0.2%, n=308.
      - Rolling folds (shift): +8.9 / +14.6 / +5.1 / +3.8 / +2.7%, but ex-top3 < 0 in every fold and median -2.5%.
      - Conservative model: +6.1 / +11.6 / +2.2 / +0.8 / -0.2% at 1 SOL; negative in 3 of 5 folds at 2 SOL.
    - **M2:** mayhem, checkpoint >= 120 s, vsol >= 70, TP 2x / SL 0.7x / 300 s. TEST +5.6%, ex-top3 +0.2%, n=113. Rolling folds -1.6 / +11.3 / +1.4 / +18.4 / -5.8%.
  - **Both are artefacts.** Checked on chain (`mhcheck.py`): in mayhem curves at vsol 85-120 SOL, the **real SOL reserves are 0.0-0.6 SOL** and k is 2.8-3.9x the standard.
  - The agent inflates the virtual reserves without real SOL behind them. A seller cannot be paid the constant-product amount, so the "upside" in these tokens cannot be realised.
- **Reverse split B** (fit on ds-late, test on ds-early + truth; conservative model): 71,808 combos evaluated; 57 positive on train, **0 positive on test, 0 on both**.
- **The 7 test-positive combos are all one family:** checkpoint >= 60 s, vsol >= 70, vsol up >= 3-6 SOL since the previous checkpoint, dev buy <= 1.5 SOL, exit TP 2x / SL 0.7x / 300 s.
  - Rolling folds (1 SOL): ds thirds **-6.4% / +0.2% / +0.5%** (ex-top3 -22 to -29%); truth halves **+24.8% / -1.6%**.
  - It is one good 1.3-hour window. It is negative on train and not a strategy.
### 6. Graduation plays after migration (PumpSwap), `grad.py` -> `grad.jsonl`
- **Universe:** every pump.fun migration tx (`MigrateV2`, account `39azUYF...`) from slot 458.35M to now (2026-10-18 07:23 to 2026-10-19 02:41 UTC, ~19.3 h).
  - That is 1,334 ok txs, 734 unique mints (the rest are retries); **441 had a normal pool** (67.4 SOL at migration).
  - ~550 graduations/day.
- **Price:** the pool's WSOL / token vault balances in the last pool tx before migration + {2, 5, 15, 30, 60 s, 2, 5, 10, 20, 30, 60 min}. Each point is anchored with a create signature at that time.
- **Costs:**
  - PumpSwap fees read from the swap events: **LP 0.20% + protocol 0.05% + coin creator 0.80-0.95% = ~1.2% per side** (not the 0.3% of a year ago);
  - constant-product impact on both legs, plus priority.
- **Decision at migration** (the token has just graduated; no look-ahead). Train = first 60% by time, test = last 40%.

**Baseline** (buy every graduation; 1 SOL):

| in -> out | TRAIN (n=261) | TEST (n=176) |
|---|---|---|
| +2 s -> +60 s | -2.6% (median -0.7%) | -2.8% (median -0.6%) |
| +2 s -> +120 s | -1.5% (median +2.1%, win 57%) | -3.2% (median +1.8%) |
| +2 s -> +300 s | -2.4% | -2.4% (median +1.0%) |
| +2 s -> +10 min | -15.0% | -12.3% |
| +2 s -> +60 min | -53.3% (median -99%) | -28.6% (median -96%) |

- **Sensitivity:** with 0.3% fees per side, +2 s -> +120 s is +0.3% train / -1.4% test. The shift impact model gives +0.3% / -1.6%.
- **Not positive in either fold.** Most graduates are dead (price -80% to -99%) within 20-60 min.

**Two kinds of graduation:**
- **"Single-tx graduations"** (curve completed by one tx in the 5 min before migration), **~245/day**:
  - The pool goes from 67 to >= 200 SOL within 2 s of migration, then drifts up for minutes. Win rate at +2 s -> +300 s is 68-72% in all three time folds, with a **median of +11 to +14%**.
  - **But 18% are rugged to < 0.3x by 5 min** (30% by 10 min), so the mean is **-4% to -5%**. At +120 s: win 71-77%, median +2 to +4.5%, mean -1% to -3% in every fold.
  - The pool size at +2 s does not separate the rugs (192 of 194 are >= 200 SOL).
  - This looks like a scripted pump-and-rug: the steady rise is bait.
- **"Organic graduations"** (>= 50 curve txs in the last 5 min), ~238/day: thirds +12% / -13% / +1% (+2 s -> +120 s). Unstable and tail-driven (ex-top3 -3.5 to -20.6%).
- **Selection grid** (pool SOL x pre-migration activity x early move x entry/exit delay x size): 4,292 combos with n_train >= 25. **0 had train ex-top3 > 0.** The best train means (+10% to +12%, n~35) give n=12 and ex-top3 -13% to -32% in test.
### 7. Mayhem-mode tokens (flag `mh`)
- **What they are:** ~45% of creates in the census. One wallet (`BwWK17cb...`, the agent) trades all of them; vs*vt drifts from 1.0x to 0.001-4x of the standard k.
- **Baseline** (first screened entry, 1 SOL): -4% to -24% mean depending on fold and exit. The ds folds show +14% to +36% means on long holds, with ex-top3 of -12% to -20%; the truth census is -14% to -24%.
- **Grid winners for mayhem** (dev not sold, dips, early entries) all collapse in test; see sections 3 and 4.
- **Verified artefact:** in mayhem curves the virtual SOL (85-120) far exceeds the real SOL reserves (0.0-0.6 SOL; `mhcheck.py`). Simulated mayhem profits from price jumps are not realisable by a seller. Every mayhem result here, positive or negative, should be read as "not tradable as simulated". Exclude mayhem launches (`mayhem` flag in the create args) from any curve strategy.

### 8. Late entries (5-20 min after the create, `ext`)
- **Universe:** 543 launches still trading at ~5, ~7 or ~9-10 min; 180 had an entry at a 300/420/600/900/1200-s checkpoint with vsol >= 36.
- **Non-mayhem first entry** (152 tokens): time 30 s -1.6% to -9.5%; time 300 s -26% to -33% (except +6.9% in F0, n=26); trailing 20% / 600 s -16% to -20% (F1, F2).
- **Best-on-train per family:**
  - momentum: TEST -13.4% (n=70);
  - dip: TEST -4.3% (n=89);
  - high curve: TEST -8.9% (n=39).
- **Full late-grid search:** 1.14M combos, but only 80 had n_train >= 30; 0 were positive on train or test.

## Closest candidates (none qualifies; listed so nobody re-runs them blind)

| candidate | train | test | why it fails |
|---|---|---|---|
| **A.** checkpoint >= 60 s, vsol >= 70, vsol up >= 6 SOL since the previous checkpoint, dev buy <= 1.5; TP 2x / SL 0.7x / 300 s; 1 SOL | -7.2% (n=31) | +9.7% (n=96) | All of the test gain is in one 1.3-h census half (+24.8%, n=37). ds thirds -6.4% / +0.2% / +0.5%, ex-top3 about -22% |
| **B.** single-tx graduation, buy PumpSwap at migration +2 s, sell at +120 s; 1 SOL | -3.0% / -1.1% / -2.6% (time thirds) | (same: all thirds) | Win 71-77% and median +2 to +4.5%, but ~5% are rugged within 2 min. Needs a rug predictor (the dumper's wallet and its token balance) that a 1-slot-late watcher cannot act on |
| **C.** mayhem dip (vsol <= 0.85 x the checkpoint max, max >= 45), TP 1.5x / SL 0.7x / 300 s | +25.4% (n=23) | -0.5% (n=78) | +22.9% on ds-late, -7.6% on truth. Tail-driven, and mayhem accounting is unverified |

## What it would take (if the owner wants to keep looking)
- **Rug prediction for single-tx graduations** (candidate B).
  - The edge would be knowing which ones dump within 2-5 min. The data to try: the wallet that completed the curve, its token balance and its history across earlier single-tx graduations; and the time-of-day pattern.
  - It is cheap to collect (one `getTransaction` per migration, plus the creator's past migrations). It is still a 1-2-slot reaction problem if the dump is a single tx.
- **Event-driven decisions instead of fixed checkpoints.** For example, enter on the n-th unique buyer, or exit on the first large sell after entry. That needs every trade, not bucketed paths.
  - The paths here have 1-3 s resolution (5 s in `ext`). The bigger losses are the dump dynamics, not the sampling, so I would not expect this to flip the sign.
- **Hours-to-days holds on PumpSwap survivors** (tokens alive after 1 h). Not tested, and outside "minutes".
- **A forward paper watcher would be simple if a rule ever qualified:**
  1. websocket `logsSubscribe` on the pump program, keep (vsol, vtok) per mint from TradeEvents and the tx counts;
  2. evaluate the rule at fixed checkpoints after the create;
  3. simulate the entry at the observed state + 2 slots and the exit by the same rules as `sim.py`.
  - It is not written, because nothing qualified.

## Limitations (honest list)
- **Decisions only at 7 (or 5) fixed checkpoints.** Paths are bucket-sampled (last tx per 5- or 14-slot bucket), so intra-bucket trades are not seen individually. There are no unique-buyer counts.
- **Exits fire on the next observed state** >= 2 slots after the trigger (often 1-3 s later). That is conservative for stops in dumps.
- **The ledger window is ~2.2 days**, not 4.4: transactions before slot ~457.70M are gone from this RPC. The ds sample covers ~38 h; the truth census 2.5 h; graduations 19 h.
- **The truth census is 2.5 h of one afternoon**, so fold F2 is a single regime. That is why rolling folds are also reported.
- **A rule is "first checkpoint that fires, one position per token".** Capital limits and overlapping positions are ignored; they do not matter when the sign is negative.

## Files (`/root/strat/`)
- **Collectors:**
  - `srpc.py`: RPC wrapper, <= 4 concurrent, 429 backoff.
  - `pev.py`: TradeEvent/CreateEvent parser, including fee bps.
  - `sigs.py`: phase-1 signatures (first try, superseded).
  - `pipe.py`: main per-launch pipeline, writes `pipe.jsonl`.
  - `ext.py`: late extension, writes `ext.jsonl`.
  - `anchors.py`: recent create-signature anchors, writes `anchors.jsonl`.
  - `grad.py`: migrations + PumpSwap pool states, writes `grad.jsonl` and `grad_anchors.json`.
- **Simulation:**
  - `sim.py`: curve maths, entry and exit simulation, both impact models.
  - `table.py`: writes `table.pkl` (main per-checkpoint feature + PnL table).
  - `table_ext.py`: writes `table_ext.pkl`.
- **Analysis:**
  - `search.py <table> <pn|pn2> <A|B>`: rule search, train -> test, robustness scan.
  - `families.py <table> <model>`: best-on-train per family, judged on test.
  - `folds.py <table> "<lambda f: ...>" <model>`: rolling time folds for one rule.
  - `diag.py`: what happens after an entry.
  - `basefold.py`: baseline by fold.
  - `search_both.py`: lists the combos positive on both train and test.
  - `gana.py` / `gana2.py` / `gana3.py`: graduation analysis.
  - `mhcheck.py`: mayhem real-vs-virtual reserves check.
  - `uni*.py`, `floor.py`: exploration only (pooled, not used for any claim).
- **Outputs:** `res_*.txt` hold the full printed results quoted above.

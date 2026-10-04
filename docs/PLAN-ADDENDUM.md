# PLAN addendum (2026-10-04): venue-maths parity and on-chain sizing integration

Added after the on-chain sizing work (commit b614ca0, `program/arbx-sizing` + `program/venue-harness`). That work validated exact integer quotes against the REAL mainnet venue binaries in LiteSVM: 46,589 exact comparisons, 0 mismatches. It also showed that the engine's own venue maths in `src/venues` deviates from the real programs (program/arbx-sizing/DESIGN.md §2.7). These two WPs fold that into the engine plan. Merge them into PLAN.md when the core lane is not editing it.

## WP-16: Venue-maths parity (engine prices with the validated maths)

- **Goal:** one pricing implementation, the one proven against the real binaries, used both on chain and off chain.
- **Evidence:**
  - `src/venues/cp.rs` PumpSwap buy:
    - It is missing the `buy_exact_quote_in` fee-overrun adjustment and the "−1" in base-out.
    - It reads the virtual reserve as 8 bytes, but the field is 16.
    - Its `p[270]` check reads a counter.
    - It ignores the held-back amounts at bytes 271/279. Their effect: sells above `Q − held` fail with error 6063, and buys fail with error 6023.
    - The program debits `min(x, eff0 + fees(eff0))`.
  - Raydium CPMM with the creator fee on the input: the engine rounds twice, while the program rounds once on the summed rate. The engine also never checks the pool's open time.
  - DLMM 0.12: the engine ignores limit-order layers, fee-on-output pairs, the bitmap jump to the next array with liquidity, and the pair's own `min_bin_id`/`max_bin_id`. Ignoring limit orders understates bin capacity, which mis-predicts post-swap prices.
  - DAMM v2: the engine has no rate-limiter refusal for b→a.
- **Design:**
  - Make the `arbx-sizing` crate a path dependency of the engine. It has zero deps and is `no_std`, so this is cheap.
  - Route all quoting through it: `best_cycle`, route pricing, sizing, the prediction/accuracy monitor and caps.
  - Keep `src/venues` only for decoding and the instruction builders, or delete the quote code it duplicates.
  - Every refusal state the crate defines (Budget, Abort, held amounts, rate limiter, Token-2022 transfer fee) becomes an engine skip with a recorded reason.
- **Tests:**
  - Differential tests: old engine maths vs crate on recorded states, with the expected deviations documented.
  - The venue-harness exactness suite runs in engine CI on the fixture snapshots.
  - Replay scenarios S1–S16 re-run with crate pricing.
- **Measurement:** per-venue prediction accuracy, computed by the WP-04 monitor against the version just before each transaction. Expected to rise, for example DAMM v2 from about 87% exact.
- **Dependencies and effort:** after WP-04 (state consistency); before or with WP-06 (builder uses the crate's capacities for the DLMM cap). About 2–3 days.

## WP-17: On-chain sizing in arbx-exec (SELF_SIZE / BASKET), off by default

- **Goal:** wire `arbx-sizing` into `arbx-exec` behind a `sizing` cargo feature, and into the engine behind a config flag (default off).
- **Program side:**
  - Parse the sizing block after the v3 leg descriptors. This includes the per-DLMM-leg `max_bins` and the LAMPORTS flag with `lamport_offset`.
  - Run `plan()`, then execute the chosen size or the best basket pair.
  - Keep the guard as the backstop: a miss still reverts, and EARLY_ABORT and SHADOW are optional.
  - Add `cu_bound(block)` to the CU limit.
  - Code-size budget: build with only the venues in use, plus LTO.
- **Engine side:**
  - Emit the sizing/basket block. Set each DLMM leg's `max_bins` with `bins_for`, at least covering the engine's amount `e`.
  - Set LAMPORTS whenever EARLY_ABORT is combined with COUNT_LAMPORTS.
  - Choose candidates for the basket.
  - Record `sizing_outcome` (Fallback / NoProfit / Shadow / Sized), the chosen size and the CU per landing, decoded from the program's logs.
- **Tests:**
  - DESIGN.md §6.3 route assertions through arbx-exec on the real venue binaries: modelled profit equals realized profit, never worse than `e`, refusals behave.
  - CU and transaction-size budgets.
  - SHADOW mode on replay.
- **Gate to enable live:**
  - Experiment X3 (replay of would-fail bundles at smaller sizes): at least 30% profitable at a smaller size and at least 0.05 SOL/h.
  - Then a SHADOW canary.
- **Dependencies and effort:** after WP-06 (builder), WP-15 (arbx-exec integration) and WP-16. About 3–4 days.

## WP-18 / experiment X10: multi-region Jito bundle submission

Added 2026-10-04 at the owner's request.

- **Goal:** find out whether sending the same bundle to more than one Jito block-engine region:
  - improves landing and latency on leaders far from Frankfurt;
  - raises our effective bundle rate.
- **Evidence and hypotheses:**
  - Today every bundle goes only to `frankfurt.mainnet.block-engine.jito.wtf`.
  - Bundles on far leaders landed slower (wallet-synthesis §7; small n).
  - The 5/s client limit dropped 1,020–1,027 of 7,643 bundle attempts (13%).
  - Jito documents a default limit of 1 request/s per IP **per region** (data/sender-tip-accounts.json `jito.features`). EU regions are Frankfurt, Amsterdam, London and Dublin; others exist worldwide.
  - **Unverified:**
    - whether our authenticated limit is also per region;
    - whether duplicate submissions of one bundle count against more than one limit;
    - how each region's auction treats a bundle already seen by another region.
  - Landing twice is impossible: the same signed transaction can land at most once, and the tip is in it. Duplicates only risk extra would-fail verdicts and rate usage.
- **Design** (behind `[send] regions = ["frankfurt"]`, default unchanged):
  - **Region clients:** one Jito client per configured region, each with its own auth token, cached token refresh and rate budget (send/budget.rs per region).
  - **Region policy** `region_policy`:
    - `primary_only` (default);
    - `all`: fire to every configured region;
    - `leader_nearest`: Frankfurt plus the region nearest the target slot's leader, using leader geography and RTT from the WP-08 LeaderBook.
  - Fan-out happens on the send path with no extra network round trip before the first send. The other regions follow in parallel.
  - **Verdicts:** every region's verdict history is recorded per bundle (WP-05 item 7, keyed by region). Landing is attributed by the processed region and validator when Jito reports it, otherwise by first acceptance.
- **Measurement** (extends MEASUREMENT.md; bundles/copies gain a `region` field):
  - per region × leader kind (Jito/BAM) × leader location: accepted, would-fail, landed, send→ack ms, send→seen ms, over-rate;
  - region-level rate-limit errors;
  - duplicate-verdict patterns.
- **Experiment X10:**
  - Randomly assign `primary_only` vs `leader_nearest` (later `all`) per attempt, at least 400 eligible attempts per arm, run alongside X5 (BAM landing).
  - **Go:** landed/attempt on non-Frankfurt leaders improves by ≥ 20% relative, or `rate_queue_timeout` drops ≥ 50%, with no loss on Frankfurt leaders.
  - **No-go:** keep `primary_only`.
  - Before going live, confirm the per-region rate limit with a shadow/keep-alive probe and Jito's docs, and log the probe's result.
- **Dependencies and effort:** after WP-05 (send policy, verdict history) and WP-08 (leader geography); runs with WP-11's experiment framework. About 1.5–2 days.

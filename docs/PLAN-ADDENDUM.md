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

## WP-19 / experiment X11: revert-protected non-Jito senders

Added 2026-10-04 at the owner's request.

- **Goal:** find out whether any non-Jito sending path:
  - can carry our routes **without paying fees when the route fails** (revert protection);
  - lands what the Jito path does not: BAM leaders, non-Jito leaders (1.3% of slots, reachable only outside Jito), or faster landings.
- **Evidence:**
  - **Our unprotected direct copies failed.** They landed 986 times with 1 win and about 24.4M lamports of fees, landing 137–170 ms after send. The untipped Haan or tpu-direct copy landed first in about 2/3 of attempts (wallet-synthesis §2, §4).
  - **Rivals do win on non-Jito paths, but with revert protection or order flow.** 9EwQoN74's priority path and 8oSD5a9E's no-tip path never fail, land only on non-BAM Jito-client leaders, and are not in Jito's explorer. The service behind them is unidentified (Harmonic is an inference). Mriya's priority path is order-flow sequencing (rival-synthesis §4).
  - **Relays wrap.** Helius, BlockRazor and Speed land some copies as 2-transaction Jito bundles, so they are partly Jito underneath.
- **Candidates and what their documentation claims** (`data/sender-tip-accounts.json`; not yet verified by us):

  | Service | Bundles | Revert protection (claimed) | Access | EU endpoint |
  |---|---|---|---|---|
  | Harmonic | yes (gRPC, whitelist) | yes (bundles) | free, whitelist | fra.be.harmonic.gg |
  | Temporal Nozomi | yes (1–4 atomic) | bundles only | free self-serve key | fra2.nozomi.temporal.xyz |
  | BlockRazor | yes (≤4, on request) | bundles all-or-nothing | free key, 3 TPS | frankfurt.solana.blockrazor.xyz |
  | NextBlock | yes | `revertOnFail` flag | trial 1 tx/10 s; $249+/mo | frankfurt.nextblock.io |
  | Hello Moon Lunar Lander | yes | bundles | key via Discord | fra.lunar-lander.hellomoon.io |
  | Astralane Iris | VIP tiers only | not documented | key; free 5 TPS | fr.gateway.astralane.io |
  | bloXroute | yes | not documented | free tier | germany.solana.dex.blxrbdn.com |
  | Helius Sender, Falcon, Paladin P3, 0slot | — | no / not documented | — | excluded unless a later doc shows revert protection |

- **Steps:**
  1. **Documentation and probe (free, no transactions).**
     - Confirm each service's revert-protection semantics. Does a failing bundle or transaction never land? Who pays what on a miss? Are the tips conditional?
     - Confirm its rate limits and whether it forwards to Jito (if it only forwards to Jito, it adds nothing over our Jito path).
     - Keep-alive RTT from Cherry with `arbx senders`.
     - Record each conclusion in `docs/research/senders-x11.md`.
  2. **Shadow measurement (free).** From the WP-02/WP-08 recorder's transfer classification, attribute rivals' landed wins and failures to each service, by leader kind (Jito / BAM / non-Jito). This shows which non-Jito paths actually land winning arbitrage, and whether their failures ever land (which would disprove revert protection).
  3. **Revert test (small live, owner approval needed).**
     - For each service that passes steps 1–2, send N ≥ 30 routes built to fail our profit check (`min_profit` above any achievable gain).
     - **Pass:** 0 of N land, and the wallet pays 0 lamports.
     - **Any landing:** the service is rejected for unprotected use.
     - Budget cap: the worst-case fee of N unprotected landings, about 30 × 25k = 0.00075 SOL per service.
  4. **Landing A/B.** For services that pass, randomly assign eligible attempts to Jito vs the service. Prioritise BAM leaders, non-Jito leaders, and leaders far from Frankfurt. Measure accepted, landed, send→seen ms and wins per arm, with at least 400 attempts per arm.
     - **Go** (enable for that leader class): landed/attempt better than Jito by ≥ 20% relative on that class, and 0 paid failures.
     - **No-go:** keep bundle-only.
- **Design:**
  - A `SendKind::ProtectedBundle { service }` path, separate from the unprotected direct kinds.
  - Allowed in live only when `[send_policy] protected_services` lists the service and its step-3 revert test is recorded as passed (`docs/research/senders-x11.md` + a config hash pin).
  - Per-leader routing (WP-05 leader kinds + WP-08 geography) picks Jito vs a protected service.
  - Per-service rate budgets and token handling, mirroring WP-05.
  - Recorder: per-service verdicts and landings (`copies.service`, `bundles.service`).
- **Owner actions:** API keys or whitelisting (Harmonic whitelist, Nozomi key, BlockRazor key, NextBlock plan, Lunar key), and approval of the step-3 test.
- **Dependencies and effort:** after WP-05 (send policy), WP-08 (classification, leader geography) and WP-11 (experiment framework). About 2–3 days of engineering, plus owner time for keys.

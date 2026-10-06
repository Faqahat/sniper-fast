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
- **As implemented (lane/wp-16):**
  - `src/quote.rs` parses every leg with the crate's per-venue `parse` from the store's bytes and quotes with it: `price_route`/`evaluate_pool` (the ladder, then `opt::locate`'s optima where a rung makes money, all exact, capped at the top rung), `route_in`, `probe_routes`/`refresh_route`, `record_caps`, `hint_check` and `accuracy::predict`. `src/venues` keeps the swap decoders; the old maths moved, tests only, to `src/venues/legacy`.
  - Refusals are route reasons `sz_*` with counters (MEASUREMENT A.1/A.7). The DLMM walk budget is the CU limit (200 bins read; 100 each for DLMM ↔ DLMM). The state stream also follows PumpSwap's GlobalConfig and every Token-2022 mint of a watched pool (other parts of the pool).
  - The crate gained `DlmmLeg::fills` (the exact swap bin by bin, host-only) for the engine's CU inputs, the builder's end bin and the DLMM post-state.
  - Tests on recorded states (`src/quote/tests.rs`, testdata/venue-parity: the venue-harness fixtures and 1,316 real swaps captured by its new `capture_post`): the engine's quotes equal the real programs on all 1,252 it quotes (56 refused `sz_transfer_fee`); the legacy maths deviates exactly in DESIGN.md §2.7's classes; the accuracy monitor's predictions are exact on every swap it predicts (legacy, over the snapshots and the harness's byte mutations: PumpSwap 33%, CPMM 58%, DLMM 74%; DAMM v2 and AMM v4 unchanged: their old maths is exact on these swaps, so DAMM v2's 87% (arb-lab's at-hint measure, res-code §3) is the hint-time state WP-04's pre-state scoring removes, not the maths). The DLMM legacy outputs were above the program in 34 of 216 swaps, by up to 1.2% (limit orders, the fee on the output): phantom gaps of the I-8 kind.
  - Not done here: replay scenarios S1–S16 with crate pricing (WP-09 has not built them yet); the production per-venue accuracy (needs a segment recorded with this build).
  - At the merge into master (after WP-05 and WP-09): the WP-09 scenarios (S1–S8, S9, S11, the replays) run on the crate's pricing. Their third-party trades keep the old maths (`venues::legacy`), so their inputs did not change, and they now hold PumpSwap's GlobalConfig (real bytes from two of this lane's captures). Two expected files changed. In S5, one route is 2 lamports lower: the PumpSwap buy delivers 909 fewer raw tokens (DESIGN §2.7 item 1). In S7, two AMM v4 → CPMM sizes moved by under 0.1%: the locator's optimum, with the same quotes under both maths, 0 and 3 lamports from the old pick, within DESIGN §3.1's ε. The executor's expected profit is now the decisions' quote delta (`RouteIn.spent`, the buy leg's debit), and `arbx quote` / `--reprice-sizes` price through the crate as well.
  - Review fixes (`docs/reviews/WP-16-review.md`, Disposition): PumpSwap pools are read at every length the program reads (211..=301 bytes, each missing trailing group as zero, pinned per group on the dumped binary) and byte 270 is `is_holder_reward` (0 or 1): the 300-byte and holder-reward pools of the census are priced, exact on the real program; mayhem pools are priced (market cap on the fixed 1e15 supply, pinned); the exact-out `buy` has its closed form (hints and the accuracy monitor; other venues' exact-out predictions are marked `solved` and kept out of the per-venue rate). The harness checks every refusal against the venue (a false refusal fails like a mismatch) and its fixtures carry the census's classes (300-byte, holder-reward, mayhem, cashback, 287-byte pools). The engine records its boot drops (`pools_dropped`, meta.json `pools.dropped`), names the crate's reasons on the hint, probe and monitor paths, parses each pool's legs once per evaluation and stops a route's ladder at its first falling rung (p50 at master's level again).

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

## Issues found in live shadow tests (2026-10-04)

- **I-1. A boot snapshot RPC error is fatal.** During the side-by-side shadow test (`cmp2`, Cherry, 13:20 UTC), arbx `e2b8fa5` exited at boot:
  - error: `shyft getMultipleAccounts: reading reply: error decoding response body … stream error received: unexpected internal error`;
  - log: `runs/cmp2-arbx-crash1.out` on Cherry;
  - sequence: the snapshot failed over from Haan (rate-limited by the other bot's snapshot moments earlier) to Shyft, which returned a broken HTTP/2 stream;
  - the old bot booted fine seconds earlier.
  - **Fix (WP-03b, `call_bounded` + boot policy):** boot-time snapshot calls retry with backoff across providers, and only a sustained failure aborts, with a recorded stop reason. A test should inject a provider body error.
- **I-2. Haan gRPC outages are transient.** The account-subscription stream returned 503 for about 3 minutes (13:01–13:04 UTC), for both bots and for one bot alone. It then recovered (probe 13:17). Reconnect with backoff already works; the gRPC probe (WP-03) and feed-health recording (WP-02) should make such outages visible in the segment report.
- **I-3. Haan grants its streams to the first process only** (cmp1, haan-probe-1, cmp2; `docs/research/cmp2-shadow-comparison.md`).
  - While the old bot held its three Haan streams, all three of arbx's got 503 for 28 minutes; alone, arbx connected at once.
  - **Fix:** a separate Haan token for arbx (owner, with Haan; also ask for the concurrent-stream limit).
  - The supervisor (WP-01 `run-w.sh`) waits until the previous segment's process has exited before starting the next one.
  - The WP-03 gRPC probe records 503s per stream, separately from other errors.
- **I-4. There is no state-health gate: arbx ran blind for 28 minutes and exited 0.**
  - store_updates stayed at the boot snapshot, slot stayed 0, and there was no warning.
  - A reconnect never re-snapshots (feeds/mod.rs:208-235).
  - **Fix (WP-04, with WP-05's send gate):**
    - Stop with reason `state_unavailable` if no state update arrives within N s of boot.
    - Price and send nothing while the stream is down or the newest update is more than about 2 s old.
    - Re-snapshot after a reconnect.
    - Status gains `state_connected`, `last_update_age_ms` and `reconnects`, and a WARNING line is logged.
- **I-5. Signer stats count false misses whenever state is down, and one file is shared across runs and bots.**
  - A pending trigger becomes a miss after 5 s unless a state update credits it (engine.rs:440, 976).
  - cmp2 wrote about 3,430 false misses into arbx's file. The old bot's cmp1 run wrote up to about 146 into the live arb-lab file.
  - **Fix (WP-04):**
    - Count a miss only while state is healthy, or better, decide the outcome from the transaction's own status.
    - Read the boot copy, and write each segment's copy into the run dir. Merging back is an explicit step.
    - Record the sha256 of the copy that was read.
- **I-6. A failed lookup-table fetch marks the table missing for the whole run** (engine.rs:595).
  - In cmp2 arbx dropped 5,001 transactions as `alt_unknown`, against the old bot's about 610. It started with an empty cache during an RPC 429 burst.
  - **Fix (WP-04, already listed there):**
    - Retry with backoff.
    - Cap concurrent fetches.
    - Preload the previous segment's `alts-final`.
- **I-7. Shadow mode builds no executor**: `exec_on = sim.enabled || canary || live`.
  - So no send gate runs and no would-send decision is recorded, and the cmp2 policy figures had to be replayed offline.
  - **Fix (WP-05):** shadow runs every send check up to the signature and writes `decisions.jsonl` / `attempts.jsonl` with `sent = false`.
- **I-8. Pricing errors that WP-04 must remove** (cmp2, old bot, 937 opportunities quoting 104.6 SOL):
  - 198 phantom (failed trigger, 65.09 SOL);
  - 62 poisoned (the other pool priced against a failed swap's prediction less than 1.5 s old, 33.76 SOL);
  - only 655 clean opportunities, quoting 4.43 SOL in all;
  - 57 opportunities sized at the 8.4 SOL ladder edge carry 98.13 SOL of the quotes, and 49 of them are phantom or poisoned;
  - quotes of 10M lamports and above realize about 55%.

  Keep the 4.2 SOL size cap and the ≥1M throttle until WP-04/WP-16 pass replay.
- **I-9. Recorder volume.**
  - 736 MB in 28 minutes, 88% of rivals.jsonl being `why = venues` rows: about 66 GB/day raw, or about 17 GB/day at zstd-3.
  - **Fix:** WP-02's compression and rotation, plus sampling of `why = venues` rows (WP-08), checked against the disk budget in MEASUREMENT §5.
- **I-10. Credentials in clear text on send paths** (`docs/research/sol-trade-sdk-audit.md`, addendum).
  - SpeedLanding's HTTP API takes a keypair **secret** as `?apikey=`. The live arb-lab config sends it over http:80, and Nozomi, Astralane and LandX keys also travel over http.
  - **Owner (2026-10-04): resolved.** SPEEDLANDING_KEY is not a wallet private key. The trading wallet's key is only in the owner-managed encrypted keystore (`.enc`).
  - **Fix (WP-05 / WP-19):**
    - A sender may carry a secret only over TLS/QUIC or in a header.
    - The config check refuses an `http://` URL holding `${...KEY}` unless the provider has no TLS endpoint, and the exception is recorded.
    - A provider key that is a keypair must be a dedicated keypair, and the config check refuses one whose pubkey equals the payer.
- **WP-19 corrections and additions (same report):**
  - BlockRazor has a per-transaction `revertProtection` flag; test it on `/v2/sendBinaryTransaction`.
  - Astralane's `revertProtection` on sendBundle needs a VIP tier.
  - Add Helius Sender Max sendBundle and AllenHark Relay `/v1/sendBundle` as candidates.
  - HelloMoon's Lunar Lander client rejects arbitrage programs per key (`BlockedArbProgram`).
- **WP-08: tip-account map.** Add Glaive, Soyas, SpeedLanding, AllenHark, Solami, the bloXroute legacy accounts (HWEoBx…, 95cfoy… = bloxroute1.sol) and the SVS legacy accounts to `OTHER_TIP_ACCOUNTS`. In cmp2, 4,197 rival transactions tipped Glaive and were recorded as unknown.
- **X12. Lane race (clean-room, after WP-19 step 3).**
  - Each round sends N copies under one durable nonce (System, ComputeBudget and Memo instructions only), from a dedicated test wallet.
  - Arms: A = unprotected lanes, B = protected lanes, C = built-to-fail.
  - About 400 rounds per arm; hard stop at 0.15 SOL.
  - Needs owner approval and a top-up. Never through any third-party SDK (owner rule, 2026-10-04).

## Go-live gate (owner plan, 2026-10-04)

**Owner's plan:**
- No new keys are set until arbx is **actually ready for live**. The owner is told when it is.
- At go-live the owner sets all keys and funds a wallet with **$80**: about 0.67 SOL at the $119/SOL the configs assume.
- **$500** (about 4.2 SOL) follows once the bot turns small profits.

**"Ready for live" means all of the following:**

1. **Code.**
   - WP-04, WP-03b, WP-16, WP-05, WP-06 and WP-07 are committed with reviews. WP-09 scenarios S1–S16 pass. All tests are green, and `arbx check` passes on the canary config.
2. **$80 canary config** (`deploy/arbx-canary-80.toml`).
   - Bundle-only, on the deployed Nexus program 8K8uyQDt. No program deploy: arbx-exec waits until after the $500 stage, since its rent is about 0.35–1 SOL.
   - Size is capped by the bankroll: min(cap, 85% of liquid SOL + WSOL − 0.03 SOL reserve).
   - **OD-11 (proposed):** equity stops. Shadow if equity drops more than 0.02 SOL in a rolling hour, or falls below 90% of the starting equity, campaign-wide (WP-07).
   - New token accounts only through WP-06's **rent-neutral create+close inside the same atomic transaction**. The rent comes back in that transaction; a failed route reverts everything; nothing stays locked. This was the best-evidenced lever in STAGE1-PLAN.
   - Until WP-06 lands, only routes whose token accounts already exist can trade (frz: WSOL and USDC).
   - Optionally, a wallet-prep step creates accounts for the top-N mints at 1,488,440 lamports each (SPL) or 1,513,840 (Token-2022), recoverable.
   - The I-10 credential checks pass.
3. **Field: a shadow soak on Cherry with the final build, at least 3 h, with Haan alone** (the old bot not running), no trading keys. It must show:
   - the state gate never fails open, and boot survives provider errors;
   - 0 core and replay record drops;
   - would-send decisions recorded with `sent = false`, with a chain-truth check of the would-send set (share real vs phantom);
   - a 1 h recording that replays identically.
4. **Send dry run.** At least 100 would-send bundles are signed but not sent, or simulated, with their size, tip and accounts checked.

**Scaling to $500 requires all of:**
- at least 48 h live;
- net ≥ 0 after all costs;
- hourly reconciliation clean;
- 0 non-bundle sends;
- evidence that real opportunities were capped by the $80 size limit. Otherwise $500 adds risk, not profit.

## I-11. arbx is standalone (owner, 2026-10-04)

arbx has no runtime, build, test or tooling dependency on arb-lab, either locally or on Cherry. Mentions of arb-lab as history (what changed and why) stay; anything operational does not.

**Done (this commit):**
- Removed `tools/analysis/`: arb-lab's one-off scripts, all hardwired to `/root/arb-lab`. Their findings are kept in `docs/research/PATTERNS.md`, moved here.
- Repointed `tools/haanrpc.sh`, `tools/pooldisco` and `tools/rpc_latency.py` to `/root/arbx` and arbx's own `.env`.

**After E2's merge** (those files are being edited now):
- `deploy/arbx-stage0.toml`:
  - `wallet_keystore` → `/root/arbx/wallets/trading.enc`. The owner places their `.enc` there at go-live; arbx never reads arb-lab's.
  - The `.env` is `/root/arbx/deploy/.env`, beside the config, mode 600, created by the owner at go-live.
- `deploy/arb.toml` is arb-lab's shadow config, with every path in `/root/arb-lab`. Retire it to `deploy/legacy/`, or repoint it to `/root/arbx`, and update the tests and the `arbx check` list to match.
- Cosmetic names in src: the temp dir `arb-lab-key-*` in send/jito.rs and `arb-lab senders --probe` in send/mod.rs.
- PLAN.md operational notes: "tools/analysis stays as history"; "copy arb-lab's signer stats".

**Rules from now on:**
- Signer stats start empty: nothing is copied from arb-lab. They are learned per segment (I-5).
- Every file a test reads lives in the repo (`testdata/`). A test that needs a file outside the repo is a bug.
- Agent briefs name only in-repo fixtures.

### Update (owner, 2026-10-05): the frz wallet and a pre-approved test budget

- Live tests use the production wallet **`FRZh63L6…`** ("frz", ≈ 0.414 SOL ≈ $60). This replaces the $80 figure above. The $500 stage still follows small profits.
- The **test budget is $3–5**: hard cap 0.034 SOL, target ≤ 0.021 SOL. It is pre-approved: once gate items 1–4 pass, live tests within it run without asking again. "Never drain it."
- Every test is documented in `docs/field-tests/` (protocol, entries `FT-NNN`, `BUDGET.md` ledger).
- The equity floor = starting equity − remaining budget.
- The owner expects the **win ratio to rise a lot in Stage 1**. The Stage 1 plan, focused on win ratio, is `docs/STAGE1-PLAN.md`.

## WP-20: Alerts (Telegram) and watchdog (owner request, 2026-10-05)

**Goal:** the owner is told at once about wins, errors and anything else worth knowing, and whether the bot is running or not, in the Telegram group "ArbX".
- The token and chat id live only in `/root/arbx/deploy/.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`), never in the repo. `tools/secret-scan.py` blocks bot tokens.
- Until WP-20 is deployed, the operator's segment watcher posts test alerts.

**`src/alerts.rs`:**
- A non-blocking sink: a bounded channel with `try_send`; when the channel is full the alert is dropped and counted.
- One sender task on `rt_bg` posts HTTPS `sendMessage` (parse_mode HTML).
- Per-chat rate limit (≤ 20/min), with retries that honour 429 `retry_after`.
- Bursts are coalesced into one message, and repeated alerts with the same dedup key are suppressed (default 600 s).
- Counters go in status (`alerts.*`) and events in `events.jsonl`.
- The token is never logged, recorded or shown in meta.json; https only (I-10).

**Events:**

| Kind | When |
|---|---|
| Lifecycle | segment start (mode, build, config hash, short wallet, budget); stop (reason, duration, decisions, opportunities, sends, wins, net); crash (a panic hook sends Critical, best-effort, with a short timeout) |
| Health | state stream down or up; a re-snapshot that does not land; Haan 503 or 429 storms; recorder drops, I/O errors, dead writers and disk-ladder steps; chain fetch dead; Jito auth or token failures; stale blockhash; SendGate changes, with the reason (budget or equity floor, hourly cap, reconciliation miss) |
| Money | **win**: route, mint, size, net, tip, slot and a solscan link, via `alerts::win()`, which the WP-05 settlement calls (wired at the merge); a failed landing (Error); budget or equity floor reached (Critical); low balance |
| Periodic | a heartbeat every `heartbeat_min` (default 60) with the key numbers; a daily summary at 00:00 UTC (wins, net SOL, sends, win ratio per send, budget left) |

**Subcommands:**
- `arbx watchdog` is a separate long-running process on Cherry. It holds a single-instance lock and watches `/root/arbx/runs`:
  - "✅ running" every `status_min` (default 60);
  - "❌ not running" when no segment process has been alive for more than `grace_s` (default 120 s, which covers gaps between segments), or `status.jsonl` is more than 60 s stale;
  - "✅ back up" when it recovers.
- `arbx alert-test` sends one test message.

**Config:**
- `[alerts] enabled, token_env = "TELEGRAM_BOT_TOKEN", chat_env = "TELEGRAM_CHAT_ID", heartbeat_min = 60, min_level = "info", dedup_s = 600, rate_per_min = 20`
- `[watchdog] runs_dir, grace_s = 120, status_min = 60`

**Tests:**
- rate limit, dedup and coalescing against a fake HTTP server;
- the sink never blocks;
- the token never appears in any record or log;
- the panic hook sends;
- the watchdog state machine on a fake runs directory;
- message formatting.

**Placement:** a lane, merged after WP-05 so the win and settlement hooks can be wired. Cherry gets only the binary (owner rule): the watchdog is a subcommand, not a script.

## Owner decision (2026-10-06): trade-success criteria for the Stage 0 exit, and the $500 trigger

- **Trade-success criteria** added to the Stage 0 exit (PLAN §6 has only safety and measurement gates). They are measured over the 24 h canary FT-005 from the chain ledger:
  - every landed trade nets > 0 after fee + tip + rent (0 exceptions);
  - 24 h net ≥ 0;
  - ≥ 10 wins, else extend;
  - realised vs quoted median within ±10%;
  - win ratio per bundle sent ≥ 0.3%, stretch 0.5%.
- **Profit is not a Stage 0 gate:** expected at this wallet size is about $0–7/day (STAGE1-PLAN).
- **The $500 trigger:** net positive over 48 h of canary.
- **Still open:** the exec-coverage gate (≥ 99%) needs more Haan capacity or a second provider (OD-1), or an explicit owner waiver.
- **Owner, 2026-10-06 (later):** the Stage 0 exit canary (FT-005) runs **12 h instead of 24 h**. PLAN §6's "24 h live" gate items and the trade-success criteria are measured over the 12 h run. The $500 trigger (net positive over 48 h of canary) is unchanged.

## WP-21: Venue coverage (owner request, 2026-10-06: "add DFlow, Jupiter for venue coverage")

**Why:** the rival dossiers (docs/research/rival-GLiCiNEn.md, and the En3NPq8o sample) show the gaps we miss sit on venues we don't trade.
- GLiCiNEn: 79% of its pools are outside our list, on 12 venues.
- En3NPq8o: routes through Jupiter v6 and DFlow into Raydium CLMM, Tessera V, Manifest and BisonFi.

**Constraint:** the deployed Nexus v2 (8K8uyQDt) CPIs only its 12-program ALLOWLIST (program/nexus-arb-v2/src/lib.rs:670), which does not include Jupiter v6 (JUP6Lkb…) or DFlow (DF1ow4ts…).
- An aggregator instruction placed outside our program is not covered by `check_profit`, so a landed trade could lose. That breaks invariant 2, so it is not allowed.

**Phase A (no deploy, no rent): native venues the deployed program already allows.**
- Venues, in order of priority: **Raydium CLMM** (CAMMCzo5…), **Orca Whirlpool** (whirLbMi…), then the CLMM forks **PancakeSwap v3** (HpNfyc2S…) and **Byreal** (REALQqNE…), then the launchpad curves **pump.fun** (6EF8rrec…), **Meteora DBC** (dbcij3LW…) and **Raydium LaunchLab** (LanMV9sA…).
- Per venue:
  - exact maths in arbx-sizing, validated against the real program binaries in program/venue-harness (exactness + adversarial, 0 mismatches, 0 false refusals, as WP-16);
  - decoders and registry boot;
  - state following tick arrays (like DLMM bin arrays) in the WP-04 consistency sets;
  - leg builders with account lists;
  - CU table entries;
  - pooldisco's candidates for those venues fed into the seed list.
- **Acceptance:**
  - the harness passes on real pools;
  - an FT shadow segment prices the new venues with 0 phantom/poisoned decisions;
  - the dry run (as FT-002) shows the bundles verify and simulate without account or CU errors.

**Status, phase A (lane/wp21, 2026-10-06): Raydium CLMM and Orca Whirlpool done; the forks and the curves not started.**
- **Maths** (3311b07): exact `swap_v2` ports in arbx-sizing (features `rayclmm`, `whirlpool`), 0 mismatches and 0 false refusals over about 94k harness cases on the deployed binaries (deploy slots 451,479,902 and 440,170,207).
- **Engine** (af5f2be, 11930d8 and the plumbing commit after them): decoders and registry boot; the parts and the tick arrays followed in the WP-04 consistency sets, the accounts that do not exist held empty; quotes at the target slot's Clock (raised to Orca's own stamps); the crate's refusal states as reasons with their counters; the `swap_v2` leg builders (Raydium: 13 accounts, the bitmap extension, the walk's tick arrays; Orca: 15 accounts with its 3 tick arrays and the oracle); the accuracy monitor on their post-states; the CU fallback by swap steps (64,000 / 48,000 + 10,000 a step) and the cu-table keyed by steps; replay (scenario S17). A per-venue switch, `[pools] rayclmm` / `whirlpool` = off | quote | send, defaults to off: the maintained configs are unchanged.
- **nexus-v2 needs no upgrade.** It CPIs any allowlisted program with the leg's own account list and data, patching the input amount at the leg's offset (8 for both venues' `swap_v2`); the deployed ELF's allowlist holds both program ids. Five engine-built routes (Whirlpool ↔ PumpSwap both ways, Raydium CLMM ↔ Whirlpool both ways, Raydium CLMM → AMM v4) land through the deployed ELF and the real programs in LiteSVM, each leg delivering exactly the engine's quote (program/venue-harness `tests/arbx_bundle_clmm.rs`).
- **Tests:** the engine's quotes equal the programs on 2,679 recorded swaps (1,343 exact out); the accuracy monitor's post-states are exact on all of them; no-panic property tests over mutated states, sizes, decoders and builders, and Orca's deployed U256 division; tools/ci-venue-parity.sh covers the new fixtures.
- **Shadow test:** `deploy/arbx-wp21-shadow.toml` (`quote` mode), `data/seed-pools-wp21-shadow.csv` (the 2026-10-06 list plus 242 pools verified on chain), plan in docs/field-tests/FT-009-wp21-clmm-shadow.md.
- **Not in this step:** PancakeSwap v3 and Byreal (one maths, layouts to check against their binaries), the launchpad curves, pooldisco candidates for these venues (the WP-22 refresh), and sending through them (`send`: an owner decision after FT-009).
- **Review (merge after fixes; /home/moiz/arbx-offload/wp21-review/REVIEW.md), fixed on the lane:** the `venue_quote_only` guard tested in live and canary runs (F4); in a run that sends, a quote-only venue's route is priced and recorded but never the pick, and the executor's check holds gated or not (F3); the existing configs' normalized hash unchanged (F8); registry rows of these venues never candidates (F1); each segment reads both programdata deploy slots at its start and end and switches a changed or unknown venue off (F5); the Raydium bitmap scanned by 64-bit words, the follow sets with hysteresis, the watch list encoded off the engine thread, a CLMM shape in the engine benchmark (F2: leg parse p99 36 µs to 1.3 µs, the drift's check 58 µs to 1.7 µs; per transaction p99 70 µs at aligned prices against 19-34 µs without CLMM); a tick array read missing priced as absent only once a second read confirms it (F6); a CLMM leg never asks less CU than its steps allow (F7); the routes' sizes against the default lookup tables measured (F11: all of the vectors fit with them, 2 of 5 do not without). Round 2 (merge after three small fixes), fixed: the provisional-absent rule applied where routes are priced too (R2-1: such a route is `unquotable_clmm_array` until the second read); WP-22's refresh no longer counts the registry's Raydium CLMM rows (R2-2); the watch list encoded on a blocking thread, each key once (R2-3: a re-follow 0.65 ms off the hot runtime, where a replacement cost a hot worker 8.8-10.6 ms); the deploy check's switch-off in meta.json `overrides` (R2-4); Raydium's follow set no longer moves when the price crosses uninitialized arrays.

**Phase B (needs an owner decision: a program upgrade): Jupiter v6 and DFlow as legs.**
- Add both to the allowlist, by upgrading Nexus v2 (the owner's upgrade authority) or through arbx-exec at the $500 stage. The profit guard then covers aggregator legs like any other.
- An off-chain quote path is required (Jupiter/DFlow quote API, or self-hosted routing). Quotes are journaled as inputs so the replay stays exact.
- Expected value: broad coverage of long-tail venues. The cost is quote latency (tens to hundreds of ms), so it suits slower long-tail gaps, not contested ones.
- **Gate:** Phase A measured first. Phase B's design and the latency budget go to the owner before any upgrade.
- **Owner, 2026-10-06 (later still):** FT-005 was shortened to 3 h. **Stage 0 closes after FT-007**, with the exit criteria measured over the canary series FT-005 + FT-006 (tips + BAM fix) + FT-007 (smaller sizes), about 9 h in total.

## WP-22: Automatic pool refresh (owner request, 2026-10-06: "start wp22, test it before closing stage 0")

**Why:** our pool list is refreshed by hand between tests, so tokens that turn active mid-test are missed.
- GMGN trending check: BINDER traded in 3 pools, including a DAMM v2 pool doing ~$1.3M volume/h. None were in our list (docs/research/gmgn-trending-2026-10-06.md).
- Venue census: on our own venues, rivals mostly trade pools we don't watch. The watched share is 17% on DAMM v2, 21% on PumpSwap, 36% on CPMM and 48% on AMM v4 (docs/research/venue-census.md).

**What:** `arbx pools refresh` builds the next pool list. The campaign runs it during each segment, so the next segment boots on a fresh list.
- **Sources:**
  1. **Our own records:**
     - activity of rival arbitrage on our venues, including pools we don't watch (rivals.jsonl / classify);
     - our own triggers, decisions and opportunities per pool.
  2. **GeckoTerminal** (free, no key): `trending_pools` (5m / 1h / 6h) and `new_pools`.
  3. **DexScreener** `token-pairs`: every pool of each candidate token.
  - GMGN is skipped: its API key needs a $100 balance.
- **Rules:**
  - Venues: only those we trade. Quote: WSOL or USDC.
  - A token needs ≥ 2 verified pools on our venues with the same quote, counting pools already listed.
  - **Every pool is verified on chain:**
    - the account exists;
    - its owner is the venue program;
    - it decodes with the engine's own decoder;
    - its mints match;
    - its liquidity is at least the minimum;
    - the existing Token-2022 and refusal rules apply.
  - Keep active pools, drop dead or idle ones, and cap the size (default: today's 1,500).
  - Priority: active listed pools first, then new pools from our records, then new pools from trending, then idle listed pools.
  - Output: a deterministic CSV plus a JSON report of added, dropped and kept pools, with reasons, sources and timings.
- **Fail-safe:** if verification fails, the previous list is kept with the reason recorded. A segment never boots on an unverified list.
- **Campaign:**
  - The pool list becomes a per-segment artifact in the campaign directory, hashed in campaign.json and the segment's meta.
  - It is the only data file allowed to change between segments. Every other file is still frozen and checked (review WP-07 #16).
  - The refresh never uses Haan gRPC (one process only).
  - Its RPC calls stay out of the running segment's Haan budget.
  - Each refresh posts one Telegram notice.
- **Replay:** a segment's input is its own pool list.
- **Acceptance:**
  - unit and fixture tests (recorded API responses, no network);
  - a pre-flight `arbx pools refresh` on Cherry against FT-006/FT-007 records, checked before FT-008;
  - FT-008.
- **Later, not in FT-008:**
  - hot-adding pools mid-segment;
  - the CLMM and Whirlpool venues once WP-21A merges;
  - new-pool events from our own shred feed.
- **Owner, 2026-10-06 (evening):** **Stage 0 closes after FT-008** (WP-22's test), no longer after FT-007. The exit criteria are measured over the canary series FT-005 + FT-006 + FT-007 + FT-008 (about 12 h).
- **Owner, 2026-10-06 (evening), Stage 0 exit:** wins must include more meme / long-tail tokens than common tokens (USDT, USDC, JUP, Meteora and the like), counted over FT-005..FT-008. The definition and the current standing are in FT-008-auto-pool-refresh.md, "Stage 0 exit".

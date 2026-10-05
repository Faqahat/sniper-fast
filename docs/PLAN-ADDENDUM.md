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
   - No new token accounts while trading. An owner-approved wallet-prep step creates the token accounts for the top-N mints, about 0.002 SOL each and recoverable.
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

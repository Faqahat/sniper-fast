# WP-00 review: Day-0 safety switch (uncommitted working tree on master)

**Date:** 2026-10-04. **Reviewer:** adversarial review of the uncommitted WP-00 diff (`git diff` on `deploy/arb.toml`, `docs/MEASUREMENT.md`, `src/config.rs`, `src/engine.rs`, `src/exec.rs`, `src/main.rs`, `src/send/budget.rs`, `src/send/mod.rs`, plus the new `deploy/arbx-stage0.toml` and `data/crowded-pools.json`). The review checks it against PLAN.md WP-00, MEASUREMENT.md §7/A.8 and the research it cites. No code was changed.

**Verdict:** no blockers. The safety switches are in place, and nothing new can send a live transaction. There are three **major** findings:
- the stage-0 config cannot do the required shadow run (F1);
- the "crowded pools last" rank has no effect at the configured 10 ms queue (F2);
- the maintained `deploy/arb.toml` lost its only pricing path (F3).

There are also eight minor findings and five nits.

---

## Verification performed

| Check | Result |
|---|---|
| `cargo build --release` (WP-00 tree) | Passes with 24 warnings. Built into a scratch `CARGO_TARGET_DIR` because `arbx/target` hit a btrfs disk-quota error at the time; nothing under `target/` was touched |
| Warnings against HEAD | HEAD (`git archive HEAD`, built separately) also gives 24. The sorted warning lists are **identical**, so there are no new warnings |
| `cargo test --release` | **74 passed**, 0 failed. HEAD: 61 passed. That is 13 new tests, and no test was removed |
| `arbx check --config deploy/arbx-stage0.toml` | `enabled send paths: jito-bundle`. The safety line shows decoded_sends false, skip_failing_signers true, state_triggers true, record true, 4.2 SOL, 0 new token accounts, sim_gate false, bundle_mix true (tpu_max_expected 1), big band ≥ 1,000,000 at 0.5/s, and the crowded file |
| `arbx check --config deploy/arb.toml` | Parses. Jito tip 70%, 10,000..100,000. The safety line shows **`decoded_sends false … state_triggers false`** (see F3) |
| `data/crowded-pools.json` | Recomputed independently from `tmp-patterns/scan-w5h-p*.json` with analyze.py's POOLBOTS rule (max over segments): exactly the same 21 pools, 9,515 market wins, 169,779,684,423 lamports. All 21 are in `data/seed-pools-w4.csv` |
| Every non-bundle path disabled | Yes. All 16 listed paths are `enabled = false`, and `Paths::new` builds only enabled paths (send/mod.rs:767). With `bundle_mix` and `tpu_max_expected_lamports = 1`, every trade with expected > 1 takes the bundle arm. Expected == 1 finds no copy and is skipped |
| Live arming | Still needs `mode = "live"` **and** `--live` (main.rs:494). The gate and the sim gate are off. Copies are fired only through jito-bundle. No new code path sends anything |

## Conformance with PLAN WP-00

| Plan item | Status |
|---|---|
| stage0 config: paths repointed to `/root/arbx`, seed list named in the repo | Done. The seed list is `seed-pools-w4.csv`, not the merged fallback; the file exists since c777f26. Acceptable, and the deviation is recorded |
| `[strategy]` skip_failing_signers = true, state_triggers = true, confirm_trigger_ms 60 | Done |
| `[live]` bundle_mix + tpu_max 1, sim_gate false, max_new_token_accounts 0, settle_s 3, max_size_sol 4.2 | Done |
| The 16 non-bundle `[[send]]` paths disabled | Done (and tested) |
| `[record] enabled = true`, `archive_feed = ""` | Done |
| Jito 0.7 / 100,000 in stage0 and arb.toml | Done (and tested) |
| DAMM v2 added to both deshred `account_include` lists | Done (and tested) |
| config.rs: 4 keys with the plan's defaults | Done, plus a rate ≥ 0 check |
| `on_trigger` hint-only after the signer, slippage and accuracy checks and the bookkeeping | Done; the order is correct (engine.rs:664-691) |
| State-path stage times and the 3 state series; `decided_to_signed` and `signed_to_fired` | Done. The "first update" meaning is not always kept (F4) |
| Attempt line written after `paths.fire` | Done. `fire` spawns at once (send/mod.rs:820-822), so the copies really leave before the line is formatted and flushed |
| Big band: 0.5/s, burst 1, `live_skip_big_band_throttle` | Done. Tokens can be wasted (F5) |
| Crowded list, rank 2, `crowded` on attempts, the drop counter split | Done as specified, but it has no effect (F2) |
| Offline acceptance: bucket test, Prio test, `check` lists only jito-bundle | Passes. The Prio queue test uses a 3.5 s queue, not the configured 10 ms (F2) |
| Field acceptance (owner) | Not run. The shipped config cannot run in shadow (F1) |

---

## Findings

### 1. MAJOR: `deploy/arbx-stage0.toml` cannot do the shadow runs WP-00's field acceptance requires
- **Location:** `deploy/arbx-stage0.toml:12` (`mode = "live"`); `src/main.rs:494`.
- **Problem:** `run` refuses to start when `--live` and `mode == "live"` disagree:
  ```rust
  if live != (cfg.mode == "live") { anyhow::bail!("live trading needs mode = \"live\" in the config AND --live ...") }
  ```
  With this config, `arbx run --config deploy/arbx-stage0.toml` (shadow) aborts. The only run it accepts is a live one.
  - WP-00's field acceptance needs two 10-minute **shadow** runs with this file: one with the recorder on, one with `[record] enabled = false`.
  - `--shadow` only arrives in WP-01 (PLAN.md:327).
  - So the owner must edit `mode` by hand, the `sed`-style config mutation that res-stops C9 / invariant 8 warn about, or run live before the shadow checks have passed.
- **Also:** in shadow, exec is off (`exec_on = sim || canary || live`, main.rs:500). The big-band bucket, the crowded rank, the drop split, `decided_to_signed`/`signed_to_fired` and `settle_s` are therefore never exercised before the first live run. None of WP-00's exec-side outputs can be field-checked before going live.
- **Proof:** code reading of main.rs:490-500. I did not run the binary, because `run` reads `deploy/.env` first.
- **Fix:**
  - Ship the file with `mode = "shadow"`. Day 0 should not be one flag away from trading before its shadow checks pass. The owner flips it to `live` (recorded in the merge note) after the field acceptance.
  - Or add a minimal `--shadow` override now: a three-line change that WP-01 subsumes.
  - Write the exact owner procedure for both shadow runs into the merge note, including how to disable the recorder without hand-editing the file. For example, ship a second file or document the one-key change.

### 2. MAJOR: "crowded pools ranked last" has no effect with a 10 ms queue; the WP goal (F6) is not met
- **Location:** `src/exec.rs:719-722` (`prio_rank`); `src/send/budget.rs:83-104` (`acquire`), :107-122 (`pump`); `deploy/arbx-stage0.toml:167-169` (`queue_ms = 10`); test `exec.rs:241-258`.
- **Problem:** `Budget::acquire` hands a free slot to whoever asks first: `if s.waiting.is_empty() && take(...) { return true; }`. The rank orders only requests that are already *waiting*.
  - With a rolling 1 s window of 5 and a wait of at most 10 ms, a crowded route still takes any free slot.
  - Ordering matters only if two or more bundles wait inside the same 10 ms when a slot frees, and that almost never happens.
  - The unit test `crowded_route_is_served_last_by_the_rate_queue` proves the ordering with a **3.5 s** queue, a regime the config never uses.
  - PLAN says crowded pools "therefore queue behind everything else in the 5/s budget". In practice they do not.
- **Proof:** replay of the legacy bundle stream through a model of `Budget` (same rolling-window and waiter rules), with and without the rank. Input: `testdata/legacy/raw/*/attempts+copies`, 12 segments, 5,740 jito-bundle attempts, 3,772 (66%) touching a crowded pool. The model reproduces the logged over-rate counts (p7 214 against 192 logged, p8 109/109, p9 199/203, p10 34/35).

  | Policy | Sent (crowded / other) | Over-rate drops (crowded / other) | Serves with ≥ 2 waiters | Serves reordered by rank |
  |---|---|---|---|---|
  | HEAD (queue 0) | 3,260 / 1,726 | 512 / 242 | 0 | 0 |
  | WP-00, queue 10 ms, big band, **no rank** | 2,790 / 1,537 | 218 / 123 | 1 | 0 |
  | WP-00, queue 10 ms, big band, **rank** | 2,790 / 1,537 | 218 / 123 | 1 | **0** |
  | queue 0 + big band (no queue, no rank) | 2,786 / 1,537 | 222 / 123 | 0 | 0 |

  - The rank changes **nothing**: crowded routes keep 64% of the bundles sent.
  - `queue_ms = 10` adds up to 10 ms of delay for 4 extra sends.
  - All the drop reduction comes from the big-band throttle.
  - A "headroom" variant (crowded may take a slot only while one or two slots stay free) moves just 15-24 sends to other routes. The 5/s budget is short in only about 13% of attempts, so no queue policy can redirect the bulk.
- **Fix:**
  - Tell the owner that OD-3's default does not deliver R §1's "stop spending 49% of attempts on the 21 pools".
  - Recommend OD-3's alternative: exclude crowded pools from bands ≥ 100k in `copies` (or entirely), with a `live_skip_crowded_pool` reason. Or give the crowded routes their own `TokenBucket` (e.g. 1/s), reusing the type this WP adds.
  - Make the Prio acceptance test use the configured `queue_ms`, or add a test showing the configured policy actually reduces the crowded share.
  - If the rank is kept, drop `queue_ms = 10` (it is a delay with no benefit) or justify it separately.

### 3. MAJOR: the maintained `deploy/arb.toml` lost its only pricing path
- **Location:** `deploy/arb.toml:48-53` (`[strategy]` sets neither `state_triggers` nor `decoded_sends`); `src/config.rs:404` (defaults `state_triggers: false`, `decoded_sends: false`).
- **Problem:** in arb.toml, decoded triggers were the only path that priced anything (`state_triggers` was never set). With the new default `decoded_sends = false`, a shadow run with arb.toml decodes hints, writes predictions and **never finds an opportunity**: `opportunity` and `state_opportunity` both stay 0, and `opportunities.jsonl` stays empty.
  - Nothing warns about it. `arbx check` prints `decoded_sends false … state_triggers false` without comment.
  - PLAN §7 says "Each WP updates deploy/arbx-stage0.toml and deploy/arb.toml". This WP changed only arb.toml's tip lines.
- **Proof:** `arbx check --config deploy/arb.toml` → `safety: decoded_sends false, skip_failing_signers true, state_triggers false, record false; …`. In engine.rs the decoded path returns at :687-690. `state_trigger` runs only when `cfg.state_triggers` (:935).
- **Fix:**
  - Add `state_triggers = true` to arb.toml's `[strategy]` (the Stage-0 pricing path), with a WP-00 comment.
  - Add a config test that every maintained config has at least one pricing path (`state_triggers || decoded_sends`).
  - Optionally, `Config::parse` or `arbx check` should warn when neither is on.

### 4. MINOR: a state trigger's `rx`/`engine` is often not the *first* update of the transaction, as documented
- **Location:** `src/engine.rs:376` (flush when `rx.is_empty()`); :223 (an incomplete pool returns without being kept); :936-939 (a new entry is pushed with this update's times).
- **Problem:**
  - The run loop flushes `state_pending` whenever the channel is momentarily empty. If that happens between two vault updates of one transaction, `state_trigger` finds the parts incomplete, returns, and the entry is gone. The same mechanism causes defect #2: "34% of state opportunities came from such transactions".
  - When the second part arrives, a **new** entry is created with the second update's `t_recv`/`t_engine`.
  - For two- or three-part pools (PumpSwap and AMM v4 vaults, CPMM), the recorded `rx` is then the *last* part's arrival. That contradicts MEASUREMENT v1.1 ("rx = the receive time of the pool's first account update stamped with the trigger transaction") and shortens `state_recv_to_*` by the spread between parts.
  - WP-02's gate is "p99 within 5 µs of the WP-00 baseline". The bias is the same on both sides, so the gate still compares like with like, but the baseline is not the documented quantity.
- **Fix:** keep the first-seen times outside `state_pending`, so a flush cannot lose them. For example, a small map `(sig8(txn), pool) → (t_recv, t_engine)` filled in `on_account` and removed when `state_seen` accepts the pair, or bounded like `state_seen`. Add a test: first part, flush, second part, flush. `st.rx` must equal the first part's time.

### 5. MINOR: a big-band token is spent before the attempt is known to go out
- **Location:** `src/exec.rs:566` (`try_take`); later failures at :644/:661 (`live_skip_no_copy_worth_sending`), :655 (build error, e.g. oversized at 1,209/1,232 bytes, defect #16), and send/mod.rs:526 (Jito budget over-rate).
- **Problem:** the single token per 2 s is consumed before the copies are built and before the 5/s budget admits the bundle. A big-band attempt that then fails to build, or is refused over-rate, wastes the next 2 s of big-band capacity, and `live_skip_big_band_throttle` then hides real gaps.
- **Fix:** check the token with a peek (`would_take(now)`) in `copies`, and consume it in `send` once `copies` returned `Ok`. Ideally, refund it when the fire result is "over its rate". At minimum, count `big_band_token_wasted`.

### 6. MINOR: `record_caps` still runs on the engine thread between consecutive decisions of one transaction
- **Location:** `src/engine.rs:248-250` (after `after_opportunity`); `flush_state` :265-266.
- **Problem:** moving `record_caps` after the send keeps it from delaying *that* send, which is good. But `flush_state` evaluates every pool the transaction moved in sequence. Pool A's caps ladder therefore runs before pool B is even priced. The ladder is about 7 doublings, up to 30 ternary steps and 7 caps, each two leg quotes, so about 150 quotes; DLMM legs walk bins.
  - With the recorder now on and `min_profit_lamports = 1`, this runs on every state opportunity (0.7-6.4/s in the legacy status, e.g. w5h-p9 6.43/s).
  - The recorder-off shadow run will include this cost, so it is measured, but it is avoidable.
- **Fix:** queue `(id, b, now)` and compute the caps after `flush_state` returns, or when the channel is idle (`housekeeping`). The line is unchanged.

### 7. MINOR: the latency percentiles sort up to 200k samples per series on the engine thread, and WP-00 adds three high-rate series
- **Location:** `src/engine.rs:177` (`pct` sorts in place), :426-429 (each series is sorted for p50/p90/p99 every 10 s; cleared only above 200,000).
- **Problem:** the state series take one sample per state evaluation, roughly 40-80/s at the measured 31-60 watched tx/s, so each reaches the 200k cap in about 40-80 minutes. A micro-benchmark of the same `pct` code on this machine: 3 series × 3 percentiles with 800 new samples per tick takes **0.4 ms at 20k, 2.3 ms at 100k and 4.2 ms at 200k** samples per status tick. That stall lands on the engine thread every 10 s, on top of the existing five decoded series.
  - The percentiles are also cumulative since start or the last clear, not per interval.
- **Fix:** keep a fixed-size reservoir (e.g. 8,192 per series), or `select_nth_unstable` on a copy, or move the computation to the status writer. WP-02's background runtime is the natural home; until then, cap the series at about 20k.

### 8. MINOR: tests are missing for the integration points
- **Location:** `src/exec.rs` `copies`/`send`; `Exec::new`; main.rs `limits`.
- **Problem:** the new tests cover the pieces (bucket, `prio_rank`, `parse_crowded_pools`, `Budget` ordering, the stats split, the engine hint and state paths). They do not cover the wiring the WP changed:
  - (a) `copies` returns `live_skip_big_band_throttle` for `Kind::Live` at `expected ≥ min` and not for canaries or below the threshold;
  - (b) `send` writes `crowded`, `queue_rank` and `st.fired`, with `fired ≥ signed`, and the line is written after `fire`;
  - (c) `Exec::new` fails when a configured crowded file is missing (only the helper is tested);
  - (d) `meta.json` `limits`.
- **Fix:** split the pure part of `copies` (the live gates) into a function, or build `Exec` with a stub RPC and test (a)-(c). Test (d) through a small `limits_json(&cfg)` helper.

### 9. MINOR: decoded hints keep pushing the v1 decoded series, whose meaning changed
- **Location:** `src/engine.rs:636-641` (`write_trigger`); MEASUREMENT.md:1179 ("changes no existing field's meaning, except the state-trigger stage times").
- **Problem:** for a hint, `resolved_to_decided` and `rx_to_decided` no longer include `best_cycle`; `decided` is just the time of the bookkeeping. The same series names now mean something smaller than in arb-lab's v1 files, so a WP-10 comparison of `rx_to_decided` between legacy and WP-00 segments would show a false speed-up. The plan asked only for the hint's `rx_to_decided` sample.
- **Fix:** state it in MEASUREMENT §7 v1.1 (for hints, `decided` is the end of the hint bookkeeping, not a pricing decision). Better, push hint samples to a separate `hint_rx_to_done` series and leave the v1 names to `decoded_sends = true` runs.

### 10. MINOR: `skip_failing_signers` changes nothing in trading under hint-only, and skipped signers' statistics freeze
- **Location:** `src/engine.rs:664-665` (skip) before :682 (`trig_pending.insert`).
- **Problem:**
  - With `decoded_sends = false`, the skip only suppresses bookkeeping: no hint is ever priced, and the state path ignores signers. The "skip_failing_signers working" goal is therefore cosmetic in Stage 0.
  - A signer that crosses the < 25% rule is skipped before `trig_pending.insert`, so its later landings never update `signer_stats`. The comment "signer statistics keep learning" (engine.rs:684, MEASUREMENT) holds only for signers that are not skipped.
  - This ordering exists at HEAD too, but WP-00's comment claims otherwise.
- **Fix:** in hint-only mode, record the hint's `trig_pending` entry even for a skipped signer (count the skip, keep learning), or reword the comment and the plan's field check.

### 11. MINOR: `signed_to_fired` measures a task spawn, not the send
- **Location:** `src/exec.rs:731-732`, :764.
- **Problem:** `t_fired` is taken right after `paths.fire` *spawns* the fire task, so `signed_to_fired` is the cost of `tokio::spawn`, typically below 1 µs. The bytes leave later (`copies.jsonl` `t_sent`). As a baseline for "signed → sent" (F13's chain) it carries almost no information.
- **Fix:** document it as "handed to the runtime". The more useful baseline is `signed → t_sent` of the first copy, which `on_settled` can compute from `Fired.copies[0].t_sent` and push into a `signed_to_sent` series.

---

## Nits

- **N1. Config validation.**
  - `big_band_max_per_sec` in (0, 0.0005) rounds to "never" silently (budget.rs `TokenBucket::new`).
  - `big_band_min_expected_lamports = 0` throttles every live trade to 0.5/s.
  - `{"pools": []}` is accepted and disables ranking.
  - Suggestions: reject a positive rate under 0.001; log or require `min > 0`; have `Exec::new` print how many crowded pools are actually in the registry (here 21 of 21 are in the w4 seed list), so a list from another registry is noticed.
- **N2. Seed rank for "both" pools.** `prio_rank` keeps arb-lab's `source == "mriya"` test, so seed pools also in the registry (`source "both"`) get rank 1. That is 165 of the 1,395 w4 seed pools. MEASUREMENT v1.1 documents rank 0 as "seed pool". Either accept `"both"` as a seed or document the exception.
- **N3. `arbx check` does not open `crowded_pools_file`.** The only check is the load in `Exec::new` at start. Loading it in `check` when the path exists locally would catch a bad list before deploy.
- **N4. `queue_ms = 10` is a behaviour change WP-00 did not ask for.** It is documented as a deviation, and per F2 it buys nothing. If F2's fix drops the rank, remove it.
- **N5. Doc-comment placement.** In exec.rs, `/// what a nexus-v2 or venue error code means, in words` sits above `#[cfg(test)] mod tests` (it predates WP-00). The new tests make the stray comment more visible; move it to `meaning`.

## Checked and found correct (no finding)
- **Hint path order.** Signer skip, `trigger_skip_will_fail`, `checks.insert`, `trig_pending.insert`, then the return. `preds` stays empty, so `state_trigger`'s two decoded skips (:226, :228) cannot fire. `confirm_wait` stays empty.
- **`state_pending` dedupe by pool.** Behaviour is the same as HEAD's duplicate entries, which `state_seen` dropped. All entries share one txn, because a different txn flushes first.
- **Moving `record_caps` after the send.** It reads only store and slot state, which the send does not change, so the line is identical.
- **`send` reorder.** The `s.watch` sigs are registered before `fire`. `s.open` is inserted after, which is safe because `Settled` is processed on the engine thread after `send` returns. The sim-gate path still fires from the task, with `fired: null`.
- **TokenBucket.** Integer refill is exact: 500 units/ns at 0.5/s gives one token every 2 s. Burst is capped, a backwards clock is safe, and u128 cannot overflow.
- **Fail-closed crowded load.** It runs in `Exec::new` before any send, and an error aborts the run.
- **Defaults.** `decoded_sends` false, big band 1M / 0.5, no crowded file. All match PLAN; the TOML integer `0` parses as f64.
- **Other changes.** `meta.json` `limits` is present. The `run.log` `over-rate N (crowded M)` format and `exec.over_rate` in `status.jsonl` are documented in MEASUREMENT §7 v1.1.

## Not verified (owner / field)
- Both 10-minute shadow runs, `trigger_hint_only > 0`, `state_opportunity > 0`, the three state series' p50/p90/p99 baseline, and the expected-files list. All are blocked by F1 as shipped.
- Whether Haan and Astralane accept a fifth deshred `account_include` (DAMM v2); watch `run.log` for feed errors.
- Copying `/root/arb-lab/runs/signer-stats.json` to `/root/arbx/runs/`. Without it, `skip_failing_signers` starts with no history; see also F10.

---

## Disposition (2026-10-04, WP-00 completion)

All three major findings, all eight minor findings and four of the five nits are fixed; N4 is resolved by the F2 fix. Every fix has a test. `cargo build --release` passes with the same 24 warnings as HEAD (the same kinds, none from the new code). `cargo test --release` passes **86** tests: 61 at HEAD, 74 in the reviewed tree, 12 new.

| # | Finding | Disposition | Test(s) |
|---|---|---|---|
| F1 | stage0 cannot do the shadow runs | **Fixed.** `deploy/arbx-stage0.toml` ships with `mode = "shadow"`; its header gives the owner procedure (run 1 as is, run 2 with `--no-record`, then set `mode = "live"` and note it in the merge note). Two small run flags were added: `--shadow` forces shadow whatever the mode, and refuses `--live`; WP-01 keeps it. `--no-record` turns the recorder off for this run only. Both are recorded in `meta.json` `overrides`. The exec side cannot run in shadow, so it is covered offline by the F8 wiring tests. The header lists what the first live run shows | `config::stage0_config_is_the_day0_safety_switch` (mode shadow), `tests::shadow_and_no_record_overrides` |
| F2 | crowded rank has no effect | **Fixed with OD-3's alternative, on top of the default.** New `[live] crowded_skip_min_expected_lamports`, default 0 = rank only (OD-3 default). Stage0 sets 100,000: a live route touching a crowded pool and expecting ≥ 100k is skipped (`live_skip_crowded_pool`), before the big-band check, so it uses no big-band token. The rank, the `crowded`/`queue_rank` fields and the drop split stay. `queue_ms = 10` is removed (N4), so stage0 refuses over-rate at once, as arb-lab did; WP-05 brings the queue back. The Budget-ordering test is kept as a test of the queue mechanism, now documented as not the Stage-0 regime. **Evidence for the choice** (replay of the 4,797 legacy attempts with a jito-bundle copy in `testdata/legacy/raw`, one bundle per attempt, rolling 5/s, queue 0): (1) jito-bundle landings by band: crowded < 100k 12 of 1,214 (all 12 wins), crowded 100k-1M 0 of 866, crowded ≥ 1M 0 of 1,030; other routes 6/437, 2/614, 0/621. (2) Crowded share of bundles sent: big band only 63.7% (other routes: 1,398 sent, 62 over-rate); with the skip ≥ 100k **44.9%** (1,466 sent, 52 over-rate), and every crowded trade under 100k still goes. A separate crowded token bucket was rejected: at 1/s it gives 50.2%, but it cuts the crowded < 100k trades that produced 12 of the 20 bundle wins | `exec::band_gate_skips_crowded_from_100k_and_throttles_the_big_band`, `exec::band_gate_cuts_the_crowded_share` (legacy band mix: 0.57 → 0.42, every crowded < 100k kept), `exec::send_writes_the_queue_fields_and_applies_the_band_rules` |
| F3 | arb.toml has no pricing path | **Fixed.** arb.toml `[strategy] state_triggers = true`. `Config::pricing_warning()` is printed by `arbx check` and `arbx run` when neither pricing path is on | `config::maintained_configs_have_a_pricing_path` (both maintained configs; the bare defaults warn) |
| F4 | `rx` not the first update after a flush | **Fixed.** `Engine::state_first`: (sig8(txn), pool) → the first update's (t_recv, t_engine), filled in `on_account`, taken by `state_trigger` once the pool is complete, FIFO-bounded at 4,096 | `engine::state_trigger_keeps_the_first_update_time_across_a_flush` (first part, flush, second part, flush: `rx` = first part) |
| F5 | big-band token spent before the attempt goes | **Fixed (build/no-copy failures).** `TokenBucket::peek`. `BandGate::check` (in `copies`) only peeks, and `BandGate::commit` (in `send`, after `copies` returned Ok) takes the token. **Residual:** a built attempt later refused over-rate by the 5/s budget still uses its token, because the refusal comes back asynchronously; WP-05 owns the send queue | `budget::token_bucket_peek_takes_nothing`, `exec::send_writes_the_queue_fields_and_applies_the_band_rules` (a big attempt that fails to build leaves the token for the next) |
| F6 | caps ladder between two pools' decisions | **Fixed.** `state_trigger` queues `(id, best, now)` in `caps_pending`, and `flush_state` writes the caps lines after every pool of the transaction is priced. Same store state, same line. The ladder still runs on the engine thread until WP-02 | `engine::caps_line_waits_for_the_end_of_the_flush` |
| F7 | percentile sorts stall the engine | **Fixed.** New `src/lat.rs` `Series`: a uniform 8,192-sample reservoir (algorithm R), `n` counts every sample, and one sort per series per tick. Measured with the same kind of micro-benchmark: 13 series × 8,192 samples with 800 new samples each per tick take 0.55 ms mean, 0.68 ms worst. Before: 4.2 ms for 3 series at 200k. Semantics are documented in MEASUREMENT §7 v1.1: `n` no longer resets at 200k, and percentiles are over the reservoir of the whole run | `lat::reservoir_is_bounded_and_unbiased`, `lat::small_series_are_exact` |
| F8 | wiring tests missing | **Fixed.** (a) and (b): `Exec::new` is split into its RPC part and a network-free `Exec::assemble`, so a test drives `Exec::send` on a made-up live wallet (the send path is a closed local port). The test checks `crowded`, `queue_rank`, `st.fired ≥ st.signed ≥ st.built`, the counters, the big-band throttle on the second big trade inside 2 s, and the crowded skip. Canaries are covered by `BandGate::check(Kind::Canary, …)`. (c): the crowded list now loads first in `Exec::new`, before any RPC call, and the test shows a missing file stops it. (d): `limits_json` helper | `exec::send_writes_the_queue_fields_and_applies_the_band_rules`, `exec::exec_new_fails_closed_on_a_missing_crowded_file`, `tests::meta_limits_carry_the_stage0_limits` |
| F9 | hints change the v1 series' meaning | **Fixed.** Hints push only the new `hint_rx_to_done`. The five v1 decoded series take samples only from priced decoded triggers (`decoded_sends = true`). MEASUREMENT §7 v1.1 and A.8 updated | `engine::decoded_swap_is_a_hint_only` (hint series 1, v1 series 0) |
| F10 | signer skip is cosmetic, and skipped signers freeze | **Fixed.** A skipped signer's swap is still entered in `trig_pending`, so its landings count and it is let back in above 25%. This applies in both modes, which changes the `decoded_sends = true` path too: arb-lab froze those signers. The comments now say what the skip does in Stage 0 (it drops the hint's accuracy check; hints are never priced) | `engine::failing_signer_is_skipped_before_the_hint_and_keeps_learning` |
| F11 | `signed_to_fired` times a spawn | **Fixed.** Documented as "handed to the runtime" in exec.rs and MEASUREMENT. A new `signed_to_sent` series is pushed in `on_settled`: the first copy's `t_sent` minus `t_signed`, only for copies actually sent | covered by the send test's series counts; `signed_to_sent` needs a settled attempt, so it is field-checked on the first live run |
| N1 | config validation | **Fixed.** Rejected now: a positive `big_band_max_per_sec` under 0.001, `big_band_min_expected_lamports = 0`, and an empty crowded list. `arbx run` logs how many crowded pools the registry has (`crowded pools in this registry: N of 21`) | `config::wp00_keys_default_safe`, `exec::crowded_pools_file_loads` |
| N2 | "both" pools rank 1 | **Fixed.** `prio_rank` treats `both` as a seed pool (rank 0). MEASUREMENT updated | `exec::crowded_pool_ranks_behind_both_other_ranks` |
| N3 | `check` does not open the crowded file | **Fixed.** `arbx check` loads the configured path, or the repo's `data/<name>`, and prints the count; a bad list fails `check` | manual: `arbx check --config deploy/arbx-stage0.toml` → `crowded list data/crowded-pools.json: 21 pools` |
| N4 | `queue_ms = 10` | **Resolved by F2:** removed from stage0 | `config::stage0_config_is_the_day0_safety_switch` (`queue_ms == 0`) |
| N5 | stray doc comment | **Fixed.** Moved onto `meaning` | — |

**Deviations from PLAN WP-00, recorded for the owner:**
- **OD-3.** The plan's default ("rank last") is kept, but on its own it does nothing (F2). Stage0 also switches on the alternative (skip from 100k expected). To return to rank only, set `crowded_skip_min_expected_lamports = 0`. **Owner confirmation needed.**
- **Stage0 ships in shadow.** The owner sets `mode = "live"` after the field acceptance.
- **New flags.** `--shadow` and `--no-record` were added ahead of WP-01.
- **New file.** `src/lat.rs` is not in the plan's WP-00 file list.

**Open for later WPs:**
- **WP-01.** Keep `--shadow`'s semantics: refuse it with `--live`, and record it in meta `overrides`. Fold `--no-record` into the provenance and overrides scheme.
- **WP-02.**
  - Move the caps ladder (F6), the percentile summaries (F7) and the recorder off the engine thread.
  - The latency gate compares against the state-path series; they are now reservoir-based.
- **WP-04.** Remove the decoded path: `decoded_sends`, `hint_rx_to_done`, the signer skip on hints and `confirm_trigger_ms`.
- **WP-05.**
  - Replace `BandGate` and the static crowded list with the crowding map and per-band policy, and bring `queue_ms` back with a test at the configured queue.
  - Refund or count a big-band token whose bundle was refused over-rate (F5 residual).
- **Field (owner).**
  - The two shadow runs. Then, on the first live run, check `live_skip_big_band_throttle`, `live_skip_crowded_pool`, `exec.over_rate`, `decided_to_signed`, `signed_to_fired` and `signed_to_sent`, and `settle_s = 3`.
  - Check that Haan and Astralane accept the fifth deshred `account_include`.
  - Copy `signer-stats.json` into `/root/arbx/runs/`.

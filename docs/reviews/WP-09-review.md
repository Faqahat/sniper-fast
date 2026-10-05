# WP-09 review (part 1): replay harness and scenario tests

**Date:** 2026-10-05. **Reviewer:** adversarial review, read-only. No lane code was changed. Probes and mutants ran in a scratch copy of the crate (`scratchpad/r3/wp09-review/mut`), renamed `arbx-mut` so that its build artifacts could not overwrite the lane's.
**Plan:**
- `docs/PLAN.md` WP-09, items 1-4 and the offline acceptance;
- `docs/PLAN-ADDENDUM.md`, go-live gate (item 3: "a 1 h recording that replays identically") and I-11;
- `docs/MEASUREMENT.md` §4.13, §4.29 and §4.50.

## 1. What was reviewed

- **The implementation** is the uncommitted diff on `lane/wp-09` (base master 323e3bf):
  - modified: `docs/MEASUREMENT.md`, `src/lib.rs`, `src/main.rs`, `tools/capture-fixtures.py`;
  - new: 28 files (`src/replay.rs`, `src/scenarios/*`, `testdata/scenarios/*`, `tests/replay_cli.rs`).
- **Snapshot.** Taken at the start (00:07 UTC) and again before writing this review; both were identical:
  - `git diff | sha256sum`: `674dd5c0739c70178e2a99ff123846ee5e5e6377a7768d5d5db42a5a0d3b715f`;
  - the diff followed by the 28 untracked files (sorted, concatenated): `c6af45932fd33892529ec57837e260c27dba2958c34fcb03c53bd8308099bac9`.
- **Builds and tests I ran.** Every build used `CARGO_TARGET_DIR=…/scratchpad/targets/lanes` and `CARGO_BUILD_JOBS=5`.
  - **Build.** `cargo test --release --no-run` in the lane worktree took 1 min 37 s. It gave 2 warnings, both pre-existing (`main.rs:501`, `:509`, irrefutable `if let`); WP-09 adds none.
  - **Tests.** `cargo test --release` in the lane gave **347 passed, 0 failed, 2 ignored**: lib 321 (+1 ignored), bin 11, legacy_fixtures 4, meta_config_hash 1, **replay_cli 1**, runtime_isolation 2 (+1 ignored), stop_path 6, supervisor 1. This matches the claim.
    - `target/release/arbx` had the same sha256 (`d9c3caa1…`) before and after the run. I used a copy of that binary for every CLI probe.
  - **WP-09's own tests:** 4 `replay::tests`, 21 `scenarios::*` and `tests/replay_cli.rs`. All pass.
  - **Fixtures.** `python3 tools/capture-fixtures.py --verify` reports "232 files listed, 0 problems" and exits 0. None of the 232 files is a scenario fixture (finding 11).
  - **Config check.** `arbx check --config deploy/arbx-stage0.toml` and `arbx check --config deploy/arb.toml` both exit 0. `check` loads no `.env`.
  - **Mutation testing.** 18 mutants, switched by an environment variable in one scratch build, run against the 21 scenario tests (§5).
  - **Experiments in the scratch copy** (§5):
    - E1: a run driven by the real `Engine::run` loop, with a 100 ms SendGate sampler wired as `arbx run` wires it;
    - E2: recorder rotation every 50 KB;
    - E3: what `ok` says about an incomplete recording.
  - **CLI probes with the lane's binary:**
    - memory and speed on a kept 10-minute synthetic run;
    - `quote --batch` scaling;
    - exit codes;
    - concurrent runs with the default `--out`.
  - **Fixture provenance.** One read-only `getMultipleAccounts` call to the public mainnet endpoint (slot 453,422,981).
- **WP-05 context.** I read the uncommitted WP-05 work in the master working tree (`/home/moiz/arbed/arbx`) for the integration section (§6), and did not modify it.

## 2. Verdict

The replay driver and the scenario suite are **sound and well built**. Evidence:
- Every targeted engine regression I injected makes its scenario fail. The one exception is a stricter lag boundary (§5).
- A run driven by the real `Engine::run` loop replays identically, except for the gate. The same holds for a recording rotated into 177 decision files.
- Streaming per rotation file works.
- Fixtures are real mainnet data and self-contained (I-11).

**Do not merge as is.** The four findings below need fixing first: one breaks the analysis toolkit, and three would let `arbx replay` print OK or hide differences in the go-live replay.
1. **Blocker (merge): `pools.json` is now an object, and arbx-report reads it as a list.** The toolkit's blockctx (attribution, route accounts) silently sees zero pools on every new recording.
2. **Major:** `ok` (exit 0, "OK") does not require that the recording replayed whole. A journal gap, an accounts.bin record missing, or a store verdict mismatch all still give OK (E3).
3. **Major:** the declared `gate_sampled` exemption watches the wrong side of the gate sample, so it never fires. In E1, all 65 sampling differences fall 0.6-98.4 ms *before* a journaled sample, and `gate_sampled` = 0. The no-executor gate read is not journaled at the decision.
4. **Major:** `verdict_from_recording` drops the replay's own reason whenever the run had an executor. A replay that says `warmup` where the run sent is reported identical. In-flight outcomes are always taken from the recording, although S9 needs them compared. After WP-05 every run has an executor.

**Go-live gate item 3 cannot be met by WP-09 + WP-05 as they stand.** WP-05 gives every shadow run an executor and writes `sent` / `would_send` / `reason_ungated` into decisions, and this replay has no executor. A WP-05 shadow recording therefore compares as different on every would-send. §6 lists what the merge must add.

## 3. Acceptance checklist (PLAN WP-09 part 1)

| Item | Status | Notes |
|---|---|---|
| 1 `arbx replay --run [--from-slot] [--to-slot] [--config] [--out] [--compare]`: store rebuilt from the boot records, journal in order into `new_offline` through `step` / `timers` on the replay clock | **Met** | Plus `--pools`, `--set`, `--reprice-sizes`. Per-record driving is equivalent to `journal::replay` over the whole slice (E1, E2) |
| 1 Exec-side checks with `exec::send_checks` (WP-05) | Not done (declared) | §6 |
| 1 `--compare`: engine-side fields, state / pricing / policy reasons, input-side reasons whose inputs are journaled (gate, blockhash, leader) | **Partly met** | Gate: approximated from 100 ms samples, with a wrong exemption (finding 3). Blockhash and leader wait for WP-05. Executor runs drop the reason entirely (finding 4) |
| 1 Taken from the recording: `rate_queue_timeout`, `crowded_pool`, λ | Met, but broader | Also `band_throttle`, `inflight_*`, and every reason of an executor run (finding 4) |
| 1 Differences to `replay-diff.json`; journal gaps reported, interval skipped; pre-WP-03 runs refused | **Met** | A gap still leaves `ok` true (finding 2) |
| 2 What-if `--reprice-sizes`, `--set` | **Met** | Unknown keys are refused. Output only in `--out`, but a refused `--set` leaves a half-made out dir (finding 9) |
| 3 `arbx quote --run --route --version --size` (+ `--batch`) | **Met** | Quadratic in batch size (finding 8). Pricing differs from the decision's in three places (finding 10) |
| 4 Scenarios S1-S8 with S1b, S1b′, S4b, S8b on real layouts captured by `capture-fixtures.py` | **Met** | 12 scenarios plus fixtures and harness tests. All 7 pools exist on mainnet with the same owners and lengths, and 95-100 % equal bytes 36,851 slots later |
| 5 Real-data regression slice in `testdata/replay/` | Later | Needs Stage-0 recordings |
| Offline: all scenarios in `cargo test`; a synthetic 10-minute journal replays identically at ≥ 20× | **Met** | 575-650× in the test, 628× through the CLI; 15,125 decisions, identical. The synthetic mix is light (§7) |
| Field: 1 h Stage-0 shadow recording, 100 % of the compared fields, ≥ 20× | Owner-run | Only recordings made with WP-09 or later can be replayed: earlier ones have no `pools.json` (finding 12). With WP-05 it needs §6 |
| I-11: no test reads outside the repo | **Met** | Tests read `testdata/scenarios/*` and `deploy/arbx-stage0.toml`, and write to `$TMPDIR` |

## 4. Findings

### 1. Blocker (merge): `pools.json` is an object; arbx-report reads a list and silently sees no pools

- **Where:**
  - `src/replay.rs:75-97` (`pools_json`, `write_pools_json`);
  - `src/main.rs:1253` (the wiring);
  - `docs/MEASUREMENT.md` §4.29, which keeps the list form and adds "As WP-09 writes it";
  - consumer `tools/arbx-report/arbx_report/blockctx.py:24` and `:240`, via `model.py:78`;
  - toolkit fixture `tools/arbx-report/tests/gen.py:575`, which writes the list form.
- **Problem.** §4.29 specifies `pools.json` as `[{idx, venue, pool, …}]`, and the toolkit implemented that. WP-09 is the first producer of the file and writes `{schema, written_ns, producer, n_pools, n_pairs, pools, pairs, watch}` instead.
  - `read_json` accepts it: the schema major is 1.
  - blockctx iterates the dict's keys, finds no dicts, and silently returns empty maps.
  - `route_accounts` (the fallback for attempts without `route_in.accounts`) loses the vaults and extras.
  - `pool_writers` loses every writer, because its accounts.bin `pool_index` → pool map is empty. That map is the attribution under F10's blockctx report, and probably under the go-live item 3 check that compares the would-send set with chain truth.
  - The toolkit's own tests write the list form, so they keep passing.
- **Proof.** On a WP-09 recording (the kept synthetic run), with arbx-report's own reader:

  ```
  type dict keys ['n_pairs', 'n_pools', 'pairs', 'pools', 'producer', 'schema']
  blockctx pools map: 0 registry map: 0 (pools.json holds 5 pools)
  ```

- **Fix (either):**
  - Keep `pools.json` a list as in §4.29, and write the replay's extras (`pairs`, `watch`) to a second file, for example `registry.json`.
  - Or, in the same merge, teach arbx-report to accept the object form (`obj["pools"]` when it is a dict) and update `gen.py` and the goldens.
- **Also:** have meta.json `pools.file` point at it, with its sha256. It is still `null`.

### 2. Major: `ok` and exit 0 do not mean that the recording replayed whole

- **Where:** `src/replay.rs:527` (`ok = diff.ok && dropped == 0`) and `:770` (`ok = acc.n == 0 && flags_n == 0 && c_differ == 0`).
- **Problem.** Three things are computed, reported, and then ignored by `ok`:
  - journal gaps (`journal.gaps`);
  - account inputs skipped for want of their accounts.bin record (`accounts.missing`);
  - ACCOUNT records whose journaled verdict differs from the replayed store's (`accounts.verdict_mismatches`).

  A verdict mismatch is direct evidence that the replayed store diverged from the run's. Decisions inside a gap are skipped, and the rest are compared only if they differ. So a lossy recording, or one whose store diverged without changing a decision in the window, prints "OK" and exits 0. That is the go-live replay criterion.
- **Proof (E3, scratch):** a small three-pool run, edited three ways, each replayed with `--compare`:

  ```
  E3a journal GAP (a lost Clock record):          ok true  gaps [{first_lost_seq 74, n_lost 1, …}]  compared 60, identical 60
  E3b accounts.bin missing a Clock record:        ok true  missing 1                                compared 60, identical 60
  E3c a verdict mismatch:                         ok true  verdict_mismatches 1                     compared 60, identical 60
  ```

- **Fix.**
  - Set `ok = false` when there is any journal gap, an accounts gap or missing record, a verdict mismatch, or recorder drops.
  - Alternatively, add a separate `whole: bool` and make the CLI exit non-zero unless both are true; list the reasons in replay.json.
  - The go-live checklist should quote `replay.json ok` only once this is fixed.

### 3. Major: `gate_sampled` excuses the wrong window; the no-executor gate read is not journaled

- **Where:**
  - `src/replay.rs:54-55` (`GATE_SAMPLE_NS`), `:423` (the replay's gate follows INPUT 3 "watch"), `:685` (`near_gate`: `t >= g && t < g + 150 ms`), `:739-743`;
  - `src/engine.rs:1968-1973`: the no-executor branch reads the live SendGate and journals nothing;
  - `src/main.rs` run(): the 100 ms sampler.
- **Problem.**
  - In a run without an executor, every opportunity's reason (`no_executor` / `gate_<mode>:<reason>`) comes from the **live** gate at the decision. The replay rebuilds the gate from meta.json and from the sampler's INPUT 3 "watch" records.
  - The sampler sees a change at c only on its next tick (≤ 100 ms), and the engine journals the sample when it dequeues it (time g). So run and replay disagree on decisions in **[c, g), before the journaled sample**. After g they agree.
  - `near_gate` excuses [g, g + 150 ms) instead. It never excuses the real artifact, and it would excuse a genuine flip right after a sample.
  - The declared deviation ("gate flips within 150 ms are counted as `gate_sampled`") therefore does not hold.
  - It also contradicts §4.13, which defines the watch records as "status and coverage, not a decision input".
  - **Today's exposure is small.** A run without an executor is sticky shadow (`mode_shadow` / `forced_shadow`), so its gate changes only at the stop, and the sampler exits without journaling that change. Live or canary runs have an executor, and there the exemption is off (`!executor`).
  - No test exercises the gate path: no scenario writes meta.json or a watch record, and mutant R1 (the replay ignores the run's gate) survives (§5).
- **Proof (E1, scratch).** Setup:
  - The real `Engine::run`, on the real clock with real timers, fed by a thread at about 3 ms per trade.
  - A live SendGate shared with a 100 ms sampler thread copied from `main.rs`.
  - The gate paused 300 ms in and resumed 300 ms later by another thread, as the control socket does.
  - Then `replay::replay(.., compare)`.

  ```
  run: 786 decisions, 255 opportunities (157 no_executor, 98 gate_shadow:paused)
  replay: ok false; compared 786, identical 721, differ 65 (all `reason`, class policy); gate_sampled 0
  65 differences: 32 run gate_shadow:paused / replay no_executor (after the pause, before the "shadow" sample),
                  33 run no_executor / replay gate_shadow:paused (after the resume, before the "live" sample)
  every difference is 0.6-98.4 ms before the next journaled sample; none is within 150 ms after one (201.8-397.3 ms after)
  ```

  Everything else in E1 was identical: the other 721 decisions and all 786 commit lines. That is good evidence that a real run loop, its after-input and idle timers and its multi-threaded inputs replay faithfully through the per-record driver.
- **Fix.**
  - Journal the gate the decision saw in the no-executor branch too: the same INPUT 3 `src` "decision" record the executor branch writes, keyed by `opp`, including the reason.
  - Have the replay apply it at that opportunity, with a lookahead over the records that follow the input (§6, item 3). Then drop `gate_sampled`.
  - If the approximation stays for now, the window must be (g_next − sampler period − queue latency, g_next], not [g, g + 150 ms). Add a test with a non-sticky gate change (E1 is one).

### 4. Major: `verdict_from_recording` drops the replay's state-stage reasons for executor runs, and always takes in-flight outcomes from the recording

- **Where:** `src/replay.rs:571-584` (`reason_stage`: `inflight_same_state`, `inflight_same_leader`, `band_throttle` → `send_slot`), `:588-592`, `:717-720`.
- **Problem.**
  1. The rule tests only the **run's** reason. If the run had an executor and its reason is past the state and pricing stages (`sent`, `not_sent`, `fee_cap`, `gate_*`, …), `verdict` and `reason` are removed from **both** lines. But an executor run reaches the executor only when `shut == Ready`. A replay whose health diverged (`warmup`, `resync`, `state_unavailable`: engine-side, journaled, meant to be compared) is reported identical where the run sent or would have sent. That is exactly the I-4 class.
  2. `inflight_*` (the in-flight lock, released by journaled INPUT 5) and `band_throttle` are deterministic engine-time logic in WP-05 (`Inflight::check`, `big.peek(t)`), and S9 is defined as a replay of them. Mapping them to `send_slot` takes them from the recording forever. The PLAN names only `rate_queue_timeout`, `crowded_pool` and λ.
  3. After WP-05 every run has an executor, so (1) applies to every recording.
- **Fix.**
  - Exempt only when the run's reason is executor-side **and** the replay's reason is the offline engine's stand-in (`no_executor` / `gate_*`). Any state- or pricing-stage reason on either side is compared.
  - Move `inflight_*` and `band_throttle` out of `send_slot` once §6 lands.
  - Until then, report `executor_verdicts_not_replayed: n` and make `ok` false for executor recordings, rather than silently passing them.

### 5. Minor: the scenarios do not exercise several real-recording paths

- **Mutants that survive every scenario (§5):**
  - **R1:** the replay ignores meta.json `send_gate` and the watch records. The gate path is untested.
  - **R2:** every TIMER is replayed with `TIMER_ALL` instead of its journaled scope. The scenarios drive timers mostly as `TIMER_ALL`; WP-04's own test covers scopes, WP-09's suite does not.
  - **R3:** every TX_COPY record is dropped. No scenario journal contains a later unexecuted copy. Real runs have many (5 feeds), and they set `first_unexec_t`, which feeds the compared `trigger.t_first_shred` and the commit lines.
  - **M4d:** a stricter lag rule (lag 2 already shuts) survives. S7 tests lag 3, not the boundary "within 2 slots".
- **Rotation.** Every scenario recording is a single file, and the gap test asserts `files.len() == 1` and edits only the first accounts file.
  - I checked rotation separately (E2: `rotate_mb = 0.05` gives 11 journal, 152 accounts, 177 decision and 45 commit files). 3,000 decisions compare identically and the digests match.
  - With rotation on, every scenario passes except the gap test (its single-file assumption).
  - A real hour will rotate: 256 MB raw per file means 4-12 journal files an hour.
- **Fix.** Add the following:
  - a scenario with a meta.json gate and a non-sticky gate change (E1);
  - TX_COPY copies with earlier `t_rx`;
  - after-input `TIMER_COMMIT` / `TIMER_HK` scopes;
  - a lag-2 case in S7;
  - a rotated recording (tiny `rotate_mb` in the Rig);
  - an `Engine::run`-driven scenario (E1 shows the pattern).

### 6. Minor: the run never records its digests

- **Where:** `Engine::digest` and `decision_digest` are compared only in-process: the Rig against the replay (`src/scenarios/mod.rs:307`). No run output carries them; I checked status.jsonl, stop.json and meta.json.
- **Problem.** On a real recording, "replays identically" can check decisions and commits only, never the state.
- **Fix.** Write `digest` / `decision_digest` (after `finish`) in the final status line or stop.json. `arbx replay --compare` then checks them when the replay ran to the end. Note also that `finish()` empties `opps` and `sigs` before the digest is taken, so the final digest cannot see them. A digest taken just before `finish`, recorded on both sides, would be stronger.

### 7. Minor: "streaming" holds per rotation file, but the compare inflates whole files into JSON trees

- **Where:**
  - `src/replay.rs:598-621`: `read_lines` / `Lines` hold a whole decisions or commits file as `Vec<serde_json::Value>`, for the run and for the replay;
  - `:186-212`: `AcctSource` holds a whole accounts file's records with full data.
- **Proof.** CLI on the synthetic 10-minute run: accounts.bin 44.5 MB raw (28,717 records), decisions 48.6 MB raw. Peak RSS was **138 MB without `--compare` and 594 MB with it**: about 4.7× the raw JSON for the two decision files.
- **Estimate.** At the default `rotate_mb = 256` (raw), the compare peaks at about 2 × 256 MB × 4.7 ≈ **2.4 GB**, and the drive at about 0.5-1 GB. The field replay should run on a machine with that free memory, not beside a live segment on Cherry.
- **Fix:** stream lines (parse one at a time) and keep only the main lines' compared fields.

### 8. Minor: `arbx quote --batch` is O(questions × records)

- **Where:** `src/replay.rs:1029-1060`: each version is a linear scan of the accounts index. `:986-1006`: `QuoteHook` loops over every question on every ACCOUNT record.
- **Proof.** On the 28,717-record synthetic run, 500 questions take 0.63 s, 2,000 take 0.83 s and 8,000 take 1.63 s.
- **Estimate.** At R8's scale (every successful swap of an hour: about 10^5 questions against about 10^6 records) this is roughly 10^11 iterations, about 10-25 minutes per hour of recording.
- **Fix:** hash maps from aseq, (slot, wv) and txn to question indices.

### 9. Minor: output directory hygiene

- **Default `--out`.** It is `<run>/replay-<unix seconds>` (`:513`), inside the recording.
  - Every replay rewrites almost everything the run wrote, a full journal.bin included: 22 MB beside a 25 MB run on the synthetic data, about 1.5-3 GB per hour on real data.
- **Concurrent runs.** Two replays started in the same second share one directory: the non-empty check (`:514`) races. Reproduced: both exited 0, wrote the same files, and left one `replay-1791161820/`.
- **Refused `--set`.** A refused `--set` (exit 2) leaves a half-made out dir (`events.jsonl`, `feedhealth.jsonl`, `keepalive.jsonl`), because the recorder starts (`:515`) before the overrides are validated. A later replay to the same `--out` is then refused.
- **Fix:**
  - validate the overrides (and `inputs()`) before `rec::start`;
  - create the out dir exclusively, or add a pid or random suffix;
  - make the default out a sibling of the run, or require `--out`;
  - turn off the replay's journal and other by-product streams (the replay journal is "not replayable" anyway).

### 10. Minor: `price()` (quote, reprice) is not the decision's pricing

- **Where:** `src/replay.rs:792-802` goes through `Engine::refresh_route` (`src/engine.rs:2047`).
- **Differences from `evaluate_pool` (`src/engine.rs:2320`):**
  - the DAMM v2 point is `self.slot`, where the decision uses the Clock sysvar's slot (`dslot`);
  - pending, contested or unverified DLMM bin arrays are not skipped (`&[]` against `pending_arrays`);
  - without a Clock, time falls back to the **real** clock (`unix_now()` outside the virtual clock), where the decision uses the engine's `t_now`.
- **Effect.** A quote can differ from the decision it should reproduce. `requote_same_gross` catches this in reprice, but `arbx quote` has no such check.
- **Fix.** Factor the decision's leg construction (clock slot, skip list, time) into a function that both paths call. Add `pending` / `unverified` flags to the quote's `state[]`, so R8 can see a torn pre-state.

### 11. Minor: fixture integrity relies on the file itself

- **Where:** `tools/capture-fixtures.py` `--manifest` / `--verify` (`fixture_files()` covers `testdata/legacy` and `testdata/wallet` only).
- **Problem.**
  - The claimed "232 files, 0 problems" checks no WP-09 file.
  - `accounts.json` carries each account's sha256 next to its bytes, which catches an accidental edit but not a regenerated or replaced file.
  - `capture.json`'s sha256 is recorded inside `accounts.json`.
  - Nothing pins `accounts.json` itself.
- **Fix:** add `testdata/scenarios/{capture,accounts}.json` to the manifest. The expected outputs stay blessed by design.

### 12. Minor: provenance of a replay

- **Same build.** The module doc says "a replay reproduces a run of the same build", but nothing compares meta.json `build` (commit, dirty sha256) with the replaying binary. A different build is reported only as differences, without saying why.
  - Fix: record both in replay.json, and warn (or refuse without `--any-build`) when they differ.
- **Older recordings.** Recordings made after WP-03 but before WP-09 have no `pools.json`, and meta.json `pools` holds only a summary, so they cannot be replayed. The PLAN's field acceptance says "made after WP-03"; in practice it means "made with WP-09 or later".

### 13. Minor: the own-landing heuristic

- **Where:** `src/replay.rs:425-427`.
- **Problem.**
  - INPUT 7 `wallet_tx` with `ok: true` is taken as "our landing". During a shadow soak, any wallet transaction (the owner's top-up, the go-live wallet-prep ATA creations) marks every later difference `after_own_landing`. This only labels differences, but the labels mislead.
  - INPUT 9 is read as `{error, landed.sig}`. WP-05 changes it to `{what: fired | statuses | dry_sim, …}` (`exec.rs` `Settled::json`), so that branch goes dead.
- **Fix:** use the executor's own attempt signatures (attempts.jsonl `tx.sig`, or WP-05's statuses and wallet settlement).

### 14. Minor: exit codes and robustness

- Every error exits 2 "refused": an I/O error, a corrupt file, a busy out dir.
- The CLI help says 1 means differences, but without `--compare` exit 1 also means recorder drops.
- The backpressure loop (`:445-452`) waits forever if a recorder writer thread dies (its queue never drains).
- A corrupt or torn accounts file aborts the whole replay. I saw `data_xxh3 mismatch` when one record was removed mid-chain. A real queue drop is safe, because a dropped record never reaches the XOR encoder.

### 15. Minor (informational, journal format of WP-03 and WP-04): inputs the replay cannot rebuild exactly

- **TX_COPY.** It carries no slot, and the replay uses `slot: 0` (`journal.rs:466`). The run raises `shred_slot` from a later unexecuted copy (`engine.rs:1613` `on_tx`). That changes `tip_slot()` while the state is unavailable, and the digest.
- **Protobuf transactions** are rebuilt with `is_vote = false` (`journal.rs:372`).
- **No-executor gate reads:** finding 3.

### Nits

- **N1. Documentation drift.**
  - §4.13 still says the watch gate records are "not a decision input … the engine ignores it"; WP-09 now makes them one.
  - §4.50's summary list lacks `own_landings`, `first_own_landing_t_ns`, `diffs_after_own_landing` and the per-diff `after_own_landing`.
  - "exits 0 when ok (or without `--compare`)" is wrong when the recorder drops.
- **N2. S5's trap is small.**
  - On the fixture, the torn snapshot's best net is **+458,436 at 0.2 SOL**, and at the bolt size it **loses 48,064,148**. Historically it predicted +19,967,380 at that size.
  - The committed state loses 134,001,185 at the bolt size, comparable to the historical −103,451,784.
  - The scenario still catches the regression: mutant M1b fails S5. The declared deviation is acceptable, but the docstring should say the fixture's trap appears only at small sizes.
- **N3. Narrow test fixtures.**
  - `pools_json_round_trips_the_registry_and_the_watch_list` uses a single pair, so the pair-order claim is untested with several pairs. I found no decision that depends on the pair map's iteration order (`pools_of` and `resync_chunks` sort), so this is cosmetic.
  - `journal_and_accounts_gaps_are_reported_and_skipped` assumes one file (finding 5).
- **N4. `stages` is excluded whole.** Only `t_priced` and `t_decided` are clock reads. `t_update_recv`, `t_commit` and `t_engine` are journaled values and could be compared.

## 5. Mutation tests and experiments

All mutants were guarded by `ARBX_MUT` in one scratch build (`apply_mutants.py`) and run against `scenarios::*` (21 tests).

| Mutant | What it breaks | Scenarios that fail |
|---|---|---|
| none | baseline | none (21 pass) |
| M1 | the ready check ignores pending commit groups (a route through a half-written pool is priced) | S1, S1b |
| M1b | a group resolves when **any** member has arrived (a torn state is priced) | S1, S1b, **S5**, S6 |
| M2 | a decoded swap is evaluated at once (a decision on a hint) | S2, S3, S6 |
| M2b | the hint's prediction is written into the store (arb-lab's stacked predictions) | S3 (S2 asserts only "no decision") |
| M3 | the consistency-set skew rule is off | S4 |
| M3b | slots compared across every part (the pool account included) | S4b and 10 others |
| M4 | Tier A complete from the start | S7 |
| M4b | lag rule off | S7 |
| M4c | lag of 3 allowed | S7 |
| M4d | stricter: lag 2 shuts | **none** (boundary untested, finding 5) |
| M5 | dead or abandoned slot versions not dropped | S8, S8b |
| M5b | no `fork_priced` follow-up | S8, S8b |
| M6 | a failed lookup-table fetch gives up at once (I-6 regression) | S6 |
| M7 | late members ignored (no `torn_suspect`) | S1b′ |
| R1 | replay ignores the run's SendGate (meta.json and watch records) | **none** (finding 5) |
| R2 | replay runs every TIMER with `TIMER_ALL` | **none** (finding 5) |
| R3 | replay drops TX_COPY records | **none** (finding 5) |
| R4 | compare ignores `routes` | what_if (`by_field.routes` asserted) |

Answer to the brief: re-enabling pricing on a torn state (M1, M1b) fails S1 and S1b, and M1b also fails S5. Re-enabling decisions on a prediction fails S2 and S3 (M2); a prediction written into the store fails S3 (M2b). The run-side assertions are strong.

**Experiments:**
- **E1:** the real `Engine::run` loop with a sampled gate; finding 3.
- **E2:** rotation into many files. It replays identically, and every scenario passes under rotation except the single-file gap test.
- **E3:** `ok` on incomplete recordings; finding 2.

The code is in `scratchpad/r3/wp09-review/review_exp.rs`.

## 6. WP-05 integration: what the merge must add for a SHADOW recording to replay identically (go-live item 3)

WP-05 (uncommitted on master) builds an executor in every run (`exec::Mode::Shadow` holds no key and no send path). `after_opportunity` then calls `Exec::inputs` and `Exec::decide`, and journals INPUT 3 `src` "decision" when the tuple (gate mode, leader kind, token ok, recorder ok) changes. Decisions gain `sent`, `would_send` and `reason_ungated`; `ev`, `rank` and `crowding` become real; `decision_digest` folds `exec` and `exec_verdict`. This replay builds `Engine::new_offline` (no executor). On a WP-05 shadow recording it would therefore:
- drop `verdict` / `reason` (finding 4);
- compare `sent` / `would_send` / `reason_ungated` and find them different on every would-send.

So `ok` would be false. To replay identically:

1. **An offline executor in the replay.** When engine_init says `executor: true`, build `Exec` in an offline mode:
   - no RPC, no send paths, no key, no network;
   - every send becomes a would-send;
   - `decide()` runs `send_checks` and the route checks exactly as in the run, and `build()` builds without signing.
2. **The executor's boot state, journaled.** Everything `Exec::new` reads at boot that is not config must go into the boot section (an `exec_init` INPUT at t 0, or engine_init):
   - the `[exec] alts` lookup tables' contents;
   - the PumpSwap GlobalConfig;
   - the held mints (wallet token accounts; today only in meta.json);
   - the crowded-pools list contents, both for `Activity::new` (the engine's `set_crowding`, which the replay must also call) and for the executor;
   - the size cap and any bankroll-derived cap;
   - the would-send path rate;
   - the tip policy state;
   - the mode.

   Without these, `oversized` / `build_error` / `rent_cap` / `crowded_pool` cannot be reproduced, and the replay would depend on files outside the run directory.
3. **Decision-point records.** These are INPUT 3 `src` "decision" records. The engine writes each one right after the input (or TIMER) whose handling made the decision, with the same `t_engine`.
   - The driver must look ahead: stage the following decision records before it hands over that input.
   - The offline executor's `inputs()` must then return the journaled values for the `opp` named:
     - gate mode **and reason**;
     - leader slot, identity, kind and `kind_src`;
     - `jito_token_ok`;
     - `recorder_ok`.
   - Between records, the last one holds.
   - `journal::replay` currently counts and skips them (`gate_observed`, `journal.rs:487`).
   - **WP-05 must also write a record when the gate's *reason* changes while its mode stays the same.** Decisions print `gate_shadow:<reason>`, but the tuple tracks only the mode.
4. **Executor inputs fed, not skipped.** The replay must feed to the offline executor (journaled settled and wallet records, with their `t_ns`):
   - INPUT 9 `settled`, in WP-05's `{what: fired | statuses | dry_sim}` form (needs a `Settled::from_json`; `journal.rs:485` skips it today);
   - INPUT 7 `wallet_tx` (`on_wallet_tx`);
   - INPUT 5 `inflight_release` (`on_release`);
   - the housekeeping `x.tick()` (already on the engine's timers).
5. **No real-clock reads in executor state.** These must take the engine's `t`, or be journaled:
   - `Exec::wants_sim` (rate window on `now_ns()`);
   - `big.refund(now_ns())` in `on_settled`;
   - `t_wallet: now_ns()` in `on_wallet_tx`.

   `RouteIn.t_priced` / `t_commit` (clock reads in the run, journaled times in the replay) must never decide a verdict. WP-05's `poh_of` fallback to the process-wide PoH index (shred walks, not journaled) must not reach a compared field or a verdict.
6. **compare().**
   - Narrow `verdict_from_recording` to the genuinely timing-dependent outcomes (finding 4).
   - Compare `sent`, `would_send`, `reason_ungated`, `ev`, `rank`, `crowding` and `attempt` (deterministic once items 1-5 hold).
   - Compare `inflight_*` and `band_throttle` (S9, S11).
   - Remove `gate_sampled`.
   - Make `ok` require a whole replay (finding 2).
7. **Run-side digests** (finding 6), so that the gate check covers the state and `decision_digest` (which now folds the executor's verdicts), not only the decision lines.
8. **Own landings** (finding 13): detect them from WP-05's statuses and wallet settlement of the executor's own attempt signatures. This is not needed for a shadow soak.
9. **Until items 1-6 exist,** `arbx replay` should flag executor recordings explicitly (`executor_replayed: false`, `ok: false`) instead of skipping their verdicts. Treat the go-live replay as not done until then.

**Textual merge risk is low.** WP-05's hunks in `main.rs` (roughly: the Cmd enum at 69-95, main() at 216-329, run() at 944-1376) and in `lib.rs` (modules above `provenance`) do not overlap WP-09's lines (the `Cmd` variants after `KeystoreEncrypt`, the match arms after `GrpcProbe`, the `write_pools_json` line after `let reg = Arc::new(reg)`, and `replay` / `scenarios` after `rec`). The risk is semantic, as listed above.

## 7. Memory and speed

- **Synthetic run through the CLI** (lane binary, 10 minutes of engine time, 71,029 journal records, 28,717 account records, 15,125 decisions):
  - 0.93 s and 138 MB peak without `--compare`;
  - 1.71 s and 594 MB with it;
  - 628× real time.
  - In-test runs give 575-650×. The claimed "about 650×" holds for this mix.
- **A real hour is heavier**, so expect well above 20× but not 600×:
  - inputs: about 700 forwarded transactions/s with their bytes (TX_FIRST decode), plus rivals, triggers and txarr re-recorded;
  - output: the replay rewrites a full journal.bin (0.5-1 GB/h compressed).
- **Peak memory** is bounded by one rotation file per stream: about 0.5-1 GB for the drive at the default 256 MB raw. The compare's JSON trees can reach about 2.4 GB (finding 7).

## 8. Process note: the shared target directory

All lanes build the package `arbx` into `…/targets/lanes`.

- **Artifact names.** Cargo's metadata hash does not include the workspace path, so two worktrees with the same Cargo.toml and Cargo.lock write the *same* artifact names (`deps/arbx-<hash>`). My first unmodified scratch build reused the lane's lib-test artifact name. Cargo rebuilds on the next lane build, because the fingerprint changed, so nothing is left wrong; I renamed the scratch package for every later build.
- **The uplifted binary.** WP-16 has a different Cargo.toml, so its hashes differ. But every lane uplifts `target/release/arbx`, and `tests/replay_cli.rs` runs `CARGO_BIN_EXE_arbx` (that path). Cargo holds the build-directory lock while it compiles, not while the tests run, so a WP-16 build that lands between a WP-09 build and its test run makes `replay_cli` exercise the other lane's binary. I checked the binary's sha256 before and after my run (unchanged).
- **Recommendation:** one target directory per lane, or run `replay_cli` against a copied binary.

## Disposition (2026-10-05, the fix on `lane/wp-09`)

**Where.** The fix is the WP-09 commit on `lane/wp-09` (base master 323e3bf; master has since moved to 6760f10, WP-05). Built with `CARGO_TARGET_DIR=…/scratchpad/targets/wp09`, the lane's own (§8), `CARGO_BUILD_JOBS=4`. `exec.rs` is not touched. The `engine.rs` edits are small and each is marked `---- WP-09` (a field, its initializer, one line in the no-executor branch, three lines in `finish`, and one new `impl Engine` block after the main one).

**Results.**
- `cargo build --release`: the two pre-existing warnings only (`main.rs` irrefutable `if let`).
- `cargo test --release`: **361 passed, 0 failed, 2 ignored**: lib 335 (+1 ignored), bin 11, legacy_fixtures 4, meta_config_hash 1, replay_cli 1, runtime_isolation 2 (+1 ignored), stop_path 6, supervisor 1. WP-09's own: 32 `scenarios::*` (18 in `harness`), 6 `replay::tests`, 1 new `rec::journal` test, `tests/replay_cli.rs`.
- Toolkit: `cd tools/arbx-report/tests && python3 -m unittest discover -s .`: 83 tests OK (4 skipped), with the 4 new ones of `test_wp09_recording.py`.
- `python3 tools/capture-fixtures.py --verify`: 234 files listed, 0 problems (the scenario inputs are now 2 of them).
- `arbx check` on `deploy/arbx-stage0.toml` and `deploy/arb.toml`: both exit 0.
- **Trial merge with master 6760f10** (`git merge-tree` on a temporary commit object; no ref or worktree touched): one conflict, the three lines of the no-executor branch in `after_opportunity` (keep WP-05's comment and `return crate::exec::Decided::reject(why);`, with WP-09's `let why = self.gate_no_executor(id);`). `MEASUREMENT.md`, `lib.rs` and `main.rs` merge clean. The merged tree, built in scratch, passes its whole suite (lib 367 + 3 ignored; the one failure seen, `probe::tests::busy_finds_live_segments_and_bot_processes`, was the scratch `TMPDIR` path exceeding a Unix socket's 108 bytes, and passes with the default one).

### The findings

| # | Disposition | What changed | Tests |
|---|---|---|---|
| 1 Blocker | **Fixed** | `pools.json` is MEASUREMENT §4.29's list again, exactly. `pairs` and `watch` moved to a new `registry-run.json` beside it (`arbx.registry-run/1.0`), which also records pools.json's sha256: a replay refuses a pair that does not belong together. meta.json `pools.file` is set, with `file_sha256` and `registry_run_file`. MEASUREMENT §4.2, §4.29. The toolkit is unchanged (it reads the list) | `pools_json_round_trips_the_registry_and_the_watch_list` (the list, every §4.29 field, two pairs now: N3); `the_toolkit_fixture_is_this_codes_recording` (the fixture is what the code writes); toolkit `test_wp09_recording.py` reads a real recording made by this code (`tools/arbx-report/tests/fixtures/wp09-run/`: pools.json, registry-run.json, accounts.bin): blockctx maps `pool_index` to the pools and attributes the trade to its pool, route accounts come from the registry, registry-run.json is listed, not refused. On the first draft's object form 3 of its 4 tests fail |
| 2 Major | **Fixed** | `ok` needs a whole replay. replay.json `whole` and `not_whole: [{why, n, detail}]`: `journal_gap`, `accounts_missing`, `accounts_gap`, `verdict_mismatch`, `run_recorder_loss` (manifest.json drops, suppressions, I/O and encode losses of journal, accounts, decisions and commits, and records lost at close), `replay_recorder_loss`, `executor_not_replayed`. Exit 1 when not ok, with or without `--compare`. replay-diff.json keeps `differences_ok` apart and carries the same `ok` | `ok_needs_a_whole_replay` (E3's three cases, each with 0 field differences and `ok` false, plus a run whose recorder dropped decisions, through `cli_replay` too: exit 1); `replay_cli` (`NOT WHOLE: run_recorder_loss`, exit 1) |
| 3 Major | **Fixed** | A decision without an executor journals the gate it read: `Engine::gate_no_executor` writes INPUT 3 `src` "decision" `{mode, reason, detail, since_ns, sticky, src, opp, executor: false, why}` whenever the decision's reason changes (the reason, not only the mode). `journal::replay` stages every decision-point record ahead of the record whose handling made it (the records after it, TICKs skipped; `Engine::gate_seen.script`), and the engine applies each at its opportunity. The replay no longer applies the 100 ms `watch` samples (§4.13 holds again: status only), and `gate_sampled` and `GATE_SAMPLE_NS` are gone | `the_gate_each_decision_read_is_journaled_and_replayed` (pause, a stale sample, resume, pause: deterministic); `a_run_loop_with_a_paused_gate_replays_identically` (E1 on the real `Engine::run` loop and clock, a 100 ms sampler thread, a pause and a resume from a third thread: every decision identical, digests the same) |
| 4 Major | **Fixed** | `verdict_from_recording` is gone. A reason is not compared only when the run had an executor, its reason is past the engine's state and pricing stages, and the replay gave its stand-in (`no_executor` / `gate_*`): counted as `executor_verdicts_not_replayed`. A state- or pricing-stage reason on either side is compared (`sent` against `warmup` differs). `inflight_*`, `band_throttle` and the send-queue reasons are compared like any other. The executor's own fields (`attempt`, `ev`, `rank`, `crowding`, WP-05's `sent`, `would_send`, `reason_ungated`) are counted, not compared, for a run with an executor only. Such a recording is never OK: `not_whole` `executor_not_replayed`, "executor replay not implemented" | `reason_stages_and_the_executor_rule`; `a_run_with_an_executor_is_not_ok_until_its_executor_is_replayed` (its lines compare equal, and it is still `ok: false`) |
| 5 Minor | **Fixed** | R1, R2, R3 and M4d now each fail a test; a rotated recording and an `Engine::run`-driven run are scenarios | R1: the two gate tests above; R2: `timers_are_replayed_at_their_journaled_scope` (a commit-only TIMER with housekeeping due: the decision stays `warmup`); R3: `later_copies_are_replayed_with_their_time_and_slot` (a copy from feed 2 received earlier: `t_first_shred` in the decision and the commit line); M4d: S7 asserts a lag of 2 slots is still ready; rotation: `a_rotated_recording_replays_identically` (20 KB files) |
| 6 Minor | **Fixed** | `Engine::finish` writes an events.jsonl `engine_digests` record: `before_finish` (the state once the last journaled record was handled: what a whole replay reaches, `opps` and `sigs` still in it) and the digests after `finish`. A replay that ran to the end, without `--set`, checks both; a difference makes `ok` false. replay.json `digests: {checked, same, not_checked, run, replay}` | every scenario (`finish_and_replay` asserts `checked` and `same`); `the_run_records_its_digests_and_the_replay_checks_them` (a recorded digest changed: lines identical, `ok` false); `replay_cli` |
| 7 Minor | **Fixed** (the compare) | The compare reads decisions and commits a zstd frame at a time and holds one line per side; the compared decision ids are kept as ranges. On the kept 10-minute synthetic run through the CLI: **137 MB** peak with `--compare` (was 594 MB), 138 MB without; 1.57 s and 1.04 s; 644× real time. The drive still reads journal.bin and accounts.bin one rotation file at a time (the review's estimate, 0.5-1 GB at 256 MB raw, stands; not changed) | `lines_stream_across_frames` (a line split across frames, a torn last frame, a plain file) |
| 8 Minor | **Fixed** | `quote`: one pass over accounts.bin finds the versions asked (maps from aseq, `slot:write_version` and transaction), and each record looks up its questions. CLI on the same run: 500 questions 0.11 s, 2,000 0.26 s, 8,000 0.97 s, 32,000 2.05 s (was 0.63 s, 0.83 s, 1.63 s for the first three): linear | `a_quote_batch_is_one_pass` (4,000 questions) |
| 9 Minor | **Fixed** | `--out` must be a new directory, made exclusively (`create_dir`); the default is `./replay-<run>-<unix s>-<pid>`, never inside the run nor beside it (a campaign directory is globbed by run-w.sh as `<name>-p*`). Everything refusable (no journal, no pools.json or registry-run.json, no engine_init, another `[strategy]`, an unknown `--set`) is refused before the directory exists. The replay's own journal stream is switched off. The recorder backpressure wait gives up after 60 s (`replay_recorder_loss`) instead of waiting forever | `the_output_directory_is_new_and_never_half_made`; `what_if_overrides…` and `recordings_that_cannot_be_replayed…` assert no directory is left; `replay_cli` (an existing `--out`: exit 2) |
| 10 Minor | **Fixed** | `Engine::quote_route` prices as a decision does: `route_in`'s legs (`chain_now`: the Clock's time and slot, else the engine's time; `skip_arrays`: pending, contested or unverified DLMM arrays left out) and `price_route`'s CU and fee rule. `arbx quote` and `--reprice-sizes` use it; replay.rs no longer builds a `RouteIn` (WP-05 changes its fields). `state[]` carries `pending`, `contested`, `unverified` | `reprice_sizes_requotes…` (the decision's gross, net and CU); `quote_prices_a_route…` (gross, net, CU; the flags on a half-written and a pending state) |
| 11 Minor | **Fixed** | `capture-fixtures.py --manifest` / `--verify` and `tests/legacy_fixtures.rs` include `testdata/scenarios/{capture,accounts}.json`; the expected outputs stay blessed | `every_fixture_matches_its_sha256`; `--verify` |
| 12 Minor | **Fixed** | replay.json `build: {run, replay, same_source, same_binary}`; a different source (commit, dirty flag, dirty_sha256) is a warning on stderr and in the CLI's output. "Made with WP-09 or later" is in MEASUREMENT §4.29 / §4.50 | (warning path not unit-tested: needs a meta.json of another build; `build_check` is a pure comparison) |
| 13 Minor | **Partly** | INPUT 7 `wallet_tx` no longer counts as our landing (an owner's top-up has it too). INPUT 9's `landed.sig` is the pre-WP-05 form; WP-05's `{what: fired \| statuses \| dry_sim}` needs the merge (below) | |
| 14 Minor | **Partly** | Exit 1 now means "not ok" (differences or not whole), documented. The backpressure wait is bounded. Kept: every error exits 2 (the message says which); a corrupt accounts file still aborts (a real queue drop never reaches the XOR encoder) | |
| 15 Minor | **Fixed** (TX_COPY) | TX_COPY appends `u64 slot` after its PoH tail (same framing, no version change: both readers ignore the tail; MEASUREMENT §4.13); the replay feeds a copy at its slot. Protobuf `is_vote`: unchanged, no engine decision reads it | `tx_copy_carries_its_slot_and_older_records_read`; `later_copies_…` (the copy's slot raises the shred slot: the digests) |
| N1 | **Fixed** | §4.13 (watch records status only again; the no-executor record; TX_COPY's slot), §4.50 rewritten (whole, digests, executor rule, exit codes, out directory, quote flags), §4.2, §4.29, A.6 (`engine_digests`) | |
| N2 | **Fixed** | S5's docstring: the fixture's trap is a profit at small sizes only | |
| N3 | **Fixed** / kept | Two pairs in the round trip. The gap tests keep their single-file edit; rotation has its own test | |
| N4 | **Fixed** | `stages` compared field by field except `t_priced` and `t_decided` | `diff_fields_names_the_fields` |
| §8 | **Fixed** | The lane's own target directory; `tests/replay_cli.rs` copies the binary first, checks the copy against the build's, and runs the copy | |

### Mutation check of the fix

15 mutants, each guarded by `ARBX_MUT` in one scratch copy of the fixed lane (`scratchpad/r3/wp09-fix/apply_mutants.py`, own target directory), run against `scenarios`, `replay::` and `rec::journal` (45 tests). The baseline passes 45 of 45; every mutant fails at least one test.

| Mutant | What it re-introduces | Tests that fail |
|---|---|---|
| B1 | pools.json as one object (the first draft) | `pools_json_round_trips…`, `the_toolkit_fixture…`, `recordings_that_cannot_be_replayed…` |
| M2 | `ok` ignores whether the replay was whole | `ok_needs_a_whole_replay`, `a_run_with_an_executor…` |
| M3a (= R1) | the replay ignores the run's gate records | `the_gate_each_decision_read…`, `a_run_loop_with_a_paused_gate…` |
| M3b | the no-executor decision journals nothing | the same two |
| M3c | the replay applies the 100 ms samples (the first draft) | `the_gate_each_decision_read…` (the stale sample) |
| M4 | the first draft's verdict rule (any executor-side run reason taken from the recording) | `reason_stages_and_the_executor_rule` |
| M4b | an executor recording is not flagged (a silent OK) | `a_run_with_an_executor…` |
| M5 | the run records no digests | 29 tests (every scenario's replay) |
| M5b | the replay does not check the digests | 29 tests |
| R2 | every TIMER replayed with `TIMER_ALL` | `timers_are_replayed_at_their_journaled_scope` |
| R3 | every TX_COPY dropped | `later_copies_…` |
| R3b | TX_COPY fed without its slot | `later_copies_…` (digests only: the lines are identical) |
| M4d | lag 2 shuts | S7 |
| O1 | an existing `--out` accepted | `the_compare_window…`, `the_output_directory…` |
| O2 | the overrides checked after the directory is made | `what_if_overrides…` |

### For the WP-05 merge

What the merge must add for a WP-05 **shadow** recording to replay identically (go-live gate item 3). WP-05 (6760f10) builds an executor in every run (`Mode::Shadow`: no key, no send path), so every such recording is `executor_not_replayed` until items 1-6 exist; this commit reports it as `ok: false`, never a silent OK. A run whose shadow executor did not start (decisions `no_executor`) already replays: its gate reads are journaled by `gate_no_executor`.

1. **An offline executor in the replay.** When engine_init says `executor: true`, build it with `Exec::assemble(cfg, <an offline Rpc>, None, rec, <a sink channel>, feeds, alts, pump, held, mode, None)` inside a tokio runtime (`assemble` takes `Handle::current()`), from the boot record of item 2; `set_health(e.health_flags())`, `set_gate` from the staged records (item 3), no `LeaderBook` (the kind comes from the records); `e.exec = Some(x)`. No RPC, no send path, no key, no network: every send a would-send. A dry-run recording signs with a throwaway key: its signatures and bundle bytes cannot be compared (shadow needs none).
2. **An `exec_init` boot record** (an INPUT at `t_engine_ns` 0, or fields of engine_init): what `Exec::new` reads that the frozen config does not hold: the `[exec] alts` tables' contents, PumpSwap's GlobalConfig, the held mints (the wallet's token accounts), the mode; and the crowded-pools list's contents, for the executor and for `Activity::new` (the replay must call `e.set_crowding` as `main.rs` does). A bankroll-derived size cap, if WP-06 / WP-07 add one, belongs there too, and so would WP-05 review's open "crowding across segments" preload. Without this, `oversized`, `build_error`, `rent_cap`, `crowded_*` and `rank` cannot be reproduced, and the replay would need files outside the run directory.
3. **Decision-point records to the executor.** `journal::replay` already stages every INPUT 3 `src` "decision" record ahead of the record whose handling made it (this commit). Route them to the offline executor instead of `Engine::gate_seen.script` (which only the no-executor branch drains: with an executor it would grow without bound): `Exec::inputs()` must return the journaled gate mode and reason, leader `{slot, identity, kind, kind_src}`, `jito_token_ok` and `recorder_ok` for the opportunity being decided (the last record at or before it), not the replay's own gate, LeaderBook, token or recorder. **WP-05 must also write a record when the gate's reason changes while its mode stays** (its tuple tracks the mode; decisions print `gate_shadow:<reason>`); WP-09's no-executor records already carry `why`.
4. **Executor inputs fed, not skipped.** INPUT 9 `settled` in WP-05's form (`{what: fired | statuses | dry_sim}`) back into `Event::Settled`: it needs a `Settled::from_json` (`Statuses` holds `&'static str` labels); `journal::replay` counts INPUT 9 as `skipped` today. INPUT 7 `wallet_tx` and INPUT 5 `inflight_release` are already fed as inputs, and WP-05's engine hands them to its executor; `x.tick` runs on the journaled timers.
5. **No real-clock reads in executor state.** `Exec::wants_sim` (`now_ns()` rate window), `big.refund(now_ns())` in `on_settled` (WP-05 review #13), `t_wallet: now_ns()` in `on_wallet_tx`: take the engine's `t` or the record's. Build and sign timestamps (`t_built`, `t_signed`) are stage times and must decide nothing. `poh_of`'s fallback to the process-wide PoH index (shred walks, not journaled) must not reach a verdict or a compared field (`note_poh` is a gauge).
6. **`compare()`** once 1-5 hold: drop the executor exemptions (`EXECUTOR_FIELDS`, `executor_not_replayed`) for recordings with an `exec_init` record, and compare `sent`, `would_send`, `reason_ungated`, `ev`, `rank`, `crowding`, `attempt`, `band` and `band_at_opp`, the in-flight and band outcomes (S9, S11) and every verdict. `reason_stage` already knows WP-05's queue names (`crowded_skip`, `would_rate`, `would_rate_crowded`). Keep `executor_not_replayed` for executor recordings made before the merge (no `exec_init`).
7. **Digests.** `decision_digest` already folds `exec` and `exec_verdict`, and the run's digests are recorded (this commit). `Engine::digest()` does not cover the executor's own state (open attempts, the in-flight map, the rate and band buckets, the tip policy): add an `Exec::digest()` folded into it.
8. **Own landings** (finding 13): from WP-05's statuses and wallet settlements of the executor's own attempt signatures; INPUT 9's `landed.sig` no longer exists. Not needed for a shadow soak.
9. **Tests with the merge:** `a_run_loop_with_a_paused_gate_replays_identically` with a `Mode::Shadow` executor in the run (the E1 pattern), replayed `ok` and identical; S9 (in-flight) and S11 (bands and crowding) as scenarios; a WP-05 recording made before the merge reported `executor_not_replayed`.

**Mechanics.** One textual conflict (above). Nothing else in this commit depends on WP-05's types: replay.rs no longer builds a `RouteIn`, and `EngineInit` and `Engine::new_offline` are unchanged on master.

### Open issues

- **Go-live gate item 3 is not met by WP-09 + WP-05 as they stand**: a WP-05 shadow recording is `executor_not_replayed` until the merge items 1-6. Treat the go-live replay as not done until then.
- The field acceptance (a 1 h Stage-0 recording, 100 % of the compared fields, ≥ 20×) is owner-run and needs a recording made with WP-09 or later (pools.json, registry-run.json, the gate records, the digests).
- The drive's peak memory is still one rotation file per stream (journal.bin, accounts.bin): about 0.5-1 GB at the default 256 MB raw (review §7); a frame-at-a-time journal and accounts reader would bound it.
- Finding 14's rest: errors (I/O, corrupt files, refusals) still share exit 2.
- PLAN WP-09 item 5 (the real-data regression slice in `testdata/replay/`) waits for Stage-0 recordings; S9-S16 are part 2.

## Executor replay (2026-10-05, on master after the merge b63dbe2)

**Where.** The "For the WP-05 merge" items above, on master (WP-05 6760f10 merged with this lane as b63dbe2), commit "WP-09: executor replay". Built and tested in the main tree on its own `target/`, `CARGO_BUILD_JOBS=3`.

| Item | Disposition | What | Tests |
|---|---|---|---|
| 1 An offline executor | **Done** | `Exec::offline(cfg, exec_init, rec)`: `Exec::assemble` on the record's lookup tables, PumpSwap GlobalConfig and held tokens, with no RPC endpoint (`Rpc::race(vec![])`), no send path and no key (a dry run signs with a new throwaway key: only its signatures differ), the record's size cap, would-send rate and tip policy; assembled on a runtime that is never driven. An offline executor spawns nothing: `simulate`, the dry run's simulation and the statuses checks keep their books and skip the call. Health is the replay engine's (`set_health`). Live and canary executors are not replayed (their sends cannot be): `executor_not_replayed`, with the mode | `an_offline_executor_reads_the_runs_records` |
| 2 exec_init | **Done** | INPUT 12 `exec_init`, `t_engine_ns` 0, right after engine_init (`Engine::journal_exec_init`; `run` calls it): `{mode, alts: [{table, addrs}], pump, held_mints, max_size_lamports, max_size_src, bankroll_cap_lamports (null until WP-06 / WP-07), would_send_per_sec, tips, crowding: {window_h, buckets, static_list}, cfg_sha256}`. The replay rebuilds the crowding map from it (`set_crowding`) and refuses a config whose executor sections hash otherwise (`exec::cfg_sha256`: `[live]`'s failed-fee cap left out, which `--budget-left` lowers per segment) | `exec_init_reads_back`, `the_executor_config_hash`, every executor scenario |
| 3 Decision records to the executor | **Done** | `journal::replay` stages the raw records (`Engine::gate_seen.script`); the no-executor branch reads their gate (`gate_of`), the executor branch hands them to `Exec::stage_seen`, whose send checks then read the run's gate mode and reason, leader kind (and `kind_src`), `jito_token_ok` and `recorder_ok` (the last record at or before the opportunity); the leader's identity and target slot are the replay's own, from the journaled schedule. A record staged at another opportunity, one that does not read, or one naming another identity or target slot is counted (`decision_records_mismatch`), executor decisions before any record read the gate stopped (`decision_records_missing`), records left unread by a replay that ran to the end are `decision_records_unused`: each makes the replay not whole. **WP-05's record is now also written when the gate's reason changes while its mode stays**, and carries the reason the check read | `the_gate_reason_an_executor_decision_read_is_journaled_and_replayed` (live, pause, the lag SLO's shadow over the pause, resume; without the reason's record the replay differs), `a_run_loop_with_a_shadow_executor_replays_identically` |
| 4 Executor inputs | **Done** | INPUT 9 `settled` in WP-05's `{what: fired \| statuses \| dry_sim}` forms is fed back (`Settled::from_json`, with `Fired`, `Sent` and `SigStatus` readers; a drop code read back as the sender's static string); an older form is skipped. INPUT 7 and 5 reach the executor as before; `x.tick` runs on the journaled timers | `settlements_read_back_from_the_journal`, `a_dry_run_replays_with_its_settlements` (the simulation's sims.jsonl line is the run's) |
| 5 No real clock | **Done** | `wants_sim(size, t)` and the dry run's simulation window run on the engine's time; `t_wallet` is the record's engine time; an attempt without a slot expires 120 s after its decision's engine time (`Open.t_engine`); the big-band refund was already the engine's (WP-05 #13). `poh_of`'s process-wide PoH index is read only in a run (an engine with I/O): it reaches a gauge and outcome lines, never a verdict, and a replay never reads it. Build and sign times stay stage times | (every executor scenario) |
| 6 compare() | **Done** | For a recording with exec_init every decision field is compared (the executor exemptions are off) and attempts.jsonl too, attempt by attempt on `attempt_projection` (`ATTEMPT_NOT_COMPARED`: `t_ns`, the stage times of the build, the signature and the send, the decision's `t_priced` / `t_decided`, the LeaderBook's `leader` snapshot, a dry run's signature and signer). For one without (an executor recorded before this, or a live or canary one) the exemptions stay, `executor_not_replayed` keeps it from being ok | S9, S11, the scenarios above; `a_recording_made_before_the_executor_replay_is_not_replayed` |
| 7 Digests | **Done** | `Exec::digest` (totals, counters, the in-flight map, the big-band bucket, cooling, the would-send and simulation windows, open and final attempts, its copies' arrivals, held tokens, the tip rotation, the last gate read) and `Activity::digest` folded into `Engine::digest` when the engine has an executor; an engine without one digests what it did before | every executor scenario (`finish_and_replay` checks the run's recorded digests) |
| 8 Own landings | Not done | Not needed for a shadow soak (as the review says) | |
| 9 Tests | **Done** | E1 with a `Mode::Shadow` executor in the run loop; S9 (`s9_inflight.rs`: same state blocked, new state, new leader allowed, same leader refused); S11 (`s11_bands.rs`: the ≥1M throttle and refill, ranks, a crowded small would-send, `crowded_skip`, a big crowded rank 3); the pre-merge recording; the dry run with settlements; the go-live item 3 hour (`synth.rs`) | |

**Go-live gate item 3, offline check** (`a_synthetic_shadow_hour_replays_identically`): a shadow run as `arbx run` makes one (`Mode::Shadow` executor, the SendGate shadow for the whole segment, WP-00's list naming CPMM, the Stage-0 config) over 3,600 s of engine time: 9,000 slots with the ring's head (stalled for 100 slots once), leader windows of 400 slots (one never came), 14,429 trades on the five USDC/SOL pools, an owner's top-up. 14,429 evaluations, 11,553 opportunities, 1,476 would-sends; behind the gate: 8,328 `band_throttle`, 1,106 `leader_skip_kind`, 536 `leader_unknown`, 107 `blockhash_stale`. The replay: 107,762 journal records in 6.4-7.3 s (490-560x real time over two runs), **ok and whole**, 14,429 decisions and 1,476 attempts compared, **all identical**, the run's digests reproduced (state `752399e437f9a861`, decisions `35cf08e65aed9d2c`), no decision-point record mismatched or left unread. The field acceptance (a 1 h Stage-0 recording) stays owner-run; it needs a recording made with this build (exec_init).

**Results** (the main tree, its own `target/`, `CARGO_BUILD_JOBS=3`):
- `cargo build --release`: the two pre-existing warnings only (`main.rs` irrefutable `if let`).
- `cargo test --release`: **408 passed, 0 failed, 4 ignored**: lib 380 (+3 ignored), bin 13, legacy_fixtures 4, meta_config_hash 1, replay_cli 1, runtime_isolation 2 (+1 ignored), stop_path 6, supervisor 1.
- Toolkit (`cd tools/arbx-report/tests && python3 -m unittest discover -s .`): 84 tests OK (4 skipped). `python3 tools/capture-fixtures.py --verify`: 234 files listed, 0 problems.
- `arbx check` on `deploy/arbx-stage0.toml` and `deploy/arb.toml`: both exit 0.

**Open.** Live and canary executors are not replayed (their sends: a replay would need the run's signatures and fires; WP-07). Item 8 (own landings from WP-05's settlements) is not done. `arbx quote` replays without the executor (it reads the store only). Scenario expected files carry no executor fields (decisions' structural assertions do); WP-16 re-blesses them. The drive's memory and exit-code notes above stand.

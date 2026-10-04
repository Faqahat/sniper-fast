# WP-03 review: chain inputs, raw chain recording, input journal, gRPC probe

**Date:** 2026-10-04. **Reviewer:** adversarial review, read-only (no code changed).
**Plan:** `docs/PLAN.md` WP-03 (items 1-11, offline acceptance, definition of done), `docs/MEASUREMENT.md` §4.12-§4.17, §4.27, §4.49, and `docs/PLAN-ADDENDUM.md` I-2..I-5, which was committed (6349694, 16:13) after the patch was cut.

## What was reviewed

- **The implementation.** The finished work is the implementer's patch `scratchpad/wp03.patch`, 30 files. It is byte-identical to `scratchpad/clone` and `scratchpad/w`: I compared every changed file. I applied it to a clean export of HEAD 1ff3102, and `git apply --check` also passes on the current HEAD 6349694, whose commit touches only docs.
- **The repository working tree** (`/home/moiz/arbed/arbx`) holds an older, partial state. 13 files differ from the patch: see finding 1.
- **Build and tests.** I ran them myself on a copy of the patched tree (`CARGO_TARGET_DIR` on tmpfs, `CARGO_BUILD_JOBS=8`):
  - `cargo build --release` passes with 3 warnings, all present at HEAD: the `Check` dead fields and two irrefutable `if let` in `nonces`.
  - `cargo test --release`: **178 passed, 0 failed, 2 ignored**. That is lib 155 (+1 ignored), bin 9, legacy_fixtures 4, meta_config_hash 1, runtime_isolation 2 (+1 ignored), stop_path 6, supervisor 1.
  - `arbx check` exits 0 on `deploy/arbx-stage0.toml` and on `deploy/arb.toml`. Both print the `haan-grpc` tx stream (max 1), the state stream's options and `[leaders]`.
  - The repository working tree, run the same way: **2 tests fail**, `feeds::tests::grpc_stream_fixture_through_forward` (no `testdata/grpc/stream.bin`) and `tx::tests::to_wire_round_trips`. 150 lib tests pass.
- **Vendored proto.** I fetched `yellowstone-grpc-proto/proto/{geyser,solana-storage}.proto` from upstream master. Their sha256 values equal the vendored files' (`56244cb0…`, `e5d16ba9…`) and the README's.
- **Scratch experiments** (in `scratchpad/rev03/exp`, module `rec::journal::review_scratch`; nothing in the repository):
  1. `run_then_replay_dlmm_drift` drives the real `Engine::run` loop, then replays its journal (finding 2). It **fails**.
  2. `accounts_keyframes_marks_and_rotation` writes 2,000 updates with `accounts_keyframe_every = 8`, length changes and `rotate_mb = 0.05`. Result: 10 files, 278 FULL and 1,722 XOR records, every record's data exact, both MARKs parsed, no gaps. It **passes**: the encoder is right, but the repository has no test of it (finding 11).

## Verdict

**Not ready to commit.** There are two blockers:
1. The repository working tree is not the reviewed implementation, and its tests fail.
2. The input journal of a real `arbx run` does not replay to the run's state or decisions. Several initial engine inputs are never journaled, and recordings made with this build can never be replayed exactly.

Everything else is sound:
- recording off the hot path, accounts.bin and journal.bin formats, exec v2, proto pinning, configs, the LeaderBook and the probe;
- no change can send a transaction (the only send-path change is a read-only hook in `send/jito.rs`);
- nothing silently drops recording beyond the nits listed.

## Acceptance checklist (PLAN WP-03)

| Item | Status | Notes |
|---|---|---|
| 1 Account updates (`write_version`, `is_startup`, `src`, `aseq`; `Arc<[u8]>`; every update incl. stale to accounts.bin; verdict in journal) | Met | `feeds/mod.rs::forward`, `rec/accounts.rs` (aseq + queue under one lock), `Engine::step` verdict via `Store::is_stale` |
| 2 Extra watched accounts (Clock, every DLMM bitmap-ext PDA, programdata of route + venues, wallet + token accounts) | Met | `Registry::extra_watch`. DLMM `extra[0]` is always the PDA (exists or not). Token accounts are derived ATAs (deviation 7). Programdata is left out of the boot snapshot (deviation 8) |
| 3 `[[state.tx_stream]]` (PumpSwap, failed incl., idx, `@watched_writable` / `@venue_programs`, `max_accounts`) | Met | `failed = true` → `None`, as at HEAD; the feed id stays 9 |
| 4 Full meta, tags pinned against vendored proto | Met | 120+ tags; the fixture is encoded from the proto text. `bank_id` is not parsed (finding 12) |
| 5 `arbx grpc-probe` | Met (offline) | The plan's subscriptions; the fake server refuses `blocks_meta`. Addendum I-3 behaviour is not handled (finding 4) |
| 6 Block meta (`auto` from probe), blocks.jsonl, `Event::BlockMeta` | Met | Fails closed: no probe file → off |
| 7 Slots: interslot, all statuses, parent, dead_error → slots.jsonl, engine | Met | Not probe-gated (finding 5) |
| 8 Provider lag → feedhealth | Met | |
| 9 exec.jsonl v2 writer in `src/rec/exec.rs` | Met | Built on the chain writer. Queue byte cap not applied (finding 8) |
| 10 Basic LeaderBook (400-slot windows every 100 slots on rt_bg; three named kind sources; `leader` / `kind` / `snapshot`) | Met, with deviation | Bundle results count as `jito`, and BAM comes from the API's `running_bam` (deviation 6; reasonable). MEASUREMENT §4.27 table text still says `bundle_result` is "used for BAM" (N10) |
| 11 Input journal (`step` / `timers`, one clock read per input, INPUT records for outside inputs, ACCOUNT by aseq) | **Not met for real runs** | Findings 2 and 3 |
| Offline: prost round trips + field numbers | Met | |
| Offline: synthetic stream fixture through `forward` | Met | |
| Offline: journal determinism (same journal twice → same digest/decisions) | Met as worded | It holds only for a `new_offline` harness driven by `step` / `timers`. A journal written by `Engine::run` does not replay (finding 2) |
| Offline: LeaderBook with fake RPC | Met | |
| Offline: probe vs fake server refusing `blocks_meta` | Met | |
| DoD: build, tests, no new warnings, configs parse, MEASUREMENT bumped | Met on the patch; **not on the repo tree** | Finding 1. MEASUREMENT is at 2.3; the journal schema minor version is not bumped (N1) |

## Findings

Severity: **Blocker**: fix before commit. **Major**: fix before the owner's field run or the dependent WP; most are cheap enough to fix now. **Minor**: fix soon; the WP still delivers. **Nit**: polish.

### 1. Blocker (process): the repository working tree is not the reviewed implementation, and its tests fail

- **Location:** `/home/moiz/arbed/arbx` working tree.
- **Problem:** these 13 files differ from the patch: `deploy/arb.toml`, `deploy/arbx-stage0.toml`, `docs/MEASUREMENT.md`, `src/config.rs`, `src/engine.rs`, `src/feeds/mod.rs`, `src/main.rs`, `src/rec/health.rs`, `src/send/jito.rs`, `src/tx.rs`, `src/leaders.rs`, `src/rec/journal.rs`, and `testdata/grpc/stream.bin`, which is missing. An untracked `tools/__pycache__/` is also present.
- **Proof:**
  - `cargo test --release` on a copy of the tree gives `test result: FAILED. 150 passed; 2 failed` (`grpc_stream_fixture_through_forward`, `to_wire_round_trips`).
  - The `/home` quota cleared at about 16:15: writes succeed again.
- **Fix:**
  1. `git checkout` those files (or start from HEAD), then `git apply scratchpad/wp03.patch`. It applies to 6349694.
  2. Re-run build and tests.
  3. When committing, add only the WP's files: the 18 modified, plus `src/{leaders,probe}.rs`, `src/rec/{accounts,exec,journal}.rs`, `src/feeds/fixture.rs`, `data/validators-meta.json` (the stage-0 static fallback needs it), `testdata/grpc/stream.bin` and `testdata/proto/**`. Never add `tools/__pycache__/`.

### 2. Blocker: a journal written by `arbx run` does not replay to the run

- **Location:**
  - `engine.rs:482-483` (`run`: `t0 = now_ns()`; `last_status_t` / `last_drift_t` / `last_hk_t` = t0);
  - `engine.rs:279-280` (`new_offline` hard-codes `min_tip = 0`);
  - `engine.rs:306` (`build` loads `cfg.signer_stats_file`);
  - `engine.rs:1206` (`best_cycle` fee includes `self.min_tip`);
  - `main.rs:1125` (`min_tip` = the smallest `tip_lamports` among enabled send paths).
- **Problem:** the WP's goal is "journal the engine's inputs so that runs replay deterministically", and MEASUREMENT §4.13 adds "Only recordings made from WP-03 on are replayable", so WP-04's replay acceptance will use these recordings. Three engine inputs that change decisions are not in the journal:
  - **(a) The timer anchors.** `run` sets the housekeeping, DLMM-drift (2 s) and status (10 s) anchors from an unjournaled clock read. A replay engine starts them at 0. Its first TIMER therefore runs `follow_dlmm`, housekeeping and the status line at journal positions where the live run did not, and the 2 s drift cadence stays out of phase for the rest of the replay. `store.dlmm_arrays` (DLMM quotes, the digest) then differs.
  - **(b) `min_tip`.** For stage 0 it is 1,000 (`jito-bundle` `tip_lamports`, shown by `arbx check`). A replay through `new_offline` uses 0, so every opportunity's `net` differs by 1,000 lamports. That `net` is folded into `decision_digest`, and opportunities near `min_profit_lamports` flip.
  - **(c) The initial signer statistics.** `skip_failing_signers = true` and `signer_stats_file = /root/arbx/runs/signer-stats.json` in stage 0. The file is cross-run, rewritten every 10 s, and shared across bots (addendum I-5). Its boot content is not journaled or copied into the segment (meta.json holds only its sha256), so the trigger-skip decisions of a recording can never be reconstructed.
- **Why the test passed:** the acceptance test drives `step` / `timers` directly on a `new_offline` engine with `min_tip` 0 and no stats file. The "both equal the original run's" claim holds only in that harness.
- **Proof:** the scratch test `run_then_replay_dlmm_drift` has one DLMM pool. Its active bin moves out of the held arrays, `Engine::run` runs for 300 ms, and the run's journal is replayed into `new_offline`. Output:

  ```
  REVIEW timers=59 live first array idx=-3 replay first array idx=1425 digests equal=false
  assertion `left == right` failed: run vs replay
  ```

  (b) and (c) follow from the code: the lines cited above.
- **Fix:**
  - (a) Initialize the anchors from journaled time: in `timers`/`step`, `if self.last_hk_t == 0 { set all three to t }`. Alternatively, journal a TIMER at `run` start and let replay do the same.
  - (b, c) Write an engine-init record before the first input. That can be an INPUT kind (e.g. 10 `engine_init`) or journal-header fields, carrying `min_tip`, the strategy config hash, and the signer statistics as loaded: their content, or the per-segment copy plus sha256 that I-5 asks for.
  - Make `new_offline` (or `journal::replay`) take these values instead of reading `cfg.signer_stats_file`.
  - Add a regression test like the scratch one: real `run` over a channel, with a DLMM pool, `min_tip` ≠ 0 and a stats file; replay; assert equal `digest()` and `decision_digest()`.

### 3. Major: SendGate changes are sampled every 100 ms, while send checks read the live gate

- **Location:** `main.rs:994-1003` (watcher on `rt_bg`); `exec.rs:759` (`wants_send` reads `self.gate.allows()` directly).
- **Problem:** PLAN item 11 and §4.13 say outside inputs that change send-check decisions "reach the engine as events … and are journaled as INPUT".
  - In the patch, the decision reads the live atomic, and a separate task posts a sampled copy.
  - The journal position of a gate change is therefore not where the decisions saw it. A change and its revert within 100 ms (a pause/resume, or a short shadow) never reach the journal.
  - `decision_digest` folds `wants_send().is_some()` (`engine.rs` `after_opportunity`), so a WP-05/WP-09 replay of send checks around a gate change cannot match.
- **Fix:** keep the live read: failing closed at once is the right safety trade-off. Also journal what the decision observed, on the engine thread at the decision point: an INPUT `gate` whenever the mode or reason seen in `after_opportunity` differs from the last one journaled, or the observed mode folded into the decision record. The watcher can stay for status. If this is deferred to WP-05, record that in the merge note and in §4.13.

### 4. Major: the probe misreports when another process holds the provider, and can blind a live segment (addendum I-2 and I-3)

- **Location:** `probe.rs:81-112` (`run_sub`), `:141-148` (accepted/refused), `:172-175` (`accepted`); `main.rs` `grpc_probe`.
- **Problem:** addendum I-3 says Haan grants its streams to the first process only, and the other one gets 503. I-2 and I-3 ask that "the WP-03 gRPC probe records 503s per stream, separately from other errors". The patch predates the addendum, but the current plan requires it:
  - **(i)** A probe run while a campaign segment holds Haan reports every subscription `accepted: false` with an `Unavailable` text. `probe.json`, its dated copy for `docs/` and §9 then record "refused" for capabilities the provider may well have, and OD-1 is decided on that.
  - **(ii)** A probe started first holds the provider for about 4 min (8 subscriptions × 30 s, one after another). A live segment reconnecting in that window gets 503 and runs blind (I-4; no state gate until WP-04). Nothing enforces "run it while no segment uses the provider".
  - **(iii)** `accepted()` treats "stream stayed open, 0 messages" as accepted, so `block_meta = "auto"` can turn on a subscription that delivers nothing.
- **Fix:**
  - Classify `Unavailable` / HTTP 503 (and resource-exhausted) as `inconclusive`: `accepted: null`, with `code` and `http_status` fields. Treat it as off for `auto`, and make the CLI exit non-zero with a message.
  - Refuse to run while a segment's control socket or pid file exists, unless `--force`.
  - Require `messages_30s > 0` for `auto`.

### 5. Minor: `slot_statuses = "all"` is not probe-gated, yet it shares the one state-stream subscription

- **Location:** `config.rs` (`slot_statuses_all` default), `main.rs:919-924`, `grpc.rs::state_request`.
- **Problem:** the accounts filter, the slots filter (with `interslot_updates`) and optionally `blocks_meta` go in one `SubscribeRequest`. A provider that refuses interslot updates (a risk named in PLAN WP-03 "Risk") would refuse the whole state stream. The bot would reconnect forever with no pool updates; it cannot lose funds, but the segment is useless. `block_meta` got `auto`; the slot statuses did not, and the probe has not run yet.
- **Fix:** default `slot_statuses = "auto"` (`all` when the probe accepted `slots_interslot` on this host, else `commitment`). Or, on a subscribe error, fall back to `commitment` with an `events.jsonl` entry.

### 6. Minor: existing gauges silently changed meaning

- **Location:** `feeds/mod.rs:365` (`c.seen(slot, t)` for every slot status); `engine.rs:1258` (`store_slot_max` from any stored account); `engine.rs:736` (`tip_lag_slots_now`); `rec/health.rs:191-205`.
- **Problem:**
  - With interslot statuses, the state feed's `slot_max_now` follows `first_shred` / `created_bank` slots, which run ahead of processed ones. Its `slot_lag_now` becomes negative or biased.
  - The Clock sysvar is now stored and updates every slot. `store_slot_max`, and so status `tip_lag_slots_now`, therefore tracks the Clock instead of pool-state staleness, the thing it was read for at HEAD (cmp2 / I-4 diagnosis).
  - MEASUREMENT §4.8 and §4.9 do not say so.
- **Fix:** call `seen` for statuses 0-2 only (keep a separate interslot maximum if wanted), and update `store_slot_max` only for pool-role accounts (`acct_pool` hit). Otherwise, document the new meaning and add a pool-only gauge.

### 7. Minor: housekeeping now runs between events under load, and the 10 s forced flush can price a torn transaction

- **Location:** `engine.rs:510-516` (the post-event `timers` call), `:551-556` (`timers`).
- **Problem:**
  - **(a) Housekeeping.** At HEAD it ran on idle 5 ms wake-ups, and every 10 s while busy. Now it also runs after a state flush whenever 5 ms have passed: up to about 200/s under load, between two events. Each run walks `opps`, collects `trig_pending`, retains `checks` and `preds`, and prunes `sigs`. The engine benchmark calls `flush_state` directly and never measures this added queueing delay.
  - **(b) Forced flush.** Deviation 5 flushes `state_pending` every 10 s even while the queue is non-empty. HEAD never flushed with a non-empty queue, because "queue empty" is the only completeness signal until WP-04. The flush can price a transaction whose other account updates are still queued (defect #2). That costs nothing on a reverted bundle, but it is a decision on a torn state.
- **Fix:**
  - (a) Run housekeeping only from idle wake-ups and the 10 s tick, as at HEAD. Either rule is deterministic now that TIMER is journaled.
  - (b) Keep HEAD's flush rule, and let the 10 s call do housekeeping and status only.
  - Add a burst benchmark of event-to-event delay.

### 8. Minor: exec.jsonl records bypass the chain queue's byte cap

- **Location:** `rec/exec.rs:21-27` (`rec.emit(EXEC, Record::enc(...))` moves the whole `PbTransaction` + `PbMeta`, logs and inner instructions included, into the closure).
- **Problem:** HEAD queued about 300 bytes of JSON per transaction. Now each queued exec record holds several KB, but declares no size, so `queue_max_mb` never counts it. A slow chain writer can hold up to 262,144 × several KB.
- **Fix:** use `emit_sized(EXEC, tx.encoded_len() + meta.encoded_len(), …)`.

### 9. Minor: the `settled` INPUT is lossy

- **Location:** `engine.rs:541-542`.
- **Problem:** the record keeps `{attempt, error, landed: {path, sig, slot}, jito}` and drops `fired`, `nonce_value` and the landed transaction (`exec.rs` `Settled`). WP-05/WP-09 cannot replay executor state from it, and the reason given is that "its replay is WP-05 / WP-09's".
- **Fix:** journal the full struct (base64 of the landed transaction), or state in §4.13 that kind 9 is a summary that WP-05 must replace.

### 10. Minor: exec.jsonl is not deduplicated by signature

- **Location:** `feeds/grpc.rs::tx_stream_item`.
- **Problem:** §4.14 says "One line is written per signature". The transaction stream at processed commitment can deliver one signature twice: on two forks, or around a reconnect. Each delivery becomes a line.
- **Fix:** a bounded recent-signature set in the tx-stream task (or on the chain writer), or document that readers must deduplicate by `(sig, slot)`.

### 11. Minor: test gaps

- No test drives `Engine::run`. That is how finding 2 got through.
- `rec/accounts.rs` has no tests of its own. The keyframe interval, length-change FULL, file rotation (dictionary restart), MARK parsing and GAP-after-drop are unexercised. My scratch test shows that they work, so adopt it.
- `exec_json` has untested branches: `why` (the removed v1 test covered it), the default-limit `priority_fee`, the v1 `config` path, `nonce`, the writability of loaded-readonly keys, and `err_ix` other than ix2.
- Also untested: the gate watcher, the `leaders::start` loop (list refresh, `leaders_list_stale`, window due), and `MARK stream_reconnect` / `watch_list_changed`.

### 12. Minor (owner decision): `bank_id` is neither parsed nor recorded

- **Location:** `feeds/grpc.rs` structs; accounts.bin, journal SLOT, slots.jsonl, blocks.jsonl.
- **Problem:** the vendored upstream proto (Alpenglow era) has `bank_id` on `SubscribeUpdateAccount` (4), `SubscribeUpdateSlot` (5), `SubscribeUpdateTransaction` (3) and `SubscribeUpdateBlockMeta` (10). It also has `SubscribeUpdateEntryUpdateParent` / `DeshredUpdateParent`, which invalidate a bank of a slot. A slot's bank can therefore be replaced, and `bank_id` is the identifier WP-04's fork handling would join on. The plan did not ask for it, but recordings made now will not have it.
- **Fix:** parse the optional `bank_id` into `Item` / `Event`, and record it with a minor schema bump: accounts.bin flags bit 2 plus a u64, journal SLOT and BLOCK_META, slots.jsonl, blocks.jsonl. Or record the owner's decision not to.

### Nits

- **N1.** The journal format was extended inside `arbx.journal/2.0`: the TX_COPY PoH tail, a repeated TX_FIRST for a copy with loaded addresses, and INPUT 9.
  - The §4.13 byte table still shows the old TX_COPY.
  - `tools/arbx-report/arbx_report/streams.py:471` (`INPUT_KINDS`) has no 9.
  - A reader that counts TX_FIRST as unique transactions now double-counts.
  - Bump to 2.1 and update the table, or say so in the table itself.
- **N2.** `on_event` still evaluates `expire_confirms` (`engine.rs:584`). §4.13 says timeouts are evaluated only in `timers`. It is deterministic (it uses `t_now`), but it contradicts the contract text.
- **N3.** `Journal::input` clones the INPUT `Value` on the engine thread: about 400 strings per leader window, every ~40 s. `on_event` ignores the data, so move it instead of cloning.
- **N4.** A journal GAP record carries the writer's wall clock as `t_engine_ns` (`rec/writer.rs` `gap_record`). A GAP among the boot records ends `boot_store`'s `take_while(t_engine == 0)` (`journal.rs:317`), and the remaining boot records are then replayed as events.
- **N5.** The `decision_digest` "exec" fold hashes only the opportunity id and two booleans, not the route handed to the executor, although §4.13 says "every route handed to the executor".
- **N6.** `state_item` drops a block meta whose blockhash does not decode, without a count or event (`grpc.rs:328`, `hash32(..)?`).
- **N7.** `block_meta = "auto"` uses a probe file of any age. Record the probe's age in meta.json and consider a maximum age.
- **N8.** `[[feed]] max_accounts` is enforced only in `expand_includes` at run time, after boot and after the state stream has started. Literal lists could be checked at config load, as `[[state.tx_stream]]` lists are.
- **N9.** leaders.jsonl writes no "kind updates" (§4.27 "plus kind updates"). A list refresh that changes a validator's kind is visible only in `events.jsonl`. The WP-03 note says so; the table text does not.
- **N10.** The MEASUREMENT §4.27 `kind_src` row still says `bundle_result` is "used for BAM". The implementation, and the WP-03 note below the table, make it `jito`. PLAN item 10 says the same as the old text. Align the plan and table text with deviation 6.

## Checked and found correct

- **Formats.** accounts.bin records and MARKs match §4.12 byte for byte, and the journal framing matches §4.13. The toolkit readers (`streams.py` `_parse_journal_body`, the accounts reader) accept the extensions: they ignore the TX_COPY tail.
- **aseq ordering.** `aseq` is taken and the record queued under one mutex, so concurrent producers (the state stream task, `fetch_accounts` on `rt_bg`, the boot) keep the file in aseq order. The boot and engine journal handles share `Rec::next_seq`, so `seq` is continuous.
- **Hot path.** XOR, xxh3, protobuf encoding and exec JSON all run on writer threads. Account data is one `Arc<[u8]>` shared by the store and the record. Raw bytes are copied on feed threads only.
- **Stale updates.** Stale updates are recorded, and the journal verdict uses the same predicate as `Store::update` (`is_stale`).
- **Transaction streams.** `[[state.tx_stream]]` → feed: `failed = true` maps to `None` (failed included, as at HEAD). `url` and token default to the state stream's, and `split_include` is false, as before. `haan-grpc` was the last `[[feed]]` in both maintained configs, so its id stays 9; the config test asserts this for stage 0. A name clash with a `[[feed]]` is refused.
- **Wallet accounts.** The wallet ATAs use each mint's token program (Token-2022 included).
- **Safety.** No change can send a transaction:
  - the send paths are unchanged except for the `jito.rs` hook, which only reads results;
  - the probe opens subscriptions only;
  - the LeaderBook and the gate watcher only read.

  `block_meta` is off unless the probe for this host accepted it.
- **Probe output.** probe.json contains no token or URL key (the test asserts it). The CLI exits with an error on bad `--seconds`, and `--only` works.

## Disposition (2026-10-04, WP-03 fix pass)

The working tree was reset to the reviewed patch (`scratchpad/wp03.patch` applied on 6349694; the older partial tree is kept in `git stash` "WP-03 pre-fix working tree"), then every blocker and major and the minors and nits below were fixed. Build and tests on the result: `cargo build --release` passes with the 3 warnings already at HEAD; `cargo test --release`: **191 passed, 0 failed, 2 ignored** (lib 168 + 1 ignored, bin 9, legacy_fixtures 4, meta_config_hash 1, runtime_isolation 2 + 1 ignored, stop_path 6, supervisor 1; the lib suite run 3 more times, stable); the toolkit's `python3 -m unittest` 78 OK (4 skipped); `arbx check` exits 0 on both maintained configs.

| # | Disposition | What was done | Tests |
|---|---|---|---|
| 1 | Fixed | The patch landed byte-identical to the clone; the commit adds only the WP's files: the 18 modified, `src/{leaders,probe}.rs`, `src/rec/{accounts,exec,journal}.rs`, `src/feeds/fixture.rs`, `data/validators-meta.json`, `testdata/grpc/stream.bin`, `testdata/proto/**`, plus the files this pass touched (`src/exec.rs`, `src/control.rs`, `tools/arbx-report/arbx_report/streams.py`, its `tests/test_streams.py`) and this review. `tools/__pycache__/` is not added | the two failing tests pass |
| 2 | Fixed | (a) The timer anchors start at the first journaled input's or timer's time (`Engine::anchor`, called by `step` and `timers_at`); `run` no longer reads the clock for them. (b, c) `run` first journals INPUT 10 `engine_init` (`t_engine_ns` 0, after the boot records): `min_tip`, `strategy_sha256`, `executor`, `signer_stats_file` and the signer statistics **as loaded**. `journal::replay_engine` builds a replay's engine from it (boot store, `new_offline`, `apply_init`; refused without the record or when the replay's `[strategy]` is not the run's). `new_offline` never reads or writes the statistics file: a replay given the run's config would otherwise have rewritten the live cross-run file (`Rec::off().task` runs inline; found in this pass) | `a_journal_written_by_run_replays_to_the_run`: the real `Engine::run` (built with `Engine::new`, `min_tip` 1,000, a statistics file, state triggers, the reviewer's DLMM case) replays to equal state digest, decision digest and DLMM arrays; it fails with the old anchoring (live idx -3, replay 1425, as in the review); a plain `new_offline` replay differs in both digests; a changed `[strategy]` is refused. `a_journal_replays_deterministically` now goes through `replay_engine` |
| 3 | Fixed | The send check still reads the live gate (closes at once), once (`Exec::wants_send` keeps the mode it read, `gate_seen`). The engine journals it at the decision, on its own thread: INPUT `gate` with `src` "decision", the observed `mode` and the opportunity id `opp`, whenever the mode differs from the last one journaled; the mode is also folded into `decision_digest`. The 100 ms watcher stays, tagged `src` "watch" (status and coverage). Replay skips decision records (counted `gate_observed`); a WP-05 / WP-09 replay applies them at opportunity `opp` | `the_gate_each_send_check_saw_is_journaled` (live, paused, still paused: two records, opp 0 live and opp 1 shadow, right after the timer that made the decisions; the live gate decided) |
| 4 | Fixed | (i) Unavailable (HTTP 429/502/503/504), ResourceExhausted, DeadlineExceeded, Aborted, Cancelled, and no gRPC answer at all are `inconclusive`: `accepted` null, `verdict`, `code`, `http_status`. With any inconclusive result `arbx grpc-probe` writes only `probe-<stamp>-inconclusive.json`, leaves probe.json as it was and exits 3. (ii) It refuses to start while a live segment's control socket exists under `<out_dir>` (depth 1-2; a stale socket file is not live: `control::socket_alive`), `<out_dir>/.supervisor.lock` is held, or an `arbx … run` / `arb-lab … run` process runs on the host, unless `--force`; it holds the supervisor's lock while it runs, so `deploy/run-w.sh` does not start a campaign meanwhile. (iii) `probe::accepted` is true only for an accepted stream with `messages_30s` > 0. meta.json `probe` gains `inconclusive` and `age_s` | `a_busy_provider_is_inconclusive_and_a_silent_stream_is_not_auto` (fake server: Unavailable, bare HTTP 503, open-but-silent), `busy_finds_live_segments_and_bot_processes` (command lines, live vs stale socket, the lock) |
| 5 | Fixed | `[state] slot_statuses` defaults to `"auto"` (`all` only where the probe accepted `slots_interslot` with messages on this host, else `commitment`); both maintained configs say `auto`; meta.json and run.log show the effective value | config test |
| 6 | Fixed | The state stream's `slot_max_now` moves on commitment statuses (and accounts) only; `store_slot_max` (status `tip_lag_slots_now`) follows pool accounts only; MEASUREMENT §4.8 / §4.9 say so | `interslot_statuses_do_not_move_the_feeds_newest_slot`, `store_slot_max_follows_pool_accounts_only` |
| 7 | Fixed | arb-lab's rules restored and made explicit in the journal: TIMER carries `what` (1 flush, 2 housekeeping). Idle wake-ups do both; after an input, only the flush, and only on an empty queue with pending state triggers; every 10 s while the queue never empties, housekeeping only (flush only if the queue is empty then). No flush ever prices a transaction whose updates are still queued | `after_an_input_the_timers_keep_arb_labs_rules` (the rule table), `a_burst_runs_no_timer_until_the_queue_empties` (6,000 queued updates through `run`: no TIMER before the last). **Deviation:** structural tests instead of a timing benchmark of event-to-event delay |
| 8 | Fixed | `emit_grpc` uses `emit_sized` with the protobuf transaction's and meta's encoded size | (accounting only) |
| 9 | Fixed | INPUT 9 now holds the whole settlement: `{attempt, error, fired, landed: {path, sig, slot, tx}, jito, nonce_value}` | (serialization of existing types) |
| 10 | Fixed | One exec.jsonl line per **(signature, slot)** per transaction stream (`rec::exec::Recent`, kept across reconnects, last 200,000 pairs): a re-delivery is dropped, a second fork kept; §4.14 says so | `recent_keeps_one_line_per_signature_and_slot` |
| 11 | Mostly fixed | Added: a test that drives `Engine::run` (#2), the accounts.bin keyframe / length-change / rotation / MARK test (the reviewer's, adopted with stricter asserts), `exec_json_branches` (`why`, default-limit `priority_fee`, v1 `config`, `nonce`, loaded-readonly writability, `err_ix` other than 2), the gate (#3), the timer rules (#7). **Open:** the 100 ms gate watcher (now status only), the `leaders::start` loop, and the code paths that emit `MARK stream_reconnect` / `watch_list_changed` | listed |
| 12 | Partly fixed (owner decision kept open) | `bank_id` is parsed and its tags pinned against the vendored proto for `SubscribeUpdateAccount` (4), `SubscribeUpdateSlot` (5), `SubscribeUpdateTransaction` (3), `SubscribeUpdateBlockMeta` (10), and recorded in slots.jsonl, blocks.jsonl and exec.jsonl (null when not sent). **Not** in accounts.bin or the journal: that is a format change WP-04's fork handling should make | `field_numbers_match_the_vendored_proto`, `bank_id_reaches_the_items` |
| N1 | Fixed | Journal schema `arbx.journal/2.1`; §4.13 table shows the TX_COPY PoH tail, INPUT 9 and 10, TIMER `what`, and that TX_FIRST repeats for a copy with loaded addresses; the toolkit names INPUT 9 / 10 and reads TIMER `what` and the TX_COPY tail | toolkit `test_journal_2_1_fields` |
| N2 | Documented | §4.13 states the exception: expired confirmation waits are also checked at the end of each input, at its `t_engine_ns` (deterministic, as at HEAD) | |
| N3 | Fixed | `Event::Input` data is an `Arc<Value>`; the journal shares it and serializes it on the writer | |
| N4 | Fixed | The boot section is the leading `t_engine_ns` 0 records with GAPs allowed among them; replay reports every GAP | `a_gap_among_the_boot_records_keeps_the_boot_section` |
| N5 | Fixed | The route handed to `send` / `simulate` (size, pools, expected return) is folded into `decision_digest` | |
| N6 | Fixed | A block meta whose blockhash does not decode is counted in the state stream's feedhealth `errors_total` | `bank_id_reaches_the_items` (undecodable case) |
| N7 | Partly | meta.json `probe.age_s`; no maximum age is enforced (owner's call) | |
| N8 | Fixed | A `[[feed]]`'s literal `account_include` is checked against `max_accounts` at config load | config test |
| N9, N10 | Fixed in MEASUREMENT | §4.27 producer line (no kind updates in WP-03) and `kind_src` (`bundle_result` → `jito`). PLAN item 10's wording is left for the plan owner | |

**Assumptions.** Open owner decisions keep PLAN §9's defaults (OD-1: one PumpSwap transaction filter). No recording in the 2.0 journal format exists, so the minor bump changes no reader's data. The probe is meant to run on the Stage-0 host with nothing else using Haan; a lone `arbx run` started while a probe runs is not blocked (only campaigns are, through the lock).

**Open for later WPs.**
- WP-04: `bank_id` in accounts.bin and the journal (with the fork tree); addendum I-5 (per-segment statistics copy, misses only while state is healthy); its replay acceptance uses `journal::replay_engine` on a recording made with this build.
- WP-05 / WP-09: the executor's replay: decision-point gate records by `opp`, the full INPUT 9, and the send / sim routes now in `decision_digest`. Until then a run with an executor replays exactly only in its engine part. STATUS records are not replayed (their `expire_confirms` matters only with an executor).
- WP-08: leaders.jsonl kind updates and tests of the `leaders::start` loop; PLAN item 10's text.
- Owner: run `arbx grpc-probe --config deploy/arbx-stage0.toml` on the Stage-0 host with no segment running and record it in PLAN §9 (OD-1). Until a conclusive probe exists, `block_meta` and interslot slot statuses stay off (`auto`).

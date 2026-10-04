# WP-04 review: state consistency, forks, accuracy monitor (and addendum I-4, I-5, I-6, I-8)

**Date:** 2026-10-04. **Reviewer:** adversarial review, read-only (no repository code changed; probes ran in a scratch copy).
**Plan:** `docs/PLAN.md` WP-04 (items 1-13, config keys, offline acceptance, definition of done), `docs/PLAN-ADDENDUM.md` I-4, I-5, I-6, I-8 (required for WP-04), the WP-03 hand-offs (commit ab4e6ee body), `docs/MEASUREMENT.md` §4.12, §4.13, §4.26, §4.30-§4.34, §5, A.1, and `docs/research/cmp2-shadow-comparison.md`.

## What was reviewed

- **The implementation** is the uncommitted WP-04 diff on 9bfd72d (19 modified files, +3,696/−1,041, and 5 new modules). I saved it at the start (`git diff` sha256 `115ca61e…`, new files sha256 `b0d649f1…`).
- **HEAD moved during the review.** Two commits landed (author `moiz`):
  - d5c8d67 (19:26) deletes the bait keystore and its test (`wallet::decrypts_arbeds_keystore`).
  - 6f8fd3c "post" (19:31) commits the WP-04 files. Its diff against d5c8d67 has the same sha256 as my snapshot (`115ca61e…` / `b0d649f1…`). **The code reviewed here is exactly 6f8fd3c.** See process note P1.
- **Build and tests.** I ran both myself in the main tree (its own `target`, `CARGO_BUILD_JOBS=5`):
  - `cargo build --release` passes with 2 warnings, both pre-existing (`main.rs:414`, `:422`, irrefutable `if let`). There are no new warnings.
  - On the reviewed tree, `cargo test --release` gives **227 passed, 0 failed, 2 ignored**: lib 203 (+1 ignored), bin 10, legacy_fixtures 4, meta_config_hash 1, runtime_isolation 2 (+1 ignored), stop_path 6, supervisor 1. This matches the report.
  - At 6f8fd3c (after d5c8d67) the lib count is **202** (+1 ignored), 226 passed in all.
  - Toolkit (`tools/arbx-report/tests`): 79 tests OK, 4 skipped.
  - `arbx check` exits 0 on `deploy/arbx-stage0.toml` and on `deploy/arb.toml`, and prints the WP-04 lines.
- **Stress.**
  - The two replay tests (`a_wp04_run_replays_to_the_run`, `a_journal_written_by_run_replays_to_the_run`) passed 15 of 15 times.
  - The WP-04 module tests (engine, commit, forks, alts, store, store_health, journal, accuracy, feeds: 61 tests) passed in four concurrent runs, the engine benchmark included.
- **Probes.** Six tests were added to a scratch copy of the crate (`scratchpad/e2/wp04-review/crate`, appended to `engine.rs`'s test module; code in the appendix), plus one integration benchmark. All six pass, which means each demonstrates its defect. The outputs are quoted in the findings.

## Verdict

**Not ready to merge as the Stage-0 state gate.** One blocker and three majors:
1. **Blocker (I-4).** After a state-stream reconnect, and at boot, the engine prices again and opens the send gate before the re-snapshot has landed. A failed re-read chunk is dropped without a trace.
2. **Major.** A fork rollback can restore a pre-fork version instead of the canonical one (the late-leader fork).
3. **Major.** Versions from a fork already known to be abandoned are still priced. In one case they are never dropped.
4. **Major (hot path).** `save_signer_stats` now builds the whole signer map's JSON on the engine thread: about 25 ms every 10 s with the real 30,304-signer file.

The core of the WP is sound:
- **I-8.** Poisoning is structurally impossible. Pricing reads only the store. In a run, the only writers of the store are account events (stream and RPC re-reads), fork drops and the boot snapshot; `simcheck`'s RPC refresh is a tool. Hints and their at-hint predictions are never read by pricing. `hints_never_change_a_decision` and the cmp2 poisoning test show it.
- **Commit groups, readiness, the warm-up gate, the boot timeout, I-5 and I-6** are correct and well tested.
- **Replay** reproduces a run written by `Engine::run`.

## Acceptance checklist (PLAN WP-04, addendum items, hand-offs)

| Item | Status | Notes |
|---|---|---|
| 1 Committed state only (`preds`, confirm path, flush, `decoded_sends` / `confirm_trigger_ms` gone; hints register W(T), write triggers.jsonl, feed accuracy) | **Met** | No residue (grep). Old keys rejected by `deny_unknown_fields` (`wp04_keys`) |
| 2 Store versions `(slot, write_version)`, 8-version ring | Met | RPC reads order after a slot's stream records, by aseq. The ordering is not fork-aware (finding 2) |
| 3 CommitTracker (known / unknown W, superseding, timeouts, quiescence, late members, commits.jsonl with `w_src`, lag) | Met | `commit.rs` is careful (stream evidence, deterministic order). `quiescence_ms = 3` is a placeholder (owner measurement) |
| 4 Route readiness (consistency sets, other parts, skew ≤ 2 within a pool only, lag rule, `state_version`) | Met | The lag rule measures the state stream against itself (finding 9) |
| 5 Evaluation on commit, quiescence fallback, route-level quiet | Met | Deferrals capped at 3 (deviation 7, reasonable) |
| 6 Chain clock, `clock_stale` | Met | |
| 7 Lookup-table retry (50/250/1000/5000 ms, then 30 s, give up at 600 s; wait cap; events; alts-final at stop) | Met | Preload volume (finding 11) |
| 8 Warm-up gate, Tier A grace, lag SLO per minute, `slo_action` | **Partly met** | The gate reopens on stale state after a reconnect and at boot (finding 1) |
| 9 Forks (tree, abandonment, rollback, refetch, `fork_pending`, `fork_priced`, SLOT `parent`) | **Partly met** | Findings 2, 3 and 7 |
| 10 Decision records; `RouteIn` gains `state_version`, `route_age_ms`, `decision` | Met | `band` / `net` are taken at sizes past the cap (finding 5) |
| 11 Replay clock | Met | Per thread, guarded, one relaxed load in a run |
| 12 Signer filter | Met | |
| 13 Accuracy monitor (pre-state scoring, `pre_state_unknown`, idle bounded queue, at-hint kept) | Partly met | Only the decoded input is used, never the executed one (deviation 1; finding 12) |
| Offline: store ordering; commit groups; skew rule ±; accuracy; ALT schedule; warm-up gate; no pricing on predictions | Met | |
| Offline: forks (sibling without `dead`, `dead`, slot-index `missing`, `fork_pending`) | Met as worded | Fails the reversed-sibling and late-leader cases (findings 2, 3) |
| Offline: S1, S1b, S8b through `testdata/grpc` + `forward` | **Partly met** | Finding 6 |
| Offline: scenarios S1-S8 (+S1b, S1b′, S4b, S8b) | Engine-level synthetic | S3 and S5 only by analogue. The real-layout files are WP-09's |
| DoD: build, tests, no new warnings, configs parse, MEASUREMENT bumped | Met | Header nit (N1). Six HEAD tests removed with their code, not named in the report (N5) |
| **I-8** price only committed, complete, canonical state; keep the 4.2 SOL cap and the ≥1M throttle | **Met** (poisoning) | The cmp2 test reproduces the pattern: priced on the failed swap's prediction, the route nets +2,306,193,614; on committed state the best route nets −2,264,093. The cap and throttle are unchanged in both configs. The ladder-edge class survives in the records (finding 5) |
| **I-4** boot stop, no pricing while down or stale, `wants_send` hook, re-snapshot after every reconnect, status fields, WARNING, shred-slot fallback | **Partly met: blocker** | Boot stop (60 s → stop.json `state_unavailable`, exit 30, classed a crash by `run-w.sh`), the stale-age gate, the hook, status, WARNING and shred slot all work. The re-snapshot is fire-and-forget (finding 1) |
| **I-5** misses only while healthy, own status when known, boot read with sha256, per-segment copies, explicit merge, offline engines untouched | **Met** | A 3 s silence that no timer saw counts as an outage. `merge` does not check that the segment has ended (N7) |
| **I-6** retry with backoff, concurrency cap, preload of the previous segment's alts-final, alts events | **Met** | Finding 11 (volume) |
| **WP-03 hand-offs:** `bank_id` in accounts.bin and the journal; replay acceptance through `journal::replay_engine` | **Met** (local) | accounts 2.1 (flags bit 2), journal 2.2 SLOT/BLOCK_META. `a_wp04_run_replays_to_the_run` replays a real `Engine::run` journal (forks, health inputs, re-snapshot, ALT retry, preload). The field replay of a Cherry recording is the owner's step |

## Findings

Severity:
- **Blocker:** fix before merge.
- **Major:** fix before the owner's field run or before WP-05 uses the gate.
- **Minor:** fix soon; the WP still delivers.
- **Nit:** polish.

### 1. Blocker (I-4): after a reconnect, and at boot, pricing and the send gate resume before the state is re-read

- **Location:**
  - `engine.rs:998-1024` (`on_health` and `resnapshot`: fire-and-forget);
  - `engine.rs:1028-1082` (`refresh_health`: no resync state);
  - `engine.rs:2365-2381` (`fetch_accounts`: `let Ok((slot, v)) = rpc.accounts(chunk).await else { continue };`);
  - `engine.rs:1018` (re-read keys sorted by pubkey);
  - `main.rs:1034-1078` (the snapshot, then the stream; nothing re-reads after the first connection).
- **Problem.** The stream does not resend writes made while it was down: a pool written during the outage holds its pre-outage version until its next write. The store cannot tell such a pool from an idle one, and item 4 prices idle pools at any age. Three paths lead to it:
  - **(a) The reconnect window.** `on_health(connected = true)` only spawns the re-read. The next slot status and Clock update make the state available, the lag rule passes and Tier A is complete. `Shut` goes to `Ready` and the `HealthFlags` that `Exec::wants_send` reads open, while every account still holds its pre-outage version. Every group that resolves then prices its routes against stale partners.
  - **(b) A failed re-read chunk is dropped silently.** There is no retry, counter, event or WARNING, so those accounts stay stale until their next write. The conditions that cause reconnects are the same ones that fail RPC chunks. cmp2-arbx's run.log, the minute after boot: `rpc haan: first 205/315 (65%), errors 110 … rate limited`, `rpc failure shyft: 41 x … no answer in 3 s`.
  - **(c) The boot gap is never closed** (pre-existing, WP-03 review F1, but WP-04 now has the machinery). The boot snapshot reads 100 keys per call with 120 ms pacing; cmp2 had 4,372 accounts, so about 44 calls and more than 5 s. Every account is labelled with the last chunk's slot. The stream subscribes only afterwards, so writes to early-chunk accounts in that window are never seen. The warm-up gate opens as soon as the Clock arrives.
  - **Side effect of the re-read itself.** The keys are sorted by pubkey and read 100 per call, each call with its own context slot. A pool's consistency set is then split across calls taken slots apart, so idle pools fail the 2-slot skew rule after every reconnect until their next swap. This fails closed, but it is avoidable.
- **Proof** (probe 1, `review_probe_1_reconnect_prices_before_the_resnapshot_lands`):
  - The setup: two AMM v4 pools (A and B), ready; the stream drops; 30 s later it reconnects. One re-read is requested and no answer is applied. Then a slot status, the Clock, and one write to B.
  - Output: `shut after the first messages Ready, wants_send flags ready true`.
  - The decision prices B→A on A's pre-outage version: `"reason":"best"`, `"net":106621773` at `"size":1999955447`, `state_opportunity 1`. With an executor, `wants_send` would have passed the health check.
  - After a real 3-minute Haan outage (I-2) nearly every active pool has moved (31-60 watched tx/s over 300-377 pools). So the window is phantom gaps across the registry, and permanent ones for any account whose chunk failed.
- **Fix:**
  - Add a resync state, say `Shut::Resync` with reason `resync`, entered on `health(connected = true)` after a loss and on the first connection at boot. Leave it only when every chunk of the re-read has been applied. Re-read the boot snapshot's accounts once the stream delivers, to close the gap.
  - Alternatively, mark each account "unverified since the (re)connect" and refuse pools with such a part (reason `resync`). A stream update or the re-read clears the mark.
  - Retry failed chunks with backoff on `rt_bg`. Count them and emit events. Stay shut with a WARNING if the re-read is not done within N s.
  - Group the keys by pool so each consistency set is read in one call.
  - Test: the probe-1 sequence must decide `resync` until the re-read lands, and an injected chunk error must be retried.

### 2. Major: a fork rollback restores the pre-fork version, not the canonical one (the late-leader fork)

- **Location:**
  - `store.rs:216-226` (`apply` refuses any version at a lower slot, whatever the fork);
  - `engine.rs:2165-2208` (`on_abandoned` / `on_dropped`: only accounts left with no version are refetched, `filter(|d| d.2)` at :2183).
- **Problem.** This is the common fork pattern: the leader of slot 12 is late, the leader of 13 builds on 11, and the validator replays 13 first and 12 next. Both write account X.
  - X@13 is applied. The canonical X@12 then arrives with a lower slot and is refused as stale, so it never enters the ring.
  - 12 wins, and 13 is abandoned (later; see finding 3). X@13 is dropped and the ring falls back to its pre-fork version, because the canonical write was never kept.
  - No refetch is issued, because the ring was not empty. X is priced as canonical but is not the chain's state, until X's next write. For an idle pool that can be minutes.
  - This contradicts item 9 ("each affected account falls back to its newest canonical version"). The S8b test passes only because the canonical sibling never wrote the same account.
- **Proof** (probe 6, `review_probe_6_rollback_restores_a_pre_fork_version_not_the_canonical_one`):
  - Output: `slot-12 (canonical) writes refused as stale: 2; 13 abandoned true; A.vault1 now slot 10 = 1000 SOL (chain: 1,050 SOL at slot 12); fork refetches 0`.
- **Fix:**
  - On any rollback, refetch every account that lost a version (`src` `rpc_refetch`, MARK 5), and hold it pending (refuse its pools) until the read lands.
  - Alternatively, make the store fork-aware. Keep a version refused for a lower slot when it is on a different live branch, and on rollback choose the newest version on the surviving branch.
  - Add the probe-6 sequence to the S8b tests.

### 3. Major: versions from a fork already known to be abandoned are priced

- **Location:**
  - `forks.rs:100-119` (`confirm` abandons only slots ≤ S);
  - `forks.rs:140-152` (`recompute_contested` skips confirmed children);
  - `forks.rs:91-97` (`abandon_with` returns early for a slot already abandoned, so no second `Abandoned` is produced);
  - `engine.rs:1860-1868` (`on_account` applies versions of abandoned slots).
- **Problem:**
  - **(a) A confirmed slot's higher-numbered sibling.** Take siblings 12 and 13 of slot 11. While both are unconfirmed they are contested, so `fork_pending` applies correctly. When 12 is confirmed, 13 can no longer be canonical. But `confirm(12)` abandons only slots ≤ 12, and `recompute_contested` drops the confirmed 12 from the sibling count, so 13 is neither abandoned nor contested. Its versions are priced until a later confirmation (here 15) abandons it.
  - **(b) A slot abandoned on arrival.** With interslot statuses (`slot_statuses = "auto"`, on once the owner's probe accepts them), `created_bank` (status 5) of slot 14 names parent 12. If 12 is already abandoned, 14 is abandoned at once, before its replay writes arrive.
    - Those writes are then applied to the store and priced, because neither `apply` nor `on_account` checks `forks.is_abandoned(slot)`.
    - They are never dropped. The later processed status of 14 calls `abandon` again, which returns early, so no `on_abandoned` runs.
    - The abandoned version stays current until the account's next write.
  - Both break invariant 3 ("…or one from an abandoned fork once that fork is known to be abandoned").
- **Proof:**
  - Probe 2: `A's routes while 12/13 both unconfirmed: "fork_pending"; after 12 confirmed: 13 abandoned false contested false; B's decision route reasons ["best", "below_min_profit"] (A at slot 13); after 15 confirmed: 13 abandoned true fork_priced 0 -> 1`.
  - Probe 3: `A.vault1 now slot 14 (abandoned: true); versions dropped 0; state_opportunity 2`. The best route netted 104,578,528 and 100,386,390 lamports on the abandoned state.
- **Fix:**
  - On `confirm(S)`, abandon every live node whose known ancestry joins S's chain strictly below S, whatever its slot number.
  - In `on_account`, refuse and count (`fork_late_version`) an update whose slot is already abandoned. Treat a slot whose known parent is abandoned the same way.
  - Add tests for both sequences.

### 4. Major (hot path, regression): `save_signer_stats` serializes the whole signer map on the engine thread every 10 s

- **Location:** `engine.rs:819-828`, called from housekeeping (`:1229`) with each status line, and from `finish` (`:1164`).
- **Problem.**
  - WP-04 changed `save_signer_stats` to build `signer_stats_json(&self.signer_stats)` on the engine thread: a sort, base58 for every key, and a serde map.
  - HEAD 9bfd72d cloned the map on the engine thread and did that work in `rec.task`.
  - The real file on Cherry (`runs/signer-stats.json`, Oct 3) holds **30,304 signers**.
  - Every 10 s the engine stops for about 25 ms. Groups resolve late, decisions are delayed, and the lag SLO, whose p90 limit is 30 ms, is polluted with up to 25 ms per stall.
  - cmp2 §6 P1 #8 already asked for this to move off the engine thread.
- **Proof** (probe 5; 30,304 random keys, the real file's size):
  - `save_signer_stats` takes `[25214, 24869, 25463, 25016, 25515] µs` on the engine thread.
  - The 10-s timers take `[24301, 24704, 25385, 25729] µs` with the map and `[17-28] µs` without it.
  - A clone of a 30,304-entry map, HEAD's engine-thread cost, takes 31 µs warm (235-299 µs cold; standalone `rustc -O` measurement).
- **Fix:** move the serialization back to `rec.task`: clone or `Arc`-snapshot the maps, as HEAD did. Better still, hand the writer only the delta and let it keep the full map.

### 5. Minor: decisions price sizes past the 4.2 SOL cap (the cmp2 ladder-edge class survives in the records)

- **Location:** `engine.rs:1583-1584` (`price_route`: the refinement's `hi` is `sizes[idx] * 2` when the best rung is the last).
- **Problem.**
  - With the Stage-0 ladder (top rung 4.2 SOL), a decision's best route can be sized 8.4 SOL. Its `net`, `gross`, `band`, the opportunity and the caps line all describe a trade the executor never sends: `route_in` re-quotes at `size.min(cap)`.
  - Route selection between routes is also made at uncapped sizes.
  - Sends are safe (capped), but cmp2's "57 opportunities at 8.4 SOL carry 98.13 SOL of quotes" class reappears in decisions.jsonl and opportunities.jsonl, and WP-05/06 bands would read inflated quotes.
- **Proof:** probe 4 gives `best route size 8399809909 net 915130421 band 4`. The implementer's own cmp2 test prints its poisoned quote "at 8,399,809,909 lamports".
- **Fix:** clamp `hi` to the top rung, or to `live.max_size_sol` when an executor exists, and record the capped quote.

### 6. Minor: offline acceptance "synthetic streams through `testdata/grpc` and `forward`: S1, S1b, S8b" is only partly met

- **Location:** `feeds/mod.rs` test `grpc_stream_fixture…`.
- **Problem.** The fixture asserts that T1 completes from the tx stream, that T2 resolves by quiescence and that a dead slot is abandoned. The two-pool split (S1), the late member (S1b′) and the sibling fork (S8b) are tested only at engine level, which bypasses the protobuf → `Event` path. The implementer reports this as "partly".
- **Fix:** extend the fixture (`ARBX_WRITE_FIXTURES=1`) with those three sequences.

### 7. Minor: slot-index `missing` evidence and RPC refetches are incomplete

- **Location:** `engine.rs:2212-2220` (`on_dropped(dropped, &[], …)`), `engine.rs:2365-2381`.
- **Problem:**
  - `missing` evidence drops versions, but drops no pending group (`fork_dropped`) and marks no `fork_priced` (deviation 10).
  - A failed fork refetch or DLMM-array fetch is never retried, so the pool stays `account_missing` until its next write. That fails closed but is silent.
- **Fix:** record each decision's (account, txn) read so `missing` evidence can mark it. Retry `fetch_accounts` chunks and count failures (shared with finding 1).

### 8. Minor: deferred sends and bundle resends do not re-check the store's health; the executor's default health is "always ready"

- **Location:**
  - `exec.rs:1281` (the deferred sim-gate send checks only `gate.allows()`);
  - `exec.rs:1297` (resends);
  - `exec.rs:834` (`HealthFlags::always_ready()` until `Engine::run` installs the engine's flags).
- **Problem:**
  - A send fired tens to hundreds of ms after its decision ignores a state outage or a warm-up that started meanwhile.
  - Any future caller that builds an `Exec` without `Engine::run` fails open. `simcheck --canaries` does today, by design.
- **Fix:** WP-05's `send_checks` should take the flags at the decision and at every deferred fire, and default to not ready.

### 9. Minor: the lag rule compares the state stream with itself

- **Location:** `engine.rs:695-698` (`tip_slot` uses the shred slot only while the state is unavailable), `:1068`, `:2032`.
- **Problem:**
  - A provider that streams continuously but N slots behind the cluster passes both the lag rule and the 2 s age rule. Its processed slot and its account slots lag together.
  - `state.last_update_age_ms_now` is the age of any message, slot statuses included, not of the newest account update (deviation 3). Account-update stalls are still caught by the Clock through the lag rule, but the field's name promises more.
- **Fix:** compare `stream_slot_max` with the unexecuted feeds' slot, with an offset of about 1-2 slots, or with feedhealth `provider_lag_ms`. Report the account-update age separately.

### 10. Minor: a sustained outage after the first message never ends the segment

- **Location:** `engine.rs:1061` (the boot stop needs `msgs == 0`).
- **Problem:** a stream that dies at minute 1 and stays down (a silent stall survives the 10 s/20 s keepalive) leaves the segment blind until its deadline, which ends with exit 0. Only the WARNING and the status fields show it. This meets the literal I-4 text, but cmp2's lesson ("ran blind … exit 0") applies.
- **Fix (owner decision):** stop with `state_unavailable` after M minutes unavailable, or have the supervisor read `state.unavailable_total`.

### 11. Minor: the lookup-table preload grows without bound and is journaled in full every segment

- **Location:** `main.rs:880-906`, `:1244`; `journal.rs` ALT `found` 3; `engine.rs:739-748` (`write_alts` dumps every table, preloaded ones included).
- **Problem:**
  - "auto" preloads the newest sibling's alts-final. Each segment then re-dumps everything it holds, so the set only grows across a campaign.
  - Every table goes into the journal's boot section at 32 bytes per entry. arb-lab's long-1-p1 dump was 157 MB of raw JSON (MEASUREMENT §5), about 3.3M addresses (est.). That makes about 100 MB of journal per segment against a §5 budget of 0.5-1 GB/h, plus the boot time to parse it.
- **Fix:** journal the preload file's path and sha256 instead of its tables (replay reads the file), and preload only tables used in the last N hours.

### 12. Minor: accuracy scoring uses only the decoded input, and incomplete groups

- **Location:** `engine.rs:2254-2326` (`input_src: "decoded"` always); `on_resolution` takes `h.writes` from the first resolution of T.
- **Problem:**
  - Item 13 asks for T's executed input when it is known. The PumpSwap stream's token balances are available but not plumbed (deviation 1).
  - A group resolved by quiescence before all of T's writes arrived scores the hint against a partial post-state. A late member does not re-score it.
- **Fix:** carry the executed amounts from the tx-stream meta. Re-score, or mark `torn`, when a late member of T arrives.

### 13. Minor: the engine benchmark does not cover the real shape

- **Location:** `engine.rs` `engine_benchmark_recorder_on_off`.
- **Problem:** it covers 2-pool pairs with the default 6-rung ladder. My runs give a best p99 of 2.4-2.8 µs with the recorder off and 3.8-4.5 µs with it on, against WP-02's recorded 1.17 / 1.30 µs on a different shape.
- **Measured shape:** the Stage-0 ladder, 4 and 8 pools per pair, recorder on (table below). The cost is 15-22 µs p50 and 21-32 µs p99 per evaluation. That is fine for Stage 0, but it is what the acceptance should state.
- **Fix:** add these shapes to the benchmark, and assert on the status line and housekeeping (p99.9).

### Nits

- **N1.** MEASUREMENT's header still says "specification, revision 2.3"; only the body adds "Revision 2.4".
- **N2.** `config.rs:716` says the signer-stats sha256 "goes to meta.json". It goes only to run.log and engine_init.
- **N3.** Suppose a transaction re-executes on the canonical fork after its group was `fork_dropped`. It is then classed as a late member, and the decisions since are marked `torn_suspect` although nothing was torn.
- **N4.** Without a Clock sysvar, `route_in` prices on the host clock (`unix_now`) while `evaluate_pool` uses `t_now`.
- **N5.** Six HEAD tests were removed with their code:
  - `after_an_input_the_timers_keep_arb_labs_rules`;
  - `caps_line_waits_for_the_end_of_the_flush`;
  - `decoded_sends_on_keeps_the_old_path`;
  - `failing_signer_is_skipped_before_the_hint_and_keeps_learning` (renamed);
  - `state_trigger_carries_update_receive_and_dequeue_times`;
  - `state_trigger_keeps_the_first_update_time_across_a_flush`.

  Each follows from a PLAN removal, but the DoD asks the merge note to name removals.
- **N6.** `GaveUp` lookup-table entries are never pruned, and `Alts::next_retry` scans all entries on every input. That is O(tables) per event.
- **N7.** `arbx signer-stats merge` does not check that the segment has ended (no `stop.json`). Merging a running segment marks it merged with a partial delta.
- **N8.** MEASUREMENT says pre-WP-04 recordings "replay with this engine only up to its WP-04 changes". In fact `replay_engine` refuses them: `strategy_sha256` changes with the removed fields, and the run's config no longer loads.

## Hot-path measurements

Method: scratch integration test `review_bench`, run through the public API. Each transaction writes both vaults of one AMM v4 pool (W unknown), and the timers 4 ms later (virtual) evaluate it. I timed every `step` / `timers` call: 20,000 transactions × 3 runs, 80 pools, the Stage-0 ladder of 10 rungs.

| Pools per pair | Recorder | Busy per transaction, p50 / p99 / p99.9 (µs) | `step` (an update), p50 / p99 (µs) |
|---|---|---|---|
| 2 | off | 2.7 / 9.3-9.7 / 85-132 | 0.19 / 0.31-0.33 |
| 2 | on | 3.9-4.4 / 14.1-16.6 / 94-120 | 0.37-0.40 / 1.9-2.4 |
| 4 | off | 11.9 / 15.3-16.3 / 111-160 | 0.23-0.24 / 0.45-0.47 |
| 4 | on | 15.3-15.5 / 21.4-22.1 / 150-192 | 0.59-0.61 / 1.4-1.5 |
| 8 | off | 16.9-17.0 / 20.4-22.2 / 123-138 | 0.24-0.25 / 0.54-0.56 |
| 8 | on | 21.3-21.7 / 29.4-32.0 / 179-258 | 0.61-0.71 / 1.5-1.7 |

- p99.9 is housekeeping plus the 10-s status line. With the real signer map, add about 25 ms every 10 s (finding 4).
- I did not build HEAD. A second checkout of this crate in a shared target dir can alias cargo artifacts (P3). The HEAD comparison is therefore WP-02's recorded benchmark and the code diff of `save_signer_stats`.

## Process notes

- **P1.** The reviewed tree was committed during the review as 6f8fd3c "post" (hash-verified identical).
  - The message does not follow the git rule ("WP-04: State consistency: price only committed, complete, canonical states", a body, the Co-Authored-By line).
  - The implementer's report says nothing was committed.
  - Whether to reword it is the owner's or orchestrator's call. I did not touch git.
- **P2.** d5c8d67 (the bait keystore removal) changes the lib test count to 202. A merge note written from the report's 203 would be off by one.
- **P3.** My probes were built from a scratch copy in the shared lanes target, and those artifacts are deleted.
  - Cargo names the artifacts of a workspace-root crate by a path-independent hash, and decides freshness by the mtimes of the files its dep-info lists.
  - So two checkouts of `arbx` sharing one target can, in principle, reuse each other's build when every listed file exists in both and is older than the other's build.
  - My copy listed WP-04-only files, so the lanes (at ab08b9a) would rebuild. Two lanes from the same base, though, can alias each other.

## Appendix: the probes (scratch only; appended to `engine.rs`'s `mod tests`)

```rust
fn rp_health(e: &mut Engine, connected: bool, t: u64) {
    e.step(crate::feeds::state_health(connected, 2, 1, (!connected).then(|| "status: 503".into())), t, &mut nop());
}

/// PROBE 1 (I-4): pricing and the wants_send flags resume before the re-snapshot lands
#[test]
fn review_probe_1_reconnect_prices_before_the_resnapshot_lands() {
    let mut r = rig("rp1");
    make_ready(&mut r.e, T0);
    let (_a, b) = (meta(1), meta(2));
    rp_health(&mut r.e, false, T0 + 10 * MS);
    assert_eq!(r.e.shut(), Shut::StateUnavailable);
    // 30 s later the stream reconnects; meanwhile both pools moved on chain; we saw neither write
    let tr = T0 + 30_000 * MS;
    rp_health(&mut r.e, true, tr);
    slot_ev(&mut r.e, 90, 0, Some(89), tr + 1 * MS);
    acct(&mut r.e, *CLOCK_SYSVAR, clock_data(90, 1_759_000_030), 90, tr + 1 * MS, None, 500);
    let shut_now = r.e.shut();
    // B's next write; A still holds its pre-outage version (no re-read answer yet)
    acct(&mut r.e, b.vault1, vault(1_031 * SOL), 90, tr + 2 * MS, Some(sig(0xB1)), 501);
    acct(&mut r.e, b.vault0, vault(970_000_000_000_000), 90, tr + 2 * MS + 1, Some(sig(0xB1)), 502);
    r.e.timers(tr + 6 * MS, &mut nop());
    assert_eq!(shut_now, Shut::Ready, "ready before any re-snapshot answer");
    assert!(r.e.counter("state_opportunity") >= 1, "a phantom gap against the pre-outage pool");
}

/// PROBE 2 (forks): a confirmed slot's higher-numbered sibling stays priceable
#[test]
fn review_probe_2_a_confirmed_slots_higher_sibling_stays_priceable() {
    let mut r = rig("rp2");
    make_ready(&mut r.e, T0);
    let (a, b) = (meta(1), meta(2));
    let t = T0 + 20 * MS;
    slot_ev(&mut r.e, 11, 1, Some(10), t);
    slot_ev(&mut r.e, 12, 0, Some(11), t);
    slot_ev(&mut r.e, 13, 0, Some(11), t);
    acct(&mut r.e, a.vault1, vault(1_030 * SOL), 13, t + 1 * MS, Some(sig(1)), 10);
    acct(&mut r.e, a.vault0, vault(970_000_000_000_000), 13, t + 1 * MS + 1, Some(sig(1)), 11);
    r.e.timers(t + 5 * MS, &mut nop());                  // A's routes: fork_pending (correct)
    slot_ev(&mut r.e, 12, 1, Some(11), t + 6 * MS);      // 12 confirmed: 13 cannot be canonical
    let (ab, co) = (r.e.forks.is_abandoned(13), r.e.forks.is_contested(13));
    slot_ev(&mut r.e, 14, 0, Some(12), t + 7 * MS);
    acct(&mut r.e, b.vault1, vault(1_001 * SOL), 14, t + 7 * MS, Some(sig(2)), 12);
    acct(&mut r.e, b.vault0, vault(999_000_000_000_000), 14, t + 7 * MS + 1, Some(sig(2)), 13);
    r.e.timers(t + 11 * MS, &mut nop());                 // B's decision prices A at its slot-13 version
    assert!(!ab && !co);
}

/// PROBE 3 (forks): writes to a slot already abandoned (created_bank on an abandoned parent) are priced and kept
#[test]
fn review_probe_3_writes_of_an_already_abandoned_slot_are_priced_and_kept() {
    let mut r = rig("rp3");
    make_ready(&mut r.e, T0);
    let (a, b) = (meta(1), meta(2));
    let t = T0 + 20 * MS;
    slot_ev(&mut r.e, 12, 0, Some(11), t);
    slot_ev(&mut r.e, 13, 0, Some(11), t);
    slot_ev(&mut r.e, 13, 1, Some(11), t + 1 * MS);      // 12 abandoned
    slot_ev(&mut r.e, 14, 5, Some(12), t + 2 * MS);      // created_bank on 12: 14 abandoned at once
    acct(&mut r.e, a.vault1, vault(1_030 * SOL), 14, t + 3 * MS, Some(sig(1)), 10);
    acct(&mut r.e, a.vault0, vault(970_000_000_000_000), 14, t + 3 * MS + 1, Some(sig(1)), 11);
    r.e.timers(t + 7 * MS, &mut nop());
    slot_ev(&mut r.e, 14, 0, Some(12), t + 8 * MS);      // its processed status: nothing dropped
    slot_ev(&mut r.e, 16, 0, Some(13), t + 9 * MS);
    acct(&mut r.e, b.vault1, vault(1_001 * SOL), 16, t + 9 * MS, Some(sig(2)), 12);
    acct(&mut r.e, b.vault0, vault(999_000_000_000_000), 16, t + 9 * MS + 1, Some(sig(2)), 13);
    r.e.timers(t + 13 * MS, &mut nop());
    assert_eq!(r.e.store.get(&a.vault1).unwrap().slot, 14, "the abandoned version is the current one");
    assert!(r.e.counter("state_opportunity") >= 1);
}

/// PROBE 4 (I-8 ladder edge): decisions price past the size cap
#[test]
fn review_probe_4_decisions_price_past_the_size_cap() {
    let cfg = StrategyCfg { state_triggers: true, sizes_sol: vec![0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 4.2], ..StrategyCfg::default() };
    let mut r = rig_with("rp4", cfg, &[(1, 15_000), (2, 15_000)]);
    make_ready(&mut r.e, T0);
    let b = meta(2);
    let t = T0 + 20 * MS;
    acct(&mut r.e, b.vault1, vault(15_900 * SOL), 12, t, Some(sig(1)), 10);
    acct(&mut r.e, b.vault0, vault(950_000_000_000_000), 12, t + 1, Some(sig(1)), 11);
    r.e.timers(t + 4 * MS, &mut nop());
    let d = decisions(&r);
    let x = d.last().unwrap();
    assert!(x["routes"][x["best"].as_u64().unwrap() as usize]["size"].as_u64().unwrap() > 4_200_000_000);
}

/// PROBE 5 (hot path): the 10-s housekeeping with the real signer map size (30,304)
#[test]
fn review_probe_5_signer_stats_save_cost() {
    let mut r = rig("rp5");
    let dir = r.dir.clone();
    r.e.set_signer_stats_out(&dir);
    let mut x = 0x9e3779b97f4a7c15u64;
    for n in 0..30_304u32 {
        let mut k = [0u8; 32];
        for c in k.chunks_mut(8) { x ^= x << 13; x ^= x >> 7; x ^= x << 17; c.copy_from_slice(&x.to_le_bytes()); }
        r.e.signer_stats.insert(k, (n % 5, n % 3));
    }
    for _ in 0..5 { let a = std::time::Instant::now(); r.e.save_signer_stats(); eprintln!("{} us", a.elapsed().as_micros()); }
    let mut t = T0;
    for _ in 0..5 { t += STATUS_EVERY_NS + 1; let a = std::time::Instant::now(); r.e.timers(t, &mut nop()); eprintln!("{} us", a.elapsed().as_micros()); }
}

/// PROBE 6 (forks): the late-leader fork; the rollback restores the pre-fork version, not the canonical one
#[test]
fn review_probe_6_rollback_restores_a_pre_fork_version_not_the_canonical_one() {
    let mut r = rig("rp6");
    make_ready(&mut r.e, T0);
    let a = meta(1);
    let t = T0 + 20 * MS;
    slot_ev(&mut r.e, 11, 1, Some(10), t);
    slot_ev(&mut r.e, 13, 0, Some(11), t);               // 13 (built on 11) replayed first
    acct(&mut r.e, a.vault1, vault(1_020 * SOL), 13, t + 1 * MS, Some(sig(13)), 10);
    acct(&mut r.e, a.vault0, vault(980_000_000_000_000), 13, t + 1 * MS + 1, Some(sig(13)), 11);
    slot_ev(&mut r.e, 12, 0, Some(11), t + 2 * MS);      // the late block 12, replayed next
    acct(&mut r.e, a.vault1, vault(1_050 * SOL), 12, t + 3 * MS, Some(sig(12)), 12);   // refused: stale
    acct(&mut r.e, a.vault0, vault(952_000_000_000_000), 12, t + 3 * MS + 1, Some(sig(12)), 13);
    r.e.timers(t + 8 * MS, &mut nop());
    slot_ev(&mut r.e, 12, 1, Some(11), t + 9 * MS);      // 12 wins
    slot_ev(&mut r.e, 14, 0, Some(12), t + 10 * MS);
    slot_ev(&mut r.e, 14, 1, Some(12), t + 11 * MS);     // 13 abandoned
    let v = r.e.store.get(&a.vault1).unwrap();
    let amount = u64::from_le_bytes(v.data[64..72].try_into().unwrap()) / SOL;
    assert_eq!((v.slot, amount), (10, 1_000), "the pre-fork boot version, not the canonical slot-12 one (1,050 SOL)");
}
```

## Disposition (2026-10-04, WP-04 commit)

The review's code is 6f8fd3c ("post"); its fixes are the WP-04 commit on top of it. Process note P1 (rewording 6f8fd3c) is
left to the owner or orchestrator: history is not rewritten. P3: every build of this work went to the main tree's own
`target`, never the shared lanes target. Tests at the commit: `cargo test --release` 243 passed, 0 failed, 2 ignored
(lib 219 + 1 ignored: 17 new; bin 10; legacy_fixtures 4; meta_config_hash 1; runtime_isolation 2 + 1 ignored; stop_path 6;
supervisor 1); toolkit 79 OK, 4 skipped; `cargo build --release` with the 2 pre-existing warnings; `arbx check` exits 0 on
`deploy/arbx-stage0.toml` and `deploy/arb.toml`. The replay tests passed 15 of 15 times, and the WP-04 module tests (60)
in four concurrent runs.

| # | Severity | Disposition |
|---|---|---|
| 1 | Blocker | **Fixed** (below) |
| 2 | Major | **Fixed**: the store is fork-aware (the review's second option) |
| 3 | Major | **Fixed** (a) and (b) |
| 4 | Major | **Fixed** |
| 5 | Minor | **Fixed**: the refinement stays inside the ladder |
| 6 | Minor | **Fixed**: a second gRPC fixture carries S1, S1b′ and S8b |
| 7 | Minor | **Fixed**: reads retried; slot-index evidence drops groups and marks decisions |
| 8 | Minor | **Partly**: deferred sends and resends check the store's health; the default flags stay WP-05's |
| 9 | Minor | **Partly**: the account-update age is reported apart; the lag rule's tip stays open (WP-08) |
| 10 | Minor | **Mechanism added, off by default** (owner decision) |
| 11 | Minor | **Fixed** (bounded preload); journaling a path instead of the tables stays open |
| 12 | Minor | **Open** (WP-16) |
| 13 | Minor | **Fixed**: a Stage-0-shape benchmark |
| N1-N4, N6-N8 | Nits | **Fixed**; N5 is in the commit body |

**1 (blocker, I-4).** `src/reads.rs` (new) and `engine.rs` (`begin_resync`, `resync_chunks`, `resync_floor`, `spawn_read`,
`on_fetch`, `read_job_done`):
- The stream's first connection (`"boot"`: the boot snapshot is read before the stream subscribes, (c)) and every
  reconnection (`"reconnect"`, (a)) start a re-read of every followed account. Until it has landed the gate is
  `Shut::Resync` (status `health.shut` `resync`; `HealthFlags` not ready; `Exec::wants_send` refuses, `reject_resync`; the
  decision verdict says `resync`).
- Per account, too: every re-read account is *unverified* until the re-read or an applied stream write after the
  connection brings it, and a pool with an unverified part is refused with route reason `resync` (`NotReady::Resync`,
  checked before `pending_commit`; an unverified DLMM bin array is left out of the quote). So the probe-1 sequence prices
  nothing against A's pre-outage version: the decision's routes are all `resync`, no opportunity.
- The re-read starts one slot (400 ms) after the stream's *resume slot* (its first account update or processed slot after
  the connection) and a chunk read at a context slot before it is read again (`resync_chunk_behind`): an RPC node behind
  the stream would miss the writes before the resume point. This goes beyond the review's fix.
- Chunks of at most 100 accounts pack each Tier-A pool's own accounts (pool, consistency set, vaults, followed bin arrays)
  together, so a pool's parts are read at one slot (the skew side effect); they start 120 ms apart, at most 4 at once.
- Each chunk's accounts come back as account events (accounts.bin src 3, aseq-named in the journal), then a journaled
  INPUT 11 `fetch` (`{job, chunk, what, attempt, n, ok, slot, missing}` or `{..., ok: false, err}`); chunk starts are engine
  times run by the timers, so a replay decides the same (b: nothing is dropped silently). A failed chunk is read again
  after 250 ms, 1 s, 2 s, 5 s, then every 10 s (`read_chunk_failed`, `read_retry` events). At `resync_warn_s` (10) a
  WARNING and `state_resync_slow`, the gate staying shut; at `resync_give_up_s` (300) a chunk is given up with a WARNING:
  the gate opens, and its accounts stay refused one by one until the stream writes them. The review asked to stay shut;
  the per-account refusal keeps pricing correct, so a broken chunk no longer stops trading on the pools that were read.
  An account the node does not have stays unverified while the store holds a version of it.
- The boot snapshot labels each 100-account call with its own context slot (`main.rs`; it used the last call's for all).
- Tests: `a_reconnect_prices_nothing_until_the_re_read_lands` (the probe-1 sequence decides `resync` until the re-read
  lands; an injected chunk error is retried; a read behind the resume slot is read again; then A is priced at the re-read
  state), `the_first_connection_re_reads_the_boot_snapshot` (boot, 40 pools packed 99 + 21 with every pool in one chunk,
  the WARNING, the give-up), `a_state_outage_stops_pricing_and_writes_no_false_signer_misses` (updated),
  `a_wp04_run_replays_to_the_run` (now through a JSON-RPC server, `rpc::mock`: both re-reads land, one chunk fails and is
  read again, INPUT 11 journaled, the replay equal to the run), `reads::tests` (pace, cap, retries, give-up, cancel,
  packing).

**2 (major).** `store.rs::apply`: a version older than the current one, from a slot (and bank) the ring holds no version
of, is kept in the ring at its place (`kept_below`); a fork drop then falls back to the newest surviving version: the
canonical one. Eviction takes the oldest first, so the newest surviving version is the newest the stream delivered on the
surviving branch, or the ring is empty and the account is fetched again (unchanged). A canonical block's writes reach
the stream before the confirmation that abandons the other branch (a confirmed slot has been replayed), so no extra
refetch is needed; a same-slot reordering is still refused. Tests: `store::a_rollback_restores_the_canonical_version_of_a_lower_slot`,
`engine::the_late_leader_fork_restores_the_canonical_version` (the probe-6 sequence ends at slot 12 with 1,050 SOL, no refetch).

**3 (major).** `forks.rs`: (a) `confirm(S)` also abandons every live slot above S whose ancestry passes below S without
going through it (the higher-numbered sibling and what is built on it), and a later status of a slot the newest
confirmation dooms abandons it on arrival (an ancestor reported late is marked confirmed instead); (b) `SlotTree::refuses`
and `Engine::on_account` refuse a write of a slot already abandoned (`fork_late_version`, status `forks.late_version_delta`);
the journal's ACCOUNT verdict is `Engine::account_refused` (stale or abandoned), which replay checks. Tests:
`forks::a_confirmed_slots_higher_numbered_sibling_is_abandoned_at_once`, `forks::a_slot_abandoned_on_arrival_refuses_its_writes`,
`engine::a_confirmed_slots_higher_sibling_is_never_priced` (probe 2: 13 abandoned at 12's confirmation, B's decision
reads A's canonical version, `fork_priced` stays 0), `engine::writes_of_a_slot_already_abandoned_are_refused` (probe 3).

**4 (major).** `save_signer_stats` hands the recorder's writer the statistics as loaded (`signer_base`, an `Arc`, no copy)
and a copy of this segment's counts; the writer adds them up and serializes. Test
`saving_signer_stats_stays_off_the_engine_thread` (30,304 signers: the save and the 10-s status line in microseconds on the
engine thread, against about 25 ms; the files hold the sum); the Stage-0 benchmark below measures the status lines.

**5.** `price_route`: the refinement's upper bound is the next rung, or the top rung itself when the best rung is the
last: a decision never prices past the ladder (4.2 SOL in Stage 0). Test `decisions_never_price_past_the_top_rung`
(probe 4). The WP-02 benchmark's 1%-gap case now uses a 0.05 SOL minimum profit (a 10% gap at the 1 SOL top rung nets
about 0.085 SOL).

**6.** `feeds/fixture.rs::wp04_stream` and `testdata/grpc/wp04.bin` (regenerated with `ARBX_WRITE_FIXTURES=1`), test
`grpc_wp04_sequences_through_forward`: S1 (a route through A and B whose write set comes from the transaction stream after
its first updates; C's evaluation in between refuses the routes through A and B, `pending_commit`; complete with B's
vaults), S1b′ (quiescence, then a late member) and S8b (`fork_pending` while 2002 and 2003 are unconfirmed; 2003 confirmed,
2002 abandoned without `dead`, its versions dropped, a `fork` evaluation) through protobuf, `forward` and `step`.

**7.** Fork refetches and new DLMM bin arrays go through `reads.rs` (retried, given up after 600 s with a `read_gave_up`
event). Slot-index `missing` evidence drops the transaction's pending group (`CommitTracker::drop_txns`) and marks
`fork_priced` the decisions that read a version it wrote (decisions now remember the (slot, txn) of the versions read),
even when no version is held any more. Test `slot_index_missing_marks_decisions_and_drops_groups`.

**8.** The sim gate's deferred send and the scheduled bundle resends check the store's health flags as well as the
SendGate (`exec.rs`). The default `HealthFlags::always_ready` for an `Exec` built without `Engine::run` stays:
`simcheck --canaries` relies on it; making it not-ready by default belongs with WP-05's `send_checks`.

**9.** Status `state.last_account_age_ms_now` is the newest stream account update's age (`last_update_age_ms_now` keeps
counting slot statuses). Comparing the store with the unexecuted feeds' slot is not done: one feed's garbage slot (the
engine believes any within 1,000 slots) would shut the gate for minutes. It needs an independent tip (the LeaderBook and
PoH clock, or two feeds agreeing): WP-08.

**10.** `[state] unavailable_stop_s` (0 by default: off): when set, a state unavailable that long without a break, after
the stream had delivered, stops the run with `state_unavailable` (exit 30, a fresh segment from the supervisor). Choosing
a value is the owner's decision. Test in `a_state_outage_stops_pricing_and_writes_no_false_signer_misses`.

**11.** `alts-final.jsonl` lines carry `last_used_ns` (when a transaction last used the table), and the preload takes only
tables used within `[alts] preload_max_age_h` (24) of the segment's start, at most `preload_max_tables` (5,000), the most
recently used first (a line without the field counts as used when its file was written). The set no longer grows across a
campaign, and the journal's boot section holds at most that many tables. Journaling the file's path and sha256 instead
would make a replay depend on a sibling segment's file: left open for WP-09. Test (bin)
`alts_preload_reads_the_previous_segments_tables`.

**12.** Open for WP-16 (the accuracy monitor moves to the arbx-sizing maths there): the PumpSwap stream's executed amounts
as the hint's input, and re-scoring (or marking) a hint when a late member of its transaction arrives.

**13.** `engine_benchmark_stage0_shapes`: the Stage-0 ladder and caps, 80 pools at 4 and 8 per pair, recorder on, the
30,304-signer map behind the status line; busy time per transaction (two updates and the timers that evaluate them) and
the status-line calls apart. One run on this host (other agents building): 4 per pair p50 7 µs, p99 22 µs, p99.9 92 µs;
8 per pair p50 15 µs, p99 37 µs, p99.9 115 µs; status lines 100-370 µs. The bounds asserted are generous (p99 under
1 ms, p99.9 under 10 ms, the fastest status line under 5 ms) for a loaded CI host.

**Nits.** N1: MEASUREMENT's header is revision 2.5 (2.4 plus these fixes). N2: the `signer_stats_file` comment says
run.log and engine_init. N3: a group a fork dropped is not remembered, so its transaction executing again on the canonical
branch opens a new group, not a late member. N4: `route_in` prices on the decision's clock (`chain_now`: the engine's time
without a Clock sysvar; the host's only before any input, for `simcheck`). N5: the commit body names the six tests removed
with their code. N6: given-up lookup tables are kept apart (`given_up`), so the per-input `next_retry` scans only work in
progress. N7: `signer-stats merge` refuses a run without `stop.json`. N8: MEASUREMENT §4.13 now says pre-WP-04 recordings do
not replay (`replay_engine` refuses them).

**Operational notes for the owner's field run.** The re-read adds about 6 s of `resync` at boot and after each reconnect
for a registry like cmp2's (4,372 accounts: about 45 chunks 120 ms apart, after the 400 ms delay), and doubles the boot's
RPC reads (snapshot, then re-read). `state_resync_done` events give each re-read's duration, retries, chunks read behind
the stream and accounts not found.

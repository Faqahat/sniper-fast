# WP-02 review: recorder framework (always on, off the hot path) and the background runtime

**Date:** 2026-10-04. **Reviewer:** adversarial review of the uncommitted WP-02 working tree on master. Master moved to `2237d54` during the review (a tools-only commit); the WP-02 diff does not overlap it.
- **Files reviewed:** the `git diff` of `Cargo.toml`, `Cargo.lock`, `deploy/arb.toml`, `deploy/arbx-stage0.toml`, `docs/MEASUREMENT.md`, `src/{config,engine,exec,lat,lib,main,provenance,rpc}.rs`, `src/feeds/{grpc,mod,shred}.rs`, `src/send/{mod,jito}.rs` and `tests/meta_config_hash.rs`; the deleted `src/record.rs`; and the new `src/rec/{mod,writer,disk,health,manifest,tests}.rs`, `src/runtime.rs` and `tests/runtime_isolation.rs`.
- **Not reviewed:** `program/arbx-sizing/`, `program/venue-harness/`, and `tools/` (no WP-02 change). `tools/arbx-report` was only run against WP-02 output.
- **Checked against:**
  - PLAN.md WP-02 (items 1-11, config keys, offline and field acceptance), §1 rows 18, 22 and 33-34, and §2 invariants 4-6;
  - MEASUREMENT.md §0, §1.2-§1.6, §2.2, §4.4-§4.11, §4.19-§4.26, §5 and §7;
  - PLAN-ADDENDUM I-2;
  - `deploy/run-w.sh` (how the supervisor reads status.jsonl and attempts).
- No repository code was changed. The probes below were built in a scratch crate outside the repo (`scratchpad/rev02-probe`), using `arbx` as a path dependency.

**Verdict.**
- **No blockers.** Nothing in WP-02 can make arbx send when it would not have sent at HEAD:
  - the only new SendGate actions close it: `core_record_loss` sets a sticky shadow, and `disk_budget` sets shadow, then stop;
  - `--no-record` is gone, and nothing else in the send path changed.
- **Three major findings.** All three are cases where recording can be lost while the run keeps trading, or where the recording cannot be analysed:
  1. Write and open errors in the writer threads are swallowed. A core stream that cannot be written (ENOSPC, EDQUOT, EIO) is reported as written in the manifest. There is no drop, no event and no shadow. This is shown with a probe (F1).
  2. A writer thread that dies is never noticed. The slow writer runs `println!`/`eprintln!`, which panic when stdout or stderr fails. After that, status.jsonl (the supervisor's budget source), run.log and events.jsonl stop silently while the engine keeps trading. At HEAD the same failure stopped the run with a panic (fail closed). Also shown with a probe (F2).
  3. The merged toolkit cannot read any segment WP-02 writes. `arbx-report segment` raises `SchemaError` on `triggers.000.jsonl.zst` (`arbx.triggers/1.1`). The implementer reported this; this review reproduced it (F3).
- There are also fourteen minor findings (F4-F17) and five nits (N1-N5).

---

## Verification performed

| Check | Result |
|---|---|
| `cargo build --release` (`CARGO_TARGET_DIR` on /tmp; the home quota has about 34 MB free, as the implementer reported) | Passes. **3 warnings**, the same as at HEAD: `Check` has dead fields, and `main.rs` has two irrefutable `if let`. No new warnings |
| `cargo test --release` | **148 passed, 0 failed, 2 ignored**: lib 126 (+1 ignored), bin 9, legacy_fixtures 4, meta_config_hash 1, runtime_isolation 1 (+1 ignored), stop_path 6, supervisor 1. `tx_error_decodes_custom_codes` moved to `src/rec/tests.rs` |
| `emit_p99_under_1us_at_100k_per_s` (ignored test) | Passes: p50 461 ns, p99 621 ns, **max 1.38 ms** (one emit, probably OS preemption) |
| `engine_benchmark_recorder_on_off` | Passes. Best p99 1,172 ns off and 1,302 ns on; the three "on" runs were 1,653 / 1,302 / 1,774 ns. Only the moves stream is exercised (F9) |
| `runtime_isolation::strict_10_percent` (ignored test) | Passed once: arrival→dequeue p99 13.0 µs idle, 14.0 µs loaded (+7.7%); dequeue→t_sent 9.0 / 9.1 µs. Several idle phases had p99s of 0.5-1.9 ms (host noise) |
| `arbx check` on `deploy/arbx-stage0.toml` and `deploy/arb.toml` | Both load; the recorder line is printed. `deploy/legacy/arb-w-live.toml` is still refused (`config_version`), as designed |
| Probe: `attempts.000.jsonl.zst` symlinked to `/dev/full`, 100 attempts emitted, recorder closed | `emit` accepted 100 of 100. The manifest says `records_total 100`, `dropped_total 0`, `bytes_written 0` and `core_record_loss false`. The gate stays **Live**, events.jsonl is empty, and `stats().core_ok` is true (F1) |
| Probe: stdout on `/dev/full`, one `Rec::say`, then 7 status lines and 3 attempts | `thread 'arbx-rec-slow' panicked … failed printing to stdout`. status.jsonl stops at the line before the panic; the 7 later lines are counted as dropped, but only in memory. The gate stays **Live**, `core_ok` is true, and the process goes on (F2) |
| Probe: 4 producers emitting core records while `close()` runs, 200 rounds | No loss reproduced: the window is theoretical (F15) |
| `python3 tools/arbx-report segment` on a WP-02 segment with one `triggers` record | `SchemaError: triggers.000.jsonl.zst: schema arbx.triggers/1.x is not supported (known majors: [2])`. `quality` (R0) completes and lists the file under `unsupported_schema` (F3) |
| Real shadow run against public RPC (dead state stream; the implementer's smoke config), `--minutes 1.2`, with 18 GB free on the filesystem | The run stopped itself after **40.1 s** with exit 20 `disk_budget`. The 4 ladder steps came at 10, 20, 30 and 40 s, while the run directory held 37 KB. manifest.json is final and status v2 is well formed. feedhealth shows the state stream `connected_now false` with reconnects counted (F5) |

## Conformance with PLAN WP-02

| Plan item | Status |
|---|---|
| 1 Runtimes: rt_hot with 2 workers, rt_bg with `bg_threads` workers niced +5, large replies parsed in `spawn_blocking`, every `Rpc` bound, a debug assertion | Done. `Rpc::bind` spawns each call on rt_bg; `check_not_hot` counts violations in release builds. Gap: the TPU path's own leader-book RPC still runs on rt_hot (F8) |
| 2 `src/rec/` replaces `record.rs`; one bounded queue per class; `try_send` drops and counts; typed records; `Arc<[u8]>` payloads | Mostly done. Unbounded channels with depth caps (deviation 2, reasonable). No global OnceLock: a `Rec` handle is passed around instead (an unreported deviation, fine). "Typed records, no JSON formatted on producer threads" is only partly true (F10) |
| 3 Writer threads: niced, optional affinity, zstd 3, a frame per `flush_ms` or 4 MiB, rotation, `<stream>.<NNN>.<ext>.zst`, a header first | Done; tested. Write errors are not handled (F1). No per-file encoder hook for WP-03's dictionaries (F16) |
| 4 Small streams plain and line-buffered | Done (status, events, feedhealth, resources, keepalive, run.log; control and stop stay in control.rs) |
| 5 Drop handling by class | Queue-full drops are handled as specified. A writer that dies or cannot write is not treated as a drop (F1, F2) |
| 6 Disk budget ladder | Done literally: one step per 10 s while either limit is crossed. In practice any crossing means a stop 30-40 s later (F5) |
| 7 manifest.json every 60 s and at close | Done. For a write-failing file it reports wrong counts (F1) |
| 8 Every existing writer migrated; diagnostic lines also go to events | Done for the engine, exec, send, jito and feeds. `pools.rs:119` still uses `eprintln!` only (N3). The migrated feed and send writers have no tests (F12) |
| 9 status.jsonl v2 counter semantics | Done (interval and run windows, `_total`/`_delta`/`_now`, `money.failed_fees_total_lamports`). The supervisor's reader already handles it |
| 10 feedhealth.jsonl and resources.jsonl | Done; first arrivals and lead lag by 10 s (deviation 4c) |
| 11 `Engine::new_offline` | Done |
| Config keys; `enabled` removed | Done; validated. `disk_budget_gb = 0` is accepted (N4) |
| Offline acceptance | All present and passing. The isolation test's tolerance is looser than the plan's (F7), and the engine benchmark covers only the moves stream (F9) |

---

## Findings

Severity: **Blocker** (must not merge), **Major** (fix before WP-02's field acceptance or before a live segment runs on this binary), **Minor** (fix in WP-02 or a named follow-up), **Nit**.

### F1. Major: write and open errors in the writers are swallowed; core records that never reach disk are reported as written

- **Location:**
  - `src/rec/writer.rs:71` `write_errors` is incremented and never read;
  - `:93-96` an open failure prints one `eprintln!` and the series then discards every record;
  - `:160-164` a record is counted (`stat.records`, `written_records`) before any write;
  - `:176-179` `write_plain`;
  - `:187-197` `end_frame`: a compression or write failure only increments `write_errors`.
- **Problem.** MEASUREMENT principle 3 and §1.5 say core streams are never silently lost: "If a core stream drops a record, … sending stops". The implementation treats only a full queue as a loss. When the disk, a quota or the device fails, the writer drops every frame and gives no sign of it:
  - no drop counter and no `recorder_drop` event;
  - no `core_record_loss` shadow;
  - `health.recorder_ok` stays true;
  - manifest.json reports the records as written.
- **Consequences.**
  - The ladder's `statvfs` check does not see user quotas (EDQUOT), which is exactly what happened on this development host.
  - The same applies to status.jsonl. A segment whose status writes fail leaves an older last line, so the supervisor's `spent` (run-w.sh:149-166) undercounts the failed-fee budget. With a torn line it falls back to "unknown", which is safe.
- **Proof.** Probe `writefail`: `attempts.000.jsonl.zst` is a symlink to `/dev/full`, and 100 attempts are emitted.
  - Result: `records_total 100`, `dropped_total 0`, `bytes_written 0`, `core_record_loss false`, gate `Live`, 0 events.
  - HEAD also ignored write errors (`let _ = writeln!`), so this is not a regression. It is a WP-02 requirement that is not met.
- **Fix.**
  - Count write and open errors per stream (`write_errors_total` in the manifest and in status `recorder`).
  - Count records only after their frame was written (or count them separately as "lost to I/O").
  - Treat any write or open error on a core stream as a core loss: shadow `core_record_loss`, plus a `recorder_drop`/`recorder_io_error` event.
  - Treat a failing status.jsonl as a fault the supervisor can see, e.g. a stop with reason `error`.
  - Add a test with a `/dev/full` symlink, as above.

### F2. Major: a dead writer thread goes unnoticed, and the slow writer can be killed by stdout/stderr errors; HEAD failed closed here, WP-02 fails open

- **Location:**
  - `src/rec/mod.rs:500-509` `Rec::say` (`println!` inside the slow writer's closure);
  - `:485-496` `Rec::log` (`eprintln!` inside the closure);
  - `:512-517` `Rec::task`;
  - `src/rec/writer.rs:15-40`: no `catch_unwind` around record encoding or tasks;
  - `src/rec/health.rs:22-39`: the monitor never checks the writer threads;
  - `control.rs:269-274`: the panic hook only logs a panic off the main thread.
- **Problem.**
  - `println!`/`eprintln!` panic when the write fails (EPIPE, ENOSPC, EDQUOT). At HEAD they ran on the main thread, so a failing stdout panicked the main thread: stop.json `panic`, exit 30, and trading stopped.
  - With WP-02 they run in `arbx-rec-slow`. The panic kills that thread, and the hook only appends a line to run.log. From then on every slow-class record fails to send and is "dropped": status.jsonl, events.jsonl, run.log, feedhealth, resources, keepalive and signer-stats.json.
  - Nothing reacts. The gate stays live, `recorder_ok` reflects only core drops, and the drop counters live in memory and in the status lines that are no longer written.
  - The engine goes on trading with no status line. The supervisor's budget then reads the stale last line (see F1).
- **More of the same.**
  - Any other panic in a writer (a `Record::Task`, a future encoder in WP-03) has the same effect on its class. Chain and replay losses are only counted.
  - A stdout pipe that blocks instead of failing stalls the slow writer: an operator running `arbx run | tee` whose `tee` stops reading. The slow queue is unbounded, and every 10 s it receives a clone of the whole signer-stats map (engine.rs:414-417), so memory grows until the process is OOM-killed.
- **Proof.** Probe `slowpanic`, run with `> /dev/full`:
  - `thread 'arbx-rec-slow' panicked … failed printing to stdout: No space left on device`;
  - status.jsonl keeps the 3 lines written before; the 7 later lines are counted as dropped, but in memory only;
  - the gate stays `Live`, `core_ok` is true, and the process does not stop.
- **Fix.**
  - In the writer, echo to stdout and stderr with `let _ = writeln!(io::stdout().lock(), …)` (ignoring errors), after the file write.
  - Wrap record encoding and `Record::Task` in `catch_unwind`, and count failures per stream.
  - Have the monitor check `JoinHandle::is_finished()` for each writer. A dead core or slow writer should mean shadow plus a stop request (status.jsonl is the supervisor's budget source); a dead chain or replay writer an event plus a counter.
  - Better still, move the stdout echo off the thread that writes status.jsonl.

### F3. Major: no WP-02 segment can be analysed with the merged toolkit

- **Location:**
  - `src/rec/mod.rs:116-142`: attempts, copies, bundles, outcomes, exec, triggers, predictions, … at `/1.1`;
  - `tools/arbx-report/arbx_report/streams.py:22-31`: `SUPPORTED_MAJORS` accepts only major 2 for attempts, bundles, outcomes, exec, triggers and predictions.
- **Problem.**
  - WP-02 labels the streams whose v2 data comes from later WPs as `1.1`, which is honest.
  - The toolkit (WP-10, merged) was written from MEASUREMENT, which calls them v2, so it refuses `/1.x` with a header.
  - Every shadow segment writes `triggers` (state triggers are on), so `arbx-report segment` fails on every WP-02 segment, including the field-acceptance run.
  - R0 `quality` completes but marks the run "Incomplete".
- **Proof.** `python3 tools/arbx-report segment <seg>` on a segment with one `triggers.000.jsonl.zst` raises `SchemaError: … arbx.triggers/1.x is not supported (known majors: [2])`.
- **Fix.**
  - A WP-10 follow-up: accept major 1 with a header for these streams and route each file to `legacy.py`'s mapping.
  - The `outcomes` rename of `failed_fees_lamports` (F14) must be mapped there too.
  - Land it before, or together with, WP-02, so that the owner's 20-minute field run can be reported.
  - WP-02's merge note should name the dependency.

### F4. Minor: status.jsonl and the core files are created lazily, which breaks the supervisor's "did this segment send?" test, and a hard kill now loses up to `flush_ms` of attempts

- **Location:**
  - `src/rec/writer.rs:80`: a stream's file is opened at its first record;
  - `writer.rs:91` and `:182-199`: compressed bytes appear only when a frame ends (≤ `flush_ms`);
  - `deploy/run-w.sh:139-151`.
- **Problem.**
  - run-w.sh decides that a segment may have sent when an `attempts*` file of size > 0 exists, or when the segment ran `--live` and status.jsonl exists. Its comment reads: "the engine creates it before anything can be sent".
  - At HEAD `Engine::new` created status.jsonl, and every attempt line was flushed at once.
  - Now status.jsonl appears with the first status line (about 10 s after the engine starts), and `attempts.000.jsonl.zst` stays at 0 bytes until its first frame ends.
  - A `--live` segment that is SIGKILLed or OOM-killed (run-w.sh itself sends SIGKILL after `ARBX_STOP_KILL_S`), or that aborts within that window after sending, is counted as "sent nothing" with 0 spent, instead of "unknown" (records only).
  - Separately, on any hard kill the last ≤ 1 s of attempts, copies, bundles and outcomes is lost (HEAD flushed per line). Stage 0 sends bundles only, so the money at risk is small, but the documented invariant is broken.
- **Fix.**
  - Open the plain streams, with their headers, when the recorder starts.
  - Have the core writer end its frame whenever its queue is empty (the core rate is a few records per second, so tiny frames cost nothing), or give core a short `flush_ms`.
  - Update the run-w.sh comment.

### F5. Minor: the disk ladder cannot recover, so any crossing is a shadow and stop 30-40 s later, and a run that starts below `min_free_gb` boots only to stop

- **Location:** `src/rec/disk.rs:47-55`; MEASUREMENT §1.4/§1.6.
- **Problem.**
  - The bot never deletes data. The run directory only grows, and free space only falls.
  - So once either limit is crossed it stays crossed, and steps 1-3 (archive off, rivals off, keyframes 4×) only delay step 4 by 10 s each.
  - On this host (18 GB free, below the 25 GB default floor) a real shadow run stopped with `disk_budget` 40.1 s after start, having written 37 KB. A manual `arbx run` on a small host never runs longer than 40 s, and only events.jsonl says why.
  - The supervisor refuses such starts. The binary itself does not.
- **Fix.**
  - Use soft thresholds for steps 1-3 (e.g. 90% of the budget, or `min_free_gb` + 5 GB) and the hard limit for step 4.
  - Or escalate only while the projected time to the hard limit is shorter than the segment's remaining time.
  - Refuse to start below `min_free_gb`, with a clear error.
  - Correct "Actions run in order" in MEASUREMENT if the design stays literal.

### F6. Minor: on a main-thread panic, stop.json is written before the recorder is closed (MEASUREMENT §1.6 says otherwise)

- **Location:** `src/main.rs:736-739` (`RecGuard`), `control.rs:269-271` (the hook writes stop.json first), MEASUREMENT §1.6 first paragraph.
- **Problem.**
  - The panic hook runs before unwinding, so stop.json and its run.log line are written while the writers are still draining. `RecGuard` closes the recorder later.
  - The data is still drained, so this is mostly a documentation error.
  - If a writer hangs (a stuck disk), `close()` joins with no timeout and the unwinding never finishes. That is still better than HEAD, which had no close at all.
- **Fix.** Correct §1.6. Consider a bounded `close()` (join with a timeout, then record `close_timeout` in the manifest).

### F7. Minor: the always-run isolation test is looser than the plan, and by the implementer's own account it cannot see a blocked hot worker

- **Location:** `tests/runtime_isolation.rs:16-19`, `:169`, `:197-203`.
- **Problem.**
  - The plan allows 10%. The test allows max(10%, 5 µs). Against a 9-13 µs baseline that is 40-55%.
  - The implementer reports that this metric "did not reliably catch a 20 ms parse on one of the two hot workers". With tokio's non-stealable LIFO slot, a blocked worker can still stall the real state-stream task.
  - The structural checks (`hot_violations` unchanged, every 5 MB reply parsed in the blocking pool) are good. They do not cover work that bypasses `Rpc` (F8).
- **Fix.**
  - Keep the structural checks.
  - Add a direct stall check: a 1 ms ticker task on rt_hot whose maximum lateness must stay under, e.g., 2 ms during the load, or tokio's poll-time histogram.
  - Make the owner's `strict_10_percent` run on Cherry part of the field acceptance.

### F8. Minor: the TPU send path still makes RPC calls, and parses multi-MB replies, on rt_hot outside `Rpc`

- **Location:** `src/send/tpu.rs:91-120` (`rpc`, `refresh_nodes`, `refresh_leaders` through its own `reqwest::Client`) and `:189-190` (refreshed every 50 slots and every 5 min inside the send-path task).
- **Problem.**
  - Invariant 5 and plan item 1 say rt_bg runs every RPC call. `getClusterNodes` returns a multi-MB JSON, parsed with `.json().await` on an `arbx-hot` worker.
  - `check_not_hot` does not see it, because it does not go through `Rpc`.
  - `tpu-direct` is disabled in `arbx-stage0.toml`, so this is latent. WP-08 owns `send/tpu.rs`.
- **Fix.** Record it in WP-08's scope: the leader book on rt_bg through a bound `Rpc`. Until then, or now, wrap `refresh_*` in a `bg.spawn`.

### F9. Minor: the engine benchmark measures only the cheapest emit path

- **Location:** `src/engine.rs:1500-1557` (`min_profit_lamports: u64::MAX / 4` at :1520).
- **Problem.**
  - No opportunity is ever priced, so with the recorder on the only records are `moves`, one closure per transaction.
  - Triggers, opportunities, caps, predictions and arrivals, which build a `serde_json::Value` with base58 strings on the engine thread and emit it, are not in the measured p99.
  - The acceptance passes, but the benchmark does not show what it claims to show: the engine with the recorder on.
- **Fix.** Add a variant in which about 1% of updates open a gap above `min_profit` (an opportunity, caps and a decided state trigger are emitted), and compare on and off.

### F10. Minor: "typed records, no JSON or base58 on producer threads" is only partly true, and MEASUREMENT §1.6 states it as done

- **Location:** every `rec.json(…, json!({ … b58(…) … }))` call:
  - engine.rs triggers, opportunities, predictions, arrivals, caps, rivals;
  - exec.rs attempts, outcomes, sims;
  - grpc.rs `rec_exec`;
  - send/mod.rs keepalive.
- **Problem.**
  - Plan item 2 says "Records are typed structs. No JSON is formatted on producer threads for hot and chain streams". MEASUREMENT §1.6 says "base58, number formatting and serialization happen there [on the writer]".
  - For `Record::Json` records, the `Value` tree, its `String` keys and every base58 string are built on the engine, hot or feed thread. Only the final serialization moved.
  - Closures (moves, txarr, poh, slots-feed, bundles, alts-final) do move the work. This is still better than HEAD, which also serialized and wrote on the caller's thread.
- **Fix.** Correct §1.6 now. Convert the per-trigger and per-transaction streams (triggers, arrivals, rivals, exec, predictions) to closures or `#[derive(Serialize)]` structs holding raw `Pk`/`[u8; 64]`, so that base58 happens on the writer. That can be a WP-03 follow-up.

### F11. Minor: per-transaction PoH records cost one boxed closure and one channel send each, on the feed task

- **Location:** `src/feeds/mod.rs:250-256`. Compare `feeds/shred.rs:277-285`, which batches per data set.
- **Problem.**
  - At HEAD, poh.log was written only when exec was on (`poh_log_on = exec_on`). Now it is always on.
  - Each non-vote transaction of an entries message costs about 0.5 µs on an rt_hot worker (emit p50 461 ns, partly cross-core cache traffic on the shared `depth` counter, which producer and writer both update). At 1-3k transactions/s per entries feed that is 0.5-1.5 ms/s of hot-runtime CPU.
- **Fix.** Batch one record per entries message, as shred.rs does. Optionally shard or pad the queue depth counter, e.g. by counting only on the producer side and having the writer publish what it has consumed.

### F12. Minor: the migrated writers have no tests, and neither do the failure modes

- **Problem.** Nothing exercises the following through the recorder:
  - `feeds::forward`'s poh v2 line, slots-feed's 13 columns and `poh_complete`, and the `entries-<feed>` frame layout (`u64 slot | u64 t | u32 len | bytes`, which must stay v1-compatible);
  - `shred.rs` `entry_idx`;
  - `rec_exec`, bundles (the closure that builds `code`), copies and keepalive.
  There are also no tests for F1 (I/O errors) or F2 (writer death).
- **Fix.** Add a recorder-backed test per migrated writer (decode the file and check the columns), plus the two failure tests.

### F13. Minor: re-using a segment directory now truncates the earlier run's core files

- **Location:** `src/rec/writer.rs:88-92` (`File::create` for compressed streams).
- **Problem.**
  - At HEAD, attempts, outcomes, copies, bundles, keepalive and sims were opened in append mode.
  - Now `arbx run --name X` run twice in one `out_dir` replaces `attempts.000.jsonl.zst` and the other compressed core files, silently. The plain files are appended to with no separating header.
  - The supervisor always uses fresh names; a manual run may not.
- **Fix.** Refuse a non-empty segment directory, or a directory that has a `meta.json`, before the recorder starts.

### F14. Minor: the field rename in `outcomes` `/1.1` breaks the legacy mapping the toolkit will apply

- **Location:** `src/exec.rs` `on_settled` (`failed_fees_total_lamports`, `failed_fees_delta_lamports`); `tools/arbx-report/arbx_report/legacy.py:119` (`failed_fees_lamports_running: o.get("failed_fees_lamports")`).
- **Problem.**
  - MEASUREMENT §7 documents the rename, and the plan asked for it.
  - Once F3's follow-up routes `/1.1` files to `legacy.py`, this field reads null for every WP-02 outcome.
- **Fix.** Map both names in the F3 follow-up.

### F15. Minor: records emitted while `close()` runs can be accepted and then neither written nor counted

- **Location:** `src/rec/mod.rs:337-359` (`push` checks `closed`, then sends) and `writer.rs:29-33` (drains with `try_recv`, then exits).
- **Problem.**
  - A producer that passed the `closed` check before `close()` set it, but sends after the writer finished draining, leaves a message in a channel nobody reads. `push` returned true, and the record is not counted as `late`.
  - At shutdown the runtimes are stopped before `close()`, but the raw-feed threads (poh) and anything still emitting are not.
  - Not reproduced in 200 rounds with 4 producers: theoretical.
- **Fix.** After the drain loop, have the writer keep draining until the depth counter is 0, or count the records left in the channel as `late` when the writer exits.

### F16. Minor: the writer has no per-file encoder state or rotation hook, which WP-03's binary formats need

- **Location:** `src/rec/writer.rs` `rotate`/`open`; MEASUREMENT §1.3 ("binary streams restart their dictionaries and keyframes per file").
- **Problem.**
  - `accounts.bin` (per-file `acct_id` dictionary, keyframes) must restart at each rotation.
  - Encoders run as closures with no knowledge of `file_seq` or rotation, and the producer cannot know when the writer rotates.
  - If WP-03 builds the dictionary on the producer side, files will not decode on their own.
- **Fix.** Add, in WP-02 or as the first thing in WP-03, a per-stream encoder trait object owned by the writer with an `on_new_file(file_seq)` hook.

### F17. Minor: replay queues are bounded in records, not bytes

- **Location:** `queue_accounts` 1,048,576 and `queue_journal` 524,288 (config.rs; MEASUREMENT §1.2).
- **Problem.**
  - A stalled replay writer can hold 1M account records. DLMM bin arrays are about 10 KB, so the queue can grow to GBs of RSS before the first drop: an OOM kill of a live process instead of a GAP mark.
  - The same applies, to a lesser degree, to the 262,144-record core and chain queues holding `serde_json::Value` trees.
- **Fix.** Add a byte budget per queue (sum of payload lengths; drop over it), and record it in the manifest. This is a plan-level gap, best fixed before WP-03 starts emitting account data.

### Nits

- **N1.** MEASUREMENT.md line 3 still says "revision 2.1" in the status, while the same paragraph describes revision 2.2.
- **N2.** events.jsonl's header `started_ns` (the time the file was opened) can be later than its first event's `t_ns`. Records are stamped when made; files open on the first write. Harmless, but surprising to a reader.
- **N3.** `pools.rs:119` (`eprintln!` "pools: dropped … transfer fee") is a run-path diagnostic not mirrored to events.jsonl (plan item 8).
- **N4.** `[record] disk_budget_gb = 0` passes validation (config.rs:770 checks `v < 0`), although the message says "must be a positive number". With 0 the ladder stops every segment within 40 s. `writer_cpus` is not validated.
- **N5.**
  - `runtime::hot_violations()` reaches only one run.log line at the end of the run; it should also be in status `health` or resources.jsonl.
  - The A.6 events `feed_disconnect` / `state_stream_reconnect` are not emitted. feedhealth has 10 s resolution, while PLAN-ADDENDUM I-2 wants Haan outages visible.
  - `simcheck` and `senders --raw` close their recorder only on success (main.rs:463, :540): a `?` error loses the unflushed tail.

---

## What is good

- The queue, drop and GAP logic is careful:
  - the depth counter is rolled back on overflow and on a disconnected send;
  - lost sequence numbers are merged into ranges;
  - `recorder_drop` events are rate-limited without a lock.
- The core-drop shadow is sticky and evented, and the tests cover it.
- Frames end at every flush, with the content size set. The torn-tail reader is tested.
- The rpc binding is simple and covers every `Rpc` call, including clients derived with `only`. The structural isolation checks (no hot violation, large parses in rt_bg's blocking pool) are the right guarantee.
- status.jsonl v2 matches §4.8 and §2.2. The supervisor's reader (`money.failed_fees_total_lamports`, last line only) works with it unchanged.
- Engine-thread file I/O is gone: signer-stats are written atomically on the slow writer, and run.log through the queue.

---

## Disposition

**Date:** 2026-10-04. All three major findings are fixed, with tests, and so are thirteen of the fourteen minor findings and three of the five nits; the rest are assigned to named WPs below. The fixes are in the WP-02 commit.

**Verification after the fixes** (`CARGO_TARGET_DIR` on /tmp, `CARGO_BUILD_JOBS=8`):
- `cargo build --release`: passes with the same 3 warnings as HEAD (`Check`'s dead fields, two irrefutable `if let` in main.rs).
- `cargo test --release`: **167 passed, 0 failed, 2 ignored**. That is lib 144 (+1 ignored), bin 9, legacy_fixtures 4, meta_config_hash 1, runtime_isolation 2 (+1 ignored), stop_path 6 and supervisor 1 (tools/test-run-w.sh: 91 of 91 checks).
- Ignored tests, run directly:
  - `emit_p99_under_1us_at_100k_per_s`: p50 461 ns, p99 631 ns.
  - `strict_10_percent`: arrival→dequeue p99 13.6 µs idle and 13.7 µs loaded; dequeue→t_sent 9.1 / 8.9 µs; longest rt_hot busy stretch 0 ns in both.
- `tools/arbx-report`: 77 unittest cases pass (4 skipped, as before). `python3 tools/arbx-report segment` reads this review's `rev02-seg` and two fresh shadow segments; the only "Incomplete" notes are for streams that later WPs add.
- Real shadow runs of the binary against public RPC, with a dead state stream:
  - (a) Free space between the soft and hard floors: the three soft steps came at 10, 20 and 30 s, and the run ended at its 45 s deadline with exit 0.
  - (b) stdout and stderr on `/dev/full`: the run ended at its deadline with exit 0. status.jsonl was written, no writer died, and nothing panicked.

| Finding | Disposition |
|---|---|
| **F1** (major) write and open errors swallowed | **Fixed.** A record now counts as written (`records_total`, a file's `records`) only once its frame or line is on disk. Errors are counted per stream: `io_errors` (failed opens, compressions and writes) and `io_lost` (the records they lost). Both appear in manifest.json (`io_errors_total`, `io_lost_total`) and in status `recorder`. A core stream's I/O error is a core loss: sticky shadow `core_record_loss` and a `gate_change` event. Failing to write or open status.jsonl, or a dropped status line, stops the segment with reason `error`; the run.log line for it is written directly, with a `recorder_fatal` event and a stderr line. Every I/O error is also a `recorder_io_error` event (the first, then at most one a second per stream; none for events.jsonl itself). A frame cut short is truncated back to the last complete frame (`set_len` + seek), so the frames after it stay readable. A file that failed to open is retried at most once a second, with its header first. Tests: `write_errors_are_losses_never_records` (attempts and triggers on `/dev/full`, the reviewer's probe), `a_status_write_error_stops_the_segment` (status.jsonl on `/dev/full`, and a directory in its place), `a_file_that_could_not_be_opened_is_tried_again`. |
| **F2** (major) dead writers unnoticed; stdout panics kill the slow writer | **Fixed.** stdout and stderr echoes now go through their own thread (`arbx-rec-echo`) and a bounded queue of 4,096 lines, with write errors ignored. A full queue counts the line (`echo_dropped`) and never waits, so a failing or blocked stdout no longer stops or stalls the slow writer. Every record's encoding, and every `Record::Task`, runs under `catch_unwind`: a panic loses only that record, counted as `encode_errors` (on a core stream it is a core loss). A panic anywhere else in a writer is caught by the thread's own guard, which closes the files as far as it can and calls `writer_died`. The monitor also checks every second for a writer thread that has finished, and for a writer with records queued that has made no progress for 60 s (a hung disk). A dead or stalled core or slow writer stops the segment (reason `error`; a core one is a core loss first). For chain, replay and bulk writers this is an event only (`recorder_writer_dead`, `recorder_writer_stalled`), and their records count as dropped from then on. `end_run`'s `Error:` line and the post-close `say` no longer panic on a failing stderr or stdout. Tests: `an_encoder_that_panics_loses_its_record_only`, `a_dead_writer_is_noticed` (chain, slow, core), `a_stalled_core_writer_stops_the_segment`, `a_failing_or_blocked_stdout_stops_nothing` (a sink that fails, and one that blocks forever). |
| **F3** (major) the toolkit cannot read WP-02 segments | **Fixed in this commit** (a WP-10 follow-up, landed with WP-02 as the review asked). `streams.SUPPORTED_MAJORS` now accepts major 1 for attempts, bundles, outcomes, exec, triggers and predictions; unknown majors are still refused. `model.Segment.v1(stream)` routes each file at major 1 (with or without a header) through `legacy.py`, per stream, even in a v2 segment: attempts, outcomes, bundles, exec, the copies fallback, and R8's predictions. Test: `tools/arbx-report/tests/test_wp02.py`. It builds a WP-02-shaped segment (meta v2, status v2, the six streams at `/1.1` built from the w5h-p1 legacy fixture) and checks the mapping, a full `runner.segment` with no `unsupported_schema`, and that major 3 is still refused. It fails against HEAD's toolkit. MEASUREMENT §1.6 is updated. |
| F4 lazy files; up to 1 s of attempts lost on a hard kill | **Fixed.** The plain streams (events, feedhealth, resources, keepalive, run.log) are created with their headers when the recorder starts, stamped with its start time (this also fixes N2). status.jsonl is created by `Rec::open_now(STATUS)` right before the engine starts; a run that cannot create it does not start. The core writer ends its frames whenever its queue is empty, so a taken attempt, copy, bundle or outcome reaches the disk within milliseconds. deploy/run-w.sh `spent` skips status.jsonl's header line and its comment now describes WP-02. Tests: `plain_files_at_start_and_core_records_at_once` (a core record on disk with `flush_ms` = 10 min); tools/test-run-w.sh scenario P4. |
| F5 the disk ladder cannot recover | **Fixed.** The ladder now has two stages. Past a soft limit (90% of `disk_budget_gb`, or free space under `min_free_gb` / 0.9), steps 1-3 run one per check. Past a hard limit (the budget, or `min_free_gb`), shadow-and-stop runs at once. A segment between the two limits runs on. `arbx run` refuses to start under `min_free_gb` (`rec::start` with the monitor); simcheck and senders are not affected. MEASUREMENT §1.4 and §1.6 are updated. Tests: `the_disk_ladder_runs_in_order` (rewritten), `a_hard_limit_stops_at_once_and_a_run_refuses_to_start_under_the_floor`; tests/meta_config_hash.rs runs its copy of the stage-0 config with `min_free_gb = 0` (its temporary directory may hold less than 25 GB). |
| F6 stop.json before close on a panic; unbounded close | **Fixed.** MEASUREMENT §1.6 now states the order: on an error or a stop the recorder closes before stop.json; on a main-thread panic it closes after, because the hook writes stop.json at once. `close()` waits at most 20 s; a writer still busy then is named in manifest `close_timeout`. Test: `close_is_bounded`. |
| F7 isolation test too loose and blind to a blocked hot worker | **Fixed, differently.** The suggested 1 ms ticker was tried and does not work. With a 5 MB parse on rt_hot, its lateness stayed at about 1.1 ms, because tokio moves the timer tasks to the free worker. The test now runs a stall probe instead: a thread reads each rt_hot worker's `worker_total_busy_duration` (a stable metric) every 500 µs. Busy time that grew by more than the wall time between two reads was one uninterrupted stretch of work. The always-run test requires the loaded phases' longest stretch to stay within 2 ms of the idle phases' (1 ms in the strict test). A new always-run negative control, `the_stall_check_sees_a_parse_on_rt_hot`, puts the same 5 MB parse on rt_hot and sees stretches of 23-33 ms in every loaded phase; with the bound client the stretches are 0. The 10%-or-5 µs latency tolerance is unchanged; the owner's `strict_10_percent` run on Cherry stays part of the field acceptance. |
| F8 TPU leader-book RPC on rt_hot | **Partly fixed; the rest belongs to WP-08.** Replies over 256 KiB (`getClusterNodes`) are now parsed in `spawn_blocking`, off the hot workers. The HTTP calls themselves still run on rt_hot outside `Rpc`; WP-08, which owns `send/tpu.rs`, moves the leader book to rt_bg through a bound `Rpc`. tpu-direct is disabled in stage 0. |
| F9 the engine benchmark covers only moves | **Fixed.** A second variant moves one pool 10% off its pair every 200th transaction, with `min_profit` 0.1 SOL and caps on. About 1% of updates (500 of 50k) then open an opportunity, and their caps and opportunities records are made on the engine thread. The variant ends its opportunities outside the timed part. Measured: best p99 1,482 ns off and 1,934 ns on (within 5 µs). The moves-only variant measured 1,192 / 1,283 ns. |
| F10 "no JSON or base58 on producer threads" overstated | **Doc fixed; the code change is assigned to WP-03.** MEASUREMENT §1.6 now says which streams are closures encoded on the writer and which are `Value` trees built by the producer and only serialized on the writer. Converting the per-trigger and per-transaction streams to typed records or closures is assigned to WP-03, which reworks those producers. |
| F11 a PoH record per transaction | **Fixed.** `Record::enc_lines(n, f)` puts several lines in one queue slot and counts them as n records. feeds::forward emits one record per entries message, and shred.rs (which already batched per data set) now counts lines. Test: `multi_line_records_count_their_lines`. The shared depth counter is unchanged; emit p99 stayed at 631 ns. |
| F12 migrated writers untested | **Fixed** for poh.log (both entries and raw feeds), slots-feed.log, the entries archive frames, exec.jsonl (`rec_exec`), bundles.jsonl and copies.jsonl. Tests: `an_entries_feed_records_poh_slots_and_its_archive`, `poh_positions_are_recorded_with_their_entry_index`, `rec_exec_writes_the_v1_exec_line`, `bundle_results_are_recorded`, `fired_copies_are_recorded`. The failure tests are listed under F1 and F2. keepalive.jsonl, a one-line `Value` from the keep-alive loop, has no recorder-backed test. |
| F13 a re-used segment directory is overwritten | **Fixed.** `arbx run` refuses a segment directory that already holds files, before it writes anything there. |
| F14 renamed outcome field | **Fixed** in `legacy.outcome`: `failed_fees_lamports_running` reads `failed_fees_lamports`, then `failed_fees_total_lamports`, and `failed_fees_delta_lamports` is carried. Tested in test_wp02.py. |
| F15 records accepted during `close()` | **Fixed.** A send that fails because the writer has ended after the close counts as `late`, not as a drop. A writer counts as `late` the messages left after its final drain. What a queue still counts once its writers have finished is reported as `queues.<q>.lost_at_close`, so every record taken is accounted for. |
| F16 no per-file encoder hook | **Fixed.** `rec::FileState` (`on_new_file(file_seq, out)`) is owned by the stream's writer and installed with `Rec::set_file_state`. The hook runs right after each file's header; its output is part of the file's preamble and is sent again if the first frame fails. `Record::stateful::<T>` records are encoded against it. Test: `per_file_state_restarts_with_each_file` (a dictionary across rotations; every file decodes on its own). |
| F17 replay queues bounded in records only | **Fixed.** `[record] queue_max_mb` (1,024 MiB) is a byte cap on each bounded queue. It counts the payload producers declare: `Record::Bin`, `Record::Line`, and `Rec::emit_sized` closures such as the entries archive. Past the cap a record drops as from a full queue (replay: a GAP follows). Byte caps and high-water marks are reported in manifest `queues` and resources `recorder_queues`. Test: `a_queue_byte_cap_drops_past_it`. WP-03's account and journal records must be `Bin` or sized. |
| N1 | Fixed: MEASUREMENT's status line says revision 2.2. |
| N2 | Fixed by F4: events.jsonl's header is stamped with the recorder's start, before any event (tested). |
| N3 `pools.rs:119` only on stderr | **Open, assigned to WP-04.** `pools::boot` has no recorder handle and runs before the engine; the line stays in `.out`. WP-04 reworks the pool registry. |
| N4 `disk_budget_gb = 0` accepted; `writer_cpus` unchecked | Fixed: `disk_budget_gb`, `rotate_mb` and `queue_max_mb` must be > 0, `min_free_gb` >= 0, and `writer_cpus` < 1024. Tested in `record_and_runtime_keys`. |
| N5 | Partly fixed: `hot_violations` is in resources.jsonl (`runtimes.hot.rpc_violations_total`), and simcheck and `senders --raw` close their recorder on an error too (`RecGuard`). **Open, assigned to WP-03:** the A.6 events `feed_disconnect` and `state_stream_reconnect`, which belong with WP-03's feed rework. |

**Deviations and assumptions.**
- The toolkit change (F3, F14) is WP-10 code landed in the WP-02 commit, as the review asked.
- The supervisor's "did this segment send?" test still treats status.jsonl as the engine-start marker. The file is therefore opened at the engine's start, not at the recorder's start like the other plain streams.
- `arbx run` now refuses to start under `min_free_gb`. A smoke run on a small development host needs a lower `min_free_gb` in its config, and the error says so.
- Assumed defaults:
  - the soft limits are 90% of the budget and `min_free_gb` / 0.9;
  - the stall limit is 60 s;
  - the close wait is 20 s;
  - the echo queue holds 4,096 lines;
  - the queue byte cap is 1 GiB per bounded queue.

**Still open, for later WPs.**
- WP-03:
  - typed or closure records for triggers, arrivals, rivals, exec and predictions (F10);
  - the feed connect and disconnect events (N5);
  - its account and journal records must declare their sizes for the byte cap (F17) and use `FileState` for per-file dictionaries (F16).
- WP-04: `pools.rs` diagnostics into events (N3).
- WP-08: the TPU leader book on rt_bg through a bound `Rpc` (F8).
- Owner field acceptance:
  - the 20-minute shadow run, reported with `tools/arbx-report`;
  - `strict_10_percent` on Cherry;
  - the `strace` check of the engine thread.

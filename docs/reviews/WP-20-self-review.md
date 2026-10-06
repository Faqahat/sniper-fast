# WP-20 self-review: alerts (Telegram) and watchdog

**Date:** 2026-10-05. **Lane:** `lane/wp-20`. **Spec:** docs/PLAN-ADDENDUM.md WP-20, with the coordinator's wording requirements: the Stage-1 plan review's F12, and docs/STAGE1-PLAN.md §1 "What you will see".

The first pass built the lane and was reviewed twice (its own findings, then an independent adversarial read). Network outages stopped it before its tests were confirmed. The **final pass** (next section) built and tested the lane, checked the owner-facing wording, and reviewed four risks again: blocking paths, token leaks, panics in the sender, and the watchdog's lock and grace. Its fixes are in the commit "WP-20: final fixes: …".

## Final pass (2026-10-05)

### Verification

| Check | Result |
|---|---|
| `cargo build --release` (`CARGO_BUILD_JOBS=2`) | passes; the 2 warnings are master's (`main.rs`, an irrefutable `if let`, at the lane's base 76d3eea) |
| `cargo test --release`, at ee86691 (before this pass) | 429 passed, 0 failed, 4 ignored (lib 397 + 3 ignored, bin 13, alerts_cli 4, legacy_fixtures 4, meta_config_hash 1, replay_cli 1, runtime_isolation 2 + 1 ignored, stop_path 6, supervisor 1) |
| `cargo test --release`, after this pass | 432 passed, 0 failed, 4 ignored (lib 400 + 3 ignored, bin 13, alerts_cli 4, legacy_fixtures 4, meta_config_hash 1, replay_cli 1, runtime_isolation 2 + 1 ignored, stop_path 6, supervisor 1; no doc-tests): the 429 above plus the 3 new unit tests; the same 2 warnings |
| WP-20's own tests | 33 unit tests (27 in `src/alerts/tests.rs`, 6 in `src/watchdog.rs`; 3 new: `owner_wording_rules`, `wp07_notices`, `the_gate_watcher_tells_every_change`) and 4 CLI tests (`tests/alerts_cli.rs`); `control::gate_modes` covers the gate's new change count |
| Toolkit (`tools/arbx-report/tests`, `python3 -m unittest discover -s .`) | 84 OK, 4 skipped |
| `arbx check` | exit 0 on `deploy/arbx-stage0.toml` and `deploy/arb.toml`; both print the `alerts:` and `watchdog:` lines |
| `tools/secret-scan.py` | 1,331 blobs: 2 findings, both allowlisted test keystores; no bot token (the tests build their fake token at run time) |
| `WP-20-exec-hooks.patch` | applies to this lane's `src/exec.rs` (master's at the lane's base 76d3eea); applied, `cargo check --lib` passes against the final alerts API. Master has changed `src/exec.rs` since (WP-09, 3ad7c53; master at 172eb56): there a plain `git apply` fails, and `git apply -3` merges with no conflict (simulated with `git merge-file`: master's file plus exactly the patch's lines, every name they use present; not compiled against master). `git apply -3` onto a copy of lane/wp-07's `src/exec.rs` leaves 3 keep-both conflicts (Merge hooks below) |

No test reaches the network or sends a Telegram message: a fake Bot API on 127.0.0.1 answers, and the CLI tests clear the environment.

### The owner-facing wording (the coordinator's rules)

| Rule | How it reads now | Test |
|---|---|---|
| The daily summary's win ratio = wins ÷ bundles **sent** (`exec.sent_total`), no fallback to attempts, "no sends" when 0, always beside wins, sends, the net from chain data, and the fees, tips and rent | `win ratio 1.2% (12 wins / 1,003 sent) · net +0.0031 SOL (ledger)` / `fees 0.005015 · tips 0.0012 · rent 0.0000 SOL` / `budget left 0.0290 SOL · segments 24 · crashes 1`. With nothing sent: `win ratio: no sends (0 wins / 0 sent) · net …`. Under 1% it keeps two decimals (`0.30%`; the old bot's range is 0.29–0.56%). `attempts_total` and would-sends are never read as sends. The net names its source (`ledger`, or `wallet records` with `≥` while a round trip is unknown); an estimated rent shows `≈` | `owner_wording_rules`, `snapshot_reads_each_generation_of_the_status_line` |
| A win alert says "succeeded" and the realised net from chain data; never "profitable"; a gain only when the net after fee, tip and rent is > 0 | 💰 `succeeded · net +0.001145 SOL`; ➖ `succeeded · net 0 SOL: no profit after fee, tip, rent`; 🔻 `succeeded but lost: net -0.00036884 SOL after fee, tip, rent` (Warning); ✅ `succeeded · net not known yet` (a second message brings the net). The word "profitable" is never used | `owner_wording_rules` (all four cases), `message_formatting_escapes_and_fits` |
| Short and readable on a phone | every message is a header line, a title and at most four lines (a win: route · mint / `size · gross · tip · fee · rent` / `slot · solscan`); an error or detail quoted from a record is cut at 300 characters; `owner_wording_rules` holds a win and the daily summary to six or seven lines of at most 90 characters | `owner_wording_rules` |

### Findings of this pass, and their fixes

| # | Sev. | Area | Finding | Fix | Test |
|---|---|---|---|---|---|
| F1 | major | money wording | The daily summary's ledger net was `money.trade_net_total`. MEASUREMENT §4.42 defines `trade_net` as `trade_gross − fee − tip`, so the "net after fees, tips and rent" left out the non-recoverable rent and could read too high | `trade_net_total − rent_nonrecoverable_total` | `snapshot_reads_each_generation_of_the_status_line` |
| F2 | major | merge (WP-07) | lane/wp-07 moves WP-05's money counters under `money.bot` once its ledger owns `money`. The summaries read `money.tips_paid_total_lamports`, `fees_landed_total_lamports` and `failed_fees_cap_now_lamports` only, so after the merge the daily summary and the heartbeat would have said fees 0 and tips 0 (zeros, not "unknown") and lost the budget | The ledger's `tips_total` and `fees_win_total + fees_fail_total` come first, then `money.<name>`, then `money.bot.<name>`. Budget left is WP-07's `money.budget_left_now` (the test budget) when the line has it, else the failed-fee cap minus the failed fees | `snapshot_reads_each_generation_of_the_status_line` (a line shaped as lane/wp-07 writes it) |
| F3 | minor | wording | The daily line read `win ratio = wins ÷ bundles sent: 1.2% (12 wins / 1,003 sent)` with the net on its own line, and `no sends (0 wins)` | The requested form (table above), `1 win`, the rent with its unit | `owner_wording_rules` |
| F4 | minor | wording | A landing whose net was exactly 0 read "succeeded but lost" (Warning) | `succeeded · net 0 SOL: no profit after fee, tip, rent` (Info) | `owner_wording_rules` |
| F5 | minor | blocking | The SendGate watcher (rt_bg, niced +5) took the gate's mutex every second. The engine takes the same mutex on every send decision (`Exec::inputs` → `gate.reason()`). A watcher preempted while holding it would stall the engine for a scheduler slice: a priority inversion | `SendGate::changes()`, a lock-free count of the gate's changes; the watcher reads the gate (under its lock) only after the count moves | `control::gate_modes`, `the_gate_watcher_tells_every_change` |
| F6 | minor | secrets | Free-text event fields went into messages unscrubbed: a stop's `detail` (it quotes the state stream's last error), the recorder's details and I/O error, `chainfetch_dead.why`, `recon_miss`. A provider's URL with a key in it would have reached the chat. (The bot token itself was never at risk: `strip_token` runs on every message) | `rpc::scrub` (URLs cut to the host, key parameters masked) on every free-text field `classify` shows | `events_classify_into_alerts` (12 event shapes carrying a keyed URL) |
| F7 | minor | watchdog lock | The lock file kept the pid after the watchdog ended, so the documented `kill $(cat runs/.watchdog.lock)` could signal an unrelated process that reused the pid | The file is emptied on exit, still under the lock (`Drop for Lock`). The stop command is `flock -n runs/.watchdog.lock true \|\| kill $(cat runs/.watchdog.lock)`: it signals only while a watchdog holds the lock | `the_lock_is_single_instance`, `the_watchdog_once_and_its_lock` (CLI) |
| F8 | minor | merge (WP-07) | lane/wp-07 adds the safety stops `equity_hour`, `equity_floor` and `token_floor` (exit 20). Their stop messages would have been Error, and a `token_floor` gate change a Warning | Every exit-20 stop is Critical; so is a `token_floor` gate change | `lifecycle_messages`, `events_classify_into_alerts` |
| F9 | minor | merge (WP-07) | WP-07 hands its money and lifecycle events to `notify::notify` (15 kinds) and also writes `recon_miss` to events.jsonl, which the recorder's tap classified. Wired as the first pass planned, a reconciliation miss would have been told twice, and the merge would have had to invent the mapping | `alerts::notice` / `notice_alert`: WP-07's level and text, key `<kind>:<subject>`, an icon per kind, never deduplicated (WP-07 raises each once). The tap no longer classifies `recon_miss` or WP-07's other money kinds | `wp07_notices`, `events_classify_into_alerts` |
| F10 | hardening | panics | The lamport sums of a net (`Win::net_lamports`, `Snapshot::of`, a period's totals) wrapped in release and panicked in a debug build on absurd inputs | i128, clamped to i64; saturating sums | `owner_wording_rules`, `snapshot_reads_each_generation_of_the_status_line` |
| F11 | merge | patch | `WP-20-exec-hooks.patch` had no blob ids, so it could not 3-way merge onto lane/wp-07's changed `src/exec.rs` | Regenerated with full blob ids (the base blob 87ba41c is in the repo): `git apply -3` works before or after WP-07 | applied and `cargo check`ed here; 3-way applied to a copy of WP-07's file |
| F12 | nit | wording | `in 0.5000` (the trade's size) read like a time on a phone | `size 0.5000` | rendered in `owner_wording_rules` |

### The four review questions

**1. Can the alert sink block the engine or the hot path?** No, after F5. Every path a producer takes:
- `Alerts::raise` (the engine thread, rt_hot tasks, the recorder's tap, the executor's settlement once wired, WP-07's notices once wired):
  - a level check;
  - `try_spin` on the dedup lock (at most 64 `try_lock`s with a spin hint; still taken, the alert passes undeduplicated);
  - a crossbeam `try_send`. It is lock-free here: the sender only ever `try_recv`s, so no receiver waits and no waker lock is taken.
  - A full queue: one counter, and at most one `alert_dropped` event a second.
- The recorder's tap: `classify` matches the kind and builds an alert for the listed kinds only; scrubbing is a pure function.
- `note_stream_error` (feed and state-stream tasks): `try_spin` on the storm map.
- `alerts::status()` (the engine's status line): atomics and one `try_lock`.
- The gate watcher: lock-free while the gate does not change (F5).
- The monitor (rt_bg): its file reads in `spawn_blocking`; `rpc::Registry::totals` is touched only by rt_bg calls.
- The sender (rt_bg): its locks (`work`, `rate`, `ctx`, the chat; the dedup lock only while a transition is held, and to prune) are never taken by the engine or rt_hot, and never held across an `.await`.
- The ends:
  - `flush` (≤ 4 s) runs on the main thread after the engine returned;
  - `on_exit` (≤ 5.25 s) runs after stop.json;
  - the main-thread panic hook (≤ 3.25 s) runs on a thread that is ending anyway.

  Together they add at most about 9 s to a segment's exit. run-w.sh sends SIGINT at 60 s and SIGKILL at 180 s.

**2. Can the token leak?** No path found. Checked:
- The token lives only in `Creds` (its `Debug` prints `<redacted>`) and goes only into the request URL.
- reqwest errors are taken `without_url`, then `redact`ed: the token, its secret half and URL-encoded forms replaced, token shapes masked, URLs cut to the host. That covers status `last_error`, `alert_failed`, run.log, stdout and `deliver_now`'s errors.
- A Bot API description is redacted before it is cut.
- Every message text goes through `strip_token`.
- meta.json and the config dump hold only the variables' names. `token_env` / `chat_env` holding a value is refused without echoing it. A TOML parse error masks token shapes.
- `--env-file` errors never quote a line.
- The watchdog reads `/proc/<pid>/cmdline`, `fd` and `cwd`, never `environ`.
- `alert-test` and `notify` print only the variables' names.
- Tested: `the_token_never_appears_in_any_record_or_log` (every file of a segment-like run, the echoed lines, status, Debug, the config dump, every request body), `a_description_is_redacted_before_it_is_cut`, `redaction_removes_every_form_of_the_token`. F6 hardens the other secrets (providers' keys in URLs).

**3. Can the sender panic?** No path found:
- There is no `unwrap` or `expect` in non-test code.
- Slices are at ASCII positions (`mask_token_shapes`) or by characters (`cut`, `fit`, `short_key`).
- Sums are saturating or in i128 (F10).
- `Instant` arithmetic adds at most a clamped `retry_after` (≤ 3,600 s).
- serde_json reads index without panicking.
- The panic hook calls nothing that can panic and does nothing without installed alerts.
- If the sender task did panic, only that task would end: its guard marks it dead, `flush` stops waiting, and the run goes on without alerts.
- Residual: the exit and crash helper thread drops its runtime after its request. If a DNS lookup hangs, that drop waits on the blocking pool. The caller is still bounded by `recv_timeout`, and the thread ends with the process.

**4. The watchdog's single-instance lock and grace logic.**
- **The lock:**
  - `flock(LOCK_EX | LOCK_NB)` on `<runs_dir>/.watchdog.lock`. It is the same inode whatever the path's spelling, the file is opened close-on-exec, and the kernel releases the lock when the process dies, so it is never stale.
  - The pid is written only once the lock is held. A refused second watchdog reads the pid for its message and writes nothing.
  - The file is emptied at exit (F7).
  - `--once` takes no lock.
- **The grace:**
  - Each look that sees a segment process moves "last seen".
  - "NOT running" comes only when no segment process has been seen for more than `grace_s`, so a gap between segments within 120 s says nothing.
  - A status.jsonl older than `stale_s` (60 s; the engine writes every 10 s), or a boot without one beyond `boot_s` (600 s), is "NOT running" at once.
  - A reminder comes every `status_min` while down. "Back up" comes when a segment process is seen again (a booting one counts).
  - The clock starts at the watchdog's own start, so a watchdog started while nothing runs also waits `grace_s`.
  - A segment's exit (flush, runtimes, recorder, stop.json, the stop message: under about 20 s) stays far inside `stale_s`.
- **Edge cases (residual):**
  - A crash loop faster than the grace reads as running: run-w.sh retries after 10 s. Each crashed segment sends its own stop message (Error), and the supervisor's crash limit (more than 6 in 15 min) ends the campaign, after which the watchdog says "NOT running".
  - The watchdog uses the wall clock, as file mtimes do: a forward clock jump during a gap could make the gap look longer than `grace_s`.
  - Of two live segments, the fresh one decides (first pass, R13 d).

## What was built (first pass)

- **`src/alerts.rs`**, with `alerts/format.rs` (HTML escaping, message composition), `alerts/telegram.rs` (the Bot API call, redaction), `alerts/summary.rs` (status-line numbers, daily totals, markers) and `alerts/tests.rs`.
  - **The sink:** a bounded queue (1,024) fed by `try_send` only. A full queue drops the alert and counts it.
  - **One sender task on rt_bg:**
    - HTTPS `sendMessage` with parse_mode HTML;
    - at most `rate_per_min` (20) messages a minute and one a second;
    - bursts coalesced within `coalesce_ms` (a Critical alert goes at once);
    - a 429 retried after its `retry_after`; transport errors and 5xx after a backoff;
    - plain text when the API refuses the HTML; a moved group followed to its new chat id.
  - **Dedup** by key within `dedup_s`. Transition families (down/back) hold a suppressed change until its window ends.
  - **Status and events:** status.jsonl `alerts` counters, and `alert_sent`, `alert_failed`, `alert_dropped` events.
  - **Exit and crash:** the exit message and the crash alert are sent from their own thread, each with a bounded wait.
- **Sources of alerts:**
  - the recorder's event path (a tap in `Recorder::event`, mapped by `alerts::classify`);
  - a SendGate watcher (lock-free until the gate changes: final pass F5);
  - the gRPC streams' failed connections (`alerts::note_stream_error`: 503 and 429 storms);
  - a monitor of the segment's last status line: a stale blockhash, the failed-fee cap as the budget floor, a low balance, the RPC registry's 429 storms, the heartbeat and the daily summary;
  - the money API for WP-05 and WP-07 (`win`, `failed_landing`, `loss`, `budget_floor`, `low_balance`), and WP-07's notices (`notice`, final pass F9);
  - the segment's start and stop, and the panic hook.
- **`src/watchdog.rs`, `arbx watchdog`:** a single-instance lock and a /proc scan for `arbx… run` processes under the runs directory. Its state machine says "running", "NOT running" (after `grace_s` without a process, or a status.jsonl older than `stale_s`, or a boot longer than `boot_s`), "still NOT running" and "back up". It keeps a journal, `watchdog.jsonl`, and offers `--once`.
- **Other subcommands:** `arbx alert-test` (one test message) and `arbx notify --text` (an operator's note: a field test's goal and result, which the README now asks to post).
- **Config:**
  - `[alerts] enabled, token_env, chat_env, heartbeat_min, min_level, dedup_s, rate_per_min`, plus `coalesce_ms`, `daily_summary`, `low_balance_sol`;
  - `[watchdog] runs_dir, grace_s, status_min`, plus `stale_s`, `boot_s`, `poll_s`.

  Both deploy configs have the alerts on.
- **Docs:** MEASUREMENT revision 2.10 (§4.2, §4.6, §4.8, the new §4.51 "How alerts read" and §4.52 watchdog.jsonl (§4.50 is WP-09's replay outputs), A.6); the operator note in docs/field-tests/README.md.

## First pass: how the review was done

1. **Every lock in the new code, by the thread that takes it** (after the independent read's fixes).
   - Producers (the engine thread, rt_hot tasks, the recorder's event path, `Exec::finalize` once wired) only try locks, a few times without sleeping or a system call (`try_spin`): the dedup state (one lock for keys and families), the storm counters; `status_json` tries `last_error` once.
   - Producers never wake the sender. It looks every `tick` (250 ms), so no producer takes tokio's waker lock, which a niced rt_bg thread could hold.
   - The sender (rt_bg) takes the dedup lock only while a transition is held, and to prune it once a minute, so a producer almost never finds it taken. Its other locks (`work`, `rate`, `ctx`, the chat) are short and never held across an `.await`.
   - The exit, crash, alert-test and notify paths use `lock_briefly`, which gives up after about 50 ms (a dying thread may hold a lock). They never run on a runtime worker.
   - Lock order: no lock is taken while another is held, except `ctx` inside `work` (the sender's compose). Nothing takes `work` inside `ctx`.
2. **Every `unwrap`, `expect`, index, slice and arithmetic step in non-test code.**
   - There is no `unwrap` or `expect`.
   - Slices: `mask_token_shapes` slices at ASCII positions only; `cut` and `fit` work in characters.
   - Arithmetic: every subtraction on counters saturates; durations use `saturating_*` and `checked_sub`; `1 << (attempt - 1).min(5)` cannot overflow.
3. **Every use of the token.** It is held in `Creds` (whose `Debug` prints `<redacted>`). It is used only to build the request URL, in `telegram::post`. Every text that leaves the module goes through `redact` (errors, logs, events, status) or `strip_token` (message texts).
4. **The tests that pin each property** (no test reaches the network: a fake Bot API on 127.0.0.1 answers each one) are listed with the findings below.
5. **An independent adversarial read** of the same code by a second agent (read-only), whose findings and dispositions are in their own section below.

## First pass: findings (mine) and their fixes

Finding 2's daily line was reworded by the final pass (F3), and its ledger net corrected (F1).

| # | Sev. | Area | Finding | Fix | Test |
|---|---|---|---|---|---|
| 1 | major | token | A message text could carry the bot's own token. `rpc::scrub` only cuts text after `http`, so a `/bot<token>/…` path without a scheme (an error that echoes the URL path) survived into an alert body. Also, `mask_token_shapes` refused a match preceded by letters, so `bot<token>` was not masked | `telegram::strip_token` on every message text before it is sent (the sender and the exit path); `mask_token_shapes` accepts the `bot` prefix | `the_token_never_appears_in_any_record_or_log` now also checks every request body; `redaction_removes_every_form_of_the_token` |
| 2 | major | wording (coordinator, STAGE1-PLAN §1) | The daily ratio's denominator fell back to `exec.attempts_total`, which counts would-sends | `exec.sent_total` only; `no sends` when it is missing or 0; the line reads `win ratio = wins ÷ bundles sent:` beside the wins and the sends; the net names its source (`ledger` or `wallet records`), and the bot-counter net fallback is gone (a net is chain-derived or `?`) | `snapshot_reads_each_generation_of_the_status_line`, `message_formatting_escapes_and_fits`, `daily_totals_and_markers` |
| 3 | major | wording (F12) | A landing was called a "WIN", and the net left out the rent of accounts the transaction created | The win alert says `succeeded · net …` (gross − tip − fee − rent); a net ≤ 0 reads `succeeded but lost` (Warning); the summaries subtract the rent of new token accounts from WP-05's net (an estimate, `≈`, until WP-07's ledger) | `message_formatting_escapes_and_fits`, `snapshot_reads_each_generation_of_the_status_line` |
| 4 | minor | sender | A header-only message could go out. The sender checks the batch under one lock and composes under a second; the crash path (`take_undelivered` from the panic hook) can empty the batch between the two | Nothing is sent when the composed message holds no alert | by inspection (a race with the panic hook) |
| 5 | minor | sender | Alerts left behind by a full message waited another coalesce window | A burst keeps its start, so the leftovers go next, at the rate | `rate_limit_caps_messages_in_the_window` |
| 6 | minor | flush | `sender_alive` stayed true when the runtime dropped the task before its first poll (the guard was made inside the task), so `flush` waited its whole bound | The guard is made outside the task and moved into it | `the_sink_never_blocks_when_full` (`flush` on no sender returns at once) |
| 7 | minor | counters | `pending_now` / `queued_now` could wrap below 0 when the exit path takes alerts the sender had counted | Saturating decrements | by inspection (`lifecycle_messages` runs the exit path) |
| 8 | minor | memory | A reference cycle: recorder → tap → `Alerts` → recorder | The tap holds a `Weak` | — |
| 9 | minor | wrong alert | WP-05's `exec.stopped = "canary count reached"` would have been called a budget floor | Only a fee or spend cap is the budget floor; a canary's count is an Info `sending stopped` | `monitor_checks_the_status_line` |
| 10 | hardening | HTTP | The client followed redirects, and used the environment's proxy even for the loopback test base | No redirect is followed (the API never redirects); no proxy for a loopback base. In production, HTTPS keeps the token inside the encrypted path through any proxy | the fake-server tests run without the environment's proxy |
| 11 | test | watchdog | The grace counts from the last sighting of a segment process; the first version of the test assumed it counted from when the process disappeared | The test observes the process just before each gap. §4.52 says "no segment process has been seen for more than `grace_s`" | `running_not_running_back_up` |

## First pass: independent read (second agent) and dispositions

A second agent read the code adversarially, read-only, for blocking paths, token leaks and panics. It found no deadlock, no panic path, and no token in Debug output, meta.json, status, events or the bot's own error paths. Its findings and what was done:

| # | Sev. | Finding | Disposition |
|---|---|---|---|
| R1 | major | **A crash could go unreported.** The crash post ignored the sender's rate (a burst had used the minute's 20) and did not retry a 429. It had already drained the queue, so those alerts were lost too, and the exit then skipped the stop message because a crash alert had been "sent" | **Fixed.** The rate state is shared by the sender and the exit and crash paths (its window and a 429's block), and they wait for it when the wait fits their bound. A 429's `retry_after` is honoured once when it fits. What a now-send cannot deliver is put back at the front of the batch, so a crash alert that did not go out is sent by the exit with everything else. Test: `a_crash_that_could_not_be_sent_goes_with_the_exit` (a 5xx, then a 429 with `retry_after` 1) |
| R2 | minor | **Dedup state could be lost under contention.** A producer's `try_lock` on the families could fail while the sender's per-tick release held it, so a later change was neither suppressed correctly nor held (the "last word" promise broken), and the dedup test could flake | **Fixed.** One lock covers keys and families. The sender takes it only while a change is held (`held_now`) and once a minute to prune, and producers spin a few tries before passing an alert through. `dedup_suppresses_repeats_and_counts_them` cannot meet contention now |
| R3 | minor | `alert-test` and `notify` failed with `min_level` above info: `deliver_now` filtered by level | **Fixed.** `deliver_now` sends what it is given, and only the exit's stop message is filtered. Test: `min_level_does_not_stop_the_operators_messages` |
| R4 | minor | **A pasted value could pass the name check.** (a) The check accepted a token's secret half without `-`. (b) An unquoted pasted token makes TOML's parse error quote the line | **Fixed.** (a) A name must be upper-case letters, digits and `_`, so a mixed-case secret never passes; tested in `alerts_config_checks`. (b) `Config::parse` masks token shapes in TOML errors |
| R5 | minor | An API description was cut before it was redacted, so a cut through the token left a piece shorter than the shape mask | **Fixed.** Redact first, then cut. A stream error in a storm alert is redacted with the token too. Test: `a_description_is_redacted_before_it_is_cut` (the token straddling character 300 at five offsets) |
| R6 | minor | False "stale blockhash: none" for a segment without a blockhash source | **Fixed.** "None at all" is a fault only in a segment that sends (live, canary); otherwise only "stale" or "none after there was one". Tested in `monitor_checks_the_status_line` |
| R7 | minor | The daily summary missed crashes of boots that failed before any status line | **Fixed.** Crashes come from stop.json alone. Tested in `daily_totals_and_markers` |
| R8 | minor (spec) | The heartbeat never fired with segments shorter than `heartbeat_min`, because a segment's start reset its clock | **Fixed.** The clock is no longer reset. The heartbeat carries the last period's numbers summed over every segment of the runs directory, plus the current segment's gate and state. Tested in `daily_totals_and_markers` |
| R9 | minor | The rate-limit test's 100 ms margin could flake under load | **Fixed.** A 3 s window and a 2.5 s bound |
| R10 | nit | Two brief waits: `notify_one` takes tokio's waker lock, which a niced rt_bg thread could hold; `lock_briefly` sleeps inside async code | **Fixed.** No producer wakes the sender (it polls every `tick`). `lock_briefly` is used only on the exit and crash paths; async code takes short locks plainly or tries them |
| R11 | nit | `proc_start_ns` overflowed after about 5.8 years of uptime | **Fixed:** u128 |
| R12 | nit | At a crash, the exit path could take the message the sender was posting, which double-counted it | **Fixed** for the counts: a `gen` counter tells the sender the message was taken over, and the sender then counts nothing for it. A duplicate message stays possible (residual, below) |
| R13 | nits | (a) The "503" class matches tonic's `Unavailable` for any connect, DNS or TLS failure. (b) The exit note claimed events.jsonl held every alert. (c) The money calls built their alert while the alerts were off. (d) A fresh segment masks a hung one in the watchdog | (a) Named `unavailable (503)` and documented. (b) The note is gone: undelivered alerts are put back, and those lost at exit are `failed_total`. (c) The calls check `enabled` first. (d) Residual: two live segments are themselves anomalous (the supervisor runs one; Haan serves one) |

## Residual risks (by decision, not fixed)

- **Two processes, one chat.** A segment and the watchdog each keep `rate_per_min` (20). In a storm the two could together exceed Telegram's 20 a minute per group; the API then answers 429, and both honour `retry_after`.
- **Volume of lifecycle messages.** Each segment sends a start and a stop message. With 20-minute segments that is six messages an hour, plus the heartbeat and the watchdog's hourly "running": about 8 routine messages an hour. The spec lists both. If the group finds them noisy, a follow-up can add an `[alerts]` switch for routine stops (deadline), or send Info-only messages with Telegram's `disable_notification` so the phone stays silent for them.
- **A duplicate at a crash.** When the panic hook takes the message the sender is posting at that moment, it may be posted twice. A loss is worse than a duplicate. The counts are not doubled (R12).
- **Latency.** No producer wakes the sender, so an alert can wait up to 250 ms (`tick`) before it is looked at. Coalescing holds it 2 s anyway.
- **Two live segments.** The watchdog judges by the fresh one, so a hung second process is not reported (R13 d).
- **The default panic hook's text.** It still prints a panic's raw message to the segment's `.out`. Nothing in the alerts panics with a URL in its message (reqwest does not put URLs in panics), and control.rs's hook scrubs URLs from stop.json and run.log.
- **The watchdog needs to read other processes' `/proc/<pid>/cmdline`.** It runs as root on Cherry. Under `hidepid` as another user it would see no segment and say "NOT running".
- **Estimates.** Until WP-07's ledger, the rent in a net is `new_token_accounts_total × 1,513,840` lamports in the summaries (marked `≈`), and `atas × 1,513,840` in a win alert from WP-05's hook (until the hook takes the ledger's exact rent: merge item 2). That is the larger of an SPL account's 1,488,440 lamports and a Token-2022 account's 1,513,840 (PLAN-ADDENDUM go-live gate), so a net is never overstated; at worst a net within 25,400 lamports above 0 reads as a loss. Stage 0 creates no accounts (`[live] max_new_token_accounts = 0`), and WP-06's create+close leaves no rent locked.
- **The normalized config hash.** It changes for every config, because the new sections are part of the normalized JSON. Field-test entries that pinned a normalized hash name the build they ran.
- **WP-07's `trade_net`.** The alerts take the ledger's net as `trade_net_total − rent_nonrecoverable_total` (MEASUREMENT §4.42 as it stands). If WP-07's review makes `trade_net` include that rent, drop the subtraction in `Snapshot::of`.
- **One money stop, up to three Critical messages.** For WP-07's equity stops these are the SendGate change, WP-07's notice and the stop message. The merge may drop the gate alert for the supervisor's rule reasons (merge item 6).
- **The watchdog does not restart itself** after a reboot or a kill (it is started by hand, as the owner rule wants only the binary on Cherry). The segments' own heartbeat keeps coming meanwhile.

## Merge hooks (exact wiring)

### WP-05 (`src/exec.rs`; not edited in this lane)

1. **Apply the hooks:** `git apply -3 docs/reviews/WP-20-exec-hooks.patch`.
   - On master's `src/exec.rs` it merges with no conflict. Since WP-09 changed that file (master 172eb56), only the 3-way apply works: a plain `git apply` fails.
   - After WP-07 it leaves three conflicts. Keep both sides of each:
     - `struct Final` gets `route: String` and keeps WP-07's `fin`;
     - in `Exec::finalize`, after `self.add(counted, o.mint);`, keep WP-07's `note_landed` line, then WP-20's money-alert block;
     - `self.finals.insert(o.attempt, Final { route: o.route.clone(), …, cooled: o.cooled, fin })`.

   What the patch does (`Open.route` is set where the attempt opens):
   - `finalize`, for `self.mode.sends()`: `landed_ok` → `alerts::win(Win { … })`; `landed_fail` → `alerts::failed_landing(FailedLanding { … })`.
   - `amend`: a landing found late is told; a success whose round trip only the wallet record brings is told again, with its net.
   - `sender_state`: `alerts::budget_floor(BudgetFloor { what: "failed_fee_cap", … })`, once.

   Every call is a `try_send`: nothing on the engine thread waits.
2. **Optional, after WP-07:** when `landed.ledger` is an object, pass its exact `rent_nonrecoverable` as the win's `rent_lamports` instead of the estimate `counted.atas × ATA_RENT_LAMPORTS`.

### WP-07 (lane/wp-07: `src/notify.rs` with `Notice`, `Level`, `set_hook`, `notify`; the ledger; the in-process supervisor; `arbx campaign`)

3. **In `arbx run`** (`src/main.rs` `run`), right after `alerts::install(alerter.clone());`:

   ```rust
   arbx::notify::set_hook(|n| {
       let level = match n.level { arbx::notify::Level::Info => alerts::Level::Info, arbx::notify::Level::Warn => alerts::Level::Warning,
           arbx::notify::Level::Error => alerts::Level::Error, arbx::notify::Level::Critical => alerts::Level::Critical };
       alerts::notice(level, n.kind, &n.subject, &n.text);
   });
   ```

   `alerts::notice` covers all 15 kinds: `equity_floor`, `equity_hour`, `equity_day`, `token_floor`, `recon_miss`, `low_native_sol`, `stranded_token`, `equity_unknown`, `campaign_start`, `equity_start`, `segment_end`, `segment_not_sending`, `segment_start_failed`, `campaign_shadow`, `campaign_end`.
   - It never waits.
   - It is never deduplicated: WP-07 raises each once.
   - The recorder's tap no longer classifies `recon_miss` or WP-07's other money kinds, so nothing is told twice. `recon_miss` therefore depends on this hook.
4. **In `arbx campaign`** (`src/campaign.rs`, its own process), after any detach or fork (a tokio runtime does not survive a fork):
   - `let (a, notes) = alerts::Alerts::new(&cfg.alerts, &alerts::env_var, alerts::Ctx { label: <campaign name>, runs_dir: Some(<runs>), started_ns: now, ..Default::default() });`
   - `alerts::install(a.clone()); alerts::install_panic_hook();`
   - a 1-worker tokio runtime and `a.start(rt.handle(), <a stop flag>)`;
   - the hook as in item 3;
   - at its end `a.flush(alerts::FLUSH_WAIT); let _ = a.deliver_now(Vec::new(), alerts::EXIT_WAIT);`. Not `alerts::on_exit`: WP-07's `campaign_end` already tells the end.

   The campaign's `segment_end` notices (crash or safety class only) overlap the segment's own stop message. Keep both: a SIGKILLed segment sends none.
5. **`deploy/arbx-canary-frz.toml`** (new in WP-07) has no `[alerts]` section, and `enabled` defaults to false. Unless it gets one, **the frz canary, the first live-money test, runs with no alerts**.
   - Copy `[alerts]` and `[watchdog]` from `deploy/arbx-stage0.toml` into it.
   - Add it to `deploy_configs_turn_alerts_on`.
6. **Optional, to avoid duplicates:** on an equity stop the owner gets the SendGate change ("SendGate shadow: equity_floor"), WP-07's notice and the stop message, all Critical. With the hook installed, `gate_alert` may return None for the supervisor's rule reasons (`equity_floor`, `equity_hour`, `equity_day`, `token_floor`, `reconcile_miss`).
7. **Status names:** nothing to do. `Snapshot::of` already reads WP-07's `money` (`trade_net_total`, `rent_nonrecoverable_total`, `tips_total`, `fees_win_total`, `fees_fail_total`, `budget_left_now`, `equity_liquid_now`) and WP-05's counters under `money.bot` (final pass F2). `exec.sent_total`, `ok_total` and `stopped` are unchanged in lane/wp-07.
8. **`alerts::loss`, `alerts::budget_floor`, `alerts::low_balance`:** no extra calls are needed.
   - Every landed win already gets a win alert that says "succeeded but lost" when its net is below 0.
   - The equity floors and `low_native_sol` come as notices (item 3).
   - The monitor reads `money.equity_liquid_now` against `[alerts] low_balance_sol` (0, off, by default).
9. **Textual conflicts to expect** (simulated by merging this lane's tree and lane/wp-07's uncommitted tree into master in a scratch clone):
   - Keep both sides in:
     - `src/main.rs` (the `use arbx::{…}` list; WP-20's `Watchdog`, `AlertTest`, `Notify` arms beside WP-07's `Campaign` ones);
     - `src/config.rs` (`Config`'s `alerts`, `watchdog` beside `ledger`, `supervisor`);
     - `deploy/arb.toml` and `deploy/arbx-stage0.toml` (appended sections);
     - `docs/MEASUREMENT.md` (the revision line, §4.6, §4.8, A.6).
   - `src/control.rs` merges cleanly: WP-07 changes `StopReason`, this lane `SendGate`.
   - lane/wp-07's other conflicts (`src/engine.rs`, `src/feeds/mod.rs` journal kind 12, `src/exec.rs`, `src/exec/tests.rs`) are with master's WP-09, not with WP-20.

## Running on Cherry

The token and the chat id come from `/root/arbx/deploy/.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, mode 600), loaded from beside the config. The bot must be a member of the "ArbX" group.

```
cd /root/arbx
bin/arbx-<hash> alert-test --config deploy/<cfg>.toml       # one test message; prints "ok: …" or "failed: <why>" (never the token or chat id); exit 0 / 1
setsid nohup bin/arbx-<hash> watchdog --config deploy/<cfg>.toml >> runs/watchdog.out 2>&1 < /dev/null &
bin/arbx-<hash> watchdog --config deploy/<cfg>.toml --once  # one look, JSON, sends nothing, takes no lock; exit 0 running, 1 not
flock -n runs/.watchdog.lock true || kill $(cat runs/.watchdog.lock)   # stop it (SIGTERM: "watchdog stopped", exit 0)
```

Its journal is `runs/watchdog.jsonl`. For a new binary, stop the old watchdog and start the new one.

## Tests

No test reaches the network: a fake Bot API on 127.0.0.1 answers, and every CLI test clears the environment, so there is no token. Test names are in `src/alerts/tests.rs`, `src/watchdog.rs`, `src/control.rs` and `tests/alerts_cli.rs`.

| Property | Test |
|---|---|
| rate limit | `rate_limit_caps_messages_in_the_window` |
| coalescing | `bursts_coalesce_into_one_message` |
| dedup and held transitions | `dedup_suppresses_repeats_and_counts_them`, `held_transition_is_sent_when_its_window_ends` |
| retries | `retries_honour_retry_after_and_count_failures`: 429 `retry_after`, 5xx, plain-text fallback, moved group, dropped connection |
| the sink never blocks | `the_sink_never_blocks_when_full`: a full queue, a stuck sender, a held dedup lock; `the_gate_watcher_tells_every_change` and `control::gate_modes` (the watcher reads the gate only after a change) |
| the token in no record or log | `the_token_never_appears_in_any_record_or_log`, `a_description_is_redacted_before_it_is_cut`, `redaction_removes_every_form_of_the_token`; other secrets: `events_classify_into_alerts` |
| the panic hook sends | `the_panic_hook_sends` (a child process), `a_crash_that_could_not_be_sent_goes_with_the_exit` |
| the watchdog's state machine | `running_not_running_back_up`, `nothing_running_at_start` |
| the watchdog on a fake runs directory, its lock | `finds_a_fake_segment_in_a_runs_directory` (a /proc scan of a fake segment process), `the_lock_is_single_instance`, `the_watchdog_once_and_its_lock` (CLI) |
| message formatting | `message_formatting_escapes_and_fits` (HTML escaping of mint names, routes and labels; links; limits) |
| the owner's wording | `owner_wording_rules` (the win ratio's form and denominator, "no sends", the four win cases, phone-sized messages, no overflow) |
| WP-07's notices | `wp07_notices` |
| config | `alerts_config_checks`, `watchdog_config_checks`, `deploy_configs_turn_alerts_on`, `check_names_the_alerts_and_the_watchdog` (CLI) |
| never fatal | `missing_env_disables_with_one_warning`, `a_run_without_the_variables_warns_once_and_goes_on` (CLI) |
| status-line numbers and summaries | `snapshot_reads_each_generation_of_the_status_line` (WP-02, WP-05 and WP-07 lines), `daily_totals_and_markers`, `monitor_checks_the_status_line`, `stream_storms_from_failed_connections`, `lifecycle_messages`, `events_classify_into_alerts`, `an_operator_note`, `min_level_does_not_stop_the_operators_messages` |

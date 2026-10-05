# WP-20 self-review: alerts (Telegram) and watchdog

**Date:** 2026-10-05. **Lane:** `lane/wp-20`. **Spec:** docs/PLAN-ADDENDUM.md WP-20, with the coordinator's wording requirements: the Stage-1 plan review's F12, and docs/STAGE1-PLAN.md §1 "What you will see".

## What was built

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
  - a SendGate watcher;
  - the gRPC streams' failed connections (`alerts::note_stream_error`: 503 and 429 storms);
  - a monitor of the segment's last status line: a stale blockhash, the failed-fee cap as the budget floor, a low balance, the RPC registry's 429 storms, the heartbeat and the daily summary;
  - the money API for WP-05 and WP-07 (`win`, `failed_landing`, `loss`, `budget_floor`, `low_balance`);
  - the segment's start and stop, and the panic hook.
- **`src/watchdog.rs`, `arbx watchdog`:** a single-instance lock and a /proc scan for `arbx… run` processes under the runs directory. Its state machine says "running", "NOT running" (after `grace_s` without a process, or a status.jsonl older than `stale_s`, or a boot longer than `boot_s`), "still NOT running" and "back up". It keeps a journal, `watchdog.jsonl`, and offers `--once`.
- **Other subcommands:** `arbx alert-test` (one test message) and `arbx notify --text` (an operator's note: a field test's goal and result, which the README now asks to post).
- **Config:**
  - `[alerts] enabled, token_env, chat_env, heartbeat_min, min_level, dedup_s, rate_per_min`, plus `coalesce_ms`, `daily_summary`, `low_balance_sol`;
  - `[watchdog] runs_dir, grace_s, status_min`, plus `stale_s`, `boot_s`, `poll_s`.

  Both deploy configs have the alerts on.
- **Docs:** MEASUREMENT revision 2.10 (§4.2, §4.6, §4.8, the new §4.51 "How alerts read" and §4.52 watchdog.jsonl (§4.50 is WP-09's replay outputs), A.6); the operator note in docs/field-tests/README.md.

## How the review was done

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

## Findings (mine) and their fixes

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

## Independent read (second agent) and dispositions

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
- **Volume of lifecycle messages.** Each segment sends a start and a stop message. With 20-minute segments that is six messages an hour, plus the heartbeat and the watchdog's hourly "running". The spec lists both. A `[alerts]` switch for routine stops (deadline) is a possible follow-up if the group finds them noisy.
- **A duplicate at a crash.** When the panic hook takes the message the sender is posting at that moment, it may be posted twice. A loss is worse than a duplicate. The counts are not doubled (R12).
- **Latency.** No producer wakes the sender, so an alert can wait up to 250 ms (`tick`) before it is looked at. Coalescing holds it 2 s anyway.
- **Two live segments.** The watchdog judges by the fresh one, so a hung second process is not reported (R13 d).
- **The default panic hook's text.** It still prints a panic's raw message to the segment's `.out`. Nothing in the alerts panics with a URL in its message (reqwest does not put URLs in panics), and control.rs's hook scrubs URLs from stop.json and run.log.
- **The watchdog needs to read other processes' `/proc/<pid>/cmdline`.** It runs as root on Cherry. Under `hidepid` as another user it would see no segment and say "NOT running".
- **Estimates.** Until WP-07's ledger, the rent in a net is `new_token_accounts_total × 1,513,840` lamports (an estimate, marked `≈`). That is the larger of an SPL account's 1,488,440 lamports and a Token-2022 account's 1,513,840 (PLAN-ADDENDUM go-live gate), so the net is never overstated. New accounts come only through WP-06's create+close, which leaves no rent locked.
- **The normalized config hash.** It changes for every config, because the new sections are part of the normalized JSON. Field-test entries that pinned a normalized hash name the build they ran.

## Merge hooks

### WP-05 (`src/exec.rs`; not edited in this lane)

The exact code is in [WP-20-exec-hooks.patch](WP-20-exec-hooks.patch). It applies with `git apply docs/reviews/WP-20-exec-hooks.patch` to WP-05's `src/exec.rs`, which is the same on master today. It type-checks: it was applied in a scratch copy, and a deliberately wrong field fails the same check.

1. `struct Open` gets `route: String`, set where the attempt is opened (`self.open.insert(attempt, Open { … })` in the send path) to `format!("{:?}>{:?}", r.buy.venue, r.sell.venue)`. `struct Final` gets `route: String`, copied in `finalize`.
2. `Exec::finalize`, right after `self.add(counted, o.mint);`, for `self.mode.sends()` only:
   - `landed_ok` → `crate::alerts::win(Win { route, mint, size_lamports: o.size, gross_lamports: (counted.rt_unknown == 0).then_some(counted.round_trip), tip_lamports: counted.tip, fee_lamports: counted.fee, rent_lamports: counted.atas × ATA_RENT_LAMPORTS, slot, signature: o.sig58, attempt })`. The rent is what the transaction left locked: once WP-06's create+close lands, pass 0 for those, or the exact lamports from the wallet record;
   - `landed_fail` → `crate::alerts::failed_landing(FailedLanding { …, fee_lamports: counted.failed_fee, error: "custom 0x… <proglog::meaning>" })`.
3. `Exec::amend`, right after `self.add(counted, f.mint);`:
   - a landing found after a final that said not landed is told as `win` or `failed_landing`;
   - a success whose round trip only the wallet record brings (the expiry check found it first, so its first message said `net not known yet`) is told again, now with its net.
4. `Exec::sender_state`, where `self.stopped` becomes the failed-fee or spend cap: `crate::alerts::budget_floor(BudgetFloor { what: "failed_fee_cap", value_lamports: spent + reserved, floor_lamports: cap_failed_fees, … })`, once. Without this hook the monitor still raises the same alert from the status line's `exec.stopped` within about 15 s, under the same dedup key.

Every call is a `try_send` into the alerts' queue: nothing on the engine thread waits.

### WP-07 (the ledger)

1. `alerts::loss(Loss { … })` for a trade whose ledger net, after fees, tips and rent, is below 0.
2. `alerts::budget_floor(BudgetFloor { what: "equity_floor" | "equity_hour", value_lamports, floor_lamports, detail })` where the campaign-wide equity stops trip. The SendGate change itself is already alerted at Critical by the gate watcher, for any reason containing `equity`, `budget`, `recon` or `fee_cap`.
3. The low balance: either `alerts::low_balance(LowBalance { … })` from the balance snapshots, or nothing at all. The monitor already reads status `money.equity_liquid_now` against `[alerts] low_balance_sol`.
4. The names the alerts read from status.jsonl are MEASUREMENT §4.8's `money.trade_net_total`, `money.rent_nonrecoverable_total` and `money.equity_liquid_now`. If WP-07 names them otherwise, update `src/alerts/summary.rs` (`Snapshot::of`). The `recon_miss` event is already an Error alert.

## Running the watchdog on Cherry

```
cd /root/arbx && setsid nohup bin/arbx-<hash> watchdog --config deploy/<cfg>.toml >> runs/watchdog.out 2>&1 < /dev/null &
bin/arbx-<hash> watchdog --config deploy/<cfg>.toml --once        # one look, JSON, sends nothing
kill $(cat runs/.watchdog.lock)                                    # stop it (SIGTERM: "watchdog stopped", exit 0)
```

The token and the chat id come from `/root/arbx/deploy/.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`). Check them with `bin/arbx-<hash> alert-test --config deploy/<cfg>.toml`.

## Tests

No test reaches the network: a fake Bot API on 127.0.0.1 answers, and every CLI test clears the environment, so there is no token. Test names are in `src/alerts/tests.rs`, `src/watchdog.rs` and `tests/alerts_cli.rs`.

| Property | Test |
|---|---|
| rate limit | `rate_limit_caps_messages_in_the_window` |
| coalescing | `bursts_coalesce_into_one_message` |
| dedup and held transitions | `dedup_suppresses_repeats_and_counts_them`, `held_transition_is_sent_when_its_window_ends` |
| retries | `retries_honour_retry_after_and_count_failures`: 429 `retry_after`, 5xx, plain-text fallback, moved group, dropped connection |
| the sink never blocks | `the_sink_never_blocks_when_full`: a full queue, a stuck sender, a held dedup lock |
| the token in no record or log | `the_token_never_appears_in_any_record_or_log`, `a_description_is_redacted_before_it_is_cut`, `redaction_removes_every_form_of_the_token` |
| the panic hook sends | `the_panic_hook_sends` (a child process), `a_crash_that_could_not_be_sent_goes_with_the_exit` |
| the watchdog's state machine | `running_not_running_back_up`, `nothing_running_at_start` |
| the watchdog on a fake runs directory | `finds_a_fake_segment_in_a_runs_directory` (a /proc scan of a fake segment process), `the_lock_is_single_instance`, `the_watchdog_once_and_its_lock` (CLI) |
| message formatting | `message_formatting_escapes_and_fits` (HTML escaping of mint names, routes and labels; links; limits; F12 wording) |
| config | `alerts_config_checks`, `watchdog_config_checks`, `deploy_configs_turn_alerts_on`, `check_names_the_alerts_and_the_watchdog` (CLI) |
| never fatal | `missing_env_disables_with_one_warning`, `a_run_without_the_variables_warns_once_and_goes_on` (CLI) |
| status-line numbers and summaries | `snapshot_reads_each_generation_of_the_status_line`, `daily_totals_and_markers`, `monitor_checks_the_status_line`, `stream_storms_from_failed_connections`, `lifecycle_messages`, `events_classify_into_alerts`, `an_operator_note`, `min_level_does_not_stop_the_operators_messages` |

Counts and the full suite are in the commit message.

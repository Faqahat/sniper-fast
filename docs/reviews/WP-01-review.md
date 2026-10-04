# WP-01 review: foundation (crate split, config hygiene, provenance, stop reasons, control, supervisor)

**Date:** 2026-10-04. **Reviewer:** adversarial review of the uncommitted WP-01 working tree on master (HEAD `b4d94a3`).
- **Files reviewed:** the `git diff` of `Cargo.toml`, `Cargo.lock`, `deploy/arb.toml`, `deploy/arbx-stage0.toml`, `docs/MEASUREMENT.md`, `src/config.rs`, `src/engine.rs`, `src/exec.rs` and `src/main.rs`; the staged rename `deploy/arb-w-live.toml` → `deploy/legacy/`; and the new files `buildinfo.rs`, `src/lib.rs`, `src/control.rs`, `src/provenance.rs`, `deploy/run-w.sh`, `tools/test-run-w.sh`, `tests/stop_path.rs`, `tests/supervisor.rs` and `testdata/programs/`.
- **Not reviewed:** `program/arbx-sizing/`, `program/venue-harness/` and `.claude/`.
- **Checked against:** PLAN.md WP-01, MEASUREMENT.md §1.1, §4.1-§4.3, §4.7, §7 and A.5, and res-stops C1 and C7-C9.
- No code was changed.

**Verdict.**
- **No blockers.** Nothing new can send a live transaction. Every new path fails closed:
  - `--shadow`, or a run without `--live`/`--canary`, gives a sticky shadow SendGate;
  - a route-program hash that does not match, or cannot be read, gives a sticky shadow;
  - a stop request closes the gate for good.
- **Three major findings:**
  1. The new boot order widens the gap between the RPC account snapshot and the state stream's start. Every segment now starts with pool state that may be stale (F1).
  2. meta.json `config.normalized_sha256` is taken after the command-line overrides. It changes from segment to segment under the supervisor and differs from campaign.json's (F2).
  3. The supervisor's `.pause` can fail without saying so: it retries forever, spams `control.jsonl`, and never falls back (F3).
- There are also eleven minor findings and seven nits.

---

## Verification performed

| Check | Result |
|---|---|
| `cargo build --release` | Passes (incremental). 3 warnings, all already present at HEAD: `Check` has dead fields, and `nonces` has two irrefutable `if let`. No new warnings. The drop from 24 to 3 comes from making every module `pub` (N3) |
| `cargo test --release` | **115 passed**, 0 failed (lib 104, bin 5, `tests/stop_path.rs` 5, `tests/supervisor.rs` 1). By `#[test]` attribute: 83 at HEAD, 112 now. No test name from HEAD is missing |
| `tools/test-run-w.sh` run directly | 38 of 38 checks pass |
| Programdata ELF hash, recomputed independently in Python from `testdata/programs/8K8uyQDt-programdata.json` | Header: state 3, slot 451,798,124, authority present. ELF end 35,240. md5 `809315befcb9554211f8019bf9df290b`, sha256 `e4f03590…bae2f`, 0 non-zero bytes after the end. Matches the test and both configs |
| `arbx check` on `deploy/arbx-stage0.toml` and `deploy/arb.toml` | Both parse with every key known. `deploy/legacy/arb-w-live.toml` is refused with "config_version = 2 is required … arb-lab v1 config?" |
| Real shadow run against public RPC (scratch copy of the implementer's smoke config) | Deadline, exit 0. meta.json v2 complete. Route program `ok: true`. The 5 venue programs hash with `trailing_nonzero = 0`. The 6 programs took **504 ms** (run.log). `ctl status` works, while `ctl pause-sending` and `ctl shadow` are refused with "already shadow for the rest of the segment (mode_shadow)" (F3) |
| Real run, SIGTERM then SIGINT 50 ms later | stop.json: `reason signal`, `SIGTERM from pid … (zsh)`, `sender_uid`, `sender_cmdline` cut to 512 characters, exit 10, final status line `stop_reason: "signal"`. The socket was removed |
| Failed boots (no RPC env) with `--budget-left 1000000`, `--budget-left 99999999999`, `--no-record`, `--shadow`, none | Each leaves a partial meta.json and a stop.json with `reason error`, exit 30. `normalized_sha256` differs with the overrides (F2) |
| Supervisor in `ARBX_DRY=1` with the **real** binary and a shadow config, `.pause` touched mid-segment | 12 refused `pause-sending` lines in the segment's `control.jsonl` within 6 s (`ARBX_POLL_S=0.5`). Nothing in `supervisor.log` or the campaign's `control.jsonl` (F3) |
| Sending paths after a pause or stop | `Exec::wants_send` is the only gate (exec.rs:719-725). `Engine::after_opportunity` (engine.rs:761-767) and the deferred `confirm_wait` path both call it at decision time. Scheduled bundle resends and sim-gated fires do not re-check it; the shipped configs use neither (M10) |

## Conformance with PLAN WP-01

| Plan item | Status |
|---|---|
| 1. `src/lib.rs` with `pub mod`; main.rs as the CLI; `arb-lab` strings renamed | Done. Only comments and test text still say arb-lab |
| 2. `deny_unknown_fields` on the 14 structs, plus `ControlCfg` | Done and tested in every section, including `[[feed]]`, `[[send]]` and `[[rpc.endpoint]]` |
| 2. `config_version = 2` required; `load` returns the raw bytes | Done through `Config::load_raw`. An acceptable deviation |
| 2. `normalized_json`: defaults filled, keys sorted | Done, but meta.json hashes the overridden config (F2) |
| 2. Legacy config moved unchanged; arb.toml kept; stage0 is the campaign config | Done. The rename is staged and everything else is unstaged (N6) |
| 3. `build = "buildinfo.rs"`, the 7 `ARBX_*` values, rerun on src/, Cargo.lock, HEAD, the resolved ref, packed-refs and the index | Done and tested. The dirty hash is limited to the binary's files, a documented deviation. Watching the index costs rebuilds (N1) |
| 4. Binary sha256; config file hash, normalized hash and frozen copy; host, pid, uid, argv, clock | Done |
| 4. Programdata hash of the route and venue programs on the background runtime; a mismatch refuses live | Done on the **boot** runtime, which feeds F1. A mismatch, or a fetch error, makes the gate a sticky shadow instead of refusing to start. That is acceptable, but the supervisor never sees it (M2) |
| 4. meta.json → `arbx.meta/2.0` | Done. It breaks two existing tools (M9) |
| 5. signal-hook `WithOrigin`; StopReason in stop.json, run.log and the final status line; exit codes 0/10/20/30 | Done and tested through the real binary (`wait-signal`). A crash during the stop is reported as the operator stop (M5) |
| 6. Control socket mode 0600, `arbx ctl`, 5 commands, control.jsonl, SendGate read by `wants_send` | Done and tested |
| 7. `--shadow`, `--budget-left`, `--campaign-dir`, `arbx provenance` | Done. `--env-file` was added. `--shadow --canary` is accepted (M7) |
| 8. Supervisor: frozen binary and config, campaign.json, `--budget-left`, control files, classification, records-only `--shadow`, last-line budget, supervisor.jsonl, no zstd, passphrase mitigations | Done and dry-run tested. Pause robustness (F3), recording while paused (M1), budget fail-open hazards (M4) and concurrent campaigns (M6) remain |
| Offline acceptance: all 7 items | Met. The gate decisions inside `run()` have no test (M3) |
| Field acceptance | Not run (owner) |

---

## Findings

### F1. MAJOR: the boot reorder widens the gap between the account snapshot and the state stream, so segments start on stale pool state
- **Location:**
  - The snapshot is taken at `src/main.rs:724-736`.
  - Then come `provenance::fetch_programs` (:743), `send::Paths::new` (:781) and `exec::Exec::new` (:790), the meta.json build and write (:803-831), and `feeds::start` (:833).
  - Only then does `feeds::start_state` run (:835).
  - At HEAD, `start_state` ran right after the snapshot (HEAD main.rs:585 → :615), and Paths and Exec came after it (:619, :628).
- **Problem:**
  - The state stream (`grpc::accounts_once`, feeds/grpc.rs:361-401) is a Yellowstone account subscription. It delivers only the writes that happen after it subscribes; there is no initial snapshot.
  - The engine has no periodic resync. engine.rs:1060 fetches only accounts newly added to the watch list.
  - Every pool write between the RPC snapshot and the subscription is therefore lost. Each affected pool stays at its pre-write state until its next write: a phantom price gap. This is the failure class WP-00 and WP-04 exist to remove (W §4, W §7.1).
  - The plan did not ask for this reorder. It asked only that meta.json be written before the feeds start.
- **Proof:**
  - At HEAD the gap was roughly the interest build plus the gRPC connect: run.log shows "state stream follows" and "feeds:" 0-5 ms after "interest" in w5h-p1, w5h2-p1, w5h2-p5 and w5h3-p2.
  - The new order puts four steps inside the gap:
    - the program fetch: 504 ms against public RPC in my run, as 12 sequential `getMultipleAccounts` calls of up to 2.2 MB each (~5.8 MB of ELF);
    - send paths: 7-303 ms in the same arb-lab run.logs;
    - Exec::new: ~990 ms in every one of them (lookup tables, wallet token accounts for ~1,000 mints paced at 120 ms per 100, nonces);
    - hashing the seed CSV and registry for meta.json.
  - That is about 1.5-2 s in a normal boot.
  - Under the stage-0 RPC conditions it is much more. Haan returned 429 on 20-26% of calls and Shyft timed out at 3 s (w5h run.logs). `Rpc::call` failover allows 3 s per provider, `Rpc::one` backs off 429s up to 7 times, and `fetch_programs` tries each account 3 times with 500 ms sleeps. Tens of seconds are possible.
  - At the measured 31-60 watched transactions/s, a 2 s gap loses about 60-120 transactions' writes across dozens of pools, in every segment.
- **Fix (any one):**
  - Start `feeds::start_state` right after the snapshot, as at HEAD. It is not one of the `feeds` that meta.json's "before feeds start" refers to, and its events simply queue. Only the shred and gRPC tx feeds need to wait for meta.json.
  - Or subscribe the state stream first and take the RPC snapshot after it (the store orders by slot, so a late snapshot cannot overwrite a newer stream write).
  - Or re-take the snapshot immediately before `start_state`.
  - In all three cases, move the venue-program hashing out of the boot critical path. Only the route program (43 KB) is needed before the gate is set. The venue hashes can be filled in later, or fetched once per campaign keyed by `last_deploy_slot`.
- Add a test or a run.log line that records `snapshot_slot` and the stream's first update slot, so the gap is measured.

### F2. MAJOR: meta.json `config.normalized_sha256` hashes the config after the command-line overrides, so it changes per segment and differs from campaign.json
- **Location:** `src/main.rs:668` (`a.ov.apply(&mut cfg, live)`) runs before `src/main.rs:695` (`provenance::config_json(&a.config, &raw, &cfg, …)` → `cfg.normalized_sha256()`).
- **Problem:**
  - `--budget-left` rewrites `cfg.live.max_failed_fees_lamports` when it is lower than the config's cap, `--no-record` rewrites `record.enabled`, and `--shadow` rewrites `mode`. The normalized hash is taken after these rewrites.
  - The supervisor passes `--budget-left` to every segment. In a live campaign, every segment after the first one that spends anything gets a different normalized hash.
  - campaign.json's `config.normalized_sha256` comes from `arbx provenance --offline`, which applies no overrides.
  - MEASUREMENT §4.1 says they are "the same as meta.json's". PLAN item 8 says `--budget-left` exists "so the config hash stays constant".
  - Toolkit grouping by normalized config (WP-10) would split one campaign into many configs.
  - The effective values are already recorded in `overrides` and `limits.supervisor`, so the hash does not need to carry them.
- **Proof:** stage-0 config, `arbx provenance --offline` → `dbc60153…`.

  | Run | `normalized_sha256` | `file_sha256` |
  |---|---|---|
  | no flags | `dbc60153…` | `009df6b7…` |
  | `--budget-left 1000000` | **`47068cd1…`** | `009df6b7…` |
  | `--budget-left 99999999999` (above the cap: no change) | `dbc60153…` | `009df6b7…` |
  | `--no-record` | **`6e5478d5…`** | `009df6b7…` |
- **Fix:**
  - Compute `config_json` (and `config.mode`, if it should keep the file's value) from the config as loaded, before `ov.apply`.
  - Keep `config.mode` documented as "after `--shadow`", or add `config.effective_mode`.
  - Add a test: meta.json's normalized hash with each override equals `provenance::report`'s.

### F3. MAJOR: the supervisor's `.pause` can fail silently. It retries forever, floods control.jsonl, and has no fallback
- **Location:** `deploy/run-w.sh:237-245`; `src/control.rs:52-62` (`SendGate::shadow` refuses on a sticky shadow); `src/main.rs:699-704` (a socket that fails to bind is only a warning); `[control] socket = false` is an accepted config value.
- **Problem.**
  - The supervisor marks a segment paused only when `arbx ctl pause-sending` exits 0. Otherwise it tries again every `ARBX_POLL_S` (2 s) for the rest of the segment, with no log line and no fallback.
  - **(a) No socket:** with `[control] socket = false`, or a bind failure, a live segment keeps sending while the operator believes `.pause` took effect. The supervisor never logs "sending paused", but nothing says it failed either.
  - **(b) Sticky shadow:** in a shadow campaign (`mode_shadow`), under `--shadow` (records-only), or after `program_hash_mismatch`, `pause-sending` is refused as "already shadow for the rest of the segment".
    - Each retry spawns the 68 MB binary and appends a refused line to the segment's `control.jsonl`: 30 lines a minute for as long as the file exists.
    - The campaign's `control.jsonl` has no line for the pause request at all.
  - **(c) Resume:** `resume-sending` failures are not checked either. run-w.sh:243-244 logs "sending resumed" whatever the reply.
- **Proof:** a dry-run campaign with the real binary and a shadow config, `.pause` touched mid-segment. The segment's `control.jsonl` had 12 lines in 6 s, all `{"accepted":false,"cmd":"pause-sending","result":"already shadow for the rest of the segment (mode_shadow)",…}`. `supervisor.log` and the campaign `control.jsonl` say nothing about the pause.
- **Fix:**
  - Make `pause-sending` on a gate that is already shadow an accepted no-op that returns `shadow`. It is not sending, which is what the operator asked for.
  - In the supervisor, log the first failure to `supervisor.log`, `supervisor.jsonl` and the campaign `control.jsonl`. After about 3 failed polls, fall back: stop the segment (as `.next`) and hold the next one while `.pause` exists.
  - Check the `resume-sending` reply.
  - Refuse to start a campaign whose frozen config has `[control] socket = false`, or make the bot exit when a supervised run (`--campaign-dir`) cannot bind its socket.
  - Add dry-run checks for "ctl refuses" and "ctl fails".

### M1. MINOR: `.pause` between segments stops all recording
- **Location:** `deploy/run-w.sh:186-190`.
- **Problem:** while `<campaign>.pause` exists, no segment starts. A long pause, such as overnight, records nothing, against the owner's requirement that recording is always on. The bot can now record without sending (`--shadow`).
- **Fix:** while paused, keep starting segments with `--shadow`. Record them as `budget` or `pause` events, so the pause stops sending only.

### M2. MINOR: a failed or mismatched route-program check is invisible to the supervisor and the status stream
- **Location:** `src/main.rs:743-755`; `src/provenance.rs:286-290` (fail closed when the expected hash cannot be checked).
- **Problem:**
  - Fail-closed is right, but the effects are hard to see.
  - A transient RPC failure in the 3 tries at boot turns the whole live segment into shadow, with no re-check later in the segment.
  - The only traces are run.log, meta.json `send_gate`, and `exec.counts.reject_gate_shadow`. The v1 status line has no `send_gate` (A.5 already names `status.send_gate.reason`).
  - A live campaign could run for hours without trading while every supervisor line looks normal.
- **Fix:**
  - Add `send_gate` (`SendGate::json()`) to every status line now; it is a one-line change.
  - Have the supervisor log the gate reason from meta.json at segment start.
  - Optionally re-check the route program in the background when the boot fetch errored (not when it mismatched), and lift the gate only on a match.

### M3. MINOR: the safety-relevant gate decisions in `run()` have no tests
- **Location:** `src/main.rs:705-707` and `:745-755`.
- **Problem:**
  - Tests cover `route_check`, `SendGate` and `wants_send`.
  - Untested: "mismatch makes the gate shadow only for live and canary", "`--shadow` is sticky `forced_shadow`", "no `--live`/`--canary` is sticky `mode_shadow`", and "`set_gate` happens before the engine runs". These sit inline in `run()`, which needs RPC.
  - An inverted condition there would pass CI.
  - Also untested:
    - the normalized-hash consistency (F2);
    - the supervisor's ctl-failure, escalation (SIGINT at 60 s, SIGKILL at 180 s) and disk-low paths.
- **Fix:** move the gate setup into a function such as `fn initial_gate(gate, ov, live, canary, route_check)` with a table test. Add dry-run cases to `tools/test-run-w.sh`.

### M4. MINOR: two fail-open or silent-death hazards in the supervisor's budget computation
- **Location:** `deploy/run-w.sh:116-135` (`spent`), `:201-202`.
- **Problem (a): the "did it send" test.**
  - `spent` decides whether a segment sent by the presence of a non-empty `attempts.jsonl`.
  - After WP-02, attempts go to `attempts.NNN.jsonl.zst` (MEASUREMENT §1.1).
  - A segment that sent but has no readable last status line would then count as **0 spent** instead of `unknown`.
  - The supervisor already knows which segments it ran with `--live`, and should use that.
- **Problem (b): a Python exception kills the supervisor.**
  - Any exception in `spent` prints nothing to stdout. Examples: a last line that is valid JSON but not an object; a non-numeric `failed_fees_lamports`.
  - `LEFT=$(( BUDGET - ${sp%% *} ))` then becomes an arithmetic syntax error, which aborts the non-interactive campaign subshell. Verified: `bash -c 'set -u; sp=""; B=5; LEFT=$(( B - ${sp%% *} ))'` exits 1 without running the next command.
  - The campaign then ends with no `stop` event, and campaign.json keeps `ended_ns` and `end_reason` null.
  - It fails safe for funds but silently.
- **Fix:**
  - Pass the list of `--live` segment names to `spent`, and treat any of them without a readable numeric last value as `unknown`.
  - Wrap `spent` in `try/except` that prints `unknown <error>`.
  - Validate `sp` before doing arithmetic on it.

### M5. MINOR: a crash after a stop request is recorded as the operator stop
- **Location:** `src/control.rs:178-180` (first reason wins), `:231-233` (the panic hook); `src/main.rs:631-635`.
- **Problem:**
  - After `.next`, `ctl stop` or SIGINT, a panic or error during shutdown keeps reason `control` or `signal`, exit 10, class `operator`.
  - The error is only appended to run.log, and the panic text goes only to `.out`.
  - Shutdown crashes are therefore never counted as crashes, and stop.json does not mention them.
- **Fix:** keep the first reason, but add `secondary: {reason: "panic"|"error", detail}` to stop.json, and exit 30 when it is set. Alternatively, let the supervisor classify by `secondary`.

### M6. MINOR: two campaigns can run at once
- **Location:** `deploy/run-w.sh:152`.
- **Problem:**
  - The only guard is `pgrep -f 'arbx-[0-9a-f]{8} run '`, which sees a running segment.
  - During a pause, a crash backoff or the start of a campaign, a second supervisor passes the check.
  - Two live campaigns would then share one wallet, its nonce accounts and its budget. That was also true of the old supervisor.
- **Fix:** take `flock -n` on `runs/.supervisor.lock` for the campaign's lifetime, in the background subshell.

### M7. MINOR: `--shadow --canary` is accepted, asks for the passphrase, and then never sends
- **Location:** `src/main.rs:581-590`, `:677`, `:706`.
- **Problem:**
  - At HEAD, `--shadow` changed only `mode`, so `--shadow --canary` still sent canaries.
  - Now the gate is a sticky `forced_shadow`, so the canaries never send, yet the key is still unlocked and the canary Exec is still armed.
- **Fix:** refuse the combination, as `--shadow --live` already is.

### M8. MINOR: venue-program hashing downloads about 8 MB per segment on the boot path
- **Location:** `src/provenance.rs:297-319`, `src/main.rs:743`.
- **Problem:**
  - PumpSwap is 1.14 MB, RayCpmm 0.72 MB, RayAmmV4 0.31 MB, DLMM 2.20 MB and DAMM v2 1.43 MB of ELF: 5.8 MB, about 7.8 MB as base64 JSON.
  - They are fetched sequentially through the same rate-limited providers that serve the trading path, on every segment boot (15 per 5 h campaign).
  - The `Rpc::call` failover allows 3 s per provider, which can time out on a 3 MB reply. The result is a venue hash with an `error`, which is harmless but noisy.
- **Fix:** see F1. Fetch them after the feeds start, or once per campaign, keyed by `last_deploy_slot` from a 45-byte `dataSlice` of each programdata account.

### M9. MINOR: meta.json v2 breaks the two tools that read it; the obvious fix would misalign columns
- **Location:** `tools/analysis/latency2.py:11`, `tools/analysis/stage1.py:39`.
- **Problem:**
  - Both read `meta["feeds"]` as a list of names. In v2 it is a list of objects.
  - It also lists **disabled** feeds, with `id: null`.
  - A naive `[f["name"] for f in meta["feeds"]]` would shift every txarr and arrivals column after a disabled feed.
- **Fix:** if they are kept before WP-10, use `[f["name"] for f in sorted((f for f in meta["feeds"] if f["id"] is not None), key=lambda f: f["id"])]` when `meta.get("schema", "").startswith("arbx.meta/2")`. Record this trap for WP-10.

### M10. MINOR: a pause or stop does not cancel sends already scheduled by an earlier decision
- **Location:** `src/exec.rs:1056-1105` (the sim-gate fire and the bundle resends run in the spawned task without reading the gate).
- **Problem:**
  - `wants_send` is the only gate. An attempt decided before a pause still fires its `bundle_resend_ms` copies, and a sim-gated attempt still fires after its re-checks.
  - The bound is one attempt under one nonce, and both shipped configs have `bundle_resend_ms = []` and `sim_gate = false`. So there is no effect today, but it is easy to re-enable.
- **Fix:** pass the `Arc<SendGate>` into the task and check `allows()` before every deferred `paths.fire`.

### M11. MINOR: some documented field locations and contents differ from what is written
- **Counters:** MEASUREMENT §7 ("`counts` gains `reject_gate_shadow` / `reject_gate_stopped`") and A.5 put the counters under `counts`. They are in `exec.counts` (exec.rs:722 → `Exec::status`). Fix the docs.
- **Fields that only look like the v2 schema:** stop.json `in_flight_at_stop` is 0 and `drained` true even when no executor ran, and meta.json drops the v1 `sim`, `canary` and `gate` sections (only the frozen `config.toml` has them). Both fit the WP-01 text, but a reader of the v2 schema may not expect them.
- **Fix:** write `null` for the drain fields when there is no executor, and add `sim`, `canary` and `gate` to the normalized sections.

---

### Nits
- **N1. Every index touch causes a full release rebuild** (`buildinfo.rs:84-89`). Watching `.git/index` means any `git status`, `git add` or `git diff` that refreshes the index reruns the build script. That includes other agents working in the same repo. `ARBX_BUILD_TS` always changes, so the crate recompiles: minutes for this release profile. The plan asked for the index to be watched; this records the cost. If it hurts, watch only HEAD, the ref and packed-refs, and accept that an uncommitted edit already reruns through `src/`.
- **N2. Git calls can depend on user config** (`buildinfo.rs:59-61`). `git diff HEAD --binary` does not pass `--no-ext-diff --no-color`. A user `diff.external` or `color.diff=always` would change `dirty_sha256` or run an external program from the build script.
- **N3. Dead-code warnings are hidden** (`src/lib.rs`). Making every module `pub` takes the warning count from 24 to 3. Real dead code is now hidden from every later WP. Consider `pub(crate)` for internals, or `#![warn(unreachable_pub)]`.
- **N4. Misleading detail for kernel signals** (`control.rs:126`). A signal sent by the kernel or a tty (Ctrl-C at a terminal has no sender pid) reads "SIGINT from pid ? (sender gone)". Say "no sender process (kernel or tty)".
- **N5. Socket permission window and no peer check** (`control.rs:334-335`). The socket is bound at umask permissions and then chmod'ed to 0600, which leaves a window of microseconds. There is no `SO_PEERCRED` check. The directories are 0700 under the supervisor (`umask 077`), so this matters only for manual runs.
- **N6. Commit hygiene.** Only the `deploy/legacy/` rename is staged. The untracked `.claude/` directory sits in the repo root. Commit exactly the WP files: no `git add -A`.
- **N7. Line interleaving.** `append_line` and `say` write one line as several `write` calls (`writeln!` on an unbuffered `File`). The signal thread, control thread, panic hook and main thread can interleave inside a line of run.log or control.jsonl. This is rare. Format the line to a `String` and `write_all` it once.
- **N8. Input files missing from provenance.** meta.json hashes the seed CSV and registry, but not `crowded_pools_file`, `templates_json` or `signer_stats_file`. Since the config hash stays constant, an edit to the crowded list mid-campaign is invisible.

---

## Deviations reported by the implementer: assessment

| # | Deviation | Assessment |
|---|---|---|
| 1 | `Config::load_raw` instead of changing `load` | Fine |
| 2 | Dirty state limited to the binary's files | Fine and better reasoned than the plan. Configs are hashed separately |
| 3 | Programs fetched on the boot runtime | Acceptable for WP-01 only once F1 is fixed. As it stands, the fetch sits inside the snapshot→stream gap |
| 4 | Mismatch makes the gate a sticky shadow instead of refusing to start | Fine and safer for the supervisor. Make it visible (M2) |
| 5 | Feeds start after send paths, Exec and meta.json | **Not acceptable as is**: F1 |
| 6 | `--env-file`; `<campaign-dir>/<name>`; `--budget-left` only lowers | Fine. A missing `--env-file` is ignored silently (`dotenvy` error dropped, main.rs:665); worth one run.log line |
| 7 | stop.json extras; `final_status_seq` = line index | Fine |
| 8 | Socket failure only warns; deep-dir socket; SIGHUP not handled; key read before the handlers | Fine, except that the warning must not leave `.pause` silently ineffective (F3) |
| 9 | `provenance` leaves out boot-only parts | Fine |
| 10 | Supervisor extras | Fine, apart from F3, M1, M4 and M6 |
| 11 | OD-7 default kept | Fine. The mitigations in the script match the plan: `read -rs`, a pipe, `ulimit -c 0`, history off, cleared at exit |

---

## Disposition

**Date:** 2026-10-04. Applied on master on top of `47552da`, before the WP-01 commit. All three major findings are fixed, every minor one is fixed or recorded below, and so are the cheap nits.

**Verification after the fixes.**
- `cargo build --release`: passes, with the same 3 warnings as at HEAD.
- `cargo test --release`: **126 passed**, 0 failed (lib 109, bin 9, `tests/meta_config_hash.rs` 1, `tests/stop_path.rs` 6, `tests/supervisor.rs` 1). That is 11 more than the 115 at review time. No test was removed.
- `tools/test-run-w.sh`: **88 of 88**, up from 38.
- Real binary against public RPC, from a scratch copy of the smoke config:
  - Shadow run: deadline, exit 0. run.log shows "state stream … started 0.0 ms after the snapshot". The route program is checked at boot. The 5 venue programs are hashed in the background in 536 ms, and meta.json is then rewritten with `programs_pending: false`. The final status line has `send_gate`. In stop.json, `in_flight_at_stop` and `drained` are null and `secondary` is null.
  - Supervisor in `ARBX_DRY=1` with the real binary and the shadow config, `.pause` touched mid-segment: one accepted `pause-sending` line with a `note` in the segment's `control.jsonl`. supervisor.log says "not sending already (… mode_shadow): the pause changes nothing", then "stays shadow" when the file goes. The campaign `control.jsonl` has the pause and resume lines.
  - In the same campaign, segment 2 took its venue hashes from `programs.cache.json`: 34 ms against 536 ms. `config.normalized_sha256` is the same in both segments and in campaign.json.

| Finding | Disposition |
|---|---|
| **F1** stale pool state | **Fixed.** In `run()` the state stream starts right after the account snapshot, as in arb-lab. Its updates queue until the engine runs, and only the transaction feeds wait for meta.json. The route program (43 KB) is still fetched at boot, before the gate is set, but it now runs after the stream starts. The venue programs moved off the boot path into a background task that starts after the feeds and rewrites meta.json once (see M8). The gap is measured: meta.json `state.{snapshot_slot, snapshot_ns, stream_started_ns, followed}`, a run.log line with the snapshot slot and the ms from snapshot to stream, and a run.log line with the slot of the stream's first update after each (re)connect (`feeds::start_state`). Test `the_state_stream_starts_right_after_the_snapshot` is a structural guard on `run()`'s order: snapshot, state stream, route program, send paths, Exec, meta.json, tx feeds, venue programs, engine, with nothing awaited between the snapshot and the stream. The first-update line is checked only by inspection, because no Yellowstone endpoint is reachable from here |
| **F2** normalized hash after overrides | **Fixed.** `run_config()` builds meta.json `config` from the config as loaded and applies the overrides afterwards. `config.mode` is the file's mode, and the new `config.effective_mode` is the mode after `--shadow`. Tests: `normalized_hash_ignores_the_command_line` covers 6 override sets, plus a live config under `--shadow`, against `provenance::report`. `tests/meta_config_hash.rs` runs the real binary through failed boots with no flags, `--budget-left 1000000`, `--budget-left 99999999999`, `--no-record`, `--shadow`, and all of them together; each partial meta.json hash equals `arbx provenance --offline`'s |
| **F3** silent `.pause` failure | **Fixed.** (1) `pause-sending` and `shadow` on a gate already shadow for the rest of the segment are accepted. They change nothing and the reply and control.jsonl carry a `note` (`SendGate::shadow` returns `Ok(false)`). (2) The supervisor reads the ctl reply (`py reply`). The first failure goes to supervisor.log ("PAUSE NOT CONFIRMED"), supervisor.jsonl `pause_failed` and the campaign control.jsonl (`accepted` false, with the reply or "ctl failed (exit n): …"). After `ARBX_PAUSE_TRIES` (3) failed polls, a `--live` segment is stopped as by `.next` (a `next` line with `who` supervisor), and segments that start while the file exists run `--shadow` (M1). A segment that never sent is not restarted. (3) The `resume-sending` reply is checked: a refusal is logged (`resume_failed`) and restarts the segment so that the next one sends. A segment that was already sticky-shadow is not asked to resume; it is logged as "stays shadow". (4) `[control] socket = false` is refused twice: by the supervisor at start (from `arbx provenance`'s new `control` section), and by the bot for any `--campaign-dir` run, where a bind failure is now fatal (exit 30) instead of a warning. Tests: control.rs `gate_modes` and `control_socket_commands`; main.rs `a_supervised_segment_needs_its_control_socket`; test-run-w.sh I (refused, 3 tries, records-only restart, then live again), J (no socket: ctl fails, the stop falls back to SIGINT), K (sticky: confirmed without change, no resume), L (refused resume restarts) and H (`socket = false` refused) |
| M1 `.pause` stops recording | **Fixed.** While `.pause` exists, segments start with `--shadow` and record. When it goes, such a segment is restarted so that the next one sends. Test G |
| M2 invisible gate | **Fixed.** Every status.jsonl line has `send_gate` (`Engine::gate`). The supervisor logs each segment's gate from meta.json (supervisor.jsonl `gate`), with a WARNING for a `--live` segment that is not live. Tests A and Q. **Open:** the optional background re-check of a route program that failed to fetch was not done, so a segment whose boot fetch errored stays shadow |
| M3 untested gate decisions | **Fixed.** `initial_gate()` and `apply_route_check()` were taken out of `run()`, and `the_send_gate_at_start` is a 12-case table test. Supervisor dry runs added for ctl refusals and failures (I, J, L), the SIGINT and SIGKILL escalation (M; `ARBX_STOP_INT_S` and `ARBX_STOP_KILL_S` set the timings), disk low (N) and the lock (O) |
| M4 budget fail-open and silent death | **Fixed.** `spent` takes the `--live` segment names. Such a segment, or one with any non-empty `attempts*` file, whose engine started (`status.jsonl` exists) and whose last line is not an object with a numeric total makes the budget unknown. A boot that failed before the engine could send counts as 0, so one boot crash does not end live trading. The whole computation is wrapped in a `try` that prints `unknown error:<type>`, and bash does arithmetic only on output matching `^[0-9]+ status$`. Test P: a last line that is an array, a missing field, an empty file, and the supervisor surviving to the end |
| M5 shutdown crash recorded as operator stop | **Fixed.** `Session::fail()` keeps the first reason and records stop.json `secondary: {reason, detail}` with exit 30. The run.log stop line adds "(then error: …)". The supervisor classes `secondary` as a crash. Tests: `a_crash_while_stopping_is_not_an_operator_stop`, `tests/stop_path.rs` `an_error_after_sigint_exits_30_with_a_secondary_reason` (new hidden flag `wait-signal --fail-after-stop`), and test Q |
| M6 two campaigns | **Fixed.** `flock -n` on `runs/.supervisor.lock`, taken before the campaign directory is created and held by the background subshell for the campaign's life. Segments and ctl calls do not inherit it (`9>&-`). Test O |
| M7 `--shadow --canary` | **Fixed.** Refused in `Overrides::apply`, before the key is read. Unit test and `tests/meta_config_hash.rs` |
| M8 8 MB per segment on boot | **Fixed.** The venue programs are fetched in the background and cached per campaign in `<campaign>/programs.cache.json`, keyed by the programdata address and its last deploy slot. A later segment makes two small calls: the program accounts, and one `dataSlice` call for the 45-byte headers (new `Rpc::accounts_slice`). The upgrade authority is taken from the fresh header. Entries carry `source` (`rpc` or `cache`), and `pending` until the fetch ends. Test `venue_programs_are_hashed_once_per_campaign` runs against a local mock JSON-RPC server: a miss fetches whole, a hit sends only the slice, a redeploy fetches whole again, a run with no cache fetches whole, a dead RPC is recorded in the entry, and expectations still apply to cached hashes |
| M9 tools break on meta v2 | **Fixed** with the reviewer's expression in `tools/analysis/latency2.py` and `stage1.py` (feeds ordered by `id`, disabled feeds dropped). **For WP-10:** the toolkit must read `feeds[]` this way |
| M10 deferred sends ignore the gate | **Fixed.** The spawned send task holds the `SendGate`. A sim-gated fire whose gate closed in the meantime settles as "not sent: the send gate closed before the deferred send (<mode>)", and scheduled bundle resends stop. Test `a_pause_cancels_a_deferred_send` covers pause and stop |
| M11 docs and field shapes | **Fixed.** MEASUREMENT §7 and A.5 now put the counters in `exec.counts`. stop.json `in_flight_at_stop` and `drained` are null with no executor, and `wait-signal` matches (the test was updated). meta.json, and `arbx provenance`, gain the normalized `sim`, `canary`, `gate`, `record` and `control` sections |
| N1 index watching | **Not changed.** The plan asks for `.git/index`, and the cost is recorded here. Revisit if rebuilds hurt |
| N2 git config dependence | **Fixed.** `git -c core.quotePath=true diff --no-ext-diff --no-color --no-textconv` |
| N3 dead code hidden by `pub mod` | **Not changed** (later WP): `pub(crate)` for internals or `#![warn(unreachable_pub)]` would touch every module |
| N4 kernel or tty signal detail | **Fixed.** "SIGINT with no sender process (kernel or terminal)". Test `signal_detail` |
| N5 socket window and peer | **Partly fixed.** Every connection is checked with `SO_PEERCRED`: only the run's uid or root, and others are refused and logged. The bind-then-chmod window remains, and `umask` is process-wide |
| N6 commit hygiene | **Done.** Only WP-01's files are committed, by name. `.claude/`, `program/` and `target/` are not included |
| N7 line interleaving | **Fixed.** `append_line` (control.jsonl, run.log from the signal, control and panic threads) and `run`'s `say` each format the whole line and write it with one `write_all` |
| N8 unhashed inputs | **Fixed.** meta.json `inputs`, and `arbx provenance`, hash `crowded_pools_file`, `templates_json` and `signer_stats_file` (path, sha256 and size, or an error). Test `inputs_are_hashed` |
| Deviation 6: a missing `--env-file` is silent | **Fixed.** A run.log WARNING names the file and the kind of error. A parse error gives only its byte offset, never the line, which could hold a secret. meta.json `run.env_file_loaded` records it. Checked in `tests/meta_config_hash.rs` |

**Behaviour changes for the owner:**
- `.pause` now stops sending but keeps recording.
- A `--live` segment that cannot confirm a pause is restarted in records-only mode.
- meta.json is written twice: once before the feeds start, and once when the venue hashes arrive.
- `config.mode` in meta.json is the file's mode. The new `config.effective_mode` is the mode after `--shadow`.

**Open for later WPs:**
- M2: a background re-check of a route program whose boot fetch failed.
- N1: the cost of watching the index.
- N3: `pub(crate)` for internals.
- N5: the bind-then-chmod window.
- WP-10: read meta v2 `feeds[]` by `id`.
- WP-07: the ledger replaces the status-line budget.
- WP-02: `attempts*` names are already covered by `spent`.

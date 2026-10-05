# WP-05 review: send policy (bundle-only, fail-closed, in-flight by route and state, crowding rank)

**Date:** 2026-10-05. **Reviewer:** adversarial review, read-only. No repository code was changed; the probes ran in a scratch copy of the crate.
**Plan:**
- `docs/PLAN.md` WP-05: items 1-11, config keys, offline acceptance, measurement outputs.
- `docs/PLAN-ADDENDUM.md`: I-7, I-10, go-live gate items 3-4, I-11.
- The E2 hand-offs: the b69c9e9 body "Not done here", `docs/reviews/WP-03b-review.md` (to WP-05), `docs/reviews/WP-08-review.md` #13 and #18, and `docs/reviews/WP-04-review.md` #8.
- `docs/MEASUREMENT.md` revision 2.9.

## What was reviewed

- **The diff.** The uncommitted WP-05 work on HEAD 323e3bf:
  - 24 modified files, +3,053/−2,046;
  - 6 new files: `src/bands.rs`, `src/crowding.rs`, `src/netcount.rs`, `src/proglog.rs`, `src/exec/tests.rs` and `tools/arbx-report/tests/test_wp05.py`.
- **Snapshot hashes, taken at the start.**
  - `git diff`: sha256 `1bc6402b2ffedb27cedeb78a80d03cc4599da4ad539141ed01e66e80ba3d8822`.
  - The diff plus the six new files (each prefixed `=== <path>`): `08d2aec68b7fa1cfa7e2882b162c71c92d510df7c72f41b674a5da6367302fe8`.
  - At the end of the review, HEAD and both hashes were unchanged. **The code reviewed is exactly this snapshot.**
- **Build and tests.** Run by me in the main tree, on its own `target/`, with `CARGO_BUILD_JOBS=5`:
  - `cargo build --release` passes. It gives 2 warnings, both pre-existing (`main.rs:452`, `:460`, irrefutable `if let`); there are no new warnings.
  - `cargo test --release`: **342 passed, 0 failed, 2 ignored**. That is lib 316 (+1 ignored), bin 12, legacy_fixtures 4, meta_config_hash 1, runtime_isolation 2 (+1 ignored), stop_path 6 and supervisor 1. It matches the claim.
  - Stability: the full lib suite passed 2 more times. The WP-05 modules (exec, send, crowding, bands, netcount, proglog and the WP-05 config tests: 57 tests) passed 5 more times.
  - Toolkit (`tools/arbx-report/tests`, `python3 -m unittest discover -s .`): **80 OK, 4 skipped**. This matches the claim.
  - `arbx check` exits 0 on `deploy/arbx-stage0.toml` and on `deploy/arb.toml`.
    - I ran it with `env -i` and an empty `HOME`, so that no `.env` and no key file could be read; neither exists on this machine.
    - Stage 0 prints `enabled send paths: jito-bundle (bundle-only: a live or canary run may start)`.
    - `arb.toml` prints `... (NOT bundle-only: live and canary runs refuse to start)`.
- **Probes.** I ran four tests in a scratch copy of the crate (`scratchpad/r3/wp05-review/crate`; the code is in the appendix):
  - Two timing probes, each run single-threaded: the crowding map's costs, and the engine-thread cost of `decide()` and `inputs()`.
  - Two behaviour probes. Both pass, which means each one shows its defect.
  - The scratch `target/` was deleted afterwards.

## Verdict

**No blocker. Mergeable after one major is fixed. Two minors should be fixed before the live canary.**

The safety core is sound, and I could not break it:
- No path transmits a transaction in shadow or dry-run mode.
- A live or canary run sends only one-transaction Jito bundles.
- Every send check fails closed.
- No secret reaches a record.
- The throwaway key only signs dry-run bundles.
- A landed bundle cannot lose: on-chain min_profit = tip + base fee + margin.

The findings, by severity:
- **Major (hot path), finding 1.** The crowding map costs O(map) on the engine thread at every housekeeping tick (up to 200 a second), and O(signers of the pool) on the decision path before the fire.
  - Measured: 27-92 µs per tick at 42k-100k entries, and 8-19 µs per decision on a pool with 2,000-5,000 signers.
  - For scale, WP-04's review rated 25 ms every 10 s major.
- **Minor, fix before the canary.**
  - Finding 2: the in-flight lock is released at the first Jito result that is not `accepted`. A probe resends the same state, to the same leader, for the same target slot.
  - Finding 3: a landing found first by the expiry status check never gets its wallet record. Its fee and round trip are lost, while its tip is counted.
- **Other minors and nits:** findings 4-18.

## Safety: what I tried to break

| Attempt | Result | Why it holds |
|---|---|---|
| Transmit in shadow | **Not possible** | `Exec::assemble` drops the send paths unless `mode.sends()` (exec.rs:688). `decide_inner` takes the fire branch only when `!would`, and `would = !mode.sends() \|\| gated` (:886). A shadow executor refuses a key (:642). Shadow does build the paths for keep-alives, but they never reach the executor. Reaching `Paths::fire` takes `arbx senders --raw` |
| Transmit in a dry run | **Not possible** | No send path is built (main.rs:1214). `Exec::new` refuses send paths (exec.rs:638), and `assemble` drops any it is handed (the test hands it some). There is no Jito client. `self.key` is None, and the throwaway key lives only in `Dry` (:692-697). The simulation is `simulateTransaction` (rpc.rs `simulate_bounded`); the mock test checks that only `getMultipleAccounts` / `simulateTransaction` are called. The gate is sticky shadow (`dry_run`), so `resume-sending` is refused. Even with the gate open the executor has nothing to fire with, and the test opens it |
| Live or canary outside the bundle path | **Refused at three layers** | `Config::parse` checks a `mode = "live"` file (config.rs:1109). `run()` checks for `--live` and `--canary` (main.rs). `Exec::new` checks again (exec.rs:633) and requires the bundle path. `decide_inner` fires exactly one `Copy` on `bundle_path()`. `direct_experiment = true` does not load |
| Gates that fail open | **None found** | `HealthFlags::default()` is warm-up. A recorder that is off, closed or has lost core records refuses (`Rec::core_ok`). A blockhash of unknown age is `blockhash_stale`. No schedule, no LeaderBook, or a book that disagrees with the schedule makes the leader `unknown`, which is skipped. No Jito client in live, or a token with under 5 s left, is `jito_auth_stale`. `send_bundle` reads only the cached token. The fee cap reserves 5,000 lamports per open attempt |
| Secrets in logs, records, meta.json, argv or dry-run records | **None found** | I-10 notes and errors name variables (`${X}`), never their values. `check_key_material` errors name the field. `RpcFailure` messages are scrubbed at construction (rpc.rs:202). The dry-run record holds the signed transaction (no secret) and the throwaway pubkey. meta.json gains `keystore_read` and `dry_run_signer` (the pubkey). argv only gains `--dry-run` |
| Misusing the throwaway key | **Not possible** | It comes from `/dev/urandom`, the seed buffer is zeroed, and it is never written. It is refused if it equals the payer. It is used only by `build::sign` and `verify_bundle` in the would-send branch. The payer stays the wallet, so the signature cannot pass on chain (the test verifies it fails against the payer) |
| Tip and min_profit arithmetic | **Correct** | tip = clamp(⌊0.7 × (gross − 5,000)⌋, floor, max(max, floor)), so `clamp` cannot panic. min_profit = tip + 5,000 + max(floor, ⌊share × net⌋). The decision's bar is max(min_profit, tip + 5,000 + `[live] margin_lamports`). `implausible_gap` bounds expected ≤ size, so nothing overflows. Rent is excluded, as planned |

## Acceptance checklist

| Item | Status | Notes |
|---|---|---|
| 1 Paths: live is bundle-only; other kinds compiled; `direct_experiment` refused; the fee arms, tiers, gate, sim gate, resends and size variants removed; one copy; canary = live with caps ≤ 0.2 SOL | **Met** | Old keys fail with `deny_unknown_fields` (`wp05_send_policy_keys`). `simcheck --canaries` went with the built-to-fail canaries |
| 2 Fail closed: blockhash ≤ 20 slots, target-slot leader and kind skip, cached token with a background refresh at half-life, recorder, gate, store health; one pure `send_checks`; the exec client on `call_bounded` | **Met** | `send_checks` = gate, then `input_checks`. Run-time RPC: `statuses_bounded` and `simulate_bounded`. `keep_token` itself is untested (finding 14) |
| 3 Recent blockhash: `Bh {hash, slot, height, src}`; nonce leasing gone; open until height + 150; `blockhash_commitment`; age and source in attempts | **Met** | Nonce code is deleted rather than kept behind the experiment (deviation; acceptable). Without heights: slot + 300; without slots: 120 s |
| 4 In-flight lock on (buy, sell, mint) with sv, target, leader, attempt, t; same state / same leader refused; hold 2 slots or the final verdict | **Partly met** | It is released at the first non-`accepted` Jito result, not at the attempt's final outcome (finding 2) |
| 5 Rate: `Prio {band, crowd, EV}`; bands from `src/bands.rs`; ≥1M at 0.5/s and behind every smaller band; crowding from an activity map, static list until it holds 6 h; `queue_ms` with `rate_queue_timeout` / `crowded_pool`; λ when ≥4 wait | **Met, with findings** | Hot-path cost (finding 1). The map is per process, so with segments under 6 h it never takes over (finding 4). Crowding is the max of the two pools, not the union (finding 4) |
| 6 Token cooling with `token_cooling` | Met | Counted per result, not per attempt (nit 16) |
| 7 Verdict history (all results, in order, with times), validator, outage events, zero-wait deleted, `be_rtt_ms` | **Met** | |
| 8 On-chain min_profit; Stage-0 floor 1 / share 0 | **Met** | The encoded value is never checked from the signed bytes (finding 12) |
| 9 Stream settlement, expiry status check with history, cross-checks at +2/+10/+60 s (500 ms), amends | **Met, with a gap** | A status-first landing loses its later wallet record (finding 3). A timed-out send is final at once (finding 7) |
| 10 `src/proglog.rs` (`meaning`, `delivered_from_logs` unchanged, `events`) | Met | |
| 11 Attempts carry `leaders.snapshot(target_slot)` | Met | The snapshot is also taken before the fire (finding 8) |
| Config keys | **Met** | In `[send_policy]` (deviation; required by TOML). `[dry_run]` is new |
| Offline: one bundle copy; a live config with another path fails to load | Met | `a_live_decision_sends_one_bundle_copy_with_no_network_call`, `live_configs_are_bundle_only` |
| Offline: in-flight table (same state, new state, new leader, expiry) | Met | `the_inflight_lock`. No test of a release before the hold (finding 2) |
| Offline: queue order, ≥1M cap, crowding rank under the paused clock | Met | Budget order under the paused clock; the cap is the engine-side `TokenBucket` (explicit ns) |
| Offline: `send_checks` (age, kind, token) | Met | Table-driven, and the order is tested |
| Offline: verdict history | Met | `every_result_of_a_bundle_is_kept_in_order` |
| Offline: network-call counter | Met | Thread and task scopes. The send reaches the fake block engine with the counter at 0; a background refresh counts only in the total. A task spawned without the scope escapes it (nit 14) |
| Offline: settlement (status hit becomes landed; late landing amends) | Met | It codifies finding 3's inconsistent money totals |
| Measurement outputs (attempts 2.0, copies 1.2, bundles 2.0, outcomes 2.0, decision reasons) | Met | MEASUREMENT 2.9 matches the code where spot-checked |
| **I-7** shadow runs every check up to the signature, records `sent = false` | **Met** | The token check is not modelled in shadow (`NotUsed`) |
| **I-10** secret only over TLS/QUIC or in a header; `http://` + `${…}` refused unless `no_tls_endpoint`, recorded; a payer-keypair provider key refused | **Met as worded** | A header secret over plain http passes (finding 5). The payer-key check runs in `arbx check` and at `Paths::new` (lenient or not) |
| **Gate item 4** dry run: ≥100 signed, never sent, size/tip/accounts checked | **Met** | 120 in the test. Neither the signed bytes' min_profit nor amount_in is checked (finding 12) |
| Dry run cannot transmit; throwaway key | **Met** | See the safety table |
| Fail-closed health with WP-04's gate and the blockhash ring | **Met** | `HealthFlags` default warm-up (WP-04 #8). INPUT 1 heads reach `SendView` |
| E2 / earlier hand-offs: `note_attempt`, `note_be_rtt`, `note_bundle_processed`, `note_jito_processed`, the LeaderBook snapshot in attempts, reading the blockhash ring, the watch narrowed to the target slot (WP-03b), the kind journaled at the decision (WP-08 #18), not ready by default (WP-04 #8) | **Met** | Each has a caller and a test |
| DoD: build, tests, warnings, configs, MEASUREMENT | Met | |

### The declared deviations

| Deviation | Assessment |
|---|---|
| `[send_policy]` instead of `[send]` | Necessary: TOML cannot hold a `send` table beside the `[[send]]` array of tables. Fine |
| Nonce code deleted | Fine: `direct_experiment` is refused in Stage 0, and the nonces stay as data in `[send_policy.direct]`. `build::advance_nonce_ix` / `nonce_value` remain unused (nit 17) |
| `settle_s`, the sim gate, resends and canaries removed | Planned (items 1, 3 and 9). None is needed for the go-live gate: item 4 is the dry run, the canary is a capped live run, and settlement is stream-based |
| Canary size capped at 0.2 SOL | That is the plan's number, so it is not a deviation |
| Header secret over http allowed | It matches the addendum's literal text, but not its intent (finding 5) |
| Shadow rate modelling approximated | Acceptable as a model, but one reason code gets two more meanings (finding 10) |

## Findings

### 1. Major (hot path): the crowding map is scanned on the engine thread every 5 ms, and per decision before the fire

**Location.**
- `src/engine.rs:1484`: `self.activity.expire(now)` in `housekeeping`. `HOUSEKEEPING_NS` is 5 ms (engine.rs:42), so it runs on every idle wake-up.
- `src/crowding.rs:61-69` (`expire`: `by_pool.retain` over every pool and every signer).
- `src/crowding.rs:72-91` (`signers`: counts a pool's whole map per call; `crowding` calls it for both pools).
- `src/engine.rs:2178` (`route_in`: `crowding(..)` on every decision, before `decide` signs and fires).

**Problem.**
- `expire` costs O(total (pool, signer) entries) on every housekeeping tick. Housekeeping runs whenever the engine idles 0.2-5 ms, which in a run is about 200 times a second.
- `crowding()` costs O(signers of both pools) on every `route_in`. That is on the decided → signed path, and on the pools the bot sent to most: 49% of legacy attempts went to the 21 crowded pools.
- The map grows for 6 h. Each pool is capped at 10,000 signers, and there is no global cap.
- PATTERNS.md's all-night bins give about 40k (pool, arbitrage signer) pairs. One listed pool (`58oQChx4…`) had 4,558 signers in a single segment.

**Proof.** `probe_activity_costs`, release build, run single-threaded:

| pools × signers | entries | `expire` per call | at 200 calls/s | `crowding()` per call |
|---|---|---|---|---|
| 500 × 20 | 10,000 | 8.8 µs | 1.8 ms/s | 0.05 µs |
| 21 × 2,000 | 42,000 | 27.5 µs | 5.5 ms/s | 7.8 µs |
| 2,000 × 50 | 100,000 | 91.7 µs | 18.3 ms/s | 0.16 µs |
| 50 × 5,000 | 250,000 | 169 µs | 33.8 ms/s | 18.5 µs |
| 100 × 10,000 | 1,000,000 | 1,441 µs | 288 ms/s | 38.5 µs |

At a realistic 40-100k entries, the engine stalls 30-90 µs every 5 ms, which is 6-18 ms of CPU a second. Every update that arrives during a stall waits behind it. A decision on a 5,000-signer pool waits about 18 µs more before its signature. The engine's own `state_recv_to_decided` budget is microseconds (WP-02's acceptance holds the recorder to 5 µs of p99).

**Fix.**
- Expire the map once a minute: the window is 6 h, and `signers()` already filters by time.
- Better, expire incrementally from a time-ordered queue of (t, pool, signer).
- Keep a per-pool count, updated on insert and expiry, so `crowding()` is O(1).
- Add a test that bounds `expire` / `crowding` cost at 100k entries.

### 2. Minor: the in-flight lock is released at the first non-`accepted` Jito result, so the same state can go again to the same leader at once

**Location.**
- `src/send/jito.rs:175`: `is_final() = outcome != "accepted"`. Would-fail, lost-auction, dropped, rejected and processed all count as final.
- The sink sends `"release": o.is_final()` (exec.rs:726-728).
- `src/exec.rs:1177`: `on_release` calls `inflight.release(attempt)`.

**Problem.**
- Item 4 allows a new attempt on a key "only if the state version or the leader differs". The entry expires "after `inflight_hold_slots` or at the attempt's final verdict".
- The PLAN's own definition of final (WP-07) is "the signature appears in the wallet stream; Jito reports processed and the wallet stream confirms it; the blockhash expires".
- A Jito would-fail says that this state version does not pay. Releasing the lock on it reopens exactly that state, to the same leader and the same target slot.
- Would-fail is by far the most common verdict (PATTERNS Q6: 4,479 would-fail against 88 accepted), and it arrives in tens of ms. So for most attempts the lock lasts only until that result, not 2 slots.
- Each repeat spends one of the 5 bundle slots a second, the scarce budget R §1 identifies.
- Each repeat also counts toward the 25 would-fails in a row that pause the whole token for 60 s or more (`token_cooling`).
- How often the engine re-decides an unchanged route is not measured. The attempts' `inflight.why_allowed` / `prev_sv` will show it.

**Proof.** `probe_would_fail_reopens_the_same_state`:
- sv 7 at tip 100 → `sent`;
- again → `inflight_same_state`;
- then INPUT 5 `would-fail` (release true), then sv 7 at tip 100 again → **`sent`**, with `why_allowed` **`first`**.

**Fix.**
- Release early only on a landing (wallet or `processed`), or when the attempt is refused before it left (`on_fired`).
- On would-fail, lost-auction or dropped, keep the entry for its hold: the state version is dead.
- Add the row "would-fail then the same sv: `inflight_same_state`" to `the_inflight_lock`.

### 3. Minor (money fields): a landing found first by the expiry status check never gets its fee, events or round trip; the tip is counted anyway

**Location.**
- `src/exec.rs:1463` (`Landed::of_status`: `fee: None`, `prog_events: Null`).
- `src/exec.rs:1249` and `:1253` (finalize from statuses).
- `src/exec.rs:1163`: `on_wallet_tx` amends only `finals` with `!landed`.
- `src/exec.rs:1273-1278`.

**Problem.**
- When the status check sees the landing first (the wallet record comes after the blockhash expiry, or the expiry check fails and a cross-check had seen it), the attempt is final `landed_ok` / `landed_fail` without a fee or `prog_events`.
- `finalize` adds the tip to `tips_paid` and 0 to `fees`. For a failed landing it adds 0 to `spent`, so the failed-fee cap undercounts.
- When the wallet record arrives with the fee and events, it is dropped (`.filter(|f| !f.landed)`), and no amend line is written.
- The money section then shows a winner's tip without its round trip: a loss that did not happen.
- The same happens to `round_trip` whenever `prog_events` is null (truncated logs).

**Proof.** `probe_status_landing_loses_the_wallet_record`:
- 1 outcome line, **0 amend lines**;
- money: `tips_paid 31499`, `fees_landed 0`, `round_trip 0`.
- `settlement_from_the_chain` asserts the same inconsistency: tips 2 × 31,499 against round trip 49,000.

**Fix.**
- Remember that a final came from statuses only (`Final.src`).
- When the wallet record arrives, write an amend line carrying the fee, CU and events, and add the fee and round trip (and the fee to `spent` for a failure) without counting the landing twice.
- Count a win's tip only together with its round trip, or report both counters as partial.

### 4. Minor: the crowding map never matures in a campaign, and a route's crowding is the max of its pools, not "either pool"

**Location.** `src/crowding.rs:79-91`. `src/main.rs:1410-1412`: a new `Activity` per process.

**Problem.**
- The map exists only in memory. A campaign's segments are short (the legacy w5h ran 15 segments in 5 h).
- So `started + window` is never reached, and `src` stays `static_list` for the whole campaign.
- In that state an unlisted pool's bucket is capped at 1 (`bucket_of(n).min(1)`).
- Item 5 says the map "replaces WP-00's bucket". In practice WP-00's 21-pool list of 2026-10-03 rules forever, and it starts empty again every segment.
- Item 5 counts "signers that landed transactions on either pool": a union. The code takes `max(signers(buy), signers(sell))`, which under-buckets two moderately crowded pools.

**Fix.**
- Persist the map at stop and preload the newest sibling segment's copy, as `alts-final` does, or document that the static list is the Stage-0 crowding.
- Count the union, or document the max.

### 5. Minor (I-10 intent): a secret in a header over plain `http://` passes

**Location.** `src/config.rs:1265-1281` (`cleartext_check` looks only at `${…}` in `url` / `ping_url`). The test `cleartext_secrets_are_refused` asserts that `node-one` over `http://` with `token_env` loads.

**Problem.**
- I-10's issue is credentials in clear text. A header over plain http is just as readable on the wire as a query parameter.
- `nodeone`, `flashblock` and `bloxroute` (all disabled today; WP-19 candidates) are `http://` URLs with header keys.
- The addendum's sentence ("only over TLS/QUIC or in a header") permits this, and the implementer declared it.

**Fix.** Treat a `token_env` / `jito_auth_env` on an `http://` URL like a URL secret, requiring `no_tls_endpoint`, or have the owner confirm the literal reading in the addendum.

### 6. Nit: the supervisor's "may have sent" test now sees would-sends

**Location.** `deploy/run-w.sh:156`: any non-empty `attempts*` file means `sent`.

**Problem.**
- A shadow or paused segment now writes attempts (would-sends, `sent = false`). If it dies before a status line carrying `money`, the campaign's budget becomes `unknown`, and every later segment is records-only.
- This is fail-safe, and unlikely because periodic lines carry `money` whenever an executor runs.

**Fix.** Note it in run-w.sh, or have the status line (not the file's existence) decide.

### 7. Minor: a copy that left but got no answer is final at once, so the lock and the reservation are released while the bundle may still land

**Location.** `src/exec.rs:1132`: `left = t_sent > 0 && ok`. A timeout (`no answer in 5s`, send/mod.rs:949-950) or a transport error after the request went out has `ok = false`.

**Problem.**
- Such an attempt is finalized `not_landed_refused` immediately. Its in-flight entry, fee reservation and big-band token are given back.
- The block engine may have taken the bundle. If it lands, the wallet stream's amend handles the money, because the signature was watched (`t_sent > 0`).
- But the lock and the cap reservation were released early, and the outcome says `refused` for something that may have been accepted.

**Fix.** Treat "left, no answer" as open (`fired`, no bundle id), and let expiry decide. Release early only for `drop` codes and explicit refusals.

### 8. Minor (hot path): two avoidable costs before the fire

**Location.**
- `src/exec.rs:821-829`: `leader_seen` takes a full `LeaderBook::snapshot(target)` on every executor decision, refused ones included. That is a RwLock read, two b58 encodes, two geo lookups, a possible region median with an allocation and sort, and the next-leader search, just to read `kind`.
- `src/engine.rs:2179`: `trig_has_poh` may take the global `PohIndex` mutex, which the feed threads share, for a gauge.

**Proof.** `probe_decide_costs`: `inputs()` p50 2.3-3.2 µs with a 3-validator book, a lower bound.

**Fix.** Use `LeaderBook::kind(slot)` (or a light kind-and-identity read) before the fire, and take the snapshot and the PoH lookup after it, when the attempt line is written.

### 9. Minor: decisions.jsonl `band` and the attempt's band can differ

**Location.**
- `src/engine.rs:2540`: `band_of(p.gross)` at the engine's priced size.
- `src/exec.rs:855`: `bands::of_gross(r.expected())` at the size cap.

**Problem.**
- F22 asks for the same bands in decisions, the queue and tips. The table is shared, but the inputs are not.
- A decision priced past `[live] max_size_sol` (the ladder reaches 8.4 SOL) records band 3 in `band`, while its `rank` and the attempt say band 0-2.

**Fix.** Record the executor's band in decisions.jsonl when the executor decided (keep the engine's as `band_at_opp`), or document the two.

### 10. Minor (analysis): `crowded_pool` means three things

**Location.**
- `src/exec.rs:873-875`: the 100k skip.
- `send/budget.rs` `Drop::Crowded`: overtaken in the queue.
- `src/exec.rs:889`: a shadow or dry-run would-send over the path's rate whose route is crowded, whether or not anything overtook it. This is the approximation the implementer declared.

**Fix.** Use distinct reasons (`crowded_skip`, `crowded_pool`, `would_rate_crowded`), or record the source next to the reason.

### 11. Nit: `Budget::acquire` can report a slot it never got

**Location.** `src/send/budget.rs:150-163` and `:174`.

**Problem.**
- After a timeout, the awaited future is dropped (its receiver with it) before `acquire` locks the state.
- If the pump locks first, `retain(|w| !w.done.is_closed())` removes the waiter without granting it. `acquire` then finds it gone and returns `Ok(Granted)`.
- One send goes over the rate, and the block engine may refuse it. The window is very small (multi-thread runtime only).

**Fix.** Mark the waiter granted in the pump, and have `acquire` check the mark, or skip `retain` for waiters past their deadline.

### 12. Minor (test gap; gate item 4): neither the dry run nor any test checks the on-chain min_profit or amount_in in the signed bytes

**Location.** `src/exec.rs:1557-1597` (`verify_bundle`).

**Problem.**
- The route instruction's data is `[2, n, amount_in u64, min_profit u64, …]` (build.rs:211-213). This is the field that makes a landed bundle unable to lose.
- `verify_bundle` checks that the route program and the pools are present, but never decodes these two numbers.
- The attempt's `min_profit_onchain` is the executor's variable, not the signed value. A regression passing the wrong value to `route_ix` would pass every WP-05 test and the dry run.

**Fix.** Add `min_profit` and `amount_in` checks to `verify_bundle`, comparing the decoded values with the attempt's `min_profit_onchain` and `size_lamports`. Assert them in the live test too.

### 13. Nit: `TokenBucket::refund` uses the wall clock

**Location.** `src/exec.rs:1147`: `self.big.refund(now_ns())`, while every take uses the engine's `t`.

**Problem.** It mixes clocks in a structure the engine owns. That is harmless live, but a replay of the bucket would diverge.

**Fix.** Pass the engine time: `on_settled` has the event's journaled time.

### 14. Nit (tests that would pass with a bug present)

- `main.rs a_dry_run_never_sends` checks the text of `run()` (`body.contains("let paths = if … && !dry_run {")`). A later line that rebuilt the paths or read the keystore in a dry run would pass. The behavioural guarantees come from `Exec::new` / `assemble` and their tests.
- **No test of `Jito::keep_token`.** The renewal loop, its backoff and its events are untested; only `renew_due_ms` and `renew(true)` are. A bug in it shows live as `jito_auth_stale` on every decision: fail-closed, but the sender is dead.
- **No test of the `jito_stream_down` / `jito_stream_up` events** (item 7).
- `netcount` counts a task spawned on the send path only if the scope is handed over (`current` + `in_task`). A pre-fire `rt.spawn(rpc.call…)` would escape the counter. No such call exists today.
- Findings 2, 3 and 12 have no failing test. Finding 3's behaviour is asserted as correct in `settlement_from_the_chain`.

### 15. Nit: `round_trip` takes the second `out` event

**Location.** `src/exec.rs:1276` and `:1307` (`delivered_of(..).get(1)`).

**Problem.** This is correct for two legs. A three-leg route (WP-06 and later) would take a middle leg's output.

**Fix.** Use the last leg's `out` (the leg index of the last event).

### 16. Nit: counters

- Token cooling counts every would-fail result, so a bundle with two counts twice.
- A closed-gate decision is counted under both `reject_gate_*` and the underlying `reject_*`, so the sum of `reject_*` is not the number of refusals.
- `canary_count` counts attempts handed to the fire, including those the rate queue then dropped.

### 17. Nit: leftovers

- `build::advance_nonce_ix`, `build::nonce_value`, `RouteIn::trig_cu_price` / `rival_cu_price` and `[send_policy.direct] nonce_accounts` have no reader.
- `limits.max_size_sol` in a canary run's meta.json is `[live]`'s (4.2), not the canary's real cap (`canary_max_size_sol` is beside it).
- `send_paths[].tls` is true for a URL that is entirely `${VAR}`, whose scheme is unknown until expansion.

### 18. Nit: shadow does not model the token check

**Location.** `src/exec.rs:809-813` (`TokenSeen::NotUsed` for every non-sending mode).

**Problem.** A shadow run builds the jito path (keep-alives) but hands the executor none, so `jito_auth_stale` periods never show in would-sends. This is acceptable for I-7 ("up to the signature"); the doc should say it.

## Measured costs (engine thread, `probe_decide_costs`, release, single-threaded)

| Mode | `decide()` p50 / p90 / p99 | Notes |
|---|---|---|
| shadow (would-send: build + attempt line) | 63.5 / 65.5 / 89.1 µs | at most `max_per_sec` (5) would-sends a second |
| dry run (+ sign, `verify_bundle`, accounts, base64) | 150 / 155 / 203 µs | at most 5 a second |
| live (sign, fire, then the attempt line) | 80.6 / 110 / 2,080 µs | decided → signed p50 54 µs (includes `inputs` and the test's route); signed → fired p50 0.7 µs |

The would-send and attempt-line work is bounded by the 5/s rate, so it is not a throughput concern. The pre-fire part is dominated by build and sign, which existed before. The new pre-fire costs are finding 1's crowding scan and finding 8's snapshot and PoH lock.

## Appendix: probes (scratch copy only)

Added to `src/crowding.rs` (a `#[cfg(test)] mod probe`) and to `src/exec/tests.rs`, all `#[ignore]`. Run with:

```
CARGO_TARGET_DIR=<scratch>/targets/wp05-review cargo test --release --lib -- --ignored probe_ --nocapture --test-threads=1
```

- `crowding::probe::probe_activity_costs`:
  - fills an `Activity` with P pools × S landed signers through `candidate` / `landed`;
  - times 200 `expire` calls and 1,000 `crowding` calls (table in finding 1).
- `exec::tests::probe_decide_costs`:
  - 400 decisions per mode on the review rig (distinct pools, engine time stepped past the rate window);
  - times `inputs()` and `decide()`, and reads the executor's `decided_to_signed` / `signed_to_fired`.
- `exec::tests::probe_would_fail_reopens_the_same_state`:
  - live rig: sv 7 at tip 100 is `sent`, then `inflight_same_state`;
  - `on_release(attempt 0, would-fail, release: true)`;
  - sv 7 at tip 100 again → output `sent (why_allowed Some(String("first")))`.
- `exec::tests::probe_status_landing_loses_the_wallet_record`:
  - live rig: sent, fired, then the expiry `Statuses` hit (slot 102, ok);
  - then `on_wallet_tx` with fee 5,000 and two `out` events;
  - output `outcome lines 1 (amend lines 0), money tips_paid 31499 fees_landed 0 round_trip 0`.

## Disposition (2026-10-05, WP-05 commit)

The reviewed code is the snapshot above (`git diff` sha256 `1bc6402b…`, re-checked before the fixes); its fixes are part of
the WP-05 commit on top of 323e3bf. Every build went to the main tree's own `target/` with `CARGO_BUILD_JOBS=5`; the
pre-fix comparisons below ran in a scratch copy with its own target under `/tmp`.

Tests at the commit: `cargo test --release` **355 passed, 0 failed, 4 ignored** (lib 328 + 3 ignored: the review's 316 + 12
new, and the two probes below kept as `--ignored`; bin 13 (+1); legacy_fixtures 4; meta_config_hash 1; runtime_isolation 2
+ 1 ignored; stop_path 6; supervisor 1); the lib suite passed 2 more times and the WP-05 modules (83 tests) 5 more times.
Toolkit 80 OK, 4 skipped; `cargo build --release` with the 2 pre-existing warnings (`main.rs` irrefutable `if let`);
`arbx check` exits 0 on `deploy/arbx-stage0.toml` and `deploy/arb.toml` (run as the review did, `env -i` with an empty
`HOME`: no `.env` and no key file can be read); `tools/test-run-w.sh` 96 of 96 checks.

**Each required fix has a test that fails on the reviewed code.** The new tests were ported to the pre-fix API in a scratch
copy of the reviewed snapshot (debug build) and run there; every one failed, and every one passes here:

| Finding | Test (this commit) | On the reviewed code |
|---|---|---|
| 1 | `crowding::tests::expire_and_crowding_cost_what_expires_not_the_map` | 200 `expire` took 143.9 ms and 200 `crowding` 9.8 ms against a 2 ms bound (debug) |
| 2 | `exec::tests::a_would_fail_keeps_the_lock` | the same state at the same leader and slot after a would-fail: `sent`, not `inflight_same_state` |
| 3 | `exec::tests::settlement_from_the_chain` (corrected), `a_failed_landing_found_by_the_expiry_check_counts_against_the_cap` | 1 outcome line, no amend; failed fees 0 instead of 5,000 |
| 5 | `config::tests::cleartext_secrets_are_refused` | a `token_env` over `http://` loads |
| 6 | `tools/test-run-w.sh` G2 (`tests/supervisor.rs`) | 95 of 96: the paused segment's would-sends made the budget unknown, the next segment ran `--shadow` with 0 |
| 7 | `exec::tests::a_send_without_an_answer_stays_open` | final at once: no open attempt, 0 reserved |
| 12 | `exec::tests::a_dry_run_catches_a_wrong_min_profit` | a re-signed bundle whose min_profit is 1 (the decision's 36,500) passes every check |

| # | Severity | Disposition |
|---|---|---|
| 1 | Major | **Fixed**: incremental expiry, per-pool counts kept on insert and expiry; measured below |
| 2 | Minor | **Fixed**: only a landing releases early; a would-fail counts once toward cooling |
| 3 | Minor | **Fixed**: the wallet record amends a status-first landing; each landing counted once; partial money reported |
| 4 | Minor | **Partly**: the max is documented (not the union); the map is not carried across segments (static list = Stage 0) |
| 5 | Minor | **Fixed**: a header key over plain http (or udp) needs `no_tls_endpoint`, at load and at start |
| 6 | Nit | **Fixed**: the supervisor ignores a non-sending segment's would-sends |
| 7 | Minor | **Fixed**: left without an answer = open until landing or expiry; an answered refusal is final |
| 8 | Minor | **Fixed**: a light leader read before the fire; the PoH lookup after it |
| 9 | Minor | **Fixed**: decisions `band` is the executor's; `band_at_opp` keeps the engine's |
| 10 | Minor | **Fixed**: `crowded_skip`, `crowded_pool` (queue drop only), `would_rate`, `would_rate_crowded` |
| 11 | Nit | **Fixed**: the pump never removes a waiter it did not grant |
| 12 | Minor | **Fixed**: the dry run decodes amount_in, min_profit, tip and accounts from the signed bytes |
| 13 | Nit | **Fixed**: the refund uses the engine's journaled time |
| 14 | Nit | **Mostly fixed**: behavioural dry-run, token-renewal and outage tests; the netcount spawn gap is documented |
| 15 | Nit | **Fixed**: the last leg's output |
| 16 | Nit | **Fixed**: per-attempt cooling, `ungated_*` counters, a dropped canary send not counted |
| 17 | Nit | **Partly**: dead fields removed, canary limits and `tls` fixed; the nonce builders and accounts are kept by plan |
| 18 | Nit | **Fixed** (documented) |

**1 (major, hot path).** `src/crowding.rs`:
- Every (pool, signer) pair is one node of a recency list (a slab with prev/next indices), oldest landing first. A landing
  moves its pair to the newest end (a landing stamped earlier than the newest is counted from the newest time, so the list
  stays ordered). `expire` pops from the oldest end while the pair is a window old: its work is the pairs that expire plus
  one look at the oldest. A pool's count is its signer map's length, kept by each insert and expiry, so `crowding` is two
  lookups. Counts are as of the engine's last housekeeping (≤ a few ms against 6 h; replay calls it at the same journaled
  times).
- New global cap: 1,000,000 pairs (the least recently landed goes first, `evicted`); the 10,000-per-pool cap stays.
- Tests: `expire_and_crowding_cost_what_expires_not_the_map` (105k pairs: the work counter is exact, 1 look per call with
  nothing due, 501 for 500 due; 200 calls of each under 2 ms, where the reviewed code took 18 ms and 3.6 ms in a release
  build), `a_pair_expires_a_window_after_its_last_landing`,
  and the existing `crowding_counts_landed_arbitrage_signers` (now expiring at the housekeeping).
- Measured with the review's probe, kept as `crowding::probe::probe_activity_costs` (`--ignored`), release, single
  thread, median of 3 runs before and after on this machine (load average 3-4 from other builds):

| pools × signers | pairs | `expire`, nothing due: before → after | at 200 calls/s | `crowding()`: before → after | a landing (new / again): before → after |
|---|---|---|---|---|---|
| 500 × 20 | 10,000 | 8.41 µs → 0.001 µs | 1.7 ms/s → 0.0002 ms/s | 0.066 µs → 0.002 µs | 113 / 101 ns → 156 / 123 ns |
| 21 × 2,000 | 42,000 | 27.4 µs → 0.002 µs | 5.5 ms/s → 0.0004 ms/s | 7.63 µs → 0.003 µs | 102 / 164 ns → 147 / 210 ns |
| 2,000 × 50 | 100,000 | 94.1 µs → 0.002 µs | 18.8 ms/s → 0.0004 ms/s | 0.168 µs → 0.002 µs | 122 / 164 ns → 179 / 184 ns |
| 50 × 5,000 | 250,000 | 171.6 µs → 0.001 µs | 34.3 ms/s → 0.0002 ms/s | 17.8 µs → 0.002 µs | 127 / 201 ns → 234 / 230 ns |
| 100 × 10,000 | 1,000,000 | 1,435 µs → 0.002 µs | 287 ms/s → 0.0004 ms/s | 36.0 µs → 0.002 µs | 170 / 169 ns → 237 / 180 ns |

  A pair that expires costs 16-55 ns once (each expires once per window: at 100k pairs about 5 a second). The price is
  on the landing path: 43-107 ns more for a new pair and 11-46 ns more for a known one (the list's upkeep), about 0.1 ms
  of engine time a second at 1,000 landings a second. The `route_in` cost per decision on a 5,000-signer pool falls from
  18 µs to under 0.01 µs.

**2 (minor).** `Outcome::is_final` is a landing only (`processed`, `finalized`): the sink's INPUT 5 `release` is false for
`accepted`, `would-fail`, `lost-auction`, `dropped` and `rejected`, so the entry is held for its hold and the attempt
stays open until its landing or its blockhash's expiry (PLAN WP-07's final). A new leader for the same state is still
allowed, as item 4 says. Each attempt's first would-fail counts toward its token's cooling; the bundle's further ones are
`cool_repeat`. Test `a_would_fail_keeps_the_lock` drives every result kind through the real Jito sink: no release; the
same state, leader and slot → `inflight_same_state`, the later slot of the same leader → `inflight_same_leader`, after
the hold → sent, and a `processed` releases at once. `the_route_checks` now needs 25 attempts' would-fails to cool.

**3 (minor).** A final remembers what its landing adds to the money (`Final.counted`), its source and whether the
wallet record came. A landing the expiry check found counts the base fee (exactly what a one-signature bundle at CU
price 0 pays; a failed one also against the failed-fee cap, at once) and an unknown round trip (`money.round_trip_unknown_total`).
Its wallet record then writes an amend line (`amends: "statuses"`, with the fee, CU, events, `delivered`,
`round_trip_on_chain` and the running failed-fee total) and replaces what was counted: the landing, win and tip once, the
fee and round trip as recorded. `settlement_from_the_chain` now asserts the consistent totals (tips 2 × 31,499 with round
trips 49,000 + 21,000, fees 15,000, nothing unknown) instead of the inconsistent ones, and a new test covers a failed
landing found first by the expiry check (stops the sender at the cap; the wallet's 6,000 replaces the 5,000).

**4 (minor): partly.** Documented in `src/crowding.rs` and MEASUREMENT §4.32: a route's count is the larger of its two
pools' counts (the union needs a set intersection per decision; a route's bots mostly arbitrage both pools; in Stage 0
only bucket 2 ranks and the static list sets it). Not done: carrying the map across segments. A preload would change
decisions, so it must be journaled for replay (go-live gate item 3: a recording that replays identically), which is a
new boot record for WP-09's replay; until then WP-00's 21-pool list is Stage 0's crowding, and the partial map is
recorded in `signers_6h` for analysis. Open issue below.

**5 (minor).** `config::cleartext_check` treats a header key (`token_env`, `jito_auth_env`, sent with every request and
keep-alive) on a plain `http://` or `udp://` URL (LandX's key starts every UDP packet) as clear text, like a `${...}` in the
URL: refused unless `no_tls_endpoint` records that the provider has none (the note names the key). `Path::new` checks the
expanded URL and the expanded `ping_url` the same way (a URL that is wholly `${...}` has no scheme before). The maintained
configs pass (their header-key http paths are disabled). The two send tests against a local plain-http server now record
the exception, and the haan test first shows the refusal.

**6 (nit).** `deploy/run-w.sh` (`spent`): a segment whose meta.json `run.mode` is `shadow` or `dry_run` (written before
anything could be sent) has would-sends in its attempts, not sends; a missing or unreadable meta.json keeps the fail-safe
rule. The fake binary of `tools/test-run-w.sh` writes `run.mode`, and check G2 covers a paused segment that dies before its
first status line.

**7 (minor).** `jito::refused_code` splits SendBundle's gRPC statuses: invalid argument, resource exhausted, permission
denied, unauthenticated, failed precondition, out of range, unimplemented and not found are the block engine's refusals
(`BundleError::Refused`); a timeout, `unavailable`, `unknown`, `internal`, `aborted`, `data_loss` (also what tonic reports
for a transport failure after the request may have left) and `already_exists` are not (`Other`). `send::Refusal` carries
`answered`, and copies.jsonl's `t_ack` is set for an HTTP status or a gRPC refusal only. `Exec::on_fired` keeps a copy
that left without an answer open like an accepted one (cross-checks, expiry check, wallet landing; its entry and its
5,000-lamport reservation kept; `send_unanswered`; its final line's `error` is `send: <reply>`). Only a copy that never
left (`drop_*`) or one refused by an answer (`send_refused`) is final at once.

**8 (minor).** `LeaderBook::kind_at(slot)` reads the schedule's leader and its kind under the read lock (no places,
RTTs, encodings or next leader); `Exec::leader_seen` uses it, and the attempt line keeps the full snapshot after the fire.
The engine looks the trigger's PoH position up after `decide` returns (`Exec::note_poh`), so the shared PoH index is no
longer read before the fire. `inputs()` p50 2.3-2.4 µs → 0.80-0.86 µs (`exec::tests::probe_decide_costs`, a 3-validator
book); the live `decided → signed` p50 is 51-53 µs (was 53-56 µs).

**9 (minor).** `Decided.band` is the executor's band (at the size it would trade); decisions.jsonl `band` takes it once
the executor reached the route checks, and `band_at_opp` keeps the engine's at its priced size. `a_shadow_run_records_would_sends`
asserts the decision's `band` is the attempt's.

**10 (minor).** The 100k skip is `crowded_skip`; the would-send rate model is `would_rate` / `would_rate_crowded`;
`crowded_pool` and `rate_queue_timeout` are only the real queue's drops (copies.jsonl `drop`, counted `drop_*`).

**11 (nit).** `send::budget::grant` (one pump round) skips a waiter whose receiver is gone instead of removing it, so an
`acquire` that finds its waiter gone was granted; a waiter abandoned by a dropped task goes a second past its deadline,
and closed waiters neither block the fast path nor count as waiting or in λ. Test `a_timed_out_waiter_is_left_for_its_acquire`.

**12 (minor).** `verify_bundle` decodes the route instruction from the signed bytes (`route_of`) and adds `route_data`,
`route_amount_in` and `route_min_profit` (against the attempt's `size_lamports` and `min_profit_onchain`, taken from the
decision, never from the built message), `min_profit_covers_tip` (the signed min_profit covers every System transfer
from the payer + the base fee + `margin_floor`: the "cannot lose" property from the signed bytes alone) and
`route_accounts` (payer authority, the WSOL quote account, each leg's output account, venue program and pool); `tip_last`
also checks the tip comes from the payer. Test `a_dry_run_catches_a_wrong_min_profit`: a builder fault (a test-only hook
in `Exec::build`) that signs min_profit 1 fails `route_min_profit` and `min_profit_covers_tip` in the dry run's record, a
wrong amount fails `route_amount_in`, and re-signed tampered bytes are caught. The live test decodes the signed route
(1 SOL, min_profit 40,001, two DAMM v2 legs) and passes every check. The dry run's decision costs p50 158 µs (was 142-153).

**13 (nit).** `Exec::on_settled` takes the engine's time (the journaled `t_now`), and the big-band refund uses it.

**14 (nit): mostly fixed.**
- `main.rs a_dry_run_never_sends` no longer greps `run()`: its send setup is `send_setup()`, which `run()` calls, and
  `a_dry_run_reads_no_keystore_and_builds_no_send_path` tests it: a dry run builds no path, never calls the keystore
  loader (one that panics), signs with a new throwaway key each run; live and canary read the keystore once each and stop
  without it; shadow holds no key. The behavioural dry-run tests (`a_dry_run_signs_and_never_sends`, `a_dry_run_reads_and_simulates_only`) stay.
- `Jito::keep_token`: `keep_token_renews_at_half_life_and_backs_off` (a test hook replaces the network renewal): renewed
  at half life, failures retried after 1 s then 2 s, each an event with `stale`.
- Stream outages: the bookkeeping is `Outage`, tested by `stream_outages_are_one_down_and_one_up`.
- Not fixed: a task spawned on the send path without the scope escapes `netcount`. No such call exists; the counter's
  process total still sees it. A guard would need every spawn site wrapped, out of proportion for a nit.
- Findings 2, 3 and 12 have failing-then-passing tests (table above).

**15 (nit).** `last_leg_out` takes the `out` event of the highest leg (the last without leg numbers) for the money and
`round_trip_on_chain`; tested with three legs and out of order.

**16 (nit).** Cooling counts an attempt once (2). A decision a closed gate refused counts `reject_gate_*` and `ungated_<reason>`
for what else refused it, so the `reject_*` counters sum to the refusals (asserted in the pause test). A canary attempt whose
copy never left is not one of `count` (`a_dropped_canary_send_is_not_counted`).

**17 (nit): partly.** `RouteIn::trig_cu_price` / `rival_cu_price` are gone, and with them the engine's per-transaction
`pool_prices` upkeep and the p75 sort in `route_in` (engine-thread work nobody read). A canary run's meta.json
`limits.max_size_sol` is its own cap (`max_size_src` `canary`). `send_paths[].tls` is null for a URL that is wholly
`${...}`. Kept: `build::advance_nonce_ix` / `nonce_value` and `[send_policy.direct] nonce_accounts`, the direct
experiment's (PLAN item 3 keeps them behind it), now documented as such.

**18 (nit).** Documented in `exec.rs` and MEASUREMENT §4.32: shadow and dry runs hold no Jito client, so the token check
is not modelled in their would-sends.

**Incidental.** WP-02's `rec::tests::write_errors_are_losses_never_records` failed once in a full run under load (load
average 6): the core writer queues its `recorder_io_error` event while it handles a sync that the events writer may have
handled already (alone it passed 15 of 15). The test now syncs twice before reading the events; the full lib suite passed
3 times since.

**Deviations from the review's fixes.**
- A Jito `processed` releases the in-flight entry (the review's fix), though PLAN WP-07's final needs the wallet's
  confirmation: the attempt itself stays open until the wallet record or the expiry.
- Explicit refusals are told from no answer by gRPC status code; an unknown code counts as no answer (fail-safe: the
  reservation is held until expiry).
- Reasons renamed: `crowded_skip` (was `crowded_pool` for the skip) and `would_rate` / `would_rate_crowded` (were
  `rate_queue_timeout` / `crowded_pool` for would-sends); MEASUREMENT A.1 and A.7 updated.

**Open issues.**
- (WP-09) Crowding across segments: a journaled preload of the activity map from the previous segment, so the map can
  mature in a campaign; until then the static list ranks.
- (WP-07) The bot's money counters stay provisional: a status-first landing whose wallet record never comes keeps the base
  fee and an unknown round trip (`round_trip_unknown_total`); the ledger should settle it by signature.
- (WP-07) `explicit refusal` classification is by gRPC code only; WP-07's reconciliation should confirm that no refused
  bundle ever lands.
- (WP-06) The tip and the band move to `src/tip.rs` / `[bands]`; `verify_bundle`'s `min_profit_covers_tip` and
  `route_accounts` must follow WP-06's new instruction order (ATA close, loaded-data limit).

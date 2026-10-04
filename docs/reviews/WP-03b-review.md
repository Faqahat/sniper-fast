# WP-03b review: chain fetch (adversarial)

**Scope:** the uncommitted lane `lane/wp-03b` (base ab08b9a): `git diff` plus `src/chainfetch/`, `src/rpc/tests.rs` and `testdata/rpc/`. It is checked against:
- PLAN WP-03b (items 1-5, config keys, offline and field acceptance, measurement outputs);
- PLAN-ADDENDUM I-1;
- the Haan/Shyft items in the implementer's report (token buckets, 429 retry and failover, cached DNS, warm connections);
- MEASUREMENT rev 2.4.

**Verdict: not ready to commit.**
- 1 blocker. With the shipped provider split, the backfill starves the slot index.
- 5 majors.
- 18 minors and nits.

The blocker and four of the majors are shown on the running code by a probe (§2), not only by reading.

## 1. Reproduced checks

| Check | Result |
|---|---|
| `cargo build --release` (lane target) | ok: only the 3 known warnings (engine.rs:104 dead fields; main.rs:400 and :408 irrefutable `if let`) |
| `cargo test --release` | 214 passed, 0 failed, 2 ignored: lib 190 + 1 ignored, bin 10, legacy_fixtures 4, meta_config_hash 1, runtime_isolation 2 + 1 ignored, stop_path 6, supervisor 1. That is 23 new tests over HEAD's 191 |
| `arbx check --config deploy/arbx-stage0.toml` | exit 0. Prints `rpc budgets: haan 4/s, shyft 4/s; boot retries for 90 s` and the role split `wallet=haan+shyft blockhash=haan backfill=haan+shyft slotidx=shyft sample=shyft` |
| `arbx check --config deploy/arb.toml` | exit 0. `public 4/s, helius 4/s, shyft 4/s, haan 4/s, erpc 4/s`: every provider is capped by `default_max_rps` |
| toolkit `python3 -m unittest discover -s .` | 78 OK, 4 skipped |

## 2. Probes run for this review

The probe is a scratch crate, not part of the repo: `scratchpad/e2/rev-03b/probe/src/main.rs` in this session's scratchpad.
- It links the lane's library through its public API and was built in the shared lane target.
- Its build artifacts were deleted afterwards.
- Raw outputs: `scratchpad/e2/rev-03b/p{1-on,1-off,2,3,4,5b-short,5b-control,7}.txt`.

| Probe | Setup | Shows |
|---|---|---|
| P1 | The real `chainfetch::Service`, `RoleClients`, `Rpc::call_bounded` and `Registry` token buckets against two local fake HTTP providers (2 ms answers). Split as shipped: haan {wallet, blockhash, backfill}, shyft {slotidx, sample, backfill, wallet}, 4 req/s each. Load: 3.7 confirmed slots/s, 30 non-PumpSwap D1 signatures/s (PLAN §0: 16-35/s), real time, 150 s. Run once with the backfill on `auto` and once held at 0.01/s (control). Each fake block lists its slot's D1 signatures. | Finding 1 |
| P2 | tokio paused clock, a fake `Chain` that never has the transaction. One attempt signature every 1.72 s (2,090 bundle attempts/h, redesign-final X2), 16 simulated minutes | Finding 2 |
| P3 | `Backfill` API: max_backlog 4, take one, push one, `done(Failed)` | Finding 3 |
| P5 | Paused clock, D1 at 30/s, slots confirmed and indexed, a fake chain that answers every getTransaction. Backfill cap 5/s (shortfall) vs 40/s (control), default `max_backlog` 200,000, 8 simulated hours, VmRSS every 30 min | Finding 3 |
| P4 | Boot policy. Provider a answers a JSON-RPC error, provider b answers correctly | Finding 4 |
| P7 | A bounded call refused for lack of a token | Findings 7 and 8 |

## 3. Findings

### 1. BLOCKER: the backfill starves the slot index on Shyft

**Location:**
- src/rpc.rs:94-100. `Role::priority`: Backfill, Slotidx and Sample are all priority 2.
- src/rpc.rs:211-248. `Limiter::threshold` / `take`: waiters are not queued, so a newly arrived caller can take a token ahead of callers that are sleeping.
- src/chainfetch/backfill.rs:102-105. `target_rps` = 1.25 × need, capped by the providers' configured `max_rps` sum (8/s), not by the capacity actually left.
- src/chainfetch/mod.rs:536-539 (backfill: up to 16 in flight, `Bounds::fetch(2 s, 1)`) and :557-561 (slot index: at most 4 in flight, `Bounds::fetch(5 s, 1)`).
- src/chainfetch/slotidx.rs:186-194 and :225-226. A `rate_budget` failure backs the slot off 1, 2, 4, 8, 16 s, then writes `status: "error"`.
- deploy/arbx-stage0.toml:124-127 and deploy/arb.toml:82-85. Shyft serves `slotidx`, `sample` and `backfill`.

**Problem.** The slot index and the backfill share Shyft's 4 req/s bucket at the same priority.
- The backfill's demand (need ≈ 30/s) keeps it at its 8/s target. It holds up to 16 calls on the buckets and starts new ones at up to 8/s (checked every 10 ms tick).
- The slot index's few calls lose the tokens, fail with `rate_budget` after 5 s and back off. The slot index gets almost nothing.

Everything built on the slot index goes with it:
- `idx` for backfilled records (only getTransaction's `transactionIndex` remains);
- the D2 path (failed transactions join the denominator only when the slot index finds them);
- `missing` fork evidence for WP-04;
- the confirmed `slotidx` blockhash source (WP-05);
- the coverage sampler, which also fails with `rate_budget`.

The field acceptance "slot index covers ≥ 99.9% of confirmed slots" cannot pass with this config. The commit-body capacity text (the slot index fits on Shyft and the backfill gets 1-1.5 req/s) is inverted: the backfill takes about 5.4 req/s and the slot index about 0.1.

**Proof (P1, 150 s):**

| | backfill `auto` (shipped) | backfill held at 0.01/s (control) |
|---|---|---|
| Shyft getBlock(signatures) served | 18 in 150 s (0.12/s) | 37 per 10 s (3.7/s) |
| status `slotidx_lag_slots_now` at 150 s | 531, growing about 3.7 slots/s | 0 |
| registry `slotidx/shyft` | 143 calls, 18 ok, 125 `rate_budget` | 556 calls, 556 ok |
| registry `sample/shyft` | 2 calls, 2 `rate_budget` | 2 ok |
| Shyft getTransaction (backfill) | 583 (3.9/s) | 0 |
| Haan getLatestBlockhash / getTransaction | 370 (2.5/s) / 230 (1.5/s) | 370 / 2 |
| status need / have rps | 30.2 / 5.47 | 30.1 / 0 |

The tests could not catch this. `FakeChain` (src/chainfetch/tests.rs:75-85) ignores roles, buckets and priorities, and no test puts two roles on one bucket.

**Fix:**
- (a) Give the slot index, and the sample, precedence over the backfill. Options: slotidx at priority 1, a per-role share of each bucket, or a FIFO waiter queue in `Limiter` so a sleeping waiter is not overtaken.
- (b) Size the backfill's rate from the capacity actually spare: its providers' `max_rps` minus what other roles used recently, from the registry. Today it uses the configured sum, and about half of its calls end in `rate_budget` (finding 10).
- (c) Until (a) lands, keep the backfill off the slot index's provider in both deploy configs.
- (d) Turn P1 into a test: the real `Rpc` and `Registry`, two roles on one bucket, asserting that the slot index gets ≥ 3.7/s while the backfill has demand.

### 2. MAJOR (live): wallet source (b) polls every attempt signature about 22 times

**Location:**
- src/chainfetch/mod.rs:452-461. `Note::Ours` → `Wallet::found(F_OURS)`.
- src/chainfetch/mod.rs:541-545. Every due signature is spawned at once, with no rate or in-flight cap.
- src/chainfetch/wallet.rs:119-132. Retries after 1 s, 5 s, then every 30 s until 10 minutes.
- src/exec.rs:1172. The tap runs before the spawned fire (:1181), so attempts that are sim-gated or never sent are polled too.

**Problem.**
- Most bundle attempts never land: Jito drops a losing bundle.
- Each signature is fetched at 0, 1, 6, 36, 66, … 606 s. That is about 22 `getTransaction` calls, all `not_found`, at priority 1, the engine's priority.
- PLAN item 1 expects "a few calls per minute".

**Proof (P2).** At 2,090 attempts/h, one signature each:
- wallet getTransaction per minute: 116, 186, 254, 325, 394, 465, 532, 603, 672, 742, then about 800 from minute 10;
- steady state 13.4/s. That is more than the whole Haan + Shyft budget of 8 req/s.

In a live run these calls take every priority-1 token on both providers:
- the engine's lookup-table fetches compete with them as equals;
- the backfill, the slot index and the sample get nothing;
- our own landed transactions' wallet records queue behind hundreds of signatures that never landed.

Shadow is unaffected: it makes no `Exec::send` call.

**Fix:**
- Track (b) and (c) signatures with batched `getSignatureStatuses` (up to 256 per call, about once a second, role `wallet`). Call `getTransaction` only once a status shows the signature landed, or once (a) names it.
- Stop tracking a bundle signature a few slots after its target slot, or once its nonce has advanced.
- Cap the wallet role's in-flight calls.
- Add P2 as a test with a bounded call rate.

### 3. MAJOR: `known` leaks every signature still queued at its 15-minute mark

**Location:**
- src/chainfetch/mod.rs:601-605. `second()` pops `known_order` and keeps an entry that is still `queued`. Nothing revisits it.
- src/chainfetch/mod.rs:514-516. A signature dropped by `push()` gets `queued = false`, but its order record is already gone.
- src/chainfetch/backfill.rs:183-194. `done()` calls `trim()` and discards the signatures it drops, so their `queued` flag stays true.
- src/chainfetch/backfill.rs:151-179. A queued item is never given up at 10 minutes. `GIVE_UP_NS` is checked only after a failed fetch.

**Problem.**
- With the shipped budgets the backlog grows by need − have (about 25/s in P1). It reaches `max_backlog` (200,000) in about 2.2 h.
- Every signature still queued 15 minutes after it was first seen keeps its `known` entry for the rest of the run, however it leaves the backfill: fetched, trimmed or given up.
- Once the backlog is full, about 25 entries/s leak: about 2M a day, roughly 0.4-0.5 GB.
- The 200,000-item backlog is also almost all signatures older than the 10-minute idx window. The backfill serves the newest first, so these are only ever dropped, never fetched.

**Proof:**
- P3. `done(#4, Failed)` returns `gave_up = false` and `dropped_total` goes up by 1: `trim()` removed signature #1 and did not report it.
- P5. With the control (no shortfall), VmRSS is flat at 25.2 MB from 30 min to 8 h. With the shortfall, the backlog is constant at 200,000 from about 2.2 h on, yet VmRSS keeps climbing: 144 MB at 2.5 h, 182 MB at 3.5 h, 252 MB at 5.5-8 h. The steps are hash-table doublings while `dropped_total` reaches 519,942.
- Apart from `d2_absent`, no code path removes a `known` entry other than :604.

**Fix:**
- When an item leaves the backfill (fetched, dropped or given up), remove its `known` entry if it is past `KEEP_NS`. Alternatively, re-queue the order record while the entry is queued.
- Return the signatures `done()` drops.
- Give up queued items 10 minutes after they were seen, and count them.
- Add a `known_now` gauge and a long paused-clock test (P5's shape) asserting it stays bounded.

### 4. MAJOR (I-1 hole): an "answer" error from the first provider aborts the boot without asking the others

**Location:**
- src/rpc.rs:1010-1021. `retryable = limited || !(code_is_answer(code) || code.is_none())`.
- src/rpc.rs:700-705. `if !f.retryable { return Err(f); }`.
- src/rpc.rs:616-623. Every boot-phase `call` is a bounded call.

**Problem.**
- During the boot policy, these replies end the call at once, and with it the boot:
  - a JSON-RPC error without a code;
  - an error with a code `code_is_answer` lists: -32600/-32601/-32602, -32001, -32004, -32007, -32009, -32014, -32015, -32016.
- The next provider is never asked.
- HEAD's failover asked the next provider on any error, and so does the Run phase now. This is a regression against the WP's own goal (I-1: "only a sustained failure aborts").
- Provider-specific answers do happen: a key or plan problem, a method not enabled on a plan, a parameter limit, a gateway message without a code.

**Proof (P4).** Provider a answers the error and provider b answers correctly; `Phase::Boot` with a 20 s budget:
- `{"message":"upstream connect error"}` (no code): ERROR in 0.00 s, b asked 0 times. In `Phase::Run` (failover): ok.
- `-32601 Method not found`: the same.
- `-32602 Invalid params`: the same.

**Fix:**
- In the boot policy, treat a non-retryable answer as provider-specific until every provider has given it. Fail early only on a unanimous answer.
- Make `code.is_none()` retryable everywhere.
- Add P4 as a test.

### 5. MAJOR (integration): the lane collides with master 6f8fd3c

**Location:**
- src/rec/mod.rs:128-131 and :171-173. `WALLET = S(28)`, `SLOTIDX = S(29)`, `TXFETCH = S(30)`, `STATIC` of 31.
- Master's 6f8fd3c ("post": WP-04 work, 24 files, +5,058 / −1,041) assigns `COMMITS = S(28)`, `DECISIONS = S(29)`, `ALTS = S(30)`, also with `STATIC` of 31. It also rewrites:
  - engine.rs (+3,084 lines, including `process()`, where the tap sits);
  - exec.rs, feeds/{mod,grpc}.rs, config.rs, main.rs;
  - both deploy configs and MEASUREMENT §4.8/§4.10.

**Problem.**
- Every file this lane touched outside PLAN §3.2's lane list also changed on master. §3.2 says WP-03b "adds only new files under `src/chainfetch/`, plus `rpc.rs`, its own config struct and one wiring block".
- The stream ids collide. A merge that keeps both constant blocks without renumbering routes one stream's records into another stream's spec and file: the `STATIC` order defines the files.

**Proof.** `git log --oneline ab08b9a..master` shows 9647c7f, 9bfd72d, d5c8d67 and 6f8fd3c. `git show 6f8fd3c -- src/rec/mod.rs` shows the three constants and `STATIC` going from 28 to 31.

**Fix.** Rebase onto master before committing:
- renumber to `S(31..33)` with `STATIC` of 34;
- place the engine tap again in master's `process()`;
- merge the status-line sections;
- re-run `cargo test`, both `arbx check`s, the toolkit tests and P1.

### 6. MAJOR (budget): the blockhash poll takes 62% of Haan at the engine's priority, unconditionally

**Location:**
- src/chainfetch/mod.rs:573-577. The poll runs every 400 ms whatever the ring holds.
- src/rpc.rs:97. `Blockhash` is priority 1, the same as `Engine`.

**Problem.**
- The poll spends 2.5 of Haan's 4 req/s on `getLatestBlockhash`, even when the slot index or `blocks_meta` has just given a confirmed hash.
- Nothing consumes the ring in Stage 0: sends use durable nonces, and WP-05 is the first consumer.
- At equal priority the poll competes with the engine's lookup-table fetches (I-6) and with the wallet fetches.

**Proof (P1).** Haan carried the poll at 2.47/s plus the backfill at 1.53/s: the bucket was full.

**Fix.**
- Poll only when the ring has no confirmed entry from another source in the last N ms (for example 1 s), or at priority 2.
- Record the polls skipped.
- The PLAN default `blockhash_poll_ms = 400` can stay as the poll's floor.

### 7. MINOR (measurement): `throttled` counts nearly every request

**Location:** src/rpc.rs:236-241 (`take` returns `now - start`, read from two `Instant::now()` calls) and :350.

**Problem.** A token granted at once still yields a non-zero wait of some nanoseconds, so `record()` counts the request as throttled. resources.jsonl `throttled_delta` therefore equals the number of answered requests.

**Proof:**
- P1 registry: `blockhash/haan: 370 calls, 370 ok … 370 throttled`; control `slotidx/shyft: 556 ok … 556 throttled`.
- P7: an immediate grant gives `throttled_delta: 1`.

**Fix.** Return zero when the first `try_take` succeeds, or count only after a sleep.

### 8. MINOR (measurement): `calls` counts refusals that sent nothing

**Location:** src/rpc.rs:594 and :349.

**Problem.** MEASUREMENT §4.10 says `calls` is "one count per HTTP request". A `rate_budget` refusal, which sends nothing, is counted as a call and as an error.

**Proof:**
- P7: 3 bounded calls, 1 HTTP request served, registry `calls 3`, `rate_budget 2`.
- P1: `backfill/haan` shows 598 calls for 230 requests.

**Fix.** Do not count `Budget` in `calls` (keep `rate_budget_delta`), or rename the field and add `requests`.

### 9. MINOR: the first backfill fetch can come before the slot is confirmed

**Location:** src/chainfetch/mod.rs:501 and :537.

**Problem.**
- The fetch is due `after_ms` (1.5 s) after the processed account update, with `commitment: "confirmed"`.
- When the slot is not confirmed yet, the reply is `null` (`not_found`) and the retry comes 1 s later. That spends a token from the scarce budget.
- The service already knows the confirmed slot from `Note::Slot` status 1.

**Proof.** Not measured here. Field check: the share of txfetch `err: not_found` with `attempts` on a first try.

**Fix.** Make the first try due at max(after_ms, the slot confirmed).

### 10. MINOR: the backfill launches at its configured cap and about half its calls are refused

**Location:** src/chainfetch/backfill.rs:102-105.

**Problem.** The backfill launches up to 8/s against the capacity actually left. Each refused call:
- moves its item down the 1 s / 5 s / 30 s retry ladder;
- writes a txfetch line;
- counts as a registry error.

**Proof.** In P1, 735 of 1,548 backfill calls ended in `rate_budget` (registry `backfill/haan` 368 of 598, `backfill/shyft` 367 of 950).

**Fix.** Finding 1 (b).

### 11. MINOR: D2 candidates of a slot whose getBlock failed are counted as absent

**Location:** src/chainfetch/slotidx.rs:241 (`failed()` puts the D2 list in `d2_absent`) and src/chainfetch/mod.rs:820-822.

**Problem.** A block that could not be fetched (in P1, most slots, through `rate_budget`) says nothing about its candidates. Yet they are forgotten and counted in `d2_absent_delta`, which understates the denominator.

**Fix.** Count them as `d2_unknown` and keep `d2_absent` for blocks that were read.

### 12. MINOR (recording safety): no watchdog on the service task

**Location:** src/chainfetch/mod.rs:926-932 (the spawned task's handle is dropped).

**Problem.**
- If `Service::run` ends, by a panic or otherwise, the taps keep dropping notes and wallet.jsonl stops.
- wallet.jsonl is a core stream, but nothing is lost from the recorder's point of view, so the SendGate stays open.
- Only `published_age_ms_now` grows.

**Fix.**
- Keep the handle and have the engine's status line flag `published_age_ms_now` above 5 s (run.log WARNING, events.jsonl).
- In live, close the SendGate: wallet.jsonl is the reconciliation source.

### 13. MINOR: a stream record the recorder drops still counts as covered

**Location:** src/feeds/grpc.rs:365-366.

**Problem.** `note_stream_tx` runs before `emit_grpc` and ignores whether the record was queued. A dropped exec record therefore counts as covered and is never backfilled.

**Fix.** Make `emit_grpc` return the result of `emit_sized` and call the tap only on `true`.

### 14. MINOR: the boot policy also governs the LeaderBook and other early background tasks

**Location:** src/main.rs:1060 (`leaders::start`) runs before :1133 (`set_phase(Run)`). The phase `Arc` is shared by every client made from the root.

**Problem.** The LeaderBook's `getSlotLeaders` and `getSlot` calls during the boot:
- retry for up to 90 s;
- write `rpc_boot_retry` and `rpc_boot_failed` events with role `leaders`, although the boot did not fail.

**Fix.** Give background tasks a client with its own phase (always Run), or start them after the boot.

### 15. MINOR: plain calls can now wait 10 s per provider for a token

**Location:** src/rpc.rs:525, :747 and :778.

**Problem.**
- `CALL_TOKEN_WAIT` sits outside the 3 s answer budget.
- In failover, an executor simulation or gate check, a status read or an engine table fetch can take up to about 26 s: two providers × (10 s + 3 s). HEAD took at most about 6 s.
- Stage 0 runs `sim_gate = false`, and WP-05 replaces the exec client.

**Fix.** Bound the token wait of the `exec` and `engine` roles to well under a second, or let them fail over at once to a ready provider.

### 16. MINOR: source (d) re-records the previous hour in every segment

**Location:** src/chainfetch/mod.rs:546-555 and src/chainfetch/wallet.rs:137-147.

**Problem.** The first run, 30 s in, fetches every wallet transaction of the last hour again. Each one gets a wallet.jsonl line and an INPUT `wallet_tx` in every segment, so WP-07 must de-duplicate across segments.

**Fix.** Mark records from before `stream_first_slot` (`pre_run: true`), or skip signatures the previous segment recorded.

### 17. MINOR: `max_tx_version = 1` has no fallback

**Problem.** A provider running a node older than v1 transactions refuses the parameter with -32602. That is an "answer", so it is not retried, and every getBlock and getTransaction fails.

**Fix.** On -32602, retry with 0 and record that the provider was downgraded.

### 18. MINOR: defaults apply silently to configs without `[chainfetch]`

**Location:** src/config.rs:59-61 and :138-146.

**Problem.**
- `[chainfetch]` defaults to enabled, with `default_max_rps = 4` on every provider. Any config without the section gets a running service and 4/s buckets.
- deploy/arb.toml's exec provider (`helius`, paid) is now capped at 4/s.
- `arbx check` prints the budgets, which helps.

**Fix.** Have the owner confirm the default. Consider `default_max_rps = 0` (no cap) unless the config sets it.

### 19. NIT: the cool-down refills the bucket

**Location:** src/rpc.rs:218-222.

**Problem.** `try_take` returns before updating `last` while cooling down. Tokens therefore accrue for the whole cool-down, and after an 8 s cool-down the full burst goes out at once, which is the 429 pattern again.

**Fix.** Set `last = cool_until` when the cool-down ends.

### 20. MINOR: (a) after (b) does not speed up the fetch

**Location:** src/chainfetch/wallet.rs:91-97.

**Problem.** Suppose a signature found by (b) is in its 30 s retry phase. Its account update proves it landed, but the fetch still waits up to 30 s for the next retry. That is settlement latency for WP-05 and WP-07.

**Fix.** On `F_ACCOUNT`, make the signature due now.

### 21. MINOR: missing tests

There are no tests for:
- the D2 path end to end (`Seen` → found in the block → denominator → backfill `shred_seen_landed`; absent → forgotten);
- source (b) with signatures (`Note::Ours.sigs` is empty in every test) and source (c);
- tap-drop accounting and the `chainfetch_tap_drop` event;
- `start_warm`;
- two roles on one real bucket (would have caught finding 1);
- an answer-class error from the first provider at boot (finding 4);
- a long-run memory bound (finding 3);
- the meaning of `throttled` (finding 7).

`taps_without_a_service_are_noops` asserts that no global service is installed. That makes the producer taps (feeds, engine, exec) untestable in this binary. Expose an injectable `Shared` for tests.

### 22. NITS: documentation and claims

- MEASUREMENT §4.14 places the coverage sampler in `slotidx.rs`. It is in `chainfetch/mod.rs::on_sample`.
- The comment on the exec tap says "after the firing". It runs before the spawned fire (exec.rs:1172 vs :1181).
- Two claims in the report cannot be reproduced from the lane: the tap costs (0.2/25/37/187 ns) and the "all 1,193 transactions of slot 453032285" v1 check. Neither has a benchmark or test in the tree. The repo test covers the first 30 transactions, at least 2 of them v1.
- The commit-body capacity text is contradicted by P1 (finding 1).

### 23. NIT: the status line computes percentiles it discards

**Location:** src/rpc.rs:378-398 and :415-422.

**Problem.** `by_role_json` runs on the engine thread, through the status line. It sorts every key's recent latencies under the registry lock and then throws the percentiles away. It is cheap at 4 req/s, but needless on the engine thread.

### 24. NIT: the coverage sample is about 10 MB a minute

**Problem.** The fixture's 30 transactions take 260 KB, so a full base64 block is about 10 MB. It is parsed in the blocking pool, and then about 1,200 `txjson::from_rpc` conversions run on the service task. That is acceptable, but should show in the resource budget (MEASUREMENT §5).

## 4. Status against the plan

| Item | Status |
|---|---|
| 1 Wallet transactions (a)-(d), fetch once, retry, give up after 10 min, `wallet_update_missing` | Implemented and tested for (a) and (d). (c) is a function only (WP-05, deviation 8). (b) has the load problem of finding 2 |
| 2 Backfill: what is queued, priority, auto rate, backlog drop | Implemented and tested on a fake chain. The capacity is misallocated (findings 1 and 10) and `known` leaks (finding 3) |
| 3 Slot index: idx, `missing`, skipped slots, `idx_check`, sampler | Implemented and unit-tested. Starved in the shipped config (finding 1) |
| 4 Blockhash ring: sources, staleness, disagreement | Implemented and tested. The `entries` source waits for WP-08 (`note_entry_hash` ready). The poll's budget: finding 6 |
| 5 `call_bounded`, roles, global per-(role, provider) registry, resources.jsonl `rpc` | Implemented. Findings 4, 7 and 8 |
| Config keys | All PLAN keys, plus `enabled`, `sigs_every_s`, `default_max_rps`, `boot_retry_s`, `max_tx_version` and the provider `burst` |
| Offline acceptance (5 bullets) | Each has a test. Role contention on real buckets is not modelled |
| Field acceptance | Open (owner). "≥ 99.9% of confirmed slots" fails by construction with the shipped split (finding 1) |
| Measurement outputs | All present: wallet, exec backfill + `idx_update`, slotidx, txfetch, status `chainfetch`/`coverage`, per-role stats |
| I-1 | The cmp2 case (429, then a body error) is fixed and tested: `boot_snapshot_survives_a_429_then_a_body_error`, `a_sustained_boot_failure_aborts_with_its_reason`. Stop reason `error` with the "sustained RPC failure" detail. Hole: finding 4 |
| Haan/Shyft items | Implemented: token buckets per provider with reserves, 429 cool-down, failover past a provider that is not ready, a DNS cache (tested), prewarm, HTTP/2 and TCP keep-alives, an idle `getSlot` (`start_warm`, untested) |
| Safety | No send path is added. Every new call is a read (getTransaction, getBlock, getLatestBlockhash, getSignaturesForAddress, getSlot). The taps are `try_send` into a bounded queue (non-blocking, drops counted). The engine thread gains one `Vec` copy per first copy of a transaction (`note_seen`) and the status-line read (finding 23) |

## Disposition (2026-10-04, WP-03b fix pass)

The lane was first rebased onto master (6f8fd3c, WP-04 "post"; then onto cb88257, two docs and tools commits), so the WP is one commit on top of master. Then every blocker and major and every minor and nit below except #17 was fixed. Build and tests on the result:
- `cargo build --release`: the 2 warnings master has (main.rs:422 and :430, irrefutable `if let`); none new.
- `cargo test --release`: **268 passed, 0 failed, 2 ignored** (lib 243 + 1 ignored, bin 11, legacy_fixtures 4, meta_config_hash 1, runtime_isolation 2 + 1 ignored, stop_path 6, supervisor 1). That is master's 226, the lane's 23 and 19 new tests. The lib suite ran 3 more times, stable.
- Toolkit `python3 -m unittest discover -s .`: 79 OK, 4 skipped. `arbx check` exits 0 on `deploy/arbx-stage0.toml` and `deploy/arb.toml`.

The probes' shapes became tests: P1 twice (on tokio's clock with the real buckets, and with the real `Rpc`, `Registry` and HTTP), P2, P3, P4, P5, P7.

| # | Disposition | What was done | Tests |
|---|---|---|---|
| 1 | Fixed | (a) The bucket (`rpc::Limiter`) has a queue: callers that must wait are served by priority, then in order of arrival, and nobody behind the first in line (a later caller, a lower priority) takes a token before it. Roles have four priorities: critical (boot, snapshot, exec, settle), normal (engine, leaders, provenance, wallet), index (slotidx, sample, blockhash), bulk (backfill, warm, other); the reserves are as before (index and bulk keep half the burst). (b) The backfill's cap is set every second to 0.9 x what its providers have spare: each provider's rate minus every other role's requests of the last ~10 s (a decaying count per (role, provider) in the registry; 0 while it cools down), never above the configured sum (`Chain::spare_rps`, `Registry::spare_rps`; status `cap_rps_now`, `cap_max_rps_now`). (c) Not needed once (a) landed: the backfill stays on both providers and takes only what is left. The deploy comments state the measured split. (d) Tests below. The commit-body capacity text is corrected | `chainfetch::tests::the_slot_index_keeps_up_while_the_backfill_has_demand` (P1, 150 s on tokio's clock, the deploy split on real buckets: 553 confirmed slots, the slot index at most 1 slot behind, none of its calls refused, 1 poll; backfill 3.87/s, 577 on Haan and 9 on Shyft, 12 refused); `rpc::tests::the_slot_index_goes_before_the_backfill_on_a_shared_bucket` (real `Rpc`, `Registry` and HTTP, one 4/s bucket, 16 backfill callers: 22 of 22 slot-index calls at 3.7/s served, none refused); `rpc::tests::the_bucket_queue_serves_by_priority_then_in_order` |
| 2 | Fixed | A signature known only from (b) or (c) is watched, not fetched: one `getSignatureStatuses` (up to 256, `searchTransactionHistory` false, role wallet) every 2 s while any is watched. It is fetched once a status shows it landed, or (a) / (d) names it; after 90 s without a status it is `unlanded` (counted). The wallet's getTransaction calls are capped at 4 in flight and the statuses call at 1. The exec tap moved into the fire task, after each firing (the first send and every bundle resend), with only the copies that left (`t_sent` set): `chainfetch::note_fired`. The wallet coverage counts landed signatures only. **Deviation:** the watch ends after a fixed 90 s, not "a few slots after the target slot or once the nonce advanced": the tap knows neither (WP-05 can narrow it) | `our_attempts_are_watched_with_batched_statuses` (P2, 16 min, 558 attempts: 481 statuses calls, 3 getTransaction for the 3 that landed (by status, by (a), by Jito (c)), at most 31 calls a minute against about 800 before, 504 never landed); `the_exec_tap_reports_the_copies_that_left` |
| 3 | Fixed | Every signature that leaves the backfill without a fetch is reported (`Backfill::take_left`: dropped past `max_backlog`, including the drops inside `done()`, and expired), and its `queued` flag is cleared. Queued items, waiting or waiting to retry, leave 10 minutes after they were seen (`Backfill::expire`, once a second; `expired_delta`). A refusal goes back to the queue unchanged. The `known` cleanup now looks again later at an entry still in the backfill, and removes one past 15 minutes. The wallet fetch and the sampler created `known` entries with no order record, a second leak; they now get one (`Service::know`). New gauges: `known_now`, `stream_now`, `wallet_sigs_now` | `memory_stays_bounded_while_the_backfill_falls_short` (P5 shape, 40 min, 30/s against a 5/s backfill: `known_now` flat at 27,000 from minute 15 (15 minutes of signatures), backlog at most 14,963, 44,979 expired); `backfill::tests::done_reports_what_it_drops_and_refusals_requeue` (P3), `queued_items_expire_and_the_cap_binds` |
| 4 | Fixed | In a bounded call, and so in the boot policy, a JSON-RPC error that states a chain fact (-32007, -32009 skipped slot, -32015 unsupported version) ends the call at once. Any other error answer is taken as that provider's own: it is asked no more in this call and the others are. The call fails with it only when every provider refused ("every provider refused the request"). An error without a code (a gateway's message) is retryable everywhere | `boot_asks_every_provider_before_an_error_answer_aborts_it` (P4: no code, -32601, -32602 from the first provider: the boot completes from the second in under 2 s; -32602 from both: fails at once, 2 attempts; -32007: final at once, the second provider not asked) |
| 5 | Fixed | Rebased onto master. `WALLET`, `SLOTIDX`, `TXFETCH` are `S(31)`-`S(33)`; `STATIC` has 34 entries, master's commits, decisions and alts keep 28-30. The engine tap sits in master's `process()` (after `record_rival`). The status line carries WP-04's sections and `chainfetch` / `coverage`. `Config` has `alts`, `accuracy` and `chainfetch`; `arbx check` prints both WPs' lines. MEASUREMENT is revision 2.5 (2.4 is WP-04's), with the stream-class rows and the INPUT and event lists merged | the full suite, both `arbx check`s, the toolkit |
| 6 | Fixed | `Blockhash` is priority 2 (index). The poll is skipped while another source gave a confirmed blockhash learned in the last second and at most 8 slots behind the chain's newest slot (`Ring::fresh_confirmed_elsewhere`); status `blockhash.polls_delta` and `poll_skipped_delta`. `blockhash_poll_ms` 400 stays the floor | `blockhash::tests::the_poll_is_needed_only_without_a_fresh_confirmed_source`; in P1 1 poll in 150 s (370 before) |
| 7 | Fixed | `Limiter::take` returns zero for a token granted at once | `refusals_are_not_calls_and_immediate_tokens_are_not_waits` (P7) |
| 8 | Fixed | A `rate_budget` refusal sent nothing, so it counts only as `budget` (resources `rate_budget_delta`, status `by_role.rate_budget_delta`), not as a call or an error. `calls` = `ok` + `errors` = requests sent | the same test |
| 9 | Fixed | A backfill's first try waits until its slot is confirmed (the service's newest confirmed slot), at most 20 s after the signature was seen; status `deferred_delta` (once per signature) | `the_first_backfill_try_waits_for_the_slot_to_be_confirmed` |
| 10 | Fixed | By #1 (b). A refused fetch goes back to the queue without a retry step or a txfetch line (`refused_delta`). In P1, 12 of 598 backfill fetches were refused (735 of 1,548 before) | P1 test |
| 11 | Fixed | The D2 candidates of a slot whose block could not be read are `d2_unknown` (`Indexed::d2_unknown`, status `d2_unknown_delta`), not absent | `shred_seen_transactions_join_the_denominator_when_their_block_has_them` |
| 12 | Fixed | `chainfetch::spawn_watched` watches the service's task. If the task ends while the run goes on (a panic), the watchdog writes events.jsonl `chainfetch_dead` {why} and a run.log WARNING, sets status `service_ok_now` false, and calls `on_dead`: `arbx run` closes the SendGate for the rest of the segment, reason `chainfetch_dead` (in live or canary; a shadow run's gate is already shadow). After 5 s with no publication it writes `chainfetch_stalled`, then `chainfetch_recovered`. **Deviation:** the check runs in the watchdog task on `rt_bg`, not in the engine's status line (the engine thread does nothing more) | `a_dead_service_is_reported_and_closes_the_gate`; `tap_drops_are_counted_and_reported` (a stop is not a death) |
| 13 | Fixed | `rec::exec::emit_grpc` returns whether the recorder took the record. The stream tap passes it on (`Note::StreamTx.recorded`). A dropped record does not cover its signature, which is backfilled; the idx check runs either way | `a_stream_record_the_recorder_dropped_is_backfilled`; `the_feed_taps_report_what_the_stream_carries` (recorder off: `recorded` false) |
| 14 | Fixed | `Rpc::with_own_phase`. The LeaderBook's client (and the warm-up loop) have a phase of their own, so they call as configured during the boot | `a_client_with_its_own_phase_is_not_under_the_boot_policy` |
| 15 | Partly fixed | A plain call of the `exec` role waits at most 1 s for a token, then fails over or fails (`Role::token_wait`). The others keep 10 s, because the engine's re-snapshot after a reconnect (WP-04, I-4) is a burst of requests that must wait out a 429 cool-down of up to 8 s. Failover already passes over a provider that is not ready while a later one is | (behaviour of `call_here`) |
| 16 | Fixed | wallet.jsonl and INPUT `wallet_tx` carry `pre_run` (the transaction's slot is before the state stream's first slot), so WP-07 can de-duplicate across segments | (field) |
| 17 | Open | No downgrade to version 0. A provider that refuses `maxSupportedTransactionVersion` 1 (-32602) now fails over to the others (#4). A provider-wide downgrade would refuse every block holding a v1 transaction anyway (slot 453,032,285 holds 181). Recorded in the open issues | |
| 18 | Fixed (owner to confirm) | `default_max_rps` defaults to 0: no bucket for a provider no `[[chainfetch.provider]]` names, so a config without `[chainfetch]` keeps unlimited providers. Both deploy configs give Haan and Shyft 4/s and set 0 for the rest: `deploy/arb.toml`'s helius, public and erpc are unlimited, as before WP-03b | `budgets_and_roles_from_the_config` |
| 19 | Fixed | No tokens accrue during a cool-down: at its end the bucket is still empty, and the first token comes 1/rate later | `token_buckets_keep_a_reserve_for_critical_roles` (extended) |
| 20 | Fixed | An (a) for a signature waiting to retry makes it due at once. A late (a) or (d) for a watched or unlanded signature makes it due too | P2 test (the (a) signature is fetched 5.2 s after its attempt, at once) |
| 21 | Fixed | Added: the D2 path end to end; (b) with signatures and (c); tap-drop accounting and its event; `start_warm` (`idle_providers_are_kept_warm`); two roles on one real bucket; an answer-class error at boot; the long-run memory bound; the meaning of `throttled`. Taps are injectable in tests: `chainfetch::with_test_service` routes this thread's taps to a test service. `the_feed_taps_report_what_the_stream_carries` drives the real `grpc::tx_stream_item` and `feeds::forward` with the WP-03 stream fixture | listed |
| 22 | Fixed | MEASUREMENT §4.14 places the sampler in `chainfetch/mod.rs` (`Service::on_sample`). The exec tap now does run after the firing. The v1 count is verified: one check on 2026-10-04 against the public RPC's block 453,032,285 found 1,193 transactions (753 legacy, 259 v0, 181 v1). Every one converted with `txjson::from_rpc` and sat at its position in the signature list. It is not kept as a test, because the block is 6.15 MB and PLAN-ADDENDUM I-11 keeps every test file in the repo; testdata/rpc/README.md records it. The tap-cost figures are not claimed anywhere in the tree. The capacity text is corrected (#1) | |
| 23 | Fixed | `by_role_json` takes no latencies and computes no percentiles (`Registry::take(.., pct: false)`) | `refusals_are_not_calls_and_immediate_tokens_are_not_waits` (by_role) |
| 24 | Fixed | MEASUREMENT §5: the sample is about 6 MB a minute (6.15 MB measured for slot 453,032,285, not the 10 MB estimated), parsed in the blocking pool, then about 1,200 conversions on the service task | |

**Files outside PLAN §3.2's list for WP-03b** (`src/chainfetch/*`, rpc.rs, config.rs, main.rs, `testdata/rpc/*`): `src/engine.rs` (the D2 tap and the status sections), `src/exec.rs` (the tap after the firing), `src/feeds/grpc.rs` and `src/feeds/mod.rs` (the stream and state taps), `src/rec/exec.rs` (`emit_grpc` returns whether the record was taken), `src/rec/mod.rs` (the three streams), `src/rec/health.rs` (resources `rpc`), `src/provenance.rs` (meta.json `rpc[]` roles and budgets), `src/lib.rs`, both deploy configs, docs/MEASUREMENT.md. The lane is based on master cb88257, so all of these already carry master's changes.

**Assumptions.** Open owner decisions keep PLAN §9's defaults (OD-1: the backfill runs at the providers' spare capacity and the shortfall is shown, `need_rps_now` against `have_rps_now`). `default_max_rps` 0 is this pass's default (#18). The 90 s watch window and the 2 s statuses period are chosen here: a Jito bundle that has not landed within a few slots never will, and source (a) normally reports a landing within about a slot. The spare-capacity estimate uses a 10 s decaying average with a 0.9 share.

**Open for later WPs and the owner.**
- #17 (above).
- #15 for the `engine` role.
- WP-05: wire `note_jito_processed` (source (c)) and read the blockhash ring. The engine's `health.blockhash_age_slots_now` / `blockhash_src_now` are still null: `BlockhashHead` inputs are journaled but not consumed. Narrow the watch of our attempts' signatures to their target slot or nonce.
- WP-08: wire `note_entry_hash` (the shreds' and entries' blockhash source).
- WP-07: de-duplicate `pre_run` wallet records across segments.
- Owner: the field acceptance (24 h). Confirm `default_max_rps` 0. OD-1 capacity: with the deploy split the backfill gets about 3.9/s against the 16-35/s needed.

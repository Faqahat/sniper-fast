# Adversarial review of docs/PLAN.md and docs/MEASUREMENT.md

**Date:** 2026-10-04. **Reviewed:** `docs/PLAN.md` (699 lines), `docs/MEASUREMENT.md` (1,031 lines) at baseline commit `66a94b6`.
**Checked against:** the arbx source tree, `docs/research/*` (redesign-final = R, wallet-synthesis = W, docs-review-synthesis = D, rival-synthesis, res-code, res-stops, res-pnl, res-engine, res-compete), the owner's measurement requirement, and the build (`cargo test --release`: 55 passed, confirmed).
**Method:** about 90 line citations were opened and compared with the code; every Stage-0 item of R §1/§4 and every failure mode in W §4/§7/§8, res-code §3 and res-stops §4 was traced to a WP; every arb-lab stream and every gap the owner listed was traced to a stream and a WP; each WP was checked for build order, file-disjointness claims and whether its acceptance can be run offline.

Severity: **blocker** = the plan cannot meet a stated owner requirement or a WP cannot reach its acceptance as written; **major** = a design or ordering error that will cause wrong behaviour, wrong data or a failed gate unless fixed before the WP starts; **minor** = an inaccuracy or gap that is cheap to fix during the WP.

## Summary

| Severity | Count | Findings |
|---|---|---|
| blocker | 1 | F1 |
| major | 13 | F2-F14 |
| minor | 30 | F15-F44 |

Line references in PLAN.md are almost all correct (see "Checked and found correct" at the end). The problems are in the design: provider limits, consistency rules, forks, accuracy scoring, money definitions, cross-segment stops, the runtime, replay placement and offline testability.

---

## Blocker

### F1. Stage 0 cannot record executed transactions for every watched account, and it regresses arb-lab's exec.jsonl
- **Severity:** blocker
- **Location:** PLAN WP-03 items 3-4 (lines 258-262) and acceptance (line 278); §6 Stage 0 exit "Recording" (line 627); Appendix A row 2; MEASUREMENT §4.14, §5.
- **Problem:** The Haan plan allows one transaction filter with one account. arb-lab used it for the whole PumpSwap program and wrote every PumpSwap transaction with its block index, read from the gRPC stream. WP-03 moves that filter to `@wallet` and covers the watched accounts with an RPC backfiller at `rps = 10` with `idx = null`. MEASUREMENT §5 itself assumes 50-150 watched transactions/s. At 10 rps that is at most 7-20% coverage, and only attempt windows ever get a block index (WP-08). The owner's requirement is "execution results for EVERY tx touching any watched account on EVERY venue, with block index ...", recorded "at least as completely as arb-lab". Stage 0 meets neither. The PumpSwap stream with block index is lost outright, and the acceptance and exit gate hide this behind "or the shortfall and its reasons are reported".
- **Evidence:** `deploy/arb-w-live.toml:117-123` ("Haan's plan allows 1 transaction filter with 1 account: PumpSwap"). `feeds/grpc.rs:324, 336-356` (`rec_exec` writes every PumpSwap transaction with `idx = TxInfo.index`). MEASUREMENT §5: "exec.jsonl.zst 227 MB/h for the whole PumpSwap program" and "50-150 watched transactions/s". res-code §3F: Haan rate-limited 297 times in p12 at far lower RPC rates. `rpc.rs:249` uses getTransaction, which has no block position.
- **Fix:**
  1. Keep the single gRPC transaction filter on PumpSwap, or on whichever program covers the most watched writes. That keeps arb-lab parity and the block index, and it gives authoritative W(T) for that venue (F2).
  2. Find wallet transactions without a transaction filter. WP-03 item 2 already puts the wallet account on the state stream. Every landed transaction the wallet pays for writes the wallet account, even when it fails, because the fee is charged. So the `txn_signature` on each wallet account update lists every landed transaction of ours, success or failure. Fetch each one with a bounded getTransaction (a few per minute) off the hot path, and cross-check hourly with getSignaturesForAddress.
  3. Size the backfiller from the measured moves/s and print the rps it needs. Make a second filter or provider an explicit owner decision, with those numbers, before the Stage 0 exit.
  4. For the block index, either fetch every slot once with getBlock (about 2.5/s, filtered to watched accounts, shared with F10) or buy a Yellowstone `blocks` filter.
  5. Remove the "or the shortfall is reported" escape from the gate, or state plainly in the plan that this owner requirement is not met in Stage 0.

---

## Major

### F2. Commit groups assume an authoritative W(T) that Stage 0 does not have
- **Severity:** major
- **Location:** PLAN WP-04 items 1 and 3 (lines 296, 303-307); R §3.2.2.
- **Problem:** WP-04 says W(T) comes from "the transaction stream (... authoritative)" or from shreds as a hint. With the WP-03 default (`@wallet` only), no third-party transaction ever has an authoritative W(T). W(T) is known only for transactions that a live shred feed forwarded through the `Interest` filter, and 5 of 10 feeds are dead. Every other group falls through to the 5 ms timeout and the quiescence rule. The WP-04 acceptance "0 decisions priced with any pending account" then holds trivially, because an unknown W(T) never stays pending. A split-route trade like AgmLJBMD's that no shred feed delivered can still be read torn if its updates arrive more than `quiescence_ms` apart.
- **Evidence:** WP-03 item 3. `feeds/mod.rs:57-64` (Interest). R §2 graft 5 ("5 of 10 feeds are dead"). res-code §1 (5 feeds delivered 0 messages in p12).
- **Fix:**
  - State the Stage-0 reality in WP-04.
  - Make the share of groups by `w_src` (`tx-stream`, `shred`, `unknown`) a WP-04 acceptance metric with a target.
  - Use the F1 PumpSwap filter as the authoritative source for that venue.
  - For routes whose group resolved by timeout, require every account of both pools to be quiet for `quiescence_ms`.
  - Add a variant of S1 in which the split-route transaction is not seen in shreds.

### F3. The parts-skew rule is over-broad, and the PumpSwap exemption is removed without knowing why it existed
- **Severity:** major
- **Location:** PLAN WP-04 item 4 (line 308); S4 (line 497); MEASUREMENT `decisions.parts_skew_slots`.
- **Problem:** "every part present, none pending, parts at most `max_part_skew_slots` (1) apart" does not say which accounts it covers.
  - Read per route (buy pool against sell pool), it refuses almost every gap, because gaps open exactly when one pool moves and the other is idle.
  - Read over accounts that a swap does not always write, it does the same. These include DLMM bin arrays off the swap path, the PumpSwap fee config and global config, and the base-mint extra.
  - Today the check covers only a CP pool's pool account and two vaults (`store.rs:58-60`).
  - The PumpSwap exemption has no comment in the code and no explanation in the research. If PumpSwap pool accounts are not written together with the vaults, removing it makes every PumpSwap pool unquotable.
- **Evidence:** `store.rs:58-60`. `pools.rs:162-163` (PumpSwap adds `PUMP_FEE_CONFIG` and the base mint as parts; DLMM arrays are followed separately). A search of `docs/research` finds no rationale for the exemption.
- **Fix:**
  - Define skew per pool, over the accounts every swap of that pool writes: CP pool, vault0 and vault1; for DLMM, lb_pair, and the arrays the quote crosses must not be pending; DAMM v2 has a single account. Never compare across pools.
  - Before removing the exemption, measure from recorded `moves.log` and `accounts.bin` how often a PumpSwap pool and its vaults carry different slots for the same `txn`.
  - Add a negative test: an idle sell pool 500 slots old must not be refused.

### F4. Forks: only `dead` slots are handled, but abandoned forks are not reported as dead
- **Severity:** major
- **Location:** PLAN WP-04 item 9 (line 313); MEASUREMENT §4.13 SLOT record (no parent); R §3.2.4 ("On a slot rollback, invalidate newer versions and refetch").
- **Problem:** At processed commitment, a slot on a minority fork can be streamed and then abandoned with no `dead` status. Its account versions stay in the store until the next write to the same account, because the store orders by `(slot, write_version)`. Routes are then priced on state that never became canonical. That is a phantom, and it breaks invariant 3.
- **Evidence:** WP-03 item 7 already records `parent`. WP-04 item 9 acts only on `dead`. `store.rs:31`.
- **Fix:**
  - Keep a slot tree from slot updates and their `parent`.
  - When a slot is confirmed, treat slots off its ancestry as abandoned: drop their versions from the 8-version ring, mark the affected routes dirty and refetch them.
  - Journal `parent` in SLOT records.
  - Add scenario S8b: an abandoned sibling fork with no `dead` status.

### F5. The accuracy monitor and the 99.5% quarantine would quarantine correct maths
- **Severity:** major
- **Location:** PLAN WP-04 item 1, third bullet (line 298); WP-07 item 4, accuracy rule (line 429); MEASUREMENT §4.34.
- **Problem:**
  - Shadow predictions come from the store at hint time and are compared with T's committed state. Any write to the pool between our snapshot and T's execution (earlier in the same slot, for example) makes a correct prediction "inexact".
  - arb-lab's measured exact-match rate for DAMM v2 was 662 of 758 (87%). A quarantine at under 99.5% over the last 200 swaps would therefore shut venues on the first day.
  - Only top-level decoded swaps are scored. R §3.3 says "every successful swap", which includes aggregator-routed ones.
- **Evidence:** `engine.rs:625-641` (the prediction uses the current store state). `engine.rs:909-942` (the check against committed state). res-code §3: "662 of 758 trigger predictions matched sqrt_price exactly".
- **Fix:**
  - Score each prediction against T's actual pre-state: the version just before T's write, from the WP-04 ring.
  - Use T's executed amounts when `exec.jsonl` has them.
  - Count "pre-state unknown" cases separately instead of scoring them.
  - Set the threshold only after measuring the corrected rate, and run the quarantine in log-only mode in Stage 0.
  - Add R §3.3's closer check: the closer's realised take against our quote at the version just before the closer, built on R4.

### F6. One of R §1's "stop doing now" items has no WP: attempts on crowded pools
- **Severity:** major
- **Location:** PLAN §1 table, WP-00, WP-05.
- **Problem:** R §1 lists "Spending 49% of attempts on the 21 pools with 150 or more bots" among the things to stop now. Stage 0 has nothing for it: the P̂ competition cells are Stage 2A, and "contested" stays false. The 5/s Jito budget keeps going mostly to pools where we win 0.4% of the time.
- **Evidence:** `redesign-final.md:66` and `:221`. PLAN.md has no matching item.
- **Fix:**
  - WP-00: rank a static list of the crowded pools (from the research analysis) last in the Jito queue, or exclude them from bands of 100k and above.
  - WP-05: add a crowding term to `Prio`, computed from the activity map (distinct arbitrage signers per pool over 6 h, from `rivals` and `pool_prices`).
  - Record a `crowded_pool` reason and report it.

### F7. The ledger's equity and category definitions contradict each other
- **Severity:** major
- **Location:** MEASUREMENT §4.42 (lines 783-798), §4.43 (lines 813-815), Appendix A.3; PLAN WP-07 item 1.
- **Problem:**
  - `equity_delta` adds `rent_locked` back, so rent counts as an asset, and snapshots include `rent_locked` in `equity_total`.
  - Yet the categories include `rent_locked`, `rent_reclaimed` and `rent_nonrecoverable`, and "Σ categories = equity_delta exactly". For any transaction that creates an account, both cannot hold.
  - The non-recoverable PumpSwap accumulator rent (1,346,200) is counted as an asset in `equity_total`, which hides a real loss.
  - R §3.7 treats rent locked as a category of the equity change.
  - Because a reconciliation miss stops trading (`reconcile_miss`), this produces either false stops or hidden losses.
- **Evidence:** MEASUREMENT lines 790-798 and 813-815. res-pnl §2 (p6#69, 2,860,040).
- **Fix:**
  - Define liquid equity and total equity explicitly. In total equity, carry recoverable rent at face value and expense non-recoverable rent when it is created.
  - Say which rent categories enter the sum and which are informational.
  - Add worked examples as golden tests: create only, create and close, accumulator creation, failed transaction, wrap, unwrap.

### F8. The equity stops cannot work across segments
- **Severity:** major
- **Location:** PLAN WP-07 items 4 and 7 (lines 422-433).
- **Problem:** The rolling-hour (0.05 SOL) and rolling-day (0.15 SOL) stops run inside the bot, but every 20-minute segment is a new process. The day stop can never fire, and the hour stop sees at most 20 minutes. run-w.sh passes only a budget.
- **Evidence:** res-stops (20-minute segments). WP-07 item 7.
- **Fix:**
  - At boot, the bot loads the campaign's equity history (the campaign ledger summary or earlier segments' snapshots, via `--campaign-dir`) and evaluates the rolling windows over it.
  - run-w.sh enforces the day stop between segments, and ends the whole campaign on a safety stop, not just the segment.
  - Test with two simulated segments.

### F9. The two-worker tokio runtime is shared by hot I/O and the new heavy background work
- **Severity:** major
- **Location:** `main.rs:502`; PLAN WP-03 items 4, 6 and 10; WP-07 item 2; WP-08 items 1 and 3; invariant 5.
- **Problem:** The state stream, the gRPC feeds, Jito sends and the Jito result stream all run on `worker_threads(2)`. The plan adds these to the same runtime:
  - getTransaction backfill;
  - full getBlock (megabytes of JSON per block);
  - getClusterNodes and getVoteAccounts;
  - QUIC RTT probes;
  - snapshots.

  One 20-50 ms JSON parse occupies a worker, which delays state updates and sends. That breaks invariant 5, and WP-02's latency gate covers only the engine thread.
- **Evidence:** `main.rs:502`. `engine.rs:522-531` and `963-972` (fetches spawned on `self.rt`).
- **Fix:**
  - Run background RPC work (backfill, blockfetch, leaders, snapshots, probes) on a second low-priority runtime, and parse large JSON with `spawn_blocking`.
  - Keep the hot runtime for state, feeds and Jito.
  - Acceptance: an offline test with a fake RPC serving 5 MB blocks. Account-update arrival to engine dequeue p99, and dequeue to `t_sent` p99, must be unchanged.

### F10. The blockctx windows and fetch rate cannot meet their acceptance
- **Severity:** major
- **Location:** PLAN WP-08 item 3 (line 458) and acceptance (line 473); MEASUREMENT §4.41.
- **Problem:** The window runs from the trigger slot to the final slot + 1. A bundle that never lands becomes final only when its blockhash expires, about 150 blocks later (WP-05 item 3). At about 2,000 attempts/h (the plan's own X2 figure), the union of windows is nearly every slot: about 9,000 slots/h, or 2.5 getBlock/s, against `rps = 1`. "≥ 95% complete within 10 minutes" is therefore impossible, and every block is megabytes of JSON (see F9).
- **Fix:**
  - Window = [trigger slot, max(landed slot, last verdict slot, trigger + 4)] + 1.
  - Deduplicate slots across attempts.
  - Derive the needed rps from attempts/h and add a backlog gauge.
  - Or fetch each slot once into a slot cache shared by blockctx, the `exec` idx and R4 (see F1).

### F11. Replay: the journal is in the wrong WP, determinism has gaps, and two parallel-lane claims are false
- **Severity:** major
- **Location:** PLAN §3.2 disjointness rules (lines 111-116); WP-09 items 1-3; WP-04 acceptance (line 324); MEASUREMENT §1.2 and §4.13.
- **Problem:**
  1. `journal.bin` is written at the engine's dequeue point (`engine.rs:328-354`), but it is assigned to WP-09, which claims "only new files plus one `Cmd::Replay` arm". WP-09 actually needs:
     - `engine.rs`: the journal emit, and an `Engine` that can be built without RPC, the runtime or the watch channel;
     - `exec.rs`: build without sending;
     - three `main.rs` arms (`replay`, `quote`, `sizefit`).
  2. Recordings made before WP-09 merges have no journal. WP-04's "replay reproduces its decisions" and WP-09's 1-hour acceptance both need a new Stage-0 run.
  3. The determinism has gaps:
     - CommitTracker timeouts (5/3 ms) fire at points that are not journaled (the spin and `recv_timeout` exits).
     - LeaderBook kind and schedule, blockhash age, Jito rate-queue outcomes and gate changes feed decision reasons, but are not all journaled.
     - `accounts` and `journal` are chain class, so they may drop records, yet replay needs zero loss and the Stage-0 exit gate (line 627) sets no threshold for chain drops.
  4. WP-08 also touches files the core lane changes:
     - `exec.rs`: `meaning` moves out, attempts gain the leader object, outcomes gain `prog_events`;
     - `build.rs`: `delivered_from_logs`.

     That contradicts its lane claim (line 112).
- **Fix:**
  - Move the journal writer into the core lane (WP-02 or WP-03), with zero-loss handling for `accounts` and `journal`: a core-class queue, or replay that detects gaps.
  - Journal an explicit TIMER event wherever timeouts are evaluated, and journal leader, blockhash and gate inputs.
  - Make replay compare only engine-side fields.
  - Correct the file lists and lane claims for WP-08 and WP-09.

### F12. Acceptance depends on data outside the repo and on runs on Cherry
- **Severity:** major
- **Location:** PLAN WP-07 tests (line 438), WP-10 tests (line 527), MEASUREMENT §6.5; the acceptance bullets of WP-02, 03, 04, 05, 07, 08, 09 and 10.
- **Problem:**
  - The legacy known-answer tests (res-pnl p1-p10: trading net −2,337,448, rent 16,383,000) and the WP-07 ledger cases need arb-lab's w5h and w5h2 run files and the full signatures (p6#69 `2wqUDpE6…`, the bolt trade w5h2-p5#648, and the others).
  - Those files exist only on Cherry and in a session-scoped `/tmp/.../scratchpad/cherry` (365 MB). `arbx/testdata` holds only the DAMM vectors and a keystore.
  - Most WP acceptance steps are shadow or live runs on Cherry, which implementers cannot run (no SSH).
  - The WP-09 real-data slice exists only after Stage-0 recordings do.
  - "Concrete and offline-runnable" is therefore not met.
- **Fix:**
  - Add a WP-00b (0.5 d) that copies a small fixture set into `testdata/legacy/` now:
    - last status lines;
    - outcomes, attempts, bundles and exec for w5h-p1..p10, plus the bolt segment;
    - a signature list with expected residuals;
    - the transactions fetched once from public RPC.
  - Split every WP's acceptance into an offline CI part with named fixtures and an owner-run field part.
  - For WP-03 and WP-04, build a synthetic prost-encoded stream fixture and feed it through `forward`.

### F13. WP-02's latency gate cannot be measured
- **Severity:** major
- **Location:** PLAN WP-02 acceptance (line 235); WP-00 (line 138).
- **Problem:** `rx_to_decided` is recorded only on the decoded-trigger path (`engine.rs:184`, `:643-647`). WP-00 returns before that code, so the metric has no samples after WP-00. The live state-trigger path has no stage times at all: `engine.rs:226` fills every stage with one timestamp. So "within 5 µs of the WP-00 baseline" cannot be evaluated, and "recording never slows the hot path" goes unverified.
- **Fix:**
  - In WP-00, add state-path stages (update received → decided → signed → sent) and record a baseline.
  - Gate WP-02 on those stages.
  - Add an offline engine benchmark that runs with the recorder on and off.

### F14. The bundle blockhash has one source, no capability probe and no fallback
- **Severity:** major
- **Location:** PLAN WP-03 item 6; WP-05 items 2-3.
- **Problem:** Every live send needs a blockhash from Haan's `blocks_meta` subscription. Nobody has checked that Haan's plan allows `blocks_meta` (the same plan limits transaction filters to one account), and there is no fallback. If the subscription is missing or lags, every send is refused with `blockhash_stale`, and Stage 0 cannot exit.
- **Fix:**
  - In WP-03, add an `arbx grpc-probe` that checks each subscription the plan needs (account-list size, interslot slots, `blocks_meta`, the transaction filter) before WP-05 starts.
  - Add fallback blockhash sources off the send path: the last entry hash of each completed slot from the shred/entries assembler (it is that slot's blockhash), and background `getLatestBlockhash` polling.
  - Record `blockhash.src`.

---

## Minor

| # | Location | Problem | Evidence | Fix |
|---|---|---|---|---|
| F15 | WP-03 Evidence (line 249) | It says the slot stream is processed-only. `filter_by_commitment: false` already delivers all commitment levels; only interslot updates are off, and the engine ignores the status. | `grpc.rs:367`; `engine.rs:350` | Correct the text. |
| F16 | WP-00 (line 131) | `skip_failing_signers = true` does nothing: the early return at :613 comes before the signer check (:622). Signer stats also stop learning, because `trig_pending` (:640) is skipped. | `engine.rs:613-640` | Say so, or move the return after the signer bookkeeping. |
| F17 | WP-00 acceptance (line 144) | The shadow run's "all recorder files present" cannot hold: `poh.log` is written only when exec is on. | `main.rs:493-495, 545` | List the expected files for shadow. |
| F18 | DoD (line 18) | "the 55 existing tests" cannot all survive: WP-05 deletes `fee_rule`, `gate` and probably `reads_nonce_and_logs`; WP-02 moves `tx_error_decodes_custom_codes`. | test list (`exec.rs`, `send/mod.rs`, `record.rs`) | DoD: existing tests minus the named removals. |
| F19 | DoD vs §7 (lines 18, 655) | "deploy configs parse with `arbx check`", yet `arb-w-live.toml` "stays as the arb-lab record". It will fail on `config_version` and the removed keys. `arbx-stage0.toml`, derived from it, points at `data/seed-pools-w4.csv`, which is not in `arbx/data`, and at `/root/arb-lab` paths. | `arb-w-live.toml:9-12` | Move the record to `deploy/legacy/` (excluded from the DoD); repoint the data paths. |
| F20 | WP-01 item 3 | `rerun-if-changed` on `.git/HEAD` does not catch a new commit on the same branch, so `ARBX_GIT_COMMIT` can go stale. | cargo semantics | Also watch the ref file and `packed-refs`, or always rerun. |
| F21 | WP-01 item 4 | The programdata hash must exclude the zero padding (on-chain ELF = 35,240 B + padding). The plan does not say how 809315be was computed. | verify-all-doc3 D3-005 | Hash only up to the ELF's end (from its section-header offsets); document the procedure and test it on the deployed account. |
| F22 | WP-05 item 5, WP-06 item 8, MEASUREMENT §4.32 | Three band definitions: `[send]` has 4 bands on expected net, `[tips]` has 5 on gross − fees, and `decisions.band` has 4 bands on net. | lines 349, 394; MEASUREMENT line 644 | One shared band table. |
| F23 | WP-05 item 8 | `margin_floor = 2000` reverts 3 of the 23 historical wins (p1#59 at 8,985 expected, p2#658 at 10,751, p7#63 at 9,310). It is a behaviour change, while WP-06 claims to change mechanism, not behaviour. | W §3; `exec.rs:519` | State it, or default the floor to 1 in Stage 0 and test 2,000 as an arm. |
| F24 | MEASUREMENT §4.12 flags bit2 | The feed task cannot know "rejected as stale by the store"; the store runs on the engine thread. | WP-03 item 1 | Record the rejection in the journal ACCOUNT record instead. |
| F25 | MEASUREMENT §4.13 | "rotate together" conflicts with per-stream `rotate_mb`. RPC-sourced records have no `write_version`, so journal references by (acct_id, slot, wv) are ambiguous. | §1.3; `rpc.rs:204` | Rotate both streams on a shared trigger; give each accounts record a sequence id and reference that. |
| F26 | PLAN WP-02 item 4 vs MEASUREMENT §1.2 | The PLAN calls "accounts keyframes" droppable bulk, while MEASUREMENT puts accounts in the chain class. The core lists differ (control and stop). | lines 216 and 57-59 | Align; see F11 for zero loss. |
| F27 | §6 Recording gate (line 627) | No threshold for chain-class drops (`exec`, `accounts`, `journal`), although replay and attribution depend on them. | — | Add chain drops < 0.01% and zero for accounts and journal. |
| F28 | WP-05 item 2 | `Jito::send_bundle` may refresh its auth token, a network call, on the send path. The "no RPC" test counts only `Rpc`. | `send/jito.rs:304-307` | Refresh tokens in the background; count every network call in the test. |
| F29 | MEASUREMENT §4.10 `rpc` | Exec, backfill and blockfetch clients built with `Rpc::only` get fresh `Stats` and stay invisible (res-code §3F). | `rpc.rs:69-72` | Aggregate per client role. |
| F30 | MEASUREMENT §1.1 | The segment's stdout and stderr (`.out`, carrying `eprintln!` lines such as gate and cool-down messages) are not in the layout. | `exec.rs:649, 729`; `run-w.sh:39` | Send `eprintln!` lines to `events`; keep `.out`. |
| F31 | WP-01 item 8 | The rewritten supervisor still keeps the keystore passphrase in bash memory for the whole campaign (res-stops). | res-stops "Other supervisor hazards" | State the residual risk, or move segment spawning into a small hardened launcher. |
| F32 | WP-04 item 8; WP-02 item 4 | Automatic shadow on SLO breach and on core-record loss has no way back to live. p90 ≤ 30 ms is unmeasured today (p50 is 14.87 ms), so the bot may shadow itself on day one. | R §3.2.4 | `slo_action = "log"` in Stage 0, and a recovery rule. |
| F33 | WP-04 item 8 | The first-shred time uses `SigInfo.first_t`, which also takes executed-feed arrivals (yellowstone-tx `t_rx`). | `engine.rs:37, 429-434` | Take the minimum over unexecuted feeds only. |
| F34 | WP-07 item 2 | Snapshot calls (`getBalance`, two `getTokenAccountsByOwner`) answer at different context slots, so a landing in between breaks reconciliation. | — | Use `minContextSlot` and a common slot, or retry. |
| F35 | §3.1 WP-10 row | R4 and X3 depend on `arbx quote` and `arbx replay` (WP-09), which the dependency table does not list. | MEASUREMENT §6.1 `quote.py` | Add the dependency. |
| F36 | WP-06 item 4 | The CU table will be starved: only wins land when sending bundle-only, so most cells fall back to the old formula. | — | Build per-leg CU from the "consumed X of Y" program logs of every watched transaction in `exec.jsonl`. |
| F37 | WP-00 and §6 | No Stage-0 trade-size cap is stated. The live config is 4.2 SOL, while R §3.8's ladder is 0.2 / 1 / 4.2 SOL "once the gates pass". | `arb-w-live.toml:245` | Owner decision, recorded in `meta.limits`. |
| F38 | WP-08 item 2 | Better PoH coverage depends on dead entries feeds being restored (R §6), which is an owner action. | res-code §1 | Name the dependency, and give the poh gauge a target. |
| F39 | WP-03 item 10, WP-08 item 1 | The Jito and BAM validator-list sources are not named; W §8 calls the static file weak. | — | Name the URLs; infer Jito-client leaders from tip transfers in their blocks and BAM from our bundle results' validator identity. |
| F40 | WP-08 item 1 | RTT from Cherry to the leader is not the bundle's path (block engine → leader). | R §3.6 | Label it as such; also record the block-engine keepalive RTT per attempt. |
| F41 | WP-15 intro (line 594) | Stale: `program/arbx-exec/src/lib.rs` already holds the v2 + v3 layouts. | `lib.rs:1-20` | Update the text. |
| F42 | WP-09 scenarios | Mispricing not explained by phantoms has no regression fixture: w5h3-p2#664 (11.7% high) and p10#156 (DLMM leg 1.26% high). | W §4 | Add pool-state fixtures from public RPC with the expected quote. |
| F43 | WP-05 item 9 | During a wallet-stream outage, a landed attempt is finalised as `not_landed_expired`, and outcomes are written once. | — | Before finalising, check `getSignatureStatuses` and the wallet account updates; allow amend records. |
| F44 | WP-00 Risk | Turning the legacy recorder on in live puts mutex locks and BufWriter writes on the engine thread until WP-02 (`record.rs:50`; `exec.rs:132` flushes every attempt). That breaks invariant 5 in the meantime. | `record.rs:50` | State it, and measure the state-path latency with the recorder on (see F13). |

---

## Checked and found correct

- **Line references.** About 90 citations were opened, and all matched the named code within ±2 lines. They include:
  - `engine.rs` :86, :120, :126, :164, :207-231, :213, :215, :245-247, :272-312, :328-354, :356, :384, :446, :537, :567-585, :611-672, :641, :709, :732, :827, :844-874, :878-896, :909-942, :976-1008;
  - `exec.rs` :132, :315-329, :333-361, :421-536, :436-437, :519, :544-545, :611-662, :646-652, :677, :683-698, :717-828, :831-839;
  - `send/jito.rs` :111, :138, :152, :228, :337-358, :361;
  - `send/mod.rs` :63, :117, :489-496, :708-730, :740-747, :841-861;
  - `config.rs` struct lines, :268, :358-366;
  - `grpc.rs` :60-71, :336-356, :367, :399;
  - `feeds/mod.rs` :37, :149-179, :202-203;
  - `store.rs` :9, :30-36, :58-60;
  - `pools.rs` :93, :115-124, :135-150, :154-166;
  - `build.rs` :35, :149, :155, :183-191, :205-222, :375;
  - `rpc.rs` :94, :114, :248-251;
  - `main.rs` :487, :493-495, :504-511, :531-532, :545-550, :572-578;
  - `run-w.sh` :32, :36, :42, :43-47;
  - `deploy/arb.toml:139` and `arb-w-live.toml:147`.
- **Proto tags.** The Yellowstone tag numbers cited in WP-03 match the upstream protos (one omission: the `InnerInstructions{index 1, instructions 2}` wrapper):
  - `inner_instructions` 5, `inner_instructions_none` 10, `log_messages_none` 11, `return_data` 14, `cost_units` 17;
  - `TokenBalance.program_id` 5, `UiTokenAmount.decimals` 2, `Message.recent_blockhash` 3;
  - `blocks_meta` 5/7, `created_at` 11, `SubscribeUpdateSlot.parent` 2 / `dead_error` 4.
- **Solana constants.** `SetLoadedAccountsDataSizeLimit` = ComputeBudget instruction 4 (u32); CloseAccount = token instruction 9; `NonNativeHasBalance` = 11; blockhash validity = block height + 150; PoH 6.25 ms per tick.
- **WP-00 bundle-only.** `bundle_mix = true` with `tpu_max_expected_lamports = 1` does make every attempt bundle-only (`exec.rs:444-448, :493`), and `max_new_token_accounts = 0` blocks ATA creation (`exec.rs:437`).
- **Effort sums.** Stage 0 = 30 d; WP-02 + 03 + 08 + 10 = 12 d; Stage 1 = 18-23 d.
- **Baseline.** `cargo test --release` passes 55 tests.
- **Coverage.**
  - Every arb-lab stream maps to a MEASUREMENT stream, except the segment `.out` (F30).
  - Every listed measurement gap maps to a WP, but exec coverage (F1) and block-ordered context (F10) are not achievable as designed.
  - R §1's "stop now" list is covered except crowded pools (F6).
  - W §7's ranked actions are covered (with F5 and F42 as caveats).
  - res-stops C1-C9 and res-code §3 A-G are covered (with F29 and F31 as caveats).

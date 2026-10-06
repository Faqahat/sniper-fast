# WP-09 part 2 self-review: scenarios S9, S11-S16

**Date:** 2026-10-06. **Base:** master 5b1bfb8. **Scope:** PLAN WP-09 item 4's remaining scenarios (S9, S11-S16; S10 was
part 1's `s10_rent.rs`), on real account layouts, each run through the real `Rig` as `arbx run` drives the engine, each
replayed with the compare, each with its expected projection apart from its inputs, and a mutation check per scenario.
FT-001 (the shadow soak on Cherry, the binary of 11e25d1) is untouched: everything here is new code in this tree.

## 1. Verdict

Every scenario runs through the `Rig` with an executor where sending is involved (shadow, or a canary whose
jito-bundle path sends to a block engine in memory: nothing leaves the process), replays `ok`, `whole`, with the run's
state and decision digests and every decision and attempt identical, and keeps its expected file in
`testdata/scenarios/expected/` (18 new files). Every targeted safety rule, broken on purpose, makes its scenario fail
(21 mutants; one is equivalent, explained in §4). The scenarios exposed one missing capability and two ledger bugs, all
fixed here (§5). One part of S16 stays the open item PLAN WP-09 names (w5h2-p10#156: its state cannot be rebuilt).

## 2. What changed

**Production code** (small, each marked `WP-09 part 2`):

| File | Change | Why |
|---|---|---|
| `src/exec.rs` | `Exec::offline` accepts a live or canary exec_init; a replayed send (`decide_inner`: no path, no key) is recorded as sent with the run's signature (`take_sent`, from the `sent` record `stage_seen` stages); `attempt_sig`; exec_init `money_guard`, `cap_failed_fees` (applied offline); an offline executor raises no alert and sends the chain-fetch service no landing note | S13 (and S9, S11, S14, S15) need a canary run to replay `ok` (§5.1) |
| `src/engine.rs` | after a send (live, canary), journal INPUT 3 `{src: "decision", opp, executor: true, sent: {attempt, sig}}` | the signature a replay sends with |
| `src/replay.rs` | `run_exec` replays a live or canary executor; `not_whole` `sent_records_missing`; replay.json `executor.sent_missing`; the attempts compare leaves out `queue.lambda` (PLAN WP-09: λ is the recording's) | the same |
| `src/ledger.rs` | `raw`: a failed transaction made and closed nothing; `money_json`: `failed_fees_delta_lamports` is the change of the reported `failed_fees_total_lamports` | §5.2, §5.3 |

**Tests and harness:** `src/scenarios/mod.rs` (`ExecSetup::ledger`; `Sending`: a canary's Jito client on a block engine
in memory, its own runtime, its results' channel; `Rig::pump`, `verdict`, `take_results`, `snapshot`, `lines`,
`bundles_sent`; the expected projection's `executor` section for a run with an executor: opportunities, attempts,
bundles, outcomes, ledger lines, reconciliations, signatures left out; S16's fixtures merged as pair `s16`), S9 extended,
S11 extended, S12-S16 new (`s12_hints.rs` ... `s16_mispricing.rs`), `exec_replay.rs` (a canary recording replays; one
without its `sent` record is not whole), `exec/tests.rs` (the `sent` record of a live send; an offline live executor).

**Fixtures:** `tools/capture-fixtures.py --s16` (read-only public RPC: 2 `getMultipleAccounts`, 3 `getTransaction`) wrote
`testdata/scenarios/s16/{capture.json, accounts.json, tx/*.json, legacy.json}`; the old bot's lines come from
`testdata/legacy/raw/w5h3-p2` and w5h2-p10's own files (the session's read-only copy of Cherry), secret-checked. The
manifest lists 240 files (`--verify`: 0 problems); `tests/legacy_fixtures.rs` walks `s16/` too.

**Docs:** MEASUREMENT.md revision 2.16 (§4.13 the `sent` record and exec_init's two fields, §4.50 the live and canary
replay), `testdata/scenarios/README.md`, this file.

## 3. The scenarios

| # | Test(s) | Executor | What is asserted | Expected file(s) |
|---|---|---|---|---|
| S9 | `s9_same_state_blocked_new_state_allowed`, `s9_new_leader_allowed_same_leader_refused`, `s9_the_holds_end_releases_the_same_state`, `s9_a_would_fail_keeps_the_lock_a_landing_releases_it` | shadow; canary | same route, state and leader held (`inflight_same_state` at the same slot, `inflight_same_leader` a slot later); a new state (`new_state`), a new leader (`new_leader`) or the hold's end (3 slots: `first`; 2 slots: still held) let it go; through the Jito client's sink: after `accepted` and `would-fail` (INPUT 5, `release` false) the deferred evaluation of the same state is refused, after `processed` it is sent. The leader schedule (INPUT 2) and the results (INPUT 5) are replayed | `s9`, `s9-new-leader`, `s9-same-leader`, `s9-expiry`, `s9-hold`, `s9-would-fail`, `s9-landed` |
| S11 | `s11_big_band_is_throttled_and_ranked_behind_smaller_bands`, `s11_crowded_routes_rank_behind_and_skip`, `s11_the_send_queue_serves_the_best_first` | shadow; canary | the ≥1M class's bucket (`band_throttle` 10 ms later, refilled 2.5 s later); ranks (2 × big + crowded) in decisions and attempts; a crowded route ranked behind, skipped from 100,000 expected (`crowded_skip`), rank 3 with the skip off; **the real queue**: a canary whose jito-bundle path sends one bundle a second with a 5 s queue (the ≥1M throttle lifted, the skip off): a big gap sent at once takes the second's slot, then big, big crowded and small are decided while it holds it; the block engine got attempts 0, 3, 1, 2 (the first, then the waiting ones best first: rank 0, 2, 3), each queue wait longer than the one before | `s11-big`, `s11-crowded`, `s11-crowded-rank`, `s11-queue` |
| S12 | `s12_a_decoded_only_trigger_never_produces_a_send`, `s12_a_hint_vetoes_a_send_on_a_half_written_state` | canary | ten decoded swaps (six PumpSwap sells of 25k-150k USDC, four AMM v4 swaps), half failed on chain, half never seen again: no evaluation, no opportunity, no decision line, no attempt, no bundle, the executor never asked; ten hint-only triggers, hints dropped (5 at once, 5 after their window). And the veto: a shred-seen transaction's pending group refuses every route of a real gap (`pending_commit`, nothing sent); its completion is the one send | `s12`, `s12-veto` |
| S13 | `s13_an_accepted_then_would_fail_bundle_is_recorded_in_full` | canary | the bundle (attempts.jsonl `sent`), its copy (copies.jsonl, b0), `accepted` then `would-fail` (bundles.jsonl in order, code 0x4e580002), INPUT 5 ×2 (`release` false), the expiry check's answer, one final line (`not_landed_expired`, both verdicts in order, the would-fail's code and detail); the same state refused while it was in flight | `s13` |
| S14 | `s14_the_ledger_books_a_create_close_landing_and_reconciles`, `s14_a_failed_create_close_landing_books_its_fee_only` | canary + ledger | a create+close bundle that landed (its record built from the very bytes the block engine got): ledger line `route`, categories `trade_gross` 9,377,994 / `tip` −100,000 / `fee_win` −5,000 summing to the equity change, rent locked = reclaimed = 2,039,280, trading P&L 9,272,994; `landed_ok` from the wallet record; the next snapshot reconciles (residual 0 on both bases, token amounts exact, the executor's money matches the chain's line); status money totals the same. A failed landing of the same kind: `fee_fail` −5,000 only, nothing created or closed | `s14`, `s14-failed` |
| S15 | `s15_status_totals_are_monotonic_and_the_deltas_sum_to_them` | canary + ledger | 17 status lines over 170 s of engine time with sends, verdicts, two landings (one found first by the expiry check: a provisional failed fee), hints, a snapshot and its reconciliation, an expiry: `seq` without a gap; every `_total` monotonic (signed money sums aside); 37 `_total`/`_delta` pairs (maps included) whose deltas sum, **on every line**, to that line's total; the delta-only commit, fork, accuracy and lookup-table sections summing to their counters; the verdicts summing to what the block engine answered | `s15` |
| S16 | `s16_w5h3_p2_664_the_cp_leg_is_priced_as_the_chain_executed_it`, `s16_w5h2_p10_156_stays_open_its_dlmm_state_is_not_on_chain` | shadow | #664: the pool rebuilt from its landing's pre-token balances and the current pool account with the virtual quote reserve both PumpSwap events pin; arbx's buy quote at 4.2 SOL = the chain's 276,985,551,117 tokens to the unit (today's reserve: 6.9 ppm low); at the trigger's state, the one the old bot priced, arbx says 278,480,720,280 and the old bot said 311,092,620,532: **11.71% high**, wallet-synthesis's 11.7%, on the right state (its maths, not a phantom). p10#156: the record's legs (DAMM v2 +1.43%, DLMM +1.27% against the old prediction) pinned; nothing in it rebuilds the DLMM bins | `s16-664` |

Every scenario's `finish_and_replay` asserts: `ok`, `whole`, the run's digests reproduced (also as `Engine::finish`
recorded them), every decision compared and identical, every attempt compared and identical, the executor replayed
(a canary's too: a send without its `sent` record would make the replay not whole; S13 also asserts
`executor.exec_init.mode` `canary` and `sent_missing` 0), the attempts' expected gross the decisions'.

## 4. Mutation check

Method: every mutant guarded by `ARBX_MUT=<name>` (a `crate::mutant` helper) in one build of the master tree's own
`target/` (the build lock, `CARGO_BUILD_JOBS=3`), the 7 touched files byte-copied first with their sha256
(`scratchpad/r4/wp09p2/mutants.py`); the 56 scenario tests run once per mutant. Then every file copied back, its sha256
checked against the copy's, touched, and the tree rebuilt (§6). Baseline (no mutant): 56 of 56 pass.

| Mutant | The rule broken | Scenario tests that fail |
|---|---|---|
| M9a | a would-fail is final: it releases the in-flight entry (`Outcome::is_final`) | S9 would-fail, S13 |
| M9b | any block-engine result releases the entry (`on_release` ignores `release`) | S9 would-fail, S13 |
| M9c | the in-flight lock off (`Inflight::check` always `first`) | S9 ×4, S11 big, S11 queue, S13 |
| M9d | in-flight expiry off (`Inflight::expire` keeps every entry) | none: **equivalent** (below) |
| M9e | the hold never ends (expiry off and the check's own age filter off) | S9 hold's end, S15 |
| M11a | no ≥1M throttle | S11 big, `synth::a_synthetic_shadow_hour_replays_identically` |
| M11b | no crowded skip | S11 crowded |
| M11c | the send queue ignores band and crowding (EV only) | S11 queue |
| M12a | a hint creates a decision (a decoded swap's pool evaluated at once) | S12, S2, S3, S6, S15 |
| M12b | a hint never vetoes (pending accounts not pending) | S12 veto, S1, S1b, S9 ×3, S13 |
| M13a | the final line drops the verdicts | S13, S14 ×2, S15 |
| M13b | bundles.jsonl not written | S13, S14 ×2, S9 would-fail, S15 |
| M13c | a send journals no `sent` record | the canary replay test, S9 would-fail, S11 queue, S12 veto, S13, S14 ×2, S15 (each replay not whole: `sent_records_missing`) |
| M14a | create+close books the rent locked, never reclaimed | S14, S15 |
| M14b | the tip not recognised (it falls into the trade) | S14, S15 |
| M14c | §5.2 undone (a failed transaction's create+close booked) | S14 failed, S15 |
| M15a | the engine's status `prev` counters never updated | S15 |
| M15b | the executor's status `prev.sent` never updated | S15 |
| M15c | §5.3 undone (the failed fees' delta of the settled part only) | S15 |
| M16a | PumpSwap's virtual quote reserve ignored (the old bot's maths) | S16 #664, S5, S11 queue |
| M16b | PumpSwap's creator fee ignored | S16 #664, S5, S11 queue |

**M9d is equivalent for decisions:** `Inflight::check` ignores an entry whose hold has ended (`target_slot + hold >
target − 1`) whether or not `expire` removed it; `expire` only bounds the map (status `inflight_keys_now`). Breaking
both (M9e) fails S9's hold's end. Kept as a finding of the check, not a gap.

## 5. What the scenarios exposed (fixed here)

1. **A live or canary recording could not be replayed** (WP-09 review, "Open": "Live and canary executors are not
   replayed"). S13 cannot be recorded in full without a sending executor, and every scenario must replay `ok`. Now a
   send journals its attempt's signature right after the decision (after the fire: the hot path gains one journal record
   per send), and the replay's offline executor replays the send as sent with that signature; the fire's result, the
   verdicts, the statuses and the wallet record come from the journal as before. A recording made before this (no
   `sent` records) replays `ok: false` with `sent_records_missing`, never a silent OK (test
   `a_canary_recording_replays_its_sends_and_one_without_its_sent_records_is_not_whole`; mutant M13c). exec_init now
   carries the equity guard (`money_guard`) and the failed-fee cap (`cap_failed_fees_lamports`, which `--budget-left`
   lowers below the config's; the frozen config file does not show it). Shadow and dry-run recordings replay as before
   (their exec_init reads the same; their would-sends are `sent: false` and journal no `sent` record).
2. **The ledger booked a failed create+close transaction as rent locked and reclaimed** (S14's failed landing). A failed
   transaction's record still lists the associated-token program's inner create (it ran before the failure; #664's real
   failed landing lists its own) and the message holds the CloseAccount, so `ledger::raw`'s made-and-closed branch
   counted 2,039,280 locked and 2,039,280 reclaimed for a transaction that changed nothing but its fee. Neutral in
   money (locked = reclaimed), wrong in the rent totals and the reconciliation's informational sums. Fixed: that
   branch needs the transaction to have succeeded.
3. **`money.failed_fees_delta_lamports` did not sum to `money.failed_fees_total_lamports`** (S15, per line). The total
   includes the base fees of failed landings an expiry check found before their wallet records (provisional: the
   supervisor reads this total); the delta was the settled part's change only, so on the lines between the status and
   the record Σdelta < total (MEASUREMENT §2.2). Fixed: the delta is the reported total's change since the previous
   line. Consequence for the toolkit (unchanged): `r1_money`'s cross-check row "money.failed_fees_delta_lamports
   (summed)" now equals its `money.failed_fees_total_lamports` row (both against the ledger's `fee_fail`): a difference
   at a segment's end is exactly the fees still provisional there.

Not a bug, noted: **PumpSwap's virtual quote reserve moves** (DreMAMRc: 17,579,766,284-285 at #664 on 2026-10-04, as
both events pin it; 17,583,646,841 in the account captured on 2026-10-06). A fixture rebuilt from "the current pool config" must take that field from the chain's events of the time; with
it, arbx-sizing reproduces the chain to the unit.

## 6. Results

- `cargo test --release` (after the mutants' revert and rebuild): **579 passed, 0 failed, 7 ignored** in 11 binaries
  (lib 543 + 6 ignored, bin 14, alerts_cli 4, campaign 3, legacy_fixtures 4, meta_config_hash 1, replay_cli 1,
  runtime_isolation 2 + 1 ignored, stop_path 6, supervisor 1; no doc-tests). Master had 567: 12 new tests (S9 +2, S11
  +1, S12 +2, S13 +1, S14 +2, S15 +1, S16 +2, the canary replay test +1). Two doc comments corrected after that run
  (`s11_bands.rs`, `s12_hints.rs`): the 56 scenario tests rebuilt and run again, all pass.
- Toolkit (`cd tools/arbx-report/tests && python3 -m unittest discover -s .`): 94 tests OK (4 skipped: they need
  `ARBX_REPORT_CHERRY`).
- `python3 tools/capture-fixtures.py --verify`: 240 files listed, 0 problems.
- `arbx check` (this tree's binary) on `deploy/arbx-stage0.toml`, `deploy/arb.toml`, `deploy/arbx-canary-frz.toml`: exit 0
  on all three (run with an empty environment; no `.env` beside the configs and no block-engine auth file on this
  machine, so the I-10 key check covered the URL and header values only).
- `python3 tools/secret-scan.py`: the commit's 44 files scanned in a scratch repository before the commit (0 findings),
  then all refs of this repository after it.
- Builds: the master tree's `target/` only, under `/home/moiz/arbx-offload/build.lock`, `CARGO_BUILD_JOBS=3`; no new
  target directory; scratch in `scratchpad/r4/wp09p2/` (the mutation script and its logs) and
  `/home/moiz/arbx-offload/scratch-wp09p2/` (the S16 exploration's transactions, test logs).

## 7. Deviations and open items

- **S16 p10#156 is not a Rig run.** Its DLMM leg's bins (and the DAMM v2 pool's price and liquidity) at slot 453,089,316
  are not retrievable; the landing's record carries only the legs' outputs (its logs hold no venue event). Its test pins
  the case from the record and the old bot's lines (the DLMM leg 1.27% high at the tokens it really got, asserted within
  0.05% of PLAN's 1.26%; the DAMM v2 leg 1.43% high) and checks that nothing in the record rebuilds the bins.
  As PLAN WP-09 says, the first Stage-0 recording with a ≥ 1% mispricing in accounts.bin becomes its fixture.
- **S16 #664's route is not priced end to end.** The DLMM pair's state at the time is not retrievable either: the run
  prices the route on the pair as captured now (its decision is recorded and replayed), and the claim checked is the
  CP-family leg's, which PLAN WP-09 names. The chain's own sell of those tokens (4,061,405,592 for 4.2 SOL in) is the
  −138.6M round trip a correct buy quote implies.
- **Mutants were switched by an environment variable in one build** (as the part-1 review did), not one build each; the
  byte copies, sha256 check, touch and rebuild are as asked.
- **outcomes.jsonl is not compared by the replay.** The run's final lines are asserted by S13-S15; a replay's own lines
  of a sending run carry no verdicts (the offline executor has no Jito client). Decisions, attempts and the digests
  (which fold the executor's open and final attempts and their money) are compared.
- A **live** executor replays through the same path as a canary one; the scenarios exercise the canary.

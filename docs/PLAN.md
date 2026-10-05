# arbx engineering plan

**Date:** 2026-10-04. **Status:** plan only, revision 2. Revision 2 applies the adversarial review `docs/reviews/plan-review.md` (44 findings); `docs/reviews/plan-changes.md` gives each finding's disposition. No bot code has been changed for this plan. The only data added is the legacy fixtures in `testdata/legacy/raw/` (F12).
**Inputs:** `docs/research/redesign-final.md` (the redesign, cited as "R §n"), `wallet-synthesis.md` ("W §n"), `docs-review-synthesis.md` ("D §n"), `rival-synthesis.md`, `res-code.md`, `res-engine.md`, `res-pnl.md`, `res-stops.md`, the arbx source tree, and arb-lab recordings measured for this revision (§0, "Measured inputs").
**Companion:** `docs/MEASUREMENT.md` holds the exact schema of every recorded stream and the design of the analysis toolkit. This plan names the streams. It does not repeat their fields.

arbx is an atomic, self-funded DEX arbitrage bot. It never trades ahead of user orders, never sandwiches and uses only its own capital. Every live transaction is a one-transaction Jito bundle whose route reverts unless it is profitable. This plan does three things:
- it evolves the arb-lab copy into the Stage 0 bot of R §4;
- it adds the Stage 1 experiments as engine features behind flags;
- it integrates the new route program `arbx-exec` behind a config switch.

---

## 0. How to read this plan

- **Line numbers** refer to the arbx tree as copied (baseline commit `66a94b6`, 2026-10-04). Each citation also names the function, because lines drift as work packages land. When a WP starts, its author re-reads the named functions. The line numbers are a map, not a contract.
- **Work packages (WP)** are numbered in merge order. Section 3 shows which ones touch disjoint files and can be developed in parallel.
- **Effort** is engineer-days for one engineer who knows the code, including tests (est.).
- **"Reason code"** means a value of the decision-reason enum in MEASUREMENT.md Appendix A.1. Every refusal to price or send records one.
- Amounts are in lamports unless marked SOL.
- **Acceptance comes in two parts.**
  - **Offline (CI)** checks run in `cargo test` or the toolkit's tests on this machine, with named fixtures in `testdata/`. A WP merges only when its offline part passes.
  - **Field (owner-run)** checks need a shadow or live run on Cherry. Implementers cannot run these (no SSH). The owner runs them, and the results go into the WP's merge note before the next dependent WP is used live.
- **Definition of done for every WP:**
  - `cargo build --release` and `cargo test --release` pass. That means the existing tests plus the WP's own, minus the named removals: `fee_rule` and `gate` are deleted with their code in WP-05, and `tx_error_decodes_custom_codes` moves from `record.rs` to `src/rec/` in WP-02. The test count after the WP is written in the merge note.
  - No new compiler warnings.
  - The maintained configs (`deploy/arbx-stage0.toml`, `deploy/arb.toml`) parse with `arbx check`. `deploy/legacy/` is excluded (WP-01).
  - MEASUREMENT.md is updated if a schema changed, and its schema version is bumped.
  - The merge note lists the offline acceptance results. Field results are added when the owner has run them.
- **Measured inputs used for sizing in this revision.** These were computed from arb-lab recordings: the moves logs of w5h-p1, w5h-p9 and w5h2-p1, and the w5h-p1 status lines.
  - The chain produced **3.72 slots/s**: 4,400 slots in 1,182 s, so about 13,400 slots per hour. Every slot had at least one watched-account write.
  - Watched transactions (distinct signatures that wrote a watched pool) ran at **31-60/s** on the w5h registry, where 300-377 pools moved.
  - PumpSwap pools were touched by **41-48%** of those transactions. Venues were taken from the seed CSVs, and 1-3% of transactions were on unknown pools.

---

## 1. Where arbx starts: defects and gaps, mapped to code

| # | Defect or gap | Where in arbx (function, current lines) | Evidence | Fixed in |
|---|---|---|---|---|
| 1 | Prices come from decoded, unconfirmed swaps (`preds`), which override live state. Failed swaps leave phantom gaps | `Engine::leg` engine.rs:567-585 reads `self.preds`; inserted by `on_trigger` :641; pruned only in `housekeeping` :384 | W §4 "Phantom quotes"; W §7.1: 10 of the 16 biggest losses; 681 of 822 decoded triggers ≥0.1 SOL failed on chain | WP-00 (gate), WP-04 |
| 2 | Torn reads: a route is priced while only part of one transaction's writes have arrived | `state_trigger` :207-231 checks only the trigger pool's parts; `state_pending` flush heuristic :245-247, :356, :893-896 | W §7.2, R §3.2.2 (AgmLJBMD split routes; the bolt trade was priced on inconsistent state) | WP-04 |
| 3 | PumpSwap is exempt from the parts-skew check, with no recorded reason. The likely reason is that a PumpSwap swap does not write the pool account: the code waits only for the vaults (`state_trigger` engine.rs:209, `check_prediction` :930) | `Store::snapshot` store.rs:58-60 | R §3.2.2; review F3 | WP-04 |
| 4 | The store orders by slot only. `write_version` is parsed and then dropped | store.rs:31; grpc.rs:399 parses it; `forward` feeds/mod.rs:202-203 drops it; `Event::Account` :37 has no field for it | R §3.2.1 | WP-03, WP-04 |
| 5 | A failed lookup-table fetch is cached as missing for the whole run | `process` engine.rs:446, `on_alt` :537 | R §3.2.3 | WP-04 |
| 6 | No warm-up gate: sends go out 3.0-3.8 s late at segment start | no gate in `Exec::wants_send` exec.rs:315-329 | W §1, R §3.2.4 | WP-04 |
| 7 | Direct (non-bundle) arm: 1 win in 989 attempts, 24.4M in fees | `Exec::copies` exec.rs:421-536 (arms, fee rules, 17 paths) | W §2, R §3.6 | WP-00, WP-05 |
| 8 | The stale-simulation override sends anyway | `Exec::send` sim gate exec.rs:617-662, stale branch :646-652; an RPC error also sends (:635) | res-code §3A, R §1 | WP-05 |
| 9 | 3 s failover and 429 backoff on send-adjacent RPC | `Rpc::call` rpc.rs:114, `Rpc::one` :94 | R §4 Stage 0 | WP-05 |
| 10 | Bundles expecting ≥1M are unthrottled: 0 of 1,869 landed, while 1,020 attempts were lost to the 5/s limit | `Exec::send` prio exec.rs:616 (ranks seed pools, not bands); `Budget` send/budget.rs | R §1, §3.4 | WP-00, WP-05 |
| 11 | Durable nonce on bundles ("Blockhash not found", nonce shortages) | `Exec::send` :544-545, `build` :346 | R §3.5, D §4.6 | WP-05 |
| 12 | The 400 ms pair lock both blocks real gaps and misses duplicates | `copies` exec.rs:436 | R §3.4, W §7.10 (#245/#246) | WP-05 |
| 13 | Rent: new token accounts are never closed. The bundle arm's +163,187 became −17,926,693 | `build` exec.rs:340, :350-353; the cap `max_new_token_accounts` resets every segment (:437) | W §2, res-pnl §2 | WP-00, WP-06 |
| 14 | CU limits come from a static table: 5 runs ran out of CU; the median ask was 206k against 140k used | `Venue::leg_cu` venues/mod.rs:35-44; engine.rs:709, :732, :827 | W §1, D §4.10 | WP-06 |
| 15 | The DLMM bitmap extension is checked once at boot; 19 failures with 0x1794 | `pools::boot` pools.rs:120-124; `dlmm_leg` build.rs:191 | W §1, §7.4, R §3.3 | WP-06 |
| 16 | No size-budget logic; copies reach 1,209 of 1,232 bytes | `build` exec.rs:358-359 only refuses | R §3.5 | WP-06 |
| 17 | Tip = floor(0.7 × (expected − 5,000)) in every band; the repo and live configs drift (0.5 against 0.7) | `Path::tip` send/mod.rs:489-496; `copies` exec.rs:511; deploy/arb.toml:139 vs arb-w-live.toml:147 | R §3.6 | WP-00, WP-06 |
| 18 | Bot counters are not P&L. `failed_fees_lamports` is cumulative and undercounted; `profit_lamports` mixes in rent | `on_settled` exec.rs:763, :769-773, :790, :820; `status` :831-839 | R §3.7, res-stops §4, res-pnl | WP-02, WP-07 |
| 19 | 16 failed landings went unrecorded (one status check after `settle_s`) | `send` exec.rs:677 sleep; :683-693 one `getSignatureStatuses` | W §6 P6, res-stops C6 | WP-03b, WP-05, WP-07 |
| 20 | No loss stop and no reconciliation | none in the run path | res-stops §4, R §3.8 | WP-07 |
| 21 | Only the first Jito verdict is kept, and the zero-wait lookup loses verdicts | `Verdicts.first` send/jito.rs:228, :341; `j.verdict(sig, Instant::now())` exec.rs:696; overwritten per copy :694-698 | W §8 "Missing Jito verdicts" | WP-05 |
| 22 | The recorder is off by default and runs on the caller's thread | `RecordCfg.enabled` config.rs:47-54 (default false), and the live config :378-380 omits it; `Recorder::line` record.rs:50 locks a mutex on the engine thread; `write` exec.rs:132 flushes every line | W §8 "Recorder off from w5h2-p3" | WP-00, WP-02 |
| 23 | Executed-transaction results are PumpSwap-only, with no inner instructions and no block order for other venues | the yellowstone-tx feed is filtered on one program (arb-w-live.toml:117-123); `PbMeta` grpc.rs:60-71; `rec_exec` :336-356 | W §8, rival-synthesis §9 | WP-03, WP-03b, WP-08 |
| 24 | No provenance; the binary was swapped mid-campaign and the config mutated by `sed` | `meta.json` main.rs:572-578; tools/analysis/cherry/run-w.sh:36 | res-stops C9 | WP-01 |
| 25 | Every early stop is an unexplained SIGINT; the supervisor counts operator kills as crashes; the "records only" fallback crashes | main.rs:504-511; run-w.sh:32, :43-47 | res-stops §1, C7, C8 | WP-01 |
| 26 | Unknown config keys are silently ignored | `#[derive(Deserialize)]` without `deny_unknown_fields`, config.rs:7 and every struct | res-code §2 | WP-01 |
| 27 | DAMM v2 and DLMM fees are priced on local time | `unix_now()` engine.rs:164 is passed to `dlmm::quote` and `dammv2::quote_exact_in` | R §3.3 | WP-04 |
| 28 | PoH coverage is thin and only recorded when exec is on | `poh_log_on = exec_on` main.rs:493-495; one clock per entries feed | W §8 | WP-08 |
| 29 | BAM status comes from a static file; no per-attempt leader telemetry | `tools/analysis/leaders.py` after the fact | W §8, R §3.6 | WP-03, WP-08 |
| 30 | Attribution by "the first tx touching both pools" misses single-pool and zero-capture closers | `finish_opp` engine.rs:982-987 | W §4 caveat, W §7.7 | WP-03b, WP-10 |
| 31 | No replay harness and no scenario tests for the catalogued losses | none | R §4 Stage 0 | WP-03 (journal), WP-09 |
| 32 | 49% of attempts went to the 21 pools with 150 or more bots, where we win 0.4% of the time | `Exec::send` `Prio` exec.rs:616 ranks by seed source only | R §1 (redesign-final.md:66, :221); tools/analysis/patterns/PATTERNS.md item 10 | WP-00, WP-05 |
| 33 | Hot I/O and RPC share one 2-thread runtime | `worker_threads(2)` main.rs:502; RPC fetches are spawned on `self.rt` (engine.rs:522-531, :963-972) | review F9 | WP-02 |
| 34 | The state-trigger path has no stage timestamps, and `rx_to_decided` exists only for decoded triggers | `state_trigger` engine.rs:226 fills every stage with one time; latency is pushed at :643-647 | review F13 | WP-00, WP-02 |
| 35 | The attempt line is written and flushed between signing and firing | `Exec::send` exec.rs:611 `write` (flushes, :132) before `paths.fire` :624 | code | WP-00 |
| 36 | A version written on an abandoned fork stays in the store and is priced | store.rs:31 keeps the newest `(slot)`; the engine ignores slot status (engine.rs:350) | review F4 | WP-04 |

---

## 2. Invariants every WP keeps

1. **No front-running.** arbx only trades atomic, self-funded round trips. A bundle holds only our transaction. Nothing is ever placed ahead of a user order.
2. **A miss costs nothing.** Live sends are one-transaction Jito bundles. The route reverts unless the quote account ends with at least tip + base fee + margin more than it started (R §3.9).
3. **Price only committed, complete, canonical state.** No decision reads a state that did not exist on chain, half of one, or one from an abandoned fork once that fork is known to be abandoned (R §3.2). **A hint (a decoded transaction not yet committed) may veto a send, never create one** (STAGE1-PLAN, 2026-10-05).
4. **Fail closed.** If any input of a send is missing, stale or unverified, there is no send, and the reason is recorded.
5. **The hot path never blocks** on disk, RPC or recording. The hot runtime runs only stream I/O and sends; all RPC and heavy parsing run on a separate background runtime (WP-02). Recording uses bounded queues and counts its drops.
6. **Everything is recorded with stable IDs** (signature, decision id, attempt id, bundle id, state version, account-record sequence). Missing data is recorded as missing, never as zero.
7. **Money truth is the chain.** Budgets and stops use the ledger built from the wallet's transactions and balance snapshots, never the bot's own counters.
8. **One frozen binary and config per campaign.** Every stop has a recorded reason.
9. **No keys in logs, records or argv.** The trading key never holds program upgrade authority. arbx never deploys programs; the owner does.
10. **No hidden shortfalls.** A gate that is not met stays not met. A requirement that cannot be met with the bought capacity is an owner decision (§9), not an escape clause.

---

## 3. Order of work and parallel lanes

### 3.1 Merge order

| Order | WP | Title | Files it touches (new files in *italics*) | Depends on | Effort |
|---|---|---|---|---|---|
| 0 | WP-00 | Day-0 safety switch | *deploy/arbx-stage0.toml*, deploy/arb.toml, *data/crowded-pools.json*, engine.rs (`on_trigger`, `state_trigger`, `on_account` stage times), exec.rs (`copies`, `send` order and `Prio`), config.rs (4 keys) | — | 0.75 |
| A | WP-00b | Legacy fixtures | *testdata/legacy/\**, *testdata/wallet/\**, *tools/capture-fixtures.py* (`--wallet` mode) | — | 0.5 |
| 1 | WP-01 | Foundation: crate split, config hygiene, provenance, stop reasons, control, supervisor | Cargo.toml, *buildinfo.rs*, *src/lib.rs*, main.rs, config.rs, *src/provenance.rs*, *src/control.rs*, *deploy/run-w.sh*, deploy/*.toml, *deploy/legacy/* | WP-00 | 2 |
| 2 | WP-02 | Recorder framework (always on) and background runtime | Cargo.toml, *src/rec/\**, record.rs (removed), *src/runtime.rs*, writer plumbing in engine.rs, exec.rs, send/mod.rs, send/jito.rs, feeds/mod.rs, feeds/shred.rs, feeds/grpc.rs; main.rs, config.rs, rpc.rs (runtime binding) | WP-01 | 3 |
| 3 | WP-03 | Chain inputs, raw chain recording, input journal, gRPC probe | feeds/grpc.rs, feeds/mod.rs, *src/leaders.rs* (basic), *src/rec/accounts.rs*, *src/rec/journal.rs*, *src/rec/exec.rs*, *src/probe.rs*, store.rs (data type only), engine.rs (`run` → `step`/`timers`, event arms), config.rs, main.rs, *testdata/grpc/\**, *testdata/proto/\** | WP-02 | 4 |
| C | WP-03b | Chain fetch: wallet transactions, backfill, block index, blockhash sources | *src/chainfetch/\**, rpc.rs (`call_bounded`, per-role stats), config.rs (`[chainfetch]`), main.rs (one wiring block), *testdata/rpc/\** | WP-03 | 2.5 |
| 4 | WP-04 | State consistency, forks, accuracy monitor | store.rs, engine.rs, *src/commit.rs*, *src/forks.rs*, feeds/clock.rs, exec.rs (`RouteIn` fields, `wants_send` hook), config.rs | WP-03 | 4.5 |
| 5 | WP-05 | Send policy: bundle-only, fail-closed, in-flight by state, crowding rank | exec.rs, send/mod.rs, send/budget.rs, send/jito.rs, rpc.rs (exec client), *src/proglog.rs*, build.rs (`delivered_from_logs` moves out), config.rs, main.rs | WP-04, WP-03b | 3 |
| 6 | WP-06 | Builder: rent-neutral, measured CU, sized, tipped by band | build.rs, exec.rs (`build`), venues/dlmm.rs, engine.rs (`route_in`, `best_cycle` fee/CU), pools.rs, *src/cu_table.rs*, *src/tip.rs*, *src/bands.rs*, *data/cu-table.json*, config.rs | WP-05 | 3 |
| 7 | WP-07 | Ledger, reconciliation, supervisor stops (campaign-wide) | *src/ledger.rs*, *src/supervisor.rs*, exec.rs (`on_settled`, `status`, `wants_send`, held set), main.rs, config.rs, deploy/run-w.sh | WP-06 | 3.5 |
| B1 | WP-08 | Telemetry: leaders, PoH, transfer classification, program-log decoders | src/leaders.rs, *src/classify.rs*, src/proglog.rs (extends WP-05's), feeds/shred.rs, feeds/entries.rs, feeds/mod.rs (PoH lines), send/tpu.rs, src/rec/exec.rs (derived-field hook), main.rs (one wiring block), config.rs (new structs) | WP-03; proglog part after WP-05 | 2 |
| B2 | WP-09 | Replay harness and scenario tests | *src/replay.rs*, *src/scenarios/\**, *testdata/scenarios/\**, tools/capture-fixtures.py, main.rs (`Cmd::Replay`, `Cmd::Quote`) | WP-04 (S9-S11 after WP-05/06) | 3 |
| B3 | WP-10 | Analysis toolkit | *tools/arbx-report/\** only | MEASUREMENT.md; WP-00b; R4/R8/X3 parts after WP-09 | 4.5 |
| S1 | WP-11 | Experiment framework; X2 delay, X4 tip share, margin arm, X5/X8 assignment | *src/experiments.rs*, exec.rs (send-task hook), tip.rs (arm hook), config.rs | WP-07 | 2 |
| S1 | WP-12 | Offline experiments X1 census, X3 smaller sizes, X6 size fit | *src/offline.rs*, main.rs (`Cmd::Sizefit`), tools/arbx-report (census) | WP-09, WP-10, WP-06 | 3 |
| S1 | WP-13 | Verifier sidecar (X9), measured CU | *verifier/* (separate crate), *src/verify_client.rs*, config.rs | WP-03, WP-06 | 8-12 |
| S1 | WP-14 | Discovery connection (X8) | *src/feeds/discovery.rs*, config.rs, main.rs | WP-03 | 2 |
| S1 | WP-15 | arbx-exec integration behind a flag (X7 plan) | *src/build_arbx.rs*, exec.rs (`build` dispatch), proglog.rs, provenance.rs, Cargo.toml, config.rs | WP-06, WP-08, WP-13 | 3-4 |

**Stage 0 is WP-00 to WP-10:** about 36 engineer-days. The core lane (WP-00 → WP-07) is about 24 days of sequential work. With lanes A, C, B1, B2 and B3 in parallel, Stage 0 takes about 25 calendar days.
- That is more than revision 1's 30 days and R §4's 9-13 days.
- The measurement requirement accounts for most of it: WP-02, WP-03, WP-03b, WP-08 and WP-10 come to about 16 days.
- The review fixes add about 6 days: the journal moved into the core lane, the chain-fetch service, forks, campaign-wide stops and fixtures.

**Stage 1 is WP-11 to WP-15:** about 18-23 days, dominated by the verifier.

### 3.2 Parallel lanes

```
Core lane (sequential; each WP rewrites code the next one builds on):
  WP-00 ─► WP-01 ─► WP-02 ─► WP-03 ─► WP-04 ─► WP-05 ─► WP-06 ─► WP-07 ─► WP-11
                                 │  │        │      ▲
Lane C (chain fetch):            │  └► WP-03b ──────┘  (parallel with WP-04; merged before WP-05)
Lane B1 (telemetry):             └► WP-08  (after WP-03; its proglog part after WP-05)
Lane B2 (replay):                          └► WP-09 S1-S8 (after WP-04); S9-S11 after WP-05/06
Lane A  (fixtures):  WP-00b from day 0
Lane B3 (toolkit):   WP-10 from day 1 (legacy readers on WP-00b fixtures; synthetic v2 streams);
                     validated on real output after WP-03/03b; R4, R8 (all swaps) and X3 after WP-09
Lane S  (Stage 1):   WP-13 and WP-14 after WP-03; WP-12 after WP-09 + WP-10; WP-15 last
```

**Parallelizable groups**, in order:
1. {WP-00, WP-00b, WP-10 (legacy part)}
2. WP-01, then WP-02, then WP-03 (core; WP-10 continues)
3. {WP-04, WP-03b, WP-08 (leaders, PoH, classification), WP-13, WP-14}
4. {WP-05, WP-09 S1-S8}
5. {WP-06, WP-08 (proglog decoders), WP-10 (R4, R8, X3 once WP-09 is in)}
6. {WP-07, WP-09 S9-S16}
7. Stage 1: {WP-11, WP-12}, then WP-15

**Disjointness rules that make the lanes safe:**
- **WP-03b** adds only new files under `src/chainfetch/`, plus `rpc.rs`, its own config struct and one wiring block. No core WP between WP-03 and WP-05 touches `rpc.rs`; WP-05 only switches the exec client to the WP-03b `call_bounded`.
- **WP-08** adds new files and changes `src/leaders.rs`, `src/proglog.rs` (internals only; WP-05 creates the file with the functions moved out of `exec.rs`/`build.rs`), the PoH lines of `feeds/shred.rs`, `feeds/entries.rs` and `feeds/mod.rs`, `send/tpu.rs`, and the derived-field hook in `src/rec/exec.rs`. It does **not** touch `exec.rs` or `build.rs`. Attempts carry the LeaderBook's snapshot struct from WP-05 on, and WP-08 fills more of its fields.
- **WP-09** adds new files plus two `main.rs` arms. It reaches the engine only through public APIs made in the core lane:
  - `Engine::new_offline` (WP-02);
  - `Engine::step` / `Engine::timers` and the journal (WP-03);
  - `exec::send_checks` (WP-05).
- **WP-10** touches only `tools/arbx-report/`.
- **WP-13** is a separate crate; the arbx side is one new file.
- **Shared files** (`main.rs`, `config.rs`, `Cargo.toml`) follow a convention, which makes their merges mechanical. Each WP adds its own config struct, its own `[section]`, and one clearly marked wiring block in `run()`. The core-lane WP merges first; the parallel WP rebases.

---

## 4. Stage 0 work packages

### WP-00 Day-0 safety switch

**Goal.** Stop the bleed before any refactor (R §4 "Day 0, config only", plus three small code changes):
- bundle-only sending;
- no sends on decoded triggers;
- the ≥1M band throttled;
- crowded pools ranked last;
- no new token accounts;
- the recorder on;
- `skip_failing_signers` working;
- a state-path latency baseline.

**Evidence.**
- W §2: the direct arm lost 24.4M, and rent cost 17.9M.
- R §1 "What we stop doing now", including "49% of attempts on the 21 pools with 150 or more bots".
- W §8: the recorder was off.
- Review F13, F16, F44.

**Changes.**
- **`deploy/arbx-stage0.toml`** (new, derived from `deploy/arb-w-live.toml`):
  - Paths repointed to the arbx tree: `out_dir = "/root/arbx/runs"`, `registry_json` and `templates_json` under `/root/arbx/data/`, and `seed_csv` naming a file that exists in `arbx/data`. `data/seed-pools-w4.csv` is copied from Cherry by WP-00b; until then the file names `data/seed-pools-merged.csv`, and the owner confirms the seed list (§9 OD-4).
  - `[strategy]`: `skip_failing_signers = true` (live had `false`, arb-w-live.toml:51); `state_triggers = true`; `confirm_trigger_ms` stays 60 until WP-04 removes it.
  - `[live]`:
    - `bundle_mix = true` and `tpu_max_expected_lamports = 1`, the p7-p10 combination that made every attempt bundle-only (res-pnl §3);
    - `sim_gate = false`;
    - `max_new_token_accounts = 0` (until WP-06 makes trades rent-neutral);
    - `settle_s = 3` (the p1-p9 value; fewer late landings missed);
    - `max_size_sol` as decided by the owner (OD-4; the file ships with the live value 4.2), recorded in `meta.json` `limits`.
  - Every non-bundle `[[send]]` gets `enabled = false`: helius, rpcfast, jito-tx, haan, astralane, bolt, tpu-direct, everstake, nozomi, blockrazor, flashblock, nextblock, jupiter, landx-fra3, landx-fra1, speedlanding.
  - `[record] enabled = true`, and `archive_feed = ""` until an entries feed is alive (erpc and constantk-prism delivered 0 messages in p12, res-code §1).
  - Jito `tip_share = 0.7` and `tip_max_lamports = 100000` (the live values).
  - The two deshred feeds' `account_include` (arb-w-live.toml:109, :115) gains the DAMM v2 program `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG`. Today DAMM v2 hints never arrive from them. If a provider refuses a fifth account, the feed error shows in `run.log` and the line is reverted.
- **`deploy/arb.toml:139-140`**: align to 0.7 / 100,000 to end the drift (R §3.6).
- **`config.rs`**:
  - `StrategyCfg` (:342-375) gains `decoded_sends: bool`, default `false`.
  - `LiveCfg` (:59-160) gains `big_band_min_expected_lamports` (default 1,000,000), `big_band_max_per_sec` (default 0.5) and `crowded_pools_file` (default `""`).
- **`engine.rs` `on_trigger`** (:611-672), when `!decoded_sends` (fixes F16):
  - Run the existing signer check (:622-624), the slippage check (:628-632), the accuracy `checks.insert` (:634-639) and the signer bookkeeping `trig_pending.insert` (:640).
  - Then count `trigger_hint_only`, push the hint's `rx_to_decided` sample, write the `triggers.jsonl` line with `opp: null`, and return.
  - The return comes before `preds.insert` (:641), `best_cycle` and the opportunity (:642-671). So `skip_failing_signers` works, signer statistics keep learning, and `predictions.jsonl` keeps its accuracy data.
  - This also neutralises the two places where decoded work blocks the state path: `state_trigger` skips a trigger the shred path already acted on (:213), and it skips any pool with a pending prediction (:215). With no decoded opportunities and no predictions, neither fires.
- **State-path stage timestamps** (F13):
  - `state_pending` (:126) carries, for each `(pool, txn)`, the receive time `t` of the first update stamped `txn` (`on_account` :878) and its engine dequeue time.
  - `state_trigger` fills `Stages {rx: t_update_recv, decoded: t_update_recv, engine: t_dequeue, resolved: t_eval_start, decided}` instead of one value (:226).
  - New latency series `state_recv_to_engine`, `state_engine_to_decided` and `state_recv_to_decided`. `exec.rs` `send` adds `t_fired` to the attempt's `st` and the series `decided_to_signed` and `signed_to_fired`.
  - These are the baseline that WP-02's gate compares against.
- **`exec.rs` `send`** (:540-625): write the attempt line after `paths.fire` (:624), not before it (:611). Today the line is flushed to disk (`write` :132) between signing and firing (F44).
- **`exec.rs` `copies`** (:421-536): for `Kind::Live`, if `expected ≥ big_band_min_expected_lamports`, take a token from a 0.5/s bucket or return `Err("live_skip_big_band_throttle")`.
- **Crowded pools** (F6):
  - `data/crowded-pools.json` lists the 21 pools with 150 or more distinct bots (PATTERNS.md item 10; per-pool bot counts from the patterns scan, `tools/analysis/patterns/analyze.py:32` `POOLBOTS`), with its source and date. If the intermediate is not in arbx, the owner copies it from Cherry with the WP-00b files.
  - `Exec::send`'s `Prio` (exec.rs:616) gets rank 2 when either pool is on the list. Today rank is 0 for Mriya-sourced pools and 1 otherwise. Crowded pools therefore queue behind everything else in the 5/s budget.
  - Attempts carry `crowded: true`, and the budget's drop counter is split by crowded or not.
  - Excluding them from bands of 100k and above is the alternative (OD-3).

**Offline acceptance (CI).**
- A unit test of the token bucket (rate, burst 1).
- A unit test of `Prio` with the crowded list (a crowded pool ranks behind both other ranks).
- `arbx check --config deploy/arbx-stage0.toml` lists only `jito-bundle` as enabled.

**Field acceptance (owner-run).**
- **A 10-minute shadow run:**
  - `counts.trigger_hint_only > 0`;
  - `trigger_skip_signer_fails` counted when it applies;
  - no decoded `opportunity` count;
  - `state_opportunity > 0`;
  - `predictions.jsonl` has lines;
  - the three state-path latency series have samples (their p50/p90/p99 is the WP-02 baseline).
- **Files expected in shadow** (F17): meta.json, run.log, status.jsonl, triggers, opportunities, predictions, arrivals, caps, txarr.log, rivals.jsonl, exec.jsonl, moves.log, slots.log, and `alts.jsonl` at exit.
- **Files not expected in shadow:** `poh.log` (written only when exec is on, main.rs:493-495, until WP-08), attempts/copies/outcomes/bundles (nothing is sent), and sims (only with `[sim] enabled`).
- **A second 10-minute shadow run with `[record] enabled = false`** gives the recorder's cost on the state path (F44).

**Measurement outputs.**
- `status.jsonl` counters `trigger_hint_only` and `live_skip_big_band_throttle`, and the crowded-drop split;
- the state-path latency series;
- all arb-lab streams (recorder on).

**Risk.**
- `max_new_token_accounts = 0` gives up about half of the tiny wins (12 of 23 wins created accounts) until WP-06. Accepted, because rent turned the bundle arm from +163k into −17.9M.
- Until WP-02, the legacy recorder runs on the engine thread: mutex locks and BufWriter writes in `Recorder::line` (record.rs:50) and the exec log flushes (exec.rs:132). That breaks invariant 5 for a few days (F44).
  - The worst case, the flush between signing and firing, is removed here.
  - The rest is measured by the recorder-on and recorder-off shadow runs.

**Effort.** 0.75 d.

---

### WP-00b Legacy fixtures

**Goal.** Make every known-answer test runnable offline (F12). The arb-lab files they need exist only on Cherry and, temporarily, in a session-scoped scratch copy.

**Already done in this revision.** The arb-lab files most at risk were preserved: attempts, outcomes, bundles, copies and status of w5h-p1 … w5h-p10, w5h2-p5 (the bolt trade) and w5h3-p2.
- They are in `testdata/legacy/raw/<segment>/*.jsonl.xz`: 5.3 MB, with sha256 in `testdata/legacy/raw.sha256` and provenance in `testdata/legacy/README.md`.
- They were checked for secrets before copying. `meta.json` and `.out` files were excluded.

**Changes.**
1. **`testdata/legacy/signatures.json`.** The ledger cases with full signatures and expected values, taken from res-pnl §2 and the raw outcomes:
   - a bundle win with an ATA create (rent 1,488,440);
   - a Token-2022 create (1,513,840);
   - w5h-p6#69 with the user volume accumulator (2,860,040, of which 1,346,200 is not recoverable);
   - a landed failure (fee only);
   - the bolt trade w5h2-p5#648.
2. **`testdata/wallet/<sig>.json`.** Those transactions, plus every landed transaction of w5h-p1..p10, fetched once from public RPC by `tools/capture-fixtures.py --wallet` (getTransaction, base64 with JSON meta; read-only). Estimate: under 100 transactions and under 2 MB.
3. **`testdata/legacy/expected.json`.** The known answers:
   - res-pnl's p1-p10 decomposition: trading net −2,337,448, rent 16,383,000, `profit_lamports` −16,201,607;
   - W §2's bundle-arm figures;
   - each case's ledger categories under the revised definitions (MEASUREMENT §4.42).
4. **Owner copies from Cherry** into `data/` and `testdata/legacy/` (no SSH from arbx work): `seed-pools-w4.csv`, the patterns per-pool bot counts (for `data/crowded-pools.json`), and any w5h `exec.jsonl.zst` that exists.

**Offline acceptance (CI).** A Rust test and a Python test load every fixture and check its sha256. The legacy known-answer tests of WP-07 and WP-10 read only these files.

**Effort.** 0.5 d.

---

### WP-01 Foundation: crate split, config hygiene, provenance, stop reasons, control, supervisor

**Goal.**
- Every run is attributable to an exact binary, config and program version.
- Every stop has a recorded reason.
- Config typos fail loudly.
- The supervisor has real controls (R §3.8 Provenance; res-stops recommendations).

**Evidence.**
- res-stops C1, C7-C9: 15 hot swaps, no build id, operator SIGINTs with no reason, a crash counter that counts operator kills, a broken records-only fallback.
- res-code §2: no `deny_unknown_fields`.

**Changes.**
1. **Crate split.**
   - A new `src/lib.rs` declares the modules now listed in main.rs:7-20 as `pub mod`, and `main.rs` becomes the CLI over `arbx::…`.
   - Integration tests (WP-09), offline subcommands (WP-12) and the verifier client need the library.
   - User-facing `arb-lab` strings (main.rs:1-6, help texts) are renamed to `arbx` once, here.
2. **Config hygiene** (config.rs):
   - `#[serde(deny_unknown_fields)]` on every struct: `Config` :7-44, `RecordCfg` :47, `LiveCfg` :59, `ExecCfg` :183, `SimCfg` :218, `CanaryCfg` :232, `PoolsCfg` :270, `RpcCfg` :287, `RpcEndpointCfg` :299, `StateCfg` :334, `StrategyCfg` :341, `Feed` :400, `SendPath` :499, `GateCfg` :541.
   - `config_version = 2` is required. `Config::load` (:557-600) bails on any other value, and it returns the raw bytes for hashing.
   - `Config::normalized_json()` serializes the parsed config, with defaults filled and keys sorted, for a hash that ignores comments and formatting.
   - **Legacy configs** (F19):
     - `deploy/arb-w-live.toml` moves to `deploy/legacy/arb-w-live.toml`, unchanged. It is the arb-lab record and is excluded from the definition of done.
     - `deploy/arb.toml` is brought to `config_version = 2` and stays maintained.
     - `deploy/arbx-stage0.toml` is the campaign config.
3. **Build provenance.**
   - `Cargo.toml` sets `[package] build = "buildinfo.rs"`. The name avoids a clash with the transaction builder `src/build.rs`.
   - `buildinfo.rs` exports `ARBX_GIT_COMMIT`, `ARBX_GIT_DIRTY`, `ARBX_DIRTY_SHA256` (sha256 of `git diff HEAD` plus the untracked files under `src/` and `Cargo.lock`), `ARBX_RUSTC`, `ARBX_PROFILE`, `ARBX_TARGET_FEATURES` and `ARBX_BUILD_TS`.
   - `rerun-if-changed` covers `src/`, `Cargo.lock`, `.git/HEAD`, the ref file `HEAD` points to (resolved when the build script runs), `.git/packed-refs` and `.git/index`. A new commit on the same branch then rebuilds the provenance (F20).
4. **`src/provenance.rs`** (new), run once at boot, off the hot path:
   - sha256 of `/proc/self/exe`;
   - the config file's sha256 and normalized sha256, and a frozen copy of the config written into the run directory;
   - **programdata of the route program** (8K8uyQDt; later arbx-exec) and of every venue program, fetched by RPC on the background runtime:
     - The ELF is hashed without the account's zero padding (F21). A programdata account is a 45-byte header (u32 state tag 3, u64 deploy slot, `Option<Pubkey>` upgrade authority, padded) followed by the ELF and zero padding up to the allocated length.
     - The ELF's end is the maximum of `e_shoff + e_shnum × e_shentsize` and the end of every section and program header's file range. sha256 and md5 are taken over `[45, 45 + end)`.
     - The procedure is documented in MEASUREMENT §4.2 and tested on the deployed 8K8uyQDt account, fetched once from public RPC into `testdata/programs/`. The test expects the reproducible build's md5 `809315be…`.
     - A mismatch with `[exec] expected_program_sha256` refuses live mode (reason `program_hash_mismatch`); in shadow it is only recorded;
   - host, pid, uid, argv (secrets are never in argv), and the clock sync state (adjtimex offset, plus `chronyc tracking` if present);
   - `meta.json` (main.rs:572-578) is rewritten to schema `arbx.meta/2`.
5. **Stop reasons.**
   - The tokio ctrl-c/SIGTERM task (main.rs:504-511) is replaced by `signal-hook` `SignalsInfo<WithOrigin>`, which gives the signal and the sender's pid and uid. The sender's cmdline is read from `/proc/<pid>/cmdline`.
   - A `StopReason` (MEASUREMENT.md A.5) is set once and written to `stop.json`, `run.log` and the final `status.jsonl` line.
   - Exit codes: 0 deadline, 10 operator stop, 20 safety stop, 30 error.
6. **Control socket** (`src/control.rs`, new): a Unix socket `<run dir>/control.sock` (mode 0600) and `arbx ctl --run <dir> <cmd> --who <name> --why <text>`.
   - Commands: `status`, `pause-sending`, `resume-sending`, `shadow`, `stop`. Every command goes to `control.jsonl`.
   - Pause and shadow flip a `SendGate`, an atomic mode with a reason, that `Exec::wants_send` (exec.rs:315-329) reads.
7. **CLI.**
   - `--shadow` forces shadow mode whatever the config's `mode`, and is recorded in meta.
   - `--budget-left <lamports>` replaces the supervisor's `sed` rewrite of the config.
   - `--campaign-dir <dir>` tells a segment its campaign (used for campaign-wide stops in WP-07).
   - `arbx provenance --config <file>` prints meta without starting feeds.
8. **Supervisor** `deploy/run-w.sh` (new; it replaces arb-lab's tools/analysis/cherry/run-w.sh, removed from arbx with tools/analysis in I-11):
   - **Campaign directory** `runs/<campaign>/`. At start the supervisor copies the binary to `runs/<campaign>/arbx-<sha8>` and the config to `config.frozen.toml`, writes `campaign.json`, and runs only those copies. A mid-campaign `mv` of a new binary no longer affects the campaign.
   - **Budget** per segment via `--budget-left`, so the config hash stays constant. Today `sed` at run-w.sh:36 changes it every segment.
   - **Controls by file:** `<campaign>.pause`, `<campaign>.next` (restart now; the file's text is the reason) and `<campaign>.stop` (reason text). No more `kill -STOP`.
   - **Early ends** are classified from `stop.json` as operator, safety or crash. Only crashes count toward the crash limit. A safety stop (exit 20) ends the whole campaign, not only the segment (WP-07).
   - **The records-only fallback** runs with `--shadow` instead of failing at main.rs:487.
   - **Budget source:** the ledger after WP-07. Until then the budget is read from each segment's last status line only (`failed_fees_lamports` before WP-02, `failed_fees_total_lamports` after), and lines are never summed.
   - **Logs:** a structured `supervisor.jsonl` beside the text log. Each segment's stdout and stderr go to `<campaign>/<segment>.out`, as today.
   - **Compression** moves into the bot (WP-02), so the post-segment `zstd` (run-w.sh:42) goes.
   - **Passphrase, residual risk** (F31): the keystore passphrase stays in the supervisor's bash memory for the whole campaign (res-stops "Other supervisor hazards").
     - Mitigations kept: it is read with `read -rs`, never in argv or the environment, and passed to each segment over a pipe; `ulimit -c 0` and `set +o history` are set; the variable is cleared at exit.
     - A hardened `arbx campaign` launcher (zeroized, mlock'd buffer; segments spawned from Rust) is owner decision OD-7.

**Config keys.** `config_version`; `[exec] expected_program_md5`, `expected_program_sha256`; `[control] socket = true`.

**Offline acceptance (CI).**
- A config with a misspelled key fails to load, with the key's name in the error; `config_version = 1` fails.
- `arbx provenance` prints build, config and binary hashes (unit test on the hashing helpers).
- The programdata ELF-end test on the fixture account gives md5 `809315be…`.
- **Signal test:** a hidden `arbx wait-signal --dir <tmp>` subcommand installs the same handler and stop path as `run`, without feeds or RPC. The test sends it SIGINT and checks that `stop.json` has `reason = signal`, that the sender pid equals the test's pid, and that the exit code is 10.
- **Control test:** `pause-sending` makes `wants_send` return `None` and writes a `control.jsonl` line.
- **Supervisor dry run:** `tools/test-run-w.sh` runs the supervisor with `ARBX_DRY=1` and a fake binary that exits with given codes and stop reasons. It checks that operator stops are not counted as crashes, that exit 20 ends the campaign, that the budget is not summed across lines, and that the config is never edited.
- The `build.rs` `rerun-if-changed` list includes the resolved ref file (unit test on the helper that resolves it).

**Field acceptance (owner-run).** Every segment directory of a short campaign has `meta.json` (build, config and program hashes) and `stop.json` with a reason.

**Measurement outputs.** `meta.json` v2, `stop.json`, `control.jsonl`, `campaign.json`, `supervisor.jsonl`.

**Risk.** Crate-split churn (mechanical). The `signal-hook` dependency.

**Effort.** 2 d.

---

### WP-02 Recorder framework (always on, off the hot path) and the background runtime

**Goal.**
- Recording that is complete by default and can never slow or block trading: separate threads, bounded queues, drop counters, compressed rotating files, schema versions, a disk budget and a manifest.
- A runtime split, so that background RPC work cannot delay the state stream or sends.

**Evidence.**
- W §8: no rivals, exec, txarr or moves records after w5h2-p3.
- `RecordCfg.enabled` defaults to false (config.rs:47-54).
- `Recorder::line` (record.rs:50) locks a mutex and writes on the caller's thread.
- `write` (exec.rs:132) flushes every attempt and outcome line on the engine thread.
- `alts.jsonl` is dumped once at exit, 107-115 MB uncompressed (engine.rs:261-269, res-stops).
- Compression happens after the run (run-w.sh:42).
- The state stream, the feeds, Jito sends and RPC fetches share `worker_threads(2)` (main.rs:502; review F9).

**Design** (details and on-disk formats in MEASUREMENT.md §1, §4.12-§4.13 and §5):
1. **Runtimes** (`src/runtime.rs`, new; F9):
   - **`rt_hot`** is today's 2-worker runtime (main.rs:502). It runs only the state stream, the shred and gRPC feeds, the Jito send and result streams, and keep-alives.
   - **`rt_bg`** is new: `bg_threads` workers (3), named `arbx-bg`, niced +5. It runs every RPC call:
     - the lookup-table and DLMM-array fetches (engine.rs:522-531, :963-972 move here);
     - the WP-03b fetchers, WP-07 snapshots, WP-01 programdata reads, and WP-08 leader metadata and probes.
   - Responses over 256 KiB are parsed in `spawn_blocking`.
   - Every `Rpc` client is bound to `rt_bg`, and a debug assertion fails if an RPC future is polled on an `arbx-hot` thread.
2. **`src/rec/`** replaces `src/record.rs`. A global `Recorder` (OnceLock) owns one bounded `crossbeam_channel` per stream class (F26; the same lists as MEASUREMENT §1.2):

   | Class | Streams |
   |---|---|
   | core | ledger, wallet, attempts, copies, bundles, outcomes, decisions, commits, control, stop |
   | replay | accounts, journal |
   | chain | exec, blocks, slots, slotidx, txfetch, txarr, arrivals, moves, poh, slots-feed, alts, leaders, triggers, predictions, caps, sims, verify |
   | bulk | entries-<feed>, rivals, validators, discovery |
   | slow | everything else |

   - Producers call `rec::emit(stream, rec)`, which is a `try_send`. When a queue is full it increments `dropped[stream]` (an AtomicU64) and returns at once.
   - Records are typed structs. No JSON is formatted on producer threads for hot and chain streams.
   - Large payloads (account data, transaction bytes) move as `Arc<[u8]>`, not copies.
3. **Writer threads**, one per class, run with `setpriority` +5 and optional CPU affinity away from the engine core.
   - They serialize (serde_json, or the binary framing for `accounts` and `journal`) and feed a `zstd` stream encoder (level 3).
   - They end a zstd frame every `flush_ms` (1,000) or every 4 MiB, and rotate at `rotate_mb` (256 MiB raw) or `rotate_min` (60). Because every flush ends a frame, a file can be read up to its last complete frame while the run continues.
   - File names are `<stream>.<NNN>.<ext>.zst`. The first record of every file is a schema header.
4. **Small streams** (meta, stop, manifest, status, control, events, keepalive) are plain line-buffered JSON lines, so they stay tail-able.
5. **Drop handling by class.**
   - **Core:** queues are large enough that a drop means a stalled writer. Any core drop writes an `events.jsonl` `recorder_drop` record, and the SendGate goes to shadow (reason `core_record_loss`) for the rest of the segment, because the segment can no longer be reconciled. The next segment starts live again (F32).
   - **Replay** (`accounts`, `journal`): queues of 1M and 512k records, per-stream sequence numbers, and a `gap` mark written with the next successful record. A drop does not stop trading, but replay refuses the gap interval, and the Stage-0 exit requires zero drops (F11, F27).
   - **Chain:** drops are counted and must stay under 0.01% for the Stage-0 exit.
   - **Bulk:** may drop under pressure.
6. **Disk budget** (`src/rec/disk.rs`), checked every 10 s: the run directory's size against `disk_budget_gb`, and the filesystem's free space against `min_free_gb`. Actions run in order, each logged:
   1. stop the entries archive;
   2. stop rivals;
   3. lengthen the accounts keyframe interval 4× (a format change: no record is dropped);
   4. finally, SendGate shadow and stop with reason `disk_budget`.

   Core and replay streams are never dropped by the budget.
7. **`manifest.json`** is written every 60 s and at close: files, bytes, records, first and last time, drops, queue high-water marks, and the sha256 of closed files.
8. **Migration of every existing writer.** Formats stay the same except for the schema header, unless MEASUREMENT.md says v2.
   - engine.rs: `out_trig`, `out_opp`, `out_pred`, `out_status`, `out_arr` (:101-106, :186, :366-370, :397, :413, :603-609, :649-653, :939, :1001-1007); `write_txarr` (:250-258); `write_alts` (:261-269; becomes events in WP-04); `record_rival` (:272-312); moves (:882-887); `record_caps` (:844-874).
   - exec.rs: sims, attempts, outcomes (:131-132, :149-151, :264, :296, :383-414, :611, :826).
   - send/mod.rs: copies and keepalive (:740-747, :769, :792, :864). send/jito.rs: bundles (:251, :261, :348-357).
   - feeds: `POH_LOG` (feeds/mod.rs:149-151, :171-179; feeds/shred.rs:247-266); slots.log (feeds/mod.rs:164-166); the entries archive (feeds/mod.rs:159, record.rs:53-63); `rec_exec` (grpc.rs:324, :336-356).
   - main.rs: the recorder is always initialised (:545-550 lose their condition), and the `run.log` writer (:531-532) moves to the slow class.
   - Diagnostic `eprintln!`/`println!` lines in the run path (e.g. exec.rs:649, :729 gate and cool-down messages) also go to `events.jsonl` (kind `log`). The `.out` file stays (F30).
9. **status.jsonl v2 counter semantics.**
   - Every number is `_total` (monotonic since process start), `_delta` (since the previous line) or `_now` (a gauge). Latency percentiles name their window.
   - `failed_fees_lamports` (exec.rs:820, :835) becomes `failed_fees_total_lamports` plus `failed_fees_delta_lamports`.
   - engine.rs `write_status` :402-417 and exec.rs `status` :831-839 change accordingly.
10. **New health streams.**
    - `feedhealth.jsonl`: per feed every 10 s, from `FeedCounters` (feeds/mod.rs:69-75), extended with first-arrival counts, last-message time and channel drops.
    - `resources.jsonl`: CPU, RSS, queue depths and high-water marks, recorder drops, disk, UDP receive drops from `/proc/net/udp`, and per-runtime busy time.
11. **`Engine::new_offline(reg, store, cfg)`** builds an engine with no RPC, runtime or watch channel; fetch requests are recorded instead of sent. It is used by the benchmark below and by WP-09 (F11, F13).

**Config keys.** `[record]`: `disk_budget_gb` (40), `min_free_gb` (25), `rotate_mb` (256), `rotate_min` (60), `flush_ms` (1000), `zstd_level` (3), `archive_feeds` (a list; replaces `archive_feed`), `queue_*` sizes, `accounts_keyframe_every` (64). `[runtime] bg_threads = 3`. `enabled` is removed: recording cannot be turned off.

**Offline acceptance (CI).**
- Rotation with a tiny `rotate_mb` produces several files, each starting with a header and each decodable on its own.
- A reader decodes records from a file that is still being written (frames end at each flush).
- A stalled writer (test hook) makes `emit` drop and count, never block. `emit` p99 stays under 1 µs at 100k records/s (an `#[ignore]` timing test).
- A replay-class drop writes a `gap` mark.
- The disk-budget ladder runs against a fake filesystem-usage provider.
- **Runtime isolation (F9):** a fake RPC serves 5 MB JSON blocks at 4/s on `rt_bg` while a synthetic state stream runs on `rt_hot`. Two latencies, each with and without the fake load, must stay within 10%:
  - state-update arrival to engine dequeue, p99;
  - engine dequeue to `t_sent` on a fake send path, p99.
- **Engine benchmark (F13):** 100k synthetic account updates through `Engine::new_offline`, with the recorder on and off. With the recorder on, `state_recv_to_decided` p99 is within 5 µs of the recorder-off run.

**Field acceptance (owner-run).**
- A 20-minute shadow run produces every arb-lab stream plus manifest, feedhealth and resources, with 0 drops.
- The state-path series from WP-00 have a p99 within 5 µs of the WP-00 baseline.
- `strace -f -e trace=write` on the engine thread shows no writes (a manual check, recorded in the merge note).

**Measurement outputs.** `manifest.json`, `events.jsonl`, `feedhealth.jsonl`, `resources.jsonl`, `status.jsonl` v2, and every existing stream compressed and rotated.

**Risk.**
- `zstd-sys` needs a C toolchain (present).
- The writers use about one core in the worst case; they are nice'd and measured in `resources.jsonl`.
- Lookup-table fetches move to `rt_bg`. That is no slower when `rt_bg` is idle, and their latency is measured in `txfetch`.

**Effort.** 3 d.

---

### WP-03 Chain inputs, raw chain recording, input journal, gRPC probe

**Goal.** Capture everything the chain says about the watched accounts and our wallet, with the identifiers that state consistency, the ledger and replay need, and journal the engine's inputs so that runs replay deterministically. Keep arb-lab's PumpSwap transaction stream.

**Evidence.**
- `write_version` is parsed and then dropped (#4 in §1).
- Executed-transaction results exist only for PumpSwap, without inner instructions (#23).
- Bundles have no recent-blockhash source (R §5).
- Interslot slot updates are off (grpc.rs:367; F15 corrects revision 1).
  - `filter_by_commitment: Some(false)` already delivers processed, confirmed and finalized; only interslot updates (first-shred, completed, created-bank, dead) are off.
  - The engine ignores the status (engine.rs:350).
- 16 failed landings of ours went unrecorded (W §6 P6).
- BAM status comes from a static file (W §8).
- Replay needs a journal written at the dequeue point (review F11).

**Design.**
1. **Account updates.**
   - `Event::Account` (feeds/mod.rs:37) gains `write_version`, `is_startup`, `src` (stream, rpc or boot) and `aseq`. `aseq` is the update's sequence number in `accounts.bin`, assigned when the feed task emits the record (F25). `forward` (:202-203) stops dropping these fields.
   - Data becomes `Arc<[u8]>` (store.rs:9 `Acct.data` changes type only).
   - Every update, including stale ones the store will refuse, goes to `accounts.bin`. The store's accept or stale verdict is recorded in the journal's ACCOUNT record, because the feed task cannot know it (F24).
2. **Extra watched accounts** on the state stream (`Registry::static_accounts` pools.rs:154-166, plus a new list):
   - the Clock sysvar, for chain time (used in WP-04);
   - the DLMM bitmap-extension PDA of every DLMM pool (pools.rs:93), whether or not it exists; an update arrives if one is created (used in WP-06);
   - the programdata accounts of the route program and of every venue program (upgrade detection, used in WP-07);
   - **our wallet and its token accounts.** Every landed transaction we pay for writes the wallet account, even when it fails, because the fee is charged. The `txn_signature` of these updates lists our landed transactions; WP-03b fetches them (F1).
3. **Transaction stream** (F1). The provider allows one transaction filter with one account (deploy/legacy/arb-w-live.toml:117-123). That filter **stays on the PumpSwap program**, as in arb-lab. It delivers:
   - every PumpSwap transaction, failed ones included (`failed: None`, grpc.rs:308), with its block index (`TransactionInfo.index`) and full meta;
   - the authoritative write set W(T) of every PumpSwap transaction (WP-04).

   `[[state.tx_stream]]` stays configurable (`name`, optional `url`, `account_include` with literal keys or `@watched_writable` / `@venue_programs`, `failed`, `max_accounts`); the Stage-0 default is that single entry.
   - In w5h, PumpSwap pools were touched by 41-48% of watched transactions (§0). The rest comes from WP-03b.
   - A second filter or provider that covers the other venues is owner decision OD-1. It needs a config change only.
4. **Full transaction meta** (grpc.rs `PbMeta` :60-71):
   - `inner_instructions` (5), with the wrapper `InnerInstructions {index 1, instructions 2}` and `InnerInstruction {program_id_index 1, accounts 2, data 3, stack_height 4}`;
   - `inner_instructions_none` (10), `log_messages_none` (11), `return_data` (14), `cost_units` (17);
   - `PbTokenBalance.program_id` (5), `PbUiAmount.decimals` (2), `PbMessage.recent_blockhash` (3).

   Tag numbers are pinned by encoded fixtures against a vendored copy of the proto text in `testdata/proto/`.
5. **`arbx grpc-probe --config <file>`** (`src/probe.rs`, new; F14). With the configured tokens, it subscribes for 30 s to each subscription the plan needs and reports accepted or refused, the error text and message counts:
   - the accounts filter at the full list size (at least 3,000 keys);
   - slots with interslot updates;
   - `blocks_meta`;
   - the transaction filter with 1, 2 and 5 accounts (to record the limit);
   - `blocks` with `account_include` of the venue programs (for OD-1);
   - the deshred filter with 5 programs.

   It writes `probe.json`, a dated copy goes into `docs/`, and the result is recorded in §9. It must run before WP-05 starts.
6. **Block meta.**
   - If the probe accepted `blocks_meta` (SubscribeRequest field 5; update field 7), it is subscribed.
   - The subscription produces a new `Event::BlockMeta {slot, blockhash, parent_slot, parent_blockhash, block_height, block_time, executed_transaction_count, entries_count}`, written to `blocks.jsonl` and fed into WP-03b's blockhash ring.
   - If the probe refused it, the subscription stays off, and WP-03b's other sources supply blockhashes.
7. **Slots.** `interslot_updates = true` and all statuses (processed, confirmed, finalized, first-shred, completed, created-bank, dead), with `parent` (2) and `dead_error` (4), go to `slots.jsonl` and to the engine (WP-04's fork tree).
8. **Provider timestamps.** If the provider fills `SubscribeUpdate.created_at` (11), the provider-side lag `t_recv − created_at` per stream goes to `feedhealth.jsonl`.
9. **The `exec.jsonl` v2 writer** moves from grpc.rs:336-356 to `src/rec/exec.rs`. It writes the full fields (MEASUREMENT.md §4.14): raw instructions, inner instructions, logs, balances, loaded addresses and compute-budget parameters. Derived fields (transfer classification, bundle membership) come in WP-08. `wallet.jsonl` (WP-03b) uses the same writer.
10. **Basic LeaderBook** (`src/leaders.rs`, new):
    - The leader schedule comes from `getSlotLeaders` in 400-slot windows, refreshed every 100 slots on `rt_bg`.
    - The leader kind (Jito, BAM, other) has named sources (F39), each recorded with its fetch time (as implemented: WP-03 deviation 6, WP-08):
      - Jito and BAM: the Jito validators API (`https://kobe.mainnet.jito.network/api/v1/validators`): `running_bam` gives BAM, `running_jito` Jito, and a validator absent from it runs neither;
      - Jito: validator identities seen in our bundle results (`Accepted` / `Processed` `validator_identity`): a bundle result shows the leader takes Jito bundles, not that it runs BAM; a public BAM list if one is identified (none is assumed);
      - a dated static fallback `data/validators-meta.json`;
      - (WP-08) the client a validator announces in gossip (`JitoLabs`, `AgaveBam` / `FireBAM`, plain `Agave`), for a validator no other source names.
    - It exposes `leader(slot)`, `kind(slot)` and `snapshot(slot)`, a struct that WP-05 copies into attempts and WP-08 fills further. send/tpu.rs `Book` (:39) stays until WP-08 switches it over.
11. **Input journal** (`src/rec/journal.rs`; moved here from WP-09, F11):
    - **The run loop** (`Engine::run` :324-358) is restructured into two calls:
      - `Engine::step(ev, t_engine)`: the engine reads the clock once per event, and that value (`t_engine`) is journaled and used for every decision made while handling the event;
      - `Engine::timers(t)`: timeouts are evaluated only here, and each call is journaled as a TIMER record. It runs at today's spin and `recv_timeout` exits (:331-346) and at the per-event checks (:355-357).
    - **Inputs from other subsystems** that change engine or send-check decisions reach the engine as events on its channel and are journaled as INPUT records: blockhash-ring heads, leader-schedule windows, SendGate changes, quarantines, in-flight releases and health changes.
    - **Account updates** are journaled by `aseq` reference, with the store's verdict.
    - `journal` and `accounts` are in the replay class (WP-02).
    - **Only recordings made from WP-03 on are replayable.** WP-04's replay acceptance therefore runs on a new recording.

**Files.**
- feeds/grpc.rs: messages :25-195, `feed_once` :307-330, `accounts_once` :361-411.
- feeds/mod.rs: `Event` :35-45, `forward` :154-206, `start_state` :209-226.
- src/leaders.rs, src/probe.rs, src/rec/accounts.rs, src/rec/journal.rs, src/rec/exec.rs.
- store.rs (data type only).
- engine.rs: `run` → `step`/`timers` :324-358; new `Event` arms at :347-354.
- config.rs: `StateCfg` :334-339 extended; `TxStreamCfg`, `LeadersCfg`.
- main.rs: wiring at :515 and :552; the `grpc-probe` arm.

**Config keys.** `[state] watch_clock = true`, `watch_programdata = true`, `watch_wallet = true`, `slot_statuses = "all"`, `block_meta = "auto"` (on if the probe accepted it); `[[state.tx_stream]] name, url, account_include, failed, max_accounts`; `[leaders] validator_lists = [...]`, `static_fallback = "data/validators-meta.json"`, `refresh_min = 60`.

**Offline acceptance (CI).**
- Prost round-trip tests: an account update with `write_version` and `txn_signature`; a transaction with inner instructions, return data and loaded addresses; block meta; a slot with `parent` and `dead_error`. Field numbers are asserted against `testdata/proto/`.
- **Synthetic stream fixture** (F12): `testdata/grpc/*.bin` holds prost-encoded `SubscribeUpdate` sequences built by a test generator:
  - wallet and pool account updates, PumpSwap transactions, slots with forks, and block meta;
  - a test feeds them through `forward` into a channel and checks the `Event` fields and the `accounts.bin` and `journal.bin` records (including `aseq` references).
- **Journal determinism:** the same journal fed twice into `Engine::new_offline` gives the same internal state digest and the same decisions.
- LeaderBook window refresh and kind lookup with a fake RPC.
- `grpc-probe` against an in-process fake Yellowstone server that refuses `blocks_meta` and accepts the rest: `probe.json` reports exactly that.

**Field acceptance (owner-run).**
- `arbx grpc-probe` on the Stage-0 config, with the result recorded in §9.
- **A 1 h shadow run:**
  - the number of `accounts.bin` records equals the store's `updates_total + stale_total`, each with `write_version` and `txn`;
  - `exec.jsonl` has a record with `idx` for 100% of the signatures that wrote a watched PumpSwap pool;
  - `slots.jsonl` carries `parent`;
  - `journal` and `accounts` have 0 drops;
  - every wallet-paid landing in the hour appears as a wallet-account update with its `txn` (the check against `getSignaturesForAddress` is in WP-03b).

**Measurement outputs.** `accounts.bin`, `journal.bin`, `exec.jsonl` v2 (PumpSwap from the stream), `blocks.jsonl` (if offered), `slots.jsonl`, `leaders.jsonl` (schedule and kind), `probe.json`, provider-lag gauges.

**Risk.**
- The provider may refuse `blocks_meta` or interslot updates; the probe finds out before WP-05.
- The journal adds about 0.5-1 GB/h (MEASUREMENT §5).

**Effort.** 4 d.

---

### WP-03b Chain fetch: wallet transactions, watched-transaction backfill, block index, blockhash sources

**Goal.**
- Every landed transaction of ours is recorded and reconciled.
- Every executed transaction touching a watched account, on every venue, has an `exec.jsonl` record with its block index, up to the capacity that is bought. The required capacity is measured and printed, never hidden.
- Bundles have several independent blockhash sources (F1, F10, F14).

**Evidence.**
- Review F1: revision 1 moved the single transaction filter to `@wallet` and planned a 10 rps backfill. That covers 7-20% of watched transactions and gives no block index.
- §0: watched transactions run at 31-60/s on the w5h registry and 3.72 slots/s; 52-59% of them are not PumpSwap.
- res-code §3F: Haan's RPC was rate-limited 297 times in p12.

**Design.** Every component runs on `rt_bg`. Results go to the recorder and, where the engine or ledger needs them, to the engine as events.
1. **Wallet transactions** (`src/chainfetch/wallet.rs`). A signature of ours comes from any of four sources:
   - (a) the `txn` of every wallet-account or wallet-token-account update on the state stream (WP-03 item 2);
   - (b) our attempts' signatures, at signing;
   - (c) Jito `processed` results;
   - (d) `getSignaturesForAddress(wallet)` over the last hour, run hourly.

   Each new signature is fetched once with a bounded `getTransaction`: base64 with JSON meta, the highest supported version, a 2 s deadline, and retries at 1 s, 5 s and 30 s. After 10 minutes the fetch gives up, with a `txfetch` error.
   - The result goes to `wallet.jsonl` and to the engine (ledger, settlement).
   - A signature found by (d) but not by (a) is recorded as `wallet_update_missing`. That tests the assumption that failed landings write the wallet account; (b)-(d) cover the case where it does not hold.
   - The rate is a few calls per minute.
2. **Watched-transaction backfill** (`src/chainfetch/backfill.rs`).
   - **What is queued:** after `after_ms` (1,500) without an `exec.jsonl` record, a getTransaction is queued for:
     - every `txn` seen in a watched-account update;
     - every shred-forwarded signature touching a watched account that the slot index (item 3) shows in a confirmed block. That second source catches failed transactions, which write nothing.
   - **Priority:** our attempts' route accounts, then Tier-A pools, then the rest.
   - **Rate:** `rps = "auto"` sizes itself to 1.25 × the measured rate of uncovered signatures (a 1-minute EWMA), capped by each provider's `max_rps` in config. When the cap binds:
     - `need_rps_now` exceeds `have_rps_now` and the backlog grows;
     - past `max_backlog` the oldest low-priority items are dropped and counted;
     - the coverage gauge falls. Nothing is hidden.
   - **Sizing from recorded data:** non-PumpSwap watched transactions in w5h came to 16-35/s, plus failed watched transactions (measured here for the first time). They scale with the registry. With today's providers this is above the demonstrated rate limits, hence OD-1.
3. **Slot index** (`src/chainfetch/slotidx.rs`; F1, F10).
   - **The fetch:** for every confirmed slot (about 3.7/s), one `getBlock(slot, {transactionDetails: "signatures", rewards: false, commitment: "confirmed", maxSupportedTransactionVersion})`. The ordered signature list is the block index. Position equals Yellowstone `TransactionInfo.index`, and this is verified on every slot against the PumpSwap stream's `idx`.
   - **What it yields:**
     - `idx` for every `exec.jsonl` and `wallet.jsonl` record (`idx_update` lines);
     - `slotidx.jsonl`, one line per slot: blockhash, parent, height, block time, transaction count, and the positions of every signature we track (watched writes, shred-seen watched transactions, ours);
     - `missing`: tracked signatures stamped in this slot by an account update but absent from the confirmed block, which is fork evidence for WP-04.
   - **Size:** the response is about 100-300 KB (est.; mostly vote signatures) and is parsed in `spawn_blocking`. A skipped slot is recorded as such.
   - **Block-ordered context per attempt** (`blockctx`) is derived from `accounts.bin`, `slotidx.jsonl` and `exec.jsonl` by the toolkit (WP-10). The bot no longer fetches full blocks per attempt window, which removes F10's rate problem.
   - **Coverage sampler:** one full block (`transactionDetails: "full"`) every `sample_every_s` (60). It measures the share of watched-touching transactions in the block that no source told us about, which checks the coverage denominator itself.
4. **Blockhash sources** (`src/chainfetch/blockhash.rs`; F14). A ring of `(hash, slot, height, src)` is fed by:
   - `blocks_meta` (WP-03, if offered);
   - the slot-index responses (confirmed blockhash and height);
   - the last entry hash of each completed slot from the shred and entries assemblers (that slot's blockhash; its height comes from the slot index when known);
   - `getLatestBlockhash` (confirmed), polled every 400 ms.

   The builder (WP-05) takes the newest entry that meets `blockhash_commitment`, and `attempts.blockhash.src` records the source. Sources disagreeing on the same slot are recorded as an event.
5. **`rpc.rs`:**
   - `call_bounded(method, params, deadline, retries)` is used by every chain-fetch component and later by settlement.
   - `Rpc::only` takes a role (`boot`, `exec`, `backfill`, `wallet`, `slotidx`, `blockhash`, `snapshot`, `leaders`). Stats aggregate per (role, provider) in a global registry, reported in `resources.jsonl` (F29; today every `Rpc::only` client gets fresh, invisible `Stats`, rpc.rs:69-72).

**Files.** `src/chainfetch/{mod,wallet,backfill,slotidx,blockhash}.rs`, rpc.rs, config.rs (`ChainfetchCfg`), main.rs (one wiring block), `testdata/rpc/` (recorded RPC responses).

**Config keys.** `[chainfetch] after_ms = 1500`, `rps = "auto"`, `max_backlog = 200000`, `sample_every_s = 60`, `blockhash_poll_ms = 400`, `[[chainfetch.provider]] name, roles, max_rps`.

**Offline acceptance (CI).** Each test runs against a fake RPC that serves `testdata/rpc/` responses:
- wallet discovery from synthetic wallet updates and from a `getSignaturesForAddress` page, with deduplication;
- backfill priority and the auto rate under tokio's paused clock, including the backlog drop and the gauges;
- slot-index `idx` mapping, `missing`, and a skipped slot;
- the blockhash ring: source choice, staleness, and disagreement;
- per-role stats.

**Field acceptance (owner-run, 24 h shadow or live).**
- `wallet.jsonl` matches `getSignaturesForAddress` 100%, and `wallet_update_missing` is reported.
- The slot index covers at least 99.9% of confirmed slots.
- At least 99% of `exec.jsonl` records have `idx` within 10 minutes.
- `need_rps_now` is recorded for OD-1.
- Exec coverage meets the Stage-0 gate (§6), or OD-1 is open.

**Measurement outputs.** `wallet.jsonl`, `exec.jsonl` (backfilled records, `idx_update`), `slotidx.jsonl`, `txfetch.jsonl`, the status `chainfetch` section (need and have rps, backlog, coverage, sampled unseen share), and per-role RPC stats.

**Risk.**
- Provider rate limits bind (OD-1).
- `getBlock` with signatures only may be refused or metered by a provider; the role-to-provider map lets it run on whichever provider allows it.

**Effort.** 2.5 d.

---

### WP-04 State consistency: price only committed, complete, canonical states

**Goal.** Price only states that existed on chain, never half of one, and never one from an abandoned fork once that is known (R §3.2). This removes the two engine defects behind 10 of the 16 biggest losses.

**Evidence.** W §4 "Phantom quotes", W §7.1-7.2; R §3.2.1-3.2.4; D §4 open question 4; res-engine §3 ("The biggest gaps are phantoms"); review F2-F5, F32, F33.

**Design.**
1. **Committed state only.** `preds` is removed from every pricing path:
   - the field (engine.rs:86) and the prune (:384);
   - its use in `leg` (:567-585), which now reads the store only;
   - the insert in `on_trigger` (:641), the skip in `state_trigger` (:215), and the removal in `on_account` (:890).

   Decoded swaps (`decode_swaps` :546-561, `on_trigger` :611-672) become hints. They:
   - register an expected write set W(T) with the CommitTracker (item 3). In fact every forwarded transaction does this, decoded swap or not: `process` (:441-478) already holds its resolved keys, and W(T) = its writable keys that are watched;
   - write `triggers.jsonl`;
   - feed the accuracy monitor (item 13);
   - feed the activity map (`pool_prices` :458-469, unchanged).

   The confirm path is removed: `confirm_wait` (:120), `on_confirm` (:193-203), `expire_confirms` (:234-242), :355, :665-669, :892, and `StrategyCfg.confirm_trigger_ms` (config.rs:358-362). `deny_unknown_fields` then rejects old configs that still set it. WP-00's `decoded_sends` key also goes: there is no decoded send path left.
2. **Store versions.** `Acct {data, slot, write_version, txn, t_recv, aseq}` (store.rs:9).
   - `Store::update` (:30-36) accepts an update only if `(slot, write_version)` is newer. Today it compares slots only, so a same-slot reordering can overwrite newer data with older.
   - Each account keeps a ring of its last 8 versions, for fork rollback, pre-state accuracy and replay checks.
3. **CommitTracker** (`src/commit.rs`, new). The Stage-0 sources of W(T) are named here plainly (F2):
   - **`tx-stream`:** the PumpSwap filter (WP-03). Authoritative, for PumpSwap transactions only. The order of its arrival relative to the account updates is measured.
   - **`shred`:** a hint from live shred and deshred feeds through `Interest` (feeds/mod.rs:57-64). It arrives earlier, but 5 of 10 feeds are dead (res-code §1).
   - **`unknown`:** every other transaction, including aggregator-routed and bot-routed ones that no live feed delivered. Today that is most non-PumpSwap transactions.

   The API and resolution rules:
   - `register(T, W, src)` and `on_update(account, T, write_version, slot, t)`.
   - Group states: pending → complete | superseded | timeout_unknown | timeout_quiescent | fork_dropped.
   - **Known W(T):** an update stamped T stays pending until every account in W(T) has an update stamped T or a newer `write_version`, or until `commit_timeout_ms` (5) passes.
   - **Unknown W(T):**
     - the group resolves when no update stamped T has arrived for `quiescence_ms`;
     - a route touching the group's pool is evaluated only if no account of either of its pools was written in the last `quiescence_ms` (route-level quiet, reason `route_not_quiet`).
   - **`quiescence_ms` is set from data.** WP-03 recordings give the spread between the first and last update stamped with the same `txn`, and the default is its measured p99.9. 3 ms is a placeholder until it is measured.
   - **Late members:** an update stamped T that arrives after T's group resolved is counted as `late_member`. Every decision priced on that route in between is marked `torn_suspect`. A sent `torn_suspect` decision is listed in R2.
   - Every group is written to `commits.jsonl` with its `w_src` and its lag from the first shred of T.
4. **Route readiness** (F3). `Store::route_view(route) -> Result<RouteView, NotReady>`, with `RouteView {state_version, min_slot, max_slot, age_ms}`.
   - **Consistency set.** Readiness is checked per pool, over the pool's consistency set: the accounts every swap of that pool writes.

     | Venue | Consistency set | Notes |
     |---|---|---|
     | PumpSwap | {vault0, vault1} | The pool account is not in the set. This matches the parts the code already waits for (`state_trigger` engine.rs:209, `check_prediction` :930) |
     | Raydium CPMM | {pool, vault0, vault1} | |
     | Raydium AMM v4 | {vault0, vault1} | Whether swaps write the amm account is measured first in WP-03 recordings |
     | DLMM | {lb_pair} | Every bin array the quote crosses must also be present and not pending |
     | DAMM v2 | {pool} | |

   - **Other parts** (fee config, global config, mint extras, the bitmap extension, the PumpSwap pool account) must be present and not pending, with no age rule.
   - **Skew rule:** within one pool's consistency set, the newest and oldest slots are at most `max_part_skew_slots` (2, today's value at store.rs:59) apart. Slots are **never compared across pools**: an idle pool is fine at any age.
   - **Lag rule:** the store is at most `max_tip_lag_slots` (2) behind the chain tip.
   - This replaces the snapshot skew check (store.rs:58-60), and with it the PumpSwap exemption (:60).
   - **Before the rule goes live,** WP-03 recordings are used to measure, per venue, how often consistency-set accounts carry different slots or `txn`s after a complete group. If the vaults of one venue skew, its rule is revisited before WP-05.
   - `state_version` is a digest of the route accounts' `(slot, write_version)`.
5. **Evaluation trigger.** `state_trigger` (:207-231) becomes `on_commit(group)`: for every Tier-A pool the group wrote, the pool's routes (`best_cycle` :788-839) are evaluated on the `RouteView`. The quiescence fallback evaluates after `quiescence_ms` without writes. `state_pending` and `flush_state` (:126, :245-247, :356, :893-896) go, and so does the :213 skip (there are no decoded opportunities any more).
6. **Chain clock.** The Clock sysvar (WP-03) gives `store.chain_clock()`.
   - The engine passes its `unix_timestamp`, not local time (`unix_now` :164), to `dlmm::quote` (venues/dlmm.rs:124) and `dammv2::quote_exact_in` (via `current_point` dammv2.rs:289).
   - If the clock is more than 2 slots old, DLMM and DAMM v2 routes are refused (reason `clock_stale`).
7. **Lookup-table retry.** `on_alt` (:533-542) no longer marks a table missing for the run (:537).
   - Retries run at 50 ms, 250 ms, 1 s and 5 s, then every 30 s, for up to 10 minutes.
   - Waiting transactions stay bounded (`alt_wait` cap 10,000); the oldest are dropped and counted.
   - `process` (:446) skips a transaction only while a retry is pending.
   - Every transition goes to `alts.jsonl` as an event, and the full table dump moves to stop time as `alts-final`.
8. **Warm-up gate and health.**
   - **Tier A** is every pool in the registry in Stage 0.
   - **`StoreHealth.ready`** turns on when every Tier-A pool has all its parts present and the store is within 2 slots of the tip. A pool whose parts cannot be fetched within 60 s is dropped from Tier A with an event, so one dead pool cannot hold the gate shut.
   - **Until ready,** decisions are recorded with reason `warmup` and nothing is sent: `Exec::wants_send` checks `health.ready()`.
   - **Service target** (R §3.2.4), checked every minute: the lag from the first shred of T to its complete commit is p50 ≤ 16 ms and p90 ≤ 30 ms.
     - The first-shred time is the minimum arrival over **unexecuted** feeds only (shred, deshred, entries). Today `SigInfo.first_t` (:37, :429-434) also takes yellowstone-tx arrivals, which come after execution (F33).
   - **On a breach** (F32): `slo_action = "log"` in Stage 0, so breaches are recorded and the gate is not changed; p90 ≤ 30 ms has never been measured. With `"shadow"`, five consecutive breaches put the SendGate in shadow (reason `state_slo`), and ten consecutive good minutes return it to live. Both transitions are recorded.
9. **Forks** (`src/forks.rs`, new; F4).
   - **Slot tree:** a tree of slots is kept from `slots.jsonl` updates (slot, parent, status).
   - **Abandonment:** when slot S becomes confirmed, every slot after the last root that is not an ancestor of S and is at most S is abandoned, even if it was never reported `dead`. `dead` slots and slot-index `missing` evidence (WP-03b) also abandon slots.
   - **On abandonment:**
     - the versions written in those slots are dropped from the rings;
     - each affected account falls back to its newest canonical version, or is refetched through `fetch_accounts` (:963-972, on `rt_bg`) if the ring has none;
     - the affected routes are marked dirty;
     - groups in those slots become `fork_dropped`.
   - **Known forks:** while two sibling slots are both unconfirmed, a route reading a version written in either is refused (reason `fork_pending`). Forks are rare, so this rarely applies; it is measured.
   - **Measurement:** decisions priced on a version later abandoned are counted (`fork_priced`), and SLOT journal records carry `parent`.
10. **Decision records.** Every evaluation writes one `decisions.jsonl` line: state version, route-wide age (the time since the last write to any route account; the X1 input), the consistency-set skew, `w_src`, `torn_suspect`, the reason code, and stage timestamps. `RouteIn` (exec.rs:40-71) gains `state_version`, `route_age_ms` and `decision`.
11. **Replay clock.** `feeds/clock.rs::now_ns` gains a replay mode (an atomic flag and a virtual time), so the engine, store, commit and fork code are deterministic under WP-03's `step`/`timers`.
12. **Signer filter.** `skip_failing_signers` keeps its default of true (config.rs:268). With decoded triggers no longer priced, it only filters hints.
13. **Accuracy monitor** (F5). Each decoded hint T is scored when T's group completes, against **T's pre-state**:
    - the pre-state is the version of each account T wrote as it was just before T's write, taken from the ring;
    - the prediction is recomputed on that pre-state with T's executed input when it is known (PumpSwap stream token balances, or a backfilled `exec.jsonl` record), else with the decoded amount;
    - the work runs at idle time on the engine thread, from a bounded queue whose overflow is counted;
    - a pre-state that is no longer in the ring is counted as `pre_state_unknown` and not scored;
    - `predictions.jsonl` keeps the at-hint comparison (arb-lab's measure: DAMM v2 matched 662 of 758, res-code §3) beside the pre-state score.

    No quarantine acts in Stage 0 (`accuracy_action = "log"`). The floor is set from the measured pre-state rate (WP-07, OD-8). R §3.3's "every successful swap" (aggregator-routed swaps included) and the closer check are computed offline by the toolkit's R8 (WP-10), through `arbx quote` on `accounts.bin` pre-states and `exec.jsonl` inner instructions.

**Config keys.** `[state] commit_timeout_ms = 5`, `quiescence_ms = 3` (placeholder; set from measurement), `max_part_skew_slots = 2`, `max_tip_lag_slots = 2`, `lag_slo_p50_ms = 16`, `lag_slo_p90_ms = 30`, `lag_slo_breach_minutes = 5`, `slo_action = "log"`, `slo_recover_minutes = 10`; `[alts] retry_ms = [50, 250, 1000, 5000]`, `retry_every_s = 30`, `give_up_s = 600`, `wait_cap = 10000`; `[accuracy] action = "log"`, `ring_versions = 8`, `queue = 10000`. Removed: `strategy.confirm_trigger_ms`, `strategy.decoded_sends`.

**Offline acceptance (CI).**
- **Store:** ordering by `(slot, write_version)`.
- **Commit groups:** completion, superseding, timeout and quiescence under the virtual clock. Route-level quiet. A late member marks `torn_suspect`.
- **Readiness skew rule:**
  - positive: a PumpSwap vault skewed by 3 slots is refused;
  - negative: an idle sell pool 500 slots old is not refused; a PumpSwap pool account 10,000 slots old with fresh vaults is not refused; a DLMM array outside the quote is not checked.
- **Forks:** an abandoned sibling fork with no `dead` status drops its versions and restores the canonical one; a `dead` slot does the same; slot-index `missing` evidence too. `fork_pending` applies while two siblings are both unconfirmed.
- **Accuracy:** scoring against the pre-state version; `pre_state_unknown` when the ring has evicted it.
- **Other units:** the lookup-table retry schedule and the warm-up gate.
- **No pricing on predictions:** a test inserts a shadow prediction and shows the quote is unchanged (`leg` never reads predictions).
- **Synthetic streams** (`testdata/grpc/`, WP-03) run through `forward` and `Engine::new_offline`: the S1, S1b and S8b sequences resolve as specified.
- **Scenarios** S1-S8, with S1b, S1b', S4b and S8b (WP-09), cover the catalogued loss kinds.

**Field acceptance (owner-run, 1 h shadow).**
- 0 decisions priced with any pending account, and no code path sends on a prediction (R §4 Stage 0 exit "0 sends priced on predictions").
- Reported: the share of groups by `w_src`, the lag by `w_src`, the `late_member` rate (target ≤ 0.1% of unknown-W groups), `torn_suspect` decisions, fork events and `fork_priced`, and the per-venue consistency-set skew.
- The lag SLO is computed every minute.
- Once WP-09 lands, a replay of the run reproduces its decisions.

**Measurement outputs.** `commits.jsonl`, `decisions.jsonl`, `predictions.jsonl` (all venues, pre-state scored), `alts.jsonl` events, `events.jsonl` (warm-up, fork, SLO), state-lag fields in status.

**Risk.**
- Pricing becomes more conservative and sends fall. That is intended: it removes phantom quotes.
- Route-level quiet and the commit timeout can delay real gaps by 3-5 ms. `commits.jsonl` lag and X2 measure the cost.

**Effort.** 4.5 d.

---

### WP-05 Send policy: bundle-only, fail-closed, in-flight by route and state, crowding rank

**Goal.**
- Bundle-only sending, with no RPC and no other network call on the send path.
- Recent blockhashes.
- An in-flight lock keyed by route and state version.
- The ≥1M band throttle and crowded pools ranked last.
- The full Jito verdict history (R §3.4, §3.6).

**Evidence.**
- W §2: the direct arm.
- res-code §3A: a stale simulation was sent on our quote.
- R §1: 0 of 1,869 bundles ≥1M landed; 1,020-1,027 attempts were lost to the 5/s limit; 49% of attempts went to crowded pools.
- R §3.4: 130 accepted-then-would-fail bundles never landed.
- W §8: missing verdicts.
- Review F23, F28, F43.

**Design.**
1. **Paths.** In live mode only `jito-bundle` may be enabled; `Config::load` refuses anything else.
   - Other `SendKind`s stay compiled, for `arbx senders` checks and a future direct experiment (`[send_policy] direct_experiment = false`; loading with `true` is refused in Stage 0).
   - Removed from exec.rs:
     - `fee_rule` and the fee arms (:231-235, :441-483);
     - the fields for tiers, compete, mix, rotate, test-all-paths, gross floor, bundle mix and the TPU arm (:153-183), with their config keys (config.rs `LiveCfg` :78-159);
     - the Jito gate (send/mod.rs:708-730, :841-861; `GateCfg` config.rs:541-554);
     - the sim gate (exec.rs:617-662);
     - resends and size variants (:561-576).
   - `copies` collapses to one bundle copy.
   - Canary mode becomes "live with the `[canary]` caps" (size ≤ 0.2 SOL). Built-to-fail canaries only made sense for direct paths, and they go.
2. **Fail closed.** No RPC call and no other network call between decision and fire. A send needs:
   - a blockhash from the WP-03b ring no older than `max_blockhash_age_slots` (20), else reason `blockhash_stale`;
   - the leader of the target slot (the slot after the current processed slot) from the LeaderBook. Kinds in `skip_leader_kinds` (default `other`, `unknown`) are skipped, with reasons `leader_skip_kind` / `leader_unknown` (R §3.6: non-Jito leaders are skipped);
   - a valid Jito auth token, already in hand (F28). `Jito::send_bundle` (send/jito.rs:304-307) today calls `self.token().await`, which may refresh over the network. Instead, a background task refreshes the token at half its lifetime, and the send path only reads the cached token. If it has expired, the reason is `jito_auth_stale`;
   - a healthy recorder, the SendGate in live, and `StoreHealth.ready`.

   These checks are one pure function, `exec::send_checks(&SendInputs) -> Result<(), Reason>`, called by `wants_send` and by replay (WP-09).
   - The exec RPC client drops the 3 s failover (rpc.rs:114) and the 429 backoff loop (:94), and uses WP-03b's `call_bounded`. Boot-time calls keep failover.
3. **Recent blockhash instead of a durable nonce.**
   - `build` (exec.rs:333-361) takes `Blockhash {hash, slot, height, src}`.
   - Nonce leasing (`NonceSlot` :93-94, the `nonces` in `Sending`, :544-545, :585, :741-743) leaves the bundle path; it stays only behind `direct_experiment`.
   - An attempt stays open until the block height passes `height + 150`, the blockhash's validity (about 40 s at the measured 3.72 slots/s). Then it becomes final.
   - `blockhash_commitment` (default `confirmed`) chooses which ring entry is used. Attempts record the blockhash age and source, so "Blockhash not found" verdicts can be related to them.
4. **In-flight lock keyed by (route, state version).** It replaces the pair lock (exec.rs:436; `pair_lock_ms` config.rs:118-120).
   - Key: (buy pool, sell pool, mint). Entry: state version, target slot, leader, attempt and time.
   - A new attempt on the key is allowed only if the state version or the leader differs. From Stage 1 it is also allowed at a new slot while the verifier confirms the gap.
   - An entry expires after `inflight_hold_slots` (2) or at the attempt's final verdict.
   - Reasons: `inflight_same_state`, `inflight_same_leader`.
5. **Rate, bands and crowding.** The Jito budget (send/budget.rs, 5/s) orders waiting sends by `Prio {band rank, crowding rank, EV}`.
   - **Bands** come from the single shared table in `src/bands.rs` (F22; the edges are in WP-06's `[bands]` and the same in decisions, the queue and tips).
   - **The ≥1M bands** are capped at `big_band_max_per_sec` (0.5) and rank behind every band under 1M (R §3.4).
   - **Crowding** (F6) = the number of distinct arbitrage-like signers that landed transactions on either pool in the last 6 h. It comes from an activity map fed by `record_rival` (engine.rs:272-312) and `exec.jsonl` `arb_like`, bucketed <20, 20-150, ≥150. Until the map holds 6 h of data, WP-00's static list stands in. Within a band, pools in the ≥150 bucket queue behind all others.
   - This replaces WP-00's bucket and the seed-pool rank (exec.rs:616).
   - A send that waits longer than `queue_ms` (10) is dropped, with reason `rate_queue_timeout`, or `crowded_pool` when its crowding rank put it behind.
   - When 4 or more sends are queued, the lowest queued EV is logged as λ, the shadow price of a send slot, for the Stage 2 Selector.
6. **Token cooling** (exec.rs:184-186, :718-734) stays, with reason `token_cooling` recorded. It is revisited after X2.
7. **Jito verdict history.**
   - `Verdicts.first` (send/jito.rs:228, :341) becomes `all: HashMap<bundle, Vec<(t_ns, Outcome)>>`, and `verdicts(sig)` returns the whole sequence.
   - `Outcome` (:152-159) gains the validator identity (`Accepted.validator_identity` :111, `Processed.validator_identity` :138) and keeps `bundle_index`.
   - Result-stream outages (`follow_results` :361-385) go to `events.jsonl`, so missing verdicts are explainable.
   - The per-copy overwrite and the zero-wait deadline (exec.rs:694-698, :696) are deleted, and outcomes carry the full sequence.
   - The latest keep-alive RTT is published in an atomic for WP-08 (`be_rtt_ms`).
8. **On-chain min_profit for bundles** = tip + base fee + priority (0) + margin, with margin = max(`margin_floor`, `margin_share` × expected net) (R §3.9). Rent is never part of it.
   - **Stage-0 defaults keep today's behaviour** (F23): `margin_floor = 1` and `margin_share = 0`. Today's on-chain floor for bundles is tip + base fee + priority + 1 (exec.rs:519).
   - R §3.9's 2,000 / 2% would have reverted 3 of the 23 historical wins: p1#59 (8,985 expected), p2#658 (10,751) and p7#63 (9,310). It is tested as a WP-11 arm or adopted by owner decision (OD-5).
9. **Settlement is stream-based.**
   - **Landed:** the signature appears in `wallet.jsonl` (WP-03b), and Jito `processed` is noted.
   - **Not landed:** the blockhash expires. Before that final state is written, one bounded `getSignatureStatuses` (with `searchTransactionHistory`) on `rt_bg` checks for a landing the wallet path missed (F43).
   - **Cross-checks:** `getSignatureStatuses` also runs at +2 s, +10 s and +60 s, each a single 500 ms `call_bounded`. It blocks nothing.
   - **Amends:** a landing found later (in this segment or the next one's wallet stream) writes an `outcomes.jsonl` line with `amend: true`.
   - The full money accounting is WP-07.
10. **`src/proglog.rs`** (new; F11). It takes `meaning` (exec.rs:211-227) and `delivered_from_logs` (build.rs:375-387) unchanged, plus a basic `proglog::events(logs) -> Vec<ProgEvent>` (NXV2LEG / NXV2OUT). WP-08 extends only this file.
11. **Attempts carry `leader: leaders.snapshot(target_slot)`** (WP-03 struct; WP-08 fills region, RTT and client without touching exec.rs).

**Config keys.** `[send] max_blockhash_age_slots = 20`, `blockhash_commitment = "confirmed"`, `queue_ms = 10`, `big_band_max_per_sec = 0.5`, `crowding_window_h = 6`, `crowding_buckets = [20, 150]`, `margin_floor = 1`, `margin_share = 0.0`, `inflight_hold_slots = 2`, `skip_leader_kinds = ["other", "unknown"]`; `[send_policy] direct_experiment = false`.

Removed:
- `[gate]`;
- the `[live]` keys `test_all_paths`, `max_priority_lamports`, `bid_*`, `spec_cu_price_micro`, `rotate_paths`, `race_mix`, `bundle_mix`, `tpu_*`, `pair_lock_ms`, `sim_gate`, `bundle_resend_ms`, `bundle_size_variants`, `compete_*`, `gross_floor`;
- `nonce_accounts` (kept under `[send_policy.direct]` for the experiment);
- `big_band_*` and `crowded_pools_file` (moved to `[send]`).

**Offline acceptance (CI).**
- `copies` yields exactly one bundle copy, and a live config with a non-bundle path enabled fails to load.
- **In-flight lock:** table-driven tests for same state, new state, new leader and expiry.
- **Queue order:** band ordering, the ≥1M cap and the crowding rank in `Budget`, under tokio's paused clock.
- **`send_checks`:** blockhash-age refusal, leader-kind skip, expired token.
- **Verdict history:** several fake results for one bundle are all kept, in order, with their times.
- **Network-call counter** (F28): every `Rpc` call and every Jito unary call except `SendBundle` increments a counter. A send reaches a fake path with the counter at 0. A token refresh in the background does not touch the counter on the send path.
- **Settlement:** expiry with a status-check hit becomes landed; a late landing writes an amend line.

**Field acceptance (owner-run, 24 h live on the Stage-0 config).**
- 0 non-bundle copies and 0 failed-landing fees.
- "Blockhash not found" in under 0.1% of verdicts, or the age and source analysis gives the threshold to use.
- Every accepted bundle has its verdict sequence whenever the result stream was up.

**Measurement outputs.**
- `attempts.jsonl` v2: blockhash with its age and source, band, crowding, queue wait, leader snapshot, in-flight key, state version.
- `copies.jsonl`.
- `bundles.jsonl`: every result, with the validator.
- `outcomes.jsonl` v2: the verdict sequence, accepted versus landed, and amends.
- Decision reasons.

**Risk.** Blockhash bundles may behave differently on BAM leaders; X5 measures it.

**Effort.** 3 d.

---

### WP-06 Builder: rent-neutral, measured CU, DLMM-safe, size-budgeted, tipped by band

**Goal.** Transactions that:
- cannot lock rent;
- ask for the CU they need;
- never run past the liquidity they name;
- fit in 1,232 bytes;
- tip by band (R §3.3, §3.5, §3.6).

**Evidence.**
- W §2: rent.
- res-pnl §2: rent residuals of 0 / −1,488,440 / −1,513,840 / −2,860,040, the last one with the PumpSwap user volume accumulator.
- W §1 and §7.4: 19 × 0x1794 and 5 CU exhaustions (756,015).
- D §4.5 and §4.10.
- R §3.5: copies reach 1,209 of 1,232 bytes.

**Design.**
1. **Instruction order** (`Exec::build` exec.rs:333-361; build.rs header :6-9):
   1. CU limit (the CU price is 0, so that instruction is omitted);
   2. SetLoadedAccountsDataSizeLimit;
   3. ATA create (idempotent, only if the mid mint is not held);
   4. the route;
   5. CloseAccount of that ATA to the payer (only if this transaction created it);
   6. the tip, a top-level System transfer, last.

   New in build.rs: `loaded_data_limit_ix(bytes)` (ComputeBudget instruction 4, u32) and `close_account_ix(account, destination, owner, token_program)` (token instruction 9; the same for Token-2022).
2. **Held set.** WSOL, USDC and USDT accounts are permanent, plus up to `held_max` (40) hot mints.
   - The set is refreshed from the wallet stream and the snapshots (WP-07), not only at boot (exec.rs:255-263).
   - A non-held mid mint gets create and close in the same transaction; a held one gets neither.
   - `max_new_token_accounts` (config.rs:69-71, exec.rs:437) goes. Trades are rent-neutral by construction, and the supervisor caps the rent locked in the held set (WP-07).
   - **The PumpSwap user volume accumulator** (build.rs:149, :155):
     - The first PumpSwap buy creates it, and we cannot close it (res-pnl §2: 1,346,200 lamports, owner pAMMBay6).
     - Its existence is checked at boot and followed on the state stream.
     - While it is absent, PumpSwap-buy routes are refused (reason `uva_missing`) unless `allow_uva_create = true`. Creating it once is an owner action.
     - The ledger expenses it as non-recoverable rent (WP-07).
3. **Mint filters.** `has_transfer_fee` (pools.rs:135-150) is extended to also drop mints with a TransferHook extension (type 14), at boot (pools.rs:115-119). Neither kind can be rent-neutral or quoted exactly.
4. **Measured CU limits** (F36). `CuTable` (`src/cu_table.rs`, `data/cu-table.json`) is built per leg, not only from our own transactions, which would starve the table because only wins land.
   - **Per-leg samples:** for every watched transaction in `exec.jsonl` (rivals included), the venue program's `Program <id> consumed X of Y compute units` log line at the swap's invoke depth gives one CU sample, keyed by (venue, bins-crossed bucket).
   - **Our route's limit** = (our program's overhead, measured from our own transactions' outer consumption minus their legs + Σ per-leg p99 + ATA create and close + tip) × 1.10.
   - **Fallback:** a cell with fewer than `cu_min_samples` (30) samples falls back to today's formula (`leg_cu` venues/mod.rs:35-44 + 29,000, engine.rs:827).
   - The formulas at engine.rs:709, :732 and :827 call `CuTable`. The `+ tag` CU hack (exec.rs:343) goes: there is only one copy now.
   - The toolkit's `cu-table` command builds the table.
5. **Fee estimate in `best_cycle`** (engine.rs:828; today 5,000 + cu_price × cu + min_tip, with `min_tip` from main.rs:579): base fee plus the tip policy's estimate. Bundles pay CU price 0.
6. **DLMM.**
   - **Liquidity cap.** The bin-array window the builder will name (≤ 5 arrays, build.rs:183-190) moves into a shared function. `dlmm::quote` (venues/dlmm.rs:124-168) takes the allowed arrays and fails with `ArrayNotLoaded` beyond them, so `best_cycle`'s size search caps the size. Decisions record `dlmm_cap_bound`.
   - **Bitmap extension per send.** The builder reads the extension PDA from the store (WP-03 follows it).
     - If the extension exists, it is passed (build.rs:191).
     - If a named array lies outside the internal bitmap's range and no extension exists, the route is refused (reason `dlmm_ext_needed`).
     - The boot-time check (pools.rs:120-124) goes.
7. **Size budget** (`MAX_TX_BYTES` 1,232, build.rs:35). After compiling, if the transaction is too large:
   1. add lookup tables from an `AltIndex` (every table seen in shred-decoded transactions, mapping address → (table, position); greedy cover of at most 4 tables);
   2. use a held ATA if the mint can join the held set;
   3. drop the route (reason `oversized`).

   Bytes, tables used and the fallback taken are recorded. Our own tables for hot pools are Stage 2A.
8. **Bands and tips** (`src/bands.rs`, `src/tip.rs`; F22).
   - **One band table** is used by decisions, the send queue and tips: `[bands] edges = [20000, 100000, 1000000, 10000000]`, over the expected **edge** = expected gross − base fee (before the tip), giving bands 0-4. Bands 3 and 4 form the ≥1M throttle class.
   - **Tip** = clamp(share(band, contested) × edge, floor 1,000, cap 100,000).
   - **Stage-0 shares** are 0.7 in every band, the status quo. This WP changes the mechanism, not the behaviour; X4 changes the numbers.
   - The tip also sets the on-chain min_profit (WP-05 item 8). It replaces `Path::tip`'s share logic (send/mod.rs:489-496) for bundles.
   - "Contested" stays false until the Stage 2A Selector supplies it.
9. **Payer-guard trailer.**
   - nexus v2 accepts an optional 8-byte `max_payer_lamport_drop` after the last leg (program/nexus-arb-v2 `encode_guarded`). `route_ix` (build.rs:205-222) appends it when `payer_guard = true`, with `payer_guard_max_drop` 0: once the user volume accumulator exists, no allowlisted leg of our 2-leg WSOL routes spends payer lamports.
   - It costs 8 bytes (R §3.9).
   - The flag ships `false`. It is switched on after X6 shows the routes still fit and a canary run shows no guard failures.

**Config keys.** `[bands] edges = [20000, 100000, 1000000, 10000000]`; `[builder] held_max = 40`, `allow_uva_create = false`, `loaded_data_limit = "auto"`, `cu_table = "data/cu-table.json"`, `cu_min_samples = 30`, `alt_index = true`, `max_alts = 4`, `payer_guard = false`, `payer_guard_max_drop = 0`; `[tips] shares = [0.7, 0.7, 0.7, 0.7, 0.7]`, `contested_shares = [0.16, 0.47, 0.54, 0.64, 0.64]`, `floor = 1000`, `cap = 100000`. Removed: `live.max_new_token_accounts`.

**Offline acceptance (CI).**
- Golden byte tests for the instruction order with and without create/close, and for the encodings of `close_account_ix` and `loaded_data_limit_ix`. The existing `legs_match_arbed` and `v2_data_layout` still pass.
- The guard trailer matches nexus v2's `encode_guarded` byte for byte (test vector copied from program/nexus-arb-v2 `logic`).
- **DLMM cap:** a quote stops at the last named array; the extension rule.
- **CU and bands:** `CuTable` per-leg aggregation from captured `consumed X of Y` logs (fixtures from `testdata/wallet/` and the synthetic exec stream), lookup and fallback; the shared band table; tip clamp tables.
- **Size:** the worst-case 2-leg routes from fixtures (PumpSwap buy + DLMM sell, with create and close) fit in 1,232 bytes.

**Field acceptance (owner-run).**
- X6 (WP-12) shows ≥ 99% of recorded attempts fit.
- In live, `rent_recoverable_now` stays flat except for deliberate held-set additions.
- Jito would-fail codes for CU exhaustion (ProgramFailedToComplete) and 0x1794 fall to 0.

**Measurement outputs.**
- In `attempts.jsonl`: the CU limit and its source (table cell or fallback), bytes, tables used, the fallback, creates and closes, tip band and share, and the guard.
- Decision reasons `dlmm_cap`, `dlmm_ext_needed`, `oversized`, `uva_missing`.
- `cu-table.json` carries its own provenance (source runs, sample counts).

**Risk.**
- CloseAccount fails if the mid balance is not exactly zero (rounding, fee-bearing mints).
- Fee mints are filtered. Any remaining failure makes the bundle would-fail, which is free, and shows up as token error code 11 (`NonNativeHasBalance`) in verdicts.

**Effort.** 3 d.

---

### WP-07 Ledger, reconciliation and campaign-wide supervisor stops

**Goal.** Money is accounted from the chain under one consistent equity definition and reconciled hourly. Equity-based stops work across segments (R §3.7, §3.8).

**Evidence.**
- res-stops §4: no loss stop; only a failed-fee budget.
- res-pnl §2-§4: true P&L against the counters.
- W §6 P6: unrecorded landings.
- R §3.7: `failed_fees_lamports` is a running total, and `profit_lamports` mixes in rent.
- Review F7 (contradictory definitions), F8 (stops cannot span segments) and F34 (snapshot slots).

**Design.**
1. **Equity definitions** (F7; formulas in MEASUREMENT.md §4.42-§4.44):
   - **Liquid equity** = native SOL + WSOL token amount.
   - **Total equity** = liquid equity + the value of other held tokens at the recorded mid + **recoverable rent** at face value. Recoverable rent is the lamports in accounts we can close: token accounts including the WSOL account, nonce accounts and lookup tables.
   - **Non-recoverable rent** (the PumpSwap user volume accumulator: 1,346,200) is never an asset. It is expensed in the transaction that creates it.
   - **Per transaction:**
     - `equity_delta` = the change of total equity. The categories that **sum** to it exactly are `trade_gross`, `tip`, `fee_win`, `fee_fail`, `fee_other`, `rent_nonrecoverable`, `transfer_in`, `transfer_out` and `other`.
     - **Informational fields,** outside the sum: `rent_locked` (liquid lamports moved into recoverable rent), `rent_reclaimed`, `liquid_delta` and `stranded`.
     - A create-only transaction therefore has `equity_delta = −fee` and `liquid_delta = −fee − rent`. A failed transaction has `−fee`. Creating the accumulator has `equity_delta` including `−1,346,200`.
   - The golden tests below pin these identities.
2. **Ledger** (`src/ledger.rs`, new). Entries are keyed by signature and built from:
   - `wallet.jsonl` (WP-03b: every landed transaction of ours, success or failure);
   - attempts (expected values, tip);
   - bundle results;
   - snapshots.
3. **Snapshots** run hourly (`snapshot_min` 60) and at start and stop, by bounded RPC on `rt_bg`.
   - **Calls:** `getBalance(wallet)`, `getTokenAccountsByOwner` for both token programs (jsonParsed, with each account's rent lamports), nonce accounts, our lookup tables, and the other owned accounts (the accumulator, flagged non-recoverable).
   - **One common slot** (F34): every call carries `minContextSlot` = the slot of the first answer. If the answers' context slots differ, the snapshot is retried up to 3 times. After that it is written with `slot_mismatch: true` and is not used for reconciliation (that is not a miss).
   - **Valuation:** USDC and USDT at the SOL/USDC mid from our pools' store state; other tokens at their best pool mid; unpriceable tokens at 0, flagged stranded.
4. **Reconciliation**, hourly and at stop, on both bases:
   - total: Δ`equity_total` between snapshots against Σ`equity_delta` + `inventory_reval`;
   - liquid: Δ`equity_liquid` against Σ`liquid_delta`.

   Each must be within `tolerance_lamports` (10,000).
   - A miss puts the SendGate in shadow (reason `reconcile_miss`) and writes `recon.jsonl` with the unexplained items.
   - Missing entries are searched with `getSignaturesForAddress(wallet)` over the window. That call is used only to find gaps in the ledger, never for land rates (D §4.13).
5. **Supervisor** (`src/supervisor.rs`, new, in-process). It acts through the SendGate (live / shadow(reason) / stopped(reason)), and each transition goes to `events.jsonl` and status.
   - **Campaign equity series** (F8): with `--campaign-dir` (WP-01), the supervisor loads at boot the `ledger.jsonl` and `snapshots.jsonl` of the campaign's earlier segments for the last 24 h, and continues the series with its own entries.
     - `drop_1h` = max(total equity over [t − 1 h, t]) − total equity at t.
     - `drop_24h` is the same over 24 h.
   - **Rules:**
     - `drop_1h` > 0.05 SOL: shadow for the rest of the segment. The supervisor starts later segments with `--shadow` until `drop_1h` is back under the limit.
     - `drop_24h` > 0.15 SOL: stop (exit 20), which ends the campaign (WP-01 supervisor).
     - Rent locked (recoverable) above 0.1 SOL: no held-set growth. Create and close stays allowed: it is rent-neutral.
     - Native SOL below 0.02: alert. The automatic unwrap of 0.05 WSOL runs only if `auto_unwrap = true`; it writes to the wallet, so it is an owner decision (R §6).
     - A stranded token held more than 60 s: alert. Automatic sale is Stage 2+.
     - A programdata change on a venue (WP-03): that venue's routes are refused (reason `venue_quarantine`) until the owner clears it.
     - Prediction accuracy: `accuracy_action = "log"` in Stage 0 (F5). The floor and window are set from WP-04's measured pre-state rate (OD-8) before any quarantine acts.
     - A core recorder drop (WP-02): shadow for the rest of the segment.
6. **Counters.**
   - The `Sending` money fields (exec.rs:99-129: `spent`, `fees`, `tips`, `profit`, `landed`, `wins`) leave the decision path.
   - Status shows ledger-derived `_total` and `_delta` values. `profit_lamports` (exec.rs:769-773, :790) is replaced by `trade_net` and the rent fields.
   - `Exec::on_settled` (:717-828) is rewritten around ledger entries, and `Exec::status` (:831-839) reports from the ledger. Outcomes get `prog_events` from `proglog::events` (WP-05).
7. **Finality and shutdown.**
   - **Final** means one of: the signature appears in the wallet stream; Jito reports `processed` and the wallet stream confirms it; the blockhash expires after WP-05's status check.
   - **On stop,** `--drain-s` (default 60; longer than a blockhash's validity of about 40 s) waits for open attempts, and any still open are listed in `stop.json` as unsettled.
   - **Later:** the next segment's ledger picks up late landings from its wallet stream, and the campaign-level reconciliation joins them to attempts by signature.
8. **Supervisor script.** `deploy/run-w.sh` takes the remaining budget and the rolling drops from `arbx campaign-equity --campaign-dir <dir>`, a subcommand that runs the same Rust code and prints JSON. It refuses to start a segment if `drop_24h` is over its limit.

**Config keys.** `[ledger] snapshot_min = 60`, `tolerance_lamports = 10000`, `mid_source = "pools"`, `snapshot_retries = 3`; `[supervisor] hour_drop_sol = 0.05`, `day_drop_sol = 0.15`, `rent_cap_sol = 0.1`, `native_floor_sol = 0.02`, `auto_unwrap = false`, `unwrap_sol = 0.05`, `stranded_s = 60`, `accuracy_action = "log"`, `accuracy_floor` (unset until OD-8), `accuracy_window = 200`; CLI `--drain-s`, `arbx campaign-equity`.

**Offline acceptance (CI).**
- **Golden ledger cases** (F7, fixtures from WP-00b `testdata/wallet/` and `testdata/legacy/expected.json`). Each case's categories sum to `equity_delta` exactly, and the rent fields match res-pnl to the lamport:
  - create only;
  - create and close;
  - accumulator creation (p6#69: `rent_nonrecoverable` 1,346,200 and `rent_locked` 1,513,840);
  - a failed transaction;
  - wrap and unwrap;
  - a bundle win with an ATA create (1,488,440 locked);
  - a Token-2022 create (1,513,840);
  - the bolt trade.
- **Reconciliation** with synthetic snapshot pairs, inside and outside tolerance, on both bases; a snapshot with `slot_mismatch`.
- **Campaign stops across two simulated segments** (F8): segment 2 boots with `--campaign-dir` holding segment 1's fake ledger. A drop split across the two segments fires the hour rule and then the day rule. The supervisor dry run refuses a third segment.
- Each stop rule against a fake ledger; drain logic under a virtual clock.

**Field acceptance (owner-run, Stage 0 exit).**
- 24 h of hourly reconciliations within 10k on both bases.
- Trade net on wins equals the chain to the lamport.
- A forced equity drop in a test run puts the bot in shadow, and the next segment starts in shadow.

**Measurement outputs.** `ledger.jsonl`, `snapshots.jsonl`, `recon.jsonl`, the money section of status (total, liquid, rent, campaign drops), drain fields in `stop.json`, gate changes in `events.jsonl`.

**Risk.**
- The valuation of stranded and USDC inventory is approximate (flagged in the record).
- The snapshot RPC load is small: a few calls an hour.

**Effort.** 3.5 d.

---

### WP-08 Telemetry: leaders, PoH, transfer classification, program-log decoders

**Goal.** Per-leader telemetry for every attempt, better PoH coverage, classified transfers and decoded program logs (R §3.6 "Per-leader telemetry from day one"; W §8 data gaps). Block-ordered context, which was here in revision 1, now comes from WP-03b's slot index and the toolkit (F10).

**Design.**
1. **Leader and validator metadata** (extends WP-03's `src/leaders.rs`):
   - **Sources:**
     - `getClusterNodes`: gossip IP, TPU-QUIC address, version → client family;
     - `getVoteAccounts`: stake;
     - the Jito and BAM sources named in WP-03, refreshed hourly with their source and time recorded;
     - region from the gossip IP, via an offline table (`data/ip-geo.csv`).
   - **RTT** (F40): a QUIC handshake (no data sent) to the TPU-QUIC address of the next leaders, at most 2 per second. This is labelled **host → leader TPU-QUIC RTT**: it is not the bundle's path, which runs block engine → leader.
   - **Block-engine RTT:** each attempt also carries `be_rtt_ms`, the latest keep-alive RTT to the block engine (published by WP-05).
   - **Outputs:** `leaders.jsonl` (per slot) and `validators.jsonl` (snapshots). The LeaderBook snapshot that attempts carry gains region, RTT, client and `be_rtt_ms`. send/tpu.rs `Book` (:39, :98-120) is replaced by the LeaderBook.
2. **PoH coverage.**
   - PoH recording is decoupled from exec (main.rs:493-495) and always on.
   - `poh.log` v2 adds the feed id and the entry index (feeds/mod.rs:171-179; feeds/shred.rs:247-266).
   - Shred feeds also write per-slot coverage to `slots-feed.log` (arb-lab's `slots.log`, v2): data sets decoded and failed, ticks seen, and whether the PoH clock covered the whole slot.
   - The toolkit merges positions across feeds for the best coverage.
   - **Gauge and target** (F38): the status gauge `poh_trigger_pct` is the share of attempts whose trigger has a PoH position. The target is ≥ 90% while at least one entries or shred feed is alive. Coverage depends on restoring the dead feeds, which is an owner action (OD-6).
3. **Transfer classification** (`src/classify.rs`, new). These are derived fields of `exec.jsonl` and `wallet.jsonl`, computed on the writer thread through the hook in `src/rec/exec.rs`.
   - **The full tip map:** `known_tip_accounts` (send/mod.rs:117-286), `OTHER_TIP_ACCOUNTS` (:63-115) and `data/sender-tip-accounts.json`, each account mapped to its sender.
   - **Kinds:**
     - `sender_tip`: a top-level System transfer to a tip account;
     - `cpi_tip`: an inner System transfer to a tip account, stack height > 1;
     - `wrap`: a transfer into the signer's WSOL account followed by SyncNative;
     - `unwrap`: CloseAccount of the signer's WSOL account;
     - `self`: between the signer and accounts it owns;
     - `venue_fee`: the PumpSwap protocol, creator and buyback recipients, from the same sources as build.rs:142-164;
     - `platform_fee`: wallets in `data/platform-fee-wallets.json`;
     - `rent_create`, `rent_close`, `other`.
   - **Jito bundle membership:** our bundles from `processed` results (slot, bundle index). Others are inferred from the tip plus block adjacency (`src = "heuristic"`) and refined offline by the explorer lookup (`src = "explorer"`).
4. **Program-log decoders** (extend WP-05's `src/proglog.rs`):
   - nexus v2 `NXV2LEG` and `NXV2OUT`: the failing leg is the last `NXV2LEG` without a matching `NXV2OUT`;
   - the arbx-exec `AXS1` summary record and events (WP-15);
   - venue error codes.

   The results flow into `outcomes.jsonl` `prog_events` through the WP-07 call site, and into `exec.jsonl` for our transactions.

**Files.** src/leaders.rs, src/classify.rs, src/proglog.rs (internals), feeds/shred.rs, feeds/entries.rs, feeds/mod.rs (PoH lines only), send/tpu.rs, src/rec/exec.rs (derived-field hook), main.rs (one wiring block), config.rs (`LeadersCfg` extended), `data/ip-geo.csv`, `data/platform-fee-wallets.json`, `data/validators-meta.json`. There is no `exec.rs` or `build.rs` change (F11).

**Config keys.** `[leaders] rtt_probe = true`, `rtt_per_sec = 2`, `geo_table`.

**Offline acceptance (CI).**
- Classification on real-transaction fixtures, with exact kinds and amounts: a Jito-tipped bundle transaction, a CPI-tip transaction, wrap and unwrap, and a PumpSwap buy with a creator fee (from `testdata/wallet/` and `tools/capture-fixtures.py`).
- Program-log decoding on captured logs, including a failure in leg 1 and an arbx-exec AXS1 record (from `program/arbx-exec` test vectors).
- Per-feed PoH from shreds (extends the shred tests); leader-kind resolution; RTT bookkeeping with a fake QUIC endpoint.

**Field acceptance (owner-run).**
- 100% of attempts carry the leader's identity and kind, or `unknown` with a reason.
- At least 95% have a host → leader RTT measured in the previous 10 minutes, or a region bucket marked as the fallback.
- `poh_trigger_pct` meets its target while a PoH-capable feed is alive.

**Measurement outputs.** `leaders.jsonl`, `validators.jsonl`, `poh.log` v2, `slots-feed.log` v2, classified transfers and bundle membership in `exec.jsonl`/`wallet.jsonl`, `prog_events` in outcomes, `be_rtt_ms` in attempts.

**Parallel.** After WP-03. The proglog part follows WP-05.

**Risk.** Some validators may rate-limit QUIC handshakes. RTT then falls back to the gossip-IP region bucket and is marked as such.

**Effort.** 2 d.

---

### WP-09 Replay harness and scenario tests

**Goal.** Deterministic replay of recorded runs, and tests that reproduce every catalogued kind of loss (R §4 Stage 0 "Recorder and replay"; R §2 graft 2). The journal writer itself is part of WP-03 (F11).

**Design.**
1. **`arbx replay --run <dir> [--from-slot N] [--to-slot M] [--config <frozen>] [--out <dir>] [--compare]`.** It rebuilds the store from `accounts.bin` (boot records first) and feeds the journal (WP-03) in order into `Engine::new_offline` (WP-02) through `Engine::step` and `Engine::timers`, with the replay clock (WP-04 item 11). Exec-side checks are evaluated with `exec::send_checks` (WP-05) on the journaled inputs. Nothing is built or sent.
   - **What `--compare` diffs** against the recorded `decisions.jsonl`:
     - engine-side fields: decision ids, routes, prices, nets, state versions, and the reasons of the state, pricing and policy stages;
     - the input-side reasons whose inputs are journaled (gate, blockhash, leader).
   - **Taken from the recording, not replayed:** the timing-dependent send-queue outcomes (`rate_queue_timeout`, `crowded_pool`, λ).
   - Differences go to `replay-diff.json`.
   - Journal gaps (replay-class drops) are reported, and the affected interval is skipped.
   - Recordings made before WP-03 cannot be replayed; the command says so.
2. **What-if modes:** `--reprice-sizes 0.5,0.25,0.125,opt` (X3), and `--set key=value` config overrides for offline policy tests.
3. **`arbx quote --run <dir> --route <buy,sell,mint> --version <aseq | slot:write_version | txn> --size <lamports>`** re-prices one route at one recorded state version. The toolkit's R4 and R8 (MEASUREMENT.md §6.4) call it.
4. **Scenario tests** (`src/scenarios/*.rs`, compiled under `#[cfg(test)]`). Fixtures use real account layouts, captured once from public RPC by `tools/capture-fixtures.py` into `testdata/scenarios/` (PumpSwap pool and vaults, DLMM pair and bin arrays, DAMM v2 pool, Raydium CPMM and AMM v4), then mutated synthetically.

   | # | Scenario | Expected result |
   |---|---|---|
   | S1 | Split-route torn read (AgmLJBMD pattern; p2#750, #1238, #1326, p9#12, p10#444, #596): one transaction writes pool A's vaults and pool B, with W(T) from a shred hint; the updates arrive interleaved and delayed | No evaluation until the group completes; the half-updated state is never priced |
   | S1b | The same transaction, not seen in shreds (W(T) unknown, F2): the updates arrive within `quiescence_ms` | Resolved by quiescence, with no route evaluated until both pools are quiet |
   | S1b' | As S1b, but with a member that arrives late | `late_member` is counted and the decision is marked `torn_suspect` |
   | S2 | Stacked failed sells (p6#364, p11#132, w5h3-p2#662-#704): many decoded swaps fail on chain, with no account writes | No decision at all |
   | S3 | Failed rival arbitrage (DreMAMRc>AwmaWjsR, 54 of 96 failures in w5h3-p2): a decoded rival arbitrage fails | No gap |
   | S4 | PumpSwap consistency set: a vault 3 slots older than the other vault | Reason `parts_skewed` |
   | S4b | A PumpSwap pool account 10,000 slots old with fresh vaults, and an idle sell pool 500 slots old (F3) | Priced normally |
   | S5 | The bolt trade (w5h2-p5#648): an inconsistent snapshot looked profitable; on the committed state the route loses (≈103M at that size) | No send |
   | S6 | Lookup tables: a table missing at first, then fetched by retry; and a table that never resolves | The first transaction is processed; for the second, the hint is dropped with a counted reason |
   | S7 | Warm-up | No send before every Tier-A pool is complete and the lag is within 2 slots |
   | S8 | Fork: a dead slot | Its versions are dropped and a refetch is triggered |
   | S8b | An abandoned sibling fork with no `dead` status (F4) | Its versions are dropped when the other branch is confirmed; routes priced on it are counted `fork_priced` |
   | S9 | In-flight (after WP-05) | Same state blocked; new state allowed; new leader allowed |
   | S10 | Rent neutrality (after WP-06) | A non-held mid mint gets create and close; a held one gets neither |
   | S11 | Bands and crowding (after WP-05) | ≥1M is throttled and ordered behind smaller bands; crowded pools are ordered behind others in a band |
   | S12 | A decoded-only trigger | Never produces a send |
   | S13 | A verdict sequence accepted → would-fail | Recorded in full |
   | S14 | Ledger categories on real transactions | Shared with WP-07's golden tests |
   | S15 | Status counters | `_total` is monotonic, and the `_delta` values sum to it |
   | S16 | Mispricing not explained by phantoms (F42), see below | The expected quote |

   S16 covers two cases:
   - **w5h3-p2#664** (11.7% high): CP-family pool state rebuilt from the landed transaction's pre-token balances (from public RPC) and the current pool config, with the expected quote.
   - **p10#156** (DLMM leg 1.26% high): best effort. Historical bin arrays are not retrievable from RPC. If the state cannot be rebuilt, the case stays a documented open item, and the first Stage-0 recording with a ≥ 1% mispricing in `accounts.bin` becomes the fixture.
5. **Real-data regression:** once Stage-0 recordings exist, a 10-minute slice (compressed, under 20 MB) is checked into `testdata/replay/` with its expected decisions.

**Offline acceptance (CI).** All scenarios run in `cargo test`. A synthetic 10-minute journal and account stream (generated) replays to identical decisions and runs at least 20× faster than real time.

**Field acceptance (owner-run).** Replay of a 1 h Stage-0 shadow recording made after WP-03 reproduces 100% of the compared fields, and runs at least 20× faster than real time.

**Depends.** WP-04 (and WP-03's journal); S9-S11 after WP-05 and WP-06. **Parallel** with WP-05 to WP-08: new files plus two `main.rs` arms (`Cmd::Replay`, `Cmd::Quote`), using only the public APIs listed in §3.2.

**Effort.** 3 d.

---

### WP-10 Analysis toolkit (`tools/arbx-report`)

**Goal.** Reports regenerated from the recorded files alone and computed correctly (counter semantics, block-order attribution, landed-only caveats), per segment and per campaign. The design is MEASUREMENT.md §6.

**Design summary.**
- **Package:** Python 3, standard library only (`zstandard` if installed, else `zstd -dc`). Readers check each file's schema version.
- **Reports:** per segment and per campaign.
- **Chain fetches** take the RPC URL from a named environment variable (`--rpc-url-env`), never from `.env` files, and cache results in the segment's `chain-cache/`.
- **Commands:** `segment`, `campaign`, `ledger`, `attempts`, `blockctx`, `attribution`, `latency`, `leaders`, `feeds`, `predictions`, `rivals`, `experiments` (x2, x4, x5, x8), `census` (x1), `cu-table`, `quality`, `compare`.
- **`blockctx`** (F10): per attempt, from `accounts.bin`, `slotidx.jsonl` and `exec.jsonl`, over the window [trigger slot, max(landed slot, last verdict slot, trigger slot + 4)] + 1.
  - Slots are deduplicated across attempts.
  - Gaps can be filled with a rate-limited full `getBlock` through `chain.py`.
- **R8 accuracy over every successful swap** (aggregator-routed ones included, decoded from `exec.jsonl` inner instructions) scores each swap against `arbx quote` at the pre-state version. It includes R §3.3's closer check: the closer's realised take against our quote at the version just before it.
- **Legacy readers** for arb-lab's v1 files let old runs be compared. `tools/analysis/` was removed from arbx on 2026-10-04 (I-11: arbx is standalone); it is in git history.

**Offline acceptance (CI).**
- Unit tests on synthetic streams:
  - summing `_delta` against taking the last `_total`;
  - attribution on a synthetic block;
  - `blockctx` windows and deduplication;
  - land rate from attempts only;
  - the "missing is not zero" rule.
- A known-answer test with the legacy reader on the WP-00b fixtures (`testdata/legacy/`) recomputes res-pnl's p1-p10 decomposition: trading net −2,337,448 and rent 16,383,000.
- The golden `report.json` for a synthetic segment is byte-identical on re-run.

**Field acceptance (owner-run).** `segment` on a Stage-0 run:
- regenerates every report from the files alone;
- gives identical output when re-run;
- has a money section that agrees with the ledger's reconciliation within 10k.

**Depends.** MEASUREMENT.md and WP-00b. The R4, R8 (all swaps) and X3 parts depend on WP-09's `arbx quote` and `arbx replay` (F35).

**Parallel.** Fully: it touches only `tools/arbx-report/`. It starts from MEASUREMENT.md and is validated on real output after WP-03 and WP-03b.

**Effort.** 4.5 d.

---

## 5. Stage 1: experiments as engine features and flags

R §5 lists the experiments. Each one below is a feature with a flag, a recorded arm and a report. The bot keeps running bundle-only throughout (R §4 Stage 1).

### WP-11 Experiment framework; X2 delay, X4 tip share, the margin arm; assignment for X5 and X8

**Design.**
- **`src/experiments.rs`** (new):
  - `[experiments] seed = <u64>`, and one table per experiment: `enabled`, `arms`, `weights`, a scope filter (bands, trigger kinds, venues), and the unit (the decision).
  - The arm is `hash(seed, experiment, decision id)`, so assignment is deterministic and replayable.
  - The arm goes into `decisions.jsonl` and `attempts.jsonl`. Configuration and block switches go into `experiments.jsonl`.
- **X2 delay test.**
  - Config: `[experiments.x2] arms_ms = [0, 5, 10, 20]`.
  - The delay is applied on the send task (a tokio sleep before fire), never on the engine thread, and only to state-trigger bundles.
  - At least 400 attempts per arm, about 1 h at ~2,090 bundle attempts/h.
  - Metrics: would-fail, accepted and landed, by delay and band.
  - Go: would-fail falls by at least 5 points per 10 ms of delay removed (one-sided p < 0.05). No-go: no latency spending.
- **X4 tip share.**
  - Config: `[experiments.x4] arms = [0.7, 0.35]`, scope: bands under 100k. A hook in `tip.rs`.
  - Metrics: land rate and net per attempt.
  - Go: if the land rate drops less than 20% relative, adopt 0.35.
- **Margin arm** (F23, OD-5).
  - Config: `[experiments.margin] arms = [1, 2000]` (`margin_floor`), scope: all bands.
  - Metrics: land rate and net per attempt.
  - It decides whether R §3.9's floor costs wins.
- **X5 BAM landing** has no live arm.
  - Its telemetry comes from WP-08 and the bundle results' validator identity.
  - The toolkit compares accepted → landed by leader kind over at least 200 eligible attempts, and compares arb-lab's nonce era with arbx's blockhash era.
  - Go: BAM lands at ≥ 50% of the Jito rate.
- **X8 Haan isolation.**
  - It assigns 10-minute blocks with the discovery connection (WP-14) on or off and records the block switches.
  - Go: Tier-A lag p50 rises ≤ 1 ms and p90 ≤ 5 ms, with no 429s on the Tier-A connection.

**Files.** src/experiments.rs; exec.rs (the spawned send task: today `Exec::send` :622-701, after WP-05 the single fire call); src/tip.rs (arm hook); config.rs (`ExperimentsCfg`); engine.rs decision records (arm field).

**Config keys.** `[experiments] seed`; `[experiments.x2] enabled, arms_ms, weights, scope`; `[experiments.x4] enabled, arms, scope_max_band`; `[experiments.margin] enabled, arms`; `[experiments.x8] enabled, block_min = 10`.

**Offline acceptance (CI).**
- Assignment is deterministic and balanced (chi-square on 10^5 synthetic ids).
- The delay is applied on the send task: WP-02's engine benchmark is unchanged.
- Arms are recorded in decisions and attempts, and replay reproduces the same arms.

**Field acceptance (owner-run).** One hour of X2 yields ≥ 400 attempts per arm with balanced bands, and `arbx-report experiments x2` produces the trend test.

**Measurement outputs.** `experiments.jsonl`; arm fields in `decisions.jsonl` and `attempts.jsonl`; report R10.

**Risk.**
- Delays cost a little landing on the delayed arms. That is bounded: at most 20 ms, only on bundles that miss for free.
- X4's low arm may land less (measured, and bounded to the <100k bands).

**Depends.** WP-07.

**Effort.** 2 d.

### WP-12 Offline experiments: X1 census, X3 smaller sizes, X6 size fit

**X1 offline census** (`arbx-report census`).
- **Inputs:**
  - Stage-0 recordings: `exec.jsonl` for all venues, `accounts.bin` versions, `decisions.jsonl` route ages, `slotidx.jsonl`, and the toolkit's `blockctx`;
  - a rate-limited chain sweep of rivals' successful arbitrage on our hot tokens.
- **Per gap:**
  - gross, size and route class;
  - route-wide gap age;
  - the winner's rung by block index relative to the opener: 0 same bundle, 1 index + 1, 2 index + 2-5, 3 same slot later, 4 next slot, 5 later (rival-synthesis §5);
  - the leader kind.
- **Capturable** means: size ≤ 4.2 SOL, age ≥ 354 ms, the winner is not rung 0-1, and the venue is supported.
- **Output:** capturable SOL/h, with medians and the top-1 share beside the means.
- Go: ≥ max(0.5 SOL/h, B/0.15). No-go: under 0.2 SOL/h.

**X3 replay at smaller sizes** (`arbx replay --reprice-sizes` on would-fail attempts, at their recorded post-trigger state version).
- Sizes tried: s/2, s/4, s/8 and the optimum.
- Go: ≥ 30% are profitable at a smaller size, with summed net ≥ 0.05 SOL/h within 4.2 SOL.

**X6 size fit** (`arbx sizefit --runs <dirs>`, `src/offline.rs`).
- It recompiles each recorded attempt with the Stage-0 instruction set (create + close, loaded-data limit, guard trailer, recent blockhash, no nonce) and reports the byte distribution and the share within 1,232.
- For arb-lab v1 attempts, the pool accounts come from current chain state, because historical account data is not retrievable; the report says so.
- Go: ≥ 99% fit. No-go: held ATAs for the affected mints.

**Files.** `src/offline.rs` (new: `sizefit` and the replay reprice driver over `src/replay.rs`), main.rs (`Cmd::Sizefit`), `tools/arbx-report/arbx_report/reports/` (census, sizes, sizefit). No change to the live path.

**Config keys.** None in the bot. The toolkit takes `--break-even-sol-h B`, `--cap-sol 4.2` and `--min-age-ms 354`.

**Offline acceptance (CI).**
- Census on a synthetic segment with known gaps (ages, rungs, sizes) reproduces the expected capturable sum.
- Reprice on a fixture route gives the closed-form CPMM optimum.
- Sizefit on fixture attempts reproduces WP-06's byte counts.

**Field acceptance (owner-run).** Each tool runs on a 24 h Stage-0 campaign in under an hour and writes its go/no-go line with the inputs' coverage.

**Measurement outputs.** Report R11 sections; `sizefit.json`, `reprice.jsonl` and `census.json` under `report/`.

**Risk.** X1's chain sweep is rate-limited and sampled, and the report states the sampling. X6 on arb-lab data uses current pool accounts (stated).

**Depends.** WP-09, WP-10, WP-06.

**Effort.** 3 d.

### WP-13 Verifier sidecar (X9) and measured CU

**Design.**
- **A separate crate** `verifier/`, so the Agave and LiteSVM dependencies stay out of the latency-critical binary (R §3.3). It uses LiteSVM 0.17, the version program/arbx-exec already uses in its tests.
- **What it does:** it loads the venue programs and our route program from their programdata, fetched at boot and re-fetched when a programdata account changes. It runs our exact signed transaction on a given account state and returns:
  - success or failure;
  - the change in total equity over the whole transaction (WP-07 definition; fees, tip and rent included);
  - CU used;
  - logs.
- **Modes:**
  - `offline`: X9 latency p50 and p99 for 2-leg and 3-leg routes, feeding the CU table, exact checks for X3;
  - `shadow`: live, beside sends, results in `verify.jsonl`, no gating;
  - `gate`: Stage 2A, persistent candidates only.
- **The arbx side** is `src/verify_client.rs`: a non-blocking Unix-socket client with timeouts, on `rt_bg`. It is never on the hot path in Stage 1.
- **Consistency monitor:** verifier results against landed outcomes (CU, delivered amounts) give an accuracy figure. Feature gates or venue upgrades that make the SVM differ from the chain show up there (R §7).
- **X9 go:** p99 ≤ 3 ms, which allows reactive use. Otherwise it is used for persistent gaps only.

**Config keys.** `[verifier] mode = "off" | "offline" | "shadow" | "gate"`, `socket`, `timeout_ms = 5`, `programs_refresh = "on_change"`.

**Offline acceptance (CI).**
- The verifier reproduces captured landed transactions (wins and failures from `testdata/wallet/`) to the lamport and the CU.
- A programdata change triggers a reload.
- The client times out without blocking the engine.

**Field acceptance (owner-run).** Offline over a Stage-0 day: ≥ 99% agreement with chain outcomes on landed transactions, and X9 latency figures per route class.

**Measurement outputs.** `verify.jsonl`; CU samples for `cu-table`; report R8/R10 sections.

**Risk.** The SVM can differ from the chain (feature gates, clock-dependent fees). The consistency monitor quantifies it, and quarantine applies (R §7).

**Depends.** WP-03 (inputs), WP-06 (builder output). **Parallel:** separate crate.

**Effort.** 8-12 d.

### WP-14 Discovery connection (X8)

**Design.** A second gRPC connection (or provider) carrying owner-filtered program-account streams, the future Tier B/C prefilter (R §4 Stage 2A). In Stage 1 it only records (`discovery.jsonl` counts and lag), so X8 can measure its effect on Tier-A lag. If OD-1 buys a second provider, the same connection can carry the transaction filter for the non-PumpSwap venues.

**Files.** `src/feeds/discovery.rs` (new), main.rs (one wiring block), config.rs.

**Config keys.** `[discovery] enabled, url, token_env, owners, connection = "separate"`.

**Offline acceptance (CI).** Request encoding (owner filters) and the on/off block switch.

**Field acceptance (owner-run).** X8 blocks run for 24 h, with each arm ≥ 10 blocks.

**Measurement outputs.** `discovery.jsonl`; Tier-A lag in `commits.jsonl` and status, per block.

**Risk.** A shared provider may rate-limit Tier A when discovery is on. That is exactly what X8 detects, and the gate then turns discovery off.

**Depends.** WP-03.

**Effort.** 2 d.

### WP-15 arbx-exec integration behind a flag (and the X7 plan)

**State of the program** (F41). `program/arbx-exec` (crate `arbx-exec` 0.3.0, a new program with its own id) already holds both layouts in `src/lib.rs`:
- **v2:** nexus-arb-v2's layout, parsed identically. Execution differs in three account-structure checks (code `0x4E580009`), and every route also logs one `AXS1` summary record (about 130 log bytes and ~200 CU).
- **v3:** a flags byte, a mandatory payer-guard field, an optional CPI-tip block, and 5-byte leg metas.

arbx integrates it without making it the default:
1. **Single source of encoding.** arbx depends on the program's host-side `logic` module (no `onchain` feature), so the builder and the program cannot disagree. If the crate's `["cdylib", "lib"]` type causes build friction as a dependency, the program side should split `logic` into a tiny `arbx-exec-logic` crate used by both. That is a request to the program's author, not a change made here.
2. **Builder** `src/build_arbx.rs` (new): the v3 layout of R §3.9, using the logic crate's encoder. The layout holds:
   - version 3, flags, `n_legs`, `amount_in`, `min_profit`;
   - the payer-guard and optional CPI-tip fields;
   - 5-byte per-leg metas, and the leg data.

   The legs themselves (`build::leg` build.rs:84-129) are shared with the v2 path; only `route_ix` (build.rs:205-222) has a v3 twin.
   - `Exec::build` (exec.rs:333-361) dispatches on `[exec] route_program`. `ExecCfg.program` (config.rs:186-187) keeps naming the v2 program.
   - `build::ERR_PROFIT` (build.rs:38) and the error table in `proglog.rs` (WP-05) gain the arbx-exec codes.
3. **min_profit rules** (R §3.9):
   - with a top-level tip: tip + base fee + priority + margin;
   - with a CPI tip: base fee + margin;
   - rent is never included.
4. **Logs and errors.** `proglog.rs` decodes arbx-exec's structured events, the AXS1 record and the error codes (taken from the logic crate's constants) into `prog_events`.
5. **Provenance gate.** At boot, the programdata ELF hash (WP-01 procedure) must equal `arbx_exec_expected_sha256`. Otherwise arbx-exec is not used: the bot falls back to nexus-v2 if `fallback = true`, else it does not send (reason `program_hash_mismatch`).
6. **Tests:**
   - golden encode vectors, checked by the program's own `parse`;
   - LiteSVM runs in the verifier crate on captured accounts, comparing nexus-v2 and arbx-exec on the same route (same delivered amounts, CU within budget);
   - a size regression with X6 on the v3 encoding.
7. **Rollout:** shadow (build plus verifier only), then canary (tiny bundles, guard on), then live behind the flag. Rollback is a config switch to `nexus-v2`; v3 keeps the v2 parser (R §3.9).
8. **X7 CPI tip** (R §5, Stage 2B or 3): `arbx_exec_flags.cpi_tip = true` on 5 tiny bundles across Jito and BAM leaders, run by the owner. Go: all land and the tip counts in the auction. Otherwise keep top-level tips.

**Config keys.** `[exec] route_program = "nexus-v2" | "arbx-exec"`, `arbx_exec_program`, `arbx_exec_expected_sha256`, `fallback = true`; `[exec.arbx_exec_flags] payer_guard = true, count_lamports = false, cpi_tip = false, self_size = false, basket = false, noop_on_miss = false`.

**Offline acceptance (CI).** Golden vectors and the LiteSVM comparisons pass.

**Field acceptance (owner-run).**
- A shadow day builds arbx-exec transactions for every attempt, with sizes within budget.
- The canary lands with decoded `prog_events`.
- Switching `route_program` back to `nexus-v2` needs a restart of the segment only.

**Measurement outputs.** The `meta.json` programs entry for arbx-exec (hash, deploy slot); `attempts.tx.program` (`kind`, `layout`); `outcomes.prog_events` with arbx-exec events; `verify.jsonl` comparisons.

**Risk.** The program interface is still moving. The flag defaults to `nexus-v2`, and the logic crate's golden vectors catch drift. A deployment that differs from the reviewed build is refused by the hash gate.

**Depends.** WP-06, WP-08 (proglog), WP-13 (LiteSVM harness).

**Effort.** 3-4 d on the arbx side. Deploying the program is the owner's action.

---

## 6. Exit gates

### Stage 0 exit (R §4, plus the measurement requirement)

| Gate | Check |
|---|---|
| Bundle-only, no failure fees | 24 h live: 0 non-bundle copies and 0 failed-landing fees in the ledger |
| Money reconciles | Hourly reconciliation within 10k lamports for 24 h, on the total and the liquid basis |
| No prediction pricing | No code path prices on predictions (WP-04 test); 0 decisions with a pending account; `torn_suspect` sends ≤ 0.1% of sends |
| Rent | `rent_recoverable_now` does not grow beyond the held-set cap; non-recoverable rent appears only with an owner-approved accumulator creation |
| Scenarios | S1-S16 (with S1b, S1b', S4b and S8b) pass in `cargo test` |
| Replay | A 1 h run recorded after WP-03 replays to identical compared fields |
| Telemetry populated | 100% of attempts have the leader's identity and kind, the verdict sequence (while the result stream was up), the state version, the blockhash age and source, and state-path stage timestamps. ≥ 95% have a host → leader RTT and a complete toolkit `blockctx` within 10 minutes of becoming final. `poh_trigger_pct` ≥ 90% while a PoH-capable feed is alive |
| Recording | Core and replay-class streams (`accounts`, `journal`): 0 drops. Other chain streams < 0.01%. Bulk < 0.1% |
| Exec coverage (F1) | ≥ 99% of the known denominator (signatures that wrote a watched account, plus shred-seen watched transactions that the slot index shows landed) have a full `exec.jsonl` record with `idx` within 10 minutes, on every venue. The sampled unseen share is < 1%. There is no escape clause: if the capacity of OD-1 is not in place, this gate is not met, and Stage 0 exits only with an explicit owner waiver written into §9 |
| Wallet | `wallet.jsonl` matches `getSignaturesForAddress` 100% |
| Provenance | Every segment has meta (build, config and program hashes) and a stop reason; `probe.json` is recorded |
| Reports | `arbx-report segment` regenerates every report from the files; deterministic |

- **Metrics tracked during Stage 0** (R §4): would-fail rate by band, by crowding bucket and by send delay; accepted → landed by leader kind; wins/h; net/h.
- **Kill or rollback:** a reconciliation miss, or a total-equity drop of more than 0.05 SOL within a rolling hour (campaign-wide), puts the bot in shadow (automatic, WP-07).

### Stage 1 exit (R §4)

A decision memo with each experiment's go or no-go (X1-X9 and the margin arm), produced by `arbx-report experiments` and `census`. Kill: X1's capturable gross under 0.2 SOL/h and both X2 and X3 failing stop work on new capability.

---

## 7. Config migration summary

| Change | Keys |
|---|---|
| Added (WP-00, temporary) | `strategy.decoded_sends`, `live.big_band_*`, `live.crowded_pools_file` |
| Added (WP-01) | `config_version`, `[exec] expected_program_md5/sha256`, `[control]` |
| Added (WP-02) | `[record] disk_budget_gb, min_free_gb, rotate_mb, rotate_min, flush_ms, zstd_level, archive_feeds, queue_*, accounts_keyframe_every`; `[runtime] bg_threads` |
| Added (WP-03) | `[state] watch_*, slot_statuses, block_meta`, `[[state.tx_stream]]`, `[leaders]` |
| Added (WP-03b) | `[chainfetch]`, `[[chainfetch.provider]]` |
| Added (WP-04) | `[state] commit_timeout_ms, quiescence_ms, max_part_skew_slots, max_tip_lag_slots, lag_slo_*, slo_action, slo_recover_minutes`, `[alts]`, `[accuracy]` |
| Added (WP-05) | `[send]`, `[send_policy]` |
| Added (WP-06) | `[bands]`, `[builder]`, `[tips]` |
| Added (WP-07) | `[ledger]`, `[supervisor]` |
| Added (WP-08) | `[leaders]` extensions |
| Added (Stage 1) | `[experiments]`, `[verifier]`, `[discovery]`, `[exec] route_program, arbx_exec_*` |
| Removed | `record.enabled`, `record.archive_feed`, `strategy.confirm_trigger_ms`, `strategy.decoded_sends` (WP-04), `[gate]`, the `[live]` direct-arm keys (see WP-05), `live.max_new_token_accounts`, `live.nonce_accounts` (moved under `[send_policy.direct]`), `live.big_band_*` and `live.crowded_pools_file` (moved to `[send]`) |

`deny_unknown_fields` makes every removed key a load error, so old configs cannot run with silently ignored settings. Each WP updates `deploy/arbx-stage0.toml` and `deploy/arb.toml`. `deploy/legacy/arb-w-live.toml` stays as the arb-lab record and is never parsed by arbx (F19).

---

## 8. Plan-level risks

| Risk | Mitigation |
|---|---|
| Provider limits (one gRPC transaction filter with one account on Haan; RPC rate limits) leave non-PumpSwap exec coverage short | The PumpSwap filter keeps arb-lab parity. Wallet transactions come from account updates, independent of filters. The backfill is sized from the measured rate, the needed rps is printed, and the exec gate is firm: buying capacity is OD-1. Reports state coverage and never treat missing as zero |
| `blocks_meta` or interslot slots not offered | `arbx grpc-probe` before WP-05; four blockhash sources; the slot index gives height and parent |
| Recording or RPC load slows trading | Bounded queues; writer threads off the engine core; no producer-side formatting; RPC and large JSON on `rt_bg`; WP-02's isolation test and benchmark |
| Disk fills on Cherry | Disk budget with an action ladder; in-process compression; manifest; the supervisor refuses a segment under `min_free_gb` |
| Commit groups and route-level quiet delay real gaps | Timeouts are configurable and measured (`commits.jsonl` lag by `w_src`); X2 quantifies the cost of delay |
| Unknown W(T) still allows rare torn reads | `quiescence_ms` from the measured intra-transaction spread; `late_member` and `torn_suspect` measured; a torn send that lands is still profit-checked on chain |
| Fork handling relies on confirmed slots arriving | Dead slots and slot-index `missing` are extra evidence; `fork_priced` measured; bundles priced on abandoned state fail for free |
| Blockhash bundles land differently on BAM | X5 before/after comparison; leader-kind telemetry |
| CloseAccount or the guard trailer makes valid bundles fail | Failing bundles cost nothing; would-fail codes are recorded; canary before default |
| Stage 0 grows (about 36 days against R's 9-13) | Lanes A, C, B1-B3 in parallel; WP-00 already removes the losses on day 0; Stage 1 measurements can start on WP-07 output |
| arbx-exec interface changes while being built | Depend on its `logic` crate; golden vectors in both repos; the flag defaults to nexus-v2 |
| Field acceptance waits on the owner | Every WP has an offline part that gates the merge; field results are batched into the owner's Stage-0 runs |

---

## 9. Decisions for the owner

| # | Decision | Options | What the plan does until decided | Needed by |
|---|---|---|---|---|
| OD-1 | **Exec coverage capacity** (F1) for the non-PumpSwap venues | (a) A Haan plan with a transaction filter of ≥ 5 accounts (the 5 venue programs): no RPC needed. (b) A Yellowstone `blocks` filter with `account_include`, if the probe shows it is offered. (c) A second Yellowstone provider with one transaction filter on the 4 non-PumpSwap venue programs (can share WP-14's connection). (d) RPC capacity of about 20-50 getTransaction/s on the w5h registry, 2-3× that for about 1,000 pools, plus about 3.7 getBlock(signatures)/s. (e) A written waiver: Stage 0 exits with the measured partial coverage | PumpSwap via the stream, wallet complete, other venues backfilled at the provider cap with `need_rps` printed | Before the Stage-0 exit; numbers from WP-03b's first field run |
| OD-2 | **Probe results** (F14) | If `blocks_meta` is refused, nothing is needed (fallbacks). If the accounts filter refuses the full list, Tier A must shrink or the plan must change | — | Before WP-05 |
| OD-3 | **Crowded pools** (F6) | Rank last in the Jito queue (default), or exclude ≥150-bot pools from bands of 100k and above | Rank last | WP-00 |
| OD-4 | **Stage-0 trade size and seed list** (F37) | The live value 4.2 SOL (shipped), or R §3.8's ladder 0.2 → 1 → 4.2 SOL as gates pass. Also confirm the seed CSV (`seed-pools-w4.csv` from Cherry or another listed file) | 4.2 SOL, recorded in `meta.limits` | WP-00 |
| OD-5 | **On-chain margin floor** (F23) | 1 (status quo) or R §3.9's 2,000 / 2% | 1; the WP-11 margin arm measures it | WP-11 |
| OD-6 | **Dead feeds** (F38) | Fix or drop the 5 dead feeds (R §6) | PoH coverage and W(T) hints depend on them; the gauges show it | Stage 0 |
| OD-7 | **Supervisor passphrase hardening** (F31) | Keep the bash supervisor (residual risk documented in WP-01), or build an `arbx campaign` launcher (about 1 d) | Bash supervisor | Stage 1 |
| OD-8 | **Accuracy quarantine** (F5) | The floor and window, set after WP-04 measures the pre-state exact-match rate | Log only | Before any quarantine acts |
| OD-9 | **SLO action** (F32) | `log` (Stage 0 default) or `shadow` with automatic recovery | Log | After a week of SLO data |
| OD-10 | Existing R §6 decisions | `auto_unwrap`, `allow_uva_create` (creating the accumulator expenses 1,346,200), capital, Jito key or limit, break-even B, and a daily copy-off of finished segments | Off / not created | As in R §6 |

---

## Appendix A. Measurement requirement → WP → stream

| Requirement (owner) | WP | Stream(s) (MEASUREMENT.md) |
|---|---|---|
| Always on, at least arb-lab's set (meta, status, txarr, rivals, exec, moves, slots, poh, entries, alts, caps, opportunities, triggers, arrivals, predictions, sims, attempts, copies, outcomes, bundles, keepalive, run logs) | WP-00, WP-02 | every stream in MEASUREMENT.md §4; the segment `.out` kept |
| Execution results for every tx touching any watched account, every venue, with block index, fee, priority, CU, pre/post SOL and token balances, inner instructions, logs, loaded addresses, version, compute-budget params | WP-03 (PumpSwap stream), WP-03b (backfill, slot index), OD-1 (capacity) | `exec.jsonl` v2, `slotidx.jsonl`, `txfetch.jsonl`, status `chainfetch` coverage |
| Transfer classification (sender tip via the full map, CPI tip, wrap/unwrap, self, platform fee, other), Jito bundle membership where knowable | WP-08 | `exec.jsonl` / `wallet.jsonl` derived fields |
| Unresolved lookup tables retried and recorded | WP-04 | `alts.jsonl` events |
| Explicit counter semantics | WP-02 | `status.jsonl` v2 |
| Our wallet's every landed tx, reconciled | WP-03 (wallet account), WP-03b (fetch), WP-07 | `wallet.jsonl`, `ledger.jsonl`, `recon.jsonl` |
| Provenance (build, git, config, program hashes) | WP-01 | `meta.json` v2, `campaign.json` |
| All Jito verdicts with timestamps; acceptance vs landing | WP-05 | `bundles.jsonl`, `outcomes.jsonl` v2 |
| Block index, ms after trigger, block-ordered route context per attempt | WP-03b, WP-10 | `slotidx.jsonl`, `outcomes.jsonl`, toolkit `blockctx` |
| Per-leader telemetry (identity, kind, region, RTT) | WP-03, WP-05, WP-08 | `leaders.jsonl`, `validators.jsonl`, `attempts.jsonl` |
| Better PoH coverage | WP-08 (+ OD-6) | `poh.log` v2, `slots-feed.log` v2 |
| Correct attribution of who closed each gap | WP-03b, WP-10 | `accounts.bin`, `slotidx.jsonl`, `exec.jsonl`, report R4 |
| Every watched-account update (slot, write_version, txn, data) for deterministic replay | WP-03, WP-09 | `accounts.bin`, `journal.bin` |
| State lag, commit-group completion | WP-04 | `commits.jsonl`, status |
| Every decision and rejection reason; hot-path stage timestamps | WP-00 (state path), WP-04, WP-05, WP-06 | `decisions.jsonl`, `attempts.jsonl` |
| Feed health; resources | WP-02 | `feedhealth.jsonl`, `resources.jsonl` |
| Wallet balance snapshots | WP-07 | `snapshots.jsonl` |
| Leader schedule and validator metadata | WP-03, WP-08 | `leaders.jsonl`, `validators.jsonl` |
| Our program's structured logs decoded per landing | WP-05, WP-08, WP-15 | `outcomes.jsonl` `prog_events` |
| Never slow the hot path (threads, bounded queues, drop counters, compressed rotating files, schema versions, disk budget) | WP-02 | `manifest.json`, `events.jsonl`, `resources.jsonl` |
| Analysis toolkit regenerating per-segment reports correctly | WP-10 | MEASUREMENT.md §6 |

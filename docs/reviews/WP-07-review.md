# WP-07 review: ledger, reconciliation and campaign-wide supervisor stops

**Date:** 2026-10-05. **Reviewer:** adversarial review, read-only. A first reviewer was cut off before writing anything, so this review started from scratch.

**Method:**
- No repository code was changed.
- Probes ran in a scratch copy of the crate. The scratch copies were deleted afterwards.
- The frz reads went to the public RPC (`api.mainnet-beta.solana.com`, about 40 read-only calls).
- Nothing was signed or sent. No `.env`, key or keystore was read.
- Partway through, the coordinator stopped all cargo work: the host was OOM-killing processes. The review was finished statically. Where a check was not run, this document says so and gives the expected result from reading the code.

**Specs:**
- `docs/PLAN.md`:
  - WP-07: items 1-8, config keys, offline and field acceptance;
  - §6: the Stage-0 exit gates and the kill rule.
- `docs/PLAN-ADDENDUM.md`:
  - the go-live gate and its 2026-10-05 update: the frz wallet; a $3-5 budget with a hard cap of 34,000,000 lamports; "never drain it"; floor = start − remaining budget;
  - OD-11, I-3 and I-5.
- `docs/STAGE1-PLAN.md` §6, and `docs/reviews/STAGE1-PLAN-review.md` F6 (the equity basis) and F10 (allotments not enforced). Both are on master (`bc666cb`, `8360300`), after this lane's base.
- `docs/field-tests/README.md`, `docs/field-tests/BUDGET.md`, and `docs/MEASUREMENT.md` (revision 2.10 in this lane).

## What was reviewed

**The work.** The uncommitted WP-07 implementation in `.claude/worktrees/lane-wp-07`. The branch is `lane/wp-07`, and HEAD is the base, `6760f10`.
- 20 modified files, +836/−67.
- 8 new files, 4,191 lines:
  - `src/ledger.rs` and `src/ledger/tests.rs`;
  - `src/supervisor.rs`;
  - `src/campaign.rs` and `src/campaign/tests.rs`;
  - `src/notify.rs`;
  - `tests/campaign.rs`;
  - `deploy/arbx-canary-frz.toml`.

**Snapshot hashes, taken at the start.**
- `git diff`: sha256 `c75161085b2058c4b0b2b29493e632a520b19421ac1c174d7998e2773e38b767`.
- `git diff` followed by the 8 new files (sorted by path): `e195f5436dc43f50a8ba0811d13b53110ab4d95360bbb0eda520acdf908f510a`.
- Both hashes and HEAD were unchanged at the end of the review. This file is the only addition. **The code reviewed is exactly this snapshot.**

**Master moved during the review.** `3ad7c53` ("WP-09: executor replay", 2026-10-05 13:14 UTC) landed while this review ran. Finding 1 depends on it.

## Builds and tests run

All builds used `CARGO_TARGET_DIR=…/scratchpad/targets/wp07` and `CARGO_BUILD_JOBS=2`.

| What | Result |
|---|---|
| `cargo build --release` (worktree) | Passes in 1 m 58 s. Two warnings, both pre-existing (`main.rs:541`, `:549`, irrefutable `if let`). |
| `cargo test --release` (worktree) | **387 passed, 0 failed, 4 ignored.** Lib 358 (+3 ignored), bin 13, `tests/campaign.rs` 2, legacy_fixtures 4, meta_config_hash 1, runtime_isolation 2 (+1 ignored), stop_path 6, supervisor 1. WP-07's own tests: ledger 15, supervisor 3, campaign 7, notify 1, config 1, exec 3, and the 2 in `tests/campaign.rs`. |
| `arbx check` on `deploy/arbx-canary-frz.toml`, `deploy/arbx-stage0.toml`, `deploy/arb.toml` | Exit 0 on all three. Run with `env -i` and an empty `HOME`. The frz output shows: wallet `FRZh63L6…`; `jito-bundle (bundle-only: a live or canary run may start)`; `canary: 0.2 SOL, 100000 attempts`; the five OD-6 feeds `(disabled)`; the stops (0.02 SOL/h, 0.15 SOL/24 h, start − 34,000,000, token floor 0.10%); the bankroll line. |
| Toolkit (`tools/arbx-report/tests`, `python3 -m unittest discover -s .`) | **80 OK, 4 skipped.** Run in the scratch copy with `PYTHONDONTWRITEBYTECODE=1`, so no `__pycache__` lands in the worktree. |
| `tools/test-run-w.sh` (`run-w.sh` changed by 2 comment lines) | **96 of 96 checks passed.** |
| `tools/secret-scan.py` on a committed scratch copy (new files included) | 895 blobs, 1 finding, allowlisted (`testdata/keystore-v3.json`). |
| Ledger on 15 real frz transactions (a scratch test; the data from public RPC) | `ledger::raw` + `ledger::entry` equal an independent Python computation in every field, 15 of 15. The table is under "Probes". |
| `arbx run --canary --budget-left 999999999999`, built binary, scratch config, `env -i` | The budget check passes. See finding 8. |
| Mutations (scratch copy, full `cargo test --release` each) | M1-M4 run: all survive. M5-M10 not run (coordinator's rule), but described with their expected results. See finding 2. |
| 6 demonstration tests | Written, but **not run** (coordinator's rule). The code is in the appendix, and the expected results are traced in findings 3, 4, 6, 7 and 8. |

## Verdict

**Not safe for the frz canary as it stands.** There is 1 blocker and there are 5 majors.

**What is right.** The stop arithmetic, the ledger and the campaign sequencing are right:
- **Units and basis.**
  - Every limit is in lamports.
  - The stop basis is native SOL + the WSOL token amount, as STAGE1-PLAN F6 asked.
  - The USDC quantity floor holds within 0.1%.
- **Order of the rules.** Floor, then token floor, then hour, then day.
- **Speed.** A record that crosses a limit closes the gate in the same engine step: shadow, then the stop closes it for good. The run then stops with exit 20, which ends the campaign.
- **Price.** No rule reads a token's value, and the reconciliation's total residual is algebraically free of token prices.
- **Ledger.**
  - It matches the 13 golden cases and res-pnl to the lamport.
  - It matches 15 real frz transactions independently: failed routes; wins that create a Token-2022 account; the owner's close-account cleanups.
- **Segment order.** A segment starts only after the previous process was reaped.
- **One supervisor.** The `flock` survives `--detach`.
- **Secrets.** No secret reaches campaign.json, provenance.json or check.out.

**What is missing.** The gaps are around the stops:
- whether their input is current (finding 3);
- whether owner transfers move them (finding 4);
- whether the hard cap is cumulative (finding 5);
- whether anything keeps them armed (finding 2);
- one claimed detector that cannot fire (finding 6);
- whether the work can merge with master and still replay (finding 1).

**Blocker:**
1. **Journal INPUT 12 collides with master's `exec_init`, and the replay cannot reproduce the bankroll cap** (finding 1).

**Majors:**
2. The wiring that arms and fires the stops in a live run is untested. Four of four measured mutants that disarm it keep CI green (finding 2).
3. A stale money view keeps the gate open. Within a 60-minute segment the stops see only the wallet records (finding 3).
4. Owner transfers move the stop basis. A deposit extends the floor (103.5M lost on a 5M budget, traced), and a withdrawal is a safety stop. Neither is documented (finding 4).
5. The hard cap is per campaign and per run, not cumulative. The frz config arms the full 34M by default (finding 5).
6. "A refused bundle that landed" can never be flagged: the executor's amend erases the refusal first (finding 6).

**Minimum before FT-004:**
- Finding 1:
  - rebase;
  - renumber the input;
  - make the replay rebuild the money view (or journal it at the decision point).
- Finding 2: add the engine-level arming test and the live-mode `acts` and budget tests. Run the 6 demonstrations and the described mutants.
- Finding 5: `test_budget_lamports = 5_000_000` in the frz config (or `--test-budget-lamports` required), and no manual `arbx run --canary`.
- Finding 4: the FT entries say "no transfers into or out of frz while a campaign runs", until the floor is adjusted for transfers.
- Finding 3: until a staleness gate exists, run FT-004 as two 30-minute segments (`--segment-min 30`), so that a stop snapshot and the campaign-wide check come every 30 minutes.

**Before FT-005 (24 h):** the code fixes for findings 3 and 4, then findings 6 and 7.

## WP-07's claims, checked

| Claim | Holds? | Notes |
|---|---|---|
| Stops on SOL + WSOL; floor = start − test budget; 0.02 SOL/h; 0.15 SOL/24 h | **Yes** | `supervisor::check`; lamports throughout. On frz: start 414,481,617, so FT-004's floor would be 409,481,617. Owner transfers move it (4); it can go stale (3). |
| USDC quantity floor at 0.1% | **Yes** | 22,967,379 − 22,967 = 22,944,412. The route program spends exactly what the previous leg delivered (`nexus-arb-v2` "every leg spends exactly what the previous leg delivered, measured from the output token account's balance"), so the 22.97 USDC holding is never sold by a route. |
| Hourly reconciliation within 10k on both bases | **Partly** | Correct arithmetic (total residual = liquid residual + rent residual; token values cancel). With 60-min segments it runs once per segment, at the stop, with no grace (7). Gaps between segments are never reconciled (9). |
| Refused-bundle-landed detection | **No** | Finding 6. |
| Ledger categories from chain transactions; 13 golden cases; res-pnl's 119 landings | **Yes** | Also 15 of 15 real frz transactions, independently (Probes). |
| `arbx campaign` lock and provider check (I-3) | **Yes**, with limits | The `flock` is inherited through `--detach`'s fork. `probe::busy` runs before every segment. Limits: findings 5 and 14. |
| Passphrase once, piped (frz needs none) | **Yes** | Never in argv, the environment or a file. Leftover copies: finding 15. |
| Binary and config frozen | **Yes** | Binary 0555, config 0444, hashes in campaign.json. Data files are not frozen (16). |
| Control files; SIGINT then SIGKILL | **Yes** in code | A second SIGINT is ignored by a draining segment ("already stopping"), so the drain is never cut. SIGKILL at 180 s is beyond the longest stop (60 + 20 + 5 s). Untested: M4 survives. |
| Crash limit | **Yes** in code | More than 6 crashes in 15 minutes end the campaign. Untested: M5. |
| spend.json | **Yes** | Each signature once, and only what landed after the start. The toolkit double counts (11). |
| Live and canary refused without a budget; `equity_unknown` until the first snapshot | **Yes** in code | `--budget-left` is not capped (8). Untested: M1 and M3 survive. |
| Bankroll: 85% of liquid − 0.03 SOL, at most the WSOL | **Yes** | frz: min(0.85 × 414,481,617 − 30,000,000 = 322,309,374; WSOL 191,524,924; canary 200,000,000) = **191,524,924**. Enforced only in the engine (12). Not replayable (1). |
| Snapshots by `getMultipleAccounts`, retried on a slot mismatch | **Yes** | frz needs one call of 5 accounts: the wallet, the WSOL and USDC ATAs, the USDT ATA (missing) and the accumulator. A single call cannot mismatch. |

**What else I tried to break, and could not:**
- **Sending after a stop rule fires.**
  - `Supervisor::evaluate` puts the gate in sticky shadow before it requests the stop.
  - `Stopper::request` then closes the gate: the test `the_hour_rule_through_the_ledger` ends `GateMode::Stopped`.
  - The rule is evaluated in `Engine::step` right after the ledger and the executor handle the record.
  - The drain handles no account or transaction updates.
- **The floor on the wrong basis.** `equity_stop` = `sol + wsol amount`. Rent is excluded, and so is the WSOL account's rent.
- **Double counting.**
  - Entries are keyed by signature.
  - An earlier segment's signatures are written `dup` and never counted.
  - The executor's provisional fee is replaced by its amend in the same engine step that adds the ledger entry.
- **A segment starting before the previous one exits.** `watch` returns only once `try_wait` has reaped the process. The test with real children shows each pid gone before the next start.
- **Two supervisors on one runs directory.** `flock` (not `fcntl`): the lock's file description is shared with the forked daemon.
- **Rent.** `max_new_token_accounts = 0` refuses every route through a mint the wallet holds no account for. The rent cap uses a 2.1M estimate; actual rent is 1,488,440 (SPL) and 1,513,840 (Token-2022).
- **Crash loops.** No segment sends before its own first snapshot, and the floor is campaign-wide.

## Findings

**Severity:**
- **Blocker:** fix before merge or before the frz canary starts.
- **Major:** a claimed safety property does not hold, or money can move past a limit. Fix it before the canary, or name the operational mitigation in the FT entry.
- **Medium** and **Minor:** as usual.

### 1. Blocker (merge): journal INPUT 12 is master's `exec_init`, and the replay cannot reproduce the bankroll cap

**Location:**
- This lane:
  - `src/feeds/mod.rs` (`Snapshot = 12`);
  - `docs/MEASUREMENT.md` §4.13, "As WP-07 writes it (journal 2.3)";
  - `src/engine.rs:1120` and `:2157-2161`;
  - `src/exec.rs:829-839`.
- Master `3ad7c53`:
  - `src/feeds/mod.rs:74-82` (`ExecInit = 12`);
  - `src/replay.rs:16` and `:420-430`;
  - MEASUREMENT §4.13, "As WP-09 writes it".

**Problem:**
- **The number.**
  - Master, since `3ad7c53`, journals the executor's `exec_init` as **INPUT 12**, in the boot section. This lane journals the ledger's `snapshot` answers as **INPUT 12** too.
  - The two cannot both be merged as written.
  - A careless conflict resolution would make the replay read a snapshot answer as an `exec_init` record ("the journal's exec_init record (INPUT 12) does not read"), or the engine read `exec_init` as a balance snapshot.
- **The replay.** Decisions now depend on the ledger in every mode, and nothing replays it.
  - `Exec::size_cap()` returns min(cap, bankroll), and the bankroll is the ledger's balances, set after every snapshot and wallet entry. Shadow and dry runs apply it too.
  - frz's config sets `bankroll_share = 0.85`, and the cap binds: frz's WSOL (191,524,924) is under the 0.2 SOL cap.
  - The engine also refuses `bankroll_empty`, live and canary refuse `equity_unknown`, and a stop rule closes the gate.
  - Master's replay builds `Exec::offline` from `exec_init`. That record's `bankroll_cap_lamports` is one value read at boot ("null: none before WP-06 / WP-07").
  - The replay engine (`Engine::new_offline`) has no ledger. Its executor sees `bankroll_cap() = None` and quotes at 200,000,000 where the run quoted at 191,524,924.
- **The consequence.** A frz-config recording does not replay identically wherever the bankroll capped a size. Go-live item 3 needs "a 1 h recording that replays identically".
- MEASUREMENT's line "a replay values and reconciles them as the run did" describes a replay that does not exist.

**Proof:**
- `git show master:src/feeds/mod.rs` (lines 73-82) against this lane's `src/feeds/mod.rs`.
- `git show master:docs/MEASUREMENT.md` line 569.
- `exec.rs:829-839` and `engine.rs:2157-2161`.
- frz's balances, under "Probes".

**Fix:**
- Rebase on master and renumber the ledger's input (13).
- Make the replay rebuild the `Ledger`, by one of two routes:
  - a `ledger_init` boot record, plus INPUT 7's `ledger` and INPUT 13. `ledger_init` holds the wallet, the `[ledger]` and `[supervisor]` settings, the candidates, and the campaign history the segment started from: the start, the series points, the test budget, `--budget-left` and `--equity-floor`;
  - or the executor's `MoneyView` in the decision-point record, the way the leader's kind and the Jito token already are.
- Add a replay test of a recording where `bankroll_share > 0` binds.
- Make MEASUREMENT give one journal version for both lanes.

### 2. Major: the wiring that arms and fires the stops in a live run is untested; disarming it keeps CI green

**Location:** `src/engine.rs:973`; `src/main.rs:1059`, `:1363`; `src/campaign.rs:429`, `:488`, `:571`; `src/ledger.rs:1030`, `:1077`; `src/supervisor.rs:130`.

**Problem:**
- The tests drive `Ledger`, `Supervisor`, `Campaign` and `Exec` through hand-made rigs, which set the switches themselves: `require_equity(true)`, `acts` left at its default `true`, a 34M budget.
- Nothing tests the assembly `arbx run` performs.
- So each line that connects the safety layer to a live run can be broken with CI green.

**Proof:** each mutant was applied alone to a scratch copy, then the full `cargo test --release --no-fail-fast` was run. M5-M10 could not run (the host's OOM pressure, then the coordinator's one-cargo rule). Their results below come from reading the tests.

| # | Mutant | Where | Result |
|---|---|---|---|
| M1 | `x.require_equity(with_ledger)` → `require_equity(false)`: a live run with a ledger sends before its first snapshot | engine.rs:973 | **Survives** (measured: arbx rebuilt; 387 passed, 0 failed) |
| M2 | `l.sup.acts = mode.sends()` → `false`: no stop rule ever acts in live or canary | main.rs:1363 | **Survives** (measured, 387/0) |
| M3 | the refusal "a live or canary run needs a test budget" removed | main.rs:1059 | **Survives** (measured, 387/0) |
| M4 | the SIGKILL escalation removed | campaign.rs:488 | **Survives** (measured, 387/0) |
| M5 | crash limit `> CRASH_LIMIT` → `> 100_000` | campaign.rs:429 | Not completed (killed under OOM pressure). Expected to **survive**: no test crashes more than 2 segments (`tests/campaign.rs`: 2 boot failures with `--max-segments 2`), and the unit tests have no crash loop |
| M6 | `on_wallet_tx` applies every entry to `cur` (`filter(\|c\| e.slot > c.slot)` → `filter(\|_\| true)`): a record that arrives after a snapshot already holding it is counted twice | ledger.rs:1077 | Not run. Expected to **survive**: in every ledger test, a record's slot is above the latest snapshot's |
| M8 | the floor fires only 0.5M below (`equity < f` → `equity + 500_000 < f`) | supervisor.rs:130 | Not run. Expected to be **caught** by `the_supervisor_acts_through_the_gate_and_the_stopper` (floor 100, equity 99) |
| M9 | the floor is the **lowest** candidate (`.max()` → `.min()`) | ledger.rs:1030 | Not run. Expected to **survive**: the only test with two candidates (`campaign_stops_across_two_segments`, ledger/tests.rs:592) makes them equal (380.5M and 380.5M). The demonstration `review_the_floor_is_the_highest_candidate` catches it |
| M10 | `arbx campaign` starts a sending campaign without a budget | campaign.rs:571 | Not run. Expected to **survive**: `tests/campaign.rs:37` uses a config without `[canary] enabled`, so it is refused one check earlier; the unit tests build `Campaign` directly |

(M7, the `bankroll_empty` refusal removed, also survives by inspection, but it is benign: a quote of size 0 is refused further on.)

**Fix:**
- An engine-level test: an `Engine` with a `Mode::Live` executor and a ledger, as `run()` assembles them. It checks two things:
  - nothing is sent before the first snapshot (`equity_unknown`);
  - a wallet entry that crosses the floor closes the gate and requests stop `equity_floor`.
- Factor `run()`'s ledger assembly (main.rs:1359-1374) into a function, and test that live and canary give `acts = true` and an armed floor.
- `tests/campaign.rs`:
  - `arbx run --canary` without a budget is refused for the budget (it fails before any network);
  - a canary campaign with `[canary] enabled = true` and no budget is refused for the budget.
- Campaign unit tests for the crash limit (7 crashes in 15 minutes) and for the SIGKILL escalation (a child that ignores the stop).
- Add the floor test with two different candidates (appendix).

### 3. Major: a stale money view keeps the gate open (fail open on the stops' only input)

**Location:** `src/ledger.rs:1035-1040` (`view`: `equity_known` stays true once a snapshot landed), `:1101-1156` (`retry_later`, `on_snapshot`, `next_hourly`), `src/exec.rs:853`.

**Problem:**
- The stops read `cur`: the last good snapshot plus the wallet entries after it. Once the first snapshot has landed, nothing checks that `cur` is current:
  - a failed snapshot is retried every 30 s forever, while the gate stays live;
  - a wallet record the chain-fetch service gives up on (10 minutes after it was found) never reaches the ledger, so that landing's money is invisible to the floor and the drop caps until the next snapshot.
- With `segment_min = 60` and `snapshot_min = 60`, the next snapshot *is* the stop snapshot. `next_hourly` is the start snapshot + 60 min, which is after the segment's deadline. So within a segment, the stops see only what the wallet records deliver.
- WP-03b's `chainfetch_dead` closes the gate only when the service's thread dies, not when its fetches fail.
- Invariant 4 says "If any input of a send is missing, stale or unverified, there is no send". This is the input the stops protect.
- **Exposure:** up to one segment (60 minutes) of losses the floor cannot see, if the RPC fails while the bot has a money-losing defect. Bundles that the on-chain guard lets land should not lose; the floor exists for when that assumption breaks.

**Proof:** the demonstration `review_stale_money_view_keeps_the_gate_open` (appendix) was not run. Its trace:
- the start snapshot sets `cur`;
- each failed answer goes `on_snapshot` → `Snapshot::parse` → `Err("rpc down")`: `snapshot_failed`, then `retry_later`, and `cur` is untouched;
- `evaluate` sees an unchanged 414.5M, so no rule fires.

After 6 h: `equity_known = true`, `gate.allows() = true`, `last_snapshot_age_s_now = 21,600`, `snapshot_failed = 720`.

**Fix:**
- Shadow with reason `equity_stale` when the last good snapshot is older than `snapshot_min` + 2 × `snapshot_retry_s`, or than a new `max_snapshot_age_s`.
- Take a snapshot at least every 15 minutes in a sending run (`snapshot_min` ≤ `segment_min` / 2).
- Shadow while a landing the executor found by a status check (`Landing::provisional`) has had no record for N minutes. Alternatively, count that landing's worst case (tip + fee) in the stop basis until its record comes.

### 4. Major: owner transfers move the stop basis; a deposit extends the floor, a withdrawal is a safety stop; neither is documented

**Location:** `src/supervisor.rs:129-150` (`check` on the raw SOL + WSOL), `src/ledger.rs:1026-1031` (`apply_limits`: floor = start − budget, fixed), `src/campaign.rs:286-290`; `docs/field-tests/README.md` "Enforcement".

**Problem:**
- The stops compare the raw balance with start − budget. The ledger does classify the owner's transfers (`transfer_in`, `transfer_out`), and `net_spend` excludes them, but the stops ignore both.
- **A deposit raises the headroom by the deposit.** Take FT-004's 5,000,000 budget, and let the owner top frz up with 0.1 SOL. The bot can then lose 4.5M an hour for 23 hours: under the 20M hour cap and the 150M day cap. That is **103,500,000 lamports lost** with no stop: 20× the allotment and 3× the 34M hard cap. frz is the production wallet, so a top-up during FT-005's 24 h is plausible.
- **A withdrawal is a safety stop.**
  - Moving 0.025 SOL out trips `equity_hour` (exit 20), and the campaign ends.
  - Moving out more than the budget trips `equity_floor`.
  - Either way the stop fails safe, but it is false, and nothing tells the owner.
- STAGE1-PLAN review F6 asked for a stop metric free of price and of transfers ("the cumulative ledger categories since the start").

**Proof:** two demonstrations, not run; their traces follow (appendix).
- `review_deposit_extends_the_floor`:
  - the floor is 409.5M;
  - the deposit takes SOL + WSOL to 514.5M;
  - after 23 hourly losses it is 411M, still above 409.5M;
  - the rolling-hour drop is 4.5M and the 24 h drop is 103.5M (under 150M).
  - Result: no stop, gate live, 103.5M lost.
- `review_owner_withdrawal_is_a_safety_stop`:
  - 389.495M stays above the 380.5M floor;
  - but the hour drop is 25.005M, over 20M;
  - stop reason `equity_hour`, exit 20.

**Fix:**
- Adjust the floor and the series by the ledger's own transfers: floor = start − budget + Σ`transfer_in` − Σ`transfer_out` since the start.
- Or add a floor rule on cumulative `net_spend` ≥ budget, which is free of price and of transfers, and keep the raw floor as a backstop.
- Document both cases in docs/field-tests/README.md.

### 5. Major: the hard cap is per campaign and per run, not cumulative; the frz config arms the full 34M by default

**Location:** `deploy/arbx-canary-frz.toml:623` (`test_budget_lamports = 34000000`) and its header, line 7 ("a canary run: `arbx run --canary` (or `arbx campaign …`)"); `src/campaign.rs:568-571`; `src/main.rs:1059`, `:1372`; `docs/field-tests/BUDGET.md`.

**Problem:**
- The owner's 34,000,000 caps **all** tests together. BUDGET.md sets the floor "from the **remaining** budget", and STAGE1-PLAN review F10.3 asks for "each test's floor from its own allotment".
- **In the code, the budget restarts with every campaign.**
  - `arbx campaign` takes min(`--test-budget-lamports`, the config's value).
  - Nothing reads earlier campaigns' spend.json or BUDGET.md.
  - If the flag is omitted, FT-004 (allotment 5M) runs against the full 34M, and an FT-005 started the same way gets another 34M.
- **`arbx run --canary` on the frz config,** which the config's own header suggests:
  - It arms a floor of *that run's own* start − 34M, and every manual run starts afresh.
  - `arbx run` takes neither the campaign lock nor the provider check. A manual run beside a campaign doubles the exposure, under two floors.
- The FT allotments are enforceable, but only by a flag the operator must remember.

**Proof:**
- The code cited above.
- `grep -rn spend.json src/`: the file is written (`campaign.rs:298-299`) and never read.
- `probe::busy` and `lock_runs` are called only by `arbx campaign` (`campaign.rs:577-578`) and `grpc-probe` (`main.rs:565-566`), never by `arbx run`.

**Fix:**
- In the frz config, set `test_budget_lamports` to the smallest pending allotment (5,000,000 for FT-004), and lower it after each test from BUDGET.md's "Remaining". Or make `arbx campaign` require `--test-budget-lamports` in a sending mode.
- Better still: a cumulative `<runs>/budget.json` (the hard cap less every campaign's net spend), which both `arbx campaign` and `arbx run --live/--canary` subtract from.
- Refuse `arbx run --canary` and `--live` while the campaign lock is held or `probe::busy` is non-empty, unless `--force`.
- Point the config's header at `arbx campaign` only.

### 6. Major: "a refused bundle that landed" can never be flagged; the executor's amend erases the refusal first

**Location:** `src/exec.rs:1256-1270` (`on_wallet_tx` amends any final without its record), `:1409-1423` (`amend` sets `fin` to `landed_ok` or `landed_fail`); `src/ledger.rs:733-771` (`exec_recon`), `:893-901` (`history` drops an amended attempt from `earlier`); `src/engine.rs:1113-1118`.

**Problem:**
- `exec_recon` flags a refused bundle only when both of these hold:
  - the executor's final is still `not_landed_refused`;
  - the ledger has an entry for the bundle's signature.
- Both come from the same wallet record, which `Engine::step` hands first to the ledger and then to the executor. The executor's `amend` then overwrites the final with `landed_ok` and sets `landed = true`.
- So a reconciliation after the record sees a matched landing, and one before it sees no entry. Neither flags the bundle.
- **`not_counted`** (an expired attempt that landed) is dead for the same reason.
- **Across segments:**
  - `history()` drops an attempt from `earlier` once its segment wrote the amend line.
  - A later landing recorded as `pre_run` is skipped by `exec_recon`.
- The test `the_executors_money_against_the_chain` builds a view the system never produces: `fin: "not_landed_refused"` together with an entry.
- The money is still counted, because the amend adds it. What is lost is the detector for a broken invariant ("a miss costs nothing", and WP-05's refusal semantics).

**Proof:** the demonstration `review_a_refused_bundle_that_lands_is_never_flagged` (appendix; it uses the existing exec rig; not run). Its trace:
- the bundle is refused, and its final is `not_landed_refused`;
- its record arrives with the route program's events (round trip 49,000), the fee 5,000 and the tip 31,499;
- `Ledger::on_wallet_tx` inserts the entry (`trade_net` 12,501);
- `Exec::on_wallet_tx` finds the attempt in `finals` (`by_sig` was cleared at finalize; it falls back to `attempt`) and amends it: `fin = landed_ok`, round trip 49,000, tip 31,499;
- `exec_recon` matches the two with `diff = 0`.
- Result: `ok = true`, `refused_landed = []`. The test's assertion of the claim fails.

**Fix:**
- Keep the first final: a `first_fin`, or a `refused_then_landed` flag set in `amend` when the earlier final was `not_landed_refused`.
- Raise it at once: events.jsonl `refused_bundle_landed`, `sup.reconcile_miss`, a Critical notice.
- Make `exec_recon` and `history()` read it.
- Test in the real order: the ledger first, then the executor.

### 7. Medium: one reconciliation per segment, at the stop, decided without grace or search; one late record makes every later segment record only

**Location:** `src/ledger.rs:1325-1326` (`final_recon`: `due = 0; searched = true`) and `:864` (`history` counts every `ok: false`; it reads `r["final"]`, which nothing writes); `src/main.rs:1520-1526` (5 s after the stop snapshot); `src/campaign.rs:353-360`.

**Problem:**
- Each 60-minute segment has exactly one reconciliation: start against stop. It is decided 5 s after the stop snapshot, with no window search and no second chance.
- Take a landing that the status check settled just before the drain ended, and whose record is still on its 5 s or 30 s retry. Its liquid delta is then the residual, which counts as a miss. `history()` counts the miss, and **every later segment of the campaign records only.** For FT-005 that is up to 23 lost hours from a race, not from missing money.

**Proof:** the demonstration `review_late_record_at_stop_is_a_campaign_miss` was not run. Its trace:
- the start snapshot (slot 1,000) and the stop snapshot (slot 2,000) differ by +12,501 liquid, and there is no entry;
- `final_recon` writes `ok: false` with residual 12,501 > 10,000, and the gate goes to `reconcile_miss`;
- `history()` over that recon.jsonl returns 1 miss.

**Fix:**
- At stop, run the window search and wait up to `recon_grace_s` inside the drain.
- If the miss is still unexplained, write it `final: false`, and let the next segment decide it again (its pre-run records cover it) before the campaign goes records-only.
- Write `final` on every recon line.

### 8. Medium: `arbx run --budget-left` is not capped at the hard cap; the floor's "highest wins" is untested

**Location:** `src/main.rs:99`, `:818`, `:1059`, `:1372`; `src/ledger.rs:1011-1031`.

**Problem:**
- The hard cap is checked in two places: `[supervisor] test_budget_lamports` at load, and `arbx campaign --test-budget-lamports`.
- It is not checked for `arbx run --budget-left`. That flag alone passes the budget check, and arms floor `b` = own start − budget-left.
- With a config whose `test_budget_lamports = 0` (`arbx-stage0.toml`, `arb.toml`), `--budget-left 999999999999` starts a canary with a floor about 1,000 SOL under its start: no floor at all.
- The frz config escapes only because its own 34M candidate wins the `max`.
- `set_campaign` also trusts campaign.json's budget without the cap.

**Proof:**
- A scratch copy of `arbx-stage0.toml` (canary enabled; keystore path pointing at a file that does not exist), the built binary, `env -i`:
  - without a budget, the run is refused ("a live or canary run needs a test budget…");
  - with `--budget-left 999999999999`, it passes and stops only at `Error: reading …/no-such-keystore.enc: No such file or directory`.
- Mutant M9 (finding 2).

**Fix:**
- Refuse `--budget-left` above `TEST_BUDGET_HARD_CAP`, and `--equity-floor` below 0.
- Clamp the budget in `set_campaign` and `history()`.
- Add the two-candidate test.

### 9. Medium: reconciliation blind spots between and around segments

**Location:** `src/ledger.rs:1268-1323`; `src/campaign.rs` (no campaign-level reconciliation).

**Problem:**
- **Between segments.** Each segment reconciles only its own snapshots. The window from one segment's stop snapshot to the next segment's start snapshot is never reconciled. It runs about 1-2 minutes an hour (the drain plus the boot), and it holds two things:
  - the late landings of the previous segment's open attempts;
  - any owner or third-party activity.
- **The promised join.** PLAN WP-07 item 7 promises that "the campaign-level reconciliation joins them to attempts by signature", but there is no such reconciliation.
- **Failed or incomplete stop snapshots.**
  - A failed stop snapshot leaves the whole segment unreconciled, and nothing records that.
  - A `snapshot_incomplete` window at the stop is never closed.
- So the Stage-0 exit's "24 h of hourly reconciliations within 10k" cannot be shown across these gaps.

**Fix:**
- Reconcile the previous stop snapshot against the next start snapshot, with the entries of both ledgers in that slot window. Either `arbx campaign` does it between segments, or the next segment does it from `History::last_snapshot`.
- Write `uncovered` windows to recon.jsonl.

### 10. Medium: PLAN WP-07 item 5's `venue_quarantine` (a programdata change) is not implemented, and not listed as deferred

**Problem:**
- A mid-run upgrade of a venue program, or of the route program 8K8uyQDt, is recorded and nothing more. The next segment's start check covers only the route program's hash.
- MEASUREMENT A.1 still lists `venue_quarantine`.

**Fix:** implement the rule, or record the deferral in PLAN and MEASUREMENT.

### 11. Minor: the toolkit counts `dup` ledger lines

**Location:** `tools/arbx-report/arbx_report/reports/r1_money.py:28-60`; `src/ledger.rs:1065`.

**Problem:** R1 sums every ledger line. A signature an earlier segment already recorded is written again with `dup: true`, so the campaign roll-up counts it twice. spend.json (the Rust side) does not.

**Fix:** skip `dup: true` in the toolkit, or count such lines in the status instead of writing them to ledger.jsonl.

### 12. Minor: the executor does not re-check the size against `size_cap()`

**Location:** `src/exec.rs:905-940`; `src/engine.rs:2159-2161`.

**Problem:** the bankroll and WSOL cap is applied only where the engine re-quotes. A future path that hands `decide` a route sized elsewhere would send above the bankroll.

**Fix:** refuse `r.size > self.size_cap()` in `decide_inner`, with reason `size_cap` (already in A.1).

### 13. Minor: the notify hook runs synchronously, before the stop request

**Location:** `src/supervisor.rs:205-218`, `src/notify.rs:56-64`.

**Problem:**
- WP-20's hook will run on the engine thread, before `stopper.request(...)`.
- If it blocks, the stop is delayed.
- If it panics, the stop request is lost and the run ends as a panic (exit 30). The campaign then restarts a segment, and the between-segment check catches the breach only if the files already show it.

**Fix:** request the stop first, then notify. Wrap the hook in `catch_unwind`.

### 14. Minor: checks that miss a second bot

**Location:** `src/probe.rs:230-260`, `src/campaign.rs:167`, `:467`.

**Problem:**
- `busy()` looks only for `arbx…` or `arb-lab…` processes with `run` in their argv. arbed's bot (bun/pm2, the same frz keystore) is invisible to it. Its landings are flagged as `unknown_route_landings` only at the end-of-segment reconciliation.
- When `try_wait` errors, `watch` returns −1 without reaping the child. With `--force`, the next segment then starts beside it.

**Fix:**
- State in the FT protocol that no other process may use frz during a campaign.
- On a `try_wait` error, stop and wait for the child, as for a normal stop.

### 15. Minor: the passphrase leaves copies and is not mlock'd (OD-7 asked for it)

**Location:** `src/wallet.rs:111-121`, `:166`; `src/campaign.rs:130-131`.

**Problem:**
- `Secret` zeroes its own `String`, but copies remain elsewhere:
  - in `stdin()`'s internal buffer;
  - in the TTY `BufReader`;
  - in the buffers that `read_line` grew and freed.
- `decrypt`'s v2 path does not zero its scrypt key.
- frz does not use this path: its keystore is the profile one, with no passphrase.

**Fix:** read the passphrase with `read(2)` into an mlock'd fixed buffer and zero it after use. Zero the scrypt key in every path.

### 16. Minor: docs and spec drift

- PLAN WP-07 still reads `hour_drop_sol = 0.05`, "shadow … until drop_1h is back under", and `run-w.sh` reading `arbx campaign-equity`. The build has `max_drop_per_hour_sol = 0.02` with a campaign stop. The build is stricter, but the docs disagree with it.
- This lane's BUDGET.md and README predate master's F6 text (`8360300`). Both must be merged at the rebase.
- The campaign does not freeze the data files the config names: seed list, crowded pools, registry. A pooldisco refresh mid-campaign would change later segments. meta.json should at least hash those files.

## Probes

### frz on chain (public RPC, read-only)

Read at slots 453,588,500-453,594,371:

| Account | Balance |
|---|---|
| Native SOL | 222,956,693 |
| WSOL ATA `HtT4Ze…` | 193,013,364 lamports; 191,524,924 WSOL |
| USDC ATA `APtQh4…` | 1,488,440 lamports; 22,967,379 raw USDC |
| PumpSwap accumulator `CUiyUSbx…` | 1,346,200 lamports, owned by PumpSwap |

- **The accounts the snapshots read.**
  - There are no Token-2022 accounts.
  - Neither ATA has a delegate or a close authority.
  - I re-derived both ATAs and the accumulator PDA in Python, and they equal the snapshots' candidates.
- **Start and floor.** SOL + WSOL = **414,481,617**, so FT-004's floor would be 409,481,617.
- **History.**
  - The last activity is 2026-10-04 19:29 UTC: three owner close-account transactions.
  - On 2026-10-03 there were 9 failed direct route transactions (fees 6,291-7,361) and 3 wins, from the old bot.

### The ledger on 15 frz transactions

`ledger::raw` and `ledger::entry` (scratch test) against an independent Python computation from `jsonParsed`: every field matches.

| Signature | Slot | Kind | ok | Fee | Tip | Rent locked / reclaimed | liquid_delta | equity_delta | Categories |
|---|---|---|---|---|---|---|---|---|---|
| `zBGThDQYTQtP…` | 452,993,211 | route | yes | 7,051 | 0 | 1,513,840 / 0 | −1,508,762 | 5,078 | trade_gross 12,129, fee_win −7,051 |
| `3ki8Y7a5KD9e…` | 452,994,390 | route | no | 6,291 | 0 | 0 / 0 | −6,291 | −6,291 | fee_fail −6,291 |
| `2eK4j9yNDFDD…` | 452,994,625 | route | no | 7,361 | 0 | 0 / 0 | −7,361 | −7,361 | fee_fail −7,361 |
| `4tkj4VSvDexU…` | 452,994,836 | route | yes | 5,000 | 18,973 | 0 / 0 | 13,973 | 13,973 | trade_gross 37,946, tip −18,973, fee_win −5,000 |
| `2T49Vjhhq16v…` | 452,997,043 | route | no | 6,531 | 0 | 0 / 0 | −6,531 | −6,531 | fee_fail −6,531 |
| `hp5vSS9djGi9…` | 452,997,583 | route | no | 6,601 | 0 | 0 / 0 | −6,601 | −6,601 | fee_fail −6,601 |
| `dYWaY1n1reru…` | 452,997,819 | route | yes | 5,000 | 13,072 | 1,513,840 / 0 | −1,505,877 | 7,963 | trade_gross 26,035, tip −13,072, fee_win −5,000 |
| `2HZt9ghYHBYs…` | 452,998,229 | route | no | 6,750 | 0 | 0 / 0 | −6,750 | −6,750 | fee_fail −6,750 |
| `5ivdcdmwarSc…` | 452,998,700 | route | no | 6,480 | 0 | 0 / 0 | −6,480 | −6,480 | fee_fail −6,480 |
| `rVg6THjCaujM…` | 452,998,756 | route | no | 6,481 | 0 | 0 / 0 | −6,481 | −6,481 | fee_fail −6,481 |
| `2amsfPghEivv…` | 452,999,387 | route | no | 7,301 | 0 | 0 / 0 | −7,301 | −7,301 | fee_fail −7,301 |
| `5iVcaSU1GcaV…` | 452,999,571 | route | no | 7,051 | 0 | 0 / 0 | −7,051 | −7,051 | fee_fail −7,051 |
| `2ud9HXTRBLjp…` | 453,350,615 | close | yes | 5,000 | 0 | 0 / 17,861,280 | 17,856,280 | −5,000 | fee_other −5,000 |
| `3nhU65P8dkHJ…` | 453,350,617 | close | yes | 5,000 | 0 | 0 / 18,013,680 | 18,008,680 | −5,000 | fee_other −5,000 |
| `2SxG2Avg33AP…` | 453,350,620 | close | yes | 5,000 | 0 | 0 / 3,027,680 | 3,022,680 | −5,000 | fee_other −5,000 |

What the table checks:
- **Rent stays out of trading.** In the wins that create a Token-2022 account (1,513,840 locked), `trade_gross` is the WSOL gain alone.
- **Closing accounts is equity-neutral** except for the fee, including the Token-2022 ones.
- **Tips.** Only transfers to non-own, non-fresh accounts count as tips.

### Demonstration tests (written, not run)

There are six tests (appendix): five go in `src/ledger/tests.rs` and one in `src/exec/tests.rs`. Each one's trace is in its finding: findings 3, 4 (two tests), 6, 7 and 8.
- The test for finding 6 asserts WP-07's claim, and is expected to **fail**.
- The other five assert the behaviour the finding describes, and are expected to **pass** on this lane's code.
- The floor test is expected to fail under M9.

## Not verified

- Wallet-record latency on Cherry: how often a record misses the 5 s window at a stop (finding 7). It is reasoned from the fetch schedule in MEASUREMENT §4.15, not measured.
- Whether arbed's bot still runs on Cherry with the frz keystore (finding 14). I did not SSH.
- M5-M10, and the six demonstrations: written and traced, not run.

## Appendix: the demonstration tests

Append to `src/ledger/tests.rs` (they use its `rig`, `snap_answer`, `usdc_price`, `wtx`, `no_landings`, `snap`, `write_segment`):

```rust
#[test]
fn review_deposit_extends_the_floor() {
    let (mut l, sess, dir, rec) = rig("rv-deposit", |c| c.test_budget_lamports = 5_000_000);
    l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0, &usdc_price);
    assert_eq!(l.sup.limits.floor, Some(414_500_000 - 5_000_000));
    let mut t = T0 + M;
    l.on_wallet_tx(&wtx("dep", 1_001, "transfer_in", true, 100_000_000, 0, 0, 0), t, &usdc_price, None);
    l.tick(t, &no_landings);
    let mut lost = 0i64;
    for k in 0..23u64 {
        t += 60 * M;
        l.on_wallet_tx(&wtx(&format!("loss{k}"), 1_100 + k, "route", false, -4_500_000, 0, 4_500_000, 0), t, &usdc_price, None);
        l.tick(t, &no_landings);
        lost += 4_500_000;
    }
    assert!(!sess.stopper.stopping() && sess.gate.allows(), "the floor held");
    assert_eq!(lost, 103_500_000);
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn review_owner_withdrawal_is_a_safety_stop() {
    let (mut l, sess, dir, rec) = rig("rv-withdraw", |_| {});
    l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0, &usdc_price);
    l.on_wallet_tx(&wtx("wd", 1_001, "transfer_out", true, -25_005_000, 0, 5_000, 0), T0 + M, &usdc_price, None);
    l.tick(T0 + M, &no_landings);
    assert_eq!(sess.stopper.info().map(|i| i.reason), Some(StopReason::EquityHour));
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn review_stale_money_view_keeps_the_gate_open() {
    let (mut l, sess, dir, rec) = rig("rv-stale", |_| {});
    l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0, &usdc_price);
    let mut t = T0;
    for _ in 0..(6 * 120) {
        t += 30 * S;
        l.on_input(&json!({ "what": "snapshot", "why": "retry", "error": "rpc down" }), t, &usdc_price);
        l.tick(t, &no_landings);
    }
    let v = l.tick(t, &no_landings);
    let m = l.money_json(t, json!({}), 0);
    assert_eq!(m["last_snapshot_age_s_now"].as_u64(), Some(21_600));
    assert!(v.equity_known && sess.gate.allows());
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn review_late_record_at_stop_is_a_campaign_miss() {
    let camp = std::env::temp_dir().join(format!("arbx-rv-late-camp-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
    std::fs::create_dir_all(&camp).unwrap();
    let (mut l, _sess, dir, rec) = rig("rv-late", |_| {});
    l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0, &usdc_price);
    // a win landed at slot 1_990; its record has not come; the stop snapshot (slot 2_000) shows it
    l.want_stop_snapshot();
    l.on_input(&snap_answer(2_000, 223_000_000 - 36_499, 191_500_000 + 49_000, 22_970_000, "stop"), T0 + 60 * M, &usdc_price);
    l.final_recon(T0 + 60 * M + 5 * S, &no_landings);
    rec.sync();
    let r = crate::rec::read_jsonl(&dir, "recon").unwrap();
    assert_eq!(r.last().unwrap()["ok"], json!(false));
    let seg = camp.join("c-p1");
    std::fs::create_dir_all(&seg).unwrap();
    std::fs::write(seg.join("meta.json"), json!({ "run": { "started_ns": T0 } }).to_string()).unwrap();
    std::fs::write(seg.join("recon.jsonl"), format!("{}\n{}\n", json!({ "schema": "arbx.recon/1.0", "file_seq": 0 }), r.last().unwrap())).unwrap();
    assert_eq!(history(&camp, None, T0 + 61 * M, DAY_NS).recon_misses.len(), 1, "every later segment records only");
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
    let _ = std::fs::remove_dir_all(&camp);
}

#[test]
fn review_the_floor_is_the_highest_candidate() {
    let camp = std::env::temp_dir().join(format!("arbx-rv-floor-camp-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
    std::fs::create_dir_all(&camp).unwrap();
    std::fs::write(camp.join("campaign.json"), json!({ "budget": { "test_budget_lamports": 34_000_000 } }).to_string()).unwrap();
    let s0 = Snapshot { t_ns: T0, ..snap(1_000, 223_000_000, 191_500_000, 4_078_560) };
    write_segment(&camp, "c-p1", T0, &[s0], &[], &[]);
    let h = history(&camp, Some("c-p2"), T0 + 61 * M, DAY_NS);
    let (mut l, _sess, dir, rec) = rig("rv-floor", |_| {});
    l.set_campaign(h, Some(34_000_000), Some(29_000_000), None);
    l.on_input(&snap_answer(2_000, 228_000_000, 191_500_000, 22_970_000, "start"), T0 + 62 * M, &usdc_price);
    // candidates: campaign start − budget = 380.5M; own start − budget left = 390.5M: the higher wins
    assert_eq!(l.sup.limits.floor, Some(419_500_000 - 29_000_000));
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
    let _ = std::fs::remove_dir_all(&camp);
}
```

Append to `src/exec/tests.rs` (it uses its `rig`, `route`, `damm`, `money`). This test is expected to **fail**: that failure is finding 6.

```rust
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn review_a_refused_bundle_that_lands_is_never_flagged() {
    let mut r = rig("rv-refused", Mode::Live, "").await;
    let t = now_ns();
    r.x.set_money(money(414_500_000, 191_500_000, 4_078_560));
    assert_eq!(r.decide(route(14, damm(15, MINT), 50_000, 1), 100, t).reason, "sent");
    let Settled::Fired { attempt: a3, fired: mut f } = r.settled().await else { panic!("a fire result") };
    let sig = f.copies[0].sig.clone().unwrap();
    f.copies[0].ok = false;
    f.copies[0].t_ack = 1;
    f.copies[0].reply = Some("refused: invalid argument".into());
    r.x.on_settled(Settled::Fired { attempt: a3, fired: f }, now_ns(), &|_| None);
    assert_eq!(r.x.landings().iter().find(|x| x.attempt == a3).map(|x| x.fin), Some("not_landed_refused"));
    // it lands anyway: its record goes to the ledger, then to the executor (Engine::step's order)
    let mut ledger = crate::ledger::Ledger::new(Default::default(), Default::default(), [1u8; 32], Rec::off(), "rv");
    let raw = crate::ledger::Raw { kind: "route".into(), ok: true, payer: true, wallet_sol: -36_499, wsol: 49_000, fee: 5_000, tip: 31_499, ..Default::default() };
    let events = json!([{ "kind": "out", "leg": 0, "amount": 77 }, { "kind": "out", "leg": 1, "amount": 1_000_049_000u64 }]);
    let d = json!({ "sig": sig, "slot": 120, "idx": 3, "ok": true, "err": null, "fee": 5_000, "attempt": a3, "prog_events": events, "ledger": raw.json() });
    ledger.on_wallet_tx(&d, now_ns(), &crate::ledger::no_prices, None);
    r.x.on_wallet_tx(&d, &|_| None);
    let (line, ok) = crate::ledger::exec_recon(&ledger.entries, &r.x.landings(), &Default::default(), 10_000);
    assert!(!ok && !line["refused_landed"].as_array().unwrap().is_empty(), "a refused bundle that landed is not flagged: {line}");
}
```

The 15 frz signatures:

```
zBGThDQYTQtPZEARUEkDPPJxNPZVJdSaaBd6R76d6zpYriSnqeUQzsNNGrCuZ5w6Ci8wXVCVN1prVWWCL7fg9sT
3ki8Y7a5KD9ejWHzRKvrwonymo9kk2nMUbNL5XD23Q7cGp76dNXd6zMdfhWZix3tpx3ZSUCJdRyHhWKdiSnP37WN
2eK4j9yNDFDDs93L3Chr8wu9utH8q7n2VfQzaRXxD5NvHTXSWgFf74CBkLfYPaNJLk1BziTTaVVkYSGcki5yXB6E
4tkj4VSvDexUsF7Jj5pwBQEGK8E8mUEWbwKU8ZpXigXJEhsX6a8oRhvG7dcWR9NvacqrfzQHEWPz7yA6RsXNrSZC
2T49Vjhhq16v4wSs2fwnX5renQLGX7QXxe7izQYC57hkLbz42WpqpwEFkEggiAep6gSe3unJCHyW2MZmYWGcoAQM
hp5vSS9djGi9Uunsw18wNFcMcK9zLQrtbNvZ8xD3n4LUPSVX5TgngWHTW2p3NrvNcg5JxzmoP4kMZXTs2kighex
dYWaY1n1rerus3pK8RWMX6rDXMdg28cJKJqCxnT6fEYRU5keTLMXtxxfSB4KYpEPYwSYgYYhiSqZPWKWgNoDSQn
2HZt9ghYHBYsjjM28WVWoEy5dEqYiT3sEy2Z5THNN57s5QiSrftdTTJkk4va9YsdJJVjoMKS5BUH17i18w8anW7f
5ivdcdmwarScBkT1jupy9maviH1hTL1iHKhjCkRVH7xVS15VqEQ2CdLYheXto57FExqQxdNSZHFMWHF5rdALECEu
rVg6THjCaujM4rxX2P7D5b34Lu84y9zCMrKqyaud5LN2py4vkDMeoDAbUDZq9s1APj6DrH4CPEDyErVVhACZv2B
2amsfPghEivvPN7yFFPKKGLEGdhZR4eASFLJtNhicaBuXiYUHEmm97zabUQ41FHuSEMWnWCueRB2fBjS5cX9wYQ5
5iVcaSU1GcaVcm3bn6DbAUUTQGYseWBEeSpRNUBtBVRRQiBrQcwXWQfEpbsZ9UXANSQ6bmjB5rWiisHQMDqVYkBV
2ud9HXTRBLjpmasXx7nRgDqpKTEEUqgswAELW1WyZfeUWgfakWyXRVeJgFNAT9tNA8yQHFpjArtEP3Ru5wBJEAgQ
3nhU65P8dkHJpFVtBaKsLLzW76m7WbGhTR7tBAAofbwfKDHLNFWadFyj2Mw3WJtXC5cLnxReYVQZBgpWKvYWsnir
2SxG2Avg33APTdZQHTsTV2auV3s4Jc6ZGSxS1j6CUKRy9QBsGXE6QTtovDSKKi62jxMy33HMfWoihQxNfgrYuJ1x
```

## Disposition (2026-10-06, the WP-07 commit)

**Base.** The lane was rebased onto master `20f6812`: WP-09's executor replay (`3ad7c53`), the WP-16 merge (`172eb56`) and the FT-000b notes. The fixes below are in the same commit as the work they fix. Every fix has a test that fails without it:
- for M1-M10, the mutant was applied alone, the test was run, and the mutant was reverted;
- for each other fix, the fix's core line was reverted the same way (R1-R15 below).

Each run took the build lock, one at a time, on the shared on-disk target (`/home/moiz/arbx-offload/targets/wp20`).

**Tests after the fixes:**
- `cargo test --release`: **473 passed, 0 failed, 5 ignored**: lib 442 (+4 ignored), bin 13, `tests/campaign.rs` 3, legacy_fixtures 4, meta_config_hash 1, replay_cli 1, runtime_isolation 2 (+1 ignored), stop_path 6, supervisor 1; doc-tests 0. The only warnings are the two pre-existing irrefutable `if let`s in main.rs.
- Toolkit (`tools/arbx-report/tests`, `python3 -m unittest discover -s .`): 86 tests OK, 4 skipped (master has 85; the lane adds `test_wp07.py`). The golden report gains one key, `dup_skipped`.
- `arbx check` exits 0 on `deploy/arbx-canary-frz.toml`, `deploy/arbx-stage0.toml` and `deploy/arb.toml`.

| # | Severity | Disposition | Tests (each fails without the fix) |
|---|---|---|---|
| 1 | Blocker | **Fixed.** Rebased. The ledger's input is now **INPUT 13** `snapshot`; master's `exec_init` keeps 12. MEASUREMENT gives one journal version for both lanes (2.2, same framing). **The money view is journaled at the decision:** the decision-point record (INPUT 3 `src` "decision") carries `money`, the `ledger::MoneyView` the executor decided with (`{equity_known, stale, liquid, wsol, native, rent_recoverable}`). It is written whenever that view differs from the last record. A replay, which has no ledger, applies it in `Exec::stage_seen`, so bankroll-capped sizes, `bankroll_empty`, the rent cap and `equity_stale` replay as decided. `exec::cfg_sha256` now covers `[supervisor] rent_cap_sol`, which the rent cap reads. | `scenarios::exec_replay::a_frz_like_recording_with_the_bankroll_cap_replays_identically`. A shadow executor under the frz canary's bankroll gets frz's 2026-10-05 balances as its start snapshot: 222,956,693 native and 191,524,924 WSOL. Before the snapshot it sizes at 4.2 SOL; after it, every route at 191,524,924. Run and replay give the same decisions, attempts and digests. The same journal without `money` replays at 4.2 SOL and differs (`size_lamports`, `ev`). R1: fails. |
| 2 | Major | **Fixed.** The run's ledger assembly is now `Ledger::for_run`, which `arbx run` calls. The tests below drive what `run()` builds. | **M1** (`require_equity(false)`): `exec::tests::wp07_the_run_loop_arms_the_equity_stops`. It runs the real `Engine::run` with a live executor and `Ledger::for_run`: `equity_unknown` before the first snapshot, `sent` after it; a loss past the floor ends the loop with `equity_floor` (exit 20). **Killed.** **M2** (`acts = false`): `ledger::tests::the_ledger_as_arbx_run_assembles_it_arms_the_stops`. **Killed.** **M3** (the budget refusal removed): `tests/campaign.rs a_sending_start_needs_the_budget`. **Killed.** The run is still refused by the budget state's own check, a second layer. **M4** (SIGKILL removed): `campaign::tests::a_segment_that_ignores_its_stop_is_killed`. SIGINT 60 s and SIGKILL 180 s after an ignored stop; the next segment starts after the kill. **Killed**, with no hang: the stubborn fake child ends on its own 60 minutes later. **M5** (crash limit 100,000): `campaign::tests::more_than_six_crashes_in_15_minutes_end_the_campaign`. **Killed.** **M6** (`filter(\|_\| true)`): `ledger::tests::a_record_the_snapshot_already_holds_is_not_counted_twice`. **Killed.** **M9** (`.min()`): `ledger::tests::the_floor_is_the_highest_candidate`. **Killed.** **M10** (the campaign's budget refusal removed): `a_sending_start_needs_the_budget`. **Killed.** M8 was not run: `the_supervisor_acts_through_the_gate_and_the_stopper` (floor 100, value 99) catches it by construction. M7 is benign, as the review says. |
| 3 | Major | **Fixed.** Snapshots run every `[ledger] snapshot_min` = 10 minutes inside the segment, each asked for up to 30 s early. The money view is **stale** in four cases: (a) its last good snapshot is older than `max_view_age_s` (600, at least `snapshot_min`; the config refuses less); (b) `stale_after_failures` (3) snapshots in a row failed or came back on different slots; (c) a landing the executor found by a status check has waited `max_record_wait_s` (120) for its wallet record (`Exec::oldest_provisional_ns`); (d) the chain-fetch service gave up on a wallet record (`chainfetch::wallet_gave_up_total`). In case (d) a snapshot is asked for at once, and the view stays stale until a snapshot asked for after the give-up lands. **While stale:** the SendGate is in shadow with reason `equity_stale` (not sticky); the executor refuses `equity_stale` (fail closed); an `equity_stale` event and an Error notice go out. **Fresh again:** the gate goes back to live (`SendGate::resume_if`, only from its own reason: a pause is never lifted), with `equity_fresh`. An operator's resume while the view is stale is closed again at the next tick. A shadow or dry run records it only. | `ledger::tests::a_stale_money_view_shadows_the_gate` (every case above, the pause, the resume, the shadow run); `exec::tests::wp07_provisional_money_is_settled_by_its_record` (`equity_stale`); `config::tests::wp07_ledger_and_supervisor_keys`. R3: fails. |
| 4 | Major | **Fixed.** The stops measure the **net spend** from the ledger's categories (`ledger::Entry::spend`). A route: fee + tip + non-recoverable rent − its trading result (its change of SOL + WSOL and of recoverable rent; a token left behind counts 0). Any other transaction: fee + non-recoverable rent. The stop value is the campaign's start SOL + WSOL − the net spend; the floor (start − budget) and the hour and day caps compare it. A deposit extends nothing, and a withdrawal trips nothing. Each transfer is an `owner_transfer`: an event, a Warn notice, the reconciliation's `owner_transfers`, and spend.json's. The token floors follow the routes' token changes only. Campaign history, campaign.json, `campaign-equity`, spend.json (1.1) and BUDGET.md use the same net spend. Documented in `docs/field-tests/README.md` ("Enforcement") and BUDGET.md. | `ledger::tests::owner_transfers_never_move_the_stops`, the review's two traces inverted. After a 100,000,000 deposit, the second 4,500,000 loss trips `equity_floor` on a 5,000,000 budget, with SOL + WSOL at 505.5M. A 25,005,000 withdrawal trips nothing: 5,000 of fee is spend, the transfer is alerted and reconciled. R4: fails. The existing `campaign_stops_across_two_segments`, `the_hour_rule_through_the_ledger` and `the_floor_and_the_token_floor_through_the_ledger` pass on the new basis. |
| 5 | Major | **Fixed.** `<runs>/budget-state.json` (`arbx.budget/1.0`, `src/budget.rs`; on Cherry `/root/arbx/runs/budget-state.json`) keeps the 34,000,000 hard cap and every sending campaign's and manual run's allotment and net spend. **Starts:** `arbx campaign --mode canary/live` and a manual `arbx run --canary/--live` read it with the lock held. An entry that is not final is re-read from its own ledger, so a killed run still counts. A start is refused when nothing is left and gets min(asked, left). **Spend:** a campaign writes its spend after every segment and at its end; a manual run at its end. A file that does not read refuses every sending start. **Manual runs** also take the campaign lock (refused while a campaign runs) and run the other-bot check. A live or canary segment refuses to start unless a campaign supervisor holds the lock (`probe::lock_held`). **Allotments:** the frz config sets `test_budget_lamports = 5000000` (FT-004's allotment); `--test-budget-lamports` can only lower it. `--budget-left` above the hard cap and `--equity-floor` below 0 are refused for sending runs; `set_campaign` and `history` clamp the budget at the cap. The frz config's header points at `arbx campaign`. | `budget::tests::the_hard_cap_is_cumulative` (5M, then 30M left of 34M, then refused; a killed run re-read; an unreadable file refuses); `budget::tests::a_manual_run_takes_the_lock_and_the_budget` (refused beside a campaign and beside arbed's bot; the lock is held for the run's life); `tests/campaign.rs a_sending_start_needs_the_budget` (no budget, over the cap, a negative floor, a campaign without a budget, a spent budget for a run and for a campaign); `config::tests::wp07_ledger_and_supervisor_keys` (5,000,000). R5: fails. |
| 6 | Major | **Fixed.** The executor keeps an immutable `refused` marker on a final that was `not_landed_refused`; an amend never clears it. The amend line carries `first_final` and `refused_then_landed`. `take_refused_landed` hands the attempt over, and `Engine::step` passes it to `Ledger::on_refused_landed` at once. That writes a final recon miss (`kind` `refused_bundle_landed`), puts the gate in shadow (`reconcile_miss`) and sends a Critical notice. `exec_recon` flags any landing with the marker, and across segments an earlier segment's refused attempt even when this segment's record is pre-run. `history` keeps it refused and counts it as a miss. | `exec::tests::wp07_a_refused_bundle_that_lands_is_flagged`: the review's demonstration, in the real order. A refused fire result, then its record to the ledger and then to the executor; the reconciliation flags it. Then through `Engine::step`: the gate is in shadow at once with a Critical notice. Also `ledger::tests::a_refused_bundle_that_landed_is_raised_at_once` and `ledger::tests::the_executors_money_against_the_chain`. R6: fails. |
| 7 | Medium | **Fixed.** At the stop, every pending window is due at once (`final_begin`). One that does not pass is searched (getSignaturesForAddress; the signatures it finds are fetched) and decided again within `recon_grace_s`, while the drain keeps handling the records (`ledger_final_settled`). A snapshot residual still unexplained is written `final: false`, `action` `undecided`, with a `recon_undecided` Warn notice. It is no miss, and the campaign does not go records-only for it. Every recon line now carries `final` and `at_stop`. | `ledger::tests::the_stop_and_the_windows_between_segments_are_reconciled`: in the late-record case, the stop's window is undecided and the next segment decides it with the late record; it passes, and the campaign counts no miss. |
| 8 | Medium | **Fixed** (see #5): the cap and the floor's sign are checked; budgets are clamped. The "highest floor wins" test exists. | `the_floor_is_the_highest_candidate` (the higher, a floor given, a `--budget-left` over the cap read at the cap); `a_sending_start_needs_the_budget`. |
| 9 | Medium | **Fixed.** A segment's first snapshot opens a window from the previous segment's last good snapshot, or from the start of its undecided stop window. The window uses every record of the span: the earlier segments' entries and this segment's pre-run records. It is decided after the grace, with a search: `between_segments`, `from.segment`, `decides`. A miss there shadows the segment and makes the campaign's later segments record only. The window's executor part lists the earlier segments' refused attempts that landed. | `the_stop_and_the_windows_between_segments_are_reconciled`, no-record case: 50,000 lamports left between the segments with no record, and it is a miss. |
| 10 | Medium | **Deferred, listed.** PLAN WP-07 "As built" and MEASUREMENT A.1 say that `venue_quarantine` is not raised. A venue upgrade is recorded (programdata role). The reason it can wait: the route program's on-chain guard reverts a route below its `min_profit`, and a bundle that reverts does not land. | none |
| 11 | Minor | **Fixed.** The toolkit's `Segment.ledger` leaves out `dup` lines (`ledger_dup` has them; the money report, `r1_money`, gives `dup_skipped`), so the campaign roll-up counts each once. The golden report gains `dup_skipped`. | `tools/arbx-report/tests/test_wp07.py`; the golden report regenerated (one new key). |
| 12 | Minor | **Fixed.** `decide_inner` refuses `r.size > size_cap()` with reason `size_cap`. The executor tests' routes are now 0.05 SOL, within every cap they set. | `exec::tests::wp07_bankroll_rent_cap_and_canary_count`: a 60M route above a 55M bankroll is `size_cap`. R12: fails. |
| 13 | Minor | **Fixed.** A stop rule requests the stop before its notice. `notify` runs the hook inside `catch_unwind` (`HOOK_PANICS` counts the panics). The process's panic hook ignores a panic raised inside the alert hook (`notify::in_hook`), so it never becomes the run's `panic` stop. | `supervisor::tests::the_stop_comes_before_its_notice_and_a_panicking_hook_loses_nothing`, through the real global hook: the stop is already requested when the hook runs, and the hook's panic loses nothing. R13: fails. |
| 14 | Minor | **Fixed.** `probe::is_bot_run` also matches arbed's bot (`bun bin/arbed.ts run …`, the pm2 app `arbed-live`, on the same frz keystore and Haan token). On a `try_wait` error the segment is stopped and waited for (stop, SIGINT, SIGKILL). If it still cannot be reaped, the campaign ends: `safety: segment … could not be reaped`, a Critical `segment_unreaped`, exit 20. No segment ever starts beside it. The FT protocol says one bot on frz at a time. | `probe::tests` (arbed's command lines); `campaign::tests::a_segment_that_cannot_be_reaped_ends_the_campaign`. |
| 15 | Minor | **Fixed.** `wallet::Pass` holds the passphrase in one page-aligned, mlock'd page (4,096 bytes). **Reading:** with read(2), one byte at a time, from stdin when it is piped (`arbx campaign`'s pipe to a segment, `ssh … < pass`), or from /dev/tty with echo off (a terminal whose echo cannot be turned off is refused). Nothing past its newline is consumed, and it never passes through std's stdin buffer, a `BufReader` or a growing `String`. A longer one is read to its newline, then refused. **Going:** it is wiped with volatile writes and unlocked. A detached campaign locks the page again after the fork, since a child does not inherit memory locks. **The keys:** the scrypt key is a `Key` wiped on every path, an early return included (v3, v2, the unversioned blobs and `encrypt`). The AES key schedule, whose first two round keys are the key itself, is wiped through the `aes` crate's `zeroize` feature (one Cargo.toml line, no new crate). The decrypted secret key (`SecretText`) and its decoded bytes are wiped too, in the profile-keystore path that frz uses as well. **Not covered:** the scrypt crate's own work buffers, which are freed, not wiped. The process stays non-dumpable, with no core. | `wallet::tests::a_piped_passphrase_is_read_into_a_locked_page`, through a real pipe: the first line, its `\r` dropped, the next line still in the pipe; VmLck 4 kB higher while it lives and back after; the page all zeros after the wipe; an empty line refused; 4,096 bytes accepted, 4,097 refused with the next line still there. R15 (no mlock) and R15w (no wipe): fail. `wallet::tests::arbeds_v2_and_unversioned_blobs_decrypt` takes both of arbed's formats through the new key; `decrypts_the_offline_scripts_keystore` and `v3_round_trip` still pass. |
| 16 | Minor | **Fixed.** PLAN WP-07 has an "As built" block: the net-spend stops, 0.02 SOL/h as a campaign stop, `arbx campaign` on Cherry, the passphrase, the replay, the deferral. BUDGET.md and the FT README are merged with master's F6 text and updated (#3, #4, #5, #14). The data files the config names are hashed into campaign.json `data_files` and checked before every segment (`data_files_changed`, Warn). | `campaign::tests::a_data_file_changed_mid_campaign_is_reported`. |

**The fix-reverting runs.** Each revert was applied alone, then `cargo test --release --offline --lib -- <test> --exact` ran under the build lock, then the file was restored byte for byte (sha256 checked). All of them ran on the lane rebased onto `20f6812`, with #15 in.

| Run | Fix | Reverted | Test | Result |
|---|---|---|---|---|
| R1 | #1 | `g["money"] = seen.5.json();` removed (src/engine.rs): the decision-point record without the money view | `scenarios::exec_replay::a_frz_like_recording_with_the_bankroll_cap_replays_identically` | **Fails** at exec_replay.rs:300: no decision record carries `money`. The test's second half strips `money` from a journal and shows the replay then sizes at 4.2 SOL and differs. |
| R3 | #3 | `self.freshness(t, &tin);` removed from the ledger's tick (src/ledger.rs) | `ledger::tests::a_stale_money_view_shadows_the_gate` | **Fails** at ledger/tests.rs:733: 10 minutes and a second after the last good snapshot, the view is not stale. |
| R4 | #4 | `Entry::spend` of a non-route = its change of equity (src/ledger.rs): the owner's transfers counted as spend | `ledger::tests::owner_transfers_never_move_the_stops` | **Fails** at ledger/tests.rs:676: the 100,000,000 deposit is −100,000,000 of spend, and the stop value is 514,500,000. That is the review's finding: the deposit extends the floor. |
| R5 | #5 | `State::remaining` = the hard cap (src/budget.rs) | `budget::tests::the_hard_cap_is_cumulative` | **Fails** at budget.rs:181: the second campaign gets 34,000,000 again, not the 30,000,000 left. |
| R6 | #6 | `refused: false` in the executor's final (src/exec.rs `finalize`) | `exec::tests::wp07_a_refused_bundle_that_lands_is_flagged` | **Fails** at exec/tests.rs:1611: the refused final carries no marker. |
| R12 | #12 | the `size_cap` check removed from `decide_inner` (src/exec.rs) | `exec::tests::wp07_bankroll_rent_cap_and_canary_count` | **Fails** at exec/tests.rs:1528: the 60M route above the 55M bankroll is `sent`. |
| R13 | #13 | a notice sent before the stop request (src/supervisor.rs) | `supervisor::tests::the_stop_comes_before_its_notice_and_a_panicking_hook_loses_nothing` | **Fails** at supervisor.rs:475: the hook ran once before the stop was requested (`[("equity_floor", false), ("equity_floor", true)]`). Both hook panics were caught. |
| R15 | #15 | `p.lock()?` removed from `Pass::new` (src/wallet.rs): the page is never mlock'd | `wallet::tests::a_piped_passphrase_is_read_into_a_locked_page` | **Fails** at wallet.rs:391: "the page is locked: 0 kB, 0 kB before". |
| R15w | #15 | the wipe removed from `Pass::clear` (src/wallet.rs) | the same test | **Fails** at wallet.rs:394: the page still holds the passphrase ("wiped"). |

**The demonstration tests of the appendix.** Each was turned into a test of the fixed behaviour; none asserts the old behaviour:
- `review_deposit_extends_the_floor` and `review_owner_withdrawal_is_a_safety_stop` → `owner_transfers_never_move_the_stops`;
- `review_stale_money_view_keeps_the_gate_open` → `a_stale_money_view_shadows_the_gate`;
- `review_late_record_at_stop_is_a_campaign_miss` → `the_stop_and_the_windows_between_segments_are_reconciled`;
- `review_the_floor_is_the_highest_candidate` → `the_floor_is_the_highest_candidate`. Its numbers changed: this segment's own start is the stop value then, 414.5M − 5M, so its candidate is 389.5M;
- `review_a_refused_bundle_that_lands_is_never_flagged` → `wp07_a_refused_bundle_that_lands_is_flagged`.

**What FT-004 still needs (not code of this lane):**
- **Go-live gate items 3 and 4 on this build.** A shadow soak of at least 3 h with Haan alone, whose 1 h recording replays identically (the frz-like replay here is a scenario, not a field recording), and the dry run of at least 100 would-sends.
- **WP-06.** The go-live gate's item 1 lists it among the work packages committed with reviews. Without it, FT-004 can trade only routes whose token accounts frz already holds (WSOL, USDC).
- **Seed the budget state.** `budget-state.json` does not exist on Cherry yet: the first sending start creates it with 0 spent, as BUDGET.md says today (no live test). Any earlier spend must be entered by the owner before FT-004, or it is not counted.
- **Keep the frz key to one process.** Stop arbed's bot (`pm2 delete arbed-live`) and any other process on the frz key while a test runs. The other-bot check refuses on what it can see, which is processes on Cherry.
- **The alerts.** WP-20's Telegram sink is not wired: the notices go to events.jsonl and to the `notify` hook point only.
- **The segment length.** Two 30-minute segments are no longer needed: snapshots now run every 10 minutes inside a segment. They do no harm.

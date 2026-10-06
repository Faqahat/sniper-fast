# WP-06 review: builder (rent-neutral, measured CU, DLMM-safe, size-budgeted, tipped by band)

**Date:** 2026-10-06. **Reviewer:** adversarial review. I changed no repository code. I applied six mutants one at a time in the master tree, ran the relevant tests under the build lock, and reverted each one, checking sha256 after every revert. For one run I added a temporary integration test file (`tests/zz_review_wp06_verify_mutants.rs`) and removed it afterwards. This document is my only output file.

**Plan:**
- `docs/PLAN.md` WP-06: items 1-9, config keys, offline acceptance, measurement outputs.
- `docs/PLAN-ADDENDUM.md`, go-live gate item 2 (amended 2026-10-05): "New token accounts only through WP-06's rent-neutral create+close inside the same atomic transaction ... nothing stays locked". Also gate item 4 (the send dry run).
- `docs/STAGE1-PLAN.md`: §3 create+close lever, §6 budget and owner decisions.
- `docs/MEASUREMENT.md`: revision 2.11, as edited by this diff.
- The lane/wp-07 canary config `deploy/arbx-canary-frz.toml` (draft).

## What was reviewed

- **The diff:** the uncommitted WP-06 work on HEAD `20f6812`.
  - 34 modified files, +2,023/−402.
  - 7 new files: `src/tip.rs`, `src/cu_table.rs`, `src/scenarios/s10_rent.rs`, `data/cu-table.json`, `testdata/builder/bundle-vectors.json`, `program/venue-harness/tests/arbx_bundle.rs`, `program/venue-harness/results/arbx-bundle-runs.json`.
  - `.claude/worktrees` was ignored.
- **Snapshot at the start:**
  - `git diff`: sha256 `9360117734aa152afae0a092e04e43bcab335d15b0c4fca705ea12acf0332f42`.
  - The new files: `src/tip.rs 55120b73…`, `src/cu_table.rs c3e68800…`, `src/scenarios/s10_rent.rs 3384ec4e…`, `data/cu-table.json 9b39298d…`, `testdata/builder/bundle-vectors.json f6725333…`, `program/venue-harness/tests/arbx_bundle.rs 8fdbf795…`, `results/arbx-bundle-runs.json 3273b09c…`.
  - Both hashes were unchanged after every mutant and at the end. The harness rewrites `results/arbx-bundle-runs.json`, and its output was byte-identical to the file before the run.

## Verdict

**One blocker (the default config), four majors, seven minors. Do not run the frz canary on this as it stands. WP-06 can merge once findings 1 and 2 are fixed; both fixes are small. Findings 3 and 4 must be settled at the WP-07 merge, before FT-004.**

The rent-neutral core holds on the real programs, and I could not make it lose money:
- **Instruction order.** The order is CU limit > loaded-data limit > [CreateIdempotent] > route > [CloseAccount to the payer] > tip.
- **Rent.** The close sends every lamport of the account it created back to the payer, after the route and in the same transaction.
- **min_profit.** It covers the tip, the base fee and the margin floor.

I reproduced the venue harness. In LiteSVM, on the dumped mainnet programs and the deployed nexus-v2 ELF:
- the payer's native balance moves by −105,000 lamports (fee + tip) and nothing else;
- the rent locked equals the rent reclaimed: 1,513,840 lamports for Token-2022, 1,488,440 for SPL;
- the CU used stays within every allowance;
- an unreachable min_profit fails with 0x4e580002, and nothing it did stays.

Of 26 mutations of a real signed vector, `verify_bundle` caught every change to the tip, the create, the close, the order, the route amounts and the CU price.

What is wrong is around that core:
- **Finding 1.** The default config enables a fallback that creates a token account and keeps it. This locks rent that min_profit does not cover, and it contradicts the go-live gate.
- **Finding 2.** The dry run's rent check takes the "close or keep" decision from the builder itself. A builder that never closes passes every check.
- **Finding 3.** Nothing tests the per-trade size cap, and the executor does not check it.
- **Finding 4.** The lane/wp-07 canary config will not load after this merge, and the two lanes' bankroll hooks are incompatible.

## Findings

### 1. Blocker (canary config; go-live gate item 2): the held-ATA fallback is on by default and locks rent that min_profit does not cover

**Location:**
- `src/exec.rs:1303-1309` (`Exec::build`), `:991` (`held_growth_ok`), `:463-466` (`min_profit_onchain`: "Rent is never part of it").
- `src/config.rs` `held_max() = 40`.
- `deploy/arbx-stage0.toml` `[builder] held_max = 40`. The lane/wp-07 canary config has no `[builder]` section, so it gets the default 40.
- `src/main.rs:846` (`limits_json` `"rent_neutral": true`).

**Problem:**
- The size budget's third step builds the bundle with the create and without the close: `if ata.is_some() && self.held_growth_ok() { … close: false … }`. It does this whenever create+close is over 1,232 bytes and the version without the close fits.
- The kept account's rent leaves the payer's native SOL: 1,488,440 lamports for an SPL account, 1,513,840 for Token-2022.
- The route's on-chain min_profit is only tip + 5,000 + margin, and the margin floor is 1 (`margin_floor = 1`, `margin_share = 0.0`). So a landed held addition can net a few lamports of WSOL while 1.5M lamports of liquid SOL go into an account. Getting that SOL back needs a manual close.
- Up to `held_max` = 40 such additions per run means up to 60,553,600 lamports (0.06 SOL) locked:
  - 1.8 times the owner's whole test-budget hard cap of 34,000,000;
  - about 15% of frz's 0.414 SOL of liquid SOL.
- Nobody decided this:
  - The go-live gate (owner, 2026-10-05) says new token accounts come "only through … rent-neutral create+close … nothing stays locked".
  - STAGE1-PLAN's owner decision 2 ("held-set size N for FT-003") is about wallet prep, not about additions made automatically while trading.
- `meta.json` `limits.rent_neutral` says `true` even when held additions are enabled.

**Proof:**
- Code above. `exec::tests::the_size_budget_ladder` builds a `held_ata` bundle (`creates_ata && !closes_ata && held_addition`), and it signs and passes the dry run's checks.
- The close is 7 bytes (program index, account count, 3 account indexes, data length, data). So this path fires only for bundles 1-7 bytes over the limit after the index tables. Such bundles exist: arb-lab's copies reached 1,209 of 1,232 bytes (R §3.5). Create+close adds about 50 bytes, and no config sets `[exec] alts` (finding 14).

**Fix (any one of these):**
1. Default `held_max = 0`, and set 0 in `arbx-stage0.toml` and the canary config, until the owner chooses N.
2. Or add `[builder] held_ata = false` (opt-in).
3. Or let a held addition through only when min_profit also covers the rent (min_profit += the rent-exempt minimum of the account), and count additions still in flight in `held_growth_ok` (finding 5).

`limits_json` should report `rent_neutral` as `held_max == 0`.

### 2. Major (gate item 4): the dry run's rent check mirrors the builder, so a builder that never closes passes; the CU and loaded-data checks are tautological

**Location:**
- `src/exec.rs:1270` (`Exec::want`):

  ```rust
  ata: (!held).then_some(build::AtaOps { mint: r.mint, token_program: r.mint_prog, close: !built.held_addition() }),
  ```

- `:1267` (`cu_limit: built.cu_limit`) and `:1271` (`loaded_data_limit: built.loaded_data_limit`).
- `verify_bundle` `:2391-2411`.

**Problem:**
- `want()` should be built from the decision, never from the built message (review WP-05 #12). For the close it is not: whether a close is required comes from the build itself. A build without the close looks like a "declared held-set addition", and `ix_order`, `ata_close` and `rent_returns` all accept it.
- The same holds for `cu_limit` and `loaded_data_limit`: they compare the signed bytes with the build's own numbers. A CU-model or loaded-data regression passes the dry run, and shows up only as would-fails.

**Proof:** mutant M1 below drops the close: `close: true` → `close: false` at `exec.rs:1295`.
- Nine unit tests fail, but only on their own `closes_ata` asserts. The dry-run checks inside them pass:
  - `rent_neutral_create_and_close` passes its `checks_ok == true` assert (tests.rs:1535) and fails at :1536 on `closes_ata`;
  - `the_held_view_comes_from_the_store` records `(creates_ata, closes_ata, checks_ok) = (true, false, true)`;
  - both S10 scenarios record every bundle as `(true, false, true, USDC)`.
- In the vector experiment below, `no_close_with_want_close_false` fails 0 checks.

The go-live gate's dry run ("≥ 100 would-send bundles … accounts checked") would report a build that locks rent on every trade as clean.

**Fix:**
1. Require the close unless the size budget declared the fallback: `close: built.alt_fallback != "held_ata"`.
2. Add a check `held_addition_justified`: the same bundle compiled with the close is over 1,232 bytes or 64 locks, and `held_growth_ok()` holds.
3. Compute the expected CU limit (`min(r.cu + cu_ata.0 + cu_ata.1, MAX_CU)`) and the expected `loaded_data_estimate` in `want()` independently of `Built`.
4. Have the dry run's summary count held additions.

### 3. Major (exposure limit; test gap): the per-trade size cap has no test and no executor-side check

**Location:**
- `src/engine.rs:2166-2169`: `let cap = … size_cap_for(&bankroll); … self.route_in(id, size.min(cap))`.
- `src/exec.rs` `decide_inner`: no size check.
- `verify_bundle`: `route_amount_in` compares the signed amount with the decision's own size.

**Problem:**
- The only thing that keeps a trade at or below `[live] max_size_sol`, `[canary] size_sol` and (after WP-07) the bankroll cap of go-live gate item 2 is `.min(cap)` in the engine. Nothing tests it.
- The executor signs whatever size it is given.

**Proof:** mutant M4 makes the call uncapped (`size.min(cap.max(u64::MAX))`). **All 445 tests still pass.**

**Consequence today:** limited. A landed bundle still cannot lose, because min_profit is checked on chain, and a size above the WSOL held only fails, which is free. But it is the owner's exposure limit, and WP-07's bankroll cap plugs into exactly this line.

**Fix:**
- In `decide_inner`: `if r.size > self.size_cap_for(…) { return fail(d, "size_cap") }`. lane/wp-07 already has this line (review WP-07 #12); keep it through the merge.
- Add a test: a canary cap below the engine's chosen size, and every attempt's `size_lamports` ≤ the cap.

### 4. Major (merge with lane/wp-07): the frz canary config will not load, and the two bankroll hooks conflict

**Location:**
- lane/wp-07 `deploy/arbx-canary-frz.toml`:
  - `:282-283` (jito-bundle `tip_share = 0.7`, `tip_max_lamports = 100000`);
  - `:397` (`[live] max_new_token_accounts = 0`);
  - no `[tips]` or `[builder]`.
- lane/wp-07 `tests/campaign.rs:100` (`the_frz_canary_config_passes_arbx_check`), `src/config.rs:436` (`max_new_token_accounts`), `src/exec.rs:889-896` (`size_cap()`, `bankroll_cap(&self)`).
- WP-06: `src/config.rs` (the `moved to [tips]` bail, the `deny_unknown_fields` LiveCfg), `src/exec.rs:982-986` (`size_cap_for(&Bankroll)`, `bankroll_cap(&self, _b: &Bankroll) -> None`).

**Problem:**
1. After WP-06, the canary config refuses to load, twice over:
   - "send path jito-bundle: tip_share and tip_max_lamports of a jito-bundle path moved to [tips]";
   - "unknown field `max_new_token_accounts`".

   This fails closed, so no money is at risk. But lane/wp-07's own CI test of that file fails, and FT-004 cannot start.
2. The two lanes add different bankroll hooks.
   - WP-06 hands the executor a store-derived `Bankroll` (journaled) and returns no cap.
   - WP-07 reads its ledger's money view, has its own `size_cap()`, and still carries `max_new_atas` and the old held logic.
   - Both rewrite `decide_inner`, `ExecInit`, `Open`/`Final` and the held set. A careless merge could keep the dead WP-06 hook and lose WP-07's size check (finding 3).
3. With no `[builder]` section, the canary gets:
   - `held_max = 40` (finding 1);
   - `cu_table = "data/cu-table.json"`, a relative path, so it depends on the process's working directory on Cherry. The run refuses to start without the file (finding 11).

**Fix:** at the merge:
- remove the three keys from the canary config;
- add `[tips]` (`shares = [0.7, …]`, `floor = 1000`, `cap = 100000`: the status quo, as this config's comments already state);
- add `[builder]` with `held_max = 0` and the absolute path `/root/arbx/data/cu-table.json`;
- choose one bankroll source, journaled, and keep WP-07's executor-side `size_cap` refusal;
- update the canary config's header (it still says "USDC routes only until WP-06").

### 5. Minor (test gap): the held set's growth after a landed held addition is untested, and additions in flight are not counted

**Location:** `src/exec.rs:1686` (`Exec::add`: `self.held.insert(mint)`) and `:991` (`held_growth_ok`).

**Proof:** mutant M5 deletes the `self.held.insert(mint)`, so the set never grows and `held_max` never binds within a run. All 417 lib tests pass.

**Also:** `held_growth_ok` counts only landed additions. Several attempts in flight for different mints can each be built as `held_ata` and push the set past `held_max`.

**Fix:** add a test (a held addition lands, then the next one is `oversized` at `held_max`), and count open attempts with `held_addition` in `held_growth_ok`.

### 6. Minor (unverified acceptance): the venue harness does not validate `loaded_data_limit = "auto"`, and the canary ships `simulate = false`

**Location:**
- `program/venue-harness/tests/arbx_bundle.rs`.
- LiteSVM 0.17.0 `src/lib.rs:1300-1376`.
- `src/build.rs:453-492` (`PROGRAM_BYTES`, `loaded_data_estimate`).
- The canary config's `[dry_run] simulate = false`.

**Problem:**
- LiteSVM's loaded-size accounting counts 8,248 per table plus 64 + data for each account in the message. It does not add the ProgramData of upgradeable programs, which mainnet's SIMD-0186 accounting does: PumpSwap's alone is 10.5 MB.
- The harness's pass therefore proves only that the 20,185,088-byte limit of vector 0 is above LiteSVM's count, which is roughly 0.2 MB of accounts. A limit 50 times too small would pass it too.
- The estimate itself does include ProgramData, and I estimate about 25% headroom for vector 0. So the estimate is probably right, but it is unproven. If it were wrong, every bundle would fail (`MaxLoadedAccountsDataSizeExceeded`): free, but the canary would land nothing.
- The ProgramData sizes are constants. An upgrade that grows PumpSwap's ProgramData by more than the margin makes every PumpSwap bundle fail.

**Fix:**
- Run FT-002's dry run with `simulate = true` on each route kind: PumpSwap, DLMM, CPMM, AMM v4 and DAMM v2, with SPL and Token-2022 mids.
- Or read the ProgramData sizes from the store, since they are already followed for upgrade detection.

### 7. Minor (defence in depth): `verify_bundle` does not look inside the legs

**Location:** `src/exec.rs:2365-2368` (`route_accounts`).

**Problem:**
- The route check covers the authority, the quote account, each leg's output account, its program, and that its pool is named.
- It does not cover the user token accounts each venue instruction names (source and destination), the writable and signer flags, or the leg data beyond the route's amount_in and min_profit.

**Proof:** four vector mutations fail 0 checks (table below):
- leg 1 spends from the payer's USDC account;
- leg 2 delivers WSOL to a foreign account;
- the mid account is made read-only;
- the leg-1 discriminator is flipped.

On chain each of these fails, through the venue's mint checks, the route's min_profit on the quote account, or the runtime's writability rules. So none can land at a loss of WSOL.

A wrong source account is the one way a builder bug could spend a payer token account that min_profit does not watch: frz's 22.97 USDC.

**Fix:** check that the only payer-owned token accounts the legs name are the quote ATA and the mid ATA, at the venue's user positions.

### 8. Minor (measurement): a what-if `--set tips.*` replay changes the engine's fee, not the executor's tip

**Location:**
- `src/replay.rs` `apply_sets`: the WP-06 block edits `EngineInit.builder` only.
- `build_engine` → `Exec::offline(&inp.cfg, ei, …)`.
- `src/exec.rs:1837` (`x.tips = init.tips.clone()`).

**Problem:**
- With `--set tips.shares=[0.35,…]`, decisions' `net` uses 0.35.
- The replayed executor still tips, sets min_profit and makes would-send verdicts at the run's 0.7.
- An X4 analysis done through replay would mix the two.

**Fix:** apply `tips.*` (and `min_tip`) to the offline executor's `TipPolicy.model`, or refuse those keys when the executor is replayed.

### 9. Minor (rollout control): nothing can turn create+close off

**Location:** `src/config.rs` (`[live] max_new_token_accounts` removed; `[builder]` has no switch).

**Problem:**
- WP-00's `max_new_token_accounts = 0` was the way to trade held tokens only.
- STAGE1-PLAN §3.1 tests create+close against a held-only control arm, and a first live hour may want held-only.
- `held_max = 0` disables only the held-ATA fallback, not create+close.

**Fix:** add `[builder] create_close = true|false`, with a recorded refusal reason such as `mid_not_held`, or make it WP-11's arm hook.

### 10. Minor (replay): an engine_init `builder` that does not read replays silently with the legacy fee rule

**Location:** `src/engine.rs:524`: `builder: serde_json::from_value(v["builder"].clone()).ok()`.

**Problem:**
- A key that is present but unreadable (a later schema, a corrupt record) becomes `None`.
- The replay then prices with 5,000 + `cu_price_micro` × CU + `min_tip` instead of the run's model, and reports no error.

**Fix:** `None` only when the key is absent or null; otherwise return an error.

### 11. Minor (operations): the run needs the CU table file at start

**Location:**
- `src/main.rs` (`BuilderModel::from_cfg` → `CuTable::load`: a run without the file refuses to start);
- `src/config.rs` (`cu_table_path() = "data/cu-table.json"`, relative);
- `docs/field-tests/README.md:32` (the Cherry upload list names the seed list, registry, templates, crowded-pools, validators-meta and ip-geo).

**Problem:** this fails closed, which is right. But `data/cu-table.json` has to be uploaded to Cherry, and a config without `[builder]` resolves the path from the working directory.

**Fix:** add the file to the upload list, and use the absolute path in every deploy config (see finding 4).

### 12. Info: the cashback "UVA WSOL account" residual risk is closed upstream; refuse it in the builder too

**Location:** `src/build.rs:179`; `program/arbx-sizing/src/venue/pumpswap.rs:176`.

**What I found:**
- `pump_leg` would name the user volume accumulator's WSOL account on a cashback pool without pool_v2. The program could create that account at the payer's expense, and we could not reclaim it.
- No route can reach it: arbx-sizing refuses every cashback pool (`Abort::Pump(Cashback)` → `sz_pump_cashback`), and `route_in` prices through the crate.

**Fix (defence in depth):** have `pump_leg` itself refuse `cashback && !has_v2`.

### 13. Info: `uva_missing` keys on the buy leg's venue

**Location:** `src/exec.rs:1119`.

**What I found:** the check is correct only because a PumpSwap route leg must quote in WSOL (`pump_quote_not_sol`, `src/quote.rs:258`). That makes the PumpSwap buy always the first leg.

**Fix:** key the check on the leg's direction (a PumpSwap `buy` on either leg).

### 14. Info: no config sets `[exec] alts`

**What I found:**
- A PumpSwap + DLMM create+close bundle fits in 1,232 bytes only through a lookup table learned from decoded transactions (`alt_index`).
- `the_size_budget_ladder` shows the worst-case route is `oversized` with the `[exec]` tables alone.
- This is not a regression, but PLAN's size acceptance ("worst-case 2-leg routes … with create and close fit") holds only with such a table.
- X6 will measure how often one exists.

### 15. Info: an SPL-mint create+close through arbx's builder is not executed by the harness

**What I found:**
- The harness runs arbx's own bundles for HOTBOT, a Token-2022 mint.
- Its SPL case is a hand-built create+close of USDC with no route.
- The close is the same instruction, so the risk is low.

**Fix:** add an SPL-mid vector.

### 16. Info: `allow_uva_create = true` would let the first PumpSwap buy lock 1,346,200 lamports that min_profit does not cover

**What I found:** the flag ships `false`, and frz already has a user volume accumulator (`CUiyUSbx…`, per the canary config).

**Fix:** if the accumulator is ever needed, create it in a separate wallet-prep transaction, as the harness does with `pump_init_user_volume_accumulator`, rather than inside a trade.

### 17. Info: other observations

- `dlmm_cap` is recorded as the per-route flag `dlmm_cap_bound`, not as a reason. PLAN item 6 lists it as a reason; MEASUREMENT A.1 documents the flag.
- `deploy/legacy/arb-w-live.toml` still has the removed keys. It is legacy and arbx does not load it.
- The build gives no new warnings. There are 2 pre-existing ones, irrefutable `if let` at `main.rs:546` and `:554`.

## Money: what I tried to break

| Attack | Result |
|---|---|
| A landed bundle that loses | min_profit = tip + 5,000 + margin (`exec.rs:463-466`); the executor's bar is tip + 5,000 + `margin_lamports`; `verify_bundle` `min_profit_covers_tip` sums every System transfer from the payer. Mutant M6 (no base fee) is caught by 12 tests. The only outflows min_profit does not cover are a held addition's rent (finding 1), the accumulator when allowed (finding 16), and venue-side account creation by CPI. I saw none of the last: the harness moves native by exactly −105,000, and the old bot's rent residuals were only ATAs and the accumulator |
| A create without its close, a close to the wrong account, a close before the route | The builder is correct (`bundle_ixs`, build.rs:427-435). The golden order test and the harness pass. M2 (close before the route) is caught by 9 tests including `verify_bundle`. M1 (no close) is caught by unit tests only (finding 2). Every vector mutation of the close is caught |
| Token-2022 extensions | A transfer fee (older or newer bps nonzero) and a transfer hook (program set) are refused by arbx-sizing at boot (`pools_dropped`) and again at every quote, because Token-2022 mints are followed as pool parts. The other extensions (frozen default state, non-transferable, pausable) can only make the route fail, which is free. CloseAccount returns every lamport, whatever the account's size |
| The cashback and accumulator rent path | Unreachable (finding 12). `uva_missing` fails closed when the accumulator is unknown, and the store's view overrides the boot read (tests, S10) |
| Tips above what a band allows | tip = clamp(⌊share × edge⌋, floor, cap); shares are checked to be in 0..1; floor 1,000 ≥ Jito's minimum and ≥ the path's `tip_lamports` (a config check); cap 100,000. Decisions, the queue and the tip use the same configured band table. Stage-0 tips equal WP-05's to the lamport (`tip_clamp_table`). M3 (the band below's share) is caught by 3 tests. It is invisible in the Stage-0 config, where every band is 0.7 |
| A CU limit too low or too high | Fallback route 212,000 + create 30,000 + close 5,000 = 247,000, against 170,507 used (harness, Token-2022). Create used 18,616 (Token-2022) / 14,917 (SPL) of 30,000; close used 1,464 / 120 of 5,000. At CU price 0 the limit costs nothing, and running out of CU only fails the bundle |
| A size above the cap or bankroll | Finding 3 |

## Claims check

| Implementer's claim | Result |
|---|---|
| `cargo test --release`: 445 passed, 0 failed, 5 ignored | **Reproduced**: lib 417 (4 ignored), bin 13, legacy_fixtures 4, meta_config_hash 1, replay_cli 1, runtime_isolation 2 (1 ignored), stop_path 6, supervisor 1 |
| Harness `arbx_bundles_are_rent_neutral_on_the_real_programs` passes: native −105,000, locked = reclaimed (1,513,840 / 1,488,440), CU within limits, 0x4e580002 | **Reproduced**, and `results/arbx-bundle-runs.json` was byte-identical. Caveats: the SPL case is standalone (finding 15); the loaded-data limit is not validated (finding 6) |
| Instruction order CU limit > loaded-data limit > [create] > route > [close to payer] > tip | **Verified** (code, golden test, harness, M2) |
| `verify_bundle` adds ix_order, loaded_data_limit, ata_create, ata_close, rent_returns, route_guard | **Verified present.** The rent check mirrors the build (finding 2) |
| `uva_missing` refusal | **Verified** (exec.rs:1116-1120, `uva_missing_refuses_pumpswap_buys`, S10) |
| Tips by band (`src/tip.rs`) | **Verified**; M3 is caught |
| CU model; the interim table has no samples, so the fallback applies | **Verified**: `legs: {}`, overhead n 0, so every route is `fallback`; ATA create and close are 30,000 / 5,000 |
| DLMM arrays capped through the shared `quote::dlmm_window` | **Verified**: the quote's route walk and `build::dlmm_arrays` both draw from it; the builder names the window up to the end bin's array plus one buffer; walked arrays outside −512..=511 without the extension are `dlmm_ext_needed` |
| Size ladder plain → alt_index → held_ata → oversized | **Verified** (exec.rs:1296-1310). held_ata is finding 1 |
| Bankroll hooks for WP-07 | **Present**: `Bankroll` comes from the store and `bankroll_cap` returns `None`. Incompatible with lane/wp-07's hook (finding 4) |
| Replay determinism (exec_init v2, builder journaled, the synthetic shadow replay identical) | **Verified by the tests**. engine_init carries `builder` (the CU table's contents included); exec_init v2 carries `tips` and `uva`; the store keeps `lamports` from journaled records; `[builder]`/`[tips]`/`[bands]` are in `cfg_sha256`, which a replay must match; index tables are rebuilt from journaled ALT inputs (`preload_alt`, `learn_alts`, `on_alt` all index). Exceptions: findings 8 and 10 |
| Defaults: tips 0.7 in every band, contested [0.16, 0.47, 0.54, 0.64, 0.64], floor 1,000, cap 100,000; bands [20k, 100k, 1M, 10M]; held_max 40, allow_uva_create false, payer_guard false | **Verified** (config.rs defaults, `wp06_builder_keys`, deploy configs). held_max 40 is finding 1 |
| Residual risk: cashback pools without pool_v2 can create the accumulator's WSOL account | **Closed upstream** (finding 12) |

## PLAN offline acceptance

| Item | Status |
|---|---|
| Golden byte tests of the order with and without create/close; encodings of `close_account_ix` and `loaded_data_limit_ix`; `legs_match_arbed`, `v2_data_layout` | Pass (`bundle_instruction_order_golden`, `close_account_and_loaded_data_limit_encodings`) |
| Guard trailer = nexus-v2 `encode_guarded` | Pass (`guard_trailer_matches_nexus_v2_encode_guarded`, from the program's own fixture) |
| DLMM cap and the extension rule | Pass (`dlmm_arrays_capped_and_the_extension_rule`, quote tests) |
| CuTable aggregation, lookup and fallback; bands; tip clamp | Lookup, fallback, bands and clamp pass. The per-leg aggregation is the toolkit's (`cu_table.py`), and the shipped table has no samples |
| Worst-case PumpSwap buy + DLMM sell with create and close fits in 1,232 bytes | Only with an index table (`the_size_budget_ladder`; finding 14) |
| Field acceptance (X6 ≥ 99% fit; `rent_recoverable_now` flat; CU-exhaustion and 0x1794 would-fails to 0) | Owner-run, not yet. Finding 1 would break "flat" |

## `verify_bundle` on mutations of a real signed vector

Method:
- A temporary integration test decoded `testdata/builder/bundle-vectors.json` case 0 (`pump_buy_dlmm_sell_create_close`: PumpSwap GLL3 buy, DLMM 6D4E sell, HOTBOT Token-2022 mid, create+close, its lookup table).
- It rebuilt the instructions from the signed bytes and checked that recompiling them reproduces the vector byte for byte.
- It applied each mutation, recompiled, re-signed with the vectors' test key, and ran `verify_bundle` against the `VerifyWant` the vector describes: its tip, min_profit, CU limit, loaded-data limit and `ata` with `close: true`.
- The file was removed after the run.

| Mutation | Checks that fail |
|---|---|
| none (baseline) | — (all pass) |
| tip × 10 | tip_last, tip_to_jito, min_profit_covers_tip |
| tip to another Jito tip account | tip_last |
| close destination = the WSOL quote account / the tip account / a foreign account | ata_close, rent_returns (each) |
| no close | ix_order, ata_close, rent_returns |
| close before the route | ix_order, rent_returns |
| tip before the close | tip_last, ix_order |
| an extra 1 SOL transfer to a foreign account | min_profit_covers_tip, ix_order |
| the tip paid twice | tip_to_jito, min_profit_covers_tip, ix_order |
| route min_profit = 1 | route_min_profit, min_profit_covers_tip |
| route amount_in × 2 | route_amount_in |
| create under SPL Token (Token-2022 mint) | ata_create, rent_returns |
| close through SPL Token | ata_close |
| a CU price added | no_cu_price, ix_order |
| CU limit 10,000 | cu_limit (only against an independent want; in production the want is the build's: finding 2) |
| no loaded-data limit | ix_order, loaded_data_limit |
| loaded-data limit 1,024 | loaded_data_limit (same caveat) |
| also close the WSOL quote account | ix_order, ata_close, rent_returns |
| tip account loaded through the lookup table | tip_last, tip_to_jito, tip_check |
| **leg 1 spends from the payer's USDC account** | **none** (finding 7; fails on chain) |
| **leg 2 delivers WSOL to a foreign account** | **none** (finding 7; min_profit fails on chain) |
| **the mid account made read-only** | **none** (fails on chain) |
| **leg 1's discriminator flipped** | **none** (fails on chain) |
| **no close, with the want declaring a held addition (`close: false`)** | **none**: the shape `Exec::want` produces for any build without a close (finding 2) |

## Mutants (tests that pass with the bug present)

Each mutant was applied in the master tree, tested under `flock /home/moiz/arbx-offload/build.lock` with `CARGO_BUILD_JOBS=3` on the tree's own `target/`, and reverted from a byte copy. The sha256 of `src/exec.rs`, `src/build.rs`, `src/tip.rs` and `src/engine.rs` was re-checked after each one.

| # | Mutant | Tests run | Result |
|---|---|---|---|
| M1 | Skip the close: `exec.rs:1295` `close: true` → `false` | lib: exec, build, scenarios, tip, cu_table | **Caught**: 9 failures (`rent_neutral_create_and_close`, `the_held_view_comes_from_the_store`, both S10 scenarios, `the_size_budget_ladder`, `the_route_checks`, `verify_bundle_on_the_new_layout`, `cu_limit_guard_and_tip_band_in_the_bundle`, `bundle_vectors_for_the_venue_harness`). Every failure is a `closes_ata` or CU assert, and the dry run's own checks pass inside them (finding 2) |
| M2 | Close before the route: `build.rs:431-432` swapped | same | **Caught**: 9 failures, including `bundle_instruction_order_golden` and the dry run's `ix_order` / `rent_returns` |
| M3 | Tip from the wrong band: `tip.rs:71` share `[band]` → `[band.saturating_sub(1)]` | lib: exec, build, scenarios, tip, cu_table, bands, engine, replay | **Caught**: 3 failures (`tips_by_band`, `margins_and_tips`, `cu_limit_guard_and_tip_band_in_the_bundle`) |
| M4 | Size over the cap: `engine.rs:2169` `size.min(cap)` → uncapped | **full** `cargo test --release` | **Survives: 445 passed, 0 failed** (finding 3) |
| M5 | The held set never grows: `exec.rs:1686` `self.held.insert(mint)` removed | lib | **Survives: 417 passed, 0 failed** (finding 5) |
| M6 | min_profit without the base fee: `exec.rs:465` | lib | **Caught**: 12 failures, including `a_dry_run_catches_a_wrong_min_profit` and the dry-run checks |

## Builds and tests run

All runs held the global lock (`flock /home/moiz/arbx-offload/build.lock`) with `CARGO_BUILD_JOBS=3`. No other target directory was created; the harness used `CARGO_TARGET_DIR=/home/moiz/arbx-offload/targets/venue-harness`. Logs are in `scratchpad/r4/wp06-review/`.

1. `cargo test --release` (master tree, clean snapshot): **445 passed, 0 failed, 5 ignored**. Only the 2 pre-existing warnings.
2. `program/venue-harness`: `cargo test --release --test arbx_bundle -- --nocapture`: **1 passed**.
   - `pump_buy_dlmm_sell_create_close`: native −105,000; WSOL +60,507,179 (as quoted); rent 1,513,840 locked and reclaimed; CU 170,507 of 247,000.
   - `pump_buy_dlmm_sell_held`: 150,427 of 212,000; nothing created.
   - `profit_fail`: `Custom(1314390018)` = 0x4e580002; no account left; WSOL unchanged.
   - `dlmm_buy_pump_sell_create_close`: 153,273 of 241,000; rent neutral.
   - `spl_usdc_create_close`: 1,488,440 locked and reclaimed; create 14,917, close 120.
3. `cargo test --release --test zz_review_wp06_verify_mutants -- --nocapture` (the temporary file, since removed): 26 mutations, table above.
4. Mutants M1-M6, table above. M4 ran the full suite; the others ran the listed lib filters.
5. A final `cargo test --release` on the restored tree, which rebuilt `target/` from the unmutated sources: **445 passed, 0 failed, 5 ignored**.

**Tree integrity:** after the last revert, `git diff | sha256sum` = `9360117734aa152afae0a092e04e43bcab335d15b0c4fca705ea12acf0332f42`, the same as at the start. The seven new files match their start hashes. The only file added is this review.

## Disposition (2026-10-06, the fix in the master tree, committed as WP-06)

**Where.** The fixes are in the uncommitted WP-06 work of the master tree (HEAD `20f6812`) and are committed with it as the WP-06 commit. Built with the tree's own `target/` under the global lock (`flock /home/moiz/arbx-offload/build.lock`, `CARGO_BUILD_JOBS=3`); the venue harness with `CARGO_TARGET_DIR=/home/moiz/arbx-offload/targets/venue-harness`. No new target directory. Nothing of lane/wp-07, lane/wp-20, the FT-000 fixes or integ/stage0 is merged here (their items are listed below, "For the merge with integ/stage0").

**Results.**
- `cargo build --release`: the 2 pre-existing warnings only (`main.rs:551`, `:559`, irrefutable `if let`).
- `cargo test --release`: **454 passed, 0 failed, 5 ignored**: lib 426 (+4 ignored), bin 13, legacy_fixtures 4, meta_config_hash 1, replay_cli 1, runtime_isolation 2 (+1 ignored), stop_path 6, supervisor 1. Nine tests more than the review's 445.
- Toolkit: `cd tools/arbx-report/tests && python3 -m unittest discover -s .`: 85 tests OK (4 skipped).
- `arbx check` on `deploy/arbx-stage0.toml` and `deploy/arb.toml`: both exit 0. The builder line now reads "new token accounts created and closed in the same transaction (rent-neutral: nothing stays locked); held-set additions off (held_max = 0)".
- Venue harness, `cargo test --release --test arbx_bundle`: 1 passed. `testdata/builder/bundle-vectors.json` (`f6725333…`) and `results/arbx-bundle-runs.json` (`3273b09c…`) are byte-identical to the review's: the fixes change what is allowed and what the dry run checks, not the bytes of a bundle that fits.

### The findings

| # | Disposition | What changed | Tests |
|---|---|---|---|
| 1 Blocker | **Fixed** | `[builder] held_max` defaults to **0**, and both maintained configs set `held_max = 0` explicitly. Held-set additions are an explicit opt-in: `BuilderCfg::held_additions()` is `held_max > 0 && create_close`, and the `held_ata` rung exists only then. By default an oversized create+close bundle is refused `oversized`. When opted in, the rung is taken only if the expected profit covers the decision's bar (max(min_profit, tip + base fee + `margin_lamports`)) plus `build::HELD_RENT_BOUND`, and the route then asks min_profit + `HELD_RENT_BOUND` on chain. The bound is 2,282,880 lamports: a 200-byte account at 6,960 lamports a byte, above mainnet's 1,488,440 (SPL) and 1,513,840 (Token-2022). Otherwise the build error says why (`held_ata: expected … below min_profit + the rent kept`, or `held_ata: N tokens held of held_max M`). `Built.min_profit` is what the route asks: it feeds attempts `min_profit_onchain`, `Open` and the sim line, and attempts add `tx.held_rent_lamports`. meta.json `limits.rent_neutral` is `!held_additions()` (it was always true), plus `limits.create_close`. `arbx check` says plainly whether additions are on | `the_size_budget_ladder`. By default it gives `oversized` where `held_ata` would fit. Opted in: the 50,000-lamport route is still `oversized` (rent not covered); the 3M route gives `held_ata`, whose signed route min_profit decodes to 40,001 + 2,282,880; a full held set gives `oversized`; the dry run passes the justified addition (min_profit_onchain = tip + fee + floor + rent). Also `wp06_builder_keys`, `stage0_config_is_the_day0_safety_switch`, `maintained_configs_lock_no_rent` and `meta_limits_carry_the_stage0_limits` (an opted-in config reports `rent_neutral` false). On the review's code: the default (40) built `held_ata`, and an opted-in addition asked no rent |
| 2 Major | **Fixed** | `VerifyWant` holds no number taken from the build. The created account comes from the decision's held view. `held_ok` is `held_growth_ok()`: the policy, false by default. The CU inputs are `RouteIn::cu` and `cu_ata`. The loaded-data inputs are `[builder] loaded_data_limit` and `RouteIn::sizes`. The lookup tables are the ones the signed bytes name, resolved from the `[exec]` tables and the engine's (journaled) cache. `verify_bundle` reads from the signed bytes the accounts the transaction creates and the ones it closes to the payer. A kept account passes only as a justified held addition: configured and allowed (`held_ok`), the route's mid account, and the signed instructions plus its close (recompiled on the tables the message names) over 1,232 bytes or 64 locks. New check `held_addition`. `route_min_profit` wants the decision's min_profit plus the rent of a justified addition; `min_profit_covers_tip` adds the rent of every kept account (`kept_rent`). `cu_limit` is re-derived: the decision's route CU plus the create's and the close's allowance for each one in the signed message. `loaded_data_limit` `auto` is re-derived from the signed message's own resolved accounts: invoked programs, the decision's sizes, 8,248 per table it names. The build's `auto` estimate now counts only the tables the message loads from (one recompile when a given table loads nothing), so the two derivations agree; they share `build::loaded_data_raw` / `loaded_data_padded`. The status counter `held_addition` counts the attempts that keep an account (fix 4's summary) | `a_dry_run_catches_a_kept_account`: a builder fault keeps the account, and the dry run's checks fail (`min_profit_covers_tip`, `ix_order`, `ata_close`, `rent_returns`, `held_addition`) with held additions off and on. `a_dry_run_rederives_the_cu_and_loaded_data_limits`: builder faults (the CU without the create's 30,000; 1 MiB less loaded data) fail `cu_limit` and `loaded_data_limit`, though the build's own record agrees with its bytes; a 10 MB account moves both derivations. `verify_bundle_on_the_new_layout`: hand-laid variants, a kept account with and without `held_ok`, `auto` re-derived. `loaded_data_from_the_message_is_the_instructions`. `bundle_vectors_for_the_venue_harness`: the signed instructions recompile to the vector byte for byte. **Mutant M1 is now caught by the dry run itself** (below). The review's `no_close_with_want_close_false` shape is gone: a want can no longer declare a close away |
| 3 Major | **Fixed** (the test); the executor's refusal comes **at the merge** | `the_engine_caps_the_size` is new. An engine and executor price a gap at 1 SOL; every attempt trades at most the cap: a canary at `size_sol` 0.05, whose bundles are decoded from what the block engine received (signed `amount_in` ≤ the cap), and a shadow run at `[live] max_size_sol` 0.03. A comment in `decide_inner`, after `implausible_gap`, marks where lane/wp-07's executor-side `size_cap` refusal lands (its review #12). It is not duplicated here, because WP-06's `size_cap_for(&Bankroll)` and WP-07's `size_cap()` differ and are reconciled at the merge | `the_engine_caps_the_size`. **Mutant M4 is now caught** (below) |
| 4 Major | **For the merge** (by instruction) | Not changed here: the lane/wp-07 canary config keys, the two bankroll hooks, the relative `cu_table` default. See "For the merge with integ/stage0" | |
| 5 Minor | **Fixed** | `Exec::held_count()` is the boot read's tokens (WSOL, USDC, USDT aside) ∪ every landed addition (`add` puts its token in the held set) ∪ every open attempt with `held_addition`, each token once. `held_growth_ok` uses it | `held_additions_count_in_flight_and_landed`. Live, `held_max = 1`: an addition in flight stops another token's (`oversized`, "1 tokens held of held_max 1"). Once it lands, its token is held (`new_token_accounts_total` 1) and the limit still binds. `held_max = 2` lets the next one go. Mutant M5 and the in-flight count removed both fail it |
| 6 Minor | **For the merge / FT-002** | LiteSVM counts no programdata, so the harness cannot validate `auto`. FT-002's dry run must simulate (`[dry_run] simulate = true` in the canary config, which is lane/wp-07's file). The programdata sizes stay constants in `PROGRAM_BYTES` | |
| 7 Minor | **Fixed** (the case min_profit does not watch) | New check `route_payer_accounts`: no leg names the payer's USDC or USDT account unless it is the route's mid account. Not done: per-venue user positions, writable flags and discriminators, which fail on chain, as the review found | `verify_bundle_on_the_new_layout`: leg 1 spends from the payer's USDC account, and only this check fails |
| 8 Minor | **Fixed** | A what-if replay hands the overridden tip model to the offline executor (`Exec::set_tip_model`: its tips, min_profit and bands), not only to the engine's fee | `s10_a_non_held_mid_mint_gets_create_and_close_a_held_one_neither`: a `tips.shares=[0.35,…]` replay; every replayed attempt's `tip.share` is 0.35, the run's 0.7 |
| 9 Minor | **Fixed** | `[builder] create_close = true\|false` (default true; in `cfg_sha256`; meta.json `limits.create_close`; `arbx check`). False refuses a route through a token the wallet holds no account for (`mid_not_held`, A.1, `reject_mid_not_held`), and nothing is created: the held-only control arm | `create_close_off_trades_held_tokens_only`; `wp06_builder_keys`; `the_executor_config_hash` |
| 10 Minor | **Fixed** | `EngineInit::from_json`: an absent or null `builder` is a journal from before WP-06 (the old rule). A builder that is present but does not read makes the record unreadable, and the replay refuses with "…engine_init record (INPUT 10) this build reads…" | `engine_init_builder_reads_back_or_refuses` |
| 11 Minor | **For the merge** | The upload list (`docs/field-tests/README.md`, which integ/stage0 edits) and the canary's absolute `cu_table` path. Both maintained configs already name `/root/arbx/data/cu-table.json` | |
| 12 Info | **Fixed** | `pump_leg` refuses `cashback && !has_v2` (`pump-cashback-without-pool-v2`). The block that named the accumulator's WSOL account is gone | `pump_cashback_without_pool_v2_is_refused` |
| 13 Info | **Fixed** | `uva_missing` keys on the direction: a PumpSwap leg its quote token (t1) goes into, on either leg | `uva_missing_refuses_pumpswap_buys` (a sell leg on a pool whose quote is the route's token) |
| 14 Info | **No change** | No shared lookup table is configured. X6 (WP-12) measures how often the learned index finds one; our own tables for hot pools are Stage 2A | |
| 15 Info | **Deferred** | An SPL-mid vector needs a second route fixture pair, in both testdata/venue-parity and the harness fixtures. The close is the same instruction. FT-002's simulation of SPL-mid routes covers it on mainnet state | |
| 16 Info | **No change** | `allow_uva_create` ships false and frz has its accumulator. Creating one stays a separate wallet-prep transaction (owner action) | |
| 17 Info | **No change** | `dlmm_cap` stays a decision flag (MEASUREMENT A.1 says so). `deploy/legacy/` is not loaded. The 2 pre-existing warnings are outside WP-06 and are left alone to keep the merge small | |

Docs: MEASUREMENT.md 2.11 records the fixes in the revision note and in §4.8, §4.13, §4.32, §4.37, §4.50, A.1 and A.7. In PLAN.md WP-06, item 2 and the config keys give the new defaults.

### Mutation check of the fix

Each mutant was applied in the master tree, tested under the lock on the tree's own `target/`, and reverted from a byte copy, with sha256 checked after each one. M1 and M4 ran on the committed code. M5, M5b, M7 and M8 ran on the code just before its last edits (a doc reflow, an unused getter removed, the `held_addition` counter), none of which touches their lines. After the last revert the tree was rebuilt (sources touched, so no artifact built from a mutant survives) and the whole suite passed again.

| # | Mutant | Tests run | Result |
|---|---|---|---|
| M1 | The review's: the build's create without its close (`AtaOps { …, close: false }`) | lib | **Caught: 11 failures.** 7 of them fail **on the dry run's own checks** (`checks_ok` false), where the review saw them pass: `rent_neutral_create_and_close`, `the_held_view_comes_from_the_store` ((true, false, false)), both S10 scenarios ((true, false, false) for every bundle), `verify_bundle_on_the_new_layout` (the executor's own bytes fail `min_profit_covers_tip`, `ix_order`, `ata_close`, `rent_returns`, `held_addition`), `a_dry_run_rederives_the_cu_and_loaded_data_limits` and `cu_limit_guard_and_tip_band_in_the_bundle`. The other 4 fail on unit asserts: `the_size_budget_ladder`, `the_route_checks`, `bundle_vectors_for_the_venue_harness` and `held_additions_count_in_flight_and_landed` |
| M4 | The review's: `engine.rs` `size.min(cap)` → `size.min(cap.max(u64::MAX))` | full `cargo test --release --no-fail-fast` | **Caught: 453 passed, 1 failed.** `the_engine_caps_the_size` failed on an attempt at 1,000,000,000 lamports against a 50,000,000 canary cap (it survived all 445 in the review) |
| M5 | The review's: `self.held.insert(mint)` removed from `Exec::add` | lib | **Caught**: `held_additions_count_in_flight_and_landed` |
| M5b | The in-flight count removed from `held_count` | lib `exec::` | **Caught**: `held_additions_count_in_flight_and_landed` ("in flight") |
| M7 | The held rung without the rent (`let rent = 0`) | lib | **Caught**: `the_size_budget_ladder` |
| M8 | The default `held_max` back to 40 | lib | **Caught: 3 failures**: `wp06_builder_keys`, `the_size_budget_ladder`, `a_dry_run_catches_a_kept_account` |

### Owner-decision defaults set by this commit

- `[builder] held_max = 0`: no held-set additions. Opting in is the owner's decision, against the go-live gate's "nothing stays locked". The rent bound and the in-flight count then apply.
- `[builder] create_close = true`: the gate's create+close lever. `false` gives a held-only first hour or the STAGE1-PLAN §3.1 control arm.
- `build::HELD_RENT_BOUND = 2,282,880` lamports, the rent an opted-in addition must cover.
- Unchanged from the reviewed draft: `allow_uva_create = false`, `payer_guard = false`, `loaded_data_limit = "auto"`, `cu_min_samples = 30`, `alt_index = true`, `max_alts = 4`, `[tips]` 0.7 in every band with floor 1,000 and cap 100,000, `[bands]` [20k, 100k, 1M, 10M].

### For the merge with integ/stage0 (lane/wp-07 + WP-20 + the FT-000 fixes)

1. **The frz canary config** (`deploy/arbx-canary-frz.toml`):
   - remove the jito-bundle path's `tip_share` and `tip_max_lamports`, and `[live] max_new_token_accounts`, or the file does not load;
   - add `[tips]` with `shares = [0.7, 0.7, 0.7, 0.7, 0.7]`, `floor = 1000` (the path's `tip_lamports` 1,000 is at most the floor) and `cap = 100000`;
   - add `[builder]` with `create_close = true`, `held_max = 0`, `cu_table = "/root/arbx/data/cu-table.json"` (absolute: the default is relative to the working directory, and a run without the file refuses to start), `loaded_data_limit = "auto"`, `allow_uva_create = false` and `payer_guard = false`;
   - set `[dry_run] simulate = true` for FT-002, because LiteSVM does not count programdata, so the `auto` loaded-data limit must be validated by simulateTransaction (finding 6);
   - update its header, which still says "USDC routes only until WP-06";
   - lane/wp-07's `the_frz_canary_config_passes_arbx_check` must pass on the result.
2. **WP-07's `rent_cap` refusal in `decide_inner`** (`creates_ata && (new_atas >= max_new_atas || rent_recoverable + ATA_RENT_ESTIMATE > rent_cap)`) must not survive as written. After WP-06 a create+close locks no rent, and `max_new_token_accounts` is gone. Kept as written, it would refuse every route through a token frz does not hold (`rent_cap`) and silently make the canary held-only. Drop the `max_new_atas` part, and apply the rent cap to a held-set addition only, inside `Exec::held_growth_ok` (its doc says "WP-07's rent cap joins here"), keeping `held_count`'s in-flight and landed count.
3. **The bankroll hooks.** WP-06 has `Bankroll` from the store (`Engine::bankroll`, journaled), `size_cap_for(&Bankroll)` and `bankroll_cap(&self, &Bankroll) -> None`. WP-07 has `size_cap()` and `bankroll_cap()` on the ledger's money view.
   - Keep one source: WP-07's money view is the go-live gate's. Delete the other hook.
   - Keep WP-07's executor-side `size_cap` refusal at the comment `decide_inner` marks (review #3).
   - Keep the engine re-quoting the route at the cap in `after_opportunity`: `the_engine_caps_the_size` must still pass. A merge that keeps only the executor's refusal turns capped trades into refusals and fails it.
   - Reconcile `ExecInit.bankroll_cap`.
4. **Unions to merge by hand:**
   - `cfg_sha256` (WP-06: `builder`, `tips`, `bands`; WP-07: `rent_cap_sol`);
   - the `reasons!` list (WP-06: `mid_not_held`; WP-07: `equity_unknown`, `equity_stale`, `size_cap`);
   - the `Exec` struct and `assemble` (WP-06: `payer_tokens`, test-only `fault_keep`, `fault_cu`, `fault_loaded`; WP-07: the money view, the bankroll and rent-cap fields, `provisional`, …);
   - `Open` and `Final` (both lanes add fields; `held_count` reads `Open.held_addition`);
   - meta.json `limits` (WP-06: `rent_neutral` from the config, `create_close`; WP-07: the bankroll's);
   - `arbx check`'s builder line;
   - MEASUREMENT.md A.1, A.7, §4.2 and §4.37.
5. **The Cherry upload list.** `docs/field-tests/README.md` (integ/stage0 edits it) must name `data/cu-table.json` with the other data files (finding 11).
6. **After the merge:** rebuild under the lock, run the full suite, `arbx check` on all three configs, the toolkit, and the venue harness `arbx_bundle`. Re-run M1 and M4 on the merged tree.

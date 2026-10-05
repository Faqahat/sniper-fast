# WP-16 review: venue-maths parity (the engine prices with arbx-sizing)

**Date:** 2026-10-05. **Reviewer:** adversarial review. No repository code was changed: probes ran in scratch copies and
this file is the only file written to the worktree (see "Incident" for an accidental write that I reverted).
**Plan:** `docs/PLAN-ADDENDUM.md` WP-16 (goal, evidence, design, tests, measurement, "as implemented").
**Background:** `program/arbx-sizing/DESIGN.md` §2.0, §2.1, §2.7, §5.5, §7; `program/arbx-sizing/REVIEW.md` F1, F9;
`program/venue-harness/README.md`; `docs/research/cmp2-shadow-comparison.md` (I-8).

## What was reviewed

- **The diff.** The uncommitted lane/wp-16 work on master 323e3bf: 19 modified files (+537/−2,083, with
  `src/venues/dammv2.rs` deleted) and 31 untracked files (`src/quote.rs`, `src/quote/tests.rs`, `src/venues/legacy/*`,
  `program/venue-harness/src/bin/capture_post.rs`, `tools/ci-venue-parity.sh`, `testdata/venue-parity/*`).
- **Snapshot.** `git diff` sha256 was `0aff38d4c5dff1922301374aa27075eee4dba3c1c4dbbfcfadb76426dc7c68aa` at the start
  and is the same at the end.
- **Mainnet census.** I made read-only calls to the public RPC (`https://api.mainnet-beta.solana.com`):
  `getMultipleAccounts` in batches of 100, about one call every 2 s, with backoff on 429. I fetched every pool in
  `data/seed-pools-w4.csv` and `data/seed-pools-merged.csv` of the five engine venues (1,395 pools), then every account
  their quotes read (4,801 accounts in all), the DLMM bin arrays within ±4 of each active bin (2,960 PDAs), and the
  signatures and recent transactions of the 47 PumpSwap pools in question. The account reads are at slots
  453,411,1xx-453,416,4xx.
- **Real program.** I ran the dumped mainnet pAMM ELF in LiteSVM: the venue-harness copied to scratch, with 9 more
  mainnet pools fetched read-only.

## Verdict

**Not ready to merge.** There are two blockers, both in `pumpswap::parse`. Together they refuse 41 live WSOL-quoted
PumpSwap pools (48,551 SOL of quote reserves) that the real program prices exactly as the crate would. 38 of the 41 had
successful swaps after the program's last deploy; the other 3 showed only failed bot transactions. There are also two
majors, both gaps in the tests.

1. **Blocker (F1, regression).** The exact-301-byte gate refuses the 14 live 300-byte PumpSwap pools.
   - 13 of them were priced by master: about 12,000 SOL of quote reserves, including pools holding 7,134, 2,041, 1,277
     and 814 SOL.
   - They trade today at 300 bytes.
   - pump.fun documents that shorter pools are read with zeros.
   - With the pool zero-padded to 301 bytes, the crate is exact against the real program.
2. **Blocker (F2, pre-existing, carried into the crate with a wrong rationale).** Byte 270 is not an unknown tail or a
   counter. It is `Pool.is_holder_reward: bool` in pump.fun's public IDL (2026-09-12).
   - pump.fun: "There are no changes to any trade instruction … Fees are computed exactly as before".
   - It is 0 or 1 on every pool. Refusing it drops 34 live pools, 28 of them WSOL-quoted (36,554 SOL).
   - With byte 270 cleared, the crate is exact on the real program, including on holder-reward pools with
     held-back amounts and a negative virtual reserve.
3. **Major (F3).** The exactness and adversarial oracle never checks over-refusal: a crate `Abort` is never compared
   with the venue. Its fixtures also have no 300-byte or holder-reward pool. That is how F1 and F2 passed with
   "0 mismatches".
4. **Major (F4).** Two new pieces of WP-16 wiring are unguarded by tests. With both of these mutations applied, all
   305 lib tests still pass:
   - the state stream following the GlobalConfig and Token-2022 mints;
   - the accuracy monitor actually predicting.

**The implementer's other claims hold.** The slowdown is somewhat larger than reported (F7).
- Builds and test counts reproduce exactly.
- All quoting goes through the crate.
- On the other four venues the crate's refusals are right and cost no coverage in the census.
- Sizing never exceeds the cap.
- I found no panic path.

The fix for F1 and F2 is about ten lines in one function, plus fixtures and tests (see F1 and F2). F5-F10 are minor.

## Settling the flagged PumpSwap risk

The crate requires `pool.len() == 301`. It refuses byte 270 ≠ 0 and any nonzero byte in 287..301
(`program/arbx-sizing/src/venue/pumpswap.rs:12`, `:37-38`, `:136-138`).

| Question | Answer | Evidence |
|---|---|---|
| What is byte 270? | `is_holder_reward: bool`, appended after `can_edit_creator_fee` @269 | pump-fun/pump-public-docs `idl/pump_amm.json`, commit e0687ae9b7, 2026-09-12 ("refresh pump, pump_amm and pump_fees IDLs … feat/add-holder-…"). The Pool fields end exactly at 271. `docs/HOLDER_REWARDS_README.md` and `docs/PUMP_SWAP_README.md` describe it |
| Does it change the swap maths? | **No.** "There are **no changes to any trade instruction** … Fees are computed exactly as before; the only difference is who ends up receiving the creator fee". BuyEvent/SellEvent only add `holder_rewards_bps`/`holder_rewards` | pump docs; LiteSVM: exact on 5 holder-reward pools (below) |
| "Nonzero counters (0x97, 0xba)" (DESIGN §2.7 item 2)? | **Not reproducible.** Byte 270 is 0 on 355 live pools and 1 on 34, and never anything else. A Borsh `bool` byte other than 0 or 1 does not deserialize, so a live pool cannot hold one. (One possible source of the observation: the low byte of `held_0` @271, which does vary.) | census |
| Bytes 287..301? | Unidentified, and zero on every pool that has them: 312 × 301 B, plus bytes 287..299 of 14 × 300 B. The crate's rule refuses none of them today, so it is harmless | census |
| Pool lengths on mainnet? | 301 B (312 pools), **300 B (14)** and 287 B (63, non-SOL dust). pump.fun: "Pools written before an appended field existed are shorter than the current layout; read the missing trailing fields as 0 / false" | census; `PUMP_SWAP_README.md`, `NEGATIVE_VIRTUAL_QUOTE_RESERVES.md` |
| Are the refused pools tradable? | **Yes.** 12 of the 14 300-byte pools and 33 of the 34 holder-reward pools had a successful pAMM swap (Buy, Sell, BuyExactQuoteIn, SellV2, BuyExactQuoteInV2) after the program's last deploy (slot 452,654,882), and the pools are still 300 bytes. The other 3 showed only failed transactions in their last 25 signatures, which proves nothing either way | `getSignaturesForAddress` + `getTransaction` |
| Is the crate's rule right? | **No, on two counts.** (a) The length gate should refuse only lengths above 301, and read a shorter pool with zeros. (b) Byte 270 should accept 0 and 1 and refuse anything else as `Layout`. The 287..301 rule can stay | F1, F2 |

## Findings

### F1. Blocker: the exact-301 length gate refuses live 300-byte pools (regression against master)

- **Location:**
  - `program/arbx-sizing/src/venue/pumpswap.rs:9-12` (`POOL_LEN = 301`) and `:136` (`pool.len() != POOL_LEN → Abort::Layout`);
  - surfaced by `src/quote.rs:227-242` as `sz_layout`;
  - DESIGN §2.1 ("len **exactly 301**") and §2.0 "Version gates";
  - REVIEW.md F9 (where the gate came from: meant for on-chain sizing, where an abort falls back to `e`; in the engine it
    is a skip).
- **Problem:** the gate treats a shorter pool as an unknown layout. A shorter pool is an older pool whose missing
  trailing fields the program reads as zero (pump.fun's documented rule). In the engine the refusal is not a fallback:
  the route is dropped.
- **Proof.**
  - **Census.** 14 of the 389 live PumpSwap pools are 300 bytes, all WSOL-quoted.
    - In all 14: V = 0, held = 0, creator_fee_bps = 0, and bytes 287..299 are 0.
    - Master (`pools.rs` ≥ 253 bytes; `cp.rs` refuses only mayhem, cashback and p[270] == 1) priced 13 of them. The 14th,
      EBNU, also has byte 270 = 1.
    - Those 13 hold 11,997.7 SOL of quote reserves:
      - `9qKxzRejsV6Bp2zkefXWCbGvg61c3hHei7ShXJ4FythA` 7,134.5 SOL;
      - `FKfRK3WdaGXokysR1fPGgCDEeGkV1b1YYnX9ykVpG3JG` 2,040.7;
      - `9htNhHVtWrPiRdcSyBZoAhtLRZ4NKxxNE8qdkDCZx57f` 1,277.4;
      - `AZmU4Bv6TPHimgqBe5eRsRQ18KKKr2aemHdqmfbVKqvr` 813.9;
      - `2z2uBDXa…` 233.7;
      - `65XQtov9…` 152.7 (also in seed-pools-merged.csv);
      - `9ZiJwWMx…` 146.4, `8dmvfYhR…` 72.6, `AmmpSnW5…` 42.9, `7wRmK97H…` 30.8, `DbjAZWoR…` 26.1, `539m4mVW…` 14.7,
        `FDXvtVFZ…` 11.1.
  - **Live.** 12 of the 14 had successful swaps after the program's last deploy and are still 300 bytes. So the current
    program swaps them without extending them.
  - **Real program (LiteSVM, the dumped pAMM ELF).** The harness's exactness test ran on FKfR, 9htN, AZmU, 2z2u and
    EBNU: about 45 sell sizes and 1,045 buy sizes per pool, plus the virtual-reserve and creator-fee mutations.
    - As built, the crate aborts every quote (`abort:Layout`) while the program swaps.
    - With the pool zero-padded to 301 bytes on the crate's side only (the venue swaps the real 300-byte account), every
      quote the venue fills is exact, and the remaining sizes are refused by both. See "Real-program proof".
- **Fix** (in the crate, so that WP-17's on-chain sizing gets it too).
  - Code changes:
    - refuse only `pool.len() > POOL_LEN` (an unknown longer layout keeps turning sizing off) and lengths below the last
      field the parse needs (≥ 245, or 253 like master);
    - read every field at or beyond `pool.len()` as zero (held amounts, V, creator_fee_bps, is_holder_reward), for
      example by copying the pool into a zeroed `[u8; 301]`.
  - Doc changes: DESIGN §2.1 ("300 or 301 bytes; shorter pools are read with zeros") and §7 item 6.
  - Fixture and test changes:
    - add a 300-byte pool to `program/venue-harness/fixtures/pool-list.json` and `testdata/venue-parity`;
    - add to `every_refusal_state_is_a_skip_with_its_reason`: a 300-byte pool gives "ok", a 302-byte pool gives
      `sz_layout`.

### F2. Blocker: byte 270 is `is_holder_reward`, and refusing it drops 34 tradable pools

- **Location:**
  - `pumpswap.rs:35-38` (`TAIL_UNKNOWN_0 = 270`) and `:138`;
  - `error.rs:37` (`PumpWhy::UnknownTail`);
  - `src/quote.rs:116` (`sz_pump_unknown_tail`);
  - DESIGN §2.1 table, §2.1 "Abort", §2.7 item 2 and §7 item 6;
  - the test `src/quote/tests.rs:397`, which asserts the refusal;
  - venue-harness `tests/adversarial.rs:236` ("tail byte 270 set", counted as an acceptable abort).
- **Problem.**
  - DESIGN §2.1 says bytes 270 and 287..301 "are zero on every pool seen and their meaning is unknown". §2.7 item 2 says
    byte 270 "holds nonzero counters on mainnet (0x97, 0xba)". Both are wrong, and they contradict each other.
  - Master's `cp.rs:112` named the field correctly ("holder reward") and refused it needlessly. WP-16 keeps the refusal
    under a wrong name.
- **Proof.**
  - **The field.** It is in the public IDL and docs (table above). The census sees only 0 or 1.
  - **The census.** 34 live pools have byte 270 = 1: 33 × 301 B and EBNU × 300 B. 28 of them are WSOL-quoted, with
    36,553.8 SOL of quote reserves, including `5wNu5Qhd…` 9,413 SOL, `HMzvsEEm…` 12,435 SOL, `3KFCgJ5R…` 2,891 SOL,
    `5PGhKcty…` 2,417 SOL, and `8ewuF2o8…` and `CBnBZf7o…`, which are in seed-pools-merged.csv. 19 of them have
    held > 0, and 5 have V < 0 (V = −held).
  - **Live.** 33 of the 34 swapped after the last deploy.
  - **Real program (LiteSVM).** On 5PGh (V = 0), 3KFC and 5wNu (held > 0, V < 0), 8ewu (V > 0) and EBNU (300 B), the
    crate as built aborts every quote (`abort:Pump(UnknownTail)`). With byte 270 cleared on the crate's side only, every
    quote the venue fills is exact, with 0 mismatches.
- **Fix.**
  - Read byte 270 as `is_holder_reward`: 0 or 1 is accepted and changes nothing; any other value is `Abort::Layout` (an
    invalid Borsh bool, which the program would also reject).
  - Keep the 287..301 rule, renamed (it costs nothing today).
  - Correct DESIGN §2.1, §2.7 item 2 and §7 item 6. Flip the `:397` assertion to "ok". Make the adversarial "tail byte
    270" case expect a quote.
  - Add a holder-reward pool to the fixtures. 5PGh and 3KFC cover V = 0 and V < 0 with held > 0.

### F3. Major: the oracle cannot see over-refusal

- **Location:**
  - `program/venue-harness/tests/exactness.rs` (rows where the parse or the quote aborts `continue` before the venue
    is run);
  - `tests/adversarial.rs` (aborted rows likewise);
  - `fixtures/pool-list.json` (3 PumpSwap pools, all 301 B with byte 270 = 0).
- **Problem.** "0 mismatches" covers only sizes the crate quotes. A refusal of a state the venue swaps is invisible.
  This hides the cost of every overly broad gate, the venue-specific gates of DLMM and DAMM v2 as much as PumpSwap's,
  which matters now that a refusal removes a route from the engine instead of falling back to `e`.
- **Proof.**
  - `results/adversarial.json` has 173 rows for "tail byte 270 set" (3 pools × 2 directions), all `aborted`, none
    compared with the venue.
  - On the same kind of state, the venue swaps (F2).
  - The suite passed on a crate that refuses 41 live WSOL pools.
- **Fix.**
  - For aborted rows, still run the venue and tally "abort while the venue swaps" (over-refusal) separately.
  - Fail on any over-refusal of an unmutated fixture snapshot.
  - Add the 300-byte and holder-reward classes to the fixtures, and keep the fixture list representative of the seed
    lists: today its 3 PumpSwap pools are all 301-byte pools that are not holder-reward pools.

### F4. Major: two pieces of new wiring are untested; mutations that break them leave every test green

- **Location:**
  - `src/pools.rs:184-185` (`static_accounts` adds the GlobalConfig and `t22_mints`);
  - `src/quote/tests.rs:282-320` (`accuracy_predictions_match_the_real_post_states`: the only assertion is
    `problems.is_empty()`, and `Err` predictions only increment `unpredicted`).
- **Proof.** In a scratch copy of the lane (package renamed so that cargo cannot reuse the worktree's artifacts), I
  applied two mutations together:
  - M1: `static_accounts` no longer follows the PumpSwap GlobalConfig or any Token-2022 mint;
  - M2: `accuracy::predict` returns `Err(NoPred::Quote)` for every PumpSwap swap.

  `cargo test --release --lib` gave **305 passed, 0 failed**. The accuracy test printed
  `PumpSwap predictions exact: crate 0/252 (0.0%)` and passed. In production, M1 would make every PumpSwap route and
  every route with a Token-2022 side `account_missing`, because both are now "other parts" (`store.rs:132-145`).
- **Fix.**
  - Assert that `Registry::static_accounts()` and `watch_roles()` contain `PUMP_GLOBAL_CONFIG` and each pool's
    Token-2022 mints.
  - In the accuracy test, assert the exact set of unpredicted swaps (today only the 56 transfer-fee swaps on Hmx1 and
    2cUM), so that `exact == n − expected_refusals` per venue.

### F5. Minor: the accuracy monitor now needs the Clock pre-state for every venue

- **Location:** `src/engine.rs:2560-2561` (`needed.push(*CLOCK_SYSVAR)`, unconditional; master pushed it only for DLMM
  and DAMM v2). MEASUREMENT §4.34 still says "the Clock for DLMM / DAMM v2".
- **Problem.**
  - PumpSwap never reads the Clock, and CPMM and AMM v4 read it only for open times.
  - The Clock gets one version per slot, and `[accuracy] ring_versions` is 8. So a hint scored more than about 8 slots
    after its commit (queue backlog, late resolution) now loses its pre-state and becomes `pred_pre_state_unknown` for
    the CP-family venues as well. Under load this biases the per-venue accuracy WP-16 is meant to measure.
- **Fix.**
  - Require the Clock only for DLMM and DAMM v2.
  - For CPMM and AMM v4, use the Clock version before T when present, else the nearest one (an open-time check is only
    sensitive at pool launch).
  - Or keep the code and correct MEASUREMENT.

### F6. Minor: exact-out hints are predicted with exact-in maths, so their post-states cannot be exact

- **Location:** `src/accuracy.rs:99-101` (`solve_exact_in`, then the post-state booked with `q.out` of that input);
  `src/engine.rs:1888` (hint check). This is pre-existing, but WP-16 claims exact predictions and promises a
  per-venue accuracy rise.
- **Problem.** For an exact-out swap the program pays exactly `amount` and computes its own input:
  - PumpSwap `buy` (base out), CPMM `swap_base_output`, AMM v4 base-out, DLMM `swap_exact_out`.
  - The monitor instead books the output of the smallest exact-in size that reaches `amount`. That output is above
    `amount` whenever one input unit buys more than one output unit (for example buying a pump token with SOL).
  - The predicted vault therefore differs from the committed one by construction. `capture_post` records exact-in swaps
    only, so this path is untested.
  - PumpSwap `buy` is a common bot instruction: the activity census saw it on many pools.
- **Fix.**
  - Model the exact-out instructions (PumpSwap `buy` is a closed form).
  - Or book `out = amount` with the program's input formula.
  - Until then, mark exact-out predictions in predictions.jsonl and exclude them from the per-venue exact rate.

### F7. Minor: hot-path cost

- **Location:** `src/quote.rs` (parse per route leg), `src/engine.rs:1856-1872` (`price_route`, including the extra DLMM
  `walk` for `crossed`).
- **Measured.** All runs in release, on the same machine.

| Measure | Result |
|---|---|
| Engine Stage-0 benchmark (`engine_benchmark_stage0_shapes`, AMM v4 shape, 3 runs each), p50 µs, 4 pools/pair | master 7, 7, 9 against lane 10, 10, 8 |
| Same, 8 pools/pair | master 13, 14, 17 against lane 17, 18, 16 |
| Same, p99 µs, 4 pools/pair | master 22, 20, 28 against lane 23, 26, 23 |
| Same, p99 µs, 8 pools/pair | master 33, 32, 42 against lane 38, 43, 36 |
| Per leg: parse + 14 quotes on the fixtures, crate against legacy (scratch micro-benchmark) | AMM v4 199 against 104 ns (+92%), PumpSwap 296 against 157 (+88%), CPMM 195 against 153 (+28%), DLMM 3,588 against 2,611 (+37%), DAMM v2 698 against 1,913 (−63%) |
| Route sizing on HOTBOT GLL3 ↔ 6D4E, legs built once per route as in master | profitable gaps 1.4-2.6 µs against 2.7-5.6 µs (−38% to −64%: the locator replaces the 48-quote ternary search); unprofitable gap 1.44 against 0.73 µs (+96%) |

  So p50 is about 15-25% slower, a little more than the reported 10-15%. It stays far inside the benchmark's bounds.
- **Fix ideas.**
  - Skip the `crossed` walk when gross ≤ `min_profit`: net ≤ gross, so it cannot change the verdict.
  - Parse each pool and direction once per evaluation: a pool is in 2(k−1) routes.
  - Drop the two `Vec`s in `quote::leg`'s DLMM branch.
  - Cache the FeeConfig tier list per version.

### F8. Minor: boot-time refusals are not recorded

- **Location:** `src/pools.rs:111-118` (prints the dropped pools to stderr only).
- **Problem.** WP-16 promises "every refusal … an engine skip with a recorded reason". Pools dropped at boot never
  reach decisions.jsonl or a counter. In the census that is 208 pools: 41 DLMM, 148 DAMM v2 and 19 CPMM. All of them
  have a transfer fee that is nonzero in the current epoch, so the refusal itself is right.
- **Behaviour change.** A mint missing from the boot RPC answer now keeps its pool; master dropped it. This is harmless.
- **Fix.** Record `{transfer_fee, transfer_hook, layout}` drop counts, and the pools, in meta.json or the status line.

### F9. Minor: the CI script cannot keep builds out of the repository

- **Location:**
  - `tools/ci-venue-parity.sh` step 2 ("its sizing-bridge builds go to program/venue-harness/target");
  - `program/venue-harness/tests/{exactness,adversarial,route}.rs` (`MANIFEST_DIR/target/sizing-bridge*`, whatever
    `CARGO_TARGET_DIR` or `TARGET_BASE` says);
  - with `TARGET_BASE`, step 4 builds the engine in `$TARGET_BASE/arbx`, not the agreed `targets/lanes`.
- **Problem.** The bridges take about 171 MB in-repo. That fails on a /home at quota, and it is how my first harness
  run wrote into the worktree (see "Incident").
- **Fix.** Add an environment variable for the bridge target (default: under `CARGO_TARGET_DIR`), and let the script
  take per-crate target directories.

### F10. Minor: only route decisions name the crate's refusal reason

- **Location:** `src/engine.rs:1887-1890` (`trigger_unquotable`), `:2016` and `:2023` (`probe_unquotable`), `:2529`
  (the monitor counts `pred_unquotable` and writes `refused` only in the line).
- **Problem.** The A.7 counters per reason exist for routes only. The other paths collapse the crate's reasons into
  generic ones. This is acceptable for Stage 0; it is noted because the claim is "every crate refusal is a skip `sz_*`
  with a counter".

### F11. Documentation

- **DESIGN.md** (not updated by the diff):
  - §2.1 table and "Abort", §2.7 item 2 and §7 item 6 need F1 and F2.
  - The §2.7 header now says the deviations are "fixed in the engine". Item 2's "counters" text remains and contradicts
    §2.1.
- **REVIEW.md F9** ("accept exactly 301") needs a note: it was correct for on-chain sizing, where an abort falls back
  to `e`, and wrong for the engine, which skips.
- **The brief's premise.** "The old engine … refused only p[270]==1" is slightly off: master also refused mayhem (@243)
  and cashback (@244) (`venues/legacy/cp.rs:109-111`). The crate does the same.

### Hunted and not found

- **No quote path bypasses the crate.** Every engine quote goes through `quote::leg` and `Leg::quote`/`walk`/`fills`:
  `price_route` and `best`, `route_in`, `probe_routes`, `refresh_route`, `record_caps`, `hint_check` and
  `accuracy::predict`. The DAMM v2 post-state uses the crate's `swap_exact_in`. `venues::legacy` is `#[cfg(test)]` and
  is used only by `src/quote/tests.rs`. The builder and exec only re-use the quoted amounts and the DLMM end bin
  (`min_out` is 1, and the guard is the backstop).
- **No wrong or overly broad refusals on the other venues.** Census (table below): DLMM, CPMM, AMM v4 and DAMM v2 pass
  every parse gate except:
  - 53 DAMM v2 pools with zero liquidity (correct);
  - the transfer-fee drops, all with a fee in force in the current epoch (correct; same rule as master).

  There are no transfer-hook drops: the 22 kept pools whose mint carries a TransferHook extension (17 DLMM, 5 DAMM v2)
  have no hook program set.
  - DLMM: all 370 pairs left after the boot drops are version 1, and all 2,550 existing bin arrays within ±4 of their
    active bins are version 2.
  - When the route's array window stops early at a missing array, the pair's bitmap shows no liquidity beyond it in
    every case but one, so the contiguous-window rule costs nothing.
- **No size above the cap.**
  - `quote::best` clamps every candidate to [`lo`, `cap`]. The rungs are filtered to ≤ cap, and the back-off stays
    inside (good, bad). `price_route`'s cap is the ladder's top rung (4.2 SOL).
  - A live send is `size.min(live.max_size_sol)` (`engine.rs:1974`).
  - `record_caps` sizes up to the largest budget cap, but that is analysis only.
  - No bankroll check exists anywhere in the engine. That is not WP-16's concern.
- **No overflow or panic path.**
  - The new engine arithmetic is bounded:
    - `pump_post` and `cpmm_post` work on u128 products of u64 values;
    - the AMM v4 `r_out − out` relies on the crate's `out < r_out`;
    - the AMM v4 and CPMM `checked_sub` calls return `None`;
    - `bin_of` indexes through `u64_at`.
  - In the crate, the paths I read are checked or bounded by construction: PumpSwap, CPMM, AMM v4, `fills`/`bin_fill`,
    the walker's `walked < budget`, and `Fx` (division by zero gives ∞, shifts are capped at 40).
  - `Trip::profit` (`back as i64 − spent as i64`) could wrap only if a SOL-side output reached 2^63. The values are
    bounded by real reserves, and the "broken_quote" check catches more than 2× anyway.
- **No standalone violation.**
  - The engine tests read only `testdata/venue-parity` (`CARGO_MANIFEST_DIR`).
  - `testdata/venue-parity/pools` equals the harness fixtures, and `real-swaps.json` is reproduced byte for byte by
    `capture_post`.
  - The new files contain no absolute paths or references outside the repository.

## Census results

### PumpSwap

The pools are those of `data/seed-pools-w4.csv` ∪ `data/seed-pools-merged.csv`. The two files list 392 distinct pools;
merged's 45 are a subset of w4's.

| | Pools |
|---|---|
| Distinct addresses | 392 |
| Closed (System-owned, 0 bytes) | 3 |
| Live (owner pAMM, discriminator `f19a6d0411b16dbc`) | **389** |
| 301 bytes | 312 |
| **300 bytes** | **14** (all WSOL-quoted) |
| 287 bytes | 63 (all non-SOL quote; dust: lp_supply 100, base ≤ 30,506 and quote ≤ 63,084,862 raw units; 63 distinct quote mints; w4 only) |
| **Byte 270 = 0 / = 1 / other** | **355 / 34 / 0** (the 34: 33 × 301 B, 1 × 300 B) |
| Bytes 287..301 nonzero (pools that have them) | 0 of 326 |
| held_0 + held_1 > 0 | 129 |
| V ≠ 0 | 194: 171 positive, and 23 negative, each exactly −(held_0 + held_1) |
| mayhem / cashback / creator_fee_bps ≠ 0 | 2 / 3 / 11 |
| WSOL-quoted / other quote | 258 / 131 |

The crate's verdicts as an engine route leg, over the 389 live pools:

| Verdict | Pools |
|---|---|
| ok | 212 (quote reserves 111,963 SOL) |
| `sz_layout` | 77: 14 × 300 B (WSOL) and 63 × 287 B (non-SOL) |
| `sz_pump_unknown_tail` | 33: 27 WSOL and 6 non-SOL (the 34th holder-reward pool is EBNU, already `sz_layout`) |
| `pump_quote_not_sol` (route only) | 62, plus the 69 non-SOL pools above |
| `sz_pump_cashback` / `sz_pump_mayhem` | 3 / 2 |
| **The crate's own gates refuse** | **115 of 389**: 77 layout, 33 tail, 3 cashback, 2 mayhem |

WSOL-quoted live pools, against master and the fix:

| Version | Pools priced |
|---|---|
| Master 323e3bf | 225 |
| WP-16 as built | 212. **It loses 13 that master priced** (all 300 B, 11,998 SOL) |
| With the fix (271..301 bytes read with zeros, byte 270 ∈ {0,1} ignored) | **253: 41 more than as built** (48,551 SOL), 28 more than master |
| Of the seed-pools-merged.csv pools (45) | as built: ok 29, not SOL 7, tail 4 + 3, layout 1 (65XQ, 152.7 SOL), mayhem 1 |

Other facts from the census:
- GlobalConfig: 949 bytes, disable_flags 0, creator_fee_configurable 1.
- FeeConfig: 4,097 bytes.
- No PumpSwap mint is refused at boot.

Recent activity of the refused pools: the latest 25 signatures of each, and up to 8 successful transactions decoded
from their logs.

| Group | Pools | With a successful pAMM swap after slot 452,654,882 |
|---|---|---|
| 300 B | 14 | 12 (9qKx and AmmpSnW5: 25 of 25 recent transactions failed, so inconclusive) |
| byte 270 = 1 | 34 | 33 (AypF: 25 of 25 failed, inconclusive) |

The pAMM instructions seen: `Buy`, `Sell`, `BuyExactQuoteIn`, `SellV2`, `BuyExactQuoteInV2`, `SweepProtocolFee`,
`SweepCreatorFee`, `CloseUserVolumeAccumulator`. The V2 and Sweep instructions are not in the public IDL (see O-1).

### DLMM, CPMM, AMM v4, DAMM v2

The crate's parse gates and the boot mint rule were mirrored in Python over the fetched bytes, with the Clock at slot
453,411,180.

| Venue | Seed pools | Pass every gate | Dropped at boot (transfer fee) | Refused at parse |
|---|---|---|---|---|
| DLMM | 411 | 370 | 41 | 0 (pair: len 904, version 1, all 370; active bin array version 2, all 370; ±4 arrays: 2,550 version 2, none other) |
| DAMM v2 | 504 | 303 | 148 | 53 `sz_damm_liquidity` (empty pools; correct) |
| Raydium CPMM | 54 | 35 | 19 | 0 |
| Raydium AMM v4 | 34 | 34 | 0 | 0 (no Token-2022 side) |

- **Transfer-fee mints.** 56 distinct mints, all with a fee in force in epoch 1,049 (50-800 bps).
- **Transfer hooks.** 22 kept pools (17 DLMM, 5 DAMM v2) have a mint with the TransferHook extension, none with a
  program set: no drops. PumpSwap mints also carry it 12 times, none with a program set.
- **Other extensions.** 13 kept pools (10 DLMM, 3 DAMM v2) have Pausable, DefaultAccountState or PermanentDelegate
  mints. None is paused (see O-2).

## Real-program proof (LiteSVM, dumped pAMM ELF)

- **Setup.** The venue-harness was copied to scratch and renamed `venue-harness-rv`, so that cargo builds it from its
  own path. It used the existing `targets/venue-harness`.
- **Fixtures.** 9 more mainnet pools were fetched read-only with its `fetch-fixtures` (27 RPC requests):
  FKfR, 9htN, AZmU and 2z2u (300 B); EBNU (300 B, byte 270 = 1); 5PGh, 3KFC, 8ewu and 5wNu (301 B, byte 270 = 1).
- **Test.** `tests/exactness.rs`, limited to these pools, with an optional relaxation on the crate's side only: the
  pool bytes sent to the bridge are zero-padded to 301 and byte 270 is cleared. The venue swaps the real account.

| Run | exact | both refuse | aborted | MISMATCH |
|---|---|---|---|---|
| Crate as built (`abort:Layout` 6,350, `abort:Pump(UnknownTail)` 5,080) | 0 | 0 | 11,430 | 0 |
| Gates relaxed | **11,274** | 156 | 0 | **0** |

Every pool is exact in both directions: 40-42 sell sizes and 1,043 buy sizes each (the dense 10,000,000..10,001,000
run included), and the same under the `virtual_quote_reserves=0` and `creator_fee_bps=0` mutations.

## Claims check

| Claim | Result |
|---|---|
| Engine `cargo test --release` 330/0/2 | **Reproduced.** lib 305 (+1 ignored), bin 11, legacy_fixtures 4, meta_config_hash 1, runtime_isolation 2 (+1), stop_path 6, supervisor 1. Two warnings, pre-existing (`main.rs:440`, `:448`) |
| arbx-sizing 62 tests | **Reproduced.** `--all-features` 62, default 56, `--no-default-features` builds |
| venue-harness 16 tests: exactness 7,145 exact, adversarial 39,444 exact, 0 mismatches | **Reproduced** exactly: exactness 7,145 / 247 / 9 / 0 / 178 / 0; adversarial 39,444 / 2,921 / 160 / 169 / 607 / 0 |
| `tools/ci-venue-parity.sh` passes | **Each step reproduced**, but not run as one script: it builds in-repo target directories (F9). Steps: sizing suites; the harness suite, with `results/swap-runs.json` unchanged; `testdata/venue-parity/pools` equal to the fixtures; `capture_post` output byte-identical to `real-swaps.json`; `quote::` 7/7 |
| All quoting goes through the crate; `src/venues` keeps only decoders; the old maths is in `legacy` under `cfg(test)` | **Confirmed.** The legacy files are verbatim moves (imports aside; decoders stayed in `src/venues`) |
| Every crate refusal is a skip `sz_*` with a counter | Route decisions: **yes**, and every `Abort` has a reason and counter (tested). Boot drops: no (F8). Hints, probes and the monitor: generic counters only (F10) |
| 1,316 real swaps: crate exact; legacy PumpSwap 84/252, CPMM 40 and DLMM 41 off, 34 of them above, up to 1.2% | **Reproduced** in the test output (DLMM worst 11,909 ppm; PumpSwap ≤ 59 ppm; CPMM ≤ 61 ppm). The monitor: crate PumpSwap 252/252, CPMM 224/252 (the 28 are Hmx1, transfer fee), AMM v4 168/168, DLMM 216/216, DAMM v2 392/420 (the 28 are 2cUM). Exact-in swaps only (F6) |
| `DlmmLeg::fills`, host-only | Public and not `cfg`-gated (host-only by convention). It equals `quote` on 128,248 random swaps (`dlmm_fills_equal_the_quote`) |
| The stream follows the GlobalConfig and Token-2022 mints; boot drops fee and hook pools | **Confirmed in code.** Untested (F4) |
| p50 per evaluation about 10-15% slower | **Measured +15-25%** (F7) |

## Builds and tests I ran

All with `CARGO_BUILD_JOBS=5`. Scratch was `…/scratchpad/r3/wp16-review/`.

1. **Engine, in the worktree.** `CARGO_TARGET_DIR=…/targets/lanes cargo test --release`: 330 passed, 0 failed,
   2 ignored. `cargo test --release --lib quote:: -- --nocapture --test-threads=1`: 7/7, with the tables quoted above.
   `engine_benchmark_stage0_shapes -- --nocapture`, three times.
2. **Master for comparison.** `git archive 323e3bf` was exported to scratch, then the same benchmark ran three times in
   `targets/lanes`. That build compiled master separately (different dependencies, so a different unit hash). It also
   forced one rebuild of the lane afterwards, which was harmless.
3. **arbx-sizing.** `CARGO_TARGET_DIR=…/targets/arbx-sizing`:
   - `cargo test --release --all-features`: 62 passed;
   - `cargo test --release`: 56 passed;
   - `cargo build --release --no-default-features`: OK;
   - `--test venues dlmm_fills -- --nocapture`: 128,248 swaps checked.
4. **venue-harness.** `VENUE_HARNESS_REQUIRE_SIZING=1 VENUE_HARNESS_SIZING_DIR=<worktree>/program/arbx-sizing
   CARGO_TARGET_DIR=…/targets/venue-harness cargo test --release -- --nocapture`: 16 tests passed. The tallies are
   above. This is the run described under "Incident": it executed the binaries built from the worktree, so its results
   are the worktree's.
   - `capture_post` output was compared with `testdata/venue-parity/real-swaps.json` with `cmp`: identical.
   - The fixtures were compared with the testdata copy with `diff -r`: identical.
5. **Real-program proof.** Scratch harness copy `venue-harness-rv` (`targets/venue-harness`): `fetch-fixtures-rv
   --pools`, then `--test exactness` twice, with `WP16_ONLY=…` and with and without `WP16_RELAX=1`.
6. **Mutation probe.** A scratch copy of the lane renamed `arbx-rv` (`targets/lanes`) with mutations M1 and M2:
   `cargo test --release --offline --lib` gave 305 passed. In the same copy, after reverting the mutations, a
   micro-benchmark test was added (F7).
7. **RPC census.** Python scripts using the standard library only: `census_fetch.py`, `census_pump.py`,
   `census_other.py`, `census_dlmm_arrays.py` and `census_activity.py`, with outputs `accounts.json`,
   `census-pump.json` and `activity.log`. All read-only. No transaction was sent, nothing was signed, and no keys or
   `.env` were read.
8. **pump.fun public documents** were fetched read-only from GitHub: `idl/pump_amm.json` at main (last commit
   e0687ae9b7), and `HOLDER_REWARDS_README.md`, `NEGATIVE_VIRTUAL_QUOTE_RESERVES.md` and `PUMP_SWAP_README.md`.

### Incident (reverted)

- **What happened.** My first harness run was meant to use a scratch copy. Cargo instead reused the worktree-compiled
  test binaries: a standalone package gets the same unit hash at any path, `tar` kept the mtimes, and the dep-info
  pointed at the worktree's files.
- **What it wrote into the worktree's `program/venue-harness`:**
  - `results/{exactness,adversarial,swap-runs}.json`, regenerated. The two gitignored files have the same sizes as
    before, and `git status` shows `swap-runs.json` unchanged.
  - A new `target/` (171 MB of sizing-bridge builds). I deleted it at once.
- **Afterwards.** The worktree's diff sha256 is unchanged (`0aff38d4…`). All later probes used renamed packages so that
  cargo builds them from their own paths.

## Out-of-scope observations

- **O-1. The deployed pAMM program is ahead of the public IDL and of the engine's decoder.**
  - On mainnet it runs `SellV2`, `BuyExactQuoteInV2`, `SweepProtocolFee` and `SweepCreatorFee`, all seen on these
    pools. The Sweep instructions presumably drain the held-back buckets @271 and @279; I did not verify it.
  - `src/venues/cp.rs::decode_pending` knows only `sell`, `buy_exact_quote_in` and `buy`. V2 swaps therefore produce no
    hint and no prediction.
  - Whether V2 swaps keep fees in the vault, which would change the post-state bookkeeping, is unverified.
- **O-2. Token-2022 Pausable, DefaultAccountState and PermanentDelegate mints (xStocks) are not refused.**
  - They sit on 13 kept DLMM and DAMM v2 pools.
  - A paused mint would make every swap on its pools fail while the engine keeps quoting them. None is paused today.

## Disposition (2026-10-05, WP-16 commit)

The review's code is the uncommitted lane/wp-16 work on master 323e3bf; the fixes are in the same WP-16 commit. Every
build went to the scratch targets (`targets/lanes` for the engine, `targets/arbx-sizing`, `targets/venue-harness`), never
into the repository: the harness has no `target/` after the runs (F9).

**Results directory.** `program/venue-harness/results/swap-runs.json` is regenerated by the final run (868 swaps: the new
fixture pools) and committed; the CI script then reproduced it byte for byte. `exactness.json` and `adversarial.json`
are gitignored and are the final run's output (the reviewer's run had rewritten them; nothing of theirs is committed).

**Tests at the commit** (all `--release`, `CARGO_BUILD_JOBS=5`):
- engine: `cargo build --release` (the 2 pre-existing `main.rs:443/451` warnings); `cargo test --release` 334 passed, 0
  failed, 3 ignored (lib 309 + 2 ignored: 4 new; bin 11; legacy_fixtures 4; meta_config_hash 1; runtime_isolation 2 + 1
  ignored; stop_path 6; supervisor 1); `arbx check` exits 0 on `deploy/arbx-stage0.toml` and `deploy/arb.toml`;
- toolkit (`tools/arbx-report`): 79 OK, 4 skipped;
- arbx-sizing: `--all-features` 65 passed (3 new), default 59, `--no-default-features` and each venue feature alone
  build; the SBF build (`sbf-check`, all venues: 206,896 B, no stack warnings) and the `cu-runner` CU regression pass;
- venue-harness, `VENUE_HARNESS_REQUIRE_SIZING=1 cargo test --release`: 17 passed. Exactness 23,523 exact (6,362 of them
  PumpSwap exact-out buys), 1,035 TooLarge/ZeroOut agreements, 9 budget, **0 MISMATCH, 0 FALSE REFUSAL**; 1,448 refused
  sizes: the venue refuses 1,282 too (98ew cashback 1,270, transfer-fee dust 12), 166 are necessary refusals (Hmx1 and
  2cUM, 83 each). Adversarial 56,866 exact, 5,665 TooLarge/ZeroOut agreements, 160 budget, 169 venue CU limit,
  **0 MISMATCH, 0 FALSE REFUSAL**; 7,480 refused sizes, all refused by the venue too (Layout 3,460, Cashback 2,664,
  HeldExceedsVault 634, Damm(Liquidity) 461, Amm(Status) 174, Damm(RateLimiter) 87). Pins: PumpSwap 4,287 sells and
  59,400 `buy_exact_quote_in` exact; 11,477 exact-out `buy`s exact;
- `tools/ci-venue-parity.sh` with `SIZING_TARGET`, `HARNESS_TARGET`, `ENGINE_TARGET`: "venue parity: ok".

| # | Severity | Disposition |
|---|---|---|
| F1 | Blocker | **Fixed**: every length the program reads, pinned per read group on the real program |
| F2 | Blocker | **Fixed**: byte 270 is `is_holder_reward` (0/1 priced, another byte `Layout`) |
| F3 | Major | **Fixed**: every refusal is checked against the venue; the census's classes are fixtures (deviation below) |
| F4 | Major | **Fixed**: two tests, each shown failing under its mutation |
| F5 | Minor | **Documented** in MEASUREMENT (as asked); the code keeps the Clock for every venue |
| F6 | Minor | **Fixed for PumpSwap `buy`** (closed form, pinned); other venues' exact-out marked `solved`, out of the rate |
| F7 | Minor | **Fixed**: p50 and p99 back at master's (measured before / after, with master) |
| F8 | Minor | **Fixed**: events.jsonl `pools_dropped` and meta.json `pools.dropped` |
| F9 | Minor | **Fixed**: `VENUE_HARNESS_BRIDGE_TARGET` (default `CARGO_TARGET_DIR`); per-crate targets in the CI script |
| F10 | Minor | **Fixed**: `trigger_`/`probe_`/`pred_<reason>`; triggers.jsonl `skip` is the reason |
| F11 | Docs | **Fixed**: DESIGN §2.0, §2.1, §2.7 item 2, §5.3, §7 items 2 and 6; REVIEW.md F9 |

**F1, F2 (crate: `program/arbx-sizing/src/venue/pumpswap.rs`, `leg.rs`, `error.rs`).** Measured on the dumped pAMM
binary before writing the rule (scratch experiments, then kept as adversarial states):
- Below 211 bytes (the original layout, bump .. lp_supply) the program fails InvalidAccountData (204, 208, 210 tried);
  from 211 it swaps. The crate accepts 211..=301 (`POOL_MIN_LEN`, `pool_len_ok`) and refuses only a longer pool.
- The program reads a trailing field only when the pool holds all of it, and two pairs as one group: a partial virtual
  reserve reads as 0 (L = 246..260 mismatched a byte-wise zero fill), `creator_fee_bps` is read together with
  `can_edit_creator_fee` (6ejg at L = 262..269: the pool's 200 bps are ignored until 270), and the two held amounts
  together (L = 279..286 with held_0 set: the held capacity is that of no held amounts). The crate reads the same groups
  (`off::END_*`): the review's "copy into a zeroed `[u8; 301]`" would have mispriced partial groups. A coin_creator
  missing below 243 bytes is zero (the harness's and the engine's builders now read it as zero too, so such a pool also
  executes: `src/build.rs`).
- Byte 270 = 2, 3, 0x97, 0xba, 0xff fail the program (BorshIoError "Invalid bool representation"); 0 and 1 swap alike.
  The crate treats 243, 244, 269 and 270 as Borsh bools: another byte is `Layout`. 287..301 stay refused when set.
- Tests failing on the pre-fix crate (scratch copy, package renamed): `review.rs` `f1_f9_…` (a 211-byte pool is
  priced), `wp16_short_pools_read_their_missing_groups_as_zero` (60 states × 17 lengths × both legs: cut pool == full pool
  with its missing groups zeroed, capacity included), `wp16_mayhem_pools_price_on_the_fixed_supply`, `venues.rs`
  `pumpswap_aborts`. In the engine, `src/quote/tests.rs:397` is flipped (byte 270 = 1 is "ok"; = 2 is `sz_layout`) and
  the refusal test adds the census's pools (9qKx and FKfR at 300 bytes, EBNU, 5PGh, 3KFC, 8ewu, GxqG priced; 98ew
  `sz_pump_cashback`; DDGN a 287-byte pool) and the length bounds (210 and 302 `sz_layout`; 211, 243, 270, 287, 300 ok).
- On the real program, through the harness: the 300-byte pools (9qKx 7,223 SOL, FKfR, EBNU), the holder-reward pools
  (5PGh and 3KFC with V < 0 and held amounts, 8ewu with V > 0, EBNU), the mayhem pool and the 287-byte pool are exact in
  both directions (exactness, pins, and the adversarial cuts at every group boundary ±1 of every PumpSwap fixture).
- **Addition: mayhem.** The census's 2 mayhem pools would have been the next false refusal: on the real program GxqG
  prices exactly like a normal pool with its market cap on the fixed 1e15 supply (its mint's supply scaled ×1/1000 ..
  ×2000: the real supply mismatches from ×5, 1e15 is exact at every scale). The crate prices them
  (`MAYHEM_SUPPLY`); `Pump(Mayhem)` stays in the enum, never returned, so the AXZ1 codes do not move. Their events carry
  no buyback (pins.rs now expects that).

**F3 (harness: `tests/common/mod.rs`, `tests/exactness.rs`, `tests/adversarial.rs`).** Every refused size (an `Abort` at
parse or quote) is swapped on the venue. Venue fails or pays 0: "both refuse". Venue swaps: the leg is re-quoted with
the refused state taken out on the crate's side only (`lift`), and the refusal is a **FALSE REFUSAL** (a failure, like a
mismatch) when those maths equal the venue at every swapped size or when the refusal has no lift, a **necessary
refusal** when they are off at one of them at least. Run on the pre-fix crate (`VENUE_HARNESS_SIZING_DIR`) the exactness
suite reports 10,016 FALSE REFUSAL rows (Layout on the 300- and 287-byte pools, UnknownTail on the holder-reward pools,
Mayhem on GxqG) and fails; on the fix, none.
- **Deviation from "any case where the program succeeds is a failure".** The one refusal of a state the venue swaps that
  remains in the suites is the Token-2022 transfer fee (Hmx1 300 bps, 2cUM 100 bps; the review's census counted 208
  such boot drops). Its
  lift (the fee zeroed in the mint) is off on every swapped size (e.g. 2cUM: lifted 424 vs venue 420), so the refusal
  keeps a misprice out; the rule reports it as "necessary refusal" instead of failing. Pricing it would mean modelling
  Token-2022 fees in the crate (on chain too), which is not WP-16's.
- Read-only RPC in all (public mainnet endpoint, `getMultipleAccounts` and 45-byte `getAccountInfo` header reads only,
  paced): 99 requests (exploring 16 candidate pools in a scratch harness 48, `fetch-fixtures --check` 8, the fixtures
  27, the census 16). Nothing was sent or signed.
- Census classes in the fixtures (`fixtures/pool-list.json`: 12 PumpSwap pools): 300-byte (9qKx, FKfR), 300-byte with
  holder reward (EBNU), holder reward (5PGh, 3KFC, 8ewu), mayhem (GxqG), cashback (98ew: the venue fails every swap of the
  engine's leg, 6060 / 6061, and 6053 without a pool_v2, so the refusal is consistent; swaps.rs, api.rs and pins.rs check
  that instead of skipping it), 287-byte dust (DDGN); DAMM v2 zero liquidity as an adversarial state (`liquidity = 0`:
  the venue fails too). Fetched read-only with the harness's `fetch-fixtures` (27 `getMultipleAccounts`/`getAccountInfo`
  requests, ≤ 2.5/s); `--check` first: no venue program was upgraded since the dump.
- Two policy refusals are deliberately not in the suites, because on the dumped binary their synthetic states swap: a
  pool longer than 301 bytes (zero-extended to 302..400 it swaps like the 301-byte one) and a nonzero byte of 287..301.
  Both are kept by design (an unknown layout or field turns sizing off), cost no live pool, and are unit-tested in the
  crate and the engine.
- The adversarial suite now runs one pool's probes at a time: its peak RSS was 9.4 GB with the new states (the machine
  killed it once) and is 1.3 GB.

**F4.** `src/quote/tests.rs`:
- `the_stream_follows_every_account_a_quote_reads`: over every fixture pool, both directions, route and third-party
  legs, `quote::leg` runs on a store holding only what `Registry::static_accounts` (plus the DLMM arrays) follows: it must
  miss nothing and read nothing else; `watch_roles` and the readiness parts must cover it. Under the review's M1 (no
  GlobalConfig, no Token-2022 mint followed) it fails; under M1b (only the Token-2022 mints dropped) it fails through the
  quote ("3Bu5…: an account the quote reads is not followed: EN2nnxrg…").
- `accuracy_predictions_match_the_real_post_states` now asserts the counts: per venue `exact == n − allowed` with the
  allowed unpredicted swaps exactly the transfer-fee pools' (Hmx1 28, 2cUM 28), at least 160 swaps a venue, and the
  exact-out buys all exact. Under M2 (no PumpSwap prediction) it fails ("3KFC Quote: 84, 5PGh Quote: 84, …").
- The mutations ran in a scratch copy (`arbx-mut`, `targets/lanes`) and were not committed. Results: PumpSwap 1,344 of
  1,344 predicted exactly (legacy 198), CPMM 224/252, AMM v4 168/168, DLMM 216/216, DAMM v2 392/420.

**F5.** MEASUREMENT §4.34: the pre-state includes the Clock for every venue, with the consequence (one Clock version per
slot, `ring_versions` 8: a hint scored more than about 8 slots late is `pred_pre_state_unknown` for every venue).

**F6.** `pumpswap::buy_exact_out` / `PumpLeg::quote_exact_out` (host only): `q = ⌈Qv·out/(B − out)⌉`, debit
`q + fees(q)`; 0 fails 6001, the whole reserve or a quote past u64 fails too. Pinned by `pins.rs`
`pumpswap_exact_out_buy_matches_its_closed_form` (11,477 buys) and quoted through the bridge in the exactness suite
(6,362 exact). The harness builds the `buy` (`BuildOpts::exact_out`) and `capture_post` records it (2,534 real swaps
now). The engine uses it in the hint check (the exact debit against the limit) and the accuracy monitor (420 of 420
recorded exact-out buys predicted exactly; legacy 30). The other venues' exact-out swaps (CPMM `swap_base_output`, AMM v4
base-out, DLMM `swap_exact_out`) keep the solved input: predictions.jsonl marks them `exact_out_model` "solved", and they
are kept out of the per-venue exact rate (counter `pred_exact_out_solved`; the toolkit's R8 counts them apart, and now
also tells `refused` and `unquotable` lines from `pre_state_unknown` ones).

**F7.** Measured with the per-leg micro-benchmark `quote::tests::per_leg_cost` (ignored test) and the Stage-0 benchmark,
interleaved over 7 rounds, master 323e3bf, WP-16 as built and the fix each built as a renamed package:

| Measure (median) | master | as built | fixed |
|---|---|---|---|
| Stage-0, 4 pools/pair, p50 / p99 µs | 8 / 24 | 10 / 27 | 9 / 23 |
| Stage-0, 8 pools/pair, p50 / p99 µs | 16 / 40 | 19 / 47 | 16 / 40 |
| `quote::best`, AMM v4 route without a gap / with a 1% gap, ns | | 340 / 453 | 75 / 343 |
| DLMM leg parse, ns | | 99 | 82 |

The opportunities are identical in the three (2,876 and 5,055). What changed: `quote::best` stops the ladder at the first
rung whose exact profit falls (the profit is concave; `sizing_stops_at_the_first_falling_rung` checks the premise and the
result against the whole ladder on the HOTBOT route at 8 gaps and on every PumpSwap, CPMM and AMM v4 fixture against
itself at 6 gaps both ways, at least 60 routes), each pool's legs are parsed once per evaluation (pool `i` is in
all 2(k−1) routes), and the DLMM leg's arrays are on the stack. The quotes themselves are unchanged: the crate's
per-quote arithmetic (the SBF-oriented u128 division) stays about twice the legacy maths' for AMM v4, CPMM and PumpSwap,
so caching parsed legs per account version, the review's suggestion, would save little (a parse is 15-80 ns).

**F8.** `pools::boot` returns the candidates it drops with why (`missing`, `owner`, `layout`, `transfer_fee`,
`transfer_hook`, `mint_layout`, the mint named): events.jsonl `pools_dropped` at boot and meta.json `pools.dropped`
(MEASUREMENT A.6, §4.29); `arbx pools` prints them. Test: `pools::tests::boot_names_every_candidate_it_drops`. The PumpSwap
boot rule follows the crate (≥ 211 bytes instead of ≥ 253).

**F9.** `tests/common::build_bridge`: `VENUE_HARNESS_BRIDGE_TARGET`, else `CARGO_TARGET_DIR`, else `target/`.
`tools/ci-venue-parity.sh` takes `SIZING_TARGET`, `HARNESS_TARGET`, `ENGINE_TARGET` (each over `TARGET_BASE`).

**F10.** `quote::REASONS` carries each reason's four counters; `hint_check`, `probe_routes` and the monitor count
`trigger_`/`probe_`/`pred_<reason>` for the crate's reasons (the generic `*_unquotable` stay for missing accounts and
sizes the venue cannot fill), and triggers.jsonl `skip` is the reason. Test:
`engine::tests::hints_probes_and_the_monitor_carry_the_crates_reason`.

### Census before / after

Re-run read-only on 2026-10-05 (slots 453,439,5xx-453,439,7xx; 16 `getMultipleAccounts` calls of ≤ 100 keys, one every
2 s): every PumpSwap pool of `data/seed-pools-w4.csv` ∪ `data/seed-pools-merged.csv` (392; 389 live: 312 × 301 B,
14 × 300 B, 63 × 287 B; byte 270 = 0 on 355, 1 on 34) through arbx-sizing's `pumpswap::parse` as the engine's route leg
calls it, with the engine's boot rules, built against the crate before and after the fix:

| WSOL-quoted live pools (258) | Before (as built) | After |
|---|---|---|
| Priced | **212** (112,787 SOL of quote) | **255** (161,319 SOL) |
| `sz_layout` (the 14 × 300 B) | 14 (12,455 SOL) | 0 |
| `sz_pump_unknown_tail` (byte 270 = 1) | 27 (36,069 SOL) | 0 |
| `sz_pump_mayhem` | 2 (8.6 SOL) | 0 |
| `sz_pump_cashback` | 3 (909.5 SOL) | 3 (the venue refuses the engine's leg too) |

43 pools gained (48,533 SOL), none lost. The 131 non-SOL pools (the 63 dust pools of 287 bytes among them) stay
`pump_quote_not_sol` as routes; a third party's swap on them is now priced. Master's rule gives about 225.

### Deviations

- F3: the transfer-fee refusal is a "necessary refusal" (proven per leg), not a failure (above).
- F1: the shorter pool is read per read group, as measured on the program, not with a byte-wise zero fill.
- Additions beyond the findings: mayhem pools priced (they would have been the suites' next false refusals); the
  adversarial suite processed per pool (memory).
- F5 is documentation only, as asked (the code keeps the Clock for every venue).

### Files outside the plan's list

`src/build.rs` (one line: a coin creator missing from a short pool is zero, like the program; WP-06 owns the builder),
`src/main.rs` (the boot drops recorded), `tools/arbx-report` (R8, its test, `gen.py` and the golden report), and in the
crate and the harness beyond the original diff: `program/arbx-sizing/src/{error,leg}.rs`, `REVIEW.md`; harness
`src/{fixture,harness,venues}.rs`, `sizing-bridge/src/main.rs`, `tests/{common,api,pins,route,swaps}`,
`fixtures/pool-list.json` and 9 fixture pools.

### Open issues

- Cashback coins: the cashback bps source is not pinned, and the engine's (and the harness's) PumpSwap leg cannot
  execute one (6060 / 6061 with a pool_v2, 6053 without). 3 live pools, 909.5 SOL.
- Token-2022 transfer fees are not modelled (208 boot drops in the census; refused as necessary).
- Policy refusals with no live case: a pool longer than 301 bytes, a set byte of 287..301.
- Exact-out swaps of CPMM, AMM v4 and DLMM are still solved through exact-in quotes (marked, out of the rate).
- The crate's per-quote arithmetic is about twice the legacy maths' on the host; a host-native u128 division would halve
  it but split the arithmetic between host and SBF.
- O-1 (pAMM V2 instructions not decoded) and O-2 (Pausable / PermanentDelegate mints) stand.
- Incident: a `cargo clean -p arbx-mut` on the shared `targets/lanes` (to drop the mutation copy's artifacts) removed
  every cached artifact named `arbx` there (1.9 GiB, the WP-09 lane's included); only build cache, rebuilt on the next
  build; no source was touched.

### Merge notes

- Master is about to receive WP-05, which rewrites `src/exec.rs`; WP-16 leaves `exec.rs` alone. Exec's
  `expected = back − size` and the decisions' `gross = back − buy debit` differ by the PumpSwap `buy_exact_quote_in`
  debit rule (`min(x, eff0 + fees(eff0))`: 1 lamport below `x` in 31 of 59,400 pinned buys). Unify them at the merge on
  the debit (the guard's quote delta), so a decision and its send agree to the lamport.
- `src/build.rs`'s one-line change may meet WP-06's builder work.

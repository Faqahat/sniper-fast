# Plan changes in response to the adversarial review

**Date:** 2026-10-04. **Review:** `docs/reviews/plan-review.md` (44 findings: 1 blocker, 13 major, 30 minor). **Revised:** `docs/PLAN.md` and `docs/MEASUREMENT.md` (both now "revision 2").

**Also changed:** the arb-lab run files most at risk were preserved in `testdata/legacy/raw/` (5.3 MB, xz, with sha256 and a README) because their only local copy was a session-scoped scratch directory (F12). No bot code was changed.

## Summary

| Disposition | Count | Findings |
|---|---|---|
| Applied as proposed | 35 | F2, F4, F6-F9, F11-F36 except F31, plus F40, F41, F43, F44 |
| Applied with a variant (the reason is given below) | 5 | F1, F3, F5, F10, F39 |
| Partly applied (the rest is not possible; stated in the plan) | 1 | F42 |
| Resolved as an owner decision, with the plan's default stated | 3 | F31, F37, F38 |
| Not applied | 0 | — |

The reviewer also noted, under "Checked and found correct", that the `InnerInstructions {index 1, instructions 2}` wrapper was missing from the proto list. It is now in WP-03 item 4.

**New measurements used in the revision** come from arb-lab recordings (w5h-p1, w5h-p9, w5h2-p1 moves logs and w5h-p1 status). They are in PLAN §0 and MEASUREMENT §5:
- 3.72 slots/s;
- 31-60 watched transactions/s on 300-377 moving pools;
- 41-48% of those touching a PumpSwap pool.

These replace the reviewer's assumed 2.5 slots/s and give the sizing for F1 and F10.

---

## Blocker

### F1. Exec results for every watched account; the arb-lab exec.jsonl regression
**Applied with a variant.**

| Reviewer's fix | What the plan now does | Where |
|---|---|---|
| 1. Keep the single gRPC transaction filter on PumpSwap | Kept on PumpSwap: arb-lab parity, block index, authoritative W(T) for PumpSwap | PLAN WP-03 item 3 |
| 2. Find wallet transactions from wallet account updates | Wallet signatures come from four sources, and each is fetched once with a bounded getTransaction (a few per minute): the `txn` of wallet and wallet-token-account updates, our attempts, Jito `processed` results, and an hourly `getSignaturesForAddress`. The assumption that failed landings write the wallet is checked in the field (`wallet_update_missing`) | PLAN WP-03b item 1; MEASUREMENT §4.15 |
| 3. Size the backfill from the measured rate | `rps = "auto"` sizes itself to 1.25 × the measured uncovered rate, capped per provider. `need_rps_now` against `have_rps_now`, the backlog and drops are in status. Measured scale: non-PumpSwap watched transactions are about 16-35/s on the w5h registry. A second filter or provider is OD-1, with those numbers | PLAN WP-03b item 2, §9 OD-1; MEASUREMENT §4.8, §5 |
| 4. Block index via getBlock per slot or a `blocks` filter | One `getBlock` per confirmed slot with `transactionDetails: "signatures"`. The signature order is the block index; it is checked against the PumpSwap stream's `idx` every slot. This is shared with the toolkit's blockctx and with R4. A Yellowstone `blocks` filter is probed (WP-03 item 5) and is option (b) of OD-1 | PLAN WP-03b item 3; MEASUREMENT §4.16b |
| 5. Remove the escape clause | Removed. The Stage-0 gate is firm. Invariant 10 ("No hidden shortfalls") was added, and the only way to exit without the capacity is an explicit owner waiver, OD-1 option (e), written into PLAN §9 | PLAN §2, §6, §9 |

**Variant, and why.**
- The block index comes from signatures-only blocks (about 100-300 KB each), not full blocks (several MB each at 3.7/s), which keeps both bandwidth and parsing small.
- Full blocks are fetched only once a minute, as a sampler that measures the share of watched-touching transactions no source told us about.
- The coverage denominator is defined explicitly as D1 ∪ D2: transactions that wrote a watched account, plus shred-seen watched transactions that the slot index shows landed. D2 brings in failed transactions, which write nothing and which revision 1 would have missed.

---

## Major

### F2. Commit groups assumed an authoritative W(T) that Stage 0 does not have
**Applied.**
- **Sources named:** WP-04 item 3 now names the three Stage-0 W(T) sources plainly: `tx-stream` (PumpSwap only), `shred` (a hint; 5 of 10 feeds dead) and `unknown`.
- **Unknown W(T):** groups resolve by quiescence, and in addition a route is evaluated only when every account of both pools has been quiet for `quiescence_ms` (reason `route_not_quiet`).
- **`quiescence_ms` is set from data:** the measured p99.9 of the intra-transaction update spread (`commits.spread_ms`).
- **Late members:** they are detected (`late_member`), and decisions priced in between are flagged `torn_suspect`.
- **Acceptance metrics:** group share and lag by `w_src`, and the late-member rate (target ≤ 0.1% of unknown-W groups). The Stage-0 gate allows `torn_suspect` sends ≤ 0.1%.
- **New scenarios:** S1b (split route not seen in shreds) and S1b' (a late member).
- **Where:** PLAN WP-04 items 3 and 10, WP-09 scenarios, §6; MEASUREMENT §4.31, §4.32.

### F3. The parts-skew rule was over-broad; the PumpSwap exemption was removed blind
**Applied with a variant.**
- **Consistency sets:** skew is defined per pool over its consistency set, never across pools:

  | Venue | Consistency set |
  |---|---|
  | PumpSwap | {vault0, vault1} |
  | Raydium CPMM | {pool, vault0, vault1} |
  | Raydium AMM v4 | {vault0, vault1}; the amm account is measured first |
  | DLMM | {lb_pair}, plus the arrays the quote crosses must not be pending |
  | DAMM v2 | {pool} |

- **Other parts** (fee and global config, mint extras, the bitmap extension, the PumpSwap pool account) must be present and not pending, with no age rule.
- **Why the exemption existed:** neither the research nor the code records it. The code itself suggests the reason: it waits only for the vaults of a PumpSwap pool (`state_trigger` engine.rs:209, `check_prediction` :930), so the pool account is evidently not written by swaps. The plan states this and measures it from WP-03 recordings before the rule goes live.
- **Negative tests:** S4b and the WP-04 unit tests check that an idle sell pool 500 slots old is not refused, and that a PumpSwap pool account 10,000 slots old with fresh vaults is not refused.
- **Variant:** the threshold stays at today's 2 slots (store.rs:59) instead of revision 1's 1, because revision 1 gave no reason to tighten it.
- **Where:** PLAN §1 row 3, WP-04 item 4; MEASUREMENT §4.32 `parts_skew_slots`.

### F4. Forks: only `dead` slots were handled
**Applied.**
- A slot tree is built from slot updates with their `parent`. When a slot is confirmed, the slots off its ancestry are abandoned.
- `dead` slots and slot-index `missing` signatures are additional evidence.
- On abandonment: versions are dropped from the 8-version ring, the canonical version is restored or refetched, routes are marked dirty, and groups become `fork_dropped`.
- New: reason `fork_pending` while two siblings are both unconfirmed, and the counter `fork_priced`.
- SLOT journal records carry `parent`. New scenario S8b.
- **Where:** PLAN WP-04 item 9, WP-09 S8b; MEASUREMENT §4.13, §4.8 `forks`, A.1, A.6.

### F5. The accuracy monitor would have quarantined correct maths
**Applied with a variant.**
- **In the bot:** decoded hints are scored against T's pre-state, the version just before T's write from the ring, using T's executed input when it is known. `pre_state_unknown` is counted and never scored. The at-hint (v1) comparison is kept beside it. Quarantine is log-only in Stage 0 (`accuracy_action = "log"`), and the floor is set after measurement (OD-8).
- **Variant:** "Every successful swap", including aggregator-routed ones, and R §3.3's closer check are computed offline in the toolkit's R8, through `arbx quote` on `accounts.bin` pre-states and `exec.jsonl` inner instructions, not in the engine. That keeps per-swap decoding of inner instructions off the engine thread.
- **Where:** PLAN WP-04 item 13, WP-07 item 5, WP-10, §9 OD-8; MEASUREMENT §4.34, §6.4 R8.

### F6. No WP for "49% of attempts on the 21 pools with 150 or more bots"
**Applied.**
- **WP-00:** `data/crowded-pools.json` (the 21 pools from the PATTERNS item 10 analysis) gives rank 2 in `Prio`, so these pools queue last. Attempts carry `crowded`, and drops are split.
- **WP-05:** a crowding term in `Prio` from the activity map (distinct arbitrage signers per pool over 6 h), with reason `crowded_pool`.
- **The exclusion alternative** (bands ≥ 100k) is OD-3.
- **Where:** PLAN §1 row 32, WP-00, WP-05 item 5, §9 OD-3; MEASUREMENT §4.32, §4.37, A.1.

### F7. The ledger's equity and category definitions contradicted each other
**Applied.**
- **Definitions:** liquid equity, recoverable rent and total equity are now defined explicitly. Non-recoverable rent (the 1,346,200 accumulator) is expensed when it is created and is never an asset.
- **Summing and informational fields:** the categories that sum to `equity_delta` are separated from the informational fields (`rent_locked`, `rent_reclaimed`, `liquid_delta`, `stranded`, `inventory_reval`).
- **Reconciliation** runs on both bases. `inventory_reval` is defined so that the residual does not depend on valuation, and raw token amounts must match exactly.
- **Golden examples** are given as a table and are WP-07 tests: create only, create and close, accumulator creation (p6#69), ATA left open, failed, wrap, unwrap.
- **Where:** PLAN WP-07 item 1 and its tests; MEASUREMENT §4.42-§4.44, A.3, §6.2 rule 3.

### F8. Equity stops could not span segments
**Applied.**
- `--campaign-dir` (WP-01). At boot, the supervisor loads the campaign's earlier segments' ledger and snapshots for 24 h.
- The rolling `drop_1h` and `drop_24h` are defined as peak-to-current.
- An hour breach puts the bot in shadow, and later segments start with `--shadow` until it clears.
- A day breach exits 20, which ends the campaign.
- `run-w.sh` checks `arbx campaign-equity` before every segment.
- Tested with two simulated segments.
- **Where:** PLAN WP-01 items 7-8, WP-07 items 5 and 8; MEASUREMENT §4.2 `campaign_dir`, §4.8 money, §4.48.

### F9. One 2-thread runtime shared by hot I/O and heavy background work
**Applied.**
- WP-02 splits the runtimes:
  - `rt_hot` (today's 2 workers) runs state, feeds, Jito and keep-alive only;
  - `rt_bg` runs every RPC call, including the existing lookup-table and DLMM-array fetches.
- Responses over 256 KiB are parsed in `spawn_blocking`, and a debug assertion catches RPC polled on hot threads.
- **Offline isolation test:** 5 MB blocks at 4/s on `rt_bg`. Arrival → dequeue p99 and dequeue → `t_sent` p99 stay within 10%.
- **Where:** PLAN §1 row 33, §2 invariant 5, WP-02 item 1; MEASUREMENT §4.10 `runtimes`.

### F10. The blockctx windows and fetch rate could not meet their acceptance
**Applied with a variant.**
- The bot no longer fetches blocks per attempt window. The slot index (F1) fetches each confirmed slot once, with signatures only.
- `blockctx` is derived by the toolkit from `accounts.bin`, `slotidx.jsonl` and `exec.jsonl`:
  - the window is the reviewer's [trigger slot, max(landed, last verdict, trigger + 4)] + 1;
  - slots are deduplicated across attempts;
  - gaps can be filled offline with a rate-limited full `getBlock`.
- The need-rps and backlog gauges cover the chain-fetch service.
- **Variant:** this is the reviewer's "fetch each slot once into a shared cache" option. It is combined with moving the derivation offline, which also makes it deterministic and testable.
- **Where:** PLAN WP-03b item 3, WP-08 (blockfetch removed), WP-10; MEASUREMENT §4.16b, §4.41.

### F11. Replay: journal in the wrong WP, determinism gaps, false parallel-lane claims
**Applied.**
- **The journal moved into the core lane** (WP-03). The run loop becomes `Engine::step(ev, t_engine)` and `Engine::timers(t)`:
  - the clock is read once per event and journaled;
  - every timer evaluation is a TIMER record;
  - leader, blockhash, gate, quarantine, in-flight and health inputs reach the engine as journaled INPUT events.
- **Replay-class streams:** `accounts` and `journal` are a "replay" class, with large queues, sequence numbers and GAP records. Replay refuses gap intervals, and the Stage-0 exit requires zero drops.
- **What replay compares:** engine-side fields and journaled-input reasons only. The timing-dependent send-queue outcomes are taken from the recording.
- **Recordings before WP-03** are stated to be non-replayable.
- **Lane claims corrected:**
  - `Engine::new_offline` is in WP-02;
  - `exec::send_checks` and `src/proglog.rs` (taking `meaning` and `delivered_from_logs`) are created in WP-05;
  - WP-08 touches neither `exec.rs` nor `build.rs`;
  - WP-09 adds new files plus two `main.rs` arms and uses only those public APIs.
- **Where:** PLAN §3.1, §3.2, WP-02 item 11, WP-03 item 11, WP-05 items 2, 10 and 11, WP-08, WP-09; MEASUREMENT §1.2, §4.12, §4.13.

### F12. Acceptance depended on data outside the repo and on runs on Cherry
**Applied.**
- **WP-00b (0.5 d)** was added, and its first step is already done: attempts, outcomes, bundles, copies and status of w5h-p1..p10, w5h2-p5 and w5h3-p2 are in `testdata/legacy/raw/`. They were checked for secrets, and `meta.json` and `.out` were excluded.
- **WP-00b's remaining work:** the signature list, the expected values, wallet transactions from public RPC, and the files the owner must copy from Cherry (`seed-pools-w4.csv`, the per-pool bot counts).
- **Every WP's acceptance is now split** into "Offline (CI)", which gates the merge, and "Field (owner-run)".
- **Fixtures for later WPs:** WP-03 builds a synthetic prost-encoded stream fixture (`testdata/grpc/`) that WP-04 also runs through `forward` and the offline engine, and WP-03b uses recorded RPC responses (`testdata/rpc/`).
- **Where:** PLAN §0, WP-00b, every WP; MEASUREMENT §6.5; `testdata/legacy/README.md`.

### F13. WP-02's latency gate could not be measured
**Applied.**
- WP-00 adds state-path stage timestamps: update receive, dequeue, decided, signed and fired.
- WP-00 also adds the series `state_recv_to_engine`, `state_engine_to_decided`, `state_recv_to_decided`, `decided_to_signed` and `signed_to_fired`, and records their baseline in the WP-00 shadow run.
- WP-02 gates on them, and adds an offline engine benchmark with the recorder on and off.
- **Where:** PLAN §1 row 34, WP-00, WP-02 acceptance; MEASUREMENT §4.37, A.8.

### F14. The bundle blockhash had one source, no probe and no fallback
**Applied.**
- **`arbx grpc-probe`** (WP-03) tests the full account list, interslot slots, `blocks_meta`, the transaction filter with 1, 2 and 5 accounts, `blocks` with `account_include`, and deshred with 5 programs. It must run before WP-05.
- **The blockhash ring has four sources:** `blocks_meta` if offered, the slot index, the shred/entries last entry hash, and a 400 ms `getLatestBlockhash` poll on `rt_bg`.
- `attempts.blockhash.src` is recorded, and disagreement is an event.
- **Where:** PLAN WP-03 items 5-6, WP-03b item 4, WP-05 item 2, §9 OD-2; MEASUREMENT §4.37, §4.49.

---

## Minor

| # | Disposition | What changed | Where |
|---|---|---|---|
| F15 | Applied | Evidence corrected: `filter_by_commitment: false` already delivers all commitment levels; only interslot updates are off, and the engine ignores the status | PLAN WP-03 Evidence |
| F16 | Applied | The early return moved after the signer check, the slippage check, `checks.insert` and `trig_pending.insert`, and before `preds.insert`. `skip_failing_signers` works, signer stats keep learning, and `predictions.jsonl` keeps its data (revision 1's "predictions pause" risk is gone) | PLAN WP-00 |
| F17 | Applied | Expected and not-expected shadow files listed (no `poh.log` until WP-08) | PLAN WP-00 field acceptance |
| F18 | Applied | DoD: the existing tests minus `fee_rule` and `gate` (deleted in WP-05), with `tx_error_decodes_custom_codes` moved in WP-02; the count goes in the merge note | PLAN §0 |
| F19 | Applied | `arb-w-live.toml` moves to `deploy/legacy/` and is excluded from the DoD; `arbx-stage0.toml` paths are repointed to `/root/arbx`; `seed-pools-w4.csv` comes from Cherry via WP-00b, `seed-pools-merged.csv` stands in until then, and the seed list is part of OD-4 | PLAN WP-00, WP-01 item 2, §7 |
| F20 | Applied | `rerun-if-changed` also covers the resolved ref file, `packed-refs` and `.git/index` | PLAN WP-01 item 3 |
| F21 | Applied | The programdata ELF-end hashing procedure is documented and tested on the 8K8uyQDt account fetched into `testdata/programs/` (expects md5 `809315be…`). This revision did not re-derive the hash itself; the WP-01 test does | PLAN WP-01 item 4; MEASUREMENT §4.2 |
| F22 | Applied | One band table `[bands] edges = [20k, 100k, 1M, 10M]` over the expected edge (gross − base fee, before the tip), 5 bands, used by decisions, the queue (bands 3-4 throttled) and tips | PLAN WP-05 item 5, WP-06 item 8; MEASUREMENT §4.32 |
| F23 | Applied | Stage-0 defaults `margin_floor = 1`, `margin_share = 0` (today's on-chain behaviour); 2,000 / 2% is a WP-11 arm (OD-5); the 3 wins it would have reverted are named | PLAN WP-05 item 8, WP-11, §9 OD-5 |
| F24 | Applied | The store's stale verdict is in the journal ACCOUNT record; accounts flag bit2 is reserved | MEASUREMENT §4.12, §4.13; PLAN WP-03 item 1 |
| F25 | Applied | Every accounts record gets `aseq`; the journal references `aseq`; streams rotate independently | MEASUREMENT §1.3, §2.3, §4.12, §4.13 |
| F26 | Applied | Class lists aligned between PLAN and MEASUREMENT (control and stop are core; accounts and journal form the replay class); keyframes are not a droppable item | PLAN WP-02 item 2; MEASUREMENT §1.2 |
| F27 | Applied | Recording gate: core and replay 0 drops, chain < 0.01%, bulk < 0.1% | PLAN §6; MEASUREMENT §1.2 |
| F28 | Applied | Jito token refreshed in the background at half its lifetime; the send path reads only the cached token (reason `jito_auth_stale`); the test counts every network call, Jito unary calls included | PLAN WP-05 item 2; MEASUREMENT A.1 |
| F29 | Applied | `Rpc::only` takes a role; stats aggregate per (role, provider) | PLAN WP-03b item 5; MEASUREMENT §4.10 |
| F30 | Applied | `eprintln!` diagnostics also go to `events` (kind `log`); `<segment>.out` is in the layout | PLAN WP-02 item 8; MEASUREMENT §1.1, §4.5 |
| F31 | Owner decision (OD-7); residual risk stated | The passphrase stays in bash memory; mitigations listed (no argv or env, pipe, `ulimit -c 0`, history off, cleared at exit); an `arbx campaign` Rust launcher (about 1 d) is OD-7 | PLAN WP-01 item 8, §9 |
| F32 | Applied | `slo_action = "log"` in Stage 0; with `"shadow"`, 10 good minutes return the bot to live; a core-record-loss shadow lasts until the segment ends | PLAN WP-02 item 5, WP-04 item 8, §9 OD-9; MEASUREMENT A.5 |
| F33 | Applied | First-shred time is the minimum over unexecuted feeds only | PLAN WP-04 item 8; MEASUREMENT §4.31 |
| F34 | Applied | Snapshots use `minContextSlot` with a common slot, up to 3 retries, else `slot_mismatch` and no reconciliation for that window | PLAN WP-07 item 3; MEASUREMENT §4.43 |
| F35 | Applied | WP-10's R4, R8 (all swaps) and X3 depend on WP-09; without `arbx quote` those sections are marked incomplete | PLAN §3.1, WP-10; MEASUREMENT §6.1 |
| F36 | Applied | The CU table is built per leg from the `consumed X of Y` logs of every watched transaction (rivals included), plus our measured overhead | PLAN WP-06 item 4; MEASUREMENT §4.48, §6.4 cu-table |
| F37 | Owner decision (OD-4) | The Stage-0 size cap is the owner's; the config ships the live value 4.2 SOL, recorded in `meta.limits` with its source; R §3.8's ladder is the alternative | PLAN WP-00, §9 OD-4; MEASUREMENT §4.2 |
| F38 | Owner decision (OD-6) plus a target | The dependency on dead feeds is named; gauge target `poh_trigger_pct` ≥ 90% while a PoH-capable feed is alive | PLAN WP-08 item 2, §9 OD-6 |
| F39 | Applied with a variant | Jito: the validators API (`kobe.mainnet.jito.network/api/v1/validators`; the implementer confirms the endpoint). BAM: identities seen in our bundle results' `validator_identity`, plus a public list if one is identified. Static fallback is dated. **Not adopted:** inferring Jito-client leaders from tip transfers in their blocks, because a tip transfer can land through any leader as an ordinary transaction, so it is weak evidence | PLAN WP-03 item 10; MEASUREMENT §4.27 |
| F40 | Applied | RTT is labelled "host → leader TPU-QUIC (not the bundle path)"; attempts also carry `be_rtt_ms` (block-engine keep-alive) | PLAN WP-05 item 7, WP-08 item 1; MEASUREMENT §4.27, §4.37, R6 |
| F41 | Applied | WP-15 text updated: `lib.rs` already holds v2 and v3; also noted are the new program id, the 3 v2 execution differences and the AXS1 summary record (about 130 log bytes, about 200 CU) | PLAN WP-15 |
| F42 | Partly applied | S16 added. w5h3-p2#664 (CP family) is rebuilt from the landed transaction's pre-token balances plus the current pool config. p10#156 (DLMM) is best effort: historical bin arrays cannot be fetched from public RPC. If it cannot be rebuilt, it stays a documented open item, and the first Stage-0 recording with a ≥ 1% mispricing becomes the fixture | PLAN WP-09 S16 |
| F43 | Applied | Before `not_landed_expired`, one bounded `getSignatureStatuses` (`searchTransactionHistory`); later landings write `amend: true` outcome lines | PLAN WP-05 item 9; MEASUREMENT §4.40, A.2 |
| F44 | Applied | Stated in WP-00's risk. The worst instance is removed now: the attempt line is no longer flushed between signing and firing (exec.rs:611 before :624). The rest is measured by recorder-on and recorder-off shadow runs | PLAN §1 row 35, WP-00 |

---

## Other changes made while revising

- **WP-00:** the deshred feeds gain the DAMM v2 program in `account_include`. Today no DAMM v2 hint or shred W(T) arrives from them (arb-w-live.toml:109, :115).
- **`--drain-s` default 90 → 60:** at the measured 3.72 slots/s, a blockhash is valid for about 40 s.
- **Effort and calendar:** Stage 0 is now about 36 engineer-days, of which the core lane is about 24, and about 25 calendar days with lanes A, C, B1, B2 and B3.
- **Owner decisions:** collected in PLAN §9 (OD-1 … OD-10).
- **MEASUREMENT stop reasons are split** into process stop reasons and SendGate shadow reasons. Revision 1 listed shadow-only causes such as `equity_hour` and `reconcile_miss` as stop reasons.

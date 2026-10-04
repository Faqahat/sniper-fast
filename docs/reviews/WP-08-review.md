# WP-08 review: telemetry (leaders, PoH, transfer classification), part 1

**Date:** 2026-10-04. **Reviewer:** adversarial review, read-only (no code changed).
**Plan:** `docs/PLAN.md` WP-08 (items 1-4, offline and field acceptance, measurement outputs), `docs/PLAN-ADDENDUM.md` (the WP-08 tip-account map; I-9, whose sampling is assigned to WP-08), `docs/MEASUREMENT.md` §4.14, §4.21, §4.23, §4.24, §4.27, §4.28, §4.37 and §5, and the WP-03 hand-offs (`docs/reviews/WP-03-review.md`, commit ab4e6ee).

## What was reviewed

- **The implementation.** The uncommitted work in `.claude/worktrees/lane-wp-08` (branch `lane/wp-08` at ab08b9a):
  - 14 modified files: `data/sender-tip-accounts.json`, `deploy/arbx-stage0.toml`, `docs/MEASUREMENT.md`, `src/config.rs`, `src/feeds/{entries,mod,shred}.rs`, `src/leaders.rs`, `src/lib.rs`, `src/main.rs`, `src/rec/{exec,mod}.rs`, `src/send/tpu.rs`, `tools/capture-fixtures.py`;
  - new files: `src/classify.rs`, `src/classify/tests.rs`, `data/ip-geo.csv`, `data/platform-fee-wallets.json`, `testdata/classify/`, `testdata/leaders/`.

  Master has since moved to 9bfd72d (the addendum's go-live gate and `tools/secret-scan.py`); neither commit touches these files.
- **Build and tests.** I ran them myself in the lane (`CARGO_TARGET_DIR` = the shared lanes target, 5 jobs):
  - `cargo build --release`: the 3 known warnings.
  - `cargo test --release`: **216 passed, 0 failed, 2 ignored**. That is lib 193 (+1 ignored), bin 9, legacy_fixtures 4, meta_config_hash 1, runtime_isolation 2 (+1 ignored), stop_path 6, supervisor 1.
  - Toolkit: 78 OK (4 skipped). `testdata/legacy` unittest: 16 OK. `capture-fixtures.py --verify`: 232 files, 0 problems. The new classify and leaders fixtures are not in that manifest.
  - `arbx check` exits 0 on `deploy/arbx-stage0.toml` and on `deploy/arb.toml`. I ran it with a copy of this lane's binary, taken right after its build, because the other lane writes the same `release/arbx`. It prints the geo table and the RTT probe.
- **Independent checks:**
  1. **cmp2 rivals.jsonl, recounted** (603 MB, streamed): 849,585 rows, 744,411 of them `why = venues` (87.6%), and 43,707 with an unnamed tip. The new map names Glaive 4,197 rows, Soyas 458, bloXroute 72 and Solami 16, as the test says.
  2. **Tip sources, checked live:** `glaive.trade/tip-accounts` (6), `api.solami.dev/onchain/tip-addresses` (15) and `allenhark.com/docs/infrastructure/relay` (11) match the file exactly. I did not fetch the Soyas, SpeedLanding or archived bloXroute and SVS pages.
  3. **Kk7Nd3 fixture, from its own balances:**
     - the unwrap: 1,488,440 + 239,868,095 − 205,427,723 − 51,255 − 1,947,669 − 51,254 = 33,878,634;
     - the signer's −210,442,942 reconciles;
     - the creator fee (1,947,669), the protocol fee (51,255) and the buyback (51,254) are the token-balance changes of accounts 2, 5 and 8.
  4. **Public `getClusterNodes` and `getVoteAccounts`** (one read-only call each, about 19:25 UTC): 3,735 nodes and 671 current validators. Findings 3, 9 and 18 use them.
  5. **A scratch benchmark of the derived-field hook** (finding 14). It ran in a copy outside the lane, and its artifacts were removed from the shared target.

## Verdict

**No blocker.**
- Nothing in the change can send a transaction or move funds:
  - the RTT prober completes a QUIC handshake and opens no stream (`rtt_bookkeeping_with_a_fake_quic_endpoint`: 2 handshakes, 0 streams);
  - it uses a throwaway self-signed client certificate (`send::tpu::quic_client`), never the wallet;
  - `send/tpu.rs` only changes where its leader schedule comes from.
- Nothing silently drops recording:
  - a record that does not decode keeps null derived fields;
  - the hook costs about 44 µs per exec record on the chain writer (finding 14).

**Three majors:**
1. The addendum's tip-account map does not reach rivals.jsonl, the stream it was meant to fix.
2. Addendum I-9 sampling is not done, and MEASUREMENT re-assigns it to WP-05.
3. The RTT is measured to the TPU-QUIC endpoint, but the region is the validator's gossip IP. For 69% of stake these are different machines (BAM and Harmonic ingress nodes), and the region-bucket fallback mixes them.

Fix 1 and 3 before commit. For 2, implement it or record an owner re-assignment in the addendum. The minors can follow, but 4 (credentials in events.jsonl) and 5 (failed transactions) are cheap and should go in with this commit.

## Acceptance checklist (PLAN WP-08 and the addendum)

| Item | Status | Notes |
|---|---|---|
| 1 Leader and validator metadata (getClusterNodes, getVoteAccounts, lists, geo region; QUIC-handshake RTT ≤ 2/s; `be_rtt_ms`; leaders.jsonl, validators.jsonl; snapshot gains region, RTT, client, `be_rtt_ms`; tpu.rs `Book` replaced) | Met, with findings | 3, 6-10. `be_rtt_ms` waits for WP-05's `note_be_rtt` call (13). tpu.rs is switched, but untested (11) |
| 2 PoH (always on; poh.log v2 feed id + entry index; shred feeds write slots-feed v2; `poh_trigger_pct` gauge) | Met, gauge not live | Entries feeds now write `entry_idx`. Shreds write every slots-feed column. The PoH index is filled but read by nothing, and the gauge is neither fed nor reported (13) |
| 3 Transfer classification (full tip map, the 10 kinds, bundle membership) | Met, with findings | Kinds and amounts are right on real transactions (checked above). Failed transactions: finding 5. Bundles come from the Jito tip only; adjacency is the toolkit's (deviation 3). wallet.jsonl waits for WP-03b's one call |
| 4 Program-log decoders | Not in scope | Part 2, after WP-05, as PLAN says |
| Offline: classification on real fixtures (bundle tx, CPI tip, wrap/unwrap, PumpSwap creator fee) | Met | `src/classify/tests.rs` |
| Offline: program-log decoding | Deferred | Part 2 |
| Offline: per-feed PoH from shreds; leader-kind resolution; RTT bookkeeping with a fake QUIC endpoint | Met | `slot_coverage_from_shreds`, `kinds_from_gossip_clients`, `rtt_bookkeeping_with_a_fake_quic_endpoint` |
| Field: 100% identity + kind or unknown with a reason; ≥ 95% RTT ≤ 10 min or region bucket; `poh_trigger_pct` ≥ 90% | Not measurable yet | No reason field (6). RTT pairing (3). The gauge is not wired (13) |
| Config keys `[leaders] rtt_probe, rtt_per_sec, geo_table` | Met | Validated in (0, 20]; in the stage-0 config; printed by `check` |
| Addendum: tip-account map into `OTHER_TIP_ACCOUNTS` (cmp2: 4,197 Glaive rivals unnamed) | **Partly met** | Finding 1 |
| Addendum I-9: sample `why = venues` rows, checked against the §5 budget | **Not met** | Finding 2 |
| WP-03 hand-offs: leaders.jsonl kind updates; `leaders::start` tests; PLAN item 10's text | 2 of 3 | Finding 17 |

## Findings

Severity:
- **Blocker:** fix before commit.
- **Major:** fix before commit, or before the owner's field run, unless the owner accepts it in writing.
- **Minor:** fix soon; the WP still delivers.
- **Nit / Info:** polish or context.

### 1. Major: the addendum's tip-account map does not reach rivals.jsonl

- **Location:**
  - `data/sender-tip-accounts.json`: the 46 added accounts;
  - `src/classify.rs:78-91`: `TipMap::build` reads that file;
  - `src/send/mod.rs:44-60, 62-115`: `tip_owner_names`, `OTHER_TIP_ACCOUNTS`, unchanged;
  - `src/engine.rs:422, 543`: rivals.jsonl's tip names.
- **Problem:**
  - The addendum asks for Glaive, Soyas, SpeedLanding, AllenHark, Solami and the bloXroute and SVS legacy accounts to go into `OTHER_TIP_ACCOUNTS`. Its reason is that cmp2's rivals.jsonl recorded 4,197 Glaive tips as unknown.
  - The patch adds them only to the JSON file, which only the new exec.jsonl classifier reads.
  - rivals.jsonl is written by `record_rival`, and its names come from `send::tip_owner_names()`, which reads the code lists only. A new shadow run therefore still writes those tips with a null name.
  - In Stage 0, exec.jsonl covers PumpSwap transactions only, so the new names appear only there.
  - The new MEASUREMENT note (§4.21, line 719) says this, and leaves the one-line switch to WP-05.
- **Proof:**
  - `grep -c GLaiv src/send/mod.rs` gives 0.
  - `engine.rs:422` has `tip_names: crate::send::tip_owner_names()`, and `:543` has `self.tip_names.get(dest)`.
  - The test `cmp2_rival_tips_the_old_map_left_unnamed_are_named_now` checks `classify::tip_map()`, not the rivals writer.
- **Fix:** either of:
  - make `send::tip_owner_names()` also take the file's accounts (compiled in, the code's names first), and build `TipMap` from it. This is one function in send/mod.rs, off the send path: `OTHER_TIP_ACCOUNTS` only names recordings, and sends use `known_tip_accounts`;
  - or add the 46 entries to `OTHER_TIP_ACCOUNTS`, as the addendum says.

  Add a test that `tip_owner_names()` names `GLaivinAWh21…` as `glaive`.

### 2. Major: addendum I-9 sampling (assigned to WP-08) is not implemented

- **Location:** `docs/PLAN-ADDENDUM.md:183-185`; `src/engine.rs:524-568` (`record_rival`, unchanged); `docs/MEASUREMENT.md:719` (the new note gives the job to WP-05).
- **Problem:**
  - I-9's fix is "WP-02's compression and rotation, plus sampling of `why = venues` rows (WP-08), checked against the disk budget in MEASUREMENT §5".
  - The patch has no sampling, no config key and no budget check.
  - The MEASUREMENT note hands the work to WP-05, but the addendum is unchanged, so the requirement now has no owner.
- **Proof:**
  - cmp2 rivals.jsonl: 849,585 rows in 28 minutes, 744,411 of them `why = venues` (87.6%), 603 MB. That is about 1.3 GB/h raw (about 31 GB/day) for this one stream, against §5's estimate of 75 MB/h compressed for rivals.
  - Every row's JSON is built on the engine thread, about 500 rows/s.
- **Fix:**
  - In `record_rival`, right after `why` is decided and before the line is built, keep 1 in N `venues` rows (`[record]` key, default 10). Choose deterministically, e.g. by a signature hash, so a replay keeps the same rows.
  - Each kept row, or the status line, carries N and the kept and dropped counts.
  - Update §5's rivals estimate.
  - If this lane must not touch engine.rs, have the owner move I-9 to WP-05 in the addendum explicitly.

### 3. Major: the RTT and the region describe different machines for most stake, and the fallback mixes them

- **Location:** `src/leaders.rs`:
  - `:268`: `region_of` uses the gossip IP;
  - `:494-526`: `rtt_target` and `note_rtt` work per identity, measured at `tpu_quic`;
  - `:189, :196-203, :525`: the RTT buckets are keyed by gossip region;
  - `:272-283`: the `rtt_of` fallback.
- **Problem:**
  - The probe measures the announced TPU-QUIC endpoint.
  - The region comes from the gossip IP.
  - The `region_bucket` fallback groups endpoint RTTs by gossip region.
  - For BAM and Harmonic validators the TPU-QUIC endpoint is a shared ingress node, often in another city or country.
- **Proof** (public `getClusterNodes` and `getVoteAccounts`, 2026-10-04):
  - Of 671 current validators, 472 (68.7% of stake) announce `tpuQuic` on a different IP than their gossip address:
    - 382 on port 5010 (BAM), which share just 16 endpoints; one endpoint serves 103 validators;
    - 78 on port 9007 (Harmonic).
  - By the shipped geo table, the two IPs fall in different regions for 210 validators (24.5% of stake) and in different countries for 51 (6.9%). Examples: FR-Strasbourg gossip with a DE-Frankfurt TPU, IE with GB-London, CA-Toronto with US-Newark.
  - The lane's own fixture shows it: `testdata/leaders/cluster-sample.json` `DRpbCBMx` has gossip 67.202.63.79 and tpuQuic 208.91.105.53:5010.
- **Consequences:**
  1. A `region_bucket` RTT is the median of other validators' ingress endpoints, grouped by where those validators are. For example, a Frankfurt BAM node's ~1 ms sample lands in the FR-Strasbourg bucket.
  2. leaders.jsonl, validators.jsonl and the attempt snapshot pair a validator's region with an ingress node's RTT without saying so. The addendum's WP-16 `leader_nearest` would route on these.
  3. The prober measures the same endpoint once per identity. That is about 12 handshakes per 5 minutes to the busiest BAM endpoint (estimated from its 9.2% stake share), where one would do. `rtt_stats.measured_fresh` counts identities, not measurements. 671 validators have only 233 distinct endpoints.
- **Fix:**
  - Key RTT by the TPU-QUIC `SocketAddr`: measure each endpoint once per 5 minutes, and let identities inherit their endpoint's RTT.
  - Record `tpu_quic` and `tpu_region` (and, say, `tpu_shared_by`) in leaders.jsonl, validators.jsonl and `LeaderSnap`.
  - Bucket the fallback by the endpoint's region.
  - Describe `rtt_ms` in §4.27 as host → announced TPU endpoint.
  - PLAN's wording ("region from the gossip IP") predates this data: record the change as a deviation.

### 4. Minor (security): RPC errors that contain provider URLs reach events.jsonl unscrubbed

- **Location:** `src/leaders.rs:723-724, 731` (new), `:741` (from WP-03); `src/rpc.rs:91, 154, 188`.
- **Problem:**
  - `Rpc::call` returns a provider's error unchanged. For a transport error, reqwest appends ` for url (<full url>)` (reqwest-0.12.28 `src/error.rs:268`), and `SHYFT_RPC_URL` carries its key in the query string.
  - The new `leaders_list_stale` events for getClusterNodes and getVoteAccounts write `format!("{e:#}")` into events.jsonl. Recordings are copied off the host.
  - Only the validators-list HTTP path is scrubbed (`leaders.rs:708`).
- **Fix:** use `crate::rpc::scrub(&format!("{e:#}"))` in every refresher event. Better, scrub inside `Rpc::call` before returning: that also covers WP-03's getSlotLeaders event and every other caller.

### 5. Minor: failed transactions count unpaid tips and are marked as bundle candidates

- **Location:** `src/classify.rs:396-401, 430-436, 477-488`.
- **Problem:**
  - `tip_total`, `tip_senders` and `jito_tipped` sum the transfers a failed transaction asked for, but a failed transaction pays only its fee.
  - `bundle_json` marks a failed Jito-tipped transaction `heuristic`. A Jito bundle commits only if all its transactions succeed, so a failed transaction that landed was never in a bundle.
- **Proof:**
  - Fixture `3QWEcb…` has `ok` false and `tip_total` 30,036,343 (test `glaive_tips_in_failed_transactions_v0_and_v1`).
  - 43% of PumpSwap exec records fail (w5h2-p1: 100,541 of 234,119), so a sum of `tip_total` over exec.jsonl overstates tips unless every reader filters on `ok`.
- **Fix:**
  - Set `bundle` to null when `ok` is false.
  - Keep the transfers, since they name the lane, which WP-19 wants.
  - Then either set `tip_total` to 0 for failed transactions and add a `tip_asked` field, or state in §4.14 that `tip_total` is what was asked and readers must filter on `ok`.

### 6. Minor: an unknown leader kind carries no reason (field acceptance)

- **Location:** `src/leaders.rs:294-305, 259-263`.
- **Problem:**
  - The field criterion is that 100% of attempts carry the leader's identity and kind, "or `unknown` with a reason".
  - A slot outside the schedule (a window that failed to load) gives `leader: null, kind: unknown, kind_src: null`.
  - A known leader that no source names gives the same `kind_src: null`.
  - The criterion therefore cannot be evaluated.
- **Fix:** set `kind_src` to `no_schedule` or `no_source` (or add a `reason` field), with a test.

### 7. Minor: validators.jsonl carries no RTT in practice, and prober health is not recorded

- **Location:** `src/leaders.rs:746-750`.
- **Problem:**
  - The first snapshot is written at the first tick, before the prober has measured anything. The next comes `refresh_min` (60 minutes) later.
  - Segments are shorter: MEASUREMENT §5 sizes 20-minute segments. So every segment's only validators.jsonl snapshot has null RTTs.
  - The prober's counts (`probes_ok`, `probes_failed`, `measured_fresh`) appear only in that same boot-time event.
- **Fix:** write a last snapshot, or at least the `leaders_refresh` RTT counts, at stop or every 10 minutes.

### 8. Minor: a failed getClusterNodes or getVoteAccounts is not retried for 10 or 60 minutes

- **Location:** `src/leaders.rs:719-733`.
- **Problem:**
  - `next_nodes` and `next_votes` are moved forward before the call.
  - Boot-time RPC failures are common (I-1, I-6: 429 bursts and provider body errors).
  - A failure at boot leaves the book with no nodes for 10 minutes: no region, client or TPU address, so the prober has no target.
  - It also leaves no vote accounts for an hour, so no validators.jsonl in the whole segment.
- **Fix:** after a failure, retry after 30-60 s with backoff; only a success should set the long period.

### 9. Minor: city-level regions split metros and thin the fallback buckets

- **Location:** `src/leaders.rs:144-147` (`region_name`); `data/ip-geo.csv`.
- **Proof:**
  - The table has 195 regions. The 671 current validators fall in 96 regions, 32 of which hold a single validator.
  - Tokyo splits into JP-Shibuya_City, JP-Shinagawa and JP-Chiyoda_City.
  - The New York metro splits into US-New_York, US-Newark and US-Piscataway.
  - Frankfurt splits into DE-Frankfurt_am_Main, DE-Offenbach, DE-Hattersheim_am_Main and DE-Limburg_an_der_Lahn.
  - Northern Virginia splits into US-Ashburn and US-Sterling.
- **Fix:**
  - Use a metro alias table (or the nearest of a fixed list of hubs) for `region`, and keep the city as its own field.
  - `arbx check` could also load `geo_table` and fail on a missing file. Today a missing table only logs "regions stay null" at run time.

### 10. Minor: the LeaderBook's long read sections can stall hot readers behind a waiting writer

- **Location:** `src/leaders.rs`:
  - `:537-561`: `write_validators` builds about 670 JSON rows, each with a region median, under the read lock;
  - `:421-426`: `write_lines`;
  - `:494-513`: `rtt_target` takes the write lock every 0.5 s, even when nothing is due;
  - the comment at `:416`.
- **Problem:**
  - std's `RwLock` on Linux blocks new readers while a writer waits: `is_read_lockable` requires that no writer is waiting.
  - The readers on hot paths are:
    - `feeds/mod.rs:482`: the state stream's task looks up the leader for every block meta;
    - `send/tpu.rs` `targets()`, on every TPU send;
    - WP-05's `snapshot()`.
  - With the prober writing twice a second, such a reader can wait out a whole validators.jsonl build.
  - This is rare today (hourly, and milliseconds long), but the comment "snapshots ... are never kept waiting" is not true.
- **Fix:**
  - Copy what the rows need under the lock and build them after releasing it.
  - In `rtt_target`, find the candidate under the read lock and take the write lock only when one is picked.
  - Or publish snapshots through an `ArcSwap`.

### 11. Minor: the TPU path's new target selection has no test

- **Location:** `src/send/tpu.rs:135-137`; `src/leaders.rs:397, 478-489`.
- **Problem:**
  - tpu.rs's own `Book` was replaced: targets, schedule fills and node refreshes now go through the LeaderBook.
  - No test covers `next_leaders`:
    - distinct leaders from the current slot on;
    - leaders without an address skipped;
    - the `n` cap.
  - No test covers `fill_window` either: it must not move the refresher's window or send an engine input.
  - The path is off in Stage 0, but it is the only direct-to-leader send path.
- **Fix:** unit tests on a LeaderBook with a schedule and nodes.

### 12. Minor (merge hazard): stream id S(28) is also lane WP-03b's `WALLET`

- **Location:** `src/rec/mod.rs:129` (`VALIDATORS = S(28)`); lane-wp-03b `src/rec/mod.rs:129-131` (`WALLET = S(28)`, `SLOTIDX = S(29)`, `TXFETCH = S(30)`).
- **Problem:** a merge that keeps both constants compiles, and then writes one stream's records under the other's name. No test ties each constant to its row in the table.
- **Fix:** renumber at the merge, and add a test that `STATIC[c.0 as usize].0` is the expected name for every constant.

### 13. Minor: the PoH index and gauge, `note_be_rtt`, `note_bundle_processed` and the wallet hook have no caller yet

- **Location:** `src/feeds/mod.rs:200-266`; `src/leaders.rs:585`; `src/classify.rs:422`; `src/rec/exec.rs:61`.
- **Problem:**
  - The PoH index is filled by every entries and shred feed: a global mutex on the feed paths, up to 1,000,000 entries. Nothing reads it.
  - `poh_trigger_pct`, `be_rtt_ms`, bundle `jito-result` and wallet.jsonl classification do not exist in a run until WP-05 and WP-03b make the calls.
  - PLAN's file boundaries justify the split, but only the implementer's report tracks it.
- **Fix:** list each call and the WP that owns it in the commit body, and in those WPs' acceptance. For example, a WP-05 test that an attempt carries `be_rtt_ms` and moves the gauge.

### 14. Info: measured cost of the derived-field hook

- **Method:** a scratch copy of this lane's crate with one extra integration test, outside the lane, as a release build in the shared target; its artifacts were removed. It ran the 152 real transactions of `testdata/classify` and `testdata/wallet` through 4,000 passes.
- **Result, per record:**

  | Work | µs |
  |---|---|
  | `exec_json` + serialize | 68.0 |
  | with `derive` | 115.2 (+69%) |
  | the hook alone | 43.8 |

  Record size grows 13.1%.
- **At the old bot's PumpSwap rate:** w5h2-p1 exec.jsonl has 234,119 records over 742 slots, about 790/s (about 1,180/s by arrival time); 43% failed. That is 35-52 ms of chain-writer CPU per second (3.5-5% of a core) and 13% more exec.jsonl.
- **No drop risk at that rate:** the chain queue holds 262,144 records.
- **Option:** most of the cost is decoding the base58 keys and base64 data that `exec_json` has just encoded. Classifying from the binary keys and the protobuf, before encoding, would remove it; wallet.jsonl could pass the same.

### 15. Nit: a slot can get two slots-feed lines

- **Location:** `src/feeds/shred.rs:182-190, 353-360`.
- **Problem:** a data shred that arrives after its slot was dropped (20 s) creates a new `SlotState`. When that state is dropped in turn it is reported again (`data_n > 0`), with `valid` 0.
- **Fix:** this is rare. Either readers keep the first line per (feed, slot), or the assembler remembers which slots it reported.

### 16. Nit: the report's claim about cmp2's remaining unknown tips

- The report says they are "mainly the eight FAST… accounts, about 4,000 rows". The FAST accounts have 4,158 rows, but the largest unnamed account is AgmLJBMD…: 4,671 rows, 585M lamports.
- About 33,800 unnamed rows remain, spread over about 190 accounts (`testdata/classify/cmp2-rival-tips.json`).

### 17. Nit: the WP-03 hand-off "PLAN item 10's text" was not done

- `docs/PLAN.md:522` still says BAM comes from our bundle results.
- WP-03's commit body lists this edit for WP-08; the report does not mention it.

### 18. Info: the gossip-client kind source changes almost nothing while a list is loaded

- 26 of the 671 current validators (1.2% of stake) are absent from the Kobe static list: 20 run Agave, 3 Firedancer and 1 JitoLabs (0.00% of stake). Only that one validator changes kind.
- The source matters only when no list loads at all.
- Acceptable as documented (deviation 4). Kind changes are not journaled (deviation 8), so WP-05 must journal the kind at each decision.

### 19. Nit: small edges

- `src/classify.rs:341-344`: a System transfer into the signer's WSOL account is `wrap` or `self` whoever sent it. A third party paying into it is not `self`.
- `TipMap::build` names a service by its JSON key when it has no `sender` field (for example `temporal_nozomi` where the code says `nozomi`). Today no account depends on this: the file adds only the 46 accounts of services that carry `sender`. It would bite the next file-only entry.

## Dispositions needed before commit

| # | Severity | Owner of the fix |
|---|---|---|
| 1 | Major | WP-08 (send/mod.rs `tip_owner_names`, or `OTHER_TIP_ACCOUNTS`) |
| 2 | Major | WP-08 (engine.rs `record_rival` + `[record]` key), or the owner re-assigns I-9 in the addendum |
| 3 | Major | WP-08 (leaders.rs: per-endpoint RTT, `tpu_region`; §4.27/§4.28) |
| 4, 5 | Minor | WP-08 (cheap, in this commit) |
| 6-12 | Minor | WP-08, or listed as open items in the commit body |
| 13 | Minor | WP-05 / WP-03b, listed in the commit body |

## Disposition (2026-10-04, WP-08 fix pass)

Every major and every minor was fixed in the lane, with tests; the nits too. Build and tests on the result (lane `lane/wp-08`, shared lanes target, 5 jobs): `cargo build --release` passes with the 3 warnings already at HEAD; `cargo test --release`: **223 passed, 0 failed, 2 ignored** (lib 200 + 1 ignored, bin 9, legacy_fixtures 4, meta_config_hash 1, runtime_isolation 2 + 1 ignored, stop_path 6, supervisor 1; 7 more lib tests than at review; the lib suite run 3 more times, stable); the toolkit's `python3 -m unittest` 78 OK (4 skipped); `testdata/legacy` 16 OK; `capture-fixtures.py --verify` 232 files, 0 problems; `arbx check` exits 0 on `deploy/arbx-stage0.toml` and `deploy/arb.toml` (a copy of this lane's binary, sha256 9d85bb16...).

| # | Disposition | What was done | Tests |
|---|---|---|---|
| 1 | Fixed | `send::tip_owner_names()` (the engine's `tip_names`, rivals.jsonl's `tips`) is now the code's lists (`code_tip_names`: `known_tip_accounts`, `OTHER_TIP_ACCOUNTS`) followed by the compiled-in catalogue `data/sender-tip-accounts.json` (`send::TIP_CATALOGUE`, `add_tip_catalogue`) for every account they do not name. `classify::tip_map()` is built from the same function, so exec.jsonl and rivals.jsonl name tips alike. The 46 added accounts stay in the catalogue with their per-address sources instead of being copied into `OTHER_TIP_ACCOUNTS` (one list to keep; **deviation** from the addendum's wording, same effect). engine.rs is unchanged for this | `send::tests::rival_tip_names_take_the_catalogue` (`GLaivinAWh21…` is `glaive` in `tip_owner_names` and not in the code lists; Soyas, both bloXroute legacy accounts; a code name wins; every catalogue account named; 46 added), `rec::sample::tests::rivals_jsonl_samples_venues_rows_by_signature` (rivals.jsonl rows written by `record_rival` carry `"glaive"`), `classify::tests::cmp2_rival_tips_…` (`tip_map().names() == tip_owner_names()`) |
| 2 | Fixed | Plan addendum I-9 in WP-08, as assigned: `[record] rivals_venues_sample` (default 10, ≥ 1; both maintained configs say 10). `record_rival` decides right after `why` (and after learning the signer): a `venues` row is written only when `rec::sample::keep_1_in(sig, N)` (splitmix64 of the signature's first 8 bytes, little-endian, mod N), so a replay or another bot keeps the same rows; a kept row carries `sample {one_in, kept, seen}`; manifest.json gains `sampling.rivals_venues` with the totals. The counters live in the recorder (`Rec::sample_rival_venues`), so engine.rs changes by three lines inside `record_rival` only (they merge with master's WP-04 engine.rs, where that function is unchanged). rivals schema 1.2. MEASUREMENT §4.21's hand-off to WP-05 is replaced by the "As WP-08 writes it" text; §4.4 and §5 updated. **Measured** on cmp2's real 603 MB rivals.jsonl with the same rule (`scratchpad/e2/wp08/rivals-sample.mjs`): 849,585 rows, 1.29 GB/h raw, 238 MB/h at zstd-3; at 1 in 10, 179,899 rows (74,725 `venues`, 10.04% of 744,411): 266 MB/h raw, **54 MB/h** at zstd-3 | `rec::sample::tests::one_in_n_by_the_signature` (rate within ±5% on 100,000 signatures, determinism, a splitmix64 known answer, 1 and 0 keep all), `rivals_jsonl_samples_venues_rows_by_signature` (through `Engine::step`: the written `venues` rows are exactly the rule's, each with its counts; manifest totals; `pools` rows never sampled; a left-out row's signer becomes a `known` row; 1 keeps 200 of 200 unmarked), `config::tests::wp08_leaders_keys` |
| 3 | Fixed | RTT is kept **per TPU-QUIC endpoint** (`Inner.rtt: SocketAddr -> Rtt`): `rtt_target` returns the next due endpoint among the next 64 slots' leaders, each endpoint measured once per 5 minutes however many validators announce it, and every validator behind it inherits the RTT. The fallback buckets are keyed by the **endpoint's** region (a validator without an endpoint uses its gossip region). leaders.jsonl, validators.jsonl and `LeaderSnap` gain `tpu_quic` (snapshot and leaders.jsonl; validators.jsonl had it), `tpu_region`, `tpu_shared_by` (nodes announcing the endpoint) and `city`; `rtt_stats` counts endpoints (`endpoints_fresh`) and the validators whose RTT is their endpoint's own or a bucket's. §4.27, §4.28, §4.37 describe `rtt_ms` as host → announced TPU endpoint. **Deviation** from PLAN's "region from the gossip IP": `region` still is the gossip IP's, but the RTT fallback and `tpu_region` use the endpoint's. **Re-measured** on public getClusterNodes / getVoteAccounts (2026-10-04 20:10 UTC): the reviewer's figures hold exactly (472 of 671, 68.7% of stake, on another IP; 382 BAM on 16 endpoints, one serving 103; 210 / 24.5% in another city, 51 / 6.9% another country); the 671 announce 233 endpoints, so the prober needs at most 233 handshakes per 5 minutes (0.8/s) where it made up to 671 | `rtt_bookkeeping_with_a_fake_quic_endpoint` (rewritten: two validators behind one endpoint measured once and both `quic_handshake`; a failed endpoint's validators take the endpoint region's median; a validator placed in region X with an endpoint in Y takes Y's; one whose endpoint region has no sample gets none although its gossip region has one; no endpoint → gossip region; the prober loop makes one handshake for two validators; 2 handshakes, 0 streams in all), `real_cluster_answers` (CAo1dCGY: gossip `US-Delta_Mills`, endpoint `GB-London`), `the_refresher_loop` |
| 4 | Fixed | Every refresher event's error goes through `rpc::scrub` (`scrubbed()`): getClusterNodes, getVoteAccounts, getSlotLeaders and the list fetch (whose reqwest error also drops its URL, `without_url`). `Rpc::call` itself is left to lane WP-03b, whose `RpcFailure` scrubs every message at the source (rpc.rs is that lane's file) | `failed_refreshes_are_tried_again_soon_and_errors_are_scrubbed` (an RPC on a closed port with `?api-key=SECRET123`: three events name `127.0.0.1:<port>`, none holds the key) |
| 5 | Fixed | A failed transaction keeps its transfers (the lane, for WP-19) and `tip_senders` / `jito_tipped`, but `tip_total` is 0 (paid) and the new `tip_asked` holds the asked lamports; `bundle` is null when `ok` is false. §4.14 table and text | `glaive_tips_in_failed_transactions_v0_and_v1` (`tip_total` 0, `tip_asked` 30,036,343), `a_failed_jito_tipped_transaction_is_no_bundle_and_paid_no_tip` (the CPI-tip fixture with `ok` false: bundle null, transfers kept), `a_cpi_tip` (the successful one stays heuristic) |
| 6 | Fixed | An `unknown` kind carries its reason in `kind_src`: `no_schedule` (snapshot of a slot outside the schedule, `leader` null) or `no_source` (a known leader no source names); leaders.jsonl lines carry `no_source` too | `window_refresh_and_kind_lookup_with_a_fake_rpc`, `kinds_from_gossip_clients`, `real_cluster_answers` (Rakurai: `unknown`, `no_source`) |
| 7 | Fixed | validators.jsonl every 10 minutes (`VALIDATORS_EVERY_NS`), the first as soon as the vote accounts are known, each with a `leaders_refresh` event holding the RTT counts. About 1,000 lines × 650 bytes per snapshot (4 MB/h raw; §5) | `the_refresher_loop` (snapshots at the first tick, +61 and +122 minutes), `failed_refreshes_…` (the first snapshot when the votes arrive, the next 10 minutes later) |
| 8 | Fixed | A failed getClusterNodes, getVoteAccounts or validator-list fetch is tried again after 30 s, then 60 s, 120 s, ... up to its period (`Due`); only a success sets the long period. The stale events carry `fails` and `retry_s` | `failed_refreshes_are_tried_again_soon_and_errors_are_scrubbed` (nodes fail twice, votes once: retried at +30 s, +90 s; then 10 minutes after the success), `the_refresher_loop` (a failed list: `retry_s` 30) |
| 9 | Fixed | `leaders::METROS` (27 metros) gathers the table's cities: `region` is the metro, else the city; `city` is its own field. The shipped table's 195 cities are 132 regions; the 671 current validators fall in 69 regions (96 cities), 24 single-validator ones (32). `arbx check` loads the geo table where this machine has it (a table that does not parse fails the check; a missing one is noted) and prints cities and regions | `the_geo_table` (every metro city exists in the shipped table, in one metro only; Frankfurt and Offenbach are one region; counts 132 / 195) |
| 10 | Fixed | leaders.jsonl lines and validators.jsonl copy what they need under the read lock (`Facts`, plain values; region medians computed once per job, `Medians`) and build JSON after releasing it; `rtt_target` searches under the read lock and takes the write lock only to mark the endpoint it picked (re-checked). The misleading comment is gone; the module docs state the lock rules | (behaviour unchanged; covered by the leaders tests) |
| 11 | Fixed | `next_leaders` also no longer returns one leader for `n` = 0 | `next_leaders_and_fill_window` (distinct leaders from the slot on, a leader without an address skipped, the `n` cap; `fill_window` adds slots and leaders.jsonl lines without moving the refresher's window) |
| 12 | Fixed | `VALIDATORS` is `S(id_of("validators"))`: its id is looked up by name in the stream table at compile time, so it follows its row whatever the merge does. Master (WP-04: commits 28, decisions 29, alts 30) and lane WP-03b (wallet 28, slotidx 29, txfetch 30) number theirs by hand and collide with each other: the merge must renumber them | `rec::stream_ids::stream_ids_name_their_rows` (every constant names its row, one constant per row, ids distinct: it fails until the merge adds the merged lanes' constants to its list) |
| 13 | Open, listed | No caller yet: the PoH index and `POH_GAUGE.note_attempt` / `status` (WP-05's attempt writer and the status `coverage` section), `leaders::note_be_rtt` (WP-05's keep-alive loop), `classify::note_bundle_processed` (WP-05, send/jito.rs `on_result`), `rec::exec::derive` in the wallet.jsonl writer (WP-03b). Listed in the commit body for those WPs' acceptance | |
| 14 | Noted | Not changed: classifying from the binary keys and protobuf before encoding is a later optimisation (the hook costs about 44 µs per record, no drop risk) | |
| 15 | Fixed | The assembler remembers the last 1,024 dropped slots; a late shred of one starts a state already marked reported, so a slot has at most one slots-feed line | `slot_coverage_from_shreds` (late data and code shreds of two dropped slots write no second line) |
| 16 | Fixed | The remaining unnamed tips are stated in `testdata/classify/README.md` and MEASUREMENT §4.14: about 33,800 rows over about 190 accounts, the largest AgmLJBMD... (4,671 rows), then the eight FAST... accounts (4,158) | |
| 17 | Fixed | `docs/PLAN.md` item 10 lists the kind sources as implemented (BAM from the API's `running_bam`, bundle results as Jito, the static fallback, WP-08's gossip client) | |
| 18 | Noted | Kind changes are not journaled: WP-05 journals the kind (the snapshot) at each decision. In the commit body | |
| 19 | Fixed | A System transfer into the signer's WSOL account counts as `wrap` / `self` only when it comes from the signer or an account it owns (a stranger's is `other`). A catalogue service that adds an account of its own must name its `sender` (tested), so a key such as `temporal_nozomi` cannot become a sender name by accident | `rules_on_synthetic_records` (a stranger's transfer then SyncNative: `other`; the signer's: `wrap`), `rival_tip_names_take_the_catalogue` |

**Not done.** The classify and leaders fixtures stay outside `testdata/legacy/fixtures.sha256`, whose scope (legacy and wallet) is WP-00b's tests' (`tests/legacy_fixtures.rs`, `testdata/legacy/test_legacy_fixtures.py`); each classify test checks its fixture's own signature. rivals.jsonl's planned `loaded_data_limit` and `jito_tipped` (§4.21 "New") are still not written: no WP owns them.

**Files outside PLAN's WP-08 list** (they matter for the merge): `src/engine.rs` (3 lines in `record_rival`), `src/send/mod.rs` (`tip_owner_names`, `code_tip_names`, `add_tip_catalogue`, `TIP_CATALOGUE`, a test), `src/rec/mod.rs` (the `validators` stream, `id_of`, the sampler, rivals 1.2, a test), `src/rec/manifest.rs`, `src/rec/sample.rs` (new), `src/lib.rs`, `data/sender-tip-accounts.json`, `deploy/arbx-stage0.toml`, `deploy/arb.toml`, `docs/MEASUREMENT.md`, `docs/PLAN.md` (item 10), `tools/capture-fixtures.py`, `testdata/classify/`, `testdata/leaders/`. `src/main.rs`'s check output moved below the recorder line, so the lane no longer edits the leaders line master's WP-04 hunk sits on; the rtt_per_sec check moved below the `[record]` checks for the same reason.

**Assumptions.** Owner decisions keep PLAN §9's defaults. The default 1 in 10 suits Stage 0's budget (54 MB/h for rivals at cmp2's rate); the owner can set 1 for a study. Metro membership is ours (27 metros of nearby data-centre towns); the city stays in every line for readers who disagree. The stage-0 host needs `/root/arbx/data/ip-geo.csv` deployed with the binary (without it regions stay null; `arbx check` says so).

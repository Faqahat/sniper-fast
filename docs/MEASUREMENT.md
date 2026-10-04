# arbx measurement specification

**Date:** 2026-10-04. **Status:** specification, revision 2. It describes what WP-00 to WP-08 and WP-11 to WP-15 of `docs/PLAN.md` must produce, and how the toolkit (WP-10) must read it. Revision 2 applies `docs/reviews/plan-review.md`; the dispositions are in `docs/reviews/plan-changes.md`.
**Owner's requirement:** measure everything, on chain and off chain, at least as completely as arb-lab, and fix every gap found in the research. Recording is always on, never slows the hot path, and comes with a toolkit that regenerates per-segment reports correctly.

This document gives, for every recorded stream and file (existing and new): its name, producer (file and function), when it is written, every field with type, unit and semantics (monotonic or delta), rotation and compression, its share of the disk budget, and which reports use it. Section 6 designs the analysis toolkit.

---

## 0. Principles

1. **Always on.** There is no switch to turn recording off (`[record] enabled` is removed). Configuration only sets budgets.
2. **Never on the hot path.** Producers hand typed records to bounded queues (`try_send`). Formatting, compression and disk I/O happen on writer threads. A full queue drops the record and counts it; it never blocks.
3. **Core streams are never silently lost.** If a core stream drops a record, the segment can no longer be reconciled, so sending stops (shadow for the rest of the segment) and the drop is recorded (§1.5). **Replay streams are never lost either.** `accounts` and `journal` are in their own class (§1.2). A drop does not stop trading, but it writes a gap mark, replay refuses the gap interval, and the Stage-0 exit requires zero drops.
4. **Stable identifiers everywhere.** Signatures in full, plus decision, attempt, bundle and state-version ids, so every stream joins without guessing.
5. **Missing is explicit.** A value we did not observe is `null` with a reason where useful, never `0`. Coverage is itself measured.
6. **Chain truth.** Money and outcomes come from chain data (our wallet's transactions, balance snapshots, block data). Bot counters are diagnostics only.
7. **Versioned schemas.** Every file starts with a header naming its schema and version. Readers refuse unknown major versions.

---

## 1. Layout, files, rotation, compression, budget

### 1.1 Directory layout

```
runs/<campaign>/                      one supervisor campaign (deploy/run-w.sh)
  campaign.json                       §4.1
  config.frozen.toml                  the only config this campaign runs
  arbx-<sha8>                         the only binary this campaign runs
  supervisor.log, supervisor.jsonl    §4.7
  control.jsonl                       §4.7 (supervisor-level commands)
  <campaign>-p<i>.out                 the segment's stdout and stderr, captured by run-w.sh (§4.5)
  <campaign>-p<i>/                    one segment = one arbx process
    meta.json  stop.json  manifest.json  config.toml  pools.json  probe.json
    run.log  events.jsonl  control.jsonl  status.jsonl  feedhealth.jsonl  resources.jsonl  keepalive.jsonl
    accounts.NNN.bin.zst  journal.NNN.bin.zst
    exec.NNN.jsonl.zst  wallet.NNN.jsonl.zst  blocks.NNN.jsonl.zst  slots.NNN.jsonl.zst  slotidx.NNN.jsonl.zst  txfetch.NNN.jsonl.zst
    txarr.NNN.log.zst  arrivals.NNN.jsonl.zst  rivals.NNN.jsonl.zst  moves.NNN.log.zst  poh.NNN.log.zst
    slots-feed.NNN.log.zst  entries-<feed>.NNN.bin.zst  alts.NNN.jsonl.zst  alts-final.jsonl.zst
    leaders.NNN.jsonl.zst  validators.jsonl.zst
    triggers.NNN.jsonl.zst  commits.NNN.jsonl.zst  decisions.NNN.jsonl.zst  opportunities.NNN.jsonl.zst
    predictions.NNN.jsonl.zst  caps.NNN.jsonl.zst  sims.NNN.jsonl.zst
    attempts.NNN.jsonl.zst  copies.NNN.jsonl.zst  bundles.NNN.jsonl.zst  outcomes.NNN.jsonl.zst
    ledger.NNN.jsonl.zst  snapshots.jsonl  recon.jsonl
    experiments.jsonl  verify.NNN.jsonl.zst  discovery.NNN.jsonl.zst
    report/                           written by the toolkit (§6), never by the bot (includes blockctx.jsonl, §4.41)
    chain-cache/                      toolkit's cache of chain fetches
runs/signer-stats.json, data/cu-table.json   cross-run files (§4.48)
```

The per-feed slot log of arb-lab, `slots.log`, is renamed `slots-feed` so that it is not confused with the new slot-status stream `slots` (§4.17). Legacy readers accept both names.

### 1.2 Stream classes

| Class | Streams | Queue (records) | On overflow |
|---|---|---|---|
| core | ledger, wallet, attempts, copies, bundles, outcomes, decisions, commits, control, stop | 262,144 | drop counted; `events` `recorder_drop`; SendGate → shadow (`core_record_loss`) for the rest of the segment |
| replay | accounts, journal | 1,048,576 (accounts), 524,288 (journal) | drop counted; `events` `recorder_drop`; a gap record (accounts kind 6 GAP, journal kind 12 GAP) is written with the next record; replay refuses the interval; trading continues; Stage-0 exit requires 0 |
| chain | exec, blocks, slots, slotidx, txfetch, txarr, arrivals, moves, poh, slots-feed, alts, leaders, triggers, predictions, caps, sims, verify | 262,144 | drop counted; reported in status, manifest and report R0; Stage-0 exit requires < 0.01% |
| bulk | entries-<feed>, rivals, validators, discovery | 131,072 | drop counted; first to be switched off by the disk budget; Stage-0 exit requires < 0.1% |
| slow | meta, manifest, probe, run.log, events, status, feedhealth, resources, keepalive, snapshots, recon, experiments | unbounded (low rate) | n/a |

PLAN.md WP-02 uses the same class lists. In revision 1 the plan called "accounts keyframes" droppable bulk; that was wrong (F26). The keyframe interval is a format choice that the disk ladder may lengthen (§1.4). It never drops a record.

### 1.3 File format

- **JSON-lines streams:** UTF-8, one JSON object per line. The first line of every file is a header: `{"schema":"arbx.<stream>/<major>.<minor>","run":"<segment name>","file_seq":<n>,"started_ns":<t_ns>,"producer":"<binary sha8>"}`. A reader must skip it.
- **Binary streams** (`accounts`, `journal`, `entries-<feed>`): byte formats in §4.12, §4.13, §4.25.
- **Compression:** in-process zstd, level `zstd_level` (3). The writer ends a zstd frame at every flush (`flush_ms`, 1,000 ms) and every 4 MiB, so all completed frames decode while the run continues; a trailing incomplete frame is ignored by readers.
- **Rotation:** each stream rotates on its own at `rotate_mb` (256 MiB uncompressed) or `rotate_min` (60 minutes), whichever comes first. `NNN` counts from `000`. Each file decodes on its own: binary streams restart their dictionaries and keyframes per file. The journal does not need to rotate together with `accounts`, because it references account records by their segment-wide sequence number `aseq`, not by a per-file `acct_id` (F25).
- **Plain streams** (meta, stop, manifest, probe, config, pools, run.log, events, control, status, feedhealth, resources, keepalive, snapshots, recon, experiments): uncompressed and line-buffered, so an operator can `tail` them. At segment end they stay plain (they are small).

### 1.4 Disk budget

Checked every 10 s by `src/rec/disk.rs`. Inputs: the segment directory's size, the filesystem's free space. Config: `disk_budget_gb` (per segment, 40), `min_free_gb` (25). When either limit is crossed, actions run in order, each written to `events.jsonl` (`disk_action`) and the manifest:
1. stop the `entries-<feed>` archives;
2. stop `rivals` and `validators` detail;
3. lengthen the `accounts` keyframe interval 4× (a format change: no record is dropped);
4. SendGate → shadow and stop the segment (`stop.json` reason `disk_budget`).
Core, replay and chain streams are never dropped by the budget. The supervisor refuses to start a segment below `min_free_gb`. Volume estimates are in §5.

### 1.5 Drop accounting

Every stream has `records_total`, `dropped_total` and a queue high-water mark, in `manifest.json` and in `status.jsonl` (`recorder`).
- A core drop is a segment-level fault (principle 3).
- A replay drop is a replay fault (principle 3).
- Reports print coverage for every stream they use (R0, §6.3).

---

## 2. Conventions

### 2.1 Types

| Type | JSON form | Meaning |
|---|---|---|
| `t_ns` | integer | CLOCK_REALTIME nanoseconds on the bot's host (`feeds/clock.rs::now_ns`). Kernel UDP timestamps use the same clock. Values exceed 2^53: readers must parse integers exactly (Python does; JavaScript needs BigInt) |
| `slot` | integer | Solana slot |
| `idx` | integer or null | position of a transaction in its block (Yellowstone `TransactionInfo.index`, or position in `getBlock`) |
| `lam` | integer | lamports; signed when it is a delta. Always < 2^53 |
| `amt` | string | raw token amount (u64) as a decimal string; signed deltas carry a leading `-` |
| `u128s` | string | u128 as a decimal string (sqrt prices, reserves) |
| `pk` | string | base58 public key |
| `sig` | string | base58 transaction signature (64 bytes) |
| `sig8` | string | 16 lowercase hex characters: the first 8 bytes of the signature in order (arb-lab's `txarr.log`/`poh.log` key) |
| `ms` | number | milliseconds (float) |
| `us` | integer | microseconds |
| `sv` | object | state version `{"h":"<16 hex>","slot_max":slot,"wv_max":u64}`: `h` = xxh3-64 over the route accounts' `(pubkey, slot, write_version)` in route order |
| `enum` | string | values listed in Appendix A |

### 2.2 Counter semantics (status and every periodic stream)

- `<name>_total`: monotonic since process start (reset only by a restart). To aggregate over a segment, take the **last** value. Never sum `_total` across lines.
- `<name>_delta`: the change since the previous line of the same stream. Summing over lines gives the segment total.
- `<name>_now`: a gauge (instantaneous value).
- Percentiles carry their window: `{"window":"interval","n":..,"p50":..,"p90":..,"p99":..}`. `interval` means since the previous line; `minute`, `hour` as named.
- Every periodic line has `seq` (starting at 0) and `interval_ns`; a gap in `seq` means lost lines.

arb-lab's `failed_fees_lamports` was a running total that was later summed across lines (R §3.7); under these rules it is `failed_fees_total_lamports` and `failed_fees_delta_lamports`.

### 2.3 Identifiers and joins

| Id | Scope | Joins |
|---|---|---|
| `sig` | global | exec, wallet, moves, commits, blockctx, ledger, outcomes, copies, bundles (`sig` of our transaction), rivals |
| `sig8` | global (collision-checked) | txarr, poh |
| `decision` | segment (u64, increasing) | decisions → attempts → experiments |
| `attempt` | segment (u64, increasing) | attempts, copies, bundles, outcomes, blockctx, ledger |
| `bundle` | global (Jito uuid) | bundles, copies, outcomes |
| `opp` | segment | opportunities, caps (legacy-compatible) |
| `txn` of an account update | global (signature) | accounts, commits, moves |
| `acct_id` | file (binary dictionary) | accounts only |
| `aseq` | segment (u64, increasing; assigned when an account record is emitted) | accounts, journal, store versions, `arbx quote --version` |
| global attempt key | `<segment>:<attempt>` | campaign-level joins |

---

## 3. Stream catalogue

| § | Stream | Producer (file :: function) | When written | Class | Status | Reports |
|---|---|---|---|---|---|---|
| 4.1 | campaign.json | deploy/run-w.sh | campaign start, updated per segment | slow | new | R0, R1, R13 |
| 4.2 | meta.json | src/provenance.rs (main.rs::run) | segment start | slow | v2 (arb-lab v1) | all |
| 4.3 | stop.json | main.rs::run, src/control.rs | segment end | core | new | R0, R1 |
| 4.4 | manifest.json | src/rec/manifest.rs | every 60 s, at close | slow | new | R0 |
| 4.5 | run.log, `<segment>.out` | src/rec (slow writer), main.rs `say`; run-w.sh captures stdout/stderr | as events happen | slow | kept | none (human only) |
| 4.6 | events.jsonl | every subsystem via rec::event | as events happen | slow | new | R0, R5, R7 |
| 4.7 | control.jsonl, supervisor.jsonl | src/control.rs; run-w.sh | per command / segment | core/slow | new | R0 |
| 4.8 | status.jsonl | engine.rs::write_status, exec.rs::status, ledger.rs | every 10 s, final | slow | v2 | R0, R2 cross-check |
| 4.9 | feedhealth.jsonl | src/rec/health.rs (FeedCounters) | every 10 s per feed | slow | new | R7 |
| 4.10 | resources.jsonl | src/rec/health.rs | every 10 s | slow | new | R0 |
| 4.11 | keepalive.jsonl | send/mod.rs::Paths::start | each keep-alive | slow | kept | R6 |
| 4.12 | accounts.bin | feeds/mod.rs::forward → src/rec/accounts.rs | every watched-account update | replay | new | R4, R8, replay, X1, X3 |
| 4.13 | journal.bin | engine.rs `Engine::step` / `Engine::timers` (dequeue point) | every engine input event and timer evaluation | replay | new (WP-03) | replay |
| 4.14 | exec.jsonl | feeds/grpc.rs (PumpSwap tx stream), src/chainfetch/backfill.rs → src/rec/exec.rs | every executed tx touching a watched account | chain | v2 (arb-lab: PumpSwap-only) | R0, R4, R8, R9, X1, cu-table |
| 4.15 | wallet.jsonl | src/chainfetch/wallet.rs → src/rec/exec.rs | every landed tx paid by or naming our wallet | core | new | R1, R3 |
| 4.16 | blocks.jsonl | feeds/grpc.rs (blocks_meta, only if the probe accepted it) | every block | chain | new | R0, R6 |
| 4.16b | slotidx.jsonl | src/chainfetch/slotidx.rs (getBlock, signatures only) | every confirmed slot | chain | new | R0, R4, R5, blockctx, X1 |
| 4.17 | slots.jsonl | feeds/grpc.rs (slots, all statuses) | every slot status change | chain | new | R0, R5 |
| 4.18 | txfetch.jsonl | src/chainfetch/* | every RPC fetch except the blockhash poll | chain | new | R0 |
| 4.19 | txarr.log | engine.rs::write_txarr | when a signature expires (10 s) | chain | kept (+header) | R5, R7 |
| 4.20 | arrivals.jsonl | engine.rs::write_arrivals | per decoded trigger, after 10 s | chain | kept (+fields) | R7 |
| 4.21 | rivals.jsonl | engine.rs::record_rival | arbitrage-like tx at shred time | bulk | kept (+fields) | R9 |
| 4.22 | moves.log | engine.rs::on_account | first update of (tx, pool) | chain | v2 (+columns) | R4, legacy |
| 4.23 | poh.log | feeds/mod.rs::forward, feeds/shred.rs::poh_advance | per tx with a PoH position | chain | v2 (+columns) | R4, R5 |
| 4.24 | slots-feed.log | feeds/mod.rs::forward, feeds/shred.rs | per feed per finished slot | chain | v2 (renamed, +columns) | R7, R0 |
| 4.25 | entries-<feed>.bin | rec::archive | every entries message of an archived feed | bulk | kept (per feed) | replay of feeds |
| 4.26 | alts.jsonl, alts-final | engine.rs::on_alt, learn_alts, process | every lookup-table event; dump at stop | chain | v2 (events) | R0, replay |
| 4.27 | leaders.jsonl | src/leaders.rs | per slot as the schedule is learned | chain | new | R3, R6 |
| 4.28 | validators.jsonl | src/leaders.rs | hourly snapshot | bulk | new | R6 |
| 4.29 | pools.json | main.rs (after pools::boot) | segment start | slow | new | all |
| 4.30 | triggers.jsonl | engine.rs::on_trigger | every decoded swap on a watched pool | chain | v2 (hints) | R2, R8 |
| 4.31 | commits.jsonl | src/commit.rs | every commit group at resolution | core | new | R2, R5 |
| 4.32 | decisions.jsonl | engine.rs (evaluation), exec.rs (send checks) | every route evaluation | core | new | R2, R3, R10, X1 |
| 4.33 | opportunities.jsonl | engine.rs::finish_opp | per opportunity ≥ min_profit after its watch window | chain | kept | R12, legacy |
| 4.34 | predictions.jsonl | engine.rs::check_prediction | per decoded trigger whose effect is committed | chain | v2 (all venues) | R8 |
| 4.35 | caps.jsonl | engine.rs::record_caps | per opportunity | chain | kept | R12 |
| 4.36 | sims.jsonl | exec.rs::simulate | per shadow simulation | chain | kept (diagnostic) | none by default |
| 4.37 | attempts.jsonl | exec.rs::send | per attempt, at signing | core | v2 | R1-R6, R10 |
| 4.38 | copies.jsonl | send/mod.rs::Paths::fire | per copy | core | kept (+fields) | R3 |
| 4.39 | bundles.jsonl | send/jito.rs::on_result | every block-engine result | core | v2 (+fields) | R3, R6 |
| 4.40 | outcomes.jsonl | exec.rs::on_settled (ledger.rs) | per attempt, when final | core | v2 | R1-R6 |
| 4.41 | report/blockctx.jsonl | toolkit `arbx-report blockctx` (derived from accounts, slotidx, exec) | per attempt, offline | — (toolkit output) | new | R4, R5 |
| 4.42 | ledger.jsonl | src/ledger.rs | per wallet transaction | core | new | R1 |
| 4.43 | snapshots.jsonl | src/ledger.rs | hourly, start, stop | slow | new | R1 |
| 4.44 | recon.jsonl | src/ledger.rs | hourly, stop | slow | new | R0, R1 |
| 4.45 | experiments.jsonl | src/experiments.rs | config, block switches | slow | new | R10 |
| 4.46 | verify.jsonl | src/verify_client.rs | per verifier result | chain | new (Stage 1) | R10, X9 |
| 4.47 | discovery.jsonl | feeds/discovery.rs | per 10 s | bulk | new (Stage 1) | X8 |
| 4.48 | signer-stats.json, cu-table.json | engine.rs::save_signer_stats; toolkit | every 10 s; on demand | — | kept; new | — |
| 4.49 | probe.json | src/probe.rs (`arbx grpc-probe`) | on demand; copied into each segment at boot | slow | new | R0 |

---

## 4. Stream schemas

Fields marked **(v1)** exist in arb-lab's files with the same meaning; **(new)** are added by arbx.

### 4.1 campaign.json

Written by `deploy/run-w.sh` at campaign start and rewritten after each segment.

| Field | Type | Semantics |
|---|---|---|
| schema | str | `arbx.campaign/1.0` |
| name | str | campaign name |
| started_ns, ended_ns | t_ns / null | wall times |
| operator | str | who started it (`--who`) |
| binary | {path, sha256} | the copied binary every segment runs |
| config | {path, sha256, normalized_sha256} | the frozen config |
| budget | {equity_drop_day_sol, failed_fee_budget_lamports} | limits given at start |
| segments | [{name, started_ns, ended_ns, exit_code, stop_reason, class (`natural`, `operator`, `safety`, `crash`)}] | one per segment |
| crash_count_15min | integer | crashes only (operator stops excluded) |

### 4.2 meta.json (v2)

Producer: `src/provenance.rs`, called from `main.rs::run` before feeds start. Written once.

| Field | Type | Semantics |
|---|---|---|
| schema | str | `arbx.meta/2.0` |
| run | {campaign, segment, dir, started_ns, host, pid, uid, argv, mode (`shadow`, `live`, `canary`), forced_shadow (bool), live_flag (bool)} | argv never holds secrets |
| build | {version, git_commit, git_dirty, dirty_sha256, rustc, profile, target_features, build_ts, binary_sha256, binary_size} | from `buildinfo.rs` and `/proc/self/exe` |
| config | {path, file_sha256, normalized_sha256, config_version, frozen_copy, campaign_config_sha256, matches_campaign (bool)} | `frozen_copy` = `config.toml` in the segment dir |
| programs | [{role (`route`, `venue`), id, name, programdata, last_deploy_slot, elf_len, elf_sha256, elf_md5, expected_sha256, ok}] | programdata fetched at boot. **Hash procedure** (F21): the programdata account is a 45-byte header (u32 state tag 3, u64 deploy slot, `Option<Pubkey>` upgrade authority, padded), then the ELF, then zero padding to the allocated length. `elf_len` = the maximum of `e_shoff + e_shnum × e_shentsize` and the end of every section's and program header's file range. The hashes cover bytes `[45, 45 + elf_len)`. Tested on 8K8uyQDt, where the md5 is `809315be…` |
| wallet | {pubkey, keystore_path, held_mints_at_boot: [pk]} | |
| feeds | [{id, name, kind, enabled, host}] | `id` is the feed index used by every stream (txarr column order, `feed` fields) |
| send_paths | [{id, name, kind, host, max_per_sec, tip_accounts_n}] | |
| rpc | [{name, host, roles: [`boot`, `exec`, `backfill`, `wallet`, `slotidx`, `blockhash`, `snapshot`, `leaders`], max_rps}] | hosts only, never URLs with keys |
| state | {url_host, tx_streams: [{name, account_include, max_accounts}], watch_clock, watch_programdata, watch_wallet, block_meta} | |
| probe | {file_sha256, t_ns, accepted: [str], refused: [{sub, error}]} / null | from `probe.json` (§4.49) |
| chainfetch | object | the effective `[chainfetch]` config |
| pools | {summary, n_pools, n_pairs, by_venue, seed_csv_sha256, registry_sha256, file: "pools.json"} | |
| streams | {name: schema} | every stream this binary writes |
| experiments | object | the `[experiments]` config, or null |
| limits | {max_size_sol, max_size_src (`owner OD-4` or `config`), supervisor: {...}, ledger: {...}} | effective safety limits; `max_size_sol` is the owner's Stage-0 decision (F37) |
| campaign_dir | str / null | `--campaign-dir`, used for campaign-wide stops |
| clock | {source: "CLOCK_REALTIME", sync_offset_ms, sync_source} | from adjtimex / chronyc |
| strategy, send, builder, tips, state | object | effective config sections (normalized) |
| (v1) started_ns, feeds, strategy, pools, wallet, send_paths, gate, sim, canary, live, exec | — | v1 had only these, as Debug strings |

### 4.3 stop.json

Producer: `main.rs::run` at exit (also on panic via a hook). Written once.

| Field | Type | Semantics |
|---|---|---|
| schema | str | `arbx.stop/1.0` |
| ended_ns | t_ns | |
| reason | enum StopReason | Appendix A.5 |
| detail | str | human text |
| signal | {signo, sender_pid, sender_uid, sender_cmdline} / null | from signal-hook `WithOrigin` |
| control | {who, why, cmd} / null | from the control socket or a supervisor file |
| exit_code | integer | 0 deadline, 10 operator, 20 safety, 30 error |
| in_flight_at_stop | integer | open attempts when stopping began |
| drained | bool | all reached a final state |
| drain_ms | ms | time spent draining |
| unsettled | [attempt] | still open at exit; the next segment's ledger picks them up |
| final_status_seq | integer | the last `status.jsonl` seq |

### 4.4 manifest.json

Producer: `src/rec/manifest.rs`, every 60 s and at close (atomic rename).

| Field | Type | Semantics |
|---|---|---|
| schema | str | `arbx.manifest/1.0` |
| t_ns | t_ns | when written |
| final | bool | written at close |
| streams | [{name, schema, class, files: [{path, bytes_raw, bytes_written, records, first_t_ns, last_t_ns, closed, sha256}], records_total, dropped_total, queue_cap, queue_hwm}] | `sha256` only for closed files |
| disk | {budget_bytes, used_bytes, fs_free_bytes, actions: [{t_ns, action}]} | §1.4 |

### 4.5 run.log

Text lines `<t_ns> <message>` (v1). They are for humans; no report parses them. Errors never contain URLs with keys (`rpc::scrub`).

`<campaign>/<segment>.out` (kept from arb-lab, F30) holds the segment's stdout and stderr, captured by run-w.sh. In arb-lab it held `eprintln!` lines such as gate and cool-down messages (exec.rs:649, :729). In arbx every such diagnostic line is also emitted as an `events.jsonl` record of kind `log`, so reports never need to parse `.out`. A panic message is the one thing that may appear only in `.out`, and `stop.json` then has `reason = panic`.

### 4.6 events.jsonl

Producer: `rec::event(kind, fields)` from any subsystem. One line per event.

| Field | Type | Semantics |
|---|---|---|
| t_ns | t_ns | |
| kind | enum EventKind | Appendix A.6 |
| subsystem | str | `feed`, `state`, `engine`, `commit`, `forks`, `send`, `jito`, `ledger`, `supervisor`, `recorder`, `leaders`, `chainfetch`, `probe` |
| feed | integer / null | feed id when relevant |
| detail | object | kind-specific: e.g. `{reason}` for gate changes, `{from, to}` for modes, `{table, attempts}` for lookup tables, `{slot}` for forks |

### 4.7 control.jsonl and supervisor.jsonl

`control.jsonl` (segment and campaign level; producer `src/control.rs` and run-w.sh):

| Field | Type | Semantics |
|---|---|---|
| t_ns | t_ns | |
| src | enum | `socket`, `file`, `signal` |
| who | str | operator name given with the command |
| cmd | enum | `status`, `pause-sending`, `resume-sending`, `shadow`, `stop`, `next`, `new-campaign` |
| why | str | required text |
| accepted | bool | |
| result | str | e.g. the new SendGate mode |

`supervisor.jsonl` (run-w.sh): `{t_ns, event (start, segment_start, segment_end, pause, resume, stop, disk_low, budget), segment, budget_left_lamports, budget_src ("ledger" or "status"), free_gb, detail}`.

### 4.8 status.jsonl (v2)

Producer: `engine.rs::write_status` with sections from `exec.rs::status`, `ledger.rs` and the recorder. Every 10 s and once at stop.

| Field | Type | Semantics |
|---|---|---|
| seq | integer | from 0 |
| t_ns, interval_ns | t_ns, integer | |
| run_s | number | seconds since start |
| slot | {processed, confirmed, finalized} | latest seen |
| tip_lag_slots_now | integer | chain tip minus store's newest slot |
| send_gate | {mode (`live`, `shadow`, `stopped`), reason, since_ns} | |
| health | {warmup_ready, lag_slo_ok, recorder_ok, leaders_ok, blockhash_age_slots_now, blockhash_src_now, jito_token_age_s_now} | |
| queue | {engine_now, engine_hwm_delta} | engine channel |
| store | {accounts_now, updates_total, updates_delta, stale_total, stale_delta, pending_groups_now} | |
| commit | {groups_delta, by_w_src_delta: {tx-stream, shred, unknown}, complete_delta, superseded_delta, timeout_unknown_delta, timeout_quiescent_delta, fork_dropped_delta, late_member_delta, torn_suspect_delta, lag_ms: pct(interval), lag_ms_by_w_src: {src: pct(interval)}} | lag = first shred of T (unexecuted feeds only) → group complete |
| forks | {abandoned_slots_delta, dead_slots_delta, versions_dropped_delta, refetch_delta, fork_priced_delta} | WP-04 |
| lag_slo | {window: "minute", p50_ms, p90_ms, ok, breaches_in_row, good_in_row, action (`log`, `shadow`)} | |
| accuracy | {scored_delta, exact_delta, pre_state_unknown_delta, by_venue: {venue: {scored, exact}}} | pre-state scoring (§4.34) |
| chainfetch | {need_rps_now, have_rps_now, backlog_now, dropped_delta, slotidx_lag_slots_now, wallet_pending_now, by_role: {role: {calls_delta, errors_delta, rate_limited_delta}}} | WP-03b |
| alts | {cached_now, waiting_txs_now, pending_retries_now, retries_delta, gave_up_delta, learned_delta} | |
| counts_total, counts_delta | {name: integer} | engine and exec counters (names in Appendix A.7) |
| latency | {stage: pct(interval)} | stages of A.8, microseconds |
| exec | {decisions_total, decisions_delta, attempts_total, attempts_delta, sent_total, sent_delta, refused_total, verdicts_delta: {outcome: n}, landed_total, landed_delta, ok_total, in_flight_now, queue_now, lambda_now} | |
| money | {equity_total_now, equity_liquid_now, rent_recoverable_now, rent_nonrecoverable_total, drop_1h_now, drop_24h_now, drop_window_src (`segment` or `campaign`), trade_gross_total, tips_total, fees_win_total, fees_fail_total, fees_other_total, failed_fees_total_lamports, failed_fees_delta_lamports, rent_locked_delta, rent_reclaimed_delta, trade_net_total, unreconciled_now, last_recon_ok} | all ledger-derived, in lamports; definitions in §4.42-§4.44; the drops are campaign-wide when `--campaign-dir` is given |
| coverage | {watched_with_tx_pct, watched_with_idx_pct, denominator_delta, wallet_with_tx_pct, wallet_update_missing_delta, slotidx_pct, unseen_share_sample, poh_trigger_pct, leader_known_pct} | interval window. `watched_with_tx_pct`: the share of the known denominator (§4.14) that has an `exec` record within 60 s. `unseen_share_sample`: from the last full-block sample |
| recorder | {dropped_total: {stream: n}, dropped_delta: {stream: n}, queue_hwm: {stream: n}} | |
| stop_reason | enum / null | only on the final line |

v1 fields (`t_ns, slot, queue, store_updates, open_opps, alts_cached, alt_waiting, ata_misses, counts, latency, exec.sending{sent, landed, wins, in_flight, failed_fees_lamports, cap_lamports, fees_lamports, tips_lamports, profit_lamports, new_token_accounts, stopped}`) are read by the legacy reader only. In v1, `counts` and `failed_fees_lamports` are totals; `profit_lamports` includes rent.

### 4.9 feedhealth.jsonl

Producer: `src/rec/health.rs`, every 10 s, one line per feed (including the state stream as feed `state` and each tx stream).

| Field | Type | Semantics |
|---|---|---|
| seq, t_ns, interval_ns | | |
| feed, name, kind | integer, str, str | |
| connected_now | bool | |
| reconnects_total, errors_total | integer | |
| packets_delta, txs_delta, forwarded_delta | integer | |
| first_arrivals_delta | integer | signatures this feed delivered first |
| lead_ms | pct(interval) | this feed's arrival minus the first arrival, over signatures it delivered |
| last_msg_age_ms_now | ms | |
| slot_max_now, slot_lag_now | slot, integer | feed's newest slot; chain tip minus it |
| provider_lag_ms | pct(interval) / null | `t_recv − created_at` when the provider fills `created_at` |
| shreds | {data_delta, code_delta, dup_delta, bad_delta, sets_ok_delta, sets_failed_delta, version} / null | raw shred feeds (`AsmStats`) |
| udp_drops_delta | integer / null | kernel drops for the feed's socket |
| channel_drops_delta | integer | events the feed could not hand to the engine |

### 4.10 resources.jsonl

Producer: `src/rec/health.rs`, every 10 s.

| Field | Type | Semantics |
|---|---|---|
| seq, t_ns, interval_ns | | |
| cpu_user_ms_delta, cpu_sys_ms_delta | integer | process, from `/proc/self/stat` |
| engine_cpu_ms_delta | integer | engine thread |
| rss_bytes_now, threads_now | integer | |
| load_avg_1m_now | number | |
| recorder_queues | {stream: {now, hwm_delta}} | |
| recorder_bytes_delta | {stream: integer} | compressed bytes written |
| disk | {run_dir_bytes_now, fs_free_bytes_now} | |
| rpc | {"<role>/<provider>": {calls_delta, errors_delta, rate_limited_delta, p50_ms}} | from the global per-(role, provider) stats registry (F29). Before revision 2, clients built with `Rpc::only` had fresh, invisible `Stats` (rpc.rs:69-72) |
| runtimes | {hot: {busy_ms_delta, tasks_now}, bg: {busy_ms_delta, tasks_now, blocking_now}} | WP-02 runtime split |

### 4.11 keepalive.jsonl (v1, kept)

Producer: `send/mod.rs::Paths::start` (:777-798). Fields: `t_ns`, `path`, `ms` (round trip, null on error), `error`. In Stage 0 only the jito-bundle path is enabled, so it measures the block engine's RTT.

### 4.12 accounts.bin (new): every watched-account update

Producers:
- the feed task in `feeds/mod.rs::forward` (account items);
- RPC fetches: boot, DLMM array fetches (`engine.rs::fetch_accounts`), fork refetches.

All go through `src/rec/accounts.rs`, which assigns each record its `aseq` when it is emitted. `aseq` is carried in `Event::Account` and the store version, so the journal and replay can name the exact record. Every update is recorded, including ones the store will reject as stale. The store's verdict is not known to the feed task, so it is recorded in the journal's ACCOUNT record (F24).

**Byte format** (after zstd decompression), little-endian:

```
file header:  magic "ARBXACC\0" (8) | u16 format = 2 | u16 hlen | hlen bytes of JSON header (§1.3)
record:       u8 kind | u32 body_len | body
  kind 1 DICT   u32 acct_id | [32] pubkey | u8 role | u32 pool_index (0xFFFFFFFF = none)
  kind 2 FULL   u64 aseq | u32 acct_id | u64 slot | u64 write_version (0 if src is RPC) | u64 t_recv_ns | u8 src | u8 flags
                | [64] txn (only if flags.bit0) | u64 lamports | [32] owner | u64 data_xxh3
                | u32 data_len | data
  kind 3 XOR    same as FULL, but `data` is data XOR (the previous record's data for this acct_id in this file);
                lengths must match, else the writer emits FULL
  kind 4 MARK   u64 t_ns | u8 mark (1 boot_begin, 2 boot_end, 3 stream_reconnect, 4 watch_list_changed, 5 fork_refetch)
                | u32 n | n × u32 acct_id
  kind 6 GAP    u64 first_lost_aseq | u64 n_lost        (written with the next record after a queue drop)
```

| Field | Semantics |
|---|---|
| aseq | segment-wide sequence number, without holes unless a GAP record says so |
| role | 0 other, 1 pool, 2 vault, 3 extra/config, 4 dlmm_bin_array, 5 mint, 6 clock_sysvar, 7 dlmm_bitmap_ext, 8 programdata, 9 wallet, 10 wallet_token_account, 11 pump_fee_config |
| src | 0 grpc stream, 1 rpc boot, 2 rpc refetch, 3 rpc snapshot |
| flags | bit0 has a txn signature; bit1 `is_startup`; bit2 reserved (revision 1's "stale" bit; the feed task cannot know it) |
| data_xxh3 | xxh3-64 of the full (reconstructed) data; replay verifies it |

RPC-sourced records have no `write_version` (0). Within one slot the store orders them by `aseq`, after every stream record of that slot. References always use `aseq`, never `(acct_id, slot, write_version)`, which would be ambiguous (F25).

Keyframes: the first record of an account in each file is FULL; then every `accounts_keyframe_every` (64) records; and whenever the data length changes. Readers keep the last data per `acct_id` and apply XOR records.

Used by: replay (store reconstruction), attribution R4 (route state at every version), predictions R8, X1 (route-wide age), X3 (repricing at the post-trigger version), `moves.log` is derivable from it.

### 4.13 journal.bin (new): the engine's input journal

Producer: `src/rec/journal.rs`, called from `Engine::step(ev, t_engine)` and `Engine::timers(t)`. These replace the body of `engine.rs::run` (:324-358) in WP-03 (moved from WP-09, F11).

**Determinism contract.**
- **Clock.** The engine reads the clock once per event. That value (`t_engine_ns`) is journaled and used for every decision made while handling the event.
- **Timers.** Timeouts (commit groups, quiescence, lookup-table retries, in-flight expiry, the lag SLO minute) are evaluated only in `timers(t)`, and every call is journaled as TIMER.
- **Outside inputs.** Inputs from other subsystems that change engine or send-check decisions reach the engine as events and are journaled as INPUT: blockhash-ring heads, leader-schedule windows, SendGate changes, quarantines, in-flight releases, health changes.
- **Latency.** Stage timestamps for latency reports are taken with real clock reads, but they are never decision inputs, and replay does not compare them.
- **Coverage.** Recordings made before WP-03 have no journal and cannot be replayed.

```
file header:  magic "ARBXJRN\0" | u16 format = 2 | u16 hlen | JSON header
record:       u8 kind | u32 body_len | u64 seq | u64 t_engine_ns | body
  1 TX_FIRST   u16 feed | u64 slot | u64 t_rx | u64 t_decoded | i8 executed (-1 none, 0 failed, 1 ok)
               | u8 enc (0 wire bytes, 1 protobuf Transaction) | u32 len | bytes
               | u8 has_loaded | [u16 nw | nw×32 | u16 nr | nr×32] | u8 has_poh | [u64 slot | u64 hashes | u32 ticks | u64 hpt]
  2 TX_COPY    [64] sig | u16 feed | u64 t_rx            (a later copy: timing only, as the engine uses it)
  3 ACCOUNT    u64 aseq (accounts.bin) | u8 store_verdict (0 accepted, 1 stale)
  4 SLOT       u64 slot | u64 parent (u64::MAX = unknown) | i32 status | u64 t
  5 BLOCK_META u64 slot | [32] blockhash | u64 height | u64 parent_slot | u64 t
  6 ALT        [32] table | u8 found | u16 n | n×32
  7 INPUT      u8 kind (1 blockhash_head, 2 leader_window, 3 gate, 4 quarantine, 5 inflight_release, 6 health,
               7 wallet_tx, 8 slotidx_missing) | u32 len | JSON
  8 TICK       (no body: housekeeping ran here; status only)
  9 STATUS     (ignored by replay)
 10 TIMER      u64 t                     (timers(t) ran: replay calls timers at exactly this point and time)
 12 GAP        u64 first_lost_seq | u64 n_lost
```

`seq` has no holes unless a GAP record says so. Replay refuses to compare decisions inside a gap interval and reports it. Volume: §5.

### 4.14 exec.jsonl (v2): every executed transaction touching a watched account

Producers, all through `src/rec/exec.rs`. Derived fields come from `src/classify.rs` and `src/proglog.rs` (WP-08).
- **The gRPC transaction stream** (`feeds/grpc.rs::feed_once`, yellowstone-tx). In Stage 0 its single filter is the PumpSwap program, as in arb-lab. It delivers every PumpSwap transaction, failed ones included, with its block index.
- **The backfiller** (`src/chainfetch/backfill.rs`, getTransaction). It covers watched transactions on the other venues, and failed watched transactions that the slot index shows landed.
- **The full-block coverage sampler** (`src/chainfetch/slotidx.rs`).

One line is written per signature. If several sources deliver it, the first is written. When the slot index (§4.16b) later gives the block index of a record that has none, a line `{"sig": <sig>, "idx_update": <idx>, "src": "slotidx"}` is added, and readers merge it into the first line.

**Coverage denominator** (status `coverage`, report R0, Stage-0 gate):
- **D1:** every signature that wrote a watched account (the `txn` of `accounts.bin` records);
- **D2:** shred- or stream-seen signatures with a watched account among their keys that the slot index shows in a confirmed block. This includes failed ones, which write nothing.

Coverage = |records with full meta and `idx` within 10 minutes| / |D1 ∪ D2|.

The full-block sampler estimates the share of watched-touching transactions in a block that belong to neither D1 nor D2: `unseen_share_sample`, with its sample count. The gate requires coverage ≥ 99% and unseen share < 1% (PLAN §6).

Measured scale (PLAN §0): D1 ran at 31-60 signatures/s on the w5h registry, and 41-48% touched a PumpSwap pool. Without a second filter or provider (PLAN OD-1), the rest needs about 16-35 getTransaction/s, plus the failed ones.

| Field | Type | Semantics |
|---|---|---|
| sig | sig | (v1) |
| slot | slot | (v1) |
| idx | idx / null | (v1) block index. Null for a backfilled record until the slot index supplies it (`idx_update`) |
| src | enum | `grpc-tx`, `rpc-backfill`, `rpc-wallet`, `rpc-block-sample` |
| found_by | [enum] | how the signature entered the denominator: `account_update`, `shred`, `tx_stream`, `ours`, `jito_processed`, `sigs_for_address`, `block_sample` |
| t | t_ns | (v1) receive time |
| ok, err | bool, str / null | (v1) `err` as `ix<i>:custom:0x<code>` / `ix<i>:ie<variant>` / `tx<variant>` (record.rs `tx_error`) |
| err_ix | integer / null | failing top-level instruction |
| why | str / null | (v1) last log line containing an error |
| fee | lam | (v1) total fee charged |
| cu | integer / null | (v1) compute units consumed |
| cost_units | integer / null | when the provider sends it |
| cu_limit, cu_price_micro | integer / null | from compute-budget instructions (null = default) |
| priority_fee | lam | `ceil(cu_limit_or_default × cu_price / 1e6)` |
| loaded_data_limit | integer / null | SetLoadedAccountsDataSizeLimit |
| version | enum | `legacy`, `0`, `1` |
| signer, signers | pk, [pk] | fee payer and all signers |
| recent_blockhash | str | base58 |
| nonce | pk / null | durable nonce account if instruction 0 is AdvanceNonce |
| keys | [pk] | static keys, then loaded writable, then loaded readonly (the full account list) |
| n_static | integer | how many of `keys` are static |
| alts | [{table, w: [u8], r: [u8]}] | lookup tables used |
| ixs | [{p, a: [u8], d}] | top-level instructions: program key index, account indices, data base64 |
| inner | [{ix, list: [{p, a, d, h}]}] | inner instructions per top-level index; `h` = stack height |
| logs | [str] / null | full log messages; null if the provider omitted them (`log_messages_none`) |
| return_data | {program, data} / null | |
| pre, post | [lam] | balances in `keys` order |
| pre_tok, post_tok | [{i, mint, owner, prog, amount: amt, dec}] | token balances |
| signer_sol | lam | (v1 `sol`) signer's lamport change |
| signer_tok | {mint: amt} | (v1 `tok`) signer-owned token changes, nonzero only |
| watched | [{acct, role, pool}] | watched accounts this tx wrote |
| venues | [str] | venue programs invoked (top-level or inner) |
| pools | [pk] | watched pools it touched |
| transfers | [{kind, from, to, lamports, mint, amount, sender, depth, ix}] | WP-08 classification; `kind` in A.4; `sender` = tip service; `depth` 0 top-level |
| tip_total | lam | sender_tip + cpi_tip |
| tip_senders | [str] | |
| jito_tipped | bool | pays any Jito tip account |
| bundle | {known, src (`jito-result`, `explorer`, `heuristic`), id, pos, size} / null | |
| arb_like | {is, why (`venues`, `pools`, `known`, `program`)} | same test as `record_rival` |
| ours | {attempt} / null | our transaction |
| prog_events | [{kind, leg, amount, code}] / null | our program's decoded logs (only for our txs) |

### 4.15 wallet.jsonl (new): our wallet's every landed transaction

Producer: `src/chainfetch/wallet.rs` through `src/rec/exec.rs` (WP-03b; F1). Revision 1 spent the single transaction filter on `@wallet`; it now stays on PumpSwap. Our signatures come from four sources, recorded in `found_by`:
- `account_update`: the `txn` of every wallet-account or wallet-token-account update. A landed transaction we pay for writes the wallet even when it fails, because the fee is charged;
- `ours`: attempts, at signing;
- `jito_processed`: Jito `processed` results;
- `sigs_for_address`: an hourly `getSignaturesForAddress`.

Each signature is fetched once with a bounded `getTransaction`. A signature found only by `sigs_for_address` raises `events` `wallet_update_missing`. Its block index comes from the slot index. The schema is the same as §4.14, plus:

| Field | Type | Semantics |
|---|---|---|
| attempt | integer / null | matched by signature |
| wallet_kind | enum | `route`, `wrap`, `unwrap`, `ata_create`, `close`, `nonce`, `transfer_in`, `transfer_out`, `other` |
| wallet_sol | lam | wallet lamport change |
| wallet_tok | {mint: amt} | changes of wallet-owned token accounts |
| created | [{acct, lamports, owner, space}] | accounts created and funded by the wallet in this tx |
| closed | [{acct, lamports, to}] | accounts closed in this tx |

### 4.16 blocks.jsonl (new)

Producer: the `feeds/grpc.rs` blocks-meta subscription (`Event::BlockMeta`), only if `arbx grpc-probe` showed that the provider offers it (`[state] block_meta = "auto"`). One line per block. Without it, `slotidx.jsonl` carries the same slot-level fields at confirmed commitment.

| Field | Type | Semantics |
|---|---|---|
| slot, parent_slot | slot | |
| blockhash, parent_blockhash | str | base58 |
| block_height | integer | blockhash validity = height + 150 |
| block_time | integer / null | unix seconds |
| executed_tx_count, entries_count | integer | |
| leader | pk / null | from the LeaderBook |
| t_recv | t_ns | |
| src | enum | `grpc` |

### 4.16b slotidx.jsonl (new): the block index of every confirmed slot

Producer: `src/chainfetch/slotidx.rs` (WP-03b; F1, F10). It makes one `getBlock(slot, {transactionDetails: "signatures", rewards: false, commitment: "confirmed", maxSupportedTransactionVersion})` per confirmed slot: about 3.7/s, as measured in w5h. The position of a signature in the returned list is its block index, which equals Yellowstone `TransactionInfo.index`. That equality is checked on every slot against the PumpSwap stream's `idx` (`idx_check`).

| Field | Type | Semantics |
|---|---|---|
| slot, parent_slot | slot | |
| status | enum | `ok`, `skipped` (the RPC reports the slot skipped or not available), `error` |
| blockhash, previous_blockhash | str | base58; also fed into the blockhash ring (src `slotidx`) |
| block_height, block_time | integer / null | |
| tx_count | integer | all transactions in the block, votes included |
| tracked | [[sig, idx]] | positions of every signature we track: D1 and D2 candidates (§4.14), and ours |
| missing | [sig] | signatures stamped with this slot by an account update, but absent from the block: fork evidence (WP-04) |
| idx_check | {n, mismatches} | PumpSwap stream `idx` against this list |
| t_fetch_ns, latency_ms, provider | | |

The full signature list is not stored (about 3,000 signatures per block). Block-ordered route context per attempt is derived offline from this stream, `accounts.bin` and `exec.jsonl` (§4.41).

### 4.17 slots.jsonl (new)

Producer: `feeds/grpc.rs` slots subscription with all statuses (`interslot_updates = true`).

| Field | Type | Semantics |
|---|---|---|
| slot | slot | |
| status | enum | `processed`, `confirmed`, `finalized`, `first_shred`, `completed`, `created_bank`, `dead` |
| parent | slot / null | |
| dead_error | str / null | |
| t | t_ns | |

### 4.18 txfetch.jsonl (new)

Producers: `src/chainfetch/*` (WP-03b). The 400 ms `getLatestBlockhash` poll is not logged per call; it appears only in the per-role stats.

| Field | Type | Semantics |
|---|---|---|
| t_ns | t_ns | completion time |
| role | enum | `wallet`, `backfill`, `slotidx`, `sample`, `settle`, `snapshot`, `leaders`, `alt`, `dlmm_arrays` |
| method | enum | `getTransaction`, `getBlock`, `getSignaturesForAddress`, `getSignatureStatuses`, `getMultipleAccounts`, … |
| key | str | signature, slot or account |
| reason | enum | `wallet_update`, `ours`, `sigs_for_address`, `move_without_tx`, `shred_seen_landed`, `attempt_route`, `slot_index`, `coverage_sample`, `expiry_check`, `catch_up` |
| queued_ns | t_ns | |
| provider | str | |
| ok | bool | |
| err | str / null | includes `unsupported_version`, `rate_limited`, `not_found`, `timeout` |
| latency_ms | ms | |
| bytes | integer | response size |

### 4.19 txarr.log (v1 format, kept)

Producer: `engine.rs::write_txarr` (:250-258), when a signature leaves the 10 s window. Text, one line per forwarded signature:
`<sig8> <slot> <first_ns> <d_0> <d_1> … <d_n>`, where `d_f` is feed `f`'s arrival in microseconds after `first_ns`, or `-` if the feed never delivered it. Feed order = `meta.feeds` ids. arbx adds the header line `# arbx.txarr/1.1 feeds=<name,name,…>`.

### 4.20 arrivals.jsonl (v1, +fields)

Producer: `engine.rs::write_arrivals` (:603-609), per decoded trigger, after its 10 s window.
Fields: (v1) `slot`, `pool`, `venue`, `source`, `first_feed`, `arrivals` {feed name: t_ns}; (new) `sig`, `t_first`.

### 4.21 rivals.jsonl (v1, +fields)

Producer: `engine.rs::record_rival` (:272-312), at shred time, for every arbitrage-like transaction (two or more venue programs, two or more of our pools, or a signer already seen doing that).
Fields (v1): `sig`, `slot`, `t`, `feed`, `why`, `signer`, `n_sig`, `v`, `cu_limit`, `cu_price`, `v1_fee`, `tips` [[account, lamports, sender name]], `nonce`, `progs`, `venues`, `agg`, `pools`, `alts`, `n_ix`, `n_keys`, `head` [data hex (48 bytes), data length, account count].
New: `loaded_data_limit`, `jito_tipped`, sender names from the full tip map (§4.14 `transfers`).

### 4.22 moves.log (v2: columns appended)

Producer: `engine.rs::on_account` (:882-887), the first update of each (transaction, pool) pair.
`<sig> <slot> <pool> <t_ns> <acct> <write_version> <role>`. The first four columns are arb-lab's; a v1 reader ignores the rest.

### 4.23 poh.log (v2: columns appended)

Producers: `feeds/mod.rs::forward` (entries feeds, :171-179) and `feeds/shred.rs::poh_advance` (shred feeds, :247-266). Always on (no longer tied to exec).
`<sig8> <slot> <ms> <feed> <entry_idx>`: `ms` = position on the leader's PoH clock since the slot began (hashes / hashes-per-tick × 6.25 ms); `entry_idx` = entry index within the slot when known, else `-`. The same signature can appear once per feed; readers keep the line from the feed with full slot coverage (`slots-feed` `poh_complete`), else the earliest.

### 4.24 slots-feed.log (v2; arb-lab `slots.log`)

Producers: `feeds/mod.rs::forward` (entries feeds) and `feeds/shred.rs` (shred feeds), when a feed finishes a slot.
`<feed> <slot> <ticks> <entries> <txs> <t_first> <t_last> <valid> <data_shreds> <code_shreds> <sets_ok> <sets_failed> <poh_complete>`. The first eight columns are v1 (entries feeds; `valid` = 0 when the feed joined the slot midway). Shred feeds fill all columns; entries feeds write `-` in the last five except `poh_complete`.

### 4.25 entries-<feed>.bin (v1 frame format, per feed)

Producer: `rec::archive` from `feeds/mod.rs::forward` (:159). One file series per archived feed (`[record] archive_feeds`). Frame: `u64 slot | u64 t_ns | u32 len | len bytes` (the raw entries message), after a header `magic "ARBXENT\0" | u16 1 | u16 hlen | JSON`. Bulk class: first to stop under disk pressure.

### 4.26 alts.jsonl (v2: events) and alts-final.jsonl

Producer: `engine.rs::learn_alts`, `fetch_alt`, `on_alt`, `process` (lookup-table resolution).

| Field | Type | Semantics |
|---|---|---|
| t_ns | t_ns | |
| table | pk | |
| event | enum | `learned_feed` (entries learned from a feed that sends loaded addresses), `fetch_start`, `fetch_ok`, `fetch_missing`, `fetch_error`, `retry_scheduled`, `give_up`, `waiters_released`, `waiters_dropped` |
| n_addrs | integer / null | entries known after the event |
| attempt | integer | fetch attempt number |
| next_retry_ms | integer / null | |
| waiting_txs | integer | transactions waiting on this table |
| err | str / null | |

`alts-final.jsonl` (written at stop): `{table, addrs: [pk or null]}` per known table, the v1 `alts.jsonl` content.

### 4.27 leaders.jsonl (new)

Producer: `src/leaders.rs`, when a 400-slot window of the schedule is fetched, plus kind updates.

| Field | Type | Semantics |
|---|---|---|
| slot | slot | |
| leader | pk | validator identity |
| kind | enum | `jito`, `bam`, `other`, `unknown` |
| kind_src | str | which source: the Jito validators API host, `bundle_result` (validator identity seen in our Accepted/Processed results; used for BAM), a public BAM list if one is identified, or the static file and its date (F39) |
| kind_age_s | integer | age of that list |
| region | str / null | country or city code from the offline geo table |
| rtt_ms | ms / null | latest QUIC-handshake RTT from our host to the leader's TPU-QUIC address. This is **not** the bundle's path, which runs block engine → leader (F40); the block-engine RTT is `attempts.leader.be_rtt_ms` |
| rtt_age_s | integer / null | |
| rtt_src | enum / null | `quic_handshake`, `region_bucket` (fallback when handshakes are refused) |
| client | str / null | from the version string |
| t_ns | t_ns | when written |

### 4.28 validators.jsonl (new)

Producer: `src/leaders.rs`, hourly snapshot. One line per validator: `{t_ns, identity, vote, stake_lamports, gossip_ip, tpu_quic, version, client, jito, bam, region, rtt_ms, src}`.

### 4.29 pools.json (new)

Producer: `main.rs::run` after `pools::boot`. The registry the segment traded: `[{idx, venue, pool, t0, t1, vault0, vault1, t0_prog, t1_prog, extra: [pk], flag, source (seed/ours/both), tier, pair_key}]`. `idx` is the pool index used in `accounts.bin` (`pool_index`).

### 4.30 triggers.jsonl (v2: decoded swaps are hints)

Producer: `engine.rs::on_trigger` (:611-672), for every decoded swap on a watched pool.

| Field | Type | Semantics |
|---|---|---|
| sig, feed, slot, pool, venue, source | | (v1) |
| zfo, amount, exact_out, executed | bool, u64, bool, bool / null | (v1) |
| st | {rx, decoded, engine, resolved, decided} | (v1) t_ns stages |
| opp | null | (v1 field; always null in v2: hints are never priced) |
| hint_only | bool | true |
| signer | pk | |
| signer_stats | [ok, failed] | at the time |
| skip | enum / null | `will_fail` (slippage bound unmeetable), `signer_fails`, `unquotable`, `exact_out_unsolved` |
| w_expected | [pk] | watched writable accounts this tx will write (registered with the CommitTracker) |
| shadow_pred | bool | a shadow prediction was made for the accuracy monitor |

### 4.31 commits.jsonl (new)

Producer: `src/commit.rs` when a group resolves.

| Field | Type | Semantics |
|---|---|---|
| txn | sig | |
| slot | slot | |
| w_src | enum | `tx-stream` (PumpSwap filter; authoritative), `shred` (hint from a live shred/deshred feed), `unknown` (no W(T); resolved by quiescence) |
| w_expected | [pk] / null | null when `w_src = unknown` |
| w_seen | [{acct, wv, aseq, t}] | updates stamped `txn` |
| t_first_shred | t_ns / null | earliest arrival of `txn` from an **unexecuted** feed (shred, deshred, entries); yellowstone-tx arrivals are excluded (F33) |
| t_first_update, t_resolved | t_ns | |
| spread_ms | ms | last − first `t_recv` of the updates stamped `txn` (the input that sets `quiescence_ms`) |
| outcome | enum | `complete`, `superseded`, `timeout_unknown`, `timeout_quiescent`, `fork_dropped` |
| lag_ms | ms / null | `t_resolved − t_first_shred` (the state-lag SLO input) |
| late_members | [{acct, wv, aseq, t}] | updates stamped `txn` that arrived after resolution; a second line with `"late": true` is written when this happens (F2) |
| torn_suspect_decisions | [decision] | decisions priced on these pools between resolution and the late member |
| pools | [pk] | Tier-A pools written |
| evaluated | integer | route evaluations it triggered (join to decisions by `trigger.txn`) |

### 4.32 decisions.jsonl (new): every evaluation and every rejection

Producers: the engine's evaluation (`best_cycle` and its caller) and the exec send checks (`Exec::wants_send`, `copies`, `send`). One line per evaluation of a pool after a commit (or quiescence), holding every route evaluated.

| Field | Type | Semantics |
|---|---|---|
| decision | integer | id |
| t_ns | t_ns | |
| kind | enum | `commit`, `quiescent`, `resend_check`, `probe` |
| trigger | {txn, slot, t_first_shred, pool} | |
| routes | [{buy, sell, mint, buy_venue, sell_venue, size, gross, net, cu, crossed: [u32, u32], reason}] | every route evaluated; `reason` = `best`, `below_min_profit`, or a rejection code |
| best | index into `routes` / null | |
| sv | sv | state version of the best route |
| route_age_ms | ms | time since the last write to any account of the best route (X1 input) |
| parts_skew_slots | {buy, sell} | the skew within each pool's consistency set (PLAN WP-04 item 4); never across pools |
| w_src | enum | of the triggering group |
| torn_suspect | bool | set afterwards if a late member of the triggering group arrived (written as a follow-up line `{decision, torn_suspect: true}`) |
| fork_priced | bool | set afterwards if a version this decision read was on an abandoned fork (follow-up line) |
| band | integer | the shared band table (PLAN WP-06 item 8, `[bands] edges`): 0 <20k, 1 20k-100k, 2 100k-1M, 3 1M-10M, 4 ≥10M, over the expected **edge** = gross − base fee, before the tip (F22). The same value is used by the send queue and the tip policy |
| crowding | {signers_6h, bucket (0 <20, 1 20-150, 2 ≥150), src (`map`, `static_list`)} | WP-00 / WP-05 (F6) |
| verdict | enum | `send`, `reject` |
| reason | enum | rejection reason (Appendix A.1) or `sent` |
| ev, rank | number, integer | the send queue's EV and band rank |
| attempt | integer / null | when sent |
| experiments | {name: arm} | |
| stages | {t_first_shred, t_update_recv, t_commit, t_engine, t_priced, t_decided} | t_ns; `t_update_recv` = receive time of the first update stamped with the trigger txn |

### 4.33 opportunities.jsonl (v1, kept)

Producer: `engine.rs::finish_opp` (:976-1008), for opportunities ≥ min_profit after `outcome_watch_ms`.
Fields (v1): `id`, `trigger`, `trigger_feed`, `slot`, `trigger_pool`, `buy_pool`, `sell_pool`, `mint`, `buy_source`, `sell_source`, `size_lamports`, `gross_lamports`, `net_lamports`, `cu`, `bins_crossed`, `st`, `arrivals`, `trigger_landed_slot`, `taker` {sig, slot, first_seen_ns, first_feed, window_ms}, `poh` {trigger {slot, ms_in_slot, ticks}, taker_ms_after_trigger}, `touches`.
v2 adds `decision` and `sv`. **The `taker` is a heuristic** (the first tx touching both pools); it misses single-pool and zero-capture closers (W §4). Attribution uses R4 (§6.4), never `taker`.

### 4.34 predictions.jsonl (v2: all venues)

Producer: `engine.rs::check_prediction` (:909-942), extended by WP-04 item 13 into the accuracy monitor. It runs when the decoded trigger's commit group completes, at idle time, from a bounded queue.

Fields (v1): `sig`, `venue`, `pool`; DLMM: `pred_active`, `actual_active`, `match`; DAMM v2: `sqrt_price_pred`, `sqrt_price` (u128s), `match`; CP family: `r0_pred`, `r0`, `r1_pred`, `r1` (u128s), `err0_bps`, `err1_bps`, `err0`, `err1`. In v1 the prediction was made from the store when the hint arrived. Any earlier write to the pool in the same slot made a correct prediction look "inexact": DAMM v2 matched 662 of 758 (87%, res-code §3).

New in v2 (F5):

| Field | Type | Semantics |
|---|---|---|
| t_ns, slot | | |
| hint | {exact, err} | the v1 comparison (prediction made at hint time); kept for comparison with arb-lab |
| pre_state | {known (bool), versions: [{acct, aseq, slot, wv}]} | the version of each account T wrote, just before T's write (from the 8-version ring) |
| input_src | enum | `executed` (T's executed amounts, from the PumpSwap stream or a backfilled exec record) or `decoded` |
| exact | bool / null | the prediction recomputed on `pre_state` with that input, against T's committed state; null when `pre_state.known` is false (counted as `pre_state_unknown`, never scored) |
| dlmm_bins | {checked, exact} | per changed bin |
| window_exact_pct | number / null | the pool's exact share over its last 200 scored swaps |
| quarantine_action | enum | `log` in Stage 0 (no quarantine acts; PLAN OD-8) |

R8 (§6.4) extends the scoring offline to every successful swap on a watched pool, aggregator-routed ones included. It uses `exec.jsonl` inner instructions and `arbx quote` at the pre-state version.

### 4.35 caps.jsonl (v1, kept)

Producer: `engine.rs::record_caps` (:844-874).
Fields: `id`, `kind` (`state`, `decoded`), `slot`, `buy`, `sell`, `buy_venue`, `sell_venue`, `mint`, `best_size`, `best_net`, `at_trade_size` [size, net], `caps` [[budget_sol, size, net or null]]. v2 adds `decision`.

### 4.36 sims.jsonl (v1, diagnostic only)

Producer: `exec.rs::simulate` (:372-416), at most `[sim] max_per_sec`. RPC simulation at processed commitment, usually one slot behind the trigger (res-engine §2): it measures RPC lag, not the gap. No gate uses it any more.
Fields (v1): route fields (`opp`, `trigger`, `trigger_feed`, `slot`, `buy_pool`, `buy_venue`, `buy_source`, `sell_pool`, `sell_venue`, `sell_source`, `mint`, `size_lamports`, `predicted_mid`, `predicted_back`, `predicted_profit`, `gross_at_opp`, `net_at_opp`), `t_ns`, `build_us`, `canary_bytes`, `build_error` or (`bytes`, `locks`, `cu_limit`, `creates_ata`, `min_profit`, `sim_ms`, `sim_slot`, `err`, `code`, `meaning`, `encoding_ok`, `units`, `delivered`, `logs_tail`) or `sim_error`.

### 4.37 attempts.jsonl (v2)

Producer: `exec.rs::send`, at signing. One line per attempt.

| Field | Type | Semantics |
|---|---|---|
| attempt, decision, opp | integer | |
| t_ns | t_ns | (v1) signed time |
| kind | enum | `live`, `canary` |
| trigger | {txn, slot, kind (`commit`, `quiescent`, `resend`), t_first_shred} | (v1 `trigger`, `trigger_feed`, `slot`) |
| route | {buy_pool, buy_venue, buy_source, sell_pool, sell_venue, sell_source, mint, mint_prog, hub} | (v1 flat fields) |
| size_lamports | lam | (v1) |
| expected | {mid, back, gross, fee, tip, net} | (v1 `predicted_mid`, `predicted_back`, `expected_profit` = gross) |
| band | integer | |
| sv, route_age_ms, parts_skew_slots | | from the decision |
| min_profit_onchain, margin | lam | |
| tip | {lamports, account, sender, share, band, arm, policy} | |
| tx | {sig, bytes, locks, alts: [pk], alt_fallback (`none`, `alt_index`, `held_ata`), cu_limit, cu_src (table cell key or `fallback`), cu_price_micro, loaded_data_limit, creates_ata, closes_ata, guard_max_drop, program: {id, kind (`nexus-v2`, `arbx-exec`), layout}} | |
| blockhash | {hash, slot, height, age_slots, commitment, src (`blocks_meta`, `slotidx`, `shred_entry`, `rpc_latest`)} | F14 |
| leader | {target_slot, identity, kind, kind_src, region, rtt_ms, rtt_src, rtt_age_s, client, be_rtt_ms, next: {slot, identity, kind}} | the LeaderBook snapshot (WP-03 / WP-05; region, RTT and client from WP-08). `rtt_ms` is host → leader TPU-QUIC; `be_rtt_ms` is the latest keep-alive RTT to the block engine |
| crowding | {signers_6h, bucket, src} | as in decisions |
| inflight | {key, prev_attempt, prev_sv, why_allowed (`first`, `new_state`, `new_leader`, `new_slot_verified`)} | |
| queue | {rank, ev, wait_us, lambda} | send-slot queue |
| experiments | {name: arm} | e.g. `x2_delay_ms`, `x4_share` |
| stages | {t_first_shred, t_update_recv, t_commit, t_engine, t_priced, t_decided, t_built, t_signed, t_enqueued, t_dequeued, t_sent, t_ack} | (v1 `st` had rx, decoded, engine, resolved, decided, built, signed. From WP-00, state-trigger attempts fill `rx` with the update receive time and `engine` with the dequeue time instead of one value, and they add `fired`) |
| copies | [{path, sig, bytes, tip, min_profit}] | (v1) one copy in Stage 0 |
| route_in | {accounts: [{acct, wv}], dlmm_arrays: {pool: [i64]}, buy_end, sell_end} | references for offline rebuild (X6) |

v1-only fields (`fee_arm`, `path_arm`, `trigger_cu_price_micro`, `rival_cu_price_micro`, `cu_price_micro`, `priority_fee_lamports`, `worst_fee_lamports`, `creates_token_account`, `nonce`, `not_sent`, `bundle_resends`) are read by the legacy reader only.

### 4.38 copies.jsonl (v1, +fields)

Producer: `send/mod.rs::Paths::fire` (:813-867), one line per copy, sent or not.
Fields (v1, struct `Sent` :689-706): `attempt`, `path`, `sig`, `tip_account`, `tip_lamports`, `t_sent` (0 = never sent), `t_ack` (0 = never answered), `ms`, `ok`, `status` (HTTP; null for gRPC), `reply`, `bundle`.
New: `blockhash_slot`, `queue_wait_us`.

### 4.39 bundles.jsonl (v2): every block-engine result

Producer: `send/jito.rs::on_result` (:337-358), for every result on the subscription, ours or not yet matched.

| Field | Type | Semantics |
|---|---|---|
| t_ns | t_ns | (v1) receipt time |
| bundle | str | (v1) uuid |
| outcome | enum | (v1) `processed`, `finalized`, `accepted`, `lost-auction`, `would-fail`, `dropped`, `rejected` |
| slot, index, bid | integer / null | (v1) slot; bundle index in block (processed); winning bid (lost-auction) |
| detail, code | str / null | (v1) block-engine text; parsed code (`0x4e580002`, `blockhash-not-found`, `instruction-error`, `other`) |
| sig | sig / null | (v1) our transaction |
| seq | integer | nth result for this bundle (0 = first) |
| validator | pk / null | from `Accepted`/`Processed` `validator_identity` |
| attempt | integer / null | |
| stream_epoch | integer | result-stream connection number; a gap between epochs is in `events.jsonl` (`jito_stream_down`) |

### 4.40 outcomes.jsonl (v2)

Producer: `exec.rs::on_settled`, rewritten around `ledger.rs` (WP-07), when the attempt is final.

| Field | Type | Semantics |
|---|---|---|
| attempt, opp | integer | (v1) |
| t_ns | t_ns | (v1) written |
| sig | sig | our transaction |
| final | enum | `landed_ok`, `landed_fail`, `not_landed_expired`, `not_landed_refused`, `unsettled` |
| final_t_ns, final_src | t_ns, enum | `wallet`, `jito`, `expiry` (after the one bounded `getSignatureStatuses` with `searchTransactionHistory` found nothing), `statuses` |
| amend | bool | true on a later line for the same attempt, written when a landing is found after the attempt was finalised (for example from the next segment's wallet stream, F43); readers take the last line per attempt and report amends |
| verdicts | [{t_ns, outcome, slot, validator, index, bid, code, detail}] | every block-engine result, in order |
| first_verdict_ms | ms / null | from `t_sent` |
| accepted | {t_ns, slot, validator} / null | first `accepted` |
| processed | {slot, index, validator} / null | |
| landed | {slot, idx, t_wallet_ns, leader, leader_kind} / null | from `wallet.jsonl` |
| slots_after_trigger | integer / null | (v1) |
| poh | {trigger: {slot, ms, feed}, ours: {slot, ms, feed}, ours_ms_after_trigger} | (v1 shape + feed) |
| ms_after_trigger_src | enum | `poh`, `block_idx`, `arrival` |
| seen | {first_ns, first_feed, by: {feed: t_ns}} | (v1 `seen_by`) our tx in our feeds |
| send_to_seen_ms | ms / null | (v1) |
| ok, err, code, meaning | | (v1) |
| fee_lamports, cu_consumed | lam, integer | (v1 fee) |
| prog_events | [{kind (`leg`, `out`, `profit_fail`, `guard_fail`, …), leg, amount, code}] | decoded program logs |
| delivered, predicted | [u64], [mid, back] | (v1) |
| round_trip_on_chain, round_trip_predicted | lam | (v1) |
| ledger | {trade_gross, tip, fee, rent_nonrecoverable, rent_locked, rent_reclaimed, trade_net, equity_delta, liquid_delta} | from `ledger.jsonl` |
| closer | null | always null in the bot; the toolkit's `blockctx` and R4 compute it |
| statuses_checks | [{t_ns, result}] | bounded cross-checks |

v1-only fields (`gate`, `copies` [...], `landed` as a path name, `tip_paid_lamports`, `profit_lamports` (includes rent), `profit_vs_expected`, `jito` (one verdict), `settle_error`, `failed_fees_lamports` (running total), `cap_lamports`, `run_profit_lamports`) are read by the legacy reader.

### 4.41 report/blockctx.jsonl (toolkit output): block-ordered route context per attempt

Producer: the toolkit, `arbx-report blockctx <segment>` (WP-10; F10). Revision 1 had the bot fetch a full `getBlock` for every slot of every attempt's window. Because an attempt that never lands is final only when its blockhash expires, those windows covered nearly every slot at more than twice the planned fetch rate. The bot now records the inputs once per slot (`slotidx.jsonl`, `accounts.bin`, `exec.jsonl`), and the toolkit derives the context deterministically.

- **Window:** [trigger slot, max(landed slot, last verdict slot, trigger slot + 4)] + 1.
- **Shared slots:** slots shared by several attempts are processed once.
- **Gaps:** a slot without a slot-index line, or a route-writing transaction without an `exec` record, is a gap. `--fill-gaps` fetches the full block for such a slot through `chain.py` (rate-limited, cached in `chain-cache/`).

| Field | Type | Semantics |
|---|---|---|
| attempt | integer | |
| route_accounts | [pk] | |
| window | {from_slot, to_slot} | as above |
| slots | [{slot, leader, kind, tx_count, complete, txs: [{idx, sig, signer, ok, wrote: [pk], ours, jito_tipped, tip, bundle_pos}]}] | transactions that wrote a route account (from `accounts.bin` `txn`), failed transactions that touched one (from `exec.jsonl`), and ours, in block order. `bundle_pos` only when known (our `processed` results, or explorer) |
| trigger | {slot, idx} / null | |
| ours | {slot, idx} / null | |
| closer | {sig, signer, slot, idx, kind, ms_after_trigger_poh} / null | from R4 (§6.4) |
| src | enum | `recorded` (slot index + accounts + exec), `rpc-block` (gap filled), `mixed` |
| complete | bool | every slot in the window has a slot-index line, and every route-writing transaction has an `exec` record with `idx` |

### 4.42 ledger.jsonl (new): money by signature

Producer: `src/ledger.rs`, one line per transaction in `wallet.jsonl`.

**Equity definitions** (F7). Revision 1 counted all rent as an asset in `equity_total`, yet also required rent categories to sum to the equity change. Both cannot hold for a transaction that creates an account, and the non-recoverable PumpSwap accumulator rent was hidden as an asset. Revision 2 defines:
- **Liquid equity** = native SOL + WSOL token amount.
- **Recoverable rent** = lamports held in accounts the wallet owns and can close: token accounts (for the WSOL account, its lamports minus its token amount), nonce accounts, lookup tables, and other owned accounts flagged `recoverable`.
- **Total equity** = liquid equity + Σ other tokens at the recorded mid + recoverable rent at face value.
- **Non-recoverable rent** (the PumpSwap user volume accumulator, 1,346,200 lamports, owner pAMMBay6) is never an asset. It is expensed in the transaction that creates it.
- **Which equity is used where:** stops, budgets and the main reconciliation use total equity. The liquid basis is reconciled too.

| Field | Type | Semantics |
|---|---|---|
| sig, slot, idx, t_ns | | |
| attempt | integer / null | |
| kind | enum | `route`, `wrap`, `unwrap`, `ata_create`, `close`, `nonce`, `alt`, `transfer_in`, `transfer_out`, `other` (= `wallet.jsonl` `wallet_kind`) |
| ok | bool | |
| wallet_sol | lam | wallet lamport change (post − pre) |
| wsol | lam | change of the WSOL **token amount** in the wallet's WSOL account(s) (raw = lamports) |
| tokens | {mint: {amount: amt, value_lamports: lam, mid_src}} | other wallet-owned token-amount changes, valued at the recorded mid |
| fee | lam | `meta.fee` |
| tip | lam | sender_tip + cpi_tip paid by the wallet |
| rent_locked | lam | lamports the wallet put into **recoverable** accounts created in this tx (informational) |
| rent_reclaimed | lam | rent lamports returned to the wallet by accounts closed in this tx. For a WSOL account close, only its rent part; the amount part is a `wsol` decrease (informational) |
| rent_nonrecoverable | lam | lamports the wallet put into accounts created in this tx that it cannot close (an expense; a summing category) |
| liquid_delta | lam | `wallet_sol + wsol` |
| equity_delta | lam | `liquid_delta + Σ tokens.value_lamports + rent_locked − rent_reclaimed` (the change of total equity; `rent_nonrecoverable` is not added back) |
| trade_gross | lam | ok route txs: `equity_delta + fee + tip + rent_nonrecoverable`; 0 otherwise |
| trade_net | lam | `trade_gross − fee − tip` |
| categories | [{cat, lamports}] | **summing** categories of Appendix A.3. Their sum equals `equity_delta` exactly |
| stranded | [{mint, amount}] | non-quote tokens left by a route (their value is already in `tokens`) |
| check | {delivered_round_trip, diff} / null | wins: `trade_gross` against the `NXV2OUT` round trip from logs |

**Summing categories:** `trade_gross` (+), `tip` (−), `fee_win` (− fee of an ok route tx), `fee_fail` (− fee of a failed tx), `fee_other` (− fee of a non-route tx), `rent_nonrecoverable` (−), `transfer_in` (+), `transfer_out` (−), `other`.

**Informational (never summed):** `rent_locked`, `rent_reclaimed`, `liquid_delta`, `stranded`; `inventory_reval` exists in recon only.

**Identities a reader may rely on:**
- Σ summing categories = `equity_delta` on every line.
- A failed tx has `equity_delta = liquid_delta = −fee` (tips and creations revert).
- A rent-neutral route has `rent_locked = rent_reclaimed`.
- `equity_delta − liquid_delta = Σ tokens.value_lamports + rent_locked − rent_reclaimed`.

**Golden examples** (WP-07 offline tests; fee F, tip T, rent R; values from res-pnl §2 where named):

| Case | wallet_sol | wsol | rent_locked | rent_reclaimed | rent_nonrecoverable | liquid_delta | equity_delta | Summing categories |
|---|---|---|---|---|---|---|---|---|
| ATA create only (R = 2,039,280) | −R − F | 0 | R | 0 | 0 | −R − F | −F | fee_other −F |
| Route win with create + close, WSOL gain G | −F − T | +G | R | R | 0 | G − F − T | G − F − T | trade_gross +G, tip −T, fee_win −F |
| Route win that creates the accumulator (U = 1,346,200) and leaves a Token-2022 ATA open (R = 1,513,840; w5h-p6#69) | −F − T − U − R | +G | R | 0 | U | G − F − T − U − R | G − F − T − U | trade_gross +G, tip −T, fee_win −F, rent_nonrecoverable −U |
| Route win leaving an ATA open (R = 1,488,440) | −F − T − R | +G | R | 0 | 0 | G − F − T − R | G − F − T | trade_gross +G, tip −T, fee_win −F |
| Failed (landed) route | −F | 0 | 0 | 0 | 0 | −F | −F | fee_fail −F |
| Wrap X (WSOL account exists) | −X − F | +X | 0 | 0 | 0 | −F | −F | fee_other −F |
| Unwrap: close the WSOL account holding A, rent R | +A + R − F | −A | 0 | R | 0 | R − F | −F | fee_other −F |

### 4.43 snapshots.jsonl (new)

Producer: `src/ledger.rs`, hourly (`snapshot_min`), at start and at stop, by bounded RPC on the background runtime. Every call carries `minContextSlot` = the context slot of the first answer. If the answers' context slots differ, the snapshot is retried up to `snapshot_retries` (3) times. After that it is written with `slot_mismatch: true` and is not used for reconciliation (F34).

| Field | Type | Semantics |
|---|---|---|
| t_ns, slot | | the common context slot of the RPC answers |
| slot_mismatch | bool | true if no common slot was obtained (the snapshot is not reconciled) |
| sol | lam | native balance |
| wsol | lam | WSOL token amount |
| tokens | [{mint, account, program, amount: amt, decimals, rent_lamports, mid_lamports_per_unit, value_lamports, stranded}] | every token account. `rent_lamports` = account lamports − token amount for WSOL, else the account lamports |
| nonce_accounts | [{account, lamports}] | |
| alts | [{table, lamports}] | |
| other_owned | [{account, owner, lamports, recoverable}] | e.g. the PumpSwap accumulator (`recoverable: false`) |
| rent_recoverable | lam | Σ `tokens.rent_lamports` + nonce + ALT + `other_owned` with `recoverable: true` |
| rent_nonrecoverable | lam | Σ `other_owned` with `recoverable: false` (shown, never in equity) |
| token_value | lam | Σ `tokens.value_lamports` (excluding WSOL) |
| equity_liquid | lam | `sol + wsol` |
| equity_total | lam | `equity_liquid + token_value + rent_recoverable` |
| mids_src | {mint: {pool, slot}} | |
| rpc | {provider, calls, ms, attempts} | |

### 4.44 recon.jsonl (new)

Producer: `src/ledger.rs`, hourly and at stop, between two snapshots without `slot_mismatch`.

| Field | Type | Semantics |
|---|---|---|
| t_ns | t_ns | |
| from, to | {t_ns, slot} | the two snapshots |
| delta_equity | lam | `to.equity_total − from.equity_total` |
| sum_entries | lam | Σ `ledger.equity_delta` for txs with slot in (from.slot, to.slot] |
| inventory_reval | lam | `(to.token_value − from.token_value) − Σ ledger tokens.value_lamports` over the window: the part of the token-value change that comes from mid changes, not from transactions |
| residual | lam | `delta_equity − sum_entries − inventory_reval`. Because of how `inventory_reval` is defined, this equals `(Δequity_liquid + Δrent_recoverable) − Σ(liquid_delta + rent_locked − rent_reclaimed)`, which does not depend on valuation |
| liquid | {delta, sum_entries, residual} | `Δequity_liquid` against Σ `liquid_delta` |
| token_amounts | [{mint, delta_snapshot, sum_entries, ok}] | raw token amounts must match exactly; a mismatch is a miss |
| tolerance | lam | 10,000 |
| ok | bool | `abs(residual) ≤ tolerance` and `abs(liquid.residual) ≤ tolerance` and every `token_amounts.ok` |
| by_category | {cat: lam} | summing categories only; informational sums are listed separately |
| unexplained | [{sig, slot, src ("getSignaturesForAddress")}] | wallet txs missing from the ledger |
| action | enum / null | `shadow` on a miss |

Rent itself can never cause a false miss. Recoverable rent sits in total equity on both sides of the identity, and non-recoverable rent is an expense category.

### 4.45 experiments.jsonl (new, Stage 1)

Producer: `src/experiments.rs`. `{t_ns, experiment, event (`config`, `block_switch`, `pause`), arms, weights, seed, scope, block: {id, arm, from_ns, to_ns}}`. Per-decision arms are in `decisions.jsonl` and `attempts.jsonl`.

### 4.46 verify.jsonl (new, Stage 1)

Producer: `src/verify_client.rs`. `{t_ns, attempt or decision, mode (`offline`, `shadow`, `gate`), ok, err, equity_delta, cu, logs_tail, latency_us, svm_slot, program_hashes}`.

### 4.47 discovery.jsonl (new, Stage 1)

Producer: `src/feeds/discovery.rs`, every 10 s: `{seq, t_ns, connection, owners, updates_delta, accounts_now, lag_ms pct, rate_limited_delta, x8_block}`.

### 4.48 Cross-run files

- `runs/signer-stats.json` (v1, `engine.rs::save_signer_stats`): `{signer: [ok, failed]}`, saved every 10 s.
- `data/cu-table.json` (new; toolkit `cu-table`): `{schema, built_ns, source_runs: [..], legs: {"<venue>|<bins_bucket>": {n, p50, p99}}, overhead: {program, n, p99}, extras: {ata_create, ata_close, tip}, cells: {"<buy_venue>|<sell_venue>|<bins_bucket>|<creates_ata>": {limit, src (`legs` or `fallback`)}}}`. The `legs` samples come from the venue programs' `consumed X of Y compute units` log lines in every watched transaction in `exec.jsonl`, rivals included (F36).
- Campaign equity (WP-07): no separate file. `arbx campaign-equity --campaign-dir` reads the segments' `ledger.jsonl` and `snapshots.jsonl` and prints `{t_ns, equity_total_now, drop_1h, drop_24h, segments_read}` as JSON.

### 4.49 probe.json (new)

Producer: `src/probe.rs` (`arbx grpc-probe --config <file>`; F14). It is run before WP-05, and a copy goes into each segment at boot if present. `{schema, t_ns, provider_host, subs: [{sub (`accounts_full`, `slots_interslot`, `blocks_meta`, `tx_filter_1`, `tx_filter_2`, `tx_filter_5`, `blocks_account_include`, `deshred_5`), accepted, error, messages_30s, first_msg_ms}]}`. No tokens or URLs with keys appear in it.

---

## 5. Volume and disk budget

**Measured inputs** (revision 2, from arb-lab recordings of the w5h registry, 300-377 moving pools):
- 3.72 slots/s, with at least one watched write in every slot;
- 31-60 watched transactions/s, of which 41-48% touched a PumpSwap pool (PLAN §0).

**Estimates** (est.) from arb-lab's long-1-p1: 34 account updates/s, 669 forwarded tx/s; `exec.jsonl.zst` 227 MB/h for the whole PumpSwap program; `rivals` 75 MB/h; `txarr` 72 MB/h; `poh` 72 MB/h; `alts.jsonl` 157 MB raw. These are scaled to arbx's registry: 200-500 updates/s and 50-150 watched transactions/s for about 1,000 pools.

| Stream | Per hour (compressed) | Notes |
|---|---|---|
| accounts.bin | 0.1-0.6 GB | XOR deltas make bin-array updates small; keyframes every 64 |
| journal.bin | 0.5-1.0 GB | forwarded transactions' bytes; needed for deterministic replay |
| exec.jsonl | 0.3-0.8 GB | full meta, logs and keys for watched transactions, all venues (PumpSwap from the stream, the rest backfilled) |
| slotidx.jsonl | 20-60 MB | about 13,400 slots/h; only the tracked signatures' positions are stored |
| wallet.jsonl | < 10 MB | |
| txarr, poh, rivals | 0.2-0.3 GB | as arb-lab |
| decisions, commits | 0.05-0.15 GB | |
| entries-<feed> | 1-2 GB per archived feed | bulk; off by default unless a study needs it |
| everything else | < 0.1 GB | |
| **Total without entries** | **about 1.5-3 GB/h** | **about 35-70 GB/day** |

Defaults: `disk_budget_gb = 40` per segment (a 20-minute segment uses 0.5-1 GB) and `min_free_gb = 25`. A 24 h campaign needs 40-70 GB; Cherry had 131 GB free (res-stops). Finished segments should be copied off the host daily (an owner task). The bot never deletes recorded data.

**RPC volume of the chain-fetch service** (WP-03b), for sizing PLAN OD-1:

| Role | Rate | Notes |
|---|---|---|
| slotidx | about 3.7 getBlock/s (signatures only) | about 100-300 KB each (est.), so roughly 0.4-1.1 MB/s |
| backfill | about 16-35 getTransaction/s on the w5h registry, plus failed watched transactions; 2-3× for about 1,000 pools | sized automatically (`need_rps_now`); 0 if a second filter or provider covers the other venues |
| blockhash | 2.5 getLatestBlockhash/s | small |
| wallet | a few per minute | |
| sample | 1 full getBlock/min | several MB each |
| snapshots, leaders | a few per hour, 1 per 100 slots | |

---

## 6. Analysis toolkit (`tools/arbx-report`)

### 6.1 Architecture

```
tools/arbx-report/
  arbx_report/
    streams.py       readers: header check, zstd frames, rotation series, legacy v1 files, binary formats (§4.12, §4.13, §4.25)
    model.py         typed rows and joins (attempt ↔ decision ↔ outcome ↔ ledger ↔ blockctx ↔ verdicts)
    chain.py         optional fetches (getBlock, getTransaction, explorer) with a cache in <seg>/chain-cache/
    quote.py         calls `arbx quote` (Rust, WP-09) to re-price a route at a recorded state version
    reports/         r0_quality.py … r13_compare.py (§6.4)
    stats.py         percentiles, bootstrap CIs, binomial / Fisher / Mann-Whitney tests, one-sided trend tests
    render.py        report.json + report.md
  tests/             synthetic fixtures, golden outputs, legacy known-answer tests
  __main__.py        CLI
```

- Python 3, standard library only; uses `zstandard` if installed, else pipes `zstd -dc`.
- **CLI** (also installed as the `arbx-report` script): `python3 -m arbx_report <command> <segment-or-campaign-dir> [--rpc-url-env NAME] [--offline] [--out DIR]`. Commands: `segment`, `campaign`, `quality`, `ledger`, `funnel`, `attempts`, `blockctx [--fill-gaps]` (§4.41), `attribution`, `latency`, `leaders`, `feeds`, `predictions`, `rivals`, `experiments [x2|x4|x5|x8|margin|all]`, `census` (X1), `sizes` (X3 summary), `sizefit` (X6 summary), `caps`, `cu-table`, `compare A B`.
- **Dependencies on the bot** (F35): `quote.py` needs the `arbx` binary with `arbx quote` (WP-09). R4, the all-swap part of R8, and X3 cannot run before WP-09. Without the binary these sections are marked incomplete, never computed approximately.
- **Secrets:** an RPC URL is read only from the environment variable named by `--rpc-url-env`. The toolkit never opens `.env` files. `--offline` forbids every network call; reports then mark chain-dependent sections as incomplete.
- **Determinism:** the same files (and the same `chain-cache/`) give byte-identical `report.json`. Every report records the input files' sha256 (closed files) or size and last record (open files).
- **Outputs:** `<seg>/report/report.json` (machine), `report.md` (human), one section per report with its coverage caveats on top. Campaign reports aggregate segment reports plus campaign-level joins (late landings across segments).

### 6.2 Correctness rules (every report)

1. **Counters.** `_total`: take the last line of the segment; `_delta`: sum the lines; gauges: never sum. Across segments, sum each segment's last `_total`. A `seq` gap is reported. (arb-lab's cumulative `failed_fees_lamports` was mis-summed.)
2. **Money comes from the ledger** (`ledger.jsonl`, `snapshots.jsonl`, `recon.jsonl`), never from status counters. Counters are shown only as a cross-check with the difference.
3. **Rent is separate from trading.** Trading results use `trade_net`. Recoverable rent locked and reclaimed are reported on their own and move liquid equity but not total equity. Non-recoverable rent is an expense line (§4.42).
4. **Land rates** use attempts as the denominator (copies with `t_sent > 0` and `ok`), never `getSignaturesForAddress` (D §4.13).
5. **Acceptance is not landing.** Report accepted → landed separately, by leader kind (146 accepted against 17 landed in the arb-lab window).
6. **Landed-only caveat.** A bundle that overprices its gap fails its check and never lands, so realised/expected over landed attempts cannot show overpricing (W §3). Such ratios are printed with this caveat and beside would-fail statistics.
7. **Attribution uses block order** `(slot, idx)` and state change (§6.4 R4), not arrival time and not "who profited". Arrival time is used only for "seen before our send". PoH milliseconds are compared only on the same leader's clock.
8. **Missing is not zero.** A row without a value is excluded from that statistic and counted in the coverage line; no `except: pass` (arb-lab's supervisor turned a bad status line into 0 spent).
9. **Time windows.** Wall hours = `meta.started_ns` → `stop.ended_ns`; trading hours = warm-up ready → stop, minus shadow periods from `events.jsonl`. Rates per hour state which one they use.
10. **Medians beside means, and concentration.** Every money total shows the median per event and the top-1 share; a single jackpot (like the bolt trade) is flagged when the top-1 share exceeds 50%.
11. **Units.** Lamports as integers; SOL only for display; USD only with the rate stated (from meta or the command line). USDC-quoted results use the recorded SOL/USDC mid.
12. **Schema versions.** Readers refuse unknown major versions; minor versions may add fields; legacy v1 files go through the legacy reader, and incomparable fields are named (§7).
13. **Joins by full signature.** `sig8` joins (txarr, poh) check for collisions and report them.
14. **Segments end with in-flight attempts.** Campaign reports join late landings from later segments' `wallet.jsonl` by signature; segment reports list them as unsettled.

### 6.3 R0 Data quality (runs first; every other report cites it)

- Schema versions and producer binaries per file; missing streams.
- Recorder drops per stream (`manifest.json`). Core drops are flagged as a segment fault; replay-class gaps are listed with their `aseq`/`seq` ranges.
- **Exec coverage** against the denominator D1 ∪ D2 (§4.14):
  - by venue and by `found_by`, within 60 s and within 10 minutes, with and without `idx`;
  - the sampled unseen share with its sample count;
  - `need_rps` against `have_rps`.
- **Other coverage:**
  - attempts with verdicts, leader, `blockctx` complete, and a PoH trigger position;
  - wallet transactions against `getSignaturesForAddress` (if online), and `wallet_update_missing`;
  - slots with a slot-index line, and `idx_check` mismatches;
  - feed uptime and result-stream outages (`jito_stream_down`);
  - lookup tables given up.
- **Commit groups** by `w_src`, `late_member` and `torn_suspect` counts, and `fork_priced`.
- Clock sync offset (meta); status `seq` gaps; unsettled attempts and amends; reconciliation failures; snapshots with `slot_mismatch`.

### 6.4 Reports and how each is computed

**R1 Money** (`ledger.jsonl`, `snapshots.jsonl`, `recon.jsonl`, `outcomes.jsonl`). Equity at start and end; Δ equity total and liquid; Σ categories; trade net, rent (locked, reclaimed, non-recoverable), fees on wins and on failures, tips; each reconciliation window with its residual. Splits by band, venue pair, leader kind, experiment arm. SOL/h on trading hours with medians and top-1 share. Cross-check: status `money` and per-attempt `ledger` sums must equal the ledger; any difference is printed.

**R2 Funnel** (`commits`, `decisions`, `attempts`, `outcomes`, `triggers`). Hints → commit groups (by outcome) → evaluations → routes priced → ≥ min_profit → each rejection reason (Appendix A.1) → sent → first verdict (accepted, would-fail by code, lost-auction, none with the stream up, none with the stream down) → landed → ok. Counts and per-hour rates; status `_delta` sums as a cross-check.

**R3 Attempts and Jito** (`attempts`, `outcomes`, `bundles`, `copies`, `leaders`). Would-fail rate by band × send delay (`t_sent − t_first_shred`, bucketed 0-5, 5-10, 10-20, 20-50, 50+ ms) × leader kind; time to first verdict; verdict sequences (e.g. accepted → would-fail, R §3.4's 130 cases); accepted → landed by leader kind, region and RTT bucket; lost-auction bids against our tips; blockhash age against `blockhash-not-found`; queue waits and λ; rate-limit refusals.

**R4 Attribution: who closed each gap** (`decisions`, `attempts`, `accounts.bin`, `exec.jsonl`, `slotidx.jsonl`, `report/blockctx.jsonl`, `txarr`, `poh`). Needs `arbx quote` (WP-09). For each attempt (and each opportunity ≥ min_profit):
1. Start from the decision's state version (route accounts at their `aseq`).
2. List, in block order `(slot, idx)`, every later transaction that wrote a route account, through the `blockctx` window (§4.41). The transactions come from `accounts.bin` (the `txn` of each version), with positions from `slotidx.jsonl` and `exec.jsonl`.
3. After each one, re-price the route at the attempt's size on the post-transaction state (`arbx quote --run <seg> --route … --version …`).
4. The **closer** is the first transaction after which net ≤ the attempt's on-chain min_profit. If our transaction landed first and won, the closer is us. If the route never closes in the window, the result is `persisted` (the would-fail then points to state lag, Jito's simulation, or our own pricing).
5. Classify the closer: `ours`, `arb_bot` (two or more watched pools, a known arber, or an arbitrage program), `user_swap` (one venue program), `other`. Record its position relative to the trigger (same slot and index difference, or slots later), its PoH ms after the trigger when both are on the same leader's clock, and whether it was seen in our feeds before our first send (`txarr`).
6. Failed transactions cannot close a gap (they write nothing). Those that touched the route are listed as "attempted closers".
This catches the single-pool and zero-capture closers that arb-lab's taker heuristic missed (W §4), lists reverted attempts separately, and replaces `opportunities.taker`.

**R5 Latency** (`attempts.stages`, `decisions.stages`, `commits`, `txarr`, `poh`, `outcomes`). Stage decomposition: first shred → account update received → commit complete → engine dequeue → priced → decided → signed → sent → acknowledged → first verdict → seen in our feeds → landed. State-lag SLO per minute. Ours against closers in PoH ms after the trigger. All wall-clock differences are on one host clock; cross-host comparisons only as PoH differences.

**R6 Leaders** (`leaders`, `validators`, `attempts`, `outcomes`, `bundles`, `blocks`, `slotidx`). Slot share by kind; our attempts, accepted and landed, by kind, region, client, host → leader RTT bucket and block-engine RTT bucket (`be_rtt_ms`); landings per 1,000 eligible slots by kind (X5), with confidence intervals. The host → leader RTT is labelled as such: it is not the bundle's path.

**R7 Feeds** (`feedhealth`, `txarr`, `arrivals`, `slots-feed`). Uptime, reconnects, messages; first-arrival shares and lead times; dead feeds; provider lag; PoH completeness per feed.

**R8 Predictions and accuracy** (`predictions`, `outcomes`, `verify`, `accounts.bin`, `exec.jsonl`).
- **In-bot hints:** exact-match rates per venue and pool against the pre-state version. The v1-style at-hint rate is shown beside it, and `pre_state_unknown` is counted, not scored.
- **Every successful swap on a watched pool** (needs `arbx quote`, WP-09): aggregator-routed and bot-routed swaps are decoded from `exec.jsonl` inner instructions. Each swap is re-quoted with its executed input at the version just before it, and the quote is compared with its executed output.
- **Closer check** (R §3.3): the closer's realised take against our quote at the version just before the closer (from R4).
- **Also reported:** quarantine events (log-only in Stage 0); realised against predicted round trips on landed attempts, with rule 6's caveat; and the verifier against the chain (Stage 1).

**R9 Rivals and the field** (`exec.jsonl`, `rivals`, `blockctx`). Arbitrage-like transactions on watched accounts, all venues; clean wins (signer's SOL + WSOL gain > 0 and no other token left); per signer: wins, profit, sizes, senders (full tip map), CPI tips, bundle membership, rung distribution (block index against the opener, rival-synthesis §5). Caveat printed: only transactions touching watched accounts are seen.

**R10 Experiments** (`decisions`, `attempts`, `outcomes`, `experiments`, `feedhealth`, `discovery`, `verify`). Randomization balance check first. X2: would-fail against delay arm per band, one-sided trend test, go if it falls ≥ 5 points per 10 ms (p < 0.05). X4: land rate and net per attempt by arm, bootstrap CIs, go if the land rate falls < 20% relative. X5: BAM/Jito landing ratio, go if ≥ 0.5, needs ≥ 200 eligible attempts. X8: Tier-A lag p50/p90 by block, Mann-Whitney, go if p50 +≤ 1 ms and p90 +≤ 5 ms with no 429s. X9: verifier p50/p99 per route class, go if p99 ≤ 3 ms. Thresholds are R §5's, fixed before the run.

**R11 Census and offline experiments** (X1, X3, X6). X1 (`census`): every gap on watched routes with gross, size, route class, route-wide age (from `accounts.bin`: time since the last write to any route account), winner rung, leader kind; capturable if size ≤ 4.2 SOL, age ≥ 354 ms, winner not rung 0-1, venue supported; output capturable SOL/h with medians and top-1 share against the go threshold max(0.5 SOL/h, B/0.15). X3 (`sizes`): summarises `arbx replay --reprice-sizes` (share of would-fails profitable at s/2, s/4, s/8, optimum, and summed net/h). X6 (`sizefit`): byte distribution and share within 1,232.

**R12 Caps** (`caps`, `opportunities`, R4). Budget tiers deduplicated into gap episodes (consecutive opportunities on one route within 5 slots, as `seg.py` did), now with the market's realised take from R4 instead of the "first profitable move within 5 slots" rule.

**R13 Compare** (`meta`, all reports). Config diff from the normalized configs, binary and program hashes, and metrics side by side, so segments are compared only when their provenance differs in known ways.

**cu-table** (`exec.jsonl`, `wallet.jsonl`, `attempts`; F36). It builds per-leg samples from the venue programs' `Program <id> consumed X of Y compute units` lines at the swap's invoke depth, in **every** watched transaction (rivals included), keyed by (venue, bins-crossed bucket). Our program's overhead comes from our own transactions: outer consumption minus their legs. A cell's limit = (overhead p99 + Σ leg p99 + ATA create/close + tip) × 1.10. A cell whose legs have fewer than 30 samples is marked `fallback`. The result goes to `data/cu-table.json` with sample counts.

### 6.5 Tests

All tests below are offline (CI) and run from files in the repository (F12). Field validation on a real Stage-0 segment is listed separately.
- **Synthetic fixtures** for every stream, written by a small generator in the test suite, including rotated and truncated files, replay-class gaps and `idx_update` lines.
- **Golden `report.json`** for a fixture segment; byte-identical on re-run.
- **Rule tests:**
  - summing `_delta` against taking the last `_total`;
  - land-rate denominators;
  - missing-is-not-zero;
  - R4 on a synthetic block with a single-pool closer, a failed attempted closer and a persisted gap;
  - `blockctx` windows and deduplication;
  - the coverage denominator D1 ∪ D2;
  - the ledger golden examples of §4.42 and the recon identity;
  - amended outcomes (the last line wins).
- **Legacy known-answer tests** through the legacy reader, on `testdata/legacy/` (WP-00b): res-pnl's p1-p10 decomposition (trading net −2,337,448; rent 16,383,000; `profit_lamports` −16,201,607) and W §2's bundle-arm figures.
  - Inputs: the raw v1 files preserved in `testdata/legacy/raw/` and the wallet transactions in `testdata/wallet/`.
  - Expected values: `testdata/legacy/expected.json`.
- **Field validation (owner-run):** `segment` on a Stage-0 run regenerates every report and agrees with the ledger's reconciliation within 10k.

---

## 7. Legacy (arb-lab v1) files

The legacy reader maps arb-lab's files to the v2 model where the meaning is the same and marks the rest as unavailable:

| v1 file | Mapped | Not comparable |
|---|---|---|
| status.jsonl | totals | no deltas; `profit_lamports` includes rent; `failed_fees_lamports` misses unrecorded landings |
| attempts / copies / outcomes | route, sizes, copies, landing | one verdict only; nonce-era; no state version, no leader telemetry; settle-time landings only |
| exec.jsonl | sig, slot, idx, ok, err, fee, cu, signer SOL/token deltas | PumpSwap-only (one program filter); no inner instructions, logs or keys. arbx keeps the same PumpSwap stream and adds the other venues by backfill |
| moves.log | first four columns | no write_version |
| poh.log, slots.log | as is | entries feeds only; one clock per feed |
| alts.jsonl | final dump | no events |
| triggers / opportunities | as is | decoded triggers were priced on predictions |
| bundles.jsonl | as is | no seq, no validator |
| meta.json | feeds and send paths | no hashes; Debug-string config |

Segments after w5h2-p3 have no recorder files at all (W §8); reports on them are limited to attempts, copies, outcomes, bundles, status and chain fetches.

---

## Appendix A. Enumerations

### A.1 Decision rejection reasons (`decisions.reason`, `routes[].reason`)

| Stage | Reasons |
|---|---|
| State | `pending_commit`, `route_not_quiet` (unknown W(T): a route account was written within `quiescence_ms`), `parts_skewed` (within one pool's consistency set), `store_lagging`, `account_missing`, `clock_stale`, `warmup`, `fork_pending` (a route account's version is on a slot not yet on the confirmed branch while a sibling is known) |
| Pricing | `unquotable_dlmm_array`, `unquotable_dlmm_liquidity`, `unquotable_damm`, `unquotable_cp`, `broken_quote` (round trip > input), `implausible_gap`, `below_min_profit`, `dlmm_cap` (informational: size capped) |
| Policy | `gate_shadow:<reason>`, `gate_stopped`, `recorder_unhealthy`, `venue_quarantine`, `pool_quarantine` (Stage 0: never; log only), `token_cooling`, `experiment_holdout`, `rent_cap`, `size_cap` |
| Send slot | `inflight_same_state`, `inflight_same_leader`, `band_throttle`, `rate_queue_timeout`, `crowded_pool` (dropped from the queue behind less crowded pools, F6) |
| Inputs | `blockhash_stale`, `leader_unknown`, `leader_skip_kind`, `program_hash_mismatch`, `jito_auth_stale` (no valid cached token; the send path never refreshes it, F28) |
| Flags (not rejections; follow-up lines) | `torn_suspect`, `fork_priced` |
| Build | `uva_missing`, `dlmm_ext_needed`, `oversized`, `build_error:<detail>`, `expected_below_min_profit` |
| Sent | `sent` |

### A.2 Outcome finals

`landed_ok`, `landed_fail`, `not_landed_expired` (the blockhash expired without a landing, after one bounded status check), `not_landed_refused` (the block engine refused the send), `unsettled` (the process stopped first). A later `amend: true` line can change a final (§4.40).

### A.3 Ledger categories

- **Summing** (Σ = `equity_delta`, the change of total equity; §4.42): `trade_gross`, `tip`, `fee_win`, `fee_fail`, `fee_other`, `rent_nonrecoverable`, `transfer_in`, `transfer_out`, `other`.
- **Informational** (never summed): `rent_locked` and `rent_reclaimed` (recoverable rent; they move liquid equity, not total equity), `liquid_delta`, `stranded`, and `inventory_reval` (recon only).
- **Transaction kinds**, not categories: `wrap` and `unwrap`. Their only summing category is `fee_other`.

### A.4 Transfer kinds (`exec.jsonl transfers[].kind`)

`sender_tip`, `cpi_tip`, `wrap`, `unwrap`, `self`, `venue_fee`, `platform_fee`, `rent_create`, `rent_close`, `other`.

### A.5 Stop reasons

**Stop reasons** (`stop.json`): `deadline`, `signal`, `control`, `equity_day` (campaign-wide rolling 24 h; exit 20 ends the campaign), `disk_budget`, `error`, `panic`.

**SendGate shadow reasons** (`status.send_gate.reason`, `gate_change` events; the process keeps running and recording): `control`, `forced_shadow` (`--shadow`), `equity_hour` (campaign-wide rolling hour), `reconcile_miss`, `state_slo` (only with `slo_action = "shadow"`; recovers automatically), `core_record_loss` (for the rest of the segment), `recorder_unhealthy`, `disk_budget` (before the stop).

### A.6 Event kinds

`feed_connect`, `feed_disconnect`, `feed_error`, `state_stream_reconnect`, `tx_stream_reconnect`, `jito_stream_down`, `jito_stream_up`, `warmup_ready`, `warmup_lost`, `lag_slo_breach`, `lag_slo_recovered`, `gate_change`, `fork_dead_slot`, `fork_abandoned`, `late_member`, `alt_give_up`, `programdata_change`, `quarantine` (Stage 0: `would_quarantine`), `recorder_drop`, `replay_gap`, `disk_action`, `leaders_refresh`, `leaders_list_stale`, `snapshot`, `snapshot_slot_mismatch`, `recon_miss`, `wallet_update_missing`, `blockhash_source_disagree`, `chainfetch_backlog`, `jito_token_refresh`, `probe`, `log` (diagnostic lines that arb-lab printed to stderr), `config_note`, `stop_requested`.

### A.7 Counter names (`counts_total` / `counts_delta`)

- **Engine:** `tx_first`, `trigger`, `trigger_hint_only`, `trigger_skip_will_fail`, `trigger_skip_signer_fails`, `trigger_unquotable`, `trigger_exact_out_unsolved`, `alt_wait`, `alt_learned`, `alt_retry`, `alt_gave_up`, `resolve_failed`, `commit_complete`, `commit_superseded`, `commit_timeout_unknown`, `commit_timeout_quiescent`, `commit_late_member`, `torn_suspect`, `fork_abandoned_slot`, `fork_priced`, `pred_scored`, `pred_exact`, `pred_pre_state_unknown`, `evaluation`, `route_priced`, `opportunity`, `state_opportunity`, plus one counter per rejection reason of A.1 (`reject_<reason>`).
- **Exec:** `attempt`, `sent`, `send_refused`, `live_skip_big_band_throttle` (WP-00 only), `rank_crowded`, `verdict_<outcome>`, `landed_ok`, `landed_fail`, `expired`, `expiry_status_hit`, `amended`, `unsettled`.

### A.8 Stage names (`latency`, `stages`)

- **v2:** `first_shred→update_recv`, `update_recv→commit`, `commit→engine`, `engine→priced`, `priced→decided`, `decided→built`, `built→signed`, `signed→enqueued`, `enqueued→sent`, `sent→ack`, `sent→first_verdict`, `sent→seen`, `sent→landed`.
- **WP-00 interim names** (state path, before WP-04's commit stages exist; F13): `state_recv_to_engine`, `state_engine_to_decided`, `state_recv_to_decided`, `decided_to_signed`, `signed_to_fired`. WP-02's latency gate compares against these.
- **v1 names** `rx_to_decoded`, `decoded_to_engine`, `engine_to_resolved`, `resolved_to_decided` and `rx_to_decided` remain for decoded hints only.

# arbx measurement specification

**Date:** 2026-10-04. **Status:** specification, revision 2.4. It describes what WP-00 to WP-08 and WP-11 to WP-15 of `docs/PLAN.md` must produce, and how the toolkit (WP-10) must read it. Revision 2 applies `docs/reviews/plan-review.md`; the dispositions are in `docs/reviews/plan-changes.md`. Revision 2.1 records what WP-01 implemented: `campaign.json`, `meta.json` v2, `stop.json`, `control.jsonl` and `supervisor.jsonl` (§4.1-§4.3, §4.7; the fields WP-01 added beyond revision 2 are marked **(WP-01)**), the SendGate reasons `program_hash_mismatch` and `mode_shadow` (A.5), and the final status line's `stop_reason` in the v1.1 files (§7), with the fixes of its review (`docs/reviews/WP-01-review.md`, Disposition). Revision 2.2 records what WP-02 implemented: the recorder (`src/rec/`), its files, headers and schema versions, queues, drops, disk ladder and manifest (§1.6), `status.jsonl` v2, `feedhealth.jsonl`, `resources.jsonl` and `events.jsonl` as written (§4.4-§4.10, "As WP-02 writes it"), and the v1.1 streams behind headers (§7), with the fixes of its review (`docs/reviews/WP-02-review.md`, Disposition): write errors and dead or stalled writers are losses, the disk ladder's soft and hard stages, the echo thread, a bounded close. Revision 2.3 records what WP-03 implemented: `accounts.bin` and `journal.bin` records (§4.12, §4.13), `exec.jsonl` v2 from the transaction stream (§4.14), `blocks.jsonl`, `slots.jsonl`, `leaders.jsonl` and `probe.json` (§4.16, §4.17, §4.27, §4.49), the feeds' `provider_lag_ms` (§4.9), moves.log's `write_version` (§4.22), and the journal INPUT kind 9 `settled`; each is marked "As WP-03 writes it". With the fixes of its review (`docs/reviews/WP-03-review.md`, Disposition): journal 2.1 (engine_init, decision-point gate records, TIMER scope, timer anchors from journaled time; §4.13), probe verdicts with `inconclusive` (§4.49), `slot_statuses = "auto"` (§4.17), exec.jsonl one line per (signature, slot) (§4.14), `bank_id` in slots / blocks / exec, and the state stream's gauges (§4.8, §4.9). Revision 2.4 records what WP-08 (part 1: leaders, PoH, transfer classification; the program-log decoders follow WP-05) implemented: exec.jsonl 2.1's derived fields (§4.14), leaders.jsonl 1.1 and validators.jsonl (§4.27, §4.28), poh.log's entry index for entries feeds and slots-feed.log from shred feeds (§4.23, §4.24), the `poh_trigger_pct` gauge and the LeaderBook snapshot that attempts carry (§4.8, §4.37), and rivals.jsonl 1.2 (the full tip map and the sampled `why = venues` rows of plan addendum I-9, §4.21, §5); each is marked "As WP-08 writes it". With the fixes of its review (`docs/reviews/WP-08-review.md`, Disposition): the RTT kept per TPU-QUIC endpoint with the endpoint's own region and the region bucket by endpoint region, metro regions with the city as its own field, `unknown` kinds with a reason, validators.jsonl every 10 minutes, refreshes retried after 30 s, failed transactions paying no tip and in no bundle (`tip_asked`), scrubbed errors.
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

Checked every 10 s by `src/rec/disk.rs`. Inputs: the segment directory's size, the filesystem's free space. Config: `disk_budget_gb` (per segment, 40), `min_free_gb` (25). The bot never deletes what it wrote, so a crossed limit stays crossed; the budget therefore acts in two stages (WP-02 review F5). Past a **soft** limit (the directory over 90% of the budget, or free space under `min_free_gb` / 0.9), steps 1-3 run in order, one per check, each written to `events.jsonl` (`disk_action`) and the manifest; past a **hard** limit (the budget, or `min_free_gb`), step 4 runs at once:
1. stop the `entries-<feed>` archives;
2. stop `rivals` and `validators` detail;
3. lengthen the `accounts` keyframe interval 4× (a format change: no record is dropped);
4. SendGate → shadow and stop the segment (`stop.json` reason `disk_budget`).
A segment that stays between the soft and hard limits runs on. Core, replay and chain streams are never dropped by the budget. The supervisor refuses to start a segment below `min_free_gb`, and so does `arbx run` itself. Volume estimates are in §5.

### 1.5 Drop accounting

Every stream has `records_total`, `dropped_total` and a queue high-water mark, in `manifest.json` and in `status.jsonl` (`recorder`).
- A core drop is a segment-level fault (principle 3).
- A replay drop is a replay fault (principle 3).
- Reports print coverage for every stream they use (R0, §6.3).

### 1.6 As WP-02 writes them

**The recorder** (`src/rec/`) starts with every `arbx run`, before anything records (it refuses to start under `min_free_gb`), and is closed (queues drained, frames ended, files closed, final manifest written) on every way out of the run: before stop.json and its run.log line on an error or a stop; after them on a main-thread panic (the panic hook writes stop.json at once, then the unwinding closes the recorder). The close waits at most 20 s for the writers; a writer still busy then (a hung disk) is left behind and named in manifest.json `close_timeout`. There is no switch: `[record] enabled`, `[record] archive_feed` and `arbx run --no-record` are gone (a config with the keys does not load; clap refuses the flag). `arbx simcheck` and `arbx senders --raw` record their own directory the same way (no monitor thread; closed on an error too). `arbx run` refuses a segment directory that already holds files (an earlier run's would be overwritten).

**Producers and threads.** `Rec::emit(stream, record)` checks the queue depth (and, for a record with a declared payload size, the queue's byte cap) and sends on the class's channel; a full queue drops and counts, nothing blocks (the offline timing test measured emit p50 461 ns, p99 631 ns at 100k records/s). A record is either a closure that encodes it on the class's writer thread (moves, txarr, poh, slots-feed, entries, bundles, copies, alts-final: their base58, number formatting and serialization happen there; `Record::enc_lines` holds several lines in one queue slot and counts them as lines), or a `serde_json::Value` that is only serialized there: its tree, and any base58 string in it, is built by the producer (triggers, opportunities, predictions, arrivals, caps, rivals, exec, attempts, outcomes, sims, keepalive, status; review F10: their conversion to typed records encoded on the writer is a follow-up). Five writer threads (`arbx-rec-core`, `-replay`, `-chain`, `-bulk`, `-slow`), niced +5 and pinned to `[record] writer_cpus` when set, an echo thread (`arbx-rec-echo`) and a monitor thread (`arbx-rec-mon`: the writers' health every second, the disk check, resources.jsonl every 10 s, manifest.json every 60 s and at close). run.log lines and the diagnostic lines arb-lab printed to stderr are written by the slow writer and echoed to stdout / stderr (the segment's `.out`) by the echo thread, through a bounded queue (4,096 lines; past it a line is counted, `echo_dropped`, not waited for), with write errors ignored: a failing or blocked stdout stops nothing. signer-stats.json is written by the slow writer (atomically). The engine thread itself writes nothing.

**Queues** (records): `queue_core` 262,144 (core class), `queue_accounts` 1,048,576 and `queue_journal` 524,288 (the replay streams, each its own), `queue_chain` 262,144 (chain class), `queue_bulk` 131,072 (bulk class); the slow class is unbounded. Each bounded queue also has a byte cap, `queue_max_mb` (1,024 MiB; review F17): the payload bytes producers declare (binary records, ready lines, `Rec::emit_sized` closures such as the entries archive) are counted, and a record past the cap drops as from a full queue (a replay drop then writes its GAP). A class's streams share its queue; `manifest.json` and `resources.jsonl` report the queues by these names.

**Streams and files as written** (header schema; `<s>.NNN.<ext>.zst` unless marked):

| Class | Stream: schema |
|---|---|
| core | attempts, copies, bundles, outcomes: `arbx.<s>/1.1` (ledger, wallet, decisions, commits come with WP-03b/WP-04/WP-05/WP-07). `control.jsonl` and `stop.json` stay plain and are written by `src/control.rs` directly (WP-01), not through the queue |
| replay | accounts `arbx.accounts/2.0` (ARBXACC, format 2), journal `arbx.journal/2.1` (ARBXJRN, format 2): queues and GAP records are WP-02's; their records are WP-03's (§4.12, §4.13) |
| chain | exec `arbx.exec/2.1` (WP-03, §4.14; 2.1: WP-08's derived fields); slots `arbx.slots/1.0`, blocks `arbx.blocks/1.0` (WP-03), leaders `arbx.leaders/1.1` (WP-03; 1.1: WP-08's region, RTT, client and kind updates); triggers, predictions, caps, sims, arrivals, opportunities: `arbx.<s>/1.1`; txarr `# arbx.txarr/1.1 ... feeds=<names>`; moves, poh, slots-feed `/2.0` (text); alts-final `arbx.alts-final/1.1` (one file, `alts-final.jsonl.zst`, the end-of-run dump). `opportunities` was in no class list: it is chain |
| bulk | rivals `arbx.rivals/1.2` (1.2: WP-08's sampled `venues` rows and full tip names, §4.21); validators `arbx.validators/1.0` (WP-08, §4.28); `entries-<feed>` `arbx.entries/1.0` (ARBXENT, format 1; header `feed`, `feed_id`) for each `[record] archive_feeds` feed that runs |
| slow (plain) | status.jsonl `arbx.status/2.0`, events.jsonl `arbx.events/1.0`, feedhealth.jsonl `arbx.feedhealth/1.0`, resources.jsonl `arbx.resources/1.0`, keepalive.jsonl `arbx.keepalive/1.1`; run.log (no header, `<t_ns> <message>`); manifest.json `arbx.manifest/1.0` (atomic rewrite) |

`1.1` is arb-lab's v1 record with the WP-00/WP-01 fields (§7), unchanged except for the header; its v2 shape comes with the WP that has the data (attempts and outcomes WP-05/WP-07, exec WP-03, ...). Readers must route a `/1.x` header to the legacy mapping: the toolkit (`tools/arbx-report`, since WP-02's review F3) accepts major 1 for attempts, bundles, outcomes, exec, triggers and predictions and maps those files through `legacy.py` per stream (`Segment.v1`), outcomes' renamed `failed_fees_total_lamports` included. moves, poh and slots-feed are at 2.0 because their v2 only appends columns: a column WP-02 cannot fill is `-` (moves `write_version` until WP-03; poh `entry_idx` for entries feeds until WP-08, and still for a slot an entries feed joined midway; slots-feed's shred columns for entries feeds).

**Headers** (§1.3). JSON lines: `{"schema","run","file_seq","started_ns","producer"}` (+ stream extras), the first line of each file; text: `# <schema> run=<segment> file_seq=<n> started_ns=<t_ns> producer=<sha8> [feeds=<a,b>]` (whitespace in values becomes `_`); binary: `magic | u16 format | u16 hlen | JSON header` with the same fields. `producer` is the first 16 hex characters (8 bytes) of the running binary's sha256 (meta.json `build.binary_sha256`). Plain JSON-lines files get the header when they are created (appending to an existing one adds none).

**Files and frames.** The plain streams (events, feedhealth, resources, keepalive, run.log) are created with their headers when the recorder starts (stamped with its start); status.jsonl right before the engine starts (`Rec::open_now`: the supervisor reads its existence as "the engine started", and a run that cannot create it does not start); a compressed stream's file with its first record. A frame ends every `flush_ms` (1,000) and whenever 4 MiB of raw data is pending, and on the core writer whenever its queue is empty (an attempt, copy, bundle or outcome is on disk within milliseconds, so a hard kill loses none that was taken; review F4); each frame is one complete zstd frame with its content size, so a reader decodes every complete frame of a file being written and leaves out a torn tail. A file rotates when its raw size passes `rotate_mb` (MiB, fractions allowed) or it is `rotate_min` old and has records; alts-final never rotates. Every file restarts its header (and, for WP-03's binary streams, its dictionaries and keyframes).

**Drops** (§1.5). `dropped` (the queue was full, its byte cap reached, or its writer gone), `suppressed` (the disk ladder switched the stream off) and `late` (emitted after the recorder closed, or still queued when its writer finished closing) are counted per stream. The first drop of a stream, then at most one a second, is an `events.jsonl` `recorder_drop` with `{stream, class, dropped_total, queue, queue_cap, seq}`. A core drop also closes the SendGate for the rest of the segment (`core_record_loss`, sticky; a `gate_change` event; `status.health.recorder_ok` false). A replay drop records the lost sequence numbers; the stream's next record is preceded by a GAP record per contiguous lost range (accounts kind 6: `u8 6 | u32 16 | u64 first_lost_aseq | u64 n_lost`; journal kind 12: `u8 12 | u32 16 | u64 seq | u64 t_engine_ns | u64 first_lost_seq | u64 n_lost`, `seq` = the first lost one, `body_len` counting the body only). Sequence numbers come from `Rec::next_seq` before the record is made (the producer carries them: WP-03's `aseq`). With concurrent producers a GAP can follow a record whose sequence number is above the lost one.

**Faults** (review F1, F2). A record counts as written (`records_total`) only once its bytes are on disk. A record the writer took but could not write is lost: an open, compression or write error is counted per stream (`io_errors`, and the records it lost, `io_lost`), a record whose encoder panicked is counted as `encode_errors` (the writer goes on; every encoding runs under `catch_unwind`). A frame cut short by a failed write is cut off the file again, so the frames after it stay readable; a file that could not be opened is tried again at most once a second, its header first. On a core stream any such loss is a core loss, as a drop: SendGate shadow `core_record_loss`. A status.jsonl line that cannot be written or is dropped (the supervisor's budget source), a core or slow writer thread that dies, or one with records queued and no progress for 60 s (the monitor checks every second) stops the segment: stop.json reason `error` with detail `recorder: ...` (exit 30), a run.log line written directly, `events.jsonl` `recorder_fatal`; a chain, replay or bulk writer that dies or stalls is an event (`recorder_writer_dead`, `recorder_writer_stalled`) and its records are dropped from then on. Each I/O or encoding fault is also an event (`recorder_io_error` {stream, class, op, error, io_errors_total, lost_total}, `recorder_encode_error`; the first, then at most one a second per stream) and a stderr line. **Per-file state** (WP-03): a stream's encoder state (`rec::FileState`, installed with `Rec::set_file_state`) is owned by its writer; `on_new_file(file_seq)` runs right after each file's header, so dictionaries and keyframes restart per file, and `Record::stateful` records are encoded against it.

**Disk budget** (§1.4), by the monitor every 10 s: while the segment directory (recursively) exceeds 90% of `disk_budget_gb` or the filesystem's available space is under `min_free_gb` / 0.9 (the soft limits), one action per check, in order: `stop_entries_archive`, `stop_rivals` (rivals and, once WP-08 writes it, validators), `accounts_keyframe_x4` (`Rec::accounts_keyframe_every()` × 4, read by WP-03's encoder); past `disk_budget_gb` or under `min_free_gb` (the hard limits), at once, `shadow_and_stop` (SendGate shadow `disk_budget`, then a stop request: stop.json `disk_budget`, exit 20). Each is an `events.jsonl` `disk_action` `{action, used_bytes, fs_free_bytes, budget_bytes, min_free_bytes, streams_off, detail}` and an entry of manifest.json `disk.actions`. The actions hold for the rest of the segment.

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
| segments | [{name, started_ns, ended_ns, exit_code, stop_reason, class (`natural`, `operator`, `safety`, `crash`)}] | one per segment. `class` comes from the segment's stop.json: `deadline` = natural; `signal`, `control` = operator; exit 20, `equity_day`, `disk_budget` = safety; anything else (`error`, `panic`, no stop.json: `stop_reason` null, an exit code outside 0/10/20/30) = crash |
| crash_count_15min | integer | crashes only (operator stops excluded), in the 15 minutes before the last segment ended; more than 6 ends the campaign |
| end_reason **(WP-01)** | str / null | why the campaign ended: `time up`, `max segments (n)`, `stop file: <text>`, `safety stop in <segment> (<reason>)`, `crash limit: …`, `disk low …`; null while it runs |

`config.normalized_sha256` is `arbx provenance --offline`'s, the same as every segment's meta.json `config.normalized_sha256` (both hash the config file as loaded, before any command-line override: WP-01 review F2). `budget.equity_drop_day_sol` is null until WP-07. The supervisor also writes `check.out` and `provenance.json` (the frozen binary's `arbx check` and `arbx provenance --offline` of the frozen config) into the campaign directory, and the segments keep `programs.cache.json` there (the venue programs' hashes, §4.2).

### 4.2 meta.json (v2)

Producer: `src/provenance.rs`, called from `main.rs::run` before the transaction feeds start. Written once, then rewritten once when the venue programs' hashes are in (WP-01; see below).

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
| probe | {file_sha256, t_ns, provider_host, age_s, accepted: [str], refused: [{sub, error}], inconclusive: [{sub, error, code, messages_30s}]} / null | from `probe.json` (§4.49); `accepted` lists only subscriptions that delivered messages (review WP-03 #4) |
| chainfetch | object | the effective `[chainfetch]` config |
| pools | {summary, n_pools, n_pairs, by_venue, seed_csv_sha256, registry_sha256, file: "pools.json"} | |
| streams | {name: schema} | every stream this binary writes |
| experiments | object | the `[experiments]` config, or null |
| limits | {max_size_sol, max_size_src (`owner OD-4` or `config`), supervisor: {...}, ledger: {...}} | effective safety limits; `max_size_sol` is the owner's Stage-0 decision (F37) |
| campaign_dir | str / null | `--campaign-dir`, used for campaign-wide stops |
| clock | {source: "CLOCK_REALTIME", sync_offset_ms, sync_source} | from adjtimex / chronyc |
| strategy, send, builder, tips, state | object | effective config sections (normalized) |
| (v1) started_ns, feeds, strategy, pools, wallet, send_paths, gate, sim, canary, live, exec | — | v1 had only these, as Debug strings |

**As WP-01 writes it.** Written by `main.rs::run` (helpers in `src/provenance.rs`) after the pools, the route program, the send paths and the executor are up and before the transaction feeds start; atomically (temporary file + rename). The state stream (pool accounts) starts earlier, right after the account snapshot, so that no pool write between the snapshot and its subscription is missed (WP-01 review F1); `state.snapshot_slot`, `state.snapshot_ns` and `state.stream_started_ns` record the gap, and run.log has the slot of the stream's first update after each (re)connect. meta.json is rewritten once, atomically, when the venue programs are hashed in the background (`programs_pending` false, `programs_done_ns`); a segment that stops first keeps `programs_pending: true`. A run that ends before that (a failed boot, a stop during boot) leaves a partial one, written with stop.json: `{schema, partial: true, run, build, config, campaign_dir, overrides}`. Fields that a later WP fills are present and null (`probe`, `chainfetch`, `experiments`, `tips`, `limits.ledger`, `pools.file`, `rpc[].max_rps`, `state.tx_streams[].max_accounts`) or false (`state.watch_*`, `state.block_meta`). Beyond the table above:
- `run.env_file` **(WP-01)**: the `--env-file` the run loaded (a path; the supervisor names the `.env` of the config it froze), or null for the `.env` beside the config.
- `build.binary_path` **(WP-01)**: `/proc/self/exe`'s target. `build.git_dirty` is null and `git_commit` `unknown` for a build outside git; `dirty_sha256` is null when clean. Dirty means the files that make up the binary (`src/`, `Cargo.toml`, `Cargo.lock`, `buildinfo.rs`) differ from HEAD, or there are untracked files under `src/`; `dirty_sha256` hashes `git diff HEAD --binary` over them plus each untracked file's path and bytes.
- `config` **(WP-01)**: `normalized_sha256` (and `file_sha256`) hash the config file as loaded, before the command line: the same in every segment of a campaign whatever `--budget-left`, `--no-record` or `--shadow` say, and equal to campaign.json's and `arbx provenance`'s (review F2); what the command line changed is in `overrides` and `limits.supervisor`. `config.mode` is the file's `mode`; `config.effective_mode` is the mode after the command line (`--shadow`).
- `programs[]`: one entry for the route program (`role` `route`, `[exec] program`) and one per venue program (PumpSwap, RayCpmm, RayAmmV4, Dlmm, DammV2). **(WP-01)** extra fields: `upgrade_authority` (pk / null), `trailing_nonzero` (non-zero bytes after the ELF's end: 0 when the procedure is right), `expected_md5`, `error` (why it could not be hashed; then `ok` is false if a hash was expected), `source` (`rpc`: fetched whole this segment; `cache`: the campaign's `programs.cache.json`) and `pending` (true until the background fetch ends). The route program is fetched at boot, before anything can send. The venue programs are fetched in the background once the feeds run, and once per campaign: later segments read each programdata header (45 bytes, `dataSlice`) and reuse the cached hashes while the last deploy slot is unchanged (an upgrade always changes it), with the upgrade authority taken from the fresh header (review F1, M8). Outside a campaign every program is fetched whole. `ok` is null when no hash is expected (venue programs; a route program without `[exec] expected_program_*`). The procedure also takes a BPF loader 2 program (no programdata: the ELF is the program account's data; `programdata`, `last_deploy_slot` and `upgrade_authority` are null). When the route program's `ok` is false, a live or canary run does not send: the SendGate is shadow for the whole segment with reason `program_hash_mismatch` (A.5); a shadow run only records it. A program whose upgrade authority is the trading wallet is a run.log warning (invariant 9).
- `wallet.keystore_path`: `wallet_keystore`, or the profile's `~/.nexus-v2-<profile>-wallet.enc`. `held_mints_at_boot` is null when no executor runs (shadow without simulation).
- `feeds[].host`: the URL's host, the UDP bind address, or `group:port@interface` for multicast; `id` is null for a disabled feed.
- `send_paths[]`: the enabled paths; `id` is null for one that could not be built.
- `rpc[]` **(WP-01)**: also `enabled` and `available` (its environment is complete); roles are `boot` (every enabled provider) and `exec` (the `[exec] rpc` ones) until WP-03b.
- **As WP-03 writes it:** `state.watch_clock`, `watch_programdata`, `watch_wallet` are the config's, `state.block_meta` whether the stream subscribed to it, plus `state.slot_statuses` and `state.extra_watched` (how many extra accounts it follows); `state.tx_streams[]` has `url_host`, `max_accounts` and `failed`, its `account_include` expanded. `probe` is `{file_sha256, t_ns, provider_host, accepted, refused}` from the probe file the run read (`deshred_5` entries named `deshred_5@<feed>`), else null; `leaders` is the `[leaders]` section.
- `state.config` **(WP-01)**: the `[state]` section; `state.snapshot_slot` (the slot of the boot's account snapshot), `snapshot_ns`, `stream_started_ns` (when the state stream was started) and `followed` (accounts it follows).
- `inputs` **(WP-01)**: `{crowded_pools_file, templates_json, signer_stats_file: {path, sha256, size} | {path, sha256: null, error}}`, the set ones only (review N8: files the config names but its hash does not cover).
- `run.env_file_loaded` **(WP-01)**: false when the `--env-file` could not be read (also a run.log warning); null without `--env-file`.
- `limits`: the v1.1 fields (§7) plus `supervisor: {budget_left_lamports, config_max_failed_fees_lamports, effective_max_failed_fees_lamports}` and `ledger: null`.
- `clock` **(WP-01)**: also `adjtimex: {state, offset_ns, maxerror_us, esterror_us, unsynced}` and `chrony` (`chronyc -c tracking`: `ref_id, ref_name, stratum, system_time_s, last_offset_s, rms_offset_s, frequency_ppm, skew_ppm, root_delay_s, root_dispersion_s, leap`, or null). `sync_source` is `chronyc`, `adjtimex` or `none`.
- `streams`: `meta`, `stop`, `control` and `config` with their schemas; the arb-lab files as `v1.1`.
- `strategy`, `send`, `builder` (`[exec]`), `live`, `sim`, `canary`, `gate`, `record`, `control` **(WP-01)**: effective config sections, normalized (keys sorted, every URL cut to `scheme://host`). `arbx provenance` prints the same sections.
- `send_gate` **(WP-01)**: the SendGate at the time meta.json was written (`{mode, reason, detail, since_ns, sticky}`).
- `overrides` (v1.1, kept): what the command line changed: `{mode: "shadow"}` (`--shadow`), `{"record.enabled": false}` (`--no-record`), `{budget_left_lamports}` (`--budget-left`).

**WP-02.** `streams` lists `meta`, `stop`, `control`, `config`, `manifest` and every recorder stream with its header schema (§1.6). `record` (the normalized `[record]`) has the WP-02 keys; `runtime` is the normalized `[runtime]`; `limits.record` is always true; `overrides` no longer has `record.enabled` (`--no-record` is gone).

`arbx provenance --config <file> [--offline]` prints `{schema: "arbx.provenance/1.0", t_ns, host, build, config, programs (null with --offline), clock, feeds, send_paths (ids null: nothing is built), rpc, state: {url_host}, inputs, strategy, send, builder, live, sim, canary, gate, record, control}` without starting anything (no pools, feeds or send paths).

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
| final_status_seq | integer | the last `status.jsonl` seq. **(WP-01)** Until status v2 (WP-02) gives lines a `seq`, it is the 0-based index of the final line; null when the run stopped before its engine ran |
| secondary **(WP-01)** | {reason (`error`, `panic`), detail} / null | a failure after the stop reason was set (a crash while stopping). The first reason stays `reason`; the exit code is then 30 and the supervisor classes the segment a crash (review M5) |
| requested_ns **(WP-01)** | t_ns | when the stop reason was set (the first request wins; later ones are only logged) |

**As WP-01 writes it.** `stop.json` is written once, atomically, by `control::Session::finish` (from `main.rs` at exit, or the panic hook for a panic on the main thread), with a `<t_ns> stop: reason <r> (exit <code>): <detail>` line in run.log and the control socket removed. Every run that got as far as creating its directory has one, including a failed boot (`error`). `signal` also carries `name` (`SIGINT`, `SIGTERM`) and `sender_comm` (`/proc/<pid>/comm`); `sender_cmdline` is cut to 512 characters with URLs reduced to their host. `detail` is human text: `--minutes N reached`, `SIGINT from pid N (comm)`, `stop by <who>: <why>`, or the error with URLs scrubbed. Until WP-05 drains attempts at stop, `drain_ms` is null, `in_flight_at_stop` and `unsettled` are the attempts still open when the engine loop ended, and `drained` says whether there were none; with no executor (shadow without simulation, a failed boot) `in_flight_at_stop` and `drained` are null (review M11). `exit_code` is 30 whenever `secondary` is set. A signal with no sender process (the kernel, a terminal's Ctrl-C) reads `SIGINT with no sender process (kernel or terminal)` in `detail`. Only SIGINT and SIGTERM are handled (SIGHUP stays ignored under the supervisor). The exit code follows the reason: `deadline` 0; `signal`, `control` 10; `equity_day`, `disk_budget` 20; `error`, `panic` 30.

### 4.4 manifest.json

Producer: `src/rec/manifest.rs`, every 60 s and at close (atomic rename).

| Field | Type | Semantics |
|---|---|---|
| schema | str | `arbx.manifest/1.0` |
| t_ns | t_ns | when written |
| final | bool | written at close |
| streams | [{name, schema, class, files: [{path, bytes_raw, bytes_written, records, first_t_ns, last_t_ns, closed, sha256}], records_total, dropped_total, queue_cap, queue_hwm}] | `sha256` only for closed files |
| disk | {budget_bytes, used_bytes, fs_free_bytes, actions: [{t_ns, action}]} | §1.4 |

**As WP-02 writes it** (`src/rec/manifest.rs`; the monitor every 60 s and once at start, and at close with `final: true`). Also `run`, `producer`, `started_ns`, `core_record_loss` (bool), `disk.min_free_bytes`; per stream also `suppressed_total`, `late_total`, `on` (false once the disk ladder switched it off) and `queue` (the queue's name: `core`, `accounts`, `journal`, `chain`, `bulk`, `slow`), with `queue_cap` and `queue_hwm` of that queue (`queue_cap` null for the slow queue). `records_total` counts the records whose bytes reached the disk (headers and GAP marks are not records; GAP marks are counted in their file's `records`); per stream also `io_errors_total`, `io_lost_total` and `encode_errors_total` (§1.6 Faults). Also `queues` {queue: {cap, bytes_cap, hwm, bytes_hwm, lost_at_close (records still counted in the queue once its writer finished: accepted, never written)}} (caps null for the slow queue), `writers_dead` (classes whose writer thread died), `close_timeout` (classes whose writer had not finished when the close stopped waiting), `fatal` (why the recorder stopped the segment, or null), `echo_dropped`, and `disk.soft_budget_bytes`, `disk.soft_min_free_bytes`. `used_bytes` and `fs_free_bytes` are the last disk check's (null before the first). Plain files (status.jsonl, run.log, ...) stay open to appends by other writers (control.rs, the panic hook), so their `sha256` is null; every compressed file is closed at the end with its sha256.

**As WP-08 writes it.** Also `sampling` {`rivals_venues`: {one_in, kept, seen}}: rivals.jsonl's sampled `why = venues` rows (plan addendum I-9, §4.21): the rate, the rows written and the rows seen (written or left out). Rows left out are not drops: `dropped_total` counts losses only.

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

**As WP-02 writes it.** Plain JSON lines through the slow writer. Kinds written so far: `log` (`detail.msg`: the sim gate's re-check and stale-sim lines and the token cool-down line of exec.rs, `subsystem` `send`), `recorder_drop` (with `why`: `queue full`, `queue byte cap`, `writer gone`) and `disk_action` (§1.6), `recorder_io_error`, `recorder_encode_error`, `recorder_writer_dead`, `recorder_writer_stalled`, `recorder_fatal` (§1.6 Faults), `gate_change` (`{to, reason, detail}` from the recorder: `core_record_loss`, `disk_budget`). `feed` is null unless the event is a feed's.

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
| note **(WP-01)** | str | a command accepted without changing anything says why (`already shadow for the rest of the segment (<reason>): nothing to change`) |

`supervisor.jsonl` (run-w.sh): `{t_ns, event (start, segment_start, segment_end, pause, resume, stop, disk_low, budget; WP-01: gate, pause_failed, resume_failed, kill), segment, budget_left_lamports, budget_src ("ledger", "status" or "unknown"), free_gb, detail}`.

**As WP-01 writes them.**
- The segment's `control.jsonl` gets one line per socket command (`src` `socket`, accepted or not: `--who` is required, and `--why` for every command but `status`), and one per SIGINT or SIGTERM (`src` `signal`, `who` = `<comm> (pid <n>)`, `cmd` `stop`, `why` = the stop detail; a second signal has `accepted` false, `result` `already stopping`). `result` is the SendGate mode after the command, `stopping`, or why it was refused.
- Commands: `status` (also returns `send_gate`, `stopping`, `stop_reason`, `pid`, `dir` and the last status line), `pause-sending` (SendGate shadow, reason `control`, until `resume-sending`), `resume-sending` (refused after `shadow`, `--shadow`, `program_hash_mismatch` or a stop), `shadow` (shadow for the rest of the segment), `stop` (stop reason `control` with `{who, why, cmd}`). `pause-sending` and `shadow` on a gate that is already shadow for the rest of the segment (`mode_shadow`, `forced_shadow`, `program_hash_mismatch`, an earlier `shadow`) are accepted, change nothing and carry a `note` (review F3: the run is not sending, which is what was asked). Every reply also has `note` (null otherwise). A connection from another user than the run's (or root) is refused and logged with `who` `uid <n>`, `cmd` `?` (review N5).
- The campaign's `control.jsonl` (`src` `file`) records the control files: `pause-sending` / `resume-sending` for `<campaign>.pause` appearing and going, `next` (`<campaign>.next`; `accepted` false when no segment was running), `stop` (`<campaign>.stop`). `who` is the file's owner (`?` for a removal), `why` its first line. A `pause-sending` line names what happened: the segment paused (`segment <s> paused`), was already shadow (`segment <s> already shadow (<reason>)`), did not confirm (`accepted` false, `result` the reply or `ctl failed (exit n): …`), or, between segments, `segments record only (--shadow) while the file exists`. A `resume-sending` line likewise (`segment <s> resumed`, `… stays shadow (<reason>)`, `accepted` false and `…; restarted` when the segment refused, `segment <s> (records only) restarted: the next one sends`). When the pause is not confirmed after `ARBX_PAUSE_TRIES` (3) polls of a `--live` segment, the supervisor stops it and logs a `next` line with `who` `supervisor`.
- `supervisor.jsonl`: `budget_src` is `status` (each segment's last status line, never a sum of lines) or `unknown` until WP-07 brings `ledger`. Unknown means a segment that may have sent (it left attempts, or ran with `--live` and its engine started, i.e. has `status.jsonl`) has no readable numeric failed-fee total in its last line, or reading failed: the rest of the campaign is records only (review M4). `budget` events name a records-only segment. `detail` is text: `minutes=… flag=…[ paused=true]` at segment start, `exit=… reason=… class=… duration_s=… crashes_15min=…` at segment end, the end reason at `stop`, `mode=… reason=… flag=…` at `gate` (the segment's meta.json `send_gate`, once known; a `--live` segment whose gate is not live is also a WARNING line in supervisor.log), the ctl reply at `pause_failed` / `resume_failed`, and `SIGKILL …` at `kill`.

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
| coverage | {watched_with_tx_pct, watched_with_idx_pct, denominator_delta, wallet_with_tx_pct, wallet_update_missing_delta, slotidx_pct, unseen_share_sample, poh_trigger_pct, leader_known_pct} | interval window. `watched_with_tx_pct`: the share of the known denominator (§4.14) that has an `exec` record within 60 s. `unseen_share_sample`: from the last full-block sample. `poh_trigger_pct` (WP-08, F38): `feeds::POH_GAUGE.status(feeds, t)` gives `{poh_trigger_pct, attempts_delta, with_poh_delta, attempts_total, with_poh_total, poh_feeds_alive_now, target_pct: 90, target_met}` over the attempts noted since the last line (`PohGauge::note_attempt(has_poh)`: the trigger's position in the engine's map or the PoH index); `target_met` is null while no entries or shred feed is alive (connected, a message in the last 10 s). The attempt writer's call (WP-05) and this section (written by the engine with WP-03b's coverage fields) come with those WPs |
| recorder | {dropped_total: {stream: n}, dropped_delta: {stream: n}, queue_hwm: {stream: n}} | |
| stop_reason | enum / null | only on the final line |

v1 fields (`t_ns, slot, queue, store_updates, open_opps, alts_cached, alt_waiting, ata_misses, counts, latency, exec.sending{sent, landed, wins, in_flight, failed_fees_lamports, cap_lamports, fees_lamports, tips_lamports, profit_lamports, new_token_accounts, stopped}`) are read by the legacy reader only. In v1, `counts` and `failed_fees_lamports` are totals; `profit_lamports` includes rent.

**As WP-02 writes it** (`engine.rs::write_status_line`, `exec.rs::status_v2`; header `arbx.status/2.0`). Present: `seq` (from 0; stop.json `final_status_seq` is the last one), `t_ns`, `interval_ns`, `run_s` (since the engine started), `slot` {processed (the newest slot of any status, as arb-lab's `slot`), confirmed, finalized; null until seen}, `tip_lag_slots_now` (that slot minus the newest slot of a stored pool-account update: from WP-03 on, the Clock, wallet and programdata accounts on the stream do not count, review WP-03 #6), `send_gate`, `health` {`recorder_ok` (no core record lost, the recorder did not stop the segment); `warmup_ready`, `lag_slo_ok`, `leaders_ok`, `blockhash_age_slots_now`, `blockhash_src_now`, `jito_token_age_s_now` null until their WPs}, `queue` {engine_now, engine_hwm_delta (the engine channel's high-water mark since the last line)}, `store` {accounts_now, updates_total, updates_delta, stale_total, stale_delta, pending_groups_now (state triggers waiting for their transaction's other updates)}, `alts` {cached_now, waiting_txs_now, fetching_now, missing_now, learned_delta}, `opps_open_now`, `ata_misses_total`, `counts_total` / `counts_delta` (the engine's counters; a delta lists only what changed), `latency` {series: pct(interval)} and `latency_run` {series: pct(run)} (µs; the WP-00 series of A.8 plus the executor's; `latency_run` is WP-00's whole-run reservoir, for comparisons with WP-00 baselines), `exec`, `money`, `recorder` {dropped_total, dropped_delta, suppressed_total, io_errors_total, io_lost_total, encode_errors_total (non-zero streams only), writers_dead_now, echo_dropped_total, queue_hwm {queue: n}}, and `stop_reason` on the final line. `exec`: {counts_total, counts_delta (the executor's counters, e.g. `reject_gate_shadow`), verdicts_delta {outcome: n} (block-engine results of the jito paths), over_rate_total {crowded, other}, decisions_total, refused_total, queue_now, lambda_now (null until WP-05)} and, with a sender, {kind, stopped, attempts_total/_delta, landed_total/_delta, ok_total, in_flight_now}; null without an executor. `money` (the bot's counters until WP-07's ledger, `src: "bot"`; null without a sender): {failed_fees_total_lamports, failed_fees_delta_lamports, failed_fees_cap_now_lamports, fees_landed_total_lamports, tips_paid_total_lamports, bot_profit_total_lamports (v1 `profit_lamports`: rent included), new_token_accounts_total}. The supervisor reads `money.failed_fees_total_lamports` of the last line (deploy/run-w.sh). Absent until their WPs: `commit`, `forks`, `lag_slo`, `accuracy`, `chainfetch`, `coverage`.

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

**As WP-02 writes it.** Written by the engine's housekeeping every 10 s (the line builder is `src/rec/health.rs`), the state stream first (`feed` null, `name` `state`, `kind` `state-stream`), then each enabled feed by id (`kind` as in the config: `udp`, `multicast`, `jito-entries`, `yellowstone-tx`, ...). `seq` counts lines (one per feed per tick). `first_arrivals_delta` and `lead_ms` (ms, pct(interval)) are counted when a signature leaves its 10 s window (txarr), so they lag the line by up to 10 s. `connected_now` is true from a feed's first message after a (re)connect until the stream ends; raw feeds are connected while their receive thread runs. `slot_max_now` is the newest slot of the feed's messages (shreds' headers for raw feeds; for the state stream, from WP-03 on, account updates and processed / confirmed / finalized slot statuses only: interslot statuses run ahead, review WP-03 #6), `slot_lag_now` the engine's newest processed slot minus it. `shreds` (raw feeds): the assembler's totals copied every 2 s (`bad_delta` counts bad packets, implausible slots and other shred versions). `udp_drops_delta` (raw feeds; null otherwise): the kernel's drops of the feed's socket from `/proc/net/udp` (read every 10 s by the monitor). `provider_lag_ms` is null (WP-03 parses `created_at`). **As WP-03 writes it:** `provider_lag_ms` (pct(interval), ms) is the receive time minus the message's `created_at` for the state stream, the transaction streams and the deshred feeds when their provider stamps messages (null for a feed whose provider never did); a provider clock ahead of ours counts as 0.

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

**As WP-02 writes it** (the monitor thread, every 10 s). `recorder_queues` is by queue (`core`, `accounts`, `journal`, `chain`, `bulk`, `slow`), `hwm_delta` the high-water mark since the last line, `bytes_now` and `bytes_hwm` the declared payload bytes queued (the byte cap's count); `recorder_bytes_delta` lists the streams that wrote compressed bytes since the last line. `udp_drops_delta`: the kernel's receive drops of every UDP socket of the process (`/proc/net/udp`, `udp6`). `engine_cpu_ms_delta` reads the engine thread's `/proc/self/task/<tid>/stat`. `rpc` is null until WP-03b's registry. `runtimes.*.busy_ms_delta` is tokio's worker busy time; `blocking_now` counts the large-reply parses running in rt_bg's blocking pool; `runtimes.hot.rpc_violations_total` the RPC work found on an `arbx-hot` thread (0 unless a client was not bound). A first line's deltas are null.

**Runtimes** (`src/runtime.rs`, WP-02 item 1). `rt_hot`: 2 workers named `arbx-hot`: the state stream, the gRPC feeds, the send paths and their keep-alives, the Jito result streams, the executor's send tasks. `rt_bg`: `[runtime] bg_threads` (3) workers named `arbx-bg`, niced +5 (its blocking pool too): every RPC call. The client is bound to it (`Rpc::bind`): each call is spawned there whichever runtime awaits it, and replies over 256 KiB are parsed in its blocking pool. The boot, the route-program check, the engine's lookup-table and bin-array fetches, the executor's simulations and settlements and the venue-program hashing therefore run on rt_bg. RPC work found on an `arbx-hot` thread is counted (a debug assertion in debug builds; a run.log WARNING at the end).

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

**As WP-03 writes it** (`src/rec/accounts.rs`, `AcctRec::record`). Producers: the state stream's feed task (`feeds/mod.rs::forward`, src 0 with `write_version` and `is_startup`), `arbx run`'s boot snapshot (src 1, between MARK `boot_begin` and `boot_end`; programdata accounts are not in the snapshot: megabytes each, the stream reports their upgrades), and the engine's re-fetches of DLMM bin arrays it starts following (`engine.rs::fetch_accounts`, src 2). `src` 3 and MARK `fork_refetch` come with WP-04 / WP-07. The `aseq` is taken and the record queued under one lock, so the file is in `aseq` order whatever thread records. `role` and `pool_index` come from the run's role table (`rec::accounts::Roles`): the registry's pools (1), vaults (2), PumpSwap base mints (5), CPMM configs (3) and the PumpSwap fee config (11), and WP-03's extra watched accounts: the Clock sysvar (6), every DLMM pool's bitmap-extension PDA whether or not it exists (7, with its pool), the programdata accounts of the route program and every venue program (8), the wallet (9) and its token accounts (10: its WSOL account and its associated account for every registry mint); DLMM bin arrays (4) are added as the engine follows them, with a MARK `watch_list_changed` naming the new ones. A reconnect of the state stream writes MARK `stream_reconnect` (n = 0). Keyframes: FULL for an account's first record in a file, on a length change, and when `accounts_keyframe_every` - 1 XOR records followed the last FULL (the recorder's interval, ×4 under disk pressure). The queue's byte cap counts each record's data. Reader: `rec::accounts::parse` / `read_dir` (XOR applied, `data_xxh3` checked).

### 4.13 journal.bin (new): the engine's input journal

Producer: `src/rec/journal.rs`, called from `Engine::step(ev, t_engine)` and `Engine::timers(t)`. These replace the body of `engine.rs::run` (:324-358) in WP-03 (moved from WP-09, F11).

**Determinism contract.**
- **Clock.** The engine reads the clock once per event. That value (`t_engine_ns`) is journaled and used for every decision made while handling the event.
- **Timers.** Timeouts (commit groups, quiescence, lookup-table retries, in-flight expiry, the lag SLO minute) are evaluated only in `timers(t)`, and every call is journaled as TIMER. One exception kept from arb-lab: expired confirmation waits are also checked at the end of each input, at that input's `t_engine_ns` (deterministic).
- **Outside inputs.** Inputs from other subsystems that change engine or send-check decisions reach the engine as events and are journaled as INPUT: blockhash-ring heads, leader-schedule windows, SendGate changes, quarantines, in-flight releases, health changes.
- **Latency.** Stage timestamps for latency reports are taken with real clock reads, but they are never decision inputs, and replay does not compare them.
- **Coverage.** Recordings made before WP-03 have no journal and cannot be replayed.

```
file header:  magic "ARBXJRN\0" | u16 format = 2 | u16 hlen | JSON header (schema arbx.journal/2.1)
record:       u8 kind | u32 body_len | u64 seq | u64 t_engine_ns | body
  1 TX_FIRST   u16 feed | u64 slot | u64 t_rx | u64 t_decoded | i8 executed (-1 none, 0 failed, 1 ok)
               | u8 enc (0 wire bytes, 1 protobuf Transaction) | u32 len | bytes
               | u8 has_loaded | [u16 nw | nw×32 | u16 nr | nr×32] | u8 has_poh | [u64 slot | u64 hashes | u32 ticks | u64 hpt]
  2 TX_COPY    [64] sig | u16 feed | u64 t_rx            (a later copy: timing only, as the engine uses it)
               | u8 has_poh | [u64 slot | u64 hashes | u32 ticks | u64 hpt]     (2.1; readers of the 74-byte form ignore it)
  3 ACCOUNT    u64 aseq (accounts.bin) | u8 store_verdict (0 accepted, 1 stale)
  4 SLOT       u64 slot | u64 parent (u64::MAX = unknown) | i32 status | u64 t
  5 BLOCK_META u64 slot | [32] blockhash | u64 height | u64 parent_slot | u64 t
  6 ALT        [32] table | u8 found | u16 n | n×32
  7 INPUT      u8 kind (1 blockhash_head, 2 leader_window, 3 gate, 4 quarantine, 5 inflight_release, 6 health,
               7 wallet_tx, 8 slotidx_missing, 9 settled, 10 engine_init) | u32 len | JSON
  8 TICK       (no body: housekeeping ran here; status only)
  9 STATUS     (ignored by replay)
 10 TIMER      u64 t | u8 what (2.1: 1 flush, 2 housekeeping; absent = both)
               (timers_at(t, what) ran: replay calls it at exactly this point, time and scope)
 12 GAP        u64 first_lost_seq | u64 n_lost
```

**2.1** (review WP-03; one minor version over 2.0, same framing, no 2.0 recordings exist): the TX_COPY PoH tail, a repeated TX_FIRST for a later copy that carries loaded addresses (readers that count TX_FIRST as unique transactions must count signatures instead), INPUT kinds 9 and 10, and TIMER `what`.

`seq` has no holes unless a GAP record says so. Replay refuses to compare decisions inside a gap interval and reports it. Volume: §5.

**As WP-03 writes it** (`src/rec/journal.rs`; `Engine::step(ev, t_engine)`, `Engine::timers(t)`).
- **Who writes it:** only the engine thread, at its dequeue point (`step`), and `arbx run`'s boot before the engine starts: the boot snapshot's ACCOUNT records carry `t_engine_ns` 0; replay applies them straight to the store, as `arbx run` does (`journal::boot_store`, which then derives the followed DLMM bin arrays).
- **The run loop:** `run` journals the engine_init record first, then takes one clock read per input and calls `step`; every decision made while handling it reads that value (prices' unix time for DLMM / DAMM v2 fees, deadlines, expiries, pool CU-price windows, signature windows). `timers_at(t, what)` writes a TIMER record, then runs the state flush (`what` 1), expired confirmation waits (always), and housekeeping (`what` 2; at most every 5 ms, with its 2 s DLMM drift check and 10 s status line). arb-lab's rules (review WP-03 #7): on every 5 ms idle wake-up both; after an input, the flush only, and only when the queue is empty with state triggers pending (an empty queue is the only sign a transaction's updates have all arrived: nothing is flushed while it is not); every 10 s while the queue never empties, housekeeping (plus the flush if the queue is empty then). Expired confirmation waits are also checked at the end of every input, at its `t_engine_ns` (deterministic, as at HEAD). The timer anchors (when housekeeping, the drift check and the status line last ran) start at the first journaled input's or timer's time, never at an unjournaled clock read (review WP-03 #2a). Stage timestamps (`st`, latency series) stay real clock reads.
- **engine_init** (INPUT 10, `t_engine_ns` 0, after the boot snapshot's ACCOUNT records; review WP-03 #2b, #2c): what the engine starts with that no input carries: `{min_tip (the cheapest enabled send path's tip: every opportunity's net), strategy_sha256 (the [strategy] section as JSON, signer_stats_file left out), executor (bool), signer_stats_file, signer_stats: {signer: [ok, miss]} as loaded}`. The signer statistics file is cross-run, rewritten every 10 s and shared (PLAN-ADDENDUM I-5): only its content as loaded makes trigger-skip decisions reproducible. `journal::replay_engine(reg, cfg, records, accounts)` builds the replay's engine from it (the boot store, an offline engine, the record applied; an error without the record or when `cfg`'s `[strategy]` is not the run's); `Engine::new_offline` never reads or writes the statistics file. A run with an executor folds its send checks and routes into `decision_digest`; an offline replay reproduces them from WP-05 / WP-09 on.
- **The boot section** is the leading records with `t_engine_ns` 0 (the boot snapshot's ACCOUNT records and engine_init); a GAP among them (it carries the writer's clock) does not end it, and replay reports it.
- **TX_FIRST** holds the bytes as the feed delivered them: wire bytes (`enc` 0) from raw shred and entries feeds, the protobuf `Transaction` (`enc` 1) from deshred and transaction streams; a synthetic arrival without bytes is re-encoded from its parsed form (`tx::to_wire`, legacy / v0, its first signature and a zero blockhash). A later copy that carries loaded addresses for its lookups is also a TX_FIRST record (the engine learns lookup-table entries from it); replay treats a repeated signature as a copy. **TX_COPY** appends `u8 has_poh | [u64 slot | u64 hashes | u32 ticks | u64 hpt]` (the engine keeps a later copy's PoH position when the first had none); readers of the 74-byte form ignore the tail.
- **ACCOUNT** names the record by `aseq`; the verdict is the store's check before the update (`Store::is_stale`). **SLOT** is every status of the state stream (interslot ones too), `parent` u64::MAX when unknown. **BLOCK_META** `height` u64::MAX when unknown. **ALT** is the answer of a lookup-table fetch (`found` 0: none). **STATUS** is `u16 feed | UTF-8 message` (a feed's status line; replay ignores it). **TICK** marks a status line written by `timers`.
- **INPUT** kinds written now: 2 `leader_window` (`{start, leaders: [pk]}`, from the LeaderBook's refreshes); 3 `gate` in two forms: `src` "decision" (review WP-03 #3), written by the engine thread at the send check that saw the SendGate's mode, whenever that mode differs from the last one journaled: `{mode (as the check read it), reason, detail, since_ns, sticky, src, opp}`, right after the input whose handling made the decision and with its `t_engine_ns` (the check reads the live gate, so a pause closes it at once; a replay of send checks applies the record at opportunity `opp`; the mode is also folded into `decision_digest`), and `src` "watch" (the SendGate's `json()` sampled every 100 ms on the background runtime whenever it changes: status and coverage, not a decision input; replay passes it to the engine, which ignores it); 9 `settled` (an executor settlement in full: `{attempt, error, fired (send::Fired), landed: {path, sig, slot, tx}, jito, nonce_value}`; the executor's replay is WP-05 / WP-09's); 10 `engine_init` (above). Kinds 1 and 4-8 come with WP-03b, WP-04, WP-05 and WP-07.
- **Replay** (`journal::replay(engine, records, accounts)`, on the engine `replay_engine` built): each record's event with its `t_engine_ns`, each TIMER at its time and scope; it counts ACCOUNT records whose verdict differs from the replayed store's, records it cannot find in accounts.bin, GAPs, skipped INPUTs (settlements, engine_init) and decision-point gate records (`gate_observed`). A journal written by `Engine::run` itself replays to the run's state and decision digests (test `a_journal_written_by_run_replays_to_the_run`). `Engine::digest()` (the decision state: store contents and versions, signature windows, opportunities, predictions, signer statistics, lookup tables, counters, pending groups) and `Engine::decision_digest()` (a running hash of every opportunity and every route handed to the executor) compare runs.

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
| tip_total | lam | sender_tip + cpi_tip paid (0 when `ok` is false; WP-08) |
| tip_asked | lam | (WP-08) sender_tip + cpi_tip asked for, whatever the outcome |
| tip_senders | [str] | |
| jito_tipped | bool | pays any Jito tip account |
| bundle | {known, src (`jito-result`, `explorer`, `heuristic`), id, pos, size} / null | |
| arb_like | {is, why (`venues`, `pools`, `known`, `program`)} | same test as `record_rival` |
| ours | {attempt} / null | our transaction |
| prog_events | [{kind, leg, amount, code}] / null | our program's decoded logs (only for our txs) |

**As WP-03 writes it** (`src/rec/exec.rs::exec_json`, built and serialized on the chain writer). Producer: the transaction streams (`[[state.tx_stream]]`, Stage 0: PumpSwap), `src` `grpc-tx`, `found_by` `["tx_stream"]`, `idx` from `TransactionInfo.index`. The backfilled and wallet records are WP-03b's (same builder). `cu_limit`, `cu_price_micro` and `loaded_data_limit` come from ComputeBudget instructions (legacy, v0) or the v1 transaction's `config` (then `cu_price_micro` is null and `priority_fee` is its `priority_fee`); `priority_fee` = ceil(limit × price / 10⁶) with the default limit min(1.4M, 200,000 × non-ComputeBudget instructions). `inner` and `logs` are null when the provider says it omitted them (`*_none`), `return_data` null when absent. `signer_sol` is null when the balances are missing. `watched` lists the watched accounts (the run's role table, §4.12) that are writable in the transaction; for a failed transaction only the fee payer can be among them (role names as accounts.bin's, `pool` the pool index). `venues` names venue programs invoked top-level or inner (the rival list's 13 programs). `transfers`, `tip_total`, `tip_senders`, `jito_tipped`, `bundle`, `arb_like` (WP-08) and `ours`, `prog_events` (WP-05 / WP-08) are null. The schema is `arbx.exec/2.0`; arb-lab's `sol` / `tok` are `signer_sol` / `signer_tok`. Review WP-03 fixes: one line per **(signature, slot)** from a transaction stream (`rec::exec::Recent`, kept across reconnects, the latest 200,000 pairs): a re-delivery (reconnect) is dropped, a transaction executed on two forks keeps both lines and the reader keeps the canonical fork's; `bank_id` (the transaction's bank when the provider sends `SubscribeUpdateTransaction.bank_id`, else null); a queued record counts against the chain queue's byte cap at its protobuf size.

**As WP-08 writes it** (`src/classify.rs`; schema `arbx.exec/2.1`). The derived fields are filled on the chain writer by the hook `rec::exec::derive` (`classify::annotate`) from the record's own fields (`keys`, `ixs`, `inner`, `pre`, `pre_tok` / `post_tok`, `venues`, `pools`), so any §4.14 record classifies alike whatever produced it; the wallet.jsonl writer (WP-03b) makes the same one call (`rec::exec::derive(&mut v)` after `exec_json`; until that merge its lines keep them null). A record whose keys or instructions do not decode keeps them null.
- `transfers`, in execution order (each top-level instruction, then its inner instructions): every System Transfer, TransferWithSeed, WithdrawNonceAccount, CreateAccount and CreateAccountWithSeed (`lamports`), every SPL Token / Token-2022 Transfer and TransferChecked (`mint`, `amount` as a decimal string) and every CloseAccount (`lamports`, `mint`). `kind`, the first rule that matches: a System transfer to a tip account is `sender_tip` at the top level and `cpi_tip` from inside a program (any sender, the signer or a program's vault); a System transfer inside an Associated Token Account instruction, and every CreateAccount, is `rent_create`; a System transfer into the signer's WSOL account is `wrap` when a SyncNative of that account follows, else `self`; a transfer to a platform wallet (`data/platform-fee-wallets.json`, compiled in; none is sourced yet, so this kind does not occur) or to a token account one owns is `platform_fee` (`sender` = the platform); a token transfer made by a PumpSwap buy or sell (the instruction directly above it) to its protocol fee token account, coin-creator vault token account or buyback token account (accounts 10, 17 and the last, as build.rs fills them) is `venue_fee`; a transfer between the signer and accounts it owns (token accounts by their owner in the token balances, or as an InitializeAccount / ATA instruction of the transaction set them) is `self`; a CloseAccount of the signer's WSOL account is `unwrap`, of any other token account `rent_close`; the rest (swap legs, pool payments, refunds) is `other`. A close's `lamports` is the account's balance when it closes: its pre-balance plus what the instructions before it moved in or out (System transfers and creations, WSOL token transfers); null when the record has no pre-balances. `depth` is 0 at the top level, else the stack height minus 1 (1 when the provider gives no height); `ix` the top-level instruction; `from` / `to` are token accounts for token transfers. Accounts created and closed in the same transaction are in no token balance: their mint and owner come from the transaction's InitializeAccount{,2,3} or ATA Create instructions. A failed transaction (`ok` false) moved nothing: its transfers are the ones its instructions asked for, and the inner ones the provider recorded before the error (they name the lane it used: WP-19); with `inner` null only the top-level ones are known.
- The tip map: `send::tip_owner_names`, the same names rivals.jsonl's `tips` carry (§4.21): the code's sender lists first (`known_tip_accounts`, `OTHER_TIP_ACCOUNTS`), then the catalogue `data/sender-tip-accounts.json` (compiled in, `send::TIP_CATALOGUE`; a service's `sender`, else its key, and every service that adds an account of its own must have a `sender`) for every account those do not name: 46 more on 2026-10-04 (Glaive, Soyas, AllenHark, Solami, the bloXroute and SVS Lightspeed legacy accounts), each with its provider source (`tip_account_sources`: `source_url`, `fetched`, `attribution`). On cmp2's rivals this names Glaive's 4,197 rows, Soyas' 458, bloXroute's 72 and Solami's 16; about 33,800 rows over about 190 accounts stay unnamed (the largest AgmLJBMD... with 4,671 rows, then the eight FAST... accounts with 4,158; `testdata/classify/cmp2-rival-tips.json`).
- `tip_total`: the `sender_tip` and `cpi_tip` lamports **paid**: those the instructions ask for when `ok`, 0 for a failed transaction (it pays only its fee; review WP-08 #5); `tip_asked`: the lamports asked for, whatever the outcome (`tip_total` = `tip_asked` when `ok`). `tip_senders`: the services those tips go to, first tipped first; `jito_tipped`: one of them is one of Jito's eight tip accounts. Both describe the lane the transaction asked for, so they are set for failed transactions too.
- `bundle`: `{known: true, src: "jito-result", id, pos: 0, size: 1, slot, index}` for our transaction once the block engine's `processed` result named it (`classify::note_bundle_processed(sig, bundle, slot, index)`, called by WP-05 in send/jito.rs `on_result`; a line written before the result arrives stays heuristic); `{known: false, src: "heuristic", id: null, pos: null, size: null}` for any other successful Jito-tipped transaction (a bundle candidate); null otherwise, and always for a failed transaction (a Jito bundle lands only when all of it succeeds). Block adjacency and the explorer lookup (`explorer`) are the toolkit's (WP-10): a line is written once, before its neighbours in the block are all known.
- `arb_like`: `{is, why}` with `why` `venues` (two venue programs besides the aggregator), `pools` (two watched pools), `known` (a signer seen doing either before) or `program` (a watched pool touched by a top-level program seen at the top of such a transaction before); the learned signers and programs are process-wide and bounded (200,000 each), as the engine's rival detection.

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

**As WP-03 writes it.** The state stream subscribes to `blocks_meta` when `[state] block_meta` is `on`, or `auto` and the probe file (`[state] probe_file`, default `<out_dir>/probe.json`) shows the state provider accepted it; the probe file is copied into the segment. Written by the state stream's feed task (`feeds/mod.rs::forward`); `leader` from the LeaderBook when it knows the slot. The engine keeps the newest block meta (`Engine::last_block_meta`) for WP-03b's blockhash ring, and journals each one. Review WP-03: `auto` needs the probe to have accepted it AND received at least one message (an inconclusive or silent result is off); `bank_id` (`SubscribeUpdateBlockMeta.bank_id`, null when 0 / not sent) is added; a block meta whose blockhash does not decode is dropped and counted in the state stream's feedhealth `errors_total`.

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

**As WP-03 writes it.** `[state] slot_statuses = "all"` subscribes with interslot updates; `"commitment"` keeps arb-lab's three statuses; `"auto"` (the default, review WP-03 #5) is `all` where the probe file shows the state provider accepted `slots_interslot` with at least one message, else `commitment` (the interslot filter shares the state stream's one subscription with the accounts: a provider that refused it would refuse the whole stream). meta.json `state.slot_statuses` is the effective value. Written by the state stream's feed task; `status` names as above (`unknown` for a value outside 0-6); `bank_id` (`SubscribeUpdateSlot.bank_id`, null when not sent; review WP-03 #12) is added. The engine journals every status; only processed, confirmed and finalized move its slot gauges and the stream's feedhealth `slot_max_now` (a first-shred slot is ahead of every processed one) until WP-04's fork tree. `bank_id` is not yet in accounts.bin or the journal (WP-04 adds it with its fork handling).

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
**As WP-08 writes it** (schema `arbx.rivals/1.2`; review WP-08 #1, #2):
- **Tip names from the full map.** `tips[][2]` comes from `send::tip_owner_names` (the engine's `tip_names`), which now takes the catalogue `data/sender-tip-accounts.json` after the code's lists: the same names as exec.jsonl's `transfers` (§4.14). On cmp2's rows that names Glaive's 4,197 tips, Soyas' 458, bloXroute's 72 and Solami's 16, which arb-lab's map left null.
- **Sampled `venues` rows** (plan addendum I-9). cmp2's rivals.jsonl had 849,585 rows in 28 minutes (1.29 GB/h raw, 238 MB/h at zstd-3); 744,411 (88%) were `why = venues`. `[record] rivals_venues_sample` (default 10; 1 keeps all) keeps 1 in N of the `venues` rows, chosen by the transaction's signature (`rec::sample::keep_1_in`: splitmix64 of the signature's first 8 bytes, little-endian, modulo N), so a replay, a re-run and another bot's recording of the same transactions keep the same rows. `pools` and `known` rows are all kept. The choice is made right after `why`, before the row is built; a left-out row's signer is still learned (its next transaction can be a `known` row). Each kept `venues` row carries `sample` `{one_in, kept, seen}`: the rate and the running counts of the segment's `venues` rows written and seen, this one included; `sample` is null on every other row and when N is 1. Readers weight a row by `sample.one_in` (1 when null); manifest.json `sampling.rivals_venues` holds the segment's totals (§4.4). At N = 10 cmp2's rows become 179,899 (74,725 `venues`, 10.04%): 266 MB/h raw, 54 MB/h at zstd-3 (§5). exec.jsonl's `arb_like` (§4.14) is not sampled: the toolkit's v2 rival report reads it.

### 4.22 moves.log (v2: columns appended)

Producer: `engine.rs::on_account` (:882-887), the first update of each (transaction, pool) pair.
`<sig> <slot> <pool> <t_ns> <acct> <write_version> <role>`. The first four columns are arb-lab's; a v1 reader ignores the rest. **As WP-02 writes it:** `write_version` is `-` (WP-03 carries it), `role` is `pool` or `vault`. **As WP-03 writes it:** `write_version` is the update's (`-` for an RPC read, which never names a transaction).

### 4.23 poh.log (v2: columns appended)

Producers: `feeds/mod.rs::forward` (entries feeds, :171-179) and `feeds/shred.rs::poh_advance` (shred feeds, :247-266). Always on (no longer tied to exec).
`<sig8> <slot> <ms> <feed> <entry_idx>`: `ms` = position on the leader's PoH clock since the slot began (hashes / hashes-per-tick × 6.25 ms); `entry_idx` = entry index within the slot when known, else `-`. **As WP-02 writes it:** always on; entries feeds write `-` for `entry_idx` (they see one message's entries, not the slot's index); shred feeds write the slot's entry index, one record per finished data set (several lines). The same signature can appear once per feed; readers keep the line from the feed with full slot coverage (`slots-feed` `poh_complete`), else the earliest. **As WP-08 writes it:** entries feeds write the entry's index in its slot when the feed followed the slot from its first entry (the same condition as the position itself: entries arrive in order, so the count so far is the index), `-` otherwise; shred feeds as before. The positions of forwarded transactions (any feed; a shred feed's only once its walk reaches them, after the hand-over) are also kept in the process's PoH index (`feeds::poh_index`, by `sig8`, earliest kept, 3 minutes), which settlement and the `poh_trigger_pct` gauge read: the engine's own map gets only the entries feeds' positions (they ride on the arrival).

### 4.24 slots-feed.log (v2; arb-lab `slots.log`)

Producers: `feeds/mod.rs::forward` (entries feeds) and `feeds/shred.rs` (shred feeds), when a feed finishes a slot.
`<feed> <slot> <ticks> <entries> <txs> <t_first> <t_last> <valid> <data_shreds> <code_shreds> <sets_ok> <sets_failed> <poh_complete>`. The first eight columns are v1 (entries feeds; `valid` = 0 when the feed joined the slot midway). Shred feeds fill all columns; entries feeds write `-` in the last five except `poh_complete`. **As WP-02 writes it:** entries feeds only (shred feeds with WP-08); `poh_complete` = 1 when the slot was followed from its start (`valid`) with all 64 ticks. **As WP-08 writes it:** shred feeds fill every column, one line per slot, written when the PoH walk reaches the slot's last shred (LAST_SHRED_IN_SLOT) or, short of that, when the assembler drops the slot (20 s after its first shred): `ticks`, `entries` and `txs` as walked in order from the slot's first entry (votes included in `txs`), `t_first` / `t_last` the first and last shred's kernel time, `valid` = the walk started at the slot's first data set, `data_shreds` / `code_shreds` received (a duplicate data shred is not counted; code shreds are counted as they come), `sets_ok` / `sets_failed` data sets decoded / unparseable, `poh_complete` = the walk reached the last shred with 64 ticks. A slot that received only code shreds writes no line.

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

Producer: `src/leaders.rs`, when a 400-slot window of the schedule is fetched, plus kind updates (WP-08; WP-03 writes none: a list refresh that changes a validator's kind is an `events.jsonl` `leaders_refresh` line, and the slots learned after it carry the new kind).

| Field | Type | Semantics |
|---|---|---|
| slot | slot | |
| leader | pk | validator identity |
| kind | enum | `jito`, `bam`, `other`, `unknown` |
| kind_src | str | which source: the Jito validators API host (its `running_bam` / `running_jito` give BAM and Jito), `bundle_result` (validator identity seen in our Accepted/Processed results: `jito`, since a bundle result says the leader ran the Jito block engine, not BAM; WP-03 deviation 6), a public BAM list if one is identified, the static file and its date (F39), or `gossip_client` (WP-08: the client it announces). For `unknown` (WP-08), why: `no_source` (no source names the leader), `no_schedule` (attempts only: the slot is outside the schedule held) |
| kind_age_s | integer | age of that list |
| region | str / null | the region of the leader's gossip IP from the offline geo table: its metro (WP-08), else its city |
| city | str / null | (WP-08) `<country>-<city>` of the gossip IP |
| tpu_quic | str / null | (WP-08) the TPU-QUIC endpoint the leader announces (`ip:port`) |
| tpu_region | str / null | (WP-08) that endpoint's region: for BAM and Harmonic validators a shared ingress node, often in another city or country than `region` |
| tpu_shared_by | integer / null | (WP-08) how many cluster nodes announce that endpoint |
| rtt_ms | ms / null | latest QUIC-handshake RTT from our host to the TPU-QUIC endpoint the leader announces (`tpu_quic`; kept per endpoint, WP-08). This is **not** the bundle's path, which runs block engine → leader (F40); the block-engine RTT is `attempts.leader.be_rtt_ms` |
| rtt_age_s | integer / null | |
| rtt_src | enum / null | `quic_handshake`, `region_bucket` (fallback when handshakes are refused: the median of the fresh endpoints in `tpu_region`, or in `region` without an endpoint) |
| client | str / null | the gossip `clientId` (WP-08), else from the version string |
| t_ns | t_ns | when written |
| event | enum | (WP-08) `learned`, `kind_update` |

**As WP-03 writes it** (`src/leaders.rs`). One line per slot when it is first learned: windows of 400 slots from the current slot (`getSlotLeaders`, on the background runtime), a new window every 100 slots, so each refresh writes about 100 lines. `kind` as known at that moment, from the newest Jito validators API list (`kind_src` its host: `running_bam` → `bam`, `running_jito` → `jito`, absent → `other`), else the static fallback (`kind_src` `static:validators-meta.json@<date>`, `kind_age_s` from that date); a validator that our bundle results named (`Accepted` / `Processed` `validator_identity`) and no list puts in `jito` or `bam` is `jito` with `kind_src` `bundle_result`; `unknown` when no source says anything. `region`, `rtt_*` and `client` are null (WP-08). List refreshes are `events.jsonl` `leaders_refresh` / `leaders_list_stale` (failed fetches keep the older list or the fallback).

**As WP-08 writes it** (`src/leaders.rs`, schema `arbx.leaders/1.1`). Every line gains `event`: `learned` (the slot first learned, as above) or `kind_update`: after a source changed (a list refresh, the node table, a validator our bundle results named), the refresher's pass writes again every scheduled slot from the current one on whose `kind` or `kind_src` is not what its last line said (the WP-03 hand-off). `city`: `<country>-<city>` (the city without its district, spaces as `_`) of the leader's gossip IP in `[leaders] geo_table` (`data/ip-geo.csv`: DB-IP City Lite ranges, CC BY 4.0, of the cluster's addresses on 2026-10-04), null when the IP or the table does not say; `region`: the metro that city belongs to (`leaders::METROS`, review WP-08 #9: Tokyo's Shibuya, Shinagawa, Chiyoda, Koto, Minato and Inzai are `JP-Tokyo`; New York, Newark, Piscataway, Secaucus, ... `US-New_York`; Frankfurt, Offenbach, Hattersheim, Limburg, ... `DE-Frankfurt`; Ashburn, Sterling, Reston, ... `US-Ashburn`; 27 metros), else the city: the shipped table's 195 cities are 132 regions, and the 671 voting validators of 2026-10-04 fall in 69 regions (96 cities), 24 of them with a single validator (32 cities). `tpu_quic`, `tpu_region` and `tpu_shared_by`: the endpoint the leader announces in gossip, its region, and how many nodes announce it (review WP-08 #3, measured again on 2026-10-04's public getClusterNodes / getVoteAccounts: 472 of 671 voting validators, 68.7% of stake, announced a TPU-QUIC address on another IP than their gossip address; the 382 on port 5010 (BAM) share 16 endpoints, one of them serves 103; the 671 announce 233 endpoints; 210 validators, 24.5% of stake, are in another city than their endpoint, 121 (14.4%) in another region, 51 (6.9%) in another country). `kind_src` of an `unknown` kind is `no_source` (review WP-08 #6). `client`: the node's gossip `clientId` (`getClusterNodes`: Agave, JitoLabs, AgaveBam, Firedancer, Frankendancer, HarmonicAgave, FireBAM, Rakurai, ...), else the family its version implies (0.x Frankendancer, 26+ Firedancer, else Agave). A fourth kind source, `kind_src` `gossip_client`, names a validator no list names and no bundle result showed: `JitoLabs` is `jito`, `AgaveBam` and `FireBAM` are `bam`, plain `Agave` is `other` (other clients say nothing; a version-derived client is no evidence; a list that names the validator wins). `rtt_ms`: host → the announced TPU-QUIC endpoint: the handshake time of a QUIC connection to `tpu_quic` (ALPN `solana-tpu`, no stream opened, no data sent, closed at once; `rtt_src` `quic_handshake`), kept **per endpoint** (review WP-08 #3): the prober measures the endpoints of the leaders of the next 64 slots, each endpoint once however many validators announce it, at most `[leaders] rtt_per_sec` (2) handshakes a second, each again after 5 minutes (after 1 minute when its handshake failed or timed out at 1.5 s), and every validator behind an endpoint carries its RTT; a leader whose endpoint has no fresh measurement takes the median of the fresh endpoints in its endpoint's region (`tpu_region`; its gossip `region` when it announces no endpoint) (`region_bucket`), never of its gossip region's when they differ; an RTT older than 10 minutes is not used (null). `rtt_age_s`: the measurement's age (the newest sample's for a region). The lines are written when a slot is learned (about 160 s ahead), so their RTT is the one known then; the attempt's snapshot (§4.37) has the RTT at sending.

### 4.28 validators.jsonl (new)

Producer: `src/leaders.rs`, hourly snapshot (WP-08: every 10 minutes). One line per validator: `{t_ns, identity, vote, stake_lamports, gossip_ip, tpu_quic, version, client, jito, bam, region, rtt_ms, src}`.

**As WP-08 writes it** (schema `arbx.validators/1.0`, bulk class: the disk ladder's step 2 stops it with rivals). Every 10 minutes once the vote accounts are known (review WP-08 #7: the first snapshot comes before the prober measured anything, and a 20-minute segment must hold one with RTTs): one line per identity with a vote account (`getVoteAccounts`, current and delinquent), with `delinquent`, `client_src` (`clientId` or `version`), `kind` and `kind_src` (§4.27), `city`, `tpu_region`, `tpu_shared_by`, `rtt_age_s` and `rtt_src` added (§4.27's meanings); `jito` = the kind is `jito` or `bam`, `bam` = it is `bam` (both null when the kind is `unknown`); node fields null for a validator absent from `getClusterNodes`. `src` names the sources of the snapshot: `getClusterNodes+getVoteAccounts+<kind list>+geo:<table>`. The node table is fetched every 10 minutes and the vote accounts every `refresh_min`, on the background runtime (`events.jsonl` `leaders_refresh` with `src` `getClusterNodes` / `getVoteAccounts`, `leaders_list_stale` on a failure, with `fails` and `retry_s`: a failed fetch, a validator list's too, is tried again after 30 s, then 60 s, ... up to its period, review WP-08 #8; every error has its URLs cut to the host and key parameters masked, review WP-08 #4); each snapshot is a `leaders_refresh` event with `src` `validators.jsonl` and the RTT counts `rtt` {`probes_ok`, `probes_failed`, `endpoints_fresh`, `regions_fresh`, `validators`, `validators_rtt_own`, `validators_rtt_bucket`}: handshakes so far, endpoints and endpoint regions with a fresh RTT, and the validators with a vote account whose RTT is their endpoint's own, a region bucket's, or neither (the rest).

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
| leader | {target_slot, identity, kind, kind_src, region, rtt_ms, rtt_src, rtt_age_s, client, be_rtt_ms, next: {slot, identity, kind}} | the LeaderBook snapshot (WP-03 / WP-05; region, RTT and client from WP-08). `rtt_ms` is host → leader TPU-QUIC; `be_rtt_ms` is the latest keep-alive RTT to the block engine. **As WP-08 provides it:** `LeaderBook::snapshot(slot)` (`leaders::LeaderSnap`: `slot`, `leader`, `kind`, `kind_src`, `kind_age_s`, `region`, `city`, `tpu_quic`, `tpu_region`, `tpu_shared_by`, `rtt_ms`, `rtt_age_s`, `rtt_src`, `client`, `be_rtt_ms`, `next {slot, identity, kind}`, §4.27); an `unknown` kind carries its reason in `kind_src` (`no_schedule`: the target slot is outside the schedule held, `leader` null; `no_source`), so the field acceptance "identity and kind, or `unknown` with a reason" is checkable; `rtt_ms` is host → the endpoint the leader announces (`tpu_quic`), its own (`quic_handshake`) or its endpoint region's median (`region_bucket`); `be_rtt_ms` is what the send path last published with `leaders::note_be_rtt` (WP-05's keep-alive loop), null when older than 5 minutes |
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

**As WP-03 writes it** (`arbx.probe/1.0`). Each subscription is opened alone, one after the other, for `--seconds` (30): `accepted` true when the stream stayed open for the whole window; false with `error` when the provider refused it (`<gRPC code>: <message>`), could not be reached, or closed the stream early (`stream closed by the server after <ms> ms`). `messages_30s` counts account, slot, transaction, block and block-meta updates (pings excluded; deshred: transactions). Extra fields per entry: `host`, `window_s`, `n_accounts` (`accounts_full`: the candidate pools, the clock, the wallet and the programdata accounts, padded with derived keys that name no account to max(3,000, 4 × pools)), `feed` (`deshred_5`, one entry per enabled `yellowstone-deshred` feed). `blocks_account_include` asks for transactions (not accounts or entries) at confirmed commitment. Written to `[state] probe_file` (default `<out_dir>/probe.json`) and a dated copy `probe-<YYYYMMDD>.json` beside it; `[state] block_meta = "auto"` reads the `blocks_meta` entry of a probe of the same `provider_host`.

**Review WP-03 #4** (PLAN-ADDENDUM I-2, I-3: Haan grants its streams to the first process only and answers the others 503; its outages are transient). Each entry also has `verdict` (`accepted`, `refused`, `inconclusive`), `code` (the error's gRPC code, e.g. `Unavailable`, `PermissionDenied`; null without a gRPC answer) and `http_status` (the HTTP status of a reply without gRPC status, e.g. 503). An error that says nothing about what the provider supports is **inconclusive**, `accepted` null: Unavailable (HTTP 429 / 502 / 503 / 504 map to it), ResourceExhausted, DeadlineExceeded, Aborted, Cancelled, or no gRPC answer at all (transport error, not opened in time). A definite refusal (PermissionDenied, InvalidArgument, Unimplemented, Unauthenticated, ...) or an early close is `refused`. `auto` (`block_meta`, and `slot_statuses` on `slots_interslot`) is on only for `accepted` with `messages_30s` > 0. `arbx grpc-probe` refuses to start while anything may hold the provider (a live segment's control socket under `<out_dir>` at depth 1-2, a held `<out_dir>/.supervisor.lock`, an `arbx … run` or `arb-lab … run` process on the host) unless `--force`, and holds `<out_dir>/.supervisor.lock` while it runs (deploy/run-w.sh does not start a campaign meanwhile; a lone `arbx run` started during a probe is not stopped). With any inconclusive entry it writes only `probe-<YYYYMMDD-HHMMSS>-inconclusive.json`, leaves probe.json as it was, and exits 3. meta.json `probe` lists `accepted` (accepted with messages), `refused`, `inconclusive` (with `code` and `messages_30s`) and `age_s` (how old the probe was when the segment started).

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
| txarr, poh, rivals | 0.2-0.3 GB | as arb-lab. rivals (WP-08, plan addendum I-9): cmp2's arbx wrote 238 MB/h at zstd-3 (1.29 GB/h raw, 88% `why = venues` rows); keeping 1 in 10 of those (`[record] rivals_venues_sample`) leaves 54 MB/h (266 MB/h raw) |
| validators | < 1 MB | WP-08: about 1,000 lines of about 650 bytes every 10 minutes (4 MB/h raw) |
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

**WP-00 fields in the v1 files (v1.1).** WP-00 adds fields to the v1 files and changes no existing field's meaning, except the state-trigger stage times and the latency percentiles below. v1 files carry no schema header, so a reader tells v1.1 by the fields' presence (`meta.json` `limits`).
- `triggers.jsonl`: `hint_only: true` on every decoded swap when `[strategy] decoded_sends = false`; `opp` is then always null (the hint was not priced), and its `st.decided` is the end of the hint's bookkeeping, not a pricing decision. Skipped triggers still write no line.
- `attempts.jsonl`: `crowded` (bool: a pool of the route is on `[live] crowded_pools_file`), `queue_rank` (`Prio::rank`: 0 seed pool (source `mriya` or `both`), 1 other, 2 crowded) and `st.fired` (t_ns at which the copies were handed to the runtime: `fire` spawns the send, so `signed→fired` is the spawn's cost; the bytes leave at copies.jsonl `t_sent`. Null when the sim gate fires them later). The line is now written after the copies are fired.
- `attempts.jsonl` and `opportunities.jsonl` `st` of a state trigger: `rx` = `decoded` = the receive time of the pool's first account update stamped with the trigger transaction (kept even when the engine queue emptied between the transaction's updates), `engine` = that update's dequeue, `resolved` = the start of the evaluation, `decided` = the end of the route search. In v1 all five held one time.
- `status.jsonl`:
  - counters `trigger_hint_only` (engine), `live_skip_big_band_throttle`, `live_skip_crowded_pool` (a crowded route expecting at least `[live] crowded_skip_min_expected_lamports`) and `rank_crowded` (exec); `trigger_skip_signer_fails` now also follows the skipped signer's swap (its statistics keep learning);
  - `exec.over_rate: {crowded, other}`, the totals of copies refused for a send path's rate, split by the crowded rank;
  - the latency series `state_recv_to_engine`, `state_engine_to_decided`, `state_recv_to_decided` (one sample per state evaluation, whatever it decided), `hint_rx_to_done` (one per hint: receive to the end of its bookkeeping), `decided_to_signed` and `signed_to_fired` (one per attempt) and `signed_to_sent` (one per settled attempt whose first copy was sent: signed to that copy's `t_sent`) (A.8). The v1 decoded series (`rx_to_decoded` … `rx_to_decided`) take samples only from priced decoded triggers (`decoded_sends = true`); with hints only they stay at n 0.
  - Latency `n` counts every sample since the start (v1 reset it at 200,000). The percentiles come from a uniform reservoir of 8,192 samples of the whole run (v1: all samples since the start or the last reset), so they still cover the run so far, not the interval.
- `meta.json`: `limits: {sending, max_size_sol, max_size_src, sim_max_size_sol, max_failed_fees_lamports, max_new_token_accounts, decoded_sends, state_triggers, big_band_min_expected_lamports, big_band_max_per_sec, crowded_pools_file, crowded_skip_min_expected_lamports, record}`, and `overrides` (what `--shadow` and `--no-record` changed for this run: `{mode: "shadow"}`, `{"record.enabled": false}`; `{}` for none).
- The `send` lines of `run.log` give `over-rate N (crowded M)` per path.

**WP-02 in the v1.1 files.** Every v1.1 stream is now compressed and rotated by the recorder (§1.6) and starts with a header naming `arbx.<stream>/1.1`; arb-lab's names change only for the per-feed slot log (`slots.log` → `slots-feed`, v2 columns), the raw entries archive (`entries.zst` → `entries-<feed>.NNN.bin.zst` with an ARBXENT header and the v1 frames) and the lookup-table dump (`alts.jsonl` → `alts-final.jsonl.zst`). The records are unchanged except: outcomes.jsonl's running `failed_fees_lamports` is now `failed_fees_total_lamports` (after this attempt) plus `failed_fees_delta_lamports` (this attempt's part); poh.log and moves.log are at v2 (§4.22-§4.23); status.jsonl is v2 (§4.8); the exec.rs diagnostic lines also go to events.jsonl (`log`).

**WP-01 in the v1.1 files.** Every `status.jsonl` line carries `send_gate` (`{mode, reason, detail, since_ns, sticky}`, the SendGate when the line was written; review M2), and the final line (written once the run knows why it stops) carries `stop_reason` (A.5). `exec.counts` (the executor's counters, `Exec::status`) gains `reject_gate_shadow` / `reject_gate_stopped` when the SendGate refuses a send (review M11: they are under `exec.counts`, not the engine's `counts`). `meta.json` is v2 (§4.2); a reader tells it by its `schema` field. The segment directory also holds `config.toml` (the frozen config), `stop.json`, `control.jsonl` and, while it runs, `control.sock`.

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

**SendGate shadow reasons** (`status.send_gate.reason`, `gate_change` events; the process keeps running and recording): `control`, `forced_shadow` (`--shadow`), `equity_hour` (campaign-wide rolling hour), `reconcile_miss`, `state_slo` (only with `slo_action = "shadow"`; recovers automatically), `core_record_loss` (for the rest of the segment), `recorder_unhealthy`, `disk_budget` (before the stop), `program_hash_mismatch` (WP-01: the route program on chain is not `[exec] expected_program_*`, or could not be read; for the whole segment), `mode_shadow` (WP-01: a run without `--live` or `--canary`, which sends nothing). A stop request turns the gate to `stopped` with the stop reason. A closed gate makes `Exec::wants_send` refuse, counted as `reject_gate_shadow` or `reject_gate_stopped` in `exec.counts` (A.7; the shadow reason is in the gate, not the counter name). A send deferred past its decision (the sim gate's re-checks, scheduled bundle resends) asks the gate again and is dropped when it is closed (review M10).

### A.6 Event kinds

`feed_connect`, `feed_disconnect`, `feed_error`, `state_stream_reconnect`, `tx_stream_reconnect`, `jito_stream_down`, `jito_stream_up`, `warmup_ready`, `warmup_lost`, `lag_slo_breach`, `lag_slo_recovered`, `gate_change`, `fork_dead_slot`, `fork_abandoned`, `late_member`, `alt_give_up`, `programdata_change`, `quarantine` (Stage 0: `would_quarantine`), `recorder_drop`, `recorder_io_error`, `recorder_encode_error`, `recorder_writer_dead`, `recorder_writer_stalled`, `recorder_fatal`, `replay_gap`, `disk_action`, `leaders_refresh`, `leaders_list_stale`, `snapshot`, `snapshot_slot_mismatch`, `recon_miss`, `wallet_update_missing`, `blockhash_source_disagree`, `chainfetch_backlog`, `jito_token_refresh`, `probe`, `log` (diagnostic lines that arb-lab printed to stderr), `config_note`, `stop_requested`.

### A.7 Counter names (`counts_total` / `counts_delta`)

- **Engine:** `tx_first`, `trigger`, `trigger_hint_only`, `trigger_skip_will_fail`, `trigger_skip_signer_fails`, `trigger_unquotable`, `trigger_exact_out_unsolved`, `alt_wait`, `alt_learned`, `alt_retry`, `alt_gave_up`, `resolve_failed`, `commit_complete`, `commit_superseded`, `commit_timeout_unknown`, `commit_timeout_quiescent`, `commit_late_member`, `torn_suspect`, `fork_abandoned_slot`, `fork_priced`, `pred_scored`, `pred_exact`, `pred_pre_state_unknown`, `evaluation`, `route_priced`, `opportunity`, `state_opportunity`, plus one counter per rejection reason of A.1 (`reject_<reason>`).
- **Exec:** `attempt`, `sent`, `send_refused`, `live_skip_big_band_throttle` and `live_skip_crowded_pool` (WP-00 only), `rank_crowded`, `verdict_<outcome>`, `landed_ok`, `landed_fail`, `expired`, `expiry_status_hit`, `amended`, `unsettled`.

### A.8 Stage names (`latency`, `stages`)

- **v2:** `first_shred→update_recv`, `update_recv→commit`, `commit→engine`, `engine→priced`, `priced→decided`, `decided→built`, `built→signed`, `signed→enqueued`, `enqueued→sent`, `sent→ack`, `sent→first_verdict`, `sent→seen`, `sent→landed`.
- **WP-00 interim names** (state path, before WP-04's commit stages exist; F13): `state_recv_to_engine`, `state_engine_to_decided`, `state_recv_to_decided`, `decided_to_signed`, `signed_to_fired` (handed to the runtime), `signed_to_sent` (first copy's `t_sent`), and `hint_rx_to_done` for decoded hints. WP-02's latency gate compares against the state-path ones.
- **v1 names** `rx_to_decoded`, `decoded_to_engine`, `engine_to_resolved`, `resolved_to_decided` and `rx_to_decided` remain for priced decoded triggers only (`decoded_sends = true`); hints go to `hint_rx_to_done`.

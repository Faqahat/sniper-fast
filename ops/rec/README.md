# sniper-rec: the pump.fun raw recorder on the host

Records every pump.fun create and every later transaction that touches one of those mints. The record format is the
same as FRA's collector (`ops/collect/collect.py`). Output is one directory per PKT day. There is a remote archive
tier, an on-demand fetch, and 24/7 supervision with Telegram alerts.

It is independent of the engines: code in `ops/rec/` (stdlib Python + bash), data in `/home/moiz/sniper-data/rec/`,
its own systemd units. Read-only: no wallet, no sends.

All times below are PKT (UTC+5). Server and container clocks are UTC.

## 1. How it runs

| Unit | What | State now |
|---|---|---|
| `sniper-rec.service` | the recorder (`recorder.py`). Restarts 10 s after a crash; a clean exit is not restarted | installed, **not enabled** (waits for the cut-over) |
| `sniper-rec-watch.timer` | watchdog pass every minute (`watchdog.py`) | enabled |
| `sniper-rec-daily.timer` | 01:30 PKT: catalog, slim extract of yesterday, archive, links (`daily.sh`) | enabled |

- Secrets live in `/etc/sniper-rec/env` (root, mode 600): `SHYFT_RPC_URL`, `RMR_RPC_URL`, `CONSTANTK_TOKEN`,
  `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `FTP_HOST/FTP_USER/FTP_PASS/FTP_DIR/FTP_PORT` (empty until the owner
  sends them). These values were copied from FRA's collector environment. Never print them.
- Settings live in `/etc/sniper-rec/rec.conf` (not secret; template: `rec.conf.example`).
- systemd loads both files and runs everything as `moiz`. The `rec` wrapper does the same for commands that need
  secrets (`sudo systemd-run ... EnvironmentFile=...`).
- **HOLD file** `/home/moiz/sniper-data/rec/HOLD` (JSON: reason, by, time). While it exists the recorder will not
  start (exit 0, so systemd does not restart it). The recorder writes it itself on a rate-limit trip,
  `REC_STOP_AT` or `REC_STOP_SLOT`. The overlap guard writes it when it stops a test. Remove it to start again.
- Crash safety:
  - Chunks are sync-flushed and fsynced every 10 s. `slots.tsv` is written only after the chunk data it describes is
    on disk.
  - On restart the recorder repairs the last chunk: it keeps the complete lines up to the last `slots.tsv` slot and
    copies the original to `repair/` (nothing is deleted). It resumes at the next slot, so no slot is lost or
    duplicated. Proven with SIGKILLs, see Tests.
  - After a stop longer than `REC_RESUME_MAX_H` (6 h) it starts fresh at the chain tip. The hole is written to
    `run.json` (`holes`) and to `gaps.jsonl`.
- `kill -USR1 <pid>` dumps every thread's stack to `logs/stacks.txt`.
- **Owner, on your side:** set the Incus container to start on host reboot: `incus config set moiz boot.autostart true`
  on the host. The units inside start by themselves.

### Modes (`REC_MODE`)

**`normal`**, after the cut-over. What FRA's collector does today:
- blocks from SHYFT, RMR and CK, round-robin by slot, 6/s per endpoint, with failover;
- getSlot, enrichment (creator history, funder, earlier creates, metadata, Jito bundles) and the per-day final pass
  (curve account + top holders) on CK at 20/s;
- `LAG` 32 slots, 10 fetch threads.

One deliberate difference: the final pass's heavy calls (getTokenLargestAccounts, getMultipleAccounts) are paced at
`REC_HEAVY_RPS` = 1.8/s.
- Constant-K's "veryheavy" class allows 2/s. FRA runs these calls at 20/s, and about a third of them get 429.
  Measured 10-27: ~50 429s/min on the engines' key.
- FRA's final pass never completes; its old runs end at "final 500/25493", "final 2100/42343", "final 10100/42408".
- On the host, ~50k mints take ~8 h (00:00 to ~08:00 PKT) in a background thread while recording goes on.

Note: RMR currently answers only `429 max usage reached` (on FRA too), so FRA in practice runs on SHYFT and CK.

**`overlap`**, side by side with FRA:
- SHYFT only, with a hard cap of `REC_EP_TOTAL_RPS` across all methods;
- refuses to build a Constant-K URL;
- enrichment is metadata + Jito only; `enrich.jsonl` rows carry `"rpc": "deferred"`;
- the final pass is deferred;
- it stops at the first 429 / usage / credit / quota error (HOLD).

Every knob is an env var (`REC_*`), listed at the top of `recorder.py`.

**Last-resort endpoints.** `REC_BLOCK_FALLBACK` and `REC_RPC_FALLBACK` are comma-separated env names, and `CK` means
Constant-K. They are used only after every primary failed (blocks), or on every second retry after a failed primary
call (rpc). This is how the recorder runs on its own key with Constant-K kept as a last resort (see OVERLAP.md):
```
REC_BLOCK_EPS=SHYFT_RPC_URL,NEW_RPC_URL
REC_RPC_EP=NEW_RPC_URL
REC_BLOCK_FALLBACK=CK
REC_RPC_FALLBACK=CK
```
`NEW_RPC_URL` goes into `/etc/sniper-rec/env`.

## 2. Day layout

```
/home/moiz/sniper-data/rec/
  days/YYYY-MM-DD/            one PKT day (00:00 PKT = 19:00 UTC the day before)
    txs/txs_<unix>.jsonl.gz   records, 5-min gzip chunks, same format as FRA (keys s,i,bt,sig,err,fee,cu,cup,cul,signers,mints,progs,ixn,ev,tb,sd,tips)
    launches.jsonl            creates of this day          enrich.jsonl   metadata/Jito (+ creator history in normal mode)
    gaps.jsonl                skipped / failed slots       final.jsonl    curve + top holders (final pass)
    slots.tsv                 ONE line per slot: slot, status (ok|skip|fail|perr), blockTime, txs in block, records, creates, processed-at
    run.json                  start_slot, start_time, window_end_time (= next 00:00 PKT), tail_end_time (= same), end_slot, mode, endpoints, holes
    status.json               live every 30 s; phase "DONE" once the day is finalized
  catalog.json  state/  logs/  slim/  cache/  repair/  HOLD (only when held)
```

**Rotation rule.** Blocks are processed in slot order. The first block whose `blockTime` is at or after the next 00:00
PKT opens the next day. Everything before it belongs to the old day, including skipped or failed slots. So
`end_slot(D) + 1 == start_slot(D+1)`: the days touch with no gap and no overlap, and `slots.tsv` proves it slot by
slot (`rec check <day>`). A block after midnight whose `blockTime` reads before midnight stays in the new day, because
slot order wins.

**Follow rule.** Every mint is followed for `REC_FOLLOW_H` = 24 h 20 min after its create, which is FRA's maximum.
Each tx goes to the day of its slot. So a day's `txs` also holds trades of mints created the day before; their create
is in the previous day's `launches.jsonl`. Existing tools filter txs by the same directory's launches. They do not
crash on this, but they drop those txs unless you load both days' launches.

**FRA differences** (see the overlap study):
- Today's FRA runs are 24 h windows starting about 19:15 PKT, with a 20 min tail. Each run follows only its own
  creates, so a mint created late in a run is followed for only 20 min.
- The host follows every mint for 24 h 20 min.
- Records are byte-identical for the same tracked mint set.

**Compatibility links.** `collect/run_YYYYMMDD_0000 -> rec/days/YYYY-MM-DD` (named by PKT day), so tools that glob
`collect/run_*/txs/*.jsonl.gz` and read `run.json` keep working.
- Links are made only from `REC_LINK_FROM` (the cut-over day) on, so FRA's runs and host days never double up.
- `rec link` (also run daily) creates them and removes dangling ones. A day archived off the host loses its link
  until `rec fetch`.
- No tool parses run-dir names for times. Lexical order of the names is still chronological.

## 3. Catalog and the `rec` CLI

`/home/moiz/sniper-data/rec/catalog.json`, rebuilt incrementally by `rec catalog [--all]` (daily, and after each day
is finalized).
- **Each day records:**
  - `where`: host / remote / cache, or a combination;
  - its paths, `slot_range`, and `time_range` (also in PKT);
  - its files, each with size, sha256, record count, and slot/blockTime range;
  - total txs, launches, enriched rows;
  - gaps, as skip / fail / longest failed run;
  - completeness: the `slots.tsv` contiguity check, holes, and `full_day`.
- **Old FRA runs** (`collect/run_*`) are indexed in place, never rewritten (`runs` section). Every PKT day lists the
  run chunk files that cover it (`legacy`), and `legacy_coverage` gives the share of the day with create coverage plus
  its holes. Example: 10-23 has the known 18:31–19:26 hole; 10-22 is 75.6%.

```
rec status                    recorder, HOLD, lag, rates, disk, catalog, archive backlog, alerts
rec days                      one line per day
rec where "2026-10-27 16:40"  (or an epoch, or a slot)  -> day / run, chunk file, where it lives
rec check 2026-10-28          contiguity inside the day and with its neighbours
rec path 2026-10-20           local path (host or cache) for tools
rec fetch 2026-10-01..2026-10-03   pull archived days into the cache
rec pin 2026-10-15 / rec unpin    keep a day local (host and cache)
rec archive [--dry-run]       upload + verify + free days older than 7 (normally run by the daily timer)
rec due                       remote days past the remote retention (listed only, never deleted)
rec remote-test               end-to-end check of the remote (run once the FTP details are in the env)
rec slim 2026-10-26           build the trades-only extract
rec test-alert                send one Telegram test message (refuses a second one without --force)
```

## 4. Archive tier (remote = OVH Backup Storage over FTP)

- **Host** keeps the last `REC_HOST_KEEP_DAYS` = 7 days. Older finished days (and old FRA runs whose days are all
  older) are uploaded to `FTP_DIR/days/<day>/...` (`runs/<run>/...` for old runs) with a manifest in
  `manifests/<unit>.sha256`.
- **Remote** keeps the last `REC_REMOTE_KEEP_DAYS` = 28 days. Older ones are only listed by `rec due` for the owner;
  nothing remote is ever deleted automatically.
- **FTP specifics** (stdlib `ftplib`):
  - **Connection.** It tries FTPS with a certificate check, then FTPS without the check, then plain FTP; the mode
    used is logged (`logs/remote.log`). Once a host has done TLS it is never silently downgraded to plain, so a
    stripped `AUTH TLS` is refused instead. Passive mode throughout, and no remote hash command is needed.
  - **Upload.** Each upload goes to `<name>.part`. An interrupted upload resumes (REST + STOR, or APPE if REST is
    refused); dropped connections reconnect and retry. Then the remote SIZE is checked and the file is renamed.
  - **Verification** (`REC_VERIFY=full`, the default): SIZE of every file, then a full re-download of every file
    streamed through sha256 (nothing is written to disk). Only after every file of the unit matches is the host copy
    removed. This is the only place a host copy is ever deleted.
- **Why full verification:**
  - FTP gives no remote checksum.
  - A day is about 13 GB, which re-downloads in minutes at OVH backup bandwidth.
  - Deleting the only copy on a SIZE check alone would not catch a corrupted transfer.
  - If `rec remote-test` shows the bandwidth makes this too slow, set `REC_VERIFY=sample`: SIZE for every file,
    sha256 for a rotating 10%.
- **Adding the remote:**
  1. `sudo nano /etc/sniper-rec/env` and fill `FTP_HOST`, `FTP_USER`, `FTP_PASS` (`FTP_DIR=/sniper-rec`,
     `FTP_PORT=21`).
  2. `rec remote-test`: connect (TLS mode shown), 64 MB upload to `.part` + rename, SIZE, re-download sha256, delete,
     and the projected minutes per 13 GB day.
  3. `rec archive --dry-run`, then `rec archive` (or let the daily timer do it at 01:30 PKT).
- Other backends (same interface, `backends.py`):
  - `REC_REMOTE=mount` with `REC_REMOTE_PATH` (NFS / CIFS / sshfs);
  - `REC_REMOTE=rsync` with `REC_REMOTE_PATH` and `REC_REMOTE_SSH=user@host`;
  - S3 is not built.

## 5. Fetch and cache

- `rec fetch <day|a..b>` downloads into `rec/cache/days/<day>/`, verifying each file's sha256 against the catalog (a
  corrupted remote file is refused). Then tools read it like a host day (`rec path <day>`).
- **Cap** `REC_CACHE_CAP_GB` = 60 GB, with LRU eviction by last use (`fetch` / `path`).
- **Never evicted:** a pinned day, the day just fetched, and a day whose only copy is the cache.

## 6. Watchdog and alerts

Every minute (`sniper-rec-watch.timer`):
- **Recorder:** process/service alive; status age and newest chunk age; lag vs the chain tip (one getSlot per minute
  on the public `api.mainnet-beta.solana.com`, never CK or SHYFT); consecutive failed slots and slot jumps; failed and
  skipped slots in the last hour; day rotation; finalization.
- **Host and archive:** disk %; archive failures and backlog.

| Alert | When |
|---|---|
| down | recorder not running > 2 min |
| stalled | status > 3 min old, or newest chunk > 5 min old |
| lag | > 5 min behind the chain |
| hole | > 30 s of consecutive failed slots, or a slot jump |
| disk | ≥ 85% used |
| archive / backlog | an archive run failed / days older than 9 still on the host (only once the remote is configured) |
| rotation / finalize | still writing yesterday after 00:15 PKT / yesterday's final pass not started by 03:00, stuck > 1 h, or not DONE by 14:00 PKT |
| hold | the recorder or the guard stopped it (an operator HOLD is silent) |

- Each alert is sent once when it starts, repeated every 6 h while it stays, and followed by a RECOVERED message when
  it clears.
- Telegram goes through the engines' bot and chat. Messages are plain, with PKT times, starting `🛰 rec:`.
- Also written to `logs/alerts.log` and `state/watch.json` (the session reads this).
- Recorder checks are on only when `REC_EXPECT_RUNNING=1` (set at the cut-over).
- One test alert was sent on 10-27 at 17:10 PKT.

## 7. Overlap test, cut-over and rollback

See `OVERLAP.md` (numbers, verdict, and the exact steps).
- `overlap_e.sh` ran the sampled side-by-side test.
- `guard.py` watched FRA's counters read-only and would have stopped it.
- `overlap_compare.py` does the slot-by-slot comparison.

For the cut-over:
- **`REC_START_SLOT`** (fresh start only): start at FRA's last slot minus a margin. The gap is filled from RPC history,
  and the margin slots are recorded by both.
- **`REC_SEED_LAUNCHES`**: keep following FRA's current-run mints. They are kept in `state/seed_launches.jsonl`, not in
  a day's `launches.jsonl`.
- **`REC_STOP_SLOT`** (for a rollback): fill up to the slot where FRA's restarted collector begins, then stop.

## 8. Disk math (300 GB disk; 10-27: 199 GB used, 100 GB free)

- **Recording volume:** host ≈ FRA ≈ 13 GB/day of chunks. The 24 h follow adds a few percent: mints older than 12 h
  are 1–5% of records late in a run.
- **Host retention:** 7 days ≈ 95 GB. The cache is at most 60 GB, and only when something is fetched. Slim extracts
  stay on the host: about 0.31 GB/day, ~9.5 GB/month.
- **Old FRA runs** on the host now: 6 runs, 74 GB. They are archived first once the remote exists, since all their
  days will be older than 7.
- **During the overlap:** the keeper copy (13 GB/day) plus the host recording (13 GB/day) = 26 GB/day.
- **Without the remote:**
  - Normal mode reaches the 85% alert in about 4 days ((0.85 × 300 − 199) / 13).
  - The keeper pauses its copies at 95%.
  - So the FTP details are needed within a few days of the cut-over (or the owner frees space).
- **Remote:** 500 GB ÷ 13 GB/day ≈ 38 days. 28 days of days (~364 GB) + the old runs (74 GB) ≈ 440 GB, which fits.
  Anything older is listed by `rec due`.

## 9. Slim trades-only extract (built, not yet decided)

- **What:** `rec slim <day>` → `rec/slim/<day>.slim`, one row per trade event of a successful tx (`slim.py` has the
  format, and `slim.load()` reads it):
  - pump curve TradeEvent and PumpSwap Buy/SellEvent;
  - columns: slot, tx index, event index, block time, mint, user, side, SOL, tokens, virtual reserves (pool reserves
    for PumpSwap), tx fee, tip, program.
- **Encoding:**
  - columnar, with mint and user dictionary-encoded;
  - slot and block time delta-encoded;
  - byte-shuffled, then compressed with lzma.
- **Measured:** full days, each from two FRA runs, de-duplicated:
  - 10-26 PKT: 11.78 M trades (68% PumpSwap) → **313 MB** (26.6 B/trade, ~2.4% of the raw ~13 GB);
  - 10-25 PKT: 10.51 M trades → **279 MB**;
  - so about **0.3 GB/day ≈ 9 GB/month ≈ 110 GB/year**;
  - built in ~140 s on 8 cores; loads all columns in 7 s;
  - round-trip verified against the raw records.
- **Biggest columns:** amounts and reserves (tok 57 MB, vtok 70 MB, vsol 54 MB, sol 39 MB). A per-mint delta could
  roughly halve them if needed.

## 10. A second source later (design only, not built)

Today `get_block(slot)` asks one pool of RPC endpoints. To add a backup stream (say a Geyser/gRPC feed or a second
provider) in about a month:
- **Source interface:** `get(slot) -> block | SKIP | None`, plus `tip()`. The RPC pool is one source; a stream source
  buffers the blocks it has seen by slot.
- **Merger per slot**, in slot order as today:
  - Use the first complete block from either source.
  - A slot counts as skipped only if every source says skipped (or the stream has moved past it and RPC says skipped).
  - If one source fails, or times out after `T` s past the other, fill from the other.
  - When both deliver, compare signature lists. On a mismatch, log it and keep the primary's block.
- **Records stay identical:** the same `process_block` runs on whichever block was chosen. Provenance becomes an extra
  `slots.tsv` column (`A`, `B`, `AB`, or `A!B` for a mismatch).
- **Gap fill:** a later `rec backfill <day>` re-fetches `fail` slots from either source and writes their records to an
  extra chunk `txs_backfill_<t>.jsonl.gz`. It cannot recover the follow-ups of a create that sat inside a failed slot
  unless it re-runs the following slots with that mint added.

## 11. Tests (all passing on 10-27)

- `tests/test_unit.py`: day maths, `slots.tsv` truncation/stats, chunk repair, truncated-gzip index, pacer cap,
  limit-error detection, slim encoding. 9/9.
- `tests/test_replay.py <raw dir>`:
  - **Setup:** 240 real blocks served by a local fake RPC as consecutive slots, with block times shifted so a PKT
    midnight falls in the middle. Injected: skips, a failing slot, a transient error, `-32004`, a backwards
    blockTime, and two SIGKILLs (one at the midnight boundary).
  - **Checks:** rotation at the first block at or after midnight; the days touch; every slot exactly once; gaps
    exactly as injected; records **byte-identical to FRA's collect.py** (702 = 702); launches identical; day
    finalized. Also a 429 trip leads to HOLD, a clean exit, and no restart.
- `tests/test_cutover.py <raw dir>`: start slot, seeded FRA mints, stop slot, resume. Records equal collect.py's
  (405 = 405).
- `tests/test_normal.py <raw dir>`: normal mode. Two block endpoints, one always answering 429 like RMR now:
  round-robin + failover, no trip. RPC enrichment fields (creator history, funder) are present, and the final pass
  runs at the day rotation (final.jsonl has one row per launch; phase DONE).
- `TEST_FALLBACK=1 tests/test_normal.py <raw dir>`: the only primary is dead and the good endpoint is configured only
  as `REC_*_FALLBACK`. Every block and every RPC call is completed through the fallback.
- `tests/test_archive.py ...`:
  - **FTP** against a local pyftpdlib server (FTPS self-signed → unverified TLS; no TLS → plain; wrong password
    refused; no downgrade; `.part` + rename; REST resume; server killed mid-upload → resume).
  - **Archive flow** with rec archive/fetch/due/pin/LRU on ftp, mount and rsync; a corrupted remote file is refused.

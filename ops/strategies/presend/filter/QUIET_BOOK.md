# QUIET book: the 24 h whale history, kept on the host, given to every node (dip21)

Owner 10-27 PM: "keep the 24 h whale dump history on the host and give it to every node at engine start (FRA, AMS, any future
node)". The QUIET arm rule (REPORT.md: skip when all four quiet signals hold) needs each whale's dumps of the last 24 h. Without
that history an engine warms up 60 min. AMS has no raw recorder, so it cannot rebuild the history itself. The host can: it holds
copies of FRA's recording.

## How it flows

```
FRA raw recorder (/root/sniper-collect/run_*/txs, 5-min gzip chunks)
   │  keeper.sh (host, every 10 min): copies new and grown chunks to /home/moiz/sniper-data/collect/run_*/txs
   ▼
quiet_book (host): extends /home/moiz/sniper-data/quiet_book/quiet_book.jsonl: it reads only the chunks after the book's end
   │  (the engine's own code: the recording reader and DumpBook::ingest, so the book holds the dumps the live engine would hold)
   ▼
quiet_book_push.sh (host): per node in ops/collect/nodes.txt: rsync delta to /tmp/quiet_book/ on the node, sha256 check,
   │  sudo install -m 644 -> /root/dip/quiet_book.jsonl.new, sudo mv -f -> /root/dip/quiet_book.jsonl (a rename: atomic)
   ▼
engine start (run_dip_prod.sh --presend-quiet passes --presend-live-quiet-book /root/dip/quiet_book.jsonl when the file is there):
   book + own journal (--presend-live-quiet-state) merged, each dump once (identity = slot, tx index, event index)
   arm rule ON at once if the merged history is continuous >= 60 min and ends <= 30 min before the start
```

- **Format**: the engine journal's format (one JSON line each): `{"k":"start","v":1,"t":ns,"s":slot}`, `{"k":"d","s","i","j","t","w","n"}`
  (a final dump: slot, tx index, event index, block time, seller, followers), `{"k":"stop","t","s"}`. The engine loads the book with the
  same loader as its own journal.
- **Coverage**: one session per continuous stretch of the recording. A gap with no tx for more than 180 s starts a new session. The
  coverage ends at the last COMPLETE slot: the last slot read minus 3, taken over the slowest run still being written. At the daily
  rotation two runs are written at once, and a copy can stop mid-chunk. A dump after that slot is held back. The next pass reads it again.
- **Incremental**: a pass resumes at the book's last slot + 1, reading chunks named from 15 min before that. Dumps older than 24 h are
  dropped. `--full` rebuilds the last 24 h from scratch. A book whose end is older than 24 h is rebuilt, not replayed.
- **At the engine's start** (one log line):
  `QUIET history at the start: book /root/dip/quiet_book.jsonl: N dumps, K session(s), continuous X h to HH:MM PKT, gap G min | journal ... | merged ... | arm rule ON now (source: book)`.
  The source is `book`, `journal` or `book+journal`. Fallback order: a fresh book, then the engine's own journal (and the two joined),
  then the preload (FRA, from the node's own recorder), then the 60-min warm-up. Loaded dumps always count for the signals, even during
  a warm-up. A missing, cut or corrupt book never stops the engine: bad lines are skipped and counted, and the line says so.
- **Lag**: the keeper pass + build + push leave the node's book 2–20 min behind. The 30-min gap rule leaves room for that. If the host
  is down for more than ~20 min, the next start falls back to the journal, then the preload, then the warm-up. Dumps between the book's
  end and the start are not in the history unless the journal or the preload has them (the gap is not counted).

## Commands (host)

```
# build or extend the book (default: --rec /home/moiz/sniper-data/collect --out /home/moiz/sniper-data/quiet_book/quiet_book.jsonl)
/home/moiz/sniper-data/speed_fixes/bin/quiet_book            # one pass (incremental when a book exists); one status line
/home/moiz/sniper-data/speed_fixes/bin/quiet_book --full     # rebuild the last 24 h
# push to every node in ops/collect/nodes.txt; one status line (also in /home/moiz/sniper-data/quiet_book/push.log)
bash /home/moiz/sniper/ops/collect/quiet_book_push.sh        # exit 0 ok | 1 stale / no book / bad list | 2 a node failed
# local test of the push (no ssh)
bash /home/moiz/sniper/ops/collect/quiet_book_push_test.sh
```

Hook it into the keeper loop (proposal: `ops/collect/keeper_loop.sh.quietbook` = keeper.sh, then quiet_book, then the push). The
running loop must not be edited in place:

```
kill $(cat /home/moiz/sniper-data/collect/keeper_loop.pid)     # the loop only; a keeper.sh pass already running finishes by itself
cd /home/moiz/sniper/ops/collect && cp keeper_loop.sh.quietbook keeper_loop.sh.new && mv -f keeper_loop.sh.new keeper_loop.sh
setsid nohup bash /home/moiz/sniper/ops/collect/keeper_loop.sh > /dev/null 2>&1 &
```

## Add a node

1. Add one line to `ops/collect/nodes.txt`: `name host port user`. The user needs passwordless sudo, rsync and sha256sum on the node.
   `/root/dip` is created if missing.
2. Run the push once by hand: `bash /home/moiz/sniper/ops/collect/quiet_book_push.sh`. The node's part of the line must say
   `book pushed` (and the lists pushed on its first push).
3. Check it: `ssh -p PORT USER@HOST 'sudo ls -la /root/dip/quiet_book.jsonl; sudo tail -n 1 /root/dip/quiet_book.jsonl'`.
4. From then on every keeper pass updates it. `run_dip_prod.sh --presend-quiet` picks the book up when the file exists. The engine's
   start line names the source.

## Numbers (10-27, measured on the host's copies)

| | |
|---|---|
| Book (24 h to 16:00 PKT) | 46,276 dumps, 9,129 sellers: 5.49 MB (1.31 MB gzip) |
| Full build (24 h: 298 chunks, 3.8 M txs) | 164–172 s, one core |
| Incremental pass (10 min of recording, 7 chunks) | 2.0–3.0 s, +180–280 dumps |
| Incremental = full rebuild | the same 46,276 dumps. The only difference is the first session's start SLOT (the 24 h clip keeps the old one; coverage uses time) |
| Book = the live path (DumpBook fed the same 24 h) | 46,276 = 46,276, identical |
| Push per node per pass (rsync delta, two real books 10 min apart) | 58 KB uncompressed (34.5 KB of new lines + checksums). With -z the new lines are 7.7 KB, so ~25–30 KB on the wire, vs 1.31 MB for the whole book gzipped |
| Push atomicity (local test) | 20 pushes with a reader in a tight loop: 1,199 reads, each one a complete pushed version |
| Engine load at the start | 26–56 ms for the book (4.9–5.4 MB); 52–71 ms merged with its journal |
| Per trade | nothing: the book is read once at the start (on_exec over 5.4 M trades, r25: QUIET off 290 ns, on 357 ns, on + journal 327 ns; ±30 ns noise) |

Restart parity against the research replay (full history), with the book built as of the start minus the lag:

| Run | History at the start | Windows | Arm rule off | Skip mismatches |
|---|---|---|---|---|
| AMS r26, restart 10:00 → 10:05 PKT | book only, 10-min lag | 286 after the restart (627 in all) | 0 | 0 |
| AMS r26, same | book + journal, 10-min lag | 286 (627) | 0 | 0 |
| AMS r26, same | book only, 25-min lag | 286 (627) | 0 | 0 |
| AMS r24, its 4 real sessions | book + journal, 10-min lag | 790 | 0 | 0 |

The whale's follower mean differs on some windows (it misses the lag's dumps) but flipped no decision on these runs. Without the book,
AMS warmed up 60 min at every start.

## Limits

- **Recorder blind spot**: the recorder follows the tokens created in its 24 h window plus a 20-min tail. Trades on older tokens are not
  in the recording, so they are not in the book. The research replay and the preload have the same blind spot; a live engine sees them.
- **The gap is not counted**: dumps between the book's end (2–20 min before the start) and the start are missing, unless the journal
  (an engine ran then) or the preload (FRA) has them.
- **Daily rotation**: for up to 15 min after the old run's tail ends, the book's end is held at the old run's last slot (that run still
  counts as being written).
- **Host recorder move**: the builder reads `run_*/txs/txs_<unix>.jsonl.gz` under `--rec`. If the host records into another layout, point
  `--rec` at a run-style directory or extend `run_dirs`.

## Live since 10-27 ~18:10 PKT (main session)
- dip21 is on both nodes: /root/sniper-dip/snipe_engine_dip21 (sha256 b406ebc3…), run script fcea4d1b.
- First full book: 47,165 dumps, 9,212 sellers, 23.85 h, 5.60 MB, 156 s.
- **Schedule:** systemd `sniper-quietbook.timer` (every 10 min at :05) runs `sniper-quietbook.service` = `quiet_book` (incremental, ~3 s; log `/home/moiz/sniper-data/quiet_book/build.log`), then `quiet_book_push.sh` (log `push.log`, ~28 KB per node per pass). It is used instead of the keeper_loop hook, so it doesn't depend on the keeper (which goes away when the recorder moves to the host).
- **Fix 10-27:** the push loop read nodes.txt on stdin, and ssh ate the remaining lines (only the first node was updated). The loop now reads fd 3, and ssh / rsync get /dev/null.
- **Check:** `systemctl list-timers sniper-quietbook.timer`; `tail -3 /home/moiz/sniper-data/quiet_book/push.log`.

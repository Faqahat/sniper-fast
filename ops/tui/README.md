# dipmon — live monitor for a dip-bot run

A read-only terminal UI for one pump.fun dip-bot run (the engine's `<TAG>.jsonl` records + `<TAG>.log`), meant to be opened on
the trading node while the run is in progress, from a laptop or a phone SSH client. One Python file (3.9+, standard library
only: curses, threading, json, urllib) plus a small shell wrapper. It also reviews finished runs and local copies.

## Install (on a node)

```sh
sudo install -m 755 dipmon.py /root/prod/dipmon.py
sudo install -m 755 dipmon    /usr/local/bin/dipmon
```

The wrapper runs `python3 /root/prod/dipmon.py` under `nice -n 19` and `ionice -c3` (idle I/O; skipped if the container
refuses it), and sets `TERM=xterm-256color` when sudo dropped TERM. `DIPMON_PY=...` points it at another copy.

## Use

| command | what it opens |
|---|---|
| `sudo dipmon` | the running engine's run (found by the `--dip-log` in its command line), else the newest `dip_*rN.jsonl` in `/root/prod/runs` |
| `sudo dipmon --run 26` | `/root/prod/runs/dip_ams_r26.*` or `dip_r26.*` (add `--region ams\|fra` if both exist) |
| `sudo dipmon --snapshot` | a plain-text summary with the overview's numbers, then exit (for ssh / scripts) |
| `sudo dipmon --snapshot --json` | the same as JSON (lamports), incl. per-session figures and alerts |
| `dipmon --file X.jsonl` | any run file (finished runs, local copies); the `.log` next to it is read too (`--log` to override) |
| `dipmon --dir DIR` | another runs directory (e.g. `--dir ~/sniper-data/runs/ams/runs --run 26`) |

Other options: `--usd 100.5` (fixed SOL/USD, no network), `--no-usd`, `--ascii` (no Unicode), `--no-color`,
`--interval 2` (refresh 0.5–5 s, default 1), `--budget FILE` (default `<dir>/../dip_budget_ams.json` or `dip_budget.json`),
`--load-duty X` (initial load sleeps X × each chunk's work time; default 1 = at most ~50% of one core).
From another machine: `ssh -p 1996 it@84.32.104.202 sudo dipmon --snapshot` (needs sudo without a password prompt, or `-t`).

## Keys

| key | action |
|---|---|
| `1`–`7`, Tab, Shift-Tab | tabs: Overview, Pre-send, Regular, Trades, Health, Log, Config |
| ↑ ↓ PgUp PgDn Home End | scroll (Trades: move the selection; Log: End = follow the tail again) |
| Enter / Esc | Trades: details of the selected trade (full mint, buy / sell signatures, solscan links, timings) / back |
| `f` | Trades: all → pre-send → regular → wins → losses → open; Log: important ↔ all |
| `w` | Log: wrap long lines |
| `s` | scope: all sessions → session 1 → 2 … (a run restarted into the same log has several sessions) |
| `u` | swap the primary unit (SOL ↔ USD) |
| `p` | pause the screen (data keeps loading) |
| `r` | refresh the SOL/USD price now |
| `+` / `-` | refresh faster / slower (0.5, 1, 2, 3, 5 s) |
| `?` / `q` | help / quit |

## Screens

Wide terminals (≥ 120 columns) get two columns and large numerals; below 70 columns everything is one column and the run
P&L moves into the top line. Every screen has the header (region, run, engine build, status, price and its age), the tab bar,
an alerts strip and a key line. Status: **RUNNING** (engine process alive), **STOPPING** (signal / kill switch / planned end
passed, no DIP DONE yet), **ENDED** (`=== DIP DONE` or `run_end`), **ENGINE GONE** (no engine process and no DIP DONE).

1. **Overview** — the run P&L (big, green/red, USD under it); per hour, pre-send vs regular, kill-switch distance; start → end
   time, elapsed / planned with a bar; wallet (START BALANCE, now **est.**, kill-switch level, loss-cap gauge, dip budget left
   across runs); the config strip (badges, below); the cumulative P&L sparkline with its high / low and their times; the last
   trades; when the run ended, a banner with the result and the END CHECK.
2. **Pre-send** — fills / cap and failed-try fees / fee budget gauges (per session: the caps are per engine session), windows
   armed now, the result (net, realized, rent back, failed tries = count × fee, the fee check, wins / losses, average, best /
   worst), QUIET (stop rule, skip rule: warm-up countdown → on at hh:mm, preload, skips, stops, would-skips in the warm-up),
   exits by reason with P&L, paper (shadow row c) vs live, landing (send → seen median, slots after the trigger), windows skipped
   / disarmed by reason, try results; per-session table when there are several.
3. **Regular** — setup, P&L (fills / failed buys), fired → filled (fill rate), failed buys by cause (6042 price guard, 6001
   Lighthouse, other) with their fees, wins, exits by reason, P&L by leader client (Jito / BAM / Harmonic / Agave / Firedancer),
   landing (ms after the dump, same-block share), the open position, the funnel (dumps, picks, skips by reason).
4. **Trades** — every trade, newest first: time PKT, PS / REG, mint, size, P&L SOL and USD, %, exit (TP / SL / time, 6042 /
   6001 / fail for failed buys, open / hold), held slots, leader client, path. `~` after a P&L = the feed estimate until the
   engine's REALIZED line (chain txs) arrives.
5. **Health** — engine pid, CPU %, RSS, uptime, threads; log / records size and seconds since the last write (alert > 30 s);
   RUNTIME lag (latest p50 / p99 / max, worst p99); POLL-RPC-ERROR this minute / last 10 min / total; keep-alive and connection
   errors per send path in the last 10 min (e.g. `falcon refused 14`); disk %, load, memory; dipmon's own CPU / RSS; the price
   source; RPC-LAT per name and method (latest minute p50 / p99, timeouts).
6. **Log** — the engine log's tail (important lines or all), scrollable, wrap toggle. Lines are cleaned before display
   (control / wide / emoji characters, anything that looks like `key=` / `token=` / `user:pass@` is masked).
7. **Config** — every setting with its badge and full text (sources below), the wallet lines, the legend.

Text screenshots of every tab at 50x30, 80x24 and 160x50 (live, ended, and a QUIET warm-up demo): `screens/` (`screens/README.txt`).

**Badges**: a dot — green ● on, yellow ● warming up / partial / stopped, red ● off (`--ascii`: `+`, `~`, `-`). Pre-send live
(size, tries/slot, fills/cap, fee budget, route), QUIET stop rule and skip rule (yellow with "on hh:mm" during the warm-up; red
when off or not in this engine), paper shadow, M2 (gate green, shadow yellow), dev list (size), and plain items: regular buy
size + exit (TP / SL / hold slots), guard ×1.05, routes preset (v8–v13 matched from the ROUTE lines, else "custom"), sell
fan-out, nonce fan-out, near-leader gate (N leaders), skip clients, kill-switch level, planned minutes, engine build. Sources:
the `run_start` record, the log's start lines (`DIP LIVE |`, `DIP PRESEND LIVE (REAL attempts)`, `DIP PRESEND LIVE QUIET:`,
`DIP near-leader gate`, `NONCE-FANOUT`, `SELL FAN-OUT`, `ROUTE`, `START BALANCE`), and the running engine's command line (only a
fixed list of numeric / name flags is kept; paths, URLs and keys are never read out or shown). The engine build comes from the
binary's name (`snipe_engine_dip20`); for a finished run without a process it is inferred from the records (marked as such).

## Accounting (= `ops/dip/report/make_run_report.py`)

All sums in lamports, per engine session, then summed:

- **pre-send net** = Σ `presend_live_realized.pnl` (chain: each fill's buy + sell txs) + Σ `presend_live_ata_close.delta`
  (`ok` ones: the token-account rent back) − **failed-attempt fees**. The fees are counted live as Σ `presend_attempt_land.fee`
  where `res != "ok"` (6042 / deadline / ata_exists / buy_6005 …; `unseen` tries have fee 0). As the report does, the larger of
  that count and the engine's own counter is used (the 60 s status line's `failed-attempt fees`, `presend_live_stop.fees`).
  When every session has stopped, the Pre-send tab and `--snapshot` print the check (counted vs engine: equal on AMS r24/25/26
  and FRA r24; a session stopped by `max_fills` gets a few more fees from tries already in flight, which the engine's later
  status lines include). Wins = realized records with pnl > 0; fills = `presend_live_fill` records.
- **regular** = the log's `REALIZED mint=… pnl=…` of each filled buy (matched to the buys of that mint in order) + every failed buy
  at its tx fee (the landed buys' fee, 505,000 lamports in the current config = 5,000 + 100,000 CU × 5,000,000 µL; tips revert).
  A fill whose REALIZED line has not come yet shows the feed estimate (sell proceeds − spend, marked `~`) until it does.
- **run P&L** = pre-send net + regular. **Per hour** = run P&L / time since the first session started (to now, or to the end).
- **wallet now (est.)** = the current session's START BALANCE + its P&L; **kill-switch distance** = that − (START BALANCE − loss
  cap). An estimate: open positions count at cost, and the fees of tries never seen on the feed are not in it (the reports'
  own wallet note; ≤ 0.003 SOL on the runs below).
- **Sparkline**: the P&L changes put in their minute (fills at their sell time, failed buys at the buy, failed-try fees at the
  try), cumulated from the first start to now / the end.

Checked on the local copies (`tests/test_totals.py`), every figure vs the run report, ±0.0005 SOL (all agree to 0.00005):

| run | pre-send fills / wins / realized / rent / fees / net | regular buys / fills / wins / fills P&L / failed | total |
|---|---|---|---|
| AMS r24 (4 sessions) | 200 / 103 / +0.9775 / +0.3018 / 0.1082 / +1.1710 | 84 / 37 / 18 / +0.5480 / −0.0237 | +1.6953 |
| AMS r25 | 95 / 60 / +0.9518 / +0.1433 / 0.0507 / +1.0444 | 35 / 13 / 5 / +0.1057 / −0.0111 | +1.1391 |
| AMS r26 | 143 / 59 / +0.1343 / +0.2158 / 0.0993 / +0.2508 | 43 / 14 / 7 / +0.0644 / −0.0146 | +0.3005 |
| FRA r24 | 100 / 53 / +0.6551 / +0.1509 / 0.0629 / +0.7430 | 119 / 35 / 11 / −0.1754 / −0.0424 | +0.5252 |
| FRA r25 (kill switch) | off | 208 / 73 / 27 / −0.4807 / −0.0682 | −0.5489 |

## Safety

- Reads only: the two run files, the budget file, `/proc` (the engine's cmdline / stat / statm, meminfo), `os.statvfs`,
  `getloadavg`. Never writes to them, never sends a signal, never calls an RPC, never opens `.env`, keystores or configs.
- Incremental tails (offset kept; a partial last line is held until its newline; truncation / replacement → a clean reload).
  The high-volume records (tries, try landings, dumps, tapes, the shadow's records) are counted with substring checks without
  `json.loads`; the rest is parsed and type-checked (an odd value is dropped, never shown). Memory is bounded: aggregates, the
  trade list, 3,000 log lines.
- Initial load in 512 KB chunks with a sleep after each (≤ ~50% of one core by default), with a "loading x%" bar; `q` works.
- The price thread: Binance, then CoinGecko, every 60 s, 5 s timeouts; the last price cached in `/tmp/dipmon-solusd-<uid>.json`.

## Performance (`tests/test_perf.py`, this dev machine)

| case | initial load | after the load, 60 s at 1 Hz |
|---|---|---|
| AMS r24 finished (59 MB records + 2.2 MB log, 4 sessions) | 0.8 s wall, 0.25 s CPU, ≤ 46% of a core | 0.13% of one core, RSS 40.7 MB (peak 41.4) |
| AMS r26 finished (48 MB + 2.1 MB) | 0.8 s wall, 0.25 s CPU, ≤ 48% | 0.12%, RSS 40.1 MB |
| following r26 live at 1× the engine's write rate (~1.3 KB/s records) | 0.5 s | 0.12%, RSS 39.9 MB |
| following r26 at 10× (~22 KB/s records) | 0.5 s | 0.13%, RSS 40.0 MB |
| `--snapshot` of AMS r24 | 0.75 s wall, 0.27 s CPU, max RSS 39 MB | – |

Targets: < 2% of one core after the load, RSS < 80 MB. On the AMS node (2 cores, both busy with the engine) each operation is
slower and nice 19 makes dipmon wait for the engine, so the load takes longer; the steady state stays far below the target.
All 43 local runs (FRA r1–r25, AMS r9–r26) load with zero unparseable lines and their totals equal their reports' (±0.0005;
FRA r7 −0.0001: an older config whose failed buys cost ~500,000 lamports on chain while its landed buys cost 506,500).

## Tests

```sh
sh ops/tui/tests/run_tests.sh            # all (the follow test replays 7 h of r26 at 50x: ~9 min; QUICK=1 -> 200x)
python3 ops/tui/tests/test_units.py      # tail / partial lines / truncation, fuzzed lines, engine detection, cleaning, 3.9 syntax
python3 ops/tui/tests/test_totals.py     # totals vs the run reports (AMS r23-r26, FRA r24-r25)
python3 ops/tui/tests/test_curses.py     # the real UI in a pty at 50x30, 80x24, 160x50 (+ TERM unset, --ascii LANG=C, --no-color)
python3 ops/tui/tests/test_follow.py     # replay r26 while dipmon follows (snapshots + curses), totals equal at the end
python3 ops/tui/tests/test_perf.py       # CPU / RSS
sh ops/tui/tests/make_screens.sh         # text screenshots into ops/tui/screens/
```

`tests/replay.py` re-writes a finished run into a directory the way the engine does (time-scaled, records split before their
newline now and then, an optional fake engine process carrying `--dip-log`, optional synthetic dip20 QUIET lines in the
engine's formats). Test data: `/home/moiz/sniper-data/runs` (`DIPMON_DATA` overrides).

## Known gaps

- QUIET (dip20) was tested on synthetic lines built from the engine source's formats (`pslive.rs`): no dip20 run is in the local
  copies yet. Check the Pre-send / Config tabs on the first dip20 run (AMS run 27).
- No chain reads: a regular fill's P&L is exact once the engine prints its REALIZED line (seconds after the sell), the wallet is
  an estimate, and the fees of tries never seen on the feed are not counted (same as the engine; the reports bound them).
- A failed regular buy is booked at the landed buys' tx fee (from the engine's `--cu-limit` × `--cu-price-micro` + 5,000 while it
  runs, else the landed buys' `fee`): chain-exact on runs 23–26 (505,000), off by ≤ 6,500 lamports a failed buy on old configs.
- The log has no timestamps: per-minute health figures use the engine's one-a-minute RUNTIME lag line as the clock.
- One run per dipmon: if the engine starts a new run (a new file), restart dipmon (a restart into the same log is followed).

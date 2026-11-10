# REWIND: dipmon v3.1 + dipview, the live monitor and run explorer for the dip-bot runs (Go)

**11-03 (owner):** tab 2 is now **Engine** (short `Eng`; it was "Pre-send"); the pre-send fill kind is shown as **T2**
everywhere it used to say `PS` (Trades / overview tables, the type sort, the split / landing lines, the config short form,
`--snapshot`; re-arm stays `RA`, regular `REG` / `RG`; `tests/parity.py` maps the Python v1 oracle's `PS` to T2); the
overview's LAST TRADES carry the same yellow dot as Trades; the Filters tab shows each filter's **verdict** from the
FILTERS-3 study (11-03), leads with **net saved** and **prec**, sorts by verdict group, and folds the DISMISSED filters into
one line (`d` expands) — see "Filters tab". Later the same day: a LIVE skip whose shadow window never filled shows
**`no dip`** and SOL **`0.000`** (the trade would not have happened: nothing saved or lost; still behind `n`), the LIVE rows
get a **`move`** column (the shadow window's price move from the engine's `presend_disarm` "move": max / min % vs the
trigger's post price, e.g. `+35/-8%`; `–` on runs before it), and the `QUIET3-A (log)` row is hidden when QUIET3-A runs live.

**v3.1 (10-28):** the Trades table sorts by any column (`o` / `O`, or a click on a header with the mouse on) and has a
running-total column (the run P&L after each trade); size and total follow `u` (SOL ↔ USD); the config is grouped in
five blocks (Pre-send / Regular / Routes & sending / Safety & limits / QUIET & paper) on the overview and the Config tab;
mouse capture is **off by default** so the terminal's own selection and link clicks work (`M` toggles, `--mouse` starts
with it on); mints are OSC 8 links to GMGN, signatures / tokens / leader accounts to Solscan (the trade details, the
Trades table, the Engine tab's best / worst), and `c` copies the selected mint (OSC 52); the new **dipview** run
explorer (below).

A read-only terminal UI for one pump.fun dip-bot run (the engine's `<TAG>.jsonl` records + `<TAG>.log`), opened on the
trading node while the run is in progress, from a laptop or a phone SSH client. It replaces the Python dipmon's UI: the
same command line, the same `--snapshot` / `--json` output and the same accounting, **to the lamport** (checked
against the Python dipmon v1 on all 44 local runs). Built on Charm's stack: Bubble Tea v2, Lip Gloss v2, Bubbles v2,
Harmonica and ntcharts. A single static binary (no Python, no libc), about 10 MB.

## Install (on a node)

```sh
sudo install -m 755 dipmon-go /usr/local/bin/dipmon-go     # the binary (from /home/it/sniper-data/tui/, check its .sha256)
sudo install -m 755 dipmon    /usr/local/bin/dipmon        # the wrapper (ops/tui-go/dipmon): nice -n 19 + ionice -c3, TERM fix
sudo install -m 755 dipview   /usr/local/bin/dipview       # the run explorer's wrapper (ops/tui-go/dipview): dipmon-go --view, same priority
```

(On the nodes every installed file goes in as `X.new` and is then `mv`-ed over `X`, so a running copy is never
overwritten in place.)

The wrapper runs `dipmon-go` under `nice -n 19` and `ionice -c3` (idle I/O; skipped if the container refuses it) and sets
`TERM=xterm-256color` when sudo dropped TERM; `DIPMON_BIN=...` points it at another binary. The binary also lowers its
own priority at start (nice 19 and the idle I/O class, every thread), so `sudo install -m 755 dipmon-go
/usr/local/bin/dipmon` without the wrapper is safe too. Verify a copy with `sha256sum -c dipmon-go.sha256`.

## Use

| command | what it opens |
|---|---|
| `sudo dipmon` | the running engine's run (found by the `--dip-log` in its command line), else the newest `dip_*rN.jsonl` in `/root/prod/runs` |
| `sudo dipmon --run 27` | `/root/prod/runs/dip_ams_r27.*` or `dip_r27.*` (add `--region ams\|fra` if both exist) |
| `sudo dipmon --snapshot` | a plain-text summary with the overview's numbers, then exit (for ssh / scripts) |
| `sudo dipmon --snapshot --json` | the same as JSON (lamports): the Python dipmon's fields exactly, plus `ath_sol` / `ath_t` / `low_sol` / `low_t` / `from_ath_sol` (times in ns); `--extra` adds the trading card and the day card (with the day's ATH / low) |
| `dipmon --file X.jsonl` | any run file (finished runs, local copies); the `.log` next to it is read too (`--log` to override) |
| `dipmon --dir DIR` | another runs directory (e.g. `--dir ~/sniper-data/runs/ams/runs --run 27`) |
| `dipmon --screen 200x35` | render the UI once as plain text (`--tab 1-8`, `--page help\|detail\|splash\|today`), then exit |
| `dipmon --gcr-seed FILE` | the Filters tab's bad-creator ledger seed (default `/root/dip/gcr_seed.json` if it exists; `none` = this run's fills only, the row says so) |
| `dipmon --screens DIR` | text screenshots of every tab at `--sizes 200x35,160x50,...` into DIR |
| `sudo dipview` | the run explorer: every run in `/root/prod/runs` (`dipmon-go --view`; `--dir DIR` for another) |
| `sudo dipview --list` | the runs and their numbers as plain text, then exit |

From another machine: `ssh -p 1996 it@cyberams sudo dipmon --snapshot` (needs sudo without a password prompt, or `-t`).

Options: `--usd 187.5` (fixed SOL/USD, no network), `--no-usd`, `--ascii` (no Unicode), `--no-color` (bold / faint
only), `--interval 2` (refresh 0.5–5 s, default 1), `--budget FILE` (default `<dir>/../dip_budget_ams.json` or
`dip_budget.json`), `--load-duty X` (the initial load sleeps X × each chunk's work time; default 1 = at most ~50% of one
core), `--sound all|wins|big|off` (default all), `--notify` (desktop notification for big trades), `--no-anim`,
`--version`, `--mouse` (capture the mouse at start), `--no-links` (no OSC 8 hyperlinks). Same as the Python
dipmon's, plus the last six and `--screen`.

## dipview: the run explorer

```
╭─ RUNS ───────────────────────────────────────────────────────────╮ ╭─ AMS r27 · dip20 ──────────────────────────────╮
│    run     engine start → end (PKT)                       result │ │ ○ ENDED  time limit / max trades               │
│ ▸● AMS r27 dip20  Oct 27 3:26 PM → 5:36 PM               +0.5877 │ │ time      Oct 27 3:26 PM → 5:36 PM PKT         │
│  ● AMS r26 dip19  Oct 27 6:58 AM → 2:03 PM               +0.3005 │ │ duration  2h 10m / 2h 10m planned              │
│  ● AMS r24 dip19  Oct 26 9:47 PM → Oct 27 2:57 AM        +1.6953 │ │ result    +0.5877 SOL  +$110.15                │
```

`sudo dipview` (or `dipmon-go --view`): left, every run of the node's runs directory (`dip_rN` / `dip_ams_rN`, a
`.jsonl` and / or `.log`): the run, its engine, start → end (PKT, 12-hour; "→ now" while running) and its result; a
**green dot** = an engine process is writing it (found by its `--dip-log`, like dipmon), a **grey dot** = ended. Running
runs first, then newest first. Right, the selected run: status and how it ended, time, duration / planned, the result
in SOL and USD (at today's SOL price), per hour, pre-send (net, fills, wins, win %) and regular (net, buys → fills,
failed, wins), trades W / L, the wallet start → now, and the key config in the same five blocks. Phones: the list on
top, a short overview under it.

Keys: ↑ ↓ PgUp PgDn Home End select, **Enter** (or →) opens the run in dipmon (the same process; dipmon's `q` comes back
to the list with the selection kept), `u` SOL ↔ USD, `M` mouse on / off (with it on: click selects, a double click
opens, the wheel moves), `r` rescans now (it rescans every 5 s anyway), `q` / Esc quits.

The numbers are dipmon's own (`core.BuildView`, the same accounting to the lamport), computed in the background one
run at a time, the selected run first, with the initial load's duty (≤ ~50% of one core, nice 19 / idle I/O) and kept
as a few numbers per run: a finished run is read once (again only if its files change); a running run is followed
incrementally (every 5 s while selected, else every minute). While dipmon is open the background reads pause.
Read-only like dipmon: the run files and `/proc`, nothing else.

## The screen

```
  ams · run 27 · dip20                                          ● RUNNING  ·  4:51:07 PM PKT  ·  SOL $187.42
╱╱╱ █▀█ █▀▀ █ █ █ █ █▄ █ █▀▄ ╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱
╱╱╱ █▀▄ ██▄ ▀▄▀▄▀ █ █ ▀█ █▄▀ ╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱
  1 Overview   2 Engine   3 Regular   4 Trades   5 Health   6 Log   7 Config   8 Filters
```

The header is the REWIND wordmark in the style of Charm's Crush: blocky half-block letters with a pink → violet →
indigo gradient, violet `╱` hatching to the edges and a small pink label (`ams · run 27 · dip20`) above the start of the
word; the run status, the PKT clock and SOL/USD on its right. The full 3-row logo when the terminal has ≥ 40 rows, a
2-row one at the owner's 200x35, one gradient line on phones and short terminals, plain `REWIND` with `--ascii` /
`--no-color`. The splash (while the run loads) shows the large logo with a spinner, "loading run 27 · 43%" and a
gradient progress bar. Every time is PKT in 12-hour form ("3:26 PM", "3:26:51 PM").

1. **Overview**, a grid that fills the screen (wide: 4 panels, P&L → card → run → live; 120–179 columns: 3 + a LIVE
   strip; 70–119: compact blocks; phones: one column):
   - **RUN P&L**: the run P&L in big numerals, SOL and USD at equal size (`u` swaps which comes first); per hour;
     pre-send vs regular. When a trade closes the number rolls to its new value (a Harmonica spring) with a brief
     flash, and a small fading "▲ +0.047" toast appears in the panel's title.
   - **RUN**: status, start → end (12-hour PKT), elapsed / planned with a gradient bar; **WALLET**: est. now, start, the
     kill-switch level and distance with a gauge (green → yellow → red), dip budget left, USD next to SOL.
   - **THIS RUN** card (a trading terminal's day card), next to the hero: Profit (the winning trades' sum, green), Loss
     (red), buy / sell txns, buy / sell volume (SOL + USD; merged into the txns line when rows are short), win rate ·
     average win / loss · profit factor, one muted line `fees −x · rent +y → net z` that adds up exactly to the hero, then
     **ATH** (the highest run P&L reached, green: `ATH +0.606 SOL $113.51 · 5:29 PM`), **Low** (the lowest, red) and
     **from ATH** (now − the ATH: the drawdown at a glance). `s` switches the card, the ATH / low and the chart to
     **TODAY**: every run of the current PKT day in this node's runs directory, summed (the others are read once, gently,
     in the background). At 70–119 columns the ATH and the low sit beside the hero; on phones under the card's rule.
   - **LIVE**: pre-send fills / wins / win %, average per fill, windows armed now (a spinner), tries; QUIET skips / stops /
     the arm rule (warm-up countdown → on); regular buys / fills / fails; landing (the medians of how long after the dump
     the fills / the regular buys landed); paper vs live; the open position.
   - **CONFIG** (v3.1), five blocks side by side, each under its title (the titles row is the section's rule; inside a
     panel on tall terminals), dots green on / yellow warming up or partial / red off, the long forms where they fit:

     ```
     PRE-SEND ──────────────────────  REGULAR ───────────────────────  ROUTES & SENDING ─────────  SAFETY & LIMITS ─────────────  QUIET & PAPER ──────
     ● 0.35 SOL · 4 tries/slot        0.35 SOL · guard +5%             routes v13 · near leaders 120  kill switch 4.432 · planned 2:10  stop ● 6 slots, < 2 trades
     exit TP +10% / SL −20% / 2 slots exit TP off / SL −50% / 5 slots  sell fan-out ● · nonce ● 8  fills 49/1000 · fees 0.02/0.40  skip ●
                                      M2 gate ● · Dev list ● 0.35      skip Rakurai                engine dip20                   paper ●
     ```

     At 120 columns the short forms (`TP off SL −50% 5sl`, `kill 4.432 · plan 2:10`); when even those do not fit, one block
     a line. 70–119 columns: the badges in 1–2 lines, grouped by block with a thin bar between blocks; phones the same.
   - **Run P&L over time (SOL)** (with `s`: **Today's P&L**, from the day's first run), full width: a braille line
     (ntcharts canvas), green above zero and red below, a dotted zero line, y labels max / 0 / min, 3–5 time labels, the
     ATH and the low marked with their values (the same points as the card's), "now" and the drawdown from the ATH in the
     title; the newest point pulses once after a trade closes.
   - **LAST TRADES**, filling the rest: the Trades tab's table (below); zebra rows; a trade whose P&L just became final
     gets a green / red highlight that fades over ~2 s.
2. **Engine** (was "Pre-send"): fills / cap and fee budget gauges (per session: the caps are per engine session), windows armed, the
   result (net, realized, rent back, failed tries = count × fee, the fee check against the engine's counter, wins /
   losses, average, best / worst), exits, QUIET, paper vs live, windows skipped / disarmed / try results, sessions, and
   **LATENCY** (ms): send→seen of every seen try (p10 / p50 / p90) and the share that landed in its send block; dump→land
   of the fills and of the **bounced** tries (failed 6042 after a dump that met the drop rule: the price was back above
   the limit when ours landed), p10 / p50 / p90; the fills' send→seen and how many slots after the trigger they filled;
   a table by leader client (Harmonic / BAM / Jito / Firedancer / Agave / other): tries, same block %, send→seen,
   fills and their dump→land, bounced and theirs (medians). On r28: fills 34 ms after the dump, bounced 307 ms.
3. **Regular**: setup, P&L (fills / failed buys), fired → filled, failed buys by cause (6042 / 6001 / other) with their
   fees, exits, P&L by leader client, landing, the open position, the funnel.
4. **Trades**: every trade, newest first (`o` / `O`: any column, see below), in a scrollable table: time, T2 / RA / REG, mint
   (an OSC 8 link to its GMGN page), size, P&L SOL and USD, %, **total** (v3.1: the run P&L after this trade: the trades'
   P&L + rent back in time order, minus the failed pre-send tries' fees booked up to that trade's minute; the last row
   = the hero unless a try failed after it), exit,
   held, the latency (`d→land` ms from the dump to the landing, `s→seen` ms from the send to seen, `blk` the block:
   slots after the send, 0 = the send block; a regular buy: after the dump), `after` (a fill: slots after the trigger),
   `whale` (the trigger dump), client, path; the latency green under 40 ms, yellow to 120, red above. Size and total
   follow `u` (`size $` / `total $` in USD). 125–149 columns drop after / whale, 110–124 also held / s→seen, 90–109 also
   size and path, 70–89 also % and blk; phones keep time / type / mint / P&L / USD / exit (Enter has it all). Zebra rows, the selection highlighted with `▸`; **sort**: `o` cycles the column (time, type, mint,
   size, P&L, %, total, exit, held, d→land, s→seen, blk, after, whale, client, path; each starts descending), `O` flips
   the order, a click on a header sorts by it (a second click flips; mouse on), the sorted header is marked `▼` / `▲` in
   the accent color and the title says `sort P&L ▲` (missing values always last, ties newest first); `f` cycles all /
   pre-send / regular / wins / losses / open, `/` finds a mint (a text input), `c` copies the selected mint (OSC 52),
   Enter opens the details: the full mint (a GMGN link), a **gmgn** line and a **solscan** token line, the size (USD
   first with `u`), the latency, landed (client, leader: a Solscan account link when it is a full key, path), the window
   (try n of the window's tries, the traders between the dump and us, the dump), the trigger, buy / sell signatures as
   Solscan links (every wrapped piece of a long URL links the whole URL); a regular buy: decision / reaction / exec lag.
5. **Health**: the engine process (pid, CPU, RSS, uptime, threads), log / records freshness, RUNTIME lag, POLL-RPC-ERROR
   counts, keep-alive / connection errors per send path, disk / load / memory, dipmon's own CPU / RSS, SOL/USD, RPC
   latency per name and method.
6. **Log**: the engine log's tail in a viewport, important lines or all (`f`), wrap (`w`), End follows the tail; each
   line with its time (exact when read live, `~` = its minute in the session for lines read in the initial load).
7. **Config**: every setting, grouped under the five block titles (Pre-send / Regular / Routes & sending / Safety &
   limits / QUIET & paper), with its dot, its full text and one plain-English line, e.g. "4 tries/slot = 4 conditional
   buys sent every slot (~0.2 s) while a window is open; each fills only on a sudden ≥ 12% drop"; the wallet; the legend.
8. **Filters**: what each pre-send filter blocked and what that saved or cost us (see "Filters tab" below).

Under the tabs: the alerts strip (engine gone, kill switch near, stalled log, fees near the budget, send-path errors,
END CHECK work, …, and the end banner) and a help bar generated from the key map, with the sound mode (`♪ all` / `- muted`)
and the refresh rate. `?` shows the full help over the screen (a Lip Gloss layer).

### dip24 runs (v3.2, 10-29)

From the engine's dip24 lines (only when the log has them: r27–r35 render exactly as before):

- **No hard limits**: `DIP LIMITS: time no time limit | regular buys unlimited | ... | pre-send fills unlimited` (and
  `--minutes 0`) show as "no time limit" / "no limit": RUN `3:33 AM PKT → no time limit`, the limits block `time no
  limit`, `fills 47/no limit`; the 90%-of-max-fills alert never fires without a cap.
- **PROFIT LOCK**: the setting (`profit lock give back max(0.650 SOL, 30% of the peak profit)`, also `PROFIT LOCK ON`) in
  SAFETY & LIMITS next to the kill switch; the RUN panel's `lock` line under `kill sw.`: the peak, the level the run stops
  below (the engine's `lock: peak, floor, run PnL` status part; before its first status line computed from our P&L line:
  floor = max(−loss cap, peak − max(M, F × peak))) and the distance; an alert under 0.10 SOL; when `PROFIT LOCK: ... ->
  stopping` is logged: STOPPING / "profit lock", a red alert and `stopped by profit lock`.
- **Rolling 24 h pre-send fee budget**: the status part `fees 24 h used/budget SOL [PAUSED] [(pauses n)]` and the
  `PRESEND LIVE PAUSED (fee budget)` / `RESUMED` lines: Pre-send `fees 24 h` gauge + `PAUSED` / "pauses at the budget,
  never stops", the limits block `fee 0.04/1.00 24h [PAUSED]`, LIVE `fees 24 h PAUSED`, an alert while paused; the 80%
  warning uses the 24 h sum.
- **Regular mode** live | paper | off (`DIP REGULAR ...`, the status part `REGULAR PAPER: picks, fills, ... net`): REGULAR
  block `PAPER ·`, LIVE `regular PAPER 6 → 0 fills · net`, Regular tab `mode`, Config `Regular mode`.
- **Observatory** (log only): the `DIP OBSERVATORY ... -> file` line and the status part `OBS: sent .. dropped .. | rearm
  windows N fills N | hold | watch | mig | blink | backrun | select | race | inslot | records MB p99`: an OBSERVATORY
  section on Health (counters, queue, file; an alert on WRITE ERRORS). The .obs.jsonl is not read. The engine logs counts
  only (no re-arm paper P&L): that needs the .obs.jsonl.
- **Feeds**: names from `feeds: a, b` / `FEEDSTATUS feed=x` lines on Health (r36's log names no feeds: no line there).
- Snapshot: `limits`, `lock`, `reg mode`, `observ.` lines; `--json` a `dip24` object (dip24 runs only); build `dip24`.

### dip26 runs (v3.3, 10-30)

From the engine's dip26 records and lines (AMS run 38 on: live re-arm, the helius-ps / astralane-ps A/B); only when the
run has them. r27–r37 render exactly as before (checked on every local run, the baseline binary against the new one:
`--snapshot` text, `--json`, `--json --extra` and every tab / page at 5 sizes, finished and as running).

- **Re-arm and T2 apart.** A re-arm window's records say `"kind":"rearm"` (arm, skip, rearm_defer, disarm, try, try
  landing, fill, exit, sell, close, realized). T2's window counters (armed, armed now, skips, disarms, QUIET skips /
  stops) no longer count them (they did). The money stays the run's pre-send total (`presend` in the JSON, the run P&L
  unchanged) and the re-arm's part is split out, **T2 = all − re-arm**: fills, wins, realized, rent back (the account
  close goes with its position), failed tries (each try's landing says its kind), net.
  - RUN P&L: `split  T2 +x  regular +y` and its own line `re-arm  +z  21 fills 10 W` (medium: T2 / re-arm / regular
    lines; phones: the same two lines). LIVE: `T2` fills / W / avg, T2's windows (now / armed / tries) and a `re-arm`
    line (fills, W %, net, its windows now with the spinner, windows).
  - Engine tab: `RESULT · T2`, `EXITS · T2`, `live T2` in PAPER vs LIVE, `armed now … T2 tries n (+m re-arm)`, and
    a **RE-ARM** section: net, realized / rent back / failed tries, fills W / L avg, windows armed · now · after waiting
    · deferred · tries, `skipped` and `ended` by reason (without the `rearm_` prefix: no_holder, age, untradeable, r5,
    blocked_*; filled, expired, quiet, whale_dump, no_holder, superseded, ...), exits, best / worst (with the fill
    path), the engine's 60 s `rearm:` counters (candidates, checks, pending, sells ≥ 6%) and the observatory's paper
    re-arm (`paper re-arm` on Health too). The fee check stays every try's (the engine counts both kinds).
  - Snapshot: `pre-send` = T2 (`T2: n fills ...`) with a `re-arm` money line under it (they add up with `regular` to
    RUN P&L); `re-arm    config ... windows ... skips ... ends ... exits ... engine ... paper`; `paper ... vs live T2`;
    `RA` trades. JSON: a `dip26` object (`t2`, `rearm` with its cfg / windows / skips / ends / engine counters, `ab`).
  - Config: the **Re-arm** item (size, window dump+3 → dump+3+gap, its QUIET stop, R5, the candidate rule) from run_start
    `presend_live.rearm`, else the start line's `| REARM ON: ...`: in SAFETY & LIMITS (`● re-arm 0.65 SOL · gap 20 ·
    QUIET 6:2 · R5 off`), the Config tab (with its explanation) and the snapshot (`RA 0.65 g20 q6:2`). A re-arm fill's
    details: `RE-ARM FILL`, its dump.
- **The send-path A/B** (two or more pre-send paths in the routes, else seen in the tries): the Engine tab's **SEND
  PATHS A/B** (first on the right; the caps `60/s · 40/s a path` in its title), per path: tries; **refused**, inferred
  from the records: a window's tick missing between sent ticks is that path's refusal (the engine's rule path =
  paths[(n + w) mod len]); a run of ≥ 2 missing ticks is a pause of every path, kept apart; landed (not unseen); same
  slot (`slots_after_send` 0 of the seen); send→land p50 / p90 (`ms_send_to_rx`); acks ≠ 200 (another status, 0 = no
  answer, or none recorded; the codes listed); fills by the filling try's path and their realized P&L. Then the
  engine's `not-sent` (all paths), by leader client (seen, same slot, p50 for each path), the paths' SEND-PATH state.
  Narrower terminals drop columns; phones use HL / AS with a legend. The engine's `per path sent/ok/6042/...` and `acks
  {...}` parts are kept (JSON). On r38's first 38 minutes: astralane-ps refused 296 of its 4,695 ticks (6.3%; the
  engine's `rate_path_config` 381), helius-ps none.
  - Alerts (while running): `<path> refused x% of its tries in 10 min (n of m)` above 1%, `<path> acks failing: n of m
    not 200 in 10 min` above 1%, `<path> UNHEALTHY: ...` while its last SEND-PATH edge is UNHEALTHY.
  - Trades: a **via** column (the fill path: HL helius-ps, AS astralane-ps) before client from 80 columns (sorts as the
    path; `type` sorts T2 / RA / REG apart); the snapshot's last trades end with `via AS`.
  - Health: `A/B paths  helius-ps ok · astralane-ps recovered (1 unhealthy / 1 recovered)`. SEND-PATH UNHEALTHY lines
    count as the path's errors like every path's (astralane-ps's too: the table, the 3-in-10-min alert); RECOVERED
    lines are no error and set the path's state.
  - Config: the **Send-path A/B** item in ROUTES & SENDING (`● A/B helius-ps / astralane-ps`).
- dipview: `T2` and `re-arm` lines; `--list` says `fills 44 (23W; re-arm 21, 10W)`. The help (`?`) has a re-arm and an
  A/B note on dip26 runs.
- CPU: O(1) a record (the tries and their landings still read by substring); the A/B summary (its percentiles) is rebuilt
  at most every 5 s while the Engine tab shows it (0.8 ms on r38's 38 minutes); an old run's load is unchanged within
  noise (r37, 145 MB: 0.53 → 0.55 s CPU).

### Filters tab (key `8`, 10-30)

The owner: "how many winners and losers we skipped live, with their reason and how much each filter +- saved us or cost
us". A port of `ops/strategies/presend/prevent/forward/filters_report.py` (equal to it to 1e-9 SOL on run 40, tested)
and of `loss_brief.py`'s per-fill rules (`internal/core/filters.go`, `internal/ui/filters.go`).

- **Table**, one row per filter, tagged **LIVE** (it changed what the engine did) or **LOG** (log only, would-have):
  filter | **verdict** | **net saved** = minus what the blocked would have made (green = saved us money, red = cost us) |
  **prec** = the losers among the marked items that have a value, % (green >= 60%, yellow >= 50% = a coin flip, red below) |
  blocked | would win n / SOL | would lose n / SOL | why (the verdict's reason; >= 113 columns). 76–99 columns: the
  counts without the SOL sums; phones: 4-cell verdicts (`NEW` = LIVE new, `LV32` = LIVE dip32, `DISM`). **Verdicts (11-03)**
  come from FILTERS-3 (`ops/strategies/presend/filters3/tune/tune.json` "verdicts", `build/DIP32.md`), one table in
  `internal/ui/filters.go` (`fltVerdicts`, key → group + label + a 3–6 word reason, easy to edit): create-slot / QUIET /
  age-1 / 10-sec = KEEP; circuit breaker / creator loss = LIVE new; bad creator = LIVE dip32 (superseded by the live
  creator ledger); creator unfollowed / group risk / QUIET3-A / fresh holders = LOG; safe sell timer / holder clock /
  landing guard / ctx85 = DISMISSED; the deeper limit has none (`–`). The **`QUIET3-A (log)`** row is left out when QUIET3-A runs live (the
  run_start's `presend_live` has `"quiet3a": true`, or the run has a `quiet3_a` skip): the log rule can then never fire
  (it stays only if it marked a fill anyway). Rows sort by verdict group (KEEP / LIVE first, then
  LOG, then DISMISSED) and by net saved within a group; the DISMISSED rows fold into one line (`▸ 3 DISMISSED  d show`:
  their net, W / L summed over the rows) that `d` expands. The LIVE / LOG tag still says how this run used the filter
  (it decides paper vs real fills and which unique total it is in). A two-line legend under the totals: net / prec /
  verdict, then how LIVE and LOG rows are scored (and the bad-creator seed). LIVE rows are a **paper estimate**: QUIET / create-slot / age-1 / 10-sec skips of a T2 trigger
  scored on the main shadow's window on the same trigger (row c `net_cheap`, scaled live size / shadow size); the
  **deeper limit** (only when the run used it) = T2 windows that tried below 0.875x and never filled, scored the same
  way, plus a line with its deep fills' real P&L vs their shadow paper (the gain) and its NET = blocks + gain. LOG rows
  are scored on the **real fills** (`presend_live_realized`): bad creator (with the ledger seed; without one "this run
  only"), safe sell timer, group risk, holder clock (approx), ctx85 (only without the deeper limit) and the **landing
  guard** (`ann.guard.block`, dip30+; older runs show `n/a (dip30+)`).
- **Totals are unique (10-31)**: the rows count a trigger / fill once per rule that has it, so the totals do not add the rows.
  **LIVE total (unique triggers)** = each skipped / refused trigger once (by trigger sig; on r40 / r42 the LIVE rows turn out
  disjoint, the dedupe guarantees it), **LOG total (unique fills)** = each real fill (w, mint) once, whatever number of LOG rules
  flagged it (the rule rows overlap heavily: r42 has 16 flagged fills but the five-six rule rows add up to 34), and
  **ALL total** = LIVE + LOG. The two sets are disjoint (a skipped trigger never became a fill), so ALL is their plain sum;
  LIVE is paper, LOG is real fills, so it is an estimate. The per-row numbers are unchanged. `--snapshot` prints the three
  lines; `--json` has `live_total`, `log_total` (now unique), `all_total`, `live_total_rowsum`, `log_total_rowsum`,
  `live_dup`, `log_dup`. `filters_report.py` prints the same three lines last (`LIVE total (unique triggers)` ...), tested
  against Go on r40 (fixture and full file).
- **Trades: yellow dot and `x`**: a real position that at least one LOG rule would have blocked has a yellow `●` (`*` with
  `--ascii`) in its own 1-cell column after the selection marker (the overview's LAST TRADES too, 11-03: first column) (only when the run has flags; on a table too tight for it the dot
  replaces the last cell of the type column). `x` (Trades) shows a **BLOCKED BY** panel under the table for the selected trade: every
  rule with its numbers, e.g. `safe sell timer (holder 5ThrZRSQ 7.5%, hz3 0.91) · group risk (11.1% = 5ThrZRSQ 7.5% +
  85YwZaQa 3.6%) · holder clock (holder 5ThrZRSQ 7.5%, h3 0.90) · landing guard (guard set 15.5% at landing)`; an unflagged
  trade says `no filter would have blocked this trade`. The trade's details (Enter) show the same under `blocked by`. The dot, `x`,
  the details and the Filters list all read the same `FiltReport.Flag(w, mint)` item (one source of truth). LIVE-blocked triggers
  are not trades: no dot.
- **Shadow rows (`v`)**: the skip list hides the LIVE rows (scored on the shadow window) by default, with `+N shadow (v)` in its
  header; `v` shows them. Picking a LIVE filter / `LIVE` with `f` shows them regardless. The list's W / L / SOL follow what is
  visible; the table above always counts everything.
- **Skip list** (newest first; `o` / `O` sort like Trades): time, LIVE / LOG, the filter, T2 / RA, the mint (GMGN link),
  WIN / LOSE, SOL, and for LIVE rows **move** (11-03). A LIVE skip whose shadow window never filled is **`no dip`** with SOL
  `0.000` (dim: the trade would not have happened, nothing saved or lost; it sorts as 0 between WIN and LOSE); `n` shows /
  hides these rows as before. **move** = the shadow window's price move from the engine's shadow `presend_disarm` record
  (`"move": {"max_pct", "min_pct", "n"}`: the highest / lowest price, % vs the trigger's post price, over the token's
  trades in the window), found like the score (trigger sig -> shadow w), shown rounded `+35/-8%` (`0` unsigned), `0 trades`
  when nothing traded, `–` when the record has no "move" (runs before the engine logged it); blank on LOG rows; the column
  is there only when the list has a LIVE row (`v`, or `f` LIVE / a LIVE filter) and the screen has >= 76 columns. A LOG row is one real fill with **every** rule that would have blocked it, e.g. F36E6Xcs (-0.121):
  `safe sell timer, group risk, holder clock` (phones: `ST+GR+HC`). `f` filters by LIVE / LOG / one filter, `n` adds the
  blocked items that would not have filled (no shadow fill), `enter` opens a LOG item's trade, `c` copies the mint.
- Live: the table follows the .jsonl as it grows (recomputed only when a filter record came).
- `--snapshot`: a `filters` section (the script's table, the deeper-limit gain, the totals, the latest 5 LOG blocks);
  `--snapshot --json`: `filters` with `rows` (a not-logged rule has `na: true` and null numbers), `deep`, the totals and
  `items` (every scored skip / block with its `rules`).
- Tests: `internal/core/filters_test.go` (r40 trimmed to the records the table reads, `testdata/filters`, against the
  script's rows at full precision with and without a seed; `DIPMON_R40=path` also checks a full run file; F36E6Xcs
  appearing live; the landing guard on synthetic dip30 records), `internal/ui/filters_test.go` (golden screens, keys).

## Keys

| key | action |
|---|---|
| `1`–`8`, Tab, Shift-Tab, a click on the tab bar (mouse on) | tabs: Overview, Engine, Regular, Trades, Health, Log, Config, Filters |
| `f` / `n` (Filters) | the skip list: all → LIVE → LOG → each filter; `n` shows / hides the LIVE skips whose shadow window never filled (`no dip`, SOL 0.000); `v` shows / hides the shadow-window (LIVE) rows |
| `d` (Filters) | the table's DISMISSED filters: one summary line (count + their net summed) ↔ their rows |
| ↑ ↓ PgUp PgDn Home End, the mouse wheel (mouse on) | scroll (Trades: move the selection; Log: End = follow the tail again) |
| Enter / Esc, a click on a trade (twice: details; mouse on) | Trades: details of the selected trade / back |
| `f` | Trades: all → pre-send → regular → wins → losses → open; Log: important ↔ all |
| `o` / `O` | Trades: the next sort column / flip the order (the header shows it) |
| `x` (Trades) | which filters would have blocked the selected trade (the yellow dot ●): a BLOCKED BY panel under the table |
| `c` (or `y`) | Trades and the details: copy the selected mint to the clipboard (OSC 52; tmux needs `set -g set-clipboard on`) |
| `M` | mouse capture on / off (default off: the terminal selects text and opens links; on: tab clicks, the wheel, row and header clicks) |
| `/` | Trades: find a mint (Enter keeps the filter, Esc clears it) |
| `w` | Log: wrap long lines |
| `s` | the card's scope, with its ATH / low and the chart: this run ↔ today (all runs of the current PKT day on this node) |
| `S` | session scope: all sessions → session 1 → 2 … (a run restarted into the same log has several) |
| `u` | swap the primary unit (SOL ↔ USD) |
| `p` | pause the screen (data keeps loading; closed trades still ring) |
| `r` | refresh the SOL/USD price now (a spinner until it arrives) |
| `+` / `-` | refresh faster / slower (0.5, 1, 2, 3, 5 s) |
| `a` | animations on / off (`--no-anim` starts with them off) |
| `m` | mute / unmute the bell |
| `?` / `q` | help / quit |

## Selecting, copying and links (v3.1)

Mouse capture is off by default, so the terminal's own selection works (drag to select, the terminal's copy) and so do
its link clicks: in Ghostty (and iTerm2 / kitty / WezTerm) Ctrl-click (Linux) / Cmd-click (macOS) opens an OSC 8 link
(mints → `https://gmgn.ai/sol/token/<MINT>`, signatures → Solscan `tx`, the token → Solscan `token`, a leader's full key
→ Solscan `account`); the details also print the full URLs, which the terminal's plain URL detection finds as well.  With
capture off, terminals that use alternate-scroll mode turn the wheel into ↑ / ↓ (moving the selection). `M` turns capture on (tab / row / header clicks, the wheel); while it is on, Shift-drag (most Linux terminals)
or Option-drag (iTerm2, Terminal.app) still selects. `c` writes the selected mint to the clipboard with OSC 52 (Ghostty,
iTerm2 with "Applications in terminal may access clipboard", kitty, WezTerm, Windows Terminal; through SSH too; tmux:
`set -g set-clipboard on`). Terminals without OSC 8 show the text without the link; `--no-links` leaves the links out
(as do `--ascii` and `--no-color`).

## Sound

One terminal bell (BEL) per closed trade, the only sound that reaches your own terminal over SSH; at most one bell per
2 s (a burst of closed trades is merged into one bell); never for the trades read at start. `--sound all` (default),
`wins` (P&L > 0), `big` (|P&L| ≥ 0.03 SOL) or `off`; `m` mutes; the footer shows `♪ all` or `- muted`. `--notify` also sends
a desktop notification (OSC 9) for big trades.

- **Mac**: System Settings → Sound → Alert sound: pick **Pop** (short and quiet), alert volume to taste.
  **Terminal.app**: Settings → Profiles → Advanced → Bell: tick **Audible bell** (untick "Visual bell" if you only want the
  sound). **iTerm2**: Settings → Profiles → Terminal → untick **Silence bell** (and choose "Show bell icon in tabs" if you
  like); `--notify` notifications appear in Notification Center.
- **Phones**: Blink / Termius / JuiceSSH vibrate or beep on BEL depending on their notification settings.
- tmux passes the bell on with `set -g bell-action any` (and `visual-bell off`).

## Accounting (= the Python dipmon v1 = `ops/dip/report/make_run_report.py`)

All sums in lamports, per engine session, then summed (the definitions are the Python dipmon's, line for line):

- **pre-send net** = Σ `presend_live_realized.pnl` + Σ `presend_live_ata_close.delta` (ok ones: rent back) − failed-attempt
  fees (Σ `presend_attempt_land.fee` where `res != "ok"`; the larger of that and the engine's own counter is used).
- **regular** = the log's `REALIZED mint=… pnl=…` of each filled buy (matched to that mint's buys in order) + every failed
  buy at its tx fee (the landed buys' fee, 505,000 lamports). A fill without its REALIZED line yet shows the feed estimate,
  marked `~`.
- **run P&L** = pre-send net + regular; **per hour** = run P&L / the time since the first session started.
- **wallet now (est.)** = the current session's START BALANCE + its P&L; **kill-switch distance** = that − the kill level.
- **The card** (v3): Profit = Σ of the winning P&Ls (each pre-send realized record, each regular fill), Loss = Σ of the losing
  ones, rent = the pre-send rent back, fees = the failed tries' fees (as above) + the failed buys' fees; so
  `Profit − Loss + rent − fees` = the run P&L exactly. Buy / sell txns and volume are the landed records: `presend_live_fill`
  (`sol_in`) + `buy_land` (`sol`), `presend_live_sell_land` + `sell_land` (`sol`). **Today** books each item in its minute
  (a fill's P&L and rent at its booking minute, a failed try at its try, a failed buy at the buy, the engine's extra fee count
  at the session's end), so its card adds up the same way and equals what the runs booked that day.
- **ATH / Low** (v3) are the highest / lowest points of the cumulative P&L a minute that the chart draws (the first minute at
  that value; the run's series is the Python dipmon's, its `series_hi` / `series_lo`), **from ATH** = the series' last point −
  the ATH. The day's series adds every run's minute bookings (as Today's card) from the first run's start that day (midnight
  at the earliest) and ends at the day card's net.

## Latency (v3, display only: no money figure uses it)

| | pre-send fill (its filling try's `presend_attempt_land`, by sig) | regular buy |
|---|---|---|
| d→land | `ms_after_d_a` (else `ms_after_x_a`) | `buy_land.rx_ms_after_dump`; a failed buy: the timing record's `buy_first_rx − dump_first_rx` (the same clock: within ~1 ms of `rx_ms_after_dump` where both exist) |
| s→seen | `ms_send_to_rx` | the timing record's `fire_to_seen_ms` (t_fire → our buy seen) |
| blk | `slots_after_send` | `buy_land.slots_after_dump`; a failed buy: the timing's `clock2.buy_slot − dump_slot` |
| details | client (the landing leader's), leader (its `presend_attempt`), path, try `n` of the window's sent tries, `n_between`, the dump's drop / price | client, leader, route, path, decision / reaction / exec lag |

The Engine tab's summary reads every `presend_attempt_land` by substring (never decoded; 15,771 in r28): every seen
try's send→seen and `slots_after_send`, and for the fills (`res` ok) and the 6042 tries the dump→land when the dump in
the record met the drop rule (`d.p_rel ≤ 1 − presend_live.drop`, 0.88 for 12%), by the leader client family. Memory
stays bounded: sparse histograms (0.1 ms buckets below 1 s; quantiles interpolate like numpy's default, the median of
an even count = the mean of the middle two).

## Safety

Reads only: the two run files, the budget file, the other runs of the day (Today, on `s`; dipview: every run file of
the directory), `/proc` (the engine's cmdline /
stat / statm, meminfo, loadavg), statfs. Never writes to them, never sends a signal, never calls an RPC, never opens `.env`,
keystores or configs. Only a fixed list of numeric / name flags of the engine's command line is kept (never paths, URLs or
keys); log lines are cleaned (control / wide / emoji characters, `key=` / `token=` / `user:pass@` masked) before display.
Incremental tails (offset kept, a partial last line held until its newline, truncation / replacement → a clean reload);
the high-volume records (tries, try landings, dumps, tapes, shred records) are counted by substring without a JSON
decode; memory is bounded (aggregates, the trade list, 3,000 log lines). The initial load reads 512 KB chunks and
sleeps after each (≤ ~50% of one core). The price: Binance, then CoinGecko, every 60 s, 5 s timeouts, cached in
`/tmp/dipmon-solusd-<uid>.json` (shared with the Python dipmon).

## Charm components, and where

- **Lip Gloss v2** (the backbone): every style and the adaptive light / dark palette (`LightDark`, from Bubble Tea's
  background-color query); rounded borders for the panels (with their titles set into the top border); `JoinHorizontal`
  / `JoinVertical` / `Place` / `PlaceHorizontal` for the grid and the splash; `Blend1D` for the wordmark's gradient, the
  progress bars, the fading row highlight and toast, and the chart's pulse; the **table** renderer for the trades (zebra
  rows, the selection, per-cell green / red) and the small tables (exits, clients, send paths, RPC latency, sessions); the
  **layer compositor** for the help screen over the frame; hyperlinks for solscan.
- **Bubble Tea v2**: the program (alt screen, mouse cell motion, window title as declarative `tea.View` fields), the
  background-color query, `tea.Raw` for the bell and OSC 9, `WithFPS(15)` (the renderer's frame cap; an unchanged
  frame is not redrawn).
- **Bubbles v2**: `help` + `key` (the help bar and the `?` screen are generated from the key map, per tab), `spinner`
  (loading, the price refresh), `progress` (gradient bars: run time, fills / fee budget, kill-switch distance, the splash),
  `viewport` (the Log tab), `textinput` (the `/` mint search).
- **Harmonica**: the hero number's spring when a trade closes.
- **ntcharts v2**: the P&L line (its canvas and braille grids, one per sign), drawn once per change and cached.

## Performance

Measured by `tests/perf.py` on this dev machine (AMD Ryzen 7 9700X), 80x24, 1 s refresh, the default load duty, the
Python dipmon v1 measured the same way (`--python`):

| case (CPU = % of one core) | Go dipmon v3 | Python dipmon v1 |
|---|---|---|
| initial load, AMS r24 (59 MB records + 2.2 MB log) | 0.75 s wall, 0.26 s CPU, peak 48% | 0.75 s wall, 0.27 s CPU, peak 48% |
| after the load, finished run, 60 s at 1 Hz (r24 / r26) | 0.127% / 0.119%, RSS 27 / 25 MB | 0.141% / 0.120%, RSS 41 / 40 MB |
| following r26 live at the engine's rate (1x, fake engine) | 0.159%, RSS 24 MB (`--no-anim`: 0.153%, the same within noise) | 0.118%, RSS 40 MB |
| following at 10x the rate (a stress case: a trade closes every few s) | 0.404%, RSS 25 MB | 0.139%, RSS 40 MB |
| `--snapshot` on r24 | 0.41 s wall, 0.21 s CPU, max RSS 23 MB | 0.80 s wall, 0.30 s CPU, 40 MB |

(With the latency: reading every try's landing by substring adds ~8% to the initial load and ~2 MB of histograms; a
run measured while the machine was busy with other jobs gave up to twice these CPU figures, so compare on a quiet
machine.)

Half the memory and half the snapshot time of the Python dipmon; the steady CPU is the same order (~0.12–0.15% of a
core; Bubble Tea's 15 fps frame ticker is most of Go's idle cost). At 10x the closed trades keep the highlight / toast
/ pulse animating most of the time (the Python dipmon has none); still far under the 2% target.

Animations run at 15 frames a second, only for ~2 s after a trade closes; otherwise one redraw a second, and a redraw
reuses the body (and the chart, the trades table, the config grid and the bars) when nothing it shows has changed. On the AMS node (2 cores, both busy with the engine) each
operation is slower and nice 19 makes dipmon wait for the engine; the steady state stays far below the 2% target.

## Tests

```sh
sh ops/tui-go/run_tests.sh       # everything (QUICK=1: follow at 200x; FOLLOW=0 / PERF=0 skip those; PERF_PY=1 adds Python)
```

- `go test ./...`: the tail (partial lines, truncation, replacement, small chunks) and a concurrent writer under `-race`;
  Python-exact formatting (float repr, rounding, thousands, `json.dumps` escapes, PKT times, wrapping); garbage / broken /
  huge lines never panic; **the card on every local run**: `profit − loss + rent − fees == the run P&L` and the buy / sell
  counts and SOL equal the records (scanned independently with `encoding/json`); **Today** on every AMS day: adds up and
  equals the minutes' bookings; **ATH / low** on every run and session scope: the series' first extremes = the Python
  dipmon's `series_hi` / `series_lo`, the JSON fields equal, from ATH ≤ 0; **the day's series** on every run's day:
  minute by minute equal to an independent sum of every run's bookings, ending at the day card's net; **latency** on r27
  and r28: every figure of the Engine tab's summary (all and per client family: counts, blocks, p10 / p50 / p90) and every
  fill's / regular buy's own latency against an independent `encoding/json` scan of the records, r28's medians against
  the owner's measurement (fills 34 ms, bounced 307 ms after the dump); **golden screens**: 11 pages (7 tabs, help, a
  trade's details, the splash, the today card) × 5 sizes (200x35, 160x50, 120x40, 80x24, 50x30) of r27, and r28's
  Engine / Trades / details, every frame exactly filling the terminal; `--ascii` pure ASCII and `--no-color` without
  colors on every page and size; **resize + keys + mouse** through 18 sizes down to 1x1 (no panic); **a run followed
  live** (r27 split in two): highlights, toast, pulse, hero spring, the bell (rate-limited, never in the load) and the
  final numbers.
- dip24 (v3.2): `TestDip24Lines` / `TestDip24Variants` / `TestNoDip24OnOldLines` (core: real r36 lines + the pause /
  resume / lock-fire lines in the engine's format; capped / lock-none / regular off; a dip20 log gets none of it) and
  `TestGoldenDip24` (ui: r36 frozen copy in `/home/it/sniper-data/tui/runs-dip24`, overview / pre-send / regular /
  health / config × 5 sizes = `testdata/golden/r36_*`, the dip24 figures on them, `--ascii` pure ASCII).
- dip26 (v3.3): `TestDip26Lines` (real r38 start / status lines: the REARM ON setting, the caps, the `rearm:` /
  per-path / not-sent / acks parts; SEND-PATH UNHEALTHY / RECOVERED for astralane-ps and helius-ps in the engine's
  format), `TestDip26Slice` (80 real r38 records in `internal/core/testdata/dip26_r38_slice.jsonl`: every T2 / re-arm /
  A/B figure, the sums, the trades' sizes and paths, items, snapshot, JSON), `TestDip26Gaps` (the refused-tick rule and
  the 10-minute alert), `TestDip26R38` (the frozen copy of r38's first 38 minutes in
  `/home/it/sniper-data/tui/runs-dip26`, md5 de03d4c9 / 8c4a4524, against an independent `encoding/json` scan: T2 /
  re-arm money and counters, every A/B figure per path, fills and P&L by fill path), `TestNoDip26OnOldLines`,
  `TestGoldenDip26` (overview / pre-send / trades / health / config / details × 5 sizes = `testdata/golden/r38_*`,
  content checks, `--ascii`), `TestDip26ResizeKeysSort` (21 sizes, keys, the type / via sort, the help notes).
- `go test -race ./internal/...`: the tail and reader, the price goroutine, the UI.
- `tests/parity.py`: Go `--snapshot --json` == the Python dipmon v1 (pinned in `tests/oracle/`, md5-checked) on every field
  of every local run (AMS r9–r28, FRA r1–r25; r28 from `/home/it/sniper-data/tui/runs`), the text snapshots line by
  line, and running copies (`--assume-running --now`, incl. the dip20 QUIET lines) byte for byte; the v3-only ATH / low fields and text line are checked against the
  oracle's own `series_hi` / `series_lo` and then left out of the comparison.
- `tests/follow.py`: AMS r26 and r27 replayed at 50x into a temp dir with a fake engine process (dipmon finds it by its
  `--dip-log`) and records split before their newline; the UI follows in a pty (`tests/ptygo.py` + `tests/vt.py`, a small
  VT screen) while keys are pressed; snapshots every 15 s (status, counts never go backwards); at the end the UI's own
  numbers (`--exit-json`), a final snapshot, the Go and the Python snapshots of the finished file are equal; every trade
  closed after the load rang (one bell per 2 s at most, bursts merged), none of the loaded ones did, and the BEL bytes on
  the pty match. First a copy whose engine dies before DIP DONE must show ENGINE GONE.
- `tests/perf.py`: the CPU / RSS figures above.

Last full run (2026-10-30 ~02:50–03:15 PKT, v3.3, `sh run_tests.sh`, on a busy machine: load average 5–14 from other jobs):

- build: static, `sha256 bdbe7ab4e6f64ceeacd898eaee03cf6c30903c023918fdd2e7d224f82580e5e8`; `go vet` clean; `gofmt` clean.
- `go test ./...`: core + ui pass: the older goldens unchanged (r27 55, r28 15, r36 25 screens), the new r38 ones (30) and
  the dip26 tests above. `go test -race ./internal/...`: pass.
- parity: 50/52 runs identical; AMS r36 / r37 differ from the Python v1 oracle on dip24 fields only (the build `dip24`
  vs `dip20`, `no limit` vs `?`, the dip24 config items and `dip24` JSON object; every money field equal): the same
  with the previous binary (since the dip24 support, 10-29).
- dipview in a pty: ALL PASS. follow at 50x: r26 / r27 pass.
- perf: PASS (r24 load 0.39 s CPU, after 0.16% of a core; following 1x 0.17%, 10x 0.40%; `--snapshot` 0.24 s CPU; the
  previous binary measured right after: 0.28 s, 0.15%, 0.18%, 0.42%, 0.52 s: machine noise either way).
- before / after on every local run (53: AMS r9–r37, FRA r1–r28, r28 and the r36 frozen copy), the previous binary vs
  this one: `--snapshot` text, `--json`, `--json --extra` and every tab / page at 5 sizes (+ 2 sizes as running):
  identical but for the help's corner (`dipmon 3.1` → `dipmon 3.3`) and, on FRA r25 / r27, the order of two Health
  send paths with equal totals (it comes from a Go map: the previous binary alone flips it between runs).
- AMS (read-only, `/tmp/dipmon-go.new`): `sudo /tmp/dipmon-go.new --run 38 --snapshot` on the live run, 0.38 s CPU, 20 MB.

Previous full run (2026-10-28, v3.1, `DIPVIEW_DATA=<real FRA + AMS run files copied read-only> sh run_tests.sh`):

- build: static, reproducible (`sha256 fb9bf0fbcbb5afacd5efabf0b47a9c8e2d5a729f9591c36a3751b80324335aaf`); `go vet`
  clean; `gofmt` clean.
- `go test ./...`: core + ui pass: the goldens (55 + 15 screens, re-made for v3.1 and reviewed), resize + keys + mouse
  through 18 sizes incl. `o` / `O` / `c` / `M` / `u`, and the v3.1 tests: **sort** (every column × both orders on r27:
  rows ordered by the key's value, missing last; the default = the old newest-first order; `o` ×4 + `O` = P&L
  ascending, shown in the header and the title; a header click), **running total** (on all 39 local runs: the last
  trade's total + the fees booked after it = the run P&L, to the lamport), **unit switch** (size `$65.60`, total
  `+$110.19`, `size $` / `total $` headers, back with `u`; the overview's last trades too), **config blocks** (overview +
  Config tab at 80 / 120 / 200 columns: the five blocks, every field of the old grid, nothing wider than the terminal,
  every config item in a block), **links / copy / mouse** (r28: the mint's GMGN OSC 8 link in the table, GMGN + Solscan
  token + buy tx links in the details, `--no-links` none, mouse off by default and on with `M`, `c` → clipboard),
  **dipview** (real run files of both nodes and a log-only run: every run listed, names / regions / order, each run's
  numbers = dipmon's `BuildView`, the screens fit at 200x35 / 120x40 / 80x24 / 50x30, Enter picks the run).
- `go test -race ./internal/...`: pass.
- parity: identical to the Python dipmon v1 on every local run (money untouched by v3.1).
- `tests/dipview_pty.py` (a real pty): the list, the overview, no mouse capture, Enter → dipmon, OSC 8 GMGN links in
  Trades, OSC 52 on `c`, `M` turns capture on, `q` back to the list, `q` quits (exit 0): ALL PASS.
- follow at 50x: r26 / r27 pass (the pty's VT helper now holds OSC strings longer than 64 bytes across reads: an OSC 8
  link cut by a read had made its terminating BEL count as a bell).
- perf: PASS (load 0.75 s wall / 0.25 s CPU on r24; after the load 0.12% of a core, live 0.15%, 10x 0.40%; RSS 23–26 MB).
- on the nodes (10-28): FRA `sudo dipview --list` read all 27 runs (≈ 350 MB) in 12 s wall / 6 s CPU at nice 19
  (r27 shown RUNNING with the green dot); AMS the same; `sudo dipmon --snapshot` unchanged.

## Build

`sh ops/tui-go/build.sh` → `/home/it/sniper-data/tui/dipmon-go` + `.sha256`: Go 1.27.2 (user-local in
`/home/it/tools/sdk/go`, the official tarball, its sha256 checked against go.dev's), `CGO_ENABLED=0 GOOS=linux GOARCH=amd64`,
`-trimpath -ldflags "-s -w -buildid="`, `-mod=vendor` (`vendor/` holds every module, pinned in `go.mod`), `GOPROXY=off`:
the same sha256 on every build. Modules: `charm.land/bubbletea/v2` v2.1.0, `charm.land/lipgloss/v2` v2.0.6,
`charm.land/bubbles/v2` v2.2.1, `github.com/charmbracelet/harmonica` v0.2.0, `github.com/NimbleMarkets/ntcharts/v2`
v2.8.0 (each the newest stable release at least two weeks old).

Layout: `main.go` (the command line), `internal/core` (tails, the model, the accounting, the view, the snapshot / JSON, the
engine / price / system probes, the card and today; `dip24.go`, `dip26.go`: those engines' lines and records),
`internal/ui` (the app, the theme, the wordmark, the screens, the chart, the trades table and its sort / running total
(`sort.go`), the config blocks (`cfgblocks.go`), dipview (`dipview.go`), the re-arm / A/B sections (`dip26.go`)), `tests/` (parity, follow, perf, the pty and VT helpers, the pinned oracle, `ans2png.py`), `screens/`
(`sh make_screens.sh`: text screenshots of every tab of r27 ended / live / warming up, colored `.ans` copies, and `png/`
images of a few for a phone: DejaVu Sans Mono on a dark background, roughly what a terminal shows).

## Known gaps

- Not yet run on the nodes: the CPU / RSS figures are from this dev machine; the 2-core AMS node is slower and busy, and
  nice 19 / idle I/O keep dipmon behind the engine there.
- Bubble Tea's renderer ticks at its frame rate (15 a second) even when idle (it skips unchanged frames): about 0.07%
  of a core of the idle cost. `DIPMON_FPS=n` overrides it (diagnostics).
- The palette follows the terminal's answer to the background-colour query; a terminal (or an old tmux) that does not
  answer gets the dark palette.
- The mouse is not captured unless `M` / `--mouse` (v3.1): without it tab / row / header clicks and the wheel's
  scrolling are the keyboard's (the terminal may turn the wheel into arrow keys).
- The running total subtracts the failed pre-send tries' fees by minute (they are booked per minute): within a minute the
  first trade carries that minute's fees; a try failed after the last trade shows only in the hero.
- dipview's USD is at today's SOL price (the price of the run's time is not recorded); its first look at a large
  directory reads every run once in the background (FRA's 27 runs, ≈ 350 MB: ~6 s of CPU at nice 19).
- `--notify` (OSC 9) works in iTerm2, WezTerm, kitty, Ghostty and Windows Terminal; Terminal.app ignores it; inside tmux it
  needs `set -g allow-passthrough on`.
- Log lines read in the initial load carry only their minute (`~4:32 PM`); lines that arrive live carry the exact time.
- Today (the `s` scope) covers this node's runs directory only (AMS or FRA, not both).
- Latency needs the engine's newer records (`ms_after_d_a`, `ms_send_to_rx`, `slots_after_send`, the timing record):
  older runs show `–`. A fill whose try's landing record is missing shows its fill record's send→seen only. The tries'
  leaders are kept for the last 1,024 tries (a fill follows its try within a few records).
- The v1 oracle has no card, Today, USD balances or ATH / low: those are checked by identities (profit − loss + rent −
  fees = P&L, the records' counts and SOL, the day's series = an independent sum of the bookings, ATH / low = the
  oracle's `series_hi` / `series_lo`), not against a second implementation.
- A regular trade's minute on the P&L line follows the Python dipmon (the minute its REALIZED line was read, which depends
  on how far the records file had been read): the same as v1, and the day's chart reads the other runs in the same
  512 KB chunks so their minutes match their own runs' charts; live, the minute is the minute it arrived.
- Golden screens freeze the system probes (pid 4242, fixed disk / memory) so they stay stable; the Health tab's live
  values are exercised by the pty tests, not by the goldens.
- The big digits and the wordmark use half / full blocks (▀▄█): phone fonts with poor block glyphs look rough; `--ascii`
  switches to plain digits and a plain "REWIND".

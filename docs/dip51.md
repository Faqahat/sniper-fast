# dip51: DENSE FRONT (11-17)

(Named dip51: dip50 is the separate GRX build of 11-12, branch dip50-grx, staged for r91 but never run. dip51 is built on dip49c, not on dip50.)

More tries per slot in a window's first slots, where most dips land. Off by default: with no dip51 flag the engine writes exactly dip49c's
records (the six golden tests pass unchanged).

## Why (r92 wintrack, full run, 1,280 dips)
* T2 dips come a median 556 ms after the trigger; 627 of 773 within 800 ms, holding +27.2 of the +32.1 SOL best case.
* 158 dips had our tries land before AND after with none inside. Those dips stay open a median 5 ms (p75 10 ms); at 20 tries per slot
  our tries are 20 ms apart.
* The engine refused more than 20 tries per slot (`--presend-live-k` 1..20).
* Re-arm dips are spread over ~5 s (median 1,187 ms), so the front is T2-only by default.

## Flags
| Flag | Values | Default | Meaning |
|---|---|---|---|
| `--presend-live-front SLOTS:K` | SLOTS 1..10, K 1..50 and >= `--presend-live-k` | off | a window's first SLOTS slots (from its first try) pace at K tries per slot, then `--presend-live-k` |
| `--presend-live-front-kinds` | `t2` / `rearm` / `t2,rearm` | `t2` | which windows get the front (needs `--presend-live-front`) |

Example: `--presend-live-k 10 --presend-live-front 3:40` = 40 per slot (10 ms apart) for 3 slots, then 10 per slot: 190 tries per
10-slot T2 window against 200 at k 20, twice as dense where the dips are.

## What it does not change
* The rate caps. A dense window takes its tries from the same global / per-lane buckets; refusals are counted as before
  (`rate_global`, `rate_path`, `rate_path_config`). One front window at 40/slot = 100 tries/s, so with `--presend-live-max-per-sec 100`
  a second window armed at the same time is refused part of its tries (re-route moves only lane refusals).
* Fees per failed try. More tries in the front = more failed-try fees unless `--presend-live-k` is lowered for the later slots.

## Records
* `presend_live_arm` (T2 and re-arm) carry `"front": [slots, k]` when that window paces dense; absent otherwise.
* `run_start` config carries `"d51": {slots, k, t2, rearm}` only when on.
* The start line ends with `DIP51 DENSE FRONT: first S slot(s) of each <kinds> window at K tries/slot, then --presend-live-k`.

## Code
* `src/presend_live.rs` `Pace::with_front` / `iv_at` (`Pace::new` unchanged: front_until 0).
* `src/bin/snipe_engine/ps51.rs` (flags, `front_for`, start-line text); `pslive.rs` (T2 window), `psrearm.rs` (re-arm window).
* Tests `dip51_tests.rs`: off = dip49c instants; 3:40 then k 10 = 40,40,40,10.. per slot, 10 / 40 ms apart, 190 tries; no catch-up
  burst; flag ranges and strays.
* Launcher `ops/prod/run_dip_prod.sh.dip51r94` = r93's with the two flags passed through (non-numeric) and engine `snipe_engine_dip51`.

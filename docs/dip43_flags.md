# dip43 flags and control keys

Every dip43 item is OFF by default: with none of these flags the engine behaves as dip42 (only the banner lines are new).
All flags need `--presend-live` (refused without it, as every `--presend-live-*` flag).

## Builder B (send path and exits; `src/bin/snipe_engine/ps43_b.rs`)

| Flag / key | Values | Default | What it does |
|---|---|---|---|
| `--presend-live-max-per-sec` (existing) | 1..200 | 20 | Global pre-send cap. B1 wants 100. The ENGINE already accepts 100; the run script must too (see "Run script" below). |
| `--presend-live-reroute` | `on` / `off` | off | B1. A try refused by its lane's own cap (`rate_path`, or the path's `[[send]] max_per_sec` = `rate_path_config`) goes to the next lane of the same leader class (route order) that has room. A global-cap refusal (`rate_global`) is never re-routed. `presend_attempt.path` = the lane used, `path_orig` = the planned lane (only when moved). |
| `--presend-live-single-token` | `on` / `off` | off | B1. An async lane's try is charged ONE rate token (the sender's `fast_budget`) instead of two (`fast_budget` + `Path::send`'s `budget.acquire`). Uses `Path::send_prepaid`. Fast (own connection) lanes were already charged once. |
| `--presend-live-skip-clients` | comma list of gossip clientIds (`Rakurai`, `FireBAM`, ..., `Unknown(N)`) | none | B1. No pre-send try is signed for a slot whose leader runs a listed client; counted as `skip_client` in `not_sent`. Independent of the reactive `--skip-clients`. |
| `--presend-live-fee-tier` | `N:CU_PRICE[:CLIENTS]`, N 1..20, CU_PRICE 1..1,000,000 µL | off | B2. Every Nth try (1-based: the Nth, 2Nth, ...) a window signs in one slot is signed at CU_PRICE when the slot's leader runs a listed client (default `AgaveBam,HarmonicAgave,HarmonicFiredancer,Firedancer,Agave`, never JitoLabs). Never lowers a try's price. Works on top of the fee A/B (`--presend-live-fee-ab`): an arm-B try can be tiered too; the A/B ledger's failed-fee accounting follows the signed price. Example (MISSES P3): `4:150000` plus `--presend-live-cu-limit 105000`. |
| `--presend-live-start-ms` | 0..500 (ms) | off (= `--presend-live-ms`, 50) | B5. A T2 window's first try N ms after its trigger (0 = at once). The window's END slot is not moved (dip42's end, computed from `--presend-live-ms`). Re-arm windows already start at once. |
| `--presend-live-exit-lots` | `FRAC:SLOTS`, FRAC in (0, 1), SLOTS 1..4 | off | B3 two-lot exit (EXIT-1). Timer (`time-limit`, `time-ms`) and `take-profit` exits sell `floor(tokens × FRAC)` now (lot 1) and the rest SLOTS slot(s) later (lot 2), or after `400 × SLOTS + 600` ms on the wall clock if the slot clock stalls. A stop-loss value of lot 2's tokens seen while lot 2 waits sells lot 2 at once. `stop-loss`, `time-limit-wall` and `orphan` exits stay whole. Lot 1's sell loop stops at a confirmed balance ≤ lot 2's tokens (it never sells the remainder); lot 2's loop sells until 0. Realized P&L sums every sell of both lots. Both sells use the cached blockhash (no RPC before the first write). A position with an estimated (RPC-read) buy, or with fewer than 2 tokens, exits whole (`lots.whole_why`). Spec: `0.5:1`. |
| `--presend-live-exit-lots-ab` | `on` / `off` | off | B3. on = position-id parity A/B: even pid = lots, odd pid = whole (`lots.arm` = `whole` on its exit record). off = every eligible exit in lots. Needs `--presend-live-exit-lots`. |
| `--presend-live-exit-lots-kinds` | comma list of `t2`, `rearm`, `wide`, `qf2`, or `all` | `t2` | B3. Position kinds the lots exit takes. Needs `--presend-live-exit-lots`. |
| `--presend-live-lot2-cu-price-micro` | 1..50,000,000 µL | 500000 (when lots are on) | B3. Lot 2's CU price (a lot 2 fired by a stop uses the run's `--sell-cu-price-micro`). Lot 2 goes on the run's sell path(s) (the "helius-swqos only" variant of EXIT-1 is NOT built). Needs `--presend-live-exit-lots`. |
| control key `exit_lots` | `off` / `ab` / `live` | the flag's mode (`ab` with `-ab on`, else `live`) | B3, in the `--presend-live-ledger-control` file (re-read every ~10 s, on change). Needs `--presend-live-exit-lots` (else ignored). Every change writes `presend_live_ledger_mode` with `exit_lots` / `was.exit_lots`; a bad value keeps the mode (`ok: false`). Note: the engine refuses `--presend-live-ledger-control` unless a ledger / gate it switches is on (bot depth / whale / holder / dumper ledger); the runs have bot depth on. |
| `--presend-live-timer-sell-cu-price-micro` | 1..50,000,000 µL | off | B4 cheap timer sells (EXIT-2). `time-limit` / `time-ms` exit sells at this CU price; take-profit, stop-loss, `time-limit-wall`, orphan and follow-up sells unchanged. With lots on, lot 1 of a timer exit uses it (lot 2 uses the lot 2 price). Spec: 500000 (fee 65,000 instead of 605,000 lamports at 120k CU). |
| `--presend-live-timer-sell-ab` | `on` / `off` | off | B4. on = A/B on the position id's SECOND bit: `(pid >> 1) & 1 == 0` = cheap, else the run's price (so it never lines up with the lots A/B's parity bit). off = every timer sell cheap. Needs the price flag. |

### Start banner (printed on every start, on or off)

```
DIP43-B B1 CAP + ROUTES: global cap 60/s, per lane entry 19/s | re-route a lane-refused try off | one rate token per async try off | pre-send skip clients none
DIP43-B B2 FEE TIER: off
DIP43-B B3 TWO-LOT EXIT: off
DIP43-B B4 CHEAP TIMER SELLS: off
DIP43-B B5 WINDOW START: off: +50 ms after the trigger (--presend-live-ms)
```

(The lines start with `DIP43-B`, not `DIP PRESEND LIVE`, so dipmon's parse of the main start line is untouched.)

### Run script (`/root/prod/run_dip_prod.sh` on the servers: NOT changed by this build)

The engine accepts `--presend-live-max-per-sec 100` already (range 1..200). The run script copy in the repo
(`ops/prod/run_dip_prod.sh.dip37`, the newest one in git) refuses it:

- `GMAX=50; [ "$NONHEL" -gt 0 ] && GMAX=60` → for B1 make it `GMAX=100` when a non-Helius path shares the attempts (keep 50 for
  Helius-only routes). The following check that the Helius attempt paths stay ≤ 50/s by themselves stays as it is: with the
  MISSES F7 table Helius carries 8 per slot = 37/s under its 40/s path cap.
- The flag pass-through `case` must list the new flags, e.g. a line next to the dip37 fee A/B one:
  `--presend-live-reroute|--presend-live-single-token|--presend-live-skip-clients|--presend-live-fee-tier|--presend-live-start-ms|--presend-live-exit-lots|--presend-live-exit-lots-ab|--presend-live-exit-lots-kinds|--presend-live-lot2-cu-price-micro|--presend-live-timer-sell-cu-price-micro|--presend-live-timer-sell-ab) [ $# -ge 2 ] || die "$1 needs a value"; PSV["$1"]=$2; shift 2;;`
  (and the PSV loop that passes `PSV` entries to the engine must include them, as it does for the dip37 flags).
- The server's live script is newer than the repo copies; the orchestrator should apply the two changes there (or in the r76
  command wrapper) and check them with a dry run.

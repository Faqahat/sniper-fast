# dip43 log records

New records and new fields of existing records. With every dip43 flag off, none of these fields is written (dip42's records),
except where a section says otherwise.

## Builder B (send path and exits; `src/bin/snipe_engine/ps43_b.rs`)

### `presend_attempt` (sender thread, one per try; existing record)

| Field | When | Meaning |
|---|---|---|
| `path_orig` | only when B1 re-route moved the try | the lane the try was planned on (round-robin); `path` is the lane it went on |
| `tier` | only with `--presend-live-fee-tier` | `{i, n, on, client, cu_price}`: `i` = the try's 1-based number among its window's tries signed in this slot, `n` = N, `on` = signed at the tier price, `client` = the slot's leader is a tier client, `cu_price` = the price signed. The record's `cu_price` is the signed price as before. |

`not_sent` (status / `run_end`) gets the reason `skip_client` (B1 `--presend-live-skip-clients`).

### `presend_live_exit` (existing record, one per exit decision)

| Field | When | Meaning |
|---|---|---|
| `lots` | `--presend-live-exit-lots` on, an eligible exit (`time-limit`, `time-ms`, `take-profit`) of an eligible kind, mode not `off` | `{arm: "lots"/"whole", mode: "ab"/"live", frac, slots, kind}`; `whole_why: "too_few_tokens"/"estimated_tokens"` when the lots arm exits whole anyway |
| `lot` | lot 1 of a lots exit | `1` |
| `tokens` | lot 1 | lot 1's tokens (`floor(T × FRAC)`); dip42 = every token |
| `tokens_all`, `lot2_tokens`, `lot2_due_slot` | lot 1 | T, T − lot 1, the decision slot + SLOTS |
| `exit_ab` | `--presend-live-exit-ab ms:N` on (every exit) | `{arm: "ms" (odd pid: the N ms timer) / "base" (even pid: the run's exit), ms: N}` |
| `timer_sell` | `--presend-live-timer-sell-cu-price-micro` on and a `time-limit` / `time-ms` exit | `{arm: "cheap"/"base", cu_price: N or null, ab}` |

A SECOND `presend_live_exit` is written when lot 2 goes (the dip19 follow-up record does the same for its rounds):
`{ev: "presend_live_exit", why: "lot2" | "lot2-wall" | "lot2-stop", lot: 2, round, tokens (lot 2's, incl. a buy that landed after lot 1),
pid, w, mint, slot, value (the stop's value of lot 2's tokens; null on a timer), t, slots_held, lot1_slot, lot1_why, ms_after_lot1,
cu_price (lot 2's; null = the run's sell price), lot1_done (lot 1's sell loop had answered), kind ("rearm" when one)}`.
`st.exits` (status `exits`, `run_end.exits`) still counts one exit per position.

### `presend_live_lot_sold` (new; main loop)

Written when lot 1's sell loop answers (it never closes the position: lot 2's answer does).
`{ev, mint, pid, round, lot: 1, sold_at (the confirmed read's slot showing ≤ lot 2's tokens; null = not confirmed before the loop's
deadline: lot 2's loop sells what is left), sell_sigs [[sig, seen, tips]], attempts, lot2_fired, lot2_done}`.

### `presend_live_sell_land` (existing; feed, one per landed sell of ours)

| Field | When | Meaning |
|---|---|---|
| `lot` | a position with a lots exit under way | `1` (lot 1's sell: before lot 2 went, or the first landing of lot 1's token amount) or `2` |

`presend_live_close` and `presend_live_realized` are unchanged in shape: `sell_lands`, `sell_sigs`, `curve_pnl` and the realized P&L
include BOTH lots' sells (`rounds` = 2 for a lots exit).

### `presend_live_ledger_mode` (existing record; control file)

`{ev, ok: true, exit_lots: "off"/"ab"/"live", was: {exit_lots}, path, t}` on every change of the control file's `exit_lots` key
(only with `--presend-live-exit-lots`); `{ok: false, err, path, exit_lots (unchanged), t}` on a bad value.

### `presend_live_b43_start` (new; once at the start, only with a Builder B item on)

The parsed settings: `{reroute, single_token, skip_clients, fee_tier {n, cu_price, clients}, start_ms, exit_lots {frac, slots, kinds,
mode, lot2_cu_price}, timer_sell {cu_price, ab}, exit_ab_ms, exit_lots_mode}` (the mode after the control file's first read).

### `run_start` / `run_end` (existing)

- `run_start` presend_live cfg gets `b43` (the same settings object) only with an item on.
- `run_end` presend_live gets `b43` only with an item on: `{cfg, rerouted, reroute_failed, tier_tries, tier_base_tries, lots {mode,
  exits, whole_arm, whole_small, lot2_timer, lot2_wall, lot2_stop, lot1_unconfirmed, pending, ctl_changes, ctl_errors},
  timer_sell {cheap, base}}`.
- The status line gets ` | DIP43-B ...` only with an item on.

### Engine log lines (stderr)

- `SELL[lot 1] #n ...` / `SELL[lot 2] #n ...` (the sell loop's per-send line, tagged); `SOLD[lot 1] mint=... confirmed <= K tokens`;
  `SELL[lot 1] mint=... NOT confirmed down to K tokens (...)` (no UNSOLD alert for a part: lot 2 covers it).
- `PRESEND LIVE EXIT <mint> lot2|lot2-wall|lot2-stop (lot 2: N tokens, X ms after lot 1)`.
- `PRESEND LIVE LEDGER MODES: exit_lots A -> B (path)`.

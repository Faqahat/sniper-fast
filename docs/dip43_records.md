# dip43 records (--dip-log)

## Builder A

With no dip43 flag, the only new record is `presend_live_feed_stall`, written when an episode happens.

| Record | When | Fields |
|---|---|---|
| `presend_live_feed_stall` | A1, at an episode's start and end (default on) | start: `phase:"start"`, `kind` (`silent` \| `lag` \| `late_try`), `silent_ms`, `feed_slot`, `tpu_slot`, `lag_slots`, `armed`, `open`, `tries_in_flight`, `live`, `late_tries`, `t`. end: `phase:"end"`, `dur_ms`, `kinds`, `max_silent_ms`, `max_lag`, `t`. Also the `FEED-STALL ...` / `FEED-STALL END dur_ms=...` lines. A Telegram critical alert is sent when a position is open or tries are in flight. |
| `presend_live_blind` | A2, a late try (one of ours seen on a shred feed, unresolved after LATE_MS) | `sig`, `w`, `mint`, `first_rx_mono`, `mode`, `act` (`status_read` \| `would_status_read`). After the status read: `status {slot, ok}`, `tokens`, `ms`, `feed_saw_it`, `act` (`opened` \| `guess_sell` \| `none_failed` \| `none_feed_first` \| `none_position_open` \| `none_unreadable`). When the feed later shows the fill: `act:"feed_confirmed"`, `slot`, `idx`, `tokens`. |
| `presend_live_fill` with `via:"status"` | A2 live: a position opened from the status read | `w`, `n`, `mint`, `sig`, `slot`, `tokens`, `tokens_exact`, `held_ms_at_open`, `path`, `client` |
| `presend_live_deadman` | A2 log: what the dead-man would do (once per position) | `mint`, `pid`, `would` (`deadman` \| `time-limit-wall43`), `blind_ms` / `held_ms` |
| `presend_live_exit` `why:"deadman"` / `"deadman_guess"` | A2 live | the usual exit record |
| `presend_live_dip43` | at the start, only when a dip43 option is given | `cfg` (the options) |
| `presend_live_fam.fanout` | A4, on the dip35 fam read's answer | `n` (recv_n), `thr`, `flag`, `act` (`none` \| `would_disarm` \| `disarmed`) |
| `fanout` on `presend_live_arm` / `_skip` / `_fill` | A4 on | `flag` (mint flagged), `n`, `read` (the window's read came back) |
| `cascade` on `presend_live_fill` and on `presend_attempt_land` (res `ata_exists`) | A5 on | `snap {slot, age_ms}` (the RPC snapshot), `set: [{w, sign_pct, land_pct, trig}]` (top 8 at least 0.5% at signing, ours excluded), `ga {n, below, abort}`, `gd {n, below, abort}`. `land_pct` is the book just before our buy (executed feed order). For an `ata_exists` try it is the book at that try's own position. |
| `mint_ledger` on `presend_live_arm` / `_skip` / `_fill` | A6 on | `n`, `worst` (lamports), `would_block` |
| `presend_live_mint_ledger` | A6, each landing entering the ledger | `mint`, `pnl` (real: curve P&L minus fees and tips; paper: the engine's paper), `paper`, `n`, `worst` |
| `presend_live_shadow_exit` | A7, 12 slots after the fill (3 after our sell, whichever is later; also at the run end) | `pid`, `w`, `mint`, `land [slot, idx]`, `vals` (value / spend at the end of slots land+0..land+12), `outside` (other trades within 12 slots), `flow3 {buy_sol, sell_sol, first_buy_ms, first_buyer}` (the 3 slots after our sell landed), `rules {t4, t5, t8, bh3, top_pct, adv3 [k, v], hs1 [slot, v]}`, `exit {why, slot, value, lag}`, `stop {slot, v_trigger, v_next_slot}`, `realized_est` |
| `presend_live_stop_shadow` | A7, every stop-loss / take-profit decision | `mint`, `pid`, `why`, `v_trigger`, `slot`, `t` (the next-slot value is in `presend_live_shadow_exit.stop`) |
| `not_sent` on `presend_live_disarm` | A8 on | `due`, `sent`, `rate_global`, `rate_path`, `paused_position`, `paused_stall`, `other`, `slots: [[slot, due, sent, refused]]` (the window's first 16 slots). due = sent + the refusals. |
| `presend_live_unseen_fee` | A8 on, a window with unseen tries is forgotten | `w`, `unseen`, `fee_est` (each unseen try at its failed-try fee), `total_unseen`, `total_fee_est`. The run's records keep fee 0 for unseen tries; dipmon NET should add `total_fee_est`. |
| `would43` on `presend_live_arm` / `_skip` | A9, a gate in `log` mode would have skipped | list of gate names (`create_slot`, `young_age`, `quiet`, `lone_whale`, `cr_loss` / `cr_unfollowed`, `blocklist`, `quiet3_a`) |
| `presend_live_skip` `why:"rearm_log43"` | A9, `"rearm": "log"` | the re-arm check that would have armed |
| `presend_live_ledger_mode` `dip43` | A9, every dip43 key change | `dip43 {key: now}`, `was.dip43`, `path`; `ok:false` on a bad file; `botdepth_refused` when `"botdepth":"log"` is refused |
| `shadows43` on `presend_live_fill` | A10 on | `would_hold` (`no_verdict` \| `stale_block` \| null), `would_hold_sticky` (a block computed on the previous slot's data or later was superseded by the pass the try went out on), `t2_armslot` (the filling T2 try was sent in the trigger's slot), `bh_short {top_pct, would}` (a holder of at least 10% at landing means it would exit at 3 slots) |
| `age43` on `presend_live_qf2` | A10 on | `age`, `ge10`, `min`, `would_arm_ge10` (both verdicts: all ages and age at least 10) |
| `presend_live_fpnb_strict` | A10 `--presend-live-fpnb-strict X` | `w`, `mint`, `slot`, `score`, `thr`, `frozen_thr`, `live`. Written when strict blocks a T2 slot that the frozen threshold passes. |
| `react_watch` | A12 `--react-watch FILE` | `wallet`, `sig`, `mint`, `buy`, `sol`, `tok`, `vsol`, `vtok` (from the executed feed's event), `slot`, `idx`, `first_feed`, `t_seen_ns`, `first_executed`, `feeds [{feed, t, dt_ms, executed}]`, `cu_price`, `cu_last3` (haqq's bot code), `presend_armed` / `presend_held` (overlap with our pre-send at the first sighting), `copy_build_sign_ns` (MEASURED build plus sign of a 0.01 SOL copy buy with a throwaway key; never sent), `t_signed_copy_ready_ns` |
| run_end `presend_live.dip43` | only with an option, or when something happened | counts: status reads, dead-man, stale skips, cascade, mint ledger, fan-out, unseen fees, shadows, control changes |

### The true-balance book (for Builder C)

- **Where it lives:** `PsLive::tbook() -> Option<&arbx::ps43_book::TBook>`, in `src/bin/snipe_engine/ps43.rs`. It returns `None` unless `--presend-live-tbal on` (or `--presend-live-cascade on`) is given.
- **What it offers:** `TBook::true_balance(&self, mint: &Pk, wallet: &Pk) -> Option<u64>` and `TBook::top_holders(&self, mint: &Pk, n: usize) -> Vec<(Pk, u64)>` (largest first, the curve excluded; filter out our own wallet yourself).
- **Freshness:** `TBook::snap(mint)` gives `(slot, mono_ns)` of the newest RPC snapshot. Balances are true only after that snapshot (taken at the arm); before it the book has only the pump txs' post balances.

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

# dip43 records

## Builder C: snipe-guard (C2)

| Record | Field | When written | Content |
|---|---|---|---|
| `presend_attempt` | `guard` | every try, only with `--presend-live-guard deadline\|holders` (absent with the guard off = dip42's record) | snipe-guard try: `{mode: "deadline"\|"holders", n_floors, ix_bytes, keys, arm?: "G" (A/B on), max_viol?, floors?: [[wallet8, floor_whole_tokens], …], age_ms?, reason?: "no_snapshot"\|"stale"\|"few_holders"\|"size", dropped?}`; the A/B's Lighthouse arm: `{mode: "lighthouse", arm: "L"}` |
| `presend_attempt_land` | `res` | each try's result | with the guard on, a snipe-guard try that failed at the guard instruction: `"deadline"` (late, as Lighthouse's), `"guard_abort"` (any other decoded kind, or an unknown code), `"guard_other"` (a non-custom failure at the guard). Lighthouse tries: as dip42 |
| `presend_attempt_land` | `guard_abort` | a snipe-guard try that failed at the guard (only with the guard on) | `{kind: auth\|data\|accounts\|deadline\|curve_high\|curve_deep\|floors\|admin, idx (sub-reason or the worst holder's index in the try's `guard.floors`), cnt (holders below), gap_bucket, gap (words), sub? (auth/data/accounts/admin sub-reason), code: "0x…"}`; an unknown code: `{kind: "unknown", code}`; a non-custom failure: `{raw: err}`. Decoded with `snipe_guard::client::decode` (table: ops/guard/codes.md). Join to the try's `presend_attempt` by `sig`. |

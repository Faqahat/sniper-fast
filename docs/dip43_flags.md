# dip43 flags and control keys

## Builder A (safety, control, shadows; no transaction change)

With none of these flags, dip43 behaves like dip42. It sends the same tries, pays the same fees, takes the same exits and applies the same gates. The golden test `dip43a_golden_no_flags_equals_dip42` checks this. The only default-on output is the FEED-STALL watchdog's line and record (A1).

Every flag below needs `--presend-live`. `--react-watch` is the exception: it is independent. The start banner prints one `DIP43 A..` line per feature. The ledger control file (`--presend-live-ledger-control`, re-read every ~10 s) holds the control keys. In it, `"log"` means the verdict is computed and recorded but nothing is skipped. `"live"` means the gate acts as its start flag says. A key that is absent leaves the current mode.

| Item | Flag | Values | Default | What it does | Control key |
|---|---|---|---|---|---|
| A1 | `--presend-live-stall-mode` | `log` \| `live` | `log` | Watchdog mode. **log**: a `FEED-STALL` line and a `presend_live_feed_stall` record only. **live**: during a blind episode the sender signs nothing new (skip reason `paused_stall`), and T2 triggers more than 2 slots behind the slot clock are skipped as `stale_trigger` during the episode and for 10 s after it. | `stall` |
| A1 | `--presend-live-stall` | `SILENT_MS:LAG_SLOTS:LATE_MS` | `1500:8:400` | Watchdog thresholds. An episode starts when the executed feed is silent longer than SILENT_MS, when the TPU slot clock is more than LAG_SLOTS ahead of the executed feed's slot, or when one of our tries seen on a shred feed has no result after LATE_MS. | |
| A2 | `--presend-live-deadman` | `log` \| `live` | `log` | **live**: a late try gets a `getSignatureStatuses` call plus a processed read of our token account, run off the event loop. A try that landed OK and is not yet seen opens a position (`via: "status"`), with its hold clock started at the try's first sighting. If the read fails, the position is a guess of the try's `min_out`, sold at once (`deadman_guess`). A position open during an episode longer than DEADMAN_MS is sold at once (`deadman`). The wall-clock backstop becomes `exit_slots x 215 + 600` ms. **log**: no RPC call and no change; `presend_live_blind` / `presend_live_deadman` would-records. The backstop stays dip42's `exit_slots x 400 + 3000` ms. | `deadman` |
| A2 | `--presend-live-deadman-ms` | `0` (off) or `200..30000` | `1000` | Blind time after which an open position is sold (live) or logged (log). | |
| A3 | `--presend-live-tbal` | `on` \| `off` | `off` | Turns on the true token-balance book. Needs `--presend-live-fam-log`: the dip35 fam read at every arm, an RPC snapshot of all the mint's token accounts, is the source of TRUE balances. The executed feed's `post_token_balances` keep the book current (they are decoded only with this flag). | |
| A4 | `--presend-live-fanout` | `N` (2..1000) | off | Fan-out shadow, using the fam read's `recv_n` (recipients by plain transfer that still hold at least 0.05%). Needs `--presend-live-fam-log`. The verifier measured a flat result for N between 8 and 40, so use 10. | `fanout` |
| A4 | `--presend-live-fanout-mode` | `log` \| `live` | `log` | **live**: when a flag arrives, the window is disarmed with reason `fanout` and later triggers on the mint are skipped as `fanout`. | `fanout` |
| A5 | `--presend-live-cascade` | `on` \| `off` | `off` | CASCADE shadow (LOG ONLY; turns on A3). Records the top 8 holders by true balance at each try's signing and their balances just before our buy. Gives two verdicts: G-A (top-6 at least 1%, floor 0.9, abort at 2 or more below) and guards (top-5 non-trigger at least 0.5%, abort at 2 or more below 90%). | |
| A6 | `--presend-live-mint-ledger` | `SOL` in (0, 5] | off | MINT-LEDGER: mint -> worst landing result. Inputs are real fills (curve P&L minus fees and tips at the close) and one engine paper landing per T2 trigger, except `create_slot` / `young_age` triggers. A paper landing enters 12% under the trigger price, exits at ±20% at a slot end, or on a 6-slot timer. | `mint_ledger` |
| A6 | `--presend-live-mint-ledger-mode` | `log` \| `live` | `log` | **live**: a trigger on a mint with a prior landing at or below -SOL is skipped as `mint_ledger`. | `mint_ledger` |
| A7 | `--presend-live-shadow-exit` | `on` \| `off` | `off` | Writes `presend_live_shadow_exit` (12 slots after each fill and 3 after our sell) and `presend_live_stop_shadow`. | |
| A8 | `--presend-live-acct` | `on` \| `off` | `off` | Send accounting: `not_sent` on `presend_live_disarm`, `presend_live_unseen_fee`, and the unseen-fee total in the status line and run_end. | |
| A9 | `--presend-live-botdepth-allow-log` | switch | absent | Without it, the control file's `"botdepth": "log"` is REFUSED and the gate stays live; a `presend_live_ledger_mode` record with `botdepth_refused` is written. | `botdepth` |
| A10 | `--presend-live-shadows43` | `on` \| `off` | `off` | Shadows on the fill record and on QF2 records: FP-NOBOT leak `would_hold` plus `would_hold_sticky`, T2 arm-slot send, big-holder short, and both QF2 age verdicts. | |
| A10 | `--presend-live-fpnb-strict` | X in (0, 1) | off | FP-NOBOT strict threshold on T2. Writes `presend_live_fpnb_strict` would-blocks. Needs `--presend-fpnb-log on`. | `fpnb_strict` |
| A10 | `--presend-live-qf2-filters` | `SOLMIN:SOLMAX:CURVEMIN:CURVEMAX:AGEMAX[:AGEMIN]` | `AGEMIN` 0 | QF2 minimum token age. An AGEMIN of 0 keeps dip42's 5-field spec and records. The verifier did not support a cut at 10, so the default is 0. | `qf2_min_age` |
| A12 | `--react-watch` | FILE | off | REACT-PROBE recorder (LOG ONLY): one `react_watch` record per tx of a listed wallet. The initial list is `ops/prod/react_watch.json`. | |

### Control keys added by dip43 (ledger control file)

| Key | Values | Needs | Effect |
|---|---|---|---|
| `quiet` | live \| log | QUIET skip on | `log`: a QUIET skip becomes `would43: ["quiet"]` on the arm record |
| `quiet3a` | live \| log | `--presend-live-quiet3a on` | the same for `quiet3_a` |
| `create_slot` | live \| log | (always) | `log`: create-slot triggers go on (the following gates still apply); `would43` |
| `young_age` | live \| log | `--presend-live-min-age-slots` | the same for `young_age` |
| `lone_whale` | live \| log | `--presend-live-lone-whale-slots` | the same for `lone_whale` |
| `cr_loss` | live \| log | creator gate | the same for `cr_loss` / `cr_unfollowed` |
| `blocklist_arm` | live \| log | `--presend-live-blocklist` | the same for the arm-time `blocklist` skip (the per-send check keeps `blocklist_send`) |
| `rearm` | live \| log | `--presend-live-rearm on` | `log`: a re-arm check that would arm is recorded as the skip `rearm_log43` |
| `rearm_r5` | live \| log | R5 skip on | `log`: R5's skip becomes `would_skip` |
| `breaker` | live \| log | `--presend-live-breaker` | `log`: a trip is recorded; nothing is paused (T2, re-arm, sender) |
| `stall` / `deadman` | live \| log | (always) | as A1 / A2 |
| `fanout` / `mint_ledger` | live \| log | their flag | as A4 / A6 |
| `fpnb_t2` / `fpnb_rearm` | live \| log | `--presend-fpnb-log on` | sets FP-NOBOT's live gate bits (bit 0 T2, bit 1 re-arm) |
| `fpnb_strict` | live \| log | `--presend-live-fpnb-strict X` | `live`: the strict verdict also blocks T2 sends |
| `qf2_size` | SOL (number) | `--presend-live-qf2` | QF2 windows' own size; refused above the larger of the T2 size and the wide-dumper size, both checked against `--max-sol` at the start |
| `qf2_min_age` | slots (number) | `--presend-live-qf2` | QF2's minimum token age |
| `botdepth` | live (log only with `--presend-live-botdepth-allow-log`) | bot-depth gate | locked to live |

Each dip43 change writes one `presend_live_ledger_mode` record with `"dip43": {key: now}` and `"was": {"dip43": {key: was}}`, plus a `PRESEND LIVE DIP43 KEYS` line. A bad file keeps the current modes and writes a record with `ok: false, dip43: true`. A key whose feature is off is reported as `<key>_ignored`.

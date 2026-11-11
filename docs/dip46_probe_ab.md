# dip46: probe tries and filter A/B

dip46 = dip43g plus two features. Both are OFF by default. Without the flags below the engine writes dip43g's records byte for byte (test `dip46_golden_no_flags_equals_dip43g`). With probes on, every decision, send, fee and exit is unchanged once the probe records are taken out (test `dip46_golden_probes_change_no_decision`).

Code: `src/bin/snipe_engine/psprobe46.rs` (state, records, control keys), sender hooks in `pslive.rs`, and `ps43_guard::try_ixs_k46` (floors A/B). Tests: `dip46_tests.rs` and `dip43_guard_tests::dip46_floors_ab_bypass`.

## A) Probe tries

A **probe** is the try a live filter blocked, sent anyway, but signed so that it can never buy:

- It is built by the same code as a real try: the same route mix (path rotation, path and global rate tokens), CU limit and price, fee tier, guard (deadline, band, and floors when the window has a holder set), and loaded-data limit.
- The pump buy `buy_exact_quote_in_v3(spend, min_tokens_out)` gets `min_tokens_out = u64::MAX`. No bonding curve holds that many tokens, so the buy fails (pump slippage error, recorded as `6042`). The whole transaction reverts: no token account, no WSOL move, and no tip. The only cost is the failed-transaction fee.
- The test `dip46_probe_tx_can_never_fill` decodes the compiled, signed transaction and asserts that the buy data's min_out is `u64::MAX`.
- If a probe signature were ever seen as a buy of ours (impossible by construction), it is not booked as a fill. The engine writes a `presend_live_probe_filled` record and a line, and the orphan path sells the tokens.

There are two places a probe comes from:

| Where | When | What is sent |
|---|---|---|
| Arm-time | A T2 trigger is skipped by a probe kind (create_slot, young_age, quiet, quiet3_a, lone_whale, cr_loss / cr_unfollowed, wh_loss, holder_loss, blocklist, m2_unseen, mint_ledger, fanout, s1_*; breaker opt-in) | A **probe window**: id `2^40 + n`, never in `armed`, never a position. It sends one try per slot from the real window's start to its end slot. It stops 30 ms after the whale sells, when the token is gone, or when a real window arms on the mint (`superseded`). Limits: one per mint, at most `--presend-live-probe-max-windows` at once. |
| Send-time | A real window's try is withheld by FP-NOBOT (`fpnb`), skip2, the per-send blocklist (`blocklist_send`) or bot depth (`botdepth`) | That try, as a probe. At most one per window per slot. |

Re-arm windows get send-time probes. Arm-time probes cover T2 triggers only; re-arm arm-time skips get no probe window.

**Rate.** Probes send at most one try per window per slot, and at most N per second over the whole engine (token bucket, burst 1). They take the same path and global rate tokens the real try would. The real windows use k = 20 tries per slot, so probes never send more than the tries they replace.

**Kept out of the books.** Probes are excluded from:

- fills and the position book
- P&L and realized records
- the failed-fee 24 h budget and its pause
- the breaker
- the real tries' landing results and per-path / per-client counts
- `sent`, not-sent counts and the A8 window accounting

Their fees are summed apart as `probe_fees`. A probe is still subject to the send gates (one position, fee-budget pause, breaker pause, stop): when the real try could not be sent, no probe goes either.

### Flags

| Flag | Values | Default | What it does |
|---|---|---|---|
| `--presend-live-probe` | `on` \| `off` | `off` | Turns probes on. |
| `--presend-live-probe-max-per-sec` | 1..50 | 5 | Global probe rate. |
| `--presend-live-probe-kinds` | `all` or a list | `all` (all but `breaker`) | Which filters get probes. Names: `create_slot`, `young_age`, `quiet`, `quiet3_a`, `lone_whale`, `cr_loss`, `cr_unfollowed`, `wh_loss`, `holder_loss`, `blocklist`, `m2_unseen`, `mint_ledger`, `fanout`, `s1`, `breaker`, `fpnb`, `skip2`, `blocklist_send`, `botdepth`. |
| `--presend-live-probe-max-windows` | 1..64 | 8 | Most arm-time probe windows open at once. |

The control key `"probe46": "on" | "off"` in the ledger control file switches probes hot.

### Records

| Record | When | Fields |
|---|---|---|
| `presend_live_probe_arm` | A probe window opens | `w`, `mint`, `filter`, `kind`, `trig` (the T2 trigger), `en_slot`, `spend`, `drop`, `lim0` |
| `presend_live_probe` | Each probe sent | Every `presend_attempt` field, plus `filter`, `kind` (T2 / rearm), `would_limit`, `would_min_out` (the real try's 0.88x-limit tokens), `min_out` = 18446744073709551615 |
| `presend_live_probe_land` | Each landing, after 2 slots; or `unseen` after the deadline + 3 slots | `res`, `err`, `fee`, `slot`, `idx`, `t`, `send_slot`, `ms_send_to_rx`, `path`, `client`, `would_limit`, `would_min_out`, `spend`, `sign` [vsol, vtok]. Also `pre` {vsol, vtok, p, at}: the curve just before our position, from the feed's last trade of the mint before (slot, idx), or the signing state if there was no trade since. Then `would_tokens` and `would_fill` (true when pump would have given at least the real min_out there). `guard_abort` when the guard aborted. |
| `presend_live_probe_end` | A probe window ends | `why` (expired / whale_sold / token_gone / superseded / stopped), `sent` |
| `presend_live_dip46` | Start | The config and modes |

Status line: `PROBE: on sent N (dry N) landed N unseen N would-fill X/Y fees S SOL | windows N (now N) | refused {..}`. run_end: `presend_live.dip46` holds sent / landed / unseen / probe_fees, results, `by_kind` {sent, landed, unseen, fees, would_fill, would_miss}, window refusals and `impossible_fills`.

### How to read a probe

A probe that **landed** gives a measured landing position for the try the filter blocked. If the curve just before that position meets the real min_out, the real try **would have filled** at that state's price: `would_fill` is true and the entry is `pre`.

- A `deadline` or `guard_abort` landing would also have failed for the real try. `guard_abort` here is the band, or floors when the window carried them.
- `unseen` means no landing, so nothing is learned.
- Arm-time probe windows usually have no true-balance snapshot (no fam read is made for a skipped trigger). They then carry no holder floors, so their `would_fill` is an upper bound wherever floors would have aborted.

`ops/probe46/probe_check.py LOG` takes the first would-fill landing of each window, checks it on the chain tape, and prices it with the r82 exit (2350 ms timer, TP/SL ±20%, exact curve). It prints, per filter: windows probed, would-fills, win / lose / net SOL, and net scaled to 1 SOL.

## B) Filter A/B by parity

`--presend-live-filter-ab LIST` (or `none`) lists the A/B'd filters. Each listed filter is bypassed on the odd half and acts as today on the even half. Each listed filter must be on in the run; if it is not, the engine refuses to start.

| Filter | Parity | Bypass means |
|---|---|---|
| `young_age`, `create_slot`, `quiet`, `quiet3a`, `lone_whale`, `cr_loss` (with cr_unfollowed), `blocklist` (arm), `wh_loss`, `holder_loss` | The A/B's own count of T2 triggers (odd = bypass) | The gate runs in log mode for that trigger (its verdict is recorded as would). |
| `botdepth`, `fpnb`, `blocklist_send` | Window id (odd = bypass) | The withheld send goes out. botdepth's "log REFUSED" lock does not apply: the A/B is an explicit opt-in. |
| `holder_floors` | Window id (odd = bypass) | The try carries snipe-guard with the deadline and the band, but no floors. Needs `--presend-live-guard holders` without `--presend-live-guard-ab`. |

**Control file.** In the same ledger control file, `"ab46": {"young_age": "ab", "botdepth": "live"}` switches each filter hot: `"ab"` turns the A/B on, `"live"` or `"off"` turns it off. These keys are read only when the engine started with `--presend-live-filter-ab`. The older parsers ignore these keys.

### Records

| Record | Fields |
|---|---|
| `presend_live_filter_ab` | `w`, `mint`, `filter`, `arm` (`bypass` / `live`), `would_block` (true), `armed`, `kind`, plus `n_trig` (arm-time) or `slot` (send-time). Written once per trigger for arm-time filters, and at the first would-block per window and filter for send-time filters. |
| `presend_live_arm` / `presend_live_skip` | `ab46` {n, arms {filter: arm}, would: the bypassed filters that would have blocked}. Written only when an arm-time filter is A/B'd. |
| `presend_live_fill` | `ab46` {arms, would, try_bypassed}. Written whenever the A/B flag is given. |
| `presend_attempt` | `ab46` [the send-time filters this try bypassed], and `guard.ab46 = "bypass"` with `reason: "ab46_bypass"` on a floors bypass. |
| `presend_live_blocklist_withheld` | On a bypass: `log: true, ab46: "bypass"`. The per-send blocklist counts it as would, not withheld. |

To split P&L by arm, join `presend_live_realized` on `w` with the arm record's or fill record's `ab46`. probe_check.py part (2) prints, per filter, live arm vs bypass arm vs the bypass windows the filter would have blocked: windows, filled windows and real P&L.

## Costs

The only cost of a probe is the failed-try fee: 5,000 plus CU limit × price. With r82's 110,000 CU and the 50,000 micro-lamport tier this is 10,500 lamports. A probe that does not land costs nothing.

Estimate from r82's log (15.85 h):

| Source | r82 count | Probes |
|---|---|---|
| T2 arm-time skips (create_slot 1351, quiet 226, young_age 208, lone_whale 79, holder_loss 52, wh_loss 33, blocklist 3) | 1,952 skips ≈ 2,950 per day | Probe windows send up to ~10 per window (one per slot to `en_slot` = trigger + 10), fewer when the whale sells. That is about 12–30k probes per day, **≈ 0.12–0.31 SOL/day**. Without `create_slot` (69% of the skips): ≈ 0.04–0.10 SOL/day. |
| Send-time withholds (botdepth 2,074 window-slots, fpnb 676, blocklist 11) | ≈ 4.2k probes per day | **≈ 0.044 SOL/day** |

At 98.8% of tries landing, the total is about **0.17–0.35 SOL/day** with kinds `all`, or about 0.08–0.15 SOL/day without `create_slot`. Use `--presend-live-probe-max-per-sec` as a hard cap: 5/s caps any day.

## Risks / limits

- **Jito-relayed copies.** A probe always fails. A path that forwards through a Jito bundle auction drops failing transactions, so the probe lands only by the path's staked or validator route, while a real filling try could also land through the bundle. Probe landing can therefore under-state a fill on Jito-leader slots. Compare `unseen` rates per client to see this.
- **Arm-time floors.** Arm-time probe windows usually carry no holder floors (no fam read is made for a skipped trigger), so `would_fill` is an upper bound where floors abort.
- **What a would-fill does not model.** It is one try per slot (the real window sends 20), so it can miss in-slot price moves. It does not include the one-position rule or our own impact on the followers.
- **Fee tier.** A probe takes the per window-slot tier counter as the real try would, so a probe window's tries always pay try #1's tier price.

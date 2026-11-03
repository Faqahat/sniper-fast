# dip26: LIVE RE-ARM in the engine (built 2026-10-29, ~20:55 PKT)

Owner decision 10-29 19:35 PKT: "add re-arm in the engine". AMS run 37 (dip25) keeps running; run 38 starts with re-arm on.
Nothing was deployed, nothing written on a server, nothing sent, no git commit. The live run script on AMS was only read (md5 bc44f8e5).

## 1. What was built

| File | What |
|---|---|
| `src/bin/snipe_engine/psrearm.rs` (new) | The re-arm state machine (a child module of pslive): `Rearm` (candidates, waiting windows, armed windows, counters, the realized split), `rearm_slot` (the clock: QUIET stop, last slot, holders checks), `rearm_check`, `rearm_arm`, `rearm_trade` (stops, QUIET count, new candidates), `rearm_tick` (waiting windows arm when clear), `rearm_take_over` (a T2 window takes the token), `rearm_stop_all`, `rearm_status`, `rearm_json`, `rearm_split`, `launch_refusal` (the T2 launch rule, shared). |
| `src/bin/snipe_engine/pslive.rs` | Flags (`RFLAGS`, `RearmCfg`, `Cfg::rearm_from`, range checks in `Cfg::check`, `Cfg::json` only when on); the sender: each window's own spend (`SWin.spend`, `att_limit`, `att_ixs`), the gate moved unchanged into `send_gate`, `"kind":"rearm"` on re-arm attempts; hooks in `on_exec` (clock, per trade), `trigger` (a re-arm window never blocks T2; T2 takes over), `fill` (re-arm size, kind), `exit` / `close_pos` / `orphan` / sell landings / late fills / attempt landings (kind), `disarm` (re-arm ends kept out of the T2 counters), `tick`, `stop`, `status`, `finish`; `realized_out` (the realized record and line, moved out of the task unchanged, + kind / " [rearm]"); `rearm_desc` (the start-up line's end). |
| `src/bin/snipe_engine/dipmode.rs` | run_end: `presend_live.realized_split` {t2, rearm} after the realized lookups are in (only with re-arm on) and a `=== DIP PRESEND LIVE REALIZED by kind` line. |
| `src/presend_live.rs` | Detector accessors: `holders_at_least`, `any_holder`, `last_trade_slot`, `trade_counts` (+ lib test `detector_rearm_accessors`). |
| `src/bin/snipe_engine/dip26_tests.rs` (new) | Golden, 13 unit / wiring tests, 1 by-hand recorded-hour live-vs-paper test. |
| `ops/prod/run_dip_prod.sh.dip26-draft` (new) | The run script draft (section 6). |

Binary: `/home/moiz/sniper-data/speed_fixes/bin/snipe_engine_dip26`
sha256 **459d4201debba31b443c8d41738cbd983ed43c1b5e6058d7cf9a5e455667d934** (also in `snipe_engine_dip26.sha256`).
The dip25 binary refuses every re-arm flag ("unknown flag"), so a script pointing at the wrong engine cannot start with re-arm.

## 2. The rule as implemented (the observatory's R0, src/obs/rearm.rs)

1. **Candidate**: a single curve SELL of >= 6% of supply (tok >= 6e13) by anyone but us, on a token the live detector follows (seen from its create, normal curve, not mayhem). Post-sell curve >= 100 SOL -> skip `rearm_untradeable`; token older than 141 slots at the dump -> skip `rearm_age`. Smaller sells are not candidates (nothing recorded).
2. **Clock**: the executed feed's slot clock, exactly the observatory's (the newest slot of an executed pump tx). The holders check runs at the first executed tx of a slot >= dump + 3, before that tx's trades.
3. **Holders check**: every wallet but ours holding >= 6% (the detector's balances), largest first. None -> `rearm_no_holder`. Then, as skips: stopped / no new buys -> `rearm_blocked_stopped`; a T2 window armed on the token -> `rearm_blocked_live_armed`; a re-arm window armed on it -> `rearm_blocked_rearm_armed`; the reactive bot holds it -> `rearm_blocked_reactive`; launch not tradeable -> `rearm_blocked_launch`; R5 (flag) -> `rearm_r5`.
4. **Deferral** (instead of dropping): our position on the token (or its 300 ms margin), our token account of it open (kept open after a sell, or an UNSOLD retry), or an earlier window's attempt on it that can still land -> `presend_live_rearm_defer`; it arms as soon as that clears if still <= its last slot (arm record `deferred`, `deferred_ms`). Its stops run while it waits; if one hits, or its last slot passes, it never arms (`rearm_blocked_position` / `rearm_blocked_ata_open` / `rearm_blocked_inflight` with `ended`).
5. **Window**: armed at once (st = now: no +50 ms, the paper's t_arm); last slot = dump + 3 + G (G = 20). Everything else is the T2 machinery: k tries per slot, limit = latest price x (1 - drop) re-read on every trade, deadline + 1, same routes / senders, shared 40/s caps, rolling 24 h fee budget, one-position pause. Spend = `--presend-live-rearm-size-sol`.
6. **Ends**: last slot (`expired`); 30 ms after the next >= 6% sell by anyone (`whale_dump`); 30 ms after the trade after which no wallet but ours holds >= 6% (`no_holder`); QUIET N:M on the same clock: at the first slot >= arm slot + N with < M trades by anyone but us since the arm (`quiet`); a T2 window arming on the token (`superseded`); a fill (`filled`); the stop (`stopped`); the token leaving the detector (`token_gone`).
7. **Fill / exit**: the normal pre-send position path unchanged (exit-ms 200 / TP / SL / slot limit, sell rounds, kept-open account and its close, realized from chain txs, end check). Only the size differs.
8. **R5** (`--presend-live-rearm-r5-skip on`, default off): skip when all 4 QUIET arm signals hold for the LARGEST holder (since_last >= 1, no cohort holder, < 2 follower bots, its dump history drew < fol buyers or none) = the shadow's `r5_skip`.

**Deviations from the shadow, and why**
- One window per token: when two dumps fall within 3 slots, the paper arms two overlapping windows (and can count the same fill twice); live arms one (`rearm_blocked_rearm_armed`). 2-6 per hour in the replays.
- Deferral and the "attempts in flight" wait (safety; the paper has no positions or accounts). In the replays the in-flight wait moved 1-4 arms per hour by 1 slot (a T2 window on the same token had just ended).
- A deferred window's QUIET count starts at its live arm, not at the check (it is about its own tries).
- Live stops a window on a T2 arm at once; the paper applies `superseded` after the fact from tailed records.
- The 30 ms stops run on the wall clock (as T2's); the paper's on the feed clock. One replay window ended `expired` live vs `whale_dump` on paper (the stop fell past the last slot).
- R5 respects QUIET's warm-up (no skip until the arm rule is on: `would_skip`) and needs `--presend-live-quiet-skip on` (its whale history, cohort and follower-bot lists).
- The re-arm needs `--presend-live-one-position on` (refused otherwise).

## 3. Safety

- **One position**: the global one-position pause covers every window; a re-arm fill pauses all windows (T2 and re-arm), a T2 position pauses re-arm windows; paused windows stay armed and resume (test 8).
- **Account guard (dip19)**: re-arm tries are the same tx (NON-idempotent Token-2022 ATA create); a window never arms while our account of the token is open or a fill of another window can still land.
- **Deferral**: never dropped for a block; never armed past its last slot (tests 6, 6b).
- **Stops**: the probe's stop, kill switch / profit lock (DIP_NO_FIRE -> stop), fee-budget pause, run-stop grace and end check apply exactly as to T2 windows (test 10).
- **Size**: re-arm size <= `--max-sol` or the engine refuses to start (test 9).
- **Off = dip25**: with the flag off nothing of it runs.

## 4. Tests (all run 10-29 ~20:40-20:50 PKT)

- `cargo test --release --bin snipe_engine`: **105 passed, 0 failed, 7 ignored** (by-hand tests). Lib: `presend_live` 7 passed (new `detector_rearm_accessors`), all `presend*` 31 passed / 2 ignored, `obs::` 15 passed.
- **Golden** `dip26_golden_rearm_off_equals_dip25`: 61,723 lines (probe records, lines, chain work, shadow records, run totals on the 312-token parity tapes with attempts, fills, exits, sells, reads, closes; 3 configs incl. run 37's pre-send options). Digest taken on the dip25 tree before any change (380c2a18...), identical with dip26. Deterministic (3 runs).
- **Real-hour golden**: the dip24 recorded-hour harness on 10-29 00:00-01:00 PKT (180,293 txs): probe (417) and dip-log (927) records byte-identical, dip25 vs dip26.
- **T2 unchanged with re-arm ON** (`dip26_rearm_on_leaves_t2_unchanged`): 30,265 T2 records identical (window ids aside) while 32 re-arm windows armed.
- **Unit / wiring** (spec list): 1 `holder_b_dumps_fill_exit_realized_tagged`; 2-4 `no_holder_age_untradeable`; stops `stops_whale_dump_no_holder`; 5 `t2_blocks_and_supersedes`; 6 `deferred_until_clear_or_never` + `waits_for_attempts_in_flight`; 7 `quiet_stop`; 8 `one_position_both_ways`; 9 `size_used_and_cap_refused`; 10 `fee_pause_kill_switch_profit_lock`; 11 `flags_and_refusals` + `presend_live_flags_and_refusals` extended; R5 `r5_skip_largest_holder`.
- **Live vs paper on recorded hours** (`dip26_recorded_hour_live_vs_paper`, by hand: probe and the observatory's rearm module fed the same txs; 30 ms stops on the feed clock):

| Hour (PKT) | Candidates paper / live | Verdict agree | Windows paper / live | Holders agree | Arm + last slot | End reason |
|---|---|---|---|---|---|---|
| 10-29 07:16-08:16 | 235 / 235 | 232 (98.7%) | 56 / 53 | 53/53 | 52/53 | 53/53 |
| 10-29 00:00-01:00 | 361 / 361 | 355 (98.3%) | 100 / 94 | 94/94 | 90/94 | 93/94 |

Every difference is a listed deviation (overlapping windows, the 1-slot in-flight wait, one stop past the last slot). About 53-94 live windows an hour (~1,300-2,200 a day; run 37 armed ~1,400 T2 windows a day).

## 5. Records and lines

- `presend_live_arm` +`"kind":"rearm"`, `dump{sig, slot, idx, j, t, seller, sol, tok, pct, drop_pct, vsol, vtok, age_slots}`, `holders[{w, pct}]`, `gap`, `check_slot`, `arm_slot`, `en_slot`, `arm_ms_after_dump`, `deferred_ms`, `deferred`, `k`, `spend`, `drop`, `lim0` (`holders_arm`, `r5` when they apply). No `trig` object (the observatory's tailer reads T2 arms by it; with it the paper would mark its own windows superseded).
- `presend_live_skip` +kind with the whys above; `presend_live_rearm_defer`; `presend_live_disarm` +kind and `rearm{dump_slot, arm_slot, en_slot, others, quiet_stop, stop, deferred_ms, holders, quiet}`; `presend_attempt`, `presend_attempt_land`, `presend_live_fill` (+`spend`), `_late_fill`, `_exit`, `_sell_land`, `_close`, `_realized`, `_orphan` +kind. T2 records unchanged.
- Log: `PRESEND LIVE FILL / EXIT / CLOSED / REALIZED ...` end with ` [rearm]` (prefixes unchanged); new `PRESEND LIVE REARM ARM w...` and `PRESEND LIVE REARM QUIET STOP w...`.
- Status line: ` | rearm: windows N armed now N fills N realized +x.xxxx SOL (candidates, checks, waits, attempts, failed-try fees, skips, ends)`.
- Start-up: the `DIP PRESEND LIVE (REAL attempts) | ...` line gets ` | REARM ON: ...` at its END (a separate line starting "DIP PRESEND LIVE" would replace dipmon's parse of the main line); the Telegram start message gets a re-arm row.
- run_end: `presend_live.rearm{...}` and `presend_live.realized_split{t2:{pnl,n}, rearm:{pnl,n}}`.

## 6. Run script draft (`ops/prod/run_dip_prod.sh.dip26-draft`, `bash -n` OK, md5 c95fc197)

Diff vs the live script (md5 bc44f8e5): 49 lines added, 2 changed.
- Header: dip26 block (rule, options, the run-38 command).
- New options: `--presend-rearm [on|off]`, `--presend-rearm-size X` (0.05..1.0, default the pre-send size), `--presend-rearm-gap G` (1..60, default 20), `--presend-rearm-quiet N:M` (N 1..30, M 1..100, default 6:2), `--presend-rearm-r5 on|off` (default off; on needs `--presend-quiet`).
- Refusals: re-arm without `--presend-live`; with `--presend-live-one-position off`; any parameter without `--presend-rearm`; values out of range.
- The re-arm size joins MAXSIZE (per-buy cap `--max-sol` = largest size x 1.05, and the 1.5 SOL budget check).
- `B=/root/sniper-dip/snipe_engine_dip26`; `${REARGS[@]}` passed after QUIET's args (all five engine flags explicit); `$REDESC` in the start-up summary.
- Checked in isolation (the draft's own lines sourced): good line OK; bad size / gap / quiet / r5 / missing value / missing `--presend-live` / one-position off / parameters without `--presend-rearm` all refused.

## 7. Next run (AMS run 38)

Run 37's options were read back from its running engine's arguments (ps on AMS); please compare with your run-37 command.

```
sudo bash /root/prod/run_dip_prod.sh --region ams --run 38 --regular paper --size 0.696 --tier wider --tp off --sl 0.5 --hold-slots 5 \
  --near /root/sniper-dip/near_leaders_ams.txt --nonce /root/prod/nonce_ams.txt --m2 /root/dip/m2_v3_reg4_top25.json --m2-mode gate \
  --presend --presend-whale-pct 6 --presend-tp 0.20 --presend-live --presend-live-size-sol 0.696 --presend-live-k 8 --presend-live-exit-ms 200 \
  --presend-live-min-age-slots 2 --presend-live-routes default=helius-ps --presend-live-max-per-sec 40 --presend-live-path-max-per-sec 40 \
  --presend-live-fee-budget-sol 1.0 --presend-quiet --quiet-stop 5:2 --quiet-fol 4.0 --quiet-fbots /root/dip/fbots_none.json --presend-quiet-v2-log \
  --sell-fanout helius-swqos --skip-clients Rakurai --clock2 --loaded-data-limit 16777216 --route-headers --window-clock --routes v13 --fallback ck \
  --observatory --minutes 0 --profit-lock 0.65,0.30 \
  --presend-rearm on --presend-rearm-size 0.40 --presend-rearm-gap 20 --presend-rearm-quiet 6:2 --presend-rearm-r5 off
```

Deploy (NOT done; after run 37 ends): copy the binary to `/root/sniper-dip/snipe_engine_dip26` on AMS and check its sha256; install the draft as `/root/prod/run_dip_prod.sh` via a `.new` file + `mv` (never in place). The observatory stays on, so the paper re-arm keeps running next to the live one for the comparison.

## 8. Open risks

1. **Edge**: REARM2.md failed its own bar narrowly; most of the paper gain is follower money (about +1.2 SOL/day at -20% followers, negative at -40%). Live lands later than the paper's +10 ms row, so expect less than the paper's +3.45 / 12 h.
2. **Fees and caps**: re-arm roughly doubles the windows. Run 37 spent 0.19 SOL of failed-try fees in ~13 h (1.0 / 24 h budget): expect ~0.3-0.4 SOL / day, still under it. Re-arm tries share the 40/s caps with T2 tries (more `rate_*` refusals).
3. **One position cuts both ways**: a re-arm position (~0.5 s) blocks T2 fills and vice versa. A re-arm window right after our T2 fill on the same token waits for the kept-open account (~1.5-3 s) and often arms late or never.
4. **Observatory paper**: live re-arm tries are tailed as `presend_attempt`, so the paper's per-second budget counts them (its `refused` counts run high; its fills do not change). Paper overlapping windows can double-count fills.
5. **Monitors**: dipmon counts re-arm arms / skips / disarms with T2's (`quiet` re-arm stops in its QUIET stops; many `rearm_age` / `rearm_no_holder` skips, ~270-380 / hour); its PS trade shows the T2 size until the close record. The run report sums T2 and re-arm P&L together (records carry `kind` for a split). Offline scripts that read `r["trig"]` on every `presend_live_arm` / `presend_live_skip` will hit KeyError on re-arm records: filter on `kind`.
6. **Not run on a server yet**: no `--presend-live-dry` run of dip26. Optional, with your OK.

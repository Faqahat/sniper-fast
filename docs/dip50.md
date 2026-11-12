# dip50: GRX = rival-ahead early exit (T2 lane)

Off by default: without `--presend-live-grx on` the engine is dip49c (same tries, exits, records, filter-state hash).
Code: `src/bin/snipe_engine/psgrx50.rs` (rule, state, records), `psctl47.rs` (hot keys), `pslive.rs` (wiring), tests `dip50_tests.rs`.
Research: `/home/it/sniper-data/grouprisk2/` (m5_entrants.py `Ln_g`, m8_exit.py), rule "G2 entrant risk".

## Rule (once per position, when the main loop registers our fill; the detector has not taken our buy yet)
- candidates = the dip30 landing annotation's set: `Detector::holder_clocks(mint, >= 2% of supply, ours out, fill slot, top 12)`
- ENTRANT MEMBER: wallet != the window's trigger whale, `risk >= 5`, `hz3 >= 0.3`, hold age `<= fill slot - trigger slot`
  (age = slots since the wallet's FIRST buy of the token, the annotation's `age`; a wallet that sold out and re-bought keeps its old age)
- `ent_pct` = members' holdings summed (% of supply); FLAG when `ent_pct >= grx_pct` (2.245)
- lane: T2 fills only. Re-arm fills: computed + logged (`over`), never flagged / acted on. Wide / QF2 / probes: nothing.
- fail open (no flag, `"skip": why`, one line): `no_window`, `no_trigger_slot`, `no_holder_book`, `no_hold_clocks`, `feed_blind`.

## Flags / hot keys (control file of `--presend-live-ledger-control`, like grp_t2)
| flag | key | values | default |
|---|---|---|---|
| `--presend-live-grx` | - | on / off | off |
| `--presend-live-grx-mode` | `grx` | log / live | log |
| `--presend-live-grx-pct` | `grx_pct` | 1..20 | 2.245 |
| `--presend-live-grx-exit-slots` | `grx_exit_slots` | 1..5 | 1 |

Needs `--presend-live-ann on`. Keys with the flag off: refused with a `presend_live_ledger_mode {ok:false}` record. Changes: mode record
`{"dip47": {...}, "was": {...}}` + the versioned FILTER STATE (fv / fh; the three keys are in the state only with the flag on).

## Live action
`tick()`: the regular timed exit is asked first (time-ms / time-limit / wall); only when it is not due: `slot_now >= fill slot + N`
-> `exit(why = "grx")`. So GRX can only add an earlier exit. TP / SL / dump-exit (trade path) unchanged; the earlier wins. The sell is the
regular whole sell at the base price ("grx" is not a timer reason: no cheap timer price, no lots). A position keeps the N of its fill.
Nothing on the sender thread or the buy path; no RPC; the flag comes from the detector's in-memory book on the main loop.

## Records
- `presend_live_fill.grx` `{mode, thr, kind, since, ent_pct, ent_n, members[{w,pct,age,risk,hz3}], old_pct, old_n, whale_pct, whale_member,
  would_exit, exit_slots, applied}` (re-arm: + `over`; fail open: `{mode, thr, kind, skip, would_exit:false, exit_slots, applied:false}`)
- line per flagged fill: `PRESEND LIVE GRX (log|live) wN MINT: entrants X.X% (n) [..] -> would exit at fill+N | EXIT at fill+N`
- `presend_live_exit.why = "grx"`; `presend_live_realized.grx` `{mode, flag, ent_pct, applied, exit}`
- `presend_live_grx_path` `{w, mint, kind, flag, fill_slot, fill_idx, price_fill, per_slot[{dslot 0..5, price, buy_sol, sell_sol,
  us_sell_sol, n}], closed:"slot5"}` for every evaluated fill (T2 + re-arm): trades AFTER our buy, outside wallets' SOL, ours apart; written
  when a slot > fill + 5 is seen, not closed at our exit. (`presend_live_flow` of dip48 is unchanged: still dslot 0..3, closed at the exit.)
- status: ` | GRX fills N flagged N (live exits N)`; run_start cfg `grx {grx, grx_pct, grx_exit_slots}`; banner `DIP50 GRX (log|LIVE): ...`

## Log-only extras on `presend_live_fill.grx` (never an exit in this version)
- `g0_pct` (= ann.grp_pct: risky candidates WITH the trigger whale), `g0_would` = t2 && g0_pct >= grx_pct
- `cas_src`, `cas_pct`, `cas_members[{w, sign_pct, land_pct}]`, `cas_would` = t2 && cas_pct >= 5.0. Set = the dip43 A5 CASCADE shadow's set of the
  filling try at its signing (`d43.sigset`: top 8 holders >= 0.5% by TRUE balance, ours out); members = non-trigger, >= 1.5% at signing, true
  balance lower at our landing; cas_pct = the summed fall. Needs `--presend-live-cascade on` (else `cas_src: "off"`, cas_pct null).
- `trig_pct` (T2: the whale's % at its trigger; re-arm: the dump's %), `small_would` = t2 && trig_pct <= 6.25
- `whale_pct`, `whale_risk`, `whale_hz3`, `whale_member`
- re-arm only: `hold_pct` / `hold_n` (every holder >= 2%, ours out, at landing), `ra_hold30_would` = hold_pct >= 30
- `presend_live_grx_marks` `{w, mint, kind, flag, fill_slot, tokens, spend, sold_at_dslot, marks[{dslot 0|1|2|5, out, vsol, vtok, buyers,
  buy_sol, sell_sol}], closed}`: at the END of slot fill+d, what selling this fill's actual tokens on the curve then returns (lamports, after
  the trade fee, before tx fees); buyers / buy_sol / sell_sol = outside wallets, cumulative after our buy. A position sold earlier still gets
  marks as if held: our own sell IS in that curve state (`sold_at_dslot`). Written with the path record (slot > fill+5 seen, or 5 s: then
  only the marks whose slot ended).

## Offline check
`/home/it/sniper-data/dip50/validate_grx.py` recomputes the rule from the run logs (ann.holders + slots_after_trigger + arm trig.wallet).

## Probe selection + re-arm probes (psprobe46.rs; defaults = dip49c's probes exactly)
- `--presend-live-probe-filters LIST` / hot key `probe_filters`: `all` (default), a comma list of filter names, `-name` excludes
  (`all,-create_slot`). Names = the probe records' `filter` values: create_slot, young_age, quiet, quiet3_a, lone_whale, cr_loss, cr_unfollowed,
  wh_loss, holder_loss, blocklist, m2_unseen, mint_ledger, fanout, s1 (every s1_*), breaker, fresh_holders, fpnb_withheld, skip2_withheld,
  blocklist_withheld, botdepth_withheld, rival_gate_withheld (accepted; nothing probes a rival-gate withhold, as in dip49), rearm_fleet_withheld,
  rearm_r5, rearm_holder_loss, rearm_wh_loss, rearm_blocklist, rearm_fresh_holders, rearm_m2_unseen, rearm_cap. Unknown name: refused at start /
  the key refused (old value kept). `--presend-live-probe-kinds` still applies on top (the breaker stays opt-in there).
  An excluded filter: no probe window at its skip, no probe of its withheld try; an open probe window of it stops sending (`probe_filter_off`).
- `--presend-live-probe-rearm on|off` (off) / hot key `probe_rearm`: (a) a re-arm check skipped by rearm_r5 / rearm_holder_loss / rearm_wh_loss /
  rearm_blocklist / rearm_m2_unseen / rearm_cap, or the re-arm fresh-holders skip (`rearm_fresh_holders`), arms a PROBE WINDOW built as the
  re-arm window would have been (re-arm size, the limit on the curve at the check, last slot = dump + 3 + gap, starts at once, one try per
  slot, stops 30 ms after the next >= 6% sell / no >= 6% holder left, ends when a real re-arm window arms on the mint); (b) a re-arm try the
  fleet rule withholds goes out as a probe (`rearm_fleet_withheld`). Records as the T2 probes with `"kind":"rearm"`. Same refusals as a T2
  probe window (stopped, a probe window / anything of ours on the mint, max windows, launch accounts) and the SAME global rate
  (`--presend-live-probe-max-per-sec`). Not probed (not in the request / no clean hook): rearm_cr_loss, rearm_cr_unfollowed, rearm_s1_*,
  rearm_breaker, rearm_log43, and every non-filter skip (rearm_age, rearm_no_holder, rearm_gone, rearm_untradeable, rearm_blocked_*).
  Re-arm tries withheld per try by FP-NOBOT / skip2 / bot depth / the per-send blocklist were already probed in dip46 (unchanged).
- Both keys need `--presend-live-probe on`; they are in the filter state once a flag or key of theirs is in use. Status: ` | PROBE lanes: T2
  windows N probes N / re-arm (on|off) windows N probes N | filters ...` (only once in use).

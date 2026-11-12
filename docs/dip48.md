# dip48: follower-flow log (LOG ONLY)

dip48 = dip47 (a85abd28) plus one log-only feature. Branch `dip48-flow`. Code: `src/bin/snipe_engine/psflow48.rs`; tests:
`dip48_tests.rs`. With the flag off, the records are dip47's (the golden digest; the filter-state object has no `flow_log` key).
Turned on, it changes no decision, send, fee or exit (golden pass: 61,723 lines identical, 238 flow records and 238 lines added).

## Flag

`--presend-live-flow-log on` (default off). It is in the filter state as `flow_log: true`, only when on.

## Why

trigdisc2 PLAN.md section 4 (lever 3). Outside buys in slots fill .. fill+1 after our pre-send fill describe the bounce
(AUC 0.82 train / 0.72 test). Most of that flow comes from the registry dip bots. The log measures it live on every fill, for later exit,
size and regime work.

## What

For every pre-send fill (T2, re-arm, wide), the trades on the mint AFTER our buy in slots fill, fill+1, fill+2 and fill+3 are recorded.
Per slot offset and per class: buy SOL, sell SOL, counts, distinct outside buyers, and the curve price (vsol / vtok) after the slot's last
trade. A fill is closed when a slot past fill+3 is seen (by the tick) or at the position's exit (`presend_live_exit`), whichever comes first.

## Classes

The study's `s4_fills.py`, exclusive, in this order:

| class | rule |
|---|---|
| us | our wallet |
| dumper | the window's trigger whale / re-arm dumper |
| fleet | the trade's tx invokes the Lighthouse program (`L2TExMFK…`; the study's "fleet program" class) |
| bots | the registry: the bot-depth list the engine loaded (`--presend-live-botdepth-list`, the study's `botdepth_wallets.json`); no list = none |
| rivals | the study's 15 named prefixes (haqq6qnV, 4ggJqUDD, DL7cmioG, 8yYMhu, E2x1, 9pQQc1xy, 8PgC4ngp, 2NUMEzNh, 3qvuM3U5, rem3dgec, peMU8nX3, DF7eRX, 7tg5VGSe, CkbAaKua, HkQ7hMjy) + 2y2iF8fA + `--presend-live-tag-wallets` |
| retail | everyone else (the study's "quick" + "retail") |

## Records

* `"ev":"presend_live_flow"` with these fields:
  * `w, mint, kind, fill_slot, fill_idx, closed (slot3 | exit), price_fill`;
  * `per_slot [{dslot 0..3, buy_sol {class: SOL}, sell_sol {class: SOL}, n_buys, n_sells, n_buyers, price}]`;
  * `tot1` / `tot2`: outside (all but us) buy and sell SOL through fill+1 / fill+2, plus fleet / bots / rivals / retail / dumper buys.
* `presend_live_realized` gets `flow: {b1, b2, s1, s2, fleet1, bots1, retail1}`.
* Line, once per fill:
  `PRESEND LIVE FLOW (log) wN MINT: +1 buys X.XX (bots a, fleet b, retail c) sells Y.YY | +2 buys … sells …`.
* The status line gets `| FLOW LOG fills N closed N trades N (x.x us each)`.

## Cost

All on the main loop; never on the sender.

* A trade on a mint without a followed fill costs one map lookup: **6 ns** (`dip48_main_loop_cost`).
* A trade on a followed mint is classified (one base58 encode for the rival prefixes) and accumulated: **0.94 µs**.
  Only the trades of the ≤4 slots after a fill are classified.

## r84 check

`ops/flow48/r84_fixture.py` builds `testdata/dip48_flow_r84.json` from the run log's `presend_live_tape` records. For all 11 r84 fills, the
engine accumulator's outside buy and sell SOL through fill+1 and fill+2 equals the Python recomputation exactly
(`dip48_r84_tapes_match_recomputation`; b1 per fill: 2.447, 0, 0, 1.384, 0, 3.429, 4.056, 0, 1.577, 0.494, 0).

## Fresh-holders skip (arm-time, LIVE-capable): `--presend-live-fresh-skip T2PCT:RAPCT`

* **Evidence.** Replay on 2,494 real fills r49–r85 (`~/sniper-data/fix8283/fresh_holders.txt`):
  * T2 at ≥35% blocks 29 fills (11W/18L) and saves +1.76 SOL; that includes 3 of our 4 worst rugs.
  * Re-arm at ≥20% blocks 71 fills (21W/50L) and saves +1.51 SOL.
* **Flags.**
  * `--presend-live-fresh-skip T2PCT:RAPCT`: each lane is 0 (off) or 5..90; both 0 is refused; default off. Suggested 35:20.
  * `--presend-live-fresh-skip-mode log|live`: default log.
  * Both need `--presend-live-f3-log`; without it the engine refuses to start.
* **Hot keys.**
  * `fresh_skip`: log | live.
  * `fresh_skip_spec`: "T2:RA" (each 0 or 5..90).
  * The rules are as for every dip47 key: absent = the start value, a bad value keeps the old one.
  * Both keys are in the filter state.
* **Metric.** Exactly the logged `f3.fresh`, computed by `f3_fresh()`:
  * the holders with at least 2% of supply and at most 1 hold on record, leaving out us and the window's whale or dumper, summed as % of supply;
  * computed at the same point as the arm records' f3 (T2: the trigger's slot; re-arm: the re-arm clock at the arm).
* **When it runs.** It is an arm-time check, so it adds nothing on the sender.
  * T2 lane: decided after S1 and grp_t2.
  * Re-arm lane: decided at the start of `rearm_arm` (a check or a deferred window arming).
  * Wide windows are never checked.
* **Live.** The window is not armed. The skip is written as `presend_live_skip {why: "fresh_holders", fresh, fresh_n, thr}`; re-arm skips also
  carry `kind: "rearm"`. It is counted in the skip stats.
* **Log, or below the threshold.** The window arms as before. The arm record gets `fresh_skip {pct, n, thr, would_skip}`, and the window's fill
  record gets the same object.
* **Probes.** dip46 probe kind `fresh_holders` is added and is in "all". A T2 window it skips gets a probe window, like the other arm-time
  skips. Re-arm skips get no probe window (dip46 probes T2 arm-time skips only).

# dip47: GRPSIGN log, hot control keys, filter state

Branch `dip47-grpsign`, built on dip46 (f38ee0d7). Code: `src/bin/snipe_engine/psgrp47.rs`, `psctl47.rs`, `Detector::grp_now` in
`src/presend_live.rs`. Tests: `dip47_tests.rs` and `presend_live::tests::dip47_grp_now_equals_landing_version`.

With no new flag and no new control key, every decision, send, fee and exit is the same as dip46. The golden digest (`DIP25_GOLDEN`) still
matches once the filter-state fields are taken out (see "Filter state"). Those fields are written by every dip47 build.

## 1. GRPSIGN (log only): `--presend-live-grpsign-log on`

* Default: off. It needs `--presend-live-ann on`, because the hold clocks are kept only with the annotations on. Without the annotations the
  engine refuses to start.
* **Definition.** This is the dip30 GROUP RISK metric, the same one as the fill annotation's `ann.grp_pct`:
  * take the holders with at least 2% of supply, our wallet left out, the top 12 by holding;
  * keep each one with at least 5 holds at risk and a 3-slot sell hazard of at least 0.3 at its hold age;
  * add up their holdings (% of supply, in the same order).

  `Detector::grp_now` computes it without allocating. A test on 400 random states (ties, our wallet, hold clocks) shows it is
  bit-identical to the landing version.
* **State at signing.** The sender signs every try from its window copy (`SWin`). After each trade of the armed mint, the main loop refreshes
  that copy's curve and `pos`, and the landing-guard set the try carries (`grd_set`, which reads the detector's holder book and hold clocks).
  With this flag on, at that same moment and from the same detector state, the main loop also computes the group and keeps it per window,
  keyed by that trade's `pos` (a ring of 64; one snapshot is also taken at the arm). The source is the detector's tracked holder book (the
  feed's trades), the same one the landing annotation reads. It is not the true-balance / fam snapshot.
* **Matching a try to its state.** When a real try is registered (`drain_atts`), its `sign_pos` (the SWin `pos` the sender read) is looked up:
  `exact`, otherwise the newest snapshot at or before (slot, idx) (`before`), otherwise the arm's (`arm`). This is done for the window's
  FIRST real try and for the try that FILLED. Probe tries and probe windows (dip46) are never looked at.
* **Cost.** Nothing runs on the sender thread for GRPSIGN: no new SWin or Att field, no lock, no read. The work is on the main loop and uses
  only state already held (no RPC). Measured in `dip47_added_time` (release build, a token with 400 holders): **545 ns** per trade of an
  armed mint.
* **Records.**
  * `{"ev":"presend_live_grpsign", w, mint, kind (t2|rearm|wide|qf2), slot (the try's send slot), at ("first_try"|"fill_try"), try, grp_pct, n,
    members [{w, pct}], would_block_t2 (kind t2 && grp_pct >= 3), would_block_6 (grp_pct >= 6), whale_in, grp_pct_x, would_block_t2_x,
    sign_pos, snap_pos, snap_slot, match}`.
  * `grp_pct_x` is the same group without the window's trigger whale or re-arm dumper.
  * `presend_live_fill` gets `grpsign: {pct, would_block_t2, pct_x, would_block_t2_x}`. If no snapshot was found:
    `{pct: null, miss: true}`.
* **Line.** Once per window, at its first try: `PRESEND LIVE GRPSIGN (log) wN MINT kind: X.X% (n) [whale out Y.Y%] -> would skip | no`.

### r82 parity: signing vs landing (ops/grpsign47/parity_r82.py)

r82 has no dip47 records. As a stand-in for the signing-time group it uses the fill's `ann.guard.set[].sign_pct`. That is the landing-guard
set: the same risky-holder test, chosen at the same main-loop moment from the same state, but capped at the top 4 risky holders. No r82 fill
has a full set of 4, so the sum is exact here. Output: `~/sniper-data/dip47/parity_r82*.txt`.

| set | fills | corr | landing ≥3 & signing <3 | signing ≥3 & landing <3 |
|---|---|---|---|---|
| all (as specified, whale in) | 145 | 0.506 | 2 (1.4%) | 47 (32.4%) |
| T2 (as specified) | 105 | | 1 (1.0%) | 45 (42.9%) |
| re-arm | 40 | | 1 (2.5%) | 2 (5.0%) |
| T2, trigger whale left out | 105 | | 8 | 6 |

The trigger whale is in the signing group on 48 of 105 T2 fills. At landing it has usually dumped already (that dump is why the try filled),
so the landing group no longer counts it. Measured at signing, "grp ≥ 3% on T2" (whale in) would therefore skip about 55% of T2 fills, not
the replay's selected few. This is why the live rule (`grp_t2`) leaves the whale out by default (key `grp_t2_whale`).

## 2. Hot control keys (new): `--presend-live-ledger-control FILE`

* The file is re-read every ~10 s, when its mtime changes (the ctl43 pattern).
* An ABSENT key means the start flag's value.
* A BAD key means its old value stays: one `presend_live_ledger_mode {ok:false, key, err, value, kept}` record and a line per bad key. The
  other keys in the file still apply.
* An unreadable file means nothing changes, plus one `{ok:false, dip47:true}` record.
* Every change writes a `presend_live_ledger_mode {"dip47": {key: new}, "was": {"dip47": {key: old}}}` record and a
  `PRESEND LIVE LEDGER MODES dip47: key old -> new, ...` line.
* At start the banner line `DIP47 CONTROL KEYS (path): ...` lists the keys.
* The control file still needs one of the ledgers at start (`--presend-live-wh-loss`, `--presend-live-holder-loss`, `--presend-live-botdepth`
  or `--presend-live-dumper-ledger`), as in dip46.

| key | values / bounds | needs at start | applies to |
|---|---|---|---|
| `floors` | off \| t2 \| all | `--presend-live-guard holders` | off: empty floor set on every window (deadline + CURVE band only); t2: no floors on re-arm windows; all: both. Armed windows are refreshed. The band and deadline are unchanged |
| `wh_kinds` | t2 \| rearm \| all | (whale ledger) | the whale ledger's live rule (`--presend-live-wh-kinds`) |
| `size_t2` | SOL, (0, `--presend-live-size-sol`] | | T2 windows armed after the change (open windows keep their size) |
| `size_rearm` | SOL, (0, `--presend-live-rearm-size-sol`] | `--presend-live-rearm on` | re-arm windows armed after the change |
| `mint_ledger_sol` | 0.01..1.0 | `--presend-live-mint-ledger` | the mint ledger's loss |
| `wh_loss` | "N:SOL", N 1..50, SOL (0, 5] | `--presend-live-wh-loss` | whale ledger |
| `holder_loss` | "PCT:SOL:WIN" (PCT (0,100], SOL (0,5], WIN [0,5]) | `--presend-live-holder-loss` | holder ledger |
| `botdepth` | "N:SLOTS", N 1..BD_K, SLOTS 1..BD_SLOTS_MAX | `--presend-live-botdepth N:SLOTS` (list gate) | the gate's threshold (the sender takes it on its next loop) |
| `curve_deep_pct` | 0.05..0.95 | `--presend-live-guard-curve-deep` | the CURVE band's D (the sender takes it on its next loop) |
| `min_age_slots` | 0..50 | | the young-age gate (also the wide tier's min age) |
| `exit_ms` | 50..10000 | `--presend-live-exit-ms > 0` | positions opened after the change |
| `tp`, `sl` | 0.02..0.9 | | positions opened after the change |
| `grp_t2` | log \| live (log) | `--presend-live-grpsign-log on` for live | the GRPSIGN T2 skip (never re-arm or wide) |
| `grp_t2_pct` | 1..20 (3.0) | | its threshold, % of supply |
| `grp_t2_whale` | out \| in (out) | | whether the trigger whale counts in the group |
| `rearm_max_per_mint` | 0..10 (0 = no cap) | flag `--presend-rearm-max-per-mint N` | re-arm FILLS per mint this run; at N no new re-arm window arms on it: `presend_live_skip {kind:"rearm", why:"rearm_cap", rearm_fills, cap}` (a waiting window: dropped "rearm_cap"). T2 unaffected |
| `pause_window` | "HH:MM-HH:MM[,...]" PKT (UTC+5), ≤4 windows, "" = none | flag `--presend-live-pause-window` | wall clock (UTC → PKT, not slots); inside: no new arm of any kind (T2, wide, re-arm, probe windows), skips counted under "pause_window" (no record per trigger); ON / OFF: one `presend_live_ledger_mode {pause_window:"on"\|"off", window, skipped}` + `PRESEND LIVE PAUSE WINDOW ON 23:00-02:00 PKT` / `... OFF`. Crosses midnight. Open positions exit as usual |
| `pause_now` | on \| off (off) | control key only | manual pause, same effect (window "manual") |

**`grp_t2` live is an ARM-TIME skip.** The signing-time value of a window's first try only exists once that try has been signed, which is
after the first send. So the rule runs at the T2 arm, on the detector state at the trigger. That state is exactly what the window's first
try signs with, unless another trade of the mint arrives between the trigger and the first try (about 50 ms). A window that passes is not
stopped later. The skip goes out as `presend_live_skip {why:"grp_t2", grp_t2:{pct, thr}}`, is counted in the skips, and is decided after
S1 (the last arm-time gate).

**The sender side.** Botdepth, the CURVE D and floors-on-re-arm are read by the sender from its own Cfg copy. On each loop the sender does
one relaxed atomic load (`Sh47::ver`), measured at **1.6 ns**. Only when that value moved does it copy the new values under a lock.

### All hot keys in the engine (the same control file)

| key | values | reader | needs |
|---|---|---|---|
| whale, holder | live \| log | pshl | wh-loss / holder-loss |
| skip2 | live \| log | pshl | `--presend-skip2-log on` |
| blocklist_send | live \| log | pshl | blocklist per-send |
| s1 | live \| log | pshl | `--presend-live-s1-log on` |
| botdepth | live \| log (log refused unless `--presend-live-botdepth-allow-log`) | pshl | botdepth |
| widedumper, qf2 | live \| log | pshl | dumper ledger / qf2 |
| qf2_size | SOL (0, 2], ≤ the start's largest size | ctl43 | qf2 |
| qf2_min_age | slots 0..10000 | ctl43 | qf2 |
| quiet, quiet3a, create_slot, young_age, lone_whale, cr_loss, blocklist_arm, rearm, rearm_r5, breaker | live \| log | ctl43 (A9) | |
| mint_ledger, stall, deadman, fanout, dump_exit, curve_deep | live \| log | ctl43 | each its own flag |
| fpnb_t2, fpnb_rearm, fpnb_strict | live \| log | ctl43 | `--presend-fpnb-log on` (strict: `--presend-live-fpnb-strict`) |
| exit_lots | off \| ab \| live | ps43_b | `--presend-live-exit-lots` |
| probe46 | on \| off | psprobe46 | |
| ab46 | {filter: ab \| live} | psprobe46 | `--presend-live-filter-ab` |
| floors … pause_now (the table above) | | psctl47 (dip47) | |

(FP-NOBOT's own `--presend-fpnb-control` file is separate and is read on the FP thread.)

## 3. Filter state (always on)

* `PsLive::fs_map()` builds one object with:
  * every hot key above, as its mode or value (a feature that is off: `"off"`);
  * the new keys' values and `grpsign_log`;
  * the start-only settings that decide: `guard` (mode, holders spec, ab), `fee_tier`, `routes` (class names + `spec_hash`), `limits`
    (max_sol, kill_switch_sol, profit_lock as given), `drop`, `k`.
* It has a version `fv`, which bumps on every real change, and `fh` (the first 8 hex of the object's sha256).
* **When it is checked.**
  * At start: fv 0.
  * At once after any control reader applied a change (their change counters are watched every tick).
  * After a dip47 key change.
  * Every ~1 s as `auto` (this catches the FP thread's own control file).
  * Re-reading the same values never bumps `fv`.
* **Record.** `{"ev":"presend_live_filter_state", fv, fh, src ("start"|"control"|"auto"), state, changed: {key: [old, new]}}`.
* **Line.** On every change after start: `PRESEND LIVE FILTER STATE fv=N: key old->new, ... (src)`.
* **Stamps.**
  * `fv` and `fh` on: presend_live_arm, presend_live_skip, the re-arm's arm record, presend_live_fill, presend_live_realized,
    presend_live_exit, presend_live_close, presend_live_dump_exit, presend_live_filter_ab and every presend_live_probe* record.
  * The sender's probe and A/B records are stamped in the writer thread, never on the send path.
  * `presend_attempt` (the shadow's) carries `fv` only.
  * Records of a window (fill, realized, exit) carry the state at the window's ARM, plus `fv_fill` when the state moved since then.
  * fill and realized also embed the full state as `filters`, so one record can be read on its own.
* **Cost** (`dip47_added_time`): stamping a skip costs 145 ns and a fill (with the cloned `filters`) 2.7 µs. Both run on the main loop,
  never on the sender.
* **Golden.** `dip26_tests::strip47` / `strip47_text` take out exactly these additions: the state records and lines, fv / fh / fv_fill,
  `filters` on fill / realized, and `"fv"` on the shadow's lines. After that, every golden (DIP25 digest) still matches.

Join example (realized P&L by a filter's mode at the arm):

```python
import json, collections
by = collections.defaultdict(lambda: [0, 0.0])
states = {}
for l in open("dip_ams_rNN.jsonl"):
    r = json.loads(l)
    if r.get("ev") == "presend_live_filter_state":
        states[r["fv"]] = r["state"]            # the full state per version (for records that carry only fv)
    elif r.get("ev") == "presend_live_realized":
        f = r.get("filters") or states.get(r.get("fv"), {})   # realized embeds its arm state; fv joins otherwise
        k = (f.get("botdepth"), f.get("size_t2"), f.get("grp_t2"))
        by[k][0] += 1; by[k][1] += r["pnl"] / 1e9
for k, (n, pnl) in sorted(by.items(), key=str):
    print(k, n, round(pnl, 3))
```

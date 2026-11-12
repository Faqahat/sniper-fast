# dip49: T2 rival gate (Rule A) and the re-arm fresh-holders f1 definition (Rule B)

dip49 = dip48 (74783407) + the two rules below. Branch `dip49-rival`. Code: `src/bin/snipe_engine/psrival49.rs`, the RIVAL TAP in
`src/feeds/mod.rs` / `grpc.rs`; tests `dip49_tests.rs`; fixtures `ops/rival49/make_fixtures.py`.

With none of the flags set, the decisions are dip48's (the golden digest; the filter-state object gains the keys `rival_gate` "off",
`rival_gate_spec` null, `fresh_skip_ra_def` null). Evidence: `~/sniper-data/rugdet/report.txt` §A items 1–2.

## Rule A: T2 rival gate (per try, like botdepth / fpnb)

Flags:

* `--presend-live-rival-gate R0:R2:AGE_H` (off; owner setting 0:2:1);
* `--presend-live-rival-gate-mode log|live` (log; run live);
* `--presend-live-rival-gate-slots N` (20, range 1..60).

Hot keys: `rival_gate` (log|live) and `rival_gate_spec` ("R0:R2:AGE_H"; R0 0..10, R2 0..20, AGE_H 0..720). Both are in the filter state.

**Rule.** It applies to T2 windows only; re-arm windows, wide windows and probes are never gated. A T2 try signed in slot s is withheld when
`rivals ≤ R0` OR (`rivals ≤ R2` AND dev age < AGE_H hours). In live mode the try is withheld and counted as not-sent
`rival_gate_withheld`. In log mode the try is sent and the case is counted as would.

| term | definition (rugdet code) |
|---|---|
| rivals | `slipsg20` (`s5_tape.py`). The DISTINCT fee payers of FAILED executed txs on the mint whose error is an InstructionError with Custom code 6001 / 6002 / 6003 / 6024 / 6040 / 6042 (any instruction), in slots [s−N, s−1]. Our wallet is out; the fleet and every other bot count (9Ye53E65's one rival is the fleet payer GaasGwtD). rugdet's window `(cut−20, cut]` with `cut = fill−2` is the same window, because the filling try was signed in slot `fill−1`. |
| dev age | `s14_devcombo.py`: `(create time − blockTime of the creator's OLDEST tx before the create signature) / 3600`. It is 0 when the create is the creator's first tx. 1000 results (capped) means old. |
| unknown | An RPC error (e.g. CK −32020 for old history), no answer yet, or no create seen. Unknown counts as NOT young, so only `rivals ≤ R0` can block. |

**Data.**

* The executed gRPC feed sends every failed tx with a slippage-type code to the main loop through the RIVAL TAP (a bounded channel; a full
  channel drops and counts). The main loop matches the tx's account keys against the followed tokens and keeps, per mint, the 16 most recent
  distinct payers (each with its last two slots). It copies them into the armed T2 window's SWin.
* The dev age is looked up ONCE per creator, queued at the token's create (followed tokens), by 2 background workers. They call
  `getSignaturesForAddress(creator, {before: create sig, limit: 1000})` with the funder log's RPC setting; the URL is never printed. The
  answer is cached per creator. The send path never waits for it.

**Fail open** (never withheld; the reason is in `open`):

* `stale`: no slippage fail seen on any mint for 60 s (the feed's fails are missing, so every mint would read 0 rivals);
* `blind`: the executed feed's blind episode.

**Records.**

* `presend_attempt` and `presend_live_fill` get `rival_gate {rivals, dev_age_h, young, dev_age_src, on, blocked, open?}`.
* `presend_live_realized` gets `rival_gate {rivals, dev_age_h, blocked}`.
* One record per window, about 2 s after its last try:
  `presend_live_rival_gate {tries, passed, withheld, would, open, rivals_min, dev_age_h, dev_age_src}`, plus the line
  `PRESEND LIVE RIVAL GATE (mode) wN …`.
* The status line gets `| RIVAL GATE fails … matched … | dev age cache … pending … calls … errs … | tap drops …`.

**Sender cost.** The sender reads the window's copy (already cloned) plus 5 relaxed atomic loads. No lock, no allocation. See the
`DIP49 RIVAL GATE sender cost` line in `dip49_sender_cost`.

**9Ye53E65** (r85 w34, fill slot 468340087, −0.78): the recorded fails give rivals 1 (= rugdet slipsg20) and the dev age is 0.92 h, so
the try is WITHHELD (`dip49_9ye53_withheld`).

## Rule B: re-arm fresh-holders f1

* Flag: `--presend-live-fresh-skip-ra-def f1|f3`. The default is f3, which keeps dip48. Hot key: `fresh_skip_ra_def`.
* It needs `--presend-live-fresh-skip T2:RA`. The owner's run: `--presend-live-fresh-skip 35:15 --presend-live-fresh-skip-ra-def f1`
  plus the mode.
* **f1** (`s4_feat.py` `f1_pct`): the holders with ≥2% of supply, top 12, with ≤1 hold on record. Left out: us, the dumper, and the R5
  holder (the largest holder at the re-arm check, when R5 ran). The result is their summed share.
* **f3** (dip32/dip48): the top 16 holders, with us and the dumper left out.
* Both values, and which one decided, are logged in the re-arm arm record's `fresh_skip.def` {def, f1_pct, f1_n, f3_pct, f3_n} (and on a
  live skip as `fresh_def`).
* **Parity.** `dip49_f1_parity_rugdet` runs the engine's f1 selection on the r83–r85 fills' recorded holder sets; it equals rugdet's
  f1_pct / f1_n exactly.
* **Caveat.** rugdet computed f1 from the FILL annotation, i.e. at our landing. The engine has to decide at the re-arm ARM, so it computes
  f1 on the arm-time state. The replay's +1.46 / +1.67 is landing-time; the arm-time value can differ.

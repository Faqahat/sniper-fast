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

## dip49b: dev-age lookup fix (r87: 900 of 900 lookups were "error")

* **Cause.** dip49 asked `getSignaturesForAddress(creator, {before: <create sig>})` AT the create. The brand-new signature is not
  indexed yet at that moment, so every call failed.
* **Fix.** The call is now `getSignaturesForAddress(creator, {limit: 1000})` with no `before`.
  * 1000 results = capped = old.
  * Otherwise the age uses the OLDEST entry: `create time − its blockTime`, at least 0. If the create is the oldest entry, or the list has
    only txs at or after the create, the age is about 0 (brand new).
  * An empty list (not indexed yet), a missing blockTime, or an RPC error is retried after 1 s, 3 s and 8 s. The job is queued again with a
    due time, so the worker never sleeps on it.
  * After that the age is "error" (unknown, so not young). A T2 trigger on the mint asks once more (once per creator).
* **Error text.** It is rpc-scrubbed and recorded:
  * `presend_live_devage {creator, ok: false, dev_age_err}` plus a line `PRESEND LIVE DEV AGE error …`, once per failed creator;
  * `dev_age_err` on the window's `presend_live_rival_gate` summary, and on its line.
* **RPC.** `--presend-live-devage-rpc URL` (`${VAR}` expanded). The default is the funder / FAM RPC setting, then rpc_url. The URL is never
  printed or recorded. The engine loads `/root/sniper/deploy/.env` (or `--env-file`) at start, so
  `https://mainnet.helius-rpc.com/?api-key=${HELIUS_API_KEY}` expands.
* **Tests.**
  * `dip49b_retry_and_error_text`: a mock RPC returns an indexing-lag error, then an empty list, then success; the success is kept. A
    lookup that always fails ends with its scrubbed text recorded. The T2 trigger's extra try happens once.
  * `dip49b_9ye53_dev_age_offline`: the creator C6XLWkbj's cached history (oldest blockTime 1794443385, create 1794446703) gives
    0.9217 h, which is rugdet's 0.92.

## dip49c: the payer fallback, a self-test, and the start / first-success lines

* **Cause** (r88: every lookup returned "empty signature list"). On platform launches the token's creator is an address that never signs,
  so its history is empty and stays empty; retrying cannot fix it.
* **Fix.** The create tx's fee payer is recorded at the create. The lookup reads the CREATOR's history first.
  * If it is empty and the payer differs, the lookup reads the PAYER's history.
  * If both are still empty after the retries, the age is 0 (a brand-new address).
  * `dev_age_src` is `creator` | `payer` | `empty0` | `capped` | `error`.
  * `--presend-live-devage-fallback payer|none` defaults to payer. `none` is dip49b: an empty creator stays unknown, which is how the
    rugdet replay treated the 96 fills whose creator had no cached history.
  * A creator that has txs only at or after the create reads as age 0. That is the same as rugdet's `n_prior = 0`.
* **Live lines.**
  * At start: `DIP49 RIVAL GATE: DEVAGE rpc host <host> (<flag>) …`, with the host only, never the key.
  * The first answer: `DEVAGE OK first lookup src=… age=… creator …`, plus a `presend_live_devage {ok: true, first: true}` record.
* **Self-test.** It runs the production path standalone: the same workers, RPC client, pacing, retries and fallback, and the same `${VAR}`
  expansion after the engine's `.env` load (`--env-file`, default `/root/sniper/deploy/.env`). No wallet, keystore, feed or send.

  ```
  snipe_engine --devage-selftest launches.jsonl --presend-live-devage-rpc 'https://mainnet.helius-rpc.com/?api-key=${HELIUS_API_KEY}' \
      [--presend-live-funder-rps 15] [--presend-live-devage-fallback payer|none] [--env-file /root/sniper/deploy/.env]
  ```

  * Rows: one JSON per line, `{mint, creator, payer, sig | create_sig, bt | create_bt}`. The recorder's `launches.jsonl` lines work as is.
  * Output: one line per row (age_h, src, error text, latency), then `DEVAGE SELFTEST SUMMARY` (% resolved, % per src, calls / errors /
    retries) and each distinct error.
  * Checked here on the public RPC (rps 2) with 19 launches from `run_20261112_0307`, including r88's 5PuRg77K, FW6U98K7 and 5VX7S1ap:
    100% resolved (capped 8, creator 7, payer 4). The 11 rate-limit errors were all retried successfully.

# APEX-PROBE (2026-11-03)

Separate binary `apex_probe` (src/bin/apex_probe/), not part of the dip engine. Strategy: APEX S2
(/home/it/sniper-studies/sniper-apexsnipe/REPORT.md + FROZEN.md): a creator on the watchlist launches → buy in the create slot, fired
straight from the create shred (no RPC on the hot path) → sell everything 2 s after our confirmed fill. Its job is to
measure how fast we land after a launch.

## Modes
- `--mode shadow` (default): never sends, needs no passphrase (throwaway signer; the config wallet's pubkey is the payer,
  so the would-be tx is the real shape). Logs each would-be buy (rx→signed µs, route, copies, tips) and, 6 s later, the
  real landscape of that launch: the create's slot/index, buy txs after it in the create slot and the next slot.
- `--mode live`: refuses to start without `--kill-below` and `--max-runtime-min`; size ≤ 0.1 SOL (default 0.05); max buys
  (20); max SOL at risk incl. fees (1.5 = realized net loss + the open position's worst case); one position at a time.
  The on-chain slot guard (Lighthouse, verified by simulation at start) makes a buy fail after create slot + 1.

## Hot path
create shred (deshred/entries feeds) → detect_launch / router create → watchlist match (CreateEvent creator) → skip rules (non-SOL
quote, Mayhem, creator fee, legacy create) → gate (caps, balance from the 2 s poller) → min_tokens_out = expected tokens
after the dev buy / 1.2 → buy v3 (+ ATAs, slot guard, tips) compiled + signed with the cached blockhash (or a durable
nonce) → async paths spawned first, then the dip engine's own HTTP/1.1 connections and UDP from the hot thread.

## Records (`--out`, JSONL, one per event)
start, create_seen (skips), buy_shadow / buy_sent (t_rx, t_decide, per-path send offsets), send_ack / fast_ack,
buy_landed / buy_failed (slot, index, create→our tx first seen in the shreds, tokens, fill vs expected),
sell_sent / sell_landed / sell_failed, position (src feed = executed feed; src block = getBlock check: idx delta,
buyers ahead, SOL ahead, rank, dev buys in the create), realized (P&L from getTransaction balance changes of every
landed tx), end_check, summary.

Report: `python3 ops/apex_probe/report.py run.jsonl` (GMGN link, create→land ms, slot delta, position, buyers ahead, P&L).

## FRA
`ops/apex_probe/run_apex_probe.sh` builds `/root/apex/apex_probe.toml` from `/root/sniper-dip/dip_probe.toml` + the side path
files (wallet 2g7rYv7y…, keystore /root/prod/wallet-prod.enc) and runs `/root/apex/apex_probe`. It refuses while a dip
engine runs on the server unless `--allow-dip` (same wallet; shared Helius 1 req/s and other send limits).

## APEX-PROBE-FIX (11-04): CreateEvent creator match + APEX-3 entry score
**Match.** `--match creator` (default) now matches the pump.fun CreateEvent `creator`, the key every APEX backtest uses
(x1_extract / s3_sim / ev3.watch). Shreds carry no logs, so it is derived: holder-reward launch (create_v2 flag) → the PDA
`["holder-rewards", mint]` of the pump program; otherwise the create args' creator. On the 11-03 tape (18,901 creates) the
event creator differs from the create's user on 3,529: 3,405 holder-rewards PDAs + 124 args creator ≠ signer. All 9 r10/r11
fills that were not backtest picks were holder-reward launches of a watched signer (the old match read the args creator =
the signer). `--match args` = the old behaviour, `signer`, `either` (event creator or signer). Records: `creator` (args),
`ev_creator`, `match_key`, `holder_reward`. The buy itself still uses the args creator (unchanged build).

**Entry score.** `--entry-filter log|on|off` (default **log**: computed and recorded on every buy_shadow / buy_sent /
create_seen skip, never gates; `on`: computed after the bundle window, before signing, skip `entry_score` when
score < thr), `--entry-model PATH` (default /root/apex/entry_model.json), `--entry-thr X` (override). Record field `entry`:
score, thr, pass, x (11 features), dev_src, bund_src, bund_unseen, u_src, bt, us.
- Model file: `python3 ops/apex_probe/entry_export.py [--code /home/it/sniper-studies/sniper-apexcmp/code] [--out DIR]` imports the APEX-3
  code (run3_lib / ev3 / gbdt_np) and writes entry_model.json (LIVE: trained on every recorded day, thr = q0.5 of the last
  day's picks scored by that day's model, as run4 "entry q0.5"), entry_model_val.json (last day's own model),
  entry_cases.jsonl (that day's launches with run3_lib's X row + score) and watchlist_apex3.json (the APEX-3 walk-forward
  watchlist for the next day, CreateEvent creators, bundle_txs_median hints).
- Port: features exactly as run3_lib X (history label means in float32 where run3_lib's are, numpy pairwise sums), gbdt_np
  bins (32-quantile edges, side=right, NaN=0) and F0 + Σ 0.05·leaf.
- Create-time inputs: dev_sol = first create leg, bund_sol / bund_users = bundle legs after the create (lenient leg reader:
  top-level pump buys incl. multi-wallet txs, rapidlaunch / GMGN / terminal wrappers; buyer = the buy's `user`), exact pump
  math (exact-in: largest n with n + ⌈0.95% n⌉ + ⌈0.30% n⌉ ≤ spend; cap: ⌊a·v/(t−a)⌋+1).
- NOT visible before signing (approximations, measured on the 546 day-7 picks with thr 1.395):
  - u (create index / block size): PoH position when the create came with PoH, else the training median (u_src).
    Median instead of the true u flips 15/546 decisions (5 lost, 10 added).
  - creator history: frozen at the export; the backtest also uses same-day launches ≥ 15 s old. A file frozen at the
    start of the day flips 46/546 (6 lost, 40 added) → re-export before a run.
  - bundle: only what the first-or-revert window saw (`--bundle-wait auto` waits only for creators with a bundle hint ≥ 0.5);
    bundle forced to 0 flips 21/546 (all lost).
- Validation: `apex_probe --entry-validate entry_cases.jsonl --entry-model entry_model_val.json [--entry-txs entry_txs.jsonl]`
  (entry_fetch_txs.py fetches the raw create + bundle txs of a sample from a public RPC).

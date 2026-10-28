# copypaper — paper forward test of copy-trading the E2x1 cluster (agent "copypaper", 10-28 PKT)

Rules are frozen in **FROZEN.md** (read that first). PAPER ONLY, local only. Live table: **RUNNING.md** (PKT, rebuilt every cycle).

## Files
| file | what |
|---|---|
| `cp_decode.py OUT CHUNK...` | raw recorder chunk (`txs_*.jsonl.gz`) → compact npz (all curve TradeEvents, PumpSwap events, migrations, completes, creates, per-slot block sizes). ~2 s and ~2.4 MB per 5-min chunk. |
| `cplib.py` | Tape (merged chunks, block clock), signal extraction, the frozen simulation (`simulate`), window aggregate (`summarize`). Curve maths = ourspeed/o2_sim.py = sniper-haqqml/sim.py. |
| `cp_score.py --start BT --end BT` | scores one window: finds/decodes the chunks covering [start−400, end+2100] (local keeper copies under /home/moiz/sniper-data/collect; a chunk the keeper has not copied yet is fetched read-only from FRA with `ssh … sudo cat`, decoded, raw copy deleted), appends one line to `out/results.jsonl` and one per signal to `out/trades.jsonl`, carries lockouts in `out/state.json`. `--mode ourspeed` = replica of ourspeed's B copy-trade for validation. |
| `cp_table.py` | `out/results.jsonl` + `out/trades.jsonl` → `RUNNING.md` (per-window rows, running totals, pass-bar status, top/bottom trades with GMGN links). |
| `loop.sh` | every 2 h (windows aligned on 10-28 23:00 PKT) scores the next window once its 1800 s look-ahead is recorded (≈ 40 min after the window ends), rebuilds RUNNING.md, prunes decoded caches no longer needed. 48 h. Stop: `touch STOP` in this folder. Pid: `out/loop.pid`; log: `out/loop.log`. |
| `delay_q.json` | our live landing-delay quantiles (copied from ourspeed), rescaled to median 66 ms. |

## Disk / footprint
- Decoded cache ≈ 2.4 MB per chunk; a cycle keeps ≈ 35 chunks (≈ 85 MB). Raw chunks are never copied locally unless the keeper lags (then fetched to the scratchpad and deleted right after decoding). Total footprint < 150 MB; validation caches (`val/cache*`, ≈ 0.5 GB each) are deleted after validation.
- Disk guard in loop.sh: < 20 GB free → lean mode (no server fetch, local keeper copies only, caches pruned); < 15 GB free → no scoring (log + sleep 30 min, retry). The keeper's own rule (pause copying at ≥ 95 % used) is untouched. Disk was 27 GB free (92 %) at loop start, 10-28 23:11 PKT — the recordings grow ~17 GB/day, so the keeper may pause copying before the 48 h end; windows then wait (cp_score retries every 10 min) and resume when chunks appear. The loop does not create any copy outside its own ≈ 100 MB.

## Data notes
- Recorder gap: version-1 txs (~3.5 % of trades, some routers) are not recorded. The cluster's own txs were ~100 % recorded in recon (1 sell missed in 2 days). A missed cluster sell makes us hold to the 1800 s timeout — counted in the `t/o` column.
- The daily collector hand-over (≈ 19:05–19:30 PKT): both runs' chunks are used, tokens created before the new run started and traded after the old run's tail are not recorded by either (OLD-band tokens). Such signals show as timeouts/unresolved.

## Validation (val/)
- D1 ourspeed-replica: raw +11.9 / cal +0.2 vs ourspeed +13.2 / +1.5; 1,318 of 1,340 lots identical to < 1 mSOL; the gap is the 22 PumpSwap exits (pool-state sell vs his realized price) — details in FROZEN.md.
- D0 ourspeed-replica: raw −8.26 / cal −22.46 vs ourspeed −7.7 / −21.8; 1,309 of 1,320 lots identical, non-PumpSwap difference 0.000, the 11 PumpSwap exits −0.98.
- Frozen rules: D1 raw +7.69 / f20fast −2.32 / cal −0.69; D0 raw +1.46 / f20fast −11.65 / cal −8.45 → the bar would FAIL on both back-days. Per-window lines in `val/d0_results.jsonl`, `val/d1_results.jsonl`; per-signal rows in `val/d*_trades_*.jsonl`.

## How to read RUNNING.md
`cal` is the headline (paper-vs-live gap removed); `f20fast` = followers haircut; `f20hold` is the literal whole-hold haircut (information only, see FROZEN.md); `ex-top5` = without the 5 best trades; running totals on the right. Pass bar line at the bottom of the table.

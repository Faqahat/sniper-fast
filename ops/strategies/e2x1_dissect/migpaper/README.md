# migpaper — paper forward test of the near-graduation rule (agent "migpaper", 10-28 PKT)

Rule frozen in **FROZEN.md** (artefact hashes in **FROZEN_SHA.md**). PAPER ONLY, local only, nothing sent, nothing deployed.
Live table: **RUNNING.md** (PKT, rebuilt after every 2-h window). Source: migrate/REPORT.md §7.

## Files
| file | what |
|---|---|
| `mplib.py` | window tape from grad/g1_decode.py chunks (VMIN=0: every curve trade, PumpSwap events, migrations, completes, creates, block clock), wallet / creator history stores, m1 features (verbatim port, V=105 first crossing), m3 replay (verbatim port, frozen exits, both entry modes), numpy GBDT predictor. |
| `mp_freeze.py` | run once: re-fits p30 / p120 (m2 code) and the continuation model (m3 code) on all rows < 10-28 20:00 PKT, exports them to numpy JSON (checked equal to sklearn), freezes the landing quantiles, builds `wstore.npz` / `cstore.npz` from migrate's wallets.npz + grad's meta.pkl, writes FROZEN_SHA.md. Also fits the train-only (m2/m3 exact) models used for the validation; they reproduce feat_p.pkl to 0. |
| `mp_score.py --start BT --end BT` | scores one window (see the docstring): local keeper chunks first, FRA `sudo cat` read-only only for chunks the keeper has not copied (raw copy deleted after decoding). Appends `out/results.jsonl` (window) and `out/trades.jsonl` (one line per entrable crossing, with both modes' replays when p30 ≥ 0.8), then extends the stores. |
| `mp_table.py` | RUNNING.md from results + trades. |
| `mp_validate.py` | the scorer (val models) on 10-28 vs the replay rows (sim_pre_2.0.pkl / sim_react_2.0.pkl), row by row. |
| `loop.sh` | every 2 h from 10-29 00:00 PKT for 72 h: score the next window once its look-ahead is recorded (≥ 25 min after the window end), rebuild RUNNING.md, prune caches older than the 3-h look-back. Stop: `touch STOP` here. Pid `out/loop.pid`, log `out/loop.log`. Disk: no scoring < 15 GB free, no server fetch < 20 GB free. |

## Data (`/home/moiz/sniper-data/e2x1_dissect/migpaper/`)
`models/` (p30/p120/cont + val_* + dly.json, 2.6 MB), `wstore.npz` (59 MB, grows ~10 MB/day), `cstore.npz` (3.5 MB), `cache/` (≤ ~160 MB, pruned), `out/`, `val/` (validation outputs; its cache is deleted). Footprint < 300 MB.

## Validation (10-28, see VALIDATION.md)
Scorer vs replay on the 10-28 test day: 52 shared entries identical to the lamport; day +4.13 (scorer, 59 entries incl. 6 post-hand-over rows the replay drops by convention) vs replay-in-windows +3.53 / report +3.66. One float32 rounding flip found and fixed before the run.

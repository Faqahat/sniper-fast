# Pre-send SHADOW (T2 "whale buy") in the dip engine (agent, 10-25 PKT)

Owner GO 10-25 ~02:00 PKT: "build pre-send shadow, we will add it for the next run".
MEASURED = a test, a replay or a timing run. INFERRED = my reading.
Nothing was deployed. No server was touched. Nothing was committed.

## Bottom line
- **What it is:** the study's pre-sent conditional buy with the T2 trigger, as a log-only shadow in the dip engine. It never
  sends and never changes a decision. Code: `src/presend.rs` (logic), wiring in `src/bin/snipe_engine/dipmode.rs`.
- **Exact match with the study (MEASURED):** 0 differences on 312 R3/R4 tokens (471 windows, 377 fills) and on the whole R4
  day (3,195 tokens, 1,192 windows, 579 fills). P&L per fill matches to the last float32 bit.
- **Off by default.** Without `--presend-shadow` nothing of it runs. The only changed existing line is the 60 s status
  line, which gets an extra part that is empty when the flag is off.
- **Cost (MEASURED on this machine):** 0.36 µs per trade on average, including its records. It runs after the IMIT1
  decision, any send and the exits of each tx, so it never delays a send.
- **Binary (not deployed):** `/home/moiz/sniper-data/strategies/presend/bin/snipe_engine_dip12_presend`, 78,224,608 bytes,
  sha256 `4f3fac863cd2788e8d6ff69e2197a6c611662f7b086fac3658281336b20fa6e7`.
  - Built from today's uncommitted tree (dip10 nonce fan-out + M2 shadow) plus this shadow. The M2 flags work as before.
  - Same file as `/home/moiz/sniper/target/release/snipe_engine` until the next build.
- **Found while porting (MEASURED replay, study code):** 29% of T2 windows (R4) are not "whale buys". They are the create's
  signer buying in its own create tx (see below). They lose money on all 4 study days. The shadow keeps them, because the
  study code has them. The evaluator splits them out.

## Flags
| Flag | Default | Meaning |
|---|---|---|
| `--presend-shadow` | off | turns the shadow on |
| `--presend-whale-pct` | 5 | holding (% of supply) at the wallet's first ≥ 3% buy |
| `--presend-window-slots` | 10 | window length after it goes live |
| `--presend-drop` | 0.12 | sudden drop vs the trailing reference that fills |
| `--presend-ref-ms` | 50 | trailing reference = the price this long before |
| `--presend-live-ms` | 50 | the window goes live this long after the trigger |
| `--presend-size-sol` | 0.55 | would-be buy size |
| `--presend-exit-slots` | 2 | sell this many slots after the entry slot |
| `--presend-tp` | 0.10 | take-profit (0 = none) |
| `--presend-sl` | 0.20 | stop-loss (0 = none) |

- Defaults are the study's chosen config ("T2|c" in ps6_select.txt).
- A `--presend-*` parameter without `--presend-shadow` is refused. A misspelled flag or a non-number is refused at start
  (checked on the built binary).
- Fixed, as in the study: the 3% first crossing, no trigger or fill at curve ≥ 100 SOL, window end 30 ms after the whale's
  first sell, a fill blocks the token until our sell + 300 ms, queue rows (a) / (b) / (c) = +0 / +5 / +10 ms.

## What it does (the study code's rules, ps4 + ps5 + ps6)
- **Clock:** the replay's block-position clock (slot × 212 ms + tx index / max(400, index + 1) × 212 ms), as M2 uses.
- **Balances:** tokens bought minus sold on the curve, per wallet, from the token's create.
- **Trigger:** a buy at curve < 100 SOL that takes a wallet to ≥ 3% of supply for the first time.
  - It counts only if the wallet is not the creator and not a create-slot insider, and the holding is ≥ 5% at that buy.
  - A wallet whose first ≥ 3% buy is below 5% never triggers later.
  - Supply = 1e15 raw units (pump.fun: 1e9 tokens × 10^6). The % is rounded to float32, as in the study.
- **Window:** from trigger + 50 ms to min(+10 slots, the whale's first sell + 30 ms).
- **Fill, per queue row:** the first trade in the window whose price is ≥ 12% below the price 50 ms earlier. We land after
  every trade up to that trade + 0 / 5 / 10 ms, and fill if the price there is still at or below the limit.
- **One window per token, per row:** a later trigger is "blocked" while one is armed (or until our sell + 300 ms).
- **Exit:** 0.55 SOL in after the trades ahead of us. Followers whose slippage our buy breaks are dropped (the study's slack
  table, by signature: reproduced exactly). Sell 75 ms into slot entry + 2, or one slot after a +10% / −20% slot.
- **Not followed:** tokens created before the engine started (no history), mayhem launches, and the study's non-standard
  curves.
- **Order:** a slot's trades are processed when the feed is 2 slots past it, sorted and de-duplicated. So a reordered or
  doubled delivery still gives chain order. Records come ~2 slots after the event; their `t` fields are feed arrival times.

## What it logs
In `--dip-log` (one JSON line each):

| Record | When | Main fields |
|---|---|---|
| `presend_arm` | each trigger | `w` (window id), mint, wallet, `pct`, `bal`, trigger sig / slot / idx / j / `t` (arrival ns) / `a` (block-position ms), `st`, `en0`, `age_slots`, `age_s`, sol, tok, curve, `rows` {a,b,c: armed / blocked / pending} |
| `presend_fill` | per row that fills | `row`, `x` (the crossing trade: sig, slot, idx, j, t, a, user, side, size, curve), `ref`, `p_x`, `drop_pct`, `lim`, `m` (last trade ahead of us), `n_ahead`, `a_land`, `ft`, `s_in`, `seller_is_whale`, `entry` {curve, fee, SOL in, tokens, prices}, `imit` {dump, env, pick, fired, m2} |
| `presend_exit` | per filled row | `exit_slot`, `hold_slots`, `why` (tp / sl / time), `pnl` (gross SOL, follower model), `pnl_naive` (no follower dropped), `pmin`, `xt`, `free_at`, `net_cheap` |
| `presend_disarm` | when the window is over | `why` (expired / whale_sold / filled / blocked / token_gone / run_end), `st`, `en`, `whale_sell`, `rows` {a,b,c: armed, filled, hit (late / untradeable), aend, `slots` = armed slots for attempt costs} |
| `presend_skip` | once per unknown mint | a single buy ≥ 5% on a token without history (an arm we cannot check) |

- `imit` = what the reactive bot did on the crossing trade: an IMIT1 dump event, in its envelope, a pick, fired (live runs
  only), and whether M2 picked it.
- `run_start` gets `"presend"` (the parameters). `run_end` gets `"presend"` (counters and timing).
- Terminal: `PRESEND ARM` lines (armed in some row), `PRESEND FILL` / `PRESEND EXIT` lines for row (c), and the status part
  `| PRESEND shadow: tokens … triggers … armed a/b/c … fills … exits … gross … net(cheap, 20/slot) … | open … late … gaps …
  | p50 / p99 / max µs per tx …`.
- Volume (MEASURED on the R4 replay): 3,612 records in 3.3 h, 2.2 MB, so ~26k records and ~16 MB per day per server.

## Parity with the study (MEASURED, `cargo test --release --lib presend`)
- The study's own events: ps4_R3/R4.npz windows, fills and paths, plus ps5's per-token arming, exported by `ps12_parity.py`.
  Each rebuilt tape was checked against the day arrays (rows, clock, fee rate, follower slack, wallet types).

| Check | Windows | Armed rows | Fills | Mismatches |
|---|---|---|---|---|
| 312 tokens, fed as the engine does | 471 | 1,210 | 377 | 0 |
| same, all at once | 471 | 1,210 | 377 | 0 |
| same, each slot reversed + every 3rd trade doubled | 471 | 1,210 | 377 | 0 |
| whole R4 day, 3,195 tokens (file outside the repo) | 1,192 | 3,105 | 579 | 0 |

- Compared: trigger trade, holding %, window start / end, armed flag per row, crossing trade, last trade ahead, landing and
  fill time, entry slot, exit slot, P&L (float32), sell time, armed-until, armed slots.
- 26 extra live arms on R4 are the study's hindsight rules a live engine cannot apply: 17 on tokens with < 5 trades over
  the whole recording, 9 in the tape's last 300 slots.
- Engine wiring test: 25 tokens through `presend_tx` write the library's records byte for byte; the reactive-bot marks land
  on the right fills only.

## Tests (MEASURED)
- `cargo test --release --lib`: 684 passed, 0 failed, 9 ignored (was 679; +5 presend tests).
- `cargo test --release --bin snipe_engine`: 30 / 30 (was 27; +3: flags, wiring, timing). The timing test and the full-day
  parity run only with `PRESEND_PARITY_FULL=FILE`.

## Timing (MEASURED here, whole R4 day: 290,307 txs, 298,912 trades)
| Path | Per trade | Per tx p50 / p99 | Txs over 50 µs |
|---|---|---|---|
| Library, records built but not written | 0.27–0.33 µs | 0.1 / 3–5 µs | ~35 (0.012%) |
| Engine wiring, records written to a file | 0.36 µs | 0.1 / 6 µs | 38–48 (0.015%) |

- Slow txs are fill bursts (3 fill records + disarm) and the periodic token clean-up (up to ~60 µs, every ~7 min). Rare
  1–2 ms maxima came from file writes on this machine.
- Done to keep it small: base58 of a signature costs 4.2 µs here, so each is made once; a follower's slack is computed when
  its trade arrives; at most 16 trades per call; one log flush per tx.
- INFERRED for the servers: the residual cost is the log write + flush (~0.1–0.5 ms there per the LANDFIX note), in ~10k
  batches a day, always after that tx's sends.

## How to run it
1. Engine: use the new binary and add `--presend-shadow` to the `--dip` command (defaults = the study config). The prod
   script `ops/prod/run_dip_prod.sh` was NOT changed (rule); it needs a pass-through like `--m2` and the binary path.
2. After the run, on this machine:
   `python3 ops/strategies/presend/ps11_shadow_eval.py --jsonl dip_rN.jsonl dip_ams_rN.jsonl --run /home/moiz/sniper-data/collect/run_<…> [--from "MM-DD HH:MM" --to "MM-DD HH:MM"] [--work DIR] [--procs 4]`
   - It rebuilds the tape from the raw recording with the study's code (a_extract → p1_build), re-detects T2 with ps4 `work`
     + ps5, and compares every live record (parity). Unmatched windows are explained (no history, engine not running, the
     study's tape rules).
   - P&L of each server's live windows on the tape (ps5_lib.run unchanged): rows a / b / c / r20 / r4 / r1 × cost rows
     cheap-k / cheap-k1 / +selltip / now-k, with 2 servers (study) and 1 server; also from the live records' own numbers;
     both servers pooled; and the create-slot split.
   - Disk: the work folder keeps ~57 MB of day arrays per recorded hour (~1.4 GB per 24 h). Delete it after.
3. Evaluator tests (MEASURED):
   - R4 with synthetic live records from the offline detector: 1,190 / 1,190 windows match, and the P&L equals the study's R4
     numbers (per 24 h): a +14.57, b +8.26, c +8.62, r20 +8.79, r4 +4.93, r1 +0.69; c cheap-k1 +14.79, now-k −633.
   - R4 with the Rust module's own records: 1,190 match; 16 live-only on < 5-trade tokens; 12 outside the window.
   - The raw-recording path (20:00–21:00 PKT, 18 chunks): 337 of 340 match; 3 live-only (< 5 trades in that tape); 8
     offline-only on tokens created before the simulated start.

## The create-slot finding (MEASURED replay, study code, row c, cheap, per 24 h)
- The study code counts the create's SIGNER as a possible whale when the create names a different creator (launchpads).
  That signer's dev buy in the create tx then arms a window.
- R4: 351 of 1,192 T2 windows (29%) are triggered in the create slot (352 by the create's signer). They give 51 of 184 row-c
  fills.

| Day | T2 as coded | Create-slot triggers | Later triggers (what REPORT.md describes) |
|---|---|---|---|
| R2 (train) | +13.14 | −4.32 | +17.58 |
| R3 | +3.71 | −2.88 | +6.58 |
| R4 | +8.62 | −2.84 | +12.49 |
| R1 | +8.20 | −2.84 | +11.41 |

- The split was not chosen on R2, so it is post-hoc. But it holds on all 4 days, R2 included.
- The shadow logs them as the study does. `age_slots` 0 marks them, and the evaluator reports the split.
- Dropping them in a live version would be a new flag (not built). Owner's call.

## Open risks
- **Hindsight in the study:** it drops tokens with < 5 trades over the whole recording. Live, they arm and cost attempts.
  On the R4 replay this cost −0.03 SOL in 3.3 h on row (c) (MEASURED).
- **Queue rows are a model.** The shadow cannot measure where a real pre-sent order would land. That needs a live probe
  (owner OK).
- **Start-up blind spot:** only tokens created after the engine starts are followed. 6–9% of the study's windows (R4 / R3)
  are on tokens older than 10 minutes, so the first part of a run sees fewer windows.
- **Feed problems:** missed trades (`gaps`) change balances and prices; deliveries more than 2 slots late are dropped
  (`late`). Both are counted, and the evaluator's parity shows their effect.
- **Run end:** windows still open get a `run_end` disarm, and their outcome is not logged. The evaluator recomputes them from
  the recording.
- **Both servers log the same windows** (same feed). The study's 2-server engine is applied offline (pooled).
- **Memory (INFERRED):** ~1k new tokens per hour × ~35 wallets; idle tokens are dropped after 6 h, so ~10–30 MB.
- **`imit.fired`** is set only in `--live` runs; in shadow runs `pick` shows what the reactive bot would have done.

## Files
- `src/presend.rs` (new; module + tests), `src/lib.rs` (+1 line), `src/bin/snipe_engine/dipmode.rs` (flags, wiring, records,
  status line, tests).
- `testdata/presend_parity.json` (9.5 MB; 312 tokens).
- `ops/strategies/presend/ps12_parity.py` (parity export), `ps11_shadow_eval.py` (evaluator), this file.

# dip24 OBSERVATORY (log-only shadow modules) + limits + regular mode

Engine `snipe_engine_dip24` = dip23 + the items below. **Every observatory module is LOG ONLY**: nothing is signed or sent, no live decision changes.
With all new flags off the engine writes dip23's records byte for byte (tested on a recorded hour, see Tests); `run_start` gains `limits` / `regular`
and `run_end` gains `stop_why` (owner request), always.

## How it runs
- **Live side** (`src/obs/mod.rs` `Feeder`, called by the dip event loop after all of its own work on a tx): one message per executed pump tx
  (its ExecInfo shared by an `Arc` clone) into a **bounded channel** (65,536) with `try_send`: full = dropped + counted, the loop never waits.
  Extras (each only when its module is on): executed txs with no pump event that name PumpSwap (migrations / pool txs); FAILED txs whose fee payer
  is watched; with `--obs-feedrace` one tiny message per arrival of every feed (sig8, feed, t_rx, slot).
- **Observatory thread** (`obs`, nice 19, idle I/O class): shared token book (`book.rs`), the modules, the writer, and a **tailer of the run's own
  `--dip-log`** (reads `presend_attempt / presend_live_arm / _disarm / _fill / _exit / _sell_land / _close` as they are written) so no live code calls it.
- **File**: `<dip-log stem>.obs.jsonl` (e.g. `/root/prod/runs/dip_ams_r36.obs.jsonl`; `--obs-file` overrides). Buffered (64 KB, flushed each second).
  **Rotation** every 6 h or 1 GB: the current part is renamed to `<file>.N`, N = the next free number (`.1` = oldest), never deleted; each new part
  starts with an `obs_part` record. Readers: parts `.1, .2, …` then the current file.
- **Clock**: `t` = the executed feed's arrival time (unix ns, the engine's clock; live pre-send records use the same clock). Block time is not
  carried by the executed feed (its logs are not kept): slots and the slot's first-seen time stand in.
- **Status**: the engine's 60 s line gets `| OBS: sent … dropped … queued … | rearm windows … fills … | hold … | watch … | …` (atomics, no lock);
  the file gets `obs_status` every 60 s, `obs_summary` every 10 min (every module's totals), `obs_start` / `obs_end`.
- **Bounded**: book tokens retire after 30 min idle (cap 250k tokens, 50k wallets per token), tapes 12 s / 1,024 trades, every module caps its open
  items (counted as `flood` / `overflow` / `dropped_full`), per-second / per-hour maps are pruned.

## Flags (engine) — `--observatory` = all modules
| flag | module |
|---|---|
| `--obs-rearm` | 1 REARM shadow |
| `--obs-hold` | 2 HOLD tapes of live pre-send fills |
| `--obs-watch FILE` | 3 WATCH list (one wallet per line, `# name`); default list `ops/obs/watch_default.txt` (32 wallets) |
| `--obs-migration` | 4 MIGRATION |
| `--obs-blink` | 5 BLINK causal trigger |
| `--obs-backrun` | 7 BACKRUN census |
| `--obs-select` | 8 SELECTION census |
| `--obs-feedrace` | 9 FEED RACE |
| `--obs-inslot` | 10 INSLOT paper (8yYMhu's same-slot backrun for us) |
| `--obs-file PATH` | the obs file (default `<dip-log stem>.obs.jsonl`) |
Script: `--observatory` → `--observatory --obs-watch /root/sniper-dip/obs_watch.txt` (copy `ops/obs/watch_default.txt` there).

## Records (one JSON object per line; `ev` names the module)
### 1 REARM (`rearm.rs`; rule R0 of REARM2.md)
- Candidate: a single curve sell ≥ 6% of supply on a normal token ≤ 30 s old (≤ 141 slots × 0.212 s), post-sell curve < 100 SOL.
  Holders check when the slot clock first reaches dump+3 (end of dump+2). `rearm_cand`: `mint, dump{sig,slot,idx,j,t,seller,sol,tok,pct,
  seller_left_pct,p_pre,p,drop_pct,vsol,vtok,age_slots,age_ms}, check_slot, holders, verdict (window | no_holder | blocked_live_armed | run_end), w`.
- Window: arm slot dump+3, last slot dump+3+20 (R2: +10); ends `expired` / `whale_dump` (next ≥ 6% sell +30 ms) / `no_holder` (+30 ms) /
  `quiet` (6:2: at arm slot+6 fewer than 2 trades by anyone but us) / `superseded` (a live T2 arm on the token, from the tailer) / `run_end`.
- `rearm_window`: `w, mint, dump, holders[{w,pct,first_buy,role (C creator/I insider/S signer),wh_fol,wh_dumps}], quiet{since_last,coh_hold,
  fb_n,wh_fol_top,all4,q}, r5_skip (all four QUIET signals hold for the largest holder), arm{slot,t}, en_slot, en_slot_r2, end{t,why,slot,
  ms_after_arm}, end_r2, superseded_live_t, others, quiet_stop, tries{n,ok,refused,k,cap,slot_ms}, n_tape, tape_cut, min_ratio, rows{a,b,c}`.
  Tries: k per slot (the live `--presend-live-k`, slot = SLOT_US) from the arm to the end; a try in unix second S is **refused** when live
  attempts sent in S (tailed `presend_attempt`) + re-arm tries already placed in S ≥ the cap (`min(--presend-live-max-per-sec, path cap)`).
- Row (a/b/c = +0/+5/+10 ms): `{blocked, hit (fill|late|untradeable|blocked|null), fill{x{slot,idx,j,t,p,w,buy,sol,drop_pct}, ref (post price
  of the last trade ≥ 50 ms before x), lim (0.88 × ref), m (last trade seen by the landing x.t+D), n_ahead, a_land, s_in, ms_after_arm,
  slots_after_dump, r2, refused_near (refused tries in [x.t−100 ms, a_land]), live_pos_open, min_ok[3] (tokens ≥ the min-out of a try signed
  on the reference state, per size), px / px_naive {size: {t200,t300,s2,tp10,tp20,live}} (gross mSOL), why{size:{policy: reason}},
  second{t_ms,slot,idx,w,sol,tok,big,before_200ms}, followers{s1,s2,s5: [distinct buyers, SOL]}}}`.
  Exits: our buy after m (fee on top, our impact), every later trade applied (`px_naive`) or buys whose min-out our buy breaks dropped (`px`,
  the study's slack table). A sell decided at T executes on the curve after every trade seen before T (zero sell latency — the tape lets you
  redo it with any delay). t200/t300 = fill seen (= a_land) + 200/300 ms; s2 = the first trade of slot ≥ s_in+2; tp10/tp20 = first of TP,
  SL 20%, s2; live = first of TP 20%, SL 20%, t200, s2. Second seller: first sell after m in s_in..s_in+2 by a ≥ 6% holder or ≥ 1 SOL.
- `rearm_tape` (windows with a fill): `w, mint, from_t (the dump), to_t (last fill + 3 s), n, trades[{slot,idx,j,t,w,buy,sol,tok,vsol,vtok,
  fl (B ≥6% holder, C creator, I insider, S signer, W watched, O ours), pct_after, sig}]`.
- Paper here is a model (rows on the arrival clock); the tapes are the ground truth for offline replays.

### 2 HOLD (`hold.rs`) — `hold_tape`, one per live `presend_live_fill`
`w, mint, fill{sig,slot,idx,t,tokens,sol_in,path,client,p_sign,lim,slots_after_trigger,ms_send_to_rx,in_tape}, dump (the biggest one-trade ≥ 2%
drop sell in the 2 slots before our fill, as the engine's attempt-landing record picks it; + drop_pct, ms_before_fill), exit{why,slot,t
(decision),value,round,ms_after_fill}, send_t: null (the pre-send sell's send time is not recorded by the engine; it is written at the
decision, no RPC first), sells[{sig,slot,idx,t,sol,ms_after_fill,ms_after_decision}], close{curve_pnl,exit_why,result,rounds,held_s,sell_lands},
first_1sol_sell / first_big_sell {slot,idx,t,w,sol,tok,big,ms_after_fill,seen_before_decision,ms_before_decision}, followers{s1,s2,s5}, trades[…]`
(every trade from the dump to fill + 3 s). Written when fill + 3 s is in and the position closed (or 20 s).

### 3 WATCH (`watch.rs`)
- `watch_trade`: `w, name, mint, buy, sol, tok, slot, idx, j, t, vsol, vtok, p, age_slots, age_ms, hist, mayhem, cu_price (µL; v1 txs: total
  priority lamports), cu_mod1000, cu_limit, v1, tips[{to,lamports,whose}] (top-level System transfers named by the sender catalogue), payer,
  pct_after, fl, trades_in_tx, sig`.
- `watch_fail` (failed txs the feed carries, fee payer watched): `w, name, slot, t, sig, cu_price, cu_mod1000, cu_limit, v1, tips, pump_ix
  (discriminator hex), mint_guess (account 2 of the first pump instruction), age`. No block index / error (the feed does not keep them).
  At most 20 per wallet per minute one by one; the rest = `watch_fail_agg {w,name,minute_t,total,written,cu_price_min,cu_price_max,mints}`.

### 4 MIGRATION (`migr.rs`; normal tokens)
`mig_v100` (first trade taking vSOL ≥ 100), `mig_v105` (first ≥ 105 not completing; a sell flagged): `mint,t,slot,idx,j,vsol,buy,sol,w,age_slots,
age_ms,sig,f1/f5/f10 {net_sol,buyers,trades}` (trailing 1/5/10 s). `mig_complete` (vtok = 279.9e12 after a buy): + `ms_after_v105/v100`.
`mig_follow` 10 s after each trigger: `kind,t0,vsol0,max_vsol_10s,completed_ms,g1/g5/g10` (forward flows). `mig_migrate` (an executed tx without
pump trade naming PumpSwap + the completed mint): `t,slot,sig,ms_after_complete,payer,age`. `mig_pool_tx` (≤ 5 per mint): later such txs.
**Pool trades that do not touch the pump program are NOT on our feed** (it subscribes to pump); PumpSwap events are not decoded (sig + t only).

### 5 BLINK (`blink.rs`; ported from sniper-blink, no model)
`blink_trigger`: `mint,slot,idx,j,sig,t_rx,cls (3 dev / 2 bundler / 1 early),seller,age_ms,age_slots (since s0 = first trade),age_slots_create,
in_create_slot,create_slot,s0,drop,sell_sol,vsol,vtok,features[22] (blink.rs FEATURES order),slot_first_t,seen_lag_in_slot_ms,block_time: null`.

### 7 BACKRUN (`backrun.rs`)
`backrun_sell` for every ≥ 1 SOL curve sell on a normal token (≤ 100 per minute, ≤ 16 open per token; ~98k/day on the soak):
`mint,t,slot,idx,j,sol,tok,drop_pct,seller,seller_fl,age_slots,age_ms,vsol,sig,n_buys,buy_sol,buys[≤20 {w,ds,idx,di,sol,wt,pro,ms}],first{…},
holds [1,2,5,9,31], size 0.75, v_br[5] (0.75 SOL bought right after the first backrunner: value = SOL back after fee / 0.75 at the end of entry
slot + h), v_sell[5] (bought right after the sell), armable{classes,live} (module 8), partial`.

### 8 SELECTION (`select.rs`)
`select_cand` for every buy taking a wallet from < 3% to ≥ 3%: `mint,w,slot,idx,t,pct_after,buy_sol,class (creator|insider|first_buy|laddered|
repeat),live_arms,why_not (not_first_crossing|creator|insider|curve_100|below_6pct_at_crossing),age_slots,age_ms,vsol,quiet{since_last,coh_hold,
fb_n,wh_fol,wh_dumps,all4},n60,b60,n120,b120,outcome{dump{slot_gap,ms,pct_sold,drop_pct},rebound_15,followers[n,SOL],paper_065_msol (0.65 SOL
right after a ≥ 12% dump, sold before the first trade ≥ 200 ms later),in_window[10,20,30]}`, written 50 slots after (or 15 after the dump).
Pros = wallets that bought after ≥ 1 SOL sells (same/next 2 slots) ≥ 50 times in the last 6 h (hourly buckets, ≤ 200k wallets).
`obs_summary.select.per_class`: n, live_arms, dump_10/20/30, paper_fills, paper_msol.

### 9 FEED RACE (`race.rs`)
Every arrival of every feed (incl. a new `[[feed]] kind = "udp"` such as Astralane shreds: **config-only**, `feeds::start` opens every enabled
feed for the dip engine). `race_tx` (txs seen by ≥ 2 feeds that matter — tag 1 whale buy (a wallet to ≥ 6%), 2 dump (≥ 6% sell or a sell in an
armed live window), 4 migration crossing (vSOL ≥ 100) — plus 1 in 20 others): `sig8,slot,idx,t,first,lag_us{feed: µs behind the first},tag,sampled`.
`obs_summary.race.per_feed`: delivered, coverage, wins, win_share, lead_us_p50/p90 (when first, vs the next feed), lag_us_p50/p90, and the same
over tagged txs. Leader-client split: not done.

### 10 INSLOT (`inslot.rs`; ops/strategies/rivals/8yYMhu/REPORT.md)
`inslot` for every ≥ 1 SOL curve sell on a normal token (≤ 100/min): `mint,t,slot,idx,j,sol,tok,drop_pct,seller,age_slots,vsol,profile (drop 8–25%,
seller ≥ 3% of supply, age 5–150 slots, curve < 60 SOL; EU leaders not checked),early_t,sig,took{ds,idx,di} (8yYMhu's own buy),holds [3,6,9,61],
legs{"15","30","45","60","90", "early_15".."early_90": {res (fill|fail_slot|fail_band|unresolved), entry_vsol, v{"0.50","0.75": value at entry slot + 3/6/9/61}}}`.
Clock mapping: all on OUR executed feed's arrival clock: decision = t_rx + 3 ms, landing L = decision + D; entry = the curve after every token trade
seen by L; same-slot iff our feed had not shown slot s+1 by L (its Lighthouse check); band = entry vSOL within [0.88, 1.04] × post-dump vSOL; a fail
costs 0.15 mSOL. "early_*" (with module 9): L from the earliest arrival over all feeds (assumes a constant executed-feed delay). Net mSOL = value×size −
size − (0.5 prio + 1.0 tip + 1.8 sell). `obs_summary.inslot` = per group (all / profile / rival_took / profile_and_took): n, per D: fills, fails,
fill_rate, net_msol[size][hold].

## Volumes (24 h soak, recorded day 10-27/28, all modules except hold/race which need live data)
| module | records/day | MB/day |
|---|---|---|
| rearm | 9,416 | 19.8 |
| watch | 58,627 | 35.6 |
| migration | 3,143 | 1.2 |
| blink | 25,493 | 20.4 |
| backrun | 98,488 | 81.1 |
| select | 52,201 | 27.6 |
| inslot | 98,642 | 102.1 |
| **total** | ~346k | **~288** |
Hold: one record per live fill (~100–400/day, ~20 KB each). Race: tagged + 1/20 sampled txs (not measurable offline).

## Reading
`python3 ops/obs/obs_report.py /root/prod/runs/dip_ams_r36.obs.jsonl [--since-h 3] [--json]` — works on a growing file and rotated parts.

## Limits (dip24) — see the top of ops/prod/run_dip_prod.sh.dip24-draft
- `--minutes 0` = no time limit. `--max-buys 0` = unlimited regular buys (allowed with `--live`; the kill switch stays required).
- `--presend-live-max-fills` optional (absent/0 = unlimited). `--presend-live-fee-budget-sol X` optional (1.0) = failed-attempt fees per
  **rolling 24 h**: the sender PAUSES at X (`presend_live_fee_pause`), resumes under it (`presend_live_fee_resume`); never stops the run.
- **Kill switch unchanged.** New: a blind alarm line + Telegram warning when the balance is unreadable for ≥ 30 s.
- **Profit lock** (`--profit-lock-min-sol M [--profit-lock-frac F=0.30]`): peak run PnL (balance + open at cost − start; peak taken only with
  nothing in flight), give-back G = max(M, F × peak), floor = max(−LOSS, peak − G); 2 consecutive polls below → like the kill switch (no new buys
  of any kind, positions finish), `run_end.stop_why = "profit_lock"`; status `lock: peak +P, floor +F (G give-back)`.
- **Regular mode** `--dip-regular live|paper|off` (+ `--dip-regular-paper-ms 60`): off = no regular buy (pick_skip `regular_off`; shred fire
  never buys); paper = live decisions on a paper book (`regular_paper_pick/_fill/_exit`, status `REGULAR PAPER: …`), never sent (a structural
  guard `regular_not_live` sits before the fire); paper never touches the live positions, the pre-send probe or any send budget.

## Tests
- `cargo test --lib obs::` (15, incl. inslot same-slot legs): book, positions, rearm (window, fill, exits, budget refusals, quiet stop, no-holder, age gate), exits on a hand tape,
  hold tape from live records, watch / migration / blink / backrun, selection + labels, feed race, inslot, writer rotation, tailer partial lines,
  bounded channel drops (never blocks), the thread end to end.
- `cargo test --bin snipe_engine dip24` (6 + 1 ignored): flags known, profit-lock owner examples, regular parse, paper fill/TP/no-fill/time exit,
  rolling fee pause/resume, minutes 0. `DIP24_HOUR=<run dir>:<unix s> cargo test --release --bin snipe_engine dip24_recorded_hour -- --ignored`:
  the probe + shadow on a real hour with the observatory off vs on: dip log and probe records identical; live-path timing per tx; paper on the hour.
- Soak: `target/release/obs_soak --run <collect run> --hours 24 --out DIR`.

## Long runs (week) — findings and rotation plan (audit 10-29)
Main files grow ~175 MB/day (.jsonl) and ~7 MB/day (.log). Tools that break at a week: dipmon `core/view.go:887` (P&L series only under 7 days),
`ops/dip/report/make_run_report.py` (keeps every line in memory: ~9 GB for a week), `apply_filter.py` (copies the whole .jsonl). Plan (not done,
needs owner OK): an opt-in engine flag `--dip-log-part-hours 24` cutting the main .jsonl/.log into `dip_rN.p{k}.*` parts at PKT midnight (a `part_end`
/ `part_start` record pair, run_end only in the last part, a parts manifest), tools globbing `{tag}.jsonl {tag}.p*.jsonl` and streaming. Until then:
fix view.go:887, stream the report, and expect 2–4 min per dipmon open of a week-long run. Engine risks for week runs (not changed here, need OK):
the pre-send UNSOLD background retry never gives up on a completed curve (fees until the run ends); reactive UNSOLD has no retry; pslive `ends`
is never pruned (run-end read burst); an `eprintln!` on a full disk panics.

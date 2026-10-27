# Pre-send T2: last 48 h at 0.35 / 0.50 / 0.75 / 1.00 SOL (agent, 10-26 PKT)

Owner request 10-26 ~00:05 PKT. Read-only and offline. Nothing was sent, no engine was started or stopped, and no server
file or engine source was changed. The server was only read: run 19's log and jsonl were pulled with `sudo cat` after
the engine had exited at 00:21 PKT.
MEASURED = live records, the chain recording, or a replay run on them. INFERRED = my reading or a model step. Times are PKT.
Order of work: the probe-3 check (section 2) was run and written at 00:34 PKT, before any 48 h run started (00:35).

## Short answer (phone)
| Size | Net over 48 h | Per day | 90% band (48 h) | 20% fewer later buyers (48 h / day) | 30% fewer (48 h) |
|---|---|---|---|---|---|
| 0.35 | **+7.4 SOL** | +3.8 | +6.5 to +8.3 | +1.7 / +0.9 | -1.3 |
| 0.50 | **+10.7 SOL** | +5.4 | +9.2 to +12.2 | +3.3 / +1.7 | -1.0 |
| 0.75 | **+15.3 SOL** | +7.8 | +12.5 to +18.5 | +4.2 / +2.1 | -1.9 |
| 1.00 | **+18.4 SOL** | +9.4 | +14.6 to +22.6 | +3.9 / +2.0 | -3.5 |
- All of these are replay numbers (INFERRED). There are no caps, and costs are fully in. The window is 10-24 00:20 to
  10-26 00:20 PKT, with 47.3 usable hours.
- The replay matched probe 3 well (section 2): live net +0.818 SOL sits at the replay's 58th percentile.
- Bigger sizes make more money only while the later buyers keep coming:
  - With 20% fewer of them, 0.75 and 1.00 earn about the same (+4.2 and +3.9 over 48 h), and 1.00 has the widest
    spread (+0.0 to +6.1).
  - With 30% fewer of them, every size loses, and the biggest size loses most.
- No pre-send fill has ever been made live above 0.35 SOL. The 0.75 and 1.00 rows are curve math on 0.35-size evidence.

## 1. Calibration to probe 3 (AMS run 19)

### 1.1 Probe 3, live (MEASURED, run 19 records + chain)
- Run: 22:20:34 to 00:20:34 PKT, stopped by `run_stopping` (the 240-minute flag; the live part ran 2 h). Caps were not
  reached: 66 of 100 fills, 0.068 of 0.1 SOL fee budget.
- 279 armed windows, 13,707 tries sent, 3,207 refused by the rate caps.
- **66 fills, 35 wins** (realized > 0 after the fill's own costs).
  - Realized (chain, `presend_live_realized`): **+0.8862 SOL**.
  - Failed-try fees (chain, every landed failed try, including 87 `buy_6005` and tries the feed missed): **0.0687 SOL**.
    The engine's own counter says 0.0679.
  - **Net +0.8175 SOL = +0.0124 per fill.**
- The run_stop record's `realized` field says 0.954 SOL. I use the per-window chain records (0.886), the same source as
  the probe 1-2 calibration.

### 1.2 The landing it measured (MEASURED, per landed try)
| Probe | Landed tries | Same slot / +1 / +2 or later | Send -> seen ms p25/50/75 | Send -> land incl. trigger view, ms p25/50/75 |
|---|---|---|---|---|
| P1 (run 16) | 3,768 | 40% / 55% / 4% | 51 / 84 / 139 | 63 / 108 / 156 |
| P2 (run 17) | 3,306 | 41% / 56% / 3% | 50 / 79 / 131 | 49 / 97 / 143 |
| **P3 (run 19)** | 13,186 | **39% / 55% / 5%** | 51 / 87 / 149 | 70 / 114 / 167 |

Probe 3 by leader client:

| Leader client | Landed tries | Send -> seen ms p25/50/75 | Same slot / +1 / later |
|---|---|---|---|
| AgaveBam | 4,727 | 49 / 101 / 175 | 33% / 61% / 5% |
| JitoLabs | 3,142 | 52 / 107 / 147 | 41% / 54% / 5% |
| HarmonicAgave | 2,577 | 54 / 72 / 102 | 49% / 47% / 4% |
| HarmonicFiredancer | 1,316 | 64 / 86 / 132 | 42% / 51% / 7% |
| Firedancer | 977 | 35 / 84 / 130 | 36% / 57% / 6% |
| FireBAM | 243 | 53 / 102 / 133 | 37% / 60% / 2% |
| Rakurai | 96 | 162 / 215 / 230 | 10% / 71% / 19% |
| Agave | 86 | 35 / 40 / 120 | 58% / 40% / 2% |
| Raiku | 22 | 23 / 26 / 30 | 82% / 18% / 0% |
- Live fills: 31 landed in the send slot and 35 one slot later. Send -> seen ms p25/50/75 for the fills: 51 / 85 / 154.
  All 66 went through helius-ps. Leader clients: AgaveBam 20, JitoLabs 15, HarmonicAgave 14, HarmonicFiredancer 11,
  Firedancer 5, FireBAM 1.
- Landing is the same as in probes 1-2: about 40% of tries land in the send slot and 55% in the next. HarmonicAgave is the
  fastest of the big clients (half its tries land in the send slot) and AgaveBam the slowest (a third).
- The replay does not split by client. It transplants whole live windows, so each donor window keeps its real mix of
  leaders.

### 1.3 Exactly what I changed (the simulator logic in `sim.py` is unchanged)
1. **Landing donor pool = probe 3 only:** its 153 full-length windows (from 13,529 live tries), instead of the 115 from
   probes 1-2. File `p3donors.py` → `s48/donors123.pkl`, built the same way as `donors.py`.
2. Each probe-3 donor window's engine view speed q is fitted on its own tries' signing prices, with the same method as
   before (fit p50 0.97).
3. The sell landing delays and the view jitter now come from probes 1+2+3, which adds probe 3's 66 sells
   (`s48lib.ModelN`).
4. Pace slot **211.8 ms**, MEASURED from 12,350 gaps between probe 3's tries (probe 2 was 211.7).
5. Settings are taken from probe 3's own `run_start`: whale >= 6%, 0.35 SOL, k 8, helius-ps 30/s path + global,
   limit 0.88, deadline +1, window 10 slots, exit 2 slots / TP 10% / SL 20%, one position.
6. New tape: a fresh decode of the recordings from 10-23 19:26 to 10-26 00:30 PKT (8.40 M trades) → `s48/tab`.
   - Probe 3's own fills and sells are removed, as probes 1-2's were (the replay puts its own buy in).
   - The detector gives the same triggers as the old tape on the overlapping hours (7,122 of 7,123).

## 2. Check on probe 3's own hours (run and written 00:34 PKT, BEFORE any 48 h result)
| | Live (MEASURED) | Replay A, P3 landing (400 draws) | Replay A, old P1-2 landing | Replay B, detected triggers (100 draws) |
|---|---|---|---|---|
| Windows armed | 279 | same 279 (forced) | same | 287 |
| Fills | 66 | 63.1 (57-69), live at the 82nd pct | 63.7 (58-70) | 63.5 (58-69) |
| Wins | 35 | 32.9 (28-37) | 34.3 (30-39) | 33.2 |
| Realized SOL | +0.886 | +0.845 (+0.559 to +1.106), 57th pct | +0.998 (+0.726 to +1.297), 28th pct | +0.850 |
| Failed-try fees SOL | 0.0687 | 0.0701 (0.0692-0.0709), live below all draws | 0.0705 | 0.0719 |
| **Net SOL** | **+0.818** | **+0.775 (+0.488 to +1.036), live at the 58th pct** | +0.928 (+0.655 to +1.227), 29th pct | +0.778 (+0.453 to +1.063), 61st pct |
| Net per fill | +0.0124 | +0.0123 (+0.0082 to +0.0162), 52nd pct | +0.0145, 22nd pct | +0.0123 |
| Fill / no-fill agreement per window | - | 91.5% | 91.3% | - |
| Landed tries: same slot / +1 / later | 39% / 55% / 5% | 35% / 58% / 7% | 38% / 57% / 5% | - |
| Tries sent / refused by caps | 13,707 / 3,207 | 13,794 / 3,247 | 13,853 / 3,254 | - |
- **Check result: PASS.** Live sits in the middle of the replay's spread on fills, wins, realized, net and net per fill.
  - Net: replay +0.775, live +0.818.
  - Net per fill: +0.0123 vs +0.0124.
- Misses (written down as found):
  - Failed-try fees: the replay is 0.0014 SOL (2%) higher than live, beyond its own spread. It has ~230 more deadline
    failures (1,654 vs 1,426), because it puts a few % more tries 2 slots late.
  - Fills: the replay is 3 low (63 vs 66, live at the 82nd percentile).
  - Both misses are small, and they push the replay in opposite directions.
- Caveat: line A with P3 landing is in-sample for landing (leave-one-window-and-token-out, but same hours). The old
  P1-2 landing is out-of-sample for probe 3 and also brackets live (29th percentile), so the result does not hang on the
  new pool.
- Line B is the pipeline the 48 h replay uses: detected triggers and the engine's own skip rules.

## 3. The 48 h replay
- **Window: 10-24 00:20 to 10-26 00:20 PKT** (10-23 19:20 to 10-25 19:20 UTC). Usable: **47.33 h**.
  - 40 min were dropped (10-24 23:00-23:40 PKT) because less than 95% of slots were recorded (same rule as REAL_REPLAY).
  - 8,524 T2 triggers; 5,258 of them can arm (not in the create slot, CreateV2, no cashback).
  - The engine is assumed to run the whole time, with token history from 10-23 19:26 PKT.
- Probe-3 settings and probe-3 landing (section 1.3), one stream, one position, 40 draws per row.
  - **No 100-fill / 0.1-SOL caps.**
  - Every cost is in: failed tries 5,120 lamports; per fill a 200k tip, a 605k sell fee and 1.2M sell tips; pump fees
    1.25% each way inside the curve math.
- **What size changes (and what it does not):**
  - Our buy's tokens on the curve, and the price move it makes. At the live fills' curve depth (median 36 SOL virtual,
    MEASURED on probe 3's 66 fills) our buy moves the price 1.9% at 0.35, 2.7% at 0.50, 4.1% at 0.75 and 5.5% at 1.00.
  - Which later buyers still fill: a buyer whose recorded slippage our bigger buy breaks is dropped, using the 711
    measured slippage settings.
  - The TP / SL value of our tokens, our sell's price impact, and pump's fees (a share of size).
  - Tips and tx fees are fixed per fill in the engine, so they do not change.
  - **The 0.88 limit does NOT fail more often at bigger sizes, so fills stay at ~1,017 at every size.** This follows from
    the engine code, not from a model choice. `src/presend_live.rs` `limit_min_out` sets min tokens out = the buy of
    `spend` at the curve state whose price is 0.88 x the signing price. So a try fills iff the curve price where it
    executes is <= the limit, whatever the spend (the engine's own test `limit_min_out_fills_iff_price_at_or_below_limit`).
  - A bigger buy does not change which tries fill. It changes what each fill earns.

### 3.1 Per size (40 draws; mean, 90% band from the draws)
| Size | Later buyers removed | Fills | Win % | Realized SOL | Failed-try fees | **Net 48 h** | 90% band | Per day | Per fill | Worst 4-h block | Worst 24 h | 4-h blocks > 0 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.35 | 0% | 1017 | 55% | +8.61 | 1.18 | **+7.42** | +6.50 to +8.31 | +3.76 | +0.0073 | -0.01 (10-25 08:20) | +3.09 (10-24) | 92% |
| 0.35 | 20% | 1020 | 49% | +2.93 | 1.18 | **+1.75** | +0.98 to +2.47 | +0.89 | +0.0017 | -0.29 (10-24 04:20) | +0.16 (10-24) | 67% |
| 0.35 | 30% | 1021 | 45% | -0.07 | 1.18 | **-1.26** | -1.91 to -0.25 | -0.64 | -0.0012 | -0.58 (10-24 04:20) | -1.37 (10-24) | 42% |
| 0.50 | 0% | 1017 | 55% | +11.93 | 1.18 | **+10.75** | +9.15 to +12.17 | +5.45 | +0.0106 | +0.06 (10-25 08:20) | +4.47 (10-24) | 100% |
| 0.50 | 20% | 1017 | 50% | +4.44 | 1.18 | **+3.26** | +2.07 to +4.39 | +1.65 | +0.0032 | -0.34 (10-24 20:20) | +0.70 (10-24) | 67% |
| 0.50 | 30% | 1015 | 45% | +0.14 | 1.18 | **-1.05** | -2.51 to +0.44 | -0.53 | -0.0010 | -0.75 (10-24 20:20) | -1.57 (10-24) | 50% |
| 0.75 | 0% | 1014 | 54% | +16.49 | 1.18 | **+15.31** | +12.45 to +18.49 | +7.76 | +0.0151 | -0.02 (10-25 08:20) | +6.25 (10-24) | 92% |
| 0.75 | 20% | 1020 | 49% | +5.40 | 1.18 | **+4.21** | +1.97 to +6.53 | +2.14 | +0.0041 | -0.52 (10-24 20:20) | +0.75 (10-24) | 67% |
| 0.75 | 30% | 1021 | 45% | -0.71 | 1.18 | **-1.89** | -3.76 to -0.30 | -0.96 | -0.0019 | -1.14 (10-24 20:20) | -2.45 (10-24) | 42% |
| 1.00 | 0% | 1018 | 54% | +19.63 | 1.18 | **+18.45** | +14.60 to +22.55 | +9.35 | +0.0181 | -0.06 (10-25 08:20) | +7.25 (10-24) | 92% |
| 1.00 | 20% | 1021 | 48% | +5.13 | 1.18 | **+3.95** | +0.01 to +6.15 | +2.00 | +0.0039 | -0.92 (10-24 04:20) | +0.13 (10-24) | 67% |
| 1.00 | 30% | 1019 | 44% | -2.32 | 1.18 | **-3.50** | -5.77 to -1.33 | -1.78 | -0.0034 | -1.60 (10-24 04:20) | -3.88 (10-24) | 33% |
- Notes on the columns (all INFERRED, replay):
  - "Per day" = net / 47.33 h x 24.
  - "Realized" = the fills' P&L after their own costs. Net = realized - failed-try fees.
  - 4-hour blocks start at 00:20, 04:20, ... PKT. The 10-24 20:20 block has only 3.3 usable hours.
  - "Worst 24 h" is the weaker of the two 24-hour halves: 10-24 00:20 → 10-25 00:20 (23.3 h) and 10-25 00:20 → 10-26 00:20.
    The other half at cut 0: +4.33 / +6.27 / +9.06 / +11.20.
- Per 4-hour block, mean net SOL at cut 0, in time order:
  - 0.35: +1.01 +0.34 +0.12 +0.75 +0.71 +0.16 | +1.08 +1.16 -0.01 +0.41 +0.36 +1.34
  - 1.00: +2.53 +0.53 +0.13 +2.08 +1.80 +0.18 | +2.51 +3.39 -0.06 +0.97 +1.00 +3.39
  - The 08:20-12:20 PKT blocks are the weak ones on both days.
- Exits at cut 0: about 73-77% time, 20-24% TP, 3% SL. TP gets a little rarer with size, because our own buy moves our
  cost basis up.
- Doubling the size from 0.35 to 0.75 doubles the net (+7.4 → +15.3). 1.00 adds less (+18.4): per fill +0.0073 →
  +0.0151 → +0.0181, while size grows 2.9x.

### 3.2 What the live caps would have done (cut 0)
The caps were applied to each 4-hour block as its own run: 12 runs, each stopping at 100 fills or 0.1 SOL of failed-try
fees.

| Size | Net with caps | Without | Runs that hit a cap |
|---|---|---|---|
| 0.35 | +6.53 | +7.42 | 5 of 12, after ~3.1 h |
| 0.50 | +9.47 | +10.75 | 5 of 12 |
| 0.75 | +13.44 | +15.31 | 5 of 12 |
| 1.00 | +16.14 | +18.45 | 5 of 12 |

### 3.3 Checks of the 48 h numbers (INFERRED, replay)
- **The landing pool matters little** (cut 0, 20 draws each):

  | Landing pool | 0.35 | 0.50 | 0.75 | 1.00 |
  |---|---|---|---|---|
  | Old P1-2 landing | +7.91 | +11.41 | +15.52 | +19.36 |
  | P1+2+3 landing | +7.60 | +10.89 | +15.77 | +18.81 |
  | Main (P3) | +7.42 | +10.75 | +15.31 | +18.45 |
- Probe 3's own 2 hours inside the 48 h stream (0.35): +0.769 SOL (+0.527 to +1.064), 65 fills. Live was +0.818 with 66.
- The same stream gives probe 1's hours -0.10 and probe 2's hours +0.01 at 0.35. These use probe-3 settings, so they are
  not the probes' own settings. Those hours were weak in the replay too, as REAL_REPLAY found.

## 4. Honest notes
- **(a) Overlap with hours the replay was tuned on.** Of the 47.3 usable hours:
  - **36.2 h were REAL_REPLAY's "unseen" test hours** (10-24 00:20 → 10-25 18:00 minus the probes). The replay was not
    fitted on them, but the settings (V0 = probe 2 = probe 3) were chosen after looking at results on them.
    At 0.35 they give +5.56 SOL = +3.69/day.
  - **6.3 h are the three probes' hours.** Probes 1-2 calibrated the old landing and probe 3 calibrated the new one, so
    landing is in-sample there. During those hours the tape also holds the market's reaction to our real probe buys.
    At 0.35: +0.68 SOL = +2.56/day.
  - 0.5 h was in REAL_REPLAY's tape but was not one of its test hours: its tail or a low-coverage bin.
  - **4.3 h are new**: 10-25 18:00 → 22:20 PKT, never seen by any replay. At 0.35: +0.94 SOL = +5.2/day; at 1.00:
    +2.62 SOL. That sample is small.
- **(b) Live vs paper.** Across our dip work, live at 0.35 has run at ~70-90% of size-matched paper on shared windows.
  - For pre-send so far, live has NOT run below the replay. Probes 1+2 together: replay -0.025 vs live -0.026. Probe 3:
    live is 105% of the replay (window by window) and 106% (in the 48 h stream).
  - Even so, 3 probes and 99 fills are a thin record. If live runs at 70-90% of the replay, cut 0 becomes 0.35 →
    +5.2 to +6.7, 0.50 → +7.5 to +9.7, 0.75 → +10.7 to +13.8, 1.00 → +12.9 to +16.6 SOL over 48 h (INFERRED).
- **(c) Why the bigger sizes are less trustworthy:**
  1. **There are no real large pre-send fills.** All 99 live pre-send fills were 0.2-0.35 SOL. The 0.75 and 1.00 rows are
     curve math plus the 711 measured slippage settings of other wallets' buys, never checked against a live fill that big.
     Elsewhere our 1.48 SOL buy did price out 2 followers (live-fill-tapes), so this effect is real.
  2. **Thin curve at the bottom of a dump.** Our fills sit at ~32-45 SOL virtual (p10-p90). A 1 SOL buy there moves the
     price ~5.5%, half of the 10% TP, and the exit sell of 1 SOL worth of tokens pushes back by a similar amount.
     - The profit is the later buyers' SOL lifting the price under our tokens. With the same buyers, a bigger position
       gets less of that lift per SOL.
     - That is why per-fill P&L grows slower than size, and why 1.00 earns less than 0.75 once 20% of the buyers go.
  3. **The follower risk grows with size.**
     - 20% fewer later buyers cut the result by 76% at 0.35, 70% at 0.50, 72% at 0.75 and 79% at 1.00.
     - 30% fewer gives a loss at every size: -1.3 at 0.35, -3.5 at 1.00.
     - Bigger buys are also more visible, so the bots that buy after us may react to them. Not modelled.
  4. **The 90% bands come from landing and follower draws only.** They do not include day-to-day market change. The two
     24-h halves differ by ~40% (+3.1 vs +4.3 at 0.35), and 48 h is only two days.
  5. **Not modelled:**
     - Wallet balance and other capital limits.
     - The reactive (M2) bot sharing the one position.
     - Competitors adapting to us.
     - A second path.
- My read (INFERRED): the replay now checks out against a live run in good hours as well as in weak ones.
  - Fair next steps are 0.50 live, or 0.75 after a 0.50 run checks out.
  - 1.00 adds little over 0.75 in the realistic follower case and carries the most risk.
  - Any size change or live run is the owner's call.

## 5. Files
- Scripts (`ops/strategies/presend/real/`):
  - `s48lib.py`: new tape, probe-3 loader, model over 3 probes.
  - `s48prep.py`: hours and triggers.
  - `p3donors.py`, `p3land.py`: calibration.
  - `p3check.py`: section 2.
  - `size48.py`: section 3.
  - `size48report.py`, `size48split.py`: tables.
- Data (`/home/moiz/sniper-data/presend_real/s48/`):
  - `dec/`, `tab/`: the new tape.
  - `live/dip_ams_r19.{log,jsonl}`: final copies, pulled 00:21 PKT.
  - `donors123.pkl`, `hours48.json`, `trig_6.pkl`.
  - `p3land.txt`, `p3check.txt/json`.
  - `size48_{main,p12,p123}.pkl/.log`, `size48_main_report.txt`.
- Re-run:
  ```
  python3 s48prep.py && python3 p3donors.py && python3 p3check.py --draws 400 --hdraws 100
  python3 size48.py --draws 40 --tag main && python3 size48report.py main
  ```

# Pre-send T2: the last hours with FRA run 22 settings (agent, 10-26 ~04:20 PKT)

Owner question 10-26 ~04:05 PKT: "how about check last hour pre-send recording?" To decide whether to switch pre-send
LIVE back on in Frankfurt.
Read-only and offline. Nothing was sent, no engine was started or stopped, and no server file was changed. I only read the
container's copy of the 24/7 recording (keeper copy of 04:15 PKT) and run 22's local jsonl.
MEASURED = live records or the chain recording. INFERRED = replay or my reading. Times are PKT.

## Short answer (phone)
| PKT | Fills | Wins | **Net SOL** (replay, INFERRED) | 90% band | Draws > 0 | 20% fewer later buyers |
|---|---|---|---|---|---|---|
| **Last 60 min, 03:14-04:14** | 24.5 | 11.5 | **+0.19** | +0.00 to +0.38 | 95% | +0.04 (-0.12 to +0.22) |
| 02:00-04:14 | 70.4 | 35.5 | **+0.61** | +0.21 to +0.98 | 100% | +0.11 (-0.27 to +0.51) |
| 22:00-02:00 (200 usable min) | 105.7 | 52.4 | +0.85 | +0.45 to +1.36 | 100% | +0.19 |
- **Check first:** on run 22's own 30 live minutes, the replay gave **-0.076 SOL** (INFERRED) and **live made -0.073** (MEASURED).
  - Live sits at the replay's 47th percentile.
  - Fills 17.9 vs 20, wins 7.6 vs 8. Both sides leave out the double-fill window.
  - So the replay tracks live. The engine's paper shadow did not: it said -0.29 for the same windows.
- The last hour is positive but thin. Three fills carry it: without those 3 windows it is -0.02.
- At 0.40 SOL, +0.19/h is about the 48 h average rate (SIZE_48H: +0.16/h at 0.35, +0.23/h at 0.50).

**Verdict (INFERRED):** the most recent hour was **positive**: +0.19 SOL at 0.40 SOL (+0.00 to +0.38), and 02:00-04:14
was +0.61. I am moderately sure. The replay matched run 22 within 0.003 SOL, and 95% of draws are > 0. But the hour rests
on 3 fills, and with 20% fewer later buyers it is about break-even (+0.04). One more double fill like 6ESztPpq (about
-0.47 SOL) would cost more than 2 hours of this gain.

## 1. What was run
- **Settings** are run 22's own `run_start` (MEASURED):
  - whale >= 6%, k 4, helius-ps path 20/s + global 20/s, 0.40 SOL;
  - limit 0.88 (drop 0.12), deadline +1, 10-slot window;
  - exit 2 slots / TP 10% / SL 20%, one position;
  - create-slot triggers skipped; failed-try fee 5,120 lamports.
- **Landing** is the probe-3 model, same as SIZE_48H:
  - the 153 P3 donor windows (`s48/donors123.pkl`);
  - sell delays and view jitter from probes 1-3;
  - pace slot 211.8 ms (MEASURED).
  - `sim.py` and the detector are unchanged.
- **Costs** are as in SIZE_48H. Per fill: a 200k tip, a 605k sell fee and 1.2M sell tips. Pump fees of 1.25% each way are
  inside the curve math.
- **Tape** (`lh/tab`): a fresh decode of run_20261025_1420, plus the cached 15:57-19:20 chunks for token history.
  - It runs 10-25 15:57:09 → 10-26 04:15:08 PKT, with 1.99 M trades.
  - The newest chunk was still being written when it was copied, so it was read up to 04:15:08.
- **Window:** 10-25 22:00 → **10-26 04:14:00 PKT**. This is the newest full minute that still has about a minute of tape after
  it for the last exits.
  - The rule is 5-minute bins with >= 95% of slots recorded.
  - All of 02:00-04:14 is covered.
  - 00:25-01:05 (40 min) was dropped: coverage there was 0.73-0.94.
- **Our own trades:** the live pre-send trades of probes 1-3, FRA r21/r22 and AMS r20/r21 are removed from the tape (611 txs:
  fills, sells and any landed buy). The market's reaction to them stays in, as in every earlier replay.
- **Main stream:** the engine is assumed on the whole time, with token history from 15:57.
  - 1,265 T2 triggers, of which 861 can arm.
  - 300 draws. The band is the 5th-95th percentile of the draws.
- **20% fewer later buyers:** the same run with `--cut 0.2`, the SIZE_48H stress test.

## 2. Check on run 22: 02:18:38 → 02:48:29 PKT
The settings and model were fixed before any result; nothing was tuned on these numbers.

### 2.1 Live, from `runs/fra/runs/dip_r22.jsonl` (MEASURED)
- 51 windows armed. Skipped: 27 create-slot, 7 blocked while armed, 2 with no launch accounts, 1 stopped.
- 1,326 tries sent. Landed: 1,125 `6042`, 98 deadline, 30 ata_exists, 22 ok; 50 never seen.
- 21 fill windows (22 fill txs), 8 wins.
  - Realized, summing `presend_live_realized`: **-0.151 SOL**.
  - Failed-try fees: **0.0064 SOL** (1,253 landed failed tries; equal to the engine's own counter).
- **The double fill, 6ESztPpq, w51 at 02:48:25, counted separately:**
  - Two 0.40 SOL fills landed in one window. Both were sold together at stop-loss in the same slot.
  - Its realized record (-0.084) counts only one buy.
  - Curve P&L of both buys: **-0.468 on 0.790 SOL in**, so its true wallet cost is about **-0.47 to -0.49** (INFERRED; the
    second buy's own wallet change is not recorded).
  - The replay's own estimate for that window as a single fill is about -0.04 per fill.
- **Without that window: 20 fills, 8 wins, realized -0.067, net -0.073 SOL.**
- With the double fill at its true cost, run 22's pre-send comes to about -0.55 SOL (INFERRED).

### 2.2 Replay on the same span (INFERRED, 300 draws)
The replay mimics the live start: only tokens created after 02:18:38 are followed, because the live engine skips older ones
as `no_history`.

| Without the double-fill window | Live (MEASURED) | Replay | Live percentile |
|---|---|---|---|
| Windows armed | 51 | 53 (all 51 live ones + 2 that never fill) | - |
| Fills | 20 | 17.9 | 64th |
| Wins | 8 | 7.6 | - |
| Realized SOL | -0.067 | -0.069 (-0.316 to +0.139) | 47th |
| Failed-try fees | 0.0064 | 0.0074 | - |
| **Net SOL** | **-0.073** | **-0.076 (-0.323 to +0.132)** | **47th** |
| 02:18:38-02:30, realized | -0.228 (7 fills) | -0.189 (6.8) | 37th |
| 02:30-02:48:30, realized | +0.161 (13 fills) | +0.121 (11.1) | 69th |
- Fill / no-fill agreement per window: **88%**.
  - Window by window, live and the replay mean have the same sign on 19 of 21 fills.
  - The live losers GRcpcww8 (-0.103) and GnJfMgsX (-0.091) are also the replay's worst (-0.078 and -0.066).
- The 20% fewer-buyers line gives -0.161 here, with live at its 72nd percentile. As on probe 3, the full-buyer line fits better.
- **Result: PASS.** The replay tracks live on this run (2 h probe 3 earlier, this 30 min now).

### 2.3 The engine's paper shadow on the same span (MEASURED; `presend_exit`, net_cheap x 0.40/0.55, by fill slot)
| | Row +0 ms | Row +10 ms | Without create-slot windows (+0 / +10 ms) |
|---|---|---|---|
| 02:00-02:30 (engine on from 02:18:38) | -0.594 (12 fills) | -0.526 (10) | -0.329 / -0.326 (7 fills) |
| 02:30-02:49 | +0.093 (21) | +0.263 (21) | +0.038 / +0.037 (14) |
| Total | -0.50 | -0.26 | -0.29 / -0.29 |
- These reproduce the owner's numbers exactly.
- The shadow also trades create-slot windows, which live skips.
- Even without them it said -0.29 while live made -0.07.
  - The shadow fills 0-10 ms after the crossing trade. Live fills landed a median 29-53 ms after it in probes 1-2 (MEASURED
    there).
  - So the shadow is not a forecast of live, in either direction (on probe 3, live was 62% of it). Use the replay.

## 3. 02:00 → 04:14 PKT per 15 minutes (main stream; INFERRED)
| PKT | Windows armed | Fills | Wins | Realized | Failed-try fees | **Net SOL** | 90% band | Draws > 0 |
|---|---|---|---|---|---|---|---|---|
| 02:00-02:15 | 44 | 11.1 | 6.7 | +0.203 | 0.007 | **+0.196** | -0.029 to +0.420 | 93% |
| 02:15-02:30 | 39 | 10.1 | 3.8 | -0.009 | 0.006 | **-0.015** | -0.232 to +0.167 | 51% |
| 02:30-02:45 | 30 | 9.2 | 4.5 | +0.056 | 0.004 | **+0.051** | -0.043 to +0.140 | 84% |
| 02:45-03:00 | 26 | 10.9 | 6.6 | +0.126 | 0.004 | **+0.123** | -0.005 to +0.248 | 94% |
| 03:00-03:15 | 26 | 4.7 | 2.4 | +0.069 | 0.004 | **+0.064** | -0.008 to +0.154 | 87% |
| 03:15-03:30 | 26 | 8.2 | 2.5 | +0.009 | 0.004 | **+0.005** | -0.062 to +0.075 | 55% |
| 03:30-03:45 | 31 | 6.2 | 4.7 | +0.114 | 0.005 | **+0.108** | +0.002 to +0.218 | 96% |
| 03:45-04:00 | 23 | 4.4 | 1.9 | -0.019 | 0.004 | **-0.023** | -0.133 to +0.089 | 34% |
| 04:00-04:14 (14 min) | 26 | 5.7 | 2.4 | +0.103 | 0.004 | **+0.099** | +0.001 to +0.171 | 95% |
| **02:00-04:14** | 271 | 70.4 | 35.5 | +0.651 | 0.042 | **+0.608** | +0.207 to +0.977 | 100% |
| **Last 60 min, 03:14-04:14** | 107 | 24.5 | 11.5 | +0.206 | 0.017 | **+0.189** | +0.003 to +0.383 | 95% |
| 03:00-04:14 | 132 | 29.1 | 13.9 | +0.275 | 0.021 | **+0.254** | +0.033 to +0.462 | 97% |
| 02:00-03:00 | 139 | 41.3 | 21.6 | +0.376 | 0.021 | **+0.354** | +0.024 to +0.670 | 96% |
- **With 20% fewer later buyers:**
  - Last 60 min: +0.039 (-0.124 to +0.217), 64% of draws > 0.
  - 02:00-04:14: +0.111 (-0.271 to +0.505).
  - 03:45-04:00: -0.072.
- **Concentration in the last 60 min** (mean per window):
  - The top three: Csafbc 03:51 +0.085, 9wcjoN 04:04 +0.069, szeCAY 04:00 +0.054.
  - The worst: GcnYhb 03:47 -0.127.
  - Without the top 1 it is +0.105, without the top 2 +0.036, without the top 3 -0.018.
- Exits in the last 60 min: 78% time, 18% TP, 4% SL.
- No engine ran 02:01-02:18. The replay assumes one did; that stretch gives +0.313 (13.8 fills).

## 4. The night, 22:00 → 02:00 per hour (main stream; INFERRED)
| PKT | Usable min | Fills | Wins | **Net SOL** | 90% band | Draws > 0 | 20% fewer later buyers |
|---|---|---|---|---|---|---|---|
| 22:00-23:00 | 60 | 15.1 | 9.7 | **+0.268** | +0.087 to +0.474 | 99% | +0.160 |
| 23:00-00:00 | 60 | 40.4 | 21.3 | **+0.574** | +0.288 to +0.899 | 100% | +0.278 |
| 00:00-01:00 | 25 (00:25-01:05 not recorded well) | 15.1 | 6.1 | **+0.137** | +0.011 to +0.255 | 96% | +0.065 |
| 01:00-02:00 | 55 | 35.2 | 15.3 | **-0.126** | -0.376 to +0.163 | 22% | -0.309 |
| 22:00-02:00 | 200 | 105.7 | 52.4 | **+0.854** | +0.447 to +1.355 | 100% | +0.194 |
| **22:00-04:14, all** | 334 | 176.2 | 88.0 | **+1.462** | +0.909 to +2.074 | 100% | +0.306 |
- The night: 4 of 5 hours positive, plus 02:00-04:14. The weak hour is 01:00-02:00.
- 01:17-02:01 is when FRA r21 and AMS r20 both pre-sent live.
  - The replay with FRA alone at 0.40 gives -0.193 (-0.433 to +0.095) on 32.7 fills.
  - Live FRA r21 (0.35 SOL) realized -0.123 on 34 fills in those minutes (MEASURED, FRA_run21 report).
  - So that hour was weak for pre-send itself, not only because both servers bought the same dumps. This is INFERRED, and it
    revises the earlier reading, which was based on paper rows that stayed positive.

## 5. Honest notes
- **What the 90% band covers.** It comes from landing and follower draws on the market as recorded. It does not include
  model error. That error was about 0.003 SOL on run 22 and +0.04 SOL (live above the replay) over probe 3's 2 hours.
- **Small sample.** 24.5 fills in the last hour, and the sign hangs on 3 of them.
- **Later buyers.** The profit is the later bot buyers lifting the price under our tokens. With 20% fewer of them, the last
  hour is about zero.
- **Not modelled:**
  - double fills (the replay makes at most one fill per window);
  - the reactive M2 bot sharing the one position;
  - AMS pre-sending at the same time (both servers buying the same dumps);
  - competitors reacting to us.
- **0.40 SOL has one live run behind it** (run 22, 20 single fills). Probe 3 at 0.35 had 66.

## 6. Files
- Scripts (`ops/strategies/presend/real/`):
  - `lasthour.py`: tape loader with our live txs removed, run-22 settings, both streams, live and shadow extraction.
  - `lhreport.py`: all the tables.
  - It reuses `sim.py`, `rlib.py`, `s48lib.py`, `variants.py`, `decode.py` and `build.py` unchanged.
- Data (`/home/moiz/sniper-data/presend_real/lh/`):
  - `dec/`: 100 chunks hard-linked from `s48/dec` plus the new decodes.
  - `tab/`: the tape.
  - `lasthour_{main,cut20}.pkl` and `lasthour_{main,cut20}_report.txt`.
- Re-run (about 1 min):
  ```
  python3 decode.py /home/moiz/sniper-data/presend_real/lh/dec /home/moiz/sniper-data/collect/run_20261025_1420 --min-age 30
  python3 build.py /home/moiz/sniper-data/presend_real/lh/dec /home/moiz/sniper-data/presend_real/lh/tab
  python3 lasthour.py --draws 300 --end "10-26 04:14" && python3 lasthour.py --draws 300 --cut 0.2 --tag cut20 --end "10-26 04:14"
  python3 lhreport.py main; python3 lhreport.py cut20
  ```
  Delete the newest `dec/*.npz` first if its chunk was still being written when it was decoded.

## Summary
| Item | Value | Label |
|---|---|---|
| Recording used | 10-25 15:57:09 → 10-26 04:15:08 PKT; replay window ends **04:14:00** | MEASURED |
| Run-22 check, without the double fill | live -0.073 vs replay -0.076 (47th pct); fills 20 vs 17.9; wins 8 vs 7.6 → PASS | MEASURED vs INFERRED |
| Run-22 double fill (6ESztPpq) | record -0.084, true about -0.47 to -0.49 (two buys, one stop-loss sell) | MEASURED record, INFERRED total |
| Run-22 paper shadow (+0 / +10 ms) | -0.50 / -0.26; without create-slot windows -0.29 | MEASURED |
| **Last 60 min (03:14-04:14)** | **+0.19 SOL (+0.00 to +0.38), 24.5 fills, 95% of draws > 0** | INFERRED |
| 02:00-04:14 | +0.61 (+0.21 to +0.98), 70.4 fills | INFERRED |
| 20% fewer later buyers | last 60 min +0.04; 02:00-04:14 +0.11 | INFERRED |
| Night per hour 22, 23, 00, 01 | +0.27, +0.57, +0.14 (25 min), -0.13 | INFERRED |
| Verdict | last hour positive, moderately sure; thin (3 fills); about break-even if later buyers thin by 20% | INFERRED |

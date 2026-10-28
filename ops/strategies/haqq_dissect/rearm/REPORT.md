# Analysts G/G2 (rearm): pre-send re-arm in an engine-faithful replay (10-28 ~04:05 PKT)
Saved by the main session from the agent's reply. Code: this folder:
- r1–r14, rsim.py (rsim.run_x);
- new in G2: r3b_holders, r8_report, r9_decomp, r10_examples, r11_stress, r12_vd, r13_fake, r14_guard.

Data: /home/moiz/sniper-data/haqq_dissect/rearm/:
- r8.txt main;
- r9, r11, r12, r13, r14, val.txt;
- examples.txt, decisions.jsonl (469,213 records), r8_chosen.json.

## Verdict (INFERRED replay, out-of-sample)
- **Analyst A's rule fails:** −3.68 SOL over 7 days, positive on 2 of 7. In the real engine a pre-sent try fills on ANY ≥ 12% drop; 69% of A's fills were cascades and other drops (−4.5 mSOL each).
- **The working rule `any:20:30:8:2` = "holder-gated re-arm":**
  - after any whale dump (one sell ≥ 6% of supply) on a token ≤ 30 s old, with a ≥ 6% holder still present at the end of dump+2;
  - arm at dump+3 for 20 slots, k 8;
  - stop at the next whale dump or when no wallet holds ≥ 6%.

  Walk-forward chose it on every test day.

| Test day | Fills (wins) | Added fills | **Replay [90%]** | ×0.81 | ×0.46 | 10% fewer followers | 20% fewer followers | Wave exit | Wave + S2 |
|---|---|---|---|---|---|---|---|---|---|
| D1 | 323 (189) | +306 | +3.51 [+2.26, +4.78] | +2.76 | +1.40 | +1.88 | +1.07 | +2.51 | +2.88 |
| D2 | 286 (156) | +274 | +1.53 [+0.27, +2.73] | +1.16 | +0.48 | +0.24 | −0.41 | +0.85 | +1.19 |
| D3 | 234 (137) | +226 | +2.69 | +2.11 | +1.05 | +1.20 | +0.92 | +1.91 | +2.18 |
| D4 | 392 (206) | +369 | +3.33 | +2.61 | +1.27 | +1.89 | +0.84 | +3.09 | +3.54 |
| D5 | 390 (216) | +367 | +3.25 | +2.54 | +1.22 | +2.05 | +1.06 | +3.07 | +3.52 |
| D6 (2.7 h) | 27 | +26 | +0.12 | +0.09 | | | | | |
| **Sum** | | **+1,568** | **+14.43 [+11.45, +17.35]** | **+11.27** | +5.45 | +7.24 | +3.19 | +11.56 | +13.47 |

- **Rates:** calibrated ≈ +2.25 SOL/day (D1–D5); conservative +1.08/day; 20% fewer followers +0.6/day.
- **Combined with the wave exit:** +13.79 over D1–D6; with S2 costs +19.80 (this includes S2's savings on today's fills).

## Checks
- **Calibration:** the replay already reproduces the adverse fill pattern (live/replay fill 1.00–1.18 by value bucket, 0.87 in the > 60 mSOL bucket). With the measured residual × 0.81: +9.86 over D1–D6. Stacking H's factors on top (double-counted) gives ≈ 0.
- **Lag stress:** re-arm tries landing 20 ms later +17.22; 40 ms later +16.05; all 21 random day-draws positive.
- **Load:** ~57 windows/hour, 13.5 fills/hour, ~1 try/s; rate-capped tries rise from 2.4–3.1% to 4.0–4.8%.
- **Caveat:** the holder-stop idea was designed after seeing the D0/D1/D3/D6 fill breakdown. The walk-forward protects the parameters, not the idea. A forward test on fresh data is required.

## Coordinator items
- **Fake round-trip dumps:** 4% of live fills (30 of 740), +14.7 mSOL/fill, NOT losers.

  | Seller of the sell that filled us (live) | Share | mSOL/fill |
  |---|---|---|
  | The armed whale | 58% | +7.40 |
  | Another ≥ 6% holder | 15% | +1.68 |
  | A < 6% wallet | 23% | +2.99 |

  A "real holder only" guard on today's T2 windows LOSES −7.21 SOL/7 days. It helps only on re-arm windows (+19.20 vs +16.69).
- **T2 window length:** a whale's first sell lands within 10 slots 38% of the time and in slots 11–20 13%. 20 slots gives +1.29 / 7 days (calibrated +0.71); 30 and 50 slots lose. Not recommended.

## Engine spec (flags, off by default)
- **presend_live.rs Detector::trade:** emit `Det::WhaleDump`, a 6% holder count, `Det::NoHolder`.
- **pslive.rs:**
  - flags `--presend-live-rearm {on|off, -slots 20, -start 3, -age-s 30, -k 8, -holder on, -paid-sol, -max-fills, -dry}`;
  - `on_exec`: handle WhaleDump / NoHolder;
  - `tick`: pending re-arms → `rearm()`, modeled on `trigger()` (l.1262) with a per-window k;
  - a T2 trigger supersedes a re-arm window;
  - records `presend_live_rearm_*` and `kind: "re"`.
- **Shadow plan:**
  1. unit tests;
  2. one-hour parity vs replay (±2%);
  3. 6–12 h dry shadow (~57 arms/h, ~13 fills/h);
  4. capped live A/B on AMS (max-fills 150; pass if live/replay ≥ 0.46 and P&L > 0).

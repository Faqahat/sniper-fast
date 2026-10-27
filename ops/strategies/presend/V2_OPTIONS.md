# Pre-send V2 options (agent, 10-25 PKT)

Asked 10-25 ~10:45 PKT. Read-only, local data only, $0. No server touched, nothing sent, no engine file changed.
MEASURED = probe records, chain tapes, replays on them. INFERRED = my reading or a model step. Times PKT.
"SOL/day" = net of ALL costs (pump fees, failed attempts, tips, priority, the probe's sell costs), one stream, one position.
TRAIN (all choices) = R1 + R2 (10-22 03:07 → 10-23 18:19, 36.6 h). TEST = R3 + R4 (10-23 19:26 → 10-25 09:56, 38.2 h).
R4 now covers the whole night and morning (the study had only its first 3.3 h). It holds the probe hour and the FRA shadow morning.

## Verdict
- **Pre-send T2 is worth a V2.** Probe 1 sat at break-even mainly because of its size, and partly because of its hour.
  - At 0.2 SOL, the fixed costs per fill (~1% of size) eat most of the margin. The probe also ran in a weak band (06–12 PKT).
  - The replay is calibrated to probe 1 and reproduces it (table below). At probe 1's settings it gives **+0.9 SOL/day** on
    the test days (90%: −0.1 to +2.0). That fits probe 1's ≈ 0.
- **Recommended V2 (B6):** whale holding **≥ 6%** (was 5%), **0.55 SOL**, **8 attempts per slot**.
  - Test: **+7.8 SOL/day** (90%: +5.5 to +10.2). Pessimistic landing: +5.0.
  - All 4 days positive (+5.0 to +13.7). 79% of test hours positive. Worst clock hour −0.35 SOL.
  - Needs: a second attempt path (~40 sends/s per armed window), plus a one-line run-script pass-through for the
    existing engine flag `--presend-whale-pct`.
- **Without a new path (A6):** the same at 4 attempts per slot: **+5.4/day** (90%: +3.6 to +7.2), pessimistic +3.3.
  - All 4 days +3.8 to +8.0. Worst hour −0.29.
  - Runnable today with flags only, whale ≥ 5% (A): +4.6/day.
- **More upside, more to prove:**
  - **C6** (8/slot, 1.0 SOL): +11.8/day (pessimistic +7.3);
  - **D6** (12/slot, 1.0 SOL): +14.1/day (pessimistic +9.8). D6 needs ~60 sends/s.
- **Why it works now (MEASURED, probe 1 + replay):**
  - Each probe-1 fill gained +3.8% on price but paid 2.5% in pump fees, ~1.0% fixed tx costs and 0.5% failed attempts.
  - At 0.55 SOL the fixed part drops to 0.37%.
  - Fills on 5–6% holders are break-even when pooled: positive on the strong days, negative on the weak ones.
    Fills on > 12% holders lose. The money is in 6–12% holders, on train and test alike.
  - 8 attempts per slot land ~13 ms earlier: median 16 vs 29 ms, INFERRED from the calibrated model.
- **Not worth adding** (replay, test days):
  - creator-dump targeting like the pros (−4.0 to +1.6/day);
  - T1t (+0.2 to +1.0);
  - leader filters (they cut fills, with no stable per-fill gain);
  - skipping seller-tool tokens (−0.5);
  - create-slot triggers (−3/day);
  - other windows (5 or 20 slots) and an 8% limit.
- **Proposed probe 2:** B6 for 30 fills, fee budget 0.06 SOL.
  - It measures the two steps the replay infers: the landing at 8 per slot, and the P&L per fill at 0.55 SOL.
  - Fallbacks: A6, B or A (see the probe 2 section).
- **Biggest risks:**
  - **the profit is the bot cohort buying after us** (MEASURED, cohort test).
    - Remove the later buys of the 541 consistent-winner bots (`ops/overnight/dip/drop_cw.json`): B6 goes from +7.8 to
      **−7.1/day**, and every config is negative on every day.
    - Remove 541 activity-matched random wallets instead: B6 stays at +4.0.
    - So the edge is getting in ahead of them, as for FINAL-2 and the dip bot. If they change, it goes.
  - a thin edge on a wide spread: B6's median fill nets +0.008 SOL, but p5 is −0.07 and p95 +0.105.
    - 4% of fills lose more than 15% of size; the worst lose ~45% (a crash inside the 2-slot hold).
    - With whale ≥ 5% the worst lose 60–67%.
  - the size effect: followers priced out by a bigger buy is a generic model, and probe 1 was 0.2 SOL only;
  - the landing above 4 per slot is extrapolated;
  - results swing by hour: the probe hour was ~0 in both live and replay, and ~22:00 and 10–11 PKT are weak;
  - the top 1% of fills carry about 20% of the profit (B6: 2.3 of 12.5 SOL on the test days).

- **Fresh hours (clean out-of-sample):** a job set at 11:25 PKT rebuilds the tape at 13:30 PKT for 10-25 09:56 → ~13:00 PKT
  (hours the analysis never saw). It runs every finalist and appends the result at the end of this file (`v2/r5_*.py`).
  - A pipeline test on the first 45 min (09:56–10:41): B6 +0.29 SOL (14 fills), A6 +0.15, probe 1's config +0.03.

## Ranked V2 configurations
All are T2 whale windows: whale holding ≥ 6% at its first ≥ 3% buy (`--presend-whale-pct 6`), no create-slot triggers,
window 10 slots, limit 12%, exit 2 slots / TP +10% / SL −20%.
Numbers are TEST SOL/day [90% clock-hour bootstrap], then the pessimistic-landing value.

| # | Config | TEST SOL/day | Pess | Change needed |
|---|---|---|---|---|
| 1 | **B6: 8/slot, 0.55 SOL** | **+7.8** [+5.5, +10.2] | +5.0 | flags + whale-pct pass-through + a 2nd attempt path |
| 2 | C6: 8/slot, 1.0 SOL | +11.8 [+7.8, +15.9] | +7.3 | as B6, size 1.0 |
| 3 | D6: 12/slot, 1.0 SOL | +14.1 [+10.2, +18.1] | +9.8 | as B6 + a 3rd path (~60 sends/s) |
| 4 | A6: 4/slot, 0.55 SOL | +5.4 [+3.6, +7.2] | +3.3 | flags + whale-pct pass-through |
| 5 | A6 at 1.0 SOL | +7.8 [+4.8, +10.8] | +4.6 | as A6 |
| – | A: whale ≥ 5%, 4/slot, 0.55 SOL | +4.6 [+2.0, +7.1] | +2.8 | **flags only, runnable today** |
| – | probe 1 as run (0.2 SOL, whale ≥ 5%, 4/slot) | +0.9 [−0.1, +2.0] | – | – |

- **Run-script note (MEASURED, read-only):** `--presend-whale-pct` exists in the engine (dip12/13), but `run_dip_prod.sh`
  passes only `--presend-shadow`.
  - So whale ≥ 6% needs a one-line pass-through in the script. Until then the engine default is 5%.
  - The script also caps the attempt rates at 50/s, and refuses reactive paths as attempt routes.

Per config details (TEST days; R3 = weak day, R4 = strong day):
- **B6:**
  - net per fill +0.0079 (R3) .. +0.0197 (R4); ~630 fills/day; 24% of armed windows fill;
  - worst clock hour −0.35; 79% of hours positive; without the top 1% of fills +6.4.
- **C6:**
  - net per fill +0.0112 .. +0.0309;
  - worst hour −0.68; 79% positive; without the top 1% +9.3.
- **D6:**
  - net per fill +0.0146 .. +0.0321; ~660 fills/day;
  - worst hour −0.64; 79% positive; without the top 1% +11.5.
- **A6:**
  - net per fill +0.0068 .. +0.0149; ~545 fills/day (21%);
  - worst hour −0.29; 77% positive; without the top 1% +4.3.
- **The whale threshold was chosen on TRAIN** (R1 + R2, finer grid 5 / 5.5 / 6 / 6.5 / 7 / 8%):
  - 5.5–6.5% beat 5% on train for every rate and size (e.g. 8/slot 0.55 SOL: train +12.0 vs +10.9);
  - test agrees: +7.8 vs +7.0;
  - per-day test with ≥ 5% (as probe 1): A +4.6, B +7.0, C +10.3, D +12.9.
  - It is not better on every day. It gives up 1–1.6 SOL/day on the strong days (R2, R4) and adds 2–5 on the weak days
    (R1, R3). So it is steadier, rather than higher everywhere.
  - Honesty note: I ran this finer grid after seeing a per-holding split (`c13_splits.py`) on both train and test.
    Train alone picks it, but the idea came after looking. The fresh hours below are the clean check.
- **Stress (pessimistic landing AND a 100 ms reference price):** A6 +2.7, B6 +3.9, C6 +5.1, D6 +7.1 per day on the test
  days. Both test days stay positive for each.
- **Add-on (new code, small):** cap the whale holding at 12%. B6 then gives +8.2/day [+5.9, +10.4], with 85% of test hours
  positive and a worst hour of −0.32.

- Rank = expected SOL/day weighed by how much of it is measured.
  - B6 is first: the 8-per-slot step is moderate, and the 0.55 size keeps the worst hour small.
  - C6 and D6 have more upside, but they add the 1.0 SOL size step; D6 also extrapolates the landing 3× beyond the probe and needs ~60 sends/s.
  - A6 needs only the whale-pct pass-through. A (whale ≥ 5%) runs today with flags alone.
- Add-ons (test days, measured on the whale ≥ 5% base):
  - deadline +2 slots: +0.1 (4/slot) to +0.4 (8/slot) per day; flag `--presend-live-deadline-slots 2`;
  - a cheaper sell (one 0.0002 tip, low priority): +1.3 to +1.5 per day. That is a sell-path change, so it needs the owner's OK.
- 20 per slot (+8.4/day at 0.55, whale ≥ 5%) adds little over 12 per slot. The attempt cost doubles (0.0042 SOL per fill).
- 1.5 SOL is no better than 1.0 (+9.6/day at 8 per slot) and its worst hour is −2.5.
- Whale holding ≥ 8% only (fewer, bigger trades): 4/slot 1.0 SOL +5.2/day, ~220 fills/day. It is dominated by ≥ 6%.
- First selection, on TRAIN only (44k configs; whale ≥ 5 or 8% only):
  - 8/slot picked 1.0 SOL / 12% / c2_tp10_slnone: train +16.9 → test +10.3;
  - 12/slot: +19.2 → +12.3;
  - 4/slot: +9.2 → +4.5;
  - creator-dump: +4.5 → +1.6.

## Calibration: probe 1 vs the replay of the SAME 118 windows (0.2 SOL, 3.79 attempts per slot)
| | Probe 1 (live, MEASURED) | Replay, calibrated | Replay, pessimistic | Study row c (+10 ms) |
|---|---|---|---|---|
| Fills of 118 windows | 20 (16.9%) | 23 (19.5%) | 22 (18.6%) | 27 (22.9%) |
| Same windows: both / live only / replay only | – | 18 / 2 / 5 | 18 / 2 / 4 | 20 / 0 / 7 |
| Fills: landing after the crossing, p50 | 29 ms | 35 ms | 41 ms | 10 ms |
| Per dump: first attempt that could fill, p50 | 31.5 ms (101 of 128 dumps) | 31.5 ms | 37 ms | – |
| Per dump: no attempt could fill it | 26.6% | 18.4% | 26.6% | – |
| P&L after pump fees, windows filled by both | +0.0080 SOL (18) | +0.0077 | +0.0268 | +0.0788 vs live +0.0521 (20) |
| Exits: TP or SL early / time | 7 / 13 | 4 / 19 | 2 / 20 | 5 / 22 |
| Wins; per fill p10 / p50 / p90 (mSOL, after all fill costs) | 9 of 20; −22.7 / −3.8 / +30.5 | 10 of 23; −18.8 / −4.8 / +19.8 | 9 of 22; −18.9 / −5.4 / +16.5 | 14 of 27; −18.8 / +0.2 / +23.5 |
| Attempts per fill | 190 | 166 (engine replay of that hour) | – | – |
| Failed-attempt fees, the hour | 0.0192 SOL | 0.0202 | – | 0.106 (20 per slot) |
| Net, the hour | −0.007 | −0.10 (24 fills) | – | −0.13 |

- **The probe's "53 ms median" counts every attempt that landed after a crossing (61), not the first one.**
  - The fills themselves landed a median **29 ms** after their crossing (p10 10, p90 55; n 20).
  - Per dump, the first attempt that could fill landed a median **31.5 ms** after it (p10 6, p90 98; n 101).
  - On 27% of dumps, no attempt could fill at all.
- **How the model moves with the rate (MEASURED by thinning the probe's own attempt stream):**

| Attempts per slot | 3.79 | 1.90 | 1.26 | 0.95 |
|---|---|---|---|---|
| No attempt could fill: measured | 26.6% | 40.6% | 51.6% | 60.2% |
| No attempt could fill: model | 18.4% | 41.9% | 57.5% | 66.7% |
| First landing p50: measured (block clock) | 31.5 ms | 44.5 | 53.0 | 58.3 |
| First landing p50: model ×0.85 / ×1.0 | 31.5 / 37.0 | 41.5 / 48.8 | 44.5 / 52.4 | 45.2 / 53.2 |

  - Model: attempts every 212/k ms from the window start. Each draws a whole probe attempt: its send → seen time
    (p10 33, p50 83, p90 207 ms) and whether it failed on the deadline (9.6%).
  - An attempt can fill only if it was signed before we saw the dump and lands after it.
  - The pessimistic rows keep probe 1's extra misses at every rate and do not shrink D.
- **Correlation check (MEASURED):** neighbouring attempts' send → seen times are strongly correlated (0.77; landing order
  inverted in only 6.9% of pairs). So the iid model above may overstate the gain from more attempts.
  - Other bound: densify probe 1's REAL stream with fully correlated copies (each extra copy takes its neighbour's transit
    and deadline outcome).
  - Result (first-sighting clock): 7.6/slot → D p50 17 ms, no attempt could fill 16%; 11.4/slot → 10 ms, 13%;
    19/slot → 7 ms, 13%. Probe 1 at 3.79/slot: 30 ms, 27%.
  - So the median landing gain holds under both assumptions. The no-fill share falls less: it sits between the calibrated
    (~1–9%) and the pessimistic (~10–18%) rows.
  - INFERRED: the remaining misses are window edges, pauses and runs of deadline failures, not attempt density.
- The live engine sells at once on +10% / −20%. The replay checks TP/SL only within the entry slot, so live exits early more often.
- **Engine shadow vs this replay (study row c, MEASURED):**
  - FRA r15 06:09–07:49: shadow 70 fills, +2.50 SOL; replay 80 fills, +2.77.
  - AMS r14 06:09–08:30: shadow 86 fills, +2.67; replay 100 fills, +3.09.
  - AMS r16 08:51–10:17: shadow +0.32; replay (cut at 09:56) −0.07.
  - The replay sees a few more windows: tokens created before the engine started.

## Options one at a time (around A: 4/slot, 0.55 SOL; SOL/day TRAIN → TEST; per day R1 / R2 / R3 / R4)
**(e) Attempt rate** (whale ≥ 5%, 0.55 SOL; landing p50 and "no attempt could fill" from the calibrated model):

| Per slot | Landing p50 | No attempt could fill | Fills/day (rate) | Attempts per fill (SOL) | After pump fees per fill | Net per fill | TEST SOL/day | Pessimistic |
|---|---|---|---|---|---|---|---|---|
| 2 | 40 ms | 32% | 526 (10%) | 164 (0.0008) | +0.0047 | +0.0018 | +1.0 | – |
| 4 | 29 ms | 8% | 802 (16%) | 211 (0.0011) | +0.0088 | +0.0057 | +4.6 | +2.8 |
| 8 | 16 ms | 0.5% | 925 (18%) | 363 (0.0019) | +0.0115 | +0.0076 | +7.0 | +4.3 |
| 12 | 11 ms | 0% | 974 (19%) | 516 (0.0026) | +0.0131 | +0.0085 | +8.3 | +5.9 |
| 20 | 7 ms | 0% | 1,016 (20%) | 821 (0.0042) | +0.0144 | +0.0082 | +8.4 | +6.3 |

- **Send rate needed (MEASURED from the windows' overlap):**
  - One window is armed 9–10% of the time. 2–6 windows overlap during 6–7% of the armed time.
  - Per armed window: 4/slot ≈ 20 sends/s, 8/slot ≈ 40/s, 12/slot ≈ 60/s, 20/slot ≈ 100/s.
  - Helius allows 50/s per region, shared with the reactive paths. 8 per slot therefore needs a second attempt path; 12 per slot needs a third.
  - The engine already round-robins a route's paths per attempt (`default=p1+p2`; code read, MEASURED).
  - Over a cap, attempts are skipped, not queued.

**(b) Size** (whale ≥ 5%, test days; after pump fees, per fill as % of size):

| Size | 4/slot: margin after pump fees | 4/slot: SOL/day | 8/slot: margin | 8/slot: SOL/day | Fixed tx cost share |
|---|---|---|---|---|---|
| 0.2 | 2.1% | +0.9 | 2.7% | +1.3 | 1.0% |
| 0.35 | 1.9% | +2.9 | 2.4% | +4.2 | 0.57% |
| 0.55 | 1.6% | +4.6 | 2.1% | +7.0 | 0.37% |
| 1.0 | 1.1% | +6.1 | 1.5% | +10.3 | 0.20% |
| 1.5 | 0.6% | +4.6 | 1.0% | +9.6 | 0.13% |

- The margin falls with size: price impact, plus followers whose slippage our buy breaks. This is the study's generic
  follower model (INFERRED). Net SOL/day peaks around 1.0 SOL.
- **Check against real buyers (MEASURED, R2–R4, `v2/c12_sizecheck.py`).** Take the first other wallet buying 0–100 ms after a T2
  crossing (2,412 cases).
  - Its 2-slot mark-to-market, pump fees in, by size: < 0.3 SOL +5.8%, 0.3–0.7 +4.6%, 0.7–1.5 +4.25% (≥ 1.5: +15.6%, a different crowd).
  - That is about −1.5 pp from small to ~1 SOL, close to the replay's −1.0 pp for our fills from 0.2 to 1.0.
  - Consistent with the model, not proof: who buys big is not random. Probe 2 measures our own fills at 0.55.

**(c) Leaders.**
- Filters cut fills more than they lift the margin, on R2, R3 and R4. R1 has no schedule.
  - BAM only: +1.3 / −0.1 / +3.6 vs all +7.1 / +1.6 / +9.5.
  - No Jito: +4.1 / +0.6 / +9.5.
  - No Harmonic: +4.9 / +1.0 / +3.0.
- Net per fill by entry-slot client (B config, R2–R4, before attempt costs): BAM +0.0102, Harmonic +0.0120, Jito +0.0128,
  FD +0.0056. No BAM edge in the replay.
- Probe 1's split (BAM +0.060 on 8 fills; Jito −0.029 on 3; Harmonic −0.033 on 5) is noise-sized.
- MEASURED landing by client in probe 1 (dumps per client 19–32): first attempt p50 BAM 25 ms, Harmonic 33, Jito 36,
  FD 43. That is a hint, not enough to filter on.
- New code would be needed: an empty route class is not a skip today. It would panic: see the engine section.

**(a) Seller-tool tokens.**
- Feed rule: a rebuy 1–3 positions after a ≥ 4% sell, 25–110% of it.
- These tokens hold 9–11% of the armed windows. Net per armed window there is not worse: it is better on 2 days and worse on 2.
- Skipping them: train +4.8 vs +5.4, test +4.1 vs +4.6 → **no**.
- Our ~30 ms landing almost never lands between a sell and its bundled rebuy anyway.

**(d) Triggers.**
- T2 including create-slot triggers: train +2.5, test +1.5 (vs +5.4 / +4.6). Keep them off: `--presend-live-create-slot off` is the default.
- T2 with holding ≥ 8% (0.55 SOL): +3.8 / +3.3. Per fill it is 2–3× higher (+0.013 to +0.015), but there are 3× fewer fills.
  - At 1.0 SOL (A8, 4/slot): +5.2/day test, positive on all 4 days. Whale ≥ 6% beats it (A6 at 1.0: +7.8).
  - Holding ≥ 10%: ~+1/day, too few fills.
- Window 5 slots: +2.1 / +3.6. Window 20 slots: +4.2 / +3.5.
- **Creator-dump targeting** (serial creators, armed from the create, causal creator history over R1–R4):
  - at 4/slot every variant loses: train −0.2 to −3.1, test −1.3 to −4.0;
  - best train pick at 8/slot (≥ 10 previous launches, ≥ 80% with a big early dump, 1.0 SOL, 1-slot exit): train +4.5 → test +1.6;
  - at 20/slot: +5.0 → −0.75.
  - We would land behind the five dense pre-senders on the same dumps (they land ≤ 5 positions after it 28–53% of the time).
- T1t (≥ 4.65% dump, serial creator): +0.4 / +1.0. At 8/slot: +2.2 → +1.0.

**(f) Limit and exit.**
- Limit 8%: +0.5 / +0.9. Limit 16%: +5.6 / +3.6. **Keep 12%.**
- Other 2-slot exits are within ±0.6/day of c2_tp10_sl20. 3–4-slot exits move −2.3 to +0.6. A 1-slot exit is worse (+1.9 / +2.5).
  Keep 2 slots / TP 10 / SL 20.
- Deadline +2: +1.0 train / +0.1 test at 4/slot, and +0.6 / +0.4 at 8/slot.
- **Attempt priority fee: a lever not testable here.** Probe 1 paid 1,000 µL/CU (5,120 lamports per failed attempt).
  - The dense pre-senders pay a median of 5,000–13,600 lamports per failed attempt, up to 44,000 (INSTANT_BOTS, MEASURED).
  - A higher CU price may place our attempt earlier in the leader's block. We have no live data on it.
  - Cost: 50,000 µL × 120k CU adds 6,000 lamports per attempt, ≈ +0.0022 SOL per fill at 8/slot.
  - The flag exists (`--presend-live-cu-price-micro`). Test it in a later probe, against the same windows' landing.

**(g) The normal dip bot** (MEASURED from the runs that logged the shadow next to the live reactive bot):
- The reactive bot holds a position about 1.0% of the time on FRA (22.6 fires/h × 1.65 s), and ~0% on AMS (0–1.3 fires/h).
- Pre-send B would hold about 1.3% of the time (~45 fills/h × ~1 s).
- With one position per server, each side loses only ~1% of its chances to the other.
- Shared dumps: 14–25% of the shadow's fills sat on a dump the reactive bot picked (FRA r15: 16 of 104; 8 were fired live,
  = 21% of its 38 fires). There the pre-sent order lands first, and the reactive buy is skipped (engine rule).
  - The shadow's P&L on those shared dumps was mostly +0.05 to +0.16 SOL (0.55 SOL).
  - INFERRED: V2's added value = its P&L minus the reactive bot's P&L on ~4–5 shared dumps/h.
  - The study's 3-day check found the combined total above the reactive bot alone on every day.
- 2 servers add nothing: same windows, positions are short (+5.3 vs +5.4 train).

## Validation details (TEST unless stated; one stream, one position)
**How long a live run needs (INFERRED; clock-hour spread, all 4 days):**
- Hours for P(the total > 0) ≈ 90%, and the share of positive clock hours:
  - probe 1's config: ~19 h, 62% positive;
  - A6: 2.9 h, 80%;
  - **B6: 1.7 h, 87%**;
  - C6: 2.1 h, 87%;
  - D6: 1.8 h, 84%.
- With whale ≥ 5%: A 6.2 h, B 2.6 h.
- One probe hour cannot judge SOL/day.

| Config | R1 | R2 | R3 | R4 | 00–06 PKT | 06–12 | 12–18 | 18–24 | Without the top 1% of fills |
|---|---|---|---|---|---|---|---|---|---|
| probe 1 as run (0.2, ≥ 5%, 4/slot) | +0.3 | +1.9 | −0.2 | +2.8 | +1.8 | +0.3 | +2.4 | −0.3 | +0.3 |
| A6 (0.55, 4/slot) | +7.8 | +6.3 | +3.8 | +8.0 | +10.6 | +1.3 | +6.7 | +2.4 | +4.3 |
| B6 (0.55, 8/slot) | +13.7 | +10.9 | +5.0 | +12.4 | +14.5 | +2.6 | +8.1 | +4.6 | +6.4 |
| C6 (1.0, 8/slot) | +22.1 | +16.5 | +7.1 | +19.5 | +22.3 | +3.6 | +12.9 | +6.5 | +9.3 |
| D6 (1.0, 12/slot) | +23.2 | +17.5 | +9.7 | +21.2 | +27.4 | +5.0 | +12.3 | +7.8 | +11.5 |

- R1 and R2 are TRAIN days. The band columns are SOL/day on the test days (10–12 hours each band).
- **Cohort test (MEASURED replay, `v2/c15_nocw.py`):** remove the buys made after our entry by:
  - the 541 consistent-winner bots → A6 −6.4, B6 −7.1, C6 −13.2, D6 −13.7 per day on test (train: −8.9 / −9.6 / −17.5 / −18.3);
  - 541 random wallets matched on activity (`c16_control.py`; they hold 56% of the cohort's buys) → A6 +2.4, B6 +4.0, C6 +5.7, D6 +7.2.
- **The replay reproduces the swing the shadow showed** (study row c, 0.55 SOL, its cheap costs):
  - 06:09–08:06: +2.61 SOL (the shadow said +2.6);
  - 08:50–10:00: −0.21 (the shadow said ≈ 0).
  - In the same two spans: B6 +1.35 / −0.16, A6 +0.68 / −0.17, probe 1's config +0.35 / −0.09.
  - So an hour like probe 1's would have lost ~0.2 SOL with B6 too.
- B6 by clock hour (all days): positive in 22 of 24 hour-of-day slots.
  - Weakest: 22:00 PKT and 10–11; strongest: 04–06, 09, 00–01.
  - Only 3–4 samples per hour: treat as a hint.
- Fills per armed window: A6 20–28%, B6 24–33%, D6 25–34%.
- Rate: with whale ≥ 6%, a window is armed only 4–5% of the time, and two windows overlap during only ~3% of it.

## Probe 2 (proposal; owner's OK needed)
**What it tests:** the landing at 8 per slot, and the margin per fill at 0.55 SOL. These are the two INFERRED steps between
probe 1 and B6. It also checks the whale ≥ 6% filter live.

Server: **AMS**, as probe 1. The reactive bot rarely fires there (0–1.3/h), so there is less pausing.
Hours: any band except ~22:00 and 10–11 PKT (weakest in the replay).

**Before the run (config, owner's call):**
- Add one more attempt-only `[[send]]` block next to `helius-ps`: a copy of another provider's block with its own `name` and
  `max_per_sec = 20`. A tip path pays its tip only on a fill.
- Keep `helius-ps` at 20/s.
- Caution: a second provider changes the landing mix. Probe 1 calibrated Helius SWQoS only, and the evaluator splits by path.

```bash
sudo bash /root/prod/run_dip_prod.sh --run N --trades T --size S <today's usual options> --presend --presend-whale-pct 6 \
  --presend-live --presend-live-size-sol 0.55 --presend-live-k 8 \
  --presend-live-routes "default=helius-ps+PATH2" --presend-live-max-per-sec 40 --presend-live-path-max-per-sec 20 \
  --presend-live-max-fills 30 --presend-live-fee-budget-sol 0.06 --minutes 120 --sell-fanout helius-swqos
```
- `--presend-whale-pct` is the shadow's flag. The live trigger uses the shadow's parameters (LIVE.md).
  - Check that the run script passes it through.
  - The banner must show 6.
- Everything else as probe 1: limit 12%, deadline +1, CU 120k × 1,000 µL, no create-slot triggers, one position, exit
  2 slots / TP 10% / SL 20%.
- `--max-sol` must cover 0.55.
- **Needs first:** the run script must pass `--presend-whale-pct` through (one line), and PATH2 must exist.
- **Fallbacks:**
  - no PATH2 → A6: the same with `--presend-live-k 4 --presend-live-routes "default=helius-ps"` and `--presend-live-fee-budget-sol 0.04`;
  - no pass-through → drop `--presend-whale-pct 6` and run B (whale ≥ 5%, test +7.0/day);
  - neither → A (whale ≥ 5%, 4/slot, 0.55 SOL), flags only.
- A server dry run first (`--presend-live-dry`) checks the rates.

**Caps and the expected outcome (B6):**
- ~26 fills/h → 30 fills in ~70 min.
- Fee budget: ~250 attempts per fill × 5,120 lamports ≈ 0.0013 SOL per fill, ≈ 0.04 SOL for 30 fills. The cap is 0.06.
- Loss bound: the run's kill switch. The worst replay hour for B6 is −0.35 SOL. One fill's stop is ~−0.11 SOL.
- Expected (INFERRED): +0.008 to +0.020 SOL net per fill, so +0.24 to +0.6 SOL for 30 fills.
  - 13% of clock hours are negative in the replay, and probe 1's hour was flat.

**Pass / fail (set now; MEASURED by ps13 + `v2/c2_thin.py` / `c4_probecal.py` on the run log):**
1. Landing, probe 1's method (per dump, the first attempt that could fill):
   - pass if p50 ≤ 22 ms and "no attempt could fill" ≤ 20%;
   - the model with probe 1's dump timing predicts 18–21 ms and 9–18%;
   - probe 1 measured 31.5 ms and 27%.
2. Fills ≥ 20% of armed windows (model 24% calibrated, ~21% pessimistic; probe 1 with whale ≥ 5%: 17%).
3. P&L after pump fees, on windows filled both live and in replay: within ±0.005 SOL per fill (c4 method).
4. Pass → a longer B6 run (3–6 h over strong bands), then C6 (1.0 SOL), then D6 (12 per slot).

**How to check it (local, read-only, after the collector is 30 min past the probe's end):**
```bash
cd /home/moiz/sniper/ops/strategies/presend
python3 ps13_live_eval.py --jsonl LOG.jsonl                       # fills, costs, landing (as probe 1)
python3 v2/c2_thin.py LOG.jsonl                                   # criterion 1: the "keep 1 of 1" row
bash v2/r5_fresh.sh /home/moiz/sniper-data/collect/run_<date>_<time> "MM-DD HH:MM"   # tape + replay of those hours
python3 v2/c4_probecal.py --jsonl LOG.jsonl --day R5 --size 0.55 --rows c,L8,L8x --out c4_probe2   # criteria 2-3
```

## What changes in the engine (read from the code and the run script, MEASURED)
- **Already in dip13 (flags):**
  - attempt flags: `--presend-live-size-sol`, `--presend-live-k` (1–20), `--presend-live-drop`, `--presend-live-deadline-slots`,
    `--presend-live-cu-price-micro`, `--presend-live-max-per-sec` and `--presend-live-path-max-per-sec` (the script allows ≤ 50);
  - `--presend-live-routes "default=p1+p2"`: one path per attempt, round-robin;
  - the caps;
  - the shadow's trigger and exit flags (`--presend-whale-pct`, `--presend-window-slots`, `--presend-exit-slots`,
    `--presend-tp`, `--presend-sl`), which the live probe reuses.
- **Run script (one line):** pass `--presend-whale-pct` (and the other shadow flags) through. Today it adds only `--presend-shadow`.
- **Server config:** one attempt-only `[[send]]` block per extra attempt path. Reactive and sell paths are refused as attempt routes.
- **New code (not needed for B6):**
  - a 12% whale-holding cap (+0.3/day);
  - a leader-class skip (not recommended).
    - **Caution:** do NOT pass an empty class such as `jito=` to `--presend-live-routes` to "skip" Jito.
    - The parser accepts it, and the sender then computes `(n + id) % 0` and would panic (`pslive.rs` ~line 287; code read, not run);
  - a seller-tool skip (not recommended);
  - a creator-dump trigger (not recommended);
  - a cheaper sell for pre-send fills (+1.3–1.5/day; a sell-path change, owner's OK).

## Method (short)
- **Tapes:**
  - R1–R3 are the study's day arrays.
  - R4 was rebuilt with the study's own code (`a_extract` → `p1_build`) for 10-24 19:25 → 10-25 10:26. The last 30 min are not used.
  - Over the study's R4 span, the rebuild holds every one of the study's 298,891 trades (MEASURED).
    It has 9,107 more, on 68 tokens that the study's earlier cut dropped.
- **Replay** (`v2/v2lib.py`, `v2eng.py`): the study's ps4 / ps5 mechanics. Trailing 50 ms reference, followers priced out
  dropped, pump fees both sides, sell 75 ms into the exit slot.
- **What V2 adds to the replay:**
  - calibrated landing rows;
  - the live engine's window rule: the crossing must be inside the window, but an attempt in flight may land after it;
  - one draw per dump;
  - sizes 0.2–1.5;
  - a 48-exit grid;
  - leader class per slot (local epoch schedules 1065–1067);
  - a causal creator history over R1–R4;
  - the seller-tool rule.
- **Costs (MEASURED, probe 1):**
  - failed attempt 5,120 lamports;
  - fill: buy fee 5,120 + tip 0.0002, sell fee 0.000605 + fan-out tips 0.0012 (0.00201 SOL fixed);
  - pump fees inside the curve P&L;
  - attempts charged for every armed slot, minus the pauses while the position is held.
- **Selection** (`v2/v2run.py`): 44,226 configs on TRAIN only (T2 / creator-dump / T1t × rate × limit × size × exit). Best per family and rate, with both train days positive and ≥ 20 fills/day.
- **Robustness** (`v2/v2final.py`): per day, PKT hour bands, clock-hour bootstrap (4,000 resamples), the top 1% removed, per client, send rate.
- **Reference-price sensitivity:** the limit is set from the price 50 ms before the crossing, as in the study.
  - A 100 ms reference (older signing prices) lowers test results by ~15%: A +3.9 (vs +4.6), B +6.1 (vs +7.0).
  - Probe 1's same-window fills (18 of 20 shared) support the 50 ms rule at 4/slot.
- **Not modelled:**
  - per-path landing differences (calibrated on Helius SWQoS only);
  - competitors adapting;
  - live rate caps when 2+ windows overlap (6–7% of armed time);
  - stale limits from deadline +2 beyond the replay's 50 ms reference.

## Files
- **Code:** `ops/strategies/presend/v2/`
  - build: `b1_tape.py` (tape from a recording), `b2_crehist.py` (causal creator history), `v2data.py`;
  - replay: `v2lib.py` (windows, fills, paths; `PSV2_TAG` / `PSV2_LREF` / `PSV2_DROP` / `PSV2_DROP_UIDS` for the variants),
    `v2eng.py` (engine + costs), `v2run.py` (option tables + TRAIN selection), `v2final.py` (robustness, finalists in `finalists*.json`);
  - probe checks: `c1_landing.py`, `c2_thin.py`, `c3_model.py` (landing model), `c4_probecal.py` (probe vs replay; takes `--jsonl --day --size --rows`);
  - other checks: `c5_interact.py` (dip bot), `c6_client.py`, `c7_tool.py`, `c8_shadowparity.py`, `c9_tables.py`, `c10_hours.py`,
    `c11_densify.py`, `c12_sizecheck.py`, `c13_splits.py`, `c14_hold.py`, `c15_nocw.py` + `c16_control.py` (cohort test);
  - fresh hours: `r5_fresh.sh` + `r5_eval.py`.
- **Data:** `/home/moiz/sniper-data/presend_v2/`
  - `tape_R4/` (0.47 GB), `c3_model.json`, `v2_R*.npz` (+ `_lref100`, `_nocw`, `_norand` variants), `summary.json`;
  - text outputs: `v2run.txt` (option tables), `v2final*.txt` (finalists), `c4_probecal.txt` (calibration), and each `c*.txt`.

## Fresh hours check (auto-appended by `v2/r5_append.py`)
- **R5:** 10-25 09:56 → 10-25 12:56 PKT (3.0 h). The tape was built after every choice above was made, so no number here was used to choose anything.
- Same engine and real costs as the test days. Each line: SOL in R5, per 24 h, fills, net per fill, then the clock hours.

- B6: whale ≥ 6%, 8/slot, 0.55: **+0.377 SOL** (+3.0/24h), 34 fills, net +0.0111/fill; hours +0.51 / -0.11 / -0.03
- A6: whale ≥ 6%, 4/slot, 0.55: **+0.124 SOL** (+1.0/24h), 28 fills, net +0.0044/fill; hours +0.33 / -0.18 / -0.02
- C6: whale ≥ 6%, 8/slot, 1.0: **+0.507 SOL** (+4.1/24h), 34 fills, net +0.0149/fill; hours +0.76 / -0.22 / -0.04
- D6: whale ≥ 6%, 12/slot, 1.0: **+0.498 SOL** (+4.0/24h), 35 fills, net +0.0142/fill; hours +0.76 / -0.22 / -0.04
- B6, pessimistic landing: **+0.191 SOL** (+1.5/24h), 31 fills, net +0.0062/fill; hours +0.38 / -0.17 / -0.03
- A6, pessimistic landing: **+0.147 SOL** (+1.2/24h), 24 fills, net +0.0061/fill; hours +0.35 / -0.18 / -0.03
- B: whale ≥ 5%, 8/slot, 0.55: **+0.440 SOL** (+3.5/24h), 54 fills, net +0.0081/fill; hours +0.67 / -0.21 / -0.01
- A: whale ≥ 5%, 4/slot, 0.55: **-0.105 SOL** (-0.8/24h), 39 fills, net -0.0027/fill; hours +0.25 / -0.32 / -0.03
- probe 1 as run (0.2 SOL): **-0.090 SOL** (-0.7/24h), 39 fills, net -0.0023/fill; hours +0.08 / -0.14 / -0.03

- Reading: B6 held up on the fresh hours (+3.0/24h vs +7.8 on test), and A6 held up (+1.0/24h vs +5.4).
  - Only a few hours, and test hours were negative 13–20% of the time, so this is a sanity check, not proof.

## Size sweep 0.35–1.0 (owner 10-25)
Asked 10-25 (coordinator relay). Same calibrated replay, real costs, one stream and one position. All numbers are SOL.
- **TEST** = R3 + R4 (38.2 h; choices made on R1 + R2).
- **FRESH** = R5, 10-25 09:56 → 15:07 PKT (5.2 h).
  - The recording reached only ~15:40 at 15:40 PKT; the last 30 min are cut, so ~17:00 was not possible.
  - R5 was rebuilt after every choice was made.
- "Pess" = pessimistic landing.
- "Worst hour" is the worst TEST clock hour; "worst fill" is the worst single TEST fill, net of every cost.
- Fills per day do not depend on size: A6 549, B6 632, B5 925.

**B6: whale ≥ 6%, 8/slot**

| Size | TEST/day [90%] | Pess | FRESH R5 (per 24 h) | Net per fill | Worst hour | Worst fill |
|---|---|---|---|---|---|---|
| 0.35 | +4.9 [+3.4, +6.4] | +3.1 | +0.64 (+3.0) | +0.0078 | -0.22 | -0.14 |
| 0.55 | +7.8 [+5.4, +10.2] | +5.0 | +1.02 (+4.7) | +0.0124 | -0.35 | -0.21 |
| 0.75 | +10.0 [+6.9, +13.1] | +6.4 | +1.32 (+6.1) | +0.0158 | -0.49 | -0.29 |
| 1.0 | +11.8 [+7.9, +15.7] | +7.3 | +1.44 (+6.7) | +0.0187 | -0.68 | -0.39 |

**A6: whale ≥ 6%, 4/slot**

| Size | TEST/day [90%] | Pess | FRESH R5 (per 24 h) | Net per fill | Worst hour | Worst fill |
|---|---|---|---|---|---|---|
| 0.35 | +3.4 [+2.3, +4.6] | +2.0 | +0.43 (+2.0) | +0.0063 | -0.18 | -0.14 |
| 0.55 | +5.4 [+3.5, +7.2] | +3.3 | +0.70 (+3.2) | +0.0098 | -0.29 | -0.21 |
| 0.75 | +6.8 [+4.4, +9.2] | +4.1 | +0.89 (+4.1) | +0.0124 | -0.42 | -0.29 |
| 1.0 | +7.8 [+4.8, +10.7] | +4.6 | +0.87 (+4.0) | +0.0141 | -0.56 | -0.39 |

**B5: whale ≥ 5%, 8/slot**

| Size | TEST/day [90%] | Pess | FRESH R5 (per 24 h) | Net per fill | Worst hour | Worst fill |
|---|---|---|---|---|---|---|
| 0.35 | +4.2 [+2.2, +6.1] | +2.4 | +0.82 (+3.8) | +0.0045 | -0.42 | -0.19 |
| 0.55 | +7.0 [+4.1, +10.0] | +4.3 | +1.34 (+6.2) | +0.0076 | -0.59 | -0.30 |
| 0.75 | +8.9 [+5.0, +13.0] | +5.5 | +1.78 (+8.2) | +0.0096 | -0.83 | -0.41 |
| 1.0 | +10.3 [+5.1, +15.4] | +6.0 | +1.95 (+9.0) | +0.0111 | -1.30 | -0.54 |

**FRESH R5 by clock hour (from 09:56), B6:**
- 0.35 SOL: +0.26 / -0.04 / -0.02 / +0.11 / +0.32 / +0.01 (worst fresh fill -0.048)
- 0.55 SOL: +0.41 / -0.04 / -0.02 / +0.16 / +0.48 / +0.02 (worst fresh fill -0.075)
- 0.75 SOL: +0.55 / -0.04 / -0.02 / +0.17 / +0.64 / +0.03 (worst fresh fill -0.102)
- 1.0 SOL: +0.57 / -0.09 / -0.03 / +0.23 / +0.73 / +0.03 (worst fresh fill -0.135)

**Where the size penalty comes from (B6, TEST; margin = net of pump fees, per fill, as % of size):**

| Size | Replay (followers priced out) | Naive (every later buy happens) | SOL/day replay | SOL/day naive |
|---|---|---|---|---|
| 0.35 | 3.18% | 3.86% | +4.9 | +6.4 |
| 0.55 | 2.85% | 3.77% | +7.8 | +11.0 |
| 0.75 | 2.54% | 3.67% | +10.0 | +15.3 |
| 1.0 | 2.20% | 3.57% | +11.8 | +20.5 |

- **Size penalty from 0.35 to 1.0 SOL: 0.98 pp of margin.**
  - About 0.29 pp is our own buy's price impact on the real tape (curve math: the naive run).
  - About 0.70 pp is the follower crowd-out model (INFERRED: the generic slippage-slack table).
  - The crowd-out model also takes ~0.7 pp at 0.35 SOL.
- **Against real buyers (c12, MEASURED, R2–R4, the first other buyer 0–100 ms after a T2 crossing).**
  - 0.3–0.7 SOL got +4.6% and 0.7–1.5 SOL got +4.25% (2-slot mark-to-market, pump fees in). That is −0.35 pp.
  - The same step in the replay (0.55 → 1.0) is −0.65 pp with crowd-out, and −0.20 pp without.
  - Real buyers sit between the two, nearer the naive run. So the crowd-out model may overstate the size penalty (INFERRED).
  - Confounded: who buys big is not random. Only live fills at the larger size can settle it.
- **Risk grows linearly with size; SOL/day grows less than linearly (B6, TEST).**
  - Worst clock hour: -0.35 at 0.55 SOL, -0.49 at 0.75, -0.68 at 1.0.
  - Worst single fill: -0.21 / -0.29 / -0.39.
  - 0.75 SOL gives 84% of 1.0's SOL/day, with 73% of its worst hour.
- **Probe 2 context (running now on AMS: B6 at 0.35 SOL, helius-ps 30/s):** INFERRED, not measured.
  - 30 sends/s lets one window get at most ~6.4 attempts per slot (30 × 0.212 s). Its landing sits between A6 and B6.
  - The replay at 0.35 SOL gives +0.0063 (A6) to +0.0078 (B6) net per fill on average.
  - Fills are widely spread: p1 about −0.08 at 0.35 SOL. So one −0.0002 fill says nothing yet.
- **Recommendation for the next step: 0.75 SOL, not 1.0.**
  - Do it only after probe 2's landing and fill-rate checks pass (V2 probe 2 section, criteria 1–2).
  - 0.75 gives most of the modelled gain (B6 test +10.0/day, pessimistic +6.4, fresh +6.1/24h).
  - It keeps the worst hour near −0.5 SOL.
  - It also tests the INFERRED size effect directly: compare the live margin per fill at 0.35 and 0.75 with the replay on the same windows (`c4_probecal.py --size`).
  - Go to 1.0 only if the 0.75 live margin holds (≥ ~2.5% after pump fees, as the replay says).
- Every size depends on the bot cohort buying after us (the cohort test in "Biggest risks"). A bigger size does not change that.
- Code: `v2/c17_sizesweep.py` (0.75 SOL was added to the replay; `PSV2_NAIVE=1` is the no-crowd-out run). Data: `presend_v2/c17_sizesweep.json`.

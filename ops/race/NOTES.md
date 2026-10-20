## Forward proof (landing models)
> **Verdict (14:02 UTC, fresh run only):** n>=100 fires and 90% CI of SOL/day above zero): Gate B (time 1s) under d <=25: +43 SOL/day @2 SOL (90% CI +9..+80); Gate B no-name (time 1s) under d <=25: +60 SOL/day @2 SOL (90% CI +15..+105); PREREG_v2 #2 (time 1s) under c LANDX: +48 SOL/day @2 SOL (90% CI +18..+77); PREREG_v2 #2 (time 1s) under d <=25: +79 SOL/day @2 SOL (90% CI +50..+108); PREREG_v2 #5 (time 1s) under c LANDX: +28 SOL/day @2 SOL (90% CI +6..+52); PREREG_v2 #5 (time 1s) under d <=25: +49 SOL/day @2 SOL (90% CI +26..+73); PREREG_v2 #5 (frozen exit) (time 1.5s) under d <=25: +49 SOL/day @2 SOL (90% CI +19..+82)
> FORWARD PROOF run 'fresh': 2730 scored base launches over 8.02 h (only launches after the run start).

- **Fresh run** `fresh`: merged binary, started 05:00 UTC, every base launch tracked, labelled on chain. It is scored only on launches after its start, with rules and exits frozen earlier (no refit). Re-scored every ~2 h by `forward_proof.py fresh`.
- **Landing models:**
  - (a) **OURS:** 38% land in S at our 18 measured positions (median ~104); the rest land in S+1.
  - (b) **JITO / (c) LANDX:** the in-S positions of Jito- or LandX-tipped outside buyers on the same leader client (`landing_dist.json`; the d <= 5 bundle riders are excluded). These assume we land in S.
  - (d) **<= 25 txs:** the ceiling.
- **Whale rule:** the trigger is the first outside buy >= 5 SOL in S; we land 'model' txs after it; sell at +3 s.

```
FORWARD PROOF run 'fresh': 2730 scored base launches over 8.02 h (only launches after the run start).
Landing models: a OURS (39% in S at our measured positions, 61% S+1) | b JITO / c LANDX (empirical in-S positions of those senders' buyers on the same leader client, d<=5 riders excluded; assumes we land in S) | d <=25 ceiling.

rule                                                           exit       model    |    n fires/d race |   mean    med    ex3  win | SOL/day @1 | SOL/day @2 [90% CI]
Gate B                                                         1s         a OURS   |  479    1434  37% |  -2.1%  -4.7%  -2.7%  27% |     -36.6 |    -60.9 [-94,-27]
Gate B                                                         1s         b JITO   |  479    1434  37% |  -1.1%  -3.9%  -1.7%  31% |     -21.1 |    -31.2 [-64,+2]
Gate B                                                         1s         c LANDX  |  479    1434  37% |  -0.1%  -3.0%  -0.8%  35% |      -7.0 |     -4.0 [-37,+29]
Gate B                                                         1s         d <=25   |  479    1434  37% |  +1.5%  -1.8%  +0.9%  42% |     +17.4 |    +42.9 [+9,+80]
Gate B no-name                                                 1s         a OURS   |  876    2623  37% |  -2.2%  -4.8%  -2.5%  27% |     -68.2 |   -114.0 [-160,-69]
Gate B no-name                                                 1s         b JITO   |  876    2623  37% |  -1.3%  -3.9%  -1.7%  31% |     -45.3 |    -69.7 [-113,-26]
Gate B no-name                                                 1s         c LANDX  |  876    2623  37% |  -0.4%  -3.2%  -0.7%  35% |     -19.5 |    -20.1 [-64,+25]
Gate B no-name                                                 1s         d <=25   |  876    2623  37% |  +1.1%  -2.1%  +0.8%  41% |     +22.0 |    +59.8 [+15,+105]
FIX base filter                                                1s         a OURS   | 2730    8174  23% |  -3.4%  -5.4%  -3.5%  18% |    -314.3 |   -549.2 [-612,-487]
FIX base filter                                                1s         b JITO   | 2730    8174  23% |  -2.6%  -4.9%  -2.7%  21% |    -246.7 |   -419.3 [-482,-357]
FIX base filter                                                1s         c LANDX  | 2730    8174  23% |  -1.8%  -4.6%  -2.0%  24% |    -185.0 |   -300.8 [-365,-235]
FIX base filter                                                1s         d <=25   | 2730    8174  23% |  -0.6%  -4.3%  -0.7%  29% |     -75.9 |    -91.5 [-166,-19]
PREREG_v2 #1 [dev>=3.0 & bundle>=1tx & bundle<=3.0SOL]         1s         a OURS   |  130     389  48% |  -3.6%  -5.6%  -5.3%  25% |     -16.0 |    -28.2 [-43,-12]
PREREG_v2 #1 [dev>=3.0 & bundle>=1tx & bundle<=3.0SOL]         1s         b JITO   |  130     389  48% |  -2.3%  -4.2%  -4.1%  29% |     -10.6 |    -17.9 [-33,-1]
PREREG_v2 #1 [dev>=3.0 & bundle>=1tx & bundle<=3.0SOL]         1s         c LANDX  |  130     389  48% |  -0.8%  -3.6%  -2.7%  35% |      -4.7 |     -6.5 [-23,+11]
PREREG_v2 #1 [dev>=3.0 & bundle>=1tx & bundle<=3.0SOL]         1s         d <=25   |  130     389  48% |  +2.3%  -0.8%  +0.5%  48% |      +7.9 |    +17.6 [-1,+38]
PREREG_v2 #1 (frozen exit)                                     10s        a OURS   |  130     389  48% |  -4.6% -13.1%  -7.4%  27% |     -19.5 |    -36.0 [-70,+2]
PREREG_v2 #1 (frozen exit)                                     10s        b JITO   |  130     389  48% |  -3.1% -11.9%  -5.8%  28% |     -13.3 |    -24.0 [-58,+14]
PREREG_v2 #1 (frozen exit)                                     10s        c LANDX  |  130     389  48% |  -1.7% -11.3%  -4.4%  30% |      -7.8 |    -13.4 [-47,+24]
PREREG_v2 #1 (frozen exit)                                     10s        d <=25   |  130     389  48% |  +1.2%  -8.4%  -1.5%  34% |      +4.0 |     +9.4 [-26,+49]
PREREG_v2 #2 [bundle>=3.0SOL & bundle<=5.0SOL & tip=lunar]     1s         a OURS   |  321     961  45% |  +0.3%  -4.3%  -0.5%  31% |      -0.2 |     +5.9 [-25,+35]
PREREG_v2 #2 [bundle>=3.0SOL & bundle<=5.0SOL & tip=lunar]     1s         b JITO   |  321     961  45% |  +1.4%  -3.4%  +0.6%  36% |     +10.2 |    +26.0 [-3,+55]
PREREG_v2 #2 [bundle>=3.0SOL & bundle<=5.0SOL & tip=lunar]     1s         c LANDX  |  321     961  45% |  +2.5%  -1.8%  +1.7%  41% |     +21.7 |    +48.0 [+18,+77]
PREREG_v2 #2 [bundle>=3.0SOL & bundle<=5.0SOL & tip=lunar]     1s         d <=25   |  321     961  45% |  +4.1%  -0.1%  +3.3%  50% |     +37.5 |    +78.6 [+50,+108]
PREREG_v2 #2 (frozen exit)                                     5s         a OURS   |  321     961  45% |  -3.4%  -8.1%  -4.7%  33% |     -36.2 |    -64.8 [-114,-15]
PREREG_v2 #2 (frozen exit)                                     5s         b JITO   |  321     961  45% |  -2.1%  -6.9%  -3.5%  35% |     -23.8 |    -40.9 [-91,+10]
PREREG_v2 #2 (frozen exit)                                     5s         c LANDX  |  321     961  45% |  -1.2%  -6.2%  -2.5%  36% |     -14.1 |    -22.4 [-74,+27]
PREREG_v2 #2 (frozen exit)                                     5s         d <=25   |  321     961  45% |  +0.3%  -5.6%  -1.2%  38% |      +0.2 |     +5.1 [-47,+58]
PREREG_v2 #3 [dev>=3.0 & dev<=3.0 & bundle<=3.0SOL]            1s         a OURS   |  130     389  38% |  -4.9%  -5.6%  -6.0%  19% |     -21.2 |    -38.1 [-50,-25]
PREREG_v2 #3 [dev>=3.0 & dev<=3.0 & bundle<=3.0SOL]            1s         b JITO   |  130     389  38% |  -3.9%  -5.3%  -4.8%  23% |     -17.0 |    -30.0 [-41,-18]
PREREG_v2 #3 [dev>=3.0 & dev<=3.0 & bundle<=3.0SOL]            1s         c LANDX  |  130     389  38% |  -2.9%  -4.6%  -3.9%  25% |     -13.2 |    -22.7 [-34,-10]
PREREG_v2 #3 [dev>=3.0 & dev<=3.0 & bundle<=3.0SOL]            1s         d <=25   |  130     389  38% |  -0.9%  -3.6%  -2.2%  36% |      -5.1 |     -7.2 [-20,+8]
PREREG_v2 #3 (frozen exit)                                     10s        a OURS   |  130     389  38% |  -2.8% -12.2%  -5.6%  26% |     -12.3 |    -22.0 [-57,+15]
PREREG_v2 #3 (frozen exit)                                     10s        b JITO   |  130     389  38% |  -1.7% -10.9%  -4.4%  27% |      -7.6 |    -13.1 [-48,+24]
PREREG_v2 #3 (frozen exit)                                     10s        c LANDX  |  130     389  38% |  -0.8% -10.9%  -3.5%  27% |      -4.1 |     -6.2 [-41,+31]
PREREG_v2 #3 (frozen exit)                                     10s        d <=25   |  130     389  38% |  +1.0%  -9.3%  -1.8%  29% |      +3.1 |     +7.6 [-28,+45]
PREREG_v2 #4 [dev>=3.0 & bundle>=1.0SOL & bundle<=3.0SOL]      1s         a OURS   |  123     368  50% |  -3.7%  -5.6%  -5.4%  25% |     -15.4 |    -27.1 [-43,-10]
PREREG_v2 #4 [dev>=3.0 & bundle>=1.0SOL & bundle<=3.0SOL]      1s         b JITO   |  123     368  50% |  -2.1%  -4.2%  -4.0%  31% |      -9.5 |    -15.8 [-32,+2]
PREREG_v2 #4 [dev>=3.0 & bundle>=1.0SOL & bundle<=3.0SOL]      1s         c LANDX  |  123     368  50% |  -0.6%  -3.5%  -2.6%  36% |      -3.7 |     -4.8 [-21,+13]
PREREG_v2 #4 [dev>=3.0 & bundle>=1.0SOL & bundle<=3.0SOL]      1s         d <=25   |  123     368  50% |  +2.6%  -0.2%  +0.7%  50% |      +8.8 |    +19.4 [-0,+40]
PREREG_v2 #4 (frozen exit)                                     5s         a OURS   |  123     368  50% |  -4.8%  -9.4%  -7.7%  26% |     -19.4 |    -35.4 [-62,-5]
PREREG_v2 #4 (frozen exit)                                     5s         b JITO   |  123     368  50% |  -3.4%  -7.5%  -6.1%  28% |     -13.8 |    -24.7 [-51,+5]
PREREG_v2 #4 (frozen exit)                                     5s         c LANDX  |  123     368  50% |  -1.9%  -5.6%  -4.7%  33% |      -8.4 |    -14.2 [-40,+16]
PREREG_v2 #4 (frozen exit)                                     5s         d <=25   |  123     368  50% |  +1.2%  -3.0%  -1.5%  40% |      +3.7 |     +9.1 [-18,+40]
PREREG_v2 #5 [dev>=3.0 & name<=10 & tip=lunar]                 1s         a OURS   |  161     482  41% |  +0.8%  -4.3%  -1.0%  29% |      +2.4 |     +7.7 [-15,+32]
PREREG_v2 #5 [dev>=3.0 & name<=10 & tip=lunar]                 1s         b JITO   |  161     482  41% |  +1.9%  -3.6%  +0.2%  33% |      +8.1 |    +18.6 [-4,+41]
PREREG_v2 #5 [dev>=3.0 & name<=10 & tip=lunar]                 1s         c LANDX  |  161     482  41% |  +3.0%  -2.4%  +1.2%  39% |     +13.2 |    +28.5 [+6,+52]
PREREG_v2 #5 [dev>=3.0 & name<=10 & tip=lunar]                 1s         d <=25   |  161     482  41% |  +5.1%  +0.2%  +3.4%  50% |     +23.7 |    +48.8 [+26,+73]
PREREG_v2 #5 (frozen exit)                                     1.5s       a OURS   |  161     482  41% |  -0.2%  -4.8%  -1.9%  29% |      -2.5 |     -1.7 [-26,+26]
PREREG_v2 #5 (frozen exit)                                     1.5s       b JITO   |  161     482  41% |  +1.5%  -4.4%  -0.3%  32% |      +6.0 |    +14.6 [-12,+44]
PREREG_v2 #5 (frozen exit)                                     1.5s       c LANDX  |  161     482  41% |  +2.6%  -4.1%  +0.8%  35% |     +11.7 |    +25.5 [-2,+56]
PREREG_v2 #5 (frozen exit)                                     1.5s       d <=25   |  161     482  41% |  +5.1%  -2.4%  +3.1%  43% |     +23.8 |    +48.7 [+19,+82]
racedeep whale (>=5 SOL outside buy in S, +3 s)                3s         a OURS   |   40     120 100% |  -4.9%  -9.6%  -7.4%  38% |      -6.5 |    -11.8 [-21,-2]
racedeep whale (>=5 SOL outside buy in S, +3 s)                3s         b JITO   |   40     120 100% |  -5.9%  -8.6%  -8.4%  30% |      -7.7 |    -14.1 [-23,-5]
racedeep whale (>=5 SOL outside buy in S, +3 s)                3s         c LANDX  |   40     120 100% |  -5.7%  -8.4%  -8.3%  30% |      -7.5 |    -13.7 [-23,-5]
racedeep whale (>=5 SOL outside buy in S, +3 s)                3s         d <=25   |   40     120 100% |  -5.1%  -7.7%  -7.7%  32% |      -6.8 |    -12.3 [-21,-3]

VERDICT (n>=100 fires and 90% CI of SOL/day above zero): Gate B (time 1s) under d <=25: +43 SOL/day @2 SOL (90% CI +9..+80); Gate B no-name (time 1s) under d <=25: +60 SOL/day @2 SOL (90% CI +15..+105); PREREG_v2 #2 (time 1s) under c LANDX: +48 SOL/day @2 SOL (90% CI +18..+77); PREREG_v2 #2 (time 1s) under d <=25: +79 SOL/day @2 SOL (90% CI +50..+108); PREREG_v2 #5 (time 1s) under c LANDX: +28 SOL/day @2 SOL (90% CI +6..+52); PREREG_v2 #5 (time 1s) under d <=25: +49 SOL/day @2 SOL (90% CI +26..+73); PREREG_v2 #5 (frozen exit) (time 1.5s) under d <=25: +49 SOL/day @2 SOL (90% CI +19..+82)
```


# FINAL (2026-10-19 05:10 UTC) — blind overnight forward test, PAPER only

**Verdict: no rule is positive at our current landing. The landing fix is what makes money.**
- **At ~100 txs behind the create (our measured landing)**, every pre-registered rule loses on the blind run.
  - Gate B: **−2.0% per trade**. Per day at 2 SOL that is **−45 SOL/day** (90% CI −72…−18) over 1,130 fires/day.
  - The same rule on the merged binary (run `mnight`) gives −2.7%.
- **At <= 25 txs (the landing-fix ceiling)**, the bundle-SOL rules turn positive:
  - PREREG_v2 #4 (dev >= 3 & creator bundle 1-3 SOL, sell at +1 s): **+2.8% per trade, +29 SOL/day at 2 SOL** (90% CI +6.5…+52) over 522 fires/day.
  - PREREG_v2 #1 is nearly identical: +2.5%, +27 SOL/day (CI +4…+50).
- **Recommendation:**
  - Do not run any sniper rule live at today's landing. The paper fallback (Gate B, 1 s) is negative on blind data.
  - The next live money should go into the **landing test** (§ Landing study: Jito one-tx bundle / LandX arms).
  - If an arm reaches <= 25 txs, the rule to run is **PREREG_v2 #4 with a 1-s exit**.

## Blind run `night` (20:09 → 04:40 UTC; 3,346 base launches, all tracked; gates and exits frozen beforehand)
- **Frozen beforehand:** `FROZEN_GATE.txt` 20:12, `PREREG_v2.json` 20:44, `EXIT_FREEZE.json` 03:22. Nothing was refitted.
- **Realistic model:** 2 SOL; land behind every slot-S trade at offset <= d; entry x1.03; own impact; pump fee 1.25% per side; 0.009 SOL buy priority.
- **SOL/day** = mean x fires/day x size. Fires/day are measured on this run with 217-ms slots. Full table: `eval_rank_night.txt`.

| rule (exit) | fires/day | contested | d=100: mean [90% CI] → SOL/day @1 / @2 SOL | d<=25: mean → SOL/day @1 / @2 SOL |
|---|---|---|---|---|
| **PREREG_v2 #4**: dev >= 3 & bundle 1-3 SOL (1 s) | 522 | — | −1.5% [−3.5, +0.6] → −10 / −16 | **+2.8% [+0.6, +5.0] → +13 / +29** |
| **PREREG_v2 #1**: dev >= 3 & bundle >= 1 tx & <= 3 SOL (1 s) | 545 | — | −1.7% → −11 / −18 | **+2.5% [+0.3, +4.6] → +12 / +27** |
| PREREG_v2 #3 (gross/net dev artefact; 10 s) | 568 | — | +1.3% [−3.0, +6.1] → +7 / +15 | +4.2% [−0.2, +9.0] → +24 / +48 |
| Gate B no-name: dev >= 3 & bundle >= 2 tx (1 s) | 2,220 | — | −1.9% → −52 / −85 | +1.0% [+0.1, +1.8] → +14 / +43 |
| **Gate B** (frozen fallback, 1 s) | 1,130 | 30% | **−2.0% [−3.1, −0.8] → −27 / −45** | +0.8% [−0.4, +2.0] → +5 / +17 |
| Gate B strict (bundle >= 3) | 686 | — | −2.3% → −19 / −31 | −0.1% → −3 / −2 |
| PREREG_v2 #2 (bundle 3-5 SOL & Lunar) | 844 | — | −1.3% (1 s) | +1.0% |
| PREREG_v2 #5 (dev >= 3 & name <= 10 & Lunar) | 483 | — | −1.8% (1 s) | +0.9% |
| FIX base filter (1 s) | 9,450 | 23% | −2.3% → −264 / −444 | 0.0% |
| stream race gate (>= 2 SOL outside in 100 ms) | 2,076 | 55% | −4.1% | −4.0% |
| *hindsight: perfect race pick* | 2,129 | 100% | *+5.7% → +241 SOL/day @2* | *+12.6%* |
| *hindsight: 4yFAz's picks* | 113 | 35% | *+1.4%* | *+8.5%* |

- **Fat-tail "runner" exits** (sell 50-85% at 1 s, trail the rest, 10 s cap), fitted pre-night, are worse than a plain 1-s exit on the blind data for every rule. Example: Gate B −3.3% vs −2.0%.
- **Medians are −3% to −5% everywhere.** All the gain is in the tail, as the owner accepts. At d <= 25 the 90% CIs of #4 and #1 exclude zero; at d100 nothing does.
- **Merged binary** (`/root/sniper-merge`, run `mnight`, 22:02 → 04:42, 325 Gate-B fires): Gate B −2.7% at d100 (1 s), +0.3% at d <= 25. It agrees with `night`. The engine ran 0 restarts and 0 panics in either run.
- **X/Twitter at launch time** (`tweets_fwd.txt`, 3,101 launches with metadata fetched live):
  - Latency: metadata p50 530 ms; full X data p50 776 ms, p90 2.3 s. Only 4% are done within 300 ms.
  - No lift. Tweets with >= 10 likes at launch: 13% race and −4.1%, vs 23% race and −2.4% for all launches.
  - It is not usable, and not predictive.

## Expected SOL/day at 2 SOL — the honest line
- **Today (land ~100 txs):** negative for every rule; Gate B ≈ −45 SOL/day. **10-20 SOL/day is not reachable.**
- **After a landing fix to <= 25 txs:** PREREG_v2 #4 ≈ **+29 SOL/day (90% CI +6…+52)** at 2 SOL, or +13 at 1 SOL.
  - That is above the owner's 10-20 SOL/day target, but only if every fire lands <= 25 txs.
  - Mixing in S+1 landings (−4% per trade) erases it.
- **The one thing to prove next is the landing:** median d <= 25 on >= 80% of fires.

# Race / 4yFAz-like selection: NOTES (paper only, no --live, nothing sent)

> **STATUS — milestone 6 (FINAL above), 2026-10-19 05:10 UTC.** The milestone notes below are kept for the record. The overnight forward PAPER run `night` (20:09 → ~04:40 UTC) is running. FINAL numbers will be at the top by ~05:30 UTC.
> - **Recommended today = FALLBACK:** Gate B with a 1-s exit (exact command below). At realistic prices and our current landing it is **about break-even to slightly positive, not proven**.
> - **The gap to "like 4yFAz" is mostly landing position, then selection.** It is quantified below.
> - **Correction made at 20:40 UTC:** slots are **217 ms**, not 400 ms (measured: 851k slots in 184k s of block time). All times, exits and rates below use the real 217 ms.
>   - "1 s" is ~4.6 slots and "S..S+5" is ~1.3 s.
>   - The earlier tables used 400 ms; their "1 s / 3 s" were really ~0.54 s / ~1.6 s, and their per-hour rates were 1.84x too low.
>   - The frozen gate is unchanged. Its exits are evaluated in real time.
> **Overnight run progress (04:49 UTC):** 3548 base launches seen, 396 fired by the frozen Gate B, 3548 labelled on chain, 3536 metadata/X fetches, 0 engine restarts; merged-binary run `mnight`: 2628 seen, 325 fired. Outcomes are not looked at until the runs end (blind test).

## Bottom line so far
- **Realistic prices:**
  - Trade: 2 SOL; we land in slot S behind every trade at offset <= 100 txs (our measured median when we land in S is 104); entry price x1.03; own impact on both legs.
  - Fees: pump fee 1.25% per side, 0.009 SOL buy priority, 0.001 SOL per sell.
  - The **cost floor is ~5.5% per round trip**, so the median trade of every gate is about -4% to -5%.
- **What each set returns at realistic prices.** Historical test (last 40%) plus forward run 1 (2 h census), pooled. Mean / median per trade, exit = sell 1 s after our buy:

| set | n | land behind 5 txs | 25 txs | 50 txs | **100 txs (us today)** | 150 txs |
|---|---|---|---|---|---|---|
| FIX base filter (`--dev-from-cap`, dev 0.5-8, host ok, vanilla) | 1271 | +0.8% / -3.7% | +0.2% / -4.0% | -0.7% / -4.5% | **-1.8% / -5.0%** | -2.4% |
| **Gate B** (dev >= 3, creator bundle >= 2 txs, name <= 12) | 181 | +5.1% / -0.6% | +4.8% / -0.8% | +3.0% / -2.0% | **+1.8% / -4.0%** | +1.1% |
| dev >= 2 | 600 | +2.5% | +2.1% | +0.8% | **-0.4%** | -1.0% |
| hindsight: perfect race pick | 298 | +15.5% / +12.5% | +13.6% / +10.5% | +11.2% / +8.6% | **+7.8% / +4.5%** | +6.3% |
| 4yFAz's own picks (hist test) | 167 | +11.3% / +6.6% | +8.6% / +5.0% | +4.6% | **+2.4% / -1.9%** | +0.8% |
| 4yFAz's own picks (forward) | 17 | +11.9% / +6.9% | +11.1% | +8.9% | **+5.2% / +4.9%** | +0.7% |

(`land_req.txt` also has the 3-s exit, which is worse for Gate B: -1.0% at 100 txs.)

- **Gate B by period, sell at +1 s, realistic:**
  - historical train: -1.4% (n=65, median -4.9%);
  - historical test: +3.1% (n=40);
  - forward run 1: **+1.6% (n=143, median -3.9%, win 37%, s.e. about ±1.2%)**.
  - Its best exit is 0.8-1.25 s everywhere; 3 s is worse (-1.9 / +8.4 / -2.6%).
- **The exact gap.** "+10-20% per trade" needs both:
  - **Landing at <= 25 txs behind the create.** We land at ~100, and in S only 16 of 42 times today.
  - **His selection quality, which no visible feature reproduces.** At <= 25 txs Gate B is +4.8%, his picks +9-11%, perfect race selection +13.6%.
  - At our current landing even perfect race selection gives +7.8% mean / +4.5% median.
- **Expected SOL/day at 2 SOL.**
  - Gate B fires ~70/h (forward run 1; the base filter saw ~490 launches/h). That is ~1,700/day.
  - At +1.6% ± 1.2% per trade: ~+55 SOL/day ± 40 (1 s.e.) on paper. It is tail-driven (median -4%) and assumes we land in S at ~100 txs every time.
  - Landing in S+1 (half our live fires today) costs ~4 points per trade, which turns this negative.
  - **10-20 SOL/day "at quality" (+10-20%/trade) is not plausible at today's landing.** A volume version of Gate B might reach it on paper but is not proven.
- **4yFAz himself does not make +10-20% per trade.** His 494 real trades over ~4 days average **+3.0% (median -2%)**: median fill 1.13x, size 1.5 SOL, median hold 12 s (first sell at a median 4 s). He makes ~10 SOL/day through volume (~120 trades/day) and by landing first (offset 0-1).
  - **His selection is still real.** His attempted-but-unfilled launches (a failed buy, the price ran) are 90% races (n=10 in the sample).
  - **Copying him in the stream does not work.** Landing 5 txs after his buy: -3.5% (n=383).

## What separates his picks (work item 1)
- **His-like score.** Weighted logistic regression of his picks vs random launches he did not buy, inside the FIX universe. Fit on the first 60%, test on the last 40% (`his_score.txt`).
  - Create tx only: AUC 0.61. +bundle: 0.63. +creator wallet history (RPC): **0.73**. +metadata or X: no better.
  - The top 15% by score have 3-5% his-precision vs a ~2% base. Realistic PnL of those tiers is negative, except tiny top-2% buckets (n=6-10).
  - Strongest weights: creator bundle present (+), dev >= 2 SOL (+), fresh creator with 0 prior launches (+), serial creator (-), creator idle >= 30 min (+), large bundle SOL (-), j7tracker host (-).
- **Early pro buyers in the stream** (`pros.json`): they mostly arrive *after* him. Waiting for them costs the entry (see the stream gate below).

## Off-chain X/Twitter (work item 2) — no lift, and too slow
- **Source:** `api.fxtwitter.com` (public). It returns author followers, joined date and verification, plus likes/views as of the fetch time. `cdn.syndication.twimg.com` works too but has no follower counts.
- **2,362 links fetched** for the historical sample (`tweets.jsonl`). His picks vs random launches:
  - status link 53% vs 65%;
  - median followers ~10^1.4 vs 10^1.9;
  - deleted tweet 31% vs 21%;
  - verified 32% vs 41%;
  - tweet < 5 min old 37% vs 47%.
  - So **"tied to a real, fresh, high-engagement tweet" is, if anything, anti-correlated with his picks.**
- **Latency, measured live tonight** (`meta_watch.py` beside the paper run, `meta_night.jsonl`):
  - metadata JSON p50 0.53 s, p90 1.5 s. ipfs.io and dweb.link return 403 to this server; ipfs.filebase.io works.
  - plus the tweet: p50 0.94 s, p90 2.7 s.
  - **Not usable for a same-slot entry** (needs <= 0.1-0.3 s). A cache would only help repeat authors.

## Exits like his (work item 3)
- **Exits tested** (`hc_search.py`; fitted on historical train, judged on historical test and forward run 1):
  - time exits 0.2-40 s;
  - TP and 2-3-leg TP ladders;
  - trailing stops;
  - "sell X% when one outside buy of >= Y SOL arrives after us" (whale trigger);
  - "dead-token cut": sell at +W ms unless >= Y SOL of outside buys has come in since our entry, else hold to T.
  - "Sell when >= Y SOL of outside buys has arrived" is the same as a TP at price ((v+Y)/v)^2 on the curve, so the TP ladders cover it.
- **Result: none beat a plain 1-1.5 s time exit out of sample.** For Gate B (train / test / forward):

| exit | train | test | forward |
|---|---|---|---|
| 1 s | -1.4% | +3.1% | **+1.6%** |
| 1.5 s | +0.5% | +5.1% | -0.4% |
| confirm 600 ms >= 0.5 SOL else cut, 1 s | -1.3% | +3.2% | +1.5% |
| 3 s | -1.9% | +8.4% | -2.6% |
| TP +30% / 10 s | — | +0.6% | -5.0% |

- **His same-block scale-out only works from his position (+1).** From ~+100 the whales are already in our entry price (GHEc at our landing: 2.85x floor).
- **The live engine already supports a pure time exit:** `--exit-cap-ms 1000 --derisk-frac 0 --ladder-frac 0 --ride-mult 99 --cut-r 0`. `exit_ladder` reads the same flags, so no new code is needed.

## Gates tested (work items 1 and 4), out of sample, realistic prices
- **Stream race gate** (>= 2 SOL of outside buys within 100 ms; forward run 1, 209 fires):
  - Picks races: 60% are races vs 15% of the launches it rejected, and 12 of the 17 4yFAz buys in the window.
  - But realistic 1 s is **-3.4%**, because entry is already at 1.34x floor.
- **Gate B** (zero wait, ~3 ms): race rate 35% vs 25%. Realistic 1 s: +0.3% (forward, n=143), +0.8% (historical test, n=40). 3 s: -1.2% forward, +5.1% historical test.
- **Strictest Gate-B variants** (dev >= 4, bundle >= 3 txs, name <= 10/12): n=9-34, -1.8% to +7%, inconsistent between periods.
- **A 3-period robust search** (`hc_multi_v2.txt`, real 217 ms timing; worst-period mean across hist-train, hist-test, forward run 1) over 5,693 rules: the best worst-period means are +1.9% to +2.6%, and medians are negative except one.
  - The top 5 are pre-registered in **`PREREG_v2.json` (written 20:44 UTC)** and judged only on the overnight run:
    1. dev >= 3 & creator bundle >= 1 tx & bundle <= 3 SOL, exit TP +30% else 10 s. Periods: +2.6 / +2.3 / +2.8%; forward median +1.6%.
    2. bundle 3-5 SOL & Lunar-tipped create, exit 5 s: +2.5 / +1.9 / +3.6%.
    3. and 4. near-duplicates of 1.
    5. dev >= 3 & name <= 10 & Lunar-tipped create, exit 1.5 s.
  - **Artefact warning:** `PREREG.json` (20:36, 400-ms timing) and `PREREG_v2` #3 contain "dev >= 3 & dev <= 3". That is a gross-vs-net dev artefact (forward dev = gross ix amount, historical = net of fee). Ignore those.

## Frozen for the overnight run (`FROZEN_GATE.txt`, 20:12 UTC, before any look at its outcomes)
- **Gate B:** effective dev (incl. cap-family) >= 3 SOL AND creator bundle >= 2 buy txs within 3 ms AND name <= 12 chars, on top of the base filter.
- **Exit:** 3 s; alternative 1 s. Strict variant: bundle >= 3 txs.

## Landing study (READ-ONLY, 2026-10-19 ~02:00 UTC). Script `landing_study.py`, output `landing_study.txt`, config `probe_landing.toml`
**Data.**
- 7,002 outside buys that landed in the create slot S: 2,765 historical (Oct 14-18 sample plus 4yFAz picks) and 4,237 from tonight's forward census.
- 478 4yFAz buys and our 18 live buys of today that landed in S.
- 141 independent buys plus 4yFAz looked up on bundles.jito.wtf.
- Position d = non-vote txs after the create. Time = d x 217 ms / non-vote txs in the block.

### 1. Where our time goes (today's live buys)
- **The create sits at a median 92 ms into its 217-ms slot** (p25 39, p75 145). That leaves **125 ms (p25 72)** for a same-slot entry.
- **Inside the engine:** shred → send < 1 ms (BUY-PREP 0.3-0.4 + SEND-PREP 0.1-0.2), warm fra-sender 0.5-0.8 ms, and Kaldera arrives 1.5 ms before erpc (detection agent, `/root/det/NOTES.md` §18).
- **Our tx lands a median 45-52 ms after the create** when it lands in S (d = 38…407), but **only 16 of 42 fires landed in S**, and **only 2 of 10 races**.
  - On our 18 same-slot buys, just 2 outside buys were ahead of us.
  - **We make slot S only on quiet launches. On contested ones we land in S+1.**
- **Other Helius-tipped outside buyers:** median 56 ms after the create (p10 17.5 ms); 7% reach d <= 25.
  - So our Helius latency is typical for Helius. The missing ~35-40 ms vs the fast lane is outside our process: shred delivery to us, then relay → leader → scheduler. The engine is not the bottleneck.
- **The fast lane (d <= 25) is reached 1-11 ms after the create.**

### 2. Who lands <= 25 txs behind the create
- **d <= 5 (~1 ms after the create; 428 buys) is not a lane we can join.**
  - Senders: 54% Jito-tipped, 41% no tip. cu_price ≈ 0.
  - Leaders: BAM (AgaveBam) and Harmonic.
  - It is dominated by wallets that are *always* at d <= 5 (AzcvjR3, BPKVyy, 9ikSKk, 5qsuh6, DTGbH6, 3ZxbA4: 11-13 of 12-14 buys each). These are launch-tool bundler wallets riding with the create, not snipers.
- **d 6-25 (~10 ms; 475 buys) is the lane to aim for.**
  - Senders: Helius 27%, no tip 19-27%, Jito 10-14%, LandX 9-10%, Astralane 8-9%, Nozomi 7%.
  - Tips p50 0.002-0.003 SOL. cu_price p50 ~0.05M, p75 21M µlamports/CU.
  - Leaders: Jito-Solana (JitoLabs) 44-47%, BAM 32%.
  - In the Jito-explorer sample, **42% of independent d 6-25 buys were inside Jito bundles** (15 of 20 multi-tx), all on BAM / FireBAM leaders. At d 26-150 the share is 28%.
- **Which sender reaches d <= 25, by leader client** ("fast-rate" = share of that sender's buys landing d <= 25):

| leader client (share of outside buys) | Jito-tipped | LandX | Helius | Astralane | Nozomi | no tip |
|---|---|---|---|---|---|---|
| BAM / AgaveBam (~34%) | **38%** (med d 47) | **26%** (med d 51) | 5% (med d 102) | 3% | — | 13% |
| Jito-Solana / JitoLabs (~28%) | **21%** | 17% (med d 46) | 13% | 10% | 9% | 20% |
| Firedancer (~9%) | **30%** | 16% | 6% | 19% | 14% | 16% |

- **Priority alone is not the lever.** Share landing d <= 25 by cu_price: >= 100M (ours) 17%, 10-100M 8%, 1-10M 11%, < 0.1M 17%. We already pay 100M x 90k CU = 0.009 SOL.
- **4yFAz:**
  - OK buys at d p50 49 (~30 ms), p25 24.
  - cu_price p50 110M, p75 388M, p90 988M µlamports/CU (up to ~0.09 SOL of priority).
  - Tipped 45% (tip p50 0.015 SOL). Senders: no tip 55%, Helius 14%, Nozomi 12%, LandX 10%.
  - **He sprays: p90 45 txs in slot S per launch, and 91% of his txs fail.** His fast landings are spread over Jito-Solana, BAM and Harmonic.
- **Other fast wallets:**
  - dKMjeG: Helius, no priority, med d 48.
  - 9qz7cW: mostly no tip plus Jito, med d 65.
  - FiFawH: Jito 22/33, cu 21M, med d 30.
- **Reaction time.** The fast lane reacts in <= ~10 ms, we in ~45-52 ms.
  - We cannot split shred-in vs relay-out without an absolute PoH clock; the DETECT lag_ms is relative to the slot's first arrival.
  - Since buyers on the same relay (Helius) reach 17 ms at p10, part of our gap is the input side, plus timing luck within the slot.

### 3. Levers ranked by expected gain in landing position (cheap to test live, ~$0.10 per round trip; owner's call)

| # | lever | evidence | how to test (flags/config) |
|---|---|---|---|
| 1 | **Jito path on BAM and Jito-Solana leaders**, as a one-tx bundle | Jito-tipped buys reach d <= 25 **38% on BAM vs Helius 5%**, and 21% vs 13% on Jito-Solana. A failed bundle costs nothing. | `--config /root/race/probe_landing.toml --send-path jito-bundle` (whitelisted `auth_keypair ~/.nexus-v2-jito-auth.json`, tip 0.002 SOL, max 2/s) or `--send-path jito-tx` (`JITO_UUID`). Score by leader client with `measure_land.py`. |
| 2 | **LandX** (Cherry Frankfurt, UDP) | Fast-rate 16-26% on every client, median d 46-56: the best non-Jito relay. | `--send-path landx-fra3` (`LANDX_KEY`, tip 0.001). |
| 3 | **Spray 2-3 relays with ONE signature** (4yFAz-style) | He sprays (p90 45 txs per launch). One signed tx with several tip transfers can land at most once, so there is no double buy. | `--send-path jito-tx --also-send landx-fra3` (AFTER_FINAL: also-send applies to buys only). Extra cost: +0.001 SOL tip. |
| 4 | **A bigger Helius tip** | The fast Helius buyers tip p50 0.0048 SOL; we tipped 0.001. | `--send-path helius-tip5` (0.005 SOL). Shares the keyless 1 req/s budget. |
| 5 | **Per-leader-client routing**: BAM → Jito; Jito-Solana → Jito/LandX; Firedancer → Jito/Astralane; Harmonic → Nozomi/Astralane (indep finding) | The table above. | **Not in the snipe engine yet.** It needs a small send-path change (owner's OK); the leader map already exists in the close-leaders code. Test the arms first (1, 2) and route by their per-client results. |
| 6 | **Helius API key** | Keyless = 1 req/s; buy+sell collisions are 429-refused (detection notes §13). | Add `HELIUS_API_KEY`. This improves reliability, not position. |
| 7 | **Drop `--close-leaders`** | It skips ~40% of launches; it is about coverage, not position. | Omit the flag. |
| 8 | **Higher cu_price** | No monotonic gain above 10M. 4yFAz pays 110-988M, but mostly on no-tip paths where cu_price orders the scheduler. | Only relevant for `staked-rpc` / `tpu-direct` arms. |
| 9 | **Faster shred source** | Kaldera vs erpc differ by only 1.5 ms. The 35-40 ms gap to the fast lane is unexplained, and the input side is the remaining suspect. | Not cheap. It needs a co-located or staked turbine feed or Jito ShredStream, compared through the DETECT t_rx lines. |
| 10 | **Stellium / 0slot / SpeedLanding** | 0slot is slow (indep). SpeedLanding has an 18% fast-rate on BAM (small n). Stellium is not identifiable in tips. | `--send-path speedlanding` is configured. |

- **Exact test protocol** (owner decides; paper first, then live; I sent nothing):
  1. Run the detection agent's recommended command (`/root/det/NOTES.md`, last section) with `--config /root/race/probe_landing.toml`, changing only `--send-path` per arm: jito-bundle, landx-fra3, helius-tip5, plus the current helius as control.
  2. Each arm: 6-10 buys of 0.001 SOL, ≈0.011-0.015 SOL per round trip, ~0.1-0.15 SOL per arm. Interleave arms over the same hour if possible.
  3. Then: `python3 /root/race/onchain.py /root/race/<tag>_onchain.jsonl 4 <live log>` and `python3 /root/race/live_land_pos.py` (edit its log list), or `/root/bsplit/measure_land.py <log>` for position by leader client.
  4. **Pass:** median d <= 25 and >= 80% in S on one arm, per client.
- **Why it matters (realistic prices, sell at +1 s):**
  - Gate B: +1.8% at d100 → **+4.8% at d25 → +5.1% at d5**.
  - Perfect race selection: +7.8% → +13.6% → +15.5%.
  - 4yFAz's picks: +2.4% → +8.6% → +11.3%.

## RECOMMENDED BINARY (merged build) and EXACT paper command
- **Binary:** `/root/sniper-merge/target/release/snipe_engine`, md5 1bb9e449…, built 21:55 UTC, BUILD_EXIT=0.
  - It is the detection agent's AFTER_FINAL (`/root/sniper-det`, see `/root/det/NOTES.md`) plus race patches 7-8. AFTER_FINAL already contained race patches 1-6.
  - From AFTER_FINAL: 99.3% create coverage, router/CPI creates, lookup-table accounts, non-SOL-quote and legacy launches skipped, dev-buy pricing for cap-family buys, holder/creator-fee misreads fixed, 215-ms PoH clock, feed-stall reconnect, atomic path dumps.
  - Race patches 7-8 add the metadata `uri=` log and `--race-min/max-bundle-sol` / `--race-create-tip-prefix`.
  - Build script: `/root/race/dobuild_merge.sh <log>`. Untouched source: `/root/race/snipe_engine.rs.arbx-det_AFTER_FINAL`.
- **Smoke test** (`paper_msmoke.log`, 5 min, paper): 55 base launches, Gate B decided at ~3 ms and fired 6, 49 rejects shadow-tracked, bundle SOL estimated, uri logged, **0 panics**.
- **Additional overnight paper run on this binary:** `mnight`, 22:02 → ~04:40 UTC, frozen Gate B, fired positions only. It will be scored next to the blind run.
- **The fallback strategy:** Gate B with a 1-s exit. The merged binary gives the same gate with the detection fixes.
```
cd /root/sniper-merge && set -a && . /root/sniper/deploy/.env && set +a && \
export KALDERA_TOKEN=$(grep -o "KALDERA_TOKEN=[^ ]*" /root/collect_blfwd.sh | head -1 | cut -d= -f2) && \
./target/release/snipe_engine --paper-trade --minutes 120 --entry-at-floor --max-r-cap 20 \
  --min-dev-buy 500000000 --max-dev-buy-sol 8 --uri-blacklist \
  --derisk-frac 0 --ladder-frac 0 --ride-mult 99 --cut-r 0 --exit-cap-ms 1000 \
  --size-sol 2.0 --dump-paths /root/race/paths_<tag>.jsonl --max-inflight 48 \
  --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
  --dev-from-cap --race-gate --race-min-dev-sol 3 --race-min-bundle 2 --race-bundle-ms 3 --race-max-name-len 12 \
  --race-pros /root/race/pros.json --race-track-rejects \
  < /root/.nexus-v2-trading-wallet.pass >> /root/race/paper_<tag>.log 2>&1
```
- **Exit flags:** `--exit-cap-ms 1000` with derisk/ladder/ride/cut neutralised is a pure 1-s time exit. The live `exit_ladder` reads the same flags.
- **Why `--entry-at-floor`:** only so the dumped paths are price/floor, which the realistic scorer expects. The engine's own PAPER-TRADE RESULT then enters at the floor and is **far too optimistic**: run 1 showed +86%/trade there against ~0% realistic. Ignore it.
- **The same command on `/root/sniper-race/target/release/snipe_engine`** (race patches only, no detection fixes) is what the blind overnight run uses.
- **Stall-aware runners:** `/root/race/paper_race3.sh <tag> <minutes> <race flags>` (merged) and `/root/race/paper_race2.sh` (arbx-race). They add the older ladder flags; scoring is unaffected.
- **Score any run realistically:**
  `python3 /root/race/onchain.py /root/race/<tag>_onchain.jsonl 6 /root/race/paper_<tag>.log` then `python3 /root/race/score_run.py <tag>`.
  It prints per-hour rate, contested rate, realistic avg/median/ex-top3/win, SOL/day at 2 SOL, and landing sensitivity.
- **Checked on arbx-race at 21:10 UTC** (`run_exact_smoke.sh`, 3 min): 19 seen, 1 fired, report printed.

## Build and housekeeping
- **`/root/sniper-race`:** a separate copy holding all the race patches, plus RACE seen logging the URI. Build with `/root/race/dobuild_race.sh <log>`.
- **`/root/sniper-fast` was restored to its original state** at 20:15 UTC:
  - binary md5 fdb08b48 = the 18:18 build, from `/root/snipe_engine.bin.bak_race`;
  - sources = `/root/snipe_engine.rs.bak_race` and `/root/snipe.rs.bak_race`.
  - The patched sources from earlier today are kept as `/root/race/*.race_final_in_arbx-fast`.
- **Flags:** see "Engine patch" below. All default off.
- **Added tonight in `/root/sniper-race` only:**
  - RACE seen logs the metadata `uri=` (patch 7).
  - `--race-min-bundle-sol F` / `--race-max-bundle-sol F`: creator-bundle SOL within `--race-bundle-ms`.
  - `--race-create-tip-prefix P`: the create tx's largest SOL transfer goes to an account starting with P; `moon` = Lunar Lander (patch 8).
  - A 5-minute smoke run (`paper_smoke8b.log`) shows `bundle_sol` estimated and the gate deciding at 3 ms as intended.
  - Build: `/root/race/dobuild_race.sh <log>`, BUILD_EXIT=0.


---
# APPENDIX A — afternoon race study (2026-10-18). OLDER cost model: 1 SOL, no slip, 0.0013 SOL fees, so its PnL figures are ~3-5 points higher than the realistic ones above.

Read-only research plus PAPER runs only. No `--live`, no sends. Keys and `/root/sniper/deploy/.env` untouched.
Full output: `report.txt`. Scripts and caches: this folder.

## Verdict (short)
1. **Our live fires were not dead launches.** Checked on chain, today's 42 live fires:
   - 76% had >= 2 outside buyers in S/S+1. Most of those are broad bots that buy almost everything.
   - 24% were real races (strict label below). That is the base rate of the filter (20-26%).
   - **We lost them on landing.** We landed in the create slot on only 16 of 42 (median position 104 txs after the create, never <= 25). On the 10 races we landed in S twice.
2. **4yFAz picks are only moderately busier than ours.** 35% of his picks are races (strict label), against 24% of our live fires and 20% of the fixed filter. His edge is mostly position:
   - If we had his picks, sold 1 s later: +15% landing 5 txs behind the create, +12.6% at 25 txs, **+4.4% at 100 txs (where we land)**, +1.7% at 200.
   - Perfect hindsight race selection: +16% / +13% / **+5.5%** / +4.1% at the same positions.
3. **The dev-buy bug was hiding most of his launches.** The old filter fires on only **13% of his picks**. With `--dev-from-cap` it fires on **76%**. Fire rate rises from ~41/h to ~216/h, and the race rate stays at ~20%.
4. **A race cannot be called at create time.** All create-tx, creator and metadata features give a lift of 2x at best:
   - Best zero-wait rule: dev >= 3 SOL & creator bundle >= 2 txs (& name <= 12 chars) → 36-43% races vs 20%.
   - Its 4yFAz precision stays at ~1.5-2%, the same as the base.
5. **The first 50-200 ms of the shred stream does call it.** Rule: >= 2 SOL of outside buys within 100 ms.
   - 71% races (3.5x the base).
   - 8% of its fires are also 4yFAz buys (4x the base; 5% when his own buy may not trigger it). It catches 31% of his picks.
   - **But by then the herd is in.** The median entry is 1.37x floor. Realistic 1-s return: -0.3% (test) / -2.3% (all). Firing the instant the trigger trips (no wait) is still -0.3% to -1%.
   - So the gate picks busy launches like 4yFAz does, but at our landing it does not make money.
6. **Ready for live?** Not as a profit test. See "Live test proposal".

## Data and method
- **Universe:** the `/root/nob` sample, SOL-quoted launches only, in slots 457.56M-458.41M (~95 h).
  - 2,618 uniform random creates. Each stands for ~27 creates; the population is ~750 SOL launches per hour.
  - 494 4yFAz picks.
  - Launches before the RPC ledger start (457.557M) are dropped.
- **Slot S:** from the create block (`/root/nob/blk_*.jsonl`), in block order.
- **Slots S+1..S+5 (~2 s):** new collection `race_collect.py` → `s1.jsonl`. It lists every signature on the mint, then fetches every OK tx (cap 90 per launch; 29 launches hit the cap).
- **Later price path:** `/root/nob/paths_*.jsonl`, plus `paths_extra.jsonl` for 432 bundled or filter launches that had no path.
- **Outsider** (`race_lib.labels`): an OK buy whose payer and buyers are not any of:
  - the creator, a create-tx signer, or our wallet;
  - a glued creator-bundle wallet.
  - Exception: a glued tx from a known multi-creator sniper wallet (`pros.json`: 591 wallets, from the INDEP class in `/root/indep/buyers.jsonl` plus wallets buying >= 3 creators' launches) counts as an outsider, and the bundle is treated as ended there. This catches 4yFAz at +1, as in GHEc.
  - **4yFAz is excluded from the label counts**, so "his picks are races" is not circular.
- **Time split:** fit on the first 60% by slot, test on the last 40%. 4yFAz precision is population-weighted; recall is over all his picks in the test period.
- **Realistic PnL** (`race_an.sim`):
  - Entry: 1 SOL behind every S trade at non-vote offset <= d_land. d_land = 100 txs + the rule's wait; ~100 ms in a typical block, 0.94 ms per tx.
  - Costs: own price impact on both legs, pump fee 1.25% per side, 0.0013 SOL fees per round trip.
  - Exits: X1 = sell at +1 s; X2 = TP +30% else 10 s; X3 = TP +100% else 30 s.
  - "S+1" = landing one slot late, behind all of S.
- **Landing assumption:** "behind the first ~100 txs" is checked on our 42 live fires today: median 104 when we land in S.

## 1. Race label and sensitivity
Share of launches that pass each definition. Counts exclude 4yFAz; the 2 s window is S..S+5.

| group | n | S>=1 out | S+S1>=2 | S+S1>=3 | S+S1>=5 | 2s SOL>=1 | 2s SOL>=3 | **RACE** | 2s>=5 & >=5 SOL |
|---|---|---|---|---|---|---|---|---|---|
| all SOL launches | 2618 | 20% | 19% | 12% | 4% | 16% | 8% | **8%** | 4% |
| not mayhem | 1798 | 28% | 27% | 17% | 6% | 24% | 12% | **11%** | 6% |
| OLD filter (sized dev 0.5-8) | 158 | 56% | 59% | 41% | 19% | 47% | 27% | **26%** | 15% |
| FIX filter (dev-from-cap) | 794 | 49% | 48% | 30% | 13% | 41% | 21% | **20%** | 10% |
| 4yFAz picks | 494 | 62% | 64% | 46% | 22% | 65% | 38% | **35%** | 23% |
| our 42 live fires today | 42 | 55% | 76% | 52% | 26% | 62% | 24% | **24%** | 19% |

- **Primary RACE label:** >= 3 distinct outside buyers AND >= 3 SOL of outside buys in ~2 s. Second label: 4yFAz bought it.
- **Sensitivity:**
  - A loose count (>= 2 outsiders in S/S+1) says 59-76% of our fires were "contested". Broad bots inflate it: haqqiUUXB5 is on 11 of our 42, CWiNFAEk on 5.
  - Every stricter definition ranks the groups the same way: his picks > old filter ≈ our fires > fixed filter.
  - Median outside SOL in 2 s: his picks 1.94, old filter 0.88, our live fires 1.46, fixed filter 0.51.

## 2. What predicts a race (visible at create time or soon after)
Base: not mayhem, host not a bot pad. Race rate: train 11.5%, test 10.9%. Lift is test race rate over base. Full table in report §2.

| tier (latency) | best single conditions (test race %, lift) |
|---|---|
| E: shred stream, outside buys in S | >= 2 SOL outside in 50 ms: 76% (7.0x); in 100 ms: 68% (6.2x); >= 0.5 SOL in 50 ms: 41% (3.7x); >= 1 outside buy in 100 ms: 34% (3.1x) |
| B: creator bundle in the same entry (~1-3 ms) | bundle >= 3 SOL 30% (2.7x); bundle >= 2 txs 26% (2.4x). **No bundle: 5%** |
| A: create tx itself (0 ms) | dev >= 3 SOL 30% (2.8x); dev >= 2 SOL 28% (2.6x); dev >= 1.5 SOL 25% (2.3x) |
| C: creator wallet (RPC 10-50 ms) | creator balance >= 11 SOL 26% (2.4x); 0 prior launches 1.3x |
| D: metadata JSON (50-500 ms) | socials, twitter, website: <= 1.5x |

- **Weak or no signal:** cu price, priority fee, the create's tip sender (Jito, Helius, Nozomi and Astralane creates race less, at 0.2-0.7x), host, name style, tx version, leader client, cap vs sized dev ix.
- Combos stay at 2x until stream signals are added:
  - tier A best: dev >= 1.5 & sized & name <= 12 → test 44% (n=25);
  - tier B best: dev >= 3 & name <= 12 & bundle >= 2 txs → test 42% (n=38);
  - tier E best: >= 2 outside buys and >= 2 SOL in 200 ms → test 72% (n=32).

## 3. Out-of-sample summary of candidate gates
Test = last 40%; 1 SOL; exit X1 (sell +1 s).

| gate | n | race | 4yFAz prec | 4yFAz recall | fires/h | entry/floor | **X1 @ our landing** | 80/20 S/S+1 | X1 if we land at 25 |
|---|---|---|---|---|---|---|---|---|---|
| OLD filter (today) | 57 | 21% | 1.8% | 13% | 41 | 1.20x | -0.4% | -0.5% | +1.4% |
| FIX (`--dev-from-cap`) | 302 | 20% | 2.1% | **76%** | 216 | 1.11x | +0.3% | +0.2% | +2.4% |
| G-B dev >= 2 & bundle >= 1 SOL (3 ms) | 99 | 32% | 1.4% | 17% | 71 | 1.28x | +1.3% | +1.1% | +3.5% |
| G-E50 >= 1 outsider & >= 0.5 SOL in 50 ms | 47 | 40% | 5.2% | 30% | 34 | 1.27x | +1.1% | +1.3% | +2.4% |
| **G-E100 >= 2 SOL outside in 100 ms** (forward-run gate) | 31 | **71%** | **8.2%** | 31% | 22 | 1.37x | **-0.3%** | -0.0% | -0.8% |
| G-E100b >= 2 outsiders & >= 2 SOL in 100 ms | 23 | 70% | 8.4% | 24% | 16 | 1.30x | -0.2% | -0.1% | -0.6% |
| hindsight: perfect race pick | 59 | 100% | 3.7% | 27% | 42 | 1.31x | +6.7% | +6.8% | +13.3% |
| 4yFAz's own picks | 169 | 35% | - | 76% | - | 1.16x | +5.4% | +4.9% | +12.8% |

- **Gate B with the name rule** (dev >= 3 & bundle >= 2 txs & name <= 12):
  - Race rate by time tercile: 43% / 44% / 41%. X1 at our landing: +1.9% / +1.8% / +2.7%. All periods: n=105, +2.1%, +1.1% without the top 3.
  - Without the name rule: n=184, +1.4%, terciles +1.5% / +1.1% / +1.6%.
  - Exit X2 (TP +30% / 10 s) is not stable across terciles (+6.9 / +0.9 / +3.0 with the name rule; +4.4 / -3.0 / -2.7 without).
- **A PnL-first search does not hold OOS.** It ranked ~3k rules by train PnL (report §5). The best train rules (+1.4% to +2.4%) all fall to <= 0 out of sample once the top 3 are removed. So treat Gate B's +1-2% as thin.
- **Firing the moment the stream trigger trips** (no wait, then 25 more txs): E100 >= 2 SOL: -0.3% (test), -0.7% (all). E50 >= 0.5 SOL: +3.5% (test, n=47), +1.4% (all, n=124), about 0 without the top 3. The race is visible only after the price has already moved.
- **GHEc** (the $780 example): dev BuyV2 unlimited, 6.60 SOL; no creator bundle.
  - 4yFAz is at +1 with 6.63 SOL. Whales follow at +30..+34 (20-23 ms) with 11.9, 3.5 and 2.0 SOL. 13 outside buyers and 22 SOL in 2 s.
  - The fixed filter takes it. Gate B rejects it (no bundle). The stream gate sees it at ~1-20 ms, but by our landing (~100 txs) the price is 2.85x floor.

## Engine patch (built, `cargo build --release --bin snipe_engine` → BUILD_EXIT=0)
- **Backups.** Before the patch: `/root/snipe_engine.rs.bak_race`, `/root/snipe.rs.bak_race`, and the old binary `/root/snipe_engine.bin.bak_race`. After each step: `/root/race/snipe_engine.rs.race_v1..v5`, `/root/race/snipe.rs.race_v2`.
- **Patch scripts** (re-runnable on clean sources, in order): `patch_race.py`, `patch_race2.py` .. `patch_race6.py`. Inserted code: `snipe_race_add.rs`, `engine_race_block.rs`.
- `src/snipe.rs`: additive only.
  - `dev_buy_cap_lamports`: cap-family dev SOL priced on the fresh curve. For GHEc, T=193593934369826 gives 6.604 SOL.
  - `dev_buy_kind`: 0 none, 1 sized, 2 cap, 3 unlimited cap.
  - `create_info` / `create_strings`, `mint_touch`, `curve_cost`.
- `src/bin/snipe_engine.rs`: new `RaceCfg` / `RaceWatch`, wired into the `--paper-trade` loop and the `--snipe-once --concurrent` live loop.
  - With no new flag both loops behave as before: the launch is queued and fired in the same iteration.
  - **The live loop was restructured but never run.** The owner should review it before any live use.
- **New flags (all default OFF):**
  - `--dev-from-cap`: effective dev = max(sized, cap-family estimate). Applies to the dev filters and to the floor price.
  - `--race-gate`: fire only on gate passes. Implies `--race-log`.
  - `--race-log`: per launch, logs `RACE seen` (create features: dev, dev_sized, dev_cap, kind, host, cu_price, cu_limit, nsig, nkeys, luts, v1, t22, tip, tip_to, creator, name). Also logs `RACE decide` (gate decision at the window) and `RACE obs` (outsiders seen at 25/50/100/200 ms, SOL, first_ms, bundle_n, and every outside tx as ms:SOL:buy:payer).
  - `--race-min-dev-sol F` / `--race-max-dev-sol F`.
  - `--race-window-ms W`, `--race-min-out N`, `--race-min-out-sol F`: stream gate. Hold W ms and count outside payers and outside buy SOL on the mint in the shred stream. Txs are de-duplicated across the two feeds; cap-family buys are priced on the curve.
  - `--race-bundle any|yes|no`, `--race-min-bundle N`, `--race-bundle-ms B` (default 3): creator bundle = buys within B ms from wallets that are not in the pros list, plus buys signed by the creator side.
  - `--race-max-name-len L`.
  - `--race-pros FILE`: known sniper wallets, never counted as bundle (`/root/race/pros.json`).
  - `--race-obs-ms O`: observe/log horizon (default 200).
  - `--race-track-rejects`: PAPER only. Gate rejects are price-tracked as shadow positions (`PAPER shadow-done`, dump `"fired":false`) and are not in the PAPER report. The live loop drops them.
- **Exact gate flag sets:**
  - **Stream race gate** (forward-run gate; picks busy launches): `--dev-from-cap --race-gate --race-window-ms 100 --race-min-out 1 --race-min-out-sol 2.0 --race-pros /root/race/pros.json`
  - **Gate B** (zero wait, ~3 ms; best create-time rule): `--dev-from-cap --race-gate --race-min-dev-sol 3 --race-min-bundle 2 --race-bundle-ms 3 --race-max-name-len 12 --race-pros /root/race/pros.json`
  - **Cap fix only** (same filter, 4yFAz recall 13% → 76%): `--dev-from-cap`
- **Known limits:**
  - The engine's outside-SOL figure is a hint: the exact amount for sized buys, a curve estimate for cap-family buys, 0 for CPI'd snipers (they still count as payers).
  - A sniper using its own program without pump in its static keys is invisible to the feed.
  - Bundle detection is time-based (3 ms) plus the creator's signers. A non-pro outsider inside 3 ms would count as bundle.

## Live test proposal (the owner decides; I did not run anything live)
**What the data says matters:** landing position. Selection alone gives at most +1-2% per trade at our current position.
- Perfect race selection would give +5.5% at d100 and +13% at d25.
- 4yFAz's own picks would give +4.4% at d100 and +12.6% at d25.

Today we land at a median of d=104 when in S, in S only 16 of 42 times, and in S on only 2 of 10 races.

So **a profit test of the race gate is not justified yet.** A small *measurement* test is:
- **Engine and flags:** the current binary with
  `--snipe-once --concurrent --live --dev-from-cap --race-gate --race-min-dev-sol 3 --race-min-bundle 2 --race-bundle-ms 3 --race-max-name-len 12 --race-pros /root/race/pros.json --race-log`
  plus the usual Helius send path, `--max-sol` of about 0.05-0.1, a small `--max-total-sol`, and 1 trade per run as before.
  - This is Gate B: zero wait, ~30 fires/h in history.
  - Without `--dev-from-cap`, cap-family launches never fire.
  - **Fill cap:** Gate B fills sit behind the creator bundle at a median of 1.28-1.38x floor. `--fill-cap 1.12` would revert almost every fire. Use about 1.5, or only `--slip-bps`.
- **Measure per fire:** landed slot and position d after the create (`/root/race/live_land_pos.py` after `onchain.py` on the live log, or `/root/bsplit/measure_land.py`), outsiders ahead of us, the realised fill vs post-bundle price, and the 1-s exit.
- **Decision rule** after ~20 fires:
  - If we land in S >= 80% of the time with median d <= 25 on these launches, history says ~+4% per trade (X1). Then the stream data can be used to size up, and a race-aware exit can be tried.
  - If we still land around d100 or in S+1 (as today), expect about +1-2% before failed-tx costs. Stop: the fix must be on landing (priority fee and leader-aware routing; inshred), not selection.
- **The stream race gate** (`--race-window-ms 100 --race-min-out-sol 2`) is the right tool to *find* races. Do not trade it live at today's landing: it is -0.3% to -2% after the 100 ms wait.

## Files (`/root/race`)
- **Scripts:**
  - `race_collect.py`: S+1..S+5 txs for the nob sample.
  - `race_lib.py`: block/S+1 fetchers, the race labels, the price path.
  - `race_build.py`: builds `race_ds.jsonl` and `pros.json`.
  - `race_an.py`: the historical analysis (report sections 1-6).
  - `gate_variants.py`: terciles, fire-on-trigger, his-precision check.
  - `onchain.py`: on-chain labelling of engine log launches.
  - `label_onchain.py`, `live_land_pos.py`: today's live fires.
  - `fwd_eval.py`: forward scoring. `mk_bsplit_out.py` feeds the existing `/root/bsplit/real_his.py`.
  - `paper_race.sh`: stall-aware paper runner, paper only. `fwd_chain_loop.sh`, `dobuild.sh`.
  - `patch_race*.py` and the `.rs` inserts.
- **Data:**
  - `s1.jsonl` (3,425 launches, S..S+8), `paths_extra.jsonl`, `race_ds.jsonl`, `pros.json`.
  - `live_fires.jsonl` (today's 42 live fires on chain), `ghec_onchain.jsonl`.
  - `paper_fwd.log`, `paths_fwd.jsonl`, `fwd_onchain.jsonl`, `out_fwd_*.jsonl`.
  - `paper_fwd_v1_dupbug.log`: the first 5 min of the forward run, before the feed-duplicate fix. Not used.
- **Outputs:** `an_final.txt`, `gate_variants.txt`, `live_land_pos.txt`, `fwd_eval.txt`, `report.txt` (everything).

## Caveats
- **Race labels** come from landed, successful buys only. Failed snipes and txs that never landed are invisible. S+1..S+5 is capped at 90 txs per launch (29 launches hit the cap; they are races anyway).
- **PnL model:**
  - Constant-product impact, 1 SOL size, fixed exits. Later price points are one tx per slot, so peaks are slightly underestimated.
  - The 1-s exit uses S..S+2 trades, which are complete.
  - Forward 10-s exits use the engine's 250 ms curve polls, shifted by ~1 s (approximate).
- **Multiple testing.** ~3k PnL rules and ~200k race-precision combos were tried. Gate B was chosen on race precision, not PnL. Its PnL edge (+1-2%) is thin, and the forward n is small.
- **4yFAz precision of the stream gate** counts his own buy as a signal (8.2%). Without it, 5.0%.
- **Bot launchpads and non-SOL quotes.** The engine's base filter lets non-SOL-quote launches through (~4% of forward launches show 0-SOL trade events); they are excluded here. This is a separate, small issue in the base filter.

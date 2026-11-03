# SPEED35: what would a 35 ms median landing add to pre-send? (AMS r36 + r37, 10-29 ~16:50 PKT)

## Short answer
- About **+0.45 SOL over 12.8 h of r36+r37 = about +0.85 SOL/day** at 0.696 (90% CI +0.6..+1.2/day).
  With -20% followers: about +0.55/day. Without the top 5 windows: about +0.6/day.
- That is roughly +14% on what the replay gives now (+3.28 SOL over these windows, about +6.1/day).
- Going faster than 35 ms adds nothing more in the model (25 ms and 10 ms give the same as 35 ms).
- A **constant** saving (every try about 43 ms faster, same spread) adds about **0**. The gain comes from cutting the slow tail
  (q90 202 ms), not from the median.

## 1. What we have now (r37 live, MEASURED)
- Pre-send fills already land fast after the dump: dump seen -> our fill seen median **4 ms** (q75 26, q90 43);
  99% same slot as the dump; block-index gap q10/50/90 = 6/22/91. So "35 ms" is already met for the fills we get.
- So 35 ms here means **send -> land of every try**: now median **78 ms** (q10 30, q25 48, q75 136, q90 202);
  41% land in the send slot, 53% next slot. All tries go via helius-ps.
- The engine sends a pre-signed try every **26.5 ms** while armed, so what decides our place after a dump is the try stream,
  not one send.
- Sells: exit decision -> sell landed median **65 ms** (q10 30, q90 186).

## 2. How the replay works
- Every real try keeps its real send time and real chain place; only its delay is changed:
  "prop" = every delay scaled so the median is 50 / 35 / 25 / 10 ms; "shift35" = every delay cut by 43 ms (same spread).
  The first try after each outside sell becomes our landing. Check: factor 1 gives exactly today's numbers.
- Our try after a sell (r37): now same slot 90%, gap q10/50/90 5/23/88. At 35 ms: same slot 89%, gap 4/21/54.
- Fill and exit = YOUNG sim (limit 0.88 x latest price per slot, window trigger+10 slots, whale stop, QUIET stop,
  run TP/SL), size 0.696, 3.52 mSOL per round trip. Failed-try fees left out (same sends in every row).
- Sell "same factor": sell delay scaled the same way (fill+1 slot 48% -> 77%).

## 3. Does it match live? (911 live-armed windows)
| run | live fills | sim fills | live P&L | sim P&L |
|---|---|---|---|---|
| r36 | 129 | 106.8 | +0.612 | +0.782 |
| r37 | 140 | 117.8 | +2.951 | +2.499 |
| both | 269 | 224.6 | +3.563 | +3.280 |
P&L within about 0.3 SOL. Fills under-counted by 17% (sim misses some live fills), so the extra may be a bit low.

## 4. Extra vs now (SOL over r36+r37, 12.8 h; per day at 0.696)
| buy landing | sell landing | extra | /day | -20% followers | fills added | 90% CI | w/o top 5 | peak | off-peak |
|---|---|---|---|---|---|---|---|---|---|
| 50 ms | now | +0.329 | +0.61 | +0.215 | +0.6 | [+0.20, +0.47] | +0.214 | +0.270 | +0.059 |
| 50 ms | 50 ms | +0.275 | +0.51 | +0.213 | +0.6 | [+0.03, +0.51] | +0.140 | +0.275 | +0.001 |
| **35 ms** | now | **+0.455** | **+0.85** | +0.285 | +4.7 | [+0.31, +0.62] | +0.313 | +0.320 | +0.135 |
| 35 ms | 35 ms | +0.550 | +1.02 | +0.400 | +4.7 | [+0.01, +1.29] | +0.078 | +0.580 | -0.030 |
| 25 ms | now | +0.471 | +0.88 | +0.294 | +5.0 | [+0.32, +0.64] | +0.331 | +0.334 | +0.138 |
| 25 ms | 25 ms | +0.524 | +0.98 | +0.387 | +5.0 | [-0.06, +1.26] | +0.029 | +0.564 | -0.040 |
| 10 ms | now | +0.463 | +0.86 | +0.294 | +5.2 | [+0.31, +0.63] | +0.316 | +0.338 | +0.126 |
| 35 ms, constant cut | now | +0.055 | +0.10 | +0.047 | -2.9 | [-0.06, +0.18] | -0.047 | +0.067 | -0.012 |
- Peak = PKT hours with more armed windows than the median hour (4, 5, 6, 8, 9, 11, 15). Most of the gain is peak.
- Fills added are few (+4.7 on 225). The gain is mostly a **better price on fills we already get** (tail landings moved up):
  16.3 vs 14.6 mSOL per fill. So "mSOL per added fill" is not meaningful (about +96 if all put on the added fills).
- Faster sells: small and noisy (CI touches 0, gone without the top 5). Not a reliable add.
- Per run (35 ms both legs): r36 +0.33 SOL, r37 +0.22 SOL.
- The 24 r37 windows that filled in paper but not live (+0.78 paper): faster landing wins back only about 5 fills here,
  so most of those misses are not landing delay.

## What this cannot model
- Rivals reacting to us (if we land earlier, they may change). Order inside a slot is taken as arrival order
  (priority fees / BAM / Jito ordering not modelled). 1 ms = same share of a slot everywhere in the slot (INFERRED).
- How the speed-up happens: if only the median moves and the slow tail stays, gain is about 0 (constant-cut row).
- Only 12.8 h, 2 runs, AMS only.

Files: code /home/moiz/sniper/ops/strategies/presend/speed35/ (s1_measure, s2_build, s3_scen, s4_replay, s5_tables, s_sim = YOUNG
sim + follower cut); data /home/moiz/sniper-data/speed35/ (tables.txt, scen.pkl, replay.pkl, s1_measure.json, tab/ = r37 tape to 16:33 PKT).

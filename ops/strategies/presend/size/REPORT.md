# Pre-send size study: are we losing because of trade size? (agent, 10-27 PKT)

Owner request 10-27 ~22:10 PKT: "check if we might be losing because of trade size; bots might be hitting slippage".
(Written by the main session from the agent's text; the harness blocks subagents from writing report files.)

**Answer: no.** Trade size is not why r26 and r28 did badly. On the same windows, 0.50 made more than 0.35 in all five runs; r26 and r28 were weak at every size. **Recommended size: keep 0.50.**

Nothing was sent and nothing on the engines, servers or configs was changed. On AMS the only access was a `sudo cat` of r28's records after the engine had stopped (md5 matches the server). The only RPC calls were read-only `getTransaction` lookups to decode other wallets' limits. Times are PKT.

**Validation passed.** At each run's live size the replay gives back all 637 pre-send fills and all 83 regular fills to the lamport. All 9,107 decoded failed buys also fail on the live state, as they did on chain.

## 1. Pre-send per run and size (INFERRED except the live cells)
"As run" = realized + rent back − the run's failed-try fees. Failed-try fees are the same at any size; r28's are estimated from its landing records (15,212 × 5,120 lamports). % is per fill as a share of size. Live cells are in bold.

| Run (live size, hours PKT) | Fills | 0.25 | 0.35 | 0.50 | 0.65 |
|---|---|---|---|---|---|
| r24 (0.34, 21:47–02:57) | 200 | +0.783 (1.57%) | +1.221 (1.74%) | +1.708 (1.71%) | +2.013 (1.55%) |
| r25 (0.34, 02:58–06:09) | 95 | +0.722 (3.04%) | +1.079 (3.25%) | +1.551 (3.27%) | +1.955 (3.17%) |
| r27 (0.35, 15:27–17:37) | 49 | +0.426 (3.48%) | **+0.622 (3.63%)** | +0.910 (3.72%) | +1.101 (3.46%) |
| r26 (0.50, 06:58–14:03) | 143 | +0.012 (0.03%) | +0.148 (0.30%) | **+0.250 (0.35%)** | +0.348 (0.37%) |
| r28 (0.50, 18:21–22:03) | 150 | +0.058 (0.15%) | +0.133 (0.25%) | **+0.273 (0.36%)** | +0.353 (0.36%) |

r24 and r25 ran live at 0.34: +1.168 and +1.042 (MEASURED).

| Run | Wins/losses (0.25 / 0.35 / 0.50 / 0.65) | Follower buys our size changes (vs live) | Flat fills (0.25 / 0.35 / 0.50 / 0.65) |
|---|---|---|---|
| r24 | 93/107, 103/97, 104/96, 103/97 | at 0.50: 14 priced out (13.1 SOL); at 0.65: 37 (23.3 SOL) | 26 / 26 / 26 / 28 |
| r25 | 56/39, 60/35, 60/35, 60/35 | at 0.50: 10 (4.0 SOL); at 0.65: 19 | 6 at every size |
| r27 | 25/24, 26/23, 26/23, 26/23 | at 0.50: 4 (2.4 SOL); at 0.65: 9 | 6 at every size |
| r26 | 57/86, 59/84, 59/84, 59/84 | at 0.35: 13 failed buys would pass (6.5 SOL) | 24 / 26 / 28 / 29 |
| r28 | 62/88, 65/85, 66/84, 66/84 | at 0.35: 4 would pass (2.5 SOL) | 20 / 20 / 20 / 21 |

- **What was added to the r065 replay:** going down in size, other wallets' buys that failed with a slippage error are re-tried with their decoded limits. With that switched off, the replay gives back r065's own numbers exactly.
- **No new fills at a smaller size.** None of our 62,069 failed tries in r24–r28 would have filled at 0.25 or 0.35, because our limit is a price limit.

**Same windows, only the size changes (0.50 − 0.35).** Ranges are 5–95% bootstrap over fills. The stress column drops 20% of later buyers, over 200 draws.

| | 0.50 − 0.35 | With 20% fewer buyers |
|---|---|---|
| r24 | +0.487 [+0.157, +0.823] | +0.140 |
| r25 | +0.472 [+0.260, +0.685] | +0.238 |
| r27 | +0.288 [+0.111, +0.500] | +0.197 |
| r26 | +0.101 [−0.177, +0.399] | **−0.066** [−0.138, +0.017] |
| r28 | +0.140 [−0.117, +0.404] | **−0.118** [−0.198, −0.036] |
| **All 5** | **+1.488 [+0.904, +2.075]** | **+0.391 [+0.205, +0.569]** |

- **0.65 vs 0.50:** +1.08 pooled in the base case, but about −0.03 with 20% fewer buyers.
- **Sensitivity:** the sign of 0.50 − 0.35 holds whether every decoded limit is held fixed or failed buys are never revived.
- **Regular buys follow the same pattern:** r24 goes +0.368 / +0.548 / +0.778 / +1.011 at 0.25 / 0.35 / 0.50 / 0.65. The only exception is r28's regular buys (15 trades), where 0.35 beats 0.50 by +0.015, which is noise.

## 2. Follower buys that failed with a slippage error during our holds (MEASURED; "would pass" columns INFERRED)
"Not dup" excludes wallets that also bought successfully in the same hold. "Miss" is how far a buy missed its own limit on the live chain state.

| Run (size) | Failed buys (per fill) | Not dup, in how many holds | Median miss | Would pass at 0.35 | Would pass at 0.25 |
|---|---|---|---|---|---|
| r24 (0.34) | 710 (3.6) | 611, 101 of 200 | 15.7% | — | 8 (4.4 SOL) |
| r25 (0.34) | 419 (4.4) | 376, 59 of 95 | 15.7% | — | 3 |
| r27 (0.35) | 169 (3.4) | 134, 23 of 49 | 11.2% | — | 3 |
| **r26 (0.50)** | 623 (4.4) | 540, 67 of 143 | 19.2% | **16 (8.2 SOL)** | 25 |
| **r28 (0.50)** | 989 (6.6) | 874, 77 of 150 | 38.6% | **4 (2.5 SOL)** | 13 |

- **Why so few would pass:** most failed buys missed by 10–40%, while 0.15 SOL more of our buy moves the price only about 0.3–0.5%. They look like rival pre-senders' price-limit tries, not followers we priced out.
- **Flat holds:** r26 had 114 such failed buys and only 3 would pass at 0.35. r28 had 53 and none would pass. So the flat study's "21 of 80" was almost all buys that fail at any size.
- **Compared like for like:** r26 and r28 at 0.35 would rescue 16 and 4 buys, and r24, r25 and r27 at 0.50 would lose 14, 10 and 4. Either way it is a few per run.

## 3. Time of day
- **Live data cannot separate the two.** The hours barely overlap across sizes, and where they do it is another day or another region (MEASURED):
  - 18h: FRA at 0.40 made +3.5% per fill; AMS r28 at 0.50 made +3.3%.
  - 22h: r24 at 0.34 made −0.5%; r28 at 0.50 made −1.8%, but on only 3 fills.
  - r26 by hour went from +5.9% (11h) down to −3.1% (13h) and −17.5% (14h, 3 fills).
- **The replay can.** On the same windows, 0.50 − 0.35 is positive in 19 of 24 hours. It is negative only in 12–14h, 20h and 22h, which are the hours where those windows lost at any size.

## 4. Plain answer
- **Not losing because of size.** Replayed at 0.35, r26 and r28 still make only 0.30% and 0.25% per fill, the same "tenth". Replayed at 0.50, the 0.34/0.35 runs keep 1.7–3.7%. The windows (hour, market) set the per-fill result, not the size.
- **Cost of 0.50 vs 0.35:** it prices out a few followers, about 0.04–0.10 SOL per run, which is less than what the bigger position earns. It adds 2 flat fills in r26 and none in r28, so the 17.9% vs 11.0% flat gap comes from the windows, not size.
- **The real risk of size:** when the edge is thin, as in r26 and r28, a bigger buy also loses more if followers thin out: −0.07 and −0.12 SOL vs 0.35 with 20% fewer buyers.
- **Size:** stay at 0.50.
  - Don't go to 0.65: its stress gain over 0.50 is about 0 and its tails are bigger.
  - If you expect another thin-edge period, 0.40 is the cautious middle; in the base case it gives up about 0.05–0.10 SOL per run against 0.50.
  - The lever is window quality (hours, filters), not size.

## Limits
- **Bots reacting to size:** bots that would skip our bigger buy are not modelled; the 20% stress stands in for them.
- **Revived buyers' sells:** later sells by the revived buyers are not invented. Turning revival off makes 0.50 look even better.
- **Coverage:** AMS only. FRA r23 and r24 appear only in the live hour table.

## Files
- Code (`/home/moiz/sniper/ops/strategies/presend/size/`): s1_live.py, s2_extract.py, s3_tape.py, s4_sigs.py, s4b_sigs2425.py, sizelib.py, s5_run.py, s6_fails.py, s7_hours.py, s8_tables.py, s9_sens.py.
- Data (`/home/moiz/sniper-data/presend_size/`): live/ (r28 copy), tape.pkl, args_hold.jsonl, args_2425.jsonl, results.json (per trade, every size), fails.json, hours.json, sens.json, summary.json.

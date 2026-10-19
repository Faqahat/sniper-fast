# racedeep: can we make money AROUND pump.fun race launches? (PAPER / READ-ONLY: nothing sent, no --live)

> **STATUS 2026-10-19 04:20 UTC: done. Verdict: NO profitable "follow the race" sniper at our real landing.**
> - Every race signal we can see arrives after the price has already moved, and what the price does next is worth less than our costs.
>   - This holds at every landing tested: +25 txs after the signal, +100 txs, the very front of S+1, and the middle of S+1.
> - ~29.6k (rule, exit) combos were tried. 2 passed training. Both lost on the blind night run: -12% per trade.
> - The only positive region is **whale-follow (one outside buy >= 5 SOL in slot S), sell +3 s**:
>   - At our landing it is +2.9% to +3.8% per trade, but the 90% CI spans 0, ex-top3 is -4%, and n=30. That is not a strategy.
>   - If we could land <= 25 txs after the whale (~12 ms reaction) it is +13.6%, ex-top3 +4.9%, about +25 SOL/day at 2 SOL. We cannot react that fast today.
> - **The money in races is only for whoever is already in front, <= 5-25 txs after the create.** The lever is landing, not triggers.

## Data, model, split
- **Data:**
  - **hist:** the race_ds random sample (base filter, 792 launches), joined to the nob block records (every tx in S with payer, cu, tips, failed txs) and to s1 (S+1..S+5).
  - **fwd:** forward run 1 (972 launches).
  - **night:** the overnight census, 3,186 scored launches from a snapshot taken at 04:12 UTC while the run was still going (7.93 h of slots, 9,645 base launches/day). The 21 night launches that overlap fwd run 1 were dropped. `./run_all.sh` re-snapshots and refreshes every output once the race agent has labelled the last ~100 launches.
  - **Same universe as the race agent:** dev 0.5-8, host ok, SOL quote.
  - **RACE label unchanged:** >= 3 outsiders AND >= 3 SOL outside in S..S+5 (excluding 4yFAz).
- **Fit / test:** fit = hist + fwd; test = night, which no rule saw. Night is also split in halves A/B (time split).
- **Sim** (`rdlib.py`; same cost model as `hc_search.sim`):
  - 2 SOL (and 1 SOL), fill x1.03, own impact on both legs, pump fee 1.25% per side, 0.009 SOL buy priority, 0.001 SOL per sell.
  - Entry is behind every trade up to the landing point.
- **Two timing fixes vs the race agent's sim. They make my numbers stricter.**
  1. **"Land +D txs" respects the slot end.** If fewer than D non-vote txs remain in S after the trigger, we land in S+1. The create sits mid-slot: a median 116 ms of slot is left.
  2. **S+k trades are timed from the real slot boundary** (end of S = (rem+1) x ms_per_tx), not from 217 ms after the create.
  - Cross-check on the same night launches (`xcheck.py`): at d5/d25 the two sims agree (race +14.0 vs +14.2%, +12.6 vs +12.0%). At d100 hindsight races are +5.5% (race agent) vs **+2.5% (here)**. The gap is fix 1: launches created late in the slot.
- **Landing scenarios** (measured live, `live_land_pos.txt`):
  - we land in S on 16/42 fires (38%), median d 104, never at d <= 25;
  - **on races, in S only 2/10.**
  - "Blend" = 0.4 x (S, +100 txs) + 0.6 x (S+1, behind half of its trades). For races and triggers this is generous.

## 1. Timeline profile: race (n=1,122) vs non-race (n=3,795), all sets (`profile.txt`)

| checkpoint | med time | race: outsiders / outside SOL / price | non-race: outsiders / outside SOL / price |
|---|---|---|---|
| create | 0 | 0 / 0 / 1.00x | 0 / 0 / 1.00x |
| S d<=5 (creator bundle) | ~1 ms | mean 0.16 / 0.28 / **1.21x** | 0.05 / 0.06 / 1.00x |
| S d<=25 | ~1-12 ms | 0.32 / 0.59 / 1.23x | 0.10 / 0.09 / 1.00x |
| S d<=50 | ~25 ms | 0.67 / 1.12 / 1.26x | 0.21 / 0.16 / 1.02x |
| S d<=100 (our landing) | ~50 ms | med 1 / 0.59 / **1.31x** | 0 / 0 / 1.06x |
| end S | 77 ms | med 2 / 2.17 / 1.37x | 0 / 0 / 1.06x |
| end S+1 | 196 ms | 4 / 3.51 / 1.45x | 1 / 0.19 / 1.08x |
| end S+2 | 348 ms | 5 / 4.01 / **1.45x (plateau)** | 1 / 0.25 / 1.08x |

- **Order of arrival:**
  - 1st outsider in S: races have one 73% of the time (median d 47), non-races 44% (d 69).
  - 3rd outsider: 43% (d 106) vs 10%.
  - 5th outsider: 20% (d 151) vs 3%.
- **Priority / senders:**
  - By end of S, races have a median max outsider cu of 3.3M µlamports/CU, a mean of 105M, and tips p50 0.002 SOL. Non-races: ~0.
  - Failed txs in S: race median 2 (mean 5.1), non-race 0 (mean 1.8).
- **Who arrives** (wallets in S on >= 15 launches, race rate vs a 22.8% base):
  - dKMjeGJ4: 83%, median d 45, 4.94 SOL, tip 0.06.
  - BXB7FF4m 84%, Anubis51 79%, G9sQPg9E 79% (cu 100M), 9qz7cWBq 63% (1.78 SOL), 8RvtT818 63% (cu 145M).
  - 4zc4w4zV / Gno1iQZK / CUQqcZZG: 100% / 100% / 84%, 2.96 SOL, big tips.
  - The broad bots dilute the signal: HVE8996r 31%, AmN88ff2 25%, H6obhoSN 12%.
  - 4yFAz: 42%.
- **Dev / insider behaviour:** the creator sells by S+2 in only 3% of races (2% of non-races).
  - Early flippers do sell: some sell happens by S+2 in 46% of races (mean 1.16 SOL) vs 10%.
  - Bundle wallets did not dump inside 2 s.
- **Earliest high-precision separator, and what it costs.** Precision = race rate among launches passing the threshold.

| when | rule | precision | recall | price already |
|---|---|---|---|---|
| d<=5 | outsider buy >= 0.69 SOL | 42% | 11% | 1.11x |
| **d<=25** | outside SOL >= 1.9 | **83%** | 11% | **1.29x** |
| d<=50 | outside SOL >= 3.2 | 94% | 14% | 1.49x |
| d<=100 | outside SOL >= 2.8 | 91% | 30% | 1.44x |
| end S | outside SOL >= 3.2 | 95% | 38% | 1.49x |
| end S+1 | outside SOL >= 3.1 | 95% | 59% | 1.48x |

- **Conclusion:** a race is recognisable at ~25-50 txs. By then 60-100% of its 2-s move (1.45x plateau) is in the price.

## 2. "If we landed after similar things": trigger x landing x exit (`search.py`, `agg.py`, `final.py`)
- **Grid:**
  - 4 create-time pre-filters (all, Gate B, dev >= 2, dev <= 3);
  - 58 stream triggers: k-th outsider buy >= X; cumulative outside SOL >= Y; >= N outsiders; N & Y; whale >= Y (with or without high priority); high-priority outsider; 4yFAz buys; pro wallet buys; failed txs >= F; first-wave-then-dip;
  - 3 windows (S, S..S+1, S..S+2) and 4 price caps at the trigger (1.3 / 1.6 / 2.0 / none) → **2,596 rules**;
  - 11 exits: 0.5-10 s, 50%/70% at 1 s + trail 0.8, TP ladder, trail, TP 1.3;
  - 7 landings: +25 / +50 / +100 txs, S+1 front / q25 / mid / end.
- **Selection:** on train (worst of hist/fwd > 0, pooled ex-top3 > 0, n >= 15 each).
  - Blend landing: 2 of 28,556 pass. On night they are **-12.1%** (n=49, median -19%).
  - Same 2 if selected at S+100; on night -12.7%.
  - Selected at S+1 front: 1 passes; on night -5.6%.
  - **Share of train-positive rules positive on night: 0%.**
- **Decay ("how fast must we be"). Night, mean PnL, sell +1 s, vs landing delay AFTER the signal:**

| signal (night n) | +1 | +5 | +25 | +100 | S+1 front | S+1 mid |
|---|---|---|---|---|---|---|
| create, base filter (3186) | +10.2% | +0.2% | -0.6% | -3.7% | -4.9% | -5.8% |
| create, Gate B (362) | +18.3% | +0.4% | -0.5% | **-4.0%** | -5.2% | -6.0% |
| create, HINDSIGHT race (726) | +30.5% | +13.9% | +11.7% | **+2.5%** | -0.3% | -2.6% |
| 1st outside buy >= 1 SOL (696) | -2.6% | -3.7% | -5.2% | -7.9% | -8.0% | -8.4% |
| cum outside SOL >= 2 (489) | -2.8% | -3.8% | -5.3% | -7.5% | -7.2% | -7.4% |
| >= 3 outsiders & >= 3 SOL (234) | -6.5% | -7.1% | -8.1% | -8.5% | -8.2% | -8.2% |
| whale 3-10 SOL (89) | -1.8% | -3.2% | -6.0% | -10.2% | -10.4% | -10.3% |
| 4yFAz buys (32) | +0.6% | -1.1% | -3.6% | -5.5% | -4.7% | -7.2% |
| **whale >= 5 SOL (30), sell +3 s** | +19.8% | +19.3% | **+13.6%** | **+3.8%** | +3.2% | +2.3% |

- **Train shows the same shape.** Hindsight race +5.5% at +100; Gate B -0.2% at +100 and +3.7% at +25.
- **Post-trigger drift is negative even 1 tx after the trigger.** The race signal is the move itself, so following it buys the top of the first wave. +1 = in the creator's bundle seat, which is not reachable.

## 3. The race tail (runners vs dumps) (`whale.txt` §3)
- **Runners are rare.** Runner = max price in (end S+1, 30 s] >= 2x the end-S+1 price: only **9% of races** (104/1,122).
- **Weak separators:**
  - dev >= 5 SOL: 17% runners vs 8%; dev >= 3: 13% vs 7%.
  - Sells by S+1: 5% vs 10%.
  - >= 12 outsiders by S+1: 0%.
  - More SOL or more buyers by S+1 is slightly *worse*.
- **"Enter after the first wave" (land S+2 mid on races-so-far):** negative in every period.
  - Examples: ">= 3 out & >= 3 SOL by S+1": hist -4.5%, fwd -5.7%, night A -6.4%, night B -7.6% (sell +1 s). Trail exits: -1% to -12%.
- **First-wave-then-dip (<= 0.65-0.8x peak) entries:** rare (n=6-8) and -7% to -9%.

## 4. Whale-follow (`whale.txt`, `whale2.txt`)
- **Post-whale drift** (whale 3-10 SOL in S, no costs): median +5.0% at +50 ms, +6.4% at +100 ms, +3.7% at +1 s, +0.3% at +5 s.
  - We land ~+50 ms after it and pay ~6% in costs, so the drift is gone.
- **Whale [2,3) / [3,5) / [4,10):** negative everywhere (-3% to -14%).
  - The [3,5) bucket is mostly dKMjeGJ4 (its fixed 4.94 SOL buys): -10% to -14% on night.
- **Whale >= 5 SOL (single outside buy in S), sell +3 s:**
  - train n=14: +13.0% @S+100 (median -2%, ex3 -9%);
  - night n=30: +3.8% @S+100 (CI -5.2..+13.1), +2.3% @S+1 mid, blend +2.9% (CI -6.3..+12.5), ex3 -4.0%;
  - by period at S+100: hist +41.9% (n=6), fwd -8.7% (n=8), night A +1.9%, night B +9.0%.
  - **Fragile:** the >= 4 and >= 4.5 SOL thresholds are -6% to -8% on night. 29 of 30 night events are races anyway.

## 5. Race-aware exit on a zero-wait entry (`final.txt` §2)
- **Rule:** hold to 2-10 s / trail if >= Y SOL of outside buys is seen by t0+W, else sell at 0.5 s. 288 variants.
- **Result:** best train -0.9% (Gate B, W 600, Y 2, hold 2 s) → night -3.4%, vs plain Gate B 0.5 s at -2.8%. No gain.

## Strategy table (NIGHT = test; fires/day from the night rate)

| strategy | landing | n | mean | median | ex-top3 | win | fires/day | SOL/day @2 | SOL/day @1 |
|---|---|---|---|---|---|---|---|---|---|
| Gate B zero-wait, sell 1 s | S+100 | 362 | -4.0% | -5.4% | -4.7% | 20% | 1,096 | **-87** | -49 |
| Gate B zero-wait, sell 0.5 s | S+100 | 362 | -2.8% | -5.2% | -3.2% | 19% | 1,096 | -63 | -36 |
| Gate B zero-wait, sell 0.5 s | S+25 (fast lane) | 362 | +0.6% | -3.5% | +0.1% | 32% | 1,096 | +12 | +2 |
| base filter, sell 1 s | S+100 | 3186 | -3.7% | -5.6% | -3.8% | 19% | 9,645 | -709 | -403 |
| **whale >= 5 SOL in S, sell 3 s** | blend 40/60 | 30 | +2.9% | +0.8% | -4.0% | 50% | 91 | **+5.3** (ex3 -7.3) | +2.5 |
| same | S+100 | 30 | +3.8% | +2.2% | -2.6% | 57% | 91 | +6.9 | +3.3 |
| same | S+25 (needs ~12 ms reaction) | 30 | +13.6% | +8.9% | +4.9% | 60% | 91 | +24.8 | +12.6 |
| >= 3 out & >= 3 SOL, sell 1 s | blend | 234 | -8.3% | -6.8% | -9.1% | 15% | 708 | -118 | -64 |
| cum outside SOL >= 2, sell 1 s | blend | 489 | -7.5% | -6.6% | -7.9% | 16% | 1,480 | -221 | -120 |
| 4yFAz buys, sell 1 s | blend | 32 | -6.5% | -6.1% | -9.7% | 16% | 97 | -13 | -7 |
| HINDSIGHT race (not tradable) | S+100 / blend | 726 | +2.5% / -0.6% | +0.6% / -2.6% | +2.0% / -1.0% | 52% / 43% | 2,198 | +109 / -25 | +50 / -20 |

- **Gate B on the blind night is negative in my sim:** -4.0% at d100 here (-2.4% in the race agent's sim).
- Gate B was +1.6% on forward run 1, so the night regime is weaker.

## Verdict / what to do
1. **Do not build a race-follow sniper.**
   - Of 29.6k combos, none is positive out of sample at realistic landing.
   - Even perfect hindsight race selection is only +2.5% at S+100 and negative in S+1. Since we land in S on only 2 of 10 races, it is about 0 in practice.
2. **Whale >= 5 SOL follow is the only positive cell.** It is too small and fragile to trade: n=30, CI spans 0, ex-top3 < 0, and it depends on the threshold.
   - If anything, run it as a PAPER forward test (no code change: it needs a whale trigger in the engine's stream).
   - At best it adds ~+5 SOL/day at 2 SOL, not 10-20.
3. **The 10-20 SOL/day target needs the fast lane.**
   - At <= 25 txs after a signal, whale >= 5 follow gives about +25 SOL/day on paper. Hindsight races are +11.7% at +25.
   - The lever is landing (Jito-on-BAM, LandX, spray; `/root/race/NOTES.md` landing levers 1-3), not selection or triggers.

## Rules tried (multiple testing)
- 2,596 trigger rules x 11 exits = 28,556 (rule, exit) combos, each scored on 7 landing scenarios and selected under 3 landing assumptions.
- Plus 288 race-aware exits, 735 whale cells, 25 second-wave cells and 6 whale thresholds: **≈ 29.6k combos in total.**

## Files (`/root/racedeep`)
- **Scripts:**
  - `build.py` → `U.pkl`: unified per-launch timeline: every S tx (payer, SOL, cu, tip, failed), S+1..S+5, price path.
  - `rdlib.py`: sim, landing model, stats.
  - `profile.py` → `profile.txt`: item 1.
  - `search.py` → `res.pkl`: trigger grid sims.
  - `agg.py <PS|landing>` → `agg_p40.txt`, `agg_s1front.txt`, `agg_s100.txt`: selection, blind test, PnL maps.
  - `whale.py` / `whale2.py` → `whale.txt` / `whale2.txt`: items 3 and 4, every whale event, CIs.
  - `final.py` → `final.txt`: decay, race-aware exits, strategy table.
  - `xcheck.py`: sim cross-check.
  - `run_all.sh`: the whole pipeline. It re-snapshots the night files into `snap/`.
- **Caveats:**
  - S+1..S+5 txs are capped at 90 per launch.
  - Order inside S+k slots is the RPC signature order.
  - Failed txs are known only for S.
  - Later prices come from the engine's 250 ms polls.
  - The landing model is position-based, not a latency simulation.

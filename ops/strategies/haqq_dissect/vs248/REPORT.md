# Analyst J (vs248): bot 248, the bot closest to ours, vs our engine; an exact bridge (10-28 ~03:35 PKT)
Saved by the main session from the agent's reply. Code: this folder (v1–v9). Data: /home/moiz/sniper-data/haqq_dissect/vs248/ (examples.json, v4_tables, v5, v6_bridge, v7_rungaps, v9_refused .txt). The bridge leaves exactly 0.000000 on every day.

## Short answer (D2–D5 = 10-24..10-27; M = measured, I = inferred)
- **On shared dumps WE beat 248:** 263 events, ours +24.9 mSOL vs 248's +4.0, gap +20.9 [+11.3..+30.5], every day. We land first 81%; 248 pays a median 5.2% more.
- **248's money is on dumps we never buy:** +13.63 SOL/day in total.

  | Bucket | SOL/day |
  |---|---|
  | Gate refused | +6.30 |
  | Our run gaps | +2.55 |
  | Guard failed | +1.36 |
  | No ≥5% dump before the buy | +1.33 |
  | Shared dumps | +0.29 |

- **248's costs are 0.543 mSOL/lot;** ours are 2.537 pre-send and 4.380 regular. 248 runs ~1,960 lots/day against our ~420 fills; it has no limit at 0.25–0.40.
- **Fragile:** with 10% fewer followers, 248's own entry, exit and costs on gate-refused dumps go to −2.29/day.
- **Corrections to the brief:**
  - 248's size was 0.25 on D0, 0.30 on D1–D3 and 0.40 on D4–D6;
  - 248 has only 0.14 open lots on average (the 5.4 figure is all of haqq).

## Selection (M)
- **248's lots by bucket:**

  | Bucket | Lots | SOL/day | mSOL/lot |
  |---|---|---|---|
  | Gate refused | 2,871 | +6.30 [4.22..8.40] | +8.8 |
  | Run gaps | 1,131 | +2.55 | +9.0 |
  | Guard failed | 516 | +1.36 | +10.5 |
  | No dump before | 1,693 | +1.33 | +3.1 |
  | Other refusals | | +0.60 | |
  | Far leader | | +0.39 | |
  | Cooldown | | +0.37 | |
  | Thresholds | | +0.35 | |
  | One-position | | −0.10 | |
  | Same dump as ours | 251 | +0.29 | |

- **Our fills, by whether 248 bought the same dump:**

  | Path | 248 also bought | 248 skipped |
  |---|---|---|
  | Pre-send | **+30.9 mSOL** (155 fills) | +0.9 (914 fills) |
  | Regular | +14.4 (78 fills) | −1.1 (397 fills) |

- **Dev-chunk pattern** (dev sell < 5% of supply, price 4–30% below its 10-slot high): 248 makes +11.6 mSOL/lot, +2.00 SOL/day; our 39 fills there make −7.9.
- **Whale dumps (≥6% holder):** 248 +16.5 mSOL/lot, +3.09/day; our pre-send 670 fills make +7.9.

## Timing (M)

| | Dump → buy | Same slot | Trades ahead | Price vs post-dump |
|---|---|---|---|---|
| Bot 248 | 66 ms | 58% | 2 | 1.036 |
| Our pre-send | 29 ms | 90% | 0 | 1.000 |
| Our regular | 50 ms | 65% | 1 | 1.012 |

## Limit and fill (M)
- We failed 64% of the 809 dumps we both went for; 248 made +1.36/day on them.
- By 248's price vs post-dump: ≤ 1.05 +25.6 mSOL; 1.05–1.10 +18.9; > 1.10 +4.1.
- At 248's entry with our exit and costs, those lots are worth −0.03/day.

## Other differences
- **Size:** 0.30 for all our fills would be −0.36/day. Don't copy.
- **Exit:**
  - our tokens at 248's sell time: pre-send +9.6 mSOL/pair, regular −16.5;
  - a 4.2 s hold on all our fills loses −1.4/day per path.
  - The wave exit is the right version (+1.0..1.6 pre-send).
- **Costs:** see above.
- **Concurrency:** not a lever (−0.10/day).

## Bridge (SOL/day, mean D2–D5, exact)

| Step | SOL/day |
|---|---|
| **Our wallet** | **+1.210** |
| Our non-shared fills, failed fees, leftovers | +0.350 |
| **= our fills on shared dumps** | **+1.560** |
| Size | −0.020 |
| Exit | +0.106 |
| Entry (248 is later and pays more) | **−1.479** |
| Costs | +0.125 |
| **= 248 on shared dumps** | **+0.292** |
| Guard failed | +1.358 |
| **Gate refused** | **+6.296** |
| Other refusals | +1.628 |
| No dump before | +1.330 |
| Run gaps | +2.550 |
| Unusable tape hours | +0.186 |
| Other trigger near our fill | −0.009 |
| **= 248** | **+13.631** |

## Changes (I)
1. **S2 tx recipe:** +0.90/day (owner OK).
2. **Wave exit:** pre-send +1.0..1.6/day, regular ~+0.4.
3. **24/7:** +0.20/day at today's +0.059 SOL/engine-hour.
4. **Selection:** not validated. On gate-refused dumps at 248's own entry:

   | Exit and costs | SOL/day |
   |---|---|
   | 248's exit + 248's costs | +5.67 |
   | 248's exit + S2 costs | +4.72 |
   | 248's exit + our costs | +2.92 |
   | Our exits | +0.1..+0.66 |
   | 10% fewer followers | −1.6..−5.0 |

**Realistic total from 1–3: +2.1..+2.7 SOL/day on top of ~+1.2 today.**

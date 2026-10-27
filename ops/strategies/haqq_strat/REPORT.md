# haqq's strategy and DV8 (agent, 10-28 ~01:00 PKT)

Saved by the main session from the agent's reply (the harness blocked the agent's report write). Window: 10-26 23:15 → 10-27 23:15 PKT. Tables are in /home/moiz/sniper-data/haqq_strat/s*.txt.

## haqq (MEASURED)
- +28.1 SOL/24 h net, from ~5,700 lots of ~0.4 SOL each.
- Edge +1.5%/SOL per lot; win rate 41–46%; his tx costs only 0.78 mSOL per lot.

| Type | Lots/day | Net SOL/day |
|---|---|---|
| DIP (within 2 slots of a ≥5% sell) | 2,158 | +15.5 |
| ADD | 1,684 | +6.4 |
| DIP_LATE | 402 | +2.3 |
| DEAD (curve ≤ 30.5 SOL, ~20-min holds) | 472 | +2.2 |
| LAUNCH | 152 | +1.6 |

- **Exits:** seconds, a soft TP/SL on a timer. His holds over 5 min lose −12.5 SOL.
- **His tx recipe:** fee 0.000125, Helius tip 0.0002 + a no-tip copy, durable nonce, own router, CU ~66k.
- **Concurrency:** he holds 5.4 open lots on average.

## Speed (MEASURED)
- His dip buys land a median 80 ms after the dump. Ours: regular 41–49 ms, pre-send fills 29 ms.
- On shared dumps we land first 80–96% of the time.

## Gap: his +28.1 vs our +3.2 SOL/day
1. **Volume:** our M2 gate refused dumps carrying +12.5 of his SOL, and gaps between runs cost +4.5.
2. **Selection:** copying his picks causally gives ≈ 0 or negative at our landing (crowded dumps).
3. **Costs:** we pay 3.39 vs his 0.78 mSOL per fill. Failed pre-send attempts cost ~1.4 SOL/day on AMS.
4. **Concurrency:** he holds 5.4 open, we hold 1.

## DV8 strategy (INFERRED replay on the held-out day)
- **Entry:** any outside sell with a drop ≥ 5% and ≥ 0.5 SOL, curve > 30.5, token ≤ 30 min old.
- **Gate:** a retrained P&L model, at about 8,000 picks/day.
- **Rest:** +5% guard, 8-slot exit, 0.40 SOL flat, up to 3 open, far leaders included, his fee recipe.

| Row | SOL/day |
|---|---|
| Our landing | +31.8 [+16.6..+47.9] |
| Calibrated | **+18.9** |
| Conservative calibration | +2.5 |
| 10% fewer followers | −22.1 |

Very sensitive to follower volume, so paper first.

## Plan
1. 24 h shadow/paper DV8.
2. His cheap tx recipe (send path: owner OK).
3. 3 positions and far leaders, only after paper passes.

Also cheap: cut failed pre-send attempts (owner OK).

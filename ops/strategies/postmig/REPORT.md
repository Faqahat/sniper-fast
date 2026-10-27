# Just-migrated pump.fun tokens on PumpSwap: is there an opportunity for us? (10-24 ~23:45 PKT)

Read-only replay study by agent; Haiku not used ($0). MEASURED = counted from recorded chain data; INFERRED = reading.
Scripts: ops/strategies/postmig/pm1_extract.py … pm12_dumpdone.py, replay engine pmsim.py.
Outputs (9.3 GB): /home/moiz/sniper-data/strategies/postmig/.

## Short answer
1. **About 900 graduations a day, but only about 210 are organic.** About 420 a day come from scripted rug farms and about
   270 a day are mayhem pools with almost no SOL in them. (MEASURED)
2. **Nearly every graduate collapses within an hour.** Median price one hour after migration is 4–11% of the opening price.
   (MEASURED)
3. **About 100 outside wallets make steady money, roughly +300 SOL a day together.** The biggest group runs a dip-backrun
   on PumpSwap: they land 1–27 transactions after the big sell and pay about 0.00002 SOL per trade. That is far faster
   (we land ~65 tx behind) and ~170× cheaper than us. (MEASURED)
4. **4,413 rule variants tested.** None stays positive on both later days once the best 3 trades are removed. (MEASURED)

## What happens after migration (MEASURED)
**Fees:** PumpSwap fees right after migration are about 1.25% per side (1.03–1.19% average in the first hour). They are
NOT cheaper than the bonding curve.

**1. Instant "brand farm" graduations (~420/day: IShowSpeed, SpaceX, YouTube, Claude, Gemini, MrBeast, Grok…).**
- Created, bought out with 85 SOL, migrated, and an operator buys 160–200 SOL — all in one slot. The operator is the very
  next transaction after the migration every time.
- The price ends that slot at 8.3× and drifts to about 9.5× as retail buys.
- The operator then dumps everything at once (median 16 min; 90% within 57 min) and the price drops 90%.
- About 5–6 operators run this. The 6tzAKfHt/4G9JAzft farm is one of them.

**2. Mayhem (~270/day).** About 0.11 SOL of real SOL in the pool. Not tradable.

**3. Fast organic (curve completed in under 5 min, ~100–140/day).**
- Flat for the first minute; holders sell 95% within 10 min.
- Price is 0.18× at 10 min and 0.06× at 1 h.
- 43% touch 2× within the hour, but no rule picks them in advance.

**4. Slow organic (~100/day).** Price is 0.87× at 10 min and 0.11× at 1 h.

**Migration-moment snipers on organic tokens lose:** −370 SOL (R2) and −903 SOL (R3).

## Who profits (MEASURED; ≥20 round trips, profit on both days)
| Group | Wallets | SOL/day (R2 / R3) | How |
|---|---|---|---|
| Farm operators (insiders, excluded) | 16 | +9,942 / +9,810 | Pump in the first slot, rug at ~16 min |
| A: fast dip-backrun scalpers | 18 | +160 / +108 | 0.5–1 SOL, buy right after a ≥1 SOL sell, sell after 2–4 s. +0.005/trade, ~22,500 trades/day (DCt1NrjQb3, HzSTDqdVFc, BwsqJFaqz5) |
| A′: fewer-trade scalpers | 15 | +41 / +67 | mostly 9CmNu8kE5j |
| B: slower dip buyers | 40 | +47 / +67 | hold 10–120 s |
| C: swing traders | 28 | +61 / +53 | 1.7–3 SOL on tokens 50–75 min old, hold 3–8 min |

## Strategies at our speed (0.5 SOL, 35 ms, real pool fees, +0.0035 per round trip; R2 → R3 → R4)
| Rule | R2 | R3 | R4 |
|---|---|---|---|
| Deep dip (≥25% in the first 5 min) → buy, sell after 2 min | +5.9 | +2.3 (+0.5 without the top 3) | −1.1 |
| Fast graduation: buy 2 min after migration, sell 2 min later | +3.3 | +3.1 (−0.6 without the top 3) | −1.4 |
| Instant graduation: snipe at migration | ~0 | ~0 | ~0 |
| Our dip-backrun on PumpSwap | — | −462 SOL / 19k trades | — |
| Copying the winners | −1% to −8% per trade | — | — |

- Instant-graduation snipes are a lost race: the operator's pump is always the next transaction.
- Our dip-backrun on PumpSwap loses even at 2–8 ms. The scalpers' picks and timing are what matter.

## Can our bot do it?
- **Already in the code:** PumpSwap buy/sell builders (src/build.rs pump_leg) and the exact AMM math
  (program/arbx-sizing/src/venue/pumpswap.rs).
- **Missing:** live migration detection and pool registration, a PumpSwap feed for the sniper, a single-swap send path, and
  cashback-pool support. That is days of work.
- **Verdict:** not worth building now. The one consistent edge needs near-next-transaction landing and about 100× lower cost
  per trade.

## Shadow plan (zero cost)
1. Freeze the 2 best rules (deep dip 25% / 2 min; fast graduation, 2 min delay / 2 min hold).
2. Replay each new recorded day with pm1 → pm2 → pm3 → pm10.
3. Build only after 3 positive new days in a row, at least +3 SOL/day at 35 ms, positive without the top 3 trades, and at
   least 80 trades/day.
4. Track group A daily: if their edge per trade rises above ~1.5%, revisit.

# Wallet BUkpShoE: his exact strategy, and can we run it? (10-24 ~21:35 PKT)

Wallet BUkpShoEWRiPckdFs3kzYGjBPfUhL6G39ufo84QeogPP. Read-only study, agent + Haiku 5.5 ($0.046).
MEASURED = counted from chain data; INFERRED = reading. Results: /home/moiz/sniper-data/strategies/bukp/.

| Day | Window (PKT) | Trips | Curve P&L before tx fees |
|---|---|---|---|
| R1 | 10-22 03:12 → 18:56 | 2,167 | +32.6 SOL |
| R2 | 10-22 20:43 → 10-23 18:28 | 3,493 | +28.9 SOL |
| R3 | 10-23 19:26 → 10-24 19:23 | 3,850 | +39.9 SOL |
| R4 | 10-24 19:25 → ~21:00 (partial) | 237 | +3.7 SOL |

Realized after his own fees: +23 SOL on R2 and +37 SOL on R3.

## His strategy (MEASURED unless marked)
1. **What he buys:** busy tokens, usually about a minute old, whose creator has sold out.
   - Curve 32–64 SOL, about 70 wallets so far, 6–7 known bots already holding.
   - Price about 18% below its high but up ~15% over the last 20 s.
2. **When he buys:** right after another wallet trades, in the same slot, a median ~100–115 transactions later.
   - 74%: after someone's buy (median 0.33 SOL, +1.5% move).
   - 26%: after someone's sell (median 0.85 SOL, −3.9% move).
   - Not a pure dip strategy.
3. **Size:** about 1.9–2.0% of the curve's SOL (correlation 0.999): 0.60 SOL at a 30–35 SOL curve, 1.0 at 50–60, 1.64 above 80.
   Every buy moves the price about 4%.
4. **Positions:** one buy and one sell per token; never adds, never sells in pieces. Holds 5–7 tokens at once, up to ~20.
5. **Exit:**
   - 24% of trips end at a fixed ~300 s timeout.
   - The rest exit earlier, often in the same slot as another wallet's trade (median 55 transactions later).
   - He sits through a median of 8 other sells ≥0.3 SOL first, and he does not sell ahead of sell waves.
6. **Plumbing:**
   - one wallet;
   - priority fee ~0.0002 SOL, plus a 0.00021 SOL tip on ~55% of transactions;
   - mostly the Astralane relay;
   - plain pump.fun instructions;
   - about 40% of his transactions fail.
   - Cost about 0.0008 SOL per round trip, about 4× lower than ours.
7. **Where the money is (curve P&L, SOL per day):**

   | Part | R1 | R2 | R3 |
   |---|---|---|---|
   | Buys of 0.6–1.0 SOL (curve under ~50) | +40 | +54 | +62 |
   | Buys of 1.3–2 SOL | −13 | −28 | −27 |

   - Trades closed between 30 s and 5 min win; the 300 s timeouts lose.
   - Without his best 1% of trips he is negative on R2 and R3.
8. **The older census note** ("profit in big or scaled-in positions") is wrong for these days: he never scales in, and his big buys lose.

## Selection
- A public-data model picks out his trading moments well: AUC 0.91 on R3 and 0.90 on R1, trained on R2 only.
- Strongest signals:
  - a 0.25–1.2 SOL buy, or a ≥1.2 SOL sell, in the current slot;
  - a big 1-slot move either way;
  - curve 32–64 SOL;
  - younger tokens;
  - more known bots holding.
- He trades only 8–9% of the top-ranked moments: a private filter, a capacity limit, or lost races.

## Haiku
- **Round 1** (16 batch requests, R2 only): recovered the size rule, the trigger types and the "bots holding" filter.
- **Round 2** (6 requests): 18 flow-based exit rules.
- **Checked in code:** all 18 lose on R2 / R3 / R1 (−0.002 to −0.044 SOL a trade). The closest misses his exit time by a median of 55–66 slots.

## Can we run it? (MEASURED replays: our costs, +5% guard, follower limits)

| Test | R2 | R3 | R1 |
|---|---|---|---|
| His exact trades, his landing, our costs | +10.5 | +22.8 | +20.3 |
| His exact trades, landing 35 ms after his trigger, his sizes | −24.6 | −3.1 | +11.1 |
| Same, 0.6 SOL size | +5.1 | +17.1 | +20.4 |
| Same, 0.6 SOL, curve under 50 only | +18.6 | +25.1 | +24.1 |
| His real entries + best simple exit (timer, take-profit/stop, sell-on-sell) | loses | loses | ~break-even |
| His real entries + learned exit model (AUC 0.89) | −17.5 | −23.2 | −5.7 |
| His real entries + Haiku exit rules | all lose | all lose | all lose |
| Entry model + rule exits | loses | loses | loses |

## Verdict
- **No:** we can't run it profitably from public data.
- **Speed is not the problem (INFERRED):** he lands about 100 transactions after the trigger; we land at about 65.
- **The money is his exit decision:** worth about +0.01–0.02 SOL a trade over anything we can build. Nothing public reproduces it — likely private flow or his own model.
- **His costs are about 4× lower than ours.**
- **Copying would need:** his exit signal, ~0.001 SOL per round trip, an engine holding 5–7 positions, and curves under 50 SOL.

# Follow-up: is his edge picking graduating tokens? (10-24 ~22:10 PKT)

Owner: "if we knew his exact exit moments, why can't we?" Read-only; Haiku not needed ($0).
Results: /home/moiz/sniper-data/strategies/bukp/ (grad.json, exit_families.json, copy_exit.json, grad_gate.json).

1. **The split is real, but it isn't his skill.**
   - On tokens that later graduate, his trips made +30.4 / +43.3 / +50.3 SOL (R1 / R2 / R3). All his other trips: +2.2 / −14.3 / −10.4.
   - His entries graduate within 10 min at about the base rate (3.4–4.7% vs 3.2–4.2%; eventually ×1.2–1.3).
   - He trades where the big moves happen, at about the base rate (INFERRED).
2. **Graduation model.**
   - AUC 0.89–0.90 for "graduates within 2 min" (0.73–0.86 for 10 min).
   - Mostly it flags tokens already at curve 85–100 SOL.
3. **A graduation-gated strategy at our speed loses:** −0.4 to −12.6 SOL/day on R3 and −5.5 to +0.6 on R1, across every exit
   tried (trailing stops, take-profit ladders, timers, hold to graduation).
   - Graduating picks pay +20–30%; failed picks fall back to ~30 SOL.
   - It needs about 75%+ precision; the model delivers 51–87%.
4. **His exit's value is cutting losses early on the ~90% of tokens that never graduate.**
   - On graduation-bound tokens his exit actually cuts winners short.
   - Trailing stops checked only on sell prints are rejected: his drawdown at exit spans 0.2–32%.
5. **Copying his exit live (we sell one slot after his sell):** −72.6 / −71.7 / −30.5 SOL per day.
   - Each copied exit eats his own ~3.5% sell impact, about 0.02 SOL a trade.
   - The non-graduating majority decides the result.
6. **Answer.** We only learn his exit after his sell prints, and by then his sale has already moved the price. No public-data
   rule reproduces his loss-cutting. Graduation prediction would need ~75%+ precision while the curve is still ≤90 SOL, likely
   requiring off-chain or social signals. Not worth a paper test.

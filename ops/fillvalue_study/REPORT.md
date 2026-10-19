# Fill-Quality VALUE study — PnL vs entry-timing curve (pump.fun sniper)

**Goal:** quantify how much each slot of entry latency costs, so we know the *prize* before
building the fill-quality engineering. Pure historical / paper replay. **No live trading.**

## Setup
- **Sample:** 1,140 unbiased pump.fun `create_v2` launches (`/root/profit_backtest/`), create-slot-anchored
  bonding-curve price paths reconstructed from on-chain trades via the global mint-authority PDA stream
  (`TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM`). No survivorship/selection bias.
- **Filter (shipped live config):** `creator_fee_bps == 0` (is_snipeable) **and** sized spendable
  `dev_buy >= 2.0 SOL`. -> **656 launches** pass = the launches we would actually snipe.
- **Exit ladder (shipped live config):** derisk 0.30, ride 1.40, trail 0.92, cut 0.95, ladder 0.25,
  cap 40 slots (~9 s). Faithful port reused verbatim from `profit_backtest/backtest.py:simulate()`.
- **Fill cost model:** 8%/leg slippage, 0.0008 SOL/leg fee, size 2.0 SOL (same as the profit backtest,
  so numbers are comparable). Returns are per-snipe net fraction of size (**R**); SOL = R x 2.0.
- **Granularity:** the bonding-curve price is piecewise-constant between trades, and the series carries
  every trade's slot — so per-slot price near the create slot is already the finest observable resolution.
  **No re-harvest was needed**; a fresh sample could not add resolution the on-chain record doesn't have.

## Entry-timing definitions
For each launch, entry = the bonding-curve price *k* slots past the create slot (last trade with
slot <= C+k; the create-slot floor if none). The ladder then replays on the subsequent path (trades after
the entry slot), r = px/entry.
- **floor** = dev-buy floor / first-trade-after-dev-buy = best case, *same-block-first* (full create-slot
  path is downstream of you). This is exactly the profit-backtest floor case.
- **+1, +2, +3, +5 slots** = progressively later; co-snipers have already bid the curve up.
- **observed-late** = first price *visible* ~1 slot after via the RPC `processed` lag — the proxy our
  current paper-trade mode fills at.

## THE CURVE — mean R by entry timing (full 656-launch sample)

| entry offset   |   n |  win% |   mean R |  median R |  total R | top-5% share | Delta vs floor |
|----------------|----:|------:|---------:|----------:|---------:|-------------:|-----------:|
| **floor**      | 656 | 24.7% | **-0.0099** | -0.0821 |   -6.52 |      -468%   |   +0.0000  |
| +1 slot        | 656 |  8.8% |  -0.0750 | -0.0880 |  -49.21 |       -17%   |   -0.0651  |
| +2 slot        | 656 |  9.3% |  -0.0724 | -0.0876 |  -47.47 |       -23%   |   -0.0624  |
| +3 slot        | 656 | 10.4% |  -0.0773 | -0.0861 |  -50.72 |       -24%   |   -0.0674  |
| +5 slot        | 656 | 11.3% |  -0.0804 | -0.0868 |  -52.74 |       -27%   |   -0.0705  |
| **observed-late** | 656 | 14.3% | **-0.0785** | -0.0813 | -51.47 |  -25%   | **-0.0685** |

**The cost of latency is a CLIFF, not a ramp.** Almost the entire loss happens in the *first* slot
(floor -> +1 = **-0.065 R**); +1 through +5 are flat (within noise). Being 5 slots late is barely worse
than being 1 slot late — the damage is done the instant you miss slot 0.

## Where the money actually is (the decisive split)

Floor replay, split by # co-snipers in the create slot (create-slot congestion):

| subset            |   n | win% | floor mean R | median R | total R |
|-------------------|----:|-----:|-------------:|---------:|--------:|
| 0 co-snipers      | 552 | 13.2% |   -0.0344   | -0.0883  | -18.97  |
| 1-2 co-snipers    |  54 | 81.5% |   **+0.1111** | +0.1087 | +6.00  |
| >=3 co-snipers    |  50 | 90.0% |   **+0.1290** | +0.0729 | +6.45  |

**All positive expectancy lives in the ~16% of launches that are co-sniped in the create slot.** At the
floor those are strongly +EV (+0.11 to +0.13 R, 80-90% win). The 84% that are *un*-co-sniped are dead
weight (-0.034 R). The sniper's job is to be *first* on the hot launches.

### The curve ON the co-sniped subset (where fill quality matters)

| offset | ALL (656) | co-sniped >=1 (104) | 0 co-snipers (552) |
|--------|----------:|-------------------:|-------------------:|
| floor          | -0.0099 | **+0.1197** | -0.0344 |
| +1 slot        | -0.0750 | **-0.0799** | -0.0741 |
| observed-late  | -0.0785 | **-0.0904** | -0.0762 |
| **prize (floor - obs-late)** | **+0.0685** | **+0.2101** | +0.0418 |

On the co-sniped launches, **one slot of latency flips +0.12 R into -0.08 R** — the whole edge is
annihilated. Mechanism: on those 104 congested launches the co-snipers push the curve to a **median
1.35x (mean 1.45x) the floor within the first slot**, so a 1-slot-late sniper buys into the top of the
co-sniper pump and the ladder (cut 0.95 / trail 0.92) stops it out at a loss.

## KEY NUMBERS

- **Floor (ceiling) mean R = -0.0099** (~ break-even). This is *below* the backtest's +0.17, because +0.17
  was a *train-overfit tuned* config (vanilla-only + anti-factory + a looser ladder). Under the **actually
  shipped** filter (dev>=2.0, creator_fee==0) and **shipped** ladder, even a perfect floor fill is only
  break-even *across the whole sample* — it matches the profit-backtest BASELINE (~ -0.005), not the tuned
  grid winner. The +EV is not in the average launch; it is in the co-sniped subset at the floor.
- **Breakeven offset:**
  - Full sample: **undefined / already negative at the floor** — no achievable entry timing makes the
    indiscriminate shipped filter +EV. (A linear fit extrapolates to -3.6 slots, i.e. impossible.)
  - Co-sniped subset: mean R crosses zero at **~0.60 slots past the floor** (interpolating +0.1197 at
    slot 0 -> -0.0799 at slot 1). **You must fill within ~0.6 of a slot of the floor — i.e. essentially
    first-in-the-create-slot — to stay +EV on the hot launches.**
- **Cost per slot of latency:** the honest figure is the **slot-0->1 cliff**, not a smooth slope:
  - Full sample: **-0.065 R** (-0.13 SOL) for the first slot, then ~flat.
  - Co-sniped subset: **-0.20 R** (-0.40 SOL) for the first slot.
  - (A straight-line fit over 0-5 slots gives -0.011 R/slot, but that *understates* the real structure,
    which is a step function: one big drop at slot 1, flat thereafter.)
- **FILL-QUALITY PRIZE (floor - observed-late):**
  - Full sample: **+0.0685 R/snipe ~ +0.137 SOL** per snipe at size 2.0.
  - On the co-sniped subset: **+0.2101 R/snipe ~ +0.420 SOL** per snipe.

## How our current same-slot landing maps onto this curve
Our live tests land **delta 0 = the create slot**. That is *not* automatically the "floor."
- The computed **floor = first-trade-after-the-dev-buy** (ratio ~0.99 vs the dev-buy price), which is the
  realistic **same-slot-FIRST** target — a hair above the absolute floor (the dev buy itself always
  executes before anyone).
- **Intra-slot ordering is not observable on-chain** (per-slot price is the finest granularity). Within
  the create slot the dev buy and any earlier co-snipers execute *before* us, so **even at delta-0 we fill
  ABOVE the floor** — somewhere between "floor" and "+1" depending on our intra-slot rank. On congested
  launches "+1" is already 1.35-1.45x the floor, so each co-sniper we let in ahead of us eats a chunk of
  the +0.21 R prize.
- **Implication:** landing delta-0 is necessary but not sufficient. The prize is captured only to the
  extent we land delta-0 **AND first (or near-first) within that slot**. Delta-0-but-late ~ delta-1 ~ loss.

## Bonus — does being earlier (less congestion) correlate with better outcomes?
Yes, but read it correctly. More co-snipers in the create slot => *better* floor outcome (these are the
launches with real demand: +0.11 to +0.13 R at 80-90% win vs -0.034 at 13% for 0-co-sniper duds). So
congestion is a **positive selection signal** (it marks a live launch) — *provided you win the race*. The
same congestion is what destroys you one slot late (it's the force bidding the curve +35-45% in slot 0).
The lever is therefore **priority within the create slot**, not avoiding congested launches.

## Honest caveats
- Intra-slot execution order is not recoverable from on-chain data; per-slot price is the finest
  granularity. The floor is the *same-slot-first* idealization; real delta-0 fills sit above it.
- Fills modeled as flat %-slippage + fixed per-leg fee (no curve-depth/size model). Floor is the
  optimistic bound.
- One ~13 h market regime, single window. Not lifetime behavior.
- 72/656 filtered launches are dead-on-arrival (0 trades); kept in the population (not survivorship-filtered).

## Bottom line — the PRIZE
Fill quality is worth **+0.069 R (+0.137 SOL) per snipe on average, and +0.21 R (+0.42 SOL) per snipe on
the co-sniped launches that actually carry the edge.** The entire prize is captured (or lost) in **slot 0**:
the cost curve is a cliff — one slot late turns the hot launches from +0.12 R winners into -0.08 R losers,
because co-snipers bid the curve ~1.4x within that first slot. **To be solidly +EV we must land in the
create slot AND first (within ~0.6 of a slot of the floor); anything later ~ break-even-to-negative.**
This confirms, with a number, that profitability is a fill-quality / same-slot-priority problem, not a
filter- or ladder-tuning problem.

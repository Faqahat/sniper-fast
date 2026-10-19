# create_cu_price > 0 — disjoint-window re-validation

**Date:** 2026-10-14  **Verdict: DECAYS (does not hold as a +EV keep-rule).**

## Question
The slot-0 selection signal `create_cu_price > 0` (dev pays any priority fee on their own
create tx) was mined on a ~7h window (656 launches) and looked strong:
create_cu>0 → ~74.6% win / +0.219 net-R; create_cu==0 → ~16% win / ~0.
Does it survive on data that was NOT used to mine it?

## Method (identical outcome model to the mined analysis)
- Outcome = econ102 net-cost model: entry = floor*1.02, shipped exit ladder
  (derisk .30/ride 1.40/trail .92/cut .95/ladder .25/cap 40), 2% pump fee + 0.5% slip +
  fixed priority/base lamports, SIZE = 0.5 SOL. win = net R > 0. Exactly the basis used for the
  mined 74.6%/+0.219 figure.
- Base filter: sized dev_buy ≥ 2 SOL, creator_fee == 0.
- `create_cu_price` read from the SetComputeUnitPrice (ComputeBudget tag 3, u64) in the CREATE tx,
  re-parsed straight from the create block (same logic as bundle_signal/classify.py).

## Two DISJOINT held-out windows (no overlap with the mined 456604917–456820114)
| window | slot range | gap from mined | n (filtered) |
|---|---|---|---|
| Mined (comparator) | 456604917–456820114 | — | 656 |
| **Paper** (held-out) | 456878173–456911074 | +58k slots later | 246 |
| **Fresh** (harvested now) | 456911928–456962910 | +91k slots later | 192 |

Both held-out windows are strictly later than and non-overlapping with the mined set and with the
bundle_signal 656. Fresh window freshly harvested via the pump mint-authority PDA
(TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM), trajectories reconstructed, then classified.

## Results — win% / net-R, create_cu>0 vs ==0 (CIs: Wilson on win%, bootstrap 5000 on net-R)

| window | bucket | n | win% [95% CI] | net-R mean [95% CI] | gross-win% (zero-cost) |
|---|---|---|---|---|---|
| **MINED (comparator)** | create_cu>0 | 106 | **74.5%** | **+0.2206** [+0.143,+0.308] | 77.7% |
|  | create_cu==0 | 550 | 15.8% | +0.0008 [-0.018,+0.023] | 18.2% |
| **PAPER (held-out)** | create_cu>0 | 62 | 16.1% [9.0,27.2] | **-0.0410** [-0.065,-0.016] | 17.7% |
|  | create_cu==0 | 184 | 13.0% [8.9,18.7] | -0.0464 [-0.059,-0.032] | 18.5% |
| **FRESH (held-out)** | create_cu>0 | 54 | 18.5% [10.4,30.8] | **-0.0364** [-0.067,-0.003] | 20.4% |
|  | create_cu==0 | 138 | 2.2% [0.7,6.2] | -0.0422 [-0.046,-0.037] | 2.9% |
| **COMBINED held-out** | create_cu>0 | 116 | 17.2% [11.4,25.1] | **-0.0389** [-0.059,-0.018] | 19.0% |
|  | create_cu==0 | 322 | 8.4% [5.8,11.9] | -0.0446 [-0.052,-0.037] | 11.8% |

Fraction of launches with create_cu>0: mined 16.2% · paper 25.2% · fresh 28.1% · combined 26.5%.

Sensitivity (strict actual curve dev_buy≥2, removes unbounded-wire/tiny-buy rows, combined n=278):
create_cu>0 win 17.5% / net-R -0.0386 [-0.060,-0.017]; create_cu==0 win 12.0% / net-R -0.0464. Same story.

## Verdict: DECAYS
- The **direction survives** — create_cu>0 still pumps/wins modestly more often than ==0
  (combined 17.2% vs 8.4% win; gross 19.0% vs 11.8%). So it is a weak ordinal signal, not noise and
  not flipped.
- The **magnitude collapses**: mined 74.6% win / +0.221 net-R → held-out 17% win / **-0.039 net-R**.
  Nothing close to 74.6%. The create_cu>0 bucket is **net-negative on both held-out windows, with its
  95% net-R CI entirely below zero** in paper, fresh, and combined. As a keep-rule it would select a
  **money-losing** bucket at our real fill/cost basis.
- **Why**: in the mined window create_cu>0 launches genuinely pumped (gross-win 77.7%). Both held-out
  windows are low-pump regimes (gross-win ~18% and ~3% even at zero cost). The mined result was riding
  a favorable pump regime; create_cu only tilts the base pump rate slightly, and the tilt is nowhere
  near enough to cover costs when the regime is normal/weak. The signal is heavily **regime-confounded**.

## Collinearity (is create_cu>0 just a bigger-dev-buy proxy?)
- Partly. create_cu>0 correlates with larger dev buys (combined median curve dev 4.74 vs 2.47 SOL).
- But not fully collinear: controlling for dev size (within the big-dev half), create_cu>0 keeps a
  small win% edge (combined big-dev 17.9% vs 11.9%). The *independent* effect is real but tiny — and
  its net-R stays **negative** (-0.042). So create_cu>0 is a mild proxy for "serious dev" that adds a
  little pump-probability, not an independent money-maker.

## Recommendation
**Do NOT add `create_cu_price > 0` as a keep-rule to the sniper.** On held-out data it selects a
net-losing bucket (-0.04 R, CI below zero) and the 74.6%/+0.219 figure does not replicate — it was a
regime artifact. At most, create_cu>0 is a weak secondary feature (mild pump-probability tilt,
partly a dev-size proxy); it is not a standalone +EV filter. If anything is wired, it should be as a
small input to a model that also gates on regime, never as a hard keep-gate, and only after a live/forward
check in a pumping regime. Sample sizes on held-out buckets are modest (create_cu>0 n=62/54),
but the conclusion is consistent across both independent windows and the strict-filter sensitivity.

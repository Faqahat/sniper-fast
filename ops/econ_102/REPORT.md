# econ_102 — Is the pump.fun sniper net +EV at our REAL priority-fee fill (floor x 1.02)?

**The decisive profitability gate.** Historical / paper replay only, **no live trading.** Entry = our
measured live fill with `cu_price = 3M` (median of the probe ratios 1.010 / 1.381 / 1.021 ~ **1.02x the
floor**). `r = 1.0` is defined at THIS entry; the exit-ladder `r` is relative to it. Reuses the proven
pipelines verbatim: the shipped `exit_ladder` port, the unbiased on-chain price paths, and the
`profit_ourfill` cost-model reconciliation (pump 1%/leg protocol fee + ~0.5% curve slippage).

## Setup

- **Sample** -- 1,141 unbiased `create_v2` launches reconstructed from the on-chain mint-authority trade
  stream (`/root/profit_backtest`, slots ~456604-456820), no survivorship bias. Shipped filter
  (`creator_fee_bps==0` **and** sized spendable `dev_buy >= 2.0 SOL`) -> **656 launches**. Co-sniped
  (>=1 co-sniper in the create slot) -> **104**. Primary sample: complete on-chain record, full forward
  horizon (median 54-slot span).
- **Second OOS window** -- the 254 disjoint, *later* paper-run mints (`paper_traj.json`, slots
  456878-456911). Reported as an independent regime check.
- **Entry** = `floor_price x 1.02`. Because we land in the create slot ~first, the sell path = the full
  create-slot-anchored trade series (the whole path is downstream of our fill), exactly the fillvalue
  "floor" treatment, shifted up by the 1.02 fill premium.
- **Exit** = shipped ladder: derisk .30 / ride 1.40 / trail .92 / cut .95 / ladder .25 / cap 40 slots.
- **Costs (ALL applied, net):**
  - pump protocol fee **1%/leg** (buy + every sell leg) -> ~2% round-trip, size-independent %.
  - curve slippage **0.25%/leg** -> ~0.5% round-trip (recon figure at our small size).
  - priority fee **FIXED**: `3M cu_price x 120k cu_limit / 1e6 = 360k lamports/leg` + 5k base/leg,
    charged on the buy and every sell leg -> ~0.00073 SOL for a 1-buy-1-sell round trip. As a FIXED
    SOL cost its % drag scales inversely with position size -- hence the 3-size sweep.

| round-trip cost @ nominal 2 legs | 0.1 SOL | 0.5 SOL | 2.0 SOL |
|---|---:|---:|---:|
| pump fee (flat) | 2.00% | 2.00% | 2.00% |
| curve slippage (flat) | 0.50% | 0.50% | 0.50% |
| priority + base (**fixed**) | **0.73%** | **0.15%** | **0.04%** |
| **total** | **~3.23%** | **~2.65%** | **~2.54%** |

---

## (a) FULL filter-passing sample -- the ACTIONABLE number (net of all costs, OOS)

Primary backtest window, 656 launches, train/val split by slot (train 328 / val 328, split slot
456702281). Per-snipe net **R** (fraction of position); SOL = R x size.

| size | mean R | median R | win% | total R | top-5% share | mean-ex-top-2 | SOL / snipe |
|---|---:|---:|---:|---:|---:|---:|---:|
| **0.1 SOL** (full) | **+0.0264** | -0.0457 | 23.6% | +17.30 | 192% | +0.0205 | +0.0026 |
| **0.5 SOL** (full) | **+0.0363** | -0.0364 | 25.3% | +23.82 | 141% | +0.0304 | +0.0182 |
| **2.0 SOL** (full) | **+0.0382** | -0.0347 | 25.5% | +25.04 | 134% | +0.0323 | +0.0764 |
| 0.1 SOL (VAL/OOS) | +0.0287 | -0.0428 | 26.8% | +9.40 | 169% | +0.0173 | +0.0029 |
| 0.5 SOL (VAL/OOS) | +0.0388 | -0.0338 | 29.0% | +12.74 | 126% | +0.0274 | +0.0194 |
| 2.0 SOL (VAL/OOS) | +0.0408 | -0.0322 | 29.3% | +13.37 | 120% | +0.0293 | +0.0816 |

**Positive at ALL THREE sizes on the backtest window**, in-sample and out-of-sample. Gross ceiling
(zero cost) = **+0.0646 R** -- comfortably above the ~2.5-3.2% total cost, which is why net stays
positive. The fixed priority cost erodes mean R from +0.038 (2.0 SOL) to +0.026 (0.1 SOL) but **never
drives it below zero**; its drag effectively stops mattering by ~0.5 SOL (0.5->2.0 moves mean only
+0.0363->+0.0382). Median R is negative (most launches are small post-cost losers) -- the mean is
carried by the minority that pump, but `mean-ex-top-2` stays positive (+0.03), so it is **not** a
2-name artifact.

## (b) CO-SNIPED subset -- the CEILING (not pre-buy knowable; the edge concentrates here)

| size | mean R | median R | win% | total R | top-5% share | mean-ex-top-2 | SOL / snipe |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0.1 SOL (co, n=104) | +0.1612 | +0.1318 | 88.5% | +16.76 | 20% | +0.1450 | +0.0161 |
| 0.5 SOL (co) | **+0.1727** | +0.1530 | 91.3% | +17.96 | 19% | +0.1564 | +0.0863 |
| 2.0 SOL (co) | +0.1749 | +0.1571 | 91.3% | +18.19 | 19% | +0.1585 | +0.3498 |
| 0.5 SOL (co VAL/OOS, n=60) | +0.1710 | +0.1388 | 91.7% | +10.26 | 17% | +0.1497 | +0.0855 |

The clean, robust edge: **~+0.17 R, ~91% win, top-5% share only ~19%, positive median** -- a real
repeatable edge, not a tail lottery. It is the fillvalue study's floor edge (+0.12-0.13 R on co-sniped)
**recovered**, because 1.02x is essentially the floor. Caveat: co-sniper count is not known pre-buy, so
(a) is what we actually earn and (b) is what perfect co-sniped selection would reach.

## Best OOS re-tuned exit (same grid ranges as profit_ourfill, shipped filter, train->val)

| size | best-OOS exit | TRAIN mean | VAL mean | VAL med | VAL win | top-5% | mean-ex-2 |
|---|---|---:|---:|---:|---:|---:|---:|
| 0.1 SOL | derisk 0 / ride 2.0 / trail .92 / cut .98 / cap 10 | +0.0671 | **+0.0824** | -0.040 | 31% | 91% | +0.066 |
| 0.5 SOL | derisk 0 / ride 2.0 / trail .92 / cut .98 / cap 20 | +0.0688 | **+0.0894** | -0.035 | 32% | 84% | +0.073 |
| 2.0 SOL | derisk 0 / ride 2.0 / trail .92 / cut .98 / cap 20 | +0.0701 | **+0.0908** | -0.033 | 32% | 83% | +0.073 |

Tuning roughly **doubles** OOS mean R (to ~+0.09) by dropping the entry de-risk (it sold 30% for ~0
gain and paid the pump fee twice) and riding winners harder (ride 2.0, tight cut .98). But it leans on
the tail (top-5% share ~83-91%), so it is **higher mean, less robust** than the shipped ladder; the
co-sniped edge above is the sturdier source of +EV. Directionally consistent with the old profit_ourfill
grid (derisk-0 + short-cap beats the floor-calibrated ladder); the difference is that at 1.02x the base
is finally low enough for it to land positive.

## Direct comparison to the old 1.33x fill (full sample, shipped, net @ 0.5 SOL)

| fill basis | gross mean R | **net mean R** | win% | verdict |
|---|---:|---:|---:|---|
| **1.02x (this study -- priority-fee fill)** | +0.0646 | **+0.0363** | 25.3% | **+EV** |
| 1.12x (old create+1 fill, profit_ourfill) | +0.0051 | -0.0224 | 16.0% | -EV |
| 1.33x (old co-sniped create+1 fill) | -0.1021 | **-0.1280** | 4.7% | -EV (blow-up) |

The whole story in one table. The old studies concluded -EV because our realized fill sat at
**1.12-1.33x floor** -- on co-sniped launches the co-snipers had already bid the curve ~1.3-1.4x within
the first slot, so we bought the top and the cut/trail stopped us out. **The priority fee fix moves the
fill to 1.02x, back onto the floor, where the co-sniped edge survives.** Gross goes -0.10 -> +0.065; net
-0.128 -> +0.036. The fix is the entire difference between a loser and a winner.

## (c) The honest contradiction -- the disjoint later paper window is -EV

| paper window (254, later/disjoint) | gross ceiling | net 0.1 | net 0.5 | net 2.0 |
|---|---:|---:|---:|---:|
| full sample | **-0.0171** | -0.0537 | -0.0443 | -0.0425 |
| co-sniped (n=159) | -- | -0.0594 | -0.0499 | -0.0481 |

On the disjoint, later paper window the shipped config is **-EV at 1.02x, at every size** -- and the
**gross ceiling itself is negative (-0.017)**, so this is *not* a cost or horizon artifact. I ruled out
the obvious confound: truncating the backtest paths to the paper window's short horizon (median 12 slots
vs the backtest's 54) leaves the backtest firmly +EV (+0.041 ALL / +0.187 co at 12 slots) -- the edge is
captured early. The real cause is **regime**: paper-window launches pumped far less. Only **22% reach
the 1.40 ride trigger (median peak 1.10x our entry)** vs **42% / 1.31x** on the backtest window. With
that little upside the ladder derisks/cuts near entry and the ~2.5% cost turns it negative. (Secondary
possibility: the live RPC harvest of the paper window may have missed fast early trades, understating
the pump; the backtest stream is the complete on-chain record.)

---

## VERDICT

**YES -- the priority-fee fix closes the economics on the backtest regime, with a real OOS-robust edge
-- but the edge is regime-dependent and a later disjoint window did not clear the bar.**

- **At 1.02x fill the shipped config is net +EV after the full 2% fee + 0.5% slippage + fixed priority
  cost** on the unbiased backtest sample: **+0.036-0.038 R** full-sample (~+0.018 to +0.076 SOL/snipe at
  0.5-2.0 SOL), confirmed OOS (val +0.039-0.041), and **+0.17 R / 91% win** on the co-sniped subset
  where the edge lives. A clean reversal of the old -EV finding.
- **At what size does it turn positive?** Positive at **all three sizes**; the fixed priority fee only
  erodes the margin (0.73% round-trip drag at 0.1 SOL -> 0.04% at 2.0 SOL) and stops mattering by
  **~0.5 SOL**. Even 0.1 SOL stays +EV here (+0.026 R) -- the gross edge is large enough to absorb it.
- **Best OOS tuned config:** `derisk 0 / ride 2.0 / trail .92 / cut .98 / ladder .25 / cap 20`, VAL mean
  **~+0.089 R** (0.5 SOL) -- roughly double the shipped ladder, but tail-leaning; prefer the shipped
  ladder plus (if achievable) co-sniped selection for robustness.
- **vs the old 1.33x number:** 1.33x was -0.128 R (blow-up), 1.12x was -0.022 R, 1.02x is +0.036 R.
  **Fill quality is the entire lever**, exactly as the fillvalue / fillprobe studies predicted.

### Honest caveats

1. **Regime dependence is the big one.** The disjoint later paper window is -EV at the same 1.02x fill
   because those launches pumped far less (gross ceiling -0.017). The +EV is real but conditional on a
   regime where launches actually run; not guaranteed lifetime behavior. Two windows, one asset class.
2. **Heavy tail on the full sample.** Full-sample top-5% share is 120-190% (top 5% carry more than all
   the profit; the other 95% are net-negative). `mean-ex-top-2` stays positive (+0.03), so not a 2-name
   fluke, but variance/sizing risk is real. The **co-sniped subset is the robust part** (top-5% ~19%,
   positive median, 91% win) -- but co-sniper count is **not knowable pre-buy**, so the actionable
   full-sample number carries the tail.
3. **The 1.02x fill is itself the live measurement under test** -- median of three probes (1.010 /
   1.381 / 1.021); one already filled at 1.38x. If real fills regress toward that on congested launches
   we slide back up the (steep) fill-cost curve toward the old -EV. The economics hold **only if we keep
   landing at ~1.02x (same-slot, near-first)** -- the fill is the gate and is not yet proven stable live.
4. Flat per-leg cost model (pump 1% + 0.25% curve + fixed priority), no depth/size curve beyond flat
   slippage; priority charged on every leg (slightly conservative for multi-leg exits). Intra-slot order
   not recoverable, so 1.02x is the per-launch fill premium, not an intra-slot rank.

Artifacts: `econ102.py` (engine), `run.py` (analysis), `trunc.py` (horizon control), `results.json`.

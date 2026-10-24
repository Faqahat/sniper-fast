# Non-SOL-quoted pump.fun curves: universe, replay, selection (2026-10-23, times PKT)

Read-only, offline. Nothing was sent and no server was touched.

Labels:
- **MEASURED**: collector data.
- **PAPER**: replay of our mechanics on the real trade path.
- **INFERRED**: my reading of the data.

Windows:
- **R1:** 10-22 03:07 → 18:00 (14.9 h).
- **R2:** 10-22 20:43 → 10-23 07:57 (11.2 h).

## Verdict

**1. No robust edge for us on non-SOL curves.**
- Unselected, our mechanics lose about **−75 SOL per run**, or about −0.04 SOL per 0.5 SOL fill. That holds for every exit, landing and variant. PAPER.
- The mechanics: buy after the bundle only if first, then sell after 5–10 s.

**2. Costs are the problem.**
- A flat round trip costs about **6.6% of size** on a 30-bps creator-fee curve and about **12%** on a 300-bps curve. PAPER.
- What makes up that cost: pump fees on both sides, 2% buy overhead, a 1.5% fill penalty and 0.3% per swap leg.
- In 53–55% of our fills nobody buys after us within 8 s.

**3. The follow-on demand is generic and real.** MEASURED.
- Generic wallets make 96–98% of the buy volume 2–10 s after the create.
- Fast snipers matter only in the first 2 s, where they are 20–25% of the volume.
- About a third of tradeable launches get ≥ 1 SOL-eq of generic buying in 2–10 s.

**4. Demand can be predicted at create time, but the prediction doesn't pay.**
- A create-time model reaches AUC 0.83 out-of-sample in both directions.
- Even a perfect look-ahead oracle (launches that will get ≥ 3 SOL-eq of generic buying in 2–10 s) makes only about **+0.05 SOL per fill**: +24 to +28 SOL per run at t8. PAPER.

**5. One weak candidate is frozen (NONSOL-1), for a paper forward test only.**
- Rule: the model's top 2% of launches, sell at 5 s.
- It was positive out-of-sample in both periods under the strict variant: **+0.8 to +2.5 SOL per period** on 22–82 fills.
- But it is fragile:
  - median trade negative;
  - negative without the best 5 trades;
  - bootstrap interval includes 0;
  - the R1→R2 profit comes from copycat name waves;
  - 3 of 4 model variants lose in one direction.
- **Expect about break-even. Do not trade it live.**

**6. Among the pros, only 9qz7cW earns real money here.** MEASURED.
- 9qz7cW: **+170 SOL-eq** on curve legs, 358 launches.
  - It mostly enters 2–4 s after the create with about 3 SOL, into launches that already show demand.
  - Its picks' median generic buying in 2–10 s is 8.9 SOL-eq; for all launches the median is 0.
- The others are small: FiFawH +9.7, DGmspi +11.3, dKMjeG −0.4, D24ipY −3.1, 9Sh2fd −2.0.
- **Generic wallets as a group lose −17.3k SOL-eq.**

## 1. Universe (MEASURED)

| | R1 | R2 |
|---|---|---|
| non-SOL launches | 8,821 (593/h) | 8,278 (737/h) |
| SOL-quoted launches, same window | 16,019 (1,076/h) | 17,871 (1,591/h) |
| non-SOL, non-mayhem | 8,627 | 7,990 |
| … with any trade at all | 4,064 | 4,128 |
| … with a dev buy in the create tx (tradeable) | 2,644 (177/h) | 2,545 (227/h) |

**By quote** (non-mayhem launches, with dev-buy counts in brackets). There are 538 different quote tokens.
- **R1:** PUMP 4,195 (366); other tokens 2,983 (1,476); pump-token quotes 732 (491); xStocks 651 (257); USDC 66 (54).
- **R2:** PUMP 3,683 (481); other 2,589 (1,078); pump-token 930 (608); xStocks 685 (294); USDC 103 (84).
- PUMP is the most common quote, but about 90% of PUMP-quoted launches have no dev buy and stay empty.
- Hourly counts by PKT hour are in `universe.txt`. Full hours range from 344 to 1,074 launches.

**Dev and bundle** (tradeable launches):

| | R1 | R2 |
|---|---|---|
| Dev buy SOL-eq, p50 | 0.05 | 0.15 |
| Dev buy, p90 | 3.7 | 4.1 |
| Dev buy ≥ 1 SOL | 30% | 32% |
| Dev buy ≥ 2 SOL | 22% | 24% |

- **Glued bundle** (both runs):
  - none: 48%
  - 1 tx: 7–9%
  - 2 tx: 13–15%
  - 3 tx: 22–23%
  - 4+ tx: 6–8%
  - Bundle size p50: 3.1–3.9 SOL-eq.
- **Creator fee is set per curve.** 30 bps on 51–53% of curves, 100 bps on 19%, 300 bps on 16–17%. Protocol fee is 95 bps everywhere.
  - Among pump-token-quoted curves, 39% charge 300 bps.
- **Curve depth** (initial virtual quote reserves) is about 30–32 SOL-eq. USDC curves are deeper (41); pump-token-quoted curves are shallower (p50 22).
- The create payer is the creator on 35–37% of launches.

**Price vs the post-bundle price** (tradeable launches; mean, and share above 1.10×). Medians are 1.000 at most checkpoints because most launches have no trades.

| | 1 s | 2 s | 5 s | 10 s | 30 s | 60 s |
|---|---|---|---|---|---|---|
| R1, all trades | 1.049 / 17% | 1.053 / 19% | 1.046 / 21% | 1.039 / 20% | 1.028 / 18% | 1.019 / 15% |
| R1, fast snipers removed | 1.021 / 9% | 1.031 / 14% | 1.035 / 18% | 1.034 / 19% | 1.026 / 17% | 1.017 / 15% |
| R2, all trades | 1.048 / 17% | 1.051 / 19% | 1.042 / 21% | 1.025 / 19% | 0.985 / 15% | 0.978 / 13% |
| R2, fast snipers removed | 1.019 / 8% | 1.029 / 13% | 1.030 / 18% | 1.019 / 17% | 0.982 / 14% | 0.975 / 11% |

- Fast snipers account for about half of the 1–2 s rise.
- By 60 s, 38–42% of launches are below 0.90×.
- Launches with a dev buy ≥ 1 SOL or a bundle are more volatile both ways (fast snipers and pros removed):
  - at 5 s, 24–27% are above 1.10× and 23–24% are below 0.90×;
  - at 60 s, 64–65% are below 0.90×.
- Removing the pros on top of the fast snipers changes nothing, because the active pros are fast snipers too.

**Who buys** after the bundle. Fast snipers = 380 SOL-side wallets (owner's rule) plus 55 wallets from the same rule on non-SOL curves, 399 in all.

| Window | Fast snipers | Pros | Generic | Launches with ≥ 1 generic buyer |
|---|---|---|---|---|
| 0–2 s | 20–25% | 6–8% | 69–71% | 32–33% |
| 2–10 s | 0–1% | 1–2% | 96–98% | 46–47% |
| 10–60 s | 0% | 1% | 98–99% | 47–49% |

- Generic buying in 2–10 s per launch: p75 2.7–3.1 SOL-eq, p90 9.4–10.3 SOL-eq.
- 33–34% of launches get ≥ 1 SOL-eq of generic buying in that window.

**Who makes money.** Non-insider wallets, curve legs only. Sells are capped at the wallet's own buys. Open tokens are valued by selling into the last curve state, or at 0 if the curve graduated.
- All non-insider wallets: **−17.0k SOL-eq** net. Generic −17.3k, fast snipers +60, pros +186.
- 9qz7cW: **+170.2** (R1 +55.7 / R2 +114.5) on 358 launches.
  - Its 281 tradeable picks: first buy p50 4.0 s after the create, 42% within 2 slots, first-buy size p50 3.0 SOL-eq.
  - This is before its tx fees, tips and failed txs. Its own ledger shows +97.5 SOL net on non-SOL curves in 36 h.
- Other non-pro earners:
  - `Fhbh1DTU…`: +71 on 516 launches, first buy 1.5 s. It is not in the fast list (41% within 2 slots).
  - `sssssyv2…`: +54, enters at about 36 s.

**Pros' picks with their own trades removed** (median, and share above 1.10×):

| | 5 s | 10 s |
|---|---|---|
| All tradeable launches | 1.000 / 21% | 1.000 / 20% |
| 9qz7cW (281 picks) | 1.12 / 53% | 1.19 / 63% |
| dKMjeG (29) | 1.24 / 62% | 1.11 / 55% |
| FiFawH (28) | 1.13 / 61% | 1.12 / 64% |
| DGmspi (12) | 1.15 / 58% | 1.17 / 58% |
| D24ipY (15) | 1.05 / 40% | 1.22 / 53% |
| 9Sh2fd (17) | 1.04 / 35% | 1.03 / 29% |

- INFERRED: same story as on SOL. The pros pick better than average, but:
  - 9qz7cW decides seconds after the create, so its pick uses information we don't have when the bundle closes;
  - the create-slot pros have small samples.
- Our model's top-2% picks overlap with pro picks on only 7–13% of launches.

## 2. Replay (PAPER): our mechanics on quote-denominated curves

**Mechanics**
- Reserves are in quote units. The curve's own fees come from its events.
- Entry:
  - Buy 0.5 SOL-eq right after the dev's glued bundle, only if first. The guard: price at our landing ≤ 1.005 × the post-bundle price.
  - Landing 30, 45 or 75 ms. R2 uses our engine's arrival timelines (block-order placement, quote-aware) for 2,076 of 2,545 tradeable launches. R1 and the rest use the block-position proxy.
- Costs:
  - 1.5% pessimistic fill.
  - 2% buy overhead, or 0.6% in the pro-cost variant.
  - Swap leg SOL ⇄ quote: 0.3% per side by default, with sensitivity.
  - 0.0005 SOL per sell tx; a guard-failed buy costs −0.005 SOL.
- Value in SOL uses the hourly measured quote rate. Exits: sell everything t s after our buy slot.

**Variants**
- **base:** the real trade path.
- **strict:** every fast-sniper and pro wallet's trades after our entry removed. Sells by wallets that held before our entry are kept.
- **harsh:** only their buys removed, their sells kept (the same as rp.sim `drop_after`).
- **(b) skipped:** variant (b) needs followers' slippage limits. The collector rows hold instruction names but no instruction data, so the limits of non-SOL followers can't be decoded.

**Validation** (MEASURED, `validate.txt`)
- The constant-product prediction matches real events.
  - Buys: median relative error 3e-9, p99 1e-3. Sells: exact.
  - Protocol fee = amount × bps on 170,231 of 170,274 trades.
- On R2 launches with a timeline, the proxy agrees with the timeline:
  - on fill / no-fill for 92–96%;
  - on the exact entry index for 92–95%.

**All tradeable launches, no selection** (total SOL):

| | t2 | t5 | t8 | t10 | t20 |
|---|---|---|---|---|---|
| R1 L45 base | −54.0 | −70.2 | −78.5 | −79.2 | −90.6 |
| R1 L45 strict | −67.2 | −75.5 | −82.1 | −82.2 | −92.0 |
| R2 L45 base | −50.9 | −66.6 | −76.7 | −85.3 | −115.0 |
| R2 L45 strict | −65.3 | −73.7 | −82.0 | −89.3 | −117.3 |

- Fills: R1 2,258 of 2,644; R2 2,162 of 2,545. Median fill −0.040 / −0.045 SOL.
- L30 and L75 are within a few SOL of L45.
- Pro cost (0.6% overhead, no swap cost), L45 strict t5: R1 −53.2, R2 −52.3. Still clearly negative.
- Every quote class is negative. Pump-token quotes are worst at about −0.05 per fill.
- No split by dev size, bundle size or creator fee turns positive.
- Oracle (look-ahead, not tradeable): launches with ≥ 3 SOL-eq of generic buying in 2–10 s.
  - Strict t8 L45: R1 **+23.8** (443 fills); R2 **+26.7** (464 fills).
  - Mean +0.056 / +0.060 per fill.

**Swap cost**
- MEASURED, retail all-in: in-tx SOL ⇄ quote conversions on trades ≥ 0.3 SOL. This includes bot fees and rent noise, so it is an upper bound.
- Median per leg: USDC 1.27%, PUMP 1.16%, xStocks 1.8–2.8%, other tokens 1.3–4.3%.
- The pros hold wSOL or quote inventory, so their direct-pool cost can't be read from our rows (the collector logs no wSOL or quote token balances).
- USDC conversions imply SOL at 102–106 USD through both runs. The price file says 104.3.

## 3. Selection (no look-ahead)

**Features**
- Known when the bundle closes:
  - quote class, curve depth, creator-fee bps;
  - dev buy (log size and supply share);
  - glued tx count, wallets and SOL-eq;
  - create payer is creator, create tip and fee, CreateV2.
- The live engine's decision-time history features (shadow decide-record names: `h_bund_*`, `h_cr_*`, heat, waves, name shape).
- Walk-forward non-SOL history, using only launches ≥ 60 s old: the creator's earlier non-SOL launches and their demand, and the same quote token's last 60 minutes.
- Excluded: metadata fetches (about 30 s late), funder lookups and post-create flow.
- FINAL-2 itself picked **none** of the 2,076 non-SOL R2 launches it scored. Its features are SOL-denominated, so a separate model was needed.

**Model:** L2 logistic regression. Label = generic buying ≥ 3 SOL-eq in 2–10 s. Train on one run, test on the other.

| | R1 → R2 | R2 → R1 |
|---|---|---|
| AUC train | 0.857 | 0.855 |
| AUC test | 0.834 | 0.831 |

- Test label rate in the top 2–10%: 56–66%, against about 24% at baseline.
- Top weights:
  - positive: bundle SOL-eq, dev supply share, creator's first non-SOL launch, bundle wallets' past wins;
  - negative: shallow curve, creator with many earlier non-SOL launches.

**TEST totals** (strict, L45). Cut = top x% by train score:

| Cut | R1→R2 t5 | t8 | t10 | R2→R1 t5 | t8 | t10 |
|---|---|---|---|---|---|---|
| top 2% | **+1.52** (65 fills) | +0.08 | −0.75 | **+2.51** (28 fills) | +1.43 | +0.74 |
| top 5% | −0.49 (124) | −2.14 | −2.58 | +1.22 (70) | −0.10 | −0.99 |
| top 10% | −0.75 (235) | −4.29 | −6.24 | −2.05 (144) | −2.93 | −3.55 |
| top 20% | −6.26 (414) | −10.36 | −15.54 | −9.49 (318) | −10.81 | −11.61 |

- A rule grid chosen on train (dev, bundle, creator fee, quote set, walk-forward history) was **negative even in-sample**: best R1 −1.52, best R2 −2.05.

**Top 2%, strict, t5, per landing.** Each period is the TEST set of the other direction.

| Test | Landing | Total | Fills | Median per fill | Win rate | Without best 5 | Halves |
|---|---|---|---|---|---|---|---|
| R2 | 30 ms | +2.08 | 82 | −0.017 | 48% | −0.66 | +0.73 / +1.35 |
| R2 | 45 ms | +1.52 | 65 | −0.001 | 48% | −1.16 | +0.59 / +0.93 |
| R2 | 75 ms | +0.78 | 54 | −0.045 | 41% | −1.90 | +0.59 / +0.19 |
| R1 | 30 ms | +1.58 | 37 | −0.029 | 40% | −1.40 | +0.63 / +0.95 |
| R1 | 45 ms | +2.51 | 28 | −0.018 | 46% | −0.47 | +0.94 / +1.57 |
| R1 | 75 ms | +1.89 | 22 | −0.018 | 46% | −0.49 | +0.23 / +1.66 |

**Robustness of the top-2% result**
- **Range:** +0.78 to +2.51 SOL per cell. The landings are alternative scenarios, so the cells don't add up.
- **Harsh variant:** R2 +0.49 / +0.27 / +0.00; R1 +1.04 / +2.10 / +1.66.
- **Costs.**
  - At 1.5% per swap leg, L45 t5 still shows +0.69 (R2 test) / +2.11 (R1 test).
  - With the pro cost (0.6% overhead, 0.3% swaps): +1.98 / +2.71.
  - With a 0.5% fill penalty instead of 1.5%: +1.87 / +2.68.
- **Bootstrap**, P(total ≤ 0):
  - R2 test: 0.15 / 0.20 / 0.33;
  - R1 test: 0.17 / 0.04 / 0.06.
  - The 90% interval includes 0 in 5 of 6 cells.
- **Name waves.** The R2-test profit comes from copycat waves: 8 "Warhound" launches (+1.23) and 3 "Michiko Malandro" (+1.28). Keeping one pick per name: R2 test L45 **−0.69**; R1 test +1.37.
- **Model variants** (`variants.txt`), each out-of-sample in both directions:
  - label "demand ≥ 1 SOL-eq": R2→R1 negative at top 2%.
  - ridge regression on log demand: R2→R1 mostly negative at top 2% (2 of 3 landings).
  - no engine features: R1→R2 negative at top 2%.
  - PnL > 0 label: positive both ways at 30/45 ms, but R1→R2 at 75 ms is negative.
  - INFERRED: noise around zero with a thin positive tail.

## 4. Frozen: NONSOL-1, weak candidate, paper forward test only

- File: `ops/overnight/dryrun/frozen_nonsol.json`.
- sha256: `3db2c5f1ee8d167df89eb9e3086dc2038bc3638f4e0d43ac86fe8d1a45f2b579`.
- **What it contains:**
  - The same recipe, re-fit on R1 + R2: 43 features with their means, standard deviations and weights; threshold = 98th percentile of scores.
  - Mechanics: 0.5 SOL-eq, first-after-bundle guard 1.005, primary landing 45 ms, sell at 5 s (t3 / t8 as readouts).
  - The cost assumptions, the out-of-sample evidence and all the caveats above.
- **In-sample refit** (strict t5, 30/45/75 ms): R1 +0.81 / +0.94 / +1.29; R2 +2.58 / +1.84 / +1.13. About 104 picks across both runs, roughly 4 per hour.
- **For the forward test:** the model features (incl. the engine's decide-record features) must be computed at decision time.

## Caveats
- **Excluded launches:**
  - 482 mayhem non-SOL launches: a fee-free agent wallet re-pegs their virtual reserves.
  - 104 launches whose quote has no SOL rate.
  - 259 of 8,405 non-mayhem curves had some mis-decoded events; those events were filtered by the curve's modal (virtual − real) offset.
- **Data gaps:** 3% of consecutive trades show reserve gaps (missing trades). That is similar to the SOL side.
- **Quote rates:** hourly mid of in-tx conversions for 87% of launches. The rest use a per-run median or the end-of-R2 price. Hold is ≤ 10 s, so rate drift is negligible.
- **Unproven assumptions:**
  - R1 entry places come from a proxy, though R2 shows it agrees with timelines 92–96%.
  - The 2% overhead, the 1.5% fill penalty and the 0.3% swap leg are assumptions.
  - Same-tx SOL→quote swapping (needed when holding no quote inventory) was not latency-tested.

## Files (`ops/overnight/nonsol/`)
- **Scripts:**
  - `ns_extract.py`: raw-tx pass for creates, non-SOL trades and tx metadata.
  - `ns.py`: loader / cache.
  - `ns_rates.py`: quote → SOL rates and swap legs.
  - `ns_table.py`: per-launch facts and the replay.
  - `ns_universe.py`, `ns_pros.py`: universe and pro analysis.
  - `ns_base.py`, `ns_lib.py`: unselected replay and shared helpers.
  - `ns_select.py`, `ns_variants.py`, `ns_robust.py`: selection and robustness.
  - `ns_validate.py`, `ns_freeze.py`.
- **Outputs:** `universe.txt`, `pros.txt`, `base.txt`, `select.txt`, `variants.txt`, `robust.txt`, `validate.txt`.
- **Data:** `data/table.jsonl` (one row per launch, incl. replay proceeds per landing × variant × exit), `data/rates.json`, `data/fast_snipers.json`, `data/select_res.json`, `data/wallet_pnl.json`, `data/raw_R1|R2/` (extracted rows).

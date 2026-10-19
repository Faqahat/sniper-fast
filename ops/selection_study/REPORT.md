# Selection Study — why 4yFAz…EQrG3's picks win ~58% when our filter's picks win ~28%

Target wallet `4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3`. Pure on-chain analysis, no live trading.
Data reused READ-ONLY from /root/profit_backtest (unbiased population + labels), /root/exit_study,
/root/snipe_study50 (his 200 landed picks + slot-0 features). New work in /root/selection_study.

## Method — one consistent label for everything
To compare SELECTION fairly, every mint (population, his landed picks, his failed attempts) is labelled
with the **identical** outcome: net return R under the baseline exit ladder
(derisk .40 / ride 1.6 / trail .85 / cut .85 / ladder .30 / cap 20 slots), replayed on the
**create-slot-floor-anchored** bonding-curve price series (`common.trajectory` + `backtest.simulate`,
8% slip, 0.0008 SOL/leg, size 2 SOL). flip-win = net R > 0. This reproduces the backtest's 28% anchor
exactly (below) and holds EXIT mechanics constant so only selection varies. His picks re-anchored at the
create-slot floor (not his higher fill) so they are label-comparable to the population.

## PART 0 — Anchors (identical floor-anchored ladder label)

| set | n | flip-win | meanR | medR |
|---|---|---|---|---|
| unbiased population (full) | 1140 | 22.5% | -0.012 | -0.081 |
| unbiased pop, OUR filter passes (fee0 & dev>=0.3) | 856 | **27.6%** | -0.005 | -0.081 |
| HIS landed picks | 186 | **78.0%** | +0.093 | +0.073 |
| HIS never-landed attempts | 269 | **82.9%** | +0.140 | +0.102 |
| HIS attempted (landed + failed) | 455 | 80.9% | +0.121 | +0.087 |

His picks win ~80% at the floor vs 27.6% for our filter's picks on the same population and same exit.
(His 58% *realised* win is this ~80% floor edge minus his fill above the floor + fees/tips/latency.)
The selection gap is real and large: **~50 points at the floor, ~30 points realised.**

## PART 2 — Fill-survivorship test (the critical alternative) -> REJECTED
He errors ~79% of his buys (2,813 failed buy-txs vs 205 landed in-window). Hypothesis: his win rate is
post-selection by WHAT FILLED, not pre-selection of WHICH mint. Test: label the mints he attempted but
NEVER landed (his SOL never entered the curve) and compare to the mints he landed.

- landed mints: flip-win **78.0%** (n=186)
- never-landed mints: flip-win **82.9%** (n=269)
- delta (landed - never-landed) = **-4.9 pts** (landed is if anything LOWER)

**Landing does not raise the win rate.** The mints he *targets* already win ~80% whether or not his buy
fills. His edge is NOT fill-timing survivorship — it is pre-selection of which launches to attempt.
(Collected from 8,011 wallet sigs over the 200-pick window; failed buys are direct top-level pump buys,
same layout as landed: disc e1f7501ed5b38488, mint=accs[1], buyer=accs[8].)

## PART 1 — Slot-0 feature lifts on the unbiased population (base full-pop win 22.5%)
POPwin = win-rate of pop launches in the bucket; HIS win = win-rate of his attempted picks that
fall in the same bucket; HISshare/POPshare = how concentrated each is.

**dev_buy size (curve-delta truth, SOL) — PRE-BUY knowable from create tx:**

| bucket | pop n | POPwin | HIS win (n) | HISshare / POPshare |
|---|---|---|---|---|
| <0.3 | 645 | 5.0% | 43% (53) | 12% / 57% |
| 0.5–1.0 | 156 | 38.5% | 82% (122) | 27% / 14% |
| 1.0–2.0 | 95 | 40.0% | 83% (108) | 24% / 8% |
| 2.0–5.0 | 123 | **65.0%** | 88% (110) | 24% / 11% |
| >=5.0 | 36 | **86.1%** | 98% (51) | 11% / 3% |

**sized vs unbounded dev buy — PRE-BUY knowable (matters a lot):**

| bucket | pop n | POPwin | HIS win |
|---|---|---|---|
| sized (finite spendable) | 594 | 34.3% | 81% |
| unbounded (u64::MAX cap) | 546 | **9.7%** | 81% |

**same-create-slot co-snipers (follow-on demand; CONTEMPORANEOUS, see caveat):**

| co-snipers | pop n | POPwin | HIS win | HISshare / POPshare |
|---|---|---|---|---|
| 0 | 928 | **10.7%** | 70% | 28% / 81% |
| 1 | 45 | 64.4% | 79% | 16% / 4% |
| 2 | 57 | 71.9% | 81% | 15% / 5% |
| >=3 | 110 | **80.0%** | 89% | 42% / 10% |
| >=1 (any) | 212 | **74.5%** | 85% | 72% / 19% |

**Weak / no signal:** vanilla (28% vs 17%, and his *non*-vanilla picks win 89%); creator in-window launch
frequency (fresh 26% vs factory 18%); creator prior spiking launch (no lift, 22.6%); launch congestion
(per-slot density too sparse to split in this window); launch metadata (name/symbol/uri present on ~all
create_v2 — not parsed, no structural signal expected).

**Feature distributions:** POP median dev 0.25 SOL, co-snipers 0, DOA(dead-on-arrival) 23%. His attempted
picks: dev median **1.19 SOL**, co-snipers median **2** (p75 4), DOA **0%**, vanilla 78%.

### The orthogonality finding
His picks win ~70–98% in **every single bucket**, including buckets where the population wins ~10%
(unbounded-cap 81% vs pop 9.7%; co-snipers=0 70% vs pop 10.7%; non-vanilla 89% vs pop 16.8%). No single
on-chain slot-0 feature *is* his selector — his selection is stronger than, and partly orthogonal to, all
of them. He fires same-slot (80% of entries at delta 0, per snipe_study50), so he is NOT himself waiting
to observe co-snipers; the crowd co-arrives on a shared signal. This points to a residual **off-chain
information edge** (social / trending / caller feeds, or a curated deployer set) that is not
reconstructable from the create tx or in-memory slot-0 state.

## Out-of-sample rule fit (time-split train 70% / val 30% on the unbiased population)

| rule | VAL n | VAL win | VAL meanR | VAL medR | pre-buy? |
|---|---|---|---|---|---|
| baseline (fee0 & dev>=0.3) | 271 | 29.9% | -0.011 | -0.078 | yes |
| sized dev>=1.0 SOL (fee0,van) | 47 | 61.7% | +0.148 | +0.051 | **yes** |
| **sized dev>=2.0 SOL (any flags)** | 54 | **81.5%** | **+0.202** | **+0.126** | **yes** |
| sized dev>=2.0 SOL (fee0,van) | 34 | 73.5% | +0.233 | +0.094 | **yes** |
| co-snipers>=2 | 55 | 80.0% | +0.111 | +0.099 | no (contemporaneous) |
| sized dev>=2 OR co-snipers>=2 | 75 | 76.0% | +0.162 | +0.092 | partly |

All winning slices have a **positive median** (most picks win, not just the tail) — qualitatively unlike
the baseline (negative median, tail-dependent).

## Realistic-fill stress (unbiased VAL; entry above floor + higher slip/fee)

| rule (VAL slice) | optimistic floor | realistic same-slot (12% slip, fill +5%, 0.005/leg) | harsh |
|---|---|---|---|
| baseline | 30% / -0.011 | 16% / -0.107 (-0.21 SOL) | 9% / -0.153 |
| **sized dev>=2.0** | 81% / +0.202 | **52% / +0.086 (+0.17 SOL)** | 39% / +0.031 |
| co-snipers>=2 | 80% / +0.111 | 47% / +0.003 (~breakeven) | 29% / -0.049 |
| sized dev>=2 OR co-snipers>=2 | 76% / +0.162 | 45% / +0.050 (+0.10 SOL) | 31% / -0.005 |

The **sized dev>=2 SOL** rule stays net-positive through realistic same-slot fills (+0.17 SOL/snipe);
baseline is negative at every fill level. The co-sniper rule has higher raw win but degrades to breakeven
under realistic fills — precisely because a crowded launch is the launch you fill worst on (co-snipers =
competition = entry further above the floor).

## VERDICT — (a) slot-0 selectable vs (b) fill survivorship

**The 28%->58% gap is essentially 100% SELECTION (a), ~0% fill-survivorship (b).** Attempted-but-failed
mints win 82.9% ~= landed 78.0%: landing adds nothing, so the edge is which mints he targets, not what
fills. This refutes the hypothesis that his win rate is an artifact of his spray-and-land process.

Within selection, the lever splits three ways:

1. **Create-tx-knowable (true slot-0 filter, no fill tax):** require a **SIZED (finite, spendable)
   dev buy >= ~2.0 SOL**, and **treat a u64::MAX cap buy as NOT qualifying** (unbounded-cap launches win
   only 9.7%). As snipe_engine thresholds: `--min-dev-buy 2.0` applied to the *spendable* dev-buy
   (data[8:16] / curve-delta), rejecting the u64::MAX sentinel rather than letting it pass. OOS VAL win
   **73–81%**, meanR +0.20, positive median, and it **survives realistic fills (+0.17 SOL/snipe)**.
   Covers ~16% of launches and ~35% of his picks.

2. **Contemporaneous demand (not a clean pre-buy filter):** same-create-slot co-snipers >=2 is the single
   strongest separator (28%->80% OOS) but is NOT knowable before you commit a same-slot buy — it is crowd
   demand coincident with entry. Only actionable by entering at create_slot+1 to observe the create-slot
   crowd, which sacrifices the same-slot fill and degrades to breakeven under realistic fills. Marginal.

3. **Residual off-chain edge (not filter-copyable):** his picks beat the population in every on-chain
   bucket, so a large part of his selection uses information not present in slot-0 on-chain state.

**Bottom line for the filter:** filtering is NOT at its ceiling — contrary to the profit_backtest
conclusion. That grid *capped* co-snipers and never *required* a large sized dev buy; requiring
conviction/demand flips expectancy strongly positive and fill-robust on its covered slice. Concrete
change: raise `--min-dev-buy` to ~2.0 SOL on the **spendable** dev buy and **reject u64::MAX-cap** buys.
This is the one copyable, fill-robust slot-0 lever (+0.17 SOL/snipe at realistic fills vs -0.02 baseline),
at the cost of trading far fewer launches (~16% of the stream). The rest of his edge is same-slot fill
quality (already the known lever) plus an off-chain information signal we cannot reconstruct on-chain.

## Sample sizes & caveats
- Unbiased population: 1,140 create_v2 launches over ~13 h via the global mint-authority PDA stream
  (unbiased, not his mints). His picks: 200 landed (186 labelled; 14 undecoded/no-entry) + 297 distinct
  never-landed attempts (269 labelled), ~38 h window.
- Label consistency: reproduces the backtest's 28% filter-pass anchor exactly (27.6%); same ladder, same
  slip/fee, create-slot-floor anchor for all sets.
- His landed picks' co-sniper counts include his own landed same-slot buy (+1); never-landed counts are
  clean of him and still show median 2 and 82.9% win, so the demand is other buyers'. The population
  co-sniper RULE is measured on the clean unbiased stream (no sniper-of-ours present), so it is directly
  usable as stated.
- VAL slices are small (n=34–75); directional, one 38 h regime, one wallet. Floor-anchored wins are
  optimistic; the stress table is the honest planning number.
- Metadata/socials/bonding-curve-param features not parsed (strings skipped in create parse); create_v2
  initial virtual reserves are protocol-constant so not a cross-sectional signal.

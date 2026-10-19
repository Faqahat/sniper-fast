# Profit backtest report
Sample: 1140 unbiased pump.fun create_v2 launches with usable create-slot price series.
Assumptions: flat slippage 8%/leg, fees 0.0008 SOL/leg at size 2.0 SOL, same-slot fill at create-slot floor px.
Returns are per-snipe net fraction of size (R). SOL expectancy = R * size.
Train/val split by slot: train=798 val=342 (split at slot 456742465).

## A. BASELINE — current config (min_dev_buy=0.3, is_snipeable, derisk .40 ride 1.6 trail .85 cut .85 ladder .30 cap 8s)
FULL   n=856 mean=-0.0045 med=-0.0812 win=28% sd=0.230 sharpe=-0.019 tot=-3.82 top5%=-825%
  passed filter: 856/1140 (75%)
  dist R: p10=-0.116 p25=-0.092 p50=-0.081 p75=+0.022 p90=+0.171 p99=+1.483
  SOL expectancy @ 2.0 SOL: mean=-0.0089  median=-0.1624
TRAIN  n=585 mean=-0.0015 med=-0.0812 win=26% sd=0.232 sharpe=-0.006 tot=-0.88 top5%=-2554%
VAL    n=271 mean=-0.0108 med=-0.0783 win=30% sd=0.224 sharpe=-0.048 tot=-2.93 top5%=-302%
  tail check: mean=-0.0045  drop top1=-0.0065  drop top2=-0.0084  (top1 R=+1.77 top2 R=+1.57)

## B. Grid search (train-tuned, validated out-of-sample)

Stage 1 — top selection filters on TRAIN (base exit, n>=40), with VAL check:
dev_min dev_max  van   co  rep |               TRAIN mean/med/win/n |             VAL mean/med/win/n
    0.1     inf True None    2 | +0.1147/-0.0407/ 38%/242  | +0.0284/-0.0586/ 29%/116
    2.0     inf True None    2 | +0.0921/-0.0779/ 30%/106  | +0.0979/-0.0499/ 41%/54
    0.1     inf True None None | +0.0869/-0.0506/ 36%/301  | +0.0266/-0.0576/ 32%/133
    0.5     inf True None    2 | +0.0855/-0.0354/ 40%/202  | +0.0345/-0.0503/ 32%/97
    1.0     inf True None    2 | +0.0830/-0.0521/ 35%/139  | +0.0670/-0.0488/ 38%/64
    0.3     inf True None    2 | +0.0816/-0.0358/ 40%/211  | +0.0318/-0.0503/ 32%/104
    0.0     inf True None    2 | +0.0801/-0.0615/ 32%/298  | -0.0104/-0.0684/ 25%/137
    2.0     inf True    2    2 | +0.0777/-0.0812/ 24%/94   | +0.0953/-0.0812/ 32%/44
    2.0     inf True None None | +0.0753/-0.0609/ 35%/137  | +0.0906/-0.0295/ 45%/64
    0.5     inf True None None | +0.0731/-0.0349/ 41%/239  | +0.0346/-0.0414/ 36%/111
    0.3     inf True None None | +0.0703/-0.0354/ 40%/248  | +0.0322/-0.0448/ 36%/118
    1.0     inf True None None | +0.0682/-0.0435/ 37%/174  | +0.0629/-0.0332/ 43%/77

Stage 2 — tune exit on TRAIN with best selection {'dev_min': 0.1, 'dev_max': 1000000000.0, 'vanilla': True, 'max_cosnipers': None, 'max_creator_launches': 2}:
  searched 1215 exit configs; top 10 on TRAIN with VAL check:
derisk  ride trail   cut  lad  cap |         TRAIN mean/med/win |           VAL mean/med/win/n
  0.30   2.0  0.85  0.80  0.4   20 | +0.1632/-0.0321/ 41% | +0.0516/-0.0543/ 33%/116
  0.30   2.0  0.85  0.85  0.4   20 | +0.1632/-0.0321/ 41% | +0.0516/-0.0543/ 33%/116
  0.30   2.0  0.90  0.80  0.4   38 | +0.1632/-0.0321/ 40% | +0.0486/-0.0543/ 31%/116
  0.30   2.0  0.90  0.85  0.4   38 | +0.1632/-0.0321/ 40% | +0.0486/-0.0543/ 31%/116
  0.30   2.0  0.90  0.80  0.4    8 | +0.1632/-0.0319/ 41% | +0.0530/-0.0511/ 33%/116
  0.30   2.0  0.90  0.85  0.4    8 | +0.1632/-0.0319/ 41% | +0.0530/-0.0511/ 33%/116
  0.30   2.0  0.85  0.80  0.4    8 | +0.1632/-0.0319/ 41% | +0.0530/-0.0511/ 33%/116
  0.30   2.0  0.85  0.85  0.4    8 | +0.1632/-0.0319/ 41% | +0.0530/-0.0511/ 33%/116
  0.30   2.0  0.85  0.92  0.4   20 | +0.1631/-0.0321/ 41% | +0.0516/-0.0543/ 33%/116
  0.30   2.0  0.90  0.92  0.4   38 | +0.1631/-0.0321/ 40% | +0.0486/-0.0543/ 31%/116

## C. BEST train-tuned config, evaluated OUT-OF-SAMPLE on VAL
selection: {'dev_min': 0.1, 'dev_max': 1000000000.0, 'vanilla': True, 'max_cosnipers': None, 'max_creator_launches': 2}
exit: {'derisk_frac': 0.3, 'ride_mult': 2.0, 'trail_frac': 0.85, 'cut_r': 0.8, 'ladder_frac': 0.4, 'cap_slots': 20}
TRAIN  n=242 mean=+0.1632 med=-0.0321 win=41% sd=0.626 sharpe=0.261 tot=+39.50 top5%=70%
VAL    n=116 mean=+0.0516 med=-0.0543 win=33% sd=0.366 sharpe=0.141 tot=+5.98 top5%=134%
  VAL dist R: p10=-0.089 p25=-0.081 p50=-0.054 p75=+0.063 p90=+0.264 p99=+1.743
  VAL SOL @ 2.0 SOL: mean=+0.1031  median=-0.1087
  VAL tail check: mean=+0.0516  drop top1=+0.0369  drop top2=+0.0219  (top1 R=+1.74 top2 R=+1.74)

## D. STRESS TEST — best config on VALIDATION under realistic fill degradation
(ENTRY_MULT = how far ABOVE the create-slot floor we actually fill; real same-slot snipes face co-snipers.)

```
 slip  fee/leg entryMx |    n   mean R   med R  win  drop2 R   SOL@2
 0.08   0.0008     1.0 |  116  +0.0516 -0.0543  33%  +0.0219 +0.1031   # optimistic (report base)
  0.1    0.003     1.0 |  116  +0.0246 -0.0788  28%  -0.0044 +0.0493   # moderate fees
 0.12    0.005    1.05 |  116  -0.0499 -0.1460  21%  -0.0770 -0.0998   # realistic snipe
 0.12    0.008     1.1 |  116  -0.0990 -0.1906  15%  -0.1249 -0.1980   # harsh fills+fees
 0.15     0.01    1.15 |  116  -0.1723 -0.2574   9%  -0.1962 -0.3447   # worst-case
```

## E. HONEST VERDICT

**No robust positive expectancy.**

- BASELINE (current live config: min_dev_buy 0.3, is_snipeable, default ladder) over the unbiased sample
  is a slight net LOSER: mean -0.0045 R, median -0.081 R, win 28%. Most snipes lose ~8%; a few winners
  nearly (not fully) offset. On a 2 SOL size that is ~-0.009 SOL/snipe (break-even to small bleed).
- The grid found a train-tuned config that is positive OUT-OF-SAMPLE ONLY under optimistic fills:
  selection vanilla-only + dev>=0.1 SOL + deny creators with >2 in-window launches; exit derisk 0.30,
  ride 2.0, trail 0.85, cut 0.80, ladder 0.40, cap ~8s. VAL mean +0.052 R (+0.10 SOL @ 2 SOL), median
  STILL NEGATIVE (-0.054), win 33%. It survives dropping the top-2 winners (+0.022 R) so it is not a
  single-moonshot artifact, but it IS tail-dependent (negative median: lose small often, win big rarely).
- It does NOT survive realistic execution. In the stress table above, at 10% slip + 0.003 SOL/leg the
  drop-top-2 expectancy is already negative; at a realistic same-slot fill (12% slip, 0.005 SOL/leg,
  filling just 5% above the create-slot floor because co-snipers bid it) the config is NET NEGATIVE
  (-0.05 R). The entire edge lives in the first ~5-10% of entry price, exactly what we cannot control
  against same-block competition. This is the fill-quality gap RESULTS.md already flagged.

### Real levers the data supports (relative, not absolute, improvements)
1. Tighten the filter to VANILLA-only (skip mayhem / holder_reward / cashback, not just creator-fee).
   Single biggest lift: moves baseline from ~-0.0045 to ~+0.03 R (val) before fills. Our current
   is_snipeable (creator_fee_bps==0 only) is too loose; non-vanilla launches underperform as flips.
2. Deny factory creators (>2 launches in the window): small additional lift.
3. The dev-buy sweet-spot-band hypothesis is NOT supported: no upper bound ranked top; low dev_min
   (0.1-0.5) + vanilla beat any mid-band. Dev-buy size is a weak signal once vanilla is enforced.
4. Exit: smaller first de-risk (0.30) + higher ride trigger (2.0) + bigger ladder chunks (0.40) extracts
   more of the right tail than the current 0.40/1.6/0.30, but only matters if fills are good.

### Confidence & caveats
- Sample: 1140 unbiased create_v2 launches over ~13h (slot window ~24h), discovered via the global
  mint-authority PDA stream (TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM) — a pure, unbiased create feed,
  NOT the target wallet's mints. No survivorship/selection bias.
- Entry fidelity verified: 1140/1141 trajectories reached the create-slot floor; hand-checked entry px
  = dev-buy floor (ratio 0.99 vs first post-create trade).
- Fills modeled as flat % slippage + fixed per-leg fee, no curve-depth/size model. We assume fill at the
  create-slot floor (the optimistic case). Real same-slot fills are worse; the stress test shows the edge
  is gone once that is priced in.
- 258/1141 launches had no post-create trades (dead on arrival); they exit at ~entry (small loss) and are
  correctly kept in the population (not survivorship-filtered).
- Single ~13h market regime, one window. Not lifetime behavior. Train->val mean roughly halved (+0.16 ->
  +0.05), evidence of grid overfit; the validation number is the honest one.

**Bottom line: at honest same-slot fill quality this sniper is break-even-to-negative. The vanilla-only
filter + anti-factory + the tuned ladder make it LESS negative and push it marginally positive only if we
fill within ~5% of the create-slot floor net of fees. Profitability is a FILL-QUALITY problem (win the
same-slot race cheaply), not a filter/ladder-tuning problem.**

# PRE-CREATE signal test — does pre-create setup predict pumps / his picks?

**TL;DR verdict: NO (with one nuance).** The headline hypothesis is not just unsupported, it is
*inverted*: a creator funded in the last minute before creating is the WORST cohort (the cold-rug
signature), not a coordinated-launch tell. The only pre-create feature that is +EV out-of-sample and
survives dropping the tail — **creator funding amount >= 2 SOL (vanilla)** — is **0.82-correlated with the
dev-buy we already read from the create tx**, so it is essentially *not new information* and needs no
pre-create lookup. Funding-recency-alone and shared-funder do **not** survive the OOS split under
realistic fills. The one genuinely useful residual finding is behavioral: the sniper's *selection*
fingerprint includes a pre-create funding profile (new wallet, funded earlier not last-second, with real
SOL, non-serial) — but it maps onto signals we can already read, not a magic predictor.

## Method
- Sample: **1140 unbiased population launches** (pure create feed, 883 with a post-create price series ->
  defined pump outcome) + **395 his picks** (target sniper 4yFAz...). Reused profit_backtest/creates.json
  + trajectories.json (unbiased + outcomes) and last500/his_500.json (+ feat_500.json series).
- For every creator we queried wallet history **strictly before the create slot** (constantk RPC,
  getSignaturesForAddress anchored at the create + scan of the most-recent pre-create txs for a SOL
  inflow). Extracted: funding recency (slots before create), funding amount (SOL), funding source,
  prior-tx count, serial-launch count, and a shared-funder fanout (# distinct creators a source funded).
  Coverage: create anchor found 92.8%, funding inflow found 85.0% of launches.
- Outcomes: pump15 = reached >=1.5x entry, pump20 = >=2.0x; netR = net return/snipe under the
  winner exit (derisk .30 ride 2.0 trail .85 cut .80 ladder .40 cap 20). Two fill regimes: **opt**
  (8% slip / .0008 SOL-leg / fill at floor) and **real** (12% slip / .005 SOL-leg / fill 5% above floor).
- OOS: chronological train/val split at slot 456742465 (same as the profit backtest).
- Baseline (all pop w/ series): pump15=34.9%, pump20=15.4%, netR_opt=+0.030, netR_real=-0.070.

## A. Pre-create feature -> pump outcome (unbiased population)

### CREATOR FUNDING RECENCY (slots before create; 150 slots ~ 1 min) - INVERTED vs hypothesis
```
band                   n    p15%   p20%  netR_opt netR_real
fresh <1min (<150)   263   34.2%  12.5%  -0.0441  -0.1374   <- WORST (cold-rug signature)
1-5min (150-750)     229   29.3%  12.7%  -0.0108  -0.1065
5-30min (750-4500)   170   41.2%  17.6%  +0.1109  +0.0035
30min-2h (4500-18k)   74   44.6%  20.3%  +0.2003  +0.0850   <- BEST
>2h (>=18k)           67   31.3%  20.9%  +0.1609  +0.0494
```
Freshly-funded-right-before-create is the *worst* cohort, not a coordinated-launch tell. Effect is much
sharper among vanilla tokens (see B): fresh<1min vanilla pump15 = 11%. OOS: the 30min-2h band holds
(train 40% -> val 52%); the >2h band degrades (train 37% -> val 16%). Recency is directional but noisy.

### CREATOR FUNDING AMOUNT (SOL of last inflow) - strongest raw signal, but see F
```
band        n    p15%   p20%  netR_opt netR_real     OOS p15 (train->val)
<0.5 SOL  444   32.2%  13.1%  -0.0629  -0.1539        33.5 -> 29.0
0.5-1     105   32.4%  15.2%  +0.0065  -0.0916        32.9 -> 31.4
1-2       129   33.3%  12.4%  +0.0954  -0.0111        32.5 -> 34.6
2-5        82   42.7%  17.1%  +0.1981  +0.0824        39.6 -> 48.3
>=5        43   60.5%  39.5%  +0.6760  +0.5188        56.7 -> 69.2
```
Monotonic and OOS-persistent. BUT it is 0.82-correlated with dev_buy (section F) - largely the same
"committed dev" effect, read from the funding side.

### SHARED-FUNDER FANOUT (# distinct creators the funding source funded) - fails OOS
```
band          n    p15%   p20%  netR_opt netR_real
solo src(1) 728   34.8%  15.1%  +0.0006  -0.0964
shared 2     38   21.1%   0.0%  -0.0513  -0.1439
shared 3-4   13   46.2%  23.1%  +0.1613  +0.0500
shared >=5  104   39.4%  22.1%  +0.2503  +0.1302
```
"Funded by a source that funds many creators" (organized funder / CEX hot wallet) looks +EV on the full
sample, but does NOT survive the split: vanilla+sharedfunder>=5 VAL netR_real = -0.063 (section E). Reject.

### CREATOR PRE-ACTIVITY (prior tx count) - no reliable signal
cold <=2 tx best on full (netR_real +0.067) but degrades OOS (train p15 42% -> val 26%). Not usable alone.

### SERIAL LAUNCHER (# launches by creator in window) - confirms anti-factory
1-launch creators netR_real -0.007 (vanilla +0.042); >5-launch -0.144. Avoid serial/factory creators -
consistent with the profit_backtest anti-factory finding. Weak but correctly-signed.

### MARKET DENSITY (pop creates in preceding 300 slots) - no signal / unmeasurable
The unbiased feed is too sparse (~0-3 creates/300 slots) to proxy true pump.fun congestion. Discard.

## B. Vanilla snipeable subset only (n=374) - what we'd actually buy
The recency effect is cleaner here: fresh<1min pump15 **11%** (netR_real -0.12) vs 30min-2h **42%**
(+0.165) vs >2h 34% (+0.128). Funding-amount effect also sharper (shared>=5 +0.205, fund grows monotone).

## C. His-picks vs population separation - pre-create setup IS part of his selection
```
feature              POP median / mean      HIS median / mean
fund_recency_slots   567  / 12825           2751 / 24706     (he funds earlier, not last-second)
fund_amount          0.33 / 4.12            1.29 / 2.77      (he picks bigger-funded devs)
prior_n (creator tx) 119  / 227             2    / 90        (he picks NEW wallets)
serial_launches      1    / 6.4             1    / 1.9       (he avoids factories)

fresh-funded(<1min)  POP 28.6%   HIS  1.7%   <- he almost never buys last-second-funded creators
cold creator(<=2 tx) POP 19.2%   HIS 52.9%   <- but he prefers brand-new wallets
serial(>1 launch)    POP 49.9%   HIS 33.2%
shared-funder(>=3)   POP 15.3%   HIS 18.5%   (no real separation)
```
His fingerprint: a **brand-new wallet, funded with real SOL (~1.3 SOL median) ~18 min before create,
not funded in the last minute, not a serial factory.** This is the "prepared dev wallet" profile and it
DOES explain part of the off-chain-looking residual - but every discriminating axis maps onto something
we can also read (funding amount ~ dev_buy; recency/serial are cheap avoid-rules), not a hidden coord tell.

## E. Concrete pre-buy rules (unbiased pop, OOS, net R/snipe) - only funding-amount survives
```
rule                                      VAL netR_opt  VAL netR_real  VAL drop-top2 (real)  n(val)
vanilla ALL (baseline)                      +0.038        -0.063          -0.090              117
vanilla + fund>=1 SOL                       +0.138        +0.028          -0.022               61
vanilla + fund>=2 SOL                       +0.272        +0.150          +0.047               28   <- survives
vanilla + recency>=750 (not fresh)          +0.068        -0.035          -0.077               60   fails real fills
vanilla + fund>=1 + recency>=750 + serial<=2 +0.118       +0.010          -0.056               29
vanilla + fund>=2 + recency>=750 + serial<=2 +0.266       +0.145          -0.044               10   n too small
vanilla + sharedfunder>=5                   +0.039        -0.063          -0.100               20   fails OOS
```
Only **vanilla + fund>=2 SOL** is positive out-of-sample under realistic fills AND still positive after
dropping the top-2 winners (VAL drop2 +0.047). Median is still negative (lose small often, win big) and
n(val)=28 is small, so confidence is moderate at best. Everything else is a tail artifact or fails OOS.

## F. Is funding amount actually a NEW (pre-create-only) signal? - mostly no
corr(fund_amount, dev_buy) = 0.82. Within the dev_buy>=1 cohort, extra funding adds little except the
extreme >=5 SOL tail (which is itself ~ a big dev buy):
```
dev>=1 & fund<1   n=49  pump15=49%  netR_real=+0.102
dev>=1 & fund1-2  n=35  pump15=31%  netR_real=-0.024
dev>=1 & fund2-5  n=38  pump15=32%  netR_real=+0.005
dev>=1 & fund>=5  n=25  pump15=64%  netR_real=+0.528
```
Funding amount is largely the dev-buy signal seen from the funding side - and dev_buy is already in the
create tx we parse at detection, synchronously, for free. So the +EV we found needs no pre-create lookup.

## G. Pre-buy knowability
- The only +EV feature (funding amount) ~ dev_buy, which is **already available synchronously in the
  create tx** - no extra RPC, usable at detection.
- The genuinely pre-create-only features (funding recency, shared-funder) require an RPC round-trip at
  detection: getSignaturesForAddress(creator) + 1-N getTransaction to find the inflow. Measured cost
  ~ several hundred ms (14k+ lookups at ~1.4 s each serial in this batch). That is **too slow for the
  same-slot fill the edge depends on** (the profit backtest showed the entire edge lives in filling within
  ~5% of the create-slot floor; a lookup delay forfeits exactly that). And neither of those features is
  +EV OOS anyway. So there is no fast, independent, +EV pre-create signal to act on.

## H. Honest verdict
**NO - pre-create on-chain setup is not a usable, independent +EV pre-buy "genuine launch" predictor.**
1. The coordinated-pre-funding hypothesis is unsupported and inverted: last-minute funding is a mild
   NEGATIVE (rug) signal; coordinated "insiders funded right before" does not show up as a pump tell.
2. The one OOS-robust +EV feature (creator funding >=2 SOL, vanilla: VAL netR_real +0.15, survives
   tail-drop) is 0.82-correlated with dev_buy, i.e. not new information and already readable
   synchronously from the create tx - so it adds ~nothing beyond "vanilla + dev_buy>=2," which the profit
   backtest already had.
3. Funding-recency and shared-funder do not survive the chronological split under realistic fills.
4. Market density is unmeasurable from this feed.
5. Useful residual: the sniper's *selection* correlates with a pre-create funding profile (new wallet,
   funded earlier not last-second, real SOL, non-serial). This partly demystifies the off-chain residual -
   but it reduces to signals we can already read or cheap avoid-rules, not a hidden coordination detector.

### What the data supports doing (relative, not a new edge)
- Keep **vanilla + dev_buy>=~2 SOL** (equivalently fund>=2) - the only OOS-robust selection here; no
  pre-create lookup needed.
- As a cheap *avoid* rule (only if a creator-history lookup is already in the pipeline for other reasons):
  skip creators funded <1 min before create and skip serial (>2-launch) creators. Small, not worth a
  blocking RPC on its own.
- Do not build a pre-create RPC-lookup gate: it is too slow for same-slot fills and the independent
  pre-create features are not +EV OOS. Profitability remains a fill-quality problem, not a signal problem.

Files: /root/precreate/precreate_feat.json (per-launch features+outcomes), precreate_raw.json (raw),
sample.json, extract_precreate.py, analyze_precreate.py, rules.py.

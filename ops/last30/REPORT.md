# Last-30 Landed Trades — How 4yFAz actually made profit
Target: `4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3` (via own program `FCdY3UTqSrbKab7ba3V6LDVSwYue2GD1xyq8tPY6Yr3o` / direct pump buys)
Pure on-chain reconstruction. His 30 most-recent landed buys, window **2026-10-14 18:06 .. 20:05 UTC (1.99 h)**. 30/30 reconstructed, 0 errors.

## Headline verdict
**His profit on these 30 is REGIME/OUTCOME, not a pre-buy filter and not fill quality.**
- Net **+12.335 SOL** over 30 trades, win rate **16/30 = 53%**, mean **+0.411/trade**.
- **98% of the net (+12.08 SOL) came from just 4 trades** — the only 4 tokens that pumped >=2x after his entry. The other 26 trades net **+0.26 SOL** combined; the 19 tokens that peaked <1.2x collectively **lose -1.37**.
- **No pre-buy feature separates his winners from his losers.** The only thing that separates them is the token's post-entry peak — which is not knowable at buy time.
- vs his own 200-trade baseline (exit_study: 59.5% win, +0.1915 mean): win rate here is *lower*, mean PnL *higher* — a textbook fat-tail stretch (he caught a few pumps), not a new edge.

## Per-trade table (most recent first)
D = buy_slot - create_slot; dev = bundled dev-buy SOL in create tx; cu = create had dev priority fee; van = vanilla launch; bun = bundled (jito tip on create/adjacent); cos = co-snipers in create slot; rnk = his rank among external buyers (cross-slot); fill = his_px / create-floor px; peak = token peak mult after his entry; nsel = #sells.

```
 # mint           slot  D   dev  cu van bun cos rnk fill peak nsel     pnl W
 1 4GeVakyp  456964952  0 18.14  y   .   .   3   2 1.13 1.00    1  +0.233 W
 2 72jEHS39  456964914  0  0.99  y   y   y  11   5 1.92 2.33    2  +2.768 W
 3 BqAz4xpn  456964663  0  0.01  y   .   .   2   1 1.00 1.00    8  -0.122 L
 4 GsRoHYCE  456963158  0  0.69  .   .   .   8   3 1.17 1.34    5  +0.674 W
 5 83Qojqre  456963108  0  0.79  y   .   .   1   1 1.00 1.34    1  +0.266 W
 6 EUYymXAp  456960562  0  1.00  y   .   .   7   4 1.67 1.08    1  +0.032 W
 7 zaxa7yFs  456959649  0  0.00  .   y   .   1   1 1.00 1.25    5  +0.211 W
 8 JCSDHbUT  456956416  0  0.10  y   y   .   1   1 1.00 1.53    1  +0.056 W
 9 AGkvDdWm  456955779  0 18.77  .   .   .   1   1 1.00 1.00    8  -0.085 L
10 Ca6UdLPg  456955605  0  0.99  y   .   .   1   1 1.00 1.20    8  +0.047 W
11 ufo5186P  456953978  0  0.79  y   y   .   8   5 1.55 2.80    1  +3.067 W
12 7FhzAZnh  456953357  0  0.65  y   y   y   7   3 1.26 1.27    1  -0.182 L
13 CvBYa2ge  456953306  1     -  .   y   .   -   1 1.00 1.00    1  -0.047 L
14 EgwYSm32  456950148  0  2.96  .   .   y   3   1 1.00 2.01    8  +1.830 W
15 897unEQZ  456949529  1  2.38  .   y   y   0   1 1.00 1.07    1  -0.004 L
16 HaobTY9B  456949471  0  2.27  y   .   .   1   1 1.00 1.00    1  -0.061 L
17 2p4GqsfD  456948795  0  3.02  y   .   .   8   1 1.00 1.20    2  -0.053 L
18 9kpPEyqj  456947000  0  2.49  .   y   y   5   4 1.32 1.05    1  -0.623 L
19 B9XWvCzF  456946648  0  1.47  y   .   .   4   2 1.16 3.79    7  +4.413 W
20 5Eee2rME  456941452  0  0.85  .   .   .   5   4 1.98 1.03    1  -0.136 L
21 4parGevv  456941093  1  0.75  .   y   y   3   6 1.74 1.05    1  -0.154 L
22 3BaF44Vt  456940742  0  0.79  y   .   .   1   1 1.00 1.18    2  +0.031 W
23 6YXkah8x  456940138  0  0.99  y   y   y   7   1 1.00 1.19    3  +0.084 W
24 4bZybHmo  456938983  0  2.49  .   y   y   5   4 1.35 1.04    8  -0.732 L
25 5eanSdPa  456937174  1  0.00  .   .   .   0   1 1.00 1.10    1  -0.058 L
26 2oVqsKMy  456937015  0  2.02  y   .   y   2   2 1.13 1.04    1  -0.090 L
27 4UDA53km  456936635  0  0.00  y   .   .   1   1 1.00 1.00    1  -0.105 L
28 yS5pdmzg  456935343  0  4.94  .   .   y   8   4 1.15 1.10    1  +0.060 W
29 66Z7a5AF  456933825  0  5.04  y   .   .   6   4 1.24 1.62    4  +0.650 W
30 DdZ3omjp  456931898  0 65.84  .   y   .   2   1 1.00 1.17    4  +0.365 W
```
(dev_buy for #1/#9/#30 are create-tx lamport-delta artifacts, not literal 18-66 SOL dev buys; central tendency ~0.99 SOL is the reliable number. #4GeVak peak=1.00 is unreliable — window unreachable, npk=0; a +0.23 winner, immaterial.)

## A. Is there a FILTER common to all/most of the 30?  — NO new one.
| feature | prevalence | filter? |
|---|---|---|
| create-slot entry (D<=1) | **30/30** (D=0: 26, D=1: 4) | structural (he only snipes at create slot) — already known |
| bundled dev buy present | 29/30; >=0.3 SOL 24/30; >=0.5 24/30; >=1.0 14/30; med ~0.99 | near-universal = his known selection; does NOT predict his own win |
| vanilla launch | **12/30** (18 non-vanilla) | NOT a filter — he snipes mostly non-vanilla |
| bundled (jito tip) | 10/30 | not a filter |
| create_cu>0 (dev prio fee) | 17/30 | not a filter (already debunked OOS) |
| co-snipers in create slot | med 3; >=1: 27/29 | contested launches, not his-only |

**None distinguishes winners from losers** (the real alpha test):
```
feature        winners med    losers med
dev_buy             0.99          2.02     (losers had BIGGER dev buys)
create_cu>0         1             0        (weak, noisy; already debunked)
vanilla             0             0
bundled             0             0
cosnipers           3.5           2        (winners slightly MORE contested)
his_rank            1.5           1.0      (losers got the BETTER rank)
fill_ratio          1.06          1.00     (winners paid a WORSE fill)
peak_mult           1.29          1.04     <-- only separator, and it's the OUTCOME
```
Every pre-buy feature is flat or leans the *wrong* way. No new durable pre-buy filter.

## B. FILL explanation — NO.
- Median fill ratio **1.00**, median rank **1**, rank<=3 on **21/30** — he often gets the floor. BUT that is dominated by the 19 non-pumping trades (floor + still lost small).
- On the 4 trades that made 98% of his money he was NOT at the floor: fills 1.00 / 1.16 / **1.55** / **1.92**, ranks 1 / 2 / 5 / 5. He paid a 1.5-1.9x ramp on two and still cleared +3.07 and +2.77 because the token ran 2.8x / 2.3x.
- Winners' median fill (1.06) is *worse* than losers' (1.00). Fill is a minor cost, not the edge.

## C. REGIME explanation — YES, dominant.
- **4/30 tokens peaked >=2x** (B9XWvC 3.79x, ufo518 2.80x, 72jEHS 2.33x, EgwYSm 2.01x) = **+12.08 SOL = 98% of net**.
- Peak dist: med 1.135; >=1.2x 11/30; >=1.5x 6/30; >=2x 4/30; <1.1x 14/30. Most snipes go nowhere (pump.fun base).
- Time: the 4 pumps are spread across the window (not one burst), mildly back-loaded (late-half 10/15 vs early 6/15). Gaps bursty (med 138s, max 1119s).
- Win rate 53% is *below* his 59.5% baseline; mean +0.41 vs +0.19 only because this 2h held a few 2-4x runners = regime/variance, not a sharper filter.

## D. EXIT — consistent with his known ladder; the capture mechanism, not the source.
- Winners: median **2.5 sells**, hold ~20 slots; losers **1 sell**, cut fast (~17 slots). Matches exit_study.
- Big runners = where he laddered hardest: B9XWvC **7 sells** -> +4.41; EgwYSm **8 sells** -> +1.83. Exit converts a pump to realized PnL; it does not create the pump. Nothing anomalous vs his usual ladder.

## E. BOTTOM LINE — decomposition
- **Filter: ~0.** No pre-buy feature separates his winners from losers; several lean the wrong way. Even in-sample they do not predict his own outcomes. No genuinely new, plausibly-durable pre-buy filter.
- **Fill: small negative/neutral.** Floor ~half the time, but won where he paid 1.5-1.9x and lost where he got the floor. A cost item, not alpha.
- **Regime/outcome: dominant.** 98% of net from 4 tokens that pumped 2-4x.
- **Exit: the monetizer.** His scale-out ladder (already characterized, ~copyable) harvests the few pumps.

**Same fill+regime story, plainly: he is not filtering for pumps — on these 30 no feature did. He sprays clean create-slot snipes near the floor, eats ~79% failed/flat, and a handful of fat-tail runners carry the book, harvested by his exit ladder.** The only genuinely-his, copyable levers remain (a) same-slot landing at/near the floor and (b) the exit ladder — NOT any pre-buy selection filter. Nothing here warrants new OOS filter validation.

## Method / caveats
- Last 30 landed buys via wallet sigs, buy = pump-program tx increasing his token balance (discriminator-agnostic). One position per mint, most-recent first.
- PnL = net lamport flow across ALL his trades per mint (buys+sells, fees/tips incl); residual tokens = 0 on all 30.
- Create slot found by paginating the mint's sigs to genesis (fixes prior bug where >1000-sig tokens looked mid-life). Co-sniper/rank parsing includes inner (CPI) instructions — his buys are often CPIs via FCdY.
- Fill: floor = first external buy px in the create slot (cross-slot through his buy slot); his_px = his curve sol/token delta.
- Peak: price = curve |sol delta|/|token delta| over all trades in [buy_slot, min(last_sell, buy_slot+400)], <=70 sampled points, priced off the curve account (not only his own trades).
- One wallet, one 2h window, N=30. Fat-tail by construction; not lifetime.
- Files: /root/last30/{positions,enriched,fill2}.json + collect_last30.py, enrich.py, fill2.py, report.py

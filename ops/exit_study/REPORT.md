# Exit / Ride Mechanics of Sniper 4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3
Pure on-chain reconstruction of the SELL side. No live trading. Entry side already solved.

## Method & sample
- Reused his last 200 landed snipes (/root/snipe_study50/snipes200.json: mint, buy sig, slot, buy_lamports).
- For each: pulled his buy tx (his buys v0, create v1), read his token acct (ATA) = token-balance owner==wallet, bonding curve = the other token-owner / large-lamport-delta acct. px = |SOL delta on curve| / |token delta|.
- Enumerated ALL his trades per mint via getSignaturesForAddress(his ATA) -> every buy+sell he did on that mint. 200/200 reconstructed, 0 errors.
- Price path: getSignaturesForAddress(bonding curve) over [buy_slot .. his last-sell slot], 197/200 mints, 4,751 market trade points, for peak r the market offered. 3 mints missing path (RPC 429); their lifecycle PnL still computed from his own trades.
- Slot ~= 215 ms.

## Headline (reproduces prior study exactly)
- n=200 positions, win rate 59.5% (119W / 81L), mean +0.1915 SOL/snipe, total +38.30 SOL.
- Every position fully exits -- residual tokens = 0 on all 200. No rugs, no stuck/unexitable bags in this window. He always gets out.
- One entry per position (no averaging down). Median 2 sells (winners), 1 sell (losers).

## WINNERS vs LOSERS exit profile (his real trades)

| metric | WINNERS (n=119) | LOSERS (n=81) |
|---|---|---|
| first-sell fraction (median) | 0.30 | 1.00 (dumps whole) |
| first-sell timing (median slots after buy) | 1 (~0.2 s) | 10 (~2.2 s) |
| first-sell r (median) | 1.178 | 0.994 |
| # sells (median) | 2 (p75=4, max 10) | 1 (p75=3) |
| last-sell slot delta (median / p75 / p90) | 11 / 31 / 66 | 10 / 33 / - |
| market PEAK r reached (median / p75 / p90) | 1.284 / 1.467 / 2.027 | 1.067 / - / - |
| frac-weighted exit r / peak r (trailing) | 0.919 (p25=0.851) | - |
| frac-weighted exit r (the cut level) | - | 0.992 (p10=0.861) |
| realized PnL (median) | +0.219 | -0.114 |

De-risk: his universal move is to sell ~30% almost instantly. Winners do it at slot+1 at r~1.18 (they wait the 1 slot to see the up-tick); losers hold ~10 slots then dump the whole thing at ~break-even.

Scale-out ladder (share of all tokens sold, by r bucket):
```
r bucket     WINNERS    LOSERS
<0.90          0.5%      20.8%
0.90-1.00      3.5%      51.2%
1.00-1.10     30.3%      21.8%
1.10-1.25     38.2%       4.6%
1.25-1.50     16.9%       1.5%
1.50-2.00      7.9%       0.0%
>2.00          2.8%       0.0%
```
Winners dump the bulk (68%) at r 1.0-1.25 and let a tail ride to 1.5-3.3x. Losers dump 72% of tokens at/below break-even (r<1.0). His ladder chunk ~0.15-0.22 of original (~0.22-0.25 of remaining after the 30% de-risk).

The ride: once a position is clearly running he stops laddering and trail-stops the remainder. Winners reach a market peak of ~1.28x median (p90 2.03x, max 3.35x) and he exits the remainder at ~0.92 of the peak (median) -- an effective trailing stop of ~8% off the top. The final sell into the high is small (the 2.8% of tokens sold >2x).

The cut (losers): no deep bag-holding. He exits losers at a weighted r of 0.99 (median) -- flat/break-even -- with the worst decile cut at r~0.86. Effective hard stop ~0.95 combined with a ~2-3 s patience window. Max observed loser hold 188 slots (~40 s) but that is the tail; median loser is gone by slot 10.

## The discretionary edge: he reads the first ~2 s of order flow
Market r at a fixed slot offset strongly predicts ride vs cut:
- r@+5 slots:  WIN median 1.153 vs LOSE 1.050
- r@+10 slots: WIN median 1.142 vs LOSE 0.994
- r@+20 slots: WIN median 1.130 vs LOSE 0.992

Rule "ride if r@+10 >= 1.05, else cut" => 81% accuracy, 84% precision (94/112 accepted are winners). His ride/cut decision is essentially: if follow-on bids push price >5% within ~2 s, ride; otherwise cut flat. This is the one piece that is order-flow-driven rather than a fixed price trigger.

## DERIVED EXIT-LADDER CONFIG (mapped from his measured behavior)

| engine param | value | derived from |
|---|---|---|
| --derisk-frac | 0.30 | his median first-sell fraction (0.30 winners / 0.33 all) |
| --ride-mult   | 1.40 | where he stops laddering and holds the runner (between winner peak median 1.28 and p75 1.47) |
| --trail-frac  | 0.92 | winners exit_r / peak_r median 0.919 (~8% off top) |
| --cut-r       | 0.95 | losers weighted exit ~0.99, hard-stop floor; cut flat, no bag-holding |
| --ladder-frac | 0.25 | his scale-out chunk (~0.22-0.25 of remaining) |
| --exit-cap-ms | 9000 | ~42 slots; covers winners last-sell p75=31 / p90=66 and loser dump by ~slot 10 |

Flags:
```
--derisk-frac 0.30 --ride-mult 1.40 --trail-frac 0.92 --cut-r 0.95 --ladder-frac 0.25 --exit-cap-ms 9000
```

## VALIDATION -- replay this ladder on HIS OWN entries + price paths
Simulator applies the exact snipe_engine.rs exit_ladder state machine to each mint's measured market price path (197 mints with paths), fees modeled per sell leg.

| config | total SOL | mean/pos | win rate |
|---|---|---|---|
| HIS ACTUAL | +38.30 | +0.1915 | 0.595 |
| derived ladder, no latency drag | +42.71 | +0.217 | 0.645 |
| derived ladder, +1% exit slippage | +37.43 | +0.190 | 0.604 |
| derived ladder, +2% exit slippage (realistic) | +32.15 | +0.163 | 0.579 |
| derived ladder, +3% exit slippage | +26.87 | +0.136 | 0.553 |

- Per-position correlation(his, sim) = 0.753; sign agreement (both win or both lose) = 83.8%.
- Examples (sim at +2% slippage):
  - 97QX85B8 his +3.03 / sim +1.96 (derisk 0.30@1.53, trail 0.70@1.20)
  - 2mBKnkQW his +2.22 / sim +1.94 (derisk 0.30@1.15, trail 0.70@1.91)
  - B8RcEHjR his +2.16 / sim +2.00 (derisk 0.30@1.43, trail 0.70@1.85)
  - 9FjQbzeS his +2.05 / sim +0.86 (laddered a chunk at 1.15 then trailed 2.12 -- ladder left money vs his discretionary hold to 2.69 peak)
  - 7SrD3wvg his -0.93 / sim -0.17 (derisk 0.30@1.05 then cut 0.70@0.95 -- ladder cut the loser smaller/faster than he did)

## How much of his profit is mechanically copyable
- ~85-100% is copyable. With no latency drag the mechanical ladder slightly BEATS him (+42.7 vs +38.3); at a realistic +2% exit slippage it does +32.1 (84% of his PnL) at the same win rate. The exit edge is NOT the alpha -- the alpha is the entry selection (already solved) plus the fact he only works clean launches that he can exit.
- The residual ~10-15% gap is discretionary and comes from two things a fixed ladder cannot do:
  1. Order-flow reading on the big runners (e.g. 9FjQbzeS): he holds the tail through dips to a true 2.5-3x peak while a fixed trail-stop clips the remainder on the first 8% pullback. His ride-vs-cut trigger is follow-on bid pressure in the first ~2 s (r@+10>=1.05, 84% precise), not a fixed price.
  2. Exit-fill quality: he lands sells with low latency; a clone eats send-latency slippage (each 1% of exit drag costs ~5 SOL / 0.025 per snipe across the book).
- A static ladder captures the de-risk, scale-out and hard cut cleanly. To close the last gap, add a cheap order-flow gate on the ride leg (arm RIDE only if r>=~1.05 by ~10 slots AND net curve inflow still positive) rather than a pure r>=ride_mult trigger.

## Caveats / sample
- 200 landed snipes, ~38 h window (2026-10-12..14). One wallet, one regime. Not lifetime.
- 3/200 mints have no market price-path (RPC 429) -- per-position PnL from his own trades; excluded only from peak-r/replay (n=197 there).
- px from bonding-curve SOL/token delta; his buy avg-fill is slightly below post-buy spot (convex curve), so r=1.0 is pinned to his fill. Same-slot pre-buy co-sniper trades excluded from the path (not prices the live engine would act on).
- PnL = net lamport flow across all his trades for the mint (fees/tips included); residual value = 0 for all.
- Replay fee model = 1.2%/leg + latency-drag sweep; the +2% row is the recommended planning number.

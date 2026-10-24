# The 1.5 SOL group (BNnN2Mqf, 2pLugeBD, 3GzBLpxT, 7PteyyyR), 2026-10-24, read-only

- **One operator, four wallets.** On 29 of 41 tokens (R2+R3) all four buy in the SAME slot at back-to-back block positions (93/93 gaps = 1). The order is always BNnN > 2pLu > 3GzB > 7Pte; size 1.5 SOL each (sometimes 1 or 2).
- **Exit together.** The first sells land in the same slot in 18 of 22 cases.
- **Not a Jito bundle.** No tip on any of the 99 buys. Each wallet signs and pays for itself, with a huge priority fee: CU price ~120,000,000 µlamports with random last digits, ~0.015 SOL per buy tx. Inference: one app sends the 4 txs at once and the leader orders them by arrival.
- **Programs.** Most buys (97 of 99) go through troyXT7Ty3s2rjJe4bqWaroUrS4Fjd8rbHHNHxcACF4. Off-curve sells go through troyXT / TroYL7 with PumpSwap (pAMMBa), DFlow-like (DF1ow4) and Titan-like (T1TANp) routes. Inference: the Trojan trading bot (vanity "troy" prefix; not confirmed on the web).
- **Copies nobody on chain.** No wallet consistently buys before them. The most common, at 22% of tokens, are busy bots 9pQQc1xy and ssssswdk, ~11–12 s earlier. The trade right before their buy is random and seconds earlier. Inference: an off-chain signal or their own picks.
- **What they buy.** Quiet, older tokens (median 331 s after launch, curve ~37 SOL).
- **Followers.** In the 5 s after the group buys, a median of 14 other buyers put in 4.6 SOL; in 30 s, 12.9 SOL (the group puts in ~6 SOL). This is the bait pattern: 4 "different" buyers make the chart look organic.
- **Payouts.** Small SOL payouts from signer HckQ93Xq via the pump program also go to other wallets on our lists (AwbjKLZP, DEdEW3SM, fRECQzM5). Inference: pump reward/cashback payouts, which link active traders.
- **PnL, last 24 h on chain**, including graduated tokens sold on PumpSwap: 2pLugeBD +1.6 SOL/day, 7PteyyyR −5.5/day. BNnN2Mqf and 3GzBLpxT could not be read (see the next point).
- **Watched by copy bots** (inference). BNnN2Mqf and 4vw54BmA get ~1,000 failed txs every 0.5–2 min from other fee payers, calling programs BevFQ2LKT3riywRANkmWWKE5dksoTkpCtn7B1uzp56A3 and DhpyNWkdxFh3DRPsBrwRwrK3TYC5t7Q4arnSvf3t84HY. One such tx lists both wallets among ~64 accounts. These look like on-chain copy triggers spamming until the watched wallet trades.

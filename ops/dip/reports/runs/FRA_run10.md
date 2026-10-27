# Frankfurt run 10 — dip bot run report

*Exit A/B — Frankfurt: 4 s hold / SL −20% at 0.55 + dev 0.75 (Amsterdam = 1.3 s control); routes v8*

> **Verdict:** Loss (−0.0733 SOL realized over 29 fills). The 4 s hold did better than Amsterdam's 1.3 s per SOL, but small samples. 44 guard fails (cheap, 0.0005 each). One huge dev-list win (9yJrLW +0.274).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.0734 SOL** (wallet 2.7859 → 2.7040, Δ -0.0819) |
| Started (PKT) | 2026-10-24 18:16:51 |
| Ended (PKT) | 2026-10-25 00:14:59 — stopped by the owner at 00:15 (Ctrl+C) to start run 11 with the nonce fan-out |
| Ran for | 5 h 58 min of 480 min planned |
| First / last buy (PKT) | 18:39:51 / 00:10:39 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 73 → **29 filled**, 44 failed on the +5% guard |
| Fill rate | 40% |
| Wins / losses (fills) | 12 / 17 (win rate 41%) |
| Per filled buy | avg -0.0018, median -0.0141 SOL |
| Fills only / failed buys only | -0.0511 / -0.0223 SOL |
| Best / worst trade | 9yJrLW +0.2740 / GsxThS -0.1304 |
| Fill landing | median 37 ms after the dump (seen on our feed); 25 of 29 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip9 |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.55 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.75 SOL |
| exit | take-profit off / stop-loss −20% / time limit 19 slots (~4.0 s) |
| price guard | +5% over the post-dump price (pump error 6042 if exceeded); slot deadline = dump slot + 1 |
| buy fee (priority) | 5M µL/CU × 100k CU limit = 0.0005 SOL per landed buy tx |
| sell fee | 5M µL/CU × 120k CU limit (0.0006 SOL per landed sell tx) |
| route: agave leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: bam leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: default leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: fd leaders | nozomi + landx-fra3 + staked-rpc |
| route: harmonic leaders | nozomi + helius-swqos + landx-fra3 + staked-rpc |
| route: jito leaders | helius + nozomi + jito-bundle + staked-rpc |
| route: other leaders | nozomi + helius-swqos + bolt + staked-rpc |
| sell path | staked-rpc (retry also via nozomi) |
| near-leader gate | 198 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off |
| durable-nonce fan-out | off (one tx to every path, every path's tip in it) |
| backup RPC | RMR_RPC_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 480 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 9**:

| Setting | FRA run 9 | FRA run 10 |
|---|---|---|
| exit | take-profit off / stop-loss −10% / time limit 6 slots (~1.3 s) | take-profit off / stop-loss −20% / time limit 19 slots (~4.0 s) |
| route: jito leaders | helius + nozomi + staked-rpc | helius + nozomi + jito-bundle + staked-rpc |

- Exit: 1.3 s / SL −10% → 4 s (19 slots) / SL −20% (owner A/B).
- Routes v8 on Jito leaders: + jito-bundle (tip 0.001).

## 4. Timeline (PKT)
- **18:16:30** start refused: `Error: keystore: wrong passphrase or damaged file` (nothing sent)
- **18:16:30** first start ended after 8 s; restarted 18:16:40
- **18:16:51** engine start #1 (session with 73 buys)
- **18:39:51** big win: 9yJrLW +0.2740 SOL (time-limit)
- **18:44:53** big loss: 3pQoFA -0.0773 SOL (time-limit)
- **18:50** owner upset at the red failed buys (Solscan): all are the +5% guard (pump 6042), ~0.0005 SOL each; bundle-only and smaller CU rejected (fills use up to 93k CU)
- **19:25:40** big loss: DMG2yC -0.1079 SOL (time-limit)
- **19:50:15** big loss: 2dfqZo -0.0652 SOL (time-limit)
- **20:03:55** big loss: 4j2zFU -0.0535 SOL (time-limit)
- **20:20:16** big win: 3yEGBB +0.1477 SOL (time-limit)
- **21:10:45** big loss: GsxThS -0.1304 SOL (stop-loss)
- **21:19:37** big loss: CcQN8v -0.0931 SOL (time-limit)
- **21:34:12** big loss: 4r3KsK -0.0772 SOL (time-limit)
- **21:57:11** big win: 4bqLVg +0.0886 SOL (time-limit)
- **22:28:42** big win: HT1iHU +0.2325 SOL (time-limit)
- **22:31:27** big loss: BhUEc9 -0.1259 SOL (stop-loss)
- **22:37:28** big loss: G4joZZ -0.0644 SOL (time-limit)
- **22:47:07** big win: 8KifAw +0.0950 SOL (time-limit)
- **22:55** owner OK'd the durable-nonce fan-out build (one tip per landed buy)
- **00:08:03** big loss: 237yvo -0.1114 SOL (stop-loss)
- **~00:10** the owner created 8 nonce accounts during the run (rent ~0.0116 SOL taken from this wallet — explains part of the wallet-vs-trades gap)
- **00:14:59** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 22657 |
| Inside the envelope (age / drop / since-buy / size) | 10707 |
| Picks (score above the threshold) | 283 |
| Skipped | far_leader 189, spacing 19, no_launch_accounts 2 |
| Buys sent | 73 |
| Filled | 29 |
| Failed on the +5% guard | 44 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 29 of 29 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 18:39:51 | [9yJrLW](https://gmgn.ai/sol/token/9yJrLWsEdCBiDJoNm5DP5WK1rV4Zt4BWuC4tgyeP7onn) | 0.75 dev | 0.27 | 1.09 / −6% | 2.8 s | Harmonic `Fd7btg` | filled | **+0.2740** |
| 2 | 18:43:44 | [7gRYtM](https://gmgn.ai/sol/token/7gRYtMX5HRB5UmLKYV5eUA8cystBM7HavDeyowyzVKUE) | 0.75 dev | 0.37 | 2.63 / −15% | 4.9 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 3 | 18:44:53 | [3pQoFA](https://gmgn.ai/sol/token/3pQoFAj9cF95pYVCh47TJHsnGs8toeaKip45DVdbStbS) | 0.55 | 0.33 | 1.53 / −9% | 5.3 s | BAM `LimeA3` | filled | **-0.0773** |
| 4 | 18:54:43 | [AuqgMZ](https://gmgn.ai/sol/token/AuqgMZN2c8CMnm6QWLHkG3aditpoAxiXCqdiuevp2yTi) | 0.75 dev | 1.15 | 3.83 / −21% | 1.9 s | BAM `5marvi` | guard fail | -0.0005 |
| 5 | 19:09:52 | [73ybJ9](https://gmgn.ai/sol/token/73ybJ92a3sLP7GuANQcWzbPLQGTNo7RtZJ6JdaEpBi3W) | 0.75 dev | 1.84 | 4.54 / −24% | 1.3 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 6 | 19:21:13 | [J9rqoR](https://gmgn.ai/sol/token/J9rqoRCS8DcwiBSUqMgwNGQrf4N9tkta7jGL5adDijMa) | 0.75 dev | 1.20 | 3.78 / −21% | 2.5 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 7 | 19:24:09 | [Av5zAP](https://gmgn.ai/sol/token/Av5zAPxA4XnM1UuaBTJkRftynpKnUDodt4MBddnS5Ptw) | 0.75 dev | 0.45 | 2.33 / −13% | 5.3 s | Harmonic `JUPiTE` | filled | **-0.0090** |
| 8 | 19:25:40 | [DMG2yC](https://gmgn.ai/sol/token/DMG2yCbfqyQYbNgUEHWnT2rsguaAJY6bgWPnz2wT5QVS) | 0.75 dev | 0.55 | 4.16 / −22% | 1.9 s | Firedancer `EvnRmn` | filled | **-0.1079** |
| 9 | 19:27:20 | [Accbf1](https://gmgn.ai/sol/token/Accbf1uWNB7MJupwx7YcWKzVHjYRjgHwRBJC2RLh8rwz) | 0.75 dev | 1.26 | 3.66 / −20% | 5.1 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 10 | 19:29:59 | [6uJLG1](https://gmgn.ai/sol/token/6uJLG1hckb83iiJ4sWwk7qqNfLf4yp4GpYxxzpKQpump) | 0.55 | 0.46 | 3.25 / −17% | 3.6 s | BAM `9jxgos` | guard fail | -0.0005 |
| 11 | 19:32:37 | [3CkG8F](https://gmgn.ai/sol/token/3CkG8FVqftf1WXNjJ1DvyNNSh1MrirgBdseasYbiFHnK) | 0.75 dev | 1.56 | 3.71 / −20% | 4.2 s | BAM `G2TBEh` | guard fail | -0.0005 |
| 12 | 19:33:32 | [9MrJk2](https://gmgn.ai/sol/token/9MrJk2YLxoojx3mpAEfXk1n3Gm7YfUzPDhYGXmR3sg1a) | 0.55 | 0.63 | 4.48 / −24% | 2.1 s | Jito `HEL1US` | guard fail | -0.0005 |
| 13 | 19:38:57 | [5C9n5A](https://gmgn.ai/sol/token/5C9n5Arefa7sVANDpzCC5hdUp39sNEe6Eqdt6c45JDPp) | 0.75 dev | 0.40 | 6.57 / −22% | 27.1 s | BAM `G2TBEh` | guard fail | -0.0005 |
| 14 | 19:41:03 | [31NzeW](https://gmgn.ai/sol/token/31NzeWynPeDUfXzYTZrP8Ck7NrnHpJmNaoxRf8eE3g12) | 0.75 dev | 0.31 | 4.24 / −23% | 8.5 s | BAM `BuonuQ` | guard fail | -0.0005 |
| 15 | 19:43:26 | [E4SB4t](https://gmgn.ai/sol/token/E4SB4t79ufFSbETqcAJU8QWdRxVPEos4qefq8byAyZLo) | 0.75 dev | 0.51 | 1.58 / −8% | 2.5 s | Jito `A9mvuk` | guard fail | -0.0005 |
| 16 | 19:43:49 | [8Toe1m](https://gmgn.ai/sol/token/8Toe1mej34mXYERGDohNAWHnxek8FKVxD33f4yVZysPA) | 0.75 dev | 0.98 | 2.35 / −14% | 8.1 s | BAM `9ppJrp` | guard fail | -0.0005 |
| 17 | 19:44:32 | [mhdaBD](https://gmgn.ai/sol/token/mhdaBD711xcoJzpV663i3QnaDnHHMzANgWrqjQbt23S) | 0.75 dev | 0.48 | 3.91 / −21% | 2.8 s | Jito `7RtC1Q` | guard fail | -0.0005 |
| 18 | 19:45:59 | [GhJqiV](https://gmgn.ai/sol/token/GhJqiV6gjghNgZxNR5THeSL2VUZsz2YRTiGUiwGepump) | 0.55 | 1.75 | 3.52 / −17% | 69.3 s | Harmonic `5ZqveV` | filled | **+0.0319** |
| 19 | 19:49:19 | [AqiZrp](https://gmgn.ai/sol/token/AqiZrpHMPHbywA7jD2eMRPU4eTjTmzTSbpAGGS9awTFX) | 0.75 dev | 1.27 | 2.77 / −16% | 7.4 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 20 | 19:50:15 | [2dfqZo](https://gmgn.ai/sol/token/2dfqZohtytRKdcCTojXkxMQ4qaQ9Lv1xbkeAF72dpump) | 0.55 | 0.28 | 2.80 / −14% | 17.4 s | Harmonic `5ZqveV` | filled | **-0.0652** |
| 21 | 19:56:54 | [BJYXKr](https://gmgn.ai/sol/token/BJYXKrVQQgG2mXR6KgKd3NJxZBqBpsvzp7Z2ToFMpump) | 0.55 | 0.52 | 2.12 / −11% | 2.1 s | Jito `8BwBBt` | filled | **-0.0141** |
| 22 | 20:03:55 | [4j2zFU](https://gmgn.ai/sol/token/4j2zFU9kHZPtgtaCk7CrV2AdCeG9M92tv9PsQFKbmmxq) | 0.75 dev | 0.21 | 2.41 / −14% | 5.3 s | Harmonic `5ZqveV` | filled | **-0.0535** |
| 23 | 20:09:32 | [3ASKsS](https://gmgn.ai/sol/token/3ASKsSef2bYsEVK1jwHAT74YTuPx6oNWp5vxboErpump) | 0.55 | 0.28 | 3.78 / −19% | 1.7 s | Harmonic `Fd7btg` | filled | **+0.0120** |
| 24 | 20:20:16 | [3yEGBB](https://gmgn.ai/sol/token/3yEGBBD5fgtMorgYDv5bvtWKnAkkvdJVAx64Kd2tpump) | 0.55 | 0.28 | 3.70 / −16% | 6.4 s | Harmonic `JUPiTE` | filled | **+0.1477** |
| 25 | 20:21:25 | [HviocW](https://gmgn.ai/sol/token/HviocWo7GxsK51d9RUAQdMkjvAYXiNmFG26ByfJCpump) | 0.55 | 0.37 | 1.96 / −7% | 3.8 s | Jito `7RtC1Q` | guard fail | -0.0005 |
| 26 | 20:28:41 | [AGQsio](https://gmgn.ai/sol/token/AGQsioSumcDzrngUe5dNvhuPYARsdJ4UJiSC3byRpump) | 0.55 | 0.24 | 3.03 / −10% | 8.5 s | Jito `HM19KB` | filled | **-0.0049** |
| 27 | 20:31:47 | [52zSqi](https://gmgn.ai/sol/token/52zSqivK5EM4xLRiStgQ6fPGNtEPXC2HEzEJmFuzpump) | 0.55 | 0.32 | 2.12 / −11% | 1.7 s | Harmonic `5ZqveV` | filled | **+0.0092** |
| 28 | 20:41:06 | [2ZxDfX](https://gmgn.ai/sol/token/2ZxDfXakzqhQhCuzBKYMvuQMhKdvLxkFRNrXZLt6pump) | 0.55 | 0.31 | 3.30 / −17% | 3.4 s | Jito `HEL1US` | guard fail | -0.0005 |
| 29 | 21:07:55 | [B8LJEK](https://gmgn.ai/sol/token/B8LJEKRoyEjEmbpCHSh4X4EkT7yvkjMrzJLWcwjUpump) | 0.55 | 1.04 | 3.85 / −14% | 131.0 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 30 | 21:10:45 | [GsxThS](https://gmgn.ai/sol/token/GsxThST5eqnEYKm8TmhSpVbqiw1vAdYETxKwJ3dkpump) | 0.55 | 0.28 | 2.31 / −11% | 3.0 s | Jito `BaDhUB` | filled | **-0.1304** |
| 31 | 21:14:18 | [2quvaC](https://gmgn.ai/sol/token/2quvaCJNkYfh1SD8c7HAAMq51qqNwriN2Lj6yZ4npump) | 0.55 | 0.72 | 5.30 / −22% | 6.4 s | Harmonic `FNKgX9` | guard fail | -0.0005 |
| 32 | 21:15:29 | [2pFWgK](https://gmgn.ai/sol/token/2pFWgKnLGv6F7GRdBmbzRXW6UPPfRE2cnha5L48ypump) | 0.55 | 0.85 | 4.82 / −20% | 19.7 s | Jito `HEL1US` | guard fail | -0.0005 |
| 33 | 21:18:52 | [FPXcFJ](https://gmgn.ai/sol/token/FPXcFJBFx1VV4b8t7J3nxR5buwKqTMjnVNgd3wuW7q5T) | 0.75 dev | 1.29 | 4.46 / −24% | 2.5 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 34 | 21:19:37 | [CcQN8v](https://gmgn.ai/sol/token/CcQN8vNaHojRU219kfNH6wwxbAR8nSBqCBiyjhJTpump) | 0.55 | 0.24 | 2.11 / −8% | 3.4 s | Jito `E1r4Ps` | filled | **-0.0931** |
| 35 | 21:30:36 | [9wgKeh](https://gmgn.ai/sol/token/9wgKeh9umaPpvAXR1DzcnyttcMrBsc8SJcdDPfUYpump) | 0.55 | 0.57 | 4.11 / −15% | 3.4 s | Jito `8gDfqH` | guard fail | -0.0005 |
| 36 | 21:34:12 | [4r3KsK](https://gmgn.ai/sol/token/4r3KsKT9AXoXWToMEQVoC4bXhjmNTrJ96j34BwAWQHb9) | 0.75 dev | 0.65 | 3.60 / −19% | 5.3 s | BAM `1KXvrk` | filled | **-0.0772** |
| 37 | 21:41:27 | [Ba5uvU](https://gmgn.ai/sol/token/Ba5uvUnUFx8CPNd9Gk89HF1k7QbvB1i6rmdfnY1qpump) | 0.55 | 0.41 | 2.80 / −14% | 48.1 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 38 | 21:41:50 | [9p9XvH](https://gmgn.ai/sol/token/9p9XvHxKBq5NNcDbnru5X1Xy4LWbB5zE2k1Vt8pRpump) | 0.55 | 0.47 | 5.77 / −19% | 3.4 s | BAM `9jxgos` | filled | **+0.0326** |
| 39 | 21:42:13 | [HAWDeL](https://gmgn.ai/sol/token/HAWDeLpLEHQvZsrCi5atkkUXKQ3mnRHXWrdb7Q3HgA8C) | 0.75 dev | 0.86 | 4.45 / −24% | 2.5 s | BAM `qZMH9G` | guard fail | -0.0005 |
| 40 | 21:42:19 | [FnBz44](https://gmgn.ai/sol/token/FnBz44W7ZGAZbqYAnUPk3P6A4ErYDNWnv1iPW55vpump) | 0.55 | 1.16 | 4.29 / −19% | 13.6 s | Harmonic `pSo1KZ` | guard fail | -0.0005 |
| 41 | 21:57:11 | [4bqLVg](https://gmgn.ai/sol/token/4bqLVgbi8dRrkYYSbFSqSAETCE8d6m6cLBtoWTNWwx9N) | 0.75 dev | 0.44 | 1.44 / −7% | 4.2 s | Jito `HEL1US` | filled | **+0.0886** |
| 42 | 22:14:01 | [CT2u9m](https://gmgn.ai/sol/token/CT2u9mGtECeuom46KTQSDSmzuvsAEXZCGJ4Ta5jjpump) | 0.55 | 0.46 | 3.45 / −15% | 74.2 s | Harmonic `5ZqveV` | guard fail | -0.0005 |
| 43 | 22:16:56 | [EYkp6m](https://gmgn.ai/sol/token/EYkp6mUHjoSMwEAMjFF4zL6nH3VHNLXUAY1VLGzxx8vo) | 0.55 | 0.21 | 3.53 / −15% | 1.7 s | Rakurai `ana2y2` | guard fail | -0.0005 |
| 44 | 22:20:58 | [8bTZh3](https://gmgn.ai/sol/token/8bTZh3qAg57NKViHaWfNvFQji67ZYUogqSpSn6UMpump) | 0.55 | 0.32 | 1.54 / −7% | 3.8 s | Jito `HEL1US` | guard fail | -0.0005 |
| 45 | 22:21:10 | [5R85Af](https://gmgn.ai/sol/token/5R85Af8VF1h6geSo688Eom14eLo9jJpoustMfvYGo6Nh) | 0.75 dev | 1.55 | 4.42 / −24% | 3.6 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 46 | 22:24:37 | [HT1iHU](https://gmgn.ai/sol/token/HT1iHUfjvgReW4DjY9R8utaQy1sCGUi11nmfwnEkpump) | 0.55 | 0.56 | 3.56 / −12% | 4.7 s | BAM `9jxgos` | filled | **+0.0232** |
| 47 | 22:28:42 | [HT1iHU](https://gmgn.ai/sol/token/HT1iHUfjvgReW4DjY9R8utaQy1sCGUi11nmfwnEkpump) | 0.55 | 0.29 | 4.12 / −20% | 252.3 s | Harmonic `FNKgX9` | filled | **+0.2325** |
| 48 | 22:30:30 | [DvihJS](https://gmgn.ai/sol/token/DvihJSTeqcoq4p8eYqkb3JPGLcE2sp4cbNxaR5bqt8no) | 0.75 dev | 0.81 | 4.19 / −18% | 1.7 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 49 | 22:30:56 | [GSczhd](https://gmgn.ai/sol/token/GSczhdhPV9NCWnjQKoQAeuRFTkEfUpJNtdLzaiX8qGhB) | 0.55 | 0.77 | 4.50 / −21% | 8.1 s | BAM `7VZM7Y` | guard fail | -0.0005 |
| 50 | 22:31:27 | [BhUEc9](https://gmgn.ai/sol/token/BhUEc9B46Sfbz48172UCrx8keJRrjzAZK1ERCpyW2gLX) | 0.75 dev | 0.39 | 2.48 / −12% | 1.5 s | BAM `CMPSSd` | filled | **-0.1259** |
| 51 | 22:32:49 | [vbVL5z](https://gmgn.ai/sol/token/vbVL5ziwf1vmLABCDkQ7y3c1GYFsCbgNUMwLSoSqXfs) | 0.75 dev | 0.88 | 4.45 / −24% | 4.0 s | BAM `CMPSSd` | guard fail | -0.0005 |
| 52 | 22:37:28 | [G4joZZ](https://gmgn.ai/sol/token/G4joZZhM5jeXPxv1JBAufc7YQwbXdwEME7URNcoapump) | 0.55 | 0.33 | 2.09 / −9% | 5.9 s | Harmonic `5ZqveV` | filled | **-0.0644** |
| 53 | 22:47:07 | [8KifAw](https://gmgn.ai/sol/token/8KifAwSGakmDLAyRbTij96gsxbiK1dGCENtX836Xpump) | 0.55 | 0.22 | 3.31 / −15% | 3.8 s | Jito `EUcJwf` | filled | **+0.0950** |
| 54 | 22:54:51 | [FggJtT](https://gmgn.ai/sol/token/FggJtT7nejfKY1MQHMiCNXMQWpjFi4kSFXkS4BeGpump) | 0.55 | 0.31 | 1.20 / −6% | 3.8 s | Jito `HEL1US` | filled | **-0.0355** |
| 55 | 22:55:19 | [BnH2vi](https://gmgn.ai/sol/token/BnH2vic9eJYc3kfmrSkXRuG1couK4fJ8zKuNivgTpump) | 0.55 | 0.37 | 1.49 / −7% | 4.9 s | Rakurai `7PdKhp` | filled | **+0.0371** |
| 56 | 23:06:31 | [CEjhQz](https://gmgn.ai/sol/token/CEjhQzVmG2t6atdEZfFYKGruaZztJXZdxDh8yMqYpump) | 0.55 | 0.42 | 5.15 / −19% | 4.2 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 57 | 23:06:57 | [icFbVj](https://gmgn.ai/sol/token/icFbVjbkALT2fepbgWPGmkuXgcnc579TpXXARdopump) | 0.55 | 0.22 | 4.04 / −14% | 6.2 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 58 | 23:13:33 | [hg6Xcu](https://gmgn.ai/sol/token/hg6Xcu8y1Mmxv7q7uPL5dXKFnmkAF56dYAVfJiwpump) | 0.55 | 0.39 | 3.66 / −11% | 181.9 s | Harmonic `DcTPJq` | guard fail | -0.0005 |
| 59 | 23:13:39 | [hg6Xcu](https://gmgn.ai/sol/token/hg6Xcu8y1Mmxv7q7uPL5dXKFnmkAF56dYAVfJiwpump) | 0.55 | 0.38 | 5.36 / −16% | 188.0 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 60 | 23:22:46 | [9BuQe6](https://gmgn.ai/sol/token/9BuQe6WqdbZZTx4anGvwbTxTb68tMYUrsCYPHsVtpump) | 0.55 | 0.43 | 5.95 / −19% | 8.5 s | Rakurai `7PdKhp` | guard fail | -0.0005 |
| 61 | 23:23:24 | [7ikRmb](https://gmgn.ai/sol/token/7ikRmbRUtn7SWQoG2UXyDFcyDpuKyJBoPuaW79KGpump) | 0.55 | 0.26 | 3.15 / −16% | 2.1 s | Jito `8gDfqH` | guard fail | -0.0005 |
| 62 | 23:34:31 | [EEeM95](https://gmgn.ai/sol/token/EEeM95CgmGTraxJaHLgxALMcLa1zNTxRFit8wAMvRrdE) | 0.75 dev | 0.28 | 3.29 / −16% | 7.4 s | Harmonic `JUPiTE` | filled | **-0.0399** |
| 63 | 23:37:03 | [DqZM5q](https://gmgn.ai/sol/token/DqZM5qPtTF2Bc7XMWx6JnpwUbbvJ7GzUwij8DM68pump) | 0.55 | 0.28 | 2.99 / −12% | 18.7 s | BAM `7y5VhV` | filled | **+0.0415** |
| 64 | 23:40:10 | [G8w8pL](https://gmgn.ai/sol/token/G8w8pL8ysBvNuQnhaRsoDQUY7snPBnHskb6ncv1qtEM8) | 0.75 dev | 0.68 | 4.68 / −23% | 11.7 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 65 | 23:46:45 | [H1q9uz](https://gmgn.ai/sol/token/H1q9uzLvLV59jhquiAVtHaVX2359Pef6TZh6cYBqe9Jt) | 0.75 dev | 0.23 | 5.51 / −24% | 7.6 s | BAM `AiDoLW` | guard fail | -0.0005 |
| 66 | 23:50:07 | [EaH5RF](https://gmgn.ai/sol/token/EaH5RFh5tmN2GVckiYebjvRDxnSGVptCdBdprE7LNMQE) | 0.75 dev | 0.89 | 3.74 / −21% | 5.9 s | Jito `A9mvuk` | guard fail | -0.0005 |
| 67 | 23:54:07 | [g6suz6](https://gmgn.ai/sol/token/g6suz6YWytMJCNgadrMw9jb7oR6uU47UpUMV5Uc1rUw) | 0.75 dev | 0.76 | 3.83 / −21% | 2.5 s | BAM `GFXVa1` | guard fail | -0.0005 |
| 68 | 23:54:18 | [g6suz6](https://gmgn.ai/sol/token/g6suz6YWytMJCNgadrMw9jb7oR6uU47UpUMV5Uc1rUw) | 0.75 dev | 0.64 | 5.01 / −22% | 13.1 s | BAM `9jxgos` | guard fail | -0.0005 |
| 69 | 00:00:44 | [2K7w4Y](https://gmgn.ai/sol/token/2K7w4YpsmuiSb3iLzvB4ttAC8Rutm7VhxacLR1Zgpump) | 0.55 | 0.27 | 4.49 / −20% | 1.9 s | Jito `HEL1US` | guard fail | -0.0005 |
| 70 | 00:02:36 | [EESKwE](https://gmgn.ai/sol/token/EESKwEKy79Bkqagu1guHpLdC6Hukf89FGdrmDvBFpump) | 0.55 | 0.77 | 5.44 / −20% | 56.8 s | Harmonic `TopjgY` | filled | **-0.0344** |
| 71 | 00:05:54 | [DmtjsW](https://gmgn.ai/sol/token/DmtjsWsH1B9GNZaxwPhJtw6prR8Nu5LEqrCB73wEpump) | 0.55 | 0.39 | 5.04 / −17% | 7.4 s | Harmonic `grpton` | guard fail | -0.0005 |
| 72 | 00:08:03 | [237yvo](https://gmgn.ai/sol/token/237yvonkCxG8mJahe9PCGixDzCyHDGyxcp8dHV8C5U8N) | 0.55 | 0.43 | 1.83 / −10% | 5.3 s | Firedancer `EvnRmn` | filled | **-0.1114** |
| 73 | 00:10:39 | [2djKVZ](https://gmgn.ai/sol/token/2djKVZ4ajAsvqohxf7HCZrZj2ZFbABd6Q7oBRm2Lpump) | 0.55 | 0.35 | 3.17 / −13% | 204.4 s | Jito `7RtC1Q` | filled | **-0.0321** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 18 | same | 1 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 4.2 s | 1 | [buy](https://solscan.io/tx/3zY44KwqVLov6R1nPbyx9fEgRArrbnmm9tm78egu44oVdAbM6iahYiyLTmHa3xVu3Zfe7gtAHb2W2ouHyW1T7Gzy) [sell](https://solscan.io/tx/2rsAmPaWAGjRApB1edbPWxuoHcDc3c9X6gsT17kSXww9wkFjw4LLKBEY3sb6sJ8VNHs7m39RjQRqmzqT8ASVmn49) [dump](https://solscan.io/tx/3bxmQWe7FsSUspwU5StYM9sH9yKwaG2vu2pthhCudr575XpEx5dDWnjBa6AYExt43TSnqGsDHmb7jpgt3BwkextB) |
| 2 | 38 | same | 2 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4Z8eDcDgPNJan7PdHVNqM7mXdqDoecnoEfW9r8EMNYmEMpPinjtc6QAZJEvS2rgt9zws8rwZDyU6cgtTvLV8C8Ev) [dump](https://solscan.io/tx/3wiFAhujyDT2JDph6C1ECw1gkSM5b5yK9xiq4KCpVs9rzfxSF9CL2emc4tm3ttRqZ4iNRLgYMsan3XXdRaUr3NRh) |
| 3 | 40 | same | 1 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 4.1 s | 1 | [buy](https://solscan.io/tx/65a6xirru8gKbJVDU9j4qvTyb2zeTxd6pXPvzyB77BFBH59c4Rs4v5LeixQeVBoB6ampGJQCvUHPy6APgSqrAnGW) [sell](https://solscan.io/tx/4A5TZSniDZRqA3Qua86qAY6Hv34ZqoZg2PboHo1w1mGr17X8tbpaCh87VGwnFbwFfKsJmLFMC7yMSUNmFjGbhqY1) [dump](https://solscan.io/tx/5EtnQEJDG9tTEVwZhd2zYaPhgKz51cCoE5Nt3Qt2BtLXcD4T2PvWMaDsVGdkBC6JNS4jLux7U46dfeRxrLqUEJp5) |
| 4 | 24 | same | 4 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4jcPZHKsNvLndh81agkhwy4AMyWiYjhwFHHsQUMwVNLT23MM3WVzLWNgMpiZhAfy8W1CQCPybtUGe7TLoYfG6PWk) [dump](https://solscan.io/tx/3woNEKa7BPSAWFoRxj3HgVqRF1V27Lvpknv5LN9kngbNdR3s3wwzY1HHbvEQfw5weuXFxdTvNQb2zSGsDPqu87iB) |
| 5 | 24 | same | 5 | landx-fra3+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/qLQSbZa32q4oMhHCm2Kfq4J1CFjkq5tTJBo1st334H8Rm7ybb4rUtbudsMqyxk5ndFHGS74rYLUZx14ufQgiG6S) [dump](https://solscan.io/tx/3maHEq7MvQqJrtKFFjpriE8LzJHjCznbrCWatxTHX8PKj4r3BrV7soJ4eySt7GsZoufBQQUjLdE78CyyM4r9PtGg) |
| 6 | 79 | same | 7 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4y7CB1V2yFG8HBgMx9DJZ9s5mNtLae6pRUg3N6vC7YcUEhCz1qaqjugH7RSuvJwqcZg58uovaDDoBCdxeDab2cpJ) [dump](https://solscan.io/tx/v5bNkRHhzWtipjLkt9TD6yW8pA5K38muu3pA4JHxAuPiMR4Ys72iJvPVkCVzDAqzvoMBnTJ4FhJM6qSKkAvMvpU) |
| 7 | 35 | same | 2 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 4.3 s | 1 | [buy](https://solscan.io/tx/5XSoDANyorJBVmzKSE4mw4BRgH3udXQ7cjX4n9MhKoSAKAJ4TkLKMgy1z2i6fvfJMSsgG7998XLEwbFtrHGTJi1M) [sell](https://solscan.io/tx/2zmKCgHSC7Q72NmeyHPahrz17ekwmBYYsNofMbnRkDrrKcvgZTj6FJjwh1uPto1ya8WCTuNH4iomeZhFSp5NxJm7) [dump](https://solscan.io/tx/4YCaAkhpMLnN3Ay4VCCu3kphBAnv91kX9M2iiXbgXwzVkiyNQVzoEFrHE1Z933eGApRXWtjXHjVfyvagaainh9VY) |
| 8 | 152 | +1 | 1 | landx-fra3+nozomi+staked-rpc+helius-swqos | time-limit 4.6 s | 1 | [buy](https://solscan.io/tx/3KFnzhC3GzjUKuxWoEwUjLf8y8BsqzdXkB55PR1Ut6cpTw5ApEZzyaQpDNNqyvAdAKjNKNHJM8vp2M8gbjY8PW1r) [sell](https://solscan.io/tx/3na47EPCWetM2fNQRE8rvGQrwUoC1voitZDkcaUGhtDndowB1BPvTojRL5tF4k1B2kJgsa8HcDroJU9UYXvjApQL) [dump](https://solscan.io/tx/3t4gzRoZUBHSLQBm3NWtvXwgUYSqwgFBGBN6DNvzCefTcnpdjNkn4S4MLhKWXKuSHWYQXE9yF6cowXQQo3RbxuVk) |
| 9 | 107 | same | 2 | landx-fra3+nozomi+staked-rpc+helius-swqos | – | – | [buy](https://solscan.io/tx/4HD15FK96CqHd2yo1qa3FVYBmLvZjePqWAqsQMuxaVaqiwjJauou3voqNgn8dVhs45tbwAgN7BpZzz9qLYcJVFxE) [dump](https://solscan.io/tx/5x4Rfurrk1cnG56VkhaPJ7nS212snTevpAdjqSTnnkZcgTRGdu6Rq81vZetTsozV2moVWb734HT9WqBdW5Cc4Y88) |
| 10 | 31 | same | 3 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/5tnRiBCoJnSim8K9sPjuuEo2knM3AgWSbAG1HFQ1g8mr3rjFScWr88PFkwKkwLayte6gcQo7dzD5izFS13R3yi9D) [dump](https://solscan.io/tx/5hwhm8xdb1a4fQidEnQPo8o9UP6VJs6FqCwqU3VLsxsW7CPvSaBVXp9exCPrEhw2SzHzeA9Z4eFp5h46Pm5tFrdT) |
| 11 | 23 | same | 3 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/3dY76mhQ8ESuN8GfhYTL1HLR1PjaeAsAocLvJfVLidAmne1sAtuibdvAbd54vfKtDfgYT2ThC278vjvHpF8jcc3v) [dump](https://solscan.io/tx/3Yth8sPDV6r1t88VuJxBhAzAuPMD7eAKtZjw218wgtGxsaQ6S2Ur2pEL7dn1su2D5QQTfUhrcX7R1cbE9X8cUHeW) |
| 12 | 89 | same | 2 | landx-fra3+jito-bundle+helius+nozomi+staked-rpc+helius-swqos | – | – | [buy](https://solscan.io/tx/5VFhAR4vwfY8pAmEH1y6aV2wqrkhUB6fGnN9zpTXb2yT1pNnzGupoiayvBoZY3pByT5nkyv71M1hj5NJhFT3hiPe) [dump](https://solscan.io/tx/5NdpMjNNmCEniMRDCdCBquJM3BtM3EkmEzjf27FK7nV8JmyvFJsm69ChrSSpFwAFPyVqLVBmmDzo3ZeY59dhuWg1) |
| 13 | 44 | same | 7 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4t8DkdS2FFLgA1UEC6SdVBLMX53BMRD1Zrehbi2gf3MbwaXDs2vkMwWAPWGMmmGRP9Z2CmfDsWtpkhBKnQeCS5sr) [dump](https://solscan.io/tx/3cbFfBrErV5M5H4RKTEesPnp6AdaL7AYZ87U1rbmDeeBSQ3DUpz7pJm6BQDhTQZP1fSjF7Qf7mTZq6DMogT7SZFR) |
| 14 | 26 | same | 5 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/nGxK52ZzTxK7ibiQqz7r221BdWsoGk6Lr2tA3KXZp7z3KQuwCMnvB34hdiyXkSKgypEN9ZkHnLh53gbDesymGqj) [dump](https://solscan.io/tx/5J7zsjSSA1zqpcv7ueRX2JJLc3SEq2Q4Y8Bjmgs7KGNWnU9WfpxvR7B5CdvhYVr3d4XAQFhsPA2q9KAzjMaTqSDJ) |
| 15 | 23 | same | 3 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4Su9oVJNtrwi7RaKVwx5UZkUynoWeqz6crhhnWpWWB8oY2HGTXpBTemnwvh9nu7VpftqdoSdQggHkrx5zYcX7heR) [dump](https://solscan.io/tx/4vLKdY5DbxQ7EtLmvSDPP4qYiSaccjCbdxHar5zk4NKyeJyqdPGC3RLZ1qm4opLq33PVcnMBvSuiR8P5PRtPq2Ya) |
| 16 | 34 | same | 7 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/55c9X9Brrxd9eLvTbdfnj4Avhat52jt2Fp18dScxwLt6HjhJX7vGmCHWgT19uynmNVcUo1KjXrnEtZDsSDtjPwPA) [dump](https://solscan.io/tx/5UEx1nprZhGQ7oPCbHEe7T8bUKbR1NKavkKuWxhkaCRqS3te39p4K8F7G3stNS5DS5uAQHfyk5cPTXvXG6bGf8vh) |
| 17 | 24 | same | 5 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/53N7WdZb2My5ZRjW9wsCdGRAptBz3YSw4SiXoAcEddeStU3qyJQuoVsv6MUiXma7hwRbwdouahRDfn3Hwmz72436) [dump](https://solscan.io/tx/5qFP9vCySCaAt8DmBn9pMTtdjgrznnUW2QPYjcn7DHQBYsxMyphRufxffmNxVQpVMtfEo72Zj6KfwdCQvLFPZYUq) |
| 18 | 36 | same | 2 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 5.1 s | 1 | [buy](https://solscan.io/tx/4z69knwvzUzQCboBottqraAbuUATBQp9LRZbSUvLz1xyeGWC7WWSRnX4STDXST2X1ktEzYXhNam1XMTtdC69UBqg) [sell](https://solscan.io/tx/aNaBQVEccK3RQedUPdRndrAbtPXtmiw2ZrAwuCBJ8et3xysaHZgLnU6nFVdyWi2x5C39uL2YXCm6japwsNCvURy) [dump](https://solscan.io/tx/4EJBDmzxqXdxi2gdzmtKWugEfN5bAhSps6gWdLSDEajXKS8B8bUEAkiaRY9Mqjb7vRrJa1iVoHQ7RRQNhVRbmLFk) |
| 19 | 43 | same | 2 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/DHvhx9m2E52PVZtxcvRewTWRxM3JKY4wWRidFPD5CdoW2anDm9LJNb8pQBBot9YJ4VDvqRUnsd9cc3FZreLn3Ye) [dump](https://solscan.io/tx/2iLCxUWfpPy6v54wXvmtpNwcd3f6rngJgvC9wRR5o9EyzkqUvVuRjuusJbE7noFHHVx7n4Rwi4kS6UHK6wLi3W6D) |
| 20 | 42 | same | 2 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 4.3 s | 1 | [buy](https://solscan.io/tx/23XshJ1KBNuC1axGoUwWfKJp1dDv5Yof6Ndib2LqFxPB15fCroqRBDMLEX5XjYfQWzBajzj97SDeKQDFutDRVJaG) [sell](https://solscan.io/tx/gE53hvThZ4fXsKdW5DYagt19zFLY8GvNT48S49SjHuRoiFTutMfTc8yBF5RF89a98xgSm5fZBs5zMzRNyPFNjWm) [dump](https://solscan.io/tx/2pW6cpgHdZ3Q68ERb4uG1CdaAR9LEYBKezYfXfK3D6Ri3QPV9xBfX4chTZu3wUc1QFj4w3zJBKRPC5s6GaUhtzXV) |
| 21 | 24 | same | 0 | jito-bundle+helius+nozomi+staked-rpc | time-limit 4.4 s | 1 | [buy](https://solscan.io/tx/5o3BEkgGdo3f2TpfXNmUvqbTLBG32u54HToa6tkropFKts8aXNGCeZwRP5C4Zk6G3WmAv1mcyLAi8jmkpLoGeFiL) [sell](https://solscan.io/tx/Vy7DF8EhRMX3J5u2LyX4XwPkpnfPjwHQvxhxFfWYPnu6mg6kjYHgHVbMFGdpf2LCayWoejz96fgaHmDtwkkBMr6) [dump](https://solscan.io/tx/2RhfRC4yrUL3rwdVvgR4bsybfb8J7bcL3ppUPEVny2sSFzvH76z2cvMNkQZgnrY7xTpneVmUSuRRHQAfQ4sL3Kst) |
| 22 | 38 | same | 1 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 4.3 s | 1 | [buy](https://solscan.io/tx/5k1BGFUaEjPK8uXQU3kPd29EaMJ9WrWiVLb82zD9aMe3XxRkrKmFh7x1PHZGC6hbNqPzo12uMvnyJMcvyJrsruzf) [sell](https://solscan.io/tx/3kSJR2yCeBB9MfYCzzzd1trvjZB6ZVy1W5xy9jwrPHXoaFLNhVvFZrsmgEU3XgCc4Hv1NjG8Hk7EnTLD9fA6b8rm) [dump](https://solscan.io/tx/YxC89JM5RiN8ikQWsmLkDHAWVBwMpokh5ipYXMVeDmitGyuYxo2gq4MMKrUCniZqh7wPEeXbyY11N8ngevpf6CN) |
| 23 | 36 | same | 0 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 4.5 s | 1 | [buy](https://solscan.io/tx/2m6yw5ffNxk265g7BDmmoCtjXj1aTkG679Ctk3scAgKT4CRnQi2wMYrGtiZZ4BdjQ88MKqxaQn3AyRgiJWbAXMuu) [sell](https://solscan.io/tx/k8E65CPcM4Syh3f53RB4wAL7zkPH1EsUd2ztXs7v5vuyGEEy1jN3r4k2pujH4Dzaq1WQTBSJbgMU3A1iyEGDY1w) [dump](https://solscan.io/tx/4brWEnmp9FvJLghjqwjc6EdQzrYyComM79h2jF8BgNtfpL6f1uAv8rFpwtLeEzHo85uheSsdYg1HVQCjAL3Fm8N7) |
| 24 | 26 | same | 1 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 4.2 s | 1 | [buy](https://solscan.io/tx/2tGKkuuM7FBZh5NdqmagJmjAYoueR91ZZE7GmQxgHZT4f7HbtD5W6k92Cp4bZ8HTW5hWtGSEgHZDVWgK9vZzztUA) [sell](https://solscan.io/tx/5voy4SAPaQGoqJcHzaMe7zbbpHFDJ7GKyxBv3iTmLHeTWnkqfhDaFX1qyVnD6KLWfcTfUMYfefsy3v2jfyNmzB4d) [dump](https://solscan.io/tx/5aymMZdViNKNksste4Bps958vYVJPinBQTQM8r3Xe5T1x27qfpsYED9eEu2Kb92mrxPcgkSBQTM6RU3HNEz3WZGK) |
| 25 | 58 | same | 4 | jito-bundle+helius+nozomi+staked-rpc+helius-swqos+bolt | – | – | [buy](https://solscan.io/tx/V61UQ2YJ58xknD3cFa3oyVqhSbhc7QjX7L5vWDjQTS2vW9YcE4cnS1LC5nNpLQq2awq4TUtR3KHNRzpmDD1L6bp) [dump](https://solscan.io/tx/4jdxo9AAviMeS6QH5K7xWNqLSwQR4erqZP4nrcYLJ7UATC1STieKjFxh4sEGnsDAWdQvV7t1uPN4dXpjHRHRzY6f) |
| 26 | 162 | same | 2 | jito-bundle+helius+nozomi+staked-rpc | time-limit 4.8 s | 1 | [buy](https://solscan.io/tx/4yjZz1q7xGdXZWRwCZpHEfi1EoBtRTtYW7YLYniXPwLp3hyakUoBBGkxyLGu5w1KtALDM8jWqV7hsr38R3eiKzPF) [sell](https://solscan.io/tx/4xv4KYTr9UvAPTYEiq6UVtAeZBG6B2qyT9UEDMB2iVK7KBqyCcMwJn7SkgniQyCtkFSdX3FGZfEqHVv8rbgyh6Ae) [dump](https://solscan.io/tx/5EGaFtKD8Ktdh7ci9YLninRJ6PxQ2ZTJUj8bPeoHdPz2utC31rQnwcsG68vHqhCqmHr9fr14i4DPBCNQrXnwJXMe) |
| 27 | 120 | same | 1 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 4.1 s | 1 | [buy](https://solscan.io/tx/5qXmd58iqnRpFzar5vgq1ZuRnbzVNLYGSPQfCRn62YCXcK2YEpTEr9Bedz4xjLCDNwqph6QC3DWMucHuMh321igc) [sell](https://solscan.io/tx/522RCtUfV775KBAw3ooa2iCTFs8Z9vAzJJdgDbbyHHyXjqkUtG9HdHjwTn9e2jGuN3SyAKyKzvk4GuNgHu6pWreg) [dump](https://solscan.io/tx/4hdTsVQEHDxYPF9nzHqPnzKU4muAq3gQN8UerpudB1nhMQbMFomP88mW7xirJq6CDdEzBFEYhhKga9Zqt2ScUvHj) |
| 28 | 94 | same | 4 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4hhdUA8P9wUZDQh54ghRa8JMs1D4Lo4j4ft9aTTkpmaNBtcRxCkovDNppSihXjjbNwMPdozxnDbHzbKq8n3LQ7wt) [dump](https://solscan.io/tx/5Gz7TKcVGxoipWfeV74iM9HW14SLFidiSotxdXEzE1oE2AoJFKMciFcxUE5DzddkJztoczSU4UmEY75bXfC6uzF5) |
| 29 | 64 | same | 5 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/46upyYPG2t1zzkEDq2cQcg6JF7kXSU8CVawXx4LpQKDwDCNvBR5WTWuP2a2EM5L1ZoyGvbZC1J7DeZrpqkMeMYqc) [dump](https://solscan.io/tx/op3DEbwJ7f3m7eg7u54PxAUuGtMy2K5bUFN8bfK7nf1RrGNKANUwX3fTfvW3gWmye8fyek9PtFTMmhLdVYJQmpb) |
| 30 | 16 | same | 1 | jito-bundle+helius+nozomi+staked-rpc | stop-loss 2.7 s | 1 | [buy](https://solscan.io/tx/2LJpbTHP97cEeeDz2hFKxGQGiDyjA1wYhKcdxed4CrWGUgCaL2RakaTqzCWSG1m96pWgTQgdNmDAzFg8yRrUrjAb) [sell](https://solscan.io/tx/2ZFZZ5sT11ayV4kdMpBHac62bNoFpDznAoXWayhW3on5wRgcUv6NfkixfxiT7krW5uV6jYbR1PiYNtLYKyfXTzs7) [dump](https://solscan.io/tx/3cKqKmeEU9pccNKAP2j6UuQpvc4XgWGkHsirXYhsSAvFLbcbA8DTySgqWT4nQ6XmcsUqWL97rajKnSfWYQx8LsEB) |
| 31 | 45 | same | 6 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/BsdScvuuJiRD7ThC61R29r9xAxdRm1ymRYXxj6h4sfK846ZNjfvscmaHpTCm2Q8xQFFwhzCQP64mDsABKaomTRG) [dump](https://solscan.io/tx/TvprCQuFxzir6rX4gLiy1PipeZPfWqRfrQy1ipjL1tpQG1aUpyhysgXjzgHb2v4cekz2pta9nagJH3Yub6wcZzc) |
| 32 | 119 | +1 | 4 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3frCEV7Ph4xi5YAz9webUBxMBXqVEHbtX3LVz5byduqLjJTyXNUnDCWN4AVAfivppULJTny6xH2yXKstfYck7uBn) [dump](https://solscan.io/tx/5URBxQZ3GpvXh9DwEku3HTskW9G2xMwwj89m7px1zgpxMRxkKCkVvFKjJtBs8LB9ThNDPGZ74SF1316wkJD3sCFV) |
| 33 | 129 | +1 | 3 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/5mwKFoSG5anDyZBjngjPAwwWCxgCm9MdeyStMuy5KCHFfVNWCi7VGtsxNxb9HBs656EtHJDEq2SYzNHchdtwUHBF) [dump](https://solscan.io/tx/2YE6AexBQarf2WfMvWrC35V6xtpPYwf86MfmsUt6Un38eKpAi8EgJsF1kS4kg6hAhcGBAxSpc5at4kQef6cNs56N) |
| 34 | 22 | same | 0 | jito-bundle+helius+nozomi+staked-rpc | time-limit 4.2 s | 1 | [buy](https://solscan.io/tx/4JdREcsNYVVMWWpGDuc6rEikc9k9ABoDBZkJPFyG4EAnqJMtr4f48baRTTyEL4XBvrw1kEcS67Q6wxpxg7Px8izN) [sell](https://solscan.io/tx/u5dPHAQKZhLAxPrArH4Hetho7UXfmXHe9KCwLBWivWAw34117riGahLmv5RMJKGKtBpEqKacX26SdB4i4ANNjtX) [dump](https://solscan.io/tx/nd5BgffWUsQkMYvRJCkm5Ac7XBWkKw9To7AFKMLeAXfSwZXeaipL8X5TWwQAbPJsPvCQVNyfGDGiXpoHVypbgFR) |
| 35 | 29 | same | 7 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3ECQzJky62gSVSRL89371pg1uscTqBkJfr7SqPvDMzP5wmQPfbyuaQay3QWf1BArA8nU2WG8HF6eXYPbyZK6ivoo) [dump](https://solscan.io/tx/55YgsefsKTuM4FPNgrr59wGNgZyu7BdzNrnHTx6i1G3wrbDhTgSvVKEyjN2T1WgW46dsPf6FERq3gN5sgTKN8BE3) |
| 36 | 16 | same | 0 | jito-bundle+nozomi+helius-swqos+bolt+staked-rpc+helius | time-limit 4.6 s | 1 | [buy](https://solscan.io/tx/65nu2c2HgXBabeYx2V59QrTGsTXGmeQERR5AyR2Zvpkpa5QLKQ7cgYw8UASMRZ1KUQvqZeqhLPonEhv5J6nScjAm) [sell](https://solscan.io/tx/2iSMYBZZvJ7P9GwSnqwkXPv5aBvzm8dvfDT111FKd1wCq9XzkDCDa7jgzV3o2RbhVtunCiM7rv22aFrFWcWQH6cJ) [dump](https://solscan.io/tx/32utAgRd6Ni9GGjnNFgVJWUi8MkhkhPosEsikrqfnedL4RcjocGQoKfdGHAE8VUWYxHYw6zJhdwBtUnNDE8bngbB) |
| 37 | 22 | same | 3 | landx-fra3+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3i4qNCzYw9DMUSrFPcPFwdJvCQSu6oWDyq2KVcEcz8wFeva1PGhF6FR8MRmsNsoPgCKJJu8wxg49ZYAo27hjgMsi) [dump](https://solscan.io/tx/3BL2PKDstPbiqn6t8oJFY2S4N3fAcTDmACR5mAwohpjFAoUpuzBhGfexSgi6vnxBVD7mJqL3Gm7mSruQaazVUaqe) |
| 38 | 39 | same | 3 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 4.3 s | 1 | [buy](https://solscan.io/tx/aHXbVUx7vfMa6Bdz1fPfp9YdUyBdNZS8w48FAxyqGi4YMoRRJM7LUtm2PeAU6zLJ8nkkRgBpFU6M3devJxSZTpC) [sell](https://solscan.io/tx/5Dd8BUecXmqJU6odd3gZ2sNseqmeSwcE4GJDbTEKEPvQNcbEpCzDEkLMi1fvjPSw2Rm5srVe3uyPWH2YUvhc8as1) [dump](https://solscan.io/tx/2KQtRFRq1cwRcNamk3db4Twkzk4tYhfcoeQbteVT5NeCvydvjxXto3XMEaXa8X5nHZcUde2gvmurkfTN9AUcFrtL) |
| 39 | 75 | +1 | 2 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/3RDQ8hPGTrWbeKkYucD8cnDJr3Cp9HWDpLfU8sX8vJo65D3ygfSHdkvdtMRpoj6bRf7uxffP92s37a5X1ZLXqqTh) [dump](https://solscan.io/tx/21XgeR43t5sh69XpBoRJSYYYY5Vw2jtGYVmdnQxVWr7qG3BZXutfxEWu38MLTQf55uEyZ3QRKRAMMP9NDTLktXN8) |
| 40 | 109 | same | 5 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/414EkUq6D54VWasL9fALNWwwDZBxFfYjbo5p4B37H71QsvrBjw5mP7VfuG8AD14myvm6tXrTgN3ngi1toowmaWfv) [dump](https://solscan.io/tx/38CGX1z3Nta5FzCQBwNjcuxtNvvvPFx4imUjbQMScodhHfCndWudDeUZrRdEacNDrzmJZB24Rm5JdH8d1NWy9z9T) |
| 41 | 19 | same | 0 | jito-bundle+helius+nozomi+staked-rpc | time-limit 5.1 s | 1 | [buy](https://solscan.io/tx/26ZCSuvq7pfLkNqoczAqSjGgAskwE9yXtB8iAwsudzX3PJVMV3ZCNbr5NPxnq9vQWkqqTsnauaC8PCG5BWtLH5Cq) [sell](https://solscan.io/tx/2vErKM6QUoSo18kiXCE3gPhquPL431mVznX7GBf5inKfxabjpSbiUimkEDfmVsf1gDQyBSxVCF8hmtButxD6XwCt) [dump](https://solscan.io/tx/3V4LFSmW6L4Lze2fTzHmVVZdKg8Due3egMThEV6AuYEFYhynqzfLaR3HuLso5GgXrK5wbz4uPr4F5NNdPpYPMzwk) |
| 42 | 32 | same | 2 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/2nobsqUvELKZjJdirnpufRLPQSNRdkHZXvTTfdCyGYxTkLAcm6Kn5Gj3ripqsMD2TsdLWK7xhK5en3ucx18Ke5ax) [dump](https://solscan.io/tx/2FZoTxphGqairqx2MvVuGXbr9SZ2HxX7fVJCj8iinuMhnP1a3nteF4odpKUUXeQJy6VEYdNpyd69v1xKfR6Ltquq) |
| 43 | 191 | +1 | 5 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/5WCVWNgha9LYfhbbmf4PKJ8F26kwz9iBLwcxhHqtPHgF78ZFj6XstRvsQSCfVFZ4HJr3YGnYmgFzEJ229XfPBmtY) [dump](https://solscan.io/tx/3urxEhkw3ewiW3tu2nnXm4QpgePi6uBxHfb6VA7dp3VTsZNEbZ6TR15VwP99WADJwPn9s67Jcb86MaVeaDpkh1dN) |
| 44 | 110 | same | 2 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4c7Dzf1KU6QPZDiw8jqYeD2Pca2iDDoHfmd7yFq6ResqB5FU2PUANoYzp22rmi895hLRBnMjYuwerrvSBUnyaik1) [dump](https://solscan.io/tx/4YmFMkN85W1tuTLfaTVTjiLCYdJABVyDAQ3NGeFf7ac7dob6hLxfEL5GkngxccE4zfNBWJWNL4Q1Cvc6XFCc6df1) |
| 45 | 38 | same | 7 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/bLwbSwp29gNUGGNuFPb5UZDXHU6ZWu6oGk2HVNr96pSGpYXuMNfGG422R3H9xjJnwmwQ7cgdm1qKz3utdJQFEiq) [dump](https://solscan.io/tx/46QucCwct1Yf9ZiCFH87pXE7b1NcFE19d3tmoXYSqMRByhvCckkyFqZ3Kw2b744YhYrW33msyDtPCkBt5GYz2rna) |
| 46 | 26 | same | 0 | jito-bundle+nozomi+helius-swqos+bolt+staked-rpc+helius | time-limit 4.2 s | 1 | [buy](https://solscan.io/tx/56G7tNMXWALbt35tyS3z4rEsjrx9HT4Z9dhmTNCFo6gP7AwiJhXUsajUjaaFrNzYiWkbdEZM8jgxEc8JmiK6XmQh) [sell](https://solscan.io/tx/2kjcsu1JRmSwHiv9E3d28Zq9jWveuvTznHU434RAv21rrF3eBBvkgH53hNDeUooYhoCdhLBQ91kQhWm1khXpA1LZ) [dump](https://solscan.io/tx/5UXYw1by4iBptLQ5UAmmKfz4r7zWFc1d4XLgoknoMVN19uqYMULr87PBNqMMBhPWdfJvqphsZYtBMPFWSU2s5n5d) |
| 47 | 37 | same | 1 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 4.3 s | 1 | [buy](https://solscan.io/tx/TtFSppq3qHAb9o29eaFtFcxRZ5jVa3414AJyJtzjnTmFXTC4UcxpbPsNNjQyLB9SyvoAKNHHARrPud8s6vYJuN3) [sell](https://solscan.io/tx/66eMEWeePWYPxA5Li5u61ZBhCiJA3nCL9vaa1XxLm4d95GGSoE3udNAKkgZ4i4RE1xwTppiNmQF8Z38aiJeF7BgY) [dump](https://solscan.io/tx/5ekdjt3Ezn8tsojvwUPyk3H3x7ca5KK88bHRZYdmZxC7uxkdoGRkCSaL8ixBudqo5HVaYuMPYrLSE9EXMGuiEfkW) |
| 48 | 52 | same | 3 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/2QRT8RVX2inoyZzzt6UBTd5Ue8aqVTXd138fqUYZ4oTXnypFH5c8u7ojZx2U5md3ezwqsy7gbUhKRrV2it5UUJgg) [dump](https://solscan.io/tx/3F1hWiASqZ1VG1wH1E2X3FiLmyGW55zfrr1Yeffnqk86BdVBGdEcE1AHsj3udxZ7o1UYau4sr7XSYBmthqxxybCn) |
| 49 | 22 | same | 4 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/5B7M5KTwvycJQu5xfTqF1FhWWCb4GAjpE8Hk2fXPRs3xfDVgU2pk8NUsdX4Nbea3XcK4PjYjMM4wKrPLdWBWjAke) [dump](https://solscan.io/tx/561GC5xXxBeaaWbfBcRJzKFJUgBjBUEX6n96xWq4JBRhkLDe5sHfXFQ4ES4JEpa6SCvqjQjPnjmaQ4hwviyWR88X) |
| 50 | 22 | same | 1 | nozomi+helius-swqos+bolt+staked-rpc | stop-loss 2.9 s | 1 | [buy](https://solscan.io/tx/AUsezcWFRWy9mCCtrAE91hsvfwhFuYbHuwsS15zEzut6xezskswxGU1CMRfJ4AergXVasJzq8UjBNZfBYjL2Tm9) [sell](https://solscan.io/tx/458N4UktoYJipNM9Qm92QvYmDdbbBQAXxp1xBfdYQFc2PjiYudtvwWZptgwuM4EzWQ3KphdwmjWS4Yk1E7BDKaRh) [dump](https://solscan.io/tx/1Yp3jxW5DsjX2qjEJCMGFkC1FKut7VySEAYcxvUy65TcRgLqHdKazuUgPDevEJj5wmyCs2CRYW1vCZUPgfkmGJ2) |
| 51 | 48 | +1 | 7 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/5PMW8TXCVLxaV4ybyEZHDezfz4koNC1kv2s5cctnvMsxoBVGqQjSsKVWsERQ7oVkVscgEp8PRZTYvszCgV98z8KS) [dump](https://solscan.io/tx/2NzfcvoLh5JafLq5RQFVxuz9tYvopTWdYYLmujuni92SME9yoDr6gwMGv59cQwhun7xDmGHHRG6y8G1NR2n6otcB) |
| 52 | 35 | same | 1 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 4.2 s | 1 | [buy](https://solscan.io/tx/DHAMitzHQ7pv2qAgTyULUzkzL47HbPgmmjaTgMHYSurctQfLcLZorwXPDnuaCRxuAT51BEAVBGUVGRAe1gMwvPE) [sell](https://solscan.io/tx/2DPHuwSFTvaLDA5T4GNr5H3U7hf5wwSuJGhuxb8stsJT4EyTShmsx6DqqZB5nHfcxBfe7oXdGYnw9oSoBQeNgwhJ) [dump](https://solscan.io/tx/3N8YitMMLMNvixxt6aUFNtSvJFRB5rBMLZx4ttqBHVcqcD3Dihb3xJrKuPouq4xpowR4fPmJKdnQUBVTqwvbk97R) |
| 53 | 66 | same | 3 | jito-bundle+helius+nozomi+staked-rpc+helius-swqos+bolt | time-limit 4.4 s | 1 | [buy](https://solscan.io/tx/2n4SWmF1pAzf3E3vByvsGurq5PBuyhgV3S5VsVsJj3L2ZswnJzqG7kVfBxT4U9SmYeCfBXijzF99FVeayqqMb7Ch) [sell](https://solscan.io/tx/hiHZiWjhKxYsivszu2bBn5t2ND9MQQTtgAaqXno9gCbvngAPJhVBX5i4caEaNRyF6aSBEeZi6MymmwjwKTrf95z) [dump](https://solscan.io/tx/2PbLJCzbjmFQbL6hyTcBGptRLd6EoNHgJxa6rfBoVYoXotw3kHzeiqbekYzFsd7ro3apjCKvN1AtYETL9RNpP7WV) |
| 54 | 44 | same | 0 | jito-bundle+helius+nozomi+staked-rpc | time-limit 4.7 s | 1 | [buy](https://solscan.io/tx/3fH3A3tbrPGArMYeG8ZzMqDkjUGTeynraoDXXbsypg2owTxJS78A6x8TCQY2fGtQqp4mtGdZKGhiYq1QbWgRPRPP) [sell](https://solscan.io/tx/3tmaiZmJh1W3q22EL2ZaQ2GaedrrY625ioYmBapggnL5huFwshSbBv1wW4FYhUP9cdKrcM9MXUeA2oE63ULmKgs1) [dump](https://solscan.io/tx/5FoTaBExE1xH5CLCcthc97kCTeTr3vDkX4MywFn9XCxcXJLbJsztNkhCriYXiKHgwKpsy9anBN79x2VQhzR6UvWs) |
| 55 | 218 | +1 | 2 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 4.5 s | 1 | [buy](https://solscan.io/tx/55qsRuBfiFZJ6LWCc3YsUw6ai7nsNWkbFhBSUVo7yvqPkoxvJC2jh96eMJQbwY9dE9DotqSSwV1hZTa8ETpSw6TG) [sell](https://solscan.io/tx/YxEmMkNjqVfHQkJ2AsDWWbRGW2hdAPus4YSHCnS1CUJCrmQmaULcToYbp72CtWEnj6W19TC15SnfpU8BfQ5iQw1) [dump](https://solscan.io/tx/jEAHuU7HrJwohjEpuYUGeR6UvHNFBX5odLCuKK3kx3fsVNAVAMV1pvKkt9VaBZJ6EYdaxnyrWNRmxDt2LG6ed29) |
| 56 | 57 | same | 7 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/5MZkLJsxzjkCVuazhBvTD11gPGgZSGX1vMkapXYvFBPC1dEpX7QkJgSdysFoVicLEgvGdF6MffoXxhYvajHBtG6z) [dump](https://solscan.io/tx/35XNbguMUq9My9ztXqvZWCaMPvx4PeBgNTxPqcEHBW4tHdAe1znXM2xWeJB8WCevEz6YwykiMMN2uc5gxYzSbWYm) |
| 57 | 50 | same | 5 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5k9NxPvXn1vwjtVNjRoLsNu6BwrfJUqiJBCGN2VbvqqQwktG7h2U3HcrEmec5oVtjYkSiaC9BqGAi2iK1MoEeAia) [dump](https://solscan.io/tx/4FFP4skNuC5ozdwFAuN9r3bBayeqLAU6KS16u8LYkJpAfYgV3ekLhqEaWzYevGcyqfinc5s4JY4XXE5eBY6VSQhr) |
| 58 | 36 | same | 11 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4DuPk7aPptwaqX5Czbxkt8zYHBHJYkGRBJbpkomV249qxhmMDS3yUKpDEQWi97qoHrvcf2hGsGDjYtUorpxGGEKy) [dump](https://solscan.io/tx/3fVZstSfLccy9ZMJxuizC3rU9R51RM1nLGwLKiZEUQndCCjY7yRaqfaMwdvMwgKvawprpauPXBv5oKWvWkiTCENx) |
| 59 | 50 | same | 7 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/2m27vYo53TGcpUhwuFcSPXyFMDmAC9HznHaJ8C7aGJUN1wuivHUGco6eSEW7NXvZ629HN1MB1FgLdC39UpBzLmfx) [dump](https://solscan.io/tx/47nroAjEeckttupeh9vwEadW1vbaV3hVr9LyddG97nd4yx2cCVq2fnoEWrj13V5BkkFRN3cygzNkpKucv3TfDdVd) |
| 60 | 224 | +1 | 8 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/3cdanaaRSzbj8U7UBsYDhF94L3h897vXty2jVBufNJm7qfvCXSDoAAtPLv3oJzDX3QZJB8ArvnFgqSUKLAhbVGtT) [dump](https://solscan.io/tx/5fotN5Mt3EpG1qetvjyp8tuvyRZ7sDeb84VAHG8zZieSmQcARtx1oWSPNrQC6Ci99tMS1CC3ZywbreEHnEKifRrF) |
| 61 | 32 | same | 6 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4MaJAkKs1g2Y8ahkeaFgHtas4PEXhTCEGSTW5njcYBiK6NjfrM8xdBbA3KCLXhnc24Grj36tD2LcrjUaHWCfKkCq) [dump](https://solscan.io/tx/48uCupDwfxEhUwTMwmtBMqr3ozQGGivd1s9BTVaG9w91joyzVcezRxEgyQPZ5AyeVSEeRna6n8tHVg9CgYymE1PA) |
| 62 | 45 | +1 | 1 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 4.2 s | 1 | [buy](https://solscan.io/tx/2q1iSZrNXHnWMv5u6eToKLMJHhvoL1d1xu1zRpJSgagdo4Cs3kqu51tFXSNFBu62rjPhGU42MdyHFK9QUsBFS2bi) [sell](https://solscan.io/tx/5q64WEt8m1frJp9CHSXMbp6kYGbGemxmWaPZ3kb1ZP64XWZ4gnmkmhWAoaDxpayfiGHV81buhVk6KEKbjj4K42TA) [dump](https://solscan.io/tx/3xSaj5iJjvQR7z41LPi3bKMv48Kz1dFDZKgwsCBizp7xbCyCKjkasV8k5HwfLHjCjpcPqcUvtpHq1FhmqW3L6miW) |
| 63 | 39 | +1 | 0 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 4.7 s | 1 | [buy](https://solscan.io/tx/49P5k9LFbYF3A3TXHsz8RYDrwVBCyKCGzmD5fLwnDZKEdoqkYurdVbg19Aw2d4WFk6Y8VsnovQrhBJwzmTUpGqtR) [sell](https://solscan.io/tx/4AwFFoKfrz8CZonWqHnKoQR6U5b7VEWJjQ8ZPifZT7VH6dGQDvzLDrsjky1Td8ycmY3Fuxd7U8aTAmMxyFa2hGa8) [dump](https://solscan.io/tx/3qsnFme1ZPgyPhS4CStjCYLSdaV86uKqgiNBXTFRtNpTJxBQthZcS1gpiVtyqKb2A1aWWsxTiJMoqz1BeCFX1nuK) |
| 64 | 52 | same | 6 | jito-bundle+helius+nozomi+staked-rpc+helius-swqos+bolt | – | – | [buy](https://solscan.io/tx/n3yRnh6Abo1SKB1T44Kg6NtK9YJtgQYWjTHUrxLFTv4HnYLVb4a6fHKEWiQgaoYKTVrmBe3pciy64kpeJ5hZfgS) [dump](https://solscan.io/tx/3KWKtPMGjA9GN4NNPZ5tRSRZbb4kebbbvZayr349sB9ksDaMCWQAoBMxS2RCxRniK3C1Azpg2Hru9RzHXWohBoBv) |
| 65 | 39 | same | 6 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/53Ww4mCz4Jpvti9yrLjSoa2TA13MF5hBRm2Yx6BFKeiLzoNTua7nFbYqmYV8xmMBkWbTxTT5czNurFAoLkxapX4X) [dump](https://solscan.io/tx/5Ysy3L6QG6GFJcWVRh11hGRT9ok8Vi8NEvz3NxmjQCQhMF7AAD3T63xDpDdQSQTADpKHAwXAHNaoS5JhQQxjq1B3) |
| 66 | 14 | same | 2 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/2zv5cDxGzGWDdvP4V1QSUCdBUP7N51LnSJoHnvjSAEscUedpApkVTzKPtRzSDhrykthi4jeELEDjSSpA3nX8yF4w) [dump](https://solscan.io/tx/3N2E64aybwuxUWnpgVd7x1zDWYiZbq8uzb8DvEqLeUUj6QjnZYDhC98mqBnGwJgiteWkMGhfaUfWyMNruSKWEhmU) |
| 67 | 24 | same | 5 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/3Uab5qFTE6g6YZXwd5akT1BEcBYq4WXHWMqFwbYdVpsmYbUKAmgxP5N4uFDgXaHvuVpRSJ5nybyW1UqkFXQFzsdn) [dump](https://solscan.io/tx/2EpKxGED9AJFXWPueVh2nb5SKZmyamewDEWKL9LxHVvMRyLjBUUAsFtqNh6WvPSFP5MvJe9gy6yVnnPE5e2NPjRE) |
| 68 | 29 | same | 5 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4B98YNBSYpTgGwNNN12SJgbznhc5tsqe1MK7ayR4Zn8uusMoKZoeKn14ahHMTKQwTFBKnjAAa3GAN4gGgykGPYDw) [dump](https://solscan.io/tx/4HzzjLDaDDYX6sPDcvcNxvZcY9VRAUNmdg1RZuoCFThbFqmNsBYckHqbqWj6nPLgnLETjXzbbzvLnVQXtVTXh1Pr) |
| 69 | 90 | same | 8 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4dq5eSiMhm3Vh1YuAHhtyL7DgANzATybuawh4EKGHMXYUbW4s8zaTpyKgRop9sr7WbZrxsdyYjx6bRkRTb6n4Wqr) [dump](https://solscan.io/tx/wKegEc4msXJ5SRmEzyam4j93q37VjTitPFejMQmz31kEeWQhokprKq2zCBGYZqvpkA4YXCv2dcdaP3DhHxNBuVS) |
| 70 | 135 | same | 6 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 4.5 s | 1 | [buy](https://solscan.io/tx/ohKXJ1FYkG8YRDgQvUXu5a4sFuoeC4wGVTbsgfk55acn2EpnnZdZztKz1DVW3u9rDWyQmA5tSH8aW5YtsPepw1B) [sell](https://solscan.io/tx/2SaiwXBkhzqTuQLDuDyJUNi488gas6C6z3e4edwdfK8MaoWpa21Qr92dkA2mFLnVVAeVNh1wjUokUzXLyAwsRwaW) [dump](https://solscan.io/tx/2EntGryDkpp3zkj7gTXr2xR6eXVLyxy5gg4enVJjPC8q8sqoQzAx4Utsv9doJmhXBU5AVULLesfsrqE1ogPRu5Fi) |
| 71 | 155 | same | 4 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/3LG3MXDMoqTgwo2M33U9v9v6Wdnx1SdWmVMiVNYBk71d82zFE13tMoBddKtFrGHdvc3WPKYasQbo2hEKCGL1TVkh) [dump](https://solscan.io/tx/2LZZ19ePoDhs29aB19Na5fXmgAu8B6eRcEARrhEomSVV3Rh7Nh7mL2uSQkuc1MHTAHHWAVsrW12ZW7j3rjbqFe74) |
| 72 | 17 | same | 0 | landx-fra3+nozomi+staked-rpc | stop-loss 3.6 s | 1 | [buy](https://solscan.io/tx/4FGbsn3Th4ZfJ7A8ZSGQdnKFeHQoDJKN8xAQ7mAXHAJHAFkiCNkzUH78G8nmrRN4adLf1HX23uhFgRKP5sJri4v7) [sell](https://solscan.io/tx/2SXP2C4CqLAwzn4Tj29p7JtKVrSKnT6gDMiDTwaBZ6tKCJWpExRpWguRbxAaT2rmdFKAWG2ke4LC2Y4JWiGqMN4h) [dump](https://solscan.io/tx/5yhaLwLFSkHUi5U28dQbRv4jGsmvLycVhAVWABQ3TtR1G6ZRewkih82J6VPwPKUzFtPqDr511D53gXFL1Hs11w1s) |
| 73 | 41 | same | 1 | jito-bundle+helius+nozomi+staked-rpc | time-limit 4.5 s | 1 | [buy](https://solscan.io/tx/5YnMYa1uQn5oDTyoTDptmEwvX6NoHF5SAjXuhkfeWrshZwb8oX1QLr4Y8qQT9R4cL6T2AitwPezuzMLDeFrvMEvV) [sell](https://solscan.io/tx/4xo3swnuZ6ev6gxszWKNtGxhAqDf1xgztmbVpoFgRCkpdL8mfJQK2Y5AyMzXJkKTzp2zozfibSP1afW6o7FqYjcN) [dump](https://solscan.io/tx/29nKV4PUmgkx7F91FF84EF6SEscKqJc4iUTbYdQhyTyPwvsqVbi8qNK3W2hX7SQthhDgrD9hu1Ap61DvLG8pBEPN) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Harmonic | 24 | 12 | 50% | +0.4348 | +0.0367 | 6/12 |
| Jito | 23 | 8 | 35% | -0.1342 | -0.0158 | 2/8 |
| BAM | 18 | 6 | 33% | -0.1893 | -0.0305 | 3/6 |
| Firedancer | 5 | 2 | 40% | -0.2208 | -0.1096 | 0/2 |
| Rakurai | 3 | 1 | 33% | +0.0361 | +0.0371 | 1/1 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 43 | 21 | 49% | -0.0113 | -0.0000 | 10/21 |
| dev list | 30 | 8 | 27% | -0.0621 | -0.0064 | 2/8 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 63 | 25 | 40% | -0.0011 | +0.0007 | 10/25 |
| next block | 10 | 4 | 40% | -0.0723 | -0.0173 | 2/4 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 18:00 | 4 | 2 | 50% | +0.1957 | +0.0983 | 1/2 |
| 19:00 | 17 | 5 | 29% | -0.1704 | -0.0329 | 1/5 |
| 20:00 | 7 | 5 | 71% | +0.1095 | +0.0221 | 3/5 |
| 21:00 | 13 | 5 | 38% | -0.1836 | -0.0359 | 2/5 |
| 22:00 | 14 | 7 | 50% | +0.1583 | +0.0231 | 4/7 |
| 23:00 | 13 | 2 | 15% | -0.0040 | +0.0008 | 1/2 |
| 00:00 | 5 | 3 | 60% | -0.1789 | -0.0593 | 0/3 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 26 | +0.3166 | +0.0122 | 4.4 s |
| stop-loss | 3 | -0.3677 | -0.1226 | 2.9 s |

## 8. P&L leaders
**Best trades:** 9yJrLW +0.2740 (Harmonic, time-limit, score 0.27); HT1iHU +0.2325 (Harmonic, time-limit, score 0.29); 3yEGBB +0.1477 (Harmonic, time-limit, score 0.28)

**Worst trades:** GsxThS -0.1304 (Jito, stop-loss, score 0.28); BhUEc9 -0.1259 (BAM, stop-loss, score 0.39); 237yvo -0.1114 (Firedancer, stop-loss, score 0.43)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `Fd7btgyS` | HarmonicAgave | 5 | 2 | +0.2844 |
| `FNKgX9dY` | HarmonicAgave | 2 | 1 | +0.2320 |
| `JUPiTERr` | HarmonicFiredancer | 5 | 3 | +0.0978 |
| `EUcJwf7j` | JitoLabs | 1 | 1 | +0.0950 |
| `9jxgosAf` | FireBAM | 4 | 2 | +0.0548 |
| `HEL1USMZ` | JitoLabs | 7 | 2 | +0.0505 |
| `7y5VhV4f` | AgaveBam | 1 | 1 | +0.0415 |
| `7PdKhpKz` | Rakurai | 2 | 1 | +0.0366 |
| `5marvipG` | AgaveBam | 1 | 0 | -0.0005 |
| `BuonuQoA` | AgaveBam | 1 | 0 | -0.0005 |
| `9ppJrpsb` | AgaveBam | 1 | 0 | -0.0005 |
| `C8Bey3LK` | JitoLabs | 1 | 0 | -0.0005 |
| … |  |  |  |  |
| `Awes4Tr6` | HarmonicFiredancer | 2 | 0 | -0.0010 |
| `HM19KBHD` | JitoLabs | 1 | 1 | -0.0049 |
| `8BwBBt23` | JitoLabs | 1 | 1 | -0.0141 |
| `7RtC1Qgi` | JitoLabs | 3 | 1 | -0.0331 |
| `TopjgY7N` | HarmonicFiredancer | 1 | 1 | -0.0344 |
| `1KXvrkPX` | AgaveBam | 1 | 1 | -0.0772 |
| `LimeA3gM` | AgaveBam | 1 | 1 | -0.0773 |
| `E1r4Psq8` | JitoLabs | 4 | 1 | -0.0946 |
| `CMPSSdrT` | AgaveBam | 2 | 1 | -0.1264 |
| `BaDhUB1e` | JitoLabs | 1 | 1 | -0.1304 |
| `5ZqveVff` | HarmonicAgave | 6 | 5 | -0.1424 |
| `EvnRmnMr` | Firedancer | 5 | 2 | -0.2208 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1288 (p25 1112, p75 1576, n 73) |
| Executed-feed lag behind first sighting, ms | 1.4 (p25 0.7, p75 2.8, n 73) |
| Buy sent → our tx seen on the feed, ms | 35.5 (p25 21.7, p75 59.8, n 73) |
| Fills: our buy seen on the feed after the dump, ms | 37 (p25 24, p75 44, n 29) |
| Guard fails: our failed buy seen after the dump, ms | 44 (p25 29, p75 79, n 44) |
| Fills in the dump's own block | 25 of 29 |
| Guard fails in the dump's own block | 38 of 44 |

**Send-path answers (FAST-ACK lines):** nozomi 73 (median ack 0.3 ms), staked-rpc 73 (median ack 3.6 ms), helius-swqos 51 (median ack 0.5 ms, 4 errors, 4×429), helius 25 (median ack 0.6 ms, 2 errors, 2×429), jito-bundle 25 (median ack 0.9 ms), bolt 24 (median ack 0.3 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 5 |
| Guard fails: rival SOL ahead (median) | 2.54 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| haqq (dip bot) | 22 | 20 |
| 6n2cCJrr | 12 | 7 |
| HkQ7 (dip bot) | 12 | 9 |
| 2KtcBC (pre-placed) | 11 | 11 |
| HLU8QbLd (41Pr family) | 11 | 11 |
| 8PgC4ngp | 11 | 8 |
| BfvkhDip | 8 | 8 |
| DF7eRXHn | 7 | 7 |
| CVPz447t (pre-placed) | 6 | 6 |
| 7PedQZmc (untipped fast) | 5 | 5 |
| 5PuQCemC | 5 | 5 |
| 5cbP5Qmj | 4 | 3 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.5246 |
| Pump fee on buys | 0.2167 (0.0075 per fill) |
| Pump fee on sells (residual) | 0.2232 (0.0077 per fill) |
| Buy tx fees (base + priority) | 0.0147 (0.00051 per fill) |
| Buy tips | 0.0746 (0.0026 per fill) |
| Sell tx fees | 0.0175 (0.00061 per fill) |
| Sell tips | 0.0290 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0223 (44 buys) |
| **Result** | **-0.0734** |

Buy compute used (fills): median 75,405 CU, max 84,405 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ start refused: Error: keystore: wrong passphrase or damaged file
- ⚠️ 25 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getLatestBlockhash: 1 timeouts/transport errors (worst p99 848 ms)
- ⚠️ RPC bh-fallback getSlot: 1 timeouts/transport errors (worst p99 854 ms)
- ⚠️ RPC bh-primary getLatestBlockhash: 118 timeouts/transport errors (worst p99 1002 ms)
- ℹ️ RPC exit-fallback getAccountInfo: slow minutes (worst p99 974 ms, max 974 ms)
- ⚠️ RPC ks-primary getBalance: 14 timeouts/transport errors (worst p99 1001 ms)
- ℹ️ send path helius-swqos: 4 × HTTP 429 (rate limited) on buys
- ℹ️ send path helius: 2 × HTTP 429 (rate limited) on buys
- ℹ️ 64 send-path health events (self-heal), e.g. `SEND-PATH rpc bh-primary UNHEALTHY: 3 timeouts / transport errors in a row (getLatestBlockhash): client REBUILT (fresh p`
- ⚠️ big loss 3pQoFA -0.0773 (time-limit, BAM)
- ⚠️ big loss DMG2yC -0.1079 (time-limit, Firedancer)
- ⚠️ big loss 2dfqZo -0.0652 (time-limit, Harmonic)
- ⚠️ big loss 4j2zFU -0.0535 (time-limit, Harmonic)
- ⚠️ big loss GsxThS -0.1304 (stop-loss, Jito)
- ⚠️ big loss CcQN8v -0.0931 (time-limit, Jito)
- ⚠️ big loss 4r3KsK -0.0772 (time-limit, BAM)
- ⚠️ big loss BhUEc9 -0.1259 (stop-loss, BAM)
- ⚠️ big loss G4joZZ -0.0644 (time-limit, Harmonic)
- ⚠️ big loss 237yvo -0.1114 (stop-loss, Firedancer)
- ℹ️ wallet change -0.0819 vs trades -0.0734: gap -0.0085 SOL (transfers / rent / unsold — see notes)
- ℹ️ wallet change includes ~0.0116 SOL of nonce-account rent (refundable), not a trading loss

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED.

## 13. Fixes and follow-ups
**Done after this run:**

- Engine dip10: durable-nonce fan-out (one copy per send path, each with only its own tip; one shared nonce so at most one lands).
- Run script: --nonce FILE; old script kept as run_dip_prod.sh.dip9.
- Studies: dip-detector agent (new P&L model +22 vs +8.8 SOL in replay, Stage A), competitors agent (we lose after sending; Jito leaders worst; BAM/Harmonic order ties by fee).

**Recommended / open:**

- Run 11 = run 10's settings + nonce (one change).

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r10.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r10.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 1.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

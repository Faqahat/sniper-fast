# Amsterdam run 10 — dip bot run report

*Exit A/B control — Amsterdam: 1.3 s / SL −10% at 0.35 + dev 0.55; routes v8*

> **Verdict:** Loss (−0.1384 SOL realized over 30 fills). BAM leaders were the leak (most fills there, mostly losing even though they landed in the dump's block) — later traced to fee ordering inside BAM blocks (inferred).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.1384 SOL** (wallet 1.4434 → 1.2965, Δ -0.1469) |
| Started (PKT) | 2026-10-24 18:17:57 |
| Ended (PKT) | 2026-10-25 00:15:09 — stopped by the owner at 00:15 (Ctrl+C) to start run 11 with the nonce fan-out |
| Ran for | 5 h 57 min of 480 min planned |
| First / last buy (PKT) | 18:25:26 / 00:11:07 |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 56 → **30 filled**, 26 failed on the +5% guard |
| Fill rate | 54% |
| Wins / losses (fills) | 16 / 14 (win rate 53%) |
| Per filled buy | avg -0.0042, median +0.0025 SOL |
| Fills only / failed buys only | -0.1252 / -0.0132 SOL |
| Best / worst trade | J5SxQW +0.0763 / ArWBsC -0.1121 |
| Fill landing | median 29 ms after the dump (seen on our feed); 23 of 30 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip9 |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.55 SOL |
| exit | take-profit off / stop-loss −10% / time limit 6 slots (~1.3 s) |
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
| near-leader gate | 120 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off |
| durable-nonce fan-out | off (one tx to every path, every path's tip in it) |
| backup RPC | RMR_RPC_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 480 min, loss cap 0.443 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 9**:

| Setting | AMS run 9 | AMS run 10 |
|---|---|---|
| route: jito leaders | helius + nozomi + staked-rpc | helius + nozomi + jito-bundle + staked-rpc |
| limits | max 60 fills, 1 open at a time, 480 min, loss cap 0.500 SOL | max 60 fills, 1 open at a time, 480 min, loss cap 0.443 SOL |

- Routes v8 (Jito leaders + jito-bundle at 0.001).

## 4. Timeline (PKT)
- **18:17:57** engine start #1 (session with 56 buys)
- **18:39:55** big win: 9yJrLW +0.0593 SOL (time-limit)
- **18:39:55** 9yJrLW bought here 3.6 s after Frankfurt bought the same token on an earlier dump (different leaders, never the same dump)
- **18:42:37** big win: J5SxQW +0.0572 SOL (time-limit)
- **18:42:48** big win: J5SxQW +0.0763 SOL (time-limit)
- **18:50** owner's Solscan screenshot of this wallet's red failed buys → failed-buy review (all +5% guard, cheap)
- **21:14:29** big win: 3qcqSK +0.0528 SOL (stop-loss)
- **21:16:55** big loss: BiemY3 -0.0738 SOL (stop-loss)
- **22:58:26** big loss: ArWBsC -0.1121 SOL (stop-loss)
- **~00:10** 8 nonce accounts created on this wallet during the run (rent ~0.0116 SOL — part of the wallet-vs-trades gap)
- **00:11:05** big loss: EPEa7b -0.0776 SOL (stop-loss)
- **00:11:07** big loss: CYm1Hg -0.0984 SOL (stop-loss)
- **00:15:09** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 22611 |
| Inside the envelope (age / drop / since-buy / size) | 10683 |
| Picks (score above the threshold) | 283 |
| Skipped | far_leader 206, spacing 19, no_launch_accounts 2 |
| Buys sent | 56 |
| Filled | 30 |
| Failed on the +5% guard | 26 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 30 of 30 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 18:25:26 | [DPuSnf](https://gmgn.ai/sol/token/DPuSnf3tgj9JcH2PHxoJr172grxsA8oEcHS3ArfAhy1a) | 0.55 dev | 0.36 | 5.18 / −27% | 2.3 s | Jito `GnC339` | guard fail | -0.0005 |
| 2 | 18:32:40 | [8cCv3o](https://gmgn.ai/sol/token/8cCv3o4oVTsTioiCtRtDdahVgMeHy9oMLVpo9LCLPABX) | 0.55 dev | 0.74 | 4.48 / −21% | 10.4 s | Jito `GnC339` | guard fail | -0.0005 |
| 3 | 18:38:43 | [fbsPyx](https://gmgn.ai/sol/token/fbsPyxXB4Baj48CkdmVPx8MBxADQoF8nXCyguNxpump) | 0.35 | 0.26 | 3.06 / −13% | 291.9 s | BAM `6WgdYh` | filled | **-0.0023** |
| 4 | 18:39:55 | [9yJrLW](https://gmgn.ai/sol/token/9yJrLWsEdCBiDJoNm5DP5WK1rV4Zt4BWuC4tgyeP7onn) | 0.55 dev | 0.42 | 3.22 / −15% | 6.4 s | Jito `LeDbQ9` | filled | **+0.0593** |
| 5 | 18:42:37 | [J5SxQW](https://gmgn.ai/sol/token/J5SxQWoksHBtuVkKjRu8m6sHxqtcw1F2egjHLCdsB3qG) | 0.55 dev | 0.54 | 1.35 / −7% | 3.2 s | BAM `Aw5wEM` | filled | **+0.0572** |
| 6 | 18:42:48 | [J5SxQW](https://gmgn.ai/sol/token/J5SxQWoksHBtuVkKjRu8m6sHxqtcw1F2egjHLCdsB3qG) | 0.55 dev | 0.25 | 3.55 / −16% | 13.4 s | Jito `icex1C` | filled | **+0.0763** |
| 7 | 18:45:12 | [q2rc3D](https://gmgn.ai/sol/token/q2rc3DCUFxj4PP15wTVYyBymhuXKnsKUJvdoqAzpump) | 0.35 | 0.45 | 2.13 / −11% | 1.5 s | Harmonic `GoeW4a` | filled | **-0.0327** |
| 8 | 18:50:42 | [5JkWRU](https://gmgn.ai/sol/token/5JkWRUBHaB26nh9x2qqgvemvossBqzvJ1qxw4Z6sBuJa) | 0.55 dev | 1.01 | 5.29 / −27% | 1.3 s | Harmonic `HTeRsa` | guard fail | -0.0005 |
| 9 | 19:13:25 | [7xwA1c](https://gmgn.ai/sol/token/7xwA1cCRWX6ZVsBFtCFVJgvdrdxBZYZwGhkuKryppump) | 0.35 | 0.79 | 2.81 / −14% | 9.5 s | Harmonic `3tzpLM` | filled | **+0.0374** |
| 10 | 19:18:26 | [HQPvWy](https://gmgn.ai/sol/token/HQPvWyQJXSWjx3KxDnd4kQhX4GmayyfhSPEJkRA8mikB) | 0.55 dev | 0.96 | 3.14 / −18% | 8.9 s | BAM `7tqeaF` | guard fail | -0.0005 |
| 11 | 19:47:09 | [3TBYys](https://gmgn.ai/sol/token/3TBYysu3BCPp5HG9oxiJ9758VgFRWjTyn8Gr8suRpump) | 0.35 | 0.55 | 5.22 / −20% | 60.2 s | BAM `76rcGH` | filled | **-0.0217** |
| 12 | 19:53:56 | [5WE4sG](https://gmgn.ai/sol/token/5WE4sGiiVf6k1RJ423qJPZbr9vMpaLgRaUaMXsqQpump) | 0.35 | 1.70 | 3.59 / −17% | 82.5 s | Harmonic `A1vqhA` | filled | **+0.0252** |
| 13 | 19:55:01 | [ASQ547](https://gmgn.ai/sol/token/ASQ547s4RzAZftqmwDYnBozRtPPnNTLCexTL63XDpump) | 0.35 | 1.19 | 5.74 / −22% | 8.7 s | Harmonic `GoeW4a` | guard fail | -0.0005 |
| 14 | 20:01:32 | [2bxA5g](https://gmgn.ai/sol/token/2bxA5gc1JssnUruUCPfuE4vqEH9DKCEHVk22Bci6pump) | 0.35 | 0.26 | 3.64 / −13% | 6.6 s | Jito `icex1C` | filled | **+0.0016** |
| 15 | 20:07:36 | [7Q8tE4](https://gmgn.ai/sol/token/7Q8tE4sjj6WCrm13iUGqyXbTNL1hsZALxQu3hj1Ypump) | 0.35 | 0.26 | 3.12 / −16% | 4.2 s | Harmonic `DrifTr` | filled | **+0.0124** |
| 16 | 20:07:45 | [33kwaU](https://gmgn.ai/sol/token/33kwaU8MwnUDsC7fPPSjyhpv3A9DteigPzoE68jyqouY) | 0.55 dev | 0.91 | 4.92 / −25% | 2.8 s | BAM `cybi55` | filled | **+0.0149** |
| 17 | 20:08:42 | [4Qfvov](https://gmgn.ai/sol/token/4QfvovwXa6sVMYXqQuL9wFCH47XJMgsVM47nZcEnpump) | 0.35 | 0.58 | 3.60 / −15% | 1.1 s | BAM `7CR3Jq` | filled | **-0.0175** |
| 18 | 20:12:19 | [AerZ3P](https://gmgn.ai/sol/token/AerZ3PiHodwegS4Y4vDVem8o4wBX4dZNQGpU7U3rpump) | 0.35 | 0.31 | 2.84 / −11% | 1.5 s | Harmonic `DrifTr` | guard fail | -0.0005 |
| 19 | 20:24:37 | [FaqVnx](https://gmgn.ai/sol/token/FaqVnxdAXkwMnFWvPctXpuaAZXtJJnhqnSMGNhnypump) | 0.35 | 0.21 | 2.08 / −10% | 4.2 s | Jito `icex1C` | filled | **+0.0343** |
| 20 | 20:26:25 | [Bx7KvW](https://gmgn.ai/sol/token/Bx7KvW7tDrFQAzYwzMcRGiaxjsL3xd2WLmJEX4vqpump) | 0.35 | 0.79 | 6.06 / −20% | 272.6 s | Harmonic `2mMGsb` | filled | **+0.0044** |
| 21 | 20:43:33 | [3PUat8](https://gmgn.ai/sol/token/3PUat8m4tmqqgtyDirTEMbkkPwvG6a4mSojEtoqtniBB) | 0.55 dev | 0.99 | 5.18 / −27% | 1.9 s | Jito `GnC339` | guard fail | -0.0005 |
| 22 | 20:48:55 | [DqEFHn](https://gmgn.ai/sol/token/DqEFHntB3taDVU77j6kEH8EY9EZ2T6RsGeKZSEmK9Prq) | 0.55 dev | 0.57 | 1.81 / −8% | 2.3 s | Jito `AEHqTB` | filled | **+0.0447** |
| 23 | 20:51:20 | [HW6kpL](https://gmgn.ai/sol/token/HW6kpLdbPCy2DmXNsBKyrTAqNVpd7PV2MdXXkrET4qQb) | 0.55 dev | 0.60 | 2.24 / −10% | 1.9 s | Harmonic `EkvdKh` | filled | **+0.0248** |
| 24 | 21:02:48 | [GDfCeA](https://gmgn.ai/sol/token/GDfCeAZcHK9MsoSHyodRxAvH6w4wVJSpdfx58moXpump) | 0.35 | 0.33 | 3.60 / −13% | 1.3 s | BAM `BUv44c` | guard fail | -0.0005 |
| 25 | 21:05:40 | [BvWHG7](https://gmgn.ai/sol/token/BvWHG7FuA3q9xdZnbAzaydGWbQwyS98qbYVvqE8aGbLR) | 0.55 dev | 1.24 | 12.46 / −49% | 1.3 s | Harmonic `3tzpLM` | guard fail | -0.0005 |
| 26 | 21:10:14 | [6DnbHR](https://gmgn.ai/sol/token/6DnbHRyNPkgcVtRLBYBzav4yo9eQ6UiSqxcKMKWipump) | 0.35 | 0.91 | 3.62 / −19% | 2.1 s | Harmonic `EkvdKh` | filled | **-0.0130** |
| 27 | 21:14:01 | [BP5nHp](https://gmgn.ai/sol/token/BP5nHpBeUooPNuGr4f8FM55xZeAF7KUK4VBEwwCapump) | 0.35 | 0.38 | 1.75 / −6% | 3.4 s | BAM `BUv44c` | filled | **-0.0429** |
| 28 | 21:14:29 | [3qcqSK](https://gmgn.ai/sol/token/3qcqSKnw2aYAT6Txbt6en2wJRTNFycrKvk1qPHQapump) | 0.35 | 0.28 | 3.75 / −13% | 1.3 s | Rakurai `2dfgsi` | filled | **+0.0528** |
| 29 | 21:16:55 | [BiemY3](https://gmgn.ai/sol/token/BiemY32xpH6xuBCPyt46FNydMecCWozydDKRhmpQp1hS) | 0.55 dev | 0.77 | 1.80 / −9% | 1.7 s | BAM `7CR3Jq` | filled | **-0.0738** |
| 30 | 21:17:25 | [HLq7FS](https://gmgn.ai/sol/token/HLq7FSmcyBYZ7V6H8gnXLd7e8qr6u8wCc3h1xYNcpump) | 0.35 | 1.03 | 3.04 / −11% | 7.0 s | BAM `5tfcGy` | guard fail | -0.0005 |
| 31 | 21:18:06 | [Hrd5ou](https://gmgn.ai/sol/token/Hrd5ouaNWevsRzApTZzpkSu6i3UuADvfATjg9Ke2w2Pb) | 0.55 dev | 1.13 | 5.98 / −26% | 9.8 s | BAM `PUmpKi` | guard fail | -0.0005 |
| 32 | 21:24:32 | [FKCvXB](https://gmgn.ai/sol/token/FKCvXB4bijcW5u2dqRczcjSceeyNfC7dyosTxuhvbX9x) | 0.55 dev | 0.50 | 14.19 / −52% | 4.7 s | BAM `GBQ2Gv` | guard fail | -0.0005 |
| 33 | 21:26:16 | [HHxYuY](https://gmgn.ai/sol/token/HHxYuYmMDbN3mqmPNZEHuuUkp4DgK92TCw4ssvtxqyXC) | 0.55 dev | 0.86 | 3.64 / −20% | 1.9 s | Harmonic `EkvdKh` | guard fail | -0.0005 |
| 34 | 21:28:12 | [GaJ7Ra](https://gmgn.ai/sol/token/GaJ7RayEmLAENRpTJidMCCZ26MSsKqhsfLqnijJZpump) | 0.35 | 0.90 | 4.87 / −21% | 8.5 s | BAM `Aw5wEM` | guard fail | -0.0005 |
| 35 | 21:38:42 | [GGwiF6](https://gmgn.ai/sol/token/GGwiF61n8TbBCSG5TWZv3G289EWcL6JguEWxXbWPBUmF) | 0.55 dev | 1.43 | 4.38 / −24% | 1.7 s | BAM `7tqeaF` | guard fail | -0.0005 |
| 36 | 21:57:31 | [37Ty3X](https://gmgn.ai/sol/token/37Ty3XXKMBUz3rub7tFzW8kESBUiuFg5SW6JuwCA4215) | 0.35 | 0.40 | 1.46 / −8% | 4.0 s | BAM `722RdW` | filled | **-0.0382** |
| 37 | 22:01:46 | [4mzRCQ](https://gmgn.ai/sol/token/4mzRCQvb84Q3CoYoSXgczbTkuTqSkgUdnLoc1WYTwMtd) | 0.55 dev | 0.66 | 1.47 / −7% | 3.4 s | Jito `AEHqTB` | guard fail | -0.0005 |
| 38 | 22:01:48 | [4mzRCQ](https://gmgn.ai/sol/token/4mzRCQvb84Q3CoYoSXgczbTkuTqSkgUdnLoc1WYTwMtd) | 0.55 dev | 0.56 | 3.33 / −15% | 4.9 s | BAM `6aDs9t` | guard fail | -0.0005 |
| 39 | 22:30:39 | [CrSnZn](https://gmgn.ai/sol/token/CrSnZnjfP5Ai4PNLFc3WFpVngVaVvM6LLgsCLkmTpump) | 0.35 | 0.31 | 2.12 / −7% | 2.1 s | BAM `6TkKqq` | filled | **-0.0486** |
| 40 | 22:32:33 | [AzawiR](https://gmgn.ai/sol/token/AzawiRkFJeuKPSuBSi6P6yJ8ozzLp6R6QEe7zG4Zpump) | 0.35 | 0.36 | 3.61 / −13% | 18.0 s | BAM `cybi55` | filled | **+0.0149** |
| 41 | 22:34:59 | [8TSrKU](https://gmgn.ai/sol/token/8TSrKUyMbKhD8PPjAXJ3SoGZxFCAusf6gv8sB5eqpump) | 0.35 | 0.22 | 3.28 / −17% | 3.8 s | BAM `6WgdYh` | guard fail | -0.0005 |
| 42 | 22:47:24 | [A43RQh](https://gmgn.ai/sol/token/A43RQhkgoKMSwyCxbgFNNwBL4WSNKwW1DUfrhNYDvTpk) | 0.55 dev | 0.53 | 3.29 / −17% | 5.5 s | BAM `7tqeaF` | filled | **+0.0240** |
| 43 | 22:47:26 | [A43RQh](https://gmgn.ai/sol/token/A43RQhkgoKMSwyCxbgFNNwBL4WSNKwW1DUfrhNYDvTpk) | 0.55 dev | 0.60 | 2.40 / −13% | 7.2 s | Jito `AEHqTB` | guard fail | -0.0005 |
| 44 | 22:52:18 | [pgHbEP](https://gmgn.ai/sol/token/pgHbEPhR1FEyQG4pXavHXkWXgzyKj4wFhdtRPYMpump) | 0.35 | 0.30 | 3.05 / −15% | 5.5 s | BAM `CoG8d9` | filled | **+0.0035** |
| 45 | 22:58:26 | [ArWBsC](https://gmgn.ai/sol/token/ArWBsCq1qCZAx2UpwTe4cekrYg5vj911pA3ZZTn7pump) | 0.35 | 0.87 | 3.95 / −18% | 12.9 s | BAM `AWcCdY` | filled | **-0.1121** |
| 46 | 23:04:44 | [FN6Kxw](https://gmgn.ai/sol/token/FN6KxwdJ72RwsN43dmJgiDaNgfgRGExQQTAafrbypump) | 0.35 | 0.25 | 3.42 / −15% | 7.8 s | Jito `ACvL73` | guard fail | -0.0005 |
| 47 | 23:05:58 | [7qLou7](https://gmgn.ai/sol/token/7qLou7Ng4fHK5wKRxu99kCw4PgJMJDcgjrBm5CCDpump) | 0.35 | 0.66 | 4.36 / −14% | 1.3 s | BAM `CoG8d9` | guard fail | -0.0005 |
| 48 | 23:19:30 | [FZFeDV](https://gmgn.ai/sol/token/FZFeDVVreaUhd37pYRPBg37SgFsEk3fsmYMT8RUXpump) | 0.35 | 0.66 | 3.07 / −12% | 150.7 s | Jito `AEHqTB` | guard fail | -0.0005 |
| 49 | 23:29:54 | [CeHg2R](https://gmgn.ai/sol/token/CeHg2RTLjBLaWy7n1B1ofyx96DYNPirP2Cf1fVcsSRdb) | 0.55 dev | 0.46 | 3.85 / −14% | 7.4 s | BAM `22rU5y` | guard fail | -0.0005 |
| 50 | 23:40:03 | [G8w8pL](https://gmgn.ai/sol/token/G8w8pL8ysBvNuQnhaRsoDQUY7snPBnHskb6ncv1qtEM8) | 0.55 dev | 0.50 | 3.49 / −16% | 5.1 s | Jito `5pPRHn` | filled | **-0.0204** |
| 51 | 23:45:48 | [8LW2Qh](https://gmgn.ai/sol/token/8LW2Qh76RGjPZgWfPiy9UzrKwsAQkTY1LMYNBuQJpump) | 0.35 | 0.52 | 1.65 / −9% | 3.4 s | Harmonic `XkCriy` | guard fail | -0.0005 |
| 52 | 00:01:26 | [EvH1D2](https://gmgn.ai/sol/token/EvH1D27idtRSDdJofsYFwCFzXB7y5XAMYnH4kG12FxxC) | 0.55 dev | 0.89 | 4.72 / −24% | 2.8 s | BAM `BUv44c` | guard fail | -0.0005 |
| 53 | 00:08:06 | [237yvo](https://gmgn.ai/sol/token/237yvonkCxG8mJahe9PCGixDzCyHDGyxcp8dHV8C5U8N) | 0.35 | 0.33 | 2.31 / −13% | 8.5 s | BAM `GSTamp` | filled | **-0.0138** |
| 54 | 00:11:01 | [EPEa7b](https://gmgn.ai/sol/token/EPEa7b1d9dZMg4Lu4vehpaaqE2QF2tjyAgWTtfyEMMRo) | 0.55 dev | 1.10 | 4.28 / −16% | 15.5 s | BAM `GSTamp` | guard fail | -0.0005 |
| 55 | 00:11:05 | [EPEa7b](https://gmgn.ai/sol/token/EPEa7b1d9dZMg4Lu4vehpaaqE2QF2tjyAgWTtfyEMMRo) | 0.55 dev | 0.74 | 4.69 / −18% | 19.3 s | BAM `22rU5y` | filled | **-0.0776** |
| 56 | 00:11:07 | [CYm1Hg](https://gmgn.ai/sol/token/CYm1Hg6q3zg33WRNw6egczB2XaryusLVSnpzpP2baPFz) | 0.55 dev | 1.05 | 3.21 / −12% | 2.8 s | BAM `6WgdYh` | filled | **-0.0984** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 116 | +1 | 5 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/2vxZjbehPdzh3q3KMG3uQGjijYn3zWx1wzxnczkU1ALpW8zh2q4TumPLppjjiAQixZ51Qbcq1uDEwQNCwzZUYysG) [dump](https://solscan.io/tx/5kVtb7Ngc1FT6CobKG295G5jUxVxABfKx1aNCmjTVfT7BGMyoG39w1FciNj7jsRBYdENPYcBGZbGEbv1XoYy3CyX) |
| 2 | 114 | same | 3 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/5EDznyBv4svUXsy6YCMrmzBSjM2HXEnbg2oTpym18T7pggtpD6H9T8FaNRioit5MP8VssDxq6DRX8TUL1AiRMQnY) [dump](https://solscan.io/tx/4WGUaipZnczyWxr4m7Ka3hiUgDbX5N7uU26xFxzZ2qjRwExp36a5Cd2WrJabZEn9h1mYyPPKusbyaxCfb5f8BT85) |
| 3 | 23 | same | 1 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/2nrjagsA3HvSkW7dLZm36oKGCFAxugXdX8FckPnsGrRztcuAJeH7kTKV9x7qE5sq4kWzeQpwDDpGMGHjVp34yyhm) [sell](https://solscan.io/tx/4Ta9JyNcjZfp5XVxexN6v3QkCpAWyrD7iUUmMMsnysPkYzZfcDUDJhnk4JCufXs8KCoXtVhmNBF2EGU8bDT7hAyp) [dump](https://solscan.io/tx/63vsK2CccgmxZ1o6fSRpfFq9CMZX47qx7ppKDeqQMAoSexpmotg1Q1j8dRC44JNcAQ8mbDRRgNRUqvUaZMdniL3k) |
| 4 | 42 | +1 | 0 | jito-bundle+helius+nozomi+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/2dXWAgAj7rHuyzsKN29ey5rKM8dWbwWxdHcz3S8FZzeSsaoWneKNCbEQ6ZEESenDJKiKCwrGa8Lom49nHCGJUmo8) [sell](https://solscan.io/tx/43jLKQSD5SBf6Z8oF4AQYb1BKZLRvw62t6v6Y35Pp3yx7r1A92S6umLSwR35M49GYuRLkSY76JB1V9oB7BkmYj69) [dump](https://solscan.io/tx/5P5g6bt9w1nXBcTAafkAd1HnGMqxuZgUGBJ37cNyu4TzAkrVk7aQ8oLRaK9pceTpcYfoptPtgfFu2yuHKnetVyhn) |
| 5 | 25 | same | 1 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/5PdiJu1WMWgEo77edhJvX9Y3hQbuU7BaTZCHq1mXuRZWZo9xCdssFpbnYVHndH5yY6DddMqWraJgZbhRcvrk9Y2f) [sell](https://solscan.io/tx/xgKBZfexgjQSHwoDDoCprd81So13UwFYwJkWoWb1MoMUbj7z7Lew6ZTq9iSb9ndDNifWpE5fjCwfx5gp8jiFfws) [dump](https://solscan.io/tx/du7kjjFmJf27RwVUZxM1LqvkGFPjj6cSm7JrrFQ87SBLDCrKiQ89mwAFCgbhKUnnEhcrHrCtRM9VuHrouwD5F9Z) |
| 6 | 47 | +1 | 0 | jito-bundle+helius+nozomi+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/3QZsTbyKB2TYPsFmsaea7mfoHdS5pW6Rwbwy6Acsg2c67HFEpCei4H22jYYmpG8U7rv6EkrFe1DB6Km7QNjSB1Xc) [sell](https://solscan.io/tx/2cFBc44bMupPyAjGTxYxo4JuYwRh1whJer8GNFqwDjJMhHSzhenUnPS1nePGmm9WTKCgXnKfQT5gv2sbiPMqf7pZ) [dump](https://solscan.io/tx/31EbH812CKgQnSb6twkUdNNZG1aG7oUaQJReCs6GajbfvG6ysBii6iFU4ixumR1LdvkbCTc7h2okU6JzZFKGxXek) |
| 7 | 35 | same | 1 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.6 s | 2 | [buy](https://solscan.io/tx/4mSstcU6kKm8LrPyoJnx24v5phB3ywLnJ6Fw8HZ5YcJffDQrXjc73qErDdxZh7mbyvpQ4jHFE7Jvo9EUaMzRcCE) [sell1](https://solscan.io/tx/5tFF58ZCw6AgsspsYhN3TfSzdF11W4gm5WGq1VpWCbPr5KirQ4n1NxbNL9njYoxaFxCmBJxebRHr7NZyRoo9jaPJ) [sell2](https://solscan.io/tx/5wwmnbA7CJdwbXTUbNF7oUCWoZYiwU8zqkBNL8tB7bPPc2o3qVxZKiGPHmy6csUcQaL5UWhnss1xs4cjuqPgTPWb) [dump](https://solscan.io/tx/4tmgMwoZfgzGnzpGyZjoi3jEx2Lfivv8u5hzG3i1t69KvcK3HqUGfwrmUVRkZTzPHu43tW9vY3ERWmrQdZ3RgVZ5) |
| 8 | 19 | same | 5 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4v7etvwBC3WanueY9wGdEBh41YdwbXTSB4ES8hfTtCP9vv45iyzGHGfWtY1JADxUBgmxRhfrx7vrPSmqwuEZKFAP) [dump](https://solscan.io/tx/W48QqE7y65EnMy9t88bB1rfMxMkMgzJ98qvg9sW5vHRy1LQUfJz3t9JsgQ2S6mq5KtNw1xmwUDHfYXoPbCh8RWV) |
| 9 | 34 | same | 2 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/jCTs4y9KTwkYDogiVsV6Ct7TGs3Ct8DpbDEL8xUXnE74vgAadrswstmUgGDXnuHgfHtobgg56sSiKSEZqsXyRSU) [sell](https://solscan.io/tx/4ytUpwtGpg6oeEEZyLVpmAAy5y3MzK2qaBcyymTs59UNrGcMRckq1c36XMBwAuSUz4uPqwLsVLXcwGcfBE5G3MUa) [dump](https://solscan.io/tx/4jZAbweXqatiwDod8qtFKqskJanvD2w3JwyzJvNxSaPtFNbLCMrPtyrjKdPoW2CYe7gNkuAxDoadxYQy8rXQCr37) |
| 10 | 20 | same | 1 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4Y6wecWTmRK69AfTUCh5gs8VHMy8FZhuPxMMhXwZyAQWFLNsYLgSJYiN3eoh9iRg3bUWTi1F3Vfa57eEmPsCygdw) [dump](https://solscan.io/tx/3YsGX74Rra1wDLh7b4TATJfQR5tU6Miz6Z1kD952yzkJyK66PsHLf7S1muXrPukAZCAGHd7szYixcrkUZVvuwmzY) |
| 11 | 49 | same | 1 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.9 s | 1 | [buy](https://solscan.io/tx/9d6wuF9DWxWGxgyUqifBcuoRC2iyeuYpjM7S6vSNjC8Ni9KqK6JbZfA58Gb4KQY8nm1wR9FaHFegUgQ6YqtQoa7) [sell](https://solscan.io/tx/2VCG2UZA5sDHN7JPNKTPTYJBYot82zAkxMuUUoonrtAhJR5Gv2CWkgPPggVn6sWCWgj9nDN4hT4ZfF9TxHW7jJce) [dump](https://solscan.io/tx/51cuPNkgmPuTRU82Pageu5C8foj9Ze1bsb3ueRaCDrofmmqUvHv3CuqumeXQLi3dd3xA8uy7E1gWvHvnaRZeXhJE) |
| 12 | 33 | same | 1 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 2.2 s | 1 | [buy](https://solscan.io/tx/3r2VhmAUmhCybogx2NkBAhPaVvmEAa1PBs3jsQwgD63S692ztLztE1cZ9EVTGYtv5ZPeqq4VMHNdzi2rn2SSmp8B) [sell](https://solscan.io/tx/3JWBte1zeU7mwJyd9oPFMDKuDjDMCBYfdwaiykmxtfgxjrWDoTe6fvpgWzjj1Uqg4LvE5icoGc3hXgvc713ZuXii) [dump](https://solscan.io/tx/43wVuibWgJa764VtSqLtUZctmSdPCQUwzPT7HWPMEp6i86KaLej3LEkCXaEXmdgNup2LebtHywfwzGtG3bFkkBXk) |
| 13 | 38 | +1 | 3 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/2qgCHi6ZhtGzhDnAmMRKvs8BcbFaiRZSwaLVB4JU5wL6skyQDEDRAbkamDrg7sSoaQKC7X2AYSg8ZaqxYHEwAwqc) [dump](https://solscan.io/tx/57q6nbH8N39ch8uwJGczpEEdxR9zu17eaqATZTViGXz9EsHHC4uo7gKvv7j7g9JNpzTRkwhKcXxkfUjj8zpzNzzi) |
| 14 | 52 | same | 0 | jito-bundle+helius+nozomi+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/292UR9Focj96C4TjNkKQxRjyuZgUxjwcHTPGyRrLdmCSVEoy2ct8cWx9pRkspJE1C7BKQykVcb4pC4tQJ1NRK861) [sell](https://solscan.io/tx/3ntsBt7kkbv9nnzVLCzbMhNGwhZJGWzxrf7KtuJzV4gnCGKAh73UcusoKJFkTAnnXA3W2QVG6wS7T3ywHxgHXg8j) [dump](https://solscan.io/tx/2f37Leuq5yTtsfQhRLd6zurkCP35qXx9gekAaJoxSq6bSbSgaXCRHR4uESjdYhUGR3i3NMS4AF6MBN8GefHcUjtq) |
| 15 | 20 | same | 1 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/3T7DAsqJ6LykMxVvrb3oUdVgbS21dJ8J53F76tEvxY1ZE1u3apt9QEWVDSUiRLjWYykbCbJDWAFQiSTE92CaZnGa) [sell](https://solscan.io/tx/3UvGKBaR4DabKVpan1nhwu3U1g9PojKk6gBBac8EpnVfDAaCxHwpdpQL9jQbv8m4zEKxZe2g2sNZwWSgr1noRTmc) [dump](https://solscan.io/tx/2VfKB5yB9KM3rphTGBxkcZ5Xv5xQYF6dgot51xN3hyd6YS7dbwmsfQmDiRbMuFJstt3V3eZznUVzY6qDTnLczf37) |
| 16 | 24 | same | 2 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/4USxwck3mxpjuG6d6n8F8Px1omsBJgHz2hY9a9EuQKKCunBSmFXXFamR2wkwMwvyVzBWi9dvWSDhcgnFUiG8JKUp) [sell](https://solscan.io/tx/jZiUWAEAWiULM7mX9AuzzK9qmBeQWfhiHYuTJ9qCij2fEgsSyLHPFx7AyFw6R87xcDiMnVV3PNHfvF89YyzLPRx) [dump](https://solscan.io/tx/34HmkmbqGBGfPpbxg9qjPusR68c8SmPZEsPX9adJVu4kL27rMTcxDpkjLw3Cv2hBgTLXQ3NT3b9NtPehteyeky79) |
| 17 | 24 | same | 1 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/2hARRKVNvY4MEuQBr7zdu68w5YJUDzgdpdWT7e7KwFNjtk4mDXecUG95thiX1oNVEqotMw49qPBDg2L1wvgNES7u) [sell](https://solscan.io/tx/2m8KUm7HuBch3djG9iZLqPpgbLnPVRvEzbsoB2mGMgUjcuBh9mwooeK7ZFLxznLnSyibK6fDtohPphAwKHAx8F9V) [dump](https://solscan.io/tx/No5ijvuy6iBifcAntjqqPrvUexxrBPzGcYpbCsHnz3q53wer3Kw7N31JRdRe2854jfEMuuDkZy1AYRFCAPKvA9J) |
| 18 | 39 | same | 4 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/66RTx9et1RCmhtuBFbG9w2b1EKQnwQa9gCn3WmtjsZ99ChGedQVwmnjaXxHvvuVWRBjo8UuoTUcKcFAsSwryWRcJ) [dump](https://solscan.io/tx/27PxxQdjNYUr1ybRD4KMt75o95KEKzuhuMNJbD6Swd2qzTXdeW64cHRVZ4efR3xK1PrYpkLrrXv4Bxq4ou4yh1wk) |
| 19 | 50 | same | 0 | jito-bundle+helius+nozomi+staked-rpc+helius-swqos+bolt | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/3FQ6VdzVSu8NQEjxHZfaFnpEUHRMimxuBP3WyTbwKoPgsuKyWpmPUWWb4oAzpUWU5aWc1E7Caf6xf7XSac7c1dbR) [sell](https://solscan.io/tx/e3fveAaevwAYuNU1j1aV2HhzK8ymY8fvx5dSB9rahKpVTZsfc2KNKXNuQufhvXsRqRnTUBLkLakdztiUk3cyHQV) [dump](https://solscan.io/tx/6GRBHC9EP2cr559KcCawJRbbvPHZbT6Y179Pz4QYSG8bTrecyrvEToYNa5wdsWTubbysnVuQziBG6CG5ppa52mS) |
| 20 | 48 | same | 2 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 2.5 s | 1 | [buy](https://solscan.io/tx/21GfeXq1wnKDRF7odhJwhcDhAiQwhFoA2VtoMFfrJA5kdYKUtjNxX21UFaLCfYVERsUy2pLUG7aKRUKeKmq9dLYx) [sell](https://solscan.io/tx/23p2tuY1UZUxPfgAjvp4587ig2A2i5Wo6MYPygAuxa8vXojF1WbHzriaJJyz4FUJAynv9MmYy1zV78ymNSAVXCWQ) [dump](https://solscan.io/tx/5Dx9j85cXbKcmM36dH97YiSxb3vQrwnCKYh1ZM6MQbSAL7QvnT9nweGBBedGX7651W4haCN9RC9AZVepiy8T8X8) |
| 21 | 112 | +1 | 5 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4yk3Gg7wPsUESSoRh7JP15G2TJyM3xcM1djf5qEUYJYYf6uBi4fDDk8iroUoaVfuGJCNsDJfXB28tw3aMUkz1EXs) [dump](https://solscan.io/tx/3bHdM4EWLyTcgXydHCrq3SSNg1668DEoEgBvsxVBMWWzjGX5nhCxarW9ghFCR2fmrEW8Pdynn6HqffaRvQgDvCZ) |
| 22 | 16 | same | 1 | jito-bundle+helius+nozomi+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/2FJqDGK2Q73iamkX6bhwt3TVcxLwe6p55TukMdUwKTsMWxGdXUukRDkn5nGS7RHDmKGzKxPKmgJ95cnhyiC7kTAR) [sell](https://solscan.io/tx/8mJJ3xxjEcXCyjdbBwJzuY2ms1p1k3VLABYFMHnknoD2LeVgfw39eSD2TySmJMErQbbica9rWPzMyLApGwPLZAi) [dump](https://solscan.io/tx/5PvuamG6aDQcTSBTuo6jh1rACU8CcDsfiC15bkt3NwLtu65n7GYQLhyAd6zEAR5ie3mfFDwY2eUBQpjwAK6FPKTq) |
| 23 | 145 | +1 | 0 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 2.0 s | 1 | [buy](https://solscan.io/tx/zEtHNmufYX2ziYxagAYULHMuMdemqzZeVPx8CYMfQhFs2wMfMsjeMK25vtxwgEKzdVfECZcg15DmxPrHtxUHSF1) [sell](https://solscan.io/tx/4xyi4pVv9yxFNo1aWWgMhpPKiX74TfWudqaKS9u94XEVeRrSEPcScVQfMqHQwfMoxhA6x3KuEtJ5vx1utg7FR9Ay) [dump](https://solscan.io/tx/4KCBPeWr63Aez419JZ43XiPMn8kMvf3ysq8d36tc7oLK8sWMeBwpg3w1y6YFqyizvTvR9Kn6QLRVwzi2EUm1rTgc) |
| 24 | 40 | same | 3 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/2j2XGG3EJpxkT2Cb7wkyppbFMGGTWauHGZbk2fN1EwMJqGqkREeexDLRhhLEaexjBZUcPvoWaSmh4ueksrjfEotQ) [dump](https://solscan.io/tx/2jrX4EuSmN9HBjP9QrG13V2yuJtKqSTSyoEQ1qbZ9nwcArUL8A5AoSzrRcbbk6XR7n4RMSktkhPiTY6EnFneD6EK) |
| 25 | 148 | +1 | 5 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/2W5gU2adR7HYNUdgbinr2bkhrVWwahhSimNWtryUg6AHNTxFQHWrTck179K1wwxoJAhanLUKf5zYVwL89mUeVhJ6) [dump](https://solscan.io/tx/4RGfn21WvUxSCmj8ZDKNc7jm5ZfVxDsT5zdAronW6y2JWgycCS6jsefbVAHzwP3x7DYtHXrTmGQKaBnLEuF3tK64) |
| 26 | 160 | +1 | 3 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.9 s | 1 | [buy](https://solscan.io/tx/3cV1W9z1f71eAACbTW21tUgSCRj199AVCCgtn8LSkMGERDmYjN2weV8B18rTUhnSXqb3jqA2A7TfJyTuQUA7mejq) [sell](https://solscan.io/tx/aAvDQ6xZADJPvGTkDuUNi7cE5FJ5riSN4h8CvuLgDhXmDUEJR7tuArgBooHwLSPn371zrssA834NUR3rzToU7cp) [dump](https://solscan.io/tx/25ne5LfbntfSGo9EJgdeiSacv9KPC4vhq28NrELThUp8rx26HeEjMRL6kdnjp3hQzeyEJ6kPXdAu9sbo1cHqvHk4) |
| 27 | 39 | +1 | 0 | nozomi+helius-swqos+bolt+staked-rpc | stop-loss 1.1 s | 1 | [buy](https://solscan.io/tx/3WLmgkKuFvT4XVuqKaHDvbibpe1jcSBapRXhwq1Pc42Jq9qZ9iDgfoJjtvTDUdPiz64TasErscpPpvKsy6K2Rvhu) [sell](https://solscan.io/tx/8zV4KS7XGQe7oNUvR8wfQfkxuSp3qRtZWpFNPr4fzY8nowZNWFeXZpGufvE4wWtrDiAD4bgaAEVd88K4w9C2uNY) [dump](https://solscan.io/tx/2CtGrgxQCs4uutz1nTi2E7i3BthNnj9q2QvicCeQUAcngJwRvCoFj8d6y9Jx9yV22UV8KQAUM1bnYVLPjkYo4B1m) |
| 28 | 212 | +1 | 13 | nozomi+helius-swqos+bolt+staked-rpc | stop-loss 1.9 s | 1 | [buy](https://solscan.io/tx/2rxyANQG3d6RvhEmSKsQfjPrYgqAxjNG2uPN6qH9RenkpNVbRRoSoHh7JDXtmeDUKZB74vDyhB22E4sUmBvYLbb6) [sell](https://solscan.io/tx/28VmEKQHheMxNeGounmoW6X1CXmjBxRSez9ZQMS8UzsPxfdF6Ao3J7omo5uJK3maDnrQZ78GzchpebFpCpZqSTQ1) [dump](https://solscan.io/tx/g6N6ykW6o99vgzyPyV4cxoqGKYFor8S9836gi64a33pvLaJ6cz6qx9gGfgyjNYB4x6TnwKB1TDp1r7CRNJJpvUk) |
| 29 | 16 | same | 1 | landx-fra3+nozomi+helius-swqos+bolt+staked-rpc | stop-loss 1.1 s | 1 | [buy](https://solscan.io/tx/pXEQ2S2Vbw9hp1RNktm22DVeGEMzJWEHrWGhMSGFN3ynjQZT92rg7DnLUpKjZ8EHXJLuhiRK2YmCFRDRuo5yR56) [sell](https://solscan.io/tx/3SXQVcLkAPKNN1V1XTp8RZByTP1TQ17oMSUufRi1cfBuN9nec6o7mewxj8gx8ub2ANekgYeJfz2ETwAN6patfB86) [dump](https://solscan.io/tx/EquhDNjqJoDWYwGobkBsLgEWWKxWKzHRyVo7bv7oBNBRfrq3M5ff7mpTb6dCuiorvbxpy1GWTWPnRtxxP8QbYj3) |
| 30 | 15 | same | 3 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/3aDhnGuMTjtr3ShcDRHayFsnnbWQ8FYuXp2rbVDmgyKP44bbZZg2oGhdsqkPoHGsm61pECgSP5nCTygD5sRYPiQq) [dump](https://solscan.io/tx/572dfYtLwjZGANRHVU7Ega2rKtLBVKfRVCy2XvtV8CkZYMBjUHVYXcQw9eaVM7ftTXrDv2TKcBsJXhB1pZttTTHS) |
| 31 | 32 | same | 6 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4yFZS6zWuyCvDo9Gy3WfyAihLpyRcG6kf3yHuMY4miU3dQ5Ub7W3pLhuaqRUt4dRNpzHuKrCqZAvtzch5YbA8YcQ) [dump](https://solscan.io/tx/3mxWTjb3H1b69F9Btd1okoRb2gxghxvHXqdmrUmMkU3JRw5K2Eza9jRmXsyjYkx2nGoCerRQx3DuSCdVStvbv39d) |
| 32 | 31 | same | 4 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4CYtZtoxXWGH7fNLS9hGfPcbjPhiB7VSubTUswHbkXrkVBXbsrdWVah7ooNexLJRk5mVEpZa2Jak1RoFbWrnNyhU) [dump](https://solscan.io/tx/panSVT1TCzJxQ4CVQaw94iam9Ru4FQtATbVrKmFhaBzMP9YtM7aQEwomJ9MCnLyrQGuX7Y5VKge8oJAhMCGafCv) |
| 33 | 75 | +1 | 5 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/3ChtqY7M8uubmYrDUSvVYmemWTSnRF8wsyV2Y3xxoBJo1t4HgcVsP2ZBVzhpjPrNc4w9VF47Tuy7vsRREs6gEsiZ) [dump](https://solscan.io/tx/MPH8Lc1Y9xZ9pF7fy4SVq3h72YfF93tJLR5obG7ouFewy6xWj6tdRXwuUmW96VfqHs1LYWZiAEajbJ1jhB3D1Ww) |
| 34 | 21 | same | 6 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4hu6VbLs8Vab7bbHSR4ysDkrmxCvtEkuTwdm7874sGE8mb7Bzp3R5QTNQkAKcLinkxoMJmBXzgg2LpMgAHAtiJJF) [dump](https://solscan.io/tx/5zMJiMaZoKQFMJQKnhYENVQXK4H3F8HM1UVGn344okRgyoeaN9pSLYkqmajduhDuNTcDvrYijifJ5Uxa87yKMXCG) |
| 35 | 41 | same | 5 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4NtBkdCCXV8h8r5cZX4WcJX7QcuG9Cc9K493ZziDerqTLDBsA8mk23dro66dEx8TvgrLWud19gzDNb2mXCFCha9h) [dump](https://solscan.io/tx/3hXLT8rv86ceuR9f639A9Zt1kZ9Lu7V6msYoitFFUuAZ1HYA3Q2oxDgS5RorhfziGVnuUbikMwwjtL8ZFHuNnCtR) |
| 36 | 18 | same | 1 | nozomi+helius-swqos+bolt+staked-rpc | stop-loss 1.4 s | 1 | [buy](https://solscan.io/tx/4wGvcTZRJ8hy8ksnJz5GMB94WWgnRPxGTxMfkV36jQ4Z5kC4NrfEhr9v6vPbVvibc6xWeVnBLYXqdfdD8UpDsqK2) [sell](https://solscan.io/tx/pn7tkGe5Pk8GEMEUMSx8ATzhVaWs62KqvUbTMN1mQkJV1DCSfnrCcwkhAUdGneFWxacTu2nh7ZiGDQaXgp2J5f4) [dump](https://solscan.io/tx/5V6bzQM4vJmwVZDpJmyjb5od2yqRho8fEw6dXJEXwvCBTxD2fAA5rarxsNuzDB8CCtkUYs6LNzH8xzxV24NtAvow) |
| 37 | 50 | same | 3 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/64jca4s6XT65ufccz11PDSxJxqq9192ZCXoZjXQeN7PhGre5HxqynHW2ss2KzuFxZjmiYXiPEjzDqPy8xMj9vQQH) [dump](https://solscan.io/tx/AyZeYCb8kW3WBUGYyqTzW72ffYntsgYZ4ESHJv6zdiJLZtMHVHitFmQpVVusGX3amHevLKFLa5tnHQzhBAp78Y1) |
| 38 | 36 | same | 3 | landx-fra3+nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/51iQswLQiKWFgJ3MGY6qYaVrefuuyAcgXUMGoCVU6MTas7A9i6KnidGfM9iHdL1auZ7rARSKvDXqu7eXkapNsr4x) [dump](https://solscan.io/tx/2Gr4fjro2jNNJ1yN4HxVm14uzpsufra6e2RGrKnkEnGEeiv3nVzuQQkwuBiTgZwJV1mYAQhXEznBu8oKMdSzSdkf) |
| 39 | 17 | same | 0 | nozomi+helius-swqos+bolt+staked-rpc | stop-loss 0.9 s | 1 | [buy](https://solscan.io/tx/4EqF4jFUoT9Zgyt9a8dfdxZrSNmYgKUGyoihMuF4WjvYq9nLxb2rqDzoNjQHteqSvS12u8hhGi2cGxBHcPzRc54t) [sell](https://solscan.io/tx/21xwyBFRvY6T1PsP2PA96s2uR71CEBDtVqoW4nBP4pf5m3bhGbR3GnGpm6wN6J6Xksbq6wxkLbobTUZHuD16Eqz5) [dump](https://solscan.io/tx/48fGp8ySUqMtPZyGSwNdT36szxDnPdSyowGNAnbZ2k5EmkV99dD2YSy7tHwrexbAV34VCL4V81g3oi4JHd53rNWy) |
| 40 | 18 | same | 2 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/2G6c8oBpQ5kh9rScrzYsxpXNpwF4aUCM6yX6VYiKDMfKAKUBWDaNe5JAHqtvpgvtacHgNMJrr83CUv9dXcdaHBkR) [sell](https://solscan.io/tx/3awYvGb5G3sWZS2X646K5nynu7gHTA7ToG1QphQ3eR811pN7aUvuixuyUjkaEWeLNqFwkwjk5FDCAdiKKGBhdpru) [dump](https://solscan.io/tx/5CiDbBSqgkoBidZQJXcG1HAfQ9GUfhTC7b6Se5VuXRF46MY73Lz9Xq7JYbmAC5uqMaTnbsN2BsCkiktsQ2ybjt7P) |
| 41 | 14 | same | 1 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/29UFGDqtG8r6QgSG8dE646yCC2kvku5E8dNSrZp6weg4dmE9DTV4JHDDsuqWB77hgmWd65CwxXSeH26JwpqA2Ahz) [dump](https://solscan.io/tx/2jgPqv8MW6RUGmpPGkoM5m6itiQzKjrwKruDxNPJoBQxxUpDSd685x3zM5GXfZjvKQX93xQhKZYNKWeu3VUqXuPq) |
| 42 | 19 | same | 1 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/CVzZxzWjyWWKVsAHQ7AHjoCFxAji35BNoqEMmMZX1P8nHrrJ4qDWqixA3opHonajzQAbtN8JJUJcEYAjc7Nz5k9) [sell](https://solscan.io/tx/4XG6gj23jDtPjvSbGTicpWos8kEu158HZstJCjbUeVmV93FAeCG5BzpiMjKrPJKYr6D4xzCQcSCzHhwpCFJyLhrr) [dump](https://solscan.io/tx/2e4xbdU39hLcDKPhVfjy1xriYaTC5MBM81CAZbV4VEySa7oNty72prtXXZKeSssh63gEiNpajSgLV74uwr79Ge5N) |
| 43 | 24 | same | 2 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3UnuwvvGQv8b2T8FXyJFQaB4FYQ9UfbP6uXWNoqNnty5NxazGwqfdSwM5CyPfTSghGdnmgTwMynwviHsA9QhiF6a) [dump](https://solscan.io/tx/4v2z24gwDFbApTte5pDp3MgzsLV1aJRURSEznUqUbDDxVCzNetgdv4djuCrDbP5gz6vrFY3BytrazRrNzVgnC3L4) |
| 44 | 54 | +1 | 2 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/4vgSqsDVBwBZTGetRnZu53wg4onWLW1a2TzRYfjqUKXE23xuuU7WqCWeg3S23tJszi88RqtBma7iaHNNSgYdZYkJ) [sell](https://solscan.io/tx/4zvM7CCGMcTv18LfcyRu1F5tu5sCk8ntQWKPH1tWSn9t5Az18FcEtJhG4JUcVYqYSWQi7TsRtbxHE32tAfjW6FFA) [dump](https://solscan.io/tx/3KSTodapVV5UYXjGodG6dMNddVxymVE8AkCL3XHmj15ECRunndzp1E7ws4da3RdkgvPj6aL8eVQCkL7vLRH15kJ5) |
| 45 | 13 | same | 1 | landx-fra3+nozomi+helius-swqos+bolt+staked-rpc | stop-loss 0.8 s | 1 | [buy](https://solscan.io/tx/4hfLAsjZbkJEYBk8d9wVafiMDP8AmszRbSrMZddAkKU2HGdtVKiDSyck5KpgcNiSbddStBChWrqTVvrQamoAcLqn) [sell](https://solscan.io/tx/3pDwLDikXmAtkiMcRMYRfCwpPhhMe1S8KqRk833CoW3Sf9cxjZhzhfr351sn5P3oKJKuZSL2uJGFtJhzhN8jTEka) [dump](https://solscan.io/tx/5B3otXMwELymKZjnxQftB3cVUFBkAKijYB1Jx1qjMkz2efZ3TwyLvzer68wpXpoHQpJkQhzJcKFLK2V3JTbTicSj) |
| 46 | 146 | +1 | 5 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3oBQnTYdcVD2K8JGYbkrPTe2PebTLMbBjbhto8K9wejd4KwtvEvVgNkFzQ8TG2ZCyuuXa1bCwReYcV5ZdF4rpcZT) [dump](https://solscan.io/tx/3oz4BMBRCDmoxnSny49eU9zDpbn37D9zXXRLq7U6svUBUzidgoDmEjazcN148x5yePUJGFYrpgLx9Ni3UpZBuFqm) |
| 47 | 40 | same | 5 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/2hmGgaAy9EJbFLMTh9GLMT1HTPScMrVyQKUiWDhcFn2qUgHciXb13dbEfA85zwB3geLFzz4rzZftWNZxgNUuofxq) [dump](https://solscan.io/tx/4snNNv1hwFDda3mf1JC2sieH8BoTXjQaHdw9r9L71xbL7akdo9NF9ix8RPkTw3ESohfEytttEC3m3ny6NwaQipqP) |
| 48 | 35 | +1 | 4 | jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/2QRmhKd7pPT29KSW1C9aJkM864yoAN6n7JaakzkgiCkVMVe7kZ1WrCEfm7jj83Twj9Z7DQdnrb7HGruyer13Wxq8) [dump](https://solscan.io/tx/5bw1CUkbvJXXmYwvNvHQum5NqBcDJNQMNE56hQxZy7rFZuU4emqNzVxNqcobwSZPRUocQSNMGj3RuN78kzPBcJqd) |
| 49 | 44 | same | 4 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/ybUgHWmwPDocqFzCBrccmMN1cJk5CFuVJTiJhxDUSu3JcYAV4MZe9ntxqHq4NcsAKNZN8vbimRzXYDr7KH7uPc6) [dump](https://solscan.io/tx/2D8JfAwMKsNSXJNKaSSjk9Qv32nSb8cSUWHvP2TmMY6VKsJztYpsGudfYuGYDgTT3gWebT4B5rTV6boABvSyJEmn) |
| 50 | 47 | same | 1 | jito-bundle+helius+nozomi+staked-rpc | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/38Y5vukfiWFq4ALRtBdrrcSDdwULu8paC5ZGEcaxTUnQFKiW7MqhDv1hbFkTq8rkJgDTkdAQUSNpC7WLBXAjUzET) [sell](https://solscan.io/tx/VNtAPS4tY3AF6tURW7CwtRxYYoFWgDXzWuGQB4SAmxbxB2zukeoxUjT9zgVkGwiiT4K1Hv1iGDFpep4hYc8GHdz) [dump](https://solscan.io/tx/TzqdvEDFEFtG4SAoCwRLaX498ea5TyMSEqAKQxUysE5WRTo2iy4wE8midNd4srdb5jzDZRArrXB2VH7GvPzFR2g) |
| 51 | 35 | same | 2 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/2jwNx4DeKcXbLwroVK46CWQhnfFiGHP4Bpmze6fwz2g38B5LK9bhuEuw6CZne8te6oyHs3u8EG6Nv9jKnQmfoBdo) [dump](https://solscan.io/tx/5o5hxVcPkUn74SKa3f7V5c3mVpPKocGSqY9fiQ6nPbB627QZth2u4EWkuGnFiqC3NyAT6b1M3koYVNppH6PCFRtt) |
| 52 | 21 | same | 3 | landx-fra3+nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/2it6w5oogAuLEB4j2dk3fg4wqxh3JYhRr2h9LdE9bfPCNo278uwT5RxKHF6zWSRFzrYGEDWYkZfvViga1MJH83A6) [dump](https://solscan.io/tx/4rskKtRd5ABoHN2z8ExNtPZ424cMH8P5kVxESrowKjLB4BAS6nEDsDXHGRB3MjLFv9iQLHqKUzKHETQHyKJB5SYV) |
| 53 | 14 | same | 0 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 2.2 s | 1 | [buy](https://solscan.io/tx/4w4tTgfNg492rodT4SNKJ3pSQ6fQFQpYbcyHKK26iYJJZbKekaLFD6sDqUXYEoiDXGUsNRFqTZwC5EgJewPVpvD9) [sell](https://solscan.io/tx/4k47Y4KG4UnyrgjcXRgD3bSQpAXt73rb9HHCmr5CanNyx7JbUcwj6SuZn2VnvvjghQV6isVazyLpGChRuqUjgDD7) [dump](https://solscan.io/tx/3vCkxYDAZ5DsnVLBvgNhjGbPxtoPesEsW92SsghFrpeSUgX3MHHhYcLHfrXysfbMu4WpKjoN9fLwAF2VkT25KJJX) |
| 54 | 46 | same | 4 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/5Hf6USPUZmccFutxgaRsoDu1EXuyJc4L7jGMsgwRv6NQ7rLvwamjWyhgRLHaea5rcj4AfYpgMMxBLNNkWZZFpWFN) [dump](https://solscan.io/tx/frp3LKiJ5wvcZYAvybwSY2GuZvRbCKxW1QkXjYXz6gzbftMuNPTirjztBiQMQ6sP2UuAusr4rnFhZT1XcMNnJcd) |
| 55 | 19 | same | 1 | nozomi+helius-swqos+bolt+staked-rpc | stop-loss 0.5 s | 1 | [buy](https://solscan.io/tx/4BxmMP2JpF6eFxoPgoBpkBTYyjCrUj23sq8iHpGpowyoi8vFHmM7hpCtSk19YzHQNiVy3J17T9Td2vT8Yz2CW7t6) [sell](https://solscan.io/tx/3f1mR6TVqBZaGxNQF99df6zdbte63d85M71yVPx3S5y9P8HK8oCGT57Rjkiw2fHQLzp8mv1cYJ94WrkgVsMALPQx) [dump](https://solscan.io/tx/4xyyEsYzsx3PNfJyzkvzE5qMPXQX1ojrEVo1SpzQsvDk8kFMD5GUoZqnUprYVtC875ag5AosmN3RkkGCSKyDNtyf) |
| 56 | 23 | same | 1 | jito-bundle+nozomi+helius-swqos+bolt+staked-rpc+helius | stop-loss 0.7 s | 1 | [buy](https://solscan.io/tx/2So5XbiNvNjTDdZmjC9ntTdTbFssChcwsRbgjdw9TJDjebb1qeVfF8t8Xw7bB1ozdfXoV4DCLNyDh2VaQmFWs4Wg) [sell](https://solscan.io/tx/5gvxLjtYXiBtJAoXCAyFizcSUT5PawRuSjcSMZ5B9XgzidXNB9QXMjWe7RSVJEiHG7dAS9L8CF5xbufaE5TA1x9s) [dump](https://solscan.io/tx/cBE2KR47oo6ie911fWNSEdupJz6joUXjMfghMEYpcFNEBz5gQtCvDs9JqqS8r5qXbZU1z9ycmEiCvmVmF1Gn1Vy) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| BAM | 29 | 16 | 55% | -0.4388 | -0.0270 | 5/16 |
| Jito | 13 | 6 | 46% | +0.1923 | +0.0326 | 5/6 |
| Harmonic | 13 | 7 | 54% | +0.0554 | +0.0083 | 5/7 |
| Rakurai | 1 | 1 | 100% | +0.0528 | +0.0528 | 1/1 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 29 | 19 | 66% | -0.1613 | -0.0082 | 9/19 |
| dev list | 27 | 11 | 41% | +0.0229 | +0.0028 | 7/11 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 42 | 23 | 55% | -0.2957 | -0.0124 | 11/23 |
| next block | 14 | 7 | 50% | +0.1573 | +0.0230 | 5/7 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 18:00 | 8 | 5 | 62% | +0.1563 | +0.0316 | 3/5 |
| 19:00 | 5 | 3 | 60% | +0.0398 | +0.0136 | 2/3 |
| 20:00 | 10 | 8 | 80% | +0.1185 | +0.0149 | 7/8 |
| 21:00 | 13 | 5 | 38% | -0.1191 | -0.0230 | 1/5 |
| 22:00 | 9 | 5 | 56% | -0.1202 | -0.0236 | 3/5 |
| 23:00 | 6 | 1 | 17% | -0.0229 | -0.0204 | 0/1 |
| 00:00 | 5 | 3 | 60% | -0.1908 | -0.0633 | 0/3 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 22 | +0.3134 | +0.0142 | 1.7 s |
| stop-loss | 8 | -0.4386 | -0.0548 | 1.0 s |

## 8. P&L leaders
**Best trades:** J5SxQW +0.0763 (Jito, time-limit, score 0.25); 9yJrLW +0.0593 (Jito, time-limit, score 0.42); J5SxQW +0.0572 (BAM, time-limit, score 0.54)

**Worst trades:** ArWBsC -0.1121 (BAM, stop-loss, score 0.87); CYm1Hg -0.0984 (BAM, stop-loss, score 1.05); EPEa7b -0.0776 (BAM, stop-loss, score 0.74)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `icex1C6p` | JitoLabs | 3 | 3 | +0.1122 |
| `LeDbQ99Q` | JitoLabs | 1 | 1 | +0.0593 |
| `Aw5wEMXh` | AgaveBam | 2 | 1 | +0.0567 |
| `2dfgsiSa` | Rakurai | 1 | 1 | +0.0528 |
| `AEHqTB2R` | JitoLabs | 4 | 1 | +0.0432 |
| `3tzpLMWR` | HarmonicAgave | 2 | 1 | +0.0369 |
| `cybi55eb` | AgaveBam | 2 | 2 | +0.0297 |
| `A1vqhA2f` | HarmonicAgave | 1 | 1 | +0.0252 |
| `7tqeaFKs` | AgaveBam | 3 | 1 | +0.0230 |
| `DrifTrN9` | HarmonicAgave | 2 | 1 | +0.0118 |
| `EkvdKhUL` | HarmonicAgave | 3 | 2 | +0.0113 |
| `2mMGsb5u` | HarmonicFiredancer | 1 | 1 | +0.0044 |
| … |  |  |  |  |
| `GnC339vk` | JitoLabs | 3 | 0 | -0.0015 |
| `GSTampk6` | AgaveBam | 2 | 1 | -0.0143 |
| `5pPRHnie` | JitoLabs | 1 | 1 | -0.0204 |
| `76rcGHdP` | AgaveBam | 1 | 1 | -0.0217 |
| `GoeW4aFK` | HarmonicAgave | 2 | 1 | -0.0332 |
| `722RdWmH` | AgaveBam | 1 | 1 | -0.0382 |
| `BUv44cVt` | AgaveBam | 3 | 1 | -0.0439 |
| `6TkKqq15` | AgaveBam | 1 | 1 | -0.0486 |
| `22rU5yUm` | AgaveBam | 2 | 1 | -0.0781 |
| `7CR3Jq4n` | AgaveBam | 2 | 2 | -0.0913 |
| `6WgdYhhG` | AgaveBam | 3 | 2 | -0.1011 |
| `AWcCdYG7` | AgaveBam | 1 | 1 | -0.1121 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1335 (p25 1026, p75 1799, n 56) |
| Executed-feed lag behind first sighting, ms | 0.7 (p25 0.5, p75 1.2, n 56) |
| Buy sent → our tx seen on the feed, ms | 32.9 (p25 18.0, p75 45.3, n 56) |
| Fills: our buy seen on the feed after the dump, ms | 29 (p25 19, p75 48, n 30) |
| Guard fails: our failed buy seen after the dump, ms | 38 (p25 24, p75 50, n 26) |
| Fills in the dump's own block | 23 of 30 |
| Guard fails in the dump's own block | 19 of 26 |

**Send-path answers (FAST-ACK lines):** nozomi 56 (median ack 0.5 ms), staked-rpc 56 (median ack 2.4 ms), helius-swqos 44 (median ack 0.8 ms, 1 errors, 1×429), bolt 31 (median ack 0.8 ms), helius 14 (median ack 0.6 ms, 1 errors, 1×429), jito-bundle 14 (median ack 1.2 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 2.00 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| haqq (dip bot) | 9 | 4 |
| 2KtcBC (pre-placed) | 7 | 7 |
| HkQ7 (dip bot) | 7 | 6 |
| 6n2cCJrr | 7 | 3 |
| 8PgC4ngp | 6 | 3 |
| GonzYBmk | 5 | 5 |
| CVPz447t (pre-placed) | 5 | 5 |
| 9k78QZyw (fast bot) | 4 | 3 |
| BfcqTk6L | 4 | 3 |
| 5w8xtjc6 | 3 | 0 |
| G9G3dCBG | 3 | 0 |
| 5ZKd8DNB | 3 | 2 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.3320 |
| Pump fee on buys | 0.1568 (0.0052 per fill) |
| Pump fee on sells (residual) | 0.1609 (0.0054 per fill) |
| Buy tx fees (base + priority) | 0.0152 (0.00051 per fill) |
| Buy tips | 0.0756 (0.0025 per fill) |
| Sell tx fees | 0.0188 (0.00063 per fill) |
| Sell tips | 0.0300 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0132 (26 buys) |
| **Result** | **-0.1384** |

Buy compute used (fills): median 78,405 CU, max 96,468 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 2 sell issue line(s), e.g. `SELL #2 qty=8086823416101 cu_limit=120000 sig=5wwmnbA7CJdwbXTUbNF7oUCWoZYiwU8zqkBNL8tB7bPPc2o3qVxZKiGPHmy6csUcQaL5UWhnss1xs4cjuqPgTPWb landed FAILED e`
- ⚠️ 22 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getLatestBlockhash: 3 timeouts/transport errors (worst p99 822 ms)
- ⚠️ RPC bh-fallback getSlot: 3 timeouts/transport errors (worst p99 824 ms)
- ℹ️ RPC exit-fallback getAccountInfo: slow minutes (worst p99 930 ms, max 938 ms)
- ℹ️ send path helius-swqos: 1 × HTTP 429 (rate limited) on buys
- ℹ️ send path helius: 1 × HTTP 429 (rate limited) on buys
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)
- ℹ️ q2rc3D: 2 sell txs landed (duplicate sell)
- ⚠️ big loss BiemY3 -0.0738 (stop-loss, BAM)
- ⚠️ big loss ArWBsC -0.1121 (stop-loss, BAM)
- ⚠️ stop-loss slipped: ArWBsC stop at −10% but the curve loss was −28% (one big sell went through before ours)
- ⚠️ big loss EPEa7b -0.0776 (stop-loss, BAM)
- ⚠️ big loss CYm1Hg -0.0984 (stop-loss, BAM)
- ℹ️ wallet change -0.1469 vs trades -0.1384: gap -0.0085 SOL (transfers / rent / unsold — see notes)
- ⚠️ q2rc3D: a duplicate sell (#2) failed with 3012 AccountNotInitialized — the first sell had landed; harmless
- ℹ️ wallet change includes ~0.0116 SOL nonce rent (refundable)

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED.

## 13. Fixes and follow-ups
**Done after this run:**

- Nonce fan-out (dip10) + standby RPC change (see run 11).

**Recommended / open:**

- Run 11 = same + nonce.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r10.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r10.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

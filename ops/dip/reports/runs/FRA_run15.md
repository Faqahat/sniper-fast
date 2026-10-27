# Frankfurt run 15 — dip bot run report

*A/B, M2 side: the new M2 model GATES the buys (dev-list keeps IMIT1); 0.35 SOL, 5-slot hold / no stop; M2 + pre-send shadows*

> **Verdict:** +0.148 SOL on 40 fills of 101 buys (40% fill rate) over 9 h. Best run since run 7. Most misses were the +5% guard on dumps faster bots took first. Full-day pre-send shadow (paper, 0.55 SOL): 1,586 windows, ~340–366 fills, net +2.7 to +4.2 SOL depending on landing (06:08–15:08 PKT).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.1485 SOL** (wallet 2.6949 → 2.8434, Δ +0.1485) |
| Started (PKT) | 2026-10-25 06:09:07 |
| Ended (PKT) | 2026-10-25 15:09:07 — time limit / max trades |
| Ran for | 9 h 00 min of 540 min planned |
| First / last buy (PKT) | 06:12:07 / 15:07:24 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 101 → **40 filled**, 61 failed on the +5% guard |
| Fill rate | 40% |
| Wins / losses (fills) | 19 / 21 (win rate 48%) |
| Per filled buy | avg +0.0045, median -0.0020 SOL |
| Fills only / failed buys only | +0.1793 / -0.0308 SOL |
| Best / worst trade | FzeP2j +0.1519 / 33V5Ee -0.0739 |
| Fill landing | median 39 ms after the dump (seen on our feed); 32 of 40 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip12 (M2 gate + pre-send shadow) |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.35 SOL |
| exit | take-profit off / stop-loss −50% / time limit 5 slots (~1.1 s) |
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
| pre-send | off (shadow only) |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 540 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 14**:

| Setting | FRA run 14 | FRA run 15 |
|---|---|---|
| engine build | dip11 (M2 shadow) | dip12 (M2 gate + pre-send shadow) |
| exit | take-profit off / stop-loss −10% / time limit 6 slots (~1.3 s) | take-profit off / stop-loss −50% / time limit 5 slots (~1.1 s) |
| pre-send | off | off (shadow only) |

- Engine dip11 → dip12: M2 in GATE mode (the M2 score replaces the IMIT1 gate; dev-list tokens keep their IMIT1 tier).
- Exit 6 slots / SL −10% → 5 slots / no stop (SL −50%).
- Pre-send shadow on (logs only).

## 4. Timeline (PKT)
- **06:09:07** engine start #1 (session with 101 buys)
- **06:12:07** big win: 3bam7k +0.0556 SOL (time-limit)
- **06:40:20** big win: FzeP2j +0.1519 SOL (time-limit)
- **07:39:42** big loss: 33V5Ee -0.0739 SOL (time-limit)
- **08:11:14** big win: 341gnf +0.0573 SOL (time-limit)
- **10:50:00** big win: 8Dbb9X +0.0903 SOL (time-limit)
- **15:09:07** engine end #1: run end

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 21589 |
| Inside the envelope (age / drop / since-buy / size) | 9596 |
| Picks (score above the threshold) | 334 |
| Skipped | far_leader 196, spacing 37 |
| Buys sent | 101 |
| Filled | 40 |
| Failed on the +5% guard | 61 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 40 of 40 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 06:12:07 | [3bam7k](https://gmgn.ai/sol/token/3bam7kHXYshxfqofFjKm3Kc9VWPYwxnE3JsKuqccpump) | 0.35 | -0.79 | 7.08 / −16% | 7.4 s | Harmonic `5ZqveV` | filled | **+0.0556** |
| 2 | 06:12:15 | [6NVyns](https://gmgn.ai/sol/token/6NVynsmZtvUjVs4FnWYyWo5AEVJ3Mx94mFbBdFYtEJ2k) | 0.35 dev | 0.39 | 1.57 / −8% | 1.9 s | BAM `3JotfS` | filled | **-0.0018** |
| 3 | 06:12:53 | [E4TMRb](https://gmgn.ai/sol/token/E4TMRbYt5v1oeS8BFQ7aHxDayGnshj6LAAi9C99Kd8BJ) | 0.35 dev | 0.28 | 1.84 / −10% | 2.1 s | Harmonic `FNKgX9` | guard fail | -0.0005 |
| 4 | 06:15:34 | [Ez39gv](https://gmgn.ai/sol/token/Ez39gvhqBb5xoYwMhKYMKCdHyYu7SbNvosQD7NwYxSgn) | 0.35 dev | 0.44 | 1.42 / −7% | 2.1 s | BAM `Hj2jzp` | filled | **-0.0384** |
| 5 | 06:17:32 | [Ejgwrr](https://gmgn.ai/sol/token/EjgwrrxcNrJBQLYGWmsoTt6A8tghaEYbPRaHyAtM8sc4) | 0.35 dev | 0.37 | 23.56 / −61% | 1.1 s | BAM `4k6wgP` | guard fail | -0.0005 |
| 6 | 06:19:21 | [GTabiB](https://gmgn.ai/sol/token/GTabiBtAzWEqNVKtuM2My5PGz5hcDSU3ZCLQw1xzpump) | 0.35 | 0.37 | 2.37 / −11% | 2.1 s | Jito `vu1sGn` | guard fail | -0.0005 |
| 7 | 06:29:08 | [8D9Xss](https://gmgn.ai/sol/token/8D9XssVZAgKMoRMX4M2wJAko4KjNa7cFAuQuwZCRpump) | 0.35 | 0.14 | 6.62 / −22% | 5.5 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 8 | 06:30:27 | [2XqFe8](https://gmgn.ai/sol/token/2XqFe8VE1SQ9xBLt5uLQ47FYfAF3pzKm15cePSaJpump) | 0.35 | 0.23 | 5.19 / −19% | 3.6 s | BAM `CfgRXm` | guard fail | -0.0005 |
| 9 | 06:30:55 | [2vx7Sz](https://gmgn.ai/sol/token/2vx7SzKj6ssNitJixc6dcVCqaCreCu8LLitFP15jpump) | 0.35 | -0.53 | 1.82 / −11% | 9.8 s | Jito `HEL1US` | guard fail | -0.0005 |
| 10 | 06:32:04 | [FB7xku](https://gmgn.ai/sol/token/FB7xkuda5g97Bhd7R3nfjPT54NpwzuSXaSM1uvd8pump) | 0.35 | -0.49 | 1.96 / −10% | 2.8 s | Harmonic `Awes4T` | filled | **+0.0180** |
| 11 | 06:33:42 | [JBTvRA](https://gmgn.ai/sol/token/JBTvRAiNAKfPeybveGRb8SDRpCrGA4gw7Lzxfogdoy8q) | 0.35 dev | 0.78 | 4.65 / −24% | 1.9 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 12 | 06:36:57 | [8ExCVE](https://gmgn.ai/sol/token/8ExCVE4gQQk2Xm63dmDE6x9wzEG92RE8WY9gYHFYpump) | 0.35 | 0.66 | 3.39 / −13% | 4.0 s | Jito `4Nwpyn` | guard fail | -0.0005 |
| 13 | 06:37:21 | [127avc](https://gmgn.ai/sol/token/127avc474TiubvqZMgHRx1UR3ojUXkNLaaVCXpcvpump) | 0.35 | 0.31 | 2.81 / −12% | 6.6 s | Jito `privaE` | guard fail | -0.0005 |
| 14 | 06:38:23 | [6Te7vL](https://gmgn.ai/sol/token/6Te7vLCzSUjs1fA8KXrMV1FpUBx5pLSKfeYk7keopump) | 0.35 | -0.07 | 2.69 / −16% | 3.6 s | BAM `G2TBEh` | guard fail | -0.0005 |
| 15 | 06:38:45 | [ARbV5E](https://gmgn.ai/sol/token/ARbV5EoiynJMc27T7gYuwn2sYjD21YXKUuA2LSXFpump) | 0.35 | -1.43 | 3.28 / −17% | 6.4 s | BAM `7y5VhV` | guard fail | -0.0005 |
| 16 | 06:39:00 | [E9jEzy](https://gmgn.ai/sol/token/E9jEzyeo2DH2iJXedhTBur5kicJsgKsBtqxFTfKepump) | 0.35 | -1.94 | 1.54 / −9% | 6.8 s | BAM `CVRr5o` | filled | **-0.0306** |
| 17 | 06:39:33 | [EfKB6n](https://gmgn.ai/sol/token/EfKB6n3N4yxM7mkQCm6XzKCoCoFxWUar7oo7LE4Gpump) | 0.35 | -0.95 | 5.16 / −20% | 7.2 s | BAM `2jS8AX` | filled | **-0.0201** |
| 18 | 06:40:20 | [FzeP2j](https://gmgn.ai/sol/token/FzeP2jy29V79RndebdLa46LETwMxUj7Vt8BvSRMApump) | 0.35 | -1.77 | 6.79 / −18% | 24.4 s | Harmonic `Fd7btg` | filled | **+0.1519** |
| 19 | 06:42:08 | [8HHRyn](https://gmgn.ai/sol/token/8HHRynxi8uDnByhCcFL648V83wCMkkurj85hqNGnpump) | 0.35 | -0.60 | 2.26 / −12% | 2.1 s | Jito `8gDfqH` | guard fail | -0.0005 |
| 20 | 06:42:10 | [LTAdFg](https://gmgn.ai/sol/token/LTAdFgwCsHA5ByRshtp7P65bNvehPNkRaMkwXhLpump) | 0.35 | -0.92 | 2.94 / −10% | 6.2 s | Harmonic `Fd7btg` | filled | **-0.0083** |
| 21 | 06:42:30 | [LTAdFg](https://gmgn.ai/sol/token/LTAdFgwCsHA5ByRshtp7P65bNvehPNkRaMkwXhLpump) | 0.35 | -0.37 | 3.89 / −13% | 27.1 s | Jito `HEL1US` | guard fail | -0.0005 |
| 22 | 06:43:04 | [6rvBYF](https://gmgn.ai/sol/token/6rvBYFVRPgf9NvFruKQnFsd7Wj2iLoGtZgxTeCgxsgp2) | 0.35 dev | 0.98 | 4.09 / −14% | 269.7 s | Harmonic `5ZqveV` | guard fail | -0.0005 |
| 23 | 07:01:01 | [42ef2A](https://gmgn.ai/sol/token/42ef2AoJhpqCaYZ1gG1NiAMMRHNybYf4PQERmFAhpump) | 0.35 | 0.69 | 2.53 / −13% | 65.1 s | Rakurai `ana2y2` | guard fail | -0.0005 |
| 24 | 07:02:02 | [8zsFH5](https://gmgn.ai/sol/token/8zsFH5cS1YT93nhb3ZWzCYk7gvADt7Nqc9P2PgGUpump) | 0.35 | 0.77 | 4.80 / −19% | 6.2 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 25 | 07:06:18 | [3jPcVT](https://gmgn.ai/sol/token/3jPcVTs5ZxWHQsprPdNnheY6et3k3HBVHYbzcC4mpump) | 0.35 | 0.44 | 3.50 / −14% | 78.7 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 26 | 07:09:54 | [4oHteQ](https://gmgn.ai/sol/token/4oHteQPSidUxTRRV6RcA8FVjutBFbwn7xXDiQ6PUpump) | 0.35 | -0.73 | 2.02 / −9% | 2.5 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 27 | 07:10:06 | [32yah1](https://gmgn.ai/sol/token/32yah1uwYgiRnFHoCp8DBareh4DHsEWBJaqx9ArEpump) | 0.35 | -1.06 | 1.97 / −8% | 2.3 s | Harmonic `Fd7btg` | filled | **-0.0283** |
| 28 | 07:19:57 | [Fnhsze](https://gmgn.ai/sol/token/FnhszeesHrgYPCSrBfQ7oS83DKvAxt9dmMWJG4d2pump) | 0.35 | 0.46 | 6.03 / −22% | 2.3 s | Harmonic `9W3QTg` | guard fail | -0.0005 |
| 29 | 07:20:00 | [Fnhsze](https://gmgn.ai/sol/token/FnhszeesHrgYPCSrBfQ7oS83DKvAxt9dmMWJG4d2pump) | 0.35 | 0.38 | 3.34 / −13% | 5.5 s | Harmonic `pSo1KZ` | guard fail | -0.0005 |
| 30 | 07:20:01 | [Fnhsze](https://gmgn.ai/sol/token/FnhszeesHrgYPCSrBfQ7oS83DKvAxt9dmMWJG4d2pump) | 0.35 | -0.01 | 3.37 / −13% | 6.6 s | Jito `HEL1US` | guard fail | -0.0005 |
| 31 | 07:21:08 | [6bJZTc](https://gmgn.ai/sol/token/6bJZTcrqpXu4mbcBjujUJhFbxpMwU84E9UqrVWg7pump) | 0.35 | -0.22 | 4.62 / −23% | 10.4 s | Firedancer `EvnRmn` | filled | **-0.0248** |
| 32 | 07:22:52 | [rUzSLB](https://gmgn.ai/sol/token/rUzSLBPCJAK9F2SHiRLG625gec5jkRgwGp6yFqLJeXh) | 0.35 | -0.63 | 3.03 / −16% | 8.5 s | BAM `JC7bH7` | filled | **-0.0161** |
| 33 | 07:31:48 | [33D1NN](https://gmgn.ai/sol/token/33D1NNmpSMjC2AhiAFXB6CGtL3vLkz1nEAbYSrTHpump) | 0.35 | -0.42 | 3.71 / −16% | 4.2 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 34 | 07:37:54 | [8hGKQA](https://gmgn.ai/sol/token/8hGKQAtBwfo8bDzkfnsSQRJgWAJSnnr4V3NrJhTrpump) | 0.35 | -1.84 | 1.94 / −11% | 11.4 s | Jito `HEL1US` | filled | **+0.0166** |
| 35 | 07:39:42 | [33V5Ee](https://gmgn.ai/sol/token/33V5EeuodTxTr1XUQNETSFJkd8K3KPeZTWBSYWT6pump) | 0.35 | -0.81 | 2.60 / −12% | 8.1 s | Rakurai `ana2y2` | filled | **-0.0739** |
| 36 | 07:40:35 | [33kLyL](https://gmgn.ai/sol/token/33kLyLkiBrq8cAFeE5vkgojhvNyxwQs8AjRBGjSLpump) | 0.35 | -0.95 | 3.05 / −14% | 5.3 s | Harmonic `EXckih` | filled | **-0.0126** |
| 37 | 07:43:36 | [HVL4QH](https://gmgn.ai/sol/token/HVL4QH6b8xtfhr6mSadxnrQd7jX9dEgvEtGCiFVjpump) | 0.35 | -2.24 | 1.52 / −9% | 36.0 s | Harmonic `5RvfTS` | guard fail | -0.0005 |
| 38 | 07:49:22 | [9LepYg](https://gmgn.ai/sol/token/9LepYg9iRDy2APTZnSz8NyoTtVqG9wHobzfU7ZEvpump) | 0.35 | -0.10 | 3.76 / −18% | 1.3 s | BAM `5pZvwj` | guard fail | -0.0005 |
| 39 | 07:57:45 | [asGRNw](https://gmgn.ai/sol/token/asGRNwUQCaCz4V2W2G1zkQe7iq2kD5hFoC3xNC6pump) | 0.35 | -0.25 | 3.15 / −14% | 1.7 s | BAM `7nzTzR` | filled | **+0.0222** |
| 40 | 08:05:30 | [DHs6rd](https://gmgn.ai/sol/token/DHs6rddUHD45idbbe3ub3s7YBT3jVYGJ9cUFj8Tcpump) | 0.35 | 1.45 | 4.30 / −19% | 24.0 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 41 | 08:06:08 | [C6aLKF](https://gmgn.ai/sol/token/C6aLKFzuSTf9byMCPWA5opLMXtjsT62YQNsPfSyjpump) | 0.35 | -0.93 | 2.17 / −11% | 4.7 s | Harmonic `G3a3iY` | filled | **-0.0355** |
| 42 | 08:10:10 | [6SWy8j](https://gmgn.ai/sol/token/6SWy8j6dGrApXFd8NY4JkbKbHBCo5RoRvKbLfXtNpump) | 0.35 | 1.30 | 2.63 / −14% | 8.7 s | Jito `HEL1US` | guard fail | -0.0005 |
| 43 | 08:11:14 | [341gnf](https://gmgn.ai/sol/token/341gnfa84BXKa61Z23XVWNQtXutTjYuHUiuBrPCNpump) | 0.35 | 0.37 | 4.25 / −17% | 6.4 s | Harmonic `5ZqveV` | filled | **+0.0573** |
| 44 | 08:11:28 | [341gnf](https://gmgn.ai/sol/token/341gnfa84BXKa61Z23XVWNQtXutTjYuHUiuBrPCNpump) | 0.35 | 0.32 | 3.69 / −13% | 21.2 s | Jito `HEL1US` | guard fail | -0.0005 |
| 45 | 08:14:52 | [4eZxnV](https://gmgn.ai/sol/token/4eZxnVygJcETMH2HMPjn5wCeRL45XusTFnLpbEKmpump) | 0.35 | -0.34 | 3.06 / −13% | 2.1 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 46 | 08:21:01 | [2wEcZv](https://gmgn.ai/sol/token/2wEcZv3FfPYQfMgTeyMiKhFPLAhtnSEzDTvQD8dbcRyf) | 0.35 | -0.02 | 2.70 / −14% | 4.7 s | Firedancer `EvnRmn` | filled | **-0.0201** |
| 47 | 08:40:56 | [FYXLXB](https://gmgn.ai/sol/token/FYXLXBBKCFhuDPNiyVNFCiwaWD65B8zofoqqBPejpump) | 0.35 | 0.84 | 2.93 / −12% | 5.5 s | Jito `HM19KB` | guard fail | -0.0005 |
| 48 | 08:42:27 | [AUEMn1](https://gmgn.ai/sol/token/AUEMn1ca1ND63z5hgnDLh7cHDHiVRtTD7qQbqdk7pump) | 0.35 | -1.04 | 4.94 / −14% | 85.0 s | Jito `C8Bey3` | filled | **+0.0042** |
| 49 | 08:46:29 | [29qFbb](https://gmgn.ai/sol/token/29qFbbCuNi84iojLL9D5xgrotrmDKnGZmCqKbofDpump) | 0.35 | -0.04 | 4.70 / −11% | 44.1 s | Harmonic `3iSQtP` | guard fail | -0.0005 |
| 50 | 08:54:12 | [36JuJo](https://gmgn.ai/sol/token/36JuJoPLWWhdsDKSpXRA7dZhH8xMUG2uiFeB484hpump) | 0.35 | 1.00 | 3.84 / −18% | 59.4 s | Harmonic `Fd7btg` | filled | **+0.0420** |
| 51 | 09:11:34 | [aXXPih](https://gmgn.ai/sol/token/aXXPihhBToNqC3oHL3V5YTT4hTEQzxdGqdz258ipump) | 0.35 | 1.13 | 4.21 / −19% | 56.0 s | Harmonic `Fd7btg` | filled | **-0.0329** |
| 52 | 09:12:08 | [F8gSob](https://gmgn.ai/sol/token/F8gSobp3VbdGcCcgPzdqqZHv6sKDiZ1EMfv7yzcDpump) | 0.35 | 0.54 | 3.38 / −18% | 194.4 s | Harmonic `BeaCHi` | filled | **-0.0366** |
| 53 | 09:26:53 | [EcEqf9](https://gmgn.ai/sol/token/EcEqf9zWKw41b3R1zDp117G64as59nC5Bd7N9Bbipump) | 0.35 | -0.54 | 2.44 / −11% | 4.7 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 54 | 09:32:15 | [HNefrX](https://gmgn.ai/sol/token/HNefrX9WJK89AexZvNG8XTn8oKokUruoJstmmth8pump) | 0.35 | -0.55 | 2.04 / −12% | 3.0 s | Jito `C8Bey3` | filled | **-0.0118** |
| 55 | 09:44:17 | [FGKsZJ](https://gmgn.ai/sol/token/FGKsZJCS2BGsYCqjz5f5A2dgBMtEWo3YCK237SaWpump) | 0.35 | -1.08 | 1.09 / −7% | 7.4 s | Jito `HEL1US` | guard fail | -0.0005 |
| 56 | 09:56:21 | [XEoJXi](https://gmgn.ai/sol/token/XEoJXiJVPSkRp2t8rLxkBAJf31ge5wXUfDDcgWopump) | 0.35 | 0.64 | 3.63 / −17% | 54.9 s | Harmonic `pSo1KZ` | guard fail | -0.0005 |
| 57 | 10:01:06 | [E6qYjw](https://gmgn.ai/sol/token/E6qYjwjCFEFqrqJYn1RjKXkPrQnBcdNuYRX2ke12pump) | 0.35 | 0.02 | 2.92 / −14% | 7.4 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 58 | 10:01:33 | [2UNWZs](https://gmgn.ai/sol/token/2UNWZsETir1oZeYjCQaEvEgQHwvh1yJ3ocD9AmkKpump) | 0.35 | 0.76 | 6.66 / −21% | 21.6 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 59 | 10:12:29 | [53ZoQS](https://gmgn.ai/sol/token/53ZoQSUkHinwGnC6eewGxXjRpSNyd9Sf61cgLpXVpump) | 0.35 | 0.46 | 3.00 / −17% | 3.8 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 60 | 10:19:40 | [FbeSRm](https://gmgn.ai/sol/token/FbeSRmqXqJoxcgXkyzDF9HcApYJpkqVcwehRv3wDpump) | 0.35 | 0.04 | 3.53 / −14% | 4.9 s | Harmonic `CQdLgw` | guard fail | -0.0005 |
| 61 | 10:19:56 | [FbeSRm](https://gmgn.ai/sol/token/FbeSRmqXqJoxcgXkyzDF9HcApYJpkqVcwehRv3wDpump) | 0.35 | -0.96 | 3.28 / −12% | 20.4 s | Rakurai `ana2y2` | guard fail | -0.0005 |
| 62 | 10:21:40 | [6qLZ4u](https://gmgn.ai/sol/token/6qLZ4ubxZiUQKawLnz9UvLzPDm6GbaG3fjd1ky22pump) | 0.35 | 0.74 | 3.43 / −15% | 192.3 s | Harmonic `CQdLgw` | guard fail | -0.0005 |
| 63 | 10:21:45 | [Hhey99](https://gmgn.ai/sol/token/Hhey99KDpoyRj552zh24dWweb8Xa8WnkygZQeQMD2b1R) | 0.35 | 0.12 | 3.27 / −12% | 2.1 s | Jito `E1r4Ps` | filled | **+0.0031** |
| 64 | 10:26:36 | [F4qS5F](https://gmgn.ai/sol/token/F4qS5FUjAqQicHmRLt3SiosXtLLsWMwYpVwyQLvKpump) | 0.35 | -0.90 | 3.40 / −18% | 25.0 s | BAM `9jxgos` | filled | **-0.0022** |
| 65 | 10:30:46 | [EMFE9j](https://gmgn.ai/sol/token/EMFE9jkQYhjTgKovbqQpKovJbyznUDTY5EeTkqvZpump) | 0.35 | -0.76 | 2.04 / −8% | 24.2 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 66 | 10:35:37 | [2S8o2R](https://gmgn.ai/sol/token/2S8o2R9MgSeatFy9hsgBZcDjn3cqWPe6aXBY1BuHpump) | 0.35 | 0.19 | 5.89 / −17% | 162.6 s | Jito `C8Bey3` | filled | **+0.0199** |
| 67 | 10:39:38 | [8nFMyX](https://gmgn.ai/sol/token/8nFMyXCpkfzXspnYHAqsL5FXxgVoE3BvnDq7QNSNpump) | 0.35 | -1.50 | 2.70 / −9% | 28.2 s | Harmonic `Awes4T` | filled | **+0.0417** |
| 68 | 10:40:27 | [8nFMyX](https://gmgn.ai/sol/token/8nFMyXCpkfzXspnYHAqsL5FXxgVoE3BvnDq7QNSNpump) | 0.35 | 0.05 | 4.78 / −12% | 75.9 s | Jito `C8Bey3` | filled | **+0.0108** |
| 69 | 10:50:00 | [8Dbb9X](https://gmgn.ai/sol/token/8Dbb9XgNv9Yv5U3x2YEBLdiryJqA2ns2EsHAGtyyiJJW) | 0.35 | 0.38 | 3.03 / −14% | 2.8 s | Firedancer `EvnRmn` | filled | **+0.0903** |
| 70 | 10:50:59 | [3btsos](https://gmgn.ai/sol/token/3btsosjijGQse8HcUsLcdu67ggtQyRMwKgTqmzpEpump) | 0.35 | 1.02 | 3.69 / −15% | 7.6 s | Harmonic `HnrXmm` | guard fail | -0.0005 |
| 71 | 10:51:55 | [DJVk1p](https://gmgn.ai/sol/token/DJVk1piu8yxyhBs1edwUAL1nzLGN6DMvjuYPhRzapump) | 0.35 | -0.85 | 3.77 / −15% | 4.7 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 72 | 10:52:00 | [DJVk1p](https://gmgn.ai/sol/token/DJVk1piu8yxyhBs1edwUAL1nzLGN6DMvjuYPhRzapump) | 0.35 | -2.20 | 1.33 / −5% | 9.1 s | Harmonic `AurseT` | guard fail | -0.0005 |
| 73 | 11:02:40 | [BooYQX](https://gmgn.ai/sol/token/BooYQXU1H95corSCX76wBhzbSnUXTJ6QFySbMaTxpump) | 0.35 | -0.46 | 2.87 / −16% | 26.7 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 74 | 11:05:13 | [7zV7kk](https://gmgn.ai/sol/token/7zV7kkFkEEtzqAVHtpsrE61MskeNTZ1PT3tCpyC1pump) | 0.35 | 0.52 | 4.95 / −16% | 205.8 s | Harmonic `JUPiTE` | filled | **+0.0333** |
| 75 | 11:05:59 | [7zV7kk](https://gmgn.ai/sol/token/7zV7kkFkEEtzqAVHtpsrE61MskeNTZ1PT3tCpyC1pump) | 0.35 | 0.30 | 8.57 / −19% | 252.7 s | BAM `9jxgos` | filled | **-0.0094** |
| 76 | 11:08:14 | [HbeVG9](https://gmgn.ai/sol/token/HbeVG9HbXZu2nwVQNTUghVR78Grw8vVk5kH7D6X6T7kE) | 0.35 | -0.81 | 2.08 / −12% | 6.8 s | Firedancer `EvnRmn` | filled | **+0.0277** |
| 77 | 11:13:47 | [FosKoV](https://gmgn.ai/sol/token/FosKoVJVpKY3s8FQZEVQWrhFV6n2Em8ohN9bUFAEpump) | 0.35 | -1.21 | 2.92 / −13% | 3.2 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 78 | 11:16:40 | [3oqmEv](https://gmgn.ai/sol/token/3oqmEvNtEM8UwjQEmU48KSneXsmWxCZYfT4NJVr2oB2d) | 0.35 | 1.47 | 15.23 / −41% | 200.8 s | BAM `9jxgos` | guard fail | -0.0005 |
| 79 | 11:36:11 | [7fMU88](https://gmgn.ai/sol/token/7fMU88S4P9zwXfYdWZY1mpwp8RyojFm5Lfv2pCYBpump) | 0.35 | -0.42 | 3.35 / −11% | 22.9 s | Jito `E1r4Ps` | filled | **+0.0184** |
| 80 | 11:38:41 | [F1G2bH](https://gmgn.ai/sol/token/F1G2bH4tSobuBcuaokhC34H2TouCrd8EYaeaAn5Jpump) | 0.35 | -0.71 | 2.31 / −10% | 14.4 s | Jito `A9mvuk` | guard fail | -0.0005 |
| 81 | 11:38:52 | [HEncXe](https://gmgn.ai/sol/token/HEncXewxJ6FKRNiPxvKYKY3WCo4jutqDEFvRtpTapump) | 0.35 | -0.21 | 1.88 / −11% | 8.1 s | Jito `HEL1US` | filled | **-0.0253** |
| 82 | 11:47:44 | [5hQrPq](https://gmgn.ai/sol/token/5hQrPq4gqP5DSyHNzm2URsHcYfP65Ye1KXbo9S2tpump) | 0.35 | -1.08 | 1.88 / −10% | 3.4 s | Jito `HEL1US` | filled | **-0.0047** |
| 83 | 11:53:32 | [2LVYAf](https://gmgn.ai/sol/token/2LVYAfg3ZtgFLp2B9QrTZy18sVzxqmocNmAgBS9Vpump) | 0.35 | -0.40 | 5.95 / −20% | 3.2 s | BAM `2gDeeR` | guard fail | -0.0005 |
| 84 | 11:57:32 | [EWoDKh](https://gmgn.ai/sol/token/EWoDKhGNC4ugbAJxU83BfyF6ZgAxxLKeWatSNApSpump) | 0.35 | 0.07 | 3.84 / −15% | 25.0 s | Harmonic `GZ4U21` | guard fail | -0.0005 |
| 85 | 11:57:34 | [EWoDKh](https://gmgn.ai/sol/token/EWoDKhGNC4ugbAJxU83BfyF6ZgAxxLKeWatSNApSpump) | 0.35 | -1.71 | 1.65 / −7% | 26.5 s | BAM `9jxgos` | filled | **+0.0316** |
| 86 | 11:59:57 | [3zZ31Q](https://gmgn.ai/sol/token/3zZ31QmFjgveDzGUWka8SQXU5UPRVpqMAGiGLFg4xVYt) | 0.35 | 1.15 | 2.84 / −16% | 3.8 s | BAM `JC7bH7` | guard fail | -0.0005 |
| 87 | 12:59:55 | [EWdT7e](https://gmgn.ai/sol/token/EWdT7ebn7s5aoy3KVVa2tdjfLW4vgkkpBzANia4zpump) | 0.35 | -0.84 | 2.43 / −10% | 17.6 s | BAM `JC7bH7` | filled | **-0.0301** |
| 88 | 12:59:59 | [EWdT7e](https://gmgn.ai/sol/token/EWdT7ebn7s5aoy3KVVa2tdjfLW4vgkkpBzANia4zpump) | 0.35 | -0.51 | 4.03 / −17% | 21.2 s | Harmonic `TopjgY` | guard fail | -0.0005 |
| 89 | 13:00:53 | [EWdT7e](https://gmgn.ai/sol/token/EWdT7ebn7s5aoy3KVVa2tdjfLW4vgkkpBzANia4zpump) | 0.35 | -0.69 | 5.04 / −21% | 74.6 s | BAM `simpRo` | guard fail | -0.0005 |
| 90 | 13:42:02 | [36T3Md](https://gmgn.ai/sol/token/36T3MdZiGBYaekskPNEhitDvds9BvY8y5kiw8qKopump) | 0.35 | -0.13 | 4.34 / −14% | 107.1 s | BAM `9jxgos` | guard fail | -0.0005 |
| 91 | 13:46:06 | [36ctdA](https://gmgn.ai/sol/token/36ctdAsbjp2EHqGSBjsCquXptoPMTVVxrJRi3Awtpump) | 0.35 | 0.02 | 3.64 / −16% | 22.5 s | Jito `C8Bey3` | filled | **+0.0248** |
| 92 | 13:47:15 | [AAhR1f](https://gmgn.ai/sol/token/AAhR1f8m3kzU2HHtKxoTRJ6s8ER1tCW9X6NBt4ARpump) | 0.35 | -0.23 | 2.05 / −10% | 3.2 s | Harmonic `9W3QTg` | guard fail | -0.0005 |
| 93 | 13:57:34 | [FY2Yiz](https://gmgn.ai/sol/token/FY2YizZ6sqwSqTRyjYH4rUHtLZb5mZcCd6kdhvuNpump) | 0.35 | -0.82 | 2.10 / −11% | 3.0 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 94 | 14:06:11 | [6hCM1N](https://gmgn.ai/sol/token/6hCM1NmAeKCPqKAGZXyeuKebLtdiyBnsABifncL7pump) | 0.35 | -0.29 | 2.77 / −13% | 4.2 s | Harmonic `shftkx` | filled | **-0.0362** |
| 95 | 14:23:51 | [9RmUWh](https://gmgn.ai/sol/token/9RmUWhCXBdLU6DvA4PvjKMSc449RFstYzxdeXT9ypump) | 0.35 | 0.27 | 5.35 / −19% | 122.1 s | Jito `HEL1US` | guard fail | -0.0005 |
| 96 | 14:24:41 | [4iiSDr](https://gmgn.ai/sol/token/4iiSDr6iWQ2mkat2hmaSBTeSb2igboxy18KtB1bRpump) | 0.35 | -0.20 | 1.94 / −11% | 5.5 s | Harmonic `5ZqveV` | guard fail | -0.0005 |
| 97 | 14:33:39 | [weenfq](https://gmgn.ai/sol/token/weenfqxyUHQ7heP1Pf65WNX2HhWDpSdggebiPDAgvTq) | 0.35 | 0.97 | 5.46 / −22% | 3.2 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 98 | 14:36:20 | [dmoUSg](https://gmgn.ai/sol/token/dmoUSgTfTukefwWDhvsjKQazHyjQDjD29QRpxzepump) | 0.35 | 0.42 | 4.44 / −16% | 10.4 s | BAM `AiDoLW` | guard fail | -0.0005 |
| 99 | 14:39:07 | [9EUgnv](https://gmgn.ai/sol/token/9EUgnvAaZCTsps9hS5DUrUBkqinviJGUNngCrcXspump) | 0.35 | -0.49 | 1.27 / −8% | 3.8 s | Harmonic `3ytgyJ` | filled | **+0.0096** |
| 100 | 14:47:56 | [AvzRnZ](https://gmgn.ai/sol/token/AvzRnZZtctd4ZhjKcJSQgDMAFQXNn1mYaxpJz2zSpump) | 0.35 | -0.34 | 2.00 / −10% | 2.3 s | Harmonic `FNKgX9` | guard fail | -0.0005 |
| 101 | 15:07:24 | [2n59Hr](https://gmgn.ai/sol/token/2n59HrcdHoybinAPTP8h9qkEoztzzLEe8jXJ1u4Upump) | 0.35 | 0.22 | 3.47 / −14% | 7.8 s | Jito `HEL1US` | guard fail | -0.0005 |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 43 | same | 2 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5S2ningatp4P9GAexxPskQN33sYz9nbKvHKX2iRqodynYpLZjzpVb9Cre3gCZ7PyNomZfDerzaaUPTynuAN9YFZR) [sell](https://solscan.io/tx/4EJLxWHzcLjQr4R3Nqd3UpSiWEuTy4ngPekWNku2Ncgq9YY9HZ2iuvPVGVKyF7j7yj4mfZorZcY6MoBjemm7GoQ) [dump](https://solscan.io/tx/ZWmRD3euXGsKn9pUf29CFcLnC2nUVPhvyekboVwuA2W8QxQkt49oDmnN6i5bTfxCfa5AedKQEa7izSjsvn2Qbhb) |
| 2 | 80 | +1 | 0 | **nozomi** of landx-fra3+nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/5WZtSFfejdiqXAPnUwnt3bRr13AL5M8QDWdt5MpQUeSPPDfpeAiE4d1xhs1hVDQneFirCk7TWYq8aHp12TMRZWm4) [sell](https://solscan.io/tx/2829EdfnBN86LjneksiY3CjcZEqwpqtdfRqgqwjCDjySBJ23SKY6nC7afCKTCqWcnHD4kwG8Fe1hrUBYifDK9aoQ) [dump](https://solscan.io/tx/5qBBRCn4AkYq9jMoBQcpjmYuJDou17yyuPJiAKHPDvezguT5z97iFNxotrr9dVpt5Kzw4C8fremeCQSXYz6kAyPv) |
| 3 | 36 | same | 3 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/47AbFuJeRoQwRmsdfRdzmzyHfAM7kaEUW1bVt6TXL7W4e1KvHvrYXPRamWyAGtxC5ctt9wm9kvFgiZr6gHGC71Gi) [dump](https://solscan.io/tx/VVELgbcgtn5F7c91qMNp3tPgU1VCRLrycbqbRSywtxMipRu6TMTwYdBxceKyBDrMD99buYRr1wEPXqpy7haCQxN) |
| 4 | 21 | same | 1 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.2 s | 1 | [buy](https://solscan.io/tx/3MjKRyDyeoRv2SwGVyshYc5f2AwfLe33Ubva3kYN5LTqQoZqDxdbvS1jMCvTsMgYJRAqGpVw65s2er2uLS6EMzhc) [sell](https://solscan.io/tx/2DMc8XiJvpe6vgxn3c2pzmaaG6zdphHgzaCYPREgLN3t8wDA1gFScefoekgQZDjZJBjKY5Rin6jTpHsTTS7d2omj) [dump](https://solscan.io/tx/5Gsy6h27KwuLMfnqMNrdQihrJxDSsdi8YcUgPXa5HHTakRmUUmgYYEdK4ssNkxKGTvtGTGsWEnhBkvNkve9uyuJW) |
| 5 | 22 | same | 6 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/deFCHLxKnsynPyvgXsoWUFM8ZfMGaffcUGumSNHTUUJMewFp5xTw148CtnTvZaMbcJrtgwemdvusiEHE5FyWLgy) [dump](https://solscan.io/tx/5ee7p3LpVJKkinCPQ9FLELdrqPRgD2TRTNKF2qiPt11VS8sd73a6FpQgGS3eEmXUBdHi3ZUD1U5MpyCao93cRS2R) |
| 6 | 73 | same | 7 | **nozomi** of landx-fra3+jito-bundle+helius+nozomi+staked-rpc+helius-swqos | – | – | [buy](https://solscan.io/tx/3URgfAeL7YFPJBD1FePv8nktisfY1FkUbdSGV5rTsi3aUACSFgKCPC1GuS5o5We7Gw87hj2VJMHysKAPZWkVtGze) [dump](https://solscan.io/tx/3yEinCLnRbSAjsDtykYEwa7pFN4Do9oFbzPaW8qgR2aXPhmUeTk3qPcnkhy1bXQoScNmqRWzjv9PLrKrfFZo9Bus) |
| 7 | 148 | +1 | 8 | **helius-swqos** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5kqZ4fq9WThSH4tBoKH1GMZinXuEk5FapmvK2pse3jno5pK6jrEQZ3b3HtHAaDxZ2WpYYWiFyCAieezbnJgm8Te8) [dump](https://solscan.io/tx/5uw6W27dqchHTB7XSiTrNpu28LKev699D2R4mx9bNFUMEwyQn9dVzsDRnzh3GG9myUbt3Aghud8zsy7XumqLSJed) |
| 8 | 60 | same | 3 | **staked-rpc** of jito-bundle+nozomi+helius-swqos+bolt+staked-rpc+helius | – | – | [buy](https://solscan.io/tx/2cbXWUEo6QQ5ZZPfAknPtwP8WRbM8jSoaqQ2r6gdQhoDKRznVTxuNgEcUWVbDt7LrAioZ5tNqps4s3cAWtr3JfP6) [dump](https://solscan.io/tx/EyjtNW6Hu6xy1ZCpyhx7Tg6pzdiettuoRagM2dcNat6VtserQKhiFWFMvU7UXTgtdESi5ZdMEPJ5zAMVKSgg4c7) |
| 9 | 90 | +1 | 8 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/quwMwwcRwP9DH4gCgdt7MMAnkmB3kh4T7Hjmne23M6pkQkNE2ZEWHdw9nV2YAmh7UNdGpNTpHmLiGyQSC4DqPet) [dump](https://solscan.io/tx/KVq63xqbJv2bxPALu2cRKQ1cgJ6CmXvRGqxbtxbtg5RV4R8AuLesrvNidTM7K3hrvkCSWHWkxbbQCKYR9PEiBjj) |
| 10 | 50 | same | 2 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/2ywyPiUo9A99b5mdWEruN4rc3ajMvyHwsvWjZg5E4QsqdgZgcCMEu3KzFyUKa5EASGoMjKUGpE9zxH2vmV89TWEB) [sell](https://solscan.io/tx/4ksua7BVadBw97BQerTsa3hgPbWK1yQNiARykyA68uQBmqVEJ1QEW5vfPCJpBfg9JAFjYYvFAF9Ksg8b6cndSFeZ) [dump](https://solscan.io/tx/hp2hNj85dP37y6TpbFfJ8zXkQXneUcihjt1e9VoRJmVRjKX3yp5xXJhDeAQaeEbM7q9xvXvP9Rx4pvrMzPsFCYe) |
| 11 | 121 | +1 | 4 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/5MYWbMvtoSGKoVz4xrc5BKgLpXHeGQbDd83UA4KBKcB7RieFCkUmbHSdNEt47tMLkh8MCCv7oBi5EAWXaRS3TLcZ) [dump](https://solscan.io/tx/2KaAdfixonVLQ91wg9BfZom6sSMTDHkZj7yy9GVHWTfUgi6Cmtt55cnBwUCkK7nKYaH4heWpSuuGMfmjagUsSejb) |
| 12 | 118 | same | 4 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4MhgYkEP6ZBFoMdHuUCnLnxX42fxbko89yQuXvbMaULFXLqE8ioZYjMZ9fJDKt1yywq2Pz7Wvpd57wWoMovPVQFy) [dump](https://solscan.io/tx/4RsPEBZo9Kfmh87pH3aCxVAjnr6R4aC1YrXfyCRsAknJAF4kPWZxSQ6BBpjctcXm147PzeCbFTJR22krPbbkK5FF) |
| 13 | 39 | same | 3 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/2aELm748uQVabYm1Y7zoDP5HLodfEjZFLK2Xpggpyr9vxEVHAJf6baEGDuqXMQiwrRpoBjnYQ3WpwdDCA19VhSTS) [dump](https://solscan.io/tx/3Tsb3s3Jem1vTBRBE5tnvr9jCs9W4ZaPYuE1xM8yfBotJdqtN6KJhgGsP9pmr2zYmtWCH7kVcKyTRztD7TdQh4Dn) |
| 14 | 33 | same | 3 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/2xATqtcYVWvK7zu6inHJCR27jTb97rAu1TUnKWimsgBvizP7p8r7DY8UgPMJ2yAEuGGFvNfMfFWDfx2DuhiLxQBU) [dump](https://solscan.io/tx/2qVp45LH4rEgeFuUmR6L8uDPhuHgtFAptkwNyRQ4dnDPuaPqEDQ1wPUrZdNsMSzTF1Lqcu1uCwHaEpPQ7ZTRZ1nG) |
| 15 | 143 | same | 4 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/wHwxqpfng4bux6MFM9PJeiaNpi69wANprY7BGSdFsft2qGFQXWsAGgdsG9UZpruAz4JVHiQFiFPBmPUWm4yJn6H) [dump](https://solscan.io/tx/44vGUYKy7Bps9K724zDPe4S7P1ka3kabhe4JqC74rWDgeeVngHjS5RjsNmoKz65pS92w2pvCYUJBi38y1ntDCBgm) |
| 16 | 45 | same | 3 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/4TWaeQFLHUrCJKjn7LH43mAdkyezw1TtU37xUQ2fECJG4xT1f3fbLFZA3fiXXNigS4QinmzMkBKDtZzK6EWmVUYu) [sell](https://solscan.io/tx/3WCFtvJRabtY7n1hnU6cgxHSz4WnSDboURp5TQp5dFzCGkVAEDEH3UwfqFdbar42ppdSbsYC3atcNL3DSiHYoeug) [dump](https://solscan.io/tx/4viC9MLSNRUKpMJhGjsV2BKS9WAF9BL1pUQeahUwnFFHQATq3F2boCs54hN75aZWsjyx6zrZgp3DQE2kL8YqhTeb) |
| 17 | 19 | same | 0 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.2 s | 1 | [buy](https://solscan.io/tx/4WcCQ2WhVfgwNe1o4Yz3yEZqqLheukkFT7ocKvAnNJfs4w9zEYq2Zf2E8CL5eZsowmWoZhJD7tHkdZfziJNo8upw) [sell](https://solscan.io/tx/3rL8BLfEWU128hdSm7xaFC3633FqfauufpcKWrk6c5aNdexBJGxBDoK4H9TKgqtGModQcrknsdxKmH1ChjcNgX9y) [dump](https://solscan.io/tx/AUAiWdvUVj5GsTa88AeQsDpEoJCX3aE2XRkQ16yYLp7QVJdqBiEzw8eVyZuTKgzLp9syr1jDaxyzpFJ6DyUq923) |
| 18 | 39 | same | 2 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/5NGSLZkJ6d9yc2GBBfzjJfhyMq4owupLw45byQvMKf2LKVCDhiqenXy1Z7pQtimZNqi4sf39syTzmAYMM1dXGM3G) [sell](https://solscan.io/tx/4Tx5NBhicmTVmTDwR7Q4z6Xovk2xmWWCH447dEWZMUW1UCmdQ5fip4HM3Mz3t3gZ7uXUFBnj2VycsgYPvxubpP49) [dump](https://solscan.io/tx/5iRiZFjh7RivFo1XBMhZamaDKcgHyxzZDRVad3RgwMKuULbUpqcpTav8bFT5mg3T8akCH7q2zKPD35WCyFRNd83e) |
| 19 | 18 | same | 3 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/2DGTYc8gM1LuEd2VKLHS9sm3GNWRczFb3799mFgtZ6K6zDc36GTnpygLouxZ6YNgjnJ1qbBGUfFA4a4T1V7eZYxk) [dump](https://solscan.io/tx/46Gten7QjTem3D1q76JDrq7GisweWh5DGrWk7jwXQx99jWn2HxRyn2fDmd7mX26AmNjV229CHLyLYw5vxFYgpcun) |
| 20 | 27 | same | 1 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.2 s | 1 | [buy](https://solscan.io/tx/59eSLhNjVmUxFVPQWYrR4i9CKPux2DR1eam6hq3P6XLLARxf8q7GtV6apfSUbw54tibPxrzNa1ozrxdaJmdhxrcP) [sell](https://solscan.io/tx/1JproGMn3SbuTw3f3VWATAcoehU9T3Kdb8165r3MSjndr6izyww4fRVyoV8Jz3dEBqggDDZgLK5iQo8phUiWFey) [dump](https://solscan.io/tx/3LswDC4xy1HGCQgzkBrTiRiKZuAHrBRoxFsmugn9N9b2DKw4ZgG5XiqDL4dfF8eypmFFTbDV9eW4dK7Znh6mZq9U) |
| 21 | 44 | same | 7 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4zjyw3zVJ1qSait5mWgTPq1isa5TeHmb4v8yr8aQWmT6wpN7EPSzhTEZyEBVA9EHTsKB1kzivTFSWSMXeiFXGkKr) [dump](https://solscan.io/tx/2eVJoc5iXfT6cehLv8PjYzhd9DcDEv7XfnyLwodwcTv3bW95t5h8SC9a5DmctJwKWT5HJciugnRfmSrtyazzswYf) |
| 22 | 41 | same | 5 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/2P3L7qKryEUzAXGDPURQJa3WNoT7UbBik1MH6UFLF7SySn3oTkdVFXooGavWEpwJE11Ntr4NonSPdWkyXuabKA6Q) [dump](https://solscan.io/tx/3yL67PX1R1iZRs62h4ohBsvyLJzhToTFsjBnb28c6gcyG1QbqwMFSVNMbxVKSNks4SPomcy2dURbSWWsyiABM6S9) |
| 23 | 205 | +1 | 7 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/22cuXG7KbNEziKmDTEvQoA3W2CJ33MHaENr8y6iiBCdwv959N7ThN8eTKcXv7v4QAijqN4QnnYqBkJvwc6oUw31V) [dump](https://solscan.io/tx/3283D2uCoymx5XYc6CDt1hv2MCppNPmx4bmuXMMobYptC25QyzgyXeRAkKAoHqnesHvpiKKLeRBUPxFjtHML3auP) |
| 24 | 74 | same | 6 | **staked-rpc** of landx-fra3+jito-bundle+helius+nozomi+staked-rpc+helius-swqos | – | – | [buy](https://solscan.io/tx/BxbW6QbtrHpE9UedHmBmyg6xjByswPZdATNDwJY8uc1qD5pMwmq3UachJX7GYC2xd8SazJ4WCNpVXdNJubkc4jn) [dump](https://solscan.io/tx/5uXnpWxLjMkWMFUwQw9kMNcPMPYxrdYTr15g543kzgMR58qTJEM7xDWnYf7Q86zEorbz4UqauhUhzMinNxMNv46V) |
| 25 | 13 | same | 2 | **nozomi** of landx-fra3+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/5KLxfCH2WymaAC3JaTADFE8qNhi528eq76WKhKEqL5kq7i5dC1pbsSSVceRuMS3rgbgGVn3Z4ofKhzioQGuTwxC1) [dump](https://solscan.io/tx/2JcWmdprUpnvgE62HznQ5CyL4K9FrgujQViT9GxqfbegCM7wnLoHTpGJtf8FPU3H3WXrjXrtWsbnS4XnNV3essKA) |
| 26 | 77 | same | 3 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/525DaZ1wj2onBpxdZ5bRLP5GivcwPFR3WvhAun8zMKvfTHqwemCXrgxMjjK9K6c2CzZDVx9jWZgq7mT4Uqy9Jxjb) [dump](https://solscan.io/tx/pzdJ1k1mvEkT6Q81pm8ubJKYRAYWnsmvSzuSnW6xLz53yk4DJndX1xw7kFnE6VNvgWCM6GUANaPdLPerQyQZ4bz) |
| 27 | 54 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/QSDfBz7oUhC27khZJQBca4US4VCBr5FEcQpisacgDLnz4t2JPFFLrKuE15asCvaSAAu3f5dWJM1trbyCfnfFtUK) [sell](https://solscan.io/tx/43oFgGLkviZ3icveXbT1qShhmnBBq1wtNRSawYkuoY8MVQ5CL8YMo6CwdAYxu4vAE7sMnK56Jv2QLe5TYT86oHqB) [dump](https://solscan.io/tx/DChXGi62F5aEVb4ukenVsqHeZPaFgHRDa9p95b7hFSk5rb58CquFjEfoKvPS1zPgiA9QqEiiXqWvsq1VDJkFjoz) |
| 28 | 45 | same | 5 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/jCfqJE2UHMMLsaWrtPBEjvvBNRjyiUCjJ4jP9FQdnGLE8La92qWtu2DHHu28mZ5uqi6DqFEhGiqAxR3aAhjyvVN) [dump](https://solscan.io/tx/41iGX3bCEx3oYGF9Ers4GzmfpMStsNa2vSGTe2ZAxY48FinxMZrebkWeEHw5oW6tkeG4yiUcugmvCLj3qb23QA5C) |
| 29 | 87 | +1 | 3 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/YERwoHAyHGkNY4BBoSDGh6cbUYV4ydztJ4DL3k5JuSBsc64fvA2JKrwj9kNbi1uheXgyX66pgdbo12e3S1UNgnc) [dump](https://solscan.io/tx/5KGMCeyZp3xE44R1nPPstWJyqn7jrDwqWGodf6baSRB64UiBp9Vpzb9erkebN5EwqkzkxRqLxZDZdw7qFRbEcWo3) |
| 30 | 78 | same | 4 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4P39wURZKYFXGMXW5efgbrNCBrw7RRUm5xN48BkTmJ3rXyLKTYYTV8LWVmks5hFwqkseNDuqMJ8QC3T2hFMfvZq3) [dump](https://solscan.io/tx/4btiShZXM3TntCe9Ge6RJ3iw4Q2aAijZgk1GrPZowfzYjt1h2TdaHKL1UVYmPUHU5CE3iCH7BRVJYiC2P44hfv3C) |
| 31 | 11 | same | 1 | **landx-fra3** of landx-fra3+nozomi+staked-rpc | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5Yif8zBzPuvNiyDZF55rUEb1Fgu9UToMtc4A9gWKjtFNGoJ7KTnB4quNpiW7GmAakHALHKgDeWwGvufQKQ7Khkzy) [sell](https://solscan.io/tx/622KuTw8RX9BKo4rdH4ouFQS9BSYJSz86pxNRCdaBM1vv4RSvXsYMdKVH7jtUB2AUoazDSTB76HXeVfWAqtJibLL) [dump](https://solscan.io/tx/2gJh5mimwaq1vsMhuWaXTMbkVhVhZ5SFyt1qVB6s8F3BjbvUUex9eXgj4QYbkhYgE3ysXRFuKY1KKGm24cUWsKyQ) |
| 32 | 22 | same | 0 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/3KBDATFbxpCLTjppsVRXziv5ZvVwhvX7UrTQV9joxsqXtNLAPeEqcLLkzT8SqKFUbd5HXZgt7R9sdiPh2E5qYaFW) [sell](https://solscan.io/tx/59Uspu2D7cPyjqtBgKrKjffaKyZwGESNjU6xfVDRqadvWhgYTRwLqAoX3UVPL3yAnsxpW1MbsnTsALyZKQZYP14v) [dump](https://solscan.io/tx/2DcYXkWy7Xxbk92EfVB8iCfz7guDHJbakxsSHSPEZwwWc6qyysjSR2VjP86iiuKbRiNpJXoGzTV39uicPuGWf9X3) |
| 33 | 30 | same | 3 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/3bryMbRV5HwAiSoYw6cKjXmUp6QN6mP2q85chhTRuTxHYZbeSXWDExmfT2MSX8NQ8v6Dtkk2hhakyp2s6WmZhCm7) [dump](https://solscan.io/tx/5JChyn7qDsVcokobwj5yWw3PXaeq7WE51xJ5tzhvKCDU7JFDjp7GPbTCmN3qWDEWcjvC1MZ8oXTqFraSFkEBaay6) |
| 34 | 27 | same | 1 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.2 s | 1 | [buy](https://solscan.io/tx/56tPyPsweRcKqVud64Uqpsh5f2WPwaAUKwyM9kQThTG85qdvR4NBo9dbEjHCytCAM5N36eB9Gocavrie2F1wtChP) [sell](https://solscan.io/tx/4bkWk4VEzXChuAjKoX6mWeQwgMQ6u8Qq6N4t59iGWvjAjdkEsooXv4nA9ti9HGuqw7eVs3pQfD8ay39PxojSjUgB) [dump](https://solscan.io/tx/3mffMH7PsShEbQH1fApEJFQaqeeDdsjT215dgXXsSY1ZAKBoiTGLuHRcmBhTsL1NRZx1LbD18JjuRvxn2uZtnAP9) |
| 35 | 224 | +1 | 2 | **bolt** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/59CsskiXkXDT5MGTFFSDtmvdVGA8PEdyFhToXbbSAchSrXkJ16F1jourBHKHqzVbQYS1NdZcgnH8CuGrgVfqHkFB) [sell](https://solscan.io/tx/2vjdjZ8CHdCGajUpsMhQcRk1Kp8yz3Ju8Jf9qGaYEz4E8FT4qeDDNRqoB9mxPRJpZzKJJTA9nvRpb58R3wCb4idV) [dump](https://solscan.io/tx/5JayygNKgBcpFt5ESqeNoUaFBzj24PvPW8bof91XKfTsNhJLoiCHgBqKkfeVxCmi7S4C8uk1uqdXgD5DzKtzmea8) |
| 36 | 31 | same | 0 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/4efZovb9hRVnRTSpfw7jyCBVJvZP4Dpzkemr7mib8TNd1c6HJA1XyvftH7ZsEkPEQZDzxegnxjTNveoDF5eD4eeP) [sell](https://solscan.io/tx/2e28GRYsGoZQird3i791vnzrphtx2VPNSAWP9PUrVL3Xed7VAj8XqYGSMPQuXjvwmHN3NTXS3XBRJgA7XSkpb2M3) [dump](https://solscan.io/tx/3gmg4bmo2TE7Avid47QjqzJEE464b1ZeugReezcvrCDZLP4Xu9jFLP6mXV1U2z13P3xGPd8TJH78QMSn16f1DwjJ) |
| 37 | 36 | same | 3 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/592icNtq99LrQAbSedreRxM2zgGUv6ew2o1foE1m6ceQPVibxWASYkTFWCH4EVeBt9GEtmYDKt8wqnpuo7vvxB1M) [dump](https://solscan.io/tx/5a1NAMWS8SHCj92S9kiE1GbTKub9drXxGr1XkqHb7UqjaJH712JKtRfFCVEgXeXEAjzgVJZqLvhqrDRRCPxNkSPc) |
| 38 | 29 | same | 3 | **staked-rpc** of jito-bundle+nozomi+helius-swqos+bolt+staked-rpc+helius | – | – | [buy](https://solscan.io/tx/3NS6n7iFjFx347KrjudVeS1UQq61mP6smBCnqigJLmZd3BEx1Ns1oH1KEmtjjt2JrSxghxnVJLidctCM7oVWxpmD) [dump](https://solscan.io/tx/4ikUT5unBYTAWSJnjkYHQg4Z6cgrsyALYNgEzS9SUspNEcW2NTHzr2LFDzSBt9UvGp3k6Y64aKgJ7WGpP4goiGss) |
| 39 | 132 | +1 | 3 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/379sN6DuHduxaZVowtCEJQMMFLbPUpZLpwct2awhX25bARSxfoeFFDW8rs7kZMWPnM43XkSF9hZpmukKbcMXx1Ky) [sell](https://solscan.io/tx/5XC5jTJi8vf3BT1nCqHz82kCeAwyYfJFwQcDMTXCowoCv96H4bggZWWq4XJDxUWRVH6yaSoaTT9BEh3BZ6WDLwFn) [dump](https://solscan.io/tx/5UWx4NKfy3i5bVSq1fF4zig9C6ESxkDKeJcoCdFZXrJcWiGSwMMcAuS6AWer6VUzoRfouaxfEhmpacDcNmc7Svc3) |
| 40 | 155 | +1 | 5 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/2v968qq716eQ66t4j7bvoryzuupcGBxPXgCtbQahfK8dMBioS9dhyfDMEqwxErJ7P5Z4UbnYCzSJxXmLrGQmTozr) [dump](https://solscan.io/tx/5RZ8FhFxdMzvYmzKbGVhJsBrUgAVLJXSJD9JzjYGVGZ9MPTBso3L8rvhUhZeuBR9ip6v955xyqvmuG6kzWftCYFW) |
| 41 | 28 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/2hz6f1Z4FLF48gRznGfn9Fdbkw6Ta6XciqZE9W4sUk21Xe3H9NHbAdrWdBPLJuZ8vzmgvP6LMWBkQW6R3wNSrJu6) [sell](https://solscan.io/tx/3wavtjtG75BV6ztCeR8SZFWfHkDQA3GZ1PQ6tn8L9w6vJxE42QBUQp6NEKQPPTa8FinJ8U9B3JQXfpKbQJmcMNC7) [dump](https://solscan.io/tx/2gXT3MNBccHWgFdAWimtuMBx5HDHuNfcK3HAxdNA3UuoBekZwbH8JDewuwL4LYFy5k351RHEuLAY5X6bz9rpHksQ) |
| 42 | 51 | same | 6 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/xnwfnBTN3diAwQQ11u6gPUMaDrVPaPQz2i8Neb8XkXdVCy9ctGx6ZvNprB7mqUqwRKdHXP8NETcdGawZdPqvTs2) [dump](https://solscan.io/tx/2F2wFZodt78SGmXpBHM2TbpNkoJg8uUUtyzne33fn53huceRSqDM83KA692TTqSNu79kkSdj2Przza9cVK2SwDF7) |
| 43 | 24 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/4tyPsZfgP1jLuAh6Mvvq29aZtNxrUVRQTduBpNsvuKBz3yXJVAna3kuB63FjA249fyvk2xPCrzbMkGo4CWtQxi3i) [sell](https://solscan.io/tx/Ay8Gms84s3J6wTaqK52qiirA1AnXT48USB48aESUS4kWbG48FhJ1kX8gtJy1DyejJ1U62kWbXK9vAMokooLZkzT) [dump](https://solscan.io/tx/4dYWKZCGNsK1H73DvN4Y6rER4GSUymhmqi7xJmSx2WSbMnWpvqcYNwHTn3NjrtLfibGepeXYmfDQsk7Z4HQaV4ZK) |
| 44 | 48 | same | 5 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/GvW17r3CXh8mYMjUqExNymuh742fbc8tfRpNH8SV9CdCrQy85t2msvYLKUKpVo5AnDDBSyJvMB5dTGRF9KdX5hv) [dump](https://solscan.io/tx/3vUfyXUuJ1RFQzxdoiFAFQQoVCKFAXYp4QyeEe6bHbhFqwCzF3JXGwp2TAgN3tsDeDJV8VZYiTbaJFa8wLo995UX) |
| 45 | 66 | same | 3 | **landx-fra3** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/3p18pu8ezoD9oYn5dQY5Dw2pQ516m9GzFvA91WUzeZSsXc6pqhLMTnFdBW6cujq6WcSYS59VsE1pdUQuRzbqZNaS) [dump](https://solscan.io/tx/3EucRufxyCfn361K9WRq5et6tVy9sq6xBuxmiXW9aq6Wo4HVJtZ8GtYYgE4NYSuaGVCYifErHfRD9ytRHQSPKuvb) |
| 46 | 213 | +1 | 0 | **nozomi** of landx-fra3+nozomi+staked-rpc+helius-swqos | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/45KqS87KEHrDYxqunUvfVT6bXwpNFrYebZRUfLnVsEsieEvvG5mRwDp3fLvbhJn2J3kEbUpj8zy3bbjaC2DE3oUG) [sell](https://solscan.io/tx/5DYXbjvYVfFphvJnCb2oiZp1uWhHNyTc2LzgGV6Bw7AikeNpseT9UAo4janham9aLJrdM4d4rngnoRM1RLYmbgLG) [dump](https://solscan.io/tx/4nzg6jJv7TRrLvu2EHSiHxMFULnBmBrFmwN3tJJ6wACMEpfytK4AhQKeuLSNDP7dCvpMp8KB2LQ4v4DBFxAeXHVN) |
| 47 | 175 | same | 3 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/28vd7hdqVGTcuVGnFKp9VEtTD8gWshu6JHDedFTwnnDd7t85ZSBoaWSQZpy94oForFzBVooyEd6ZzA4caG4PPTBt) [dump](https://solscan.io/tx/34Pd7XeAvp5mrxBA4vvVckBEuSvSAe8hVHg9Gp1qsvSugnBVq1Bd7596YDHSGAx8dvNU8DxvdJgUKmbG7aCrsdgT) |
| 48 | 77 | same | 3 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5QUiYsvvCj9C1MfCN22f6fxkdHkBzpBLiNoEmq6arj2xzp6bWEB3nFR35zZ5mhu4vZjQ3w3jyCsjf165SjW5Dwk) [sell](https://solscan.io/tx/55yXUGpW57VfuFkGg64kcxkJGpCN7t8hHXkBhbtXBjgBb1aS6Rht6TpJNoUV3grX7PCCMfnaLfBsTksZDEW2TvYD) [dump](https://solscan.io/tx/47RhQpi5CK4c61GEJuTUSWhKeguNDWw2LbTxmb6TGyDYLS3uoeqYoKeyZTLugfScG9bMU76RehFqfVVdR3QPfgLC) |
| 49 | 43 | same | 7 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5b2oWHw57977Bz5eWgo3j6hACqhP9MC5pysa4zfeHXZ8Ty3i58SBmQ81AAdPqrfs1qJjpon9kop191hLnER22Mn8) [dump](https://solscan.io/tx/4Y8Xs6wVTXZKNMtQRzPjyZkZyChwZS6kM7ifZYNDFT3affBVme9ySWFeDSUswsyNkpPxaKUmvVbSYTju7PSnWunG) |
| 50 | 40 | same | 2 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 2.5 s | 1 | [buy](https://solscan.io/tx/5J2oGza94ZqkaedV6pwHA5MPKbAGqKSEnyojHrAMHSX5PPJE5uQva6g8tmsauAFbTduyumG1yC5cij3ChhM1oGhn) [sell](https://solscan.io/tx/3v41i5ymptqiGZkDcPJUtzdeBtn21NyWp39aDkko14uShhkmLLVpo9SJmN3LBFYsg1AnzHTbQd3wvXEGAqcxNsJD) [dump](https://solscan.io/tx/5xQzJREeR4iASKRZ6r7UdCwxp1BoGxDKv9EzEYcf8KvW6n1B3mYzyZtgznVt8iRkGf9YFK6zqWr99e4huZnjZf9b) |
| 51 | 21 | same | 2 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.2 s | 1 | [buy](https://solscan.io/tx/4LGxXyWTXh7gHJCZU2dZiAScdmypPkqrS4LdMRn86Qi7wjo4qubQHUKwmRvKSKJMUTEd9TUbVE5uRkFyapo35isi) [sell](https://solscan.io/tx/2PGuwsLCeFMuuBKKWvyM44xixZhvhCJz6UHcyFuTTxsFB69ZQ2mf87witusUDVcFp4szpgqeEjDd59TsW16spirE) [dump](https://solscan.io/tx/3nyG3GYpFSwnr3Be52hRmViWrnmbLY9PssoGaeSCcXg3ibeGXH53uL59QibzGbjnUFaQt939Mih1Xivy2YcyeRrh) |
| 52 | 140 | +1 | 2 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/4nKovgxNWbvocNAoCBtk7PHSEfvipGyzujYYuzf2qysoqEttzSwJgbB8rFDvLCZcNrhbJgEBWy2SohSRu3oVsEiW) [sell](https://solscan.io/tx/zQU7Gvugq6iWkja1ZZWJR3QhgJyBiM8Jp6v8kcH4frJZac4siZYDr6QMMi8naNo973kitzg14KLSmEBV2tA8wCn) [dump](https://solscan.io/tx/3U3GGYp2F3ND1K6Nt9P8T98UmzgWahhis45SqzkdVfo65GEakRZeUKXkMmGJtLBsZtFAoEDyNARpniqDK6nVNzaY) |
| 53 | 56 | same | 3 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/ZFZ25bxhyw3d2RVMMVPQRJCgcid8kRUiPbR11htoQSW9iSy2NcV3Cuc9gLKJ7NB6PWtxSoqp1ZkSMQFatxkUmdf) [dump](https://solscan.io/tx/5oh8bySVkgWt2khrnHTwFKbkdYQpwHgWEUcXQ8UPvMr4bJ2y7zTCowyBuqLbUrLCLathSSCPDp5c7DEhJ75cdE52) |
| 54 | 123 | +1 | 1 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/3XNiMVBuQWEyTYDYdUmKnZ4rS18Lb84nLhGK7xau3ceJ9SFvHyrEvR6kZTTBv5bNcoi3qQ9top5jWX7E1rKndrKS) [sell](https://solscan.io/tx/5xcgN9iWpGi9XiYHskPXLEFZr2YdjJiPkqcQVj7kfos1xG7cCBV64VyQbRyXT3H4Tfec3Mz2QfXeHipRJubmHLdm) [dump](https://solscan.io/tx/4Hut5GDrQPWooKjyoPJstEzTpwQndr5DraHnoA88f3Fi4ou9UFucZLEyiGieTxvj8gfJma9cyowsxEjKLzGNVg49) |
| 55 | 43 | same | 2 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/5hb5Nu2wR82eQ9fWLWSy5WXvfU5zVTMxLLR1U1d5oQVRt1MBXR4vu23AfKvn8hPhrjg9M6LWR7F46wEEFkdp7NcE) [dump](https://solscan.io/tx/5KqLyWLh1U7khaizeBRPnQ53BhyNpYh4Gngm4S5GsmNaLj8XzwPNzEjQoxSp4LpkdFdY8Fpiebs3XW9fMfrfhy76) |
| 56 | 45 | same | 3 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/GMWH8brNB3dgJR4j9Hft25fRsdVAZz3QHrkB3krneasq6ySsHNfQVCVRyyJF7AUbxr3dqC2TQwCgdXTQJYuWFmi) [dump](https://solscan.io/tx/4D75MT4GytPnh3W6MuWqpp9gniNfGyMvbVixBhnrRWoGLzzEna1vW8teZSoYsnw5NdhdATiRQNULxDyJEcRc5XHU) |
| 57 | 60 | same | 1 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4wSa3YFFsSQ8K6o3ysYDfZaNCDaAGY73AgCYqkHbeFQz1warAHjT3Gv5pXKfdJ3fYcvHqPpbEAPRy4NYTzX591oU) [dump](https://solscan.io/tx/2NbALBLztK3FFHAsKPjjTvn7TEgTNFQp73cLT2MCHCXzS2MThoA4cR4ojR9BFi6w1tpG2fRNVfxV8nMoXNx9MMXd) |
| 58 | 48 | same | 3 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5T3E5ofG3ptW5RWV2CCWv3BZa334teRCLWBf2zaiuZXtYEVEjgpvmUvyND4H2QEpLGQyRRqcn1tKbeYs9nUhmypA) [dump](https://solscan.io/tx/22FuADvmj8Canv2nhPCNfJDdREycTJ9m9Dqe9fYNLzXkFphemzeBp7HYL2JRQC7z1JeTGACuPQtZ7eWvuRdCxkKd) |
| 59 | 120 | same | 3 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5mmtFABZuG1b8MT4XuSctTCnL7G7RA636yxQ9DUEuwK5NaJoTu9SyjnkzLkKSiMr5YDKtVYw62kqN3i2PWvGUFso) [dump](https://solscan.io/tx/35gtvEQGHBebybLLcqGyJ1UYVMHX1ZywyksTcYScYDfzxbdjeNvj8XTjHi5JdWsubrQMSXu12zQAAqEaCJ23tpDz) |
| 60 | 165 | same | 5 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/2mw21bMrNUtGdN6bYptPm6CNPpSZGxzLrBZJHenT8JmLzXELn6QcjmExF4TvG5WYicvDRF1vpiCJoeKnf9tXNHk8) [dump](https://solscan.io/tx/3XRAhgXcCDNLZZeYyTShTFohERPNmazyL84aRztxEKYu2C18gHXMTwfLto1yrtri2W4zRoG1wupMkKaHJP7LDZpG) |
| 61 | 166 | +1 | 8 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/3Y5T8t5WM1Uxkc2excEgC9bPDnFqg2KBctf2bBQDr2q5TrdpU7qfSZjVP2PYUJoFzub64QYaKgrdEF2XaimuTJK1) [dump](https://solscan.io/tx/2BfN74rVkXoMKnGzzjjUDgmTHozS6eWcsV1D3ETB6jB2nYuZMn4RWExMtNKYVNTCPPCVcxqWMNrMWZvVv23LXg41) |
| 62 | 44 | same | 4 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4tkzGyDQ73X2jPvikx6fp6kMTuVZssxS3hNhHxb6J6VBTACEAKQ3HzVivwFWSNtRAoxEA9AWmHD539zj5uSwT7Eg) [dump](https://solscan.io/tx/4Y1NT3EJ2y1cjudcAkYBLTkaEiVy5yq7sUZn1rdU7aHQ2BikTwCDG9MqYG4JiZc8rExhk91peE7LHxwtbYtSQgyF) |
| 63 | 34 | same | 1 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/3btgC9eYqdkMRfFCQTrXZ22fh9w6KisBQ6wXN54yW9QNYddQdrRwQ4E3WSqNxtcxaD1ek8652QbSdKHpwQR7pW39) [sell](https://solscan.io/tx/482w3M5uC3cD3H2sMD4u15CwTtVqC7FmRe9anBzqZEWutEWvMNMc9WxH3KrickoEcTiFPEN9mzDSvHNkd7TpWfY) [dump](https://solscan.io/tx/4hcsmSTA7mcwrLnAdj42cXVN5yRtDiyC8rgqB3M11zXAgw9UoD7xzdzkWubrGQ3ctHLqTFS3XfUoxBMssVpGibob) |
| 64 | 71 | same | 0 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/5nKs5hrEKMwqHvCdGf6GWN6cbPEuUH8mZ7ymypK78o8ANUy7igbWUvhy2BvU4ypFGUpPXZuMfJMnDYRNaTTq85mh) [sell](https://solscan.io/tx/66PNrabSbMx2cBQ3yPdrcrFX2nJJjKBeuGC88UmvUduBWWHFrXJYx3kjXPSTdM8cRSBti8EB9fKbXwGvH6EoNvcT) [dump](https://solscan.io/tx/4EuriubGKCRVtTMk4S5sUZfUnZ4qW8JE6pnF7u7tjDXzwEYt7AYd5apBjEGxbBs4NeppK3pnkmjTiTxQW3ocQr8B) |
| 65 | 60 | same | 5 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/dEN7ddnW4GWFFuzj8eU1uUqVxiebaWQg8fGfnLGiawhNUPVSUnbmdFnWp2jAcFtFv3FVeysu4zee7RcyG2FqY58) [dump](https://solscan.io/tx/wmQyDjYXQvKyc2Ysjjp3AMVAtxgseS9bvuS6prntVc6taqHvxFJdSNoEp8aAA3KuGxfVeMD8URHXhYS2REXV2PB) |
| 66 | 213 | +1 | 3 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2iF3wHgJEvyY47TWngrVAMKyi2jgRemzmfmgZMgU8m3637fpLw4qbPJvfPemCFJ1GrAnw7AnJTjyShMknPpKRU11) [sell](https://solscan.io/tx/7AsHiBYDDKNG7kv6WGJAoA4QGhmoEvgEjrGwHCBJiXhfLzr6Y4cuXk4VEQPfRfZTxfZxadh8Tjem8gfCG8tBGGX) [dump](https://solscan.io/tx/3GpB3jwD67FtPkmvTGPpWj1fPz9WHXCxrbHvocoz64UsWWvwySHzd2VWW75YBYyRvk8ZMWjqhz394ttaxHYxycJs) |
| 67 | 34 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.9 s | 1 | [buy](https://solscan.io/tx/3oVKxbyu54JTjb2QAGruCXdz9nnmMDnQq2q7C8z5gcaAY53MmaTYVAuTbZnS7MeBwqcsErV6z4iQskWvYSUjCKGX) [sell](https://solscan.io/tx/3hgajj3RzHeGbdMJ2iRAi1Lwt8jYLD63YBRjRkYT6mcyBKZSRbCXPUUNsgewtmydd4ARm9MGR6NFXxRrCbmcQWxq) [dump](https://solscan.io/tx/5EtqFS9QGKNriZ2K3Ae9WqNanhbkgQJquFFJTTKA8YwZk7SL6qZgz6nPvdNnjQxSm7H4rgLieSnwnu7TSuCqHjUf) |
| 68 | 138 | same | 4 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/4rxWpwocm2f4f1McpuetmxVSwycYCsAiHsnXPdQkcsrEvWMS9LMZEg8Hs9UbmbfX21jg4ybZGVFAqnPi7is1MF2q) [sell](https://solscan.io/tx/49bizXJ2iFMBJHcVRnxCvoiVhWRGY9QVjzgiCFJkyiJeZJbL7hPETqaztngpRSdERG4NvUQxuuSuNpZDXpHky4sR) [dump](https://solscan.io/tx/3Edbgf5sdrnimMg8uHH86gU6p6ajPrgFTqaJPQrbwcMdubLRvU3dZAocb7KnnW6PuyQ7axp2vAiaojsRjFUFZ4BP) |
| 69 | 16 | same | 2 | **landx-fra3** of landx-fra3+nozomi+staked-rpc | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5F1NCpDsHixou3zkMUWw4EpE8SNwVzLmriU3TaFbnWoEBsu2QjPTtGDqcFPYvjMkbSucvNduPkde7tWiGQTw3tau) [sell](https://solscan.io/tx/4DZaja1K1nc9usm4RhLmC4n8RazXWHYUmKiSstTik8vyioGKC4gaQHtcmyqipEhVsr6DDccHRfY9wKAL1XVDnxsv) [dump](https://solscan.io/tx/3YTFsjNdcEamKpZ3iHxNa4aD8MTF4w7Np8DiXXdqhdHcaFJb8jvqaGiyucrDjsWTzm4UwJu5SkSVTZiFx9MCjCUZ) |
| 70 | 71 | +1 | 5 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/55ejdE71R5WTyYW5eWXaYMD27zkS86bn2BZ6vQGScxZarCwH2SqqPhkQ3hknyHszuF836NXK54QKSiY1bHhG8M67) [dump](https://solscan.io/tx/3rg69Nbv7Ngm2VHhjTMzjgjqEWvzEpRJrBE5ZWMRg36NGHZ2hfnnFKiB4oijfL8HBTkqz2pyqeK3vGfYZE9t16De) |
| 71 | 179 | +1 | 10 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4nEvy8gKeVszGxdWEFnLBMc7jLzSsssuFcEDmf7gHQCCtTCRFUT3SbUKhjx7g1A7fPDzgqG1YK1LVaDCafapsmeJ) [dump](https://solscan.io/tx/4qh9bUvRHDjoBVJAqtTAgD1j25NYpJNLU3UxT9hqv1EYahYqW5oBwwNmWovLjBL2jXqJe53e5Jz7Du5bvHGqAwKE) |
| 72 | 191 | +1 | 7 | **helius-swqos** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5TV2Wxg6Bh2a7e4cmZtjFCtcLiTYxwcpLPEqyYJv2z4t7nZ7chhD1qQqnwhMQmTZ3oKeYiyyDnm7AreNg2RSJMFU) [dump](https://solscan.io/tx/2pd8jqnTV4PUtXoPTkwcjAtxmgFeKi5rh5Sam3qFKFpW8m1qJHiBEYy822qJPGS69SV6HG8JFe7FURmAcJGcMyMm) |
| 73 | 96 | same | 2 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3vf42gbYinLKY1yrmZTkHAej5b4HA3DokWir5mgNAkmqYnHdCxAhnC623GQoGnvs33DQAZ7cAtrvmG4kx8cGkmv8) [dump](https://solscan.io/tx/2FL3ZUswGPtH8nivQKeBtLAdDL7fktZTx3Qi7WqHWAN6befZEXPKYGghHpnavrHZnoi9qN1U5ZLYxRqag1tji7pa) |
| 74 | 40 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/7WSsgbW6zpXHa8odvT4f6htdzvCxMys1UowBFKX1bf7VgBhwwtE9eanzX59N9kDfzMGJqEZuifKhFXZQCGieiUv) [sell](https://solscan.io/tx/5hDSbLoHWzpv2YdRHDK4qLKSqMRE6FDtGM7k9EqqVLEuV59evBjN1B77dSRP5T9VzeHTm545v2S3xW1DtJRYbjKL) [dump](https://solscan.io/tx/374BZ1zja8SqXEpcDhL3GtZK2rBGdPEgr89HZJ3LmcN5jxDp2nYn1iRWAVAJ3jgcY1NEar27BWHqxbjNjqMeK3YM) |
| 75 | 46 | same | 3 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5JiiK16JCTnyqoGKGrnpzhBsvYZJ9onwtPxij5Xtc8n2kFUioZ2vpkpyy8ZHQmaGodoTH7fMZ6cNoeZzWmTLuY8B) [sell](https://solscan.io/tx/45ocBLvynoE6MQU8nMU4qPmEAsnZPGfnZk7ru3dNcSCZMRrTic7x9aA5QEnfQYXvtmrgf2Y4GgmzRE6g3b7LEMSF) [dump](https://solscan.io/tx/gE7cgoggJc8LvHQRxPSFW5wM8ZxK46fKUFoGoGn3QgN93fnmrASJdHgCYfsrSiJYsH22SbSgfi4VwjoWC26qJ9i) |
| 76 | 30 | same | 1 | **landx-fra3** of landx-fra3+nozomi+staked-rpc | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5ZMUnvfupDHYFzmpmpbqpUFMprqqwRPjwNmD3L6qqxBAehTLL5WnH3Mtp7EA4r6gtw9WQgk1oV3NQ3MVj7AAwTnL) [sell](https://solscan.io/tx/39bdTXtWt8mWN5X4ZM4H1seCvKZUeLBx6h62umtguaXWz2qiaoFK9vJKHYcjyC3pHWeZJjgMRz4mWxF8fDLRVWW) [dump](https://solscan.io/tx/kDNndnPMZs6uj963jdFEJAZX99B3qhCwPaNE1T9n5pPnP7B8RVP3DHRcWBFd1UbYNMXUWY8KcPyYnQExnETxCBS) |
| 77 | 40 | +1 | 2 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/3H6jsJEXD3wjuAx13sXSrbcbN5yhHt7eduE8wKjH151kerf8bmXPf4yxaUFvXKPntrcVvKJSuBp3zyLt8bxDZjzR) [dump](https://solscan.io/tx/4sUT3TtTVo2sXvTFFw1gLjhg1izyM7P5yCh3G7sky3n23ntYjPtyMyS3rsjngJAJxEdfeA5fDEN3Y144L4cACMXC) |
| 78 | 36 | same | 5 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/3bjEP2CbFt1vNKZofnFzZkP2qMek7gvf2dbbo7wFaUDLeKfzHcvSFJwrN32QXA7mKqEChZGExC4b9mUtGAL2FGcV) [dump](https://solscan.io/tx/5V6JkiUopteQ8TxC1iUDP65wQgr2dX8Sq3Pshw2eERceRkWJoi75qs4Aqm1BbUwVo9g1rRo8J8VUWbegJ6dStTWB) |
| 79 | 45 | same | 2 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/2evnev1ut3pWT2E2BfsrPr1faAJey84kUw55jY4LtFke1p45n2uiSWdYxwH9s7ZwWoN1qVKBm23FKsb5xt9K8QQU) [sell](https://solscan.io/tx/3A6X67NWvzb6jRdJEqjgittMSKqSa6FMBiCs8FiZdexkZWGmezjzrVA2QPPccVb1ioPvm5UbaQpdG3oS4FtK4fhj) [dump](https://solscan.io/tx/2iQBv6DHSq66obZRRWApFmazQTqseEHd8J5K4rEtvMjVKncA8hV5NDsPZYQirioHNqKBbBQy5UgRdJMmhj96cQM2) |
| 80 | 24 | +1 | 4 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/gQ7eoSrAvLX2FJMWq3W2gwbTqFDzodkyQazjRe4hCksPZd32FRDXTE1DQqQUtutd774u1XfVVVWeafL6sWaNLbo) [dump](https://solscan.io/tx/angAYf9FhXvgEFfYKVfJa9Cit681RPDbMsv6RRtZbGg1zC5nA9kprfK3E3tKnojx7Mf9zRMo4i3c8QLBYiR4KhV) |
| 81 | 26 | same | 0 | **helius+helius-swqos** of jito-bundle+helius+nozomi+staked-rpc+helius-swqos+bolt | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5DrrtvZ6TCGsD8EpwpDYFKJiUsgqa2kUuXQj9ZHUvwENapPMMCKEwg7GXdiDBHEFWTUhxoek6xa1fW2imjENBQFS) [sell](https://solscan.io/tx/37LnxpvxP1cQqDFC3nAFZ6PZoHgNg23hMPTQeWgyr4VKjDvo1wuFEaDqETwDPT1wPH9VAnpiZo9p2bXdjnLCpBeW) [dump](https://solscan.io/tx/4jk5UXqpbJZtFdicPHhXvjXn3qkiV4ji5FpudjApuLvDzsnWVs2JQX58atW5ugK8h6fHjnEsegkwifyjxMFbvTCz) |
| 82 | 150 | +1 | 0 | **nozomi** of landx-fra3+jito-bundle+helius+nozomi+staked-rpc+helius-swqos | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/3JYN5W4oethH1zG5eHGkmsfhmuVZQLh6ei8Gj6uZLvmexNVPz1LD8W8FTAw3beRropJ58ztT7dctHvpkfvqraVox) [sell](https://solscan.io/tx/3zNRe145QJdVKejCkAAWyCSD7hBTbqMWKEUKxnZpNqgvpEwBN1P5r7c94J72X5euRJwWB5SaPDuoNnPY8CbqddkP) [dump](https://solscan.io/tx/4J82eo5JPAGHb5GRjs44DyxjWBXSX6Skbo5H4NJzPXnJFKR7LPzNLsaGhPPVbBGy6Yyqo4Th29TVTpsLN1639UZ4) |
| 83 | 71 | +1 | 4 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/28roVSwyAdEPjh7naCRuwjRQ7v72VNsDE65yC2pxk68ayeF3ZrS6BuT9US6hojrbb9Wmoq5ztWfRn43rVS89mHX4) [dump](https://solscan.io/tx/3k4t2QY8thaPfSKiFfxRK7AxUMJrGR8L2x7gTmUjfjRytZvmP4jp7YQ22acKgrCp2qh7465d6hzeteVpdK5bJrFv) |
| 84 | 42 | same | 3 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5Ba2iTXrn44LX53C1cHHK1a9E5VPnNY64M4j3Mtz6QucLreJqM3WGRFVeGFe9PBuX1UiLTFPLM1WMT5DnrKtZCKy) [dump](https://solscan.io/tx/2EJm634S6CrCbbxmnUb7ZCxbKFvkevKqF8vuzdusBUCmwyof8FArvRouupAe6R65HJQdW8WrjSAY4S74uXeLStd4) |
| 85 | 30 | same | 0 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/39NDW74cBXceGha88GCzuBV5oiBzo7rM7QbLQmDBjUkGikJrE42ngqH2YH1anMNzLtv5neLnK6pBxLDj9gNBKk43) [sell](https://solscan.io/tx/5x9dbNerfceqhvBJ3eg4JdqVeyUwGLoiGc5XpczXZK8AZ7zg6aA4qhMAJu55KYKxJbp5mH4JVgGTCGy1v2q49ZwT) [dump](https://solscan.io/tx/4XAeiBaWJ6C9DFjfXF897sqnRW2amqKMFPStTZinJhsiuhCR5zWJ8oAAnBvprKNFr1RzDxpiALZMK69i9Q2uL1iY) |
| 86 | 25 | same | 3 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/5vtKbQ8JF3mKX7UhPdpEd9iy598sssz52BcEkrHetSfnwu6JpAUEwuSbQARLYyfRrqEocRLQj5AbdVEybSwSfbfZ) [dump](https://solscan.io/tx/Gf737b4VDjCN8Q98zPSNUST2EfnAqfYGvrfy8pi9VnLXCLE12RHd68kQLpqgrVwizRcbkXm9EDMXfyxqgT7zUz7) |
| 87 | 26 | same | 1 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/2mzR6EKAiSJCLuWwtL1cb9HSQJ8rYbT4N28dvtFAQ1q1Emx4H5j8L9ypF648zimMbEquu3dYJrDA8vvVR2zBhXY7) [sell](https://solscan.io/tx/2DahWvAPgt7qVuVV9bPMzuoaBjs1vRtkczKri2zuaC7SbxEEuWh3VXhrUeKTnVMugJ2LyunEjcxZrbTwUuWcjbXJ) [dump](https://solscan.io/tx/5J4M9PcMkBDe56y47ktoRN2KZFVpzStoV3wzWRGbgmrBuSbTzweEGv8rYcqwKQLxMwmHXayrheX6AdvQLWNEYX2H) |
| 88 | 43 | same | 2 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5SVZ4pumFBpg7vuxA6ZnR6s2LFpyBWf6XXyyuubEXteNwTgjdW1Mx8JeG7fRJPZUHwZrtLxifLy5ao5aZmxmBxGp) [dump](https://solscan.io/tx/26itip62iMYNPUWdnW7BRaVDzK5jSTVRGPQtVZX2EpZ2zLv8fZgPzhJbGCwPr66fMLAGqWUyXM7dVdxhKKZyqVoq) |
| 89 | 27 | same | 3 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/67UzhGigNAjgtg3KdWm9N7TNpWxzNqA4k6FSDPwyVotoEaNfUt6RU5HpjJqYQYBuqbj3B6d1LEXH79V8WEXFGU7c) [dump](https://solscan.io/tx/2mjT3AX1CZY5PsvvLaZKzW9krCZFKr1EQv5FnYj3YEHqMkwsgPTxhBkuJbJda74umTSWYwvDHVdx1kXJLus3rMWV) |
| 90 | 28 | same | 7 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/59qRpQHz5LxDEa5EaKz9NkFRpkT8dzLsh2Wud8ZEkfXACM811mPDk9WngwA3Lj8CSL53pPDovG7eWcvhmND7NohW) [dump](https://solscan.io/tx/5ksXjs9Hm2DZZFg2QFkmpp4xT1F3cr7tQJyZfqWWnefe23BUg691yCX6pFey4qwN8gNTHq6oNg8Fa1PtqJwxYi9i) |
| 91 | 134 | same | 3 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/4QfBJFQ8zdNt2Xj5yDosgocT5fb8zKUakZ86XsPrALMuiv5DR7LB6WBfymMrSiKBduzazdBUYVB9KdxjCVWGYZEf) [sell](https://solscan.io/tx/5ad5umgwfFX6wKGcoz4kwTaJb8wbPgC1itwXQdn8LhzRML6FsxJUjF6AQEweU3HSJUmGHMzjgAfu5123sn12bFZm) [dump](https://solscan.io/tx/61eRt9eFA1PM5aTikD3JVpvZSccVMXd8E5kCKFaXZXn6LUrdVKWyD5kYTu18c18HojPULUDCbHjXw9EBqaT49YMs) |
| 92 | 108 | same | 3 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/55FYEFSGAaLvarVX997FpbVVVaKzJSS5ibYw3BhJURuTVn4Nj13Mnw7Tebqjm52xSJqCEkEHXynmQf3vcMzcEYs3) [dump](https://solscan.io/tx/aqPD1h5avBLZyiUCSN47gnDZb9A7mgqpVBS9Hke2T55GL1DzTYyfQGKEyCjpQZ87zPPwef4WYGkSfP49aWUZK7M) |
| 93 | 134 | +1 | 4 | **staked-rpc** of landx-fra3+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/54ageNhR7EDTKkR4VHzK7LLHpeDqToJkn59EfMxEkPZkZicmLzoaDJHfQXzLUvYvwkLMYZHp83qNcSZrPMpnfmfa) [dump](https://solscan.io/tx/2Aor6Xk1wvKViB29iYx8CMVXEP3eBPCHa2Rw8zA5WKr2psYvUeM41UzNmK6VAivcBSLQUYY5LznsYVGxUQmjGTH5) |
| 94 | 12 | same | 0 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/22T19fjVVwDCszgD26uH87KcCmm8ncTWMm3cHAtzHv92L5857V7UXEPRr9BYvJkTkRfqWLqomCJ5vUkMPiHPrxJb) [sell](https://solscan.io/tx/uFTDe4NRZ8QdaZ3hhVykKxfzAUujEXTjtAJ7eRPxpiFfHo6THUJqPk7mv3cZBtVdsjgFfYLk5LSFW8SHNXaQUob) [dump](https://solscan.io/tx/237yU7jG2PLQppK64t6sGUY3kz11zGEPNxjnYWbKziMSEkTdWTrAi4yRDXzrr9zXtPD2nisGguDYAyLQn1Ggo7td) |
| 95 | 56 | same | 4 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3b7WKSWM7zE8VFknKJy8xSYsHNPTNZeyz3QhpQZ2spXiRxvgzBX34RChjcaZ8BhFjwDUGVu8NpiNeXxssR2akRwB) [dump](https://solscan.io/tx/bmb4m8CycZnYsXasz2dJWsFonktg2yRcMFbUAM2qdwLPdgVpm6u33aTy9ep2AciNfThpKA16wU6yPwSMaLr78Dt) |
| 96 | 71 | same | 2 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4WHHfEqisTeRkGEdf1dYHHfpEgQeiW1jhXLrKy8HBQpn9MZL7yF4CpGreYJtLvM3uBYyGyHzJMCQfwz8WmvoHZCB) [dump](https://solscan.io/tx/5WipLL1KEdhZtjiEAAwHgC677knWiLc3Y7HAbrkDVqAsqpCBw3hEYKyFDgV6YA7VKu7QwdNkmnUhczveFjC5mR65) |
| 97 | 66 | same | 8 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3mopZqXZTrFEvutACrV69qFg5RatHcxxq2KrXujn3JZ4qu7s3nBhp82EZeEQUq4rJqJZziGpsePc95CMktHZ9H6Y) [dump](https://solscan.io/tx/2nhXJU2yRDdrRtT2EERnyxbx8ZTZfh4bvMEFx8jECSdzTNTa3fXVSduu9Yfb1huyT5cPLecomkbwRHc49dvjA8J4) |
| 98 | 27 | same | 4 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/38h5DrgBsaof7BTo8TkxNwLz5uck7okGe4bFxKV4yo2aV3VYkD78g7nh8xaEWCnrV3GToa2nfPNCiaE78o9f7XGR) [dump](https://solscan.io/tx/4EiF43pfeheqKVtXaPeUrkBSAJdGgRyjXopb5tR1Aho9dYPsTXmcVEvrPLkPGW7XD18UAxREGqapTnSH557srjGk) |
| 99 | 36 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2rmaF7Yja1e4jSL8jPrvuuT2AXLGwW91f72uxP6BNi9JJebZBd2ZwenqmqMg6VTusrd63VVHxovCbzXS2EyGocdK) [sell](https://solscan.io/tx/XjC2fcnejiBzE36smSGdUPJrheTrTjtdVSWCf4XWKcPJtPRktyCsmxyyoqrAMs9t6qkRjZdHQDyityR3PYw5iiP) [dump](https://solscan.io/tx/4DCeQpK9xjcBdU86nVtRbS9cgxrRmsyans2SpnzupjdiQCkMmBz1odbquoJmNgjAxrv1ciMPF42t7ANDW8dGTehA) |
| 100 | 110 | same | 1 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/3xDxTtitgqLYH4j8NUno4ZwPcoNr2gRwzdzAbSmzQ9apa3bPeDah3CWTzpfwAd94XpyvoSmi1RcMunHpyWJU7mQX) [dump](https://solscan.io/tx/5yJGsSc13cZP4a5WaBwnrCvbzcE4UiVQ9hDt14WnjMWqLRxocRcNT6A1XTDiMGTFkpbEWVXihRoqFzKmyawFANyY) |
| 101 | 54 | same | 2 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/j9YEC61iSXKnTmbzAgCJDqfyTrKp9fLiRhuH2dHaf3JGf6FMLYyQDwJpdTvTHnSEovyGMnnMYiycC2go7VbBVLY) [dump](https://solscan.io/tx/66DeqzArzi3UGQjjmR1QYGrUYBoidp2qnFXJKoXBqe9VzUXmbQ9uoNMKSh12ueeECCyR788JoHRYUFWVjAC1Siw6) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Harmonic | 40 | 15 | 38% | +0.2062 | +0.0146 | 8/15 |
| Jito | 31 | 10 | 32% | +0.0455 | +0.0056 | 7/10 |
| BAM | 21 | 10 | 48% | -0.1005 | -0.0095 | 2/10 |
| Firedancer | 6 | 4 | 67% | +0.0721 | +0.0183 | 2/4 |
| Rakurai | 3 | 1 | 33% | -0.0749 | -0.0739 | 0/1 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 95 | 38 | 40% | +0.1907 | +0.0058 | 19/38 |
| dev list | 6 | 2 | 33% | -0.0423 | -0.0201 | 0/2 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 79 | 32 | 41% | +0.2622 | +0.0089 | 17/32 |
| next block | 22 | 8 | 36% | -0.1137 | -0.0133 | 2/8 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 06:00 | 22 | 8 | 36% | +0.1191 | +0.0158 | 3/8 |
| 07:00 | 17 | 7 | 41% | -0.1220 | -0.0167 | 2/7 |
| 08:00 | 11 | 5 | 45% | +0.0448 | +0.0096 | 3/5 |
| 09:00 | 6 | 3 | 50% | -0.0828 | -0.0271 | 0/3 |
| 10:00 | 16 | 6 | 38% | +0.1587 | +0.0273 | 5/6 |
| 11:00 | 14 | 7 | 50% | +0.0681 | +0.0102 | 4/7 |
| 12:00 | 2 | 1 | 50% | -0.0306 | -0.0301 | 0/1 |
| 13:00 | 5 | 1 | 20% | +0.0228 | +0.0248 | 1/1 |
| 14:00 | 7 | 2 | 29% | -0.0291 | -0.0133 | 1/2 |
| 15:00 | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 40 | +0.1793 | +0.0045 | 1.4 s |

## 8. P&L leaders
**Best trades:** FzeP2j +0.1519 (Harmonic, time-limit, score -1.77); 8Dbb9X +0.0903 (Firedancer, time-limit, score 0.38); 341gnf +0.0573 (Harmonic, time-limit, score 0.37)

**Worst trades:** 33V5Ee -0.0739 (Rakurai, time-limit, score -0.81); Ez39gv -0.0384 (BAM, time-limit, score 0.44); F8gSob -0.0366 (Harmonic, time-limit, score 0.54)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `Fd7btgyS` | HarmonicAgave | 9 | 5 | +0.1223 |
| `5ZqveVff` | HarmonicAgave | 4 | 2 | +0.1119 |
| `EvnRmnMr` | Firedancer | 6 | 4 | +0.0721 |
| `Awes4Tr6` | HarmonicFiredancer | 5 | 2 | +0.0582 |
| `C8Bey3LK` | JitoLabs | 8 | 5 | +0.0466 |
| `JUPiTERr` | HarmonicFiredancer | 3 | 1 | +0.0323 |
| `7nzTzRZz` | AgaveBam | 1 | 1 | +0.0222 |
| `E1r4Psq8` | JitoLabs | 6 | 2 | +0.0194 |
| `9jxgosAf` | FireBAM | 5 | 3 | +0.0190 |
| `3ytgyJXp` | HarmonicAgave | 1 | 1 | +0.0096 |
| `4k6wgP5W` | AgaveBam | 1 | 0 | -0.0005 |
| `vu1sGn2f` | JitoLabs | 1 | 0 | -0.0005 |
| … |  |  |  |  |
| `CQdLgwkm` | HarmonicFiredancer | 2 | 0 | -0.0010 |
| `3JotfSFP` | AgaveBam | 1 | 1 | -0.0018 |
| `EXckihF3` | HarmonicFiredancer | 1 | 1 | -0.0126 |
| `HEL1USMZ` | JitoLabs | 11 | 3 | -0.0175 |
| `2jS8AX38` | AgaveBam | 1 | 1 | -0.0201 |
| `CVRr5oHC` | AgaveBam | 1 | 1 | -0.0306 |
| `G3a3iYZK` | HarmonicAgave | 1 | 1 | -0.0355 |
| `shftkxns` | HarmonicAgave | 1 | 1 | -0.0362 |
| `BeaCHioS` | HarmonicFiredancer | 1 | 1 | -0.0366 |
| `Hj2jzpAp` | AgaveBam | 1 | 1 | -0.0384 |
| `JC7bH7HS` | AgaveBam | 3 | 2 | -0.0467 |
| `ana2y2Yv` | Rakurai | 3 | 1 | -0.0749 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1738 (p25 1313, p75 2236, n 101) |
| Executed-feed lag behind first sighting, ms | 2.4 (p25 0.9, p75 4.7, n 101) |
| Buy sent → our tx seen on the feed, ms | 40.4 (p25 27.3, p75 88.3, n 101) |
| Fills: our buy seen on the feed after the dump, ms | 39 (p25 27, p75 77, n 40) |
| Guard fails: our failed buy seen after the dump, ms | 56 (p25 40, p75 96, n 61) |
| Fills in the dump's own block | 32 of 40 |
| Guard fails in the dump's own block | 47 of 61 |

**Which copy landed (nonce fan-out):** staked-rpc 48, nozomi 38, helius 7, landx-fra3 4, helius-swqos 2, bolt 1, helius+helius-swqos 1

**Send-path answers (FAST-ACK lines):** nozomi 101 (median ack 0.3 ms), staked-rpc 101 (median ack 3.7 ms), helius-swqos 69 (median ack 0.5 ms, 4 errors, 4×429), helius 33 (median ack 0.5 ms, 3 errors, 3×429), jito-bundle 33 (median ack 0.9 ms), bolt 25 (median ack 0.3 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 2.87 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 8PgC4ngp | 19 | 11 |
| 6n2cCJrr | 17 | 13 |
| HLU8QbLd (41Pr family) | 15 | 14 |
| DF7eRXHn | 12 | 9 |
| 7PedQZmc (untipped fast) | 12 | 10 |
| Dk2jdQ93 | 10 | 9 |
| haqq (dip bot) | 9 | 8 |
| HkQ7 (dip bot) | 8 | 5 |
| EprLoV21* | 7 | 6 |
| 3MHgGwdL | 6 | 6 |
| DiqYk5RD* | 5 | 5 |
| 9pQQc1xy (bait follower) | 5 | 5 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.6562 |
| Pump fee on buys | 0.1728 (0.0043 per fill) |
| Pump fee on sells (residual) | 0.1816 (0.0045 per fill) |
| Buy tx fees (base + priority) | 0.0202 (0.00051 per fill) |
| Buy tips | 0.0380 (0.0009 per fill) |
| Sell tx fees | 0.0242 (0.00060 per fill) |
| Sell tips | 0.0400 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0308 (61 buys) |
| **Result** | **+0.1485** |

Buy compute used (fills): median 75,932 CU, max 88,652 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 40 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ℹ️ RPC bh-fallback getLatestBlockhash: slow minutes (worst p99 320 ms, max 882 ms)
- ⚠️ RPC bh-fallback getSlot: 1 timeouts/transport errors (worst p99 320 ms)
- ⚠️ RPC bh-primary getLatestBlockhash: 259 timeouts/transport errors (worst p99 1002 ms)
- ⚠️ RPC exit-primary getSignatureStatuses: 1 timeouts/transport errors (worst p99 1000 ms)
- ℹ️ send path helius-swqos: 4 × HTTP 429 (rate limited) on buys
- ℹ️ send path helius: 3 × HTTP 429 (rate limited) on buys
- ℹ️ 109 send-path health events (self-heal), e.g. `SEND-PATH rpc bh-primary UNHEALTHY: 3 timeouts / transport errors in a row (getLatestBlockhash): client REBUILT (fresh p`
- ⚠️ big loss 33V5Ee -0.0739 (time-limit, Rakurai)
- ℹ️ Investigation during this run (WHY_LIVE_LOSES.md): our buys land a median 58 ms after the dump; the paper model is right at our real landing. Speed after the send is lever #1.

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Done after this run:**

- Engine dip14 staged (speed fixes: shred fire shadow/live, defer, skip Rakurai, clock2, feed-lag, probes); Helius key + rate rebalance in the base config; sell fan-out via Helius SWQoS (dip13+).

**Recommended / open:**

- Speed shadow run (dip14 --shred-fire shadow --clock2 --feed-lag --defer --skip-clients Rakurai), then relay probes, then the live speed A/B (ops/dip/PLAN_1025_PM.md).

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r15.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r15.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

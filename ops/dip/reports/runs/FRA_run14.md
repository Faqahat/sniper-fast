# Frankfurt run 14 — dip bot run report

*M2 detector SHADOW (dip11) beside IMIT1 trading; 0.35 SOL, 1.3 s / SL −10%*

> **Verdict:** +0.0475 SOL on 27 fills. The M2 shadow graded better than IMIT1 on paper: Stage A c4 +2.56 / +2.04 / +1.25 vs IMIT1 +2.22 / +1.41 / +0.90 SOL at 35 / 50 / 75 ms over 01:42–05:40, both servers. Live picks matched the study on 99.7%.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.0475 SOL** (wallet 2.6474 → 2.6949, Δ +0.0475) |
| Started (PKT) | 2026-10-25 01:41:34 |
| Ended (PKT) | 2026-10-25 06:08:24 — stopped with Ctrl+C (SIGINT) |
| Ran for | 4 h 26 min of 540 min planned |
| First / last buy (PKT) | 01:43:43 / 05:57:20 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 63 → **27 filled**, 35 failed on the +5% guard, 1 failed (other) |
| Fill rate | 43% |
| Wins / losses (fills) | 13 / 14 (win rate 48%) |
| Per filled buy | avg +0.0024, median -0.0015 SOL |
| Fills only / failed buys only | +0.0657 / -0.0182 SOL |
| Best / worst trade | DaWdz2 +0.1159 / 2xhyMi -0.0471 |
| Fill landing | median 42 ms after the dump (seen on our feed); 18 of 27 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip11 (M2 shadow) |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.35 SOL |
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
| near-leader gate | 198 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 540 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 13**:

| Setting | FRA run 13 | FRA run 14 |
|---|---|---|
| engine build | dip10 | dip11 (M2 shadow) |
| limits | max 60 fills, 1 open at a time, 480 min, loss cap 0.500 SOL | max 60 fills, 1 open at a time, 540 min, loss cap 0.500 SOL |

- Engine dip10 → dip11: the M2 model scores every in-envelope dump after the decision (logs only).

## 4. Timeline (PKT)
- **01:41:34** engine start #1 (session with 63 buys)
- **02:04:14** big win: DaWdz2 +0.1159 SOL (time-limit)
- **06:08:24** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 18351 |
| Inside the envelope (age / drop / since-buy / size) | 8372 |
| Picks (score above the threshold) | 178 |
| Skipped | far_leader 101, spacing 11, open_on_token 2, no_launch_accounts 1 |
| Buys sent | 63 |
| Filled | 27 |
| Failed on the +5% guard | 35 |
| Failed (other) | 1 |
| Never landed | 0 |
| Sold (positions closed) | 27 of 27 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 01:43:43 | [2EiGAC](https://gmgn.ai/sol/token/2EiGACq9TNCaopZy7Q9wXPbCVvqiSBmG1LGMnWexfofJ) | 0.35 dev | 0.73 | 6.17 / −19% | 8.9 s | Harmonic `9W3QTg` | filled | **+0.0089** |
| 2 | 01:53:18 | [2vnSUU](https://gmgn.ai/sol/token/2vnSUULWu7Z7ypq6nmRF4tYhQ92zxKXCLrEjHHCHpump) | 0.35 | 0.61 | 3.91 / −18% | 2.3 s | Harmonic `Awes4T` | filled | **+0.0100** |
| 3 | 02:00:33 | [6y38hn](https://gmgn.ai/sol/token/6y38hnzfErQnBp8iSMx34puGyNR3S8Nb2MSueeKmpump) | 0.35 | 0.23 | 4.85 / −15% | 339.6 s | BAM `9jxgos` | filled | **-0.0378** |
| 4 | 02:04:06 | [DaWdz2](https://gmgn.ai/sol/token/DaWdz2ZM7YuMfEoxpGk7dnSJK8TxCJPpbxW93DjhHBHA) | 0.35 dev | 0.58 | 5.45 / −23% | 4.9 s | Harmonic `CQdLgw` | guard fail | -0.0005 |
| 5 | 02:04:14 | [DaWdz2](https://gmgn.ai/sol/token/DaWdz2ZM7YuMfEoxpGk7dnSJK8TxCJPpbxW93DjhHBHA) | 0.35 dev | 1.15 | 3.43 / −13% | 12.7 s | Jito `C8Bey3` | filled | **+0.1159** |
| 6 | 02:05:04 | [DaWdz2](https://gmgn.ai/sol/token/DaWdz2ZM7YuMfEoxpGk7dnSJK8TxCJPpbxW93DjhHBHA) | 0.35 dev | 1.49 | 5.71 / −16% | 61.7 s | Harmonic `BeaCHi` | filled | **+0.0147** |
| 7 | 02:11:47 | [GrJNQg](https://gmgn.ai/sol/token/GrJNQgGVqHyVd5sBo9Mcofh8LW7dSYBBCuHZFHxy4pws) | 0.35 dev | 1.11 | 1.24 / −7% | 3.0 s | BAM `7y5VhV` | filled | **+0.0476** |
| 8 | 02:12:13 | [GKCXhq](https://gmgn.ai/sol/token/GKCXhq7pA4sBY5BD8nMFJ319rdwRndZzUQ4bbjyTpump) | 0.35 | 0.23 | 4.83 / −18% | 12.7 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 9 | 02:12:20 | [GrJNQg](https://gmgn.ai/sol/token/GrJNQgGVqHyVd5sBo9Mcofh8LW7dSYBBCuHZFHxy4pws) | 0.35 dev | 0.61 | 3.28 / −14% | 35.0 s | Harmonic `EJsJx7` | guard fail | -0.0005 |
| 10 | 02:14:10 | [BjCCdA](https://gmgn.ai/sol/token/BjCCdA3zUNBcXRz1VAQABzoNJvA3YedtLVKDDG7RpX4J) | 0.35 dev | 0.83 | 3.40 / −17% | 3.6 s | Harmonic `3iSQtP` | filled | **-0.0470** |
| 11 | 02:16:36 | [BjCCdA](https://gmgn.ai/sol/token/BjCCdA3zUNBcXRz1VAQABzoNJvA3YedtLVKDDG7RpX4J) | 0.35 dev | 0.49 | 4.27 / −13% | 147.8 s | Harmonic `Fd7btg` | filled | **+0.0077** |
| 12 | 02:18:05 | [EunKeo](https://gmgn.ai/sol/token/EunKeoA7zD3GpRD4ZXknxPNTEvDQaTqFESfbkhZjpump) | 0.35 | 0.93 | 4.58 / −16% | 4.2 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 13 | 02:20:57 | [6Y1phM](https://gmgn.ai/sol/token/6Y1phMFm2CHFLF4y83zjP4n3QReuiBfa3r8gJUopump) | 0.35 | 0.25 | 1.82 / −7% | 3.6 s | BAM `2UBhtR` | filled | **-0.0076** |
| 14 | 02:27:14 | [2nQXUn](https://gmgn.ai/sol/token/2nQXUne6jDDbSYejYv2FLWXuHgpcz5g4Z5cPyz2H6XJn) | 0.35 | 0.28 | 2.84 / −14% | 3.2 s | Jito `6XJ4aK` | filled | **-0.0182** |
| 15 | 02:33:46 | [6M8tUF](https://gmgn.ai/sol/token/6M8tUF6NkUcXo7ZaKWyWBKpyUskdkUX8SGQWtgqtsgX4) | 0.35 dev | 0.35 | 2.00 / −8% | 2.5 s | Jito `A9mvuk` | guard fail | -0.0005 |
| 16 | 02:33:49 | [6ADR8g](https://gmgn.ai/sol/token/6ADR8g3hUHLTd9P9aHcNEWUTaaSM2MoKF831Gbrypump) | 0.35 | 0.26 | 8.09 / −38% | 2.5 s | Jito `C8Bey3` | filled | **-0.0041** |
| 17 | 02:34:52 | [2i6JMW](https://gmgn.ai/sol/token/2i6JMWqXqRcb8j1Uv2heJ5oHehTzfgSVZKUeKdbFpump) | 0.35 | 0.31 | 3.42 / −16% | 26.9 s | Harmonic `Fd7btg` | filled | **+0.0074** |
| 18 | 02:39:12 | [GJuS1Y](https://gmgn.ai/sol/token/GJuS1Y5oE54ipfbyPeFmAxPismK6kfFpeujVUJTnpump) | 0.35 | 0.32 | 1.92 / −11% | 4.7 s | Jito `privaE` | filled | **-0.0015** |
| 19 | 02:46:54 | [2HUyjP](https://gmgn.ai/sol/token/2HUyjP4qzoBF3RMXEbeQeJCCaRwimYSDVYFPGdthpump) | 0.35 | 0.55 | 4.70 / −12% | 192.7 s | Jito `C8Bey3` | filled | **+0.0219** |
| 20 | 02:50:42 | [DAvnee](https://gmgn.ai/sol/token/DAvneeksMRjMbcRUibxeTwi94kLmzqKeUvhtXuaWpump) | 0.35 | 0.43 | 3.39 / −17% | 34.1 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 21 | 02:56:05 | [3KmUfH](https://gmgn.ai/sol/token/3KmUfH5PPGBwzSciDYXm1BYor3cTXiyhQTK9hqHopump) | 0.35 | 0.52 | 4.60 / −15% | 3.6 s | Jito `HEL1US` | guard fail | -0.0005 |
| 22 | 02:58:04 | [4o1drX](https://gmgn.ai/sol/token/4o1drXawi8AnUdFoqE1henS6dw3xcPaUXF7khKYipump) | 0.35 | 0.30 | 5.21 / −21% | 10.0 s | Jito `HEL1US` | guard fail | -0.0005 |
| 23 | 03:01:04 | [2x9K6j](https://gmgn.ai/sol/token/2x9K6j7iv53okdDcemBL5fHAhWV8QefK6o9sE7n6pump) | 0.35 | 0.43 | 3.31 / −14% | 1.3 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 24 | 03:01:41 | [5WDsNf](https://gmgn.ai/sol/token/5WDsNftodyCuYJz2bjqeEsN6VjoRssELMYuuxa1mrgyS) | 0.35 dev | 1.11 | 5.11 / −27% | 1.5 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 25 | 03:08:22 | [DnEcoP](https://gmgn.ai/sol/token/DnEcoPYHCfJhJB5K1VbUgbX5cRooVivZTdqh34mnpump) | 0.35 | 0.60 | 5.50 / −22% | 101.1 s | Harmonic `CQdLgw` | filled | **+0.0187** |
| 26 | 03:09:46 | [CkjNR3](https://gmgn.ai/sol/token/CkjNR31Cz276xUacJuWhUfAFi9oJUrNZkzbhM2EpE5DM) | 0.35 dev | 0.69 | 2.19 / −10% | 2.1 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 27 | 03:13:00 | [CxS5LW](https://gmgn.ai/sol/token/CxS5LWWbN6NB8mXY34GQn7ASEXQq9dj1sd1wp8Z6pump) | 0.35 | 0.63 | 3.84 / −11% | 112.8 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 28 | 03:13:19 | [DsBjEX](https://gmgn.ai/sol/token/DsBjEXJyRq7sitZjH5zpJK2GUjMZ3S5wNzcBuWGKpump) | 0.35 | 0.34 | 2.94 / −14% | 1.3 s | Jito `Je6ckv` | failed | -0.0005 |
| 29 | 03:14:31 | [2vFbLD](https://gmgn.ai/sol/token/2vFbLD65w5C6A7kmBSpJmxuj9gF3LLPyEjN3spAgKZ9g) | 0.35 dev | 0.29 | 1.89 / −10% | 1.3 s | Jito `E1r4Ps` | filled | **+0.0021** |
| 30 | 03:14:51 | [2Memge](https://gmgn.ai/sol/token/2Memgeow2W7C6KCtrAXh8NU9BicRvuHGRZENhmWv9PnL) | 0.35 dev | 0.60 | 3.89 / −21% | 2.3 s | Jito `HEL1US` | guard fail | -0.0005 |
| 31 | 03:19:28 | [7hb9VC](https://gmgn.ai/sol/token/7hb9VCvzrY18ukkEiyL54vpouCojAXdCkpxgTcEPYjA8) | 0.35 dev | 1.04 | 2.80 / −10% | 2.8 s | Jito `C8Bey3` | filled | **-0.0397** |
| 32 | 03:22:00 | [5eV1K7](https://gmgn.ai/sol/token/5eV1K7Rt11HKSkW7LY1uC3k7hg8erT5DZniF9iHPpump) | 0.35 | 0.42 | 2.23 / −11% | 1.5 s | BAM `5marvi` | guard fail | -0.0005 |
| 33 | 03:28:11 | [345gnr](https://gmgn.ai/sol/token/345gnrJd8mkuUM59AWZt5tWF8ybSq8HDLs7oWTbvPre1) | 0.35 dev | 0.39 | 1.10 / −6% | 2.8 s | Harmonic `shftkx` | filled | **-0.0276** |
| 34 | 03:30:25 | [2xhyMi](https://gmgn.ai/sol/token/2xhyMioQd8Lh1qi5NxpQUKu4KGbcUr8zmhAZSwjvpump) | 0.35 | 0.91 | 4.84 / −21% | 18.9 s | BAM `N43JWB` | filled | **-0.0471** |
| 35 | 03:31:09 | [3pC52p](https://gmgn.ai/sol/token/3pC52pd5kikcHgB1rx3X1nhcCNJpbK1VXvwZaqtMpump) | 0.35 | 0.41 | 2.54 / −12% | 5.9 s | Jito `HEL1US` | guard fail | -0.0005 |
| 36 | 03:41:23 | [6YuXTu](https://gmgn.ai/sol/token/6YuXTui7dABJ5sTEDFZdpnygJLNnpTKfr5uHqmRYpump) | 0.35 | 0.21 | 3.00 / −14% | 7.0 s | BAM `nebu15` | filled | **-0.0126** |
| 37 | 03:42:46 | [9YgsXm](https://gmgn.ai/sol/token/9YgsXmTz4HStELFFR1gBHQk1qsUXHcJgRJQ8dAE9pump) | 0.35 | 0.72 | 2.40 / −12% | 3.6 s | BAM `9jxgos` | guard fail | -0.0005 |
| 38 | 03:44:24 | [7oVimM](https://gmgn.ai/sol/token/7oVimMrAaZVVhrwwXbo1YsrGGhkeyeVcU69M3iLHpump) | 0.35 | 0.40 | 3.15 / −13% | 46.0 s | Harmonic `Fd7btg` | filled | **+0.0288** |
| 39 | 03:45:27 | [3UqWUK](https://gmgn.ai/sol/token/3UqWUKiF1a5DfVa6osXDz1BVVvct82jh1PdhMebNpump) | 0.35 | 0.21 | 1.98 / −11% | 3.6 s | Firedancer `EvnRmn` | filled | **-0.0105** |
| 40 | 03:46:57 | [5vwH7y](https://gmgn.ai/sol/token/5vwH7yHbWhvKVnkvYt558S5Mu5UYjEYLo7kJVjuNpump) | 0.35 | 0.39 | 2.69 / −13% | 12.5 s | Jito `CTDGxT` | guard fail | -0.0005 |
| 41 | 03:55:03 | [H2859o](https://gmgn.ai/sol/token/H2859oDnYraSeqo6X49WDiNTUeYdAYK75dx6cFvapump) | 0.35 | 0.32 | 4.91 / −14% | 31.4 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 42 | 03:58:48 | [FeU7N6](https://gmgn.ai/sol/token/FeU7N6AmFJNiUWroV871us3og4wfdWP2unrdqspapump) | 0.35 | 0.96 | 4.87 / −17% | 17.2 s | Harmonic `43Am3P` | guard fail | -0.0005 |
| 43 | 04:01:18 | [92kMHH](https://gmgn.ai/sol/token/92kMHHMQu8e7tESZfsTMdzE3vvH1SddckwigSDxpqSBU) | 0.35 dev | 1.41 | 4.51 / −24% | 4.5 s | BAM `GEM1N1` | filled | **+0.0204** |
| 44 | 04:03:08 | [8kJDFF](https://gmgn.ai/sol/token/8kJDFFZCWet7NLGwwcYzWhMNbUb6NbiRmTzvxw9tpump) | 0.35 | 0.62 | 4.20 / −17% | 4.2 s | BAM `9jxgos` | guard fail | -0.0005 |
| 45 | 04:05:53 | [3g25Ko](https://gmgn.ai/sol/token/3g25KoJALP2XSjB7r7RvpRCEQfo2xzLCqtkEhFou7X8m) | 0.35 dev | 0.51 | 2.92 / −16% | 3.0 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 46 | 04:07:36 | [GBH3Lu](https://gmgn.ai/sol/token/GBH3LuSi8bKW8E3jn5yUNRV3yHiXYaBu9wLcdkGxad4S) | 0.35 dev | 0.98 | 4.82 / −25% | 1.5 s | Jito `siidBV` | guard fail | -0.0005 |
| 47 | 04:13:58 | [7a4tdC](https://gmgn.ai/sol/token/7a4tdCSEDKNvq4WUcvsaQELWnFJy7iZR3ZrBAYgbVUg) | 0.35 dev | 1.31 | 8.51 / −39% | 2.5 s | BAM `AiDoLW` | guard fail | -0.0005 |
| 48 | 04:14:42 | [Bk32JA](https://gmgn.ai/sol/token/Bk32JAXaDSyJEeqoheq1d66sFJ4Eh4h9GdaPymLnuBiT) | 0.35 dev | 1.33 | 4.49 / −19% | 34.1 s | BAM `2Wf9V9` | guard fail | -0.0005 |
| 49 | 04:23:57 | [5sj3VR](https://gmgn.ai/sol/token/5sj3VRMPubD3tpbeuTwtkaRb6LimH5gq4wCgQQDog7wa) | 0.35 dev | 0.48 | 4.16 / −22% | 1.7 s | Harmonic `EXckih` | guard fail | -0.0005 |
| 50 | 04:27:26 | [CiqNUY](https://gmgn.ai/sol/token/CiqNUYb1ajAtbgfbQ4At3oweJxb4Gd9nHxYXxcDypump) | 0.35 | 0.63 | 3.21 / −16% | 2.8 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 51 | 04:37:37 | [Gfg6yj](https://gmgn.ai/sol/token/Gfg6yjvqZLX7qj5hqmF3ggMvAX46oTYenXFw7G7Ypump) | 0.35 | 0.65 | 7.10 / −34% | 7.4 s | Jito `HEL1US` | guard fail | -0.0005 |
| 52 | 04:40:16 | [J4UCBh](https://gmgn.ai/sol/token/J4UCBhKTU6176xEtprkKZd4KgbwaCLXUryGWHc77VwCU) | 0.35 | 0.61 | 3.75 / −19% | 10.0 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 53 | 04:49:44 | [128N5P](https://gmgn.ai/sol/token/128N5PJ3XafFjvwYgWCfHP7xobqKigATnrPWtUxfpump) | 0.35 | 0.63 | 2.93 / −13% | 108.3 s | BAM `PAD9aP` | filled | **+0.0396** |
| 54 | 04:52:57 | [8mwDEi](https://gmgn.ai/sol/token/8mwDEiBJE4NVY3rfBDwP89ze8AEmzQpDr2gjPzshAZMX) | 0.35 dev | 1.05 | 5.08 / −27% | 1.3 s | Harmonic `HnrXmm` | guard fail | -0.0005 |
| 55 | 05:07:21 | [CBmgZD](https://gmgn.ai/sol/token/CBmgZD5M8GcHKxtqc4LBaE9uq15uTwXTNMKLzk9Drcty) | 0.35 dev | 1.13 | 3.79 / −21% | 2.8 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 56 | 05:09:53 | [5GTpzD](https://gmgn.ai/sol/token/5GTpzD6M8ESacqzG6GiHMPiJ8jrNbRFrmhV31LkXpump) | 0.35 | 0.46 | 2.87 / −13% | 97.9 s | Harmonic `H9ENbt` | filled | **-0.0031** |
| 57 | 05:11:53 | [HBjNaR](https://gmgn.ai/sol/token/HBjNaRzKmRZ9jefqJjFDZ4DN8Cmq5UX6HzMCaSS94mJ) | 0.35 dev | 1.13 | 3.82 / −21% | 2.5 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 58 | 05:15:10 | [MbyosB](https://gmgn.ai/sol/token/MbyosBd6GSB9GEzvm4ctKW1Pfp7WQDDnG4aU2vnuQoR) | 0.35 dev | 0.63 | 3.12 / −17% | 4.5 s | Jito `HEL1US` | guard fail | -0.0005 |
| 59 | 05:22:41 | [DU7LpR](https://gmgn.ai/sol/token/DU7LpR7mbFzWXsJ8ob1PkFbvYT8QRZnfaugctBqkpump) | 0.35 | 0.60 | 4.25 / −19% | 5.9 s | Harmonic `TREEir` | guard fail | -0.0005 |
| 60 | 05:38:24 | [3xu825](https://gmgn.ai/sol/token/3xu8256ziU9nNxaDtPQPbYAJiD1cZP96VwzwGwWUpump) | 0.35 | 0.51 | 4.22 / −11% | 206.1 s | Jito `HEL1US` | filled | **-0.0163** |
| 61 | 05:44:24 | [CqKSKX](https://gmgn.ai/sol/token/CqKSKXF1cDmAjVwMvkazdMwSKxJK8PvU4WFFSZZKpump) | 0.35 | 0.22 | 5.55 / −22% | 7.0 s | Harmonic `5ZqveV` | guard fail | -0.0005 |
| 62 | 05:57:06 | [wqDA8J](https://gmgn.ai/sol/token/wqDA8JymXx51fsj9R2uNmb4uGCTHfXuEHM5hhZJvyCf) | 0.35 | 0.22 | 5.28 / −20% | 7.6 s | Harmonic `5ZqveV` | filled | **-0.0049** |
| 63 | 05:57:20 | [6fkJjU](https://gmgn.ai/sol/token/6fkJjUCZTyu9nHXysAv44AVin9TFTCT3GA9Dmysf5Cub) | 0.35 dev | 0.77 | 8.24 / −37% | 2.8 s | Rakurai `7PdKhp` | guard fail | -0.0005 |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 141 | same | 5 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 2.2 s | 1 | [buy](https://solscan.io/tx/37mCYUqm16RzUi38oAUrNHYw8fzJPCAekft2oMmGj7jcxbDQ66STseRBewHwAymaacU2oAAoiRYTdoMHU1ruEx9E) [sell](https://solscan.io/tx/4MfBsEkAi7vAZsgJ77RHi9qo5gG3FbZMdQhVb3PxQ2iryEiSs4r27R47QqX2xu8fb4YsjXmcj7EXJhDsuDj1CVPY) [dump](https://solscan.io/tx/41R7LXUXrKEhQEpj2CjpAZBrNso3jQipWJXxXa8Yn8c7eJu2ycSSqb1fq5g4YpJRV5pY4Sk3myUvuKk7JSyBNXPq) |
| 2 | 43 | same | 3 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/273sZp61oS55ihjGHr6gXd11XY324R2gTEnYfUwZyrEuBcn1zepYWS1RWwiwpcWtPQ4zDfeVsa23AxTNFZEFMn3X) [sell](https://solscan.io/tx/4gtR3Q3RMFyaMcAAMfL1uYkyKA4ZooYmZksNZfsazW4xL7ve8pCe494DTnKbQsbtwGnywVcHEL6VxtGWsQeAuz7K) [dump](https://solscan.io/tx/355ca1HvTBqAMRFHoZw2imWcabnd176oF3gEbxfrhkrKUQ3LHPYMmVNe2AQSGeSWKFNoF18WZryHoer69UQPEGZg) |
| 3 | 81 | +1 | 2 | **nozomi** of landx-fra3+nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/Ph9vVD7BApsQv6XiRyTmYboXeUq4AYn4qzmuf1464H4NLxa5JPEsZRDahamQsDufmeyicb8nktPRSvosLzkc3vy) [sell](https://solscan.io/tx/5SiLvVTBggwsJf4JCibPGDCcu85VhdUa8Y7e84ZhPihv5ki1dAwPKbmWeQZ9TjnGxbQF1MP8Bhips4GP4Y7Hd7en) [dump](https://solscan.io/tx/5zNYe97M65m3eZ33P5KBm3oKohiwokLjs7WxPNxAzTKnRMvGzyy8YbmSXLEoohsMqeNe9GSPyXUr6YkQn8czLjsb) |
| 4 | 185 | +1 | 3 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/2gzm8trR7HA9bCNLz4cPhKWwhKCe2ZeYpf8jG54DtG4g98niKEr61gvNTypJxwqHBZ6Cz2DUbomncg8Y4gmaSTWW) [dump](https://solscan.io/tx/H7TixiVSVGgescH3sCQt2xS4n66UQrQ2RstwKoFocJuWA9MdDAVDkFFCXvKHGqR4dxYtdUJA9mtvqasL8FR1YhR) |
| 5 | 141 | +1 | 2 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/654TAQ613zRgtbavfZhEQ5or78Yaq5G4Q8iG7nLK4V6gPAbTw6z2sQPYoHkwgCkb2mgc4L5kgeaqzAkUc7YUYFUG) [sell](https://solscan.io/tx/53wTpqt42PMciZhfV9XRa9VcZRD3gSJZjkTxZr4z9iSxcgU6gtSNsDFFUCYXqMfnDghpkLehjU9g7GweUjNViYBf) [dump](https://solscan.io/tx/5YQ6cAhTHPCM9j9ko2f27n5DKyeqoRmGUAnWRoSVB4eZzgfT7vVnqLFU9RJr4s2ptTb2YK6bPK2Gi4QUE4Udzuin) |
| 6 | 34 | same | 3 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.9 s | 1 | [buy](https://solscan.io/tx/Yvq2MEc2BYTKJPRwFwkJjVsSeWGqVUk2snUegdUThJDXdpWVaw5fLdPzJmoHXHcBoEY4KKswKKe4v67UjB5AiVC) [sell](https://solscan.io/tx/5oDzQ8PvpKnHwS9wjaT5qpkEYJwkFCDv6K4EDJ4itAhQp7RV5U8BkJmWeUV4CVuPEfbsyeTvvdPDd8o8DyFbvdHh) [dump](https://solscan.io/tx/XdSVZiGfFD9FcbUeY99FUCvqM29EDKcJhYQ2k4MDVTAuxghxUfnUmGcw7XdXCnSGjaznURSWdpk5FUA5KMpJQPu) |
| 7 | 33 | same | 1 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/5u625CLzt3nfqLABUJsr47Jbca7kJ5fMuttWbBF3y5WAAArxuBWuH6jZM17SPLjhByhdDcnxnhHdrxKZ5wegfszM) [sell](https://solscan.io/tx/4pGBTztqKGGfZ73H2jn5iJgqjjnhik3J2WoVQn9EHeQ7oVn7HdfJNwk4MwaryTBiwVmSbK6ANcBTNmbsqEfyzCh1) [dump](https://solscan.io/tx/4UakUmviwdbCK1jurQe7ygZz13VkvSh163QABRF8avR5NSeemfSMiT3gtRFiJ1w1i3pveHViACM1ATvL5C1Mm7hz) |
| 8 | 43 | same | 5 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc+helius-swqos+bolt | – | – | [buy](https://solscan.io/tx/3nDQtYreMihfHiRkPLMp5eZsD4QWRXcRmG5Dakp1Dw2aCtbwkEziEVt4u2TPaMth4ET8iUzAUpkx3a5QcZYsoGD2) [dump](https://solscan.io/tx/48jqDCxTh27EwbGXFFENW25wLAARStbCXVM8GguF41KCFxJTRTGpCGzYHuTCbRbkX8w8qKdWiMJNbXYAzrqm9uNv) |
| 9 | 165 | +1 | 5 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5JrBmG5c3mcSioXogR4QRBHVNyJUo4QcHZarGWFuQx1XxCpwjvLCxqeLgj62V3e6xBGsw1Ks5TGUgZhBiUaKLk9r) [dump](https://solscan.io/tx/uB8GtMZh8NxnwyhGUNfRq87AKWk9r1CMdQc9exPz8SokobYgrjV3TGNV2hgzoGoLeKx4zxVNyfhfLXo4QeMTpb7) |
| 10 | 45 | same | 2 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | stop-loss 1.8 s | 1 | [buy](https://solscan.io/tx/33Jse3ffjd31XF3VDEbnoFcpoL6GbVcURFhybHPnV8rHLwdYX4eZbDSfD3eEJbRjhuS2zpMPMenLe4qX9GrA2hL4) [sell](https://solscan.io/tx/24rsj3MKnGZteMMvHif83T2ZX51aDTDsQBENHJVfm6XT45VjqapnhcsHHPaxD7AxxabiYDm1dP4gS9dFht7BddAo) [dump](https://solscan.io/tx/5WazVrzjABXb21Wu5dyfNWim3UM9DpKgQLMNM5qoW9SnPjLUQkdWQUDWqyMMEs5uKxvDFK4RNRSDk3Bfbnoko2Jq) |
| 11 | 25 | same | 5 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/ctd68wYLYBiapmef8KUiJTfjVf9Ly34nVWLjDcBMcW6XwdqJBysyv2NgwhqJvmbWxhsPifNUQmFDMj886R7ci8L) [sell](https://solscan.io/tx/21j3sVZVqtsNhpzrYxFv11fWfYtD76suJCiwJhoBD7SYr2fAkDrqw8LhtWsGr3jP4PM8KED6SpDiktZaRkAtHo3K) [dump](https://solscan.io/tx/3uQM6MhA78mEbpyBpUHbmXzchgHFxDL7AzgjwbTaPcGY6jbJCqohBrcTTtv5GfQpmekAsEChByD2zYFeAys4Fd4f) |
| 12 | 147 | +1 | 3 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/662YoWxjWCY1Vk9NhXJnMe1xvDfJ4EHqdZpwdkJTvvcqu87U9fWctjJ89dk5F7G6S5btqSwrFvHuiJfxyrBP9giW) [dump](https://solscan.io/tx/2e4zHrwpSrArT3eNz4hQSKeqDYNdRsE77rCev6wiLuXtn2Lt4NhUQ655sj5NxrGC6xxeqtaGdHXWxkWPNAEhU1Qx) |
| 13 | 43 | +1 | 0 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/35f8ebYUoF4s8zLokhoR1cTV94PpDoD7ZYbGccYQLGjc9rp4fQhPgsChH53eziZYxSHmByQFV6fX9JDdjJHgKZA6) [sell](https://solscan.io/tx/32Rhg9MxkKDxA4PyC2iPSZqg948292WQw4pGDzLvAsq8vBod99ZjgE58z7suqXGh79mAheLmVqoJKuqp8Xy1Jvui) [dump](https://solscan.io/tx/XkzoFkHhB18DoRWVv8Wo4ZqRcaaFSQAJVR1X6xeMd7CKM3DEzwoi83gkRLtCTVXMrEmJynzDi3QeDqM2cGC9JPT) |
| 14 | 47 | same | 0 | **helius** of jito-bundle+helius+nozomi+staked-rpc | stop-loss 1.1 s | 1 | [buy](https://solscan.io/tx/5B3n6E6c6QG6br8aJazxAqEyMnmCCCtzvgtW95H1gpsVt543Cg2JNzSkJ7i89jCo5MWGEy1T7HSAkTKKZ8cGNxGK) [sell](https://solscan.io/tx/4M32KFbwoJNmhMVZf9Ed34gmJZ8sMopEuzE81a8WD6ibfTjN8gRbSPGu5Jf9bG4JJyixveWtSvPThfSBKCytkVBt) [dump](https://solscan.io/tx/37Ezm93xFY1voVjgF4gbPgRXLKvwcaztnqmkWduBNctXVYj7aoo3TGvkCuWn1vQCLed8kgbwGwmd6NMfK1RkHTYf) |
| 15 | 12 | same | 4 | **nozomi** of landx-fra3+jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/2ZNhssB5o3bbe9hqow1brcHiuCfRTYwLui7J5raEKQCkFR8kWoDsoNcMyDoSCFtP6iMoaWNG1skg18VPXJ4Gdz6s) [dump](https://solscan.io/tx/5cCAwLSgCqJaW19cFiru2PG3jWbNBKYheBU3wPbigqKy1mweHi4UHWx5pM3zxR16sih7ojcx8ye1mcNtmLXURVU6) |
| 16 | 138 | +1 | 0 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/5CyTSzHefCbLBawCe5Tg8bc4hSHRZabWsVr3BCRjHBu3VPZGZDN5G9LvoTNxhoKVDNxpkWcZLwegE8imxEyzjgtU) [sell](https://solscan.io/tx/2UE6BJ4WApMNDUrDxGBgsutoXYp5bLQbzGdRrcqQFtK8xw9YpsVYgFkhekGouhLZJjwbWJpKEq21KXQxDZxakqEs) [dump](https://solscan.io/tx/43L2GX4G9q1Nzg8qAx9Rdjg7Sbnhj8Gm8KPDiFuBJxkXS7oBWRwdhkjTHtpvY4M8X3znk3AHgZ3UsWerLqRsuqVo) |
| 17 | 36 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/285nF7qqksU9QmPWDmGJT1SGZ8C7Ciumdxai8dYiGPJLHxAe3KBiMuKZFBcDrdb8whLGCAC2W5FFKwgwsn76aLNV) [sell](https://solscan.io/tx/66ntF984F51DgufGEarrqf5Bmf4nFpxUNvNoE9UzrTfwqHdYRdEedAwSxmSw62cqamCknWduWRuKMVwBCXogdMQk) [dump](https://solscan.io/tx/27RxR6eeHJDYkEfQgzuXdPGq7D3DWrSF1fcjELSotrRyp9FcouGdWvjmMe1VmN9t7NzzBJUkbQSAVDLBRfHuADvt) |
| 18 | 28 | same | 0 | **helius+helius-swqos** of landx-fra3+jito-bundle+helius+nozomi+staked-rpc+helius-swqos | time-limit 1.9 s | 1 | [buy](https://solscan.io/tx/5cPhQWTUr8hoskTfEjmrfVFBgMqAg6xTyyzxaaWSFc19T6rtSF4NJ8gcMgt43Ex4hm1m8aMeeJybRNbszBioBzJX) [sell](https://solscan.io/tx/2SNMZjVcz4R7tvx9zZTC6hZXwqRBEzfyQbEMoemm61rRUQETUQuDCyRAYdsKKXzJp4jRtovohaaTaXjuBK5au84t) [dump](https://solscan.io/tx/SRdmiU3uTiz3oPEo4JW6SaLYtnPGWghpvYMfvAznaGxk5uFXKC4R5nAmcPppCXFhYEdm15Jq7rDHzoWHd6Ra25m) |
| 19 | 139 | +1 | 5 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/5q799wSJ3PPw7pZTntLTvzjFYUDrcMZeQwHm8jmcVvuxvGBCd8NQy3oF7y16Fsi3RoyHrSws7z6KHGUMWRhq7GVW) [sell](https://solscan.io/tx/4Jn2Dn3LudgT34sfzJYb2shPMmXZrbaSjyBokN9fwS3F6J1HfkjMsUsmR2UqtMUjehGXUwpAKi35iMcFeXnfbz6Q) [dump](https://solscan.io/tx/5eBNHT8GHVibmxNhb7PRVX57s5ZUsJkxjXSxKigEFCT3wWHzF6gNpLXGZNGxVcsq3ik1YZCtDWDkk3vV6dL8nKjk) |
| 20 | 21 | same | 4 | **landx-fra3** of landx-fra3+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4RdeTBwch4E2XZ69MTNu2cfdSLPAis3Y1XeiosPjyf9Y5v5zbdig1T7UsVqF3C2HB1PhdPpvN4d32hZ6JAsfKuaB) [dump](https://solscan.io/tx/4kvE9mocjaVUJmVF74c9v8wiNyR5ptr7xaj9BVkayAHFDkt4XpRRFGe72tTj8duzqkSkjXQDSjwEHnaCKNpASPNF) |
| 21 | 43 | same | 3 | **staked-rpc** of landx-fra3+jito-bundle+helius+nozomi+staked-rpc+helius-swqos | – | – | [buy](https://solscan.io/tx/53eY5rwU68EdSB94rPY2NrYRkzUiVdpBnJaZcXeDkDzGoUD4QW9jMSCd2DfQzFwmAPP2SVdDSfqJY9unsspuxEa1) [dump](https://solscan.io/tx/4ZBrrEFCoNjkj5AY1Zy468Qc5AV7aGKcUyFtTzFBpbVyRiv7D71RXK9CVLAqhLLXrVrQfMpqdStW9iV5agtF4cRn) |
| 22 | 54 | same | 9 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/HddS3KFsa4JCZuL4szNnuJgVeWk5bKp9CnXq495XYr4g6zLZmbNJ4oXQDSqwy25SK1gquKyVWwoXnDjFMMpVg4A) [dump](https://solscan.io/tx/45TxAM6KvpBhLZckd9DkAzSMoVbtbf2f21zNaXRYS7VXF3FChSH28n4YV3sC9uh9ghPN5nxU63idfVpBsQBXeV2u) |
| 23 | 19 | same | 7 | **nozomi** of landx-fra3+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/YCwtJQS6ay2twJvRPfbuUfQjwfjmbUoWNpJEojzwkBM2kdkGorw8Uot2Y7nVX8bQi4u7oaaiCB3kCzdVhAG2E7U) [dump](https://solscan.io/tx/2S8J4eGWfd66Lq3K5zRjXRdRLmfeJLn8JTkfPmGrc6KzientvwpQBNsdZRjRvgd19Sw4LYPdfSccBqRNfoqErVcn) |
| 24 | 42 | same | 6 | **landx-fra3** of landx-fra3+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/5WvQahu2Kd4QQfzfk6wABFgsJbFDmw9urXLXNHkVe7LbvC3bR1xd1AwyjY4jDTK9K5QXBx7QUEzW5euf95L4T5iG) [dump](https://solscan.io/tx/DGTNXeyAnDvXXPAiv3w4SWxxKCj2g5raQkfVUxc8XuYNvpt3Dk3TXewjvVoEUeTQrvBykHEauGdhfT865WufYq1) |
| 25 | 32 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/3wHyL66qSK3sobqbkBJCX6Qxv9k5nkz6EtsJX9gTaZFekZPRAjiVZ5pEUjYaXqg56yaLesAFrWZfMPdsPcU6JV7a) [sell](https://solscan.io/tx/Tzon8NDx4PNLjU777En981758eU2VKkw33PmJUvCf9wWMRWygW71J7NhURLrWswAXoLLXb8BztpsiCGd5rA19yE) [dump](https://solscan.io/tx/5uWDdV5v34ukDkwSe73Ln5MUz3o9uwrHNc5X82sLJbGZRcLAHB68r6RrjkwGbSG56bzdNRvn5WxQcPkG1xfzfEdJ) |
| 26 | 68 | same | 4 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4DKqxuUYbW8vLD3srt6yidQAopsszi17qfFu6DUWLd1gAsL2K8XUtyrsCuNTmYhHfLWWyJruuN12jdWxBE11SgFs) [dump](https://solscan.io/tx/35NtFwKmUH7y4ytNZYHTtWd3itbUbVXZE8UkQK2AkqwnMwRRrfGwB4w44Biy2ctPY1zY2y4A4wheASmYrBe5Va3s) |
| 27 | 191 | +1 | 5 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4ybvxBjQr3gBgx1BSRTHtHLiPmMLnQtXeEYQ13EdjZ6HXhFkbVXXtbMcDYRKoPEynngd3TvMgL7eE4g8vua4v8iq) [dump](https://solscan.io/tx/3KqBbGLn8PFEdpnotQcsbvCrRyNiCbzDnPbRYVQcXeckEPYM1bbcc8N55vLcmZGx1ag4YtanymTozzAJEHiEXwu1) |
| 28 | 692 | +4 | 5 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/31LotbExrgRGhQFtGBr48S3mkva1biqK85ic52EkfUNpMwNGKSC8YspVuvLRuMfCH875rNAvLqiZN4LLGiUW9g9H) [dump](https://solscan.io/tx/2dHEkaWoMCk6CJSZmux4dKcY1rBEZrxu68BXD2w5Kw8eLypgFjv7SZyaVnoFM2XqXW6HQcTWzCfeWWYsjTmskYHq) |
| 29 | 42 | same | 2 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/zH6QGWyzWThXsMFykGgpqUL1ZJQwZvdRUyCvx37F791qxLvMDSXqd1RYic6j3AHpNVoXbFmaCLiH8n4D3mveYog) [sell](https://solscan.io/tx/2ea3udCUh7FaA4b2egxvCfnFmudbFzWSvgrEg9rHQDckWHUfNvmgNbxnanfMQWLzLdqVyx5HxspLqb9aHvtby2yp) [dump](https://solscan.io/tx/qUA8oLtBHqfzhu4jcX1Jsb6Xv6ymevb8s9Hj75HxLQvzspcdXirSThb69Esi8JFMGePa2ge4V9aMRXqMBUJ6dDG) |
| 30 | 40 | same | 7 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/yheE3ByKfdCvCN832Y66wo7RRtbJwdv7Z5VZR98LBZLQRkbav6tEn5ZwTrx5juWFTNCc7QR6st2fRtJAxuhmbYP) [dump](https://solscan.io/tx/4evme1HQMhT3Z2cZqwvb1vv2o32g6NxLs4bCsc4VN1YEVNYgpBSJgEiLXAAErm7x5E31Z7zufYExkW8DMxYMDnGC) |
| 31 | 134 | +1 | 1 | **helius** of jito-bundle+helius+nozomi+staked-rpc | stop-loss 1.0 s | 1 | [buy](https://solscan.io/tx/95kV2mPQ31D13X7g4xH8cTEgeUbb5yBpTCvQSxHANuZerhsKMzy8v63gwVM7QGD4efFiUnVZ382WbEqJpZkRtKN) [sell](https://solscan.io/tx/5Bf4h2NcBghkG5nhsfZeRj5dtKHDLzm5imyG4pcbCFA7611vK4Ai7kHy3s1vxMVVCAt8uGeNEkcdtesCU7x7mj35) [dump](https://solscan.io/tx/334eMMh8h8bpVT1XNvGkMGkvrFute2kiixRH19Uvt91u44L6CcKzCsHDVKR3qBHnVPvEgZGS3FjorcXawdVQzQDz) |
| 32 | 40 | same | 4 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/nJoTJHhnxtTzdkz7jBAfEgcuG9dcPGridzAQ4YYcknp3dKXVQUVnELvenFW4RKxMpRgHVN3uxbNYQrsstqFQAj7) [dump](https://solscan.io/tx/2pGjEygfhcK7XCKV3UPTaUg9o7EfCmNj7LJ8UkTuyxuVqgFm8G8yVgduv9TTxLBsPXg3cez1c5yFpZqADEFBJVpe) |
| 33 | 31 | same | 0 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | stop-loss 1.1 s | 1 | [buy](https://solscan.io/tx/3bgW1gSEoWeNXwjWZJptr8xGnJxCrGqyTGXuEitYVWf3Mvcp1DvBNM5Vq87ijTYjoY3zpy2MdsYtTuuQynisSyra) [sell](https://solscan.io/tx/LDTadyLZiUWTK6SM4cBBTGzTdzvWKRSXhje4ZgX1BCX211C7X5BoKcdcVJoZezmtrJVz326CJUwtUZhcpVGmAvn) [dump](https://solscan.io/tx/2wB4a7patbsAvTKbhFybhTTa4MDF679NPYXUXrNe3rpEcJNnjWmKtFcMANSxieuV6bDg4ohsse29y7m4e51oU9Uz) |
| 34 | 33 | same | 1 | **jito-bundle** of jito-bundle+nozomi+helius-swqos+bolt+staked-rpc+helius | stop-loss 0.8 s | 1 | [buy](https://solscan.io/tx/26fFwoRgPqrf75PHKrHTmws7NxA3Q92nVzwtAVfFvxD92vSSHGcZiGSL8LuJVkBdTnerXPv7aZPt3DtcKSmL6ZuA) [sell](https://solscan.io/tx/3rPBvArBiAAC7nWdXhMJ4fKoYE2Urc25wDvT6znE5GZbygCN5j6GtNrbqSAxMQXoyR74HEQJojZ852cH5TDzRqqJ) [dump](https://solscan.io/tx/3h3Hm6Gfv58kAHsSrh3SLwg4HfJTjPb1ojooTeEtGdAgWSPT3Cbi3rAnzDgqhcfPRVm3bhTJLguvXgRSHNqbGvXA) |
| 35 | 66 | +1 | 4 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/461RPsu1FofcYUxBBSenZbbb1dftymEnw3EHT2ASL5D46RCkZfpoXxwqWFjAFqLb48rpf5YvcHrArbE275HSmo5w) [dump](https://solscan.io/tx/5o4wjZXhaQJ5n2QUXUhDnS5EXFgWNtAVhts1MFu7imNxGjiPc9U3heVCCtXZgBdRtqdAJJ8BX7AuL9pVvKskTger) |
| 36 | 57 | same | 1 | **jito-bundle** of jito-bundle+nozomi+helius-swqos+bolt+staked-rpc+helius | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/4jnMAwdx75kwHbSkpBPXE1yNd437uNrZfibFRvXAnqiHPChgky5FJiMGi6zoiho4WiizvEYJWxKMwgSZJeTbSPDr) [sell](https://solscan.io/tx/2DYM9dpuhE8d4BSmPqbesy9ySm8f9WgD1NDrCt8PF7amvpMEN1u24bXMKWk9g4TMuY4Jobb5kTzPuXVPxHxVA9kb) [dump](https://solscan.io/tx/4MJfAKXXvbsXEfBQ3dhRipW5CPSgAK8VzfMctZp2i97THjb9QHedQiNinshHpa8RjuTM1EMmEQJiuEVj7AsbZaHe) |
| 37 | 37 | same | 3 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4UvT2UPmGUTWKgUrd4dcAci9VDicxysXvLxfYgnybZk9PbLXCWk7cVY3JpaJ22CtWMCErDULxN55Ms5q3YTxy3RS) [dump](https://solscan.io/tx/3xcZysRfycLXZrnnQ7pcc17PMEzv46sErxQBuTrgdLhHCfACntL84YueCi5hQY97eeQpJTnyFAWUs5i8mPuiRWMT) |
| 38 | 31 | same | 0 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/5jzFjDLE42dDjtBH3hsWar3qRkqZRrLYrHyEchsJ6q572xpwUzPnwLU6t8o3f7nGjzadhjRahD6nXziCMRxGiPdB) [sell](https://solscan.io/tx/2gc3kDM8e9eoq3zNUrDkHSiVTbkBpJKbppyRXVwi6EzXw5udMExgiZg3BwzHZR1ZhKwzrjTNXcG56gdchpqTSALh) [dump](https://solscan.io/tx/C1bBM2tAxWSv1W9EAuVyaVbUSHaDcXhvryE4DL7JhuJ4aj5AqhhTtNf3uo1pSFw6dLfcqMK17kimzGrnMZ2XM5L) |
| 39 | 39 | same | 1 | **landx-fra3** of landx-fra3+nozomi+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/4S9RPJk5gqcwpcn1vWrMFJVNsaSTgef9J1LCdRNPVEbydMjNXs5DniWbRyzYXKJQmDutDcHT75GSzvJcHCf3gbC6) [sell](https://solscan.io/tx/22NUJFTmLqNSaQVHhgaaBuHEeRQispNrF1bqF3ufmUgQP5tQ4hjBmKNgsBUGubaPqxTfujAZMvSTHU2WXkF29sF1) [dump](https://solscan.io/tx/2iSWVGsUHi5pQkKuxszfyfukMiPajqj3o1GdDWSu8AJBkja6EH8kjJn8x7TD4Aey1Czvqf5546AY1P12ikSisckU) |
| 40 | 62 | same | 4 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4J8Exd1fyVT7DmkqwaQQvxW2eAcf9w91cYo59CPrwagLyqMqjhoTjkB1PzTKDUAEjDE1B4y3Km3kRnzQDi4fDdGo) [dump](https://solscan.io/tx/2qFSkgH7zZV9cn4av6dH1MfPQKVNkmNHVbRzMusEC99JraCmwMrcvKcV3akPfkKhM7qCFBh9jZyQJ5LbjMRWdgKA) |
| 41 | 24 | same | 4 | **landx-fra3** of landx-fra3+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3D2PLDyir35w7tPCVzZNQePb7rygeVjx6mi7Kh9dCfRpeq3ciZYKWvDb9owQLrEr1KwzxdpGxAYs6aZ7czixUYjS) [dump](https://solscan.io/tx/2TPkWm6YuWndD3EdNphozNs8sYu6BxehffYau9k1Ez46jv7Zngwdsfwbm1DDooGzW7mPEyNhmdg4dvhumbevY7Qj) |
| 42 | 145 | +1 | 5 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4PXgU1smXM4kRga2iHx1m9V2rLU55XWL7XvBgeZr6BzPfT4pxCDsoXjyBYQXt2L2B5aAJGyr9T5qzBEv6fQ1DQVn) [dump](https://solscan.io/tx/5zhMnqkbhn8vPA36XLGisYW6guBFNxFQcwNoL2msre568RauPEbjrQx7XV4HwFUHJA7LPjMuDRS1QS7Bd2U9Fyi7) |
| 43 | 32 | +1 | 1 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/4h7ExUVAVKCPpMRaBKJsooBj1K1kyV7UeKwgfDjSkspEorFwcfVbim1PfP6JSiQEenPb2NUsx4dAspqfqZgoxNhq) [sell](https://solscan.io/tx/3xd2YoyfrMSnHt2ZJFJ3zwBX3JfABZVg2A6e9D1g8cYyRGzfd8q7KG4K9bLo434Ji4kx7EdEajS8LYXnArySV2UV) [dump](https://solscan.io/tx/5XiHVBViYvjGVbakRAAgrvfiGWf2bC7YssTpFEAypanEm45PKyKcRLVXg8qqfoYmxCiUpBNV2GnMeUJNL9jnFsw4) |
| 44 | 30 | same | 2 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/5hqCH8Gum6iCH1adhtttmWyuzsVymUmwhaxc5d7McCJr9Y9FSdciysumprqKxh7TvXZeagdBCBZB3drNAiZ1DcRF) [dump](https://solscan.io/tx/4YtR2CLHAibhw9DpfxfDC8NwqQz5tge2YFKQHxuEZaRGrYWzzwhHvx1dRBwv7KvbnvhpyZj16Ly7h9EJ98hJyKzD) |
| 45 | 45 | same | 6 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5WXg8GJ47St8SbahD7yQyroKgzVVyZDJgYneWQyQ8QSNCeQtiz5UXrVuzxvjrFbRZqwbUcFnnfwkQHcd3L2pDBQs) [dump](https://solscan.io/tx/5oum8QXR5FvM3waeX2bzbXq7BwAdH2D6pohXAxa6AU5e8NqSqWSMQQPVQ8nuMJHN2x8yX65gCN6tX59KbWadr8w) |
| 46 | 126 | same | 4 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/5L7teBXsVETJQS9JBerKdx3a8A8dvxrtu4Hhaerj7GVeDJe5UzkRX4JwE9v5eVcfBehJXUJyrX9cSTvDrpgQ4ocZ) [dump](https://solscan.io/tx/Lbhc6FWNNZRcaWgrgP8inaZ3nz2zH5Lwj8k3d9r3TF9tLZbUCjYcBUW4rT9928AQN9HsQYzrVY9Xp2PsT2htAPq) |
| 47 | 36 | same | 3 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/3iiWGuDbaJhNiKGdcRGEAja9CuTBHSmNMKsyw3QagjbqCCE4aYyTAXkoo6XUwnbYwAkyZDiDFqMbztMN8WGeNNsG) [dump](https://solscan.io/tx/2cuDn2ikaAQGNS4J4QxXNsVPhqXHrAWsBsDafkXnACgxJwsHdoYQTsTSWs4jpiNAwbbrfz3Z9JvkpgncHhUB3XXu) |
| 48 | 31 | same | 2 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4JUSAccPkKGqpLtTF2FCec42sM5XK6TM4aXBE8Y8x8Ar3jGkLRtaaWGru9HMLA4M4UJVFApxg28TJDiVx3vha2Pd) [dump](https://solscan.io/tx/4yXvGY61dUuum3XB9NVi6u3oo8eqKMv5o5erN1ud6tVj2z7qv4S3sH9w4gsDu8q4agqxmCnb8NdJ2hafozN5Abvw) |
| 49 | 35 | same | 3 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4X5u4eKSu72Nrm146ASKYLdPmGjeiWVjFqCDtnjgfGBVJ1yhQ8LsRomdhUhaNBxkVfDtqfsLkTPAw11Rv1dzMBc3) [dump](https://solscan.io/tx/23XuiQUwpNGGj3XYCHQbKaBM2k8BSX9R9cZZG1QZBq3d1dCYyDE2ATSpQ4SsYtxnSeSsMMTZcM6PhK6etDWABeYG) |
| 50 | 74 | same | 3 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4gZ4zbSsYRinBnid4gfWqwgg87iVd4dEUwQGCvhmvrgnQL7oKTEcsNAryxqPJUzsHXk6iuprfr2fwGxgTj1wpCnJ) [dump](https://solscan.io/tx/41UQq9eMW8HfmPyFB4qwpdcLzzwZJCpY28umozfG4iUQ8Xxj8nCfxgQBjruMvkaLvh5i1B46ckuFULjcWzqJZC8M) |
| 51 | 48 | same | 1 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/w3gXBjhyAUUq24Mwnwzix53MUegFUQSye5ocqdhNkaJDwWsz4eaKXk2njUxpe6SAzQED8CCBZXCHXHUbtX9J4ut) [dump](https://solscan.io/tx/vS4o5HCxgePn2oMT8MED2Vvts5M4nkPe3LakvYug2x1iCZoq7wwX69HHYoHnCTCQ1esEFFkptPJHJtxapiTpt5M) |
| 52 | 142 | +1 | 2 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4xqjxzKDpJQVMqXLRWNW561woX2cEtzVtGqHrVgjrDNvCA2J5UUaoSSqwaTUbGXEPzcznVM6SUaKgskRF5hK6gp4) [dump](https://solscan.io/tx/4GT3tETxyGRy41oBP7q6EFB6fdDVVXpVs9FYbV4ENGHsvjQZFoDo5w5Cv51uQDREC3pJXWa5F8ZSZuigFgwtkjD5) |
| 53 | 15 | same | 1 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/xLDEDPU3uhCxQpB4hnzkwb5EUv3rRwwSB8sbe12uJVmB3xhgo12TXfBKgfuffETBRppWjEtf7vhzP7L7fjoySKG) [sell](https://solscan.io/tx/aiGSEkedP6htppe4HAme3TrP5jnUZYcHSNWgKYjxV54vGqLqjGrF6icqrcVrjKM8uZZKcXkomEMU7oLNxGzPn1N) [dump](https://solscan.io/tx/3Zv6YWLUG8UiVBnEFjhwrPSaLF2yZMEHsyVtxdKzgXvoFKX2rfAKQyAHBXHje1BFvD4X3CY3TpNdhmYzUy6gRuNg) |
| 54 | 38 | same | 4 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/45GWqNTJvRFUKxe2JwKo8ybQ7U1HrEqx8V6qn58Q7VQzznQE1XBz2hixytoBqo4ToR1rVRpMvVXWaf1au4aLgAY) [dump](https://solscan.io/tx/4oPvj7m1W3tHbXPeLVgNP82Hmd1gNxBEDq6fpB6svTrj63PLz78FJqeSS2qbJXWrAxMNyJD4H3nKZHpieM39MwTd) |
| 55 | 36 | same | 5 | **helius-swqos** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4e68zFoBR31CGZUb6s1UxiXSU8rhwrvHAcg94BdsMzNFrtyCDtJM5XHs9YNvfBrKfxHjcRybXVXjJ1vjFQjPnJUU) [dump](https://solscan.io/tx/2FFAiAqF7JXLwumPoEuHkStm5Tg5qBj8r89TVn6XEGUn87YLx6ajpW288CTTzK2Xe5Cc8BJgh6FUPMhbB6KsZeKd) |
| 56 | 33 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/25z2q7f7Asz3VrUarf1atgsrc5j9cLadEXMaWt2mMC4ZURgD8TniMm5c6RimNGvSH2SwDVZXj2uXAALuXuL5qzsK) [sell](https://solscan.io/tx/51KtXmR8ZLkeJEzNxHDHNdq4smYBL9bWxAMQRUdTrzL75cuRk7G4gBXv44Ya3gE7muMektRoXiDgAYo5usoXuX7w) [dump](https://solscan.io/tx/2iRTL96AyE72Tq8hRdj9qg6BNxCbVF8BeFLrQAA9shjwo4EqHwdGFW7QBn7c1FtKDZKRLiiYCYfUBzRXJWSfDfqv) |
| 57 | 178 | +1 | 7 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3pZyyzaH6UfmDjPduA9UnBuAGhnGvXDyp26pHMNCfdKXCReVrS79wYDuyocSAee4kfSAysXU4wdVSWNLAVQ6V6bN) [dump](https://solscan.io/tx/2Cfe1KH2S2DsyP2N58Wtc9b6Rpzs5ChxD71TYVTuMAWbkMSR7XWsfi46A8vivfwb821M7gWRFPEMAMKBphPcAbe4) |
| 58 | 50 | same | 2 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc+helius-swqos+bolt | – | – | [buy](https://solscan.io/tx/37TmnNg24i9k1NkVVnv14i2BpYQySbj873iXL1GPag7ww66WgE4xp6eeob862c6ZjgEzoqDnicUbHVRTkDvQuz4Z) [dump](https://solscan.io/tx/JP7ybL2BVNwmWzvYymphzMaTKVer8VDVKqiL4n2rF5MrXgjXMWNTMZQRhsjsidpmdV75n5K5fzVicGSEpry6P8s) |
| 59 | 149 | same | 5 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/476CSu2qxoY7DD9RHwLK7aC2NMyASUXk96wbdzVCBK1FV4Pg5vrgTeDBYj2Wge4hC41WiiQaj7dQ2DNK4ykMq4Lr) [dump](https://solscan.io/tx/5B9dGYJvB7ADBJ7drywEn8BMmwyjSvv9SJTYHnKRMWMmx2qhA1XEUrdr4R9o52mUb2kDS328nNBp4kEbJnEeTYZp) |
| 60 | 46 | +1 | 3 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 2.0 s | 1 | [buy](https://solscan.io/tx/256kz7nxX7MrRfRgQ3q2MCWihb5oVpApRWm1WU1UkA1Btu3YMaMmTLPKPtbLede5NP3aHdhroNn1S2wzutHH3xUd) [sell](https://solscan.io/tx/25AZNyqWq7CSgYtjgTU4bx6LsCJjFAdYUZy5PVhYd2JsxkdPPJotE554RF2PivpWwdDJKWq5473TV21gXyx8hebB) [dump](https://solscan.io/tx/5RcjAR8hS6BwSMkHcQdCsohNQeF1jxST9aMVG5AUQKXmmRVYGk9QTnC4y3Ev4phSKjjEXaJJDU7RXo71AqnCYz4v) |
| 61 | 35 | same | 3 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4m5VnFdjz8MMCSbaTYZ8HF2om5AoLocnzEpFsPr55iAn2UbzHiskyNvd8SYvaCTvy1Pyeoa6RMgxkDyDPSnUd8BK) [dump](https://solscan.io/tx/4AG7rYo7LvGVKSNkb95MKd9hXTzzQnosdJNTvnnUNWsxw6eq8jiXmtKrBtTm2tJN58sBeNKkAL9RtqsCf3VncneC) |
| 62 | 145 | +1 | 3 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/s8YaHCkSJkKZQJqz144NdfqbvDTAu8UwJAxn2cto2kwvHj7FiuQJ7SKWgyYYPCkDeNL99D1PKCc18ER6cUP9TGu) [sell](https://solscan.io/tx/3SVbDzL7tu8xt69QkB8yRGZRJN2LCWoMWWR5mWXt4Q2RroeqhWePf1KXmf5npffXdmywfg8VQ9RghiWD9iXZAbya) [dump](https://solscan.io/tx/3H4pR8SmQoTjzyr9Sx3ydtZhDJQc5QzwzU8MZLUTwPriAeZ3mTPeyAninPerDBz6SaddEHgmjVLVxTD4PM4LNfni) |
| 63 | 213 | +1 | 7 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4Jz9hfm2rScb9b6Q7YbuKnAwq5GckmaxWNDVPvp96h4jVvo2vv3jx8VoJQyirSbJwMadxK1eVk65ZtPt6J6ouKH7) [dump](https://solscan.io/tx/5XhM38T4bRiKi3p3LCnXpFwg93x39ii6GyyefkgGMTEPPZstsP7vk1dh6gyWZrKyVUwsBnfpa4GMAdppKKxiNJgF) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Harmonic | 23 | 11 | 48% | +0.0077 | +0.0012 | 7/11 |
| Jito | 22 | 8 | 36% | +0.0531 | +0.0075 | 3/8 |
| BAM | 12 | 7 | 58% | -0.0002 | +0.0003 | 3/7 |
| Firedancer | 5 | 1 | 20% | -0.0125 | -0.0105 | 0/1 |
| Rakurai | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 37 | 17 | 46% | -0.0474 | -0.0022 | 6/17 |
| dev list | 26 | 10 | 38% | +0.0949 | +0.0103 | 7/10 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 44 | 18 | 41% | +0.0048 | +0.0010 | 10/18 |
| next block | 18 | 9 | 50% | +0.0432 | +0.0053 | 3/9 |
| 2+ blocks | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 01:00 | 2 | 2 | 100% | +0.0189 | +0.0094 | 2/2 |
| 02:00 | 20 | 12 | 60% | +0.0950 | +0.0083 | 6/12 |
| 03:00 | 20 | 8 | 40% | -0.0940 | -0.0110 | 3/8 |
| 04:00 | 12 | 2 | 17% | +0.0549 | +0.0300 | 2/2 |
| 05:00 | 9 | 3 | 33% | -0.0273 | -0.0081 | 0/3 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 22 | +0.2454 | +0.0112 | 1.6 s |
| stop-loss | 5 | -0.1796 | -0.0359 | 1.1 s |

## 8. P&L leaders
**Best trades:** DaWdz2 +0.1159 (Jito, time-limit, score 1.15); GrJNQg +0.0476 (BAM, time-limit, score 1.11); 128N5P +0.0396 (BAM, time-limit, score 0.63)

**Worst trades:** 2xhyMi -0.0471 (BAM, stop-loss, score 0.91); BjCCdA -0.0470 (Harmonic, stop-loss, score 0.83); 7hb9VC -0.0397 (Jito, stop-loss, score 1.04)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `C8Bey3LK` | JitoLabs | 7 | 4 | +0.0925 |
| `7y5VhV4f` | AgaveBam | 1 | 1 | +0.0476 |
| `Fd7btgyS` | HarmonicAgave | 5 | 3 | +0.0429 |
| `PAD9aPiK` | AgaveBam | 1 | 1 | +0.0396 |
| `GEM1N1UE` | AgaveBam | 1 | 1 | +0.0204 |
| `CQdLgwkm` | HarmonicFiredancer | 2 | 1 | +0.0182 |
| `BeaCHioS` | HarmonicFiredancer | 1 | 1 | +0.0147 |
| `Awes4Tr6` | HarmonicFiredancer | 2 | 1 | +0.0095 |
| `9W3QTgBh` | HarmonicAgave | 1 | 1 | +0.0089 |
| `E1r4Psq8` | JitoLabs | 2 | 1 | +0.0016 |
| `EJsJx7Sm` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `A9mvukTd` | JitoLabs | 1 | 0 | -0.0005 |
| … |  |  |  |  |
| `privaEdS` | JitoLabs | 1 | 1 | -0.0015 |
| `H9ENbtmy` | HarmonicAgave | 1 | 1 | -0.0031 |
| `5ZqveVff` | HarmonicAgave | 2 | 1 | -0.0054 |
| `2UBhtRuy` | AgaveBam | 1 | 1 | -0.0076 |
| `EvnRmnMr` | Firedancer | 5 | 1 | -0.0125 |
| `nebu15XQ` | AgaveBam | 1 | 1 | -0.0126 |
| `6XJ4aKjs` | JitoLabs | 1 | 1 | -0.0182 |
| `HEL1USMZ` | JitoLabs | 7 | 1 | -0.0193 |
| `shftkxns` | HarmonicAgave | 1 | 1 | -0.0276 |
| `9jxgosAf` | FireBAM | 3 | 1 | -0.0388 |
| `3iSQtPgk` | HarmonicFiredancer | 1 | 1 | -0.0470 |
| `N43JWBg4` | AgaveBam | 1 | 1 | -0.0471 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1519 (p25 1272, p75 1893, n 63) |
| Executed-feed lag behind first sighting, ms | 2.5 (p25 0.8, p75 5.1, n 63) |
| Buy sent → our tx seen on the feed, ms | 38.5 (p25 29.1, p75 120.3, n 63) |
| Fills: our buy seen on the feed after the dump, ms | 42 (p25 32, p75 81, n 27) |
| Guard fails: our failed buy seen after the dump, ms | 45 (p25 36, p75 142, n 35) |
| Fills in the dump's own block | 18 of 27 |
| Guard fails in the dump's own block | 26 of 35 |

**Which copy landed (nonce fan-out):** staked-rpc 26, nozomi 22, helius 7, landx-fra3 4, jito-bundle 2, helius+helius-swqos 1, helius-swqos 1

**Send-path answers (FAST-ACK lines):** nozomi 63 (median ack 0.3 ms), staked-rpc 63 (median ack 4.0 ms), helius-swqos 40 (median ack 0.4 ms, 3 errors, 3×429), helius 24 (median ack 0.5 ms, 3 errors, 3×429), jito-bundle 24 (median ack 1.1 ms), bolt 15 (median ack 0.4 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 2.47 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 8PgC4ngp | 15 | 7 |
| haqq (dip bot) | 14 | 13 |
| 6n2cCJrr | 11 | 8 |
| HkQ7 (dip bot) | 10 | 7 |
| 9k78QZyw (fast bot) | 9 | 8 |
| 2KtcBC (pre-placed) | 9 | 8 |
| CVPz447t (pre-placed) | 8 | 8 |
| HLU8QbLd (41Pr family) | 7 | 6 |
| 9u5f8WMf | 5 | 1 |
| DF7eRXHn | 5 | 4 |
| 5PuQCemC | 4 | 3 |
| Dk2jdQ93 | 4 | 4 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.3869 |
| Pump fee on buys | 0.1167 (0.0043 per fill) |
| Pump fee on sells (residual) | 0.1215 (0.0045 per fill) |
| Buy tx fees (base + priority) | 0.0136 (0.00051 per fill) |
| Buy tips | 0.0260 (0.0010 per fill) |
| Sell tx fees | 0.0163 (0.00060 per fill) |
| Sell tips | 0.0270 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0182 (36 buys) |
| **Result** | **+0.0475** |

Buy compute used (fills): median 76,755 CU, max 87,254 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 27 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getSlot: 1 timeouts/transport errors (worst p99 280 ms)
- ⚠️ RPC bh-primary getLatestBlockhash: 126 timeouts/transport errors (worst p99 1002 ms)
- ⚠️ RPC exit-primary getSignatureStatuses: 1 timeouts/transport errors (worst p99 1001 ms)
- ℹ️ send path helius-swqos: 3 × HTTP 429 (rate limited) on buys
- ℹ️ send path helius: 3 × HTTP 429 (rate limited) on buys
- ℹ️ 48 send-path health events (self-heal), e.g. `SEND-PATH rpc bh-primary UNHEALTHY: 3 timeouts / transport errors in a row (getLatestBlockhash): client REBUILT (fresh p`
- ⚠️ DsBjEX: landed 4 blocks after the dump

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Recommended / open:**

- A/B: Frankfurt trades on M2 (run 15), Amsterdam on IMIT1 without BAM leaders (run 14).

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r14.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r14.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

# Frankfurt run 2 — dip bot run report

*5 trades × 0.25 SOL, routes v3, engine dip8*

> **Verdict:** Good: 4 of 5 fills won (+0.1333 SOL). Runs 1+2 together +0.2582 SOL, but 72% of buys still missed.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.1333 SOL** (wallet 3.9823 → 4.1156, Δ +0.1333) |
| Started (PKT) | 2026-10-24 03:03:59 |
| Ended (PKT) | 2026-10-24 03:50:31 — max fills reached (5 of 5) |
| Ran for | 0 h 46 min of 120 min planned |
| First / last buy (PKT) | 03:04:09 / 03:50:29 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 18 → **5 filled**, 12 failed on the +5% guard, 1 failed (other) |
| Fill rate | 28% |
| Wins / losses (fills) | 4 / 1 (win rate 80%) |
| Per filled buy | avg +0.0280, median +0.0182 SOL |
| Fills only / failed buys only | +0.1399 / -0.0066 SOL |
| Best / worst trade | 5yi9Q2 +0.1039 / GZRarp -0.0147 |
| Fill landing | median 62 ms after the dump (seen on our feed); 1 of 5 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip8 (timing records, near-leader gate available but off) |
| model / tier | IMIT1 strict (score >= 0.5419) |
| size (normal) | 0.25 SOL |
| dev list | off |
| exit | take-profit +5% / stop-loss −10% / time limit 6 slots (~1.3 s) |
| price guard | +5% over the post-dump price (pump error 6042 if exceeded); slot deadline = dump slot + 1 |
| buy fee (priority) | 5M µL/CU × 100k CU limit = 0.0005 SOL per landed buy tx |
| sell fee | 5M µL/CU × 120k CU limit (0.0006 SOL per landed sell tx) |
| route: agave leaders | nozomi + helius |
| route: bam leaders | nozomi + bolt |
| route: default leaders | nozomi + bolt |
| route: fd leaders | nozomi + landx-fra3 |
| route: harmonic leaders | nozomi + helius |
| route: jito leaders | bolt + astralane |
| route: other leaders | nozomi + bolt |
| sell path | staked-rpc (retry also via nozomi) |
| near-leader gate | off (every leader) |
| pre-send | off |
| durable-nonce fan-out | off (one tx to every path, every path's tip in it) |
| backup RPC | RMR_RPC_URL |
| holder-reward tokens | allowed |
| limits | max 5 fills, 1 open at a time, 120 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 1**:

| Setting | FRA run 1 | FRA run 2 |
|---|---|---|
| engine build | dip6 (sha c6f1b40f; holder-reward tokens allowed) | dip8 (timing records, near-leader gate available but off) |
| route: agave leaders | helius + nozomi | nozomi + helius |
| route: bam leaders | helius + astralane | nozomi + bolt |
| route: default leaders | helius + nozomi | nozomi + bolt |
| route: fd leaders | nozomi + helius | nozomi + landx-fra3 |
| route: harmonic leaders | nozomi + astralane | nozomi + helius |
| route: jito leaders | helius + nozomi | bolt + astralane |
| route: other leaders | helius + nozomi | nozomi + bolt |
| limits | max 3 fills, 1 open at a time, 120 min, loss cap 0.500 SOL | max 5 fills, 1 open at a time, 120 min, loss cap 0.500 SOL |

- Engine dip6 → dip8 (timing records in every fire).
- Routes v3 from probe D: BAM = nozomi + bolt, Jito = bolt + astralane, Harmonic = nozomi + helius, FD = nozomi + landx-fra3, Agave = nozomi + helius, others = nozomi + bolt.
- Max fills 3 → 5 (owner plan).

## 4. Timeline (PKT)
- **03:03:35** start refused: `Error: keystore: wrong passphrase or damaged file` (nothing sent)
- **03:03:35** first start ended after 8 s (an extra run-2 entry in the budget file); restarted at 03:03:46
- **03:03:59** engine start #1 (session with 18 buys)
- **03:09:50** big win: 5yi9Q2 +0.1039 SOL (take-profit)
- **03:50:31** engine end #1: run end

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 3307 |
| Inside the envelope (age / drop / since-buy / size) | 1550 |
| Picks (score above the threshold) | 19 |
| Skipped | spacing 1 |
| Buys sent | 18 |
| Filled | 5 |
| Failed on the +5% guard | 12 |
| Failed (other) | 1 |
| Never landed | 0 |
| Sold (positions closed) | 5 of 5 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 03:04:09 | [ErXGrP](https://gmgn.ai/sol/token/ErXGrPkVkNH9pWdHuii5JNvdwHifY6NyqgCZWvLobTQe) | 0.25 | 0.80 | 12.15 / −49% | 1.1 s | ? `9GHvMe` | failed | -0.0005 |
| 2 | 03:05:43 | [2WrTTh](https://gmgn.ai/sol/token/2WrTTh4zTPAdAQTPDZvZjtU8eLEawCgDanzBygoMpump) | 0.25 | 0.59 | 4.42 / −22% | 3.8 s | Firedancer `DNVZMS` | guard fail | -0.0005 |
| 3 | 03:09:50 | [5yi9Q2](https://gmgn.ai/sol/token/5yi9Q2mvGaWEjCAviaWppkXqaY4ot2H8yR2mUAP6pump) | 0.25 | 0.69 | 2.03 / −10% | 1.3 s | Jito `C8Bey3` | filled | **+0.1039** |
| 4 | 03:16:35 | [GiHFe5](https://gmgn.ai/sol/token/GiHFe5qSTXatMjCoPgHnohgCNmiDtGSgscGRWtiJpump) | 0.25 | 1.02 | 3.51 / −14% | 191.9 s | BAM `Aw5wEM` | guard fail | -0.0005 |
| 5 | 03:18:41 | [Fxje8f](https://gmgn.ai/sol/token/Fxje8ftSy9mJD6XDCBcv7x5BhnnLRbn65LpbJkcRpump) | 0.25 | 0.75 | 5.30 / −16% | 111.1 s | Firedancer `9eGrDo` | guard fail | -0.0005 |
| 6 | 03:20:17 | [NjXjez](https://gmgn.ai/sol/token/NjXjezdD9CZbRVsEdXXdCCzbz3HG6wWDtTXF3qhuw4V) | 0.25 | 0.79 | 3.62 / −20% | 3.0 s | Harmonic `DcTPJq` | guard fail | -0.0005 |
| 7 | 03:24:38 | [2HWLS5](https://gmgn.ai/sol/token/2HWLS5bjJGWgtLTdrrav3TN34WuEqqURPb4nVkz89Wa7) | 0.25 | 0.80 | 4.99 / −26% | 2.1 s | Harmonic `SFundN` | guard fail | -0.0005 |
| 8 | 03:28:26 | [GZRarp](https://gmgn.ai/sol/token/GZRarpWzBaYmaSSzppGDFr4uB4JnTgBQ8oS6ro5fpump) | 0.25 | 0.75 | 4.55 / −13% | 280.1 s | BAM `DRpbCB` | filled | **-0.0147** |
| 9 | 03:31:50 | [CGbMG1](https://gmgn.ai/sol/token/CGbMG1rQpHPQBjood2oTHCJx3tDTX3iZX3oMgt8Vpump) | 0.25 | 1.29 | 2.92 / −14% | 215.2 s | Jito `8o8wWC` | guard fail | -0.0005 |
| 10 | 03:31:54 | [CGbMG1](https://gmgn.ai/sol/token/CGbMG1rQpHPQBjood2oTHCJx3tDTX3iZX3oMgt8Vpump) | 0.25 | 0.96 | 4.12 / −20% | 218.6 s | Jito `bitHUm` | guard fail | -0.0005 |
| 11 | 03:34:04 | [DrWCph](https://gmgn.ai/sol/token/DrWCphA6frwWELd9FHJ24S86CbgGsJvRivsnN6Mvngoy) | 0.25 | 1.07 | 4.48 / −17% | 5.7 s | BAM `AfZTWY` | filled | **+0.0246** |
| 12 | 03:34:49 | [DDAk5R](https://gmgn.ai/sol/token/DDAk5RLJw8PdQ4q2g2QaqWDK4T69dft61gYP2uiHpump) | 0.25 | 1.36 | 3.43 / −16% | 71.4 s | BAM `Cu9Ls6` | guard fail | -0.0005 |
| 13 | 03:36:38 | [Cjv7Wa](https://gmgn.ai/sol/token/Cjv7WabqGdcaAxNVXip2g641ArxwAB5KAnaNGX6bdPQ) | 0.25 | 1.23 | 6.20 / −31% | 1.3 s | Jito `Df16xM` | guard fail | -0.0005 |
| 14 | 03:39:29 | [4fCN5R](https://gmgn.ai/sol/token/4fCN5RT8PvB62DMTpJWKuCdfEoqk5zPrrsFpbzPRpump) | 0.25 | 0.64 | 2.97 / −13% | 7.4 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 15 | 03:43:47 | [FwDZn1](https://gmgn.ai/sol/token/FwDZn1YpBYnuYqoKDfC96WRGjbtjjcCTJYP2hZawWNgh) | 0.25 | 0.66 | 7.01 / −32% | 4.0 s | Jito `privaE` | guard fail | -0.0005 |
| 16 | 03:45:09 | [AC3g7R](https://gmgn.ai/sol/token/AC3g7RqANnmVHu7zPxcjJ3zTJn5A2Yx3MA2dstivpump) | 0.25 | 1.24 | 3.14 / −15% | 102.2 s | Harmonic `CAo1dC` | filled | **+0.0182** |
| 17 | 03:50:01 | [Db79BV](https://gmgn.ai/sol/token/Db79BVa5bFp49nk7D9GWAFZuHaK6sw5BL4F1mWBNJrn7) | 0.25 | 1.52 | 4.43 / −24% | 3.2 s | BAM `2VKu11` | guard fail | -0.0005 |
| 18 | 03:50:29 | [25yfy9](https://gmgn.ai/sol/token/25yfy9rXf1jDNKnPX4Km6z2Lu8Fjw9fGxPP8psbapump) | 0.25 | 1.13 | 3.08 / −14% | 40.3 s | Harmonic `87CcUx` | filled | **+0.0079** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 108 | +2 | 3 | nozomi+bolt | – | – | [buy](https://solscan.io/tx/Ft89C4RNhseekfa5hib4H8rqyKDDm5iYquohJ2b5wA4r6M4q8itudkn5pj3w47kaxm8ZMq6r937djDMmoVBZ2FR) [dump](https://solscan.io/tx/4BYnxSPWDDWuGM46YZQYRrh83RZKTuKpqqAKGJez8GqqCUJCKexTpYc9qLA5iSK7rzZvkYT2q1dnmSdUyHyU3dXt) |
| 2 | 40 | +1 | 4 | landx-fra3+nozomi | – | – | [buy](https://solscan.io/tx/5MSmDco231L1xZshtxhMCb9Pu6r8yNpVZ36Q7zMtLpn3urD9PuaFpPAXEgJH6W7WQMwzhZGtaHK5W9CS4fJNtGY3) [dump](https://solscan.io/tx/4qvGa2xNDehx3Zt6JTRBp1XnF9Mkp1egPXr4gnmmHNg8p9MjMpoS6DNgXxtxJSFpvTkUP5gMov4cwVB43WECkKMx) |
| 3 | 59 | +1 | 0 | bolt+astralane | take-profit 1.5 s | 1 | [buy](https://solscan.io/tx/Aqr5L3SqfkEB8e2dpS4AherGYcbJgUTbLu7FmSuresSie75eVDpNo44iC1A4zkGM4Qfv3NKeNuXSGmUpB2pGKVy) [sell](https://solscan.io/tx/5NHnRDEKurrGGV553LxRW79WkRxDCumXh6NJBHu5pvokwic8FiUd5Mr8juMdxwX2nKPehE8obG6FqyK7pXFRZjJ1) [dump](https://solscan.io/tx/5hP4Z6mjfLdjDTFmViQTHe7NLP2rrA14VgqFoJh1kZMCeS8sghiHAg5ZcYBnkYViqE9rjEL6PPJVZ9KYsvdFqimp) |
| 4 | 45 | same | 3 | nozomi+bolt | – | – | [buy](https://solscan.io/tx/bYuyJkQ6pXuZrd87CVmXsZam5YXwsAMj6JFx5b9ni786gccgTFcQDVi8Ebdrj3KitekobNucoLESdogu6kqTtHL) [dump](https://solscan.io/tx/2omEiEUZ5vQaFZmPecmPHSuqJsiVgM1f3qL67V12B9FrrD6Zi4H4pXDLUKCEQWcaJWcL57Eo2saDf3UX33bzGr35) |
| 5 | 110 | +1 | 5 | landx-fra3+nozomi | – | – | [buy](https://solscan.io/tx/2zDLjaT5hqAZ7UBbY1qoUMZY2AzQVmse53bD3kyAi4oL1dThTHUYeeMWBCAsNsovnQU3WpWdrjjU6BB6fJcujdTb) [dump](https://solscan.io/tx/5JmmWkz3bejEoWunYQ2Gba4HA2FUG9jRrykmGF32cTByhnwVFZGirGP521VtANU2jv8zjTKH28rWjhTubQ7qjfjX) |
| 6 | 41 | same | 1 | nozomi+helius | – | – | [buy](https://solscan.io/tx/5ZnhEqALeWkzxbLTsAkgGN6iXdhHmmgStbzAoCg36VDduoLE2qxpSaz5rBNBwQ4cb7tWVktJTvBM1aBiEGn76tQW) [dump](https://solscan.io/tx/4R5xRwdqAF65huCGDtNzd8eRZMDmJweFzTBBi8yyvRv1vUpTbLy3WWPkcHWoBRP47msFVMb82BtzG7L9T3dioHgt) |
| 7 | 343 | +1 | 2 | nozomi+helius | – | – | [buy](https://solscan.io/tx/uG6N7LTh2sWAmYuWGP6nzgTHj5vsqUE95zVgeSSfphahwV853WxM9cwZE7Es8Tb8ZtxxWwcA32Ka2RWH2Y1cjze) [dump](https://solscan.io/tx/57ybwnLDtGWfDbcAwdYeLUnR14N13ghzKZSAAAy4g2Msj5ABJEK1r4ZGtvJ9daW5FUQX3yY3EqvGy7qRnUTib6Nk) |
| 8 | 62 | +1 | 1 | nozomi+bolt+astralane | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/2jAFtiUVbaRDcFK1fzcTD3S63CjkMcaiwBftCthFsjeSsAz6kPB3iktc7xmVRLQAxJW7GEfgUZgkWn5vHU37c91N) [sell](https://solscan.io/tx/Feva8N4S1y3As42UhzgvM38tdkhcvhyEFFC9qRivheev39BM516LHsm3mFv7WC7daJW7u4DNk8TxvQSVahenyaU) [dump](https://solscan.io/tx/2K7oPz4C2tYpYceCEFrHsgcs6NXS5LJtRs8G8JVMzwN1h678ChAgvpVrpWi5WnTtsECDy5aA6EhxatAFNRbckVLg) |
| 9 | 75 | same | 5 | bolt+astralane | – | – | [buy](https://solscan.io/tx/3n1yMU1P8NyLCSAFYcevXuLUQb6AfQeytifjHmKa1a3ntDHHgEcznBHQkR4bKzd7AmpvJ5WKrFPb13qxBGZNQHzu) [dump](https://solscan.io/tx/2Bv3uRZdcKA328MVrbcG25eNTGRRdTtzfEdyJ18428kV4DTLZg4xsg9akVjEVbRiQoxkpprKTX7CeENRSsbMFSuA) |
| 10 | 231 | +1 | 2 | bolt+astralane | – | – | [buy](https://solscan.io/tx/43NR3bPiYNTKJ6Xh4U8XLcdGj5DzCmnm7J8cydEQhJqLbMmTu8DwpQHNHz3ZoSujvzFgNsNKVDoUP5bqRFUrccQ) [dump](https://solscan.io/tx/3SKb5zw8W1cWuw2HMFwj7n2m4djkGmMTo5sUTFCv9wqEyP97RAKee3273rsVJ3gHCSHAEiYrMfnY1TSeC4ptkLg2) |
| 11 | 186 | +1 | 2 | nozomi+bolt | take-profit 0.9 s | 1 | [buy](https://solscan.io/tx/4dZAD7yx3DfFCoBnd4dMZgYr4cBojmQ7E61GL9PEKoEH3KCKj36y1vm266c3Na3ugDwSZ2cxpZjrUcFfkmFaw5D1) [sell](https://solscan.io/tx/3uqkStDBHDRShDTvH5kH5W7JHCqAVvyqVqqPnwYcYvcaPgde2g5XVRYyzYb1f7ggpXPRHLqSBAswKEF9F6cJZdk9) [dump](https://solscan.io/tx/2aAp6p1xaZwKC8znB6NNJ4VE76BY3xXaja7TaZGZvGMs41eCRMyYXv2Tr7Pc4ZeEM2h9vavGgQ4BkgKcELB6hBxX) |
| 12 | 40 | same | 5 | nozomi+bolt | – | – | [buy](https://solscan.io/tx/oA9SDU6PCFfVxxWCWxJXAURg7A8T4dxSe2dnTR7YiHQgQuVZQpUDWbiS1mHn9aQvSaPssh5ZX7RPo6Tz4ZNGDsP) [dump](https://solscan.io/tx/4B7ciU4SJVN51exmDeUjJoxrEhJ5VP6vNoQvF9iVyDxycfXhDxdFYB5SSSJWPya72mHx1zmmGqs3oZSZ1ikyG7rP) |
| 13 | 120 | same | 9 | bolt+astralane | – | – | [buy](https://solscan.io/tx/4JK9AiYtoN7Yi5RMRTcwi1V7M35uAazDgiM4AqT8iRiiAEfP6Tw5jp845pQ6WDJBpAGdewuCmgMV4b37RhMjM3sh) [dump](https://solscan.io/tx/5ZWeraTrJcNcBqXqx5Y3bCJb33JBjdFkasvsbYf59ygFK2qty45Ygjns2cCpoepF6fiX7aMwL53pzq4GNSEUJR2s) |
| 14 | 18 | same | 3 | landx-fra3+nozomi | – | – | [buy](https://solscan.io/tx/3iojUrMtD95zCuLso8FNnq7XGsB9u1a6tQVXETRk1YyE5r3sRXaGi4BQEaQrfuqKCrgYWrtyEhe4QJyYst4c3uaW) [dump](https://solscan.io/tx/Qxtck15Nz8f3MPLXiGHc3KMKtki5ie5SnJVLGiDGGHpdNwNDPYSct1DPMn1r4SnzDoppzEVnZXin3UVNgp4ZHgh) |
| 15 | 39 | same | 3 | bolt+astralane | – | – | [buy](https://solscan.io/tx/42RMVrrt2NawQGqePt6SyuoQ6XhooZfJbX9nkrTmUb7KbcdCexVZF3euHY2A1aGto2fCdCmFTPGyPPoquVCtjRJj) [dump](https://solscan.io/tx/3AWy4J3koYBUnPi5hUaGiA7DYmHcBykfXHpJiebfVBxt4NBHnZQY4TMzj3z11QZ3fKJeZtiyRQbstKxm6spiQAn9) |
| 16 | 35 | same | 0 | nozomi+helius | take-profit 0.5 s | 1 | [buy](https://solscan.io/tx/5o5rALJvftEzVbW6DrvXTVUfFJv76sHmfyrRC5yGjRATw4BcfcFzbsQ3B51RpHh6VdKZf5Zu2jx1WNAMac7y6tGg) [sell](https://solscan.io/tx/3bgLPvRqrZMEdMUyar3ygoUxDWycsFtX15qpCaceLuiaswhc93F8z8zZtfWdg7a7kERKmzmTBdrvbrwGd5v4YLvm) [dump](https://solscan.io/tx/4kH4Fb3nn8LYdTRAjgvtQ6eLagzwDNawMhymW8daxWpq39MNAMpW6krQm4JAUqn3CogpjC4H13BRywY9umEZXqBy) |
| 17 | 71 | same | 4 | nozomi+bolt | – | – | [buy](https://solscan.io/tx/4egH7Nmdc3efrixV1URuHojQXk2Fpxwfu1gEnXSgnCvwAXkWr6rghvgwKMfrfWADahPvLvkhLWh8SJ5DFs5mzrR6) [dump](https://solscan.io/tx/5TZtYrCx2UUsX8ZdZMA2rnxDHom4NGRQ5pWHvbq3YmyjEHDNbegrVmH7VFiQLd6xBHixYhkZi5NUemL76H1ahzhg) |
| 18 | 119 | +1 | 1 | nozomi+helius | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/4Vr6sMGBc1toya3yii1EEXQM7QQZrq3C3ZfBKg3iW7dvwLkdXU362xKNc3gG4xC4qpkVFrG6AjQtoPfhuNLJrHup) [sell](https://solscan.io/tx/29Akz1yGchwQ4SzceXtN4QF5AEnX5YXHWgnLtqC81rn9YBsG7UkMuJFTiqTNzjTRiPDgMQS919CBJMX23tGv3sYs) [dump](https://solscan.io/tx/aUkCYSwGoM6gDPpNvVi2zVkooNmCbWUmKTVM4qQZMeoUj465V5cBpsYFV8xj2G1pn4wU3LSBHFagkUunq1d8uNX) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Jito | 5 | 1 | 20% | +0.1019 | +0.1039 | 1/1 |
| BAM | 5 | 2 | 40% | +0.0083 | +0.0049 | 1/2 |
| Harmonic | 4 | 2 | 50% | +0.0251 | +0.0131 | 2/2 |
| Firedancer | 3 | 0 | 0% | -0.0015 | – | 0/0 |
| ? | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 18 | 5 | 28% | +0.1333 | +0.0280 | 4/5 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 9 | 1 | 11% | +0.0142 | +0.0182 | 1/1 |
| next block | 8 | 4 | 50% | +0.1196 | +0.0304 | 3/4 |
| 2+ blocks | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 03:00 | 18 | 5 | 28% | +0.1333 | +0.0280 | 4/5 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| take-profit | 3 | +0.1467 | +0.0489 | 0.9 s |
| time-limit | 2 | -0.0069 | -0.0034 | 1.7 s |

## 8. P&L leaders
**Best trades:** 5yi9Q2 +0.1039 (Jito, take-profit, score 0.69); DrWCph +0.0246 (BAM, take-profit, score 1.07); AC3g7R +0.0182 (Harmonic, take-profit, score 1.24)

**Worst trades:** GZRarp -0.0147 (BAM, time-limit, score 0.75); 25yfy9 +0.0079 (Harmonic, time-limit, score 1.13); AC3g7R +0.0182 (Harmonic, take-profit, score 1.24)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `C8Bey3LK` | JitoLabs | 1 | 1 | +0.1039 |
| `AfZTWYoF` | AgaveBam | 1 | 1 | +0.0246 |
| `CAo1dCGY` | HarmonicAgave | 1 | 1 | +0.0182 |
| `87CcUxpy` | HarmonicFiredancer | 1 | 1 | +0.0079 |
| `9GHvMeJ4` |  | 1 | 0 | -0.0005 |
| `DNVZMSqe` | Firedancer | 1 | 0 | -0.0005 |
| `Aw5wEMXh` | AgaveBam | 1 | 0 | -0.0005 |
| `9eGrDohd` | Firedancer | 1 | 0 | -0.0005 |
| `DcTPJqPN` | HarmonicAgave | 1 | 0 | -0.0005 |
| `SFundNVp` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `8o8wWCYN` | JitoLabs | 1 | 0 | -0.0005 |
| `bitHUmbK` | JitoLabs | 1 | 0 | -0.0005 |
| `Cu9Ls6ds` | AgaveBam | 1 | 0 | -0.0005 |
| `Df16xM2X` | JitoLabs | 1 | 0 | -0.0005 |
| `EvnRmnMr` | Firedancer | 1 | 0 | -0.0005 |
| `privaEdS` | JitoLabs | 1 | 0 | -0.0005 |
| `2VKu11f8` | AgaveBam | 1 | 0 | -0.0005 |
| `DRpbCBMx` | AgaveBam | 1 | 1 | -0.0147 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1035 (p25 898, p75 1247, n 18) |
| Executed-feed lag behind first sighting, ms | 1.7 (p25 1.0, p75 2.5, n 17) |
| Buy sent → our tx seen on the feed, ms | 57.7 (p25 35.4, p75 107.8, n 17) |
| Fills: our buy seen on the feed after the dump, ms | 62 (p25 59, p75 119, n 5) |
| Guard fails: our failed buy seen after the dump, ms | 58 (p25 40, p75 110, n 12) |
| Fills in the dump's own block | 1 of 5 |
| Guard fails in the dump's own block | 8 of 12 |

**Send-path answers (FAST-ACK lines):** nozomi 13 (median ack 0.4 ms), bolt 11 (median ack 0.3 ms), astralane 6 (median ack 0.4 ms), helius 4 (median ack 0.8 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 1.66 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| HkQ7 (dip bot) | 5 | 5 |
| haqq (dip bot) | 4 | 4 |
| CVPz447t (pre-placed) | 3 | 2 |
| 3MHgGwdL | 3 | 3 |
| 2KtcBC (pre-placed) | 3 | 3 |
| DYXD (dip bot) | 3 | 2 |
| GonzYBmk | 2 | 1 |
| 3mK48y1P | 2 | 1 |
| EprLoV21* | 2 | 2 |
| ssssswdk (sss fleet) | 2 | 1 |
| 5w8xtjc6 | 2 | 2 |
| 63otb3qf | 2 | 2 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.1947 |
| Pump fee on buys | 0.0154 (0.0031 per fill) |
| Pump fee on sells (residual) | 0.0179 (0.0036 per fill) |
| Buy tx fees (base + priority) | 0.0025 (0.00051 per fill) |
| Buy tips | 0.0110 (0.0022 per fill) |
| Sell tx fees | 0.0030 (0.00060 per fill) |
| Sell tips | 0.0050 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0066 (13 buys) |
| **Result** | **+0.1333** |

Buy compute used (fills): median 72,254 CU, max 94,757 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ start refused: Error: keystore: wrong passphrase or damaged file
- ⚠️ 5 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ℹ️ RPC bh-fallback getLatestBlockhash: slow minutes (worst p99 553 ms, max 646 ms)
- ℹ️ RPC bh-fallback getSlot: slow minutes (worst p99 552 ms, max 650 ms)
- ℹ️ RPC exit-fallback getSignatureStatuses: slow minutes (worst p99 331 ms, max 348 ms)
- ⚠️ ErXGrP: landed 2 blocks after the dump
- ℹ️ GZRarp (−0.0147) landed on a far leader (Ashburn) at a BAM → Jito slot edge and paid 3 tips; DYXDDrZC bought 1.16 SOL ahead of us
- ⚠️ 13 of 18 buys missed (guard / 1 deadline)

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED.

## 13. Fixes and follow-ups
**Done after this run:**

- haqqiUUX check (owner: 'no failed txns?'): 11.4% of its txs fail like ours (GMGN hides them); it uses its own router, Helius with tiny tips, CU price ~1.84M.
- Blueprint generated: ops/dip/BLUEPRINT_V1.html.

**Recommended / open:**

- Run 3: 10 trades at 0.35 SOL (owner).

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r2.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r2.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 1.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

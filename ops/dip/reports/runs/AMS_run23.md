# Amsterdam run 23 — dip bot run report

*Live 5.5 h: reactive M2 + routes v13 on dip19; 0.35 SOL, dev list 0.35; pre-send SHADOW only*

> **Verdict:** −0.101 SOL on the wallet (1.9052 → 1.8040), matches the engine (fired 99, landed 30, realized −0.101281). 30 fills (9 wins): fills −0.066, failed buys −0.035. One trade kept it close: 4fh6MRuf +0.265 (Harmonic, 19:57); without it −0.366. BAM leaders weak: 13 fills, 3 wins, −0.210 with their failed buys; Harmonic +0.133.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.1013 SOL** (wallet 1.9052 → 1.8040, Δ -0.1013) |
| Started (PKT) | 2026-10-26 16:10:55 |
| Ended (PKT) | 2026-10-26 21:40:55 — time limit / max trades |
| Ran for | 5 h 30 min of 330 min planned |
| First / last buy (PKT) | 16:17:09 / 21:31:20 |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 99 → **30 filled**, 68 failed on the +5% guard, 1 failed (other) |
| Fill rate | 30% |
| Wins / losses (fills) | 9 / 21 (win rate 30%) |
| Per filled buy | avg -0.0022, median -0.0115 SOL |
| Fills only / failed buys only | -0.0664 / -0.0348 SOL |
| Best / worst trade | 4fh6MR +0.2646 / HhcnPh -0.0874 |
| Fill landing | median 33 ms after the dump (seen on our feed); 24 of 30 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip19 |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.35 SOL |
| exit | take-profit off / stop-loss −50% / time limit 5 slots (~1.1 s) |
| price guard | +5% over the post-dump price (pump error 6042 if exceeded); slot deadline = dump slot + 1 |
| buy fee (priority) | 5M µL/CU × 100k CU limit = 0.0005 SOL per landed buy tx |
| sell fee | 5M µL/CU × 120k CU limit (0.0006 SOL per landed sell tx) |
| route: agave leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: bam leaders | nozomi + helius-swqos + bolt + falcon + falcon-udp + soyas + solami + 0slot |
| route: default leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: fd leaders | 0slot + nozomi + landx-fra3 + staked-rpc + soyas + solami |
| route: harmonic leaders | nozomi + landx-fra3 + falcon + falcon-udp + glaive + soyas + solami + 0slot |
| route: jito leaders | solami + soyas + glaive + falcon + falcon-udp + helius-swqos + 0slot |
| route: other leaders | nozomi + helius-swqos + bolt + staked-rpc |
| sell path | staked-rpc (retry also via nozomi) |
| near-leader gate | 120 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off (shadow only) |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 500 fills, 1 open at a time, 330 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 22**:

| Setting | AMS run 22 | AMS run 23 |
|---|---|---|
| limits | max 500 fills, 1 open at a time, 720 min, loss cap 0.500 SOL | max 500 fills, 1 open at a time, 330 min, loss cap 0.500 SOL |

- Same settings as run 22; time limit 330 min (owner stopped run 22 at 16:08 and restarted at 16:10).

## 4. Timeline (PKT)
- **16:10:55** engine start #1 (session with 99 buys)
- **16:22:07** big loss: HhcnPh -0.0874 SOL (time-limit)
- **19:57:06** big win: 4fh6MR +0.2646 SOL (time-limit)
- **20:38:35** big win: DM3K8n +0.0517 SOL (time-limit)
- **21:02:20** big loss: EAfJMn -0.0612 SOL (time-limit)
- **21:04:54** big win: 98NafQ +0.0582 SOL (time-limit)
- **21:10:24** big loss: 9xqERd -0.0523 SOL (time-limit)
- **21:40** time limit (330 min) reached; run 24 started 21:47 with pre-send LIVE
- **21:40:55** engine end #1: run end

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 28452 |
| Inside the envelope (age / drop / since-buy / size) | 13716 |
| Picks (score above the threshold) | 476 |
| Skipped | far_leader 309, spacing 63, legacy_create 4, max_open 1 |
| Buys sent | 99 |
| Filled | 30 |
| Failed on the +5% guard | 68 |
| Failed (other) | 1 |
| Never landed | 0 |
| Sold (positions closed) | 30 of 30 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 16:17:09 | [7VZgom](https://gmgn.ai/sol/token/7VZgomNHW52sSgxiyf7bSgurRWDTiL8UwvuoCrg6pump) | 0.35 | -0.43 | 4.74 / −21% | 1.9 s | Jito `ACvL73` | guard fail | -0.0005 |
| 2 | 16:22:07 | [HhcnPh](https://gmgn.ai/sol/token/HhcnPh9J8b8Yfr8dAVvrX7DpFSvy9Ukfvm5gAAUEiYeS) | 0.35 dev | 0.61 | 1.81 / −9% | 1.1 s | BAM `AWcCdY` | filled | **-0.0874** |
| 3 | 16:28:27 | [Bo5Nyb](https://gmgn.ai/sol/token/Bo5NybcY4NRF1zVzAsi4vMgXXhKLJPx4Vxsj7a7zpump) | 0.35 | 0.40 | 4.21 / −20% | 3.6 s | BAM `6WgdYh` | guard fail | -0.0005 |
| 4 | 16:29:08 | [5CdESJ](https://gmgn.ai/sol/token/5CdESJjWHugmFtZPpbr7r34VQoDJ88tf8mmuNZacpump) | 0.35 | -0.28 | 2.67 / −13% | 8.9 s | Harmonic `GoeW4a` | guard fail | -0.0005 |
| 5 | 16:34:13 | [5kSDr8](https://gmgn.ai/sol/token/5kSDr8S8JN3F7tLMhLfqFAGUMubedyDMzJVGy453pump) | 0.35 | 0.14 | 3.79 / −15% | 7.6 s | BAM `STKEsv` | guard fail | -0.0005 |
| 6 | 16:43:39 | [3TpidP](https://gmgn.ai/sol/token/3TpidPwUnjmyzkwbzooNbBaQzyu8V6LU4BRgkYHHpYS6) | 0.35 dev | 0.81 | 4.02 / −16% | 4.7 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 7 | 16:44:08 | [GQtMoe](https://gmgn.ai/sol/token/GQtMoeuK5sfZdZmTap3hy5xm69WQA5372KiZ5XqUf6XF) | 0.35 dev | 0.24 | 2.09 / −12% | 8.7 s | Jito `LeDbQ9` | guard fail | -0.0005 |
| 8 | 16:45:31 | [3apAxd](https://gmgn.ai/sol/token/3apAxdQdgNYHmBw96rBUhfpm1VKABnd7dArhMZNppump) | 0.35 | 0.09 | 2.48 / −11% | 5.7 s | BAM `bkpk9K` | filled | **-0.0055** |
| 9 | 16:59:00 | [B28wZt](https://gmgn.ai/sol/token/B28wZtQ6aD8mj4AUo54MaXNu1xmYAyNkdNwkyYdi9S2e) | 0.35 dev | 1.53 | 4.37 / −24% | 3.2 s | Jito `2Df1aL` | guard fail | -0.0005 |
| 10 | 17:01:00 | [AgxFFo](https://gmgn.ai/sol/token/AgxFFozTgrCuH7GsSDDG1RDBfGizHcgsXVxdeKYLpump) | 0.35 | 0.26 | 3.70 / −19% | 3.8 s | Harmonic `AMukCL` | guard fail | -0.0005 |
| 11 | 17:05:58 | [HpMnNy](https://gmgn.ai/sol/token/HpMnNyNiZazCSnDuydZE8WpVKWe9WMjHMtxxyZjyJW2q) | 0.35 | -0.15 | 4.84 / −21% | 24.0 s | BAM `vALigX` | guard fail | -0.0005 |
| 12 | 17:07:08 | [6j1zQN](https://gmgn.ai/sol/token/6j1zQNQ63PCxuSoWv5PLvURtt7AYz6KfCL8TU2NZpump) | 0.35 | -0.11 | 3.93 / −16% | 15.9 s | Harmonic `2m1A2W` | filled | **-0.0102** |
| 13 | 17:14:52 | [D2mxvk](https://gmgn.ai/sol/token/D2mxvkinkuQiWKZkkDZKtv4oN2mQ7Y9tSoRUBMRfpump) | 0.35 | -0.42 | 1.98 / −11% | 2.8 s | BAM `CoG8d9` | filled | **-0.0018** |
| 14 | 17:21:13 | [5BMX1p](https://gmgn.ai/sol/token/5BMX1pNbEGsXboxAcExtRAoyhMrmr72oL9KWYKBayHMz) | 0.35 dev | 1.22 | 4.72 / −24% | 1.5 s | BAM `AWcCdY` | guard fail | -0.0005 |
| 15 | 17:34:45 | [2kgmFs](https://gmgn.ai/sol/token/2kgmFsCT6JyDXaJKACucuJX1TixagfMqgqGeohFWqfbX) | 0.35 | -0.53 | 3.68 / −13% | 130.6 s | Harmonic `HTeRsa` | guard fail | -0.0005 |
| 16 | 18:00:22 | [2BUHHL](https://gmgn.ai/sol/token/2BUHHLXgdFNzyVxp3LsbdUVaBXSf97SC6TdGwVVKhesq) | 0.35 dev | 0.94 | 3.93 / −21% | 1.3 s | BAM `6WgdYh` | filled | **-0.0146** |
| 17 | 18:10:36 | [2geUqx](https://gmgn.ai/sol/token/2geUqxStzcJp9mjX1ohRY74ZBJHMXp7kBrJxJ2m9Uwaa) | 0.35 dev | 0.76 | 8.98 / −39% | 4.2 s | Jito `2oHUYy` | filled | **-0.0197** |
| 18 | 18:10:43 | [4gKzsw](https://gmgn.ai/sol/token/4gKzswCKbeZmoc45VKmwY27wTMcXEF4d4VJNySd1iVYg) | 0.35 dev | 0.59 | 3.56 / −20% | 3.0 s | Jito `GnC339` | guard fail | -0.0005 |
| 19 | 18:13:51 | [76DGoC](https://gmgn.ai/sol/token/76DGoCSzxQCB2xrqunEME8CDgkJvixKdKA41AHDvotMe) | 0.35 dev | 0.94 | 2.43 / −9% | 1.9 s | BAM `7tqeaF` | filled | **-0.0087** |
| 20 | 18:18:28 | [6vpDNg](https://gmgn.ai/sol/token/6vpDNg87FCbPg2eNyahbRrrXgraaRqTXAyKBuKsY7RLf) | 0.35 dev | 0.28 | 13.36 / −51% | 2.8 s | Jito `2oHUYy` | guard fail | -0.0005 |
| 21 | 18:23:35 | [Hbj4LU](https://gmgn.ai/sol/token/Hbj4LUFajyUUZPpCMntJodkNtrJaHxbwzqGj2tjC5xtb) | 0.35 | -0.04 | 2.85 / −11% | 8.3 s | Harmonic `2m1A2W` | filled | **-0.0221** |
| 22 | 18:23:37 | [Hbj4LU](https://gmgn.ai/sol/token/Hbj4LUFajyUUZPpCMntJodkNtrJaHxbwzqGj2tjC5xtb) | 0.35 | 0.27 | 4.23 / −15% | 10.6 s | Jito `ACvL73` | filled | **+0.0223** |
| 23 | 18:23:50 | [HLaP2j](https://gmgn.ai/sol/token/HLaP2jD91rk1nE7AvphZst7UnTZb6jZMnA1N4y7576gE) | 0.35 dev | 0.79 | 8.10 / −38% | 3.4 s | Jito `BCJN2v` | guard fail | -0.0005 |
| 24 | 18:26:26 | [4PYggJ](https://gmgn.ai/sol/token/4PYggJAvuEomR8r7cMzCfZ7a4tpsyQ1agSpsgxsppump) | 0.35 | -1.34 | 5.00 / −20% | 5.9 s | BAM `GSTamp` | guard fail | -0.0005 |
| 25 | 18:27:09 | [4UJyzj](https://gmgn.ai/sol/token/4UJyzj84DP4sicPytwTHebmWvFksa2FVEeX1okVP96Zt) | 0.35 | 0.43 | 3.79 / −18% | 29.7 s | Jito `ABC1U4` | guard fail | -0.0005 |
| 26 | 18:32:19 | [FGtRMy](https://gmgn.ai/sol/token/FGtRMyGtHYm6DuYnWvGfgS3aL9NY7QSNRdunsM6xpump) | 0.35 | -0.81 | 6.72 / −22% | 9.3 s | Firedancer `HW4zor` | filled | **-0.0150** |
| 27 | 18:32:29 | [FGtRMy](https://gmgn.ai/sol/token/FGtRMyGtHYm6DuYnWvGfgS3aL9NY7QSNRdunsM6xpump) | 0.35 | -0.72 | 2.06 / −11% | 19.1 s | Harmonic `2m1A2W` | guard fail | -0.0005 |
| 28 | 18:33:21 | [5Ft4d3](https://gmgn.ai/sol/token/5Ft4d3Yb5t7sMyXVc9Ezr22zjnhXYNDHCrtCbzSQpump) | 0.35 | 0.40 | 4.97 / −17% | 8.5 s | BAM `7CR3Jq` | guard fail | -0.0005 |
| 29 | 18:35:52 | [53b67J](https://gmgn.ai/sol/token/53b67JhZLPauxrh93bVoxVrDipx8orXYEPdPFQDrpump) | 0.35 | -0.46 | 2.99 / −16% | 23.5 s | Jito `Df16xM` | guard fail | -0.0005 |
| 30 | 18:37:01 | [B7QPn4](https://gmgn.ai/sol/token/B7QPn42gF57jCGwL5BpQLoR32qThD8LSjNukdja1pump) | 0.35 | -1.89 | 1.44 / −8% | 35.2 s | Harmonic `AMukCL` | guard fail | -0.0005 |
| 31 | 18:45:17 | [Du7adD](https://gmgn.ai/sol/token/Du7adDLLCXVFXhXtTCRACpSEM1bxyJQbzPAzTHAupump) | 0.35 | -1.35 | 1.82 / −11% | 5.7 s | Harmonic `GoeW4a` | guard fail | -0.0005 |
| 32 | 18:53:04 | [HtG4aP](https://gmgn.ai/sol/token/HtG4aPgb4db96mqo8VhuQ5Td5Aj8ER1MR8gqGDjsm1x9) | 0.35 dev | 0.52 | 2.54 / −15% | 4.0 s | Harmonic `AMukCL` | guard fail | -0.0005 |
| 33 | 19:00:07 | [Csz8Tn](https://gmgn.ai/sol/token/Csz8TnG3aWTR7bCtBEXXuXNgR8cu1LyXqxvTnEGspump) | 0.35 | 0.03 | 5.30 / −18% | 4.9 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 34 | 19:00:25 | [Csz8Tn](https://gmgn.ai/sol/token/Csz8TnG3aWTR7bCtBEXXuXNgR8cu1LyXqxvTnEGspump) | 0.35 | -0.58 | 4.90 / −15% | 22.7 s | BAM `5tfcGy` | guard fail | -0.0005 |
| 35 | 19:20:38 | [4zakn8](https://gmgn.ai/sol/token/4zakn8Gy7iPqBfQD2yh25YAysiyuWoxJJ1HzQUENpump) | 0.35 | 0.63 | 6.13 / −26% | 1.1 s | Harmonic `BbCQMW` | guard fail | -0.0005 |
| 36 | 19:23:20 | [9R4yzQ](https://gmgn.ai/sol/token/9R4yzQKZFVy5DExC1SYsrNyeseqkF3kwGhU9urEqGeyb) | 0.35 dev | 0.52 | 6.49 / −20% | 65.3 s | Harmonic `2m1A2W` | guard fail | -0.0005 |
| 37 | 19:27:56 | [GdgAZT](https://gmgn.ai/sol/token/GdgAZTfLVVwxh6KaxoHcveC3ikCoT9kncBFHKdoKaAWU) | 0.35 dev | 0.61 | 8.13 / −38% | 4.5 s | Harmonic `EkvdKh` | guard fail | -0.0005 |
| 38 | 19:28:03 | [GwaCpa](https://gmgn.ai/sol/token/GwaCpagHu4fM7JusqovKZmW373jR5Dh7A5UH5Eqhpump) | 0.35 | -2.83 | 1.62 / −9% | 10.2 s | Harmonic `GoeW4a` | filled | **-0.0228** |
| 39 | 19:29:29 | [2DkuBn](https://gmgn.ai/sol/token/2DkuBnM6LVU7T1NSNRjV5KXNcfuib95kmkPgQQJXpump) | 0.35 | -0.93 | 2.16 / −9% | 3.6 s | BAM `22rU5y` | filled | **+0.0024** |
| 40 | 19:32:40 | [Fho3Xz](https://gmgn.ai/sol/token/Fho3Xz8Bw1hkv4j11E8eoMagwufNECjvT1HRri4Ypump) | 0.35 | -1.84 | 1.64 / −10% | 14.0 s | Harmonic `EkvdKh` | filled | **-0.0196** |
| 41 | 19:37:08 | [3broca](https://gmgn.ai/sol/token/3brocanySTUQJX5yC2yV5rsRM3CoBbKkfm295SvRpump) | 0.35 | -0.70 | 1.17 / −6% | 4.2 s | BAM `LA1NEz` | filled | **-0.0324** |
| 42 | 19:37:42 | [CS1jiW](https://gmgn.ai/sol/token/CS1jiWhDzQPqzGmzAUVVmpjrrKnH3sFKK5Y3LmfHKjYB) | 0.35 dev | 1.02 | 3.58 / −20% | 4.9 s | BAM `bkpk9K` | guard fail | -0.0005 |
| 43 | 19:38:13 | [9SMAUc](https://gmgn.ai/sol/token/9SMAUcBgWooqKyaeVUDUeJ6Y3UUkL726CC4zj4ZTXD2c) | 0.35 dev | 0.84 | 6.57 / −31% | 3.8 s | BAM `GSTamp` | guard fail | -0.0005 |
| 44 | 19:39:42 | [GTi15k](https://gmgn.ai/sol/token/GTi15kLzyYoLkTmnkmXEJx5tMoFeXsoUKRD1R72Cpump) | 0.35 | -1.69 | 1.50 / −9% | 11.7 s | Jito `AHNX2Y` | filled | **+0.0018** |
| 45 | 19:51:14 | [sSUegi](https://gmgn.ai/sol/token/sSUegietZX8SukuYz66yXTykWQuGG48bvoNaiZToNvy) | 0.35 dev | 0.26 | 8.11 / −38% | 8.7 s | BAM `GSTamp` | guard fail | -0.0005 |
| 46 | 19:52:01 | [4XjSmy](https://gmgn.ai/sol/token/4XjSmyZQtgx51TJu43MaWLYEp5HkQhxzC7UtwcgPpump) | 0.35 | 0.31 | 5.16 / −25% | 11.9 s | Jito `8NpDWR` | guard fail | -0.0005 |
| 47 | 19:53:44 | [FU1Yop](https://gmgn.ai/sol/token/FU1YopYwkJrQ47nCaCUb8jnXjbRZGzxs4bfYvyCPpump) | 0.35 | -0.64 | 3.40 / −19% | 7.4 s | BAM `Ninja1` | guard fail | -0.0005 |
| 48 | 19:56:04 | [ANvDJL](https://gmgn.ai/sol/token/ANvDJL2ihxYpqjFtmqSCfxdnt78d4ScMjhRBq4bVpump) | 0.35 | 0.18 | 3.23 / −18% | 3.6 s | BAM `GSTamp` | guard fail | -0.0005 |
| 49 | 19:56:13 | [6hgC2o](https://gmgn.ai/sol/token/6hgC2oh8HpP24cPuJCZ6fGDwCtPbvd9LD96FwSa7pump) | 0.35 | 0.23 | 2.62 / −14% | 4.5 s | Jito `LeDbQ9` | guard fail | -0.0005 |
| 50 | 19:56:31 | [8ybS1D](https://gmgn.ai/sol/token/8ybS1DxjFc88NLYY8yGaJZParKQzzx36VpdmgQKapump) | 0.35 | 0.06 | 6.47 / −21% | 4.9 s | Harmonic `HTeRsa` | failed | -0.0005 |
| 51 | 19:56:56 | [6cMiu3](https://gmgn.ai/sol/token/6cMiu3G2JVLBN8ujXw4xGamhghtRHrk3QobGptnPweVW) | 0.35 dev | 0.22 | 8.46 / −34% | 2.1 s | BAM `PUmpKi` | guard fail | -0.0005 |
| 52 | 19:57:06 | [4fh6MR](https://gmgn.ai/sol/token/4fh6MRufdskqwDjUTKcauRsm4UTP9wUCwwmvoT6Dpump) | 0.35 | 0.15 | 4.92 / −18% | 10.6 s | Harmonic `A1vqhA` | filled | **+0.2646** |
| 53 | 19:57:42 | [3f5UT4](https://gmgn.ai/sol/token/3f5UT4NaMWnLFEEmECvbHV3aBTGZuu5RiAqbbrNppump) | 0.35 | -0.88 | 4.25 / −12% | 79.9 s | Harmonic `GoeW4a` | filled | **-0.0006** |
| 54 | 19:59:47 | [pu5Q3G](https://gmgn.ai/sol/token/pu5Q3GD2VBS4nuMym4LpCTa453HnspYvd1UjTBQpump) | 0.35 | -0.68 | 2.75 / −11% | 4.7 s | Jito `GnC339` | guard fail | -0.0005 |
| 55 | 20:00:09 | [3K5eiz](https://gmgn.ai/sol/token/3K5eizUn6qoueLgJGt2V7vMpeV2TmQNxmhXhHeuMpump) | 0.35 | -0.58 | 5.47 / −27% | 6.2 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 56 | 20:01:52 | [Eob121](https://gmgn.ai/sol/token/Eob121Uhdp3iqbqugoBvwmcKrsVwVcxF8VE9bqbWpump) | 0.35 | -0.07 | 2.63 / −13% | 4.2 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 57 | 20:02:44 | [2rpGeZ](https://gmgn.ai/sol/token/2rpGeZeuPR3sEVHZ8dY6SuwyP51dtddKwfmsFrTtTjPu) | 0.35 dev | 0.82 | 6.76 / −33% | 8.3 s | Harmonic `2m1A2W` | guard fail | -0.0005 |
| 58 | 20:11:16 | [5sCE8t](https://gmgn.ai/sol/token/5sCE8tvdBA3US6suimHaenDw5QjQSeWdemMwTePBpump) | 0.35 | -1.13 | 2.79 / −10% | 4.9 s | Jito `AEHqTB` | guard fail | -0.0005 |
| 59 | 20:11:26 | [DfCpS1](https://gmgn.ai/sol/token/DfCpS17hPcpu7PKvWxxHtqw2cXK5127M3FuZZU5Pxf25) | 0.35 | 0.83 | 5.08 / −18% | 46.2 s | BAM `GBQ2Gv` | guard fail | -0.0005 |
| 60 | 20:11:40 | [3fNpt2](https://gmgn.ai/sol/token/3fNpt2NVKMRCrYJHvE4sUSLKLTdAdSK21yvDeujJpump) | 0.35 | 1.11 | 6.29 / −25% | 5.9 s | Harmonic `HTeRsa` | guard fail | -0.0005 |
| 61 | 20:11:45 | [3fNpt2](https://gmgn.ai/sol/token/3fNpt2NVKMRCrYJHvE4sUSLKLTdAdSK21yvDeujJpump) | 0.35 | 0.77 | 3.36 / −14% | 10.8 s | Jito `G8kUFx` | guard fail | -0.0005 |
| 62 | 20:11:47 | [Gb9P9J](https://gmgn.ai/sol/token/Gb9P9J95LnSBSCTeZFdU96pf4kk444S4KWwrtxtspump) | 0.35 | 0.17 | 2.34 / −11% | 4.5 s | BAM `Aw5wEM` | guard fail | -0.0005 |
| 63 | 20:11:51 | [J1uKUj](https://gmgn.ai/sol/token/J1uKUj7hJczuHWSgWha12jX2z8L12wyCUfDER5c3pump) | 0.35 | -0.36 | 3.46 / −19% | 7.6 s | Jito `Cogent` | guard fail | -0.0005 |
| 64 | 20:16:26 | [D8jPLf](https://gmgn.ai/sol/token/D8jPLfbH9ijt6pADx2BZRmBiXR1i9u6Yv6VFHJBptxN7) | 0.35 dev | 0.44 | 4.99 / −26% | 1.7 s | BAM `6aDs9t` | guard fail | -0.0005 |
| 65 | 20:16:34 | [GU3L7H](https://gmgn.ai/sol/token/GU3L7HuyJifFZxMHShfGK5Uf9RJVrbKeixJX3FxmoyVJ) | 0.35 dev | 0.72 | 9.85 / −41% | 1.9 s | BAM `GSTamp` | guard fail | -0.0005 |
| 66 | 20:18:36 | [3fnYSi](https://gmgn.ai/sol/token/3fnYSiLd2HAE3xi4mrW9tv98WSx2o3WNsP6jvuPypump) | 0.35 | 0.18 | 3.23 / −13% | 4.5 s | BAM `PAWsME` | guard fail | -0.0005 |
| 67 | 20:27:38 | [3ofedb](https://gmgn.ai/sol/token/3ofedbqVkqiYMu55E87GMioD5L7bA9b8ixtx2maupump) | 0.35 | -1.85 | 1.54 / −9% | 61.5 s | Harmonic `2m1A2W` | guard fail | -0.0005 |
| 68 | 20:29:00 | [GqwmZv](https://gmgn.ai/sol/token/GqwmZv5Z5XSA7pe2hy8PWu3GQMen5QJ1QMhsiC9UL4jZ) | 0.35 dev | 0.53 | 14.39 / −52% | 2.1 s | BAM `6WgdYh` | guard fail | -0.0005 |
| 69 | 20:29:06 | [CWPWAt](https://gmgn.ai/sol/token/CWPWAtFZR8a8M2X3QrPCj6qfv9TzV7isdNoLLKebpump) | 0.35 | -0.34 | 5.83 / −16% | 5.5 s | Harmonic `BbCQMW` | filled | **+0.0223** |
| 70 | 20:29:24 | [Hs3q9s](https://gmgn.ai/sol/token/Hs3q9seeqHxuvkeLnMA8A9jNEN9bDkpZ8r467YDoehYu) | 0.35 dev | 1.25 | 8.30 / −38% | 1.5 s | BAM `5essVp` | guard fail | -0.0005 |
| 71 | 20:29:38 | [9FJKhC](https://gmgn.ai/sol/token/9FJKhC8PPYo7XV3q43adF33zKEuqvpXXCpuXARJqmZuX) | 0.35 dev | 0.53 | 5.27 / −20% | 1.3 s | Harmonic `Ex1AxF` | guard fail | -0.0005 |
| 72 | 20:30:07 | [Hpbz5Y](https://gmgn.ai/sol/token/Hpbz5YSyijAAvUXB1rokjSf8rCYQVALwzK9qmq5XHphQ) | 0.35 dev | 0.27 | 3.07 / −14% | 2.3 s | Harmonic `ALp2Gd` | guard fail | -0.0005 |
| 73 | 20:30:54 | [WBApSF](https://gmgn.ai/sol/token/WBApSFtANKBBfNB96f5Kgvrv3Dd2RoWACqJLEw5pump) | 0.35 | -0.82 | 2.16 / −13% | 8.9 s | BAM `5essVp` | guard fail | -0.0005 |
| 74 | 20:31:02 | [E8HRhG](https://gmgn.ai/sol/token/E8HRhGru9jdouPavFFmufyhcyVUPJgukphJRWciEomMf) | 0.35 | -0.35 | 7.26 / −34% | 4.7 s | Jito `74MzXS` | guard fail | -0.0005 |
| 75 | 20:37:55 | [BN1RxW](https://gmgn.ai/sol/token/BN1RxW9CYKsCFmzKJdvJ8pTFdz4VEkmmB8ZmPpJZtNTs) | 0.35 dev | 1.21 | 8.51 / −39% | 2.1 s | BAM `AWcCdY` | guard fail | -0.0005 |
| 76 | 20:38:28 | [8SQm7S](https://gmgn.ai/sol/token/8SQm7Sw5LdLDAEiBHPoefYYqm2wBWFLTLRu6Y5bXtShd) | 0.35 dev | 0.30 | 11.85 / −49% | 3.6 s | Harmonic `GoeW4a` | guard fail | -0.0005 |
| 77 | 20:38:33 | [7NUK2F](https://gmgn.ai/sol/token/7NUK2FuzmS6uK9C9n9P4sgLaQjr6KjaXoK9pH4Hupump) | 0.35 | 0.80 | 3.65 / −15% | 68.0 s | Harmonic `DrifTr` | filled | **+0.0042** |
| 78 | 20:38:35 | [DM3K8n](https://gmgn.ai/sol/token/DM3K8nPfPJXEpoKFz22dMjF8py5mPPjd3cWhi4Bfpump) | 0.35 | -1.06 | 2.13 / −11% | 28.8 s | BAM `PUmpKi` | filled | **+0.0517** |
| 79 | 20:38:40 | [7bFKj1](https://gmgn.ai/sol/token/7bFKj1Eh9FD7mNnCoKrtracZ8UZfDV7A8NVsQZjn1KBJ) | 0.35 | -1.67 | 2.32 / −12% | 8.1 s | Harmonic `2m1A2W` | filled | **-0.0021** |
| 80 | 20:42:35 | [8urBrS](https://gmgn.ai/sol/token/8urBrSVEMFgzWjZKD87DTCncXdhtxRZzZMZTFP8hLTmC) | 0.35 dev | 0.28 | 3.43 / −16% | 11.2 s | BAM `6TkKqq` | guard fail | -0.0005 |
| 81 | 20:44:25 | [BSpweZ](https://gmgn.ai/sol/token/BSpweZQUqVMvfndfVGuZP8RrDeqwpmYqXuLf5gWTpump) | 0.35 | -0.93 | 2.38 / −10% | 3.8 s | BAM `HbidP4` | filled | **-0.0128** |
| 82 | 20:45:53 | [HHKFej](https://gmgn.ai/sol/token/HHKFejj3J4apCjbgtainKspvwwS2mRbtFevFPD2Npump) | 0.35 | -0.74 | 3.58 / −14% | 27.4 s | BAM `5tfcGy` | filled | **-0.0385** |
| 83 | 20:48:06 | [HMWYPU](https://gmgn.ai/sol/token/HMWYPUXHs68yQuZonKKzV3JZqZMDQfTEfJDHZtbppump) | 0.35 | -1.53 | 8.26 / −22% | 13.1 s | Jito `GnC339` | guard fail | -0.0005 |
| 84 | 20:51:42 | [A1pXL7](https://gmgn.ai/sol/token/A1pXL7uC332Mw23u69AA354M4nsdQgeCUrZaazKXpump) | 0.35 | 0.15 | 5.22 / −26% | 5.9 s | BAM `6TkKqq` | filled | **-0.0456** |
| 85 | 20:57:46 | [3guVh3](https://gmgn.ai/sol/token/3guVh3Mynz2GxxvCTU8LmnKx3csKKVzQaSpzRSbSpump) | 0.35 | 0.63 | 4.24 / −15% | 6.8 s | Harmonic `ALp2Gd` | guard fail | -0.0005 |
| 86 | 20:57:47 | [5QLjcY](https://gmgn.ai/sol/token/5QLjcYv1efXccDY1pbJunTsBrUEs2paKPgg7sP9wpump) | 0.35 | 0.54 | 6.15 / −22% | 12.9 s | BAM `6WgdYh` | guard fail | -0.0005 |
| 87 | 21:02:20 | [EAfJMn](https://gmgn.ai/sol/token/EAfJMnpU1gAVnPT8jgGdAC5kXxKbqf1Dbow7TXXnpump) | 0.35 | -0.81 | 2.71 / −13% | 18.2 s | BAM `76rcGH` | filled | **-0.0612** |
| 88 | 21:04:54 | [98NafQ](https://gmgn.ai/sol/token/98NafQzcKeSdWDruuzoHFZbnWf1dsR89iymZDGcnpump) | 0.35 | -0.10 | 2.77 / −14% | 8.1 s | BAM `HbidP4` | filled | **+0.0582** |
| 89 | 21:10:24 | [9xqERd](https://gmgn.ai/sol/token/9xqERdeGYts73fEVNiAA1SkCv44ruprgcuuY4RLbpump) | 0.35 | -2.04 | 1.30 / −7% | 7.8 s | Harmonic `HTeRsa` | filled | **-0.0523** |
| 90 | 21:11:00 | [7iVgM1](https://gmgn.ai/sol/token/7iVgM1p2Hqr3x6sENueLLSJVRPqR7i5KifnBNVYdpump) | 0.35 | 0.36 | 2.86 / −16% | 36.9 s | BAM `AWcCdY` | guard fail | -0.0005 |
| 91 | 21:12:39 | [3hEvDG](https://gmgn.ai/sol/token/3hEvDGHpAnJgTF1j87eATRC2AU38TS1WeKuHuw7Bpump) | 0.35 | -1.00 | 3.08 / −12% | 12.5 s | Jito `2Df1aL` | filled | **-0.0232** |
| 92 | 21:17:20 | [6TDcpk](https://gmgn.ai/sol/token/6TDcpkqcaiGLZX3pqEGa6B8faLThQR9RtkhQ8HQtMH5q) | 0.35 | 0.96 | 6.62 / −33% | 7.8 s | Harmonic `DrifTr` | guard fail | -0.0005 |
| 93 | 21:19:48 | [EYAV7A](https://gmgn.ai/sol/token/EYAV7AwkSpRTGxdLWHzYMAKjaxputFHUn1uc9deFpump) | 0.35 | -1.29 | 1.36 / −8% | 6.6 s | BAM `GBQ2Gv` | guard fail | -0.0005 |
| 94 | 21:19:56 | [7j22EZ](https://gmgn.ai/sol/token/7j22EZCy1Ecxn8FWHmcJi3sh3UxQs1ELZUBmoYceYbpy) | 0.35 dev | 1.01 | 8.18 / −38% | 2.5 s | BAM `BUv44c` | guard fail | -0.0005 |
| 95 | 21:20:18 | [HxLu3q](https://gmgn.ai/sol/token/HxLu3q9HSPoKGQykjTq5ZPTSHn15wKB6pJivd9zjHQHh) | 0.35 dev | 0.22 | 1.50 / −9% | 5.9 s | Harmonic `AMukCL` | filled | **-0.0181** |
| 96 | 21:21:26 | [3t4nX6](https://gmgn.ai/sol/token/3t4nX692WdMr89YyNdM1pP7nndeThLh6ciYH8Bsua7vN) | 0.35 | -0.12 | 6.62 / −33% | 5.9 s | Jito `ACvL73` | guard fail | -0.0005 |
| 97 | 21:30:20 | [2fEifo](https://gmgn.ai/sol/token/2fEifoNMiQ9amEh1nXdhFpWzDSa87YmwHczbJyerpump) | 0.35 | -2.02 | 1.41 / −8% | 8.7 s | Jito `5pPRHn` | filled | **+0.0203** |
| 98 | 21:30:36 | [H1qpBJ](https://gmgn.ai/sol/token/H1qpBJL7Sxr3XUgoZGtpKeXWLdEzpQT1m88A2Kmgpump) | 0.35 | -0.73 | 2.84 / −16% | 27.1 s | BAM `6WgdYh` | guard fail | -0.0005 |
| 99 | 21:31:20 | [B8BzJv](https://gmgn.ai/sol/token/B8BzJviYA92hFDkJwN6dW6zxzwGjbLCspSGq66KjC1Wc) | 0.35 dev | 0.24 | 7.12 / −30% | 12.1 s | Harmonic `HTeRsa` | guard fail | -0.0005 |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 136 | +1 | 6 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/2iRkqfiL53dLPH9EqWyuoAuBkBVwa6rqk8Z338ixobpxo246QUAX9NQVDmuEu9WfzgNu3QdvBNtLS2jP3DiPz6VF) [dump](https://solscan.io/tx/4PAqKASr9JHi6X3yWxUD8qEresgch3wUaJXoaetQDFMZEqPk46gjdsWJfzRxyyygmoGNtjasRv1gsv334N7QZLeE) |
| 2 | 32 | +1 | 1 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/b9cUxWsrwRtyKr8do3NnTdxXTyjc29bPqq4N1ugec6L1x1sR7KfMqiXudyvbHYxfVHg6DasmvNGtuHrw5g83rcN) [sell](https://solscan.io/tx/5AsRMyYF6kUQ4djgASTx7rNPf23NqwKUeLkVTYZ2YLtXirD5672cSK444NPxgFui7GY9VDihtVCQHpECt9i5mGjb) [dump](https://solscan.io/tx/5vLcAftDR9vcdMWeJ2ZRfiT39FYiFLvZKsxbBYhUFQ7eJQwoFTrAA2hEypZP27xuAMTKWCkrSrwdEtq1YTgLFQca) |
| 3 | 19 | same | 6 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/2aFdnounJmVnSJjeNSp4pcNP5TAekWw16rejYDGFyDQh862h2Uo9gyutXVLXm1eDT33EoBWjoBEXinEaT7qEpECH) [dump](https://solscan.io/tx/2xaxsJdPmyygZfutFx7U6Q4EW9Ge9EZudMCb21j6ahex5ov49SNUwz7G3sXpiQU5c8JYyeykbdd7RSTqYfGWv7tr) |
| 4 | 39 | same | 3 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2vbR9bGoEJ8FHZFgkY892q2V53S7s6wNM4qMM7F6Xru7QtQ8unNh73J93RUVYDWihPkN11pUaxtsa6RAJqn9988J) [dump](https://solscan.io/tx/2eerETe7qW2NmZTtrW2NH3texvrL2uRJGPGGTaKvSaa6CRr8epDF8yjA4peqEet7FUH6NJh9AhbqKTRWTt4SKDiB) |
| 5 | 31 | same | 2 | **glaive** of falcon-udp+landx-fra3+nozomi+helius-swqos+bolt+falcon+0slot+glaive | – | – | [buy](https://solscan.io/tx/jRsrfFtsexx7Fhiok4k5TGJEJYqjAskKk1ayxpowtGCaPDJVet9UAc4HixPUejXNYEiovZF3qmvngkDZxDpKZLx) [dump](https://solscan.io/tx/43UvMvj4V72231dkriEEhMt3xoLq1oE2WxVCZJjNqotx6gvfzKB6ken6SWZgSFDFLzQNfaU4WCzDhniFSoFn2ngc) |
| 6 | 111 | +1 | 11 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/3yvBdMj5JFt1Dz9ZHCZfU4TMUx8JvbVazzfED4Vi2EFS6B3PSpseVGibtErgd3rCpF45B6K7PjDUVJmZipKsymZz) [dump](https://solscan.io/tx/2hzYUyCDHtSfDe9jFWr9mzXF6TUKpm7Zq6ouwMbwmmBceTmXVt6NStbhp4KHtpzydHoJrhffZAA8kwPtSz9z12Gf) |
| 7 | 110 | +1 | 1 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/5E1GrkHSDYMLDt5NiL5tzUML5hCyimLwRVk6U5LqVP13kGwp7M6fqUNnFmRSisp5KeaCct3SZVBn2J8UyF6C59Nz) [dump](https://solscan.io/tx/2gyqRU1gBuaZtnejBo1pPwy3QAwoX3xnJQe6KmqyKw6XSmhCqduRocP2Vz2RUFKaEmB614moSGvmicRRzC22kKDU) |
| 8 | 27 | same | 3 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/2CjMVs2fusxbBngiPFtbUTCZdGrLhL82KaTVaJv3WqMitX9XBDG5RXpi1aUM8vfPKY6oJ6v3pS4eE7iEiidr76K8) [sell](https://solscan.io/tx/2MQDwDhFCtiYyTc5cWpSYsyXhL5uCC6vTN74czqA3V88ySVgKkkE6wcHktYhmTLq7R21cky9uhDt6B85vVw4jLnb) [dump](https://solscan.io/tx/kvAxK9VSAZjdHzv4bquAhx2vaNUGv7o7a41jZYeSskApkqndwWhtwuahRLQ84QYR765r4S1884Kzz9Qvt58Z8Sj) |
| 9 | 128 | +1 | 6 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/3cPzRDZDQamMGGSkZC1VGezhvY1oHmKEQNPoxffCTJ6rcu21yhj76j5CZWfGxVDwamim37XM14gGozhrQpNwc28J) [dump](https://solscan.io/tx/5xZ5vdzuEqRLF2LjdKhrud3pcMQwAJqf9tTioriLiYnpkzx9SKL3M1FWrVZkCVqmzG8Sin2zhmMp4ZLgKCPuDgb) |
| 10 | 62 | +1 | 6 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/375X8fR3oveVCKAn8G7nJHY2TTha9dPYmC38kNkAFoueLCt28AuSoTDNjwE41cEDimJ6EFnUQR7Ux5ftzvsgRmxs) [dump](https://solscan.io/tx/5krk78EFRinyKoBsiZRVH4726gHcK3oozSHrag4sZJsPTFrKY9c8GcnFDAoboCesFksD8XmobFTuagy3VjSTs1R9) |
| 11 | 16 | same | 3 | **glaive** of falcon-udp+landx-fra3+nozomi+helius-swqos+bolt+falcon+0slot+glaive | – | – | [buy](https://solscan.io/tx/43bs6nVzVyNpCdrEhqw452gY5mRwoP935MjtBbyxUAWy9BsuDra4V688Q6XkkusZRLwaFHLDe1aVr1uEqFBGEdrd) [dump](https://solscan.io/tx/5hGaz5UPvGiNTzUqDzcrfFygmEKLrZP6SvE9ZL64b3VngS7AkC2ntH9CgXaGiztfoFsByargMBddj6e5xPWN59J6) |
| 12 | 34 | same | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5D38hgwLF5S4rFCgx8EFcAaGRr1EXdLCoQx4jBFPeMHFDLcRQHiSnmTr9CoRskurri7zYQjddcZ1a5jFdkhe8MY7) [sell](https://solscan.io/tx/5hhR562oS5HeY33GNoPdHcFBZhRSHCfvqDb8ZtkjW6LcBxDEw9tVPrsRqJTFYL2V2pEskPSEo4L9fVpATbqcJ7DS) [dump](https://solscan.io/tx/416aZdjPnzENwWuduQC1xLCt52PkATnzGqWFQE2Sz8sXb71SxY1mCdXbqbb2RXjNodNgFvZov7C3qqWWpdzQFznB) |
| 13 | 21 | same | 1 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/3AqyUqMQy93XZLsdEACfAVBsceJDV7hj9brRbsoKDgdrrzT7fuCjNLEfrw5mPd2xoduMvFbme8XhXxnWVK9ThMNH) [sell](https://solscan.io/tx/58pys7hCF71opYEcCuDLKVFa1vSEwzQsfRBnSKJq15ctbt34x7ZAwbQUtn37KNbpRjqrmghKW4Uru1DYpg5Efpua) [dump](https://solscan.io/tx/2EQwqb2e3r9tFNeFTLCXhbmmU67LM8DEdo8b1pfQv9sPgqfSRHfwjDQR8z9yg5FHWMxyLwQ7GzKoZWRmAkNy4ph4) |
| 14 | 22 | same | 3 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/XSGNrZqhtUrTsLFyxqNWm6MysUXPCMjLpGWNFShpwRmW2rN7LjBLpn5VyntK87xtLj49ADQnHwscyci9Agi8aAB) [dump](https://solscan.io/tx/38fQMV4mKtmZA3jk6rD7rPdyQFW3hbAAwRGeorhfyrCYziQLZMkmcV5DXaGaQoyB7DhJ7SptxD8DbR7gG5nUG9Q5) |
| 15 | 40 | +1 | 7 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/59JR5JySwstR1u55m4197vtjJk6M7B48QKEEuoiNcnoLc3VxLiPpdXBk5oqPJ28Wt76aRWh6s5Xa3ZjEmNi9xhLU) [dump](https://solscan.io/tx/3QW7mQL1Eu2qVbXH5TwMgYKV4QpkMQ7tk6tUgSkzgEsf25VYdLZzVFy8GzuBsWzTcKcsTsP67S7wunLZdZqCqFDZ) |
| 16 | 16 | same | 1 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/3AWoPyauQYukk6bKKCfjeaF2Wd6zTn6xuw5nuGkSYfD6TpewibF2uNpAQkU2XnTYKrqmTiqLNuxgkVwmB6U82XmV) [sell](https://solscan.io/tx/3GtXsBuwg6gDz2W5LJCHkmB8iEboGEwPfj1vgmK3K8zwCx8wjCpygCRpbg43r139cHdKWdLQbKagxj1upSqhCuk5) [dump](https://solscan.io/tx/5vwsLrnUf43mdYGbeRewMjEyg5LsaXLZPk63uQTFhaa3dQGsqQmsHC1Vqt9PSuxMQYHiKrv4tvdYUWeufCH9XdJi) |
| 17 | 15 | same | 1 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/EU4KHdLkc4ry1TFmRgsuKRkB8RGaNdYKgcP5yru1xp3TWfLdpXQaiD4VcqdtsiQBvSmWntFgNCzB8N2q8GJRfHa) [sell](https://solscan.io/tx/higw9h3Taq371TX2x6RL3GxfxYoEifdMJqzaxZH9XaCMq9b69YiXbvzzZtEWe42ym58Eo88weExoaooH443buMT) [dump](https://solscan.io/tx/NhbfGZNfs7kM8uEae44b4jA3iScU1gGFS1jfSaoYpZJC5izpNJPekaAC7rpW1SPmh5qDt9vYmMXh3vbLwApNmm2) |
| 18 | 11 | same | 2 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/65ZbvtBo9vQduVyrcHkFZbBqERirZcakaRsaNh43EitZDAmW8QoaTx2iNMiH2Ec5vHXHKd3CDTSDt3ZXN9KeEj5a) [dump](https://solscan.io/tx/2nWvi9FSFAnrzeg2SWUPnan5444uLtB5MiDoCZUsrWnayrcd6UGriYRSbzXtvgR2YBDqK2hVW27PT4khVithYRrU) |
| 19 | 23 | same | 1 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.2 s | 1 | [buy](https://solscan.io/tx/2H57Zng6e2TSpfmBC5nPQeeWrVJMbbpTksSbFADM8dztAJRe6qf6WJr6QfFTeqeFVkRg6SFRJ6zp1NuJ6zsy7Tz9) [sell](https://solscan.io/tx/5VfGj1sQRhxSGSCPXqNpihWLGx4c1RZWF7mdj76N9gSxAmsL1PRZW52rj8Pwd34cT9EJuZa6g3MfkM15ksrn1vEt) [dump](https://solscan.io/tx/4gwYBZo2RXycq33QNovadpDgNNU56Sav5ciCzQCBxmkAFw63ibybG43PezJBPxmqgXd7GUZ9uSgyY7bb85X4Y1yP) |
| 20 | 14 | same | 3 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/4B9oVEAEoNEvp2kJkbHet4myWhJfxwfwdXjpSLyeydb42YwTVDGHSAG7MSpV8LcprZcfEbewNfgU8EehozUWtCVz) [dump](https://solscan.io/tx/5FPQV5qVepNXShqigVUj7PJ522MiAbu4v9bfjxp6TYy4suJmqNMiaETjfg5ndV5pXt6E1aZaM7tndMwz1kde8oz5) |
| 21 | 30 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/2famPiDrSQ7D2QtEpyKerXgRLaNZ2RE9FtQDUjkKLsTKvQMZL9cv4EeXkqpcBZGE7eNfhaLumvG6ffbX9FNAid71) [sell](https://solscan.io/tx/eHbRXY8oFqeBmhPbZ3jsfb2Dg76z7QsRRajiWQAqV31BhAEJu9zwpGdMZ9Y9ZwtDU9QPcYosLHhyxzCRRCSU8LF) [dump](https://solscan.io/tx/3xeep3w7PK8QQAqDU8EMrYVTYzRVQ2K8gtiDzg19r7DT8CRTiUYGzbS83qLDoeZSNMWDtqVEEGxMaFqc2KWtS1Hn) |
| 22 | 135 | +1 | 5 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/3YfurCotb9kfWkWAHy2dZgMvqZgxAhTtkC17r7fKqY1EPfBgbpy6B6qEXRUNayiXbWkunHhPBkdbn4S7eK1FEV6F) [sell](https://solscan.io/tx/aVjV7c3QvEx75oxstwsJT5zhG8n9WTDFCmePZ5CExRDTCKxs3iS536neXC7qc7REkqrB2KxMZJmrSbsohVpuZkv) [dump](https://solscan.io/tx/4rE7M1mSjy6AjK22VHfehmqoAp73usG4fcvfnEAJHvSr9LDM8uayLiEH79uAZgnP3qsmiLa6hF8w33kFwx6g5hg) |
| 23 | 89 | +1 | 4 | **falcon+falcon-udp** of falcon-udp+landx-fra3+glaive+falcon+helius-swqos+0slot+nozomi | – | – | [buy](https://solscan.io/tx/5P1fVx2kgf8H82pabXXXYtiwSYyBXEpspVbjVbJDHRWCLF1FamWYg6i54eWCDYPorf6ZWMc5MmP9bX93eD3QAiWV) [dump](https://solscan.io/tx/2eyLHwPeYNo1FhWxXnpByxpTVyMMdJzyzeho3WaLjTYo4B55vnPAAWyfpcgJUMbZ91odm61qg28TxQscwRoyWk6P) |
| 24 | 54 | +1 | 6 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/nAHy9gcvS56bLLBP59dwVoM1A9MvPgrdHiriXFSgeHu8nr4qkemNJfjvifYJS2X6hCmj95eekmDVRRkVD4ta6PU) [dump](https://solscan.io/tx/2vnDivqy5vP2d7UDaqxkEnLKw2URk3cExggkNHkCxEBfrnA4qyKB5fMHNobq4tPJkzmjAdRjmegnFVbs3tFMfiMB) |
| 25 | 43 | same | 2 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/aC9Nw8gsc6C9YXghzgZdHaarFqvPCwDXb7qpaA3ndmBeANa1r6zbrCi9GZQsjVywt3NnbJxJBDhYfA7mTuaNTcX) [dump](https://solscan.io/tx/4jy3xhdu8x5Bkmo4FXZAFmuS3bTWXqrUPbFDxPsyTgKLF1ys1nRg8WMDX3KJDWHhnsXXjDDqGpADt6MuUBmPiUqG) |
| 26 | 20 | same | 0 | **landx-fra3** of landx-fra3+falcon-udp+0slot+nozomi+staked-rpc+glaive+falcon+helius-swqos | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/e8YonaqaPLaSQcLS9gf6MoDGswijgHYDKGPR9PpJsohaL1zGhHdXwStWtQuCq8KcMMsZj1LWyzxsGHwUgQCWiwk) [sell](https://solscan.io/tx/3SpyMoQS7m17GEcfcEbEyUwpxjX8ctPzvumN4n9UFPqg58DAvqujpoTaauUjfRkc5aV1rj1zqGzs2X9egC8XDgU9) [dump](https://solscan.io/tx/4u6kwnJiszCQg6aqewUChTQaWBTRxFWJnKaUaqscuBZaXUhA69PLhXMCRmzcstMYCyBJzZRBNZnirhmrnFm6fzhv) |
| 27 | 66 | same | 4 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2rRS1ULxaAGCyspchzctVpb6YDwBCmkMMuSsaShAF7cKt8vQYKA6msNLUVy4b2SdWpxvVco2eXVqNqn7ATjAdcH6) [dump](https://solscan.io/tx/2qfQ8Cs44uBmYtHv2eKBmXHVM1GeW51xgtLDg1Qskh9Wisgo8yRfGtnW78sALXGkkGbkqpVcwYTeMoSsvJSgECjV) |
| 28 | 26 | same | 7 | **solami** of falcon-udp+landx-fra3+nozomi+helius-swqos+bolt+falcon+0slot+glaive | – | – | [buy](https://solscan.io/tx/QAH7dZE4Hu5uMwgR59FzLa6CfMpswwKnWV7pZrNyYDyqJ2nyQys1qqzMEPDL6MRFzS8Mw5PryaTCz4rp9u4hpJh) [dump](https://solscan.io/tx/3RMXG4StHHwRbGt1mLj5FQbN6b9qHXvP7Ak4FDzErn32GEC8tb7esfFazb9emTHYuhRUMbmmAwghCfLR8Z8VZ7aQ) |
| 29 | 119 | +1 | 4 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/LUjAn2bEAvxCmqkjR8KpSrCTt9JGgGNueqisVZkMNwESvy1YX4rpVjKFDn35A7Y8kZRJBiQKHGFtT3p7uvQqN13) [dump](https://solscan.io/tx/5wyXScnAboCe7jAvQt4cRLNCxoSUbxMTUs5Ds1tgXWUUZCUMLz4K7aqMLLUJjsL3JBMuTuwdDfefgxdfELAFHbgf) |
| 30 | 217 | +1 | 1 | **0slot** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4hAov4UQC7y5qw4RmsMsEEW25M8Kac9bQa4n2M8Cn7q1eNPSMzKkP87BD3uwyvB1avP328YhYdEL3mVud9Q7wmRr) [dump](https://solscan.io/tx/4LKjzzAY79h6DP1QTdBDPQd6MtireqbrjwbHqFxKFSTHXjYuQ59RZzs3AuQctAxytXUScDUFobRMgYtidrcR7p96) |
| 31 | 192 | +1 | 7 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2yDAhn3qQ739A1pJMk7cTYT81eHwYpHGSpouSE3Pe1hwgW41vQmhHUwsgEFMm6XqGUPmTrdabGUCX4Mx2JLfWaSk) [dump](https://solscan.io/tx/54sUSqmLkYHdZHMvAVtpsQCkAn2C4QoGZy6BaaYaUWv4QY4h66iwqudYvBZ3mYDsHDcDQEoEPYzkc8VU6sPaNtfa) |
| 32 | 45 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/gTVuBqwCKENa8nNJeu5Lo8yCMiTHpgJUmFtuEdma1eAEdXA6JyhExQwWdtXdjVwXK8jKEXpxC9dL3DPMebT22xk) [dump](https://solscan.io/tx/2GidTqqpgbxkuGZx59Zy9YgrUjUw9b4Ciq9u1UZjZS2HP17Ea8bZ2xopMpzdmsY8GjXsJHgii96B9aMEzL4oB6pZ) |
| 33 | 111 | +1 | 4 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/5kfhWNncVaS8Yjd5QmcTTSf1mtr6QTzmiSUqYVMF9Z67Qbw5rZkUqRJBUfAs8EroyTZd3YYHkMgfvEGuYrHK41Mn) [dump](https://solscan.io/tx/2g8vnWpjtzHYJFRvHPyoEVv9QUfse5VWuKCihyDkJtfckVuhRH4iYhGWVN31VdnybNoHxZVg6vnFrTaQaZUWdMwo) |
| 34 | 30 | same | 3 | **solami** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/4PiSX1VhNRhY5RS1jh3r9jq5Q7cU6nZhGNkJgzxhc7zcx1Q1Ebapidx1PkV1rMv3x4aFy5wh3PAv2VkW1y6UNJjB) [dump](https://solscan.io/tx/5rR2vpgv3xRUSBY4C5vwuAfdcLizBFLBzNwasFBfGVEoTn6uhetZK453cuyvixHJsEoCGTonxmo27gACSJJE8mok) |
| 35 | 36 | same | 4 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2WfCpNWddCg5EXnoDY3j39uMAcAxRGW9izfUCF9vLKz4TiECkn9uvh8dEKqYqf2kpbuTUYcZvEEDyMjS8VFxtF7J) [dump](https://solscan.io/tx/4wKmuhVY7xutmYki72NFvkQcYZiQwTuc7mK4J7XiYzBux9YDC3RTXffnPxRpzuXEqs4BADkFYCx4UQJ6LpZzFJjW) |
| 36 | 39 | same | 7 | **0slot** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/49gcLqPxUgxfYaT86r51XmkRkbYHbbFGFZP95gLG49245M9rNC9yUE1vLt4Er9MaBaEjWcFYSy1pYm6NJGnjf4HH) [dump](https://solscan.io/tx/3J8iJmiaTGFtE9wmQiNFMzoFHX63ZsBcMSxwcY8Y1cZ2BbNbsJhgXpqHrA2WjvNFFxVwzz3V5yi6HPnnpSJQJmnm) |
| 37 | 147 | +1 | 3 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2Pogp8hZM3Mnur4ZttWamvCbiL9N1FfRFqUNJnZWTUiReeUNXa7qmMkiUFQ5hC3kDPDdUwpikEEiRVmcfAJvvqfy) [dump](https://solscan.io/tx/5RLNet2q5Z2VYjTdn65Cb3FhFVPrUUqsHF9DADTvQ4PCBWy3n8bUbAmmRTZ4czH5tMehRgYgPefeq1aeNzxXPwmE) |
| 38 | 133 | +1 | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/3u48JiFsdg7bUHbmvfCDvQv1GSd3NVeVKjeaqcyRzaVKkW8vPkJBaZHHVhMoaRmummrNjcGXAwNDNZJVz95TFLoc) [sell](https://solscan.io/tx/4kPmgXATHiGHugwY3oBgKb3F4om3swcBXRR4HFAxTG85x8tASc5hbaBy87ifFdLo5K5TXfRsU5RY9THpvM3BTryA) [dump](https://solscan.io/tx/2H87DWuf9QLD3CBT6Jwa3J3BT2qrkPLdrVETEppRaqWvkVeiCrrGzUoGAcStFSXpkvCTeyyoCWCyYpPpGMArWNZV) |
| 39 | 18 | same | 0 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.2 s | 1 | [buy](https://solscan.io/tx/3RD2V7kHTtpwxigSKGzTi36nipaPqbfoGHmVhTQkrpXCvMqATSuxm7Fb96cNRLujZToNT85xSUHNkspThCAPAPbF) [sell](https://solscan.io/tx/2j6QRH8ndeTo7eysr9QqQKGbujxaJcDNm5xPuLgE2ecjPi2j83pPkqbttZvSBWK9PHBqgMgkgLx1jP9sGz48BUev) [dump](https://solscan.io/tx/rUUsnxtKcgdrNXJTseDKdqzzTq48JrTjXTuQRTEz165VoSBLQ31gM1U7DdEubGLn57cEM1B9tJHdoQDD6Rmwgzo) |
| 40 | 37 | same | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/i3dARyWd7NUP5NnJ3UTBBSvB41XVFFdj9ySF5vkbriqeTWwfCRrkTN4B81JouHRP7cbt6mfcGTLCCmXPJUPw5eY) [sell](https://solscan.io/tx/GWUgcyB7dtVd5zDUUsmdh7N5JAsWo2arZjrrQBQDDeg9EMUtantdJXcRxsPFBifc6Vdn3Fv2wA4Qvnmaj3dcntn) [dump](https://solscan.io/tx/5YuJNjwBTvn5J9zU7JfberbC4DCJ9t3SEWhTckFuhBsdLCBCxpo4B3CRAwhYfhfybUaULqyVdf5cAcY7ZvBcfedL) |
| 41 | 35 | same | 1 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/2KKf9uxQRTSmTBffAJSME7w7K79jaxqyuoE6nBrR41Q4HHKPHzqkhag9TifyHTDEdG7q8CAjeQLuexBGcsNX2mb1) [sell](https://solscan.io/tx/PTvi27wTt76sqm8RphEKuWkk7BTEHgLBwkCXzjXy9PWrsATTQkCjdHwTrUXYKBgoEyLKey6C7S8NDGdCEsNQBWX) [dump](https://solscan.io/tx/46zKGpmuqy3fKZ3uBTJ5enyHo85W99sAZkRM2YqKJShjzvMQqXNBK21YZPPD9phwyLyDjNMVKHSvGDKzDhvBFZaU) |
| 42 | 36 | same | 3 | **solami** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/4uBsV71vCf8UpmNzBqTsMXABYCMNyLXesrtsVe2JBzfy7DhVTGqrLaA25YQWqgYGEw3RyM8kNJvWcw3nKPAtPXYE) [dump](https://solscan.io/tx/53kVpV8gkiTKizhrMdLwnnTKK2GHHhJS4XttHeS4UYsvNvaHpYPkjB7jxUiAM2Sy3NT4F6ZqrDJorkmDw9S2jp1i) |
| 43 | 43 | same | 2 | **solami** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/5YsNSSr3wXKchbL5XS7fu7Dpb4XtaxAyQjZoi3APBBAM9yJbKExd6LFRk1enV4PGLmG1D1dB49omHrDit1Gcv8HQ) [dump](https://solscan.io/tx/rDiW8FSy5NeAKpxxSxVfu64LyuSsEsuNnFF329HF6pUxK5mEjeYGRrHpZRWQqX4ckNbwxhfaFkvPPPQstAkNDmA) |
| 44 | 12 | same | 1 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5bhVinxVYrig8Xii5Z9TTiofJx9RwoYCJngacjV3xH1arpQxU5YvNh6HxDneKLscKz4Ga92S4S1mZLgTm3Tg8eVv) [sell](https://solscan.io/tx/PU8L8iCFiCBjFdRBDFPBGhAbkNWP5ZkCkMVSdjy9vZBNurBCB58McycK3PdD4x6f9EBQ45ReRhbhqPpf54y71pD) [dump](https://solscan.io/tx/3fdhnuy7ey3ZZpxpmnY3S1HjETG2zz3UA9317eve1vb38ScM96mjCBspibnQEZbDN6bBVJrgCxpgnvXW7akPUTxu) |
| 45 | 41 | +1 | 3 | **helius-swqos** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/3oWiWrPZurz2LA9c9deWFJFBNXxw3gqUmLtARx6yhSZuResLxxu8AysP5FhekzxhfV92THcnnaFjAYpoa1yvwTrE) [dump](https://solscan.io/tx/4nDfHtSphCuAxLDXqwyXcgAGSmMgGeNfwZWTHNY6ufRkzezR2hYTw1vW7Ys9XC4HiChVSe8GCoy3y6NL89ihjfLp) |
| 46 | 134 | same | 3 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/2tPGDse6eqNgn6JuLchtgZL8kqyRpACeiv3XwwvbysV9jP43A5X2QYP61RWyi4ePk44bU1eTo66QqVP7EorB4qes) [dump](https://solscan.io/tx/C4KbwUwbiRYbhdTh3JZce14uMfb4y6UBLNdJd1tjUTGS4U2CzVroj4L94kvTpq4Tx5tVCf9hwEKUJCBJ3LzxLna) |
| 47 | 38 | same | 1 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/5Xn3YuCuBjtgjuHBHPxjzw4ARWi8o1fxKHvsQo6k9N5zCBzp2uFPgDQjZaxozFEWscWrvfta4p33oA8uzrhtzJ4e) [dump](https://solscan.io/tx/BiCnpdE58CynRmnvuCb2ocqHYZC4VQtYi3XF4JVqTWD9hNAtZBzvvedA4VXNQHaSLTay59BcSkQdbBgPXV6HjnV) |
| 48 | 47 | same | 2 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/2QoB6ijaYUP1E7ybfEHmWXYXZaXN3DyHGsKxMgoFtLFuxwFB5DrBUoGuzHJXwKq3oucnRsd6r2dLL779UXrytDFL) [dump](https://solscan.io/tx/3K3nxAXMFwBCHuyY7bP7FWA9sXSEXRG6QCQpBfRUKfiAhscJpZQpM3D9q2eVvo8oTQBcykVXqEA4mCbxaVzYM1kN) |
| 49 | 116 | +1 | 4 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/2J8MuLtGznPeaVaCDmekBZVaMJiZ926Dxyxi25Hi4JECzpsYj1KscFwbjz5jCsQZJRjVPT4hHvcAue4L9ovJ7e1m) [dump](https://solscan.io/tx/2Co5WBQ9Qh5ecsAhosFc3sUBmZVLZzeJ1MrDSJoaV67pPs62yjVrUpZRRvRaKQNjz7gKpYdNJ6k9qQH1jBMQHiZN) |
| 50 | 409 | +2 | 3 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2mVJa4uYaG8ApJNUhubbGe7sVKvnNVfhCzHuhd9n5MfenYcBsy1nyxrcRKMe3rpJokQh1d39g6xPQfq2fkppNqgU) [dump](https://solscan.io/tx/4vVtjVV39pHr5VXrUX5K5GDEdo8Aeumv4qjBfH4rbEU3foVHGFdWFGTUWkUYf2ytauKF5Gq4edXhEp1LCSoFHkma) |
| 51 | 26 | same | 3 | **0slot** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/Kpz43gxWBMMPYcNzLZYNWtEwU8LM1yXRrv5gsd77ah36rUYkmc7ujAz6YYfiiQXMCsbQNLCnNiMH8isVzABVmP4) [dump](https://solscan.io/tx/2VkN6pBVDMQ7fWe2KmneCbkihau6SGrbueYZLkaFKGtGoVbYKWeyxnv8uzEa95QgxX8SgMAix3DJ16FJ9yFR56eM) |
| 52 | 36 | same | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/5KpCsN7RT6X5gcp2PeFoSX2b5k5JkqtntHjpwsj7SgVy4VVN3CsxNJtwjZmm6PmdJsvEbBZroonhhpYnZwf25K7w) [sell](https://solscan.io/tx/5Rxh6HwtSK7FhuzjkxmDqFnZvkEXSMyL7ToQRuEG8d8ZshCBwDJbWsyrQEM3PGcvBWyvwQRuhMnRUEfaXHuSSrPn) [dump](https://solscan.io/tx/5nYL2cFKxnmez7YxJNyS1rvX2aGnmkGQWcF9JkTCThKcc958Wqcwk1ifdQ6DgoqR8ARmmwLHLUvDWWZknp4Lzo2R) |
| 53 | 37 | same | 3 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.2 s | 1 | [buy](https://solscan.io/tx/2B1FE2TvPUCWgYNQcRCcca5rpX8gyUwmEYe68ozuhKMef56DCbMXhrK7HJbTMEwHyNnyAcyBX85z1yWWM5jFAYEn) [sell](https://solscan.io/tx/3wDnr3dt7HQviESh8TSgQaNgu1MnrapG6u5uZDSgPX1v7rPJypupbajTvvw3tw56T2wkWxfykUcaFmzgazyHtERA) [dump](https://solscan.io/tx/3d54xdAozb2rDc9AZaZ6U5CJrxvoM8QSSpjmJ8AG4QLtsC9ew8Sh536GASpvWemwR4CAhHGFhdkfSuaZV7p6fyqi) |
| 54 | 26 | same | 3 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt | – | – | [buy](https://solscan.io/tx/2bYFvVq6wrsBvms2LGCabUxnTL8bcRXThtTxCFk1jehhgeRihs1pfLYuwyDFe83jxrABJAZzVweoSXD5YSXiaqJp) [dump](https://solscan.io/tx/4wCG6ULHLVxAHZRjK4STV9aNz7KY9FetsRP3swAZA9HUWfCgXsD4R1B91Y312fQLALRFUzLpfgbk65zerfviFcdD) |
| 55 | 112 | same | 2 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/3ZRJff1mR7xumg8F3w8QNSTbDBWTbu23enrok4tsgbvKVQc7a7YcGaEsnMDt5eqtpmerjQ67MzifcGqAJFt5xPAn) [dump](https://solscan.io/tx/3Juu8GVT4io5SE8N2bxbh2oQ6uQ9e3bCJfDUT8TQouy4rK4AojTVhbFWRHESv9w24ezGtAZYonBiMxuwc2pwyy9M) |
| 56 | 162 | +1 | 4 | **landx-fra3** of falcon-udp+landx-fra3+glaive+falcon+helius-swqos+0slot+nozomi | – | – | [buy](https://solscan.io/tx/3vLMb17Qn4ErVnCoJBdPX9eRajSGV4iYW3ZJG6mkhuZbcnHEfHTGsZiBVqXdUFWuurVGvjoag5s5W2wSg84uTCEP) [dump](https://solscan.io/tx/5q9NpyqGVmkB8hC6CNjKQcVu8pDp8TGEsM7hqFb5PgFJqeAMT1SLSEcWpCxhyLy3ypoMcKEeHmTVAKjUXoZvFY3z) |
| 57 | 151 | +1 | 1 | **glaive** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4333eo4RHAgnz9rCDuHf5fBs5oDjEyDzRvTnummqqvyubb5cvgRPadUqUL7CxuNXnkfWUtErkWmTWXSMp1mSoKfZ) [dump](https://solscan.io/tx/5Y9i8Sybc7VY5dpUPDTUrUJ4K8Rt6Lj4gGwV3dEMDM8CabSXj6BctTchfUiFvb83xgSR4aNBAJhsBH9keTkb6pou) |
| 58 | 17 | same | 2 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/3aDymZ7PGS37ra7QVQR3YiUJzM5eEKMtb2FoHGojUgF1E5EVMMrBRGbd7RozmChxQKRzYqDoKaSYYCupC4TacE1j) [dump](https://solscan.io/tx/5i5D6ZDNqqPkMUF6fDzJb4gXorAK1KvnQsqeyvyvwqtWhk2KJ4dkppDzcQ2iFc9KLWR3z55T6RXvqr5mAbuaendw) |
| 59 | 37 | same | 5 | **soyas** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/4yM9rQrpaBvFt8SMU8Gx5b1BHaBGaKt7335ypUJ6NA9SH1AxfAQ4Lp6NkjwBvP92XUr1Hi3Q2RdDNFfC9TqkN6J8) [dump](https://solscan.io/tx/3Lu3NJg7ic7qEcajw5Mcxv1YkaXnLXXZvmDUfHNKHnFY1LtUipxE5csax5LQ2pPiVb6t7pEHDsszRUyQ5wNfs58E) |
| 60 | 187 | +1 | 8 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3K8tssnpYnvbg17kDhkN4VVoXDvEywcwfbYJxmyUWPBNy3XYumWwvTpAt7tcrVoMbEjAgXA8Svukre5QTwS6qhLn) [dump](https://solscan.io/tx/3QCQJi4q43AmwPMTRECxK23HGXc3qC3TFQqRavDCteDaRntKjZjNv2KuPva3tjxEQPpDEnYrooeYh7FxxpyyuEZR) |
| 61 | 140 | same | 4 | **nozomi** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt | – | – | [buy](https://solscan.io/tx/5spaUq7VmmYkP3wsfbuQ4gfqV959hRMhPbqST7aJLSPGHMRAEnP87uavaTftv3uQ7mcJKgPCq8o8Lfs9PBsgQKto) [dump](https://solscan.io/tx/5frB3pVoUqzkFKVdvQLcgE9bNeNhT2ccY8i8gMC7UYwKWpGuDd3txCWotNCkTPE5kCJfVGmTNd4xCyLBZt1gVozL) |
| 62 | 26 | same | 4 | **solami** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/3sLRWqF4PcNEspCHSmGKcpe4NL7MBxSDpfFtVmnkM4MGaWPWZqTvTvByqz86kSjnBiJFrM5KLcPyEtvhzw2n5f8J) [dump](https://solscan.io/tx/ctwqKvj4WDgV8KJcoZgkmtnHkWhiAfB4jgbX8rs747bCspyJZWxUqfn3ednKWAVjz7Fr58SyrGL2Gxqby423BBP) |
| 63 | 133 | +1 | 1 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/3pTbEjDNpQ79SRGTCWKR2X6JSGC8jo65FDrEvcmiGuAFBBWSKkHQ888gianMZMi7E4gPMnvUHsLFmnJK2SsnQ8H2) [dump](https://solscan.io/tx/2X8Q2vCr66N1sGSSZbVhBaWYGdgrLHaBj1drQZpmiureYdpdLyGaKfQYsFwAbHcJaNbN9DkXdm43nzwwZMJLniZq) |
| 64 | 20 | same | 2 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/38a4K7z266jLxGh27q26EiXBxuj2oLem3TiH77jBNQSXZZo4EJv91FjUDE6xRuCQfPrCAsN9S5RaA5TZGBPogAmD) [dump](https://solscan.io/tx/3zhWEPPHU4hNSZrSCrGWpoDn7txvyLZH657aAULZNnGbfMdZvGrozZukCyVcyDUuHmMLDaRCZyxCueTXawYGAWnB) |
| 65 | 21 | same | 2 | **0slot** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/57PyvPNLW29y3UPDzsYXC83BH72RvVUQGV87c18SXU9LWrY9FCUTCiXiFQRMLnFETRiep8wbuyKJ8qjWTfFFYYb7) [dump](https://solscan.io/tx/45HB2ZcThein925x2qvibJcoFTciJqgFE8wKbhkmMqwGv89kfFHgUu2bdMBmaTGHVL28hxS7L8pK4iCgjbB7ipgB) |
| 66 | 14 | same | 6 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/5oZXc3fH3wmHQHTDdaVT6iskFMW7zjuYtmK51L8F9NCkeBijkGraeUK7ywQFaHDPXtUDkzDAdVhfnnYncPn69k6h) [dump](https://solscan.io/tx/2y92g8gjMgzg1DGabQeATQ2YMWSCMFwxwz5iyrtDJDTwFoTQh25gBQjGMBVLCD8iQ3p3txpeUtprs5SKcTUEREHV) |
| 67 | 145 | +1 | 6 | **0slot** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/5uJEzU1JzitB1JUQJp3XopiG4rWbUhUMr1ha7NUvDhpKrs8bdqzbmzmFzBQJATsDUGHCDzLh2aa6qFzQ4VNMZoy5) [dump](https://solscan.io/tx/2oRozR8UUCNPdPAhy7wyx3xiyU5fiGLJYJ2Rv7p7Kq6WYfZxYWbj2PK6U5j842DyuaTqtyPvzWfqmLxbYDtEcS4q) |
| 68 | 19 | same | 4 | **0slot** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/4c5e8C8rrsaA8NNY1syrKmqmTKQ57uRLzjKBDcxZBVVCL5krH7QzQSSarWJdUWbBTnAVwnq46L5LTvbbQWzU2dWj) [dump](https://solscan.io/tx/2fFno7Kz2q8Zsr7pVT2nJAdC25oU7QPtveAtzXAFJTYo3fhEGpqRmUcMRWViipBpNz2jLLyFqrizedLF6TaDjkvH) |
| 69 | 136 | +1 | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.9 s | 1 | [buy](https://solscan.io/tx/4vnjvt6LrNwAquvUL7KF3TAiMQ8J4YYgvUDqq72YkyvMGje9Jvns43wVTSjrWNYjms7hHnRZzrnYrDHHYbAyuno7) [sell](https://solscan.io/tx/22zNw8JrD9w6QxP9BiYJhdZBQ8y1ZK1mMtvC99jnCaBuBFq4LM5mFGxqRgopVnHBiwU6ttLBWuK8jo5qMDr33ade) [dump](https://solscan.io/tx/sQpWRdAGza7tRxLzg7JGZWFg54MLxdnmZLiLZKr8kQCHyJKPXbBe9BKe5qVpCmh8BAbyxLWvn8Stcsyo6q9tyGJ) |
| 70 | 24 | same | 3 | **bolt** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/4VpjR8y4rqpN9S1iAwx85ShvSBn6kjpRSSHSGqeSGXV5o5M8txo8yyGoDJ9jsNxmuufqxHZHiVPS4WwZPqKVviux) [dump](https://solscan.io/tx/5wD7XyrvJTA3uzAtfNvdcpCjX3NqH5bkZff3Y1J7Ba6Uxcgnox4UzjmskCVXopfD8AAnkCmeXZ5wDKdPmYPyCXJx) |
| 71 | 106 | same | 5 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3dmSszBhvzFZu4uVcUh8jomFpY5CbBoobLKGeSavngvNxEyGKV5SE2EAGQPVrLriFPKpMQFPZHE7yR7dNXCAExbc) [dump](https://solscan.io/tx/3KdF7FDEXMqwZzitSkuYr3UJ28Y7t5TiDhjwYVG2sEguCJYSa7eeVzruBobkTZscTEMdxKLszFupi5GM7CYP2hDA) |
| 72 | 45 | same | 2 | **glaive** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2ArSVg3HGFNEshiAoqWDgHomxu8iceSs4KJqjDdRUjeoRVbEt1sr32VUd6eHYS552kJX73dQaRazeZ9gvALrJvrd) [dump](https://solscan.io/tx/4rt8EXqgbcHstR2J17a3pRLrt2Sh2EYJexfnUqjmY3jfGzLy74cyBPRFFYsyiztWRik6ezbxbX1C6ft32j7D22UX) |
| 73 | 33 | same | 2 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/4pT8u7MipGD3Go9WLTe9sxRKT1KkUCdB13s4qQ3zBCMRaSVDXzHvFeZC1s9js8ae4yK4dv4mmiAgphjhAzWfLj9J) [dump](https://solscan.io/tx/3GxzA7h2fjMyTUB8WX982f4xK7fexy1NgDJwhvMbhsV3YmsrfoxpyQAmXQJcpvjWQmB4d2YFCJgoxXXKGGJhLuV9) |
| 74 | 89 | +1 | 2 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/3kaXS3CaCLPUs5SDoqc4pPFiemswjkUgUi6TbCs1AWAvDwVmwLxokQfP9TMWwLL7KrGmXBaqZxJyJuYG3NZdTHUW) [dump](https://solscan.io/tx/3syGXZm2Lb1Kax8UH6EZetzLoAn6urityG4hmQiTPJdQD6faBmuqsvJMH4T2NnbGqZKxCGRownvXLgUFxHqs2Loj) |
| 75 | 29 | same | 4 | **solami** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/4hDZWJeWRJdsx14ruxCztK6gn9v4wvmboeEMjvDw1f1e43vyRVHUprH59Zo3iLWNNgTJj3zKssxSeWziNot4G4Yq) [dump](https://solscan.io/tx/5CrU5DqQyCP8WJvvb4LkH1HhaBewL7URM2aZccyxbSWy3qW6s1DJ5eERnzzBtgaZJYiMSaXhU4FvzRNxmqborByg) |
| 76 | 40 | same | 3 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4conMg6fxaQq7iZ4SKRbA6etchBqhbWbXD6hNyhC6TxveajoqxncQx8XBEtepWb8sDnxwoDxkBBZAH5UYTXgJbBb) [dump](https://solscan.io/tx/4zFW2MLCX5MSRMBmtVTAXARxgS8M5G7zF3yrWxzLHPZwzaxkuEscGSxoz8TYofLj3io3HUhdSRrtZyiRA4RSiXW4) |
| 77 | 34 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2P1UkH2PYZedUwa7HeTjZrt7csH2tk5tBFYCTXR5VxEhMpB4CbGKwsuyyCi6nUquvc21mrK4okZVAPQj3tPbpTZk) [sell](https://solscan.io/tx/2TXz9kbFWVgjoW4e4BaG5sCweSxbPj9dQhkzXgsKtyPaR58Wm34Qne7XyE5L698zNJ5BW4gWkL7SKQNSZnrjnj85) [dump](https://solscan.io/tx/41GQqCEBJqqRmRAvQtw28TR6jEpbSZcBYvL2ii25YAVpDkhkMQcsJkmsbLwnnHCq8ieMSNrHTNvk4DbQ9spPCApi) |
| 78 | 20 | same | 0 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/3FecxipLDCM8rd1Hj9woveg9hjLw56oQ81rLoteddxPcQT4DEbcriUX9HjPQsPKKcQ4Pif32s1iJrFPvVYYFitsg) [sell](https://solscan.io/tx/43eHCbDLDQwPpDKQPFwENrgYBSZyC2DuP1KXWzkhBpcWfqiiu2ypdo3249ivdSwPHMTrbzxuxouN4v4qUQ7iCcg3) [dump](https://solscan.io/tx/Z5xiXo1wWxMqXRjtGhp79812cucGWm357sweS9JHzbXn6VEewyrYVQZFGMzz8iEVGJDnGXQvEbLXHaEXhPYeNoi) |
| 79 | 31 | same | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/4EQ3qBcbuybcKYBNTwB1XADR6NNVUiVDEpBGAw4MCpZqbBGa25qQtUggJeKvmy4RkYkSKAUDML8YkUyAY56JLfgo) [sell](https://solscan.io/tx/569WWKeyBanFuchjUXEnPkht6pjVaPj7ewcYXAmsELFJTMPo6zCVYypA6MenCSq2U4NZFowv7wVJehgYZZarpzzR) [dump](https://solscan.io/tx/5rf7Rh2yqWeH8ULgbCgJb7HS43TE6rdoUGPddJXt4KFLSgBPfcPF9uunqUXx1iXzxVd8gWwYJ1FD3raqVGaahA1L) |
| 80 | 31 | same | 3 | **solami** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/czsrvaRpPUgzmZqpKWBCPLpUVvKrhyF2Qpi7gmXoLLaCJg6WeKXqVq7vULgsDpgZeojpCSmHBSin8Apts64kwZg) [dump](https://solscan.io/tx/3fzJzmap514pkK8mSQxdsPRBQgtT9FZP41XuWMedfu7P7kN1K82bEgDSETDExM9ChYUWQSa7A5UYX9ZGKqw9HSb9) |
| 81 | 170 | +1 | 1 | **0slot** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot+glaive | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/4rqcC9TXmcpw1gQDqpPscEzMWnTT8qbg8EgdP5wcDJJZgNCHKjuGHSvUcDDhFJNFbz3hZR1Bf6nUi8Yk3A1J9vcT) [sell](https://solscan.io/tx/2AhXFdWJhQtvynwv3GwKi1opegyjqUvdZ22iZeJaudR4kVBdTK5atrxAorL4XZYRLt7UXUXq3YjkgaG7ZrfhJ2Wg) [dump](https://solscan.io/tx/pqTZNdyVV1CTZ2HX25gdqeb5ygXKXnLtFr8YKNSY6UiCEi5WndW1Kgiq5wfFoEEoNk644WcJwTHCwoVcmCr6rNm) |
| 82 | 40 | same | 0 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/4e7EWnDHPHYYD28NANCCz7vHAVHt2o9aaHNjVvAcAoEEudTo77gggacfjwtVpXZPQGmUx7XhXbvmUkhKovFxdGDY) [sell](https://solscan.io/tx/4bUSnV5CVWYmXDM2jp2MywUowhQifn5f8gD3qALSMxaaYa8mXR9rbVMCscwYdY5zhuaNUXk2ek4w3vu7Lidw2vX7) [dump](https://solscan.io/tx/2yJx4tWxCbsYR69heiuj1RLJo8QRNtG6tDpMubVU1G39bqn7oBDRYWrFRBapuigJKqns9cSmuWU6baQXxSfkmtyW) |
| 83 | 20 | same | 2 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt | – | – | [buy](https://solscan.io/tx/2KYPD41PiGBbX1KBFTRcKbZHYyWnbZHRrpmFD3VrKgnafLfeXB3JxXXJRM4hHg6ZcSc4eojCN5i8d2Y9Rk6SRqvN) [dump](https://solscan.io/tx/4DWWJGQFtgREVGJeZxipKUmGBWEA5ujCfVK1KDgp7a15Q8HfshRd1vgz12cvqSWgYm9xmbp35v1ZYLCYtYodBth1) |
| 84 | 22 | same | 0 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.2 s | 1 | [buy](https://solscan.io/tx/57k4XYh72uXhSwY73wzE6B2cLkxR8hggw9JrVDuMdUrYtcSttPmaWyMLkxC93TNYEjAbBGxwizNsUY7A1zLwCuGN) [sell](https://solscan.io/tx/2wyLv38DzqLqmXcDBMsHptdbtC7eXnx3PDFpihmK5B61JqwCgGmWjzbw4N8JeAkjv9nDxDuQcgRgcS7YoDLQXTQk) [dump](https://solscan.io/tx/vu8uEX9DwVpgLf1vu2Ji8BdAVGKcjTchuzNPgjepGx8jCH8WgRDar9BjeHQXTxoFpNFasxpW7LBkvX4Exr64N79) |
| 85 | 33 | same | 3 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/5mheKTTZkaVLcE6yyaBsBnoRWH9UNJyAtHpJUjE2SGgzq34WiAnG9W55mWu6PGt9ZnFieACRoe9Y99PwERiLJLQh) [dump](https://solscan.io/tx/31gVP6d2nNFQjGLNwESRCpQkLT3ubdf5599y14gss51NqjEAZWSsw7nWFBrU6h7bnxL31BrQNgcM3mrmRTk4sorK) |
| 86 | 39 | same | 7 | **bolt** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/4SK8EEe6f1Wv92FPm6F936cFeBwh2k58VxRFGm7aC3M8DfCEyjjDBjdR3emFUzVZhB7CH2viqjtDJqB2eAsZyiaA) [dump](https://solscan.io/tx/2LXrvBGLH7EBxCbFnUBxQGDsqjHCVPqsHSZ1ZeAPsjUkP9Z7MBt8uRP7sLgrDjzxY323Y8iT8FZABeoK1sPoWnA3) |
| 87 | 28 | same | 0 | **bolt** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/4vDn3iMaWGu96WbX8SLfYtFgvSBLEv51xQLSyUwa75M8wo5sArsZ6oZVdpNPanacguCZD1gMnpZXgpZN9TqwjhTK) [sell](https://solscan.io/tx/5Ay4J682mQepTxDBTcrGG4nVmqRX1LPeokobQuXod6niGByqgenwj2M8BkAnj2FxtLU9hH4Z1Pw6sdhWAKeXNRQk) [dump](https://solscan.io/tx/4zZb1NhuszyST5QJuYsmHCkp1VwDudLiDpRvzUViktSeprn8dQhWfT7EiZLSP66UtnfVLEkbRiqHfv5YHVEcnXR7) |
| 88 | 23 | same | 1 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/2aBeALL2BkTvVx8hehkpboiZVEKk55Z344dwhJXbyC9AL4ifnVRaxEAJTXMP4Rf7frga6rFaLRkgCh5a9491PrTG) [sell](https://solscan.io/tx/2AmUfNUxGm4g5RwWEqLtqzYx4t1aMhNGGuB3e6pSA2VW6DX2Pa1ZLmMsVDZF9hoprbp5m52UZ8RYdvo3UeULz35a) [dump](https://solscan.io/tx/EfF9FBRLaqsRBs965g889uSWPQoW1pt9WdfNpTeN5uyGWJBtRFpqyHeEYgVMCPmbkzefMWNWQgjdEQ8VBUZj1qv) |
| 89 | 36 | same | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/2V8SwM8JvPGTa8qyMShJQPcYuY9XNugUYLfknyhfS4qx78sbtzeEwxD6tLARD3K9CRettnuPAGfZ9U8WNExrqdru) [sell](https://solscan.io/tx/2K8NhjjfrN899DTz5X93pYRd9SQhUSe9nZJQSUABb7dMas3SJLNehEeV3NqmHyQnMj7FtjtVFREgSN3RiQkx8G6U) [dump](https://solscan.io/tx/53rTemZyHnG9NGTN1zwQXkjzEkG6pNKPQLMQ5uXP1AicoaDdxPbtsiao52hJNKTmj6L2NYMDyC2jfxB2u1MsXQGT) |
| 90 | 38 | same | 2 | **helius-swqos** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/2ozoMs8JawXBsEqjk6nTnWquaVvGRGHytukGmYZQK92EMuSXqBXyP3q3aG1dwRG9v3VWhE2c5rWfHHoLY2Kh9Kfi) [dump](https://solscan.io/tx/6sFi6mqkfLFAaY21P1hUfjK4dRdBVDF4P7bLJz7hPHZTaQ4hSNjLrFXQpB8RoXRxzWt9vBUncxqLpzUWLAawmit) |
| 91 | 41 | same | 1 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/23Ktr5A3CHUXkDmDtsez26ZHD92TN2Pgxx3XHs75rx3vpM2C2eSX7F5q8a1uS3ZpD1dZGWVndPTP8Fk8b65fVWZq) [sell](https://solscan.io/tx/bmMAMgZ7QCKRJe2iJZSiTQwg9qbcZoyzXVSwVMRGRvswuud3hDYQ6T9H57t1p8pyGbidNUtr6B9fsuxDn34qzNS) [dump](https://solscan.io/tx/XTGeL8bg3kkRti7k9HdLxkMm2wVXdc2NPxQC9T4p8k1xPzAKAmHzDc1imGZ1vFdvThqgNvbvbg2gU3chE3AGNtX) |
| 92 | 33 | same | 3 | **0slot** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4GGNG1XWzqbDH5UR9joCShwD1ksNHmS7LbuzzYJxcxQw6Xm1SHVDha5SxMhmjMxN32KhkzVbfvWG4ePr2Bm1D1Cr) [dump](https://solscan.io/tx/3xk5mMeev1iJwNdo4HmVwZKRiZXH4BpxSVUQNddW62xB9quqXkjLA5k2m72tUs9arrziatroFzmBU9Xx8hqkg7gK) |
| 93 | 22 | same | 5 | **soyas** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/4fNsnMyxy11F3BJvme6AqZbwWNLGhohkspcDkRryJrRBwAoRYDCYoEAGw7HWUZkN8j9D9gkqJyGPHfbvWLF74QTC) [dump](https://solscan.io/tx/2SDVWFWQDbkbe7Zj51BUpyCus4zwiGrixviNsvyuzTVjuAMSk1YUhvi4KyRRzomqZdpQS7KRv7iKWtUNpsgg5qps) |
| 94 | 19 | same | 4 | **soyas** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/2JW8YuA7AqP6fTpWpcXERNRbq2xLvzyaL4CU4quazWMzDVSNy9pNjLwYid8UQ37qRAYQbashAjERpLXJ48Es5QWM) [dump](https://solscan.io/tx/4EVws2NbZ22WtFiPYH6XEASL4dMNwL2J7K9qdWL5TaebpZ1DvVyzyoSBJ5seRF7i8phwvvRv7qXu6scDr4Z77mi1) |
| 95 | 41 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/uNi2dMPZhKqtsLsrQRhRPdR2HashQ3eds5rqhK2BxJpcPUwqybnbRBogYSyc525rSVrquKZunS8Af9gz1kQygzG) [sell](https://solscan.io/tx/4aeqWukHWj9X3sRkQhRmeJGTJukoA4sp2QP2fnYznxcsHvaKGDT3aF3vkJZD9frByodQdt24mTGyzS7BvMkvVWbn) [dump](https://solscan.io/tx/4fwtcMCBpkGUbDpdr3BtPtr2sCySawpFbGqwfsnGGtM6GESZgLc2Akg64FavDuPmyKaynP6QQGpALYK1x1d5o36s) |
| 96 | 131 | same | 2 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/4PtZJcgi2g3sYCc4Zfv9weqE55roRzrhHhNkYqDCq9atLVLJTn71iHFsE9pWqETXw1xE9Y1A2JsXhcpYX9y1tQNB) [dump](https://solscan.io/tx/4uzsDbE7CWVLXbnYYnTzBi3FGPzBrQLqfLbgcAmQh7dyB1u9H5DTscw9dqtEGTwTgTwu534uXWYYwVeBty8QeiF6) |
| 97 | 110 | +1 | 3 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/2Xek3AVpG2PH5H5eyny9heRVShTdo8cBkjTRb2HjDjUHdtv5JRHZsnUbie5aAEJeikfi691qQ6a39ZTpipZjV7B) [sell](https://solscan.io/tx/tAff1ScZK4eub9Y4nu5n2FfbyP2AA6q47u7cfdVKUqpYtH4HhS5cwJtabhMqFrEZtUnLywv69tYFpKQdHAxZbF4) [dump](https://solscan.io/tx/5d56ouFJih7wkGWPWjx2F78qAJvPGo8asgqs4htAWSVEZB3Pjz1ZApkzXnRRBm27JN6yH2NPyYEFyjtWcrjXQE8d) |
| 98 | 19 | same | 1 | **0slot** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/2kqpY1p9egcc1LercSvKXnzqij29e4ucmS3JJgraSo5jUdsbnZotdxDsnDChYgAupfZ6xwuTC947UeRgepRpYYH5) [dump](https://solscan.io/tx/524K6RN8TKeJqYFMvbxFXDZ65Ub5WTdSP7Vi2CpZ1QqyQCsphxfjoCw5sxRuREZw6dHuTL2seWHXTgk1m4MnYUQY) |
| 99 | 141 | +1 | 2 | **0slot** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3nCQA38Au8E3y3pJ3soUdY1BRKt55JuzwqJoBGmUPzzJEW47CPWp3wXzZnxWzckBayNic5t3tLr1oMwo7ydLKhJN) [dump](https://solscan.io/tx/29EWjGGe8gbwQcBcfmgVgo3N5cBGqf7rJk557YUseNW5BFi7migMUsoXxyPsAW7oVYjDJMNTstzYTKSVASnLi3FQ) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| BAM | 41 | 13 | 32% | -0.2104 | -0.0151 | 3/13 |
| Harmonic | 31 | 11 | 35% | +0.1331 | +0.0130 | 3/11 |
| Jito | 26 | 5 | 19% | -0.0090 | +0.0003 | 3/5 |
| Firedancer | 1 | 1 | 100% | -0.0150 | -0.0150 | 0/1 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 68 | 25 | 37% | +0.0604 | +0.0033 | 9/25 |
| dev list | 31 | 5 | 16% | -0.1616 | -0.0297 | 0/5 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 70 | 24 | 34% | -0.0315 | -0.0003 | 6/24 |
| next block | 28 | 6 | 21% | -0.0693 | -0.0097 | 3/6 |
| 2+ blocks | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 16:00 | 9 | 2 | 22% | -0.0965 | -0.0465 | 0/2 |
| 17:00 | 6 | 2 | 33% | -0.0139 | -0.0060 | 0/2 |
| 18:00 | 17 | 6 | 35% | -0.0634 | -0.0096 | 1/6 |
| 19:00 | 22 | 7 | 32% | +0.1857 | +0.0276 | 3/7 |
| 20:00 | 32 | 7 | 22% | -0.0335 | -0.0030 | 3/7 |
| 21:00 | 13 | 6 | 46% | -0.0798 | -0.0127 | 2/6 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 30 | -0.0664 | -0.0022 | 1.4 s |

## 8. P&L leaders
**Best trades:** 4fh6MR +0.2646 (Harmonic, time-limit, score 0.15); 98NafQ +0.0582 (BAM, time-limit, score -0.10); DM3K8n +0.0517 (BAM, time-limit, score -1.06)

**Worst trades:** HhcnPh -0.0874 (BAM, time-limit, score 0.61); EAfJMn -0.0612 (BAM, time-limit, score -0.81); 9xqERd -0.0523 (Harmonic, time-limit, score -2.04)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `A1vqhA2f` | HarmonicAgave | 1 | 1 | +0.2646 |
| `PUmpKiNn` | AgaveBam | 2 | 1 | +0.0512 |
| `HbidP4hp` | AgaveBam | 2 | 2 | +0.0454 |
| `BbCQMWnf` | HarmonicAgave | 2 | 1 | +0.0218 |
| `ACvL73V4` | JitoLabs | 3 | 1 | +0.0213 |
| `5pPRHnie` | JitoLabs | 5 | 1 | +0.0183 |
| `DrifTrN9` | HarmonicAgave | 2 | 1 | +0.0037 |
| `22rU5yUm` | AgaveBam | 1 | 1 | +0.0024 |
| `AHNX2YiD` | JitoLabs | 1 | 1 | +0.0018 |
| `STKEsvUS` | AgaveBam | 1 | 0 | -0.0005 |
| `vALigXFg` | AgaveBam | 1 | 0 | -0.0005 |
| `BCJN2vZF` | JitoLabs | 1 | 0 | -0.0005 |
| … |  |  |  |  |
| `AMukCLCr` | HarmonicAgave | 4 | 1 | -0.0197 |
| `EkvdKhUL` | HarmonicAgave | 2 | 1 | -0.0201 |
| `2oHUYyW2` | JitoLabs | 2 | 1 | -0.0202 |
| `2Df1aLCR` | JitoLabs | 2 | 1 | -0.0237 |
| `GoeW4aFK` | HarmonicAgave | 5 | 2 | -0.0250 |
| `LA1NEzry` | AgaveBam | 1 | 1 | -0.0324 |
| `2m1A2WM1` | HarmonicAgave | 7 | 3 | -0.0364 |
| `5tfcGyf3` | AgaveBam | 2 | 1 | -0.0390 |
| `6TkKqq15` | AgaveBam | 2 | 1 | -0.0461 |
| `HTeRsa3g` | HarmonicAgave | 5 | 1 | -0.0543 |
| `76rcGHdP` | AgaveBam | 1 | 1 | -0.0612 |
| `AWcCdYG7` | AgaveBam | 4 | 1 | -0.0889 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 2124 (p25 1540, p75 2656, n 99) |
| Executed-feed lag behind first sighting, ms | 0.7 (p25 0.4, p75 1.1, n 99) |
| Buy sent → our tx seen on the feed, ms | 33.0 (p25 20.1, p75 106.9, n 99) |
| Fills: our buy seen on the feed after the dump, ms | 33 (p25 22, p75 40, n 30) |
| Guard fails: our failed buy seen after the dump, ms | 40 (p25 26, p75 111, n 68) |
| Fills in the dump's own block | 24 of 30 |
| Guard fails in the dump's own block | 46 of 68 |

**Which copy landed (nonce fan-out):** nozomi 31, glaive 16, 0slot 15, falcon+falcon-udp 12, solami 11, landx-fra3 5, soyas 4, bolt 3, helius-swqos 2

**Send-path answers (FAST-ACK lines):** falcon 99 (median ack 0.7 ms), 0slot 99 (median ack 1.3 ms), nozomi 78 (median ack 0.8 ms), helius-swqos 68 (median ack 0.9 ms), glaive 62 (median ack 0.6 ms, 1×429), bolt 44 (median ack 0.7 ms), staked-rpc 1 (median ack 2.2 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 3 |
| Guard fails: rival SOL ahead (median) | 2.37 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 8yYMhuYo | 31 | 21 |
| 2KtcBC (pre-placed) | 16 | 15 |
| HLU8QbLd (41Pr family) | 10 | 10 |
| 5PuQCemC | 9 | 8 |
| 8wbJjSFz | 9 | 7 |
| CVPz447t (pre-placed) | 7 | 7 |
| 8PgC4ngp | 7 | 4 |
| 9DW4QLas* | 6 | 5 |
| 5Q2RjKr7 | 6 | 5 |
| 8SMLjVUz | 5 | 4 |
| haqq (dip bot) | 4 | 4 |
| 9mZeEDjX | 4 | 3 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.2940 |
| Pump fee on buys | 0.1296 (0.0043 per fill) |
| Pump fee on sells (residual) | 0.1333 (0.0044 per fill) |
| Buy tx fees (base + priority) | 0.0152 (0.00051 per fill) |
| Buy tips | 0.0282 (0.0009 per fill) |
| Sell tx fees | 0.0181 (0.00060 per fill) |
| Sell tips | 0.0360 (0.0012 per fill) |
| Failed buys (tx fees) | 0.0348 (69 buys) |
| **Result** | **-0.1013** |

Buy compute used (fills): median 80,566 CU, max 88,904 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 28 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getLatestBlockhash: 1 timeouts/transport errors (worst p99 291 ms)
- ⚠️ RPC bh-fallback getSlot: 1 timeouts/transport errors (worst p99 290 ms)
- ℹ️ send path glaive: 1 × HTTP 429 (rate limited) on buys
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)
- ⚠️ big loss HhcnPh -0.0874 (time-limit, BAM)
- ⚠️ 8ybS1D: landed 2 blocks after the dump
- ⚠️ big loss EAfJMn -0.0612 (time-limit, BAM)
- ⚠️ big loss 9xqERd -0.0523 (time-limit, Harmonic)
- ℹ️ One buy failed with 6001 at instruction 6 (8ybS1Dxj): the Lighthouse slot-deadline guard (inferred) — fee only.
- ℹ️ Nonces healthy (8 ready, 0 dead, 99 used, 0 fallbacks); every fill sold.

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
- none recorded

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r23.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r23.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:57 PKT.

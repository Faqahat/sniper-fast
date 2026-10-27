# Amsterdam run 22 — dip bot run report

*Live 12 h: M2 gate + routes v13 (adds 0slot, skips Rakurai) on dip19; 0.35 SOL; pre-send SHADOW only; near list near_leaders_ams.txt (disjoint from Frankfurt)*

> **Verdict:** +0.090 SOL on the wallet (1.8156 → 1.9052), matches the engine (fired 94, landed 44, realized +0.089643). 44 fills, 48% wins. BAM (−0.146) and Firedancer (−0.111) leaders lost; Harmonic (+0.174) and Jito (+0.172) won.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.0896 SOL** (wallet 1.8156 → 1.9052, Δ +0.0896) |
| Started (PKT) | 2026-10-26 03:56:27 |
| Ended (PKT) | 2026-10-26 16:08:38 — stopped with Ctrl+C (SIGINT) |
| Ran for | 12 h 12 min of 720 min planned |
| First / last buy (PKT) | 04:32:09 / 15:51:53 |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 94 → **44 filled**, 49 failed on the +5% guard, 1 failed (other) |
| Fill rate | 47% |
| Wins / losses (fills) | 21 / 23 (win rate 48%) |
| Per filled buy | avg +0.0026, median -0.0019 SOL |
| Fills only / failed buys only | +0.1149 / -0.0253 SOL |
| Best / worst trade | 47Me6d +0.0910 / 5rh8HB -0.0832 |
| Fill landing | median 38 ms after the dump (seen on our feed); 32 of 44 in the dump's own block |

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
| limits | max 500 fills, 1 open at a time, 720 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 21**:

| Setting | AMS run 21 | AMS run 22 |
|---|---|---|
| engine build | dip18 (QUIC lanes soyas / solami + falcon-udp) | dip19 |
| route: bam leaders | nozomi + helius-swqos + bolt + falcon + falcon-udp + soyas + solami | nozomi + helius-swqos + bolt + falcon + falcon-udp + soyas + solami + 0slot |
| route: fd leaders | nozomi + landx-fra3 + staked-rpc + soyas + solami | 0slot + nozomi + landx-fra3 + staked-rpc + soyas + solami |
| route: harmonic leaders | nozomi + landx-fra3 + falcon + falcon-udp + glaive + soyas + solami | nozomi + landx-fra3 + falcon + falcon-udp + glaive + soyas + solami + 0slot |
| route: jito leaders | solami + soyas + glaive + falcon + falcon-udp + helius-swqos | solami + soyas + glaive + falcon + falcon-udp + helius-swqos + 0slot |
| limits | max 60 fills, 1 open at a time, 60 min, loss cap 0.500 SOL | max 500 fills, 1 open at a time, 720 min, loss cap 0.500 SOL |

- Engine dip18 → dip19; routes v11 → v13 (0slot added, Rakurai leaders skipped).
- Limits 500 fills / 720 min (owner 10-26); pre-send shadow only (no --presend-live, owner rule after the 10-25 race).

## 4. Timeline (PKT)
- **03:56:27** engine start #1 (session with 0 buys)
- **03:58:56** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends
- **04:26:21** engine start #2 (session with 94 buys)
- **04:45:32** big loss: DvbaTz -0.0559 SOL (time-limit)
- **06:16:33** big win: FrMD4E +0.0628 SOL (time-limit)
- **08:14:28** big win: 3To5zz +0.0721 SOL (time-limit)
- **10:03:22** big win: 47Me6d +0.0910 SOL (time-limit)
- **10:56** no buys until 12:14: 31 picks skipped as far_leader + 4 spacing — the dumps were on Frankfurt-near leaders (disjoint lists by design), not a fault
- **12:41:38** big win: 63r5pz +0.0521 SOL (time-limit)
- **12:43:24** big loss: 5rh8HB -0.0832 SOL (time-limit)
- **16:08** owner stopped the run (Ctrl+C); run 23 started 16:11 with the same config
- **16:08:38** engine end #2: SIGINT: no new buys; open positions finish their exit, then the run ends

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 38809 |
| Inside the envelope (age / drop / since-buy / size) | 17569 |
| Picks (score above the threshold) | 509 |
| Skipped | far_leader 357, spacing 53, legacy_create 4, max_open 1 |
| Buys sent | 94 |
| Filled | 44 |
| Failed on the +5% guard | 49 |
| Failed (other) | 1 |
| Never landed | 0 |
| Sold (positions closed) | 44 of 44 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 04:32:09 | [2Tedws](https://gmgn.ai/sol/token/2TedwsZ1vossRRzPg8FjidxbCGoD9hZmJLLZ1dfsv6pZ) | 0.35 dev | 0.77 | 2.37 / −9% | 5.5 s | BAM `6TkKqq` | guard fail | -0.0005 |
| 2 | 04:33:18 | [8vJ1fQ](https://gmgn.ai/sol/token/8vJ1fQUTDjdj5t5QQWAcpvDze4bFQTr4FgyDmjLNpump) | 0.35 | -0.18 | 2.87 / −13% | 1.9 s | Jito `7Zm1pE` | guard fail | -0.0005 |
| 3 | 04:39:42 | [QkUDiq](https://gmgn.ai/sol/token/QkUDiqHsY4bkmFC3NB1mqmA2TKieVC4Vfo7UFmkpump) | 0.35 | 0.75 | 3.11 / −15% | 15.7 s | Harmonic `BbCQMW` | guard fail | -0.0005 |
| 4 | 04:44:43 | [JD3uju](https://gmgn.ai/sol/token/JD3ujuHF7A4NT85k7XgXzjwmETrS6ACidfuEy7hkpump) | 0.35 | -0.57 | 3.21 / −14% | 3.6 s | BAM `7tqeaF` | filled | **+0.0222** |
| 5 | 04:45:32 | [DvbaTz](https://gmgn.ai/sol/token/DvbaTzWmzYbLBX54fJyriV9BPre3hjPiuaVhLDCTpump) | 0.35 | -0.61 | 5.78 / −24% | 5.3 s | BAM `BUv44c` | filled | **-0.0559** |
| 6 | 04:52:05 | [D3cTeM](https://gmgn.ai/sol/token/D3cTeMg7SxoVf51F4tJMtvJ3nYyZx237G6GwVn5gwyPP) | 0.35 | 0.44 | 2.17 / −13% | 6.2 s | Harmonic `2m1A2W` | guard fail | -0.0005 |
| 7 | 04:56:07 | [7SGZBD](https://gmgn.ai/sol/token/7SGZBD1rQxCAZ9qyAZQGTDsp11wJP5MM2czUo6Stpump) | 0.35 | -2.81 | 1.14 / −7% | 14.4 s | Harmonic `Ex1AxF` | filled | **+0.0078** |
| 8 | 05:04:10 | [8topFj](https://gmgn.ai/sol/token/8topFjwyBA878mnbBW3PM6jZ2kzZYkgtthz7Rpkhpump) | 0.35 | -0.71 | 5.99 / −23% | 4.7 s | Jito `2Df1aL` | guard fail | -0.0005 |
| 9 | 05:17:33 | [B3ywC3](https://gmgn.ai/sol/token/B3ywC37dpkES3C9AHpvNBwbcsAKLMNfS8gLM8SXtpump) | 0.35 | 0.96 | 6.72 / −17% | 276.0 s | Firedancer `HW4zor` | guard fail | -0.0005 |
| 10 | 05:19:05 | [3ym1ar](https://gmgn.ai/sol/token/3ym1arweKBuozhUr5jdmjqDpn7pnJnVqAinaXJNppump) | 0.35 | 0.01 | 3.52 / −15% | 5.1 s | Harmonic `DrifTr` | guard fail | -0.0005 |
| 11 | 05:24:24 | [6oAvSL](https://gmgn.ai/sol/token/6oAvSLWzs8B1goT8bb9ZbYyfFnJi53d9AgrVuUwGpump) | 0.35 | -0.41 | 5.13 / −16% | 14.4 s | BAM `KAW1Lj` | guard fail | -0.0005 |
| 12 | 05:32:26 | [DdFeaG](https://gmgn.ai/sol/token/DdFeaGEyuYSQYmSpkpY9HJnLdR35bZ5Xvn7qeoLspump) | 0.35 | 0.97 | 4.57 / −16% | 136.5 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 13 | 05:34:47 | [aFyVUp](https://gmgn.ai/sol/token/aFyVUpFmZAepKzm1GhrYqgN9bW9X9U3Mk2Xs9jqpump) | 0.35 | 0.80 | 4.64 / −12% | 75.0 s | Harmonic `GoeW4a` | filled | **-0.0074** |
| 14 | 05:34:59 | [EYz4Z4](https://gmgn.ai/sol/token/EYz4Z4CN41WeAJrQFn1b1V1ReKsUT9WQQQS4kVSspump) | 0.35 | -0.77 | 5.53 / −15% | 12.1 s | BAM `5essVp` | filled | **+0.0135** |
| 15 | 05:36:53 | [ACMJtz](https://gmgn.ai/sol/token/ACMJtzDgvi5RMt4Lfv9HUERcwWNa6EAYNLebW9bkpump) | 0.35 | 0.32 | 4.50 / −23% | 30.5 s | Jito `7cVfgA` | guard fail | -0.0005 |
| 16 | 05:39:50 | [Bvc8Yx](https://gmgn.ai/sol/token/Bvc8YxQYP8sFGgmKzz8JUFJc5ihcmmqg3yo8xmfwpump) | 0.35 | 0.47 | 4.03 / −15% | 132.9 s | Firedancer `HW4zor` | filled | **-0.0133** |
| 17 | 05:55:40 | [6X4zWV](https://gmgn.ai/sol/token/6X4zWVbp8zoK1GhvRt9dEQPphYtcSdrwbMzAwjewpump) | 0.35 | -0.84 | 2.57 / −12% | 3.4 s | BAM `AWcCdY` | guard fail | -0.0005 |
| 18 | 05:56:09 | [DKH53z](https://gmgn.ai/sol/token/DKH53zTPYru9ifF3CzAW1qdVa6zoX7fthS3C2GNWfdog) | 0.35 | -0.70 | 4.99 / −11% | 135.9 s | BAM `Ninja1` | filled | **-0.0149** |
| 19 | 05:57:21 | [FsZffx](https://gmgn.ai/sol/token/FsZffx45BPdcTrLizSte8hDANn7d2CcxxhCpErZZV51V) | 0.35 | 0.60 | 2.02 / −12% | 6.8 s | BAM `Aw5wEM` | filled | **-0.0195** |
| 20 | 06:08:46 | [3MHnpY](https://gmgn.ai/sol/token/3MHnpYzAbLpK4Hd8cRdwASkzYJ783vktvXWpcXmQpump) | 0.35 | -0.53 | 2.47 / −9% | 5.1 s | Harmonic `XkCriy` | filled | **+0.0418** |
| 21 | 06:11:47 | [2bq7Za](https://gmgn.ai/sol/token/2bq7Zav5e6TparW9eB4QfMe8X5e2UKR9sSSiUj4dBc8F) | 0.35 dev | 0.61 | 3.29 / −14% | 17.4 s | Harmonic `A1vqhA` | filled | **+0.0357** |
| 22 | 06:14:46 | [DCfpY1](https://gmgn.ai/sol/token/DCfpY1v6wFkx32eeJvf4ZsiRRNn1rViu3z3GmuHHpump) | 0.35 | 0.10 | 4.03 / −15% | 289.6 s | BAM `6TkKqq` | filled | **+0.0045** |
| 23 | 06:15:15 | [3ogamo](https://gmgn.ai/sol/token/3ogamojce7NKLuL1JhsLZbMzYRQA1jiZxmCneXfopump) | 0.35 | -0.59 | 2.69 / −16% | 3.8 s | Jito `2oHUYy` | guard fail | -0.0005 |
| 24 | 06:16:33 | [FrMD4E](https://gmgn.ai/sol/token/FrMD4Edf16FtTXpzJHVbc9z51E3j6W6Uep66FXFypump) | 0.35 | -0.55 | 5.34 / −19% | 12.3 s | BAM `HbidP4` | filled | **+0.0628** |
| 25 | 06:22:12 | [91qT2m](https://gmgn.ai/sol/token/91qT2mv3nUY8MegW5xHGsioATJudsvKJNqqhSFSJpump) | 0.35 | 0.24 | 3.15 / −15% | 3.8 s | BAM `GSTamp` | guard fail | -0.0005 |
| 26 | 06:50:13 | [EdCaBG](https://gmgn.ai/sol/token/EdCaBGFeHTkASGDjggkqb5aRCdbTjUx5csnGdtD8pump) | 0.35 | 0.98 | 4.41 / −16% | 135.0 s | Harmonic `GoeW4a` | guard fail | -0.0005 |
| 27 | 06:52:09 | [9QQbFM](https://gmgn.ai/sol/token/9QQbFM1SGDLyesFiR7cnMoNSwSFB6s78sfe4DfyPe5Pr) | 0.35 dev | 0.43 | 4.97 / −26% | 3.6 s | BAM `bkpk9K` | guard fail | -0.0005 |
| 28 | 07:02:17 | [3SEJmP](https://gmgn.ai/sol/token/3SEJmPTrftsXvrbnwsacS3sQg4yWHd1s3N5amUAzpump) | 0.35 | 0.61 | 3.15 / −13% | 3.6 s | Harmonic `HTeRsa` | guard fail | -0.0005 |
| 29 | 07:04:27 | [Akv4MW](https://gmgn.ai/sol/token/Akv4MWyBPLh8VQBL6KAj5cjWdVYusfAwdx3fVUs4zHqK) | 0.35 dev | 0.38 | 3.87 / −14% | 21.2 s | Harmonic `DrifTr` | filled | **+0.0181** |
| 30 | 07:05:34 | [3vSpgb](https://gmgn.ai/sol/token/3vSpgbssRNTJH6AGYuouoPn9XV9sLgCM2vKXmGRvpump) | 0.35 | 0.36 | 3.86 / −15% | 6.8 s | BAM `Aw5wEM` | guard fail | -0.0005 |
| 31 | 07:06:20 | [3k44GE](https://gmgn.ai/sol/token/3k44GEL1BRGEWG1bYjYjVfM2a8eHSqPUnkdqDC7Fpump) | 0.35 | -2.01 | 3.11 / −8% | 14.0 s | BAM `7tqeaF` | filled | **-0.0027** |
| 32 | 07:07:34 | [A1JNkT](https://gmgn.ai/sol/token/A1JNkTWN3EtuBUEyXZxGSpKgM3zzCA6GYrWfmVoMpump) | 0.35 | -0.72 | 3.06 / −9% | 11.0 s | BAM `722RdW` | filled | **+0.0070** |
| 33 | 07:20:19 | [29vDxp](https://gmgn.ai/sol/token/29vDxpcMNFHYKG4JbtxuoS77BpPbwWcrtQJympMRpump) | 0.35 | -0.45 | 2.75 / −12% | 2.1 s | BAM `HbidP4` | guard fail | -0.0005 |
| 34 | 07:20:38 | [7rbbQ5](https://gmgn.ai/sol/token/7rbbQ5bZnbNhQGKvEfYyJnh55R7oa5256eQGj1AeLYUS) | 0.35 dev | 0.96 | 4.20 / −22% | 4.2 s | BAM `LA1NEz` | guard fail | -0.0005 |
| 35 | 07:21:33 | [EQpwLo](https://gmgn.ai/sol/token/EQpwLou8Thdz3goS9yv8g8nsCr7x6Ttsubc3WNtBpump) | 0.35 | -0.47 | 4.56 / −25% | 9.8 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 36 | 07:25:37 | [Du51gD](https://gmgn.ai/sol/token/Du51gD8243zw5ZAF7kfWQr9FR6kni9kq6v6XC21kpump) | 0.35 | 1.59 | 6.09 / −22% | 15.3 s | BAM `spcti6` | guard fail | -0.0005 |
| 37 | 07:30:48 | [9qyebE](https://gmgn.ai/sol/token/9qyebEMMmKow9Vh7Myr17NQXYJrvkVcbfB1oHrcppump) | 0.35 | -0.48 | 3.62 / −14% | 44.5 s | Harmonic `DrifTr` | guard fail | -0.0005 |
| 38 | 07:37:04 | [27Co72](https://gmgn.ai/sol/token/27Co72skaeEXToFVJDwGU4VQ9xjjNCMY21bfQvvipump) | 0.35 | -0.42 | 4.00 / −16% | 10.6 s | BAM `Aw5wEM` | guard fail | -0.0005 |
| 39 | 07:38:24 | [BZauEf](https://gmgn.ai/sol/token/BZauEfvf2483384MS6okHUA2fe7tbM5bFZaCnj5zpump) | 0.35 | 0.33 | 5.61 / −19% | 254.2 s | Firedancer `HW4zor` | filled | **-0.0314** |
| 40 | 07:47:10 | [8VNwni](https://gmgn.ai/sol/token/8VNwniM5TvB97JGmgWLV4sMvG5kCmmJUpRPbX3nupump) | 0.35 | -0.90 | 2.04 / −11% | 2.5 s | Jito `5pPRHn` | filled | **-0.0191** |
| 41 | 07:48:29 | [2DKung](https://gmgn.ai/sol/token/2DKungsVaeXSaWZon7mxtGj3qPzK7XL94YwRCKzUpump) | 0.35 | -0.42 | 2.27 / −10% | 2.3 s | Jito `DDnAqx` | filled | **-0.0152** |
| 42 | 07:51:58 | [6Q251B](https://gmgn.ai/sol/token/6Q251BLT1juWkvVXQLVamqKScohZj8HESBDpytTppump) | 0.35 | -0.30 | 4.07 / −22% | 1.7 s | BAM `GSTamp` | guard fail | -0.0005 |
| 43 | 07:52:47 | [Hijnr6](https://gmgn.ai/sol/token/Hijnr6oGqrLxnSq4GqidVfqa36PVKbW3jBhojC4Mpump) | 0.35 | -0.28 | 4.04 / −16% | 4.2 s | Harmonic `2m1A2W` | filled | **-0.0031** |
| 44 | 07:57:16 | [CLu1Sa](https://gmgn.ai/sol/token/CLu1SaqwBMLjGR6f8UhvYzpzutV9PNepLXUSSBJdpump) | 0.35 | 0.38 | 2.69 / −10% | 19.3 s | BAM `Aw5wEM` | guard fail | -0.0005 |
| 45 | 08:02:18 | [HWkvSF](https://gmgn.ai/sol/token/HWkvSFn77FoAeYCt3aswWf5i6swf81aoTjhjTGiopump) | 0.35 | 1.18 | 3.04 / −15% | 87.6 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 46 | 08:03:31 | [3F23CA](https://gmgn.ai/sol/token/3F23CAfmZ7ej7jmurW3sJLhsQaDrrWWEoriD21iDpump) | 0.35 | 0.65 | 3.33 / −15% | 6.6 s | BAM `22rU5y` | guard fail | -0.0005 |
| 47 | 08:05:49 | [3T6ngw](https://gmgn.ai/sol/token/3T6ngwJqaZBUn8HyU2MND3ndEphYkjoUusc4MruUpump) | 0.35 | -0.84 | 1.19 / −7% | 6.4 s | BAM `AWcCdY` | guard fail | -0.0005 |
| 48 | 08:09:07 | [BjfCpM](https://gmgn.ai/sol/token/BjfCpMX1Fjymi1HrQfMmGFQ7zzU3yX2Jo5NDLKzBnYzv) | 0.35 | 0.81 | 5.58 / −26% | 31.8 s | Harmonic `AMukCL` | failed | -0.0005 |
| 49 | 08:14:28 | [3To5zz](https://gmgn.ai/sol/token/3To5zzSr12zhVQkqLxHRyiN6pWoew6XWoELqRqc5pump) | 0.35 | 0.28 | 4.97 / −16% | 13.1 s | Harmonic `A1vqhA` | filled | **+0.0721** |
| 50 | 08:17:54 | [HvZqDS](https://gmgn.ai/sol/token/HvZqDSN6knAd4VcZuhuUJD1jitQHouDAtpc8VczYpump) | 0.35 | 1.10 | 5.57 / −22% | 8.1 s | Harmonic `2m1A2W` | guard fail | -0.0005 |
| 51 | 08:21:54 | [EThNKS](https://gmgn.ai/sol/token/EThNKS2jkp5xMCa97z36frMCBLJSaVQJ7cTRjrbRpump) | 0.35 | 0.11 | 4.10 / −13% | 1.1 s | Harmonic `2m1A2W` | filled | **-0.0281** |
| 52 | 08:41:46 | [3USzmn](https://gmgn.ai/sol/token/3USzmnm1jwrkysFJXdKuHDxmuwGFXLKjcbw39FYHpump) | 0.35 | 0.07 | 4.59 / −19% | 3.0 s | Jito `GnC339` | filled | **+0.0140** |
| 53 | 08:50:49 | [Fg7K4E](https://gmgn.ai/sol/token/Fg7K4EHVpxivzeFSDVakr9nwuTnWtAu8YnsrAUrKpump) | 0.35 | 0.11 | 3.08 / −14% | 3.4 s | Jito `5pPRHn` | filled | **+0.0280** |
| 54 | 08:50:53 | [2oVKBS](https://gmgn.ai/sol/token/2oVKBSDPVGEq4o1qju7UkWMfMPNtqqJMUgj7xbZJpump) | 0.35 | -0.92 | 2.49 / −12% | 2.1 s | Jito `ACvL73` | filled | **+0.0425** |
| 55 | 08:56:25 | [BXnLS8](https://gmgn.ai/sol/token/BXnLS8gsS1fNauqco3fgPz6vL5SLLdAg2vMArZLMpump) | 0.35 | -0.53 | 2.88 / −12% | 2.5 s | Harmonic `2m1A2W` | filled | **+0.0142** |
| 56 | 09:00:20 | [G3poHX](https://gmgn.ai/sol/token/G3poHXbBf6mBNrmDhpxn84dB68HTCvf1jc4Qenqxpump) | 0.35 | 0.73 | 3.22 / −16% | 24.4 s | Harmonic `DrifTr` | guard fail | -0.0005 |
| 57 | 09:08:22 | [3NvWgr](https://gmgn.ai/sol/token/3NvWgrT8swoLLHt26EpZsjXqJmB4HLj78HkKuTB1CX5T) | 0.35 | 0.27 | 3.29 / −14% | 15.7 s | Harmonic `GoeW4a` | filled | **+0.0177** |
| 58 | 09:09:19 | [FrdfbY](https://gmgn.ai/sol/token/FrdfbYr7A8Ur1mDTCUbuqfX3SbnYgSkghibikt8Epump) | 0.35 | 0.43 | 4.07 / −22% | 4.2 s | Harmonic `DrifTr` | filled | **-0.0096** |
| 59 | 09:21:40 | [FEfVpP](https://gmgn.ai/sol/token/FEfVpP9e4zVAMTTykdutNgd23DStjNSNKo781R1Dpump) | 0.35 | 0.23 | 4.00 / −14% | 12.5 s | Jito `ACvL73` | guard fail | -0.0005 |
| 60 | 09:27:53 | [2Q1DZt](https://gmgn.ai/sol/token/2Q1DZtUmmbiMu3o6gdEz6FShgo5gbsQ6XQS6r7wNRTFg) | 0.35 | 0.22 | 2.94 / −10% | 4.7 s | Jito `5pPRHn` | filled | **-0.0490** |
| 61 | 09:27:57 | [2Q1DZt](https://gmgn.ai/sol/token/2Q1DZtUmmbiMu3o6gdEz6FShgo5gbsQ6XQS6r7wNRTFg) | 0.35 | 0.30 | 3.92 / −15% | 8.7 s | Jito `ACvL73` | guard fail | -0.0005 |
| 62 | 09:32:35 | [4mdNnU](https://gmgn.ai/sol/token/4mdNnU42zrRKGz2MLbywnF43WvmVtbya4sK2958bpump) | 0.35 | -1.40 | 6.72 / −17% | 13.4 s | Firedancer `HW4zor` | filled | **-0.0179** |
| 63 | 09:34:37 | [3VHzof](https://gmgn.ai/sol/token/3VHzofuiRxoKrbwu2KrJTfXNWchsQbWLp3Hhwdk7pump) | 0.35 | 0.37 | 4.01 / −16% | 2.1 s | BAM `BUv44c` | filled | **-0.0111** |
| 64 | 09:38:11 | [84GB6M](https://gmgn.ai/sol/token/84GB6MiGwvgFdeqV87t3Pb2YHyQTAZYngettj7swbNJh) | 0.35 | -0.07 | 3.01 / −12% | 6.4 s | Harmonic `A1vqhA` | filled | **+0.0241** |
| 65 | 09:53:10 | [EjX3FJ](https://gmgn.ai/sol/token/EjX3FJ4JyHjMJfsBJhqv4GGvuGnCTs25QLzUQb7Qpump) | 0.35 | 0.20 | 3.01 / −14% | 4.7 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 66 | 09:57:26 | [44MTU4](https://gmgn.ai/sol/token/44MTU4G9UPFLnsStuUMmcbQckkha7a2zakFd9Sddpump) | 0.35 | -0.35 | 5.56 / −11% | 117.7 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 67 | 10:03:22 | [47Me6d](https://gmgn.ai/sol/token/47Me6dCMtKKrhf9s3UfUZy5F7yU9MrEdEvh2pMvYpump) | 0.35 | 0.20 | 3.32 / −13% | 13.8 s | Jito `5pPRHn` | filled | **+0.0910** |
| 68 | 10:07:42 | [AJ5aDM](https://gmgn.ai/sol/token/AJ5aDMsSY4k6eqfrGLWS6nQErL6QeiVLs4Adz5sspump) | 0.35 | -0.18 | 2.54 / −12% | 2.3 s | BAM `MBVyz9` | guard fail | -0.0005 |
| 69 | 10:41:08 | [GftBQH](https://gmgn.ai/sol/token/GftBQHQ3DUjspEWpSDRPXCHJrgK3g3W94ZyL2jw2PVRt) | 0.35 | -2.71 | 1.17 / −7% | 12.3 s | BAM `HbidP4` | guard fail | -0.0005 |
| 70 | 10:42:24 | [FXj1bk](https://gmgn.ai/sol/token/FXj1bkRhQB8uqJ63ekeKDnfWCKYKgqcMTJzRiT95pump) | 0.35 | -0.77 | 3.26 / −8% | 25.6 s | Harmonic `EkvdKh` | filled | **-0.0055** |
| 71 | 10:55:36 | [GMQJME](https://gmgn.ai/sol/token/GMQJMEJA2bDtDKXtxM2K8bvPQNvpHkB4gvJFFqZtah53) | 0.35 | -1.85 | 1.32 / −8% | 6.8 s | BAM `722RdW` | filled | **-0.0210** |
| 72 | 12:14:03 | [D6CmF2](https://gmgn.ai/sol/token/D6CmF2qmHT9tpoU4QT1YJ9g1gP3XxjKigYghk4SRpump) | 0.35 | -0.49 | 2.16 / −11% | 2.1 s | Harmonic `EkvdKh` | guard fail | -0.0005 |
| 73 | 12:29:34 | [4hj5Pf](https://gmgn.ai/sol/token/4hj5Pf5UNtu5UCjv3kCLQscj6B9TroUDcDMnGzEhpump) | 0.35 | -0.26 | 2.66 / −14% | 14.8 s | BAM `ciTyjz` | guard fail | -0.0005 |
| 74 | 12:30:08 | [3MuFZa](https://gmgn.ai/sol/token/3MuFZarf1CFhca5wNhTPKn4oNSVX2xHmZKGfZ7qJpump) | 0.35 | -0.20 | 3.78 / −15% | 5.1 s | Jito `8NpDWR` | guard fail | -0.0005 |
| 75 | 12:41:38 | [63r5pz](https://gmgn.ai/sol/token/63r5pzFgBnLkvFm57fVmn236a1mD5XPE6muMYr5Fpump) | 0.35 | 0.02 | 3.02 / −11% | 6.4 s | Jito `7cVfgA` | filled | **+0.0521** |
| 76 | 12:43:24 | [5rh8HB](https://gmgn.ai/sol/token/5rh8HByKoZDv7t2Jvis18FMSEz4oN78Q2RtbcT13pump) | 0.35 | -0.34 | 3.08 / −12% | 3.8 s | BAM `22rU5y` | filled | **-0.0832** |
| 77 | 12:43:29 | [5rh8HB](https://gmgn.ai/sol/token/5rh8HByKoZDv7t2Jvis18FMSEz4oN78Q2RtbcT13pump) | 0.35 | -0.60 | 3.16 / −14% | 8.9 s | Jito `7cVfgA` | filled | **-0.0011** |
| 78 | 12:46:24 | [EfFBmb](https://gmgn.ai/sol/token/EfFBmbzspFkcT11DZEnkdV1bq2cgH6HjWxEH7uiUpump) | 0.35 | -0.11 | 3.33 / −12% | 42.8 s | BAM `CoG8d9` | guard fail | -0.0005 |
| 79 | 12:46:24 | [6Jn6ug](https://gmgn.ai/sol/token/6Jn6ugDnJSE9rPqEX5nHzydq3meVEYhAfSG9KhDPpump) | 0.35 | -0.70 | 2.27 / −11% | 2.3 s | Jito `GnC339` | filled | **+0.0356** |
| 80 | 12:47:42 | [6ZXmWS](https://gmgn.ai/sol/token/6ZXmWSphF24Ez2gV2AUh4hbiwQrW5thir1JJFjJ7pump) | 0.35 | -1.05 | 5.51 / −19% | 6.4 s | BAM `8ebFZA` | guard fail | -0.0005 |
| 81 | 13:18:29 | [9nD4xw](https://gmgn.ai/sol/token/9nD4xwTKJtEBacuEmZcv3LxvKZ5kpUdhm7j7DpwsNbfc) | 0.35 | -2.27 | 1.41 / −8% | 92.4 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 82 | 13:31:17 | [8bMJGF](https://gmgn.ai/sol/token/8bMJGFtpbuTpZExSPEppei6xWZyqbz168e213Bj6pump) | 0.35 | -0.43 | 2.92 / −12% | 5.5 s | Harmonic `A1vqhA` | guard fail | -0.0005 |
| 83 | 14:03:57 | [EE2udR](https://gmgn.ai/sol/token/EE2udRkfv4bgDAmWWS2eSJpVs3b1Yp2c9wJ5dkH4pump) | 0.35 | 0.30 | 6.72 / −23% | 7.8 s | Firedancer `HW4zor` | filled | **-0.0153** |
| 84 | 14:16:19 | [AWpYM1](https://gmgn.ai/sol/token/AWpYM13SvDb92qZnBzR5kgUPyVqW1Qtmzxvx3asUpump) | 0.35 | -0.77 | 4.75 / −21% | 2.3 s | Harmonic `A1vqhA` | guard fail | -0.0005 |
| 85 | 14:33:05 | [Agn4cm](https://gmgn.ai/sol/token/Agn4cmRwPNQse3faqVsztNgQmaAVjpfCEiqSFrtppump) | 0.35 | 0.24 | 6.72 / −22% | 107.7 s | Firedancer `HW4zor` | filled | **-0.0378** |
| 86 | 15:19:50 | [BBDJBc](https://gmgn.ai/sol/token/BBDJBcYqwfjEH1mzXSMQYHpavVPDBxPX1hbVsCvbpump) | 0.35 | 0.01 | 3.36 / −14% | 5.3 s | Jito `ABC1U4` | guard fail | -0.0005 |
| 87 | 15:21:26 | [6wwxxs](https://gmgn.ai/sol/token/6wwxxsPxadP1e472qcuZ6MxCwnRei1XE3c21pRjQpump) | 0.35 | -0.00 | 2.83 / −14% | 5.3 s | BAM `GBQ2Gv` | guard fail | -0.0005 |
| 88 | 15:21:50 | [5mHRYC](https://gmgn.ai/sol/token/5mHRYC4xWfaqzQTHQPPB7fkiim3iUWERs3oJfWm6pump) | 0.35 | 0.27 | 2.96 / −14% | 5.3 s | Harmonic `GoeW4a` | guard fail | -0.0005 |
| 89 | 15:22:02 | [3Yy56A](https://gmgn.ai/sol/token/3Yy56ANdnCqJYDLwxMjWpkLsvMb38Hoqh3wDUZTdpump) | 0.35 | -1.22 | 2.17 / −7% | 12.5 s | Firedancer `9WzPWq` | guard fail | -0.0005 |
| 90 | 15:23:18 | [BBDJBc](https://gmgn.ai/sol/token/BBDJBcYqwfjEH1mzXSMQYHpavVPDBxPX1hbVsCvbpump) | 0.35 | 0.92 | 3.77 / −18% | 212.8 s | BAM `5essVp` | filled | **-0.0120** |
| 91 | 15:27:12 | [3P1CM6](https://gmgn.ai/sol/token/3P1CM6VJFrqPgewDgFvkJY1qrWR3tmsUT1AKkYbRpump) | 0.35 | -0.23 | 6.72 / −14% | 76.1 s | Firedancer `HW4zor` | filled | **+0.0063** |
| 92 | 15:42:33 | [AZ322G](https://gmgn.ai/sol/token/AZ322GFNbZaMhaRnJLFKEmYgc369td8JJGe3EXxvpump) | 0.35 | 0.31 | 2.62 / −13% | 6.8 s | Harmonic `EkvdKh` | filled | **+0.0031** |
| 93 | 15:49:43 | [Frmcfm](https://gmgn.ai/sol/token/FrmcfmPeTs6QmyNm2rjfatPNaiKuYWz3Dt4aDBZopump) | 0.35 | -0.19 | 4.66 / −19% | 4.0 s | BAM `722RdW` | filled | **-0.0254** |
| 94 | 15:51:53 | [GRa3A8](https://gmgn.ai/sol/token/GRa3A8cFw32YDNd8S2UwQ2g7cLxCW6DqAj1jHtQ4pump) | 0.35 | -0.02 | 2.26 / −10% | 4.5 s | Harmonic `GoeW4a` | guard fail | -0.0005 |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 48 | same | 2 | **solami** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/jko2waxHHvaZ4KwsUyPAY9FmBtF6wJJFz8CpRJzfmrVx2aj1iGpVr8KscqWtAprfnBJDwN3p64Ftd7BsL88NyZF) [dump](https://solscan.io/tx/622STd1N2DDeqvcBT8UDXFe7FUArCddNyMvUwsvg1ZZTPnnYa5owpQ26jRbVGLNg2V3ybPoGQ5VMzTp4Aun9uejG) |
| 2 | 95 | same | 5 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt | – | – | [buy](https://solscan.io/tx/3KrwdFytBQRggpmwTr6muy66HXyKRGn9EFih3qMyuGpJqtHjxM49TNUmrE7ZYBu6BZfwiQV3zgDpdUez2ShhhXZP) [dump](https://solscan.io/tx/4WVWdzCmE6k6cG8LKd7nh8pN2zXVCPUrDbnCrFgF3BaLnBBpMZgRUXw4Rkmzpxth6ZePH6ZC83XbG9XdSpBCdEBb) |
| 3 | 38 | same | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/41Kw6ATs27nU7EbrXiBcJr3pb63td5cpT1ggKjRTjhEH86FLfVLQhWf7waS9CVAeiTDPZn4RoxVYMeCqSHfyQ8S3) [dump](https://solscan.io/tx/3934ic8FCemH6xdSqeQVpjNfbZYPQFQ8jNAb2FZaFMcXWSybL4sDV57eeXFSFEm2hFwygRMHrqTYksp83v8PqvPW) |
| 4 | 75 | +1 | 0 | **nozomi** of falcon-udp+landx-fra3+nozomi+helius-swqos+bolt+falcon+0slot+glaive | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/3opVYcWyqrwr8mC253NwZZjZzkKsUfgFH2tgWqZ35r9SP9CchZ8Rt6k8VvBpWR3irhB8DP3CskpXt6GEusmqLkmL) [sell](https://solscan.io/tx/4Uj11PxHAQziMyTWLAp5X3QdVwwy8g22NH5Hp2BzFWxcj5mVBJeXFurJDf4mygu1dGAJH9hS8uh1CQHiJuWfDZxp) [dump](https://solscan.io/tx/mtiSvUa5JwztZcderJyjWh4BDgeeNgoKujinQbBMRkxGHN2VJE54dtZhD9g1N9d43yYEkF75EygcWzfPu3S7DjS) |
| 5 | 50 | +1 | 0 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/4SGxxqHTFY43ZiBQ5X5wYbwEDjhDaGPgvaGX8TyA7vpghi3M1bmydD4FmBYNwdCgGzJD2LUGodBY44SiSAYparkg) [sell](https://solscan.io/tx/gP1eu99Xoxk4rJJZyhStQFid3FuyWix3DX2HvbhJZDMCruPuxASPjSqZe35k5qKyjBsryJKDK6cesUySUEtxxmp) [dump](https://solscan.io/tx/3Tdd9ZBaevBnsj8BJFJw6tvoJhp8g3A5b1rygqa4YMZB4v41mkfb3SZ7qu5A5DcnB2QPCqm7WCanwXajTBw8wAH4) |
| 6 | 37 | same | 2 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/VNpVfTyp6SPSDihoDM369nufgEw6Bpbr3cPrH6LF6xFYAXQ8wFByzJwBNmKo8RQkRBvDhYSEKN2xVtBdCcUHcQN) [dump](https://solscan.io/tx/2pAFi1x3drzz2UTjgh4yQfW87Rf5eC9MRJLBSrtUo2JjbXDqZDuDBQMAY77BwJUc6mx8hSx9GySLT8EghUkfqLuD) |
| 7 | 36 | +1 | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/34zfw8nPopmMAWXyeq3g17DDeG6jCppNd8LAPFWXJQmhCcRhrKifYqWv6VaE7vfvywKnifnEsCyJJ2L2mXi59zwk) [sell](https://solscan.io/tx/2ckQUxddFHhW9XbxEr3QDoFjJC3uofaLDBnSRhmVFw1bVvs6DYdL4RoV5XeXA8SGaptYcGrb8ydSkKJqA3HWh763) [dump](https://solscan.io/tx/3mk1xyk81eDpxYyKSE8MEC9NRkurvwGWSyUZXuhTY549MG4L1xq7GbaZyaDQEvcxVwrBFKGx7MYizrnNkXKZ5qQx) |
| 8 | 141 | +1 | 4 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/2itpdoSpFCsnK8eqbxMZu2F4r5G8672d3BwrCjqQm9Hb66q1yHxP2Hdnbfeifbiw8PBPhderYzbcdk7Phyvgmnhq) [dump](https://solscan.io/tx/4Yv82fc6SHz7X93WRYK11NwGs83Ua7WJaCNGEGNJQb2SLGbV5a6vSWzWeSLyJXbFKbCCeXcsYTRGs4TrofHTPswm) |
| 9 | 28 | same | 4 | **landx-fra3** of landx-fra3+falcon-udp+0slot+nozomi+staked-rpc+helius-swqos+bolt+falcon | – | – | [buy](https://solscan.io/tx/3pn16wiEu5tWG9dKJkukBPrCULhJR7vVMHCuB6vaZ3go8ERsS38yGhp3CHH1a6eWHB6tiu6d7fNJyHjBQS4FGQkw) [dump](https://solscan.io/tx/5HB7EWUxayPAQjkfmtMkDbm5BpVef85M9KooGuuXvQ6QiMAKSQCeGDbvmp24kypEfe1BQXcTb1jXtysPApX3rHqS) |
| 10 | 11 | same | 3 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3BzH9JwssmEcxrgFFbarczH5ANx6jukK7u3NQkeaacuJ9kGv3uN8DUBgAakuxj2f13gpkergomqQUeC6xZBzxGP7) [dump](https://solscan.io/tx/4omVcWw4sZdZNoVkZ78p5xGLeRfVfZiC1gdToHSkVXgQTU673Zh281EEFiThPsDznYrRJRngWFUNxUEjno7cAyyZ) |
| 11 | 16 | same | 4 | **glaive** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot+glaive | – | – | [buy](https://solscan.io/tx/5tpBYe5oAWxnK2bnuRa1D461TxBra593oSUoqWBFV6Zi6VG3wd1EK1e9mAGHYiUdzaM62pKZ43ejAxjbhLG9grwt) [dump](https://solscan.io/tx/3XJVxmpnDeTBtYjt12bWdybSKi3hQDfBTQ9bBtyp2grgYCPGvW9PgpLT22gThPBHMjuvjgZjHqnXGSBdbjnE7omv) |
| 12 | 122 | same | 5 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/5EoEdWqzhJiaExcdhBaDVwZmxDj1CEtzE2X62voWdTQRVf8NAXAymJF8qsGsTTjqVVawMxFvm7JDe5xFWDw3MKmC) [dump](https://solscan.io/tx/2QmAJ8sfPPcFjfPfCZrNEKdAbFCEp7xHgZBphik2Zash4ar9Lp9MZJAnDNqNVC9BLmqJpKmoUJ5i1PunhrL6hbM1) |
| 13 | 34 | same | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/52LM8nCrYRq1ufeoyYmnSaud2Po8j72urWjfAmpBiD3V6gGJhMr336Npfmve4UTC8s31n4nMt4TRshZmQ9cMPGkc) [sell](https://solscan.io/tx/5EU9qavAAHU4qv4T7YG5d9HtVGKW2rpygzRyE9vHt6ATBSH7paT2pTC9QjDw4uoMMJbkiPo2YqQyt6xLk4QzKepi) [dump](https://solscan.io/tx/2PTKFLLCa7bj5TG3DNCL9sq9cz9AR6JgWUWuP7ZwYZaZNw1FpJ5aT5E5zW7h9tU454X8wFhacVjZYdEG1LfuVbKE) |
| 14 | 19 | same | 2 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/4wXr3quEmfD26E7PNVXjbjYDFTpei3s8DGF6tScEQzG3tMjiYL12rb7WKuDikG5D91vYezsoywtxC1Upjkb5y3kA) [sell](https://solscan.io/tx/2VsYZ34Q3WsjxU8UmjTncr3nVa6hNDdq18Pq6rQ8dZ6wBP3uPVzcmFJbpZDvqZXixf3sRU57aviyDddN7CjJTy9v) [dump](https://solscan.io/tx/3LDipVz9z1RW5AgyK2Yxb56txgCa6Ha9FFRm58mDfVoYyDD7rnSSFuSY5JpdqeHzZbFMzHJpGyPoVci99pc1rhTz) |
| 15 | 151 | +1 | 6 | **soyas** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/33vZ7hBqZTQF5HVCf7D79ADp5Y2KFjJACtcwh3caseL469g26KfLtAB2fFifzn7QihJn74RuJ78HPeVXeaegHgMm) [dump](https://solscan.io/tx/3ipgwNBQoVccDJLBzJzkRQB85tSo1dbGbfPVC9os7SGMyNxMXaQHUzsRQSeeJcxLjCxMprWHRHP2sqomx4sncRuL) |
| 16 | 47 | same | 1 | **landx-fra3** of landx-fra3+0slot+nozomi+staked-rpc | time-limit 2.1 s | 1 | [buy](https://solscan.io/tx/5XFhJsM2BNgLiQJmH7v3kYGweVNggkmgmpbZVXNhBuacdvYhe57vtut1kEziF1iZKUq1PV4bEVYYvcKvXjCFn5Ym) [sell](https://solscan.io/tx/3EEaKVn6oSma1ZqyRvxHbnqsCeTWX5GmbEGpkn4Qk3J1uHZW6Ed5NT9mcupNmCzUprhYcJfyXFeVLTuDDNZXpbHn) [dump](https://solscan.io/tx/4QhbkptdNiQ63BbeQUBPEA4W1RexPJxhbfiWmUWQfSR1WSrrNgdynrfpbLG4Gg9nCaXLsu5AruNZZLoh2HU5bpoF) |
| 17 | 25 | same | 4 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/4uM29jHN3jd4DDn6qqD9Xeb6mDufEW1s7u9vuDLGExZExUXutnqBZSxmPmkaunkJLnvEkhYU3k8QxeftnFk6m2po) [dump](https://solscan.io/tx/51nSnvez2hqaDawxQv7vXJ7A9TzJex69S136DQ5xL2YxdGqwDgvN6oqfmUhcGG7Yx54YTcJd8RffqGxcpoECv6UX) |
| 18 | 27 | same | 0 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/wN5R9AbmjS2oSC1LZanW4Qo6iNGUEq42mvME7VnXD8fTizHgZAZKFtovm5qGnKJT1sn97VNHMcYNNDsKPmDsKgQ) [sell](https://solscan.io/tx/38dqGVTKYGfHrynUhXa33GKY9ghmzQ8hjWZ6JjEv1PM5A8ox8GVv8AriECaBxZLFZifYswoD9ZRg7tXkMzRV9wKR) [dump](https://solscan.io/tx/PvotKjPQ7nXqbJqx2Md6uKCTNXs2reAeGSkDn6GYk38HHmw74eryygBJ9jpMcSaaM3k6jmKYSpCDhe5CMoXhHLS) |
| 19 | 38 | same | 2 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/eeyhVKL8sDDBSjccFpoYJUtGN2fwXq1fdyBU1cJdcRRTW9p4hieRkNawZ4FkJ2q7sBYmx3ZwyxEZuiyL8fcF8tS) [sell](https://solscan.io/tx/51s2sQbog4ogxPjJQAmg4Q88TUgoitBfW7b8XUxcJ1fEqruBshb1d2Pjkc7LQsJibeEJvYFhZwUhYMMPFdB284Ac) [dump](https://solscan.io/tx/4zbZtddPZFb27eLDYir66dQzwWGFZznXmMHcvN2P9hAMbuES6nN5vBomZ97z8FU84rdGuVayXXSAD2MCDfPeggyx) |
| 20 | 26 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2LNv534tNjxpMtXePdiGEwLcUzuD6jm4rBZseZB9DYbmRAj5xqJeb4B2YJhaB4Mv7npLasNhawzj5vLduinMzipM) [sell](https://solscan.io/tx/5rqDrMD8oggGn54edVta1skNqh9koVDEyUhTjFW8C7xUSJCNmHjZ3z2Qqbv8r41z86dickbjBugWmgEjKdhxF1LM) [dump](https://solscan.io/tx/2W876XMTh7TW739w8mN4v7a7iMbzZabmN1VZJJr45frUz1kNkfTx7fzXo5mQaK6rVYpWQPKJYrDKMkatN2aiYBXA) |
| 21 | 34 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2G6kGuN8HWy7BgJcj7X7g9SZ917EyGrosohQAViqh2Wc6cCqUXq3ALuzFEZedVuPSoJpZBwZ89WaJnNxkTFbUjY2) [sell](https://solscan.io/tx/5xGceQndEFJt5kGVBcA6oQTBvrCnHgdMWTuY7FHpWQ6EJHx2wJQj6jn1i7Wk6JZzDXewhFDVUTC4nYJtYBKJbLfg) [dump](https://solscan.io/tx/2E4somiJnmuDGZYP2NiBz8kcF8L1Ngq6Xxz8pLmJLkFwN7qgsNMsfQGUxrKajALn8MftbCdm7Xm9Tm8RUpV5hodh) |
| 22 | 38 | same | 3 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 2.0 s | 1 | [buy](https://solscan.io/tx/43frHtz7R5eS7gVgeAN2cA3C4LaXWxPCpDxgdNUBfPaQnh61sCJnxccu1DU74E9umwJsisdK9hqW9NGmPuJER1kK) [sell](https://solscan.io/tx/5Z4G4G8JUHZbdLJRnTusLKLRnuRCQRT7DVj9ndTnTPWKt3tRdqCEUqgBBqKrWhvLWtzuWinefRsW8kNAyKdu1Tck) [dump](https://solscan.io/tx/Gn68qrZeuuC9oyDAMrse8Z64LaayXvVCjBg83iEwsCNgoQrd41UrUctNdzvFWE6LBemgCnDugdpJS1pnfdfmPmz) |
| 23 | 16 | same | 2 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/Gi5B2DHdjGUqiLis8e2rrRZjbvpj5MrQiRKhJ1NtuCiVbng8XSRBoMv9CehyABetituZfXcQ613DiMaTvF5vtrt) [dump](https://solscan.io/tx/2C4QEDQ38roLFv8Xz2BV85VuMCzXcDjVKi8xcwLdCc3NcAJNQsbFmSpqCg8CJzo33sbCkCB64u4NQrRBt7FV2KSu) |
| 24 | 20 | same | 0 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/48BrF3JWfuFSDVgPBh6NA7qgBqwegVbRWqi5BbPNi1HDRQEezCnYbMQi9jfoQhnwDAx7iUYaaGQgtuCNcgC1YvML) [sell](https://solscan.io/tx/4B6i7mbttrGfpPCWAsQXFEcrtmZ53oQkWqfxZ6LVcPcozefLJDnedtyGmtAwVXZRMkB14vUKVijtJQKTprjnA7qM) [dump](https://solscan.io/tx/2QpH597z74Kf6pwHt3qmifvzhnEAHBFnpAsf6isRxqRDXLdg4zKDtWidH9HZwo2tX1oXNzTqhxdimXgD6UTkmX4D) |
| 25 | 28 | +1 | 3 | **helius-swqos** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/2ixX1sT7nfLvnjg7HqmemFdG35JDMozVureMAycN7VowfnyREcL9zv3mLSQUQL9ovT9bYFQkAvn7TuGKsGnsTiKc) [dump](https://solscan.io/tx/5Dd2AM5ikqSiUTDt1QxdcxTpSJJRmeHkERTWZFaEcPcYrMuDgWXWeD1EpZSjrL64jmb6PYAx5f4btQt7K5L4gKUs) |
| 26 | 62 | same | 2 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/E83QW8sBjsYsN7WCmNwqKvkyske42cxUKn74BAGpGRhwR1ioDWDrTRtWsfaRTmsgdYVxG6SUgjM8MuyCjzbyRr8) [dump](https://solscan.io/tx/3tewr6yNWyJDdEkhWLKNa5F318DqmhgFfwWSDgK7LtKMR6QaaiZjjzQ6KiyZRP2iejitwpqMcnujdjXQ1jnMu6ry) |
| 27 | 17 | same | 3 | **0slot** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/L2TyH2ShiHvQ63kj964pjwSeoiGSKkK7GrQKgt2mt6kS94yREZhN3DjND5RozCbRdbtcWNz8FPw77u4H9PzXZ3D) [dump](https://solscan.io/tx/2wraCwgvQthMq5rsnawS31VUChvPQgsxQwT4CCbhr8h2UFckk8zRZWpdRKhEdw8yJQrRpFEfNwLx6QthjUzCu4Fy) |
| 28 | 138 | +1 | 5 | **0slot** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4DxC1c4C61jZkWWCG3mpPVvpWpho81KjXCvCAhEaY6VjGVvztJAGLsi92F4po9BYhR3jDSHphkt6hZRv8ywPJP8Q) [dump](https://solscan.io/tx/3WqfSSaY2ZQxaqrKSBD1E6sTqYqQDE1BZiYh6B7Vem5TR3ME2kF7cYv18ym2bgY9LeGzFhsmyobXvNykSDfiWqup) |
| 29 | 151 | +1 | 3 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/5nudup6jV1JXHd2pAYeXy8qMc11dx2QpcVnczTMdAYKeYvyq1y51wD9FyHJEZgajpyjSbMpoKfRKFvFd1akb6cmY) [sell](https://solscan.io/tx/2mJMNdvbPe4su8YGK4exqmX7vVrZPUK3Nmm4YZzBz4MYZXTNJfLwgwCXYnen9t3LZG1QvjnLXs4XcimvKYLbasPW) [dump](https://solscan.io/tx/63PTwdT52pTCih2csuP4T6E5hPeZZ814Gz2GWkAYKwxGgokCjzA5LhKV7oddMoRjzx2oGWL1sgYSoswSzv9ZdKhD) |
| 30 | 16 | same | 3 | **solami** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot+glaive | – | – | [buy](https://solscan.io/tx/JCP1morMrcivpTvBdhNFN1mAvtKYsDZd1hLEh3ojf3W8pMPMkMyikqyWJ4A392gBYJuReEuY9sAm2wWsSwVPZFm) [dump](https://solscan.io/tx/4LVsgVALpF9wPeHK633fvHSFAxZtReabMPMQsLS7D6U2ZYwprFbrUmfjbwbz7p91QUhsnB1E5LDe3UHx3DbkGUut) |
| 31 | 42 | same | 1 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2GdYDyhcCnF61xv4zpuexagJQt9mSuuoY6GBE8hpvfQUH7UbxAtjso7U4HFxFa9xeYWBwCxha8JyKTpsFXMAmXLG) [sell](https://solscan.io/tx/FEkS7UUxhWVig2ST3tJJmHEka3KyySvDm1YFdHWj4p7g77BqGCGYTEFJBeUXon3kZv1hjcXX9Dr1b2E8VJw4tbv) [dump](https://solscan.io/tx/4RdkYkAFvwzL88jr5BUxAYak8Ps3anyFFb1xQ81yAq7LxNizoTTkaugHn9CzopyiuLTM1JztWMmKbtU8JEef7CQK) |
| 32 | 44 | +1 | 0 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/25SM7FP1VWDUntRp5uEHCyAeAkEJ5QVmXfvGuhmvtXFB1GjhkqSWFwSBfXJ2YvHJvCJNPYLUaigMshqz9nyZ3STG) [sell](https://solscan.io/tx/2zwf7M4n1oCapLY5VrsPmutfkZq5gTtCQdZqJ4THnu76sXxuN2K675oY4BGgYqpwFcEV6DfvQjfjX2S4A9T2EshR) [dump](https://solscan.io/tx/2zYFtRw12nxAjftfm2F5oDoD6WJbXK5zdP2YUFaHfcgmSTLt5h1kEBcZSxu5PppKfUi4p548DrxBs2oECcqCQ4Tu) |
| 33 | 44 | same | 4 | **soyas** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/2Qk4Kvpk7t6x8ByH5hKtU14yGHV1FS16N3hE4XbbQ7N8dHBFykQQfcaZdHfXcfEaptx49QJSrMQcTF9Z17NsJKvQ) [dump](https://solscan.io/tx/2o5VQSjjKYKTZRrLK4xaEN1VhqXFvujcQXmneXPYxkZxBQHbJowqnvycoEBa4eKPtv4ZjxUp12hNoqnZukQiWmez) |
| 34 | 20 | same | 2 | **solami** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/4i7qtEzmaxANUKEeGn1FaC4PNeM5ogwnnYZ1ZS5cdkuB6CAjhuHTRSd6YtLy7UoEjcMn9HKDU6zHCAuD52JQTpmD) [dump](https://solscan.io/tx/2q5cebDF5LKK81iHDpd3j1jxqkZefePxXptD1KUsdo5AF3Suck6pQd4L3eKqikr2cLXLbxQSjAD6qCK6jfDF7hez) |
| 35 | 112 | same | 3 | **nozomi** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt | – | – | [buy](https://solscan.io/tx/396rTcYHSRoS4mVpns9j58YWhw8c1hT4KRWQtnKB9CS37i3WgLfvnJSzG2pgxGCYnnxN7ZGwW42AvajTYTfrpico) [dump](https://solscan.io/tx/9N5Qb7ZmrGuWVH9T2Toz9rugG9C1rtzP8aMYo45ueVsd2SsyECucsGSwykmYHfW79s27GdHgJZHtrf61QqSzBVP) |
| 36 | 25 | same | 6 | **soyas** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/2ouyCnbXMbx4daRgzxmpnvBfCESixRpKeDBeqx4WAAA2bfEhc346YWD2YZWu9UvZKvMTLDVMcSEq6rYuNkaeawJx) [dump](https://solscan.io/tx/4fQmJkGTR192RKsJ9oGGcEG8aVzbtrrnAkTnppjAqo2tXZX6VxE5KTzuTT56qxniuUgXtWmNBYCqiF5CJNh8Hw4H) |
| 37 | 42 | same | 5 | **falcon+falcon-udp** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/5qNnsTucnsLuNrvpCDBX9BXkeb1veg7PA3rij97SiJvQFACcQPggMXgmi7W5a6ZZwnaLsKynDHypALPgwDq4pTNL) [dump](https://solscan.io/tx/5m95nMZxmhTH4kYzy1LxCVdn1tD5vKkfZVoetfTxbUuyYcN29xwj97uoMiiTS6kNvdsQhKvNgh56x7fzQWnC2jLM) |
| 38 | 25 | same | 4 | **soyas** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/5uVhy1SgmcYxKeAtibWSfzqUBBTMszYBJn9VkUcc3bASuwEG2WoqVWTMMxUt5qGsLPVtrrFditxo4tLvpKi3CN3g) [dump](https://solscan.io/tx/4NmYgsRU1XrddUeoJpH5EuFfG5hsupbu4CTavtf5FrbBJnYmXqHwzcQ7xH9UmFU5D4j3j5GPug847sp4NzX83jHz) |
| 39 | 78 | same | 3 | **landx-fra3** of landx-fra3+0slot+nozomi+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/56SLj8rWza1kzac6FyWQyKf269rtCuQwC8go7BUCiqCn4tguGNfFNDk2LQ3KLHAg2CG2iSGfRWW9sdEBgV2FG69h) [sell](https://solscan.io/tx/57tp1dEWpWLECdEBVWnEPJb16k2TSy392e3ay1P3cwwLnq1D1uEmMtYwcZHNznir4WbXMRHSeSY6PsRFUc3g8yTw) [dump](https://solscan.io/tx/5k9XRWmiSEAEvbxQNSQ4uyNoXXfKbd8XNFB57bNLGhzw1ynBg32BT5eCcsYE5enkdwRnKSA8Ny4Kix6si7VKnYuu) |
| 40 | 58 | same | 2 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/1g8jvdiEnKJEyT2ab6mEyGvnSNmeoqFP1P3Bgds6v6m5jh8fcjBAcdzXanXzivzvfbfRaJPzbMqA1LrGYkH8vLK) [sell](https://solscan.io/tx/4JHFy18k2xZ9gYvxpVxKkr57a6XLqhqYRzc6jzqrvBa7FosEsmpMU43gUJd9bL2hX4GvEoB1uFdVD85rVpcJUAbn) [dump](https://solscan.io/tx/3Q5HH4Bohu7zy3QrxWyRczojSG29Q7qULJg1vb1aGzq1Yfp6WmHaQSsWExdSectCo16m9BuRsd4LwRZwb1C2BvYF) |
| 41 | 13 | same | 1 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/pNkRMQ5LTJbcYYX7PDfohRgBuwKjfcpxsgKAohuPnGJMaQaBw2g697MjUeTbRWdmNxm5GzG3HotaMtiBmgDkX9g) [sell](https://solscan.io/tx/JeyVNsK9UKh2RVMGiUsY3KTpunREPsjHire7NDxcygHMCsawyXYQsRj1U5HXjgRN9G8weoq5S3mR1EXoXJvywFR) [dump](https://solscan.io/tx/32aWR73PvZE2TqBYLK3p4bPWrq1846NrEtd7RT95X2tVMXxiyYxvfKKC3KvbmSJU9W49ixfcohHMfWUkFKjRTVbN) |
| 42 | 22 | same | 3 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/36mWwGGWRnvRuZZrf4WR3BnnSuiud7A6aRB62rKZWX9skFLtY1wytf6oJTKesVKa98HiiS8zMKMQxzJnhTECwncC) [dump](https://solscan.io/tx/5cwkhggr13wGFEXM7S4tzfrokZWkt7Co6k5GUT4FgkRyadyTPR9H25Gpd7ZcWuTAk7dtrHnkwnmYiAWFnWWJr9Z9) |
| 43 | 34 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/3wqBewc41EZPo9gQXW6BuBExw2X2T5B77QF81muwdEbZnXC8Cn6RRzNR4r2Xup5D2deGDxaKjQJws2fcFim4ZHJ3) [sell](https://solscan.io/tx/5xMqcQNN1rM82fLXX6CBGQ5UBHEjDifNkTH5ZWr7u361dH9H5GuP3eC6m2NZWF8PvSLv8GYqzKLduMaCRKaRsVxr) [dump](https://solscan.io/tx/4frf3HnKNnHj4aupDDmZhJSZJLzY32durwgi6YHx6ZnoyQgU5RjtqDf6fNssxrN7XLX7EagHAjuuKu4aWyS4Le3S) |
| 44 | 13 | same | 2 | **solami** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/Pmtwg1crw5tSUDzxdfuggu4zG62SU9fTX9d85gFPnuccRC2eCB6B129UFbkqr2oVP9p1JK9ty5HFTzaEHtEP9Um) [dump](https://solscan.io/tx/oAPZFXF6A65e6Pfcjrrhy7XnTo7G8aKtWPUiHV7EXkxXJoetscQjQ1zv26KtXSjwE9UncVB8ZckZm6TRceFheDT) |
| 45 | 122 | same | 3 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/2W14Ux2A19aNpPpwiGPVC7Exwiq8EbLPtkK4TkEsUz3Pp3gc9vLQbKBmSXMgwXUW8wvBaALiWVS64Ds36kK7wWxg) [dump](https://solscan.io/tx/4wqRGHJBVzZUeKubiWFkXyTMDiFos4bVxfzSRGoBoCL5iZHZbiQ68BWK7GZeL7mQjK623s1jQeAMnQBs3N2RKKFc) |
| 46 | 24 | same | 4 | **helius-swqos** of falcon-udp+landx-fra3+nozomi+helius-swqos+bolt+falcon+0slot+glaive | – | – | [buy](https://solscan.io/tx/5SUxrpF3ujtrVW7wq5W2xTYtkDY85umBpE5FTUsK47b6JBEvnLVUyGApAMUL4kvBn4wP9kX64iE25Y2m5VwDfWiy) [dump](https://solscan.io/tx/4qfpdgRh8Vsh4beAD17tQU1BZ8UVfLHEJT61ufYq1GBNUshBM5a6UYTcRjD7dVJ6jaAdGBW4RfVA1F2bRATXWLBj) |
| 47 | 15 | same | 2 | **soyas** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/3zWP8KhqctjsV5ffXNu5r3VCcKJ62qR6EE8ax7PbUU9Q6R8uDmXEiwJvsias1xEj3WmMftWU46XyAEjjj5M87QuW) [dump](https://solscan.io/tx/4DNCwFw6hiQaco6zwvfvn7pxDtWNBcauBMoQavbSqGZ9eigXJVH45gPtvB5u4aqPF2UsTzdi9cnFdgHMdJSduMP3) |
| 48 | 810 | +4 | 8 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/25sLCMPrD2Ckh3LLixqeqkwxBNXqxATS1FaCtdv77aoogVHSd9hYu6cYvYprHAyjjbc61LhimV3YwymWU5kK9SHc) [dump](https://solscan.io/tx/2owt72zsqHKkUEhzvtHxFBFW8Gx6yWyHVTr8wuHRPy9ckko6rqFcM88e8Fp5rM7bAM26Ki33GziN3nPSfHp76tBK) |
| 49 | 36 | same | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/4uX1KnDbYRcchdJarihGoNL3YKgdfNF2j1U5wA8FWCr5pNpLK5xC3YisWFD3Hb6GEaxL45S72eK2BY76E23gX8uY) [sell](https://solscan.io/tx/4kyHzAriiZQ894DHbtS6yxYbMwqnVrhSPtryhcge4GEizXwBFigjiAFK9gjz9T9s4Bg1bvEdfNHYgAXrbZR5TFHZ) [dump](https://solscan.io/tx/bvw8JKuoBVW2H1VktQvhh81oikgyn1ryiwXD22Gvgnu5ZRFdd6faYauzAze55BpCH283WkHervHXCb1obj583tY) |
| 50 | 158 | +1 | 8 | **falcon+falcon-udp** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3nTwuXbKoiyacjAAXgRNeJ6igAEBs3x1oSYGRWA9tgyA4Sim3GUvDCGqEWiTQToHD8YwXMQfLfSy552TZTpemdq6) [dump](https://solscan.io/tx/32FReaM8fDNuDMucoqJR5VuHDkuguX4EcFw16Vgp2ppWFNux2U4xDE1tarAqcwt6JSaaV8aq6ZYkgFYCmerHBdRQ) |
| 51 | 37 | +1 | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/JHjmgyRPYxDbQ28oVty2iPLKFMTtNdMXm6VrSE8tu1nWn1ayU55aeiMJjXpatsNoor5twiKRGXa9itA1RMP5Etb) [sell](https://solscan.io/tx/3KRoFDgVqtddpRsCEkz6PNi371Nm9G5GQoMZ3xMq2wJSLv26FPaXnoJattuwuhRPLwbDYPzMMiqyHqkY9bNExvGj) [dump](https://solscan.io/tx/34qSZfRbEdHnP2e2bdr1LwM6g8cPCy8UU4aFqw2XCE93kAGNcfvZgpaYCMaXM4AdqESoJ8G7pha2otZHyTwGLXfC) |
| 52 | 23 | same | 2 | **glaive** of falcon-udp+landx-fra3+glaive+falcon+helius-swqos+0slot+nozomi | time-limit 1.2 s | 1 | [buy](https://solscan.io/tx/4wWNiQUaqPMqGfUdugLW79HMRk6m2sazfebM1m55pqqUFX4dkDpJHMgSHA4XJ98woAdyeCaTcD9vtFrTKoKEHNPC) [sell](https://solscan.io/tx/5NcP2Yv51JmxtJRs9MT9FY5drW4tRxBVmztDqXKBdq2vpSkAdCxqPF7KGjNmb2TgUdpAoScQ2Q3G8cqrScVrvsXP) [dump](https://solscan.io/tx/8x99ubCTEmnvWhX3vk48YSRqL9BaYquHkaT4KDRc79z363BcWi6JAtKZVa13qDFhoNhCH7CwRoV8LVuSqeEvFBN) |
| 53 | 119 | +1 | 3 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.9 s | 1 | [buy](https://solscan.io/tx/sUrp8A5gE2TA7RkEfwi13Tmx8wiV3BVb2sMEg536y9CsW4q7B3ZkbsMj5FqQtMChM8piNP6X8YsTZoiABqLWier) [sell](https://solscan.io/tx/5DpZ3w7XWfz7T6LymVWqpX6jgXzcHduGDE4bYPwq3vADEVB2PKZykXP6gcS5CTLBvk296pjXua5Q1kpHEen9ZCAE) [dump](https://solscan.io/tx/4n5o76DmsQX4ocbxWHMmiEpVzJAwaVoXW5XJ1UZpRxiBgfMokgqT2xLjWb8GDwQfmohNCwoD74mdngsdbTXXgcuN) |
| 54 | 47 | same | 1 | **0slot** of falcon-udp+landx-fra3+glaive+falcon+helius-swqos+0slot+nozomi | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/3vJ1GEXUMPCT7kq9J3aUZZ33T1DhZkX7m5KAGVHLndAZYr7PcdZbM66jreeserPPgxDeXC8kdrYBhkykrRYAHwVf) [sell](https://solscan.io/tx/35HFWJDJKcndVuP5NUaj4nRq14VeDTrg7HBkca5da419omA5f9UanLfZ8MJMYQG4ivMMi9MmFNfHCvV1XcHKMUAv) [dump](https://solscan.io/tx/uX87vxZb74t3uSaza3AZsoQLrchm2wUZkN2eTPwiCTN9zN3Vg3dS1dpX2Z4MNFnwQtZ7mvKwhnjADkTQJ4HBe8M) |
| 55 | 38 | same | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/3BH8gVnwuhCtEvhZvAP9o7st3vt6wr9AQGWeryB6ENYpQcMu5jv79YXBTz4CD65mPBny2wRWBkXRBt6goKEHjsyZ) [sell](https://solscan.io/tx/33kkuyL8D4MnTLPVu9pwcv3XarFiktS1stx5cpyLS2JsMXRGtwGgP3MGMvgdtSyohAbyszxYn3kEMtoYiC1dyJBc) [dump](https://solscan.io/tx/2kRMPKN9zFabAXWkVE9jTsVPiN7866beZ9BgV6cX7Y5H2mRkFRmCcbCqz6MoQcgTmf4Z3cxVYGy8ewnh5qB6TW6u) |
| 56 | 40 | same | 8 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/5GBXfZE4kU7NTD6yHzLWJ5XJ27GDLqPHvQN7VNQLTZrLoJbo82CWXfxrsRjYarpSc89f7qBEywgKgTtu5SSySdMj) [dump](https://solscan.io/tx/9EnLmxfUWt7L1foaSPct5EhdkxVMV6kAWN5EswJEzajo69AEVSXUZcfVcWu6C3aybP6R84iviSdDad6bQg1a14E) |
| 57 | 144 | +1 | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/5KpH5fBCyZthzig8JQm7y4dYuUdobFpAEU1zQDBQQsU3rVaY37ySmqzFPpwBFD1CJpH2px2VimEXPKPegEakvZmw) [sell](https://solscan.io/tx/26Y9iVvfPxmv6uwvqfANCHtFiVnmgvogqkSupb7TmVAU7Bv2WBY3ymtU2X5qTXQAKvVBKEN27Sy1hehUdg6DiFEK) [dump](https://solscan.io/tx/2tuz989Hk3JMzdDL9AvunTzU4cX1RMonZjELuCnr5Q4TeGZ5G3YhRrFfYnun77nBAY8LPmqaHH9GpoSFgr4E8mZH) |
| 58 | 32 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/7xEWz5bPtqkLVF5zJuUszYM1ZbqDnSAKEdb2TpsAwk2V8yMC2mFcnS2PNi5bhQqi3VGSWY3QPGX25bkk9Wm7bz6) [sell](https://solscan.io/tx/2GVdZ9q9oYjJPfgESeRcd3DRBUsAfdm6q4nF3SMV7Kn1QimxGcKofguQziiTMdMyhoUJsPPuMh3D2RsM8SGrzYRe) [dump](https://solscan.io/tx/2Z42nh543rSYSpNb5MaTAeifxKS6pRAakeRShM2nUdG7Chp9F8CRNXE6FFDszBKCiWbrEWX8C8LNuBRfCVyor4CN) |
| 59 | 140 | same | 6 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/xKipF3hP2YqGpWHJTC9dWSykfHRTbvEEStyrK8T59Ly3Qeqv4QJik7Fy9bJ9rwAfQjhuUyUoP16kodt5qchDkfS) [dump](https://solscan.io/tx/46K5k1tj7RFEn5yZHb41sYDpwxy1SEwiabfKjb5LjXBY68uGWpjQHjQdeEqtjAWaVomxJPkti4DUWQLvU8aWiRoj) |
| 60 | 130 | +1 | 2 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/2ZXqGXmmNbw5PSZo9rJaCrojpBexk9xnhjWwzvacEpZwFVF8d55fZuaKXvebD1uWfG6LmaaRFWu4MLF2Ck8yGewd) [sell](https://solscan.io/tx/3RJEzoVWA7Ww4pAuQZ6gFzU3BvYwk56MKFgD3fPs2JAJDidcP7e7QuRYRu9aUyYB3NYEQe6nZuWkHZoFUH2XXGKk) [dump](https://solscan.io/tx/yTyBrsTyy2jMwVVKxbHXWxM6KxpWcT5zsD6pGPyfzR2rzRJESPdgWKJo8LATbXbViLdqDZmeYuLpRiLpDkzfcKg) |
| 61 | 131 | same | 9 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/qBjytEwSEkfiiFzKYfmna7smCTTeYK5uB5ifAk4JTdbrnY7SEGLuS5DFNXzKPAc9TSqAh6HT61dGWevWZ3W5zSh) [dump](https://solscan.io/tx/5cLLpBjy3zWGZPh7FksNSUu562go2Tucu2GTz3iViKdnZoNEV55dxBuTFyw6h6dHSpeJL2Pmj6F25BWce4JRv73T) |
| 62 | 101 | same | 0 | **landx-fra3** of landx-fra3+0slot+nozomi+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/5c7TQfkygsGRyJKrGjJsDNvCMUUxSjUck1PrQVdWi1TTzxdBMVyaVKkgZoaFjhakPPo5gnxbdPEB5Er1133zJt9J) [sell](https://solscan.io/tx/7hiaDBnqePqqpoAQnSA2AV4gX4PbDcM9Nw5aoHTVxzPSBUuzooZuSpWLKNcMhnZbvU2pYbS1Zs2j9zsgJWX5tVj) [dump](https://solscan.io/tx/SP8aZm42mZHP7sct2UriC6FUCvz1VZ4JYEmcqZPk65rYfzk2T7vt3oSour3XuHsULAamY33zMAaF1qmeRM2mHyk) |
| 63 | 142 | +1 | 0 | **staked-rpc** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/3qp63dC6pEY5LH1ZEcMFMeh1qDb9MBMdiCNsy6uTnwuxatF1niFkzKz8W1YN8ndArBmDqcshhkJbLepZZYhZ5PjH) [sell](https://solscan.io/tx/5Jpauyj2qAFK6VAZP2RYEWBUAfcgeycQAhJGzHmWsMbDFcqyiFJNuMoeEaLKqzQ49iWvej1CXxLPfrmUFNePMXug) [dump](https://solscan.io/tx/26LawL5kNNo5RkV3TCQxofSpG8Z4xa4kSgmgESyNhmauYVLs3RXojpbtSx7Das7EchBZXBVz8orwj8bFfzgJUM2R) |
| 64 | 49 | same | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/Q3by8nseyJ4ST9wRt94H2gEbFvhWN2tuKaM6Hq8T1bTsN6FbhWeVUUaWvQVHf6TktnoqX99miMWzrHPKphG9PqU) [sell](https://solscan.io/tx/4CKybwhygUmGZuHn5ZE8SK3DWEX2b5wmNnz4XtbDVr2fRZz7JrGHLkcX1e7zy7CXNw8Vb1uH5HTaeaRsZV525xKD) [dump](https://solscan.io/tx/5A87AT5qg69kM2PQxq4wwLWmfJsKgz5aGpVYZy75qabqifqEWvSqieFcHukF4hprxPTfVCn1s9GvTm6DvL9K2gXv) |
| 65 | 109 | same | 3 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/2SGmdMrMReq2PvhMwcCsRuqzB7vYNbB21jdPA8KuoDtKAHMgGAXpdtfjQQNu5X6dGCzEegaHFND54JTkqVnMHWzq) [dump](https://solscan.io/tx/3yMpvQB8VizFYhrNnRMwuf32wpkRs931cAUN6mvY4kfamnLozWdriJ2eTL2rLzYbrGzzyUKT4RoXu44EjmcyoCud) |
| 66 | 170 | +1 | 6 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4FkmTYAMtMKegbmSFcjNqRXdVCtsxYqsHvpXVyyPKrNhoByyg8RiKLRUa5KZS8G4e6vb3gPatYey7J9Xz7zjm858) [dump](https://solscan.io/tx/3CjFWZx6TTQVrAoUX1dh6sA45x348gHgN7BZVHzZxQUpstfFpmGwgQun83i5skX69Ky9uXvetRJnLjvLG87Gdg5M) |
| 67 | 21 | same | 0 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 2.0 s | 1 | [buy](https://solscan.io/tx/5QfpgLP2LFkb2ockZaDY8DqMcKR2FJJaQxVTU3fxRoSSsJhUQtXBZyBL55oSQbV47Ui6VZdUGvxFzppp6xjg86Kq) [sell](https://solscan.io/tx/4yjRSgk55jet6mTCTDa7s4zccsNoqFX6Hqf8kDB6UYAqcYM4LUbN4GBVKv91GgUGcjwsaDZunaYFvy8x8X3LnRn1) [dump](https://solscan.io/tx/5rsonwqkADyGm2B4fo2kVZgXAQSdprcvdX4XipRNPPtvsCi3ep5G2smBqND4iXhFHd1AYHgN27NYvU5tXN3BKxdu) |
| 68 | 25 | same | 3 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/2LF6vb7ZfP87t8MTroucqCAjCsapwdBXj8WyuZgWK7AmeZNqQgSxgahXPf2AmzHQ452QFs4q9ATJoUWi34SFKHay) [dump](https://solscan.io/tx/qBw2HTxE5JBjRz3QuS5TyHXgqdaF7crwnw9LMqgyjoq258ci8gWXs1mz6FVAyptqDosCke8PfoP3AK4wgNYfXgw) |
| 69 | 30 | same | 7 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/nm1VmJXvX55wUs4zbou8ireC554Jm9Yz24PNr1nbSvGTjmmzrBb9CNUqE56uTEXNBnoSUWpveQLynzeU8a7qW1o) [dump](https://solscan.io/tx/4ZjVmuRca2spVwXwd4zRrQiSAz87vFNTcxMiWQc9M8yra1mQM5Wt1qgFU7D86KiaNc4esHivRgNzzfGNfRvWzoHM) |
| 70 | 36 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/36G6dp1qncGdpmc7xx1fj92krDDr9ThFr31SJtC7nPasyvZ3FAvbcuhtGz34ckg5Gm5VzYSvz5JsqCSfV6unEZgS) [sell](https://solscan.io/tx/5gsExU2f68at7wcMDM85KN9Tv8sBuX8cDyLUvp7p9YqstBo5NvAx3oPJw8bJMpzUhBXscDZT1BYMjgEaPdk7Wsvr) [dump](https://solscan.io/tx/5pR4Ehu6E7qFj34KVFKGFo1KPccHJj8sdqyNbupLeuaAwa8aA88H1uvibYYc5orioyc6QudH9m1FuDbrXrKdDg57) |
| 71 | 32 | same | 2 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/3rHRLEBa4eXHCA7y7c9ipim1UkybzGJKtjwfz7jDhKj67oVkPUMoW5gPdaYEbq8Emqe2RsVFs4eFtX3v1RZYoLAw) [sell](https://solscan.io/tx/2vuKiYHrjUNLsUDddmAYBSKuFwyso7rmASPp4tLbdPBbmGYV9oq1neTB8Xx6AjhQdXPYcCPDN24FZJpzXirqBudb) [dump](https://solscan.io/tx/oFhUpxCTaXe6g5jbjsMoQnzSdTjczexnJPaAgRBJtC6Za5VX73a8gPoNd9We32DZJF2kvDTH7PjtDwPivwJUsn8) |
| 72 | 37 | same | 4 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/Jsjy5jMBjjCdRgLLhgWadkj4YrxouiChFxysmFudssNLjkZ2SPcucyV8ErzZeHaY6odzDyYytZgky2hgSPvYx8J) [dump](https://solscan.io/tx/2eU6QQ4oKAJJGYZqWtEYio4UujRPWgowsEgMg6siJA1UmT6tgtKfW7piJASWnChT5R9mm5rczHJZ8h1rVnEn4WnX) |
| 73 | 28 | same | 6 | **helius-swqos** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/3b7Lejo5MfQFTSV8FVrYVQ6rKNfv5xBbUDicrPNbrof9jBtugYHkywPowjXpRSE4FsMikHWxZUL8VpZGaAjsC9A9) [dump](https://solscan.io/tx/Jh88fvEtxe8aBNMnpt884rYbgSFCF4zn47BG5AdFgJXFRoibLoBKRRakPqdK3DrBNCfjhD6A9uh2cuBe2d8TY9N) |
| 74 | 138 | +1 | 4 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/2LYtcaZpP987EhG1eVt1FMKY7ihZA8yLb3H5wa3kBQiF3cJw3AeuCUMd7eg3TDM3e7NSkav5XUnbHPR8rEVGdk69) [dump](https://solscan.io/tx/3ekd3UUEozdUW2f4edR8MzDTicr9k82ys5BK13wfUtp82Bsn2489ayfHBF6YqAxM5rP3KdYyZiQcgNWRnxTGhTfH) |
| 75 | 172 | +1 | 5 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/5KyWPa6rYesZNzvCmyS8M8MmVoEK4MXvFbYWCV1YQRKpyVhExtQDo5T6nWJKQ9weuNuNArUAHzpke9AhzM6vJz2p) [sell](https://solscan.io/tx/93S6RR5A2A9knQ1QD2LVyF1ojPW7BWJKZxG8RvJckjZJ7ZMjmCogfSSLhEN7qn8R1QRhkqkNPhS9aAssogh5ant) [dump](https://solscan.io/tx/64wCKbXPjwBUAv8km1PUPahJdn264Aa4R7X1nkwgDQBoWMbAwRxau7BoTrxamd67GCwNCAMpdrgM3oC3WA2tW3xz) |
| 76 | 49 | same | 0 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/5hr8ju1S3xZ9ZkRWqcbLiMLTw6vTXptGHeNcNRnXmYC2zMoPJQiWLDRSHyiSeJrcTXfLkfogRx5Tjv3KngLkbm8Y) [sell](https://solscan.io/tx/4VKdfkajffYhzN9kWtuFH9xUy2URQnUj6P5SdsuNxGLZvjnjqYLSk81KWtUnA98g6dZ47WuqnVDmwiTg9iePEnkh) [dump](https://solscan.io/tx/3WCCR1FEEjZMcgYMNfASnC8ye4GmUQNyLRBVTWLY4YbPfk2Vi4ifMTG7DC1NURfqTjya3bsdEqCr8Y3mQ7bAPGWK) |
| 77 | 15 | same | 1 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/4Fi4iUDEMwLFFCia2vFhRaB5D6k5gGGZHkw9th8oNjEL9of81XQZCRa8LYKZj2PG1H5pcmSd1kgRe3D8jfiawiCf) [sell](https://solscan.io/tx/4r8TudGfHUmH1kcMen2geZgeaFD8YFLPp39qiAd6u3i3sgpe9yQc7yHfiuVsR158V7Jv8fJTj9yECv9VSA6CbASy) [dump](https://solscan.io/tx/2S1HTWbZuT8oayRVTNksr8U4nLc9NJvdQLzw1fsHj17XgJdBm4xnTSdJK1iC7UWiADJcVfXf94nDp8mwWHQxjofE) |
| 78 | 40 | same | 6 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot+glaive | – | – | [buy](https://solscan.io/tx/2o52HZUi3cJqRdv9G4aGnWi3TETbT8y8Boy9AgTcpTQnigkBg1VU5v6Ez4TdLDd8pE9LUVxRNutC7G1Judh97HQb) [dump](https://solscan.io/tx/3EVk5DzxHomXQTNArktcTABdTa8rQ8dbghX9HrHbjPfRnhnk89CPjJAMjKGf5akZ5ydtVRCoiWzUEr5mYkybP4Si) |
| 79 | 28 | same | 0 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/5xyXKrjAeWDksHcACLsCv5tffP6gWfEUAFBDVr73hYBfc4QTLtxFDb2zj1nTh7Vcnryzrw5bp5tuk2R89fsSro82) [sell](https://solscan.io/tx/2uBHavF67eMqFzgXiyYfi4MV1Qkb98Tjq2Y8qFjbECbYgPKfupEgJsLU8duwqdxHFybXamW2tFK8TeZE9ixtk8si) [dump](https://solscan.io/tx/RfcvbCkxUcjCjaaCSxYi5WHimvhQ1C27jXBQge23Cd1kCgzr1kUtmi7xVxAJtS6Kv6nnS8wcjNUSrdwi4tQW1z9) |
| 80 | 23 | same | 6 | **helius-swqos** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/3DC1pTThMTUk36WpEdNh8akEHoUtbFcKJQgfpaBNUH8rbJy99HBNgiPkry4ntB2d3EPK5wfWgc9ZbVUHP5p5KUN8) [dump](https://solscan.io/tx/2KmvpsTFPJ3LHqnGf5p4f49hj2HmY1wi2SRCFNAHsJjD3G75iqWmmewyTiDbBgVns8r9wf5ubAiEfK7zkUbopUxB) |
| 81 | 111 | same | 3 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/4U9F97rFRBqaxZTrh83QFYwuYNBQ24hRgWXFEUt6wUDWQ466evWNEXtxjkdfXqqueax4ZCPE8DjRq7YB2s1tcPhr) [dump](https://solscan.io/tx/3NByJuXvG8nfHmywD8mHN9KLvak9LihpcwMJCtFV8QrJ8arErswiWHBm6NFdwzR2r1ugCP2w1QqEKf6FVirE3JjV) |
| 82 | 41 | same | 4 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3aQFb5pfwoMeHnXmvLJEcqFzHEvH3L7dLRJHbMVZCCLBqc9HHsAijg435d6X6WLtmciPGCDAwncf1s9tHZ86ioLi) [dump](https://solscan.io/tx/3saiwQPftpDAXmC2LcXrmfsesKgcbvG7nnuW5fUdGPa7K5SS2rCPPN5US66oqFKmfijFGKvZkG3vbEkLqR92965V) |
| 83 | 81 | same | 0 | **landx-fra3** of landx-fra3+falcon-udp+0slot+nozomi+staked-rpc+glaive+falcon+helius-swqos | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/5Drt9BPtSPSL4sVHUDESt5iaRRZcmjF7oruZMbYn3TfcckcnMeaJZ3JxL2FUGMZJkTe82mWg76Etr9s9JcfPyj5N) [sell](https://solscan.io/tx/5NQSufBgH6vr3HYzbqKjrAwJnbb5R7GkoNk8RCMr4tRe1MRALGMnS2uVQN1PCKKYcVaSironaXWMqiuYA8HqQEFj) [dump](https://solscan.io/tx/434RXUVivxBWdcYF136zk9EWJFCo2ZmDpAJz2EFpBS2TtJnXyv8BfQgiGNGUZ4G8RsBkzBnQXxPyXSguWNGZd2cq) |
| 84 | 36 | same | 3 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/56hFfh5yh1zkHrGhgUKRgMX3hrGkhDqNqPcTBfeDJAATbPvWP8yrHFewtBy34UctNNF1tnkuHj5XYx3Vt7HoRUWD) [dump](https://solscan.io/tx/3BexGxrgRbRFEQN1C5Rm3rTBuj2eXtxT6Gux7qdjYmcGwHqHppoKnPgbZLA1eAa9CGtZB9M3aEN4UgE7f7paaSny) |
| 85 | 65 | same | 0 | **landx-fra3** of landx-fra3+falcon-udp+0slot+nozomi+staked-rpc+helius-swqos+bolt+falcon | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/4ZUwdQSGTAtn5dY6BtJvGCKGtCNpAtnCPD1J4sHr1QEb9YdDuXGooDXMW3Rbb55YVRLnwJe1zTWzdWWwbK2VMs5N) [sell](https://solscan.io/tx/3np6UWYktxnz94FxhN8UieSHGf7agDspBYUW26a7gyTwHYtxYTvcXRWyN9M2kqP2ZHxvM9eRa89Lv2PHwY93adz3) [dump](https://solscan.io/tx/34h68vYS1H8JMbzmuB2v5RYEynV1vsdaXJoe3CnySmUHWr88H99JTu8HwiN3v9jvTmryJQDY9JARk83U14BwktWo) |
| 86 | 21 | same | 2 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/3B2J1XJD2TCWkALtJTYABPGrkLYS9oTwRypszKSPYoLAYbYsJVCE3iA4WE17szFXf38sVEHvBHJz5ZJM8iDyZSHk) [dump](https://solscan.io/tx/52h81zsHMCVzSg5vYcmrNpWQpgYB3BEZATPJcMoBb8Mx8Zdv6GTMPNMaJ39pURe4G1hXtZ6qhC7cg35TwsxFnHcN) |
| 87 | 19 | same | 4 | **landx-fra3** of falcon-udp+landx-fra3+nozomi+helius-swqos+bolt+falcon+0slot+glaive | – | – | [buy](https://solscan.io/tx/5Y1E279fgQqwMvbDy4UBd5e1wsFtJYg4FBvwZg6Ujg8EyFJ8h3tSUqCowXwTzq8455NteNoUeaRaTiSWNVVq36P5) [dump](https://solscan.io/tx/2oYLXm4SGsszwi2RfZJGao4w31eX51hPwY2qbHpZBAhHNCJLFCTPvfvDaL1gRbTFnfZfbC85CcGu138Z5tLscWN1) |
| 88 | 44 | same | 3 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/j7itT4jAuwGaSW3FJhzy7ZRLbnmEr3TxKm3J7yLo87TsRKweEqbq8uhfj67WXm7JCZRDb8op2bzW8qiNFD6sqWF) [dump](https://solscan.io/tx/5LZnSccgGuFJVRUqyskhWKmJDPHccNJWdYR6n3ZPoJaSUTu11pXbUQZ6Ax7K4AHfpntzSF6uXNFZNrstYWttSTji) |
| 89 | 82 | same | 4 | **nozomi** of landx-fra3+falcon-udp+0slot+nozomi+staked-rpc+glaive+falcon+helius-swqos | – | – | [buy](https://solscan.io/tx/62ecd1SmFuAkhzcBjvKBYZScp67KUAnCZ7KoxkZtbNPnaCtELZvqZ3JMSvp6pULy9yZaEbnFwWbSLtsyepJQoQ6r) [dump](https://solscan.io/tx/cf3mvdhBe2Etk88iAag9F3pP3bJbB4uaDjaaCKbWh4AQ8VJr42usg4qb2VEpfjMzLLrkTj24RtD66Cu2Unkpfrq) |
| 90 | 39 | same | 2 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2u2vUrXHXyq8iMdh7Wts2Ev6n6qBCiZ8R6ZwT3D5jkDM16Nhk5qBfDN11pE4QTA5h3AfAeBa4xfUUCy34UrMEUr2) [sell](https://solscan.io/tx/2bu3VzxgShBbezRofbgyfiVq31ARDCCvLPhxsUvUHWSXFFNhjANWffPvghNhp394sKSt7oQwAgtXxB7BxPMjaWRz) [dump](https://solscan.io/tx/z1uofpxS54ZKsxnz3Zu3tqFznEMuYXrYT7VmSzrsMQYdHxyPKnwSpPyjEUcFZZ557SnBpSU6PL3kUU1cARB4YDX) |
| 91 | 77 | same | 1 | **landx-fra3** of landx-fra3+falcon-udp+0slot+nozomi+staked-rpc+helius-swqos+bolt+falcon | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2bvYCpKXoQTqVddmRPMPN1CLAmqjmCmih4VDCChAYS1nCnNyFzn5HKwz8qmLiYdR6fhj299VTeQgmVrk4QzTsfZb) [sell](https://solscan.io/tx/25v2zywPsZBb2vJCBADaDyWerbVSaWD6EMvuBW9LEUBws5uAxTYkCPM3Xf3L2zsD7hdNcFWUuQbfNgXDXVJmnSPg) [dump](https://solscan.io/tx/5xquUSE6j4qdJKZc7xCaq9Ge2iWHzCmfrS2nRG7RRhGXaAs8efQVi9uyQznhqFpy8xvkdLpUx7mfEEUQdqSekDti) |
| 92 | 38 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/3VubYzmiQiEcBoj1J8fVxL5CFv3pDhp6kE4tar1mR981PKxy5nyFyPovg5WYKSoaBMuztUBtbJ1wSQrXS4YmVHgk) [sell](https://solscan.io/tx/5NfZaC1fDTsjdV4FQBniAnkxJ1RLmZdzDmRWE8AepaGQDU7TXjCWr7mv8276oM3V1VnT8pkEuGK4qU2AYiS3vCy3) [dump](https://solscan.io/tx/3WEVb2vGw7cCY6LoziQ8kmUPdrof2inLtwohTqksTYf23aCMBdLN2hmA1syFc9b6xCWMz1rfCkztFntA9QCSNFoq) |
| 93 | 37 | +1 | 0 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5hh7S4wLh5so13EhBr2g7u3oVvgzXLab5ye9FH6fbBmEa9NCpJsRLmSaUuTpkPLzFc5eN3bCFZ4chdsYMdkxcd6G) [sell](https://solscan.io/tx/3enUkkTazUZTTWmgLczvBzDhrZesUN5ToY5NVc2nE6FaAEnwoReVEDHsL5M1nkxQshNFWxYrNJMKrrihCcnxcWH7) [dump](https://solscan.io/tx/7sx4vMDrkKkGPWWuR9yvHJttRQ3q1bVa4CTYXmuEPmvrwe6wBx9kisA4Tn1aPncyrCKRKNWpaMdNyQdFpcbdUbm) |
| 94 | 38 | same | 5 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3gKVPLiRp1VeKGfCAB2arDgJ1iDyxzymnJPfcmaGGAzbsFdCVgk8VgFZi8wKZVVpqgyE3NrjyPyCtE5CiLKgQNq) [dump](https://solscan.io/tx/3m86Xb1dCFF6uVubGQK8tFRQCfPPCK3HZCSn1wKnbd9QfjtLUepanarwZ37x9PV54CAw7vcKyMAs9sbwyVAPDGER) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| BAM | 34 | 14 | 41% | -0.1456 | -0.0097 | 5/14 |
| Harmonic | 28 | 14 | 50% | +0.1738 | +0.0129 | 9/14 |
| Jito | 24 | 10 | 42% | +0.1719 | +0.0179 | 6/10 |
| Firedancer | 8 | 6 | 75% | -0.1105 | -0.0182 | 1/6 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 89 | 42 | 47% | +0.0374 | +0.0015 | 19/42 |
| dev list | 5 | 2 | 40% | +0.0523 | +0.0269 | 2/2 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 74 | 32 | 43% | +0.1102 | +0.0041 | 14/32 |
| next block | 19 | 12 | 63% | -0.0201 | -0.0014 | 7/12 |
| 2+ blocks | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 04:00 | 7 | 3 | 43% | -0.0279 | -0.0086 | 2/3 |
| 05:00 | 12 | 5 | 42% | -0.0451 | -0.0083 | 1/5 |
| 06:00 | 8 | 4 | 50% | +0.1429 | +0.0362 | 4/4 |
| 07:00 | 17 | 7 | 41% | -0.0514 | -0.0066 | 2/7 |
| 08:00 | 11 | 6 | 55% | +0.1402 | +0.0238 | 5/6 |
| 09:00 | 11 | 6 | 55% | -0.0483 | -0.0076 | 2/6 |
| 10:00 | 5 | 3 | 60% | +0.0636 | +0.0215 | 1/3 |
| 12:00 | 9 | 4 | 44% | +0.0009 | +0.0009 | 2/4 |
| 13:00 | 2 | 0 | 0% | -0.0010 | – | 0/0 |
| 14:00 | 3 | 2 | 67% | -0.0536 | -0.0266 | 0/2 |
| 15:00 | 9 | 4 | 44% | -0.0305 | -0.0070 | 2/4 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 44 | +0.1149 | +0.0026 | 1.4 s |

## 8. P&L leaders
**Best trades:** 47Me6d +0.0910 (Jito, time-limit, score 0.20); 3To5zz +0.0721 (Harmonic, time-limit, score 0.28); FrMD4E +0.0628 (BAM, time-limit, score -0.55)

**Worst trades:** 5rh8HB -0.0832 (BAM, time-limit, score -0.34); DvbaTz -0.0559 (BAM, time-limit, score -0.61); 2Q1DZt -0.0490 (Jito, time-limit, score 0.22)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `A1vqhA2f` | HarmonicAgave | 5 | 3 | +0.1308 |
| `HbidP4hp` | AgaveBam | 3 | 1 | +0.0618 |
| `7cVfgArC` | JitoLabs | 3 | 2 | +0.0505 |
| `GnC339vk` | JitoLabs | 2 | 2 | +0.0496 |
| `5pPRHnie` | JitoLabs | 10 | 4 | +0.0479 |
| `XkCriyrN` | HarmonicAgave | 1 | 1 | +0.0418 |
| `ACvL73V4` | JitoLabs | 3 | 1 | +0.0415 |
| `7tqeaFKs` | AgaveBam | 2 | 2 | +0.0195 |
| `GoeW4aFK` | HarmonicAgave | 5 | 2 | +0.0088 |
| `Ex1AxFCi` | HarmonicAgave | 1 | 1 | +0.0078 |
| `DrifTrN9` | HarmonicAgave | 5 | 2 | +0.0070 |
| `6TkKqq15` | AgaveBam | 2 | 1 | +0.0040 |
| … |  |  |  |  |
| `9WzPWqKS` | Firedancer | 1 | 0 | -0.0005 |
| `AWcCdYG7` | AgaveBam | 2 | 0 | -0.0010 |
| `GSTampk6` | AgaveBam | 2 | 0 | -0.0010 |
| `EkvdKhUL` | HarmonicAgave | 3 | 2 | -0.0029 |
| `Ninja1sp` | AgaveBam | 1 | 1 | -0.0149 |
| `DDnAqxJV` | JitoLabs | 1 | 1 | -0.0152 |
| `2m1A2WM1` | HarmonicAgave | 5 | 3 | -0.0180 |
| `Aw5wEMXh` | AgaveBam | 4 | 1 | -0.0210 |
| `722RdWmH` | AgaveBam | 3 | 3 | -0.0394 |
| `BUv44cVt` | AgaveBam | 2 | 2 | -0.0670 |
| `22rU5yUm` | AgaveBam | 2 | 1 | -0.0837 |
| `HW4zorvt` | Firedancer | 7 | 6 | -0.1100 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1824 (p25 1444, p75 2508, n 94) |
| Executed-feed lag behind first sighting, ms | 0.7 (p25 0.4, p75 1.1, n 94) |
| Buy sent → our tx seen on the feed, ms | 35.7 (p25 22.3, p75 78.2, n 94) |
| Fills: our buy seen on the feed after the dump, ms | 38 (p25 34, p75 65, n 44) |
| Guard fails: our failed buy seen after the dump, ms | 38 (p25 24, p75 109, n 49) |
| Fills in the dump's own block | 32 of 44 |
| Guard fails in the dump's own block | 42 of 49 |

**Which copy landed (nonce fan-out):** nozomi 37, soyas 10, landx-fra3 10, falcon+falcon-udp 10, glaive 9, 0slot 9, solami 4, helius-swqos 4, staked-rpc 1

**Send-path answers (FAST-ACK lines):** 0slot 94 (median ack 1.3 ms), falcon 91 (median ack 0.8 ms), nozomi 76 (median ack 0.8 ms), helius-swqos 63 (median ack 0.9 ms), glaive 60 (median ack 0.8 ms), bolt 41 (median ack 0.8 ms), staked-rpc 10 (median ack 2.9 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 2.34 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 8yYMhuYo | 27 | 19 |
| HLU8QbLd (41Pr family) | 18 | 17 |
| 8PgC4ngp | 15 | 10 |
| DF7eRXHn | 13 | 12 |
| 7PedQZmc (untipped fast) | 9 | 6 |
| EJX629cp* | 7 | 5 |
| 9mZeEDjX | 7 | 6 |
| 3MHgGwdL | 6 | 5 |
| 9DW4QLas* | 6 | 6 |
| haqq (dip bot) | 6 | 6 |
| ocBBRKb1* | 5 | 4 |
| GEMPyqU1 | 4 | 3 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.6451 |
| Pump fee on buys | 0.1901 (0.0043 per fill) |
| Pump fee on sells (residual) | 0.1982 (0.0045 per fill) |
| Buy tx fees (base + priority) | 0.0222 (0.00051 per fill) |
| Buy tips | 0.0403 (0.0009 per fill) |
| Sell tx fees | 0.0266 (0.00061 per fill) |
| Sell tips | 0.0528 (0.0012 per fill) |
| Failed buys (tx fees) | 0.0253 (50 buys) |
| **Result** | **+0.0896** |

Buy compute used (fills): median 78,404 CU, max 91,908 CU (limit 100k).

## 12. Health checks and red flags
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used) (×2)
- ⚠️ 43 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getSlot: 2 timeouts/transport errors (worst p99 370 ms)
- ⚠️ big loss DvbaTz -0.0559 (time-limit, BAM)
- ⚠️ BjfCpM: landed 4 blocks after the dump
- ⚠️ big loss 5rh8HB -0.0832 (time-limit, BAM)
- ℹ️ One 6001 at instruction 6 (BjfCpM): Lighthouse guard (L2TExMFK…) assertion failed before pump — fee only. It landed 4 blocks after the dump, so probably the slot-deadline assertion (inferred).
- ℹ️ The 'sell issue' lines in older versions of this report were false matches (status lines with 3012 inside a bigger number); the check now needs the bare code.
- ℹ️ Wallet holds only the frozen spam airdrop ByiDNcxM besides SOL (left alone). Nonces healthy at the end: 8 ready, 0 dead.

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Recommended / open:**

- Run 23 (AMS) started 16:11 PKT with the same config, --minutes 330 (until ~21:45).

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r22.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r22.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 2 (restarts appended to the same log, each with its own START BALANCE; every section sums them); refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

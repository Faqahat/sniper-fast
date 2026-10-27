# Frankfurt run 16 — dip bot run report

*Speed shadow run: dip14 with shred fire in SHADOW + clock2 + feed-lag + defer + skip Rakurai; M2 gate; 0.35 SOL, 5-slot hold / no stop; pre-send shadow (2 h)*

> **Verdict:** −0.193 SOL. 39 M2 picks, 13 buys sent, only 3 filled (Az6Arr7o −0.118, 3Acndka7 −0.015, 27eoQv6N −0.055); 10 reverted on the +5% guard (faster bots took the bounce). Shred fire shadow: 0 wrong decisions in 1,207 checks and every phantom (failed) dump skipped, but it covered only 7 of 39 picks (22 dumps never reached us on shreds first, 7 blocked by pending txs) and saved ~1.3 ms median. Feed lag: the executed feed is ~2.2 ms behind the first shred, flat all run; our queue 0.1 ms. Pre-send shadow (paper): 252 windows, 38–40 fills, net −0.68 / −0.39 / −0.23 SOL.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.1930 SOL** (wallet 2.8434 → 2.6504, Δ -0.1930) |
| Started (PKT) | 2026-10-25 15:29:21 |
| Ended (PKT) | 2026-10-25 17:29:21 — time limit / max trades |
| Ran for | 2 h 00 min of 120 min planned |
| First / last buy (PKT) | 15:43:51 / 17:17:43 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 13 → **3 filled**, 10 failed on the +5% guard |
| Fill rate | 23% |
| Wins / losses (fills) | 0 / 3 (win rate 0%) |
| Per filled buy | avg -0.0627, median -0.0548 SOL |
| Fills only / failed buys only | -0.1880 / -0.0051 SOL |
| Best / worst trade | 3Acndk -0.0151 / Az6Arr -0.1180 |
| Fill landing | median 37 ms after the dump (seen on our feed); 3 of 3 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip14 (speed fixes; shred fire logs only) |
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
| limits | max 60 fills, 1 open at a time, 120 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 15**:

| Setting | FRA run 15 | FRA run 16 |
|---|---|---|
| engine build | dip12 (M2 gate + pre-send shadow) | dip14 (speed fixes; shred fire logs only) |
| limits | max 60 fills, 1 open at a time, 540 min, loss cap 0.500 SOL | max 60 fills, 1 open at a time, 120 min, loss cap 0.500 SOL |

- Engine dip12 → dip14: --shred-fire shadow, --clock2, --feed-lag, --defer, --skip-clients Rakurai (trading decisions unchanged).
- 2 h run, 15:29–17:29 PKT.

## 4. Timeline (PKT)
- **15:29:21** engine start #1 (session with 13 buys)
- **16:21:18** big loss: Az6Arr -0.1180 SOL (time-limit)
- **17:15:27** big loss: 27eoQv -0.0548 SOL (time-limit)
- **17:29:21** engine end #1: run end

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 3988 |
| Inside the envelope (age / drop / since-buy / size) | 1712 |
| Picks (score above the threshold) | 39 |
| Skipped | far_leader 20, spacing 6 |
| Buys sent | 13 |
| Filled | 3 |
| Failed on the +5% guard | 10 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 3 of 3 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 15:43:51 | [2EvdxS](https://gmgn.ai/sol/token/2EvdxSo3NTNDiz4ESp9CNp4VMLe4xuT2HY9fZpxZpump) | 0.35 | -0.31 | 6.39 / −20% | 11.7 s | Harmonic `CQdLgw` | guard fail | -0.0005 |
| 2 | 15:48:31 | [EA4Byq](https://gmgn.ai/sol/token/EA4ByqfgdeDZwhAY7Nz6Mhxko5AXWc4MhQWXFTfCsAaj) | 0.35 | 0.25 | 2.83 / −17% | 17.2 s | Harmonic `G3a3iY` | guard fail | -0.0005 |
| 3 | 15:51:43 | [CyaaPF](https://gmgn.ai/sol/token/CyaaPF2FdFTqZyZY6bKNcAMb955C9qDHXbRp2tj8pump) | 0.35 | 0.41 | 4.49 / −16% | 3.0 s | BAM `2Wf9V9` | guard fail | -0.0005 |
| 4 | 16:18:10 | [9gNwPB](https://gmgn.ai/sol/token/9gNwPBUbzYJNFyUUeuCUgcrqPcCUAZjXwS6vSokBpump) | 0.35 | -0.53 | 1.96 / −10% | 2.5 s | Harmonic `shftkx` | guard fail | -0.0005 |
| 5 | 16:20:03 | [9j9Uda](https://gmgn.ai/sol/token/9j9UdaHujVmMgqdVNbw1LitMJfYkptxfp19bDxSCpump) | 0.35 | -1.41 | 2.10 / −7% | 61.7 s | Harmonic `CQdLgw` | guard fail | -0.0005 |
| 6 | 16:21:18 | [Az6Arr](https://gmgn.ai/sol/token/Az6Arr7o4c37NLCWKyfb5ptveqx8sSa14zbufNtSpump) | 0.35 | 0.11 | 1.99 / −9% | 4.2 s | Harmonic `DcTPJq` | filled | **-0.1180** |
| 7 | 16:50:33 | [5wdfrL](https://gmgn.ai/sol/token/5wdfrLNVZYMBTzCUEWWUZYPXNb6pXVdbnYMfo4Ewpump) | 0.35 | -0.29 | 5.33 / −18% | 6.8 s | Jito `HEL1US` | guard fail | -0.0005 |
| 8 | 16:54:52 | [3Acndk](https://gmgn.ai/sol/token/3Acndka76ipSb2bYgEN5YvvuVM1NpgepBZJVtcTWpump) | 0.35 | -0.23 | 3.57 / −14% | 26.9 s | Agave `rsbp8z` | filled | **-0.0151** |
| 9 | 16:59:56 | [8aMcVm](https://gmgn.ai/sol/token/8aMcVmuLb5eJ74Es1xbv1KWBeKsUrp2Wxt4R3BCppump) | 0.35 | 0.24 | 3.16 / −15% | 5.3 s | Jito `ANC1u9` | guard fail | -0.0005 |
| 10 | 17:08:27 | [GxQWPG](https://gmgn.ai/sol/token/GxQWPGMRFnSHeVwii8AHzHKrnsiDryeYDizRdJFMpump) | 0.35 | 0.36 | 4.18 / −17% | 5.1 s | BAM `2gDeeR` | guard fail | -0.0005 |
| 11 | 17:08:58 | [8qM2Sg](https://gmgn.ai/sol/token/8qM2SgJxKtskztnKzHEX1y8AWjwRBXfM3GVZJxq4pump) | 0.35 | 0.50 | 4.05 / −20% | 6.4 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 12 | 17:15:27 | [27eoQv](https://gmgn.ai/sol/token/27eoQv6NziX4taaEPwmox1rjxcwBQXBcBi2yGP9N2vDm) | 0.35 dev | 0.41 | 1.33 / −7% | 1.9 s | Harmonic `Awes4T` | filled | **-0.0548** |
| 13 | 17:17:43 | [SN6NGr](https://gmgn.ai/sol/token/SN6NGrHCwbcwE1XYttYSmypWBgyEAA2L91Du71qFQG3) | 0.35 dev | 0.34 | 8.32 / −35% | 2.5 s | BAM `nebu15` | guard fail | -0.0005 |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 44 | same | 8 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/615nCJtvVi1EeGmrmQuCyMJ9cWLFVTtdjQNq2cpBYL26dzk1wUPcQAfVuEqQANi3Gq8qAwRB4yvRcuXxu3SpnvGL) [dump](https://solscan.io/tx/2YSjSzTsiEa6hw5Ar88F3EhHi1Awp9qxLeauu9QmJaQD3w2CFAbc5ckm9g8gKxMZZ2PPV58c4J3aLNbPC1cZpDaZ) |
| 2 | 33 | same | 1 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/342D1woZXveJEzxBLJqbyaYEuoHokWebBCDey9SJg9Q3AWeD5HaKbWJpoaUbQAMwoGEe29tAvUA5ZBDmCGEknneu) [dump](https://solscan.io/tx/5MzdUma9f1d3QryAHFN7y1R2H8ydcRPrX6EkpG57ZcDC4XnbAPUDfsu3eFEZaQGzwxA1AWSKg9n9QqK7xsmZKgZ4) |
| 3 | 24 | same | 5 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/5dzDd8RQmyhJneuaKVePoExFntL9VqHnvffEEM9kq9XLRvWCfmJBt4JsCZWyXQVtxHc6Jh7WFBkwA1W6GZYaacTb) [dump](https://solscan.io/tx/31YAJQBinsuekDiyqRTPjAdCiYTtj9jwncr13nbr1H6oHnKi3gVjULpujXZ6UaXkVLbZjmDQDTDYWxUhYkHifQqh) |
| 4 | 134 | +1 | 2 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/33d9QHZ9SqnQbMu1K5HrDF5suwwZ2gYw5cTcD8RXm5aLgtNpDqWWp7Zf5h97WRp4zEa8xMKtv6rfPiAbyLLoQskq) [dump](https://solscan.io/tx/3KEGFgTd3W5NmJaG2XV9sNhZvp74rDCNZTBw1dXuoVfhG3DdfaSQXitrCXcsSWh454JnKHE72RteQ3iky9TQzUH4) |
| 5 | 65 | same | 19 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/64crxRZr7Cmt7VreDEPZ9qGknB5ENCnLiHUun23iMc8V9SvPBLJr73i1oSE5p3HXGf8oyYQf7z4gCLS1wawiJ4sN) [dump](https://solscan.io/tx/52y2RD2vVJcvopG6WGrTjkxApDa28sz7KjxALutSdnpsTdJQn9wSjnh3BTBVysgK6WBYieeqokteC5Svo84cXv1T) |
| 6 | 55 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/2qU17EwZwy37mc9db1f1Hvu8rPqiCPpVFSvKjtG4XikVWXnkV4Y21CjuCvFr3Rf9SWH3yvPoz8r1ZLV1Cpvbqn8P) [sell](https://solscan.io/tx/8JY1gZfU6CoPj5F8zjDgmV42s5zKMRQ2aeZRTx38hjZXDeBeiFQG9xizUi9R65YnBufdzLdmS6fixVrnZTgt6KU) [dump](https://solscan.io/tx/2dTEZR38JufKeHHqhDKwqQQRxsXzq6HqjLDLah6fHpAbcqizqNAPmLsXiC8RMM5x5DK49aaErQNWr6BeTqopCWM6) |
| 7 | 41 | same | 3 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/2KWQzBqmv9wtrzB8YUt8cJPY2PFZT1CvAddf9Jk1fiBTgPZ78Etbzt2oWEkhoeWzzHMM1oL3dtYvT35yMZf6D391) [dump](https://solscan.io/tx/5eSryLbLLL3kAGND4pJjDaG4ZZgwMsR3AKH3Kp3ZTC9kq3xh4d8JuuumqiUJde1HSqRJQuThYWSbe38vnd8LTNXo) |
| 8 | 19 | same | 7 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/4kpevGoKZPvBtMCvvXcvTghxzNcDLT8oAUAXBdahQqFaLH2CptmRCWUxiPtK8EsjEnomPpmPPN4oPPWerXkPhdsb) [sell](https://solscan.io/tx/3dMUFz5Taa5BZzLMdiW23m9MYtmCvRjYXKqtenVc9hX8roMMxVLsoPWNMZGwFoz2xn3kp4cWhQzRThKjVCE9edX1) [dump](https://solscan.io/tx/MNvLF6wFCECMGp72PkULbvVSWAErkgm146WkDQeH4ueA5VQZ5bF7yomHJz7kc6WqnEhDk4j4iCHfCvzGvvGuXNT) |
| 9 | 172 | +1 | 6 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/hV32qjH4n5eStbEjffBg4vsndmnVQe6soMcQwKZZxsNRFDQ3CNX5ER1rftJFqwQj4v2cP3jWETosjbo5xj218TL) [dump](https://solscan.io/tx/nhn2rndPuv7g2PmgB4JQ1PJKYRMjDRVo7RiRwbpdRw3U5YzSRSU4g1vxbuUMxrYYcp6KeCiYsqVKwuu9kBBDfhe) |
| 10 | 41 | same | 5 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/2yWCXwbE7bxgNbUjQTFTnhatnHVUZ8os72ametUTKpkSjaAzyBeH7aZSpjpc1LFpvkaVLgLg92WHFdCJPqxp2w5L) [dump](https://solscan.io/tx/2XnVaNDk2AJ2gT5sramspkvhZ4BkhEbKDy5f7Ei495M7WUi8BDbDBt5BxBkynPLdkWrsSMHBemGWYAqj5mJdiTvS) |
| 11 | 46 | same | 4 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/3AjpHf7QLx5HjARPfx8fpx98Lb9idNDsvuYX75GJwi1iXnqHsg1Ac8XhTMjUajPH86toRrq3cZogTKcAeLW8Rucy) [dump](https://solscan.io/tx/3ZPZ1khCtiXmmjAVYBwPfXLX7uTAkkbyigYGFCo89btt3mNTxx4Gb6u7URWd6u9P7R7sj4USZL1sEQcseduTYAry) |
| 12 | 37 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/2fv4BVagoSxAYBUeYdKsKnrKpHxxVjxMFEDeBufg5g7RRRVF7hP6W7dP2s9TaSByMZKkF2dcztmorrRQMjVNhkwm) [sell](https://solscan.io/tx/4vK5mSPEPMwSnbSnCv1GzKdDe7Hff2YGLqqzSsmXAJcpeMnEncC9NVnkumuNk6HATyshDVGPHV5LgDYfdiR4WRp5) [dump](https://solscan.io/tx/3YMBFTroTKkDtj5JXYLHhjLbETkTaye9Fa4VJcaR7YAvJ6uV9Cfi3xDJ1zGPzSJ7tQeD98e6D3EgkkRGe6MMRGjf) |
| 13 | 41 | same | 5 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/66YEZZkwMiJHuDyqc3mhTJPVBkmXQgtF9pWgX63o2KwGZnfjf5kyxcxWE6nCdBfJGfkU5q9UVhBBbdiV6eJvgKHH) [dump](https://solscan.io/tx/2bTmAhnpvJNSV1PbkpBmoLfmwKxAu6rZ2scyfZpZd5L15xP4QLWZFfmbymaw6zZZhZZda28WytybB9jnR4xWgnjp) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Harmonic | 7 | 2 | 29% | -0.1754 | -0.0864 | 0/2 |
| BAM | 3 | 0 | 0% | -0.0015 | – | 0/0 |
| Jito | 2 | 0 | 0% | -0.0010 | – | 0/0 |
| Agave | 1 | 1 | 100% | -0.0151 | -0.0151 | 0/1 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 11 | 2 | 18% | -0.1377 | -0.0666 | 0/2 |
| dev list | 2 | 1 | 50% | -0.0553 | -0.0548 | 0/1 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 11 | 3 | 27% | -0.1920 | -0.0627 | 0/3 |
| next block | 2 | 0 | 0% | -0.0010 | – | 0/0 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 15:00 | 3 | 0 | 0% | -0.0015 | – | 0/0 |
| 16:00 | 6 | 2 | 33% | -0.1352 | -0.0666 | 0/2 |
| 17:00 | 4 | 1 | 25% | -0.0563 | -0.0548 | 0/1 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 3 | -0.1880 | -0.0627 | 1.6 s |

## 8. P&L leaders
**Best trades:** 3Acndk -0.0151 (Agave, time-limit, score -0.23); 27eoQv -0.0548 (Harmonic, time-limit, score 0.41); Az6Arr -0.1180 (Harmonic, time-limit, score 0.11)

**Worst trades:** Az6Arr -0.1180 (Harmonic, time-limit, score 0.11); 27eoQv -0.0548 (Harmonic, time-limit, score 0.41); 3Acndk -0.0151 (Agave, time-limit, score -0.23)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `G3a3iYZK` | HarmonicAgave | 1 | 0 | -0.0005 |
| `2Wf9V9rP` | AgaveBam | 1 | 0 | -0.0005 |
| `shftkxns` | HarmonicAgave | 1 | 0 | -0.0005 |
| `HEL1USMZ` | JitoLabs | 1 | 0 | -0.0005 |
| `ANC1u9sY` | JitoLabs | 1 | 0 | -0.0005 |
| `2gDeeRa3` | AgaveBam | 1 | 0 | -0.0005 |
| `nebu15XQ` | AgaveBam | 1 | 0 | -0.0005 |
| `CQdLgwkm` | HarmonicFiredancer | 2 | 0 | -0.0010 |
| `rsbp8zMH` | Agave | 1 | 1 | -0.0151 |
| `Awes4Tr6` | HarmonicFiredancer | 2 | 1 | -0.0553 |
| `DcTPJqPN` | HarmonicAgave | 1 | 1 | -0.1180 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1490 (p25 1429, p75 2294, n 13) |
| Executed-feed lag behind first sighting, ms | 2.0 (p25 1.1, p75 3.7, n 13) |
| Buy sent → our tx seen on the feed, ms | 37.0 (p25 30.2, p75 52.9, n 13) |
| Fills: our buy seen on the feed after the dump, ms | 37 (p25 19, p75 55, n 3) |
| Guard fails: our failed buy seen after the dump, ms | 42 (p25 41, p75 65, n 10) |
| Fills in the dump's own block | 3 of 3 |
| Guard fails in the dump's own block | 8 of 10 |

**Which copy landed (nonce fan-out):** staked-rpc 9, nozomi 4

**Send-path answers (FAST-ACK lines):** nozomi 13 (median ack 0.3 ms), staked-rpc 13 (median ack 3.7 ms), helius-swqos 11 (median ack 0.5 ms), bolt 4 (median ack 0.3 ms), helius 2 (median ack 0.9 ms), jito-bundle 2 (median ack 1.3 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 5 |
| Guard fails: rival SOL ahead (median) | 3.33 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| DF7eRXHn | 5 | 4 |
| HLU8QbLd (41Pr family) | 3 | 3 |
| Dk2jdQ93 | 3 | 3 |
| haqq (dip bot) | 3 | 3 |
| 3MHgGwdL | 3 | 2 |
| 9HALQh4i | 2 | 2 |
| EprLoV21* | 2 | 2 |
| 5NUgaqxD | 2 | 2 |
| 8PgC4ngp | 2 | 1 |
| 2XyiEK56* | 2 | 2 |
| 8yYMhuYo | 2 | 0 |
| 6n2cCJrr | 2 | 1 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | -0.1540 |
| Pump fee on buys | 0.0130 (0.0043 per fill) |
| Pump fee on sells (residual) | 0.0110 (0.0037 per fill) |
| Buy tx fees (base + priority) | 0.0015 (0.00051 per fill) |
| Buy tips | 0.0030 (0.0010 per fill) |
| Sell tx fees | 0.0018 (0.00060 per fill) |
| Sell tips | 0.0036 (0.0012 per fill) |
| Failed buys (tx fees) | 0.0051 (10 buys) |
| **Result** | **-0.1930** |

Buy compute used (fills): median 78,254 CU, max 78,255 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 3 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ big loss Az6Arr -0.1180 (time-limit, Harmonic)
- ⚠️ big loss 27eoQv -0.0548 (time-limit, Harmonic)
- ⚠️ Fill rate 3/13 (23%): the paying dumps bounced past +5% before we landed.
- ⚠️ Shred feed coverage on FRA is low: 22 of 39 picks' dumps were not seen on shreds before the executed feed, so shred fire would rarely fire.
- ℹ️ Biggest loss Az6Arr7o: the creator and 7 fresh launch wallets sold together during our hold (ops/dip/devsell/DEV_LINK.md). A creator/insider filter loses in the 61 h replay, so none added.

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Done after this run:**

- Dev-link study done (DEV_LINK.md): keep buying creator dumps; no filter.
- Feed lag measured: not our engine (queue 0.1 ms); the ~2.2 ms wait is provider-side.

**Recommended / open:**

- Shred fire: find why the shred feed misses most of our dumps before any live switch.
- VM1 independent verification (agent) running.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r16.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r16.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

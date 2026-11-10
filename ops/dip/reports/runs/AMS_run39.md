# Amsterdam run 39 — dip bot run report

*dip27: lone-whale skip (50 slots, live) + log-only annotations (deeper limit, bad creator, holder clocks) on run 38's config + profit lock 1.0/30%*

> **Verdict:** +0.428 SOL on chain (14.288553 -> 14.716788) in 3 h 13 min (10-30 05:36 -> 08:49 PKT, stopped by the owner to start run 40 on dip28). 88 positions: T2 44 (realized -0.118), re-arm 44 (realized +0.523). Low -0.37 at 07:55 (weak 06-07 h: -0.12 / -0.22 realized), then 08 h +0.5. Lone-whale skip: 13+ skips, none would have filled (paper). Logged rules on live fills (direct, no refills): deeper limit T2-only 7 flags net +0.20 (T2+re-arm 16 flags +0.155); bad creator 8 flags -0.22 (would cost); holder clock (approx) -0.05. Young-token re-arm losses (FRBrHz/EzX2PH age 2) not caught by any filter. dtrzJPj7 holder again on B48ycU (-0.188). End check 0 held.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.4303 SOL** |
| Started (PKT) | 2026-10-30 05:36:07 |
| Ended (PKT) | 2026-10-30 08:49:23 — stopped with Ctrl+C (SIGINT) |
| Ran for | 3 h 13 min |
| First / last buy (PKT) | no buys |
| Server / wallet | cyber-dock (cyberams) / `EgxfYgEb…` |
| Buys sent | 0 → **0 filled**, 0 failed on the +5% guard |
| Fill rate | – |
| Wins / losses (fills) | 0 / 0 |
| Per filled buy | – |
| Fills only / failed buys only | +0.0000 / +0.0000 SOL |
| Reactive bot / pre-send live | +0.0000 / +0.4303 SOL (pre-send: 88 fills, realized +0.4053, rent back +0.1328, failed-attempt fees -0.1078, 41 wins; see section 4b) |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip27 (sha a08ce238; run script md5 d3e6e153) |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.70 SOL |
| dev list | off |
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
| pre-send | LIVE: whale >= 6%, 8 tries/slot, 0.696 SOL, limit x0.88, route helius-ps, caps ? fills / 1.0000 SOL failed-try fees, exit ? |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 0 fills, 1 open at a time, 0 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 27**:

| Setting | AMS run 27 | AMS run 39 |
|---|---|---|
| engine build | dip20 | dip27 (sha a08ce238; run script md5 d3e6e153) |
| size (normal) | 0.35 SOL | 0.70 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.35 SOL | off |
| pre-send | LIVE: whale >= 6%, 4 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 1000 fills / 0.4000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% | LIVE: whale >= 6%, 8 tries/slot, 0.696 SOL, limit x0.88, route helius-ps, caps ? fills / 1.0000 SOL failed-try fees, exit ? |
| limits | max 500 fills, 1 open at a time, 130 min, loss cap 0.500 SOL | max 0 fills, 1 open at a time, 0 min, loss cap 0.500 SOL |

## 4. Timeline (PKT)
- **05:36:07** engine start #1 (session with 0 buys)
- **08:49:23** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 4b. Pre-send live (pre-placed buys) — separate from the reactive bot
Buys pre-sent after a big whale buy, before any dump. **Not included in sections 5–11**, which cover only the reactive dip bot. Realized = the engine's PRESEND LIVE REALIZED records (chain txs of each buy and sell; the buy pays the token-account rent). Rent back = that rent returned when the engine closed each pre-send account after the exit (dip19+; before dip19 the sell closed it and the refund sat inside realized). Failed tries = fees of tries that landed and failed (6042 price, deadline, …). Net = realized + rent back − failed tries.

| Session | Started | Size / fill cap / fee cap | Tries sent | Fills | Wins | Realized | Rent back | Failed tries | Net | Stopped |
|---|---|---|---|---|---|---|---|---|---|---|
| #1 | 10-30 05:36 | 0.70 | 21,619 | 88 | 41 | +0.4053 | +0.1328 | -0.1078 | **+0.4303** | run_stopping |

**Try results (as seen on our feed):** 6042 19,107, deadline 1,696, unseen 460, ata_exists 252, ok 88.

Tries never seen on our feed: 460. If they landed and failed they cost up to 0.0024 SOL in fees that are **not** in the failed-try total above (5,120 lamports each; inferred, the engine does not see them).

**By exit reason:**

| Exit | Fills | Wins | Realized SOL | Per fill | Median hold |
|---|---|---|---|---|---|
| time-ms | 80 | 35 | -0.3635 | -0.0045 | 0.8 s |
| take-profit | 6 | 6 | +1.0952 | +0.1825 | 0.6 s |
| stop-loss | 2 | 0 | -0.3263 | -0.1631 | 0.8 s |

**By leader type (the slot leader where the fill landed):**

| Leader type | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| BAM | 32 | 15 | -0.2497 | -0.0078 |
| Harmonic | 23 | 11 | +0.5855 | +0.0255 |
| Jito | 19 | 8 | +0.0784 | +0.0041 |
| Firedancer | 11 | 4 | -0.0388 | -0.0035 |
| Rakurai | 2 | 2 | +0.0199 | +0.0100 |
| Agave | 1 | 1 | +0.0100 | +0.0100 |

**By hour (PKT):**

| Hour | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| 10-30 05:00 | 5 | 2 | +0.0380 | +0.0076 |
| 10-30 06:00 | 16 | 6 | -0.1146 | -0.0072 |
| 10-30 07:00 | 19 | 8 | -0.2197 | -0.0116 |
| 10-30 08:00 | 48 | 25 | +0.7016 | +0.0146 |

**Best pre-send fills:** Cy8HNQEd +0.2670 (Harmonic, take-profit); G6iyReBP +0.2163 (Jito, take-profit); 5cC6RZee +0.1663 (Harmonic, take-profit)

**Worst pre-send fills:** B48ycUo2 -0.1881 (Jito, stop-loss); BaJUPp1s -0.1470 (BAM, time-ms); FRBrHz8e -0.1382 (BAM, stop-loss)

**End-of-run checks:**

- session #1: END CHECK 84 mint(s) read at confirmed: 0 sold now, 0 empty account(s) closed, 0 held / 0 unreadable (per mint: none 84)

**Every pre-send fill** (time = fill; whale = the trigger buy; P&L = realized, rent back not included):

| # | Time | Token | Whale % / SOL | Slots after whale | Leader | Exit | P&L SOL | Links |
|---|---|---|---|---|---|---|---|---|
| 1 | 05:39:12 | [4NfZyz](https://gmgn.ai/sol/token/4NfZyzrv4Kx281Ly4VMvZ3F4YpN4xym2sAntvtJLpump) | 6.6% / 2.47 | +2 | Jito `3SkE34` | time-ms 0.7 s | **+0.0978** | [buy](https://solscan.io/tx/5rE13Pd7tpvu7Q9Wqa4YSGwEaLnErM7f3YxtJw8KEEX4yJnhBAGCqJqAufq4JWFRx2ABZ2JYPkyqXXZzDL6sTvBz) [sell](https://solscan.io/tx/4Q6RhbQq4iQ1VLLhbFBHaWBrCNVcSqtYMvLdxyrTAc1zH7bNza4qvLypfchPT4fDv6vV6PKMdBBrsGQMoBDUuFdW) [whale](https://solscan.io/tx/4uMR67cgH4ZDRfGCycKyZr3oPzVB6ABiaT5q5FpxDpUfZVJzdMvibxhczf8M9o33SJDBwNBtRayQm8FaLpJn5Zhb) |
| 2 | 05:41:53 | [F94exq](https://gmgn.ai/sol/token/F94exqpfdGBtnEAnxrGJ7CDczAUDZjFSC5qZiHpFpump) | 8.3% / 3.28 | +1 | Firedancer `HW4zor` | time-ms 0.8 s | **-0.0486** | [buy](https://solscan.io/tx/3cRx49K3rPL9uRCiwDkkeJQJWUW7pEYgHM2K9jHAvKQhFN4SwrM5eLtY72bEA8onJbBTcg2YH3cg3S4muU98o69d) [sell](https://solscan.io/tx/4joejRUTMX1EUmx9Ddkb1scBEWXsxrxsUcpxSyrAmnvZQg5p9QVs7mhUFAtwEJfMFz2WhazCRtuBbzmvCYHStkFG) [whale](https://solscan.io/tx/TQfnWUcHruat2NLwmHMffrQfLvJ2cFjBPmm94dXjQAPVR5TchQZuyoMp5fJ6MqmRiKwnjKz6KHvTdk2846TrA5m) |
| 3 | 05:48:00 | [8vMAeq](https://gmgn.ai/sol/token/8vMAeqfTYPRijhRVr28ncaLYUMf6Geib7zVzE8Qypump) | 7.6% / 2.96 | +5 | BAM `DeXsDv` | time-ms 0.7 s | **+0.0025** | [buy](https://solscan.io/tx/636uunUUTASmrRkoKus8NhdVPgYbFhFusQB28RsqjsxMNcARgJyetr6ppA97TPUK3BRmKExuhsJ6kgetgUva5z55) [sell](https://solscan.io/tx/3psm8FxbAKtHoEMTWaVMPmEXAJiWTSriYVfhaLzN7kzMkR6kUa3mVudS1a9QHDqA2UyZfU7MnKDcMq4QfQd5y8pZ) [whale](https://solscan.io/tx/4Vui9pBgoQn5hSo8uSickRfHsSsvjyHvpg8W1uS3QBjt9pPGMsASoDQgUFf1tjnuruc1PtfhQzwstrStH6wyTrM6) |
| 4 | 05:54:36 | [FFAguU](https://gmgn.ai/sol/token/FFAguUpszYCXNoshoRHXwWQmr9MHiSdFH7n4XKGUpump) | – | +15 | BAM `7qGNnX` | time-ms 0.9 s | **-0.0084** | [buy](https://solscan.io/tx/KZ9J8TZbVL8Cc71GyRtYVMo7D5FeHp2paGie5s4yXemvquTxgoiR5bZqNumpVDDiXhrtKTecKT91ptVLKXZdiDh) [sell](https://solscan.io/tx/3uVN1nkUfUJBAXmJjSDer4FpJE7W1W8YMmqtrGjqCHWAkBcxaYBWFp3SdhM4XVr3m9qVeBjFtkDGRDC9pVgHo7Ej) |
| 5 | 05:54:40 | [FFAguU](https://gmgn.ai/sol/token/FFAguUpszYCXNoshoRHXwWQmr9MHiSdFH7n4XKGUpump) | – | +16 | Firedancer `BRAZAt` | time-ms 1.4 s | **-0.0054** | [buy](https://solscan.io/tx/ysHnydQvubu8P2TYHDNJ4yKHUKDTH7J4SWas5kQSFo2aHEXuK2Q7r2iVxkALXwEhwTQTqPRfqmapS5Yfjdzo549) [sell](https://solscan.io/tx/jRPQ8Zj9yTTPrvCTYoMAJWoFQh1vkrRGefiHWqUY1HPAJkergv2m7xpvhrwXB7WPWZgvtjS9wabsyvht3JsMYWy) |
| 6 | 06:07:28 | [BbZGgP](https://gmgn.ai/sol/token/BbZGgPPDkpJ94oNvmqkX15nzLtpQ5W9oBxj7Ye56pump) | 8.1% / 3.46 | +4 | BAM `FoigPJ` | time-ms 0.9 s | **+0.0164** | [buy](https://solscan.io/tx/5J12GNKY1grWmzG8gdPXboDXMksKPs2NRegZ5BZzZffRqc1d6HEH3hX369gtwipV8iqGyoSgDHd3Co9XFghRchHD) [sell](https://solscan.io/tx/45SqHYptjd8RwH1NqcvLBpzgCRYuMnmgmYJm2MLpGaxTfEBLoUJaNAf8AqpK8FhE7RnwYsdii7tvEu1hVQCYHRjN) [whale](https://solscan.io/tx/5gpytygEiqMUSrjT16F5rhVuzNEECytwAgiBrTJVxsMuZPfrYZsvxDjt52kfcdWVyPQdCrixuo9GDCe352TGh3EQ) |
| 7 | 06:07:31 | [BbZGgP](https://gmgn.ai/sol/token/BbZGgPPDkpJ94oNvmqkX15nzLtpQ5W9oBxj7Ye56pump) | – | +15 | Jito `3YVoK8` | time-ms 0.9 s | **+0.0192** | [buy](https://solscan.io/tx/3FESq95BmCriW6h7pxbcQZDFbKdf2oiw8mAx91gRCHoCEHmniEfncaDNSok2LQJGcAWjNfx4wQqcBLAtY6rTdNVP) [sell](https://solscan.io/tx/5i12d8VxCBm3KBwHA8GofvqBPRBkcVGaKGubVpRktHxrpCePpFxoKS7upDH7uMqVgQ1NR9rXSuo9M3kqqaU4bDy9) |
| 8 | 06:10:26 | [4RietM](https://gmgn.ai/sol/token/4RietMqWcbsvSHuoBd9e9GMbvmuP4EGdDY488an6pump) | – | +8 | Harmonic `Fd7btg` | time-ms 1.1 s | **-0.0218** | [buy](https://solscan.io/tx/51GsZqaegz8vULp8HsTMwJVxfxxQshwBaTbyaLsZ65qWdaqzVSr74LrkjJ1j9fUEseZ2Mvbs8Qirdw2TT5cvS89d) [sell](https://solscan.io/tx/VJoGtv4znMHhrrtRyMY6RRBfrLNuESCskPDbbbMuFR5mJt47kxkbZgP1CUzVy1Ricg9CUKHNgweodpFZVc4MKdf) |
| 9 | 06:10:30 | [4RietM](https://gmgn.ai/sol/token/4RietMqWcbsvSHuoBd9e9GMbvmuP4EGdDY488an6pump) | – | +17 | Harmonic `FNKgX9` | time-ms 0.7 s | **-0.0268** | [buy](https://solscan.io/tx/5wpyN6ksUvHQ7JbPqvxdtRBFt56MtUKFLq7b4M5Yfw7fQEmPw2tjCLssG8p7Krn4oZbdHoMuFSUQhexnpCDRvogx) [sell](https://solscan.io/tx/3iXqkHFCViVBqn9yRJkRDgAV387vQ13nw1mpFT3wXHiSuvChtaR6MPDCpgjiszrjCxa7i3B4CzyZrcwUogq1ZPF6) |
| 10 | 06:24:43 | [4Kwak9](https://gmgn.ai/sol/token/4Kwak9bay4Px3cnxWTvXQc3Hx8RYBPjd2BxC8xB5pump) | 7.0% / 2.47 | +2 | Jito `3SkE34` | time-ms 0.8 s | **-0.0208** | [buy](https://solscan.io/tx/5HwLrDmMhWMBWNVxHeaZD4219jsuhqRbMCkT9cShsZh9jC7cdTrq8BFmF9oZMumy5ovn97jY7wjfAhYFiNgRaLtE) [sell](https://solscan.io/tx/5zqtFbL1bngqY2FGbVdLb5vZ9yc68zrBWBdKbpLmDw41G9NwVLS1ZXu7Wrjv5msk1x7Fea2yoPjx7UjZ4s3vrdfg) [whale](https://solscan.io/tx/5ZEHYr4RW15NUsyM5Pjs1J7yzBhX7HX4w82P2j4H77zn1pAa7iEqbfwu9F8sLTd48D5XU7E54rr29sb2SuU8Z8UU) |
| 11 | 06:25:29 | [2kouSX](https://gmgn.ai/sol/token/2kouSXKoD8snV2UR9PhC54Uq1hY7Q1A93pjgbN2Upump) | 7.3% / 1.78 | +2 | Jito `ACvL73` | time-ms 0.7 s | **-0.0206** | [buy](https://solscan.io/tx/2cKTEBW2yD5VtgW1aWXESyEHhyFNCBDJRWtoM12K1jRPq7PbmJjJtD6URGjLagAdwNhVqMyv57t7g3dczYKHKFSJ) [sell](https://solscan.io/tx/3tVD6raTvaLPvgC1pGe3ytDs1VJAJpJ8BFNMWnJXQCWTXMk4f5yZHjeRhhf4bhfLuhBwVkRmYdLwn3zpNyoqrQDr) [whale](https://solscan.io/tx/42yFukqULYYJfrWx5fVBWWAcMcMddZbmowjBfnEDtseLPwKAL4Zijzn3CYhZiHUgqRvo9Yva3d1DdqeDUp6t92EX) |
| 12 | 06:32:48 | [4SCDWR](https://gmgn.ai/sol/token/4SCDWR3WPFopLTvYQhhz5SoQzQW5jNN8buqcJwMtpump) | 11.2% / 5.93 | +2 | BAM `7y5VhV` | time-ms 0.8 s | **-0.0331** | [buy](https://solscan.io/tx/3TmxicC2KRT5nvzvF4AMRQChqfEvYwBYsf7j5yDzM1tCD2vGVBJ4k4p3v3LrnipDUNdkpUSAm3KgzBK1PVythAdj) [sell](https://solscan.io/tx/58dFQBVLAeVhmPMHExUgBDJVYn8nVNmUcXPnwj69H8CB9RPdaJGmXpury275mhsxqPQGQqRB1CE8zooeKcBbyGzY) [whale](https://solscan.io/tx/SSB9MQ11WKoqpwNeDCrdaURcwbeGc1rCqiHje94634DXVr6rqQJ4KyubpY9vrEiZfTe4AVQgUy2cbj9hBJrABEP) |
| 13 | 06:33:22 | [DuupeG](https://gmgn.ai/sol/token/DuupeGMFwoe3xVV5W2FUy3dParzTeDTJoLwj7CZSpump) | 7.5% / 8.15 | +1 | Firedancer `9eGrDo` | time-ms 0.9 s | **-0.0839** | [buy](https://solscan.io/tx/4XVtcQsJsEoJYUob3vWjK3HP8viS1gmECApdTLEDVsNGn5bovUfr6GueJNVEFPJpZT4PGF71FcrZ5ggcXq6GARYk) [sell](https://solscan.io/tx/Cc8rWc2FNTjcKqN2YGy7Dv7CVvoH9a73LC25oX3iVHaWSTRmmLGuw8n7GHYGFq3cJ94oRgbBVPFfPNZujhWZdHC) [whale](https://solscan.io/tx/5QgKVSiWVeNWpBVfhkBBbgBhgYgPaLjDH1gEMCb46wFUhbUvdHTeyVjqE4Qq66fKybcaouPgAbNvHXfCXqiKHNyb) |
| 14 | 06:38:09 | [CTgGx9](https://gmgn.ai/sol/token/CTgGx9cYNVNMSahTdY3YmFZPQh4ZYrjMVHjTC1UDpump) | 8.3% / 2.96 | +9 | BAM `Aw5wEM` | time-ms 0.7 s | **+0.0088** | [buy](https://solscan.io/tx/4nNAy3TdQvxNbRFgSdTU6CosHJyBwhNQryWJmoj7NohhtCqrWiJkUnTAwNVbJXS985wC3gFE6dyG6yVjYPt4bjtt) [sell](https://solscan.io/tx/2ApM6TECktKAs9oVeCXWTgFAn6gPAwdCYrN9BkamZinP8QzP7XD1DrL6DnJF75fH3reTuxjW32HQHYfZYmcxdeVE) [whale](https://solscan.io/tx/GnCZMdBnhXDLAkS2VQrL5cWfFApHbcYTTcnLAkLqXLguUTpvdQAZVDk3qw2Hn9LdumdKAGvdVnFLMvYJPDCyqnb) |
| 15 | 06:41:40 | [CuWL9E](https://gmgn.ai/sol/token/CuWL9E7fboEEhCaiM4mEttR7TL8nri6WmbKmBfUhpump) | 11.1% / 3.67 | +1 | Firedancer `HW4zor` | time-ms 0.9 s | **-0.0382** | [buy](https://solscan.io/tx/2F6hAxkvaXBQo3NXFyhmidMPsLGq3axQKsBNr8YWxu8chBy5Q5SvwPhWDFuaUD1hwFQNnfzCc61War9kMY4Thmnf) [sell](https://solscan.io/tx/QFwbNaBX1vMuL3ntHwaMbNoGwUzQrpAmhnerzuwnGiTHrZUXCzDK61JtrgcYCT6XoacmX9nZreXmsn8uyLzd7KB) [whale](https://solscan.io/tx/58bQWGY4LXJ3Yxjvc1sv6Q9XLTVXdC26q7VcCSCMHhmHeu9ci9GKuDvPTrbkPFSL9W3XaG3qsCQGmLPCQfr4yT8y) |
| 16 | 06:42:46 | [ETaP6x](https://gmgn.ai/sol/token/ETaP6x8RYG6iKc7t7FuuNFAeER3CF6pYvHH8ZMekpump) | 6.3% / 2.47 | +2 | Firedancer `9eGrDo` | time-ms 0.9 s | **+0.0088** | [buy](https://solscan.io/tx/2qRojzhNsQYJU9Nb2CoSJKVCHKyd8Uq62vHpndD9rcj8F9wNx1yHKCCCpGE45mVBnQgq9Sb51BujDNLSmuRoBdRX) [sell](https://solscan.io/tx/3ynXwAyhMg1Mu3LkDFkKmv4MeuestzMExR7mCmZUWXB7zkJAf6iLaEzmY18awuR4dHpomUouu1Y4DePGmYEKZFER) [whale](https://solscan.io/tx/5p4eeMP24VDwJP16M2J1cwtRZzG72jk8ZgLXTv2j2Qf1eLdzMUKKPyBjgxaMdy7JkRHwZMA1H38bDhTnhvaesvRd) |
| 17 | 06:46:07 | [EqCYuQ](https://gmgn.ai/sol/token/EqCYuQZyB5u8aAWyDKyGa6GsDa4A7GJMhYTsnB4pump) | 6.3% / 2.52 | +2 | Firedancer `BbCQMW` | time-ms 0.8 s | **-0.0252** | [buy](https://solscan.io/tx/Gu9Xs49Zd5TRsAE4ffnepJbHx1Y7duAzYaMJSrDEshA3UquQjWF5cW7fsxGwNtDtEAPcrXzW4NyBY5fP1RK8zfo) [sell](https://solscan.io/tx/2VF77bVKZHowAnMArWE58TrQzh1ASfXtYrECpPzDKq5seHVZdpEMTSKn1MLjLQCTdAgVt6mum54KZwNru6S5LU63) [whale](https://solscan.io/tx/2w1D2LZSp2m4E9bLKm5n5fwA7vz7AeqGNok4ayAc8hEri56TD8e6fR9ztQSLtKFjCBhKKR8oTjzkYrkD2QR5Wadq) |
| 18 | 06:47:27 | [DY2TDi](https://gmgn.ai/sol/token/DY2TDizs7yCWMt3tS33VpkSb6DZ8BTs6N3mEZMuSpump) | – | +20 | Jito `E1r4Ps` | time-ms 0.7 s | **-0.0417** | [buy](https://solscan.io/tx/5PVv2LEYjqUvM1HijZfPwaK7pmnA3Sg23KVqVRNJtHS7RGeYRyKFSyYuAFUQQQqcQTnz4uWTKvU6PsstdRRh3Z43) [sell](https://solscan.io/tx/4ukrbiSuJ66ZCPUt8VSeLcq93DuzPnJ6bvk9vy1yHaaZ2tr1p4s3QTkuNJQS8xR3LnSDuMAJSBrinzm5C4D21Yke) |
| 19 | 06:53:03 | [3JxMrE](https://gmgn.ai/sol/token/3JxMrE7vwnZHTdHtxSHknDk5GKDnvD2QV1PhjuM9pump) | 18.9% / 9.88 | +4 | Harmonic `JUPiTE` | time-ms 0.9 s | **-0.0206** | [buy](https://solscan.io/tx/4yMDYSLZe66nY85g2jMDA8vUARKmDDeLBbN8LweJfVjQ4Cj79Fz2GYzvRvChW47TcMPLhoLq9B29RzV9kgtbafKp) [sell](https://solscan.io/tx/4KynDzK24erHK2Fsx3mXfyTB3cVPt4pBULr7w6m8Vrnm9ugDgTnxtTH3vA3PHk5r3kNaVgvZZz8R9XgNxjUigHKh) [whale](https://solscan.io/tx/5cDXcKymrFhB64VFtxFjDuuMwDVt62vboqobDtSh4xoWTbrZ7SABBtAiDgGxsY6hSVwR71JcEsaMgpUs3KZWabbU) |
| 20 | 06:53:21 | [2dosW2](https://gmgn.ai/sol/token/2dosW29wP56qE1LBjaeKn7pbWkj2k3NakVUzSErPpump) | 6.8% / 6.16 | +5 | Rakurai `ana2y2` | time-ms 0.8 s | **+0.0081** | [buy](https://solscan.io/tx/2i2iPyuw2Z6mXdBkyS3fo88AJHCLDLXpNfCpVomqW3nA3qYSe2c7MBzvs2x2bDTsif9YFUboX7Mnbas3wg6LJjFu) [sell](https://solscan.io/tx/2VcJzHsSQjCzCnKo4x2f1W4suxaWZZDS2pTRE3NpbK6vSpFNrxXk7h2RU7gMPmLPXh4VXBzzRxPNocEEk47JrWdU) [whale](https://solscan.io/tx/4JgvruxDaz83SG7UN1Nt99eMVMer2oCDAdpTPh2qFQPTbrYgLeKnLrXF9psBWddAqLTgUQcenHjnVPvVHKLZ61pu) |
| 21 | 06:53:54 | [54Umjw](https://gmgn.ai/sol/token/54UmjwjSGZqRdKhp65VUiQqf54BNRM7Cm9QBUUdEdown) | – | +4 | Harmonic `GoeW4a` | take-profit 0.6 s | **+0.1566** | [buy](https://solscan.io/tx/3iEMuXEapZyc2i7QhBExh2TSrMErJTqNQhJxjYiddofvgC8xRkdkwT4AUQnGBgn1GvVi9nA5Q6NoSCtoD2K7mKMz) [sell](https://solscan.io/tx/4wCMTCJrXcuSyyMnnwVSdpLteRhw1V9Nwe7sDCnFCwPurJiCRoKYW5CMs36nLK5Q2LN16QSHzyR2ztg82ahDvrBT) |
| 22 | 07:01:41 | [EVyZXj](https://gmgn.ai/sol/token/EVyZXj9PC8q6rrPji6u3iZmcDQLAWU9fMVB1KqC9pump) | – | +13 | Jito `GnC339` | time-ms 0.8 s | **-0.0196** | [buy](https://solscan.io/tx/41JKF2vHsnY5nWs1RCt59m8oq4r7dEpXeRQJEBoZuVS35y5dPhPT9eaHvRQy7Mz1j6DsLdL6thxcZPERDmHxoWV2) [sell](https://solscan.io/tx/5kqVfAf8QJ3fmeCHJonAtMwB4tL3xDb3BMqBpjq5axnvWYfQcFcqg7Bx5cgc1aUwyFDoigBwmMz727xK5vdwZ7mM) |
| 23 | 07:11:01 | [3FCUPN](https://gmgn.ai/sol/token/3FCUPNnur4cjQ8R4oQM1g1N69oaeCec8AxsoxxMdpump) | 11.1% / 6.91 | +4 | BAM `DRpbCB` | time-ms 0.9 s | **+0.0989** | [buy](https://solscan.io/tx/9kVBzav26EXZCx3ExVi7iw99F4EDBnmpvUiqpfKE6RPyjQuyHLGe3uzt55VNXu86HQgw3dqfnF7CJRRNARxRvox) [sell](https://solscan.io/tx/2emEGqJTZC5SyGgCuJQn6C5tTTVJ5TvhaUZEMBYQBoh4wmvSKNXe6gD5u5PyyHmzRCpzmFRNiRDk1VaT9YX43Evy) [whale](https://solscan.io/tx/3aSb1na9T8rrHwUZ3p7D9VPPnXMhs3QFaXVVHrhczHcBavAmERCJ9yqsSyq1B3GpN2nWg8qY2VkcuMEWtPehNBSB) |
| 24 | 07:15:13 | [H1pnp2](https://gmgn.ai/sol/token/H1pnp2hTgaVB4wbih6WrqYDhZEKBKg7a69rQExFBpump) | 10.2% / 3.46 | +6 | BAM `qZMH9G` | time-ms 0.6 s | **+0.0690** | [buy](https://solscan.io/tx/5zYPAdXbmWfFK2K78QHYuHLo9FGzevFToCEJacUqn4ToDcK27pEZr8mETpajwUBpaBG8ptPvoPMwoW79gCACUQTU) [sell](https://solscan.io/tx/8vcBnwaKAaQagkh6ebNQ7cuBieStBokN9a3iRfSyNstgFCv53N47qkU8cvQXYiXSc4YCRqZ7FoWnCAh8b198Et7) [whale](https://solscan.io/tx/31Tttgd1tjkZL3hSaC5jJPDS4MuaB2xWPdgy5ZRY5k4oZ85YgYaLoXnLzA97aCouWJMYazh9Gc5B9G7GccY6kiox) |
| 25 | 07:15:20 | [251NNn](https://gmgn.ai/sol/token/251NNnUnkYrj7771Ed4g4BZAWrnmazb1mrFYLEtypump) | 6.4% / 2.96 | +8 | BAM `2zykwz` | time-ms 0.8 s | **-0.1203** | [buy](https://solscan.io/tx/3vTjuidYaBvBgW8QiL5U5TNeNfYXnYcEUdGoc4xKEoULDFJ9RK1FYiHvEbg56dURBq1oRuCaNYZJwY9DLKRKGr8U) [sell](https://solscan.io/tx/7KtU8Tfzhf6V7y3Fo5URWVMhNnS6cu7GaxMxGdaUvaRbd1kRb1CAYees8f6oCquKE9JENmQiVnww65YQkbEEF4B) [whale](https://solscan.io/tx/e7zDtpMAWhNhNCbnwGVMpHkYybkNaC5jUpWbWUPoDBrJDTHGL1nWfHsWRSSv9kXGwhMZ54FBubN5pygLm3tqTyz) |
| 26 | 07:15:46 | [CCZKHh](https://gmgn.ai/sol/token/CCZKHhwLcznV1LQaBLEBJKYVrMwETrrnB5SFDaVEpaid) | – | +13 | BAM `2Wf9V9` | time-ms 0.9 s | **-0.0195** | [buy](https://solscan.io/tx/3XtB7BmchsWWna9XroxfSm8k1VjvkkTJGMaWEPoA7VB7V7MSM5UJ8CRR4SFWWwpTnYugWozz2AHJfLgx1vz1BFjY) [sell](https://solscan.io/tx/3PHsEKJ8JYVQMk5AoqziBHdPqe9FB8FhoaYSmiN99CgcuwJ8YDdozMNqz9q7mrFHqVHNAAqXaLRwb7yS4zH3vmtg) |
| 27 | 07:18:44 | [3ZbR47](https://gmgn.ai/sol/token/3ZbR47pDC3CHg84afhRWaFMrHZWJ8jbCkG4VgoFjpump) | 7.3% / 2.96 | +4 | BAM `PAWsME` | time-ms 0.6 s | **+0.0230** | [buy](https://solscan.io/tx/3giBdwDFY8UTjemEZ21dB2Zso5wUoR2KBFZmaYy9j8oXGUN4SGduGBRbnS95DDcAWB4E9KixopWCC1Z9bc8SiqPp) [sell](https://solscan.io/tx/3jf3gSjxayyP77uJccoy3FPNZ18c51jdtgP6dtpoQMQg2NfoYRxfgeB6YhERRydFaevgoV8W9ViQULiv6NrBpZ6K) [whale](https://solscan.io/tx/2YpeJogjacxYR9dgnswUXp6KGZFCjUYDJJXTkPiRumtMG4AjvYfMAH5pXnawYEAC9Gth7Za1dRQVSd1ekNzrcXXX) |
| 28 | 07:19:21 | [8WWJJK](https://gmgn.ai/sol/token/8WWJJKmzx8F6tebzMURKV4zbarXbCVLxknBwrTjABWNA) | – | +3 | Jito `EUcJwf` | time-ms 0.8 s | **-0.0249** | [buy](https://solscan.io/tx/3TmjFRYpLEf4ZdsyiWj9oXmJYvVKJGYkZmroDPt3FipJUqockXve8sfFktwWFbXQmsMNekSuq12YU9vcPXV1QCSz) [sell](https://solscan.io/tx/5JEdEymSz2dQgnxas45UC2CmhhFpyAvYt15q5gdmsNCWJwPR9s2PYwAhQEHBScHHdcaxNpi7SgeDSaz8VkhjiXC) |
| 29 | 07:21:50 | [FRBrHz](https://gmgn.ai/sol/token/FRBrHz8eJUWPRtcbuhHSiqgvfnXaUjLnQTjvn4aZpump) | – | +3 | BAM `ECZx4D` | stop-loss 0.7 s | **-0.1382** | [buy](https://solscan.io/tx/4kDcrnCKcRcEfH5YHc4rbK3efQMtT5MdhNUSy8UMzi1wdwaJ11GHr3oXeBsMD3kY1gQsHxDr4xehjwEh5w9HgfYD) [sell](https://solscan.io/tx/5igePuAPCXkKfDEjRcgU7e11u8qQxH62MfoVXwD77gfCdbzCGcTZ7UDWN8iSM4y9bmSe6TiBo9c4UmmbMKbo7GZQ) |
| 30 | 07:23:04 | [pRLPRw](https://gmgn.ai/sol/token/pRLPRwnupVH7S7zWSQdg1v3cnoTCAB564NLA2q8pump) | – | +22 | Harmonic `JUPiTE` | time-ms 0.8 s | **-0.0291** | [buy](https://solscan.io/tx/4E7gPKAbkEfcZJvnLJK4TLqxTsvwmMwRJFTaS9Gdy3fHaye2tXR3YncW5c7xY86jUkC8dLvBSfQx3Y7pUtfF1U6z) [sell](https://solscan.io/tx/3x3DfU4mfB9kP869jcnDdMeQvWmrbrUznLhFSa45X1GKqixmq1tC3Pjy6wStUCA88LFYRPYaxms9sftiD9VHyuR2) |
| 31 | 07:24:11 | [EzX2PH](https://gmgn.ai/sol/token/EzX2PHGf5uNWaFP6gDjUgiq2ZHH9p7m9SypuAXxepump) | – | +7 | BAM `GzDfKK` | time-ms 0.9 s | **-0.0524** | [buy](https://solscan.io/tx/4MsmKtsFCehtxHKL8RMaPqF2Dmph1E9LJzBQrYFpDAbg5mYyR2S3JfwiufzbFXU6BTpH7yZxZXBWwpqM2Ens8rY2) [sell](https://solscan.io/tx/634Y6bmQ1jktqWEkYLVRbEgkUn5QvKFmqqAv38RmaGNfhx8LFfHzHWgtQ6yokkSeAeWjKi1aNNYGQQTPxp1oZRxS) |
| 32 | 07:27:52 | [Cy8HNQ](https://gmgn.ai/sol/token/Cy8HNQEdDwFjuRYM1vSmazTX9RdaUZuFN33eHCKCpump) | 14.0% / 5.93 | +2 | Harmonic `6ptuwW` | take-profit 0.6 s | **+0.2670** | [buy](https://solscan.io/tx/r51URHSEhFWNbN1HRjSaJomffuMQH624A5pFymDSBTrnzBcC93k5cHgeLDJ8V2jR4GpuqZiX8DSXRMsnNCMkEtB) [sell](https://solscan.io/tx/4SvYNMWXPQc1Gffp2ev1Wxbz3TnwwzF5Z4ydn6vYNv72jvwH5Rno5xqM7EwSUN5HjzLh3ZUEwnb4u4V1Z6w9H4WJ) [whale](https://solscan.io/tx/4adPy37iAM2H5ivmWqt2cxuFwDLL579BwGpTq7Jwg6cYAPro6q6C23N82akWQncj8CasMWdYDy6Dk4CvEFTaPJuM) |
| 33 | 07:31:08 | [B48ycU](https://gmgn.ai/sol/token/B48ycUo2fHcUZ9BuX2rBBzJknfnoPNaU1cgKgWvKTtD6) | 7.0% / 2.96 | +3 | Jito `C8Bey3` | stop-loss 0.8 s | **-0.1881** | [buy](https://solscan.io/tx/5EjMKjstiRWuetxq4YGgP6pCYBnTk8cuWx9bJUqncpqPaT2iM6c58CtT6Sq1teg5cqMkWMbpUGPp7bdrD8WUFDW6) [sell](https://solscan.io/tx/5Ku6Qj1ZSZ8ePgiK8eBh61V1iaL9Gop1ehRT16vWomWvRPP57smsCxujLdc9FZtkEjYaAe2uyHdaBDCug5Vod8CB) [whale](https://solscan.io/tx/3QtrXFJUpSvJEcwR3bb5WNDsDm8uaYh8gkrsPfqbtx1vTEk6PsK2iydKtxSgEqxd8TWFgSSjRknH21fENuXfwaQZ) |
| 34 | 07:37:19 | [BaJUPp](https://gmgn.ai/sol/token/BaJUPp1s5q4qsxSugxnYHtetr8wU2C7JJtf8dJLnpump) | 9.0% / 2.81 | +1 | BAM `5ejbTA` | time-ms 0.9 s | **-0.1470** | [buy](https://solscan.io/tx/2817joZF75EqDPx6tAP8CT7em9GKjoVbeXxn58DLmu362VZfEHf5ii242QUPgyUPeWHFy1ajXrTCTormNuRaAzzg) [sell](https://solscan.io/tx/4aRuYfGt7i2YnNnC8sWxd6ucNmdU6rtjFDbLQczNA9WECQbucrFxzkvzGLF4z36wRwHoDiKF3o1cdufJap6t1Vsu) [whale](https://solscan.io/tx/3Xm61ULcF11M7qnwG419gokVApwwVrvdGM4Xzo14arRfZ9QyS1tTT8X16B2CHdthQK77UJseJUpiiYFiTtg8a1ru) |
| 35 | 07:39:37 | [ELgYQU](https://gmgn.ai/sol/token/ELgYQUv3bqVofLJyhghFS1bCW4RwmuUPmks44Ewq8Hfi) | – | +14 | Harmonic `Awes4T` | time-ms 0.8 s | **+0.0312** | [buy](https://solscan.io/tx/5rSj9LhnmbKe3PSSUvu2qKEzEU5Np6yHHUoLNaeQd3Yijnm5wwcAoXT4EzJdwDWi1wLnKvyD2cUaEPpNMjxcw3QE) [sell](https://solscan.io/tx/3zp6wakzC9q7F6WraKZQNBvQyQiHHTQNDjLR8e9BDEFkYJhk7XWihcF8W44WP4pXLsQX3KkQoJQs7p7j8GvVx5pT) |
| 36 | 07:43:46 | [xWnmtb](https://gmgn.ai/sol/token/xWnmtbPcJCMmh4QU4cqSUTR75bsJGkMqEj5jwCepump) | – | +14 | BAM `Av8EnY` | time-ms 0.9 s | **-0.0338** | [buy](https://solscan.io/tx/39gKPKsmXpKnSxhR15Lp2fzggPCjQWZ7L4bgF7VsHGUYKjvDi8gXziBzSwiGxy9E3NXeF59WNNXtyV91u76NCUxa) [sell](https://solscan.io/tx/22vPwTD5v6HULk6WyCcJZm2dkAxQouV4xv2tjt1jEhfrmUXmg6pxsYfL2hUvpwnBMNvV5hC4KDJL9eFuHS5sg4MW) |
| 37 | 07:46:03 | [GCQYS6](https://gmgn.ai/sol/token/GCQYS67ARxXC2GHfN6uMCPLaG1MMzzVM6P6A2tqmpump) | 6.7% / 2.47 | +2 | Agave `5Us18h` | time-ms 0.9 s | **+0.0100** | [buy](https://solscan.io/tx/2wpeR6h8TSLqPXgwxkhSgJPRj4FNrqXFq6vuHWxyYMVVQwx4azxSCNRFTvmY79U96RHeNsoR9mZ1bjrLRc6mp9E1) [sell](https://solscan.io/tx/5wyShAskJ1jM41ABwsBbs8dv3eSUZeJVhFy1jx8THswQP6fR7rDYbXEqaVfk8arLJaLYvmPuQB58pcGFkMtkHRcb) [whale](https://solscan.io/tx/3AL9qZnMQaF6CEffvP74PdL8Ghodcfd7zDY8MtQXvqj3mbtc5r16fDvBEFNX8gd2my7tBu6AvSc9LMYSpq3xTyyy) |
| 38 | 07:51:38 | [CKegRm](https://gmgn.ai/sol/token/CKegRmJvD8TjuDVmCHsUjvzBLFYY8LRb3HJgrnKjpump) | 7.8% / 3.91 | +0 | BAM `Va1idL` | time-ms 0.8 s | **+0.0022** | [buy](https://solscan.io/tx/4ov7PQEDfe8RGmUG44KHixRSDs6nna7c9QU7ikXnK2duMNHxxVg7mH83mMR5EiXUbDsXocjtB3YKyW4vjXwYQcUo) [sell](https://solscan.io/tx/5JZbLFMEdTxrT4cVP3NseQuS6TCqNmWC7eM9ekow85oU4gQ1F6s1AtBZCwkwmjCXP4q1uiMG2Za28eedtiyr1Zy7) [whale](https://solscan.io/tx/3fRrUpQiFHF9GXzMMDeEiV62syhnLSmcV9x6rr75DJWKBPT8sV7Dj4Sf2fbka8ExuXqoyUaV39rfuieZPxNui2LC) |
| 39 | 07:55:10 | [1zLLK9](https://gmgn.ai/sol/token/1zLLK9x2mXo8So3TFuYptAEP87ukx2DFTTdMwwZpump) | – | +6 | BAM `GBQ2Gv` | time-ms 0.8 s | **-0.0119** | [buy](https://solscan.io/tx/3LD55kjfD4yFjTbowg4r5sZqzhEWi13QMEo7nhiQSdWeLFYrEXQz8nVx28w5N5twWPLiRWgsSRBQA8pB18cDyivh) [sell](https://solscan.io/tx/5gdeEgurfT3aTpbxoEUUdCDkpezbrGNkBwvmqSsWdUPpavdYM7MujKr27ZdGpsDjYGFPWPPh46QZxAnW3ye1o88m) |
| 40 | 07:56:43 | [BhwRkf](https://gmgn.ai/sol/token/BhwRkfD5PZTTASn7Psy9b4unR7zwpuxw3BwQTDHNpump) | 6.5% / 3.95 | +3 | BAM `2GUnfx` | time-ms 0.6 s | **+0.0638** | [buy](https://solscan.io/tx/gwExLCm3ZhoUzfJdfsVTmKYzyF4qSZRCyorjcqry9XW1TiEh3wSQRszUVhuoDU2LxGhDQSQeizmWDMHcM2SNa7G) [sell](https://solscan.io/tx/2fBEtJQJUFXRvRahi8N1c2ABvtZ1RBmUT661cXedv7SDz3chuNLdutYjwHbv8n8zkMogneEbVV81ZMMbWGV2b6n7) [whale](https://solscan.io/tx/3A7cMfZxS5Wi4R1tH9vUgFsgLJ9vFUhi7byqqqAW1EVugWgN3df6mjsYhzKiyX4G81rBnMg6xreEpawhCc3rEPdi) |
| 41 | 08:00:50 | [5Xy3q9](https://gmgn.ai/sol/token/5Xy3q9oVnLFcb1yoy15KeKLTVkArJon3yGnFGWECpump) | – | +8 | BAM `Fc6NNd` | time-ms 0.8 s | **+0.0303** | [buy](https://solscan.io/tx/wAR64bRp1Xv82ijxvyj9hut6j94n9Ep4bsGwbc2MprG5YuXW5b3yqqcNXV8U1xQo4h55y95HTSrCdxHZsmkELaq) [sell](https://solscan.io/tx/jhVsr8HEUvp8DqpNpwH41nh5LBwJCywTCJQMhfDJjmVRD3bEs5F4W2ZJ96zqu4dFwxThpq2TNsCXDuRDzyw77H6) |
| 42 | 08:01:15 | [DP7BUL](https://gmgn.ai/sol/token/DP7BULA9SuRaYnbh6EYEyD5UP3Sa7Ynm4Y4JMKs1pump) | – | +16 | BAM `BUv44c` | time-ms 1.0 s | **-0.0164** | [buy](https://solscan.io/tx/4rQfoRkP4mtdPfnLuKRCPFiHdMwdA11Z6XbniMxU3h1m9m4A1TT2u2fmNhsSDdW5jbB1za87jABcwF1Eviwz12uB) [sell](https://solscan.io/tx/3sWemnDivWAHsg17MtJyQvv9romqUbjJBGagLvo9aZNVny8rh771maCk1D1sPCWS68iCmxWq1ymHjZQ3aZc9JVxL) |
| 43 | 08:02:08 | [G2cfwc](https://gmgn.ai/sol/token/G2cfwcua3ytbWYZnM9Eh1WuaJ9A4fVrEcS5XZVQapump) | – | +10 | Jito `8gDfqH` | time-ms 0.7 s | **+0.0426** | [buy](https://solscan.io/tx/3HWUBfgq7qA1fhCxiBuYs8Jn4YEKk5tgk3gxSp6fyyU9fqFWybcQ2VVUyaA8ZrSsfUoGtryPzpRTxd7i5akkfGrC) [sell](https://solscan.io/tx/2HLeAtNENvzTr22vcniQvWacoeipaZykfzNzRcMTTmuftTvjChzZmrBzGJyw9rcv1CpqN1MxghTMtfnvUoeAUG5S) |
| 44 | 08:02:45 | [2P2zUa](https://gmgn.ai/sol/token/2P2zUaYNFSf54yEjwkK3ShVMF8HJnjmnjB9s2RaMpump) | – | +6 | Harmonic `Fd7btg` | time-ms 0.7 s | **-0.0196** | [buy](https://solscan.io/tx/wu9s8o9pqj9rSKTvGC2Gucz554X7B5g6PEs53mUHcVrepwL4hwsJMq9XAGCiBZ5YfzdvG5koETYHVg8Ptreh4WT) [sell](https://solscan.io/tx/3F3PnJLdJco6zJnsZGVfJo8AbYo8u8ibAkj6cSaUjQn1d8FfY23fYAFH9Xvr8ZtadhFoV4w6vSFFASL5K25wdNZS) |
| 45 | 08:04:47 | [BhwRkf](https://gmgn.ai/sol/token/BhwRkfD5PZTTASn7Psy9b4unR7zwpuxw3BwQTDHNpump) | 7.1% / 2.47 | +2 | Firedancer `9eGrDo` | time-ms 0.9 s | **+0.0583** | [buy](https://solscan.io/tx/5jLgCK9DWKs8rTYYV5UrJ8KeRZChd6tDdC2sEM9C4gHbpY5e2LXXHotW6SmMo7F3GYSAVwPgytdfoFzYEByosVVQ) [sell](https://solscan.io/tx/vyRg9itmCdnoVGcpTg3TQs4J8xwzDSK8o9cvhaRkV32fQEGnovAhQRiNTjLPS4zaiGzTfbcNwrVCZLgvtbMNRad) [whale](https://solscan.io/tx/3eAFurNquu1RA1mfmqM37D4Ej3imM67JpKV5Akq2D3DPHN7xcc1Ji5Hhdm1vBZ8x5bvGiLUUSTc8581RNWw1CAsw) |
| 46 | 08:05:42 | [2pSKbA](https://gmgn.ai/sol/token/2pSKbAqyJvT4cy7RmK3fHqyJAtWbwq77BQkWgKiCpump) | 12.2% / 4.94 | +3 | Firedancer `JD549H` | time-ms 0.9 s | **-0.0168** | [buy](https://solscan.io/tx/5PfLjUrBYUmbdLZ7oh7a8RUdXUWuJeFBsFEaeufTxwuFsSeetFBJoCbJ8AZ8MNgrcfJH64QukgnQFKdqi3RwwvpW) [sell](https://solscan.io/tx/jieknLdRPTLtXCkoPg18fgdHkdosNir2jYdCDpo1T7UcxFyGwuiqud1ykK9vPVneGM1neuWgqkWFW5KawkPcgJ2) [whale](https://solscan.io/tx/4Yc1mfpceQsHP2ACRFDWDMszVhFgcHYUSbDQ9dozd58xgpX7GpttYTFVvaeQwKM5ppRipvCMUnWNXxzKKZHtx67q) |
| 47 | 08:06:58 | [AXum2C](https://gmgn.ai/sol/token/AXum2CMZWww6FafRUvQpcrXJT8VqF1LHmLuQYUEFpump) | – | +8 | Firedancer `DNVZMS` | time-ms 0.8 s | **-0.0006** | [buy](https://solscan.io/tx/5umodi5tHjyHNdHeEPwt35uFg1pYg5fJnMkewTwwyXi3bPEJHwiYnxpTQm8W2uJJPivsCRqyQ3PgwzbUgxzFfQmZ) [sell](https://solscan.io/tx/2MQWt5EhGHRRnZNvozjzpxUjtgRq6LYSRPmx1i6zy3vu3w9rHnVFCDo2VcNzcqvTDDb4GPzSJWSBa65fkrKqudkV) |
| 48 | 08:11:39 | [EbJzpU](https://gmgn.ai/sol/token/EbJzpUKAqWzwwjdc7twB1bzPs7igmrKJdpD3m52Npump) | 7.4% / 2.93 | +5 | Harmonic `87CcUx` | time-ms 0.8 s | **+0.0206** | [buy](https://solscan.io/tx/DXhYNprRDoTytninSZoLupn9aDgXLrBwfEiJHKFzBNstEKdzJVEMsNpKRM26wd8JU2KUmyYQrvhv9NhhutuagdQ) [sell](https://solscan.io/tx/64qiUvd4TQPyJb1gcMWzx5gzi1J7u8jh3xmFeGMXVV1JqwvBZH6avuFHT17mTHL61o84dVsUyMggZ6fWHJ1YHAvE) [whale](https://solscan.io/tx/2nersY879KGpDK46Ed4fBvqFLSZ2BM393YPrGMbsZc6ECLNRXgvAJwnGpMFRZxgg1MKSztLPmfy7AeJ5DL5XMmev) |
| 49 | 08:13:14 | [3R2f4s](https://gmgn.ai/sol/token/3R2f4s5aeCLFQuWNKSvJSRXXfMT4wAB8ZFbQosxTpump) | 12.3% / 5.78 | +7 | Jito `E1r4Ps` | time-ms 0.8 s | **-0.0509** | [buy](https://solscan.io/tx/2cD69CpdQbBvuTxANaBByfs1qQxTjUSp2t4tZvU8cbyLg6T9LM1MYGWkCBVHy6orN7GZpNDLzjX1rY9UgzR9Ubk9) [sell](https://solscan.io/tx/5tbArVEkFyBfsY2zEu4QEiZorRBpKfZpaBiUAz9E4WrmsqMGv948hSy33B2fCfkoBXbYhvJehCfkZhZpbDvBcRsN) [whale](https://solscan.io/tx/YqWvyTCYpbMgP8ZthVJHZ3ZjRqypUfZrKNCcaP7eJ6KnpTVgUKB7yADi2PvKKoZcGQsv4AVhaqMJHTVnJj91U8n) |
| 50 | 08:13:18 | [AdH3Wb](https://gmgn.ai/sol/token/AdH3WbnttetfCp4jTKjdmNowghPSAhLTGYbJTRjEpump) | – | +5 | Rakurai `ana2y2` | time-ms 0.8 s | **+0.0118** | [buy](https://solscan.io/tx/4cQKu7Z9t3kZF3H6kijqWD55B7gLLn4ufKT2jKyPnkySCUbVDHMGvxTaFNe14MESBrVu7F2hN15FmUpxZARteuC2) [sell](https://solscan.io/tx/rP6sCYDFXbu8RXMkSP98LD3uuMw2f6VicMP2izbAP3CcBm9cMycsuy6SHB2FWXpnMLTQCw9DotCzn6xGPt5t1c5) |
| 51 | 08:13:22 | [2yYgKb](https://gmgn.ai/sol/token/2yYgKbuAusfkzgjSKRJa6Tmmb63vzKatj332XkPra9Gn) | – | +7 | Jito `C8Bey3` | time-ms 0.9 s | **-0.0196** | [buy](https://solscan.io/tx/3dCgRyNEUXUpUsAKyPLKJtAimBJzc2qnf3tRwXugFf4NQ6GhkQkmwsUVBpAdA8kqHizUUPNrF6R5kzBB5CyLQRcy) [sell](https://solscan.io/tx/4Ff7ukBqqkF4FeRUBf46ruDE7vuj8evngpmY7xTPe8EYX4dwJi31ABrYzMRR42Dg27ak5hqCXmqrhDMwmhjcC3jK) |
| 52 | 08:13:28 | [3WnZg3](https://gmgn.ai/sol/token/3WnZg3NgSR11dhRE68HqFoFSf5asTqXXi2FNMDCVpump) | – | +3 | Harmonic `shftkx` | time-ms 0.9 s | **-0.0620** | [buy](https://solscan.io/tx/3MvwxWCHD2PcQEmJuAn1aCEEYuEHynVsLoZg9BGK5y98FBsvUXiYRBk1NYqxX1v1KRtQW5D3MZV5K61qkSuYa6qb) [sell](https://solscan.io/tx/ThUf8EfNGnjF9wVcyfRpHqk1xTqzX6aBvcd6zDf5topT8fvc6MJ1QiTWzXgH37RYbZq4xxVUsZXFXrwqmQFK4CM) |
| 53 | 08:13:42 | [Jm326L](https://gmgn.ai/sol/token/Jm326Ldm4QhePqKTqkWeASqZXmfq9gW6atMvxeWpump) | – | +7 | Jito `5pPRHn` | time-ms 1.2 s | **+0.1491** | [buy](https://solscan.io/tx/PaQ9mNz9839d27urmYRYKoYRt3w2NVUrexN5Z2JLQ7BZBwS2LbhMhosQ4kC5ubDUDsVXZfMRwkgPSpJJFUFJ2R6) [sell](https://solscan.io/tx/23grMsnJSGY3rY99Z4dUvSNASKpKHr2FqaDdryK2hMHSqA21ooaGQY3bFatKBKJTdUYKYdN6jM4KTDHa2CwNd7nC) |
| 54 | 08:13:47 | [FbjZDL](https://gmgn.ai/sol/token/FbjZDLrwXbSwcWq6kgKehLu7JHbzZPiokiwPKgzoQJq1) | – | +8 | Harmonic `DrifTr` | time-ms 0.8 s | **-0.0230** | [buy](https://solscan.io/tx/54ZYK2WfgnJ1QukjPHAKVeWNbfTmobAi4UxtCtFFuVMiKBhtoxqddKjrTqCpvQDcZ2hZsRq5KgLemhahmPz7kEEG) [sell](https://solscan.io/tx/4HAnrTgPUYssMVsbxjkQ7cVLsSakxA1UWhtJtkv7qkKEWHGgiaeWcQbxcABQarpVTcsZhuvEdFMSShgvQF4KvG8F) |
| 55 | 08:13:51 | [Hir7KU](https://gmgn.ai/sol/token/Hir7KU7KFF7xrPoYyQCdjPwM7y7zdXP78Xh3C43Apump) | – | +16 | BAM `BNtHBL` | time-ms 1.0 s | **-0.0196** | [buy](https://solscan.io/tx/ee5UZVHHdeJ2Jm7YEJEpeDmpjQerrv1NTCJ9j8iLL8pL4MDvCqyumvHMgJ3YD63QzeCzfp5j8xfiLZyna4MQAFZ) [sell](https://solscan.io/tx/WBztQQ2HaHbKXiRworZuD1udgGG988k8TQfJfSrdhQw53gqBf4NCT4vxCmw1dLsoPeDP4NHs1MUzw4xWCqEbJ6W) |
| 56 | 08:14:11 | [5cC6RZ](https://gmgn.ai/sol/token/5cC6RZeeAA46CoUvwFAqw1ZRVk7mfsCe8U17PcsqSCm6) | 7.7% / 4.94 | +3 | Harmonic `Fd7btg` | take-profit 0.7 s | **+0.1663** | [buy](https://solscan.io/tx/n5Vs6m5SDsBM7EwWDXrNmV6A6VmvYHhuEdCRUA5FB5qYDq9LV5gwAkobjTsZDZKbGdJQApgVnPKuD1EVm2NrR5i) [sell](https://solscan.io/tx/3C7TaN9T9fUhdNjW6eq2q2y4wvCatJiR1CBrk74J91ZZkomindDBQLdg2jgxNACzW5jbiFhSjkPLE8Fm6rYyip2i) [whale](https://solscan.io/tx/2a54VxUfgDTk6QZRRgt7aafDD8WoNuc4cVeD18j1869Koj9vy5XTEsaRNN6oViRWve7qFUEZjjfmepuXw35xEWoP) |
| 57 | 08:14:48 | [61xnVr](https://gmgn.ai/sol/token/61xnVrSX8mCrEg3XecTnEvtRKSqixRuLP23noP23pump) | – | +7 | BAM `74Xkp2` | time-ms 0.8 s | **+0.0692** | [buy](https://solscan.io/tx/U2VZAq6mfQqXNnBSzkHTEpXWsG1jLuMSe6L6yP1ALgWmFkuLqfz5vVLJrZMKe5M7poELqCncNbQnECRTHm69HfW) [sell](https://solscan.io/tx/3eBtDYFUeBSRt1cAfk6aKcycZaNa5j1LcaeTQLxbvaEVd5J7ua4GBKjBV5nLbX7LgAX524SBWzj7ioBMV5SchmkE) |
| 58 | 08:15:28 | [GtC6yB](https://gmgn.ai/sol/token/GtC6yB1UteSLQKYsRpm5ytxsVmKsW7qodLGYvoNKgdoW) | – | +5 | Jito `HEL1US` | time-ms 0.8 s | **+0.0193** | [buy](https://solscan.io/tx/2uaV3UZeahiXPnb6rj4HV7dXhcBkv79qsqRQPvQ5iXXACCNVPXyLttxFFgkChZonmvWJNXeBe766u3JUicivv7D2) [sell](https://solscan.io/tx/LCiCfHs7ZHPhdzEXDYVWYE4Vx87wKeAmu4kNAxFuML6xk1LGJFxeb1okHqehiUEC3kJQDdiEh3t23XH4aYuLzMd) |
| 59 | 08:15:45 | [DknJJ4](https://gmgn.ai/sol/token/DknJJ4mM5apdKBcvYYg8ojURVBkLB9bSZWzn31mwpump) | – | +3 | BAM `GzDfKK` | time-ms 0.8 s | **+0.0257** | [buy](https://solscan.io/tx/63SmuMHxr3EUtW6cm6tJfYbUy3YH5SGjPHwBbTZrTd2o4nqsCdYbzykTnZjggA7RF9HU9wnYwxZDMj9MtufeNWzq) [sell](https://solscan.io/tx/5RzCfc6eCfEXLMnXq9FH3Nhjfy43uu9YMgsqrjvvyCWCJpBsWBK5u5N1ysNvovSaFjibwxZ2vpAhviacEAzWDWT6) |
| 60 | 08:17:42 | [sq7Ku8](https://gmgn.ai/sol/token/sq7Ku83WZR5ZeqSfyjZpTKWv6Eg9YUaKaic2zSrpump) | – | +7 | BAM `HSDTxf` | time-ms 0.9 s | **-0.0196** | [buy](https://solscan.io/tx/2Q1V6pgtAhLzKceerPc69dHbVZYYnoEjg6v5hVSB9PgH82qgs159CwPQUBQxJ6YXG1aHGLBPNnQd5S5z3VnqA78F) [sell](https://solscan.io/tx/3HyNBq8L4U2nxuVvK9t1MYxGbEAr4vuyxDjpTGfkqppsWKceh7e2dvfyNgc5Kd65azjrmWmDAc6Xbwi9QAXLuqR9) |
| 61 | 08:18:57 | [AoM7GQ](https://gmgn.ai/sol/token/AoM7GQUAeTB9vJbsMm5icrcNYcytvSTywqMJDVPFpump) | 8.9% / 5.93 | +2 | BAM `HaLanf` | time-ms 0.9 s | **-0.1359** | [buy](https://solscan.io/tx/5snRwBBCA2bMt1D6nPs8YujGQhfBuCqvNBEy8sMVK2rJYcKDcUsVKE8WAJmcnfw5Mku46yvnFn7eRcCxDKNDpdw2) [sell](https://solscan.io/tx/aWkMjc7acscZWt5TQTue3nGAnszhKBx3miAr5gYg6Yx6hPYnKmhq69LwJYbN3j4dfWAWHAm5WcFAR4WfU3UqDmj) [whale](https://solscan.io/tx/Th6axdYqe59JBKJLv3X1hZVKTBME6rdAZVy6j26bMF5S3ZnPgjXeDLw3ctHEpbhPTwAdYh5GU22tQPveirVZzDf) |
| 62 | 08:19:34 | [3D2GJE](https://gmgn.ai/sol/token/3D2GJEpL6DT2dmsHaRZovJWH1AmAFmoYGNjH9K3Spump) | 8.4% / 3.95 | +2 | Harmonic `DcTPJq` | time-ms 0.8 s | **-0.0203** | [buy](https://solscan.io/tx/5JaE3aDnmK6WZ5G3GeYXpR6ZZ5FG8aoQCpwzLrrF7w4s3ZcXfUSZZ6M72khFbgbkELUNhcJBfoToZwjUbUJWes5S) [sell](https://solscan.io/tx/x8ZmStMZTbLKk8wUr47L7Uc9gHHKXADp9raxvKqJkbqr8zjnb3utWwdkoekeUKoQLkmaLrPx4x73TQMb9MnBCGr) [whale](https://solscan.io/tx/4Zjk1oaBzTWipP4ofe6WD7qTy9gZ5cE8h4Re7h986AjMc49Q5GUB1UDZ9MWZFLcky8vGBjaiYSxN3ckxws9epeHF) |
| 63 | 08:20:52 | [GZKZU2](https://gmgn.ai/sol/token/GZKZU2jmMxtYcXD819tahr3vtr3yVsuijJJp8d6Fpump) | – | +11 | Firedancer `DNVZMS` | time-ms 0.8 s | **+0.0647** | [buy](https://solscan.io/tx/3Ae1kpB915khABg2yNsEWmHtggev1mMaroJTKNgFkUW7A42npc35YeMeT3MDSC4HXXnhUpZHbocNZ9Ghwfi9qEmY) [sell](https://solscan.io/tx/JADusZnCZ78XAreLsm83WzmpkRJv4wscZdaEpAHjdgVDpan2xLaNuhiGnp7LNxppDVXc2aFva3xCuyh7ihaQaC6) |
| 64 | 08:20:54 | [CKHrmc](https://gmgn.ai/sol/token/CKHrmcAYmMrM8jxJV9ytTYTEsMmCwhiSMuymRvLfUdgW) | – | +7 | BAM `6y7V8d` | time-ms 0.8 s | **-0.0377** | [buy](https://solscan.io/tx/SJ8enja5PZghDYxPJXYsuVMKNZUADxKZvWW5TwMT7GZjhaNFBUbDZ9FNmm8rU3hfJwZxg7hLYE6VTr3n7v1aUgS) [sell](https://solscan.io/tx/3tHW8bA4SeEsdHwUegGurdh4q6kFYAnWqHbYM5dV8zavu18WPSbxGfcdZ7PwGHjXi4okpZM3sKJf8J5VLG52RLfr) |
| 65 | 08:21:51 | [5UfL7w](https://gmgn.ai/sol/token/5UfL7wK6R24nJsrFQFS5UndfYErBS5pBasGdGY7Me6F3) | – | +7 | BAM `6y7V8d` | take-profit 0.6 s | **+0.1555** | [buy](https://solscan.io/tx/54mRY7YX2e74NsashxN2LJXDKXQSU6mUehKGDYtp7GZ5dA5Euks9n3BYVSZTveUCv6A5ZRgXURdPCUzUbbzAqK6k) [sell](https://solscan.io/tx/2UJ6q8xZhFoQLcwdFy7ae85qe5aPyMftXd8QxPE5wFVPgA9FShW1cA9Z3zdCbFqzV9w7SDJrJpFJr8mKCDNpYjb9) |
| 66 | 08:22:53 | [HwuTuN](https://gmgn.ai/sol/token/HwuTuNUafj1ZY15SPAzxH2MtTDv3SdAq98kvd2kbuY7U) | – | +3 | Jito `E1r4Ps` | time-ms 0.9 s | **-0.1033** | [buy](https://solscan.io/tx/nNTviDS3MHy7yw87uW3KLoPfbmVZLxwMJy4MPNaugZJA4knsrri9YpfKxdC7XSKwRTz8brxXKerJSbEvCQoA866) [sell](https://solscan.io/tx/mrZefeCaYDAR9Ss4NQGrH6PfH8VqNRfgqdf5VFe4H6fC9riDUF4FnAjH4EwtS7aWTARKpmettYsX36ELxdPSfCn) |
| 67 | 08:22:55 | [7UeJrt](https://gmgn.ai/sol/token/7UeJrte4LhFcLcW2APjzb5eVbNhRe9vvBxBQYNsotTEC) | – | +7 | Harmonic `2mMGsb` | time-ms 0.7 s | **-0.0027** | [buy](https://solscan.io/tx/YdYLQp3VE3PeDsca6mwQ3DwxAyyzsy1shn48HkudV8JDLt5Wbm8vmnusxbeFo2K9Wsops47p795FdsXkMWfi7Ww) [sell](https://solscan.io/tx/2QDioGfu9RUjoFJFNriYwGzmhpnZhNUbff2B5ni3dtrogYbbXFgVbzAZHku35uDKx6cAt47cR2yW8tyVNw79DRsm) |
| 68 | 08:23:04 | [J7q2vZ](https://gmgn.ai/sol/token/J7q2vZiFuQA9BXoMGXpX8dQGtJs8vxCJ4bD22L1Npump) | 11.8% / 4.94 | +1 | Jito `E1r4Ps` | time-ms 0.8 s | **+0.0166** | [buy](https://solscan.io/tx/4pyVYnPbBer1t6FTw2YVS6bEymtD95hShP3QwozjyeYZ3qmvS2ZvmGgbqVvM8PXV4DiAs3jqv6eMqb9BuxFYWXHq) [sell](https://solscan.io/tx/mvf7NbX2Aiv4qwwL9YtiXzFtoND1K4yPjND6ri28SjEEdGvqiHwnNQHhXrxyh4f4Po6NEBeBQjt9KbAVYCGj4Ve) [whale](https://solscan.io/tx/ygyUPUFtFd4eqCC4F7PTr4MEQc5LLTpMxSeHvXhNBC1e6tZiaQ3CJEaBXB8tMMyw8VereciUCdhW1zVdKfootoW) |
| 69 | 08:23:32 | [G6iyRe](https://gmgn.ai/sol/token/G6iyReBP1Du4TghGfykQsSACqYA4DtC6tFET7Rvpump) | – | +13 | Jito `2Df1aL` | take-profit 0.7 s | **+0.2163** | [buy](https://solscan.io/tx/R9UytRUPrvxg5hJZFe7QrP5TUJt8aeXc4DkUtQGAwqsC2BbxE1YnMs8m61dxdJcQEYC3RtMwDEUzVJcNDc34mbt) [sell](https://solscan.io/tx/4BPvEAPyfVa7mFXex7PhUVk5nBfEciRDzrz9VY1R3Kgs7Fo6tA5XKJ6fSEJWX9D4vsKX5rPDH2wFxW6ac7UyaTkR) |
| 70 | 08:23:53 | [h5VjZa](https://gmgn.ai/sol/token/h5VjZaJybu9qe8yzdxkwGEkfys4K9TrRqshrw5bpump) | 6.3% / 2.00 | +4 | BAM `HnfPZD` | time-ms 0.8 s | **-0.0279** | [buy](https://solscan.io/tx/54gCEztEwqzQoPcmGmHcWJ5HATJQNU7rxr5Msokh6z7ZxnYEVrMzWC2duF4j7hXABKTEJgZNiDcnLtMSAXbfXYFn) [sell](https://solscan.io/tx/5Ye6mzY3D1Zy38L1vKKiCTSgEdhz1A8oEbSZTcTCpWJT6ujCJuMyKV4cBb1qDVRmCd3YmGT1FU2k6bip9MMV2WGg) [whale](https://solscan.io/tx/3qwTdqu5TGNK5JVWrjNSj9sHxGgKWb2dnRFwhBwoLqCuWADtwdKYohFcHCqosdsJcTHE8VNzRAbF7hQmYojEaAMB) |
| 71 | 08:25:00 | [G6szyR](https://gmgn.ai/sol/token/G6szyRqd2swEzistaTckbbaj3KBcuyCshgu9FHx5RHQC) | 6.5% / 3.95 | +2 | Harmonic `AbvfvR` | time-ms 0.7 s | **-0.0114** | [buy](https://solscan.io/tx/4fvTkZDaywkJPdbep4e9ZfBnYVkSxpk1vsmYofVdXdWezhmPGRz9FDYABC4wzEnWw23e6otq4eXMYu61XC8nw2sp) [sell](https://solscan.io/tx/56Wxtv6A8eazy1dycArTyGDdmiCsQVHWvJnpfBc7mgDHQXUQ3zfsEbmp4ebmy3gYRB9ZQJZ6JnyNCMfzBbo39yCB) [whale](https://solscan.io/tx/5rZCCkXpSngbucwkqA2NWXijgPMZUsFsXvWAPknPBVQFCdDNcePCzarFmARUeEPXejgekSq6nNCWeKK1Kuxhw55y) |
| 72 | 08:25:03 | [G6szyR](https://gmgn.ai/sol/token/G6szyRqd2swEzistaTckbbaj3KBcuyCshgu9FHx5RHQC) | – | +12 | Harmonic `5ZqveV` | time-ms 1.0 s | **+0.0330** | [buy](https://solscan.io/tx/49PMGxSGemaYxyaFrjvArDZcdoC2AyAZeBtgxZaedqoGZjuWCbwbv5BNzh5ioZgd1hnqCVnHDVZvFVGHdyGQgc6H) [sell](https://solscan.io/tx/4Hbf7e3e2GsDJ1M5PiLSUD4ZpVYmkzydVhqXDcrBcNJdxc6q7k7ZHgsrrHiy2pVHs11yNR4EpCQFapuyBwANJpnW) |
| 73 | 08:25:30 | [FVYvYd](https://gmgn.ai/sol/token/FVYvYdMywetysc3qaxfdDANxYJi3GRQvP14C9M3epump) | – | +3 | Harmonic `Awes4T` | time-ms 0.7 s | **+0.0009** | [buy](https://solscan.io/tx/57SUHnGxRP1oVGvaW6B3Fxjk4qKKGWe9Z1w485tMTtpk7i8JxjavQC54rvhTfTEd4xfVkJhdNRtJL8i7hY1gby8D) [sell](https://solscan.io/tx/3BezLm4dH9xyho9WzaHWsdRYv52NzSGk6WcibrejE41B5yu5KwFXLAWc9XGddmpt7Jg4hYNCto6xru6Ka6BTqaFP) |
| 74 | 08:26:34 | [6zRCLK](https://gmgn.ai/sol/token/6zRCLKyX8YVSU62EonzRAuzfxMnZL4ktLny7MtBMpump) | – | +13 | BAM `7MTjmt` | time-ms 1.0 s | **+0.0581** | [buy](https://solscan.io/tx/EUy9BxymeDBzYuLSrnHZb5SqEkfGoVFgJkq7ABDivFBzmS7GRiBcazpePXZCH5X3M64gV1AHDs9eTxaERtfNLng) [sell](https://solscan.io/tx/4MNKYf9LQe2DT2xBWFbkvd7cVmasbZ98Hriwta6xMRb7GyBVhUoafNuKMhbvjif3riFpwW8jDeX1kKafzYUAQzSF) |
| 75 | 08:27:14 | [3ZUxWh](https://gmgn.ai/sol/token/3ZUxWhg19xr12gz5arzTwhdXKErnwvpnzsWs9D4Ppump) | 9.4% / 3.95 | +3 | Jito `EvnRmn` | time-ms 0.9 s | **-0.0193** | [buy](https://solscan.io/tx/4RCXRyb7SA7p7cXuLVQx5EH4YjXJnE4FRhd6LrvQo8Fu3NzWYzifiYDNZjJZw6HQkxaBdeksd21WkX7cE1dHS8zw) [sell](https://solscan.io/tx/3WSzDFykePYvfskzWtNDVevFjrvvNbahbCseBpzxCqS9yQoomxykFeHPwBZT1TDdeXj76pZBDBrfG3H6bDByzLMp) [whale](https://solscan.io/tx/3AimCTXncnfoGrovARHzxhezJVhLCGFdnS97Tbde3qaL23U4mLSmXoS35xAiN4Yp74MvC5XaDMBzSzK9ZzkCroco) |
| 76 | 08:27:49 | [7XH74z](https://gmgn.ai/sol/token/7XH74zMkFnitsx2FgYYu1s2aaW9GkeC2woDkq4gXpump) | 6.5% / 2.47 | +10 | Harmonic `9UM8wQ` | time-ms 0.8 s | **+0.0026** | [buy](https://solscan.io/tx/5oQ1tK1ty9MjDuSDTsbQtFfeRotZS8dQpkAJV7cCzisdKNo4T6Gg3nX6udvfVCxWyCKtbGELaxWDx7EnXdoXpeg9) [sell](https://solscan.io/tx/eqaz6EbWsnWUKEkdfiYATby8QEEC2gLj7sSyua4yNVunkxabTK7KcnBXDJcEXdtxnpovB3vQtNJTS7k9cDGWAqp) [whale](https://solscan.io/tx/3mTtyTPrnBuGoyCYyQQsuouFH1Hw8baaUSJfcXJWsjVpXydZmKCSwPm6mRk6QqJFwi86LMhTWRVJUCq1DRLwnCrQ) |
| 77 | 08:28:03 | [Sfxk5m](https://gmgn.ai/sol/token/Sfxk5mj85MddHJHuPUq1kp85E675ns7f5Qc44JYpump) | 8.7% / 6.78 | +2 | Firedancer `BbCQMW` | time-ms 1.1 s | **+0.0479** | [buy](https://solscan.io/tx/55k4my374qyU6s7BXkmbhPqneR5rLzzD6f7PNeJQeprv6iVZB74vng5aM1stV97DsKXjXKg41CtWR6BstEDLTcGp) [sell](https://solscan.io/tx/5FByeYhfL57zPZzfyC5LSVoxu2Y1ydpoQUcGWN4R4kRycywCNYFWxm6x3QKrmW9Zs9BCzxBehfVftj1U1eZX2G89) [whale](https://solscan.io/tx/wwcv3F5aDPGQCXLUB5jw9EFaYFGbsnKtHQQ12yz9XLubn54vFaU8WTRN8S4MefBM6f8FT8ms7JGHkXw3yHEmBgZ) |
| 78 | 08:28:19 | [Gsux7P](https://gmgn.ai/sol/token/Gsux7PXxKm2qoL16zAMhWPy4iXPDsJSwX11ez9rpmAdX) | – | +8 | Harmonic `5ZqveV` | time-ms 0.8 s | **-0.0196** | [buy](https://solscan.io/tx/23gws2PY6VBwDDnw39vdsv9Yf3RRXjb45BZYxbbmVTmFD9iDA5B6E59Ah4CtbX84dH8vJBQEwrKp1RQZvdmH8epQ) [sell](https://solscan.io/tx/5YDEtqhV3uqCKBb1d8ropYoZywxWiWcoZBcnTRyYj12eJWcj2X6e8J2S4jF5v1aTNvasF6EW5qdeT5XBjsFgSFsi) |
| 79 | 08:29:29 | [A8xbJa](https://gmgn.ai/sol/token/A8xbJaPvKgVTcRZYR99AbzifvnAazF4RwhKwz7DZVFkV) | 6.1% / 2.96 | +2 | BAM `3JotfS` | time-ms 0.8 s | **-0.0881** | [buy](https://solscan.io/tx/FfgfCCJrGEhLGRe5kbi1x43WRf7fuWZuyM3wRyVKdieMxzkXZ2XwdzcLspqs48p74veTgxDYBpBrX5yNbFcYqoE) [sell](https://solscan.io/tx/5J2iaKJ4qVeU1Dvg63njTaRzaXjAm78YSeS8dunPsRzsTbRenGLYuQt8RUFVp7vSqsWWYzcp7f3pZ5hHtToVAA9F) [whale](https://solscan.io/tx/4Y61LvahuHuj8fp1rN1Snmxw8QFwgNbLGmzByafSzQUZxjyzWgZ9JGLfKs4Ntuvf6tdoUefPmzWfuWihoh6M4uuQ) |
| 80 | 08:30:38 | [BsprDd](https://gmgn.ai/sol/token/BsprDdSa2t2gApGSSQzaVyCE8CNuTjc3hnBdUTKgpump) | 6.5% / 5.12 | +10 | BAM `parafi` | time-ms 0.7 s | **+0.0320** | [buy](https://solscan.io/tx/3ZFDusTaYFqumrrrx1zDq6ecPw6qFU9ugCBh4UFCWtnR6BZ6KTUGp72CootZkCsKSF9yJejkR6C29sfpWfqHtvGy) [sell](https://solscan.io/tx/5bhdjQTgm3xCqGuSLfSZaa91GY1F4pPAJFw1peQamwSs9voErB7KCmCS2jMNbujsrH8hzvSQgq5c8ZELFQiPqyyr) [whale](https://solscan.io/tx/47nMzpHqRKGDRMq1jot2KhZy2e51JzrGHFdePLXRs8xfnu3NYWjqyERu2TXm2bss6wqbBD25agaQ4ECV8ttmZEZD) |
| 81 | 08:32:11 | [G6szyR](https://gmgn.ai/sol/token/G6szyRqd2swEzistaTckbbaj3KBcuyCshgu9FHx5RHQC) | 7.6% / 2.96 | +3 | Harmonic `shftkx` | time-ms 0.7 s | **+0.0267** | [buy](https://solscan.io/tx/3nAncmmR5a12coyxg7kFoERFTvxTYfKqSZKwdmJUbD7bcYWcxKwMX6X2xyJU71v7LuguVzMjfi2osHV5PggUTDwy) [sell](https://solscan.io/tx/4qc5YuALayLrXVu3A69HBrSiWTH8ZhtNSQKvtByqQJvtjFzGhKgkqepSux4u5WieBhFeC7828JHauFtGSHBT3RNo) [whale](https://solscan.io/tx/64t2P3zdb6iq6aBQ574aSk78DrQXBNPtFpZ2NsTWotz3hYrEGkhXTyZEsYs2Cj9Nfgjxas1Ewt6uh7xkH2479WrR) |
| 82 | 08:34:19 | [24ErE2](https://gmgn.ai/sol/token/24ErE2suMB8S9A69kWXngWtTA3RD7dCXgtBwkNRApump) | – | +18 | BAM `DRpbCB` | time-ms 0.9 s | **+0.0616** | [buy](https://solscan.io/tx/5VKrtqJTHP2DvjUL2eZnyg7ykXTftYr6CseD4qjqPMFZYEZ1rHYbS3HKdrN1o8Ak9vJ8gRELELhDgJWkHNCaGvmJ) [sell](https://solscan.io/tx/fDpUPnfzQScLJQD6HGJKfA6eVQozwLMxE6MyZJCTsCweiCxGE2Qn6TDDrWsohfakexnWTEKKjLq5mxCqaQjpXdA) |
| 83 | 08:34:55 | [46E5qa](https://gmgn.ai/sol/token/46E5qabUELaEs17kmbm8TzyrkguN5XXbf6RP6pZStxQm) | 6.4% / 2.96 | +4 | Jito `HEL1US` | time-ms 0.7 s | **-0.0207** | [buy](https://solscan.io/tx/5pqu5RJqr7xAkbFxaLG5yXKWyGtKb2xazF87g9eBw8VfHm5fdgeuG5W4fZrdu5N6FMZdch9VCckmF5XmZNU77gcp) [sell](https://solscan.io/tx/3jbai8FFE4sNrWzRhHPVLsvkLd6cSGf1x2sNp6e1iNKCjYGVEPnFaasFfhGwpWW7eHv4FpG9RvJ9unZeypvo86sm) [whale](https://solscan.io/tx/3mBBNzQEDx4UnDtj1zm37rRRJBxxVxMmsYksvomUk9ecFiQRMPKsFA34b95WTHt6e36QukCSa67Ux8ZzTsQWZumB) |
| 84 | 08:38:26 | [24ErE2](https://gmgn.ai/sol/token/24ErE2suMB8S9A69kWXngWtTA3RD7dCXgtBwkNRApump) | 6.2% / 9.88 | +9 | Harmonic `Fd7btg` | time-ms 0.7 s | **-0.0176** | [buy](https://solscan.io/tx/652eXLs1hCbjVwRviLqRwQtUffUArbUay7KXohwH1uz63884aEZBDXx9vsMvTeWeefdfYKoKFQTRRYfC9twcfQms) [sell](https://solscan.io/tx/5gKGK1fD9jnmoJPR5qH9GeyekaoYe9oQxHGTK4dA65g3pNu9WSJiUp1aRPV5nZADQpEUbQ8FeSTozBvBtLRDf3uG) [whale](https://solscan.io/tx/3aXBv7BZfqVBUwohhv3FmniMf8JzdCPpKb6GiQiYfvWtJD6hRnccaHa5KVmb1uLfTaNPkYZykr5gwF5RL1B7MRsQ) |
| 85 | 08:40:30 | [FRgnLT](https://gmgn.ai/sol/token/FRgnLTQ5VQXNb4UbBxhcsuWze46KPLJNJhe3C9M7pump) | – | +7 | Harmonic `JUPiTE` | time-ms 1.4 s | **+0.0215** | [buy](https://solscan.io/tx/2FDgLi2FPJyBukFBgMFHo12rYSPrHGdX12oUwcixLAASeysRryG6ub1Ts9z24QZjJkHuguJ2vPnUMS5mq4xYhET1) [sell](https://solscan.io/tx/5s4cKTLTmcEsvEPzJCEiceg36xuB9gF354S4GddSPtCdD7Ggq5TiCheSjRUJAKT1KwqgNnPG2WTEnAyGmAQJhqZU) |
| 86 | 08:45:25 | [76d61A](https://gmgn.ai/sol/token/76d61ALKcHoirMyupnGTrCjk9UeB1omrEQU3zyqipump) | 12.3% / 5.63 | +7 | Jito `Gv9ggu` | time-ms 0.8 s | **+0.0469** | [buy](https://solscan.io/tx/57WbgqgpCVCHAG8HmBxPuF8pGo3LsCA3HGrc68Y5aTuJjBnE73mhGFCSVAJFKeDA9Z5SADrnbC6cbMWgsTg6ThrJ) [sell](https://solscan.io/tx/2Hay8vZfrumtVHTfYHb3kBT41Kn2jd8YNi7WAaDC6HzVDn48mg8dN4yeW87ekHNvpdjW8fqTTdhegica3tq6eGAD) [whale](https://solscan.io/tx/4xMMACtp3xLt6i4aP9kXUX64mVyvK4SdHW7B1AP6J87ejnjqtCibx6gBKC3aC1QcYN6pHMGT7HYYt2LWRHNGV6bu) |
| 87 | 08:47:14 | [GpaV7x](https://gmgn.ai/sol/token/GpaV7xQQ6wYnwHVJtFHqzTojZLAqqiEVsRQUMQZsBiyt) | 15.5% / 5.93 | +1 | BAM `7y5VhV` | time-ms 0.7 s | **-0.0570** | [buy](https://solscan.io/tx/3ytCNH6GSGdKvZWb1vCK2AwH63EsnUkjrXtDLwDeRc4wuU521oUbhMTuEJZ74cxxTio46hWTTpTjLnjaghsdozbS) [sell](https://solscan.io/tx/2PuoarJ9THM1WQb6Zya6NkJFWLivPMY5pPBtAqCgeZKgiFy2HFW9wUCYoU6aGd7WfFkxQoGgjD4hC2v1jsqPKptq) [whale](https://solscan.io/tx/EN55hNYzYyQMuRiLZBTdodYbMrGwyAmzPTs31vNQhFU7Nmf9s1ZeSe8afTrLmhxBPBGt6LuJYARR2AwbUB9YzMf) |
| 88 | 08:47:44 | [3Pk7Va](https://gmgn.ai/sol/token/3Pk7Va5QJoFMTjNTHcTz7NMm7bqAFPNbdCg2vwfopump) | – | +7 | Harmonic `6YY2VS` | take-profit 0.7 s | **+0.1334** | [buy](https://solscan.io/tx/2TgAMMgsjSASLbDHKtJg9jdNm7wRm5hCxQ9z8iLVdRnmMSmYD17auH7xpyo3tQmrrQCKqAe8rQ2Y7DVvERACrZ5f) [sell](https://solscan.io/tx/36dEDCKXiM51Qi1fyH8BHEyozSXqkKneM3WFR5CogPAVcf8Mh29iuimQBmEg4vc5LobQ86JXmF5Vv5FoWkuRtNbo) |

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 12493 |
| Inside the envelope (age / drop / since-buy / size) | 5638 |
| Picks (score above the threshold) | 113 |
| Skipped | far_leader 68, spacing 20, presend_armed 5, presend_position_open 2, presend_position 1 |
| Buys sent | 0 |
| Filled | 0 |
| Failed on the +5% guard | 0 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 0 of 0 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|

## 7. Breakdowns
## 8. P&L leaders
**By slot leader (validator), best to worst:**

- no buys

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | – (p25 –, p75 –, n 0) |
| Executed-feed lag behind first sighting, ms | – (p25 –, p75 –, n 0) |
| Buy sent → our tx seen on the feed, ms | – (p25 –, p75 –, n 0) |
| Fills: our buy seen on the feed after the dump, ms | – (p25 –, p75 –, n 0) |
| Guard fails: our failed buy seen after the dump, ms | – (p25 –, p75 –, n 0) |
| Fills in the dump's own block | 0 of 0 |
| Guard fails in the dump's own block | 0 of 0 |

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | – |
| Guard fails: rival buys ahead (median) | – |
| Guard fails: rival SOL ahead (median) | – |

## 11. Costs
No fills. Failed buys cost 0.0000 SOL in tx fees.

## 12. Health checks and red flags
- ⚠️ 79 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getLatestBlockhash: 8 timeouts/transport errors (worst p99 534 ms)
- ⚠️ RPC bh-fallback getSlot: 12 timeouts/transport errors (worst p99 1001 ms)
- ℹ️ RPC exit-fallback getAccountInfo: slow minutes (worst p99 430 ms, max 430 ms)
- ℹ️ 4 send-path health events (self-heal), e.g. `SEND-PATH rpc bh-fallback UNHEALTHY: 3 timeouts / transport errors in a row (getLatestBlockhash): client REBUILT (fresh `
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)
- ⚠️ big pre-send loss 251NNn -0.1203 (time-ms, BAM)
- ⚠️ big pre-send loss FRBrHz -0.1382 (stop-loss, BAM)
- ⚠️ big pre-send loss B48ycU -0.1881 (stop-loss, Jito)
- ⚠️ big pre-send loss BaJUPp -0.1470 (time-ms, BAM)
- ⚠️ big pre-send loss AoM7GQ -0.1359 (time-ms, BAM)
- ⚠️ big pre-send loss HwuTuN -0.1033 (time-ms, Jito)

Checks passed: every pre-send fill was closed by a sell; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
- none recorded

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r39.jsonl`, log `.log` on cyber-dock (cyberams) (local copy `/home/it/sniper-data/runs/ams/runs/dip_ams_r39.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Pre-send (section 4b): the jsonl presend_live_* records (fills, closes, REALIZED, account closes, stops, end checks) and presend_attempt_land (try results, failed-try fees); the log's PRESEND LIVE lines when a run has no such records.
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-30 08:50 PKT.

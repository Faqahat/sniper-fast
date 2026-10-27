# Frankfurt run 25 — dip bot run report

*Live overnight: reactive M2 only (pre-send live off) + routes v13 on dip19; 0.40 SOL, dev list 0.40; 720 min*

> **Verdict:** −0.549 SOL on the wallet (3.5146 → 2.9658). The KILL SWITCH ended it at 05:30:40 (run P&L −0.548859 below −0.5). 208 buys, 73 filled (27 wins): fills −0.481, failed buys −0.068. Jito leaders lost most: 17 fills (5 wins) −0.417, −0.444 with their failed buys; worst EVQCNPrR −0.205. 04:00–05:30 lost −0.503 of the total. Engine speed was normal all night (decision median 1.9 ms, executed-feed lag 2.5 ms, runtime-lag worst p99 2.5 ms — same as runs 23 and 24).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.5489 SOL** (wallet 3.5146 → 2.9658, Δ -0.5489) |
| Started (PKT) | 2026-10-26 21:48:17 |
| Ended (PKT) | 2026-10-27 05:30:40 — kill switch (run loss cap reached) |
| Ran for | 7 h 42 min of 720 min planned |
| First / last buy (PKT) | 21:55:33 / 05:30:38 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 208 → **73 filled**, 129 failed on the +5% guard, 6 failed (other) |
| Fill rate | 35% |
| Wins / losses (fills) | 27 / 46 (win rate 37%) |
| Per filled buy | avg -0.0066, median -0.0086 SOL |
| Fills only / failed buys only | -0.4807 / -0.0682 SOL |
| Best / worst trade | 3aC5KH +0.1268 / EVQCNP -0.2052 |
| Fill landing | median 43 ms after the dump (seen on our feed); 54 of 73 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip19 (dip18 + pre-send merged-fill fix: follow-up sells, accounts closed after exit) |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.40 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.40 SOL |
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
| near-leader gate | 198 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off (shadow only) |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 500 fills, 1 open at a time, 720 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 24**:

| Setting | FRA run 24 | FRA run 25 |
|---|---|---|
| pre-send | LIVE: whale >= 6%, 4 tries/slot, 0.400 SOL, limit x0.88, route helius-ps, caps 100 fills / 0.1000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% | off (shadow only) |
| limits | max 500 fills, 1 open at a time, 330 min, loss cap 0.500 SOL | max 500 fills, 1 open at a time, 720 min, loss cap 0.500 SOL |

- Pre-send live off (run 24 had it on at 0.40); reactive settings unchanged; time limit 720 min.

## 4. Timeline (PKT)
- **21:48:17** engine start #1 (session with 0 buys)
- **21:50** the first start (21:48, 330 min) was stopped with Ctrl+C before any buy; the restart at 21:55 ran with 720 min. The log holds both engine sessions (two START BALANCE blocks); the report sums them.
- **21:50:23** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends
- **21:55:06** engine start #2 (session with 208 buys)
- **22:46:11** big loss: CGyKUs -0.0509 SOL (time-limit)
- **22:46:20** big win: Fu9ZUB +0.0912 SOL (time-limit)
- **22:54:46** big win: 64eNnj +0.0836 SOL (time-limit)
- **00:39:28** big win: 9e936s +0.0820 SOL (time-limit)
- **00:48:09** big loss: EVQCNP -0.2052 SOL (time-limit)
- **01:28:59** big loss: 8JG22M -0.0584 SOL (time-limit)
- **01:51:02** big win: 3aC5KH +0.1268 SOL (time-limit)
- **02:39:29** big win: 3wJsEz +0.0650 SOL (time-limit)
- **04:44:36** big loss: BwBbrk -0.0745 SOL (time-limit)
- **04:48:57** big loss: 2Ew1GA -0.0782 SOL (time-limit)
- **05:18:51** big loss: H3bwFk -0.0521 SOL (time-limit)
- **05:22:17** big loss: 5ebU1Q -0.0778 SOL (time-limit)
- **05:30:38** big loss: mj1swJ -0.1636 SOL (time-limit)
- **05:30:40** engine end #2: run end
- **05:30:40** kill switch: run P&L −0.548859 SOL (balance 2.965788) below −0.5 → no new buys, run ended

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 51398 |
| Inside the envelope (age / drop / since-buy / size) | 23597 |
| Picks (score above the threshold) | 731 |
| Skipped | far_leader 421, spacing 94, skip_client 5, max_open 1, open_on_token 1, no_launch_accounts 1 |
| Buys sent | 208 |
| Filled | 73 |
| Failed on the +5% guard | 129 |
| Failed (other) | 6 |
| Never landed | 0 |
| Sold (positions closed) | 73 of 73 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 21:55:33 | [73YuKb](https://gmgn.ai/sol/token/73YuKbgncFUMptCtMAM8SgAa5edFx28ye8FtESPJpump) | 0.40 | -0.23 | 2.16 / −11% | 2.1 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 2 | 21:58:06 | [8cj98g](https://gmgn.ai/sol/token/8cj98gxHVRShtS8PV5YwcKwDEqkxk2aiQhMq9wo77ZBH) | 0.40 | 0.00 | 7.25 / −25% | 5.5 s | Harmonic `CQdLgw` | guard fail | -0.0005 |
| 3 | 21:58:07 | [D4CxoN](https://gmgn.ai/sol/token/D4CxoN5fbH72ziMuNnsweRJvPoPkVhQxojaKBJ2Spump) | 0.40 | -0.12 | 7.23 / −15% | 20.6 s | Harmonic `Fd7btg` | filled | **-0.0301** |
| 4 | 21:58:32 | [J7PJym](https://gmgn.ai/sol/token/J7PJymSQ4dJzNgP4JuAv8CVpE7fRpLhvZ45B1Xxspump) | 0.40 | -0.70 | 2.23 / −13% | 1.7 s | Harmonic `EXckih` | filled | **-0.0132** |
| 5 | 21:58:50 | [F8dJMm](https://gmgn.ai/sol/token/F8dJMmQixHHZjK1psf2EyPoeeHyWimJTtPaohj3RnsDt) | 0.40 | 0.55 | 7.33 / −35% | 1.3 s | Harmonic `shftkx` | failed | -0.0005 |
| 6 | 21:59:31 | [8XSpnV](https://gmgn.ai/sol/token/8XSpnVUSymvWEctYhQD1dmDMSkcLnboVzttZBgQFpump) | 0.40 | -4.30 | 1.13 / −6% | 56.4 s | Harmonic `5ZqveV` | failed | -0.0005 |
| 7 | 22:00:27 | [3RuhZb](https://gmgn.ai/sol/token/3RuhZbnsLViYmLeFMWe7icZSLtxwGsYnvwMgJ7DGpump) | 0.40 | -0.27 | 3.05 / −15% | 2.1 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 8 | 22:01:12 | [4VE33s](https://gmgn.ai/sol/token/4VE33sxaGN2JFu4WhqmMkvah6hfCJDWzs1KZw1DVpump) | 0.40 | -2.01 | 1.58 / −9% | 14.4 s | Harmonic `pSo1KZ` | guard fail | -0.0005 |
| 9 | 22:02:24 | [4C4ZjR](https://gmgn.ai/sol/token/4C4ZjRF4nJLymuyK8U7XivekUWTfYAH9uvzkFEkvpump) | 0.40 | -0.56 | 3.83 / −21% | 3.2 s | Harmonic `5ZqveV` | guard fail | -0.0005 |
| 10 | 22:03:10 | [XT4qr2](https://gmgn.ai/sol/token/XT4qr2UQxZoE5U6MneHEmRizsR89bkHqNhprAC6pump) | 0.40 | -2.88 | 1.26 / −7% | 50.2 s | Jito `EUcJwf` | filled | **+0.0159** |
| 11 | 22:08:09 | [C4QDjk](https://gmgn.ai/sol/token/C4QDjk1GBofzmEzfhex1jxjndrzN8CpkiP2HNDMqpump) | 0.40 | 0.80 | 5.01 / −20% | 6.2 s | BAM `ALPHA6` | guard fail | -0.0005 |
| 12 | 22:15:05 | [8mZjTP](https://gmgn.ai/sol/token/8mZjTPP1iXqHKzuxA4XFXsqvJMv7y9hVpSa5oMfsFC9j) | 0.40 dev | 0.75 | 3.59 / −20% | 4.0 s | Jito `HEL1US` | guard fail | -0.0005 |
| 13 | 22:15:50 | [3j2Ecv](https://gmgn.ai/sol/token/3j2EcveFUVo45bCMe4xJyBsMQDjJRrTkVK8EGZX7pump) | 0.40 | -0.27 | 2.57 / −9% | 26.3 s | Jito `EUcJwf` | filled | **+0.0152** |
| 14 | 22:16:49 | [C4QAs7](https://gmgn.ai/sol/token/C4QAs7eYYd95PhgQeqQV6GLryFedJfi4X869t97DokFC) | 0.40 dev | 0.91 | 5.70 / −29% | 4.7 s | Jito `4Nwpyn` | guard fail | -0.0005 |
| 15 | 22:16:51 | [C4QAs7](https://gmgn.ai/sol/token/C4QAs7eYYd95PhgQeqQV6GLryFedJfi4X869t97DokFC) | 0.40 dev | 0.33 | 3.72 / −17% | 7.0 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 16 | 22:22:27 | [2khbN8](https://gmgn.ai/sol/token/2khbN8HDXWquRLB6S4Qnf1Ns3qUJD64ALkmksa2ypump) | 0.40 | -1.10 | 1.46 / −9% | 4.7 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 17 | 22:22:39 | [EdCZQ8](https://gmgn.ai/sol/token/EdCZQ8qUoNjUWJdmiiBfC1qLkQqcnSDLRPRNohcSXeKr) | 0.40 dev | 0.25 | 10.01 / −42% | 4.7 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 18 | 22:23:01 | [HZi3fc](https://gmgn.ai/sol/token/HZi3fcn6QfG5n82aK1YpNQEybYHJiBppEx4hbQMxpump) | 0.40 | -2.08 | 1.21 / −7% | 9.8 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 19 | 22:25:29 | [G4mqZd](https://gmgn.ai/sol/token/G4mqZdSeRPBLMLiYjppW4q1ZX2F1MjHAzHwvuJLwpump) | 0.40 | -0.46 | 2.58 / −12% | 2.3 s | Harmonic `Fd7btg` | filled | **+0.0497** |
| 20 | 22:25:50 | [8jfyFF](https://gmgn.ai/sol/token/8jfyFFt9f2FqgQdXgHZc8XyFxewRRf6DL3oHPHWPpump) | 0.40 | 0.38 | 7.30 / −21% | 15.3 s | Harmonic `EXckih` | guard fail | -0.0005 |
| 21 | 22:28:00 | [CbEY7K](https://gmgn.ai/sol/token/CbEY7KxBPDrhmL6Zshgkyo1rwYWRXSxsb2FvXpXx6VJ8) | 0.40 | -2.88 | 1.25 / −7% | 11.2 s | BAM `2Wf9V9` | filled | **-0.0207** |
| 22 | 22:28:13 | [7AY9x1](https://gmgn.ai/sol/token/7AY9x1ucE14dfHFDLCyX248uevzX95yh9Qvd3tNdHSTG) | 0.40 dev | 0.43 | 3.18 / −15% | 6.2 s | BAM `GQiWnD` | filled | **-0.0132** |
| 23 | 22:28:33 | [3WLZdM](https://gmgn.ai/sol/token/3WLZdMnM9P6AYoDvfWdvTDTBCL2Q4UbkvBdXVCASpump) | 0.40 | 0.71 | 4.69 / −16% | 20.8 s | Agave `scb1Z7` | guard fail | -0.0005 |
| 24 | 22:28:54 | [J6Ajcg](https://gmgn.ai/sol/token/J6AjcgCpZnD3hqKrfGfMfkgXJ5xBmYU9vzS5RkCLpump) | 0.40 | 0.39 | 6.17 / −22% | 2.8 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 25 | 22:28:58 | [J6Ajcg](https://gmgn.ai/sol/token/J6AjcgCpZnD3hqKrfGfMfkgXJ5xBmYU9vzS5RkCLpump) | 0.40 | -1.17 | 2.42 / −7% | 7.0 s | Harmonic `shftkx` | guard fail | -0.0005 |
| 26 | 22:29:00 | [J6Ajcg](https://gmgn.ai/sol/token/J6AjcgCpZnD3hqKrfGfMfkgXJ5xBmYU9vzS5RkCLpump) | 0.40 | -0.86 | 3.23 / −10% | 9.1 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 27 | 22:33:18 | [4mYCHi](https://gmgn.ai/sol/token/4mYCHiEAayNkyQEpTDZuejhd3gdbMvS45RvNW5zAXN2d) | 0.40 | 0.40 | 5.03 / −17% | 11.9 s | BAM `Av8EnY` | guard fail | -0.0005 |
| 28 | 22:33:26 | [9NmqyL](https://gmgn.ai/sol/token/9NmqyLKabRQjd8UAfnGoLtnsqQLrzPk4JRpVSsipqwvY) | 0.40 dev | 0.42 | 3.18 / −10% | 1.9 s | Harmonic `5ZqveV` | filled | **-0.0164** |
| 29 | 22:34:24 | [Dih8ik](https://gmgn.ai/sol/token/Dih8ikHBPwiX1iHoyLZq5pgEd9ceT5kQ5zMs6YHbpump) | 0.40 | -1.38 | 2.20 / −12% | 9.1 s | Harmonic `9W3QTg` | filled | **-0.0376** |
| 30 | 22:35:04 | [9VSKD3](https://gmgn.ai/sol/token/9VSKD3Z465LmJFc9RYS68xwgvHgDHNwBYcLTDSN2QAAy) | 0.40 dev | 0.53 | 9.97 / −42% | 5.5 s | Jito `HEL1US` | guard fail | -0.0005 |
| 31 | 22:35:30 | [3jqZ4x](https://gmgn.ai/sol/token/3jqZ4x1eCFTjQpCweXHUU5RuKCoC8B9RSPQk6de5pump) | 0.40 | 0.39 | 3.53 / −14% | 12.7 s | Jito `HEL1US` | guard fail | -0.0005 |
| 32 | 22:38:28 | [5k9sn7](https://gmgn.ai/sol/token/5k9sn7k4vTNYiXv3BgzXQMo63C96nQxu8XjTWEdGyDkM) | 0.40 | 0.75 | 6.92 / −34% | 2.5 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 33 | 22:40:11 | [6tcqha](https://gmgn.ai/sol/token/6tcqhaqxrgQsHC19ChvzHdYyraebxVbQ2LNNYZw9pump) | 0.40 | 0.36 | 5.78 / −21% | 8.1 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 34 | 22:40:14 | [6tcqha](https://gmgn.ai/sol/token/6tcqhaqxrgQsHC19ChvzHdYyraebxVbQ2LNNYZw9pump) | 0.40 | -2.01 | 1.73 / −6% | 11.9 s | BAM `23SUe5` | filled | **+0.0248** |
| 35 | 22:40:17 | [6tcqha](https://gmgn.ai/sol/token/6tcqhaqxrgQsHC19ChvzHdYyraebxVbQ2LNNYZw9pump) | 0.40 | -0.42 | 3.29 / −12% | 15.1 s | Harmonic `mrgn2v` | filled | **-0.0035** |
| 36 | 22:40:43 | [5sEgpw](https://gmgn.ai/sol/token/5sEgpwBdH2SRrmazZHEnWdYgaahqTVNjeBbAMV1Qpump) | 0.40 | 0.74 | 4.51 / −20% | 40.5 s | Harmonic `FNKgX9` | guard fail | -0.0005 |
| 37 | 22:41:12 | [Ho3gsS](https://gmgn.ai/sol/token/Ho3gsSbZnhajVbYmxVNWpcmBjRD1AsEoDaTN5uK5pump) | 0.40 | -1.66 | 4.16 / −16% | 5.5 s | Harmonic `97jbhV` | filled | **-0.0448** |
| 38 | 22:41:59 | [6LmszS](https://gmgn.ai/sol/token/6LmszSXJtR3y3No9Nb6H4PGcb7s7LQ3CoVguauxaSmpQ) | 0.40 dev | 0.62 | 3.86 / −17% | 39.9 s | Harmonic `HnrXmm` | guard fail | -0.0005 |
| 39 | 22:42:00 | [G7kocv](https://gmgn.ai/sol/token/G7kocviSMNq51r8VFpvPKx4YQxUSxvEVWhETgyhSpump) | 0.40 | 0.46 | 3.25 / −17% | 52.4 s | Jito `6xWLi1` | guard fail | -0.0005 |
| 40 | 22:44:24 | [3k4d3A](https://gmgn.ai/sol/token/3k4d3AvS4c8vLBqS7JTZcktMVAV5vhjLEFvzt9xHpump) | 0.40 | -0.68 | 5.50 / −16% | 26.5 s | BAM `Va1idL` | guard fail | -0.0005 |
| 41 | 22:46:11 | [CGyKUs](https://gmgn.ai/sol/token/CGyKUsYGaqLKkrxxXhptffsHLDfkQ6azz8Qmi7KHpump) | 0.40 | -0.99 | 4.63 / −16% | 6.2 s | Jito `C8Bey3` | filled | **-0.0509** |
| 42 | 22:46:20 | [Fu9ZUB](https://gmgn.ai/sol/token/Fu9ZUB6WN6uTPkFK9o6W2MU2DRmushLgeJgaZ2ANNX7q) | 0.40 | -1.42 | 7.61 / −17% | 43.2 s | Harmonic `Fd7btg` | filled | **+0.0912** |
| 43 | 22:46:25 | [Fu9ZUB](https://gmgn.ai/sol/token/Fu9ZUB6WN6uTPkFK9o6W2MU2DRmushLgeJgaZ2ANNX7q) | 0.40 | -3.80 | 2.00 / −5% | 47.5 s | Harmonic `TopjgY` | filled | **+0.0358** |
| 44 | 22:46:51 | [Fu9ZUB](https://gmgn.ai/sol/token/Fu9ZUB6WN6uTPkFK9o6W2MU2DRmushLgeJgaZ2ANNX7q) | 0.40 | -1.34 | 3.86 / −9% | 74.0 s | Harmonic `5ZqveV` | filled | **+0.0182** |
| 45 | 22:46:57 | [BcQLdb](https://gmgn.ai/sol/token/BcQLdbpzewDYqLqQivme7nmTJoxM7aEX5eT6XBKfzTpu) | 0.40 dev | 0.39 | 3.01 / −10% | 1.9 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 46 | 22:47:11 | [Fu9ZUB](https://gmgn.ai/sol/token/Fu9ZUB6WN6uTPkFK9o6W2MU2DRmushLgeJgaZ2ANNX7q) | 0.40 | -0.99 | 3.42 / −7% | 93.1 s | Jito `ANC1u9` | filled | **-0.0290** |
| 47 | 22:47:56 | [EMytCm](https://gmgn.ai/sol/token/EMytCmUnsMQubHttakidL857DrujLBGGPhgc96Ti9jja) | 0.40 dev | 0.98 | 13.61 / −51% | 1.3 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 48 | 22:54:46 | [64eNnj](https://gmgn.ai/sol/token/64eNnjjFxd38GhuWPqUbjXebXYrxxvBfrzVU5JScpump) | 0.40 | -0.22 | 3.23 / −12% | 15.1 s | Harmonic `Fd7btg` | filled | **+0.0836** |
| 49 | 23:00:04 | [EabQjF](https://gmgn.ai/sol/token/EabQjF9zAXtYRYrc5TGWPJZyoktRGVHhdpVgzeHspump) | 0.40 | -0.29 | 5.36 / −20% | 5.9 s | BAM `3JotfS` | guard fail | -0.0005 |
| 50 | 23:03:33 | [EfyENG](https://gmgn.ai/sol/token/EfyENGHhKTu72qjWtgKkoZZmzRRwh421mWuy42HSpump) | 0.40 | 1.09 | 4.82 / −20% | 10.0 s | BAM `fhsM2s` | guard fail | -0.0005 |
| 51 | 23:04:11 | [B53gx3](https://gmgn.ai/sol/token/B53gx3HKSq9d6UaoWtuXz3HQCp2dEdx5eiEAjDzJpump) | 0.40 | -1.36 | 2.64 / −9% | 15.7 s | Jito `4Nwpyn` | guard fail | -0.0005 |
| 52 | 23:05:04 | [EfyENG](https://gmgn.ai/sol/token/EfyENGHhKTu72qjWtgKkoZZmzRRwh421mWuy42HSpump) | 0.40 | -0.71 | 3.77 / −8% | 99.8 s | Harmonic `DcTPJq` | filled | **-0.0155** |
| 53 | 23:06:55 | [EfyENG](https://gmgn.ai/sol/token/EfyENGHhKTu72qjWtgKkoZZmzRRwh421mWuy42HSpump) | 0.40 | -0.39 | 9.10 / −17% | 211.8 s | Harmonic `Awes4T` | filled | **+0.0254** |
| 54 | 23:07:33 | [9BTGt8](https://gmgn.ai/sol/token/9BTGt8zWdYtX8B75PejK3Ld35TyD9P3fJvPjidk3pump) | 0.40 | -0.07 | 3.02 / −13% | 2.5 s | Jito `7RtC1Q` | guard fail | -0.0005 |
| 55 | 23:08:19 | [CwqZmM](https://gmgn.ai/sol/token/CwqZmMN5KGxmukn4yJp97rWcSWazeEKLGdUECq8qpump) | 0.40 | -0.15 | 2.79 / −14% | 4.5 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 56 | 23:10:44 | [AgCZa8](https://gmgn.ai/sol/token/AgCZa8YSBbk4j474ptr4Evzw6MqHFaGNUWRfxXSTpump) | 0.40 | -0.56 | 2.36 / −9% | 44.7 s | Harmonic `Awes4T` | filled | **-0.0122** |
| 57 | 23:15:05 | [5q4mA1](https://gmgn.ai/sol/token/5q4mA1evwMW2eJDGMtW7LXga95FuzSifLoqnLLdfpump) | 0.40 | 0.24 | 2.69 / −13% | 97.5 s | Harmonic `5ZqveV` | filled | **-0.0138** |
| 58 | 23:15:07 | [5q4mA1](https://gmgn.ai/sol/token/5q4mA1evwMW2eJDGMtW7LXga95FuzSifLoqnLLdfpump) | 0.40 | 0.51 | 6.12 / −27% | 99.4 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 59 | 23:19:04 | [6hsAjP](https://gmgn.ai/sol/token/6hsAjPGsSqmzrWma12E2GnTBbxBooPxCGHpj2rTNpump) | 0.40 | 0.87 | 8.52 / −33% | 10.0 s | Harmonic `4k6wgP` | failed | -0.0005 |
| 60 | 23:20:31 | [6RnLso](https://gmgn.ai/sol/token/6RnLsofd5ePZ2YTKazA6HyZs8p86hM1eaZSKKxF6pump) | 0.40 | -0.05 | 3.20 / −14% | 5.3 s | Harmonic `shftkx` | guard fail | -0.0005 |
| 61 | 23:22:08 | [EvxBe8](https://gmgn.ai/sol/token/EvxBe8Dcnpo2VS7gw2kNF3DT6SvgoQ8inJ9MomLDpump) | 0.40 | -2.51 | 1.12 / −6% | 11.9 s | BAM `CfgRXm` | guard fail | -0.0005 |
| 62 | 23:26:11 | [AnPtUd](https://gmgn.ai/sol/token/AnPtUdyQbsXvWSYwf8MMbHKGGMeiJUmMfx9LQa6t4hyt) | 0.40 dev | 1.03 | 5.10 / −27% | 1.5 s | BAM `7y5VhV` | guard fail | -0.0005 |
| 63 | 23:28:38 | [FqLKXw](https://gmgn.ai/sol/token/FqLKXw7oNZBwCT3oXWpe9jmpc7oYQdpArrJxkjgpump) | 0.40 | -0.31 | 4.38 / −24% | 3.8 s | Jito `vu1sGn` | guard fail | -0.0005 |
| 64 | 23:34:30 | [8Ed1DW](https://gmgn.ai/sol/token/8Ed1DWDsz9fWJEd5jwr8j17APE8nzm5ASawgHSaNmPSc) | 0.40 | -0.04 | 3.25 / −15% | 9.1 s | BAM `GWJyUx` | guard fail | -0.0005 |
| 65 | 23:34:59 | [AkWjwe](https://gmgn.ai/sol/token/AkWjwenr7Pg7F4pHgAftefCTXZPShgch9HKrwGstpump) | 0.40 | 0.33 | 4.68 / −15% | 16.5 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 66 | 23:35:25 | [AfXyjs](https://gmgn.ai/sol/token/AfXyjsMpeVT2rE5zYWBgBa1j42zp63UsEXQvkYWZpump) | 0.40 | -0.40 | 3.32 / −15% | 2.8 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 67 | 23:36:57 | [3NxwCU](https://gmgn.ai/sol/token/3NxwCU9Gt4YjwiFuKotQVXtiXTFdzfLLjSteU1Fmpump) | 0.40 | 0.18 | 4.76 / −24% | 6.4 s | Harmonic `Awes4T` | filled | **-0.0086** |
| 68 | 23:37:02 | [AkWjwe](https://gmgn.ai/sol/token/AkWjwenr7Pg7F4pHgAftefCTXZPShgch9HKrwGstpump) | 0.40 | -0.09 | 5.31 / −16% | 137.8 s | Harmonic `Fd7btg` | filled | **-0.0209** |
| 69 | 23:37:56 | [4KKCgr](https://gmgn.ai/sol/token/4KKCgrd7bm76SCX7RvCNqXb1RasUqzAyyDKtV8uMyxnJ) | 0.40 dev | 0.29 | 4.77 / −15% | 3.2 s | Jito `EUcJwf` | filled | **-0.0175** |
| 70 | 23:38:22 | [B3MtXe](https://gmgn.ai/sol/token/B3MtXeMHWWdnLQ5mrczrQMdUTsGRdABtQhZhBMXtpump) | 0.40 | 0.21 | 5.01 / −27% | 11.4 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 71 | 23:39:47 | [Bcs6EN](https://gmgn.ai/sol/token/Bcs6ENFLGpohvHa6Giny4jiRdDduGKMCMof7mMSrMWfK) | 0.40 dev | 0.45 | 4.46 / −19% | 1.5 s | Jito `HEL1US` | guard fail | -0.0005 |
| 72 | 23:45:25 | [5fZYU8](https://gmgn.ai/sol/token/5fZYU879zdc8ZTrACUEeKqmQ2Y2bWujVmQphYXdhcqWh) | 0.40 dev | 0.29 | 2.01 / −8% | 2.3 s | Harmonic `shftkx` | failed | -0.0005 |
| 73 | 23:46:28 | [8Ei8Dw](https://gmgn.ai/sol/token/8Ei8DwLqJmPcunJAkt1YUn4jLm9obUsse8i5JHffweYq) | 0.40 dev | 0.69 | 4.94 / −19% | 1.9 s | Jito `HEL1US` | guard fail | -0.0005 |
| 74 | 23:47:05 | [HWGpko](https://gmgn.ai/sol/token/HWGpkoSA9LN7K2rC5RadYwr9akxTkb8VAVmTcrcRpump) | 0.40 | -0.37 | 2.17 / −8% | 4.0 s | BAM `GFXVa1` | filled | **-0.0001** |
| 75 | 23:48:32 | [HWGpko](https://gmgn.ai/sol/token/HWGpkoSA9LN7K2rC5RadYwr9akxTkb8VAVmTcrcRpump) | 0.40 | 0.85 | 5.58 / −16% | 89.9 s | Jito `A9mvuk` | guard fail | -0.0005 |
| 76 | 23:49:17 | [DcBnee](https://gmgn.ai/sol/token/DcBneeTsJ6LE8WDHZjFZrzBPZXtgoTonntM4uswLpump) | 0.40 | 0.16 | 7.00 / −34% | 2.3 s | BAM `CMPSSd` | filled | **+0.0260** |
| 77 | 23:56:55 | [3sWYzy](https://gmgn.ai/sol/token/3sWYzyS23S65rxoNeQSZo2MQAKgCiX6EvBD1bCwkpump) | 0.40 | -0.22 | 4.43 / −17% | 4.9 s | Harmonic `Stakex` | guard fail | -0.0005 |
| 78 | 23:58:53 | [DmS1kV](https://gmgn.ai/sol/token/DmS1kV4xGnAHjfZWUgcf5KcNwiWse1XSMdgxoL7Bpump) | 0.40 | 0.89 | 4.67 / −22% | 9.3 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 79 | 00:00:57 | [GHy2pJ](https://gmgn.ai/sol/token/GHy2pJSHqBxYo7oqLqbmzx3vKuXAkSkDVyboJuTWpump) | 0.40 | -0.19 | 4.71 / −17% | 5.7 s | BAM `LimeA3` | guard fail | -0.0005 |
| 80 | 00:04:54 | [GHy2pJ](https://gmgn.ai/sol/token/GHy2pJSHqBxYo7oqLqbmzx3vKuXAkSkDVyboJuTWpump) | 0.40 | 0.21 | 4.41 / −13% | 241.7 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 81 | 00:06:05 | [Eu3wDX](https://gmgn.ai/sol/token/Eu3wDXFLQPkkdEBZKTuiDaecL2R8uw8ugtV6Q4Nhpump) | 0.40 | -0.42 | 2.63 / −10% | 3.0 s | Harmonic `fdzip8` | guard fail | -0.0005 |
| 82 | 00:08:31 | [Ei6BYZ](https://gmgn.ai/sol/token/Ei6BYZ919sR2oKPkrnwQFxmYLtGVmNoP181pjPQ1pump) | 0.40 | 0.03 | 4.53 / −17% | 3.8 s | Jito `8gDfqH` | guard fail | -0.0005 |
| 83 | 00:09:47 | [H5FK4S](https://gmgn.ai/sol/token/H5FK4SYo8JGV2t3eJJcwqe1dqTneBSzTEq2gziTypump) | 0.40 | 0.21 | 6.31 / −21% | 2.8 s | BAM `6NDen7` | guard fail | -0.0005 |
| 84 | 00:09:51 | [H5FK4S](https://gmgn.ai/sol/token/H5FK4SYo8JGV2t3eJJcwqe1dqTneBSzTEq2gziTypump) | 0.40 | -0.09 | 8.89 / −25% | 6.2 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 85 | 00:11:51 | [DeY4wX](https://gmgn.ai/sol/token/DeY4wXrJn1Gn2o51W6rBjmHzsXFGP9Fea91VAG3jpump) | 0.40 | -0.59 | 3.38 / −11% | 7.4 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 86 | 00:12:27 | [CCK7YB](https://gmgn.ai/sol/token/CCK7YB9H4so8QBZJXtNZsVnmSxjEKCcLinoeHxWjpump) | 0.40 | -0.05 | 2.77 / −12% | 12.1 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 87 | 00:19:57 | [G6tbw1](https://gmgn.ai/sol/token/G6tbw1KYuDs8tRq5HDBFiVY2ygrueRxFDBsKPmSJpump) | 0.40 | 0.12 | 6.34 / −20% | 7.6 s | Harmonic `FNKgX9` | failed | -0.0005 |
| 88 | 00:23:09 | [Ep8sW8](https://gmgn.ai/sol/token/Ep8sW83jz4Wm4RKzU7XCRo3xjF1K13wpFNQ1Bui9pump) | 0.40 | 0.27 | 3.56 / −13% | 2.3 s | Harmonic `Fd7btg` | filled | **+0.0285** |
| 89 | 00:23:20 | [6w6nJQ](https://gmgn.ai/sol/token/6w6nJQNskNVtJ6SwueAwPmyBUQMPKB9acBzexHm4pump) | 0.40 | -0.85 | 2.71 / −12% | 4.2 s | BAM `CVRr5o` | filled | **-0.0183** |
| 90 | 00:23:32 | [6w6nJQ](https://gmgn.ai/sol/token/6w6nJQNskNVtJ6SwueAwPmyBUQMPKB9acBzexHm4pump) | 0.40 | -1.02 | 3.44 / −13% | 16.1 s | Jito `HEL1US` | filled | **-0.0441** |
| 91 | 00:29:37 | [3D8gyP](https://gmgn.ai/sol/token/3D8gyPyn99UJAQ1ybWxKDZnmpBD7U6b3xeHaPs6Apump) | 0.40 | -0.82 | 2.70 / −13% | 14.0 s | Harmonic `shftkx` | guard fail | -0.0005 |
| 92 | 00:34:30 | [7XzkbR](https://gmgn.ai/sol/token/7XzkbRmeb5SaqESovJD1nhMSDkHaUvLQ8oVTv47Rpump) | 0.40 | -0.36 | 6.74 / −21% | 11.9 s | BAM `GWJyUx` | filled | **-0.0095** |
| 93 | 00:34:43 | [7XzkbR](https://gmgn.ai/sol/token/7XzkbRmeb5SaqESovJD1nhMSDkHaUvLQ8oVTv47Rpump) | 0.40 | -1.23 | 1.94 / −8% | 24.8 s | Jito `E1r4Ps` | filled | **+0.0216** |
| 94 | 00:37:16 | [9J4fGN](https://gmgn.ai/sol/token/9J4fGNJVX5W1ioT4jMTGiYH1BVXfNXYGqRHoE8N6pump) | 0.40 | 0.63 | 5.51 / −19% | 26.7 s | Jito `ANC1u9` | filled | **+0.0040** |
| 95 | 00:39:08 | [6fV7K4](https://gmgn.ai/sol/token/6fV7K4k4QE8NZGWCAm7rbAV4nWAUh15wo1zP5c57FWNR) | 0.40 | 0.14 | 4.38 / −15% | 5.5 s | Jito `vu1sGn` | guard fail | -0.0005 |
| 96 | 00:39:28 | [9e936s](https://gmgn.ai/sol/token/9e936szeiLQCJ1uxXRcp9jFUeLh1HYjnGzBx7YHwpump) | 0.40 | -1.04 | 1.83 / −11% | 13.1 s | BAM `23SUe5` | filled | **+0.0820** |
| 97 | 00:40:16 | [9y2reL](https://gmgn.ai/sol/token/9y2reLGRCB2iunbZ3bydht9MoHDELpkLoSJoU3f8pump) | 0.40 | 0.01 | 6.26 / −18% | 6.2 s | Harmonic `CQdLgw` | filled | **-0.0011** |
| 98 | 00:42:39 | [4ydjao](https://gmgn.ai/sol/token/4ydjaoDK5FHL3pdpwViAiftsM7EVUyrHf1jecrAzASar) | 0.40 dev | 0.79 | 4.76 / −21% | 12.9 s | Jito `HEL1US` | guard fail | -0.0005 |
| 99 | 00:45:49 | [HoS2pp](https://gmgn.ai/sol/token/HoS2ppRbXEE5deTb4dVivgatcg55jNoT8Zb6MPihpump) | 0.40 | -0.28 | 3.31 / −11% | 42.2 s | Jito `FWD1aV` | filled | **+0.0132** |
| 100 | 00:46:09 | [FPeQja](https://gmgn.ai/sol/token/FPeQja5UPhQvgicftbL3wiwzLquYku3yNW4xGgY7pump) | 0.40 | -0.26 | 3.81 / −13% | 7.6 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 101 | 00:48:09 | [EVQCNP](https://gmgn.ai/sol/token/EVQCNPrRFBZH7ynMNNq2a5fs6xzoZ57KXMG4uswipump) | 0.40 | -0.19 | 3.22 / −13% | 30.9 s | Jito `HEL1US` | filled | **-0.2052** |
| 102 | 00:49:18 | [DextmP](https://gmgn.ai/sol/token/DextmPpX7q7zSFcpq453FJDLnMmo737LpG8rpuNpGhPF) | 0.40 dev | 0.42 | 3.44 / −15% | 123.2 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 103 | 00:54:52 | [FsRHqK](https://gmgn.ai/sol/token/FsRHqK37bhyVvCmwc299EdF1wVecqEUEDDgwmTTQpump) | 0.40 | -0.33 | 3.03 / −13% | 5.1 s | BAM `fhsM2s` | guard fail | -0.0005 |
| 104 | 00:55:13 | [FsRHqK](https://gmgn.ai/sol/token/FsRHqK37bhyVvCmwc299EdF1wVecqEUEDDgwmTTQpump) | 0.40 | -2.41 | 1.10 / −7% | 26.9 s | Harmonic `4k6wgP` | filled | **-0.0340** |
| 105 | 00:55:43 | [GYYQ14](https://gmgn.ai/sol/token/GYYQ14xKHpU4jSxGg6fWnJQY4ehZSbmQcj3XyC2dpump) | 0.40 | -1.28 | 1.64 / −10% | 6.6 s | Jito `E1r4Ps` | filled | **-0.0132** |
| 106 | 00:56:46 | [5UJkWh](https://gmgn.ai/sol/token/5UJkWhgLxiZZoCbcN4NfqacmrtAPKNxwa17Puv4zpump) | 0.40 | -0.17 | 2.54 / −12% | 8.3 s | Harmonic `JUPiTE` | filled | **-0.0008** |
| 107 | 00:58:59 | [5o8JBw](https://gmgn.ai/sol/token/5o8JBwYtQqJd9wg7ez1bF231YLUxrKdtcGqUe9wpump) | 0.40 | -0.33 | 2.75 / −12% | 15.7 s | Jito `8gDfqH` | guard fail | -0.0005 |
| 108 | 01:01:44 | [7934hW](https://gmgn.ai/sol/token/7934hWvP8T3ycPVqa2spEPRknYJykZshu1BCY6j9pump) | 0.40 | 0.20 | 4.54 / −18% | 6.4 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 109 | 01:05:41 | [9jyfZn](https://gmgn.ai/sol/token/9jyfZnLMUA7fVkX5r7x9xbiVVQamWmsoX1bS6cgBpump) | 0.40 | -0.06 | 4.67 / −15% | 4.5 s | Jito `6xWLi1` | guard fail | -0.0005 |
| 110 | 01:06:09 | [2CPfot](https://gmgn.ai/sol/token/2CPfotUfy5R1VcSjVXas4YXSpqYAAuE7jLozqB6ttYXi) | 0.40 dev | 1.24 | 4.95 / −25% | 4.0 s | Jito `BULKzV` | guard fail | -0.0005 |
| 111 | 01:08:30 | [HWeX6e](https://gmgn.ai/sol/token/HWeX6eyz5xRsNjptqgj1VNAWk8RNES2qgjf1rkvAnVW4) | 0.40 | 0.05 | 3.30 / −17% | 17.4 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 112 | 01:09:11 | [CFruoH](https://gmgn.ai/sol/token/CFruoHn9GeBWHfUSh4Cn1bY8XztqnrAW8TJ7T6DMpump) | 0.40 | -0.67 | 8.78 / −24% | 8.3 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 113 | 01:09:30 | [FshVTL](https://gmgn.ai/sol/token/FshVTLaQVvFEgjVRNXn5MY5F1uW6HExdyYHffq9vpump) | 0.40 | 0.31 | 4.25 / −14% | 7.4 s | Harmonic `3iSQtP` | guard fail | -0.0005 |
| 114 | 01:11:17 | [6i2GBP](https://gmgn.ai/sol/token/6i2GBPiZ81DP75YrdkD6oy34H5vpaEbGQhV2zvRspump) | 0.40 | 0.05 | 6.36 / −21% | 6.6 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 115 | 01:11:18 | [6i2GBP](https://gmgn.ai/sol/token/6i2GBPiZ81DP75YrdkD6oy34H5vpaEbGQhV2zvRspump) | 0.40 | -0.47 | 6.22 / −21% | 7.6 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 116 | 01:16:24 | [FcjH2V](https://gmgn.ai/sol/token/FcjH2VJm741s7TWCsDAqqcfqRJhygAXDtdmXHLUepump) | 0.40 | -1.83 | 1.13 / −7% | 30.1 s | Jito `8gDfqH` | guard fail | -0.0005 |
| 117 | 01:18:42 | [6FQrcf](https://gmgn.ai/sol/token/6FQrcfh9HGPrdiyTxcVd3RtSNXVp7vWwBv1LafGgnke6) | 0.40 dev | 0.24 | 2.83 / −15% | 4.2 s | Agave `rsbp8z` | guard fail | -0.0005 |
| 118 | 01:24:21 | [13qFvU](https://gmgn.ai/sol/token/13qFvUU8BproD3qqn4y2fcmeRLoFEtxQ2hNj4VbWUhw6) | 0.40 dev | 0.77 | 9.26 / −40% | 3.2 s | Harmonic `FNKgX9` | guard fail | -0.0005 |
| 119 | 01:26:42 | [56t5oY](https://gmgn.ai/sol/token/56t5oY6g8Sy7PSUwtLCeKkt4sSGGXyQN7ZkigEUFEYQn) | 0.40 dev | 1.32 | 13.85 / −51% | 1.5 s | BAM `3JotfS` | guard fail | -0.0005 |
| 120 | 01:28:59 | [8JG22M](https://gmgn.ai/sol/token/8JG22MR1CuPBNGxfNLdjyKh2jKqfRZNHzfih1pvMpump) | 0.40 | -1.49 | 4.92 / −14% | 12.7 s | Harmonic `JUPiTE` | filled | **-0.0584** |
| 121 | 01:30:54 | [2DB2nq](https://gmgn.ai/sol/token/2DB2nqYqKmBmWwUAa2QBVa9usRGRZTnU295ZAogrpump) | 0.40 | 0.11 | 3.66 / −11% | 90.1 s | BAM `5zm9g3` | filled | **-0.0033** |
| 122 | 01:35:33 | [HEhad4](https://gmgn.ai/sol/token/HEhad4NhRF35QbU7PHXXWjhvutZbGr9QWEEVfmZzpump) | 0.40 | -0.78 | 2.85 / −14% | 47.3 s | Jito `EvnRmn` | guard fail | -0.0005 |
| 123 | 01:36:51 | [DMZAKB](https://gmgn.ai/sol/token/DMZAKBhq6zvV53QKxUj3m8S54s3a17NqQw9ahGTXpump) | 0.40 | -0.36 | 1.99 / −12% | 2.3 s | Jito `HEL1US` | guard fail | -0.0005 |
| 124 | 01:37:27 | [4KXRBY](https://gmgn.ai/sol/token/4KXRBYRnaSb9o63wAHnzFeGbC3j1HJWppH2ERW8bceYV) | 0.40 | -0.05 | 2.01 / −12% | 7.4 s | BAM `GEM1N1` | guard fail | -0.0005 |
| 125 | 01:39:23 | [EdCUGd](https://gmgn.ai/sol/token/EdCUGdHEkyEYKaA44bUR4vp6PtLiBPmyPp2pCWKppump) | 0.40 | -0.56 | 4.12 / −15% | 23.3 s | Harmonic `JUPiTE` | filled | **+0.0021** |
| 126 | 01:40:12 | [7oDsHq](https://gmgn.ai/sol/token/7oDsHqG3ema6pjPwfEFf9QGkXa5S2HoN1oyou4fYpump) | 0.40 | -0.61 | 3.84 / −17% | 70.8 s | Jito `CTDGxT` | guard fail | -0.0005 |
| 127 | 01:41:47 | [27Cekd](https://gmgn.ai/sol/token/27CekdhYBb5DiTUAZqXzHqWEmhtZ1fSqLmNzDTcopump) | 0.40 | 0.59 | 4.56 / −21% | 5.1 s | Jito `EUcJwf` | guard fail | -0.0005 |
| 128 | 01:42:12 | [8qfHsa](https://gmgn.ai/sol/token/8qfHsaV1Bb11BJ6e9bMEdwi4wrNe1jT2wB5jkYhNpump) | 0.40 | -0.69 | 1.56 / −9% | 4.5 s | Harmonic `shftkx` | guard fail | -0.0005 |
| 129 | 01:51:01 | [3aC5KH](https://gmgn.ai/sol/token/3aC5KHpdnEiNEzFzJPcRWhrA9KhFp8DLtFtUqa8Xpump) | 0.40 | -1.04 | 9.52 / −19% | 11.7 s | BAM `CMPSSd` | filled | **+0.0307** |
| 130 | 01:51:02 | [3aC5KH](https://gmgn.ai/sol/token/3aC5KHpdnEiNEzFzJPcRWhrA9KhFp8DLtFtUqa8Xpump) | 0.40 | -0.93 | 7.97 / −18% | 13.4 s | BAM `RBFiUq` | filled | **+0.1268** |
| 131 | 01:51:38 | [FnDKjC](https://gmgn.ai/sol/token/FnDKjCxjC36f4a5oPAJJBs8PUhextSP5TTBBgjQEpump) | 0.40 | -0.54 | 2.59 / −11% | 4.5 s | Jito `C8Bey3` | filled | **-0.0237** |
| 132 | 01:51:39 | [FnDKjC](https://gmgn.ai/sol/token/FnDKjCxjC36f4a5oPAJJBs8PUhextSP5TTBBgjQEpump) | 0.40 | -0.57 | 2.30 / −10% | 6.2 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 133 | 01:57:09 | [3BFTQf](https://gmgn.ai/sol/token/3BFTQfUFrgRzfQ4C4P5eMXmybpgrGM3iDgkVV4RHpump) | 0.40 | 0.32 | 3.89 / −16% | 4.2 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 134 | 01:58:22 | [B7Xgch](https://gmgn.ai/sol/token/B7XgchDeM4ySr6xrtfYXBpjEPzvumr8gxmcHsrN9pump) | 0.40 | -0.87 | 7.17 / −16% | 4.5 s | Harmonic `EXckih` | filled | **+0.0307** |
| 135 | 02:01:33 | [3PHaLo](https://gmgn.ai/sol/token/3PHaLotNcg3o3wWLnj9jbfrrS6waHRSKyk8tTwa7pump) | 0.40 | -1.67 | 5.83 / −13% | 246.8 s | BAM `3KiDz3` | filled | **+0.0183** |
| 136 | 02:03:07 | [7zAtPR](https://gmgn.ai/sol/token/7zAtPRN34cdG1jdopsUN5LsgNcwS1CWzFVMUVfG4pump) | 0.40 | 0.75 | 3.03 / −16% | 125.9 s | Harmonic `mint13` | filled | **-0.0267** |
| 137 | 02:07:14 | [46ktiP](https://gmgn.ai/sol/token/46ktiPQbiXY3i7VyoXsVU1fMwNk6R7gi87QKMe3gpump) | 0.40 | -0.91 | 1.83 / −9% | 83.3 s | Harmonic `Fd7btg` | filled | **-0.0126** |
| 138 | 02:08:20 | [5BzDgR](https://gmgn.ai/sol/token/5BzDgR4jJoszm3yKTnJF8yzggg8fd7iBZkVtoAeo8Gpr) | 0.40 dev | 1.12 | 10.20 / −43% | 3.6 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 139 | 02:09:48 | [8tzrs6](https://gmgn.ai/sol/token/8tzrs6yGT3X8dHJS75jXnLWGrPdEWCpWs8nKvkAnpump) | 0.40 | 0.42 | 3.14 / −15% | 18.2 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 140 | 02:10:53 | [B2aTZv](https://gmgn.ai/sol/token/B2aTZvgZpiaLNRufSyz6uyMTsC5w61gbTMimWCmSpump) | 0.40 | -0.51 | 3.13 / −14% | 12.3 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 141 | 02:16:45 | [A39Ezw](https://gmgn.ai/sol/token/A39EzwEyRgHMEA6BNC7DHGXwx5JyN32LaQC5zzbTpump) | 0.40 | -0.26 | 5.39 / −19% | 2.8 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 142 | 02:17:53 | [AGhodb](https://gmgn.ai/sol/token/AGhodbaJctch5F56eJzMa7kMGqiAYqd6CMwNg79w5ieV) | 0.40 dev | 0.26 | 12.38 / −46% | 4.5 s | BAM `CeJjdk` | guard fail | -0.0005 |
| 143 | 02:21:38 | [5kctrB](https://gmgn.ai/sol/token/5kctrBDtKHwiXtdeF8SMnb2JuNBAPorGimiCRfvM9Rec) | 0.40 dev | 0.85 | 5.10 / −27% | 6.4 s | Jito `A9mvuk` | guard fail | -0.0005 |
| 144 | 02:24:43 | [GncH5J](https://gmgn.ai/sol/token/GncH5JR2FkhNB6pWv2Pr12EYhXSDHpxqGP5jjCrRpump) | 0.40 | -0.50 | 5.77 / −21% | 3.8 s | Harmonic `5RvfTS` | guard fail | -0.0005 |
| 145 | 02:25:37 | [9cAyYy](https://gmgn.ai/sol/token/9cAyYyvY7STi5i9ig1hK5u4Me7FshWrU5tPL46Zupump) | 0.40 | -1.29 | 1.74 / −10% | 25.0 s | Harmonic `pSo1KZ` | guard fail | -0.0005 |
| 146 | 02:26:19 | [7kdYYB](https://gmgn.ai/sol/token/7kdYYBiVaPYJMHiSzoH8v2yD9yGrL6PgqcQki6Capump) | 0.40 | -0.13 | 5.40 / −20% | 11.2 s | Harmonic `3ytgyJ` | guard fail | -0.0005 |
| 147 | 02:30:13 | [6biVux](https://gmgn.ai/sol/token/6biVuxvqqKLeSSApTGVu5KNQKTUECHUVcx4xg4UUpump) | 0.40 | -0.49 | 2.31 / −12% | 1.3 s | Jito `EvnRmn` | guard fail | -0.0005 |
| 148 | 02:37:32 | [7rxBK8](https://gmgn.ai/sol/token/7rxBK8ydC9pfa2MhpSGWhntqHmqoHKvyUJByRTXdsPjg) | 0.40 dev | 0.44 | 4.23 / −22% | 4.2 s | BAM `LimeA3` | guard fail | -0.0005 |
| 149 | 02:37:52 | [CivjG6](https://gmgn.ai/sol/token/CivjG6Mx9C7U917iFVTtWF7krgo4UGqWgPft3aTNw3CD) | 0.40 | 0.89 | 4.17 / −17% | 5.7 s | BAM `3JotfS` | guard fail | -0.0005 |
| 150 | 02:37:59 | [CivjG6](https://gmgn.ai/sol/token/CivjG6Mx9C7U917iFVTtWF7krgo4UGqWgPft3aTNw3CD) | 0.40 | 0.09 | 3.64 / −17% | 13.6 s | Harmonic `DcTPJq` | guard fail | -0.0005 |
| 151 | 02:39:29 | [3wJsEz](https://gmgn.ai/sol/token/3wJsEzPMNtUptUmfHrbuT52FQ2PdCgMyDaUfeq6vpump) | 0.40 | 0.80 | 2.52 / −9% | 4.0 s | Harmonic `FNKgX9` | filled | **+0.0650** |
| 152 | 02:42:02 | [H4F5Gb](https://gmgn.ai/sol/token/H4F5Gbf6Bs4ZnoKprPajqRn1CLiBnAjbj3SxWQ8dyd55) | 0.40 dev | 0.41 | 3.16 / −17% | 5.7 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 153 | 02:42:37 | [5US6uN](https://gmgn.ai/sol/token/5US6uNpdjaj9dkaUba8K8xW61Rmq9Cnvi5mTr13bpump) | 0.40 | 0.58 | 4.59 / −22% | 38.8 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 154 | 02:45:45 | [F7GSVY](https://gmgn.ai/sol/token/F7GSVY1167ZizJJy2KVJMLfiZAip5iGQjWVp6839pump) | 0.40 | -1.42 | 1.87 / −10% | 14.2 s | Jito `HEL1US` | guard fail | -0.0005 |
| 155 | 02:46:29 | [5Y2Sat](https://gmgn.ai/sol/token/5Y2SatjdeVBt7VyTLeCX1RyodYsUt3PxA9NQWtJ3Xgzw) | 0.40 dev | 0.87 | 4.45 / −17% | 61.7 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 156 | 02:54:26 | [CnWtP1](https://gmgn.ai/sol/token/CnWtP1tUxEZyv7pySAAq324tW5NDjZn2PSSAkFvTpump) | 0.40 | 0.50 | 3.74 / −15% | 14.4 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 157 | 02:55:58 | [AzJgg5](https://gmgn.ai/sol/token/AzJgg5rd2juV3wJrtayMySMzz7C5NDfCBgwgyMMDpump) | 0.40 | 0.13 | 3.75 / −14% | 55.5 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 158 | 02:57:00 | [4Tfc7B](https://gmgn.ai/sol/token/4Tfc7BzWknaghxh3n5gSU9DsG5Ayvp2RV6KffBVTpump) | 0.40 | 0.59 | 3.48 / −18% | 16.5 s | Jito `8gDfqH` | guard fail | -0.0005 |
| 159 | 02:57:10 | [6CwJZc](https://gmgn.ai/sol/token/6CwJZchZp23CXNy7fWf39JjoPB8v2JBDKVCVzvnvpump) | 0.40 | -0.16 | 5.70 / −19% | 43.0 s | Jito `HEL1US` | guard fail | -0.0005 |
| 160 | 02:57:17 | [332yKY](https://gmgn.ai/sol/token/332yKYWi2mVyg6gkM9h5LxvYc3J2aeDN8r3kfFKS1hBz) | 0.40 dev | 0.44 | 3.95 / −21% | 2.3 s | Harmonic `3iSQtP` | guard fail | -0.0005 |
| 161 | 03:00:12 | [n5L1SN](https://gmgn.ai/sol/token/n5L1SNvpfW2pweHbXXtE8i5FuzBooLH8ZeTpmLcpump) | 0.40 | -0.93 | 6.95 / −28% | 6.8 s | BAM `9jxgos` | filled | **+0.0150** |
| 162 | 03:04:37 | [fEzy36](https://gmgn.ai/sol/token/fEzy36dyu4euEw3yyQWEGqr9efm8Pr93H9NYaEGpump) | 0.40 | -1.01 | 4.13 / −16% | 9.8 s | Harmonic `shftkx` | guard fail | -0.0005 |
| 163 | 03:04:41 | [vsDwmT](https://gmgn.ai/sol/token/vsDwmTD2a7p12QPALccTPEjFSnjRwMMzWu5iSW4pump) | 0.40 | 0.55 | 2.59 / −13% | 1.5 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 164 | 03:04:58 | [A6PY45](https://gmgn.ai/sol/token/A6PY45dkDPLsTA8HoE8eHvj4Qd4h45CS2FpVVnhUpump) | 0.40 | -0.89 | 2.96 / −13% | 7.0 s | Harmonic `CQdLgw` | filled | **+0.0408** |
| 165 | 03:06:27 | [GGEj3C](https://gmgn.ai/sol/token/GGEj3CW1rwHuu5HEwwy6X7G2BKShAMsPSgNnGsk2pump) | 0.40 | 0.47 | 3.61 / −19% | 1.9 s | Harmonic `Awes4T` | filled | **-0.0148** |
| 166 | 03:15:15 | [37CGJE](https://gmgn.ai/sol/token/37CGJE3ih6WW459hkWQE4xKD97m32hPsN9xy5bURpump) | 0.40 | -0.98 | 2.90 / −16% | 17.8 s | Harmonic `9W3QTg` | filled | **-0.0132** |
| 167 | 03:15:47 | [FMa8RY](https://gmgn.ai/sol/token/FMa8RY4y7Uyq7pJgxAsYDdgN5s6wWF5BaSNyEJS3pump) | 0.40 | 0.53 | 3.60 / −14% | 38.2 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 168 | 03:16:09 | [43YC5N](https://gmgn.ai/sol/token/43YC5NU82Yq63PJwmBN9AJEvAYrkyfz9eAHt2Aqhpump) | 0.40 | -0.16 | 5.61 / −19% | 9.1 s | Harmonic `shftkx` | guard fail | -0.0005 |
| 169 | 03:18:04 | [Hbj18m](https://gmgn.ai/sol/token/Hbj18meuMg6iVPSphGfwqAmaVjx6KcwxwwDascSDFroN) | 0.40 | 0.85 | 6.93 / −34% | 3.2 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 170 | 03:18:08 | [48H3ag](https://gmgn.ai/sol/token/48H3agU6aqPhegLi5qg2YKh9svsr4ssmcc6Azq4dpump) | 0.40 | -0.72 | 2.10 / −9% | 2.5 s | Harmonic `JUPiTE` | filled | **+0.0192** |
| 171 | 03:18:18 | [48H3ag](https://gmgn.ai/sol/token/48H3agU6aqPhegLi5qg2YKh9svsr4ssmcc6Azq4dpump) | 0.40 | -0.01 | 3.42 / −16% | 12.3 s | Jito `HEL1US` | guard fail | -0.0005 |
| 172 | 03:20:12 | [FEvLVD](https://gmgn.ai/sol/token/FEvLVDnQRzwB45uZjUEL8jp1mDaTJ1cAgYmRYpNGpump) | 0.40 | -1.34 | 4.65 / −13% | 61.5 s | Jito `EvnRmn` | failed | -0.0005 |
| 173 | 03:23:13 | [Ddi6h2](https://gmgn.ai/sol/token/Ddi6h2CRrbJjsfZ341PAdtjPUhHx3WeiuMHXWGh6pump) | 0.40 | -1.12 | 3.72 / −11% | 12.1 s | Harmonic `DcTPJq` | filled | **-0.0395** |
| 174 | 03:35:30 | [6QxfLD](https://gmgn.ai/sol/token/6QxfLDcspfGyoZk8h2PAakrcenR6NAXjsmMRLPBopump) | 0.40 | -0.58 | 2.67 / −14% | 5.1 s | Jito `EvnRmn` | guard fail | -0.0005 |
| 175 | 03:37:59 | [C4CpL2](https://gmgn.ai/sol/token/C4CpL2oWKGLt4LCQa52KHNPQr1wfYpGqo7nZjh16pump) | 0.40 | -0.21 | 1.89 / −8% | 3.8 s | Harmonic `5ZqveV` | guard fail | -0.0005 |
| 176 | 03:40:55 | [EEHQqj](https://gmgn.ai/sol/token/EEHQqj3eyKr23W3WPo9e3S3GMLK2NYs42FTUaeakpump) | 0.40 | -0.52 | 6.05 / −15% | 111.1 s | BAM `3V2xac` | guard fail | -0.0005 |
| 177 | 03:41:41 | [21cGma](https://gmgn.ai/sol/token/21cGmapeUvcShy1KKFczkwuqhFkWJRdB6xfBqUaGpump) | 0.40 | -2.46 | 1.14 / −7% | 92.9 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 178 | 03:46:10 | [9UX9S6](https://gmgn.ai/sol/token/9UX9S6f4m3KeqWuyw9Z5Sj8ahGpZeQC39P6i9eY8pump) | 0.40 | 0.54 | 3.90 / −14% | 50.2 s | Jito `3YVoK8` | guard fail | -0.0005 |
| 179 | 03:47:12 | [HrXZgt](https://gmgn.ai/sol/token/HrXZgtu6Xop4rx1XVSUwKhdSaNQQ77iXNroSbBqdpump) | 0.40 | 0.10 | 3.02 / −16% | 19.1 s | Harmonic `EJsJx7` | guard fail | -0.0005 |
| 180 | 03:57:13 | [9G9WF1](https://gmgn.ai/sol/token/9G9WF18PHXdUpYohqKmBgDiGYUhUPa7Vqd3oC8LBo1gk) | 0.40 | -0.52 | 2.80 / −14% | 3.2 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 181 | 03:59:20 | [FTMGHV](https://gmgn.ai/sol/token/FTMGHVoQYttvArMDMgq2956f21h9tJHMPrbDAYuMpump) | 0.40 | -0.62 | 5.44 / −20% | 7.0 s | Jito `HEL1US` | guard fail | -0.0005 |
| 182 | 03:59:55 | [AHYTpF](https://gmgn.ai/sol/token/AHYTpFEeJbZXh3xZSx8UCxo2A2ms4X8s84ZLJFqfpump) | 0.40 | -0.86 | 3.23 / −11% | 7.8 s | Jito `HEL1US` | guard fail | -0.0005 |
| 183 | 04:05:33 | [HmRNwV](https://gmgn.ai/sol/token/HmRNwVYdNHDuGdco6n1cUaQYNTdcqVEbzaT3p8r1pump) | 0.40 | -0.19 | 3.16 / −12% | 6.8 s | BAM `nebu15` | guard fail | -0.0005 |
| 184 | 04:06:12 | [FqYWoe](https://gmgn.ai/sol/token/FqYWoeiHxXR5DCGE66xjWsFDh8LtxZkn9xLXXmLnpump) | 0.40 | -0.40 | 2.23 / −11% | 4.0 s | Harmonic `FNKgX9` | guard fail | -0.0005 |
| 185 | 04:07:07 | [HrR6Gs](https://gmgn.ai/sol/token/HrR6GsS63no7gMNFQzonHmbjxnYXgNGWn9DML81LZAxJ) | 0.40 | 0.75 | 3.15 / −14% | 74.8 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 186 | 04:12:30 | [5Z1sxZ](https://gmgn.ai/sol/token/5Z1sxZSc9HSMWcoNr7B96QeV2VTtAUu3paxQhQeqpump) | 0.40 | -2.31 | 2.23 / −13% | 15.1 s | BAM `7nzTzR` | guard fail | -0.0005 |
| 187 | 04:12:33 | [LL6on2](https://gmgn.ai/sol/token/LL6on2Z25mnce6fV1A7nGiczsVE1yNGmWAudLkzpump) | 0.40 | -0.33 | 2.35 / −13% | 7.4 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 188 | 04:26:52 | [FMAdoJ](https://gmgn.ai/sol/token/FMAdoJBibHPPddcCvbZiAc9eY23PhmzneG9VKCDypump) | 0.40 | 0.89 | 5.08 / −18% | 3.8 s | BAM `AmjX7C` | filled | **-0.0038** |
| 189 | 04:30:58 | [9hLbQT](https://gmgn.ai/sol/token/9hLbQTXcYH2rZ634sHfaT1XYU14jkP6GHiNS16Xxpump) | 0.40 | -0.59 | 2.31 / −9% | 3.8 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 190 | 04:44:36 | [BwBbrk](https://gmgn.ai/sol/token/BwBbrk2GrJkxr1A3ei28Mk65hvECMUVbRqP4TXVDhnUk) | 0.40 | -1.04 | 2.56 / −11% | 2.5 s | BAM `9ueKvL` | filled | **-0.0745** |
| 191 | 04:46:15 | [BwBbrk](https://gmgn.ai/sol/token/BwBbrk2GrJkxr1A3ei28Mk65hvECMUVbRqP4TXVDhnUk) | 0.40 | -0.26 | 7.74 / −17% | 102.0 s | Harmonic `Fd7btg` | filled | **-0.0380** |
| 192 | 04:46:39 | [6iiKNR](https://gmgn.ai/sol/token/6iiKNR3WNpUgY9J2Hhox9VdWt2X3fsLXp26S5Ryfpump) | 0.40 | -0.29 | 5.40 / −28% | 4.7 s | Jito `8gDfqH` | filled | **-0.0067** |
| 193 | 04:47:21 | [RKor5T](https://gmgn.ai/sol/token/RKor5TpK3jF7HYAnTFAKyCj99ewneXvN1MZ3Ftrpump) | 0.40 | 0.03 | 3.86 / −18% | 11.9 s | BAM `7y5VhV` | filled | **+0.0117** |
| 194 | 04:48:57 | [2Ew1GA](https://gmgn.ai/sol/token/2Ew1GAyFdLyapNMWRi8pLXt4G1QMNSCfBtuXCQy7pump) | 0.40 | -0.38 | 4.11 / −13% | 21.2 s | Jito `E1r4Ps` | filled | **-0.0782** |
| 195 | 04:50:52 | [Cxoe53](https://gmgn.ai/sol/token/Cxoe53DGEfDYompUHazEFLs5MvMjePgqxG8No6SkpsHP) | 0.40 | 0.53 | 4.10 / −22% | 4.0 s | BAM `7nzTzR` | guard fail | -0.0005 |
| 196 | 04:52:16 | [5bMrkC](https://gmgn.ai/sol/token/5bMrkCWkM7zVBq1MZqWWJSfvo5yeBTePFHSP8Hgspump) | 0.40 | 0.26 | 3.27 / −13% | 4.0 s | Harmonic `Fd7btg` | filled | **+0.0299** |
| 197 | 04:53:20 | [JBCicY](https://gmgn.ai/sol/token/JBCicYrn4UDrRq6zj6p4KKRW9oB2rivozLbE5Szpump) | 0.40 | -0.20 | 3.04 / −14% | 7.2 s | Jito `EvnRmn` | filled | **-0.0091** |
| 198 | 04:53:27 | [P1st61](https://gmgn.ai/sol/token/P1st61EawctaAo5BD7CZ6AcmeEYo3x3vtffUwtdpump) | 0.40 | -0.85 | 9.03 / −20% | 12.3 s | Jito `EUcJwf` | guard fail | -0.0005 |
| 199 | 04:53:53 | [2xr8Vw](https://gmgn.ai/sol/token/2xr8Vwdh2nsGJ8egfdqL83azW5TVCr5bNWdXVxoV6T7T) | 0.40 | -2.66 | 1.79 / −5% | 16.1 s | Jito `E1r4Ps` | filled | **-0.0048** |
| 200 | 04:54:32 | [6BZPmN](https://gmgn.ai/sol/token/6BZPmNP4bXC3MLGGWzSpLzgjbMJ824esDmHQne7Ypump) | 0.40 | -2.51 | 1.26 / −7% | 6.4 s | BAM `CVvaeD` | filled | **-0.0237** |
| 201 | 04:56:29 | [ArRDgf](https://gmgn.ai/sol/token/ArRDgfcJg5wS1N6yezepntXVKLyYCpDifA19s9fHpump) | 0.40 | 0.23 | 3.15 / −11% | 32.9 s | Harmonic `HnrXmm` | guard fail | -0.0005 |
| 202 | 05:01:08 | [Bq27Fw](https://gmgn.ai/sol/token/Bq27Fwejdjcva6UpQg5powyezFgudq198P5i6cWUpump) | 0.40 | -1.29 | 3.01 / −17% | 18.4 s | Jito `6xWLi1` | filled | **-0.0050** |
| 203 | 05:08:23 | [HiUSFL](https://gmgn.ai/sol/token/HiUSFLQjASpELffrBbQjKQT1sK6stZkEteba2nfepump) | 0.40 | -1.13 | 1.29 / −8% | 6.2 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 204 | 05:18:51 | [H3bwFk](https://gmgn.ai/sol/token/H3bwFkWKftXPg3ieVYESMJ3j83cmY5GapPjftDX6pump) | 0.40 | -1.65 | 2.05 / −10% | 2.5 s | Harmonic `JUPiTE` | filled | **-0.0521** |
| 205 | 05:22:15 | [5bGXVy](https://gmgn.ai/sol/token/5bGXVywbvGZ1szFKsv3HMCJWV7FMcBVUdabUnntFpump) | 0.40 | -0.29 | 3.45 / −12% | 21.2 s | Harmonic `grpton` | filled | **+0.0107** |
| 206 | 05:22:17 | [5ebU1Q](https://gmgn.ai/sol/token/5ebU1QnM4Gn84oDdiPhhEnqnxYr2AgU2QpbWkM1EhfJv) | 0.40 | 0.29 | 4.09 / −21% | 3.8 s | BAM `9jxgos` | filled | **-0.0778** |
| 207 | 05:26:47 | [HpUVUU](https://gmgn.ai/sol/token/HpUVUUb2xteRCVXDjr7zYz7oVWGgT19GzmyeswtMUJcj) | 0.40 | 0.15 | 7.90 / −37% | 3.8 s | Harmonic `H9ENbt` | filled | **-0.0132** |
| 208 | 05:30:38 | [mj1swJ](https://gmgn.ai/sol/token/mj1swJMWJN3mQrd3Tzopgr1fhuBaRq2SGDV9GoYYqEP) | 0.40 | 0.69 | 5.17 / −19% | 9.1 s | Harmonic `shftkx` | filled | **-0.1636** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 17 | same | 2 | **soyas** of landx-fra3+0slot+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3oFo5Dv5aBeuH4BPKVWSWn1VL55zrySFhmjrEq9KFhajGw1UFnkZ8PYM2PmgfVVLcx5V1Lvj7HWbVDvzxto7vMob) [dump](https://solscan.io/tx/57C16Cs44S4Y5FPbKyJ1RURshdF3aEWAjpP77ZCXos8LSksns4ZjMvfSsGqpAUkgSAxG5c77CMxExiGBWYhvdXjM) |
| 2 | 225 | +1 | 4 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/34aLuX9cxEJudGtUNPx52pJPTk1Y3P1EPCqprX1KXEKbGfHJ6SXc89z83UZ8sqWM4GHJ84ys75EppM613o8pQHns) [dump](https://solscan.io/tx/eV6RFiR3WQDiUBeDSLchXCxZXb5xvwfWV6n4ZTcjUFBdUUhkGFAPBHPwvtkzM3J6dVduCzHEmEw5nmDbntKPwSQ) |
| 3 | 143 | same | 3 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5Qgm5RZhK6xptc84z5TqimrTxyvzKnBAvDosPg3rjLc7V9BibxfZ8YmDxTp5eNxfpwPh9cyeBAh1hhpw6YHHz52Q) [sell](https://solscan.io/tx/4YnCqy4GJQwWgj572hnoshSL2umwYKqNYc1gEB1AYuwgPvcE7hRzwcYUTCiV3QcPkU47RevQVxTm2y9kvpL22aA7) [dump](https://solscan.io/tx/EG7QZ4GSQM1AgSYJjaZeynRy9LG6gpKGJvPMzkg2D6VPcj5tpuu98hLXrzyTet5StbqGKiQ82P44mSB2fVoyVzK) |
| 4 | 56 | +1 | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/4iLVVTjEqEVgc5TsFXFioKTiFVyvU31JP5TgXwUAWH8EwfXuPmaHrge1r4TAiXwELybeo4YJZrJYNgXtikcxYShF) [sell](https://solscan.io/tx/5jSf7vBoYfjnLCTufH34i1w7RezbqoodFBJxtzjxceoqRh5jiFKBLrBJrBvmDJ919V4FXBqDZU3m1SdXLZdqTvBz) [dump](https://solscan.io/tx/2NAyj7dngc7hpx3atv9UnBkmZahwCj2KkCXZ9Rncm7erYN1T8skgEFaPPXQec9A4YRrrAM2VczL7V3Z6CWnNQf4v) |
| 5 | 710 | +4 | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4Ctja6qS7fchNw128vXjjSCYZzCWHdgbEZpeKzkcPH4ViocFWpHRRv5kp8cfeSiAwGa7g3jqSo2gpdxvXxJiRLRw) [dump](https://solscan.io/tx/2xQ7VKRXMj2P6hpn7YjtFBaKcoLmn2iXafR9quGXgzW4gyUmFYsvG9Sd6TSEejrtAVCGqVam1TpGqBQscV9VH2vc) |
| 6 | 706 | +4 | 6 | **glaive** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/e9oFReKMaVRaT1S2Rt76RhcENDS7jd61ckbvhAuog2FNub6XNpv4FxY5KVm6mN8a9vnZfEJhbi4PCni6w4jLjtM) [dump](https://solscan.io/tx/ZcJt3VrD7x4dnXH2UErsnZFgFFcWMkj4vinS83fCpddLmgDz4B8ivzx62vkjQUH13SGor9CPDTo5kbPjFYFEp8C) |
| 7 | 54 | same | 3 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/3paCBcdY5BYdYY3W4yaeU1LuXFZtudyeKVxigFvMVh1H1UdAqNoANFBDJMR7yWuT3v9sB7UJNMeNTRvvU1s1t4kc) [dump](https://solscan.io/tx/2p3MHUYzaHX2p95igGsfUgAhuKYJeWFNbj78D57htQwTLSZNdX1eVU4YPMsYE5H5mqejgqeGggdi2k3jgMUYcpCf) |
| 8 | 165 | +1 | 2 | **glaive** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2RfE4vXaPx2HDbAPgmpQrcFEMYmi8yJArGpHwAGuAsyd4AxTDfi1eenCrkvkJm4Pg969LoGBpbruMZDhWsA6Z6wh) [dump](https://solscan.io/tx/2seYmsao6rPWtDp9Ace5cwZ2xUGSLKrLjXp7mBWg1s1awzQDxhP9EBBHYWWvRisvebHdLLJSo44Z2C1vsXQtJ31C) |
| 9 | 137 | +1 | 1 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/5a5SSZS3qwYzpm6dKhCbKeD4FhZpycNMQh7fZ9bi9eoFZJLKrB5UhGCy97uZa8KUEqPQTUhx9z7FPPvDMzsomKdY) [dump](https://solscan.io/tx/5zeo345CvaxHJ49FK8Q2R3gLw7P8f4jrLj89AvXbBT3j1wqkBsxE57a9K36qcWU661bgqrQHAh8tWDKecfdptq4p) |
| 10 | 73 | same | 1 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/wdVnvbLBEnS6GUpEZLTbsDRPcQ3VWmvSaav5Frea8Hc1B8DRC414bisJJQp3AqZx8FcywbT5kpsS9VJxRbddU86) [sell](https://solscan.io/tx/Rti2uELwik2oMves4KqPeMJZBYZ5bagZYGfRtiHpLgfRaMefQ8j8d4j2FKny4qMa4DUAw6QjpX9suBZBncVu9gS) [dump](https://solscan.io/tx/awdRSHQqVrvS2kjs4gR2nUPEtRn6oKuyzTejXeMhcrdAAF9NG2MGjEKzNfTtKb9CnPBYoBtGRAu4kkJnNabDPMD) |
| 11 | 22 | same | 5 | **solami** of falcon-udp+landx-fra3+nozomi+helius-swqos+bolt+falcon+0slot+glaive | – | – | [buy](https://solscan.io/tx/3LzRoa5Xs64y6MMbp3AwDjTsFEE65FRubLzgFR9UCozB721MmaH2qqxh1zgmtqrbNuc5WCbzSpd14byo1R79jY9H) [dump](https://solscan.io/tx/395YLhHErBuP4amRF6A3maxX9NHmFSdMxiyVFKbToTAQR2LV7QoRCXQ7hgM3XZemAqdGB76WYQm9eXDTgoUoPXRi) |
| 12 | 99 | same | 5 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/4spZrLhcx3BBptg1dubGkcTKMQdDaWvRtyWC82K32MJJgRaRMah1JjwSyyBwhv6LT8LpA6vfM1qSc3gjKsqAU6zh) [dump](https://solscan.io/tx/5gaAZ8cxL39BGCcovZNcgsJ5CfqjeDTZasDHkUw1RKsTXmgPuW9wTNdgwaRbzxheWsm6U8qfNpcafP3B7Vc4uu3D) |
| 13 | 262 | +1 | 4 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/4ScTyTj3HVaXWauTv1WVoCXW8yX1tedjqaWcPFMnJoXEuM2k3DBgxazh5MeMExDeKe7bKj7vash9xgcxpqdnUnpD) [sell](https://solscan.io/tx/5SpngDUNKdP5BREzFEQGY8vpfmPpytge3baFZVBjRUWEnbY964A89LTRGkyvyf975LNtVkf3bnZ4h2iToAkHygWM) [dump](https://solscan.io/tx/37WDFEN6egBTKTmcrHhYwiprtasqUXrJkb3zLjH7z6Y9jN3Q2gib6Ayvktty5BXM7sCPxPk5jxRWZhit6cP57kN7) |
| 14 | 116 | +1 | 3 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/368o5deewKDAMevLVvyQE52F7YCfxXfjdfuhAVU35FqMMpjSsXzN3RQuYBGDXKiQEHpMWfasgwjZHBA3qez6QEBm) [dump](https://solscan.io/tx/5asicNm8J8shuGyBWYZZoxKGNrv8dH6BFfu2v1ZG9uZALDMrJMnPTNDxcRqqrPj6mB9d5YT3BMnWGdBMXEpatYQ) |
| 15 | 150 | +1 | 4 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/ikMV82qQP5Xe8gUnu9EktK3SARZCUr2gzmfw8nXTKLxsd2ieDDtoC1exBdUsgxxocLLNg2M5yVXbGFvkc2HrAra) [dump](https://solscan.io/tx/eBsu3bwoHoVMUemw9ZXmPDGfTSjY2TW5C1Txt8Mx5AQ3wRg2SWEhYKVLj8f3J8DMTRuf7j8ojTG1kYgE4WjXyx8) |
| 16 | 73 | same | 2 | **landx-fra3** of falcon-udp+landx-fra3+glaive+falcon+helius-swqos+0slot+nozomi | – | – | [buy](https://solscan.io/tx/4fyof9vnHzFGtHy9ZXLHSE2SKh1ZDxKMyeHJnXozuXEDPP7himfDr5GdN6vPEmAGgTtGLqdnCR2gryA1Diyicqgb) [dump](https://solscan.io/tx/2LyLTxf173XT2pCRHzaqnWBozq1hSJj2pCWvLirQDkeFoL6i8WCWe53vRPtfswSobNDowBHg3b8G1G8wENmUMoGZ) |
| 17 | 141 | +1 | 2 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3moZBiEiAyax1CJBnC8zU5MMsmNPUB7dMBGJ83YQ5TSMNbrQUFtuYh9DmjY7tbaZsfXHPLy8pprRuoiswV3oGBAS) [dump](https://solscan.io/tx/5ya8zDGXbB7BSbqhzrZWHe1uLoM28GmpANiGy3kPQBEKuS27oBniEtgkyrU226ERQj24hoRqHkdG66kkLbWqpFRo) |
| 18 | 58 | same | 7 | **falcon+falcon-udp** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2JjfDGofhT9hQQEWYU2qP36FD1ecFAF384yKfo43R1pZMgEto79ixBnG1qdV9dLWbuSWGgSU3NYGMzkYPm1qiS1U) [dump](https://solscan.io/tx/2rYCUG5kQRKRsXJ49p3Y4rfFQiPiMhfeT6GtUxUHHpKiS41nHB564Nip15CHxfvYH1aYESknsMLd8HwnCb3mVVpD) |
| 19 | 53 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/RYaTzzzYnChhMZRukPKZzuw5vAJEoLkpGcokpBYhdVUwHs2fELGUj8fmSrfM7tdTvTKSAK6dpxJrWcYfAeTuJVo) [sell](https://solscan.io/tx/3enH7pSjgbU7e2Jrduq7G4ppmAu2ZwZDWxw88Me7j6qkcqNpnFTjeycbufcbyeMMDCtJQyLGHFdrEKcTZPZHEhyq) [dump](https://solscan.io/tx/5gbvjvKSzXi7QwitufWHTUg8z7zSuGiX4AobkdS4shPrLmDCYUth4YQzBwjt7UsjvJ9JvisX5W3jS6frLyfZLsu4) |
| 20 | 34 | same | 6 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3qfMWu82rrDnJnyY8fNs4SoDbLQgJb8XHpUsqMDbAf8MoKWL9q24S49GV5qZR2r2DnyK658fiFGTMx3QYjCoPejd) [dump](https://solscan.io/tx/27dTtfMPDtGX4oXjZidwDvYjvcZTn8e1b6ptTkvu4NQWk7QtgC3TBCqKJwUNwCvPpg265XNgyHURcMWgzGp27HrD) |
| 21 | 23 | same | 2 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot+glaive | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/5Mu75AzyBB6yu3BJztK3up8FAJ8HP6M49yzhofnXxVEVHov4HsuJ6uSxLT3nCvqzoy65Z11GPz3P9AyQQNtKbqrZ) [sell](https://solscan.io/tx/2qBnHbUBScSZpWfcjrVYsWoUqsEg7HBM1KJ2sGasakq3Tp2tuXx6qLD281MmW67smrzhkn2nTrvLrXsRkyyK6oYT) [dump](https://solscan.io/tx/3CKfC5kcy8QsCguZU5Zja3xUaX22NndQzno6ScppjXwZB12oe8BmjFJts9VGxWCU1VNGqZicqzVDMeUx3rAkxwKx) |
| 22 | 20 | same | 0 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.2 s | 1 | [buy](https://solscan.io/tx/2Hj6NRw8ttWQJQc5EBueCLWUccnXaRcH3pMd1hC65ZTR2PsdAQfU8sZCe5QGiNe9LCXGirE2pfHoavav3dFdAwqg) [sell](https://solscan.io/tx/xyM1gfyiLVrrRNUYSHxA5kbufdHDZ1JY9y1sZbsevf9u2az2KXkyCVBeVnU5uhNY7BtfdDkBtQS6vwppy7XckLV) [dump](https://solscan.io/tx/9J3mu4Rbp9dTHRE1HHu94cnfkAn35NkKK7Spd2SvbFUJ6X7D8aD8M4J2GeoswBcWUFhkx4HPt4FiBC4qJuL33Ve) |
| 23 | 16 | same | 4 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/2mCuo593V7xA93r5rPZysHZw3XxegDd65GbBi56DhWxaZ2C1GuwpFiieJHjdE9HNHVnJoRfNJwm4WmxZM87ePGMc) [dump](https://solscan.io/tx/48QD8aNRp4EiiXbQuCeoU8N9D3W3Ge4ggLwsY1JDtMMHAMr5NmszWDybUcTR8t3mkdWiRjtTxopEFtrUXGrPmc33) |
| 24 | 55 | same | 8 | **glaive** of falcon-udp+landx-fra3+glaive+falcon+helius-swqos+0slot+nozomi | – | – | [buy](https://solscan.io/tx/364LdiPXqXW8hF8uk5qUaV51YgnQpqEC2fSWzgB6rBLT9FeBYuDW8DbYc1xXbQX2GWNUHcZTtNmP2jCeddqUwrqV) [dump](https://solscan.io/tx/8Cd8jFnnLd9365if8wbKY7xERnCgsHYeDTnpkxKSRtHa9KWy849z8ER9JVGAxV3WvA5RQ9PcA2FSFaTZFHna4Aa) |
| 25 | 34 | same | 4 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2VTfNmQ5vxGYgyzztzQZVxBS5NJJthChJdGmBoCBz5wPdeg9Dm7P5HpWGFVDaw6fuwaGEwL1juBEunBRjV6HTBwo) [dump](https://solscan.io/tx/2xFyayWDqHtbxfLjfs9pWiwViT9yTRreYNS1xU3SGxtJm4gycapcSQPW8TLD7WK2bmoRDJ6YKS9RSis3MRPdJW6j) |
| 26 | 53 | same | 4 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/42duyD4Muvt4KjmK2txU1JMLCcvrKnRoaEkcWbdgg2ExSS7KNLG76abAhYqMSvwL7XV8RfRBDjY6TvSeeu7FB4d) [dump](https://solscan.io/tx/5ggkvMUyEbrCr2Au8s9GFGJndrmodUbK5cQbb737FhyjE33ErxtaLgwmXdLXwJ1ty2Mvgj3JbZm8MhFnUXaVdSxD) |
| 27 | 31 | same | 6 | **soyas** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/4W1ykLwUdGb181iQ16WGaAt6pzfjj8MWSFfxB26MMBEmSU4S5aNwUZkouM8A9yETpnT6yoh5eBbFdPXQBbKTvJcE) [dump](https://solscan.io/tx/2mswEp3pYCkHBSShxTQzk4MVzjNDLRZsiFpvvRAkS3U6VzYLWVnNeBS6qMq3G3hjXau1MpYcFjgayHZsXua8Dis5) |
| 28 | 99 | +1 | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/46T596YX5aaX6qRnvAn13jkTWgpKuQ6qFQNf1AA9BVr93KLrHQEaE434prNpo76F2XUHQ6PniQ3rZLxKEV2TVGN3) [sell](https://solscan.io/tx/vn6PtAN4RQ36r9Xgjnze2JDM8Gu2xSMgoowgGy9SiLbPrB9UotCkHaJM2QVqTv4AJJ3ekU4Ak1tMZJ2Z19Tn6H5) [dump](https://solscan.io/tx/64zRQLENgUaWraU6WujK4qVbc9Z9MT2YusevDx5ANgyuDHoXKWrE6iZnVEpzS8LJND9mPeFvp19z9DN9viE27e9Y) |
| 29 | 28 | same | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5GznUq3vf1WcdVTzcvdN3xBXWzWWYxCoBdEam5w7BSUj9WNzpnPpByiEwHdaNHtzCqR2iv8LW4RtKSSp3k3qwe74) [sell](https://solscan.io/tx/hht6yko3DV5i2zFWDE9D6WBGCfgKEVtyvhoUkiR61tmP7zWFxzduRBKNrzNQtknW4Zs93eK4SXm9MqnsCHfY1mN) [dump](https://solscan.io/tx/2V9P9GwcXNRk8dx13wkG7ygErRuzHzkFa9WZhiX8paL3ULmo8u9pYQkfT4PMjowSTjEoYFudwv7PbtWo5RWv1Etw) |
| 30 | 116 | +1 | 1 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/3XVHT8d43TcKSvjd3D4s3LB8LHnfADtA6ckMbmu2Au2Q9jiUeAU6MBJcReV1aYeWXnUjn9phhBYX6EL5i59NJipd) [dump](https://solscan.io/tx/51czaPRpPmHsxH53bDEKVaBeUCJ3i7GQgiLiqT7c3fFUFDqm31soyfhhxET2VV5PMfJv1rrnW2jyqw56k4vbt7fa) |
| 31 | 87 | same | 6 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/371x4WVRLHm5tEd6TeFnzJETceeJbaAJAZtbS7Ro3xqNkDVmoW9cwCKPedfA2QoLKU4vcPmBVthRyvQ7jZgUQvbs) [dump](https://solscan.io/tx/4oFcSkayQyL6roqNry4k38U4XC6cagfvz5c5ewxoP55Y6cvQEYzs8CZCpTXKkn4WtXrAHznV7Fcca4SeczBgveqx) |
| 32 | 124 | +1 | 2 | **staked-rpc** of landx-fra3+0slot+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/Y4zCh1BBUtPjnJCmWP1gGZSjVTiWgEbth9MKjhqdLgdYv4XHharoibGzSs1KUFskmAazNAoQxyCndzZDNKrjSwb) [dump](https://solscan.io/tx/21iMg83Qz5DuFTPFKsQhgZT4zJwrVsS97vWPdhYyjhLQqTquXhm8N746K3p3NSPkthXgmRmtEc4rFrEUimBV9dnD) |
| 33 | 158 | +1 | 4 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/5gsA7gu9Lg1Saagjvcpy8radCmpV7q4f8p2YTsajMFAWW2bpC52st18H6t1BALEpbyBvzed4c1nAHjc1LbJ1YH2G) [dump](https://solscan.io/tx/sPaEqFRF7uKcqbXk2NTSBBdoMd7CfiYUkaMNvz9HCS2df9Db3yxa8ifBkzot5UjQ2R5uShEYF2fikSBsKfcXDrY) |
| 34 | 40 | same | 2 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/556pNDRoZvZjW1QkswP6AWxwP7AdA5K9hdqSzb9wnxzpTm3ob32esC8iY4tiFkfi6ScyePiCx2MazzgP2ngFnJor) [sell](https://solscan.io/tx/2XoL6s6X7nzWrj4Z9QrwA6uTQmFE6pMxs9Pg2UYBGF5KodEcGDgRpEboYD34zAEkRX29u95Q8seVUqfkA3u5hp7P) [dump](https://solscan.io/tx/4fR8ALf2RTTkvU7BtLmcZ31g1hCW1vZXZYPsumuXtUCSUMTVJF4QvCX1WEeEWfeAsdXUbnX1KDmm4EF6mU59hheD) |
| 35 | 39 | same | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5ehpdzAGZSiq71d29er8rSXxWGCPHXF5gSRfn74fkBr1DHSk4LrzikShbBfnHY3oRjbdosKxDsEduQNLX7MKir85) [sell](https://solscan.io/tx/2dPnSZ54BqrJ6Zk8YrMXQYVNLXr1osiFC4pbdgzk1NQLU6FHne5p7NjbfUvWwRmsV83yZ3QiVv57TgxFzohFeKNK) [dump](https://solscan.io/tx/3o7jYE91uwqcsVPpnQfsYfm3aDXMqUrH2QdfHgw7U3LKzxf1cqCbwGSKp49XJEatXsgJfv1Vc71jtHfm8D4WQxGS) |
| 36 | 37 | same | 4 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4Dyb3CTH8zUnhJZDAWptwYdtxsmvvh9QSciduMAxErM64yP6DKbQF2ZGLvKUNbw9CY7AdKoMj3WVd7bsHJMqYJcc) [dump](https://solscan.io/tx/2GASy4EXB8ziphz35Ft3aNXYj5LmG7vS1EUcxBdRq34DEXdqpzYfQAFg1EPWUr4C4DEprmZS9Cp6E9TYxeatGQSw) |
| 37 | 43 | same | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/62kdmKJQNgKxkpQC1gSZizcbQwPjBKJiukRTFNfg7Ph8FdJfJTTj5YcgnHgzYKr48ow36BcZG3S49WSffpKa8nC9) [sell](https://solscan.io/tx/2ctSKUG74chAyyt5mnKv5esUyA7eLovbkPb3U8xPgZpMioKNE2AtZNEnejADy2Shq7jjNCjhMJgiCKJ9zPFZr3Qg) [dump](https://solscan.io/tx/8um4sfom9aoscx9S5ncXmRnCnJkFEVNfieGiBtKFtnJfuDNYq2PB59KqHGnBR7xqXDxFDdgaKnWKkDLk4JDxmGu) |
| 38 | 61 | same | 6 | **falcon+falcon-udp** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/mBsz7NxkrLVwgggLauBy4wT6eDtq1zVMNADgUuWDAudoJfyikuKb35PAgK1D1C9DU5sbau2gkA1iJzyRvyH6bhh) [dump](https://solscan.io/tx/5mhicnVycjUwy6yB9CH8pnsrjBHK7h9orweVFAu2gPVK7YWRGoJFKMRN5NgheMqpe5t3ansc2t8ECgpxLGVdVWMG) |
| 39 | 174 | +1 | 3 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/2LBksn9nHD5jPF598oKa56LqmNV8p2c35V3fVEeEvMigJRtRCyaKF11ydRcSEtDJP2x3VeM6dT2QZNxkQUV581kw) [dump](https://solscan.io/tx/3R536eqykk4tNBS4RNBNqTPr9gj2x1JkTcvzMM2XC9vuGwXcnSHneWkZsJYjQuLZ9wFGJQS1anLdcRALzp5EKGM5) |
| 40 | 32 | same | 5 | **bolt** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/3KhAcqh57U44erkS6Qw9ikXJBAz2PjXM79q1dYdBpdzis142e129pGduzKMWfZRTEUfuBS5jz1KbBkcxrzTY6Jbz) [dump](https://solscan.io/tx/YPzruBS8CTKPDwfrYUZznaDsZzdsjoQFmb6KFdqMrDY4L1KvJ99DgvYEBQdXoqLbHCGx8JhbbT12SKDZzQmYkk3) |
| 41 | 131 | +1 | 0 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/VG7CArQgFepTnXUAXbbQgx9EbyqbtE5GhMVAiPeBTyCEp32rmRrCBF2BnW8sRt4h7VSrDs5a9JkB1ZEJYAVSTuB) [sell](https://solscan.io/tx/wpc51ij17zNSemhUGHKnbqLqkGPe5Em9ekxvMP26stc9nPR22bRENn5ix1hzkybjjoaKB3S7QVavkECYV7QrkMM) [dump](https://solscan.io/tx/a8iVA6JJHTnuNrNNWBsgtf134v5n8EfJ8qyb8d1Fj7ErGB3QtMPdskFHnC4rFqBQPi8o4gbAJRtAiUZFdvUGQ8K) |
| 42 | 57 | same | 5 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.9 s | 1 | [buy](https://solscan.io/tx/3M1tNHTCnBzmnBfjAMU7J5614EttaNs7P8XdvMKSuxKcJuGmtDoHZd7rCryP2JaFBS7fHW4hMASBGwYEt9JsH6W7) [sell](https://solscan.io/tx/59ad4zHiTNH16vEdTN2tCZYbQuqC1yofQtDyoXWLsnN1bqCqBz6CxdUZFiXQsQyTZxKD2zZ2rVmruPa69TB1cvLF) [dump](https://solscan.io/tx/2D2zirbQNdSpcecTmHS9ynpKt4bhg3XTiaWuCk3XaenyNUT6136PfU3qPLf1hDpvecgFGG3ThaKECDCdF17bt6ik) |
| 43 | 69 | +1 | 3 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/3ih8kWfoZ79XMKLiKjruYtDNNikVj6R2dvYtQLmgSgcYmtHaBWuppHoHmcEMcbmh72rMmBenk12DRKrwkfvbmVJZ) [sell](https://solscan.io/tx/2HNjPSRzkkDMR3SznyBPCKisK9NxWehcoJo7REmvuSaR8Qo1BP2y65H49bJc7DnWwXD4yvXg1768dbqmtVMaN65E) [dump](https://solscan.io/tx/4a5AesGLy7DLYFQUCexxvQqWUQt5cP6QadLLSo8DaMWN3YPgXgKvmp8YVPTAuZk36SUcA5yMocLVriPMuSnddWWh) |
| 44 | 39 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5bdDt1PNWnr68Axivo7zDRcPJ6mtrKPzRuP3eVsZfv4nUaMVtiJ68XHGB8esS9G1zbFzXFcst31YZ6LEUmYGYFZe) [sell](https://solscan.io/tx/s8DcrSDnNjYnVzk5aV9Ya8JdvVpRrUDsGsC6v1AymwoVoKkbfWNcufpJGuuJ4SoxPGNXRoFprYMG9Rp5vTSPtFo) [dump](https://solscan.io/tx/4DvnrjGq5vbkbMmzMJMd6ScUCCHg6JMPxSkG8rqR1SuxC11PkKpUyt5DoVHUhQQECEDMnY3rztvkC4EJSv9yphHh) |
| 45 | 184 | +1 | 4 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/6NAYLkQjNLCBbx1DofrVnGWFjPEkZH4YNNAihwFzzVcHQyPoLarzpmuW31yzc9xjgZerBzKNoUevSNtVJXq2Hez) [dump](https://solscan.io/tx/48yFSLc8zkA9993UZaEyMjesa55GraW36MbyuA98eN3aEb99nSL4GjZmFUwZhRRJuzC9RWqY5wyiMfqPjmF9UhJP) |
| 46 | 100 | +1 | 0 | **nozomi** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt | time-limit 2.0 s | 1 | [buy](https://solscan.io/tx/CLwSwDf1nrVUd3G9J41kvEjNGgJGPsy5cHpeAUNYj1mJ7TKwZrymirs7GAudRQgWoC46nbbgEvwVB1QAttNKc97) [sell](https://solscan.io/tx/nxsrdcLdsKqHESPuvJcHidrJnfwGUecjnnmTTRmHS14moepbeZdx2w6jkz6TXznBza62ZZJgkaTNdotC6PyY9mK) [dump](https://solscan.io/tx/kYg32XcVu6daNvEvpyGuW7rF7tB5RrC1KRVQ2cRm2BdgrXDEwUzHjD8RcTxLgW7B462HMqn8KGvJVZmyofi2Vzs) |
| 47 | 157 | +1 | 3 | **helius-swqos** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/78hDhuBYfzi13WHLRKBEcaz5FrC9MQ4ppjoVFb1HLVPVHgk4RJ8VmcVJgizMoHo4Nk1QK6Fgjn1yLMyFvRJ2sGW) [dump](https://solscan.io/tx/5fC9GcWGqFVxHniiPT6bnMap7RJea1oEv2dhuJiRWoELTWoAoY1H9sLo6opYoehy49NRo7Df3fxRpEvZQFifPfw8) |
| 48 | 35 | same | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2FXBPzNG1RNXxRUpTsknZkXYw6L3Dd3tiRhBFuSFXjbV5q9hLssgrkVZspEcV7zYMZUeoz8urzo5hYgQwtwbPMms) [sell](https://solscan.io/tx/5ct1goAMu6HoFodQgNwsGgKTDqbAyVKLo9uu8dq8i1ZwXVF1XeDYSk17G5rxZ6dW1SE72Frvnk9aNYKMcXtL7hLa) [dump](https://solscan.io/tx/GyEN8PDJE5CUTSiAUJPdcnEnY5DKE1cBRv9EMsbJLxToP9MMnDvLhrgLBd8a84nSnpYmwsd2h8DStaT3MprX2k1) |
| 49 | 54 | same | 8 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/5CfGUekgXduVN2yk41ezAq5JB7dYQHXT8vYohKsrVNqGLZH3GcdR3syVwTdJ5uRhyLkJZf3iB1D74FsCQaSqpap8) [dump](https://solscan.io/tx/3deYinwxRStmr974xfs2ffsZ2VgQHUhCd74kzyGo29r72XonHGZwrJSDA2MadezJNrZrBbAdWSiepviDnsCJDAJR) |
| 50 | 32 | same | 4 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/h4vmSiGX8EEpMamfnFyq8tzCPAjJg6yNU4WgNTAme26QFJfF1pikJ9J8NCcQQbUj6GT6CQJfsGXw8PkV9HqrouX) [dump](https://solscan.io/tx/ME9xWdyLSJ9MEZ14q9P74znT9BMom4DuU1a41cyNKvZwhxnXcRzdEAK4mt9hG7SAW3Gb8LzcYfj14CANYA6PMGv) |
| 51 | 189 | +1 | 2 | **staked-rpc** of falcon-udp+landx-fra3+glaive+falcon+helius-swqos+0slot+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/2HwEEWzCxWsUFbBx8dTofRefBizrvaAe2ZfmNRZ2fff3Dy6bdx3PfsYebdbDQfKZfL9VivnLWKJgP3tVJ2wofuZh) [dump](https://solscan.io/tx/55tGF88b2a9FrGwsSRyvY1sDHkkUXyU9uhdJ8KAf3JTqzbrd1d61LU7ESASZRHYH3QNUhkEnoYNKHN7qFrNLS36m) |
| 52 | 62 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5Tn79dFfeMca4veV2L6D1Hn7ZEv5JniYRj7AbwuMnGGNUiArnGwLgz43mtFzB1y3dJRtvBHS6XZAAnHdS1EpVKt5) [sell](https://solscan.io/tx/URDPXqW4Voxw5RMB7jufAHggnZ2vytkaEmJT75vxyA9HZ4eS2MgfHRsgPncWkai2pCbBkEAxYpPtDRWfspamqBv) [dump](https://solscan.io/tx/5sS121WNxZdjdKhQxhjb3WPJmiu3t4gTbzNg5DhGaBPqFXdrWvqXBQkrwCaj5b3KfMXLgmfQpinDYo3Romn1MHj6) |
| 53 | 43 | +1 | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.9 s | 1 | [buy](https://solscan.io/tx/63nnYneyuYFU7WC6ySYrZtUhKb52hww9zPTXfCRup3uHcHk9MqHbuVxhvYsL6RY6t9FJDXwuWZgXfFpCmcaZ3MRK) [sell](https://solscan.io/tx/3VTepfKoX9qEsYPKtZ2MMeNKStEzxE8voRsqoUVfCxC6kdLf66bzoKE5WjdQLkiHHmCT4kUSSnPAHED5giQNcEZ8) [dump](https://solscan.io/tx/46UP266sKBhu6RZb2HXDPFmSB8T12Xe8d2G45pahXEmvGn2aTyMN7Z2X6mNzzjk4iqmaFkEHtpt9r9bfWinBDWxa) |
| 54 | 21 | same | 2 | **glaive** of falcon-udp+landx-fra3+glaive+falcon+helius-swqos+0slot+nozomi | – | – | [buy](https://solscan.io/tx/4zJTxsVgdqF5asX5Z9jnnCxC2UafkvhnrbcYANk9CgTBtcM2R37optWF4WQzL4Bifd1nEiAWZGr8UsCjnvwLuYpu) [dump](https://solscan.io/tx/6a4fYeM6vzf884afyrn4gipGeNp6cTH2uVBjJeD42uc2x2mz9gkGvW5NCC3Pk1hEu5bjmGJqgGoJs4zjrE1yDrd) |
| 55 | 44 | same | 2 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/5p8ghJqpseLTmd98e7XvRe9fBrygenYmSrqUwfrPNm76spkQdg3k6vJyp4zjByPxKEPR7hXjKeqGDeY8VRUZiH3C) [dump](https://solscan.io/tx/366fXwZGTXpyyMRDpadUeU22sjPAkWy4xqWGz58YPAtAfmWAgRAVXnrccHZqkeyygxBmTWNDkLXtdgmwbh67GXm8) |
| 56 | 33 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/ZvnaktBQj8uhd9XKfYcNASsUCFfUVwbVC4YVZ9Fnk8V5cSzs9tZFF9Mbq1LnyEiaypRY2RzfC4z8b35cxCiSjM7) [sell](https://solscan.io/tx/3SvBahoEvHmHkTFRksbvfwJSnmXpyoJbGa9ghMB57tzm8C7JAB634p3tf2kCytUmPa14gddTya54dc379hUYW3VA) [dump](https://solscan.io/tx/2ubt5QgDZAenAn7ZNZhdMbHfkSL2bd13AjwBbLhGhyUBX6YDPbqub9x2rsrEY3TGcBF2FMTtPYdhzspwcLeMgd25) |
| 57 | 52 | same | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/4C7DdHGB6ji1ZTmcu3ViBtRFSCUEEX2bnoHzkG1q5zTYB8swwyCKgeSNqGZXNZ3JN4zYk3KqsM1zZ147N3edn6Dt) [sell](https://solscan.io/tx/2EcVwC94RL93TRf4KksUbMqHGT28vW6etSyQGGJV53P1YFAPZSWKE5zw8Hy3e6eG3F2o9VLQe9JdbZqVUkxuGZL9) [dump](https://solscan.io/tx/3BU33ehnHmD4P9VQMoEq7K625hNJSrivHTk2Y5ovVveoftyYg9t3kBb13g9SBwtwYa4ru32QpoWWAp6612QCQnX1) |
| 58 | 92 | +1 | 3 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3Bf32QBCARyLneaPBse21mqtobD1LgwWKuBzg5KTnNjfyy5cGiXaQz3KCT3yMrRQw9kTHNFRowXm111D16M6wwNi) [dump](https://solscan.io/tx/23WwrwGnko66cw6FzppWAF5jfgsPAVD7sBK7DtNRJuggSJp5fvoj6Y8BYw62JHTmfYDrxnDimyJ3LMPYYi1i9xbB) |
| 59 | 625 | +3 | 7 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/1mh3TmEHN5GXm2cVDdCt52diWka5JaW89y5LHscCkXSAA9XUKFanhyPnZWsFddReQLofKDSGS8WYBNcpr9Lbsb9) [dump](https://solscan.io/tx/5hCFUbvuxY5orMJNjKKg8C6DxKSbKdBqVVVwhptxCrsxrKbuz4GoJBezimuJSX2GFm6UTnJ5AZC4hytfhjFfHWkG) |
| 60 | 42 | same | 5 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/52GVn3L2JkwqVGHTWv6AmU7tYeorgJVjFRpAwKESs8SsDp12gXf6rUjFz3n8bF3p9412FXa3pzXutbVWFbieg92b) [dump](https://solscan.io/tx/3ymeU7RQRuZQsRPmEJYhMmpZ1JjxR1gjhhnTTJYxG5o9CYgSAo2iWw4UR7Us2V3TPbcnphCHLVpYJVDXPJ7tg9oz) |
| 61 | 25 | same | 2 | **0slot** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/26PsmdJspUfmpnPqyCjSdDcdRgmQPhTeyQptLCMMgsJe8YnjCe3HLtpGssNzMAunYGPWRz6ifUdprpbcr8YUKVun) [dump](https://solscan.io/tx/3iCK1diQicgJD7EbrQEfoj4gN8wWt2oqmxWvih1a7WRdzgBdKGEpbHfhYqdYNXJugc5qd4ADAfWRfX1sLo9C6w9n) |
| 62 | 40 | +1 | 1 | **0slot** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/5d2cRDP8yc5CtDK8ZuCY5xjzPr444bHNF9U692M6t1YT8pk4Z1ctuMXWus8YaMyX5HKy4WYVgA6jou9pZkZnbRyH) [dump](https://solscan.io/tx/3AzB9DBQ3ja6CrRpjZpkheNEmFTPfxu1zqcD86hVUJdtppLfq9Vg957HerT7oSCUHvfxhmW1L9YJLFAZSq4bqmfw) |
| 63 | 68 | same | 2 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/zBH4sq5nXD9YxoYxzpSFekX3Kc6pdADSDTtNpZWqJzYBt3p9JSzmn5hH7Mx7JvgD9BefbhFzCKCruZRNBWCMz5h) [dump](https://solscan.io/tx/464jXujoXK3RKbvLSwdxKc9jv1wKgzxvcdwqPH86wLps15LXEf9e5UDxqukpS2r3u24uD1pdpW5w13BKpW1CDWMS) |
| 64 | 18 | same | 2 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/3rgDVCAEECHPupG5gbQqr4Sw3yHNvSeSfJFQxuKh46qSrB9eP4BrRMQebo194cCMyP7qcE3dSFU25G4DTXbrk5L) [dump](https://solscan.io/tx/5pUxp1NxvwHCiwyEtm36PQC1YjEZSSBbPN9yNg23q4qkuyKgP295ZpXEB2KPKejeyzckth1wzQsQrQFgjPDf6qPX) |
| 65 | 33 | same | 5 | **glaive** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2RyMWRG2XNTAN7XoUuAdVXZe75nrSiHgLT3dudh6RKToGrDw7nNnjtBoxhhsxdxHKEnCvJHbCxsh5FYnvcqGKEUK) [dump](https://solscan.io/tx/sZfvq6rAo6WZ5W7QVTNzUasVcjfTLYhagkgDdU2Z3GB4FMvNeTdEjfdAn9DMcyHEsNQ2q4wPhwWuoyMaqWyGEb6) |
| 66 | 179 | +1 | 2 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/3c4b43ZSuqtDPdgRgfMbbJUxu7XB8y73sJZTURzjTgaakp7k9X874w9mTE4oSiPWivX1gNJYRW8k1nhTpKziKWbz) [dump](https://solscan.io/tx/4HFmpyuJKAXeqJXseTey5eu2VEke5ktNPATd2JR9BMrXUDxJqFdMYh8QFXY45S2MSVCkBqVqRVBdW8GG7hjKezXK) |
| 67 | 30 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2nxVKArUrhu61vFnsKfyJf7AmPAFm5HzRv3VftMeaoyZHMwqt82A2Jh1WhtxziNFAwn5iGR6ViXapPujPRxJG1Ue) [sell](https://solscan.io/tx/Ynp2Z1RYmRhnR7yWzzBTiJLZGhSdL4Hqf5KG2vAX96BFYjYrcJzJuEFDXNmYLHKHTzNnzDCBhF9D1xAv2Xa2NFm) [dump](https://solscan.io/tx/575yKqW4qzrsMGTNKBpyXWYiPKB8MaqU3k9kmXKRRcMDqDrUzbGeuDTwKryrFoCQnyV2a8WWFTURQXt4vebKnd4h) |
| 68 | 23 | same | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/53izq9VvqEB9qtFuN6gJCrqvfXzujNDRa6gRPpALfBr97KB3Q6syvfCH2f3YSTNrGiiW6xZjJaj1SmDUGLjtEFL3) [sell](https://solscan.io/tx/3ZPoaPijMinJVuCKDXJjmnbqhn8rZrHUeqJGySrZBK9gzjaoGuycfDWcLL52uhszfkysr1bnFHoE7gbVtGchb9m7) [dump](https://solscan.io/tx/4BC6g13WETUyht3JACwqsvrRuLEGJt8pAufEZ2knqeCsMZiLN6DHHvYKhdpYsNoGPAxrhy4whAmzs6asxWb5Bxiz) |
| 69 | 89 | +1 | 4 | **helius-swqos** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/5XeUQkVnee5zL2vHr9fXgRvVf843xU2JAJRXPqUgzVSVNWyWtrRkUEB3eqXdG2abaPJAwu3aCChXK5MdsKV8Q6ZD) [sell](https://solscan.io/tx/4DPKti66Ec7WyUYyWSqRPMS6yCk1DBBUp8sXcUZL7kqbWPFQ5B344MAH1XcHLykYtv48SzgxSii4mAPEHuiJfg58) [dump](https://solscan.io/tx/2kSXSNZLNxb3MHUR76ZRfSnW5JHWg5pbwchvxvwTjB9JBGbKWVkEG8JJAEiEHc2CGqCXSogMFEcW9jVH7FJKqoHj) |
| 70 | 138 | same | 4 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt | – | – | [buy](https://solscan.io/tx/487Q2p4K7gao2scRj1bfhV5GEidm2GcUf85pTiCccbs4tzTMsfnMHdzDwbSmrA9EdsAytFFvDdTNYPXz7oZSz5RD) [dump](https://solscan.io/tx/3DAfxbMrHURAu4Fn71ww9uQezcxQdydcB93z7oK2X8k3rfUKJWbmCS492Z9LTAdJCgGLjVjhJ4DC5EcnzvAdjqTr) |
| 71 | 94 | +1 | 2 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/5u6ZjbwQeL1Bv4ppzYweVZ48VnErYBasrqeVwQ8226ePon8u5xF3Fu6SGYJwkUnHWUZR9evLDQsMqt5RKTTDncjP) [dump](https://solscan.io/tx/4KiYiJm98XDR887ij6ueCXxCqR646BJcb5EZozwzoSRYF73KHCYnWkEJWyqUFSrpjcdzqtZGj3tKPJKGsg5o3yjw) |
| 72 | 152 | +2 | 4 | **glaive** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/583T6KrACxVoKudmpM2kWRBvHjzPdMHUTjsSJdisK9ZHSvWLDDTFRbVnu3jmQ3TNd3JJgPzkf4QbeyKh542Ghv5X) [dump](https://solscan.io/tx/Jyne9pyJRfWAhmGpesfZWCak3BzYstEJfhV4NAK2wfiANEBt3wNmN18wHfZqPeK2w6uH4NBfYaQH1usK35VeGe9) |
| 73 | 86 | same | 5 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/4SYz9bVKNDov6ihhuCDzPLbCZzL8Z4rLvNLBsWtdmiXbJodTNVjqtwo7WyY9DTPVVvfiBo65Cebjq5PwDMrA3VCL) [dump](https://solscan.io/tx/4wQmhPQz3sGxT4WnMqegtBi96ZTZjRoSZZriDvNPibXj2UFtPc3MnHSJWvAhjJfULywZ8pXK8jK7cgvxeQynzxBA) |
| 74 | 45 | same | 2 | **0slot** of falcon-udp+landx-fra3+nozomi+helius-swqos+bolt+falcon+0slot+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/MBEbRxECuTD7J1K9P61foSRkuEmWpYxERe1gdyj6oMhkcMfAvsyYwh5DiZQT2nJTZ9NPz3jzc9LWb5BKbxHPNk1) [sell](https://solscan.io/tx/39nNJYhXwVBPn552Ci9YZUcWSaJgJjGPaVCpybsJSxdvt3FFSMRe9XSyQgosrRPtePPugFrpiady2YuRpETAZaHt) [dump](https://solscan.io/tx/56tKjRjZnLWeWNp4FAtjWrrtXs2yPMY2kykXRa5QtER4BRFiG8bdgs5daZSZ3dwGybssMwbeyeziNo56tbq57UEL) |
| 75 | 29 | same | 6 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/1rv4wpkvSpvw6ZuzvmRa47P8SJtRjFcYecE1EGmSDKpMdxbhNABKUbQ3jsqdK8UZdufQg1EFTWE2QCJX9qEbgQq) [dump](https://solscan.io/tx/4fxhcvXhy9E3Sps9M91tpXtgjazxT6msS1Y3tnwd4R9zvxt5HMuszfcMTzonVHmKoLt2Mi82nZQL93c7tLxufhRo) |
| 76 | 24 | same | 0 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5N3zuqQBb4z56e6PEgaDmdp7j15QrF1VxJquPCzFXLCgtwhpWU1MajW8CT9N3c7syVX6WrNjzTmRn6FQkCyAn3XT) [sell](https://solscan.io/tx/31HYaZfqxuLUBPdUmSRkikd2jN9cHnTYH52S9wmKwY65kQ6e7Wd9L22t5SWgg422jsxWy4XxbmSgTgBchcovPLKA) [dump](https://solscan.io/tx/2hjRWFBzEviqYuceykcooU7X1nyFidUFZSBrBG8iwphn5TVgGk5Jqj56H53QPEUkdHCrctDS6pyNXR9k2zJzeLaf) |
| 77 | 103 | +1 | 5 | **falcon+falcon-udp** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4TDsgzWRdD3pq1q7yvxUCPGf8tPJYoAugo2Gs1oNtp42cvP34wSYzvoJb9D4stJXA7SZoyK7epuMSyty1j7yg5jb) [dump](https://solscan.io/tx/3SZpaEjNkikGxpu6oSsox1WfPqoVDoRSWeGALPMJ7Df4W5AdG3F7rGNBSaqDW4qorgGubo8X4cztFJo7TA5k2xpL) |
| 78 | 18 | same | 6 | **falcon+falcon-udp** of landx-fra3+falcon-udp+0slot+nozomi+staked-rpc+glaive+falcon+helius-swqos | – | – | [buy](https://solscan.io/tx/4N6k3SWMs2Xc16WQoFThnmioT71ce4wigH9ewdSes7ctm5ZN1ubgCyQbqqbAB5FDcXswooUnmFKDTiVYoojDL8xd) [dump](https://solscan.io/tx/4fk5ZU3ztiWuvCeRM7KKqsFkFMkiVcJhvr7bcgsJzvdjnhq51xf7QZovpZYMNvD8BiaQyx3d9NHPUB4mLVGq6s2R) |
| 79 | 85 | +1 | 3 | **soyas** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/ebVgPHbrbFDo4tHZDs4DphSZdwww2K8E1kkQeTPkRGEqHkrtBR4McgDbzUz3UeFSNg2UagWAqbMWhAa8rphZuAF) [dump](https://solscan.io/tx/aTHRPa3MX3tqwR3NguHSjQzzkobcsvNquoDX7Z2YvnkZHs6P1ZxYeZTCcxfUYcsUaRRUui64KF7fVnLhsvPVz8K) |
| 80 | 42 | same | 4 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3Nt4AdxvhJorjdeZKUVghNaoTQMRTAKmdq7GSaGQxS2JUkiv8BmZK9ddUBeNtfWerFt6JYunErC2vXSae2K6MgvW) [dump](https://solscan.io/tx/266yDbRjF5Q2yhJgmcoezsxsNUx2Bc1BrQr24Fp2XxZB3HgMYm1qmEY3DVWefPiBhTUXEk1wSUHGo8HF6kFWoEKg) |
| 81 | 71 | same | 2 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4NSFJD4KjEawnHZjc44oeHSB3Z25V9i79dUBv4EWVYk9o6UdBebqSBEdUB6RxsgP9iQFMehE4FXVi79xdL35dait) [dump](https://solscan.io/tx/2RDBhk6tGkr2CB6FMg2aXoStGEG7qCj78GeWgUGm4ZLHLGLJN84Hw2mDXYcffB8FaFzmovfqXiJBjkngtXpo1vLA) |
| 82 | 14 | same | 5 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/87jYF8FL9NQnVw21p19c8CbiXcQywZSPQT714AHsWrUpJ6mf1DCjcWgmm8wyApSfd2jLNo7kA1A7jC7zCzUtitp) [dump](https://solscan.io/tx/pGsHMCyZDiWKvKEKVXVLAZci9hB78iunErtz4vLsNpxFRNR2e4Zz4DUUB693LMGUeECRFhPwzFFF5Giq8tr9fbH) |
| 83 | 26 | same | 5 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/qcC69FPvtpWSYN41KnkdJukLWH4aeupdhq4c5xicVWBedeAFPDayqxudyAcyY4XZFD6wWaBCEBDKyqFdgS4PZLs) [dump](https://solscan.io/tx/3YgrowUyWiUKzNfDqMqdwxkB3sUsjYJt9RYcjAiCWPGSAY4XPwZeU5jEmTcA91p2AxZ2FPqXpuM6ZUR4mpvQTB6d) |
| 84 | 148 | same | 11 | **glaive** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4HA9av2XtH2unyr6FM3QJ5K14ixNaKPeu9J6yPHu8azG3z8TucQNQ2B6dXkgMovq5sdkiXKLFiu4rZthydNgFf5F) [dump](https://solscan.io/tx/2JDZcwcFqQUprdrVDoJRT5xvXfGjPymkxQkb2KQ3VeSfSd42cy32ZZCqNR8JRcRXNTZRnrLddhCmQS6jo5NgD32G) |
| 85 | 49 | same | 2 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/4xDGGEcxfQcv8Q6PcJKdSx58Sg2tQXBtJfmwm8hhMjhZLmCNfTRpg2M34zJd5d3btVCeYLBDF49EM2nTw7xbgkJ7) [dump](https://solscan.io/tx/4NhAgZfwm6JqdrsEcqVTzgRNjkXwsvnqUrd4i6Fj5Q4UNVGWBhZf5TpNsPD94MqRYkGCFfHsNVwHZKnGcLJAwNhf) |
| 86 | 63 | same | 3 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4zfmnsJALp4AasEw6EaB8AwwtLmVBoFT7bfL47ZV941ZPWYdJGWDYNEWEVRscT8xc14YfFqCiMxnTaMdayUQg6Ze) [dump](https://solscan.io/tx/4EiCHfXZTpEvwbgTDPkz4732X6e6Jiz1mbqNL6o1eriPy4Dyfe6D15MRUkwt5mg8WeGXHPjtYbsBpTk3JouCsRtX) |
| 87 | 539 | +2 | 31 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/5z9vT2jzAh59QyeGk6Mk9VCh4MqNiox5TJDvjgxEyVuRpaPcLmT7kBCD8ckoFcaBqNMNuZ7WQnkaZpknbqThcvs6) [dump](https://solscan.io/tx/2r3CbPX7EmEAQ8UmRLZRjCBEet8DYJTbQoHovUs87NS5envFrPonkw4NwYw2gGH5fHvRWXW8dQra1AVGGcfLMSPs) |
| 88 | 40 | same | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/2ow9Ko2wPbBcTCHa9V4gTBWMhn9fy4WTYCuC58Rf2AGZoSC4ZDfKRhppgkcqaSfiYSkAinhqcnAMkD7Srxm5rRx) [sell](https://solscan.io/tx/5PVedLRsTspdzTRkkWxpyhwSyMUWdN4Li98BSB5uvCbp7NHK4D8AiwK2EyPQM1sDpwqJ75BXwmVqNo99aLi27biS) [dump](https://solscan.io/tx/43bSpbAwv3oKGwqxXXpXNHsDdJLyWTZzpNU9oRYNijKnvY5eqWxUQ354LMWjwipFwFy6k55rAJCNjuM2CqR7yyGU) |
| 89 | 57 | +1 | 2 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/4HobWMcyMh3yZ1JXTug2LwT9GtCBBrvFZAGJzQpGSE2zZCvBRHJdoN8CbCa3zREBeufGJSogs6D9Cj7iWWC9VF81) [sell](https://solscan.io/tx/3vdoFXZPVMfmCMZhmSSKBiYrh4icCRMvGTvfZ9uYKa6ZvWxESZnMojY8hf6j6tUD2QSiKphvZc9Sb744CYMVE5z9) [dump](https://solscan.io/tx/5kZF95oyKo3SvN59HGAFivbJYdj7eYCq43wzYxhWaYB5NTRPpunf5WVNRG6KwzddZFYfHoiVzNgCrEsBTs8T78WJ) |
| 90 | 98 | +1 | 3 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/5BKRdqMfaszjNdh7Nfmq11HHbPeaaDeszrM9AaJhoufgYbcAEDtyLhxhzGtdGGonn72MmdGx9PxA9XrabJGQ89F) [sell](https://solscan.io/tx/Po6FsgU3fyqczm5GMNQWwxBVtGF2akXqidGRLsPy7gH87CpjqDzrBTCvVuBjveyrxd16RM9mmpGGJKiYUdumoHE) [dump](https://solscan.io/tx/5hw9aG9wZMCky913qpxkf6Pp7AUhcgd9fbRmakuoB9ZdjLz8nijTDEV7n9zpv6J1hgDixFJSve98aXGBEGEV1yP6) |
| 91 | 41 | same | 5 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4WiWZMo4vd8j8XHcZJLwGDeDv55mcXZwdyFfuu5xZgZGjLJTsEc1K1Ldcp5rd599pffqSqHaC6vok3mJvYnrGfkr) [dump](https://solscan.io/tx/3nf3YJU9XthCmKejuDmzsQfktHP5DfqbeWAc4vR6VoEi5phtruLD83Z5sE7YrY2MoBM5zHns8ZT1m9V9y5hLGitv) |
| 92 | 20 | same | 1 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/NCdyQrrQeufMdeXGvACywqoDiT25Bd536ZZEwESE9cpC4QRXVFXPvCaZrMQu2Yz2M1zHQaMhhMZZdGJfaxwNuVJ) [sell](https://solscan.io/tx/5WhUumZhV9Wmhb3LL7wjp9cYoF49347WnXiybMzaNnLEi28DzgbDwjox1ZqLRnersqeWiMrYngZG8Lgjro3H3vTe) [dump](https://solscan.io/tx/129bUmKL4siCRJkYsasP5TY4DBAUFPgomPPZrPSYA3aa3rQWwkRqJ9zQ6kgeNmG341SXJ1mUrFcg17yyfLGEuP99) |
| 93 | 26 | same | 0 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/3PAbPEqkgiG5v1y2VgqHQb1F9jsrv95nAneTsWBYncCDtP4huuiCGJnyRQCKUxnXvdr8ux1eaEe4Aw96afwqkFxf) [sell](https://solscan.io/tx/5Nk2ACoiAYCP1nRRox9evpwjmfyo7KCUp6sKeJV3ToSbcWQd4VXDeUU8Kv7w16izQpDsA1DsvepeNWrdpJMmEbFC) [dump](https://solscan.io/tx/2iGM966SQYhPP8VMH9qhMCwtmZp5vEbXhH7JbBuchWBF2QSUikpuWMnnQRLi5FsJAFGHR5BuoBn8vRjAxY6u48zE) |
| 94 | 172 | +1 | 1 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/2wsX1eprqBGrqwBEkezeWgyNLbQHEZgpb2raQJpSYVVQF39WmyKr6yt6chDeG2ygRcfNtPWK7XsUGhd6EcpJ23uX) [sell](https://solscan.io/tx/4BWaEpNpBZtkyQ45rZD5JdQFwYy5jajDfxJuDDsczHAbdsAEPL8zp9F9U9t84XrK5ecT4e3pLzu7cUY7cTYjw2VS) [dump](https://solscan.io/tx/3CCdMqQHfeRcR82Pmqm1sW39cjWqNA4e3VEpJN3g27iQTWQwYzcDLgyzL7KLMiw1pG3wYiTZFQDx1CDrTh6Z3P7h) |
| 95 | 98 | same | 1 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/2g51iNzfGAp5RLERBjvrs8HebLbCnyiRtJzPCVjMPwNHfZBkVFTwNvescjiVnPZYMch92Xd5tws7sh5ViWZfWhN2) [dump](https://solscan.io/tx/2GsUieUsHD5xpUojNUXtLEUK85ZjdgyJqWr4U3PdgXBWWHFVUzKkVbFKbnhsZc514mC1QrLzkX76caSeZKd6Ws1j) |
| 96 | 167 | +1 | 0 | **helius-swqos** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/4PEE7p4vVKLo6EGgRTCPW4EzGY98LUGmsbbd9u7iULotgFr3E5TZfbikRMh6D3A4ShXv4CMpfTEKdrDczEmZUfvs) [sell](https://solscan.io/tx/2dtEN3Arsi2r6kqZAeV36pWViF1szh4BsQQMU11tXRxm9XXVtesXFPL4LUHaybS9pSHGiacaoF2YHZ5ptL112Dby) [dump](https://solscan.io/tx/3zJxBbJWGZCxNtST4T4Zsek8KTxRzEhb66G7dqp5g2swEFDykJknURq93zDbpDQKQ4ag3VWCVeDLBwA86Vg6XfSg) |
| 97 | 156 | same | 5 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/2GLWYKHS8ZnziTKDV5bWp4DEDPPt9JoRajpEaDr2qK2Nit3cXVZqk4wSMtAPfMoGHgL1hT25iHf2fqbBUU4VrFC7) [sell](https://solscan.io/tx/3nuEqDtALNpXx1SShDSLQeXwaFbKyLMpk41eVFuY3Hrpd264J5rycG5KbKoHoLRJWpt5ctFPthJFymzCv331LRih) [dump](https://solscan.io/tx/4W1Vv5sbX82itTF6JkyucqePqgCCSSoVLMmoAgSgmR1GBES4RK6HNKKbKMfE9PMsQp7ua6SUY5jbiX1rddxWjou9) |
| 98 | 92 | same | 2 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt | – | – | [buy](https://solscan.io/tx/3aFsmHhJDuWqTHRVxZmTeCeRNLaBdq62XeQEV7AgKCxd5whionXY4yFX9iTvjvtnZn3fBUqj4fcazxtgnXbnXCHW) [dump](https://solscan.io/tx/Tq1yZZ1jt3WboVJskcYbre3CH4epNnFsVT2Uk7gr5BbpfvRoQPXTBtWqvwQ2eFyiF6PEpo6vwnAeEumPjuyGQXk) |
| 99 | 174 | +1 | 3 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/3nfrM3hmzTJBGTiSBtiFcr9poaRf1EsHw3RLY6GSvHbzJG3NgtBNpoLm559qLB1RGZzmMrVzDFZ9vdkPPxBuRLwZ) [sell](https://solscan.io/tx/3E51JXpq8hfYtKmwYHKZ9rTzGfHGDWbooKPgdsJ4vUEJZkobkNPs1Ghk6nWA7npi81P7gEfLmiXY6V3ocNo1Fvyw) [dump](https://solscan.io/tx/4DZQbuJhibVoNhg3a8BW1mBvJo51VyJwSUF6GEo9ZtHJDNoThWxx4AgZZ5PbUJh7bfhAveV4MJJHMUfvxsTfgsru) |
| 100 | 168 | +1 | 2 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/51EXqNRsZ4HDiycE4RXaRqiguavw7T3vXiihQo9Fut5ReEf2q6m4sc1fTbHBJ5y2GhnbZTez7Q4ThrkXN6fhD6Zr) [dump](https://solscan.io/tx/2NgTR7KRc7ygbhtgc89iS2DZ8aHiziwmsUpbg134cT4fghrcxfbFLG1mDqQbtYRE9tX8EcZRVFGzuKrpVPPLKRiQ) |
| 101 | 73 | same | 3 | **nozomi** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/2nXz5NSKJBT6ZxaTbeoiPhsBFdeYZ9UxasZKdUVQMMTsiYc2DnfmLStd4deJ6gf6YA1rQV8XcBTHYjbFoUwEygGS) [sell](https://solscan.io/tx/2cUvmZ6wSDSfhgMGRNF4S3CPWqJYfXVWFu47TmQqXC9ErzdQErxRUCTKzkuofvPKHBTinAWe9VaXsJKpdRPKDuzG) [dump](https://solscan.io/tx/4XGaPW2tLRKr7PpwVX2vokzBZkxutdJh3jyMnYQVscWpHefYUh6K8whzpQMpoh2Nk5p9Paq8JrfMJk2EAavXzu1N) |
| 102 | 39 | same | 3 | **falcon+falcon-udp** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4YSNBe6QVe6v2rUMLcPkCUEnv1n6AT99a6Hzrrsb3LpJAB2h43NQQcttHwjFN4tSg4qGNMszGgzc5chw2nLaX9C6) [dump](https://solscan.io/tx/4syRUyRwTmtCpgXwJzkDxiy7CQVhvFxyEQupT7jkaALD1uZcDAJnTqKYyvYknv6uQaRgQH43Y2fgRTJgH9SRakjp) |
| 103 | 16 | same | 3 | **0slot** of falcon-udp+landx-fra3+nozomi+helius-swqos+bolt+falcon+0slot+glaive | – | – | [buy](https://solscan.io/tx/2Wq9WVEskhtGVnwA5cnG63pVRuNJRRzv9ryFbobEpAXTGp7fUg3WHQEToBu1bTUMo5mc9is2Pdey2WAcyzVz7Lmc) [dump](https://solscan.io/tx/HprC87D4Lx2aZjuRPziZPNkYk66H8JVXSRQ7noNhnPTBPssMyzbPwDhY8pBMANmNuykqVP4yjVh2sU2SqotcApt) |
| 104 | 36 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/4B9kooCzuNZv19r63BpkHicjo9psfZC5EfHG3148hD4Qd5hjYxJ5ChCehffMLKWFbALrw8zJi8EyG3TQoQTFL169) [sell](https://solscan.io/tx/3oTe1ekyDRWhDynfc1Wd3abScrT4KTbFLzgXu2Dz5MnqmnrEYBmcirfcFUNeXxwnJmdt24NrGCmxKxjYKF8NMgnB) [dump](https://solscan.io/tx/4wnForAKh2mNFEXUGb6DqyKLvjq4FgTTvv99EjUPU7Ssc5i7fNFHcYHgY4CG1kheX8jKhDL1qTTnCuPBuRvQ6bDt) |
| 105 | 56 | same | 1 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/53f5gtAc3657kSwrSj1XJrn6deFXUNSsoGH1iL8XWgD5cnYPV2B3vya25Zt9Dwq6mDE11A1Dwi2DQUgaJgqGmqKX) [sell](https://solscan.io/tx/4WRqoX8DrrR6b2tgJqYN439kCZTFaejdtZaDqkcer9TQc4BXoyN1JHJYoYxnEcoyC3bt9tNnXqPxBpkyFK77u2cz) [dump](https://solscan.io/tx/5ebCENhH4ee5SULiHm4hKYFuNb4Q17yLehS5vT7R6vabUoAsvZ4G9b9V7474GWkprwayEdxdpzSWKp9brKrDdqnG) |
| 106 | 62 | same | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/4eWykEfLHPsGftj9uqt1e8LetFRxtUU4XvYfycm1W5HrArGxm5hpMpwpzX76pPg8cbvzUe7uTM4Wsz9YSUGG6qJM) [sell](https://solscan.io/tx/enp2ZTCMGMEXshB1XCHA2ZYEpmGccFDkg4fmdGs2x62UKR7wTGboLUhdyuKDpN5ZbPvdmcodYPhBgxGcfiG9NdS) [dump](https://solscan.io/tx/3pUS67Y1Gem2UKzN6YFGgJpXQxeyaWN8WrsMxRncTtiNygEy7FUZa2f7jBFzj6sFFZucfcqfuf5PaPg6Y28sMbJ7) |
| 107 | 21 | same | 2 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/3t84wqG74CzyRpVk8GUXWJGf25YYtQY1WixsHtWYxySyj6H5L97ZvjDJo4UMbdQYhH1pYuH67sMe59V2dDooWwFP) [dump](https://solscan.io/tx/3UyD8RSYzxfq2gnCbDiMC4p2BcP7GT8VSJt6aFRXbW9MeivXoJvKndTvB4c9D65hb64o4uMV2EKHgu3bXXcKUog5) |
| 108 | 40 | same | 10 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/1LnaUbYsH7yhdL2QfQsiXMQeH4YMPiTXmUg3qDMabJrr51qcGem5ubovGF8M1Q6wmy3GuACsSaDqZDzwxJJwnXD) [dump](https://solscan.io/tx/2Kqyy5s5xsCrEfaoUzWBeAQQQQXh9JtD1CvrGthCSGf5HfgJ3AApWttZjpTE6F5oU6M7vampbhMyfCHFQptnD8FC) |
| 109 | 73 | same | 1 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/575q48GttRhjV2sdTpGMPXZSnjTWkhKVJDxb6GiGKrGJoHSFiJuH3V8BTo8ZKKSQi8mqKpSJEdP2Y2ttAc1jQsjB) [dump](https://solscan.io/tx/4mdmGsnqNHBHmuhmK4cox372Sq6MCE5X49XhYtwUJFaRfwoEs9rizw91v7HQptkqu2JWNYrxyWbYcfBMapac5h46) |
| 110 | 17 | same | 2 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/3YFnCtxgQMvoHWdYY8XrTXcT1VW4mEAMT8khPRmm5gJehN5Z1GsThQfr8AuxYtLK5wiQRbFwp4U6Yyej83wqWUuo) [dump](https://solscan.io/tx/ahQb9zQ6fKC6iSd29pwZ3muqKa8TaBB6mRiY6c6f7Wj7Rx8fN1BaJSSdQwenKpK48uTtamFMCnHC4cyMVELwRDr) |
| 111 | 39 | same | 3 | **0slot** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3qrT2CMK3J6G9zJv9kRJWuHWjmpxPeUwnvSEHLh1eznKbMu2DvuabtSCw9VazPqBMg9zCG6RgnJb2QFRhSR1Sa25) [dump](https://solscan.io/tx/4tzLLsXpKXkunKj1gEFR8EFcLbomX5BF26j8pp6ssJA53SyNAgnQyWWzXtai6Kpn91maKjeoid5gZo8o9FDAedow) |
| 112 | 37 | same | 9 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4zEQKdV3pN4JzUfh2w2ScBstoLGpLCJhyKwhf23UNbDRLQBkLmEjE6wGPaTuLBkQCMsumPUaG5zwQ7D5o9gL1XYu) [dump](https://solscan.io/tx/3p1i6nSt96YAKsw8DAvdk9p5bQ59pBtUv5cN2imWBSa6F4iGXWSMidWXssN9TMLzPS9xRWzf8nRt6jrXxUhog7TJ) |
| 113 | 31 | same | 4 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/5K4h5YSD95XQePbTMfXcy31rvDMBNkTDWzHx58SukdjCLvNvJ1HrasaAWPFzNjndDHnLwmTxPoEZYbTHy2FNDkbR) [dump](https://solscan.io/tx/5k1nBmxpdAhf71hFy7Emnjgw2eHdQybdHe5spJsqP6V1bk4AgU7asBxL4XC6fhwF1Jyw1ngR8V8rnVknovYbnXA6) |
| 114 | 141 | same | 12 | **falcon+falcon-udp** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3HN7532hUgqhHKQy9iQuRn9Md6vaFaHyzfswdw55MGgw5tG32rC7DdeczbyFRJJU1jwk1ZWB8LT2DxA8JrSpyy5u) [dump](https://solscan.io/tx/4X8qqgD13Bg3G7EzQkjyrziRfsAhr9WTYhVkqWeJVKpYCFXjKp1k2i5wg1HihNcdykzUahnXKhWFFN1EyqwJkcGg) |
| 115 | 56 | same | 7 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/25xqnKteihvcyFWh8mtorXDp5R2fHEPvM5G9Vg8zyoDN9MubF9ywnFPzknC6nb3RKXc6t1npEBoNn3BzyzckzSWt) [dump](https://solscan.io/tx/3vzmf7uiWct5SNySFUejwj6oWVE891LA8Vo8hboMuyZjBhyzFgMAJNSNVu8xLWyREb52uM6ZpsH7KzyCRUt2GGNU) |
| 116 | 16 | same | 1 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/4fwiVdRmxKmdpTvgdemdG5joajYVBMEkUhxQwddWaZhAp4zsz8TWQqT99kMgLM88bETsqzAS2qL43thCa3fs9PNK) [dump](https://solscan.io/tx/kk8a3JDHsoivUYQX8Y8h36kxNzn8r4cTVzCBuyEoPw8GVyejAS2V278tYJE9yHMtYUUN7NqTrfbm6LyUwqn3cv1) |
| 117 | 26 | same | 4 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4DP5oiejW3XAfzB9UKojPtGySNd7oxzt15kbwNcM6z8Pjd68Q1AfCC5H8dN1HUnsnTjVden9nLcDuTVgJfK46ahb) [dump](https://solscan.io/tx/38fLgPy5hHgJp3uipJrgy7Kz46unVKWBLFo6MBWedjsnjhyANtG9zqqJ8PiDW7EfskZC5BYgvys5NCmfGFuFQqnZ) |
| 118 | 155 | same | 9 | **0slot** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/5XGihUhc3nDYcQKHG9Pnt3KETs1uLD2bAnPgUa5WmDLBATP6AxCh4AorubeXN8xu8SjFkkDbrjGe4wgG5LWpf4XK) [dump](https://solscan.io/tx/sCAteTzUb7P9kYxXu8GYu4sKXQSeLj6i4YRSPoVF2A9gHPJ4YjgYsS5UVRhjv6yMtGaQ78Ru1Jf43RFWwnDV9ja) |
| 119 | 21 | same | 3 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/j7wz9abqU54VXfFqp4y4RNPVo7BBFKhTaxZnLeeTpm73NPLHGMBDgJXbetspiX1mxUvfNTqtLcP6xMer3d5yzeU) [dump](https://solscan.io/tx/21CQ7LpvCg4ppdivoXQKG1Ft4TekJfrn2cZLWkinLZgovYWjxzZyPgbuSp1rf3vrwi8L7uuhEe57fxVjcKDXw5xv) |
| 120 | 73 | +1 | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/CDDLkWGv6MEqKLXZVS7ACNXogX27acGaqMP8bTn1RweH9LiYHtrwbaqK9LrNtLQjR6ahj4w8ycsufsS7RjPpbFP) [sell](https://solscan.io/tx/EmHjVrGDCmuNs9QwPn1BrSv6ds9KLYs23Gr2JYawKn7UmSYKRqmmHvHZv3GQVh5JmJp2xea6LUxZGwxtFeD9fek) [dump](https://solscan.io/tx/2we9Csatmpud7MV5a2f51FHgpzK1ioYpw7kL9sn86hTzvAK88PrNe3VpGQEHYtRqtRzqeWZMq6FpLx1TELTMP42w) |
| 121 | 27 | same | 5 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/ZZKCBaBNMHcUzJ1ugNf1UPdvWh2fzxVuQkNG6jonMHHM9VEyS2hmiajhwNypSCrvjCHCDrArtb9qrHSnvqgRVYb) [sell](https://solscan.io/tx/4uzk866SxHXN2JeCePvXMug7foRU4TZNovwDMyhtv323JWWpYewnSGvB5TN2G8XLRun89jXidmB78ve3Wefvr3w7) [dump](https://solscan.io/tx/3C3cUXFe49AYhikAwPKBKCn974eB2EuNY5HHFxcZQvVY9Aq66HmtcUnUR51NLtSmkjCoENsy3XBzwgJc5BamQ2VG) |
| 122 | 110 | +1 | 3 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/3ng8U5TQd46XmGCxAsyHioYRj6XXg7ZU7jMoKVRHsf15SbZo7Da3hk9PfvRaFRdWRwuMakgYPQzoVMDrvhuudDig) [dump](https://solscan.io/tx/4eHxqS47yFqRAsqRZU9Tdxb3ta5QHcLN5t2DBxSkHE5z338cwv9ain8afWUaRymZrvegWXqfoRofyyVa141p6LkZ) |
| 123 | 89 | same | 4 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/4Yy9Z2q4NoEVDp7BRgjKCdy6HNm9a8a9NX7xmSxseEzvruuSuDUrwVkjwnNvPf4z4Cpr2eVqthtV7QHGjYtjKgBq) [dump](https://solscan.io/tx/dyTTxBdpCZGVPDzC5tVfhUQfhsjJSCY9MyUj3KreJBUYzDvqw3bYpCxaGMcTgLJ1hRQUjNoC7VPCjVhhR1xDHif) |
| 124 | 31 | same | 4 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/3epaVq1V1276zUc1jLddfRL1c9VkXYhcohtF7nkMsj3v7zLbZgCgkj5PvP8GATQi4CNgyzB4yDoStda2kDQijtgB) [dump](https://solscan.io/tx/2LE1WA1QNxzLHkAzBVmkJ3QxVaP7VGsm99sJXaFco7Eep49RnVR5LzR1JzHQ1cxSVaL1Pxu2igZtHXpF11gBAoKK) |
| 125 | 117 | same | 3 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/rtnBAa3GfYh2WWPwzTPQopYPexZPgnMdCJsPrWnLPYXiT3dH6m55wf4h6KGfzFBqn7925NsKHixeG2eQAcBgf2T) [sell](https://solscan.io/tx/5CdH36fGsTxFNgTnCnZNVSmiTRynXaxbqrVVkJQK5kyHokMyQhcaXW39Fz3Ryy94sSpVtedUjPwkwMEiSJfsfgTQ) [dump](https://solscan.io/tx/Ya9fwDzSGJnDHNQAbY9YiiZKbDfg651ucFEnVw71NzucMUp1WoK6yTKXwhALXfBeH3kWd5zuxiqKkHnzpNuiRMN) |
| 126 | 75 | +1 | 4 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/2KeBZrxqbkf7bHQsns6xiuUHJLhZjgQf2aLQ5PdUbL4KPtbxbTCLAeeDVrMoqWk4jT9VgifsV5BWFBz2p7SLDBDy) [dump](https://solscan.io/tx/uxvk7nuibABC6gcGEBbTfeBuRj2CtTFE9BPwXYiAofa4q2T59TPzfZ8acxnxeTkaaXCzE5uiT5KjGBZRa1XgPtg) |
| 127 | 74 | same | 2 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/4ZbmGhp4NAsW6awmqfBpGD8dJCaZpEuCn5yrjGwYm2mgYkKWi9RkSFTLcsTETqCMEJ9bb6kSbJnpHU5SzByC7Cyj) [dump](https://solscan.io/tx/3rmY9BUdoDisiCh2wtVzHLtqCyma3EUXSZXopstsVKZpk46GB2dh7XMdYTW1Yr6wceM1WygrdEWkb4gZz6zSE85g) |
| 128 | 41 | same | 5 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/DDBjTvbYaY8qn8vY4WJkzTJ25nBeKiLWB1EvVTC9bHHqoBmfjHbqA5jFDcJgzAh92Zo5rXQRnAgzdbKvRwgi1Dw) [dump](https://solscan.io/tx/66qGHYtmsTSY5WSra2DkKKyMVGtLEuttm73KMXYC7SKBatXpeDKaR2bkJCrvzr2sn7rTvg45Hq1a94hY771CXPmY) |
| 129 | 37 | same | 4 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/2Lgjg4LU6sGmCH71aMCv89f4MbXxNB3mWj6ujkRHch1hTnzRSmLbKSVYFUa8rvqcnHUPxep8pCAkWS7731k5gsff) [sell](https://solscan.io/tx/4NjkG9vUmjG6exF3SM1QuU24HBTaxgUMD5LKYYUtYdrdySUMWLWjcvboMtZtxwHoRiVXUrw5z4WNy7jqHuJBAMGf) [dump](https://solscan.io/tx/4E74Ug6NZr3LAJhoSt1upEHv56QCQxzXXznJ3gnyv5a4vN3A1C8cYWiMxPZUxE74GDUzKd5pVGABVaK4CvUNzMQg) |
| 130 | 38 | same | 1 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/4ws6p5gpT5gfcVX443K8hX5zbuVmH6FkvpaNyuZb1rJvg8gDwRJTVQ45rCaLvCtf5Me5aHrz8rdyfmG7XdAM9Q8K) [sell](https://solscan.io/tx/5LP3eTaaLCuHkqATMNkQ53EufRM3rgFFJ3vejyt9AR1CTsfVcc9V7VsfM2CNnZjeE9iDVUSg67mE14VkPNNqnPCG) [dump](https://solscan.io/tx/2SHdFf7pUdtLstpzSfRc6KVjoQWVTdHRZ2RZnGBfA4azmijkXso6pAggKU5wsWTvbZsZzoEShxzHSxQ7bGK9NgSS) |
| 131 | 135 | +1 | 0 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/5zVrqsZ3vemagpnk6aHLVQkytFr2KPgzc7R7gPMounRrtxth3oYyLGmMe5cW5jWue8hvBkj5W4poaenxMcjDzJcE) [sell](https://solscan.io/tx/REXkgQWPmRKPq1z84bvRNZuQV2Uh3KeFCouwv5moqHmhoKDM8CYifSpfocfVW59WJRZM6JBkAAdsGwFfXRBULP8) [dump](https://solscan.io/tx/5AKWJcMnjem55M9SaduPhSh3YqBneSbLVby75snRETLJpXGaoEqjApprKXTnLDBDUnGgpRXTX2ba3gvB87riQZSL) |
| 132 | 187 | +1 | 3 | **soyas** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/5yeSnaNxmXMyeMpwC1c95spPoUjtzjcuNonUaaEidivnz5podyP2v4QdiKAfFHese7pD3c7LxPRPGLNBX8R3Eb6p) [dump](https://solscan.io/tx/4PuHfgL71dkBhvzhZ3VEJfzvmqhZJTSxY3V1a2LpoGn5ngqoTq4hop5UXmJ7HpRibo9JVBkYQ9KymrNWpxSEVhFd) |
| 133 | 44 | same | 3 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/HcGFZNarekUe7Mih71e4uvSZqTiWBSqcpz3S18MaPb2pGR27ZAEFpSabhU1LMG4JhwBA1vK9ELAD5maMtkZ5mt7) [dump](https://solscan.io/tx/4gf3kcD1Jb8h9rEQL2MKgKzny1enV2zNkuxW2MDZYTNALT5fhDi1QuqX2QroK1uGLZKQ8ANc3Eq7PUFS3zhBuZaB) |
| 134 | 45 | +1 | 8 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/wgFjGqteU7CMWarhh7zoXr3encodTySZrxrJoeKRyeToxovpRoEbXZyn2qRg9qwTYrvL53UfiggNwvvX3cjgxvp) [sell](https://solscan.io/tx/ioyitr9zmqoPgYecT4FVyKFjB4uLwxAVmm9wFfzCmySaKNXMJbh2MukRsoRQBzTurRc4KteaJUh5SpPER82vvZY) [dump](https://solscan.io/tx/iKXXtVACV9osQCZ6xDga1EHyvRYx23hiQaNHC4N4KSi6RwmZvE4y3JtBtk8yJW8QjPAhWqr96RknhqmiTF9MVbA) |
| 135 | 43 | same | 1 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/4Xqkx2bHqqDEWnoeKrcdeTQVpKW5jKpwhX8rBw5FdkyTTiFJmUezy59TWajC5woCFDqny3dq9tcZTCrWX8RQEAaQ) [sell](https://solscan.io/tx/3u1SutDtntTxtBiPTevCG1279K2ELdK1rFgrd9VcNZShvo8u439A15ZJRrMxEbAsy5WeTHsY5MtXJAvhRzDRqnE5) [dump](https://solscan.io/tx/2hpVVmeg9LycrFCjTs4hURLH6exjSJJnyj2dHRqufa36XTxyVyk3RXTnzDLazaJnZxVp7wh5R3hS3ssRUUeQ2bQB) |
| 136 | 11 | same | 3 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.1 s | 1 | [buy](https://solscan.io/tx/48YsPKeXkmo5cKbzhRouqMu8h2k54xx7QoechREM1iRB8AVjm6XRAKLZVpsQkiZKUJWokZxr7WPFJnDx6ovnKkYu) [sell](https://solscan.io/tx/4D8e73j38p91yXHiHWi6JD12dKqjNCnEmYDgNx4BzCc6cxuMd7ZYMBAj8u5pSWF4x9r1HVirnapScojcuALFsW1d) [dump](https://solscan.io/tx/2GxejUXTjayceRMP2dbX3ASRDBomviNoN5wpL8hzEEq2VqMoE71YtV9AE8Jrj6ijUHdZLJ1K5FNWL4hZtFJSG3n9) |
| 137 | 32 | same | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/3VsjE3wpecu32cZurGNPuLKqXGSbSZsMsjnNZXw7BusC5uDffhLjEXiSQdd8n6j1FiuchgKPyyFyriMYiTpfYRmH) [sell](https://solscan.io/tx/2r1NsoqssTNfbpU6gSgwt5twmJZ88BPTTfxpyYjhDDqdbbkHWwD77SHY89Y2JrjN4yoEoQRWj8eDitAwUrTQ42TU) [dump](https://solscan.io/tx/46D87MLqEDTimbtdvQsFy3ST9e9Q994Ff2La89KGaxPRWjFoBe2bLbp5XXUybHEitGkAohspLntidBVTf4hwGoci) |
| 138 | 83 | same | 5 | **helius-swqos** of falcon-udp+landx-fra3+glaive+falcon+helius-swqos+0slot+nozomi | – | – | [buy](https://solscan.io/tx/2cRsxHv1R8avL2hMPjDRvG3PLEcNVvz5TvTfj2oivuwip3eK3zqWZ94sSk574icW6UQG2LNjGamsNSuT9rPDWMNp) [dump](https://solscan.io/tx/3YSJ7nRvPLEW4SK5rKPE6hyisABdXFj3adAutVg3bNV9RgngmZcuVW7G7ScEqkJLFKnkpPSa4XgDbwR4oaoPJtyc) |
| 139 | 54 | same | 3 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/KcCqeQQDEJmySvUEk5zDYHuv7wSYHt5YraiNxTqHCUheqqFoiWJgWLeKoMfZwCT7idyjw6PEHtfwc45thfX47Rj) [dump](https://solscan.io/tx/4eYGFHW6SQcvBJA14LNJJN6GMju8yNi64xyrCFXgs5Ke8WETrrmNRjVtmZb7XB6kNvvs8wDYy5VeQzM2tyr2UxDn) |
| 140 | 65 | same | 5 | **landx-fra3** of falcon-udp+landx-fra3+glaive+falcon+helius-swqos+0slot+nozomi | – | – | [buy](https://solscan.io/tx/NhRsFSyR5PhHZxnHttDzTCgsv1NJGVR3U2BTeiCVi3CbfBJGLZ4szJtUioQT6aCrJu2V8VGVqiTuq8GQRHGXLKn) [dump](https://solscan.io/tx/3Dc7KvmhpWtosGLo5mAR6kDiTjmoAekhL3ZEpr7fwPrZXrFL1R2kqV93bMkrSueQNYA7obo7BVnKGDVUMwHYzztS) |
| 141 | 50 | same | 8 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/fzKbs1Wosjy1yQ5nuLqBmXgmGCthN4ayMttdiPfvMcEUnoQh3WURsfBXXPGWdB1QeWLa1nAGGpJvU76Dp7GuL4U) [dump](https://solscan.io/tx/21VD59PcHv6kR3KgYfS4oVyKJui2mJUSgJvwnWSCLn8sx7GyQTBsmAMkLMEdEa4fJ4EsoX7z157nMwpmjDPteNdw) |
| 142 | 51 | same | 5 | **bolt** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/2pyGCJjbdpN9jVb1m4QiPAwbbeVjnpTTnssb3u9hmY6SD4TounNPbDiFUzY4Z25zu1JbRQVUtjXmG4Dn5Y3q384N) [dump](https://solscan.io/tx/5xUhq4yQmtHNw22RUtRUwT1YjUUwwAyPYnB8fwa5rGvirZCmZLc6u4ro78Ppd6Yj1FeyMwsQ2pv8Ho7n7rCEQd2x) |
| 143 | 19 | same | 5 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/2dcSX5mMzFt9KicJ7CqwCoxSnjftiZ6hBw912g72eQuRuq5auhWYR7zmhertpZUbFW3epZg7A7dBJs4qpiUzpGVJ) [dump](https://solscan.io/tx/akH5pbd9E7ozcEmF91VMzkn8QKKm48LZ1M7DePbeXq4PBv7Kyon6F3rpCrm94mgSa66eMk1ZocT7fM195tz7n6m) |
| 144 | 49 | +1 | 5 | **0slot** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/5D7PKrqF77CZhKM5GDj9fdJn4dxvZgNGoy3jeMnHRRfX9YVi1eBUQjkrDD8web3UFMRqitwtBDNoT9HqFVQK8Uao) [dump](https://solscan.io/tx/R8C6z2e86gmb787SXwmQb1cfaPQ4bWJJwjancXDDbvgVnhEfyW9HoPGcCRRduan8mXD7x4MSWZQxDmSXNWhubB3) |
| 145 | 46 | same | 4 | **glaive** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4eZpBntnH81c7xkiUrdF1tQenNWzYNpZ7eDbBGCWyQjKqSyhwHXEjxVo7ng6isppFq9EE1cFv6FFiNwdUniWyHuC) [dump](https://solscan.io/tx/5yMbr338hHL4Vb67ymWDWbGBt9vP4wk1U1jjKkp2YhzCpx3SN61QdHL17c436Q5TWXcLM2rfQCjBHEf9zpXhBrPS) |
| 146 | 271 | +1 | 5 | **glaive** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/5NHsb1411NaMcHtd4PSVue9owoKUycLcrbyFRzyFhDtCKxcXRnWSZ7y3QuGJw3FrioZacH2vzoySnzMaVFQL3jHX) [dump](https://solscan.io/tx/DegrHzhdWPtixewYB9xhqNnkgtwaKnuQtYGwXZX9d8QsFmgwbqj2oQHUqRLr5CrZmxweLg5eBw2zVJQsbcPDFQx) |
| 147 | 33 | same | 2 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/5Qp2mx4CmpuEeEVEpPTQba7dX6Ec74A8nrCoF9ssMmx7eqamDXP2hTDazhbhzcLpfmiFUvaspQghAdM5B3EAfJ3N) [dump](https://solscan.io/tx/4RzDJRaHdfyyMVc2kiFg2f2h5UQqnShbgBX1EupfRkJjRyzdLFWPMh5jiHAc2psCmhAfU79FQ8C9rwVGfM7NvmxB) |
| 148 | 115 | +1 | 2 | **soyas** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/TAvwcMenENRPXTcRqgehWdURT86g9nVmTLquaMDygVByrYNyarXgFexR4B8KV1FzPcV74rx1xtV6EsCJddvwGAT) [dump](https://solscan.io/tx/21XxXFvCNV6RpzBQwL329Hm3s4KJDeepvMm4hYSvN9M7rcCedw4tXPoXdNandiJS6sNbyiLbQ5Uri9RRNbpgVygi) |
| 149 | 22 | same | 4 | **helius-swqos** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/NqamFUWyVBJqRK3jJbrYJ3GGnnkLsRPPehTZCB4zeYE2NkMu111YJ3dCr894YCHwVRpk93Rwo6jvHmhxwwKShae) [dump](https://solscan.io/tx/493jYeZe2RmPJ3UHSSbNfVBBs1L6ee2KtRdgqcVLxAhbFBZmXiYZbSZyBkdTmNnbhjYQiRcfubVtrhmrDfjYkuQK) |
| 150 | 61 | +1 | 3 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/xDyMBM9W6iiwwDv4wnXWrXyaEAZMpnd8FWbZW4X7K2eSexXFjPT5VfkJuRBXbzs9kmorVVR8AecSFSdaiRAverd) [dump](https://solscan.io/tx/966XvqQS1nEf9Rifbdk3TYFdpFdZmK1mfQt6iMxWaP7Rtk1V6SqrR24C747bD67Vme1b2SY8iSpZGabbWRqoV3w) |
| 151 | 43 | same | 1 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/4Gd6ziM7ZfZnAapzuDyVsiUCoyAWzZ1GsqTZ73VYLGPfVVPnnzrQaG7i4Q4CkkChGWr7vyf46rp2pby5L4agyjh1) [sell](https://solscan.io/tx/CCSQkgURTPtc3Y3c7ZKEq2rBi6GWDdyER1G7hWen4xwRSB7FpDyKNrFXT5WzXBK43jd1mnDT6r18zvoJnSMR9Gc) [dump](https://solscan.io/tx/4rSiDc6yD4JTpQXQYRNakRZVEwbLr435U3kNLjXLbak2NiD64ckLqnnaaasKbGyNxBjkt8Di77i2wvQq4qTTzqgg) |
| 152 | 31 | same | 2 | **glaive** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/fvKxbCdpHmdUAUFbsCwSjCsuSdLnuBGkweuW9agUzusENbCeLB7weDx4ToFQawFqqJ9pcWvtcu9A7zSqf1P3C6n) [dump](https://solscan.io/tx/4HUCCgoYJBSvErn31ETnRYxNy2GM1Rwbbj3mpLooNfGy4u3d75Q3po6hnv8DBNSumbgh35oDp679PGqyfQVaptvm) |
| 153 | 59 | same | 5 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/5GkY5CaLe8bGXAkXwwYo1UmuW4PzZKF8vpNF1bcjUvYqRYqEFSVPV4t5ZvRzp5wuzCab34gg1sRJ1WyU39zwi1W7) [dump](https://solscan.io/tx/3jkHeUNhrT6shcHxkTLDuEgGR6jvibnY3AfFEv2waDjp7PeLbmxJvo5mUGxxSSvWsbV75xY5ThV1DxjYN5iDfuT5) |
| 154 | 111 | +1 | 5 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/4VDF67bB5qKzmjQ34mMzafwuBe5qe948wSVAkTg2PWVSTGHBDYSruKuot9PUXkRwEAmdHJhpsotoRuQhXqYJfybE) [dump](https://solscan.io/tx/2ujzKyYBucmRnjAe54tpfwisPXQ4iSB7t6Waxwjbsax8pSJcybqd5TwQpsrBzGXFSe1ysD3rmUEfsh2si5UMgMj2) |
| 155 | 35 | same | 4 | **glaive** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3n7ZSwES8kwKdkteiZHJPbALGvBzVRYY6TybQmRvsusC2Qjq2u76fxtxFDcspygcexNyULjQjMrW3jdQQRgcUMz9) [dump](https://solscan.io/tx/5F7BVnvsa2hWK8DmNyo2Yu7ow4Fg4NjCCEw2Qd1cCHtzDPk1C65oGp41ChJmdxMSY6TNQLD9WkPV12GpDd8yVBni) |
| 156 | 136 | +1 | 9 | **solami** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/4hw8cCAZ1sHDYhGfJD5T4dnM7ZDdRJCJNqHek17UdybJ94GaXx2fe93suqJT3QLSwUKyQ189BJtHJcuzRMuyv1Hf) [dump](https://solscan.io/tx/5zWmSJYAvkUuwcieso4Woe4jrtgsR1d7J8RVKx2u2a4e4E1sfH7zLHaV3eCSBAzQmwwLrRgBw5qQ3YATB412VEgv) |
| 157 | 43 | same | 3 | **glaive** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4ag9pnV9qxgabbj71jxox1vHb6DN6iJPQNoTuHbVSndykcwJ2cwHu1zLtggEpnLKqVJwJ9KpvVZtTaAxjTKTuSgk) [dump](https://solscan.io/tx/4CeR48j2xmWKXCni1SvJZByPUPAeamLA6c2jAHt5ejJQBTtHC6S8nyv9vuXdQjGiN4mrrNfPskp3vSzEZSYimczX) |
| 158 | 42 | same | 2 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/56zyNc38nqJNREVzEyupCY6HEwRaaCVAE6XHvDMBDXYAKCfN5TLpCD5ZP7xdsWcwAD4qJz89Cgzj7babw5yGP5EY) [dump](https://solscan.io/tx/21VWqjXXGcWwNWFpMRGgReTTorJuR2qJQUt2X3jXCiHkg6qy6SLAbqYCyAwuDoNMr1XHdnjP4s9Zk72RKh5gAm7a) |
| 159 | 87 | same | 6 | **glaive** of falcon-udp+landx-fra3+glaive+falcon+helius-swqos+0slot+nozomi | – | – | [buy](https://solscan.io/tx/4tTPtF2yrrPhpfYKBiKRin8xBexHg5c3FdEPthD24RH2KL5fPaaHS5k2kHJsNaNHM8T2KqGmf9fiLUaakaTQwr6W) [dump](https://solscan.io/tx/4LtzfH6uEvUoAMNez3GtFqXm9gFP4Zu3DeP5DxgdwiQuG4jTDaF12wNqj26J6p2BWir4WoiXwpaDWBRPGMBHdovf) |
| 160 | 43 | same | 3 | **glaive** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2mqUNeoyPDzJRYKQnP84WoEw7ovu5hPQSNRqJqVWmcuZ8awGJKHgoqna824UzeU71xwJhdXFqheBYnuCbDTSodXs) [dump](https://solscan.io/tx/6Bwm5jhh1RRDewFrVeTCzD4CYgx7x7dv8gwCwRQfPurhgvDdHcczfaYcwSoa4FSSczvrsgXPsGzgocGiWkZJeVt) |
| 161 | 43 | same | 3 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2mEJFuAaGgSnY4jkMVDU7P5PJVafkUqEshXgHDnU7wHV1uerU7wRW24TkUfavaNuHWcitR1PBhaZQ8jA6Fnqj7a6) [sell](https://solscan.io/tx/4gMuaJymYkAtZAvyoGJvFV8ewjE7d2zUkty27cnkKrY5cT4XYZssxTNW4qBpiSPnUiTrpFDAper436VRunF8EoPP) [dump](https://solscan.io/tx/NsGimoLtxLm1SDv7x2rpNsa78RS7mM4sdURfj2qmxz6ZVZeaMcxhUxebeAPRJMfYF9yUZxHtrFm1v3viNzRsi84) |
| 162 | 35 | same | 11 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2pdVcH8Fnmw1UnWfjBjYRh7AkJSunnNAEc8qguzFZoJD4WbHaA3EHP6yaz2qQkcdjdqTVAxAy6gas3bewAtSUNhM) [dump](https://solscan.io/tx/2SAmFMkLBCqyqEHDznfcGvBk1QW6VaLK8WVyZAyeoSYCHhChVGzYNZUovjboB3PT3NspYyX9oBS2xPSQmw8gRufL) |
| 163 | 54 | same | 4 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/498qAw9RGDikZFDV3YCYWPJCwfeREw5exMnWatt9kzEsgGfiT34berGBfyeNimA8ZS5ndFSLxZaLNXtNQwrFURqG) [dump](https://solscan.io/tx/2F9pj1EUeJHw2xfF9apczCKsgBNLeNsAhtn9jRhyCrCuYpL8uGTy9vs83kbzK7yqbw7rLxaQPALrdNqdbLRv3Qid) |
| 164 | 35 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/63faL1zxYt3YWwgqjsdMbBCkUe1yDYUHVw26Pk2XrU95WwSVLVWPBnXnQHRUvUQeCpqksQq9KjixEz6w4eH1EbVT) [sell](https://solscan.io/tx/vcmx2ggtzjoRU8xhJoMAFyopBVqbUeM5kmrUideFe9AGAkkF5mpFvc2RBpuYqwpQpWYWFwSzjgkCgEPLC2qRtdU) [dump](https://solscan.io/tx/HVdgamT4arxSbvQrw97wfrg7FA7GTR2M7v2FqkFGKr935zY2Ft9xXX6A84nnUokJnbcx7MGWZ3jkgky82qG4JLp) |
| 165 | 34 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/4A4BEi4q8hPh2Fm2i4k8aVBEXjEoBhzwG5jfNrKcNVNZ2ZBeWF8jMewEEptm9TCXTPJQk9oGcYJwV5Q8ab6rzBGU) [sell](https://solscan.io/tx/4JackYkuePUaWg4tFej2vMC2Mfay9QHemh69XRNTJLh8mz8Raw98QffXJXDLumG92meva326swEYbUs6kKAqMFZM) [dump](https://solscan.io/tx/4azRd15ofPDTDS6UF46Ub9hk18sVA7ZwvhnwTpq4UVQeu92iJjEdz2Ko2qFDJGwRGHo2dD8cfnqUse9cPvq5SVfD) |
| 166 | 41 | +1 | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/2frWNPp9GUU8iYA72KExRRJHyQ4vMQkAF5YttV8ZkuymFhsunaWsgVZ8aqLyRz4uqYTXFNk9QEU4zkdEVvhq8jDL) [sell](https://solscan.io/tx/5GYzmij7Pyzn7LbDHG9timbuiYDmEW9BXDSBU2gB1VWRaRFUVhnSwujnXSHWxHLyQowGrQKDEa4ktWZKzf4zGPd4) [dump](https://solscan.io/tx/3HWqwGttC5yuAVUcKrz1dLKmUG3YRbA9pL2Jt7xRZt3gCz21MCupDCsBmQ6GWmiRx2NVmT7YgQfYgpUUjwYnv2kt) |
| 167 | 41 | same | 3 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt | – | – | [buy](https://solscan.io/tx/4GCXWLtfrt8phDAaXNvRFHHKq21fUGZ2Tc7xA9eA9fRYQ8tMg7h6YTxzc3w6JRRAVHfPXtK3MwJYscUSAahjcDix) [dump](https://solscan.io/tx/4jwuY87Xq7uQAVKarqU85UBXuQUrs6bqWSQYYTRikiRrv2L4Vqc4wyAsBWHuyVtP7qtaMai6HXzYZuyDZtRPFAif) |
| 168 | 51 | +1 | 3 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/FVTwnQFMqPNKYYnHhNE1j8uRNDkb2uQ3qdgoWTfxpeq5sxDgtK4MWmzCG2DWSMwSMEEZYr6UdhePuU5CHcK7JUU) [dump](https://solscan.io/tx/55QGb5atEfRFQSz8E8raXhuQad4ki8nPxtKXL9bmGJ3bKzUVGMeTnT2RjvfcerPzqZc1DFTAJPkTdX7GQbRxoiCd) |
| 169 | 63 | +1 | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4tWAmkHToG4tnGuRseH63syH7B2whnebGEXyVseNEHoForrCwRBDwDCYakSpFgkvKwADDwth3bqX8m23tUixY94H) [dump](https://solscan.io/tx/8MurWMugf3R4Lz6t1WFHsXrNi4gyLEiFPZfHBQdxvLxweth9Gb6NNbxuVhXToATvfvsUzELGQ3kfhu9XmYRyq3s) |
| 170 | 62 | +1 | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/64gAb88prwjUre2NZxnmdp9z4adbz1dY4EPKV4NiViSpNEUnrTej6tMXKzSAPveCxYQJBMxZHxa1UnC1xFGA8kgc) [sell](https://solscan.io/tx/28DMShQTPpbrEfJKZyjmPQCxQGpNkuXm8qsHC7YUYTcKrfDRFvWe4zFzTdBNA8yxSXVrDHHKdywCab8Tmt1MYdEu) [dump](https://solscan.io/tx/38p3pBw5zCa5hzCXCdpRnb3Lg7u1oWhP5FQRgVKjVPfNKXnK9ousrwpp4GTbt7fYw7MNcqxbDWaYhCMGmWYttx3J) |
| 171 | 93 | +1 | 6 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/THgQVwQso3uSXxxe8iwrnkcPMVfa2Y69of7hNgSbuRx8jsHLewG3BLVAQrPfnYVqkQDXboetEPND9cuXSuKhw6m) [dump](https://solscan.io/tx/2qwyAnNtA68HUWFBkRLsnE1jtKogNBMD6ft5VsF82jUVqYrhMJaphbHVXhqHkDjxC6qATabbLTyWmGjxrnEy9R1C) |
| 172 | 151 | +3 | 5 | **helius-swqos** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/2QRXLW1SMVeeR6rmowvRME9VQ8Uu3BYf6dsqW1HuZepKpexqvapSQEhQshDgipnQZ4iMZCtb3RN6QSnPJZ7o4PBH) [dump](https://solscan.io/tx/5SX9kscreFyJbmqxM1qchTy8qgU2ZGMNWAA8YkR2ee3fmMh7xTUaVJRVpgXjhnSaQLNjuDYdxotzKysy4rQiYJPg) |
| 173 | 32 | same | 3 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 2.5 s | 1 | [buy](https://solscan.io/tx/4mE6sT3GptweRpjrPvAdcBkKdRtaDHksXbgcue8CK5svAumqBqBMuheTJhCmo8MvgCjW6JAmfmrcdjHGSjFEd3xW) [sell](https://solscan.io/tx/3BRUVn5LPDXfWTbL7N7oLJ8aFizqvPWRBMJ14tSh6WU3Cfb9g2Q81Nx2QgW4kpm9x5fnrQjM2oFPdycDbAXLtjm1) [dump](https://solscan.io/tx/3C7bMwHzMPUgE29R4TAoGXoGmZqAXg63GH9mseXp6cRv4Eyy2gFhNoWJ8T213keEkJEiTWREkPZV51dr9Uj5hd7R) |
| 174 | 153 | same | 2 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/2PMMoZhp3hgihBh3s5tp8bzZXMMUAUJEmpCNJAvsserJvdAx2phL8GJWa5zJDP7S8ETAv88PCxiZsM4X5kvmgSfo) [dump](https://solscan.io/tx/4i2HBQeFyzVZt2WTcYHh7q5UxtfzZFSnGoaQuCo5HvjmouT3GaLTkrCgBebSQxEUTUrwUUNrvGwNhFesgB9CBktg) |
| 175 | 60 | same | 3 | **falcon+falcon-udp** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/arFm1sQxpnfU42CZLJNv2eDC1pSNzigVgzxGuVMFwuTSM7FQ98uPwAG5cz3AfeSozfoYysEiSddevDk7i3moUSV) [dump](https://solscan.io/tx/4Fi2QigvAHsuiTgKTmojgMvrFxKW887oL7tuPUJJncx8qbPKz7AQsWTgeNeJt8XouzJe6Jt94oAa6jhRYc24YdmN) |
| 176 | 43 | same | 3 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/gNkqtcdykAcrhaogYvSmeZiHNRX5eUDap3DAq8TPNU2kBFUejC8Q56ALYv8anqBhaRrFBNDxSYecv6kSXwAyf3f) [dump](https://solscan.io/tx/XJpG5s32242DsppMMQW4HWR2aUwSGLEAJQpjrjn654fpu23ftPgsH39qXUiLZmnkKyZi51ndZ8LyGaVKfk7Ctwn) |
| 177 | 53 | same | 5 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/2pTUb74fUeYCLYCgUsR3tQSW4HAxkTr8hcGTdZdaCwUpHgLKdfKps3nhmyvAG8Qkh2RKssVjTAokXWS83fjtXYJo) [dump](https://solscan.io/tx/5YhFtpDk9mM71UuZ8FKTbZo1kCWDGxek6Rbd3TxPyhxMSX7NuHaFEqE2GKjzXrsQXy34Nhzbx6KoeAEj7Jcdqu4q) |
| 178 | 27 | same | 5 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/65pxt7yhj6ZCggKXScFcwj7r9JRDk29yCqRCsYRTRsKNkFAeRvxktZhKkz4Qeu49hykGLCFMiZz7WHejRZsGbWLX) [dump](https://solscan.io/tx/4PWq5bWn3eqZA48mALowRaYXEBu62eBs9KWHdUSUfxoLpGnbQZXnHgnWEZfQW587dgGt4Z29RHVkfhgRUHBdgskh) |
| 179 | 36 | same | 4 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/siB3yuKQJkDp7J7DSQrmGvnmwekr687Mon1Vvp4uCwGJ96rpJ49krm6yUi9NFcqxVLCk8uQF8KNqUzz1mmnANZN) [dump](https://solscan.io/tx/2rUpaHY2Xe5hwwGT6QcWgw7S2Crq3wXsUBjtr3y4ePTbBZrdFYgLNSF52rHsv5xSVTZCa5d2RxQYS3wyTDhF8Fzp) |
| 180 | 62 | same | 1 | **helius-swqos** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt | – | – | [buy](https://solscan.io/tx/3HpRYDWXyLR75vCzJRoZ2CSwMBWPUUe5ZwUacsohMJ82RYFwy5rAw6PKG9XJqxgGbTZy6DiGpFJBZKtHZ6hfr6ze) [dump](https://solscan.io/tx/5zehwdnHqNdm2KPHTf5RKicd8sGib9MTaBQhNHbyKZMQztZfH8VMYeF8meyJgNNERTRqze5tBS5VeeWtDbQajgvD) |
| 181 | 85 | +1 | 11 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/5E6ToevEjs5nyQEc9iFttGVvHGbSqQHFf2hGkWwDxU7v9BD96ByeX4ixhzajVCPFzQvrvRNeTYX5MqkZStDDQz9S) [dump](https://solscan.io/tx/3ncVhCXziVePwVNCSwNFFACB6ujhYmk8XiiEwGnNxMiCyvcPXoFV4KzB4qVqLDMBDCpWNB5oVcCW9cimpnVrHK44) |
| 182 | 101 | +1 | 5 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/61i5pguaE98VanwDv9s8eRqUTiqNdyXQoMphMWYHipyRXfyyQ5GZg4gFDBryUSEZ36vTFTeSQhL6vfkBP2ZruKPJ) [dump](https://solscan.io/tx/3Nybk67pE7tZGXesAQKVkptz3RT3uZNrvY8UGRQnjGTxWppcWWxTLZvXT3KCfjoWbUfy5mYxgzHv5bb41DXTkKG5) |
| 183 | 30 | same | 2 | **soyas** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/316Hrcv8hnvmYTLDCokHVtWVoeGYJw573HN97HsWgipt387G6ASxhqbp6mLmBPSkCLc6Juj5GXs8cRj9sTN4P9tM) [dump](https://solscan.io/tx/5tw5fZJ3r4eKkURoVK38xA2MD4Bdtwc8gLm8s3JHpE34mXm8eFGT6pbodYVWYG7dbVHE3QVTWEC5XBvvrhwNUWcy) |
| 184 | 145 | same | 1 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/meE4VsKgAYhfFQeenshJCanmXXz1ekWGMZntVdzwLx4dM4KhoecfdgEHZsweq3WyVQ63Arvjxz1JK8aZvD1mYh1) [dump](https://solscan.io/tx/29ncRAhqwmpGCHTikwaRtE152BDwJLG9GDKjYWFU5YpaHNQuwwve4MzXcsY49oi9F8DQv2TTf8WYfdzUnqVRrsg4) |
| 185 | 34 | same | 4 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/UpUW5V3biRsSQxWjBUCX3xDVtEazq8kxKbABNwPpVn7ijuEvQae8iNrqQjeiD3wFAbaUcAfyPDtEqErUhto6ZCA) [dump](https://solscan.io/tx/65acTgKNdvdbqhJFuExq5UbfiMioDAsF47eEmJU8P3kv5jW78CyQ6ezPtMXLadZsrACf8FJnV4UXpZtQgSfg7ULJ) |
| 186 | 40 | same | 3 | **0slot** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/spUdU8rMJkP8ffo5htuHKBz9fdGaHbGwsdh4dLAqMgG2V8ESxUFhaZHnmeNkSASB6gh76SVUnwBmC2TsxkkTc8Z) [dump](https://solscan.io/tx/3c5TaVTSYNRfHFpGNwnREkAGaJKZgf5LrNzGDX8NNcLvosXE5HTmeerTb2e3xV4ZAJFB7Lgdwziyup5X1kdGXnuE) |
| 187 | 51 | same | 2 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/5RJ7bwFrrFNdqGgfj39z5f5PAhxN3F2TyFrpnoZ3J2t3f3dJfTa5yQBULwv2zPgqZyDvbsdX9qsqiFffZJLkHoKf) [dump](https://solscan.io/tx/5ktt6usPnhwJNRxQnxEiBMDVabubewPKWkTCN4hzd2aXHmBMKhC96Q1raF2EWDVc1qgR7kL4rA7C6FqATMYhJ6yX) |
| 188 | 22 | same | 1 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5zzyfksyK6QSHbk9ek9CEeNWrSEyFZTXjCe1m5vZ1HRqxJd2X1C8zSzX5w6tuPkTdKcqWz9mWsi6DMDPTGFWWG1U) [sell](https://solscan.io/tx/5abty5LzcRZ3iHZmoRkQ8NC7tJaLr7SHpGrPURsG9Em7vBrKC5BBWUzDdZY48M619XrmCcCZAb49fEET4Dh1b6GQ) [dump](https://solscan.io/tx/5i4iaFkkHvNTfyaG3Eoz1x3oz9u6NZBfZtiDFcdw6kGZA5SuWAhYagKddjNN5CFA12sruwVeWmHULSV33yE83Xz4) |
| 189 | 135 | +1 | 10 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3pHTCdosXPCAEagockdF5RnUf7dWyr8c6ZnLZzmnLv9jwCPsXJiKSFBYJh4ogPAYPLt7ATatWRBoYze4vvvDoXXv) [dump](https://solscan.io/tx/3NsiVJYaNUzfR3rhjuHxBVCtj7L4jtbCom4jDogPQV43gfLuu4ww6ZqVaPAReA7LoBT6gUmnCS3E76bxpg6DH92E) |
| 190 | 35 | same | 0 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/4gDmNUnWFafkqNDwo43b7GuUPua1it8v7d5EK9xYSE9KLr23WaRWE2H6pF77tbRhaEyKxdg5CRw7rBmDv2UNDAc4) [sell](https://solscan.io/tx/41S522aP9y4zfpct7AwacxA2yLuqghDgoq6StFU4sXJbrLiupvF5FfknvuU6By6VexuV584xfAVdCu4AAiG5KUzh) [dump](https://solscan.io/tx/2GhTxs5uHgAiA2sPPoYjgLAMrZF2kX7oMBtauu2deMJVR4SA7X9Pop1yxFBFwHgM6UEUU5rHrzCgqFRvzTMFmDAF) |
| 191 | 27 | same | 3 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.2 s | 1 | [buy](https://solscan.io/tx/tSZRsDL8cxnUiCQqxb3BiGoqmwd16Rz69ULaPNT7TSMkzts2KixsTPrxBZxVQ98aBMKuTZVMj5GeRYb3xRi4G1X) [sell](https://solscan.io/tx/5QPS8FP8D5HnEs5wd5aQqeCnEJMoXHfsZe7WQVFsmyznfEyPdT8L9y1KtA67PYyHpbBUAw5bQkgvKanV2WWCV3Se) [dump](https://solscan.io/tx/2WapDUqA8Qr8qYMMKVmXzd8uujpFLVr7NZHL7HuSd1rcsHwRGXD3RqCsH5jG9d3uSaavpuK6FwQepNDJDD28a4wp) |
| 192 | 35 | same | 1 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/4My7WjMoAHUvU4r2NzERa5FDJ4KMpUJXMBXR7fX8zmzG8cvsLkKmYTQP2BmdNb5Me6Xiw7a5E4vfzfSAfDX2wEXd) [sell](https://solscan.io/tx/3MKQmexrUGhUTdUYnUFnBqeS2kGTCtkw7754S8sbQyuAHCEjfD9DUG3Y6jPH2TS6EQUxKicUznsk7q7LQ1oqeyPc) [dump](https://solscan.io/tx/3k94AwTkoHrUAqcVTBdK4CeeY4GaLtLsch35rSevLDLkC8Smsedcj48c2wxRr5oie3J8WGP3fXk8W8ZiMKJaP12r) |
| 193 | 28 | same | 1 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/53bRuccuSKS8JYQ8HLjc1cEBo532aNn2L31ndRhBRZYamHf6YMdJZf3NfjgKcMH6qcMjSbJNi813LHHBfNbGDySr) [sell](https://solscan.io/tx/3BxuRctQncKJWYsPxzQTRk54TTnFaAekzkrdgmLcZ7eEpPTesuTANmfMxhikLWh1xbQoEp7yVGYaycnzsk1g8VyR) [dump](https://solscan.io/tx/5BsshFTKqkjbU85B7jkb6N9zXh3ZYYAtRto57tLR3jNNDJLKhK6fgd396YM2L6iQZZ2ojnGcZvMKUryKtP8eex4Z) |
| 194 | 52 | same | 2 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 2.0 s | 1 | [buy](https://solscan.io/tx/bZrMYoXNDXFKkM93Vr7MgkMwN65W6M3UAxDveD2TxnKALu8JinvQcNTEQiELU8pJR5VaAHvTV6co4PVATqX9jTV) [sell](https://solscan.io/tx/2iJrV91A1PYTRUCPUKL5Xi1c12kwGnk5A8LNCkwm1fwzcbp8Ek3DHZXKXkfxDhJuDc5vLCTVTbP9hRf7XAfRcJ46) [dump](https://solscan.io/tx/BSTTVf7oDGpbtCFCPP1Lzvz8WsA2pVsnkp2atsVtap1K1mp6ogPQQnbV7sNJZe7dx2FacGG6MY648sakq8U4aZX) |
| 195 | 27 | same | 3 | **falcon+falcon-udp** of falcon-udp+landx-fra3+nozomi+helius-swqos+bolt+falcon+0slot+glaive | – | – | [buy](https://solscan.io/tx/4oVGzgQuWZFS8FvpEzvS4EzsNY6ZNxBeWxvR9n41ygDnGPrJkPS7GgrSv9aEbmgvALC4gtqKbDYVgUE2oEwTPVmA) [dump](https://solscan.io/tx/estDWt8rhmsuvt6BY312tb5Df4MiJgVTgCz9hPKAy4vvTZfr6B1wNgfgTFVZ3nEktoY33rGnVemgHG59M5FMJhN) |
| 196 | 24 | same | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/4Q4vJKNeZpnwsXG3qHoQBePYV33hsvCnBSCHgoJkmAah2FdSzrJ2sm5VSd8XeTgXTShbRh644SZ9rUnQ4FdWTgrH) [sell](https://solscan.io/tx/3hHH5sTC9ZHuaHoEWHbVrxBK3UApbtqe61gpTAFcYC5vxcgNVoBVHWqjzcsGwRLso4W4Niu6tVYU9r8y2LDz4bVT) [dump](https://solscan.io/tx/3vBBaazYuJbEt8pDcFKsJJpuDnkVcc2fMBbYXqs7M2UPhpfLmt3tJbKA3j9VDq7KPGjFkT4iXd9iTxnGcWuZf7zW) |
| 197 | 65 | same | 1 | **nozomi** of falcon-udp+landx-fra3+glaive+falcon+helius-swqos+0slot+nozomi | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2Q2468nd3Gz2uUQh8LeRAZppcXBAKqjSFEXH84BEmct4XnCPduabau3Qa1czusCpm2aJDpZL55zpioPz2pbmCz5j) [sell](https://solscan.io/tx/3Kk5VFxAiRgPXwjYGdmFkso9herEb5uYCmmp44CANWhkuT6LgX8nNrTZMkvguMX1D22ARqpLP9hrcqerCJcCntx7) [dump](https://solscan.io/tx/5QDfmypMaUw3Cun6cnQjcwGPEpMwHrJnFDZv414xRbom2cWK33Fni9TteppbgBtmEyV6HVEGwxaZtAFJiREGuPKi) |
| 198 | 77 | same | 6 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/DKWeqCzwrigqfqjor3mLWRrBkGdMx72LF5eD2aV8Azn32efustSccSabKXGz86wAacLvJZjA2bz5ud2xhTEMjG6) [dump](https://solscan.io/tx/2r9bj89mMt7uR1eHFK5tiKM2HyGx41TeTvBUu5wDUbbRpUxKhaucodSRBXr2V7hRQ1yU4gdDr6mnhD8YPLiwspNa) |
| 199 | 59 | same | 0 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/TwuKJtr3WKuwtv65jFR5N36XpLR41gvhUoQYKeDLHpLyDgtMcFy2Hdk3xHj6h5EKpftJzV65EBDmoF3vvKK8KKu) [sell](https://solscan.io/tx/2WX986aYPkpWPeapEXiEj2nAkSsuTLW9Nisn27KBJjyFWo6XjwpkXp5tq1wUrb64Cxq1UmevGLYR5d4zWYeB93aB) [dump](https://solscan.io/tx/3a4DM9ie5HhY8DY54aE3hXYyCzw68nqtyEShE8uQPJ4Pk6jKtRYA6KGEBC7YmrCBzn6W1aWjJmomRig6FgNZoe4Q) |
| 200 | 52 | same | 1 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5CmCNACeMU3rtAMVsHMYaiZnQz48BqGkhvaPvT623ReEVbrX87EFr5ikhoNNx3LKaHZsuF22UYHqFyYeGuBkn3Ur) [sell](https://solscan.io/tx/43ZpAnHFLit6hxw8WhJWZbg1Frw6cnYkN1gkDvh8kgtWNZAxT8y7MZFQVPjuXmpf8MuEB6fgg5S5EjbneGFLyD7F) [dump](https://solscan.io/tx/3efL4JdeYFEdSFKzpaucuLVVVJR7gfn3aEGKfEJrLZ6RUB8MS7DgPUZcck7jXMK4xquH5c9LJCUwTHiXQFADmpF1) |
| 201 | 42 | same | 4 | **0slot** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2M8A8Etgrr3mQrgR4AGY3tbLmgKKRmtVr34V2ha8TQEGgpTDgQU7MD4msYLziB5Ht3G9oMSZVZfoqtF7g8vSYKMr) [dump](https://solscan.io/tx/5EEUf4Z2NwuXszkwo3zGyepdUiMPqVsZWSF3sim4DxP4exiiyznmakrWCadqEshrKFx8ZG4SHsoK5TdsCQ83SCNS) |
| 202 | 52 | +1 | 0 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/5WtgJac2Z1kv6TNNCuw5EsbSzTJKN9Uj4E5e2ccAina5WVgg5AyXEvAnDGczUaKiKYrxZ9P5CRER5euwT1uow1rY) [sell](https://solscan.io/tx/3u2HbwbBGanpomSmRKZvPVUfR5rm3ZU8zesT93Ua7yzNb4vcMJbiZfRXrvKnZmRSxerFQdJ9GCzH2DrGnCjmBGh6) [dump](https://solscan.io/tx/avEsCq4nrYKGnB36Nga73bhTJuhX1Ubwh626oxkXHSESEJQoDX9NNu4VzTDm2jobEBKptmj7VpA4thhrKPWmzjG) |
| 203 | 61 | same | 5 | **0slot** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4k8NmF3X3o6ArfNWXz1gfx8d1js6jW63dKo6NJhxDqWDcPePaT2y25oRzn6y5iDf9CqerrzkykFrTL5c7n3d6mFi) [dump](https://solscan.io/tx/4otNjBRkMGaiJAM9CC5NhneDz5HQBhcnfgYZbeP5JQc9x5G9i5Looc59RwW2L1B6NqdBvtnNePWmDCRKqw8g6L2F) |
| 204 | 46 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/24a86RkE6RAeKKnne8UuZXbm5VsigdBWArLgpeeyQdjZ7GR5JArN2J3Kn6AKeTMhzyRSfdUnSLY2c3J5KAHHAcZv) [sell](https://solscan.io/tx/2xDJ5cakiiYdy9xb5DJUdNSp3oRJ7yCk4iJXadpWVKLmNJi1AMJYgr411fF2H3rR9yYJ5Kya2We2egfdCAiTdcLo) [dump](https://solscan.io/tx/32noETfM5QuADYmrQV69QBsFsXCpAbkLfRRAM3sFvnH2Ps2eBJPKqev4KLR6r54CQ9MospKdS6w9qNNFuGk2Fk1S) |
| 205 | 64 | same | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/2ygyJLvBR5Gf9uanVCGCMoaXcxW284fGbSaeUyskgQeihiJsqhqo41qvUHcDs3Fh7uinQaDWok7MGNStzwbTWFxu) [sell](https://solscan.io/tx/4tsqWdXyWRDDxXd1T9YvkzJw6FMJwi9SVtTHQ8es36ketAR7wNBhtfCscWQnaEmxHUnJSNojmvRvxZBsh85hpCiV) [dump](https://solscan.io/tx/YjjXnF4fNzo2xLGmdaYRHcChvD36saZjVQsz1WVdLUxKKTLXYSvSraNqhK5u526o4Pk5hko8uSPcqRH12Qhtx1r) |
| 206 | 30 | same | 0 | **glaive** of falcon-udp+landx-fra3+nozomi+helius-swqos+bolt+falcon+0slot+glaive | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2XSaYaoqAXvCgZN9u3Fhoe9SNNGeYtZnDSjZeyidhAR6R3vW6ssrMrGqZhjxqWo5BLpzQmyNzDRqcdQMkch4KU9r) [sell](https://solscan.io/tx/38QNV5QUsMS2NQu8aFUgC7JuzBoWtx4thSh54BGXgmgSVH74HPyk231XDcVAu4FBnXgTrsc1R5tuvozMvJ54wJfi) [dump](https://solscan.io/tx/2g2zaR1cQzjZSTEjwpgkZRQeK2zpZL7arnrp6due76zRVS4TE4JZonHnaGvMYPnw7X7SJnest2kv3w8nkGWiEsPL) |
| 207 | 26 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/5VSTfwZH8ufoeL4XZ6WjoBcRniJNmBLWDne9Rff6DFVzHizZbTxmTwHCaUb3ECGEa4DfbF8GLNCWiB27Agn3JkyZ) [sell](https://solscan.io/tx/5n9vFBsYcar9JpZC81oEHKR4nvUXUovygaoV6xV5kTDZwUZjwSZE3u9YMuKqT3v2jnbHFVw6EtDw6PW8HRJuZnpv) [dump](https://solscan.io/tx/4UVWuvsg3CweoDwuRqoS1bLCs4Yu5FcLmeQeAehHFvnyYKe1rhKhv9HZAtzry3Gi9hpQbGXt5ZhrebuMayiRs74Q) |
| 208 | 39 | same | 3 | **0slot** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/fLzRG6WjkMcqDzKJNdJbQA3TQsoggbnJLc9tAJLkBRaLZAk8oYXv9ooEWwXofdSKEe14uVmLeNA9oVKevR7BYkz) [sell](https://solscan.io/tx/3TTCMtfTCGQH3AkYa3BeiKgz3Jfg7GcvoxYiJgXchVr6MZ8nPewDQK4yeknUTJMjSH8SjtuCpYsqtMAT4Gx6faCE) [dump](https://solscan.io/tx/qurM57i4B4EnXLFoNCfipDdV9NTsAgAJ4UNxnkMMXnTQ2MJmUHse2qShUsNHjegrvmPd4JYbXg3GNEatdCPr7bK) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Harmonic | 95 | 38 | 40% | -0.1825 | -0.0040 | 14/38 |
| Jito | 70 | 17 | 24% | -0.4442 | -0.0246 | 5/17 |
| BAM | 38 | 18 | 47% | +0.0804 | +0.0050 | 8/18 |
| Firedancer | 3 | 0 | 0% | -0.0015 | – | 0/0 |
| Agave | 2 | 0 | 0% | -0.0010 | – | 0/0 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 180 | 70 | 39% | -0.4892 | -0.0062 | 27/70 |
| dev list | 28 | 3 | 11% | -0.0597 | -0.0157 | 0/3 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 148 | 54 | 36% | -0.4639 | -0.0077 | 19/54 |
| next block | 54 | 19 | 35% | -0.0819 | -0.0034 | 8/19 |
| 2+ blocks | 6 | 0 | 0% | -0.0030 | – | 0/0 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 21:00 | 6 | 2 | 33% | -0.0453 | -0.0217 | 0/2 |
| 22:00 | 42 | 16 | 38% | +0.1052 | +0.0074 | 8/16 |
| 23:00 | 30 | 9 | 30% | -0.0476 | -0.0041 | 2/9 |
| 00:00 | 29 | 13 | 45% | -0.1851 | -0.0136 | 5/13 |
| 01:00 | 27 | 7 | 26% | +0.0948 | +0.0150 | 4/7 |
| 02:00 | 26 | 4 | 15% | +0.0330 | +0.0110 | 2/4 |
| 03:00 | 22 | 6 | 27% | -0.0007 | +0.0012 | 3/6 |
| 04:00 | 19 | 10 | 53% | -0.2017 | -0.0197 | 2/10 |
| 05:00 | 7 | 6 | 86% | -0.3015 | -0.0502 | 1/6 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 73 | -0.4807 | -0.0066 | 1.4 s |

## 8. P&L leaders
**Best trades:** 3aC5KH +0.1268 (BAM, time-limit, score -0.93); Fu9ZUB +0.0912 (Harmonic, time-limit, score -1.42); 64eNnj +0.0836 (Harmonic, time-limit, score -0.22)

**Worst trades:** EVQCNP -0.2052 (Jito, time-limit, score -0.19); mj1swJ -0.1636 (Harmonic, time-limit, score 0.69); 2Ew1GA -0.0782 (Jito, time-limit, score -0.38)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `Fd7btgyS` | HarmonicAgave | 22 | 9 | +0.1747 |
| `RBFiUqjY` | AgaveBam | 1 | 1 | +0.1268 |
| `23SUe5fz` | AgaveBam | 2 | 2 | +0.1068 |
| `FNKgX9dY` | HarmonicAgave | 5 | 1 | +0.0630 |
| `CMPSSdrT` | AgaveBam | 2 | 2 | +0.0568 |
| `CQdLgwkm` | HarmonicFiredancer | 3 | 2 | +0.0392 |
| `TopjgY7N` | HarmonicFiredancer | 1 | 1 | +0.0358 |
| `3KiDz3wu` | AgaveBam | 1 | 1 | +0.0183 |
| `EXckihF3` | HarmonicFiredancer | 3 | 2 | +0.0170 |
| `FWD1aVC1` | JitoLabs | 1 | 1 | +0.0132 |
| `EUcJwf7j` | JitoLabs | 5 | 3 | +0.0126 |
| `7y5VhV4f` | AgaveBam | 2 | 1 | +0.0112 |
| … |  |  |  |  |
| `mint13XH` | HarmonicAgave | 1 | 1 | -0.0267 |
| `4k6wgP5W` | HarmonicAgave | 2 | 1 | -0.0345 |
| `97jbhVBY` | HarmonicFiredancer | 1 | 1 | -0.0448 |
| `9W3QTgBh` | HarmonicAgave | 2 | 2 | -0.0508 |
| `DcTPJqPN` | HarmonicAgave | 3 | 2 | -0.0555 |
| `9jxgosAf` | FireBAM | 2 | 2 | -0.0628 |
| `9ueKvL3W` | AgaveBam | 1 | 1 | -0.0745 |
| `E1r4Psq8` | JitoLabs | 11 | 4 | -0.0781 |
| `C8Bey3LK` | JitoLabs | 14 | 2 | -0.0807 |
| `JUPiTERr` | HarmonicFiredancer | 12 | 5 | -0.0936 |
| `shftkxns` | HarmonicAgave | 9 | 1 | -0.1676 |
| `HEL1USMZ` | JitoLabs | 14 | 2 | -0.2553 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1872 (p25 1468, p75 2749, n 208) |
| Executed-feed lag behind first sighting, ms | 2.5 (p25 1.1, p75 5.0, n 207) |
| Buy sent → our tx seen on the feed, ms | 44.1 (p25 28.5, p75 90.2, n 207) |
| Fills: our buy seen on the feed after the dump, ms | 43 (p25 33, p75 64, n 73) |
| Guard fails: our failed buy seen after the dump, ms | 54 (p25 35, p75 94, n 129) |
| Fills in the dump's own block | 54 of 73 |
| Guard fails in the dump's own block | 94 of 129 |

**Which copy landed (nonce fan-out):** nozomi 69, falcon+falcon-udp 46, glaive 29, 0slot 17, soyas 16, solami 10, landx-fra3 10, helius-swqos 7, staked-rpc 2, bolt 2

**Send-path answers (FAST-ACK lines):** 0slot 206 (median ack 0.5 ms), falcon 204 (median ack 0.4 ms), glaive 171 (median ack 0.4 ms, 1×429), nozomi 152 (median ack 0.5 ms, 1×429), helius-swqos 111 (median ack 0.5 ms), bolt 46 (median ack 0.5 ms), staked-rpc 7 (median ack 5.5 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 2.68 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 8yYMhuYo | 74 | 54 |
| 8PgC4ngp | 23 | 14 |
| haqq (dip bot) | 20 | 16 |
| 9pQQc1xy (bait follower) | 15 | 14 |
| 5PuQCemC | 14 | 11 |
| BUkpShoE* | 14 | 11 |
| EgxfYgEb | 13 | 9 |
| 5k2Ckkiu | 9 | 7 |
| 7PedQZmc (untipped fast) | 9 | 7 |
| 2KtcBC (pre-placed) | 8 | 7 |
| EMKY7r6U* | 8 | 5 |
| 5UipEgoi | 8 | 7 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.4846 |
| Pump fee on buys | 0.3605 (0.0049 per fill) |
| Pump fee on sells (residual) | 0.3666 (0.0050 per fill) |
| Buy tx fees (base + priority) | 0.0369 (0.00051 per fill) |
| Buy tips | 0.0696 (0.0010 per fill) |
| Sell tx fees | 0.0442 (0.00061 per fill) |
| Sell tips | 0.0876 (0.0012 per fill) |
| Failed buys (tx fees) | 0.0682 (135 buys) |
| **Result** | **-0.5489** |

Buy compute used (fills): median 75,407 CU, max 85,908 CU (limit 100k).

## 12. Health checks and red flags
- 🔴 kill switch: DIP KILL-SWITCH: run PnL -0.548859 SOL (balance 2.965788 + open 0.000000) below -0.500000: no new buys
- ⚠️ 66 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getSlot: 2 timeouts/transport errors (worst p99 260 ms)
- ⚠️ RPC bh-primary getLatestBlockhash: 8 timeouts/transport errors (worst p99 474 ms)
- ℹ️ send path nozomi: 1 × HTTP 429 (rate limited) on buys
- ℹ️ send path glaive: 1 × HTTP 429 (rate limited) on buys
- ⚠️ F8dJMm: landed 4 blocks after the dump
- ⚠️ 8XSpnV: landed 4 blocks after the dump
- ⚠️ big loss CGyKUs -0.0509 (time-limit, Jito)
- ⚠️ 6hsAjP: landed 3 blocks after the dump
- ⚠️ 5fZYU8: landed 2 blocks after the dump
- ⚠️ G6tbw1: landed 2 blocks after the dump
- ⚠️ big loss EVQCNP -0.2052 (time-limit, Jito)
- ⚠️ big loss 8JG22M -0.0584 (time-limit, Harmonic)
- ⚠️ FEvLVD: landed 3 blocks after the dump
- ⚠️ big loss BwBbrk -0.0745 (time-limit, BAM)
- ⚠️ big loss 2Ew1GA -0.0782 (time-limit, Jito)
- ⚠️ big loss H3bwFk -0.0521 (time-limit, Harmonic)
- ⚠️ big loss 5ebU1Q -0.0778 (time-limit, BAM)
- ⚠️ big loss mj1swJ -0.1636 (time-limit, Harmonic)
- ℹ️ 6 buys failed with 6001 at instruction 6 (each landed 2–4 blocks after the dump): the Lighthouse slot-deadline guard (inferred) — fee only.
- ℹ️ Nonces healthy (8 ready, 0 dead, 208 used, 0 fallbacks); every fill sold; no tokens left in the wallet (checked on chain 10-27 14:50 PKT; SOL 2.965788 = the end balance).

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
- none recorded

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r25.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r25.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 2 (restarts appended to the same log, each with its own START BALANCE; every section sums them); refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

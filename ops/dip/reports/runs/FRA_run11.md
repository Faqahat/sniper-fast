# Frankfurt run 11 — dip bot run report

*Durable-nonce fan-out (dip10) + Constant-K standby RPC; run 10's A/B settings*

> **Verdict:** Short (26 min, −0.0719 SOL on 2 fills: 8Ub8f4RU +0.064, 8SytCSCS −0.134 on the −20% stop). The nonce worked: one copy landed per buy, fills paid one tip, failed buys paid none.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.0719 SOL** (wallet 2.7040 → 2.6321, Δ -0.0719) |
| Started (PKT) | 2026-10-25 00:30:02 |
| Ended (PKT) | 2026-10-25 00:55:32 — stopped by the owner at 00:55 to restart (Amsterdam 15M fee test; Frankfurt later as run 13 at 0.35 / 1.3 s) |
| Ran for | 0 h 25 min of 480 min planned |
| First / last buy (PKT) | 00:38:00 / 00:49:01 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 5 → **2 filled**, 3 failed on the +5% guard |
| Fill rate | 40% |
| Wins / losses (fills) | 1 / 1 (win rate 50%) |
| Per filled buy | avg -0.0352, median -0.0352 SOL |
| Fills only / failed buys only | -0.0704 / -0.0015 SOL |
| Best / worst trade | 8Ub8f4 +0.0639 / 8SytCS -0.1343 |
| Fill landing | median 45 ms after the dump (seen on our feed); 2 of 2 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip10 (sha256 b8210182…) |
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
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 480 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 10**:

| Setting | FRA run 10 | FRA run 11 |
|---|---|---|
| engine build | dip9 | dip10 (sha256 b8210182…) |
| durable-nonce fan-out | off (one tx to every path, every path's tip in it) | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | RMR_RPC_URL | CK_STANDBY_URL |

- Engine dip9 → dip10 with --nonce /root/prod/nonce_fra.txt (8 accounts): every buy = one copy per send path, each paying only its own path's tip.
- Backup RPC: Helius (RMR_RPC_URL) → Constant-K's Amsterdam endpoint (--fallback ck). Helius had hit its plan cap (HTTP 429 'max usage reached'); the engine refuses to start without a working standby.

## 4. Timeline (PKT)
- **00:21** two starts refused (00:21:13 and 00:22:02, typed with 0.35 / 0.45 SOL): 'RMR_RPC_URL getGenesisHash timed out' — Helius out of credits; nothing sent
- **00:25** run script 0426bd0a deployed: --fallback ck
- **00:29:48** started with 0.55 / 0.75 (run 10's sizes)
- **00:30:02** engine start #1 (session with 5 buys)
- **00:48:44** big win: 8Ub8f4 +0.0639 SOL (time-limit)
- **00:48:51** big loss: 8SytCS -0.1343 SOL (stop-loss)
- **00:55:32** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 1421 |
| Inside the envelope (age / drop / since-buy / size) | 617 |
| Picks (score above the threshold) | 20 |
| Skipped | far_leader 14, spacing 1 |
| Buys sent | 5 |
| Filled | 2 |
| Failed on the +5% guard | 3 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 2 of 2 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 00:38:00 | [9QKaSS](https://gmgn.ai/sol/token/9QKaSS6Kh7y51QKpcuCUETjFfZRGauxDybsLM1RtSpSz) | 0.75 dev | 0.88 | 4.04 / −20% | 8.5 s | BAM `Cu9Ls6` | guard fail | -0.0005 |
| 2 | 00:40:11 | [FHfq6g](https://gmgn.ai/sol/token/FHfq6gWPcnAb2CQSFvrgEBWv5QHmGtkhKnjqXGMKYy8E) | 0.75 dev | 0.63 | 5.04 / −25% | 2.8 s | Jito `HEL1US` | guard fail | -0.0005 |
| 3 | 00:48:44 | [8Ub8f4](https://gmgn.ai/sol/token/8Ub8f4RU6hmeHHrJUwJHU45m78PAoVFEvh6EtCYipump) | 0.55 | 0.56 | 1.53 / −7% | 4.2 s | Harmonic `DcTPJq` | filled | **+0.0639** |
| 4 | 00:48:51 | [8SytCS](https://gmgn.ai/sol/token/8SytCSCSzfLMyqEf2pnh7yXBFCCNU64iGnByxpYNZh9H) | 0.55 | 0.64 | 1.87 / −10% | 3.0 s | Jito `EUcJwf` | filled | **-0.1343** |
| 5 | 00:49:01 | [EkXjwZ](https://gmgn.ai/sol/token/EkXjwZbiJuoTWiq148kPC1LAUZJ4DhVnacN8DQ32JZwH) | 0.75 dev | 1.33 | 4.55 / −24% | 2.5 s | Harmonic `JUPiTE` | guard fail | -0.0005 |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 45 | same | 6 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/6GHVrhxyCBGLwwKqNKpE1m82haivjPv4wj5e5Tw3nRERU5cMmooZSpV3RxcqmJCH8bBWLzo8m6tU8KaaZKbZToS) [dump](https://solscan.io/tx/L3hRE8KeADwf7uQ8FiGu2pfGhsCBSekuKii82JDFH9XYbJskxmCSHC88suFWL84RAqLrDbKtXK3MDEpKhexN2zT) |
| 2 | 41 | +1 | 5 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/5SLZBDuMLRYywoGziSh1beFzm2xvPUH2pxi6ZYsns7WaNjJpS9koTaJ2PMaUmtyxyRZxwceaP7BcwxD5d3xGYR5M) [dump](https://solscan.io/tx/4FZpWdVxiq42Y45x5yKCxpenqXjWb7TkvdmEV91LLcTjxN6Ys6Fxiv5G5W3NwbCZ1pAX4VHuvC6oE38NDvZ5AsYH) |
| 3 | 37 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 4.6 s | 1 | [buy](https://solscan.io/tx/2S4tDfG6aKD2j53AGgSQ5iEG2nGVE4A6kE1KTWVsoywiLNS94pegqy9S86fYHephV3ivTvZQrzB3jxUiMciVC63B) [sell](https://solscan.io/tx/3ZxGTXYTrUxooXL9kezPfUqsDqrD2inrdNz2Pxj4GXAgC4aJeLqTDAEXm2dBKPGLno6M9doDCDByUczgUHMYRmYc) [dump](https://solscan.io/tx/3jao7z1bi1F6iTLNEP3ZjCKMDix64GFJSCgAYZfXap3GAxg7L1tPPPudTPZ3DE3Dacf3F38V9Z9v2pjEKmW1SBW6) |
| 4 | 53 | same | 1 | **helius** of jito-bundle+helius+nozomi+staked-rpc | stop-loss 3.1 s | 1 | [buy](https://solscan.io/tx/3Me6t2ZPjQXQufwzx9AC3aTuX5dFXwtHuGorqL37VkoEi2Dqddv8kjhJJn5sTpwwWWA1WUCJxGS6RTL8F3ZzK5on) [sell](https://solscan.io/tx/5uxx4ZgxxMKaoZvq4Veoy1KD49nomjJQ5Scvj2117YemUfMA8w2sQ8wkivG8aYjGLSU1mjachvoSMcAjS2ofUfCS) [dump](https://solscan.io/tx/2CHA8BWpe1SVnG1HsZee7qZU2UYbwj5edn4dzDnxNz7G4jCPdBu7horP7akqsvvTnteKKXm4Sd5H3L7JEzK16F2B) |
| 5 | 38 | same | 5 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/3Je8jGV1urAhnnSUAZeE2STM4fdyXgjghhzkKHJUujV4hg6N5vouUVqjikumJGsRTpEEnrmfA3V1p9D2rx2YTEs6) [dump](https://solscan.io/tx/5tAkr4CNu1yegMeANNGqxo7QH4L56LLzbFnv51koYWf9DZs8u4dgKvU74fyrS4hRHqSyczTggB5hdGrTPuEoVSd3) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Jito | 2 | 1 | 50% | -0.1349 | -0.1343 | 0/1 |
| Harmonic | 2 | 1 | 50% | +0.0634 | +0.0639 | 1/1 |
| BAM | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| dev list | 3 | 0 | 0% | -0.0015 | – | 0/0 |
| normal | 2 | 2 | 100% | -0.0704 | -0.0352 | 1/2 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 4 | 2 | 50% | -0.0714 | -0.0352 | 1/2 |
| next block | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 00:00 | 5 | 2 | 40% | -0.0719 | -0.0352 | 1/2 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 1 | +0.0639 | +0.0639 | 4.6 s |
| stop-loss | 1 | -0.1343 | -0.1343 | 3.1 s |

## 8. P&L leaders
**Best trades:** 8Ub8f4 +0.0639 (Harmonic, time-limit, score 0.56); 8SytCS -0.1343 (Jito, stop-loss, score 0.64)

**Worst trades:** 8SytCS -0.1343 (Jito, stop-loss, score 0.64); 8Ub8f4 +0.0639 (Harmonic, time-limit, score 0.56)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `DcTPJqPN` | HarmonicAgave | 1 | 1 | +0.0639 |
| `Cu9Ls6ds` | AgaveBam | 1 | 0 | -0.0005 |
| `HEL1USMZ` | JitoLabs | 1 | 0 | -0.0005 |
| `JUPiTERr` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `EUcJwf7j` | JitoLabs | 1 | 1 | -0.1343 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1423 (p25 1088, p75 1426, n 5) |
| Executed-feed lag behind first sighting, ms | 1.3 (p25 0.4, p75 2.2, n 5) |
| Buy sent → our tx seen on the feed, ms | 36.4 (p25 32.5, p75 39.0, n 5) |
| Fills: our buy seen on the feed after the dump, ms | 45 (p25 37, p75 53, n 2) |
| Guard fails: our failed buy seen after the dump, ms | 41 (p25 38, p75 45, n 3) |
| Fills in the dump's own block | 2 of 2 |
| Guard fails in the dump's own block | 2 of 3 |

**Which copy landed (nonce fan-out):** staked-rpc 3, nozomi 1, helius 1

**Send-path answers (FAST-ACK lines):** nozomi 5 (median ack 0.2 ms), staked-rpc 5 (median ack 6.1 ms), helius-swqos 3 (median ack 0.5 ms), helius 2 (median ack 0.5 ms), jito-bundle 2 (median ack 1.1 ms), bolt 1 (median ack 0.3 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 5 |
| Guard fails: rival SOL ahead (median) | 1.88 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| haqq (dip bot) | 2 | 2 |
| 9k78QZyw (fast bot) | 2 | 2 |
| 2KtcBC (pre-placed) | 2 | 2 |
| 6n2cCJrr | 2 | 1 |
| HLU8QbLd (41Pr family) | 1 | 1 |
| 3Kcgq69S | 1 | 1 |
| 5k2Ckkiu | 1 | 1 |
| AEgTuy8L* | 1 | 1 |
| 9bwHbhAE | 1 | 1 |
| DiqYk5RD* | 1 | 1 |
| CWGXmc3v | 1 | 1 |
| HkQ7 (dip bot) | 1 | 0 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | -0.0375 |
| Pump fee on buys | 0.0136 (0.0068 per fill) |
| Pump fee on sells (residual) | 0.0131 (0.0066 per fill) |
| Buy tx fees (base + priority) | 0.0010 (0.00051 per fill) |
| Buy tips | 0.0020 (0.0010 per fill) |
| Sell tx fees | 0.0012 (0.00060 per fill) |
| Sell tips | 0.0020 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0015 (3 buys) |
| **Result** | **-0.0719** |

Buy compute used (fills): median 72,246 CU, max 73,747 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ start refused: Error: --rpc-fallback-url-env RMR_RPC_URL: getGenesisHash timed out — cannot verify the cluster: refusing to start (×2)
- ⚠️ 1 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getSlot: 1 timeouts/transport errors (worst p99 280 ms)
- ⚠️ big loss 8SytCS -0.1343 (stop-loss, Jito)
- ⚠️ the standby RPC (Helius) ran out of credits: the two engines' standby polling (~4–5 reads/s each) used the plan up; fixed by moving the standby to Constant-K (no usage cap)

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Done after this run:**

- --fallback ck in the run script (both servers).
- Owner: Amsterdam 15M buy priority test (run 12) after the leader-type study showed Amsterdam's BAM fills losing (5 wins of 18).
- Owner: Frankfurt restarted as run 13 with 0.35 SOL (normal and dev) and the 1.3 s / SL −10% exit.

**Recommended / open:**

- Frankfurt run 13 vs Amsterdam run 12 (fee 5M vs 15M).

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r11.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r11.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 2.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

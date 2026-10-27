# Frankfurt run 6 — dip bot run report

*0.5 SOL strict + dev 0.75 — short, stopped for run 7*

> **Verdict:** Too short to judge (2 fills: 9vWX2S −0.0677, B5TfMe +0.0613 → −0.0069 SOL).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.0069 SOL** (wallet 4.1943 → 4.1874, Δ -0.0069) |
| Started (PKT) | 2026-10-24 07:53:07 |
| Ended (PKT) | 2026-10-24 08:04:11 — stopped by the owner after ~11 min to start run 7 (near leaders only) |
| Ran for | 0 h 11 min of 480 min planned |
| First / last buy (PKT) | 07:57:34 / 08:02:15 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 3 → **2 filled**, 1 failed on the +5% guard |
| Fill rate | 67% |
| Wins / losses (fills) | 1 / 1 (win rate 50%) |
| Per filled buy | avg -0.0032, median -0.0032 SOL |
| Fills only / failed buys only | -0.0064 / -0.0005 SOL |
| Best / worst trade | B5TfMe +0.0613 / 9vWX2S -0.0677 |
| Fill landing | median 180 ms after the dump (seen on our feed); 0 of 2 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip9 |
| model / tier | IMIT1 strict (score >= 0.5419) |
| size (normal) | 0.50 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.75 SOL |
| exit | take-profit off / stop-loss −10% / time limit 6 slots (~1.3 s) |
| price guard | +5% over the post-dump price (pump error 6042 if exceeded); slot deadline = dump slot + 1 |
| buy fee (priority) | 5M µL/CU × 100k CU limit = 0.0005 SOL per landed buy tx |
| sell fee | 5M µL/CU × 120k CU limit (0.0006 SOL per landed sell tx) |
| route: agave leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: bam leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: default leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: fd leaders | nozomi + landx-fra3 + staked-rpc |
| route: harmonic leaders | nozomi + helius-swqos + landx-fra3 + staked-rpc |
| route: jito leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: other leaders | nozomi + helius-swqos + bolt + staked-rpc |
| sell path | staked-rpc (retry also via nozomi) |
| near-leader gate | off (every leader) |
| pre-send | off |
| durable-nonce fan-out | off (one tx to every path, every path's tip in it) |
| backup RPC | RMR_RPC_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 480 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 5**:

| Setting | FRA run 5 | FRA run 6 |
|---|---|---|
| engine build | dip9 (dev list, templates per size) | dip9 |
| size (normal) | 0.35 SOL | 0.50 SOL |
| limits | max 10 fills, 1 open at a time, 180 min, loss cap 0.500 SOL | max 60 fills, 1 open at a time, 480 min, loss cap 0.500 SOL |

- Size 0.35 → 0.5 SOL (normal picks).

## 4. Timeline (PKT)
- **07:53:07** engine start #1 (session with 3 buys)
- **08:01:01** big loss: 9vWX2S -0.0677 SOL (time-limit)
- **08:02:15** big win: B5TfMe +0.0613 SOL (time-limit)
- **08:04:11** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 567 |
| Inside the envelope (age / drop / since-buy / size) | 331 |
| Picks (score above the threshold) | 3 |
| Skipped | 0 |
| Buys sent | 3 |
| Filled | 2 |
| Failed on the +5% guard | 1 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 2 of 2 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 07:57:34 | [8bnk3j](https://gmgn.ai/sol/token/8bnk3jLVWpd4Qoe3mJr9jQYVidNUAs894yQMNUuupump) | 0.50 | 0.64 | 5.59 / −22% | 3.0 s | BAM `peNgUg` | guard fail | -0.0005 |
| 2 | 08:01:01 | [9vWX2S](https://gmgn.ai/sol/token/9vWX2SUuHrQEuRnx3dyM4YFz6BXiGXcSmXw23E8kpump) | 0.50 | 0.67 | 2.10 / −11% | 2.3 s | BAM `GQzMeE` | filled | **-0.0677** |
| 3 | 08:02:15 | [B5TfMe](https://gmgn.ai/sol/token/B5TfMeH5bhPMuV9Qg5QyhLqHa4zVhxqoGgmd1wchpump) | 0.50 | 0.71 | 1.55 / −8% | 4.2 s | BAM `DUND26` | filled | **+0.0613** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 119 | +1 | 7 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/2t9dVadL9v6jsxLoductt9bF3uKSdcfMaWCVhHMYdCCp2SJpZqPri3kPA7NJvo7FCktUbJkjefnmPJyN9H71U2uj) [dump](https://solscan.io/tx/4XfuG3ASypYfmohWyvp2VeNoiFAPyRtqiG2Q7BgWtZXe2FxkDunGj4JbrncQA8nh8aUCyaTNpymbXijDpSABWzZx) |
| 2 | 161 | +1 | 0 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/3E94Spp9nWRvfLTYwVfqKMdfXwXRUergdto4bqoQwuvrkyVKixn66Y57LG8u62uvbcrH74kHreXLPoJUpB2M2fxn) [sell](https://solscan.io/tx/57D2bn7YbqDd4JtD6jomJniPVQpy2Zi2BDWt9UzFoS5GoF3TGe88fS9iwkKvKGSudub6F6RPGVpTXWJMbHv26wGQ) [dump](https://solscan.io/tx/5wvqpdAvjUbbRtzQoA6jvfQWQjsUPko3rhB3YqNTNB8ib4N4LsHFPJZPQDMAXrCWCXjifF7c6UkJdEy8eeuqsFw) |
| 3 | 199 | +1 | 2 | landx-fra3+nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/NJUUSRD8NAxz75txmZArJB6njMAdfUYomeJDiYSKNeou2gMjHnzfqRK987gt6CSBZj8PEtMDtJSAtw1ajceAkBZ) [sell](https://solscan.io/tx/2f9GrPUGc8DyEfwhxD2FAYJnwXrR8PL2LMkYNNdu5nyaAyhPxpii3bRVDevEkqX1WQukzvWvZ47ZvA9faoT4py6x) [dump](https://solscan.io/tx/5Gpow3HwQqtVeYL5huVRj4MvAugmsSsDgwsNrGQbv3qH4D6mDjftQvymf66ARaAeMGgProsQKcrErQ5rwq24sGwE) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| BAM | 3 | 2 | 67% | -0.0069 | -0.0032 | 1/2 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 3 | 2 | 67% | -0.0069 | -0.0032 | 1/2 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| next block | 3 | 2 | 67% | -0.0069 | -0.0032 | 1/2 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 07:00 | 1 | 0 | 0% | -0.0005 | – | 0/0 |
| 08:00 | 2 | 2 | 100% | -0.0064 | -0.0032 | 1/2 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 2 | -0.0064 | -0.0032 | 1.7 s |

## 8. P&L leaders
**Best trades:** B5TfMe +0.0613 (BAM, time-limit, score 0.71); 9vWX2S -0.0677 (BAM, time-limit, score 0.67)

**Worst trades:** 9vWX2S -0.0677 (BAM, time-limit, score 0.67); B5TfMe +0.0613 (BAM, time-limit, score 0.71)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `DUND26mE` | AgaveBam | 1 | 1 | +0.0613 |
| `peNgUgnz` | AgaveBam | 1 | 0 | -0.0005 |
| `GQzMeEMw` | AgaveBam | 1 | 1 | -0.0677 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 882 (p25 797, p75 1254, n 3) |
| Executed-feed lag behind first sighting, ms | 4.6 (p25 1.0, p75 6.6, n 3) |
| Buy sent → our tx seen on the feed, ms | 160.3 (p25 116.4, p75 192.8, n 3) |
| Fills: our buy seen on the feed after the dump, ms | 180 (p25 161, p75 199, n 2) |
| Guard fails: our failed buy seen after the dump, ms | 119 (p25 119, p75 119, n 1) |
| Fills in the dump's own block | 0 of 2 |
| Guard fails in the dump's own block | 0 of 1 |

**Send-path answers (FAST-ACK lines):** bolt 3 (median ack 0.5 ms), helius-swqos 3 (median ack 0.5 ms), nozomi 3 (median ack 0.9 ms), staked-rpc 3 (median ack 3.4 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 7 |
| Guard fails: rival SOL ahead (median) | 2.93 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 5DcEukSQ | 1 | 1 |
| 4Aktn51c* | 1 | 1 |
| EprLoV21* | 1 | 1 |
| AN83UxaK | 1 | 1 |
| 4kmJcBce | 1 | 1 |
| Epysd8fS* | 1 | 1 |
| haqq (dip bot) | 1 | 1 |
| 8GPTNX4j | 1 | 0 |
| 6b4gt1WW | 1 | 0 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.0282 |
| Pump fee on buys | 0.0123 (0.0062 per fill) |
| Pump fee on sells (residual) | 0.0127 (0.0063 per fill) |
| Buy tx fees (base + priority) | 0.0010 (0.00051 per fill) |
| Buy tips | 0.0054 (0.0027 per fill) |
| Sell tx fees | 0.0012 (0.00060 per fill) |
| Sell tips | 0.0020 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0005 (1 buys) |
| **Result** | **-0.0069** |

Buy compute used (fills): median 76,980 CU, max 78,554 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 1 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ℹ️ RPC bh-fallback getLatestBlockhash: slow minutes (worst p99 556 ms, max 565 ms)
- ℹ️ RPC bh-fallback getSlot: slow minutes (worst p99 557 ms, max 564 ms)
- ℹ️ RPC exit-fallback getAccountInfo: slow minutes (worst p99 343 ms, max 343 ms)
- ⚠️ big loss 9vWX2S -0.0677 (time-limit, BAM)

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED.

## 13. Fixes and follow-ups
**Done after this run:**

- Independent agents (headtohead, freshaudit): our bot reacts in ~3 ms; the send → block leg is 30–37 ms vs rivals ~25 ms; Jito leaders worst (91 ms, 25% fill); far leaders worth ~0; tips 0.0026 SOL per fill.
- Near-leader list built: 199 leaders < 5 ms from Frankfurt = 35.9% of slots (/root/sniper-dip/near_leaders_5ms.txt).
- Routes v7: Jito leaders = helius + nozomi + staked-rpc.

**Recommended / open:**

- Run 7: near leaders only, routes v7, 8 hours (owner 08:10: 'run 7 with all your recommendations for 8 hour').

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r6.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r6.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

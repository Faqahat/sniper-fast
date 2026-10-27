# Frankfurt run 8 — dip bot run report

*Wider tier on every token, 0.55 SOL (owner) + dev 0.75, near leaders*

> **Verdict:** Loss (−0.0962 SOL on 3 fills): Hnkrfb (wider pick) −0.0770 on the stop at −13%, CfdREo −0.0319; one wider pick won (8DN9HV +0.0153). Too few trades to judge the wider tier.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.0962 SOL** (wallet 4.4239 → 4.3278, Δ -0.0962) |
| Started (PKT) | 2026-10-24 15:44:51 |
| Ended (PKT) | 2026-10-24 16:40:43 — stopped by the owner at 16:40 to fund Amsterdam and start run 9 on both servers |
| Ran for | 0 h 55 min of 480 min planned |
| First / last buy (PKT) | 15:49:37 / 16:32:12 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 8 → **3 filled**, 5 failed on the +5% guard |
| Fill rate | 38% |
| Wins / losses (fills) | 1 / 2 (win rate 33%) |
| Per filled buy | avg -0.0312, median -0.0319 SOL |
| Fills only / failed buys only | -0.0936 / -0.0025 SOL |
| Best / worst trade | 8DN9HV +0.0153 / Hnkrfb -0.0770 |
| Fill landing | median 68 ms after the dump (seen on our feed); 2 of 3 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip9 |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.55 SOL |
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
| route: jito leaders | helius + nozomi + staked-rpc |
| route: other leaders | nozomi + helius-swqos + bolt + staked-rpc |
| sell path | staked-rpc (retry also via nozomi) |
| near-leader gate | 199 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off |
| durable-nonce fan-out | off (one tx to every path, every path's tip in it) |
| backup RPC | RMR_RPC_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 480 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 7**:

| Setting | FRA run 7 | FRA run 8 |
|---|---|---|
| model / tier | IMIT1 strict (score >= 0.5419) | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.50 SOL | 0.55 SOL |

- Tier strict → wider (score >= 0.2109) on every token (replay of run 7's hours: +0.11 SOL).
- Size 0.5 → 0.55 SOL (owner typed 0.55 on purpose) — two changes at once, compare per fill as % of size.

## 4. Timeline (PKT)
- **15:44:51** engine start #1 (session with 8 buys)
- **16:32:12** big loss: Hnkrfb -0.0770 SOL (stop-loss)
- **16:40:43** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends
- **16:41** after the run: 1.5 SOL moved from 2g to the new Amsterdam wallet (transfer script, recorded in the budget)

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 2258 |
| Inside the envelope (age / drop / since-buy / size) | 1132 |
| Picks (score above the threshold) | 16 |
| Skipped | far_leader 8 |
| Buys sent | 8 |
| Filled | 3 |
| Failed on the +5% guard | 5 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 3 of 3 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 15:49:37 | [HYuGYE](https://gmgn.ai/sol/token/HYuGYE6uuL8QFHDcT8PRXGE24YeWyd2KrNTGqGPJZMSY) | 0.55 | 0.69 | 4.20 / −21% | 19.7 s | BAM `9jxgos` | guard fail | -0.0005 |
| 2 | 15:56:42 | [GNssGW](https://gmgn.ai/sol/token/GNssGWrW9ZFvFqLN3wqKd3B71r8Ps3JjpWQVoTHQVtrY) | 0.75 dev | 0.67 | 2.29 / −13% | 7.4 s | BAM `9ppJrp` | guard fail | -0.0005 |
| 3 | 15:58:24 | [CfdREo](https://gmgn.ai/sol/token/CfdREogGRVdkPwkcEj6UatDYyPa2JUoQbRkR4iZwTA9X) | 0.75 dev | 1.19 | 3.63 / −19% | 4.7 s | Jito `C8Bey3` | filled | **-0.0319** |
| 4 | 16:16:02 | [2mbQas](https://gmgn.ai/sol/token/2mbQasMHHWmWUd2wWeWmpWu2SNinSbkjL6VkDvZbpump) | 0.55 | 0.51 | 3.39 / −13% | 32.2 s | Jito `HEL1US` | guard fail | -0.0005 |
| 5 | 16:27:01 | [8DN9HV](https://gmgn.ai/sol/token/8DN9HVusgyq3rU7XLYVkLVxEXo54NHmDQCUDr3vspump) | 0.55 | 0.42 | 1.51 / −8% | 1.7 s | BAM `11AMA4` | filled | **+0.0153** |
| 6 | 16:29:19 | [vK7Jph](https://gmgn.ai/sol/token/vK7JphwHy2APYNJPRukY6oGr1zAaznfRC5CBuJGkCXP) | 0.55 | 0.90 | 7.04 / −34% | 3.2 s | Harmonic `3ytgyJ` | guard fail | -0.0005 |
| 7 | 16:32:10 | [Hnkrfb](https://gmgn.ai/sol/token/HnkrfbusXr5N5enak9jkQbmya9hHVZ2e3GZYPagPpump) | 0.55 | 0.48 | 3.02 / −14% | 135.7 s | BAM `CfgRXm` | guard fail | -0.0005 |
| 8 | 16:32:12 | [Hnkrfb](https://gmgn.ai/sol/token/HnkrfbusXr5N5enak9jkQbmya9hHVZ2e3GZYPagPpump) | 0.55 | 0.25 | 2.51 / −11% | 137.6 s | Harmonic `Awes4T` | filled | **-0.0770** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 32 | same | 3 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/5fmP1atRaqyvoDLxYHniokpsRgkYsCQcGAnfqDY6B7jzWVRVQB1YLWLJthzukGgL7MY7ScSYDYtD14WTb8mXV6yc) [dump](https://solscan.io/tx/3x24J6rzyqxthD5hRtQMbdGwLhkG34oW2nDP6DYBaHpWvLFCfXX72nvyedYG5RXF5ikreywrpdaCyGn2TscssVyQ) |
| 2 | 36 | same | 5 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/2rJTDg62KGuRqpo2xDXTkAf8XBEpaDF8KFKAVMf4uFzuJxX6E5CdipH76Bpj8HQ3nARkEwp8DSRQrnwijSCSpQbH) [dump](https://solscan.io/tx/3NfALUKpFUXMeXCggZJoxdTZ5aVrcmPEEUKRq4eA4N6BfSRPYQ9tnZtcKCWVYah1THLFa71qthsm9r3JNffrfrQn) |
| 3 | 27 | same | 2 | landx-fra3+helius+nozomi+staked-rpc+helius-swqos | time-limit 2.0 s | 1 | [buy](https://solscan.io/tx/36Sc7TtsG7QijLyWwfUT8hY1jtYZhzc7Rc9Gxua74xauADw76J2fMWqYhnFLRQHsqNjRgtEv4UKkYsfd94svNeAm) [sell](https://solscan.io/tx/47L1arHofTdfUEgA9koAWuQ6tbuJt7M1xVvKE9vUhN5uNPHBrneVDvhgDbY1aHfkbAFn5AEH3yNfsNMiM3BN9FkA) [dump](https://solscan.io/tx/44DS41GD27bceCHHZudpv869YkyrTrxiD4W5RjirWguZ9gP5p2ueDEMAqFN38Rqu5gB8DBW2fMQsbsn3GEVGC5t2) |
| 4 | 100 | +1 | 5 | helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3mFAvRCnWdDSA5pYWh2WiBJDz2T1dNwkcqidsFkrXNnqx451oNPZ72esmVEn8LRWzc3bVsHLtQXZPPLSPKKgajNB) [dump](https://solscan.io/tx/TYLQgCyfw2LjC7bZnEPo1MqjHDpdGUMJCjjjYptuNq9QhaXkU3BkY3rqj8twmAx3D164mvQiqh29EvFUW9aQ7DN) |
| 5 | 191 | +1 | 1 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/3eSoDyXxVam4zpBB31QdC7UqGV7XgbdrRXrFuK4cfQoL3oM4oapWcJLW21sTJ4qYN66gMRSLQpuSFKxv9ACadP3) [sell](https://solscan.io/tx/4xYNV8hh4XBKrJokUxNtFWSCRDYa24GsHbBrkpVUSFyK6CiwXKh76Wajmp8uk8H5CaVKrdLPLJtB3c92WfB3weqd) [dump](https://solscan.io/tx/hNw7QP41j2JHg74Ch6PVsgovLoRpwVEdwGySBZFwuTMLPgLe8Z9mFHg57uqsmJmGtG2TSPvDeF8PKLrPmNDitCP) |
| 6 | 61 | same | 3 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5yX3Qy3a4KXyhLNKnLc62YG4wMAkMcVKA8Xcs1gjPo4rJaeUKFFwm1tHUd2nv6Bo2BXzJe9RbdPbHnJTZxj1s7Zd) [dump](https://solscan.io/tx/P1qSVdPuu4g5oYYgjXyNFCJCSe5ADHizes3kjYh4ZjfW4WZ63PP3UBVJ7Fv3zDJGMV3oTSynZJnXgAdsX76r3oS) |
| 7 | 25 | same | 2 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/3GiNpwXpfjcTr3GRJeyzpFTyk5J1gTEpmaHPG9q1Pt69NkuC7KZSwbQjfXnARGN4BZLtvWBnZggBPnc9xSRzyg7W) [dump](https://solscan.io/tx/4F6mFaoEX6Yrbee1yxvwxLV9Sf2n9NagZggER7hCXfTYvYiPrw31HjupQem7fLDbevF8tWcmTb3me7VzHQnh2KzJ) |
| 8 | 68 | same | 1 | landx-fra3+nozomi+helius-swqos+staked-rpc | stop-loss 1.1 s | 1 | [buy](https://solscan.io/tx/28Wa6gBzdC4eZ284xyxr9dPtzP61ScVW3WK8puYFZBkF8wuP984z2Nfg7yQxDte9y4UszTifuZqiTr7BUSHGbB3o) [sell](https://solscan.io/tx/5i7tAMQAwB9mZpUryrM4J4UgTGnkVWRF6TDsc47YHp6w7VaBPLnnhthmeiqyPL7RqWRjfu3i1dM5kQ3on4mG8Lt1) [dump](https://solscan.io/tx/kAjYYeVBZ2hkgH5CZvBFEr1DknasW57ASPMG1yYTS9bNDZSYvSpSm6pWE2F81VSB3gQvVKasYf2WXd7Yn9MDEnX) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| BAM | 4 | 1 | 25% | +0.0138 | +0.0153 | 1/1 |
| Jito | 2 | 1 | 50% | -0.0324 | -0.0319 | 0/1 |
| Harmonic | 2 | 1 | 50% | -0.0775 | -0.0770 | 0/1 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 6 | 2 | 33% | -0.0638 | -0.0309 | 1/2 |
| dev list | 2 | 1 | 50% | -0.0324 | -0.0319 | 0/1 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 6 | 2 | 33% | -0.1109 | -0.0545 | 0/2 |
| next block | 2 | 1 | 50% | +0.0148 | +0.0153 | 1/1 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 15:00 | 3 | 1 | 33% | -0.0329 | -0.0319 | 0/1 |
| 16:00 | 5 | 2 | 40% | -0.0633 | -0.0309 | 1/2 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 2 | -0.0166 | -0.0083 | 1.8 s |
| stop-loss | 1 | -0.0770 | -0.0770 | 1.1 s |

## 8. P&L leaders
**Best trades:** 8DN9HV +0.0153 (BAM, time-limit, score 0.42); CfdREo -0.0319 (Jito, time-limit, score 1.19); Hnkrfb -0.0770 (Harmonic, stop-loss, score 0.25)

**Worst trades:** Hnkrfb -0.0770 (Harmonic, stop-loss, score 0.25); CfdREo -0.0319 (Jito, time-limit, score 1.19); 8DN9HV +0.0153 (BAM, time-limit, score 0.42)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `11AMA4mn` | FireBAM | 1 | 1 | +0.0153 |
| `HEL1USMZ` | JitoLabs | 1 | 0 | -0.0005 |
| `9jxgosAf` | FireBAM | 1 | 0 | -0.0005 |
| `9ppJrpsb` | AgaveBam | 1 | 0 | -0.0005 |
| `3ytgyJXp` | HarmonicAgave | 1 | 0 | -0.0005 |
| `CfgRXmp1` | AgaveBam | 1 | 0 | -0.0005 |
| `C8Bey3LK` | JitoLabs | 1 | 1 | -0.0319 |
| `Awes4Tr6` | HarmonicFiredancer | 1 | 1 | -0.0770 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1057 (p25 915, p75 1374, n 8) |
| Executed-feed lag behind first sighting, ms | 1.3 (p25 0.3, p75 3.1, n 8) |
| Buy sent → our tx seen on the feed, ms | 44.5 (p25 26.8, p75 61.8, n 8) |
| Fills: our buy seen on the feed after the dump, ms | 68 (p25 27, p75 191, n 3) |
| Guard fails: our failed buy seen after the dump, ms | 36 (p25 32, p75 61, n 5) |
| Fills in the dump's own block | 2 of 3 |
| Guard fails in the dump's own block | 4 of 5 |

**Send-path answers (FAST-ACK lines):** nozomi 8 (median ack 0.3 ms), staked-rpc 8 (median ack 3.1 ms), helius-swqos 7 (median ack 0.4 ms, 1 errors, 1×429), bolt 4 (median ack 0.4 ms), helius 2 (median ack 0.5 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 3 |
| Guard fails: rival SOL ahead (median) | 1.19 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| HkQ7 (dip bot) | 4 | 3 |
| 6n2cCJrr | 2 | 2 |
| E6JasdE8 (speedlanding) | 2 | 1 |
| BfvkhDip | 2 | 2 |
| haqq (dip bot) | 2 | 1 |
| 5w8xtjc6 | 1 | 1 |
| FCZ1NwdT | 1 | 1 |
| DYXD (dip bot) | 1 | 1 |
| 3MHgGwdL | 1 | 1 |
| 9u5f8WMf | 1 | 1 |
| 4NTuJFwm | 1 | 1 |
| EjywYBfN* | 1 | 0 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | -0.0347 |
| Pump fee on buys | 0.0228 (0.0076 per fill) |
| Pump fee on sells (residual) | 0.0224 (0.0075 per fill) |
| Buy tx fees (base + priority) | 0.0015 (0.00051 per fill) |
| Buy tips | 0.0074 (0.0025 per fill) |
| Sell tx fees | 0.0018 (0.00060 per fill) |
| Sell tips | 0.0030 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0025 (5 buys) |
| **Result** | **-0.0962** |

Buy compute used (fills): median 76,907 CU, max 78,394 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 2 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ℹ️ RPC exit-fallback getAccountInfo: slow minutes (worst p99 361 ms, max 361 ms)
- ℹ️ send path helius-swqos: 1 × HTTP 429 (rate limited) on buys
- ⚠️ big loss Hnkrfb -0.0770 (stop-loss, Harmonic)
- ⚠️ Hnkrfb: both buys on this token were wider-tier picks (scores 0.48, 0.25); the filled one lost −0.0770 at the −10% stop (sold −13%)

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED.

## 13. Fixes and follow-ups
**Done after this run:**

- Transfer script: Amsterdam allowed as a destination, refuses while a run is live, caps 0.5 SOL per transfer, records the move in the budget.
- Amsterdam edge server set up (2 vCPU / 2 GB, all endpoints 0.19–0.32 ms away); near lists split by distance: Frankfurt 198 leaders (35.9% of slots), Amsterdam 120 (20.5%).

**Recommended / open:**

- Run 9 on both servers.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r8.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r8.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

# Amsterdam run 9 — dip bot run report

*First Amsterdam run: 0.35 wider + dev 0.55, own near list (120 leaders)*

> **Verdict:** Small loss (−0.0566 SOL by the wallet). Every start check passed on the new server.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.0566 SOL** (wallet 1.5000 → 1.4434, Δ -0.0566) |
| Started (PKT) | 2026-10-24 16:59:25 |
| Ended (PKT) | 2026-10-24 18:16:23 — stopped by the owner at 18:16 to start the run 10 A/B |
| Ran for | 1 h 16 min of 480 min planned |
| First / last buy (PKT) | 17:22:56 / 18:09:47 |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 7 → **2 filled**, 5 failed on the +5% guard |
| Fill rate | 29% |
| Wins / losses (fills) | 1 / 1 (win rate 50%) |
| Per filled buy | avg -0.0270, median -0.0270 SOL |
| Fills only / failed buys only | -0.0541 / -0.0025 SOL |
| Best / worst trade | AMZp4f +0.0030 / 6GgVYW -0.0571 |
| Fill landing | median 28 ms after the dump (seen on our feed); 2 of 2 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip9 |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.55 SOL |
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
| near-leader gate | 120 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off |
| durable-nonce fan-out | off (one tx to every path, every path's tip in it) |
| backup RPC | RMR_RPC_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 480 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 9**:

| Setting | FRA run 9 | AMS run 9 |
|---|---|---|
| size (normal) | 0.55 SOL | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.75 SOL | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.55 SOL |
| near-leader gate | 198 leaders (buys only when the dump's leader is on the near list) | 120 leaders (buys only when the dump's leader is on the near list) |

- New server (cyber-dock, Amsterdam), new wallet EgxfYgEb… funded with 1.5 SOL from 2g, its own 0.5 SOL loss budget.
- Near list near_leaders_ams.txt: 120 leaders (20.5% of slots) that are closer to Amsterdam; none shared with Frankfurt.
- Sizes 0.35 / dev 0.55 (owner's choice for a new region; Frankfurt 0.55 / 0.75).

## 4. Timeline (PKT)
- **16:58** two starts refused: '--env-name must be DEV or PROD' (my run-script label PROD-AMS); fixed in a minute, nothing sent
- **16:59:12** started
- **16:59:25** engine start #1 (session with 7 buys)
- **17:24:39** big loss: 6GgVYW -0.0571 SOL (stop-loss)
- **18:16:23** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 3319 |
| Inside the envelope (age / drop / since-buy / size) | 1738 |
| Picks (score above the threshold) | 25 |
| Skipped | far_leader 18 |
| Buys sent | 7 |
| Filled | 2 |
| Failed on the +5% guard | 5 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 2 of 2 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 17:22:56 | [5G5Gei](https://gmgn.ai/sol/token/5G5GeiW2iuRv4NCnH5Up4zHUMMXLte6yXxG1PDusBwxK) | 0.55 dev | 0.92 | 4.35 / −22% | 3.2 s | Jito `ACvL73` | guard fail | -0.0005 |
| 2 | 17:24:39 | [6GgVYW](https://gmgn.ai/sol/token/6GgVYWL6nQECGVXpmNL3wy37tAWQpUGHBupBgKWPjnJu) | 0.55 dev | 0.75 | 3.84 / −20% | 3.0 s | BAM `AWcCdY` | filled | **-0.0571** |
| 3 | 17:25:50 | [AMZp4f](https://gmgn.ai/sol/token/AMZp4foj3NfbpX1st2xqXSQ9mjFkzxd1zzowiK97893M) | 0.55 dev | 0.30 | 4.97 / −26% | 3.0 s | Harmonic `DrifTr` | filled | **+0.0030** |
| 4 | 17:33:19 | [9A3Zaz](https://gmgn.ai/sol/token/9A3ZazrSZUKFSNenjjCANjmdLkqaDbGjrU5V9na2VmWN) | 0.55 dev | 0.96 | 4.62 / −24% | 2.1 s | Jito `GnC339` | guard fail | -0.0005 |
| 5 | 17:56:29 | [3adKQ6](https://gmgn.ai/sol/token/3adKQ6iU7aRxszE2fuDxwMWCEb5g8jevNTo9XRScpump) | 0.35 | 0.27 | 3.14 / −18% | 18.0 s | BAM `BUv44c` | guard fail | -0.0005 |
| 6 | 17:59:06 | [GMYFgs](https://gmgn.ai/sol/token/GMYFgs2MnQrXGzNPa1d2LDTBxhpgZ56ovx2mFmb3GWPf) | 0.55 dev | 0.41 | 4.60 / −24% | 8.5 s | Harmonic `2mMGsb` | guard fail | -0.0005 |
| 7 | 18:09:47 | [B8gesX](https://gmgn.ai/sol/token/B8gesXqyJ2eiVxFHfrXNptW19oMimsYTeernWCnyWoDF) | 0.55 dev | 1.04 | 3.70 / −19% | 4.0 s | BAM `BUv44c` | guard fail | -0.0005 |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 139 | +1 | 3 | helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3FBRiUgBWUgqXiTUPKrvzfe5L7zCryJ7fqE2BJiTtSxtdsQ39Q1crBcSPWQGY9MYD4jzVHwdw2ZjPr2ayfhWSACA) [dump](https://solscan.io/tx/4DNYHKrjNVAgx9TBrGow4n2wyizy3nziMTixDXSZXbwmYGo18mB7eY3tERXSNngG5szpzWjPFrzusGCYMGLb447A) |
| 2 | 24 | same | 2 | nozomi+helius-swqos+bolt+staked-rpc | stop-loss 0.8 s | 1 | [buy](https://solscan.io/tx/3ksGk7B3sPYpUYbELSeFy6yzgTFKfa2fkQoPP1eyYNHQka9xuVwezaChEqSa1rG9gNYffRQbB5TPpNhkuxbJ8yJd) [sell](https://solscan.io/tx/5HE6ddnxzj7YugWryCzr3miS4fCGt26NmtnLxNMWcXH1iUiBGeQeUDZjNuvs6Xy6uHTCfuyAuEcS6WbsWy1ojUi9) [dump](https://solscan.io/tx/xopePd8UAQYsXhXAPMXiLWGvMVkCdW3d2apDRy1Bj6HwXs6yn6wDdJYKDGMdvYBdV65o3Yu54XdVvsqoxVGDgx2) |
| 3 | 33 | same | 3 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/2bqFJhb6TFMwbvfig2tvXBRS7BYKFpTjHeHBGWA9LpPmjS7f6wp6s8AVmJWVrEbqR6UU8eurY35nBcjqkWSFrzKD) [sell](https://solscan.io/tx/JeU3iUcS6KjthRkDXZKAVrsUoLNU7L2qsqnQrP4LjcoS4CCXYMAhnYdSRYeK3jLcR3SPGbgL71io9HDg8EhajYN) [dump](https://solscan.io/tx/61SKf1W9vGyPFeDRXDxJR31C7Fqt3c6CYPwCjUoYJhbfkPdHXGkYGzmSQ4xhkSCYETSK4aCatPgzhsrjvTuT7rvD) |
| 4 | 113 | same | 5 | helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3wJy7VRwBu2M1cJ5WsYQtwBaoVYsH3p8wtDf6HQjX5u7ieG993jgn3zqVZhdgKgxkJKuhYoxx3FYhD2AbNGaiLdW) [dump](https://solscan.io/tx/KfE9kzZwj2PfWCcLbDoyHEUYrRwANj8NNcgCBR4N55MKZUNJGj9qRv1BwSny6mu7YBFwPDXGaCjN1DqXUY3FmsR) |
| 5 | 19 | same | 2 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/5ZzxWjFv3mcuMkRQi97Wh6wz1cVjifHqXBoMcQDPJWEKnSo51TAeirB55KFoCFsaFTRMfZ9od9SXJ9jkgtuMMzg8) [dump](https://solscan.io/tx/3kw2CGDd4ABPc3hYkoZ5M9RScBp4DgbPzndGZ1SoExwR5S7be9NoM6d6HvgVED1m6wdaetrnfzBvzHmvkY8VRrJf) |
| 6 | 55 | same | 3 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/2BNimvfRp9Ns1otZZF1UrqJ4u2wm4p5kJexxHmHNPQLn6hdYRzUaTCzAZEi5KWZT3rMrxJ5H6twj7b2PMdKSNZVH) [dump](https://solscan.io/tx/rQPbrcSYCUXcT6xwzUyHkdcK6vg9QApaAcYcA3AgHmNaFn3SzMap2r5MKf3gVcA4KguSCjMpNy4Yy978Hx48Bo9) |
| 7 | 24 | same | 2 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/2CaW3qn8Mq3HyDKjxLoNWaaXrhTKTPdFTmWRJ4CzEgNDq1NoJE9Q8UxQcMaVTDUBNAtSZzcqe8Bq4CQn6P7xPX67) [dump](https://solscan.io/tx/5JmrSMQwtgTYBn2coWpf3NfKEhE6Si8fir348gh6KiiGjN43USs9icbMd6gYuZhFyYNWWxAbuXZkyTD8kj1Kxeme) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| BAM | 3 | 1 | 33% | -0.0581 | -0.0571 | 0/1 |
| Jito | 2 | 0 | 0% | -0.0010 | – | 0/0 |
| Harmonic | 2 | 1 | 50% | +0.0025 | +0.0030 | 1/1 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| dev list | 6 | 2 | 33% | -0.0561 | -0.0270 | 1/2 |
| normal | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 6 | 2 | 33% | -0.0561 | -0.0270 | 1/2 |
| next block | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 17:00 | 6 | 2 | 33% | -0.0561 | -0.0270 | 1/2 |
| 18:00 | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| stop-loss | 1 | -0.0571 | -0.0571 | 0.8 s |
| time-limit | 1 | +0.0030 | +0.0030 | 1.6 s |

## 8. P&L leaders
**Best trades:** AMZp4f +0.0030 (Harmonic, time-limit, score 0.30); 6GgVYW -0.0571 (BAM, stop-loss, score 0.75)

**Worst trades:** 6GgVYW -0.0571 (BAM, stop-loss, score 0.75); AMZp4f +0.0030 (Harmonic, time-limit, score 0.30)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `DrifTrN9` | HarmonicAgave | 1 | 1 | +0.0030 |
| `ACvL73V4` | JitoLabs | 1 | 0 | -0.0005 |
| `GnC339vk` | JitoLabs | 1 | 0 | -0.0005 |
| `2mMGsb5u` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `BUv44cVt` | AgaveBam | 2 | 0 | -0.0010 |
| `AWcCdYG7` | AgaveBam | 1 | 1 | -0.0571 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1042 (p25 933, p75 1309, n 7) |
| Executed-feed lag behind first sighting, ms | 0.3 (p25 0.2, p75 0.4, n 7) |
| Buy sent → our tx seen on the feed, ms | 29.1 (p25 22.7, p75 51.8, n 7) |
| Fills: our buy seen on the feed after the dump, ms | 28 (p25 24, p75 33, n 2) |
| Guard fails: our failed buy seen after the dump, ms | 55 (p25 24, p75 113, n 5) |
| Fills in the dump's own block | 2 of 2 |
| Guard fails in the dump's own block | 4 of 5 |

**Send-path answers (FAST-ACK lines):** nozomi 7 (median ack 0.6 ms), staked-rpc 7 (median ack 4.2 ms), helius-swqos 5 (median ack 0.7 ms), bolt 3 (median ack 0.5 ms), helius 2 (median ack 0.7 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 2 |
| Guard fails: rival buys ahead (median) | 3 |
| Guard fails: rival SOL ahead (median) | 1.71 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 4DN7GT99 | 4 | 3 |
| 9k78QZyw (fast bot) | 3 | 1 |
| 2KtcBC (pre-placed) | 2 | 1 |
| CVPz447t (pre-placed) | 2 | 1 |
| HkQ7 (dip bot) | 2 | 2 |
| DzRqREhH | 1 | 1 |
| ocBBRKb1* | 1 | 1 |
| haqq (dip bot) | 1 | 1 |
| D8kKCwfL | 1 | 1 |
| D1QuMgpv | 1 | 1 |
| 64hJxoZz | 1 | 1 |
| G9G3dCBG | 1 | 1 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | -0.0157 |
| Pump fee on buys | 0.0136 (0.0068 per fill) |
| Pump fee on sells (residual) | 0.0162 (0.0081 per fill) |
| Buy tx fees (base + priority) | 0.0010 (0.00051 per fill) |
| Buy tips | 0.0044 (0.0022 per fill) |
| Sell tx fees | 0.0012 (0.00060 per fill) |
| Sell tips | 0.0020 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0025 (5 buys) |
| **Result** | **-0.0566** |

Buy compute used (fills): median 89,642 CU, max 93,391 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ start refused: Error: --env-name must be DEV or PROD: refusing to start
- ⚠️ RPC bh-fallback getLatestBlockhash: 1 timeouts/transport errors (worst p99 716 ms)
- ⚠️ RPC bh-fallback getSlot: 1 timeouts/transport errors (worst p99 790 ms)
- ℹ️ RPC exit-fallback getAccountInfo: slow minutes (worst p99 360 ms, max 360 ms)
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)
- ⚠️ big loss 6GgVYW -0.0571 (stop-loss, BAM)
- ℹ️ Jito validator ACvL73V4 (Amsterdam) — first buy there failed; later studies: 0 fills on ACvL73V4 / GnC339vk

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED.

## 13. Fixes and follow-ups
**Done after this run:**

- Run-script --env-name label fixed (PROD for both regions).

**Recommended / open:**

- Run 10: Amsterdam = 1.3 s control of the exit A/B.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r9.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r9.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 1.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

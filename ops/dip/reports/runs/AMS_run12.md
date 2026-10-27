# Amsterdam run 12 — dip bot run report

*15M µL/CU buy priority test (sells 5M); 0.35 SOL, 1.3 s / SL −10%*

> **Verdict:** +0.022 SOL on 1 fill of 7 buys. 15M did not land faster than 5M (speed study: same-slot write → seen BAM 27 vs 21 ms, small sample).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.0220 SOL** (wallet 1.2763 → 1.2983, Δ +0.0220) |
| Started (PKT) | 2026-10-25 00:56:11 |
| Ended (PKT) | 2026-10-25 01:40:50 — stopped with Ctrl+C (SIGINT) |
| Ran for | 0 h 44 min of 480 min planned |
| First / last buy (PKT) | 01:10:20 / 01:35:01 |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 7 → **1 filled**, 5 failed on the +5% guard, 1 failed (other) |
| Fill rate | 14% |
| Wins / losses (fills) | 1 / 0 (win rate 100%) |
| Per filled buy | avg +0.0310, median +0.0310 SOL |
| Fills only / failed buys only | +0.0310 / -0.0090 SOL |
| Best / worst trade | 8yFPX6 +0.0310 / 8yFPX6 +0.0310 |
| Fill landing | median 39 ms after the dump (seen on our feed); 1 of 1 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip10 |
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
| route: jito leaders | helius + nozomi + jito-bundle + staked-rpc |
| route: other leaders | nozomi + helius-swqos + bolt + staked-rpc |
| sell path | staked-rpc (retry also via nozomi) |
| near-leader gate | 120 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 480 min, loss cap 0.276 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 11**:

| Setting | AMS run 11 | AMS run 12 |
|---|---|---|
| limits | max 60 fills, 1 open at a time, 480 min, loss cap 0.296 SOL | max 60 fills, 1 open at a time, 480 min, loss cap 0.276 SOL |

- Owner OK: buy priority 5M → 15M µL/CU on Amsterdam only.

## 4. Timeline (PKT)
- **00:55:31** start refused: `Error: keystore: wrong passphrase or damaged file` (nothing sent)
- **00:56:11** engine start #1 (session with 7 buys)
- **01:40:50** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 2787 |
| Inside the envelope (age / drop / since-buy / size) | 1275 |
| Picks (score above the threshold) | 51 |
| Skipped | far_leader 41, spacing 3 |
| Buys sent | 7 |
| Filled | 1 |
| Failed on the +5% guard | 5 |
| Failed (other) | 1 |
| Never landed | 0 |
| Sold (positions closed) | 1 of 1 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 01:10:20 | [2EpmqZ](https://gmgn.ai/sol/token/2EpmqZUKeuEhnz7ECf3kmwJUsmregopLvy6vbn1xK2Xx) | 0.55 dev | 0.89 | 4.62 / −24% | 1.9 s | Harmonic `AMukCL` | guard fail | -0.0015 |
| 2 | 01:19:56 | [8yFPX6](https://gmgn.ai/sol/token/8yFPX6WahM11Z9wkhiz6bVZT9EMdnooJCHCwHxexL5nd) | 0.35 | 0.43 | 4.29 / −21% | 38.8 s | BAM `6TkKqq` | filled | **+0.0310** |
| 3 | 01:22:54 | [BuAv5r](https://gmgn.ai/sol/token/BuAv5reCks3PkAmVh1KZGpAzDnZ3bSvzSYyvabfkkoqk) | 0.55 dev | 0.82 | 5.13 / −27% | 1.9 s | Harmonic `DrifTr` | guard fail | -0.0015 |
| 4 | 01:24:08 | [2vLJvd](https://gmgn.ai/sol/token/2vLJvd75hC8RJebvcAr5gwDZ5zTEE8BSwDS2GJ6vpump) | 0.35 | 0.23 | 5.84 / −29% | 3.0 s | Harmonic `DrifTr` | guard fail | -0.0015 |
| 5 | 01:24:30 | [C45TDX](https://gmgn.ai/sol/token/C45TDXexBo2NjqwpeuThT393ExMXjpbcryscHofgfHs7) | 0.35 | 0.59 | 7.85 / −27% | 32.6 s | BAM `STKEsv` | guard fail | -0.0015 |
| 6 | 01:25:20 | [APueiv](https://gmgn.ai/sol/token/APueivL29k2L3q952xnkaxZqBZb4SFVAuK83HtpKpump) | 0.35 | 0.38 | 2.94 / −10% | 4.0 s | BAM `bkpk9K` | guard fail | -0.0015 |
| 7 | 01:35:01 | [GhksrL](https://gmgn.ai/sol/token/GhksrL6AdFUevB4XJULdNiNX6Hz8TgxzkgkNcPYypump) | 0.35 | 0.33 | 3.00 / −13% | 18.2 s | BAM `22rU5y` | failed | -0.0015 |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 34 | same | 3 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4QjjKhWpLicoLmGU9t4RvqWuDvazUTvhLUVRZTXneSWGWinrzmRjPDUbH48kH28auyLBTchJUZMcyQkxb5J2Johi) [dump](https://solscan.io/tx/4VjYzJK4EwYd1zQjuPezxMLSQcjJ2w2V2LTZLHdhJHwSMS5x1GJBQJt8TVoS53XcmNewezFVM97a3Rv1jQC8HAAb) |
| 2 | 39 | same | 2 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/3sKuvjtj5EF3nYGc8y8C6KEunw5A3HggnbWKwH6dx9W3tMBzEARHa3iqmG6iH4fDG8F6QENJH4Nq5WCDbCjGbF93) [sell](https://solscan.io/tx/2QcepMc2k68uFZyKN934npkKfCHzDfwA8XkV6h8fEVnaAKWUCCNioKKAgXmAmVwPqAgBj3vyNtnxhXNPjrcpTpL4) [dump](https://solscan.io/tx/2xAikBYwDLTiMwK7i14pq7RLTjQVrsSHAwuBZREjNE4B5V1K7RBE173TDAjc2tfxxUrpVFNvULkHinwLszM4JU8E) |
| 3 | 43 | same | 6 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5yXs46ZMbUkFiy48WX8K2x8st9kgy4jbRJbYCrNvoTXMAhbm5DGk1EBLf6u2hFrQBXDQU5Jupbm6C4AznyUv6AFR) [dump](https://solscan.io/tx/3tNqiajF51XWtGydpcRUPUFDpjX3wkWE27krsbDWoWeoDxZL4B3kFjtH6VegRLj9iucLqNA4Cv2sRy5BrTsSSucC) |
| 4 | 37 | +1 | 2 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/3NHbB2z4BzWmfVnWx1QCy3Zv9zuFXrN49fVjJbrgb1eANa4HMVMdFmHVuaaH3yYVdce3L1iBPamUhA3B9o5Wvzby) [dump](https://solscan.io/tx/4W9gASR6My4PjAooMEK6SV8nY9XRPWjKPCpqpUSV2D32ZTGgpzzRZPWAg3ZNv7cpg7oYvRgqbPQWLPVPVZEFY5f7) |
| 5 | 36 | same | 3 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/imt54UqamHWD64U67YK7WSjcmj7pqNvVBnHtp7BGPhnyE1WkQ9qjZjUsZ8P64Pt2m9VhUx4WzcRwsNYc6WCF3JY) [dump](https://solscan.io/tx/2KvNyRqnCAVBtZcRqRSTu7vLAYBpofVXKLaSui7s2gwnJh9pumVx5ijS4NJeW1eV1mLR6Z897bNpxTZQn1vHgx7u) |
| 6 | 55 | same | 21 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/5vn94mkVJye7RRoF2bjVYChuC5MYjfEWn3kHZmz63kEK9MzayUNsJk73j6K4M9jen2ERzj4U74GBMnxQe29JhVXv) [dump](https://solscan.io/tx/58SvQMMHbwzmLR6KugrAevjaBq17BpcBuWXw1RUiqyThCFjSNRMRk5MU7D8en26aeBTSLcp32yhUAfZeoS6xiMJe) |
| 7 | 24 | same | 2 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4Qtv1xc7AynqaTw6i28vxZG4rfUCxgd4N8KFJqfVNpfw7kMW7JRTnwkKqXsokdEakLvshGEsfQnzvQ5gtdnTcFs9) [dump](https://solscan.io/tx/NRrK6uSUGJPpmnYbgNoGK7KobrdiQdj7tAnvPF29vhh5822jYhuC9yXXAVxSxWRdT8A5ynibiMP37pzKw9kb9o4) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| BAM | 4 | 1 | 25% | +0.0265 | +0.0310 | 1/1 |
| Harmonic | 3 | 0 | 0% | -0.0045 | – | 0/0 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 5 | 1 | 20% | +0.0250 | +0.0310 | 1/1 |
| dev list | 2 | 0 | 0% | -0.0030 | – | 0/0 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 6 | 1 | 17% | +0.0235 | +0.0310 | 1/1 |
| next block | 1 | 0 | 0% | -0.0015 | – | 0/0 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 01:00 | 7 | 1 | 14% | +0.0220 | +0.0310 | 1/1 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 1 | +0.0310 | +0.0310 | 1.5 s |

## 8. P&L leaders
**Best trades:** 8yFPX6 +0.0310 (BAM, time-limit, score 0.43)

**Worst trades:** 8yFPX6 +0.0310 (BAM, time-limit, score 0.43)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `6TkKqq15` | AgaveBam | 1 | 1 | +0.0310 |
| `AMukCLCr` | HarmonicAgave | 1 | 0 | -0.0015 |
| `STKEsvUS` | AgaveBam | 1 | 0 | -0.0015 |
| `bkpk9KVs` | AgaveBam | 1 | 0 | -0.0015 |
| `22rU5yUm` | AgaveBam | 1 | 0 | -0.0015 |
| `DrifTrN9` | HarmonicAgave | 2 | 0 | -0.0030 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 2070 (p25 1300, p75 2133, n 7) |
| Executed-feed lag behind first sighting, ms | 0.7 (p25 0.7, p75 0.7, n 7) |
| Buy sent → our tx seen on the feed, ms | 33.4 (p25 32.6, p75 37.7, n 7) |
| Fills: our buy seen on the feed after the dump, ms | 39 (p25 39, p75 39, n 1) |
| Guard fails: our failed buy seen after the dump, ms | 37 (p25 36, p75 43, n 5) |
| Fills in the dump's own block | 1 of 1 |
| Guard fails in the dump's own block | 4 of 5 |

**Which copy landed (nonce fan-out):** staked-rpc 7

**Send-path answers (FAST-ACK lines):** nozomi 7 (median ack 0.3 ms), helius-swqos 7 (median ack 1.0 ms), staked-rpc 7 (median ack 3.0 ms), bolt 4 (median ack 0.5 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 2 |
| Guard fails: rival buys ahead (median) | 3 |
| Guard fails: rival SOL ahead (median) | 2.37 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 2KtcBC (pre-placed) | 2 | 2 |
| 9k78QZyw (fast bot) | 2 | 2 |
| CVPz447t (pre-placed) | 2 | 2 |
| 8PgC4ngp | 2 | 1 |
| 6n2cCJrr | 2 | 2 |
| HLU8QbLd (41Pr family) | 1 | 0 |
| BfcqTk6L | 1 | 1 |
| Gq5wJWbT | 1 | 1 |
| GonzYBmk | 1 | 1 |
| BUkpShoE* | 1 | 1 |
| EprLoV21* | 1 | 1 |
| 7PedQZmc (untipped fast) | 1 | 1 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.0433 |
| Pump fee on buys | 0.0043 (0.0043 per fill) |
| Pump fee on sells (residual) | 0.0049 (0.0049 per fill) |
| Buy tx fees (base + priority) | 0.0015 (0.00151 per fill) |
| Buy tips | 0.0000 (0.0000 per fill) |
| Sell tx fees | 0.0006 (0.00060 per fill) |
| Sell tips | 0.0010 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0090 (6 buys) |
| **Result** | **+0.0220** |

Buy compute used (fills): median 79,608 CU, max 79,608 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ start refused: Error: keystore: wrong passphrase or damaged file
- ⚠️ 1 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getLatestBlockhash: 16 timeouts/transport errors (worst p99 1001 ms)
- ⚠️ RPC bh-fallback getSlot: 16 timeouts/transport errors (worst p99 1001 ms)
- ℹ️ 10 send-path health events (self-heal), e.g. `SEND-PATH rpc bh-fallback UNHEALTHY: 3 timeouts / transport errors in a row (getLatestBlockhash): client REBUILT (fresh `
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Recommended / open:**

- Run 13: back to 5M, M2 shadow (dip11).

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r12.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r12.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 1.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

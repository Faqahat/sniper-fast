# Amsterdam run 11 — dip bot run report

*Durable-nonce fan-out (dip10) + Constant-K standby RPC; 1.3 s / SL −10% at 0.35 + dev 0.55*

> **Verdict:** Short (26 min, −0.0202 SOL: 1 fill BUQvqA1Y −0.0192 on a BAM leader, 2 guard fails). Nonce worked as designed.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.0202 SOL** (wallet 1.2965 → 1.2763, Δ -0.0202) |
| Started (PKT) | 2026-10-25 00:29:43 |
| Ended (PKT) | 2026-10-25 00:55:22 — stopped by the owner at 00:55 to start run 12 at 15M buy priority |
| Ran for | 0 h 25 min of 480 min planned |
| First / last buy (PKT) | 00:38:38 / 00:50:18 |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 3 → **1 filled**, 2 failed on the +5% guard |
| Fill rate | 33% |
| Wins / losses (fills) | 0 / 1 (win rate 0%) |
| Per filled buy | avg -0.0192, median -0.0192 SOL |
| Fills only / failed buys only | -0.0192 / -0.0010 SOL |
| Best / worst trade | BUQvqA -0.0192 / BUQvqA -0.0192 |
| Fill landing | median 30 ms after the dump (seen on our feed); 1 of 1 in the dump's own block |

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
| limits | max 60 fills, 1 open at a time, 480 min, loss cap 0.296 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 10**:

| Setting | AMS run 10 | AMS run 11 |
|---|---|---|
| engine build | dip9 | dip10 |
| durable-nonce fan-out | off (one tx to every path, every path's tip in it) | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | RMR_RPC_URL | CK_STANDBY_URL |
| limits | max 60 fills, 1 open at a time, 480 min, loss cap 0.443 SOL | max 60 fills, 1 open at a time, 480 min, loss cap 0.296 SOL |

- Engine dip9 → dip10 with --nonce /root/prod/nonce_ams.txt (8 accounts).
- Backup RPC: Helius → Constant-K's Frankfurt endpoint (--fallback ck).

## 4. Timeline (PKT)
- **00:26** first start refused: Helius standby RPC out of credits (429); nothing sent
- **00:29:43** engine start #1 (session with 3 buys)
- **00:55:22** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 1416 |
| Inside the envelope (age / drop / since-buy / size) | 611 |
| Picks (score above the threshold) | 20 |
| Skipped | far_leader 16, spacing 1 |
| Buys sent | 3 |
| Filled | 1 |
| Failed on the +5% guard | 2 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 1 of 1 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 00:38:38 | [8P8TcE](https://gmgn.ai/sol/token/8P8TcE87L9w5tjjr5Jatr2VZj8PtYEBbhMzFheT1kq1f) | 0.55 dev | 0.26 | 8.25 / −30% | 5.3 s | Harmonic `HW4zor` | guard fail | -0.0005 |
| 2 | 00:46:54 | [BUQvqA](https://gmgn.ai/sol/token/BUQvqA1YGejUCTWcZh5Kd57mntWrx3bJnR36rnw2J1mX) | 0.35 | 0.63 | 5.79 / −28% | 3.6 s | BAM `722RdW` | filled | **-0.0192** |
| 3 | 00:50:18 | [2DSXKT](https://gmgn.ai/sol/token/2DSXKTPodW8rEWiZkLFxWbCMWjp53hTQ2zMhgWHzpump) | 0.35 | 0.82 | 2.88 / −16% | 4.9 s | Jito `LeDbQ9` | guard fail | -0.0005 |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 251 | +1 | 7 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/REykTCehpPzacrSFLbSikLHymWbktvJbDpsZYQcAeXxzvbrrApGEt6nMGvK3itveu1h2qqfH9SNNkcNws94TmEc) [dump](https://solscan.io/tx/5k7zY9tyjnqT3534nLbomVhntAsmTp56eYUr6MYNihcwbs7mbFGKfosrxFSsxfzS2C3PwCNpuRBDnzKMe6Q4VoXD) |
| 2 | 30 | same | 2 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/5KNjqJfZjerjGm8Fk6QWZccRJHwMGKet1mHE5AwHfkmj8yuJQvTibkbVvYQkpmaZPBbKraAjTQLGjAYD9jB73CJy) [sell](https://solscan.io/tx/3B7Ud1s5P2Qe39LW8gUoUC7UMyCZrBZHmoWpQ7oJkgrZuEHPQrv8cF1qZtzoixTJLc9A178gCnZjdCMVbt9uRBg4) [dump](https://solscan.io/tx/5zk2PB8mJrq1isqwfz75M1vPY895Cnjkt1yLpCEw9cwe7S1PGJbxmEMdJLrtU6fs4Mr7zs3p42YmokM7E7SDdNK3) |
| 3 | 112 | same | 2 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3czJMxQgeNizTsnLAQjKRLjUV9wntPbsb6USTmLPk5nSpygJU8D5W3hEAp3MNQS8RheyER8kdfCPbDVE8D63XMfd) [dump](https://solscan.io/tx/2zSarZH9QUc1n6fPpxH7R3553xwQ6UJ3wW2NwPRPiNKtGpjDaPotbQNPu4eRuVSTNokt3vpjB8me4ULXRXjmDSzw) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Harmonic | 1 | 0 | 0% | -0.0005 | – | 0/0 |
| BAM | 1 | 1 | 100% | -0.0192 | -0.0192 | 0/1 |
| Jito | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 2 | 1 | 50% | -0.0197 | -0.0192 | 0/1 |
| dev list | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 2 | 1 | 50% | -0.0197 | -0.0192 | 0/1 |
| next block | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 00:00 | 3 | 1 | 33% | -0.0202 | -0.0192 | 0/1 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 1 | -0.0192 | -0.0192 | 1.5 s |

## 8. P&L leaders
**Best trades:** BUQvqA -0.0192 (BAM, time-limit, score 0.63)

**Worst trades:** BUQvqA -0.0192 (BAM, time-limit, score 0.63)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `HW4zorvt` | HarmonicAgave | 1 | 0 | -0.0005 |
| `LeDbQ99Q` | JitoLabs | 1 | 0 | -0.0005 |
| `722RdWmH` | AgaveBam | 1 | 1 | -0.0192 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1697 (p25 1034, p75 3650, n 3) |
| Executed-feed lag behind first sighting, ms | 0.4 (p25 0.4, p75 3.3, n 3) |
| Buy sent → our tx seen on the feed, ms | 110.3 (p25 25.5, p75 248.0, n 3) |
| Fills: our buy seen on the feed after the dump, ms | 30 (p25 30, p75 30, n 1) |
| Guard fails: our failed buy seen after the dump, ms | 181 (p25 112, p75 251, n 2) |
| Fills in the dump's own block | 1 of 1 |
| Guard fails in the dump's own block | 1 of 2 |

**Which copy landed (nonce fan-out):** nozomi 2, staked-rpc 1

**Send-path answers (FAST-ACK lines):** nozomi 3 (median ack 0.4 ms), staked-rpc 3 (median ack 2.3 ms), helius-swqos 2 (median ack 0.5 ms), bolt 1 (median ack 1.9 ms), helius 1 (median ack 0.4 ms), jito-bundle 1 (median ack 0.9 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 2 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 2.66 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| EWFv5ZJ9* | 2 | 1 |
| CWGXmc3v | 1 | 1 |
| FUru6V3L* | 1 | 1 |
| AWrTFnoS | 1 | 1 |
| 4GCtzCQb | 1 | 1 |
| DF7eRXHn | 1 | 1 |
| EJX629cp* | 1 | 1 |
| haqq (dip bot) | 1 | 1 |
| G9G3dCBG | 1 | 0 |
| 6n2cCJrr | 1 | 1 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | -0.0075 |
| Pump fee on buys | 0.0043 (0.0043 per fill) |
| Pump fee on sells (residual) | 0.0042 (0.0042 per fill) |
| Buy tx fees (base + priority) | 0.0005 (0.00051 per fill) |
| Buy tips | 0.0010 (0.0010 per fill) |
| Sell tx fees | 0.0006 (0.00060 per fill) |
| Sell tips | 0.0010 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0010 (2 buys) |
| **Result** | **-0.0202** |

Buy compute used (fills): median 76,679 CU, max 76,679 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ start refused: Error: --rpc-fallback-url-env RMR_RPC_URL: getGenesisHash timed out — cannot verify the cluster: refusing to start
- ⚠️ 1 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getLatestBlockhash: 1 timeouts/transport errors (worst p99 129 ms)
- ⚠️ RPC bh-fallback getSlot: 1 timeouts/transport errors (worst p99 197 ms)
- ℹ️ 2 send-path health events (self-heal), e.g. `SEND-PATH rpc bh-fallback UNHEALTHY: 3 timeouts / transport errors in a row (getSlot): client REBUILT (fresh pool + conn`
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Done after this run:**

- Owner OK'd a 15M buy-priority test on Amsterdam (run 12): leader-type study showed Amsterdam BAM fills at 5 wins of 18, −0.028 SOL per fill, despite 89% landing in the dump's block.

**Recommended / open:**

- Run 12: 15M buy priority (sells 5M).

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r11.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r11.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 1.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

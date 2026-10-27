# Amsterdam run 14 — dip bot run report

*A/B, IMIT1 side: no-BAM near list (54 leaders), 5-slot hold / no stop, M2 + pre-send shadows*

> **Verdict:** −0.056 SOL on 1 fill of 3 buys in ~2.4 h. Without the BAM leaders IMIT1 almost never fires here (65 of 71 picks were on leaders off the list); the M2 shadow would have bought ~30 on these leaders. Stopped for the pre-send probe.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.0560 SOL** (wallet 1.2842 → 1.2282, Δ -0.0560) |
| Started (PKT) | 2026-10-25 06:09:28 |
| Ended (PKT) | 2026-10-25 08:30:44 — stopped with Ctrl+C (SIGINT) |
| Ran for | 2 h 21 min of 540 min planned |
| First / last buy (PKT) | 06:17:36 / 06:44:32 |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 3 → **1 filled**, 2 failed on the +5% guard |
| Fill rate | 33% |
| Wins / losses (fills) | 0 / 1 (win rate 0%) |
| Per filled buy | avg -0.0550, median -0.0550 SOL |
| Fills only / failed buys only | -0.0550 / -0.0010 SOL |
| Best / worst trade | HDoame -0.0550 / HDoame -0.0550 |
| Fill landing | median 39 ms after the dump (seen on our feed); 1 of 1 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip12 (M2 + pre-send shadow) |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.55 SOL |
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
| near-leader gate | 54 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off (shadow only) |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 540 min, loss cap 0.284 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 13**:

| Setting | AMS run 13 | AMS run 14 |
|---|---|---|
| engine build | dip11 (M2 shadow) | dip12 (M2 + pre-send shadow) |
| exit | take-profit off / stop-loss −10% / time limit 6 slots (~1.3 s) | take-profit off / stop-loss −50% / time limit 5 slots (~1.1 s) |
| near-leader gate | 120 leaders (buys only when the dump's leader is on the near list) | 54 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off | off (shadow only) |
| limits | max 60 fills, 1 open at a time, 540 min, loss cap 0.298 SOL | max 60 fills, 1 open at a time, 540 min, loss cap 0.284 SOL |

- Near list: Amsterdam's 120 leaders → 54 non-BAM leaders (BAM leaders lost money here: about −0.028 SOL per fill).
- Exit: 6 slots / SL −10% → 5 slots / no stop (SL −50%), as Frankfurt's A/B side.
- Engine dip12: pre-send shadow on (logs only).

## 4. Timeline (PKT)
- **06:09:28** engine start #1 (session with 3 buys)
- **06:44:32** big loss: HDoame -0.0550 SOL (time-limit)
- **08:30:44** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends
- **08:34** stopped by the agent (owner chose 'Amsterdam now' for the pre-send probe); no open position

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 7479 |
| Inside the envelope (age / drop / since-buy / size) | 3405 |
| Picks (score above the threshold) | 71 |
| Skipped | far_leader 65, spacing 3 |
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
| 1 | 06:17:36 | [3uxMAY](https://gmgn.ai/sol/token/3uxMAYWzGVqg4ut2dn41gFgAPkBoAWRMt65jgquxSu9S) | 0.55 dev | 0.76 | 12.04 / −49% | 1.7 s | Jito `2Df1aL` | guard fail | -0.0005 |
| 2 | 06:33:09 | [2XqFe8](https://gmgn.ai/sol/token/2XqFe8VE1SQ9xBLt5uLQ47FYfAF3pzKm15cePSaJpump) | 0.35 | 1.41 | 5.03 / −16% | 165.2 s | Jito `8o8wWC` | guard fail | -0.0005 |
| 3 | 06:44:32 | [HDoame](https://gmgn.ai/sol/token/HDoame3R14SzgNF8kjji2yr72g96mb3h7ZKt3wtfpump) | 0.35 | 0.49 | 3.27 / −16% | 310.8 s | Jito `ACvL73` | filled | **-0.0550** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 131 | same | 4 | **nozomi** of landx-fra3+jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/MHSFEkHYfKo2bHiQcGooNcCCzENpJNG9tFCxvUfQLkBJHeXtKMyT2WTDdQQdXHH1EXacf2MryGNuHbB1Ttid2ZT) [dump](https://solscan.io/tx/QqPcS5kn2jap6fKkBbHv56etkoM3vhA6zfuS4vp298zHWobbNF5HhJozvxZDjyHHERw5T3hrMtJavLGMaudTrvR) |
| 2 | 64 | +1 | 3 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/5X6mYobK5WbqWYuWJASoZfBQzG59NeisqBej3DbRP3hUi8JbvtNf2xgLA37cVcShiS99JhbfUaGV2MvRjpL1tU8L) [dump](https://solscan.io/tx/2vaDKwmEe8aLQHEoH61jZcWy4zKaiBiXLLvzC7yDkHwqFT5MidJQJqPUCMK11mLA9Mni9ekvN1xUoXQbM8nf7qmg) |
| 3 | 39 | same | 0 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/3AbyoeVUH6tknQUPA2nzjeqT68WG5ujCKtytpUkppCJ6HsAt4fryGbxey7XXgMK4RqWgio3qcYUPtnuSnNQSuqGR) [sell](https://solscan.io/tx/dAP3uAnrU4XKtfTSvUyrToiwbDjr2G1SBw2x5qQerDyR57PfHA1zf7YDEuZdoBeCbuTjE4yEhDVXyPyPKNRowhG) [dump](https://solscan.io/tx/5it2TjhmbmVoGJDpc5DfqniPTfc8Diqt4q5YacRCEFs1vtH7a6enfe6ukPEKji6BDxCibuUkwEpPDuMtqyZZAGGe) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Jito | 3 | 1 | 33% | -0.0560 | -0.0550 | 0/1 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 2 | 1 | 50% | -0.0555 | -0.0550 | 0/1 |
| dev list | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 2 | 1 | 50% | -0.0555 | -0.0550 | 0/1 |
| next block | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 06:00 | 3 | 1 | 33% | -0.0560 | -0.0550 | 0/1 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 1 | -0.0550 | -0.0550 | 1.4 s |

## 8. P&L leaders
**Best trades:** HDoame -0.0550 (Jito, time-limit, score 0.49)

**Worst trades:** HDoame -0.0550 (Jito, time-limit, score 0.49)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `2Df1aLCR` | JitoLabs | 1 | 0 | -0.0005 |
| `8o8wWCYN` | JitoLabs | 1 | 0 | -0.0005 |
| `ACvL73V4` | JitoLabs | 1 | 1 | -0.0550 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 3059 (p25 1185, p75 4232, n 3) |
| Executed-feed lag behind first sighting, ms | 1.0 (p25 0.9, p75 1.1, n 3) |
| Buy sent → our tx seen on the feed, ms | 59.0 (p25 36.1, p75 129.0, n 3) |
| Fills: our buy seen on the feed after the dump, ms | 39 (p25 39, p75 39, n 1) |
| Guard fails: our failed buy seen after the dump, ms | 97 (p25 64, p75 131, n 2) |
| Fills in the dump's own block | 1 of 1 |
| Guard fails in the dump's own block | 1 of 2 |

**Which copy landed (nonce fan-out):** nozomi 2, helius 1

**Send-path answers (FAST-ACK lines):** nozomi 3 (median ack 0.5 ms), helius 3 (median ack 0.7 ms), staked-rpc 3 (median ack 3.6 ms), jito-bundle 3 (median ack 1.9 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 0 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 3.16 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| BfcqTk6L | 1 | 1 |
| A9KKBdLy | 1 | 1 |
| 9k78QZyw (fast bot) | 1 | 1 |
| CVPz447t (pre-placed) | 1 | 1 |
| 7PedQZmc (untipped fast) | 1 | 1 |
| 8PgC4ngp | 1 | 1 |
| 7Fmy1zv7 | 1 | 1 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | -0.0438 |
| Pump fee on buys | 0.0043 (0.0043 per fill) |
| Pump fee on sells (residual) | 0.0038 (0.0038 per fill) |
| Buy tx fees (base + priority) | 0.0005 (0.00051 per fill) |
| Buy tips | 0.0010 (0.0010 per fill) |
| Sell tx fees | 0.0006 (0.00060 per fill) |
| Sell tips | 0.0010 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0010 (2 buys) |
| **Result** | **-0.0560** |

Buy compute used (fills): median 76,758 CU, max 76,758 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 1 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getLatestBlockhash: 236 timeouts/transport errors (worst p99 1002 ms)
- ⚠️ RPC bh-fallback getSlot: 235 timeouts/transport errors (worst p99 1002 ms)
- ℹ️ 51 send-path health events (self-heal), e.g. `SEND-PATH rpc bh-fallback UNHEALTHY: 3 timeouts / transport errors in a row (getSlot): client REBUILT (fresh pool + conn`
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)
- ⚠️ big loss HDoame -0.0550 (time-limit, Jito)

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Recommended / open:**

- Run 15: pre-send live DRY run (10 min), then run 16: the live pre-send probe.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r14.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r14.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

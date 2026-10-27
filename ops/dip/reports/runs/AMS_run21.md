# Amsterdam run 21 — dip bot run report

*Live 1 h: routes v12 (soyas, solami, glaive, falcon, falcon-udp) + M2 gate on dip18; 0.35 SOL; no pre-send live*

> **Verdict:** −0.001 SOL (1.8166 → 1.8156): 23 picks, 2 buys, both failed on the +5% guard (fees only). 4F9ft4 landed in the dump's own block via falcon 22 ms after the dump but behind 5 rival buys; 2oAztc (dev list) landed one block late via solami (84 ms, 3 rivals ahead). 16 picks were skipped as far_leader (not on the Amsterdam near list).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.0010 SOL** (wallet 1.8166 → 1.8156, Δ -0.0010) |
| Started (PKT) | 2026-10-26 02:19:29 |
| Ended (PKT) | 2026-10-26 02:49:43 — stopped with Ctrl+C (SIGINT) |
| Ran for | 0 h 30 min of 60 min planned |
| First / last buy (PKT) | 02:33:14 / 02:46:09 |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 2 → **0 filled**, 2 failed on the +5% guard |
| Fill rate | 0% |
| Wins / losses (fills) | 0 / 0 |
| Per filled buy | – |
| Fills only / failed buys only | +0.0000 / -0.0010 SOL |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip18 (QUIC lanes soyas / solami + falcon-udp) |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.35 SOL |
| exit | take-profit off / stop-loss −50% / time limit 5 slots (~1.1 s) |
| price guard | +5% over the post-dump price (pump error 6042 if exceeded); slot deadline = dump slot + 1 |
| buy fee (priority) | 5M µL/CU × 100k CU limit = 0.0005 SOL per landed buy tx |
| sell fee | 5M µL/CU × 120k CU limit (0.0006 SOL per landed sell tx) |
| route: agave leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: bam leaders | nozomi + helius-swqos + bolt + falcon + falcon-udp + soyas + solami |
| route: default leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: fd leaders | nozomi + landx-fra3 + staked-rpc + soyas + solami |
| route: harmonic leaders | nozomi + landx-fra3 + falcon + falcon-udp + glaive + soyas + solami |
| route: jito leaders | solami + soyas + glaive + falcon + falcon-udp + helius-swqos |
| route: other leaders | nozomi + helius-swqos + bolt + staked-rpc |
| sell path | staked-rpc (retry also via nozomi) |
| near-leader gate | 120 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off (shadow only) |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 60 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 20**:

| Setting | AMS run 20 | AMS run 21 |
|---|---|---|
| engine build | dip18 | dip18 (QUIC lanes soyas / solami + falcon-udp) |
| size (normal) | 0.45 SOL | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.45 SOL | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.35 SOL |
| route: bam leaders | nozomi + helius-swqos + bolt + falcon + falcon-udp | nozomi + helius-swqos + bolt + falcon + falcon-udp + soyas + solami |
| route: fd leaders | nozomi + landx-fra3 + staked-rpc | nozomi + landx-fra3 + staked-rpc + soyas + solami |
| route: harmonic leaders | nozomi + falcon + falcon-udp + landx-fra3 | nozomi + landx-fra3 + falcon + falcon-udp + glaive + soyas + solami |
| route: jito leaders | falcon + falcon-udp + helius-swqos + helius | solami + soyas + glaive + falcon + falcon-udp + helius-swqos |
| pre-send | LIVE: whale >= 6%, 4 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 100 fills / 0.1000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% | off (shadow only) |
| limits | max 60 fills, 1 open at a time, 240 min, loss cap 0.500 SOL | max 60 fills, 1 open at a time, 60 min, loss cap 0.500 SOL |

## 4. Timeline (PKT)
- **02:19:29** engine start #1 (session with 2 buys)
- **02:49** stopped with Ctrl+C at 02:49:43, about a minute after Frankfurt run 22's kill switch (02:48:50)
- **02:49:43** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 1462 |
| Inside the envelope (age / drop / since-buy / size) | 599 |
| Picks (score above the threshold) | 23 |
| Skipped | far_leader 16, spacing 5 |
| Buys sent | 2 |
| Filled | 0 |
| Failed on the +5% guard | 2 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 0 of 0 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 02:33:14 | [4F9ft4](https://gmgn.ai/sol/token/4F9ft4vQEksNcXiLVrnchmQbdLAKoMeNT7XcfHDU9iin) | 0.35 | -0.88 | 2.71 / −13% | 2.8 s | BAM `GBQ2Gv` | guard fail | -0.0005 |
| 2 | 02:46:09 | [2oAztc](https://gmgn.ai/sol/token/2oAztchJv6gsPzJ8A539KauiAcT6PN9zaUiZTaMC56jg) | 0.35 dev | 0.70 | 4.68 / −24% | 1.9 s | Harmonic `DrifTr` | guard fail | -0.0005 |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 22 | same | 5 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon | – | – | [buy](https://solscan.io/tx/2ki533p51ACzs9my9vfz3oCwi5eARGpxT1MmHmiYv4AjxSTJA5H7aajtHJUYRxkSkWDrZmtoZasD7Rgdhux1xPkz) [dump](https://solscan.io/tx/2dwxdWCd9an8L5fUmRg2WULKAm1u6uyEjBpYDxU6TSfmSvuN1xf4EQFLvunMa9oCZE1RVyMpXDHwYFgzeAzLLd7F) |
| 2 | 84 | +1 | 3 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive | – | – | [buy](https://solscan.io/tx/3rTJH2Tk275oT1tVr6PZbZfEYKg5ghdksNj8SoQHtLWUod1c2zJnZtfurmJKnhBFxC1P5tTFThT234nrX9wUXe8X) [dump](https://solscan.io/tx/5UDeS5613GEWXF1pdiDRJFgRNRGksKj3Kft1zYiaUwtQ1pSHxz9QjoHrVT38wvD1fYNYevFc5Wo2JJAaxnHmSUHm) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| BAM | 1 | 0 | 0% | -0.0005 | – | 0/0 |
| Harmonic | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 1 | 0 | 0% | -0.0005 | – | 0/0 |
| dev list | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 1 | 0 | 0% | -0.0005 | – | 0/0 |
| next block | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 02:00 | 2 | 0 | 0% | -0.0010 | – | 0/0 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|

## 8. P&L leaders
**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `GBQ2GvTz` | AgaveBam | 1 | 0 | -0.0005 |
| `DrifTrN9` | HarmonicAgave | 1 | 0 | -0.0005 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1264 (p25 1064, p75 1464, n 2) |
| Executed-feed lag behind first sighting, ms | 1.0 (p25 0.7, p75 1.3, n 2) |
| Buy sent → our tx seen on the feed, ms | 50.2 (p25 19.4, p75 81.1, n 2) |
| Fills: our buy seen on the feed after the dump, ms | – (p25 –, p75 –, n 0) |
| Guard fails: our failed buy seen after the dump, ms | 53 (p25 22, p75 84, n 2) |
| Fills in the dump's own block | 0 of 0 |
| Guard fails in the dump's own block | 1 of 2 |

**Which copy landed (nonce fan-out):** falcon+falcon-udp 1, solami 1

**Send-path answers (FAST-ACK lines):** nozomi 2 (median ack 0.3 ms), falcon 2 (median ack 1.0 ms), bolt 1 (median ack 1.2 ms), helius-swqos 1 (median ack 1.2 ms), glaive 1 (median ack 0.9 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | – |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 2.78 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 634yyAz3* | 1 | 1 |
| CzAzndSP* | 1 | 1 |
| DF7eRXHn | 1 | 1 |
| 8yYMhuYo | 1 | 1 |
| 3axMAeeJ* | 1 | 1 |
| ocBBRKb1* | 1 | 1 |
| 2KtcBC (pre-placed) | 1 | 1 |
| AhMYGUEt | 1 | 1 |

## 11. Costs
No fills. Failed buys cost 0.0010 SOL in tx fees.

## 12. Health checks and red flags
- ⚠️ RPC bh-fallback getLatestBlockhash: 13 timeouts/transport errors (worst p99 1001 ms)
- ⚠️ RPC bh-fallback getSlot: 13 timeouts/transport errors (worst p99 1001 ms)
- ℹ️ 6 send-path health events (self-heal), e.g. `SEND-PATH rpc bh-fallback UNHEALTHY: 3 timeouts / transport errors in a row (getLatestBlockhash): client REBUILT (fresh `
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
- none recorded

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r21.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r21.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

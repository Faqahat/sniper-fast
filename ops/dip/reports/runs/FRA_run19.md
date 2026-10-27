# Frankfurt run 19 — dip bot run report

*Relay probe (Jito + Harmonic leaders): glaive, falcon, helius-swqos, astralane, landx-fra3, flashblock; no trading*

> **Verdict:** No trades, by design. −0.0364 SOL = fees of 72 probes, all landed (the run ended after the 72nd probe, 12 min). In the dump's block, both leader types together (probe_r19.json): falcon 92% (feed p50 85 ms), glaive 83% (49 ms), landx-fra3 67% (55 ms), astralane 58% (73 ms), flashblock 42% (87 ms), helius-swqos 33% (92 ms).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.0000 SOL** (wallet 2.5777 → 2.5413, Δ -0.0364) |
| Started (PKT) | 2026-10-25 21:34:37 |
| Ended (PKT) | 2026-10-25 21:46:56 — time limit / max trades |
| Ran for | 0 h 12 min of 60 min planned |
| First / last buy (PKT) | no buys |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 0 → **0 filled**, 0 failed on the +5% guard |
| Fill rate | – |
| Wins / losses (fills) | 0 / 0 |
| Per filled buy | – |
| Fills only / failed buys only | +0.0000 / +0.0000 SOL |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | probe mode (exact build not in the log) |
| model / tier | IMIT1 strict (score >= 0.5419) |
| size (normal) | 0.05 SOL |
| dev list | off |
| exit | take-profit +5% / stop-loss −10% / time limit 6 slots (~1.3 s) |
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
| near-leader gate | 199 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off |
| durable-nonce fan-out | off (one tx to every path, every path's tip in it) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 1 fills, 1 open at a time, 60 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 16**:

| Setting | FRA run 16 | FRA run 19 |
|---|---|---|
| engine build | dip14 (speed fixes; shred fire logs only) | probe mode (exact build not in the log) |
| model / tier | IMIT1 wider (score >= 0.2109) | IMIT1 strict (score >= 0.5419) |
| size (normal) | 0.35 SOL | 0.05 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.35 SOL | off |
| exit | take-profit off / stop-loss −50% / time limit 5 slots (~1.1 s) | take-profit +5% / stop-loss −10% / time limit 6 slots (~1.3 s) |
| near-leader gate | 198 leaders (buys only when the dump's leader is on the near list) | 199 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off (shadow only) | off |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) | off (one tx to every path, every path's tip in it) |
| limits | max 60 fills, 1 open at a time, 120 min, loss cap 0.500 SOL | max 1 fills, 1 open at a time, 60 min, loss cap 0.500 SOL |

## 4. Timeline (PKT)
- **21:34:37** engine start #1 (session with 0 buys)
- **21:46:56** engine end #1: run end

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 703 |
| Inside the envelope (age / drop / since-buy / size) | 410 |
| Picks (score above the threshold) | 0 |
| Skipped | 0 |
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

**Send-path answers (FAST-ACK lines):** glaive 12 (median ack 0.4 ms), falcon 12 (median ack 0.4 ms), helius-swqos 12 (median ack 0.5 ms), astralane 12 (median ack 0.6 ms)

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
- ℹ️ wallet change -0.0364 vs trades +0.0000: gap -0.0364 SOL (transfers / rent / unsold — see notes)
- ℹ️ The wallet gap (−0.0364) is exactly the probes' fees in the jsonl.

Checks passed: fast-verify: 0 identical, 0 MISMATCHED.

## 13. Fixes and follow-ups
- none recorded

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r19.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r19.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

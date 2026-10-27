# Amsterdam run 18 — dip bot run report

*Relay probe P1b (Jito leaders, Amsterdam): 6 paths; no trading (cap 1 trade × 0.05 SOL, strict tier)*

> **Verdict:** No trades, by design. −0.0212 SOL = fees of the 42 probes that landed (46 sent in the 60 min). In the dump's block (probe_ams_r18.json): falcon 8/8 (75%, feed p50 115 ms), helius-swqos 63% (116 ms), flashblock 50% (126 ms), helius Sender Max 50% (135 ms), nextblock 29% (122 ms); blockrazor landed 3 of 7 (p50 99 ms).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.0000 SOL** (wallet 1.2021 → 1.1809, Δ -0.0212) |
| Started (PKT) | 2026-10-25 20:31:34 |
| Ended (PKT) | 2026-10-25 21:31:34 — time limit / max trades |
| Ran for | 1 h 00 min of 60 min planned |
| First / last buy (PKT) | no buys |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 0 → **0 filled**, 0 failed on the +5% guard |
| Fill rate | – |
| Wins / losses (fills) | 0 / 0 |
| Per filled buy | – |
| Fills only / failed buys only | +0.0000 / +0.0000 SOL |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | probe mode of dip14+ (exact build not in the log; CLOCK2 on) |
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
| near-leader gate | 120 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off |
| durable-nonce fan-out | off (one tx to every path, every path's tip in it) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 1 fills, 1 open at a time, 60 min, loss cap 0.202 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 17**:

| Setting | AMS run 17 | AMS run 18 |
|---|---|---|
| engine build | dip13 (pre-send live + sell fan-out) | probe mode of dip14+ (exact build not in the log; CLOCK2 on) |
| model / tier | IMIT1 wider (score >= 0.2109) | IMIT1 strict (score >= 0.5419) |
| size (normal) | 0.35 SOL | 0.05 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.55 SOL | off |
| exit | take-profit off / stop-loss −50% / time limit 5 slots (~1.1 s) | take-profit +5% / stop-loss −10% / time limit 6 slots (~1.3 s) |
| near-leader gate | 54 leaders (buys only when the dump's leader is on the near list) | 120 leaders (buys only when the dump's leader is on the near list) |
| pre-send | LIVE: whale >= 6%, 8 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 30 fills / 0.0600 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% | off |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) | off (one tx to every path, every path's tip in it) |
| limits | max 60 fills, 1 open at a time, 120 min, loss cap 0.221 SOL | max 1 fills, 1 open at a time, 60 min, loss cap 0.202 SOL |

## 4. Timeline (PKT)
- **20:31:34** engine start #1 (session with 0 buys)
- **21:31:34** engine end #1: run end

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 3208 |
| Inside the envelope (age / drop / since-buy / size) | 1463 |
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

**Send-path answers (FAST-ACK lines):** helius-swqos 8 (median ack 0.6 ms), helius 8 (median ack 0.5 ms), falcon 8 (median ack 0.4 ms), blockrazor 7 (median ack 0.4 ms, 4 errors)

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
- ⚠️ RPC bh-fallback getLatestBlockhash: 1 timeouts/transport errors (worst p99 201 ms)
- ⚠️ RPC bh-fallback getSlot: 2 timeouts/transport errors (worst p99 380 ms)
- ℹ️ send path blockrazor: 4 non-200 answers
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)
- ℹ️ wallet change -0.0212 vs trades +0.0000: gap -0.0212 SOL (transfers / rent / unsold — see notes)
- ℹ️ The wallet gap (−0.0212) is exactly the landed probes' fees in the jsonl.

Checks passed: fast-verify: 0 identical, 0 MISMATCHED.

## 13. Fixes and follow-ups
- none recorded

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r18.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r18.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

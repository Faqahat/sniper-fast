# Amsterdam run 15 — dip bot run report

*Pre-send LIVE DRY run (dip13, 10 min): builds and signs pre-sent buys, sends none*

> **Verdict:** Clean: 24 triggers, 15 windows armed, 494 attempts signed (sign 0.26 ms p50), limit exactly 0.88 × price, 53 ms pacing, live triggers = shadow triggers. Normal bot: 0 buys.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.0000 SOL** (wallet 1.2282 → 1.2282, Δ +0.0000) |
| Started (PKT) | 2026-10-25 08:37:19 |
| Ended (PKT) | 2026-10-25 08:47:19 — time limit / max trades |
| Ran for | 0 h 10 min of 10 min planned |
| First / last buy (PKT) | no buys |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 0 → **0 filled**, 0 failed on the +5% guard |
| Fill rate | – |
| Wins / losses (fills) | 0 / 0 |
| Per filled buy | – |
| Fills only / failed buys only | +0.0000 / +0.0000 SOL |
| Reactive bot / pre-send live | +0.0000 / +0.0000 SOL (pre-send: 0 fills, realized +0.0000, failed-attempt fees +0.0000, 0 wins; see section 4b) |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip13 (pre-send live + sell fan-out) |
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
| pre-send | DRY (builds + signs, never sends): whale >= 5%, 4 tries/slot, 0.200 SOL, limit x0.88, route helius-ps, caps 20 fills / 0.0300 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 10 min, loss cap 0.228 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 14**:

| Setting | AMS run 14 | AMS run 15 |
|---|---|---|
| engine build | dip12 (M2 + pre-send shadow) | dip13 (pre-send live + sell fan-out) |
| pre-send | off (shadow only) | DRY (builds + signs, never sends): whale >= 5%, 4 tries/slot, 0.200 SOL, limit x0.88, route helius-ps, caps 20 fills / 0.0300 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| limits | max 60 fills, 1 open at a time, 540 min, loss cap 0.284 SOL | max 60 fills, 1 open at a time, 10 min, loss cap 0.228 SOL |

- First start with the Helius API key (both Helius paths keyed; caps helius 15 / helius-swqos 15 / helius-ps 20 per s).
- Sell fan-out ON: every sell to staked-rpc AND Helius SWQoS in one tx (owner OK 08:05).

## 4. Timeline (PKT)
- **08:37:19** engine start #1 (session with 0 buys)
- **08:47:19** engine end #1: run end

## 4b. Pre-send live (pre-placed buys) — separate from the reactive bot
Buys pre-sent after a big whale buy, before any dump. **Not included in sections 5–11**, which cover only the reactive dip bot. Realized = the engine's PRESEND LIVE REALIZED records (chain txs of each buy and sell; the buy pays the token-account rent). Rent back = that rent returned when the engine closed each pre-send account after the exit (dip19+; before dip19 the sell closed it and the refund sat inside realized). Failed tries = fees of tries that landed and failed (6042 price, deadline, …). Net = realized + rent back − failed tries.

| Session | Started | Size / fill cap / fee cap | Tries sent | Fills | Wins | Realized | Rent back | Failed tries | Net | Stopped |
|---|---|---|---|---|---|---|---|---|---|---|
| #1 | 10-25 08:37 | 0.20 / 20 / 0.03 | 0 (+494 dry) | 0 | 0 | +0.0000 | +0.0000 | +0.0000 | **+0.0000** | run_end |

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 414 |
| Inside the envelope (age / drop / since-buy / size) | 212 |
| Picks (score above the threshold) | 4 |
| Skipped | far_leader 4 |
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
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)

Checks passed: fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Recommended / open:**

- Run 16: the same, with real attempts.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r15.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r15.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Pre-send (section 4b): the jsonl presend_live_* records (fills, closes, REALIZED, account closes, stops, end checks) and presend_attempt_land (try results, failed-try fees); the log's PRESEND LIVE lines when a run has no such records.
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

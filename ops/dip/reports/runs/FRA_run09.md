# Frankfurt run 9 — dip bot run report

*First two-region run — Frankfurt: 0.55 wider + dev 0.75, own near list (198)*

> **Verdict:** Small loss (−0.0419 SOL by the wallet).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.0419 SOL** (wallet 2.8278 → 2.7859, Δ -0.0419) |
| Started (PKT) | 2026-10-24 16:47:05 |
| Ended (PKT) | 2026-10-24 18:15:38 — stopped by the owner at 18:15 to start the run 10 A/B |
| Ran for | 1 h 28 min of 480 min planned |
| First / last buy (PKT) | 17:24:11 / 17:59:05 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 9 → **2 filled**, 7 failed on the +5% guard |
| Fill rate | 22% |
| Wins / losses (fills) | 1 / 1 (win rate 50%) |
| Per filled buy | avg -0.0192, median -0.0192 SOL |
| Fills only / failed buys only | -0.0384 / -0.0035 SOL |
| Best / worst trade | EgLPei +0.0236 / 6S3C8r -0.0620 |
| Fill landing | median 66 ms after the dump (seen on our feed); 1 of 2 in the dump's own block |

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
| near-leader gate | 198 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off |
| durable-nonce fan-out | off (one tx to every path, every path's tip in it) |
| backup RPC | RMR_RPC_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 480 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 8**:

| Setting | FRA run 8 | FRA run 9 |
|---|---|---|
| near-leader gate | 199 leaders (buys only when the dump's leader is on the near list) | 198 leaders (buys only when the dump's leader is on the near list) |

- Near list: near_leaders_5ms.txt (199) → near_leaders_fra.txt (198): one leader moved to Amsterdam, which never sees Frankfurt's leaders (no shared dumps).
- Wallet funded down: 1.5 SOL moved to Amsterdam after run 8 (balance 4.33 → 2.83).

## 4. Timeline (PKT)
- **16:47:05** engine start #1 (session with 9 buys)
- **17:44** routes v8 deployed for the NEXT runs (Jito tip 0.012 → 0.001 SOL; Jito leaders get helius + nozomi + jito-bundle + staked-rpc); run 9 kept its loaded settings
- **17:59:05** big loss: 6S3C8r -0.0620 SOL (stop-loss)
- **18:15:38** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 3642 |
| Inside the envelope (age / drop / since-buy / size) | 1846 |
| Picks (score above the threshold) | 25 |
| Skipped | far_leader 16 |
| Buys sent | 9 |
| Filled | 2 |
| Failed on the +5% guard | 7 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 2 of 2 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 17:24:11 | [7iCVdo](https://gmgn.ai/sol/token/7iCVdoaXxogYJ162fpKmHqgbDjJzeppQVmGvy5jNhnF) | 0.75 dev | 0.45 | 4.27 / −22% | 2.8 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 2 | 17:27:16 | [9f2gei](https://gmgn.ai/sol/token/9f2geiAhhEy1KFFTFpeBTa7oLPHrcXxr7ksDShDpump) | 0.55 | 0.27 | 7.91 / −36% | 3.8 s | BAM `9jxgos` | guard fail | -0.0005 |
| 3 | 17:27:26 | [8PNozd](https://gmgn.ai/sol/token/8PNozd45zLrdyCNVVstUyx7Xf3FDRNDBynStajxiwzov) | 0.75 dev | 0.77 | 4.41 / −24% | 13.8 s | Jito `HEL1US` | guard fail | -0.0005 |
| 4 | 17:33:05 | [EgLPei](https://gmgn.ai/sol/token/EgLPeiMXN7nhmWQuEdXQrbkoUJM4fDF3evMGygpBpump) | 0.55 | 0.35 | 4.72 / −14% | 9.8 s | Harmonic `5ZqveV` | filled | **+0.0236** |
| 5 | 17:35:55 | [DUw6mH](https://gmgn.ai/sol/token/DUw6mHhxk7LvY6KwYfWnGQJAkCZZbiTo3j5QKHP3pump) | 0.55 | 0.37 | 2.77 / −11% | 5.9 s | Jito `HEL1US` | guard fail | -0.0005 |
| 6 | 17:36:33 | [7oHGwb](https://gmgn.ai/sol/token/7oHGwb2sdj6qNBzm4KiBDJdkzcWLFNUjRmvPmTv9KTja) | 0.75 dev | 1.06 | 3.85 / −21% | 2.5 s | BAM `GEM1N1` | guard fail | -0.0005 |
| 7 | 17:48:50 | [7LtTpu](https://gmgn.ai/sol/token/7LtTpu3vLJaUzgW86NxneNSasUz8wTEkysXbU1rQpump) | 0.55 | 0.37 | 3.55 / −14% | 4.0 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 8 | 17:56:16 | [4gNjef](https://gmgn.ai/sol/token/4gNjefWMzww9Lawank7MRxpMoMFyRi5b8czgtAsxdjGj) | 0.75 dev | 1.25 | 3.85 / −21% | 3.2 s | Jito `A9mvuk` | guard fail | -0.0005 |
| 9 | 17:59:05 | [6S3C8r](https://gmgn.ai/sol/token/6S3C8r58LdYm7moJxjxDb8wqEdE8zQbvNZ9qDKwHpump) | 0.55 | 0.30 | 5.75 / −16% | 58.5 s | Jito `HEL1US` | filled | **-0.0620** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 19 | same | 3 | landx-fra3+nozomi+staked-rpc+helius-swqos+bolt | – | – | [buy](https://solscan.io/tx/2wibPAf9sQQ116UkkbtF3PUo9tgbXoVSs57YAxFfPuBVAg1Y5icxpL7Bi3TRB8TpGwMocr4KTy1S6eWFZ1TvLwJE) [dump](https://solscan.io/tx/62AYNaWowyGdcptqbpgDNUxqKQ4reFXJgnJTqLEEvUnqZSURJ9aqAEtTeKhtXfCNGaQxQ8kEJNDwPADXPqFUf3VD) |
| 2 | 17 | same | 4 | landx-fra3+nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/458gnx8FJJZHNc69HiWioCFTb89V1BkqNM5NozT6VzAixp9mJ2CqQXRxL4p4JrY3fNMFov4XbqZubtcqBjRNm2Q1) [dump](https://solscan.io/tx/N1ce4ac6EAJCYvgRYJ7m4YXtKrvnpKvnnNep1CqWbCheoE7cdWLqxynQ9mg6F8vsezBHBHE3MDquoVHCVkWyyvz) |
| 3 | 117 | +1 | 8 | helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/65d4CAViKDQ1Je69JwuiWtLebe6h66BHQPT25rB9tYM83u1jEF9mNUQD1swD74GS4EnnvJqB3KsdfSGL1PqBMx1F) [dump](https://solscan.io/tx/41EA27FX8s5avMrWnijXXg4VVWCZuBkB81hdhw4E5LQCUiBhXD9ZAq55Kva43fiFhDn3WS5fiL5Ci5cHef1RZoES) |
| 4 | 41 | same | 1 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/3eXs529LyVKRVUECbNY6XoPmnR1k3dAf1V59PAWaGimeJdj9pp5AqWMiJfmP8rc7zzQAatu6aGhkqzKdVLpQqdT9) [sell](https://solscan.io/tx/5JrNCKKtX7Po6nYfB7vAabRwrZfr6JFrMsA3f3wu43vkcAbYFDacw8vtrrUvdqaavN4htKBxZK3wQNKdJsjbCLFM) [dump](https://solscan.io/tx/YottrnGuUAeiPWHj13x2SrpEE7XrCJ8KPhWrVtZJ8Y1nBqHjBkhn4Uy9cP5HQugAXnwYbpvtHPk5Stc6oAzeRWa) |
| 5 | 101 | +1 | 4 | helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4EmkhbePGJ8Xkr7gVJkoQ7RBnFV7X1SLoadmmRFGGP1u2mYUQ8DbMFomAGLZdVTF14G3FDfrzHz4sdV4HYi9e68N) [dump](https://solscan.io/tx/35D6MzqpLmNGumfFnL3mZ9dNK4UmcgVBTEfNUCwm8NW6XNBqk2sVEzkwgwYeBDrrWppvymFcaBr3BdJEv4kWVnQs) |
| 6 | 22 | same | 5 | nozomi+helius-swqos+bolt+staked-rpc+helius | – | – | [buy](https://solscan.io/tx/22cL1T4WNyRyHLicNC4sjjYdqo1oxFrPPGRsro8QuDAzSEbrnqRmSX99qpSx5MKBpcccurXASzGkvq3Uw9m4bnjn) [dump](https://solscan.io/tx/4JGGKNicV7p4hk1rRE56bdb4XPt32D8WSCRh4QxsBimHKz87Qsp7Hytfc8cWu94bhfCbJUqbXLKb3SNsh9RWm6xm) |
| 7 | 37 | same | 5 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/zScQVcYDLB8f9od72iKCPTM9hD6q3X2x6gkpRAqgY2daq4Q6oh6FSarSKQadNta3RzfFFSU9mzwDRaVG2W1cS1g) [dump](https://solscan.io/tx/5W8XtkjiJfj4K2YwtZUqU7ksJj82eZSQM4KQNeAVihB3DMRe5G6qpoH6wxSy54UiLWAjnxN1XuDx2XNGNHYqPu2s) |
| 8 | 37 | same | 4 | helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/Ns6bQ4iusfwGDxTCX7eYR7cv4mtRYi8CCbTooqERgjyNQKtDTnx5JqjJCBtAsibMMTMceM6Hg6pzYUAdrBTE24N) [dump](https://solscan.io/tx/3BXNfh86Es7uBA7GPXMHKpbgufoRx2QqURneH8aNUBW5ZTtfvwpKGqPxLKuibKEEZNRztc8xgqxNBjmTkq4jgrh4) |
| 9 | 90 | +1 | 3 | helius+nozomi+staked-rpc | stop-loss 0.7 s | 1 | [buy](https://solscan.io/tx/4oh9ewN9yw292CyqSAkLXyHTdNZx7msRwKo7nrRQy8cjzkkA5LP48FxAQeKaAujhGkYRgG7358CdGTViScG5pAGf) [sell](https://solscan.io/tx/xAbp8RxXKwfSdEeNPeis5NoZ2HavTYYMDZJziYD5Azq8yo356dxFwKqarmHKuN7QgrZsiHJMoZCA4ee3GSqjWY5) [dump](https://solscan.io/tx/51ARShXir1dRPeaW4G9B2v6URMMibTGkvawehwZU5UaGVuTVgXifqgoYvD2WWrQj1rD64cSxfxJX26nH61TomGnu) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Jito | 4 | 1 | 25% | -0.0635 | -0.0620 | 0/1 |
| BAM | 2 | 0 | 0% | -0.0010 | – | 0/0 |
| Harmonic | 2 | 1 | 50% | +0.0231 | +0.0236 | 1/1 |
| Firedancer | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 5 | 2 | 40% | -0.0399 | -0.0192 | 1/2 |
| dev list | 4 | 0 | 0% | -0.0020 | – | 0/0 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 6 | 1 | 17% | +0.0211 | +0.0236 | 1/1 |
| next block | 3 | 1 | 33% | -0.0630 | -0.0620 | 0/1 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 17:00 | 9 | 2 | 22% | -0.0419 | -0.0192 | 1/2 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 1 | +0.0236 | +0.0236 | 1.6 s |
| stop-loss | 1 | -0.0620 | -0.0620 | 0.7 s |

## 8. P&L leaders
**Best trades:** EgLPei +0.0236 (Harmonic, time-limit, score 0.35); 6S3C8r -0.0620 (Jito, stop-loss, score 0.30)

**Worst trades:** 6S3C8r -0.0620 (Jito, stop-loss, score 0.30); EgLPei +0.0236 (Harmonic, time-limit, score 0.35)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `5ZqveVff` | HarmonicAgave | 1 | 1 | +0.0236 |
| `A9mvukTd` | JitoLabs | 1 | 0 | -0.0005 |
| `GEM1N1UE` | AgaveBam | 1 | 0 | -0.0005 |
| `Awes4Tr6` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `EvnRmnMr` | Firedancer | 1 | 0 | -0.0005 |
| `9jxgosAf` | FireBAM | 1 | 0 | -0.0005 |
| `HEL1USMZ` | JitoLabs | 3 | 1 | -0.0630 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1217 (p25 955, p75 1388, n 9) |
| Executed-feed lag behind first sighting, ms | 2.2 (p25 1.1, p75 3.3, n 9) |
| Buy sent → our tx seen on the feed, ms | 34.2 (p25 17.4, p75 87.9, n 9) |
| Fills: our buy seen on the feed after the dump, ms | 66 (p25 41, p75 90, n 2) |
| Guard fails: our failed buy seen after the dump, ms | 37 (p25 22, p75 37, n 7) |
| Fills in the dump's own block | 1 of 2 |
| Guard fails in the dump's own block | 5 of 7 |

**Send-path answers (FAST-ACK lines):** nozomi 9 (median ack 0.3 ms), staked-rpc 9 (median ack 4.8 ms), helius-swqos 5 (median ack 0.7 ms), helius 5 (median ack 0.6 ms, 1 errors, 1×429), bolt 3 (median ack 0.2 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 2 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 1.89 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| haqq (dip bot) | 6 | 6 |
| 9k78QZyw (fast bot) | 2 | 2 |
| 5CWWaCq3 | 2 | 2 |
| 3MHgGwdL | 2 | 2 |
| DYXD (dip bot) | 2 | 1 |
| 6n2cCJrr | 2 | 2 |
| 2KtcBC (pre-placed) | 1 | 1 |
| BPaF9JM5 | 1 | 1 |
| 9K5QgBKa* | 1 | 1 |
| 8g1w4PNC* | 1 | 1 |
| 7Segg5fr | 1 | 1 |
| 4DN7GT99 | 1 | 1 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | -0.0028 |
| Pump fee on buys | 0.0136 (0.0068 per fill) |
| Pump fee on sells (residual) | 0.0135 (0.0068 per fill) |
| Buy tx fees (base + priority) | 0.0010 (0.00051 per fill) |
| Buy tips | 0.0042 (0.0021 per fill) |
| Sell tx fees | 0.0012 (0.00060 per fill) |
| Sell tips | 0.0020 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0035 (7 buys) |
| **Result** | **-0.0419** |

Buy compute used (fills): median 79,819 CU, max 84,394 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 1 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ℹ️ RPC bh-fallback getLatestBlockhash: slow minutes (worst p99 749 ms, max 879 ms)
- ℹ️ RPC bh-fallback getSlot: slow minutes (worst p99 750 ms, max 879 ms)
- ⚠️ RPC bh-primary getLatestBlockhash: 8 timeouts/transport errors (worst p99 1001 ms)
- ℹ️ RPC exit-fallback getAccountInfo: slow minutes (worst p99 442 ms, max 442 ms)
- ℹ️ send path helius: 1 × HTTP 429 (rate limited) on buys
- ℹ️ 2 send-path health events (self-heal), e.g. `SEND-PATH rpc bh-primary UNHEALTHY: 3 timeouts / transport errors in a row (getLatestBlockhash): client REBUILT (fresh p`
- ⚠️ big loss 6S3C8r -0.0620 (stop-loss, Jito)

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED.

## 13. Fixes and follow-ups
**Done after this run:**

- Routes v8 (above) used from run 10.
- Owner A/B for run 10 (18:15): Frankfurt 4 s hold / SL −20%, Amsterdam 1.3 s / SL −10%.

**Recommended / open:**

- Run 10: exit A/B between the two servers.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r9.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r9.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

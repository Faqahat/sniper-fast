# Frankfurt run 1 — dip bot run report

*First live PROD run: 3 trades × 0.25 SOL, strict tier, routes v2*

> **Verdict:** Good start: 3 of 3 fills won (+0.1249 SOL) — but 8 of 11 buys were blocked by the +5% guard because we landed ~80–95 ms after the dump while the fast bots buy at 4–36 ms.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.1249 SOL** (wallet 3.9574 → 4.0823, Δ +0.1249) |
| Started (PKT) | 2026-10-24 02:15:57 |
| Ended (PKT) | 2026-10-24 02:43:19 — max fills reached (3 of 3) |
| Ran for | 0 h 27 min of 120 min planned |
| First / last buy (PKT) | 02:17:21 / 02:43:18 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 11 → **3 filled**, 8 failed on the +5% guard |
| Fill rate | 27% |
| Wins / losses (fills) | 3 / 0 (win rate 100%) |
| Per filled buy | avg +0.0430, median +0.0478 SOL |
| Fills only / failed buys only | +0.1290 / -0.0040 SOL |
| Best / worst trade | C3aA8C +0.0535 / AMKcxJ +0.0276 |
| Fill landing | median 113 ms after the dump (seen on our feed); 1 of 3 in the dump's own block |

Owner plan (10-23 23:40): prove the IMIT1 dip strategy live with 3 trades, then 5, 10, 12 … up to 100, on the 2g PROD wallet with 1.5 SOL usable and a 0.5 SOL loss cap. This run capped at 3 fills and stopped itself.

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip6 (sha c6f1b40f; holder-reward tokens allowed) |
| model / tier | IMIT1 strict (score >= 0.5419) |
| size (normal) | 0.25 SOL |
| dev list | off |
| exit | take-profit +5% / stop-loss −10% / time limit 6 slots (~1.3 s) |
| price guard | +5% over the post-dump price (pump error 6042 if exceeded); slot deadline = dump slot + 1 |
| buy fee (priority) | 5M µL/CU × 100k CU limit = 0.0005 SOL per landed buy tx |
| sell fee | 5M µL/CU × 120k CU limit (0.0006 SOL per landed sell tx) |
| route: agave leaders | helius + nozomi |
| route: bam leaders | helius + astralane |
| route: default leaders | helius + nozomi |
| route: fd leaders | nozomi + helius |
| route: harmonic leaders | nozomi + astralane |
| route: jito leaders | helius + nozomi |
| route: other leaders | helius + nozomi |
| sell path | staked-rpc (retry also via nozomi) |
| near-leader gate | off (every leader) |
| pre-send | off |
| durable-nonce fan-out | off (one tx to every path, every path's tip in it) |
| backup RPC | RMR_RPC_URL |
| holder-reward tokens | allowed |
| limits | max 3 fills, 1 open at a time, 120 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
- first run of this kind (nothing to compare)

- First PROD run. Before it, FRZ plumbing tests (dip3 → dip6) proved buy → exit → sell → ATA close and fixed: the missing signal handler, the tee/Ctrl-c panic, the RPC helper's token, holder-reward tokens (verified by a simulated round trip).
- Guard raised 2% → 5% (owner: strict slippage blocked every test; blocked buys were only +3..+24% above the post-dump price).
- Routes v2 from the landing probes A–C: BAM = helius + astralane, Jito = helius + nozomi, Harmonic = nozomi + astralane, FD = nozomi + helius, others = helius + nozomi (2 tips on a filled buy).

## 4. Timeline (PKT)
- **02:15** trade 1 trigger: an insider (first-trade wallet in the 462 cohort) sold 2.69 SOL, a third of its 5.9 SOL launch buy, 1.3 s after 7 buyers / 9.9 SOL
- **02:15:57** engine start #1 (session with 11 buys)
- **02:17:21** big win: C3aA8C +0.0535 SOL (take-profit)
- **02:43:19** engine end #1: run end

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 1881 |
| Inside the envelope (age / drop / since-buy / size) | 914 |
| Picks (score above the threshold) | 13 |
| Skipped | spacing 1, max_open 1 |
| Buys sent | 11 |
| Filled | 3 |
| Failed on the +5% guard | 8 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 3 of 3 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 02:17:21 | [C3aA8C](https://gmgn.ai/sol/token/C3aA8CpRYjyXJWLnRfiwTD3Hr6pXRhsPmGXSZvHBo8Rt) | 0.25 | 0.74 | 2.69 / −13% | 1.3 s | Jito `HEL1US` | filled | **+0.0535** |
| 2 | 02:19:20 | [3MBfSx](https://gmgn.ai/sol/token/3MBfSxsL3ppBNgReBHcybPexpABWUbuUoJrR4VhoNoVe) | 0.25 | 1.33 | 4.51 / −24% | 3.4 s | BAM `9jxgos` | guard fail | -0.0005 |
| 3 | 02:19:27 | [57bRk5](https://gmgn.ai/sol/token/57bRk56nfcrDVBmVNceWceDbumgnYfN3eYJ1482b2s3M) | 0.25 | 0.57 | 2.72 / −11% | 56.0 s | Firedancer `9eGrDo` | guard fail | -0.0005 |
| 4 | 02:30:28 | [Ey2xjW](https://gmgn.ai/sol/token/Ey2xjWkiTGUo2Dpb1kSXGmTyJsyf9evR4b2bcYrPVssj) | 0.25 | 0.94 | 2.76 / −9% | 1.9 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 5 | 02:30:48 | [2dY2zM](https://gmgn.ai/sol/token/2dY2zMRxzn7qemoCZiZfijYzr5WWnAVKAAQUyoYfpump) | 0.25 | 0.64 | 5.27 / −22% | 12.9 s | Jito `GnC339` | guard fail | -0.0005 |
| 6 | 02:30:59 | [7uzdsa](https://gmgn.ai/sol/token/7uzdsaySSzMuRV6CVWpLXdBDLKL7r7ybhGkkyW6jj7Ey) | 0.25 | 1.04 | 12.18 / −49% | 1.3 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 7 | 02:31:14 | [7kgMU6](https://gmgn.ai/sol/token/7kgMU6nWNV8t2gBQNd51rXJaoHrGQtYtyVaD6QG8XdBE) | 0.25 | 0.93 | 12.28 / −49% | 1.3 s | BAM `DRpbCB` | guard fail | -0.0005 |
| 8 | 02:31:21 | [DeRoNo](https://gmgn.ai/sol/token/DeRoNoMtihvjtf1xEsusWQewwEfmpS6ewFB8BVYwpump) | 0.25 | 0.71 | 5.38 / −22% | 10.6 s | Jito `8gDfqH` | guard fail | -0.0005 |
| 9 | 02:31:34 | [2dY2zM](https://gmgn.ai/sol/token/2dY2zMRxzn7qemoCZiZfijYzr5WWnAVKAAQUyoYfpump) | 0.25 | 0.81 | 5.56 / −14% | 58.1 s | Firedancer `JD549H` | guard fail | -0.0005 |
| 10 | 02:42:00 | [AMKcxJ](https://gmgn.ai/sol/token/AMKcxJyjW3uUXiZXnoWoyttFJe2fiCN6XRu5iTRV7K97) | 0.25 | 0.71 | 5.13 / −27% | 1.1 s | Harmonic `Awes4T` | filled | **+0.0276** |
| 11 | 02:43:18 | [CiYHxY](https://gmgn.ai/sol/token/CiYHxY9jv5JsNP8eU68kE4WxSfyFRL3S292YN9A9wkZs) | 0.25 | 0.83 | 9.31 / −40% | 2.3 s | BAM `5Cchr1` | filled | **+0.0478** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 60 | same | 0 | helius+nozomi | take-profit 0.6 s | 1 | [buy](https://solscan.io/tx/5L2bJeE6vLtEFkAhqqT2s8GPPUAnsc6GcfrpASAmFbZrbf4WwnS3GHP4PhTE3BPzAT2oVLrZkLgLiZkC8jbmgQju) [sell](https://solscan.io/tx/44kpKJN24DQnxtCoxMTeEuJmV6yrmrgTB6ntWGR6gZGDBjKuXEDXAukfpqzzmWHHVpxudbhF5D4Zg1GVrFox7r9p) [dump](https://solscan.io/tx/4Vrc4dRNqFdGUqrsYQuQHDXbZ1Hrtat4QtmL12Zsj49GXehsG16UC9zJGRENTjqHwtVwTCEA5Um6Nyb82NA7DCSo) |
| 2 | 50 | same | 5 | helius+astralane | – | – | [buy](https://solscan.io/tx/3ra9yo3GMXGUR7YQrZRGZ6jPb9eTExNU4zoZSuwN6TrBwhfG2t1PGB7TuwupyXvHmy2W9c264JuLRAxqKgmLmYwZ) [dump](https://solscan.io/tx/495haE4GQjN5WbEdm79gdFrJSaHGQH5vYVDEt7ZvidbuCqd5S6rVtUCdFYXHXKTTz41PT8bCz9FheYPtfBvzonZN) |
| 3 | 79 | +1 | 5 | nozomi+helius | – | – | [buy](https://solscan.io/tx/5Z7A5Fc4aWEuA9w9tJPrZKPzY4okU9P4kJBWcfPK1CYSEJUwyQXmT5LiXpN81wXwRY1obyG8eyjVhgx9bpZKXvTg) [dump](https://solscan.io/tx/vWtaczGrrQ6bJok3CZaVvQUviNj6LN6F3FXJGLKGqJpCyMieUgRoBGFCTpCFrmHc51n44ddPCpXW7PQqPM8crQ7) |
| 4 | 32 | same | 3 | nozomi+astralane | – | – | [buy](https://solscan.io/tx/2GWsUZUP5gRgnT2VTySAvcfZRaQuoKcWLEXN4cmN1BbYgMfnwnUw4Ug6CXKYzYggAZFZbgaMZ7ThED7Q3zS4uoBW) [dump](https://solscan.io/tx/2Qp9HLm5MtWk2TfDPWjQgvCacWzt2BkPLFsfNw7TR4r1XEjbbBeXK2pFjqmwmAwMSoV9XjrXwf7QD1FHAxLvXyv9) |
| 5 | 122 | same | 4 | helius+nozomi | – | – | [buy](https://solscan.io/tx/3imita63TeoyGNeBFjMGTwknCtkWwj8sbWfBL8eSgGGaHckNmU8v3MC1pduqFkyiYHYQNT7QYDuXC1WqxnwDRJjc) [dump](https://solscan.io/tx/JXoroYfMWiZAiYXX8yoiRf6P9cZAt9ZmSPyvJ8Hfxf2ZwYgXgrUBgvxq2Ay2ocZeaf3K7y69JJh47G2SR7NXAaG) |
| 6 | 123 | +1 | 5 | helius+nozomi | – | – | [buy](https://solscan.io/tx/L66CXNF6baY8L4XKXdA6aeYDKkm4PfeCcJGfWoQsPNGgGir8ARKEbCdErkDU6k4mqT6Th72cP8onj9NgYLGVme4) [dump](https://solscan.io/tx/GCDb2DYj23EycxFYxfgtA9TrQKCoKFEQCBQZUUkHVpAePzgpsK9SPsayMa3nKs9iA9YaGBbdJfB4f1h97M9JY3N) |
| 7 | 102 | +1 | 6 | helius+astralane | – | – | [buy](https://solscan.io/tx/3gHx4c7NHGWMcsKGhMkWdPgVoKfcxbUpD27UP236YkZs3HRBuZQVQHu8PeH1AGgVg7PskWL5khxywucfu1zCempL) [dump](https://solscan.io/tx/3enQCvdc6ZLdoWe9LqVV41X81sFC2aDNLg9rTjVLJMKRAGUnKEj1Zw9BxssWw6tURiqTq41UA6ebsiYSUkTJheXx) |
| 8 | 22 | same | 5 | helius+nozomi+astralane | – | – | [buy](https://solscan.io/tx/P1a2Y8WyrzN7M5pkTS9nNBWGEVnmtGwcfj7w1vQxUGLwftXDJVSTdshoozQfDhtsJPgpoyHwrwKwdJgN3FbtZtc) [dump](https://solscan.io/tx/5Q44zbEKRJJcNAQuFmGD9s2fKufu3zmBZAsGe6faMfDTRHyHXJsL1t5a5bS8rAXBiWd22PqDJqcVwZ4cNtSZjvhJ) |
| 9 | 289 | +1 | 5 | nozomi+helius | – | – | [buy](https://solscan.io/tx/66YnLbDbgzW15k8teLQaYgs9mBEA1LXK1joCsBJs4fRehjGCE1nPALKKJYk7ZbfYLFuYNYnPKV2bDz9EzUHTx6yp) [dump](https://solscan.io/tx/59B1mfJ6zKWDyT7g88Q7jLmyCnBVphbnjE16QSdrgB518TuUpZMhbNjTpus2G7Wuu89AMiKbMkXssutXvbHbSGpx) |
| 10 | 189 | +1 | 1 | nozomi+astralane | take-profit 1.1 s | 1 | [buy](https://solscan.io/tx/5RMgmzLDTTD7FaZugQx57RCPedC4jbCptaLk8Ws25tVRkJHBcB4cmwGNkJzzKJgdmJPpLrpVUMj34o5SLtkcy3pH) [sell](https://solscan.io/tx/JEEADqtDzHW3CQfM6jj7xmTsHtAcaoX47Pgg8vxKRzQWFBkyjT4yoKjfhECxoBZ2Vj9KMB5ahmDwyQTt5Cu5Pxz) [dump](https://solscan.io/tx/5y1jv6UsxyBpwHNxAFwgGMPqz13gHCHbcAUmBt16nfkVkDQzHJ5ML5hC8NDRMxjHNEQpeXfpDgJ5xkmyMjQc8uVt) |
| 11 | 113 | +1 | 2 | helius+astralane | take-profit 0.9 s | 1 | [buy](https://solscan.io/tx/JreSc9dzNPKaVXodpuhx6xmP27j79kLWBq52ZVUnz5WF7Nsc5XGmRC78iUXMFobzujnrCukkYBkQNNKNfrugHfz) [sell](https://solscan.io/tx/5smtzZe8u2JPvobMSsFaNQqPLjKUfXpzL9YxWeES64usU1dSNUGPaz26AMXJchqfY3RXVJHD3dBCJwR7jo8uWy38) [dump](https://solscan.io/tx/XZGCmHMt1C4i5Zxo5aeEtwrigFheiJ2hmSKez2fsNdxicz73QD8cC8gvUccRmSPxwUY1zKYnAJGzqgHRWSSrFJY) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Jito | 4 | 1 | 25% | +0.0520 | +0.0535 | 1/1 |
| BAM | 3 | 1 | 33% | +0.0468 | +0.0478 | 1/1 |
| Firedancer | 2 | 0 | 0% | -0.0010 | – | 0/0 |
| Harmonic | 2 | 1 | 50% | +0.0271 | +0.0276 | 1/1 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 11 | 3 | 27% | +0.1249 | +0.0430 | 3/3 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| next block | 6 | 2 | 33% | +0.0734 | +0.0377 | 2/2 |
| same block | 5 | 1 | 20% | +0.0515 | +0.0535 | 1/1 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 02:00 | 11 | 3 | 27% | +0.1249 | +0.0430 | 3/3 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| take-profit | 3 | +0.1290 | +0.0430 | 0.9 s |

## 8. P&L leaders
**Best trades:** C3aA8C +0.0535 (Jito, take-profit, score 0.74); CiYHxY +0.0478 (BAM, take-profit, score 0.83); AMKcxJ +0.0276 (Harmonic, take-profit, score 0.71)

**Worst trades:** AMKcxJ +0.0276 (Harmonic, take-profit, score 0.71); CiYHxY +0.0478 (BAM, take-profit, score 0.83); C3aA8C +0.0535 (Jito, take-profit, score 0.74)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `HEL1USMZ` | JitoLabs | 1 | 1 | +0.0535 |
| `5Cchr1XG` | AgaveBam | 1 | 1 | +0.0478 |
| `Awes4Tr6` | HarmonicFiredancer | 1 | 1 | +0.0276 |
| `9jxgosAf` | FireBAM | 1 | 0 | -0.0005 |
| `9eGrDohd` | Firedancer | 1 | 0 | -0.0005 |
| `JUPiTERr` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `GnC339vk` | JitoLabs | 1 | 0 | -0.0005 |
| `C8Bey3LK` | JitoLabs | 1 | 0 | -0.0005 |
| `DRpbCBMx` | AgaveBam | 1 | 0 | -0.0005 |
| `JD549Hsb` | Firedancer | 1 | 0 | -0.0005 |
| `8gDfqHXZ` | JitoLabs | 1 | 0 | -0.0005 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1018 (p25 810, p75 1475, n 11) |
| Executed-feed lag behind first sighting, ms | – (p25 –, p75 –, n 0) |
| Buy sent → our tx seen on the feed, ms | – (p25 –, p75 –, n 0) |
| Fills: our buy seen on the feed after the dump, ms | 113 (p25 60, p75 189, n 3) |
| Guard fails: our failed buy seen after the dump, ms | 91 (p25 50, p75 122, n 8) |
| Fills in the dump's own block | 1 of 3 |
| Guard fails in the dump's own block | 4 of 8 |

**Send-path answers (FAST-ACK lines):** helius 9 (median ack 0.6 ms), nozomi 8 (median ack 0.4 ms), astralane 6 (median ack 0.7 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 5 |
| Guard fails: rival SOL ahead (median) | 2.78 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| CVPz447t (pre-placed) | 4 | 3 |
| 2KtcBC (pre-placed) | 3 | 1 |
| 7PedQZmc (untipped fast) | 3 | 3 |
| HkQ7 (dip bot) | 3 | 3 |
| EprLoV21* | 2 | 2 |
| 9k78QZyw (fast bot) | 2 | 2 |
| 7GVDpszM* | 2 | 2 |
| GonzYBmk | 2 | 2 |
| 3mK48y1P | 2 | 2 |
| 3MHgGwdL | 2 | 2 |
| AEgTuy8L* | 1 | 1 |
| 5TFXfcHb* | 1 | 1 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.1618 |
| Pump fee on buys | 0.0093 (0.0031 per fill) |
| Pump fee on sells (residual) | 0.0113 (0.0038 per fill) |
| Buy tx fees (base + priority) | 0.0015 (0.00051 per fill) |
| Buy tips | 0.0060 (0.0020 per fill) |
| Sell tx fees | 0.0018 (0.00060 per fill) |
| Sell tips | 0.0030 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0040 (8 buys) |
| **Result** | **+0.1249** |

Buy compute used (fills): median 73,753 CU, max 76,755 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 2 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ℹ️ RPC bh-fallback getLatestBlockhash: slow minutes (worst p99 555 ms, max 638 ms)
- ℹ️ RPC bh-fallback getSlot: slow minutes (worst p99 556 ms, max 639 ms)
- ⚠️ RPC bh-primary getLatestBlockhash: 2 timeouts/transport errors (worst p99 209 ms)
- ⚠️ 73% of buys blocked by the guard: we executed ~80–95 ms after the dump; 6 bots typically got in first (CVPz447t 5.7 ms, 3Xti8uhq 13 ms, 9k78QZyw 14 ms, haqqiUUX 36 ms…)

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED.

## 13. Fixes and follow-ups
**Done after this run:**

- Guard what-if on 15 real blocked buys (re-bought at our exact block position): 5% −0.009, 10% −0.057, 15% −0.063 SOL → keep +5%.
- Leader distance study: leaders < 50 ms away land ~75% in the dump's block; US leaders ~10% → later the near-leader gate.
- Engine dip8: timing records (first sighting, feed lag, reaction, fire → our tx seen), near-leader gate flag, forced-path probes.
- Probe D (70 fail-by-design buys on nearby leaders): nozomi 30 ms, landx 31, bolt 35, helius 35, astralane 46, haan 49, tpu-direct 50 → routes v3.

**Recommended / open:**

- Run 2: 5 trades (owner plan).

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r1.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r1.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

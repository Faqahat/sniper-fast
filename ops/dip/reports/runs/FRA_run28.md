# Frankfurt run 28 — dip bot run report

*Pre-send only with the 200 ms sell (dip22 --presend-live-exit-ms 200): 0.45, k8, QUIET*

> **Verdict:** +0.516 SOL on chain (4.782204 -> 5.298393) in ~5.5 h (14:31 -> 20:02 PKT, stopped by the owner to move to AMS with the 40/s cap). 78 pre-send fills, realized +0.573, failed-try fees -0.057. The 200 ms sell beat the old exit (2 slots / TP 10% / SL 20%) by ~+0.17 SOL on the same fills (~15%; checker ops/dip/exit200/check.py, P(old better) ~0.06). Dipped to -0.15 after two rugs (AaXkyT -0.315, HRzj4J -0.216) around 18:00, then recovered.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.5163 SOL** (wallet 4.7822 → 5.2984, Δ +0.5162) |
| Started (PKT) | 2026-10-28 14:31:45 |
| Ended (PKT) | 2026-10-28 20:02:35 — stopped with Ctrl+C (SIGINT) |
| Ran for | 5 h 30 min of 720 min planned |
| First / last buy (PKT) | no buys |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 0 → **0 filled**, 0 failed on the +5% guard |
| Fill rate | – |
| Wins / losses (fills) | 0 / 0 |
| Per filled buy | – |
| Fills only / failed buys only | +0.0000 / +0.0000 SOL |
| Reactive bot / pre-send live | +0.0000 / +0.5163 SOL (pre-send: 78 fills, realized +0.4555, rent back +0.1177, failed-attempt fees -0.0568, 43 wins; see section 4b) |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip22 |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.45 SOL |
| dev list | off |
| exit | take-profit off / stop-loss −50% / time limit 5 slots (~1.1 s) |
| price guard | +5% over the post-dump price (pump error 6042 if exceeded); slot deadline = dump slot + 1 |
| buy fee (priority) | 5M µL/CU × 100k CU limit = 0.0005 SOL per landed buy tx |
| sell fee | 5M µL/CU × 120k CU limit (0.0006 SOL per landed sell tx) |
| route: agave leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: bam leaders | nozomi + helius-swqos + bolt + falcon + falcon-udp + soyas + solami + 0slot |
| route: default leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: fd leaders | 0slot + nozomi + landx-fra3 + staked-rpc + soyas + solami |
| route: harmonic leaders | nozomi + landx-fra3 + falcon + falcon-udp + glaive + soyas + solami + 0slot |
| route: jito leaders | solami + soyas + glaive + falcon + falcon-udp + helius-swqos + 0slot |
| route: other leaders | nozomi + helius-swqos + bolt + staked-rpc |
| sell path | staked-rpc (retry also via nozomi) |
| near-leader gate | 198 leaders (buys only when the dump's leader is on the near list) |
| pre-send | LIVE: whale >= 6%, 8 tries/slot, 0.450 SOL, limit x0.88, route helius-ps, caps 1000 fills / 0.5000 SOL failed-try fees, exit 2 slots or 200 ms after the fill (dip22, first) / TP +10% / SL -20% |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 1500 fills, 1 open at a time, 720 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 26**:

| Setting | FRA run 26 | FRA run 28 |
|---|---|---|
| engine build | dip21 (QUIET + host whale book + journal) | dip22 |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.45 SOL | off |
| pre-send | LIVE: whale >= 6%, 8 tries/slot, 0.450 SOL, limit x0.88, route helius-ps, caps 1000 fills / 0.5000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% | LIVE: whale >= 6%, 8 tries/slot, 0.450 SOL, limit x0.88, route helius-ps, caps 1000 fills / 0.5000 SOL failed-try fees, exit 2 slots or 200 ms after the fill (dip22, first) / TP +10% / SL -20% |

- Engine dip22: sell 200 ms after the fill is seen (time-ms), the slot limit and wall backstop stay (owner OK 10-28).

## 4. Timeline (PKT)
- **14:31:17** start refused: `Error: keystore: wrong passphrase or damaged file` (nothing sent)
- **14:31:45** engine start #1 (session with 0 buys)
- **17:30** owner check at ~30 trades: 200 ms vs old level (within 5%) -> keep running
- **~18:00** two rugs (AaXkyT, HRzj4J): ~70 wallets dumped in one slot after our fill; the old exit would have lost the same
- **20:02** stopped by the owner (kill -INT); clean end, 0 held
- **20:02:35** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 4b. Pre-send live (pre-placed buys) — separate from the reactive bot
Buys pre-sent after a big whale buy, before any dump. **Not included in sections 5–11**, which cover only the reactive dip bot. Realized = the engine's PRESEND LIVE REALIZED records (chain txs of each buy and sell; the buy pays the token-account rent). Rent back = that rent returned when the engine closed each pre-send account after the exit (dip19+; before dip19 the sell closed it and the refund sat inside realized). Failed tries = fees of tries that landed and failed (6042 price, deadline, …). Net = realized + rent back − failed tries.

| Session | Started | Size / fill cap / fee cap | Tries sent | Fills | Wins | Realized | Rent back | Failed tries | Net | Stopped |
|---|---|---|---|---|---|---|---|---|---|---|
| #1 | 10-28 14:31 | 0.45 / 1000 / 0.50 | 11,336 | 78 | 43 | +0.4555 | +0.1177 | -0.0568 | **+0.5163** | run_stopping |

**Try results (as seen on our feed):** 6042 9,983, deadline 857, ata_exists 259, unseen 138, ok 78.

Tries never seen on our feed: 138. If they landed and failed they cost up to 0.0007 SOL in fees that are **not** in the failed-try total above (5,120 lamports each; inferred, the engine does not see them).

**By exit reason:**

| Exit | Fills | Wins | Realized SOL | Per fill | Median hold |
|---|---|---|---|---|---|
| time-ms | 63 | 29 | -0.3785 | -0.0060 | 0.8 s |
| take-profit | 14 | 14 | +0.9762 | +0.0697 | 0.7 s |
| stop-loss | 1 | 0 | -0.1422 | -0.1422 | 0.7 s |

**By leader type (the slot leader where the fill landed):**

| Leader type | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| Harmonic | 29 | 15 | +0.5086 | +0.0175 |
| BAM | 25 | 15 | +0.1875 | +0.0075 |
| Firedancer | 15 | 7 | -0.4572 | -0.0305 |
| Jito | 7 | 5 | +0.2173 | +0.0310 |
| Rakurai | 1 | 1 | +0.0051 | +0.0051 |
| Raiku | 1 | 0 | -0.0059 | -0.0059 |

**By hour (PKT):**

| Hour | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| 10-28 14:00 | 9 | 7 | +0.3252 | +0.0361 |
| 10-28 15:00 | 13 | 5 | -0.0181 | -0.0014 |
| 10-28 16:00 | 4 | 1 | -0.0100 | -0.0025 |
| 10-28 17:00 | 12 | 6 | -0.1905 | -0.0159 |
| 10-28 18:00 | 15 | 10 | +0.0672 | +0.0045 |
| 10-28 19:00 | 25 | 14 | +0.2816 | +0.0113 |

**Best pre-send fills:** Aqb6b9p6 +0.1304 (BAM, time-ms); 2t7ZQLKR +0.1196 (Harmonic, take-profit); BV5X1mUy +0.1135 (Firedancer, time-ms)

**Worst pre-send fills:** AaXkyTAB -0.3152 (Firedancer, time-ms); HRzj4J2Q -0.2157 (Firedancer, time-ms); AiCdMSJX -0.1422 (BAM, stop-loss)

**End-of-run checks:**

- session #1: END CHECK 84 mint(s) read at confirmed: 0 sold now, 0 empty account(s) closed, 0 held / 0 unreadable (per mint: none 84)

**Every pre-send fill** (time = fill; whale = the trigger buy; P&L = realized, rent back not included):

| # | Time | Token | Whale % / SOL | Slots after whale | Leader | Exit | P&L SOL | Links |
|---|---|---|---|---|---|---|---|---|
| 1 | 14:31:58 | [9XANtG](https://gmgn.ai/sol/token/9XANtGjiGENF5vfwzVSfustx1opd6he8td5jR4bPYB2v) | 7.4% / 2.96 | +1 | Harmonic `Awes4T` | time-ms 0.7 s | **-0.0554** | [buy](https://solscan.io/tx/327otzJoVMMNtEgtszyPTu2FP8pU2ssMvyTqMQvHKzf4NMNgNbKs6fgES5a1ndwQkNWRpopDtcRTUhGozFNw68ff) [sell](https://solscan.io/tx/5ZiDGimtKAKgGVrcP7tPRwfrsuouf2jao26mTeq5EExadJQWfCy1GXq9TryP68PjEUJtB2shamEEdn2suZpHvAKF) [whale](https://solscan.io/tx/3RP6YayHDHivDD91tAFwp9TgWGVjp3XWcGibiw4gL7cJvc6YApTL3qMtd2pJmhaSMG6xr8Dka9dh5mgk1quCHuA4) |
| 2 | 14:37:23 | [5DPeta](https://gmgn.ai/sol/token/5DPetaiLiMmjwhAWKyvPbxnYSWLBpC8CvY2E4gX8odvT) | 7.3% / 3.95 | +1 | Jito `5FbKKG` | take-profit 0.9 s | **+0.0701** | [buy](https://solscan.io/tx/2yPs5aBDAaVrfEbv8qfp4LBSCKaxRv5gJvuhu6pCLyVqhEbS1dKr7EtMqNasNBKy92msaP1WqebLQ7Y5tsMcF6io) [sell](https://solscan.io/tx/5s7Kh1FSfwcA38UixaHEjrg7922n8tQUwzQV2iiNP1pnbxtU37x8FwFFQRzqr1w4LArSTuAZdt3ArE3CXUj2KWEY) [whale](https://solscan.io/tx/1EU46s3QiQ7MEGCpg1XAKRxnwF4ES3WfmVzLUZEpBGKECJVJtTGhf56XuzzZyAL7rbekYQ932N84RSWUYZpiJmG) |
| 3 | 14:44:04 | [2t7ZQL](https://gmgn.ai/sol/token/2t7ZQLKRMXKJcJUGNsAzEJss2vJnTk6wL2seGNDiVq6g) | 11.1% / 5.93 | +2 | Harmonic `2DTXh3` | take-profit 0.6 s | **+0.1196** | [buy](https://solscan.io/tx/36Tsy9Wq3i3Jz1iYJDdrv565Aqc5xLF5CR6JqnR9gaAtvxEou6GgV9F1H393ABS3fDgEo4JQFCDUHzHxDXr3WXPK) [sell](https://solscan.io/tx/34Q6K1cfbP2hpEXhZvJEZ8QcZzUW7KoQfwma5aApsJVJr1QLndwxe3rAwVEz3GaUN8a3M6yjixkmAUzZ2QA6fCQh) [whale](https://solscan.io/tx/3PAfPhEjv2TXyvrRriZQUbM6KJVwcn9RajYL4bH4kDKnsLQatUjRj26c5RZD9c4ogdpgnd5gPbmqjdojSHT5XysW) |
| 4 | 14:45:03 | [GcXkjA](https://gmgn.ai/sol/token/GcXkjAkkeU6TmKH1VJbi9ygzU17SXfnfHnMQSDFtRrAf) | 6.6% / 2.96 | +1 | BAM `6y7V8d` | time-ms 0.9 s | **+0.0223** | [buy](https://solscan.io/tx/4VbN1kgQ6ZRAjMuPqw45K5xThB6u5CVkZmt6oWMNN5ooMnPvK9xTD3dstawBvPYMBB9khWmNvBdorDgS3kP6PtCU) [sell](https://solscan.io/tx/2qGQy8oWH9foTLZcW8QywkjMvmmTHWNPZeWa7yJdhiyWTKsaX1BjaYwMP7SxLMvYC8QyoQkWyQ5jMFc6pA1uu1kb) [whale](https://solscan.io/tx/2UTRecAJDkC85RG4fFXTpRr7JJfFExQ9ekXRWuh4dxmEtVEAZKSKV698MV96SdvBXJsZY39nU1ee8HyfCySCginh) |
| 5 | 14:48:56 | [4DccPk](https://gmgn.ai/sol/token/4DccPk6XtaYwHcAkfPNnE1XjQ6mcRPNvswGWurte9j7y) | 6.3% / 3.91 | +7 | Harmonic `3psxMy` | take-profit 0.8 s | **+0.0925** | [buy](https://solscan.io/tx/4SZknQE6VqoHSmcaR25HCXtYnSbUar1pf7Yni6EQXZGEXbXHgJkW5HNtr1izSg8xoCqdkKYHCJ5zXME1DzkCcTh6) [sell](https://solscan.io/tx/5YTFRTLqgPDcfph63P8N9BgM1kH17ttQWHfvJk5LpjfwReo8PhhpijyJws1PLHe5vnzpftvbBEkR6dgxu9N7JJRL) [whale](https://solscan.io/tx/eCiukNmgG2odD2E2ARuuiYndqgVf433BjCQCHPizY9xm6fhzNzgLmcREhWhRu6jpz2tQeMdwi4eT67nm7UitPEV) |
| 6 | 14:52:23 | [BXm1ok](https://gmgn.ai/sol/token/BXm1okGJomrww6ebHeDgJxaxpfaz12TnYu1L4kqspump) | 6.9% / 5.93 | +1 | Harmonic `CAo1dC` | time-ms 0.7 s | **+0.0414** | [buy](https://solscan.io/tx/5EMYYjE1cz9qA37XwNHHTeoSEQswJx9E1Rphzq5rCfrNTUZofijxHEssD9wqQuixWq2GYdsBRbhKJdBcBVyVJ8ad) [sell](https://solscan.io/tx/2xDhDAj16dLi46uj7hKD7fSzfub7h4AiqiPwHVcgXyA168Ea2xX3Vp1wfJLk2EN8qZqsuFURfPVYHWvN5epAnAGj) [whale](https://solscan.io/tx/63tVQFUDLr3pYzff22Lktc7zhcF8Zajyeum6YTQroX55JUcsHVGuJMDnPU3hjpg8WM1RMxLr9suKfEzQxXyyxcTg) |
| 7 | 14:54:44 | [241Wxq](https://gmgn.ai/sol/token/241WxqTr6J67q7YP3xsJ3vNmrSm8YeAfGJjTdJpRBauN) | 12.6% / 6.78 | +2 | Firedancer `BbCQMW` | time-ms 0.7 s | **+0.0178** | [buy](https://solscan.io/tx/3jvLKhNfHjv94u9RzdWURAasawDB4FeAuniXgtbrxZ1YcGg8rstQU4vWUgbvfe9SgHoJkXdMwLvSWi9D877ACCsW) [sell](https://solscan.io/tx/xNtcWMuJtCqwm29LkvXtMgecp4pPC8sk2uVsavcUqjCrAqypsYhRqkJTad8qcc6o1zQ98DthMyAZMkxbhLv8ahD) [whale](https://solscan.io/tx/5QNs4WwRDu91CJc7uSzowRwSuYo6SuSnaUVu9qo4ubugi8mUuPWoVV5jpWi1KZVxQuo6EAtP8DKxwdrUWATdVfzi) |
| 8 | 14:57:39 | [HdUdjh](https://gmgn.ai/sol/token/HdUdjhVvz8s5qJwyhWyCdUoxSWGbfVo3ysJV5PTCpump) | 7.8% / 3.35 | +1 | Firedancer `HW4zor` | time-ms 1.1 s | **-0.0235** | [buy](https://solscan.io/tx/43pz4NEXjxK39YHiAuJaFumev9o1XNQ75BdTWFhznm53VXRSt1J5wvJY1o7qhc8F68NCgSNnYEq9x4TW1WZuQyqm) [sell](https://solscan.io/tx/5vTEt8itLxPstFfnd1wrkCmUotCs1j6eQ9JzBSK3yUcHkx8eRK8HQRm3yv4XS16cRa4LzSd5xB3nuGFNBfzgta4v) [whale](https://solscan.io/tx/3ueg319FF2zyqUiPr8Q9bdjwbN2NUvz6pCjxAspct3K4eU1cHJ14u389f7fYBdsdWiRUCvrV3jcyFCBnamsYfY9x) |
| 9 | 14:59:17 | [EereLU](https://gmgn.ai/sol/token/EereLUERkGuLgtMRLFrJZc4ci3Fv25TXxr7vV6appump) | 6.3% / 3.36 | +6 | Harmonic `BEsnod` | time-ms 1.0 s | **+0.0403** | [buy](https://solscan.io/tx/2uCCVCWxM4WeY2dNxfsyLX2HBSZ4tjPnybHCgQDPv1NaWwUtRQ2uz8uTbaNvQq94AQYWAQpTDz2q99PkWup6CfkG) [sell](https://solscan.io/tx/smLKcpZGng6KeLuZTv44ue2RUyt4Nhy3YcBpHrwno9EjPBoA5qDWYfFjXu3EfVLCswM4L9ruwYHwhJDFXogFXqG) [whale](https://solscan.io/tx/24q81TBLpZW6oDXerDJA6bvmZqnsQpjbQGqMJw6BbFFJCXckbtXPyTck7bmv5Nh8ATqxJLgm3J5ANumTh9ssk8Xc) |
| 10 | 15:03:21 | [Rm8xx8](https://gmgn.ai/sol/token/Rm8xx8HesYGvDb7pvSSLKUvadcY9Ti3wvoAMu1fpump) | 7.8% / 6.78 | +2 | Firedancer `BbCQMW` | time-ms 0.9 s | **+0.0282** | [buy](https://solscan.io/tx/571F4yAS6tVBprFzYa7hqLN1BuHU2ds5k1y1JFCDSk2EQhoutGn8yMbML9ZigAQ4da96phzWyh8fbJAEputyQS1D) [sell](https://solscan.io/tx/2xaQFEwG9S9RrAYtd9XuGyW6i9V6jJFx3rZwuc9LwSUAfBu5XVsHc1VjtabSL4HjttzYpNu4bFeU75cp423zFM7Z) [whale](https://solscan.io/tx/3sc72tNixTNk6rL8A69JWeGnnJzzBSMuEfh32VnXKBRWuoXnyqAXG1rUVSN9UY5TxUJ3px4Z9NCRYfM9ZNgNRNG1) |
| 11 | 15:13:44 | [HZccH9](https://gmgn.ai/sol/token/HZccH9aPk9PpxNRZwgESbYE3BMb3zcrjtunJkdAwpump) | 8.9% / 4.05 | +2 | BAM `7qGNnX` | time-ms 0.8 s | **-0.0100** | [buy](https://solscan.io/tx/4BX25cZAWbQzvvMrHBJ8jJP77FAxrScjJNQgPxuEP2hi4qEDQgpPgrk1GZx4uQ863B3xgRJdB3ufA3SUHnuib2Z4) [sell](https://solscan.io/tx/2aF4PZJGjFypxseFx5x1JerZXgbpiptVqtVr4gfdeAqj2JZ2En3W1xKq8mccm9bM7v4VhQJM8c8vboup7hMW5k5Y) [whale](https://solscan.io/tx/3TXfwrhYeaTLAVtzTEgKM1UtHt9acoDdrLNDwxKnwtSXCabrBW4KnTbaQ4Gh8sP4SqQD6yNraKL7zGrS7fqYdRaa) |
| 12 | 15:17:04 | [4exjGH](https://gmgn.ai/sol/token/4exjGHRiBqNqJHw6qreErsx8ewDz7vkzxsLL2fbLpump) | 11.8% / 5.77 | +1 | Firedancer `BbCQMW` | time-ms 0.9 s | **+0.0371** | [buy](https://solscan.io/tx/5igBJS11cizjX6VttEGpXrenbPKhZgttmsY1WU5F7PniwDHQi57umUCYYvuhkxwyHjTP7gS2b96MMmF715n7Mk2i) [sell](https://solscan.io/tx/5KtDPTBdvfRnh9NSHeDQbxqoSiWEQzT2KRA8XioucNnapXJ3DXGhba117ePib4toD3UKrZfaET99T7Zde54xyWLT) [whale](https://solscan.io/tx/5EuhiJB9cEYFY6kcgJmKf82HQKz1zaJnPhyuUfk97BKDu4qM7AMVhMnDwoCZn9h3G2JjgDJiuQHfWFDq5eBjgGfS) |
| 13 | 15:30:17 | [6okHSJ](https://gmgn.ai/sol/token/6okHSJQ28528xjiovGbRTpVE9tJ5fxr7ZpJyAZtr6XP1) | 6.1% / 2.96 | +1 | Harmonic `Fd7btg` | time-ms 0.8 s | **-0.0170** | [buy](https://solscan.io/tx/22JdLFDU6otP7oZLwZvcubHyTtrqJwKJBktiRufXCSKuWKBHDwhS613eXU2TMBb7H2ZqSFSo6yUSTTME5bGkqoaA) [sell](https://solscan.io/tx/4Qfqt87R9vt7dPcQSJRAE2m1VZ341TkFJW1uiba8a7WM1FYGzwU2CMUkXDWAnzkkEHnnqJGUqj8QSyEC1cpp6QXg) [whale](https://solscan.io/tx/2sEsaFku5ujoVHdP2GFDoEt6K41bvm4M7HgyJpLnuc5gJ3q9zeUcrNRUxHphp9wmsN1PMwG2Z9vdhy5RTbCYGBm6) |
| 14 | 15:30:24 | [MzVFyy](https://gmgn.ai/sol/token/MzVFyyn8PnJ5YyuXPUEM613GyoKFRze2LWzfe6Dpump) | 6.5% / 2.00 | +2 | BAM `AoB1wT` | time-ms 1.0 s | **+0.0118** | [buy](https://solscan.io/tx/2PNaLM6caVkEZtsF5diMYhvp1mxCa213XtCnNexTahJswbrqRP5qU4YBE6cHcGyCMGi2iveh6P7X6wGic63rLmuC) [sell](https://solscan.io/tx/3GpXjz9cZb28BbHVQaCvbW5yDCWUP5bw2uxiK76FujqpjYwjReWXRgBMRWBiJd4yaXPqJgDDszdqMYPPwvqYsdJW) [whale](https://solscan.io/tx/27SMXSZ9Koz7sxvE9PrJ5sHT4YbxxWG6LCSR5EG3TcFPMMEmqndkMmdVahm5JAoVf6c1ZHzBKbVufLBGUXoXVeDV) |
| 15 | 15:30:57 | [Dc2tj5](https://gmgn.ai/sol/token/Dc2tj5PT4EJMh6YbwfPRF3cLRiskn89DdrtyH6ohpump) | 6.0% / 1.98 | +1 | Harmonic `shftkx` | time-ms 1.2 s | **-0.0120** | [buy](https://solscan.io/tx/3Ec1of4APKSLp9EPgLU1P4tajuMKbyvRaynRuQhcEQFxuEX8UX6HP4to91BcZZ8YjZmnVZVph1B2WqbGyztMkS7M) [sell](https://solscan.io/tx/5W1R8ht3BNazwasDRzdyCYMoNHCSRCC4M917fLcHNzLUzEmwX9D6z8TEfwwv4FLHN3kuj6tZoHBEPBJWfsmLgyq4) [whale](https://solscan.io/tx/4T8tYvxg4vYdmA9GXdyv1WHJ2cCsCTJFpGURmhDeNLwTgUz9jJP1qa8ofzFMSC68PECTQT18VsQ3C4PNt1nQ1M68) |
| 16 | 15:31:17 | [eKEbWw](https://gmgn.ai/sol/token/eKEbWwdFTVdE8RsyFveYKHCeXniMbEAHjkLGmfxpump) | 17.2% / 6.78 | +1 | Firedancer `BbCQMW` | time-ms 1.0 s | **-0.0078** | [buy](https://solscan.io/tx/2mUEEuxmDkqff9wrRnDHkRaq39v5qh9S7Ceo8efSVsxiqGZ4tBGT1MAof8qSkrBdzgNDXTdASJLS9RTg3M1qT5nv) [sell](https://solscan.io/tx/4yYWrJFa5ULtVrm6CeYnV4vjWE4VCdFGVX4bkiQtMZf1JWfg5eCrbtFXaUqCJd61ydYQ2K9LJ53z45iWpBbRpkDh) [whale](https://solscan.io/tx/4dRGcKsquLSXJn51AwT7krYNLA7oetgui3L6w2KjUmXGpj8UEF3f9639jNKqnbNAn1hqjsTHsgnoLnnScDouySZA) |
| 17 | 15:31:47 | [A3dNy5](https://gmgn.ai/sol/token/A3dNy5Et73bxi8nXss6sj2aCDHou8UPc92qWVR5Xpump) | 13.0% / 5.85 | +8 | BAM `2GUnfx` | time-ms 1.3 s | **-0.0222** | [buy](https://solscan.io/tx/3sPwtm3KA39xhzWNJuNEdyw1Nc7r4mssZmRZuhHZVMbaiEuGV4Zvs4SUY14nFr3riY1N8khhDS258eYhYXjfdoZN) [sell](https://solscan.io/tx/5jVmgknkdYaQgPVhMpoh3VFPf7VjwMaSXDTbsYS2P9yrnVAfQggGzCPFLHLGHEZH52hyQGXZvvimoR6yPLJvcHae) [whale](https://solscan.io/tx/2QCVq215TpDh26bi7H8C978MgqBHG1UcqtjNdAoAVW4LykQLSaeSPeQjB1VYAUyAGvFXKdTSCUMrrTdgt9zfSpcK) |
| 18 | 15:48:07 | [LvDn9V](https://gmgn.ai/sol/token/LvDn9VYxabBdywvo3AgHp22B9C5VUi3LagGZF8adCQN) | 6.4% / 2.47 | +1 | Jito `Chorus` | time-ms 0.9 s | **-0.0121** | [buy](https://solscan.io/tx/5EYW2CiGfiCm7DK76oQsN71CEwyz5mq8bGTJqxLVy5hohBXRi86c8UjZnsMpoKbvAoBjK5HUsZPxmUfNvwjz55EK) [sell](https://solscan.io/tx/2Tw5KMNGwCs2EHMu5MX5W5ubwVZwWzLgXF5ifSWYgFcBQVxMcUFiMLasF2MjjGH91KwXyudCe4fFT7XFnDNUGwyT) [whale](https://solscan.io/tx/3i8FrBrLgMM3JAvyZnYr3YD9QA2MGb5AxRGW5otBkDGsdUrD9KnWwusDWiVLoNg2BifqrFECjFUrks92bsQVNBSL) |
| 19 | 15:48:12 | [LvDn9V](https://gmgn.ai/sol/token/LvDn9VYxabBdywvo3AgHp22B9C5VUi3LagGZF8adCQN) | 7.2% / 2.47 | +1 | BAM `spcti6` | time-ms 0.6 s | **-0.0146** | [buy](https://solscan.io/tx/3YbEvr6qLkYDibNVSyy359wDMDB69vdv2GuoFQ4hrgoHjRQ6BEHW1g6SUqxwNiFS7Ec1dpk2E1HD5yE34JtSH3Jy) [sell](https://solscan.io/tx/5kkK2uJGKNk9sh9uQeSay7eYeWcKqfySrD5zo7pgPWazXrRYHZFHFjR9bvmxbBn8WNYpcpMbtgjgccbXMrLYSQuD) [whale](https://solscan.io/tx/3c24EqmBcMK9ZfMme4hGQDHFJToeMVVNQXxwyy1V5MLLyJDmrwxYE5V66npvhhDkJdvWVratded72Kg3awdZQvRF) |
| 20 | 15:48:17 | [7DaA5x](https://gmgn.ai/sol/token/7DaA5x9Fwcg7mybgYovE5sddgYPczaTVNduqGZ8VR7oK) | 7.9% / 3.33 | +3 | BAM `HaLanf` | time-ms 0.8 s | **+0.0101** | [buy](https://solscan.io/tx/64jA19t8EbgwzeXKDckPJhKwtnkuHLAYnDbYExd8xsNpiwpWYanhtbbutyBwYccJF4mZU99rmTuj5vfztowA8UNB) [sell](https://solscan.io/tx/33fc7KPA1VbFqERYqhNJiNeNisKA17Faxscg56ALe5ncG6NfCfPtXUKsLU5Xyd1N3Ba88GqtkxotC6JJJMrSpqdY) [whale](https://solscan.io/tx/2CrAaE3oWbpto2unz71Dn388fojHvvanQQNyPHkcQFqkq6jfZ6DdXUKbbu5B7CjEhoW18FHGQWww9mRhUYhzTjhi) |
| 21 | 15:52:17 | [Ea6FCT](https://gmgn.ai/sol/token/Ea6FCT3jqvGFzAnp8uWeVVaQPAtRswQA5xq84rjfpump) | 22.0% / 15.80 | +9 | Rakurai `ana2y2` | time-ms 1.2 s | **+0.0051** | [buy](https://solscan.io/tx/4uFoYFaScfBxpNNsJre4qxKu4nGvJRo7DYUpeF4XfTr49Sg2UiqHucRkdUmPAb2nwjzEfmFTPYBcZMYYKVSH9eXe) [sell](https://solscan.io/tx/2iKhGdzL4qhfQ2uuMdxaoTMUPMMFzBovkyuBjZenZViGg2mKe37SF4uk6FpoiVKqJwSKBJkHCE2btmhkJsVxn8PV) [whale](https://solscan.io/tx/4NMDPdpWykXt8kEQUTSJAvKtwrkFLr1eDFQ6X1RL1f9TSprSVYvDqWtiEXzzBtVVpRBDA5DQnxz1NrwFNexJWNs3) |
| 22 | 15:53:00 | [9Ddiuj](https://gmgn.ai/sol/token/9DdiujZveLrq7p6kqMgHAgqadCo7xpmy2CeSXpEffQqQ) | 6.4% / 2.47 | +3 | BAM `DUND26` | time-ms 0.9 s | **-0.0146** | [buy](https://solscan.io/tx/4SxmsDZVhJTfhsxdYeEZ8M7hT7w3dA6bgHDp3mU7QecxfmHhiEJFdggoozhGANZY5oKVDoAaPyz9GeW7cYyzzNsE) [sell](https://solscan.io/tx/5mPJHtTby374vnMJbHTh6DrDiKnBZwLnAahKmPsLuZawpp4otWjrDx7orL2uSY1n1DeqkV5n4DLxpfbq6CgHG9qF) [whale](https://solscan.io/tx/5muYBt6FiZzzypp1v4oSsVitMWry7w7fAWhMCwgXBDiU3kMBGi9USfo9D6AXi9TLTUuQ9kQgpFDfcE7KY9cGDLU8) |
| 23 | 16:08:34 | [FDdRHC](https://gmgn.ai/sol/token/FDdRHC1DTRMjUPBfjySyfUoyU7dwycLpEkuhomKnLpyu) | 6.4% / 2.47 | +1 | Jito `HEL1US` | time-ms 0.8 s | **-0.0120** | [buy](https://solscan.io/tx/4HXZPZJMrVtjc25Qi1oV8GESsPKLQjGxuY2YGFp2cmpb5jCuuSCRAASuDHQ2dCaovXUKYFouPk68LS3FAmXppNaP) [sell](https://solscan.io/tx/2it4GyE9usKq2mikimAjCaED6ZkpLDXMZxxGwTXwX1SLygBB5mcVofzE6fx2zyYTfzo3sgL6b6KL6JZwppc84iKa) [whale](https://solscan.io/tx/28WcYvA8CSjqParGAgDH2jwSqHVaKDSwVgHCkbwjqosr1G4x862DvZ5xFsqrE6netZejA7CNV4sdZsW9qFHeR2ru) |
| 24 | 16:38:55 | [6LZBoy](https://gmgn.ai/sol/token/6LZBoy9xprmvUpgd3b4mxjpKyBFhMcjTakX6CTX5pump) | 6.2% / 2.79 | +3 | Harmonic `A1vqhA` | time-ms 0.6 s | **-0.0146** | [buy](https://solscan.io/tx/q7i65nCK2L5jU4w1uP8BiCX7uh3b72zeCG1rDmxKSPwrEQNc4iroxSnJLFw8R4ptbfEHXaJZ94bjurucww41vRt) [sell](https://solscan.io/tx/VyxZ4rYQpszujz5iG4UnGiY93R6uE4QgZDeVA1aFX8QrD3RdYzLSvc1E6mJzCp7UyN6ryms5K6zn8fRVhWwD1Co) [whale](https://solscan.io/tx/5dBMgK5GJtHqQEo2uNahpY238GGN53M93eigecbdqsEcBDTcFT7GVgoGx9RNYesAnahGU2LiwvuuLHWN3jaqFxTR) |
| 25 | 16:44:43 | [5MeaMc](https://gmgn.ai/sol/token/5MeaMcKVNqwYjygwNsdmNMk9L83LqeSLNgXx85w8pump) | 6.1% / 2.93 | +2 | Harmonic `CAo1dC` | time-ms 1.0 s | **-0.0170** | [buy](https://solscan.io/tx/4ui49SmYxLU1Absb7nxafFrAMJmrvGNBuUxeJZmAY2VFXMnGumd24csKttpkRz9zDkRDSWcqshdKR67mecuUELT7) [sell](https://solscan.io/tx/3AaL7ae2YYRYRe2hsdkcGxriiUhXbuUokJxJuzxmCuQZVH77a1Z2J3FmtgzsaddUEm92m32azsBYhcTGmVkDB98T) [whale](https://solscan.io/tx/3nXuKQQRD92sB41G3Euo8XhkLe1dBa1ber5gMNLBLypqhh2jE4ePajDGQ7chn1AtvgNdoPDE1BLDfQiFUf6pxKyg) |
| 26 | 16:56:40 | [4Z2ApF](https://gmgn.ai/sol/token/4Z2ApFVmx8L2xiRVWjjKGCFNbuQKGQWi9EbvwADyYj8e) | 7.7% / 2.96 | +3 | Jito `E1r4Ps` | time-ms 0.7 s | **+0.0336** | [buy](https://solscan.io/tx/aQiJpy5NqjDSXx41tCoPWpQHWCYU9iTziXTZtoGDj5mwwDTFJxNXS2CNFVCBiUCE73n2RVnBXwYrPZMmZjsnJdS) [sell](https://solscan.io/tx/4HdfeZ6TvwiDyojxzfSHwmvQNL7g27FjhSHPyTJYetd91go8PhCuqBX5uE4ED48tfTNfwsiTn5owbBuQoVMLu16K) [whale](https://solscan.io/tx/28VgkJPnPNqb1678x4jW4HXULqAsU3dYHtH5HGG8n79WnGeVu6iMHu8Vi6QFRUBuAgADG9YsjHa8UQogunfg65hv) |
| 27 | 17:12:38 | [2MGsNc](https://gmgn.ai/sol/token/2MGsNchxCZxuNp8NQEekeiGKp7M4kSb9KLcpNzVwpump) | 7.2% / 2.96 | +1 | Harmonic `Hz5aLv` | time-ms 0.9 s | **+0.0050** | [buy](https://solscan.io/tx/4LD2d5ra9mkcXT7VfuNwiCf65UDwDwKWY8JGWdUF1N9SSm1eja7EZM2DZkjVgUQ49Txahj97rGzuwzQ4QsGvFL7d) [sell](https://solscan.io/tx/47Y4LBajaYXAHkZQmExnrrTi9qCaifa3wPCY8ncebrq6v3XhfCuaDpEWBUajvac5vXExkMWoMYeUvScun8mSCgGW) [whale](https://solscan.io/tx/2x7szxvw97zW2F9m8T26V1jXEZqXGhSPwLvmrJ1ReHJ87CZYZwQj71veTneXSy4hNefjgvazCKZHkfxnt2mJN9LA) |
| 28 | 17:27:28 | [FsM3pu](https://gmgn.ai/sol/token/FsM3puRMniQdb6nR2RDYdv7ZCLmt6B9yshesa7x8pump) | 8.0% / 2.93 | +7 | Harmonic `87CcUx` | time-ms 0.8 s | **-0.0057** | [buy](https://solscan.io/tx/3FENq141FD3WT4yFftAbzJcU9ZXrboyvLditYr1kpdzmeLLxwcq64o2sU2wU5PXj9oE2w9sVndpAGdDHqr2ErKAU) [sell](https://solscan.io/tx/3tYnN3232duvGzDr48eZWrQUgcZhpGpZ6CyKLPhy41o81Gvi6JprKCFS6sN83SD3uYxGTJXihzS5MXuAdQSvjF4T) [whale](https://solscan.io/tx/48LreVwu7wjv6gGrKxidt9qR2PEPoMjYrdnTDH7PeuYaGEDrtFAb31PDbp687rZuvw7egyiNnRXDajuwDymRQ9Us) |
| 29 | 17:35:44 | [7hM3nK](https://gmgn.ai/sol/token/7hM3nKrjU6RKuCuAHqQrcrF2zeCMES7aCgXMSAgypump) | 8.4% / 3.19 | +2 | BAM `G9vCpJ` | time-ms 1.0 s | **-0.0615** | [buy](https://solscan.io/tx/276xTGPnehrYF4ahCuqsJXcyhZ6FfoDs1Mu2a4NXHdQwd6R1JNHNcBUdG5XMtHxtiGQZy2hvfswxJuG2kQregwmj) [sell](https://solscan.io/tx/5Bq2PpWDipSANCKdfrX7hRLUGD2ePjLEiSTjHQ6srrdBbteshEunt5vmLLkLpBEjic44k1hhSeKuC6k3dAbwxVH2) [whale](https://solscan.io/tx/j8mQGgqQ7Ypzioguy4Xz1veDXPy6gToDuEnuzUpQtmMfWdpi7bHpoYjA6W2w5aQPdfEJEMTrTuL5aijz2f5iqzu) |
| 30 | 17:44:07 | [zYepJe](https://gmgn.ai/sol/token/zYepJeP3icpZ6sqZfkouFeQuTAq2wCXwJSfGNaTpump) | 9.0% / 3.01 | +6 | BAM `58KprH` | take-profit 1.1 s | **+0.0436** | [buy](https://solscan.io/tx/4Tiyw6X7CXWroJGix6xSsjL2DtBtk1zfsxjhz6D1KWcSnx4n8dcX4CNcVnSXT9YGED4HFZhGPiArMymN7YuzUJCR) [sell](https://solscan.io/tx/2pvQ9sPdycacRTCoJcuwLjxYbCZdee9kE1YA6YpQxNLrEpDvzoU7zkCEjkU9udeq3obYPi2uQScynTcJzf5tYR1c) [whale](https://solscan.io/tx/2Lmxgnq3Q4LDw7dQAwgXLNQRmNYdhuc9yMoGV57tNsfyZqFqKhK41Sgz4rzjDucsrM5PMBPQa58YPRY7rpqqYKG8) |
| 31 | 17:45:18 | [74srbv](https://gmgn.ai/sol/token/74srbvncEwpALVJ5grtYE3y6urjySmhbagYFkRG5PpWV) | 10.9% / 5.93 | +2 | Harmonic `DrifTr` | time-ms 0.6 s | **+0.0228** | [buy](https://solscan.io/tx/5wkSN2PrsPupSnyDXrxAedDYt9Vme5MfFuS2CndhJS9bCWFjjpKP8Qe3N2XyQHF7NkeJ4y2yPRz7pcNoBbecbFz6) [sell](https://solscan.io/tx/64nfq5yU3DVnQrjBoGa9vPA95zr2YaYp6gVsBrhLkJMxdCrup37uEn2UpT2vmU9RG5FRm1HmjExg4KqyWSongGoS) [whale](https://solscan.io/tx/5R1tu12swhsj3x5nQUNso715LwvaZ8KzMJWYD5Uc5hRuKsGTcERNvcydqNXY98bJw7K1TffPQPyDiYkYenAf9Q93) |
| 32 | 17:46:12 | [GbJ3fG](https://gmgn.ai/sol/token/GbJ3fG6gmFf4fvi9PE4JKfrYdxaovVo5eT4cgxQDpump) | 9.2% / 3.46 | +6 | BAM `dxa6QF` | time-ms 0.8 s | **+0.0199** | [buy](https://solscan.io/tx/2UrRwbdmf2vDdoKYrnvs5Tfcaz444XRTh6ezC7CxqfH9nCRrBU3KQ3G2AKcqyLAsiDsiYdjtkNzrL6ddDB9gUKZX) [sell](https://solscan.io/tx/9wVroZdRypoHcj7TvyzqtBeLquHy84MftbcefzdKqNVzfGPguud9w2aqRNH4rdKVLtaypkqRZbfApyxvRDcVso8) [whale](https://solscan.io/tx/2k9KzacRy6UhSkBxkrbf3qPmDiYG8QtW2eEwwJX8LAPaG22XmJLzt3zSgZqfY6Qd3av7dK2HUg18gUzMRj6n3evN) |
| 33 | 17:46:43 | [7WALXS](https://gmgn.ai/sol/token/7WALXSYv2wsG5zcJZRazqQAWLCpeUB91XcE5dtGfpump) | 7.2% / 2.93 | +9 | Harmonic `GYx8kp` | time-ms 0.9 s | **-0.0094** | [buy](https://solscan.io/tx/92M79ST7g8YnbmnqG3RpaT37zYxXtn8jLq9No5PZPkiM4xYArN55GZD7kTeNvUXSeh3YP2RtXf5C3uYVjWJEAh4) [sell](https://solscan.io/tx/gMxfywiWCDXqL5XFXQFvZCktiqaxYpUDnDAHMf2ezY1PXqfQUKQigCNZ6iDFpZwSaFk5Q8w8KQcqTphVYnuo4wK) [whale](https://solscan.io/tx/3yJQt8D5FUX9Rd5VFzTgHYCBkGFURsdE2tb3stKakMDScAhQYv5REYYuRnLUgUApLrxB55H9R8FeKoCZiVLCF9xu) |
| 34 | 17:47:07 | [74srbv](https://gmgn.ai/sol/token/74srbvncEwpALVJ5grtYE3y6urjySmhbagYFkRG5PpWV) | 6.7% / 6.06 | +2 | Firedancer `HW4zor` | time-ms 0.8 s | **-0.0171** | [buy](https://solscan.io/tx/3wF4D2ZW1BeseAXqFNgnE9TLboWDtKPi6yuDAAoCVNCqqAXXCkjwTR49ctRnmAtBmDqV3dpSLptqZVgyPQqNcf67) [sell](https://solscan.io/tx/4PdiiQjAwecRQpEPpXQDsCmyNW3B8SEhJambP66KLxam49rM5DGMRZgeRfspfjY9yXBnnsLpRAMUN4r9ZdK6PzJk) [whale](https://solscan.io/tx/4AAsEZUjPYdfKRq6SUNUAEiNCrWBNJbGESejCVHbLQfRs6Gc8QGG6UgXajxVdCXXDzgmVB2yMkoVV4Xc5kJnyxwY) |
| 35 | 17:50:10 | [CHVhuz](https://gmgn.ai/sol/token/CHVhuzzzxDoDfEih9Tp8JwjrmPYbU3rKhsczRTqhpump) | 9.3% / 2.96 | +1 | BAM `Ste111` | time-ms 0.8 s | **+0.1075** | [buy](https://solscan.io/tx/3i5LLdRaNHPbTaMxakVZPPjmh6YEuakcZnXKqiWwqNxBvvX5tZ5gkPEyJDkEpjJ79SAAoNToLnU5YKPeJngbCNct) [sell](https://solscan.io/tx/2j6t4YzucwqqF5eXipajBhi3by6jXZJybv2ZysqqAxC8PaxkxZq5L896Ab7EcdMhTC9Q8RXmffDw6VjxnAg4JGJU) [whale](https://solscan.io/tx/3GxBx9mqU4GFch4BHbAowG11B88QXLknmy8Dm6EuXroG53XxidggxeGknRQp8HKvRn5ANvT2jt3chWELB3Lbu1nw) |
| 36 | 17:51:04 | [74srbv](https://gmgn.ai/sol/token/74srbvncEwpALVJ5grtYE3y6urjySmhbagYFkRG5PpWV) | 7.6% / 2.96 | +3 | BAM `8uJiHD` | time-ms 1.0 s | **+0.0226** | [buy](https://solscan.io/tx/ztc8ZD5mzXcNiNPnuCpzV3K6hTk79yntEMyKGCwvuhBZadqoFxL6ZiWTXjG4brUH44k5StTD6PTvh1uX8Nmrnww) [sell](https://solscan.io/tx/5AH4JLA2jn5H28oqtMq4c7sZPdSc74J73BqPN9Zw4RcMt2yKmn7L8otUUihzzZu2Y3QFaHvnoDVq5HbJfER5ap8g) [whale](https://solscan.io/tx/3cvqkBChdpEvRK9H68W25U1CcbCWxYCKCvTUNW4ix9WEMMVfi4ACzHVGwBojZKZEDiq4MALKULxrN3RSKFGeazoy) |
| 37 | 17:54:29 | [AaXkyT](https://gmgn.ai/sol/token/AaXkyTABPynETQmQzhc2LSrBs1G9CMfm9R5BdhoEpump) | 6.3% / 6.37 | +1 | Firedancer `HW4zor` | time-ms 1.3 s | **-0.3152** | [buy](https://solscan.io/tx/3feEYVXdm3sF4EMy8RJWhz1HMakXm5ea6CR2Fz8LkRgswnEpJDBVdkQBL9ApMKRZJVx1FAi2qsuBBFTQdPdX3V53) [sell](https://solscan.io/tx/3GiGSt3WnZ8kDvtH7EwWGuQQStfJuZi6KRV58BPutYyQvcdfHqsJD7J6by3GMDxT2CHSx9rpRiVyVJewtpTyA1oq) [whale](https://solscan.io/tx/rqGnaRXQuJfbnuAMCoQajEYESZnsriJwNKmUdQrxxTtcWgThhEWeWcvSwNQB1gCm2LpN3ypBcmqvwonshf39ycY) |
| 38 | 17:59:35 | [GQmknK](https://gmgn.ai/sol/token/GQmknKuEPyx6kpYzRtHu5yeCBV4G2pS1WJ8xNS54pump) | 6.9% / 2.44 | +6 | BAM `DRpbCB` | time-ms 0.7 s | **-0.0032** | [buy](https://solscan.io/tx/fG8PjuQnrSo1rMvxJh4rVaenJMB8izBBGrS64mw3PTMAGAtbw5PrJwTQWCwDehQUNFM652iyjB1DYMsonSEEjiZ) [sell](https://solscan.io/tx/jPJNbajobjWWwsACMwKCphgRDEHBwLxWhtXpRCYTJJnqWWoq5Mr6MgCnWWfc2vaBJNNx577URgwxRGBcs5Ncow9) [whale](https://solscan.io/tx/3cLa19AFKdx1h23rS6fjsk8VCLzkTq2vYW1Tp53pT8sGKZJHCJwq7FVGDJKxwBKE5gWjHPwbVSg23U5rbffKjtDo) |
| 39 | 18:01:50 | [HRzj4J](https://gmgn.ai/sol/token/HRzj4J2Q8HdcYWkJJMGsDiJMDBubqf472Jr7N3rUpump) | 9.5% / 6.78 | +2 | Firedancer `BbCQMW` | time-ms 0.8 s | **-0.2157** | [buy](https://solscan.io/tx/3CZdiC8TSz8DDWXzAAV73b3QFX2CmCnxRfG4doaFKPUafoffLAw1juC7uoziLP6mDxkZsgRSchMMRHPa3VKjoXfh) [sell](https://solscan.io/tx/4R7reQHraKzJjoNzsYKGuPd17YNXx4ibvTaZuXuUUKpWzzhYQW4wZQKBectTeYowZA3Aa7EcQtdaE3BcdsvvyRDy) [whale](https://solscan.io/tx/42rfMX3LhMCZREruMebp9yyCnV5DSEC3bGSEKchZ4EpsSGD5Pj5msQ54yzmdcxxpQ3ppa1ZTcXriVxc9N7CXqYQq) |
| 40 | 18:06:34 | [EH5tce](https://gmgn.ai/sol/token/EH5tceQ7edbvwMjQT2VFRNNzQQBq27CC8ihEW5xvpump) | 8.9% / 4.94 | +8 | BAM `FWwwP9` | time-ms 0.8 s | **-0.0305** | [buy](https://solscan.io/tx/5gyMSwnWHxLULoXfXgbkf5YbWwmUAH8jhqhXu5axrn2iTezk9hAdJoiWC3BsP3KUdDvfaHWh5G4KYX73w5zUEm7e) [sell](https://solscan.io/tx/yu7eM33Z7eSjncQMzgRGuux1wosfN6zsgHZK3xHQoNFcTKPHtVSYjGhbTVmxsaj5mqTvRo5JhWtZUxjfFgXcY7T) [whale](https://solscan.io/tx/2JaogD4hNXCVcVHyyDsLmAitZMPYw1FtQrwaQS81VVnHQQF3jvLFaKUrpx8izptn44naY7F5JFkVr471MfYr5jsy) |
| 41 | 18:06:40 | [MBjkr2](https://gmgn.ai/sol/token/MBjkr2q6z9J4C15zAw3C6ZyZmKc3eUnreYAifM6pump) | 7.0% / 2.93 | +1 | Harmonic `Fd7btg` | time-ms 0.7 s | **-0.0098** | [buy](https://solscan.io/tx/4eynjBKkqtpiixeq1jFxLktrzUPjUPinki7hfrmzQpyHfQ8uxKZJQ4KbWdn8vg4dmWdbhAHPxujTMry7YPKwfoEB) [sell](https://solscan.io/tx/3p9FQwWPcHaBmfbkqEsEtwDgFLMRxeRoHHsRbHC8ShPpe5XVAKFsFsTuQQm1S9Q3UVKY2CPPhvNk5yzXvhUN7FVT) [whale](https://solscan.io/tx/jrV95iSoeCDbrse4WQr5r1DPadXfJc34W1hyqCECnMozAuEUGJKG167vc429svb5Ms4EYbKSpb9Krp1rTvamnRs) |
| 42 | 18:12:55 | [BV5X1m](https://gmgn.ai/sol/token/BV5X1mUyiUhTCN1QbPsRekqtM2LXcdqriuXRuuJVpump) | 9.0% / 2.96 | +2 | Firedancer `6DTkui` | time-ms 0.6 s | **+0.1135** | [buy](https://solscan.io/tx/uTf5bF4BmVKZdhwe8Fn5bN47qrNz9uwW8vhybM8qeEN7ZM7eQgTSgcycQpGP9VVnENrwzsQEPuwUs9j682Jw1aq) [sell](https://solscan.io/tx/4Re2UCdUmHakevWX7Yw9QUTcMNzJ8D27HRwGitA6raPayiNsWYuemk4YeWCqbSi5PZteFkRmZniwn7XMx7xCA8ob) [whale](https://solscan.io/tx/5Rq5kFdeNN3QGdtJVTk3PXuUVncL1YeHYg8jPtFKMWyrWLx6NsPpPGNqsbMg7Zh8A5H42MpGBGV3rg6WDmHznkiW) |
| 43 | 18:12:56 | [6v7XHz](https://gmgn.ai/sol/token/6v7XHz8YDk3vG4iZt8NKJ8na14hf7Cb69yW2CmS6QAm7) | 7.5% / 2.79 | +2 | BAM `1Link6` | take-profit 0.5 s | **+0.0453** | [buy](https://solscan.io/tx/4y2VGPWbtSK6AKUHeMUqbCeGYaXjRKUH23u6CNiUJ1EpWZ4EYyVqp1SkYND99qPcAWG4cvrZuZHchTKRQj9U1VQw) [sell](https://solscan.io/tx/FLMrKZwmFJwLvR2UjxjqReE3RKmzSX7sa83AhSytKmzVZTT9SUMdg7Hpkvttau9VDUH42yURFmyo9eAzLWEhquP) [whale](https://solscan.io/tx/26r7zSJogo3MQTeh82H72UrbuWqS967BgHmpgLU7GSp1qCfxdYrVLVgHRqi8bPe77RrkMr65gypaFEyPMVMapAXM) |
| 44 | 18:15:18 | [GaeFor](https://gmgn.ai/sol/token/GaeForzktFSJ8pj5tgbL7Pe4iQJ1Km1SjxeJtEaJpump) | 7.6% / 2.96 | +6 | BAM `GzDfKK` | time-ms 0.8 s | **+0.0030** | [buy](https://solscan.io/tx/2hAwDHKEorgqUBn46XRqcmv8X4LfZZPwJ68fmH8kvQNQHdAck9oWR8vk2m2CbUdyQcodFeix8tg9thv694d3XDFV) [sell](https://solscan.io/tx/21YzKMEG4VGhNEPa6aKrqxqQ91DCgvFefqf15mkCLUtTwAJxoAqFRp4FRYeDrzyBp5eEQLwKoxDL6c18U7BfPbhT) [whale](https://solscan.io/tx/3NoKrXGSdfjHN7vzxzS7db4ShxisoEd7g3E7ko8PUT6ZQpkW2rs1q8AF9nE1qTBWZtHcwHhZcaHLxLNNRXt9iuG3) |
| 45 | 18:20:22 | [JDZY5T](https://gmgn.ai/sol/token/JDZY5TpavVVAAepmRPf8u1V7gMDZCVwdzCp3WCQspump) | 6.5% / 2.96 | +3 | BAM `AiDoLW` | time-ms 0.7 s | **+0.0235** | [buy](https://solscan.io/tx/5wGAKKeYWrQ7GdavisPaztnbfP2mGYhBsCVMD5HA3HDnSBa2Uf8b49pp2SJQkHofeQZCZnQ34f9Nw41RVc242xxR) [sell](https://solscan.io/tx/HTjQ6FFk21wNAbkdCvsYgFn8wyUciGdstxFYpCfkZ5PG2fmRVoaBx4xxHKCAT8VYty7JGFdTVC3t2DQJdzHavda) [whale](https://solscan.io/tx/4ttu4XY7W7MLcmKCS4GYwCBzDMb3594WqVyhJo7tmTaankwTyS4HCGjYQMNoZgyk8tSjVLXo47vXcJwuQPEf76bs) |
| 46 | 18:25:11 | [AiCdMS](https://gmgn.ai/sol/token/AiCdMSJXGrGC3NJxqJ6AQwqjHHEfpZMVtmeWFaW8pump) | 7.2% / 2.96 | +3 | BAM `FWwwP9` | stop-loss 0.7 s | **-0.1422** | [buy](https://solscan.io/tx/5zqe6FdKsz4poekM63kvk9da3yzYdVZrpu7wQY7AFd9yFVpoCxgFp3dHt47y7Lviq8CGbHaxGdzjpZh8X8KjnRmC) [sell](https://solscan.io/tx/4KvnDKfFuZdZXa47mVHVJsXYohf4CmKHPky5Szhu3doKuqBnjixKUGLtZRQixtuPoXN5i2LUqmN6SFQ33YutYs4G) [whale](https://solscan.io/tx/5dvWHBWxs3r1YDsCBVJFX5hnfpeRykoNZBemyrxBUQC9aqifS1JUvg5uYUxJyb9FWuQZqT966dbXFXQUmomn7RXN) |
| 47 | 18:34:00 | [FNezBd](https://gmgn.ai/sol/token/FNezBdsLAn7H5KyBYPdrbjRzRop49kSmGpMVe19Gpump) | 7.2% / 3.46 | +6 | BAM `9jxgos` | take-profit 0.5 s | **+0.0603** | [buy](https://solscan.io/tx/E9Czeb5Y34qARHfpprpuTytyUsAE3kUMKD9DRHbWmNaR4LVdeFPb3dgxdhnEvd6d2Z4SEKPWCysDAJ9qipJHLPo) [sell](https://solscan.io/tx/3PTVdty1CYELGoSSm59ZWjHBnwHH984cYQGXibSVKkXVL2fZyJaQ4jFkP6xsUHKiKQ9GQ7zZ1FTYzRhynUk3m7YF) [whale](https://solscan.io/tx/4fxi7qz5qJRa4crkXo38z4ZYhLSH9yzsZJCYwtXnSD2hC9Dq3hm3hNHgPycDZpWKAzREu27TTR7MgtBaVyX3PMki) |
| 48 | 18:34:38 | [FNezBd](https://gmgn.ai/sol/token/FNezBdsLAn7H5KyBYPdrbjRzRop49kSmGpMVe19Gpump) | 12.4% / 4.94 | +2 | Harmonic `Fd7btg` | take-profit 0.5 s | **+0.0442** | [buy](https://solscan.io/tx/4rVCdhPxtNKFvV4eUsZY9AoE1AhGCugRCvmScJTYmCW59vRYMVxG5VxfNfAUxSWfpSciVyZr26AannvjFSt76Nfv) [sell](https://solscan.io/tx/4k7T25DQ3SWq4uFeJatNFfQPr3M6jApaffMBwWH6pyozkYaGwQ6zL4vTXqcDQtqNhddDFu9WbxHHJdFAUCsPFSR7) [whale](https://solscan.io/tx/sKMnqYfeEm3Bad4JppLrgkmYYVLKjQaW3CQAaVJwVM6AFr8aCt3k58eJWoDMq9WKVa2gPkmVufqBwD8o9gpnf6s) |
| 49 | 18:35:48 | [A7AtqF](https://gmgn.ai/sol/token/A7AtqFvvBD9MfWqwvGAcih5SAtL6N7GpXqrQ73RqMXVC) | 7.2% / 2.96 | +7 | BAM `7nzTzR` | time-ms 0.6 s | **+0.0042** | [buy](https://solscan.io/tx/2NGoxbctdra91nV3uqk5z5S1mzRXe4ijzx7kgvp4VPRYCkzLzFQVe6DTfG38FJtAgT1EGHtvjJwBwGiGjnKvUgGR) [sell](https://solscan.io/tx/3N2fzZW6CYD6oNUqYce8sqC4XUGwsGddSjx9fHLGxoUuWsaoyQ8YUdDUFdTuAckhcyhg9DVHbn6JZ32yyA4FnZsg) [whale](https://solscan.io/tx/64oTp6G6q8xBTuLZacYynPLL3YmqDVXbcnVvCu18BCYmrX4mjhv5LS9GQpiS3UFU8jEr2ifRAwj7TkMQiET6vWFn) |
| 50 | 18:36:45 | [72KTne](https://gmgn.ai/sol/token/72KTne4FjHhzsu2Gw3i62ncjWdGrvsTykiMniBcxpump) | 9.2% / 9.88 | +0 | Raiku `9xcXe4` | time-ms 0.8 s | **-0.0059** | [buy](https://solscan.io/tx/4KKPGtYWbV71hFkYGd2jHzQ7QECoAuxFKJstkKHLYJpzXp5xoj1cj2JzS5zLQZPE9YXUE18GoWfymjnnG1zVVamg) [sell](https://solscan.io/tx/hF8LZ7k6LWZxzcCrqzLboT8tdZUu2hMEaLiFh4NQbZmfPRWX5NumFn1A4EENPUWSiaJ2tFkWeihyYebxiX5JtoF) [whale](https://solscan.io/tx/5HZ3RsKq29srGtNC1zk6QyAnH9jSaHV8u9kPYJf9NDxBDw8Wk9W5a6D3wqP8j98aVXawyZ8nVq1NT3JyZgkSxA5P) |
| 51 | 18:42:28 | [BM9UYU](https://gmgn.ai/sol/token/BM9UYUhwFeQZ2XavgvtsXDw8Q7VyCNtCZ8SNhbQMVxgv) | 6.4% / 3.01 | +6 | Jito `HEL1US` | take-profit 0.7 s | **+0.0794** | [buy](https://solscan.io/tx/28dFgcURkHE2xhN7WrhChrCZWtUpZGcTVS5wHaoNoQXvtH2hDExVk1YBcRdUMnfaJBv6ed6ebei6hcs7h3RcaVQ7) [sell](https://solscan.io/tx/32FMWyvUQ1eTsPEDDrEtHJpEL7qipyj39rJE2jcTAP4psC3pXZRXt1xbdmnhCXWKRcWAw46dNVnJnx31g2AtK6gb) [whale](https://solscan.io/tx/5eMQTzJay3nAK3KkeMwJHhmZars2i7q4bt1ncTnnG7iUZ4GqnbGbKhXytV13VvoDmhmXLDpB6NQgt4c9isYu8wy6) |
| 52 | 18:50:54 | [AG8Kc1](https://gmgn.ai/sol/token/AG8Kc15fbxkPF5Fo3eobjJax7zY6pJVKE8KPGrpKDB7) | 7.4% / 2.47 | +3 | Harmonic `Hz5aLv` | take-profit 0.7 s | **+0.0969** | [buy](https://solscan.io/tx/tH1F4zviu1yepnAGFrtNfHpCGNevbukiLRaocaAhL3tcdZS5TWGxagRGqZL4NRfEYerD8DNqXmrvtizn1GHqT13) [sell](https://solscan.io/tx/23wrDNjjE8T9HaUTZnDdiJJetypaRFaZp639HSFpif9ruu8qE4L32fPFWQCCzrypdAYWK2VtKM4fuKY8Mx76mXmn) [whale](https://solscan.io/tx/5gKAgzc7jtJZzJ7j8LRUHRkgU8iwjMH1fENUJ6GgszBUqdcDe5zD2hV3ejSahjjuaUPMhr6j3H9pfJArxKj7sc8T) |
| 53 | 18:58:34 | [BaAB7g](https://gmgn.ai/sol/token/BaAB7ghmdP4u4Y8STq6ZYacc9TdHdLVJPdnzqNRoYWNg) | 9.0% / 6.91 | +9 | Firedancer `JD549H` | time-ms 0.7 s | **+0.0009** | [buy](https://solscan.io/tx/2c2QJWLJgHWSwvbRLiCbyRNCZfz51eJDDsATMHL9zcWRMaevx5Vd6CvKTcEF4QeD83oRhzzWwTc5LKckEGrcU1ST) [sell](https://solscan.io/tx/5iZGgZvghyi8SyVuUSWF2j43cXNpfB6PEftMiVdytRRftqcQcSTdTPAMnMZnQ5pgia4brvxQkBNW2xggkPDLutmU) [whale](https://solscan.io/tx/5tcndycCJ8X1MSDT3pp2TgrGkqqDrC9sunD7bzHD7oUeQmt5LTW9ssD6RupAojdzRfhjPcntBfiD5NqVCvq1yUtk) |
| 54 | 19:02:58 | [B1CFQW](https://gmgn.ai/sol/token/B1CFQWAgaj6Y9uX4KUBxPKiueNWe4E4VdRAcnpzdpump) | 8.1% / 3.08 | +1 | Firedancer `HW4zor` | time-ms 1.1 s | **-0.0826** | [buy](https://solscan.io/tx/4ZtwBprQPZwqTaqt4u9yWDNwnwA8tC2172RD5pLsBynPNgYSsDRrMxzhatdsnEbicgmLMZYzXDSqrXysFPqmb8eK) [sell](https://solscan.io/tx/4BJHnaFgWntq7UE6R1s1L1gBfazyHMBNdSgd61WJ5owVWfVEbvfvjjsj3981PGuneeNiXiS3LWGuBwxcKjZaBGfp) [whale](https://solscan.io/tx/eYDkoSqRH21HejXCQx67464hJmAjr1DNmpfY8BYZsPQHzo3cgQnL7MWQsfDzyY1MFrRLWaMGBqNmVYu6tgsPxAN) |
| 55 | 19:11:17 | [4iLYt5](https://gmgn.ai/sol/token/4iLYt5o3dQsfEosMtt1FGu8Zf4ZZ5QxTVZbKmZwLpump) | 6.6% / 2.96 | +3 | BAM `Atom7L` | time-ms 0.8 s | **-0.0172** | [buy](https://solscan.io/tx/45v8TeroFnmLdBKVWq18APxdCWLQo7F4sPMHu1S66wrjD4iDfKCRy9xRsxnDe7TtbU5EiKNFARnXdwhmS74LbBYx) [sell](https://solscan.io/tx/2KHAMTMYBCujSUaeKY38y1K9PkebouWNYSYjY93QRAFUsUMthW18ecFUCruXcxM8MjwxwCheMfrbu7ab1Ce43UgA) [whale](https://solscan.io/tx/2VWvn1L61cfN6KP9kESBT8E81cw5hAJ6a6U4YbbzY6mthPZHbKB2t1MXqT6KQi7q1ZvEx2vHLaPFQ6dWua9kB3hv) |
| 56 | 19:16:02 | [GTzJGT](https://gmgn.ai/sol/token/GTzJGTTFJWFNjrRj78WEF9LYHveAuuEYwxayiku7sKpN) | 7.5% / 2.96 | +4 | BAM `7EzbSa` | time-ms 0.8 s | **+0.0064** | [buy](https://solscan.io/tx/fggkMCdki2eVAVV5KNqXaWtkvny65CBoWW6tiN7jWprQNi8crCXYCdMYUncyjDZmdxUWQ3yiLDt323Yjy9BnNiZ) [sell](https://solscan.io/tx/3oq8mXvQcNh37mkMeJNkNsoy7Qf9ZrShdoiuxJdB2RhdtP9uzh4pzjjo5i2aPo33QDQQUT1z15Lc4KedKLSajYxz) [whale](https://solscan.io/tx/veSD3C3pHK4B7mdZTJVuywjH5qPbicJEM1dhB2CRKoP3JLLZLoM1TJsXWcFWQ47dxiEfZkrZjQNp9dgHYAWNG7N) |
| 57 | 19:16:24 | [H2q3Qh](https://gmgn.ai/sol/token/H2q3QhbY9KZTDMUBTS8C3JQHRRxFmfQNspgFUw5Jpump) | 13.7% / 5.93 | +3 | Harmonic `6yFGGA` | take-profit 0.9 s | **+0.0866** | [buy](https://solscan.io/tx/38q3TJ3dgWQWRdCDuyUHxhtGqxRczmstPMZsiQu22QCHYhDEneWSPRHCTErBt2TNnLE3UeSD3Xqge82xp7aDCbhJ) [sell](https://solscan.io/tx/4yuCBDLtqQ2BBszuPw2HNFK82hom5CHHmHQYcbXDiPB9HkmkrNHcGKta74YKkjDp2pXACpnbSgSvkuCjQ3ojNGZA) [whale](https://solscan.io/tx/pHeWiZJDBaVCF6PAEttnxhpAEUKVMiA2823Nxp4XEioiM2yf7DLAr2VsXoc11wfeoHDLve5vFq1kjbkLQN52K8Y) |
| 58 | 19:18:41 | [AWo8cZ](https://gmgn.ai/sol/token/AWo8cZLpWHG6UsMTGXEENTPExnLEiKYk8cbjf1yMLf55) | 15.2% / 6.78 | +2 | Firedancer `BbCQMW` | time-ms 1.1 s | **+0.0251** | [buy](https://solscan.io/tx/2pkfWsocxVnFtsdYDEXgue7BnMxNqUMfzs7LxLBPFqLvKdDAuny7gPKd3rSEkD1rb1yTNbTXHaGnDa21TgoCjsQA) [sell](https://solscan.io/tx/4vjRVS2TSRBEuUsXzdjYyWVRwoAVZMjXowqTqU93TSRAaQvN9oo4ZA9Jk6C12EfkUFNEu235mXnDguvYmurxX267) [whale](https://solscan.io/tx/3fkVYjre2ArbQHvhdcx1j9yR7K7sCb8SxAwsw44ALdZxyVcUKtQXVJUZfPxPiLd698SdoawisZneoYYXKXLgkB5w) |
| 59 | 19:23:15 | [Aqb6b9](https://gmgn.ai/sol/token/Aqb6b9p6KTuYzfaAAdRLgtVQR98EzqnuxhS3YzHgSbN3) | 13.1% / 5.93 | +2 | BAM `Ninja1` | time-ms 0.9 s | **+0.1304** | [buy](https://solscan.io/tx/2FticqFjPy85YX489mWoSxJT5GiLJZaZn92BPPtUoCAyuLi4xMHZ1Vv3g3UtG9cuHHGtS4GiSWdQeS1EYKZyaT8T) [sell](https://solscan.io/tx/5NuNoR53DtHbVaFgbD5oDXPNuYJKrRzGCpH5uJBnxEzXar8TnWYmX6ZwXA6LwCkXfoFchFSruud2z9eXdcw72xKs) [whale](https://solscan.io/tx/2zcLE5vW6goMKrj4CpnbWbswCXpmPWgwVmn18DaDKEXy8ATwPxUkwU9p9gx4P22vSNYqBhvtavtcT9Kc9aVp2qZn) |
| 60 | 19:23:52 | [4nUnqe](https://gmgn.ai/sol/token/4nUnqeicatWQf4iGrcR4vUSkPrwszw4sDpbAzuaspump) | 6.3% / 3.46 | +2 | Harmonic `HTeRsa` | time-ms 0.8 s | **+0.0313** | [buy](https://solscan.io/tx/3q3X2veVN4jj4JnZidSWN8CUyZKS95HtLxEmmCkoKWtZ2HFoy6y5AoLgNPJBgAbWtHUMEPMVsu93fYpQ6JCBXojS) [sell](https://solscan.io/tx/61zEG347YDbExWvuUCXraCWGQaMisMBaYtQ1wh7AUAo257C3uFrs9fKhoJxt4F9cTE7Asz3Jr1kLDHVVRN1fo4bX) [whale](https://solscan.io/tx/25GAbMmcWuK6s2jjfVXVs7gm8oTtnTeJBnBhZwN1WjpoD376PE8FHdNby8t772YFtCS3xbuHQz9QGwCHp1qwr73u) |
| 61 | 19:23:57 | [394RuU](https://gmgn.ai/sol/token/394RuUzCBmZmpdkc5PCy8ALu6MbMGrWafdVnaF7Cpump) | 9.0% / 3.95 | +5 | Firedancer `JD549H` | time-ms 1.3 s | **+0.0110** | [buy](https://solscan.io/tx/5GN8atKYkRDutwKVWRDAmjLaF7iywRX485iiNcVpTp1YaUkebozASBX1oHougxpJwnqP97nYvwyL2uUJVLRXTViX) [sell](https://solscan.io/tx/jKT9vcQod9AWw1vqLLKR7Hjue6uZ2f1WXTbAJ646EoXDaRyTb4VX4h8T1fjNiRSAXNCntzXFvF2vhAbvTb9WHeb) [whale](https://solscan.io/tx/3NPsVgNLbTFB1cHvPbFonTXuypu143r8bdk4xVKSu5aaJaXxCaDHqNn3fYUpRS4cYSKEMLeJKVgjSAnYqhvmhvLn) |
| 62 | 19:25:36 | [39fejD](https://gmgn.ai/sol/token/39fejDXL6QrfVePQ7TseUXgkRkYAqwAwdV4TrSvYpump) | 6.6% / 2.47 | +3 | Harmonic `DrifTr` | time-ms 0.9 s | **-0.0146** | [buy](https://solscan.io/tx/2fv9QWNqMALaXxXA3KkQGB6kGuoRKqFLiSucRC7FdBdsHkEDKjWjpYpUELMUUAVXGryk7fg1bXkwQBeWHeyvVtJP) [sell](https://solscan.io/tx/3RLMR4n2awt9BHo8HTFvgBpwkim6FiZ6cXe7SE2svFPRdSnHfCewGxZAG6UYFCmDq7WmnbcHUEb2wCzH5ftwqcym) [whale](https://solscan.io/tx/2Ks1G3EPFpsMJBNuj4n5eTS7uwXoqYi2YFgTSwyQsh6yvz5sf2DTAcEbQdUrGfMTCgZLKTz7DCaStUq5VsjBVpfQ) |
| 63 | 19:26:02 | [7CiXCj](https://gmgn.ai/sol/token/7CiXCjWWbG6UFEtgJA2sYXrXnjW3Nx4umFRaSwj2pump) | 9.6% / 5.93 | +1 | Harmonic `GoeW4a` | time-ms 0.9 s | **-0.0316** | [buy](https://solscan.io/tx/4jE5KbpE8U7Nu2NQN7ee7DbTdCLVvztrWzSgoYx1wXhJDYYKTyfPedVnUviPDzXkgFXEuLY6KrAgx34YmZWk3FqK) [sell](https://solscan.io/tx/61rHreEtuorzLbnv6EW8yU34AW3YQE6xvgxZDAyWPHR6kpJRFgqPyAuwSdAgkDJckbzN72wRFJVmyNaCncRcUgNd) [whale](https://solscan.io/tx/45XJeLvjcDbnpH8PWKMug8ndEhzNHHQGbbYsYn7NChmX9L2HsRFmJ8cJDKkijiYtaXdSbgZ4C566EJCc5eyp62JS) |
| 64 | 19:26:41 | [Xe9aYX](https://gmgn.ai/sol/token/Xe9aYXmqk6mNfsrDvxw1z2VNd9ZKXbhNtckY7HPpump) | 8.2% / 6.78 | +1 | Firedancer `HW4zor` | time-ms 1.0 s | **-0.0193** | [buy](https://solscan.io/tx/36Exeq1HZW6BSB2WDNef8ucwh1dkRbMFZGrc3GMp9g7TyK8uqY7mUsmfVdWwY7mWvHEeKWZapBrbZdZopUzPhBAQ) [sell](https://solscan.io/tx/44XW96NKj4jkGYh5paZ629w19w9RWjcVCJi4JY4jVbCGnFFR27Y4pdgKo8pWcKAqetXTS6GsasUonmjToqVuYFR6) [whale](https://solscan.io/tx/573L1aoeHwGc3duaSUsUx57Qd35ziiVCoDQs9oNw5a9EJQYVT7BUtjJn8TdgjPf4tsex69EYL1S3vn3DXBXW7qwK) |
| 65 | 19:27:04 | [4biV2u](https://gmgn.ai/sol/token/4biV2urUKduJvWvwpZfw4Cn8VnQf1cefhev5rakBA8Cq) | 6.9% / 4.94 | +6 | Harmonic `AMukCL` | time-ms 0.7 s | **-0.0420** | [buy](https://solscan.io/tx/4PQ24MTg2eyhaKwee62CPXGsNPuSsWUVsfoXV12XhYa5y49NsYmggVQ3wBggj2g4wc1Mtx5xnLCuhPpTz5FERobL) [sell](https://solscan.io/tx/5jFeCTbqATMjuP598AWTsB6aMz9GPjVdShEBgYUPcdVWJvUsSbe885KGQJdfWcCaqf1C8NuQb7tUuHMQvXGy8y1w) [whale](https://solscan.io/tx/79ytugiU3aN2i7yjHN9qQfwXpsR75i6JZxMkiVX7t4tyBHj3b5bVMber5Mpqv1eNFeECN58X2vFQK5aEkTjw6k7) |
| 66 | 19:27:17 | [3ezcFJ](https://gmgn.ai/sol/token/3ezcFJdyaVFyJyegZfEqXLdedwpnmmT5D7VehV35pump) | 8.5% / 4.94 | +2 | Harmonic `2m1A2W` | time-ms 0.9 s | **+0.0065** | [buy](https://solscan.io/tx/5gfZvsVdWNJ6c5Qe2rrmbmtgEATxRixXW1NPtMNAcMg8FgbAPujHb3rdFRVLRmBzdRuQjHoQXR3oja2REBjyYD4J) [sell](https://solscan.io/tx/4v322EESm9Xp6GqpuNamw9fzEr1jpzsy6zPV95UFapta8rBm3c29N7rqYGr1FHzvRbStEUs1bnUXPxNqzZpZRRXy) [whale](https://solscan.io/tx/63cS1XkJgm5AC2shsPgeZctPjavT5FWbCbtstyS1wD3eEniMBCfsx48oyxmAhr2rGUBnofFcy84M7wG4KU8xQ7mM) |
| 67 | 19:31:57 | [3cKdXJ](https://gmgn.ai/sol/token/3cKdXJRzWcpZGTYb86c7yru2dg9LmFjm6vSwECJgpump) | 9.9% / 4.89 | +6 | Harmonic `6yFGGA` | time-ms 0.7 s | **-0.0175** | [buy](https://solscan.io/tx/5wqiZ22pBpqvegW1XHLTVepfJuYw3CeJfoPQrQZaQKw9xq3D7GVhwAuHPKjdd5BigPw7QM9Y83BEYqXptjqwrBjD) [sell](https://solscan.io/tx/2kYgsQ42AGQofVyGhELoj9t7r8zNyN4pNdyPpX6jUGDgUc7eACnT8iVpA4y7q6qedKHE8WvfPsabNnin5qY3F4bv) [whale](https://solscan.io/tx/523BTyNZ8eSBc3VDXJq1wChLpfmeD6GfjV11mDYiM372k7UPTXCd2u3K4T4KsmMEbpg63FgFhqgACcF7vhr6TJAa) |
| 68 | 19:32:23 | [EATM7Y](https://gmgn.ai/sol/token/EATM7Y2byEEWXdZnoHCGMoMnULLizEAm5ya58d4epump) | 13.4% / 5.51 | +2 | Jito `HH5dA4` | take-profit 0.6 s | **+0.0548** | [buy](https://solscan.io/tx/2Pb3AcLCEwa4hUoXn9qvLzCSxabHNpsFND4upRwk2fz1MPtJZC4jvVENVAUaryfCTdtZkjRyuibzQJtMCRYKM5ZU) [sell](https://solscan.io/tx/4pSv23VG3yNZjhiTnfRtRwvpBmUA9TL3nQsA9dDmZmqSWiEooAi5U6n213DnSBzwKK43o9YCPusquJPQnDCDwssV) [whale](https://solscan.io/tx/3f9jDXzeoLMu9YQqE3JQFqeyvJ6gbHpnzEiDyQY2FCB59z6r6aTiFWJXhi7M2qqHUQbYuZdWr9TxVvk7iMEdYuP5) |
| 69 | 19:35:37 | [79HsTq](https://gmgn.ai/sol/token/79HsTqvSCyjngxJQkEAZyjREh6xXrfXSR1CZWKr9XtCm) | 10.0% / 5.93 | +5 | Firedancer `JD549H` | time-ms 0.8 s | **-0.0096** | [buy](https://solscan.io/tx/3gHQVVNVn2b1s7bBRHdVf2Jm8Pwyg5ghFodok9rY2bbeMP3jXYVF7ppCQNpEEnU9PG2B2XWDvTvpaXB2rdnNCdrq) [sell](https://solscan.io/tx/xY4j1GzC9XL3aFBkGM9hCK5xSMCadEPWu76trzig6gCvWixaYYEs5JaGmG7T6qHfkBgidzwzk6nCKbVtwuwrn1r) [whale](https://solscan.io/tx/3hnEQXjhxckS8qEhftEzJZp4teUp1eHNjxRR6N3p44kXiAyyGTBceX7rx2FAyWXTFPgau9xRTYMVnJJuaRHQSKam) |
| 70 | 19:35:45 | [79HsTq](https://gmgn.ai/sol/token/79HsTqvSCyjngxJQkEAZyjREh6xXrfXSR1CZWKr9XtCm) | 8.6% / 3.95 | +2 | Harmonic `AMukCL` | take-profit 0.7 s | **+0.0435** | [buy](https://solscan.io/tx/654iixfKLZHyvCtkTY5LiEVC8p7p2C317X6PjRvgy3YUm3JZZbWH7YXQMTXTYwFbVddaVAHAbZW6NsS6L1AGeYyh) [sell](https://solscan.io/tx/13zDvsr5NBNooY3N2wtFJJD898dMGVruAWNwpyERMkw5GRn4UZowe8t6tek2TVEGorehSdnEFjhrpq9MUwRCzZF) [whale](https://solscan.io/tx/4hzNqrW6hX4ZWcpsKvF9xKGx4zSedGW6dBJkWyzwhNX2wADqY2JaEGtgv7ATVWZDAitEpZrDLTFacEfsJQazLyfV) |
| 71 | 19:36:18 | [5A4gGr](https://gmgn.ai/sol/token/5A4gGrQ5geC8bQn2rJe43ZXNBzYSu7wTBonVsarkpump) | 7.6% / 2.93 | +2 | Harmonic `GoeW4a` | time-ms 0.6 s | **-0.0146** | [buy](https://solscan.io/tx/3H55WQtDvpTYSk9ng9RWXx5dGuKJAr5RdJgrKhV17ymmayWBc6iGcCkEWXi5DXzqA16FEqoRTQbedUHrHiarZaR1) [sell](https://solscan.io/tx/2tP9BtKtVXh4ZHfZd7jzfL9ScnntMysGNxoBtNDSdEKVxY6iUN3rDVXqqg4PqEfMAxBnvuiv6cDU9PuWL89MB575) [whale](https://solscan.io/tx/49chXSLZmbE8eQFLUwEydtbZZEatqMi8w6tKtk3pNUmMxYCnmaN32xpx5xseLwK9re9Pcp91AmbghUoxFkmAb8Ds) |
| 72 | 19:39:01 | [5h3UmH](https://gmgn.ai/sol/token/5h3UmHB4H32X2wVZexovMhre1quUwk8QWBdFYL93iMfy) | 6.5% / 2.64 | +2 | Harmonic `CAo1dC` | take-profit 0.7 s | **+0.0543** | [buy](https://solscan.io/tx/5XscPf4o4b6Pdbardvj6NaEELCP5FL8aso4tjQo3sFn4PecpuRNsSWxmXiLvv4j5sDsBLqSWX36juqw7bF7J18fa) [sell](https://solscan.io/tx/2FEYtPWSbJXkeq9xiyWJpHEFXoAh8cdohD7HPXHgKExnwFQWUdkUCwimkvgqfpxVhkaTNHoADQQrYQspEUCuYTd2) [whale](https://solscan.io/tx/mYE55zggA2b6d2sbAxCn8CrJhWaXcW8NDGH98FogJ1mEPjskpDTj8v2xwZohkkDpy2UFbmJbzFUdjAe6Rs9x6GP) |
| 73 | 19:39:05 | [12nwwh](https://gmgn.ai/sol/token/12nwwhe8QLhC6t8b63JhH1UJEPnPE7SRg3Ec8zfbpump) | 7.3% / 2.96 | +2 | BAM `AWcCdY` | time-ms 0.9 s | **+0.0292** | [buy](https://solscan.io/tx/2oiFiefX1KNTr7mCBG5afyHn69pjcyktVyMBxYyky558vzwUagnyqpAA8nFg1n48AXSzvs4ggdzYTcBQw9jpJMg) [sell](https://solscan.io/tx/2urytjakoq9mHTe6hHoWtGv9HSmeKZCQWLHtWWB3hAvkTbJxmc8bdSQ13EbXEQJ7uPuTJhKAAUSn653yrTthr8Jg) [whale](https://solscan.io/tx/3fVr9jD2v6P5uWqzvp2kR3s5NVyU9iUZaGnQpaLKShjERo3fZp554keenuCd9wEN6TwywNXUwx2Xu4cewdAufB8y) |
| 74 | 19:43:21 | [F6ETgy](https://gmgn.ai/sol/token/F6ETgyhK8C74FuH3XKcv6fHKvQ1x1bzuadbWYT6Jpump) | 23.5% / 9.88 | +1 | Harmonic `Awes4T` | time-ms 0.7 s | **-0.0095** | [buy](https://solscan.io/tx/PRjK2V5DEX6QumMTTSBVm6dr3s37XrpgMPAZBZVooMCef6PhSoqnRGRZVA3EGmw5Rkrc5LLC1mVFRcRuxwBw4qr) [sell](https://solscan.io/tx/5QjDaxsWHH48LPY3fq54N8djQRcDrHsgepDpAj74WxbqtBBCH8EUPZ5seqq8mM13kMe7Gc17R6iK4qdLe3qVFpRG) [whale](https://solscan.io/tx/pHaMyAcTt6CbLzWFHPwHN3pahRspBWiMgzhHc97GBwViDhLnX7btcyNPZHpaZxZbYW8JPUfGbpA14MqNYc499iA) |
| 75 | 19:45:16 | [8MYWrF](https://gmgn.ai/sol/token/8MYWrFukXWr1Do1UYk36afF7xYfeQxWewm99ig7zpump) | 6.3% / 3.92 | +8 | Harmonic `Fd7btg` | take-profit 0.6 s | **+0.0848** | [buy](https://solscan.io/tx/5kg34jgS6MP7aPXx6nMcpAc53mE8HWY7DyYd4QkjFfENgbAf4FcxJq4Su4NvD4w1ihWBPc5dDCCJtiaSJGz1gKix) [sell](https://solscan.io/tx/53ypW8eUdvDrecDAz6irYcug23BYohGyPETMrgmERYJ46YCFbcVZNbnwPvcvygeV5LW42t1a4DcJvyPqM5kzxUYo) [whale](https://solscan.io/tx/356cr7pkJZC9gvLAizaWQHYND9qSx4g5J4fcmtLYLMDPncsRXpxAWepzMkzgDcXo7KEAaBp3AEmfCv6hMiRg8r2e) |
| 76 | 19:46:05 | [EJ5Bs2](https://gmgn.ai/sol/token/EJ5Bs2kKqWNSW3vst3V7FCoG43s2BW45gKwq1bFzpump) | 7.3% / 2.96 | +6 | Harmonic `CAo1dC` | time-ms 0.8 s | **+0.0095** | [buy](https://solscan.io/tx/34sSGL4Gint2TqKHnXEWbSuuaWckarbC2RhLBjJ6k59ZGVvaY8KJH69tz4WzjLSAdpNCcvtfZiRumJ24Rwntasv6) [sell](https://solscan.io/tx/5zLZH787CvaE8B3cC3xXNLdRhSynjuesmFHZPDFavgyUL1x9pQe2dwYrKhmaFHYNMieCNxiDFRH2twKKWQ7vxQT7) [whale](https://solscan.io/tx/64UcW82CkEafqTdgKoJCgvJskKThFGWG7YXcLowxhKeCZG7yQwwemf6m3SR1fYRuEkwTcJ9vHbDDcwfpjCiBYdmg) |
| 77 | 19:50:56 | [J9BgFu](https://gmgn.ai/sol/token/J9BgFuzyMVfuUageapQGmcK17oCf6Hwmt1w1fW4cCTXB) | 7.1% / 2.96 | +6 | Jito `E1r4Ps` | time-ms 0.7 s | **+0.0034** | [buy](https://solscan.io/tx/2w5SwCC4mC5Qx32ZXXuYVdtD63p4sWBcanSKTUZvVyp3d6FEkb1ymJpJAHjf9RUqXNAoPVLzrutusoT8n6DgFoMb) [sell](https://solscan.io/tx/65kXNgSmSSj8ZNh4QqX5KMMsZrweyyjMQn8pPhQCU1RqCQhRP93K8Ak7kkJV2rdzZzbjL9SPMKD4vHpPeoudnkM) [whale](https://solscan.io/tx/2Xd35tqdxUXTgT8Jr9kWmpsYAP85Kes8LnqWYASRwkcHhrAALvZgZEDuDVFuotXKzjALhHjBrPg9wuPM5vNZ1sCX) |
| 78 | 19:56:02 | [13FiFP](https://gmgn.ai/sol/token/13FiFPvxRViATXYZ8ry4BvXBW9bQdF3V9BVL2abcpump) | 8.0% / 2.96 | +3 | BAM `HLnodb` | time-ms 0.8 s | **-0.0366** | [buy](https://solscan.io/tx/3Bp9grHSRuau518f87ib6xv3uHRMYVpbN9Tj5hcZU9tXQcZQhzaz1bueuTtHbaUQbMVrpeHKSYyxqJwZKLu2ecgn) [sell](https://solscan.io/tx/59bt8MWU1S22saZKoB5We2j3pdYTUYgW6HzPZ4iaYrmG1wBR3xsdBhATfzDstZfzuaXp7ffhmMoRULH38hHeFXkG) [whale](https://solscan.io/tx/8BpPUpeWPdC8mohmweXJtLeW5UAAKVVkM8ex38gd5FY8g15PxKYWyMie2LSdg8ffBQdGUobEPj3LefrfeagRebK) |

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 20245 |
| Inside the envelope (age / drop / since-buy / size) | 9853 |
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
- ⚠️ start refused: Error: keystore: wrong passphrase or damaged file
- ⚠️ 72 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getLatestBlockhash: 3 timeouts/transport errors (worst p99 277 ms)
- ⚠️ RPC bh-fallback getSlot: 3 timeouts/transport errors (worst p99 277 ms)
- ⚠️ RPC bh-primary getLatestBlockhash: 8 timeouts/transport errors (worst p99 1001 ms)
- ⚠️ RPC exit-primary getSignatureStatuses: 1 timeouts/transport errors (worst p99 527 ms)
- ℹ️ 4 send-path health events (self-heal), e.g. `SEND-PATH falcon UNHEALTHY: 3 transport errors in a row (last: falcon: error sending request: client error (Connect): tc`
- ⚠️ big pre-send loss AaXkyT -0.3152 (time-ms, Firedancer)
- ⚠️ big pre-send loss HRzj4J -0.2157 (time-ms, Firedancer)
- ⚠️ big pre-send loss AiCdMS -0.1422 (stop-loss, BAM)
- ⚠️ helius-ps cap 20/s: ~40% of tries refused (7,213 by 19:47); fills lost to it (COVERAGE.md: 55 shadow-only fills worth +1.48 shadow SOL).
- ℹ️ Landing slower than r27: >130 ms on ~51% of fills vs 36% in r27.

Checks passed: every pre-send fill was closed by a sell; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Done after this run:**

- helius-ps cap raised to 40/s on FRA and AMS (owner OK 10-28 20:05).

**Recommended / open:**

- AMS run 34: same config, cap 40/s.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r28.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r28.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Pre-send (section 4b): the jsonl presend_live_* records (fills, closes, REALIZED, account closes, stops, end checks) and presend_attempt_land (try results, failed-try fees); the log's PRESEND LIVE lines when a run has no such records.
- Engine sessions in this run: 1; refused starts: 1.
- Generated by `ops/dip/report/make_run_report.py` at 10-28 20:04 PKT.

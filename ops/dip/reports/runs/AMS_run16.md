# Amsterdam run 16 — dip bot run report

*Pre-send LIVE probe (dip13): 0.2 SOL, 4 attempts per slot via helius-ps, caps 20 fills / 0.03 SOL fees*

> **Verdict:** Pre-send: 20 fills of 118 windows (9 wins), realized +0.0119 SOL, failed-attempt fees 0.0192, NET −0.0073. Live = paper on the same windows (+0.30% vs +0.31% per SOL). Landed a median 53 ms after the price drop (not 0–10 ms). Normal bot: 0 buys (37 of 40 picks on leaders off the list).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.0073 SOL** (wallet 1.2282 → 1.2207, Δ -0.0075) |
| Started (PKT) | 2026-10-25 08:48:49 |
| Ended (PKT) | 2026-10-25 10:18:49 — time limit / max trades |
| Ran for | 1 h 30 min of 90 min planned |
| First / last buy (PKT) | no buys |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 0 → **0 filled**, 0 failed on the +5% guard |
| Fill rate | – |
| Wins / losses (fills) | 0 / 0 |
| Per filled buy | – |
| Fills only / failed buys only | +0.0000 / +0.0000 SOL |
| Reactive bot / pre-send live | +0.0000 / -0.0073 SOL (pre-send: 20 fills, realized +0.0119, failed-attempt fees -0.0192, 9 wins; see section 4b) |

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
| pre-send | LIVE: whale >= 5%, 4 tries/slot, 0.200 SOL, limit x0.88, route helius-ps, caps 20 fills / 0.0300 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 90 min, loss cap 0.228 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 14**:

| Setting | AMS run 14 | AMS run 16 |
|---|---|---|
| engine build | dip12 (M2 + pre-send shadow) | dip13 (pre-send live + sell fan-out) |
| pre-send | off (shadow only) | LIVE: whale >= 5%, 4 tries/slot, 0.200 SOL, limit x0.88, route helius-ps, caps 20 fills / 0.0300 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| limits | max 60 fills, 1 open at a time, 540 min, loss cap 0.284 SOL | max 60 fills, 1 open at a time, 90 min, loss cap 0.228 SOL |

## 4. Timeline (PKT)
- **08:48:49** engine start #1 (session with 0 buys)
- **09:49:31** pre-send live (session #1) stopped: max_fills — 20 fills, failed-try fees 0.0192 SOL; no new pre-send tries (the reactive bot kept running)
- **10:18:49** engine end #1: run end

## 4b. Pre-send live (pre-placed buys) — separate from the reactive bot
Buys pre-sent after a big whale buy, before any dump. **Not included in sections 5–11**, which cover only the reactive dip bot. Realized = the engine's PRESEND LIVE REALIZED records (chain txs of each buy and sell; the buy pays the token-account rent). Rent back = that rent returned when the engine closed each pre-send account after the exit (dip19+; before dip19 the sell closed it and the refund sat inside realized). Failed tries = fees of tries that landed and failed (6042 price, deadline, …). Net = realized + rent back − failed tries.

| Session | Started | Size / fill cap / fee cap | Tries sent | Fills | Wins | Realized | Rent back | Failed tries | Net | Stopped |
|---|---|---|---|---|---|---|---|---|---|---|
| #1 | 10-25 08:48 | 0.20 / 20 / 0.03 | 3,808 | 20 | 9 | +0.0119 | +0.0000 | -0.0192 | **-0.0073** | max_fills 09:49 |

**Try results (as seen on our feed):** 6042 3,387, deadline 326, unseen 40, ata_exists 35, ok 20.

Tries never seen on our feed: 40. If they landed and failed they cost up to 0.0002 SOL in fees that are **not** in the failed-try total above (5,120 lamports each; inferred, the engine does not see them).

**By exit reason:**

| Exit | Fills | Wins | Realized SOL | Per fill | Median hold |
|---|---|---|---|---|---|
| time-limit | 13 | 4 | -0.0497 | -0.0038 | 0.9 s |
| take-profit | 5 | 5 | +0.1400 | +0.0280 | 0.6 s |
| stop-loss | 2 | 0 | -0.0784 | -0.0392 | 0.6 s |

**By leader type (the slot leader where the fill landed):**

| Leader type | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| BAM | 8 | 6 | +0.0602 | +0.0075 |
| Harmonic | 5 | 1 | -0.0333 | -0.0067 |
| Firedancer | 4 | 2 | +0.0145 | +0.0036 |
| Jito | 3 | 0 | -0.0295 | -0.0098 |

**By hour (PKT):**

| Hour | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| 10-25 08:00 | 3 | 3 | +0.0629 | +0.0210 |
| 10-25 09:00 | 17 | 6 | -0.0510 | -0.0030 |

**Best pre-send fills:** 36JuJoPL +0.0335 (Harmonic, take-profit); 34q91xj4 +0.0315 (BAM, take-profit); JE2i5Grb +0.0304 (Firedancer, take-profit)

**Worst pre-send fills:** aXXPihhB -0.0484 (Harmonic, stop-loss); 3V4FvAPb -0.0300 (BAM, stop-loss); GjjAS9WK -0.0219 (Firedancer, time-limit)

**End-of-run checks:**

- session #1: no END CHECK line in the log (engine before dip19)

**Every pre-send fill** (time = fill; whale = the trigger buy; P&L = realized, rent back not included):

| # | Time | Token | Whale % / SOL | Slots after whale | Leader | Exit | P&L SOL | Links |
|---|---|---|---|---|---|---|---|---|
| 1 | 08:52:59 | [33JBgP](https://gmgn.ai/sol/token/33JBgPpwT6CQNSRUuXxYa7F4t4HfHssjqwrW8CzGpump) | 9.1% / 2.96 | +8 | BAM `Fc6NNd` | take-profit 1.3 s | **+0.0197** | [buy](https://solscan.io/tx/4PVnNpqcLjHbN71RyMQh8RaQgZPyDTjtd8bA8pp4mtStEDgbY6DjMSPza8WfztCp326sJjYkcUegJAugJW27FgCW) [sell](https://solscan.io/tx/4r2h9XUEDrMmCcJQWCiHZ5YbjdnNfniUy5kgv8VHtzxXKwpndQsMHycsEMXQMuWzE5a1v2hG2g2WTTT7SjJK8UBe) [whale](https://solscan.io/tx/35S97GfRYES9t7HpuH7Yhpg6GaighcPgMrsmZzVk3SwQo5xEcRBUDfSvLamRcywBMMPeQtWTWPfU6RGBHWrAb9vk) |
| 2 | 08:54:12 | [36JuJo](https://gmgn.ai/sol/token/36JuJoPLWWhdsDKSpXRA7dZhH8xMUG2uiFeB484hpump) | 5.2% / 1.97 | +3 | Harmonic `Fd7btg` | take-profit 0.4 s | **+0.0335** | [buy](https://solscan.io/tx/4aquVAWFxdoeqpvySPSkLMcF1Lz7RF4JfbFMebHxrJQ6XcGHbLguho6V222ZSh9d5Teyu8CzegCZpFG1U8vqR3MU) [sell](https://solscan.io/tx/2ZKuSAdcK4KE4sLojzmX9Ke8j9Zi3ZmCU8Rs6Fvf2W6BBTSex4c63YEUjowoHgjbWgwNpToN4MnNZKaavaNSqfHd) [whale](https://solscan.io/tx/5orVARyMb4b3hhhpZBmVocDTvq4UNhifA67vghmPpuAR5btzVGNMstXsThrASpg7WhvAMyhGb9Fy8P2ZhtpnX1iR) |
| 3 | 08:59:46 | [VzZW19](https://gmgn.ai/sol/token/VzZW19bKsLydbc21u3KJUhpaMSYveLxransncR5RUNE) | 6.0% / 4.94 | +2 | BAM `GBQ2Gv` | time-limit 0.8 s | **+0.0097** | [buy](https://solscan.io/tx/4PKzHM5NpXvmLBMSoywDC8FaGmthB5FfQHeGcM23YvedkK219is58u47DLpqg3vKenbuBViqnnmno1GBLyG8c9PY) [sell](https://solscan.io/tx/2eherD5HtCKkxXH4KHNS24PwiwA6TPEcxjrRbZT1zxZtn9eQiFaLrBzknGqWjPh39Yy2ka32RZhx9fcmdt7Gb1FP) [whale](https://solscan.io/tx/28e9Yu8nJ641n8w93c7TrZdTRMVCHWm8pe3VNd9U6A95YRaGDfabZ8EMfK4LucWnA4EtXVMHmecrhHHZym6mzWUN) |
| 4 | 09:07:11 | [3d9EKY](https://gmgn.ai/sol/token/3d9EKYfoqeGruYfgLaFZyE9cz34DivrLEAiYqYh1pump) | 7.1% / 2.79 | +1 | BAM `DRpbCB` | time-limit 0.8 s | **-0.0069** | [buy](https://solscan.io/tx/3NeSNvBkRdSQJag1AsSabqnc4QBQjZF3qNVBQsppTUiXZx7kJupCqZ1rLjF8rzmfSSAJBSi2BVmPCP9yGXu92gZi) [sell](https://solscan.io/tx/64nFYnhioHqC4P4ugZaqnt7mqGisdsWr2bRDVQ5abKAhUS2T7XfME3g9PqaZffzJ78f1pVzs47cUqNo3yzFQ4c1p) [whale](https://solscan.io/tx/5UUgvwDRrxtczwriHhrLnwtqxDmxfQ7KNWQqjo38JJDs3osmWfKNcEa9acRNuuXVTwmV1tHhsmFeDgAhVgCJPiKL) |
| 5 | 09:11:34 | [aXXPih](https://gmgn.ai/sol/token/aXXPihhBToNqC3oHL3V5YTT4hTEQzxdGqdz258ipump) | 9.0% / 2.93 | +7 | Harmonic `Fd7btg` | stop-loss 0.6 s | **-0.0484** | [buy](https://solscan.io/tx/2RBDhcBfaubx6gzu4pbAa9sap22m8FzgtRY15vJZmuy52J43DGZfhtjivAK6meAPKQJjob6F7GxgYer6WHq88vjE) [sell](https://solscan.io/tx/DCKLqJdcikBAk1xCmoQh2daCmq9nyYqnPgGWxRgoK9rNJhatWZ6QeTQjJ29KGfszgkMH2i5VyZkSFcSumsdTcxP) [whale](https://solscan.io/tx/3MC3eski2zZVchCHkS4vTSTeuH5vso9iFNxTgd1JjaqvA42F6crMRVqFruJVh7MdVL9r47pCJJkGu28XdU1zE6cC) |
| 6 | 09:11:57 | [CAcTJe](https://gmgn.ai/sol/token/CAcTJeokozVkTEoU7DQkGiMP9eXePLk5CYEFyagxpump) | 9.4% / 2.93 | +3 | Firedancer `JD549H` | time-limit 0.8 s | **-0.0189** | [buy](https://solscan.io/tx/z8FEDYqx74K6RDkukpAx6PboxYnvrrQTnbfGKwtb4NKdnKJ9TCmxChHoaciiZmkqW7PpeRHobqqNzG8phVqmJSP) [sell](https://solscan.io/tx/4Lh7r2ZXvaeStemvRpEaVBaAvdwkMSgwerqFXtyUZyyDrBnJicMP35Yb9MLdcm9Bw7GhiMg93i7gyzSLYVSYDi2N) [whale](https://solscan.io/tx/5ceRkGZthxctzs1j49enc7TArA6dTcjcVzZwzLR8MrXPvTA53bknTPEtLotnVuqxTrWyG6Puvmydzz3M8L54qRYj) |
| 7 | 09:12:08 | [F8gSob](https://gmgn.ai/sol/token/F8gSobp3VbdGcCcgPzdqqZHv6sKDiZ1EMfv7yzcDpump) | 8.9% / 2.93 | +9 | Harmonic `BeaCHi` | time-limit 0.7 s | **-0.0044** | [buy](https://solscan.io/tx/3EH1diMJBnN9VHTSpBXoaxKy6Ru6wNJHeZ4aGmypdpk7QVvoCftr7ccQhQPWWh4DFxEZUSgFhEKJDjUpUafk5m9y) [sell](https://solscan.io/tx/4uN3FSiDqKwDghFwrU8dLXBcNPkhduNcHbo3uKpYMiWSfaaM3aFC6Y6d9C1PbCrj4TD6jJgB2q7aV3gXgBZX53Ui) [whale](https://solscan.io/tx/2agi6EgidVGugmComNDL9GV8kKE87mDV7i75Kn8GoUArmVvjrrqNFbq5ZqnwkMCkQSo5FDMVjzMc2pLjoRRPPZD2) |
| 8 | 09:13:40 | [3V4FvA](https://gmgn.ai/sol/token/3V4FvAPbcmKWBiT292Pa9rRJra3vz6S7oc24eWoJpump) | 11.3% / 6.91 | +1 | BAM `ByszyW` | stop-loss 0.6 s | **-0.0300** | [buy](https://solscan.io/tx/vy1REq8fXaKXUbXTpHSbYNnp4VnRtHVN5a5SK2onqkvroS949yXzmnP51v5nZT7SR2iFPL4yzSw5x2tMxfS5pD5) [sell](https://solscan.io/tx/2SmgU21HQeFmde5pt9tNK1UXPHRSkjftFjjpQ6paGjiDMnt2q4aRSRjzhgakSNP4NZw642YEXwJoykJBq7hkTZKx) [whale](https://solscan.io/tx/37osnNFLRzd7pKFMEWh1SDwDSaTr2LhYSLAfPCJAHNmorzMVvZSXhRtRxyhSdUPxV1XZvojrNXT6Y3iPHzxMMKLv) |
| 9 | 09:14:02 | [GjjAS9](https://gmgn.ai/sol/token/GjjAS9WKq4FzodXY7gtsqJ2Z3UGki3RQ796UhH2fpump) | 5.6% / 5.16 | +2 | Firedancer `HW4zor` | time-limit 1.0 s | **-0.0219** | [buy](https://solscan.io/tx/4h9Yczbk3DrfuGLnRfyYt2nvUaPgLiyoQfvV5nwWBW9FpzmcDV6Apicivetjuk6v8CQEDznFj6EPJmsyBv5dfWJe) [sell](https://solscan.io/tx/3tHGYzD2Mz6Sc1VfzC8QFeSiZzeq8fRc7v1EVVeFiU9Nnawge8gMwpikrrUjN8GBQqoQfmzGpFChfifmGkRwsMHg) [whale](https://solscan.io/tx/2gPWDJ68GDJZi2Gqqxe3hsKGWjMPH1NLsDxipJzKHB6bNWjCRc4zDBEi6xjCHnj45u7vRsvmWWjwUfurhGnYUYxo) |
| 10 | 09:15:31 | [EDHxyc](https://gmgn.ai/sol/token/EDHxycv1oVAmrqrxePoAeoE7FHe6h2iCBZHH1Jfpump) | 7.3% / 2.96 | +5 | BAM `3RXKQB` | time-limit 0.8 s | **+0.0178** | [buy](https://solscan.io/tx/5MMxBDLLCBxk9ZwaVq62btvn9MF3aVGMQv6SJdYHvPdvctvLwKrTbjs5jZBHwVsKTHNNULR2Tyw4ETQW1ZAFFdKw) [sell](https://solscan.io/tx/1Mv6WrosaxQZCUsSCV4CriYFaSU25nmwWKNEcNgHgTkqWN46XMeWJYL28ATYbzxRSSjvKCuXucuSgfmEqiMKY38) [whale](https://solscan.io/tx/5BbSLSr6J1PbJM6unPHwmPLfk9xtvE1M4PqQVY2M35vuL8KxykUDVi3ZQWA9PF8Ch1vmmv2tmQu7df9jbPAvh12Z) |
| 11 | 09:25:00 | [8cbqmN](https://gmgn.ai/sol/token/8cbqmN63Rjwqb3o2SFsp4LYq1kNxHEDHfEzsyDK7QUiF) | 8.4% / 2.96 | +4 | Harmonic `6yFGGA` | time-limit 0.9 s | **-0.0069** | [buy](https://solscan.io/tx/2n8HcQVeZ57ZoAQHYqcCfQsYNmtyDXCoCv2p9Smoivr1QTC72HgfS7143mYM9E8imP4dgEF895qdNbytViP5hUMo) [sell](https://solscan.io/tx/3zmPdaWjkHYqtc5MgpF77cEAThCxJUkSn8sFKTQyR7pRkyahA9b2uj3zKSXw8sZdwzQmY1JL7sVAQLo5sW8qJV4b) [whale](https://solscan.io/tx/4HEZPxizQso79y9JRx9nxp1mJuxJdhkrMUbHXid5sqc3xaR2QowGDB7XmukGh92DpDsUxo6X7322219XkheRxGvy) |
| 12 | 09:29:17 | [C39CNs](https://gmgn.ai/sol/token/C39CNsHbpwQ5HwDBFZefCY8aodJXihGqM9mNgYjQpump) | 5.8% / 7.29 | +6 | BAM `DRpbCB` | time-limit 1.2 s | **+0.0123** | [buy](https://solscan.io/tx/2KVCRhzfU196T3VQVic2PEKzMdjAAoxc5qwnfQy9PP5j6h85Ho8VX5yAT9Vg3ZgEwc3McLzhgeabqpGuYNSGAVsL) [sell](https://solscan.io/tx/48HWNU8Vvk9wGd8qxuHDVBigMFmoUFNBKW7qCbJRtECu3ZK37yCKf6pc1CxeipJJonWNefncFCuQF1fWTMtzV3un) [whale](https://solscan.io/tx/4TQcMd7nHJD7y2nhFrUDAKyS66M3bDzvmcbbJ6kGYRnd9Ue7dYNYRi8VQQ2psd2KPmwszw1NhmMFuRqwxH8y8VjT) |
| 13 | 09:33:40 | [EMK4bi](https://gmgn.ai/sol/token/EMK4bidWog2FeHaKUZiSfAKwyysyCTgcok5Yi54vpump) | 8.4% / 2.96 | +3 | Jito `8o8wWC` | time-limit 0.9 s | **-0.0032** | [buy](https://solscan.io/tx/2U2PjFjf86XAodJ7jbVicZwMwBXHv7A3S3xKmcR928TS9nPQYhCpr7FALaM52vKWGDrCaurgvriSF7ofsayyeZEJ) [sell](https://solscan.io/tx/3maVBNYhWRA1T5AC2r6T1bV6gxUCd1S8WHnv1VPFMjV5WbZDS2qAn4xV6fi6zro77gqU3QrFshHec14RvSLrBRQr) [whale](https://solscan.io/tx/JaMeqQvG8ZAUnMYRfGbMM15Vi8WJKRojCEKk7q6VZpBhChJWvdmSwyezUqaTTnZTYgP2dneuKBhA4bZ7jdqJijU) |
| 14 | 09:37:12 | [3q4V9r](https://gmgn.ai/sol/token/3q4V9rVq69T9cQG582ionmDKtuDx3ddFkGvkkdNqpump) | 6.8% / 3.25 | +5 | Firedancer `BFmqBs` | take-profit 0.6 s | **+0.0249** | [buy](https://solscan.io/tx/4stFtdFgLUArdejyc4wmBJfnexD1oqvyJkxKBxYNGPRbX4aeXgS2cveTVVPLHT94ff7enCm5WTWNvJGacDZ7pt89) [sell](https://solscan.io/tx/5a7ZeJCsWnVNK1F2Yk76PKoRa2ynEypVa1EPMAPBSjDyXhbS9WPo1Pt63rnkcRLNtSaUZx9mSpMmUC65dcbXp8ba) [whale](https://solscan.io/tx/5eYY4uDbBMKUPYVwj1WV9SpiqG5u4BgHNF9AeS2tCdMQzP6bfMUuWG1pZfJaG5Uqkv6d3MnjTbvFPLzumbi93jmr) |
| 15 | 09:39:36 | [JE2i5G](https://gmgn.ai/sol/token/JE2i5GrbHunnmy1UcqFFW6MEXaFwspoA6p5C21Z8pump) | 11.9% / 6.78 | +2 | Firedancer `HW4zor` | take-profit 0.8 s | **+0.0304** | [buy](https://solscan.io/tx/4itfb12W76ffwMtr1nGkG5NKPRSQ4gUi1ADQgvqS3aNDwFK3GmDHFihLBf4i9ZCUV26LaqXgCEdXSPDEvBQuJorh) [sell](https://solscan.io/tx/4g5BjWyz8LeAdYtKTsfU9G8Hh4XLEbXnQXzKSPCnCfzDt52HcvzVY4yJifxJNYLmMEVxUFevV5nRFSBJgqiBdoF7) [whale](https://solscan.io/tx/XSPYmr6CgM9iDX41LBS12N3SAnytcCbN7J9dnmjYEUiD7WVyyhqALfqWGhPQEYHLzJrj1RbHgkA5WaUiYNcJEgc) |
| 16 | 09:40:23 | [7AJSXi](https://gmgn.ai/sol/token/7AJSXiTym1b7kcg9rDGzqwnrd7vE4kksZbHshDBUpump) | 8.4% / 2.53 | +3 | Jito `9rkJMA` | time-limit 0.9 s | **-0.0204** | [buy](https://solscan.io/tx/h4FSgwWqiYfJjB9gn59gQjeXTCcT5RAB2GEdch5YLkjAFSFpBx6c7An3bGonUEz7u91a6FdcKaTD5YrxgrA2YPX) [sell](https://solscan.io/tx/5j49iua2xrnmxMXNmD4ws5tA5NRQgaDg3KhqMWtnpoCutr5i9ZALoYje5jAk8KDENWoNDMv2Y4a34v2GVHLkfpXS) [whale](https://solscan.io/tx/GWFMNL9iqvx4j4u2RXgBRdWcSgBrhsVhAZyvfWLaVcSEo7ZjAAFiN4f8kNRVST1YyR2iCGtgmtxLu6EYrRZCJ6G) |
| 17 | 09:44:18 | [34q91x](https://gmgn.ai/sol/token/34q91xj4hKYf6fqR7DTd29ipP49jDPnx7NjEU7rypump) | 5.3% / 3.25 | +6 | BAM `BSVckj` | take-profit 0.6 s | **+0.0315** | [buy](https://solscan.io/tx/3hfKvBUJWv3N1sx55SA9i1wq7LKWgMiubUV7SZpMtQtCneyz1VKC9GnrvdXYhLKMujvqsLoKLwhN3LxU5dVeK9wB) [sell](https://solscan.io/tx/2199RYjDF7bTva6MgfbKHjGpM1FwR2JZuru9bpxu3PqaUH6so9P4e8axK6DsaH31N4vduMxV1oZLt1HbBAo5tFDS) [whale](https://solscan.io/tx/5iLh6ASJWByPWPruRzZn6saD1ZbmW18NvMzvSiGAtkwRt2xw3an3f66vf4TWix9tmUyQ79aJFnVxteKBrobQgoDE) |
| 18 | 09:47:05 | [GKqghZ](https://gmgn.ai/sol/token/GKqghZAE98fsLy2wsbAiWygB1qGpW2JuVgb4UGBcpump) | 7.7% / 2.93 | +3 | Jito `EUcJwf` | time-limit 0.9 s | **-0.0059** | [buy](https://solscan.io/tx/2yGhqULchzscdhua7QkuZ3BpRFYDgrbYBqis1mzB4Bfdbxuo2UrDMX7fxChUF3iSZpMdZ7pdAb3S8mwa4bC6ek9v) [sell](https://solscan.io/tx/2fYJ1qNYEdzq6ERTzhCpVG8Yywzvbu9HUXg9MxcgztYDHyc7nGHmQpm7cqW3TsPJcTnQuKLtZost3GuAWCjeD4bz) [whale](https://solscan.io/tx/3h8SBmciokEkZQQgoVkD4ESMXRZzjRvzcvPpsJcvZdrco1vYng2HQnwZAdmnsd6SP225pKLZGhLL63ajzZZLx9xg) |
| 19 | 09:48:49 | [6KaJxA](https://gmgn.ai/sol/token/6KaJxARwrFyE9es32z9bRt131KBjeTdE69VBjuFpump) | 6.6% / 3.01 | +3 | BAM `KAoSp3` | time-limit 0.9 s | **+0.0060** | [buy](https://solscan.io/tx/3jQMTjY3nnbmk4i9jsiGbAKZqPTeD27swBZ8JQeHGYxwSp3iHmd2niZjLrmv5nia1AnhE9dS7CQushXz7bTvUPf9) [sell](https://solscan.io/tx/66tkAteBvZwLTdFqUNxTTrcqoTXvg253dtFkbb3YdMSR3z6wzAYMat6f22vPEAGhBGtXDgAJ7SQ2Y1CbntKED7mC) [whale](https://solscan.io/tx/8xDY7Huw2iC4GbbcbttZRhzJ7jjgrqeohKxKYxXV6o33tgKDdzzd7qd67A8bUHJhaJ7eUfLGhQuMMAAMTM3YrAd) |
| 20 | 09:49:31 | [2dBHbt](https://gmgn.ai/sol/token/2dBHbtm9Hc4wxbtHMov2qniCc2aWzNkwFrec5rZfpump) | 5.2% / 1.53 | +4 | Harmonic `A1vqhA` | time-limit 0.8 s | **-0.0069** | [buy](https://solscan.io/tx/59XS7zKaHb7i8c3yRetFcRQet7vuhFPQcPeQnwhr7HDzSR5brikANe3TRfHDLrkAEfvz9zFJxtj3VqxXr1GdQ3cW) [sell](https://solscan.io/tx/Hq1rR43dLWrquF7NP3LAb59ZE96fdN1aUiWWjTKVmxK5FAa2DKiUTiAgkitov41rjMyonXiUADasEiYN4UZnHCe) [whale](https://solscan.io/tx/d3wTAJiLtiw1x4dsoi8jfMbbr28gAoQP1vJbeGb1YU9Znk8CiQEUzZCgsf9AddS8yC4tn2SKCdUysMGJcDsXHPw) |

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 3209 |
| Inside the envelope (age / drop / since-buy / size) | 1522 |
| Picks (score above the threshold) | 40 |
| Skipped | far_leader 37, presend_armed 2, spacing 1 |
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
- ⚠️ 20 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getLatestBlockhash: 1 timeouts/transport errors (worst p99 87 ms)
- ⚠️ RPC bh-fallback getSlot: 1 timeouts/transport errors (worst p99 148 ms)
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)
- ℹ️ wallet change -0.0075 vs trades -0.0073: gap -0.0002 SOL — about the fees of the 40 pre-send tries never seen on our feed (up to 0.0002 SOL if they all landed and failed; inferred)
- ℹ️ Costs ate the margin: the price move averaged +3.8% per fill, but pump fees took ~2.5%, tips and priority ~1%, failed attempts ~0.5% (ops/strategies/presend/PROBE1_RESULTS.md).

Checks passed: every pre-send fill was closed by a sell; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Recommended / open:**

- Instant-bot proof: dense pre-senders (26–85 attempts per slot) on creator dumps; copying that on T2 loses (INSTANT_BOTS.md).
- Pre-send stays a shadow; speed fixes (dip14) first.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r16.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r16.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Pre-send (section 4b): the jsonl presend_live_* records (fills, closes, REALIZED, account closes, stops, end checks) and presend_attempt_land (try results, failed-try fees); the log's PRESEND LIVE lines when a run has no such records.
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

# Amsterdam run 19 — dip bot run report

*Pre-send live probe 3: 0.35 SOL, whale >= 6%, 8 tries per slot via helius-ps 30/s, exit 2 slots / TP 10% / SL 20%; normal bot IMIT1 (M2 shadow) (2 h)*

> **Verdict:** +0.886 SOL on the wallet balance (1.181 → 2.066). Pre-send PASSED its pre-set rule: 66 fills, 35 wins, realized +0.886, failed-try fees 0.068, net +0.818 SOL = +0.0124 per fill (pass line +0.004; 66 fills < the 80 asked). Live = 62% of the size-matched shadow (+0 ms row). The realistic replay, re-calibrated afterwards, reproduces it: +0.775 vs live +0.818 (live at the 58th percentile). Normal bot: 14 fired, 3 filled, +0.074 SOL.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.8863 SOL** (wallet 1.1809 → 2.0664, Δ +0.8855) |
| Started (PKT) | 2026-10-25 22:20:34 |
| Ended (PKT) | 2026-10-26 00:20:54 — time limit / max trades |
| Ran for | 2 h 00 min of 120 min planned |
| First / last buy (PKT) | 22:48:31 / 00:12:33 |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 14 → **3 filled**, 11 failed on the +5% guard |
| Fill rate | 21% |
| Wins / losses (fills) | 1 / 2 (win rate 33%) |
| Per filled buy | avg +0.0245, median -0.0058 SOL |
| Fills only / failed buys only | +0.0736 / -0.0056 SOL |
| Reactive bot / pre-send live | +0.0680 / +0.8183 SOL (pre-send: 66 fills, realized +0.8862, failed-attempt fees -0.0679, 35 wins; see section 4b) |
| Best / worst trade | 4xx2ME +0.1088 / Cse431 -0.0295 |
| Fill landing | median 71 ms after the dump (seen on our feed); 2 of 3 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip15 (dip14 + pre-send shutdown grace + empty-route refusal) |
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
| pre-send | LIVE: whale >= 6%, 8 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 100 fills / 0.1000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 120 min, loss cap 0.181 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 17**:

| Setting | AMS run 17 | AMS run 19 |
|---|---|---|
| engine build | dip13 (pre-send live + sell fan-out) | dip15 (dip14 + pre-send shutdown grace + empty-route refusal) |
| pre-send | LIVE: whale >= 6%, 8 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 30 fills / 0.0600 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% | LIVE: whale >= 6%, 8 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 100 fills / 0.1000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| limits | max 60 fills, 1 open at a time, 120 min, loss cap 0.221 SOL | max 60 fills, 1 open at a time, 120 min, loss cap 0.181 SOL |

- Probe 2 → probe 3: same settings (0.35 SOL, k 8, helius-ps 30/s), caps 100 fills / 0.1 SOL fees, 2 h at 22:20–00:20 PKT (owner: 'market looks active').
- Engine dip13 → dip15: the run now ends 20 s after the pre-send stop even if some tries never resolve (probe 2 hung); an empty pre-send route class is refused at start.

## 4. Timeline (PKT)
- **22:20:34** engine start #1 (session with 14 buys)
- **23:55:36** big win: 4xx2ME +0.1088 SOL (time-limit)
- **00:20:54** engine end #1: run end

## 4b. Pre-send live (pre-placed buys) — separate from the reactive bot
Buys pre-sent after a big whale buy, before any dump. **Not included in sections 5–11**, which cover only the reactive dip bot. Realized = the engine's PRESEND LIVE REALIZED records (chain txs of each buy and sell; the buy pays the token-account rent). Rent back = that rent returned when the engine closed each pre-send account after the exit (dip19+; before dip19 the sell closed it and the refund sat inside realized). Failed tries = fees of tries that landed and failed (6042 price, deadline, …). Net = realized + rent back − failed tries.

| Session | Started | Size / fill cap / fee cap | Tries sent | Fills | Wins | Realized | Rent back | Failed tries | Net | Stopped |
|---|---|---|---|---|---|---|---|---|---|---|
| #1 | 10-25 22:20 | 0.35 / 100 / 0.10 | 13,707 | 66 | 35 | +0.8862 | +0.0000 | -0.0679 | **+0.8183** | run_stopping |

**Try results (as seen on our feed):** 6042 11,699, deadline 1,258, unseen 343, ata_exists 210, buy_6005 87, ok 66.

Tries never seen on our feed: 343. If they landed and failed they cost up to 0.0018 SOL in fees that are **not** in the failed-try total above (5,120 lamports each; inferred, the engine does not see them).

**By exit reason:**

| Exit | Fills | Wins | Realized SOL | Per fill | Median hold |
|---|---|---|---|---|---|
| time-limit | 46 | 15 | -0.3480 | -0.0076 | 0.9 s |
| take-profit | 20 | 20 | +1.2342 | +0.0617 | 0.6 s |

**By leader type (the slot leader where the fill landed):**

| Leader type | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| Harmonic | 25 | 13 | +0.3324 | +0.0133 |
| BAM | 21 | 12 | +0.2039 | +0.0097 |
| Jito | 15 | 6 | +0.0118 | +0.0008 |
| Firedancer | 5 | 4 | +0.3381 | +0.0676 |

**By hour (PKT):**

| Hour | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| 10-25 22:00 | 7 | 5 | +0.1647 | +0.0235 |
| 10-25 23:00 | 48 | 25 | +0.5753 | +0.0120 |
| 10-26 00:00 | 11 | 5 | +0.1461 | +0.0133 |

**Best pre-send fills:** 9S2cxorf +0.1425 (Firedancer, take-profit); AsDx1ENs +0.1341 (Harmonic, take-profit); DoS68rqF +0.0916 (Firedancer, take-profit)

**Worst pre-send fills:** 2aWfy1Xb -0.0611 (Harmonic, time-limit); 4FNMdFWp -0.0423 (Harmonic, time-limit); 7QcyUCti -0.0378 (Harmonic, time-limit)

**End-of-run checks:**

- session #1: no END CHECK line in the log (engine before dip19)

**Every pre-send fill** (time = fill; whale = the trigger buy; P&L = realized, rent back not included):

| # | Time | Token | Whale % / SOL | Slots after whale | Leader | Exit | P&L SOL | Links |
|---|---|---|---|---|---|---|---|---|
| 1 | 22:22:51 | [ATUqNw](https://gmgn.ai/sol/token/ATUqNwz6twEN6CvdZh7azozmPCz2jxR2GVAu7Dpdpump) | 6.1% / 2.07 | +7 | BAM `76rcGH` | time-limit 0.8 s | **+0.0082** | [buy](https://solscan.io/tx/489tMEwSjz62pjBsXsejur6NCiLLN1yyycuGzJu83Ykt1N32mRvP8VScH2tGSBFnJoJzWKppzhATsyyCyb8skr2j) [sell](https://solscan.io/tx/5ZMZYC8hjqPvx6v6sXuJDLb7dvtXWN6oxH5u22h1dALjSDbfdAKVWuffwvRBKAtnuXTR1RhuqLQ4bNT9zpXyvq7a) [whale](https://solscan.io/tx/4eD3796gd5L1SDuy3RdZMEEDZB6wmMMPWnC7yTgJS6vJReRFTiT8BJ4fFoM3CtsPyW4Mab589YYehD5jJDSswFQo) |
| 2 | 22:23:55 | [4sDmUJ](https://gmgn.ai/sol/token/4sDmUJ992rVSnDYxEde2GtvHQGzzMrfmCaiwVHe9pump) | 7.4% / 4.44 | +2 | Firedancer `D2RV1q` | take-profit 1.3 s | **+0.0734** | [buy](https://solscan.io/tx/24kUprNipN4fbpxEZHnpre65MgFFTMzsdnvzwv8aRVDz9M1D4ZaQxnKKshteUTA3Wno47wfKLukSBVQ6fisLmbfQ) [sell](https://solscan.io/tx/3Z98Dxb9ZkYjqzVLpdoPLnkUJKeKpPAnSyKZeLzS3ShMRfJAR2vyzEy22JTaZjBNRY5jLgpR2FF5BvJZMfok9RZy) [whale](https://solscan.io/tx/UT2oV82pjMyNfW1Ffvpwoq4gjLWhaa6JuHpcM4msbqJREorYpwdy3qJsv58MKU3KCgoKvcYxwDSbF6fJgFdYRaN) |
| 3 | 22:36:05 | [AWdjwR](https://gmgn.ai/sol/token/AWdjwRVymSdwmFq4FkLtaRNtWCWbPvvaCqzv4tSHpump) | 7.1% / 2.47 | +8 | Harmonic `shftkx` | time-limit 0.9 s | **-0.0107** | [buy](https://solscan.io/tx/22MVw2ob7wTDF7gm2echDM4wqnMekvpyKRFpozBwVupdjoSeqXwifju3cnhsWxyDkBnzxJjQNgRJ3UD8Y9fFgEmA) [sell](https://solscan.io/tx/4LLSsxyGCzyQCCrTKxQwhjWtpjoqUhJuoLyS8NAcFPnhAaw2vRVPLAbVghrAoRnkyNARGsGJGZhX5sk8iP5nfNX3) [whale](https://solscan.io/tx/fiHSHbKyT3RJjBH9gkiucANNWK9JXWpNWbiEE6UAfJTC9EWkcuCAb5YS1Xqz2FMF8EBYj6aYZHqSgpyKqKqd95T) |
| 4 | 22:42:40 | [5a32ej](https://gmgn.ai/sol/token/5a32ejUNNQHc8GF9UMWcGz6eAvHSK5iQ2AZ9oykFTa7Z) | 6.8% / 2.96 | +2 | Harmonic `5ZqveV` | time-limit 0.8 s | **-0.0107** | [buy](https://solscan.io/tx/5YaJyTwQNmnqJeMoyNj3BFPtFaTmBVTVHH71yqvvGFtT8rR9VsPuRAHkiFMDq58Bn5QM4ZARWcymC9shUFTLuNRN) [sell](https://solscan.io/tx/41A7BHNLopJYMELeQonZWytqrwpyskk3fBUZ2sAYdGh263X49gq4HPWhfyyWUnpo28SUV1FYvESCaibj7QRnf8xM) [whale](https://solscan.io/tx/2vxy61Fmbe8yiqs1Wxh1DrYF3V9JTkaSYXGJkHT3CgdVfEjikXxXab8WyH5q74aRj5aPA9pvunKeL4UFP5ggSQcY) |
| 5 | 22:44:00 | [8ZYxN4](https://gmgn.ai/sol/token/8ZYxN4479gY48wA6i8fzkAggSCtvyhgbTvwyWA6epump) | 8.8% / 2.93 | +6 | BAM `5essVp` | time-limit 0.9 s | **+0.0172** | [buy](https://solscan.io/tx/41U9mXps8sNXfHwiRjrznpWNoEz1ohqTJFTF4h38mtqfdtbeNXLQQEJY49q98YM681JZqcvLAjNoHJD7b4JGRQN1) [sell](https://solscan.io/tx/3yBKfwJZk4vA8sM4r4Ea6YBaEZMgEuyaFcT3PY1AUcYJkePVCWbsemiSRkFEqw5yFrx8dDtFuXyENYFFsXMpbVka) [whale](https://solscan.io/tx/3ebHSpwkA9SVf9a3jdtZfniHHSVc1mxwqgXtB2rBrAX65QeAUXFsycKNb6LXDA3nJDgQaBBN3c6T7pqBWKKGWDaf) |
| 6 | 22:56:25 | [HeQnbt](https://gmgn.ai/sol/token/HeQnbtbnDfATj48uVCpmbWPemm3B3h5PsSRWSCp3pump) | 7.6% / 2.96 | +1 | BAM `5Cchr1` | take-profit 0.7 s | **+0.0331** | [buy](https://solscan.io/tx/3TvXCabvTwTc4fkcr88xypwqf5Rd7p9PDwy7p7B683rjYzm1Nm49pMVp6qKqRCXAkKkGYiDifjMuAAyw62mcePMj) [sell](https://solscan.io/tx/ern8HbMpBL8XH5V5LvunqgC44yE9cJGS4Ks3CCzDZvZiqTLBWiQF9PV28PfTzPQ8xq95E5dzohbMc9LQEyPSjEd) [whale](https://solscan.io/tx/ud7Q4EUaPgvtCidVaFzM6xWRJk2jZVCzymSPeJSdmw3F1W41E4GKhHdCNMSZ4ECvB1ziK2P5vMmE6BtkNAoWW6D) |
| 7 | 22:56:38 | [HeQnbt](https://gmgn.ai/sol/token/HeQnbtbnDfATj48uVCpmbWPemm3B3h5PsSRWSCp3pump) | 7.6% / 3.46 | +2 | Harmonic `CQdLgw` | take-profit 0.6 s | **+0.0541** | [buy](https://solscan.io/tx/5ZwkfeLqhcBJ7Sa9rTmQehuUm94yjkduSNEBA7ijdJ6wyhU3icjdci2db1wJGzKudpcp2YT49HKQsBPihY5uUSHd) [sell](https://solscan.io/tx/4w4qXsCgpwizMpk3jCyrBLaFupGeVN9Sqcqx4ZRb4JB3APFfLKiCGCjm2XxdFTByEtoECyeD4TGehWSEx4t1Ar8E) [whale](https://solscan.io/tx/2iBgSSTL8c3agEVqSsT6Fwk6aREzZSXMufF8K9hHagcM5qxxDcSMzTrvic3g4hAeHUrE9mHsM5tEjc4S1FeWt6E2) |
| 8 | 23:00:09 | [AED6vs](https://gmgn.ai/sol/token/AED6vsLNY3N1qaBJo9hkjaHwRxxQo6FvNDT6rDuDpump) | 6.9% / 3.46 | +3 | Jito `HEL1US` | take-profit 0.6 s | **+0.0568** | [buy](https://solscan.io/tx/2ACY8hqJVuZV6sjkR9DAqopFrGT7tf9Q4eT5nESHRGFXKrHpTSmdpdPg3ro2jywCGRAGR2UJs7nSaeahKwMkbXph) [sell](https://solscan.io/tx/53jG5Z36jffbHdzka6o3trzSAuS8VgyjBoM4JPwrN66ajkdMJnwvXsyYDkmGVpFNXxVY5prFuHStzbuxG64nVxRD) [whale](https://solscan.io/tx/3FhDHXf3PJH3Tb8tgAYknn6bjBmst1EmqVWtPRRscREJMdb1YdsJ5dvwnGBYFTh24Jsyrz1KDQWGfQDnV9J7sEVA) |
| 9 | 23:00:33 | [H52Skr](https://gmgn.ai/sol/token/H52SkriR1ytqAZCPNhxywv7dG3QoYBtSzJKXUdZUd4C3) | 6.8% / 2.96 | +6 | BAM `2X5yar` | take-profit 0.7 s | **+0.0341** | [buy](https://solscan.io/tx/4ztcEzfxEMAZ1icGmT8MmUNoKdbZtCJi5PQAqTTzHqq5JJLVHuyb2oomz7gGM9nHz9wZVMiNHEsDNSQ8qrGT766A) [sell](https://solscan.io/tx/SwKH2Pi8HLjHYAFVJEc5aYSXt1gr4NXdRTE3R2S8SYuxqwUt6vj7FhAk4X5NXQ8DDccPHYQDvgtJCwUwgUYVS82) [whale](https://solscan.io/tx/2akgbSB3Q21NtyJEeSsbjdmZ7L8YfsnjU5FXDMJSFkVctux2jnZVoAzSKxEQACkZMzRAXwhFTfQxe24xJksyZhsF) |
| 10 | 23:01:09 | [DoS68r](https://gmgn.ai/sol/token/DoS68rqFHyr7x81PjqCb387DKNN5AHe54KQQfbVx3A2L) | 6.8% / 2.96 | +7 | Jito `C8Bey3` | time-limit 0.9 s | **-0.0037** | [buy](https://solscan.io/tx/63wD4tnmqsWLQcsKSu1tZgMpnUB7MSHsvKeCKdMxhGmGcYag7LLfdyxda9joVF3yKS8zFHzG2QXKzjyYf2oWF5Z) [sell](https://solscan.io/tx/5L3tZkco6KphYwc7i8McbHXQEQqMFJxF8A47EoBpZNyrNmTPwZvyqy7BwcM6tRQpo22wfiRjqyFhPGg59EqMgYPR) [whale](https://solscan.io/tx/qX2XvAacZMQznX9YCPgnC7CrPpWC54BwXJj6UXqvffaa5CyKLN5Nii3zrJ4kQ5Tv5SDxoieTFDt2HXG32rQ53kM) |
| 11 | 23:01:15 | [DoS68r](https://gmgn.ai/sol/token/DoS68rqFHyr7x81PjqCb387DKNN5AHe54KQQfbVx3A2L) | 8.0% / 2.96 | +3 | Firedancer `EvnRmn` | take-profit 0.4 s | **+0.0916** | [buy](https://solscan.io/tx/5TLrGhurNCcWugHzSxxoqZGUHnqw1DrNcsoVc5HhBKy4sNRRQ5dJpEWoa57iDrrDdh1RDgdBi12gnFaTCsP1HvZU) [sell](https://solscan.io/tx/22pZQ8sbBSGhhrSZCWG9o4hE7V7NuNbKdkQvjTnr4zLiyeWCtWQy2eY7dcGFA2Bq6fzfxPnhxrRXrKkvGc5jQYHR) [whale](https://solscan.io/tx/3vCf9PDoUwZRS9K6KGVAiVZmDhN5zfYQ8pTeKm4dwufGJeKFStLMWHEYtMAqPdJ4mvEzkSbNVJuhP8GfwxbkX6z9) |
| 12 | 23:03:42 | [2aWfy1](https://gmgn.ai/sol/token/2aWfy1Xbb8CE5HiJdSHknuwJ4k9T4aa2poPp9qeapump) | 13.6% / 5.23 | +1 | Harmonic `HTeRsa` | time-limit 0.9 s | **-0.0611** | [buy](https://solscan.io/tx/479N5w9x5s97mwTHiMHBxNSL6gLEwxq8r4MU5UEAFaPiYyfZuESmikwroPZadTPAWwLPtEeVeUe1uMpdSrw1p5jN) [sell](https://solscan.io/tx/2vdWN1xkQWahAMXteDuPBYwqxsjN7yV56Yihwq6eBuNFMK5s3EkubJ3feAupRgPmT1pQgT4vWDrQhkEBoUu5xbhN) [whale](https://solscan.io/tx/58eYwq5fBcEV1SaQf6ypMMqbVcZUsS79nQkSem3LV3RjpQJjV9JUJyJSCf3qSwjUnsgan6oT2rwiVd1g5A71BuYX) |
| 13 | 23:04:46 | [5ahMWQ](https://gmgn.ai/sol/token/5ahMWQPA3r4j56gBR78ZoneGn8EykGJiaeXqpKRdpump) | 6.3% / 2.07 | +9 | BAM `2GUnfx` | time-limit 0.9 s | **-0.0172** | [buy](https://solscan.io/tx/J5rGPx5fyRmm2TSGdxHkGzbHTGpp8gK72rmchL8Gh47bL6TkpXeNcHkE9Ku5uBqzQECNf6aQiAGD7JGNsV8nBao) [sell](https://solscan.io/tx/3fxU2eVBkLo3Rpnwpexi4xSYCA4rEiHa7CbXNdaDiYhq7hQ7dZQzfWTyPUEY5mypXjWqJpQwLTaGD1RMEUz1ES8E) [whale](https://solscan.io/tx/vub8gs3dTo8R1JdfjcWcshxbwWvgiarhKCTjwqu175VNDnwnynqqdKP9QHMiCj7MvZN5qhXY58MWyutBLSMBoZd) |
| 14 | 23:05:55 | [3xwPhe](https://gmgn.ai/sol/token/3xwPheF6jwpmj2Y4FAewEE5nkCadsxTpNoAkxdfcpump) | 8.6% / 2.96 | +2 | Harmonic `CQdLgw` | time-limit 1.1 s | **+0.0147** | [buy](https://solscan.io/tx/3zd1wTxXNKCKtgtynDum81V3FKVPgn9DWWxaJATBWGaKrp4jnbJtGrTmpCBQXEqaxuQrTAnGzD2bKV1pYh9g3m3h) [sell](https://solscan.io/tx/5NrnKzEYYoVTP4VH1P8jkFiEn1dqR5oDoqo1oai18aDd8wow1QCH4ib9srTbnBmUtkAPNzkPqLijTn5ymHTw6xXR) [whale](https://solscan.io/tx/dkST45zsvxhDrt2ePfcSmV2AJupU6G7RPPcE4z53QQ6Zk5piz2AorYp37EwY9Dp38mkn9VEYU1TGfZ8KERwCQBo) |
| 15 | 23:09:18 | [9S2cxo](https://gmgn.ai/sol/token/9S2cxorfzsjSUQyGzXkbSvELTioDzPdSyu5acrgweEHo) | 6.5% / 2.96 | +1 | Firedancer `4SNKY7` | take-profit 0.6 s | **+0.1425** | [buy](https://solscan.io/tx/mG3Vpscy98XguhZg2dUyrkaoW7GUWBq2kHchwCF8VM8mfApyTJBwd2D65M6UiySuv8eLCgbpVzf2357qdHQJXy9) [sell](https://solscan.io/tx/3r7rFbohhvYVkNc9Jy3otgxRQrwXhrwg7EjU4h7mD1RZEgc43py1HptJEXaAUG9iVUWiGZ6LBNCLXXhWMhC21Pqf) [whale](https://solscan.io/tx/28JT3juvYLmMuCrNJQ8UMu7t1Tcktuo6FkfuUZTQSKXjnwBa2Xbq7opgMLfHRS6QYjRftEuPB31UHsRZyGLVAt1G) |
| 16 | 23:09:32 | [B6FuKe](https://gmgn.ai/sol/token/B6FuKeFK9Txs1pcy9gYBUK9DKFFuL8i1PFzDfScpeH3B) | 7.7% / 2.79 | +4 | BAM `A4hyMd` | take-profit 0.5 s | **+0.0491** | [buy](https://solscan.io/tx/41jtKt41JXcY3YYR7x88bCYucZGwgi3UcFA9XXFYhBq4c5b6LWryRznFSk5szPwNUPiUUoyLHFSdmNiHDYihVhEu) [sell](https://solscan.io/tx/5JajmPo6C8nHy916ZQd2aKeFAtuVgMCDgUoTsEXNu2CpGAv7Sv2e8jiAAXNrHeR4bfRtWoz49HKgde5nztkouWDT) [whale](https://solscan.io/tx/KdMxdsTx9C2Vn57yb82rajBUekcmsmyG2WxC2egsUdaiSPZSV1mJWwSwqxkLCHZ4w6LUj1AxPJBTu68W9setfxv) |
| 17 | 23:11:09 | [8t1bt2](https://gmgn.ai/sol/token/8t1bt2zNKHbxjxbDinkSZxN61qB4bBdx9VyhC6Gspump) | 6.2% / 3.25 | +3 | Harmonic `HTeRsa` | time-limit 0.9 s | **-0.0376** | [buy](https://solscan.io/tx/4r4eKHz7H9eSKxg4eaZkpvSMqLfc4Fs9Cgj51MUeq6brAsTqaTSky8x3vKWH8bqFb447CSLcyzLNEAJXhz7iQhUX) [sell](https://solscan.io/tx/DaYM7zgCz2jc3qbYy7DEV8KcbAWiiKvTexbHFbjRipZTfjvwzmuwGGY4fhdrvp9kDCxcqpmZZcD2J8S4n31aPu7) [whale](https://solscan.io/tx/5V8R1ucpHtMUYrcvDhePpCnMAX4rJ8XcGuxH86kzsCs4M2kwLpejnkajUqamzgq4hfnjYLFbCoLxm7L11qgpvLHg) |
| 18 | 23:13:56 | [7iQWvs](https://gmgn.ai/sol/token/7iQWvsRz1LyhbZxy6RNqAB7L1gHXWrXLFsgxhYE3pump) | 6.2% / 2.93 | +9 | Jito `Chorus` | take-profit 0.6 s | **+0.0391** | [buy](https://solscan.io/tx/4EM4oSc97EBaByo6jfSnDfsjb7L9T854ncoRdnpijbbDfAQcErzbyRkz16Lhzgih6Ht4YPaqukCGCP8rtcrPHCy9) [sell](https://solscan.io/tx/5VMngHu2E8fV5QPfc8z2JLvQ5qtuDC7cDanVq9JceBgRnfPEboYEmUbjycW1LwNtosrXBB6HyqNJjVeaeTqoAyNW) [whale](https://solscan.io/tx/29VrTwKSXUscoqXd4Y3gYwVn4tmx3TS8esicsGjsWVR8yEM68FnpdDeTvwRAwahUDRvhHVnqFRRkDCZm5Mkb6tPS) |
| 19 | 23:15:07 | [ALK8QL](https://gmgn.ai/sol/token/ALK8QLitAR3wrrLgGD8K8bUgWU3Y3EV1fWqxh9uEpump) | 6.5% / 2.96 | +4 | Harmonic `JUPiTE` | take-profit 0.6 s | **+0.0542** | [buy](https://solscan.io/tx/LpJCfPkXrYKWBKuXNcXJdHscDQcB5VdbJMb2KzDKmxJcumkyAZpoPjEwfo7UtjZAfbinXcLBtu8QUEfH8TegnwF) [sell](https://solscan.io/tx/2WjfKDddiTMVcqLH8tJCxYQCxT5kammmDwfjUai98ozGBcLDJoX5eK4zZBDzvR1mhibGfwjt9yxEAp3qVr4TyLkT) [whale](https://solscan.io/tx/xBogzdmdeen2d9jygx1LY8FtkezQ9xmxJe1dHMwW7s7W8Nrnn5Fo5eyJDQ2f3UonpUS2BZ6CixyUu1WYfPtunH2) |
| 20 | 23:16:35 | [3cD6bx](https://gmgn.ai/sol/token/3cD6bxkrj64R23tcXkeNBiNDuyUNoWRg2K2XaEgRELAY) | 7.1% / 2.93 | +2 | Jito `capyS1` | time-limit 0.8 s | **-0.0188** | [buy](https://solscan.io/tx/3T5cjX2P6MVvhAaZA1C6kfT7AQvKQhZ6xSsge1FjphkN8LHjXNeRLnPxqip6CJofnhpToUKwNVHAkyWPgPwe8pAx) [sell](https://solscan.io/tx/3DiAvkx2aPypFtVPANQU41rzCigopzDG9Q4vUVxDFKn4odMA3EXB4hVXtwGocnNH6tTdqzwuhpQTwMEcGXs4ZJ6B) [whale](https://solscan.io/tx/4fAkfJgkKk6NEDRLGqjv7XAZm9R165ZbL2Lk6tb7wceKCtxHUBtg3GGUB27dRYM1zX47mV6mth8spX3s2nzZEnQQ) |
| 21 | 23:21:27 | [FExD3Q](https://gmgn.ai/sol/token/FExD3QFqFndXwBUJ7wA7nFZMF3292bF6CGFbiANSpump) | 6.2% / 3.46 | +3 | Harmonic `Fd7btg` | time-limit 0.9 s | **-0.0107** | [buy](https://solscan.io/tx/547A7wj4NFFLN4L57Ctxpp1wv3Ep9y5NxCp5DxxiRA4BMgp4r5gbdGAYqkEsVh9QEDv7SiBsBV5UrGbr7JbwiLh4) [sell](https://solscan.io/tx/46SELgEAq68Wg9FEXNAcD2f8YK1buokdvAJCXJXEKXcfcSxGxnA8VpJmUXeVpE2HYsPfDeX3Cdc1XUkWWYXHqSY2) [whale](https://solscan.io/tx/55LjYM3rDCfn4qBoayXKSVuP6pBTwxrhiYS4i1G97JAJHkvwYEaWbXQT5BBn2anXWdB82uCWhe2mJt326QbfwjHh) |
| 22 | 23:24:28 | [67fn6X](https://gmgn.ai/sol/token/67fn6Xpx5VynWVAeGMqE9QX6EasHmbq7sKrCPEkxpump) | 7.3% / 3.25 | +7 | Harmonic `BtsmiE` | take-profit 0.7 s | **+0.0391** | [buy](https://solscan.io/tx/2rSM9Lgre5WJKwG6W2fE9n4SR4aRRYLfFzFViTEXVj4Ntrg2koe2tojFQ4T3yrBJU7uWiUzDjaPniZrMDdHXBHZS) [sell](https://solscan.io/tx/5gErw7btLQmQFnQXPBttEsqmyJW1uBBaDwWonA9K4ckPKmsGydivGEPv6BZ5NtU6jqKbcoW9aYQ3Gw2YnZfMbuyx) [whale](https://solscan.io/tx/2QfjpSLiM4WZecUdWL85XpD5unudHCvNLV1X3fFkvth7SktBzdcmoF3HbB7GY4WLyPwkefJLe3cxxEbaJEvGadTW) |
| 23 | 23:24:43 | [BdmDSn](https://gmgn.ai/sol/token/BdmDSnTuKFjqreVMJFju4347jMUYw1vAq3sAasfqpump) | 6.9% / 3.46 | +8 | BAM `fhsM2s` | time-limit 0.9 s | **+0.0114** | [buy](https://solscan.io/tx/2UNvnF39s5o7voTuUavNKx3Ty9TXeu9w7BB4N81mGEgtGLvA6h3YvnRbboDsp6khYhbveUwJ9Dfrz1xD2XjvgvgG) [sell](https://solscan.io/tx/tgNHQeLmWiEwadmXWutwqg95pncgtkqGM2uBwJfsjWG2cECYEbrDgFhSeWsAWCqM5ACTCt6MsEdNvMpnS2eg5tT) [whale](https://solscan.io/tx/g5TDrP8fjofgQQq1ps2SKwnVR6vofB4ph9ULWWUrf89y37rDKQ6aR9GPDa62NbpEwhnu6oGfFqBxsZfGCfjVQX6) |
| 24 | 23:25:27 | [BdmDSn](https://gmgn.ai/sol/token/BdmDSnTuKFjqreVMJFju4347jMUYw1vAq3sAasfqpump) | 6.4% / 2.47 | +1 | Harmonic `Awes4T` | time-limit 1.0 s | **-0.0102** | [buy](https://solscan.io/tx/3iBUkSy48NVdAaaLj8FAsqpp6JjdFVMgaoGs3sVzkFB5iHbqS6QFobbyVLDyECFrsCe7WPWGgc1Tjb5sgGSs9ckS) [sell](https://solscan.io/tx/3MEsftYCC9xSyGU1XcZqBZ7DRZMntPVGy47muRFPyQnZUrsy4Tz1WGttMXykjUHDFGbvLWAb6Dr7cqt5jbnXJ5Ut) [whale](https://solscan.io/tx/2TcTgph6EPSUBTFemTGFQx9iuJHzKfDhArC6v493c3RbXkPU3Lekus771kQZgd7VE94K2kE9f3ubRNTr28ityR4q) |
| 25 | 23:29:53 | [DtDSoP](https://gmgn.ai/sol/token/DtDSoPN3XYbXM12R47ccmt2brQY7s1rFqoFyYPKepump) | 6.5% / 3.95 | +2 | Harmonic `JUPiTE` | time-limit 0.9 s | **+0.0015** | [buy](https://solscan.io/tx/1HPdi82GZFJkAcPKFhnpKTZa4DCziwAPCdR7vCk7Jkrjho239mBVMuRocq9hD93sT5ABpZzXs61Qew2jjBjerqT) [sell](https://solscan.io/tx/34cn7Ycq3GSKwbGCAEkZDXp6Tu6HFoQwqaesQFPp9aMGhgHZZwoFNUC4BD13UdJs5XDFf9Piw3b3JapFREPgRWyG) [whale](https://solscan.io/tx/514KndjmdbhsLDPdZbRYEpeBcwNv91kAwYCa5aGm3Lsmo6aNVEBBDangWfvSsHYkthLezR3Zz8yny7qnYGiy1E4j) |
| 26 | 23:31:02 | [2za8US](https://gmgn.ai/sol/token/2za8USX7xh2CTXnvkVpbt3bgnBhPHMsJJDyFBWDrPFSC) | 7.3% / 2.96 | +2 | BAM `DRpbCB` | time-limit 0.8 s | **-0.0109** | [buy](https://solscan.io/tx/5nFkLJiRtF1oUd1XkUg1FZe9h9p5azbwybznezembopvXvZyS5rB5Y1ctEwcpDoKAuya9UZ9hpMGEPSK1JTfFaBJ) [sell](https://solscan.io/tx/39SFVKgpka8UXessyrHazoJ6dCfpgFyC7JeEvXPNy5rEPiYnKakepKFsytpmipqom5Pn8fLDgjoyALE2sravwthp) [whale](https://solscan.io/tx/4Zi9bgNWSP5wP25z25hBhp2ESVctwL1ycdbzCafME2DL7ttPfpos5QcfT8WkLr5CcAb5se7FFZRUJQ17FZX7ZxrE) |
| 27 | 23:31:05 | [FrjRkx](https://gmgn.ai/sol/token/FrjRkxqagTzUsYuQaWQhX5aoytCNukBByamVwTnrpump) | 17.1% / 5.93 | +2 | Firedancer `EvnRmn` | time-limit 0.8 s | **-0.0107** | [buy](https://solscan.io/tx/3wUvNzYy5UwjZHERiHRTjjNtxAEeVCWukvt9FvB1wnmtGF5mnvEGDE7uinexTeH7Ve4cwLoX2bWxpULAWcw6Tb4w) [sell](https://solscan.io/tx/5vhAek3hwAeoa9KTuMtgaRqUgRLu6dF5qabhuLDUQEo52bvo5nLbCk5vVmJJMkec7s2P3Nhh1PzAAYq1aaHNHDDE) [whale](https://solscan.io/tx/5gL5eWDB9Q6xB26LQGurchyfX6AWxSN6rAgP8LZ7tDtmFb1ZDTjdSdK9XrANDTCg78L1EwsMKZ9CytPDRuUnzUMV) |
| 28 | 23:33:45 | [DgQwJw](https://gmgn.ai/sol/token/DgQwJwxGCMj4pXSNRPJm8asfZotV1kZPqvWCddMocqKD) | 6.8% / 2.96 | +7 | Jito `bitHUm` | time-limit 1.0 s | **-0.0259** | [buy](https://solscan.io/tx/2DhxhuaPUwaCa8DoUAboVsNaoMFLKuy7LK3EYQtMMnHuNxP3vdd2PqVq7kdW48dgj4srEN4bQ5dMspoamd6zkdeq) [sell](https://solscan.io/tx/5YASUeBcHQ4XMpeto78HTNkKMqHYd1QZWQjbcAYVpdgX1mVQYASJaJJ1TdV9v2awHZY5T1hQ9J73Ec4tyvZvcTQi) [whale](https://solscan.io/tx/yPyPm563YDecWRFcQwTWkZ5iWRMUB4CwbTBiSYwqWZtZpVVacjrCufvtzt3G9ggAynyKMi7LZYuLRksbmSCLRs8) |
| 29 | 23:34:10 | [4FNMdF](https://gmgn.ai/sol/token/4FNMdFWpdJwUSFUPTKoVAJipx8J9XK9weC9R7wvrpump) | 6.5% / 2.47 | +2 | Harmonic `GZ4U21` | time-limit 0.9 s | **-0.0423** | [buy](https://solscan.io/tx/2geq2ZrF9V5dy66ZQbxfFtsN12A9DwjwAg4zZndrz8ptiPs1Au6gTPgmmVFThraXD9BnKcXoMLvPBb14zJ8WvPWf) [sell](https://solscan.io/tx/BhCPFokd9DoGU7kLwLQBi69LVaEjMSh8dJKY1k8hDmzjmQDABqzKwbfV4evnVubK6EgF5sfv8KUcKQhGtP3XAXm) [whale](https://solscan.io/tx/5bpJPqa2z2x5gbZQX5ZdhMMW6eq1uu7MFxDyKUxQpBLgYvevz5vEZCvpa5MS8XwxkAsCeQyYybtQWmF8pkcZg4ia) |
| 30 | 23:34:16 | [DgQwJw](https://gmgn.ai/sol/token/DgQwJwxGCMj4pXSNRPJm8asfZotV1kZPqvWCddMocqKD) | 6.5% / 1.98 | +9 | BAM `Fc6NNd` | time-limit 1.3 s | **-0.0107** | [buy](https://solscan.io/tx/339xFMT8HGuSXYkxbPAnyMsd4N3YqQjcMJUnUdSH5ps8MbqQ1desjgdgkW71mgoTwcFwFqonzcePw4unHsDjRwza) [sell](https://solscan.io/tx/5T3BxdbQK9qJVU5bnKUsDZrjDjSCJL1j6WYvCx4CVrBw7HHRg3L7zCeQapbvrRB2WQfQ7rjpQtnQF4FFDowMsCd6) [whale](https://solscan.io/tx/2oTdPpZ1L3o43nqWz9BVi44odaytHVTTRtfkZBo4TzBx1QtMsvA5W4qGoDf2Lfc2rCKZeJRqEpY5fERqCMEQuwhk) |
| 31 | 23:34:52 | [9DNrAR](https://gmgn.ai/sol/token/9DNrARJCS8m21au8VKm5eHVoBKjgzPf8eMMpdE94pump) | 6.1% / 2.96 | +2 | BAM `Frog1F` | time-limit 1.0 s | **+0.0024** | [buy](https://solscan.io/tx/5nwh3SuF2ekyX1GuVmSibvw5DxRJ3SJtjdYBXE9YKxoJBTYezTWWA19Ye7xZXXj5dygncckvBrhoc4uyrj73SQTT) [sell](https://solscan.io/tx/42GyrhjwVVaRYKwYceoQkid8Q6KVQSbRWPkFCUyFja3rWTw1X5pjxQnEKM1MHucQ2Gxz1UEKxyiH8pVFN8s6DjQz) [whale](https://solscan.io/tx/2oc5nqZGPxf2b1A4AyZ8dja9UFWEVxQ1S48QGPt3MqRwC4rmuk8zMPdmWhwqpqYLPU8TaecKnvLaUcpRLkdZLiGh) |
| 32 | 23:38:46 | [4moGrw](https://gmgn.ai/sol/token/4moGrwmPUWX2AmdUBAzPeqfVCNi8h1Go8j9Xa5J8pump) | 13.4% / 5.93 | +2 | Firedancer `DNVZMS` | take-profit 0.5 s | **+0.0413** | [buy](https://solscan.io/tx/2LubVYAM1WHZXWWtiCTVXV945zpBK26WrHg4dLi627E1x9Eai1jCEHwX7CFqNKhkXZT8VktRhAMLeUwdJwBt2GZM) [sell](https://solscan.io/tx/36UGZbfeDGhX2mSEYHXiaBuwRkdqP4DkRKLpFHfsGpDzgGZychH5Rj1Dd9eZRcUGNiYzq6uSwwtyihCcqu8WZvBe) [whale](https://solscan.io/tx/2g5CDLuLeDSToc2UJCG7nXmtJR7Q1tb9qfxHe3xMk9937gzEKcwLrabPWpZx5pfPFCdw4CJrC9MqA7txFXF443py) |
| 33 | 23:39:57 | [8iz8hv](https://gmgn.ai/sol/token/8iz8hvmiwJJCtU5RrUeUzUgwYUKAzNFBUhpNJWujpump) | 26.6% / 24.69 | +1 | Harmonic `BtsmiE` | take-profit 0.5 s | **+0.0548** | [buy](https://solscan.io/tx/5bnrUxhTy7FVLrxryVsmdzzYKGdy8vwtxmeHjGnQYzwkGBX3GzB8GQftP4M7VFDiRsDRuSYQD8EqQr1Y6s47itra) [sell](https://solscan.io/tx/5b1F3988E7FzjTbkyqtQZjCL9WXSdnK9MuEATyc37j2bwVzez5z3LfodVcepQf2TAJF7hmMaQMAV9Z3NoiF2hLh2) [whale](https://solscan.io/tx/Qq82FSGzM5B5ZVKKnAzJHBAbg7Fhoe6AtctcWGxYshY8tfYL8BK4AHJ4AF1YFE9BdkiF8pvQERTViK2S3eWg3SG) |
| 34 | 23:39:59 | [8D1hW9](https://gmgn.ai/sol/token/8D1hW9MbuxZuTm5hQmpCGpciEcM61THyPbgHNgUepump) | 6.2% / 4.94 | +6 | BAM `Aw5wEM` | time-limit 1.4 s | **-0.0116** | [buy](https://solscan.io/tx/3Ma3eEeBGZ33NeVxMBAp4umkEhRgGrzs1k8qrgZYyqZgkrBYiV9dEkieG4t9nvkrKrdktGWK4SvHvTbJYYyWfMrb) [sell](https://solscan.io/tx/2PYHhLsBLdhFP5Njd9dFgg1VnwzbiZsKTHjDDhcCMnqACjPUAr4jN71xLKEbR454DTzzC7wZq6wbR7oYnKtukZao) [whale](https://solscan.io/tx/nPsoNSWtQ9tHufWDCbDZLsuFFGN6fUYgcg66WtV187e9S4nzr2aFguTHo8xcJQEoPnSunPXpEXEyAZ13yxiEYHT) |
| 35 | 23:40:13 | [4cLNRh](https://gmgn.ai/sol/token/4cLNRhXrhgP911BUmZsBNtMdCLPn6W9xghTT1yBUC7GJ) | 7.1% / 2.96 | +11 | BAM `DRpbCB` | time-limit 0.8 s | **-0.0253** | [buy](https://solscan.io/tx/25VkkMyf35ecFcBW9U1FQVCSBpmERmGGrT21wdJTAUCHFP4Pa1NQ93am7y8YqSQvjK1Q5p5iLFtPTHArtSZRCmbn) [sell](https://solscan.io/tx/2TNwkzTKz5ugo1mtzPcuZpg5WMwsk3Ej9F7o9ZMcafmJyTCjHVYXAwta17YhK2URfeWtpAEQHqyZbfmcLLndLLpT) [whale](https://solscan.io/tx/2nrk1kTQPKww81vmjoJ27jbCeuV1ozgPEWjitdPF5yypE5BbnJUUooWVvGMvcAnmuXb9vpkso1PZHDRYdQsS8UjN) |
| 36 | 23:40:20 | [8Km82u](https://gmgn.ai/sol/token/8Km82u8C8pX1pjTmEbtahwgBbSc1qaoFdKfmcDKJZYDn) | 7.6% / 2.96 | +7 | Harmonic `FBKFWa` | take-profit 0.6 s | **+0.0398** | [buy](https://solscan.io/tx/35eS44xc8xQzRQTeqdXH1u5FZD3G18UvLajMpzw3qVDHvnjqnrrVCNMgUbMKvyGLVQzHQagZNnRn8BUAdmwFS1se) [sell](https://solscan.io/tx/2JH5iF4Dj5JVhCjwPpEDipJqe5ubC1byk4A6kztQi7GBzNBskNEdSbYTW8oK3H2RhbLoXEscNqwAmQ9S5YSkWen9) [whale](https://solscan.io/tx/SbraNyo5gPUT2vkkf8uaC8RLBSPcSuq2b5UJHG5gNWY98V1v6WujYjAHz6MC7mJwAhkzV2Jkey8u22WnRWSQ6M9) |
| 37 | 23:41:02 | [9fdp4o](https://gmgn.ai/sol/token/9fdp4omcJoRycUArgAmfnZ2Am5vRq72C85yJzvfypump) | 35.6% / 17.78 | +0 | Harmonic `FNKgX9` | time-limit 0.8 s | **+0.0098** | [buy](https://solscan.io/tx/3JSS5dZjNPmA3qHPRxzg4B5AzQQXyKF4aZbKdMdErao1fMZ4hGp6X9Ya7tDVsdxDAbCxfZ9AFAjvWa1XC3CQHk6B) [sell](https://solscan.io/tx/38Pw3fwsUdadhoVoQbCWvfjG7AYQNboaVe7XKSgtVxLt2yggS7FYERj4BKdvDg3gR81ETBvKggitoE6cetDUVHE6) [whale](https://solscan.io/tx/5juYr2pAwkiC4Vjymchz6MzvYP9MopFi4MJL5sMKsNLFDnXxLaYNfYAPKHjBT7VFihPc8wb2jj9ucrM7qbdxUVwq) |
| 38 | 23:41:31 | [38aswv](https://gmgn.ai/sol/token/38aswv17Rtur9PMKuX3hzrGaXQrhYMfaXwVKqm6Kpump) | 11.8% / 5.19 | +7 | Harmonic `juigBT` | time-limit 0.9 s | **-0.0070** | [buy](https://solscan.io/tx/3QAgUBUb7KdKHfJdVr4WPRgRwjW5EQh93wG6cwYPhBwXjMnYF92AzTYTX5efTnRAkXZ3uA2fvwiWoVhP19h5saKy) [sell](https://solscan.io/tx/3bD5zX7v2UTUNe77oVi9Bh71F1CrxtD7cMpj7MJkMLaDS3MbeZ9RRm7QigGZKCWuTamgnoCHdU8nUDvykTxUs5eo) [whale](https://solscan.io/tx/3edbM6UoDP27mohNCkWwVhTcD2hhcdGxuXEusZQBVBXoBeWB3wiWoVMzbyB4fifC6L4uRC2LL2kZMecDJBfgjtPT) |
| 39 | 23:42:33 | [5Qbrmd](https://gmgn.ai/sol/token/5QbrmdqWwUmS9n8kXd7ixrERtcry4Kw1jHB1KHg1pump) | 12.7% / 4.44 | +3 | Jito `5pPRHn` | time-limit 1.1 s | **+0.0141** | [buy](https://solscan.io/tx/2Eu7hFNrj3xs16hwvkHJfDeuMCskEZYj1vqme7aDC2fKMzKdWGjhLAEAxxMnXYyCcYivXSFtbFrgq1WV5dRV5pEK) [sell](https://solscan.io/tx/5AXbWRPvxSbxuqWT3d3quhaaKVX3LwGbNU4reJBcHmDiFb6qNZ49rv4H2v8gcGBtLCZJRS8CHN5oEEQj7bxSwbFp) [whale](https://solscan.io/tx/42WxMgLDQcanGBRpC54GQZxKVxMZSPpZfMJaXxo9dD8P9aKRzTY4jmc4cZFiXTd4yV8A1777izR9EFG8TUV8yVp1) |
| 40 | 23:44:19 | [4WMJKw](https://gmgn.ai/sol/token/4WMJKwxHkNu9qGJyYApU8dTJLgxCiEM67BJWaynkpump) | 6.9% / 2.79 | +8 | BAM `BSVckj` | time-limit 0.8 s | **+0.0021** | [buy](https://solscan.io/tx/4gujsG4ej8FxQmgBMjXhY4ruyhHXt1fLBDahYGyNKtHpq1AwSY87KwNjqhyRKDTWm7N8hA7xjn4vxS2QrDW1HUPg) [sell](https://solscan.io/tx/WvqrN9YqkXzAs4WSZww9wQqSzBsHGxaxz3bFyXMQatU1dtrRSmnsB434Jgr7xYUE6jczW5TFkfGobEb3PTCobWM) [whale](https://solscan.io/tx/3LiTyYQ5aLsrNtaiLcnWphiK13zWUjknW8VAXi1Lkon6GzpffwvVC1MUCSWtaVWVfAzsLPefMpCb2c9oEWk9Wc2z) |
| 41 | 23:45:24 | [9CfDMr](https://gmgn.ai/sol/token/9CfDMr9hAGeC8VCb7zuUK2U8873tjcPHEwU1sPCQpump) | 6.6% / 2.00 | +5 | Harmonic `Fd7btg` | time-limit 0.8 s | **-0.0111** | [buy](https://solscan.io/tx/59icoHVEUQuXo8rgGCZVUMuPFnazR5bgY2YU9HYQNdXtv4MUWMC3WkXg6pQojyccSyKycAS5FEScoaguhM8B4SY8) [sell](https://solscan.io/tx/TE1wH3dTvd6Z1NWc8ct8UwQmoks1cnv1rdjNBfNEQ2f2W1deppvwo3HcPnEkkTuj5YfQUDXYeXUWF5ygJZsGq1A) [whale](https://solscan.io/tx/bwBdCqtDeVBPgNuj82rf8tcuFy3cWAyeuHvKwSxsizxjUzJKGJJTEU4PAEthP5Pcejkj8qifYriLRhtYUjfXRqy) |
| 42 | 23:46:01 | [2kb7TF](https://gmgn.ai/sol/token/2kb7TFEtajchAveCEkCZcYqJNzUZ2zGA1Vm856wbpump) | 8.7% / 2.93 | +6 | Harmonic `Ex1AxF` | take-profit 0.5 s | **+0.0445** | [buy](https://solscan.io/tx/5SiezwWx4hAX1ZKmeiAsL49ZD73MWhy4jPYwP3ZBSewXipkLk1hatzJR7s44DFzaivxn5HnJHx8KwY71mFKxn8DQ) [sell](https://solscan.io/tx/ghkvnzFZfFoojM4cX6tY7cP3CaBCeUGELRBX6eEhPcfy1JSsyKAZAFB9aY5T5HQv6N1sSmPiW8dpAbjCgXZYbBd) [whale](https://solscan.io/tx/goNsgNYzoEqujMGkj86bqQLPHkg4yxUpPCKBAkqJDcrsv2dmjSRb5hNy7iDWwH8dGeNgpG1rFrKFGfD3ECm17ZK) |
| 43 | 23:49:44 | [HWpTfv](https://gmgn.ai/sol/token/HWpTfvsPcYtdfpPvzR4j2EWyZNAmHin58AersFU5pump) | 6.0% / 2.82 | +6 | Jito `C8Bey3` | time-limit 0.8 s | **+0.0206** | [buy](https://solscan.io/tx/3cSHbRi5GoAztjDD8Xm6MAr1k9xGMHyLG1ywcT7TbNWZhqVYB4YHD2WjWWoX6NaQcvZX99764oRnuRbFr5zvnAQJ) [sell](https://solscan.io/tx/2J7UeXntZggoF8ctFa32NFB4y1cfEw61Kw8oQLfHLqUB3eyqtp1w9P7pwE4nxkRS8AvHf2eXfG3NReQRrHMyGvMm) [whale](https://solscan.io/tx/5EjHc2UkisDN28yX9dTxDirA8GNWxbpJVMCw6i32wesDo5E9b4X9X7AotAzHSk9nPhYvTSFJrbbsXgFUfTAXScrM) |
| 44 | 23:50:46 | [65VRR8](https://gmgn.ai/sol/token/65VRR8w3VzGWcx1oLBF2QEET5iyMoFDdu1p6ev6Upump) | 6.9% / 2.47 | +2 | Jito `HEL1US` | time-limit 1.1 s | **-0.0236** | [buy](https://solscan.io/tx/4obdjtiBMQBfN3keBgfSHjsnweBZmTR8MU352xGm6XUGhSUZC3KDWKDVkzB7iYMZ4LnqCH5g447D4WnHscMBpjSw) [sell](https://solscan.io/tx/2NskadVZ5wxMQxACE6hX9XHtBdeaYyBkpRTB3J7YWUiYzTskBiY1ceBmgwBuNXrkN9dXY9onJSZNRy5oj47VNTXE) [whale](https://solscan.io/tx/49LEFu4nUa2E2ydbAmNEQ4fXb3XRgzBoXixTvdrLKDXsh9LtFU2GBGGVRsEvKUGyKoverb4kfLjyziR8pMJUauyC) |
| 45 | 23:50:47 | [DukuN6](https://gmgn.ai/sol/token/DukuN6bhqDZMmBwRgUEiJwiM8a5B8EiKN4CvRAdiet3Z) | 6.1% / 2.96 | +2 | Jito `ReFiqM` | time-limit 1.0 s | **-0.0107** | [buy](https://solscan.io/tx/3Gfu5qugUNL2PHsFxTMUgdsaCSEcLK2FfQJa751vv1BGDHGkwZuVyiMG5na1StT5bm3YENp27mTkhtRYds8i6Y2u) [sell](https://solscan.io/tx/4Ge2YhfDpJN9abgcYQ9FishGevryHeniJ3ary99e2TrfH1dn87kc5Ymbnc7b6XmkdWZjfYvNp6bpDiXpvB7B27HA) [whale](https://solscan.io/tx/4UzYYyrBkwtzrHUy5Kpv1rncQmR7FzGfzzG6h9JBLwAUobgdKpJwuBoC44qkrDLowyh8jwnkGkRdM6NZkivysVkp) |
| 46 | 23:51:39 | [EeGexL](https://gmgn.ai/sol/token/EeGexLcFaScmGnWrLXtPyLa8pE3QYuLX8E3WyN6Rpump) | 10.1% / 4.84 | +10 | BAM `7qGNnX` | time-limit 0.9 s | **+0.0294** | [buy](https://solscan.io/tx/4eBNuST1rVNpVR2NkYYggeGc5TDAxoonLuQPDEADLtqHbxJakZQ7CiWRfgWuwaLY7nuxHRb4HmBVoYf6vdwG8BV1) [sell](https://solscan.io/tx/9nUeUzvrbSPupsUeBW1EoT2pxL5Y9gZWsVXohSXMjF2r5dXGRcbbn4LfJZ3VJv2sspUZyPXqWjDB2D9ZgThyTPg) [whale](https://solscan.io/tx/2b2wCVR13pu7fYd58jFtRQL9GLSwWJTAmi5zBN1sSf1vxg6K6YpFd6qHRkv3gKfb7Wxtq7jDwcgS3LkM1sTXjPWh) |
| 47 | 23:51:49 | [ECXyKx](https://gmgn.ai/sol/token/ECXyKxJMxPwATAcB8swURkrxCUHA9PNkQnrZDy1Maxi5) | 6.8% / 2.96 | +8 | Jito `ACvL73` | time-limit 1.6 s | **-0.0107** | [buy](https://solscan.io/tx/5rZZctoRx7xGVzGZU7zW7n5C4xZ7RQMX3uTXa2mHkNtgPym2pa4Av3G8keRAUDhUru53TJ893X4qSXeg6kmkVuDi) [sell](https://solscan.io/tx/vaZ9v29ec8FHeYiBtsXXNQ3psqKkTQJrpyHDPRFYVtbYVCurz82jEWvms13gCyuEkbvWCJr6BC2PR4zMsiMw25d) [whale](https://solscan.io/tx/35gFj1s1LdcZ6z56GtKCRmvCPNvstrmuothCCBndcTKDdjCZkCcMKuvA6fznxzTnBfmzBbuS14o1KSxqLX59ShGL) |
| 48 | 23:51:56 | [CoYRC8](https://gmgn.ai/sol/token/CoYRC8vvPfLEfXHQ9zoDbxxWRaYuAQ9WU89WJXXHpump) | 9.1% / 2.96 | +7 | BAM `E99w1X` | take-profit 0.9 s | **+0.0420** | [buy](https://solscan.io/tx/2FpugybBmT8UM3pn4DCRDVoybVGZ2A9pj1KXfsMHmHmp7U6UGzxBqeqmhDWyQTSTaZepKoE8Cj7fiw5gq5SEThNi) [sell](https://solscan.io/tx/2GfiKD4J9Mf9yBWLiv4qAWwx5h7QHxXaNFr74RedEEe6qegE9tiGJwnckcqeJ5pkfwBGgkYFvyunfdv6me5dvQLu) [whale](https://solscan.io/tx/217R8cqYZNP1ttvDvifwNi3mALGmfSgZR6UZRih25jiQ7bB4LBuURLBTGsVxfRxKSW4uzwrHc3LQDXyQVrKNW1Mj) |
| 49 | 23:52:35 | [FRY3gU](https://gmgn.ai/sol/token/FRY3gUKrJKKL86ukrUZkzP61P55pTw36NGYpT56apump) | 13.1% / 5.93 | +2 | Jito `HEL1US` | time-limit 0.8 s | **-0.0107** | [buy](https://solscan.io/tx/5NYCBL6PUxKWUvJSNtNFbKCj1mSUkA5XVeQDcWiFdTDqdReRxr1fkMQ3sw8jcXaCBJHec4oEjssRGQJr5EXSRm7j) [sell](https://solscan.io/tx/5TAbcEGpL7R2K8CxQXkcbe5yxk1UXEuN8iAYR7CsgnF7CpfeSK96Be1VTY4V694oUWfXzPnrj4SwURBoJUFn2ufZ) [whale](https://solscan.io/tx/32hq4K36fU9UbQ1kvkr3stH5sQn7U4CZHAxa5ScBqZXZHF8JZjWPjFLGzBXUFpehiJJAeX5i9SAnSBk73QVCjQL2) |
| 50 | 23:52:42 | [sfxBT5](https://gmgn.ai/sol/token/sfxBT5xUjU8jvbXNTbN4TLuFP8HShd4C3AGtW7mpump) | 8.0% / 2.93 | +6 | BAM `HLnodb` | time-limit 0.8 s | **-0.0087** | [buy](https://solscan.io/tx/4jKVfngvBCgdYLJioLXEttttsnEpXvGdFPm2BmQqGXS8aFSVDQUm1ktYZwwsF6rwMEGcPFCJCvzTkg6wCBnHzVYC) [sell](https://solscan.io/tx/5nwkqCU34Aef6Yp1M1txsLv44vd1idaeek4RQFvQUn5RaK2wCLtMjGh8on3EP8MYPpZTdMrf3tfwKzqKxQGZAycn) [whale](https://solscan.io/tx/38M4n9t9V9MZCDk829XcFrvZRN77fF9vRh67Pjf6FxHBPib6U6Fxxq1Y6TZ8XUreBFy1D5rw8SQP9XJ563CYcKFD) |
| 51 | 23:53:42 | [A7S6xi](https://gmgn.ai/sol/token/A7S6xiuiaNBq1kdTpXGmLdi5N7hNumr5m2MJmiRkpump) | 7.4% / 2.96 | +3 | Jito `5pPRHn` | time-limit 1.0 s | **+0.0028** | [buy](https://solscan.io/tx/5iJ9dGfKGGbu3216KrsPpCgR4nG8rCxSbkytjakaoRFx8K7UnWq6sq3w3ndRnEfXV5t2fgspVidryJyxE2SKBdkd) [sell](https://solscan.io/tx/5hCh3CJ3DrMCEmbhZvvheF1LSuRmQWCBL5kRQHqjRPxEgVY1XwNHaG4n6MPE2b7sn3kkFCyP4WfJwLpdu8bHJhb9) [whale](https://solscan.io/tx/5mJ33aLj6PjLmzaxrZCHDASo1eojJRdgbyCgYgaALk9KDx9cx1qJr7eLPacMyNAcfWC78FxvBD5mPBV8EoqGNEXi) |
| 52 | 23:54:52 | [H61Kwm](https://gmgn.ai/sol/token/H61KwmdsmEgpRpzYM3DmLgCeGVH5YH4TKYgLackapump) | 12.0% / 4.84 | +0 | Jito `vu1sGn` | time-limit 0.8 s | **-0.0128** | [buy](https://solscan.io/tx/3B4KwX4Jmd6Dfsesh1JAm2eGBBAJJsdn1FvoiW7hnH1B67zLad5unHTR9pdQf3sN111tfuqpCVkkT4cGSwZ9U8Uv) [sell](https://solscan.io/tx/4mgZnCQHmjsEeh1DjsdAroy3BdjhWF7J7tMJy8QGPaR9Y5LMuEcVEWKMdhNbpqA12u1qMJ7UsLVdDbVpTofLxaBM) [whale](https://solscan.io/tx/63UsHwnuqfoD9RL7ea5puca8qhpEU96Tg9p67Q36CTwKxd3Vm1T12pUJBjC1bx22TgtdAaDpze74Fitykp6wNkzJ) |
| 53 | 23:58:08 | [CPFEK3](https://gmgn.ai/sol/token/CPFEK3FV8DUJH9hBkekXhqRMNDZLZerhjrUyhMQxpump) | 9.2% / 2.96 | +1 | Jito `8gDfqH` | time-limit 0.8 s | **-0.0169** | [buy](https://solscan.io/tx/4PVZexEG9LPK845gQJx95kd31YrB8WXvbszkqfBC1nUqFgnQGjCpuwxNE2CX6v4Xddnie4RBNepq91bet9kA6YE2) [sell](https://solscan.io/tx/8KNeKefYS54ot1QKuREtdZ7xMEBe9xzwe6m3gmSNyA1iq8qh4ZBX4znWWQzE5aD9faHh7utBZaXFeY5xmWHfjoj) [whale](https://solscan.io/tx/nmSUo6xedGFdusNZsDXnTooqEvTnt5uTsFV2zqYEkoexGvxanSGpqXkW6nfRPJfC1N5tXzvx7Yhuhf8jJ2HXaDb) |
| 54 | 23:58:16 | [AsDx1E](https://gmgn.ai/sol/token/AsDx1ENsaQyCnWiKZnGgKKi5tKtiNkMetrjBEGFUpump) | 9.1% / 4.94 | +2 | Harmonic `DcTPJq` | take-profit 0.9 s | **+0.1341** | [buy](https://solscan.io/tx/32heTk1Lq7MqPvc2iaiPPYmCzijfUFaicokjYTqcCZwa4WrPVCDed2h6UsgN2tPiW9dUKL3ZRVDRKfN6hPrZqPKv) [sell](https://solscan.io/tx/uWru9AxifLVP4uzjLCNJGCKKS1hg2uMiVJegJfkYfnnrHahRvDonVQRRy9Lo9rNcCJVkSfbNufKqWAbortE4NCq) [whale](https://solscan.io/tx/3qdWbJKoeyhGzousDb4M57c4EhAbwWs2SaBws1uBdTu7Msvyq3v7hRE7oGevGDcWdZY2JHW8nTA8TCVTiFMR8Wyq) |
| 55 | 23:58:55 | [E4bsDU](https://gmgn.ai/sol/token/E4bsDUVN2qzfGuoWhjwmohtTXEGrQz1FtKuW9ndiA8G6) | 7.9% / 3.95 | +3 | Jito `9rkJMA` | time-limit 0.9 s | **+0.0120** | [buy](https://solscan.io/tx/3Xc3zFgZWj6b8jZuAoTV7h53srS3wGRY6Qh97FQ2yPwBGWWDLKXJNVuksaDQ2khmnPLTk2LUv4TtcsuRke1K4dCe) [sell](https://solscan.io/tx/29rqCXGtsT2QFd6rj1aLxsknHAs9EhBxN5SEtKVjRFNzFqagt3oPKvdhkBVnsvFKsukhoBL3q7wRPdWw2jZjUY99) [whale](https://solscan.io/tx/MS9y3VKLGn6xcgUKbTmQuFGwEc1kbgm1mTeZiSEnCBdVhGzrrFZajG4b8nXJdrTmGLPfM18MHVVrkAVKYtzXLRG) |
| 56 | 00:01:54 | [6UYa21](https://gmgn.ai/sol/token/6UYa213GEL1wyGbmZjteU8m3By3J2pYqW7rQGXx3jZVa) | 6.5% / 2.79 | +7 | BAM `GSTamp` | time-limit 1.0 s | **+0.0035** | [buy](https://solscan.io/tx/HrvJLPtxtTU1m2siBg2hKLbSigcyD9VWToQUN58vmdZuA8GFpVQoyGTSET8DPHKD86VEgu8W4C6nYupmqZVaSor) [sell](https://solscan.io/tx/4yELSTDgUgUifHyWZ512Q8vGUoZgSpxGm9hTLApooBW4G77ezjMfXWKT9iodkGmv8MxkkFshuCHk2rZL5cBpeKbS) [whale](https://solscan.io/tx/2pP5R53zkwLVR1jjCFkaUNq9Hbq2A1tXcT9NJNXHxBen8ZiwzXvdtuJYaK1h3kqG5wXRoXgBEAdzUV2PS2Ei4cUS) |
| 57 | 00:02:27 | [DPf2Be](https://gmgn.ai/sol/token/DPf2Be1m2J81o3ZwHLc1UubtTRhtHXymFdc7Np9cpump) | 11.6% / 4.44 | +3 | Harmonic `87CcUx` | take-profit 0.7 s | **+0.0732** | [buy](https://solscan.io/tx/yJXmNhMfJR5XfVkHCb49qPuFTrXP9T2ruJ1YA1vgve5fx3cmPkJk3UaPD1XLpzsob1jxd3heNXThrJd9TVXRtYq) [sell](https://solscan.io/tx/3naivQbqgkaBcN9YDXGSdgL1Du97cEnGsB7VJjQBxFF3sknbH12LZZ6yYQ5NsqWb4SLqDDQHVKotxi8g94JKHg7n) [whale](https://solscan.io/tx/66TeGZFzdsKFpydt55t87rzpWsR5ZjpivFDa4T6ZvKyqt2eD3kvG7zpLRJuRo2xmsjPCm54Kgj8a4rC3qjtQTWJz) |
| 58 | 00:02:29 | [52N2XQ](https://gmgn.ai/sol/token/52N2XQsnxq1BtXdmdNucC9KNbJi3HNjt3VcL5ofnpump) | 6.1% / 2.96 | +4 | Harmonic `CAo1dC` | time-limit 0.9 s | **-0.0171** | [buy](https://solscan.io/tx/3xigHLJpfvfbTJ4uQq44Vyk29f7gsXY6JYBHqoXP25uE85ymrzz5oqkLU4R2fyArbPkXTNCDK4paezri5hKdLn6a) [sell](https://solscan.io/tx/4X9tE21GJJSA1K22s7xGiiBNwjQbGhN7zzF6xKcQAwdquacsM2hCDVwzawaGpiBgmPyUKsV2Bokk5TgqTDnfvD7t) [whale](https://solscan.io/tx/2H2VAQgd75JigvH7SqRd69u3CLYcboCSbWgVqB5Wzu8ReZWk5ELwqzycR6buHNb16yPFLRUdEk654jpNUySHERoM) |
| 59 | 00:03:51 | [3pZLCN](https://gmgn.ai/sol/token/3pZLCN6ykDsRmneTCaa4ELaRKdCfQnmTYL2hEsPXpump) | 9.2% / 2.96 | +2 | BAM `DRpbCB` | time-limit 0.8 s | **-0.0107** | [buy](https://solscan.io/tx/3hVczxejX9Czb6AL4zUYk5QxHQLUMW4h5SoabL1bMa4wCcxcJ8TBgXLkCMiaAVZ4aTCGtLSRuegoA8adMsw5xTZE) [sell](https://solscan.io/tx/34zFum16edgrx4yhebe3CMsMwyx7oEa6FxLGEywauzVLkotk2WskaAxWYJXJSa1DBy7xwhZnu9z1PYY6pyM4puKV) [whale](https://solscan.io/tx/5zcVMFvNz1H4t756HRqyQKHV6tnehCjJtT9pESYMe4XPRf2Gghd9u8XkWg69gMCEUEuLmL9CnwAP9CGiq6Z1NWVE) |
| 60 | 00:10:48 | [FDRgp7](https://gmgn.ai/sol/token/FDRgp7Yca7BE5ndkWLEUa2b19VJNG8WEP16HmnMRpump) | 8.5% / 5.93 | +2 | BAM `DRpbCB` | take-profit 0.7 s | **+0.0781** | [buy](https://solscan.io/tx/ZUaAddw7iSLWaoKdv1MrmLAYYE9HYkKYpNfnGotLSzmSZbwA2gVqLmSPTDRQueMUWt6pmYjaXSHkADJ1nFfy56o) [sell](https://solscan.io/tx/13oCBkAuFhbLpjSpuXUELeXGYfyGXvSjLUZLbZLEfRcT4RTp8YuZ6y8cNKhwEda7UseQk9vXrQHSsEPHiBL7nK4) [whale](https://solscan.io/tx/QxLmb5SKQVLXQYcV91GHBn6uC7ZN4KJ774TetXHdas1rdgsYZvBHPqDzEG2yjCkQ29uxoDgSMH7SnT1mJ2H2ekH) |
| 61 | 00:11:25 | [6rNLPY](https://gmgn.ai/sol/token/6rNLPYGyumrDTurm8eTjMpXPQSCwYraKZ4EEb7Axpump) | 6.3% / 1.98 | +1 | Harmonic `87CcUx` | time-limit 0.8 s | **-0.0107** | [buy](https://solscan.io/tx/5gEgJ16Mu6KVcUNbe9RN8xKRpLUyfKEHmBYyuxqeuGLifQJoB4X1hFCTSg47j9oDTUnMrCkLHwoeY7dqe9RJsNb1) [sell](https://solscan.io/tx/8CuxDxEdhQYHEvDhtxHa6StEpFia3kuicG5RTUQSee7qBAcCCzXbsoJ4D2LADcyqeAt1Qzrm5ViHN7TnLsQDMo3) [whale](https://solscan.io/tx/W7bJ3H2psL4Dba9vXu9Brkq9vsjaszRiJSeAqeFRsW3qzar6fime3GnpDn8zhA3tU5ChFmnTYs6UFPyzyXnCeTg) |
| 62 | 00:14:02 | [5qzhbf](https://gmgn.ai/sol/token/5qzhbf4S3dCD4bUyP4YJtbJfxuoTJW3C5jakroP4pump) | 7.6% / 2.79 | +2 | Harmonic `CQdLgw` | time-limit 1.2 s | **+0.0200** | [buy](https://solscan.io/tx/3q3drc66ujV7bNKdnQ7q5bZxJqgVjVAqHkQ1Ee4j5bhfTgSk8fA8NM8VqQprKYoXCoSz5CeUdf8Yw1ZUT4UikukR) [sell](https://solscan.io/tx/ENbPpmP2DuDvB955hBrpE9xVpfTYEMX5dpbbNU8xUYT8vEtm5dBDsoB15F1Kz3CEkbgrmbJeYkbc9ECDwuRPDwf) [whale](https://solscan.io/tx/4p5G9XoR1H6jYa2hTGqMZHjavCY2RDpnrGRJyky4uxqgsiS4ySEXrUb2RDpCGRCXuk5T7Zp9j54X6wLL1UycpZAt) |
| 63 | 00:16:45 | [EtT5TS](https://gmgn.ai/sol/token/EtT5TSkshh5jWBxEcvMWb41uaXktZf4ZnSocThrJpump) | 7.4% / 2.96 | +6 | BAM `5Cchr1` | time-limit 0.9 s | **-0.0107** | [buy](https://solscan.io/tx/4rBmYEc8Qj3dcKKwatwwjGcM6B7uDdotrheXyr9zZx1RT2pDNV578kJPH4EjuoxpLLTAric41vdoutU55HqTiSoD) [sell](https://solscan.io/tx/37LPdHxm2NSBs2uM7bHih9nqUWsqubKu8Gn23xHge6GxupYvfn5Hbj1deUgF7jxzCXdCe98UXjbF6EWGdYCW7ESp) [whale](https://solscan.io/tx/4zCn1fJu1BiR336e4NjnfQu4Ue1coEJFEEWNVBp7REKscdkSRdivoA1cE9vPEYoPEppeqgeD149d792gs9bmrfqi) |
| 64 | 00:16:52 | [5HYwM5](https://gmgn.ai/sol/token/5HYwM5yJzzPLmj5WJwcUYXXhw5n1dsJaeYQcWv3Rpump) | 6.2% / 2.93 | +1 | Harmonic `87CcUx` | take-profit 0.6 s | **+0.0592** | [buy](https://solscan.io/tx/jZQPVY8CVnz5tfjGWutYNtB8dv8aQRQcrhjENX8KeV1LBZaMgUuiEMYWnxMtG8kJhGnZJVnMNsXghXucA9SxU6y) [sell](https://solscan.io/tx/5FU85XNVQMCQA3oXbtyVpyPaF5AuJc7p1xFn8JahcWgKVfu58tjuCQTZhrQ6VJ3uJayTPraSwo8QFm97Q6h3nHJ6) [whale](https://solscan.io/tx/3ygtUgfgYwuhjDQBehw3rmrXyAqwmjriFGe5QzGuTUFydgfyFMzueuKo3qQa97vfWgS2oS7hComBiMseDcByEhg8) |
| 65 | 00:19:11 | [7QcyUC](https://gmgn.ai/sol/token/7QcyUCtipUGVw93f63XXc5twk2UXWToVVsc9FiPbpump) | 7.9% / 4.44 | +4 | Harmonic `XkCriy` | time-limit 1.0 s | **-0.0378** | [buy](https://solscan.io/tx/5XKLHFf2kjY1i8QfciJijv6XZ85pjv1qfDsYof7rJkpauiUvYYTkZygPz9utVM2pAskEHZAHj9cjTo5mG32xB5pp) [sell](https://solscan.io/tx/b25DZFxVW5eZSVsNMVj4Uc6cqTPrq9AQdthxnQ1qU9kiWYP8MFgRtACBwQzbyaeWqQuLVVmuNCAbkqmvNtoiPqh) [whale](https://solscan.io/tx/23GeEdzS3EpUDLqmGWCj6w8gFavjUkKzbg2nHrrMs92TMSpxxmcV7KqzVpgC7ap5SKeZWWhC8cqvG7zxLRp8hssW) |
| 66 | 00:19:14 | [7QcyUC](https://gmgn.ai/sol/token/7QcyUCtipUGVw93f63XXc5twk2UXWToVVsc9FiPbpump) | 6.5% / 3.25 | +4 | BAM `rapXHr` | time-limit 1.2 s | **-0.0010** | [buy](https://solscan.io/tx/TQoy2j84aXSVqEiPN2Ei7R8SAhxmDQoDQ4Ddqos5gTAGKE9Dadf3s6ZJyaYYZp2MpbjMQRK2eXA7o5sKgNZpYLe) [sell](https://solscan.io/tx/4T77w9j3vUgGDFcGfKsDAmQ2iYcV3VWteRVNxpysx22Gi9y6WhitZMNmLC7nPWhKQoYrC5bwmJU3eCjJxqDSuJ56) [whale](https://solscan.io/tx/2EoNbAEw99XGSPNn4SCJpb5WxRZQyHd4njQCY8Yv4Bfnrz8bFCrDhNNNKaQ5PwMgiqkWWeuYC7kNscptQC8Lqk8Q) |

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 7174 |
| Inside the envelope (age / drop / since-buy / size) | 3555 |
| Picks (score above the threshold) | 98 |
| Skipped | far_leader 72, spacing 6, presend_armed 4, no_launch_accounts 1, no_new_buys 1 |
| Buys sent | 14 |
| Filled | 3 |
| Failed on the +5% guard | 11 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 3 of 3 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 22:48:31 | [dxD6sf](https://gmgn.ai/sol/token/dxD6sfxX7XUqn5QMQjEqwSAG8dQ1tL5ga8bAZ5nKKo3) | 0.55 dev | 0.99 | 4.92 / −25% | 2.1 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 2 | 22:49:08 | [4KgmWz](https://gmgn.ai/sol/token/4KgmWzwhbMYwS3bSJMYndbBHfR5wxLijoK56sZYNt6kk) | 0.55 dev | 0.93 | 3.58 / −20% | 3.4 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 3 | 23:17:51 | [H1EdPF](https://gmgn.ai/sol/token/H1EdPFQYfkumWqAj7JJsanrhhZastqw1JJKBhD8C5GYs) | 0.55 dev | 0.79 | 6.68 / −31% | 3.4 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 4 | 23:31:33 | [ALHbqq](https://gmgn.ai/sol/token/ALHbqq5AVQTmiLCdS2DSM19JztUf7C3bBHFwasW8pump) | 0.35 | 1.08 | 3.30 / −13% | 4.7 s | Jito `GnC339` | guard fail | -0.0005 |
| 5 | 23:32:13 | [9V33Lk](https://gmgn.ai/sol/token/9V33LkaWXb9EsEsLrPuoGLWDgvrKzptmFq1hDcf85J6d) | 0.55 dev | 0.62 | 14.98 / −51% | 5.3 s | Harmonic `HTeRsa` | guard fail | -0.0005 |
| 6 | 23:40:21 | [8Km82u](https://gmgn.ai/sol/token/8Km82u8C8pX1pjTmEbtahwgBbSc1qaoFdKfmcDKJZYDn) | 0.55 dev | 0.34 | 4.09 / −21% | 5.9 s | Harmonic `EkvdKh` | guard fail | -0.0005 |
| 7 | 23:41:22 | [DwidxB](https://gmgn.ai/sol/token/DwidxBkfs9q9GN1BW4S3kfD4Aq2dX13CU8DmSUa3v2b7) | 0.55 dev | 0.49 | 6.11 / −29% | 9.3 s | Jito `ABC1U4` | guard fail | -0.0005 |
| 8 | 23:44:53 | [6EgrYc](https://gmgn.ai/sol/token/6EgrYcX79PcYSMS6UJAKHd1nm7eyypP3hFJapqjCgtEq) | 0.55 dev | 1.03 | 3.59 / −20% | 4.5 s | Harmonic `GoeW4a` | guard fail | -0.0005 |
| 9 | 23:45:35 | [9fdp4o](https://gmgn.ai/sol/token/9fdp4omcJoRycUArgAmfnZ2Am5vRq72C85yJzvfypump) | 0.35 | 0.91 | 3.11 / −12% | 274.1 s | Jito `AHNX2Y` | guard fail | -0.0005 |
| 10 | 23:55:36 | [4xx2ME](https://gmgn.ai/sol/token/4xx2MEeMSLsA6FyyVsPAwkwf4WUAFc5w4zJVT9P3AVq5) | 0.35 | 0.53 | 3.57 / −16% | 2.3 s | Jito `8NpDWR` | filled | **+0.1088** |
| 11 | 23:59:08 | [Ha3WSe](https://gmgn.ai/sol/token/Ha3WSeTArik4quNVfeGcP1EEx6VmDeZdrBHK2yTRHFEE) | 0.55 dev | 0.69 | 6.70 / −31% | 2.8 s | Harmonic `ALp2Gd` | filled | **-0.0058** |
| 12 | 00:04:33 | [CpqMqq](https://gmgn.ai/sol/token/CpqMqqGr6uUMij1aVeX44g2hM2apJGopFk93K6NTND6f) | 0.35 | 0.94 | 5.94 / −30% | 1.9 s | Jito `Chorus` | guard fail | -0.0005 |
| 13 | 00:07:35 | [Cse431](https://gmgn.ai/sol/token/Cse431VwAaMzxsoCYNA6JT1porbg6KfkSuzxR8cnpump) | 0.35 | 0.32 | 3.11 / −14% | 3.6 s | Jito `GnC339` | filled | **-0.0295** |
| 14 | 00:12:33 | [7vGfF2](https://gmgn.ai/sol/token/7vGfF23C6PVxazLXE5KAufKyyC3VNmPUpr83Yorkpump) | 0.35 | 0.60 | 3.42 / −13% | 45.8 s | Harmonic `2m1A2W` | guard fail | -0.0005 |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 117 | +1 | 5 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/593Dr9JkjTkVhW5oLh4A3GYQgibi7hJaM1uB9EFrNuaB3gRzDsyFGz97Q6mSr8GLtiirtxxxMKbnw9MFnAKvwaWH) [dump](https://solscan.io/tx/JyMJWPa3EJ2fTZ9WuEdtSZgun7L24NFU7328iHb6jMsiGy9k6B3WPFJc9yCH5Cq4LmpGkFWz2KHcm1McMo3fjSd) |
| 2 | 122 | +1 | 4 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4g7j1My4dpM4V1g4KpnsXTq7m6W7RRckFRcMWFHpxUSb14RRk45vBSENT9cMyz4FLo27tgx1Z82LFVqviGBBzUvt) [dump](https://solscan.io/tx/vt5aVKNxmh5JX8Sig5aH3XMFXFPy1eM3XD4HeSR9w59RwyhXg69t4oePXheCJnbwjsrzGgqNPugKs2fgEWqPJnY) |
| 3 | 119 | same | 6 | **nozomi** of landx-fra3+jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3WWVMLhpmWTN7dc2EenEuXNTpynj4bn75o86yTw3qNsbRSG7fZ9tT7KhHwBVqCoMJLg4SKD7QrcBYbD9dhiWGhRj) [dump](https://solscan.io/tx/2sqxjkSEE2oNEg4UfVSBmfHGRTbJEL3FPUyheW1hrw7yDz6Qo9Qv2yy7o2RW5MhHE2NXZq8WMkv3KHsxETVmQoHN) |
| 4 | 17 | same | 4 | **bolt** of jito-bundle+helius+nozomi+staked-rpc+helius-swqos+bolt | – | – | [buy](https://solscan.io/tx/4bCRDkW8FMAReafEfXhZdzgGcdP6ab4wCw9qqT1E3vCAuU3V4G4uqDZQSKPLr4iRuGb8ZZhGbDwAPipxNiesZDiH) [dump](https://solscan.io/tx/3mgAeRzD6Adgp4Jfyk8iyj2vAiBZeNcwDUiue67HteAkCMRejyXVAtgVk2fS3RGYz1PfpRGYiGfamA3QMkaEE1yX) |
| 5 | 18 | same | 2 | **landx-fra3** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/45nRHtsZrvZmHwGuyFWztjCRU3eC1dw3oohnRBPwZtKpjkwKhoybsHvmeXGGBkp2KWmKQVn7K7Ahnhr2b5qygpg1) [dump](https://solscan.io/tx/2dj1k229Y1TQU2rQvmthCBMsL69suP3jioqZfUzUHM96x1hNTUN1QUX8mSbtamaAVACc4hdFZmRRQFXjn9vQi9sY) |
| 6 | 146 | +1 | 2 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5RJoTrPUzu2PTM2W6N1ZokYtGcpWhhPZ5sNVTzorbFzKCwTsLq87GEGkhJkVYLZY7MemLnE8fPrBmt3yoZsT4zy1) [dump](https://solscan.io/tx/349VvBuRxWHDZ86SMVezyEZ2deXxaavdxz1eqWkNAKZqayQZHoBNZBmwV9pFMC4EW1zZJGNr9uHX6Km4p99V4h48) |
| 7 | 17 | same | 1 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4a2ssD9vumggRAaNY2ewz2JQc2mmVdYeKvTo6RKA85iLUCYsEacwsDJwkEhxbq36eZx1CroHbnMDE5BTSuTw7mfn) [dump](https://solscan.io/tx/4hZXzKWLeGK6B3HrEFGSdrS2ngA5XvLMVAWwGFVjgXx5BDb2rrczJiDm1HR9RaBFd9WNBFrq4B43iuEAMr4Sab2q) |
| 8 | 43 | same | 4 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/9tn6gdEQN5oD4gWPVhnd8GHZo6VeVdDujPvKQmeK33MFAdSAprZ8vcS8TgE5GG85vcFkdzRbcTyFkeJGNA54dXK) [dump](https://solscan.io/tx/3oa5anTbtZ4gPyj6RdgkGXoqgfY9n6V8EtZgjQ31obQ7kWSfTsKdFTWncHPQuG7GdCN2JbitKqCcGjXKYCMQiPnf) |
| 9 | 37 | same | 3 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/26i6oJbEVegdKKpibBv18d8tT4p5Kv1WR98LQtY2KaQEi7bXKThcBT7aZ8usSmb3ccid5C91ozYoQsbnjDZSWwnm) [dump](https://solscan.io/tx/3E3NByb9E3nKWeaWt5BhwG1vqtZSgwKAFp4JDFDufMb1MNJtsSE1qVdbRXgZDnwBGxgX5qXxzNjME557rr1z9AAg) |
| 10 | 71 | same | 1 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/faUzhnJbEFEn6KpNf7ZVFsk435VSYhQDB7TztavcqYaxnXSW2Fd4LGWdJP48upozJwqZvYXygu4BjPu1z88pQ77) [sell](https://solscan.io/tx/2EeLE2pKo5iAR7FmFau6YjeraduYJKH2FKjtjGidp6nJqZWQp9nQRQw432Ju2PvimidwoKZ8eHnFJSSXstqDNJ4n) [dump](https://solscan.io/tx/3waW1PZp3ZYKY4GfewoMdqqvPWREZQhRCZEJ1N9hE5VCkces7fK2XDsvKe7e7sWFc1B994i3yhodCcHo49WeJ9BB) |
| 11 | 43 | same | 2 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/qQ66x1xvvtKCAYYariqYUY57Vqp8AKWsDgHMZJB6gWQF6SPXaNvcqLB4PLW9JTK6xxoEgNMFtpj8UnETnTr96j4) [sell](https://solscan.io/tx/szDdSJRn3UDrwfGc6wAEc3voyTkgR2a5St2anJT3uQSPRfYssAzVvk4xfC4GFnbtXbdG33mTK1bYFZJGyHijpWv) [dump](https://solscan.io/tx/4wGRNnywj4YKpmS6QaRkVfrnPVZHTMHMQUa99L7xWmoavXrtZSjxWgX3MgjPPzD4DbT968QKufGwZMeCdYWrfvHD) |
| 12 | 163 | +1 | 2 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc+helius-swqos+bolt | – | – | [buy](https://solscan.io/tx/2Eo3EZC6d6BNofiQ99c8Qfe5s29epbBKaSCLkE9QBs4av2RHRKBrX8C9jrYvFcaBpdd7a5vtyzZy4NQHgwPr4izC) [dump](https://solscan.io/tx/MXEZzRS3AiVcwfsjTE7fhtPxh99EohZZtcgYxgMoURXAiYeGhT8SmJYX3mtpCPtc69vwg5aRNyYu5EeD7xGZVQF) |
| 13 | 124 | +1 | 4 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/4UJSS37UiFq57Q39JwDqWqCsshLzYp7JGwzr68kRs2Dr3HKHXZ65o9jxsy6L64L9a57njJfB2fjjvyfG1WwGUPtz) [sell](https://solscan.io/tx/4iZDhRVF75Do2iPyNZwdnEPznWUigsEoDcxhDiyo7RVfJoYPZzGx3iQD38wCeRrAeWr8jnonmNGF7vQwrgp8kyZb) [dump](https://solscan.io/tx/4pvb58LyrjXGHceoCmtST8F6xmjJU9ZryzLzVcg17boAdn4z7HS387GGFN7AjShq7rTeHx6YsxoXWEQvZa2VyKmn) |
| 14 | 63 | same | 8 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4vp8xkbeF4P2fGgmcZTuc6MsV2FP47vaSegWfhxhJ1q6dNyAZ1pYmBFpaHAoN7EGoiznXyoYrvXxizN9naMVLdmG) [dump](https://solscan.io/tx/2QJWA6wPFMUHghJ9zqUZkW2vj3MciWm7vRoJ2m1kRCCRLyVGpnD2zfRgHN8jhjtp4wnYL7Y2XBR8Wew1HC4oJJRJ) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Jito | 9 | 2 | 22% | +0.0758 | +0.0397 | 1/2 |
| Harmonic | 5 | 1 | 20% | -0.0078 | -0.0058 | 0/1 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| dev list | 8 | 1 | 12% | -0.0093 | -0.0058 | 0/1 |
| normal | 6 | 2 | 33% | +0.0773 | +0.0397 | 1/2 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 9 | 2 | 22% | +0.0995 | +0.0515 | 1/2 |
| next block | 5 | 1 | 20% | -0.0315 | -0.0295 | 0/1 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 22:00 | 2 | 0 | 0% | -0.0010 | – | 0/0 |
| 23:00 | 9 | 2 | 22% | +0.0995 | +0.0515 | 1/2 |
| 00:00 | 3 | 1 | 33% | -0.0305 | -0.0295 | 0/1 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 3 | +0.0736 | +0.0245 | 1.4 s |

## 8. P&L leaders
**Best trades:** 4xx2ME +0.1088 (Jito, time-limit, score 0.53); Ha3WSe -0.0058 (Harmonic, time-limit, score 0.69); Cse431 -0.0295 (Jito, time-limit, score 0.32)

**Worst trades:** Cse431 -0.0295 (Jito, time-limit, score 0.32); Ha3WSe -0.0058 (Harmonic, time-limit, score 0.69); 4xx2ME +0.1088 (Jito, time-limit, score 0.53)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `8NpDWRcK` | JitoLabs | 1 | 1 | +0.1088 |
| `HTeRsa3g` | HarmonicAgave | 1 | 0 | -0.0005 |
| `EkvdKhUL` | HarmonicAgave | 1 | 0 | -0.0005 |
| `ABC1U4cf` | JitoLabs | 1 | 0 | -0.0005 |
| `GoeW4aFK` | HarmonicAgave | 1 | 0 | -0.0005 |
| `AHNX2YiD` | JitoLabs | 1 | 0 | -0.0005 |
| `Chorusmm` | JitoLabs | 1 | 0 | -0.0005 |
| `2m1A2WM1` | HarmonicAgave | 1 | 0 | -0.0005 |
| `5pPRHnie` | JitoLabs | 3 | 0 | -0.0015 |
| `ALp2GdA1` | HarmonicFiredancer | 1 | 1 | -0.0058 |
| `GnC339vk` | JitoLabs | 2 | 1 | -0.0300 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 2769 (p25 1491, p75 3435, n 14) |
| Executed-feed lag behind first sighting, ms | 0.6 (p25 0.2, p75 1.4, n 14) |
| Buy sent → our tx seen on the feed, ms | 61.8 (p25 29.8, p75 119.0, n 14) |
| Fills: our buy seen on the feed after the dump, ms | 71 (p25 43, p75 124, n 3) |
| Guard fails: our failed buy seen after the dump, ms | 63 (p25 18, p75 122, n 11) |
| Fills in the dump's own block | 2 of 3 |
| Guard fails in the dump's own block | 7 of 11 |

**Which copy landed (nonce fan-out):** nozomi 7, staked-rpc 4, bolt 1, landx-fra3 1, helius 1

**Send-path answers (FAST-ACK lines):** nozomi 14 (median ack 1.1 ms), staked-rpc 14 (median ack 2.9 ms), helius 9 (median ack 0.4 ms), jito-bundle 9 (median ack 1.2 ms), helius-swqos 7 (median ack 0.6 ms), bolt 2 (median ack 1.1 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 2 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 1.74 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 2KtcBC (pre-placed) | 5 | 5 |
| 8yYMhuYo | 5 | 5 |
| CVPz447t (pre-placed) | 4 | 3 |
| 9k78QZyw (fast bot) | 3 | 2 |
| 3MHgGwdL | 2 | 2 |
| 9pQQc1xy (bait follower) | 2 | 2 |
| GEMPyqU1 | 2 | 2 |
| FUru6V3L* | 2 | 1 |
| HLU8QbLd (41Pr family) | 2 | 2 |
| 7PedQZmc (untipped fast) | 2 | 2 |
| DiqYk5RD* | 1 | 1 |
| H81m5Qv7 | 1 | 1 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.1158 |
| Pump fee on buys | 0.0154 (0.0051 per fill) |
| Pump fee on sells (residual) | 0.0169 (0.0056 per fill) |
| Buy tx fees (base + priority) | 0.0015 (0.00051 per fill) |
| Buy tips | 0.0030 (0.0010 per fill) |
| Sell tx fees | 0.0018 (0.00060 per fill) |
| Sell tips | 0.0036 (0.0012 per fill) |
| Failed buys (tx fees) | 0.0056 (11 buys) |
| **Result** | **+0.8863** |

Buy compute used (fills): median 81,254 CU, max 82,744 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 63 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getLatestBlockhash: 1 timeouts/transport errors (worst p99 247 ms)
- ⚠️ RPC bh-fallback getSlot: 1 timeouts/transport errors (worst p99 430 ms)
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)
- ℹ️ wallet change +0.8855 vs trades +0.8863: gap -0.0009 SOL — about the fees of the 343 pre-send tries never seen on our feed (up to 0.0018 SOL if they all landed and failed; inferred)
- ℹ️ Self-competition: on AsDx1ENs and 5qzhbf4S Amsterdam's pre-send bought first and Frankfurt run 20's reactive buy failed on the +5% guard. Owner then paused Amsterdam while Frankfurt runs pre-send.
- ℹ️ 6 pre-send windows still had unresolved tries at the end; dip15 exited cleanly 20 s after the stop (the probe-2 hang is fixed).
- ℹ️ Live landing: 31 of 66 fills in the send slot, 35 one slot later; send→seen median ~87 ms (AgaveBam slowest).

Checks passed: every reactive fill was sold; every pre-send fill was closed by a sell; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Done after this run:**

- Frankfurt run 21 runs pre-send live (k 4, 20/s) on engine dip18 with routes v11 (Falcon UDP added).

**Recommended / open:**

- Amsterdam paused. 48 h size replay (SIZE_48H.md): +7.4 / +10.7 / +15.3 / +18.4 SOL at 0.35 / 0.50 / 0.75 / 1.00 (−~75% if 20% fewer later buyers); agent read: 0.50 next.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r19.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r19.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Pre-send (section 4b): the jsonl presend_live_* records (fills, closes, REALIZED, account closes, stops, end checks) and presend_attempt_land (try results, failed-try fees); the log's PRESEND LIVE lines when a run has no such records.
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

# Frankfurt run 26 — dip bot run report

*12 h planned at 0.45: pre-send k8 40/s + QUIET (dip21) + M2-gated regular; stopped after 1 h 51 min on the owner's order*

> **Verdict:** +0.266 SOL on chain (2.9658 → 3.2315). Pre-send +0.669 (43 fills, 25 wins; failed-try fees −0.041) carried the run; regular lost −0.403 (11 fills of 35 buys, 1 win; 24 failed the +5% guard). The owner stopped the run at 02:23 PKT to restart without regular buys (run 27). The end check read 49 mints: nothing held, nothing to sell.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.2662 SOL** (wallet 2.9658 → 3.2315, Δ +0.2657) |
| Started (PKT) | 2026-10-28 00:32:13 |
| Ended (PKT) | 2026-10-28 02:24:00 — stopped with Ctrl+C (SIGINT) |
| Ran for | 1 h 51 min of 720 min planned |
| First / last buy (PKT) | 00:32:37 / 02:18:00 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 35 → **11 filled**, 24 failed on the +5% guard |
| Fill rate | 31% |
| Wins / losses (fills) | 1 / 10 (win rate 9%) |
| Per filled buy | avg -0.0355, median -0.0369 SOL |
| Fills only / failed buys only | -0.3904 / -0.0121 SOL |
| Reactive bot / pre-send live | -0.4025 / +0.6687 SOL (pre-send: 43 fills, realized +0.6453, rent back +0.0649, failed-attempt fees -0.0415, 25 wins; see section 4b) |
| Best / worst trade | 27FhVP +0.0479 / 2ePe73 -0.0772 |
| Fill landing | median 53 ms after the dump (seen on our feed); 5 of 11 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip21 (QUIET + host whale book + journal) |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.45 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.45 SOL |
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
| pre-send | LIVE: whale >= 6%, 8 tries/slot, 0.450 SOL, limit x0.88, route helius-ps, caps 1000 fills / 0.5000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 1500 fills, 1 open at a time, 720 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 25**:

| Setting | FRA run 25 | FRA run 26 |
|---|---|---|
| engine build | dip19 (dip18 + pre-send merged-fill fix: follow-up sells, accounts closed after exit) | dip21 (QUIET + host whale book + journal) |
| size (normal) | 0.40 SOL | 0.45 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.40 SOL | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.45 SOL |
| pre-send | off (shadow only) | LIVE: whale >= 6%, 8 tries/slot, 0.450 SOL, limit x0.88, route helius-ps, caps 1000 fills / 0.5000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| limits | max 500 fills, 1 open at a time, 720 min, loss cap 0.500 SOL | max 1500 fills, 1 open at a time, 720 min, loss cap 0.500 SOL |

- Size 0.45 (owner: 'ig 0.45 size'), pre-send k8 at 40/s per path (the density study's only positive setting), QUIET on with the host whale book, fee budget 0.5.
- Regular buys used the M2 gate (min 0.0101), not IMIT1 as the setup table's model line says.

## 4. Timeline (PKT)
- **00:32:13** engine start #1 (session with 35 buys)
- **01:37:22** big loss: FrL1NP -0.0583 SOL (time-limit)
- **01:37:46** big loss: 96wVc2 -0.0728 SOL (time-limit)
- **01:40:03** big loss: 2ePe73 -0.0772 SOL (time-limit)
- **01:53:37** big loss: 4RuRS5 -0.0647 SOL (time-limit)
- **02:24:00** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 4b. Pre-send live (pre-placed buys) — separate from the reactive bot
Buys pre-sent after a big whale buy, before any dump. **Not included in sections 5–11**, which cover only the reactive dip bot. Realized = the engine's PRESEND LIVE REALIZED records (chain txs of each buy and sell; the buy pays the token-account rent). Rent back = that rent returned when the engine closed each pre-send account after the exit (dip19+; before dip19 the sell closed it and the refund sat inside realized). Failed tries = fees of tries that landed and failed (6042 price, deadline, …). Net = realized + rent back − failed tries.

| Session | Started | Size / fill cap / fee cap | Tries sent | Fills | Wins | Realized | Rent back | Failed tries | Net | Stopped |
|---|---|---|---|---|---|---|---|---|---|---|
| #1 | 10-28 00:32 | 0.45 / 1000 / 0.50 | 8,390 | 43 | 25 | +0.6453 | +0.0649 | -0.0415 | **+0.6687** | run_stopping |

**Try results (as seen on our feed):** 6042 7,085, deadline 869, unseen 225, ata_exists 147, ok 43.

Tries never seen on our feed: 225. If they landed and failed they cost up to 0.0012 SOL in fees that are **not** in the failed-try total above (5,120 lamports each; inferred, the engine does not see them).

**By exit reason:**

| Exit | Fills | Wins | Realized SOL | Per fill | Median hold |
|---|---|---|---|---|---|
| time-limit | 30 | 12 | -0.1430 | -0.0048 | 0.9 s |
| take-profit | 13 | 13 | +0.7883 | +0.0606 | 0.9 s |

**By leader type (the slot leader where the fill landed):**

| Leader type | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| BAM | 17 | 10 | +0.2228 | +0.0131 |
| Jito | 12 | 6 | +0.1108 | +0.0092 |
| Harmonic | 8 | 6 | +0.2763 | +0.0345 |
| Firedancer | 5 | 3 | +0.0501 | +0.0100 |
| Rakurai | 1 | 0 | -0.0146 | -0.0146 |

**By hour (PKT):**

| Hour | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| 10-28 00:00 | 11 | 8 | +0.2318 | +0.0211 |
| 10-28 01:00 | 22 | 14 | +0.4643 | +0.0211 |
| 10-28 02:00 | 10 | 3 | -0.0507 | -0.0051 |

**Best pre-send fills:** HEoT1oFp +0.1249 (Harmonic, take-profit); 2WTSLyNR +0.0874 (Harmonic, take-profit); 6PMwHqdW +0.0764 (Jito, take-profit)

**Worst pre-send fills:** GHbZhjDq -0.0566 (BAM, time-limit); xUFKdTaV -0.0435 (BAM, time-limit); GC4hpXq4 -0.0423 (Jito, time-limit)

**End-of-run checks:**

- session #1: END CHECK 49 mint(s) read at confirmed: 0 sold now, 0 empty account(s) closed, 0 held / 0 unreadable (per mint: none 49)

**Every pre-send fill** (time = fill; whale = the trigger buy; P&L = realized, rent back not included):

| # | Time | Token | Whale % / SOL | Slots after whale | Leader | Exit | P&L SOL | Links |
|---|---|---|---|---|---|---|---|---|
| 1 | 00:35:35 | [7sh6Qf](https://gmgn.ai/sol/token/7sh6Qf491F89jTmdAAH8ovFbvpp13Eh5fqVPu4Aqpump) | 15.9% / 5.93 | +2 | BAM `22rU5y` | time-limit 0.8 s | **+0.0047** | [buy](https://solscan.io/tx/3auToJuMextR2ea2QVo5uEPmKeoHVCNm4ikxVS92brtjjiJv6MdiN8C5DuLbM7McJLW3NErJG7G2XPDuR5kHr8oY) [sell](https://solscan.io/tx/5jts35GQNYGGWwfNrA2ocmjrWbLvoUFh6UZt82g1R4RURxMWmxvER6j71KARrdwuGm18tqCQst8ZZncTkPF4smme) [whale](https://solscan.io/tx/2C3MPvkLb6VvNSwHbW9kFgrKMb34riZA9kP1tw4gY5GEK33BDS1D5P8zGD4XTx24EHDQG7ifVPNyzWGL5Ja5zmkG) |
| 2 | 00:36:21 | [CTJzth](https://gmgn.ai/sol/token/CTJzthV7krn2kb9TAqZ1T7udXsaq6mGYZrB9Sjc5Whd3) | 7.0% / 2.27 | +6 | Jito `HEL1US` | time-limit 0.8 s | **+0.0271** | [buy](https://solscan.io/tx/2HZQjdFqyae7BpJXqQagZBKjga3zXq4Rfuu3JSWzeJp8HKxLN1ofbuDhRJebQKQjM8ZLzf9pqVZBVMKLcXdKEqf3) [sell](https://solscan.io/tx/wXnpjQSfy7W1E2jDs3Lt96S55NE6RApUshJbMxza9ZxcVFcnYyR8oz1B6YCPCwEv8JYg33qP8fs47kCgLESbFNE) [whale](https://solscan.io/tx/te5qoUWBiuoWJhKFDmQHH1R74DeCMCiqW6kxJLFBT3mQiny88xznYuvqsZFEnV1Ainox7EA3nL7b51B7q2MR7W6) |
| 3 | 00:40:32 | [E3ZytD](https://gmgn.ai/sol/token/E3ZytDKtKvjv3xrsbVStfmkRPdicH4kJyFaVTifWpump) | 9.5% / 4.94 | +3 | BAM `ALPHA6` | take-profit 0.5 s | **+0.0431** | [buy](https://solscan.io/tx/5uzfhb28azCFQpWzYTNFBwjuzGsqxLsveJfdaqLiVdwjiYsnKvK6USthAJxtaT3Bj3bhfNu8rTnUD56qYLGJnX1V) [sell](https://solscan.io/tx/QNxLftbVwCeBNLVMBuH7hu1wi2tbNY7U96vQC9c3bCqojAMxSS13MdWD19DCAC8HcXtFwUataUJyx2ka2PSHsLZ) [whale](https://solscan.io/tx/5Cqr8RBCpgGcS2kCBJFjS4W8rVMFPa5E1hMKeUYZVEtFx5SreEVbYmGqVo1Ww36fo3px6Y5x3vGzz7XHTACeabas) |
| 4 | 00:44:25 | [CrUpmS](https://gmgn.ai/sol/token/CrUpmSc1ZxDVxzm16Jj2GU99SxhEfvcKFsUxquN6pump) | 11.7% / 4.94 | +1 | BAM `G2TBEh` | time-limit 1.6 s | **-0.0034** | [buy](https://solscan.io/tx/62MTXAnrhW7zpYGanhTvqvpCQqpN6KAQXfq3fz7a2sFuJXN1QF21thTWDYNPHvoZMLWtrMT99aPPTR2unufBVx5Z) [sell](https://solscan.io/tx/3c1eLQmndB57F5zjXTVTVQYEDfq7RpQNRnPyHvVFkWPqSWNLQwXaGKRMW1CXLrXByzjPjnx6bLtrTaFDoLEST4YT) [whale](https://solscan.io/tx/jTJ1D6Vt9XkJCN9EY7bQsyxtkvqsXBAMhKzUbLBKE7ggVaFJyemgrHu64s3P4YzuMDqev7vp3ayBSfzJZyYKtop) |
| 5 | 00:46:53 | [2WTSLy](https://gmgn.ai/sol/token/2WTSLyNRZKtY4d8kS7QDxERNTJjSTFLKVsGJgyJzpump) | 8.9% / 3.56 | +2 | Harmonic `AicQr2` | take-profit 0.9 s | **+0.0874** | [buy](https://solscan.io/tx/3fdwmmT7Lpxq3AzVr2ojZJRHCBwER7N7b7gYevMwszuSbJGt76kLW9wXWYfNKHt7mM4ZM1vFkCRrrpt5P1DQSqih) [sell](https://solscan.io/tx/4sX5MfBjbaAayHMtWFxYP8csigb4QP7nViV44w6Zfra7pnijvPtC7L7nXxksM4RhZJdEFzZpcZqhzUUVoSQvQwXa) [whale](https://solscan.io/tx/5hgZ5m7wi1nkGfQ2fv95CUskcCRTyjxi91K1cp6etRKKooxiFL93am1cohh1Xk66LDm2Ev7XaSJgJCKEbZNAXJrr) |
| 6 | 00:48:34 | [GHbZhj](https://gmgn.ai/sol/token/GHbZhjDqiDERkSr5ZaDrsqLYFhe6YoqE1JTsUHjZpump) | 6.2% / 2.96 | +1 | BAM `5Cchr1` | time-limit 0.9 s | **-0.0566** | [buy](https://solscan.io/tx/4iyw9dHajVJtjhe3J8oUHUBPEtZpmtaKNQhrsBvyrHBWiBvsM3kEMTLA24a2Dh9aWWrFfbEw3ZskpsWeWnqHujFE) [sell](https://solscan.io/tx/5F1qviZdvdP1Kb7GEJpGaJozVKANnC5LyqkQpLA5n5NPPMbfZSJgp1XEmZ6sU6mBLdi2SQ1sPsvdW8pB7PTUk2yC) [whale](https://solscan.io/tx/5b1J9d4nNExjapcYXxJsrxUMACjP42s6fAdP4o5UHjXJG3Cnaoy6WEFQjwxEYKVTq2u7vCvMbh1E327yq1BZTBUj) |
| 7 | 00:48:40 | [5d38UG](https://gmgn.ai/sol/token/5d38UGXn817fUzwvAvkHPLDGfjGe4vDbhbnHtk6Kpump) | 7.4% / 2.37 | +10 | Harmonic `XkCriy` | time-limit 0.9 s | **+0.0373** | [buy](https://solscan.io/tx/iyjDmSdr9CXnx8fauVJnSwBqVmyRE921YWrb9pUv8Y6Xff17Z8Ato5bp1fepYdckVwVnm12jSYHUocjHN8uZche) [sell](https://solscan.io/tx/4MJv3ozC9zEzjWfuQropgPBhiZqAhtnuNXV2G51WVZCpMobgQRKKkCZrqftUihXB74yHAtgx1Fz53kmCVYT511Wz) [whale](https://solscan.io/tx/22nYCtBhgjhXYtj8bZYPnPvGtDXMzTLWdxFb5GHa4bAyTE8Xtn69eRHS6oNB49JS4Bu8YcwoAZUzinkycikJDsLT) |
| 8 | 00:53:12 | [6LLmbf](https://gmgn.ai/sol/token/6LLmbfrxhnuBhpeoMix2BYcBPDRWqKijUz6E5QRFpump) | 7.6% / 3.23 | +2 | BAM `BLUEHG` | take-profit 0.9 s | **+0.0557** | [buy](https://solscan.io/tx/43SjCRszKKABB8N4NcC7hS2PgHaik4zdTYTYReCy581PebwUKuNVq5WgqTmBz8VgBpeZX7jVmGzeGXSL9JpgHX25) [sell](https://solscan.io/tx/54Hi2dFo6hQBjTduhRFRevR4UVd93sHXZNJqEzz4xiXwAMuTqZfaaBz3gQXPsEv4EPB7Y6WwcNfwwKxccVbyuYB3) [whale](https://solscan.io/tx/5QvPVAwBTpVfvFavvftcdHLJjMW93xHDnE72MoVxG3oqp15Betr6tmTMP3wd6Gz7K3ZViowLsExpHxKMBWzLwBU9) |
| 9 | 00:55:30 | [5GQUhn](https://gmgn.ai/sol/token/5GQUhnJETFW7sH3iJhCDAVhDCboithyeL7SJNvPBpump) | 6.4% / 2.93 | +3 | BAM `57i31U` | take-profit 0.7 s | **+0.0499** | [buy](https://solscan.io/tx/5BsTrKXgSGekdjoozW4J8jB5JMUPn8uQdC4QcMvKX7tPvkrGRXcoHSVuMiSMfR1T3mgfK1QEbmVYbN6yzPrjQ8hW) [sell](https://solscan.io/tx/3CTPAvQnisDnsbAu6Cyhv83JjUaSNB4kZzioDfxrtDfaZGM6BUMKy5orC6xaqYCT4kM9ArmQExuBzLaPXc8YUTch) [whale](https://solscan.io/tx/3Ls2Yj57Qm3Ann1mhsRo9i14Ji3AXugMjw1jipDHe892Ykrff3sr85Gvo7f5NWJ4wYcVetQMH6KnY7SVmXnwge8c) |
| 10 | 00:58:43 | [CGmRM1](https://gmgn.ai/sol/token/CGmRM1dPWG8wiDjgffkS4CoxKePad9m2JhrAdZH6pump) | 7.7% / 3.95 | +7 | Harmonic `FBKFWa` | time-limit 0.9 s | **+0.0173** | [buy](https://solscan.io/tx/36k5NuJ3QipWjetMYzFErTRkoc59AQhM81FZzMt8ZGScej8g7NZiwiKVgKpbnanuNpKzJimvBkU3ioCm2hFUsNwT) [sell](https://solscan.io/tx/5zLq7KiHEC2oeHHCT342fLMrRBMJgmTY48eMiQrKVoRN4reBDP4HKuuvXVA7m7MnEE55MnVb4UfwCumoUaDjD6jF) [whale](https://solscan.io/tx/4S4znYHJzWYdTPXaqYyZavgzVoAodGK7xkgm56iFMhx8s959J2eYrFNvfRHcnsTV8Fscq63zkpQxugVbS2g3EKn4) |
| 11 | 00:59:07 | [8cj3mS](https://gmgn.ai/sol/token/8cj3mSqgEavZ4yAkWELHuSjjtzmfqNDAS36618yBmZBi) | 6.9% / 3.95 | +1 | Jito `C8Bey3` | time-limit 0.8 s | **-0.0308** | [buy](https://solscan.io/tx/MSAWxAScji2ZJbJMEsjmSuBvyvFfWcG76RAfGDjAm91exo7XvoxKR7oK69bR4sWD4jXa1ykEK6Jo8ErLUUBmhpZ) [sell](https://solscan.io/tx/5VY4VDK79NztXCiarPFJR1fLaGRvaAcLygWkmemeMqykgXh2ZrRLXVE38q6CYS4asevgbWpqVGaM1mysGEJbwZ3i) [whale](https://solscan.io/tx/5pZbjSp61ZM9y2NUepT98eNYiLKJWMctTT3RjJRSEA7aGZkcdC1YaNvmYNtaCSuxR5TBd8CDH1qF8ni3zy1n4mEU) |
| 12 | 01:00:47 | [5wkFDx](https://gmgn.ai/sol/token/5wkFDxhBpHdpPmWi6Zgso7W2eXuWK59mYk3SRPEASsbY) | 7.5% / 3.46 | +6 | Firedancer `JD549H` | time-limit 0.8 s | **-0.0186** | [buy](https://solscan.io/tx/2DzqDuGn83vgpzvn7rNa77Q5y5tbGZkFKvNfvGyhP1gEbPExCeycocd4bDWLiQCndPVsSWHgJcwV7EeHXQnMSnCi) [sell](https://solscan.io/tx/2vk5QEmwh2doqht5EmLTmkKarxgt8FGZzdJoyPgt92EUpDNJEK8caWjffup9GnLnoctrbnP8mmu61hmbAq9nqsha) [whale](https://solscan.io/tx/269NdcNfC2uhBE1rZY7kHXiPN9Sc4FphzygmTfkQTj53tBn5CD6CKp4VamkAgeCkzJ6t3oqeKkjo6HAUigD7qSkd) |
| 13 | 01:02:24 | [6PMwHq](https://gmgn.ai/sol/token/6PMwHqdWZG5ABmsshBHxqvLYU6Yyvcnwy2Wvzje3pump) | 8.8% / 3.95 | +3 | Jito `74MzXS` | take-profit 0.7 s | **+0.0764** | [buy](https://solscan.io/tx/2diCbR2Z97LQZeZkpNzBNJBAZ3vgtJSHucTz4xok6GgKbRQDfeFY3FSPXMVhGQL5e7exLrZpM26uZ8nrbkwPLiBf) [sell](https://solscan.io/tx/3ANddTBXtffWeVgTByAHaMC9NsbSFJYP5nEf9zS9s3jXoz9m4WDBbnm1JjZZVaxLwFv2rfLDUkPmY5k3FjtQipKU) [whale](https://solscan.io/tx/386tprjyeCnBmdmLSqaJYDCitewJ2GFmzWGgcxbVKrckVDMNKcEomr2SKDVetjXMjPCeyapq9WgfRKSatCKfY1wK) |
| 14 | 01:15:35 | [3Y7oEf](https://gmgn.ai/sol/token/3Y7oEf3KsM4NM5EhtZt6ZGn9vBShjnGzQdu38Gwppump) | 7.0% / 2.47 | +3 | BAM `2GUnfx` | take-profit 1.0 s | **+0.0431** | [buy](https://solscan.io/tx/67kA8tuDtVPdrDDjHMePRENpoDW4BSZdiu3crdC4c7Q5aZPnMoxUQvpjme1vX3xwfRjbPF2FfzpQcTywunpF7Jn3) [sell](https://solscan.io/tx/46LvyN3ojJkAmdRM2tgjbCS5Uf1ZNE1e3F9EVfFpXNuqrGzMkLhysjpHPTa7JU14WFGHNkRe4yqmaEBmA8Pw4BHc) [whale](https://solscan.io/tx/33xtYJ3CNcMFjiKZukLqHNaZGok59ekssrPqyDS7o9f1J1qyRz4wWhankpkLVfgGGNS7DUza3j8g5ccsgNNbrHKK) |
| 15 | 01:20:02 | [HTzivr](https://gmgn.ai/sol/token/HTzivrfXpuX5YpGXAATvmb4MjvycUhku1ZH8ewrLZoo2) | 6.1% / 2.96 | +6 | Jito `E1r4Ps` | take-profit 0.7 s | **+0.0628** | [buy](https://solscan.io/tx/24GVwZ6VqHShcQqDFUX18SBcjB5egCFUiFQrnhgyjEhpcNBrKF3wvU2mmse9yEEK9SxJQNWTzwV3zUZngJr76dR3) [sell](https://solscan.io/tx/2mp6cAPWafHGaEMNpbdHRBfXT1YTX81gEnMq1sTDdRAvsN6hzrsqZqDW2N8qA3efvANDDgA5HPgAMpdU9A3XLamJ) [whale](https://solscan.io/tx/5iQTibPWAtrfStCbjKyNKTPkwNpjSgVTqurPmRhBxDqYrryjaEMhsHpWDbeGDoijwqZkoDy3YhgyCX7EWSp9pe4o) |
| 16 | 01:27:56 | [FgsSTa](https://gmgn.ai/sol/token/FgsSTazXwy4pxjrNMuzsQbEPbYPjAW17pAN8dfRHpump) | 9.3% / 3.46 | +7 | BAM `E9hD3i` | take-profit 0.7 s | **+0.0634** | [buy](https://solscan.io/tx/4pF3hC7XBnWPyH6AfAzg9pqghKPTXSdNg8mRNHz6wHSFjpnJGvCqwcn9zvA5Xe6dHBFoEuCzDqJ9LNozKVJPJ5yg) [sell](https://solscan.io/tx/LtFm1ogz2a7tY3jbWrMJMokCpRbNDm7e7zS381BANitbSoTesxrjB1ZL4iT9a1EWrGyWVFEQUpFf7ySg2TaUNft) [whale](https://solscan.io/tx/n5gW52znG8KyFdiVr58FxjUCfkcF7dAPm3FgnZfeJ8ogmsEbjogA1kJeWCAe5dVpaHaMWnBTGLi4ehVvEBu2z3b) |
| 17 | 01:31:22 | [5XvCVm](https://gmgn.ai/sol/token/5XvCVmV8DbBXUwbwLYMPgou8SuhsWyeeJyCWKdDrpump) | 11.5% / 5.22 | +2 | Firedancer `HW4zor` | time-limit 1.1 s | **+0.0324** | [buy](https://solscan.io/tx/32GB7EUek1oLsMqjayGoPiWbfpzeSWY3ds2X5ms5GLWzRzUw1u783N349tzDgpMq7WNUmtxPmZiz9mZuRJKbteFA) [sell](https://solscan.io/tx/5DGjeeMyC2xRcLnpsiCeXTAW3ZnNGr1TNd7Yt8P2zL9k1th5BgJeHsUwLDdyQqTi9m3AmKmcnf23siCZaVA8TRqa) [whale](https://solscan.io/tx/2t8PWz8xX6TwHuNdCXpnQWsaQcFNj68dK3yHhEQKKNXgPYyyCB7dfzdQtRXcWYupk4HHxq3NZGiiEU8v91dryJB9) |
| 18 | 01:31:23 | [BYSwyK](https://gmgn.ai/sol/token/BYSwyKP5Xj3kt3fMNExaXrXRYqp5aPxbH6hSGQ3XDUuU) | 7.8% / 6.78 | +2 | Firedancer `HW4zor` | take-profit 1.0 s | **+0.0285** | [buy](https://solscan.io/tx/23hzPQftuipEUciT14aEbjjPWUKT1szfEvit4DSPkFM69bDAhMBAAoBtJGfiRkCJt32V55o9UzX1UmeK2kZM5g2z) [sell](https://solscan.io/tx/5GwWCAsoit8XLE8UNowHBdaePrfhedHiZKMXkGBzFcM63EDJWdaNDovjkifKzVXFQYA1FA8f8xq7QM4BXi5kSz3v) [whale](https://solscan.io/tx/YoFPsB1v8mR6oxpyfZ22e9htVm6E8cCDWrc8Ck45mkFeh7hEqt5xbdcsYfoH7EFiNaa3xBUzASZnDW2o1afE3HW) |
| 19 | 01:33:49 | [8YyMvq](https://gmgn.ai/sol/token/8YyMvqcZpBqNvubU6fuuxTPL72vpUpVWBpXgAjEq8Y68) | 6.5% / 2.95 | +6 | BAM `G2TBEh` | time-limit 0.9 s | **-0.0146** | [buy](https://solscan.io/tx/2ZrR6gi79JWzkT2MWvqX3VpsnSseRZmUB5UNc9xGiRHs1jfroDRDRyN5YMP2VR28ZKru94pKJEQF8yNYFNfASkx7) [sell](https://solscan.io/tx/2CcNP4AjSB5xrVmS9uenYQs8Dqq5crtwc9cP5sH6Lr3B8UCM4R1zfARXCYvqWcFQ78hfuYiKzAYWD4PQLuitnSYn) [whale](https://solscan.io/tx/2yKbewCYE54mQFWS4KZiPQTLv5EUvRWuEERN7wjdc8PBkxw3gZmxLX7cSLPQjGzLNruxyDNGKCZ8fHTc9qm7q1av) |
| 20 | 01:33:58 | [6ceE4K](https://gmgn.ai/sol/token/6ceE4KH4MWzXArmchDANuqEAdTnNC8m4A82rP4yepump) | 6.2% / 2.81 | +2 | Jito `E1r4Ps` | time-limit 0.8 s | **-0.0089** | [buy](https://solscan.io/tx/4CtR2d8U4KEd33oxbq6eATLHtByFkBeewp2pi8fXbQc1bCRDKm5mcDNWMfAfZAtksEdzxReCgSgJV4CPzwNXG1Cq) [sell](https://solscan.io/tx/56oyHMFBwxamZQvcndfr3pxJEeYEvEXAZgCWCtPbkc8M3niC4GQDvY6CuxQ1fQx5WyVQqxKMZ4eq1txjJobYLm8P) [whale](https://solscan.io/tx/5meqeBnG8BTEKcEqC5udHJEf3XTds2xmvGFofPPCyJJ9CTAwkabRy3Veyz3t6Teo4Cd7ykcWPWqnWXQkXfbBfLmR) |
| 21 | 01:36:25 | [DqCu9S](https://gmgn.ai/sol/token/DqCu9SiCE2aqd1G8DrdN1aJMk5VTTSTaSM8EsvKNpump) | 18.0% / 9.88 | +2 | Jito `ACvL73` | time-limit 1.1 s | **-0.0182** | [buy](https://solscan.io/tx/5K2ihq2nmKS7Btjf2762TPoER5d7V1d1dPuEzVUTUYH3Qq3xytucQx1fK1H3BnrnF9QPfx7Rh3LxM8RCsnxbzdQV) [sell](https://solscan.io/tx/5Ayuu8FeF1tdtAwAZJETh1T96crDzCaZMptorWkoia4i8RHB72bfz8F29WdXuiCdLuCkdEkBdNtiucgweV8F3LKs) [whale](https://solscan.io/tx/2oudwh37ezhcthh9dDGDKRxqvKcECCAnbikSgH6hfuRVcCLzy46Nk2jvWe9tmspzYxyNFMNK7Q6spBFkABuQV5AT) |
| 22 | 01:37:21 | [G5zquu](https://gmgn.ai/sol/token/G5zquuSgY7oYJXSRBQwxosDMRtnFA22oTm1cxoS1NYif) | 6.0% / 2.94 | +3 | Jito `HEL1US` | time-limit 0.8 s | **+0.0017** | [buy](https://solscan.io/tx/5P3s9wJJjdomdWq1gS7evBkGJTcBMpPe6hgkZy8engVNBwutvzRX2DUqaKkPnD4ZC2xrPkpi5tTa7ftPzhvBzP8m) [sell](https://solscan.io/tx/53JJxHEkeSScQJrZr8XMNUovqWr12BnroSqSKockHTZca5RQ9cmHGmAdy8YHD9nPND5cichxUs7EDus43FyEwwMh) [whale](https://solscan.io/tx/4hUQiAWRJNnj4rdmDbinSqAu6acp861i6Kg8rsWM3fnZjcuku6ad4MzYN2qfpSi7WjzXPa1Ut4Ta6WM3Rb6dVS6U) |
| 23 | 01:37:26 | [q3t7qF](https://gmgn.ai/sol/token/q3t7qF9b9tz1GrA2fCbRKScek1Mshr1BvASH1Eqpump) | 6.5% / 2.02 | +10 | BAM `DUND26` | time-limit 1.0 s | **+0.0014** | [buy](https://solscan.io/tx/kZEG1JCE4PiT55Xg3dnpi3QHRGUZ6jXqBnUndVkCbocF9yS7hcsmcAsA5eK1AprBfMHNuFAd5hzcgXMTG6HUxrS) [sell](https://solscan.io/tx/3fcM6ch7hyG7pqrq5qRrbCjfCNnb6ysfPvpuFxfcraSrDE7jVAkcQGfc35C8s5govwdouxK4oPe6XCFJfAM3D5SE) [whale](https://solscan.io/tx/33ZKQswWCfpfMm5aUmohAvqCS18tn7h7bkxyCJTx9vPTirC2AhWyFzSmm8RB5WoHAjvhNK7KkvUAMAR2qaWt457J) |
| 24 | 01:37:27 | [B2kHXP](https://gmgn.ai/sol/token/B2kHXPGmwaPa25mHNLr3RgBoCfJjzqiQZb3CLwvscv78) | 6.5% / 2.79 | +6 | BAM `CMPSSd` | time-limit 0.8 s | **-0.0025** | [buy](https://solscan.io/tx/4Nv6gohffb9JnM9QPwzkMED1bs6nP3SodjBoR4UivdsgDPcjEByyxbYKN9SAq3zB9rD1x18L6uYjtpidf4fqGotr) [sell](https://solscan.io/tx/5sWNv56dMdT8YgEkStxuSBNLi731P6Zjk4XDSuWwAR3LSumF4LL2GY5BWFugQTaRvtSnkr3dGKVV26YDq39hXwHW) [whale](https://solscan.io/tx/4QHEaccSCJCaqLWF2rwz6emHJShUgU2LBGNSWBuwTNTsQLc3XAhdVbS8pNmoyAV1BMo9E7JXSoP3yNvL2ckPrSFx) |
| 25 | 01:37:58 | [BqPwD9](https://gmgn.ai/sol/token/BqPwD9GMMcfE3ZmAu3B2UxqQTiT1GuHGSer8d8h3pump) | 8.7% / 3.25 | +3 | BAM `Fc6NNd` | take-profit 1.0 s | **+0.0614** | [buy](https://solscan.io/tx/3cBJGgNFw6vkfQPDeoeVHjbt9faBwE1usdMPw68TTTAho2ygyxk6SanuCoj7tjafvhmxXBiH7hsyjiQv7aa2f6oC) [sell](https://solscan.io/tx/3ayZC5eMQYLPzcoxnVYuDUTawdqd1GD2GpJ52uif9eTD7XXyAyxG2wNyoCS7v25EVzU9jejaEtYrTUabtgJyyXb1) [whale](https://solscan.io/tx/4u9TfDSyBbE3q7uHsbnXR7DTFCgLchNJbmPMn5zcsuFtAMk2gar374h82exV9YpHqBUouQncFxtVRdmKajqv93hT) |
| 26 | 01:39:16 | [xUFKdT](https://gmgn.ai/sol/token/xUFKdTaVT372o3C4AKZm3XpFQrTk4CbpPRP78Ud82Qi) | 6.0% / 3.56 | +2 | BAM `CoG8d9` | time-limit 0.8 s | **-0.0435** | [buy](https://solscan.io/tx/D3CdJwVLiU24RuVo6WxAbnE7GBLYxDPuro5fuvqvPxnSTTzRSDo8dETwqW9rVJazLvzE4tyMEcgQmin96msKZJ2) [sell](https://solscan.io/tx/2rvnfNMokNfzAkET6D5CT1ZNRYDNusvxbMNb9k56VsrZEvpNRxgnhYwsK6rGbfk1TJKhAscduM6YgepJtpbcYpJ9) [whale](https://solscan.io/tx/BSX2Qo2MdSJQQfxpkfJ4mtjMt1zbNje6jkWGeAvCPMRXQuURuFdM4H11hjMc82bzAD7AV5UAVmdcUUwBjqrJman) |
| 27 | 01:40:17 | [6Xqaho](https://gmgn.ai/sol/token/6XqahoBeXa6pgZuXfwozmYgnnvUnSFP54ipT8uycpump) | 9.5% / 4.17 | +6 | Harmonic `SFundN` | time-limit 1.0 s | **+0.0401** | [buy](https://solscan.io/tx/4JXVLVwayYBwqUZcEQzQ7gRnD3ZwJYZfLjDaJRHZb978gBL7fFmaDRfgP2mhvpNnVgK99cbm4ropoJvfjwr7maJb) [sell](https://solscan.io/tx/3x7zLQhT9HVmt4n5vJ92UPsX9JdQ3JcCMCxoy9GmNb7iDGHcFLDiLRJouvAbzoHGsuqmRodEpqnFRGGthkizTjKH) [whale](https://solscan.io/tx/2HwYHLk3ETxn2i8bM52cVFi1rNF8qb5ydfF4BtcdMY6pLpBJcSKRLkkyV97eUg6uheHkAmTGccsFdAHcrb3xJh5b) |
| 28 | 01:41:34 | [A7WSdJ](https://gmgn.ai/sol/token/A7WSdJr6qL7Di8dyJQ6bzF3x2GzqNkwgzC5fJVQHpump) | 7.8% / 4.94 | +1 | Jito `E1r4Ps` | take-profit 0.9 s | **+0.0476** | [buy](https://solscan.io/tx/4ex9vSX2hhTcbCkJWo6KMZdfST9SrR8Ux9quwmDwjkd5y4E9VTjAytzmqXpYJP1J6jSq7oEhSFrEBVvd3MC3ifFP) [sell](https://solscan.io/tx/21B32B8bEwjVpCqh2rDX3ipivaEDKJVs2w5b17oNRtEtKxvhM2AU4B2uPkMAWfYtG2T2iUMa7RUE1q6ywtvR96Mg) [whale](https://solscan.io/tx/5SRYZxcN6q3SRj6WQPq5RwQHwJCafuCfGaaumkh7ZCDpQGXUE7qJrzUqeRpEfJEb8NZLhKYqsKm4LfJ9VEhZbsVW) |
| 29 | 01:48:52 | [FxLjpv](https://gmgn.ai/sol/token/FxLjpvGrtML7uoqo7FEVL8epDrTEF9fmfh6zikxEpump) | 6.2% / 3.46 | +1 | Jito `C8Bey3` | time-limit 1.5 s | **-0.0078** | [buy](https://solscan.io/tx/3V7hbFuQi1D3PshP6PDxij6t4X1oLrnUm8yvEFjSqPeKtTfachY1ozCDTfFZLQax229NbKAyM91SkoTdfEzDq4eK) [sell](https://solscan.io/tx/ZJEUoLX9vweBYY1TjHbUB27KQqG2RcNr4TDjqjoqB9c6RAkhMAToEXETJXx2wZGjrMCWjtcWeXLpWJ3XSXF9mb7) [whale](https://solscan.io/tx/5BG5VWHoNFXnniUL5WWbhM7iEShbpRMryx5Tcsz7LiQRHW2ZtK8ePiL9EP5EK6u2WNyHUns2ULJmZQbwgi45Ai5R) |
| 30 | 01:50:25 | [HEoT1o](https://gmgn.ai/sol/token/HEoT1oFpbVnbnKYD8BVAD3NiK7c4k4CJuitmRmJ3SwGg) | 6.8% / 4.94 | +5 | BAM `AoB1wT` | time-limit 0.9 s | **+0.0298** | [buy](https://solscan.io/tx/4fUhymVTfAvqgpoYYAncGQiyXuMT5uhk9642xmfjC5wKJewn9mEUR3utAqXjPnYTcpE1SWGxgxNGUkkPq615TmQJ) [sell](https://solscan.io/tx/WF9aw31BfqKVjzt6uAmrPnQeR7rHb7PHGavnpCAEHRqE3MidZWGRNrtQ7TGnJJC6TWfiykcQJffxSDu5MziBb7W) [whale](https://solscan.io/tx/3gtkYEHLe19WD317kWa6X3K7Jngegym4jsZBG7Xjs3rrAtSWApTvEHzrKyPuEunHFQavY9w5SuKmtcszAv8ipM6G) |
| 31 | 01:50:53 | [HEoT1o](https://gmgn.ai/sol/token/HEoT1oFpbVnbnKYD8BVAD3NiK7c4k4CJuitmRmJ3SwGg) | 11.5% / 4.94 | +1 | Harmonic `DrifTr` | take-profit 0.4 s | **+0.1249** | [buy](https://solscan.io/tx/7ibdxfWFYsP74ZoTY6zJF7XQBPuHwnzSFm9d2xG2jqkzJXRpPqL5n7wTxJ2By1bYkhVrap9dRwZPrjj5qVxaiYj) [sell](https://solscan.io/tx/2RM4NkVjKdQZ61xuis7eNapLfvCm9mdCqY8uLATavjepSFJrEHhTPPL6fh4oNhXCZHDv4FptkgGxeJTntKxWAXFD) [whale](https://solscan.io/tx/5xYH2EDeynRRLzXhqVm4Cw2DJ9YamYmbAESbHbCSfh9TPV2rxxmFKXFqZDxj5wwmfdSRzberijj47ZnmsHdgpXVp) |
| 32 | 01:54:44 | [2amJAC](https://gmgn.ai/sol/token/2amJACSmY9JnLiUsUo51CXNUEKtLKBo2P26P5HdQpump) | 6.5% / 1.98 | +3 | BAM `DRpbCB` | time-limit 1.3 s | **-0.0415** | [buy](https://solscan.io/tx/5Dgii8BMhnBxhKQ1dW6Q3EctxgJdRuGqtH2TN31gRYNUgYbzRCAVwpH9QQzUcdw3TuGa25CPEtLseqvCeKY3YiJP) [sell](https://solscan.io/tx/5wm8HDKVUXfV28HkgHPhjDaQtnE3Dq645HGv4yhx6fBx8xBpPLp9Liin9sChZ1Y773eNZ3RLXLKMXKvubyE4hCNm) [whale](https://solscan.io/tx/szs77DA2fxfRuW4F8N3hYpCBarLBnBZKKp5U7UAHkjmvm89gJUD9kt8t2PZ9ANMCgvG7AuNoRqsVHurXmqgP1rF) |
| 33 | 01:59:45 | [C6rMWa](https://gmgn.ai/sol/token/C6rMWaqjtVQR3fGP98GLZGMaaTxRPXCy33V3zFiqpump) | 8.7% / 2.96 | +6 | Harmonic `CW9C7H` | time-limit 0.9 s | **+0.0063** | [buy](https://solscan.io/tx/32Aa2wEsbR7qTf4oTYjiELKEHwBkkDjAuiT6o5pvyKMSaiJH3zRPKBqpnEdeY21ga7NBX5KZELKA5aF766p9NZf6) [sell](https://solscan.io/tx/2wLedDdYcy4UT73PMNDfGhrnbVtv6QaDtiu2oAnm9NpSt36VaLCuL8FeitrMB3KVSY5MiND3UdLMCa6aToYWHmS3) [whale](https://solscan.io/tx/5ma9ws6LfiMXhURSVtoLDzXxUiBCyyPqgtLc54TMcUGcuAde7sS96bUXGRR5yGViEYyYUTwFNga6eNtniCoYXG6r) |
| 34 | 02:04:52 | [GC4hpX](https://gmgn.ai/sol/token/GC4hpXq446vk6eY3yimTDaApZ4HPRtHgssFB4BVupump) | 6.4% / 4.94 | +7 | Jito `Gv9ggu` | time-limit 1.4 s | **-0.0423** | [buy](https://solscan.io/tx/ku8ercK2dnMMjStwai3pg7GH8nJv9z3F1m7seC6SjgVM8DJPsQDK9B7gousGAyRqnfWycpCX6HW8kKFSwPqALhZ) [sell](https://solscan.io/tx/3C5YsAUfVqSwxjkTCub9tWHVf19n6tqSn8MguPwiif8uEpDQ1D8BmrTmkKREAFsA8gKyQTVd9WWJruUXiNAwuaed) [whale](https://solscan.io/tx/4tVNFFWk4bmsHSLebFJUwrBpYdXHjhhJsqJriFr2kUFTWfqXdqLktv8Ejo1pSN51cLhjnbN1UCn2z9zwTX18v2pB) |
| 35 | 02:05:55 | [AZJNx5](https://gmgn.ai/sol/token/AZJNx5CCZcAXjZ5NKEJRsZNqYswbpE9PKyP3gvkPpump) | 12.4% / 8.29 | +1 | Harmonic `Fd7btg` | time-limit 0.8 s | **-0.0149** | [buy](https://solscan.io/tx/5xEqo3wQSdRije3bKhffAYkRJyGFxUbHh7BSQCCVhrrkAuNWGtv58NjJAzTTHy5GJCBHUo74enQu2F93cnzkNsjV) [sell](https://solscan.io/tx/4B9Svfrxbc1eEoj1VyyMRihekrVfqz4AVw11xba9j1eDGHRaXWv3aUS1b62S7XPgnnvbMtjV5ayzHjw72btgtZAp) [whale](https://solscan.io/tx/3paFKAzsciZLPMn8xXGpBkyDgxj5Uohw93pBfNY1ShC3875HkW4Sa4YLYodbXXAFeDcz8oC8pVuSeLDvfm5D241s) |
| 36 | 02:06:25 | [Hvdhzo](https://gmgn.ai/sol/token/HvdhzomsGAR5SK6dDXh7TAR5hhYbotC29hfmqwvvpump) | 6.3% / 1.87 | +6 | Rakurai `ana2y2` | time-limit 0.8 s | **-0.0146** | [buy](https://solscan.io/tx/3J3BtTCZnuHd8ecG4azwXoHy44yCYztHXNdbM9zJE1zU92XLUAqXZiLDq78bgXYTY9ZsyYSTQUq1AtHF8Bsaihas) [sell](https://solscan.io/tx/46gcXAuvMRgKJvYt6EhMLcms2AxyTxtwkJNn3Xu72yyTcMXvfmrA5M7JAdJhSy8QyUo9HJA8kNak5iFyaL7eYtpC) [whale](https://solscan.io/tx/uFMhnBAke8jFFVfbeUifhRxfa4kcNdnJqieZJEiMzMJZYENrFxo4UaKE1aempcZfm9mz5DHtccT5B5Z1DqA22Af) |
| 37 | 02:13:01 | [Fdt5gn](https://gmgn.ai/sol/token/Fdt5gnTYf1FpAWVN8tjWyfCCbDKVA5Zwt9n4bZNSpump) | 33.0% / 16.79 | +1 | BAM `5Cchr1` | time-limit 0.8 s | **+0.0412** | [buy](https://solscan.io/tx/3dixw2yCseJsZEvcuRS3ZS4YBK4ENK1ZaTZqxf33YoSuMykjiYSSjidd4YJKmRoAdz1a9ReXSXcQv4m3o2iPjZMq) [sell](https://solscan.io/tx/4V9X5HNPt1QBs81msoEztCrvVLux9JT2mMG63tTanNKPSYZY6PaaS3Wxi2uq4RWQTMoMo7yaEDsfEs1ipvmtsA7Z) [whale](https://solscan.io/tx/3GfhGuDiPG47b95zJhCF85T1zb2VKQngzhAGf7DCffa9APWyVizeHRWAwtLGdG1LxaEBWrxeWVJ9bJv29sEkeQp8) |
| 38 | 02:13:17 | [EmwwCv](https://gmgn.ai/sol/token/EmwwCv3nkribTLmkZ7CFzC4Kert5LpgzGETMGYyqpump) | 11.8% / 5.18 | +1 | Jito `C8Bey3` | time-limit 0.9 s | **+0.0172** | [buy](https://solscan.io/tx/42KogabFhNxTCCVAFFRhGr5o9Q1CtGVVkrk2e9xzqxW7QyRwa87C7UCbkKWp3NZLYNqtjiKLsjuZHNgQcAt9pz3V) [sell](https://solscan.io/tx/4NKLw9Q7WcvA7vBkfvHSXdHQ6ixisjQswPi7fQwmLbXtosQPazkC8LJpQf7Kxzox45wKpdcnAiSkN8zb3GaFNqHV) [whale](https://solscan.io/tx/32g1Jh9KqQqSUTcBp1kgtDLWyoGtuWozLDQMJ7j2YyKJPQcqB7uxSNDpAMp15pQk1r6ByM4HhBy7XkrshVk2VY74) |
| 39 | 02:13:24 | [EmwwCv](https://gmgn.ai/sol/token/EmwwCv3nkribTLmkZ7CFzC4Kert5LpgzGETMGYyqpump) | 8.4% / 3.24 | +2 | Firedancer `BbCQMW` | take-profit 1.0 s | **+0.0440** | [buy](https://solscan.io/tx/2hZ2u7fYpVdTGk2ju3UEcG1Uz3GgMH1NjfhiA4okEzH82yyw9nReUN4XVuwhaSwEEtTsdHaoVFVx87hdMvwSovSg) [sell](https://solscan.io/tx/yKp6T7ABKLw5mCvgpgRgjWQUCgNYGVxwtnt49HDwnuU3zFcqxjA9yHGA8b4ENvNqCUQ8u6HWndwt8ReTiVz7Z6k) [whale](https://solscan.io/tx/3JQdAsqvZNyf6JkUcqFKP7mDZQEDGFVrrTVjx3jGwJkuATguYM7RNBakywdMBpZd2rwwBc36fyd34wSZCepNQBW7) |
| 40 | 02:18:54 | [6ZZybA](https://gmgn.ai/sol/token/6ZZybAMvJE1n4gBPwSzQBfRJpLfntPakcvfq8qTrpump) | 7.0% / 2.96 | +1 | BAM `ppppoq` | time-limit 0.8 s | **-0.0089** | [buy](https://solscan.io/tx/TcoVGetjEhxu4m2BcPWNszoG9qYZET3o6T7ouu2YpYTLz8YRZ6tdPbBg7Av3ayaBjdxsYeQQXnd5mLRfS6gXJ5w) [sell](https://solscan.io/tx/kEaB1yJZYwvoVTqy5ByQxkBwfsWfVCnwhyYvh6oA3EaJbkVeNuJ5yj57qRjSkNpozsZgnR8DJfF8dvXZ7nth7Eg) [whale](https://solscan.io/tx/HJMZvy8AeJV7AqcWkeZfCUXTtfZ9unbCKsVF9Z52EeL1VrfsS3Z9PtDcgWqfEtgqtLpTMTXepLYrY5FZHvPkpAe) |
| 41 | 02:19:36 | [D2ULbH](https://gmgn.ai/sol/token/D2ULbH8e8fDYg8k8wHfFFMXXv2wKN2yVB3RUQqpKUUeg) | 7.6% / 2.96 | +1 | Harmonic `Fd7btg` | time-limit 0.9 s | **-0.0221** | [buy](https://solscan.io/tx/2yijSdwYbapS7SyKpZXi92YDxsP8onsVhNf5T5PNVimFYRzoTSDnpE7YUKz6MR52wFU4qsdG6beC4k3vZ9SNZMrj) [sell](https://solscan.io/tx/4uuK8Q2TnoohKBkvbsRwUjqKERBCacgjW2fheYes66nw16KQSVVmrc6AC7yFWRAYjep8SsVPqWattx7aMjeg9Hik) [whale](https://solscan.io/tx/2opr6jgba7Psn4JQMjqUQ8eHDbHqDSiBQoC4vHVZPRnRf1yQ8TebqX28AZLbCuUcBuymw4kvGjNtw5Jvaep4RXSM) |
| 42 | 02:19:51 | [GgHr2j](https://gmgn.ai/sol/token/GgHr2jrLJzDkTizDHyUJSwfG9NFRRF5eKckHouVrpump) | 7.2% / 2.35 | +2 | Firedancer `4VRs6A` | time-limit 1.0 s | **-0.0363** | [buy](https://solscan.io/tx/3ruoCFad8qd6dvKinrpEFQwc21SbDekrTyopUjZpLY291HCM9abKtUy9p3gVsUSpDKtz9PE87Zdtm1jDWtReF6W7) [sell](https://solscan.io/tx/4pvwLW2ZncQYhJrjDFMvK43jS8UcM5b3bcAXf7hNf75W3G4Ncwdko6XCXKYBJYNeKq6E4gazQXM512epCF5UfHWU) [whale](https://solscan.io/tx/5MjJGr6krAVbCF3f9ZRcoyX5GDLV4zb2ZMbdBbicKFaRqARe8PSyY3dqumvWEetoLKYgh92WLZYqT615ZV9wyjcP) |
| 43 | 02:19:54 | [6UEAPt](https://gmgn.ai/sol/token/6UEAPtiRBg7gy6Gf3dKGCgQN6PwZr4r8zShGpQw7pump) | 9.0% / 4.94 | +2 | Jito `Ha1iad` | time-limit 0.9 s | **-0.0140** | [buy](https://solscan.io/tx/1kZsyfpfjYUSAbjZf7k1K8muWA9UMaLyTv9iTo1g2BbKt6NicJp99JjJfs1jvgxDqEKL6D5CeD7hHHpFpFb7jCC) [sell](https://solscan.io/tx/5oV9qDU6E6DrenftaYPzoFqCSgkVzHVsh6QDb6Carjmxjs5uohi5nicKU6XQ4k2qptBnqK4NfhEKrkEBX4FBhMyb) [whale](https://solscan.io/tx/1nFoZtdZZfVw69VFYXZCiNmwoVguqPepEKoTgAygGjjy7HGrZ7wvz1Hvqs98Lihe9FeV8X1re1vaPHdvwzXVEUu) |

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 11591 |
| Inside the envelope (age / drop / since-buy / size) | 5352 |
| Picks (score above the threshold) | 186 |
| Skipped | far_leader 100, spacing 35, presend_armed 9, presend_position 2, max_open 2, presend_position_open 2, skip_client 1 |
| Buys sent | 35 |
| Filled | 11 |
| Failed on the +5% guard | 24 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 11 of 11 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 00:32:37 | [4UTwF2](https://gmgn.ai/sol/token/4UTwF2eFxKF1ZdwqzF3qdcGz1twZkYFukEkzh53UxqYm) | 0.45 | 0.92 | 2.05 / −11% | 4.5 s | Jito `siidBV` | guard fail | -0.0005 |
| 2 | 00:49:07 | [935h71](https://gmgn.ai/sol/token/935h71UXEdRrWg5gZc7AMA8PDqHnXDBmogDeVuAqKHx8) | 0.45 dev | 0.77 | 5.53 / −28% | 2.5 s | Harmonic `pSo1KZ` | guard fail | -0.0005 |
| 3 | 00:51:59 | [DvKM5n](https://gmgn.ai/sol/token/DvKM5nfjUfFpFXM3gtqTSWFxmgYKJAuCawYSZ3z9oSpf) | 0.45 | 1.27 | 2.29 / −13% | 3.6 s | Harmonic `Awes4T` | filled | **-0.0391** |
| 4 | 00:55:47 | [G5MviP](https://gmgn.ai/sol/token/G5MviPXeWwUzLW3tExipfuTG3bg3GvgdsZbneFW5pump) | 0.45 | -0.94 | 4.60 / −10% | 4.5 s | Jito `EvnRmn` | filled | **-0.0191** |
| 5 | 00:58:57 | [GPAirS](https://gmgn.ai/sol/token/GPAirSs5D4dfnkRadAvoQPZbxLWaPCCXheTkTgaoJeai) | 0.45 dev | 0.90 | 8.09 / −38% | 7.0 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 6 | 01:04:01 | [27FhVP](https://gmgn.ai/sol/token/27FhVPWWjwRrBMqEnJgssFzRXQHeptz23Nf9uCknpump) | 0.45 | -0.50 | 7.00 / −22% | 8.1 s | Jito `8gDfqH` | filled | **+0.0479** |
| 7 | 01:09:51 | [E1q3Ca](https://gmgn.ai/sol/token/E1q3CaFZbPmJhRGBBUcQWYdhZCxcxkPkWvJaHG1epump) | 0.45 | -0.10 | 3.75 / −19% | 2.8 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 8 | 01:13:52 | [Fm1ksj](https://gmgn.ai/sol/token/Fm1ksj7SvMLG5LK2TDHfUcyvS4AJZ1rMujbDqn3nYoZA) | 0.45 dev | 0.70 | 12.09 / −49% | 1.5 s | Harmonic `G3a3iY` | guard fail | -0.0005 |
| 9 | 01:18:18 | [pEgDFY](https://gmgn.ai/sol/token/pEgDFY4tQyCtjtSc2NDZfrnK2RiEq7mBbF4T1e4AXZF) | 0.45 | -0.07 | 4.01 / −15% | 4.5 s | Harmonic `shftkx` | filled | **-0.0369** |
| 10 | 01:19:29 | [9W1Wdt](https://gmgn.ai/sol/token/9W1WdtBwZ8kekMb8xuw1aR1by6L4MfxniFcd8Czqpump) | 0.45 | -3.26 | 1.58 / −9% | 17.6 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 11 | 01:23:52 | [3rTUsi](https://gmgn.ai/sol/token/3rTUsi2LfktwFTsQsqzM86Kh68vL7psg6zaf55sdpump) | 0.45 | -1.24 | 3.28 / −17% | 12.3 s | Jito `E1r4Ps` | filled | **-0.0273** |
| 12 | 01:27:14 | [4QQZK6](https://gmgn.ai/sol/token/4QQZK63aUvn7VewYABC7su9HSauKke6BuT24u17Dpump) | 0.45 | 0.87 | 3.91 / −18% | 83.1 s | Jito `HEL1US` | guard fail | -0.0005 |
| 13 | 01:35:25 | [FaxcUt](https://gmgn.ai/sol/token/FaxcUtnGBpmBTzGRWWcEjUfzx6VAxkKe6nB6raSBpump) | 0.45 | -0.84 | 2.66 / −10% | 12.5 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 14 | 01:37:14 | [FrL1NP](https://gmgn.ai/sol/token/FrL1NPun3a8CdSajtgLYdi7sTFu5YNTHVERwgeVKpump) | 0.45 | 0.21 | 9.66 / −23% | 4.0 s | Jito `HEL1US` | guard fail | -0.0005 |
| 15 | 01:37:22 | [FrL1NP](https://gmgn.ai/sol/token/FrL1NPun3a8CdSajtgLYdi7sTFu5YNTHVERwgeVKpump) | 0.45 | -2.99 | 2.14 / −6% | 11.9 s | Harmonic `G3a3iY` | filled | **-0.0583** |
| 16 | 01:37:46 | [96wVc2](https://gmgn.ai/sol/token/96wVc2F6ULdvcEhjdycf9gsBp9YRbTGWJ2av8ALtapX6) | 0.45 | -0.65 | 2.85 / −10% | 3.6 s | Jito `C8Bey3` | filled | **-0.0728** |
| 17 | 01:40:03 | [2ePe73](https://gmgn.ai/sol/token/2ePe73YG4pW57pEwKtfQGCLBqSRX9N6M4neifdbcpump) | 0.45 | -1.80 | 1.52 / −8% | 13.1 s | Harmonic `shftkx` | filled | **-0.0772** |
| 18 | 01:40:40 | [DdNBaY](https://gmgn.ai/sol/token/DdNBaYGEd3GSezA7cGKMcuLiBkRy3PnoCASBCPx4pump) | 0.45 | -0.60 | 1.92 / −11% | 2.3 s | BAM `G2TBEh` | guard fail | -0.0005 |
| 19 | 01:40:50 | [6tz1xw](https://gmgn.ai/sol/token/6tz1xwF3tht8UPRZhk4psn75iBjbfkZ8TT39TFcepump) | 0.45 | -1.92 | 1.23 / −7% | 12.1 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 20 | 01:40:56 | [Enbsuw](https://gmgn.ai/sol/token/EnbsuwG8EavhbyiRuKpuZjjfSU2tcEHN6D9c2KKLpump) | 0.45 | -0.10 | 2.69 / −16% | 3.0 s | BAM `3JotfS` | guard fail | -0.0005 |
| 21 | 01:41:40 | [CSeCCG](https://gmgn.ai/sol/token/CSeCCGUdwGuq8KxqP6KpKBvK6omxSeAXtfqTwxKzpump) | 0.45 | -0.53 | 5.05 / −20% | 3.4 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 22 | 01:42:47 | [HWsZzx](https://gmgn.ai/sol/token/HWsZzx9r2RdB3vUxyXiwnkpGxTGi3jLV7ii1squspump) | 0.45 | -0.72 | 3.16 / −9% | 233.8 s | Harmonic `5ZqveV` | filled | **-0.0154** |
| 23 | 01:44:41 | [ESDMrs](https://gmgn.ai/sol/token/ESDMrs36GRYGL2RGeQsbR42kKeCmgBsvwZvsXbDkB3cs) | 0.45 dev | 1.27 | 8.16 / −38% | 2.1 s | BAM `9jxgos` | guard fail | -0.0005 |
| 24 | 01:50:30 | [HEoT1o](https://gmgn.ai/sol/token/HEoT1oFpbVnbnKYD8BVAD3NiK7c4k4CJuitmRmJ3SwGg) | 0.45 | 0.12 | 2.88 / −13% | 11.7 s | Harmonic `FNKgX9` | guard fail | -0.0005 |
| 25 | 01:51:35 | [GYjwaW](https://gmgn.ai/sol/token/GYjwaWNgTYTPgneYifUfDpsgaJRH1yqdQVBBuitJpump) | 0.45 | 0.85 | 3.37 / −14% | 4.7 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 26 | 01:53:37 | [4RuRS5](https://gmgn.ai/sol/token/4RuRS5qAiVDMBuF6eHF1rsMMVcdk1pUKFsrgUw8ppump) | 0.45 | -0.54 | 3.18 / −15% | 3.4 s | Harmonic `JUPiTE` | filled | **-0.0647** |
| 27 | 01:56:54 | [TA7Ani](https://gmgn.ai/sol/token/TA7AniuG6VoEKTBXFuMJWTh4BzByX64UwQfzQcipump) | 0.45 | -1.47 | 1.19 / −7% | 18.4 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 28 | 01:58:55 | [6FAnqB](https://gmgn.ai/sol/token/6FAnqBimTtvNJ6S6U4W1rPvtE9xfFEu166vhh81qpump) | 0.45 | 0.25 | 3.44 / −19% | 1.1 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 29 | 02:00:52 | [5UDrgx](https://gmgn.ai/sol/token/5UDrgx9iJtTq2QyfNvfeRxtcL8bFF8T1A2e6LhpMFg8u) | 0.45 dev | 1.50 | 4.58 / −24% | 2.3 s | Harmonic `TopjgY` | guard fail | -0.0005 |
| 30 | 02:01:01 | [4uQkoe](https://gmgn.ai/sol/token/4uQkoefutsTPGzBiW7V7hVvU5c4QSRtqkbB1AGjcpump) | 0.45 | -0.14 | 4.30 / −15% | 43.2 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 31 | 02:01:27 | [3vRtyR](https://gmgn.ai/sol/token/3vRtyRJ4rNbKoXHmRTAAirHxiFvDrN6bZn42F5Mjpump) | 0.45 | -0.34 | 3.71 / −17% | 5.9 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 32 | 02:10:19 | [92pVTA](https://gmgn.ai/sol/token/92pVTAsGmrHfoA7bAZ2Wweku7CJexM9dvqiLQgJfpump) | 0.45 | 0.67 | 3.24 / −17% | 63.8 s | BAM `SWiz7Q` | guard fail | -0.0005 |
| 33 | 02:11:53 | [5zkrEr](https://gmgn.ai/sol/token/5zkrErh4z6ZShtv5rFzNbkvc3yTqy6aTSyJyZADzpump) | 0.45 | -1.15 | 1.41 / −8% | 10.2 s | Jito `EvnRmn` | filled | **-0.0276** |
| 34 | 02:14:27 | [BsZM9g](https://gmgn.ai/sol/token/BsZM9geTYUPKfmV7eA8nw9FJ7evNoRfXdyaevmm8sUhw) | 0.45 dev | 0.70 | 3.99 / −18% | 1.7 s | Jito `HEL1US` | guard fail | -0.0005 |
| 35 | 02:18:00 | [DZF8FW](https://gmgn.ai/sol/token/DZF8FWDQpj1uTxYBpeBDN6czu96kuaaM4LxvTxdBvgwQ) | 0.45 dev | 0.61 | 3.86 / −21% | 5.5 s | Harmonic `JUPiTE` | guard fail | -0.0005 |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 125 | +1 | 4 | **nozomi** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt | – | – | [buy](https://solscan.io/tx/35zeW6aqvN38zCbYe1w9VD8Q2EMRE6yFSCapEiSzWABRtiZUpRFjbCj9G2NL8F4bPhkQmmCV6u6iEzNYwrwVs6DJ) [dump](https://solscan.io/tx/5u1KbChheEZC9QB4YzWqNwh4VggAp7pyPgiMAj9rs97LpCmisjJwhYnDsDBYWrNh2P5cAjkWfdoXTFUR7j4AUpUX) |
| 2 | 44 | same | 7 | **glaive** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/n85P6B48a5AJJNXb4emMB2WM8FZwCyqBJkDmZEd79fpnT3v9amLAs5rsxZ33JQhono495btE69bEXVPvCJNkvaw) [dump](https://solscan.io/tx/2mjFCbL2q5eS81d3kQQWCjJCLuBbyAjSqhdXEkXdsuPiHisscaPfAANYDJDg59ZeRgEf5XDmNmPP6sPcHJz6td96) |
| 3 | 40 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/2PhgQocAmGQn2fVZ8AxeAPwRpK1k2tqah7dvispGSCMCCHtBwPaBgfr7uB4NjpSPy7YYwmVb9sMXVSYLznwyhb5R) [sell](https://solscan.io/tx/3kddWPWYW1kYv4DfqAu7HfVPApE3HJEsnx5aSwgDd9zo2ht3xQUkSwQhr4jcNb4in6cmNxvptyuUpkjXk8EF1nx3) [dump](https://solscan.io/tx/3zxLeGKJN7pjMcDEfd8gDvrXr2WJhJewWBcXYZZpgyyRmx3PUWQEgyXjjT8iEXQtMAuai8VREKczA5FMXBxMMx5W) |
| 4 | 170 | +1 | 3 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/53Uyp1L4gFVjcgzbywA9c5SF3eGg2pe9cXnKBWvdEbZtsWgkMmtXbSmuUiM1aSch8UJfujqb2eHtmnPPQqBVXLF4) [sell](https://solscan.io/tx/3qiiGRe1m9eMYzjtKMq1s6s7PeS3F23h7kzyS8cs15X9ZqWTRMC3gYj6aogSgA6q9PY86N3JHKGi8P1v6hQKJPB6) [dump](https://solscan.io/tx/26dkRs2kQ6eUVRhQX2r2mdXsKzFK7K4GJ18ZxH26PujXsShoRz6MfA89ekDzPxs1VLhTM6PnZc9uMntEepkMuVtE) |
| 5 | 51 | same | 3 | **falcon+falcon-udp** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2Xkj1L7bKiFwfkNrisWTXSo1XmnBrVdxKGi87DhtcedrxQ5yPykrohmBu5TgTXRSKzDbA7jPpjVYo1ACJ6qwiXdf) [dump](https://solscan.io/tx/5G5AqQeHBbVCwuNNAiSrEnN8cZ4v4QcyxV3ZxxkNRLdHQmJjKNir6t3avBoeJ5HscwNYDoPFx4KBWy6zscjyjkJH) |
| 6 | 29 | same | 2 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/4uXEG2u9E2ZueJW1DE9yEpPEDoZcB8BZWhbQGVYu8Zcf4Aec51tuEkbsq5X3zoUjjNdnEXseMSk2asuYMymoxtSu) [sell](https://solscan.io/tx/4fQfnY4Ws6ZfHEKw5Mk7bpG5C2Ak3QTfpzAUj6X96j4NLVe4uA682ZjoTggSZoxC8eYiBoY3mmP8HxpXMmPR7gwc) [dump](https://solscan.io/tx/29CEeEhyGSmFwsaByPipH6jdG7PJ6U6k7x2MenoHgRguJsGwoPJ95KLRRnsKHTiZC1TNcjpMtafPejuWMHxQmCHp) |
| 7 | 98 | same | 4 | **helius-swqos** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt | – | – | [buy](https://solscan.io/tx/2pKTFM4JUymhUyXHGcUMBSxz4B3SS4zasobfj8Egbc2Wn2h1WoSRNBmwSBTw7xu4pdeCBGhFKcMFEZt4tZN7r9Z3) [dump](https://solscan.io/tx/vtdpzvDJqMLUpsMs3brvK2DUTpFRSohgMpNcg4npv2FRWX28mAMxRKqqWNCgyMvEGE2RSD9dNNGg1TqicB5Zjdr) |
| 8 | 77 | +1 | 2 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4TqRwjjPiGg6ZLMYo8ZuAEDfGZdkotRvLFYCwNuVokxQXpnFVrtmXLaTfviqrZm7jnxCgEAooRuw4zn9PkCasdVW) [dump](https://solscan.io/tx/28Exb1sc7Yh5ukg8XTnWfe6fHHcPrAvcVZX3MyzSaTid8S7fZvt94pLnrRDq3ZxgsjAgbXf5qH8dGNVDrV4moBFk) |
| 9 | 101 | +1 | 5 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/2eTCqjzXiDHGqy2EgeUJxMqLGwH5Mqyxkyray4ELLnsJxMgWJUXyAUkGY7DuxFruGnvRkditqG2DBjB3jd48F3Yx) [sell](https://solscan.io/tx/3LJJ3eoYYw7AXxDqRCCYn8Hgna8yEsPMKYZvK2NFznpyrPi22ENhU95bVHNrjAWt7efRjUMvrPvgJD3ARrYdGpdD) [dump](https://solscan.io/tx/63ZMaqiyuTewapCuSA1TuYzYWtzv3RLdrrgksn1fxdcVMv4FvvaWwpkJKRkA2a1Thjhbmiah3Jws3ui6HwCvEthQ) |
| 10 | 73 | same | 5 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/5JwA5nCHY6YWPRkknG6UHaFD8DZVXwhG7HkBA7bq4bQwGh3BXDyB1D4P1kijwT1pPyzH1sTkZJzsMQgv1qyA9vN9) [dump](https://solscan.io/tx/5pvi7TiqH11BXuTR1GJeWrRC9ynbx8KTH9KzGSmzP5WE3FuQsTFZgKKos4oUYVVyeHZj1Pnr5mZ3Z3FeFyrqT6Rt) |
| 11 | 53 | same | 3 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/nAL9WficZrPvQitZcuVncgaDpsxpYoXdV13DyVBxqhrNMr1wmvM8GHoES7yoPWyx4t6NK72uA31qks3CyVG5hHq) [sell](https://solscan.io/tx/4saVmRdspc4wqEzVtmRc4SfP8WiPf7N4CyonFWjDKNyoLEmqtDNCtUYm94SkRdPoC18HefA73aHCUCeLDUTX9s4z) [dump](https://solscan.io/tx/2MoUEQkE1Rboio9kKqSHnT98ULxK3dTarhLwfbijedkok46q7rnbH4eAEs1RqqT81uYVwYrKRiwatEFB9SFKg8Sd) |
| 12 | 85 | same | 3 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/28yBmCWinNBjkAspQugdwu3QpoLJjDmdiWw4JQGaSEP8hRjW5Evm5GSNoSwTHF3fWFpda1q8P9fdYUXf366SxU8c) [dump](https://solscan.io/tx/3ZosEJsCJC973Srik62i7YSeX7NaTxoeYkPziH8UY686ufmCYEheASeG84Efr5p7MZxnE3QkkDRNRSNBUvL4evNu) |
| 13 | 128 | +1 | 1 | **soyas** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/oyVvFVAkwEobmd9ewN3r3jqG7T7J7h6dqsBmF2K2SV1bn1JGwaLSvcE8ntyLbquBK9EimVGESLzgBSZ13jY96VF) [dump](https://solscan.io/tx/39FXQvjLFGRLpPS9UAusSbcoCpwGANbQe3HmHPptDurnLdAXZcC6q11VxfT26SZHs7T5FVXDQe38jp98tPRyG6Bs) |
| 14 | 84 | same | 13 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/4GNsTrQuF8NYciYJSPZ6LVMXpHvD8XmAut8AN39xABiS4svjyzR9GfAPvXtf5dZs5hKUAMRDB9S2yUxUXM5L6vzt) [dump](https://solscan.io/tx/1FuhcSJ6CAzt8dB8NDjfofqJW22J63WJNfpXdNj1CLjEghnEa6wE7tH4rhcD9dzEwfSV7u8ixx9KsVG8MNCVf12) |
| 15 | 53 | +1 | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/BULXMzmfqrNXf1qT6a74XyeBRdrd5kRVt8v1DywLmVXhwU4C5DTiQzoTFT3RRExJwVmGCTzgawALYsDEFBWoaAN) [sell](https://solscan.io/tx/HKWRrEP4qZmb1xrJWoW81dDfJBLUFoEUbVpfxid39R8G44ZwWncfRYeGyFP4rR7WRVowJ1G6BVzpzZJN931pdNQ) [dump](https://solscan.io/tx/3nLm4o2WeAQ47TpztzkfED4aU98raLGATnenTAyNuBAGXCR5Ktodn72fdiqns5fPFL6RWjQdsqunhHaHqvKxbzN7) |
| 16 | 168 | +1 | 3 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/53nxQ61C3jbd1QAMQhwu3AKwpy85tWNnvBC5bYVHLVm27WXZfqez2iu2UCaNeLKeW8MLSJgR2xdRputciABh1z3Q) [sell](https://solscan.io/tx/2xJbEWoregdt8a7JpnpiJxCeCetCt8fPPkAaFRowjawnwkSg76txchQGY7nDGYE6D7my5Fj28LmgBwr94s3po5zp) [dump](https://solscan.io/tx/2DD2grBaFvaXtqJQVZnSEzvxwWTEMgyCMhn8qf4SqrG3MKKwFNXbwc9LuR6R1ZDRmTauyekx4qNVnDQboow3MfPv) |
| 17 | 11 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.2 s | 1 | [buy](https://solscan.io/tx/2YARhPRQDnvJsAPhmUMBq6f2yy8nRSjJuRYaDGmRzFjrWGW2DYVKmWA2TyzBYSk7sqKeqTivvddaQtK1jZ8M4e4J) [sell](https://solscan.io/tx/HjgYsLYkan7bgLj6uwDTgn7XMoFn6YEzWNSovJyobptxoAqfYsB4snt6EoxSZmAXrdxo81eXMGhL9Jj83PFtSJC) [dump](https://solscan.io/tx/55mtRYBRbFYYKDmZYGyu79t2jcKd2HRbNfZAmZjsiHqekK5DKXLaA65crSHfWCfegCtW1M8BiH8oBVFZbmf3vqvR) |
| 18 | 27 | same | 4 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/o36EKmeaZT9rprSbz1m6esKPh8dPL61suFSbw1Yemk2QFyzw9tqcQs1Pz45Lz4SLuZF1qCz5Tit7i5HUHQB4nyF) [dump](https://solscan.io/tx/3yx2ohY83hjet7912oafnBW8DpLkiC9V2ghWi5WuYp89aWrZWnr5hByJDiFLrE47WWoRQKgsB24B6PDLiMFoPabf) |
| 19 | 48 | same | 1 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/42Mq4zXiCTgkb64SX2cdC8U4VcLxzfcfa5DRy8F9XnaUkH7DxQKxeqgtuY9GiBa1uQwDaShPmBu2Pruzd4YPVNvk) [dump](https://solscan.io/tx/2sLUMDm3q2WqHX2rAkiQdHWzyMGeow56eHBgwsMzYfwxUhZ5BQAxUQwixc1VcfGiqnBG14wG4fBUuqor3xLv2a2C) |
| 20 | 37 | same | 3 | **soyas** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/eRk8zTZTEbQphDLxco5jT3kzwgf4mVQy1tSQy51SwYC19n7aDeikvAsL3T3sbrjwpuyF8tNAbyhKYKy89j6CjQh) [dump](https://solscan.io/tx/61SGbbQvLuWK4bryUmE4LXdX9Kj98Px8poHw2MuuwMYSj44srFQuR9P5YSdkPqB2nieTyvUwbzCtRgUXP3EhLSny) |
| 21 | 175 | +1 | 4 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/4uEvC7c1WGyjusj71gFiM1hT564crWBa4aSRW6RK2tQTTWDch2EieVAHfx98FGSeYm87oTuiYnjB9qVdZKraE7zD) [dump](https://solscan.io/tx/4dESBAYGexQ2Fo6noq4W3xe5PTug7wyAq9EYMEdPY7U6Boe61GBAW473MttQR8mdD6WJkazjuQ93d28861ZLNrPj) |
| 22 | 34 | same | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/W7Epy8PT11juJCQdmeHRPrejVXZcE2TM2ysQXp85YLeWXehJBauiieKrsEdZsFp4CBpwWVS1npaNX5f3SCYQnTZ) [sell](https://solscan.io/tx/4RifCZfXvoMH3XUcuxrv23Tud93jMR16CSQq6DTHmVqQswY63u3j2XtE7z8X7CPdP1Zf9rnJRBuA372P7igQNAiY) [dump](https://solscan.io/tx/fGG3WH2zfps7JAvXFTBhMvhQa8DN7RC5U9dRwQzWiWtU1QmgR9YqYCjgLsfoqptmJfq5ZFBKUx11saowT9S3QsK) |
| 23 | 45 | same | 4 | **bolt** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/CkK1z4Mbw11X57GPNpBqxDDNEvKraEbEWfok4aAQHEYLVegrYneGLX14rogvvZJkde2EjnuW1H5tLPov5XASnzS) [dump](https://solscan.io/tx/5QKoSe2XckWL6mJDWahJ4UPvXRia5zB57vZXQv26egaExC2xf7DugTT13T7Sz4BANYeFkKvQ3EiVgbSfSsuhwiyV) |
| 24 | 41 | same | 2 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/jwogWtQjirRN9DJ53srHS4bTuUrde9AEsfVRdFmbVyfCk4fQagTtzckWRyB6em1fwH2pnf9j6HvBiRDABnPpzPk) [dump](https://solscan.io/tx/4M7UGxbirzAY2DwYF7fejdTHoshFSHve9WwbSNs9EEV86FziExb4wZXpcMkNsAeWK636Keh56CCFjrtiLZJo7Vd5) |
| 25 | 54 | same | 4 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/4xZtUWBHQHES5p9ayhavNJ73UD3a85qoCiEQAM2HULaEeaxFfsTdgYLvobreWq32BaF9Qp1t5yV1Tp9xvMBhaKYN) [dump](https://solscan.io/tx/1Dwhc5WaCLFNB8JYwBTLdagsYQtdwRamfmVuTmmCbrAeJCekdEtgsseQ4ogAmrfMxLzKNyCC2smvTdSkMcehinV) |
| 26 | 136 | +1 | 2 | **glaive** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/2TEDRx6EhtNKtApJwygGxehVs57cNy844NFbSxpBRjLpTsH8L813bZA2A8ZKzJaAJfwPcSje6DER38qJ5oQ95nHN) [sell](https://solscan.io/tx/2LvhFqHWacepce6BmzdMJ2jQVZNzBbnMiKMHmdQ6sxWzxiUKug3oeojdsuvzSq8VU8Z6ikQRTS3vdwVMVy2cDpMv) [dump](https://solscan.io/tx/5jRDzEEEFHFM44tYoGV1mWxM3cpHHnW6dGFPa45Mi7tWremJVgMaNbEAQ9kGWUdZDKgzKFZ5TX7yot4HfGYhtPBN) |
| 27 | 71 | same | 2 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/4irhUUTyESyfdoK36fJ6UKtXNXaajFhnqgGyQsSxk1Z2oCEtUXouq2Xfwa7FQyPsFK5nCw1WcdBDhav3VmPZN9yu) [dump](https://solscan.io/tx/1Hx9UqNsisWJrkUkNjBVkYCQDiitvhNPLn4eR7UMRNicXKEToW1Cq11dkwQZtKcv4hncSMJB1dYk3SejyBCjHZE) |
| 28 | 67 | same | 2 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/4rZsrMLSj9xGfrn3oCuBEJq8ZWv7Gm5arkBeCKodGo1jgsA5pyqxZbi1idNDZ6jPnvfLFsbF3ui7km7qy3Nrq1Hs) [dump](https://solscan.io/tx/443sfQVdtEUHkXUXFZdFKmhQXA52WgHFUKtjTWuRwdchqWP22MHgKqV5P4L8tY4AokCmpe6bFtJrMFnyhr7p6pfM) |
| 29 | 133 | +1 | 5 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2cRK9N58NCdgPUVcK6iAwjNXoqnTSqHN3pwEMzm5eboEagKTkRcrGAQUvmPeLgfEhCkza7zEEZK39biG9ZHVEDxZ) [dump](https://solscan.io/tx/2ncXyiwrgHJJPqnMGDzFRntkYqcSgbbwq797292z9XgxMGp4d58gHxJ1iQ5sMa26TKCL5jFe7GU5umTVkCMuNw1Z) |
| 30 | 155 | +1 | 4 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/57mhvCXyuQuAmmD7chrJsKm6VTghwjJtspu1iT9Rf6VdAr29PqqdLTnPB79ke461ftDgb1fn2zd6xDRNn5oFmTFm) [dump](https://solscan.io/tx/3b4Xo7TPJPahDnAueDMAWEEYByo1kLmtMsYztw5w9puuGuxAtUAmFExdHWtidwj5vpx7J82BNK8dbk1eK4mxtG6f) |
| 31 | 142 | +1 | 6 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4SZhRG1qgKeu4rWfkPxbwNAGH6BtxBkc4FRSKPWim4D21AUee1wnMagtY9LqkvptL7YckMf1vJ54zkbnmAc9PFP4) [dump](https://solscan.io/tx/2GnrqUAESwgCbfSKeQrv99fKHnSatZP2mFfwTvT1DMFUVxXXyqtRtYaDNQcDbyfmbdKGWye4YEZjNzJnqpKYm1US) |
| 32 | 31 | same | 5 | **soyas** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/r6js7P1wdrcomyhufLJJvV9fWfZnctiSrFhAkHsf6Kq2EeVbA1DUWBtKQpXVsDNBfHtbnNDF7brRZx1sdAcWnnm) [dump](https://solscan.io/tx/3qtrz4fB4B5YJFoXkJjvs63hez9M5zWopDVicaVFMdZRZCQowWRqHar8rrXGJdDe9eEdcS5jdsgrpeyeynHv3gfN) |
| 33 | 172 | +1 | 5 | **helius-swqos** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/6W5naXgwHkJietiQS8RA6DKv1pFABqyVMmDujJcwdS7oQTbhBrZs6WCbbvktZYrq7NdeyFYVoi9EE6VbE8GqnMU) [sell](https://solscan.io/tx/5dEfmAtvjLHgbBTiekQf2Knfii1pA1ynJczQwLCjTenBjk7norKLkmtmAZS4XYHnF9kjLJd3a42BoNmFJ1dQ8KNv) [dump](https://solscan.io/tx/5xRLZqQBft2JpZLzj6nr1eajpTgNeeVJxCpGAi8VeHuso8us575nKJfR9mqcB4K5WgfTQVd4DqiP8HTUexJ8uy8i) |
| 34 | 83 | same | 4 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/34w5VySeu3F5wKSjFJPmcSRvwGguhkrZxbz9qQGWJmkkG2pnrL1uSsTcZyFVYnPovNefUBvVoAPy62z5tC47gvTX) [dump](https://solscan.io/tx/5wEte5dJoNENGDEuJXaVRJgqzfBFw28z6FBy4K66s1kmMvQhgsTEQRZ3qcqdz8zfuybkYLsj1W3tsdrS1bSUhQjr) |
| 35 | 43 | same | 3 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/5DWKBQz42sP2QZ6xrFn7kixKRTsb5ACuBRbeEMwcrajaXm9LmJMi2d5pXasCQqAe9SdWcPDdePLwpcBn2CBVkBWU) [dump](https://solscan.io/tx/4wvCffUM7odyxNEHVQpRvV3oT8aoipy8Xxk57m6d6CwDoUbMzmVfeT59Vf9bmmgPt1LpgmZj2pv5Vxv1rCyySG2G) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Jito | 17 | 5 | 29% | -0.1049 | -0.0198 | 1/5 |
| Harmonic | 14 | 6 | 43% | -0.2956 | -0.0486 | 0/6 |
| BAM | 4 | 0 | 0% | -0.0020 | – | 0/0 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 28 | 11 | 39% | -0.3989 | -0.0355 | 1/11 |
| dev list | 7 | 0 | 0% | -0.0035 | – | 0/0 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 22 | 5 | 23% | -0.1196 | -0.0222 | 1/5 |
| next block | 13 | 6 | 46% | -0.2829 | -0.0466 | 0/6 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 00:00 | 5 | 2 | 40% | -0.0596 | -0.0291 | 0/2 |
| 01:00 | 23 | 8 | 35% | -0.3122 | -0.0381 | 1/8 |
| 02:00 | 7 | 1 | 14% | -0.0306 | -0.0276 | 0/1 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 11 | -0.3904 | -0.0355 | 1.4 s |

## 8. P&L leaders
**Best trades:** 27FhVP +0.0479 (Jito, time-limit, score -0.50); HWsZzx -0.0154 (Harmonic, time-limit, score -0.72); G5MviP -0.0191 (Jito, time-limit, score -0.94)

**Worst trades:** 2ePe73 -0.0772 (Harmonic, time-limit, score -1.80); 96wVc2 -0.0728 (Jito, time-limit, score -0.65); 4RuRS5 -0.0647 (Harmonic, time-limit, score -0.54)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `8gDfqHXZ` | JitoLabs | 1 | 1 | +0.0479 |
| `siidBVew` | JitoLabs | 1 | 0 | -0.0005 |
| `pSo1KZXg` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `G2TBEh2a` | AgaveBam | 1 | 0 | -0.0005 |
| `3JotfSFP` | AgaveBam | 1 | 0 | -0.0005 |
| `9jxgosAf` | FireBAM | 1 | 0 | -0.0005 |
| `FNKgX9dY` | HarmonicAgave | 1 | 0 | -0.0005 |
| `TopjgY7N` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `SWiz7Qwn` | AgaveBam | 1 | 0 | -0.0005 |
| `Fd7btgyS` | HarmonicAgave | 2 | 0 | -0.0010 |
| `HEL1USMZ` | JitoLabs | 3 | 0 | -0.0015 |
| `5ZqveVff` | HarmonicAgave | 1 | 1 | -0.0154 |
| `E1r4Psq8` | JitoLabs | 6 | 1 | -0.0298 |
| `Awes4Tr6` | HarmonicFiredancer | 1 | 1 | -0.0391 |
| `EvnRmnMr` | JitoLabs | 2 | 2 | -0.0466 |
| `G3a3iYZK` | HarmonicAgave | 2 | 1 | -0.0588 |
| `JUPiTERr` | HarmonicFiredancer | 3 | 1 | -0.0657 |
| `C8Bey3LK` | JitoLabs | 4 | 1 | -0.0743 |
| `shftkxns` | HarmonicAgave | 2 | 2 | -0.1141 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1895 (p25 1379, p75 3379, n 35) |
| Executed-feed lag behind first sighting, ms | 4.1 (p25 1.2, p75 11.8, n 35) |
| Buy sent → our tx seen on the feed, ms | 52.5 (p25 34.2, p75 122.6, n 35) |
| Fills: our buy seen on the feed after the dump, ms | 53 (p25 34, p75 168, n 11) |
| Guard fails: our failed buy seen after the dump, ms | 72 (p25 45, p75 98, n 24) |
| Fills in the dump's own block | 5 of 11 |
| Guard fails in the dump's own block | 17 of 24 |

**Which copy landed (nonce fan-out):** glaive 8, nozomi 7, falcon+falcon-udp 7, landx-fra3 3, soyas 3, 0slot 2, helius-swqos 2, solami 2, bolt 1

**Send-path answers (FAST-ACK lines):** 0slot 35 (median ack 0.7 ms), falcon 35 (median ack 0.4 ms), glaive 31 (median ack 0.4 ms), helius-swqos 21 (median ack 0.8 ms), nozomi 20 (median ack 0.4 ms), bolt 6 (median ack 0.8 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 2 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 3.07 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 8yYMhuYo | 10 | 7 |
| haqq (dip bot) | 5 | 4 |
| HJojpSUQ | 5 | 4 |
| 7eYVJnGA | 5 | 5 |
| 74NEdBFk | 4 | 4 |
| 5GpzkbJ1 | 4 | 4 |
| cwEzcAEt | 4 | 4 |
| DibyFyf9 | 4 | 4 |
| 8PgC4ngp | 4 | 1 |
| 6eVWZbj5 | 4 | 4 |
| CvHEVC7S | 3 | 1 |
| 9pQQc1xy (bait follower) | 3 | 3 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | -0.2373 |
| Pump fee on buys | 0.0611 (0.0056 per fill) |
| Pump fee on sells (residual) | 0.0581 (0.0053 per fill) |
| Buy tx fees (base + priority) | 0.0056 (0.00051 per fill) |
| Buy tips | 0.0084 (0.0008 per fill) |
| Sell tx fees | 0.0067 (0.00061 per fill) |
| Sell tips | 0.0132 (0.0012 per fill) |
| Failed buys (tx fees) | 0.0121 (24 buys) |
| **Result** | **+0.2662** |

Buy compute used (fills): median 78,404 CU, max 82,904 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 49 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getLatestBlockhash: 1 timeouts/transport errors (worst p99 251 ms)
- ⚠️ RPC bh-fallback getSlot: 1 timeouts/transport errors (worst p99 321 ms)
- ⚠️ RPC bh-primary getLatestBlockhash: 7 timeouts/transport errors (worst p99 724 ms)
- ⚠️ big loss FrL1NP -0.0583 (time-limit, Harmonic)
- ⚠️ big loss 96wVc2 -0.0728 (time-limit, Jito)
- ⚠️ big loss 2ePe73 -0.0772 (time-limit, Harmonic)
- ⚠️ big loss 4RuRS5 -0.0647 (time-limit, Harmonic)
- ℹ️ wallet change +0.2657 vs trades +0.2662: gap -0.0005 SOL — about the fees of the 225 pre-send tries never seen on our feed (up to 0.0012 SOL if they all landed and failed; inferred)
- 🔴 Regular buys: 10 of 11 fills lost (−0.39), the same pattern as AMS r29–r32. While a regular position is open, pre-send pauses, so regular also cost pre-send chances (5 'reactive_position' skips).

Checks passed: every reactive fill was sold; every pre-send fill was closed by a sell; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Done after this run:**

- Run 27: regular switched off (--m2-min 999, no dev list); regular is measured in shadow from the engine's M2 scores and replayed afterwards.

**Recommended / open:**

- FRA run 27: pre-send only, 12 h, same pre-send config.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r26.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r26.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Pre-send (section 4b): the jsonl presend_live_* records (fills, closes, REALIZED, account closes, stops, end checks) and presend_attempt_land (try results, failed-try fees); the log's PRESEND LIVE lines when a run has no such records.
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-28 02:26 PKT.

# Frankfurt run 4 — dip bot run report

*0.35 SOL, routes v5 (nozomi + helius-swqos + tipless staked-rpc)*

> **Verdict:** Good (+0.1198 SOL by the wallet). Misses now landed 17–48 ms after the dump on nearby leaders (runs 1–3: ~80–95 ms).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.1198 SOL** (wallet 4.0760 → 4.1958, Δ +0.1198) |
| Started (PKT) | 2026-10-24 05:09:59 |
| Ended (PKT) | 2026-10-24 06:38:30 — time limit / max trades |
| Ran for | 1 h 28 min of 180 min planned |
| First / last buy (PKT) | 05:13:00 / 06:38:28 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 24 → **7 filled**, 17 failed on the +5% guard |
| Fill rate | 29% |
| Wins / losses (fills) | 5 / 2 (win rate 71%) |
| Per filled buy | avg +0.0183, median +0.0012 SOL |
| Fills only / failed buys only | +0.1284 / -0.0086 SOL |
| Best / worst trade | FGWAR5 +0.0659 / 3PsjL5 -0.0007 |
| Fill landing | median 45 ms after the dump (seen on our feed); 6 of 7 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip8 |
| model / tier | IMIT1 strict (score >= 0.5419) |
| size (normal) | 0.35 SOL |
| dev list | off |
| exit | take-profit +5% / stop-loss −10% / time limit 6 slots (~1.3 s) |
| price guard | +5% over the post-dump price (pump error 6042 if exceeded); slot deadline = dump slot + 1 |
| buy fee (priority) | 5M µL/CU × 100k CU limit = 0.0005 SOL per landed buy tx |
| sell fee | 5M µL/CU × 120k CU limit (0.0006 SOL per landed sell tx) |
| route: agave leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: bam leaders | nozomi + bolt + landx-fra3 + staked-rpc |
| route: default leaders | nozomi + bolt + helius-swqos + staked-rpc |
| route: fd leaders | nozomi + landx-fra3 + bolt + staked-rpc |
| route: harmonic leaders | nozomi + helius-swqos + landx-fra3 + staked-rpc |
| route: jito leaders | nozomi + bolt + astralane + staked-rpc |
| route: other leaders | nozomi + bolt + helius-swqos + staked-rpc |
| sell path | staked-rpc (retry also via nozomi) |
| near-leader gate | off (every leader) |
| pre-send | off |
| durable-nonce fan-out | off (one tx to every path, every path's tip in it) |
| backup RPC | RMR_RPC_URL |
| holder-reward tokens | allowed |
| limits | max 7 fills, 1 open at a time, 180 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 3**:

| Setting | FRA run 3 | FRA run 4 |
|---|---|---|
| route: agave leaders | nozomi + helius + bolt | nozomi + helius-swqos + bolt + staked-rpc |
| route: bam leaders | nozomi + bolt + landx-fra3 | nozomi + bolt + landx-fra3 + staked-rpc |
| route: default leaders | nozomi + bolt + helius | nozomi + bolt + helius-swqos + staked-rpc |
| route: fd leaders | nozomi + landx-fra3 + bolt | nozomi + landx-fra3 + bolt + staked-rpc |
| route: harmonic leaders | nozomi + helius + landx-fra3 | nozomi + helius-swqos + landx-fra3 + staked-rpc |
| route: jito leaders | bolt + astralane + nozomi | nozomi + bolt + astralane + staked-rpc |
| route: other leaders | nozomi + bolt + helius | nozomi + bolt + helius-swqos + staked-rpc |

- Routes v5: nozomi as the core path, helius-swqos (0.0002 tip) instead of helius, and a tipless staked-rpc copy on every leader type.

## 4. Timeline (PKT)
- **05:09:59** engine start #1 (session with 24 buys)
- **05:57:06** big win: FGWAR5 +0.0659 SOL (take-profit)
- **06:38:30** engine end #1: run end

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 5578 |
| Inside the envelope (age / drop / since-buy / size) | 2657 |
| Picks (score above the threshold) | 26 |
| Skipped | spacing 2 |
| Buys sent | 24 |
| Filled | 7 |
| Failed on the +5% guard | 17 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 7 of 7 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 05:13:00 | [FLaZxi](https://gmgn.ai/sol/token/FLaZxiPvnxNuEdwQ9DwhwRdYD18HFd5wUeXvDo4Jpump) | 0.35 | 0.72 | 3.34 / −17% | 25.0 s | BAM `2Wf9V9` | guard fail | -0.0005 |
| 2 | 05:19:05 | [7KLDo7](https://gmgn.ai/sol/token/7KLDo7PBKBwxqDznD54FYnbgpcJxFCkzJEa4SCqEKS47) | 0.35 | 0.97 | 12.65 / −50% | 1.5 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 3 | 05:19:49 | [CDpBtX](https://gmgn.ai/sol/token/CDpBtXULKLyrGwDtHgqCLYLGzbCneunmtPrt3jBmpump) | 0.35 | 0.84 | 3.50 / −14% | 3.8 s | Jito `8gDfqH` | guard fail | -0.0005 |
| 4 | 05:23:02 | [FUMMyp](https://gmgn.ai/sol/token/FUMMypMwEQqvx2zNXBA5gororx5nEjPtV9WUPxN8kRuu) | 0.35 | 0.67 | 4.33 / −14% | 2.3 s | BAM `76rcGH` | guard fail | -0.0005 |
| 5 | 05:24:54 | [Gdp7xe](https://gmgn.ai/sol/token/Gdp7xeZqKkC9eLatJHJjiuGRfrx2ARMnuM3d2jfrpump) | 0.35 | 0.60 | 4.54 / −20% | 30.1 s | BAM `2GUnfx` | guard fail | -0.0005 |
| 6 | 05:33:38 | [3PsjL5](https://gmgn.ai/sol/token/3PsjL5XevDMroCMdKWAQMtSSpnr2usUkhfKFfomKhhro) | 0.35 | 0.76 | 3.72 / −19% | 4.9 s | BAM `5zuNci` | guard fail | -0.0005 |
| 7 | 05:34:14 | [Biiv46](https://gmgn.ai/sol/token/Biiv46yBzZwwdg3HvYQ52yPXmnMb5EnF8dboTx2qpump) | 0.35 | 0.68 | 5.54 / −14% | 109.4 s | Firedancer `HW4zor` | filled | **+0.0282** |
| 8 | 05:34:45 | [G7rUZb](https://gmgn.ai/sol/token/G7rUZbtFf6nDQ1MXiC7zS6J3dyokFgxGHt6PABd1pump) | 0.35 | 0.57 | 4.29 / −18% | 2.1 s | BAM `DRpbCB` | guard fail | -0.0005 |
| 9 | 05:35:19 | [3kFzLs](https://gmgn.ai/sol/token/3kFzLscbYHRyvkxxxfB5g7E9gY5ThtwytpaFtErqpump) | 0.35 | 0.64 | 4.32 / −17% | 7.8 s | Harmonic `mint13` | guard fail | -0.0005 |
| 10 | 05:36:35 | [3PsjL5](https://gmgn.ai/sol/token/3PsjL5XevDMroCMdKWAQMtSSpnr2usUkhfKFfomKhhro) | 0.35 | 0.80 | 4.71 / −15% | 180.8 s | Rakurai `ana2y2` | guard fail | -0.0005 |
| 11 | 05:36:38 | [3PsjL5](https://gmgn.ai/sol/token/3PsjL5XevDMroCMdKWAQMtSSpnr2usUkhfKFfomKhhro) | 0.35 | 0.55 | 2.44 / −8% | 184.0 s | BAM `4VrjyX` | filled | **-0.0007** |
| 12 | 05:39:11 | [7UhhrF](https://gmgn.ai/sol/token/7UhhrFyYKb6BeZnbD6rB8N63hpBrPn4jGNqAzj3k335g) | 0.35 | 0.99 | 4.53 / −24% | 1.3 s | Firedancer `9eGrDo` | guard fail | -0.0005 |
| 13 | 05:42:23 | [4F4qGZ](https://gmgn.ai/sol/token/4F4qGZC37ABtTCvNz18MZ8BsYMfNa3ozVtUhdb64pump) | 0.35 | 0.88 | 3.51 / −17% | 3.4 s | BAM `5EhGYU` | guard fail | -0.0005 |
| 14 | 05:47:58 | [BpX1Xb](https://gmgn.ai/sol/token/BpX1Xb5GH19s8mZPh6pyi3qdvZ5baSwfAiEvgzuZpump) | 0.35 | 0.56 | 4.30 / −17% | 18.9 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 15 | 05:57:06 | [FGWAR5](https://gmgn.ai/sol/token/FGWAR5z9EuoMMrcAoqivV8P9crn9GtfrBEmeuTEspump) | 0.35 | 0.68 | 1.40 / −8% | 4.5 s | Jito `3YVoK8` | filled | **+0.0659** |
| 16 | 06:01:29 | [2kBfCT](https://gmgn.ai/sol/token/2kBfCTgZ4J27F98J63Vn4ZxfnwxeFE4s7CGdDGU41NXQ) | 0.35 | 0.96 | 3.39 / −19% | 4.5 s | BAM `5ejbTA` | guard fail | -0.0005 |
| 17 | 06:02:45 | [ANj3nf](https://gmgn.ai/sol/token/ANj3nfzoghhewXdQQ9wgk23aSkwa9Zk54TS9BF8KVnQv) | 0.35 | 1.03 | 2.45 / −14% | 3.6 s | BAM `DRpbCB` | guard fail | -0.0005 |
| 18 | 06:05:05 | [DUKTmB](https://gmgn.ai/sol/token/DUKTmB79rB9EwMC8N4d6ZLPLHNS3uv3aru3BBxJrpump) | 0.35 | 1.29 | 3.75 / −18% | 21.0 s | BAM `HpcB5Q` | guard fail | -0.0005 |
| 19 | 06:21:34 | [649rrz](https://gmgn.ai/sol/token/649rrzxeaTt1KvhLqcBidKAAHHjxV88unPT1mCpXpump) | 0.35 | 1.20 | 3.22 / −16% | 48.3 s | Harmonic `2m1A2W` | filled | **-0.0004** |
| 20 | 06:26:09 | [AE3WB7](https://gmgn.ai/sol/token/AE3WB7F6gQsEp9T6PAZqFw6JoVvU9tgJuBhyUbNHpump) | 0.35 | 0.62 | 3.50 / −14% | 104.3 s | BAM `DRpbCB` | filled | **+0.0001** |
| 21 | 06:26:12 | [GDPqT9](https://gmgn.ai/sol/token/GDPqT9eh3oMojE18TmTERCrG5WKaPK7j3Fvz33PrBwek) | 0.35 | 0.79 | 7.10 / −23% | 1.9 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 22 | 06:27:27 | [AE3WB7](https://gmgn.ai/sol/token/AE3WB7F6gQsEp9T6PAZqFw6JoVvU9tgJuBhyUbNHpump) | 0.35 | 0.62 | 3.41 / −14% | 182.3 s | Jito `UPSCQN` | filled | **+0.0341** |
| 23 | 06:30:18 | [ABkaAK](https://gmgn.ai/sol/token/ABkaAK7iXQrrNt9yRLZ5eBcKmtydfYo1Hkeo4Gs1tCpQ) | 0.35 | 0.94 | 6.14 / −31% | 1.3 s | Jito `HEL1US` | guard fail | -0.0005 |
| 24 | 06:38:28 | [CLjwTQ](https://gmgn.ai/sol/token/CLjwTQCxmQriJqoT5rHU4VqixWgxagS5cCexRAL6pump) | 0.35 | 0.83 | 2.20 / −11% | 2.1 s | Jito `GnC339` | filled | **+0.0012** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 35 | same | 5 | landx-fra3+nozomi+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/37mUFvQdjGQwWYVMohHsaABEfgJgBRUtsQJL9jdn3S2NmyspaesozyTtmsZKnPocpmuaWY6sHvTr55TUdBcTKTCG) [dump](https://solscan.io/tx/278upSsYLL5iUN68quBxNbPgVpn9cSbyuKbyN54H5RDKhLYS8zh8SwMQxdQL2vwHQv1zJpooYqJ6CPAQVtYzwSLH) |
| 2 | 48 | same | 4 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5bW4MSGYCNSuLyq1ZgWq7rRfckG17a4tdUfXaYrrsBAYCbrh6EnCd4sgnJXmeZfFrSi5YJ2tqB5GwEnakYWQ569Q) [dump](https://solscan.io/tx/3NCAsrkit4z2vbVf86CPE6WnqbfuzrwuV3ZRzoUgYBd3AXNSLC3AaBUu94CmTtVgpqmkLXt5a2sxAbFwFwxeEQxc) |
| 3 | 17 | same | 5 | landx-fra3+nozomi+bolt+astralane+staked-rpc | – | – | [buy](https://solscan.io/tx/63n7JtwGWbNGUvXVDgE88go5AmTEDUjHUAyNqGnbdNU7of1gtQVAqFm3nzUGrptLaUzxzxdbSR6AVUFQtc2rSj2A) [dump](https://solscan.io/tx/4HJbRRhXXA9BDoFBbksYutRUHS22yXWbNU4zzLqfJbaYJbKiXhXBoeBriDFJKERojVaV8yjjzuqJAyvxxnBVpF59) |
| 4 | 38 | same | 4 | landx-fra3+nozomi+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/zLsxsTuEyCkWk4o77tiq4m6G459e5UqksHFSY9Sahfra8HveuxuzZmNYGvNH26A8Ya27ySZ5hmvB6zMstqovMwU) [dump](https://solscan.io/tx/2RfBFCXqx8YAU2Wn1pLhGfGxsnP9J6zXDq6ExV3c13RFHRinWxjGDH4A3CkA5GRaSgzwbY4fokBrnYUfGznsqTXD) |
| 5 | 159 | same | 2 | landx-fra3+nozomi+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/48HRMeYrk5R32Yd3CubujCeSeVU6sR1gNkVfuSuTLF4WfeEW7sk3wfbk8AHUkAuVNbXqwFUwnEoMwKXEpVNghXC5) [dump](https://solscan.io/tx/3YJdV7GUVPVYHhPjJNsRy4qsgteWinT6s9cxd7cQGzj6dH59UcTKPEDPwwmWsLDhEVNv1i89Ro2SGtVTWqy8X8Zp) |
| 6 | 166 | +1 | 1 | landx-fra3+nozomi+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/n4zuLA73RwtG5njoThpV3sKDxteXbGFtFWMj7w4S18VoSJiZ6F5VYhuxAekTRC3HxJg18PKRL6Vii9oBynM197k) [dump](https://solscan.io/tx/5Uj66KPrCe7A3xm9M5FxGFNM3e8xJhnBuEftzU6gE3GWzBdg9AG9tcc9YkknQsYwAuCgsKbUutC2gcnVp8hCcFxw) |
| 7 | 45 | same | 4 | landx-fra3+nozomi+bolt+staked-rpc+astralane | take-profit 1.4 s | 2 | [buy](https://solscan.io/tx/ABMUrdMNyhDDmyADPqQbSV2YBwWAMbfxrMi7nzD2aymrpwpDqvistBHhFaTbou5TFC99QcZH1kp6LruCc1Mk9y1) [sell1](https://solscan.io/tx/4Yt8WPp56MBertJUXwtMaeKrR4BKDzP6YyvSk2KRvAsKdaxHHMGnEkFhZTi3RHAkBrnZr7pB8qHwEzdZyo3xtSFx) [sell2](https://solscan.io/tx/2bK9DjGRMg9FgymSTbbvt4bf5c3XS4aVqMVizvzRS6SW4EYTWAmA7K3ik4qfx2zpn97hJ29615VoVAcHbZVSm6sM) [dump](https://solscan.io/tx/5aHacMFrSaLT7hjBvWhDPVoT3WxxgP8W26DFKBbFMJ2jjUs47Q21S2CSxyEGLsbaJvizdYHx2bc4cNQsqXymud7u) |
| 8 | 115 | same | 9 | landx-fra3+nozomi+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4gLCr84yRryP9bhtV7nDoiiuWqaXBWudQi25Je6vUQE699qJ6zPk1ygQmfS4z1aRgboEXHVtL84dwuQzwGcyzUFB) [dump](https://solscan.io/tx/44trCGK8drTjpPF9z9PWXNeDQv7feoWePNcbEeAZHHyiCGxzWvFRMsGPhAiU2uZREpCKbS2DTQuzhY3E9Trijxcc) |
| 9 | 159 | +1 | 6 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/2zBV2x9jcXLSEx2M7xC54M1RdtfGnGFx26E4nxnFoTQNtzC7J21Bpfv758QcUXTMBstENaQi2Xp6jpHnRkZyJ1Pa) [dump](https://solscan.io/tx/62UcYWzpdLGbA1FVQws1oY1Cr7AxPTvegH961Cg4CmmhQR7cR2FbPSAKu3hP9LtiVYFHkuuTHfr8LWE1cDcHMRd4) |
| 10 | 217 | +1 | 9 | nozomi+bolt+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5tKk3PYswt4mJDcREMFJyuu77mqe3CbhbzWYcJkqzXbd8LoFJMhjLHTptMbQVfbpbRDP8btogwHSvwoXCaJw8ZS3) [dump](https://solscan.io/tx/FUEBRicDj3hswb24h3KCfXRG5ueyChNYxkm3QbgiWCLJboepX1Th4oWQxJSntdhE2zbbqFAr5uXa4VWHvXnzbRX) |
| 11 | 37 | same | 0 | landx-fra3+nozomi+bolt+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/PnZJ4hySRRutcToEmKvFKaPzTmjYj6B5NbRmbrHjvA62aFbNVZx8XLq9pmPnAVhSYACdPHvLZPuj2HwkVkemoEE) [sell](https://solscan.io/tx/2BHvcrmKyVyjFEkqqwDkCiN9SA9mmZwHNNbLfv41mYPvNCCU7ETfRDg7gWPKSekwGXpt9MqCiRJ9NeG9z1n3MbsK) [dump](https://solscan.io/tx/2KTDB6aopx2a8f3nqRrjt2X2XhAqBAd6ay4giWGAXUNbDiNGJBmNNuApG1L7kXPm1emkn97FSpRzgi1fqKEo6YsN) |
| 12 | 41 | same | 3 | landx-fra3+nozomi+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4RKdowimmaRHxDajLUfqUFNniYZizqcXa7bR1sD7tX9Ujt6YViqzLHyTMrVevZC8LBhiw5sZGimbgjkfayGnRWsm) [dump](https://solscan.io/tx/5hzFzdW2jA7PwUUeji5s4qCse4qXKQ8pDC44JfYEW2rLFKr1qvaLkJJqSKNY5w9Cr6pQS45XELW7gtupgz2nJaVu) |
| 13 | 235 | +1 | 11 | landx-fra3+nozomi+bolt+staked-rpc+helius-swqos | – | – | [buy](https://solscan.io/tx/3NTb6jE6JvXwfGHom6Q4V188beDJA14hF9wb8LCEZCKvLoWbYvoA1CDJZHBkj2HAVaRbjPcgymG4vM4HBD8DT665) [dump](https://solscan.io/tx/5dVfTkEpZ8kPZAtanaH21wmVQMuUgenVraezSAgYPSAkUFczhXddY3H6TLhQyC6839oF7iPRruyEsjTwqwXbALen) |
| 14 | 42 | same | 5 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5k8PpvhQuYiWL3Rh8VcvTEqHWyESQU6QS8swK86oCduJ6d8s4qPeM2J7WqeFmmK9f8F4LNDBn7UESabAmJ4iEDH3) [dump](https://solscan.io/tx/3prWLPArQHjFCyu2hWXE2MJ71wU6Yr1Du4DQLA6xVWqH7WETzcqiMLb5qmjLgzckfuRy9pY9j8JC1PjJWeWtrD3j) |
| 15 | 25 | same | 2 | nozomi+bolt+astralane+staked-rpc | take-profit 1.0 s | 1 | [buy](https://solscan.io/tx/3mK4E944ajtUS7uyQEy6vghZB22VKVSmLQKXShYXdGHpoQhivtb8kWjetarHNNK4gejmbpfzh4oM2ibLYAAhMhLT) [sell](https://solscan.io/tx/2be1HxfHjfEMhVoyW4fsNTcAKYhqqCoDx7rQVhCL23krT3VuttZ8mZa4Mchfd7G6vaq24xWrUTYXo83PwGG2w2UZ) [dump](https://solscan.io/tx/2wTDNVzMSWTEYiNsdHK2KoiXPnJ2ph54vkuKksPdwARLssc2pDbLV8nFNiZY6Koiu11xEWGfFvZ4CMUshAFSkYwd) |
| 16 | 66 | same | 5 | landx-fra3+nozomi+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/LRFhKtEJoKiXuEU83b39MKarhVFqxzuwtkLq8Nd1tmD9bHcPwBqFrsppS8jR8sFPeRR1oadtjVtrCtJux5qwmEz) [dump](https://solscan.io/tx/29HjP9NGLUr5Vijo643nsuLDQ7QEUrBmsRZcW8hESpMyKrgExh9FfN8153XhGBaMzEBCEa5ePCSNftpWqEJzjAk9) |
| 17 | 98 | +1 | 5 | landx-fra3+nozomi+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/5oEanyrrcS36ZVsAtjKWEJKSkmmVBA8e7BDbWuii7aQvtLNB81M38TmAeFUAUW8ibRZWXf24boSiZmy57T6axpzy) [dump](https://solscan.io/tx/H4Gjuqwf1HRMLgBWKJYh1YQrv1jL8M9VEwSkzbWn2nGnNybnTQeKctZ47SRNEoMKKjL3L5Y313vGvwcHNhPx9Cr) |
| 18 | 41 | same | 2 | landx-fra3+nozomi+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/522dt2E5YXicMpe48iARsAbRQk2k8KJX1CNyphCmzFwjSbaDg4VHGXmJiP3SxfYdjtcVZocqtK4YB6QiPUkRrFhv) [dump](https://solscan.io/tx/5P5TtZk5Eu6Z577MKafQL2TLbxsNKXQJsN5UyMXMdVfdhYCr7DK6jFK4nmLSV9cuRXCMYRdT7nDaJpxqmuZFdDSm) |
| 19 | 37 | same | 2 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/4V6tVbFssTGLog1BjwYRr5qBGsrMhTvjwwUrBuvk7mf3G39jiHuqw7m4nrVnWxPnhSUxvVG3Br6L36ofPpiffRDy) [sell](https://solscan.io/tx/5f4BM3unio78HgCdXkTLueQmZz95wCh3ZG1XjkS7uK9LVkAinBFhZtfdEE1MFRu26GXzrjcXJH5NWXgiDFgJKEoD) [dump](https://solscan.io/tx/5faUzHDtj1xvyoMSywUkZ3NEECdEiQBZcMqLmDap3PVBLtmKs5Ybn5bpDBBoRh1sTAQ1PmH5GSiV5j4ssjU4JB77) |
| 20 | 98 | +1 | 2 | landx-fra3+nozomi+bolt+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/SnoWm7DikeiPAe4eCawMcMu9mM1E5W66euZrutQMgYhfXFroXmix39SfYeQNxy4huWA9Xj5apbbapUxQK2zCQq4) [sell](https://solscan.io/tx/4CiQAi1yKjJWqt5VQ78pMiHe222UNNZD5mgTuTKyXmuAayjnkLdXa99SP8CMqxRLgxzas9mVsrUUp5ib8xNmoP84) [dump](https://solscan.io/tx/2Sv8imo1ho9VCSPyWEHAC4WwhzuWG64Ck1yKu93GpprRY7KLe5nv51vqkqkeDYMUtdKgc2qGzyX6sVECcLWsuXj) |
| 21 | 58 | same | 3 | landx-fra3+nozomi+bolt+astralane+staked-rpc | – | – | [buy](https://solscan.io/tx/264haUynpY5rHu2CX1U4bMvgxbMPumM9gWHRk9EdCtj3LoKmpc5uX9qc7piVVDxse2rHKzCP3kURo2LrABLEkCK7) [dump](https://solscan.io/tx/5saLfyu7KxMJWiXxqKzjFq2SjHbjUsB2JjXaakeSaPzx5oduku6WkPeFabosy68cP3RNnzybRi55ELZYmwy2Ka9n) |
| 22 | 93 | same | 3 | nozomi+bolt+astralane+staked-rpc | take-profit 1.3 s | 1 | [buy](https://solscan.io/tx/wbkfXJpu4m7Ca8WSLDbWQD5PUgFz9NexY5QUBAFCSaY1AcXonuiNFYXVZ8CEEmvmvo1P5ozeX7Gbm73cqKjhuAG) [sell](https://solscan.io/tx/4UzD3LkG1MHSgN6CrSBJkaSJk6tTpUhNxQEJPgqWin4qMpzr4rDARuCnxwKA14deQaaq4afeuT9MfLQAbyiG9mET) [dump](https://solscan.io/tx/3s7Erq1xiLqd1iZ7hrwUPediKYfgEtz5d3rAusPhjBjz8N18as7e6dh74dXDNpEBJWgACTR4roM9ybuJZuoEEXdM) |
| 23 | 94 | +1 | 7 | nozomi+bolt+astralane+staked-rpc | – | – | [buy](https://solscan.io/tx/3uruNXVF6fNdj7FwF7YwrRkay2ZfgwdQvP1hYkuEGnvDPXXfGHbVrwiSPhxamWCH7mn71yeEmHLhUkH46eHzM3Fa) [dump](https://solscan.io/tx/25xiEC3gfMA2qcbFpZ5t8VTBVxS5C79gSDMPmstmpWJBK2zhAMDrRakQRExSEq8uuDs4fF5grN4twKCUry3a7LGy) |
| 24 | 50 | same | 1 | nozomi+bolt+astralane+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/4LnYaVr3N2zkGG9P7Cs25eXVALki7NA2AzSLTFz3qMRRmydDGVjeBXL9WBSqkGv1GrXMJKkTUoFWkWsQfjkoniJX) [sell](https://solscan.io/tx/5ufKagu32i87JBSRowHnx6w2Mr1p7bR7na3eU8p4MCCvKEj3UcFoREumZ99jmYtKLsX2j2abP9zwkAYrZKbgpqk4) [dump](https://solscan.io/tx/4bknHqhECmfspkJbhz7bNumJLeAGRvMkeYyPJbWnvrgCb7C6xUNa8Nd7xX72kbi9P389v1YABbsnHsugUCNy4SPh) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| BAM | 11 | 2 | 18% | -0.0052 | -0.0003 | 1/2 |
| Jito | 6 | 3 | 50% | +0.0997 | +0.0337 | 3/3 |
| Harmonic | 4 | 1 | 25% | -0.0019 | -0.0004 | 0/1 |
| Firedancer | 2 | 1 | 50% | +0.0277 | +0.0282 | 1/1 |
| Rakurai | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 24 | 7 | 29% | +0.1198 | +0.0183 | 5/7 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 17 | 6 | 35% | +0.1227 | +0.0214 | 4/6 |
| next block | 7 | 1 | 14% | -0.0029 | +0.0001 | 1/1 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 05:00 | 15 | 3 | 20% | +0.0873 | +0.0311 | 2/3 |
| 06:00 | 9 | 4 | 44% | +0.0325 | +0.0088 | 3/4 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| take-profit | 3 | +0.1283 | +0.0428 | 1.3 s |
| time-limit | 4 | +0.0001 | +0.0000 | 1.6 s |

## 8. P&L leaders
**Best trades:** FGWAR5 +0.0659 (Jito, take-profit, score 0.68); AE3WB7 +0.0341 (Jito, take-profit, score 0.62); Biiv46 +0.0282 (Firedancer, take-profit, score 0.68)

**Worst trades:** 3PsjL5 -0.0007 (BAM, time-limit, score 0.55); 649rrz -0.0004 (Harmonic, time-limit, score 1.20); AE3WB7 +0.0001 (BAM, time-limit, score 0.62)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `3YVoK8UN` | JitoLabs | 1 | 1 | +0.0659 |
| `UPSCQNqd` | JitoLabs | 1 | 1 | +0.0341 |
| `HW4zorvt` | Firedancer | 1 | 1 | +0.0282 |
| `GnC339vk` | JitoLabs | 1 | 1 | +0.0012 |
| `2m1A2WM1` | HarmonicAgave | 1 | 1 | -0.0004 |
| `2Wf9V9rP` | AgaveBam | 1 | 0 | -0.0005 |
| `76rcGHdP` | AgaveBam | 1 | 0 | -0.0005 |
| `2GUnfxZa` | AgaveBam | 1 | 0 | -0.0005 |
| `5zuNci3T` | AgaveBam | 1 | 0 | -0.0005 |
| `mint13XH` | HarmonicAgave | 1 | 0 | -0.0005 |
| `ana2y2Yv` | Rakurai | 1 | 0 | -0.0005 |
| `9eGrDohd` | Firedancer | 1 | 0 | -0.0005 |
| `5ejbTALc` | AgaveBam | 1 | 0 | -0.0005 |
| `HpcB5Qg8` | AgaveBam | 1 | 0 | -0.0005 |
| `HEL1USMZ` | JitoLabs | 1 | 0 | -0.0005 |
| `8gDfqHXZ` | JitoLabs | 1 | 0 | -0.0005 |
| `5EhGYUyQ` | AgaveBam | 1 | 0 | -0.0005 |
| `E1r4Psq8` | JitoLabs | 1 | 0 | -0.0005 |
| `4VrjyXQT` | AgaveBam | 1 | 1 | -0.0007 |
| `DRpbCBMx` | AgaveBam | 3 | 1 | -0.0009 |
| `Awes4Tr6` | HarmonicFiredancer | 2 | 0 | -0.0010 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1385 (p25 1236, p75 1634, n 24) |
| Executed-feed lag behind first sighting, ms | 1.3 (p25 0.6, p75 2.2, n 23) |
| Buy sent → our tx seen on the feed, ms | 56.6 (p25 34.7, p75 96.3, n 23) |
| Fills: our buy seen on the feed after the dump, ms | 45 (p25 37, p75 50, n 7) |
| Guard fails: our failed buy seen after the dump, ms | 66 (p25 41, p75 159, n 17) |
| Fills in the dump's own block | 6 of 7 |
| Guard fails in the dump's own block | 11 of 17 |

**Send-path answers (FAST-ACK lines):** nozomi 24 (median ack 0.4 ms, 1×429), staked-rpc 24 (median ack 3.2 ms), bolt 20 (median ack 0.4 ms), astralane 7 (median ack 0.4 ms), helius-swqos 6 (median ack 0.4 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 2 |
| Guard fails: rival buys ahead (median) | 5 |
| Guard fails: rival SOL ahead (median) | 2.21 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| haqq (dip bot) | 6 | 6 |
| 9pQQc1xy (bait follower) | 4 | 4 |
| HkQ7 (dip bot) | 4 | 3 |
| CVPz447t (pre-placed) | 4 | 4 |
| 2KtcBC (pre-placed) | 3 | 3 |
| 5PuQCemC | 3 | 3 |
| 8HzpVL7E | 3 | 3 |
| 9k78QZyw (fast bot) | 3 | 3 |
| 2HEEWXVw | 2 | 2 |
| EorGEbt1 | 2 | 2 |
| 4oN18efp* | 2 | 2 |
| 6hQSw5JD | 2 | 2 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.2283 |
| Pump fee on buys | 0.0302 (0.0043 per fill) |
| Pump fee on sells (residual) | 0.0321 (0.0046 per fill) |
| Buy tx fees (base + priority) | 0.0035 (0.00051 per fill) |
| Buy tips | 0.0212 (0.0030 per fill) |
| Sell tx fees | 0.0048 (0.00069 per fill) |
| Sell tips | 0.0080 (0.0011 per fill) |
| Failed buys (tx fees) | 0.0086 (17 buys) |
| **Result** | **+0.1198** |

Buy compute used (fills): median 76,903 CU, max 84,405 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 6 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ℹ️ RPC bh-fallback getLatestBlockhash: slow minutes (worst p99 551 ms, max 636 ms)
- ℹ️ RPC bh-fallback getSlot: slow minutes (worst p99 550 ms, max 675 ms)
- ⚠️ RPC bh-primary getLatestBlockhash: 2 timeouts/transport errors (worst p99 117 ms)
- ℹ️ RPC exit-fallback getSignatureStatuses: slow minutes (worst p99 863 ms, max 863 ms)
- ℹ️ send path nozomi: 1 × HTTP 429 (rate limited) on buys
- ℹ️ Biiv46: 2 sell txs landed (duplicate sell)
- ℹ️ Biiv46: a duplicate sell failed with 3012 (the first sell had landed; balance not yet confirmed 0) — harmless, fixed later

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED.

## 13. Fixes and follow-ups
**Done after this run:**

- Exit study on 17 live fills: no take-profit / sell at 1.3 s +0.630 vs TP +5% +0.356 SOL → TP off for run 5.
- haqq on Helius: lands 61% of his trades through the Helius SWQoS-only tier (0.0002) → routes v6 (helius-swqos on BAM / Jito / Agave / other).
- Serial dev bwamJzzt found (owner's contact: 'haqq mostly buys from this dev'): 'mostly' is false (14%), but its tokens pay +17%/fill vs +5% for others in the backtest → dev list + 0.75 SOL size for run 5 (engine dip9).
- haqq's re-buy style replayed on our fills: −1.03 SOL → keep the quick exit, no re-buys.

**Recommended / open:**

- Run 5 (owner 06:25): no TP, 1.3 s, dev list at 0.75 SOL wider tier.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r4.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r4.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

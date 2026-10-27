# Frankfurt run 13 — dip bot run report

*0.35 SOL normal + dev, 1.3 s / SL −10% (same exit as Amsterdam)*

> **Verdict:** +0.0153 SOL on 5 fills of 23 buys (22% fill rate; most misses were the +5% guard).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.0153 SOL** (wallet 2.6321 → 2.6474, Δ +0.0153) |
| Started (PKT) | 2026-10-25 00:59:13 |
| Ended (PKT) | 2026-10-25 01:40:44 — stopped with Ctrl+C (SIGINT) |
| Ran for | 0 h 41 min of 480 min planned |
| First / last buy (PKT) | 00:59:27 / 01:39:31 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 23 → **5 filled**, 18 failed on the +5% guard |
| Fill rate | 22% |
| Wins / losses (fills) | 2 / 3 (win rate 40%) |
| Per filled buy | avg +0.0049, median -0.0003 SOL |
| Fills only / failed buys only | +0.0244 / -0.0091 SOL |
| Best / worst trade | GudTWM +0.0710 / GNBsvY -0.0547 |
| Fill landing | median 42 ms after the dump (seen on our feed); 2 of 5 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip10 |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.35 SOL |
| exit | take-profit off / stop-loss −10% / time limit 6 slots (~1.3 s) |
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
| near-leader gate | 198 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 480 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 11**:

| Setting | FRA run 11 | FRA run 13 |
|---|---|---|
| engine build | dip10 (sha256 b8210182…) | dip10 |
| size (normal) | 0.55 SOL | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.75 SOL | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.35 SOL |
| exit | take-profit off / stop-loss −20% / time limit 19 slots (~4.0 s) | take-profit off / stop-loss −10% / time limit 6 slots (~1.3 s) |

- Owner: "start it with 0.35 size both dev and non dev and 1.3s same as ams".

## 4. Timeline (PKT)
- **00:59:13** engine start #1 (session with 23 buys)
- **00:59:27** big win: GudTWM +0.0710 SOL (time-limit)
- **01:30:48** big loss: GNBsvY -0.0547 SOL (stop-loss)
- **01:40:44** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 2736 |
| Inside the envelope (age / drop / since-buy / size) | 1244 |
| Picks (score above the threshold) | 50 |
| Skipped | far_leader 24, spacing 3 |
| Buys sent | 23 |
| Filled | 5 |
| Failed on the +5% guard | 18 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 5 of 5 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 00:59:27 | [GudTWM](https://gmgn.ai/sol/token/GudTWMjZf13nhSZME5FwzziiViWrDeU7hYvaNovJvdHc) | 0.35 dev | 0.62 | 1.50 / −8% | 2.5 s | Jito `HEL1US` | filled | **+0.0710** |
| 2 | 00:59:55 | [65Xh5J](https://gmgn.ai/sol/token/65Xh5JXnmSzM86c5RcamC8HMdAm7G4kQ7dkrkJCWpump) | 0.35 | 0.48 | 7.90 / −37% | 7.0 s | Harmonic `FNKgX9` | filled | **-0.0003** |
| 3 | 01:01:09 | [GvMhGu](https://gmgn.ai/sol/token/GvMhGuFvoXy5eikCsRmE448TxWULEZAH85BSvXSVpump) | 0.35 | 0.30 | 4.18 / −20% | 18.2 s | Jito `HEL1US` | guard fail | -0.0005 |
| 4 | 01:01:39 | [5Vyhzr](https://gmgn.ai/sol/token/5VyhzrPb9qPwtaXWQ5SZncujVpeu2oVBizHCLpwTAxYA) | 0.35 dev | 1.27 | 3.83 / −21% | 4.2 s | Jito `HEL1US` | guard fail | -0.0005 |
| 5 | 01:03:42 | [CGhzAy](https://gmgn.ai/sol/token/CGhzAyTfWg9MkTy74NAx9T27YJVX4toEd68CCNW2pump) | 0.35 | 0.42 | 5.77 / −21% | 12.7 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 6 | 01:07:59 | [3QYw3G](https://gmgn.ai/sol/token/3QYw3GQLuHvvtLgEuQQiVSUtuXUQinKWamXtpVuVpump) | 0.35 | 0.40 | 3.67 / −15% | 25.0 s | BAM `9jxgos` | guard fail | -0.0005 |
| 7 | 01:11:36 | [FYaXon](https://gmgn.ai/sol/token/FYaXonffVv4ia8AzQfsaeazK6N191sz1HFnc615cpump) | 0.35 | 0.22 | 3.87 / −16% | 3.2 s | BAM `5marvi` | guard fail | -0.0005 |
| 8 | 01:16:58 | [4xtwhV](https://gmgn.ai/sol/token/4xtwhVWaBKy1k42saZT9oQBeiVF8ExLmR6FJ3EZKpump) | 0.35 | 0.45 | 2.96 / −11% | 147.3 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 9 | 01:24:55 | [A1WKnK](https://gmgn.ai/sol/token/A1WKnKDLJR6K9MnrXZpmZ2QwhsWBrGpN5hQ4WwShpump) | 0.35 | 0.41 | 6.46 / −29% | 31.8 s | Jito `C8Bey3` | filled | **+0.0090** |
| 10 | 01:25:39 | [9jo3kZ](https://gmgn.ai/sol/token/9jo3kZG53q8mP9MJVwnLRK8NpksECUTbp16h7FU8pump) | 0.35 | 0.32 | 4.75 / −25% | 5.9 s | Harmonic `5ZqveV` | guard fail | -0.0005 |
| 11 | 01:25:59 | [FHuWQy](https://gmgn.ai/sol/token/FHuWQyb6wkpdursz7PzjYLERw883DiGu72Cm6tHXpump) | 0.35 | 0.26 | 5.27 / −18% | 36.9 s | Harmonic `shftkx` | guard fail | -0.0005 |
| 12 | 01:26:10 | [A3N4Dc](https://gmgn.ai/sol/token/A3N4DcCPw53GupsCKc6kpPKsnakEHtQisG5jCx8LdwFC) | 0.35 dev | 1.22 | 5.95 / −30% | 5.7 s | BAM `CfgRXm` | guard fail | -0.0005 |
| 13 | 01:26:20 | [EiQ74g](https://gmgn.ai/sol/token/EiQ74gg51mxRbvkN7tvhV5vVhc6p6AJYq17aBeDagUo6) | 0.35 dev | 0.99 | 13.77 / −51% | 1.5 s | Harmonic `shftkx` | guard fail | -0.0005 |
| 14 | 01:27:20 | [4iSKaa](https://gmgn.ai/sol/token/4iSKaaMGvAnA1sgcMryep44G8ENZJ7WueuXd8mn2FYzV) | 0.35 dev | 0.93 | 12.83 / −50% | 1.1 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 15 | 01:27:25 | [E7o1Ft](https://gmgn.ai/sol/token/E7o1FtyriJiJtaPiKoVm4zqc4Gdaiy8oN8rL2wz8AD5i) | 0.35 dev | 1.21 | 8.09 / −38% | 2.5 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 16 | 01:27:29 | [FHuWQy](https://gmgn.ai/sol/token/FHuWQyb6wkpdursz7PzjYLERw883DiGu72Cm6tHXpump) | 0.35 | 0.91 | 5.72 / −17% | 128.5 s | BAM `G2TBEh` | guard fail | -0.0005 |
| 17 | 01:28:10 | [Aw88TK](https://gmgn.ai/sol/token/Aw88TK7Sh8ihNAnpz1fYg49NaTWWxxdP4ySMdCjGpump) | 0.35 | 0.35 | 7.97 / −37% | 4.5 s | Jito `HEL1US` | guard fail | -0.0005 |
| 18 | 01:28:48 | [AwdLBu](https://gmgn.ai/sol/token/AwdLBuFhP6SvTei5e34tZHkEXtV1VrmMQaSRTSYupump) | 0.35 | 0.59 | 8.44 / −38% | 3.0 s | BAM `7CR6wh` | guard fail | -0.0005 |
| 19 | 01:30:48 | [GNBsvY](https://gmgn.ai/sol/token/GNBsvYAwV9As2fLjL1CtzXMBz24ykpivoSKMCq1HUNpY) | 0.35 dev | 0.45 | 1.31 / −7% | 2.8 s | BAM `6gnbme` | filled | **-0.0547** |
| 20 | 01:31:17 | [2megwG](https://gmgn.ai/sol/token/2megwGPtMLSwSV5VovhmGsQXFibPDLY4AemQQP4cpump) | 0.35 | 0.71 | 7.94 / −37% | 3.2 s | Harmonic `shftkx` | guard fail | -0.0005 |
| 21 | 01:34:02 | [5eFE4a](https://gmgn.ai/sol/token/5eFE4aBT6TPE4eiww7EcJV3ZuNEvqrbnnUiXaccPpump) | 0.35 | 0.43 | 3.64 / −19% | 6.6 s | Jito `HEL1US` | guard fail | -0.0005 |
| 22 | 01:34:44 | [GhksrL](https://gmgn.ai/sol/token/GhksrL6AdFUevB4XJULdNiNX6Hz8TgxzkgkNcPYypump) | 0.35 | 0.46 | 2.34 / −12% | 1.7 s | Harmonic `DcTPJq` | guard fail | -0.0005 |
| 23 | 01:39:31 | [6bKjj2](https://gmgn.ai/sol/token/6bKjj29Bs3VXW2wcu33H297zMMo1VWF8qqRFSmtJR59a) | 0.35 dev | 0.81 | 5.07 / −25% | 3.2 s | Jito `C8Bey3` | filled | **-0.0006** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 42 | +1 | 2 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/36bQtWamqvXsR62aWj2m3kDUE18YcyFSVtzp4yvS9VN5RQrNDygUkSMyAjnv3BZsxuRTizrqUaRdHFcLcpRZa1jc) [sell](https://solscan.io/tx/3PQcQzXuqmGQxYZaAhCPDEca66DP1nAzPD2oRV7jS8R5uE5jL7Dxwy7v4wrNYmP1HdGjDQctcpWqPteemBGjy8ST) [dump](https://solscan.io/tx/gM2YyTQFFbwBZeFuYp9k63DcL5RYdq6ewRzZuYixmRAzjCvD48b5ac5LAHAtrvR8n8GRCoS2EE6fej7Fs7iWmiw) |
| 2 | 39 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/54Wyvt8LWSotsrt2rGnzWAXFp2mzh36xtsZxCSt1Fnr7KmrEoMPYrh1skXH4WH2wjrPXU8s5XR9E5TYBrbKcNCyH) [sell](https://solscan.io/tx/33gVJvwKtJan3obNi4TQyKN7X6SjWgvMvk8h9nXNjknzZg5UZ9iNPpXJyMLq2Rsi4rNBVdfG8JEMZLuVc8j17kaP) [dump](https://solscan.io/tx/48bpj33E9zT38A3A9vY7sfj6WJCbGrUSGN5eXoaQGqKCKwMxYTcsUQRP97nnWybSPrTFtXxRRrczWT93Zz7beDLc) |
| 3 | 243 | +1 | 3 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc+helius-swqos+bolt | – | – | [buy](https://solscan.io/tx/4GVgZ7ASzdTicXk5vUCF8eVT234eSUMa1tj9P4ijnwWVk6znbbpVCEqFVcun4FxVhuFqUUgNRxtuWG8CJFxpMXFq) [dump](https://solscan.io/tx/CXFGYDJUgaZGbBoiXfokjyHfMZ45GRyhQbGeX8skbfowWrnsbqAersMa9DimewaKVmSNiX6Eq5UkTyiS1dKA4h1) |
| 4 | 51 | same | 3 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4ywSbc6r9x85Qei2f6Uud5YdN8GQxzgiLe7i6V2oNcFFYAXVHBmnk2FubSng53Lm61ovAnp3FkdXtjH6gE6Yy45a) [dump](https://solscan.io/tx/5sQbupDzWbQG8rq3wrxuqoAriSjMHXXX9SWQiaVaJxjvE8oG3wuJQQPqxagMAGyFVG9hpVXM4Nz1QoHnAR1HNtzj) |
| 5 | 158 | +1 | 5 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4Qxn4hxeHHNwA89Z8Mj7iGaTEX98w53Rzq9yGHAiH4b53wfDBvFkaePbAWqFsVnZg26XWD5zq6RF8eVnaC8hgYLi) [dump](https://solscan.io/tx/5djCXpuVDxuSkdxeb1a5LjcZNSDMoPJLscuP5BwydrpKuAh18sFv7Gwdsyo87FL3mpm7wr2ds8xWGoYKp8JxfKFN) |
| 6 | 36 | same | 7 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/3khaR877WFRkn4dX9zDYQb571mFAGSwMrNm65w3xaKMdHQbyXf2XRb6A5iC5c6eLm1n7MsxfzemzGJ47h3wqyS7d) [dump](https://solscan.io/tx/27XPFshQ5LApFScDNgDYjfwqNPW7S6x29an8Abg1R8vJ5mRMsCzTG7tyYhFCGWWJjz8jdKj2xuFjDVerBUtG57TW) |
| 7 | 30 | same | 6 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/bhsD6w74W2CJh73zxTjEqJfBYne2faVNc4krnFVbTRjr1MZtodi673xP9zoCfgbGCUVawZquUnHoosnWuoNpVdC) [dump](https://solscan.io/tx/3wGejiDCmBJ6wX95Sew2GUKAjNVXxyGkFv7Sgup5FXZwa1PmkzVK4K6dUV51rJeZLAD1eEM8HxwZmFF3CpbL42Mu) |
| 8 | 66 | same | 2 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/26tVHPd7RmDJeiJn5XAYYUvBRAK5eWHivj4t5fstojnFtMhwkwUYX5GQMHbJ4uBEVmXe2XYB9QH9f21Po5oAwyVC) [dump](https://solscan.io/tx/3QGR2x2UckcEJNtJ7gau7g2xPUiMQ3SGwJt9Rky8HNhBysu2UPaUqsRHtJbjK49wdLj6gUbpDDs6FxumgGkHsSE) |
| 9 | 119 | +1 | 0 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/4YZSn8PnKfzR3rZXNgV6xe3wHPRvxTWD2sRGaw5X4rWTiGdFMC5QnG7qoL1LbqwqYKoxXJ1LBramqQaLYNAP5QQr) [sell](https://solscan.io/tx/4Lpa2ztyerEMpBurf88AF7nmqCrzc2MYFDcW6QSvBbzrVfT33XuJs62qAXp55NpuLkKeCQjdMWFGFBVeiwtLx5DY) [dump](https://solscan.io/tx/232f2Qs5caBvUJPan6z4qNYikuut79jtghWP5Rat82AQXp3sXwXSdP38ipv8joXVq9UrLoLEE8zhzshFi9gU4gGZ) |
| 10 | 12 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/tBo7eNLkRjteaZYy2agFzvFPpPxJhsB1pAAEkmT2sx31etEUEPtU96tZxJTehuhgjkShqJ5EQ2e4zjUXbNZpYp9) [dump](https://solscan.io/tx/xpVX8VTaGNbidbmvws8BHns6vtJ2aE4jjqYtfaQQ36ugiFhVUsSsorYqPW79PzkuWFA6v8i9N5bKen3EppohmAM) |
| 11 | 24 | same | 3 | **landx-fra3** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/3GEsQ5HSVKrEUWzkRFTRxCtYCcZE8bqPqu83TSGjoGtH9wK6ogqdybxxvBUmRvxJ9qE5NqYM39R7iPSnbrqATgtc) [dump](https://solscan.io/tx/BuEk33G9AoQwAiGEYu5EpfLuGKrR57CnscHLYwxiNSLPevE4EGvpYngBwC3xqpsJPCTpptE4mFp1eiCQWk3FZoq) |
| 12 | 28 | same | 8 | **landx-fra3** of landx-fra3+nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/46nQAjDMuh4MvADojj1aZZqV2pLFPAAoVXCpRVkV5kJPbxjV5kU4gSMduk51UBaqUNZZkRzRNwjG8zUGppHQKRAS) [dump](https://solscan.io/tx/51Bioxn2qzzauMYBaF9HP2Zdmd476LYAWHa7WhQwpXSU7eQz55EMqtw7kkyVSr5TqM9LZHsXzVo4RqocJapBB6PC) |
| 13 | 44 | same | 8 | **helius-swqos** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5DqgUEYyYbTaKcYXEBR85Sfnehnzs3kvS2RzdRGrcH36ULz3D3t63YK1tx8mF8EnjjDEFzqbPv37q1VjWi68HTxa) [dump](https://solscan.io/tx/2iVZfwqJPpj3YoEuxmV4Hw8nuATnZ1TTboRjvXw29ZZxkgVPx1ThQHg9EdvDwnKxo9NV1M91xegf7vTNbetQkE5A) |
| 14 | 320 | +1 | 5 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5qq6TUBkQJMvhnYBXKeB7HhRFCZRW1oSZQu5j72RDdxoqNgsRLQkyMnTw29Kz2JejyGtp76ZyjJi2LmiVRMuMMwb) [dump](https://solscan.io/tx/41u9C7GjAYB8gY95pJbq1JYTKqVFZjSjU4a5snQpCevnv1D4XaC1tFKs46xQ924A56Y89wHRmr8jHc13FSqhPFSo) |
| 15 | 45 | same | 5 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/4f3Z3nGu1CDSpUauBfW7JHfwemZBuyPP2eRES49ZjWNnMe9hd1jZKik1y8WX282EnfPD5vfo432GBy3v3JGZUD7h) [dump](https://solscan.io/tx/3MWXpT25kQ9wMKZF1q76VsKGgy3C26HPT1DRQy3wudfeFuotR7s2CUM2HUGADFpNHqwzMri4BVbYkqed6MwtWoGu) |
| 16 | 21 | same | 3 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/32CZUo6m6b6v6xWzrn7d7vBfEpBqhqMLeEuzpnAKpCsRvJmVmZZeyDGKhqeP1synuohYXMJXyxDKG86pdd581QJ8) [dump](https://solscan.io/tx/658HfDqifk8Zh2AYRB944t2mYzBAXgcQnH6vW97fmwR28y7L6WpwvYsLan77xjFPKRFHtntZV21mGczJ7CXG38ZH) |
| 17 | 95 | +1 | 3 | **staked-rpc** of jito-bundle+helius+nozomi+staked-rpc+helius-swqos+bolt | – | – | [buy](https://solscan.io/tx/BDAPamN1nwuqsULJjcWjA1rXYFvmNXLKK2BhmfQTEgPrKHuuws37WgYBgnqGhy6DT2Mx6uA4JEChCKsjpEkt17h) [dump](https://solscan.io/tx/4CBGigsnuRS869g4gXTY9jDePomuCADJQbgxcknEczCp9wuHfuTAMiNrBVxDfSiMtj736xuP4XANE4jUsCpjpwwX) |
| 18 | 35 | same | 1 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/41b9dAsWyj13CbutpS5ZeAc8yPkn1UJAV4xkFPTrA9wacWnu8PXGGiSr4SiXR3WFT9PNbE1V1jp5WAEPvT6cMytn) [dump](https://solscan.io/tx/2TkKZUyxLnT8bRgWYAQ9CxdkDMvCap1S6RtXDdc687CgPjgza3aABT4tt9MP5gGW5kQcWj5keTEw6hMps4U3jB2) |
| 19 | 33 | same | 0 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | stop-loss 1.5 s | 1 | [buy](https://solscan.io/tx/2QCBUJnTVenPVMqZ9vmytyKtvWmQaBFaK34SSkJA5p8etG8XaCrwMEKXWHMSqYkvmBoTgf3XA372ZeFdFvPwGuEA) [sell](https://solscan.io/tx/2qQKchVe35P2o88W4C7sLw9baGk8pWmUCvmoJMb7xcxFoq4MrGuSD8oACo4byYG7ToyEmUDswnKsmJfSJJywAnYc) [dump](https://solscan.io/tx/kcHGHYNg3ArcA34uBmVzwwdPiocQdG2h5WSB7XnWx9CnwZtfizLuWY8bgVUuhJrRbsNDVK5hM9tPFo29TMh1RYd) |
| 20 | 126 | same | 1 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5qjbunNzFxyzCc1YoDnyqt6iv5cbzapgeS8S4EkrLab3Aka1NRVdCHDdV7d4TLmxgg9QSH4WbK9wH8ebgHupX8iW) [dump](https://solscan.io/tx/4tGKo4DHy7wUwAGsUAR9vqKQdLKJmCMdSbsWF6gvYqToiddtUfGJdxpXzAC561Na9Q5dG6Shx4ZiPjcgtf1bUiT8) |
| 21 | 38 | same | 5 | **staked-rpc** of landx-fra3+jito-bundle+helius+nozomi+staked-rpc+helius-swqos | – | – | [buy](https://solscan.io/tx/FEe6rjn6jh6bynMzPVMvZpqbotA1aBKKzJLRKBVLYyQBUWzv1jWabmb5mh6YutrvJuLE28egogij3acgyudgjHn) [dump](https://solscan.io/tx/2o8jkrw1PaFhYnHh8wqYapQvb3ouTrvYchiVKG51BSjVNLBn4KF8amk5v5HMX28Kziz6CMw2VHSWeECNpUadQCty) |
| 22 | 39 | same | 2 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/3A4Yoe6hJJJ88152j54cW7iBvWwjFd6CHpXoRSwjZH2VujK6anrMkkriQScs7nxLfL5qNVTtrGPVczmb21VhRk4A) [dump](https://solscan.io/tx/4vtsHLGNWtvjDkUiDRYVyr3BzrHyxeKBRhUmRGyG7ngmDMLFoLkEqbLdynYpnY6Akn9BqRd9qvafKH3AVoESLpFT) |
| 23 | 176 | +1 | 5 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/1Eb5srCG8wBjmiL2rdU6tBUxLyoPr1KsQuJT3oK3jK7N3LLEy48eTfM9tHFgSsrAtU2dwj57sCGXcQT1ZMXF2Fg) [sell](https://solscan.io/tx/bLZKT7s2Xi87Gj8HuUGJ6e3rmbwLtb1eA2S5ScmLpvybso5A5AhCxg1GS7Hxg9bnXuBZiuUMug6574qm41TsdWy) [dump](https://solscan.io/tx/4gHRaNbyNeq14vQnfNVFEkkkPXLtUB1sGyVqBrL1U6vXWdPte9heR7ZaYPu3SUkt32HSJ6ugbYxdxJwJ5yUTvLM9) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Harmonic | 10 | 1 | 10% | -0.0049 | -0.0003 | 0/1 |
| Jito | 7 | 3 | 43% | +0.0774 | +0.0265 | 2/3 |
| BAM | 6 | 1 | 17% | -0.0572 | -0.0547 | 0/1 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 15 | 2 | 13% | +0.0021 | +0.0043 | 1/2 |
| dev list | 8 | 3 | 38% | +0.0132 | +0.0052 | 1/3 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 16 | 2 | 12% | -0.0621 | -0.0275 | 0/2 |
| next block | 7 | 3 | 43% | +0.0774 | +0.0265 | 2/3 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 00:00 | 2 | 2 | 100% | +0.0706 | +0.0353 | 1/2 |
| 01:00 | 21 | 3 | 14% | -0.0553 | -0.0154 | 1/3 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 4 | +0.0791 | +0.0198 | 1.6 s |
| stop-loss | 1 | -0.0547 | -0.0547 | 1.5 s |

## 8. P&L leaders
**Best trades:** GudTWM +0.0710 (Jito, time-limit, score 0.62); A1WKnK +0.0090 (Jito, time-limit, score 0.41); 65Xh5J -0.0003 (Harmonic, time-limit, score 0.48)

**Worst trades:** GNBsvY -0.0547 (BAM, stop-loss, score 0.45); 6bKjj2 -0.0006 (Jito, time-limit, score 0.81); 65Xh5J -0.0003 (Harmonic, time-limit, score 0.48)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `HEL1USMZ` | JitoLabs | 5 | 1 | +0.0689 |
| `C8Bey3LK` | JitoLabs | 2 | 2 | +0.0084 |
| `FNKgX9dY` | HarmonicAgave | 1 | 1 | -0.0003 |
| `9jxgosAf` | FireBAM | 1 | 0 | -0.0005 |
| `5marvipG` | AgaveBam | 1 | 0 | -0.0005 |
| `JUPiTERr` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `5ZqveVff` | HarmonicAgave | 1 | 0 | -0.0005 |
| `CfgRXmp1` | AgaveBam | 1 | 0 | -0.0005 |
| `Awes4Tr6` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `G2TBEh2a` | AgaveBam | 1 | 0 | -0.0005 |
| `7CR6whiY` | AgaveBam | 1 | 0 | -0.0005 |
| `DcTPJqPN` | HarmonicAgave | 1 | 0 | -0.0005 |
| `Fd7btgyS` | HarmonicAgave | 2 | 0 | -0.0010 |
| `shftkxns` | HarmonicAgave | 3 | 0 | -0.0015 |
| `6gnbmed7` | AgaveBam | 1 | 1 | -0.0547 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1025 (p25 957, p75 1357, n 23) |
| Executed-feed lag behind first sighting, ms | 3.5 (p25 2.3, p75 4.1, n 23) |
| Buy sent → our tx seen on the feed, ms | 36.8 (p25 32.0, p75 93.6, n 23) |
| Fills: our buy seen on the feed after the dump, ms | 42 (p25 39, p75 119, n 5) |
| Guard fails: our failed buy seen after the dump, ms | 41 (p25 30, p75 95, n 18) |
| Fills in the dump's own block | 2 of 5 |
| Guard fails in the dump's own block | 14 of 18 |

**Which copy landed (nonce fan-out):** staked-rpc 16, nozomi 2, helius 2, landx-fra3 2, helius-swqos 1

**Send-path answers (FAST-ACK lines):** nozomi 23 (median ack 0.3 ms), staked-rpc 22 (median ack 4.1 ms), helius-swqos 19 (median ack 0.5 ms, 3 errors, 3×429), bolt 8 (median ack 0.3 ms), helius 7 (median ack 0.5 ms), jito-bundle 7 (median ack 1.0 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 3 |
| Guard fails: rival SOL ahead (median) | 2.10 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 6n2cCJrr | 5 | 4 |
| 8PgC4ngp | 5 | 5 |
| haqq (dip bot) | 4 | 3 |
| HLU8QbLd (41Pr family) | 4 | 4 |
| 2KtcBC (pre-placed) | 4 | 3 |
| Gq5wJWbT | 4 | 4 |
| 7PedQZmc (untipped fast) | 4 | 4 |
| AEgTuy8L* | 3 | 3 |
| CVPz447t (pre-placed) | 3 | 2 |
| EprLoV21* | 2 | 2 |
| 9DW4QLas* | 2 | 2 |
| 4oN18efp* | 2 | 2 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.0822 |
| Pump fee on buys | 0.0216 (0.0043 per fill) |
| Pump fee on sells (residual) | 0.0226 (0.0045 per fill) |
| Buy tx fees (base + priority) | 0.0025 (0.00051 per fill) |
| Buy tips | 0.0030 (0.0006 per fill) |
| Sell tx fees | 0.0030 (0.00060 per fill) |
| Sell tips | 0.0050 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0091 (18 buys) |
| **Result** | **+0.0153** |

Buy compute used (fills): median 73,598 CU, max 78,254 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 5 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-primary getLatestBlockhash: 42 timeouts/transport errors (worst p99 1002 ms)
- ⚠️ RPC exit-primary getSignatureStatuses: 1 timeouts/transport errors (worst p99 8 ms)
- ℹ️ send path helius-swqos: 3 × HTTP 429 (rate limited) on buys
- ℹ️ 12 send-path health events (self-heal), e.g. `SEND-PATH rpc bh-primary UNHEALTHY: 3 timeouts / transport errors in a row (getLatestBlockhash): client REBUILT (fresh p`
- ⚠️ big loss GNBsvY -0.0547 (stop-loss, BAM)

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Recommended / open:**

- Run 14: the M2 detector in shadow (dip11) during the peak hours.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r13.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r13.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

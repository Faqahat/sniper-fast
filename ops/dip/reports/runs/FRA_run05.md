# Frankfurt run 5 — dip bot run report

*No take-profit / SL −10% / 1.3 s; dev list (bwamJzzt) at 0.75 wider, others strict 0.35; engine dip9*

> **Verdict:** Flat (−0.0014 SOL): 5 wins / 5 losses; one bad stop-loss (wVKcA4 −0.0766: stop at −10% but the sell landed at −20%). No dev-list token came up.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.0014 SOL** (wallet 4.1958 → 4.1943, Δ -0.0014) |
| Started (PKT) | 2026-10-24 06:50:22 |
| Ended (PKT) | 2026-10-24 07:46:36 — time limit / max trades |
| Ran for | 0 h 56 min of 180 min planned |
| First / last buy (PKT) | 06:52:13 / 07:46:35 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 15 → **10 filled**, 5 failed on the +5% guard |
| Fill rate | 67% |
| Wins / losses (fills) | 5 / 5 (win rate 50%) |
| Per filled buy | avg +0.0001, median +0.0017 SOL |
| Fills only / failed buys only | +0.0011 / -0.0025 SOL |
| Best / worst trade | 7Aakts +0.0450 / wVKcA4 -0.0766 |
| Fill landing | median 138 ms after the dump (seen on our feed); 4 of 10 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip9 (dev list, templates per size) |
| model / tier | IMIT1 strict (score >= 0.5419) |
| size (normal) | 0.35 SOL |
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
| route: jito leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: other leaders | nozomi + helius-swqos + bolt + staked-rpc |
| sell path | staked-rpc (retry also via nozomi) |
| near-leader gate | off (every leader) |
| pre-send | off |
| durable-nonce fan-out | off (one tx to every path, every path's tip in it) |
| backup RPC | RMR_RPC_URL |
| holder-reward tokens | allowed |
| limits | max 10 fills, 1 open at a time, 180 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 4**:

| Setting | FRA run 4 | FRA run 5 |
|---|---|---|
| engine build | dip8 | dip9 (dev list, templates per size) |
| dev list | off | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.75 SOL |
| exit | take-profit +5% / stop-loss −10% / time limit 6 slots (~1.3 s) | take-profit off / stop-loss −10% / time limit 6 slots (~1.3 s) |
| route: bam leaders | nozomi + bolt + landx-fra3 + staked-rpc | nozomi + helius-swqos + bolt + staked-rpc |
| route: default leaders | nozomi + bolt + helius-swqos + staked-rpc | nozomi + helius-swqos + bolt + staked-rpc |
| route: fd leaders | nozomi + landx-fra3 + bolt + staked-rpc | nozomi + landx-fra3 + staked-rpc |
| route: jito leaders | nozomi + bolt + astralane + staked-rpc | nozomi + helius-swqos + bolt + staked-rpc |
| route: other leaders | nozomi + bolt + helius-swqos + staked-rpc | nozomi + helius-swqos + bolt + staked-rpc |
| limits | max 7 fills, 1 open at a time, 180 min, loss cap 0.500 SOL | max 10 fills, 1 open at a time, 180 min, loss cap 0.500 SOL |

- Take-profit +5% → off (exit at −10% stop or 6 slots ~1.3 s), owner 06:25 'for next run lets do 1.3 and 0.75 for this dev tier'.
- Engine dip8 → dip9: --dip-dev-list / --dip-dev-tier / --dip-dev-spend-lamports.
- Dev list: bwamJzzt's tokens from the wider tier at 0.75 SOL; everything else strict at 0.35.

## 4. Timeline (PKT)
- **06:50** 24/7 raw recording set up the same hour (owner OK: 'record all the runs raw so we can do this daily')
- **06:50:22** engine start #1 (session with 15 buys)
- **07:46:35** big loss: wVKcA4 -0.0766 SOL (stop-loss)
- **07:46:36** engine end #1: run end

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 3367 |
| Inside the envelope (age / drop / since-buy / size) | 1724 |
| Picks (score above the threshold) | 15 |
| Skipped | 0 |
| Buys sent | 15 |
| Filled | 10 |
| Failed on the +5% guard | 5 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 10 of 10 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 06:52:13 | [AorAyR](https://gmgn.ai/sol/token/AorAyRoTCvAa1fMNuUw4zcxGRNtyFNZxdumuVuSapump) | 0.35 | 1.07 | 2.88 / −12% | 48.3 s | BAM `9jxgos` | filled | **+0.0108** |
| 2 | 07:04:46 | [FCHTPt](https://gmgn.ai/sol/token/FCHTPtULShzVyiqDvt8p3SEhmNaMEGjpvHoghLGZpump) | 0.35 | 0.67 | 1.68 / −8% | 3.0 s | BAM `2GUnfx` | filled | **+0.0077** |
| 3 | 07:06:42 | [7nKLXu](https://gmgn.ai/sol/token/7nKLXuSQ6fLMmkXmUGaTmEfF4kUYuTkEu1hvEQbrpump) | 0.35 | 0.98 | 3.68 / −19% | 15.1 s | BAM `HnfPZD` | filled | **-0.0128** |
| 4 | 07:10:52 | [E5yXCm](https://gmgn.ai/sol/token/E5yXCmwps4MQ7cXSwrGy5t5FcKuGKumPDXsMepcUpump) | 0.35 | 0.80 | 4.39 / −21% | 10.8 s | Harmonic `Awes4T` | filled | **-0.0101** |
| 5 | 07:10:58 | [E5yXCm](https://gmgn.ai/sol/token/E5yXCmwps4MQ7cXSwrGy5t5FcKuGKumPDXsMepcUpump) | 0.35 | 0.76 | 3.22 / −15% | 16.1 s | BAM `5EhGYU` | filled | **+0.0080** |
| 6 | 07:17:58 | [2c5iTH](https://gmgn.ai/sol/token/2c5iTHYUiMRF8MSaTNaJisPfKkfK61fTAWDibK9wpump) | 0.35 | 0.57 | 3.75 / −18% | 14.6 s | Harmonic `CAo1dC` | filled | **-0.0080** |
| 7 | 07:18:08 | [2c5iTH](https://gmgn.ai/sol/token/2c5iTHYUiMRF8MSaTNaJisPfKkfK61fTAWDibK9wpump) | 0.35 | 0.57 | 2.97 / −12% | 24.6 s | BAM `G2TBEh` | guard fail | -0.0005 |
| 8 | 07:24:16 | [7Aakts](https://gmgn.ai/sol/token/7Aaktsg1sLmC2iZrL2j4afaxYnT7iDYuo9DefZtPpump) | 0.35 | 0.74 | 3.46 / −15% | 2.1 s | BAM `radM7P` | filled | **+0.0450** |
| 9 | 07:26:28 | [66LnWh](https://gmgn.ai/sol/token/66LnWhVMusvVcecw4Ktsov8zXLYtxS5nWStzNpSrpump) | 0.35 | 0.56 | 3.56 / −14% | 75.9 s | BAM `HaLanf` | guard fail | -0.0005 |
| 10 | 07:26:41 | [Aodj1A](https://gmgn.ai/sol/token/Aodj1ASGGQTPabQsSs4TXEqcNYY4TYpaFNpNsDTbpump) | 0.35 | 1.56 | 6.00 / −24% | 5.9 s | BAM `8Nvaxz` | guard fail | -0.0005 |
| 11 | 07:32:27 | [BNGrnA](https://gmgn.ai/sol/token/BNGrnAZR6m9GNcnCfdjRQntKdRCKAnkxFh7FeZbkpump) | 0.35 | 0.58 | 3.75 / −18% | 14.0 s | BAM `jzDsim` | filled | **+0.0413** |
| 12 | 07:40:37 | [5tf6Kk](https://gmgn.ai/sol/token/5tf6Kk8fb3gUYTALStGYbWu1qd2Ycddse2Ax4Umpump) | 0.35 | 0.86 | 3.04 / −16% | 25.6 s | BAM `Aw5wEM` | guard fail | -0.0005 |
| 13 | 07:43:55 | [3VGvPi](https://gmgn.ai/sol/token/3VGvPi6G75bbypyofhZKxsCvvTxSmHmSCQ4312p1pump) | 0.35 | 0.68 | 32.03 / −73% | 35.4 s | BAM `5Cchr1` | guard fail | -0.0005 |
| 14 | 07:44:49 | [2Qg82V](https://gmgn.ai/sol/token/2Qg82V8ZzziQG1xVqNs1djEGVktJGsm4nrbXQqbwpump) | 0.35 | 0.68 | 2.65 / −15% | 5.5 s | BAM `9jxgos` | filled | **-0.0042** |
| 15 | 07:46:35 | [wVKcA4](https://gmgn.ai/sol/token/wVKcA4sACmPBRf9wSwvYZVtK2285WtAgs6ndS1Lpump) | 0.35 | 1.22 | 6.48 / −19% | 1.5 s | BAM `Fc6NNd` | filled | **-0.0766** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 38 | same | 2 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/3wHweLRgqNShXnYVNHHBtL2kqAE4rE1F4doDmNXZTVVyoQCV4EF6eXxq8GQE7uZYCP2GjeoCoi2uaHZiVdhhMnEW) [sell](https://solscan.io/tx/5qidzYy94m92dQ56jGYEkYFw9n7ARkvyXevQ6QWfMBigggrZ1Sh1RUsiDbuCpVUAMAuP1ue5jLyapvVMD7sQZMzR) [dump](https://solscan.io/tx/YT7HKsmH5c3rUpvX4ZHqGCMZUJGyU8iz7rQCYkLWrQpiJmPMwBwbWdwZWgTKVakvqt683Jm5Bwzuouu3EaMDiKv) |
| 2 | 163 | +1 | 1 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/28BoDcic5gQZkr4ftjrfzsRkhef9XacR1Fea2Vd1JMD6vjcZB8G8tB2F4EcniAC1j9yFz6CUHcRmxD8neigFjFGa) [sell](https://solscan.io/tx/vevCbjG2PEuPgm3mmCbdGwEHbDdkmch1zVYP1XuUcsLgyCUQmFgRj1VRMhPaQ9PUf2ptm7Nf5E2S1ZpqSTkUN8G) [dump](https://solscan.io/tx/2YbkyYnJpKrScpW2WS4LMuLYZY31o8QmDYjzmYjTox6uhTZTXYVAmH12szx8Ae3WVqKe5vWGbADVMDLHW9RTp1oe) |
| 3 | 140 | +1 | 1 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.9 s | 1 | [buy](https://solscan.io/tx/3fc2JiCJqZ3iAaemSskM1gEsc25V96Qoh6xY6AAtna16BcTpHikdLPTKGFLVDkaWDgcf8BwAUQxk5qsZ6cJaKcdp) [sell](https://solscan.io/tx/xERtpPqXai3nnWDDsBKbBpZubybnmTu3Qk6Uoiv9UHWCkR9m3SeYnQjmQGBd4zsRYhEuR4Xdk6TB1ThVaGZzkZo) [dump](https://solscan.io/tx/5nqdVCWQfeHhrC9mScVDrWsBC7MBxwjLJFVpBGqQgLhaiibh4CiyS5Rcng2L9h3JLkxxM3wyZhYMBvbG8oXeJNs6) |
| 4 | 82 | same | 2 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/4GUBd4rDpLQMEaHAuzHJDdkfw8GbJ4U9ZgH6wrRwCTgtNuNrteZGAHR1DzkowGdkGT8VhxtFWMMqeXfawM5UvL54) [sell](https://solscan.io/tx/2UagWvqZX9Rnw87durxy8GzQSoUQggmAEZDe64HUvYj9JzqUupEs3MhkT4ykATXJhRsPK4tBujLPeZGZJebWA6Ei) [dump](https://solscan.io/tx/gspv5YeRmnxKM4UpKmfakBeBU1A51hbvV18mauEWZNwPfNYko2AMLUVfT4NaZeYgiruLzbTTwNKRXY3qvL3JQuQ) |
| 5 | 253 | +1 | 4 | landx-fra3+nozomi+helius-swqos+bolt+staked-rpc | time-limit 2.4 s | 1 | [buy](https://solscan.io/tx/3rT5FfNvZ88Njq9hKDpTD9JrHhfgzCu7CoqPnhxFJEh9f1QSDbbsrt5wdXnJsfsYgKrjtD3cwPKcSSQLZRRJA5Jn) [sell](https://solscan.io/tx/2JRPPZf1NPndrq9Jqxv91UCxuWieGWDzukajwTifp8WHfwjtsejExwvG9Fs8UfyxE36cBLvzoyHsCDbgrWJNHWD7) [dump](https://solscan.io/tx/RAAg275Sqgb4tPULBxQ92DF1N9DrgCaxQzjQhVCKvYdcjmrKLipAHgppsLdNZS8taZdLupKpZDuiJvmuij9FTAZ) |
| 6 | 36 | same | 2 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/4qyiXJj4wDD9d8TWbJJpg9fdKV8Q81swBZxHRUroWyGRQsTmyrAHrPQNQuSCjeAnPd9HRZCe4rNQaPBepDpQbXAn) [sell](https://solscan.io/tx/jaTVyCE8mJJztdLdKLTJEv7yrjqFiQqufTMSiN6jLm24msgvdQ4tV7iujetwyAqe7ezfum6u6Z46ETBwbDjS4h7) [dump](https://solscan.io/tx/3JTnrzoRaekRTbp9suDMGvmHvTSTsX1eACSVLcbtED6R6NZo8vmFH5eRdf4u3ikvkYym8epW7epHVccaKsgSCHCZ) |
| 7 | 15 | same | 3 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/4Xvbofc5WqFbtz7akT3QhCYsZUtYkWdJXMEAWQz4uqw1rCZwjeduGsV1okL6nWJBv78YV3ZHK7uKn2phb8YEqMHZ) [dump](https://solscan.io/tx/2YKqFV1ZdDcCcoTagiGgNZTj7Bp1zf5SWMLZDE4X22JfwuKkVanUvGbENCz8gV8ev9cJuFHcBdhLXnYSVT3nFoyR) |
| 8 | 168 | +1 | 4 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/65MAW5ADr3qd6UPuvzGBSwys8onmuCR11MHJp9KMo7ueCSQJJsg6vDLBmuyBZ7bBcWFS6Gv4nfE9KuM39nhDAWxH) [sell](https://solscan.io/tx/2itJfMDShabgrZRbCDCNakBmZ82vgdcupi1cnd5iLghK9hbJXSjjQ8FEp6M38DXoGqz45RbmzgmHt1xvjgx61tLT) [dump](https://solscan.io/tx/2NewwysKAnHNm7MQG6smEuUzvLDNqWAjFheS2YwDixffVyEFMbM7xjxHTEtgTsURMRWYjjnpfvDRnRLUc6FGE1xN) |
| 9 | 65 | same | 2 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/5GxtCupJFSqJKN3DduaZmcu3nvLmSGiiPxmouersh67nzbJ5yJBfW1wLJo2qGQABeJntiER2NxDDeCYBqUTYKqj3) [dump](https://solscan.io/tx/2osHzG8HDQpXXjBYWV7iM24tswW7qWxPBUJx6pV1ynq8UW2Q8PPMinY7k1Ez1TLVMQd9wWpK1LW2t7YipBUu12DL) |
| 10 | 30 | same | 5 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/CDJ57m7zN1pYYPt8k8YJhq2duYXyZbXqu32wLpgCE5yZbD82ejgTHx36K49nJoHsqJBe8jbavHyEzn4ZxiUybLc) [dump](https://solscan.io/tx/4XXtwrJoESvRxzhxhR1v8etFYvcEsAZ5CgNjdozKRoX66QiMp6Mr3LRVrV6jK4xLKQpnLxbMsjPdPjtHwyY9MoMA) |
| 11 | 137 | +1 | 3 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/4NeGCKvukZqgebCajGcGS61PP8iHxE3Nk4h3zog9A9DUymTo9DGATSyyZGCNPaqCPF7wZKt6RxsSuW7xkNDycDcv) [sell](https://solscan.io/tx/3axSRs9kNkMtHPzgJ7hqHB5hUSRDA7mnSSCnLRAkuq5c3yRaPkQFsN44HbykMRvUDNSmL5CwbsK7EXxUnG3CcFLR) [dump](https://solscan.io/tx/4dGutaFCyzsbZukEWVnRkPuoMT3dUdgnwATJSYrur855bnWw3dcLwpnvLzcqfQ96oyF96NRCJV1CUxSkZsud7Egh) |
| 12 | 23 | same | 2 | landx-fra3+nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/54xoSmNEZcWHB9voV7kpMxNA4Vcx7bY6R75UGu9mnMu7dA5Gaws3paH6aBo77tGfXrZt1TiZG11aHvQ42C9iDhyG) [dump](https://solscan.io/tx/3dPc2cpEzKMyD86uDaAfin5Xhr5H59eqHmX9TFAELDJChPqa6kYWpSSDqqimQ5QfhfiZAxcr9PQRaTDyWC2u6nNB) |
| 13 | 188 | +1 | 2 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/2LdKNTmYGtd8QvLLn1bcMHUEJ36Kkh7JDiquo141EyQ9WLBXAyTn6tLAsinab9vfMbsXMfNmFBJKks98ysJ6Spcn) [dump](https://solscan.io/tx/exQJvhU1T6nfy5PpANAPKthEX32QrMDXYCErxzTsbcwCnieP4nmC8UzhSwxkVwiamTBiTPFY9JezXniXg9n5kHq) |
| 14 | 34 | same | 1 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/55MrKLUfkoRXvkCWJ41FaWBiyt9uoxJEhaWhXCg9bEgzgfJ1QYaU52ZQkhMkQXbff9yktryJPDKX2ZUA5ByNuMdd) [sell](https://solscan.io/tx/3cqyUZ5b4u2mDsWVio32s5AN2uipvt5QNTF9oz9TVF6v4uBqNjTovbk8UmrKCmRDvaCnd8QxjCUXXrF8WSNLy77C) [dump](https://solscan.io/tx/3uPFeSbK9mkkiwvu8drnKdwAK13y6Q8JD5nPQWFogmFZ7319eBxyh3AyzUCpZWCSpoHizWC4HY3HVUm6MCWsSvfM) |
| 15 | 176 | +1 | 0 | nozomi+helius-swqos+bolt+staked-rpc | stop-loss 1.1 s | 1 | [buy](https://solscan.io/tx/T8MPm8w8vR8QTZhYrTPM1VZQNf77tVQDSFgia6n6FiGR6nigMSGaKZb3dAQHUD7N2arqeKpqh2QUwcJNTE3Jjvv) [sell](https://solscan.io/tx/V1kQ9rTychNdpTTo8DJ1pWwoJVSbqFB8c9WLuaEmTg7atqcygEEwwu6o3wHhukpLEuJc3y8o89yHTw6UZt3rsuE) [dump](https://solscan.io/tx/3ZeV2XjpU3GXS79bDZ4iGfroPFGmwNHJSHEvmuB8ARzcatScu9F8XDn1wcm43o44iR2rJBYuGZLGC4FggUru3hqJ) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| BAM | 13 | 8 | 62% | +0.0167 | +0.0024 | 5/8 |
| Harmonic | 2 | 2 | 100% | -0.0181 | -0.0090 | 0/2 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 15 | 10 | 67% | -0.0014 | +0.0001 | 5/10 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 8 | 4 | 50% | -0.0136 | -0.0029 | 1/4 |
| next block | 7 | 6 | 86% | +0.0121 | +0.0021 | 4/6 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 06:00 | 1 | 1 | 100% | +0.0108 | +0.0108 | 1/1 |
| 07:00 | 14 | 9 | 64% | -0.0123 | -0.0011 | 4/9 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 9 | +0.0777 | +0.0086 | 1.7 s |
| stop-loss | 1 | -0.0766 | -0.0766 | 1.1 s |

## 8. P&L leaders
**Best trades:** 7Aakts +0.0450 (BAM, time-limit, score 0.74); BNGrnA +0.0413 (BAM, time-limit, score 0.58); AorAyR +0.0108 (BAM, time-limit, score 1.07)

**Worst trades:** wVKcA4 -0.0766 (BAM, stop-loss, score 1.22); 7nKLXu -0.0128 (BAM, time-limit, score 0.98); E5yXCm -0.0101 (Harmonic, time-limit, score 0.80)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `radM7PKU` | AgaveBam | 1 | 1 | +0.0450 |
| `jzDsimGW` | AgaveBam | 1 | 1 | +0.0413 |
| `5EhGYUyQ` | AgaveBam | 1 | 1 | +0.0080 |
| `2GUnfxZa` | AgaveBam | 1 | 1 | +0.0077 |
| `9jxgosAf` | FireBAM | 2 | 2 | +0.0066 |
| `G2TBEh2a` | AgaveBam | 1 | 0 | -0.0005 |
| `HaLanfo9` | AgaveBam | 1 | 0 | -0.0005 |
| `8Nvaxzif` | AgaveBam | 1 | 0 | -0.0005 |
| `5Cchr1XG` | AgaveBam | 1 | 0 | -0.0005 |
| `Aw5wEMXh` | AgaveBam | 1 | 0 | -0.0005 |
| `CAo1dCGY` | HarmonicAgave | 1 | 1 | -0.0080 |
| `Awes4Tr6` | HarmonicFiredancer | 1 | 1 | -0.0101 |
| `HnfPZDrb` | AgaveBam | 1 | 1 | -0.0128 |
| `Fc6NNdS2` | AgaveBam | 1 | 1 | -0.0766 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1012 (p25 939, p75 1143, n 15) |
| Executed-feed lag behind first sighting, ms | 1.6 (p25 0.6, p75 3.8, n 14) |
| Buy sent → our tx seen on the feed, ms | 68.3 (p25 27.9, p75 160.7, n 14) |
| Fills: our buy seen on the feed after the dump, ms | 138 (p25 38, p75 168, n 10) |
| Guard fails: our failed buy seen after the dump, ms | 30 (p25 23, p75 65, n 5) |
| Fills in the dump's own block | 4 of 10 |
| Guard fails in the dump's own block | 4 of 5 |

**Send-path answers (FAST-ACK lines):** nozomi 15 (median ack 0.3 ms), helius-swqos 15 (median ack 0.4 ms), staked-rpc 15 (median ack 3.0 ms), bolt 13 (median ack 0.3 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 2 |
| Guard fails: rival buys ahead (median) | 2 |
| Guard fails: rival SOL ahead (median) | 1.44 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| HkQ7 (dip bot) | 4 | 2 |
| 5w8xtjc6 | 3 | 1 |
| haqq (dip bot) | 2 | 1 |
| 6n2cCJrr | 2 | 0 |
| 7PedQZmc (untipped fast) | 2 | 2 |
| EMKY7r6U* | 2 | 0 |
| EaaCfVxV | 1 | 0 |
| 9DW4QLas* | 1 | 0 |
| GDYfTMW6 | 1 | 0 |
| EJX629cp* | 1 | 0 |
| GKd5EMzR (F9 scalper) | 1 | 0 |
| 8dBG7prP | 1 | 0 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.1333 |
| Pump fee on buys | 0.0432 (0.0043 per fill) |
| Pump fee on sells (residual) | 0.0449 (0.0045 per fill) |
| Buy tx fees (base + priority) | 0.0051 (0.00051 per fill) |
| Buy tips | 0.0230 (0.0023 per fill) |
| Sell tx fees | 0.0060 (0.00060 per fill) |
| Sell tips | 0.0100 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0025 (5 buys) |
| **Result** | **-0.0014** |

Buy compute used (fills): median 75,405 CU, max 82,904 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 8 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ℹ️ RPC bh-fallback getLatestBlockhash: slow minutes (worst p99 544 ms, max 798 ms)
- ℹ️ RPC bh-fallback getSlot: slow minutes (worst p99 545 ms, max 797 ms)
- ⚠️ big loss wVKcA4 -0.0766 (stop-loss, BAM)
- ⚠️ stop-loss slipped: wVKcA4 stop at −10% but the curve loss was −18% (one big sell went through before ours)
- ⚠️ wVKcA4 (score 1.22, token 1.5 s old, 6.48 SOL dump): stop fired at −10% but the sell landed at −20% (−0.0766)

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED.

## 13. Fixes and follow-ups
**Done after this run:**

- Exits re-checked on all 26 live fills: no TP +0.70 vs TP5 +0.47 → keep no TP.
- Speed: fire → seen 32 ms when the buy lands in the dump's block, ~117–160 ms when it misses (next leader) → the send → block leg is the lever.

**Recommended / open:**

- Run 6 at 0.5 SOL strict.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r5.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r5.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

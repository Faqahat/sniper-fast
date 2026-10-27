# Frankfurt run 7 — dip bot run report

*8 h, near leaders only (199), routes v7, 0.5 strict + dev 0.75, no TP*

> **Verdict:** Best run so far (+0.2365 SOL, 9 fills, 6 wins). Near-only made us fast: fills ~35 ms after the dump by block position, 7 of 9 in the dump's own block. Two big winners carried it (5LnSgd +0.144, 5mXG5C +0.108).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.2366 SOL** (wallet 4.1874 → 4.4239, Δ +0.2365) |
| Started (PKT) | 2026-10-24 08:04:53 |
| Ended (PKT) | 2026-10-24 15:43:39 — stopped by the owner at 15:43 to start run 8 (wider tier) |
| Ran for | 7 h 38 min of 480 min planned |
| First / last buy (PKT) | 08:10:50 / 15:22:02 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 18 → **9 filled**, 9 failed on the +5% guard |
| Fill rate | 50% |
| Wins / losses (fills) | 6 / 3 (win rate 67%) |
| Per filled buy | avg +0.0268, median +0.0089 SOL |
| Fills only / failed buys only | +0.2411 / -0.0046 SOL |
| Best / worst trade | 5LnSgd +0.1443 / 2mJMZh -0.0345 |
| Fill landing | median 47 ms after the dump (seen on our feed); 7 of 9 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip9 |
| model / tier | IMIT1 strict (score >= 0.5419) |
| size (normal) | 0.50 SOL |
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
| near-leader gate | 199 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off |
| durable-nonce fan-out | off (one tx to every path, every path's tip in it) |
| backup RPC | RMR_RPC_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 480 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 6**:

| Setting | FRA run 6 | FRA run 7 |
|---|---|---|
| route: jito leaders | nozomi + helius-swqos + bolt + staked-rpc | helius + nozomi + staked-rpc |
| near-leader gate | off (every leader) | 199 leaders (buys only when the dump's leader is on the near list) |

- Near-leader gate ON (199 leaders < 5 ms) — far leaders were worth ~0 and cost failed buys.
- Routes v7 on Jito leaders: helius (0.001) + nozomi + staked-rpc (was nozomi + helius-swqos + bolt + staked-rpc).

## 4. Timeline (PKT)
- **08:04:53** engine start #1 (session with 18 buys)
- **12:03:25** big win: 5LnSgd +0.1443 SOL (time-limit)
- **12:58:06** big win: 5mXG5C +0.1077 SOL (time-limit)
- **15:43:39** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 18027 |
| Inside the envelope (age / drop / since-buy / size) | 7393 |
| Picks (score above the threshold) | 54 |
| Skipped | far_leader 36 |
| Buys sent | 18 |
| Filled | 9 |
| Failed on the +5% guard | 9 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 9 of 9 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 08:10:50 | [FGSuyt](https://gmgn.ai/sol/token/FGSuytPhGUShvYSQ3RnXDtwm98vqWC3uzUYFpm4Jpump) | 0.50 | 0.57 | 2.15 / −8% | 138.9 s | Jito `HEL1US` | guard fail | -0.0005 |
| 2 | 08:18:44 | [EwX2T1](https://gmgn.ai/sol/token/EwX2T1p2PmgTsSq2Bi6XtQYxPC5krR4P2fxPfN4Qpump) | 0.50 | 0.74 | 3.63 / −12% | 312.3 s | Harmonic `5ZqveV` | filled | **+0.0201** |
| 3 | 08:38:05 | [2eWVWU](https://gmgn.ai/sol/token/2eWVWU5eLbgJZyha3QLqRUxhdkZ7xfXQGBC3Lzkapump) | 0.50 | 0.85 | 1.52 / −7% | 3.8 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 4 | 08:55:06 | [2mJMZh](https://gmgn.ai/sol/token/2mJMZhjW7JTimUrupT6f9949UdBU3XdaDgJt3skopump) | 0.50 | 0.61 | 4.06 / −20% | 189.9 s | Jito `HEL1US` | filled | **-0.0345** |
| 5 | 09:46:53 | [CACbKu](https://gmgn.ai/sol/token/CACbKus5h8iEpncWfLafR2bPcYB8tvTyokPwA6CFpump) | 0.50 | 1.27 | 4.99 / −18% | 173.0 s | Harmonic `pSo1KZ` | guard fail | -0.0005 |
| 6 | 09:52:06 | [AbdbJW](https://gmgn.ai/sol/token/AbdbJWEXk3Fj9tBZUHfNn32t7KFN2g1JyvkDWimcpump) | 0.50 | 0.73 | 3.02 / −17% | 200.1 s | BAM `9jxgos` | guard fail | -0.0005 |
| 7 | 09:59:24 | [B7cX5w](https://gmgn.ai/sol/token/B7cX5wW3wxHhRzSYTpM56YgMo8pesJjJk6ehz8aXpump) | 0.50 | 0.85 | 3.97 / −9% | 250.8 s | Jito `C8Bey3` | filled | **+0.0118** |
| 8 | 10:46:46 | [VQWGXt](https://gmgn.ai/sol/token/VQWGXtX1oTH6hrGbN1vKknZctzCC8vB5YyACa2tYMZt) | 0.50 | 0.94 | 5.94 / −30% | 1.9 s | Harmonic `5ZqveV` | filled | **-0.0001** |
| 9 | 10:50:24 | [CLtecz](https://gmgn.ai/sol/token/CLteczFPWs4J1Sj5jA5fconkNP7kXxsoUWxHcX6Lpump) | 0.50 | 0.91 | 3.17 / −15% | 5.1 s | Harmonic `GZ4U21` | guard fail | -0.0005 |
| 10 | 11:02:28 | [2fjSi9](https://gmgn.ai/sol/token/2fjSi92rb2VpYX183eXfahjAFZCeof61akNLVDhTpump) | 0.50 | 1.10 | 4.68 / −23% | 15.7 s | BAM `9jxgos` | guard fail | -0.0005 |
| 11 | 11:37:49 | [C3Z7zU](https://gmgn.ai/sol/token/C3Z7zUrvVN7RbaU1zn9jmzkd8ak2iJhQyyKBsfQrNfbQ) | 0.50 | 0.79 | 3.13 / −18% | 6.2 s | Harmonic `Fd7btg` | filled | **-0.0253** |
| 12 | 11:49:32 | [9RRMqs](https://gmgn.ai/sol/token/9RRMqsdzDR8utotWThDEjepyo4X2cHsAKqsMiPpKpump) | 0.50 | 0.80 | 4.28 / −13% | 103.9 s | Rakurai `Ed9WjP` | filled | **+0.0083** |
| 13 | 12:03:25 | [5LnSgd](https://gmgn.ai/sol/token/5LnSgdpgUfs93BAGrDTxgVGKcjNbiPd1RPoJSBpDpump) | 0.50 | 0.66 | 3.97 / −16% | 3.0 s | BAM `1KXvrk` | filled | **+0.1443** |
| 14 | 12:15:50 | [F3CJ9N](https://gmgn.ai/sol/token/F3CJ9NXyZBWigvECC6xwuhb4s4Uq9k2oERrgPzJta1cQ) | 0.50 | 1.03 | 3.12 / −18% | 4.7 s | Jito `HEL1US` | guard fail | -0.0005 |
| 15 | 12:28:06 | [Cifwur](https://gmgn.ai/sol/token/CifwurgDCwesWEcyjLZFutf5e9RCHHW4hMJhbSjNpump) | 0.50 | 1.47 | 3.87 / −18% | 4.7 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 16 | 12:58:06 | [5mXG5C](https://gmgn.ai/sol/token/5mXG5CH8GCJXAa9eYECALw2p5WMpSGhhWa6WSSdspump) | 0.50 | 0.96 | 4.45 / −16% | 14.4 s | Harmonic `Fd7btg` | filled | **+0.1077** |
| 17 | 14:08:45 | [2iFyia](https://gmgn.ai/sol/token/2iFyiaZc6wk9LeN24ZihdfrjJNMAWRns2A7nGKGLpump) | 0.50 | 0.83 | 1.46 / −7% | 3.6 s | Harmonic `BeaCHi` | guard fail | -0.0005 |
| 18 | 15:22:02 | [F55CWW](https://gmgn.ai/sol/token/F55CWW5vHkPzyJ8uLtMi8596khyXcZsfLXEfqGjvpump) | 0.50 | 0.58 | 3.07 / −15% | 218.2 s | Harmonic `G3a3iY` | filled | **+0.0089** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 81 | same | 4 | landx-fra3+helius+nozomi+staked-rpc+helius-swqos | – | – | [buy](https://solscan.io/tx/3XLtSW7corJN1K3CMLLBLMDGXuaXE77TqC5RtQPzVdbk6qYTiL7TepUTeZ8KMgTRoetn7mDNS1guGDhrNZHGATM8) [dump](https://solscan.io/tx/38gehBNYPR7scEo93VWm9LAbd6LMXeFqKqTEBiS3XKB1egCmH5xb5GRkdoqmLLDgWBUiFstcERTQPgGHSMvmjk5k) |
| 2 | 34 | same | 0 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/VJVwcJNXvdv1P3qD2KMCdvGyTjUBh94ySkme2rDvpis87zip8TnLodRhS6zUACd6YU1gp1GZChcvEFQWufuHiUb) [sell](https://solscan.io/tx/77mJpFY1EVvtzzGKYhnopPjxSqCDhnsqikYd1jT3eA3FdybdHoRyKwKKTkssEKgo6voWMjwoit79gtwtdhkPZuZ) [dump](https://solscan.io/tx/2qgv4EvdFiYXgkNeL45Q8yXEJWtpYtQWmf5GPBUEAopYi9hHGoRErpJrBSSbxaWjwgz91WWMuxAwiSDf9V2q5bXt) |
| 3 | 39 | same | 5 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/47ELCyqUKjdWN9vZzmqe4AC3WmGqoQpxFsqz9LzsHxRescsKP7RBHxhtuUTq6m4WKYyFi5xqksE9WfmCCN9g9iyb) [dump](https://solscan.io/tx/3zsQ5mzLy8KAgGtEzvWAJ12ghudTdR3iAQGdyugoDsHmfnVv1grBdhaUEYqpyW519gqVSzkKKS7BpgBYQtXKAtV1) |
| 4 | 85 | same | 2 | helius+nozomi+staked-rpc | stop-loss 1.0 s | 1 | [buy](https://solscan.io/tx/hjGmfVConAsn5FRoBZ6JY7dp3x5hYqgQ7yK91sv5kBgH8QHqsKPP2rCasfLBkjZcrnpqufV1VmjhF3wHvcoukg6) [sell](https://solscan.io/tx/HjcVn6H6ctV66ee7XwAHDt4wZjUCu9HFVCXedZRyEjTb8TcLh1dfs4nQ7xKYYxDywcX8wMfd5toaBj9rRuJydhH) [dump](https://solscan.io/tx/4fZejfFGneoCV4svN2VnYrbncJohjtCt78YDDEr5yy88nLVjfM6LfK6mZJUHbxBeP4P35ZjiyEmBdKqVgh8oy9e6) |
| 5 | 40 | same | 2 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5HCz5e826vw9qbvEZ1FSQhbJyCKt7GxymY3wEd2wZGjuZ4BXeUfc8y6df6BxuscRiARkCw4FXJCt2pXWXaVatsUP) [dump](https://solscan.io/tx/3ebPDbZmFWLfdfpjcRFKqGzeDNJLjLM2W1ENXZDFUUhwna1s1HZuZc2hW8gcwvv9YeUeam9A9DhHhvJUci57Xnnn) |
| 6 | 36 | same | 4 | nozomi+helius-swqos+bolt+staked-rpc+helius | – | – | [buy](https://solscan.io/tx/2vLjHEeAPgiQdPu5CGcxKR1Zh69ZmRsxX6e54psdQiFk8JmW9Lk5mAxD7ZQHNKnL8ErG6p95uAB2CJrUitVom3Z7) [dump](https://solscan.io/tx/5zDWtwJx4uGHXE6DWtiLBTDyXoK99u8UcSW3nzyNWBKcuueC1EYGzSNDo3f7BTUNeteTSPvWKz78Ni8b5USrKkHV) |
| 7 | 67 | +1 | 0 | helius+nozomi+staked-rpc | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/5n1ENv3TJBe6rzDc5Path6Ugqp2CEcNEFMQ9KruPKHCe7RjpHMFQPSzafw1z8eDcCryjpyZPMacrSNjWVYFCy7nC) [sell](https://solscan.io/tx/3iabXjGhKkE31tvdMnETfLA3mbHTjeXZ9k9Wruyz1iSfGKq5oMm7rokaeUTCSNSTH1onGBm1qy6g5G3t8h2QW2pk) [dump](https://solscan.io/tx/3TkkRbA9ZAe9zx4bjgKiNsaY2zTgrcwDqEbLLTtePrBgEjqvGLkhkqCaPnQXibg8yb5itRiacnuR3LJhdJr224Ge) |
| 8 | 38 | same | 0 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/3u1P5yugqQZvAm8gLUvFzxex5vqRb3EGwMd8Hn5xV7ywuFsREcuoNLHZ2pBMBmc2SnCePSDuWiJWV9hF6556yBW) [sell](https://solscan.io/tx/3vjxnMY5ayy3aRycbhNv7egtEbsXYjQYw54gAQ3KiMTidtyLywKbfoLiquL64JY679Em81xsbEfRJGqdCbQwQwYC) [dump](https://solscan.io/tx/5wX6Ez4VDMe5gty5AAqZ5fF6xDMoXaBqpyX8v8sPETGHtrxsahv2nAWXQkpHZCXwsv2S1dgZzvvG1HKsRbXt76ku) |
| 9 | 26 | same | 3 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/DkqU2CMSWRPSynRG73QNKJc9G2Y575MeJbEiYu1eotso1NQUefTMKnV5cPZTFuLnXuCkFLAoDvHpyvB2JNbUvsB) [dump](https://solscan.io/tx/M1yfBD1LZSWHqh6Xt3LSnU84fJTBQGKvrsX39iHdgaaw36BJjPaW2HrkDSn8EpWcrPdterAJciemtEtABzRqnTk) |
| 10 | 31 | same | 4 | nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/t1ZD7nezc5DXjLK139JPpvtvqk9iAmMSPPjDC1YfCBoVdUpNtcSoAzmBR7cCFFW5K4YsriRX4AcURnav54fuK84) [dump](https://solscan.io/tx/2Ggt7Setv7eJoSxmT8gzToFw7zfHSnAdqRjqk1jzsF5dwr6qJRKUB7YB46pknsEVvzzF1GP8JMMY9ENJSQyrmgQm) |
| 11 | 73 | same | 1 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/gJKRuhBK85twRLQjnTECURn9DTLvRAkapMUt1gWMPMqULhi3Mu1oCCCeHV3hvfPFR4ZKvdUihjzrEq7ET5WHZpH) [sell](https://solscan.io/tx/427oMPE9q2ePNZ61dsMaiAPb4pojXhRTQELL31NQKs7PcGUW19BZeZKi1MAevXyN7HwbsUzf4rRzj8jfo8ZvuPbB) [dump](https://solscan.io/tx/2ApGm2o2iDAfLHtqSNtwqggfD7hXWdCfeZKZz2dqM7ifFrbfoCZzo5M6x6GU7MEofa77VRqYkJbFxMYJFwkiDGvK) |
| 12 | 75 | same | 1 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/2VMMA25hbiREKMho9QWJdDq5ANTG4dscWgeKjbFC7WJ7BeZitEEnz5eFh9GijTCG8YBkevux7dGUwDhjEW53oQ24) [sell](https://solscan.io/tx/3yeLzQZ78kWweQSfLrePbsd7e6rkWWEnzBVYXVWh9Q4o16c2Tiq9mBHxSCPuZndxvWjx5jZUyekkif9AJhyK1rCA) [dump](https://solscan.io/tx/4zHrkV8GPGyeYJfcw2aj3KEXsuSLePZ73iptzb8ks8TfubmYjcKJLc8qkhWwbZdfx6KbBbH6cBFa4Xz9kdvqDAAt) |
| 13 | 47 | +1 | 0 | nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/4nTZNp3XuQHeBgqJznhpRZ5uLy9bo9GJCvyPYjEbdgdCGFEuP5JAZ4gokcYvpggqr6LFTkSnZDidVWTPk5SAvSxJ) [sell](https://solscan.io/tx/5wxrP8pedrdpzHorBTcUCvarWJD1VLj1d7YY7sHo8LTHjrdvV74C8fwPQe9cYB58SBybLLusFcZRWihk48NTgMAG) [dump](https://solscan.io/tx/2kagaWsPQQLYGMZQWufN2wpDNcZysPDH22idiGFt2o6Q2JwamAYnBwuEPPszYDesHXcKdE43Kg6tshrQfPeGYUkR) |
| 14 | 121 | +1 | 3 | helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/2P3mqMBRqMxkkB1G4Po7yksHNDSUJgYnh2MRxT29u7xdfm8aJDG9aAyz2rVfUgH5zL2ozjbeSScTNNcN88brkY2j) [dump](https://solscan.io/tx/3V1TebfaiST7GtBia8ZDWWYXpik6fJFNQfZJDpz8qeeSVdpM8fDXuoDjWfN5kpoAa64AHc838Ab1FhsNmLQg3mNt) |
| 15 | 137 | +1 | 4 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/3QUnpy9iLSb39itNs5mHpBUEUymBTneuNtanqHD1PDxXQiaRT7AodbpqH9pWpUuHgYN7KAKR7vPoWH2bJmugkiAJ) [dump](https://solscan.io/tx/575MwtVP6JP9dYzyM8hPfy7mCZQD68dyqLQcacSscRFEz9yVqttPWrgG6GsVUTA6omNsRNsxHFoQuZiSMKjjKXWC) |
| 16 | 35 | same | 1 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/4EFcF5JezanhhJ6TwKGYHopzPdqFiyAt66ikRoU94XocAPJtQAa9oLy48sqnteCZSgGGFunUQFaX7swEwB3WNuXP) [sell](https://solscan.io/tx/mcb2JjAwdbBWR3j52oWSGPAgtAiPBBhJJTb8fqqPAxUjD6htUBJCq9ympo5eepkkmUSR7r7UyWR6RmDwiqYXtE4) [dump](https://solscan.io/tx/4fTYZc2mmwHS362ef9tj8FvHcAGJsACPV9WTXWTWxYpRcUaDzpvUsHjf99kKRmboTwZXbRKUBhyMyHfwuKk6AepT) |
| 17 | 36 | same | 2 | landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/3XbeMLTUFQMHPeDoycNJ14tWWehFisaE1BNS8QpRxf2ny2zk6Y26tawetd3QgVqArBNpywiAm3GABcgqsEgfGkq) [dump](https://solscan.io/tx/4nhP54FU2AXMrPYN8LCdHC4oGwCiQRUG1HY5WAju4r2gF4cujZJjHyFRoAyfsirMFC96VtJezNWS2kiwRVFQFqJF) |
| 18 | 28 | same | 1 | landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/4mwHbDm5KBHMvj6AWPW51vu4i1cZGJs7B5EQara7MKrwDms59jMMgkDAn8iA3Af8pu8JG49spX8jbQ6YtQDbWXQu) [sell](https://solscan.io/tx/2CLEYH6UkZW9WBxntLZbFsPY8oiTMhcgmLhrCuwKUEe1nGHWgwWoaKmWDEVbMRnXmFuc5ArxKQDsiAY6fhb2wnXb) [dump](https://solscan.io/tx/61q1W7cpeZuAKyJFcYbHVbnTTCxjpFT1nmby8LnMKKk3Jb1yyGfjdgB5WGkR4xqhjKmyLk2gXqS2RVq1TdargSSC) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Harmonic | 10 | 5 | 50% | +0.1087 | +0.0222 | 3/5 |
| Jito | 4 | 2 | 50% | -0.0237 | -0.0113 | 1/2 |
| BAM | 3 | 1 | 33% | +0.1432 | +0.1443 | 1/1 |
| Rakurai | 1 | 1 | 100% | +0.0083 | +0.0083 | 1/1 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 18 | 9 | 50% | +0.2366 | +0.0268 | 6/9 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 14 | 7 | 50% | +0.0815 | +0.0122 | 4/7 |
| next block | 4 | 2 | 50% | +0.1550 | +0.0780 | 2/2 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 08:00 | 4 | 2 | 50% | -0.0154 | -0.0072 | 1/2 |
| 09:00 | 3 | 1 | 33% | +0.0108 | +0.0118 | 1/1 |
| 10:00 | 2 | 1 | 50% | -0.0006 | -0.0001 | 0/1 |
| 11:00 | 3 | 2 | 67% | -0.0175 | -0.0085 | 1/2 |
| 12:00 | 4 | 2 | 50% | +0.2510 | +0.1260 | 2/2 |
| 14:00 | 1 | 0 | 0% | -0.0005 | – | 0/0 |
| 15:00 | 1 | 1 | 100% | +0.0089 | +0.0089 | 1/1 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 8 | +0.2756 | +0.0344 | 1.6 s |
| stop-loss | 1 | -0.0345 | -0.0345 | 1.0 s |

## 8. P&L leaders
**Best trades:** 5LnSgd +0.1443 (BAM, time-limit, score 0.66); 5mXG5C +0.1077 (Harmonic, time-limit, score 0.96); EwX2T1 +0.0201 (Harmonic, time-limit, score 0.74)

**Worst trades:** 2mJMZh -0.0345 (Jito, stop-loss, score 0.61); C3Z7zU -0.0253 (Harmonic, time-limit, score 0.79); VQWGXt -0.0001 (Harmonic, time-limit, score 0.94)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `1KXvrkPX` | AgaveBam | 1 | 1 | +0.1443 |
| `Fd7btgyS` | HarmonicAgave | 4 | 2 | +0.0814 |
| `5ZqveVff` | HarmonicAgave | 2 | 2 | +0.0199 |
| `C8Bey3LK` | JitoLabs | 1 | 1 | +0.0118 |
| `G3a3iYZK` | HarmonicAgave | 1 | 1 | +0.0089 |
| `Ed9WjPnZ` | Rakurai | 1 | 1 | +0.0083 |
| `pSo1KZXg` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `GZ4U21pY` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `BeaCHioS` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `9jxgosAf` | FireBAM | 2 | 0 | -0.0010 |
| `HEL1USMZ` | JitoLabs | 3 | 1 | -0.0355 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1174 (p25 1098, p75 1448, n 18) |
| Executed-feed lag behind first sighting, ms | 1.4 (p25 0.8, p75 3.0, n 18) |
| Buy sent → our tx seen on the feed, ms | 34.7 (p25 32.3, p75 72.8, n 18) |
| Fills: our buy seen on the feed after the dump, ms | 47 (p25 35, p75 73, n 9) |
| Guard fails: our failed buy seen after the dump, ms | 39 (p25 36, p75 81, n 9) |
| Fills in the dump's own block | 7 of 9 |
| Guard fails in the dump's own block | 7 of 9 |

**Send-path answers (FAST-ACK lines):** nozomi 18 (median ack 0.4 ms), staked-rpc 18 (median ack 3.6 ms), helius-swqos 15 (median ack 0.4 ms, 1 errors, 1×429), helius 5 (median ack 0.4 ms, 1 errors, 1×429), bolt 4 (median ack 0.3 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 2.22 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 6n2cCJrr | 3 | 2 |
| BUkpShoE* | 2 | 2 |
| DiqYk5RD* | 2 | 2 |
| 64hJxoZz | 2 | 2 |
| E6JasdE8 (speedlanding) | 2 | 1 |
| HkQ7 (dip bot) | 2 | 1 |
| haqq (dip bot) | 2 | 2 |
| 4oN18efp* | 1 | 1 |
| 4Aktn51c* | 1 | 1 |
| 7PedQZmc (untipped fast) | 1 | 1 |
| JSPpg9V6 | 1 | 1 |
| Eqh4dLmJ | 1 | 1 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.3956 |
| Pump fee on buys | 0.0556 (0.0062 per fill) |
| Pump fee on sells (residual) | 0.0605 (0.0067 per fill) |
| Buy tx fees (base + priority) | 0.0046 (0.00051 per fill) |
| Buy tips | 0.0194 (0.0022 per fill) |
| Sell tx fees | 0.0054 (0.00061 per fill) |
| Sell tips | 0.0090 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0046 (9 buys) |
| **Result** | **+0.2366** |

Buy compute used (fills): median 73,755 CU, max 78,404 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 6 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ℹ️ RPC bh-fallback getLatestBlockhash: slow minutes (worst p99 553 ms, max 645 ms)
- ℹ️ RPC bh-fallback getSlot: slow minutes (worst p99 551 ms, max 645 ms)
- ⚠️ RPC bh-primary getLatestBlockhash: 10 timeouts/transport errors (worst p99 419 ms)
- ℹ️ RPC exit-fallback getAccountInfo: slow minutes (worst p99 354 ms, max 354 ms)
- ⚠️ RPC ks-primary getBalance: 1 timeouts/transport errors (worst p99 314 ms)
- ℹ️ send path helius-swqos: 1 × HTTP 429 (rate limited) on buys
- ℹ️ send path helius: 1 × HTTP 429 (rate limited) on buys

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED.

## 13. Fixes and follow-ups
**Done after this run:**

- Replay of run 7's hours: the wider tier on every token would have added ~+0.11 SOL at every speed → run 8 = run 7 + --tier wider.
- Multi-region kit built (owner 16:00: Amsterdam edge VPS): one engine per region, own wallet and budget, disjoint near lists.
- Cost-cut proposal for run 8 (one tipped relay per leader type, priority 2M, CU 85k) written but NOT adopted.

**Recommended / open:**

- Run 8: wider tier.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r7.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r7.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

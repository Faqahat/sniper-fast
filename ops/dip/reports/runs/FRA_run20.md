# Frankfurt run 20 — dip bot run report

*Live: M2 gate + routes v10 (falcon on BAM / Jito / Harmonic leaders) on dip16 (loaded-data limit, route headers, window clock); 0.35 SOL, 5-slot hold / no stop; pre-send shadow*

> **Verdict:** +0.148 SOL on the wallet (2.541 → 2.690). 52 buys sent, 19 filled (10 in the dump's own block, median 37 ms on our feed). Falcon landed first on 16 buys (7 same-slot; 2 of 9 on Jito leaders, 3 of 3 on BAM). Stopped by the owner to start run 21 on dip18.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.1482 SOL** (wallet 2.5413 → 2.6895, Δ +0.1482) |
| Started (PKT) | 2026-10-25 21:57:06 |
| Ended (PKT) | 2026-10-26 00:25:22 — stopped with Ctrl+C (SIGINT) |
| Ran for | 2 h 28 min of 240 min planned |
| First / last buy (PKT) | 21:57:28 / 00:22:39 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 52 → **19 filled**, 33 failed on the +5% guard |
| Fill rate | 37% |
| Wins / losses (fills) | 10 / 9 (win rate 53%) |
| Per filled buy | avg +0.0087, median +0.0007 SOL |
| Fills only / failed buys only | +0.1649 / -0.0167 SOL |
| Best / worst trade | FWLmXr +0.0756 / 4Ki2Sh -0.0646 |
| Fill landing | median 37 ms after the dump (seen on our feed); 10 of 19 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip16 |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.35 SOL |
| exit | take-profit off / stop-loss −50% / time limit 5 slots (~1.1 s) |
| price guard | +5% over the post-dump price (pump error 6042 if exceeded); slot deadline = dump slot + 1 |
| buy fee (priority) | 5M µL/CU × 100k CU limit = 0.0005 SOL per landed buy tx |
| sell fee | 5M µL/CU × 120k CU limit (0.0006 SOL per landed sell tx) |
| route: agave leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: bam leaders | nozomi + helius-swqos + bolt + falcon |
| route: default leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: fd leaders | nozomi + landx-fra3 + staked-rpc |
| route: harmonic leaders | nozomi + falcon + landx-fra3 |
| route: jito leaders | falcon + helius-swqos + helius |
| route: other leaders | nozomi + helius-swqos + bolt + staked-rpc |
| sell path | staked-rpc (retry also via nozomi) |
| near-leader gate | 198 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off (shadow only) |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 240 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 16**:

| Setting | FRA run 16 | FRA run 20 |
|---|---|---|
| engine build | dip14 (speed fixes; shred fire logs only) | dip16 |
| route: bam leaders | nozomi + helius-swqos + bolt + staked-rpc | nozomi + helius-swqos + bolt + falcon |
| route: harmonic leaders | nozomi + helius-swqos + landx-fra3 + staked-rpc | nozomi + falcon + landx-fra3 |
| route: jito leaders | helius + nozomi + jito-bundle + staked-rpc | falcon + helius-swqos + helius |
| limits | max 60 fills, 1 open at a time, 120 min, loss cap 0.500 SOL | max 60 fills, 1 open at a time, 240 min, loss cap 0.500 SOL |

- Routes v8 → v10 (from the landing probes): falcon added on BAM / Jito / Harmonic, jito-tx / staked-rpc / nextblock dropped from Jito.
- Engine dip15 → dip16 (+11% priority via the loaded-data limit, CK route headers, window clock).

## 4. Timeline (PKT)
- **21:57:06** engine start #1 (session with 52 buys)
- **22:51:56** big loss: 4Ki2Sh -0.0646 SOL (time-limit)
- **23:23:56** big win: FWLmXr +0.0756 SOL (time-limit)
- **23:59:27** big win: CxN2eE +0.0644 SOL (time-limit)
- **00:25:22** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 8825 |
| Inside the envelope (age / drop / since-buy / size) | 4364 |
| Picks (score above the threshold) | 190 |
| Skipped | far_leader 114, spacing 23, no_launch_accounts 1 |
| Buys sent | 52 |
| Filled | 19 |
| Failed on the +5% guard | 33 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 19 of 19 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 21:57:28 | [9vRBYu](https://gmgn.ai/sol/token/9vRBYuiKix8jEXTg1afG4XDndRB27rWbb644iKLrpump) | 0.35 | 0.25 | 6.31 / −25% | 4.7 s | BAM `7y5VhV` | guard fail | -0.0005 |
| 2 | 21:59:45 | [ETV96L](https://gmgn.ai/sol/token/ETV96LQwmZZQw5ZRYGFsosjJcetFKDAsCBBGS7pUiv6X) | 0.35 dev | 0.71 | 4.00 / −21% | 2.5 s | Harmonic `Awes4T` | guard fail | -0.0005 |
| 3 | 22:03:03 | [2f8FrJ](https://gmgn.ai/sol/token/2f8FrJS3dpLRTaFha8y8N4TRCJUNTToKDx6qMksjpump) | 0.35 | 0.42 | 2.72 / −14% | 21.4 s | Jito `privaE` | guard fail | -0.0005 |
| 4 | 22:04:34 | [3Kdz5y](https://gmgn.ai/sol/token/3Kdz5y2Bp9xppJQ6kzmTTDDgG2DEoV7w5JPEVpyQpump) | 0.35 | -0.85 | 5.74 / −16% | 10.2 s | Harmonic `Awes4T` | filled | **+0.0303** |
| 5 | 22:07:43 | [4foQFD](https://gmgn.ai/sol/token/4foQFDdH4mwMdjhEsigVKWk6Vn2xADKN5piXoFx6aap5) | 0.35 dev | 0.63 | 6.54 / −32% | 1.5 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 6 | 22:08:46 | [J8GeV6](https://gmgn.ai/sol/token/J8GeV63GywfcfGoGCqKY4D5jRPc4gnxtE6HSgLJfpump) | 0.35 | -2.33 | 2.56 / −9% | 64.9 s | Jito `A9mvuk` | filled | **+0.0423** |
| 7 | 22:17:31 | [HNW7j2](https://gmgn.ai/sol/token/HNW7j2pAvJpdeYeTe3WJrFLz5L9Ee9Hsw3vPi8g9wRai) | 0.35 dev | 1.04 | 3.60 / −20% | 3.4 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 8 | 22:23:57 | [4sDmUJ](https://gmgn.ai/sol/token/4sDmUJ992rVSnDYxEde2GtvHQGzzMrfmCaiwVHe9pump) | 0.35 | 0.25 | 4.67 / −15% | 5.3 s | BAM `G2TBEh` | guard fail | -0.0005 |
| 9 | 22:24:24 | [DXh3KH](https://gmgn.ai/sol/token/DXh3KHy5XDVz2kwM82eLnSMrrPRrFaiVguoVeQkcGAo8) | 0.35 dev | 1.35 | 9.17 / −40% | 1.9 s | BAM `7y5VhV` | guard fail | -0.0005 |
| 10 | 22:26:51 | [5ehDLu](https://gmgn.ai/sol/token/5ehDLuSyeFTGxijbG2kC2ZNuf39Xi4fdRkW5HhHtpump) | 0.35 | 0.36 | 4.96 / −21% | 2.8 s | BAM `9jxgos` | guard fail | -0.0005 |
| 11 | 22:31:09 | [3bCAiE](https://gmgn.ai/sol/token/3bCAiEyZKRPAHrjopvZJJPG8krccQJTmf7inazSqUkbP) | 0.35 dev | 1.19 | 3.68 / −20% | 3.0 s | BAM `CfgRXm` | filled | **+0.0307** |
| 12 | 22:35:58 | [HZ4NiZ](https://gmgn.ai/sol/token/HZ4NiZnG43vgDj8PTkvePAuzJ3TcFDH5AMp1sMQgpump) | 0.35 | 0.02 | 2.22 / −8% | 5.7 s | Harmonic `pSo1KZ` | filled | **+0.0306** |
| 13 | 22:51:11 | [4Nha7N](https://gmgn.ai/sol/token/4Nha7NCsNok9Qu8e1Qxi7vJNqierBnLGkCxAVJiwpump) | 0.35 | -0.81 | 3.47 / −14% | 9.1 s | BAM `9jxgos` | guard fail | -0.0005 |
| 14 | 22:51:56 | [4Ki2Sh](https://gmgn.ai/sol/token/4Ki2ShMQJ92hd8XYXHh158m44FavLtK2y747wc7ipump) | 0.35 | -0.60 | 2.84 / −14% | 2.8 s | BAM `Av8EnY` | filled | **-0.0646** |
| 15 | 22:56:38 | [HeQnbt](https://gmgn.ai/sol/token/HeQnbtbnDfATj48uVCpmbWPemm3B3h5PsSRWSCp3pump) | 0.35 | 0.47 | 3.55 / −17% | 12.7 s | Harmonic `CQdLgw` | guard fail | -0.0005 |
| 16 | 23:00:16 | [AED6vs](https://gmgn.ai/sol/token/AED6vsLNY3N1qaBJo9hkjaHwRxxQo6FvNDT6rDuDpump) | 0.35 | 0.69 | 4.58 / −16% | 10.8 s | Harmonic `CQdLgw` | guard fail | -0.0005 |
| 17 | 23:00:34 | [H52Skr](https://gmgn.ai/sol/token/H52SkriR1ytqAZCPNhxywv7dG3QoYBtSzJKXUdZUd4C3) | 0.35 dev | 0.38 | 2.43 / −10% | 3.8 s | Jito `E1r4Ps` | guard fail | -0.0005 |
| 18 | 23:01:09 | [DoS68r](https://gmgn.ai/sol/token/DoS68rqFHyr7x81PjqCb387DKNN5AHe54KQQfbVx3A2L) | 0.35 dev | 1.08 | 3.69 / −19% | 4.0 s | Jito `C8Bey3` | guard fail | -0.0005 |
| 19 | 23:01:15 | [DoS68r](https://gmgn.ai/sol/token/DoS68rqFHyr7x81PjqCb387DKNN5AHe54KQQfbVx3A2L) | 0.35 dev | 1.11 | 3.64 / −17% | 10.2 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 20 | 23:05:07 | [FMJXtW](https://gmgn.ai/sol/token/FMJXtW5mqRydUB7DUCepqL1kZFacUwmpY5ZZeB1bpump) | 0.35 | -0.04 | 1.89 / −11% | 3.2 s | Firedancer `EvnRmn` | filled | **-0.0068** |
| 21 | 23:09:30 | [B6FuKe](https://gmgn.ai/sol/token/B6FuKeFK9Txs1pcy9gYBUK9DKFFuL8i1PFzDfScpeH3B) | 0.35 dev | 1.16 | 8.13 / −38% | 2.5 s | BAM `CfgRXm` | guard fail | -0.0005 |
| 22 | 23:13:56 | [7iQWvs](https://gmgn.ai/sol/token/7iQWvsRz1LyhbZxy6RNqAB7L1gHXWrXLFsgxhYE3pump) | 0.35 | -0.46 | 2.41 / −9% | 7.0 s | Jito `HEL1US` | guard fail | -0.0005 |
| 23 | 23:14:27 | [DcP4JR](https://gmgn.ai/sol/token/DcP4JR8ACGcxhX8y9N7nCyALayJj2qmMfKeaN3vnpump) | 0.35 | -0.47 | 2.24 / −13% | 6.4 s | Jito `vu1sGn` | guard fail | -0.0005 |
| 24 | 23:14:34 | [2Ko3UP](https://gmgn.ai/sol/token/2Ko3UPixbTSEtaTR8TbxGH61E4Ko4jqZMycaVheNpump) | 0.35 | -0.58 | 1.98 / −12% | 11.9 s | Jito `HEL1US` | guard fail | -0.0005 |
| 25 | 23:15:07 | [ALK8QL](https://gmgn.ai/sol/token/ALK8QLitAR3wrrLgGD8K8bUgWU3Y3EV1fWqxh9uEpump) | 0.35 | -0.25 | 2.88 / −14% | 14.4 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 26 | 23:21:40 | [FExD3Q](https://gmgn.ai/sol/token/FExD3QFqFndXwBUJ7wA7nFZMF3292bF6CGFbiANSpump) | 0.35 | 0.26 | 6.59 / −24% | 16.8 s | BAM `CfgRXm` | guard fail | -0.0005 |
| 27 | 23:23:56 | [FWLmXr](https://gmgn.ai/sol/token/FWLmXr8KowXp3EiLgbDfAEBrV347SQe8SwrJaciBpump) | 0.35 | -0.66 | 2.40 / −12% | 4.7 s | Jito `E1r4Ps` | filled | **+0.0756** |
| 28 | 23:30:10 | [7trCLP](https://gmgn.ai/sol/token/7trCLP3akPQfK7N7Rxe76naC3cabQrK5nRxtijxFxVVN) | 0.35 dev | 1.05 | 7.88 / −34% | 4.2 s | Harmonic `pSo1KZ` | guard fail | -0.0005 |
| 29 | 23:32:45 | [BTWwK7](https://gmgn.ai/sol/token/BTWwK7KR5P1mzBFrFh5aQVQWSMZSGXk4aUGxUi4dEBpi) | 0.35 dev | 0.97 | 3.66 / −20% | 6.6 s | Harmonic `5ZqveV` | guard fail | -0.0005 |
| 30 | 23:34:23 | [B8o4Xs](https://gmgn.ai/sol/token/B8o4XspYf5XFiJk7LT9kXuw7WY3hWi72FQGBKCjKpump) | 0.35 | 0.72 | 3.13 / −13% | 3.2 s | BAM `2t53Lv` | guard fail | -0.0005 |
| 31 | 23:38:05 | [3nfvPk](https://gmgn.ai/sol/token/3nfvPk5c1Cqf8vWNw1Xa2NehCF6eGfpXRTjRSt73pump) | 0.35 | -0.82 | 2.07 / −9% | 2.3 s | Harmonic `Awes4T` | filled | **-0.0233** |
| 32 | 23:41:40 | [38aswv](https://gmgn.ai/sol/token/38aswv17Rtur9PMKuX3hzrGaXQrhYMfaXwVKqm6Kpump) | 0.35 | -0.72 | 2.26 / −10% | 10.4 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 33 | 23:42:13 | [2G5rsB](https://gmgn.ai/sol/token/2G5rsBFusDu7KGaoZiEXPez2wdRtX7ZtcQJREt8Vpump) | 0.35 | -1.56 | 1.20 / −7% | 13.1 s | Jito `HEL1US` | filled | **-0.0008** |
| 34 | 23:42:55 | [7YStmV](https://gmgn.ai/sol/token/7YStmVaayyAPfiLLpGE61jBDXnbVoakyYNuqh72AM4m5) | 0.35 | 0.42 | 3.29 / −17% | 2.5 s | BAM `Va1idL` | filled | **-0.0120** |
| 35 | 23:45:53 | [H3E2xT](https://gmgn.ai/sol/token/H3E2xTVTtrdpxeKtBn8DNL9Z9w5DM5EKNht1XHSUpump) | 0.35 | -0.66 | 1.95 / −12% | 8.9 s | Jito `privaE` | filled | **-0.0120** |
| 36 | 23:51:53 | [ECXyKx](https://gmgn.ai/sol/token/ECXyKxJMxPwATAcB8swURkrxCUHA9PNkQnrZDy1Maxi5) | 0.35 dev | 0.34 | 4.72 / −24% | 8.3 s | Harmonic `9W3QTg` | filled | **+0.0135** |
| 37 | 23:52:07 | [6njaM9](https://gmgn.ai/sol/token/6njaM96VRyUYxwRRqmwuqhEmh2PSmC8BgXtiEohZpump) | 0.35 | -0.17 | 1.98 / −11% | 3.8 s | Jito `EUcJwf` | filled | **-0.0269** |
| 38 | 23:52:08 | [EPNtZY](https://gmgn.ai/sol/token/EPNtZYia4hAJzjsZ2KQo6SePTkkWarN2x5EqWtz8pump) | 0.35 | 0.18 | 4.42 / −15% | 2.8 s | Harmonic `5ZqveV` | guard fail | -0.0005 |
| 39 | 23:52:17 | [2FRfGF](https://gmgn.ai/sol/token/2FRfGFwCbQQ4DSptQSs8yAwH9JvapDnD4P375RGNTzCM) | 0.35 dev | 0.83 | 4.96 / −22% | 1.7 s | Harmonic `DcTPJq` | filled | **+0.0169** |
| 40 | 23:52:40 | [FRY3gU](https://gmgn.ai/sol/token/FRY3gUKrJKKL86ukrUZkzP61P55pTw36NGYpT56apump) | 0.35 | 0.15 | 3.06 / −11% | 8.7 s | Harmonic `GZ4U21` | guard fail | -0.0005 |
| 41 | 23:52:51 | [DroPiq](https://gmgn.ai/sol/token/DroPiqYQoEtadiSNF6VPbUfMMxD7bPZ7Pp5JkdpwoqwL) | 0.35 dev | 1.25 | 5.84 / −30% | 4.5 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 42 | 23:53:57 | [FRY3gU](https://gmgn.ai/sol/token/FRY3gUKrJKKL86ukrUZkzP61P55pTw36NGYpT56apump) | 0.35 | -0.77 | 4.94 / −14% | 84.8 s | BAM `9jxgos` | filled | **-0.0001** |
| 43 | 23:57:16 | [FwjDsq](https://gmgn.ai/sol/token/FwjDsqYwZDDPBtYUEiwCJHTYRkisiMVxmcVC7gPjpump) | 0.35 | -0.89 | 6.70 / −32% | 4.9 s | BAM `GEM1N1` | guard fail | -0.0005 |
| 44 | 23:57:52 | [7bytb7](https://gmgn.ai/sol/token/7bytb7oo364tmiFCdFJxAkJb2RATwwiwv38dN6pFyMzx) | 0.35 dev | 0.64 | 6.73 / −31% | 2.8 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 45 | 23:58:16 | [AsDx1E](https://gmgn.ai/sol/token/AsDx1ENsaQyCnWiKZnGgKKi5tKtiNkMetrjBEGFUpump) | 0.35 | 0.30 | 4.78 / −19% | 4.0 s | Harmonic `DcTPJq` | guard fail | -0.0005 |
| 46 | 23:58:41 | [Fx9Gs6](https://gmgn.ai/sol/token/Fx9Gs6hD3xb65qrTcPe4NT885ZQCe6MrYgArfWiFpump) | 0.35 | -0.35 | 1.76 / −9% | 4.9 s | Harmonic `HnrXmm` | guard fail | -0.0005 |
| 47 | 23:59:27 | [CxN2eE](https://gmgn.ai/sol/token/CxN2eEVo1gp3VCLefwaMZp8D2j1oGWeKSjxzP6GUkdbt) | 0.35 dev | 0.65 | 1.71 / −7% | 3.0 s | Jito `HEL1US` | filled | **+0.0644** |
| 48 | 00:01:30 | [9h89az](https://gmgn.ai/sol/token/9h89azrt3e9GaymoZAqfu1yyXjc5DTP4wM5YNU5ipump) | 0.35 | -0.12 | 7.26 / −35% | 5.3 s | Harmonic `Fd7btg` | filled | **+0.0007** |
| 49 | 00:02:12 | [E4pPJb](https://gmgn.ai/sol/token/E4pPJbYyenbgXuQJ2ioYb6ZVreWLfQYF8JdBvxcZhbUt) | 0.35 dev | 0.49 | 5.68 / −29% | 4.5 s | Harmonic `shftkx` | guard fail | -0.0005 |
| 50 | 00:07:08 | [FZRs2f](https://gmgn.ai/sol/token/FZRs2fppz2KU8Ean9mmvboXQrfDvbPNP8nUd1qSjpump) | 0.35 | 0.09 | 2.96 / −17% | 1.9 s | BAM `9jxgos` | filled | **-0.0120** |
| 51 | 00:14:02 | [5qzhbf](https://gmgn.ai/sol/token/5qzhbf4S3dCD4bUyP4YJtbJfxuoTJW3C5jakroP4pump) | 0.35 | 0.10 | 4.83 / −24% | 2.1 s | Harmonic `SFundN` | guard fail | -0.0005 |
| 52 | 00:22:39 | [8CpPus](https://gmgn.ai/sol/token/8CpPusVaSBNeFxDW5gtA3jo9hPYEdSR5mFbaydbD73VV) | 0.35 dev | 0.73 | 4.32 / −20% | 6.2 s | Harmonic `Fd7btg` | filled | **+0.0182** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 39 | same | 5 | **falcon** of nozomi+helius-swqos+bolt+falcon | – | – | [buy](https://solscan.io/tx/MtF8aXzg1Mc5ENZZRXqR7RXA2p26bonRcRA4N9DumHTByG8eH3G1yypz6vpn1UQci6v3ScA4kGQPZWtRpPAYDwt) [dump](https://solscan.io/tx/5TVLbiR4NBCt6dbzNtQpgVGUtHUGzQVoryyQSTcEkdnWXr29LPbgqoQu3oZpYVGLNVfrnqeQ1RGe2PHhT1bXTxhB) |
| 2 | 35 | same | 4 | **nozomi** of landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/5QTFnbacZi4yr98nefAfLqdU1ZsW14gHbeeAEqe8cWnbb3hGZgZBTEBcG4bwUwE4R5EeBrJFre2y5Dyx8sQuMYc6) [dump](https://solscan.io/tx/4tmHPN6bDfXP6pUxvJptR5q3sRWhACauGiy6JwdXh9WhJfY7xgf4AbKNEg7XmhYASdgFNkPJbjqWeaAtEUqyEvkB) |
| 3 | 48 | +1 | 3 | **falcon** of falcon+helius-swqos+helius | – | – | [buy](https://solscan.io/tx/2Qov7PXQeqBFNBAF59Ji6fZppasGPfMF97L3RYndDkZ5CoJ1Dc7SroqbrYa7tLxPkMjEJJnRuYpKRq2LWhJKzeMZ) [dump](https://solscan.io/tx/BpwYTXn6SERZUD5eM4GPRhpm5Art9rTge2NopjvSZVmK1q97auwnfzZdPvtGsmi9m7owXS7pfwAyGTsBQxkdcpB) |
| 4 | 37 | +1 | 2 | **nozomi** of landx-fra3+nozomi+falcon | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/GbV4rYqsV5PbnUpNjpJEEnpitbZd6jeHEj359Abo2h8Bq61vbpxG6viYxDQMghwhz6MbYFGabfMLf6ADVZDrzot) [sell](https://solscan.io/tx/49GJPNtarxHKtAy2hZx5rxfzgvCsoNJvBc6se7W38ZXGr9seqYnZ47EuvY1H4BxxdTRjxQ2rGL3MW92PgWp4Prdy) [dump](https://solscan.io/tx/2gRfsHBUXxkttPeLxPZX7iJu1HxSNNYcdJKKiSw39eG52hW6VZVbZRewFRuruznnzxtMAVo1gfPjvzcwaubhDEgw) |
| 5 | 149 | +1 | 5 | **falcon** of landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/AW29ziw2cQu7hYzoR36QbDqAgL7F5Z5C5s6mL8Ndn3YdcpMvsFqJ2zbaxV7r9pc92uY8fmQY9g7bJAa9omSQ2k6) [dump](https://solscan.io/tx/33UTtk2SV4dsiF3zvGqBKCvnDp2wzuKFnBwipDXbWCrLmMscCaiz4jobZLg9AHGCgxsvXbui3XHLxFHgRHSCuRAn) |
| 6 | 14 | +1 | 1 | **falcon** of falcon+helius-swqos+helius | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/5eS6pnSX8TnhyGwvyhQ4ovKzMWLNceFdNPQdLcpnr85zJ9WX6adwsHW5S5WvqvyWGGXnJ7WVPKWkhqC2uM32ckrY) [sell](https://solscan.io/tx/M75umoc6WcTs2HT737MJ8ubyaojoHQpBJk1opXLLpiw9TmZdc7fRh1rYoWrFZdj92PENVQ3qEyeruA1USpk4tRj) [dump](https://solscan.io/tx/3mA6GSxJcKbH3jkDD6Q6VqMVXChaECvoaz4AAtz9PswxGtV9EYCJtUbAm3gBBEGrMb3bcNo8jCNwPE9KH6aeCwVt) |
| 7 | 128 | +1 | 2 | **helius-swqos+helius** of falcon+helius-swqos+helius | – | – | [buy](https://solscan.io/tx/2rDC1AmGCxXuEDTyL4JJijbi8u8cWPxGHhttoiYh6U19E9C2Quhj8zXT2ADTkgJo3DNEkJz4oxkuP4cCMH2rX5YM) [dump](https://solscan.io/tx/26DkDVJEMqZfNnhk8k3LWfr9GrDsMFvSprcJ1RT53FHz5YW5CCqWFmb8jXVUezuWFxHpzUJf2ynhh9rmWLV9BD7m) |
| 8 | 37 | same | 3 | **bolt** of nozomi+helius-swqos+bolt+falcon | – | – | [buy](https://solscan.io/tx/3Tp4X7JhedHukwZX3nkVP3mx7W1muJUXa9o5hN3MAB8eyaWK1zXV9GibiuxVQmeofcdftTKn54diWwcFWTtr64kj) [dump](https://solscan.io/tx/5bSvFn55BvMyyfeTkz3fvLxSZNXPSC3Geu2CygKHy5PTe8SUNMb1KuUEuaYHnPm5eZMxP68PXHz83z8eSu9U1vBb) |
| 9 | 42 | same | 5 | **falcon** of nozomi+helius-swqos+bolt+falcon | – | – | [buy](https://solscan.io/tx/2x3chQHkHP4Gg1eEvirMGm3UxaYzMcKRq2pBXyFYvzf35XgJGiANZfy6J4YCA7S6gE8m9dyZYCNjMr4Sk8fBde3) [dump](https://solscan.io/tx/4PXydJhfUuLByX8RrwhyNkZAouSRYTffCdJRBJdPdQKqaYFWTyrcuQpzqS625UbVEtdvZqhVCW5itzv7MRF4g1qT) |
| 10 | 33 | same | 3 | **falcon** of nozomi+helius-swqos+bolt+falcon | – | – | [buy](https://solscan.io/tx/3hHs6yH2toGdHbH146mnJgVBSow77MREhtzDMaE5TPx1i46kpDYnKYeQ8tp4UCLpo4ncdpw2KhcbZYmhX1Jnxf8S) [dump](https://solscan.io/tx/ukLqi3tZTfSovtH6XDUwtf9QbCWXeM7rjgMKKE27wNDyUYXTqeR248BuGP5o2gEB4Wy5QdMom3TFf8NWqwoBNsB) |
| 11 | 23 | same | 2 | **nozomi** of nozomi+helius-swqos+bolt+falcon | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/r1vTQ665sojzaPzGtDMFADCBJ66jMFYeSiFABbVadMvwJxHHVrBfWwyL2EY5KWomDw4zihmnMHyz3v7JatXVshQ) [sell](https://solscan.io/tx/216o9QS9Sch9n9uT2qPefBkgRScR1qFC7NfzUUvpgyds7Cu8AgQpWnMmzGDvATzp16BrSs4LvoqdrZumnuyyBEab) [dump](https://solscan.io/tx/4QrCgJ17D1rmeWC6SdmvV91AKej7dqJVKim9xasPFDe5BvugeyBNQg5JL2vHec7oDgu8CPJftB9qWA7rtxMoKcte) |
| 12 | 37 | same | 1 | **nozomi** of landx-fra3+nozomi+falcon | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/4AadVRWzhqMASeBZDXYe54ZKTJ4uKx3ecnzphQS5amp7XGA8r27vd9zRCBd7shXf2FiLhgZwYSbN9SxtrzNVBjDu) [sell](https://solscan.io/tx/4czw8Er8emMBRBnFCj89F9uiPFfSbknWHKfUTsaG1bbHtXnL6xwrkh387TA4ccbMH82NssUTE7i4Nzatwy2NeNQg) [dump](https://solscan.io/tx/4pMJNEf18rFpv7EjfxhKYo37BCzFavE3d58z6ts8cTAJ3woaGV5jvXb7ab1hU2UHyJY7xV5toEgXrXMaCb7ZwtMY) |
| 13 | 44 | same | 4 | **helius-swqos** of nozomi+helius-swqos+bolt+falcon | – | – | [buy](https://solscan.io/tx/5F6bqrecbH9GRVfJT7ER3j7cpUFRk1otFqbybBCMDWJawjJLvZHHqbKcdjpTUjPCH6ii6oT5yvdd3srBh9kdEYRH) [dump](https://solscan.io/tx/rRJ9xMPzd51jzaE7AR914xYJQstft1Lv39FNdB2Yz4K7AhCudBBnBqfqZic6ENe8nruYZfz6i9U6NHLEbDB2cHx) |
| 14 | 21 | same | 1 | **nozomi** of nozomi+helius-swqos+bolt+falcon | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5HAkEXmGEtej7y5Ffsvfoac3T9HGZ7PUA4wP9RRN4qvDWbD5wF1wGzdJjPNoEf3fe8iJNYdxLmSPURbhC9enKb9o) [sell](https://solscan.io/tx/5Ty4kE7suc4j9URLaMYqriZWSnqfVRkmm2SJrgezhzk3UFqgFgyoxJriGCi4YkRChUkquumL5rEwUkT2bf9b5gwE) [dump](https://solscan.io/tx/2MCb7i7KvUi6PygJAGWVZowmKw5f5zETe7FUGynBYTvwf4xKJp4zi2EG6KWJgPgjpdxaFzTSQDDnkiiUTRJKfxCc) |
| 15 | 63 | same | 6 | **falcon** of landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/2Q9GK5PpuBQLUrvUCEEAhbpsL6ZUep8teVB8fVBTET35U9e3p1LWvLTJs3hDKFViwrJC1vjtgfrP1wAX8qShcKQx) [dump](https://solscan.io/tx/5qr4QwGpuBs8msgsK8CW3HmSeCSnMewHNZv2MA6qLXTTe6SV9SrdJGje6BnkCVxkT6Hv5pKXRLzsRPJHfqjyYFin) |
| 16 | 18 | same | 4 | **landx-fra3** of landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/4BH7P1JnAN32LrLKeFpMoWf3GrQriKxoanmt7EUHWLLwMVfm27Tmp1WJr8giuMFuy8yGZnLvs2qUsuw7fxzwg9PQ) [dump](https://solscan.io/tx/4HoMWUNHRbxFQByUYcqaQyR91MbZsLBFBckZrK6J4StWEhtCo1vVXR3WfaZuthik1wSbg2Q4w1YYzPemQBqdhQhv) |
| 17 | 65 | same | 3 | **falcon** of falcon+helius-swqos+helius | – | – | [buy](https://solscan.io/tx/4w6N3QSSYFbrdVrX8SKZGVCuVbbWiQQr3bHQFqBKE8TKq5DHGfdYjCgaGhNTzW6aMQVLnJkGSYs6X3qp5fKwjpMz) [dump](https://solscan.io/tx/39Eq8LThPWJdoViTWrJ75EgAaxaZ2YU6hiia33JGEuLg8vGAyUmf6yvAEkpUHsHUCnbSi1LWHq3Zvet46xKJhaGr) |
| 18 | 186 | +1 | 3 | **falcon** of falcon+helius-swqos+helius | – | – | [buy](https://solscan.io/tx/5gSf1zdnd7wR7RuD5c36jZzqZ4NVobnPGNVL6qoVG4jZGU9tVXprosPTXJPBVVDHnGyySomubgP7AcGSgQUYSUQE) [dump](https://solscan.io/tx/3u48QvnXj1PqjZX38sBG5VH1aTSqxb25hGdztqp18dtSdh4aec5ZqJ4mVaNgbTcSYuVZjfTH4XpRFqzcYZz7NER2) |
| 19 | 22 | same | 6 | **landx-fra3** of landx-fra3+nozomi+staked-rpc+helius-swqos+bolt+falcon | – | – | [buy](https://solscan.io/tx/5ikQDFPVXMhKRqXc23HHUumY83W9duvfXLV3QKnkgkqVqxQurebHEBQNYgj5S28VjDjEAV3Ec3PSraB5RWHR1f59) [dump](https://solscan.io/tx/2C86pVHxjKe8qJ3TsVsvKuuhNH2FZPa71xDangAtqC2TwdGm2JP3mRECt4HGyawAkUPGgtXYcrGwt1eTW8hKMZD) |
| 20 | 29 | same | 1 | **landx-fra3** of landx-fra3+nozomi+staked-rpc+helius-swqos+bolt+falcon | time-limit 1.2 s | 1 | [buy](https://solscan.io/tx/2eV4ydx6XztG1wUtJA3axNvgbBiNw2Qz8oM3V1jCwZK62PqJtjSbZhbGJcyGfxHgdojGEHHPwSTveQHpGaPzDrP) [sell](https://solscan.io/tx/3DG5Wa9v5EYibUA6YQxLRCGi1bAgGgny2K1xVaXN2YqoK31qiNnpdgT2y8m1nhT5GR2DKU2uDSMQVjBS7GHNTpFZ) [dump](https://solscan.io/tx/2WDqFPfxhxk5dGroVUoiGD8aaTN1VHiD84g2tSL5j7DF1qPu9yPK2QLTT5XbhGv16wcpYKnNzmfBTUSXVxgfw3fq) |
| 21 | 32 | same | 4 | **helius-swqos** of nozomi+helius-swqos+bolt+falcon | – | – | [buy](https://solscan.io/tx/2uttJ7TSQkeShXmAnaNTZ6jX4H5k17ZMtQYgFJLiXYrBwBRjFujJ9Vy24o1NivGX9mvZqyje9pGwxNc2qfh8BvJt) [dump](https://solscan.io/tx/4zPNoL7Q9J7wuWMsx1jTreL5anfGybozarG5zPg8s889AqNud8RWRrHepg2zpWXveEZXiPUExDUuP1myN23UHaUH) |
| 22 | 88 | +1 | 5 | **falcon** of falcon+helius-swqos+helius | – | – | [buy](https://solscan.io/tx/2pafvFHajYCqv9Q5aWZ48EB2b7Nqqzxxqkz7a8dfZ62jUAQTgNtSJF8vFhsRVQysS18qRn7KWjBYdcTGqXoW5XPi) [dump](https://solscan.io/tx/2RSyCG7bBxESt8CYZQv6jnFZH84wFmdGTMUgJ1UZAKgFcUuM8yuxqaV3ywwn7hCj24yCii2kGn5K68ap92oC2Ad) |
| 23 | 91 | same | 4 | **helius-swqos+helius** of falcon+helius-swqos+helius+nozomi+bolt | – | – | [buy](https://solscan.io/tx/4fAFsacFYvMR59CBSvXrqWA8DPuKWFpsb8KiypkeV67VLzub1ubvttftPYhqURYb6Cji6LjuX14hp7xbo657LgeH) [dump](https://solscan.io/tx/CWrcJpvdTT8dPUi8cvVEJaWviaYA3PU1J6SvKg8qYG9aoQBYR9voZ2X2SSe4k8wd5thqUubU7TKpt4UQ6YygULp) |
| 24 | 96 | same | 4 | **falcon** of falcon+helius-swqos+helius | – | – | [buy](https://solscan.io/tx/3xHM5C1hHRnAVPWGbh42PuVgC6JFKRMTV3XytRyDbWeCMGQaSr98uerkX2ZVABH3BXSKPXLXabJtKzr1eDWWZnKv) [dump](https://solscan.io/tx/4XiRM9h5Am6BFdcFoh1n79hWreEj5zk1dC7VYoDu5j9vXD7zqncBYUn1R6pfpAviCGqnF7arErNpHjLHNF5SBC4h) |
| 25 | 66 | +1 | 5 | **landx-fra3** of landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/2B5VxmUKUGWa6XTxe2T1NLPk3qC7FnmyDSCcZu1tMTsxsv89RCid8rMgBcQ7tV51Ta7jqkpdjbjQBtuVHU5rqM2r) [dump](https://solscan.io/tx/HQWYnsGYoDwh5CSZpDxNP17jvfTK7pZnfoGmC77rsR9yFbKsgwuRqQK8yWc3JuuXQ7NHxquZBKCcbcikZnAJ6R8) |
| 26 | 44 | +1 | 3 | **nozomi** of nozomi+helius-swqos+bolt+falcon | – | – | [buy](https://solscan.io/tx/oW3zTSb1uBe7qmM5tVNeCbHUquJNqciqqyo52e7jmt5TexHSce6CJiydvQNmDwnbYSDuWJCzdsY8xLZrzXqNwjX) [dump](https://solscan.io/tx/44XxK9qdG6VxwwpRtqzViL2HS1XbGADF36am68F47wVJWmnEb6fm6Mskc2kfXsqLAck2qj8Hcypc5ULqHP8WooS8) |
| 27 | 76 | +1 | 1 | **falcon** of falcon+helius-swqos+helius | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/2UMqzGg5yX5DNhfn1bXBSQ6QQX2BLAA7szMeDGzAi4ek4EDei8GTPiSp3zRymer6psTN5AHttFjk3UUVHN5X5WMj) [sell](https://solscan.io/tx/2ShAZDLic4ULvSk4c8emeCZiSkWAndKHXBMGfoCYAFt5tUHZ4S7mvqVFWyiitaLSEdgtz972d1CtUizGaZzUpA3o) [dump](https://solscan.io/tx/2dwosLHFgc6N2f5Gvv93RG76RmF3vyBYyLZ6yrLQcxgfoaJ5TPG4q6yGbzbsjbQxdd1y2AFUxfFboizALAWZYn5M) |
| 28 | 19 | same | 7 | **nozomi** of landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/zUYEZo9NtDWBY5znZYskS6qWrfEngzCrMoDLkjq3c4Z22PbAzpM9XyBmG4q8h9g6r16bwxzGcq5HWr4Pjv4ECH2) [dump](https://solscan.io/tx/4H9e9Dt8hn7zjj6pPDeTkH4JvTonipQFHYXULfawCGbFeRxtEkFgAsXsHug1ruzzbpCbkCJnN3S1owepgsTd2jio) |
| 29 | 43 | +1 | 4 | **nozomi** of landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/2t6MQeur3cvy2YAaEoHX9nGj1e8ZwH96Csn785Ju2UNNDpKWc9yDbKvgWsQcJSZwxuDsBmK2jrDYfiRsGUXdg79C) [dump](https://solscan.io/tx/4AFkN3ynPY9VFLJiLs6qjMYTynFZqJMfekeqTdejAiSKx5tWsJUsid4CMBr5oH5A85QG9hsoDM9nDwLwB3xC5ku6) |
| 30 | 36 | same | 6 | **bolt** of nozomi+helius-swqos+bolt+falcon+helius | – | – | [buy](https://solscan.io/tx/5UP2hWXmM1gCscy5SS8szgDdpTxUVYcbvRu3hmxbzfuyYoKdq9amyKSLFbLUmKMcmzM9TooGD6AtBeJXtqHCV4A2) [dump](https://solscan.io/tx/4nmEhUuSKdUDKzioLgjeK6qZNbSykrmv51DndFXm5bhEK8vdeF13WC9z2eCV153dLnJmaJzTLVEJ9vZ28idm3kp7) |
| 31 | 39 | +1 | 0 | **nozomi** of landx-fra3+nozomi+falcon | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/2NB7f4BNZkKHLzU9sL9AppzqbpfpofBwJaBCYLUnWp5RTfyYPmjTYxGviVTMA3Gqq9epqs6AgdeADQQxQRDvg8MR) [sell](https://solscan.io/tx/3p7JJ6g281vpygcJPFgwNWVDgn5igUHoSLcPa6G2piUEbyG23KwntmVPqaz1oBfvEpLTyzjtqThhWUHqBwzmnk5j) [dump](https://solscan.io/tx/4DVH3oyDJwapaTyJrP52YkhCizi7Zp2FvdvxkMPGkHWBNqRuKj6ZLp52cBnXz1U4P4GgFoG3kvou6FbtwAAhFWsH) |
| 32 | 23 | same | 1 | **nozomi** of landx-fra3+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/2Zzw3c4uycgCw6DP4D1WB3j9uJngFFAy1bPcgTYwYpLPeD8oNta58u94QgCbmCSpBkgJ1U44mR2uSLyY5TJbuXZm) [dump](https://solscan.io/tx/5FsuT21dH2MuA4Pi1Fq9BxmpfQVn8XFsShUf5PaSMrbDkSNNQcyNNXecXUsnTwYvVpLyYmr9NDotXaGY9ffFMbuv) |
| 33 | 85 | +1 | 1 | **falcon** of falcon+helius-swqos+helius | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/cy9m2TC8MvTYeBNc7CjmdQhoGva2zqbmtbYRWBhNcDE1tPUav9X2dntUdmJeBfzjFtu7viH9HCqgWPKiPns1r9U) [sell](https://solscan.io/tx/2qkczota4RUrA526vBYxhuSuFMeAa18eSQoTKLXZiNKfo8yHv7Jn7H2FFnGXVtiDuaa1r3ga9sfR1rFbhYG64HkW) [dump](https://solscan.io/tx/DhnG4JYjeFohvyavDkTJM14tSKcV37CgsbJq3Y59HQjB5W7KeYfbNFb1RNMCpWmQJSdhV3CJUguGrqsU9F65Ld1) |
| 34 | 50 | +1 | 0 | **nozomi** of nozomi+helius-swqos+bolt+falcon | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/5ckxotsgZk6LCmovBM6ydNakTUv22ys56WNVKzMhrjn4bJcR6RgQHXBptbZsUKMu4w969k1dW6ZbpHm8KtBTT9Kb) [sell](https://solscan.io/tx/fDERYJFL6LtMvXAGwLm42cJggzrhZjRPV6bUvBMkaxAMgeHnYtk9gMZ6PzkUu4s5YZkqsMB3xskMcYKrKmeLrBU) [dump](https://solscan.io/tx/4ZLhqti7GrRWibNLSG3TZv6MbdwqEjk62AWEpLL6kmc94fLBPyBgPu8CYSVoXFVeyztunhGq3XZS6kpEA1EoCvdy) |
| 35 | 47 | +1 | 1 | **falcon** of falcon+helius-swqos+helius | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/4iaeT3vZViBjBwHii9NQX8v5d6oWFX9F6Hfj9ALGXWPSskrmKMxkbCnu3g18EEHAvAcMHW2ysrPFQEx9yQqpM72c) [sell](https://solscan.io/tx/578GrAQ7Krrsd9fu52kN7c2m9RaYFSU3UZjRk3nJ9bQmqNYCvXz1yXctii92eivpCvk81gyhb8k8bMK7of9LJBFX) [dump](https://solscan.io/tx/4P9vBYME6HWHv29bhSW1iGP5CKfvtpvSj8Lkuyq7NmQqMvc3honkfLZFbBwh85EjvcwuQxAgcbY6PZhyk48GymVp) |
| 36 | 40 | +1 | 1 | **nozomi** of landx-fra3+nozomi+falcon | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/4HjDRdvAgk8anaKJAPuauJQGxvut1Buo7PEE95swdkHz8BBvJpzW7SyLzYde4csFpCLKZjZgMHcbt5DWgZ8FFCxV) [sell](https://solscan.io/tx/4iSGMdWXYzqAcauV39v3FGmtJbooPLCMLaSHzzBbAj3UXVc8zLYdcawj5PXDkrJ54CSMPK16ojh6CoLto3bKkFGQ) [dump](https://solscan.io/tx/36ysMeiKKNzjoNWh2JmayxjS3PC55v34f5szwdPcxyCcMVZsgV4cAwgj1DvehpgPWeQJn4EVk13PtvW3idJuY8i) |
| 37 | 78 | same | 0 | **helius-swqos+helius** of falcon+helius-swqos+helius | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2SQG6Jz8BddHgKGzSeLaz5zsEkriY6ALuMEYTq74WN6H9MgWnTiQ3G62yG76oGzLVbSmt7xriu6TstzQngLkq65Q) [sell](https://solscan.io/tx/5UUfEBuTWXdfVQ7V6xvgPe7DCQLVyhWgKABtrLEdzVxodcxVBgY8ku4LvAwduJT8XuAY6XLDAhRedmPrBXiMkxKa) [dump](https://solscan.io/tx/2Xt7PtzMBM8CYkgGVYzY1co5FmeBitXqvm41TGdRkw7FL39unHNZ1ZYxQ7QSKyWhqsi1KSTgstKGEShUrMSaNKP9) |
| 38 | 26 | same | 4 | **falcon** of landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/5HdBcHb32MrF2JneXMCTgs2Csz1BiNTuLZVSJRqqrm5aGGCyrH2iPzAD1XjzPbymxKuJkQgxsT8sk71HUFc1gDBU) [dump](https://solscan.io/tx/Sx2fo271gcz4D8bski1Cvawc2ttAMZeG992xuhxmriAX31CPaBQaZPZKMz1UTj7UCgB2tJwpCMtpi2UaLU8jsT2) |
| 39 | 43 | same | 0 | **nozomi** of landx-fra3+nozomi+falcon | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/3dJ9UqzA4HoeUXKdGwzvvgZ5j7maWsGUuyRH7KW8TH82E99EoGYJdhHHhKw5ZaFGrgBX62iKv1ijJiad6Mzmvp2G) [sell](https://solscan.io/tx/3Xs1RmGJAJiSSef86AtienTk8YTQw8nTMRWYREbr9Y7KTFc5EzwS2ELkn4gA76wCvFFsPcUWC4oAPn8WsoiHHHYX) [dump](https://solscan.io/tx/3cspY1oFDuSsudtAE4wS7nrKqTRNJSYSarHjQouuZSePozfHSQZzNyefjgDA6iLLeuwb6Ch6BsjoC9quX92N8VA2) |
| 40 | 59 | same | 9 | **nozomi** of landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/64xW2YDJW4FXT2gcVZc3VMyRpuLH6StqnbR4VgQF6feXevmH88xgrGq8otnPsFE3o23ySjLeWzcD3ShHkzMMk3eX) [dump](https://solscan.io/tx/5wVgRz4QDaArVfaBWmAefz3MoLUdYURXQXX4vG1iHr7q3oWH7LJwKhbUxpPkE3JpmYHAe2F9qLkJFwCPyMoH4Ptc) |
| 41 | 91 | same | 2 | **staked-rpc** of landx-fra3+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/2DUT4aGEfAjqbz3qF6TeZYViaQzRSTGn5HN6UR9EYzxKQLWd6e9149zGqv8iuDniWzMKy3qKoVqQuGsXkuYzUjGQ) [dump](https://solscan.io/tx/645Xg5GWTxPsjhmNj7HGJHrDNwnqW84A81xfKkULopFUoimqArmQPoRCkPPvvRizKhTwAfDRjbBZjefG4Ujx8mN7) |
| 42 | 34 | same | 0 | **nozomi** of nozomi+helius-swqos+bolt+falcon | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/pECATQSoZJUiTtxoedS4qd7Lhs1qgwGEqDhsbbnLBi8rfzhqzHjk7MG5oJTf1Qrs9P27PSAHEzPRzkpR96yfaHs) [sell](https://solscan.io/tx/2yVmNCVr9rRYVMoy2dPiCcsjmks5JwKdhftjrFagzfMYpc2Wry3W6LLLakjhpQXTXAnPsT7tug36fXJ4KN4rreP6) [dump](https://solscan.io/tx/5eRmQi5kKfCfWjGrAoSFXTe6pqKwspANcQcW6vDP7pSAPAygKpeRr6vyKabVaX4oXj4Mm8kivf5se6pc8no24Atv) |
| 43 | 40 | same | 2 | **helius-swqos+helius** of nozomi+helius-swqos+bolt+falcon+helius | – | – | [buy](https://solscan.io/tx/2ukeUveFS1wwg4QhLQEg9vrtyQh5Hz6tF68ukN3ZezfDG292aixfQ4Ccu2mCNfiruTw3QdGECKqSvocUs82CZMU6) [dump](https://solscan.io/tx/4EQuwzkLfXedJoPZB4akX4dgMcWf8ybgLeznR7fdoNVmTJ4Mk6heNVFoJJDRgKNztUbaYWH9i3kd4sU2iCrUBUzt) |
| 44 | 40 | +1 | 2 | **falcon** of landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/5r4c57AdFJLuUwmXEJ87CTXSjru3wQ1XhKyndifgDt22TsDDe2NmeuMQTJ9trfxk6kN6y3ehedBX8GTpJRV7ZNpL) [dump](https://solscan.io/tx/3QcZSJh3bpwrTxnJtsGuS1SX46bor8zW7Bp5Ux3m2PHQd3pjm36khyWJtJaHWaMRD3v7tgUCGse2LbupZvZvqAta) |
| 45 | 113 | same | 10 | **nozomi** of landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/5zZqgEukHXZZ9T4KoLdjM9r7XVDxDwMx439BDBDFzVtzgWH5w3cXUkCYBLXCmNPVc7eh3EGwwCx1d4MWarbSN5Ci) [dump](https://solscan.io/tx/3hpsYtZhjZqPBQq68ksui4pBv5PiFa1LKP3Hs9GbrxUWjFGFByUYAZt6jkVdqrJ5jrZ9c1KmBfDd7HdmraRNdLWP) |
| 46 | 71 | +1 | 8 | **landx-fra3** of landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/4svFimRtSkF2bAEpynTCT37MT9cCN29TUdUayPXcxHNXmQ6NJNwouU5L7TU8GXnoqEQughPLsM4CWewTSsxne4WD) [dump](https://solscan.io/tx/4sn2U1ikmATEN68mzg5NLjiY4HAwP5ExP2zcA1sNyhfrvnBXKxbqF6qgvDFYuSKN1rCgVBsQh3kQthXGrS3xbtEf) |
| 47 | 23 | same | 0 | **helius-swqos+helius** of falcon+helius-swqos+helius | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/4NFFJEeFviirc3rs1gJjJF99kXg2H3fbxuCRzuUioh9UjqXaZrwADCkhBNEbFvzfYZ7VkwJvb5JRujw3h2as6c6m) [sell](https://solscan.io/tx/63ZGHWPbXdpMiH4csNxTcpuMKdeaN4SBrmB4ZuKZkJiBZtVCkv1GsHsFTtaVgcaBU1U4wfSGuwrkCA1Qb9nMm2CZ) [dump](https://solscan.io/tx/2rq6thMVeNwSCCZwRBhDx7N26C47md6P6YRYJKceExnJm1psFa8Ju43cdpvCdG6htaMnd1PAhKGXDFmYdrWzNNpo) |
| 48 | 19 | same | 0 | **nozomi** of landx-fra3+nozomi+falcon | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/WLB2X6vAfqHQohvuBxDeNwWwcSpgpvofar3gLmbuCWvgifRXqXVeB3p6VZ1fBGu7TXqF4uiWmcgmS3vASs2KSow) [sell](https://solscan.io/tx/5ebX8v8PHkUZGtkWpy6FJMo7hnZ1eGGozqY2LBnrdfQZewRG6TDdEabevMwdQRRQzWgnPw8si6tGuUddTVaAcFsG) [dump](https://solscan.io/tx/4AfYwm8kJDke9qVL5YXNqBVNgrYMfmWwKfLKYj7kt1zP3QvfqcuJEU8PRd9ZydzbyssEuqCH25Xgn4GMR6rtovwN) |
| 49 | 38 | +1 | 2 | **landx-fra3** of landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/t1VA6r8UUPNKmrkdmDi21qnRNE231GEnNSfjjGtAnCFruHMMe2W27EyzfkC8uRv48pGLNP1VrBF1WegeojbBZaT) [dump](https://solscan.io/tx/2hiSz2vWP7SmELZqT9GTmpUwCZb1kioHgKbkjt5AHJMvvzHxMxTSgH4qpav5whjLARZaPpGye352NH5HgSQXqFej) |
| 50 | 26 | same | 1 | **nozomi** of nozomi+helius-swqos+bolt+falcon | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/2i4hJvGPcRGCnLjb3pJeVjjyq4syRE8wMApxHj4HfHTPkVHAUSfouZnPRENj6KPegYyGCgiXzNoe29jyC2nabKZ3) [sell](https://solscan.io/tx/4GedH5KByxKijZk9DxQayKCTfeNR9zJPCDWAC2E6fiQ2f8TUut5hwL7tEi3fvmVHQQgQ1UKteP3Q2e4wSmB93RAB) [dump](https://solscan.io/tx/tHmxzHPfp7U2zRsVqGyBsSBXBc9y9JjRQpcQeStguVkK5pgpc3qKNictC4X8PqHuXhZjqnXBhtu8goAW8tunJFE) |
| 51 | 138 | +1 | 2 | **landx-fra3** of landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/5rbGGYNMZeTEmtg68B6nspLSWBYTsr1XBmENJ9EvqW8Ep5PEXjU7RazwS4vF2dAbdfyLHSFxGdfoQceDLDLYX9NY) [dump](https://solscan.io/tx/5RwznUbCeg9rPVvMmxAUeG1Ut1o8vnqFxQJAfo25cWRSmTT6fE5Thh2zjfcF6nJYrhJM1fYS29qMTKwYMTeKDmKX) |
| 52 | 36 | +1 | 1 | **nozomi** of landx-fra3+nozomi+falcon | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/2cf1tNkDVqwt66Vkonu18oVwJrSqjAhu5X2L9Uvk8LymmJzC7y7JqGgcrJY2KtuZ4TJUgzRDnmy7R4ehPEmWJS2N) [sell](https://solscan.io/tx/L3Q1aaTmBxCZjFzoN7ipc56QhLdhUB72uYsBBbEhiuFA5TfjkQ4Z7DSeW5JFJxZGrfaxQrTcxJJkN3aqhiSVbCq) [dump](https://solscan.io/tx/YMPXa39LyemzEk1kpU5mtNBDpsdovyg2ssWFSrP8NwZJ86tTwvj1f9ixe6cMoEkoPQXCu6hkCfebuFnTohkh2R5) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Harmonic | 21 | 7 | 33% | +0.0799 | +0.0124 | 6/7 |
| BAM | 14 | 5 | 36% | -0.0623 | -0.0116 | 1/5 |
| Jito | 13 | 6 | 46% | +0.1390 | +0.0237 | 3/6 |
| Firedancer | 4 | 1 | 25% | -0.0083 | -0.0068 | 0/1 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 34 | 14 | 41% | +0.0110 | +0.0015 | 5/14 |
| dev list | 18 | 5 | 28% | +0.1372 | +0.0288 | 5/5 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 31 | 10 | 32% | +0.0224 | +0.0033 | 5/10 |
| next block | 21 | 9 | 43% | +0.1258 | +0.0147 | 5/9 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 21:00 | 2 | 0 | 0% | -0.0010 | – | 0/0 |
| 22:00 | 13 | 5 | 38% | +0.0653 | +0.0139 | 4/5 |
| 23:00 | 32 | 11 | 34% | +0.0779 | +0.0080 | 4/11 |
| 00:00 | 5 | 3 | 60% | +0.0060 | +0.0023 | 2/3 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 19 | +0.1649 | +0.0087 | 1.5 s |

## 8. P&L leaders
**Best trades:** FWLmXr +0.0756 (Jito, time-limit, score -0.66); CxN2eE +0.0644 (Jito, time-limit, score 0.65); J8GeV6 +0.0423 (Jito, time-limit, score -2.33)

**Worst trades:** 4Ki2Sh -0.0646 (BAM, time-limit, score -0.60); 6njaM9 -0.0269 (Jito, time-limit, score -0.17); 3nfvPk -0.0233 (Harmonic, time-limit, score -0.82)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `E1r4Psq8` | JitoLabs | 2 | 1 | +0.0750 |
| `HEL1USMZ` | JitoLabs | 4 | 2 | +0.0625 |
| `A9mvukTd` | JitoLabs | 1 | 1 | +0.0423 |
| `pSo1KZXg` | HarmonicFiredancer | 2 | 1 | +0.0301 |
| `CfgRXmp1` | AgaveBam | 3 | 1 | +0.0297 |
| `Fd7btgyS` | HarmonicAgave | 4 | 2 | +0.0180 |
| `DcTPJqPN` | HarmonicAgave | 2 | 1 | +0.0164 |
| `9W3QTgBh` | HarmonicAgave | 1 | 1 | +0.0135 |
| `Awes4Tr6` | HarmonicFiredancer | 3 | 2 | +0.0065 |
| `G2TBEh2a` | AgaveBam | 1 | 0 | -0.0005 |
| `vu1sGn2f` | JitoLabs | 1 | 0 | -0.0005 |
| `JUPiTERr` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| … |  |  |  |  |
| `shftkxns` | HarmonicAgave | 1 | 0 | -0.0005 |
| `SFundNVp` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `7y5VhV4f` | AgaveBam | 2 | 0 | -0.0010 |
| `C8Bey3LK` | JitoLabs | 2 | 0 | -0.0010 |
| `CQdLgwkm` | HarmonicFiredancer | 2 | 0 | -0.0010 |
| `5ZqveVff` | HarmonicAgave | 2 | 0 | -0.0010 |
| `EvnRmnMr` | Firedancer | 4 | 1 | -0.0083 |
| `Va1idLRt` | AgaveBam | 1 | 1 | -0.0120 |
| `privaEdS` | JitoLabs | 2 | 1 | -0.0125 |
| `9jxgosAf` | FireBAM | 4 | 2 | -0.0130 |
| `EUcJwf7j` | JitoLabs | 1 | 1 | -0.0269 |
| `Av8EnYrP` | AgaveBam | 1 | 1 | -0.0646 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1507 (p25 1271, p75 2013, n 52) |
| Executed-feed lag behind first sighting, ms | 1.4 (p25 0.9, p75 3.4, n 52) |
| Buy sent → our tx seen on the feed, ms | 36.2 (p25 27.9, p75 60.4, n 52) |
| Fills: our buy seen on the feed after the dump, ms | 37 (p25 23, p75 47, n 19) |
| Guard fails: our failed buy seen after the dump, ms | 44 (p25 36, p75 88, n 33) |
| Fills in the dump's own block | 10 of 19 |
| Guard fails in the dump's own block | 21 of 33 |

**Which copy landed (nonce fan-out):** nozomi 19, falcon 16, landx-fra3 7, helius-swqos+helius 5, bolt 2, helius-swqos 2, staked-rpc 1

**Send-path answers (FAST-ACK lines):** falcon 50 (median ack 0.3 ms, 1×429), nozomi 40 (median ack 0.9 ms), helius-swqos 29 (median ack 0.5 ms), bolt 17 (median ack 0.4 ms), helius 15 (median ack 0.5 ms), staked-rpc 4 (median ack 5.5 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 2.83 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 8yYMhuYo | 11 | 9 |
| 8PgC4ngp | 9 | 5 |
| 2KtcBC (pre-placed) | 7 | 6 |
| DF7eRXHn | 7 | 5 |
| haqq (dip bot) | 6 | 5 |
| 3MHgGwdL | 5 | 5 |
| GEMPyqU1 | 5 | 4 |
| 5PuQCemC | 5 | 5 |
| 6VzXcLk9* | 4 | 4 |
| HLU8QbLd (41Pr family) | 4 | 4 |
| E2x1ewwX* | 4 | 4 |
| EgxfYgEb | 4 | 4 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.3969 |
| Pump fee on buys | 0.0821 (0.0043 per fill) |
| Pump fee on sells (residual) | 0.0871 (0.0046 per fill) |
| Buy tx fees (base + priority) | 0.0096 (0.00050 per fill) |
| Buy tips | 0.0190 (0.0010 per fill) |
| Sell tx fees | 0.0115 (0.00060 per fill) |
| Sell tips | 0.0228 (0.0012 per fill) |
| Failed buys (tx fees) | 0.0167 (33 buys) |
| **Result** | **+0.1482** |

Buy compute used (fills): median 76,905 CU, max 87,404 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 19 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-primary getLatestBlockhash: 1 timeouts/transport errors (worst p99 261 ms)
- ℹ️ send path falcon: 1 × HTTP 429 (rate limited) on buys
- ⚠️ big loss 4Ki2Sh -0.0646 (time-limit, BAM)
- ℹ️ Two reactive buys failed on the +5% guard right after Amsterdam's pre-send bought the same dump (AsDx1ENs, 5qzhbf4S): self-competition between servers.

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Recommended / open:**

- Run 21: dip18 + routes v11 (Falcon UDP) + live pre-send on Frankfurt.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r20.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r20.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

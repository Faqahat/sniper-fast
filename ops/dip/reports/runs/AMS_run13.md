# Amsterdam run 13 — dip bot run report

*M2 detector SHADOW (dip11) beside IMIT1 trading; 0.35 SOL, 1.3 s / SL −10%*

> **Verdict:** −0.014 SOL on 17 fills. Same M2 shadow grading as Frankfurt run 14.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.0141 SOL** (wallet 1.2983 → 1.2842, Δ -0.0141) |
| Started (PKT) | 2026-10-25 01:42:03 |
| Ended (PKT) | 2026-10-25 06:08:31 — stopped with Ctrl+C (SIGINT) |
| Ran for | 4 h 26 min of 540 min planned |
| First / last buy (PKT) | 01:45:32 / 05:44:16 |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 31 → **17 filled**, 14 failed on the +5% guard |
| Fill rate | 55% |
| Wins / losses (fills) | 9 / 8 (win rate 53%) |
| Per filled buy | avg +0.0004, median +0.0004 SOL |
| Fills only / failed buys only | +0.0069 / -0.0211 SOL |
| Best / worst trade | 9XLLD5 +0.1364 / BY8wNe -0.1141 |
| Fill landing | median 43 ms after the dump (seen on our feed); 14 of 17 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip11 (M2 shadow) |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.55 SOL |
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
| near-leader gate | 120 leaders (buys only when the dump's leader is on the near list) |
| pre-send | off |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 540 min, loss cap 0.298 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 12**:

| Setting | AMS run 12 | AMS run 13 |
|---|---|---|
| engine build | dip10 | dip11 (M2 shadow) |
| limits | max 60 fills, 1 open at a time, 480 min, loss cap 0.276 SOL | max 60 fills, 1 open at a time, 540 min, loss cap 0.298 SOL |

## 4. Timeline (PKT)
- **01:42:03** engine start #1 (session with 31 buys)
- **04:10:01** big loss: BY8wNe -0.1141 SOL (stop-loss)
- **04:13:49** big loss: DJasC1 -0.0523 SOL (stop-loss)
- **05:09:52** big win: 9XLLD5 +0.1364 SOL (time-limit)
- **06:08:31** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 18350 |
| Inside the envelope (age / drop / since-buy / size) | 8370 |
| Picks (score above the threshold) | 178 |
| Skipped | far_leader 135, spacing 11, no_launch_accounts 1 |
| Buys sent | 31 |
| Filled | 17 |
| Failed on the +5% guard | 14 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 17 of 17 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 01:45:32 | [3zw6oJ](https://gmgn.ai/sol/token/3zw6oJprhRt32YAnUwtZsf7LBMTptzcdD4Px2HsRpump) | 0.35 | 0.21 | 5.74 / −23% | 4.0 s | BAM `LA1NEz` | guard fail | -0.0015 |
| 2 | 01:58:32 | [7VseVe](https://gmgn.ai/sol/token/7VseVe1RShHWKvZRpskdHC7x3ZdUcBBwkMBxRLKcpump) | 0.35 | 0.46 | 8.63 / −30% | 2.1 s | Jito `FLwV8t` | guard fail | -0.0015 |
| 3 | 02:16:32 | [D9B1MJ](https://gmgn.ai/sol/token/D9B1MJSoFQKtLyQBjiA99RKaGsGWAtxYgffMXHhisooT) | 0.55 dev | 0.54 | 4.15 / −13% | 235.1 s | Jito `AEHqTB` | guard fail | -0.0015 |
| 4 | 02:30:34 | [2L3z93](https://gmgn.ai/sol/token/2L3z93gByhSs8ecv9pxE9Viih4MdMFqTSBGY6qCcpump) | 0.35 | 0.33 | 2.32 / −11% | 1.5 s | BAM `AWcCdY` | guard fail | -0.0015 |
| 5 | 02:32:06 | [9ERTTs](https://gmgn.ai/sol/token/9ERTTs9zAGivUHFCmZWBCL9xsVhX3GXfmtC1ZkcEpump) | 0.35 | 0.41 | 8.27 / −38% | 3.4 s | Harmonic `Ex1AxF` | filled | **+0.0004** |
| 6 | 02:32:18 | [D13fKW](https://gmgn.ai/sol/token/D13fKWbgYCX54kRwAWYdwtdfS1u3zeuXKVWR3Fn3pump) | 0.35 | 0.39 | 1.43 / −8% | 2.3 s | BAM `PUmpKi` | filled | **-0.0258** |
| 7 | 02:32:23 | [EsF6HT](https://gmgn.ai/sol/token/EsF6HToBLfcazJfTvRLHhKL7XtpM9e1paCJQDYWHpump) | 0.35 | 0.57 | 7.90 / −37% | 4.7 s | Jito `5pPRHn` | filled | **+0.0126** |
| 8 | 02:33:53 | [8t2i4S](https://gmgn.ai/sol/token/8t2i4S8RzHffa5HbwJdPAGCx7d4Ep2Ch96VMeimApump) | 0.35 | 0.36 | 7.94 / −37% | 1.9 s | Harmonic `GoeW4a` | guard fail | -0.0015 |
| 9 | 02:35:20 | [CAp2hi](https://gmgn.ai/sol/token/CAp2hi9R5Zm35mdQPesr2cPMNaCE5yVcXcZjrvXkpump) | 0.35 | 0.26 | 1.49 / −8% | 1.1 s | BAM `Aw5wEM` | filled | **+0.0328** |
| 10 | 02:39:11 | [GJuS1Y](https://gmgn.ai/sol/token/GJuS1Y5oE54ipfbyPeFmAxPismK6kfFpeujVUJTnpump) | 0.35 | 0.44 | 2.10 / −11% | 3.2 s | BAM `ETcW7i` | filled | **-0.0032** |
| 11 | 02:47:05 | [8mEoNt](https://gmgn.ai/sol/token/8mEoNtfzTJBPd39kUJutatDDSnRPZjkzXVxVma3vuxGA) | 0.55 dev | 0.89 | 3.33 / −17% | 3.2 s | Jito `5pPRHn` | guard fail | -0.0015 |
| 12 | 03:13:42 | [GAb255](https://gmgn.ai/sol/token/GAb255M4uMFoETfwCJzMUb3HxMXBKYwGQhw6v37Epump) | 0.35 | 0.25 | 3.90 / −22% | 8.5 s | Jito `5pPRHn` | guard fail | -0.0015 |
| 13 | 03:20:06 | [CL6z8N](https://gmgn.ai/sol/token/CL6z8Nvxq4ABCjV8kyNwoW1QLvXw4JEpRdobTqikEy73) | 0.55 dev | 0.99 | 8.95 / −39% | 1.5 s | Harmonic `HTeRsa` | guard fail | -0.0015 |
| 14 | 03:20:10 | [8z1BJr](https://gmgn.ai/sol/token/8z1BJrUTZCw5FgKk4FPMYuSWkeaBcKaZZ6VcXooz1RRN) | 0.55 dev | 0.68 | 3.87 / −21% | 2.1 s | Harmonic `EkvdKh` | filled | **+0.0245** |
| 15 | 03:36:53 | [2xtw6U](https://gmgn.ai/sol/token/2xtw6UtLBPZtCni1snjp3VbH24rYwEqF5MgnbCGxpump) | 0.35 | 0.28 | 5.13 / −21% | 9.8 s | BAM `GSTamp` | filled | **-0.0415** |
| 16 | 03:46:11 | [6oDUwk](https://gmgn.ai/sol/token/6oDUwknaS8QT514ZiZQCeqDFBEbroq5ggiVHX41b7EGo) | 0.55 dev | 0.60 | 3.09 / −17% | 3.2 s | Harmonic `AMukCL` | filled | **-0.0097** |
| 17 | 03:48:29 | [3qm28y](https://gmgn.ai/sol/token/3qm28ysnFkXewKn6G96bfkZdHY2JgQzLhcjAoNf8pump) | 0.35 | 0.38 | 4.93 / −12% | 229.0 s | Harmonic `GoeW4a` | filled | **+0.0214** |
| 18 | 03:52:41 | [9TsqZX](https://gmgn.ai/sol/token/9TsqZXrzBE68RRJp46F4jAgrjJwQdVfsAetEXcwALwhU) | 0.55 dev | 1.13 | 4.59 / −24% | 2.3 s | BAM `6WgdYh` | guard fail | -0.0015 |
| 19 | 04:10:01 | [BY8wNe](https://gmgn.ai/sol/token/BY8wNeRWSdLMzuFe8TXFuiqcQrsmHd28djRqBjE1pTwa) | 0.55 dev | 0.79 | 5.63 / −21% | 12.3 s | BAM `Ninja1` | filled | **-0.1141** |
| 20 | 04:11:18 | [2d2epN](https://gmgn.ai/sol/token/2d2epNZPpnQYewABkezWuNJ789S9UHLgB1UNLG5F2AB2) | 0.55 dev | 0.48 | 11.65 / −44% | 1.9 s | BAM `CoG8d9` | guard fail | -0.0015 |
| 21 | 04:11:28 | [21Hfvr](https://gmgn.ai/sol/token/21Hfvro6Zn4nTPpWgbwm2QTqPywP3VkxJFnk5brpizKT) | 0.55 dev | 0.94 | 8.35 / −38% | 2.1 s | BAM `722RdW` | guard fail | -0.0015 |
| 22 | 04:13:40 | [3F1AVD](https://gmgn.ai/sol/token/3F1AVDMBh9NCiP8YVaCUeajW9ZxxNKw5MmJJEXyZMvjj) | 0.55 dev | 0.33 | 4.11 / −18% | 1.3 s | Jito `GnC339` | guard fail | -0.0015 |
| 23 | 04:13:49 | [DJasC1](https://gmgn.ai/sol/token/DJasC1KhzeHWa2ADisTTa72aovz7fm2ktr4EyA14pump) | 0.35 | 0.25 | 2.13 / −7% | 3.0 s | BAM `BUv44c` | filled | **-0.0523** |
| 24 | 04:34:15 | [GiybNi](https://gmgn.ai/sol/token/GiybNixW3gE8tvQvXUcLXnW7X4pAkKASkdnW9sCGpump) | 0.35 | 0.42 | 3.41 / −12% | 312.9 s | Jito `ACvL73` | filled | **-0.0236** |
| 25 | 05:07:17 | [8WAAk1](https://gmgn.ai/sol/token/8WAAk1M6s8khbFLjskKPzdXyerekqMBDcGtNYAcHpump) | 0.35 | 0.72 | 3.92 / −20% | 16.5 s | BAM `8augxY` | filled | **+0.0305** |
| 26 | 05:09:52 | [9XLLD5](https://gmgn.ai/sol/token/9XLLD56Xjr4RxvqvAikgN7UNMD7BU6cJ38JhM4su7cbm) | 0.55 dev | 0.58 | 4.82 / −22% | 5.3 s | Harmonic `GoeW4a` | filled | **+0.1364** |
| 27 | 05:15:34 | [8EBkFi](https://gmgn.ai/sol/token/8EBkFiMfLVR5Nb3cQvjqjbdTCn85JN9ZASXivyVDkfka) | 0.55 dev | 1.40 | 4.49 / −24% | 3.0 s | Jito `8o8wWC` | guard fail | -0.0015 |
| 28 | 05:32:34 | [DHzCgi](https://gmgn.ai/sol/token/DHzCgivLBrQaCK3vW3YSoiNsLSdPFFXJDLS3ESiZpump) | 0.35 | 0.31 | 1.99 / −10% | 1.7 s | Harmonic `Ex1AxF` | filled | **+0.0176** |
| 29 | 05:35:17 | [3xu825](https://gmgn.ai/sol/token/3xu8256ziU9nNxaDtPQPbYAJiD1cZP96VwzwGwWUpump) | 0.35 | 0.49 | 4.36 / −15% | 17.4 s | Rakurai `2dfgsi` | guard fail | -0.0015 |
| 30 | 05:42:07 | [6feP82](https://gmgn.ai/sol/token/6feP82zFBiFxCanu4uQ2M5orqGWxp7QsPgAAJHKBpump) | 0.35 | 0.30 | 5.22 / −27% | 8.5 s | BAM `Aw5wEM` | filled | **-0.0049** |
| 31 | 05:44:16 | [FrbS2P](https://gmgn.ai/sol/token/FrbS2PurNfpBdKGyDaiYJo6TmhDR2FEoGJwSXUBbpump) | 0.35 | 1.58 | 3.33 / −16% | 314.2 s | Jito `LeDbQ9` | filled | **+0.0059** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 25 | same | 4 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/2xfd34KpzNQLD3vbthXRNRGmxbegC7aXayWjzQqVsaLqMGt9bFRKNb2TK7Q1CpgiKGpxvnoHcE6qaCJmP8DtRpAm) [dump](https://solscan.io/tx/dozEu1mcf2dMJCkNfmj7mF4xNoBLB2a62fbydM8E2YSLKwTKy5BZT79bfD9aNLyaw6uTso9Zi2WnWZak9jF7B5m) |
| 2 | 143 | +1 | 5 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/2E1wRd84pkPD52pZGR57wSYB2LT5fr2iMfXvfRfDaKid8rJdDdDXvq7yuh7x23eChKLJKW4GzArYMofaxwHDMnHp) [dump](https://solscan.io/tx/2Yf6BLLdAvygmVqqn4gSAjRZB3HC33EQq7hqqhLE6GQmGGkut9WELswficMubc1wiRbmeJGqWuBUUX14c2kzqV7E) |
| 3 | 37 | same | 3 | **helius+helius-swqos** of jito-bundle+helius+nozomi+staked-rpc+helius-swqos+bolt | – | – | [buy](https://solscan.io/tx/2sw8phZP38USAUJsMyyEK1syZ9HA3jhtjDg8JHuKdT57i97uLutp7eDeav1dBrpK2wcwSDksJihHGgNW377o1XSB) [dump](https://solscan.io/tx/3JgQXBaufZZPT1b6xH8WD4bAX5fZDkVR4NKKRQr5UrF1tpEGaAZebvwcm4Q38TXEXDJNLfJYRkV6Fva29SGc9gVf) |
| 4 | 29 | same | 1 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/632EKGYFh4CmSFKLdjSQQVztpuL7YZXvF4ohSLmdegPCYFEjPLKQwUA21D5kDxNGWRugudxgZ5vytWSZnVrFyKSV) [dump](https://solscan.io/tx/4cvbb82dm2arHywwDNTzCJaW1PbeQUEKEEtDCX7FbWdfxAMCGpzP5W7HeXKGKxDudvXcLCTHZeUDMgBQDa7hoNsC) |
| 5 | 33 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/3pgLoZk6Az4mZm2ZJJ7zaMpMtcKiuUEjeFiyFHg1CF66dPR6nvu8Lt1vigHHz1K86Lt1wevhhMQQwoPEjwc7Mr23) [sell](https://solscan.io/tx/3ChmwiYcm36jaLzR2uBX5bdz6thxML8bvq7q85ah3ZsR6XynP4xjKXWuhQGfFgfSjT4pqAt8MxuSeVWgQH5BNB4D) [dump](https://solscan.io/tx/4Q9rQKkzsMjoy9g2UqvqoMbpPF463uMYvwsLwgmcgEADL5xf8j2JEJtaduaDx8DDSis9ZDGFkiJEV3o5RgWaPCT) |
| 6 | 22 | same | 0 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/5n7PBcof1eoqxpRVLUSKprcMZBp5epVGxeiNfthBPiV8KSXRxrnYbDcmBXwGnG6SVhEN2mMDSELWRhHQUscqvEgq) [sell](https://solscan.io/tx/5wET58P7PPifb8p5QQCPKFsgKdR52Z9ZaraULJMxUnFWCpCqk4EgNiTUdA9vW5cD46csgLGoZtMWnuDtYWBTftrx) [dump](https://solscan.io/tx/3TQtnZPAYxmo8hof68nLSB6ya6Zx1N7jGLYhj4R2dENXomKy1pthMZeYUrsnDuZ162iobpRLxhRMhrt1iRr1Nmin) |
| 7 | 46 | +1 | 0 | **jito-bundle** of jito-bundle+helius+nozomi+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/TL8DyHx6xiQZZCCCtYEnKQhT67NZGUQ24hjwz2hizRAhnMY8VzmCuxbYD6Q2jocq2yG6wak3VBf54qT8G6U3G7w) [sell](https://solscan.io/tx/4k4FjioexiQwvkS53cr5LsgymVJKi6PCsuM1oq7PLdsiZHcRVAVHF2w9C5Fc2cdrRgG47qWV389NpCu2Eer887B7) [dump](https://solscan.io/tx/Arvi6gwqtXpBLotTh2haE5vH5QnnsxP2FigGoqTbk3DY6d3dJQzNRrgGQMRQbCK21H8CmQgdgsDCjYMNPyRYH7Q) |
| 8 | 137 | same | 2 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/48eggFP4Ckc7E3MpnnEtbU8PqQLg1rPkznyzNX9wN4kWSGsmqpUmzM73qJkiCYQQKwNzUzcviZ3XKMgJ5vHu1aNb) [dump](https://solscan.io/tx/2618fT9tMSV5duz4eeerRFCauC2avHAUrq7sVZ7BsA8S1zfgRxE7m9ZPBdQzxR6JQNSjKdvVLXZVrW2WeVbfmoCE) |
| 9 | 42 | same | 2 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/54TkjSCx94W7ew1Hh372W7apuxMtHLrqGS23YCtaMaWUT28swKVvmnzfNDzcCAMec93xiVD2CnkExPUwgDPrfTPZ) [sell](https://solscan.io/tx/3rL3q35DNs4FE4GUF9XakmTL8chyH7CvbdB3TBbJQfnChhDhE28uPf8XbQvgmwo7GtUDSyHw95KonJgmxKdZZAhu) [dump](https://solscan.io/tx/2kvWHiF9mNUXbZ6RDiVKStubVxYdHsFosuDTG5eSWEkS4T62pBPnFzb777ESaMXFyRUxPsgGHqUVb8Lzs98Fodeh) |
| 10 | 29 | same | 0 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/3oVaL7xYBZnqcA8kY57tg6CEogzF7U3XftWoy3k33K152yjAvQ36TPvNUL9JzrH2YrwahNjM3K9k6Er5fT2ick9B) [sell](https://solscan.io/tx/2uebcXh4vpCXLYWYpBAoYu4T6ptb7SWNcjs7vGrXwr5Wy1uGe15eHdt4pE49wwbRX4nWMq2z6VUNDcK9htC95NQY) [dump](https://solscan.io/tx/3w7kLnHpBx1Qp2qFdtrhvxqmKp7iY3KV8tRWwb4xtDjKEcb3Kvd9j31bG8eipMLQ7ET3ZhtPXpWKHoAcbdVFpciW) |
| 11 | 124 | +1 | 3 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/4rREXqijeuv2G9kP67ePQ1FehdRdk71Qb3W5DwQPyqFz4R3J2SAQMUjjnSxxao8Qsw8C1GjhDKL8TDKVWXXkGAE7) [dump](https://solscan.io/tx/4eQnMWL9KUikPwq3AnQ31f1vBwhFHZqda4mBxPytRcdHZ2P1nZindKF1Dw8P8j9m76Nx1aJV6twhcmj31LztBrXr) |
| 12 | 124 | +1 | 1 | **helius** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/2tVhEEoGrv8Ky8TAibdjMKHyN6Y9JFxGUG2wbccyF91YMzx8X9dK59oR6iVXNM4m5S5JUiVrkA8LmdmZCAUqYxbd) [dump](https://solscan.io/tx/4P9wNB5hGz5e94XZjZbskaBStmyuhFCZf9orWt1e3cTFwhwA2g9vGNcfcVKDPyaSCntQMcMWzFAsPqcMYNttjuZU) |
| 13 | 34 | same | 1 | **staked-rpc** of landx-fra3+nozomi+helius-swqos+staked-rpc | – | – | [buy](https://solscan.io/tx/5STXsaTvDRtVLLAnzXppaTgpfW7ofoD2PoEj8YWEdiYbkgTnmiwopEbxanWHrkHUok8RUBKkYgKtJjhrN7vtSThT) [dump](https://solscan.io/tx/2ibpvSNPK3Sk2xkY8492ScRnocvaRVVSjSNEmjfbHwUYThaFTW87H9rQ15Cm1do15uusRAjHTtHNGcJ3uS3m9F7s) |
| 14 | 140 | +1 | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/2gkR6sdV5bF9fU8c9uvAweNgge6nBNXSNoRBV62diU9qkairJRv8dchpJekTYz7YhHV2XDMescSo1pRLMCV6xjz8) [sell](https://solscan.io/tx/5rVTBYKHSrMxKafzDxJGA5bbmy3MeR7JeGSHVMZz6N1i1ba4ki7x7U36MezhADAfQc6bq22ULyY7ovM1sz7vLT1P) [dump](https://solscan.io/tx/FwWgpwBW9pCmWbHLhqstMrGuzofZFKu2MjwhARgYNsBH1dMxEu3VHXU8PvwisKtGTVK1rwsZ87fAfqiyaSyjCss) |
| 15 | 128 | +1 | 0 | **bolt** of nozomi+helius-swqos+bolt+staked-rpc | stop-loss 0.6 s | 1 | [buy](https://solscan.io/tx/59Qs93sGMxjMGq2kXhvBS9g6DbDtNoUQMXygXpuwZCiaP9HemhdvMfHyQroWfi4LG4vHVfiGFFNQu3ankiUHojBH) [sell](https://solscan.io/tx/y8UaKo55gKTHo2bdT1VLogAdoTrcyKmeULuWKaACKjGc9X1dPHASDWtwsbNZfnTS8oqjJTtN5Lk3Bc3zcQjsP4z) [dump](https://solscan.io/tx/5jJiRRPvU6J12pJ1evRZaQLYei1PiAGupQLMgARJpqGpYP471odZknUyF6szX1CvHVv9TQNdPC4qZwxnQ6PypdjY) |
| 16 | 69 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/4EukWa5sr3B8xe1XekBexs8E8ZLFjc6Jo5MxSEw6kUeX3D8rFhYb4vimJKebEwegpca6aTFqQ8WEWKDqUwmhpEHw) [sell](https://solscan.io/tx/2xD5Way1XNpE99mBzH3RxmoB4BLHNtWP6E7CrEYBjfRh8rvibMTEFaMo2Awzq6jPyWeN2QQ6Yh4guarnDkpVjwcD) [dump](https://solscan.io/tx/3NsaKQzKJ6PytrmTjzW9iWK32HfRsBYDAmg8hVPica8z9ZMxV1rKWQhkRTVYn6jZfTpDRLEbNKfvXgvbp5ccjoGD) |
| 17 | 36 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/2Rf575dkrkMWMxqconKMZQEQYmAL8Z1GY9PQaQpt6LT9gEbYdwff1ssdsgdqjsneR54kvoSH4XFYXNTFNcVksFft) [sell](https://solscan.io/tx/37PcidrTBLLWe11JjLFkEJXkAuwo347DJ6Z9nRfteYRjUhce1rCW52DjVNeevewCVQRngF2oaHakRVq1C7DbjDU9) [dump](https://solscan.io/tx/3ZQgcBnLdxwkyvxrwx47MRZxCtekaAXn3G9s7Bhtesb8WUyUgFEPALDKXXm6MzaqoLVX7zq9ZwpV7josnsCshtRe) |
| 18 | 19 | same | 2 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/5kyBiq3MAcXCQsdjZckPgQe1yeaoaz25a8QhvpPTWkeC33RMRzGSa6q3PPw7eCu6xyVhnWHy7h4eJeWFzwZvFYPm) [dump](https://solscan.io/tx/4pSyBj5LoaAH8nC6KMr85TACVdbHPqMfJ5FjD3NqLMraDg9AxZjykdLh5NwVsCGgGapFbPJUJ6CRat2Pc6ishpCh) |
| 19 | 21 | same | 1 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | stop-loss 1.2 s | 1 | [buy](https://solscan.io/tx/2fr9VnMCLMLzP513LeQqTtrcUtT9n5HLrFJBsBoqcNRQNV6KdHgUUg9AxbWvr9JCPzj9GrB2aU5grT2kArUehP8r) [sell](https://solscan.io/tx/5sDWyYRbMijU6goWGPwyqrKg9x4jPSUVTtnPrk41dT5Gdo5VsAtqtycYYuxeJBPNmvkDoG4xASvgUcqLev34aKYh) [dump](https://solscan.io/tx/iQHX2mLSpiTb5ZfQCbxsPHeh4oLSL2sn28Wx6o8V7kLn6xnu1zwHtYvwRtoJHvf7K5qQVKuE3nktC5BpzaTSG5Z) |
| 20 | 48 | same | 6 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/5PA1Nnmnq4WbBCnSFfic2iKZ9MrL6U5D695xjApaWkxzyC9VjfDFouia3FqJfuvdUZrDqNVjiro9CfBBj8mJuh5N) [dump](https://solscan.io/tx/m4aPiV39gHrDH5hck5sTWx63PnrZjaLY5sjetsb2QfjkwiNYTWYGkcACAUrVD9jYr2vnPVc8K6Xqb4UXyUmDoqk) |
| 21 | 25 | same | 2 | **staked-rpc** of nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/2jswqT1PVi6mXCxcWRYxVim58Bf9zAhXCDEcVywFbCeCNCP5fckqnhe8LcpRcLpNHixaD8G1ErNh1gsccvCoY8fP) [dump](https://solscan.io/tx/VoHDkx5ipENZAkZXK5fBNfZZ54a6hYGm9U4iX6rwUwuJQjgtXbkg4zuZ2tDoDFRGybayP1jaL5UxSSnX5DYsb15) |
| 22 | 117 | +1 | 2 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/UVq9u4BsWRSDU4SFrnv8eFQpnkjz3jgChbZBzK4khz4GJN3TLjH36naTDCc8aCmJh7FpGoXzWsoLaunBC6tCvDK) [dump](https://solscan.io/tx/4GhRgbu4vKJ4TntkvkdRNQZC2c1k7fXR7jUEhqJapBd1YVZWLJKf8MifMyV89DnqEVrBcEo4NKueg4ArwLoZzZmj) |
| 23 | 20 | same | 0 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | stop-loss 0.7 s | 1 | [buy](https://solscan.io/tx/3FC4kbZ1DHgCgheQoGYuekxQvyQxX73nDrpqFjjARckC2417yfMmNJBeCKxkuz9yTwa5uts46rSoiReWPtBPQqLA) [sell](https://solscan.io/tx/3NdAToXq4kC7UTPB1h3UBrjokqQmQgtTpyGArpAUFs8imuRDZAvDtUk8SG6TpCduuHXVrdPfR72Mdu3RXC7GAkKM) [dump](https://solscan.io/tx/4rTe4SkSEuzMVpUwg1xSjCzVyEiQTkodJ1dTw7qazsASXiYcurxkk26JzzsZZornqyhUKyEk7mPUZrTXaoYsdjuq) |
| 24 | 139 | same | 1 | **helius** of jito-bundle+helius+nozomi+staked-rpc | time-limit 2.1 s | 1 | [buy](https://solscan.io/tx/2rtfnfBCFpVVXv69uGutfZoQstvhHNZ2CoLd29gwnH4vSaN7CjNB2fEYRVUTeTV2dFJ66JhHirEWA4U5qkNYnEiK) [sell](https://solscan.io/tx/58qzKFx67yNys2N2nwmBmDiKSfF22EHBGM2HyNmW3X4uc9LUDjUqNE9KPdkXputJxu4S7z3D1CDQQaeHU8vm1LFA) [dump](https://solscan.io/tx/23vjuEfE2cyyu8yE6rQpoBJ48PZWPMNoiZq9nekiN59CNjGTXJpPHMGuTcHLosZdn3CKMXce48uCyfDJ6awj8bqe) |
| 25 | 38 | same | 1 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 2.1 s | 1 | [buy](https://solscan.io/tx/2gK1QNaP4p6925qE1uHXaKrdPgb3G7oT57esxh81WDCsbqchWrCM8FkW7jT7gYgZECvZq99bjFCetjEoXfpRRSnm) [sell](https://solscan.io/tx/4JpXLrL2B2muLZprEBWyqPhVT8nyJm6rxgysvbspnF5yJvHc68jqgSBkpYdKq8zqxxEqZWtGsqVifkaGabVjWFdy) [dump](https://solscan.io/tx/5JPrxSz2Xc5BziTB88aXk8wMz3dZJoa18YeH3yuXVGtPBMAkNZGQeZRLBYor1brAnPtRcwfGvPTZctTQSoNrx63S) |
| 26 | 105 | same | 5 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/n3BaoUjUntTg8w5dLxJVXAf4BS8RSABV1GCjdsGS1nCMr9B4jS6oEZSt1cJrW6CLTjhNxs4iywYSBg6Rwp8ehUx) [sell](https://solscan.io/tx/47KnMGJJzPkv9NoHYobzk2WwMmof8MgPUxUg5Cpd3rWHdGZtqbGAtvbqrz8dM5okCPkbc3TzAmUa41puJLF3mdga) [dump](https://solscan.io/tx/33uRUCXxXUxrKWG5tNc7ymdDzY9qRGW7vtVzWddrjgXRSjYC5pauNLYyTYpABjg9YxfV6Mgvx2cnGNSmnEEAp8Yy) |
| 27 | 71 | same | 5 | **nozomi** of jito-bundle+helius+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3nvMkdVvyqhxKeSf3jBzaijRSmQH5Xjq69gkC2AZmX3ZgJsQpZ3xhDhdiVww83f3uxtLEx3XUxZUHdeF8J4NAf6z) [dump](https://solscan.io/tx/2Xuq57ukVsjJpMzjEqSK1tuntpyaADfsBT6GBLkxu2ras2ikFuXkPPHM4E6wAEv4wrV5undK1vdgFYkCkTUy9PQR) |
| 28 | 72 | same | 1 | **nozomi** of landx-fra3+nozomi+helius-swqos+staked-rpc | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/4BFbdA8oYM379EsUQwcLiAXgpVMRMz6X43RK8aRAtrnkURikfURpJKXQqEgCamNDKqaVQW5ZBATgZZi7MTM9gFBw) [sell](https://solscan.io/tx/2ReDyTBVgHL1E9NdiLWWSTPDq6KoR6Ag5UgS4uSKV4NKAx4CXS752eNLVFiCNimjerqQ2jqRzUmJJUfZh9U4J7eK) [dump](https://solscan.io/tx/gUw9UypT9JVvBxJi2K2tf8rDdVTsmgAWpiQhsc3q98tnMGAw93yuHiBxmEGzyiMMmgV1a5dFbiLhPEkV1FSCwwf) |
| 29 | 62 | same | 5 | **nozomi** of landx-fra3+nozomi+helius-swqos+bolt+staked-rpc | – | – | [buy](https://solscan.io/tx/hfubuAfbR8ZYKGaZTwUdP51buofJBfJ5vCFpoWu9fuGVdVrH5bgUSbveQFpkPzh7HAxq9tFggQgqL42LAHD4J42) [dump](https://solscan.io/tx/5b3S8Jsy6u4gWkZ9vtkS6DXudMTFX9TPB5vYiakmY5PXxFaiansyL6Lw3bbzR5Gb2o1HK8AGg1hcKUGzzf4Q2JUB) |
| 30 | 43 | same | 0 | **nozomi** of nozomi+helius-swqos+bolt+staked-rpc | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/2mQAJ4vVoWtd3wtTLt9E5nk6g97K79H4oRxFWxBTLGAQJy9aKbM1oh3pb3hmFZ8TcfKBdNnQdNkdTS8oaU3hFH3k) [sell](https://solscan.io/tx/3rENAfvhcqiEwNK2VBXMRHGffb77iLMnF3VTuYr5CXSfjwBWPyj7p9XaLh4KSwN5TAVxvgTyeUjhPEUfW2R713MJ) [dump](https://solscan.io/tx/HirdVH7GPSkvbiYpij65GTTV5xmZinbc9Xs7Ss85C67cJhgPDsWbTJmCPPkc71oECyha7M2HuZccipAq4FdtQPV) |
| 31 | 53 | same | 1 | **helius+helius-swqos** of landx-fra3+jito-bundle+helius+nozomi+staked-rpc+helius-swqos | time-limit 1.9 s | 1 | [buy](https://solscan.io/tx/2MozW4jt7UQNw7JoRtVbNoH8Aarme8VrLjKFzBmgFitrRgDwoP24CBuj2v33AnFJ1bfJPsLpdX6A2XuwCu4Xe3yC) [sell](https://solscan.io/tx/4TK1K4XTCfz8nRtdEY469hYS3qzdaU2mSZ8Mj2gBTZswQeVog6oecQJN152kg4KapJzHgKHpNfQUeHRFNTGGYTdB) [dump](https://solscan.io/tx/DTJoRW3U31Uuxri6UVPgtHrTpgnQoGxuakS9pXxJw2VN7v1rTR3BG8NvXaJrk8cnobfCyDDKQgELZBGPoUs9Bpt) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| BAM | 13 | 8 | 62% | -0.1860 | -0.0223 | 2/8 |
| Jito | 9 | 3 | 33% | -0.0141 | -0.0017 | 2/3 |
| Harmonic | 8 | 6 | 75% | +0.1875 | +0.0318 | 5/6 |
| Rakurai | 1 | 0 | 0% | -0.0015 | – | 0/0 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 19 | 13 | 68% | -0.0391 | -0.0023 | 7/13 |
| dev list | 12 | 4 | 33% | +0.0250 | +0.0093 | 2/4 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 24 | 14 | 58% | -0.0037 | +0.0008 | 7/14 |
| next block | 7 | 3 | 43% | -0.0105 | -0.0015 | 2/3 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 01:00 | 2 | 0 | 0% | -0.0030 | – | 0/0 |
| 02:00 | 9 | 5 | 56% | +0.0108 | +0.0034 | 3/5 |
| 03:00 | 7 | 4 | 57% | -0.0098 | -0.0013 | 2/4 |
| 04:00 | 6 | 3 | 50% | -0.1945 | -0.0633 | 0/3 |
| 05:00 | 7 | 5 | 71% | +0.1824 | +0.0371 | 4/5 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 14 | +0.2148 | +0.0153 | 1.6 s |
| stop-loss | 3 | -0.2079 | -0.0693 | 0.7 s |

## 8. P&L leaders
**Best trades:** 9XLLD5 +0.1364 (Harmonic, time-limit, score 0.58); CAp2hi +0.0328 (BAM, time-limit, score 0.26); 8WAAk1 +0.0305 (BAM, time-limit, score 0.72)

**Worst trades:** BY8wNe -0.1141 (BAM, stop-loss, score 0.79); DJasC1 -0.0523 (BAM, stop-loss, score 0.25); 2xtw6U -0.0415 (BAM, stop-loss, score 0.28)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `GoeW4aFK` | HarmonicAgave | 3 | 2 | +0.1563 |
| `8augxYLU` | AgaveBam | 1 | 1 | +0.0305 |
| `Aw5wEMXh` | AgaveBam | 2 | 2 | +0.0279 |
| `EkvdKhUL` | HarmonicAgave | 1 | 1 | +0.0245 |
| `Ex1AxFCi` | HarmonicAgave | 2 | 2 | +0.0179 |
| `5pPRHnie` | JitoLabs | 3 | 1 | +0.0096 |
| `LeDbQ99Q` | JitoLabs | 1 | 1 | +0.0059 |
| `LA1NEzry` | AgaveBam | 1 | 0 | -0.0015 |
| `FLwV8tm3` | JitoLabs | 1 | 0 | -0.0015 |
| `AEHqTB2R` | JitoLabs | 1 | 0 | -0.0015 |
| `AWcCdYG7` | AgaveBam | 1 | 0 | -0.0015 |
| `HTeRsa3g` | HarmonicAgave | 1 | 0 | -0.0015 |
| … |  |  |  |  |
| `CoG8d9Fp` | AgaveBam | 1 | 0 | -0.0015 |
| `722RdWmH` | AgaveBam | 1 | 0 | -0.0015 |
| `GnC339vk` | JitoLabs | 1 | 0 | -0.0015 |
| `8o8wWCYN` | JitoLabs | 1 | 0 | -0.0015 |
| `2dfgsiSa` | Rakurai | 1 | 0 | -0.0015 |
| `ETcW7iuV` | AgaveBam | 1 | 1 | -0.0032 |
| `AMukCLCr` | HarmonicAgave | 1 | 1 | -0.0097 |
| `ACvL73V4` | JitoLabs | 1 | 1 | -0.0236 |
| `PUmpKiNn` | AgaveBam | 1 | 1 | -0.0258 |
| `GSTampk6` | AgaveBam | 1 | 1 | -0.0415 |
| `BUv44cVt` | AgaveBam | 1 | 1 | -0.0523 |
| `Ninja1sp` | AgaveBam | 1 | 1 | -0.1141 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1579 (p25 1272, p75 1873, n 31) |
| Executed-feed lag behind first sighting, ms | 0.9 (p25 0.4, p75 1.7, n 31) |
| Buy sent → our tx seen on the feed, ms | 43.1 (p25 31.0, p75 102.4, n 31) |
| Fills: our buy seen on the feed after the dump, ms | 43 (p25 33, p75 72, n 17) |
| Guard fails: our failed buy seen after the dump, ms | 55 (p25 29, p75 124, n 14) |
| Fills in the dump's own block | 14 of 17 |
| Guard fails in the dump's own block | 10 of 14 |

**Which copy landed (nonce fan-out):** nozomi 20, staked-rpc 5, helius+helius-swqos 2, helius 2, jito-bundle 1, bolt 1

**Send-path answers (FAST-ACK lines):** nozomi 31 (median ack 0.9 ms), staked-rpc 31 (median ack 2.7 ms), helius-swqos 24 (median ack 0.7 ms, 2 errors, 2×429), bolt 15 (median ack 0.9 ms, 1×429), jito-bundle 9 (median ack 0.8 ms), helius 9 (median ack 0.7 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 2 |
| Guard fails: rival SOL ahead (median) | 1.56 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 6n2cCJrr | 6 | 2 |
| 2KtcBC (pre-placed) | 4 | 4 |
| CVPz447t (pre-placed) | 3 | 2 |
| 3Kcgq69S | 2 | 2 |
| 8GPTNX4j | 2 | 1 |
| 5k2Ckkiu | 2 | 2 |
| 3MHgGwdL | 2 | 2 |
| 9k78QZyw (fast bot) | 2 | 2 |
| HLU8QbLd (41Pr family) | 2 | 2 |
| haqq (dip bot) | 2 | 2 |
| 7PedQZmc (untipped fast) | 1 | 1 |
| 6VzXcLk9* | 1 | 1 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.2466 |
| Pump fee on buys | 0.0833 (0.0049 per fill) |
| Pump fee on sells (residual) | 0.0874 (0.0051 per fill) |
| Buy tx fees (base + priority) | 0.0256 (0.00151 per fill) |
| Buy tips | 0.0170 (0.0010 per fill) |
| Sell tx fees | 0.0103 (0.00061 per fill) |
| Sell tips | 0.0160 (0.0009 per fill) |
| Failed buys (tx fees) | 0.0211 (14 buys) |
| **Result** | **-0.0141** |

Buy compute used (fills): median 78,065 CU, max 87,243 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 16 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getLatestBlockhash: 84 timeouts/transport errors (worst p99 1002 ms)
- ⚠️ RPC bh-fallback getSlot: 87 timeouts/transport errors (worst p99 1002 ms)
- ⚠️ RPC exit-fallback getSignatureStatuses: 2 timeouts/transport errors (worst p99 1001 ms)
- ⚠️ RPC ks-fallback getBalance: 1 timeouts/transport errors (worst p99 80 ms)
- ℹ️ send path bolt: 1 × HTTP 429 (rate limited) on buys
- ℹ️ send path helius-swqos: 2 × HTTP 429 (rate limited) on buys
- ℹ️ 27 send-path health events (self-heal), e.g. `SEND-PATH rpc bh-fallback UNHEALTHY: 3 timeouts / transport errors in a row (getLatestBlockhash): client REBUILT (fresh `
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)
- ⚠️ big loss BY8wNe -0.1141 (stop-loss, BAM)
- ⚠️ stop-loss slipped: BY8wNe stop at −10% but the curve loss was −18% (one big sell went through before ours)
- ⚠️ big loss DJasC1 -0.0523 (stop-loss, BAM)

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Recommended / open:**

- A/B run 14: IMIT1 without BAM leaders, M2 and pre-send in shadow.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r13.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r13.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

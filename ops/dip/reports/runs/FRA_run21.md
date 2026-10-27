# Frankfurt run 21 — dip bot run report

*Live: M2 gate + live pre-send (0.35 SOL, 4 tries/slot, helius-ps 20/s) + routes v11 (Falcon UDP next to Falcon HTTP) on dip18*

> **Verdict:** −0.119 SOL on the wallet (2.690 → 2.570). Pre-send: 49 fills, 21 wins, realized +0.020, failed-try fees 0.024 → −0.005. Reactive: 31 fired, 14 filled, −0.114. Before Amsterdam started pre-send (01:17 PKT) Frankfurt's pre-send was +0.142 on 15 fills; after, −0.123 on 34 fills while paper (alone) stayed positive (+0.14 at +10 ms) — both servers bought the same dumps (race: FRA landed first 13 of 20).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.1185 SOL** (wallet 2.6895 → 2.5697, Δ -0.1199) |
| Started (PKT) | 2026-10-26 00:26:59 |
| Ended (PKT) | 2026-10-26 02:01:15 — stopped with Ctrl+C (SIGINT) |
| Ran for | 1 h 34 min of 240 min planned |
| First / last buy (PKT) | 00:34:22 / 01:58:30 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 31 → **14 filled**, 17 failed on the +5% guard |
| Fill rate | 45% |
| Wins / losses (fills) | 5 / 9 (win rate 36%) |
| Per filled buy | avg -0.0075, median -0.0090 SOL |
| Fills only / failed buys only | -0.1051 / -0.0086 SOL |
| Reactive bot / pre-send live | -0.1137 / -0.0048 SOL (pre-send: 49 fills, realized +0.0195, failed-attempt fees -0.0244, 21 wins; see section 4b) |
| Best / worst trade | 47mAqN +0.0576 / 5zqq8j -0.0652 |
| Fill landing | median 48 ms after the dump (seen on our feed); 9 of 14 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip18 (dip17 + Falcon native UDP lane) |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.35 SOL |
| exit | take-profit off / stop-loss −50% / time limit 5 slots (~1.1 s) |
| price guard | +5% over the post-dump price (pump error 6042 if exceeded); slot deadline = dump slot + 1 |
| buy fee (priority) | 5M µL/CU × 100k CU limit = 0.0005 SOL per landed buy tx |
| sell fee | 5M µL/CU × 120k CU limit (0.0006 SOL per landed sell tx) |
| route: agave leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: bam leaders | nozomi + helius-swqos + bolt + falcon + falcon-udp |
| route: default leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: fd leaders | nozomi + landx-fra3 + staked-rpc |
| route: harmonic leaders | nozomi + falcon + falcon-udp + landx-fra3 |
| route: jito leaders | falcon + falcon-udp + helius-swqos + helius |
| route: other leaders | nozomi + helius-swqos + bolt + staked-rpc |
| sell path | staked-rpc (retry also via nozomi) |
| near-leader gate | 198 leaders (buys only when the dump's leader is on the near list) |
| pre-send | LIVE: whale >= 6%, 4 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 100 fills / 0.1000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 240 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 20**:

| Setting | FRA run 20 | FRA run 21 |
|---|---|---|
| engine build | dip16 | dip18 (dip17 + Falcon native UDP lane) |
| route: bam leaders | nozomi + helius-swqos + bolt + falcon | nozomi + helius-swqos + bolt + falcon + falcon-udp |
| route: harmonic leaders | nozomi + falcon + landx-fra3 | nozomi + falcon + falcon-udp + landx-fra3 |
| route: jito leaders | falcon + helius-swqos + helius | falcon + falcon-udp + helius-swqos + helius |
| pre-send | off (shadow only) | LIVE: whale >= 6%, 4 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 100 fills / 0.1000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |

- Engine dip16 → dip18: Falcon native UDP lane (16-byte key + raw tx, udp://fra.falcon.wtf:9000). Routes v10 → v11 (falcon-udp next to falcon HTTP; same signed tx, one tip).
- Pre-send LIVE moved to Frankfurt (probe 3 on Amsterdam passed): k 4, 20/s (Frankfurt's helius-ps cap).
- First try was refused: wrong keystore passphrase (typo); second start clean.

## 4. Timeline (PKT)
- **00:26:32** start refused: `Error: keystore: wrong passphrase or damaged file` (nothing sent)
- **00:26:59** engine start #1 (session with 31 buys)
- **00:43:52** big win: 47mAqN +0.0576 SOL (time-limit)
- **01:25:22** big loss: 5zqq8j -0.0652 SOL (time-limit)
- **01:33:28** big loss: 3LR5iA -0.0505 SOL (time-limit)
- **02:01:15** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 4b. Pre-send live (pre-placed buys) — separate from the reactive bot
Buys pre-sent after a big whale buy, before any dump. **Not included in sections 5–11**, which cover only the reactive dip bot. Realized = the engine's PRESEND LIVE REALIZED records (chain txs of each buy and sell; the buy pays the token-account rent). Rent back = that rent returned when the engine closed each pre-send account after the exit (dip19+; before dip19 the sell closed it and the refund sat inside realized). Failed tries = fees of tries that landed and failed (6042 price, deadline, …). Net = realized + rent back − failed tries.

| Session | Started | Size / fill cap / fee cap | Tries sent | Fills | Wins | Realized | Rent back | Failed tries | Net | Stopped |
|---|---|---|---|---|---|---|---|---|---|---|
| #1 | 10-26 00:26 | 0.35 / 100 / 0.10 | 5,150 | 49 | 21 | +0.0195 | +0.0000 | -0.0244 | **-0.0048** | run_stopping |

**Try results (as seen on our feed):** 6042 4,093, deadline 571, unseen 324, ata_exists 76, ok 49, buy_6005 19.

Tries never seen on our feed: 324. If they landed and failed they cost up to 0.0017 SOL in fees that are **not** in the failed-try total above (5,120 lamports each; inferred, the engine does not see them).

**By exit reason:**

| Exit | Fills | Wins | Realized SOL | Per fill | Median hold |
|---|---|---|---|---|---|
| time-limit | 35 | 9 | -0.3251 | -0.0093 | 0.9 s |
| take-profit | 12 | 12 | +0.5790 | +0.0483 | 0.6 s |
| stop-loss | 2 | 0 | -0.2343 | -0.1172 | 0.6 s |

**By leader type (the slot leader where the fill landed):**

| Leader type | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| BAM | 18 | 10 | +0.0401 | +0.0022 |
| Harmonic | 15 | 7 | +0.1428 | +0.0095 |
| Jito | 14 | 2 | -0.2314 | -0.0165 |
| Firedancer | 2 | 2 | +0.0680 | +0.0340 |

**By hour (PKT):**

| Hour | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| 10-26 00:00 | 10 | 5 | -0.0283 | -0.0028 |
| 10-26 01:00 | 38 | 15 | -0.0045 | -0.0001 |
| 10-26 02:00 | 1 | 1 | +0.0524 | +0.0524 |

**Best pre-send fills:** 9kZbVvYi +0.0669 (BAM, take-profit); D6frXV3a +0.0648 (BAM, take-profit); 7JBQnZBB +0.0590 (Jito, take-profit)

**Worst pre-send fills:** GoJWMxo3 -0.1291 (BAM, stop-loss); FnkjEdN2 -0.1053 (Jito, stop-loss); D23cEP16 -0.0693 (Jito, time-limit)

**End-of-run checks:**

- session #1: no END CHECK line in the log (engine before dip19)

**Every pre-send fill** (time = fill; whale = the trigger buy; P&L = realized, rent back not included):

| # | Time | Token | Whale % / SOL | Slots after whale | Leader | Exit | P&L SOL | Links |
|---|---|---|---|---|---|---|---|---|
| 1 | 00:28:46 | [GoJWMx](https://gmgn.ai/sol/token/GoJWMxo3naF6esqFqUdnq9NcjeWJU7m6xZJWHfZhpump) | 15.5% / 6.91 | +10 | BAM `DRpbCB` | stop-loss 0.6 s | **-0.1291** | [buy](https://solscan.io/tx/5NXbkmygYq1Ro7kQKHGRyaAHM3KTKF43AgXF6u1scA3dr5QUFYZmqwaDD4Tg7sggNcrEotc1Q42abyHWEXBVYSCu) [sell](https://solscan.io/tx/5Tf8imVtteCuJkxn9FBMtR7L1dxHhuAhkjc4tj7KyifcfMjPjYbUjtM9VQnkJDfKGYEnxPAbpwAYxgKmyAsz5r7L) [whale](https://solscan.io/tx/2r3SrKoV2kW2W2giUZf5cV86qUe9NVukswd3uPNaxxWeLYuPdVFeMVheoPdiGF5kP4b369J7XKbL6XotQG9bDrDe) |
| 2 | 00:35:42 | [HsfEQP](https://gmgn.ai/sol/token/HsfEQPRqwjsSvWLEH3yF9koM1JotfrwRC1rGipUopump) | 8.6% / 2.96 | +6 | Harmonic `2m1A2W` | time-limit 0.9 s | **-0.0218** | [buy](https://solscan.io/tx/63r3KSzFthkfTQfLxx8XSiUPT6XWPMoz1CBdoz8kyddhAEUZLXhRFeiLR1EXe9JExY66JEwLvXrwhjPrZvdmVQqE) [sell](https://solscan.io/tx/29AzDgFokCJvhXHaGScM5X1X23A33SdGUYQ9DFURatM9hi5comH9yGpCYYpfmvg1kRJaePSAz5CkXyKqAc67AbTm) [whale](https://solscan.io/tx/5Sk57zSiXXQH4xrmkHDGqUTuUJdAiD4Uq8Xwy4h2D1mLRk1niRQ7b1HE6pA8YZPkizxWYivBHXPs155AyZPviDHz) |
| 3 | 00:36:28 | [D6frXV](https://gmgn.ai/sol/token/D6frXV3a2D16QppTTFsxWS2M2o23b6tXzK6LBuFJpump) | 7.3% / 2.96 | +3 | BAM `722RdW` | take-profit 0.6 s | **+0.0648** | [buy](https://solscan.io/tx/Awj8Lqbe34XKyJZt2Yq5faxMYouySjiAWbDBvWys8ZD4NkXSBPP7682XpsDJMJoGuYdUUHaWyEMk9HZbL5iRuYh) [sell](https://solscan.io/tx/rKfSEdJJ6UNa1i5HoSNf66h9EFKHuAVdTmFpcTmPspxDMLscLhLHhk69wcEU4DdaepLNQS4zzkFBRvypuXBBFtB) [whale](https://solscan.io/tx/vMoWURu4VEDC22aWWs9Jyu8JYYFHFdywhvSvAGE3FuGYdrtAvNFLbkzdBXewhbThUro6PPNQCv3C9NGjnNeTPF5) |
| 4 | 00:44:35 | [BF9RqN](https://gmgn.ai/sol/token/BF9RqNTgJd1T7FT5QS2zDiA6TUKuiK3sjbvMDcQ2pump) | 10.5% / 3.46 | +7 | BAM `Fc6NNd` | time-limit 1.2 s | **+0.0468** | [buy](https://solscan.io/tx/29oRxB9BPPkobZvDtR9hjbSFFvyquRth3PAZ8kCEMkrEXk5qcyM35TX7hT4WLWot5Pg9ztpYJxfbrTeWxk9RUX99) [sell](https://solscan.io/tx/5kmuDjK3b9onUZW3tpCAnxiKdMBjHAwt8uVm8WAHPGmEQmrgj71NHrP5gFX7Ebs5JGFeDhUgMfbcSTjrjyU1GsHo) [whale](https://solscan.io/tx/4FW3ddsrbUHW9u2gqSCiNcM4PS5v45atYS2BbiaGtSxt71A1n81Lhm2C56HKrPonmipHX9dUJkf7MVhnGzY5zhYL) |
| 5 | 00:44:58 | [4RBSRh](https://gmgn.ai/sol/token/4RBSRhZFLjEKzk4S6h72rGUzqAJxH7SGYSkru5FKpump) | 7.7% / 2.96 | +4 | BAM `5Cchr1` | time-limit 1.4 s | **+0.0197** | [buy](https://solscan.io/tx/Ftg1knfzSqrqMy8iRmX7zYBdVHC9cxtzfppoNRpVNPRaxEoKMSSA6aMkvErcQWwqoA3PHcBrbgCULjk8goNgXiP) [sell](https://solscan.io/tx/2qkVaE3Djm9BYimnYzrV2a6FhtFr7ddwypRwqEEKz4dvss8wjEhpaAdX6W42Fo7ZAWYWRBN5DUJLEHYfEY8mVvyd) [whale](https://solscan.io/tx/5XgBKb8dpqDkrwyA3vf6kHtwRsqzjU1n87FbDBgmWWzUquKh8UqRhwvyrHmXhYbsWQa9AwvUZ16zRcCA43pH5a78) |
| 6 | 00:46:45 | [55c7oA](https://gmgn.ai/sol/token/55c7oAzdzkRqs9z7q4h5ugJFvezZdVeFyarRPUhCpump) | 6.2% / 2.96 | +6 | BAM `DRpbCB` | time-limit 0.9 s | **+0.0066** | [buy](https://solscan.io/tx/4T7XDDKgSeJ8udsL7FwZr1HuGqCS64fV8x21REc4xbK2EJftGVFKKhuvvw45av4UK7aMZYmd41R5Ck2Bwq4mqJCB) [sell](https://solscan.io/tx/3JcwWJdp1xNvs8GEMkbye5iZT5gjQnEvGtbAv1WRWuyeNB85geBozFGakAxdr46wSCZ4GgkYxM3A9fn1DnpZhhxE) [whale](https://solscan.io/tx/2ocBZZGaFpotGdHSmrk1sfHgFn7vAQyCjfZJv65Zky4ZvNSAW5gtvF61Wn36t4AqTpstvFS7QVNtGFC8Nx6fKRmd) |
| 7 | 00:54:41 | [9kZbVv](https://gmgn.ai/sol/token/9kZbVvYis2qTsyWHWeY6jwAxqXoyy1b56UCaXdtapump) | 15.9% / 5.93 | +3 | BAM `Fc6NNd` | take-profit 0.8 s | **+0.0669** | [buy](https://solscan.io/tx/3a9QiLXKdh85RDPJmzKeF54id1SfXQ4Vivbr7UyoUh6R8dBvoaQpRdWACdV1E6fuqupD3RisaYRhzSRAy8G12E9N) [sell](https://solscan.io/tx/42ueXn6GBPViEX81t3wfeZVmSm4AFD6sUrYYTFG1akCHLJbug8BLdQ5qGWzQyQut3MgmspW8FFr2dPAAJvPrLg9q) [whale](https://solscan.io/tx/2zMFQasV8qhNZxpxfoe5PGc4iGBfMbf6p7a27mYUgbSMaDwY4DxiXE2kJAdMcKAxDfVHBXxFH8vWbBkZTjMDtVsG) |
| 8 | 00:55:45 | [D23cEP](https://gmgn.ai/sol/token/D23cEP16gJ4FKagv1YDUQEmC5W1nCoJKWMpMAyRLpump) | 8.6% / 2.96 | +4 | Jito `6xWLi1` | time-limit 1.0 s | **-0.0693** | [buy](https://solscan.io/tx/54gFnvB8vEyCsEWoo8kdS97YHQ3CDXRZWT6qyXce6amDiWVKi8RkGEXZxmtTwPxXaGHkq5j7a2CkD4WXMBJWxx8s) [sell](https://solscan.io/tx/4dzu8YgX9p3kwnUQFhbFiqmFjA449dBobTnG69Q6PT5Hbba81YLrePhDeTXBphvBbWBvtdrtRPG227TStYxLxXe8) [whale](https://solscan.io/tx/2xpnap1VZyCmWAK3PKvQNTVmvbUycaMBjhNyTxAr3tmAMoGKwq3BhNeN7okj2oJgKuaq6dsbw2Ph7tMbFxBnAUzN) |
| 9 | 00:58:06 | [EcR4VR](https://gmgn.ai/sol/token/EcR4VRTFG37xeWrotkYWzJkb8dCgK1ZbWqmgnB9xpump) | 8.7% / 2.96 | +10 | Harmonic `Certus` | time-limit 1.2 s | **-0.0107** | [buy](https://solscan.io/tx/3xjCHDkVeajcPC9tu7rJxKzFWnN3BD5JWJ5HWk1rE8xS9rRp9p5rMTk3zCj189J6qkyRhVE1LjbVNpsnmSrZaD2F) [sell](https://solscan.io/tx/4F3XMKPL8CtvdNwkwFNeniU7bbS9g1PPSnZSk61SMrTyRgvQGe7cRFXPWFBF7nypM272cU2GK616GRhYxzZygrbJ) [whale](https://solscan.io/tx/5tMi6FhoAVqAAfdwtRKNsY89hWDLDF1QSw4ibzmbBSVaxHr5XcuR9gMsGMcUJWPfC6GzSAsFDTxVjNvTqeNzzopM) |
| 10 | 00:58:17 | [GXLSax](https://gmgn.ai/sol/token/GXLSaxCoWyEtG4XhLHcVXtuuFsPuPbT8EBfFHWg7pump) | 7.9% / 4.94 | +5 | Harmonic `5ZqveV` | time-limit 0.8 s | **-0.0023** | [buy](https://solscan.io/tx/RipVkFaU9iwZdNijNWJRkoTDwDss1qCqXp8Zgcqzu9AEc8eQvtg8SA3o5y4RH9i2YLber1jtzcMFyo5amkcZmi3) [sell](https://solscan.io/tx/3Cc6uByPGVf86Yp4P3DLmbfNpdBqE5WDfNB2Tsm1bZjApoH9BBU5pqkJdWGaHdnZcfT3Y6Y1QaYMFWDMDXLsPdY2) [whale](https://solscan.io/tx/5uVzzKzFDVZ3VJWmXhrv2jUaVVkD2coG4LG8ZnNqzg4g9Pwgkf7tyCSGxCbK2XUWtVWVKckn2H7A9upmhGNm77f1) |
| 11 | 01:01:20 | [8nTXUJ](https://gmgn.ai/sol/token/8nTXUJ3P1T495q44gZbUASfbXFKn9X5aGPe1RjUnpump) | 11.7% / 3.95 | +3 | Harmonic `A1vqhA` | take-profit 0.5 s | **+0.0547** | [buy](https://solscan.io/tx/2Ae9TC6LNxeb3DeTubGvo8tJy9AjMBsmFgq6d5AeTTgvX2YU5LSrYiUVJfP7nvLzrV81DF3KYwHnwZdbaCmFctSW) [sell](https://solscan.io/tx/3ksUsfPCX4BxLtN6169Bu5pubBGxF4D2713Czpu6ZRYNagtnd2UMSovBFj4fQ5g2LqHGXb2BqLk6Xc76xPxFqrG5) [whale](https://solscan.io/tx/3C7ZWrq9xMFzFfY69wXjJCPCA9kk3cGHhd9svLsTCUW4WdfFc43EvtfzxFFSCDX7jUkPtahm7tUxpkoZgir6XQQp) |
| 12 | 01:03:47 | [CddPvX](https://gmgn.ai/sol/token/CddPvXcmUgrG1AJhTsdEBYixNH7CvP6GPHbe9nDqpump) | 9.5% / 3.95 | +4 | Jito `DP9SwU` | take-profit 0.7 s | **+0.0415** | [buy](https://solscan.io/tx/PuLc3TYPUE1PPrvK9SdWiJKqo2wMTrPpiDWsmgRgZ4azEZ99JBSNT1P9NQXpqsrREyNfoKycfTnMCyuxinEbhBk) [sell](https://solscan.io/tx/3X3NR8q1unrSB5bHur54e2LrufG2MZs7VBrTKSepsEEAxzMFUs2ymEUiHwSHLfV3vhnFjnrEppFdZLFiL7nQSKJi) [whale](https://solscan.io/tx/2GNdYhDgVbkuQAaa2HFQcNcvoGCmyUKkB31QbugoWLxNgFGDuKyouwEzcU6UcC3SHnDS8TvpenzpqGRa2HPUjkGG) |
| 13 | 01:09:40 | [8HJ7zL](https://gmgn.ai/sol/token/8HJ7zLWKjjUw2kENvys7he3mjyThHbUvsJqw8vpdpump) | 14.0% / 4.94 | +3 | BAM `Fc6NNd` | take-profit 0.8 s | **+0.0463** | [buy](https://solscan.io/tx/3AfwRBTGoCJrUhgJ2nwZcW9EFXiWsgdWR2yoQztPovsz9CLMfzwoSVwpx7ivzC3jrSWFEVpRB3NNeqJpASDHwWw7) [sell](https://solscan.io/tx/5t6FYQDJYMRJ7xobrqJUs4wyKqkg25w9fPn31hGCximL3nisbVCiwGGXai5jUvmNmiVxKpV7R8EP9uxSVG82bSuy) [whale](https://solscan.io/tx/2dydatiYxCtdQ7GvUwg9XtoS3Fhr6bCep9M4xkiP6gzJhVwJUqcR45Wiy44NHMxnUQkwD17CJyvvP19ixRxhGAqg) |
| 14 | 01:10:34 | [3KFsBY](https://gmgn.ai/sol/token/3KFsBYD53YMjsRVs65p48qbfYjJBrEPnmpdRNozmpump) | 7.8% / 3.46 | +2 | Jito `A9mvuk` | time-limit 0.9 s | **-0.0059** | [buy](https://solscan.io/tx/2y5BnHgbUr8QW3p6P9nKeb7HL2teNmZsXmc3L35dSzwJTUFTuCj4KGmagRwNeDUY49it8u6toBEcdSfZcgiUuEsw) [sell](https://solscan.io/tx/63Wq5c8HqcV77wdefHVDf2AmNihFwY4C2Vpj3wUyRKv3zAY9vu8X2eLJJAp3yvZpvnt7XYpo4Y5ASGzhu9pB9EXc) [whale](https://solscan.io/tx/3Y36GodYznxkd9QkKA2Pkg9jUaUcaFtgJJa5hqzrj6vS2BFnESKkBjtFRJqzdVvRWK8WY9dUijWqEhjj9wCyVjuV) |
| 15 | 01:17:36 | [4qo4CZ](https://gmgn.ai/sol/token/4qo4CZCEmZokwsKYLKxPa5GZdkwDHT1A1Bri7qCopump) | 8.3% / 2.96 | +2 | Harmonic `GoeW4a` | take-profit 0.6 s | **+0.0341** | [buy](https://solscan.io/tx/3s427ZKo81WFU15u5VaFFPeafr3dZqnr47A9QUxD7V4KEDvJRkVPuj3x5n46F8pkpkFpn5MDMf36QyqpPZvdtShX) [sell](https://solscan.io/tx/3XgVhAzZAS4wYDL5RBpGwDRvdKx645GkxDEmnX6gcXCBcNnz1AJBmP8oSEuLx9UcXQ1GmruNTubPRGxAaDaZcree) [whale](https://solscan.io/tx/46AwzVCUtmppgF8PMU4MS4H7kmwLNFjznQ5nokLd95xKccyQ5PwU9LWupGhpfNsHwiSxLv9Eta7e6w5pCCLLkQ8q) |
| 16 | 01:21:35 | [EikmF6](https://gmgn.ai/sol/token/EikmF644QmzAFruSYox4sUNSbx4dxaSBgSKFBQPYpump) | 11.0% / 4.94 | +1 | BAM `R2D2im` | time-limit 0.9 s | **-0.0106** | [buy](https://solscan.io/tx/5CntCa12r3tW3J6xDcj9RVWJxYwZjoo23gVJqJo8B7vE2CZBRGcLbWJKbgToSjmPTyRgCRRm7ZihFf8gLxYvEkEF) [sell](https://solscan.io/tx/4EbyskBuUVcouxC9ZmMEU5ryKj8bAhSoNX88H8Vo8uxvje1phAJk8gNC1cbsjyPGtbPqZLBMKsPvo878mPfWh1Ct) [whale](https://solscan.io/tx/4KaNih4vMxesMGYcrhifchNchuNpqotXm8A6B5GJcjb3P3v4ihSkG9B7DURJpp1YcvxaqTe6h9hUeD6YiDDe2tdv) |
| 17 | 01:22:15 | [DEf5Aa](https://gmgn.ai/sol/token/DEf5Aa91iHqSV9aBHY9HFNRHT4esFHV6kHq3QGnUZhoF) | 9.1% / 6.78 | +2 | Firedancer `HW4zor` | take-profit 1.0 s | **+0.0294** | [buy](https://solscan.io/tx/5deLaSvRbkRqYxYuHH9YyZD9p2nafmc9FN8Yiuwiq1zTboP6Qn74U1eXKxmiJLU6EN959Ef8XyHFEmYCB6dJVvZa) [sell](https://solscan.io/tx/4tUN15fqRhvgp8nAw3KsTgGXnrrpCTb14kb47Mq82UspavLW8sVbQaxA1XZRw1zVeB9jVwPHiBpYbtt1X1h6eHje) [whale](https://solscan.io/tx/3fxTGTrDnMwXHmbuc9U47HRXTtux6HJzoFyS3HzFHSsGpjQpvUpSEdqBCKKXYoFN6BHcaSd5xejtYvoELx7tZhhf) |
| 18 | 01:22:56 | [13JHmd](https://gmgn.ai/sol/token/13JHmd7VDVLnMdebhfyFaaMnkdN4rg4UNZdvpWnypump) | 6.1% / 6.48 | +7 | Harmonic `Ex1AxF` | take-profit 0.6 s | **+0.0503** | [buy](https://solscan.io/tx/2G81Qx2kwSZrbRUEcdmwK5KLVgPhJASST72TzhoXcdFDW6di3hvo7M6bRFRYAYDTBNtohZiK9xpgKfjssBjU5XMy) [sell](https://solscan.io/tx/3H7paCtxDN45hg1rabW3FfRp7vAfzSeEpwD3tWUk6YqB5eJ3P36zpvBkC9tcTJJLDTVA59Qc1rU6eZbcGBqDD4kw) [whale](https://solscan.io/tx/65ucEN5nqchspQUYdiVV9k7js9jLGrqHcCo1hUwoj18394FQAGbHQ8Aw8MTDPDX42Vz1TpccvHwdV9ffkxSjGRfr) |
| 19 | 01:24:08 | [CZwpDR](https://gmgn.ai/sol/token/CZwpDRdKBEo8ESKbiBdQ4CKrJySQzZAMDBUzzjDspump) | 6.5% / 3.22 | +3 | BAM `gVALrR` | time-limit 1.0 s | **-0.0012** | [buy](https://solscan.io/tx/42YRcWu5XrhcxKEe9WiBiM3SuUwuRWPM8EHiJRiwogk3Uwx44dKLpg5jeJnZZUBD1znA1DSBqF5rLe32i9Uhmi3A) [sell](https://solscan.io/tx/3ti6Nzr7LQbgn7PvxyFom9fBgzmCvPSL1zMcKNxPBJpPDfMwKFNbGRQh7tcHfu5RfsnHVXBWmo7BNwjeeAbecEid) [whale](https://solscan.io/tx/5WkCs65q4N51GtBktsdQbgkxBrPJNcF8hmpYyL2WcbHny654n91TMD9nJMtb15TVGRNXiCQph6GSb8fz4XwGf1e7) |
| 20 | 01:24:59 | [CeXgon](https://gmgn.ai/sol/token/CeXgonvoZxEi9Rgpm8H98SHLzjApa3g42CpoHXu4pump) | 6.4% / 2.93 | +7 | BAM `9jxgos` | time-limit 0.8 s | **-0.0044** | [buy](https://solscan.io/tx/5zSfqGz5m7Q8kRBRG2Lu9TdfWYzT1CRnFVyhtGYRrPquBHfQm58KmvkeT855pJrkH19ZDFt6TTRZA3DjWPaP3hEX) [sell](https://solscan.io/tx/33Noq7XWsU1jAQrrC7xWKdTrMyrNDVF1jvxjhMrMcdZjPuNj1kwbTbyLTMqjq1QQr2JZQg9Rk5QG4ZwDkgH5ZkaA) [whale](https://solscan.io/tx/2CSZHZFRnZmeVRwtBNw28QGzpAc8AMUQBduTeCq2a3QtcTEKfi8UqdAm8QLncGNTXWC1gAVBJgwF42e4hGmMh8rw) |
| 21 | 01:25:14 | [6RWLVo](https://gmgn.ai/sol/token/6RWLVoFq8bBG81TDhshSB31xRVjAeo1cK1sjxy8Ypump) | 7.8% / 2.40 | +8 | BAM `DRpbCB` | time-limit 1.2 s | **-0.0107** | [buy](https://solscan.io/tx/3sBJcHrxnCDF3duA9vjidaddJUfQeJNXmV2KFaMtqUeCh2WkMHxfXnigjCRQuUAZHyr3imysjddCmmuRinTp7Yfh) [sell](https://solscan.io/tx/3b2XiVMe9vzn5nnd4mKusfdJaygqdbMAURL1zgDcALWfD18foPA1DGkRba4W2VrRQRmPfAxyFcSKm6Ha5NQgKvth) [whale](https://solscan.io/tx/66XyLWf8ABXLsvJVJKhZUSuLxVaahG4myDkurKzWqLVajzDu4Ms4Eh8Krrj6o8Uw7WseF45DPoJDFhSeoCMSS2Px) |
| 22 | 01:25:15 | [5x9DxE](https://gmgn.ai/sol/token/5x9DxEugAvCEqBnyUhCoL7iUjEurzeu9wdT5TYCjpump) | 6.5% / 2.79 | +3 | Jito `siidBV` | time-limit 0.8 s | **-0.0107** | [buy](https://solscan.io/tx/2kknzvaqwVqNDv6zSaeSAoA8KYuNnZy56NMUUF1sXotrK8ovTqn3Qmaexk6mR5rNFHVEbTyVdhieeM4R191WpW8r) [sell](https://solscan.io/tx/2x65XQFHeQuyCNKzeHHhCTQHVJeM8KxoPutCNy2aoNEtZJqAycwXRjBQ2Fc6sHh6XFdLuEAiDh4QQ9yiNmpis9ta) [whale](https://solscan.io/tx/NuCrnpuEwMXGnai1QjkRynZTb8bsnhQ2KKm4Kcg2fevv59DpZ7Q3fZoSVFFcZrWfeGwbz1oESXwHuavrAWptB9D) |
| 23 | 01:26:01 | [9dymiQ](https://gmgn.ai/sol/token/9dymiQUx3jwKftpxWM4eKcSKa5QDTPRkz2W4mQ1UGD7y) | 7.9% / 2.37 | +10 | Harmonic `SFundN` | time-limit 0.8 s | **+0.0191** | [buy](https://solscan.io/tx/4Zp6rTsMwcLdofR4QYUeppGRAinXTmtdotmXhWeGfD9jCGq3Rd7nxJNCYENh4z4rKrtiuiUbdpC9wZPtUp7xohN1) [sell](https://solscan.io/tx/5RkN43dNpi99pirJ5od62yWgu128dggTakTpg54MXauNrHcZ3yTV7Nu5rwiLJSc1dhvpyS4jSBabCiaTpKBv2Wri) [whale](https://solscan.io/tx/4Bp9EMVC9QLvUqrQLJH45vhtHjK2Jh4wME7UTAnr5wQszhnhxpc19Q2MAoW9ANs19kDcdJpo3DfGRVV1oJkdFi8a) |
| 24 | 01:26:04 | [AZzY84](https://gmgn.ai/sol/token/AZzY842pJAQdrvujwiRxMFKkabeyo6Pu2SJAVCWmpump) | 6.3% / 3.12 | +5 | BAM `sbidYi` | time-limit 1.0 s | **-0.0616** | [buy](https://solscan.io/tx/2tAuJuWTaJVfKmatnNK4FW7yjFSkNy3RgPkLSCbr4kA34aiVchEr4dBFjY8cB479fTWYvGzhJpWgG9dic7k7wGw4) [sell](https://solscan.io/tx/3t74CGBXsGWBLiBRtkQpDbff8wWpsdqV22iyfBNaLUMtcH8A2ZRs7MM6FxEvoF8HK5ZboocTWHT94ENkqcwdAS6w) [whale](https://solscan.io/tx/47kGCX3wWzgHhvp2hmtVnbgB2LVgLK3WiLFUQjAgUZKdAeCXnY3ahg2SezZ1jZm1SCDSNrm7V2cwJ9bjdiZFoHa3) |
| 25 | 01:26:16 | [4FU9fv](https://gmgn.ai/sol/token/4FU9fvwgiYawd6zzU11gAtvojADpg6Tgjh9ALoxgpump) | 6.8% / 3.46 | +3 | Jito `siidBV` | time-limit 0.9 s | **-0.0060** | [buy](https://solscan.io/tx/4QRdGPjFu8qACNshmkRs2LqeRG6tkzVnEhcTdPbKK4HVGJDSKgGhuViok8Y9izW6wTTG5ZJGM7jdL9BpBh3Xm8PG) [sell](https://solscan.io/tx/55vZ7A7Fm8aVyL8krh57yQJLzYHkDxDZEY678pc5rQejrWKiqCC3JRWRWwJLxRHM2E41pcmCfhRsrDwaTwrbfHtF) [whale](https://solscan.io/tx/4BciRGXZrRgzjDRLErfAJEVt1oYHLQGvTs9WNsE7AWKGv5XLBkSxsoR1HJ8vAb5UmTDS7QzSoK5YR5Th5Eq3eGpR) |
| 26 | 01:26:22 | [4FU9fv](https://gmgn.ai/sol/token/4FU9fvwgiYawd6zzU11gAtvojADpg6Tgjh9ALoxgpump) | 16.8% / 19.75 | +2 | Jito `E1r4Ps` | time-limit 0.9 s | **-0.0194** | [buy](https://solscan.io/tx/Urq4k2gqFYwNFDe2b63dhNs6kNUpvBjZ5M7j3SG23jz1mAnsw8KLaHvoDzc1TkhqecgBUb5hzCKhLAmjQN1vttZ) [sell](https://solscan.io/tx/5ZyZFVtMjmjLLNwvZjzAKcX3mzJryRQXLNnjp9pzoWbCyhdoD7DK89AsPzX9PArxwLHpRGjhJdZbEw3L9YQNzo1y) [whale](https://solscan.io/tx/5h66nuHRLA1vHhB2ZRWdMNQWgr1rQAeDAdMeP1Vu4oepuMayN9CmtHUb3gRsi3s6nAsRbboMF7FwAFg4qKBRiUGj) |
| 27 | 01:26:47 | [HMLqNU](https://gmgn.ai/sol/token/HMLqNUBRTF6Z3zVsCswKSaMTWDLUgqC8WfLffRiypump) | 9.1% / 2.96 | +6 | BAM `FWwwP9` | time-limit 0.9 s | **+0.0069** | [buy](https://solscan.io/tx/2FFcVKDFGYds3u6PCxQZwSJELZdDuhTBU55mKxji3MaxZFVi6NofaCSJnSKkiAUvihwUhzaUKHidvx1vi8tw4UnJ) [sell](https://solscan.io/tx/33wxHiRa9myDYqYYKzfRD5Ch8szr5jJWXtCLAH4qxYTazhFMj2Kmhd5WjNiGGMxRKEG9RVCDrRzLabyvMHE5ufYh) [whale](https://solscan.io/tx/3PNFHGTZC1xo4t8w6tGLGUr2PEkiFYHhXU6AEno57k3TPiVBYHe1biegzCS3Az2ZyTNR4RLMowmY6P8sjWwLZkyR) |
| 28 | 01:27:38 | [B71iz6](https://gmgn.ai/sol/token/B71iz66q9EPgV3VTDenwGnGuG3r1YcheKkHZKQ9gpump) | 7.1% / 3.46 | +3 | BAM `HLnodb` | time-limit 0.8 s | **-0.0367** | [buy](https://solscan.io/tx/3i96HXPP6AwMEmdBLn4GogoK9w1uLToZFvRpmREcoHVKwPKJ9VfmmzTugkqxWAt8ZzNfaYVTnHr7cgUR3hK1a8CZ) [sell](https://solscan.io/tx/2xDtkygB8T2CifLCJrvg32Cvmrx8TVrguW37CXm3fmaSnvfqBZmVdKjC4dvNbyAEQrmTBLGmC1X5tAS3k4tZuRVK) [whale](https://solscan.io/tx/2bKS3qZNfextyJt4YZPgsTvn7NrZKmDDpgkt1eJqyBARhaa1DweJTz3wsrS86ieZZoEDcmsUmQTp4onWj4ANJazi) |
| 29 | 01:38:55 | [FnkjEd](https://gmgn.ai/sol/token/FnkjEdN2eUcXiH5eRMtNRqwqiUNeDD6BKwEabCD1PFSC) | 7.9% / 4.44 | +9 | Jito `E1r4Ps` | stop-loss 0.7 s | **-0.1053** | [buy](https://solscan.io/tx/8zB1Pv4SQrZWE5xwNUbh4umpqQb5gDCq79uBhgcJDraWfggtq8LRs2i5WwT7BoB8UB5U2PN9qfXXboiHey1kjAQ) [sell](https://solscan.io/tx/4u9DgseMz8nKTVZUWpk76SB9E4FFh19fRG9QSutmKhikZLb3LUSbmbAxToq19SH9R55Un63zudaNqf2KH1zwGyHt) [whale](https://solscan.io/tx/2eeHTnSHGLVpvgGMx73DetJQGVcxuVR5JBFEoTUEAcaFUfk9obDQpbt3JXSJUek8T2ARcCAq2Swpby3sBoBg2pEi) |
| 30 | 01:40:18 | [FePWrP](https://gmgn.ai/sol/token/FePWrPZrhMXmTFoow6RVhgiU3SeCp5w9RDXgQr4JWdFj) | 9.6% / 3.04 | +6 | Jito `9rkJMA` | time-limit 0.9 s | **-0.0107** | [buy](https://solscan.io/tx/9E3DGoBfoHR9nS3hfLK7DgDjV3KwrVKqq81RNrpj1Gv3mEcNGTCeaVR1eq8SjQ7yE6kkLFfvMvXeXZUDEGLVyDy) [sell](https://solscan.io/tx/56GirYJhdwWsE4hbRFEADiryonjqJV1VuzqhLvvyVcYygSWB2TDGChrWdFE2acr4yNGEQiwEj5JywVBHXrG2CwA) [whale](https://solscan.io/tx/4ZWcR2UwoKAS7D3m5V14PnoetxRYaiQXAeftwG4NtH33t2vBddKf3e7HfvGQkRdHmsC3sSvFF2NCz7gJ8mdexLt) |
| 31 | 01:40:50 | [CLBvQq](https://gmgn.ai/sol/token/CLBvQqggFxobAcTP3RALsLZT1zwQHkCRzjg7o6CBpump) | 6.3% / 1.98 | +2 | Harmonic `3psxMy` | time-limit 0.9 s | **-0.0235** | [buy](https://solscan.io/tx/PW7Rw9Gjqd9mb2bqEq11CtW6vFvDYjtCisZkGYmZuUsW9piKkWFii667AAib8TYKtdUDiJyrVBWtcqxneCSaDEE) [sell](https://solscan.io/tx/3rud2wYYyPv7Dqu5iScgAZc9n5mX7vrCm8bAMcK8ig5xojpUVHQgRmoRG7RvNDwNKdHxRRatFdfSbU6TuPpKzRtk) [whale](https://solscan.io/tx/4feeZ3dM9fXsHawnuqsrErcqjh6YVU7asna7hNkwqSUS95SagjfgEsLonwKHQAHmEuGY1G8wEBKRmKMwrKrFVJyL) |
| 32 | 01:42:10 | [FRwW7e](https://gmgn.ai/sol/token/FRwW7etm1e2mrvYw9q81znTJgweyEPCf5UQApdM8pump) | 13.5% / 5.93 | +5 | Jito `7cVfgA` | time-limit 1.0 s | **-0.0262** | [buy](https://solscan.io/tx/FQQ8iuVo6TxubyaHfAsmc5CuZBPUU7fCoXXvD5KdzU5wWDVnca19hANPRC8HRm7G4diAvVgCJfAkbniy7yEy7Ep) [sell](https://solscan.io/tx/2zu9to5xuZg26ce3wxkfWCABdNev1ySimwv3RHu6uboqhYLacwgwMRqfowjU9XmuaemsajuBsHVzj9Ca3shcfJY4) [whale](https://solscan.io/tx/39vZmqtAxJ5WQ9sHS3D8gastSjxCvbaaaqDRW89JuLkmnrEJ9Yr4v9Sk9DV7C8eVk123uJC679ksyVu9z32aEdw2) |
| 33 | 01:43:30 | [7JBQnZ](https://gmgn.ai/sol/token/7JBQnZBBoiemEafusiF8Wgm3mb5LZfS6j65UHJDdpump) | 8.6% / 3.46 | +3 | Jito `C8Bey3` | take-profit 0.8 s | **+0.0590** | [buy](https://solscan.io/tx/Mkh5aUBF4fq2PBUZgmMdovHxaCLaWFM21w5DfhzMarS3y8pyqgcozXyp2d34dEapmcMxWuUc43CPTHvYThEyYma) [sell](https://solscan.io/tx/3qJH5isrByBvdjJkBFdCX7KdqP4jy3Ltc9MbYLQEv2tXwv5ERp4EXSfztHxFSbiGWUJHrZdbHvkYJWV8J8CP1DkW) [whale](https://solscan.io/tx/2TK3NJyh3jUFRufo9e2wBo1BUzX4KgqMoo4utbKWbQGzyuTrH8M1DUAVmyk4u79r2pi6Je8XWCvPqj2wQTP3WiSm) |
| 34 | 01:45:38 | [FZDa8r](https://gmgn.ai/sol/token/FZDa8rJRc6HovftDkN7TJBW4tNcZwo8pt7A6uPHvpump) | 6.5% / 3.46 | +4 | BAM `5EhGYU` | time-limit 0.9 s | **+0.0180** | [buy](https://solscan.io/tx/3ver4QWEMrH82djLWunaXCwqmf4H9QaBVZbciEW7tEVHwc6eo3119qW4QQeZKpQXZgErJ3VmUNdpoeobGXNu2UCw) [sell](https://solscan.io/tx/53EGMnzwsw5cNDFMz5JBs6uUjbn2qAxmTFbf1yk8ovo6R2B8sYzJx7yPiBRmCUhHgEwUxNMH5h3A2qA1mAk7WSZz) [whale](https://solscan.io/tx/2vCi6DtdX6qeoZnLBYqxo5DkHfwm2UvxjRnjxwSox2JwSxyNQdXWhaFjk3dsapsfRm1wpuN93nywikqQrF6j1mPY) |
| 35 | 01:48:42 | [BmUnqR](https://gmgn.ai/sol/token/BmUnqRhv6qrEtgYtdDGARptxuv3oCbZSh8eKNtnVpump) | 9.2% / 2.96 | +2 | Jito `C8Bey3` | time-limit 0.9 s | **-0.0284** | [buy](https://solscan.io/tx/3CwtbCdiRgFGwKWATkXsSHrTQinbijtiNk6MVxumB1rhyFavrzHt7WMWmwfiGTQFWvaWgbLj8YwN366cppDLG1SF) [sell](https://solscan.io/tx/5n1yMXZbyWqdf24bodxdRSfinsM1JyQcDAsZJbDkPdPZVkbt8D1DU1tbCLbcZNDXbWVJMeSia7ZZ9MBU99fxYFqe) [whale](https://solscan.io/tx/3xGpqdXkf6ZAm5YQnJbzihXi5TZhJtgSUL8o4NvSxesqLCXZiEuc54dUFxcGkjeU7dsVPQJmu9k6EwQXzUzZFnGx) |
| 36 | 01:49:18 | [GLwe2V](https://gmgn.ai/sol/token/GLwe2VYqwpU9VdAHZkKbT6rmkU1bJ79r8KFExKgwpump) | 8.1% / 3.25 | +3 | Harmonic `shftkx` | time-limit 0.8 s | **-0.0047** | [buy](https://solscan.io/tx/5DihVnSYBHrHj9aG9SQyW24BwitT5W2EidmP9x81btyJdmuAUgUMaHX9UgJihnaR9MUrLAYt2dt4Qa8LrfjhDxHE) [sell](https://solscan.io/tx/k88AiEa2qB4n6GCb79UAmVgxBkxZsBnHLdQktkieYotSD7ZWAJGdBBDRxNwrQRPs5Epxo9nvWeZrewspXL1WcHF) [whale](https://solscan.io/tx/47AmBvWHN4qJ7YALFfjeA8VtyHEha1TCvv6o9i8SdjKfoo44Wq4GoYUnbCjFAoEJL9k5uzdWnzSdaq1vJRC3VjFR) |
| 37 | 01:49:32 | [Ch1Tuf](https://gmgn.ai/sol/token/Ch1TufytwF1oVuLPCdkgnQvvb7z5F77sMzyx3278yeV3) | 6.5% / 5.93 | +0 | Harmonic `EJsJx7` | time-limit 0.8 s | **+0.0329** | [buy](https://solscan.io/tx/3w8Jzx3EbKTKWVTGS9vq9Q4CqZhpJzxMddNrqAvyrShsJyRDETZxSMymX5qrogKDPyBQiMh59urDr6bnQ57C7ZjV) [sell](https://solscan.io/tx/czKncmBAJpYBgNWGmG2kKiMtWotJy7eCsevgogGSZE77JKTX7SA1oxU8EjbnKGwsBpaNBjPPmnjXmD85oRugVn7) [whale](https://solscan.io/tx/RTUrUwPa84WeAgUrSNauJMJ1GK6CjWs8LWrC8UvBc8Q8PyuAj5USaems8qzHVTy9cdgLdqvLrvBWB1H5ZXDZVxf) |
| 38 | 01:50:04 | [KkreKn](https://gmgn.ai/sol/token/KkreKnbofUzmzq1ZLWyKoHzt86mWwmpk6wKzBCGpump) | 10.8% / 5.93 | +2 | Harmonic `BtsmiE` | time-limit 0.8 s | **+0.0100** | [buy](https://solscan.io/tx/3W8QL6diSLFkhLHvBNMpzb91F2vFt12A575ExVZPUM2KUMiEXjrUg988fGNuvZyU8196ZbfCtb5fUcVGqbKt7a3L) [sell](https://solscan.io/tx/2Wm897sfzTwM9cAtP9PJW3zgn7DqMtyUmPzD5b1wdRMZSqHhEKcrwo8an9bB8FkiYh7JsQccmcJX8YWhohebauZD) [whale](https://solscan.io/tx/5ryJFAfLpNA3pBnZhi6Nuu3pX6u6WbmZKNfxYqHeVXTnx782tbMHe3tRaD7MeE4aR6jAuLEhCanQoBS8r3xDxVV1) |
| 39 | 01:50:19 | [KkreKn](https://gmgn.ai/sol/token/KkreKnbofUzmzq1ZLWyKoHzt86mWwmpk6wKzBCGpump) | 15.0% / 6.69 | +5 | Harmonic `Fd7btg` | time-limit 0.9 s | **-0.0025** | [buy](https://solscan.io/tx/3YbX69zrNSayjNzBhBrZzTaUjy5Yns1LcN4yHR8c1z1ozT6fABx3wzz718SZns6zDCA26UV9nbTpBP1CrXZHECVQ) [sell](https://solscan.io/tx/599ZuuAHQN4GQWiXcHnPESCfVVnRY61t1d157YFjkLpH5dd7sYNKtiFbDfyfdXZVZYokQEaDtpLoRpNTFePR4kP6) [whale](https://solscan.io/tx/4a6oj94qBwo4eJHEkLPG9TEWtZskNy2JwbKaZrFFUq28jdr7onq1Jk6EoQppQ5v76ewhtPDbBBPTrEjSi29VchLd) |
| 40 | 01:52:01 | [GoPFj3](https://gmgn.ai/sol/token/GoPFj3jgJjCEJV5myuJZ9aBZ5PtfS1wRN4iTP35Npump) | 9.2% / 2.96 | +1 | Jito `HEL1US` | time-limit 0.9 s | **-0.0227** | [buy](https://solscan.io/tx/2PX54XJDjN3voXMqtG1fB8agm5VC3wakKNs9CozYUDzQ71cpmh6LpDL26gpdfZifhb3uLZriNJSCoZkor6XB6zh5) [sell](https://solscan.io/tx/2MbGwCpsNBqkAxzEm7zoNcN4VviJaPPncqeXQFovHhKPQ6JqaxQTinjcF5aUymbJ95boYNKbG8bbhdYFVyJpd6AL) [whale](https://solscan.io/tx/3Y7sndgbgaiqc4qtBXQYBFPQ4kFsPZ95K8pFiwJsw6DHYsuSR5YzfufyDUa8AaHXP4GogNo7BBPShyXyb5c5zWNj) |
| 41 | 01:52:52 | [AMfUHm](https://gmgn.ai/sol/token/AMfUHmRaz5aFadkMtYBL6e8ZcbX9QJVGFaHPkZHfpump) | 14.2% / 5.93 | +2 | Jito `BCJN2v` | time-limit 0.9 s | **-0.0047** | [buy](https://solscan.io/tx/64FrRfmLuSiN4CdJhHfUqeip9WNvrgWUhaX92V5JTtrPomSnLoBFa86eNcSaRm4KqY7ApwpTC6gvEmokfxPsf1Lp) [sell](https://solscan.io/tx/4GnSp29cmDsHuSy9MrJeycgerA1LyALhkQXy3skh6pTsLGavCB2BZ2HG9bwkQt1LdbUAHfNpMATc3cwJ852LXiB5) [whale](https://solscan.io/tx/3mFYF9bPnnVCioVYiAXYZJSvQpnjJXsRFkfFs49CgGNg6RPqXP4eQgdV9KrLoEanpGLwzvothVuwxgKYvdaLJxLE) |
| 42 | 01:53:31 | [Ge5NLK](https://gmgn.ai/sol/token/Ge5NLKPzwAja6NGtHzuqCunR9NeVUyahemWddcorpump) | 6.9% / 2.96 | +3 | Firedancer `EvnRmn` | take-profit 0.4 s | **+0.0386** | [buy](https://solscan.io/tx/3LrvKLLa53GwYZMGxNFEwaDyvSgtZJSvwNnLRr9SfemAgeAF8dusFh2s7uThAfxjcpjJKST1tJqdbrarbgGwYD11) [sell](https://solscan.io/tx/6161ZGnyWFX4dpj9GYSRRAx4rD9ekwFbXiTQdxwGTksmYeqT19fTBnQYLHNkbion9oC2qoTn7pN7beGjdVJqxY7H) [whale](https://solscan.io/tx/2SG9eTRGpf9p7majqWxex4Jg1QrbaLHtYisUK4CFr5SWyhm3yvKK8cCxJxX38F8qzXzSEkRZzGWq4bgVjS7f9yoX) |
| 43 | 01:53:39 | [GnZeBq](https://gmgn.ai/sol/token/GnZeBqAXWX9Dz7pbwKC5vbP7E5pbn265uVg9tzQwpump) | 6.3% / 2.96 | +3 | BAM `HLnodb` | time-limit 0.8 s | **+0.0012** | [buy](https://solscan.io/tx/4cPh6pdSQvKsqZY1wNfZgif8pgcAZrCpt91tucGynX9g18CsZrztiaYkRdCJBSrt91WeYEECBE4CBVqf7dY6nxGr) [sell](https://solscan.io/tx/2vBCv2bACiwsdKd7arLSJx4m5kfHtYzpVn8VAjHc7Swp4rP3fbYUAUXmAf23LejLfyks6EkbmVLfCxnzbFcYMTgM) [whale](https://solscan.io/tx/2Db7Stxvg1nm3aQZbwxYjUq3FbZ8mfrQJNz33ZGjTptgQcW8wV1U4fYkbCFvzyH8KgXLsssf7JudaovXShsxoaqY) |
| 44 | 01:54:32 | [Ge5NLK](https://gmgn.ai/sol/token/Ge5NLKPzwAja6NGtHzuqCunR9NeVUyahemWddcorpump) | 7.3% / 2.79 | +3 | Harmonic `5ZqveV` | time-limit 0.9 s | **-0.0119** | [buy](https://solscan.io/tx/5B7obhETUAG2qKDhbkyXZM8CKGnffj3E7msV744eNbCCoSXFqYsxTtcTUQtWUpsKLiapT3pthzS7xW2CZ5g8zJDt) [sell](https://solscan.io/tx/5fbAxwFQx7isCB8wRWHPTbkKnmDZByjStLGXcDvr9UAcYUi3agca5Xd97TejAaWGeh4aJdfqrr4Y5Eji994S3g8u) [whale](https://solscan.io/tx/DHbSLYtKHinLEFzg1h4vUBZZufPBbL4TWCGVTrvcUAAqdccaQr39wQs6wW8HtaMfLQK8p8oXtixJe5P1TppkYzx) |
| 45 | 01:55:30 | [GNbxhM](https://gmgn.ai/sol/token/GNbxhMvGwWV3u8E3EnMc6bgBF1gkYQ7AvV7TRBiRpump) | 7.0% / 2.96 | +2 | Harmonic `pSo1KZ` | take-profit 0.5 s | **+0.0411** | [buy](https://solscan.io/tx/5LdNys1WiV9yukCNvbLsUA1YYEVrJhsZzUThfXg3iNpCEyzgMosF6BAU6c74ikpM3weK1byWvefQZKZCLu1WGGAw) [sell](https://solscan.io/tx/4mepQBRrmHX3L9495NVGqcB1Aa8VLtiHPfhJXLkPQ5EwMU84AdPsatCWcWt73WkwBRTXCws4LQsZPffmVHSJsSJh) [whale](https://solscan.io/tx/4k2FKnhHRprau66YLAm9zZ4HqKjvSbrXQA7by9hxUDF1taaGZYGbEWqRfjhoAp3BUHDv6FXERa7Rz7JTYJA4hf9E) |
| 46 | 01:55:43 | [8gWSGn](https://gmgn.ai/sol/token/8gWSGnA6pNnnWMgeRK5Xmqy4hYrXovaDDzkiPa6Zpump) | 9.2% / 2.96 | +1 | Jito `E1r4Ps` | time-limit 0.8 s | **-0.0227** | [buy](https://solscan.io/tx/5hpm7KXpq82ZooLGVJ31bkat6LY6UiWWQCZXxpu5tCFYiXszrVUtqGrBsyQNZ8eTPi8S1mZ56o79ywfNLTkCK7DW) [sell](https://solscan.io/tx/43kxvnH2LikuA8exLX2RUKBw42JFpJQ6uqXpDreXeJFgVamtGvycfZBoNUvU6DT9fT46UR8HEZjU4B9HXqWEaKeB) [whale](https://solscan.io/tx/Fm371Uerm989nCYqWD3r1mwVturbyij3BMYEc87bJHnaQvSpyB4CPEVLrKS6MHk5t57nGxp3foKGwJJ5vGhSSGS) |
| 47 | 01:57:24 | [CSsmSN](https://gmgn.ai/sol/token/CSsmSNoHjzLUhgRE2zybGQSHSYANH7KY8vgUycyGpump) | 45.4% / 29.63 | +7 | BAM `5pZvwj` | time-limit 1.3 s | **-0.0353** | [buy](https://solscan.io/tx/4CvWjuoAezgD8EdSqyMpQRGdRTBCUhjiSmyc32n7CoLdvHnFeSQ3QieNcrX9yRs13JPur5ATxnpU7UM4ULMM3eVf) [sell](https://solscan.io/tx/34R3V65U3TeMqzvJbewxhFLffqf8Y2jTvEhB3QLb2r1c9VSsNb4Z653d7EauvjQPXtANX6U5bhhy1vSzoe8djnnN) [whale](https://solscan.io/tx/37SZNKmUPNhZx7QGo3GAGuDPTJuhz9M6hWZmf38MtD9cCMg6GZcpJJ8uBBdtjPhq22FbwJKe13PbEefHhYZWANX) |
| 48 | 01:57:58 | [GrEdcy](https://gmgn.ai/sol/token/GrEdcyVQRvfNyxXW1ppsJhXVSEWjJQcD9wQariycpump) | 11.9% / 3.95 | +1 | Harmonic `FBKFWa` | time-limit 0.8 s | **-0.0221** | [buy](https://solscan.io/tx/4jSvRohUbozLwUTTNzvBPEZGtQG3PFFctphFfa6nA3ixePVjKZLcjwuAnkfsK9gAZ6LPf3cCMRGpjyQNRDfrRUHE) [sell](https://solscan.io/tx/3LzLi7XcXvDrwCWgYQbsu6TFvihw9bgQ2jW619FtazsPuSnz3DgyUrbJjfiB5RUqHSZMBwRgUW4dN7UorypQTDEC) [whale](https://solscan.io/tx/39Fjgrqd1NZUe8hfhkxP5Dq5GQ9hAL2a6GZYRc8etL7DxGRvxEEozUNSz6Ctk6krqMyJYk3v6PzicMaP93LUzKLx) |
| 49 | 02:00:14 | [JBX3aq](https://gmgn.ai/sol/token/JBX3aqVZ4eKEJJtWT9rkMymDJkkSUDzqVskUD65opump) | 6.2% / 2.81 | +2 | BAM `jzDsim` | take-profit 0.9 s | **+0.0524** | [buy](https://solscan.io/tx/61URudMsmXunLCzgLEg2ma6kf5rfdTxotqp5md76DwPgm7NB76eesag3zUmmb3ubb7ZVW6cg49Cwuch5eRb7VcRt) [sell](https://solscan.io/tx/4pUSacuoEfuBYH7PkYK6EioD4DztEYhh9SRrLv7GTmNXJDsiH92GRNnP5eut1vL2NCgzURQprykcMUifVqDKXkHA) [whale](https://solscan.io/tx/3ZUmQnYj3cj5XzKSQAi9DZKw1qLcfeJASHuVMkYpsdUyFYCo2ZD7RFm6BrLkr8FMWgRbU4iwjk2E2Z6UmJ5LnaBh) |

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 6859 |
| Inside the envelope (age / drop / since-buy / size) | 2885 |
| Picks (score above the threshold) | 97 |
| Skipped | far_leader 50, spacing 10, presend_armed 3, presend_position_open 2, open_on_token 1 |
| Buys sent | 31 |
| Filled | 14 |
| Failed on the +5% guard | 17 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 14 of 14 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 00:34:22 | [6oto1n](https://gmgn.ai/sol/token/6oto1nM25U7cHHjThh7gvh6wNGrFxYsApdLC3Npqpump) | 0.35 | 0.03 | 3.16 / −10% | 225.8 s | Harmonic `3iSQtP` | guard fail | -0.0005 |
| 2 | 00:35:07 | [72UuvW](https://gmgn.ai/sol/token/72UuvWnASEUdiMZkUbNLUwEGWjeDUCVoaaT8kKZSpump) | 0.35 | 0.27 | 3.63 / −11% | 52.6 s | Jito `E1r4Ps` | filled | **-0.0047** |
| 3 | 00:35:10 | [F6gbKX](https://gmgn.ai/sol/token/F6gbKXwVZAjvV8FR1ZLpREL4jAcrGK8zMGnCrxTQpump) | 0.35 | -2.08 | 1.12 / −7% | 11.0 s | Jito `HEL1US` | guard fail | -0.0005 |
| 4 | 00:39:06 | [5SE1qH](https://gmgn.ai/sol/token/5SE1qHPiydvCHjmRANnWhRB7qA9VA8QQrSFNVupgpump) | 0.35 | -0.92 | 1.78 / −10% | 7.0 s | Firedancer `EvnRmn` | filled | **+0.0075** |
| 5 | 00:39:36 | [78GNpw](https://gmgn.ai/sol/token/78GNpw9qvt1aNtQ5YRGaqsJhanvexWtev15pS7i3pump) | 0.35 | -0.10 | 7.62 / −23% | 6.8 s | BAM `5XKJwd` | guard fail | -0.0005 |
| 6 | 00:39:47 | [78GNpw](https://gmgn.ai/sol/token/78GNpw9qvt1aNtQ5YRGaqsJhanvexWtev15pS7i3pump) | 0.35 | -1.26 | 3.18 / −8% | 17.8 s | BAM `Cu9Ls6` | filled | **-0.0133** |
| 7 | 00:41:57 | [Cw2sD5](https://gmgn.ai/sol/token/Cw2sD5g4DrEJbovgPWkELauBmE27SQE3c1nLKYEKpump) | 0.35 | -1.07 | 4.16 / −10% | 15.7 s | Harmonic `5ZqveV` | guard fail | -0.0005 |
| 8 | 00:42:16 | [78GNpw](https://gmgn.ai/sol/token/78GNpw9qvt1aNtQ5YRGaqsJhanvexWtev15pS7i3pump) | 0.35 | -0.02 | 5.59 / −13% | 167.3 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 9 | 00:43:52 | [47mAqN](https://gmgn.ai/sol/token/47mAqNwjx1njf72BPJ95p4pUWkf58QbUpddjYARSpump) | 0.35 | -0.65 | 1.90 / −9% | 2.5 s | Harmonic `pSo1KZ` | filled | **+0.0576** |
| 10 | 00:46:06 | [DtoqYp](https://gmgn.ai/sol/token/DtoqYpwvDi9egCMEYvFmsAbTqv8hFfYAKNWYUxdS2ZyN) | 0.35 dev | 0.94 | 11.92 / −49% | 2.5 s | BAM `YuRBAs` | guard fail | -0.0005 |
| 11 | 00:51:56 | [7tbNpW](https://gmgn.ai/sol/token/7tbNpWf22h1jTfPVrJFx17cJZgPSWbjeFxdV6x83pump) | 0.35 | -0.16 | 4.95 / −14% | 152.6 s | Harmonic `FNKgX9` | guard fail | -0.0005 |
| 12 | 00:52:14 | [3Bppea](https://gmgn.ai/sol/token/3BppeagFM2xHCkGHMcvKMGvSxMiEM81zyBowqHEupump) | 0.35 | 0.86 | 3.28 / −14% | 19.3 s | BAM `9jxgos` | filled | **-0.0048** |
| 13 | 00:56:55 | [3kQuJL](https://gmgn.ai/sol/token/3kQuJLkoRszRjkSUXxqc4WKWco8cs7t8VL6anuvXpump) | 0.35 | -0.33 | 2.54 / −14% | 3.6 s | BAM `11AMA4` | filled | **-0.0274** |
| 14 | 00:57:03 | [643XfS](https://gmgn.ai/sol/token/643XfSzYVnA7Dr9CjABUT2TecNjdUbqS6E1HSqeYYUbD) | 0.35 dev | 0.48 | 1.77 / −9% | 1.7 s | Harmonic `JUPiTE` | filled | **+0.0051** |
| 15 | 01:00:57 | [3CKozA](https://gmgn.ai/sol/token/3CKozA3meWKeCPAcv9xoG1bDvoUy4t5tcZ7QL5hepump) | 0.35 | 0.50 | 1.78 / −10% | 3.6 s | Firedancer `EvnRmn` | guard fail | -0.0005 |
| 16 | 01:24:26 | [CZwpDR](https://gmgn.ai/sol/token/CZwpDRdKBEo8ESKbiBdQ4CKrJySQzZAMDBUzzjDspump) | 0.35 | -1.75 | 1.16 / −7% | 19.7 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 17 | 01:24:52 | [59uDru](https://gmgn.ai/sol/token/59uDruJCf5D6X3VBzWy4xe9rZYhtwscHNuFyd4yD6dGf) | 0.35 | -1.06 | 2.09 / −11% | 7.2 s | Jito `HEL1US` | filled | **-0.0496** |
| 18 | 01:24:59 | [53zSXi](https://gmgn.ai/sol/token/53zSXixBLHc6aUwPLUJZEhxZ28cY4fthZNRrrSs6pump) | 0.35 | -0.93 | 2.47 / −15% | 4.9 s | BAM `9jxgos` | guard fail | -0.0005 |
| 19 | 01:25:22 | [5zqq8j](https://gmgn.ai/sol/token/5zqq8jP5w3jaZX3DL3MSNQv4wLx6mFLJcY5a1DG3pump) | 0.35 | -3.35 | 2.83 / −7% | 31.6 s | Harmonic `Fd7btg` | filled | **-0.0652** |
| 20 | 01:25:29 | [91YUbB](https://gmgn.ai/sol/token/91YUbBrG8Y5aTEm69EAiDB6HM8UDmRVze5Mm8DGApump) | 0.35 | 0.26 | 2.47 / −14% | 10.0 s | Harmonic `CQdLgw` | filled | **-0.0190** |
| 21 | 01:25:31 | [AzW2Sw](https://gmgn.ai/sol/token/AzW2Swc5fxm9WaLAoMRnLQdxCWAyMQqdjAFtCJuLpump) | 0.35 | -1.20 | 3.69 / −19% | 8.9 s | Harmonic `Fd7btg` | filled | **+0.0486** |
| 22 | 01:26:41 | [29bHtR](https://gmgn.ai/sol/token/29bHtRZzzDB8cJspyyeiCEkuyo1GyJKvnp5hxwWEpump) | 0.35 | -0.67 | 7.91 / −37% | 4.0 s | BAM `8yjHds` | guard fail | -0.0005 |
| 23 | 01:29:05 | [FuRpxg](https://gmgn.ai/sol/token/FuRpxgexk7qrrnm78YtvVUcQnnhuUoWJjJuuRfJopump) | 0.35 | -0.45 | 4.94 / −26% | 3.6 s | Jito `HEL1US` | guard fail | -0.0005 |
| 24 | 01:30:22 | [3LPTan](https://gmgn.ai/sol/token/3LPTanzycRAjguU6VAXE7T2Fd12LePQLpHATXXs9pump) | 0.35 | 0.74 | 2.84 / −11% | 114.7 s | Harmonic `JUPiTE` | guard fail | -0.0005 |
| 25 | 01:33:28 | [3LR5iA](https://gmgn.ai/sol/token/3LR5iAd3VtwUJ1yLqwYhx2HMVzdciMYh6nTkb5iLpump) | 0.35 | -1.15 | 3.10 / −12% | 3.4 s | Harmonic `HnrXmm` | filled | **-0.0505** |
| 26 | 01:43:28 | [6zyR4X](https://gmgn.ai/sol/token/6zyR4XMBE8ZefFhqoDpfjacFVq8C22ppNNskpnT1pump) | 0.35 | 0.31 | 3.43 / −14% | 70.8 s | Harmonic `shftkx` | guard fail | -0.0005 |
| 27 | 01:50:35 | [EZ9NXc](https://gmgn.ai/sol/token/EZ9NXc6G6tXfPw4nSNQPgZquTc1VFvUouYiz9kd7pump) | 0.35 | -0.77 | 5.24 / −20% | 6.2 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 28 | 01:53:40 | [Ge5NLK](https://gmgn.ai/sol/token/Ge5NLKPzwAja6NGtHzuqCunR9NeVUyahemWddcorpump) | 0.35 | -1.51 | 1.40 / −8% | 21.0 s | Harmonic `Fd7btg` | filled | **+0.0331** |
| 29 | 01:54:24 | [767itv](https://gmgn.ai/sol/token/767itv4YUz2P5KaSFXsBB5f9i1Ju5cpvaZ25hHc1pump) | 0.35 | 0.00 | 1.83 / −11% | 5.1 s | Harmonic `3ytgyJ` | guard fail | -0.0005 |
| 30 | 01:55:23 | [9mzsxR](https://gmgn.ai/sol/token/9mzsxRKn8zSE1JMwCWiUmbLYgQUSz1oMx92DhdgYmAGU) | 0.35 dev | 0.26 | 3.29 / −17% | 6.2 s | Harmonic `Fd7btg` | filled | **-0.0225** |
| 31 | 01:58:30 | [HRXXn8](https://gmgn.ai/sol/token/HRXXn88CkQpZzS4dRvszJUDuW6qhFjVA6DnLCx1Rpump) | 0.35 | 0.19 | 2.49 / −8% | 2.5 s | Harmonic `3ytgyJ` | guard fail | -0.0005 |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 40 | same | 7 | **nozomi** of falcon-udp+landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/3v9YTn66pfyCovFnkjEa4nrEuC915MQrPViDStmKftxpgsseaBYXk7hX4Tgnc8rkM94uAA7XMpncEBKJmsGRZqJE) [dump](https://solscan.io/tx/3NUzT1C8Kx7B7tat8ypXVTuC2nWZ9vjDDE9WVayDNbLd1BWYjWbUbMFShPMAkDGssbmyz6XxRe7cm81mhuUZk9Kw) |
| 2 | 78 | +1 | 2 | **falcon+falcon-udp** of falcon-udp+falcon+helius-swqos+helius | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/47fhDjsjdHeBpEzNwbdyWiPABUgDx3VTJSbmtRDYpWrivCrWNZDr35cSiL3GnsC71XvBizXTrShYKeUehPys5yz6) [sell](https://solscan.io/tx/3YgN8Dh7Sud5ZoUGR8mMuE3pFLAtsdzDAbrNgXTXB4BiVACEztBFEmtXnJFQyvPaM4Ba7iVEUny7qRGkD9uMdyNB) [dump](https://solscan.io/tx/4T6ui9okKkiCZFKQBaHEjSPzsoNGjAPFpbavFzRiNMR8n5tvpbhQ8jb5cKxawH3XQWBrrDC4phpDDyihSY2DHp2C) |
| 3 | 94 | same | 6 | **falcon+falcon-udp** of falcon-udp+falcon+helius-swqos+helius | – | – | [buy](https://solscan.io/tx/3FpYu35VeCtfLK2yEdLYXBebjzYQ3Mp8n6qMAYGA8dL2FNBGYhwP8Fnjg99MFy3useky4TFZJ34DUZwW3TdQLmib) [dump](https://solscan.io/tx/3KskGecKF5uUPi2HgLL2kDF3LUN35ig2X5fWMPKRcyEfSgbpqKq56V48w2omU1uw8krKS87Q5RUcz6iXch4AntSt) |
| 4 | 15 | same | 1 | **landx-fra3** of landx-fra3+nozomi+staked-rpc | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/3TrqHYbTz2FwcT2tpn8My4yec3GmtSkoKku7WwbAu2XB3Rx5Sj3opWwUKv8oDH1D6ESvBzZJ45Qm8xyo76gNKTxo) [sell](https://solscan.io/tx/3nNKAysMce7QCMBrJx39cHPZquBpRRo5rgrUYjNgbyEM7ZKkXMbLphR5cdUJbre4rzgTJnzSrNVGHSMqeeTBXFfj) [dump](https://solscan.io/tx/2HLfdjDAoowWLbS19B6hxicYWJZZr33eNiRZYdHg7aPHjsPyp3qk5YT7chFaEkg6HFReYwoy9G4oQsGDczv5NkC) |
| 5 | 36 | same | 6 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon | – | – | [buy](https://solscan.io/tx/67Au7S7iZf69ZcCLwRos5FvwMow7GYR5VL2AcXGxZSYFDiBo32XEKryeofbrA22ef4WpKw9Q59QrvtkmXoeU4Vdo) [dump](https://solscan.io/tx/DgH7XsNzCeM37UjKmyEXUdXaBreuJ31tRm9mh2tMPuRDmBktaENTzNA2AjxY2zstaMdpKJbFjYgXZDFNp7D1uNz) |
| 6 | 48 | same | 1 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/4hXcviXx4jyu3n3JSsAJFtz2xqJB5gCVJ6n3HmAGWEVaKrka67JsYRmNVB1ATYnxqQuJq8HCamGNTTGmePJn6Xes) [sell](https://solscan.io/tx/29HAS63P2obissrYxxbgoy61upmrj5nbX5NQbycGT9xuCJJ1mv5UvRWWJ5Bys3PauKJCWncdWqw2mEmLjXNBjix5) [dump](https://solscan.io/tx/2FRx87FY1VpZnLbkknTUK7LDSxbV69d2BQbWjzALK6vo5jtr3cqQLyrvh7hxWsqrdhi1f2wmKGUfvHPUDjkHZfi4) |
| 7 | 69 | same | 5 | **landx-fra3** of falcon-udp+landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/4b6Wyh8tJzo13SnLwqw9tkkdu4K6zVg6SkYQEsDfk5N8F1srttxaWTeoFNnpi6DNuEbEpcELswRN4x2HkQWXRae3) [dump](https://solscan.io/tx/2BYFw5eJkrtAD4jcyzpPJsyXjip8zCAqeEHxfaJXuK8eyqdxyRroAUBFRxs7tEHfxBURa1UNLBeu9q9Xf7HTnuCH) |
| 8 | 29 | same | 6 | **nozomi** of landx-fra3+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/5xh7P6Y4vwZmSH3PE2VGtr5AQtVgK8uySAX49PhRoTjjgySuq8Yvsd4XQVrwEnFAsbaTvTDUMKwRBihVc88BmQtP) [dump](https://solscan.io/tx/2R1cQk6cwj2eYRDLwLCLZT5sCYe2sQTSifRGK88Jo4rWYHQzjTVvMcwUcisUyG7WJuYgtNoERoNDQrMxhWWRiZdY) |
| 9 | 36 | same | 2 | **nozomi** of falcon-udp+landx-fra3+nozomi+falcon | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2VwZGjU8agmJMKKp7HWhtKv57A9CMUs4cjFjHJPgwMQod1H59jmWXkanXXcrbqYYHSAvpt2j8imjbJwBR9iVdhVF) [sell](https://solscan.io/tx/2qRvnwoHu3wgZmDguwq2Vem9ju8s46Cupp2C2zVHZdybjRHwRaQGbqTHMsSF4pxoT3XMxAQACKzBqDXGZx3LhQFv) [dump](https://solscan.io/tx/5oPKfFtRTE8ohSxJNWyAUrjZ6DX1MS3WideY9BAmiefANPNnGxSm7hzCrzpB9tZo5RY6d5edcvABREv44uBf9c4L) |
| 10 | 39 | same | 7 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon | – | – | [buy](https://solscan.io/tx/2ycCvp88uyAJPoGgBS8BcbM5V6gzzUyHJP4w5uuvATMtAcNYPWCBin8c1fpv8BX9DpM6yQgWBbWtm39bvhTSoLXQ) [dump](https://solscan.io/tx/5UMWSJoTKJD4LZYFRwY3EeQVK6ySLvLj2yUBWuDTTCttYrbzHFLittmdmzp4q8vekVER7boyEtq2PcfGHktLcmxP) |
| 11 | 16 | same | 4 | **nozomi** of falcon-udp+landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/goNbXfW7u6G7cVj6RWZP4cmrWPNzVewzqAdw7ssGJPemT6a4RtPpGyDhsP1dNvtkfkn2ymMJSvyhYoMhCCjVExd) [dump](https://solscan.io/tx/3JHCDbepVkD24TSRykrkLZDM3JVPaHJwViMMM6yDEtYgw9KQ6Z63A1XdEPFpbYyc5mmwxqFWKagRD3x494wunFi3) |
| 12 | 41 | same | 1 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+helius | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/5fG6b4zG6snqKRiDjQDHvvwkwhyVBv5WTMzvnoxde8MXw5WfY1KYKVf7VLQyz9W19EQt6NheBfV1evBwMLH3tnbm) [sell](https://solscan.io/tx/2w8ee6a2fw6TyqADdQrFqnEnQ1vQnQG5JywwuoSuyvnF8TcTjiKFUKAgH3UU7ygMDRKiRAnSYTmHmV54cHAPd7EX) [dump](https://solscan.io/tx/2ZRMo75DqQtnSP1gUsgFv5FJzwbnemp7YkHVeehmMGAT5h7ikt7igQowNYqNc4SyunKW9edqjCBTwvkHftYfW47w) |
| 13 | 59 | same | 1 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2ftSbdy382H9TEvmTiPxnXi7BNJNJc7zJCSKf3bQqg3dBkqoJZKQtiC5mCbQ3n1qQyXqEJqU2xxF2mqDMAm76aeQ) [sell](https://solscan.io/tx/57LHfq5EGmhHKavzN82q1KUjzi6AGVJhB86sTrnXTPJRxaQ6mmifrpvAtxWuyUw2fpjxk272NLcf6z7zyQu62YXc) [dump](https://solscan.io/tx/wdYFN2hZzkJSWdsvRWqMW97Ycj6jjQhtd4SestA3rLoEXmFK5FDi5HP6rJm8khPxUF5zSn5fGSB7reR3bqgyhb4) |
| 14 | 42 | +1 | 1 | **nozomi** of falcon-udp+landx-fra3+nozomi+falcon | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/CG92hDXmiY3HoPtSVdbyBarJZgTJqpS9YTubtvX7KqQm4qZVZ6A1EVE1dAFP3MWV8K7e3ZdSW2TBx6kGQnPwDvj) [sell](https://solscan.io/tx/223RPG8gJYHd4TfsiX5LDEnegjHNomwrEeNF1y6WjFJJYpG6zrD8NFvbbDxwqeR3MrbWyTo7cHqdLGmqjVSMp7P4) [dump](https://solscan.io/tx/hZV5XbzMXg9bSvj5TQx5WSzQWGoPTz9MWLZJNfFpae5ge82ZqffxXaQtD2xomdEf7boJKPH3UeJTCs6mvR5L7fb) |
| 15 | 81 | same | 3 | **landx-fra3** of landx-fra3+nozomi+staked-rpc | – | – | [buy](https://solscan.io/tx/3i6RqSSPan3zj5Z5JXqfvQT2KpsbuQ5ReoKSP3AQKF3X5XhPsX3PiXcZvQv8yuzuEKiwTpifoixBWrM3K32kEP5o) [dump](https://solscan.io/tx/32iuQsFPM1sqaHXsmdqKu1Ddjooz2421cFfT5CJGiKRnjWe99H3s6RAHMStUnYpJ49mdFpX46mfadytMAkjARVB7) |
| 16 | 38 | same | 3 | **landx-fra3** of falcon-udp+landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/5iNgjY1fMPYdw8dAYRLmZMBUjRWQRP8pu4V1oTyAMnjzQaDraKumoxsAgRZbwvTC1mwc2GVV2BcqtWKHwn2fjgfR) [dump](https://solscan.io/tx/3dAyga4UXMpkF97bBoNasojAGLLE8wcCekFdgXzq4r7Bmvt5vNZVZ8577XVcGzcSbnXTSK3VZnXZiYHoACPRtoEi) |
| 17 | 130 | +1 | 8 | **falcon+falcon-udp** of falcon-udp+falcon+helius-swqos+helius | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/3yoSMPu2gJXcsTHPELZ1ee7b8aMzLKDWmkoBywStB8AfQhGtfGRi1XuiZw78cFUzR4CrKk6Q1tVBefbonfGAaYxW) [sell](https://solscan.io/tx/55ebLDjUBDzxKwe6tfMjcWqQqwYADVhzqm41GsFByqxVJywbhEN1KGDQCBEfuUEHfC4RGino9VUGYqm551zNJhX3) [dump](https://solscan.io/tx/xmHeCjgKDoNEN9X9dttizfg33NJKrUwzB2gGD1BQDEkqq2QMJkoV4HBXUAHh9uem3htoCjFYm1QdsyeCkPt1Wfa) |
| 18 | 44 | +1 | 3 | **bolt** of falcon-udp+nozomi+helius-swqos+bolt+falcon | – | – | [buy](https://solscan.io/tx/9AyWJd9D5rKtYjxDaLL5ZoVjEPfipTHAV5zeuTpVhxZ48pXWbXAvr2xoqzDaQnt5WSpdHhxXX3tfasVP8jPNJc7) [dump](https://solscan.io/tx/4DATMixeNixSg5rSfa8Mo8G2CNqMS8W29imCKWf3R4zV3wGpms84g1tWRaJ7w3oHjRENwGqqqM4KfLbkHV2cwNkR) |
| 19 | 141 | +1 | 1 | **landx-fra3** of falcon-udp+landx-fra3+nozomi+falcon | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/A1vUU2pKj4iKmTPjDXrXqyNWfJ3xYBTKaALo8r2ZfCCSJkmBUQhGs7pf1mBBAk4qPiVpBTgdr5mZ5CH68PhJGu3) [sell](https://solscan.io/tx/2J4bYA9LKjn5zbC1Ydqzz28a8Pgx4CfDYjmhmdAoGqPxUbk6sHVwhd442cL6r76BGxJ5gEjD5x9ubc5akAfGzYi8) [dump](https://solscan.io/tx/5LzTDPNd7ai9FzYBMeMfGjiKySN4YBDbdJg2RjsP66xGgFPWb9z9Bjzed1G6CgQqxiicvXDJu3a6LrE9i19vTbLS) |
| 20 | 97 | same | 1 | **nozomi** of falcon-udp+landx-fra3+nozomi+falcon | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/5Rf9p1ADFUQidQSr6xkvncGdFmuSNruN9sMbBQncQGhtehupPHae8wahfN9LfLkJ3YDAi1ZjP5MtGgnQEkx3qJiM) [sell](https://solscan.io/tx/4W3WdySJvDxZtXqw2AtnVdx2eYke4nrziA9Kakovxd5yeeC544zyEFvf1vMHBp1oPBHTP4EGqydNMNo8rC1AfXES) [dump](https://solscan.io/tx/2kzhtoJGBvNqNHGY18aF1p4Sjnu9ZGpsXLsT1LoEojSETTkqzLfTA3GtLC19ytWKoqxn1f6jnXaigqc1dRQTkdZ8) |
| 21 | 48 | same | 2 | **nozomi** of falcon-udp+landx-fra3+nozomi+falcon | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/4WEQCoNVFCfzi98eqCor3gGq3XTdS7fupyPU32VVrUYkH3e93fZAz268DSAAQzEa8u41DGZ85DuaQcxgsvR1DrzW) [sell](https://solscan.io/tx/5Jd73HRB7CmkDJyvqiMuntE7uoKnGSLEaSz4zqjFULUJMxr7PFyzP1TLtsAqCWZ7TfQJXAtFfy5d1DUTP1afZDUy) [dump](https://solscan.io/tx/4hN5Eq6iP2QsGVxpCwxMyvwWbLc8DuzQSXXg1NNHpXAFZJicPDg9zZLLrjGHvW17CNvGgCzTTpLwJ8H9MxScUSyH) |
| 22 | 98 | +1 | 2 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon | – | – | [buy](https://solscan.io/tx/fQTvBaNkC7w9iBdfQZoyDm2sXxcaRJYFqjHtPksrNb8BqagKxeEgcSP98TSKfsD4LhbKYMsHPcnmwr2VvD7wayY) [dump](https://solscan.io/tx/5SRRJpWNt5Wd9Fe6683tBx15HZETYVp4E9ho1HHTvEpHYib6s8n96QffhvWncoNNyqtNtqpfq5HVw4w1ckZL2Hvk) |
| 23 | 84 | +1 | 2 | **falcon+falcon-udp** of falcon-udp+falcon+helius-swqos+helius | – | – | [buy](https://solscan.io/tx/2edzoE5yBiRd86Af4E7BbUiqr35CWRxNBKTkxVQ2RBwvDshigDAHwUqhRKLaPeRn5sH5dQrMjGdYt8hUeNcb1HA2) [dump](https://solscan.io/tx/4EYKnMo76RLcvvFK7KGg9DbdqxHvBZ4zU8tTFoineVZgKynqDXX19bSBq7R8q5A7ZwJNtgbUEVR1yFjNx636XUnD) |
| 24 | 80 | same | 3 | **nozomi** of falcon-udp+landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/5J6B6z6bnPQCYLY6rrS2ByRJJ8nq1ZMzW4kqA1zX18WDYLJxYHUvhS1A1AfZGbWKgw52MHMyv1teu5bYgHXw2qj3) [dump](https://solscan.io/tx/2B2zUpUv4JijAfQeUztiKFWxo1CcHDkE9KTsiY3WSJVX5fdzmPmzq8ZxBzXBiwqJs8iLteuYgRYhjji7FdrCG8wf) |
| 25 | 41 | same | 2 | **nozomi** of falcon-udp+landx-fra3+nozomi+falcon | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/3gNXdgrcgynfS3KqHkBLe3mQosLG1v2dxwoXqMfHvhMeTvipCdmPyqxCXdo1XRZwbPYj7AYvc72wKnFqEzgDLWhB) [sell](https://solscan.io/tx/yzUiTNzpETfjZvHisXDmUVYk8ChQgiK52qcn6hp2ciMtAJ1ev3TkQgxLDggXoiopa5jxXimVYpG4E6csDQytP5i) [dump](https://solscan.io/tx/5FAjc4pRYkT3hvSCjKw8nRVe7LDhhkqRUM2D9qxHXNVxBcHsqUznxGECpYtNtCHUoDHyvnH3iMHhGiVnLwFk9JqS) |
| 26 | 15 | same | 3 | **nozomi** of falcon-udp+landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/3PU1HqT6EfJgUXTGZyoF2e5rAQFSxVrnMeVXxU1dRrB7S56rqtwisqBRZFM1YNLiFnD3bGC63sWcRGrnHewADcHD) [dump](https://solscan.io/tx/3GFfw1NWYxhASpXTqDEseAuyQ2yaxaDFJfFGb1ZDqj8q9f8agc6Q7m6vGWuHn3vYcxtFvfKkrqTdizWY6DuxmmCF) |
| 27 | 52 | same | 5 | **landx-fra3** of falcon-udp+landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/2Kx76dYe8kJNRfKoF6YNBZSYnEPqfcMm37CFuT5hEjke4nnUNqTxKr4LcztNmzEBc2WwPgNJMGihJzcKG8CrmSeC) [dump](https://solscan.io/tx/2ZAi6eSdy3eJPWr7cwR6nZ5EN9jFXZ3c1ufpVTXUMZ5vunTaKQPPazzm83vCSEpAdY1yMb4iVGVBzxGbjW3aab7g) |
| 28 | 76 | +1 | 1 | **landx-fra3** of falcon-udp+landx-fra3+nozomi+falcon | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/58ADmktmXVxGWtDRjasvos8qM6CUyQdSe2dgwfuFL3VJwLAj1cfjwAdHUMZsLazWTJ2ze3FZvrPqRCMu6RQGi7gh) [sell](https://solscan.io/tx/3hZsrNmkWYRdFNvsqdrHF1FNgY9ATFX7ii8dJ6gMuxb5cNdA9eVT2ShcMs6n45VpSUGqs88S73wrLkS5kwNfnxWx) [dump](https://solscan.io/tx/4JBgs54KcTmFqstU6LJvdpYuiBpiqN8PaCTKpTeqoRgLtUVDhU1jd3TkrA8GJ7oWqCq8qXMw2zAyykbFR6Mpg2mi) |
| 29 | 144 | +1 | 3 | **nozomi** of falcon-udp+landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/5X98GbFAPqwPk8TfY6Qu7xEh3mUWwnNsCtJbb3fTTZ1KzubMCMgUZDx2ZsLTuMf84oUKCcZVk2ryAozh1HzrtpSN) [dump](https://solscan.io/tx/3pE3bzGy6ZUxjQ847LFcMYHhss6WU9jNvE9K6GbSHVrYKMjGMJ1dAAf8BKaVmUeSxPRMwyRzhGe7XnBsXTDRqT2h) |
| 30 | 35 | same | 1 | **nozomi** of falcon-udp+landx-fra3+nozomi+falcon | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/5WqAvqtmsJFdgoqCLkzxMrSgh1JtbVm8ybYr2a8tdWo74zAjVkrbetfohPghoM1XxsfjjGPgjaByr5w1BYWxXXyX) [sell](https://solscan.io/tx/2jg5D5pDwbapcvxrGNaj55SrzqnsVaBQsLpQ2Ch9is6Ms9TCMVcQP8zWbfJE7tV8wmYRDJpAyvaxYyoCKPGnQv2K) [dump](https://solscan.io/tx/3N8QN8DbT69TCruaJJZCNrDHgh2vW1jmsrcEPLWddn1PNpkj6gxErbwQLYc1Z6Q15UqVL78WgWH5irCaUZP5FhD4) |
| 31 | 133 | +1 | 23 | **falcon+falcon-udp** of falcon-udp+landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/219EcD2C1iFcazCs7upAGkXJTjq8283KC6rYwRbuMTHCBqtzcVvrQETfcr7E7CMBkXr9yhvZonmaUo7Y6Wab5tth) [dump](https://solscan.io/tx/2E41qxnSSYxD12eBogmbiWmFJfuAEJuSoP6b1paZBS4mhfS144coqujeD7HZsf4tto6osfqwzaismv9brMB1PDvY) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Harmonic | 17 | 8 | 47% | -0.0174 | -0.0016 | 4/8 |
| BAM | 7 | 3 | 43% | -0.0474 | -0.0151 | 0/3 |
| Jito | 4 | 2 | 50% | -0.0553 | -0.0272 | 0/2 |
| Firedancer | 3 | 1 | 33% | +0.0065 | +0.0075 | 1/1 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 28 | 12 | 43% | -0.0957 | -0.0073 | 4/12 |
| dev list | 3 | 2 | 67% | -0.0180 | -0.0087 | 1/2 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 21 | 9 | 43% | -0.0298 | -0.0026 | 3/9 |
| next block | 10 | 5 | 50% | -0.0839 | -0.0163 | 2/5 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 00:00 | 14 | 7 | 50% | +0.0165 | +0.0029 | 3/7 |
| 01:00 | 17 | 7 | 41% | -0.1302 | -0.0179 | 2/7 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 14 | -0.1051 | -0.0075 | 1.4 s |

## 8. P&L leaders
**Best trades:** 47mAqN +0.0576 (Harmonic, time-limit, score -0.65); AzW2Sw +0.0486 (Harmonic, time-limit, score -1.20); Ge5NLK +0.0331 (Harmonic, time-limit, score -1.51)

**Worst trades:** 5zqq8j -0.0652 (Harmonic, time-limit, score -3.35); 3LR5iA -0.0505 (Harmonic, time-limit, score -1.15); 59uDru -0.0496 (Jito, time-limit, score -1.06)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `pSo1KZXg` | HarmonicFiredancer | 1 | 1 | +0.0576 |
| `EvnRmnMr` | Firedancer | 3 | 1 | +0.0065 |
| `JUPiTERr` | HarmonicFiredancer | 3 | 1 | +0.0041 |
| `3iSQtPgk` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `5XKJwdKB` | AgaveBam | 1 | 0 | -0.0005 |
| `5ZqveVff` | HarmonicAgave | 1 | 0 | -0.0005 |
| `YuRBAsy9` | AgaveBam | 1 | 0 | -0.0005 |
| `FNKgX9dY` | HarmonicAgave | 1 | 0 | -0.0005 |
| `8yjHdsCg` | AgaveBam | 1 | 0 | -0.0005 |
| `shftkxns` | HarmonicAgave | 1 | 0 | -0.0005 |
| `3ytgyJXp` | HarmonicAgave | 2 | 0 | -0.0010 |
| `E1r4Psq8` | JitoLabs | 1 | 1 | -0.0047 |
| `9jxgosAf` | FireBAM | 2 | 1 | -0.0053 |
| `Fd7btgyS` | HarmonicAgave | 5 | 4 | -0.0065 |
| `Cu9Ls6ds` | AgaveBam | 1 | 1 | -0.0133 |
| `CQdLgwkm` | HarmonicFiredancer | 1 | 1 | -0.0190 |
| `11AMA4mn` | FireBAM | 1 | 1 | -0.0274 |
| `HnrXmm65` | HarmonicFiredancer | 1 | 1 | -0.0505 |
| `HEL1USMZ` | JitoLabs | 3 | 1 | -0.0506 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1601 (p25 1286, p75 2037, n 31) |
| Executed-feed lag behind first sighting, ms | 2.9 (p25 1.7, p75 4.7, n 31) |
| Buy sent → our tx seen on the feed, ms | 40.8 (p25 32.6, p75 76.6, n 31) |
| Fills: our buy seen on the feed after the dump, ms | 48 (p25 41, p75 78, n 14) |
| Guard fails: our failed buy seen after the dump, ms | 52 (p25 38, p75 84, n 17) |
| Fills in the dump's own block | 9 of 14 |
| Guard fails in the dump's own block | 12 of 17 |

**Which copy landed (nonce fan-out):** nozomi 16, falcon+falcon-udp 7, landx-fra3 7, bolt 1

**Send-path answers (FAST-ACK lines):** falcon 28 (median ack 0.4 ms), nozomi 27 (median ack 0.4 ms), helius-swqos 11 (median ack 0.6 ms), bolt 7 (median ack 0.3 ms), helius 5 (median ack 0.7 ms), staked-rpc 3 (median ack 9.2 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 3.01 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 8yYMhuYo | 11 | 6 |
| 8PgC4ngp | 7 | 5 |
| 7PedQZmc (untipped fast) | 5 | 3 |
| DF7eRXHn | 4 | 3 |
| GKd5EMzR (F9 scalper) | 3 | 1 |
| 3MHgGwdL | 3 | 2 |
| BUkpShoE* | 3 | 2 |
| 8GPTNX4j | 3 | 1 |
| haqq (dip bot) | 3 | 3 |
| 9pQQc1xy (bait follower) | 3 | 3 |
| 4A1AVd1m | 2 | 2 |
| 3Kcgq69S | 2 | 2 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.0630 |
| Pump fee on buys | 0.0605 (0.0043 per fill) |
| Pump fee on sells (residual) | 0.0613 (0.0044 per fill) |
| Buy tx fees (base + priority) | 0.0071 (0.00051 per fill) |
| Buy tips | 0.0140 (0.0010 per fill) |
| Sell tx fees | 0.0085 (0.00060 per fill) |
| Sell tips | 0.0168 (0.0012 per fill) |
| Failed buys (tx fees) | 0.0086 (17 buys) |
| **Result** | **-0.1185** |

Buy compute used (fills): median 76,904 CU, max 88,905 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ start refused: Error: keystore: wrong passphrase or damaged file
- ⚠️ 62 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ big loss 5zqq8j -0.0652 (time-limit, Harmonic)
- ⚠️ big loss 3LR5iA -0.0505 (time-limit, Harmonic)
- ⚠️ big pre-send loss GoJWMx -0.1291 (stop-loss, BAM)
- ⚠️ big pre-send loss FnkjEd -0.1053 (stop-loss, Jito)
- ℹ️ wallet change -0.1199 vs trades -0.1185: gap -0.0014 SOL — about the fees of the 324 pre-send tries never seen on our feed (up to 0.0017 SOL if they all landed and failed; inferred)
- ⚠️ Self-competition from 01:17 PKT: Amsterdam run 20 ran the same live pre-send; nearly every pre-send fill was bought by both servers in the same block (the second buyer ~2% worse). Doubled losses on dumps that did not bounce (FnkjEdN2 −0.105 here, −0.116 on Amsterdam).
- ℹ️ Two stop-loss fills crashed far through the −20% stop (GoJWMxo3 −0.129, FnkjEdN2 −0.105).
- ℹ️ Falcon UDP vs HTTP cannot be told apart on chain (identical signed tx); falcon landed first on 3 of 9 reactive landings.

Checks passed: every reactive fill was sold; every pre-send fill was closed by a sell; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Recommended / open:**

- Owner rule from the race: pre-send only on Frankfurt; Amsterdam runs without --presend-live.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r21.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r21.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Pre-send (section 4b): the jsonl presend_live_* records (fills, closes, REALIZED, account closes, stops, end checks) and presend_attempt_land (try results, failed-try fees); the log's PRESEND LIVE lines when a run has no such records.
- Engine sessions in this run: 1; refused starts: 1.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

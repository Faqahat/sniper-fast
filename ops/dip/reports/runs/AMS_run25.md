# Amsterdam run 25 — dip bot run report

*Live: pre-send LIVE 0.34 (k 4, 100-fill cap) + reactive M2 0.35 + routes v13 on dip19 (same as run 24)*

> **Verdict:** +1.137 SOL on the wallet (3.4964 → 4.6331). Pre-send: 95 fills (60 wins), realized +0.952, rent back +0.143, failed-try fees −0.051 → +1.044. Reactive M2: 35 buys, 13 filled (5 wins): fills +0.106, failed buys −0.011 → +0.095. The owner stopped it at 06:09 (Ctrl+C), 5 fills short of the pre-send cap.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+1.1391 SOL** (wallet 3.4964 → 4.6331, Δ +1.1367) |
| Started (PKT) | 2026-10-27 02:58:37 |
| Ended (PKT) | 2026-10-27 06:09:25 — stopped with Ctrl+C (SIGINT) |
| Ran for | 3 h 10 min of 720 min planned |
| First / last buy (PKT) | 03:00:15 / 06:04:45 |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 35 → **13 filled**, 22 failed on the +5% guard |
| Fill rate | 37% |
| Wins / losses (fills) | 5 / 8 (win rate 38%) |
| Per filled buy | avg +0.0081, median -0.0046 SOL |
| Fills only / failed buys only | +0.1057 / -0.0111 SOL |
| Reactive bot / pre-send live | +0.0946 / +1.0444 SOL (pre-send: 95 fills, realized +0.9518, rent back +0.1433, failed-attempt fees -0.0507, 60 wins; see section 4b) |
| Best / worst trade | 8s2ewA +0.1498 / 2Ew1GA -0.0305 |
| Fill landing | median 37 ms after the dump (seen on our feed); 10 of 13 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip19 |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.35 SOL |
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
| near-leader gate | 120 leaders (buys only when the dump's leader is on the near list) |
| pre-send | LIVE: whale >= 6%, 4 tries/slot, 0.340 SOL, limit x0.88, route helius-ps, caps 100 fills / 0.1000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 500 fills, 1 open at a time, 720 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 24**:

- no setting changed

- Restarted at 02:58, right after run 24 ended.

## 4. Timeline (PKT)
- **02:58:37** engine start #1 (session with 35 buys)
- **04:46:50** big win: 8s2ewA +0.1498 SOL (time-limit)
- **06:09:25** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 4b. Pre-send live (pre-placed buys) — separate from the reactive bot
Buys pre-sent after a big whale buy, before any dump. **Not included in sections 5–11**, which cover only the reactive dip bot. Realized = the engine's PRESEND LIVE REALIZED records (chain txs of each buy and sell; the buy pays the token-account rent). Rent back = that rent returned when the engine closed each pre-send account after the exit (dip19+; before dip19 the sell closed it and the refund sat inside realized). Failed tries = fees of tries that landed and failed (6042 price, deadline, …). Net = realized + rent back − failed tries.

| Session | Started | Size / fill cap / fee cap | Tries sent | Fills | Wins | Realized | Rent back | Failed tries | Net | Stopped |
|---|---|---|---|---|---|---|---|---|---|---|
| #1 | 10-27 02:58 | 0.34 / 100 / 0.10 | 10,489 | 95 | 60 | +0.9518 | +0.1433 | -0.0507 | **+1.0444** | run_end |

**Try results (as seen on our feed):** 6042 8,449, deadline 1,280, unseen 491, ata_exists 129, ok 95, buy_6005 45.

Tries never seen on our feed: 491. If they landed and failed they cost up to 0.0025 SOL in fees that are **not** in the failed-try total above (5,120 lamports each; inferred, the engine does not see them).

**By exit reason:**

| Exit | Fills | Wins | Realized SOL | Per fill | Median hold |
|---|---|---|---|---|---|
| time-limit | 71 | 38 | +0.0879 | +0.0012 | 0.9 s |
| take-profit | 23 | 22 | +0.8847 | +0.0385 | 0.7 s |
| stop-loss | 1 | 0 | -0.0207 | -0.0207 | 0.6 s |

**By leader type (the slot leader where the fill landed):**

| Leader type | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| BAM | 39 | 22 | +0.1203 | +0.0031 |
| Harmonic | 30 | 22 | +0.4965 | +0.0166 |
| Jito | 21 | 12 | +0.1693 | +0.0081 |
| Rakurai | 3 | 3 | +0.1257 | +0.0419 |
| Firedancer | 2 | 1 | +0.0400 | +0.0200 |

**By hour (PKT):**

| Hour | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| 10-27 02:00 | 1 | 1 | +0.0082 | +0.0082 |
| 10-27 03:00 | 28 | 18 | +0.3256 | +0.0116 |
| 10-27 04:00 | 28 | 15 | +0.0633 | +0.0023 |
| 10-27 05:00 | 32 | 23 | +0.5106 | +0.0160 |
| 10-27 06:00 | 6 | 3 | +0.0441 | +0.0074 |

**Best pre-send fills:** Fazxg3Qc +0.0846 (Harmonic, time-limit); 7ubNV9gb +0.0785 (Harmonic, take-profit); mj1swJMW +0.0745 (Rakurai, take-profit)

**Worst pre-send fills:** Cxoe53DG -0.1062 (BAM, time-limit); RKor5TpK -0.0752 (Harmonic, time-limit); 5FFhP5PU -0.0504 (BAM, time-limit)

**End-of-run checks:**

- session #1: END CHECK 93 mint(s) read at confirmed: 0 sold now, 0 empty account(s) closed, 0 held / 0 unreadable (per mint: none 93)

**Every pre-send fill** (time = fill; whale = the trigger buy; P&L = realized, rent back not included):

| # | Time | Token | Whale % / SOL | Slots after whale | Leader | Exit | P&L SOL | Links |
|---|---|---|---|---|---|---|---|---|
| 1 | 02:59:11 | [FjMSrL](https://gmgn.ai/sol/token/FjMSrLgL5ZxTcaedk4xGbvEM4XgorZry4mafGyxNpump) | 6.5% / 2.44 | +3 | BAM `jzDsim` | take-profit 0.7 s | **+0.0082** | [buy](https://solscan.io/tx/3ZG95MGdi3WQXJiSHtSKArJyPpnKCLd7sdRvoL8h2vqQ9jkbseNjkbPnUVpRuevYR6LPB2kTE7Np7E179EhGs9Nn) [sell](https://solscan.io/tx/54CHUUrk7AupVXxUjTv3PgQk76BzHwgLFVQNtjaFAhjbVFtZNMWu6zt2qa45zF8XbfrfBZe5BtLr67P829zYiaNq) [whale](https://solscan.io/tx/5E6TDxZooGhnmWEfSTVdwfbqkeQcaFER162dNeoQiE5afAVb5nUPReY1BttKduar11XZ133WVPwjtHVnNR2bVxjo) |
| 2 | 03:00:10 | [5FFhP5](https://gmgn.ai/sol/token/5FFhP5PUeLg3Y8fAMgL1cLryVmtVT4T4PLk8srKM61RL) | 7.4% / 4.94 | +5 | BAM `2GUnfx` | time-limit 0.9 s | **-0.0504** | [buy](https://solscan.io/tx/sHjogoypTEtSS8eTFvwtaGwXHqywQAiq9Byaqu1F2m1V62AMB9LtAoYbmwNoM5FH5Mznxkci1WphcGcmytwdVPz) [sell](https://solscan.io/tx/RoN4hLPhMmhF8HL3rptJSzoHZyjsvtkyVh73TSDX1xnsW3nqPVB5BggjyPA847XRYutPLE4vX1i3BfcQj7THrUY) [whale](https://solscan.io/tx/2QtzodTCnUcLJM1t1KZZBdZyArU5g54AzfDZjqLCn1kt7t3YnZ1cuDDQ2SqiS1qw9Eo1N4bUupXgQJ9MmKePJs6t) |
| 3 | 03:00:50 | [2YNYmC](https://gmgn.ai/sol/token/2YNYmCCDarrSYiJmdMS8RN56SHeyHXWYrW5RN6BKpump) | 7.7% / 2.88 | +2 | Harmonic `A1vqhA` | time-limit 1.1 s | **+0.0085** | [buy](https://solscan.io/tx/LV3znrRoHYgT3XLRpr2a1k3XymdtAyk7swURPcv6jfdUeFcpeMJQ1YQCCPTR6G3bjrgK8QxzauvsdNGXBJd4VZ8) [sell](https://solscan.io/tx/yrs1hYesur78HNXupRwAqtrKcKS12V9ds9cX6rK3XJuowb4yCuNuKQPLsrUXqJu3hQSn2L2KWuKXxrZoGNQWCf1) [whale](https://solscan.io/tx/5ErtLkQucnJUdPpswAAfvosjmnAUSE8UxZbZAn415jwZGXaPeFSsfgzgyitcUaBDGfAfVvKBJw9XPa6Z1CvP8YFe) |
| 4 | 03:01:32 | [HMYtyF](https://gmgn.ai/sol/token/HMYtyFWAXkNW9jhpbZBHx4NszT17jJSFSgpnrE1rpump) | 6.3% / 2.96 | +5 | Jito `Chorus` | take-profit 1.0 s | **+0.0316** | [buy](https://solscan.io/tx/4pe9NqoPk2SuTaaXXn7CprLi1xRRTDMYvw5bqvXRVgz7EVgtEsA7GbFew1Qseij834sdzVQt1wBXh623dP8AJrca) [sell](https://solscan.io/tx/25gi2dBAD6X8NCHet51iukeTeogLhzBwv6ouJFX4JGBJ8rADMGCGwzLfexvJRFBjVioFkZGMEveBEibL9QFCUg1e) [whale](https://solscan.io/tx/3p1Qdq6SPUfGh5nYsephx8ptkB9DzXo4yZ3pbJWP8pe6QgFbGkAowPTJxubU1sbKciwKn1QqUL9BuzniJuVbnQos) |
| 5 | 03:02:37 | [EjrniH](https://gmgn.ai/sol/token/EjrniHmJHnycYZFwxQas1RQ3pPfH9S6tMNAbB71Gpump) | 6.6% / 5.93 | +1 | Jito `C8Bey3` | stop-loss 0.6 s | **-0.0207** | [buy](https://solscan.io/tx/3Mk2sY31w3J638CXFxA9stbKu4vkPHVSGTmedg9EV4nn7MXK3CTAp7GzEnUv5wJFigPi2ojvAQz18HFzgTesJRpT) [sell](https://solscan.io/tx/4XFvuYnvwfeD3FdeyfRG2DkAEbUxJdUnXtdqqJp4eU8hbHQZbtTpt9KMY1cGakaSM4pBX33TYyAVBunLc6jMTeLu) [whale](https://solscan.io/tx/5TtpFGXjPpNbbL6gGPh5M7vN1PEubkcqX6S6yGHfJgXH8XCwBmKmTzsEzjT5KaGMcR9qjF6zup2zVScToG9rEG1S) |
| 6 | 03:07:29 | [EGHeVu](https://gmgn.ai/sol/token/EGHeVuPQvcPNQSzBjsN187961kV9rLQBN6YdNUBJpump) | 11.8% / 3.95 | +5 | BAM `2GUnfx` | time-limit 1.1 s | **-0.0162** | [buy](https://solscan.io/tx/2zPJP7W1bJte7ngdC21eupJPvisPvWK8LgwiDGNAkmgDr7WbTxfR9isWMYEFqshWhVnCbxqUykn1vbr5j8cnUDWd) [sell](https://solscan.io/tx/HqDd4di9VeBYrPan68zRqcZjgfdWwwwBDhdsyZZTXpDKR7q7iZiHFMsPczahwX8E6Eg55p8jYFfkWujyiFfuLSp) [whale](https://solscan.io/tx/3VkYNZFozJWxjPAsrivEkDgX3m1G2DueQwvDPMebpVnLe6NcqMvQdfsHghu33z1HD3jF9Qw91nMUgV9Y8vAyEKCY) |
| 7 | 03:10:02 | [8uUYMb](https://gmgn.ai/sol/token/8uUYMbMttzJU16q1YNJABKUWUyMkSt5pU7k61k46pump) | 7.4% / 2.93 | +9 | BAM `GmCxjm` | time-limit 0.8 s | **-0.0049** | [buy](https://solscan.io/tx/kitMtDfBAo61Pn9FZWVez1gpFeC3smyLriRVbE2fxEHLc5XJxhAyXYN2VKX3qD7XzVMA711FpisSgX723SdGD5s) [sell](https://solscan.io/tx/4dwwVnGZFxweabFQw55TPjULdFpAmKLUU7RBAVJbCk443pVU57RoAU5cSBTwRb6ivu1xM7Eh6LfzcXnDV1h198DT) [whale](https://solscan.io/tx/4RYpjMMB7RmC7syFPoyViN3VRmK1JDzSgprVaJoAcE79WZdN2LB9VY2vwYjkT6LKwaFzxCVS2XCjAAFjpMZwMYCr) |
| 8 | 03:12:59 | [CFiMPm](https://gmgn.ai/sol/token/CFiMPmT2AXj2c1qw1mo6b785k8fCUHMY3F9Qy9cCpump) | 8.2% / 3.29 | +4 | BAM `8uJiHD` | time-limit 0.9 s | **+0.0205** | [buy](https://solscan.io/tx/5Xhw2xCcbaMBmXQMxsCsyyGdskEvYVmuWw4Bebf522x7qh6ZZnpd57WQyAumgGRckLpQy5Z9ZDAFSCij11nUyRK6) [sell](https://solscan.io/tx/2jjDeAzcdmPM3XDknpZhxEMDny6K1NnwzQ7hYLdjXEa6U46NWtKkd74yR5VFDqqX8j32Fxc5MMC6gM1Q1kqDXxqy) [whale](https://solscan.io/tx/3NMoVKbaKZJ1A3R8fM8LLhRVUv4YtWBTiFR9k9C669xUyhDnB8VCT5Sho9jyG7FeNKv4PqXiKdu9eB73WLiNopgt) |
| 9 | 03:17:34 | [7ubNV9](https://gmgn.ai/sol/token/7ubNV9gbXjNJNZAf2tyEYiBvPxVBQNGDBFvwoeqDpaid) | 7.5% / 3.26 | +8 | Harmonic `GoeW4a` | take-profit 0.7 s | **+0.0785** | [buy](https://solscan.io/tx/5XByzAEeYPmp8C3c3kKsY9Rf5irB8CcBUhtNz4o2NsR8gRcSvkMcswQeNqLCtrndrxHE5LHRymrpiDSwobJAchQG) [sell](https://solscan.io/tx/JZJdsx5w8GKo8Y7rFf988bQSExZJeCgXFRLCRqk4sdR3G3ZiJELa293b2zCLXhx69Zfsps1p1MJUzGiknhGm9nn) [whale](https://solscan.io/tx/5KLQAtvBbS8szJ1fcsocv5u4DPagaSSqh68KmwuVV85eDFsGwj2xcSbgWDndoGZvBWRKuAMG5mMNCavf4KfyvRmh) |
| 10 | 03:18:22 | [24Qxow](https://gmgn.ai/sol/token/24QxowW3QGPTwPYnidPM3rS3FdUYnzdv35pyDdADpump) | 13.5% / 4.94 | +1 | BAM `DRpbCB` | time-limit 1.2 s | **-0.0212** | [buy](https://solscan.io/tx/3tqynABGQ87giDqW5yvAa3eENkcaxHjjYSfnwJ2ZwwCLcaLXo79GwvsUimDTQ3frogrFBnhDnmD59Utzu5SdQipd) [sell](https://solscan.io/tx/qSb81M28MoV8CHmyxEwt6GCqDa73LaXHhDSRAaCjqadd6G9xg8aVLpcJ69UmUUXKJCAEWhLjkd8xv1mDNCQMmcz) [whale](https://solscan.io/tx/3E9phQvNHYdHavYDgqabGCYbtfp5wt5ATMmXTMZ5ZU9tSgFqcAiS1zqUa7HfENYfYqaQoP4Xzyhrk9XMKcQXjYPc) |
| 11 | 03:22:09 | [5vwX58](https://gmgn.ai/sol/token/5vwX58sMkchob2NKeUvF3ADFheJRE3eZ6S7oNu8Wpump) | 6.9% / 4.18 | +7 | BAM `7qGNnX` | time-limit 0.8 s | **+0.0241** | [buy](https://solscan.io/tx/58koscPXUSzfCwFRtJNETY56ULCGxeHP3c8tSbU1vb1e4tKDepokEK78P7Db8459oLfR95gmKYSRKT76KmmDAXYW) [sell](https://solscan.io/tx/4LEnLoWrDrQcZfQkG5vTfvVVeeh3SuEYmgzoKYuNqzchZKSw8kpJ8vyHfnkbuyohDBnH5VwDoz5i5XewFPg28z9r) [whale](https://solscan.io/tx/5PBiPK8ZAWb1vCQBvUe1nw9Xug26LF2KEWXHTqkSZnygExpWH4wkzukdcDiGz3qMDtmKTv5owBCoG5CVH9gAmVZ9) |
| 12 | 03:24:24 | [BdhHra](https://gmgn.ai/sol/token/BdhHra2szLK9Qr1ZSvZrq1NhbfxgxgYohExEPSHupump) | 6.0% / 2.81 | +6 | Jito `3SkE34` | time-limit 1.0 s | **-0.0231** | [buy](https://solscan.io/tx/2goNi8cbGfQzQny6sMLAkEMsfwa1fMX41MQRAjeUHuUh3bfaqKFWYQE39kekKCHxZZpiWDnFJazisRqGaDXenouw) [sell](https://solscan.io/tx/TyQ9cx7aUbF3PQbw9LdsQdYrpLiASErmYJqJ6gGBkUnPRY6zvTP3wdAYvpwQtsWVx1MThYQnoiE18U5fasB6is2) [whale](https://solscan.io/tx/4tZNEivp1osMR5E7xHH6BS29VqBvC4BzA1JgPHcbWqe333XutuCqzGEyu4J7RHxTZH6BWsFrznFu16uwiDj3sh49) |
| 13 | 03:24:28 | [GeNDgm](https://gmgn.ai/sol/token/GeNDgm87v2DTmAHSt9QvT7dmawyfaYRQahDDRxdCpump) | 8.2% / 2.79 | +4 | Jito `AEHqTB` | time-limit 0.9 s | **+0.0185** | [buy](https://solscan.io/tx/3SmzM5oqMhSHTC5aD2NmDjWHCKputmJXyWhViSjdFtC3JxYvjs8zXSpZdr5wGsPDaDnJEHvs6UbSdJ2xKaTyLzA5) [sell](https://solscan.io/tx/3c34zzpe4gbfe1j5eqwbWtPw6aG5mzp9DQZt3vDf937KeTy6GFfutg2BKNY5JFxXoNPRTVqKQURDsDEkKrBYCZ72) [whale](https://solscan.io/tx/4TjvMoHHxqEGoW8zhJthMynSpcAaaJ4RE2K9eWYGR92UaoS5Cd3GEVUrD84UpfhXb3eMrHDhAQfdgvr9WEMLmwU6) |
| 14 | 03:27:02 | [Fi9Dir](https://gmgn.ai/sol/token/Fi9DirCVnJyfwH6q7AJ73MhVEcfTr1k5PiqdkeLWpump) | 7.6% / 2.96 | +7 | Jito `Fudp7u` | time-limit 0.9 s | **-0.0119** | [buy](https://solscan.io/tx/3BbvZdy94miPBxu9VJjRcZxodR6CQ4bRJbU4Mn6zbvhaMWe7K8vt3Sd2QJ7irQPViU61AJkqwTFuJNtuac53iRdy) [sell](https://solscan.io/tx/5mViJd6yHZGEBPM97AsFythMBKky9zdYSse7dKwB7i9hq6hs4em6sJ5x7dG3MLXSJKVypPdAvBzb5nDeE3rD7Eyy) [whale](https://solscan.io/tx/wnjqnbd5eQpf1U8VRjE4kS1LJT9prfDe71MixFC9oPkKz85dpxwv8KEnzB5qh28Bfd6UsNe7XuvNSjt8Z7Hs52q) |
| 15 | 03:27:26 | [AmWxmZ](https://gmgn.ai/sol/token/AmWxmZUNUa1K7hvhuj9RMcjzm78Bq3GEXNYHsARxpump) | 7.3% / 2.96 | +3 | BAM `Aw5wEM` | time-limit 0.9 s | **+0.0301** | [buy](https://solscan.io/tx/3SUtqMy4cM7iF8217xav1m3LPSNLEtMDr5WoUDJE1SDYVctcd3EWpjYT8D6gM45dodRem6tQeoBTBK2L8XqZHe6p) [sell](https://solscan.io/tx/AB3FF2kBJo7dABTAj75mjpXdqZPPcczKYjALhCZ1KLCb7gyVmeHRmWj3pVeT7u9sg1S1sFbPxjX4qVLMG7KT6Ch) [whale](https://solscan.io/tx/2RfNK1Bf3RVTdbKDuBZtYU5nTrnbmefgfFLA8s3i2oafNrnWAQsWmP9evLLBoQ2qEp224hPAkDNQEpb9C1tEoS65) |
| 16 | 03:27:51 | [4Q5PqG](https://gmgn.ai/sol/token/4Q5PqGfXaq795Nqo9MUPJCUAp3WQNg5mCto6f2XHpump) | 7.7% / 2.79 | +4 | Harmonic `Bi9kKN` | take-profit 0.8 s | **+0.0381** | [buy](https://solscan.io/tx/5A1QUE5vmJwxkmTuqSgRCJBMnLfNnYhsAfQz8bA4fCXsn7JdFuhHyLxNCQe8DTuSsEBGPzwaHw22dn9ZqRG9ZSf2) [sell](https://solscan.io/tx/4Mhg5cTiEmTwakorBApF8yrwBUG2bs446M8crTu7U6cqXyrpPh13KQQhrnhvvx95EpBLou8rYvVuiv36Dheu3dhw) [whale](https://solscan.io/tx/3kQQXCenGPMj3jDMBsusmbQPD5m9SNMKpT4uVPQ8Q9dTaMceN4P6ey7qwBmvvh6sf23x4p6WbDuWQYBApAhR6Uvp) |
| 17 | 03:30:03 | [3tMXAQ](https://gmgn.ai/sol/token/3tMXAQi9Pm9vWnkKwdW3uuJnQSoRNDTo64mDVY82pump) | 16.1% / 8.69 | +3 | BAM `8Nvaxz` | time-limit 0.9 s | **-0.0020** | [buy](https://solscan.io/tx/4VYDfendaTR6ssefjN4X4D9iTVWju2D5r6aAa2P37HZ3GJRjqxZ7yFhoSH4eGFoEcf7kLD91M9oZ63dVZbgtajDs) [sell](https://solscan.io/tx/5fc9hwSXMYGcaS9vMEqKeWq589odgyi7GPV1RrPa7yD7wkjoLp5Fcjuyce5RVcQFtfNtAqRqTz2usLkiwnmAZJry) [whale](https://solscan.io/tx/kMjzRiLpKpveuoDiuhQS1VMpqyaSuN4rnw7HtzGRYT1uFNsYMLDnqDkumRrZstKpHwmhsf2X5wtxH78FmoAXtuN) |
| 18 | 03:32:30 | [3rni6A](https://gmgn.ai/sol/token/3rni6AAMjiNF4kTda4cvrzPsvLB2bY77VjtUxEZ4pump) | 17.0% / 7.96 | +8 | BAM `DRpbCB` | time-limit 0.9 s | **-0.0140** | [buy](https://solscan.io/tx/2WjURaJQQeSQB8oi13KRxMhXxbcMMGW1so5nx12fUs2CSzDxE5JToaWoEPuXef4k9kocu6U98PpXvAuHw8brfgGd) [sell](https://solscan.io/tx/31iczzG7Q1zWXjk9fwtA75vwEdFVB7pQcNq75ToNZRQHV58dUNuGJG5dusKKFCDpo3m8w8UVa3jhYa9yKUT39PVu) [whale](https://solscan.io/tx/4tBCdjH1coKEgktPfo9pngvBQHz6SQHDWy8gK5SbSj7UfZqitmGJuXVvw8J5yMDEU47Ztr6FscA56rFVsBrSQ5rM) |
| 19 | 03:35:58 | [DznL8h](https://gmgn.ai/sol/token/DznL8h8wJH7dYyrtLQ54kfphsG2Ft9FMs4WCE3Sxpump) | 6.2% / 1.96 | +3 | BAM `2GUnfx` | time-limit 0.9 s | **+0.0487** | [buy](https://solscan.io/tx/3vPfehJyUrTJGZeNzPcf2BtPRkmfn2F2GUAuCyt5RuTXhTZd2p6cX2bJz9MefLq1w2pX5kkgT9rnboGA8mXFi3Py) [sell](https://solscan.io/tx/59xeXuKXdTFHaSN77K4E7kujVeNF9GiiHJKZqEXzoPQy8gKrm8wuNABX7eyPyeh6BWGjHTEXHhVUTR9ogbmCmefe) [whale](https://solscan.io/tx/5xqVkwLng9pw3JZiJYpYvaJUY2c9TmR47T5K1jRJMVEmjBJuNNZpZWKLKaiA7vXkfzJBw28C9paJ6aaVAVbGotJc) |
| 20 | 03:36:14 | [97Bj7F](https://gmgn.ai/sol/token/97Bj7FEKbeQD99QYiP5iRieoAn7qacenNmRCiekHpump) | 6.5% / 2.96 | +3 | Harmonic `CAo1dC` | time-limit 0.9 s | **+0.0126** | [buy](https://solscan.io/tx/4fjujJF1vzwdkDe9oHxAKKWmhrQuYet645wfgzkjDCaiB7i8JkR2itrCEkNEqHCSF2yNkPuA1khMYkGZ55Rs3G7R) [sell](https://solscan.io/tx/5fssEZFB58DEAPnV8mRQdFr2VCpEGMmbe6Tbx78Uv7TUG8AbdCdehEzrXx9sy3n22Z5PXiikRFqLmMQohp29qDzJ) [whale](https://solscan.io/tx/4MBg9yemCPfeN24VXeM32TYN5FRTcm2fuLJYcGvrgHLaSatL4iVjRDX3kFjnsvKWVfpPQcgGa5R9zatueY462Qra) |
| 21 | 03:39:06 | [42Ly23](https://gmgn.ai/sol/token/42Ly23xwuYtvDtA59dXcjfMz3qeahKViMBiNmtrWpump) | 6.1% / 2.79 | +2 | Harmonic `9UM8wQ` | time-limit 0.9 s | **+0.0045** | [buy](https://solscan.io/tx/3ZterSkGdisTYmaxUFsZDippgtCKgA7RF4JLyQ9cwzgTqhPqdcucz2Pibfs1R2JdTccopFhez3byBm5WHHSSdbZq) [sell](https://solscan.io/tx/5jRa85s2LVQKfBXFnfmbtjtGkGXN397F9r5Ac3Ug2Bio3We8ttrccPzk7hg9Ug3XKSwuy7Wpp6yzuGdd2FdbyVMv) [whale](https://solscan.io/tx/5J2NYhScj4iNtR6bK6x4PdRzhpoPZSC6tbySJHnAkesFFaME2yc99BQvc6rX57fxgpxs1XbuFVvjEFG38mrqizsf) |
| 22 | 03:41:26 | [C4CpL2](https://gmgn.ai/sol/token/C4CpL2oWKGLt4LCQa52KHNPQr1wfYpGqo7nZjh16pump) | 8.8% / 5.93 | +3 | Jito `5pPRHn` | take-profit 0.9 s | **+0.0259** | [buy](https://solscan.io/tx/wchcRzacdmAWFFFa1GPuoeWEByVaLqUp2DYrQWGNJ2aGSBSUUUg1zeM2C3BZexshmqzfuaLBXueLYedLccZWP6k) [sell](https://solscan.io/tx/RqjoscyEx4Qa3QTkeEooVjCsFcNcjRjREVYG2py9UYQPfFgPPvjfWsKFB1kgA4ocboAYdTjLd1jx5VeQDZGpw8S) [whale](https://solscan.io/tx/5ET2vSKdv1Mi65nyQi4dog7vL5Dugz5ARBknEU3KpVguDyRstQB3hegCP9ZGdCgfA49VCKHjnKjdTpjPwFotMUaq) |
| 23 | 03:43:13 | [C3N7Jj](https://gmgn.ai/sol/token/C3N7Jj7KQQCd1cfToN61p9Asua1AugALJFakfjRzpump) | 10.3% / 4.15 | +1 | Harmonic `2mMGsb` | time-limit 1.1 s | **+0.0264** | [buy](https://solscan.io/tx/eeHTCc5iVU5YduJEhpWGSgVjZgVu3xVQ6QtbnYkxjMYpRFaS9JYqCaifMxTssMZ3fc2g7UUNeTEnApHhLWihGZ3) [sell](https://solscan.io/tx/37d7ToxgC6cHMiRpWciqx19YHuDxxDAdwdBYXZR5dgJurd91y6UD3TtoDiauxecbfp7gmz2kcK17CPkEhPc41gP7) [whale](https://solscan.io/tx/5LeLcsVGkVj338Pk11G1stZSovvknL1Y4FJmmgjpfBavxJVtUhoheYj2EnZ6WY3MVBHkzQnRHQwLQtVS5Eqo7wG2) |
| 24 | 03:46:08 | [9UX9S6](https://gmgn.ai/sol/token/9UX9S6f4m3KeqWuyw9Z5Sj8ahGpZeQC39P6i9eY8pump) | 30.5% / 17.78 | +4 | BAM `9jxgos` | time-limit 0.8 s | **+0.0081** | [buy](https://solscan.io/tx/4QTjebWS1XcVdascNJpLhGJVyCnAiZPCYX5DPtUmHpoQy5BBxqGRGWTkHRrwjz7ZgshZheMH6h8g6kkUEb6e7tiw) [sell](https://solscan.io/tx/3jNsJBhYHGJ5MynoYxvBfZ1qujxHZrQwhG2aE8Vmk7vsxXRnuPiezpPcwAahnkjbuQ1cwvKv6oYXoBuycARwyvS8) [whale](https://solscan.io/tx/64i4w5uGb8XbGWB9iQkMiDf13zgJTx6TJVtYbCgf2urUCYbdMAy7tutPdMaDKbA2BQ1bvr4hCfshfKmhPYt2nZye) |
| 25 | 03:47:12 | [HrXZgt](https://gmgn.ai/sol/token/HrXZgtu6Xop4rx1XVSUwKhdSaNQQ77iXNroSbBqdpump) | 7.8% / 2.96 | +2 | Harmonic `HnrXmm` | take-profit 0.7 s | **+0.0351** | [buy](https://solscan.io/tx/jW2psFgjjotzx5kTU4GKaM3ifbFytSXdsXHmzdkZbM19dEJvdWjaEtLv139QJVJeBTAgkzru6PQkARtN4KCd3Xi) [sell](https://solscan.io/tx/586mrz4kWX4VPMLmRYpsQDz5Rjgm4wxi16p3Ytxmz5BYd4RguvWinVaEvexgZ6De7QvyK7bzXVTbadNHHJJ2zBSP) [whale](https://solscan.io/tx/2Gn1GWSarYAPmAESV9K9M75YNjjduqQWoLfCTJzY2VtJuG5zxoQ4CSHUP41xQBzLp7wfkuJCparMYNL6shc34HFi) |
| 26 | 03:50:52 | [BXEEvi](https://gmgn.ai/sol/token/BXEEvicmS7EYXE1uCS8ichyNeR76yrT96EqJq583pump) | 16.1% / 5.93 | +3 | Harmonic `3iSQtP` | time-limit 1.3 s | **-0.0119** | [buy](https://solscan.io/tx/4EEoHvXW88yEorRCVoPiXYcyvS7GMXeJKJGDoCvYs1pMUjfbGHACLWhq8ahTCpzuMa3AGE3CVUPh5r8WQ8b1B7hC) [sell](https://solscan.io/tx/5ANrzzyz4eYdWF59i4hqPr69YPRsAnUPQ6TY5eYC8VxtHiAYvfGsXrUx9D8qncnQc6X92tFXwT1yBg8vFywf7CG9) [whale](https://solscan.io/tx/3DdBPpAbg5PV8VhHho3KxNkrtkVSfvwqUgRM7kmXaeehYHSgT9v1DZZfsFiEXLLP2QeqqfdSNXzFGkZVZqZQDDP8) |
| 27 | 03:54:35 | [Ew3Vge](https://gmgn.ai/sol/token/Ew3Vgerv6tz89JwuAv8u7XpWJ4XAQgvcGX1fCSPQoXq5) | 7.9% / 2.44 | +3 | BAM `MBVyz9` | time-limit 0.8 s | **+0.0022** | [buy](https://solscan.io/tx/4dA6qonpT9xKdNoRnpAxQrEAikhX8HpqN5WByiGTGcc3FqDuvjfn9VtNJifdBnf56KjsGBNtZtSwPeuawE9T1ZWH) [sell](https://solscan.io/tx/2b5CF5GffouTHMBHo3h5LLVT4L6mQNGkUACXYCtksWCLnvnJGzUAYvVfkZcSkSDZnQPf65R6gfPX3uCK3TyQsGmx) [whale](https://solscan.io/tx/2y6zCDQ3y177t94PS7T9G69L9eCTuxhkFQkYrmQtabQ5Kwx3Y8dXNVrQGg9GB3r5DWkLZXAFzZaByd5syLNvc4kx) |
| 28 | 03:58:55 | [7ytMf7](https://gmgn.ai/sol/token/7ytMf7u12kpyWo1hS8DFcnH55nuyuHm8v1Xktwm8pump) | 6.2% / 2.47 | +3 | Harmonic `A1vqhA` | take-profit 0.4 s | **+0.0449** | [buy](https://solscan.io/tx/33p3yHSKZmEeypUNLW9GXozPTK6qRSnr6cFKfLZgK43YFdy3KU8LDePHA7rPVj3QrTmRgVMFL4qXuAq7V5bFBfqX) [sell](https://solscan.io/tx/5rQHRhtdshDFhrpQTv2SVksToRqtGvnQ7wCoKHebcFQykJmma3Yu872U9UbmBboZZTyq881ittkNQtK5ovw6E8pK) [whale](https://solscan.io/tx/inFAyrRC59VRNRn8rCSBtMka4NRCiD6NNs6ivGtsuUwjVRywHSqmZKUETWsJigXRrpx2iab9FxD1GdMvG8d17L4) |
| 29 | 03:59:41 | [3w8Q2V](https://gmgn.ai/sol/token/3w8Q2V29yiqYbxSbZuECQLj3Sqcm1k5iyMaJ7TcPpump) | 6.7% / 2.96 | +7 | Harmonic `AicQr2` | take-profit 0.7 s | **+0.0437** | [buy](https://solscan.io/tx/23Uq81JjRZb9oy3V8jTuQC1Q1cmsgt1mYbB6GTxD3vSwB1vm91EXNqoAToe6kaeFphwFkyWhow28JNdRH5umVbf9) [sell](https://solscan.io/tx/4huqoC1U5QoAiEE52W4zpdWcVFfrFLdyKVQn2d9k4MLVPgN9Xr9P2bE9GiUeVXdQWFRhAtWYx2PW65sYrqQ9wtA6) [whale](https://solscan.io/tx/5oPdtGCwwschzCzygCyW3cnDyB4Hv19VzShkt7KUsR4n5TNAp5gUYp44AucTBvrffZFbLw9c9QZG1NJCn3vkvqmy) |
| 30 | 04:00:41 | [6pfeCc](https://gmgn.ai/sol/token/6pfeCcBcDweRsuV8UmSx9urfgvgx6nzKbotfGpz8pump) | 6.8% / 2.96 | +2 | Jito `5pPRHn` | time-limit 1.1 s | **-0.0028** | [buy](https://solscan.io/tx/2pYBZbL3pHiQH4Jm8zQVmy3QtuoPWdBfRLc38zLustJWHMPHTi3uwCPaYjare9NAp1TuEjqec6KnjQZsPwYjNfyy) [sell](https://solscan.io/tx/1ipH5oP2seFgnpuLCWB1LGJ2kMQYEnahQaDgPDHQr5NJ1MoX14ZrLACXckaRQ5Xm3K34kFA5gdNoJFF1Nd2gNd9) [whale](https://solscan.io/tx/4e4q4wmcspGFDodzzcyCSToezELCkNj9TPzXAPAYE4URtAH5aEtD9kkEPVeriEgJcNaJnAtHUbsjYKKb1dMWhmrn) |
| 31 | 04:01:52 | [DhLBC9](https://gmgn.ai/sol/token/DhLBC9yztM1hbe7d99GaiMGhzKvt6Yz6ctr6SZQZTcsj) | 7.2% / 2.17 | +4 | Rakurai `7PdKhp` | time-limit 0.8 s | **+0.0101** | [buy](https://solscan.io/tx/463jGjFfyNry8eQD2j7CPPMpdR77FNFF89ydwdqbXnJx3daE2Fm67VnzjNAx6tWyFJ1sewp83CJj6fpG3wRC1G8b) [sell](https://solscan.io/tx/2JhT4NvKQw1vvKfZfZ2HigCNUy9vfgtZDprdnJn1PhjhDTJxRgZiee5E4zbUYBSL3vjhunRCg9uih9VjzTWERUt3) [whale](https://solscan.io/tx/37eANKDd5smtWedrNc2iSnLFdzfgqpRTYDViT4qhAJEGmmAr6ADnwVoNXYDJz6KPAsLT4YMPMvrz2AzW1mrCfejA) |
| 32 | 04:02:06 | [7kzaR2](https://gmgn.ai/sol/token/7kzaR2pU5AqRBxozAemjtArFGc1ETTUSRRxVCHFwpump) | 7.4% / 2.78 | +4 | Harmonic `5ZqveV` | take-profit 0.7 s | **+0.0588** | [buy](https://solscan.io/tx/52357axmkNcc6KmVr7qJnbQTvt1r6yxf8xDzpsZCmjJHT2QSBeNKeTC9wMMB1vHTNDXm6PW3EyE6yqkxeupjDzjX) [sell](https://solscan.io/tx/55JNz6qK82sc65YM7sCHG9Zj4Bdkyk8ZxWgVKZR4RwpYYamGJkzAbeTvvVMSRYGx2Nfv3NZYNgB5icuMkwhwPTCR) [whale](https://solscan.io/tx/3mGBYjEipYKnywgC2YRzS5z5uiuwmBSxaHuxxNJaSgCvRmcfHu4KooQTbMq5AEn8npgEzdouDvQ59nfyFWaQnbqA) |
| 33 | 04:07:07 | [HrR6Gs](https://gmgn.ai/sol/token/HrR6GsS63no7gMNFQzonHmbjxnYXgNGWn9DML81LZAxJ) | 6.1% / 2.96 | +3 | Jito `Cogent` | take-profit 0.5 s | **+0.0376** | [buy](https://solscan.io/tx/3ZTdcJJzfzyLPEkwo1SXWNiWg63VdyPhDceDodWPa2cw1gnWuKdKUN3syDiKSF1FVn9AHBDzP9U1dH6KRxgpEbUB) [sell](https://solscan.io/tx/21PkpVrLJscATRsESn8U4bQNGSaaWCQdC78dLUYJM9EwJ6EHxxtr6vBziZbS6Y9NF8bwK6ePeVZSomiKVyPpnpHS) [whale](https://solscan.io/tx/FLo8ZZW7igpDh1y1ZA1jkrufjTCLVa49LXHuCjPLCe5fEURizaGaJ9FS78QQBo6Tx4oHLHzeqcpMD7ri7yxvsFY) |
| 34 | 04:08:50 | [8bCfmA](https://gmgn.ai/sol/token/8bCfmAKexEM4dT9TzjAVZj1D5gXEXMRqcCkEqy3Cpump) | 6.1% / 2.96 | +3 | Jito `HEL1US` | time-limit 1.0 s | **+0.0051** | [buy](https://solscan.io/tx/3RgBoM8MGZxFxjtGgRRSrbFx9KcYxRk175RMxJAxkPUZT5u3eACRyBXasDBnbuRXuqeA6Vz2Fhjde6ni26yH5azP) [sell](https://solscan.io/tx/3vgqWQf68Gc6gATkAm321yyj39oBfAkF91VfgK2nVmLpRCZyiBcaRHCMfpYXKz4euu2bqH7jLPdVdZPvGyxy6r13) [whale](https://solscan.io/tx/4BbtfuUaKRFzHcLuKVHtaC9U3hPKUVTtK8eke7nTFxqMSmvHFWXF3m7oLokxkWQDSui3UqVSC4SQQHu9yj7NM4kh) |
| 35 | 04:09:21 | [GjBd3o](https://gmgn.ai/sol/token/GjBd3oqnwwp6KN5MopVkxb3mgGXu6Y5MKYJCVSGSpump) | 6.0% / 2.96 | +0 | Harmonic `2m1A2W` | time-limit 0.9 s | **-0.0119** | [buy](https://solscan.io/tx/EZWFJDFsZx658UtESLCBjwVqxiaZQMXUPtZhEDEv9dB4bMfBXGCjHkZcKhxkbtnh2YZGy4uBjLuSBtv4zt6pjg8) [sell](https://solscan.io/tx/4DW3eouqy69RBiPZqKgW7qjtDsAo5naEVoPcPP2Mag5R5VxXmSbQAX5AyWe75ZzJRhcmNZmPWapnMHWqz7Ata1Ju) [whale](https://solscan.io/tx/2F338TinTHFSdrbQB9vaUuHZLcwELyHNaDsNJhPhZ8xkxeKYVgBa4x8W1NJvoeeea9d5p1gq29uZrFYTMFSRQLcq) |
| 36 | 04:11:51 | [GcP31y](https://gmgn.ai/sol/token/GcP31yEMw6NT9uou9YfL3YYYe4u5mCYsj4JusgpZpump) | 30.8% / 19.26 | +1 | BAM `9AW87W` | time-limit 0.9 s | **-0.0054** | [buy](https://solscan.io/tx/2yD3iZKVu1EyBebH9p5shWU4FvsTjaFuZd5wXiadSWWaAAXt1qpSKPwTzLxzo6fGcY8M8uSY3cNRBaupeDZkT3RE) [sell](https://solscan.io/tx/uhR6ZgmrVj7WbCRSsRsJFdcsvjCruSeQCFb3keFvGTFunkUXia46C4V1XrpbrBJ7hfqEsxe9y7JS3v9zWrwaG5N) [whale](https://solscan.io/tx/3AANCaC31gifuHtZk4Z1McwtWrUyTrpRNvjhcp3m8xpGQyQJMnCx6hBR1j7MRcrtHNwj2VFT2oD8YdEZ957fNKn) |
| 37 | 04:12:15 | [FoU1BZ](https://gmgn.ai/sol/token/FoU1BZsseaDNWiVrJ1n9Ypgys3mVNMBqkVW6oZYipump) | 11.8% / 8.20 | +1 | Harmonic `AMukCL` | time-limit 1.3 s | **-0.0116** | [buy](https://solscan.io/tx/BfAz29cwaSKFNY1xqmGgv2qqTGj2SCTVxD2tKtjRcPd78NxYf3Snfd6LRst8pYL4HmcPKGUXrMyPkp4BJskPbja) [sell](https://solscan.io/tx/26rQTdTt2Wd6EiFeuBsHeVBAgucgBRNxdq8DGFWFV3CBXhJVYJqVNRSypDeqf9jok7LBCW9DuX7shiie5oB7qmQ7) [whale](https://solscan.io/tx/2RCzkuLdnBrfpMgsU6PAwjDjPVjjVAADJ3MhQiDnQBWvafGztj2nNt4yG6SdDpqCiGLhVtMWCN5UmKWngBvzUaiv) |
| 38 | 04:14:03 | [AvR7dt](https://gmgn.ai/sol/token/AvR7dtKohBgg4jb83w99gyP8yMH6pHKQxc1ZJAhTpump) | 16.8% / 5.93 | +5 | Rakurai `ana2y2` | take-profit 0.7 s | **+0.0411** | [buy](https://solscan.io/tx/4Pt9okULSRuZ4emoBa3HPqiZRyeqig7F6NZSk6x8m1GxbVDddhp2VxputtxL7PvpGR7cauNvJCH7GWpJW1HCV2s8) [sell](https://solscan.io/tx/u9BuMWZwQJA273TNjuG9SKbofeAA3Q3Qv19X6bCSug5AyQ7W9ErAUdvWeY535pgaaB8THuWcTgKhPTKy2vnHcsL) [whale](https://solscan.io/tx/3oRE4Tz2dUW5tdHw2ACSZ6mL4rJkV3xdHaRySxe2t3sBJ12fvXMT5MnBQHxH2us85AhfK3u8ioiRYCW5tffb9u84) |
| 39 | 04:14:56 | [GmjuE3](https://gmgn.ai/sol/token/GmjuE3EERvgkse7up9fvZ3op3tC7DtRPwzFsXs87pump) | 10.5% / 5.93 | +3 | BAM `DRpbCB` | time-limit 1.5 s | **-0.0119** | [buy](https://solscan.io/tx/2Xw9c7xq96j3hxJnvAvjVPpwuPR6DA9V6nC4HhhcPqQtTtQ2MkWYxhbHc2hJTbzVbQ4y3vNistZ9zvi5e98bCiVq) [sell](https://solscan.io/tx/2XmsQoaKvf7HqkP753McXGS5FtC7LqtMxz1bqgM6FVAiLdYuZFse8QudZxTm2yrT1151JUc3cWSzxu5AMWLcPTCe) [whale](https://solscan.io/tx/4z81Q6tidtbcqahF3xcySXyeMHtyDCehSG1LU6ivjqHcj6FvGZeFDE5zF36fVoK9W1m9yGDCdDTAowunAY3SBobv) |
| 40 | 04:15:40 | [G6CufH](https://gmgn.ai/sol/token/G6CufHbtG2EtRQK3SnFfCJsybL6SXf7zexGxRmTWpump) | 9.9% / 3.25 | +11 | Jito `Fudp7u` | time-limit 0.8 s | **-0.0051** | [buy](https://solscan.io/tx/5fNvivMnPcyfNWkFHGzmo52WuXH7HGkdKj7EunfeANdRgoQGURVv3xAxPXHd2FrhsxZRUsrbReUTzW4wJAWjdaAt) [sell](https://solscan.io/tx/5VKxmVURFC9HUfnXs3t6bmDJGq1yDGcuND9mv7QKXNf7hkdhg1r1DV6re9sD34h8EnKhUVL6VdUZwgAPpMxp8iFo) [whale](https://solscan.io/tx/3ymEtqRJHQzf5Agp7NZsNbtAiFuZSaX5A2YrKrNrrViA9TxKDY3SJcbBNyJ7UiGc34bth4puP4e94zaeeQHqP3qm) |
| 41 | 04:17:18 | [Gv86PS](https://gmgn.ai/sol/token/Gv86PS44Aua29HZqupL1SyWC9x5c4gGQUgzDssq2pump) | 7.4% / 2.93 | +8 | Harmonic `BtsmiE` | time-limit 1.2 s | **-0.0119** | [buy](https://solscan.io/tx/4EfmBJ4oMV9H2wvTNzfNtkpQ9r1G3XyJw5pKdvtATqCU15HAJz9M9HR81z3d2EARnTVi2Fok7F2kjvmpbFq7TheH) [sell](https://solscan.io/tx/53zTCWRfoB3q7vgkRACVukSaAbb8sgX17RqDgduvccCs99xfMdkcCLd4kPQcwxUfvdXnbQKHfLdYhvka8dedCiaj) [whale](https://solscan.io/tx/y9cCDLTEGZYkWzNZB16A9BTHXHL4fn6phjhAJB4wZkEKqHd7pM4i5su3tBv4vWgmTDW4YRFEGj3ZGZtcUSLiG2y) |
| 42 | 04:17:56 | [BVUHbC](https://gmgn.ai/sol/token/BVUHbCkTY6dEzpNk9ungidK23ff4EbmHqguXZZXopump) | 6.8% / 2.96 | +4 | BAM `9jxgos` | time-limit 0.9 s | **+0.0259** | [buy](https://solscan.io/tx/2A2aaiKStFBuQrSw91EMKFi9Q18nXY4pcGnJ28HfNtycsCuUZZwo7WvJz5YmCjCn7H56XpGWsAiMPa8ZZ5HPH2qV) [sell](https://solscan.io/tx/3HPEt8Zpb1aty7qb7rXG12ED1KevPKaiX5BEJ1y1WhvPcJAXWth92JBprD9wXLDR9M1uj5WUiWiacgd3mu99z5PU) [whale](https://solscan.io/tx/pKnbejDqsmeU4uiUq5fXRcWYXpeUBcrGeE1rTKq7tpXHD4uo33rJyVuFNwKUS6rq7tywpoayZpq8ioTXSjPoUrN) |
| 43 | 04:20:39 | [CkGvuZ](https://gmgn.ai/sol/token/CkGvuZGjauSbEmCvukUKwWuoA4EG4c755wurQf5s5Nzv) | 9.4% / 3.46 | +4 | BAM `Aw5wEM` | time-limit 1.1 s | **-0.0068** | [buy](https://solscan.io/tx/3VbBjy5s44K1BA5TA9zTAymQRcj7bWVBBvyYiouYUkjLfjM1gTW8hWanwFvHr9KPJRY6LmNk7tnYpT4WtzmCwAiW) [sell](https://solscan.io/tx/5VRiytY8BwaghKB5Wp74xovr38hL3EKyFa76V2N8fCefzNQEAce8KQyusR4ZC5Evcn2stkGxghHKNnm5Sf69WXjk) [whale](https://solscan.io/tx/3GuxHULrgsu9mE6RGSjfY3TyFDw7oy57tBJcpv6utFExx4yntWbNwFufCsrTt1vDQ8YyWtGqBdBFD9eh32xkD4Bg) |
| 44 | 04:23:51 | [H6J9qy](https://gmgn.ai/sol/token/H6J9qySDEswnBzCCyMU1CLshUmssgFs1FW4g1Uhypump) | 11.1% / 7.90 | +7 | Harmonic `9W3QTg` | time-limit 0.9 s | **+0.0007** | [buy](https://solscan.io/tx/41DVp21WnLbcqWTGmuj4pfbxXs1XR57Z9NqYRyAiWCYAGHMDwsNXCQPttmLgnpBuPbteHdPtXt57HhG2Pqqh7UbT) [sell](https://solscan.io/tx/5Q8QZDvNxTZn5qEtubRBCDnfWdFh6WRCM7TqcoJHGtjRgHKhmPLprCkDuyUyp5mTRUMY3B3xJUJHGVBERpj9Q1kk) [whale](https://solscan.io/tx/49t5HdMUMh6CrG9vovSm4YFu323aGzWqhN595tsdjiFjAyoqQQuUmXa27TdkfGNWvs9zFt3Ke3BNoRtcVPoLwXT9) |
| 45 | 04:25:20 | [BFmqKb](https://gmgn.ai/sol/token/BFmqKb3BqkP7QiW9pHTgMJo2SdBng8HStwz7wQwpump) | 7.6% / 3.26 | +8 | BAM `GwHH8c` | time-limit 0.9 s | **+0.0033** | [buy](https://solscan.io/tx/2cs8aqWd8g38tGZ6GNHQYXVtdw5SV1NPQBkidc3bUmCf2iaEQ2UQTnxzgKPu9bdgCtVbHmkZXqvxSqBeU3RpdzVM) [sell](https://solscan.io/tx/48G7QusuZHrCxb3vYpLftFmH28ZfxBSe3yLuBLwpbHfS5sckU9UQzWVky574hhixFoBjcNkcgauSK7C4EBCWVnxg) [whale](https://solscan.io/tx/2DxrTbeA89tDE1to5dH8Y577Z1iosFsUaFe5n86oxv83siQjC8PpNGg6GyETNqR1bBFj59USp2WMC9GM1hzZyeVW) |
| 46 | 04:38:56 | [4qz944](https://gmgn.ai/sol/token/4qz944jQxCdYdA5L7UyRRVLU9JSpPDL4NdShadNPKqKu) | 7.5% / 2.93 | +9 | Harmonic `FBKFWa` | time-limit 0.9 s | **-0.0031** | [buy](https://solscan.io/tx/5pwqQQyRYoNnNfWHpmG7drroBixYTLKt7ogqRUScKiPs2XxWZfzyuR1JY5HYQso8hN4Z3GUEeUpJkQL5JTrW66Er) [sell](https://solscan.io/tx/4CUmCchaFpLu1wi6uqGt3GGqb1LuHaSz5ZXmSjkrEktbZasBqEXBCrGyd9Gjr5SPPFtt5ZSfm7z8G7adKZGWZZLE) [whale](https://solscan.io/tx/36RtgfGXAuiKAFL8qPJ3JXDoCtELftcTtuF4133CA8Ga6NwYYX52qdYzn9U5QPV3oeVoJcwpH7BsaLBiumujHp4R) |
| 47 | 04:40:52 | [2RgGfv](https://gmgn.ai/sol/token/2RgGfvqfvtz7RPeiau1Bdq2AFoC4b2nKsPNut6zM1UD9) | 7.5% / 3.95 | +1 | Jito `5pPRHn` | time-limit 1.0 s | **+0.0220** | [buy](https://solscan.io/tx/67Ld4DhqV8aFtuv3Dm18suAh5fxHMDbaBWZwQKhkt7DHz6ajZaNSgRRatKuUhedg35cZr5H483CXmLDCMtPdTyds) [sell](https://solscan.io/tx/3a9YZaXkyXrohYFNoD5rq99CCQrGN4NGgb8QXbpwNfxd9eDDHkunyxdbdUtrGqvcGMR4f4Fo5KuBhem1nFMqSZcw) [whale](https://solscan.io/tx/5Gu5SfmDANAQ12SH9Upv9P4PUUZKXBkT2d6W4wmzf9R7wtDQMPXT6PQL71tnG1yyKPWH9zWUMUe87dUELEE4CCtY) |
| 48 | 04:47:18 | [RKor5T](https://gmgn.ai/sol/token/RKor5TpK3jF7HYAnTFAKyCj99ewneXvN1MZ3Ftrpump) | 10.8% / 4.17 | +1 | Harmonic `3psxMy` | time-limit 0.8 s | **-0.0752** | [buy](https://solscan.io/tx/46HMNv6TfoAQ9MGf9u5hx31qQpHD9Yfm51bqWnrB2UbqDQxqyK9BPUPZnpnUi9Q9rweykYLHNjLzGgnytDg8G2Ke) [sell](https://solscan.io/tx/3jVVbnDuVDcnYREwKUK2iqbTsy5qTWCpLk4uD1zQucZRnrJVfuDCjPhCL7mU8scKYxHK2mr4TvVfHq8hb1oj1fL9) [whale](https://solscan.io/tx/5K3PQmarz8C684j34BH32Hsh2iPQmJBxsqKXiRyxdVeWKVVFT6aAJgBjGWNfRY5evdfV4qu4cnXEHju84NpQBF9W) |
| 49 | 04:48:15 | [Dt6eZV](https://gmgn.ai/sol/token/Dt6eZV9XkpD3vejre4XhNgYMYgQ5q19txKJjXnZVpump) | 6.8% / 3.16 | +7 | BAM `HpcB5Q` | take-profit 1.1 s | **+0.0340** | [buy](https://solscan.io/tx/4YkmSRucHrr3EA5LNnXSJWomzTtWJDSjZreQ3NMzp4sqhqi224k9CKBW8z4Z4BSpkMK6VaQudgW3PecgAiVpMkpD) [sell](https://solscan.io/tx/4GPGLEZEwFU2DX5uuem7wTAqnPzodtohK2vsdUiiXUSCscbyLFepJk8nT4PVpZimJPe4JDqBpBaSEeFeSJb38w6V) [whale](https://solscan.io/tx/2x7SR1GuxPZfbevss2MUBFw2vpGJo3nDUfe19FRN4nyhvCTGRcSy8w3mhxThB9MbdgoqrvAwQGgZssP9grGVwfQh) |
| 50 | 04:48:38 | [2Ew1GA](https://gmgn.ai/sol/token/2Ew1GAyFdLyapNMWRi8pLXt4G1QMNSCfBtuXCQy7pump) | 7.8% / 3.46 | +10 | Jito `c3rtoM` | take-profit 0.7 s | **+0.0347** | [buy](https://solscan.io/tx/2HnHPv9ytWnGNdjjZzKEXRLfTwdcwbqwhh2CZA1LeQQartucgFCaK885UokVYvAnD52jUpFqae9dDWDCRGGPLdoD) [sell](https://solscan.io/tx/3sp8v6go4BeHT7bVaoA3mEZv6QaFGa8rX1aLTsDv9zUfF2TRTYvUs2D45VNbmuCBvvk3KjMXYJ1DaBvqQYGzK9uX) [whale](https://solscan.io/tx/3XaqKkrwYxud5YFisV7nq5sJDtA2Zex5CmcqJxf1aZmM6Nd9eZmQD4LTZA5zuuyGPfVpRyU1DQG6UXweL1V5agcw) |
| 51 | 04:50:50 | [Cxoe53](https://gmgn.ai/sol/token/Cxoe53DGEfDYompUHazEFLs5MvMjePgqxG8No6SkpsHP) | 7.5% / 4.94 | +2 | BAM `Fc6NNd` | time-limit 0.9 s | **-0.1062** | [buy](https://solscan.io/tx/5EnG8P9Lgp7NHhKwgMacXPRMKndepf1HH9QXYAaZmHBvCqdoHATS7mAfitTTYpzuQKT5Xew4n2iKRBZGhqDMALPq) [sell](https://solscan.io/tx/3mNcmLp4wngZQ35Vs4RCbQ2LysLUXhmguZLWhd4YNvFVtn7TwYU19d2gt4uFe8uojV7PyhSq9RxWtejxaJRgwUtC) [whale](https://solscan.io/tx/49svNCUQv7W7kJRYoKLnW21GErnZ5KbXJuCtr2L9Kx5t9YovS7D5pmGzSQuEqm7kBYw335Z89koWZsLUAz5iDTp6) |
| 52 | 04:53:20 | [JBCicY](https://gmgn.ai/sol/token/JBCicYrn4UDrRq6zj6p4KKRW9oB2rivozLbE5Szpump) | 6.3% / 3.46 | +3 | Jito `EvnRmn` | time-limit 0.9 s | **+0.0282** | [buy](https://solscan.io/tx/2s5i4NRcBwHiCBrnxknJTN8cWXiH2dNSbvkHRPSSeM1T7XVdwi5jJSrbKbLYrMF3nJyuP898obAdLJyZS4kqRhVj) [sell](https://solscan.io/tx/62WKabzvMwWwZ1V8qjh5FF764jj2zVLPFp8oSh936fCJgKY9DRoaUPygQ2nSv8sFsGFoSVN1DoHFmiFrUB35WWXd) [whale](https://solscan.io/tx/2Ve2RswK7Nopx2acFtSRvQvheuMHLBCpUD3EVahAMchnw3YyKWqRLuLFv9AzYmiZvU4cLgMP1wMPMMkGGvywdEZv) |
| 53 | 04:53:27 | [BjqTN2](https://gmgn.ai/sol/token/BjqTN23EshbUJFjThL14MVLpTFtFecBMV1X3byBsQz3D) | 8.4% / 4.94 | +1 | Harmonic `GZ4U21` | time-limit 0.8 s | **-0.0245** | [buy](https://solscan.io/tx/5dy27tx3sqNCpQt3XWBCFmbTAcrgVGfCiGUnPVvf5LvzGrcAn2x7RXhsSWzbkriSJMyFtBWMEvPCe57UyxUJQa5z) [sell](https://solscan.io/tx/2d1aLEgsWJZDqzvHdgQdbV9rNzmigsBDSQ32jH8KJeCsFC75Xo6BGRQHJSEVq1TFckw6Fy2B9BLtjUp7LgUD9T6c) [whale](https://solscan.io/tx/2NcQzKPjdq3B78GgQrLaPxj4zXBWeQuFZG8YyYvKY843sYWoTUaEbeygQ9kA1Smy5kEK82appd4YBqmngPig8uoj) |
| 54 | 04:54:15 | [CbTe8U](https://gmgn.ai/sol/token/CbTe8UVe65JyGranK2acfGGp4NGVj3vJAzfBmYNWpump) | 6.5% / 2.96 | +2 | Harmonic `Fd7btg` | time-limit 0.9 s | **-0.0121** | [buy](https://solscan.io/tx/62csyj2mmmzYvQjTF5xRXVBsHmoVpjzMsFMvUdBRN6dJPY8UmRjsdpXRwb1XKz7PXTfAB5rmtbndiQ4xzzgRpVhL) [sell](https://solscan.io/tx/2ciG9xgo3gBcNhFMtH8zm43ZRx7uuU7tQ34hZyWuczGmY3QZF1mfv4mgiYvFvAdZaeFXwDFTn57QUA36PL7BJvfm) [whale](https://solscan.io/tx/VmCdRbfGzfvHgC5hfcfeDkAQEwcUGUcRe8f6MDWsUM3FvaYBn71eBJfKW53wHRTSDncgz1T1bn3vgKG2rtpP62W) |
| 55 | 04:54:21 | [5Qe41m](https://gmgn.ai/sol/token/5Qe41mdnsWJt79cY7VQSdXka6omDgEGtqu5Q8VAapump) | 7.4% / 3.46 | +3 | BAM `PUmpKi` | time-limit 0.9 s | **+0.0005** | [buy](https://solscan.io/tx/4uNtaiNXi93HZPUTvvzNv3A7zSZ3o9f4PN3g51SYJxtYKQ5nPKrqPT9zvkA7nEApsHVhd9UekAHohpjmfRDe2rPn) [sell](https://solscan.io/tx/5sEfRxZiFQsf73sDmCMuuaKbYKprpoM95qZxNUCpFKPuitPrfN3UEvFaYj9aCXxgsGwZcGi4DCACYJ7J5s1gYLej) [whale](https://solscan.io/tx/3Q22MGpsvXBqq5Me7Hsj39PCNggTL6DNwSd9CFJGhPFZmSW56qUXJGhTUSf6X8jaRGTaG8rY7DQgdQqdZkCJNinZ) |
| 56 | 04:54:58 | [2Lf3gX](https://gmgn.ai/sol/token/2Lf3gXnqYtpfn11SBmxyVJk5MgA1cZ2sH5Qd2LC6pump) | 8.0% / 2.58 | +7 | BAM `RoYLtt` | time-limit 0.9 s | **+0.0059** | [buy](https://solscan.io/tx/pPaCeeogBEizkPmA2XYE54CFfG15RLzaiUuAaQuMxpULTBAXzeetPGhvQK8rHZB1xRnFCKED2FMt5bAsSpE6Y7W) [sell](https://solscan.io/tx/4NE8Ky8uBR8bpKevcSvWfEzGvNzT5WL6pKs7qz4xgSKyepjcfJBaHe7KqWqYx29Kd2yofzcgZbMDYcReNiJHS7Dk) [whale](https://solscan.io/tx/3BjArkMnThE7EQvMmoJfKTAU26VCEqAWMWiNRYWLNQQMSC869oGyyKA9QWKBBUTuWdNFTQehkmXtS9jCk7Kxdp1W) |
| 57 | 04:55:09 | [FZfyuy](https://gmgn.ai/sol/token/FZfyuyB9tfkUxQHHCNPXFsfi1LrM8uC2V8c5ceK1pump) | 6.7% / 3.46 | +2 | Firedancer `JD549H` | take-profit 0.6 s | **+0.0441** | [buy](https://solscan.io/tx/hGeu9mQsqZkuegk4QXNU7dSU1WPjw8ZHacj96jAkL7QGaA812PTE6UAMNoEbsMJCfaPSLW1EkSZE3AyKyvxXSQG) [sell](https://solscan.io/tx/4A5Y4BgCdzgp33LPXAMQpZrzr2X3NVTa6BG2YLXHxdQug9joDVp3R59piN2FnzvykRGnAhZo1hCGarA9meSSEy8N) [whale](https://solscan.io/tx/51pwny2sQ4PnejyxGp31BnvCSMBYA1epWzZXFRyJpTbmGQExeRPchci9mbdrCBLgv7nbAypGkfwrwtLpk7kpHV8y) |
| 58 | 05:03:38 | [92yqXT](https://gmgn.ai/sol/token/92yqXT4KsrinMZkjFeut8as8eRXejCRhxg6bvTYupump) | 9.2% / 4.94 | +2 | BAM `D4r6Rc` | time-limit 1.0 s | **+0.0407** | [buy](https://solscan.io/tx/13PGUkA289xmHjQfmMMNFDodoxC8QieUuYRPQ2H4z18zKV7E3MfngsxiKLrDbZcq1WkTceFFiQEUZg279jur75S) [sell](https://solscan.io/tx/5JnD7T7j64VTZqCeDAivYWporKvwsusXWRdxRG3iJzj9qhQnY4cLrYNsVA9mk8RCSnQraz2mXFT8kcfTQMWgYdJw) [whale](https://solscan.io/tx/25DTDFtybtpWMs8MtjrhsZecvcjbAQiEQ1cfFfhE31kenKcapyqPq9cc4iYMRLwwWUoMomet7UwFRpe1TXLUEQD2) |
| 59 | 05:05:29 | [6KS4pB](https://gmgn.ai/sol/token/6KS4pBSdvgNepMiwSDUY9ZQ5hH8NFhTLQEApYhKEpump) | 7.7% / 11.10 | +1 | Jito `Df16xM` | time-limit 0.9 s | **-0.0135** | [buy](https://solscan.io/tx/5AEmAbHE911pVbeRGQaBZEzFe5NLZ4diqDGrC3DpsDR2XstkkLJiFp3W8dGsRxXLNcCKvpFGnyzwsgbPEy4shcz) [sell](https://solscan.io/tx/21z9GXjBwk5vvpGb4trnUDVdrtHV1UWwmjeaarAu2MWnsxmwocVy4vWQTm4R7pNnxDQAFAxdY4xmdHc7MVWoQ3vZ) [whale](https://solscan.io/tx/5G314DcyxDH5YPfARR9JfVxPEW94f7JA4xyyA9huyPh81mCvCoYrehF3zFK8oJv77DLoDMQnFBXrnZb2NAmQFubZ) |
| 60 | 05:07:09 | [GcKUNE](https://gmgn.ai/sol/token/GcKUNEKbSdPY3e3VEUDVx28qU8hbZQTm6PBfvFTzpump) | 8.8% / 2.96 | +4 | BAM `76rcGH` | time-limit 0.7 s | **+0.0034** | [buy](https://solscan.io/tx/4HwXPAktUqLdTDNjUkF73ck7ipuFwpAsQfyMD3pn9mDz11a9zzKdLbSnWTrtEiHh57eDURLhnmHDAfeVyrTAND9i) [sell](https://solscan.io/tx/54PuucK6r9gPSHYC26QY3dfb4z8N2qvssSJ9JWzdEzPztDm3DMeFehbTEpX7PaMUFKvrbZ6PSzeUWMcuaZ2zMmJt) [whale](https://solscan.io/tx/zu2xfk3baDtb17uX6q3kgE3VFTJrG9z37QUuGuC7uGJKWvxKumV9gGUHPk31jAxwmC2TkyigAwWi43gMqDH6SQ7) |
| 61 | 05:08:03 | [BhydQC](https://gmgn.ai/sol/token/BhydQCii2th376n2F49ggJLQk4abF3hXYx49T5Rnpump) | 12.4% / 5.93 | +2 | BAM `jzDsim` | time-limit 0.9 s | **-0.0142** | [buy](https://solscan.io/tx/3m8ATUrrFLFYhhPXHcpPWkpP6kV1hE3ZuBRn4gdMJfp1THaR8t4FoQZF8v5L5YixBM1CuwLipefSLdrgpjHgK3RN) [sell](https://solscan.io/tx/4iXsUj9goRSDQBkU9jcNbqft72Gz3Exdc7TuWHZbt1SPKUfNxqButa3HvoJxZpAfxLpPocK7j6Ndmp77shRjdrXQ) [whale](https://solscan.io/tx/3TjyJoBx63uV3XDPqkk7o7ow4CC12FoppDrDPgTaAwQYWt5p4Eb4jtnmkNLt9f4vismGrVEgMwfQz7pmgYvFvqG) |
| 62 | 05:09:53 | [H2hwKF](https://gmgn.ai/sol/token/H2hwKFJGsraFjiShPr3WUiV42SdRGMMT87xqXJ9Gpump) | 7.0% / 2.96 | +4 | Jito `EvnRmn` | time-limit 1.0 s | **+0.0224** | [buy](https://solscan.io/tx/24ZuWNvRhybF8XxzB8BYq2N8c8KFqzbnHLQYh3zZskAiqcnPmmQVxABdFqEnuTfwQR5Go5MV9oCH6rgozLVSVvJG) [sell](https://solscan.io/tx/GXaN2DcMZ3Dbd7tuAiKEB59R815qaKDFez7g9Yey25f9tgcC8fLWWDzeSS3aMkpo6ftjsukWRXYSjBGcd3vr6ew) [whale](https://solscan.io/tx/CUByYP5KS9LDTqPHh8FsHXFC7wZnVmLit7QxDViSi7zXXySEiVcjeG4pZr3MboFhZuiNoaPGHuFejAtWbEEFxdC) |
| 63 | 05:11:31 | [CcsbBa](https://gmgn.ai/sol/token/CcsbBaByDF974y7DmvmF699bU1in5nE8sGP39eiBpump) | 6.6% / 2.93 | +3 | BAM `spcti6` | time-limit 0.9 s | **-0.0119** | [buy](https://solscan.io/tx/a367mjjnqiEAw5FqRBaSd3GJPoc7Ro2b7b8VUAWMAqcUtXzXQsDcLTPgzVgpPTkAupHL5f5yN3QPAtVquFtFuxU) [sell](https://solscan.io/tx/3mrJ19ryJ9PVD8kpcWXsoG6HQca9JqLW6QAftwvWA3AaAn5W7jmogvGTL4emjEWrWkwULoADJXmM4sGwUubVGh7s) [whale](https://solscan.io/tx/5TpDC5mLNk1XsJ9akbdFJeD33EEMYp2U5ifvEn5VkxJRibLtJw2UwPjGJeWS1AsYT8r6JKPR8CECy255hxn7qxjA) |
| 64 | 05:12:54 | [8fsziC](https://gmgn.ai/sol/token/8fsziCyXFgtX3NjkzLifanRkSidhfYFsdGftHuEhpump) | 6.4% / 9.73 | +1 | BAM `2mDrrm` | time-limit 0.8 s | **+0.0052** | [buy](https://solscan.io/tx/2HNsrdGkBccZtb5WDUTGCbfC518XdYTFbPPKfY85E8c8U8fWA6ME3NFpwiaDUBAXYsf26fZo159eYsq9bzosQR9c) [sell](https://solscan.io/tx/4Z3gQNVanFZkHQ37gRJxHB8tYRqSxWtS53xzZXzx2pJN2c7AF4s7kom6iEyrMDBmVWGQAWMvckrxspbZespPc7TK) [whale](https://solscan.io/tx/5BoMjXDiQEqq5RddNaL1EXMWvZd56WjxFrvuQJLV6TNhreVwukPiz7FbR45yN9Mi6WQ8Ri9tQv4QHRbF9DVaEfzp) |
| 65 | 05:13:02 | [7XWFnv](https://gmgn.ai/sol/token/7XWFnvCYrfpi63kkGUq8D1k2hhxDNumyd4kBuB6Ppump) | 15.4% / 5.93 | +3 | Harmonic `8LDyye` | time-limit 0.8 s | **+0.0114** | [buy](https://solscan.io/tx/3bY1EEcwyTM3m87g8tsk2pZHCiyT1tznJ8sPxtdS791BCCbnrT5M1tLVKe9bF3pq4w6pUJPBkG12UsUn8DXaSM5H) [sell](https://solscan.io/tx/Qdx7kCj1JDMDACTswd45VFZDfM4xvDht4W9haVLpPh7jkgFL3P5CnFAtwcXHbDMhQkABDXEi8W5qLJPtY24VDc1) [whale](https://solscan.io/tx/64hdpcuUEkK26Bp7tbgpavPaQU8xm82qvBALGnEs3MGtHyNGtvYjd1s897F1jigQZQUvFcqQ9GK9V3gpRDU1CTtv) |
| 66 | 05:19:26 | [ypy3Uf](https://gmgn.ai/sol/token/ypy3UfiZhiMJmbTDErakqVuXhEyvnodjUygb5MJpump) | 6.8% / 2.47 | +3 | Harmonic `FNKgX9` | time-limit 0.8 s | **+0.0194** | [buy](https://solscan.io/tx/5gzGvtT5zdgJdk6v8sX5rpytwFxd7BcKHbYmmwGU11t1X8Z1ZGMPj4N9Ty4CErgcM6XqksT1HU9xm6r39HPkhcns) [sell](https://solscan.io/tx/5MT8c7daVAv9uL9bEu5qsLdHe1m2WPf6BgcN8gSAG22Ujgn18W7HyiunUN7X5rLkZy9hh65mTqMicCYAev2dj61V) [whale](https://solscan.io/tx/YP9aYskHD6n2pLdJ7eMVKLEUUaAH1C8sDyxoLuvDDLrKiKwvHeXLsDuw4mSJb24E3MV5KZDFufyc8hUEtQjmiEz) |
| 67 | 05:22:16 | [EmZG2B](https://gmgn.ai/sol/token/EmZG2BMp9hSS1oZqN69uCTvCx5Xr6FdA5uvkrCJkpump) | 6.7% / 2.93 | +7 | Harmonic `HTeRsa` | time-limit 1.0 s | **+0.0150** | [buy](https://solscan.io/tx/XVYVYtgSD3Ug5ee6GVM5AuMQ8Q6s3mL5vXZgWDzhsz2QXdAHAm19sLS3cajDLv6qPGCJhjeLxZRBCdME2tF3FnJ) [sell](https://solscan.io/tx/ZhAhdGNYzfDP3DYuAby9KXHY73HU1FxqSyjsxqgBdr9LwtaQ7JadPABd8ENxAVrx4nw36C5Pc8ZjegCrdtKE9Qi) [whale](https://solscan.io/tx/2SBozoNBCnV6R529heoUFfQioU2u1P8aQRJyKdruvsEqsqRgU3UQ15J3UA8tiCYxBS9y7Bk6Yhf4bXZFYUW4z92v) |
| 68 | 05:27:38 | [EzLUbm](https://gmgn.ai/sol/token/EzLUbm58gBbQs8suVqAWfjrvGKUZm5UQWUoKKWxNpump) | 8.9% / 4.94 | +2 | BAM `DRpbCB` | time-limit 0.9 s | **+0.0246** | [buy](https://solscan.io/tx/3qgRp2mBGiN3vQGufREBnsuW4NDYNWRGyye8wVQWMJSLc7djeVqGkyyM3Z6dKQ4d9C8FkQ2AmkDTbCSYGkS8Nf5s) [sell](https://solscan.io/tx/3LnCWXkzgzHox1EbUNzbim6ahXJbqoYMDJvciE2Rn5D1Ucmn7DnDxeCbBAW1719isnf2ejKuMHzZFF79nZV37px) [whale](https://solscan.io/tx/2jFsXnh8Q8bBBCJTMgANp8eUvrzkwDNBxthXAeVjjLaAczNEqV2THbt3BcN9Tgtj7qnuwbC7eUTSSTbgoAEKzEST) |
| 69 | 05:28:28 | [7G5wkT](https://gmgn.ai/sol/token/7G5wkTW6jxLZvVDjRqgsEPFYmufyyx2D3bCtU1cfgfKZ) | 9.4% / 3.26 | +8 | Jito `C8Bey3` | time-limit 0.8 s | **+0.0095** | [buy](https://solscan.io/tx/TmstmsWsKm15rA7ZCWAmUayzs7Db2LM6EXvztoKx1qyZ4nzXDTEvWx6p1Cu4gWhhbhezSBAYpJYtraspHTjQW9s) [sell](https://solscan.io/tx/4BAPRYHNvXTdFAHc2Kz1GbREMNoyoQZUX851DVTbokwZogmwWeKbVYNqHHwBDByHRnJf2WZS73EWhdzit5oTQC5T) [whale](https://solscan.io/tx/3jNBEMykzAXWCznPZz6uApCP8GkfJ75Hh7pkYdBXkgppzzyi7ktvQ9xevaK9QNamqoD1qjDWniu6k9DNXrXq4NW8) |
| 70 | 05:29:34 | [Fazxg3](https://gmgn.ai/sol/token/Fazxg3QcGaCLJgV3XJeoumsH3Gkd357g53iT55Bvpump) | 6.4% / 2.79 | +3 | Harmonic `BtsmiE` | time-limit 0.8 s | **+0.0846** | [buy](https://solscan.io/tx/4Pq7xcDHo5J71tWUxj4eDa4KpgUnoXjSjFyyhvK3MAVXPC16XcdEEhxy91Sjo64XmdvSGFWPyWGFh1NnZX5hfpqc) [sell](https://solscan.io/tx/2aK4mvgXTnwosb3ncunbS2p7vkdq9d374C7DqYS6MuymWrSdfuVs3P9xgWUteUSyVTUYZbXbcMPTQM6QSjdJvhsx) [whale](https://solscan.io/tx/3YcCmLyLWp4VLinUMC75sLPbrC2LQTFTujnDp6Bgg1QhvEM51wbTSn5UpZeubzWBRA1iBXcmapsyxbdWgaEySNX8) |
| 71 | 05:30:15 | [AsiWS3](https://gmgn.ai/sol/token/AsiWS3yGVLoEirXF82RQRCGMBKdb7hysdbG6RU8br6Ed) | 12.2% / 3.91 | +3 | BAM `DRpbCB` | time-limit 0.8 s | **-0.0119** | [buy](https://solscan.io/tx/44GnfZHGE4DYuNrv7ApSVCVNqgBXT5Nm8ZRJvYvyyssvWM4zjAartLkrJManbSqfKqGXviw9GahqswyXz3rngnmn) [sell](https://solscan.io/tx/4DGvLKPbzHzabyfxtib1UPEMaT4KLSruhkPW4dgXSof9nDMiP3nwZm5h7pSJHvxvTArqU8rQhXnVkStA16AhFNa4) [whale](https://solscan.io/tx/4t3VjVyDDFJ1GkMrLvPZN32nab9NjNiW5iRHJTyU6iAPSaKL15zLfuabSwWE9SFrfFoye5fyc4nNzU7rT8pbEjyc) |
| 72 | 05:30:35 | [mj1swJ](https://gmgn.ai/sol/token/mj1swJMWJN3mQrd3Tzopgr1fhuBaRq2SGDV9GoYYqEP) | 7.0% / 2.93 | +4 | Rakurai `ana2y2` | take-profit 0.7 s | **+0.0745** | [buy](https://solscan.io/tx/5SJXMNoiGqZvijRXpWHnjcrDWrk6e67QbsBP9jB8fYb8qkZ82SEHGGqQPYTKnXvTtVkKSMduqnZtevbMbqCQURPb) [sell](https://solscan.io/tx/3VTTJxWABcekwDZmP3WP3LEeEgL4DVbUnDsHUrZ2qNxkaJrxpMVBTA9grQqEmyzEMSpcN7pYYjop3VmrwCB2vMkU) [whale](https://solscan.io/tx/5tBdpUj7tw3ieFUk7QP3e77P6GAuzmbS2xLZa2s96KeiDrcDE3KJ97Sh8XowYeKPgxNGCuvrmXkA7wDzyqfeS7Kd) |
| 73 | 05:30:43 | [EiAT4G](https://gmgn.ai/sol/token/EiAT4Gw6bZgwACNjYxab1MDiubjS1PXbBE2N3hfsKrQB) | 6.2% / 2.93 | +5 | BAM `Fc6NNd` | take-profit 0.8 s | **+0.0463** | [buy](https://solscan.io/tx/25gxhRcaRqW2RfoyNe6235pGz9LMzfdqnVbSsiikqz35zAtrJRkuDhWeQb3u58LrUGHMQURE43sfWMFw1xdkTH4R) [sell](https://solscan.io/tx/2proMaeLhYUb5VrV32sq6myA8scMTZo3iuxMMibDYcemudiQQB27Rk7RVUtYoKoe6ahbkmD4mgDhq7k9SFx4SaJL) [whale](https://solscan.io/tx/4UzcnDe8qzW7H4U6JbuihV6xes9WAtdUevWLUBPdA2Jp8CeYheBLxS33cw6PfDYnFrtAGMU7XzVip7La2TZE8CVy) |
| 74 | 05:32:21 | [HCovTB](https://gmgn.ai/sol/token/HCovTB3hjvj7sKQm4QJBoY2c9nku1CVqheBHwnzPpump) | 6.4% / 2.00 | +3 | Jito `EvnRmn` | take-profit 0.4 s | **-0.0015** | [buy](https://solscan.io/tx/2DAV4wgzQ8JHam9fVeFCJYntZM4N5fe1ZuLQiKnnbL24ATWfvYCA6PSnuckYXMkBtRy9JzoWyMEifJXdG9MzmaqK) [sell](https://solscan.io/tx/3CsLr4LWKSCFRMV5emstpuKvgkxviAfy5ecn3DJhBX2kqFYZ74Bcee62YSJ3yJ4FhFXHdAytiGxvvaWKxg7t22RZ) [whale](https://solscan.io/tx/54KGgYNcojYQ5XMhguAuSdynn993ggVBgEdJYeY7Vr3CZCrxRonZRXPHiCxJTVQTmfzoNrsUAiFpdaGiP52uKKu2) |
| 75 | 05:32:22 | [FdJqsc](https://gmgn.ai/sol/token/FdJqscvuoKUUdjQgxxy8Mxs5YYK2rLynMgXDU3Rppump) | 6.5% / 1.96 | +7 | Harmonic `2DTXh3` | take-profit 0.8 s | **+0.0321** | [buy](https://solscan.io/tx/3HyJnVhThhu3FxPsTtoP5FCX1iNAghppQLhVzZa2mvDNvNMjvHf84LixqensX3FeqnzwWDUzD6mpUxC45F2Qdh1y) [sell](https://solscan.io/tx/5RH5VUQvDzBgVSHKTWNZBq92LxogMEPgFS5kvstXiBcg3QpLa1voiMmwSuhiXBfVeMwZiPM816YpKU4MPfxobWJD) [whale](https://solscan.io/tx/5FgC1yBSr3WzwzsEckqY2ufBnec3p8jeEbAqAuhGRF8wEDcn7rLG99dBZ5SS6ceDUV32tCStHXy7JjCE7RcVJgZB) |
| 76 | 05:32:31 | [HCovTB](https://gmgn.ai/sol/token/HCovTB3hjvj7sKQm4QJBoY2c9nku1CVqheBHwnzPpump) | 6.2% / 2.00 | +4 | Jito `HEL1US` | time-limit 0.9 s | **-0.0235** | [buy](https://solscan.io/tx/5ReAitYhmAxkLLc6GGYY9V6NbwtRAFYJjVsfrYZjUqJpbMtypk8AfvjZXr5HRF2thZ7Rtsrsf4UpEwF5NRMohYW1) [sell](https://solscan.io/tx/3P4PqdwHQv9q3SvRVssLuBKp3eiRtXeoEsUFTS6ojFZWxgDvmf8Cnz3gyai5UUp4MKZSwg9jBU61iZvQovAuyWma) [whale](https://solscan.io/tx/KThddQvS93W3Cn9u1gXnmXP4hUAbjF4XibHeTeXmDdS7udnVrJowrnoQkHZZhKGqN7WoVz8RSdWu5KyiX8d1WZE) |
| 77 | 05:33:50 | [EiAT4G](https://gmgn.ai/sol/token/EiAT4Gw6bZgwACNjYxab1MDiubjS1PXbBE2N3hfsKrQB) | 6.3% / 3.46 | +3 | BAM `DRpbCB` | take-profit 0.9 s | **+0.0339** | [buy](https://solscan.io/tx/TNjQCNECvhkDcLtkD6K22QmDx2UkZyN2nq5LugPLNYzzuYniCw6ppGyJhuN31ArMhnVUQzYMD4zKtLyRffMMXPt) [sell](https://solscan.io/tx/5PCV1YnmNJGrMc5JJ8koaXZxuQkMU81PkLwzoTb53Wg7cP3GoLwsk2E6W9Ca51Jn53RhHXy3Kc6vXTrhVQBGd9i8) [whale](https://solscan.io/tx/3KmtKaqeuxigDb6b1JMPyBWgRtXnbmGyYtS9BWqQgBooWK1JHgjzhzEiUupmizumo4z8kMnvoL8WHdLLLxUv6Ywq) |
| 78 | 05:35:47 | [AqdopL](https://gmgn.ai/sol/token/AqdopLC3UQKBrx4yfZnReRh9meBV4ytugyP6kfnLpump) | 8.2% / 3.06 | +4 | BAM `GBQ2Gv` | time-limit 0.9 s | **-0.0091** | [buy](https://solscan.io/tx/2p5Kr5VTuC38RuATes5bVtLXfq6udiQ1WE27vPXpWjpG1EU8z1avJNWvhWaxZniTkZHb5CbCmjWUc7TXEjQV4Avb) [sell](https://solscan.io/tx/A7DrFfYaPzAxzwfJc8spxsb1tkxSG3ZxGn1sJeohvoPmTrZy7PG5B2RZD7HeMhdT4MH191THoEFnvVNTYyE2biw) [whale](https://solscan.io/tx/5rkYhrR3Gb8FhnESZsJhJaJaLR29q8KCRMKK3DFLW1gexrCJ7VmrRiR9aaErZTff3b5EKYVxbdYrmAcRyQ3WpnaJ) |
| 79 | 05:36:12 | [2HSKtH](https://gmgn.ai/sol/token/2HSKtHtXjCu7sWSqiMCCQz7WJRCyqU4dRSw9vHThpump) | 6.4% / 2.96 | +4 | Harmonic `5RvfTS` | time-limit 0.9 s | **+0.0005** | [buy](https://solscan.io/tx/64j8dSTN3mgz6fnAndWa97hA4zW3y4xi57WTk8bDHw5MxnBs9w9pW8YpGtFGUYwR5qynua2iGj7dcCYRPsPRx4Ue) [sell](https://solscan.io/tx/62x83PoYxcjCupFRWCFAWCjFec6gWkVECwGH4hsi76CweFZzzBUsmCCXzaVb5U2iNE3EZT2eBji31xC9Zg7kYSC1) [whale](https://solscan.io/tx/5saed5d8eqFa9NDyrJvKF3uunYwKhipixjw6LcjA5rRVWCXuxz4pZ4LxdHpz83Tm3NFAozicPwSVRTJKwrQFJ94J) |
| 80 | 05:37:52 | [3mQDF7](https://gmgn.ai/sol/token/3mQDF7CraFyAfHDF1qxoSGo8DJ3BaAEnaKWeuf1upump) | 7.1% / 2.93 | +9 | Harmonic `mrgn2v` | take-profit 0.6 s | **+0.0402** | [buy](https://solscan.io/tx/6mb12rkgQe7DLFMPD5drtUF4SWddd972q5vA7vntVd1twg4K5nVF5sGfrKnVnryZv5uP8YZddR8VwoJrBXkEfUK) [sell](https://solscan.io/tx/4MTnpGJn2pUeNa6Bf4iEsWpZ5sHMXorL64u8GgDY5sTaE7WGbhjHJZs7sY9HTtYKDFazBBvwbZ3J3rx16ZY2gZRN) [whale](https://solscan.io/tx/2zUVPqdC1SwzxWVLmWSvBLUvkNTv6L4UWPsBnXyaJ5vgTGtMEHNMPMQrxYMXuJV75VRcRQ4iBWCyiRnL1uU9SaN) |
| 81 | 05:38:26 | [651ckq](https://gmgn.ai/sol/token/651ckqGbNHRJtUxoxAFL1ZyyLzFCTFzj1vqX7EBWpump) | 7.8% / 3.25 | +3 | Harmonic `6yFGGA` | time-limit 1.0 s | **+0.0088** | [buy](https://solscan.io/tx/2zqZChrFn1tb4Ha1hDkYGTT74SfUy2GUg7GsqX5GHzqHY9YjSAgsLVLS6Fq9RwUS1dhpnXk4Zrkzb7VTfs5pA375) [sell](https://solscan.io/tx/2H3k6L7gzGWq99BH5rTSgszTL8vwMRCcftjhAZuV9vCtYLF7Z6AjgHrxYqpLwnmtqz9AyA47DbNKpsmhhzW5MDxV) [whale](https://solscan.io/tx/5DD3o9kBToqExmUCJKShY9PcLuFh1cML3Wa97QWn8fMCKDPDRJ7a9SoKaePniX2pobgC828PNvAM6XfaWSfSDcAh) |
| 82 | 05:41:54 | [HtCzFM](https://gmgn.ai/sol/token/HtCzFMmM14dEwLdCV66QD7J6ZQyYBWVW3MboDXKQpump) | 12.5% / 5.59 | +4 | Jito `C8Bey3` | time-limit 0.9 s | **-0.0071** | [buy](https://solscan.io/tx/2ri5gQSpaxdcRSj2GYYRKdKhbwB2ezVe3xmDKcXN3Sm2Jz9r13Xr8YxKvNNxjgjmAKFQT6AN5pRG5d8N5cafEnyz) [sell](https://solscan.io/tx/587d1hfmiSR7SVzWpuZxnPpEHQaXDhFu3QJE4kgWsHjkKPc3dRjsD3b76BF1cthmj3RGF6yM3tZaUjyXMrCUYss7) [whale](https://solscan.io/tx/4cdg2xbDEjnFeSErWrhnqGzdfUJQEVQ5Z4CGve4orjXxLmM8pinsMddeVigargg78wZvb2dwiqpcY7ftVvavFAZW) |
| 83 | 05:45:05 | [4jM56i](https://gmgn.ai/sol/token/4jM56iiu9nipDs2Z7oXhxGmxxVAZtjTr1RbjhTuapump) | 7.7% / 2.96 | +2 | Firedancer `4SNKY7` | time-limit 0.9 s | **-0.0041** | [buy](https://solscan.io/tx/5PgApcaRJw9KM3pwyufhim4TWXJBzvEuUWjHT6rtUNNoGqwdGBYbVLqiUTazVh87Rbzw41QkudaSiy1oYULjg2YD) [sell](https://solscan.io/tx/5wvLgUMuWv1VuiL7t11SYQTqw2xBSp3rm9eCuX42hhoaPbL5FLVNAXY22bMVd8oCKY43NRJFNinRVJXwyfDmA7B) [whale](https://solscan.io/tx/4qBkahYdfcwv4AtgGjRGqYg558xREMZmxjHDQrg2oiXzFcmCdan6iv2u1DQQZaj2XCJPcwhLSUft18ZvLFioUoDd) |
| 84 | 05:45:57 | [BKyz6U](https://gmgn.ai/sol/token/BKyz6U2K6pSMJVtENqKkXzJqLvBHQj4fwXT9RYGEpump) | 6.4% / 2.96 | +3 | Harmonic `AMukCL` | time-limit 0.8 s | **+0.0273** | [buy](https://solscan.io/tx/4r8aB3vg2uBHMyVJk8ieuo8QK54ZoFvxYsWTsa39NFEMYjASidRX2ZHjN62SJMBCLZ6nX5HSRxYBHfChzMSuGbLu) [sell](https://solscan.io/tx/4cX2S6cLpvo4QcK3yJFfhXVzdQUzxpJWtGbSmq4oMGKmsqmouNGmKe6xNzunUGhzde78HKnAu3VPWWqHoEFAvHXh) [whale](https://solscan.io/tx/2VJY756eHB8r6QWQauarvtQjmfbFTxqeXRQswDtBu9W1qkxVAAUKckA5e5riEF2eKQ3jgFwZPVGUezocJ2NfP5DP) |
| 85 | 05:53:09 | [2DrL3m](https://gmgn.ai/sol/token/2DrL3mE8JR4CcfDn2dhEikEDMu3X4Mf25YY3mq5tpump) | 9.2% / 4.18 | +7 | BAM `2mDrrm` | take-profit 0.6 s | **+0.0354** | [buy](https://solscan.io/tx/4s4cfSCFqUtvytmMg7J2yCZ7uvoVBaYPjiVoMfFih3r8LjUfpbHsSFSxQiQ9w1fA3ExDyCwkqwrmY6ZtboZQjHnK) [sell](https://solscan.io/tx/2Z1sDwmuAb6Cyk7TWBuTadh5ZsKjs1kXzpHrTkDwXHp9NJbbSkJG5Wog8db5WHRkHnVDi7oWWfjCVr2F5Qnj5G4V) [whale](https://solscan.io/tx/2QsZMiekLHXdVHL6WqYrteCdTJX61B8uhcnFytJqPF15y13BcobJ3MqMz3pGjwXpA5HdHicXT38ve1ZTMb5YC2ra) |
| 86 | 05:55:12 | [76vWc3](https://gmgn.ai/sol/token/76vWc3MnVPCB4W33H2fdniz5tXiduhQucSAodYGjpump) | 6.2% / 2.96 | +4 | Jito `Gv9ggu` | time-limit 0.8 s | **+0.0076** | [buy](https://solscan.io/tx/43oQEaAVKerafQ5rzS6Gsn4byarFn2A8Z4g7njD3rqhE721axuE7CPiYwzoxKikCE3HBbR36UALZzKJww6LWZjPx) [sell](https://solscan.io/tx/7rN6QMA4PsfUomJ3v55HcrsoHXsUQwSxjmFZSfrhs3DxU9Ef29LrQWCtFa4iXNak1QDaDqHwaJnSgKmtU3sd7T9) [whale](https://solscan.io/tx/24B9LdpthTfD2Pik3972Bf9tmXeFjo5tmhZZccRE8rsjiwpDxhrftuG5ofS8o1zXhmn5R9oT1b7gkBVMcAKPA8nF) |
| 87 | 05:55:44 | [5mEPfo](https://gmgn.ai/sol/token/5mEPfoWpg1pBdF35rZgqARn7M8EHD86gd9WgD8Lspump) | 7.6% / 2.94 | +7 | BAM `5Cchr1` | time-limit 0.9 s | **+0.0004** | [buy](https://solscan.io/tx/3f8ozPGcAGMxNLB9BtooatZC6EyfV8FmqqgEXo44MAZcUkG9n2b8uC2bvusE7ztfmMWAMrSiWvmFWJvtTUbhviC4) [sell](https://solscan.io/tx/4yzDpVsyyrUmssDbUVCFwJesBY9kXBQYc7atzVAwUxWP8TePcLCiXUBZzhU7r1TdCfrRG5rCJ75ykiruX7U4uWKv) [whale](https://solscan.io/tx/5Q1os8AfdgcB7x54d7tg67aPWsZX4DorMBETrbyMGEmXfyU9H1An2F6D2otMVoiehrZWaFZavGs9McskURhwcQ7S) |
| 88 | 05:56:59 | [8GZiMm](https://gmgn.ai/sol/token/8GZiMmL2fPtj2tKApUu4a81omj7ipZkeETnyKRQXpump) | 8.2% / 2.93 | +4 | Harmonic `A1vqhA` | time-limit 1.3 s | **+0.0353** | [buy](https://solscan.io/tx/5UGBvJtHA5a2vVuKn5kZsHcCp4py7nq71Ve88hbBPgNsz7xwKhv7cSTqmE1uTyWLvhHms8Mp1joGVJy1RDv2Cawz) [sell](https://solscan.io/tx/3AKJNTvRCawQ6h2TacoDyH8ABEvb4R9bbG7KaXpVMxWoxQ5srw2zUoBFn812uTvF9pYE5QHQurHM2VEv6YwzG4av) [whale](https://solscan.io/tx/5vvDdpYiHGh631DzvqfscnzXCvwyw5DRcgz58jokyDFrX5tKYhoTN8QFKZRCTFqio6iW6K6So9dY9xG1ceDzfXEP) |
| 89 | 05:57:59 | [2PzbXh](https://gmgn.ai/sol/token/2PzbXhNva8Y1gcbvh1kXGPFybS4XDUyuirrwdXVbpump) | 8.5% / 3.46 | +6 | BAM `Fc6NNd` | time-limit 0.9 s | **+0.0286** | [buy](https://solscan.io/tx/4ZBLNxS2ERZL6Xq9q7ydobKihoozhoiqAvDEynw1tQbtw6UknPMy33kEowef1qDof3q1s61QGMZudJWAY6vZyhkJ) [sell](https://solscan.io/tx/3G8wNtamUum85N5es2ZVJMJTUdRiGxBjxY1FDxHTbCJDeKVNqvQ4jYjHmzLR6FfKr2gG9Ftyt41QHjhnv639ygB9) [whale](https://solscan.io/tx/5gX9jcJQgi7CQkVDzt9KwRmmx2v49Wjq5j6CGd7eWeuH9Mx8iPJxr5fy5uJnbMvxnMfVkZd6aTFjx9JTffrjdUJ8) |
| 90 | 06:01:46 | [4jEW5o](https://gmgn.ai/sol/token/4jEW5o2LXb9odQgdHShxwBi6xPUaQU8dqFpeUiQPpump) | 8.3% / 4.15 | +10 | BAM `5EhGYU` | time-limit 1.1 s | **-0.0116** | [buy](https://solscan.io/tx/36Mn8B1htWagsg2HncGMqKMcDAbYG4xedy8f8Njbiz6tTWsx3wF1GvfkgFkqCWLB5aEa3F24biwpaVg6j6XzJV4v) [sell](https://solscan.io/tx/2QqnvYJa6qGhoFwMvuJJx1ZDbjhC2RCRCKatQRgnF1hjr9WyGzJTH4Tzd4YED7ok13o5tpEpy15KytCdgRrNr7vW) [whale](https://solscan.io/tx/4L5PXN8hmX6DZibncyQjHU5Lav9UY9KJLt8y6bdqHG83PN5x2BRW4TeTHjk6cJ4Me3CfKShidLQHuk7Cfc41mNW2) |
| 91 | 06:02:51 | [AuYSxY](https://gmgn.ai/sol/token/AuYSxYfjVr9yaj8sm5Ce6Go68hf656YsxCNxzW6Hpump) | 6.8% / 3.46 | +2 | BAM `DRpbCB` | time-limit 1.5 s | **-0.0119** | [buy](https://solscan.io/tx/5voNvUy9yetk3UpoHdGudiQgyBtFgVwGUTpCCCJxjR2ztsEUNmxpfixRvg8gFqUZ6QrKPkxbG2ep5JHnEGs36bXL) [sell](https://solscan.io/tx/3Zrm6gy1DpiNrEW5HqQ7YD3gNEteK24W6xc9qMfecqwiv56GewFKizv5JLyJy2nJ7gvhpo6MJYH2tp7ccJdy9Uw4) [whale](https://solscan.io/tx/3QGoH5JuBPpbZq2se7vC5AqYviyNRXndKRwAEXt9j4KmWg7VyfaZhWS5oXRUdk5ZmJVXyx6AQ1dpBLgXHAXUXUSs) |
| 92 | 06:03:11 | [5R99Zo](https://gmgn.ai/sol/token/5R99ZoWzv1q2QaYKMeUDtk5iTCaTwXjRaz1jXiWepump) | 10.4% / 3.95 | +2 | Harmonic `shftkx` | take-profit 0.5 s | **+0.0322** | [buy](https://solscan.io/tx/31WRYUPEaSSN82iFPnqCBboxhyQ7CxUoaoWM2jejJAxjA8HVuNGrFghtXtis3Z2DDmEdM5qxwLhbvgjcnEKXvskV) [sell](https://solscan.io/tx/MTqXjPYkGFSKQan3rUtBag1hMsYYiERzKAX5H7VLLfVWAv67yxP3aQVeRfi3AajwCkLEBnvA1ZyDnRVG3XFdH7s) [whale](https://solscan.io/tx/3MigCVhCeNCiS9LHckmzzwYKkvydBekDuKr1BAE2Xh35vYuRM7UacGWETZcbASsJAdaHWverpSwouWe7mENF1BsH) |
| 93 | 06:04:51 | [7ktkHD](https://gmgn.ai/sol/token/7ktkHDico8Dbgan899WccM5vmLvDcoArza8SdBWepump) | 6.4% / 2.96 | +3 | Jito `C8Bey3` | take-profit 0.5 s | **+0.0353** | [buy](https://solscan.io/tx/3vcCoyBKXCW3na1R4KSp54Ri5A7LYYyk3D5dX6jjKtpevwbCUg3vV6UGcjfnNVSfic8kkWyopTQzpK78CTitN8Ns) [sell](https://solscan.io/tx/56QUSx9Ef9w1XQRTnRrHtbZrzqwtweJprzBcQmtQomEr4quPMe4UXCWyrQoVatqSfLEBbe9c9w7Z2LH7QbxP4mjR) [whale](https://solscan.io/tx/3iPH5a1fXkzf8rcrvAUNzxsXjZJ7BERzkusJ8cC5QdoZzLfUZy4P2khtCyxSP6CaWbSbn7pedDNUfUmnyMxU6z1s) |
| 94 | 06:06:19 | [BVG49M](https://gmgn.ai/sol/token/BVG49M5Mh6bf1yVUtNvnSVnXDo793gZRVMrTRMn3HDeG) | 6.9% / 3.03 | +1 | BAM `9AW87W` | time-limit 0.9 s | **-0.0414** | [buy](https://solscan.io/tx/64MrhkaGdaNTxNCtbtGFUnumJhhzoggT72iprrXxCYSquhg4Qpx325UU8cYePN4HPExcfdatxuDhBg1ymi1gCni8) [sell](https://solscan.io/tx/hvS2UcZ7h4bFoSdyUWjbfvmUN859pam946RgV1bvqo9fcaBTi8tTwScnSdSUzvEshZ8UYz8awmTp8Dg31PfSVPK) [whale](https://solscan.io/tx/mUcHLCRiCZZEC2aNKJXxCHiJ9bQ6YQaE1g99gXxHUk4nRCp1sa7xhxpsBu9vXjNr2NHZHuyYGZGfE93EjMqMfTm) |
| 95 | 06:08:56 | [88nZue](https://gmgn.ai/sol/token/88nZueCFZS7uZdmHsbwzgEyKwXYDYJ2CNno9nrcwpump) | 8.3% / 3.25 | +6 | BAM `dcntru` | time-limit 1.1 s | **+0.0415** | [buy](https://solscan.io/tx/66RSCvgwgZSFrRrqtiXbxtNMrFvVte4qEDx4ZAWMnczaNvavKojjeVhJ5chqthVXYdCPRJnteQnjvrWgpJjcQRg8) [sell](https://solscan.io/tx/2hYT5BYfqmW4h5ALZ4hvvr2w8jUfhyYeYv5s1gZxjwEFXYW5AjUiMDs6PkhLmCNUehgLxZxvQmwmvVSSSxmdbWoq) [whale](https://solscan.io/tx/5n4Wod6k1MoRGN6x9ZPrLfSqcFhfMuZ6kMbqQgfcoDyYmhnhF1MxHaJFMerCwLepXqnFUDWhppxjbuPYSFJPfmSz) |

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 16421 |
| Inside the envelope (age / drop / since-buy / size) | 7615 |
| Picks (score above the threshold) | 229 |
| Skipped | far_leader 146, spacing 37, presend_armed 6, presend_position 2, presend_position_open 2, no_launch_accounts 1 |
| Buys sent | 35 |
| Filled | 13 |
| Failed on the +5% guard | 22 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 13 of 13 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 03:00:15 | [5FFhP5](https://gmgn.ai/sol/token/5FFhP5PUeLg3Y8fAMgL1cLryVmtVT4T4PLk8srKM61RL) | 0.35 | -0.53 | 10.39 / −30% | 7.2 s | BAM `6TkKqq` | guard fail | -0.0005 |
| 2 | 03:00:26 | [551iiZ](https://gmgn.ai/sol/token/551iiZkjwDzFPvqtDS2L2bbDZG8YaT9CLHtYVKRQv8jR) | 0.35 dev | 0.68 | 11.24 / −44% | 3.6 s | BAM `PAWsME` | guard fail | -0.0005 |
| 3 | 03:00:59 | [BZHtQf](https://gmgn.ai/sol/token/BZHtQfm323VFuDJsnidnuiSJK8c4cfqLYK8i855Dpump) | 0.35 | -0.38 | 1.19 / −7% | 6.2 s | Jito `GnC339` | filled | **+0.0294** |
| 4 | 03:02:51 | [32hD2z](https://gmgn.ai/sol/token/32hD2zRVDEnmGsfVXaPKe8hEE54mtKC9Z9suCLiWpump) | 0.35 | -0.81 | 1.78 / −7% | 4.7 s | Harmonic `EkvdKh` | filled | **-0.0084** |
| 5 | 03:05:50 | [7ejmCP](https://gmgn.ai/sol/token/7ejmCPY9dnbr6aeCSQrVQLxJu9rYfzSa3HHR3ZAepump) | 0.35 | 0.19 | 2.42 / −11% | 4.7 s | BAM `HbidP4` | guard fail | -0.0005 |
| 6 | 03:30:12 | [3tMXAQ](https://gmgn.ai/sol/token/3tMXAQi9Pm9vWnkKwdW3uuJnQSoRNDTo64mDVY82pump) | 0.35 | -0.37 | 4.87 / −15% | 9.5 s | Harmonic `AMukCL` | guard fail | -0.0005 |
| 7 | 03:33:40 | [3DGfcM](https://gmgn.ai/sol/token/3DGfcMjTNMF6QDycNXTBFkG3De1GLXT9afHkRBCtpump) | 0.35 | -0.74 | 2.57 / −10% | 5.5 s | BAM `vALigX` | filled | **-0.0046** |
| 8 | 03:34:42 | [Ewt92R](https://gmgn.ai/sol/token/Ewt92RJZRKTtsMSwgvg8wmiCdoPWwPpddKuAQrxJpump) | 0.35 | 0.09 | 2.31 / −14% | 5.7 s | BAM `4QNeka` | guard fail | -0.0005 |
| 9 | 03:36:06 | [4bsWrm](https://gmgn.ai/sol/token/4bsWrmR7DpwfyFMLkA5s1hJhGx36THiRHFgMnP9Ypump) | 0.35 | -0.03 | 5.34 / −13% | 263.5 s | Jito `FLwV8t` | guard fail | -0.0005 |
| 10 | 03:46:54 | [HrXZgt](https://gmgn.ai/sol/token/HrXZgtu6Xop4rx1XVSUwKhdSaNQQ77iXNroSbBqdpump) | 0.35 | -0.37 | 2.22 / −12% | 1.1 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 11 | 04:00:48 | [Ftn2bz](https://gmgn.ai/sol/token/Ftn2bz9eFiEXDGYbCq17KgqK1DSufSBnoggjmwN4pump) | 0.35 | 0.18 | 3.29 / −12% | 6.8 s | BAM `Ninja1` | guard fail | -0.0005 |
| 12 | 04:13:15 | [Bu5Mje](https://gmgn.ai/sol/token/Bu5MjegMYLJRduS1jdJTwXEtLnEsXNMTfzNK1HPNpump) | 0.35 | -1.09 | 1.89 / −9% | 30.9 s | Harmonic `A1vqhA` | guard fail | -0.0005 |
| 13 | 04:24:36 | [45D5kX](https://gmgn.ai/sol/token/45D5kXhdjAGYJaYdejeutWWEL1tAg94wH6vLd6NGpump) | 0.35 | -0.93 | 1.96 / −12% | 4.0 s | BAM `76rcGH` | guard fail | -0.0005 |
| 14 | 04:25:23 | [BFmqKb](https://gmgn.ai/sol/token/BFmqKb3BqkP7QiW9pHTgMJo2SdBng8HStwz7wQwpump) | 0.35 | -0.29 | 1.78 / −10% | 5.3 s | Jito `G8kUFx` | filled | **-0.0124** |
| 15 | 04:30:33 | [CFUYJT](https://gmgn.ai/sol/token/CFUYJTNsiZt4G99WAoYW1QqU8ruJqdK2AJxmbMe3pump) | 0.35 | -1.13 | 1.91 / −11% | 8.1 s | BAM `AWcCdY` | guard fail | -0.0005 |
| 16 | 04:32:53 | [E3Vqde](https://gmgn.ai/sol/token/E3VqdeifUCcqNYhMcKCWguYuPE1nAJqQnXQ88M6spump) | 0.35 | -2.25 | 1.88 / −10% | 9.3 s | Jito `7cVfgA` | filled | **+0.0034** |
| 17 | 04:45:15 | [9wXito](https://gmgn.ai/sol/token/9wXitopPFZ4o3s6EwbtbM1sm4B8feiLhgDX3Zjzxpump) | 0.35 | -0.21 | 3.62 / −19% | 2.3 s | BAM `AWcCdY` | guard fail | -0.0005 |
| 18 | 04:45:16 | [BwBbrk](https://gmgn.ai/sol/token/BwBbrk2GrJkxr1A3ei28Mk65hvECMUVbRqP4TXVDhnUk) | 0.35 | 0.76 | 5.44 / −19% | 42.6 s | BAM `AWcCdY` | guard fail | -0.0005 |
| 19 | 04:46:50 | [8s2ewA](https://gmgn.ai/sol/token/8s2ewAUe4frpzLrqLG4WV6fo4h68epsq8BFmQTmqpump) | 0.35 | -2.22 | 1.12 / −7% | 16.8 s | Jito `5pPRHn` | filled | **+0.1498** |
| 20 | 04:47:16 | [RKor5T](https://gmgn.ai/sol/token/RKor5TpK3jF7HYAnTFAKyCj99ewneXvN1MZ3Ftrpump) | 0.35 | -0.12 | 3.11 / −17% | 6.4 s | Jito `74MzXS` | guard fail | -0.0005 |
| 21 | 04:48:40 | [2Ew1GA](https://gmgn.ai/sol/token/2Ew1GAyFdLyapNMWRi8pLXt4G1QMNSCfBtuXCQy7pump) | 0.35 | 0.44 | 5.70 / −21% | 4.9 s | Harmonic `EkvdKh` | guard fail | -0.0005 |
| 22 | 04:48:41 | [2Ew1GA](https://gmgn.ai/sol/token/2Ew1GAyFdLyapNMWRi8pLXt4G1QMNSCfBtuXCQy7pump) | 0.35 | -0.20 | 2.74 / −11% | 5.9 s | BAM `6WgdYh` | filled | **-0.0305** |
| 23 | 04:53:45 | [2xr8Vw](https://gmgn.ai/sol/token/2xr8Vwdh2nsGJ8egfdqL83azW5TVCr5bNWdXVxoV6T7T) | 0.35 | 0.09 | 10.77 / −31% | 8.7 s | Jito `HH5dA4` | guard fail | -0.0005 |
| 24 | 04:54:19 | [8EaYTc](https://gmgn.ai/sol/token/8EaYTcbFeKW5ZLuF25BhVrtk3EgaqXSB2NJWcfQppump) | 0.35 | -0.29 | 8.27 / −38% | 2.1 s | Jito `2Df1aL` | filled | **-0.0256** |
| 25 | 04:56:32 | [CswnpY](https://gmgn.ai/sol/token/CswnpYCBMfnGruTFQxCT7vBkjFWnBZ2NGSYbWRG6pump) | 0.35 | 0.51 | 3.74 / −17% | 77.8 s | Harmonic `XkCriy` | guard fail | -0.0005 |
| 26 | 05:00:02 | [FSA6hu](https://gmgn.ai/sol/token/FSA6huw8m6DP4RUboqJxvpoC29cPA4ep5T2ak7QQpump) | 0.35 | -0.22 | 3.01 / −10% | 1.9 s | Jito `5pPRHn` | filled | **-0.0115** |
| 27 | 05:10:16 | [Bq1Xz9](https://gmgn.ai/sol/token/Bq1Xz9YPZJeWvH1USkqyxDZi71DBR7mzRvd7Ghc9Z1o6) | 0.35 | 0.24 | 4.01 / −22% | 3.6 s | BAM `CjmXSa` | guard fail | -0.0005 |
| 28 | 05:25:25 | [9iwFdR](https://gmgn.ai/sol/token/9iwFdRxvSW5HEcffSLXnAHioA4UJ2TAqLgyri6Xwpump) | 0.35 | -0.13 | 8.29 / −20% | 88.8 s | Jito `5pPRHn` | filled | **+0.0241** |
| 29 | 05:37:32 | [AEgyKs](https://gmgn.ai/sol/token/AEgyKsnTUBajdZDqqX5MWL73SUhvKLC4NqLnhKvYpump) | 0.35 | -0.10 | 4.47 / −14% | 3.6 s | Harmonic `2m1A2W` | guard fail | -0.0005 |
| 30 | 05:44:53 | [H5bhNH](https://gmgn.ai/sol/token/H5bhNH6TzKkTQAmNVPFuSpQDwpFbyC6zNabsETipump) | 0.35 | -0.52 | 6.80 / −18% | 94.8 s | Harmonic `GoeW4a` | filled | **-0.0020** |
| 31 | 05:52:11 | [3jxNoq](https://gmgn.ai/sol/token/3jxNoqQwjbxjMYwCJxNaF6MBgQWdZAdrx5XKCHispump) | 0.35 | 1.10 | 3.72 / −15% | 27.8 s | Harmonic `HTeRsa` | guard fail | -0.0005 |
| 32 | 05:58:16 | [9dGiae](https://gmgn.ai/sol/token/9dGiaeXU1kYVXtv2bSFr9zF5hL5E5B9eeyizRxEspump) | 0.35 | -0.34 | 3.10 / −12% | 13.8 s | Harmonic `2m1A2W` | filled | **+0.0052** |
| 33 | 06:04:02 | [HohFdG](https://gmgn.ai/sol/token/HohFdG4j7oFvyZMybeDCGHC8roBJoY9uYhs39P1Zpump) | 0.35 | 0.13 | 4.19 / −19% | 6.8 s | BAM `6aDs9t` | guard fail | -0.0005 |
| 34 | 06:04:03 | [HohFdG](https://gmgn.ai/sol/token/HohFdG4j7oFvyZMybeDCGHC8roBJoY9uYhs39P1Zpump) | 0.35 | 0.04 | 2.27 / −11% | 7.8 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 35 | 06:04:45 | [7ktkHD](https://gmgn.ai/sol/token/7ktkHDico8Dbgan899WccM5vmLvDcoArza8SdBWepump) | 0.35 | 0.30 | 2.30 / −12% | 3.0 s | BAM `A4hyMd` | filled | **-0.0114** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 32 | same | 6 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot+glaive | – | – | [buy](https://solscan.io/tx/2XbZ3uEj4D2upaiXjY6gTBi6fxH43CQQ5rAG7BSqwXdxRP55Wde83jioj3zmvDfQeX7TgtNKEVqAef38q9LRTyax) [dump](https://solscan.io/tx/5nB1GSSG8AKzPud6oTghaGhSBY3FtKcBdFR9P75shnuQYvLVF8Zt9w8hpNyzW6bjaupjjEXRdZPGfs97oQc6AGMK) |
| 2 | 32 | same | 4 | **bolt** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/QKqZNVNJJDEXfik5b2FTP4QzDNW5YxnhDSw4U8gbEXYahsYSHFfjm7W7NthMPzVZF2cX2ELrRBdiaqzfqkBonTZ) [dump](https://solscan.io/tx/4oZqBc91mkF84usFKm9j2de2FRYY2KqNDAN2hUgPztBVgM5RCZnkUaqmXHAZe7SktwP23YYjipFqTJqQ3ZFcdyW4) |
| 3 | 9 | same | 0 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/3eqUEYdcAGx2wXWPHLQkDsECxVsgEAuz2DTZ5NHJfz3XDrkDPCJkqgRYd5612sfFsqWXo2TEfZWb3KDk54oRc22w) [sell](https://solscan.io/tx/4pRq7BNUysaUqWifbwWTkefdpQRqLftaDQ2GqR9MJT5eb7BenTTvUmWnUN5BGYmsRUordc3isMQkKmexsb4dJF4K) [dump](https://solscan.io/tx/5frnaYo77iuc37pPQfGUP6vHYVLkaP7p5FB5ypzdDTRABQVPhSKDSWrrafykLW3pvR1useW9wgbvdnLhXY91AGWz) |
| 4 | 24 | same | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/3Dc9rQSK52jLvyU3ASEyRo8ABvCoTu5gcS7agN4tAVaJmTfS2i7V5wodpYFTeBo9q9u1uAC37KDd4vue2nQgBhQF) [sell](https://solscan.io/tx/5Cq9uoFeu1kRCdMnMU3iNvu5UgXBW1t6F9gLr3KdpEvswprRw67mihAFTeKg45611FSV8Vm3FUmRjDgMtdJoafVt) [dump](https://solscan.io/tx/2Zx2mAhbDjhmFVk9HCg4mY5iJZXYPRjwtPL48k2UncVTH2dczB3pxJhrbeTFf6DhiiE3zEKLHFN9mqHGdXwrBpjG) |
| 5 | 19 | same | 2 | **bolt** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/2oNDgrtD8cgFJ7ASg34vnD26jDM4VtS8ZuRaiyeKcGd5a4CwENSAv55fxywNd4c7ecTWVtdF4jMVsYJ9Ha88wUk2) [dump](https://solscan.io/tx/2TpEXV9CsF4SxTkzZDDbXncPu7L7oMGSKh5wzpsiowjnyv2tenzD8gtsmmMLg2KzwqBnFxBtj22APxbSZhywag5c) |
| 6 | 37 | same | 5 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/qgvdQXUuavmnK4P3HZC7wXzXWcSgcaaXDomgyFXvDfYsrPD3XZK1bfZ5dNpUkE8e9SJYAkxqQ3h2eEo4SBqs16F) [dump](https://solscan.io/tx/3QCScQtrst7CuTu3Uz3tkv1cZArMX15cDJt7R1nMC88Vi8D24MY6fubLEk1taSXdeqNGxwxEu2F2Wjpx59xXjUwv) |
| 7 | 16 | same | 1 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/skWrfwGAnenrQ1LnJHZ8sXEhuZK3YLQvt6bWQjADjiW8QdnKSTZEmvZ8Sao8xtPZ1v7ozp3hWCiqG8DFy9Dg7Fg) [sell](https://solscan.io/tx/47vb37FZ1o1SMcSoWi241CHFCkKRr6QCLay9aSHPrzwqaF1aHJP1ZH83r4TE9LLsC7CRayeMEAzd7ed8NDYpBY6d) [dump](https://solscan.io/tx/2H2X7iBeXt1JjEDT4Crd2yN8eX4E6jTQGspZiSx1ECriZamZWrNb4S63fSpoUh8LxQEU2pKd6NSFXzuKfsbEb2PB) |
| 8 | 36 | same | 4 | **solami** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/4EjU1u7uQDfr4ikzfYBb6WuiWNyNgBGK5RQruBLMtCnC6pHv7RAmrmcm9krfuaaeRExPxnJTCVACNKzB4uCcjHRr) [dump](https://solscan.io/tx/5dPYEJrRJ3hZYzVhaQKNEFg2TzajGSjuueFo4jqvxT55omxycBSoXTvyRHyNFFiaqEGfwNV5VtpCW779zs7DPkmQ) |
| 9 | 139 | +1 | 11 | **helius-swqos** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/Bq6HGbtyVpXKia1HkMDjaCcWF4ycrJAVPYEmL47TFvLswbbQNmQpD4UxoVU3HKNK1qAG944ErUFMPUcEpynJEGR) [dump](https://solscan.io/tx/2b87ZHhyANn1zxR6xadZhEAqCguQwA5dUv6hBGaVc5p9KsrP1bSPWuNPtmykHMaW4Vawgy6YKVjFsEby2uoYPmFH) |
| 10 | 238 | +1 | 3 | **falcon+falcon-udp** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/wVD56JszFXq1auqmv1vqvu5aVCu6MR4kTaAxHWdVsmdxZhGUMKMPYHg2dhGMHenRYaFMsGpaXu636iay3p6269i) [dump](https://solscan.io/tx/5cUGpVfWPbJR79CsMZbSM3WwhQkf5u4snLwbbpuvUGatU2BMWMoyJH2r7Q16d6chHKZmTH2tuj12bZQ4aA2MSaye) |
| 11 | 24 | same | 3 | **helius-swqos** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/Gi2G45Wv1QhE8A5RduEeCzKAEM1zUsMLHiHmNJmPbFccTrBHxTxPiLXQbcRS94Q2FgguCLnVY4k5WAcZp7YKcbi) [dump](https://solscan.io/tx/2tmUPpX7bgMRnGg7qXwd81g1x7kyXLxMrJsfmF29Fri344xmWWAfM48BHZnKc61TEnJmJcrwgxXcu4vQM8KZXWhv) |
| 12 | 41 | same | 4 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/2JAXuAfp4JXe1XNpvYwSm22YF5p18B2xoJPVi1WqpMzUs7rt13wYx5xhnRyGdAHeqPmakRv1XUGaxvEMkeUZ42yN) [dump](https://solscan.io/tx/323MwiG6g8KY7gSzuyhuiFxTdWgYPa9mPVr75qVheSSMNsezqVjcUcyaUmRorarTtWM9Xkd3ytgr48m77gyvU88n) |
| 13 | 32 | same | 1 | **soyas** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/dLqugE6ug3f8tNynU9ytKcUKe26KwWavwJ3tJYWUhuGEFyUJ5SuRFGAfaZdsVqRzJdWsyfMdugdgDbqx6Js7Kzc) [dump](https://solscan.io/tx/4DThSw4cDCHnc27EitdUay7yKFQrGiEzbJgXbAqazepjhT25yrDctQWSqJzc6enP5cfDEQAXEFXu9ZwDnVbM8s9U) |
| 14 | 127 | +1 | 2 | **staked-rpc** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt+staked-rpc | time-limit 1.9 s | 1 | [buy](https://solscan.io/tx/5HSi19GPcye8Auz52R3ZcH7cFaGqobbFd5wPg41tWRwwD4hB38bWVwEmSSbnjF2SJ3runeKJV2QHw4YBqtUnM1ir) [sell](https://solscan.io/tx/3ucnT4oiGycu7a4g7bLckQmZwLAn8ku4mNBuPDdDqRGgYmmboQawH9LWzcjDmYEecWyXYfewT8i8DrfPG1WG2tKN) [dump](https://solscan.io/tx/2fJccAEpc4RJzvhVPcUHg1g7D9qAHDHxvVPHDxkkL7eBv4MSmGzdzucvsbzv2eRUCTUc6YPoSanrMPShSbmBAKP1) |
| 15 | 18 | same | 2 | **falcon+falcon-udp** of falcon-udp+landx-fra3+nozomi+helius-swqos+bolt+falcon+0slot+glaive | – | – | [buy](https://solscan.io/tx/4Mn3PM2JZ4cdHvWbr3ARDjqzZr4AWZGwYQ4aJUz3gdUcTBSMXV7EivQsE8PVnwREo3N1qjyy4AvJ7mMvyz6pmhvv) [dump](https://solscan.io/tx/ssHUuan6m8QVMuZtygvf3d6omXnb58LGL4NRARPMtqS1Yp3tZx8vCRvpnY2TAiA7cQjzYGkB9CdnEdvnqfoM5hj) |
| 16 | 25 | same | 1 | **glaive** of falcon-udp+landx-fra3+glaive+falcon+helius-swqos+0slot+nozomi+staked-rpc | time-limit 1.2 s | 1 | [buy](https://solscan.io/tx/4pgZ3FjGpmPiqfJzpyL6QQsp4bHoEaygeURPUJKXPA1u1BisHHfWf6yvA3ikHjbrmDnf3KTNFNK4PBcyyTq9WHUd) [sell](https://solscan.io/tx/uVNuGPVyhfh5o1KVcoeKk7q4Qcgd3tKiAsg6rpQiE5jRCwzowed9cDJVn6GMUNpJCZaXBnBgEbxhsZzp9GEYDSm) [dump](https://solscan.io/tx/2PfuhQ4gMK32sSkSGCbZ4Wy3jy9wv4o5SGtvaic6joG6nWQaLy6hk5sYTXdm2QgzSLakxNEG6hRLDYJa3DNTQP83) |
| 17 | 24 | same | 2 | **bolt** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/3ihFapEn4pjY3jTfGwxoFnxwR2riDYz4oZpR1AwhG6SXNazXuom262KjKtbkGeebGV7L9JAvKAZTy5VuXzyvWcEC) [dump](https://solscan.io/tx/5G8seEVC1D6TsQDxebptVVynjhx2KovyQdYakqfKne8CFvzMfADRzoj7EPBho9WhLWwxctkGvhtde89ccRqQLDia) |
| 18 | 20 | same | 9 | **soyas** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/3VkqGkDt9qVWL9HjmNLBT5FReneP5QMij55zykm4tPmE9Ki2mHSf2QWH3DMJhsNJqeb1V5epcGPUJYN4654ZUbah) [dump](https://solscan.io/tx/3dQ7vwT15iGCgZmuEcByHGzGZJEk69zPKmK37yGspcyywjXjR5CAPVku4bQHtjw4LCQHXAHKdjGwPYTf3FJ18uVd) |
| 19 | 84 | same | 2 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 2.1 s | 1 | [buy](https://solscan.io/tx/3GmmavhuCNWs9JH2jGyyx2yGh7jyrWYtyCiZFgqshQkU5MFZtpsutFTuadHuWb7BbLYr3B5BwtWiVSBLhHZJT3op) [sell](https://solscan.io/tx/2myBgrXQH5JJaUptHfGD4xwP352J7CKv259JWTHX3myJLw65jhEbuDzLxMXdBXfdmgZbNzBL8cbonzuz3gkhAjjU) [dump](https://solscan.io/tx/612BgxPesAgg2jDswXJWRpcVQfoZMa64DKxn78thbpVKkJXru9iyuedPeTEraPLWRAu9kHUECwJzYYmbqEJBtsVm) |
| 20 | 93 | +1 | 3 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/3S4HeW7DDLQb7LrH65saAmaRSJQD1Gxoz4SN4MJLcVrbYkZncRqkNmiXYzhwKpFXxT6wFzfBupJazonAdagSbssh) [dump](https://solscan.io/tx/38WQPdXVi5KcLnQLspYEDrecyfFt7xFLYpS3sE18BVVmdQoMRvXAtE3L2xpVJqF7pevB2d5RB6xcdUKDTwKQnwdB) |
| 21 | 153 | +1 | 7 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/5eCC8qXXgGjKU9pwKmL62XHnM8zKTFYrzBYRdFsSgQnCc5CjsLkikBRVdEKSHUcXWmhjT5E4vLHph2t1RP7xKzGP) [dump](https://solscan.io/tx/j9U8NT2mvnV1TL7dLkaPXWxDBnovURtMqyuuhSF8t3p339UpTbK9WcFt8Skyn85g5y99ha1fcV2vP7oJNyajx5C) |
| 22 | 29 | same | 3 | **0slot** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/2MWD98xwxeQ2msVSVWKQJNv1VaGqus56XJjFeZyC57Gpona2H7ZpGciaGjY1D5HhV5KrFahNocjdnSdneZaiXyfi) [sell](https://solscan.io/tx/2YJzxshE12bYkVLHurDoXHjvaYPZohmsF45hBadWNjpYedaxZrZ9H7fbXFE6AYTY8uVG5RJXe7pqnCLUxY5nPz5X) [dump](https://solscan.io/tx/4cvMEPatf1T11mRdEZi2etrakJet8ykN2WLpmvbLbEXx4UXbpmyDiGAA2bM7ZWa9Dh5pbPo3HgwizT5iMUG1ZXWV) |
| 23 | 93 | same | 9 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/2o6QcJoCNAmT8JyqCRZ19jUPyX4RUMSxQq5cRXshare7B9QF7gfGk12Hpv9qmd6CV94gTVkKTw3Xpus5kmKbPbqN) [dump](https://solscan.io/tx/4y2xfXYFyoRDPGSFgpiXQYMqQ4N14y4Xwg5Wu71iJae3jX3GTDyKwdVfCxjH9iMGvbTUCVpwXam3ZHqj63NT8gMg) |
| 24 | 51 | same | 1 | **0slot** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/5v2dHousA637njkwExUEt9E7WBboVVM2w21NiSbBtffYpHEC2SY5Wcv7YYncZpTqmKQGq1p5UW2MSdkMXi5gsWXh) [sell](https://solscan.io/tx/m6Me5QiYHWuziy4Q4gjVr1FpuMVLUVnguF9DSYJXP2mjbFLnUf9r1LmYkpSvE2UBmeqiX2kyxBSSLWCMagmJbFE) [dump](https://solscan.io/tx/2qw32DFrFcMkKyHZvmrGc3PKTtvLDpN9JaUqtaFcQXFr9aywP9QjwAJ1doC5CbdFUVtq9ZvdaXRQY4SJfHjkiwqz) |
| 25 | 36 | same | 5 | **landx-fra3** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3gyPAboDRBbpXtYkKKc2YFTxPngr1y5e7ZN138K8TjoiSZU8kJo1gRM9K2XnZmRZyNFNF31DMLsMUCZAjxVzxfdg) [dump](https://solscan.io/tx/58L9PCxdsdS77dX2nBcK4YYSqN238fFBUzTghMp82qjNcb2pbf3R9jf6BJTT67XoAKsyHhg8rdVyCSSAmoYXsafz) |
| 26 | 112 | same | 4 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/5YgdoRSoSXZFazupay82tTJwr98ySfbx3mGEf5Kf1Fg7a1NHziCKVT5gXzTodMmRRoZboRTEXyMj9ELWoK93nrLi) [sell](https://solscan.io/tx/564ZrcXvEK1vfJuudqB6guFTzGK5b1TMeVuBHkq4LMdZisXsQ8N1CpyMZBeFw2Vz1GLFeuKDtpy42CjAW1q4WjT5) [dump](https://solscan.io/tx/4Yo4EMXFyqk8zSAHu4UDEiDpP1Y25T9YmyeJFFEHRuhT8m5d6FLLm1PBBK5RAYMytdWdawUtd1cothG6EMkkt9q8) |
| 27 | 46 | same | 2 | **helius-swqos** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/g7RM9J4ywyDkc6Tu4cLcWWrpNoNKa9RXugraeirpWXnD4rHmGbVBa3QECr9yUkYja2HSUANHkxFUHuDkHtZxKCH) [dump](https://solscan.io/tx/2kdGn2iqTFbPuMjY48xAuKjHpCkSozYrc9Qai2G3QAeomHhXvDi2My8qzPyQvsuXKQj8uDC6ttqPQf3tbUtAn892) |
| 28 | 120 | +1 | 3 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/KBwtiUVRcdFmvnLEq5VFUWh3QazG2ELWhut6v8qM9CWdgbJsUrnfdnvqAnBTSs5tPVFgt5EdAYcAN5yFiBHQGX2) [sell](https://solscan.io/tx/5Qe45FB4f9CxZNQWWAmxkGeyLCfC8gErJGethwRaq5pxFaxxtBsf1RaZcK2jLZPt77XgLjrDXv8NRo4idAWJA95j) [dump](https://solscan.io/tx/2zeCew5rzbP9jqNCroeUNsW7PzGMeNQ1Zay5mASRr9rAMZrq1tLu1fswtxxxbvbL12P8F1NpPCAYtqoFE1ZAqT4e) |
| 29 | 35 | same | 1 | **0slot** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3PVhpJLCH4piLMRYGUAtzK5GPQAkqiuPwC75oFxG9ijpBKFsxBxKhxHhejoKZ7W3SVW7ZwUCFCKC7THJVFpkzeBL) [dump](https://solscan.io/tx/eaY2CNHzvyejhDb9qUJNrxZcsFgAJxQqc7MijNeiaGHZezzRrL4Po3RYCRK4yqLdZmj6xiFb7LjTxhAevzTuLYt) |
| 30 | 37 | same | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/3ySPsyd1J7PdwwVb2vNFV4CXVnXd9HiEyQQidDKNtyRvgsHMSgEsnxUuj4hm6Luv1fQGjK1ykKg9QS8Tv6YvoxpE) [sell](https://solscan.io/tx/4f9kpUj8ib56gjEBGpLGNuzgCV9DGsDZEf8y2gWYPFdyHKLXMwwstUPX4RvHrF4A6R7LinM7Y9DJvZoQxyyPQoqx) [dump](https://solscan.io/tx/4NrGPzUr4AuT7aNhmvqEfjAT6YXiWDpuvNAkVd8PQi7ADGBFCVAQGMNXuhXxxek6CUqqTMRTpAWHhwcvuvYF55BG) |
| 31 | 42 | same | 4 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4qNA3vwGBU48EYK56Yj8JMNDMTVLFtb6YozPUZYrG26dH7aNQ79rYAQ8av8LaoAVpZvdHsZtKz9nfzWPcsgnyt51) [dump](https://solscan.io/tx/5MRKm5hg1kwmMRD8R4ejETYJZ5UnTW5xSCtjaT4jXRwsxZphvZWSuo6WxeHpQEarJamQXPpQXE6mYyhV17DFxTkp) |
| 32 | 46 | +1 | 1 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/4raQPUyUu12N9z1yjvoPuv9aF1GL3M1KPaMAqAuDLfbRiLMx6xm6AYCCsmFiAQwQJGUCXBXDEkuV6VxTHdh3N5K1) [sell](https://solscan.io/tx/2UTBLAjhF9kHzVLsnDxNLiwAcqcp8jprMtS6ysyYyi7iewcDD1mFmKs2k8dHPiYkdsvTh23KkJJfJAFnXs9cH3xP) [dump](https://solscan.io/tx/4KkNYjwkbGAnKkRUVxR678joqmaiijamHpRGgeGm9Q7ySgsY42r8hvxnDKyxmUD5XZ79mNDGEuiadjyVb6okKEfW) |
| 33 | 20 | same | 2 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | – | – | [buy](https://solscan.io/tx/2tkeAGiGsKiS3Wy95ZAKitchb7W4R9Qo95cuQKT3WaJpvJkBzviPcfYaFewm6STmJEmm95CRugsXsV82TK595L6X) [dump](https://solscan.io/tx/3UBazA6JK6y7sLMMkptvBfiGnh62aPepkiWDoK9nELpTjmhfXCETpeT3AodSm9DzrpXkB5zrzaX5T1csFj6nxw7L) |
| 34 | 116 | same | 2 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/XR3TQNHS6egDs462Q1RL4A1updJaR6eBzjLQyaNJ5bpu7cy21SuP26G2xVzuLniAvo1Yui1pURhPTeJ1aWrzENX) [dump](https://solscan.io/tx/2orYj7aDkF3qU8CofpaiABGt8s4DvtxDC2Z2g49QZU8yK7XT4gUfbzrXEmdvMBzz5WVbz8LE7JhfBGJyd6Lm3TrN) |
| 35 | 21 | same | 1 | **staked-rpc** of falcon-udp+landx-fra3+nozomi+helius-swqos+bolt+falcon+0slot+staked-rpc | time-limit 1.3 s | 1 | [buy](https://solscan.io/tx/49zAuQCvL5VmQqCBL4oWdQzEHjwb8GkkszXRR5uQePx567AuM5qU73kzC2jmD7jZ5nu1pdQrMtzcTafnPJvN4u7x) [sell](https://solscan.io/tx/3rKQN3u4RmPw8q7VV3uzLpaoxrj67YBX5ChBEPKZM1R4v8wSBtE4awtpsPjYLiLiyCu5Ro2BGDc1vqm5WmV64X16) [dump](https://solscan.io/tx/5rbhdDSdq1xDFPZLY92JG8GDcDzQqmgQMJTR8PAGB9TzDc2gkKyHUbuyvzyff1ekXsTYwSzZZ62kmfHGzdd4RTR8) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| BAM | 14 | 3 | 21% | -0.0520 | -0.0155 | 0/3 |
| Jito | 12 | 7 | 58% | +0.1548 | +0.0225 | 4/7 |
| Harmonic | 9 | 3 | 33% | -0.0082 | -0.0017 | 1/3 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 34 | 13 | 38% | +0.0951 | +0.0081 | 5/13 |
| dev list | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 28 | 10 | 36% | +0.0798 | +0.0089 | 3/10 |
| next block | 7 | 3 | 43% | +0.0149 | +0.0056 | 2/3 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 03:00 | 10 | 3 | 30% | +0.0130 | +0.0055 | 1/3 |
| 04:00 | 15 | 5 | 33% | +0.0798 | +0.0170 | 2/5 |
| 05:00 | 7 | 4 | 57% | +0.0143 | +0.0040 | 2/4 |
| 06:00 | 3 | 1 | 33% | -0.0125 | -0.0114 | 0/1 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 13 | +0.1057 | +0.0081 | 1.4 s |

## 8. P&L leaders
**Best trades:** 8s2ewA +0.1498 (Jito, time-limit, score -2.22); BZHtQf +0.0294 (Jito, time-limit, score -0.38); 9iwFdR +0.0241 (Jito, time-limit, score -0.13)

**Worst trades:** 2Ew1GA -0.0305 (BAM, time-limit, score -0.20); 8EaYTc -0.0256 (Jito, time-limit, score -0.29); BFmqKb -0.0124 (Jito, time-limit, score -0.29)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `5pPRHnie` | JitoLabs | 5 | 3 | +0.1614 |
| `GnC339vk` | JitoLabs | 1 | 1 | +0.0294 |
| `2m1A2WM1` | HarmonicAgave | 2 | 1 | +0.0047 |
| `7cVfgArC` | JitoLabs | 1 | 1 | +0.0034 |
| `6TkKqq15` | AgaveBam | 1 | 0 | -0.0005 |
| `PAWsME7o` | AgaveBam | 1 | 0 | -0.0005 |
| `HbidP4hp` | AgaveBam | 1 | 0 | -0.0005 |
| `AMukCLCr` | HarmonicAgave | 1 | 0 | -0.0005 |
| `4QNekaDq` | AgaveBam | 1 | 0 | -0.0005 |
| `FLwV8tm3` | JitoLabs | 1 | 0 | -0.0005 |
| `Ninja1sp` | AgaveBam | 1 | 0 | -0.0005 |
| `A1vqhA2f` | HarmonicAgave | 1 | 0 | -0.0005 |
| … |  |  |  |  |
| `XkCriyrN` | HarmonicAgave | 1 | 0 | -0.0005 |
| `CjmXSapt` | AgaveBam | 1 | 0 | -0.0005 |
| `HTeRsa3g` | HarmonicAgave | 1 | 0 | -0.0005 |
| `6aDs9tUm` | AgaveBam | 1 | 0 | -0.0005 |
| `AWcCdYG7` | AgaveBam | 3 | 0 | -0.0015 |
| `GoeW4aFK` | HarmonicAgave | 1 | 1 | -0.0020 |
| `vALigXFg` | AgaveBam | 1 | 1 | -0.0046 |
| `EkvdKhUL` | HarmonicAgave | 2 | 1 | -0.0089 |
| `A4hyMd3F` | FireBAM | 1 | 1 | -0.0114 |
| `G8kUFxhR` | JitoLabs | 1 | 1 | -0.0124 |
| `2Df1aLCR` | JitoLabs | 1 | 1 | -0.0256 |
| `6WgdYhhG` | AgaveBam | 1 | 1 | -0.0305 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1676 (p25 1347, p75 2326, n 35) |
| Executed-feed lag behind first sighting, ms | 0.9 (p25 0.7, p75 1.4, n 35) |
| Buy sent → our tx seen on the feed, ms | 32.9 (p25 21.1, p75 88.7, n 35) |
| Fills: our buy seen on the feed after the dump, ms | 37 (p25 24, p75 84, n 13) |
| Guard fails: our failed buy seen after the dump, ms | 36 (p25 24, p75 93, n 22) |
| Fills in the dump's own block | 10 of 13 |
| Guard fails in the dump's own block | 18 of 22 |

**Which copy landed (nonce fan-out):** glaive 7, nozomi 5, falcon+falcon-udp 4, 0slot 4, bolt 3, helius-swqos 3, soyas 3, solami 2, staked-rpc 2, landx-fra3 2

**Send-path answers (FAST-ACK lines):** falcon 35 (median ack 0.6 ms), 0slot 35 (median ack 1.1 ms), nozomi 26 (median ack 0.7 ms), helius-swqos 26 (median ack 0.5 ms), glaive 23 (median ack 0.5 ms), bolt 16 (median ack 0.5 ms), staked-rpc 3 (median ack 1.7 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 2.46 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 8yYMhuYo | 14 | 8 |
| 9K5QgBKa* | 5 | 5 |
| 9pQQc1xy (bait follower) | 4 | 3 |
| Gx3nQJUe | 4 | 2 |
| 5k2Ckkiu | 3 | 1 |
| 6eVWZbj5 | 3 | 3 |
| 8PgC4ngp | 3 | 2 |
| 5UipEgoi | 3 | 3 |
| 8GPTNX4j | 2 | 2 |
| ETwEAQPL | 2 | 2 |
| 2XyiEK56* | 2 | 2 |
| B4nN6YyF | 2 | 1 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.2588 |
| Pump fee on buys | 0.0562 (0.0043 per fill) |
| Pump fee on sells (residual) | 0.0594 (0.0046 per fill) |
| Buy tx fees (base + priority) | 0.0066 (0.00051 per fill) |
| Buy tips | 0.0074 (0.0006 per fill) |
| Sell tx fees | 0.0079 (0.00061 per fill) |
| Sell tips | 0.0156 (0.0012 per fill) |
| Failed buys (tx fees) | 0.0111 (22 buys) |
| **Result** | **+1.1391** |

Buy compute used (fills): median 76,914 CU, max 94,907 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 100 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getLatestBlockhash: 4 timeouts/transport errors (worst p99 358 ms)
- ⚠️ RPC bh-fallback getSlot: 5 timeouts/transport errors (worst p99 371 ms)
- ℹ️ 4 send-path health events (self-heal), e.g. `SEND-PATH falcon UNHEALTHY: 3 transport errors in a row (last: falcon: error sending request: client error (Connect): tc`
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)
- ⚠️ big pre-send loss Cxoe53 -0.1062 (time-limit, BAM)
- ℹ️ wallet change +1.1367 vs trades +1.1391: gap -0.0024 SOL — about the fees of the 491 pre-send tries never seen on our feed (up to 0.0025 SOL if they all landed and failed; inferred)
- ℹ️ Pre-send END CHECK clean (93 mints at confirmed: 0 sold / 0 closed / 0 held / 0 unreadable). Nonces healthy (8 ready, 0 dead, 35 used, 0 fallbacks); no tokens left in the wallet.

Checks passed: every reactive fill was sold; every pre-send fill was closed by a sell; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Recommended / open:**

- Run 26 started 06:58 with pre-send 0.50, a 1000-fill cap and a 0.4 SOL fee budget.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r25.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r25.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Pre-send (section 4b): the jsonl presend_live_* records (fills, closes, REALIZED, account closes, stops, end checks) and presend_attempt_land (try results, failed-try fees); the log's PRESEND LIVE lines when a run has no such records.
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:57 PKT.

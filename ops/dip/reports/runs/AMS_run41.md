# Amsterdam run 41 — dip bot run report

*dip30: run 40's config WITHOUT the deeper limit, + wide shadow 3% (log), landing-guard + group-risk logging (K4 6%), re-arm 0.65, profit lock 1.0/30%, kill switch start - 0.5*

> **Verdict:** -0.50 SOL: KILL SWITCH fired 03:45 PKT (run PnL -0.5004 vs floor -0.5), engine stopped itself with no open positions. 40 fills: T2 26 -0.200, re-arm 14 -0.320; realized -0.460 (engine), -0.52 on chain from 20.341811. Started 02:08 PKT. Bad stretch 01:16-03:45: deep-dip buys (14.9-44.9% down) into holders who dumped at our landing; log-only landing family caught only CsV2WE7N (and F36E6Xcs earlier). Deeper limit was OFF: its conditions held on 17 fills, -0.64 realized, ctx85 paper +0.00; not the cause. Lesson: a run of group dumps with no filter catching them, kill switch did its job.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.5002 SOL** |
| Started (PKT) | 2026-10-31 02:25:29 |
| Ended (PKT) | 2026-10-31 03:45:34 — kill switch (run loss cap reached) |
| Ran for | 1 h 20 min |
| First / last buy (PKT) | no buys |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 0 → **0 filled**, 0 failed on the +5% guard |
| Fill rate | – |
| Wins / losses (fills) | 0 / 0 |
| Per filled buy | – |
| Fills only / failed buys only | +0.0000 / +0.0000 SOL |
| Reactive bot / pre-send live | +0.0000 / -0.5002 SOL (pre-send: 40 fills, realized -0.5202, rent back +0.0604, failed-attempt fees -0.0404, 19 wins; see section 4b) |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip30 (sha be1496e3) |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.70 SOL |
| dev list | off |
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
| pre-send | LIVE: whale >= 6%, 8 tries/slot, 0.696 SOL, limit x0.88, route helius-ps, caps ? fills / 1.0000 SOL failed-try fees, exit ? |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 0 fills, 1 open at a time, 0 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 27**:

| Setting | AMS run 27 | AMS run 41 |
|---|---|---|
| engine build | dip20 | dip30 (sha be1496e3) |
| size (normal) | 0.35 SOL | 0.70 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.35 SOL | off |
| pre-send | LIVE: whale >= 6%, 4 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 1000 fills / 0.4000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% | LIVE: whale >= 6%, 8 tries/slot, 0.696 SOL, limit x0.88, route helius-ps, caps ? fills / 1.0000 SOL failed-try fees, exit ? |
| limits | max 500 fills, 1 open at a time, 130 min, loss cap 0.500 SOL | max 0 fills, 1 open at a time, 0 min, loss cap 0.500 SOL |

## 4. Timeline (PKT)
- **02:25:29** engine start #1 (session with 0 buys)
- **03:45:34** engine end #1: run end
- **?** start refused: `Error: keystore: wrong passphrase or damaged file` (nothing sent)

## 4b. Pre-send live (pre-placed buys) — separate from the reactive bot
Buys pre-sent after a big whale buy, before any dump. **Not included in sections 5–11**, which cover only the reactive dip bot. Realized = the engine's PRESEND LIVE REALIZED records (chain txs of each buy and sell; the buy pays the token-account rent). Rent back = that rent returned when the engine closed each pre-send account after the exit (dip19+; before dip19 the sell closed it and the refund sat inside realized). Failed tries = fees of tries that landed and failed (6042 price, deadline, …). Net = realized + rent back − failed tries.

| Session | Started | Size / fill cap / fee cap | Tries sent | Fills | Wins | Realized | Rent back | Failed tries | Net | Stopped |
|---|---|---|---|---|---|---|---|---|---|---|
| #1 | 10-31 02:25 | 0.70 | 7,971 | 40 | 19 | -0.5202 | +0.0604 | -0.0404 | **-0.5002** | run_end |

**Try results (as seen on our feed):** 6042 7,265, deadline 451, ata_exists 142, unseen 47, ok 40, buy_6005 26.

Tries never seen on our feed: 47. If they landed and failed they cost up to 0.0002 SOL in fees that are **not** in the failed-try total above (5,120 lamports each; inferred, the engine does not see them).

**By exit reason:**

| Exit | Fills | Wins | Realized SOL | Per fill | Median hold |
|---|---|---|---|---|---|
| time-ms | 37 | 18 | -0.3659 | -0.0099 | 0.8 s |
| stop-loss | 2 | 0 | -0.3209 | -0.1605 | 0.6 s |
| take-profit | 1 | 1 | +0.1666 | +0.1666 | 0.5 s |

**By leader type (the slot leader where the fill landed):**

| Leader type | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| Harmonic | 12 | 8 | +0.1274 | +0.0106 |
| Jito | 11 | 6 | +0.0304 | +0.0028 |
| BAM | 9 | 4 | -0.0520 | -0.0058 |
| Firedancer | 8 | 1 | -0.6259 | -0.0782 |

**By hour (PKT):**

| Hour | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| 10-31 02:00 | 16 | 9 | +0.2518 | +0.0157 |
| 10-31 03:00 | 24 | 10 | -0.7720 | -0.0322 |

**Best pre-send fills:** 9NGkR2Lj +0.1666 (BAM, take-profit); 9uvH2ztk +0.1206 (Jito, time-ms); G2rduvWz +0.1006 (Harmonic, time-ms)

**Worst pre-send fills:** DXvegiAQ -0.1976 (Firedancer, time-ms); DByjN8BJ -0.1709 (Firedancer, stop-loss); 8xrtjATQ -0.1593 (Firedancer, time-ms)

**End-of-run checks:**

- session #1: END CHECK 38 mint(s) read at confirmed: 0 sold now, 0 empty account(s) closed, 0 held / 0 unreadable (per mint: none 38)

**Every pre-send fill** (time = fill; whale = the trigger buy; P&L = realized, rent back not included):

| # | Time | Token | Whale % / SOL | Slots after whale | Leader | Exit | P&L SOL | Links |
|---|---|---|---|---|---|---|---|---|
| 1 | 02:25:48 | [Do5Hab](https://gmgn.ai/sol/token/Do5HabL1DoKz4oxEVhE94NbpysESvcCGJvNwtMsBpump) | – | +10 | Jito `5pPRHn` | time-ms 1.0 s | **-0.0092** | [buy](https://solscan.io/tx/3Rc43MtKwZQSC98qQ3VJYTU87Jma9WT67Wn1rCF5bsjsRxQEyt2EAPZoDajd4ptFHaFMNEZ9gGQtbG5m9mdVdT7V) [sell](https://solscan.io/tx/4S6N8k1FANB8JXo7vxR3nHNjmZoKsNGdnDosnaqvVZSpzK8e6YndU7g4e5iVdPW5tWjF8TXy5MAxKBrGRaVMxT4X) |
| 2 | 02:26:06 | [2EutHK](https://gmgn.ai/sol/token/2EutHKkhB49Ns3rVvNHcapBiiuHGXwBkHeKm5TAq8ZGS) | 6.7% / 3.95 | +2 | Harmonic `Ex1AxF` | time-ms 0.7 s | **-0.0162** | [buy](https://solscan.io/tx/5ck2YY3G3wCRqkS4YvB3RY7Aq8Gv7jWqqApw36Uxd1ymEkuiD85QuvguwWVyRT8uP2zerwdwW6TE2n5JGgFFdyH9) [sell](https://solscan.io/tx/3RMBqTMMQFAt6eHJbarsTFB5sBXSbyuVo6KKDpHdDbc4fqkH5Bur5LWwXucXGUPFpe1SLY9bNn6kAounbmPy756e) [whale](https://solscan.io/tx/4TQKzjQgNZRWNSTUordPgxLYaHtCeWimboCbzymPhS9sVVxy2gGAYLQfWKKPL5hT3ZJmPaFhoNMZa2GikemvVfHU) |
| 3 | 02:26:18 | [Do5Hab](https://gmgn.ai/sol/token/Do5HabL1DoKz4oxEVhE94NbpysESvcCGJvNwtMsBpump) | 8.5% / 4.94 | +5 | Firedancer `BbCQMW` | time-ms 1.0 s | **-0.0632** | [buy](https://solscan.io/tx/MaLwTvUkWPz2UDeBkzgRGwad3Ka3B1uyrMPhQ9oCrKN2ZpDT6rfuBzC6KeTJNFcXyEoRv4aKJRtYLtkksKacNFV) [sell](https://solscan.io/tx/4bCjVB2Kq9oLocJtjHXAH1eaw8VcTY7FJwMHzoAZWz5U6eHmqqkUMfRCGkxnD9U58jdwiM7vUPYamYS2jj79z49d) [whale](https://solscan.io/tx/3eA7UxfiQJdKSjNrzizR7GRLBbjUt22WxmMpXq1CUJ8RZutQn3DbnkXKVY5zDG6JE8XvRKkBz9AmZTUkLzXt8tTn) |
| 4 | 02:35:47 | [9uvH2z](https://gmgn.ai/sol/token/9uvH2ztkaKV2ibwUC7PUfaeWvYgtmSSvSonnKNDQpump) | – | +7 | Jito `C8Bey3` | time-ms 0.9 s | **+0.1206** | [buy](https://solscan.io/tx/VVVW9exc2a3CXLUVYYVUeeeuCaYobcWUzcYRfeFRrjJt2AbocRqpCP7EPsTpSk559636mRZruNtcfQ3wEQQG9RF) [sell](https://solscan.io/tx/4JmJCqxQhbAHgTvDLyHYAn82usXm8UkoMCeQBrzgttVB6gNAEJkcjBSeeszTpWZ81PJ7REhaaKkXZ32aSWk3jmGe) |
| 5 | 02:36:33 | [92ACPd](https://gmgn.ai/sol/token/92ACPdUX2u9xLBsDbiEogPT1jz9SkSwTzPLUuHmmpump) | 6.7% / 2.93 | +2 | BAM `Fc6NNd` | time-ms 0.9 s | **-0.0256** | [buy](https://solscan.io/tx/3UwLqgUktWNX4h9h84xS6WeL8DpkoP52PhXg23u3cYdvQG4tDy1KQjqnsgW8ZsUi7pKqqBma4RvVzQSqbN19Cn6a) [sell](https://solscan.io/tx/5ru7eCRNhNx2CZ7cv2Rx831JyzBKeGTovaJngDKSjJxsfsPxbNuC33C51816CRXLLatiRfumHKqAhdpbGdsWp6Bk) [whale](https://solscan.io/tx/676Gq59X2guUDLGnNqGGU1VoxMxeXZvprwXFF3KPLvSuyz4Tha5mFKvuWuDGKK8ASDYWFp7UGaZgYJttacvU2fLp) |
| 6 | 02:36:50 | [QujrZF](https://gmgn.ai/sol/token/QujrZF3A7PLyqRGEnaaD2MvYJnLDwKpQmQCWYimpump) | 7.7% / 2.96 | +3 | Harmonic `Fd7btg` | time-ms 0.9 s | **+0.0647** | [buy](https://solscan.io/tx/2kd8UzuS5yeR6qvDFKDWnRWMPbhYjeoXMtvutt3ue2Tp6HZbG926ZDHCqVfzrdgvqs1jSeWQN7RRcXkSVgz5izup) [sell](https://solscan.io/tx/5hiiPSeanmMnyFdtP4EMk9TYVLApyKg3gtVmYwYFuHkZhNqLYhyDvMGR2oWYax7s7qq5U1v6QRURySsLBhyn9PuQ) [whale](https://solscan.io/tx/5QUMdXF1cMiiYKA6qWWEwnyqEqBTbuumNYvDT8fFDWCyccvyFWCZjUb8sbZ2QW6MceYpUKLW5nScEVknkcNkMAjA) |
| 7 | 02:38:50 | [88qNtH](https://gmgn.ai/sol/token/88qNtHjqBXErVG9zNGmkRJZqRLctaWpjUXoQf7ubpump) | – | +16 | Jito `5pPRHn` | time-ms 0.7 s | **+0.0267** | [buy](https://solscan.io/tx/4aYZ9LWmTkt1u5KLHH8iUXgv6sceSezYxhKNLoE9VVGbvptik2jadW92TnV4eqigQ5pjzArjdHUmFv72znvccgza) [sell](https://solscan.io/tx/266V1BDx9EjETEsLnRKvy4G6LnaK6LehxqtfESNJEouAJZ9MWhWKU9rstfZGNwx1brn98T92bU2z26nigfHsi3Yv) |
| 8 | 02:41:34 | [HAbXdP](https://gmgn.ai/sol/token/HAbXdPwTzyd21z2EfvJ9aNriWcsQi4nsyFcbPfFVpump) | – | +9 | Jito `HEL1US` | time-ms 0.7 s | **-0.0066** | [buy](https://solscan.io/tx/4Rn6eoCTjkqNPGZPsNrFR1SxZLJUxZfwDoXF29hLYqrDRubf732af8cy1zohcwRbgA1UtmnAv95kz5pZb1JNr8Qx) [sell](https://solscan.io/tx/4xxBU6GkmojPJNtgeNGeLQNpYgU1LkH7urYpAAZbPWMxEhjkEAkNbQFzgELnb1BZL5WubojDsz2ZwPGD8C7KRB4P) |
| 9 | 02:43:30 | [4zLWA9](https://gmgn.ai/sol/token/4zLWA9TrbfprUWA58q9bgKcfD8d3vTh3EgL2D46kpump) | 6.8% / 2.96 | +5 | BAM `GQzMeE` | time-ms 1.0 s | **-0.0206** | [buy](https://solscan.io/tx/62N66hav4zsbgVW1Vjo8N84atB34y8MKbynndS2Bcu6m4RiDeThVv7rnum1J5fYinWGpcdoMDnKD9J6F7xzGJz9x) [sell](https://solscan.io/tx/7Vstciy1MTqZW3knzkphEZytmKicfHXA1y7L9q6AyhAchjvEDGftKCftm9zhRV37fkyZCdvw36ne6SKZQBFp897) [whale](https://solscan.io/tx/gpPopgTvmWUyiQp97KXyGdmv2xRWHwyyKxdWHmqsrwin2TJhnpcKasz5RWCmm1hLufxDuegJV6SVxbPNvM7NLBp) |
| 10 | 02:43:46 | [9kYWuk](https://gmgn.ai/sol/token/9kYWukRUBL5Fq5o5YdRfjxiB1cxTFMMyqU2KazNnpump) | 6.4% / 2.79 | +5 | Jito `E1r4Ps` | time-ms 0.9 s | **+0.0816** | [buy](https://solscan.io/tx/4LESnMQMC7SBjynH2zVEr5tui2o76YPD1DcwtJbvydFqwvkqtAqTvgJUyzZGybGGsWgs1N5HawrAWsNkW3t6DBeh) [sell](https://solscan.io/tx/4GDy9rE1xoN1igdZdJCNieorMqwamRQfrF6vCAqQgKJbKxQ1Vvsmv4wAMa8EaSBUByU1KeiXDBcyQkim1RAbKoJn) [whale](https://solscan.io/tx/FUCeYKbTsD2aV7HFcepeqe99yhmEsfEuZLiPWSbnJXrhTLkBzt9YLguzPWcH21U9fwL2H3LncwEZA2W9f7UiFMq) |
| 11 | 02:49:46 | [9kYWuk](https://gmgn.ai/sol/token/9kYWukRUBL5Fq5o5YdRfjxiB1cxTFMMyqU2KazNnpump) | 8.3% / 8.26 | +1 | Harmonic `FzQqaD` | time-ms 0.7 s | **+0.0069** | [buy](https://solscan.io/tx/7rAzL4dqHYyoD9pWcgXMdSwFwXW7fHrkBT5H8jdQmFXmxPe3VVruRB2L83UpJTDBaZvJqvLHsZRsnqxkt4j971u) [sell](https://solscan.io/tx/56EQQDaBCZaN16zMXuZm9UhDb2EQ6mJdV9N6MDvxNXQbd5gUR7JMjGdhvwes4AuKvMtHbtxgnp2MHxAcL5bg3mV3) [whale](https://solscan.io/tx/5WebAGEQs8RUgLYV2JnQ7xxXt9LZB7dkc3ZYAK7quXyyTy86zwwtRNQdqpGmQfW5KqSLYPNborox6H4YHxdiEK8F) |
| 12 | 02:51:42 | [7MyPHr](https://gmgn.ai/sol/token/7MyPHrHqiwkvnB3MMz6hSdmXG2AcYgFAyArb7Vpw3V3q) | 6.3% / 2.44 | +5 | BAM `BSVckj` | time-ms 0.9 s | **+0.0117** | [buy](https://solscan.io/tx/3jyXTBiw9kofWJjJzzJbTRX2TjVbHCTqqcJik8SsrC2QK6agy37bm5vH7rHF91R7oryHZiHFdbavsHTAt6Upzyjd) [sell](https://solscan.io/tx/tnvaCrYkoHwJDzXcXjCDwFk1DEaf2AyDWoRyymymicTwupnuged6FjQwuQ9DzRzgPwBLiWAy2SAB6cHBbqzjDCs) [whale](https://solscan.io/tx/3nz5SdSopMaAZjoraRbzKmmND83N1jZwYLGMRZLvRy7f9EJEhpP2Nu6icghWZXVBPQsSorTe8xk4VRfNgWGTeEao) |
| 13 | 02:52:15 | [3LWi7F](https://gmgn.ai/sol/token/3LWi7Fsw9uAfjko5rKDghGEZwMRsvmP2QhxBbR13pump) | 6.4% / 2.96 | +3 | Firedancer `9eGrDo` | time-ms 0.8 s | **+0.0213** | [buy](https://solscan.io/tx/4kcUgrmUwUdu6reN6Hmwt785CV1UQGS1apZDaPAuAkLgqGNDvHj1jETkErvXb9FahKUrR8JPj7NWSNyqsKRjubcE) [sell](https://solscan.io/tx/3hdmPRc2FeKrMEnBSx4bwe5eNF2m7PnSz1wYBhUA2uW3iGEwUtHC1MhVSes4n6mS6isjjHJfctHpKDncx39NUs36) [whale](https://solscan.io/tx/4vDwzj4FVmoZGEZ5LyifdyNMbQcnRnr6P2Jjic9mAH1BaYw7kxmnxgem1pkrcj2UgpfG6NSbugp1NN8QxkdLcPoN) |
| 14 | 02:53:19 | [ATt4K8](https://gmgn.ai/sol/token/ATt4K8CE7Ndxmakb83VqaaNwP5VyH1gYK7DLrc4Bpump) | – | +11 | Harmonic `CAo1dC` | time-ms 0.7 s | **-0.0196** | [buy](https://solscan.io/tx/3A9g6Z88YjiuQYp2zBjAJsnoNgLrxrRd89RQFPATaT7zXPyhpRyK52Zdujw4tfWG4NmaXjgx3S7rpyqhVkqPYii6) [sell](https://solscan.io/tx/BP7CVb5oQE6GuytFLvqTHAt4NjG3bad9NhF1xwJyVtZAwduEKYrBWcazBo1kvbdCRkrTTN1K5kEahUJoQb2Vzem) |
| 15 | 02:54:32 | [9QAGy2](https://gmgn.ai/sol/token/9QAGy2wX14R4vxnTta61bmSzt3hKFjcL7fta1FEqpump) | 7.0% / 2.96 | +0 | Jito `E1r4Ps` | time-ms 0.6 s | **+0.0489** | [buy](https://solscan.io/tx/4eYKwVRGmcnoYXReoj98UF6mCVHYjzqAENvLY58u2aAiTofqR5HUPU33XbnQXJ6ioZW6Ln7WzEVmjzja31HAnQFC) [sell](https://solscan.io/tx/3HCh7ULbNso6X4tnpNZKcqL5SA1t1wRMWYvU6mpe25FEj6mK4ZVN8Yy3McgpjDzBXRCHMB38DJpDWh8h2F7i8x4o) [whale](https://solscan.io/tx/2WXeBUmqWzQG2JJgYHWJEWbeA6nT4TPeVyJ3taR2eDUbBbheRQywh6KXqipQ1CFbrVp95BuLFaRCYqFtHCH3szQS) |
| 16 | 02:57:44 | [upYFhU](https://gmgn.ai/sol/token/upYFhU38wTtD1QJXXRjM6zxCWtfPmnUoPv1xSiipump) | 6.7% / 2.79 | +3 | Harmonic `87CcUx` | time-ms 0.9 s | **+0.0307** | [buy](https://solscan.io/tx/5NHu5DgXBNy6aPwo4oiMJSzpSD941dPfp9iXADzRBhkPdNoHuEkEvMEVApYPzsnCv8XcCz55wwbeohnHWW194f9p) [sell](https://solscan.io/tx/59Pu7cPVZ1RgQvTCazMWVtJniqc298nknAv9B1wmSSxka8Mvpftcb9MDd74zZwMksZmPdeYJtn6MypAveU9ZTgAx) [whale](https://solscan.io/tx/4gyikW722kBcLUWEznToNJDXXGMGJ8izb9ATc9HpRArjcwHWeu1Ubi7hbChWfznSJdtfK8ZcpijhjwxorsNzQ5vr) |
| 17 | 03:07:43 | [7JLScV](https://gmgn.ai/sol/token/7JLScVj1Nh3Mg2RdxEyee6Jc7LYPGVAwTxb9EmF1pump) | 6.0% / 4.34 | +2 | Firedancer `ALp2Gd` | time-ms 1.1 s | **-0.0194** | [buy](https://solscan.io/tx/4axY8Z9QEyuvv3RTvtUSMk4Qnt7qoiVnqKweWoMFQkYwzoyBNdWHAR3nvEvuFSPHhmHeaqgEu1Fz2C8jLNBvN1LX) [sell](https://solscan.io/tx/5ixZGYs2H5TNi6MFcfZAVjpvbnT6XbUEsG4r6MBwUsKQJswWGWgsJZArFFUWcqtivsV9hNU4Y2i2BWL9jyeDodc1) [whale](https://solscan.io/tx/4r4VSrXNwt7QMHBe7afqevZygress3uY5pzybh4ooA3xrmZq4gJr3RYMWrLFpyEnC3FheLhtnhxYb6vXKQguMkit) |
| 18 | 03:10:30 | [C9SLGn](https://gmgn.ai/sol/token/C9SLGncGzVfUwKhFNcXrmebbm3hkgHa3FRjuphSdpump) | – | +11 | BAM `6y7V8d` | time-ms 0.8 s | **+0.0580** | [buy](https://solscan.io/tx/dWzqomnU5am7n33VEZD8GnqekyLbiSU2p9CU35nbkgCSN7ifSDBZn5WykKm1QnFnRh7U1jDJNzCKYNbqtGd5DFd) [sell](https://solscan.io/tx/5SRGgYknZ2pRacpzAVpA5G74qrjY6ffRuq9E5yzoL2CU5tuTnmXVcyZqskXMw8ewsshKwRCjge1KJS2rJe4fnAjq) |
| 19 | 03:15:14 | [G2rduv](https://gmgn.ai/sol/token/G2rduvWzS4sTpK6Sg5Pod2kByZp9w1SSUVdRopYVVs9m) | – | +17 | Harmonic `GZ4U21` | time-ms 0.8 s | **+0.1006** | [buy](https://solscan.io/tx/5nBbJJ3T26KJwcwEYqVozhaS7u4r1sZ2XaBL8s2qnvvieVk2h18e2YLpmEcK8E1EmXjXCyYYXdmiSSwYtduCZcwq) [sell](https://solscan.io/tx/utBzhZeKMHD3Hagc3B8qLc2pbSTDTZhEUujER8y6G2TpjQAAmQ5hHVgS1Y4QycXSqo4ZaxThgh5FzJXr17gbkcN) |
| 20 | 03:16:55 | [87b3G3](https://gmgn.ai/sol/token/87b3G3YtR3W4CvtZj44jHyrFBAF4rQAfnNLzA95qSDSM) | 9.6% / 5.93 | +2 | BAM `mythxv` | time-ms 0.9 s | **+0.0231** | [buy](https://solscan.io/tx/hf9USrYrHJXSaNyt4YaJtuDv1i1RTD9jZsig46DDQ6ebq5oeRejuecYPNmEJZVpPBx5DxqJdyBboSidPVdVatVS) [sell](https://solscan.io/tx/L3b5tPLmhga8w1e8tb6Jm33Mfi53i56nYM724pUSX8dBoJNN5WG1behBiNT8WgkymwhtLNNMECzJXU2NAKgXoLa) [whale](https://solscan.io/tx/WSMm8E6NQvfXhNVHGdLjPFGCUHr8u1n1NqQAq26kcvuo1wHUgR9HQ6joS4h3FPLB24zPRqt4n26XBvA35aZAHST) |
| 21 | 03:18:38 | [2bGXpo](https://gmgn.ai/sol/token/2bGXpoVmZKi6ZGCB1fustEpEZTTkmyvv6gZzbouHpump) | – | +11 | Harmonic `BtsmiE` | time-ms 0.7 s | **+0.0211** | [buy](https://solscan.io/tx/4p6BgYnmi4kGBf7tSJbWfm4pH9vthzfYYmD5yBQt9NcR2iqLvxABbiWL7tizbRZ8rKJEkBdW7F39wuY2XUygnNyj) [sell](https://solscan.io/tx/4R85tyffVifYrQzMac2EKqFebaTHhUNmDNnvnozdXYarwcB5Y3jh3rFmUgbM4sZw6CnzVpTNGPEmy4YFwvR5yDK7) |
| 22 | 03:19:22 | [CZEVH8](https://gmgn.ai/sol/token/CZEVH84aWDWUjmfmQEUVzs6En7kJL5m8zhbYVJ9ipump) | 6.3% / 6.78 | +1 | Firedancer `BbCQMW` | time-ms 0.9 s | **-0.0162** | [buy](https://solscan.io/tx/55m8CgrzHdFVtcRuMgBUfn4QoCq9wgaHsqzYyGnhCbY7Qev2mMGio8EC4MpGBLTRfb7i7zHZaXeMxmDK1dsDNzb9) [sell](https://solscan.io/tx/2hRnNxuxTgz85k6763cZTcn3nqqjy6rBiYKZaD37QAMv1KmEyFb3DRxbxDTu2hwuzssu5UvShD4qP6HzS8uyLSUh) [whale](https://solscan.io/tx/2vLGw7WMDSDGe1bEDCBLShJHCQpsPmPb2M9LeXheaCjK7E5E9Y8ejJucc428EfwA5tePepC6ncosWUwA9hFGmmnJ) |
| 23 | 03:20:52 | [DfCJER](https://gmgn.ai/sol/token/DfCJERoKuLoGvAZykXYPEq19Z97pKLWDtEwWyowXpump) | 6.8% / 3.97 | +2 | BAM `CoG8d9` | time-ms 0.9 s | **-0.1561** | [buy](https://solscan.io/tx/4uuz9UWLiKL7CqitZWpHGobGyFNmUPqgvAo48c73s5iGMaZLUWJrLPKp3p51Xz3XmmsiumVTYzTFFTH8mDbKiLCL) [sell](https://solscan.io/tx/4HvfkxjNYqPFHQ7CckDjkoFzRx7ubVwqmzw5WH2xw1g79zMAqcY9WJ3c91yB5DhuizrrC8SyhoaaBQLMmhYkmHfx) [whale](https://solscan.io/tx/Dqq24gZkWBmpT6PS3WQYbTeQdaVd87aPP4TwjVXarw3gRAZDydCd2u3B8kvbx7Ayz6UqBUjoZ5aYNvYdugLNopK) |
| 24 | 03:25:02 | [DByjN8](https://gmgn.ai/sol/token/DByjN8BJMu8aH9aJjKdK6fYEJFS5dXSSiroCC4Sppump) | – | +8 | Firedancer `JD549H` | stop-loss 0.7 s | **-0.1709** | [buy](https://solscan.io/tx/5yTv8TWRJekXCym1EUQZXNkLqnNYdKt5WRq4vfa2RJicgWZT1Pvjss4JQA7vjpxMfqTQjRzFtDkait7tDwdcjBbo) [sell](https://solscan.io/tx/3R17Mr3JHNn2QufYCDgcWAk1nFwCNuVt6a1ya8Qn2MN7kStEg7xihuB1xabAfTA1YBFBqzB9EtdZZ8SuPj2VmQA6) |
| 25 | 03:26:16 | [2Uc8Lf](https://gmgn.ai/sol/token/2Uc8LfPDY1iLfUPZZP2HNZMZS6xJUZPgBHZ3GdRbpump) | 6.0% / 2.47 | +2 | Jito `AEHqTB` | time-ms 0.7 s | **+0.0115** | [buy](https://solscan.io/tx/5imYKuZzaXM1iPx6NDtvUMKrxw7Awvbh3EX6NZYCHpqTUQ8C4rRfhNHnia3Me59Xi7gjBhZp3mS3u3C7wsQvz8c3) [sell](https://solscan.io/tx/3HUYrndkmWwCeq7NusJN2UMjAB7J4jVYpZ1JPb56fex3nwhhxzbeG1NgdAxQd3Wg3dBdLzBMCPWncy7rzxqugXFK) [whale](https://solscan.io/tx/4u4zKmk5BZuAuyZ3dz3N79unqfLrGYkNATSEVMCWjwkDXjKVAVzLRDdUNvSeFdZkdmgDfYrvR8CFGy7Cqtf6q7g7) |
| 26 | 03:30:42 | [Eoi6YF](https://gmgn.ai/sol/token/Eoi6YFkjqCdyhwQMcHU6Hvxtem5xMXLHbDmWNsgXt39T) | 7.1% / 4.94 | +2 | Jito `ANC1u9` | time-ms 0.9 s | **+0.0109** | [buy](https://solscan.io/tx/3BBjHwkhzXzdy4Z8tXPbNoqXahFT1Sc54jK1TTRHbKsmbNsabbLMXSCXyqPECat6P7e5hvzQjpd2XXXkDAtEHRrX) [sell](https://solscan.io/tx/PuJp4gu5GSgFQVuxP19YidMqfiCJio5EH3g2v5TcYxMNNLehiQ7Za58sremmPU27YVM8zaPCnUBzi1bWnULfJki) [whale](https://solscan.io/tx/Ku1N25EMNBNuUWBMqZA2WyRaGZcfFpg1eFdyDVLN7ccZgjSiP3Sq7L93FBE7wcDj799ad3b6ZZw3ofZRQtkh1Vd) |
| 27 | 03:30:52 | [8xrtjA](https://gmgn.ai/sol/token/8xrtjATQpxUtdLmwhAKqLJJ6dry2xc9pAMhwFFaJpump) | – | +21 | Firedancer `JD549H` | time-ms 1.2 s | **-0.1593** | [buy](https://solscan.io/tx/524YDxNHsZCixfT5VVdC2sKZGp6dP15RmMBHavSiJxzzH9JvocYxQ1FbzLuTBWH6tKUoXTPaCR2F9S118MyWho9o) [sell](https://solscan.io/tx/2XV9DanqFPw1mBsymtQ3evn2kXSJ3ACMVVLRtvjDwzMeMcmCFponFqwmd8mZa39QzK4GhF82basyvRb5Y2zKLeZW) |
| 28 | 03:30:58 | [ETKMgt](https://gmgn.ai/sol/token/ETKMgtcm3pKuqrKqiMPDF2HQxYgGfG9DwtydB43Kpump) | – | +3 | Harmonic `CAo1dC` | time-ms 0.8 s | **+0.0092** | [buy](https://solscan.io/tx/33rF86U6pjvH4hXQiAPLdVw5qZ8irounUP3LtCmNCPwsMpK2oNWDeauUCatUaLM3zQAropiG6ZdkK657Ryg77oke) [sell](https://solscan.io/tx/2Vi6RMTZL9C5AHmHmLYWuJMMeNCRayqNdAGxZffkmSbc8SPTf8t49wM4CjVVpZVEqrEYNsqJ8otY6bfzrDoYjmvQ) |
| 29 | 03:33:24 | [8Y5uah](https://gmgn.ai/sol/token/8Y5uaho3ux5DpGQKkhoy6Wee2HkDp2frnTYxkA7rpump) | 7.7% / 3.25 | +3 | Harmonic `Awes4T` | time-ms 0.6 s | **+0.0172** | [buy](https://solscan.io/tx/5sMRJJdj5XHjxYGhYFbtPnGSVK6Yi4sLKNSKrq4GFmA9zk9UWHjq3mRDNCKKaBt8XYQY9kBAN6g1MVFteawgrapg) [sell](https://solscan.io/tx/2gto5fcDZ1seEyLLhV5mu25pha8uMxrWAEsHiYEPC3E1T9amyap77rgvEjiwfGPTXzfwyhJfwXhS8gT9xVkd8Kk8) [whale](https://solscan.io/tx/R5nESvyk5KtRk8n6LSjcW6uq9rPSV3P3VN7wutkFbikganj7xxQBi14iSh9Dnf7gUH58v7EvUx3C6k6oNsYjKxC) |
| 30 | 03:33:48 | [GD8cMG](https://gmgn.ai/sol/token/GD8cMGD6SMqvJFtUj4TSxzXrqaeDUF3RaHM3d8Ynpump) | 6.2% / 2.17 | +7 | Harmonic `Fd7btg` | time-ms 0.8 s | **+0.0396** | [buy](https://solscan.io/tx/5EbxSpzMQBKFTx5kCFxsBmVaiBknpn2bQSUsbhrLTBKpF2ekLcdDauwVHeD9x93PvgdcySijgbaCG88A1ewRjczY) [sell](https://solscan.io/tx/2G8t67oPqWeA58hHm26Y8B83NRUkhiLw6J4NcmoG7A2wPWu5jUGx5JSQHvxBTu4o8tMtxLgLgh3DrZNyVYTsTa6Q) [whale](https://solscan.io/tx/4UEewjU3JQ4Kzn3hjA3P6jwfaoyGbXJmLF35TwD1euFuqQv8q1UkGf7K9Y3rsGPELeQL82xkSHURTCfs7k25SFM2) |
| 31 | 03:34:54 | [6iSYaV](https://gmgn.ai/sol/token/6iSYaVb6xKFhhCbAFCwY8wGUrwWwPi2ybMNxaVp7pump) | 7.2% / 1.47 | +4 | Firedancer `RNXnAJ` | time-ms 0.7 s | **-0.0206** | [buy](https://solscan.io/tx/5VevnFr9FyGFiS7Ci6Ztxse8RfUooBMd8MLP4jm3WsY8W5HejBYn84SvkkiRRnBCJg8kSVbMRiDexmktdznRgPm8) [sell](https://solscan.io/tx/WBG2NTNkABgdzRFEaCWnCn2rBBnGCko1GpPLsm9tYhBvjEQ7Z6aUVYmmVCaqv6ibowct1dYD7UESXQK3ApRu79Z) [whale](https://solscan.io/tx/5PTado8UDkzxEb3T6VEq7BkYsPYCce8Ye64VG1FC6uykoyDaL41UKwyRoHX3d4g4L4tGE5KYFxskRhkCJw3LTAFM) |
| 32 | 03:34:56 | [DxCvDH](https://gmgn.ai/sol/token/DxCvDH4x1sxKU7QWnPxZss9GQZzp8DFTj2HAF1gepump) | 8.0% / 2.96 | +3 | Jito `EvnRmn` | time-ms 0.9 s | **-0.0089** | [buy](https://solscan.io/tx/XdbQDgZvngR3SCoSGbL9umjgvUPRpw3qZV7JLFGTzXbhFSe8ZKmUfrr3N8yZY5dhiDy3JohYXAcyXYkSMSwM2ZC) [sell](https://solscan.io/tx/3Lhi7GfPPRLcNJiYHdov6Hchyrz7L2YuLXiRtE2YvYAhRPuTS9w5dctfGnFty1PeyriVeemj27XZXBCMX3v9i7p8) [whale](https://solscan.io/tx/gEKfmJxb9S3SBFsMShF4AeSfXoSBGM99mrgsTi58Ep1PiAFoWS2TpGUKp7p6UDpgGs4er5o9QADFvRaAXrq4bYX) |
| 33 | 03:36:48 | [DXvegi](https://gmgn.ai/sol/token/DXvegiAQ9oZyHCzXJm6HsCpR9W7Q7AV8UEAXLmMNpump) | 8.7% / 6.78 | +2 | Firedancer `ALp2Gd` | time-ms 0.9 s | **-0.1976** | [buy](https://solscan.io/tx/5mva6kphqyR7GZBjEScuoyGzLNu2FmkBCUneu5dRZD1KuHVj4CjQfRb1dad5AKcnTNERtbo3ToiaGR7of32t7AVi) [sell](https://solscan.io/tx/wKJD8LorFuu1udFLdEBur5k7xoh2Z4egHzXGUuaiJLXmZbj1LUC5iKXY9tKmHwMqsb81Bj1daKKE9NkCjzFSzCU) [whale](https://solscan.io/tx/ufMKa381vJZCsjvm4u7eykZCrEqSeXs7GLnhMuGgTDrn17Tt6XEdz4awVEPKx4iUgmZJwfMP1Fu5KV2ro1ktv9N) |
| 34 | 03:40:08 | [H9932w](https://gmgn.ai/sol/token/H9932w4K9P9dLoNEkVL3Kg9FspoR8yasqhdqGvMHpump) | – | +8 | BAM `HpcB5Q` | time-ms 0.8 s | **-0.0455** | [buy](https://solscan.io/tx/53qbP3Dk1FEnTpSaFsq1WtrND2ehYRbvVGBWe4nZW9qNzfxrfUVxyCpnRDJZNFKa6xTJjNBfU3YuS8GxNv3YdMRv) [sell](https://solscan.io/tx/3uZrnhUSFgF1CeHmuzTkwjF2cNHwDaF9XeYzU9VbEC2iK4DGb1xvHBBm43CFPZZCRDeTXMeyaBfixB5VaCdSnA7G) |
| 35 | 03:40:57 | [GHUu87](https://gmgn.ai/sol/token/GHUu87c5LrizpxJ1WNSHjiv51AzHbNUtYzATWgoYpump) | – | +7 | Jito `ACvL73` | stop-loss 0.5 s | **-0.1500** | [buy](https://solscan.io/tx/3TZtQ2V1brvjqacjwLvsDZ7cUmWNURMasKXcQPCoRnRiroMCbRKExYufaJKUMmBHXVp2N3hQeMzUeDHQC2Xq1rRr) [sell](https://solscan.io/tx/VpYh6q9jQKsGqLykcNPo1ogvRo13L5xeWggez1SskdPwNK4FXcUCQiVrgryASAL5dXH3faTa2xfvUHmjEtaCH4s) |
| 36 | 03:42:57 | [9NGkR2](https://gmgn.ai/sol/token/9NGkR2LjftKtY979jiUfpdCfe7TZW3knmmU3aaNQpump) | 6.2% / 2.96 | +6 | BAM `7CR6wh` | take-profit 0.5 s | **+0.1666** | [buy](https://solscan.io/tx/5Gsd7dDwRwvn31XDXJiMaRM7pWTpgQhSnsg62sZhzCqJfjkwGw1LNpgrvr1GT82nv95oSGjb7Jf2yPFCeLWnZCwQ) [sell](https://solscan.io/tx/3eNibQUMNkLmuFuot59sXaB1X2m8LgpdaPhGFTwEWFrMXwNshNkGVmBB4MNhWGH9vTAjizdGZ1PkrJ31Wp9FJKpH) [whale](https://solscan.io/tx/WP9pebZ4XGNMbwSwSmzH9XThp7w1HEFBgHDL1tZaPJR6Xej8tjCfZJycbkmf8sxyuW7Q6iTdZoE271oKLfhwy4D) |
| 37 | 03:43:09 | [GxwP3s](https://gmgn.ai/sol/token/GxwP3s6UtENSGZoaZJy3YJqHCoM9vwZbtNf7tcTF59LL) | 6.7% / 3.36 | +3 | Harmonic `Fd7btg` | time-ms 0.8 s | **-0.0415** | [buy](https://solscan.io/tx/5b1r3n1bWtGcHAod5aT8yVJEZ7QfMhnzP2kWpPygf9nJAcPahk4gNr3BA1QRJhTbk8oKAxsV3tVFEj52Hz51jB6o) [sell](https://solscan.io/tx/4B5xccQVkRUt1rZ5uphyvbLB3Mai2UuRbi7XKsyyCYTnV5QFLY2WL1sfeQztoy9MCcHCoHCF7TBoHewgbms2JJ8S) [whale](https://solscan.io/tx/2wB1WHkfWDG5GMa6utcwQnwJoL3zVFJHWZFEwYEqm53bUo1N6z3rxpx87kGqwEJJe68G6zPMQnxfPB7Hso7xJorY) |
| 38 | 03:43:15 | [GxwP3s](https://gmgn.ai/sol/token/GxwP3s6UtENSGZoaZJy3YJqHCoM9vwZbtNf7tcTF59LL) | 8.5% / 4.44 | +10 | Harmonic `BtsmiE` | time-ms 0.6 s | **-0.0853** | [buy](https://solscan.io/tx/3rXQ8G1QSHAPVcQ2TJSKTWi7gKcyLSYxvKrCf5sorzmqquGhoRXbK7kELnCfmqQ9box2q8zWMse8qopDRGiYghv2) [sell](https://solscan.io/tx/38ps2nixnfj7RzoXDxGt3b1Z2aPhbNqV7RpiaubYWm9Jb5YkQGP6r3TAVjMtbFQe5oJVbhXCtM4WaehJUFj2L2ey) [whale](https://solscan.io/tx/H2GBdmTsc4DrZxpikcPuk27X6wD2PZRMzyxtez8fNyLYWRWa7yo6YRLsFh7KvGpWW5bK52KA55ijVFyrqfw63BD) |
| 39 | 03:43:44 | [ERgyFU](https://gmgn.ai/sol/token/ERgyFUv4NyYMRGszZN5m7d6ZeJzdg1Xfhjxg9wESpump) | – | +4 | Jito `HEL1US` | time-ms 0.7 s | **-0.0950** | [buy](https://solscan.io/tx/3ppGDZeqyPXG9vrNdYd5rwbmadpc2mrsKN8ztB12kDVcfiMW5iqUt7u9Hb2hfyncWvARJJFAcS7VX4EmLFTnkCSE) [sell](https://solscan.io/tx/5F4jmine3q4HnoAvrPcdttBw4QuxVTTHgUajuJ3Po4xvWscHacCFtmkUgFM2Y6pFyDsLDuBihn8x9rhe8iU8SYS7) |
| 40 | 03:45:09 | [CsV2WE](https://gmgn.ai/sol/token/CsV2WE7NVheXB4N2QsjNCkfKWbP3x4GERCjc8Gp3pump) | 8.7% / 4.54 | +2 | BAM `DRpbCB` | time-ms 0.6 s | **-0.0635** | [buy](https://solscan.io/tx/4VKk77nCHV68hZ2wW78SnmFo5kN3gsMeyPC2XBcpPDPPrcQXymnAaJHPyL8Bco8jbx7Qa7q7RKbyCskuMhusUqZk) [sell](https://solscan.io/tx/5W6s1spEtzGoQ3yvzmcHStvy6FTvQaHVaUspYXQoZzwRg4qk8fgG5u3WMoCcgnATXS9XCFRmU1T3RdMZPyYijggo) [whale](https://solscan.io/tx/5pNNjgJTjy9i9SU2UN3Bubona3dy99wLVaytUPz7vrSYmv9UFefTrAHY5jC3dtWRDG3ZGESEf9wY7kNxZNNXBUsS) |

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 4702 |
| Inside the envelope (age / drop / since-buy / size) | 2205 |
| Picks (score above the threshold) | 39 |
| Skipped | far_leader 25, spacing 5, presend_position 1, presend_armed 1 |
| Buys sent | 0 |
| Filled | 0 |
| Failed on the +5% guard | 0 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 0 of 0 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|

## 7. Breakdowns
## 8. P&L leaders
**By slot leader (validator), best to worst:**

- no buys

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | – (p25 –, p75 –, n 0) |
| Executed-feed lag behind first sighting, ms | – (p25 –, p75 –, n 0) |
| Buy sent → our tx seen on the feed, ms | – (p25 –, p75 –, n 0) |
| Fills: our buy seen on the feed after the dump, ms | – (p25 –, p75 –, n 0) |
| Guard fails: our failed buy seen after the dump, ms | – (p25 –, p75 –, n 0) |
| Fills in the dump's own block | 0 of 0 |
| Guard fails in the dump's own block | 0 of 0 |

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | – |
| Guard fails: rival buys ahead (median) | – |
| Guard fails: rival SOL ahead (median) | – |

## 11. Costs
No fills. Failed buys cost 0.0000 SOL in tx fees.

## 12. Health checks and red flags
- ⚠️ start refused: Error: keystore: wrong passphrase or damaged file
- 🔴 kill switch: DIP KILL-SWITCH: run PnL -0.500427 SOL (balance 19.841384 + open 0.000000) below -0.500000: no new buys
- ⚠️ 36 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getLatestBlockhash: 4 timeouts/transport errors (worst p99 539 ms)
- ⚠️ RPC bh-fallback getSlot: 4 timeouts/transport errors (worst p99 544 ms)
- ℹ️ 4 send-path health events (self-heal), e.g. `SEND-PATH rpc bh-fallback UNHEALTHY: 3 timeouts / transport errors in a row (getLatestBlockhash): client REBUILT (fresh `
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)
- ⚠️ big pre-send loss DfCJER -0.1561 (time-ms, BAM)
- ⚠️ big pre-send loss DByjN8 -0.1709 (stop-loss, Firedancer)
- ⚠️ big pre-send loss 8xrtjA -0.1593 (time-ms, Firedancer)
- ⚠️ big pre-send loss DXvegi -0.1976 (time-ms, Firedancer)
- ⚠️ big pre-send loss GHUu87 -0.1500 (stop-loss, Jito)

Checks passed: every pre-send fill was closed by a sell; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
- none recorded

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r41.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r41.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Pre-send (section 4b): the jsonl presend_live_* records (fills, closes, REALIZED, account closes, stops, end checks) and presend_attempt_land (try results, failed-try fees); the log's PRESEND LIVE lines when a run has no such records.
- Engine sessions in this run: 1; refused starts: 1.
- Generated by `ops/dip/report/make_run_report.py` at 10-31 03:48 PKT.

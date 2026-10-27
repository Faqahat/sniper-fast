# Amsterdam run 27 — dip bot run report

*Short evaluation run: pre-send LIVE 0.35 (k 4, cap 1000, fee budget 0.4) + QUIET (dip20: stop 6:2 from the start, skip rule after a 60-min warm-up) + reactive M2 0.35 + dev list 0.35 + routes v13*

> **Verdict:** +0.587 SOL on the wallet (4.9324 → 5.5198, chain). Pre-send: 49 fills (26 wins), realized +0.570, rent back +0.074, failed-try fees −0.022 → +0.622. Reactive M2: 10 buys, 4 filled (1 win) → −0.034. QUIET (MEASURED): the stop rule cut 45 windows short (their fees −0.005); the skip rule was ON from 16:27 PKT and skipped 36 triggers. In the warm-up hour, the 20 windows it would have skipped were traded live: 4 fills, net +0.0015, so skipping them would have been neutral. By phase: warm-up 15:26–16:27, 74 windows, 19 fills, +0.060; skip rule on 16:27–17:36, 103 windows, 30 fills, +0.562 (incl. 3N44sv +0.220).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **+0.5877 SOL** (wallet 4.9324 → 5.5198, Δ +0.5874) |
| Started (PKT) | 2026-10-27 15:26:57 |
| Ended (PKT) | 2026-10-27 17:36:57 — time limit / max trades |
| Ran for | 2 h 10 min of 130 min planned |
| First / last buy (PKT) | 15:35:23 / 17:34:51 |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 10 → **4 filled**, 5 failed on the +5% guard, 1 failed (other) |
| Fill rate | 40% |
| Wins / losses (fills) | 1 / 3 (win rate 25%) |
| Per filled buy | avg -0.0078, median -0.0114 SOL |
| Fills only / failed buys only | -0.0314 / -0.0030 SOL |
| Reactive bot / pre-send live | -0.0344 / +0.6221 SOL (pre-send: 49 fills, realized +0.5703, rent back +0.0739, failed-attempt fees -0.0221, 26 wins; see section 4b) |
| Best / worst trade | GFcPyQ +0.0090 / CKTeAG -0.0175 |
| Fill landing | median 36 ms after the dump (seen on our feed); 3 of 4 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip20 |
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
| pre-send | LIVE: whale >= 6%, 4 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 1000 fills / 0.4000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 500 fills, 1 open at a time, 130 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 26**:

| Setting | AMS run 26 | AMS run 27 |
|---|---|---|
| engine build | dip19 | dip20 |
| size (normal) | 0.50 SOL | 0.35 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.50 SOL | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.35 SOL |
| pre-send | LIVE: whale >= 6%, 4 tries/slot, 0.500 SOL, limit x0.88, route helius-ps, caps 1000 fills / 0.4000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% | LIVE: whale >= 6%, 4 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 1000 fills / 0.4000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| limits | max 500 fills, 1 open at a time, 720 min, loss cap 0.500 SOL | max 500 fills, 1 open at a time, 130 min, loss cap 0.500 SOL |

- Engine dip19 → dip20 with --presend-quiet (QUIET: stop a window at trigger + 6 slots if < 2 other trades; skip a trigger when all 4 quiet signals hold; 24 h whale dump history; 60-min warm-up, no preload on AMS because AMS has no raw recorder).
- Sizes 0.50 → 0.35 (pre-send, reactive, dev list); 130 min (owner: a short run to evaluate QUIET).

## 4. Timeline (PKT)
- **15:26:57** engine start #1 (session with 10 buys)
- **15:26:57** start (dip20, QUIET on; the skip rule warms up until 16:26 PKT)
- **15:30** falcon keep-alive refused ×2 (falcon is in the BAM / Harmonic routes of the reactive buys); quiet again until 17:30
- **16:27:09** QUIET skip rule ON (first armed window with the rule on)
- **17:04** pre-send 3N44sv +0.220 (best trade of the run)
- **17:30:40** falcon UNHEALTHY: 3 transport errors in a row (connection refused) → HTTP client rebuilt
- **17:36:57** engine end #1: run end
- **17:36:57** run end (time limit); END CHECK 49 mints at confirmed: 0 held

## 4b. Pre-send live (pre-placed buys) — separate from the reactive bot
Buys pre-sent after a big whale buy, before any dump. **Not included in sections 5–11**, which cover only the reactive dip bot. Realized = the engine's PRESEND LIVE REALIZED records (chain txs of each buy and sell; the buy pays the token-account rent). Rent back = that rent returned when the engine closed each pre-send account after the exit (dip19+; before dip19 the sell closed it and the refund sat inside realized). Failed tries = fees of tries that landed and failed (6042 price, deadline, …). Net = realized + rent back − failed tries.

| Session | Started | Size / fill cap / fee cap | Tries sent | Fills | Wins | Realized | Rent back | Failed tries | Net | Stopped |
|---|---|---|---|---|---|---|---|---|---|---|
| #1 | 10-27 15:26 | 0.35 / 1000 / 0.40 | 4,419 | 49 | 26 | +0.5703 | +0.0739 | -0.0221 | **+0.6221** | run_end |

**Try results (as seen on our feed):** 6042 3,872, deadline 361, ata_exists 58, unseen 58, ok 49, buy_6005 21.

Tries never seen on our feed: 58. If they landed and failed they cost up to 0.0003 SOL in fees that are **not** in the failed-try total above (5,120 lamports each; inferred, the engine does not see them).

**By exit reason:**

| Exit | Fills | Wins | Realized SOL | Per fill | Median hold |
|---|---|---|---|---|---|
| time-limit | 38 | 15 | -0.1261 | -0.0033 | 0.9 s |
| take-profit | 11 | 11 | +0.6964 | +0.0633 | 0.7 s |

**By leader type (the slot leader where the fill landed):**

| Leader type | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| Harmonic | 19 | 11 | +0.1020 | +0.0054 |
| BAM | 17 | 10 | +0.3514 | +0.0207 |
| Jito | 9 | 3 | +0.0560 | +0.0062 |
| Firedancer | 3 | 1 | +0.0135 | +0.0045 |
| Rakurai | 1 | 1 | +0.0473 | +0.0473 |

**By hour (PKT):**

| Hour | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| 10-27 15:00 | 11 | 5 | +0.0337 | +0.0031 |
| 10-27 16:00 | 18 | 10 | +0.1328 | +0.0074 |
| 10-27 17:00 | 20 | 11 | +0.4038 | +0.0202 |

**Best pre-send fills:** 3N44sv2M +0.2203 (BAM, take-profit); A4afZKwa +0.0605 (BAM, take-profit); EG7Kus8v +0.0599 (Firedancer, take-profit)

**Worst pre-send fills:** B7jwy1MN -0.0377 (BAM, time-limit); 59T8FsaQ -0.0293 (Firedancer, time-limit); CiMLdKUm -0.0291 (Harmonic, time-limit)

**End-of-run checks:**

- session #1: END CHECK 49 mint(s) read at confirmed: 0 sold now, 0 empty account(s) closed, 0 held / 0 unreadable (per mint: none 49)

**Every pre-send fill** (time = fill; whale = the trigger buy; P&L = realized, rent back not included):

| # | Time | Token | Whale % / SOL | Slots after whale | Leader | Exit | P&L SOL | Links |
|---|---|---|---|---|---|---|---|---|
| 1 | 15:28:48 | [4MDt2o](https://gmgn.ai/sol/token/4MDt2oaT2617rJDvcmuZrgmhzLQHFuuohbVLKDMApump) | 7.7% / 2.96 | +4 | Jito `9rkJMA` | time-limit 0.9 s | **+0.0149** | [buy](https://solscan.io/tx/49UQ8jcmt6345hwRF1DTobEeN3L1smANu9XtAbBBLQEv2XW3SwtrjtE9FqZoiqEpV4p7X2nYqeyqc5TniN1esJD9) [sell](https://solscan.io/tx/5LYeLt4gUaXyHNjqmmspq2XccsaXU15ZqbGM3R3tthBzVrZdrZmAQRi5idWnHEkdZGE5mqudVqiemcxb9AReysb3) [whale](https://solscan.io/tx/2vuxmfJnWuMd7hVNxuvSMHCSK5jBruqLyfgriJYhCyhPVoP7gto49RaZv4z3mrJR4av33cX71YsQVDrLjj7tEdoU) |
| 2 | 15:28:54 | [2tJWKX](https://gmgn.ai/sol/token/2tJWKXcgKhs5Lx3gxv7RX4wgLZAnzE9LSED4V4M76emH) | 7.0% / 2.78 | +3 | Harmonic `GoeW4a` | time-limit 1.6 s | **+0.0031** | [buy](https://solscan.io/tx/G3wfXGk7Gq9a8mEbzWQFu4ykGppGaUB95RA5hnegRA2ZSVDCJD6L113K2tgxjvNMaB5xxKVeAPMvNspQrzLbcAz) [sell](https://solscan.io/tx/5uLacPecygAy1UvqR8FE23XFr4D5XJjtUMd83GjpmkjE4HuJtoqZk9ciHMscPoyhvKNvTfMcYYTEzsTrFMMTnSiD) [whale](https://solscan.io/tx/3Pgkk33jVVP6MK1EDyE1CgSSjzBaY2AoN1UzNR7qAfY4k1BbgC1sLApcPg7bYYv9zL46qkUAQ6gdqc85HRVxB5cD) |
| 3 | 15:30:37 | [3UeiRc](https://gmgn.ai/sol/token/3UeiRcVWAJWrjN5p6YxhVZooK5cpt5i4qtNNMUi4JFJX) | 6.6% / 3.26 | +3 | Jito `C8Bey3` | time-limit 0.8 s | **-0.0085** | [buy](https://solscan.io/tx/inL97r9Gb9A2cNWAFb7GjnQn7yCfGLUwRHXSh3UdxLL8JvRxDqRbrQWSc7b5PFh9uvBj1s19B6SP2Z9oab6H3Qz) [sell](https://solscan.io/tx/2Nh4NUva2C3QeH2unbFFa7mvbnBhj11MzuNnZ26NDzZhcHoHMgYpxJArcvarTzzsuPoPyzYNbB1846Hf8dMGryjK) [whale](https://solscan.io/tx/3SV7eJpQov8g8ayXSzSRZvripVh7jTWFBiSpFr4arCowGDkayDUTcahDRsuwst4uQNfdD3zVqsCdnN6a8Wv42FNT) |
| 4 | 15:31:11 | [BPdi8Z](https://gmgn.ai/sol/token/BPdi8Ztqk7jtz6spQuEdcJdc1VLk4DrdwaEGfJ8roWGs) | 8.0% / 2.96 | +5 | BAM `PUmpKi` | time-limit 1.0 s | **+0.0296** | [buy](https://solscan.io/tx/21YCn148EqCkC7e6AzrTaSSujBnmwa3CrftKy5bcnufcwwsdnsJwCEhMvR71xYKnqHMyxqnFw63kaxif8UF22sDC) [sell](https://solscan.io/tx/4ayeE6r8BpHvbRinihNJPGNL9DzRMJtxSe3TnMAvefm3j66Xi9nshYsFoZ3ft3U6DwG2Ke99jdPgQREQKegJMpxj) [whale](https://solscan.io/tx/4uo1yT26fkNA1JB8ksYfP1p7sd1HXpevVu4HVcTiazsZqxwagYLKotZjtoG58pCWmSMmUuPQYu7565oUaFD8vChx) |
| 5 | 15:38:12 | [arpYGs](https://gmgn.ai/sol/token/arpYGsy47DA69RqsgyRF9dBoVgo1TDPaGg9H4m9wSQM) | 6.6% / 2.93 | +10 | BAM `HpcB5Q` | time-limit 1.1 s | **-0.0029** | [buy](https://solscan.io/tx/zUikfQZ2dFxLMJPvqnnyZb7toCV4CfgHgbu3Vq9FCrBoyyAJfKtGrQW8hzeodoqk4bYtJmq5skyXP6Qqy1ZzANZ) [sell](https://solscan.io/tx/ffQunEbgN8mrMVxBz3P2VTeBPX6gsf2nTf1cpPxKPhsCzt3sKzzUmhmBh1ctYY3gDWhnmfj7Rfc5nCwuWkPLFWA) [whale](https://solscan.io/tx/52AJp2nu81Ttrd2D45jjJmub3narZxP8GeANazWMLJRyHrxJEBD2XBnePfa83uWuDG3G8MiBbWKxhReHF8XfUyPU) |
| 6 | 15:44:07 | [2Ujgen](https://gmgn.ai/sol/token/2UjgenJmuydz3W2vjd3Agzx3MKM3dQWouVC6h2NMpump) | 7.9% / 3.91 | +7 | Harmonic `Fd7btg` | time-limit 0.9 s | **+0.0045** | [buy](https://solscan.io/tx/5FbinkCy4ehtSdHWAH8cexuNrHqqaxfk8huYP51M4iyXwhRPpf668oa9CEEcTbLJ9R8vdUG3bLtHyk88vhvAiwHs) [sell](https://solscan.io/tx/59ad5iqibKejwCR63kcAwxgUBYdHjF29ejn4QCNF1ofgsigjmrSuQWsXwJLaggrNsgqJ91TdGbgg5WcJPYefiobu) [whale](https://solscan.io/tx/WsdEp8xdHLktxkSRwatBZJTBaZjtcxvuz26nJEY3UPuJtpVASDpJCBpdJDp4fvvW4RcvxT8KwSuiXs9LwFrHShh) |
| 7 | 15:49:44 | [2dzkua](https://gmgn.ai/sol/token/2dzkuafE6bPcRD5DvAYaPo7Q9WakcAAckfmFVJdepump) | 8.0% / 7.90 | +0 | Harmonic `BtsmiE` | time-limit 0.8 s | **-0.0155** | [buy](https://solscan.io/tx/5bzATNLyCuuUdag5UNjbvTcDEizdBD5Kx4Se6n8Mmzq2c2p8bxB9kYmBw48iSTkxk58pXVnc9TMkpwodec53Gjkb) [sell](https://solscan.io/tx/btYA9iW4RSsU64LucKeT3mgK7EYJ3HC8NcEjmjYPvMu7GC741cty8fcTYv88uNA9iauHXQnyz7qB5bXcRjcDk1k) [whale](https://solscan.io/tx/a7qALM5njsbFft6PsgpctPDbeLwiYguRhH7qZLb1MDUNkgavtLWxyM1ifu1oHVnwuXagSdvSCb8tVKLSsgnhVfF) |
| 8 | 15:50:34 | [5vVRSj](https://gmgn.ai/sol/token/5vVRSjXtr4jzoT9puukEYXAbi4JqEBBU4zPRYgrypump) | 6.3% / 2.96 | +6 | BAM `6y7V8d` | time-limit 0.9 s | **-0.0122** | [buy](https://solscan.io/tx/3cM6AypovpF6htd2cVX7aDaFsa6VwHD1P1HhbRSkNeN46XD3tkoj4ywLTjQrMqLEbv6oDwqVwjom5QdzbjELmDWK) [sell](https://solscan.io/tx/3dzP9ATe65is4tmpTfATXTrH2b9ViPUECrBfrXs2bhLAmBPR3rE7khhLn5F4WzteUiV5EhxrvqFxLAn2Uizf49WU) [whale](https://solscan.io/tx/4WFeMS884QGQpYQiUvKVYZCFKkWf7FXNm4vV37ESQEUAtmLCXarqnSaWiFwhwr8SN142FryUVz38GcKYPVC5i8ed) |
| 9 | 15:53:37 | [5xo4Ay](https://gmgn.ai/sol/token/5xo4AyWr8c3bJMtb7YsdP7891ggBqnNyB2GAm5pNpump) | 6.9% / 2.96 | +5 | Jito `DF1owX` | time-limit 0.8 s | **-0.0056** | [buy](https://solscan.io/tx/4AJFxJjQiUtVszm85fPNfRDfVckLk9fu1UHjJhUcrRS2tykaysLwyk6ZZ1M6wsc7rcaTTqxgZtcXaeHKPor8uLxq) [sell](https://solscan.io/tx/2Hh3ovqpuXsxQvqawVhSFLh8GscwWHze4vPMSmYXmDEXis9nPY2zJPyfpqmhR457FMtyzWdX7GJjfzCpTZ4MKy1s) [whale](https://solscan.io/tx/w4H2MM9uAwHBXEPavDDD87wtgSL4job4mCaxJ8z1bFYQcgCUFTexxQjcajn7zn1DVfeziuwsgN9GqwjpDchWkok) |
| 10 | 15:55:11 | [FTr872](https://gmgn.ai/sol/token/FTr8723FtUMfonSSRNxDmHfgWcuvcR18KGpFkVjLpump) | 8.6% / 3.21 | +9 | BAM `BUv44c` | time-limit 1.3 s | **-0.0192** | [buy](https://solscan.io/tx/2a3Ad11FjhktnLhReM5WXPUa3WE9v54Ai92QJ5VdNeLqQ6tn5TFxY5CfBkmUtYN5hPNZo3k42RfmoWKdF9AzVPQr) [sell](https://solscan.io/tx/5NPYqUA32mr8R6kcN5tmFfLhoySU7qGhuXeCePazomPAv6Z5mH4kFLw5m7M1MPoAHH9WsNZaJYuvF8PekQh1GP74) [whale](https://solscan.io/tx/2PfsSeaRF3HBbcDxF3h8cnCnCYg5oNdLDmwrSRTRunX5M9fw9VWGiEQE9uCD3DZPgAY3JeNirmyuXdSmHjZnYMgx) |
| 11 | 15:58:44 | [7QKUqp](https://gmgn.ai/sol/token/7QKUqpg3ZUaPyxVxw5uu2di1DGSj4h2oQXaxX9c4pump) | 9.8% / 3.36 | +5 | Jito `Chorus` | take-profit 0.9 s | **+0.0455** | [buy](https://solscan.io/tx/4eYLU7mqMJzjwrRtoJJmt9RoFt2QCseEWys9GgRFXz57XWJZuavk3Z613dwMAcTqTth3fgssTBFGHTT4fMPc8gGY) [sell](https://solscan.io/tx/eZNN8ehq3888mTssxVLBwz1xbwNgoZosW3DaXWjdYw5wP1RWjErm3bXyKqzjBuFxWhgfC6XXWyj1qHT6oxa9dFY) [whale](https://solscan.io/tx/4UBeHRZ3H69jDYfdwqvTzXuKPxnWU28jLG6W8Xd1raqV4aS8u76dpUxgdP5WNhZA5HMPHfrGrzksdBQQSLm3Jum) |
| 12 | 16:00:07 | [EAgBZW](https://gmgn.ai/sol/token/EAgBZWFuSCNKPgqRsB3cKbmfydpkwmyohqYhyXEjpump) | 6.0% / 2.44 | +8 | Harmonic `A1vqhA` | time-limit 0.9 s | **-0.0054** | [buy](https://solscan.io/tx/3UH1bq1AMykKUJFVXZxD7c5vYGS9M9PPDVr1EfvJgyQxvYx6zwzMwfxzWX6VBovwBysvRFVh6pF6p6KN9DJ3L1BL) [sell](https://solscan.io/tx/2pWqMTCoLXq9DmME363JnkNTyrLFzSdRhNCRqxTkTYt4AMbWVqmSZUHGV7ANLaRB18x1Dbq1kXxnbS6isS1UPTgq) [whale](https://solscan.io/tx/3GZFKLQ7VAwyeHtok4XWq8G4pmaby7BxVt2fzMMX85nYAsLXndk35wrHRboocd4gXFZqZstVCLyity9N1wXKaAhq) |
| 13 | 16:01:42 | [HNCyLC](https://gmgn.ai/sol/token/HNCyLC9iHnnaWJZpMcLWp2m7J2b296X58QB22LFMpump) | 6.4% / 2.96 | +3 | Rakurai `gUvo3g` | take-profit 0.6 s | **+0.0473** | [buy](https://solscan.io/tx/2jb7S2PydFAZRfu3dAhgdY1KQYPfwB5CvDisnPGQP477teem55awNnKF6QnFynMxECfiCqL9L7Nt2sk3STwqYSqJ) [sell](https://solscan.io/tx/2mcgooy8SMK1AyMNSm9EhnSEZ4HSMw3C7qXN5KxEobXr9fedd5UitHz4cvuyfVRS1vrSBULqGir77Bnqqp3GfH4s) [whale](https://solscan.io/tx/QRJtGptuGD3CAqFYkVRNNFZ19FokdTMBGgwcFBorDhXiQvrE133CEaoDaQoWNjjKqYe4TVUjyNcEBaCAsPSJwo5) |
| 14 | 16:04:17 | [4eZR2k](https://gmgn.ai/sol/token/4eZR2kApe4joC2gAxYR8AphdVCcnyCFHXnXrkvnrpump) | 9.6% / 2.95 | +7 | Jito `5pPRHn` | time-limit 0.9 s | **-0.0122** | [buy](https://solscan.io/tx/3dmjuTzc122z9i5MjPwNMWL9oxuXeCMqvK3w8VpnaX8XoqehpmUCgiW2k1w7Xyuf8NpUBkFLaPgiDtVA3zvbGt5T) [sell](https://solscan.io/tx/5wNYKTrZZGoPNN1LLvyakG2ivgMTL6dBQ9JuZogDG6tri7ampWkKJdSAyfPM1wzYHtPVzfvfrD4MmDTSc7zk7yNd) [whale](https://solscan.io/tx/4NGsczAufUwMWzEgEmqXPjavKcML1Q2Dc5xcd9so33S45BF2QkDns73UJon3AYg8gXXemqzBUekQw4DBzJp6RgLF) |
| 15 | 16:05:28 | [4A5Rze](https://gmgn.ai/sol/token/4A5Rze6vymbumzqnqLvxh1Qc8F3vyLYVqonkj8R6pump) | 6.9% / 2.96 | +3 | Harmonic `FBKFWa` | time-limit 0.9 s | **+0.0313** | [buy](https://solscan.io/tx/2t69p4sWCLGzkPV6nGpezLc6Sax5HPZy3VbnvxxZFvKYCppx1jz22e1vx9SvaTzTYtYoiJ7oxQjFURJjhmy7KHaZ) [sell](https://solscan.io/tx/65nM4MRgqruVaMmHk6nLLzFa6Lg7uPr9pz1V88Yfuq1Jr2X48WA9opwWgCBmQ2n6yqLBemUk4NzK4UyxUc34TxaL) [whale](https://solscan.io/tx/41Vu9tMy6P2TukAnyaXGh3Fkpesz9DtqoQNYteisubY7jnvSLf72BjwtHf2Bn9LMmtkstJAZdoVhhgijmwwafBG2) |
| 16 | 16:08:49 | [B3Uj4z](https://gmgn.ai/sol/token/B3Uj4zxmvHMyTKfjjSXkbmnVvSt2WZzGXhFX3VCapump) | 7.0% / 2.96 | +4 | Harmonic `Bi9kKN` | time-limit 0.8 s | **-0.0158** | [buy](https://solscan.io/tx/4CpBk5KCrwZChchXKb9YXgvGLWCJQshZD6gGSDWUuSRAZioWqLXeoDYnqZHKDLoYjmCKhVLYg9xaZWpmGG9PK9in) [sell](https://solscan.io/tx/3AsvzHJgfRAyKAWGPEmzyE2h5MeLqNmj4vdSkmkgHGDZGZ51vFjF5ZFsuvY6VxBmJKdVF7LbzympHzpuuhtw8s3m) [whale](https://solscan.io/tx/Wj3PQhn9hS7A7iVwLryZEFQ211Z9EVtPD4SFc58Vy1VHFkTXVcfsieAzCChTrdp9rN26zTJLdfLSV3GF7XFsaLa) |
| 17 | 16:14:28 | [89pbj9](https://gmgn.ai/sol/token/89pbj96BqL2QMM5PvyJM335rEM8c2azzvRdntg8kpump) | 8.6% / 2.86 | +3 | Harmonic `6YY2VS` | time-limit 0.8 s | **+0.0036** | [buy](https://solscan.io/tx/59RsYGyZ9DrYCn5hQ4owngodLJz8bA84cGnZrNAFRJDjceYCa4vJfuANU2X3s4BqFchsWSdijj1nyDgT8MGRqZxy) [sell](https://solscan.io/tx/U3Ukf86JBsYSXgTSLFrnVDSrXm9yiUNz6LWisBxQwsvwgYfJ9RDe8xxLzGDatEdjb4zEtcvRjufmvMJZ2B3c6QC) [whale](https://solscan.io/tx/2XoeQNS7Q9AfLM52fTaE9XbUYFXBDMz6p2kGMYtRAh4JBwyh185kL1t7cVvYzVcc2dVrkH6UenDv6PxW3m8uF8rb) |
| 18 | 16:16:55 | [8piYa3](https://gmgn.ai/sol/token/8piYa3r2NtX89SbnTD3ddcEcJLF5WXvLCXTFP7Mpump) | 7.3% / 2.96 | +2 | Harmonic `CAo1dC` | time-limit 0.9 s | **-0.0122** | [buy](https://solscan.io/tx/5wVMBcuiVp7ZCJw1Ud2DSYgehGNUMkwVDouFjV7oU1jQ956nEcAX6xoFihTkMS6ceepooq2AJzccfD3TKwDEfJuX) [sell](https://solscan.io/tx/4uGFswYjR1Ad71jP96FXtGXvJratyCM275bdAatZMoH57gFVgjSt9TWB4DJFcTsdPzJ4iBibgjHEbCydTFAdKMzX) [whale](https://solscan.io/tx/2z6rHcq9EQcZRAGAZDaEqSohVieVxDikgN1xN4uJYV67tQfXbvyCeYp6QsTLoih6frYkaLvJUG5vkHovjJBvBXQu) |
| 19 | 16:17:49 | [CiMLdK](https://gmgn.ai/sol/token/CiMLdKUmYn3NY7ma2hgCMxzTkQhjyFqtUJHQVGh5pump) | 7.2% / 2.93 | +2 | Harmonic `FNKgX9` | time-limit 0.8 s | **-0.0291** | [buy](https://solscan.io/tx/y2jJGV1xNVVSaSCHWEbmpyuR4nDeAm4E3Z99krHnX1YqRxYgZahg35CbABBheAmYLubnXPMhpsuUvdZQEPUzpUz) [sell](https://solscan.io/tx/39rigwfoyEEiM95VH8N8zWkCuTXd43HbWnNKgoJ9Gphr2uto5FVN5UneU6gwzyxVgKHGveSfrN2Q5FfRJE31xR5k) [whale](https://solscan.io/tx/BeyBQaZaDbVtyBub7LXZQPxEfAcwqqvsfXq41bRESiq5obem9KyYBYPNHr8dMdCDHidCdesyV678pSoz97y5NpJ) |
| 20 | 16:33:50 | [4Mw1pn](https://gmgn.ai/sol/token/4Mw1pnvQTL5AGv69VBthVJNR7SAaEhYAuBmsAcubpump) | 6.9% / 2.79 | +3 | Harmonic `CQdLgw` | time-limit 0.8 s | **+0.0156** | [buy](https://solscan.io/tx/3BjZ21vVQoPXHLVfVRq3VTu9vuRYxdFYHe9F3QzcV9gdLzstzjJQwzto1nnWwzsHvunkaHb5regDmXjBemHTmSGW) [sell](https://solscan.io/tx/5WJsk3gPgiiWj41jmAujmPTnkGWMm9hdouwy4VtvbyNLBjRBt41UmZQLkmhk5C8TPDpPjeV7itg99KuEHJTeogxT) [whale](https://solscan.io/tx/3g1A6To3KogFeSSVDH12uNWGhXgqu4Mdtnb9b25aWFe58RFQ8Fhfzv3PnGNbjGc1jv1V1AXRkfxJPpktnNvMKoxm) |
| 21 | 16:35:54 | [77scJt](https://gmgn.ai/sol/token/77scJtHcGY4nWxHUKzYx74CsumEhSzb8CwU3PpUqpump) | 6.8% / 3.25 | +3 | BAM `7y5VhV` | time-limit 1.4 s | **+0.0062** | [buy](https://solscan.io/tx/4roaDwTTSURrFHbaq6SmeyiFxbzN4fZXrwDky2vs3f3pAViLMnU2PDwFp3axLbSAunSttfxn4xadFHyBD1HuxFrS) [sell](https://solscan.io/tx/3N2bc5R5XrEgPromVYfamfv1QXPjmaBFTCYr1aKF4M1ZVPTtbDc6c7pBYMTEKPy8XA6tJYF5AuA9EMi8qpuVuMzm) [whale](https://solscan.io/tx/2BJhgnjW4sAAJK3uXHGXnr661R6ctCgP2PUbfE9Qc5r1voaqj6ZicmFsicvEpSEmD54P4AiZ1vH5xTBatKzFciQT) |
| 22 | 16:40:07 | [GBezN3](https://gmgn.ai/sol/token/GBezN3n8xfdvNHsUimVFaVd98qaNU9xzDWA3kbb5pump) | 6.2% / 7.64 | +5 | Harmonic `6YY2VS` | time-limit 0.9 s | **+0.0347** | [buy](https://solscan.io/tx/233hJgYWY3adHmsPQKfPbTTbDFWciJo8KnLDFemYcZNH2GDwwsJUSDv6k2HwpZAwH8yr951UGb2U77Py8f9Y7cdE) [sell](https://solscan.io/tx/FayPKrUnAqZdGqjsxeAudGLFDyuzxonypJdBFHPuRtcQSgCRwbkXLitxsGg3EJV2hRhtMJXXsH1WM5e7hmbM9UH) [whale](https://solscan.io/tx/3AWMXuSF3XVn9YL4tFi7EbMKqYcrxkgpET7Jntr3kPu8VnLDTN4qyVqPoz6nPWP2gQQvEdrwzgh7qC9ML8c4VFiF) |
| 23 | 16:40:55 | [4Mt6zE](https://gmgn.ai/sol/token/4Mt6zE3MCEHpVg2nBc6KWK1qTXdKcSRdkg7A5rC9pump) | 6.4% / 2.96 | +5 | Harmonic `grpton` | time-limit 0.9 s | **+0.0271** | [buy](https://solscan.io/tx/UUagHeUm5nh1zTUS9c4agZhZ4cdjvLQrkBMiPSESSFqAgy1C9wudaTUrvrhYoJYPi9edPoQ2bAQquShmZupqxQZ) [sell](https://solscan.io/tx/3tHVMEMUvC8sRhwBiMReuqUkULFfLdXjkSkm116Z63GxwAMsVpHnpyzKvbkTRWjHJ9z5Snp1TxBY6CcTgnkeimsm) [whale](https://solscan.io/tx/5Wj73DwsZhns1Qs2ZvGzG3YRJn5t9jTnkQsG8T1sY3UaDi2tMMHG9zeZi44buoeXDiYHxA1GQWkkZuQ1Aogd8V2j) |
| 24 | 16:41:36 | [EQxb1N](https://gmgn.ai/sol/token/EQxb1NT3Md3ZAUKoTKd6hgC458q2g3gbqGosPG1Tpump) | 8.8% / 2.79 | +6 | Harmonic `Fd7btg` | time-limit 0.9 s | **+0.0097** | [buy](https://solscan.io/tx/32PgBZJdmjKWam9LYXBf7FqUqvd96p4YJCmStg72vNgQ3S5ydxoLEY6MJ4GjdJFxsXemykbtDmfm7oHspTSZxrT5) [sell](https://solscan.io/tx/5AR7i45atJFFzFQkianW8jm3c6bC5jV6Y4BuqSxjiaiBBuSaU9sidzcRF4wVeRADzAaLcaki8uau6geSdUPbKV3n) [whale](https://solscan.io/tx/5WtmCLbrSBwFgPa9DfdVPuSMCwcPoUB7iNaUR7XHakrdJnVeKfGEz1dWsnxca7hajXY3nbgPgiNa8NpKPCJYbYY8) |
| 25 | 16:46:55 | [C7qWCu](https://gmgn.ai/sol/token/C7qWCu6YRQRYVb5JX4KJg2rvBbf1JWm2pxwp7VZ2gG6f) | 7.7% / 4.17 | +7 | Harmonic `3x9nib` | take-profit 0.5 s | **+0.0475** | [buy](https://solscan.io/tx/4nX7YteQUpLpeo6Bd5YABP8Wt5crbhmfapkihVuU7UwPdSRTgAZWE1vFsuS2bPtvKUHpjtHK6YKQNiMnQChckYoN) [sell](https://solscan.io/tx/4xAuUkjFkfN3ZgvjZAPKEmFwFfUkQHdBhnZbkSvWbvJmckdv5VJBk9weXJQbaJTmKuy4NVStQpLetaWgwT23zvwx) [whale](https://solscan.io/tx/3DtCkSqAQ3QUzvBZngteKvMfVg6y7Jh2R3HdbSXL9NAqnLRzuVpc1x8UsDzyf9QZ2pEHctisABvJdugnDt4xkhH6) |
| 26 | 16:47:29 | [DukPMY](https://gmgn.ai/sol/token/DukPMY4QNZPrLDTi8sXXNXDzRrrF1aPPUWGuh2fJ6Ast) | 7.2% / 2.96 | +1 | BAM `5Cchr1` | time-limit 0.8 s | **-0.0270** | [buy](https://solscan.io/tx/2Vbo6a4xLsiCii6NP3ZYGXsFK3PpYDdA7naYs37Yphen5o1NKXekWa6qbmATsi8SGGP4AdLkwNSNhtocS2Ccuntr) [sell](https://solscan.io/tx/mkHW8LtGafuwdcsGszhnwtvWBC6u4R6RJefXQbguPKEEs2CqQgJk3Jnbu5VbEa1qooSGk2NPHt3hQVAiNcTppg6) [whale](https://solscan.io/tx/zkzvEMvUg1857TgVDx93QPqYYuAagrJLjFBT3efnqKANacvjZ7ZV42GxH4Mvn1wMebUstcxumDZmXveBAxdjTNj) |
| 27 | 16:49:10 | [Hk5apY](https://gmgn.ai/sol/token/Hk5apY9Vn3bmSLPVAreDibd4E8F19ioLYgkHWZZpump) | 9.1% / 3.15 | +10 | BAM `5Cchr1` | take-profit 0.7 s | **+0.0317** | [buy](https://solscan.io/tx/24QZBbWr5ZMVZKWEq2TNp7383k7RtEiJ3vc388mbhMR7Y6JpgUdSLXU6MiPq93w3RNCqBuAiX2dXWrcDEUAS5sNf) [sell](https://solscan.io/tx/ZYRsDECRuHGTCDt8aUStNbJqKZBG9qwCTkVfpT1z6Lrpha2nkkLWu9zev1VUzvTjtP8DJZximQWnNChHB24PyLX) [whale](https://solscan.io/tx/4cjhcpyXYbbKkNPTtsc3gxwG41b6VBHDH7mapWQxK1GUr6Cj8GTn7VQFRBXmkpDahhkaKwa3hsanFXKqK8s3bGoQ) |
| 28 | 16:50:44 | [GmVGgA](https://gmgn.ai/sol/token/GmVGgAVN3xGxoQWMM7MedzkY4ihEnCjh4DkNVe3Spump) | 9.5% / 5.93 | +6 | Jito `E1r4Ps` | time-limit 1.2 s | **-0.0034** | [buy](https://solscan.io/tx/N2C6fEhYpYvpezzn2CQkNLW8ipruc3cyVGvXE2Njofp2nBQoGTRqGdcez4TCytWCFRHtuHmtr1iz6AfVZXXdfVN) [sell](https://solscan.io/tx/49K4zGWzFtmqJQdrJDxvMnr3oSv3iEUyKmK4jERjqPbUWravMDHiNDnmjABNcNkekUL3meEGHDtdMDytBJc7MSq5) [whale](https://solscan.io/tx/3H2k8WU8mopebH38TQ5G9wZrCbGaaiysEdQMsyPLyDSgTbJgp2gTKUGZhHxXLEA6FBy2jmDKpLkAX5ARA4TL9DBX) |
| 29 | 16:56:26 | [FNKkGM](https://gmgn.ai/sol/token/FNKkGM5bhwCvu8UZyP1MmBwNLuNh7rsfeVdxqfctpump) | 8.2% / 3.46 | +3 | Firedancer `9eGrDo` | time-limit 0.9 s | **-0.0171** | [buy](https://solscan.io/tx/2yQstwFU3UJbVKsFZKXGir8oLy6mcHvUDTbBbBYP9ZxAHBQRi1D8XyVAN8dz3DCRmuDr87tWVohLhsTCH5KVWpuY) [sell](https://solscan.io/tx/4RtRrxYRvPb4Sr2ZMe5qLkUHePcodeENYNuii3fjYgmU4toj5FaP2vyFjBzAfeJvE1poNc1SXHpV1J9toiBLXQBo) [whale](https://solscan.io/tx/4uhbT1UHkP32dhUH1vmfGnz9pUJLSt9CMvSDgKXtnng8pGccHUuB9sUCdyZJw38T6uobRU2Z4XWy3c7eLdvJsUWg) |
| 30 | 17:01:35 | [Aj4g9M](https://gmgn.ai/sol/token/Aj4g9Mp3ha66pNszpbTE5aswNrJNZQo2z1qA2dfvpump) | 6.1% / 2.96 | +6 | Jito `32ke3u` | time-limit 0.8 s | **-0.0086** | [buy](https://solscan.io/tx/5mzXqVYYamtqxWAZwfw5JGzUcdZoRWppDp5Z6UzSHRF9kC8WfLJ2kuNePxq34Mh1a6DuWk9ods1GpZD5NJkMNSwc) [sell](https://solscan.io/tx/ys1E3Mf9XexDDnMw8u6CPJVWXpQq1Tv15LpX5izF9NPmAMMYMaztQBDPsb2WsunaU2bHBdwqLjSLTxE8RUD2hPk) [whale](https://solscan.io/tx/3GCaMUpPY9kzNcPp7GcXuyJ7chZfB82yXBsUbxFP5ibGo3qzspjPudedttoN4xc5tpPrdq7xe6EbDQicB5n3i82r) |
| 31 | 17:02:21 | [3N44sv](https://gmgn.ai/sol/token/3N44sv2MFQ1SV36CP4NHZeNQkeXZekz6GLpyjbp2HiRm) | 7.4% / 2.96 | +8 | BAM `Fc6NNd` | take-profit 0.7 s | **+0.2203** | [buy](https://solscan.io/tx/5uP3awLXtLdrjW7mX2PgR6V4fh2ecvJVwP2BBHrQHfFuVW7WVjVtRc4zFN5YKTJ8hSCafDg8bX5EheAgXNgYqGXC) [sell](https://solscan.io/tx/2AmkDi88VSsc1Rni2EqybBF1Y5UoxW6pAeBSc19fEX1PVyrZA8kkqjyWRfGmHNLXcn3ZB1V4Y6Akb1pmUDaMJfWS) [whale](https://solscan.io/tx/49cc5aHKYgUVt4tFXH9faKYxoe4kiJrWzBZJTHZdygxQcoup3f8Y5cBRGZ82Qhsc4dDhjWtC2bEznhhWpKfS33r7) |
| 32 | 17:04:47 | [GhNrZ7](https://gmgn.ai/sol/token/GhNrZ7YCVniNTDEJ84nGVhoxTiUDcZyS2FC5bVhupump) | 6.1% / 2.96 | +4 | BAM `GmCxjm` | time-limit 1.0 s | **+0.0002** | [buy](https://solscan.io/tx/4HcREbVeNnxAfeQqgWwCXYEFQtQwV3oyxkBeLLW7fCacjHX7ha5k5384X6nVrZKKVcCTw89p5oiHCQh3uWpe6VZg) [sell](https://solscan.io/tx/3utNisK5maFr636jzma2tEQez1azTiuEVpo15G8YZGxfTBNNXQLWDK6Mb7Qt1ePvP7RdX2V1jnZfFsjRb9MT1KV2) [whale](https://solscan.io/tx/2kV2vhhnEBwQLs3axo4AreUobCVknzRLKR97Agb4aLGyUJ932QZSNN6vCShcFSvY3dKMyq9DbBeNFfTKppsE3U3g) |
| 33 | 17:07:32 | [B7jwy1](https://gmgn.ai/sol/token/B7jwy1MNX4Ejgzh4h12RVNp6xaX2jfTp9SfKUHQQpump) | 14.6% / 14.81 | +1 | BAM `5ejbTA` | time-limit 0.8 s | **-0.0377** | [buy](https://solscan.io/tx/4ygoV3p8nck8JYa2WKAZK423vjwmdLeuD7BicwyfJkZ8SEhs8vESpX4posbxBUVaFku6T3jdEdZcjbnNJFyjhpxU) [sell](https://solscan.io/tx/47es75fTe7XuvbWL2ats1PXNdD1Xq3W5rfP86q5dwBjtfCVLDAW8aAgFybcuowY5TsWbAxXsQYQ77iFULjYaVULd) [whale](https://solscan.io/tx/3P74iyKBZsoWXsb2PyFnrPT7LkeSna5LPGWWBNmm6L3Edb1gd5Z3pXgPqKoRLPjNvYN5HV2QvkrNXJcZTy2G1NRN) |
| 34 | 17:08:04 | [FGKfYR](https://gmgn.ai/sol/token/FGKfYRZHDiaKsNkN2sBUHNawvs3dVUjXXCg8ZTwopump) | 7.6% / 2.79 | +3 | Harmonic `XkCriy` | time-limit 1.1 s | **-0.0122** | [buy](https://solscan.io/tx/2h8YQ3hkKW9eiNKk7oYcrgxEJTrJjkHtjKxaN7dU5PteDqJGFgXG3aYUdqtL1KyRhdHSU6nncaLkF7Ceztkr8cj) [sell](https://solscan.io/tx/28fohCkXcaVpbrhadUbaTyi2bg7CVLRWdCjsgTJJQtgPaoS3iRJx71LSJX9i2PT1PEnwfKe9VDm7DnAV7CJAWikD) [whale](https://solscan.io/tx/48cyAtgymQjGnv73mPXXYk6hnET5BK8QMyWX5yWwb1WZkNjdFkVoAAysRG4BonMdErQfiXbeuAzHsoQpf5uxEUdQ) |
| 35 | 17:09:21 | [HNjk91](https://gmgn.ai/sol/token/HNjk91B1Fpg37MUnUQi8eg8VwLuTh8csDmxn5i7hpump) | 6.5% / 2.79 | +4 | Jito `E1r4Ps` | take-profit 0.6 s | **+0.0460** | [buy](https://solscan.io/tx/aS9PuzgxfYDoU7FCWrdvnJyNdq9uSJKmH1qbXHHFLhFVoraD2r9htdGqB2W28iH5fYKzekjyanccKGYHHuguv3C) [sell](https://solscan.io/tx/NXxRusdwBuMvovib5GPWDiqq9vegAFzmF6An3kYnsqx26esrnZinz1hRHeRHsCvGRDjkViFQUQMJQMmC4KY1JdD) [whale](https://solscan.io/tx/2VoBAdyH3fksT56vSHZkvTJ72T8HrYb1zFfdFTXCqnZUDmGqrgCxgjyTcXgnFtersVidxhP9SLF2susgyAkRf1Lr) |
| 36 | 17:10:03 | [4Bi8Xk](https://gmgn.ai/sol/token/4Bi8Xkq6e2irCwqVXJqptKmzSqtQPYyRmdvfRxiQpump) | 6.1% / 2.96 | +3 | BAM `RoYLtt` | time-limit 0.8 s | **+0.0190** | [buy](https://solscan.io/tx/5P7rLAmkkQ6dMvPBXFA69xs5PFSfY9hWAT3A3or8cWFtNDgNF3a5v9umS7gDcLq3XAgqun5bQnZw6camvvWygVf5) [sell](https://solscan.io/tx/d72VPnnCWEjHAZsPAfaARrKKTdgLnfQvNfqCD1gVpBmtzQBCftkrow2L3JJVpRCEYCgy459NwkckjU87fwTTM2H) [whale](https://solscan.io/tx/2Kg1T8S2YRqYGjVnggUWz2QHTejCAXs1hJYACZZAEQCtyqgss6yfVTua2HBymtNtjCDdYViKtfyKgr4UnR3M9ARL) |
| 37 | 17:10:37 | [5mz2yw](https://gmgn.ai/sol/token/5mz2ywJqEsofiWSWh8D2Sgn8js9TP1iseej2Sr4ypump) | 8.0% / 2.96 | +3 | Jito `Ha1iad` | time-limit 0.9 s | **-0.0122** | [buy](https://solscan.io/tx/41Kv476sFeaJufZLrogZLotXn2bsLR1fQwUFdXRUUc4eJkEwUFKrCi7zFWPdLHh2duCbgzAPunneyzcaGDhybr94) [sell](https://solscan.io/tx/Gm4pAWFjefuZ2JPr5yVxrwSvv1CU1Jf8pBFfUhf3rQ3Z6tBr9kqxa7z1ku7wc1vNyXYKZmeFTriKJXMgMWbvJtA) [whale](https://solscan.io/tx/5sxBsaVQEtQCjDmBUDBj343RDJ9SXJcPF4WLTa1jD83tzLyMvWtnG1tR2YUyuABkzxkRRpxXkkQk6Q5dbhZSnSbq) |
| 38 | 17:10:45 | [DCDVhZ](https://gmgn.ai/sol/token/DCDVhZPgedq5nu9fKeC2wShAGwDUSN9LL7pUGHJQpump) | 6.7% / 2.96 | +8 | BAM `BXAxLM` | time-limit 1.1 s | **-0.0122** | [buy](https://solscan.io/tx/5m1tL2vgEc1vrwmfDNnLCRP5YEhVLKANfRgJzx7f1eZdR3uYwWQF3A456YA7ExmVg56oNdvc8iJmyhM1uEv2YZB4) [sell](https://solscan.io/tx/3EchrMzxiE87uXDzLoRVhnsABmgQbCmCVmtdGvSDRJCJBm5YK2djcYV4y4mDsKArt11xWbYFUGZyp85P8hH8Ty62) [whale](https://solscan.io/tx/332RBxQz6vJukKFwKgYENUpUJ2SXFAYAbsar8anZ3a12YfsFrEan7gbU5RUBW1tpymJx3UTYhg9wANwiFTnRVB5w) |
| 39 | 17:11:04 | [HTSH1F](https://gmgn.ai/sol/token/HTSH1FBQYwUMwSxmBppreA8ABcY7RpZPpFjDuai7Wxmh) | 6.4% / 2.96 | +1 | BAM `DRpbCB` | time-limit 1.4 s | **+0.0073** | [buy](https://solscan.io/tx/23aB6AWAryjEfFvLYnroZKbtCHnf3em9UDbEG4XzagsNTBsLPxrUCLWbiP31VgCLqmqfaBK6tufHjBEm1UAdjbER) [sell](https://solscan.io/tx/4rNy7WqHt9DP7tWshBU2k3aZZgzQwNDcvDW6USS2pKK1XZjrK1wPXb9gQbU51yYFkzUyZYhyNk7ZRGaUumPtiZF7) [whale](https://solscan.io/tx/2ryiRD6mZ57auRvbgo5LL1u6JHdAR7CDGzc4qoBgN8Ci7wgjbh896aSNr7ShrM4qzLGQKMEuv4ffZz9StWabMwSa) |
| 40 | 17:11:22 | [GM6KZ7](https://gmgn.ai/sol/token/GM6KZ7vf6HSzfPFn7HsB7BGnyQD7dXndfzvxvG4ipump) | 13.0% / 4.94 | +2 | BAM `DRpbCB` | time-limit 0.8 s | **-0.0173** | [buy](https://solscan.io/tx/2NRDRdRT73fgJS8rTWdSuG1kdwiUETQD4zxqU3Lysqxatah2YZ9UdkUdMureYX2GdWVkUiTrf6uPK9tTEhH9uYxU) [sell](https://solscan.io/tx/42PrLAHVQBNsHH4yFAzBzGTAQFPkzziSJySKmVJzmY9Cnmg8B1hY1bmb9L6oKgSBrdHGFwj9fK1zfcoXrt6hEmzA) [whale](https://solscan.io/tx/dFZX47yYrLrbLPFLJqfKfbMKb3A5sCmaYGaBKGS61nNNRb7pPr11BuFG6GyUy5Ra4JUFKLfm8S9MKhHkQsD7Vyw) |
| 41 | 17:11:37 | [4Jo73V](https://gmgn.ai/sol/token/4Jo73VXgQqjyDdhzjNM8tfqXyurycq3AABSgfYzbHki3) | 9.1% / 2.96 | +3 | Harmonic `pSo1KZ` | take-profit 0.6 s | **+0.0328** | [buy](https://solscan.io/tx/38omW26yEvjA67HnKyPBxe9ASdav8fuk5wVxtoF83njcQjNtY7b5EpzVLqvDvXqnEcwSRs5S87Dpaj5ov7Z15edF) [sell](https://solscan.io/tx/Bxo2HfWA9cwbkxKnBndpS8gNnnQ7wLZxj8Lasm1CnhDfSAQhMsbQSyMqaoVB6nUrLpK7mskayXieJW7LmtMYTDx) [whale](https://solscan.io/tx/5LQWLdRgaY98bUQRkpUirxa2hGJc3DfoUVxwiAx97DXeDTEcCAdj1j63wq6hAAjkai6tg8cL37moLddiDVTQfD47) |
| 42 | 17:13:47 | [ii5pvj](https://gmgn.ai/sol/token/ii5pvjaC8oNWX6VGR52BfhQ18DbPg5BjLMaTvHnpump) | 6.4% / 2.96 | +7 | Harmonic `Bi9kKN` | time-limit 0.9 s | **-0.0255** | [buy](https://solscan.io/tx/YXpitbWWHJfiWYzuVgMmdGnntvNEmaEJgCaiEe5t5MsLZRpMqRDyLesfHDWiEba4RWW9r8ErhggPJzn77MuvWwv) [sell](https://solscan.io/tx/5Sb97C4Y75gis48TfoGBukQzUFxPeLV9QGSNss6PUwZdRtbWy2BRzuk2hG9iGgg6DHv9AEpXaR1TnMneyhtXtXK1) [whale](https://solscan.io/tx/4BjcBtGpzFMehw5hJuuN2H64oTxaTdUzXM8ZYTYGm1ZF8yB59e9grUp71L2kdMhykTzECWBYsDPmADAc7oVsgLYQ) |
| 43 | 17:16:24 | [CuJmx6](https://gmgn.ai/sol/token/CuJmx6oNyUbiHqcqfTYvPp32wcLURj7uEgqLH9GFpump) | 6.3% / 5.90 | +5 | Harmonic `JUPiTE` | time-limit 0.9 s | **+0.0242** | [buy](https://solscan.io/tx/3HwYco6vBZdQdxE5wUsbYnypQvumF856ZQ7ESHLbBTxy6UjstqRVmk5EXSKavopMuxmrU1RqPpnuxKs1Hf9t8Vne) [sell](https://solscan.io/tx/5NC87TFPU6W8RobWJUFW29Z1H2MxXFQy2XgkumJ5QhdFvDZQhM1yTBSMzLuexb5oDYJJSgxWAvp9Nfk4ZEhLPj6T) [whale](https://solscan.io/tx/2JBp3JpTQWdQzu7FFmx9ufLjrskA8SF3qUwFk649NqoKGy3BycNgLCiiS7X5opSYe1dy8HwCdaQ3CzykUkiKq7Ma) |
| 44 | 17:16:38 | [HNY2cV](https://gmgn.ai/sol/token/HNY2cViYoemxSSQHRQrhsgmLo2Qiwyt492xhHDAgpump) | 8.0% / 3.25 | +4 | BAM `HLnodb` | take-profit 0.6 s | **+0.0561** | [buy](https://solscan.io/tx/2k9NVX8o31vWx7EqJGFeQ8qUa2KvWb56butUZ7cx75ghv2anoh6mrRn5h7mQRh57K9GtyhyDZj1WKsGWvcqMdtbG) [sell](https://solscan.io/tx/2aNU5Hh559MziyDwqCesc9E2NrJwMwagxh91XRgvph5Qr8LtnLmtNDZLxrUR8Xn9AzVgaKpfXqmhS46mwnGyMZKx) [whale](https://solscan.io/tx/2BvUJFxkU9TsZNgaovyqdT4JedR69Mw6kKEeGSAj6xk7iXSmf18tRHMvQwbovFAAJ6DxhfeWUuCRtDy6Kq99Rpcx) |
| 45 | 17:18:46 | [7u8p3e](https://gmgn.ai/sol/token/7u8p3eymTVS9hyFeCWZbDNcQkKVzMMcUjSFXnhJXpump) | 6.7% / 3.46 | +3 | BAM `7qGNnX` | take-profit 1.0 s | **+0.0488** | [buy](https://solscan.io/tx/5MCazxYDdhuYt63xsBTi1UxjknchYSvr2s2zFJWuHVxpnKYqjQ5e9VugXHkz38sMpSZURey2PPsku3sb97XFynba) [sell](https://solscan.io/tx/5hSgPh83DSW9bUpoPEWzk6vgYjk3X9obJvoPdReuVHqQ7bnrcWZbdi5Gd6dcx1FAGyC8j5cAobwzQ2nHCxRcM9QT) [whale](https://solscan.io/tx/2uNtS3PAKnnPTS35dvVgJvkUHY6xSGBwq1At3Whu99U3LKNz1Xh6YntMRWPL1EJ5dUna3xR5mLMiMQt4SXoBuT4o) |
| 46 | 17:25:37 | [HprsR2](https://gmgn.ai/sol/token/HprsR2nkA574sukFETo6ejjsFfuvAvXa3NbKPejRpump) | 7.6% / 3.91 | +2 | Harmonic `5RvfTS` | time-limit 0.8 s | **-0.0164** | [buy](https://solscan.io/tx/5kRHwe9wVgVTjbZExwNN1X9opGMvWEcnaF6eRUSmGfKgNYTzRcpv8tmSJVio5YYcjRAVupahRfkpLwMNDHEjz3hC) [sell](https://solscan.io/tx/4EPkgjcxWgUcbaGt5Hff4n2um82FpAnb7UXEitnZLTjrDHgGM38AWMFtvcDNdT5ibRMov4v6eBtDrauQyE9qzWfv) [whale](https://solscan.io/tx/452Ld4KQeqp4fqeiwAkaDYTviBAuZ1SzUpaWFmtgqM4G3e9FiNbiduiWsYX9uEgtqcG2fZZiLyBaojRsaSp9PHy8) |
| 47 | 17:25:44 | [A4afZK](https://gmgn.ai/sol/token/A4afZKwaAF337AViUwaCSTbUageJHBxMxby2iNJapump) | 13.6% / 4.94 | +3 | BAM `CTwsru` | take-profit 0.8 s | **+0.0605** | [buy](https://solscan.io/tx/3C4d7SFQPUPrCnBusZGzJAqkzSFzBYa3vFev4nkLLEBB6cZJc195MFShkHJYUzsT5xGxFYd6oJT1457AjsHp4DGJ) [sell](https://solscan.io/tx/3SDFKdjSpN71tUVHbHMUPaUaMXLeEzfgKfewzigcYr6o15s6e4KAUzwQti21F9fjx5XHCMSuKwT2d6cUu3s9kAX6) [whale](https://solscan.io/tx/4SUC33pBewVoU5nBQSJGttTGfP8jbr16p9CNFDGp3Xqf6mYfJMr123s7PiuQ13rhtkwG347Qne2EWw4BDuLPbdLS) |
| 48 | 17:29:51 | [59T8Fs](https://gmgn.ai/sol/token/59T8FsaQaV3tWAsWMHJnrbeB4S9hKFsmCArihQ6CS1Ep) | 9.8% / 6.78 | +2 | Firedancer `BbCQMW` | time-limit 1.0 s | **-0.0293** | [buy](https://solscan.io/tx/4bKWa9SjxKN3YZkBgZnkXFtTbHp75jK6QyYivctsToYs6Fjns8brx1EiCDGRFeBkkcGD4T3gUhCzLChAZcFcxXRH) [sell](https://solscan.io/tx/Vvmiogu8ArB4PLRZDMxq3vGnTAHLMpzYfNd66FpBKs1Y8xSMDNh6F8iamsiGQor2E4zVUJdzK5dkfMzCDvQY3NT) [whale](https://solscan.io/tx/kUJ9vUZEhepmnxeGefuzRaeWC8fXmksaoTiiXxoGV587TSupHiRzdTjxqyzwH23nvEvcVj69zSkPsqhFQcHyYrj) |
| 49 | 17:29:51 | [EG7Kus](https://gmgn.ai/sol/token/EG7Kus8vqNotMgC9Wy6RqTLovDCi2v7TGPgQhLfopump) | 16.6% / 6.78 | +2 | Firedancer `BbCQMW` | take-profit 0.8 s | **+0.0599** | [buy](https://solscan.io/tx/3d6cPgkb8rEABS6fKPzsQGCY2vwm4BM6jhbs3E2SoMvMTaPZr2VXRvBp8DsP14zj3cFgjDTwYuKKTLbH4VPJtnsJ) [sell](https://solscan.io/tx/269HJ1zkU65nM1SZ7Bd3128Xne8n6hXw2ikfiJeXQh8rkYsMBqukgNHsDqJ8TMYzmhSYiLXdZRDij8MBidHJ4gxA) [whale](https://solscan.io/tx/gxQJEiGyiTcpAnionGMVVpNUMWAqF9zxtkwzesKyqHox2p3AqFWbUit41CLbZCnqFxg4amkKU2tA7dCbj6MpSKx) |

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 7847 |
| Inside the envelope (age / drop / since-buy / size) | 3535 |
| Picks (score above the threshold) | 67 |
| Skipped | far_leader 49, spacing 5, presend_armed 3 |
| Buys sent | 10 |
| Filled | 4 |
| Failed on the +5% guard | 5 |
| Failed (other) | 1 |
| Never landed | 0 |
| Sold (positions closed) | 4 of 4 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 15:35:23 | [4999ip](https://gmgn.ai/sol/token/4999ipQaDvq8TkCsi49rMRXTsMs3aPpx8ywVyxJhpump) | 0.35 | -1.12 | 1.12 / −7% | 10.2 s | Jito `Chorus` | guard fail | -0.0005 |
| 2 | 15:42:06 | [BryTFG](https://gmgn.ai/sol/token/BryTFG56T6SBvJeJra4WsThxQCn1zZ3Lob4CPR5xpump) | 0.35 | -1.17 | 2.40 / −10% | 10.4 s | Harmonic `DrifTr` | failed | -0.0005 |
| 3 | 15:48:36 | [CRMjYM](https://gmgn.ai/sol/token/CRMjYMwurQFTLvmiBgH31hBn3mqP4GNcsb1FCAzxK16M) | 0.35 dev | 0.35 | 3.22 / −16% | 7.0 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 4 | 15:58:10 | [EAgBZW](https://gmgn.ai/sol/token/EAgBZWFuSCNKPgqRsB3cKbmfydpkwmyohqYhyXEjpump) | 0.35 | 0.36 | 3.08 / −11% | 49.0 s | Harmonic `AMukCL` | guard fail | -0.0005 |
| 5 | 16:21:38 | [EQuxQq](https://gmgn.ai/sol/token/EQuxQqdvKD5r2xzb6FfbPaAAxF3MPyQKy3qV73RBpump) | 0.35 | 0.11 | 5.26 / −14% | 61.7 s | BAM `CoG8d9` | filled | **-0.0104** |
| 6 | 16:45:45 | [F21dyE](https://gmgn.ai/sol/token/F21dyEot5WH6HzgatUDrYzPfHbgZP86x1kfKS3v5pump) | 0.35 | -0.24 | 2.76 / −13% | 2.5 s | Harmonic `GoeW4a` | guard fail | -0.0005 |
| 7 | 16:50:46 | [GmVGgA](https://gmgn.ai/sol/token/GmVGgAVN3xGxoQWMM7MedzkY4ihEnCjh4DkNVe3Spump) | 0.35 | 0.39 | 3.51 / −14% | 4.5 s | Harmonic `HTeRsa` | guard fail | -0.0005 |
| 8 | 17:21:15 | [4nGvvk](https://gmgn.ai/sol/token/4nGvvkcFFvVQR2wuC9GAnGJfkXXPtwVte869N1Kxpump) | 0.35 | -1.99 | 1.16 / −7% | 13.6 s | Harmonic `XkCriy` | filled | **-0.0125** |
| 9 | 17:25:18 | [GFcPyQ](https://gmgn.ai/sol/token/GFcPyQBJD4R5eikQeHjx88tQgxgwvCXxgSjtysLa4cBw) | 0.35 | -2.56 | 1.08 / −6% | 33.9 s | Harmonic `EkvdKh` | filled | **+0.0090** |
| 10 | 17:34:51 | [CKTeAG](https://gmgn.ai/sol/token/CKTeAGpoLT5koBkMxKPRa71XJ3LRRFySU1HfkyW9pump) | 0.35 | -0.84 | 3.05 / −17% | 10.4 s | Harmonic `GoeW4a` | filled | **-0.0175** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 129 | +1 | 2 | **glaive** of falcon-udp+glaive+falcon+helius-swqos+0slot | – | – | [buy](https://solscan.io/tx/jaASQXFUtbv8k6E7AvMDXKtRi1hb2tEJpSCzP7MUyRsfQjs5vGkq1U8cSt5rrtBTEqPSjarN25PF56HUAGS2Saw) [dump](https://solscan.io/tx/22KBHqHa7CJuLhDxMN4BeCuhtcTHUoEvYuRH1bgB3TkbmwFkm8RHCGALMRRgm2qrgN4VCMnww4E5Q1yZ52bK7Mp8) |
| 2 | 1172 | +6 | 22 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/kSvMiRKSVm5mbjvJbbrmDZSrRcpXoDrFVJhyTig4LET4ZW1qVQDgXiEktHNjVpY4u55xVEND8AxB2zAfYdspRJR) [dump](https://solscan.io/tx/3DETcmJGSerFxDADtATzW6vLxezkMX3ppHuDda33sfAjnMcPAmpKtaTwrYWexGbX3E6xpEvudabgSsvbSMej9RPf) |
| 3 | 122 | same | 4 | **nozomi** of falcon-udp+glaive+falcon+helius-swqos+0slot+nozomi+bolt | – | – | [buy](https://solscan.io/tx/3DZTJ1LKsbbHSaNmKi4zX9HnurqEZYMvBFqKT9eg3ufi4nJbSwsP7tkaRWKuVFe1ZQDkDE1i6K8MNhgyknXw522g) [dump](https://solscan.io/tx/a685SRf2kVQycxW4FrQTnkqMwiJrDPjvx6ymUt3pQT6nFBHpAWEJRMiHjzbk7C2wTquVyvdQRuTHgKfbwE96ekj) |
| 4 | 41 | same | 5 | **0slot** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4WQS8BqwQi2Qohx47SRK6qxQcJiZ31AF5EeUiTtwU1tDZWm4cxdiPQnXaib1xzhtWdi9mF1q6t4yYNfAa4kKBGr8) [dump](https://solscan.io/tx/mEuyiuK54ttUpahiW3QWchp9YqCC5H1nkTFc53niaJxx95xB6Jbj4MBDdFWKWsCmuFwBzJ32zazj1KF55fFbY8g) |
| 5 | 67 | same | 3 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon+0slot | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/3JwW7vLLL93PmVsc28NehCM4obr4yK7Yde55RQypYihgeME5q56MkGHdbiSD3kRid97LCXzvMr6U2YGSzuYqxFad) [sell](https://solscan.io/tx/35VMbXLEDYyaPrH2NwYC3M4fD34w78iL2voX2HjJ78hZRedxeGJGne7LbSvqYKmfAvoSA9gCooFXD4gWxYaYmJTF) [dump](https://solscan.io/tx/37U5SmwiPy8FgEQVxtiKLeCorcB8GWn5mPXRzxa8rdX34HAc5Wx3PRsRBZxF8oxjcx3r8tvS8VQQgrgjijjY27ye) |
| 6 | 44 | same | 4 | **solami** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/3R5K4M2nJxu5hZJu3kXi88MKo8SJAxtAktD1iEPdYZ4RPAXZ7ZpQjWPcQJR4fmR3zNCxY1RkVMjzfMawqyaADvxA) [dump](https://solscan.io/tx/xmAqNBiX42thqTXzqJXRxBiaDeRDvEkwCg3HDZAzaYKZ6qbjSw6vMJDWkoPBSxiEXqyTMvBF7AueBd4aBF3eAhJ) |
| 7 | 37 | same | 4 | **soyas** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | – | – | [buy](https://solscan.io/tx/4CmU75dj6KmzXswHMHesrZiZsEYG95dbTrh7zSSorbSoZBZAGEpLE2mjpUTE2DJ7P18gEayuUKtMy9BDSac3m8sS) [dump](https://solscan.io/tx/mkb72WkQJkMgL6EKESGnesg7EGJS47K27e3UdfDWmBpi5cZsQwmqno5rnpMsTFX8K1UGtwRC2dc9sj8yvR8tfTk) |
| 8 | 16 | same | 0 | **falcon+falcon-udp** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/8pQEskjP6gdjwno89cTTEZZru7NxaMo8MrFwev4JLocdRBRARHVEmhvexoFQ41oW7JsVn3BxngQJZ3GX6VHv94x) [sell](https://solscan.io/tx/4HEFjiHUsDWu6Pmbj27tkup1jZ9eN7aV8zyBdJSPh7cTt1oRcDUGP8rMWme4rL3BUNRc97wQtGHSUCQHvpgkYpy) [dump](https://solscan.io/tx/zwtoDqYYzwnDnSogNs1gceHf6aURrS55JiYDRa9trKTpVrTJkxfT5XpeAJRVJVwMMY5eRvRqykk5AeJ8qXX4XF6) |
| 9 | 39 | +1 | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/62F9KmMhuPeNVGqTyMxhQ9sDqWLZ5MPGgj8j9HwJg8JpdFgEJ6vRR4dGuZgRzwiacaok41HAjpeTrN9kKivWSkNg) [sell](https://solscan.io/tx/25NbyyGcGdbWfeYkDtrGoowZR9jgc1B9BHqiTZfjA4juA97UKF116W4jcmu5M9Cm6P6iykAWJwAVtxF8p3ZA6aca) [dump](https://solscan.io/tx/fQ1w4Hz2PRY46wmuVQaraHbYPU6PsodLN6Pwk5Hm42yMH9cEGSxpJedSV99kpAD6UrHEjiT5a8nEf1n2eLeSDoM) |
| 10 | 32 | same | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive+0slot | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/5rxMehhjAPzZYuw6BG9XJ7ERD62T9epEv2W29R9MevcU9biitRMX1WzkqeudbFH2W87tg4UXMMLo2HViaqVabX7K) [sell](https://solscan.io/tx/3yqusTBtA13zqs53hbMeRVFyBHKgk9Ddsyo5v3W4Q3UYmohCDapN1t3RvfuRsd1CwFUetZsDgP3pDmSbswYUivxY) [dump](https://solscan.io/tx/2RV8Yjpswmst4UQxCycFtQPw4r7D5yNA7BTX9aNA3XLpk7m562R5wbhnSUR6jQ9Z23u6WhDDKGtSi2rQRFFk1AyY) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Harmonic | 7 | 3 | 43% | -0.0231 | -0.0070 | 1/3 |
| Jito | 2 | 0 | 0% | -0.0010 | – | 0/0 |
| BAM | 1 | 1 | 100% | -0.0104 | -0.0104 | 0/1 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 9 | 4 | 44% | -0.0339 | -0.0078 | 1/4 |
| dev list | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 7 | 3 | 43% | -0.0424 | -0.0135 | 0/3 |
| next block | 2 | 1 | 50% | +0.0085 | +0.0090 | 1/1 |
| 2+ blocks | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 15:00 | 4 | 0 | 0% | -0.0020 | – | 0/0 |
| 16:00 | 3 | 1 | 33% | -0.0114 | -0.0104 | 0/1 |
| 17:00 | 3 | 3 | 100% | -0.0210 | -0.0070 | 1/3 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 4 | -0.0314 | -0.0078 | 1.5 s |

## 8. P&L leaders
**Best trades:** GFcPyQ +0.0090 (Harmonic, time-limit, score -2.56); EQuxQq -0.0104 (BAM, time-limit, score 0.11); 4nGvvk -0.0125 (Harmonic, time-limit, score -1.99)

**Worst trades:** CKTeAG -0.0175 (Harmonic, time-limit, score -0.84); 4nGvvk -0.0125 (Harmonic, time-limit, score -1.99); EQuxQq -0.0104 (BAM, time-limit, score 0.11)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `EkvdKhUL` | HarmonicAgave | 1 | 1 | +0.0090 |
| `Chorusmm` | JitoLabs | 1 | 0 | -0.0005 |
| `DrifTrN9` | HarmonicAgave | 1 | 0 | -0.0005 |
| `5pPRHnie` | JitoLabs | 1 | 0 | -0.0005 |
| `AMukCLCr` | HarmonicAgave | 1 | 0 | -0.0005 |
| `HTeRsa3g` | HarmonicAgave | 1 | 0 | -0.0005 |
| `CoG8d9Fp` | AgaveBam | 1 | 1 | -0.0104 |
| `XkCriyrN` | HarmonicAgave | 1 | 1 | -0.0125 |
| `GoeW4aFK` | HarmonicAgave | 2 | 1 | -0.0180 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 2275 (p25 1770, p75 3992, n 10) |
| Executed-feed lag behind first sighting, ms | 1.0 (p25 0.5, p75 1.4, n 10) |
| Buy sent → our tx seen on the feed, ms | 39.7 (p25 34.1, p75 118.9, n 10) |
| Fills: our buy seen on the feed after the dump, ms | 36 (p25 32, p75 39, n 4) |
| Guard fails: our failed buy seen after the dump, ms | 44 (p25 41, p75 122, n 5) |
| Fills in the dump's own block | 3 of 4 |
| Guard fails in the dump's own block | 4 of 5 |

**Which copy landed (nonce fan-out):** nozomi 4, soyas 2, glaive 1, 0slot 1, solami 1, falcon+falcon-udp 1

**Send-path answers (FAST-ACK lines):** falcon 10 (median ack 0.9 ms), 0slot 10 (median ack 1.5 ms), glaive 9 (median ack 0.7 ms), nozomi 9 (median ack 1.3 ms), helius-swqos 3 (median ack 0.8 ms), bolt 2 (median ack 1.0 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 3.46 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 2YXTUm74 | 3 | 3 |
| 8PgC4ngp | 3 | 1 |
| haqq (dip bot) | 2 | 1 |
| 8yYMhuYo | 2 | 2 |
| 9pQQc1xy (bait follower) | 2 | 2 |
| Ai1SoJhK* | 1 | 0 |
| HDp472dU | 1 | 0 |
| 3Lu6DXW8 | 1 | 0 |
| Bcn2qwBC | 1 | 0 |
| 2qVqccpF | 1 | 0 |
| 7PRtq4CC | 1 | 0 |
| EV8mH8fD | 1 | 0 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.0166 |
| Pump fee on buys | 0.0173 (0.0043 per fill) |
| Pump fee on sells (residual) | 0.0175 (0.0044 per fill) |
| Buy tx fees (base + priority) | 0.0020 (0.00051 per fill) |
| Buy tips | 0.0040 (0.0010 per fill) |
| Sell tx fees | 0.0024 (0.00060 per fill) |
| Sell tips | 0.0048 (0.0012 per fill) |
| Failed buys (tx fees) | 0.0030 (6 buys) |
| **Result** | **+0.5877** |

Buy compute used (fills): median 81,352 CU, max 82,904 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ start refused: Error: keystore: wrong passphrase or damaged file
- ⚠️ 52 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ RPC bh-fallback getLatestBlockhash: 3 timeouts/transport errors (worst p99 205 ms)
- ⚠️ RPC bh-fallback getSlot: 3 timeouts/transport errors (worst p99 279 ms)
- ℹ️ 4 send-path health events (self-heal), e.g. `SEND-PATH rpc bh-fallback UNHEALTHY: 3 timeouts / transport errors in a row (getLatestBlockhash): client REBUILT (fresh `
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)
- ⚠️ BryTFG: landed 6 blocks after the dump
- ℹ️ wallet change +0.5874 vs trades +0.5877: gap -0.0003 SOL — about the fees of the 58 pre-send tries never seen on our feed (up to 0.0003 SOL if they all landed and failed; inferred)
- ℹ️ falcon refused connections at 15:30 (×2) and 17:30 (3 in a row, rebuilt). It is one of 7 paths for reactive buys on BAM / Harmonic leaders; pre-send uses helius-ps only.
- ℹ️ What the 45 stopped and 36 skipped windows would have made cannot be measured live; a replay on the chain recording is pending.
- ℹ️ Paper shadow row c: 91 fills, net −0.046, vs live +0.622. The engine's shadow is not a forecast for this setup.
- ℹ️ No tokens left in the wallet (chain 10-27 ~17:40 PKT: 5.519834 SOL, 1 empty token account).

Checks passed: every reactive fill was sold; every pre-send fill was closed by a sell; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Recommended / open:**

- Replay the 36 skipped and 45 stopped windows on the chain recording to estimate what QUIET gave up and saved (ops/strategies/presend/filter/live27/).
- dip21 (whale history built on the host and pushed to every node) removes the 60-min warm-up on AMS.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r27.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r27.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Pre-send (section 4b): the jsonl presend_live_* records (fills, closes, REALIZED, account closes, stops, end checks) and presend_attempt_land (try results, failed-try fees); the log's PRESEND LIVE lines when a run has no such records.
- Engine sessions in this run: 1; refused starts: 1.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 17:42 PKT.

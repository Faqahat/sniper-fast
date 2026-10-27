# Amsterdam run 20 — dip bot run report

*Live, same config as Frankfurt run 21 (M2 gate + live pre-send 0.35 / k 4 / 20/s + routes v11 on dip18) — but regular size 0.45 SOL (owner); a head-to-head race with Frankfurt*

> **Verdict:** −0.250 SOL on the wallet (2.066 → 1.817) in 44 min. Pre-send: 34 fills, 16 wins, realized −0.161, failed-try fees 0.013. Reactive (0.45 SOL): 8 fired, 3 filled, −0.076. Race on 20 shared pre-send fills: Frankfurt landed first 13, Amsterdam 7 (the 10 shared fills before the race: Amsterdam 6–4). Paper alone over the same 44 min: +0.09 to +0.14 at 0.35 — live lost because both servers bought the same dumps.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.2494 SOL** (wallet 2.0664 → 1.8166, Δ -0.2497) |
| Started (PKT) | 2026-10-26 01:16:51 |
| Ended (PKT) | 2026-10-26 02:00:52 — stopped with Ctrl+C (SIGINT) |
| Ran for | 0 h 44 min of 240 min planned |
| First / last buy (PKT) | 01:24:04 / 02:00:45 |
| Server / wallet | cyber-dock (84.32.104.202) / `EgxfYgEb…` |
| Buys sent | 8 → **3 filled**, 4 failed on the +5% guard, 1 failed (other) |
| Fill rate | 38% |
| Wins / losses (fills) | 0 / 3 (win rate 0%) |
| Per filled buy | avg -0.0245, median -0.0261 SOL |
| Fills only / failed buys only | -0.0735 / -0.0025 SOL |
| Reactive bot / pre-send live | -0.0760 / -0.1733 SOL (pre-send: 34 fills, realized -0.1606, failed-attempt fees -0.0127, 16 wins; see section 4b) |
| Best / worst trade | 7zzoiG -0.0052 / 8NYB87 -0.0422 |
| Fill landing | median 110 ms after the dump (seen on our feed); 1 of 3 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip18 |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.45 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.45 SOL |
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
| near-leader gate | 120 leaders (buys only when the dump's leader is on the near list) |
| pre-send | LIVE: whale >= 6%, 4 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 100 fills / 0.1000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 240 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Amsterdam run 19**:

| Setting | AMS run 19 | AMS run 20 |
|---|---|---|
| engine build | dip15 (dip14 + pre-send shutdown grace + empty-route refusal) | dip18 |
| size (normal) | 0.35 SOL | 0.45 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.55 SOL | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.45 SOL |
| route: bam leaders | nozomi + helius-swqos + bolt + staked-rpc | nozomi + helius-swqos + bolt + falcon + falcon-udp |
| route: harmonic leaders | nozomi + helius-swqos + landx-fra3 + staked-rpc | nozomi + falcon + falcon-udp + landx-fra3 |
| route: jito leaders | helius + nozomi + jito-bundle + staked-rpc | falcon + falcon-udp + helius-swqos + helius |
| near-leader gate | 54 leaders (buys only when the dump's leader is on the near list) | 120 leaders (buys only when the dump's leader is on the near list) |
| pre-send | LIVE: whale >= 6%, 8 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 100 fills / 0.1000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% | LIVE: whale >= 6%, 4 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 100 fills / 0.1000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| limits | max 60 fills, 1 open at a time, 120 min, loss cap 0.181 SOL | max 60 fills, 1 open at a time, 240 min, loss cap 0.500 SOL |

- Amsterdam idle after probe 3 → owner: 'frnk has less activity than ams, run ams alongside with same config, so we can compare'.
- Deployed dip18 + falcon-udp side file (udp://ams.falcon.wtf:9000) + run script b305d2ec while idle.
- Owner started it with --size 0.45 --dev-size 0.45 (pre-send 0.35).

## 4. Timeline (PKT)
- **01:16:51** engine start #1 (session with 8 buys)
- **02:00:52** engine end #1: SIGINT: no new buys; open positions finish their exit, then the run ends

## 4b. Pre-send live (pre-placed buys) — separate from the reactive bot
Buys pre-sent after a big whale buy, before any dump. **Not included in sections 5–11**, which cover only the reactive dip bot. Realized = the engine's PRESEND LIVE REALIZED records (chain txs of each buy and sell; the buy pays the token-account rent). Rent back = that rent returned when the engine closed each pre-send account after the exit (dip19+; before dip19 the sell closed it and the refund sat inside realized). Failed tries = fees of tries that landed and failed (6042 price, deadline, …). Net = realized + rent back − failed tries.

| Session | Started | Size / fill cap / fee cap | Tries sent | Fills | Wins | Realized | Rent back | Failed tries | Net | Stopped |
|---|---|---|---|---|---|---|---|---|---|---|
| #1 | 10-26 01:16 | 0.35 / 100 / 0.10 | 2,598 | 34 | 16 | -0.1606 | +0.0000 | -0.0127 | **-0.1733** | run_end |

**Try results (as seen on our feed):** 6042 2,132, deadline 313, unseen 79, ata_exists 40, ok 34.

Tries never seen on our feed: 79. If they landed and failed they cost up to 0.0004 SOL in fees that are **not** in the failed-try total above (5,120 lamports each; inferred, the engine does not see them).

**By exit reason:**

| Exit | Fills | Wins | Realized SOL | Per fill | Median hold |
|---|---|---|---|---|---|
| time-limit | 28 | 11 | -0.2402 | -0.0086 | 0.9 s |
| take-profit | 5 | 5 | +0.1960 | +0.0392 | 0.8 s |
| stop-loss | 1 | 0 | -0.1165 | -0.1165 | 0.6 s |

**By leader type (the slot leader where the fill landed):**

| Leader type | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| BAM | 12 | 6 | -0.0715 | -0.0060 |
| Harmonic | 10 | 5 | +0.0142 | +0.0014 |
| Jito | 10 | 3 | -0.1670 | -0.0167 |
| Firedancer | 2 | 2 | +0.0636 | +0.0318 |

**By hour (PKT):**

| Hour | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| 10-26 01:00 | 33 | 15 | -0.1983 | -0.0060 |
| 10-26 02:00 | 1 | 1 | +0.0377 | +0.0377 |

**Best pre-send fills:** 7JBQnZBB +0.0584 (Jito, take-profit); DEf5Aa91 +0.0406 (Firedancer, take-profit); JBX3aqVZ +0.0377 (BAM, take-profit)

**Worst pre-send fills:** FnkjEdN2 -0.1165 (Jito, stop-loss); CSsmSNoH -0.0425 (BAM, time-limit); FRwW7etm -0.0375 (Jito, time-limit)

**End-of-run checks:**

- session #1: no END CHECK line in the log (engine before dip19)

**Every pre-send fill** (time = fill; whale = the trigger buy; P&L = realized, rent back not included):

| # | Time | Token | Whale % / SOL | Slots after whale | Leader | Exit | P&L SOL | Links |
|---|---|---|---|---|---|---|---|---|
| 1 | 01:21:35 | [EikmF6](https://gmgn.ai/sol/token/EikmF644QmzAFruSYox4sUNSbx4dxaSBgSKFBQPYpump) | 11.0% / 4.94 | +1 | BAM `R2D2im` | time-limit 1.0 s | **-0.0364** | [buy](https://solscan.io/tx/3uuDXEzhhdicSctnAwAHsNvornURrbawUriVLdxQAJZnoaY6GRKFcgnwuySGhgz4d4Ekr86r5Wy6NrpmHshkcDCw) [sell](https://solscan.io/tx/rByMrjbTjf3pxLGAScVDwosvtaECRUUh1wx4nAnGR5A8xyTRnAKQPVBa8MTEFeUexbDcQjW6ZcrrhG5z48i8wKG) [whale](https://solscan.io/tx/4KaNih4vMxesMGYcrhifchNchuNpqotXm8A6B5GJcjb3P3v4ihSkG9B7DURJpp1YcvxaqTe6h9hUeD6YiDDe2tdv) |
| 2 | 01:22:14 | [DEf5Aa](https://gmgn.ai/sol/token/DEf5Aa91iHqSV9aBHY9HFNRHT4esFHV6kHq3QGnUZhoF) | 9.1% / 6.78 | +2 | Firedancer `HW4zor` | take-profit 1.0 s | **+0.0406** | [buy](https://solscan.io/tx/4kkDqegQnpaB8Qa7sHZT3Ki5WuTKGUBoTjRbibzqoYGiyzckJkyQG4x4jwhRr89TT5KqV56EXXyxi2Ccq5zhhjyF) [sell](https://solscan.io/tx/4gtp4GHkPXF6o4qJmWs39BSBZJkJF4idrpeqybWRtoD1K3WzoSsR37Ljz9TipV3gbdDUzdeTR7ZzqZxA2esoFcEU) [whale](https://solscan.io/tx/3fxTGTrDnMwXHmbuc9U47HRXTtux6HJzoFyS3HzFHSsGpjQpvUpSEdqBCKKXYoFN6BHcaSd5xejtYvoELx7tZhhf) |
| 3 | 01:22:56 | [13JHmd](https://gmgn.ai/sol/token/13JHmd7VDVLnMdebhfyFaaMnkdN4rg4UNZdvpWnypump) | 6.1% / 6.48 | +7 | Harmonic `Ex1AxF` | take-profit 0.6 s | **+0.0324** | [buy](https://solscan.io/tx/JFguVxbpNfVikjM6Ry8wjAMuuvHaPAFfDf4REBTL5onKDyJ21NFtpg3ZAeExPxvNN52KmaudsLpLjeVTX5kP4Li) [sell](https://solscan.io/tx/4eJSSCGKzjqHnVwFawheCf9X1voKBPpB7CSzYDDy57Lip1JW15ahrdndYnqAeV1Tw8MfMQS5a2hx9trAw8J4yF4S) [whale](https://solscan.io/tx/65ucEN5nqchspQUYdiVV9k7js9jLGrqHcCo1hUwoj18394FQAGbHQ8Aw8MTDPDX42Vz1TpccvHwdV9ffkxSjGRfr) |
| 4 | 01:24:04 | [7rZvTR](https://gmgn.ai/sol/token/7rZvTRJMrHunckEYCD8zzaBN2VN8iQNeSvYjYt8pump) | 7.3% / 2.96 | +5 | Jito `Df16xM` | time-limit 0.9 s | **+0.0024** | [buy](https://solscan.io/tx/33ymCNSnribWKwgJjHhh36KYxAD3SpnemmV8vBSR7QASLXbvAht77hTLXwCeuMWwFRYotBR8MPD2QeXAEuM3FJdt) [sell](https://solscan.io/tx/3ar4G1VseG1vGKnDw7hX3FTo7WiiaETYGEakyBy7ssUsHxqHw233qHyD8YEi8y6bcqqt8ZdarGygzNdhhjncxUNJ) [whale](https://solscan.io/tx/51ojAWMwKxBfvcKpoLyoUEpX762d5m3NQmc3DK6C87CxwtLczvFYSvubZXasARJwcFkALsMAQCuqHG9SXeMxCDBf) |
| 5 | 01:24:08 | [CZwpDR](https://gmgn.ai/sol/token/CZwpDRdKBEo8ESKbiBdQ4CKrJySQzZAMDBUzzjDspump) | 6.5% / 3.22 | +3 | BAM `gVALrR` | time-limit 0.9 s | **+0.0108** | [buy](https://solscan.io/tx/2Bh3mUW63Wk63DSY9iiGBna2Xbpm7Gnh3y93rbHfomo1kskm4bjPhZ9Sb1ix5P6gCEV6FyriH1ZakLLdM8sEz6f4) [sell](https://solscan.io/tx/2d1xQcVE1ZAfjAxLcmDUyGoHHHSDYC6jud7xxP5DSvhtqZXFik1q8YrVKv7SNjzk1whoE3yWLqbqQ8p4wG5kwUbc) [whale](https://solscan.io/tx/5WkCs65q4N51GtBktsdQbgkxBrPJNcF8hmpYyL2WcbHny654n91TMD9nJMtb15TVGRNXiCQph6GSb8fz4XwGf1e7) |
| 6 | 01:24:59 | [CeXgon](https://gmgn.ai/sol/token/CeXgonvoZxEi9Rgpm8H98SHLzjApa3g42CpoHXu4pump) | 6.4% / 2.93 | +7 | BAM `9jxgos` | time-limit 0.8 s | **-0.0169** | [buy](https://solscan.io/tx/5EcnEY9kJeef5SbwGE6uefXfzQoEjFnAA5WuWyUwhHMeHewBKivv6gkAVMnvth1hFu3mUUcda8GUZXnZJ24c4b5N) [sell](https://solscan.io/tx/RUzo4mGsFEQY1HB9tQoqu3g2TJ9At8Lc9Mxy2851VbWd3A3voivsPxRpYPyqzemgkDyQJqj68AuMQXtkbixd7so) [whale](https://solscan.io/tx/2CSZHZFRnZmeVRwtBNw28QGzpAc8AMUQBduTeCq2a3QtcTEKfi8UqdAm8QLncGNTXWC1gAVBJgwF42e4hGmMh8rw) |
| 7 | 01:26:00 | [AZzY84](https://gmgn.ai/sol/token/AZzY842pJAQdrvujwiRxMFKkabeyo6Pu2SJAVCWmpump) | 6.5% / 4.44 | +3 | BAM `3JotfS` | time-limit 0.9 s | **+0.0213** | [buy](https://solscan.io/tx/mtiWNFwScsdbVCar1vu1F8WTHHNRA1Hdrs7pSKpyZLsLJihaZQocuP5wPvkvrRXbM9JQsbwmc86Yzsdz3SCo5m7) [sell](https://solscan.io/tx/4Pk9QaaGTxV2KS5NQiQQjHrtUWXZkKDnVE2KMyhVMmUbLFRvAnAMrSPZoZdk1EG2mTXPranppZbuTuG5UJG5r7F3) [whale](https://solscan.io/tx/3m4rzmvCFmmCZDdYueb4te1D8zNriHdbndbjYBhW5V4N3JwL76pMK6wQyTVJMzbabPbRgDETvTv1cbNQjuNDro5f) |
| 8 | 01:26:01 | [9dymiQ](https://gmgn.ai/sol/token/9dymiQUx3jwKftpxWM4eKcSKa5QDTPRkz2W4mQ1UGD7y) | 7.9% / 2.37 | +10 | Harmonic `SFundN` | time-limit 0.8 s | **+0.0026** | [buy](https://solscan.io/tx/zZ18gZ1WDAm3vdzUx9qzfFNXXiKc9PPUP3AqrpHCfxvW1wuRoLZ6JnmuU5k6n3M6sogn12tHRGWi5rRHEcDoFXy) [sell](https://solscan.io/tx/3Fue8FNs2cTbWtmQkvbBdj3rHcSQmQWE8Ki8wVX9ffDvAEKnwmriNpzAjRkpzxrMaSGzT2vBDtkfTRL1UAE6UcpC) [whale](https://solscan.io/tx/4Bp9EMVC9QLvUqrQLJH45vhtHjK2Jh4wME7UTAnr5wQszhnhxpc19Q2MAoW9ANs19kDcdJpo3DfGRVV1oJkdFi8a) |
| 9 | 01:26:04 | [AZzY84](https://gmgn.ai/sol/token/AZzY842pJAQdrvujwiRxMFKkabeyo6Pu2SJAVCWmpump) | 6.3% / 3.12 | +7 | BAM `sbidYi` | time-limit 0.8 s | **-0.0112** | [buy](https://solscan.io/tx/63DFsFs5hmJU3mM5AYZvZGmZPXDemAaZokTCtpa6jsKqavrsCUQNz3B8FxthJrgpJzqFjfsd7dmNYZsLaXczMkns) [sell](https://solscan.io/tx/3Xw9Qkrqbo1EYQS5smWeHNNNJM4ijMyaNMMpppGpUr5sPsGNzRoEEUMhVhrCTm7q8MqVvRUv6RD6Bv3fXhsANNJh) [whale](https://solscan.io/tx/47kGCX3wWzgHhvp2hmtVnbgB2LVgLK3WiLFUQjAgUZKdAeCXnY3ahg2SezZ1jZm1SCDSNrm7V2cwJ9bjdiZFoHa3) |
| 10 | 01:26:16 | [4FU9fv](https://gmgn.ai/sol/token/4FU9fvwgiYawd6zzU11gAtvojADpg6Tgjh9ALoxgpump) | 6.8% / 3.46 | +3 | Jito `siidBV` | time-limit 0.9 s | **-0.0061** | [buy](https://solscan.io/tx/5snuxgrQfzw2stZd2jkTooBy1nF2T43DozDjcYnVYuznszoUBHtCW8igKQFo5gdPshkS4M9wy4JHG11jUCvqfeRU) [sell](https://solscan.io/tx/5XsRUDU5SqWuEH4KAMVeVxqgPqs7tRideYea6Lf5wcS7PNoecRqJYE2hG98G6a7pAowASwMGnwHyHHdo8CZa2akp) [whale](https://solscan.io/tx/4BciRGXZrRgzjDRLErfAJEVt1oYHLQGvTs9WNsE7AWKGv5XLBkSxsoR1HJ8vAb5UmTDS7QzSoK5YR5Th5Eq3eGpR) |
| 11 | 01:26:22 | [4FU9fv](https://gmgn.ai/sol/token/4FU9fvwgiYawd6zzU11gAtvojADpg6Tgjh9ALoxgpump) | 16.8% / 19.75 | +2 | Jito `E1r4Ps` | time-limit 0.9 s | **-0.0123** | [buy](https://solscan.io/tx/3LcjfYttaGDknmNG665Gjo58DgEjdYXy1RH56WACowTC3tRkjM6czkkSEgAeSvepfmVKAymju6hLAgPULV1eKJXx) [sell](https://solscan.io/tx/2d387BEuoKNWupVgMAP4G4rp5NMvBHG3CsKRDssd3kP1WgwJhnTVWobsbfznv1xesda7s4tGoRpZJoTkUDHL4q64) [whale](https://solscan.io/tx/5h66nuHRLA1vHhB2ZRWdMNQWgr1rQAeDAdMeP1Vu4oepuMayN9CmtHUb3gRsi3s6nAsRbboMF7FwAFg4qKBRiUGj) |
| 12 | 01:26:47 | [HMLqNU](https://gmgn.ai/sol/token/HMLqNUBRTF6Z3zVsCswKSaMTWDLUgqC8WfLffRiypump) | 9.1% / 2.96 | +6 | BAM `FWwwP9` | time-limit 0.9 s | **+0.0067** | [buy](https://solscan.io/tx/3QhqftCbkGGJV8z1ZMYKFuFTNuc8EsgRsTcP2RaXBdxWD6Ae8BQi4pmLBMVVDAFHKVMs29hiwJ8ep2vZqWSABPqE) [sell](https://solscan.io/tx/21GEKG4YH8hC5UnrtfaTQYSxK6k3pZwKfZ8tHy58AApdw7fCWCtPZGhh7Ck5HvgbXgnY8tTcporyTBqrHigNTmgA) [whale](https://solscan.io/tx/3PNFHGTZC1xo4t8w6tGLGUr2PEkiFYHhXU6AEno57k3TPiVBYHe1biegzCS3Az2ZyTNR4RLMowmY6P8sjWwLZkyR) |
| 13 | 01:27:38 | [B71iz6](https://gmgn.ai/sol/token/B71iz66q9EPgV3VTDenwGnGuG3r1YcheKkHZKQ9gpump) | 7.1% / 3.46 | +3 | BAM `HLnodb` | time-limit 0.9 s | **-0.0257** | [buy](https://solscan.io/tx/5HG2qLqpo6ZCcHB1bbZPyWRc5CRD8JwJnLvAPBXiQ3CCkbiqC4meUpDm2NPFZJtgrTj621oicVWFxSS4RZtBBKie) [sell](https://solscan.io/tx/2vYRwPm34H9PeTby4bxK5az2CQrCw6FZbQSokYDqD9H7MRxKUDTF7DKc3mgR3EBxcenjRgzAMm7wxWiW687vA8iA) [whale](https://solscan.io/tx/2bKS3qZNfextyJt4YZPgsTvn7NrZKmDDpgkt1eJqyBARhaa1DweJTz3wsrS86ieZZoEDcmsUmQTp4onWj4ANJazi) |
| 14 | 01:38:55 | [FnkjEd](https://gmgn.ai/sol/token/FnkjEdN2eUcXiH5eRMtNRqwqiUNeDD6BKwEabCD1PFSC) | 7.9% / 4.44 | +9 | Jito `E1r4Ps` | stop-loss 0.6 s | **-0.1165** | [buy](https://solscan.io/tx/FAfAjqPJWx5aSc4TRB1B7GTczSpaqJ9MzqDwinsgVaPXagEsb2M1r8tSuphoyKcdKUTR9EwBf8Py9g6i8RugFBo) [sell](https://solscan.io/tx/4a3zzM9vic64rP73YmFGLdYAnhsnXzVH9vfoy4869pFZe5QPvS15jt8k5YkSzxHvibE4AEVKwLCKcUT44bk89iMk) [whale](https://solscan.io/tx/2eeHTnSHGLVpvgGMx73DetJQGVcxuVR5JBFEoTUEAcaFUfk9obDQpbt3JXSJUek8T2ARcCAq2Swpby3sBoBg2pEi) |
| 15 | 01:40:50 | [CLBvQq](https://gmgn.ai/sol/token/CLBvQqggFxobAcTP3RALsLZT1zwQHkCRzjg7o6CBpump) | 6.3% / 1.98 | +2 | Harmonic `3psxMy` | time-limit 0.9 s | **-0.0237** | [buy](https://solscan.io/tx/Rjr7hu9RcJ132BENAAbD1u6d7cFd3anTb7QdydamtCcPj6KoQDnjptSHD9Lgsx6xcoyz65ixZyG8xRfudnfXCL2) [sell](https://solscan.io/tx/4bRDY71ZCujKBCFhs35zPo4LsiMNxk56fusCcTsN2BLHuxDcdjiRAcy8nVZgR57JW3qvAQwzMwAKFQxuJuoJ6L6b) [whale](https://solscan.io/tx/4feeZ3dM9fXsHawnuqsrErcqjh6YVU7asna7hNkwqSUS95SagjfgEsLonwKHQAHmEuGY1G8wEBKRmKMwrKrFVJyL) |
| 16 | 01:42:10 | [FRwW7e](https://gmgn.ai/sol/token/FRwW7etm1e2mrvYw9q81znTJgweyEPCf5UQApdM8pump) | 13.5% / 5.93 | +5 | Jito `7cVfgA` | time-limit 1.0 s | **-0.0375** | [buy](https://solscan.io/tx/5VMF3eryT5Cy3qijVUXFUBZ5o9BpuRrXtkdpHrisXe86EmoaZYPZFkLB5fVy4TvhB8WTd4UoDbCWtBEexciLYJWn) [sell](https://solscan.io/tx/45uvxJjhhPtoke3hxbb8NgnoNNP2SupcrPqvE84Fp2yzdEDQmjS1bmYx7vPv5hm5dra5hP5z4XebftkME4WiSem2) [whale](https://solscan.io/tx/39vZmqtAxJ5WQ9sHS3D8gastSjxCvbaaaqDRW89JuLkmnrEJ9Yr4v9Sk9DV7C8eVk123uJC679ksyVu9z32aEdw2) |
| 17 | 01:43:30 | [7JBQnZ](https://gmgn.ai/sol/token/7JBQnZBBoiemEafusiF8Wgm3mb5LZfS6j65UHJDdpump) | 8.6% / 3.46 | +3 | Jito `C8Bey3` | take-profit 0.8 s | **+0.0584** | [buy](https://solscan.io/tx/2qkhQPx18CAtsDD2epioUxzSwqp66y6wqSxRdjmWDyNugqdFcck5rhBREZLbxtkoDcPxiCZpwJRko6F3vVRrKsp1) [sell](https://solscan.io/tx/57b8ZfefUWqeVZ7EGMehrPuf7tWMWYGbZp5YGaeUVECs5KUG8X4MMgaPQQZ7XyxYgU8SX2M4LEJ9BnAxX7B1TdU8) [whale](https://solscan.io/tx/2TK3NJyh3jUFRufo9e2wBo1BUzX4KgqMoo4utbKWbQGzyuTrH8M1DUAVmyk4u79r2pi6Je8XWCvPqj2wQTP3WiSm) |
| 18 | 01:45:38 | [FZDa8r](https://gmgn.ai/sol/token/FZDa8rJRc6HovftDkN7TJBW4tNcZwo8pt7A6uPHvpump) | 6.5% / 3.46 | +4 | BAM `5EhGYU` | time-limit 0.9 s | **+0.0055** | [buy](https://solscan.io/tx/3eHrb4pF55d8AqvcjMG1qk3nepSBWLcvEWeCjADDkK6GaBqFLXbSfQ5EtPgY6sSviV8zK2Je7TGkjWPmrPJB5Lsn) [sell](https://solscan.io/tx/5KjxZNZFqvwTJW7XZ8vTS2m45QWQzkUBXhyYti9bBDbadyBgdUJb5wT4bK3pVRheLFEWCh9ApRp6Mdz3aKsvcDwE) [whale](https://solscan.io/tx/2vCi6DtdX6qeoZnLBYqxo5DkHfwm2UvxjRnjxwSox2JwSxyNQdXWhaFjk3dsapsfRm1wpuN93nywikqQrF6j1mPY) |
| 19 | 01:48:42 | [BmUnqR](https://gmgn.ai/sol/token/BmUnqRhv6qrEtgYtdDGARptxuv3oCbZSh8eKNtnVpump) | 9.2% / 2.96 | +2 | Jito `C8Bey3` | time-limit 0.8 s | **-0.0286** | [buy](https://solscan.io/tx/3QxkYEcsK8ppL3B5RsWBKwPTDJ723vLUu163xknUesvLUk35KtA2QVi93yiGijvYYqQTtcjLPE3oJn982LxonvY3) [sell](https://solscan.io/tx/5ZscWMXD5vZGGwE7Dkc9fNdD97fVyWwqgWD9tqHYNt5yznhBKdXoYk2sSUTc2HzBPiAVDjh7dJ9CgAFsE2HWW7PV) [whale](https://solscan.io/tx/3xGpqdXkf6ZAm5YQnJbzihXi5TZhJtgSUL8o4NvSxesqLCXZiEuc54dUFxcGkjeU7dsVPQJmu9k6EwQXzUzZFnGx) |
| 20 | 01:49:18 | [GLwe2V](https://gmgn.ai/sol/token/GLwe2VYqwpU9VdAHZkKbT6rmkU1bJ79r8KFExKgwpump) | 8.1% / 3.25 | +3 | Harmonic `shftkx` | time-limit 0.8 s | **-0.0047** | [buy](https://solscan.io/tx/5WgVVe8Q9QT14DFXGMzKivcUSSAG43XiJTvbR1mD3NuSsgFZch1uU6wfehfAPZcVxR6LBTEKER6cSUtjGAMZv3dM) [sell](https://solscan.io/tx/44WmGn7rPZZ4mhL4DkcUgb2R3xxwAvmBZL2oEVqtuKHeGVhvW2vLXWrahveyWnaaceo1RXHDhaVnFSBJ9TNamqti) [whale](https://solscan.io/tx/47AmBvWHN4qJ7YALFfjeA8VtyHEha1TCvv6o9i8SdjKfoo44Wq4GoYUnbCjFAoEJL9k5uzdWnzSdaq1vJRC3VjFR) |
| 21 | 01:49:32 | [Ch1Tuf](https://gmgn.ai/sol/token/Ch1TufytwF1oVuLPCdkgnQvvb7z5F77sMzyx3278yeV3) | 6.5% / 5.93 | +0 | Harmonic `EJsJx7` | time-limit 0.8 s | **+0.0333** | [buy](https://solscan.io/tx/4VYL2mdhmFRJ1nKR9nvjhJpVLm2ebdWVxtF68MTw7qfUhe7nDBFAXowD4aGH4uBcgh827iEdJMyFxJ26HVbeMwSF) [sell](https://solscan.io/tx/2gWbVjV7e3g5Ueck6Axer1JhLiuvkWg1RuLExmUA2wcgPKpFP5yg1J42vs35atVbtaUouSFWQT6jLEmMSxMQPen9) [whale](https://solscan.io/tx/RTUrUwPa84WeAgUrSNauJMJ1GK6CjWs8LWrC8UvBc8Q8PyuAj5USaems8qzHVTy9cdgLdqvLrvBWB1H5ZXDZVxf) |
| 22 | 01:50:04 | [KkreKn](https://gmgn.ai/sol/token/KkreKnbofUzmzq1ZLWyKoHzt86mWwmpk6wKzBCGpump) | 10.8% / 5.93 | +3 | Harmonic `BtsmiE` | time-limit 1.0 s | **-0.0280** | [buy](https://solscan.io/tx/4BkdCciFXwhnF21ixUFJoSEyQF3wenWcamHHZaZF7z8WKizzHPA3q3V6apHiWTf1P8qVqb6qXHPMivCD3z2hTzom) [sell](https://solscan.io/tx/3ujZJXJUteMFH1KyxsgALJMbutsuQ76R8s5eVaiNY9fquGS3vBuhZMuywFe28VQxrJ81WHQVRWdd548Kw4KsoRUs) [whale](https://solscan.io/tx/5ryJFAfLpNA3pBnZhi6Nuu3pX6u6WbmZKNfxYqHeVXTnx782tbMHe3tRaD7MeE4aR6jAuLEhCanQoBS8r3xDxVV1) |
| 23 | 01:50:19 | [KkreKn](https://gmgn.ai/sol/token/KkreKnbofUzmzq1ZLWyKoHzt86mWwmpk6wKzBCGpump) | 15.0% / 6.69 | +5 | Harmonic `Fd7btg` | time-limit 0.9 s | **+0.0093** | [buy](https://solscan.io/tx/GuLLxoU7szTnEHQzo9jNrNE3ubpqef4VrTcR79Jo4xr4bbUdxC8gCYQAbZ9jGfV2wkhLVUKHdmtcFrv4Pw19xrr) [sell](https://solscan.io/tx/2pNQeGwT3nJmzogunfth2nGhRoUPUstgGJypZciXXx9z5GNWqJ8LGVw8hEEsZSshcdWmPvYYqHdLTTntgfyjQp1x) [whale](https://solscan.io/tx/4a6oj94qBwo4eJHEkLPG9TEWtZskNy2JwbKaZrFFUq28jdr7onq1Jk6EoQppQ5v76ewhtPDbBBPTrEjSi29VchLd) |
| 24 | 01:52:01 | [GoPFj3](https://gmgn.ai/sol/token/GoPFj3jgJjCEJV5myuJZ9aBZ5PtfS1wRN4iTP35Npump) | 9.2% / 2.96 | +1 | Jito `HEL1US` | time-limit 0.9 s | **-0.0228** | [buy](https://solscan.io/tx/2djb3JFDHYyFtYEWjxyi8gcgfHnMEN2DRRoS7oFRAqh86DsXSN2ZFTD73WNwXVy2fFaa5edWZjuUUbHMKF9EQ6LQ) [sell](https://solscan.io/tx/2wc1ChiXuThsKht9doH8RSMhFQaQ2UXkGjzYouUa8XPvJnGrgySuHsn2M9vgWqvmmYTR3UeLvw67mpDqbzXBqEhA) [whale](https://solscan.io/tx/3Y7sndgbgaiqc4qtBXQYBFPQ4kFsPZ95K8pFiwJsw6DHYsuSR5YzfufyDUa8AaHXP4GogNo7BBPShyXyb5c5zWNj) |
| 25 | 01:52:52 | [AMfUHm](https://gmgn.ai/sol/token/AMfUHmRaz5aFadkMtYBL6e8ZcbX9QJVGFaHPkZHfpump) | 14.2% / 5.93 | +2 | Jito `BCJN2v` | time-limit 0.9 s | **+0.0189** | [buy](https://solscan.io/tx/2CagJ6mDJCfGTMTWAXjcuD1AJrUNBFmeoAdtXbvWNfQAv3jYn8L2uEcvzAo2vckCNDf6xxWaybKoq9P9PLbrft98) [sell](https://solscan.io/tx/2dcQ4ZWpdrdR8pfi14MxwtCQpZuC2rwtytZF1dzQ9scni1i71e99Z26BXTmFLfgqo74Rvt53Bg2P8RYw1tymec4Z) [whale](https://solscan.io/tx/3mFYF9bPnnVCioVYiAXYZJSvQpnjJXsRFkfFs49CgGNg6RPqXP4eQgdV9KrLoEanpGLwzvothVuwxgKYvdaLJxLE) |
| 26 | 01:52:53 | [DCPS6i](https://gmgn.ai/sol/token/DCPS6iejoULa3aN7VDXRqJaBHAkmJhd7Jwo7way3pump) | 6.7% / 2.79 | +7 | BAM `6WgdYh` | time-limit 0.9 s | **-0.0218** | [buy](https://solscan.io/tx/3yP1CChBbW9GwRFpdd7ngfafonhTF7siR39jdJqowVEhybrBuL1tNgCKkmerU5tsJNy24jvVDdW8QWpviy3gp1GX) [sell](https://solscan.io/tx/4cDUVoFHoLLcYKH8x14Sj98mFn8tZ8uDFA1kjDgqeibV9o8iurL4VM4GazPDQpudj7JV4PegK4nJdRa19jABAvVT) [whale](https://solscan.io/tx/2r7ULdGuGzoUQJBFtipPRUYw7xBoSUFvkR6rUBfYQGuq2PYLXjjPTTSvMijT3bynf2kRedXkzoM7smHkXvjtjuii) |
| 27 | 01:53:31 | [Ge5NLK](https://gmgn.ai/sol/token/Ge5NLKPzwAja6NGtHzuqCunR9NeVUyahemWddcorpump) | 6.9% / 2.96 | +3 | Firedancer `EvnRmn` | time-limit 0.9 s | **+0.0230** | [buy](https://solscan.io/tx/3hqkF5Aa5rhwRNUoGz3bP5M9ZFrgF4tPMNaZ5D4BQ11mNRssPNkRrxtbVPYu4FwY9XXihDt27SEmNjfqGzaAs44n) [sell](https://solscan.io/tx/65pKQNpfruhDz2gNzTp77K2yqzjJ2ADjWsBjW8CxkSp5BgvxC4XcwbaW3MkuyCDKc7ApxSjS67mHe9CecaiAJqpH) [whale](https://solscan.io/tx/2SG9eTRGpf9p7majqWxex4Jg1QrbaLHtYisUK4CFr5SWyhm3yvKK8cCxJxX38F8qzXzSEkRZzGWq4bgVjS7f9yoX) |
| 28 | 01:53:39 | [GnZeBq](https://gmgn.ai/sol/token/GnZeBqAXWX9Dz7pbwKC5vbP7E5pbn265uVg9tzQwpump) | 6.3% / 2.96 | +3 | BAM `HLnodb` | time-limit 0.8 s | **+0.0011** | [buy](https://solscan.io/tx/63b9ZSZZ4EMCvwUchThL3WGkyZM7DCUdqder1T53KFqJP7MBxkiJYdydAqcZUVfpPcDtandHv6jBQwjhQaiKXEY5) [sell](https://solscan.io/tx/4hFr18F5MNWZ68uAAa4Lu7h9qgNRGFV5tHQjpFNaKZxof8GqPHeo4iaYgfG6XAunf8AXzQmBscNW8snPiqB4izjZ) [whale](https://solscan.io/tx/2Db7Stxvg1nm3aQZbwxYjUq3FbZ8mfrQJNz33ZGjTptgQcW8wV1U4fYkbCFvzyH8KgXLsssf7JudaovXShsxoaqY) |
| 29 | 01:54:32 | [Ge5NLK](https://gmgn.ai/sol/token/Ge5NLKPzwAja6NGtHzuqCunR9NeVUyahemWddcorpump) | 7.3% / 2.79 | +3 | Harmonic `5ZqveV` | time-limit 0.9 s | **-0.0118** | [buy](https://solscan.io/tx/4QCxwwVVLiY13R3FXV7Ub4xqJ3Xspsqmoen7sRPymLQuemCy2STmHbTPsdZbU7ve2EzdKAFriTXwo5wuSr7KZ4ED) [sell](https://solscan.io/tx/2p9x5juvqkW89XgcheyFLv4KXdwtaR6q5DVVeaKpuhM5ZeaFDgy5cfFVseDH2awpvxMsQsACnvsfj78ayAknczMN) [whale](https://solscan.io/tx/DHbSLYtKHinLEFzg1h4vUBZZufPBbL4TWCGVTrvcUAAqdccaQr39wQs6wW8HtaMfLQK8p8oXtixJe5P1TppkYzx) |
| 30 | 01:55:30 | [GNbxhM](https://gmgn.ai/sol/token/GNbxhMvGwWV3u8E3EnMc6bgBF1gkYQ7AvV7TRBiRpump) | 7.0% / 2.96 | +2 | Harmonic `pSo1KZ` | take-profit 0.5 s | **+0.0270** | [buy](https://solscan.io/tx/2TGQsDT8jsSGhejo213AwqFrPEbXpcfBA6N2pQ4DPBm4K3Sm3kKbEvgyYJAsAnoRPuq7eErgvoWFvcJzEKdBkRX4) [sell](https://solscan.io/tx/3P7gfj4d8E2YT3MQhESrYX4itNbom9mLqmY8z98Zs2EcbMKKsu3dviKVF8tm4wYjvpANSYLA74QviTbN2uG6Npuk) [whale](https://solscan.io/tx/4k2FKnhHRprau66YLAm9zZ4HqKjvSbrXQA7by9hxUDF1taaGZYGbEWqRfjhoAp3BUHDv6FXERa7Rz7JTYJA4hf9E) |
| 31 | 01:55:43 | [8gWSGn](https://gmgn.ai/sol/token/8gWSGnA6pNnnWMgeRK5Xmqy4hYrXovaDDzkiPa6Zpump) | 9.2% / 2.96 | +1 | Jito `E1r4Ps` | time-limit 0.8 s | **-0.0228** | [buy](https://solscan.io/tx/2xZYAwZpcuM6bfqk8yckHnmWrDcHM6jTiLkWjAiWPkitcpB72R4d2q5WjumnxeQpHMwN5v8q4wMRqKqGuxq9TV8s) [sell](https://solscan.io/tx/ygUwxJj4MSCGKSuSQdeS5dvdbgy7TbnkDauxKGp9S1Y1ozTqomaPLoNb62EiWgcf9gqtq81XmZcte7T4adWFM5B) [whale](https://solscan.io/tx/Fm371Uerm989nCYqWD3r1mwVturbyij3BMYEc87bJHnaQvSpyB4CPEVLrKS6MHk5t57nGxp3foKGwJJ5vGhSSGS) |
| 32 | 01:57:24 | [CSsmSN](https://gmgn.ai/sol/token/CSsmSNoHjzLUhgRE2zybGQSHSYANH7KY8vgUycyGpump) | 45.4% / 29.63 | +7 | BAM `5pZvwj` | time-limit 1.3 s | **-0.0425** | [buy](https://solscan.io/tx/4oRxwPYChRPtAbKrHy6kCXz78oveNyAJaNm6qK8CWPMgfkN8CBi3p1s8qXoKBy9ikouGMUS42EGLMRZMFiYF4BWF) [sell](https://solscan.io/tx/5afeLpnvRdxAnS5cQL7VcvxohShNaMs3MS6BFCGe4QJitrXGuDqQx7bnT9m9KQb2PkjKfRqA2fceL98zEBVhUzk7) [whale](https://solscan.io/tx/37SZNKmUPNhZx7QGo3GAGuDPTJuhz9M6hWZmf38MtD9cCMg6GZcpJJ8uBBdtjPhq22FbwJKe13PbEefHhYZWANX) |
| 33 | 01:57:58 | [GrEdcy](https://gmgn.ai/sol/token/GrEdcyVQRvfNyxXW1ppsJhXVSEWjJQcD9wQariycpump) | 11.9% / 3.95 | +1 | Harmonic `FBKFWa` | time-limit 0.8 s | **-0.0220** | [buy](https://solscan.io/tx/49pKrHYqUzYo1XWNJNq6nE7yaq8bWkKiuo6JoJX47oPi67ob2EF4DtyextZJniR37xJxWYUWEwiAQgwNGNYHrJg8) [sell](https://solscan.io/tx/5icvjQaaeEAbogoQwtpCRm3kNcwSqf2Cx7h1X89wps7TyDJ56qcU8HMrNjPYTPLtzqAstivKRtqXtA524QfBawWP) [whale](https://solscan.io/tx/39Fjgrqd1NZUe8hfhkxP5Dq5GQ9hAL2a6GZYRc8etL7DxGRvxEEozUNSz6Ctk6krqMyJYk3v6PzicMaP93LUzKLx) |
| 34 | 02:00:14 | [JBX3aq](https://gmgn.ai/sol/token/JBX3aqVZ4eKEJJtWT9rkMymDJkkSUDzqVskUD65opump) | 6.2% / 2.81 | +2 | BAM `jzDsim` | take-profit 0.9 s | **+0.0377** | [buy](https://solscan.io/tx/d9rx5rs9iCGKyqpBHwYBvYropPxapZXPXwf5tyEDWzYuKQt1A42ctbZJ3Xmg6Cj3qjPgzY6NgA8iSNuKwmV2w3D) [sell](https://solscan.io/tx/3zcYUN7WsQYdpcXf7fqqN834D9ASaiQNcrGdWCMqsfwfe2NPmZSoWsMrmm8fGDbWmp935UyTPtag4NUUYZru77bj) [whale](https://solscan.io/tx/3ZUmQnYj3cj5XzKSQAi9DZKw1qLcfeJASHuVMkYpsdUyFYCo2ZD7RFm6BrLkr8FMWgRbU4iwjk2E2Z6UmJ5LnaBh) |

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 3356 |
| Inside the envelope (age / drop / since-buy / size) | 1475 |
| Picks (score above the threshold) | 56 |
| Skipped | far_leader 39, spacing 7, presend_armed 2 |
| Buys sent | 8 |
| Filled | 3 |
| Failed on the +5% guard | 4 |
| Failed (other) | 1 |
| Never landed | 0 |
| Sold (positions closed) | 3 of 3 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 01:24:04 | [3KugMf](https://gmgn.ai/sol/token/3KugMfTzysnKsM25peAewNuXKSP8VUFJBBpNu3PLpump) | 0.45 | -0.68 | 3.51 / −14% | 9.8 s | Harmonic `8vk6Qp` | guard fail | -0.0005 |
| 2 | 01:24:12 | [CZwpDR](https://gmgn.ai/sol/token/CZwpDRdKBEo8ESKbiBdQ4CKrJySQzZAMDBUzzjDspump) | 0.45 | -0.06 | 2.38 / −11% | 5.7 s | Harmonic `A1vqhA` | failed | -0.0005 |
| 3 | 01:24:53 | [59uDru](https://gmgn.ai/sol/token/59uDruJCf5D6X3VBzWy4xe9rZYhtwscHNuFyd4yD6dGf) | 0.45 | -1.61 | 1.21 / −7% | 8.5 s | BAM `22rU5y` | filled | **-0.0261** |
| 4 | 01:25:20 | [8NYB87](https://gmgn.ai/sol/token/8NYB87Sdmm7rCiQdqqhsYiTuMzZnz6sk5FN2TDY8pump) | 0.45 | -1.63 | 1.15 / −7% | 10.8 s | Jito `5pPRHn` | filled | **-0.0422** |
| 5 | 01:26:05 | [AZzY84](https://gmgn.ai/sol/token/AZzY842pJAQdrvujwiRxMFKkabeyo6Pu2SJAVCWmpump) | 0.45 | -0.38 | 2.52 / −13% | 8.7 s | BAM `AWcCdY` | guard fail | -0.0005 |
| 6 | 01:49:41 | [Ch1Tuf](https://gmgn.ai/sol/token/Ch1TufytwF1oVuLPCdkgnQvvb7z5F77sMzyx3278yeV3) | 0.45 dev | 0.90 | 6.20 / −26% | 17.2 s | Harmonic `2m1A2W` | guard fail | -0.0005 |
| 7 | 01:53:33 | [7zzoiG](https://gmgn.ai/sol/token/7zzoiGYeiN4joytd9sY9chEUc5G1bPjNTgVi5w4e8Hrd) | 0.45 dev | 0.85 | 7.63 / −35% | 6.6 s | Jito `4MKi9P` | filled | **-0.0052** |
| 8 | 02:00:45 | [3Xri9B](https://gmgn.ai/sol/token/3Xri9B9zK1xf77iKK6CUiwYM3wtrH7xHN8VMEVvkpump) | 0.45 | -1.57 | 2.40 / −10% | 10.2 s | Harmonic `HTeRsa` | guard fail | -0.0005 |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 64 | same | 3 | **falcon+falcon-udp** of falcon-udp+landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/2deS6LNbquE8Ec11QoNPyrgZbRfDxM48Sf71srrxfM6JCeeKcLr7Mn4hrQC2acajAP4GXYu49pikrxBJCYrAhqtJ) [dump](https://solscan.io/tx/2MJ9Vb6aMHAkwo6xsWrebwq2c3YXzPawnkpawiXf44so4NQ1ZppAXVTzj1MBeApC35KKsoxET9UCCwR1rQ3jUnnm) |
| 2 | 513 | +3 | 2 | **nozomi** of falcon-udp+landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/3C8WEeakLQvQZ41mFyPZxNovnwppAV7ADKHWdJy62E87GxnRg4pT4ynTAXErcUkuESyrhmRtVXgkUBSw4CtshXB9) [dump](https://solscan.io/tx/641sFYABoTbwszDtmGhUumwtQ5WoExwbiMb6okERDFHQeRM9jxqUy6mavDZjSVXdrhhdJMTTtMB4Bb2p665Lhfuw) |
| 3 | 33 | +1 | 0 | **nozomi** of falcon-udp+nozomi+helius-swqos+bolt+falcon | time-limit 2.1 s | 1 | [buy](https://solscan.io/tx/3BmXBgHYLzEV6e3XoivJE2SndcA35cycgPTMapFUtMDkXWYaZjSM1QVV9F9BgZiqDvgqrBLXo3UuMckrKfYVGfy6) [sell](https://solscan.io/tx/oYzkLkQBZtLfnc5L6cFcMqynoS5PTrhWXHXgRc5LC1km9QyzPrkFi3wLJ7bu7EBHd5rA5JN4YZ5VChBALQkNhSc) [dump](https://solscan.io/tx/4wKNRmZy3mAtdjh3NQKmTS1M6pHzrXxfVcLup75K3n9QWmee6nv7mBaPbJ2SDidWhJYRdxfG36wxdhQux3qrFvi6) |
| 4 | 115 | same | 4 | **falcon+falcon-udp** of falcon-udp+falcon+helius-swqos+helius | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/pt54x39AEcqzictsreCxmYcSAFBg6VDpGvkeSWkyqJwmxoKpmMpK7F3JEj8UHGLB2trdkhQs1qkgQbRjhfW8LMp) [sell](https://solscan.io/tx/aZnmoG7WSTW4pQ33q5kc5U1ain7cKyikdw3kS1iFnVwYaPNh8XN48sX81q2BYnTz6PivAu4LhLGmeSTmMcMGxX4) [dump](https://solscan.io/tx/3gEbZFTsSpwzpGhxhVkruEsefEnppTnqZfCPqzQV83bQLeF3KRQjkRgT93xZ9tpDkQ63gS9qH6nkMSpRxPfvZCLY) |
| 5 | 41 | same | 5 | **helius-swqos** of falcon-udp+nozomi+helius-swqos+bolt+falcon | – | – | [buy](https://solscan.io/tx/5A6zt6nHoKoQ4EVk91rC6yGZZ563XqPc289YycQM4kp62KV7KnhtSFGA89oWLkTPVRRyDsBGm2vcecpb66Ftos1T) [dump](https://solscan.io/tx/vqAXb4vag29zFKzuZ4UccRZwwcc5L4phYLgSFR9XXxYh965sYqsmxsM8FoWS6u24nAnSNobn1u2T6YdM8cYt4Tt) |
| 6 | 55 | +1 | 9 | **falcon+falcon-udp** of falcon-udp+landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/2atz2Vu2biioTSQzA2X9TTAvBbgogVo9JzqgKkrbKVx6tGXaWgr3QW7m1x865EHsP1g26y2G88ou77qxM1Mi18un) [dump](https://solscan.io/tx/ooGGpP26KFTSctpBZ9f1aYCqJrS3S1uV2dqLiRSKntctpj1qzUKmevWrDZzNJJm3RoFATixydMdYQ26rww5bYnc) |
| 7 | 110 | +1 | 1 | **nozomi** of falcon-udp+landx-fra3+falcon+helius-swqos+helius+nozomi | time-limit 1.5 s | 1 | [buy](https://solscan.io/tx/2jbg6mknV5Jkyqnd7isTf8rPKx7NN9TL1mY71vaoLpBmH5a8inXUDFvUUeMfpBUmeFZyho63RPwZK8bnKjPbX7cm) [sell](https://solscan.io/tx/3UvPyrhTmanFyRDbfQfyp84wdvseqWvbrY8mVUZzpt1wL4ktj77ku3krXryDSPVPgjLzSVmhW8ykRqEQi89L3h3v) [dump](https://solscan.io/tx/2BNCQZuVYWhDUhuwkoDivoAPSVyReQbm19AYdQ2DJVRyqdeMscRZwQQpue8ZXC2VgWeT4jNgrqMFqJiY1qGtGcUQ) |
| 8 | 14 | same | 1 | **falcon+falcon-udp** of falcon-udp+landx-fra3+nozomi+falcon | – | – | [buy](https://solscan.io/tx/4GHiDdAfo2dLiDYZW22wsWMeM1K2SzkKanQX9R9pbUf9uCeBS26HWfCX41Y8kBaQeM4r3fJmB9TLNwRm6xZmf8YS) [dump](https://solscan.io/tx/5stezqr7isHfqRxLjZuHPxTXRE7noLdtqotdwqDHZeER5uFhrJDaVSYXU6NP2cZ6FYT9vCPyutiNuS4qjgCy5CHW) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Harmonic | 4 | 0 | 0% | -0.0020 | – | 0/0 |
| BAM | 2 | 1 | 50% | -0.0266 | -0.0261 | 0/1 |
| Jito | 2 | 2 | 100% | -0.0474 | -0.0237 | 0/2 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 6 | 2 | 33% | -0.0704 | -0.0342 | 0/2 |
| dev list | 2 | 1 | 50% | -0.0057 | -0.0052 | 0/1 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 4 | 1 | 25% | -0.0437 | -0.0422 | 0/1 |
| next block | 3 | 2 | 67% | -0.0318 | -0.0156 | 0/2 |
| 2+ blocks | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 01:00 | 7 | 3 | 43% | -0.0755 | -0.0245 | 0/3 |
| 02:00 | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 3 | -0.0735 | -0.0245 | 1.5 s |

## 8. P&L leaders
**Best trades:** 7zzoiG -0.0052 (Jito, time-limit, score 0.85); 59uDru -0.0261 (BAM, time-limit, score -1.61); 8NYB87 -0.0422 (Jito, time-limit, score -1.63)

**Worst trades:** 8NYB87 -0.0422 (Jito, time-limit, score -1.63); 59uDru -0.0261 (BAM, time-limit, score -1.61); 7zzoiG -0.0052 (Jito, time-limit, score 0.85)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `8vk6QpG9` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `A1vqhA2f` | HarmonicAgave | 1 | 0 | -0.0005 |
| `AWcCdYG7` | AgaveBam | 1 | 0 | -0.0005 |
| `2m1A2WM1` | HarmonicAgave | 1 | 0 | -0.0005 |
| `HTeRsa3g` | HarmonicAgave | 1 | 0 | -0.0005 |
| `4MKi9PLR` | JitoLabs | 1 | 1 | -0.0052 |
| `22rU5yUm` | AgaveBam | 1 | 1 | -0.0261 |
| `5pPRHnie` | JitoLabs | 1 | 1 | -0.0422 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1339 (p25 1254, p75 1364, n 8) |
| Executed-feed lag behind first sighting, ms | 1.0 (p25 0.3, p75 2.0, n 8) |
| Buy sent → our tx seen on the feed, ms | 56.0 (p25 36.1, p75 107.4, n 8) |
| Fills: our buy seen on the feed after the dump, ms | 110 (p25 33, p75 115, n 3) |
| Guard fails: our failed buy seen after the dump, ms | 48 (p25 41, p75 55, n 4) |
| Fills in the dump's own block | 1 of 3 |
| Guard fails in the dump's own block | 3 of 4 |

**Which copy landed (nonce fan-out):** falcon+falcon-udp 4, nozomi 3, helius-swqos 1

**Send-path answers (FAST-ACK lines):** falcon 8 (median ack 0.4 ms), nozomi 7 (median ack 0.7 ms), helius-swqos 4 (median ack 0.7 ms), bolt 2 (median ack 1.5 ms), helius 2 (median ack 0.5 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 1 |
| Guard fails: rival buys ahead (median) | 4 |
| Guard fails: rival SOL ahead (median) | 2.57 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 8PgC4ngp | 3 | 1 |
| HLU8QbLd (41Pr family) | 3 | 3 |
| 8yYMhuYo | 2 | 1 |
| GEMPyqU1 | 2 | 1 |
| 7PedQZmc (untipped fast) | 1 | 1 |
| DNS3xPtH | 1 | 0 |
| 3MHgGwdL | 1 | 0 |
| DF7eRXHn | 1 | 1 |
| 5yNBPneF | 1 | 1 |
| 5PuQCemC | 1 | 1 |
| AUih1Qc6 | 1 | 1 |
| 43TuXbZU | 1 | 1 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | -0.0306 |
| Pump fee on buys | 0.0167 (0.0056 per fill) |
| Pump fee on sells (residual) | 0.0163 (0.0054 per fill) |
| Buy tx fees (base + priority) | 0.0015 (0.00051 per fill) |
| Buy tips | 0.0030 (0.0010 per fill) |
| Sell tx fees | 0.0018 (0.00060 per fill) |
| Sell tips | 0.0036 (0.0012 per fill) |
| Failed buys (tx fees) | 0.0025 (5 buys) |
| **Result** | **-0.2494** |

Buy compute used (fills): median 73,904 CU, max 81,403 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 32 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ℹ️ Harmonic bundle auth FAILED (public sendBundle used)
- ⚠️ CZwpDR: landed 3 blocks after the dump
- ⚠️ big pre-send loss FnkjEd -0.1165 (stop-loss, Jito)
- ℹ️ wallet change -0.2497 vs trades -0.2494: gap -0.0004 SOL — about the fees of the 79 pre-send tries never seen on our feed (up to 0.0004 SOL if they all landed and failed; inferred)
- ⚠️ Self-competition: 34 of 34 pre-send fills came while Frankfurt pre-sent too; almost all were the same dump in the same block. Combined live pre-send after the overlap: −0.28 SOL on 68 fills vs paper +0.14 per server.

Checks passed: every reactive fill was sold; every pre-send fill was closed by a sell; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Recommended / open:**

- Restart Amsterdam with --presend (shadow only), no --presend-live.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_ams_r20.jsonl`, log `.log` on cyber-dock (84.32.104.202) (local copy `/home/moiz/sniper-data/runs/ams/runs/dip_ams_r20.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Pre-send (section 4b): the jsonl presend_live_* records (fills, closes, REALIZED, account closes, stops, end checks) and presend_attempt_land (try results, failed-try fees); the log's PRESEND LIVE lines when a run has no such records.
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

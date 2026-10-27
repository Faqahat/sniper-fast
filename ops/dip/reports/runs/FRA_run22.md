# Frankfurt run 22 — dip bot run report

*Live 1 h: routes v12 (soyas, solami, glaive, falcon, falcon-udp) + M2 gate + live pre-send 0.40 (k 4) on dip18; 0.40 SOL*

> **Verdict:** Kill switch after 30 min, caused by the pre-send merged-fill bug: the wallet fell −0.561 (2.5697 → 2.0085). Window w51 on 6ESztPpq: try A filled in slot …576 and stop-lossed in the same slot (its sell closed the token account); try B landed in …577, bought again (0.395 SOL) and was logged 'FILL MERGED' into the closed position, so it was never sold and realized booked −0.084 while the curve said −0.468. The kill switch (balance-based, held tokens not counted) saw −0.561 and stopped the run at 02:48:50. The tokens were sold by hand afterwards (wallet 2.0085 → 2.3385, +0.330 incl. account rent; budget file) → the real run result ≈ −0.231. Pre-send otherwise: 22 fills in 21 positions, realized −0.151, failed-try fees −0.006; reactive: 4 buys, 3 fills, −0.002.

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.1593 SOL** (wallet 2.5697 → 2.0085, Δ -0.5612) |
| Started (PKT) | 2026-10-26 02:18:38 |
| Ended (PKT) | 2026-10-26 02:48:50 — kill switch (run loss cap reached) |
| Ran for | 0 h 30 min of 60 min planned |
| First / last buy (PKT) | 02:24:55 / 02:47:16 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 4 → **3 filled**, 0 failed on the +5% guard, 1 failed (other) |
| Fill rate | 75% |
| Wins / losses (fills) | 2 / 1 (win rate 67%) |
| Per filled buy | avg -0.0005, median +0.0061 SOL |
| Fills only / failed buys only | -0.0014 / -0.0005 SOL |
| Reactive bot / pre-send live | -0.0019 / -0.1573 SOL (pre-send: 22 fills, realized -0.1509, failed-attempt fees -0.0064, 8 wins; see section 4b) |
| Best / worst trade | 9y9ktW +0.0429 / DTwks6 -0.0504 |
| Fill landing | median 55 ms after the dump (seen on our feed); 1 of 3 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip18 (QUIC lanes soyas / solami + falcon-udp) |
| model / tier | IMIT1 wider (score >= 0.2109) |
| size (normal) | 0.40 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.40 SOL |
| exit | take-profit off / stop-loss −50% / time limit 5 slots (~1.1 s) |
| price guard | +5% over the post-dump price (pump error 6042 if exceeded); slot deadline = dump slot + 1 |
| buy fee (priority) | 5M µL/CU × 100k CU limit = 0.0005 SOL per landed buy tx |
| sell fee | 5M µL/CU × 120k CU limit (0.0006 SOL per landed sell tx) |
| route: agave leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: bam leaders | nozomi + helius-swqos + bolt + falcon + falcon-udp + soyas + solami |
| route: default leaders | nozomi + helius-swqos + bolt + staked-rpc |
| route: fd leaders | nozomi + landx-fra3 + staked-rpc + soyas + solami |
| route: harmonic leaders | nozomi + landx-fra3 + falcon + falcon-udp + glaive + soyas + solami |
| route: jito leaders | solami + soyas + glaive + falcon + falcon-udp + helius-swqos |
| route: other leaders | nozomi + helius-swqos + bolt + staked-rpc |
| sell path | staked-rpc (retry also via nozomi) |
| near-leader gate | 198 leaders (buys only when the dump's leader is on the near list) |
| pre-send | LIVE: whale >= 6%, 4 tries/slot, 0.400 SOL, limit x0.88, route helius-ps, caps 100 fills / 0.1000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| durable-nonce fan-out | ON, 8 nonce accounts (one copy per path, one tip each) |
| backup RPC | CK_STANDBY_URL |
| holder-reward tokens | allowed |
| limits | max 60 fills, 1 open at a time, 60 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 21**:

| Setting | FRA run 21 | FRA run 22 |
|---|---|---|
| engine build | dip18 (dip17 + Falcon native UDP lane) | dip18 (QUIC lanes soyas / solami + falcon-udp) |
| size (normal) | 0.35 SOL | 0.40 SOL |
| dev list | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.35 SOL | 1 dev (bwamJzzt): tier wider (score >= 0.2109), size 0.40 SOL |
| route: bam leaders | nozomi + helius-swqos + bolt + falcon + falcon-udp | nozomi + helius-swqos + bolt + falcon + falcon-udp + soyas + solami |
| route: fd leaders | nozomi + landx-fra3 + staked-rpc | nozomi + landx-fra3 + staked-rpc + soyas + solami |
| route: harmonic leaders | nozomi + falcon + falcon-udp + landx-fra3 | nozomi + landx-fra3 + falcon + falcon-udp + glaive + soyas + solami |
| route: jito leaders | falcon + falcon-udp + helius-swqos + helius | solami + soyas + glaive + falcon + falcon-udp + helius-swqos |
| pre-send | LIVE: whale >= 6%, 4 tries/slot, 0.350 SOL, limit x0.88, route helius-ps, caps 100 fills / 0.1000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% | LIVE: whale >= 6%, 4 tries/slot, 0.400 SOL, limit x0.88, route helius-ps, caps 100 fills / 0.1000 SOL failed-try fees, exit 2 slots / TP +10% / SL -20% |
| limits | max 60 fills, 1 open at a time, 240 min, loss cap 0.500 SOL | max 60 fills, 1 open at a time, 60 min, loss cap 0.500 SOL |

- Routes v11 → v12: soyas + solami (QUIC) and glaive added; Jito leaders = solami + soyas + glaive + falcon + falcon-udp + helius-swqos.
- Owner skipped the planned probes ('run both live with new dip senders, we will test live'): 1 h each, pre-send on Frankfurt, reactive only on Amsterdam (run 21).

## 4. Timeline (PKT)
- **02:18:38** engine start #1 (session with 4 buys)
- **02:28:08** big loss: DTwks6 -0.0504 SOL (time-limit)
- **02:48:50** engine end #1: run end

## 4b. Pre-send live (pre-placed buys) — separate from the reactive bot
Buys pre-sent after a big whale buy, before any dump. **Not included in sections 5–11**, which cover only the reactive dip bot. Realized = the engine's PRESEND LIVE REALIZED records (chain txs of each buy and sell; the buy pays the token-account rent). Rent back = that rent returned when the engine closed each pre-send account after the exit (dip19+; before dip19 the sell closed it and the refund sat inside realized). Failed tries = fees of tries that landed and failed (6042 price, deadline, …). Net = realized + rent back − failed tries.

| Session | Started | Size / fill cap / fee cap | Tries sent | Fills | Wins | Realized | Rent back | Failed tries | Net | Stopped |
|---|---|---|---|---|---|---|---|---|---|---|
| #1 | 10-26 02:18 | 0.40 / 100 / 0.10 | 1,326 | 22 | 8 | -0.1509 | +0.0000 | -0.0064 | **-0.1573** | run_stopping |

**Try results (as seen on our feed):** 6042 1,125, deadline 98, unseen 50, ata_exists 30, ok 22.

Tries never seen on our feed: 50. If they landed and failed they cost up to 0.0003 SOL in fees that are **not** in the failed-try total above (5,120 lamports each; inferred, the engine does not see them).

**By exit reason:**

| Exit | Fills | Wins | Realized SOL | Per fill | Median hold |
|---|---|---|---|---|---|
| time-limit | 15 | 5 | -0.0650 | -0.0043 | 0.9 s |
| stop-loss | 3 | 0 | -0.2778 | -0.0926 | 0.5 s |
| take-profit | 3 | 3 | +0.1919 | +0.0640 | 0.6 s |

**By leader type (the slot leader where the fill landed):**

| Leader type | Fills | Wins | Realized SOL | Per fill |
|---|---|---|---|---|
| BAM | 9 | 4 | -0.0250 | -0.0028 |
| Harmonic | 6 | 2 | +0.0326 | +0.0054 |
| Jito | 5 | 2 | -0.0557 | -0.0111 |
| Firedancer | 1 | 0 | -0.1027 | -0.1027 |

**Best pre-send fills:** DiWbWoTD +0.0690 (Harmonic, take-profit); HZN3x4o3 +0.0674 (BAM, take-profit); BQfuALZv +0.0555 (Jito, take-profit)

**Worst pre-send fills:** GRcpcww8 -0.1027 (Firedancer, stop-loss); GnJfMgsX -0.0909 (Jito, stop-loss); 6ESztPpq -0.0842 (BAM, stop-loss)

**End-of-run checks:**

- session #1: no END CHECK line in the log (engine before dip19)
- session #1: 22 fills but 21 closed positions (a fill merged or left open — check the wallet)
- session #1: merged fills 1, late fills 0

**Every pre-send fill** (time = fill; whale = the trigger buy; P&L = realized, rent back not included):

| # | Time | Token | Whale % / SOL | Slots after whale | Leader | Exit | P&L SOL | Links |
|---|---|---|---|---|---|---|---|---|
| 1 | 02:20:37 | [GRcpcw](https://gmgn.ai/sol/token/GRcpcww8dSKosNDX2F7am7bYQs9knTAZxtj2W2fT1AR4) | 13.1% / 4.94 | +9 | Firedancer `EvnRmn` | stop-loss 0.7 s | **-0.1027** | [buy](https://solscan.io/tx/4S95GMdnM8VT9SVLrVh83LSgbmjZpaMybza4YWUvrhwBcKhdNMGCSBcExDLSr1o9yiL6bDpXLdowzAAP1vCfpvMy) [sell](https://solscan.io/tx/53MtrxUHjt9cmuv95quMobzxWJreZyNnwSEgFATph9jgsQ2ZdbJYRUSb3HDZAzEaBVw7GKwCPMsLJ2XtB9iTqJgK) [whale](https://solscan.io/tx/eQabdXiydBtEaNiaL5J5rtBvtRkUKBAVhRP9oiptFE7EN4ihDqDSm3iJMt5Q4kqa2nsb2GURZhbobEPL9BiumLa) |
| 2 | 02:20:48 | [Bbr9zn](https://gmgn.ai/sol/token/Bbr9znGZWEJtkfz93HghudLgmvGgUMQGGFjok2Drpump) | 6.8% / 2.96 | +5 | Jito `9rkJMA` | time-limit 1.1 s | **-0.0235** | [buy](https://solscan.io/tx/5J4oz2pF2n4zduxyvipwyoWwpy9XqenH1eXMubQ3iDhymrwZKDsjouUxmymqFJeutsVQ5EtKYK68dfr3KHp3B52f) [sell](https://solscan.io/tx/4PpdRjokcyDU3E43E5uVrVYvzQDfc5kLpKw6UcUhNrUTcbY31L8eGZNUzrUvqAmA37q7bTGXwdmfKaxuZfBKqt7S) [whale](https://solscan.io/tx/4TGLcBQRNbKgvt2bdX4oUq8naFxaqfT2sEq4AFuE1CPxRLJYp7CtVKFpMYaNy7LogFeDgsTrCe73Jr2zDcKrrsKt) |
| 3 | 02:21:38 | [HXALag](https://gmgn.ai/sol/token/HXALaghZFri27rdBFVv4Gnyx8b31aLUzeRcB7a66pump) | 6.3% / 3.95 | +2 | BAM `HSDTxf` | time-limit 0.9 s | **+0.0117** | [buy](https://solscan.io/tx/37t3rcGXfthvbFKfc4UznTFFTZr9NyTiy2WNo9AxD6wdS4jCGUESJxiwnm4yxmnPE5UMAi12UoXUVU7NrjTPcFuo) [sell](https://solscan.io/tx/5ihiSDzQhK7cXzpjLyaJXgo6nHyVX3qwyqy915rPSXTmE3fNAvkNsCUrKzRpEeuiuymc1xsRCG7nGBvmQfyBAjhA) [whale](https://solscan.io/tx/3fa1SC9LfhFt4FMfQbra24p6CDqqJowC2rj3mujd4ynbMTgTkmgHji1sd1avj6Cjqq9Kv2j5guNMx9FVzc3sNrKe) |
| 4 | 02:22:20 | [4gucDN](https://gmgn.ai/sol/token/4gucDNbFAatN1Uwtb6hvUqhoh2PMGn6jogdK54afVWoU) | 7.2% / 2.96 | +6 | BAM `FyrwfM` | time-limit 0.8 s | **-0.0065** | [buy](https://solscan.io/tx/4bWPVNt9eXrEB4yBpMbiSH7AbEq4fteMCLd7Nm2WrjQ3Rgy54U7VFPFns7GULPHGf3avF8dLM599chRt8ENoTgSR) [sell](https://solscan.io/tx/3HpRexGY8d7FXcuBF2FHVkR5ZFeGwo5cokG8YDpGq25JxWeH7cHrQ4hVf7DZWZ1GQY6Az5DBgQWsd7qYw691KPke) [whale](https://solscan.io/tx/72Yumbqg7nBpwpi8EJ4Fam5W6KDXHn9psBZEyEGjuu4iLsKdrkseFKRiFs7VvhbuYkbnsiSyKbohW5ruZS5E95W) |
| 5 | 02:22:43 | [GnJfMg](https://gmgn.ai/sol/token/GnJfMgsXe4FVStgzxkPfNdC6pH5Fx1zdGLhJ691hpump) | 7.4% / 7.90 | +1 | Jito `A9mvuk` | stop-loss 0.4 s | **-0.0909** | [buy](https://solscan.io/tx/4QeXZdDs4wz4iP9oGniWrVM3xmS6xYqHu9Szr4dkdyFnRMaomi2mQ5ybaoLQCUoyVyhEBK1vqi9R1sszZ6Z4guUF) [sell](https://solscan.io/tx/XtQhoyYwTnSAEVQmz8ZN2ekdjQJ5k7cFPfkwyzLis9YtiG2DPko8ug7R5NnejneZ4hmo8HPBNEVRoAWMY8ZuMTR) [whale](https://solscan.io/tx/3C5DrypapJxSkYpQ94PErR2Rbv3DriptLnqVrPZZZod4WhFqRtkU1AYdVH9UxJ48mCuUcwoSQVk1UDEAxfQ624N9) |
| 6 | 02:23:05 | [3veVqA](https://gmgn.ai/sol/token/3veVqAPrVtRTpFMxn2Srg5XrWdzsZwkceFErBoz3pump) | 6.3% / 1.98 | +4 | BAM `2mDrrm` | time-limit 0.8 s | **-0.0119** | [buy](https://solscan.io/tx/2fasK5HwPRqvBEZ1aijoYYWn9MPXHdtLqF6V3jpdqGGWVVbUW65MRVGxYwmcvhwHDB6Z3GKfCwcejeW6XzeEGxyG) [sell](https://solscan.io/tx/4mE6cEQeQE1iYFfThzuze3sRmoJQqRPLra3m8kTifd8tpga1jZdMvC3sB3PHtt2QQiWXXSm7FRSrMXC1Mw1bs8aa) [whale](https://solscan.io/tx/gEYwZGJTzon7CVKNok9dK66dsreRdoFB2kcQKHFxjZpg67A6om52NfcU2wKaZMZA8KBEzKsnsWnebtyoYvr464x) |
| 7 | 02:26:53 | [9UJxjc](https://gmgn.ai/sol/token/9UJxjc26zsFsSJgyJVV2Mtp1BDAFeWztNajWbA5vcKYa) | 8.8% / 4.94 | +5 | BAM `mineL1` | time-limit 0.9 s | **-0.0042** | [buy](https://solscan.io/tx/5RVWAXUCwJQf3yTnYZ4Vfbvj3xUEanTygZwUZMtTGsKAVE4MxfbwTEvhUP7Hhr593hL23eQKBiZF1tja9YF6QFf9) [sell](https://solscan.io/tx/FX9DusAxCJdTSRQwRmnPJEc8xxGjWC4xwaTp1s91DPkp5djJoXNTiHidzuCQ1fQoqiYH15Geo8Yw3EUV89D7n6d) [whale](https://solscan.io/tx/2i7JaA69EkwK8WrxxN9qonwmCAUeMix3EhBFJJCV6wVjNb8K5jxFA77snrtuuH1BR7iWZydRKkE6jLuVjupHaVei) |
| 8 | 02:30:13 | [BQfuAL](https://gmgn.ai/sol/token/BQfuALZvJBmHXk3nYLzBiBWwwatmo2HTJHfch8ffpump) | 6.8% / 2.96 | +3 | Jito `3SkE34` | take-profit 0.6 s | **+0.0555** | [buy](https://solscan.io/tx/2dNyAx8uoJBsCGpKemUhpU1sJB7vDutErBgax7MqxBwkCGrh4v7VtS8b5cDyuuw191y8nADEPB47ftX1oMFeFHC4) [sell](https://solscan.io/tx/xDTegtcNZWKHkNpHswC6BoUt7oq6GztUizSz7QfiQnikqYo2LCviuRrwniVs7HR8AweDNDAA3kgSgqLPnfm3jv9) [whale](https://solscan.io/tx/4PoBWpsKiHeKzPVT4pgy1M3HY4LwGWsYndm46q7gEkd7VaQR4fjmvRDEEEgKGdMH4V2hgm8DLTJPAobajL7LzM8J) |
| 9 | 02:30:48 | [7YtnNb](https://gmgn.ai/sol/token/7YtnNbk8BLatNmwA5CzekRzobZFZP5Vcw84PzEzypump) | 7.1% / 2.96 | +6 | BAM `3JotfS` | time-limit 0.9 s | **+0.0124** | [buy](https://solscan.io/tx/3Yk3TLzLTpxrduvgR3ZPdFungSWqG2LoSNwmGbBWB7wEP9UFBj7Md2FvvSiqJGAp6JvaJWHtBgUEPMg5tvw8Quvq) [sell](https://solscan.io/tx/2tYj4EoZvq3UmUoHCAf9QYaZ7ARAjD2DVZp81ZLxzsEgLPAiU8RvECsopY31RC9xbNXi5ibUbc5xNWpKh7NMunfT) [whale](https://solscan.io/tx/3oEw1tJqf9n4PxVw7eVWiKrWhobWwfqXJuSX2aUJEdXnujZ3AezWAbvZRSkbzc9h3zN4CipmmzCqxKeVALZYb5Ny) |
| 10 | 02:32:44 | [GKyEUy](https://gmgn.ai/sol/token/GKyEUyn7LjdF3er8BnAcjTa3oJdJAeFqjbfThHbvpump) | 6.3% / 1.98 | +9 | Harmonic `Fd7btg` | time-limit 0.7 s | **-0.0119** | [buy](https://solscan.io/tx/42YmRhnEZk1Q6zqHYeaVBKtAb2NVrmNAhuRfW1GurszBE3SYF54fEkf2Thxz3aczbNj5yeKoYNnf2CjbDjPJT9oQ) [sell](https://solscan.io/tx/5Tw93vkULMu1YELCKybyXQYd3F63XrJHKENofCirnEA63KyX2my4UCiSnyHrUSqEGodZ2VSTumFnFSnfYswqJ6bu) [whale](https://solscan.io/tx/2j8rbF4wCNPnTj7QK6E8MzhVngdzJaoFk6Mt2PhieVJBCKGBMWuvj7t1CatmAxL8uNXJswQTFjFXSH4cGt1z7Hqk) |
| 11 | 02:34:06 | [9UJxjc](https://gmgn.ai/sol/token/9UJxjc26zsFsSJgyJVV2Mtp1BDAFeWztNajWbA5vcKYa) | 6.2% / 2.79 | +4 | Jito `5pPRHn` | time-limit 1.0 s | **+0.0096** | [buy](https://solscan.io/tx/46PL3pNS5iu6iZn4GwhBjYPcMxijKMMr1uRsW5bn8aoqRKQsg4wDDLjNZDvHk6Drjc96Lg4r7Twq4szLJmpF7nEF) [sell](https://solscan.io/tx/55TQGmnMyVVeCxVMwZ1p3V7sgVA51RxxcNpKbAcVqCu8zxW7az2miDmB269P8biwNEAi1gE4ppjUTRM5onZwSRhP) [whale](https://solscan.io/tx/3tayWuAnNbzjL37U1XjZ1YBNapaEChhGEvE8thwXxaHQZesMzmfVstnM8qxEGjMazRWGGGWSsePL6YxoNSEvJLaJ) |
| 12 | 02:36:47 | [C6WkJZ](https://gmgn.ai/sol/token/C6WkJZLLALwoN771E1J7Z1scQV4oqUDxssVVAYkZpump) | 12.7% / 5.86 | +0 | Harmonic `9W3QTg` | time-limit 0.8 s | **+0.0073** | [buy](https://solscan.io/tx/sgk4QJ8CFxseYHVrV2c5w6tg392WnsL5axeee6Zf3QTNnxcAKSwC7jk1UbbUHfM9cZ7bEq9oyAn6kddnjxaDS1t) [sell](https://solscan.io/tx/3dHbnAoE3psuRsSHXWtTSonGHpZsJ3jizuzrzrnBPRjsycUmgfdNifxnMVH2TuurCX2THxjsEmCgeWUbkH2AuNFP) [whale](https://solscan.io/tx/31gxnL19jY1eHaoAZHet81ijqiTVfYVgwiLScm9pnkBQ6VGiZQdbSkAz54nCiafVxzQErYsXb3tscDNeqV3ysbp8) |
| 13 | 02:37:48 | [C9HbAM](https://gmgn.ai/sol/token/C9HbAMsNy9mxgST3PWaBk8neT1bQbf5xhCyPnGWApump) | 6.3% / 1.98 | +1 | Harmonic `EXckih` | time-limit 0.8 s | **-0.0139** | [buy](https://solscan.io/tx/5U43Y78VV7j5Kz3zECMpkXhYUMGRueoM6unXz87n2sAvMizoS87teytUk52WoozbwGfhXrDFcaj3zdC6XwBd3quq) [sell](https://solscan.io/tx/5D31Ybrz43J4v94WAjZW3vdnMxYxi69kiJ1nU6G511xBtQWWQt7D8o3zMin5P3FJQKSR6f3idmAiouRiZUap5XJ4) [whale](https://solscan.io/tx/5pEr6kYrn2A74Yt4Kp3AsqYQRj85kBeZddCKjPABX3GAsqJMF7XMPjkecScp7a1ueUYgHcjU574ZZ2qCtqqPo6nH) |
| 14 | 02:40:39 | [5gSeSi](https://gmgn.ai/sol/token/5gSeSiFqSMaNL8pmAH76f1RKdcM2ZnobV3F7iiQByX4S) | 13.1% / 4.94 | +7 | BAM `HLnodb` | time-limit 0.8 s | **-0.0316** | [buy](https://solscan.io/tx/Uv4qs6oHJ6EfHQzbiKoqLQkaC1BTA72isw7FRXVyhav7RtoaaugE9ADNMyxnfwoLu1FF8eF6cFNe3xsY8Z4j8mL) [sell](https://solscan.io/tx/51jSKdptNCRDsfecQNdUatXfDsQJGVy828B7aY5H1LZyhD1TsH1XDZH9FJq2v1BfWBGp3E8VSLJfprMsQJfC5gfX) [whale](https://solscan.io/tx/5D2G6BzvASe8JBQb1qNN5Zn7wE5zp3iubQgjHfg1pXpv74ozzcGGyMhDx9hXseWwZDksqnJrjWpySSBjmevKM8GE) |
| 15 | 02:40:57 | [3N8v1m](https://gmgn.ai/sol/token/3N8v1mNaZxDDaHmniqoxTJQZJSHZh3jS3m65vanXpump) | 7.3% / 4.44 | +6 | Jito `E1r4Ps` | time-limit 0.8 s | **-0.0065** | [buy](https://solscan.io/tx/ZuRs1ztQPwdZkbkhfUngGtQzWptX4ooVgjQRoeMsbPwPLQNY1c2GoSeLFZgr8nKsuaVXg6pxYM1mNtewk86yhKh) [sell](https://solscan.io/tx/4A4AD2z2bfYKb7ompoX7u71iERarEEpFffQjyjSfZpusExfGfJMAhadJjWNCQLcuVe5L8YLXGJYNS6ngxFT7rEkr) [whale](https://solscan.io/tx/5ffKPStrv55q3wo1MVaa3rddEFmejmpqz3GYNb5nzWsohuzyWzGccXoufDiviR9RPGiTrPFGqCcD6ZtBrZ4FXRb2) |
| 16 | 02:43:10 | [4Cvdjz](https://gmgn.ai/sol/token/4CvdjzLrvk9CBuVwT8Xvw6xUMLbDUPsiB55YMFiPpump) | 8.4% / 3.46 | +2 | BAM `CwyVpf` | time-limit 0.9 s | **+0.0219** | [buy](https://solscan.io/tx/55x9i1d4Y76BzxhjrSZNKd9F3V7fa9EPhQ5edYs98JJ2bMVX1KbgVV82WtTaDVDWaModJKdnyQb9PV3xgZgPeWue) [sell](https://solscan.io/tx/5zvqgqoT8vQJT8hQHSxFQE9wonGKdewFZSx4oTWi3mgUz9CG5VJWkpdgpSPKkWQxQFfSJ4RZvoHDjBQ9fnTjvqbj) [whale](https://solscan.io/tx/569z6EBf5MDaU84y9BiRQQuhyr1yfLYvm4gZUNj9f46f7Z7BAe4X617Xp7GLrpm4UHz1F3YQ4oWg17ZTSE4rDnKH) |
| 17 | 02:44:09 | [WBVfcU](https://gmgn.ai/sol/token/WBVfcU61gotv2AsQACeuuMU78MJHBW99BS7ZzTepump) | 6.4% / 3.46 | +2 | Harmonic `Hz5aLv` | time-limit 0.9 s | **-0.0119** | [buy](https://solscan.io/tx/3Xqx3EVkA1seVAScaY4jFJ4DWDPbuL1pGcUWMaX3jCRghVxp2CUgRUDF9nyU54aHtDqtZQ5FrMTxu635wp7iQS9B) [sell](https://solscan.io/tx/4XyedZA2Q7Lv28Qq3s8ExwztnS3yUqQk2pBEnGxWqaiDJZko2MRCthn2ozXX7zPhdfamtE3XojccByLdwpXLrWW9) [whale](https://solscan.io/tx/2aiWHVRxdogopajUS5NbjN9Q8v2NTBe5zfcwuL1w9FPXersM8DMYet7coHyCATV5nFxM6rxhVrbHdeQMbGTcmhdx) |
| 18 | 02:45:49 | [2zYvnA](https://gmgn.ai/sol/token/2zYvnAdMSX2ukCjcrHfCNC7CNGmGXZkScPenJsaUpump) | 14.4% / 4.94 | +3 | Harmonic `2m1A2W` | time-limit 1.0 s | **-0.0061** | [buy](https://solscan.io/tx/4H7Px61mYxKtE5icCN7oJ21rt5LqSZ2r9mJMC9tDZtthyxLLr5Sa4Cp5WaesTpAbyQvqjC8egKmSt51Mvt62Jejq) [sell](https://solscan.io/tx/aqT8kFVXpgACXpdmPYWymL84auGhcsz7mr2W7F4X4JDFehtDHA3FjrgT2TcE9tQYQ8GHj9YRBgRrtUnh6amf5gB) [whale](https://solscan.io/tx/2b2cfZHpWXjVZ7JuL3rPMGWPaycZfpkodsVbsBQFZgBwRHQAbGajPXAk4UXhJPz7pMWQqFQM7c6nPW331LWTTcoe) |
| 19 | 02:47:19 | [HZN3x4](https://gmgn.ai/sol/token/HZN3x4o3Wwpn7U6pdzkjxCBYs14Sx4a5mwRKDYp6pump) | 6.1% / 3.25 | +6 | BAM `5DYpYg` | take-profit 0.6 s | **+0.0674** | [buy](https://solscan.io/tx/3goiLuuVs28zeYbFjJPWEMdDmRKvyXKRUDw8HaH9C8AvLQZS9eyvXdYGe74PjJz3z2xzCAmLJEyuzxr5pq5QdPT2) [sell](https://solscan.io/tx/5M3PyWNAQWCgyrWJKqKX1jE6S6KNi8eJrfBbRTEt4sKXaGfqaQcQBoXkMTFgSKLcCw2i6ByZ5yfp1zoXjHKdsgKf) [whale](https://solscan.io/tx/4cPEfwBJs1AsV7JRa1N6aMWdvuuLbQemATJ1ZAwUXqL1Q9fJoGvidrKUgBiFP7MVGb9W1vGUmf2U2zXgQ79SE96k) |
| 20 | 02:48:07 | [DiWbWo](https://gmgn.ai/sol/token/DiWbWoTDgtAutopSdboEyX8Vstr4KdECyFMH9iKipump) | 6.5% / 3.25 | +6 | Harmonic `CAo1dC` | take-profit 0.6 s | **+0.0690** | [buy](https://solscan.io/tx/2vJ886Xnornd2GTe1RYXtyzaAGGmySygu9eKjkqZBYjZUyVJDf3VJMzpbELkWypjJWL5WtXqpxDbbrAAM44Kxd8G) [sell](https://solscan.io/tx/sEiBawPPN89iCQSTRWTr2671bt5mAtmVDaWt9wLzZr95hkX9xkKqjxbPEzVDzK5gR2Vx3fGzACUEmUSavAPCyMk) [whale](https://solscan.io/tx/hTGrnfjtfcCbfNcgc5bCnLtqq7BHPXD1popaihSDxFvNMU1HS6fxGi81F6Qxjp98QS2UouxDxVDCrohxYEwhFmN) |
| 21 | 02:48:25 | [6ESztP](https://gmgn.ai/sol/token/6ESztPpqDyndKTfWZyhnuVEC2tC4QtVgVSAgXy6Bpump) | 6.2% / 2.67 | +1 | BAM `parafi` | stop-loss 0.5 s | **-0.0842** | [buy](https://solscan.io/tx/4WT6Vdm5VpnGbzuqvdmxAt2xvHQN9UiP8ErwFvCtWMagb7CeQwoPx6EaHDTow5Nox4eDXGzQjY94GeLFxsoxJqVL) [sell](https://solscan.io/tx/1cHN4wV5aZEe95FQbGfYv25LeAgTCzErjq8Vw6vPKcwvkWpGjmFDPDK8Evq5doKWfxPt1T1XTcrcWv9ETMVreDu) [whale](https://solscan.io/tx/35eE9ByHoRVudQyJmnFymVx66ZTwBwHRgiHtqSV7cfdurGxwNxxwenSdhrnzSRdvF55irV8cRWdNtJi1Jarb2JTQ) |

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 1594 |
| Inside the envelope (age / drop / since-buy / size) | 643 |
| Picks (score above the threshold) | 23 |
| Skipped | far_leader 13, spacing 5, presend_armed 1 |
| Buys sent | 4 |
| Filled | 3 |
| Failed on the +5% guard | 0 |
| Failed (other) | 1 |
| Never landed | 0 |
| Sold (positions closed) | 3 of 3 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 02:24:55 | [GJYD36](https://gmgn.ai/sol/token/GJYD36QKw8GCNKJaik9jxEq36EVY71RaczVvxGTnpump) | 0.40 | -1.08 | 2.08 / −12% | 1.7 s | BAM `4XspXD` | filled | **+0.0061** |
| 2 | 02:28:08 | [DTwks6](https://gmgn.ai/sol/token/DTwks6SoKhHQePZ75c17RSrx1v77egK8rR8Xee6mpump) | 0.40 | -0.34 | 6.00 / −17% | 2.3 s | Harmonic `GZ4U21` | filled | **-0.0504** |
| 3 | 02:30:15 | [BQfuAL](https://gmgn.ai/sol/token/BQfuALZvJBmHXk3nYLzBiBWwwatmo2HTJHfch8ffpump) | 0.40 | -0.67 | 3.15 / −16% | 10.0 s | Jito `HEL1US` | failed | -0.0005 |
| 4 | 02:47:16 | [9y9ktW](https://gmgn.ai/sol/token/9y9ktWSsHp6V9vWXaE9yhYjgpLwjv4gz4V494zpKpump) | 0.40 | -1.40 | 1.65 / −10% | 7.4 s | Harmonic `Fd7btg` | filled | **+0.0429** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 64 | +1 | 0 | **falcon+falcon-udp** of falcon-udp+nozomi+helius-swqos+bolt+falcon | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/FoNLh6vEA4qygGNSqKwZMcwCKRuUMk3ag4HP8swbKWkqDPuVPfqtCHvQfYpeGTjXDHkeoyBec2otDc2pWRyN3n3) [sell](https://solscan.io/tx/3q1jodr7VWrKxTGW5ntda6HmeiJAyAcs7NL8p8f5bwoxTvNqd5Macj9yEuq1evybk3XzMp1vxbyAh373bbzWt5RX) [dump](https://solscan.io/tx/45PRUbGm4Lfrhw1qt27hjTsAbQdoZoGjMWR4m2K5gjK3EtDhdYUPW2RD9Lyodv7ZbyUf6kWyduMzboBAGdMChTR2) |
| 2 | 33 | same | 2 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive | time-limit 1.6 s | 1 | [buy](https://solscan.io/tx/2hCCVHbV5Gi2dABDeCUTGXPyhpFPB1FbgGCbH1cNQBoye5aSYZ6LJjYCXCp5u5gR21H7Xqa3rwkF1a7KBJsV32wV) [sell](https://solscan.io/tx/2R8hwQTKamNJQzt8aBZcgtYFKsySgZHb4uaDrotd3ze29GYTQRqxNgoHS1GmGN6Pfuj2u97GLtSvZQ5oATrZsjHC) [dump](https://solscan.io/tx/3ZVRBReuDPwyzSpRePbRDEfzLNrABn4JWLxR9V3vc3Z8RZdVRoQjXkY2ZAXJ9nA8fQnRZM9BSf12wvWP2cKugvb7) |
| 3 | 344 | +2 | 6 | **soyas** of falcon-udp+glaive+falcon+helius-swqos | – | – | [buy](https://solscan.io/tx/2WfcbkHF1em7zAx5XPZgtL8RUibbGZSwwoWi73gkkPKk7A3i9Mn8TvZt9TfDSvAar8srzhi3mahSz3iGE6xjUVAK) [dump](https://solscan.io/tx/4tfkYHh2XSk63cAr2jKqhN2Dt6JsrYkNE8hAdXk3neE5bN5CjHXqX2h74dNunsUTnunSk9mmbPLWxTbhTHTAwYih) |
| 4 | 55 | +1 | 0 | **nozomi** of landx-fra3+falcon-udp+nozomi+falcon+glaive | time-limit 1.4 s | 1 | [buy](https://solscan.io/tx/KwnUErJznXjp2fvfLpVfyg3eT5vs7XMvhidayVxzgU94T1omXfGdCZGqXLhi6czQc8K2YJiynKeadz7sBrJaQo4) [sell](https://solscan.io/tx/2qUWgd2f2H7nyg5LQEBmmoRHyAnZXhpnS3SpSJDUDGWw3aRY9RhxLwrE65eauXhhxtSRPm8i8EM4L7pqx3YwqowD) [dump](https://solscan.io/tx/2EsPZ14xpv8NnhjSJH2PwbutNuFbHBxxtupCGJGoDSf5QiFXTT2ZPtv5CreWD3kKrtgmFE8AP83ifufAK9MVXGP5) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Harmonic | 2 | 2 | 100% | -0.0075 | -0.0038 | 1/2 |
| BAM | 1 | 1 | 100% | +0.0061 | +0.0061 | 1/1 |
| Jito | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 4 | 3 | 75% | -0.0019 | -0.0005 | 2/3 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| next block | 2 | 2 | 100% | +0.0490 | +0.0245 | 2/2 |
| same block | 1 | 1 | 100% | -0.0504 | -0.0504 | 0/1 |
| 2+ blocks | 1 | 0 | 0% | -0.0005 | – | 0/0 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 02:00 | 4 | 3 | 75% | -0.0019 | -0.0005 | 2/3 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| time-limit | 3 | -0.0014 | -0.0005 | 1.4 s |

## 8. P&L leaders
**Best trades:** 9y9ktW +0.0429 (Harmonic, time-limit, score -1.40); GJYD36 +0.0061 (BAM, time-limit, score -1.08); DTwks6 -0.0504 (Harmonic, time-limit, score -0.34)

**Worst trades:** DTwks6 -0.0504 (Harmonic, time-limit, score -0.34); GJYD36 +0.0061 (BAM, time-limit, score -1.08); 9y9ktW +0.0429 (Harmonic, time-limit, score -1.40)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `Fd7btgyS` | HarmonicAgave | 1 | 1 | +0.0429 |
| `4XspXDcJ` | AgaveBam | 1 | 1 | +0.0061 |
| `HEL1USMZ` | JitoLabs | 1 | 0 | -0.0005 |
| `GZ4U21pY` | HarmonicFiredancer | 1 | 1 | -0.0504 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1421 (p25 1406, p75 1435, n 4) |
| Executed-feed lag behind first sighting, ms | 3.2 (p25 2.6, p75 3.8, n 4) |
| Buy sent → our tx seen on the feed, ms | 55.8 (p25 49.6, p75 61.9, n 4) |
| Fills: our buy seen on the feed after the dump, ms | 55 (p25 33, p75 64, n 3) |
| Guard fails: our failed buy seen after the dump, ms | – (p25 –, p75 –, n 0) |
| Fills in the dump's own block | 1 of 3 |
| Guard fails in the dump's own block | 0 of 0 |

**Which copy landed (nonce fan-out):** nozomi 2, falcon+falcon-udp 1, soyas 1

**Send-path answers (FAST-ACK lines):** falcon 4 (median ack 1.2 ms), nozomi 3 (median ack 0.6 ms), glaive 3 (median ack 0.3 ms), helius-swqos 2 (median ack 4.2 ms), bolt 1 (median ack 0.3 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 0 |
| Guard fails: rival buys ahead (median) | – |
| Guard fails: rival SOL ahead (median) | – |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| 8yYMhuYo | 1 | 0 |
| 2XyiEK56* | 1 | 0 |
| 5ZKd8DNB | 1 | 0 |
| HLU8QbLd (41Pr family) | 1 | 0 |
| 2Dd3TRSd* | 1 | 0 |
| 66vDAQEe* | 1 | 0 |
| CatkiNiJ* | 1 | 0 |
| haqq (dip bot) | 1 | 0 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.0386 |
| Pump fee on buys | 0.0148 (0.0049 per fill) |
| Pump fee on sells (residual) | 0.0153 (0.0051 per fill) |
| Buy tx fees (base + priority) | 0.0015 (0.00051 per fill) |
| Buy tips | 0.0030 (0.0010 per fill) |
| Sell tx fees | 0.0018 (0.00060 per fill) |
| Sell tips | 0.0036 (0.0012 per fill) |
| Failed buys (tx fees) | 0.0005 (1 buys) |
| **Result** | **-0.1593** |

Buy compute used (fills): median 73,905 CU, max 81,404 CU (limit 100k).

## 12. Health checks and red flags
- 🔴 kill switch: DIP KILL-SWITCH: run PnL -0.561160 SOL (balance 2.008499 + open 0.000000) below -0.500000: no new buys
- ⚠️ 24 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ⚠️ big loss DTwks6 -0.0504 (time-limit, Harmonic)
- ⚠️ BQfuAL: landed 2 blocks after the dump
- ⚠️ pre-send (session #1): 22 fills but 21 closed positions
- ⚠️ big pre-send loss GRcpcw -0.1027 (stop-loss, Firedancer)
- ℹ️ wallet change -0.5612 vs trades -0.1593: gap -0.4019 SOL (transfers / rent / unsold — see notes); pre-send tries never seen on our feed: 50 (up to 0.0003 SOL)
- 🔴 Merged-fill bug (see the verdict): tokens left unsold at the end of the run. Fixed in dip19 before run 23: a pre-send account is closed only after every try's deadline, a fill after a close opens a new position that gets sold, and realized sums every buy.
- ℹ️ This report's −0.159 leaves out the unsold tokens: the wallet was −0.561 at the end of the run and −0.231 after the hand sell.

Checks passed: every reactive fill was sold; fast-verify: 0 identical, 0 MISMATCHED; nonce self-test passed.

## 13. Fixes and follow-ups
**Done after this run:**

- dip19 (10-26 ~03:55 PKT): merged-fill fix, deployed on both servers; first used in run 23.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r22.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r22.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Pre-send (section 4b): the jsonl presend_live_* records (fills, closes, REALIZED, account closes, stops, end checks) and presend_attempt_land (try results, failed-try fees); the log's PRESEND LIVE lines when a run has no such records.
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

# Active send paths (w5h2 segment 5, 2026-10-03 22:18 UTC)

All run from Cherry (Frankfurt). Keys are in `/root/arb-lab/.env` and are never shown here. Tips are paid only when the trade succeeds;
copies share one durable nonce, so at most one lands per trade.

| # | Path | Service | Endpoint | Round trip from Cherry | Key passed as | Tip (lamports) | Profit share | Rate limit/s | Tip accounts |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `jito-bundle` | Jito block engine (bundles) | `https://frankfurt.mainnet.block-engine.jito.wtf` | 0.5 ms | whitelisted auth keypair | 1000 | 0.7 | 5 | 8 |
| 2 | `helius` | Helius Sender Max | `http://fra-sender.helius-rpc.com/fast` | 0.2 ms | none | 1000000 | 0.5 | - | 10 |
| 3 | `rpcfast` | RPC Fast Beam | `beam.rpcfast.com (from LANDER_RPCFAST_URL)` | 2.4 ms | key in URL (LANDER_RPCFAST_URL) | 10000 | - | 1 | 2 |
| 4 | `jito-tx` | Jito sendTransaction | `https://frankfurt.mainnet.block-engine.jito.wtf/api/v1/transactions` | 0.6 ms | header x-jito-auth (JITO_UUID) | 5000 | - | 2 | 8 |
| 5 | `haan` | Haan Sender | `https://sender.haandigital.eu/api/v1/transactions` | 0.6 ms | Bearer (HAAN_API_KEY) | none | - | 1 | none |
| 6 | `astralane` | Astralane Iris | `http://fr.gateway.astralane.io/irisb?api-key=<key>&method=sendTransaction` | 0.3 ms | URL api-key | 1000000 | - | 5 | 17 |
| 7 | `bolt` | Raiden Bolt | `https://fra.bolt.raiden.wtf/api/v1/sendRawTransaction` | 0.3 ms | header api-x-token (RAIDEN_BOLT_KEY) | 1000000 | - | 5 | 9 |
| 8 | `tpu-direct` | Direct to leader (QUIC) | `https://rpc.haandigital.eu/` | 0.7 ms | none (Haan RPC for leader schedule) | none | - | - | none |
| 9 | `everstake` | Everstake SWQoS | `http://fra-swqos.everstake.one` | 0.5 ms | none | 1000000 | - | 10 | 10 |
| 10 | `nozomi` | Temporal Nozomi | `http://fra2.nozomi.temporal.xyz/?c=<key>` | 0.2 ms | URL ?c= (NOZOMI_KEY) | 1000000 | - | 5 | 17 |
| 11 | `blockrazor` | BlockRazor | `http://frankfurt.solana.blockrazor.xyz:443/v2/sendBinaryTransaction?auth=<key>` | 0.3 ms | URL auth= (BLOCKRAZOR_KEY) | 100000 | - | 3 | 14 |
| 12 | `flashblock` | FlashBlock | `http://fra.flashblock.trade/api/v2/submit-batch` | 0.2 ms | header authorization (FLASHBLOCK_KEY) | 100000 | - | 10 | 10 |
| 13 | `nextblock` | NextBlock | `https://frankfurt.nextblock.io/api/v2/submit` | 0.2 ms | header authorization (NEXTBLOCK_KEY) | 1000000 | - | - | 8 |
| 14 | `jupiter` | Jupiter tx.jup.ag | `https://tx.jup.ag` | 0.9 ms | header x-api-key (JUPITER_API_KEY) | 1000000 | - | 1 | 16 |
| 15 | `landx-fra3` | LandX (Cherry Servers FRA) | `udp://fra3.landx.dev:10000` | same data centre (UDP) | first 12 bytes of each UDP packet (LANDX_KEY) | 1000000 | - | - | 10 |
| 16 | `landx-fra1` | LandX (TeraSwitch FRA) | `http://fra1.landx.dev/txb/<key>` | 0.2 ms | URL path /txb/<key> (LANDX_KEY) | 1000000 | - | - | 10 |
| 17 | `speedlanding` | SpeedLanding | `http://fra.speedlanding.trade/sendTx?apikey=<key>` | 0.4 ms | URL ?apikey= (SPEEDLANDING_KEY) | 1000000 | - | - | 8 |

## Tip accounts per path

### jito-bundle (Jito block engine (bundles)): 8 accounts

```
96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5
HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe
Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY
ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49
DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh
ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt
DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL
3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT
```

### helius (Helius Sender Max): 10 accounts

```
4ACfpUFoaSD9bfPdeu6DBt89gB6ENTeHBXCAi87NhDEE
D2L6yPZ2FmmmTKPgzaMKdhu6EWZcTpLy1Vhx8uvZe7NZ
9bnz4RShgq1hAnLnZbP8kbgBg1kEmcJBYQq3gQbmnSta
5VY91ws6B2hMmBFRsXkoAAdsPHBJwRfBht4DXox3xkwn
2nyhqdwKcJZR2vcqCyrYsaPVdAnFoJjiksCXJ7hfEYgD
2q5pghRs6arqVjRvT5gfgWfWcHWmw1ZuCzphgd5KfWGJ
wyvPkWjVZz1M8fHQnMMCDTQDbkManefNNhweYk5WkcF
3KCKozbAaF75qEU33jtzozcJ29yJuaLJTy2jFdzUY8bT
4vieeGHPYPG2MmyPRcYjdiDmmhN3ww7hsFNap8pVN3Ey
4TQLFNWK8AovT1gFvda5jfw2oJeRMKEmw7aH6MGBJ3or
```

### rpcfast (RPC Fast Beam): 2 accounts

```
ASdXviZw2kbViFuAgZF26RPZL1HdybUoWdcveG2nfU8D
Ax2JBnTPUpBFWe75z3YtgueWUfvZPZ6ZFXiMWJMUnjbo
```

### jito-tx (Jito sendTransaction): 8 accounts

```
96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5
HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe
Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY
ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49
DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh
ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt
DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL
3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT
```

### astralane (Astralane Iris): 17 accounts

```
astrazznxsGUhWShqgNtAdfrzP2G83DzcWVJDxwV9bF
astra4uejePWneqNaJKuFFA8oonqCE1sqF6b45kDMZm
astra9xWY93QyfG6yM8zwsKsRodscjQ2uU2HKNL5prk
astraRVUuTHjpwEVvNBeQEgwYx9w9CFyfxjYoobCZhL
astraEJ2fEj8Xmy6KLG7B3VfbKfsHXhHrNdCQx7iGJK
astraubkDw81n4LuutzSQ8uzHCv4BhPVhfvTcYv8SKC
astraZW5GLFefxNPAatceHhYjfA1ciq9gvfEg2S47xk
astrawVNP4xDBKT7rAdxrLYiTSTdqtUr63fSMduivXK
AstrA1ejL4UeXC2SBP4cpeEmtcFPZVLxx3XGKXyCW6to
AsTra79FET4aCKWspPqeSFvjJNyp96SvAnrmyAxqg5b7
AstrABAu8CBTyuPXpV4eSCJ5fePEPnxN8NqBaPKQ9fHR
AsTRADtvb6tTmrsqULQ9Wji9PigDMjhfEMza6zkynEvV
AsTRAEoyMofR3vUPpf9k68Gsfb6ymTZttEtsAbv8Bk4d
AStrAJv2RN2hKCHxwUMtqmSxgdcNZbihCwc1mCSnG83W
Astran35aiQUF57XZsmkWMtNCtXGLzs8upfiqXxth2bz
AStRAnpi6kFrKypragExgeRoJ1QnKH7pbSjLAKQVWUum
ASTRaoF93eYt73TYvwtsv6fMWHWbGmMUZfVZPo3CRU9C
```

### bolt (Raiden Bolt): 9 accounts

```
t1TcSg9biJsz4NjKjhopK8QZzPS4KzBgFSszu5QTGgF
t2XFAFBaUkCzxJwEbLWFX9PKFjfBCp2tSyFtx5z4RZM
t3QLYyXH4vZYbEifLqjD581t5dPVhq9LABxWceySzL2
t46SqGmwStEffUMp1fr2xmv5uyR85TB9annJuLKLf83
t55hdzzftxWkYy3J8t32C9RRcZDuMZ4LDuBmbTzJFkU
t6UtTQLUGHJJrzxAb8PBBZdZKra8SWUqvTv9zPnxKNz
t7qUQU35sLpPydh42BcPmtEfTWW8gBe4Ry3gjwVnokJ
t8pPgarSK3TnuLbbHmoE1RCQdLxfxuPqNTyFjBKahok
t96GGdw3MiaGR993XN8PSsRpKGXx56t5Wf6zcF1hBpY
```

### everstake (Everstake SWQoS): 10 accounts

```
J4cL8c22KNLHwheuWxK1SCYBWASWPGhEi6xvcGyf6o3S
EzuhsszPxRUHBwGPXtKoqCB58EiTJ1QiYA2XrhbUEFbr
7wsUm2VDopGDFyXkyhmgUh9V15QkEvnyqbgUPcagLcw2
Cy3WAM9NdjFG3kXCxXmD17WmtJMBKVpoBXabkSm88Xdt
BEEya88mme6JJ4rgshBR23eiDHmygUii9opUHE3qxnqK
Gq21dPAGVuuZucqBQeCkfbbqoEowL1t88igZekJ93CRu
79HFWkNoPhotXuFYi1ksuK5hE7AUnKasafP6c71hS9sM
Cp4pCm5JjDaZ4gXB8eSjNJvQ8eg7uK6awgjveofrSATz
DMHQ51qK2wChtDEUED54cqzbSLMLGvTygQCv5uLTUmZP
GDnz7cAA7hKEFmDyrk6mz3drybHWc3Gn14y9LCsvvtjE
```

### nozomi (Temporal Nozomi): 17 accounts

```
TEMPaMeCRFAS9EKF53Jd6KpHxgL47uWLcpFArU1Fanq
noz3jAjPiHuBPqiSPkkugaJDkJscPuRhYnSpbi8UvC4
noz3str9KXfpKknefHji8L1mPgimezaiUyCHYMDv1GE
noz6uoYCDijhu1V7cutCpwxNiSovEwLdRHPwmgCGDNo
noz9EPNcT7WH6Sou3sr3GGjHQYVkN3DNirpbvDkv9YJ
nozc5yT15LazbLTFVZzoNZCwjh3yUtW86LoUyqsBu4L
nozFrhfnNGoyqwVuwPAW4aaGqempx4PU6g6D9CJMv7Z
nozievPk7HyK1Rqy1MPJwVQ7qQg2QoJGyP71oeDwbsu
noznbgwYnBLDHu8wcQVCEw6kDrXkPdKkydGJGNXGvL7
nozNVWs5N8mgzuD3qigrCG2UoKxZttxzZ85pvAQVrbP
nozpEGbwx4BcGp6pvEdAh1JoC2CQGZdU6HbNP1v2p6P
nozrhjhkCr3zXT3BiT4WCodYCUFeQvcdUkM7MqhKqge
nozrwQtWhEdrA6W8dkbt9gnUaMs52PdAv5byipnadq3
nozUacTVWub3cL4mJmGCYjKZTnE9RbdY5AP46iQgbPJ
nozWCyTPppJjRuw2fpzDhhWbW355fzosWSzrrMYB1Qk
nozWNju6dY353eMkMqURqwQEoM3SFgEKC6psLCSfUne
nozxNBgWohjR75vdspfxR5H9ceC7XXH99xpxhVGt3Bb
```

### blockrazor (BlockRazor): 14 accounts

```
FjmZZrFvhnqqb9ThCuMVnENaM3JGVuGWNyCAxRJcFpg9
6No2i3aawzHsjtThw81iq1EXPJN6rh8eSJCLaYZfKDTG
A9cWowVAiHe9pJfKAj3TJiN9VpbzMUq6E4kEvf5mUT22
Gywj98ophM7GmkDdaWs4isqZnDdFCW7B46TXmKfvyqSm
68Pwb4jS7eZATjDfhmTXgRJjCiZmw1L7Huy4HNpnxJ3o
4ABhJh5rZPjv63RBJBuyWzBK3g9gWMUQdTZP2kiW31V9
B2M4NG5eyZp5SBQrSdtemzk5TqVuaWGQnowGaCBt8GyM
5jA59cXMKQqZAVdtopv8q3yyw9SYfiE3vUCbt7p8MfVf
5YktoWygr1Bp9wiS1xtMtUki1PeYuuzuCF98tqwYxf61
295Avbam4qGShBYK7E9H5Ldew4B3WyJGmgmXfiWdeeyV
EDi4rSy2LZgKJX74mbLTFk4mxoTgT6F7HxxzG2HBAFyK
BnGKHAC386n4Qmv9xtpBVbRaUTKixjBe3oagkPFKtoy6
Dd7K2Fp7AtoN8xCghKDRmyqr5U169t48Tw5fEd3wT9mq
AP6qExwrbRgBAVaehg4b5xHENX815sMabtBzUzVB4v8S
```

### flashblock (FlashBlock): 10 accounts

```
FLaShB3iXXTWE1vu9wQsChUKq3HFtpMAhb8kAh1pf1wi
FLashhsorBmM9dLpuq6qATawcpqk1Y2aqaZfkd48iT3W
FLaSHJNm5dWYzEgnHJWWJP5ccu128Mu61NJLxUf7mUXU
FLaSHR4Vv7sttd6TyDF4yR1bJyAxRwWKbohDytEMu3wL
FLASHRzANfcAKDuQ3RXv9hbkBy4WVEKDzoAgxJ56DiE4
FLasHstqx11M8W56zrSEqkCyhMCCpr6ze6Mjdvqope5s
FLAShWTjcweNT4NSotpjpxAkwxUr2we3eXQGhpTVzRwy
FLasHXTqrbNvpWFB6grN47HGZfK6pze9HLNTgbukfPSk
FLAshyAyBcKb39KPxSzXcepiS8iDYUhDGwJcJDPX4g2B
FLAsHZTRcf3Dy1APaz6j74ebdMC6Xx4g6i9YxjyrDybR
```

### nextblock (NextBlock): 8 accounts

```
NextbLoCkVtMGcV47JzewQdvBpLqT9TxQFozQkN98pE
NexTbLoCkWykbLuB1NkjXgFWkX9oAtcoagQegygXXA2
NeXTBLoCKs9F1y5PJS9CKrFNNLU1keHW71rfh7KgA1X
NexTBLockJYZ7QD7p2byrUa6df8ndV2WSd8GkbWqfbb
neXtBLock1LeC67jYd1QdAa32kbVeubsfPNTJC1V5At
nEXTBLockYgngeRmRrjDV31mGSekVPqZoMGhQEZtPVG
NEXTbLoCkB51HpLBLojQfpyVAMorm3zzKg7w9NFdqid
nextBLoCkPMgmG8ZgJtABeScP35qLa2AMCNKntAP7Xc
```

### jupiter (Jupiter tx.jup.ag): 16 accounts

```
GGztQqQ6pCPaJQnNpXBgELr5cs3WwDakRbh1iEMzjgSJ
2MFoS3MPtvyQ4Wh4M9pdfPjz6UhVoNbFbGJAskCPCj3h
BQ72nSv9f3PRyRKCBnHLVrerrv37CYTHm5h3s9VSGQDV
6U91aKa8pmMxkJwBCfPTmUEfZi6dHe7DcFq2ALvB2tbB
4xDsmeTWPNjgSVSS1VTfzFq3iHZhp77ffPkAmkZkdu71
CapuXNQoDviLvU1PxFiizLgPNQCxrsag1uMeyk6zLVps
9nnLbotNTcUhvbrsA6Mdkx45Sm82G35zo28AqUvjExn8
6LXutJvKUw8Q5ue2gCgKHQdAN4suWW8awzFVC6XCguFx
HFqp6ErWHY6Uzhj8rFyjYuDya2mXUpYEk8VW75K9PSiY
DSN3j1ykL3obAVNv7ZX49VsFCPe4LqzxHnmtLiPwY6xg
69yhtoJR4JYPPABZcSNkzuqbaFbwHsCkja1sP1Q2aVT5
HU23r7UoZbqTUuh3vA7emAGztFtqwTeVips789vqxxBw
3LoAYHuSd7Gh8d7RTFnhvYtiTiefdZ5ByamU42vkzd76
3CgvbiM3op4vjrrjH2zcrQUwsqh5veNVRjFCB9N6sRoD
GP8StUXNYSZjPikyRsvkTbvRV1GBxMErb59cpeCJnDf1
7iWnBRRhBCiNXXPhqiGzvvBkKrvFSWqqmxRyu9VyYBxE
```

### landx-fra3 (LandX (Cherry Servers FRA)): 10 accounts

```
LandX1EMgYtrfi4jVJ7ryby4mDpZcef6sVH9b9U1cog
LandX2gHE7y6RejuvoLJK4hJiKkrAwcrJJ34u19Gmo1
LandX3uK1cSUF7hbefKo3oL1j4FhvhxitiMRKut99Z6
LandX4wXzvDyWfq1XXn4StRjwPjzqb7je2kqDGLoT9L
LandX5T4jfRASrcn76owxHM4q9bduNGj24ev4Ufc5fP
LandX6RsjjnfaxfYAFTZX1TW9Cgfe9HFStj9nRDd5SK
LandX7LsdzXDAbbyBjAq5FxLTnGQaU3LojGQMLZCvkt
LandX8Gv3UkhjmgKdSEg4F7yG7Z2tiqhNDYDtxazydN
LandX9fhNN5S7fuBgekKBYeYvK1Sy9hbGvDmHsBGYFh
LandXXxDXaSS8MjrqG9nri51htrfM6V4R3zXDVCeV8R
```

### landx-fra1 (LandX (TeraSwitch FRA)): 10 accounts

```
LandX1EMgYtrfi4jVJ7ryby4mDpZcef6sVH9b9U1cog
LandX2gHE7y6RejuvoLJK4hJiKkrAwcrJJ34u19Gmo1
LandX3uK1cSUF7hbefKo3oL1j4FhvhxitiMRKut99Z6
LandX4wXzvDyWfq1XXn4StRjwPjzqb7je2kqDGLoT9L
LandX5T4jfRASrcn76owxHM4q9bduNGj24ev4Ufc5fP
LandX6RsjjnfaxfYAFTZX1TW9Cgfe9HFStj9nRDd5SK
LandX7LsdzXDAbbyBjAq5FxLTnGQaU3LojGQMLZCvkt
LandX8Gv3UkhjmgKdSEg4F7yG7Z2tiqhNDYDtxazydN
LandX9fhNN5S7fuBgekKBYeYvK1Sy9hbGvDmHsBGYFh
LandXXxDXaSS8MjrqG9nri51htrfM6V4R3zXDVCeV8R
```

### speedlanding (SpeedLanding): 8 accounts

```
SpEEdz8S1KorkMZqjMUxfxrmWwofmp6ReNP2Nx6CUmq
SpeeDy3GJM4wcrQmk1itRFWgidvxX4rwjTLMv78wwjE
SPeEdva37vW8vRtqgYjprQs1g3965icfVN5Rt7SMAyh
speEdrSEpox5GUfHWcBc7tQjRuSfUin2yvB7qoYvvJh
SPeEDmkHkN3A2roSZf6aZyEMsmrGqTHKqwP51y2Y4rV
SpeedLdTJXh2RKpXEaP8JCxkWoUVXhtdPQ1EnxBJMxc
SpEediGKLbbXndSYTzwmz6Z3NDgHQLDcTDEvGFkSMH9
speede8xCcUq2Tiv1efXeTuE3k9TDNq8TnGKaKSc6J4
```


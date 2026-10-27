# Frankfurt run 3 — dip bot run report

*10 trades × 0.35 SOL, routes v4 (3 paths)*

> **Verdict:** Small loss (−0.0396 SOL): a quiet hour, two losers (AEQKoc stop-loss −0.0563 after a single −20% trade, 4ZZ5Ke −0.0386).

## 1. Summary
|  |  |
|---|---|
| Result (chain, after every cost) | **-0.0396 SOL** (wallet 4.1156 → 4.0760, Δ -0.0396) |
| Started (PKT) | 2026-10-24 04:15:04 |
| Ended (PKT) | 2026-10-24 05:01:19 — time limit / max trades |
| Ran for | 0 h 46 min of 180 min planned |
| First / last buy (PKT) | 04:24:41 / 05:01:17 |
| Server / wallet | cybershock (84.32.100.36) / `2g7rYv7y…` |
| Buys sent | 14 → **7 filled**, 7 failed on the +5% guard |
| Fill rate | 50% |
| Wins / losses (fills) | 4 / 3 (win rate 57%) |
| Per filled buy | avg -0.0052, median +0.0075 SOL |
| Fills only / failed buys only | -0.0361 / -0.0035 SOL |
| Best / worst trade | CgWwnp +0.0267 / AEQKoc -0.0563 |
| Fill landing | median 35 ms after the dump (seen on our feed); 5 of 7 in the dump's own block |

## 2. Setup
| Setting | This run |
|---|---|
| engine build | dip8 |
| model / tier | IMIT1 strict (score >= 0.5419) |
| size (normal) | 0.35 SOL |
| dev list | off |
| exit | take-profit +5% / stop-loss −10% / time limit 6 slots (~1.3 s) |
| price guard | +5% over the post-dump price (pump error 6042 if exceeded); slot deadline = dump slot + 1 |
| buy fee (priority) | 5M µL/CU × 100k CU limit = 0.0005 SOL per landed buy tx |
| sell fee | 5M µL/CU × 120k CU limit (0.0006 SOL per landed sell tx) |
| route: agave leaders | nozomi + helius + bolt |
| route: bam leaders | nozomi + bolt + landx-fra3 |
| route: default leaders | nozomi + bolt + helius |
| route: fd leaders | nozomi + landx-fra3 + bolt |
| route: harmonic leaders | nozomi + helius + landx-fra3 |
| route: jito leaders | bolt + astralane + nozomi |
| route: other leaders | nozomi + bolt + helius |
| sell path | staked-rpc (retry also via nozomi) |
| near-leader gate | off (every leader) |
| pre-send | off |
| durable-nonce fan-out | off (one tx to every path, every path's tip in it) |
| backup RPC | RMR_RPC_URL |
| holder-reward tokens | allowed |
| limits | max 7 fills, 1 open at a time, 180 min, loss cap 0.500 SOL |

## 3. What changed from the previous run
Compared with **Frankfurt run 2**:

| Setting | FRA run 2 | FRA run 3 |
|---|---|---|
| engine build | dip8 (timing records, near-leader gate available but off) | dip8 |
| size (normal) | 0.25 SOL | 0.35 SOL |
| route: agave leaders | nozomi + helius | nozomi + helius + bolt |
| route: bam leaders | nozomi + bolt | nozomi + bolt + landx-fra3 |
| route: default leaders | nozomi + bolt | nozomi + bolt + helius |
| route: fd leaders | nozomi + landx-fra3 | nozomi + landx-fra3 + bolt |
| route: harmonic leaders | nozomi + helius | nozomi + helius + landx-fra3 |
| route: jito leaders | bolt + astralane | bolt + astralane + nozomi |
| route: other leaders | nozomi + bolt | nozomi + bolt + helius |
| limits | max 5 fills, 1 open at a time, 120 min, loss cap 0.500 SOL | max 7 fills, 1 open at a time, 180 min, loss cap 0.500 SOL |

- Size 0.25 → 0.35 SOL (owner).
- Routes v4: 3 paths per leader type instead of 2.

## 4. Timeline (PKT)
- **04:15:04** engine start #1 (session with 14 buys)
- **05:01:17** big loss: AEQKoc -0.0563 SOL (stop-loss)
- **05:01:19** engine end #1: run end

## 5. Funnel
| Step | Count |
|---|---|
| Dumps the engine scored (≥2% sells it saw) | 2976 |
| Inside the envelope (age / drop / since-buy / size) | 1491 |
| Picks (score above the threshold) | 15 |
| Skipped | max_open 1 |
| Buys sent | 14 |
| Filled | 7 |
| Failed on the +5% guard | 7 |
| Failed (other) | 0 |
| Never landed | 0 |
| Sold (positions closed) | 7 of 7 |

## 6. Every buy
Times PKT. Result: P&L from the chain after every cost (pump fees, tx fees, tips). Failed buys cost the tx fee only.

| # | Time | Token | SOL | Score | Dump SOL / drop | Age | Leader | Result | P&L SOL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 04:24:41 | [D4aHGM](https://gmgn.ai/sol/token/D4aHGMk5KH6WUERR7p6A4H2vm6nE95RcwA6CwhiaTCvD) | 0.35 | 0.56 | 4.29 / −22% | 4.9 s | Jito `5pPRHn` | guard fail | -0.0005 |
| 2 | 04:27:52 | [Arg2bM](https://gmgn.ai/sol/token/Arg2bMP37v7eMG5JypWN7YyLfXWEETvWvU2eVzFvE6Xm) | 0.35 | 1.38 | 5.25 / −21% | 8.9 s | Harmonic `Fd7btg` | guard fail | -0.0005 |
| 3 | 04:28:26 | [GFXU9F](https://gmgn.ai/sol/token/GFXU9Fhc2VuWUGzbykwgpprLTwDxGPrTBda2iAmdpump) | 0.35 | 0.78 | 4.60 / −21% | 22.5 s | Harmonic `JUPiTE` | filled | **+0.0187** |
| 4 | 04:39:59 | [CgWwnp](https://gmgn.ai/sol/token/CgWwnpwwTUwzzwfgivgSdP5Cmp1U6KzBV7Hjj6aSbaux) | 0.35 | 1.02 | 2.84 / −14% | 3.0 s | Harmonic `EJsJx7` | filled | **+0.0267** |
| 5 | 04:40:17 | [92jg98](https://gmgn.ai/sol/token/92jg98RAV1r98ciSDM9Hz6x49Yav3M7DLxj5gSWSpump) | 0.35 | 0.73 | 3.95 / −16% | 1.5 s | Harmonic `Fd7btg` | filled | **+0.0141** |
| 6 | 04:41:01 | [4ZZ5Ke](https://gmgn.ai/sol/token/4ZZ5KeuAy8NZLmm5m5UR6UwXUpXwDua4sQou7fKBpump) | 0.35 | 0.64 | 2.14 / −11% | 3.8 s | Jito `9rkJMA` | filled | **-0.0386** |
| 7 | 04:41:52 | [AHyusb](https://gmgn.ai/sol/token/AHyusbnfKvbDWD6QhK62qmnknUiSdZxerE8c2MHXpump) | 0.35 | 0.65 | 2.00 / −11% | 4.0 s | Jito `ACvL73` | guard fail | -0.0005 |
| 8 | 04:47:24 | [3JtWRx](https://gmgn.ai/sol/token/3JtWRxn7rga879wviiXPbEZAT9pdhMto4ekf4bPzpump) | 0.35 | 0.85 | 4.55 / −17% | 8.9 s | Jito `HEL1US` | guard fail | -0.0005 |
| 9 | 04:47:26 | [2ssK7Y](https://gmgn.ai/sol/token/2ssK7Y32ekqs48BPamgF2DecveoZLL2hghEEBHxbhaJt) | 0.35 | 1.03 | 6.04 / −31% | 1.9 s | Harmonic `Fd7btg` | filled | **-0.0083** |
| 10 | 04:48:33 | [Q1pQm3](https://gmgn.ai/sol/token/Q1pQm3JoLn7V1kbSpo8JBvrmnSyHpwqbYHGSoPiNXiR) | 0.35 | 0.92 | 5.94 / −30% | 1.9 s | Harmonic `Fd7btg` | filled | **+0.0075** |
| 11 | 04:49:52 | [FH4ZtY](https://gmgn.ai/sol/token/FH4ZtYnzu4xAPRdKrMLy6gUp2iBdeqr4HsGeUNdXpump) | 0.35 | 0.57 | 5.47 / −23% | 24.8 s | Jito `3SkE34` | guard fail | -0.0005 |
| 12 | 04:55:13 | [5yHdC2](https://gmgn.ai/sol/token/5yHdC26NGJGGTGTk4BLJZYzJ7wnEdnjgAJne7kT4Xgej) | 0.35 | 0.72 | 4.05 / −21% | 5.5 s | Jito `HEL1US` | guard fail | -0.0005 |
| 13 | 04:56:29 | [9gvD7F](https://gmgn.ai/sol/token/9gvD7FJZimi4XbJbqGDjJyEXwJBHEc347WX8yqnfx3fn) | 0.35 | 0.91 | 6.14 / −31% | 1.5 s | Harmonic `3iSQtP` | guard fail | -0.0005 |
| 14 | 05:01:17 | [AEQKoc](https://gmgn.ai/sol/token/AEQKocd5s9BXTZaoynCwNrKUK7R2G8WewiifdaNLggcd) | 0.35 | 0.74 | 3.42 / −16% | 18.4 s | BAM `CtvdyH` | filled | **-0.0563** |

How each buy landed and was sold:

| # | ms after dump (feed) | Block | Buys ahead | Paths sent (landed copy) | Exit | Sell txs | Links |
|---|---|---|---|---|---|---|---|
| 1 | 125 | same | 3 | bolt+astralane+nozomi | – | – | [buy](https://solscan.io/tx/62HhLNg1YG3JY3Y6qNDJMy3PJeWT4WY96LbirPz2jpua5ziBzutqUgZF3TTdCdaWGcryfi6PByJrvMWZ6kVykrKL) [dump](https://solscan.io/tx/5K9E1VtcnwPdFYZ48e7efVPttm5s5eMb6WEiHy6UhCjJEeHkPibUSqh88YazbqRpBxT6vqRj6vunMHAyq1S6R1BL) |
| 2 | 151 | +1 | 9 | landx-fra3+nozomi+helius | – | – | [buy](https://solscan.io/tx/5QYHKUzvRj38nRkit86dMyFVHaXD96JpHCJidUkaPx6hCifD5nE2QUFoqfPh43Tmzf6xjiPrH4u462X5EXnz3jhF) [dump](https://solscan.io/tx/bDY35gJnAhq2G7dZ7aHoTbHWgNRH1YinyZQYSS4jcf8iK43GrviNCNaz3hHbfTCs316udjh1R22aw6XJ8kDXxpJ) |
| 3 | 35 | same | 0 | landx-fra3+nozomi+helius | take-profit 0.5 s | 1 | [buy](https://solscan.io/tx/2xKSH5NMNbXdn34ZTq5gb919EenfbGjXZg3Rnpdwb3Ehct73ZrLmQM4zsV832EMcggkRMbbdZ179o5DGKCZTG689) [sell](https://solscan.io/tx/3aag8j41KH8RpTe7FhqZEnuPm4z6rXhG8wJmJJeyBxeLTiFLPtXUvAoAy2kqeknjVrKRqNPv17cc5VxbyH2VSMz7) [dump](https://solscan.io/tx/66W9tNsWQ7w9U9aa6jcUGbHHNM8gvGdo9MZdr8RK9V7EMvvQXHUt7c33zzeNBgyGSkDDUDqQKWJr76gkB16mC9i7) |
| 4 | 35 | same | 1 | landx-fra3+nozomi+helius | take-profit 0.5 s | 1 | [buy](https://solscan.io/tx/46YHCNq4EdYYKeEmYsjhA3jYH9WpDM56U39PStuieYhM1EpjB1Y9TvXJrdWRmNeXcxRedNmD7gqM4YJqTd6vYaPb) [sell](https://solscan.io/tx/dJbLwDuUwzZn8xPxPyvbABBfERev6XSxX3xjpzddoT7vtLn3EBUHQfczK62DqoVuztZN5PPEokt2AatZneLPBCZ) [dump](https://solscan.io/tx/2Fyh9nvwudh8CPZo8hecE5qWKqTsh5MGsByVTXhowgpF9QigFETkqvNjxQKyjRRmi87PtbEYGXzEyTQcL1GKTvC1) |
| 5 | 34 | same | 0 | landx-fra3+nozomi+helius | take-profit 0.6 s | 1 | [buy](https://solscan.io/tx/2BuwZ872L7ybfB78YBg5rVkPbmBqoQqVoS9HQD9yaYWhMcSdxNGufAJHE8oov4xbC351RR8kcVeEr6ZU5LmodU32) [sell](https://solscan.io/tx/5qNNaaR16MASWqs6qAJsvzrqT5o9zshz4SFtYwBWJzA4zLKtxBxbgffVHR3PyU2AYm4v3iYwa5fLWHiXbMHWht8t) [dump](https://solscan.io/tx/3gLY5Yt16JxoMJJsyjYQuJ15B2GA6gV5Wom28PM3zFMEj23wpaYxkQhC5xbQL9RrWBaZwPQ1NELqsWyonfVg9ZQi) |
| 6 | 149 | +1 | 0 | bolt+astralane+nozomi | time-limit 2.0 s | 1 | [buy](https://solscan.io/tx/67Yn1Qr34P6KUg5geDtrNBSntT3YEj3CoUndxrnSM5MKfUrTzUA8nkTjfFFx6WRxEyyJ5N2AULjVUyKdN8ZHpD4G) [sell](https://solscan.io/tx/5GpgTEvd4MhXR2WVdbkiQ4s5Mcn22adXhitghRznCXyNKvQek8HYRqPvvPcgcGhgXBakPkVNEK3qkpWHTkKVEGrD) [dump](https://solscan.io/tx/2V1zEtQxzvUrvsEBZS2xASPZjsMu8UgdJrm61tQdR3C8TvBgniMjNhVadou8jbdnnAu1Zc3bvKtYxmK9RK1MsDMy) |
| 7 | 139 | same | 2 | bolt+astralane+nozomi | – | – | [buy](https://solscan.io/tx/2qao5Pag5juyrrHcZ1tEw4NMxDmiwAR6cDUHCnsWEwRvSbZn84VQdwsxvcmoLeK53AbW9n3htNi21YgGg8xGPg7p) [dump](https://solscan.io/tx/3mDm717CTsrkfdJPS2iwXK8NTRF6kaYygCgzrupWbbxC3QZvvBUwnWScM3coJ25TfuvAgmFXhm5BgtRnDaGWn7D3) |
| 8 | 84 | same | 10 | bolt+astralane+nozomi | – | – | [buy](https://solscan.io/tx/5oUjxRFsFnErEd3gzqqxQZqZRc5PTsp2LypwkqReCkcLi7NDW95v9yMjYgwFQ44X71e7fQHrwaAT3cjkWg7FH2aD) [dump](https://solscan.io/tx/5FfeU8fkuTVVRLDYs4fEtkFgK4xKWwMDEZNMCgUDiZ4UQ7ZFVfkJAs88DAesquAXCcY1FwsFXBbfjkukX4jGTJxr) |
| 9 | 39 | +1 | 1 | landx-fra3+nozomi+helius | time-limit 1.7 s | 1 | [buy](https://solscan.io/tx/txw9kgm4TaJ921b7mwF6kky432r8R7gKAGwTpoqkzp4KAk4wG85SDgWomcLqTREKZiXbc1wok5a9af9hxUpxfGZ) [sell](https://solscan.io/tx/4FS3Ed4JZtb3hV4JeKd7sarR1NnkKozhMdNAKrB2infs2PVYw9goBa3iLzdBFh94LvVrRXeGMSu7spsfArunnQpC) [dump](https://solscan.io/tx/bmBQmzE3gZjK5w2FjjD8RJ5XKbxPieHda4pdVEaWyJaMyeuXarZK51utnRoa4kf1oCTariY3enYsMs2aC3nTYnK) |
| 10 | 45 | same | 0 | landx-fra3+nozomi+helius | time-limit 1.8 s | 1 | [buy](https://solscan.io/tx/3ud1V1BHKzkQQ8vshKaporoS9iY39gU2vJuF1xMGpRmDmaLHPnGb1LkGyDqqfaJVwYDNi6Ee6pdNT9X6oMVcsuQ2) [sell](https://solscan.io/tx/Ci9pYzE4QuErWpfDpHjt43CvQ759QkYhuCuLSdwwQBtFmskHejQG9qeAjLL5de3eYJ4SxBMoCDKBFB8CwYxR9ZS) [dump](https://solscan.io/tx/2YiyQLYfTiuzExBQvaanUdCBxz8stFdXUfccccNZ3JGnEHtRKArsZXoJDZ46Gv8WNz14cfCCt55xgrtuxsVrd52K) |
| 11 | 39 | same | 6 | bolt+astralane+nozomi | – | – | [buy](https://solscan.io/tx/2h7QLkamkSFkoyoUCDK8GBzS7ADPeofnQLRLvAJXSrm8kxfMSugNVEUanaBzQaDABJL3wsq9idopVn8bpXHL5QzD) [dump](https://solscan.io/tx/2K5L1PSJLSpjmBFi28b5PHi9m6eViCwJgVDng91f7RCdMDe3cREpG5EJa41iiAc6JQ7y34fzJ6DxBhjLBEtRhNvr) |
| 12 | 113 | +1 | 5 | bolt+astralane+nozomi | – | – | [buy](https://solscan.io/tx/jyQdjijXiuK69vNnUxyghhJjPkvaR55hQFraXyQFwtwmvT13Np9ve8CW7WkcMoKPmJP1QtpVb2fhZE53kKLATk8) [dump](https://solscan.io/tx/vq5vY3TBZdpVR1AUr7bZKDUE2rkE8nS9h8qCR3f25GBCGTasTsRwu1h4pXLCyMZeJ65mKjMAa6WrVyEoiD99W7J) |
| 13 | 93 | +1 | 7 | landx-fra3+nozomi+helius | – | – | [buy](https://solscan.io/tx/3fZ69j7KbQX8TuPJ6yMTwSKmM5bpV8sEyALPDktfVkaURCeCzFbVnQyrbtpkuGLHYmMYLkAnDYF73Js9Vba2Gqfk) [dump](https://solscan.io/tx/53wP7qEputpZxJBRpjrGCrGcTEL8nTVYxzJGphdDzahgNmGgMm1rSbk3K6hFX1C6ADKFkRN6JvHktdLjcVCi8zzB) |
| 14 | 33 | same | 2 | landx-fra3+nozomi+bolt | stop-loss 1.5 s | 1 | [buy](https://solscan.io/tx/53g65GM2sG2ax9Zxyta3rCK3XTG5TGvm7HUZMkAsXqbey7ZCPgnnqgoeGAtZiZB1LC7K3iEwB2njGDE7S5MfGrVR) [sell](https://solscan.io/tx/4ZUqMmPZDbyXry2wUhCZrCsRUGqZJyusw9w4YViQcS8opPET7X3mhtsCuvoHqTbFXhCtgxTH4yAtDa7QZuA1QFXH) [dump](https://solscan.io/tx/2yoet57sUqUfM1vzZHdtzesA3utMX287U1oQaUiqwCCQR7Njfw3YaMybWDYbdECuc6MSSVoyAoCFDm4QfA2zcFYb) |

## 7. Breakdowns
**By leader type:**

| Leader type | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| Harmonic | 7 | 5 | 71% | +0.0578 | +0.0118 | 4/5 |
| Jito | 6 | 1 | 17% | -0.0411 | -0.0386 | 0/1 |
| BAM | 1 | 1 | 100% | -0.0563 | -0.0563 | 0/1 |

**By size tier:**

| Size tier | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| normal | 14 | 7 | 50% | -0.0396 | -0.0052 | 4/7 |

**By landing block:**

| Landing block | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| same block | 9 | 5 | 56% | +0.0087 | +0.0022 | 4/5 |
| next block | 5 | 2 | 40% | -0.0484 | -0.0234 | 0/2 |

**By hour (PKT):**

| Hour (pkt) | Buys | Fills | Fill rate | P&L SOL | Per fill | Wins |
|---|---|---|---|---|---|---|
| 04:00 | 13 | 6 | 46% | +0.0167 | +0.0034 | 4/6 |
| 05:00 | 1 | 1 | 100% | -0.0563 | -0.0563 | 0/1 |

**By exit reason (fills):**

| Exit | Fills | P&L SOL | Per fill | Median hold |
|---|---|---|---|---|
| take-profit | 3 | +0.0596 | +0.0199 | 0.5 s |
| time-limit | 3 | -0.0393 | -0.0131 | 1.8 s |
| stop-loss | 1 | -0.0563 | -0.0563 | 1.5 s |

## 8. P&L leaders
**Best trades:** CgWwnp +0.0267 (Harmonic, take-profit, score 1.02); GFXU9F +0.0187 (Harmonic, take-profit, score 0.78); 92jg98 +0.0141 (Harmonic, take-profit, score 0.73)

**Worst trades:** AEQKoc -0.0563 (BAM, stop-loss, score 0.74); 4ZZ5Ke -0.0386 (Jito, time-limit, score 0.64); 2ssK7Y -0.0083 (Harmonic, time-limit, score 1.03)

**By slot leader (validator), best to worst:**

| Leader | Client | Buys | Fills | P&L SOL |
|---|---|---|---|---|
| `EJsJx7Sm` | HarmonicFiredancer | 1 | 1 | +0.0267 |
| `JUPiTERr` | HarmonicFiredancer | 1 | 1 | +0.0187 |
| `Fd7btgyS` | HarmonicAgave | 4 | 3 | +0.0129 |
| `5pPRHnie` | JitoLabs | 1 | 0 | -0.0005 |
| `ACvL73V4` | JitoLabs | 1 | 0 | -0.0005 |
| `3SkE34PV` | JitoLabs | 1 | 0 | -0.0005 |
| `3iSQtPgk` | HarmonicFiredancer | 1 | 0 | -0.0005 |
| `HEL1USMZ` | JitoLabs | 2 | 0 | -0.0010 |
| `9rkJMARq` | JitoLabs | 1 | 1 | -0.0386 |
| `CtvdyHYt` | AgaveBam | 1 | 1 | -0.0563 |

## 9. Speed and landing
| Measure | Median (p25, p75, n) |
|---|---|
| Decision (dump seen → buy sent), µs | 1077 (p25 745, p75 1368, n 14) |
| Executed-feed lag behind first sighting, ms | 1.9 (p25 0.9, p75 4.2, n 13) |
| Buy sent → our tx seen on the feed, ms | 82.0 (p25 35.3, p75 121.5, n 13) |
| Fills: our buy seen on the feed after the dump, ms | 35 (p25 35, p75 39, n 7) |
| Guard fails: our failed buy seen after the dump, ms | 113 (p25 93, p75 125, n 7) |
| Fills in the dump's own block | 5 of 7 |
| Guard fails in the dump's own block | 4 of 7 |

**Send-path answers (FAST-ACK lines):** nozomi 14 (median ack 0.4 ms), bolt 7 (median ack 0.3 ms), helius 7 (median ack 0.5 ms), astralane 6 (median ack 0.3 ms)

## 10. Who got in ahead of us
Buys by other wallets between the dump and our buy (fills: by block position; guard fails: by arrival on our feed). `*` = a wallet in the 462-wallet winner cohort.

|  |  |
|---|---|
| Fills: rival buys ahead (median) | 0 |
| Guard fails: rival buys ahead (median) | 6 |
| Guard fails: rival SOL ahead (median) | 3.03 |

| Wallet | Ahead of us (buys) | …of which on our guard fails |
|---|---|---|
| haqq (dip bot) | 6 | 6 |
| HkQ7 (dip bot) | 4 | 3 |
| 5yNBPneF | 2 | 2 |
| 5PuQCemC | 2 | 2 |
| DzRqREhH | 2 | 2 |
| CS93HDW8 | 1 | 1 |
| EprLoV21* | 1 | 1 |
| 2UYEBF1w* | 1 | 1 |
| 7PedQZmc (untipped fast) | 1 | 1 |
| AEgTuy8L* | 1 | 1 |
| 9DW4QLas* | 1 | 1 |
| GC6jyQ25* | 1 | 0 |

## 11. Costs
| Item | SOL |
|---|---|
| Curve P&L of the fills (before any cost) | +0.0610 |
| Pump fee on buys | 0.0302 (0.0043 per fill) |
| Pump fee on sells (residual) | 0.0310 (0.0044 per fill) |
| Buy tx fees (base + priority) | 0.0035 (0.00051 per fill) |
| Buy tips | 0.0210 (0.0030 per fill) |
| Sell tx fees | 0.0042 (0.00060 per fill) |
| Sell tips | 0.0070 (0.0010 per fill) |
| Failed buys (tx fees) | 0.0035 (7 buys) |
| **Result** | **-0.0396** |

Buy compute used (fills): median 76,907 CU, max 81,404 CU (limit 100k).

## 12. Health checks and red flags
- ⚠️ 7 POLL-RPC-ERROR lines (exit-path reads that failed on the primary RPC)
- ℹ️ RPC bh-fallback getLatestBlockhash: slow minutes (worst p99 555 ms, max 638 ms)
- ℹ️ RPC bh-fallback getSlot: slow minutes (worst p99 554 ms, max 634 ms)
- ⚠️ big loss AEQKoc -0.0563 (stop-loss, BAM)
- ⚠️ AEQKoc: the stop-loss was hit by a single −20% sell before our sell could land (−0.0563)

Checks passed: every filled position was sold; fast-verify: 0 identical, 0 MISMATCHED.

## 13. Fixes and follow-ups
**Done after this run:**

- Miss analysis (30 guard misses): the price crossed our guard a median 45 ms after the dump; we needed to be ~34 ms earlier (10 ms earlier → 2/30 would fill, 30 ms → 12/30).
- Competitors: HkQ7hMjy fails ~70% of buy attempts too (failed attempt ~0.000135 SOL vs our 0.000505); ALL top bots use a durable nonce with one copy per relay (6–9 paths) + a no-tip copy → one tip per landed trade (built later as dip10).
- haqqiUUX sizing tiers 0.25–0.75 SOL; our backtest: per-fill % barely drops from 0.35 to 0.75 SOL.
- Probe E: nozomi 35 ms, staked-rpc 42 (tipless, 7/8 same slot), helius-swqos 58, bolt 60, helius 65 → routes v5 (nozomi core + helius-swqos + tipless staked-rpc everywhere).

**Recommended / open:**

- Run 4 with routes v5.

## 14. Data and how this report was made
- Engine records: `/root/prod/runs/dip_r3.jsonl`, log `.log` on cybershock (84.32.100.36) (local copy `/home/moiz/sniper-data/runs/fra/runs/dip_r3.*`).
- P&L: the engine's REALIZED lines (computed from the chain transactions) for fills; failed buys from getTransaction; costs split from the chain tx fees, the engine's tip records and the curve amounts (sell pump fee = the remainder).
- Engine sessions in this run: 1; refused starts: 0.
- Generated by `ops/dip/report/make_run_report.py` at 10-27 14:56 PKT.

I couldn't save the report: the harness blocks agents from writing `.md` report files. The full text is below for you to save as `/home/moiz/sniper/ops/strategies/e2x1_dissect/exec/REPORT.md`. Every number comes from the tables in `/home/moiz/sniper-data/e2x1_dissect/exec/`. One correction to the brief: recon's "every tx on a durable nonce" is not quite true; the Helius copy with the 0.001 tip has no nonce.

## 12-line summary
1. **Speed:** he is not faster than us. On our dump definition he lands 44 ms after the dump (72 % same slot); haqq does 45 ms, our pre-send fills 20 ms (97 %), our older reactive fills 25–35 ms.
2. **How he gets same-slot fills (inferred):** a streaming feed (shreds or processed txs) plus four regional engines. The nonce-account seeds name the regions: fra, euw4 (Netherlands), use4 (US-East), asse1 (Singapore). Each engine buys on leaders near it, which matched in 53 of 64 sampled buys. Reaction time ≈ 60 ms; 0.8 % of his same-slot buys land within 10 txs of the trigger.
3. **Relay:** which copy lands follows the leader. Helius wins on BAM (87 %), astralane on Harmonic, Jito and Firedancer (81–95 %). Neither relay is faster on the same leader.
4. **Failed duplicates:** 519 in D1, 0.043 mSOL per lot. Each order is 2 copies on one durable nonce plus 1 Helius copy on a normal blockhash. When both kinds land, the second fails: sells with error 3012, buys with IllegalOwner. The account-creation step stops a duplicate buy from filling twice.
5. **Exits:** always one full sell, never partial. GRAD (sell on PumpSwap ~48 slots after the token graduates): 22 lots, 21 wins, +17.8 SOL. 30-minute timeout: 96 lots, −9.1 SOL. The rest are not a simple tape rule: the best of 90+ rules matches 19 % of his exits and makes +14.8 vs his +42.7.
6. **The exit is a signal on the token, not on the position:** Grozoe exits in the same slot 92 % of the time even when it bought 50+ slots apart, and either wallet sells first about half the time.
7. **Our 200 ms exit on his own lots** makes about +1.0 SOL in D1 (+7 in D0) vs his +60.5 (D1). His money is in the hold and exit, not the entry speed.
8. **Cost:** he pays 2.05 mSOL per lot (0.44 % of size); we pay 2.53–2.89 mSOL per fill (0.56–0.64 %). Our extra cost is the failed pre-send tries (0.5–0.9 mSOL per fill). Cost is not his edge.
9. **Grozoe is a twin engine:** same size code (size ratio 0.99), same tips, same exit moments. Both wallets created their nonce accounts within 5 minutes on 10-21 with the same seed names. Inferred: same operator or same software.
10. **No funding link found between E2x1 and Grozoe:** Grozoe was funded by DA9nTGVx… on 10-14. Public RPC history for E2x1 only goes back to 10-19 and starts with a trade, so its funder is unknown.
11. **The followers are copy-traders of his wallet,** not his own wallets: 11 wallets buy after him and sell after him. They are linked to each other (FiYZPb… was funded by 8VqKtt…, another copier), not to him.
12. **Copiers add +8.2 SOL in D1 (+10.2 in D0), about 20–25 % of his curve profit.** Without them he still makes +34 / +30. Unlike haqq, his profit does not depend on followers.

---

# E2X1 exec: landing, failed copies, exits, cost, sibling and copiers (agent "exec", 10-28 ~21:00 PKT)
Wallet E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb. D1 = 10-27 20:00 → 10-28 20:00 PKT; D0 is the check day. M = measured, I = inferred.

Code is in this folder (x0–x13, xlib.py). Tables are in `/home/moiz/sniper-data/e2x1_dissect/exec/` (x1.txt … x13.txt, funding.json, nonce_origin.json).

Clock: "ms" is the chain clock used in the haqq exec study (t7), so his, haqq's and our numbers compare 1:1. One slot = 212 ms. Position inside a slot = tx index divided by the block size (largest pump tx index in the slot + 1).

## 1. Landing (x1, x2, x12, x13)

**Trigger T (the trade his buy size was computed from) → his buy. D1, 1,010 lots with a trigger; D0 is nearly identical (69 ms, 61 %):**

| group | n | ms p25/50/75 | same slot | next slot | ≥2 slots |
|---|---|---|---|---|---|
| all | 1010 | 44/68/111 | 61 % | 37 % | 2 % |
| leader Harmonic | 288 | 38/57/96 | 68 % | 29 % | 2 % |
| leader Firedancer | 44 | 35/51/79 | 66 % | 34 % | 0 % |
| leader Jito | 263 | 43/71/115 | 55 % | 43 % | 2 % |
| leader BAM | 392 | 51/76/123 | 58 % | 40 % | 2 % |
| landed copy: astralane | 585 | 40/60/98 | 64 % | | |
| landed copy: Helius 10k (nonce) | 365 | 50/76/123 | 61 % | | |
| landed copy: Helius 1M (no nonce) | 60 | 49/102/272 | 27 % | | 20 % (I: a later re-send) |

**Which copy lands depends on the leader (M):**

| leader | astralane | Helius 10k | Helius 1M |
|---|---|---|---|
| BAM | 10 % | 87 % | 3 % |
| Harmonic | 90 % | | |
| Jito | 81 % | | 14 % |
| Firedancer | 95 % | | |

- On the same leader the two relays are equal (BAM: astralane 76 ms, Helius 75 ms).
- So the speed gap between copies above reflects which leaders each relay wins, not a faster relay.

**Reaction inside the slot (M):**
- Same-slot buys sit 47/70/109/180/270 txs after T (p10/25/50/75/90), a median of 57 ms.
- Only 2.8 % of his same-slot buys are within 25 txs of T, and 0.8 % within 10.
- His chance of landing in T's own slot drops as T sits later in its block:

| T's position in its block | 0–20 % | 20–40 % | 40–60 % | 60–80 % | 80–90 % | 90–100 % |
|---|---|---|---|---|---|---|
| he lands in T's slot | 86 % | 82 % | 73 % | 49 % | 15 % | 1 % |

- The pattern is the same on every leader client:

| leader | T in first half of block | T in second half |
|---|---|---|
| BAM | 80 % | 36 % |
| Harmonic | 88 % | 42 % |
| Jito | 79 % | 30 % |
| Firedancer | 78 % | 31 % |

- When he misses, T sat late in its block (median at 77 %) and he lands early in the next block (median at 16 %).
- Inferred: he sees T while the slot is still being built (shreds or processed feed) and needs about 60 ms to land. There is no sign of a sub-10 ms colocated reaction.

**Four regional engines (M, from the nonce-account seeds):**
- Nonce accounts are created as createAccountWithSeed(E2x1, "fbn-<region>-NN"). I decoded all 16 sampled ones (two needed an RPC lookup):
  - fra-00…04: 5 accounts
  - euw4-00…03: 4 (GCP Netherlands)
  - use4-00…02: 3 (GCP N. Virginia)
  - asse1-00…03: 4 (GCP Singapore)
- All were created 10-21 12:19–12:24 PKT. Each lot's buy and sell use the same nonce account, so one regional engine owns each position.
- Engine region vs location of the buy slot's leader (sampled buys):

| engine | leader location (matches / sampled buys) |
|---|---|
| use4 | N. America 17/17 |
| fra | Germany 17/22 |
| euw4 | Netherlands 11/14 |
| asse1 | Asia 8/9 |

- His D1 buys by leader location: Germany 456, Netherlands 300, other EU 206, N. America 222, Asia/other 154. About 28 % are on leaders outside Europe.
- Trigger → buy by leader location:

| leader location | ms p50 | same slot |
|---|---|---|
| Germany | 55 | 69 % |
| Netherlands | 59 | 71 % |
| other EU | 62 | 69 % |
| N. America | 104 | 44 % |
| Asia | 147 | 27 % |

**Head to head (same definition: the previous outside trade is a sell ≥0.5 SOL at most 2 slots earlier):**

| who | n | ms p25/50/75 | same slot |
|---|---|---|---|
| E2x1 D1 | 141 | 22/44/70 | 72 % |
| E2x1 D0 | 150 | 25/46/70 | 71 % |
| haqq (haqq t7) | 10,181 | 27/45/83 | 68 % |
| ours: pre-send fills D1 (FRA r27 + r28 + AMS r28) | 281 | 9/20/35 | 97 % |
| ours: older reactive fills (haqq t7), FRA / AMS | 98 / 76 | median 35 / 25 | 74 % / 71 % |

- Same definition by leader location, his ms p50: Germany 31 (83 %), Netherlands 46, other EU 45, N. America 52, Asia 54. Ours (pre-send): 16–21 ms in Europe and N. America, 32 ms in Asia.
- Our D1 runs fired no reactive buys, so there is no D1 reactive number. The brief's "60–90 ms" uses a different (wall) clock.
- Only 2 cases where he and we bought right after the same trade; we landed first both times:
  - [BbX57QDp](https://gmgn.ai/sol/token/BbX57QDpvdZ9adfTFGh831GFanAJoFi6Xa3q6LCEpump): [ours](https://solscan.io/tx/2q3MqTJDkYCyaZufBwNqM6R3B6vDHq9PKaMuMSWGyMZ9iB9Ed79QtorQSzkAXYVqqaSNFBwj1vyJa5WAJKbE77Yg) +24 ms vs [his](https://solscan.io/tx/WqR9TZ3wHvUMiGYrsSB9qRwjHUG4LHXUBKmKhNfJZb2PW8ea7iQj13DKncAEuwhDFzhjkT188keLua66XJ38Pcf) +43 ms.
  - [DB8JVSaY](https://gmgn.ai/sol/token/DB8JVSaYmZ44NoZMYV6bAZJMqwzcYxmkub7db5Sepump): [ours](https://solscan.io/tx/47GiU4sPuc9JEpzThebVhdpPsFuGJF99Gkh6yrD2MBF2bWHtTdWa2i3AR7m2q26wC3hZ4A1ryJir7EvHJYxL45KW) +29 ms vs [his](https://solscan.io/tx/2i4xsoRYsy1Phwa4zEYdZogFi1oKVatUQXx4BCeYAQqr5ADtnN4XxaK1sp8V5427BGkEc82jBB85DUYtR3nNmk1q) +221 ms.

**Examples: same-slot landings (T → his buy):**
- [9Zrgjenf](https://gmgn.ai/sol/token/9ZrgjenffwiujsYdVN8FJiGKkDP9XQ3gvh8u2fHmdEEr): [T](https://solscan.io/tx/xJKsxDyabpXbomRWwmsWu4nQ9Gj7d4BD65MA41xgEZkqGwERy8jPW4k8nNrBCNjKtVhvNzrVygSrXvapZLM2cFh) at index 137 → [buy](https://solscan.io/tx/53CxmmCFtMQ7viLk2WrNbFnZTF1JV43ra4nqwmt9Vaj3URPAPfdbRBLGRJ1t4Ur9ts9J9Q4j5yJadaJrfbPnWznx) at 263, 77 ms, BAM.
- [5SKjVwpQ](https://gmgn.ai/sol/token/5SKjVwpQygiqax9WSEHc8JPGbxxy2E9NdPFqVYFkdibs): [T](https://solscan.io/tx/ptVQm3Ty7tzWFno389EJH9dyfVHL2chMA3nsxmkC43aXhW8KC8nCW4hpQznk4BG2ie7W37EDubzyRN4xrcoG5WK) → [buy](https://solscan.io/tx/2LuMAdp5dgtpHH4muGyEqTfCcBcKuyWqCnJwM2L6hsQ53dfjebFn3AuEJ8n68ts5vrst1WGLwkBthV61A8rjcQu9), 102 ms, Jito.
- [5rd1Y9Go](https://gmgn.ai/sol/token/5rd1Y9GonhvnKszqPv5VqvSVGzY6J597cRNqHy1Rpump): [T](https://solscan.io/tx/mDNfpifcoiDSmJhX7pde54DxEfhdZi7uq7nvnXJJJ8HTsjK8zvSMPDSMX8iJP6fHvdkdV9VuLDi7HSveKg3LUSQ) → [buy](https://solscan.io/tx/3pFp5xrDWz6tdAkS2G7dZMHuhsP8Mqa2TLsaDiytyK2Bv3rSMz4ps6nfEX4GAyWyY5QXK3RAVGF1MZXdYKDgfGPQ), 49 ms, Harmonic.
- [B78HYcTx](https://gmgn.ai/sol/token/B78HYcTxycWGM9P6q1QmQUi3Byo83XJC5jyzZ5aRQocd): [T](https://solscan.io/tx/5A1ZpZaEEt3a1YSbDXSRWksbNf4AL2zeNoR4DVBZhgXUTzCgjgnPD36sWmb34ZgavM1APJo41AtmgkLsZUMaCZ3C) → [buy](https://solscan.io/tx/2gUgJrstypQc5YGVuqDo58tYLbxrpMtvbqQm3WenxPFwJBSYyeuGtwRgEw8jjeRS2RZytnRV7eeTC7Y2wir1A5Yo), 99 ms, Jito.
- [CPtf6VxX](https://gmgn.ai/sol/token/CPtf6VxXV6rzn8G5g9ffpi34ZXMZxfXZS9F1m4zYpump): [T](https://solscan.io/tx/S8DzXXjzF1RmKJ7JJ2aTEkq2TiborwXsP5Hgg8vppimMPgrTVnPDhxSE3GpB1hMDgoh6mEeVvQyTjqb2oH2fN1U) → [buy](https://solscan.io/tx/526f3coE6h2xEY4aWRLpJxKtJpyGTDVTD2ecEh2EcA8bjAKAhNXSLy7PGosUezGVF1S6AtDrMeAfZV4m1h6eWkgu), 69 ms, BAM.

**Examples: next slot when T was late in its block:**
- [D8kYnQkK](https://gmgn.ai/sol/token/D8kYnQkKeLThRHhNGcDBFNaeCibtvHkFPZ2THHGxpump): [T](https://solscan.io/tx/5ZB7z4myc9zvCycxgpvvdSFrbcTwZUwt5G4hhRrvFXzQ5KULgxEH6VVUDhdyHumnAQ3uN5eNQdKBYokv9ruW212W) at 84 % → [buy](https://solscan.io/tx/yuWm14cMPKrr8Rc8atchAq56CYL8DWqKTxP3hnDnBF82qpgiPLW13z4UJLgHAA1BhobjnPUzGRW1WS6ZmAU4SyE) at 14 % of the next block.
- [HjacGnbL](https://gmgn.ai/sol/token/HjacGnbLDFm4Jct9q49m5JQQ9USYytiHqvpQxs2pump): [T](https://solscan.io/tx/2ZsEu5XYD6sCmWmRtWqgrmmXPQ2sSKYLtPhdNFs6inSPrzqiHw99mtgbrS8WAxBaxb5EZHmP5CxmwVYxTj3am3cT) at 93 % → [buy](https://solscan.io/tx/4cxSa56rgYwb5cTMHeKUumG1d7JgYNp4LMTCi3cvUMLkq9pzy5z8pj6cbMj4jKdwKFHAZEmbaVUPPuTSnh3bNRiu) at 26 %.
- [AWFzp7Uj](https://gmgn.ai/sol/token/AWFzp7UjjX4r59Z9MfQWrRouMDtW94gzXoNidEVZavnz): [T](https://solscan.io/tx/31BQXDdHqCtc4PjLYGKyzoBU9fiiQbzUehoChCVK8a1hKcx1GdwWruom11pCt6weRd5Gj9zHRHcAGY8iAx1xgJ9D) → [buy](https://solscan.io/tx/5GgiGDvrPtZ6VpUt29GVDQcs9axzfWqbbSWmNfjoAsX3G3npAanuJmcZcUCRXjRB77VyF663AuvPYXdJQcQ9TLYc).
- [4fnKiLpG](https://gmgn.ai/sol/token/4fnKiLpGvWCvUjjE8fc1XXjDEV72azS54Wpu7n1Vpump): [T](https://solscan.io/tx/4AjKyTEHDWkLAUKjvyMkW9bhhRsYehkvAVy3ndy5HBA6Z2ZMLZ9jnBhdeAWeBVkwj65zQEgihywokRLat5Cwxd3q) → [buy](https://solscan.io/tx/DR36JovFbarZJDbq4o3pcFuftW4bXfhQmh6nKSjQvaQC2jUVrrizp4TPgsYndqHCQBrHq7XhvbUbKuj1TFYhABQ).
- [9Vv3Q7Hu](https://gmgn.ai/sol/token/9Vv3Q7Hu9C2hrRfcdzeo4nLCKDM9go7Agz2MJD5Npump): [T](https://solscan.io/tx/5hvXWgVdeur4gmT5HvpyRj1gupmz8dphfjpmzQ1qEirAfAYwbu4n8e7XeXV8MDu8zzYekfMt7LgiUwngbwTt87KH) → [buy](https://solscan.io/tx/5MydD25C8BVRqgCJt29JnVfhPWsAduADGi9sEX8nLKi87fenDyVapLG1rSdAMHcpaCbXjCjXHnPfRfsZ4VoH2qXJ).

The rare very close ones (≤25 txs after T) are listed in x11.txt section C, e.g. [GYexMgsi](https://gmgn.ai/sol/token/GYexMgsiepGqRVuovTgwffJqiLcYyCkctQa689j6pump) at +7 txs and [DqedPSxK](https://gmgn.ai/sol/token/DqedPSxKL5VMthfED7u2WiqWDTNsVYhNJkndgdt6pump) at +4.

## 2. Failed duplicates (x3)

**D1: 519 failed txs costing 0.05785 SOL = 0.043 mSOL per lot; 211 lots have at least one. D0: 585 failed, 0.049 mSOL per lot.**
- A failed tx pays only its fee: 0.105 mSOL for a sell, 0.15 for a buy. The tip transfer reverts.
- How the copies work (M, RPC sample):
  - astralane (tip 1.1M) and Helius 10k are durable-nonce copies on the same nonce. Only one can ever land; the other is dropped and never reaches the chain.
  - Helius 1M is a copy on a normal recent blockhash, with no nonce (5 of 5 sampled buys, 4 of 4 sampled sells).
  - If both kinds land, the later one fails.

| D1 error | count | where it fails | what happened |
|---|---|---|---|
| sell 3012 | 359 | instruction 2 (no-nonce layout) | the no-nonce copy landed after a nonce copy had already sold and closed the token account |
| sell 3012 | 72 | instruction 3 (nonce layout) | a nonce copy landed after the no-nonce copy sold first |
| buy IllegalOwner | 58 | instruction 3 (create token account) | the no-nonce buy already created the account, so the second buy is blocked: a built-in double-buy guard |
| buy 6042 | 12 | instruction 4 (the buy) | same pairing |
| other (6023 / 11 / 6005) | 17 | | |

- Of 69 failed buys, 59 sit next to a landed Helius 1M buy. Relative to the good tx, failed buys land in the same slot 44 times and one slot later 10 times; failed sells 217 and 173 times.
- Examples:
  - [2xLHdgnv](https://gmgn.ai/sol/token/2xLHdgnveg8kGDdtNtLyucKnqT1tEhRuU4uvteiXpump): [IllegalOwner](https://solscan.io/tx/32jQDnsFk6qkzdUncqh3D3cUkhpmY83ibH39jj48fhaKHqT56WJZavXMYBZaSjY1N4FkfcboA9HJJ4ahX2oFzxM3) next to the [landed buy](https://solscan.io/tx/4BN18FKKwtjoWxfvAwnwKX1Y9i26D2R2EaCamXRxbVaQFfkdbmjKQpaxe6UVnsiA14C9X7qE6FhKbuzxF2cL9DyP), plus a [3012 sell](https://solscan.io/tx/5GCYk39WokDwXutx4YUtm955Acn4DoFKJ6V5VDB2nz66nMtLUZvMX97QF4JCzWZUJgn7kKKrRWph2kHQUxRJEgUV).
  - [4d7PW4vs](https://gmgn.ai/sol/token/4d7PW4vsGcfvZVxmc87eQ9aAgWbdq8cqGQZWdMLgh2PS): [6042](https://solscan.io/tx/gq9MXr26Rh7Y4fbojeYxpC8SjxZqePWMuDLDrHoaq3DBGGdoYSXN1xEeE7qVjD6JjeAPBYQpbpR7BwkJapPM4TN).
  - [5P7Z76mA](https://gmgn.ai/sol/token/5P7Z76mAjYNre4tWitwVAbxaK8QoAguHhpXy7Uh5pump): [IllegalOwner](https://solscan.io/tx/p2io5vSKZHTNRE8EL461JDBP46e5JAEpNuBgjtVVSywdsu1aHhJ5SCniyNBT7ktDVAHA7HG7Ur8YPQPtEsCRGZw).
  - [APybGHr2](https://gmgn.ai/sol/token/APybGHr2TxNwJ1ioaWAtStqiSivB2tcXVZMQmFuupump): [6042](https://solscan.io/tx/4hRohVFwy6veSzBCSAngiBwst99PSDY2NmG47D8qeiP9QT9e5MCeC65DdFqCEM26M72ZFNM9u85aogRVP5gmij3a).
  - [FuGEkeTo](https://gmgn.ai/sol/token/FuGEkeToNUSWpMFPnW94fCG9FSHfinfFuG6K6vD6pump): [6023](https://solscan.io/tx/47so8s3UyzBjn7pzvi9kGActypKJNUAAdkuAZSszaXhypmHP9s2J9z1Uwtf4LAQmKAmwZewP5QLiy4GtRFk6aSHG).

## 3. Exits (x4–x8, x11)

**Shape (M):** every lot closes with one full sell (D1 1,340 of 1,340; D0 1,321 of 1,321), with no minimum price on the sell.

**His D1 P&L (+59.3 SOL) by exit type:**

| exit type | lots | P&L (SOL) | notes |
|---|---|---|---|
| GRAD: token graduates, sold on PumpSwap | 22 | +17.79 (21 wins) | 17 of 22 sold 44–50 slots (~10 s) after the last curve trade; D0: 11 lots, +12.04 |
| TIMEOUT: sold at 1,800 s | 96 | −9.13 | median price at exit ×0.70 of entry |
| all other curve exits | 1,222 | +51.8 | no simple rule (below) |
| still open at the end (marked) | 4 | −1.13 | |

- GRAD examples:
  - [DzfDFonC](https://gmgn.ai/sol/token/DzfDFonCVcF4zygAFPRZpf85Pw7EUKwKWETmfsbzpump) +3.05, [sell](https://solscan.io/tx/yVEEfuXzwwv7jjnPTazGppbFLkcbG53eotK7G7X6DTXfp1eYHWX3pxycgnS4mJUUzjJWHNH54h7TsWRsdFhdGJv)
  - [HjVGL4ku](https://gmgn.ai/sol/token/HjVGL4kuW2H6eeY2sTxwp5VCUhCJChzZBHc3aQ3EMKRS) +1.81, [sell](https://solscan.io/tx/4PnZX9KsZjVsu4yeJvxTCkVfu6dhgBr8K1ZFpscVYSk24nNTBzgmxjp9Fg44gWYS5e8BeQAF2wBdrnL52swLy7aB)
  - [GJyNrRBN](https://gmgn.ai/sol/token/GJyNrRBNt85m7DX7PYJBHo9sjmpTxMEQYfRbvMoYpump) +1.80, [sell](https://solscan.io/tx/22Z9nz6HEJCUZSJ5YJzpZ5QeSV1yvHZKGvVcApD96Dre8yCLS1qrnxPxR6gc7B8JTLoHLFAEwKza8aZuuMGE4oqC)
  - [DA4yHG5X](https://gmgn.ai/sol/token/DA4yHG5XdywG7ZSAWffKZet3cH7JQamjEJwRC3vVXN5X) +1.63, [sell](https://solscan.io/tx/26sPMTHpzeQwYpwUSgD4X9VS1eWPi2JcKdJ9ps8yciiDtUpPRLWFEHRur1a5fQFYi8ALAbmDx5zXNdzBdp5dCWSL)
  - [DDgEb1Ay](https://gmgn.ai/sol/token/DDgEb1AyoqR81NNTJX44AgpfYkbnWAegf4BrxP1Bpump) +1.33, [sell](https://solscan.io/tx/7gtbtVDmX6cQGB3i1Q8Te3fR2X1PzWTe9WW8S4LqS1Dq62pnzXfzobSQTW24z6DHvBu72cfZWBSUEVWqayHLgUx)
  - Many OLD buys are made at curve vSOL 90–108, close to graduation. Which tokens he picks is the "select" agent's topic.
- TIMEOUT examples:
  - [BZRMQH74](https://gmgn.ai/sol/token/BZRMQH74sDMKWRT8MePCyjNsoRWrbe32zhT47tzjpump) −0.126, [sell](https://solscan.io/tx/5DJWwMr7NDEfhtsb9zKuXeyNtHcdRVa8nCmsRQdMH8AhpvawJyJ6fdydPYY93GKF9k8y7ixEdwxWWJ2Sbq5SDinZ)
  - [6DF1kU7L](https://gmgn.ai/sol/token/6DF1kU7Lsf6SMBNrWQuagmeoRu7iRXbtnYTfvBDNpump) −0.254, [sell](https://solscan.io/tx/5hz1qkeJEhjNx5Ewp8UYbG6zZ28BiPiTrBYSRtzeRuA6yQAn6WGjDUUTfM4AepUzzCTk1rYsRdhSWavVfhd2f9V9)
  - [CihTYuzu](https://gmgn.ai/sol/token/CihTYuzuDfkCAtmDY1zpcQGmDCzMnLNrK9QmzNLspump) −0.098, [sell](https://solscan.io/tx/3kJL7cAhuEhUazvHJZMzUSTJ542NjZSnstQxWKV4j6U376P7NsjaA6sQE3EsBjRDxkQbkEtR8yH9urdus7ssjxkW)
  - [CsjFmtFh](https://gmgn.ai/sol/token/CsjFmtFh9uVRbCrcKtFU95M3bRv9YrzJr5aP1MC3pump) −0.099, [sell](https://solscan.io/tx/3VqhSvBWmnmULyciEh7keC5R2ZKVjW82333T8L8C2PQqzvHfQyZsbXxLnSQgHGQ4rD4ahyXuGSp9L4KPmbS25wak)
  - [4ovdwdxq](https://gmgn.ai/sol/token/4ovdwdxqgxfN4GH9A6GGkAms5EUQNjy9HHMJg9i8QEhT) −0.035, [sell](https://solscan.io/tx/63wcgHijiKfb24uNnquwahWYZpjuYppZmc9zJcLrdMyuRELEHb7gUkyhoVb9fa3FXgBPo6fGhkotY26yJ9iAedeV)

**Curve exits are not a simple tape rule (M):** I looked at all 141,651 outside trades during his D1 holds and asked how often his sell follows each one.
- After an outside sell he sells next 1.5 % of the time (75 % of his exits follow a sell); after a buy, 0.4 %.
- The rate rises with:
  - the size of that sell: 0.7 % → 2.5 %
  - time since the last outside buy: 0.5 % → 5 %
  - drawdown from the peak: up to 1.9 %
- No feature bin goes above 5 %.
- Who sold just before him: the trigger wallet 1.0 %, the token creator 1.9 %, Grozoe 87 %. Grozoe is not a cause; see the twin result below.
- Rule grid (90+ rules: take profit / stop loss, trailing stop, flow stop, sell after a sell, sell into a buy, timers; all with the 1,800 s cap):
  - Best agreement: trail 15–20 % with a −20 % stop. It matches only 18–21 % of his exits within ±2 slots.
  - Best P&L: +14.8 vs his +42.7 (D1 curve-sold lots). On D0 a different rule wins (+23.0 vs +40.7), so no rule holds across days.

**The key result: Grozoe exits in the same slot even when it entered at a different time (M).** 521 positions in D1 were held by both wallets at once:

| how far apart the two buys were | exit in the same slot | Grozoe sold first |
|---|---|---|
| same slot | 95 % | 41–49 % |
| 50+ slots apart (86 cases) | 92 % | 41–49 % |

- Inferred: the sell signal belongs to the token, not to the position. It is not a take-profit, stop or timer measured from the entry, and not one wallet copying the other.
- Examples (bought far apart, sold in the same slot):
  - [C796JR1F](https://gmgn.ai/sol/token/C796JR1FA3BCBjU6iRCABvi1iUvhq1FQGi2RaSxqpump): Grozoe bought 124 slots earlier. [His sell](https://solscan.io/tx/4cyychWKuaXG17wPT93wVCtoSaiKH4UoywUcqgjxtQRQHQ52VdV9EPEAxUS6Rm2bzbFXHMmPPZqwVcMmMnJafjhr) / [Grozoe's sell](https://solscan.io/tx/4CPpsQbszWmZ3gAKRh6fXgvaaBJBLt3FPrco3AbJF4gTcT47G2tTZvbzimRiFuZXx4BGVn2NhQN3gfXcmGMdD5cp).
  - [GTY2zzTw](https://gmgn.ai/sol/token/GTY2zzTwF8Vy6UFMdFND83qH3vRLymUrK49qMVeLhyyc): 313 slots apart. [His](https://solscan.io/tx/2kmoDZoTQK1uagH7MWm6qWLce14z9VVXDQ3dLi8A6ZPnje6ZpgA2N8wwfJUx8EbjciGcRs269pxFf4oh8VfFu3Zy) / [Grozoe's](https://solscan.io/tx/3N66J8q3JsBXvVAjek9jXHVsEVos7iQ5WpmcXFnNZNhx8Fjkj64utpFZBdKN7Zg4d3G73QpeuYDhzo8YbpVU2TZ4).
  - [7eyFNAZN](https://gmgn.ai/sol/token/7eyFNAZNay8Lq8kKBHf9zWahhgmxa9ypNa3fhucCpump): 410 slots. [His](https://solscan.io/tx/51Xs3WqFoMSmpJrae1mhCVZNkCDqFejW7X78VMV4kL1XgPLv3UwcdHNLyzKWFvigEX9Ch3EgHBrScGJw9H7WcW9a) / [Grozoe's](https://solscan.io/tx/3zXNitABqKfd1JiPNE4e7XdzbBSHW7Y3dprqqBF6knr4gWqxe5Xmeoq5M6VkpSqg1Hx3D4icbZa9gfVRbBmUByXa).
  - [DFgdUzoo](https://gmgn.ai/sol/token/DFgdUzoo36z84Sv6GVeggWRYvaGL8vDMFXWo2FWvpump): 521 slots. [His](https://solscan.io/tx/4mSzyDg9Ey42o6DuHeBv2YzPucT6f14f6ymnNQbYChGdDTotLAfZ5iVqnFGUhwk3oKWHVgmVJnAuRL3Gme8ycF33) / [Grozoe's](https://solscan.io/tx/32c481bK4YinP5SMMDtRih2D6egP5iMVKD4QqM9vvJ1N1di9sWqCF6UqgMDyBxjcRhiqEtDyDJGtgwJEabkvdtPH).
  - [ENtq4Dk4](https://gmgn.ai/sol/token/ENtq4Dk4obbxX3xjihB39WNKNThV3tfEuBRUuWsZpump): 132 slots. [His](https://solscan.io/tx/3N4g8ELqxxdPHC3wFHBg5u2QLgJNphTjtquTYKAuXWSXnWA54Y3HsZbG4rRwL8A51vRM6q3W8cmo1edgV8mG2Hwp) / [Grozoe's](https://solscan.io/tx/3e33mhAhTPBGdj1wHtBdNJpS34gzrNRWqLqJ451UBQN7U63W25Hykgbq1c8AZ4U2oT9M5n325XGuXiaoaNXS9vQE).
- The token's age at exit shows no spike at 30 s or 120 s, so the age bands do not drive exits.
- Winners above +0.2 SOL exit at a median 0.96 of their peak price. Part of that is mechanical: his own sell and the copiers' sells right after it create the peak.

**His exit vs our 200 ms exit, on his own lots (M, tape + curve maths, x8).** Exit price = the curve state at buy + dt; all other costs kept as he paid them. Curve-sold lots only (GRAD lots below the table).

| exit | D1 all | FRESH | MINUTE | OLD | D0 all |
|---|---|---|---|---|---|
| his actual | +42.69 | +8.06 | +13.07 | +21.56 | +40.70 |
| 200 ms | −0.23 | | | | +2.30 |
| 2 slots (our 200 ms + landing) | +1.15 | +0.37 | +0.65 | +0.13 | +7.17 |
| 1 s | +5.04 | | | | +11.96 |
| 60 s | +7.35 | −4.28 | +5.91 | +5.72 | +16.58 |

- GRAD lots: his +17.79 vs −0.15 with a 2-slot exit (D1); +12.04 vs +0.12 (D0).
- Lots where his longer hold won the most vs the 2-slot exit: [9xe8DXZ5](https://gmgn.ai/sol/token/9xe8DXZ5AkqJwYy34P2yKw34yVSGGepSAHQLWdJFpump) +2.52 vs +0.01, [2j4iCzjv](https://gmgn.ai/sol/token/2j4iCzjv54siy96t6ySqGmatbhSwr4bmNRRzpJ8C9KBV) +1.64 vs +0.03, [FixpvmWb](https://gmgn.ai/sol/token/FixpvmWbF2AkdMD65jbgdky9G1Zkoq7SLySyGucipump) +1.48 vs −0.01, [DsA98kXc](https://gmgn.ai/sol/token/DsA98kXcJEsQqpm7rLBVdjBjGeQRDeXqUjeK8PMKmYc8) +1.27 vs +0.02, [ENkivw8C](https://gmgn.ai/sol/token/ENkivw8CNx4o9FS19U1XWU585JRxiGVpyhpQVPKwf96F) +1.18 vs +0.00.
- Lots where his hold lost: [FzFXw2SX](https://gmgn.ai/sol/token/FzFXw2SXuwVcFbp2yjeJUKC9WYg5Yjgaj8zPB2YFpump) −0.86 vs +0.01, [FKZs8DGs](https://gmgn.ai/sol/token/FKZs8DGsStrao4Xg2ThtrQrT6asVmVivLNsK1Brhpump) −0.80, [AcYTifcC](https://gmgn.ai/sol/token/AcYTifcCyhdKkFoDm4WDRWbgxsnCUAqf2ZyD3t56pump) −0.79.
- Buy and sell links for all of these are in x8.txt.

## 4. Cost per lot vs ours (x10)

| mSOL per lot or fill | buy fee + tip | sell fee + tip | failed | total | % of size |
|---|---|---|---|---|---|
| E2x1 D1 (1,344 lots) | 0.150 + 0.688 | 0.105 + 1.065 | 0.043 | 2.05 | 0.44 % (FRESH 0.68 %, OLD 0.24 %) |
| E2x1 D0 | 0.150 + 0.719 | 0.105 + 1.056 | 0.049 | 2.08 | 0.39 % |
| ours FRA r27 | 0.205 | 1.820 | 0.863 (169 failed tries per fill) | 2.89 | 0.64 % |
| ours FRA r28 | 0.205 | 1.805 | 0.729 (142) | 2.74 | 0.61 % |
| ours AMS r28 | 0.205 | 1.805 | 0.519 (101) | 2.53 | 0.56 % |

- His D1 total: tips 2.36 + fees 0.40 = 2.76 SOL against +59.3 SOL P&L.
- He pays more per buy than we do (he tips each buy) and less per sell.
- The difference is our failed pre-send tries. Cost is not his edge.

## 5. Sibling and followers (x6, x9, x9b, x12)

**Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ is a twin engine (M):**
- Same tx fingerprint: own durable nonces (it is its own nonce authority), fixed CU price, the same astralane 1.1M / Helius 10k tips, and a no-nonce sell copy.
- Its nonce accounts are separate from E2x1's but use the same seed names: fbn-euw4-00 (4KBJQ6…) and fbn-use4-00 (8yzgfZ…).
- Both wallets created their nonce accounts on 10-21 between 12:19 and 12:24 PKT, minutes apart.
- In D1 it holds the same token at the same time in 521 of his lots, with buy size ratio p50 0.99 (the same size code). Buys are in the same slot only 33 % of the time; exits are in the same slot 92–95 % of the time.
- Inferred: one operator, or one bot software and config running both wallets.
- Funding (M):
  - Grozoe was funded on 10-14 22:34 PKT with 10 SOL from DA9nTGVx7NX2siZjMptCS2Pf6kdDgJW8A6Q1BPf8aHxC.
  - Public RPC history for E2x1 only reaches 10-19 14:04, and the first tx there is a trade, so his funder is unknown.
  - No direct transfer between the two was seen; recon also found zero transfers out of E2x1 in D0/D1.

**Followers are copy-traders of his wallet (M):** each buys ≤2 slots after his buy and sells ≤3 slots after his sell.

| wallet | D1 co-buys | also co-sold | size vs his |
|---|---|---|---|
| 3iawEZGfWF3H7q6HLxHjSfeZHjCvPr8U9xjXpMgtobDN | 789 | 594 | 0.34× |
| Hj4uACn8Jp2QvbMFhkhWWCdHPzC2SEXg7fhpZayYVcyL | 390 | 341 | 0.83× |
| FiYZPbS4wi7CSEBerzvyHEAzQkT7qj1apB2mZob3R3zj | 309 | 275 | 0.98× |
| 4HgMCR7abFKHDPgYfMrtjvKniPXj4zHwuSNNRVx7QEzQ | 204 | | dust |
| AZ45pUnDKayDSsqxASohrqTaAWSLRwwfTzTpdNoqAQSx | 160 | | 0.10× |
| 8VqKtt…, 5174QiRm…, GLsnUR…, EfN6eT3G…, J7EA3X…, 7yY786… | 27–92 each | | |

- Order: 89–98 % of their buys come after his (about 60 % in the same slot), and ≥98 % of their sells come after his sell. That is a bot reacting to his transactions.
- Funding: 3iaw… by 8d9PjFEi… (10-23); Hj4u… by 6vG3cjb1… (10-27, 0.01 SOL); FiYZ… by 8VqKtt… (10-28 01:40, 4.66 SOL), and 8VqKtt… is itself a copier. The copiers are linked to each other, not to E2x1.

**What the copiers are worth to him (M, x6).** The curve price depends only on the net SOL sitting in the curve, so I removed the copiers' SOL still in the curve when he sells (median 0.26 SOL) and re-priced his sell:

| day | his curve-lot P&L | copier value | without copiers |
|---|---|---|---|
| D1 | +42.69 | +8.24 | +34.45 |
| D0 | +40.70 | +10.25 | +30.45 |

- D1 by bot: FRESH +8.06 → +4.37, MINUTE +13.07 → +11.00, OLD +21.56 → +19.07.
- Lots with a copier buy within 2 slots make +39.9 mSOL per lot vs +0.9 without. That split is confounded: copiers skip some of his lots.
- Examples (his buy → copier buy; his sell → copier sell):
  - [CYUYKtjq](https://gmgn.ai/sol/token/CYUYKtjqPnD532sX1BNTufV8177Lwu5jkcmBsYzZkaiD): [buy](https://solscan.io/tx/3wB8KrnURHCXmfBVxXGyAKGMAvV4tXi3CQvkywcfS8Y9c9UJidjYjQDN2T5eXr8i7ytp13Bo4ScuK6kreAsEcUc2) → [Hj4uAC buy](https://solscan.io/tx/3V9Z4T3zVXuTAMaKRmK6n8M9nK1tdUFtUbjVmm4Q74fDuDahWXusVn7ef31CX8cH2QB1tD4TL3S3AhEF8MAbLpFA); [sell](https://solscan.io/tx/uocozZVfAKxgAGiupWVBWnqt9qP4DHKEiJbP7w9ukMxJbVuy21t41w2DqVuG9MkBBqnYTncphjwCt8jKy9YH7fZ) → [Hj4uAC sell](https://solscan.io/tx/3SFE8MLd4FnH1WAbRLifBMaQx9vuY9bVNXoXJzBDDVUxT8AmyU14ayHRw1RkhUF2z1ebjqk5JNLPJ6xZUw2q9LVi).
  - [J2Yx7nho](https://gmgn.ai/sol/token/J2Yx7nhowMzBczhkuqArC5KxAQgvq8SXfLHFTH3tpump): [buy](https://solscan.io/tx/2WxQ3fZNY8A154dNtKzq9HNY5Ce8wEKXAyAJQUeHTxNnvrCBqamH55dGwK2MjjEeu2RFNz1Pw8DrD7XMsbUJ6vs6) → [3iawEZ buy](https://solscan.io/tx/3ebJYs4QFVDLpqw6Hq8DyfNQAK1HEWLTaRJLBDV2QVaU5BJMw7DcATMshLzRzBNzFS7wSRaUZ88Vesc3hwNRZKZY); [sell](https://solscan.io/tx/2ppFRhT1ZnWaYQBVdgGzJTSVV54DrJhSw7AVkmGAQuh2iP23pRpjp3sPza6GxCGn9H6ikhfRaqNsbtK1xsUrDSyA) → [3iawEZ sell](https://solscan.io/tx/46xpFRj1C39EyWvDrC5oEPD8N9efPwaczwQuQvjcQcwypGdYRHbB2H4N5fYL6vpLzNU2HZfz1eJ4CXRKGqyCdLaJ).
  - [8SjwEMtE](https://gmgn.ai/sol/token/8SjwEMtE6cdGSmiyoYYxFs22zEoX9uex8LweBM2zpump): [buy](https://solscan.io/tx/2BiuXEQpbNR45hofg4MiiAKDTHTKYYWbVsNgC1eq562p4HeGUdY39irwhYZvAS4vCQuJ2XY24yGGHJcFQuHELj4q) → [3iawEZ buy](https://solscan.io/tx/2fKJgi6v6jBkp3UwRppofJ5GTVbMfNojdhcBViuEuDVui999TQFpmVcZty6BQMqeRJrXkxY7qbybvsTeyo1xhYoQ).
  - [4GQcJ866](https://gmgn.ai/sol/token/4GQcJ866LcThvkgHmehU3GdkBSXp6kN2x5Ee63popump): [buy](https://solscan.io/tx/5Z25G6NJhM6Tu2iy4CPY9FJ38q5B2zqpNNgpba7eSEC8rn1L6NxrNFvR6kr6aLNiyEHkT6uaXBdcqRco2gscZHEa) → [AZ45pU buy](https://solscan.io/tx/2ZJzfiMbW5fMA68ZWsxRLk9hqrvLfwZHJhkH3KXcxeGn9c9mDqueUrXTMEbkztkpJDtnUvh5XxW7mSV4nv25m2wm).
  - [CFHP5Ksf](https://gmgn.ai/sol/token/CFHP5Ksf9SvYMHKw6UKzfmjvThi8LLMRaBEo1Ceepump): [buy](https://solscan.io/tx/5CfnW4K6RwKXgfzqFoBNV7qxHGDBLtpZbTHhdB7NhAWbujyJuYXXR6knxoPwdUvucoZpJEwkMHK6PmmCZkG55sm5) → [Hj4uAC buy](https://solscan.io/tx/3ZCxJGHj1vwoDC7NssEdqKZJSk99jXyKwD8grKUvNkeZrKmzUjDQn4qbjDxRhaDgjmGk2Hp2RPTQkxsefHoFY7HU).

## What this means for us (inferred)
- **Speed is not where he beats us.** Two things worth copying:
  - **Regional engines near each leader:** he trades 28 % of his lots on leaders in N. America and Asia.
  - **His copy pattern:** 2 nonce copies + 1 blockhash copy, with account creation guarding against a double buy, for 0.04 mSOL per lot of failures.
- **His money is in the exit.**
  - **GRAD:** hold through graduation and sell on PumpSwap ~48 slots later. It is clean and rule-like, worth a separate test.
  - **Curve exits:** the token-level sell signal is not reproduced by any simple tape rule, the same result as for haqq.
- **Copiers add 20–25 % to his P&L;** we would not get them.

## Caveats
- Block size is a lower bound (largest pump tx index), so in-slot timing is approximate. The same method was used for haqq and for us.
- Leader locations come from an IP lookup made in epoch 1063, so some may be stale.
- Copier value counts only their direct SOL in the curve, not how others reacted to it.
- The rule grid assumes a fill right after the triggering trade, which is optimistic.
- Trigger matches for small trades can be wrong.
- The extra "sell into a buy" rule run (best +5.8 on D1) has no table file; its numbers are only in this report.

## Files
Everything is in the folders the brief assigned to "exec":
- **Code:** `/home/moiz/sniper/ops/strategies/e2x1_dissect/exec/` (x0–x13, xlib.py)
- **Tables:** `/home/moiz/sniper-data/e2x1_dissect/exec/`, about 99 MB. Start with x1.txt, x3.txt, x6.txt, x8.txt, x10.txt and x12.txt; examples are in x11.txt.
- **Added there:** a fresh leader schedule for epoch 1070 (schedule_1070.json) and the validator client list (cn.json).
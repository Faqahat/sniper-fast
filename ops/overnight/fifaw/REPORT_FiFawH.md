# FiFawH: a full dissection of a profitable pump.fun sniper (2026-10-23, read-only)

Wallet: [FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W](https://gmgn.ai/sol/address/FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W) ([solscan](https://solscan.io/account/FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W)).
Times are PKT (UTC+5). Every claim is tagged **MEASURED** (read from chain data or our collector) or **INFERRED** (my reading of measured facts).
Visual page with its last 15 snipes: `FiFawH_snipes.html` (same folder).

## Verdict
1. **It is a private, custom bot, not a commercial one.** MEASURED:
   - It trades through 7 on-chain programs of its own.
   - FiFawH itself deployed its sell program on 07-01 17:34 PKT, 1.5 min after it was first funded.
   - The other 6 programs share one upgrade authority, D9VpYF….
   - In samples of 25 recent txs per program, FiFawH was the only signer.
   - It pays no fee to any bot service (AKbot, Axiom, BullX, Photon, GMGN, Trojan or Maestro).
2. **It makes money after all costs.** MEASURED, constant prices:
   - **+27.75 SOL in 61.3 h (≈ +10.9 SOL/day)**, from 10-20 18:04 to 10-23 07:22 PKT.
   - Gross trading made +89.6 SOL. Sending and failures cost 61.7 SOL: tips 25.9, failed-buy fees 14.4, fee-only txs 7.4, guard no-ops 6.2, other fees 7.9.
   - The wallet holds about 395 SOL in total.
3. **Its edge is choosing the right launches, plus being first in line.**
   - **Its picks draw ordinary buyers** (MEASURED). With its own trades removed, its picks are at a median 1.14× the post-bundle price after 5 s; all other launches are at 1.00×. 60% of its picks are above 1.1× at 5 s, against 17% of other launches. From 2 to 10 s after the create, its picks get a mean of 12.5 unrelated buyers (median 6); random launches get 5.7 (median 0).
   - **It is first in line** (MEASURED). It is the first outside buyer in 123 of its 127 replayable snipes. 96 of the 127 land in the create block.
4. **Its exit is "dump unless up"** (MEASURED).
   - 332 of 429 positions are sold in one go at a median of 3 s. As a group they lose −19.9 SOL.
   - The 97 positions sold in steps make +75.7 SOL.
5. **For us, the edge only exists in the first slot, and we cannot find its picks at create time.**
   - **If we knew its picks in advance** (ORACLE, not tradable): at our 75 ms landing with the 1% guard it would pay. With slippage on and every fast sniper's buys after ours removed, a 5–10 s hold makes +3.8 to +4.5 SOL on 49 fills out of 144 attempts. At 45 ms it makes +6.3 to +6.8 SOL.
   - **Every tradable version fails** (MEASURED, replay):
     - A deployer list built from its past attempts goes from ≈ +1 SOL to ≈ 0 or negative once fast snipers are removed. Rejected: depends on fast snipers 9qz7cWBq, Anubis51, HVE8996r, 6y5cGrki and FiFawH.
     - Create-time rules that imitate it lose in both directions: −0.2 SOL (R1→R2) and −5 to −11 SOL (R2→R1).
     - Copying its buy 0.15–5 s later loses −2 to −5% per trade, the same as random launches.
     - Waiting for strong buying before a later entry also loses.
   - **Do not copy FiFawH.** Three lessons are worth keeping (section 7):
     - Hold good picks for 5–10 s rather than selling at the end of the next slot.
     - Infrastructure details: one durable nonce for every buy, several landing services, tips that grow with size, and a guard that makes the tx fail instead of returning success.
     - Its pick signal is probably off-chain (news or celebrity names, deployer identity), as we found for 4yFAz.

## 1. Infrastructure and bot identity

### 1.1 Example transactions (all MEASURED)
| what | tx | notes |
|---|---|---|
| direct buy, Nozomi tip | [5fxUdu…](https://solscan.io/tx/5fxUduFfqPYHpyeBmoKxPFjgsHfmMmTTnuMKXuRHKjX6QnteQjiUiJ5FuMGGEBzJuTKM4EBjETZXpbYcgZhQUZ2a) | Pump `BuyExactQuoteInV3`: 1.5 SOL in, min out 46.5M tokens (≈ 2% slippage). Nozomi tip 0.0276. Priority 0.00115. 54,077 CU. |
| guarded buy via its program B78FW9 | [9Wfc9C…](https://solscan.io/tx/9Wfc9CkzBH6YvAkwWDBR2UUCRHdrXpzXV2AkPyQHAWc95VPPnWc36fN6hFeFJQZoNutLXNLPDxjgQ6oJxpXQJ3U) | Args: 1.5 SOL and 5 SOL (the 2nd is a guard limit, INFERRED: max curve SOL). Tip 0.0023 to AsTzjK…. Priority 0.0129. |
| USDC-funded buy of an other-quoted curve | [4FeE8i…](https://solscan.io/tx/4FeE8ifDE32WAEEfhCshj4awVR3gmxBZvw4mwYSU58kKUy2S8czkrYagpaRAhotckmwBYxA7Q12zaioZ8yegZymc) | Program 9uGqm7: 160.6 USDC → Meteora DLMM swap → pump `BuyExactQuoteInV3` on the curve. Jito tip 0.0473. |
| sell 100% | [3q2AfP…](https://solscan.io/tx/3q2AfPR22CDTFbQnpgBCGe77V3zRTnBjgjkAMPmCFAFvqsS2MG38VCy2ce6rzBZM5xqK6B9Yf63vjUitz2xE4HiW) | Its program 2kAA3B, args (100%, min out 0), then closeAccount. Recent blockhash, no nonce. Jito 0.0003 + Helius 0.0016 tips. Priority 0.0035. |
| failed priority-only copy | [2Hdxfc…](https://solscan.io/tx/2HdxfcHrDn5B27bqAMbWtfLmaP38rKRVyXYwfBJyLc4LLms1EeP5pQVm3wGZLpLAYrZs5mC79urXck7RWwyf3PUi) | A 5 SOL buy with no tip and a **0.1226 SOL priority fee**. It failed with `BondingCurveComplete` and still paid the fee. |
| guard no-op that still paid a 0.93 SOL tip | [8afwtm…](https://solscan.io/tx/8afwtmbJjLEhnmVt2dmJbHiWaHSAaBS4Fa26EqFkfbAWxzCJ4fu4Trgdi7JKTureVdLaK7zjPoXhZQcMaeBQkwh) | B78FW9 (a 6 SOL buy, limit 6.5) returned *success* without buying, so the Jito tip of 0.929 SOL was paid. This happened 5 times in a row on one launch on 10-22 around 18:45 PKT. |
| fee-only tx | [2LaaWu…](https://solscan.io/tx/2LaaWuJemUup4ETwnx2FGFppTcD9EDwEosUv9aGcq9LGfFtpXhP9uUJFT5vr6n9WHZYXKstzjD6b4nDoFhLjWdkm) | Two compute-budget instructions only: 304 CU at a huge price, a **2.94 SOL fee** for nothing. |

There were 5 fee-only txs in all (0.40, 0.40, 2.94, 0.72, 2.96 SOL), each in a block of a different leader. INFERRED: a bug in how it builds transactions, not a payment to one validator.

### 1.2 Fingerprint over all 1,519 txs it signed (MEASURED, `q1_infra.py`)
- **Transaction:** v0 (1,512 of 1,519), always one signer.
- **Buys:**
  - All 863 buy attempts (landed, failed and no-op) use the durable nonce [4kT5gq…](https://solscan.io/account/4kT5gqyZkLqkFV3J5yRwqF3qCxmvExTtZiyf4saT3Cah).
  - Compute budget: CU price, CU limit (p50 60,950) and, on about 1/3, a loaded-accounts-data limit of 12,124,160.
  - The CU-limit instruction carries a dummy read-only account. 37 different ones were used.
- **Token account:** `createAccountWithSeed`, where the seed is the first 8 characters of the nonce blockhash, then `initializeAccount3` (Token-2022). The ATA program is not used.
- **Buy routes (429 landed buys):**
  - direct pump `BuyExactQuoteInV3`: 217;
  - other-quote program 9uGqm7 (swap USDC on DLMM, CLMM or Whirlpool, then buy): 123;
  - guard B78FW9: 43;
  - guard 9f2uHx: 33;
  - LaunchLab program 5gP7LH: 13.
  - INFERRED: this explains our engine's undecoded "0.000:0" entries.
- **Landing (tips on the 429 landed buys):** Jito 146, Nozomi 103, Helius 67, LandX 28, the unlisted tip account AsTzjK… 13, Stellium 3, BlockRazor 2, Falcon 1, bloXroute 1. 65 had no tip, only a priority fee. Buy tips totalled 24.7 SOL.
- **Tip grows with size** (tip plus priority as a share of the buy): median 1.9% (p10 0.9%, p90 5.1%).
  - 1 SOL buys: 2.6%. 1.5 SOL: 1.9%. 2 SOL: 1.5%. 3–3.5 SOL: 5–6.5%. 8 SOL: 12.9%.
- **Failed-buy fees:** 402 failed buys paid 14.4 SOL in priority fees (p50 0.013, p90 0.10 SOL). 171 of them had no tip at all.
  - INFERRED: one copy of each buy is a priority-fee-only tx sent outside the tip services. It lands even when it is too late and then fails while paying its fee.
- **Sells:** no nonce; recent blockhash; CU limit 100k–250k; priority 0.0035 SOL; Jito 0.0003 + Helius 0.0016 tips on every sell (634 and 635 of 635).
  - The argument is a percentage (100 / 49 / 32 / 15) with min out = 0.
- **Our clock:** it arrives in our engine's feed at a median of 61 ms after the create (p10 14 ms, p90 172 ms).
- **Programs:**
  - buy: [B78FW9](https://solscan.io/account/B78FW9mVQT2fDhsW7ChvqTBhZzhCbRrtWYC6K5oa7xuv), [9f2uHx](https://solscan.io/account/9f2uHxWdaB5nRgjRgsUe4T1LtyzejLNnxuzLfvyMyyxP), [9uGqm7](https://solscan.io/account/9uGqm7Xh7Vq2EzqTNHVG5Ca4echELK1UjDq9W9Qg5kzF), [5gP7LH](https://solscan.io/account/5gP7LHpRndFJSjANFB2ZBJtPJ3KhcPf2xgSNKVD7tAfK);
  - sell: [2kAA3B](https://solscan.io/account/2kAA3Bm3npaBzrevWXJfojagG1BEAac4KwayWphYMYQG) (upgrade authority FiFawH), [6iemSi](https://solscan.io/account/6iemSi2wHcEJoAwEdG69VznRPGHWJr6Y2VRSyj6m9h45), [BCzSQS](https://solscan.io/account/BCzSQSmV988WPnCM6MXToLvBaL8dmj8uJWG1MaceenvX);
  - all except 2kAA3B have upgrade authority [D9VpYF…](https://solscan.io/account/D9VpYFsfLXDoWkUUgYoKBcKdzV745qDajxLsjpNWuaNk). They were last deployed on 10-03 23:18 PKT (5gP7LH, 6iemSi, BCzSQS) and 10-09 05:33–05:45 PKT (B78FW9, 9uGqm7, 9f2uHx).

### 1.3 Comparison with 9Sh2fd (an AKbot user)
- **Same ideas:** a durable nonce on every buy, `createAccountWithSeed` + `initializeAccount3` instead of the ATA program, tips that grow with size, swap-then-buy routes for USDC- or other-quoted curves, single signer.
- **Differences:**

| | 9Sh2fd (AKbot) | FiFawH |
|---|---|---|
| tx format | v1, fee in the header | v0 with compute-budget instructions |
| landing | LandX tips only | tips to about 9 services plus a priority-only copy (INFERRED) |
| router programs | AKbot's | 7 of its own |
| bot fee | 1% to AKbot | none |
| guard | — | on-chain guard program |
| selection | lists of serial devs | 184 different deployers |
| exit | lightning sell plus take-profit ladder | dump unless up, then a ladder or TWAP |

- INFERRED: FiFawH is a self-built bot, probably run by the same operator as D9VpYF.

## 2. Profit (ground truth, owner-RPC window)
Window: 10-20 18:04 → 10-23 07:22 PKT (61.3 h, slots ≥ 459,240,222). 1,519 txs signed by FiFawH.

Values are SOL plus WSOL plus quote assets at today's prices (SOL = 106 USD). No launch tokens from the window are still held. There were no deposits or withdrawals in the window: the 500 txs signed by others only reference it (a copy bot, a holder fee payout, dust).

| PKT day (hours covered) | landed buys | trading (incl. their fees and tips) | failed-tx fees | guard no-ops | fee-only txs | **net** |
|---|---|---|---|---|---|---|
| 10-20 (5.9 h) | 56 | +4.86 | −1.52 | −0.14 | 0 | **+3.21** |
| 10-21 (23.9 h) | 155 | +30.48 | −7.08 | −0.20 | −4.46 | **+18.74** |
| 10-22 (23.6 h) | 154 | +17.25 | −4.55 | −5.42 | −2.96 | **+4.31** |
| 10-23 (7.3 h) | 64 | +3.33 | −1.28 | −0.44 | 0 | **+1.60** |
| 1 failed tx with no block time | | | −0.10 | | | −0.10 |
| **total** | **429** | **+55.91** | **−14.53** | **−6.19** | **−7.42** | **+27.75** (incl. −0.02 token-account rent) |

**Costs** (SOL): buy tips 24.67 · failed-buy fees 14.40 · fee-only txs 7.42 · guard no-ops 6.19 · buy fees 5.60 · sell fees 2.23 · sell tips 1.20 · failed-sell fees 0.03. Gross trading before any fee or tip: +89.62.

**By venue** (trading only):

| venue | positions | SOL |
|---|---|---|
| pump, SOL-quoted | 302 | +37.79 |
| pump, other-quoted (bought with USDC) | 108 | +18.62 |
| Raydium LaunchLab | 19 | −0.49 |

**By size:**

| SOL spent | positions | SOL | mean return |
|---|---|---|---|
| < 1.2 | 33 | +0.32 | +1.0% |
| 1.2–1.8 | 128 | +7.45 | +4.0% |
| 1.8–2.6 | 220 | +15.60 | +3.5% |
| 2.6–4.5 | 32 | +8.60 | +8.0% |
| ≥ 4.5 | 16 | +23.95 | +22.5% |

INFERRED: it sizes up when it is confident, and those calls are right.

**Longer history** (signatures only): active since 07-01, 133,753 signatures. Aug 52k, Sep 45k, Oct 21k (to date). PnL before 10-20 is not reachable through the owner's RPC.

## 3. Funding and relations (MEASURED unless marked)
- **First funding:** 7.558 SOL on 07-01 17:32 PKT ([tx](https://solscan.io/tx/2DjQWVSmqVudNTBnCmPt7pKHM1Roj5JzFRCuP9dCgtYr8n1ZENGz5K8LPsk4nNJpCKhHqBjoYnRv2e1sHZ9yUcVA)) from [2AQdpH…](https://solscan.io/account/2AQdpHJ2JpcEgPiATUXjQxA8QmafFegfQwSLWSprPicm).
  - That wallet holds 185,714 SOL and made 1,000 payouts in 3.7 h. INFERRED: an exchange hot wallet.
  - 1.5 minutes after funding, FiFawH deployed its own sell program 2kAA3B ([tx](https://solscan.io/tx/3GPsRzzDDSAGhZDff1VJE8uhbR3LdEwc1s5mLU7dd88LmgmzvTpJ9tS2VzedU2PormkdJxmSeA6mCPCQkGwkM639)).
- **Program operator:** [D9VpYF…](https://solscan.io/account/D9VpYFsfLXDoWkUUgYoKBcKdzV745qDajxLsjpNWuaNk) holds 1.40 SOL and is the upgrade authority of the other 6 programs. It made 927 self-signed txs since 10-20 12:28 PKT, sending ≈ 0.005 SOL to many addresses.
  - INFERRED: the same operator's dev or ops key. No direct SOL link to FiFawH was found in the window.
- **Shared tip receiver:** [AsTzjK…](https://solscan.io/account/AsTzjKRAZ91h6VpiR7Za5EWP8MPYRhfnRxAG4CUXL3oT) (0.78 SOL).
  - Among 30 recent senders: FiFawH 25, [DxhpC9c4…](https://gmgn.ai/sol/address/DxhpC9c4kGkYJR34xUrfFeDx9vwb6yoHUMWrTCZybwtH) 3. DxhpC9c4 trades through its own program FATLh4….
  - INFERRED: AsTz is a small or private landing service, or another key of the same operator. DxhpC9c4 is a candidate linked wallet; not proven.
- **Copy follower:** [DeFG8i8z…](https://gmgn.ai/sol/address/DeFG8i8zoJ3hN155nmvLq266ZVxWmNgRaTz5KQVHfe2S) sent 433 txs through program [F7hMV9…](https://solscan.io/account/F7hMV94qDyUXuv5HirXYJhU59AjuPfJMFaZFbwzLD62r) (authority 3ct4z3q2…). Each passes FiFawH as an account and buys the same tokens.
  - It is not a fast sniper: 0.1% of its 4,899 buys come within 2 slots of a create.
- **Others that reference it:**
  - HckQ93Xq…: a pump.fun `DistributeFeeToHolders` payout. FiFawH is just a holder.
  - 3uxuYq…, 7VGtN8…, B1ZVhF…, FJVL1F…, Ep2XTp…: dust and memo spam.
- **No cluster of trading wallets found.** Its programs are used only by FiFawH (25 of 25 sampled txs per program).

## 4. Selection: what it buys
Population: 45,981 launches in its attempt window (10-22 03:17 → 10-23 05:34 PKT). It attempted 267 (0.58%) and filled 154. 264 of the 267 attempts were within 5 slots of the create.

**What raises its attempt rate** (MEASURED, lift vs 0.58%):
- **Deployer it already attempted:** ×25–53. 30% of its attempts are repeat deployers, but it uses 184 deployers in all, and the top 10 cover only 19%.
- **Never mayhem:** 1 of 11,072 mayhem launches.
- **Other-quote curves:** ×2.2.
- **Create signer is not the creator:** ×2.1.
- **Fresh deployer** (< 2 prior launches): ×1.9–3.4. Serial deployers with ≥ 20 launches: ×0.1.
- **First launch of its name in the last hour:** ×1.6. Name copycat waves: ×0.4–0.7.
- **Dev buy:** 1–3 SOL ×1.7–2.5. But 115 of its 267 attempts have no dev buy at all.
- **Glued bundle:** exactly 1 glued tx ×2.4; 2–3 glued txs ×0.1–0.3.
- **Create fingerprint** (CU price | CU limit | tip): `10000|600000|0` ×8.2 (19 of 399), `10000|500000|1` ×7.0.
- **Metadata:** ipfs.io ×1.4. j7tracker metadata ×0.4. Axiom image CDN ×0.3.
- **No effect:** hour of day (PKT), name length, has Twitter.

**Are its picks better than average?** Yes, by a lot. MEASURED, price relative to the post-bundle price, **its own trades removed** (replay validated 152/152 against the feature table):

| checkpoint | its picks (n=151) median | share > 1.1× | other launches (n=16,845) median | share > 1.1× |
|---|---|---|---|---|
| end of create slot | 1.007 | 36% | 1.000 | 10% |
| 1 s | 1.127 | 53% | 1.000 | 15% |
| 5 s | 1.138 | 60% | 1.000 | 17% |
| 15 s | 1.098 | 50% | 1.000 | 15% |
| 60 s | 1.047 | 38% | 1.000 | 11% |
| 10-min peak | 1.372 | 81% | 1.032 | 38% |

The gap holds at every dev-buy size.

**Follow-on demand is broad, not a few bots** (MEASURED). Counts are distinct buyers, excluding insiders, FiFawH and the 1,853 fast snipers; SOL-quoted launches only:

| window after create | its picks (n=166): buyers mean / median, buy SOL median | random launches (n=1,122) |
|---|---|---|
| 0–2 s | 4.4 / 2, 0.78 SOL | 1.9 / 0, 0 SOL |
| 2–10 s | 12.5 / 6, 1.86 SOL | 5.7 / 0, 0 SOL |
| 10–60 s | 18.7 / 4, 0.91 SOL | 9.6 / 0, 0 SOL |

**Can a create-time rule find its picks?** No (MEASURED, train/test across the two runs):
- Rules on content and launch features reach only **3–6% precision** (6–27% recall). The R1-trained rule goes 6.2% → 5.2% on R2; the R2-trained rule goes 5.9% → 3.5% on R1.
- Its own deployer history works best (17–24%), but that depends on FiFawH.
- INFERRED: the missing signal is off-chain (news, celebrity and trend names: "Ryan Garcia", "McRib Indicator", "Mini McGregor"), plus deployer identity.

## 5. Entry and exits
**Entry** (MEASURED):
- **Size tiers** (landed buys, SOL or USDC-equivalent): 2.0 SOL (167), 1.5 (88), 1.0–1.25 (26), 0.75 (8), 3–3.5 (23), 5–8 (10).
- **Block position** (127 landed snipes we could replay):
  - 96 in the create slot, 29 in the next slot.
  - **0 outside buyers ahead of it in 123 of 127.**
  - In the create slot it sits a median of 51 txs after the create tx (p10 21, p90 183).
- **Failures** (402 failed buy txs):

| error | count | cause |
|---|---|---|
| `BuySlippageBelowMinTokensOut` | 271 | others landed first; its ≈ 2% min out was not met |
| `MintDoesNotMatchBondingCurve` | 81 | INFERRED: wrong curve account for some pool types |
| its own guard errors (custom 7001 / 7002) | 35 | |
| `ExceededSlippage` (DLMM swap) | 6 | |
| `IncorrectProgramId` | 4 | |
| `BondingCurveComplete` | 2 | |
| other | 3 | |

  - Every failed tx paid its priority fee: 14.4 SOL in total.
  - The guard also returned *success* without buying 32 times, which paid the tips: 6.2 SOL lost.

**Exits** (MEASURED, 429 positions):
- **One sell of 100% (min out 0):** 332 positions, median hold 3 s, **−19.85 SOL**, 26% winners.
- **2 sells:** 75 positions, +33.30 SOL, 97% winners. The first sell is usually 49%.
- **3 sells:** 9 positions, +12.21.
- **4 or more sells:** 13 positions, +30.24. This is the ladder for 6–10 SOL buys: 32% at 0–2 s, then 15% of what is left every 30 s, then the rest at 300 s.
- **First sell:** median 10 slots / 2 s after the buy (p90 21 slots / 5 s). Price at the first sell: median 1.024× its buy price (p90 1.373×).
- **By hold time:**

| hold | positions | SOL | winners |
|---|---|---|---|
| < 2 s | 69 | −1.90 | 33% |
| 2–5 s | 241 | +5.71 | 35% |
| 5–15 s | 107 | +25.92 | 57% |
| 15–60 s | 3 | +2.68 | 100% |
| > 60 s | 9 | +23.51 | 78% |

- **Compared with DGmspi and 9Sh2fd** (AKbot): they use a lightning sell, a fixed share at 0–2 slots and at any price, then take-profit steps and down-sells. FiFawH has no lightning sell. It waits about 2–3 s and dumps everything unless the price is up; if it is up, it sells about half and lets the rest ride.

## 6. Copyability for us (replay, new realism rules)
**Our mechanics:**
- Landing at 45 or 75 ms. R2 uses `rp.place_bo2` with failed-tx anchors; R1 uses `rp.place_proxy`.
- 1% price guard; a guard fail costs −0.005 SOL.
- 0.5 SOL buys, `fill_pen` 1.5%, 2% buy overhead.
- Exits: end of the next slot (eos1), ~1, ~2, ~5 and ~10 s.
- **Later entries** (D*x*): decide *x* s after the create, then land after every trade up to *x* + 0.4 s. No guard, 0.5% send cost.
- Mayhem and non-SOL quotes are excluded.
- R1 = 10-22 03:07 → 19:01 PKT; R2 = 10-22 20:43 → 10-23 05:37 PKT.

**Variants:**
- v0: as on chain, no slip.
- v1: plus followers' decoded slippage limits.
- v2: v1 without FiFawH's trades after our buy.
- v3: v1 without the trades after our buy of **all 1,853 fast snipers**. A fast sniper bought within 2 slots of the create on ≥ 5 launches, with ≥ 50% of its buys that fast; FiFawH is one of them.
- v4: v1 without the top-10 most frequent after-us buyers of that set.
- v5: v3 and v4 together.

z = share of fills with no outside buy between our buy and our sell.

**Slip coverage:**

| landing | eos1 / 1 s / 2 s | 5 s | 10 s |
|---|---|---|---|
| L45 / L75 | 88–100% | 50–62% | 33–41% (unknown buys are kept as fills) |
| D modes | 6–67% | | |

**Key results:** total SOL (R1 / R2), guarded fills / simulated launches.

| set | landing | fills | v1 eos1 | v1 ~5 s | v3 eos1 | v3 ~5 s | v3 ~10 s | z (v3, eos1) |
|---|---|---|---|---|---|---|---|---|
| (a) ORACLE: its 267 attempts | L45 | 71/144 | +4.47 (+3.11/+1.36) | +5.33 (+4.89/+0.45) | +1.18 (+1.69/−0.52) | +6.34 (+5.71/+0.62) | +6.79 (+5.71/+1.08) | 62% |
| (a) ORACLE | L75 | 49/144 | +2.76 (+1.74/+1.02) | +3.58 (+3.04/+0.54) | +0.30 (+0.78/−0.48) | +3.79 (+3.38/+0.41) | +4.48 (+3.84/+0.64) | 59% |
| (a′) ORACLE: its filled buys | L75 | 23/78 | −0.09 | +0.49 | −0.73 | +1.10 (+0.36/+0.74) | +0.87 | 65% |
| (b) walk-forward deployer list (≥ 2 att, ≥ 10%) | L45 | 37/84 | +1.63 (+0.18/+1.45) | +0.83 | −0.78 (−0.63/−0.15) | −0.07 | +0.24 | 62% |
| (b) | L75 | 29/84 | +1.00 (−0.17/+1.17) | +0.33 | −1.00 (−0.64/−0.36) | −0.31 | +0.23 | 79% |
| (c) generic rule, R1→R2 | L75 | 25/39 | −0.25 | −0.17 | −0.69 | −0.59 | −0.40 | 96% |
| (c) generic rule, R2→R1 | L75 | 346/471 | −8.83 | −5.46 | −10.35 | −5.75 | −6.56 | 93% |
| (z) 3,000 random launches | L75 | 774/1,015 | −20.72 | −22.49 | −23.92 | −23.18 | −23.80 | 92% |
| (a) ORACLE, copy 0.15 s after create | D0.15 | 165/165 | −3.94 | −6.67 | −4.00 | −6.76 | −8.84 | 90% |
| (a) ORACLE, later entry 1 s | D1 | 165/165 | −3.55 | −6.33 | −3.55 | −6.40 | −7.69 | 86% |
| (a′) its filled buys, copy 0.15 s | D0.15 | 91/91 | −2.07 | −3.56 | −2.07 | −3.58 | −4.56 | 92% |

**Readings:**
1. **Only the oracle is positive in both periods**, and after removing fast snipers only for 5–10 s holds. At eos1 its profit mostly comes from fast snipers buying after us.
   - Our guarded fills are always cases where we beat FiFawH, and FiFawH then buys after us in 36 of 71 fills at L45. That is the "selling into the bot" the owner rejects; v2 and v3 remove it and the 5–10 s results stay positive.
   - The remaining profit is from generic buyers: a mean of 12.6 after-us buyers within 5 s, of which 2.2 are fast snipers.
   - **But this set cannot be traded**: we only learn its picks when its buy lands.
2. **(b) is rejected: it depends on fast snipers 9qz7cWBq, Anubis51, HVE8996r, 6y5cGrki and FiFawH.** R1 alone is negative in every variant.
3. **(c) generic imitations and (z) random launches lose** (−2 to −3% per fill).
4. **Later entries cannot capture its demand.** Every set and exit loses −2 to −5% per trade.
   - Waiting for strong buying first also fails (`copy/q7_tests.txt`): enter at 1 or 2 s only if non-insider buyers ≥ 5/10/20 and net SOL ≥ 2/5/10. On random launches this gives −0.02 to −0.04 per trade. One cell (n = 7) is +0.63 in total (R1 −0.14 / R2 +0.77): noise.

## 7. Strategy ideas for us at our landing

| # | idea (rule) | numbers (slip on; R1 / R2) | confidence | main risk / label |
|---|---|---|---|---|
| 1 | **Hold 5–10 s instead of eos1, for any selection with real demand.** Ordinary buyers arrive over 2–10 s. | ORACLE L75, fast snipers removed: eos1 +0.30 (+0.78/−0.48) → 5 s +3.79 (+3.38/+0.41) → 10 s +4.48 (+3.84/+0.64). Random launches: no help (eos1 −23.9, 10 s −23.8). | Medium (needs a tradable selection) | Only helps if the selection is good. |
| 2 | **Its exit: dump at ~3 s unless up; if up, sell half and hold the rest.** | ORACLE L75, fast snipers removed: half at 1.15× then 8 s +3.93 (+2.93/+1.00); 15% trailing stop +4.60 (+4.04/+0.56); plain 3 s +3.81 (+3.06/+0.76). Random launches: −21 to −24 for every exit. | Low–Medium | No exit fixes a weak selection. |
| 3 | **Find its pick signal off-chain** (news, celebrity and trend names; first-of-name; deployer reputation) and snipe with the guard. | Not tradable yet. The best create-time rule lost: R1→R2 −0.25, R2→R1 −8.8 at L75. | Low | Needs an X or news data feed. |
| 4 | **Deployer list from its attempts.** | L45 +1.63 (+0.18/+1.45); fast snipers removed −0.78 (−0.63/−0.15). | — | **Rejected: depends on 9qz7cWBq, Anubis51, HVE8996r, 6y5cGrki and FiFawH** |
| 5 | **Copy its buys 0.15–5 s later, with or without a demand check.** | −2 to −5% per trade in every variant, both periods. | — | **Rejected: the demand is already priced in by ~0.5 s** |
| 6 | **Infrastructure we can borrow** (no PnL claim): durable nonce on every buy with a unique marker account per copy; parallel sends to several tip services; tip ≈ 1.5–2% of size; the guard should *fail* the tx; no priority-only copy. Its failed buys and guard no-ops cost it 20.6 SOL in 61 h, 23% of its gross. | Its costs (MEASURED) | High (as engineering advice) | Send-path changes need your explicit OK. |

**Bottom line:** FiFawH is a genuine, profitable, generic-demand sniper, and its picks really do attract many unrelated buyers. That value can only be captured inside the create slot, by a picker as good as its own, and no create-time feature we have reproduces its picks. Nothing derived from it is tradable for us now without depending on specific bots. The useful lessons are ideas 1 and 6.

**Caveats:**
- USDC and other quote assets are valued at today's prices (SOL = 106 USD).
- R1 placement is a proxy.
- Slip limits are known only up to about 2 s after our buy.
- Other-quoted launches (25% of its buys) and mayhem launches are excluded from the copyability sims.
- `copy/part6*` (the earlier R2-only, no-slip run) is superseded by `copy/q6*`.

Files are in /home/moiz/sniper/ops/overnight/fifaw/:
- FiFawH_snipes.html
- copy/q6_tables.txt
- copy/q7_tests.txt
- copy/fast_snipers.json
- copy/q6.py
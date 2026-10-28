# E2X1 recon — facts, lots, exact reconciliation, bot split (agent "recon", 10-28 ~21:30 PKT)
Wallet E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb. Code: this folder (r0…r14). Data + shared tables: /home/moiz/sniper-data/e2x1_dissect/recon/
(lots.pkl v2 + README.md). Days in PKT: **D0** = 10-26 20:00 → 10-27 20:00, **D1** = 10-27 20:00 → 10-28 20:00. Everything MEASURED unless marked INFERRED.

## 1. Every signature (MEASURED)
getSignaturesForAddress: 7,000 sigs back to 10-26 16:01. Recordings hold 6,628 of them; the other 34 in D0+D1 were fetched by getTransaction.
| | D0 | D1 |
|---|---|---|
| signatures | 3,305 | 3,238 |
| his buys (all pump `buy_exact_sol_in`) | 1,321 | 1,344 |
| his sells (pump `sell`; PumpSwap sells after graduation) | 1,326 (11) | 1,340 (22) |
| his failed txs (sell 3012 = account already closed: duplicate sell copies; buy IllegalOwner/6042 = duplicate buy copies) | 585 | 519 |
| pump `DistributeFeeToHolders` paying him (he held a "holder" token) | 67 | 33 |
| dust / spam transfers in | 6 | 2 |
| recorder missed (fetched): 1 sell (D1) + 33 third-party txs | | |

**Engine (MEASURED, same for all bots):** one signer; direct pump.fun program calls (no router); CU price fixed 1,000,000 µlamports (no code in it);
CU limit 145,000 buy / 100,000 sell / 140,000 PumpSwap sell; **durable nonce** on every landed buy and sell (pool of ≥15 nonce accounts; a lot's
sell uses the SAME nonce account as its buy: 42/42 sampled lots vs 10 % shuffled); each order is fanned out as copies on astralane (tip 0.0011 SOL)
and Helius (tip 0.00001 SOL) — which copy lands is a race, not a bot code; a third, non-nonce Helius copy (tip 0.001) lands ~6 %.
Buy slippage: min_tokens_out ≈ 0.62–0.85 × filled; sells: full balance, min_sol_output = 0. Duplicate copies fail cheaply (0.105–0.15 mSOL each).

## 2. Lamport reconciliation (MEASURED, public-RPC pre/post balances at the day boundaries)
| line (SOL) | D0 | D1 |
|---|---|---|
| start balance (pre of first tx) | 233.892566308 | 288.913332171 |
| end balance (post of last tx) | 288.913332171 | 348.668530109 |
| **chain change** | **+55.020765863** | **+59.755197938** |
| buys (TradeEvent sol + pump fee + creator fee) | −709.414000000 | −627.675000000 |
| sells on curve (sol − fees) | +743.237301467 | +653.927085383 |
| sells on PumpSwap (net) | +22.767766203 | +35.842574519 |
| tx fees (landed) / tips | −0.337820 / −2.349090 | −0.343180 / −2.356430 |
| failed-tx fees | −0.066040 | −0.057850 |
| token-account rent paid / returned | −1.999656 / +2.007225 | −2.033966 / +2.027911 |
| curve realloc rent paid by buys (650,240 lamports each) | −0.001300 | −0.005852 |
| **= trading total** | **+53.844386390** | **+59.325292382** |
| holder-fee distributions in | +1.174779640 | +0.429905498 |
| dust in / one 0.00158 transfer from 3wLSzgWk… | +0.000018 / +0.001581 | +0.000000058 / 0 |
| **predicted change** | +55.020765863 | +59.755197938 |
| **RESIDUAL** | **0 lamports** | **0 lamports** |
**No transfers out at all** (no payouts, unlike haqq): the balance just grows (234 → 349 SOL in 48 h). 84 recorded txs re-fetched from RPC: 0 mismatches.

## 3. Bot split (MEASURED)
**Size code.** Every buy spends an exact mSOL amount = round(f × curve vSOL just after one trade T, 1 mSOL), f ∈ {0.7 %, 1.0 %, 1.3 %, 1.5 %},
capped at 1.000 SOL. Hits (D0+D1): 0.7 % 1,084, 1.0 % 541, 1.3 % 237, 1.5 % 103 lots; same test with off-grid f (±0.03 pt) hits only 7–9 % (chance).
The code switches **exactly at token age 30 s and 120 s** (confusion: age<30 s → 0.7/1.3 % in all 1,298 tiered lots; 30–120 s → 1.0/1.5 % in 632 of 651;
misfits sit at 30–31 s and 120–135 s = clock rounding). ≥120 s: not vSOL-tiered (1.000 cap 58 %, rest 0.1–1.0).
1.3 %/1.5 % are a "boost" of the same bands, used on ~half the lots until 10-27 ~09:30 PKT, never after (config change).
Sell-matches-buy: the only sell-side per-position field is the nonce account (matches its buy 100 %), and nonce accounts are shared by all three bands
→ **one engine with three age-band configs** (INFERRED from shared nonce pool, signer, relays, CU settings), named:
- **FRESH** — token age < 30 s, size 0.7 % of vSOL (~0.28 SOL)
- **MINUTE** — age 30–120 s, size 1.0 % (~0.42 SOL)
- **OLD** — age ≥ 120 s, size up to 1 SOL (median 1.000)

### Exact per-bot P&L
Cash view = every in-day trading lamport assigned via its lot (failed txs with no lot by token age); **sums to the trading total exactly (0 lamports)**.
Lot view = lots bought in the day, followed to their close (4 open at the end, marked at the last curve price).
| bot | D1 cash | D1 lots | D1 lot P&L | mSOL/lot | ret on SOL in | win | hold p10/50/90 s | D0 cash | D0 lot P&L |
|---|---|---|---|---|---|---|---|---|---|
| FRESH | **+12.147** | 689 | +13.076 | +19.0 | +6.4 % | 45 % | 1/18/1140 | +23.208 | +21.835 |
| MINUTE | **+17.624** | 322 | +18.343 | +57.0 | +12.5 % | 49 % | 3/34/248 | +11.525 | +11.289 |
| OLD | **+29.555** | 333 | +27.927 | +83.9 | +10.1 % | 51 % | 10/83/1020 | +19.111 | +19.613 |
| **ALL** | **+59.325** (= trading total) | 1,344 | +59.345 | +44.2 | +9.5 % | 48 % | 2/34/550 | **+53.844** | +52.737 |
Median lot ≈ break-even (gross p50 −2 %…+1 %); P&L is tail-driven (top 5 % of lots ≈ 75–140 % of a bot's P&L).

### Profile (D1)
| | FRESH | MINUTE | OLD |
|---|---|---|---|
| age at entry p10/50/90 s | 3/8/21 | 36/62/105 | 136/310/1584 |
| curve vSOL at entry p50 | 41.5 | 43.2 | 51.3 |
| trigger T in his own slot / 1 slot earlier | 61 % / 37 % | 60 % / 38 % | (no size code) |
| T is a buy; T size p50 | 65 %; 0.77 SOL | 69 %; 0.80 SOL | |
| other trades in his slot before him p50; his block index p50 | 2; 195 | 2; 190 | 2; 183 |
| exits: astralane normal / Helius 0.001 / **30-min timeout** (Helius 10k) | 637/23/27 | 301/17/3 | 305/24/3 |
| first sell after buy, slots p10/50 | 4/84 | 12/157 | 47/394 |
| failed txs per lot | 0.38 | 0.38 | 0.41 |
| lots / mints (re-entries, never 2 open on one mint) | 689/624 | 322/272 | 333/217 |
**Same-slot landing (MEASURED):** in ~60 % of tiered lots the trade his size was computed from sits in HIS slot, 2 trades (median) before him —
he reads the slot as it is produced and lands in it. 30-min timeout exits (hold = 1,800 s, Helius 10k tip) lose −14…−56 % each.

### Examples (5+ per bot; more in r14.txt)
FRESH: [HjVGL4ku +1.81](https://gmgn.ai/sol/token/HjVGL4kuW2H6eeY2sTxwp5VCUhCJChzZBHc3aQ3EMKRS) ([buy](https://solscan.io/tx/5Sppy44pvPTDhwDxf3DW4KFi84CDKunXkS2U7RCHRqc6ZWp3euRLptzyn5pbmiRtyJp8hgKDbaB31sAZycMXZbU2)),
[6Z7gZron +1.29](https://gmgn.ai/sol/token/6Z7gZronuV3yymwijK8YuUBCBykRvJMvAMrQvaPRpump) ([buy](https://solscan.io/tx/UABw5JNyN4zzX2nfZMD3qjjgrr96YQfejaqNzfE2XqmZXmpARfb3jnXZBMDE5uBbsz7egcsp4ue2oAeTktCio95)),
[8SRwhhP8 +1.05](https://gmgn.ai/sol/token/8SRwhhP8uF41FfvdLYdBZVX3oPxGKhLDSRSPu9thpump) ([buy](https://solscan.io/tx/4Jo39pAL3pudtYakMLq513RUVfDEPf1VVVPDrvvn5D397n9fkounDyUeCao63HEBKGbBtLU2AiynprgEoPqjJSk3)),
[JAPau9E9 −0.007](https://gmgn.ai/sol/token/JAPau9E9STqUKNebv62KnKWbrKb5EZPeYNfBWyzCpump) ([buy](https://solscan.io/tx/5cWb35Ytbus9oo9aasftiCKdFwkK1Aqd88PvfxFoioboFvdWFCc5CVxJtokys6QYtvVMwgA7wVbRPGqwpFTMRnZn)),
[Gs6SgRps −0.56, 30-min timeout](https://gmgn.ai/sol/token/Gs6SgRpsMU83NymbKBy8bHXeGNe7vPiBdygWpsCjpump) ([buy](https://solscan.io/tx/2NY4AWv1gJU44J3ida7SFhH4aq8nPAgx5EJ96YRuuM89yKJuZYQ5Ho7KE1QZZ4bLKXcyThT9w1TbX7GaT1UjwWP7)).
MINUTE: [DzfDFonC +3.05](https://gmgn.ai/sol/token/DzfDFonCVcF4zygAFPRZpf85Pw7EUKwKWETmfsbzpump) ([buy](https://solscan.io/tx/AGtPV1APLMZ5zERm3UjTAL5s4pn5BxhNMFBA8prJzEDREhAtREsu7R28zbzidr2DgeoMMrHuwcmJhYSaZJBhE6R)),
[DA4yHG5X +1.63](https://gmgn.ai/sol/token/DA4yHG5XdywG7ZSAWffKZet3cH7JQamjEJwRC3vVXN5X) ([buy](https://solscan.io/tx/5HJKvCND8LNChE6r6Af4Xe7tfT2DggDXYbrieWTKRZt2suhpNFDsDvNXVmK98G9nLPwCSsqpgH1HE4HTw4SpmTPz)),
[DsA98kXc +1.27](https://gmgn.ai/sol/token/DsA98kXcJEsQqpm7rLBVdjBjGeQRDeXqUjeK8PMKmYc8) ([buy](https://solscan.io/tx/67WBhm3GWMm9CoAiripxe5TxmfrReS95DXFNTg8iXjNVmFe35hYsxqoGXP2WpVfnk7UVei8pbrUy2f)),
[3SRbYWAz −0.005](https://gmgn.ai/sol/token/3SRbYWAzz7XSiMx3dkgfNyB7m6xGwdfdPy8LAtwrpump) ([buy](https://solscan.io/tx/4qbjMJFHXTb6iDQyV2ZHPWmdWduiuvg5AyT7zthFLonUGdMGT1b45GE7gwt9R3UFvyWzNKWmSu4xNURwL9KFZ4gb)),
[FzFXw2SX −0.86](https://gmgn.ai/sol/token/FzFXw2SXuwVcFbp2yjeJUKC9WYg5Yjgaj8zPB2YFpump) ([buy](https://solscan.io/tx/5u8ry7CaZjDrjfhx6MKZ4VMtY8HMcZmAiq6Jmk1JpwkKQGzTpKHBHEEyh5kZFo1PKMRaoK3pC7TjrhnFu9QNhoae)).
OLD: [9xe8DXZ5 +2.52](https://gmgn.ai/sol/token/9xe8DXZ5AkqJwYy34P2yKw34yVSGGepSAHQLWdJFpump) ([buy](https://solscan.io/tx/366LsXscfczCSxRZF2P3Zw25FksnkQJ36xPELiqEwceCCzyMZMV9odBRKrauX5eD47GbLfWGeKfivWRJyr9ELVh2)),
[GJyNrRBN +1.80](https://gmgn.ai/sol/token/GJyNrRBNt85m7DX7PYJBHo9sjmpTxMEQYfRbvMoYpump) ([buy](https://solscan.io/tx/3LnNsrXhjH6jroxv3prnVRcNJAxw6wbxsQZm2TsUcEpEfA4oXf7QctQgnhtz8WhjuuU3KLLivspaT7bzuif4WVVB)),
[2j4iCzjv +1.64](https://gmgn.ai/sol/token/2j4iCzjv54siy96t6ySqGmatbhSwr4bmNRRzpJ8C9KBV) ([buy](https://solscan.io/tx/m37cpJL8knDngnDKfC3VNyh2RRsu7TZWaDH7Dkpuw9keDgbzgMkQmiDBzJDup5DKTL6tGaJYu63PcrN9jsp2PEb)),
[88yvLXXJ +0.002](https://gmgn.ai/sol/token/88yvLXXJYgV8VeNdHU2WNj4GmDmbbsBFXpvgr8gkpump) ([buy](https://solscan.io/tx/3PHDZWaJrrZCd1A9mX6hqER3mAeGQ8WmqLUYXNH8L9LsK1w1o7GGmsxWLcMFjvNg2DTM7a2agUEdV6W6G4BSkioK)),
[FKZs8DGs −0.80](https://gmgn.ai/sol/token/FKZs8DGsStrao4Xg2ThtrQrT6asVmVivLNsK1Brhpump) ([buy](https://solscan.io/tx/2iCYBXtSC5aAXJeH8BGE8pWdprfYm1hRPkyKqNwPq7dKxhNyCq9eHDwPdQUnNbgqQrvpqP2GhCzJYB5pNiFWhMow)).

## 4. Wallets around him (MEASURED, D1 lots, tape)
- **Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ** — same tip triple (astralane 1.1M / Helius 10k / Helius 1M), 760 shared mints, sells in the SAME slot as him in 98 % of shared exits (before him 46 %, after 54 %) → likely a sibling wallet of the same operator (INFERRED). Worth adding to the dissection.
- Followers (trade after him, both buy and sell, mostly same slot): 3iawEZGf… (599 of 1,340 lots; Helius 5k), Hj4uACn8… (338), FiYZPbS4… (272), AZ45pUnD… (153).

## 5. Overlap (MEASURED)
| our run | window PKT | our fills | fill tokens he traded | fills within his hold ±60 s | our armed tokens he traded |
|---|---|---|---|---|---|
| FRA r27 | 10-28 02:26–14:26 | 200 | 45 of 195 | 40 | 189 of 877 |
| FRA r28 | 10-28 14:31–20:02 | 78 | 18 of 73 | 15 | 69 of 319 |
| AMS r25/r26/r27 | 10-27 02:58–17:36 | 287 | 56 of 280 | 50 | 184 of 957 |
~20 % of our fills are on his tokens at the same time; examples in r12.txt.
**haqqiUUX:** traded 57 % of his tokens (D1: 504 of 888); in D1, 621 of his 1,344 lots have a haqq buy within his hold ±60 s
(FRESH 438, MINUTE 158, OLD 25) — the two overlap mostly on fresh tokens.

## Files
r6.txt reconciliation · r11.txt bot P&L · r12.txt overlap · r13 (r13_ixdata.py) nonce / ix args from the RPC sample · r14.txt profiles + examples.
Open: public RPC here runs ~0.15 tx/s, so nonce/ix-args rest on a sample (r8, 70 D1 lots per bot, still filling).

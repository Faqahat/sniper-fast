# Wallet DF7eRXHn: what it does differently

Wallet `DF7eRXHnvRQ9QeVCrdfS56a7RpBD6se6mgPvzApHPNr9` ([Solscan](https://solscan.io/account/DF7eRXHnvRQ9QeVCrdfS56a7RpBD6se6mgPvzApHPNr9)). Study 10-25, ~23:30 PKT. Read-only: our raw recording, ~150 read-only `getTransaction` calls and 17 `getSignaturesForAddress` pages. Nothing sent, no server touched.

- **Window:** his whole trading life inside our recording. First trade 10-24 15:52 PKT, window end 10-25 19:07 PKT: **27.2 h**. The wallet was created 10-22 16:12; it made no trades before 10-24 15:52.
- **Labels:** MEASURED = counted on chain. INFERRED = my reading or a model. All "ms" use the block clock from HOW_PROS_LAND.md (INFERRED, ±17 ms for a single trade; medians are fine).
- **P&L** = his exact SOL balance changes from the recorder, plus WSOL from his 18 PumpSwap exits (read by RPC). It includes pump fees, tx fees, tips and failed txs.

## Verdict

**He has no secret signal. He wins on cost, volume and being first.**

- He makes many small, cheap trades and is usually first or second in line.
- He made **+25.2 SOL in 27.2 h** (≈ +22 SOL/day) on 4,328 filled buys. That is **+5.8 mSOL per trade = +1.9% of 0.3 SOL**, the same as GMGN's +1.89%. MEASURED.
- The typical trade loses (median −3.6 mSOL, 45% win). **The best 5% of trades make +50 SOL; the other 95% lose −23.7 SOL.** The profit is a fat tail of winners he lets run.

**What we could copy, ranked by value**

| # | Difference | His numbers (MEASURED) | Ours | Value / caveat |
|---|---|---|---|---|
| 1 | **Cheap round trip** | Buy 1.17 mSOL: one 0.0011 SOL budget per copy, paid as CU price OR tip, never both. Sell 0.21 mSOL: 0.0001 priority + 0.0001 tip. Failed buys add 0.27 per trip. **All-in ≈ 1.65 mSOL** | 4.3–4.9 mSOL | With our costs his +26.3 SOL of trades would be ~+12 SOL. Costs are **half his edge**. Engine change, free, needs OK. |
| 2 | **Trades far leaders** (US / Asia / other) | 31% of his buys and **+10.4 SOL = 41% of his profit**. +7.0 mSOL per trade there, his best location. FRA +4.4, AMS +6.9 | We land late there (fastest 10%: 87 ms US, 134 ms Asia) | Needs engines in more regions. His fastest 10% there is ~21 ms (HOW_PROS_LAND E7). Costs money. |
| 3 | **Only be 1st or 2nd** | Dump backruns by bots ahead of him: 0 → **+7.6** mSOL (97% fill); 1 → +5.0; 2 → +2.4; 3 → +0.8; 4+ → **−3.4** | We are first on 27% of fires | On the 58 dumps where we both fired he made **−2.5 mSOL/trade**. Our dumps are crowded; even he loses on them. Speed + avoid crowded dumps. |
| 4 | **More trigger types, not just dumps** | Wake-up buy (first ≥0.5 SOL buy after ≥10 quiet slots) **+6.8**/trade · big-buy follow **+9.8** (38% fail) · dump in a token ≤10 s old **+6.8** · other dumps +4.6 | Dumps only, ~21 fires/h | Same edge on 2× the trades. **Needs paper at OUR landing first** (INFERRED transfer). |
| 5 | **Let winners run** | Holds ≤2.5 s +6.0/trade; 13–60 slots +5.6; 61–300 −0.2; **>1 min +7.6 (37% win)**; 21 held through graduation **+3.75 SOL** (+178 mSOL each) | 5-slot exit, no stop | The tail is half his money. Our learned "hold winners" exit failed OOS before; retest with his trigger mix only. |
| 6 | **Re-enter the same token** | 45% of buys are repeats on a token he already traded (up to 23 on one token). Re-entry 1–2: +5.2/trade; 3+: +2.4 | One entry | This is GMGN's "$30/$60/$120… ladder": each entry is 0.3 SOL, and GMGN adds them up per token. |
| 7 | **Tx shape** | Legacy, 1,029 B; CU limit = used + ~10 k (uses 58 k); CreateAccountWithSeed; own buy program; 3 nonce accounts for buys and 3 for sells | v0, 967 B, 100 k limit, ~93 k used, ATA program ×2 | ≤1–3 ms (INFERRED), cheaper per CU. Small. |
| – | **Do NOT copy yet: loose slippage** | min-out ~18% below the price just before his buy (median; p10 3%, p90 26%; 88 sampled buys; args MEASURED, curve math INFERRED) | +5% guard | Our 61 h guard sweep: looser guards lose at our speed. Only after we land faster. |

**Not different:**
- **Size:** 99.6% of his buys are exactly 0.3 SOL (`BuyExactQuoteInV3`, SOL in). We use 0.35.
- **Landing setup:** the same as the hicu-family template in HOW_PROS_LAND.md: durable nonce, ~22 services, no-tip copy at ~15 M µL.
- **Same operator:** he is one of ≥6 wallets with this template. 30% of his buys have a sibling wallet (EprLoV21, HLU8QbLd…) buying the same token within ±3 slots.

---

## 1. What he trades (entry trigger)

Trigger = what happened on the token in the 3 slots before his buy (MEASURED, my classes).
- "dump" = a sell ≥ 0.3 SOL that moved the price ≥ 3%.
- "wake-up" = a ≥ 0.5 SOL buy after ≥ 10 slots with no trades.
- "Bots ahead" = other wallets' buys between the trigger and his buy.

| Trigger | Attempts | Filled | Failed | Net SOL | mSOL / fill | Win | Trigger size p50 | ms after trigger p25/50/75 | Bots ahead p50 | Curve SOL p50 | Token age p50 | Hold p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Dump backrun | 2,284 | 1,911 | 16% | **+8.82** | +4.6 | 43% | 1.59 SOL | 27 / 41 / 63 | 1 | 6.8 | 45 s | 7.6 s |
| Wake-up buy | 979 | 750 | 23% | **+5.10** | +6.8 | 50% | 1.00 | 27 / 39 / 58 | 1 | 10.0 | 11 min | 26 s |
| Dump, token ≤ 10 s old | 888 | 683 | 23% | **+4.65** | +6.8 | 43% | 2.31 | 25 / 38 / 65 | 2 | 9.8 | 5 s | 2.6 s |
| Big-buy follow (not quiet) | 812 | 503 | **38%** | **+4.94** | +9.8 | 47% | 1.32 | 22 / 36 / 57 | 2 | 17.7 | 2.3 min | 13 s |
| Other (no big trade in 3 slots) | 376 | 366 | 3% | +1.30 | +3.6 | 43% | – | – | – | 7.3 | 4.4 min | 17 s |
| Launch ≤ 10 s, no dump | 163 | 115 | 29% | +0.36 | +3.1 | 43% | – | – | – | 7.9 | 5 s | 3 s |
| **All** | **5,502** | **4,328** | **21%** | **+25.16** | **+5.8** | **45%** | | | | | | |

- Fresh tokens only: 99% were created inside our recording. Median age 55 s; 25% are under 14 s old.
- The trade just before his buy is another buy in 78% of cases, usually another dip bot: EprLoV21 (his sibling), GKd5, 8PgC, haqq, HkQ7. He is usually 2nd in the crowd, not alone.

**Dump backruns by dump size and order** (MEASURED):

| | n | Fill | mSOL / fill |
|---|---|---|---|
| Dump 0.3–1 SOL | 503 | 87% | 0.0 |
| Dump 1–2 SOL | 896 | 85% | **+6.9** |
| Dump 2–4 SOL | 668 | 82% | +3.4 |
| Dump 4+ SOL | 220 | 73% | +10.8 |
| 0 bots ahead | 779 | **97%** | **+7.6** |
| 1 bot ahead | 668 | 85% | +5.0 |
| 2 ahead | 390 | 72% | +2.4 |
| 3 ahead | 212 | 74% | +0.8 |
| 4+ ahead | 238 | 63% | **−3.4** |

**By curve size and token age** (all triggers; mSOL per fill):
- **Curve size:** <3 SOL +6.1 · 3–10 SOL +5.5 · 10–25 SOL **+8.6** · 25–50 SOL +0.3 · ≥50 SOL −1.3. Above 25 SOL the edge is gone, except the graduation rides (section 3).
- **Token age:** <15 s +7.7 · 15–60 s +7.2 · 1–5 min +1.2 · 5–30 min −0.2 · >30 min +8.3.

## 2. Size and the "ladder"

- **Every buy is 0.3 SOL:** 4,312 of 4,328 fills. The other 16 are 0.5–3 SOL.
- **There is no size ladder.** GMGN's $30 / $60 / $120 / $180 / $220 / $300 steps are 1, 2, 4, 6, 7 and 10 separate 0.3 SOL entries on the same token, added up per token.
  - He traded 2,606 tokens, 2.1 attempts per token on average, at most 23 on one token.
  - Each entry is sold before the next one. Only 11 times did he hold 2 entries at once, sold together.
- **One sell per entry:** a full exit with `CloseAccount`. He never sells in chunks (4,296 of 4,307 exits are a single sell).

## 3. Exits

| Hold | Fills | Net SOL | mSOL / fill | Win |
|---|---|---|---|---|
| ≤ 12 slots (~2.5 s) | 1,313 | +7.85 | +6.0 | 50% |
| 13–60 slots | 1,144 | +6.36 | +5.6 | 47% |
| 61–300 slots | 733 | −0.13 | −0.2 | 43% |
| > 300 slots (> 1 min) | 1,117 | +8.51 | +7.6 | 37% |
| Graduated, sold on PumpSwap for WSOL | 21 | **+3.75** | **+178** | 86% |

- **Hold time:** p10 2.0 s, p25 2.3 s, median 6.9 s, p75 70 s, p90 252 s.
- **A floor of ~9 slots:** only 1.7% are sold earlier, and 29% are sold at 9–12 slots. MEASURED.
- **The rule after that is not clean TP/SL.** INFERRED reading:
  - Short holds sell after 4–10 quiet slots (flow stops).
  - Mid holds sell right after someone else's sell, ~5% below the peak since entry (trailing-like).
  - Long holds sell anywhere from −23% to +47%.
- **Graduation rides:** he bought tokens near the end of the curve (median 53 SOL in the curve) and rode the migration. Example: buy [4kY9Ruor…](https://solscan.io/tx/4kY9RuorLmVy9jSsMABdnEAvbxo4CwsSR7R3STyu87AgStVEqAzCuAq7teF2v4SpUaRQ6pTGuWsh33PVxiMUxCDy) → PumpSwap sell [2aA5C1ye…](https://solscan.io/tx/2aA5C1yEVtrM23Ccx83vvdQk2UP33p6j3g1yqnsYKVeFnP5KmBe8YM13UFSWMEpqzoPr83ezXeBVZ43RXJB8Tida), +0.35 SOL.

## 4. P&L, costs and failures (MEASURED)

- **Net +25.16 SOL in 27.2 h** = 4,328 round trips (+26.33) − failed buys (−1.17). Fee rebates (`DistributeFeeToHolders`) add +0.35; failed sells cost −0.14.
- After the window (10-25 19:07–22:32 PKT) his native SOL fell 1.6. WSOL exits are not counted in that figure.
- **Per filled trade:** mean +6.1 mSOL, median −3.6, p10 −51, p90 +64.
- **Gross price edge** ≈ 10 mSOL = 3.4% per trade (INFERRED). That is before pump fees (~2.8 mSOL a round trip) and his tx costs (~1.65).

**Where his money comes from:**

| By leader location (buy's slot) | Attempts | Fill | Net SOL | mSOL / fill |
|---|---|---|---|---|
| FRA | 1,984 | 73% | +6.33 | +4.4 |
| AMS | 1,194 | 80% | +6.59 | +6.9 |
| other EU | 607 | 70% | +1.81 | +4.3 |
| **Far (US / Asia / other)** | **1,717** | **87%** | **+10.44** | **+7.0** |

| By leader client | Attempts | Fill | mSOL / fill |
|---|---|---|---|
| BAM | 2,021 | 90% | +4.1 |
| Harmonic | 1,620 | **50%** | +4.9 |
| Jito-own | 921 | 90% | +4.7 |
| Firedancer | 482 | 92% | +10.5 |
| Jito-relayer | 347 | 92% | +8.0 |

On Harmonic his failed buys land (fill 50%). On the other clients only ~10% of attempts land as failures.

**Failed buys** (1,174 = 21% of landed attempts):
- All are slippage: pump 6042 `BuySlippageBelowMinTokensOut`.
- **Costs:** 984 × 0.0011 SOL (the no-tip copy pays its full priority fee) · 64 × 0.001 · 79 × 0.0001 · 39 × 0.000005 (tip copies: the tip transfer reverts, so only the CU-price part is paid).
- **Total 1.17 SOL**, or 0.27 mSOL per filled trade.
- The owner's example [zTMEcr8a…](https://solscan.io/tx/zTMEcr8aFPQFdK7wQ5hiX4kRqFGtxYscPzjP9CP2EfZCqfL9MQroURYsWznbL3gzAvQQYpvLwtwmJEo9Gpm2CoD) is a no-tip copy that failed at 44.9 k CU. It got 3.2% fewer tokens than its minimum.

**Other failed txs** (cheap, 265 in total):
- 136 duplicate sells after the position was already closed (`InvalidAccountData`, 3.6 k CU, 0.000105 SOL).
- 69 sells with `InsufficientFunds`.
- 63 buys stopped by the **Lighthouse assert on the no-tip copy** (custom 6001 at instruction 1, **996 CU**), e.g. [4z5BahHn…](https://solscan.io/tx/4z5BahHnU3kAGVJxns5rqg7RuuWhVySD5sKyGyXvNDB2SywVcEoUKbKiG2PdtRkasiK6HUtMKq3LZa2FdeEMVDi9).

## 5. How his txs land

**Buy tx** (RPC sample: 81 filled buys, 6 failed, 3 Lighthouse fails; MEASURED):

| Item | Him | Us |
|---|---|---|
| Version / size | legacy, **1,029 B** (tip copies) / 1,060 B (no-tip copy), 23–24 keys, no lookup table | v0, 967 B, 23 keys |
| Order | AdvanceNonce → [Lighthouse, no-tip copy only] → CU limit → CU price → CreateAccountWithSeed → own program `41Pr4X…` (InitializeAccount3 + `BuyExactQuoteInV3` + TransferChecked inside) → [tip] | nonce, CU limit / price, Lighthouse guard, ATA program ×2, buy; tip placed before the buy (E4) |
| Buy args | 17 B: SOL in (0.3) u64, min tokens out u64, flag u8 | – |
| CU limit / used | **65–87 k / 54–66 k** (limit = used + ~10 k, set per tx). Median used 58.3 k | 100 k / ~93 k |
| Loaded-data limit | not set | not set |
| Durable nonce | 100%. **3 nonce accounts for buys** (HcqWdy…, 3C6d4n…, 67uACY…) and **3 for sells** (FS39gX…, 9nzURB…, nPuCgA…) | 100% since r11, 8 accounts |
| Fee per landed copy | **always ≈ 0.0011 SOL**, split per route (below) | 5 M µL on every copy + a tip |

**Fee shape per copy** (sample; one budget, split per route):

| Shape | Routes seen |
|---|---|
| No tip, CU price ≈ 0.0011 SOL ÷ CU limit (12.7–16.9 M µL) + Lighthouse guard | "none" (direct / staked RPC) |
| Tip **0.0011**, CU price 0 | helius, bolt, flashblock, 0slot, blockrazor, unk-D1Mc, unk-MANKAZ, everstake, also nozomi / soyas / landx / falcon / speedlanding / astralane / bloxroute |
| Tip **0.001** + CU price ≈ 0.0001 SOL (1.3–1.5 M µL) | stellium, landx, nextblock, falcon, unk-Sp, bloxroute, soyas, nozomi |
| Tip **0.0001** + CU price ≈ 0.001 SOL (13–15 M µL) | astralane, speedlanding, glaive, 0slot |
| Tip 0.00001 + CU price ≈ 0.0011 SOL | unk-AS6R, unk-AVwZ |

- Some services appear in two shapes, so he sends more than one copy to them. He sends at least ~25 copies per buy (INFERRED lower bound; copies that never land leave no trace).
- **The landed copy always costs the same 0.0011 SOL**, whichever service wins.

**Which copy landed** (4,328 fills, 22 services): none 64%, helius 13%, astralane 5%, landx 4%, glaive 3%, soyas 2.4%, bolt 1.7%, unk-D1Mc 1.6%, nozomi 1.5%. Then stellium, speedlanding, flashblock, falcon, unk-Sp, 0slot, bloxroute, unk-AVwZ, unk-MANKAZ, unk-AS6R, blockrazor, nextblock, everstake.

**Speed on dump backruns** (2,089 reactions to dumps ≥ 1 SOL; ms after the dump):
- **Overall:** same slot 67%, filled 80%.
- **By route** (filled, median ms): soyas 26, falcon 28, glaive 30, none 42, helius 43, speedlanding 40, astralane 50, landx 50, bolt 57, nozomi 62.
- **By leader client** (median ms · same slot · route that won):
  - BAM: 47 · 65% · none.
  - Harmonic: 42 · 69% · none.
  - Jito-own: 51 · 66% · helius, then none and astralane.
  - Firedancer: 47 · 74% · none, astralane, landx.
  - Jito-relayer: 47 · 71% · helius 64, soyas 21, bolt 13.
- **Fastest 10%** (HOW_PROS_LAND E5/E7): 14–17 ms on every client; **21 ms on US and Asia leaders**. He runs engines in several regions.

**Sell tx:**
- **Shape:** legacy, 894–943 B. Nonce → CU limit 100 k → CU price 1 M µL (= 0.0001 SOL) → own sell program `4DvQwk6W…` (pump `Sell`) → Token-2022 CloseAccount → [tip 0.0001] → Lighthouse.
- **Graduated tokens:** sold through PumpSwap `pAMMBay6…`, with CU limit 200 k at 0.5 M µL.
- **Landed sell routes:** astralane 36%, speedlanding 32%, none 24%, glaive 5%, helius 2%.
- **Cost:** 0.21 mSOL per sell (fee 0.108 + tip 0.104).

## 6. Throughput and concurrency (MEASURED)

- **Buy attempts per minute:** mean **3.4**, p50 3, p90 7, max 15. 11% of minutes have no attempt.
- **Volume:** ≈ 200 attempts and 160 fills an hour, ≈ 3,800 fills a day. We make ~21 fires an hour.
- **Open positions:** mean 2.6, max 13. That is ~0.8 SOL deployed on average out of a ~21 SOL balance.
  - Time share: 0 open 13%, 1–3 open 59%, 4–6 open 24%.
  - With only 3 buy nonce accounts, at most 3 buys can be in flight at once (INFERRED).
- **His sends that land:** 79% fill / 21% fail of landed attempts; on dump backruns 84%. Copies that never landed are invisible, so the real send success rate is unknown.

## 7. Him vs us on the same dumps

We matched 58 dumps where both of us landed a reaction (our runs 1–17, both servers; MEASURED order, ms INFERRED):
- **He was ahead of us on 78%.** His median 34.5 ms, ours 50.2.
- **His buy filled on 62%, ours on 24%.** We had 44 buy fails and 14 fills.
- **His P&L on these 58: −0.14 SOL (−2.5 mSOL/trade).** On the dumps we pick, even this faster and cheaper bot does not make money.
- His landed routes there: none 37, helius 10, astralane 3, plus D1Mc, MANKAZ, bolt, flashblock, glaive.

Example dump [3KWKtPMG…](https://solscan.io/tx/3KWKtPMGjA9GN4NNPZ5tRSRZbb4kebbbvZayr349sB9ksDaMCWQAoBMxS2RCxRniK3C1Azpg2Hru9RzHXWohBoBv) (Jito-own leader):
- Him via unk-D1Mc, +31 ms, filled, +22 mSOL: [3MvNbhqw…](https://solscan.io/tx/3MvNbhqwoUSuur9dHucGJ1TT5NiVuTdx6EXS2j6LQDM61YjwvpKYWcPETonUgiZLdWZzWyJnzYWhgg8sgJj5ydgU)
- Us, +68 ms, failed: [n3yRnh6A…](https://solscan.io/tx/n3yRnh6Abo1SKB1T44Kg6NtK9YJtgQYWjTHUrxLFTv4HnYLVb4a6fHKEWiQgaoYKTVrmBe3pciy64kpeJ5hZfgS)

## 8. Examples (Solscan)

| Case | Trigger | His buy | Sell | Result |
|---|---|---|---|---|
| Dump backrun, first in line, landx | sell 3.77 SOL, −20% [2vgdHr73…](https://solscan.io/tx/2vgdHr73H1mH3DdoYtZrX2i8pPsA84GJn8hgTPhs4pjhQuZppxmVxWtBXxnHpR3Z7pACn5ocdfhr4JSWW4WWUTP1) | +27 ms [4WdzKJa9…](https://solscan.io/tx/4WdzKJa9TScX4jtjFonaD1EaBhDf4ZwN6XSCs5QxyftjoUeqAX7bwTJ92XwG3ntYZdWPNjaFbT6zcbnTUHFbhK9G) | 2.4 s [5799DfQB…](https://solscan.io/tx/5799DfQBDiu6vqe7oE3mvJm86c6XWFuq19pjngHYhgiYUKELkX3dduMxeMgWzMYNR7r2bhTBj3jyySjEqmS1oGqy) | +87.5 mSOL |
| Dump on a 3 s old token, helius | sell 2.18 SOL [Pup6w4TY…](https://solscan.io/tx/Pup6w4TYPsdgkC5z9bSA1rpfKCVWFS35xxnT9mLhSoksQcUBu3qxSzkHdc8mVAnUSCQRKvmb4z1wt2DjrPvidQD) | +20 ms [5MEPaVQ7…](https://solscan.io/tx/5MEPaVQ7FQCLEBakzJseXtxfg9ScF7bcimjqBbhKs2vsx4LPToCZ8NgP9soF4TPBSJN3FYnoVubsZyLz2FMK1iH1) | 3.0 s [5kFEdmXC…](https://solscan.io/tx/5kFEdmXCMwxRHc5NBnBz91SAD5Fv479T5AjyQAvwpiGNkZ5F4M2WHg3nB72nUQA7nax9KHpQW8SmpSSvYqx6nbJk) | +46.6 mSOL |
| Wake-up buy, helius | 2.96 SOL buy after a quiet spell [4g2SafxjH…](https://solscan.io/tx/4g2SafxjHX8qt8jX5y8CsbQM7iqwHfXV5rcc2vrQJTYJyee4v28taZfcLUF6Dtdw37fASay6DVpsratL5bSqVzeW) | +51 ms [Cy4LATyM…](https://solscan.io/tx/Cy4LATyMYkeVD7pgb9PrDxiX5aPLJuDqiNo8JGc1amEGsW3Fx6xUwY8oentNt6Qg4rJ4wzoDLyMsaGgtd3XQFNH) | 20 s [3rfhbYoj…](https://solscan.io/tx/3rfhbYojcvMXFQrwncaDWMQ3GFGBz4p3dajKydfKApFMyJgiguRUCM34FjFv4eufqiK5kAeNFkzhRmxnN21oMb3D) | +18.0 mSOL |
| Big-buy follow, unk-D1Mc | 2.96 SOL buy [4piVQcT3…](https://solscan.io/tx/4piVQcT35yp88PAxCJRQYQvkAhKXaB1MfhmsNwL3dUoTk7uok8bmB8QZZtG6we5c2Ln7Fv8gwjXu8HeLjxzzihK3) | +27 ms [5ExzcVuq…](https://solscan.io/tx/5ExzcVuqU9b2NP1rsaXCMQhnEVyWGWsevrzY3puNkbhqbH24aHhpURWEwx88AEKc5mVyra4Ui26vgZQe5m4De1CU) | 121 s [5kQzCsK2…](https://solscan.io/tx/5kQzCsK269aJS9UFQGojKmsFQjNouH6MC4GwJajVxh6Y7qgU7KnJWeDRXdYGvCjLf8vM3a7hEqSBuxEWmGtZyr8q) | +4.8 mSOL |
| Crowded dump (5 bots ahead), no-tip copy | [2N7AwSpU…](https://solscan.io/tx/2N7AwSpUmmwHFiUxUM71BPzzqqZkgX4vLfieBhJnsg3HPG1zR9BvB8gWUPBFTu2WXD6oLqvu3PJkMvmY9mZ1XWdV) | next slot [2ENR2avf…](https://solscan.io/tx/2ENR2avf8u7TMqgCH49agHV4TBm3yAXtJfwh9ni8PrSHZBSwjhiZGMrTbyBJVUhRiYETak9yBYiouuYURM3DBsnx) | [2v7hZE1a…](https://solscan.io/tx/2v7hZE1awRAMXu3x8JgYo4QZX6xpn15Ad5zLpuK5DdbhDDy6SKCFg2uCn4huJ7tzjvfdwwj4m3Lcynh84j24phnB) | −17.5 mSOL |
| Tip-copy anatomy (astralane 0.0011, CU price 0) | – | [4P2fxmdc…](https://solscan.io/tx/4P2fxmdcVBBnhGKsivmbtGwkKmho6BeAXvt1Ejh1KrVYPia19wDBh1Panievm8hc6uDv7QaNy4XBXPW5H5VgFw2M) | – | – |
| No-tip copy anatomy (16.1 M µL, Lighthouse) | – | [dhpZUrNr…](https://solscan.io/tx/dhpZUrNrtAc1MKAyR6g7R8me5uBuejQX3GJM7maNdrwoW5kVN4huigeP2887sJomwoM6LVw8fHtKWyeqywT9yRT) | – | – |
| Sell anatomy (speedlanding 0.0001) | – | – | [2Wzrd4zR…](https://solscan.io/tx/2Wzrd4zRYmJfrEzh6DW44wPnFr6u65QXWo9xf5cf9tFBgQXxQodMYspcpXjGgBFMeFhUQf1VUSB5kxpzVU1K4fBL) | – |
| Duplicate sell after close (3.6 k CU) | – | – | [4zUpm6rc…](https://solscan.io/tx/4zUpm6rctNxdcTQmDTRZ97tGMVpsRZbk2iWMrjPf5Y5wQteYBTqLCaSZ33eAu6RFMXfyaxAJubyNzuPRovVS9Lu6) | fail, 0.000105 SOL |

## Method and limits

**Scripts:** `ops/dip/speed/landing2/df7e/`. Data is in `/home/moiz/sniper-data/landing2/df7e/`.
- `d1_extract.py`: his txs (failed too) and every curve trade on his 2,606 tokens, from the x1 compact files of R3 + R4.
- `raw_scan.sh` → `raw_sd.json`: exact SOL deltas per tx from the raw recorder (runs 10-23, 10-24, 10-25).
- `d3_trades.py`: one row per buy: trigger context, curve size, age, paired sell, hold.
- `d4_analyze.py`: trigger classes and P&L tables (`d4.txt`).
- `d5_amm.py`: PumpSwap exits (WSOL proceeds, RPC).
- `d2_tx.py`: tx anatomy (RPC, cached).
- `d6_guard.py`: decodes his buy args (min-out).

**Limits:**
- Trigger classes are my definitions (INFERRED). His real trigger can be a mix or a model.
- "Bots ahead" counts every buyer between the trigger and him.
- The block clock is INFERRED. Order and positions are exact.
- Copies that never land are invisible: copy count and send success are lower bounds.
- The 58 same-dump trades are a small sample.
- 27 h of one wallet's life: no out-of-sample period.

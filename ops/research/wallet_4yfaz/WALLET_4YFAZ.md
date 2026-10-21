# Wallet 4yFAz7dp…QrG3: what it does now (2026-10-21)

Read-only study of the pump.fun sniper `4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3`. All numbers come from on-chain data (public RPC). Nothing here is from GMGN.

## Summary

- **It makes money, and more than before.** Last 24 h (10-20 14:35 → 10-21 14:35 UTC): **185 trades, +50.9 SOL** after all tx fees and tips. Failed-tx fees cost about 1.2 SOL more, so the net is **about +49.7 SOL/day**, on 413 SOL bought.
  - Per trade: mean **+0.27 SOL**, but the median is **−0.01 SOL** and the win rate is **50%**. The profit is a fat tail: without the best 3 trades it is +33 SOL, without the best 10 it is +12 SOL.
  - The 24–48 h before that was quieter (48 trades, +13.4 SOL; that window's data is only partly fetched).
  - Last 6 h: 51 trades, +6.7 SOL. The rate swings by hour: 03 UTC was +13 SOL from 7 trades, 16–17 UTC was slightly negative.
- **Activity: about 8 launches per hour** (2–13 per hour). One buy per launch, never re-entered.
- **Sizes come in fixed tiers that track his conviction.** The tiers are 1.19 / 1.45 / 2.18 / 2.96 / 6.72 SOL (median 2.18).
  - The small tier (< 1.5 SOL) is break-even: 68 trades, −0.4 SOL, 29% win.
  - The bigger tiers make the money: 1.5–2.5 SOL +18.5, 2.5–3.5 SOL +18.7, > 3.5 SOL +14.1 (75% win).
  - The size goes up with the dev buy (median dev 1.5 / 0.6 / 3.0 / 6.9 SOL across the tiers). A repeat creator usually gets the same size each time.
- **Fast exit, partial ladder.**
  - He holds a median of **4 s** (19 slots). 48% of trades are fully closed within 5 s. A cluster of exits sits at about **40 s**, which looks like a time stop; those 31 trades lost −5.1 SOL.
  - The first sell came 0–1 slots after the buy in 45 of 185 trades. The first leg was about **30% of the tokens** in 89 trades and 100% in 82.
  - Ladder trades (2–10 sells) made **+44 SOL** at a 66% win rate. Single full sells (n = 82) made +6.8 SOL at a 29% win rate, mostly quick cuts.
- **Landing: same slot as the create 80% of the time, +1 slot 20%, never later** (96 launches with full data).
  - He was the **first outside trader on the mint in 68%** of launches.
  - Our feed saw his buy a median of **~30 ms after the create** (6–155 ms, 18 launches in our logs). That is the same speed class as our new routes (17–35 ms). **He is not faster than us any more.**
  - His fill is **1.24× the post-dev price** (median). On bundled launches where he was the first outsider it is 1.34×: the creator bundle had already pushed the price 1.24×. On launches with no bundle it is 1.065×. His own size adds about 6%.
- **He pays a lot to land: about 2.7% of the SOL he buys** (11.3 SOL of fees and tips on 413 SOL).
  - He pays **either** a priority fee **or** a tip, and the amount grows with size: about 0.015 SOL on 1.45 SOL buys, 0.05 on 2.18, and 0.06–0.14 on 2.96.
  - He sends each buy over many routes (Helius, Nozomi, landx, Jito, speedlanding, bolt, soyas, 0slot, nextblock, a "b1oom…" vanity account set). The copies that do not land fail cheaply (mean failed-tx fee 0.0007 SOL). 66% of his signatures fail, and in the sample those were mostly duplicate copies, not trades he called off.
- **Selection: he takes about 1% of the launches our engine passes, and no simple create-time rule copies it.**
  - Of the 1,424 launches our engines watched (base filter + close leader, groups A–E), he bought **18**. On those 18 he **lost −1.05 SOL** in real PnL. His profit comes from launches outside our watched set or outside our log windows.
  - **28% of his picks have a dev buy below 0.5 SOL**, which our base filter rejects (+4.0 SOL on 26 of them).
  - No rule built from his preferences held up out of sample on our model (table 5).
- **Rule #2 overlap: 4 of 76 rule #2 launches.**
  - His real PnL on them: +0.02, +0.36, +0.53, −0.17 SOL.
  - On two of them our model refused the buy (the price was 1.19× and 1.39× when we would have landed). He got about 1.08× because he landed before the outsiders who pushed the price.

**Recommendations**

1. **Copy: size by conviction plus a scale-out exit** (paper first, zero cost). Sell about 30% into the first pop, ladder the rest, and use a hard time stop well below 40 s (his 40 s exits lose). This is where most of his edge shows. Confidence medium.
2. **Copy: multi-route sending with cheap duplicate failure.** He sends the same buy through 5–10 relays, each with its own small tip, and the losers fail for ~0.0007 SOL. We already have multi-path routing built (arbx-lat, not run live). Confidence medium. It is a send-path change, so it needs the owner's OK.
3. **Paper-test fee in proportion to size (~2% of size)** on contested (bundled) launches. That is what he pays, and fees help. Confidence medium-low.
4. **Do not try to copy his selection with a create-time rule.** His picks inside our universe lost money, and the rules built from his preferences failed out of sample. Confidence medium-high.
   - A "copy his buy when our feed sees it" trigger is not worth it. We would see his buy at about the moment our own buy would land, so we would always sit behind him.
5. Optional, low value: track his creator list. 7 creators were picked more than once, and they get stable sizes. But only 16 of 96 picks were repeats.

## 1. Activity and PnL (`trades.py`, `trades.txt`)

Window: wallet signatures 10-19 07:15 → 10-21 14:35 UTC (6,578 signatures: 2,204 succeeded, 4,374 failed). Every successful tx in the last ~23 h was fetched. Older successful txs were fetched only partly (1,200 of 2,204 in total), so the "24–48 h" row is incomplete.

PnL per trade = sells × (1 − pump fee) − buys × (1 + pump fee) − the tx fees and tips of its buy and sell txs. ATA rent is excluded (the close txs reclaim it). Failed-tx fees are estimated from a 148-tx sample (mean 0.0007 SOL) and shown separately.

| window | trades | /h | SOL in | PnL (SOL) | failed-tx fees | mean | median | win |
|---|---|---|---|---|---|---|---|---|
| last 24 h | 185 | 7.7 | 413.1 | **+50.85** | ~1.19 | +0.275 | −0.008 | 50% |
| 24–48 h ago (partial) | 48 | 2.0* | 125.9 | +13.43 | ~1.62 | +0.280 | | 58% |
| last 6 h | 51 | 8.5 | 115.4 | +6.67 | ~0.27 | +0.131 | | 47% |

\* undercounted: the older txs were not all fetched.

- Biggest wins (24 h): +7.14 (6.72 SOL in, 9 sells, 12 s), +5.60 (2.18 in, 1 sell), +5.09 (5.14 in, 8 sells), +3.65, +3.52, +3.42.
- Biggest losses: −1.50 (6.8 in, held 39 s), −1.00, −0.94, −0.85, −0.74, −0.68.
- Return per trade: p10 −18%, median −0.4%, p90 +38%.

| size tier (SOL in) | n | PnL | mean return | win |
|---|---|---|---|---|
| < 1.5 (1.19 / 1.45) | 68 | −0.44 | −0.4% | 29% |
| 1.5–2.5 (2.18) | 55 | +18.53 | +15.8% | 58% |
| 2.5–3.5 (2.96) | 54 | +18.67 | +11.7% | 63% |
| > 3.5 (4.1 / 6.72) | 8 | +14.10 | +30.8% | 75% |

| exit | n | PnL | mean | win | median hold |
|---|---|---|---|---|---|
| single sell | 82 | +6.81 | +0.083 | 29% | 2 s |
| ladder (2–10 sells) | 103 | +44.05 | +0.428 | 66% | 6 s |

- Hold time distribution (24 h): 0–4 s 89, 5–9 s 29, 10–14 s 18, 15–29 s 12, 30–39 s 8, ≥ 40 s 29 (the 40–41 s group looks like a time stop; the 31 trades held ≥ 38 s lost −5.09 SOL).
- First sell: 0 slots after the buy 23 times, 1 slot 22, 9–11 slots 56, ≥ 30 slots 42.
- First leg size: about 30% of the tokens (89 trades) or 100% (82 trades).

## 2. Landing and execution

**Buy tx (all 234 bought mints):**

| item | value |
|---|---|
| CU limit | ~51,000–58,000 (tight, set per tx; ~55k used) |
| priority fee | median 0.0013 SOL, p90 0.06 SOL (CU price up to ~1e9 µL) |
| tip | median 0.0013 SOL, p90 0.06 SOL |
| fee + tip by size | 1.45 SOL → ~0.015; 2.18 → ~0.05; 2.96 → 0.06–0.14 (about 2% of size on contested launches) |
| total landing cost | 11.3 SOL on 413 SOL bought (2.7%) |
| buy path | direct pump `buy` (+ATA create) 54%, his program `2YAbTp…` 40%, `BehnpC…` 3%; guard program `L2TExM…` on some |
| sell path | his program `FCdY3U…` + guard `L2TExM…` (this program was his BUY path on 10-13; it now sells) |

Routes on the buy txs that landed (the tip account in the landed copy):

| route | buys |
|---|---|
| none (priority fee only) | 84 |
| helius | 40 |
| nozomi | 38 |
| landx | 32 |
| jito | 8 |
| speedlanding | 8 |
| soyas | 5 |
| "b1oom…/B1ooM…" vanity set (unlabelled) | 5 |
| bolt | 5 |
| nextblock | 2 |
| 0slot | 2 |

**Failed txs (66% of his signatures):**

- Mean fee 0.0007 SOL (median 0.000006).
- In a 40-tx sample:
  - 25 failed with System-program error 0 (account already in use). This looks like a dedupe account that lets only one route copy execute (*inference*).
  - 5 failed with pump slippage error 6042.
  - 4 failed with his guard program's error.
- 13 of the 40 were on mints he did buy. The other 27 mostly had no pump mint in their static keys, so the attempted mint is unknown.

**Landing vs the create** (`features.py`, 96 launches with the create and the mint's signature list; `landing_summary.txt`):

| slot delta | n | his PnL | per trade | win |
|---|---|---|---|---|
| 0 (create slot) | 77 | +21.8 | +0.29 | 53% |
| +1 | 19 | +7.0 | +0.37 | 68% |

| outside txs of the mint ahead of him | n | PnL | per trade | win |
|---|---|---|---|---|
| 0 (he is first outsider) | 65 | +26.8 | +0.41 | 63% |
| 1 | 20 | +0.1 | +0.00 | 42% |
| 2–3 | 11 | +1.9 | | |

- Fill vs the post-dev price: median **1.24×** (p25 1.07, p75 1.39). His own size adds a median 1.06×.
- Bundled launches where he was first outsider (n = 31): the bundle pushed the price a median 1.24× before him, his fill was 1.34×, PnL +19.0 SOL.
- No bundle and he was first (n = 34): fill 1.065×, PnL +7.8 SOL.
- In raw block order he is NOT right behind the bundle. The median gap is 96 tx indexes (votes and other txs included); only 2 of 77 were directly behind it. He is first on the mint, not first in the block.
- **Our feed timing on his buys** (RACE obs, 18 launches in our logs): we saw his tx a median **~30 ms after the create** (min 6, max 155 ms). On 9 of those 18 he was the first outside tx our feed saw, and on several his failed duplicate copies were visible too. That is the same speed class as our new routes (17–35 ms).

## 3. Selection

**What his launches look like** (96 picks with create data vs our watched universe of 1,424, groups A–E; `feat.txt`):

| feature | his picks | our watched universe | his PnL by value |
|---|---|---|---|
| create tip: none | 47% | 39% | +17.7 (n 44) |
| create tip: lunar | 12% | 19% | +5.1 (n 11) |
| host ipfs.io / j7tracker / uxento | 44% / 26% / 16% | 44% / 34% / 7% | +16.7 / +5.6 / +4.0 |
| dev < 0.5 SOL | 28% | 0% (base filter) | +4.0 (n 26) |
| dev 2–3 SOL | 9% | 9% | +7.1 (n 8) |
| glued bundle txs 0 / 1–2 / 3+ | 49% / 24% / 27% | 46% / 17% / 37% | +8.1 / +13.2 / +7.5 |
| create_v2 | 98% | – | |

- His pick rate in our engines' DETECT logs (80 of his buys fall inside our log windows; all 80 were detected): **1.2% of `pass` launches** (57 of 4,780) and 0.2% of `skip_dev_low` (22 of 10,557).
- Repeat creators: 7 creators were picked more than once (16 of 96 picks). Sizes by creator are stable: DWHEZ8 2.96/2.96, BoEVpc 2.96/2.96, EgJoaE 6.72/6.72, 54yAKt 1.19/1.54/1.19.
- Biggest winners: dev 8.9 / 2.5 / 0.0 / 2.0 / 4.9 / 3.1 SOL, mixed tip and host, all on him as first outsider (one with 3 ahead). Nothing in common at create time.

**Overlap with our watched launches** (`overlap.py`, `overlap.txt`):

| group | watched | he bought | rule #2 | he bought of rule #2 |
|---|---|---|---|---|
| A (10-20 evening) | 325 | 4 | 19 | 1 |
| B (older + overnight) | 553 | 5 | 31 | 1 |
| C (10-21 morning) | 54 | 1 | 1 | 0 |
| D (paper 10:13–12:37) | 252 | 4 | 16 | 1 |
| E (paper 12:37–13:26) | 240 | 4 | 10 | 1 |

- On those 18 launches our model's S+2 PnL was +0.057 per launch (+1.03 SOL in total), against +0.003 on the launches he skipped. **His real PnL on the same 18 was −1.05 SOL** (correlation with our model 0.65).

| rule #2 launch | his size | his fill | his real PnL | our model p2 (price when we would land) |
|---|---|---|---|---|
| 73XDo27C (B) | 1.17 | 1.031 | +0.022 | +0.114 (1.00×) |
| FShDX4yU (A) | 1.43 | 1.042 | +0.357 | +0.661 (1.09×) |
| 8E4L9kgP (D) | 2.93 | 1.077 | +0.533 | −0.011 refused (1.19×) |
| 7BEUZH3E (E) | 2.93 | 1.076 | −0.170 | −0.011 refused (1.39×) |

**A rule built from his preferences, tested on our model** (`rule_test.txt`; A = in-sample, B–E held out; per-launch S+2 PnL on the realistic landing model):

| rule | A | B | C | D | E | held-out B–E: n / per launch / total |
|---|---|---|---|---|---|---|
| all watched | −0.000 | +0.005 | +0.039 | −0.005 | +0.007 | 1099 / +0.005 / +5.18 |
| rule #2 | +0.133 | +0.058 | +0.080 | +0.007 | −0.007 | 58 / +0.033 / +1.91 |
| his picks (oracle) | +0.029 | +0.085 | +0.200 | +0.080 | −0.009 | 14 / +0.065 / +0.91 |
| no create tip + ipfs.io + early | −0.013 | +0.004 | −0.013 | −0.001 | +0.041 | 212 / +0.011 / +2.24 |
| no bundle + dev 2–5 + early | +0.077 | −0.026 | −0.036 | +0.035 | +0.129 | 86 / +0.052 / +4.51 |
| bundle of 1 tx + early | −0.046 | −0.013 | −0.073 | −0.030 | +0.123 | 38 / +0.002 / +0.06 |
| dev 2–3 + early | +0.051 | −0.053 | −0.036 | −0.055 | +0.074 | 73 / −0.013 / −0.93 |
| uxento + early | +0.005 | −0.051 | +0.301 | −0.018 | −0.020 | 47 / −0.023 / −1.08 |

- The only positive candidate ("no bundle + dev 2–5") is tail-driven: held-out median −0.038, win 27%, −0.34 SOL without the best 3.
- **No implementable selection rule.**

## 4. What we could copy cheaply

1. **Exit ladder** (biggest lever, zero cost to paper-test). Sell ~30% into the first pop (his first leg is ~30% in about half of trades), ladder the rest over ~5–15 s, and use a hard stop well before 40 s. His ladder trades: +44 SOL at a 66% win rate.
2. **Size by conviction.** He sizes 2–3 SOL when the creator bundle or dev is substantial (dev ~2–7 SOL, or a known creator) and 1.2–1.5 SOL otherwise, and the small tier is break-even. For us this means sizing up only on the rule #2 shapes, not more launches.
3. **Multi-route send with a dedupe account.** Each copy carries a small tip to a different relay (Helius, Nozomi, landx, Jito, speedlanding, bolt, soyas, 0slot, nextblock, b1oom). Only one executes, and the rest fail for ~0.0007 SOL. Needs the owner's OK (send path).
4. **Fee about 2% of size on contested launches**, and priority-only (no tip) on clean ones. 84 of his 234 landed buys had no tip at all.
5. **Tight CU limit** (~55k, set per tx). We use 100k; that matters only if the fee is set per CU.
6. Not worth copying:
   - his selection (no create-time rule)
   - a "follow his buy" trigger (he lands about when we do)
   - his creator list (few repeats)

## How it was measured

- Scripts are in this folder. Data are in `/home/moiz/sniper-data/research/wallet_4yfaz/` (not committed). Only public RPC (publicnode, then api.mainnet-beta for older data), at most 3 threads. Nothing was sent, and nothing on the server was started or stopped. The server was used only for one light grep of `DETECT … first=1` lines from the two current paper logs.
- `sigs.py`: the wallet's signatures for 55 h.
- `txs.py`: every successful tx (pump TradeEvents, fees, CU, tips, programs, block tx index). Its `--failed` mode samples failed txs.
- `trades.py`: round trips and PnL.
- `creates.py`: each bought mint's create tx and its signature list up to his buy (with block tx index). 127 of 211 were fetched before the rate limit forced a stop. 96 joined with full data: newest first, so they cover about the last 17 h.
- `tidx_backfill.py`: his buy's block index for older rows.
- `features.py`: landing and features tables.
- `overlap.py`: his trades inside our recorded watched launches (block recordings S..S+2, wallet match).
- `detect_univ.py`: our engines' verdict for his mints, from DETECT lines.
- Rule test: `rule_test.txt`, using `filters3_rows.json` (FILTERS.md model, unchanged).
- Caveats:
  - Fill and position use the mint's signature list. Glued bundle = successful txs at consecutive block indexes after the create.
  - The "first outsider" count includes outside sells and failed txs are excluded.
  - Feed timings come from our engine's RACE obs lines (ms after the create in our feed).
  - The "b1oom" route label is a guess from vanity addresses.
  - The 24–48 h PnL is incomplete.

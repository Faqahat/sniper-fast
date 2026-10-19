# Creator bundles vs independent snipers (2026-10-18), read-only research

Everything here was read-only: RPC reads only (getSignaturesForAddress, getBlock, getTransaction, getSlotLeaders) plus GETs to the public Jito bundle explorer. No transactions were sent and no process was started or stopped apart from these scripts.
Full output: `report.txt`. Re-run: `analyze.py creates.jsonl wallets.jsonl bundles.json > report.txt`.

## Sample
- 3041 pump.fun creates. 2816 are random, every create in the ~4.5 h window up to slot 458,375,184 (from getSignaturesForAddress on the mint authority TSLvdd1). 195 are the old /root/fill launches. 30 are the launches behind our 28 live buys (the FIRE lines in live_bl_*.log).
- For each create I rebuilt the create slot S and the next produced block S+1 from getBlock, in transaction order.
- 961 creates had at least one buyer in S or S+1. **704 had at least 2 buyers in the create slot itself** (558 of those are random creates). That is above the 300 target.
- 4578 buy events in total: 381 independent wallets and 699 bundle wallets. I traced the history of every buyer and creator: transactions before the buy (capped at 1000), first-seen time, and SOL funders.
- Leader client of the create slot: BAM 38%, Harmonic 29%, Jito-Solana 24%, Firedancer 8%.

## How each buyer was classified (signals; share of the rank-0..2 front positions where each fires)
- (d) **glued**: part of the unbroken run of buys of this mint directly after the create, at +1..+4. Fires on 66%. Run length is a median of 3.
- (d*) **same Jito bundle as the create**, confirmed by bundles.jito.wtf: 51%. Bundles are 2 to 5 txs with the create first, and the tip usually comes from a buyer wallet. The explorer confirms 236/265 glued creates on BAM leaders, 151/157 on Jito-Solana and 60/63 on Firedancer, but only 64/204 on Harmonic, which builds its own blocks.
- (c) wallet reused on 2 or more launches by the same creator cluster: 31%.
- (d') same tip sender as the create tx: 29%.
- (f) wallet born within 120 s of the bundle wallets or the creator: 20%.
- (b) funding link (funded by the creator or the creator's funder, shares a funding tx, or shares a non-hub funder with a linked co-buyer): 19%.
- (e) fresh wallet (10 or fewer prior txs, first seen up to 30 min before the launch): 4%.
- (a) buy inside the create tx itself: about 0%. Creators bundle the buys as separate txs.
- **96.8% of glued buys are confirmed by at least one other signal.** Only 1.3% of all buys are glued with no other link.
- Independents look like bots: 88% buy launches from 3 or more creators, and 59% have 1000 or more prior txs.
- Uncertainty:
  - Funding was traced one hop only. Address history only reaches back to the RPC's ledger start (slot 457.43M, about 4.4 days).
  - Funders that fund wallets under 4 or more creators (exchanges and farms, 42 of them) are ignored as links.
  - 3.9% of buys are AMBIG_reuse: wallets that bought the same creator twice but landed late. They are either the creator's team or dev-tracker snipers, and are excluded from both sides.

## VERDICT: the front block is the creator's bundle
| population | creator bundle | ambiguous | independent |
|---|---|---|---|
| rank 0-2 after create, all creates (n=2454) | **68%** | 2.5% | **29%** |
| rank 0-2, creates with >=2 same-slot buyers (n=2031) | **81%** | 1.7% | 17% |
| rank 0-2, random creates only (n=1957) | 66% | 2.2% | 31% |
| all buyers filling <=1.10x (n=1515) | 55% | 4.9% | 40% |
| all buyers filling <=1.05x (n=1036) | 52% | 5.9% | 42% |
| next block (S+1) buyers | 0.4% | 7.7% | 91% |

- **The earlier "co_rank0 = 1.036x, Lunar dominant" finding** (same 154 fill-sample launches): 77% of rank-0 buys were creator bundles, filling at a median 1.04x. 20% were independent; they filled at 1.006x, but only on launches that had no bundle.
- **Lunar Lander is a creator tool, not a sniper edge.**
  - 420 create txs (14% of all creates) tip Lunar themselves, and 330 of those carry a glued bundle.
  - 628 of the 644 Lunar-tipped buys are bundle-class (97.5%).
  - The 14 independents who tipped Lunar landed a median 290 txs after the create and were first only 7% of the time.
  - Do not buy Lunar access to snipe.
- 23% of all creates (20% of random ones) carry a glued creator bundle. That is **73% of the creates that attract any buyer**. Median bundle SOL ahead of the first sniper: 3.8 SOL.

## What an independent sniper can actually get
- First independent buyer per create (n=806): it lands same-slot 64% of the time, a median 76 txs after the create.
- Fill a tiny buy (like ours) would get at each queue position:
  - **First independent:** p10 1.00x, median 1.19x, p75 1.29x. 41% of these fill at 1.10x or better.
  - **First independent, no bundle ahead (37% of cases): about 1.00x.** Second independent: 1.04x. Third: 1.07x.
  - **First independent, bundle ahead (63%): p10 1.13x, median 1.24x.** Second independent: 1.33x. Third: 1.36x.
- A 1.12x fill cap therefore reverts almost every bundled launch, whatever the send path. That matches the 0/20 result in the live test with the 1.12x cap.
- dev >= 8 SOL: the first independent fills at about 1.00x (n=21).

## Independent snipers by sender (S + S+1). Full tables and fail counts are in report.txt
| sender | n | %same-slot | med offset | %first-indep | fill p50 | tiny-fill p50 | med tip SOL | med prio SOL |
|---|---|---|---|---|---|---|---|---|
| Helius dual-route (tip >=0.0002) | 402 | 51 | 110 | **43** | 1.29 | - | 0.001 | 0.0002 |
| Helius SWQoS-only (tip <0.0002) | 478 | 36 | 185 | 18 | 1.23 | - | 0.00001 | 0.00001 |
| none (no tip: direct/staked/Harmonic) | 546 | 50 | 127 | 34 | 1.32 | 1.29 | - | 0.00025 |
| Nozomi | 212 | 46 | 129 | 38 | 1.26 | 1.24 | 0.001 | 0.0006 |
| Jito | 175 | 50 | 105 | 38 | 1.23 | 1.22 | 0.0002 | ~0 |
| Astralane | 150 | 57 | 110 | 47 | 1.31 | 1.29 | 0.001 | 0.0016 |
| 0slot | 89 | 39 | 168 | 18 | 1.29 | 1.28 | 0.0001 | ~0 |
| FlashBlock | 60 | 62 | 113 | 12 | 1.21 | 1.21 | 0.0001 | ~0 |
| Lunar (independent only) | 14 | 14 | 290 | 7 | 1.48 | 1.46 | 0.001 | 0.0001 |
| **OURS constant-k staked-rpc** | 21 | 62 | 186 | 5 of 21 first | **1.31** | | 0 | 0.00024 |
| **OURS Nozomi** | 7 | 43 | 176 | 1 of 7 first | **1.38** | | 0.002 | 0.00024 |

- Median independent rank is 1 for most senders. Median SOL ahead is 3-5 SOL, and most of that is the bundle.
- **The pooled table is confounded by bot quality.** One operator runs 40 wallets on the Helius SWQoS-only mode (tip 0.00001, cu_price 60k), and that drags down the pooled Helius row.
- Same bot, two senders, compared by median offset (5-15 bots per pair):
  - **Helius is faster than Nozomi in 11 of 14 bots** (by about 24 txs) and faster than Astralane in 11 of 15.
  - Helius and Jito are even (3 vs 3). Jito beats no-tip in 5 of 6.
- Spray races are the cleanest comparison: the same bot and create, sent via several senders (45 bots, 922 races, mostly bots that keep failing).
  - Nozomi lands before Helius in 55% of races (n=74).
  - Stellium lands first most often (52%). It is not in our engine.
  - LandX and 0slot are slowest.
- **The ordering lever is the priority fee.** Inside a slot, a higher fee lands earlier in 0.69 of independent pairs; the tip scores 0.66.
  - Independents paying >=100M µlamports per CU (median 0.015 SOL priority) are first 62% of the time and same-slot 71%.
  - Independents at our tier (1-10M µlamports per CU, about 0.00024 SOL) are first 32% of the time.
  - The top snipers pay 0.003-0.014 SOL in priority or tip: CWiNFAEk, 9qz7cWBq, 8RvtT818 and 4yFAz.
- **4yFAz (clone target)** in this window:
  - 16 buys, first independent on 14. Median offset 50, 10 of 16 same-slot, fill p50 1.09x.
  - Mostly no tip, with a 0.013 SOL median priority fee and median size 2.35 SOL.
  - He sprays each create through Stellium, Helius, Nozomi, LandX and Astralane; 489 of those txs failed in the window.

## By leader client (independents): %first-indep / median offset (n)
| sender | BAM | Harmonic | Jito-Solana | Firedancer |
|---|---|---|---|---|
| Helius dual | **44% / 86 (192)** | 32% / 158 (72) | **53% / 74 (106)** | 29% / 258 (28) |
| Nozomi | 22% / 168 (50) | **46% / 124 (120)** | 35% / 88 (31) | small n |
| Jito | 43% / 92 (74) | 25% / 124 (44) | 46% / 89 (41) | small n |
| Astralane | 46% / 98 (56) | **56% / 132 (45)** | 32% / 130 (28) | 52% / 70 (21) |
| none | 34% / 125 | 37% / 123 | 30% / 158 | 40% / 124 |

- **The best sender does depend on the client.** Helius dual-route and Jito are best on BAM and Jito-Solana leaders, which together are 62% of slots. Nozomi and Astralane are best on Harmonic leaders, which are 29% of slots.
- The fill of the first independent is the same on every client (median about 1.21x).

## Recommendation
1. **Do not buy Lunar Lander.** The 1.04x front fills are creator bundles that land atomically with the create. No sender can get ahead of them.
2. **A/B test live, interleaved per launch in the same window:**
   - Helius Sender in dual-route mode (not swqos_only), tip >= 0.001 SOL.
   - Our current constant-k staked-rpc.
   - Optionally a third arm routed by leader client: Helius on BAM/Jito-Solana leaders, Nozomi on Harmonic leaders.
   - Measure the same-slot share, the offset after the create, rank among independents and the real fill.
   - Separately, raise the priority fee. It is the strongest ordering factor measured: we pay about 0.00024 SOL; winners pay 0.002-0.015 SOL.
   - These are send-path changes and need the owner's OK.
3. **Expected fill, honestly:**
   - Even as the first independent, a creator bundle is ahead in about 63% of contested launches. There the median fill is about 1.24x, and p10 about 1.13x.
   - Without a bundle, the first independent fills at about 1.00x and the second at about 1.04x.
   - Our current median independent rank is 2, giving 1.31x.
   - A realistic target with the best path is a median of about 1.2x overall. A cap of 1.10-1.12x is only reachable on launches without a bundle.
4. **Bundle-aware gate.** The bundle sits at +1..+3 in the same slot, right behind the create, so it is most likely in the same entry/shreds we already decode. Compute the post-bundle curve price before firing, then skip the launch or adjust the cap.

## Confidence and caveats
- **Bundle vs independent:** high confidence. The sample is large and 97% of glued buys are confirmed by an independent signal.
- **Per-sender ranking:** medium-low confidence.
  - Pooled numbers are dominated by a handful of bots per sender.
  - Same-bot comparisons have 5-15 bots per pair.
  - Spray races mostly come from slow, failing bots.
  - We only see buys that landed in S or S+1 (survivorship).
- **Our row:** 28 buys from 2026-10-17, so small n.
- Alpenglow activates 2026-10-21 and BAM goes into maintenance mode. Re-measure after.

## Files
- Scripts: collect.py (creates and blocks), wallets.py (wallet history and funders), bundles.py (Jito explorer), analyze.py, inspect_mint.py, common.py (RPC, tip map built from mod.rs and the catalogue, parsers).
- Data: creates.jsonl (per create: create tx, a window from -3 to +25 txs around it, every tx on the mint in S and S+1), wallets.jsonl, bundles.json, buyers.jsonl (every buy with its class and signals), ours.json, report.txt.

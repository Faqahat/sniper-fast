# Landing study: why ~97% of arbx's bundles do not land, and what would raise the land rate (2026-10-07)

- **Question (owner):** why do about 97% of our sent bundles not land, and what would raise the land rate on the venues we already trade? No new venues.
- **Data:** every sent bundle of FT-006, FT-007, FT-008, FT-010, FT-013 (parts A and B) and FT-012b segment 1 on the frz wallet: **22 segments, 15.11 h, 10,361 sends, 284 landed (2.74%), +1,176,328 lamports net (77,825 lamports/h)**. FT-012b segments 2+ were still running and are not included.
- **Method:** read-only. Core streams (attempts, copies, outcomes, ledger, status) were local; the other streams were pulled from Cherry with rate-limited scp, reduced to what touches our pools, and deleted. Nothing was written to Cherry. 150 public-RPC calls checked a sample. Scripts and extracts: `/home/moiz/arbx-offload/landing-study/` (list at the end).
- **Status:** analysis only; nothing committed, no config changed.

## The answer in five numbers

1. **97.0% of sends fail Jito's simulation; none loses an auction.** In 10,361 sends there are 0 `lost-auction` results; 2.7% land and 0.2% got no verdict or were refused.
   - 28.5% are rejected **within 10 ms of sending** with our profit check `0x4e580002`: the gap was already gone when the block engine received the bundle.
   - 68.2% fail **later, at auction time**, mostly 40–200 ms after sending: 38.7% with the profit check and 29.5% with an uncoded `InstructionError`.
   - 0.4% fail with a venue program error.
   - 4.7% were "accepted" (forwarded) first and then failed a later simulation.
2. **Gap size decides it.**
   - Sends expecting under 20,000 lamports of edge (band 0) land 7.0% of the time and earn 71% of the net.
   - Sends expecting 100,000 lamports or more (bands 2–4) are 40% of all sends (4,153). They landed **once**, and that win realised 3.8% of its quote.
   - No send expecting 75,000 lamports or more landed except that one.
3. **We lose by tens of milliseconds while the bundle travels to the leader, not by slots.**
   - The transaction that closed the gap was in the trigger's own slot for 72% of failed sends, and in the next slot for 20%.
   - It was first seen p50 29 ms **after** our send. 25% were seen before it.
   - Our own winning bundles take p50 82 ms from send to appearing on chain (Jito-led 73 ms, BAM-led 174 ms; p10 38 ms).
4. **Our decision is fast. The wait for state dominates it.**
   - From the trigger's first shred to our send takes p50 14.7 ms. 13.7 ms of that is waiting for Haan's account update, and our own compute takes under 1 ms.
   - Removing the whole wait is modelled at only +5–8% wins. Landing 40 ms sooner is modelled at +18–32%.
5. **Stale-blockhash refusals cost about 4% of net.**
   - 2,244 refusals in 15.1 h: 2.5 a minute (0.6–5.9 per segment; 1.8–3.0 at 2 bundles/s). The executor's counter does not support the "about 10 a minute" in the FT-013 doc.
   - Every one came while the Shyft slot index lagged more than 10 slots: 0 refusals at lag ≤ 10, 2,098 at lag > 20.
   - Estimated cost: 18,454 lamports out of 461,973 net on the 5 segments measured.

**Ranked levers** (details in §6):
1. Stop sending gaps of 75,000–100,000 lamports or more, and give their send slots to small gaps.
2. Build the CU table. Every send used the fallback CU limit, 1.8× the compute it used, and the BAM tip floor is charged per requested CU.
3. Rank the send slot by band, then by recent contestation of the route, instead of first-come.
4. Fix the blockhash source.
5. Test smaller size caps or expected-value sizing.
6. Re-price after in-flight writes.
7. Send through a block engine near the leader.

Changing tip shares and speeding up the decision path rank last.

---

## 1. Where sends fail

**How a send is classed** (outcomes.jsonl `verdicts`, the first `would-fail` decides):
- **DOA:** the profit check failed and the first verdict came under 10 ms after the send (the block engine's check on receipt).
- **Auction-time:** the profit check, or the uncoded `InstructionError`, came 10 ms or more after the send.
- **Venue error:** `0x1794`, `0xbbd`, `0x1795`, `0x1788`, "Program failed to complete".
- **Other:** no verdict, or refused.

### 1a. Overall and by campaign

| campaign | sends | landed | land % | DOA profit-check | auction-time profit-check | auction-time InstructionError | venue error | other | net of wins |
|---|---|---|---|---|---|---|---|---|---|
| FT-006 | 2,404 | 38 | 1.6% | 30.9% | 35.1% | 32.0% | 0.4% | 0.0% | 232,600 |
| FT-007 | 2,093 | 65 | 3.1% | 24.5% | 39.7% | 32.1% | 0.2% | 0.5% | 235,938 |
| FT-008 | 2,282 | 74 | 3.2% | 29.6% | 39.6% | 27.2% | 0.3% | 0.2% | 274,644 |
| FT-010 | 1,528 | 56 | 3.7% | 33.5% | 36.7% | 25.6% | 0.5% | 0.0% | 198,949 |
| FT-012b p1 | 949 | 25 | 2.6% | 25.2% | 44.3% | 27.0% | 0.5% | 0.4% | 140,742 |
| FT-013 (A) | 249 | 7 | 2.8% | 26.9% | 37.8% | 30.9% | 1.6% | 0.0% | 30,482 |
| FT-013b (B) | 856 | 19 | 2.2% | 23.6% | 41.6% | 31.5% | 0.5% | 0.6% | 62,973 |
| **all** | **10,361** | **284** | **2.7%** | **28.5%** | **38.7%** | **29.5%** | **0.4%** | **0.2%** | **1,176,328** |

- **Lose the auction:** 0 of 10,361. No `lost-auction` (`StateAuctionBidRejected` / `WinningBatchBidRejected`) result was ever received.
- **Forwarded but not landed:**
  - 708 sends got at least one `accepted`; 219 of them landed.
  - The other 489 (4.7% of sends) were forwarded and then failed a later simulation: 373 with `InstructionError`, 114 with the profit check.
  - 65 landings had no `accepted` result at all.
  - 26 landings also received a `would-fail` (15 of them `InstructionError`). A `would-fail` is therefore not always final; this study classes every send by its chain outcome first.
- **When the verdict came** (share of each class):

| class | n | <5 ms | 5–10 | 10–20 | 20–40 | 40–60 | 60–100 | 100–150 | 150–200 | 200–400 | ≥400 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| landed (first verdict = accepted) | 235 | 0% | 0.4% | 15.3% | 36.2% | 28.9% | 11.5% | 3.4% | 2.1% | 2.1% | 0% |
| DOA profit check | 2,951 | 86.4% | 13.6% | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| auction-time profit check | 4,007 | 0 | 0 | 3.8% | 1.9% | 4.6% | 38.0% | 21.3% | 15.3% | 11.0% | 4.2% |
| auction-time InstructionError | 3,055 | 0 | 0.3% | 2.6% | 22.6% | 26.5% | 27.7% | 12.0% | 4.7% | 3.4% | 0.3% |

- **The uncoded `InstructionError`:**
  - It is Jito's second wording of a simulation failure: `TxnErr(TransactionError { …, err: InstructionError })`, with neither instruction index nor code (`send/jito.rs::error_code` maps it to `instruction-error`).
  - It never comes on receipt (0.3% under 10 ms). It comes in the same 20–150 ms window as the `accepted` results of landed bundles.
  - The closer was first seen p50 21 ms **before** it, but in 38% of cases only after it. The coded auction-time failures come p50 64 ms after the closer was seen, and only 12% before it.
  - Its share is highest on the smallest gaps (44.5% of band-0 sends, 1.8% of band 4) and on BAM-led slots (35.8% vs 25.6%).
  - Reading: our bundle failed inside the auction or leader pipeline against a competing transaction. That it is our profit check is plausible but cannot be proven from the record.

### 1b. By band (expected edge at the traded size)

| band | sends | landed | land % | DOA | auction-time profit | auction-time IE | net of wins | net per send |
|---|---|---|---|---|---|---|---|---|
| 0 (<20k) | 3,854 | 271 | **7.0%** | 16.8% | 31.3% | 44.5% | 839,106 | 218 |
| 1 (20k–100k) | 2,354 | 12 | 0.5% | 22.7% | 43.0% | 33.2% | 314,521 | 134 |
| 2 (100k–1M) | 2,862 | 1 | 0.03% | 37.7% | 44.1% | 17.4% | 22,701 | 8 |
| 3 (1M–10M) | 1,182 | 0 | 0 | 53.0% | 41.0% | 5.1% | 0 | 0 |
| 4 (≥10M) | 109 | 0 | 0 | 56.0% | 37.6% | 1.8% | 0 | 0 |

Finer, by expected edge (gross − 5,000):

| expected edge (lamports) | sends | wins | land % | net of wins | net per send |
|---|---|---|---|---|---|
| <10k | 2,626 | 241 | 9.18% | 650,027 | 248 |
| 10–20k | 1,228 | 30 | 2.44% | 189,079 | 154 |
| 20–35k | 867 | 7 | 0.81% | 181,760 | 210 |
| 35–50k | 504 | 3 | 0.60% | 70,587 | 140 |
| 50–75k | 562 | 2 | 0.36% | 62,174 | 111 |
| 75–100k | 421 | 0 | 0 | 0 | 0 |
| 100k–1M | 2,862 | 1 | 0.03% | 22,701 | 8 |
| ≥1M | 1,291 | 0 | 0 | 0 | 0 |

- **The one band-2 win** was ft008-p2 attempt 144 (`fone`, 0.05 SOL). It quoted +595,544 and paid the 100,000 tip cap, but realised +22,701.
- **The larger the gap, the more DOA failures:** from 17% in band 0 to 56% in band 4. Big apparent gaps are gone before our bundle reaches the block engine.

### 1c. By leader kind, and band × leader

| leader | sends | landed | land % | DOA | auction-time profit | auction-time IE | net of wins |
|---|---|---|---|---|---|---|---|
| jito | 6,439 | 183 | 2.8% | 30.7% | 40.1% | 25.6% | 974,919 |
| bam | 3,922 | 101 | 2.6% | 24.8% | 36.3% | 35.8% | 201,409 |

| band | Jito-led sends | land % | BAM-led sends | land % |
|---|---|---|---|---|
| 0 | 2,348 | 7.4% | 1,506 | 6.4% |
| 1 | 1,481 | 0.6% | 873 | 0.3% |
| 2 | 1,786 | 0 | 1,076 | 0.1% |
| 3 | 747 | 0 | 435 | 0 |
| 4 | 77 | 0 | 32 | 0 |

- BAM-led wins average 1,994 lamports net against 5,327 for Jito-led wins, because they pay **47% of gross in tips** against 13% on Jito-led slots. Net per send is 51 against 151.
  - The `bam_floor` policy bids at least 0.05 lamports per **requested** CU.
  - Every one of the 10,361 sends used the fallback CU limit (`tx.cu_src = "fallback"`); `data/cu-table.json` is still the interim file with no samples.
  - Landed bundles consumed p50 56% of their CU limit (p10 51%, p90 68%).
- Our bundles reach the chain more slowly on BAM-led slots (§3).
- The `bam_floor` tip policy lands at 4.9% against 2.2% for `share_of_edge`. That gap is band mix: the floor applies to small-gap BAM slots.

### 1d. By venue pair (top 20 by sends)

| buy → sell | sends | landed | land % | DOA | auction-time (both kinds) | net of wins |
|---|---|---|---|---|---|---|
| Dlmm → Dlmm | 3,492 | 119 | 3.4% | 21.3% | 74.9% | 281,567 |
| PumpSwap → Dlmm | 2,081 | 22 | 1.1% | 37.9% | 59.9% | 157,580 |
| Dlmm → PumpSwap | 1,668 | 21 | 1.3% | 36.3% | 61.9% | 194,399 |
| Dlmm → DammV2 | 507 | 12 | 2.4% | 32.3% | 64.6% | 36,305 |
| DammV2 → Dlmm | 477 | 8 | 1.7% | 34.6% | 62.6% | 17,589 |
| RayClmm → Whirlpool | 206 | 3 | 1.5% | 25.7% | 72.3% | 3,791 |
| Dlmm → RayClmm | 183 | 5 | 2.7% | 16.9% | 79.2% | 5,151 |
| Whirlpool → RayClmm | 168 | 4 | 2.4% | 20.2% | 76.8% | 18,013 |
| RayClmm → Dlmm | 151 | 3 | 2.0% | 26.5% | 71.6% | 3,975 |
| Dlmm → RayAmmV4 | 133 | 2 | 1.5% | 25.6% | 71.5% | 3,746 |
| DammV2 → RayCpmm | 121 | 4 | 3.3% | 14.9% | 81.8% | 41,281 |
| Dlmm → Whirlpool | 119 | 3 | 2.5% | 11.8% | 85.7% | 4,623 |
| Whirlpool → Dlmm | 112 | 3 | 2.7% | 15.2% | 81.3% | 5,036 |
| RayAmmV4 → Dlmm | 104 | 5 | 4.8% | 30.8% | 64.5% | 12,562 |
| Dlmm → RayCpmm | 103 | 15 | **14.6%** | 24.3% | 61.1% | 94,205 |
| PumpSwap → DammV2 | 86 | 11 | **12.8%** | 17.4% | 69.8% | 59,527 |
| Whirlpool → Whirlpool | 84 | 5 | 6.0% | 15.5% | 78.6% | 34,159 |
| RayCpmm → Dlmm | 83 | 12 | **14.5%** | 34.9% | 50.6% | 29,808 |
| DammV2 → PumpSwap | 75 | 13 | **17.3%** | 28.0% | 54.6% | 51,655 |
| DammV2 → DammV2 | 73 | 0 | 0 | 28.8% | 71.2% | 0 |

- **PumpSwap ↔ DLMM** is 36% of sends but lands 1.1–1.3%, with the most DOA failures (36–38%). It is the most contested pair.
- **Raydium CPMM against DLMM (14.5–14.6%) and DAMM v2 against PumpSwap (12.8–17.3%)** are small in volume but the best per send. DAMM v2 against DLMM lands only 1.7–2.4%.
- **CLMM/Whirlpool pairs** land 1.5–6%, in line with the older venues.

### 1e. By pool, crowding, trigger, token

- **Pools:**
  - We sent on 834 pools; 641 never won. Two DLMM pools carry the most sends: `3msVd34R…` (1,469 sends, 3.3%) and `HTvjzsfX…` (1,373, 4.7%).
  - The PumpSwap pools with the most sends rarely win: `9GBXHym9…` 0.4%, `BaiHzFqn…` 1.1%, `FB2Dw7CB…` 0/146, `6e3jZLtf…` 0/141, `3NBq9zyn…` 0/136 (64% DOA), `BNG5962Z…` 0/130. Full table in `out/p134.md`.
- **Routes:**
  - 1,717 routes (buy pool, sell pool). 190 routes with 10 or more sends and 0 wins hold 42% of all sends. 194 routes won at least once.
  - Wins still come on routes with long losing streaks, so a hard blacklist costs too much (§6, item 9).
- **Crowding:** the static crowding bucket (WP-00's list, the only source in campaign segments) does not separate wins from losses: 2.7% / 2.6% / 3.3% for buckets 0 / 1 / 2. A live measure does (§4).
- **Trigger kind:**
  - `commit` 2.8% (9,804 sends), `timeout` 1.8% (443), `quiescent` 2.6% (114).
  - Every trigger was a state trigger: no send was triggered from shreds.
- **Token class** (owner's list): meme 1.8% (6,510 sends, 783,690 net), common 4.3% (3,851 sends, 392,638 net).

## 2. Who beat us, and by how much

**Method**, for every one of the 10,077 failed sends (not a sample):
1. **The writers of our two pools after the trigger:**
   - taken from moves.log (`sig slot pool t_ns acct write_version`), in (slot, write version) order after the trigger's own write;
   - kept only if their account update reached us **after** our decision, so they were not in the state we priced;
   - looked at up to 6 slots after the trigger.
2. **The closer:** the first two-pool taker (a transaction writing both our pools: the FT-000 taker, without its 2 s window), else the first arbitrage-like writer, else the first writer.
3. **Each closer's details:**
   - signer, tips and lane from exec.jsonl (all 22 segments; it covers about 70% of watched transactions, OD-1), else rivals.jsonl;
   - first arrival in our shred feeds from txarr.log;
   - block rank from the slot index's non-vote order.
4. **Spot check against the public RPC:**
   - 110 sampled closers: 110/110 exist, succeeded, and are in the recorded slot. Signer equal 56/56 where we had one. 52/110 paid a Jito tip (p50 12,970 lamports). Fees p50 5,000, p90 294,926.
   - 40 same-slot cases (`getBlock`): the closer comes after the trigger 40/40, and the order agrees with the slot index's ranks 40/40.
   - Block-index gap from the trigger to the closer: +1 in 7 of 40 cases, median about +150, at most +768.

### 2a. Was there a closer, and what was it

| | failed | DOA | auction-time | landed |
|---|---|---|---|---|
| sends | 10,077 | 2,951 | 7,062 | 284 |
| an unpriced writer of either pool within 6 slots | 99.7% | 99.4% | 99.9% | 72.5% |
| … a two-pool taker (our pair) among them | 67.8% | 74.2% | 65.0% | 12.7% |
| … an arbitrage-like writer among them | 89.3% | 90.7% | 88.7% | 61.6% |
| the **first** unpriced writer is a two-pool taker | 46.9% | 57.9% | 42.2% | 2.5% |
| the first unpriced writer is arbitrage-like | 65.3% | 70.4% | 63.2% | 41.2% |
| the first unpriced writer is in the trigger's slot | 82.3% | 92.2% | 78.1% | 21.1% |
| the first unpriced writer was **seen in shreds before our send** | 35.0% | 68.6% | 20.9% | 6.0% |
| an arbitrage-like unpriced writer was seen before our send | 26.0% | 53.2% | 14.5% | 3.5% |

### 2b. How far ahead was the closer (first seen in our feeds, minus our send)

| closer first seen − our send | failed | DOA | auction-time |
|---|---|---|---|
| before −20 ms | 3.0% | 8.5% | 0.8% |
| −20 … −10 ms | 12.2% | 30.3% | 4.5% |
| −10 … 0 ms | 9.9% | 19.9% | 5.6% |
| 0 … +10 ms | 8.2% | 5.9% | 9.1% |
| +10 … +20 ms | 9.6% | 5.0% | 11.6% |
| +20 … +50 ms | 19.4% | 8.5% | 23.9% |
| +50 … +100 ms | 12.7% | 5.9% | 15.5% |
| +100 … +400 ms | 16.2% | 10.0% | 18.8% |
| after +400 ms | 8.1% | 5.1% | 9.3% |
| p10 / p25 / p50 / p75 / p90 | −13.9 / −0.7 / **28.7** / 98.0 / 309.0 | −19.0 / −14.3 / **−5.5** / 33.8 / 204.3 | −1.8 / 14.2 / **39.9** / 120.4 / 362.2 |

- **Measured from the trigger's first shred,** the closer appeared p50 44 ms later. That is p50 9.5 ms for DOA sends and 55 ms for auction-time failures.
- **Our own winning bundles** appeared on chain p50 82 ms after our send (p10 38 ms, p90 339 ms), about 97 ms after the trigger's first shred.

**Reading: "tens of ms late", not "a few ms", not "slots".**
- **About 25% of failures are stale-state sends.** The closer was already in our shred feeds, p50 about 12 ms before the send, but not yet in our account state, which lags shreds by 13.7 ms.
  - These are most of the DOA class: in 68.6% of DOA failures the first writer was visible before we sent.
  - Sends with any writer of our pools visible in shreds before the send land 0.5% (3,575 sends, 17 wins); with an arbitrage-like one, 0.4% (2,626 sends, 10 wins). Those without land 3.9% (6,786 sends, 267 wins).
- **About 50% are lost in the bundle pipeline.** The closer reached the chain 0–100 ms after our send, while our bundles need 38–340 ms.
  - Land rate rises steeply with how long the route stays quiet after our send (first unpriced writer seen x ms after send, band 0):

| x | <0 | 0–50 | 50–100 | 100–150 | 150–200 | 200–300 | 300–500 | 500–1000 | none ≥1 s |
|---|---|---|---|---|---|---|---|---|---|
| band-0 land % | 2.0% (665) | 1.6% (1,478) | 2.2% (638) | 6.3% (269) | 10.2% (196) | 8.1% (247) | 24.1% (108) | 41.5% (82) | 60.8% (171) |

- **About 25% have a closer after 100 ms.** Here our bundle failed although the route stayed quiet for a while: other price moves, or the bundle not being run in time (far or BAM leaders, §3).
- **Not slots:** 71.7% of closers are in the trigger's slot, 19.8% in the next, 8.1% two to six slots later, and 0.3% have none within 6 slots.

### 2c. Position in the block (same slot as the trigger)

| closer rank − trigger rank | failed sends | share |
|---|---|---|
| +1 (immediately after: a sequenced backrun) | 1,099 | 15.2% |
| +2 … +5 | 305 | 4.2% |
| +6 … +20 | 623 | 8.6% |
| +21 … +100 | 2,714 | 37.5% |
| more than +100 | 2,488 | 34.4% |

- 15% of same-slot closers sit right behind the trigger, i.e. bundled or sequenced with it. We cannot reach these by reacting to shreds (as in the redesign findings).
- The other 85% land later in the same block.
- **The two failure classes differ:**

| class (same-slot closers) | n | +1 | +2…+5 | +6…+20 | +21…+100 | > +100 |
|---|---|---|---|---|---|---|
| DOA | 2,475 | 36% | 9% | 13% | 24% | 17% |
| auction-time | 4,709 | 4% | 2% | 6% | 45% | 44% |

  - DOA failures are mostly gaps a sequenced backrun or an earlier transaction had already taken.
  - Auction-time failures are races lost to transactions landing later in the same block while our bundle was in the pipeline.
- When our own bundles win in the trigger's slot, they land more than 100 positions after the trigger in 118 of 140 cases.

### 2d. Who

- **Coverage:** a signer is known for 8,072 of 10,049 closers (80%), from exec where present, else rivals (which keeps 1 in 10 of its `venues` rows).
- **Spread:** 587 distinct closer signers; the top 5 hold 24%.
- **The top closers are known rivals:** 5,079 of the 8,072 signed closes are by signers already named in `docs/research` (rival-GLiCiNEn, venue-census, rival-synthesis, PATTERNS) or the FT docs.

| signer | closes | share of signed | named before | median tip | Jito-tipped closes | tip services seen |
|---|---|---|---|---|---|---|
| MriyaNN8… | 599 | 7.4% | yes | 0 | 22 | jito 29, helius 8 |
| AgmLJBMD… | 347 | 4.3% | yes | 0 | 0 | — |
| rLsi2DPw… | 342 | 4.2% | yes | 18,001 | 136 | jito 218 |
| En3NPq8o… | 340 | 4.2% | yes | 0 | 18 | jito 63, helius 62, astralane 20 |
| GgGap6ti… | 332 | 4.1% | yes | 4,459 | 69 | jito 307 |
| R32xAccF… | 273 | 3.4% | yes | 79,349 | 61 | jito 119, astralane 56, helius 32 |
| GxDC9e7S… | 239 | 3.0% | yes | 0 | 1 | blockrazor 19, nozomi 6, bolt 3 |
| 4XBqViD1… | 183 | 2.3% | yes | 0 | 3 | helius 19, jito 11, astralane 5 |
| 4B8srvot… | 155 | 1.9% | yes | 80,153 | 60 | jito 101, helius 8 |
| 6AGp6zbG… | 153 | 1.9% | yes | 155,828 | 74 | jito 138 |
| FHpcNSe6… | 146 | 1.8% | | 0 | 16 | jito 28, helius 25 |
| DtvmxrTA… | 143 | 1.8% | yes | 0 | 0 | astralane 23, landx 11, nozomi 8 |
| CzYQ2kFn… | 139 | 1.7% | yes | 0 | 19 | jito 20 |
| GLiCiNEn… | 138 | 1.7% | yes | 1,350 | 62 | jito 132, helius 5 |
| CQwT1byu… | 137 | 1.7% | | 0 | 29 | jito 48, astralane 5, flashblock 3 |

- **Closer tips** (n = 8,072 known): p10 / p25 / p50 / p75 / p90 = 0 / 0 / 0 / 20,648 / 549,570 lamports.
  - 4,257 of them (53%) paid no Jito or sender tip at all (priority-fee and other lanes).
  - Where the closer tipped, it tipped more than us in 3,009 cases and no more in 806 (median ratio 4.0×).
- **Kind of closer** (n = 10,049):
  - arbitrage-like and two-pool 53%;
  - arbitrage-like on one of our pools 27%;
  - a non-arbitrage transaction writing both our pools 15% (aggregator routes);
  - other 5%.

## 3. Our own timeline (ms)

| stage | n | p50 | p90 | p99 | landed p50 | failed p50 |
|---|---|---|---|---|---|---|
| trigger first shred → account update received | 10,262 | **13.660** | **22.218** | 58.276 | 14.203 | 13.630 |
| update received → commit | 10,361 | 0.045 | 0.254 | 5.087 | 0.046 | 0.045 |
| commit → engine | 10,361 | ~0 | 0.011 | 0.387 | | |
| engine → priced | 10,361 | 0.205 | 1.114 | 5.891 | 0.594 | 0.201 |
| priced → decided | 10,361 | 0.001 | 0.003 | 0.005 | | |
| decided → signed | 10,361 | 0.241 | 0.379 | 0.594 | 0.217 | 0.242 |
| signed → sent | 9,252 | 0.030 | 0.244 | 0.551 | | |
| **first shred → sent** | 9,213 | **14.68** | **24.17** | 62.39 | 15.46 | 14.66 |
| sent → sendBundle reply | 9,256 | 0.7 | 0.9 | 1.5 | | |
| sent → first `accepted` (when any) | 637 | 38.9 | 90.7 | | 37.6 | |
| sent → first verdict | 10,289 | 59.9 | 176.1 | 1,518 | 39.0 | 60.8 |
| sent → our transaction seen on chain (landed only) | 284 | **82.1** | 338.5 | | | |

- **The state wait dominates our part.** 93% of first-shred → sent is waiting for the state stream's account update; everything we compute takes under 1 ms.
- **After the send, the bundle path dominates:** 38–340 ms to be on chain.
- **Send → seen on chain, by leader:**

| leader | p50 |
|---|---|
| Jito | 73 ms |
| BAM | 174 ms |
| Germany | 68 ms |
| Netherlands | 82 ms |
| US | 137 ms |
| UK | 133 ms |
| Singapore | 208 ms |
| Japan | 295 ms |

- **Bundles target the slot after the trigger's, but 49% of wins land in the trigger's own slot.** The target slot is the trigger's + 1 for 10,360 of 10,361 sends. Wins landed in the trigger's slot (140) or the next (124).
- **Speed counterfactual:** shift every send earlier by d and read the land rate from 2b's curve.

| shift | 5 ms | 10 ms | 13.7 ms (no state wait) | 20 ms | 40 ms |
|---|---|---|---|---|---|
| modelled wins, all bands | ×1.02 | ×1.05 | ×1.08 | ×1.13 | ×1.32 |
| modelled wins, band 0 | ×1.01 | ×1.03 | ×1.05 | ×1.07 | ×1.18 |

## 4. Wins vs losses

| factor | what the data says |
|---|---|
| **Gap size** | The strongest factor (§1b): expected gross <10k lands 11.3%, 10–20k 5.3%, 20–50k 1.0%, 50–100k 0.2%, ≥100k 1 in 4,208 |
| **Size** | Small trades land: ≤0.001 SOL 24.4%, ≤0.002 20.3%, ≤0.005 8.1%, ≤0.01 2.7%, ≤0.02 2.4%, ≤0.05 0.7% (5,646 sends, 54% of all), >0.1 0.1%. Net per win is similar up to 0.05 SOL (2,100–6,900), so **net per send** falls from 792 (≤0.001) and 634 (≤0.002) to 37 (≤0.05). This holds inside band 0 as well: 26.2% at ≤0.001 SOL vs 2.4% at ≤0.05 |
| **Live contestation** | Two-pool takers on the same route in the previous 10 minutes, computed from our own state stream (band 0, sends after a segment's first 10 min): 0 → 9.5% (257 lamports/send), 1–2 → 7.4% (326), 3–10 → 5.1% (139), 11–50 → 4.0% (84), >50 → 4.0% (83). All bands: 4.6% → 0.6%. After the fact: with no arbitrage signer writing our pools within 2 slots of the trigger, sends land 9.2% (1,692 sends); with one, 2.0%; with two or more, 0.9–1.5% |
| **State staleness at send** | A writer of our pools already in shreds before our send: 0.5% vs 3.9% (§2b) |
| **Trigger source** | All state triggers; `commit` 2.8%, `timeout` 1.8%, `quiescent` 2.6% |
| **Time since the trigger** | First shred → send is flat across our range: <10 ms 1.4%, 10–15 2.8%, 15–20 3.1%, 20–25 3.7%, 25–30 4.0%, 30–60 ~3%, >100 0/34. Our latency spread is too narrow to matter |
| **Route age** (ms since the route's last write) | No effect (3.0% / 2.7% / 2.5% / 1.9% from <0.01 ms to <10 ms) |
| **Tip** | Land rate falls with the tip (13.1% at the 1,000 floor, 0.8% at 10k–20k, 1 win in 4,006 sends above 20k), but the tip is 0.2 × edge, so this is the gap effect. 0 lost auctions; the closers' median tip is 0, and 53% pay no Jito or sender tip. FT-012b p1's randomized arms (0.1 / 0.2 / 0.35: 9/291, 9/280, 7/277 wins) are too small to tell apart |
| **BAM vs Jito** | Band 0: Jito-led 7.4%, BAM-led 6.4%. BAM-led bundles reach the chain later (174 vs 73 ms). Their wins net less (1,994 vs 5,327) because the BAM floor makes tips 47% of gross (Jito-led 13%) |
| **Leader distance** | Band 0, by host → leader RTT: <10 ms 7.5%, 10–30 ms 8.6%, 80–150 ms 6.0%, ≥150 ms 4.7%. Far leaders (≥80 ms): 5.3% on 1,104 sends; near: 7.7% on 2,747 |
| **Leader client** (band 0) | Firedancer 13.1% (251), FireBAM 13.1% (61), HarmonicAgave 8.0%, AgaveBam 6.2%, JitoLabs 6.0%, Rakurai 0/46 |
| **Blockhash age** (≤20 by rule) | No effect: 2.4% at <3 slots, 3.0–3.2% at 3–10 slots |
| **Pool and token** | Common tokens land 4.3%, memes 1.8%; memes win larger. PumpSwap ↔ DLMM lands 1.1–1.3%; Raydium CPMM ↔ DLMM and DAMM v2 ↔ PumpSwap land 13–17% |

## 5. Stale-blockhash refusals

**Cause, confirmed:**
- The bundle uses the ring's **confirmed** head (`[send_policy] blockhash_commitment = "confirmed"`, `max_blockhash_age_slots = 20`; `exec.rs::input_checks`, `SendView::blockhash`).
- The confirmed head comes only from:
  - the Shyft slot index (one `getBlock` per confirmed slot, on 3.8 of Shyft's 4 req/s);
  - the Haan `getLatestBlockhash` poll, which runs only while no other source is fresh (`chainfetch/blockhash.rs`).
- The gRPC stream's block metas are processed-level, so with `confirmed` they are never used.
- The age is measured against the processed tip. When the slot index falls more than 20 slots behind, every send is refused until it catches up or the poll's answer is fresher.

| slot-index lag (status line) | seconds observed | refusals | per min |
|---|---|---|---|
| ≤ 2 slots | 34,719 | 0 | 0 |
| 3–5 | 8,294 | 0 | 0 |
| 6–10 | 2,471 | 0 | 0 |
| 11–20 | 2,480 | 144 | 3.5 |
| > 20 | 5,821 | 2,098 | 21.6 |

- **Size and frequency:**
  - 2,244 refusals in 907 segment-minutes, 2.5 a minute.
  - Per segment 0.6–5.9 a minute; at 2 bundles/s (FT-012b p1, FT-013b) 1.8–3.0 a minute.
  - The executor's counter equals the decisions' `blockhash_stale` count on the segments checked, so the FT-013 doc's "about 10 a minute" was not reproduced.
  - Slot-index lag p90 per segment is 5–41 slots, the maximum 35–56.
  - The ring head was older than 20 slots in 2.7–13% of status lines.
  - The fallback poll did not prevent it: 778 refusals fell in status intervals that ended with the head taken from the poll.
- **Cost, on the 5 segments whose decisions were pulled** (ft007-p3, ft008-p6, ft010-p2, ft012b-p1, ft013b-p2; 3.4 h):
  - 533 refusals fell in 158 send windows (refusals more than one `every_ms` apart: a burst shares one slot).
  - Their band mix was 229 / 116 / 129 / 57 / 2 across bands 0–4.
  - At each band's realised net per send (218 / 134 / 8 / 0 / 0 lamports) the lost net is about **18,454 lamports, 4.0%** of the 461,973 those segments made.
  - Over the whole dataset that is about 3,000 lamports/h.

## 6. Recommendations, ranked by expected effect on net SOL/h

Baseline: 77,825 lamports/h over these 15.1 h (FT-008 alone 91k/h). Effects are relative to it.

1. **Stop sending large expected gaps:** expected edge ≥ 75,000–100,000 lamports at our size (bands ≥ 2), and give their send slots to small gaps.
   - **Evidence:**
     - Bands 2–4 are 4,153 sends (40%) with 1 phantom win. Edges of 75k–100k: 421 sends, 0 wins.
     - DOA failures rise from 17% to 56% with band: those gaps are gone before the block engine sees us.
     - On the 5 segments with decisions, 325 of 995 band-≥2 sends held the send slot while a band-0 decision was refused `canary_wait`. In 168 of them the refused decision's pools were disjoint from the holder's (a different opportunity).
   - **Expected effect:**
     - Replacing those sends at band 0's 218 lamports a send: **+8% to +14% net** (36,600–64,300 lamports on 461,973).
     - Cost: the one 22,701 win, about 1,500 lamports/h.
     - The tip cap is no longer paid on phantom quotes.
   - **How:**
     - Now, config only: `[send_policy] big_band_max_per_sec = 0` means "no big-band trade" (`config.rs` validation) and stops bands 3–4. That is 1,291 sends (12.5%) with 0 wins.
     - Then a small executor rule: refuse an expected edge at or above about 75,000–100,000 lamports, recorded as its own reason, to cover band 2. Re-measure the cut-off on fresh data.
   - **Confidence:** high on "never lands"; medium on the size of the reallocation gain.
2. **Build the CU table so bundles request the compute they use.**
   - **Evidence:**
     - All 10,361 sends used the fallback CU formula; landed bundles used p50 56% of the limit.
     - On BAM-led slots the tip is at least 0.05 lamports per requested CU (`[send_policy.bam]`), so the inflated limit inflates the tip. BAM-led wins paid 535,892 lamports in tips on 1,214,600 gross.
     - Recomputing those 100 wins' tips with a limit of consumed CU × 1.10 (the table's p99 × 1.10 rule) and the same 0.05/CU floor saves **108,988 lamports, 9.3% of all net**. The bid per requested CU, which is what BAM ranks on per FT-006's evidence, is unchanged.
     - The repo's notes say Jito also ranks bundles by tip per requested CU (`deploy/*.toml`, FT-006). If so, Jito-led sends would gain auction rank at no cost (not measured here).
   - **How:** `arbx-report cu-table` (MEASUREMENT §4.48) over the landed transactions and exec records, then upload `data/cu-table.json` with `cu_min_samples` met.
   - **Expected effect:** **about +9% net** from BAM tips alone.
   - **Confidence:** medium-high. It assumes BAM ranks by the bid per requested CU, as FT-006's evidence suggests. A CU limit at p99 × 1.10 of measured use also leaves a small risk of running out of compute, which only fails that bundle.
3. **Give the send slot to the best candidate, not the first.**
   - **Evidence:**
     - `canary_wait` refused 10,797 decisions on the 5 segments, 4,550 of them band 0.
     - 1,065 of 2,623 send windows had a refused band-0 decision; 506 of those were held by another band-0 send, 160 on disjoint pools.
     - Within band 0, routes without recent takers land 9.5% (257 lamports/send), against 4.0% (83) on routes with more than 10 takers in 10 minutes.
     - The static crowding list does not separate them (2.6–3.3%).
   - **How:**
     - Today the canary gate (`Exec::sender_state`, `canary_wait`) gives the slot to whichever decision comes first after `every_ms`. The bundle path's rate queue behind it already orders by band, crowding bucket and EV (`queue_ms`), but rarely gets to choose.
     - Let the queue's 2/s budget be the binding limit and choose there. Rank by band, then by takers on the route in the last 10 minutes (the engine sees every write to our pools), then by expected net.
   - **Expected effect:** +3% to +8% on top of item 1, plus better use of the 2/s Jito budget.
4. **Fix the blockhash source.**
   - **Evidence:** §5. About 4% of net, about 3,000 lamports/h.
   - **How**, two config-only options:
     - Raise `max_blockhash_age_slots` from 20 to about 60; the config allows 1–150. A blockhash is valid for 150 blocks and our bundles land within 1–5 slots, so a 60-slot-old hash still has about 90 blocks left. This alone would have removed nearly all refusals: the slot index's worst lag was 35–56 slots.
     - Or `blockhash_commitment = "processed"`: `SendView::blockhash` then takes the newer of the ring head and the gRPC stream's latest block meta, which is never more than a slot or two old. The risk is a hash from a block that is later skipped, which only fails that bundle's simulation, at no cost.
     - Durable fix in code: promote block metas to confirmed when the slots stream confirms the slot, so the confirmed ring stops depending on Shyft's `getBlock` budget.
   - **Expected effect:** **+3% to +4%**, at almost no cost.
5. **Test smaller size caps or expected-value sizing:** land probability × net instead of quoted net.
   - **Evidence:**
     - Realised net per send is 792 lamports at ≤0.001 SOL, 634 at ≤0.002 and 330 at ≤0.005, against 37 at 0.02–0.05 SOL.
     - Band 0 alone: 26% at ≤0.001 SOL vs 2.4% at ≤0.05.
     - FT-007, which cut the cap from 0.2 to 0.05 SOL, doubled the win ratio.
   - **Caveat:** part of this is which opportunities have small optimal sizes (thin, uncontested pools), not our choice of size. Hence a test.
   - **How:** an FT-012-style randomized arm with a 0.01 or 0.02 SOL cap against 0.05.
   - **Expected effect:** uncertain; plausibly large (+10% to +30%) if partial-gap survival is causal.
6. **Re-price before sending when a writer of our pools is already in shreds.**
   - **Evidence:**
     - 35% of sends had one; they land 0.5% vs 3.9%.
     - A hard veto would lose 17 wins (12% of net, mostly band 1), so wait for that writer's account update (about 13 ms) and re-price instead.
   - **Expected effect:** small directly, +1% to +3%; mainly it frees slots for items 1 and 3.
7. **Send through a block engine near the leader** for far leaders (US, Asia).
   - **Evidence:**
     - Our bundles reach the chain in 137 ms (US) and 295 ms (Japan) against 68 ms (Germany).
     - Band-0 land rate is 5.3% for leaders ≥80 ms away against 7.7% near.
   - **Expected effect:** bringing far-leader slots to the near rate gives at most +27 band-0 wins in 15.1 h, **+5% to +7% net**.
   - **Check first:** how Jito routes bundles between regions.
8. **A faster decision path** (pricing from shreds instead of waiting for Haan's account update): **+5% to +8% wins** in the model, at high cost and with the poisoning risks WP-04 removed. Not before items 1–7.
9. **Tips: no change to the shares beyond the running FT-012 arms.**
   - **Evidence:**
     - 0 lost auctions.
     - 53% of the closers pay no tip at all.
     - Where the closer tipped, it tipped 4.0× more than us at p50, but the failures are timing failures (§2b).
     - FT-012b p1's arms do not differ yet.
10. **No hard route blacklist.**
   - **Evidence:** wins come on routes that failed many times before.
     - Skipping a route after 5 sends without a win keeps 75% of sends but loses 30 wins and 15% of net.
     - After 10 sends: loses 16 wins and 7%.
   - Use the contestation ranking (item 3) instead.
11. **Grow the supply of small, uncontested gaps on the current venues** (WP-22 refresh and new pools at creation).
    - **Evidence:** 95% of wins and 71% of net are band 0. The best per-send pairs are Raydium CPMM ↔ DLMM and DAMM v2 ↔ PumpSwap (13–17%).
    - **Expected effect:** not quantified here; this is where net/h scales once items 1, 3 and 4 free the slots.

**Order of work:**
- Config-sized, immediate: item 1 (`big_band_max_per_sec = 0`) and item 4 (blockhash age or commitment).
- Data and tooling: item 2 (CU table).
- Small executor changes: item 1's band-2 rule and item 3.
- Experiments: items 5 and 7.
- A project: item 8.

Together, items 1–4 are worth roughly +20% to +35% net/h on this data, about 94,000–105,000 lamports/h against 77,825.

## 7. Limits of this analysis

- **Time-separated campaigns.** Market hours, settings and pool lists differ between tests. Only FT-012b p1 has randomized arms, and it has 949 sends.
- **The closer is a heuristic.**
  - It is a writer of our pools whose update reached us after our decision; whether it actually removed the gap was not re-priced (`arbx quote`, WP-09, was not run).
  - A closer that changed price through accounts we do not follow is not seen.
  - "First seen" is our shred feeds' arrival, not the closer's execution time on the leader.
- **Signer and tip coverage is partial.**
  - exec.jsonl covers about 70% of watched transactions (OD-1). Where exec was missing, rivals.jsonl keeps only 1 in 10 of its `venues` rows.
  - Signers are known for 80% of closers; the "who" table leaves out closers neither stream kept.
- **Block positions** come from Shyft's slot index, which ranks non-vote transactions. Order is reliable (40/40 against `getBlock`); absolute indexes are not.
- **The `InstructionError` class** carries no code. Treating it as a timing failure rests on its timing, not on its content.
- **DOA failures with no earlier writer:** about 30% of them (898) saw their first writer only after our send (p50 +30 ms). The closer may have run on a distant leader before we saw it, or the block engine's bank may have differed from ours (for example, not yet holding the trigger). This was not tested.
- **Value estimates** use realised net per send by band from these same tests and assume refused or blocked decisions were as good as sent ones. Opportunities in one burst are correlated, hence the ranges.
- **The speed counterfactual** assumes the land-rate curve against "route quiet time" is causal and unchanged by being earlier.
- **Blockhash cost** is measured on 5 of 22 segments.
- **FT-012b segments 2 onward**, still running, are not included.

## Appendix: data and scripts (`/home/moiz/arbx-offload/landing-study/`)

**Scripts** (`scripts/`):
- `core.py` → `out/attempts_all.jsonl`: one row per sent attempt.
- `p134.py` → `out/p134.md`: §1, §3, §4 tables.
- `extract.py`, `extract_exec.py`, `extract_dec.py` → `ext/<seg>/`: Cherry pulls reduced to our pools and signatures. The raw files were deleted after each pull.
- `p2.py`, `p2sum.py` → `out/p2/*.jsonl`, `out/p2.md`: §2.
- `p5.py`, `p5b.py` → `out/p5.md`, `out/p5b.md`: §5 and slot competition.
- `p_slots.py`, `policy.py`, `contest.py`, `p_speed.py`, `region.py`, `seen.py` → `out/*.txt`: §3, §4, §6 figures.
- `verify_rpc.py` → `out/verify_rpc.jsonl`: 150 public-RPC calls.

**Kept, 89 MB:**
- `out/`, including the per-attempt attribution `out/p2/*.jsonl` and the per-attempt table `out/attempts_all.jsonl`;
- `scripts/`;
- the decisions extracts (`ext/<seg>/decisions.jsonl`);
- FT-012b p1's core streams (`raw/ft012b/`).

The large extracts (rivals, txarr, slotidx, exec, moves: about 2 GB) and the other pulled streams were deleted after the run. `extract.py` and `extract_exec.py` re-pull them from Cherry while the run directories remain there.

**Inputs:**
- Local copies of FT-006/007/008/010/013.
- Pulled from Cherry, read-only: opportunities, triggers, bundles, moves, arrivals, blocks, slots, leaders, meta for every segment; FT-012b p1's core streams; rivals, txarr and slotidx reduced per segment; exec.jsonl reduced (22 segments); decisions reduced (5 segments).

# Wallet 2g7rYv7y: recent wins and losses compared with the research

**Window:** w5h2-p1..p11 and w5h3-p1..p2, 2026-10-03 21:32:42 to 2026-10-04 01:32:54 UTC. That is 2.99 h of w5h2 and 0.67 h of w5h3. Amounts are in lamports unless marked SOL.

**Sources:** the chain ledger (all 1,010 wallet signatures, fetched with get_tx), our run records, and per-block checks done by eight analyses and their verifiers. Every verifier correction is applied below.

## 1. Bottom line

- **Small wins went as the research predicted.** There were 23 Jito-bundle wins:
  - Each was tiny: 0.0026 to 0.234 SOL in size, 8,985 to 228,454 expected.
  - The tip was exactly floor(0.7 × (expected − 5,000)) in 23 of 23.
  - The on-chain round trip matched the prediction exactly in 18 and within 12 lamports in 22.
  - They landed late: send to first sighting p50 66 ms, block index p50 704.
  - We were the first trade after the trigger to take value from our pair in all 23.
  - Together they made +163,187 before rent.
- **Losses look as predicted, but the cause is only partly the research's.**
  - What matched: every direct send landed, 986 of 987 failed, 962 of those on our own profit check (0x4e580002), and more paths, bigger tips or priority changed nothing.
  - Where a real gap existed, a faster rival took it, usually already in shreds before our send. MriyaNN8 was the most frequent closer (18.4%).
  - What the research missed: many of the largest quotes were phantoms created by our own engine. The engine kept predicted pool states from decoded swaps that failed on chain, and it read trigger state while only part of it had been applied. This explains 10 of the 16 biggest losses and 6 of the 14 in the stratified sample.
- **The window's only real profit was one lucky direct trade.** w5h2-p5#648 via bolt made +27,459,627 (+28,973,467 before rent).
  - It was priced on an inconsistent pool snapshot; on the true state it would have lost 103.45M.
  - Three outside buys worth 12.38 SOL turned the trade profitable before it landed. It is not a repeatable strategy.
- **True P&L:**
  - Wallet change −14,834,557.
  - +4,769,163 excluding 19,603,720 of recoverable rent locked in 13 empty token accounts.
  - −24,204,304 excluding rent if the bolt win is removed.
  - Failed direct landings cost 24,367,491, about 6.5M per hour.
- **The sim gate was never turned off.** sim_gate=true in all 13 segments; only the shadow simulator (SimCfg) went off at p3.
  - So P7 cannot be tested here.
  - The gate's stale sims said "fail" on 968 direct sends and were overridden every time. They were right 967 times and wrong only on the bolt win.
- **P6 is right in direction but much smaller than the research said.** 16 failed landings were unrecorded (0-3 per segment, 419,911), not 11-16 per segment.
- **P9 holds. P10 holds but with little statistical power. P4 has one counterexample in 1,511 sends.**
- **Our own bugs:**
  - 19 failures from a missing DLMM bitmap-extension account and 5 from CU limits set too low cost 756,015.
  - 7 segment-start sends went out 3.0 to 3.8 s late.

## 2. The money (from the chain)

| | w5h2 bundle wins (21) | w5h2 bolt win | w5h2 failures (831) | **w5h2 total** | **w5h3-p1..p2** (2 wins, 155 failures) | **All** |
|---|---|---|---|---|---|---|
| Gross round trip | 613,850 | 30,002,068 | 0 | 30,615,918 | 54,629 | 30,670,547 |
| Tips paid | 359,052 | 1,000,000 | 0 | 1,359,052 | 31,240 | 1,390,292 |
| Fees on wins | 105,000 | 28,601 | — | 133,601 | 10,000 | 143,601 |
| Failure fees, recorded | — | — | 19,722,215 | 19,722,215 | 4,225,365 | 23,947,580 |
| Failure fees, unrecorded | — | — | 332,506 (13 txs) | 332,506 | 87,405 (3 txs) | 419,911 |
| Rent locked (recoverable) | 18,089,880 | 1,513,840 | 0 | 19,603,720 | 0 | 19,603,720 |
| **Net wallet change** | −17,940,082 | +27,459,627 | −20,054,721 | **−10,535,176** | **−4,299,381** | **−14,834,557** |
| **Net excluding rent** | +149,798 | +28,973,467 | −20,054,721 | **+9,068,544** | **−4,299,381** | **+4,769,163** |

- **w5h2 without the bolt win:** −19,904,923 excluding rent.
- **By arm:**
  - Bundle arm: +163,187 excluding rent, but −17,926,693 with rent.
  - Direct arm: +3,092,136, which is one win minus 986 failure fees (+4,605,976 excluding rent).
- **Hourly rates:** bundle profit excluding rent was about 50k/h in w5h2 and 20k/h in w5h3. Failure fees were about 6.7M/h and 6.4M/h.
- **How well our records match the chain:**
  - All 1,010 in-window signatures are our own copies: 24 succeeded and 986 failed.
  - outcomes.jsonl matches the chain to the lamport on all 994 landings it recorded.
  - The supervisor's `profit_lamports` (w5h2 +9,519,545, w5h3 +13,389) is the sum of win nets including rent. It leaves out failure fees, so it is not P&L.
- **Rent:**
  - 13 accounts: 10 Token-2022 accounts at 1,513,840 and 3 SPL accounts at 1,488,440.
  - All end with 0 tokens; the 4 checked live are still open.
  - No write was done here.

## 3. Every win (24)

Notes on the columns:
- **ms** is from the trigger's first arrival to the first sighting of our tx.
- **+N** is block positions after the trigger in the same slot.
- **"+1"** means the next slot, at the block index shown.

| Trade | Pair, mint | SOL | Expected → on-chain | Tip | Rent | Landing | Who else | Verdict |
|---|---|---|---|---|---|---|---|---|
| p1#59 | PumpSwap>Dlmm EkFRff9a | 0.0026 | 8,985 → 8,983 | 2,789 | 1,513,840 | +1 idx 773, 269 ms | Nobody after the trigger. GLiCiNEn's arb at idx 849 came before it. | ALIGNS P1, P2 |
| p2#658 | Dlmm>RayV4 USDC | 0.0283 | 10,751 → 10,751 | 4,025 | 0 | +392, 66 ms | CzYQ no-op; 8NQ32SyF failed; NotArb logged "no opportunity" ×4 after us | ALIGNS |
| p2#1413 | PumpSwap>Dlmm E7bNJ5eq | 0.0066 | 56,256 → 56,254 | 35,879 | 1,513,840 | +415, 94 ms | Nobody | ALIGNS |
| p3#418 | Dlmm>DammV2 2AVjqmGb | 0.0064 | 12,305 → 12,305 | 5,113 | 0 | +157, 85 ms, BAM | XUrKb2aK (idx+3 bundle) took a different pair from the opener (+114k). Our 398k try (att 417) came back would-fail. | ALIGNS |
| p3#1083 | Dlmm>Dlmm CbcyNo7m | 0.0139 | 12,679 → 12,679 | 5,375 | 1,513,840 | +225, 49 ms | FePyVntt and NALUnJA2 filled the same DLMM bin on other pairs | ALIGNS |
| p5#449 | Dlmm>Dlmm USDC | 0.0247 | 12,794 → 12,794 | 5,455 | 0 | +1 idx 1103, 367 ms, BAM | Nobody | ALIGNS |
| **p5#648** | Dlmm>PumpSwap 9dSMwFfP | 1.865 | 19,967,380 → 30,002,068 | 1,000,000 | 1,513,840 | +80, 37 ms | 5CKAa7Wm and BACKsEEY reverted before us; 8 same-direction failures after us | PARTLY (see §5) |
| p6#67 | Dlmm>PumpSwap 9dSMwFfP | 0.0042 | 21,087 → 21,075 | 11,260 | 0 | +1 idx 797, 257 ms | GxDC9e7S took the opener's 479,740 gap (our quote: 479,741) | ALIGNS |
| p6#114 | Dlmm>DammV2 A5ffnvMh | 0.050 | 12,603 → 12,603 | 5,322 | 1,513,840 | +1 idx 48, 107 ms | Nobody | ALIGNS |
| p6#311 | DammV2>PumpSwap Cm6fNnMk | 0.0052 | 20,032 → 15,960 | 10,522 | 1,513,840 | +207, 63 ms | gtagyESa ran a USDC triangle through our sell pool at idx+6, before our send | PARTLY: round trip 4,072 short |
| p7#63 | DammV2>DammV2 2AVjqmGb | 0.0091 | 9,310 → 9,310 | 3,017 | 0 | +304, 77 ms | None | ALIGNS |
| p7#154 | Dlmm>Dlmm USDC | 0.1034 | 25,055 → 25,055 | 14,038 | 0 | +1 idx 331, 90 ms | The trigger was GHigB15j's own arb; FePyVntt failed ×8 | ALIGNS |
| p7#307 | Dlmm>Dlmm C1mBfBoD | 0.0045 | 17,331 → 17,331 | 8,631 | 0 | +306, 88 ms | shakRDxy hit our buy pool 7 positions ahead, same bin, no effect on us | ALIGNS |
| p7#643 | Dlmm>RayV4 HNT | 0.0318 | 23,259 → 23,259 | 12,781 | 1,488,440 | +503, 39 ms | All 8 txs in between failed | ALIGNS |
| p8#162 | Dlmm>PumpSwap 8nnaeWCw | 0.0687 | 39,082 → 39,082 | 23,857 | 1,513,840 | +1 idx 104, 45 ms | Hhw5g5a1 touched both pools and took nothing | ALIGNS |
| p8#216 | Dlmm>Dlmm CTPoyCwk | 0.0061 | 11,794 → 11,794 | 4,755 | 1,513,840 | +1 idx 704, 265 ms | Nobody | ALIGNS |
| p9#35 | DammV2>DammV2 2AVjqmGb | 0.0111 | 14,497 → 14,497 | 6,647 | 0 | +1 idx 24, 134 ms | GiknBsga looked and logged "No profitable pair" | ALIGNS |
| p9#78 | PumpSwap>Dlmm JCX5nDG9 | 0.0422 | 15,363 → 15,355 | 7,254 | 1,513,840 | +1 idx 143, 189 ms, BAM | xxMCvuWY failed 30 positions after us | ALIGNS |
| p9#101 | DammV2>PumpSwap GTBxUiw6 | 0.0032 | 14,712 → 14,712 | 6,798 | 1,513,840 | +360, 62 ms | Nobody; the FLASHX flow had no 4BQ6 backrun | ALIGNS |
| p10#412 | Dlmm>Dlmm USDC | 0.082 | 35,650 → 35,650 | 21,455 | 0 | +229, 53 ms | 3 later failures | ALIGNS |
| p10#559 | Dlmm>DammV2 PerPsCe2 | 0.0033 | 15,947 → 15,947 | 7,662 | 1,488,440 | +65, 32 ms | MriyaNN8 at idx+1 took the sibling gap: 698,633 vs our quote of 698,625 | ALIGNS |
| p11#246 | Dlmm>Dlmm BPxxfRCX | 0.2345 | 228,454 → 228,454 | 156,417 | 1,488,440 | +1 idx 417, 220 ms | 7dGrdJRY (idx+1) and R32xAccF (+5.26M) took the big gap; MriyaNN8 failed | PARTLY: P11 only partly |
| w5h3-p1#18 | Dlmm>Dlmm USDC | 0.0809 | 40,190 → 40,190 | 24,633 | 0 | +743, 58 ms | En3NPq8o failed. Jito said would-fail after it had landed (already known). | ALIGNS |
| w5h3-p2#687 | Dlmm>Dlmm USDC | 0.0561 | 14,439 → 14,439 | 6,607 | 0 | +354, 108 ms | En3NPq8o failed ×3 | ALIGNS |

- **Totals:** 21 ALIGNS, 3 PARTLY.
- **Landing slot:** 13 landed in the trigger slot (+65 to +743 positions, median +306) and 10 in the next slot (one at idx 24, one at idx 48).
- **Real reaction time:** on state triggers our send left 10 to 28 ms after the trigger's first shred, because of the Haan state lag. It is not under 1 ms.
- **Selection bias:** a bundle that overpriced its gap fails its on-chain check and never lands. So wins cannot show overpricing.

## 4. Losses

### Population (all 986 on-chain failures)

**Arm.** Every failure is a direct copy.
- 989 direct attempts. The gate blocked 2 (w5h2-p9#0 and w5h3-p1#410, both "sim_gated ... 0x4e580002").
- The other 987 each landed exactly one copy, because every attempt uses a durable nonce.

**Errors:**
- 962 hit our profit check (0x4e580002). Every one had a negative round trip at execution: p50 −149 bps of size, against an expected +104 bps.
- 19 were DLMM 0x1794 (bitmap extension not passed). 7 of them were on one pair, 8RdbS9dS/FpJWjYZ5.
- 5 were ProgramFailedToComplete: 4 inside DLMM and 1 in our own route program. In all 5, CU used equals our CU limit.

**Timing:**
- Trigger first shred to our first send: p50 17.6 ms.
- Send to first sighting: p50 137 ms (p90 349).
- 40.5% landed in the trigger slot (same-slot index p50 903).

**Who closed the gap:**
- The recorded taker was in shreds before our first send in 506 of 807 cases (62.7%).
- p1/p2 closers found from pool moves (n=211), and how many were ahead of our send:

| Group | Closers | Ahead of our send |
|---|---|---|
| Rung 0-1 sequenced backrunners (Mriya 35, 8oSD 6, 9EwQ 5) | 46 | 43 |
| Sprayers | 36 | 31 |
| Reactive bundlers (Bgok 14, A9pQ 5) | 19 | 11 |
| DtvmxrTA | 7 | 2 |
| 4BQ6 | 5 | 5 |
| R32x | 5 | 4 |
| Other catalogued bots | 31 | 20 |
| Long tail, not in the catalog (arrival p50 28.3 ms) | 55 | 25 |
| User/flow | 7 | 4 |

- **Timing of those p1/p2 closers:** 197 of 211 landed in the trigger slot. Of the 113 whose block distance could be measured, 38 sat at idx+1.
- **Combining p1/p2 with a 115-tx later sample,** MriyaNN8 is the top closer at 60 of 326 (18.4%).
- **Caveat on the detector:** the taker and moves detector misses reverted, zero-capture and single-pool closers. In 10 of the 21 measurable p1/p2 "no closer" cases there was in fact a successful rival that touched both pools.

**Where a real gap existed, our pricing was exact.** The closer's take matched our quote:

| Closer | Took | Our quote | Trade |
|---|---|---|---|
| MriyaNN8 | 4,733,554 | 4,733,548 | p1#20 |
| MriyaNN8 | 50,407,617 | 50,407,577 | p5#716 |
| MriyaNN8 | 3,088,958 | 3,088,957 | w5h3-p2#132 |
| 9EwQoN74 | 16,903,365 | 16,903,648 | w5h3-p1#176 |
| 9EwQoN74 | 51,256,592 | 51,256,598 (gross) | w5h3-p2#474 |

**Phantom quotes from our engine.** These come from two engine defects:
- **Failed swaps left as predictions.** A decoded swap writes a predicted pool state (`self.preds`, engine.rs:641) that overrides the live state when we quote. The prediction is cleared only by an account update from the same tx, or by a 1.5 s prune that runs only during housekeeping. Each new decode re-stamps it, so stacks of failed copies can live for seconds.
  - `skip_failing_signers` is false in every segment (the default is true).
  - 681 of 822 decoded trigger txs with a priced opportunity of 0.1 SOL or more failed on chain.
  - In w5h3-p2, 54 of 96 failures (1,656,656 in fees, 13.86 SOL of "expected") were on DreMAMRc>AwmaWjsR. The median first-leg ratio there was 0.926, against 0.9945 on other pairs.
- **Torn trigger reads.** On split-route triggers we priced one pool or vault still at its pre-trigger value.

**Config changes:**
- Failures per direct attempt: 1.000 on 2 paths, 1.000 on 10, 0.996 on 17, 0.994 in w5h3.
- Send to sighting p50: 136.9 / 137.2 / 139.9 / 117.3 ms.
- Failures per minute fell from 10.8 to about 3.6, because the direct threshold rose from 1.5M to 3M at p3, not because of the gate.
- The untipped haan or tpu-direct copy landed in 66/98, 322/478 and 100/155 attempts.
- The landed copy was the first one sent in only 13/98, 34/478 and 17/155.
- No failure paid a tip, even though 498 carried tip instructions worth 4.416 SOL in total.

### Every individually analyzed loss (66)

Every loss was a direct copy that failed and cost only its fee (14,800 to 55,001 lamports).

**Real gap, closed before our send or in the trigger slot (24):**

| Trade | SOL / expected | Closer | Verdict |
|---|---|---|---|
| p1#20 | 1.73 / 4.73M | MriyaNN8, 23.4 ms before our send. Unrecorded (shyft timeout). | ALIGNS |
| p1#94 | 4.2 / 312.7M | Bgok +39.8M, A9pQ +31.3M, JAkGWTYL +642M; the recorder missed them | ALIGNS |
| p2#52 | 4.2 / 182.4M | MriyaNN8 before our send; unrecorded | ALIGNS |
| p2#56 | 0.76 / 19.07M | MriyaNN8 (the trigger was its own arb); unrecorded | ALIGNS |
| p2#400 | 4.2 / 1.874 SOL | CzYQ2kFn +2.658 SOL with no tip, Dy1jE82C, 78XwCxCT, all 0.5-2.3 ms after the trigger; priced correctly | ALIGNS |
| p2#516 | 4.2 / 487.8M | MriyaNN8 at idx+1, 0.48 SOL priority fee | ALIGNS |
| p2#528 | 4.2 / 52.2M | CzYQ2kFn, 35.1 ms before our send | ALIGNS |
| p2#1322 | 4.2 / 99.7M | 4BQ6ATUt inside the trigger's bundle (rung 0) | ALIGNS |
| p2#1404 | 4.2 / 147.4M | MriyaNN8 inside the trigger's bundle (rung 0) | ALIGNS |
| p3#884 | 3.57 / 89.2M | CatyeC3L +74.4M, DtvmxrTA +35.6M; we landed 2 slots late | ALIGNS |
| p5#716 | 2.59 / 50.4M | MriyaNN8 at idx+1 took our exact gap | ALIGNS |
| p6#128 | 4.2 / 138.7M | A9pQ1Qsv 0.44 ms before our send (588.6M gross); unrecorded | ALIGNS |
| p6#130 | 1.24 / 73.5M | CatyeC3L 4.9 ms before our send (73.78M); unrecorded | ALIGNS |
| p8#304 | 2.34 / 33.3M | 7dGrdJRY 3.1 ms before our send (33.65M); unrecorded | ALIGNS |
| p10#176 | 4.2 / 101.8M | 4BQ6ATUt at idx+1 behind FLASHX flow | ALIGNS |
| p11#244 | 4.2 / 19.87M | 7dGrdJRY at idx+1 hit our sell pool, then R32xAccF | ALIGNS |
| p11#510 | 3.06 / 91.6M | An idx+1 sequenced backrunner; our price was within 0.1% | ALIGNS |
| w5h3-p1#202 | 0.16 / 33.9M | 78XwCxCT bundle and gtagyESa; our state update arrived 35 ms late | ALIGNS |
| w5h3-p2#100 | 4.2 / 50.7M | MriyaNN8 inside the trigger's bundle | ALIGNS |
| w5h3-p2#132 | 0.37 / 3.09M | MriyaNN8 at idx+22, before our send | ALIGNS |
| w5h3-p2#474 | 4.2 / 41.4M | 9EwQoN74 at idx+1, priority fee = 75% of its gross | ALIGNS |
| w5h3-p2#452 | 3.28 / 23.3M | 7dGrdJRY at idx+1 (Astralane tip) | ALIGNS |
| w5h3-p2#636 | 0.25 / 3.10M | Bgokg3ju in its own bundle at idx+18 | ALIGNS |
| w5h3-p2#764 | 1.32 / 3.16M | 4YP7YJFD at idx+45, 8 ms before our send | ALIGNS |

**Real gap, rival seen after our send but landed first (8):**

| Trade | SOL / expected | What happened | Verdict |
|---|---|---|---|
| p2#804 | 4.2 / 34.8M | Bgokg3ju came after our send; we landed about 800 positions deeper | ALIGNS |
| p2#970 | 4.2 / 524.4M | DtvmxrTA (0.536 SOL tip) landed in the trigger slot; we landed in the next | ALIGNS |
| p2#1470 | 4.2 / 95.9M | FUJKrQhx in the trigger slot (196.9M); we landed slot+6; unrecorded | ALIGNS |
| p5#2 | 1.75 / 4.30M | A9pQ1Qsv in the trigger slot; unrecorded (shyft timeout) | ALIGNS |
| p1#138 | 4.2 / 51.7M | 6AGp6zbG seen 8.8 ms after our send; we landed slot+5; unrecorded | PARTLY |
| p1#144 | 0.74 / 6.25M | 5CKAa7Wm seen 27.4 ms after our send; unrecorded | PARTLY |
| p2#48 | 0.32 / 29.8M | MriyaNN8 at idx+1 took a different pair; HjjhSHoQ, sent 70 ms after us, took ours | PARTLY |
| p5#64 | 0.92 / 27.0M | No arb closer; two ordinary buys moved our pool before our slot+1 landing | PARTLY |

**Phantom or overpriced (29, all PARTLY):**
- **Torn split-route state (AgmLJBMD trigger), DLMM untouched in the block:**
  - p2#750: 0.65 SOL / 5.38M, DLMM leg −390 bps.
  - p2#1238: 1.19 / 24.2M, −630 bps.
  - p2#1326: 0.75 / 8.59M, −409 bps.
  - p10#444: 1.28 / 13.8M, −441 bps; landed after 41.7 ms and still failed.
  - p10#596: 0.46 / 4.62M, DLMM leg short.
  - p9#12: 0.82 / 3.85M; PumpSwap was priced at its pre-trigger state.
- **BGghhU9j's failed 3.57 SOL buy left in our prediction for pool 4pANrqEv:**
  - p3#896: 2.59 / 49.2M.
  - p3#894: 2.16 / 32.9M.
  - p3#898: 2.16 / 32.9M. This attribution is weaker: #898 came 1.72 s after the decode.
- **Failed decoded sells stacked into our predictions:**
  - p6#364: 4.2 / 1.122 SOL.
  - p11#132: 4.2 / 1.435 SOL; we predicted 54.6B tokens and got 40.2B.
  - w5h3-p2#662: 4.2 / 1.684 SOL; 12 of 12 copies failed.
  - w5h3-p2#694: 4.2 / 1.431 SOL; 16 of 22 failed.
  - w5h3-p2#704: 4.2 / 1.100 SOL; 17 of 17 failed.
- **Failed CPD18rED arbs left in our prediction for AwmaWjsR:**
  - w5h3-p1#204: 0.14 / 32.6M.
  - w5h3-p1#206: 0.13 / 32.9M; DLMM leg −33%.
- **DreMAMRc mispriced, with no rival involved:**
  - w5h3-p2#674: 0.79 / 3.40M.
  - w5h3-p2#220: 0.60 / 4.92M; zero swaps between the trigger and us.
  - w5h3-p2#752: 4.2 / 348.4M; zero swaps.
  - w5h3-p2#730: 4.2 / 54.4M.
  - w5h3-p2#690: 0.23 / 3.68M.
  - w5h3-p2#184: 0.076 / 6.79M; landed 17.5 ms after send and still failed.
- **Rivals captured 0-10.5% of our quote:**
  - p5#266: 4.2 / 18.5M.
  - p7#338: 4.2 / 9.51M.
  - p7#340: 4.2 / 17.8M.
  - w5h3-p2#556: 1.66 / 47.3M.
  - w5h3-p2#558: 0.26 / 4.21M.
- **Real gap, but our quote was wrong anyway:**
  - w5h3-p2#664: 4.2 / 454.5M; the real gap was +1.83M and our quote was 11.7% high.
  - p10#156: 3.04 / 37.3M; our DLMM leg was quoted 1.26% high.

**Our bugs and startup (5, all PARTLY):**
- **Missing DLMM bitmap-extension account (0x1794).** In each case a rival had already taken the gap first:
  - p2#616: DsCJ5siu +5.44 SOL, XUrKb2aK +2.88 SOL.
  - p2#786: HxjwdF32 at idx+1; we had also overpriced the gap about 1.65×.
  - w5h3-p1#176: 9EwQoN74; unrecorded.
- **CU limit:** w5h3-p1#250 ran out of compute at 272,006 of 272,015 CU, after R32xAccF had taken the gap.
- **Startup:** p2#0 was sent 3,033 ms late, most likely because the gate's sim RPC timed out at boot (inference).

## 5. The big bolt win (w5h2-p5#648)

**Landing:**
- Slot 453069812, block index 1391 of 1510; the trigger was at index 1311.
- First seen 22.34 ms after the bolt send. That ranks 27th of 971 direct landings, the top 2.8%.
- Leader GnC339vk: Jito client, not BAM, on DoubleZero in Amsterdam (RTT 6.8 ms), in the first of its 4 slots.
- 16 copies shared one nonce. The bolt copy landed, paying a 1M tip (paid only because it succeeded).

**Why it won:**
1. **The trigger.** AgmLJBMD's DFlow split-route sell of 7.53T 9dSMwFfP across both of our pools. A split route leaves both pools at about the same price, so there was no gap at the trigger's state. 8oSD5a9E's rung-0 backrun in the same bundle took a different pool pair (+0.22M).
2. **Our quote was wrong.** The engine read a half-updated PumpSwap snapshot: SOL vault after the trigger, token vault before it. That snapshot reproduces our predicted output (1,885,413,758) to the lamport. On the true post-trigger state, at the 80 bps creator-fee tier, the round trip is −103,451,784.
3. **Outside buyers saved it.** Three PumpSwap buys landed between the trigger and us, all with durable nonces and large tips:

| Buyer | Index | Size | Round trip for us afterwards |
|---|---|---|---|
| C86oRMyU | 1358 | 1.868 SOL | −82.7M |
| 13VK7ZrR | 1359 | 6.956 SOL | −8,519,739 |
| iK7BmyUo | 1370 | 3.555 SOL | +30,002,068 |

   The DLMM leg was exact; the PumpSwap leg came in 10,034,688 above our prediction.
4. **We were first in line.** The real gap opened at index 1370, about 5 ms after we sent.
   - Before us, BACKsEEY (our direction, same state, 104M in-tx tip) failed with "Arbitrage was not profitable", and 5CKAa7Wm (opposite direction) failed.
   - After us, 8 same-direction rivals failed.
   - MriyaNN8 was absent.

**Is it repeatable? No.**
- On this token, 40 direct sends landed: 39 failed and 1 won, net +26.38M against 536.7M of summed expected profit.
- All 7 split-route sends on this pair were priced on partly applied state, and the other 6 failed (round trips −12.4M to −81.0M).
- The engine also never decoded C86oRMyU's buy (router H8fw2f). Its +20 ms reprice (opp 876) was therefore on wrong state too, and the 400 ms pair lock suppressed it.
- What is repeatable is the delivery: bolt plus a nearby non-BAM leader gave a top-3% landing.
- **Verdict PARTLY.** It contradicts P3 on outcome, is a single P4 counterexample, and leans against P8. P11 is not contradicted: this was rung-3 value, which the research calls reachable.

## 6. Prediction scorecard

| # | Result | Evidence |
|---|---|---|
| P1 | **Held** | 23/23 bundles tiny; tip formula exact 23/23; round trip within 12 lamports in 22/23 (p6#311 was −4,072 after a rival hit our sell pool). Negative profit comes only from rent in 13 accounts. 6 of 23 are USDC; 9 are Dlmm>Dlmm. |
| P2 | **Held** | Send to sighting p50 66 ms (research: about 79). Same-slot wins landed +65 to +743 positions after the trigger. We were the first value-taking trade in 23/23. Sibling big gaps went to faster rivals (GxDC9e7S, MriyaNN8, XUrKb2aK, 4XBqViD1, R32xAccF). |
| P3 | **Partly** | The outcome holds almost always: 986/987 landed and failed, send to sighting p50 137 ms, 59.5% in a later slot, and paths, tips or priority changed nothing. The mechanism holds for about 63% (taker before our send) and for all curated real gaps. But 29 of the 66 analyzed losses were phantoms, including 10 of the 16 largest, and 8 were lost on landing delay after we had sent first. |
| P4 | **Held** | 1 win in 1,511 attempts of 1 SOL or more. The bundle arm went 0/901, the same count as in w5h; the direct arm went 1/609 sent. |
| P5 | **Partly; mechanism new** | Wins cannot test overpricing. The large overpriced quotes came from failed-swap predictions and torn reads, not from slow persistent gaps. |
| P6 | **Held, smaller** | 16 unrecorded failed landings (1.6% of landings), 419,911. 2 were lost to shyft status timeouts; 14 landed 3-6 slots after the trigger, after the single 1 s status check (inference). |
| P7 | **Untestable** | The gate was never off; only SimCfg went off. Stale failing sims were right on 967 of 968. Honoring them would have saved 23.90M but lost the bolt's +28.97M before rent. |
| P8 | **Mostly held** | An untipped copy landed first in about 2/3 of attempts; no failure paid a tip. The one direct win came through bolt, a paid path added at p3. |
| P9 | **Held** | 3/23 bundle wins on BAM leaders, against a 38.1% BAM slot share (P = 0.0085). Direct failures landed on BAM at the normal rate (39.6%). |
| P10 | **Held, low power** | Band where the cap binds: w5h2 1 win in 2,803 attempts, w5h3 0 in 634 (about 0.2 expected). The drop in w5h3 is in the band the cap never touches (2/591 vs 17/2,206, P ≈ 0.18). |
| P11 | **Partly** | MriyaNN8 is the most frequent closer (18.4%). The biggest single takes went to others: DsCJ5siu +5.44 SOL, XUrKb2aK +2.88, CzYQ2kFn +2.66, JAkGWTYL +0.64, DtvmxrTA +0.63, A9pQ1Qsv 0.59 gross. About 32% of p1/p2 closers are rung-3 or sprayer bots that the research calls reachable. |

## 7. What is new, and what to do next (ranked)

1. **Failed decoded swaps poison our pricing.** This drives 10 of the 16 biggest losses and most of the giant quotes.
   - Apply predictions only once the swap is confirmed, or discount them.
   - Drop the whole stack on any newer account update for that pool.
   - Deduplicate by (signer, pool, amount).
   - Turn on `skip_failing_signers`.
   - Make the 1.5 s expiry real rather than housekeeping-only.
2. **Torn trigger state and missed decodes.** Wait until all of a trigger tx's writes are applied before pricing, and decode the H8fw2f router. This would have blocked the 6 split-route losses (and the bolt win).
3. **Rent.** Rent turns the bundle arm from +163k to −17.9M. Add a close-account instruction to the same tx, or pre-create and later close token accounts for frequent mints.
4. **Fix the DLMM bitmap-extension bug and the CU limits.** pools.rs checks for the extension only once, at boot. Together these cost 24 failures and 756,015.
5. **Make an explicit sim-gate policy.**
   - Today stale failing sims are always overridden. That passed 967 losers and 1 big winner.
   - Simulating on the trigger's own state would be informative.
   - Don't send when the gate RPC times out at startup; this caused 7 failures 11-15 slots late.
   - The gate also adds about 2.3 ms between signing and sending on direct copies.
6. **Outcome tracker.** Add a second status check and retry on status-RPC errors.
7. **Attribution.** Stop using opportunities `taker` as "who closed the gap". It misses reverted, zero-capture, single-pool and some account-update closers. Re-enable the recorder for one segment.
8. **Rivals not in the catalog:**
   - 7dGrdJRY (King7ki4, idx+1 with Astralane or Nozomi tips).
   - gtagyESa, shakRDxy, 4YP7YJFD, B7XwXUuZ, HxjwdF32, DsCJ5siu and 78XwCxCT.
   - BGghhU9j copied our #884 size to within 25,032 lamports and its tip to within 3 lamports. Then its failed copy poisoned our pricing for #894-#898. A leak or mirror is possible (inference).
9. **w5h3 changed more than the bundle tip cap.**
   - It removed tip_share 0.5 / tip_max 50M from 13 direct paths.
   - It raised max_failed_fees to 25M.
10. **Smaller observations:**
    - Several triggers were rival arbs, so we were pricing their leftovers.
    - Bundles on far leaders (London, Singapore) landed slower (n is small).
    - Duplicate same-pair bundles (#245 and #246) were not stopped by the pair lock.

## 8. Data gaps

- **Recorder off from w5h2-p3.** There are no rivals, exec, txarr or moves records, so rival arrival times after p2 come from block position or a sample only. Pre-send ordering for p3#884 is unverifiable.
- **Block order only partly verified.** Block order between the taker and our tx is checked only for PumpSwap pairs in p1/p2 (the exec feed is PumpSwap-only).
- **Thin PoH coverage.** The bolt block is covered only for indices 0-49, and there is none for the wins in p9-p11 and w5h3.
- **BAM evidence is weak.** BAM status comes from a static per-validator file, and the Jito explorer saying "not found" on BAM leaders proves nothing about bundling.
- **Missing Jito verdicts.** At least 5 of the 23 landed bundles have no verdict row, and 1 has only a would-fail verdict.
- **Phantom attributions are inferred.** They rest on engine.rs logic and on predictions.jsonl. No engine replay was done; #898 and #204/#206 are the weakest.
- **Two unknowns about the bolt win.** The DLMM bins at index 1370 were not fetched, so the true optimal size is unknown. BACKsEEY's failure is not decoded.
- **The unrecorded-landing cause** is inferred from landing slots; the settle and retry code was not read.
- **Sampling bias.** The curated loss sets are skewed toward w5h3-p2 and DreMAMRc, so the phantom share does not extrapolate directly to all 986 failures.
- **No 4XBqViD1 sends** were present in the stratified sample; flashblock, rpcfast and everstake failures were not sampled.
- **Rent accounts** were left untouched (no writes were allowed); 4 were confirmed still open.

**Files** (all under `/tmp/claude-1000/-home-moiz-arbed-arb-lab/5e4b11f2-122d-406a-b161-b66016d99287/scratchpad/cherry/work/`):
- Ledger: `shared/derived/ledger-w5h2w5h3.jsonl`
- Per-analysis scratch: `wallet-ledger/`, `wallet-wins1/`, `wallet-wins2/`, `wallet-loss-agg/`, `wallet-loss-top/`
- Verifier scratch: `verify-wallet-*/`
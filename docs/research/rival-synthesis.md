# Rivals on our watched pools: synthesis (w5h-p10..p15, w5h2-p1; 0.967 h, slots ~453,041,000-453,056,300)

**Sources.** This report draws on:
- three PATTERNS.md checks;
- three cross-cutting studies: senders, latency/ordering, programs;
- 13 rival dossiers, each with verifier verdicts. Corrected values are used and refuted facts are dropped;
- the census roster (work/census/roster_md.md).

**Evidence labels:**
- **[PS]** measured on exec.jsonl, which covers PumpSwap-touching txs only.
- **[S]** shreds (rivals.jsonl), no result.
- **[R]** getTransaction samples.
- **[J]** Jito explorer.
- **[W]** wallet balances.

"Big win" means gain >= 0.01 SOL. Slots ran 269 ms, not 400.

**Synthesis check.** `failed_fees_lamports` in outcomes.jsonl is a running counter. Its final values are 497,170 lamports (p12), 1,117,914 (p14) and 632,200 (w5h2-p1), so 2.25M lamports in total. Two verifiers cited "0.416 SOL of direct-copy failed fees". That figure summed the counter and is **refuted**.

## 1. Bottom line

- **The market is bigger in count than PATTERNS.md says, but not in SOL.**
  - PATTERNS measures PumpSwap only: 30.3 SOL/h in p10-p15.
  - Non-PumpSwap wins add about +75% in count (about 3,880 wins/h) but only about +12% in SOL (3.8 SOL/h, CI 2.3-5.6). Dust and USDC wins add about 9%.
  - The recent market on our pools is **about 34-37 SOL/h**. MriyaNN8 takes about 50-52% of big-win SOL.
- **Value goes to sequencing, not to reaction speed.** 31% of big wins, carrying 41% of big-win SOL (about 11.5 SOL/h), execute at block index +1 behind the tx that opened the gap [PS].
  - About a quarter of these by count, and about 15% by SOL, are same-bundle backruns [J].
  - The rest sit adjacent to the opener without a Jito bundle: Mriya's high-bid tier, 8oSD5a9E's "h" path and 9EwQoN74's priority path. How they get there is not identified.
  - The openers are mostly retail and aggregator flow: FLASHX8D, Jupiter, 6Vo3245e, GMGN and AgmLJBMD's DFlow executions.
- **Same-slot reactive gaps are 47% of big wins** (about 10.6 SOL/h, arrival gap p50 10.5 ms).
  - On-chain-sizing bundlers win them at a profit: A9pQ1Qsv +0.82 SOL/h, Bgokg3ju +1.71 SOL/h.
  - Standing-queue sprayers win them at a loss: CzYQ2kFn -1.20 SOL/h, HiP about -0.25, 4Qv3 -0.18 [PS], FUJKrQhx -0.30 without its jackpot.
- **We are one inclusion cycle late.**
  - On state triggers we send p50 15.3 ms after the first shred. 14.9 ms of that is waiting for Haan's state feed; our own code takes 0.3 ms.
  - Bundles then land p50 79 ms after sending, and direct copies 170 ms.
  - On gaps we contested, the winner was already in shreds before our send in 86% of cases for Mriya, 92.5% for 9EwQoN74, 80% for 8oSD5a9E and 36-56% for the bundlers and sprayers.
- **"Would-fail" mixes three causes:**
  - 48%: the gap was already closed when we sent.
  - 22%: we lost inside Jito's pipeline.
  - 26%: Jito-state lag or phantom gaps.
  - Two compounding problems: our own sims ran at trigger slot -1 in 98-99% of cases, and our pricing is weak. Persistent priced gaps were about 6x overpriced, and for 18 of 23 slow-slice wins we had no opportunity at all.
- **No missing sender explains the gap.**
  - Jito bundles carry about 56% of win count but only 16-22% of win SOL.
  - Our paid direct copies landed about 265 times with 0 profitable outcomes. Their 1M-lamport tips lost to our own untipped copy.
- **Fixes, ranked:**
  1. Fix simulation and trigger state, and move to shred-level triggers.
  2. On-chain sizing with a pool basket and a bundle-level profit guard.
  3. Pricing coverage: multi-hop, USDC and hot-token pools.
  4. A BAM landing check.
  5. Apply to backrun order-flow programs.
- **Do not copy the volume sprays.**

## 2. PATTERNS.md review

| # | Claim | Verdict | Corrected statement | Why |
|---|---|---|---|---|
| P1 | Big wins are same-slot backruns: 91% same slot; gap p50 1.6 ms, 48% <1 ms; 90% follow another bot's arb | Partly | Same slot holds: 90% with the scan's opener, 89% with the corrected one. The sub-ms gaps are an artifact of txs arriving in the same shred batch. On 116 pairs with PoH times (mostly small wins), 55% are <1 ms by arrival but only 31% by PoH; the two agree from 7 ms up and at 150 ms. "After an arb" is 62% (342/552) once non-rivals openers are counted, 57% with the corrected opener, and about 54% if AgmLJBMD counts as non-arb. 31% of big wins sit at idx+1 and are not reactions | Openers missing from rivals.jsonl were left out of the denominator; 27% of openers were no-ops |
| P2 | MriyaNN8 takes 59% of big-win SOL; no tip, bid about 1% | Stands, smaller | About 50% in p10-p15, 50-52% with non-PumpSwap. Bids are spread: 127 wins under 1%, 166 at 1-30%, 59 at 30-36%. 57% of its gain comes from 83 non-nonce high-bid txs, and 15 of its txs are 2-tx backrun bundles | Resample; dossier |
| P3 | Big wins need size | Stands, with a caveat | Mriya made 75% of its gain at input >=4.2 SOL; Bgok made 54% from 5 trades over 4.2 SOL. The size bands miss v1 txs (91 of the 97 big wins of unknown size) | sizes.py used maxSupportedTransactionVersion 0 |
| P4 | DLMM<->PumpSwap is 85% of big-win SOL | Changes | 81% in p10-p15 (PumpSwap only); **about 73-74% (68-78%)** once non-PumpSwap big wins (about 2.7 SOL/h) are added | PumpSwap-only exec |
| P5 | No-tip winners bid 13% of gross, Jito winners 71%; one bot paid a 39.5 SOL "tip" | Partly | The 13% is a sum dominated by 9EwQ (69%) and 8oSD (67%); the median is 1.0-1.25%. The 71% comes from one 13.6 SOL tip (6AGp6zbG); without it the sum is 41% and the **median 34%**. ESuvjvsQ's 39.5 SOL is a WSOL re-wrap; its real tips are about 0.006 SOL. Zero-priority "no-tip" wins are mostly hidden bundles (48/53) | One outlier; every System transfer counted as a tip |
| P6 | The slow slice is small (1.0 SOL/h gross); we could capture 0.02-0.1 SOL/h | Stands as "small"; the capture estimate is unsupported | p10-p15: 15 wins, 1.47 SOL. Which wins belong to it is unstable (only 9 overlap with the corrected reference), and one win of 12.46 SOL size is 0.99 SOL of the total. Within our size cap: at least 0.42 SOL in 0.915 h. Non-PumpSwap adds 0.04-0.14 SOL/h. We had no opportunity for 18 of 23 | The limit is pricing coverage, not speed |
| P7 | Small wins are numerous but worth little | Stands | Gap ages are understated (Jito small wins p50 66 -> 85 ms). Non-PumpSwap adds about 2,160 small Jito wins/h, but the slow small slice stays under about 0.3 SOL/h | Opener method; blind spot |
| P8 | Our results fall with size; DAMMv2<->PumpSwap holds 37% of small Jito wins | Partly | Our counts hold, but 16 of our 31 "wins" had wallet profit <=0 (token-account creation cost). With non-PumpSwap counted, DAMMv2<->PumpSwap is about 25%, and DLMM<->DLMM (469/h) and DLMM<->DAMMv2 (389/h) match DLMM<->PumpSwap (456/h) | PumpSwap-only share |
| P9 | Volume does not pay; bundle-only bots break even | Stands, with fixes | The sprays do lose. But "landed" really means "touches PumpSwap". The bundle-only break-even is the ESuvjvsQ wrap (corrected: gross 3.16, tips 2.93). A9pQ is +0.79 SOL, not -0.02. 4Qv3 is one entity of 16 wallets. 8oSD is about 0.7 SOL/h without its windfall. Sprayers lose through tips on txs that succeed but make no profit | Every transfer counted as a tip; exec coverage |
| P10 | Higher fees do not win on their own; snipers scale bids to the gap | First half changes | On no-tip txs, the top priority bucket wins more in 7 bots, less in 2, the same in 5. For 6AGp, 8oSD and Dtvmx the priority-0 bucket is tipped bundles. The scaling is mechanical: 8oSD's bid = min_profit = 0.7 x expected gross, and 9EwQ's >1M bucket is its revert-protected path. Jito's <=10M bucket is 99% failed txs | Hidden bundles; path confound |
| R1 | Re-price at the next slot (+400-800 ms), then send 1-4.2 SOL | Unproven; deprioritize | The next slot is +270-540 ms. Only 2.8% of priced gaps stayed untouched for 540 ms or more (a lower bound). Like-for-like, persistent gaps were overpriced: our expected 0.076 SOL vs the takers' 0.0124 SOL gross. Our sims ran at slot -1, so the would-fail verdicts cannot test R1 | Fix pricing and simulation first |
| R2 | Small sizes; move budget from DLMM<->DAMMv2 to PumpSwap pairs | Partly | Small caps are fine, but the market reasoning is a PumpSwap-only artifact. On our own data, keep Dlmm>Dlmm (17/1,542 = 1.10%); DLMM<->DAMMv2 is 0/939 and DAMMv2<->PumpSwap 3/437. Value is under 0.01 SOL/h either way | Blind spot |
| R3 | Bid 30-35% of gross on small Jito gaps | Changes | Winners' tip/gross rises with gross: 16% under 20k lamports, 47% at 20k-100k, 54% at 100k-1M, 64% at 1M-10M. Tier the tip by band. Tips are not why we lose (0 lost auctions) | The median is driven by sub-20k wins |
| R4 | Rotating hot-token list | Untested; keep it for pool discovery | Value concentrates in a few tokens (7VertkgF for Mriya, FUJK, 4Qv3 and Bgok). 9 of 23 slow candidates touched pools we never priced, and winning legs are often unwatched (8oSD's trio, DdLAc65E). Reallocating budget alone does not fix would-fail | Coverage evidence |
| R5 | Stop paid direct sends (0 wins in 239 landed) | Stands; the reason changes | w5h: 236 landed, 3 ok (2 were token-account rent, 1 lost 7,652 lamports). p12/p14/w5h2-p1: 163 landed, 0 ok. Helius Sender Max: 29/29 landed, 0 wins. Copies carrying 1M tips were sent, but an untipped copy always landed first, 170 ms after the send. Failed fees were only 2.25M lamports. The priority level itself (10k/60k/100k µL/CU) is untested | Our own outcomes |

## 3. Rival catalog

Per-hour figures are over 0.967 h.

**MriyaNN8**: about 50% of big-win SOL. Program AN225ykG (507 KB).
- Design: fixed amount_in (p50 0.50 SOL, max 80.4), a profit guard and a full revert, which is close to ours. 2-5 hops and USD-quoted routes.
- Senders: 94.5% of txs bid by priority fee only. It uses 786 nonce accounts.
- High-bid tier: 83 non-nonce txs, 49/49 ok, 8.71 SOL (57% of its gain), 79/83 on Jito-client leaders, 3/52 in bundles. 15 bundles have the shape [another signer's tx, Mriya].
- Ordering: at idx+1 in 62% of same-slot wins. 53% of its gain came behind users of 6Vo3245e, a retail platform with 7,170 signers.
- Economics: +14.32 SOL [PS] (14.8/h), plus about +5.3 SOL non-PumpSwap (CI 0.6-11.7). 62% of its PumpSwap txs fail. 75% of its gain came from inputs of 4.2 SOL or more.
- Edge: it has the opener before execution, plus capital.

**8oSD5a9E**: program HMS28jpC. It runs an on-chain sized search where bid = min_profit = 0.7 x expected gross.
- Backrun engine: 77 of its 89 [PS] wins.
- Nozomi state shots: 565 txs, 5/323 ok.
- "h" path (no tip): 91/91 ok, none on BAM leaders, not in the Jito explorer. A revert-protected non-Jito path that is not identified.
- "j" path: 45/45 are 2-tx bundles [opener, 8oSD].
- Economics: +10.63 SOL [PS], but 10.01 SOL of that is a trio of USDC-triangle trades whose meme legs we don't watch. Without the trio, about 0.7 SOL/h.

**9EwQoN74**: program Babq1RQD; inventory of 537 SOL plus 143.5k USDC.
- "-P-" priority path: 76/76 [PS] wins, 0 failures, none on BAM, 0/32 in bundles, bid p50 74% of gross. The Harmonic attribution is an inference.
- Astralane 3-tx backrun bundles.
- Nonce lottery: 662 txs, 6 wins. A fan-out tier across 15 services won 0.
- Ordering: idx+1 in 42 of 53 wins.
- Economics: about 0.96 SOL (1.0/h), 43% of it non-PumpSwap.

**4BQ6ATUt**: a customer of SolanaMevBot.com (program MEViEnsc), plus its own program CGGq.
- Every tx is position 1 of a 3-tx bundle [FLASHX8D user swap (p50 5 SOL), 4BQ6 backrun, tipper calling 6ubjFJSt]. The Jito tip equals 20% of the user's fee (10/10 sampled).
- It pays a flat 1M lamports per backrun to 10 rotating accounts, which have accumulated 40.8 SOL.
- Economics: +1.85 SOL [PS] (1.9/h); 44% of its txs are on pools we don't watch.
- Edge: exclusive access to that flow.

**Bgokg3ju**: program ATM777JF.
- Design: a 5-byte instruction carrying 2-4 candidate pools. Route and size are chosen on-chain, and a guard instruction makes the tip conditional on profit on the normal path.
- Senders: all 198 landings are self-tipped Jito bundles (136 bundles, 62 of them 2-tx). Tip tiers are 170k x {1, 2, 4, 15, 30, 60} lamports; tip/gross p50 0.33. 54% of landings are on BAM leaders.
- Economics: +1.66 SOL (+1.71/h). 54% of gains came from trades over 4.2 SOL; it holds 746 WSOL. 18 early exits on BAM leaders leaked 0.054 SOL.

**A9pQ1Qsv**: program Cd4A3vR5, run as 4 instances.
- Bundle shape: 3 txs [arb A, arb B + funding, tipper C]. A bundle-level guard requires profit of at least tip + 15k; legs that would lose do nothing instead of failing.
- Tips are 170k or 5.1M lamports, 16.6% of gross overall.
- Economics: +0.79 SOL (0.82/h); 27% of gross is non-PumpSwap; 594 WSOL. It lands about 2x as often per slot on BAM leaders.

**DtvmxrTA**: program 8KDGPdXX; 2-4 hops, Manifest and USDC legs.
- Senders: 99% durable nonce; 77.6% direct with no tip. A side wallet pays Jito tips, on BAM leaders only.
- Economics: +0.58 [PS]; at least 0.85 SOL/h including non-PumpSwap (inferred). 94% of its PumpSwap txs fail.
- p15 slot 453052858: our 4.2 SOL bundle at +0.8 ms came back would-fail. Its 8.75 SOL direct tx at +12 ms netted +0.225 SOL. Our engine had priced the optimum at 8.40 SOL.

**FUJKrQhx**: baskets of candidate pools with uncapped on-chain sizing, a strict (revert) mode and a soft (no-op) mode, 4-5 send paths, 29.6k tx/h.
- Economics: +3.36 SOL [W] over 1.134 h, but -0.35 SOL without two p14 wins.
- Its 3.29 SOL win landed 17.7 ms after an AgmLJBMD swap. Our 6 direct copies, sent at 17.4 ms, never landed.

**CzYQ2kFn**: a standing spray of 210k tx/h.
- Each tx carries p50 6 candidate pools and a +1-lamport guard, does nothing on a miss, and 96% pay priority only.
- Economics: -1.20 SOL/h [W].

**R32xAccF**: three arms.
- A: a nonce spray using 5,020 nonce accounts; likely loses money.
- B: own 1-tx bundles, 113/113 ok.
- C: backruns through sender services (Astralane 3-tx bundles).
- Economics: about -0.03 to +0.2 SOL/h.

**HiP group** (66666y3R, Luckywzb, DEEPJncp): the hiparb v1.9.1 program with min_profit 0.
- Standing bundles in 83% of Jito slots; 99.3% of its txs are no-ops that still pay fee and tip.
- Economics: about -0.27 SOL.

**4Qv3mbzc group** (16-18 wallets): each tx borrows a shared vault of about 136.5 SOL and pays a 7% profit cut back to it.
- Mode 0 does nothing on a miss (Jito and no-tip copies); mode 1 reverts (Nozomi copies).
- Economics: -0.17 SOL [PS]. Only one 0.621 SOL Nozomi win was positive.

**Census roster** (46 signers, 1.003 h):
- SOL won on our pools: Mriya 13.58, FUJK 3.73, Bgok 1.38, 4BQ6 1.08, DtvmxrTA 0.88, DsCJ5siu 0.80, JAkGWTYL 0.66, 8oSD 0.65, CzYQ 0.63.
- Worst [PS] nets: CzYQ -1.36, Dy1jE82C -1.24 (it rotates programs), CP2PtWw9 -0.33, DsCJ5siu -0.29, AXmnRBrN -0.28.
- Corrections to the census: A9pQ is +0.79 (not -0.018) and 4BQ6 is +1.85.
- Platforms: NotArb (4DcT8f8V, +1.42 [PS]), Copychain (14 wallets), SolanaMevBot.com, hiparb.
- AgmLJBMD is a DFlow/Jupiter flow executor (-30.8 SOL), not an arb bot. It is one of the main gap openers.

## 4. The sender landscape

- **True bundle share** (4,925 [PS] wins, 39.79 SOL): about 56% of wins by count landed inside Jito bundles, but only about 16% of SOL (22% without 8oSD's trio). Visibly Jito-tipped wins are 48% of count and 8% of SOL.
  - Zero-priority "no-tip" wins are hidden bundles in 48 of 53 cases. The tip is paid in one of four ways:
    - by a CPI inside the arb tx;
    - by the signer's own second tx;
    - by a routed tipper wallet (A9pQ, CtKVtEVG);
    - by a relay wrapper: the Helius, Speed and BlockRazor tipper wallets pay 95-101% of the user's tip.
  - No-transfer wins that pay a priority fee are genuine non-bundle landings: 1 of 51 was in a bundle.
  - The explorer does cover BAM: it found 184 of 186 Jito-tipped wins.
- **Services that win** ([PS] wins / SOL):

  | Service | Wins | SOL |
  |---|---|---|
  | No transfer | 2,225 | 28.30 |
  | Jito | 2,354 | 3.08 |
  | Helius | 86 | 5.57 |
  | Astralane | 154 | 0.66 |
  | Nozomi | 11 | 0.79 |
  | All others together | under 30 | |

  - Nozomi, Falcon, Stellium, 0slot and FAST copies land and then fail.
  - The value paths are of two kinds:
    - Revert-protected non-Jito priority paths: 8oSD "h", 9EwQ "-P-", and likely Mriya's non-nonce tier. They succeed 100% of the time, appear only on Jito-client leaders that are not BAM, and bid 70-74% of gross.
    - Order-flow backrun bundles: built by the searcher as [user tx, arb], Astralane 3-tx bundles, and FLASHX8D -> 4BQ6.
- **By leader kind.** Slots split Jito 60.8%, BAM 37.6%, non-Jito 1.3%. Jito-tipped wins per 1,000 slots: 189 on Jito leaders, 172 on BAM.
  - Profitable bundlers over-index on BAM: Bgok has 54% of its landings there, A9pQ lands about 2x as often per slot, and R32x's arm B landed 196 of 284 there. We landed 2 of 17 known bundles on BAM.
  - A claimed effect of leader distance on priority-path SOL turned out to be an outlier artifact.
- **Fan-out.** The value winners do not spray: Mriya sends 1.24 txs per slot-and-pool group. Spray losses come from tips paid on no-op txs that succeed (HiP, 4Qv3 mode 0, CzYQ's Jito copies, the VLX* sprayers), not from failed landings.
- **Unknown destinations.** None is a validator identity or vote account (0 of 9,232).
  - Glaive and Soyas are now documented senders. Speed is a confirmed relay. FAST, Sp*, LandX, D1Mc and nigerL are inferred to be senders.
  - pfn x16 and 6HRgJ look like retail platform fees.
  - GBXk, paid by Mriya, may be a profit share of about 50% (inference).
  - Dpjf8e16 is ESuvjvsQ's own WSOL account.
- **Our paths by segment:**
  - p10 and p15: bundles only.
  - p12: a TPU arm (shyft, haan, tpu-direct) at 10k µL/CU.
  - p14: 6 paths at 60k µL/CU, with 1M tips on Helius, Astralane and Nozomi.
  - w5h2-p1: Helius Sender Max, tip p50 5.03M.
  - Every attempt carries a durable nonce, and the arms alternate per attempt.

## 5. The latency/ordering ladder

Big wins, p10-w5h2-p1 (n=266, 27.27 SOL) [PS]:

| Rung | Share of big wins | Gap to opener | Who |
|---|---|---|---|
| 0. Same bundle as the opener | about 25% of idx+1 wins by count, about 15% by SOL | 0 (same PoH) | 4BQ6 (100%), 8oSD "j", Mriya's tipped txs, 9EwQ and R32x via Astralane |
| 1. idx+1, no bundle | the rest of the 31% (41% of SOL is at idx+1) | 0 | Mriya high-bid tier, 8oSD "h", 9EwQ "-P-" |
| 2. idx+2..5 | 13% | PoH p50 2.2 ms | mixed |
| 3. Same slot, later | 47% (10.3 SOL) | arrival p50 10.5 ms | 4Qv3 12.2, A9pQ 14.4, Bgok 15, CzYQ 17, HiP about 14-21, DtvmxrTA 23.8 ms |
| 4. Next slot | 5% (21% of all wins) | p50 177 ms | small wins |
| 5. Two or more slots later | 3% | p50 2.3 s | rare |

- 99% of idx+1 wins arrive within the leader's RTT + 2 ms of their opener, so they are not reactions.
- In rung 3, 41% of the big wins (3.26 SOL, about 3.4 SOL/h) have a gap above RTT + 2 ms. 31% of slots have a leader less than 1 ms from Cherry.

**Where we sit** (state triggers, n=2,172), median time for each step:

| Step | p50 |
|---|---|
| First shred -> Haan state update | 14.87 ms |
| Decide | 0.07 ms |
| Sign | 0.13 ms |
| Send | 0.08 ms |
| Jito acknowledgement | 0.65 ms |
| Jito verdict | 6.4 ms (p90 114) |

- Landed bundles show up p50 79 ms after the send (n=17); 12 of the 17 landed in the trigger's slot.
- Direct copies show up 170 ms after the send; only 60 of 163 landed in the trigger's slot.
- Our same-slot landings sit 160-1,200 block positions after the trigger.
- When we decode the trigger from shreds, we send at 0.4 ms, but 218 of 220 such bundles came back would-fail, 75% of them before any rival had moved the pools.
- On the 147 big gaps we sent on, the winner had already arrived before our send in 115.
- So we decide late in rung 3 and land late in the slot or later.

## 6. Programs and transaction shapes vs ours

- **Ours.** 8K8uyQDt (42 KB) takes a fixed amount_in and a min_profit, then reverts with 0x4e580002 after about 155k CU (117 of 121 landed PumpSwap txs).
  - On-chain min_profit is tip + base + priority + 1 for bundles, and tip + 1 for direct copies.
  - route_ix already supports 1-8 legs into any quote token. The 2-leg SOL-only limit comes from the engine (exec.rs:339) and from tx size (max 1,209 of 1,232 bytes).
  - Other parameters: 5 venues, v0 txs with 2 lookup tables (ALTs), CU limit p50 175-200k.
- **Rival design families** (watched-pool wins):
  - Full revert: 16.3 SOL, 13.5 of it Mriya.
  - Early abort: 16.0 SOL, 13.3 of it from 4 outlier txs.
  - No-op on a miss: 6.3 SOL, spread over many small wins.
- **What we lack:**
  - On-chain sizing (8oSD, Bgok, A9pQ, FUJK, CzYQ, HiP, 4Qv3).
  - Baskets of 2-7 candidate pools per tx, or 2 routes per bundle.
  - Multi-hop and USDC legs, including Manifest, Tessera V and ZeroFi.
  - SetLoadedAccountsDataSizeLimit and tight CU limits.
  - Reuse of winners' own lookup tables: Mriya's table DiPcRv8w is used by 15 signers.
  - Rotating programs against copiers (Dy1jE82C).
- **Tip interaction.** A no-op inside a bundle still pays the tip on a miss (HiP, 4Qv3 mode 0, the early exits of A9pQ and Bgok). The profitable designs keep the tip conditional on profit, with a bundle-level guard (A9pQ) or a guard instruction (Bgok).
- **Program design is not what decides the top earner.** Mriya's program is close to ours. Program design mainly matters for rung 3 and for leftover gaps.
- **Flash loans do not win:** only 2 of 1,189 executed Kamino flash-loan txs succeeded.

## 7. How we differ from each rival

**Our baseline:**
- About 1,014 pools; 2-leg SOL pairs.
- Fixed size, capped at 4.2 SOL; full revert.
- 1-tx Jito bundle with tip 0.7 x (expected - 5,000), capped at 0.1 SOL.
- A durable nonce on every attempt.
- Send at 15.3 ms; landing +79 ms (bundles) or +170 ms (direct) after the send.
- Failed bundles cost nothing.

| Rival | Venues/pools | Sizing | Program | Sender/tip | Nonce/fan-out | Rung | Fail cost | Decisive gap | Closable? |
|---|---|---|---|---|---|---|---|---|---|
| MriyaNN8 | DLMM+PS, 2-5 hops, USD routes, 28% off our pools | fixed, up to 80 SOL | like ours | priority fee, 34% tier, backrun bundles | 786 nonces | 0-1 | 1.44 SOL | has the opener before execution; capital | Structural |
| 8oSD5a9E | adds CLMM/Whirlpool, USDC triangles | on-chain | early abort | "h" path, 2-tx bundles | few copies | 0-1 | about 0.07/h | order flow, private path | Structural; sizing is closable |
| 9EwQoN74 | multi-hop, USDC | small trades, 537 SOL | guard covers its bid | priority path, Astralane | nonce lottery | 0-1 | 0.046 SOL | order flow | Partly (apply to the programs) |
| 4BQ6ATUt | PS<->DLMM | up to 23 SOL | no-op flag | flow bundle, 1M fee | none | 0 | 0.08 SOL | exclusive flow | Structural |
| Bgokg3ju | DLMM<->PS (80% of gains) | on-chain, up to 38.5 SOL | basket + guard | own bundles, tip tiers | about 1.2 bundles per decision | 3 | 0.054 SOL | sizing, 2 routes, capital | Engineering + capital |
| A9pQ1Qsv | same pools + CLMM | on-chain, 594 SOL | bundle guard | 3-tx bundles, 16% tip | 4 instances | 3 | 0.026 SOL | bundles that adapt and pay only on profit | Engineering |
| DtvmxrTA | 2-4 hops, Manifest | up to 17.9 SOL | guard = bid | direct; bundles on BAM | 50 nonces, size ladders | 3 | 0.40/h | multi-hop, capital | Partly |
| FUJKrQhx | baskets | uncapped | soft/strict modes | 4-5 paths | volume | standing | 0.36/h | volume + capital | Not worth it |
| CzYQ2kFn | 6-pool baskets | on-chain | +1 guard, no-op | priority fee | standing | standing | 2.2/h | copies already queued | Not worth it |
| R32xAccF | 12+ venues, USDC | small | fee+tip-1 guard | 11 services | 5,020 nonces | 0 / 3 | about 0.16/h | arm C flow; our valuation | Partly |
| HiP | groups of 4-6 pools | on-chain | min_profit 0 | standing bundles | 2-4 per slot | standing | 0.5/h | constant queue presence | Not worth it |
| 4Qv3 | hot baskets | vault-backed | 2 modes | per-wallet profile | 16 wallets | standing | 1.4/h | spam + shared vault | Not worth it |

## 8. What this implies for us, ranked by expected value

1. **Fix the trigger and simulation state, then use shred-level triggers.**
   - Evidence: our sims ran at slot -1 in 98-99% of cases; 10 would-fail bundles landed and passed our profit check; 22% of would-fails were lost inside Jito's pipeline.
   - Test: an A/B of bundle send delays of 0, 5, 10 and 20 ms after shred-decoded triggers, plus simulation run with our tx inserted after the trigger.
   - Shred-level triggers remove 14.5 ms of waiting for Haan.
   - Target: rung 3 on nearby leaders, about 3.4 SOL/h of market big-win SOL with a gap above RTT + 2 ms.
2. **On-chain re-sizing, a basket of 2-4 pools per token, 2 routes per bundle, and a bundle-level guard** so the tip is paid only on profit. This is the design A9pQ and Bgok win with, at 16-33% tip/gross. Do not put plain no-ops in bundles.
3. **Improve pricing coverage and accuracy.**
   - Evidence: we had no opportunity for 18 of 23 slow-slice wins; 9 touched pools we never priced; persistent gaps were about 6x overpriced; three p14 quotes showed 1.15-1.58 SOL.
   - Add 3-hop and USDC routes (an engine change only).
   - Add pools of hot tokens automatically.
   - Filter out broken quotes.
4. **Check BAM delivery.** Profitable bundlers over-index on BAM leaders; we landed 2 of 17 bundles there.
5. **Apply to backrun order-flow programs.** Helius Backrun Rebates is documented, and Astralane backruns are observed. This is the only route to rungs 0-1 (11.5 SOL/h). High value, but admission is uncertain.
6. **Raise the 4.2 SOL cap only after item 2.** 75% of Mriya's gain and 54% of Bgok's come from larger trades, and our engine priced an 8.40 SOL optimum in the DtvmxrTA case.
7. **Tier tips by gross band.** The savings are small.
8. **Fix measurement:**
   - add an executed-tx feed for DLMM and DAMMv2;
   - record CPI tips and inner transfers;
   - fix what rivals.jsonl drops (the record_rival filter and alt_unknown; it missed 20 of 198 Bgok txs);
   - fix outcomes.jsonl, which misses 11-16 failed landings per segment.

**Do not chase:**
- Volume sprays and standing no-op queues: CzYQ -1.20/h, HiP -0.25, 4Qv3 -0.18, FUJK -0.30 without its jackpot.
- More sender services, or bigger tips on direct copies.
- A next-slot re-check before pricing is fixed.
- Flash loans.
- Racing rungs 0-1 from shreds.
- A blanket 30-35% tip.

## 9. Coverage limits and open questions

**Coverage limits:**
- Measured wins are PumpSwap-only. Non-PumpSwap figures come from heavy-tailed samples: DtvmxrTA's 1.31 SOL/h estimate rested on one tx and came out at about 0.43 when resampled.
- rivals.jsonl is a filtered subset of landed txs.
- Unlanded copies, losing bundles and send paths are invisible.
- PoH data is sparse and nominal (6.25 ms per tick), and first-arrival times compress sub-ms gaps.
- Explorer coverage is about 99%, but only 47 of 94 of 4BQ6's bundles in Jito-leader slots were found.
- USDC is valued at about 119.7 USD/SOL.
- Before 23:41, the kit's get_tx silently dropped v1 txs.
- The window is about one hour on one day, and w5h2-p1 covers only 3.5 minutes.

**Open questions:**
- How do Mriya, 8oSD "h" and 9EwQ "-P-" land at idx+1 without a bundle, and only on Jito-client leaders? Harmonic, a private relay, or a deal with validators?
- Who controls FLASHX8D, 6Vo3245e, 4BQ6's collector accounts and GBXk?
- How do Astralane and Helius admit searchers to their backrun flow?
- Does Jito's simulation only see a same-slot trigger after about 9 ms?
- Why do our bundles rarely land on BAM leaders?
- What is the true non-PumpSwap P&L? Answering it needs a full results sweep.
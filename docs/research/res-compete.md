# Competition, latency and send paths

## Competition, latency and send paths (w5h p1-p10, read-only)

Scripts and outputs are in `SNAP/work/compete/` (paths.py, latency.py, takers.py, value.py, verdicts.py, sims.py, p10lag.py, p10win.py, mriya_poh.py, trigsigner.py, plus their `.out` files). For p10 only, I downloaded txarr, poh, exec and rivals into `SNAP/big/w5h-p10/` with the 40 Mbit/s cap. Nothing was written on Cherry or in the repo. The local `zstd` binary is missing, so I decompressed with node's zlib (`work/code/unzst.js`).

### 1. Who takes our gaps, and how far ahead they are

**Where the takers' profit goes.** Source: `rivals_on_gaps` in report.json for p1, p2, p4, p6 and p7. That is 1,824 rival wins and 24.59 SOL (about $2,926) over roughly 1.4 h of segments.

| Taker's ms after the trigger arrived | wins | SOL | share |
|---|---|---|---|
| ≤1 ms | 223 | 9.41 | 38% |
| 1-15 ms | 142 | 8.02 | 33% |
| 15-50 ms | 242 | 2.57 | 10% |
| 50-150 ms | 360 | 1.73 | 7% |
| >150 ms | 802 | 2.58 | 10% |

**The dominant winner is MriyaNN8.**
- It took 188 wins and 17.31 SOL, which is 70% of the total.
- Its median is 0.05 ms after the trigger; 105 of its wins came within ≤1 ms.
- It used a durable nonce on 157 of 188 wins, with a cu_price p50 of 472,727.
- It paid almost no tips (Jito 9, Helius 4).

**Mriya's profile** (botprof-report.txt): 28 tx/min, 49% success, 98% no tip, 88% nonce, cu_price p50/p90 164,576 / 33M, one program (AN225yk…).

**Other sub-millisecond takers** (PoH 0.000 ms where poh.log covers them): 9EwQoN74 (cu_price p50 2.2-16M), 8oSD5a9E (1-12M), 7dGrdJRY, and 4BQ6ATUt, which pays exactly 1,000,000 lamports to rotating unknown accounts.

**p10, the config segment 11 runs.** Source: the engine's own taker, meaning the first transaction after the trigger that wrote both pools (opportunities.jsonl), matched against rivals.jsonl.
- 720 lost attempts; 520 had a taker, spread over 114 signers.
- MriyaNN8 took 45: arrival p25/p50/p75 0.0/0.0/0.0 ms, 40 before our first send, 44 in the same slot. Its PumpSwap-measured gain was 5.86 SOL, 83% of the 7.05 SOL measured.
- CzYQ2kFn (a high-volume sprayer) took 40 at p50 18.2 ms, gaining only 0.049 SOL.
- **By sender service:** no tip 290 (p50 16 ms), Jito 155 (p50 37 ms, tip p50 48k), unknown-tip 23, Astralane 21 (p50 4 ms), Helius 7, Nozomi 2.
- **Value by taker timing:** takers ≤1 ms after the trigger got 5.79 SOL; takers within 111 ms after our send got 0.39 SOL; takers more than 111 ms after our send got 0.18 SOL.
- **Trigger signers for the ≤1 ms takes:** 98 of 117 differ from the taker's signer, so this is not one bot's multi-transaction pattern.

**Inference:** landing in the same PoH position as the trigger cannot be done by reacting to shreds. Our own fastest reaction is 0.3-0.5 ms just to send, and at least ~25 ms to land. These bots are either bundled with the trigger (they have order flow) or have transactions already waiting in the leader's queue.

### 2. Our send paths, p1-p10 (copies, outcomes, bundles)

| path | sent | accepted | landed | wins | landed-fail (fees) | send→seen ms p10/p50/p90 |
|---|---|---|---|---|---|---|
| jito-bundle | 3,858 | 3,858 | 18 | 18 | 0 | 25.7/110.9/226.9 |
| tpu-direct | 101 | 93 | 30 | 1 | 29 (1,638,216) | 34/133/385 |
| shyft | 101 | 101 | 26 | 2 | 24 (383,443) | 39/107/230 |
| haan | 92 | 92 | 16 | 0 | 16 (211,958) | 51/152/866 |
| jito-tx | 95 | 94 | 12 | 0 | 12 (119,304) | 104/501/951 |
| helius | 95 | 95 | 7 | 0 | 7 (49,277) | 23/167/509 |
| nozomi | 46 | 46 | 4 | 0 | 4 (66,064) | 98/218/472 |
| astralane | 46 | 46 | 3 | 0 | 3 (22,083) | 163/177/259 |
| everstake | 46 | 46 | 1 | 0 | 1 (6,901) | 115 |
| bolt | 46 | 46 | 0 | 0 | 0 | none |

**Jito bundles.**
- First verdict: 3,779 of 3,858 were would-fail (98%). By error: 3,139 our profit check (0x4e580002), 603 instruction errors with no code, 21 blockhash-not-found, 10 code 0x1794.
- 63 were accepted but never landed; 12 landed after being accepted.
- There were **zero lost-auction verdicts**.
- Would-fail verdicts arrive 2.5/3.9/100.7 ms after send (p10/p50/p90).
- **By expected profit:** all 18 wins had an expected profit under 120k lamports and a size under 0.2 SOL. Bundles with ≥1M lamports expected went 1,188 sent, 0 won. Bundles of ≥2.1 SOL went 350 sent, 0 won.
- The +100/+250 ms resends in p7 (762 copies) never landed (senders-p4-p7 [B]).

**The TPU arm (p1-p6) lands but loses.**
- Of 957 TPU-arm attempts, 856 were sim-gated and 99 landed (36 in the trigger's slot, 42 one slot later).
- Of those 99, 96 reverted, costing 2,497,246 lamports (0.0025 SOL). That matches the supervisor's failed-fee sum exactly.
- 95 of the 96 had a negative round trip on chain, at a median of −1.53× predicted. The gap was gone or reversed by the time we executed.
- Our wins realized exactly the predicted round trip (median ratio 1.00).
- **Leader kind** is from senders-p4-p7 [A], which needs the leader schedule, so I did not recompute it. tpu-direct landed first under Jito/Europe (5), BAM/Europe (5) and Jito/same-DC (4) leaders, and 100% of TPU attempts landed under every leader kind. Bundles: Jito leaders 738 would-fail / 8 landed; BAM leaders 492 / 1.

**Keep-alive round trips (p50, ms):** astralane 0.24, nozomi 0.27, bolt 0.34, everstake 0.46, jito-tx 0.60, haan 0.65, jito-bundle 0.71, helius 2.69, shyft 5.72 (p90 93). In p1, 8 tpu-direct sends failed with "no leader known for slot".

### 3. Our internal latency

**Feed arrival (p10 txarr, 1.54M transactions).**
- First to deliver: dz-leader 45.0% of the time, dz-retransmit-eu 41.1%, astralane-deshred 12.8%.
- Median lag behind the first copy: haan-deshred +8.4 ms, haan-grpc +15.3 ms.
- raiden, corvus, getblock, constantk-prism and erpc delivered nothing.
- Only 15% of transactions have a poh.log position, because the entries feed is dead.

**State triggers (84% of p10 attempts) fire late.** They fire when the Haan account update arrives, which is **13.8 ms after the trigger's first shred** (p10 8.7, p90 24.0, n=636).

**Engine.**
- rx→decided p50 91-146 µs, p99 1.0-1.9 ms (status.jsonl). p2, p5 and p8 had p99 outliers of 25-106 ms.
- rx→first send: state bundle 0.28-0.34 ms; decoded bundle 0.42 ms in p8-p10, versus 14.2 ms in p1-p7 under confirm_trigger_ms=60; TPU arm 3.1 ms, which includes a ~2.1 ms sim gate.

**End to end.** From trigger shred to our first send is about 14 ms (p50 over 2,196 lost attempts). Our landed bundles were seen 36/94/253 ms (p10/p50/p90) after the trigger.

### 4. Why we lose: lost sent attempts p1-p10 by when the taker arrived

| class | attempts | our expected SOL |
|---|---|---|
| no taker within 2 s | 977 (30%) | 29.0 (52%) |
| taker ≤1 ms after the trigger | 456 (14%) | 10.7 (19%) |
| taker after 1 ms but before our first send | 439 (14%) | 6.1 (11%) |
| taker ≤111 ms after our send | 813 (25%) | 4.9 (9%) |
| taker >111 ms after our send | 433 (13%) | 4.5 (8%) |
| taker, timing unknown | 64 (2%) | 0.4 |

The total is 3,240 lost attempts and 55.6 SOL expected. 58 broken quotes from p1/p2, where expected profit exceeded half the trade size, are excluded from the value column.

In 553 lost bundles, nobody arbitraged the pair until at least 20 ms after Jito's answer, and Jito still said would-fail in 525 (95%). This also holds for 120 decoded-trigger bundles sent 0.4 ms after the shred.

**Our own simulation runs one slot behind.** 4,070 of 4,464 sims in sims.jsonl ran on a bank one slot behind the trigger's slot (sim_slot = slot−1), and 99% failed. So the TPU sim gate mostly measured pre-trigger state.

**Verdict.**
- **Speed (structural) is about 53% of losses:** the ≤1 ms, before-send and ≤111 ms classes together. The biggest share of value (≥71% of rival SOL) goes within 15 ms to bots that are bundled with or already queued behind the trigger. Faster tuning cannot win those.
- **Opportunity quality, or stale state at Jito, is about 43%:** the no-taker and >111 ms classes, which hold 60% of our expected value.
- **Price is not the limit:** zero lost auctions, and TPU copies were included 98% of the time.
- **Path choice is secondary:** bundles fail free but blind, while TPU lands too late and pays ~26k lamports per fail.

### Problems in the operator's scripts (seg.py / senders.py)

1. **Winners are only measurable on PumpSwap pairs.** exec.jsonl is filtered to PumpSwap, so on p10 seg.py found a winner on 313 of 368 PumpSwap-leg attempts but only 95 of 352 without a PumpSwap leg. Its "nobody profited, so it was a fake gap" conclusion is biased.
2. **The 5-slot attribution picks the wrong winner.** It breaks ties within a slot by signature string; ordering by arrival changes the winner in 87 of 408 cases. It agrees with the engine's taker in only 208 of 408. And 45 of 532 "winners" landed before the trigger (negative ms).
3. **"Sendable races we still lost" overstates the case.** It compares the rival's *landing* time with our *send* time, ignoring our 26-227 ms to land.
4. **"No tip" is overcounted.** Tips are read only from top-level System transfers, so tips paid inside a bot's program or in another bundle transaction look like "no tip".
5. **Inventory-based arbitrage is excluded.** Wins are dropped whenever a non-WSOL token balance changes.

The per-path landing attribution in senders.py is sound: each copy's signature is unique (CU-limit tag, exec.rs:341-343).

## CLAIMS
- [high] C1: Across w5h p1-p10 the bot sent 3,858 Jito bundles; 18 landed (all wins); 3,779 (98%) got 'would-fail' as Jito's first verdict (3,139 on our profit check 0x4e580002, 603 'instruction-error', 21 blockhash-not-found, 10 code 0x1794), 0 got 'lost-auction'. Would-fail verdicts come 3.9 ms (p50) after send.
  EVID: copies.jsonl + bundles.jsonl + outcomes.jsonl for w5h-p1..p10 via work/compete/paths.py (paths.out ALL row) and the verdict-latency snippet (would-fail n=3770, p10/p50/p90 2.5/3.9/100.7 ms)
  VERDICT: confirmed — Recomputed with work/verify-compete/c1.py (copies, bundles and outcomes for p1-p10). 3,858 jito-bundle copies were sent. 3,779 had would-fail as the first verdict: 3,139 code 0x4e580002, 603 instruction-error, 21 blockhash-not-found, 10 0x1794, 5 other, 1 0xbbd. 75 were first accepted, 4 got no result, 18 landed, all ok, and there were 0 lost-auction lines. Would-fail p10/p50/p90 was 2.5/3.9/100.7 ms (n=3,779, not 3,770). Caveats: the 3,858 are copies, including the p7 +100/+250 ms resends; only 3,160 attempts sent a bundle. Also, 2 of the 18 landed bundles had would-fail as their FIRST verdict, so a first verdict is not final.
- [high] C2: The TPU arm (p1-p6) had 957 attempts: 856 sim-gated, 99 landed on chain, 3 won, 96 reverted. 95 of the 96 had a negative on-chain round trip (median -1.53x predicted), costing 2,497,246 lamports in failed fees, which equals the supervisor's p1-p6 failed-fee sum.
  EVID: outcomes.jsonl landed rows (round_trip_on_chain vs round_trip_predicted), attempts.jsonl path_arm=tpu; paths.out per-path failed fees 383443+1638216+49277+119304+211958+22083+6901+66064; w5h.supervisor.log
  VERDICT: confirmed — Recomputed with c2.py. TPU arm: 957 attempts, 856 gated, 99 landed, 3 won, 96 failed, 95 with a negative round trip, median ratio -1.531 (n=95). Fees sum to 2,497,246 lamports, which equals the supervisor's p1-p6 sum. Caveat: the 'about 26k per fail' figure is a mean. One tpu-direct landing in p2 alone cost 1,305,030 lamports (52% of the total); the median failed fee is 7,361. Only p5 logged gate sim slots (39 of 40 gated checks were behind the trigger on the first check).
- [high] C3: MriyaNN8 took 70% of the SOL rivals won on our gaps (17.31 of 24.59 SOL, 188 of 1,824 wins) in p1,p2,p4,p6,p7, at a median 0.05 ms after the trigger with nonce on 157/188 wins; in p10 it took 45 of our lost gaps at p50 0.0 ms, 40 before our first send, measured gain 5.86 SOL (83% of measured taker gains).
  EVID: report.json rivals_on_gaps aggregated (snippet in this session); p10: work/compete/p10win.py on big/w5h-p10 exec/rivals/txarr + opportunities.jsonl taker (p10win.out)
  VERDICT: partly — The report.json aggregation is reproduced exactly (c3.py): 1,824 rival wins, 24.589 SOL; MriyaNN8 188 wins, 17.309 SOL (70.4%), ms p50 0.053, nonce on 157; bands 38/33/10/7/11%. For p10 I confirmed 39 measurable Mriya taker txs worth 5.856 SOL (mriya.py on big/exec.jsonl.zst). Caveats that change the reading: (a) seg.py's 'gain' exists only for txs in exec.jsonl, which is PumpSwap only. It counts any profitable tx that moved EITHER pool of ANY priced gap (caps.jsonl), not only gaps we sent, and 1,842 of 3,160 bundle attempts had no PumpSwap leg. (b) A single Mriya tx (4Wjoy..., 3.887 SOL, on an attempt where we expected 0.486 SOL) is 66% of the 5.86 SOL, so '83% of measured taker gains' rests on one outlier. (c) meta.json shows 844 of the 1,014 watched pools were seeded from MriyaNN8's pools, so Mriya's dominance is partly by construction.
- [high] C4: State triggers (84% of p10 attempts) fire 13.8 ms (p50; p10 8.7, p90 24.0, n=636) after the trigger transaction's first shred arrival; engine processing from rx to first send is only 0.28-0.42 ms, so trigger-to-first-send is ~14 ms p50 across lost attempts.
  EVID: work/compete/p10lag.py (attempts st.rx vs txarr first_ns, p10lag.out); latency.py and the rx->first-send snippet by period (state bundle p50 0.28-0.34 ms, decoded p8-p10 0.42 ms); takers.out 'our first send' p50 14.1 ms
  VERDICT: confirmed — Recomputed independently with c4.py, using opportunities.jsonl trigger arrivals rather than txarr. In p10, state rx minus the trigger's first shred was p10/p25/p50/p75/p90 8.72/10.88/13.8/18.0/24.03 ms (n=636), and 637 of 762 attempts (84%) were state triggers. rx to first send p50 was 0.28 ms for state bundles and 0.39 ms for decoded. Shred to send for state attempts in p10 was p50 14.0 ms; across p1-p10 it was 14.7 ms.
- [high] C5: Of 3,240 lost sent attempts (p1-p10): 30% had no taker of the pair within 2 s (52% of our expected value), 14% were taken <=1 ms after the trigger, 14% after 1 ms but before our first send, 25% within 111 ms after our send, 13% more than 111 ms after our send, 2% unknown.
  EVID: opportunities.jsonl taker.window_ms vs copies.jsonl first t_sent minus min(opportunity arrivals); work/compete/value.py (value.out) and takers.py (takers.out)
  VERDICT: confirmed — Reproduced with c5.py: 977/456/439/813/433/64 with 29.03/10.71/6.07/4.94/4.49/0.39 SOL. The percentages use 3,240, which includes the 58 excluded broken quotes; over the 3,182 classified attempts the no-taker share is 30.7%. Interpretation caveats: 99% of the 55.64 SOL 'expected' sits in the 1,176 attempts with expected >= 1M lamports, and attempts below 1M total only 0.40 SOL. 302 of those large attempts (28.94 SOL, about 0.096 SOL each) had no taker for 2 s on pools Mriya watches, which suggests many are phantom quotes (inference). In 293 of the 813 'taker <=111 ms after our send' cases, Jito's would-fail arrived BEFORE the taker, so those are not speed losses.
- [medium] C6: In 553 lost bundles the eventual taker arrived >=20 ms after Jito had already answered, yet Jito said would-fail in 525 (95%). This includes 74 of 75 decoded-trigger bundles sent ~0.4 ms after the shred, so these losses were not races against a rival.
  EVID: bundles.jsonl first verdict t_ns vs opportunities taker.window_ms (snippet in this session); verdicts.py cross-tab (p8-p10 decoded: 215 would-fail / 217)
  VERDICT: partly — Per-attempt counts reproduced (c5b.py): 553 bundles had the taker >= 20 ms after Jito's first verdict, and 525 of them were would-fail (95%). For decoded triggers, 74 were would-fail out of 75. The report body says '120 decoded', which contradicts this. The mechanism claim is overstated. The engine's taker must write BOTH pools (engine.rs:963-969). In p7-p10 (c6.py on moves.log), 136 of the 400 such would-fail cases had another, non-trigger, non-ours tx move one of the pair's pools between the trigger's update and Jito's verdict. So 'not races against a rival' holds for roughly two thirds, not all.
- [medium] C7: Our own RPC simulations ran on a bank one slot behind the trigger's slot in 4,070 of 4,464 sims (99% of which failed the profit check), so the TPU sim gate mostly tested pre-trigger state.
  EVID: sims.jsonl sim_slot - slot for w5h-p1..p10 via work/compete/sims.py (sims.out); rpc.rs:240 simulates at commitment 'processed'
  VERDICT: partly — The sims.jsonl counts hold (c7.py): state sim_slot = slot-1 in 4,070 rows and decoded in 319. Where the trigger pool is the buy leg, the first leg deviates from prediction (only 7-17% exact), consistent with a pre-trigger bank. The analyst's 'ok 39' includes 24 rows with no simulation result; the real ok count is 15. But sims.jsonl is the STEP-2 sim (exec.rs:371-410), not the TPU gate. The gate's sims are logged only in p5's settle_error, where 39 of 40 gated checks were behind on the first check and 28 still behind on the last. Since p6 the code already sends on our quote when the sim is behind the trigger (exec.rs:646-650; 56 'sim stale' lines in w5h-p6.out). Sims at or after the trigger slot also failed the profit check 31 of 31, so the bank lag alone does not explain the failures.
- [medium] C8: All 18 bundle wins (and all 21 wins) had expected profit under 120k lamports and size under 0.2 SOL; 1,188 bundles with expected >=1M lamports and 350 bundles >=2.1 SOL produced 0 wins.
  EVID: verdicts.py cross-tab by exp and size (verdicts.out); outcomes.jsonl landed rows
  VERDICT: confirmed — wins.py: the largest win had expected 117,687 lamports and the largest size was 0.115 SOL. verdicts.out by attempt: >=1M expected 713+475 = 1,188 with 0 wins; >=2.1 SOL 350 with 0 wins. Missing context: the 21 wins are economically negligible. Their on-chain round trips sum to 632,807 lamports (about $0.075); tips were 337,744 and fees 113,670, leaving about 181k lamports (about $0.02). profit_lamports sums to -16,201,607 because 10 of the 21 wins created a token account.
- [medium] C9: seg.py's winner attribution is unreliable. On p10 it found a winner for 313 of 368 PumpSwap-leg attempts but only 95 of 352 non-PumpSwap ones (exec.jsonl covers PumpSwap only). Re-ordering same-slot candidates by arrival instead of signature changes 87 of 408 winners. It agrees with the engine's taker in only 208 of 408. 45 of 532 'denied' winners in p4/p6/p7 arrived before the trigger.
  EVID: seg.py lines 128-135 (min((slot,sig))), record.rs:6 (exec.jsonl = Haan PumpSwap feed); p10win.out header; report.json denied ms<0 counts (29+4+12)
  VERDICT: confirmed — Independent recompute (c9.py, moves + exec + txarr for p10): 720 lost, 408 with a seg.py winner (313 of 368 PumpSwap-leg, 95 of 352 non-PumpSwap), 87 that change when ordered by arrival, 208 equal to the engine taker. report.json denied in p4/p6/p7: 289+71+172 = 532, of which 29+4+12 = 45 have ms<0. seg.py's min((slot, sig)) is confirmed at seg.py lines 128-135. Caveat: disagreement with the engine's taker is not proof by itself, because the two definitions differ (either pool and profitable, versus both pools) and the engine taker has its own bias.
- [low] C10: In p10 only 5 of 10 configured feeds delivered anything: dz-leader was first 45.0% of the time, dz-retransmit-eu 41.1%, astralane-deshred 12.8%. haan-deshred lagged 8.4 ms (p50) and haan-grpc 15.3 ms. raiden, corvus, getblock, constantk-prism and erpc delivered nothing, and only 15% of txs got a PoH position.
  EVID: big/w5h-p10/txarr.log.zst + meta.json feeds via p10lag.py (p10lag.out); poh.log.zst 233,482 lines vs txarr 1,542,100
  VERDICT: partly — Numbers reproduced (c10.py on big/w5h-p10/txarr.log.zst): 1,542,100 lines; first feed dz-leader 45.0%, dz-retransmit-eu 41.1%, astralane-deshred 12.8%, haan-deshred 1.1%. poh.log has 233,482 lines (15.1%). run.log fwd/txs shows raiden, corvus, getblock, constantk-prism and erpc at 0/0: constantk-prism fails with 'Unauthenticated: Missing or Invalid API Key', and erpc gets a TCP connect timeout to shreds-fra6-1. The analyst's mechanism ('only 15% because the entries feed is dead') is incomplete. In p10, poh.log is written by the shred assembler (shred.rs:246-265). It does not use FEC recovery, and a missing data shred or a failed set stops the PoH clock for the rest of the slot, so coverage is also a code limitation.

## MISSED (verifier)
- The analyst's recommendation 4 is already in the code and live since p6, and the data shows it hurts. exec.rs:646-650 sends on our own quote when the gate's sim slot is below the trigger slot. In p6, 56 'sim stale' lines led to 57 TPU landings with 56 failed (755,198 lamports). The TPU arm returned in p12 and p14 with the same rule: 84 and 85 'sim stale' sends, 74 of 74 and 63 of 63 landed failures, 0 TPU wins, and 1,615,084 lamports in fees (tpuseg.py, p1214.py). In practice the gate's stale 'fail' verdicts were right.
- The wins are worth almost nothing. All 21 wins (p1-p10) total an on-chain round trip of 632,807 lamports (about $0.075). Net of tips (337,744) and fees (113,670) that is about 181k lamports, and including the rent for 10 new token accounts it is -16.2M lamports. Meanwhile 99% of the 'lost expected value' (55.64 SOL) comes from attempts with expected >= 1M lamports, and 302 of those (28.9 SOL) had no taker for 2 s, which points to phantom or mispriced quotes rather than lost races (inference).
- The fast path does not win more. In p8-p10, decoded triggers sent about 0.4 ms after the shred won 1 of 217 bundles (216 first-verdict would-fail), while state triggers sent about 14 ms later won 8 of 1,570 (dec.py). Also, in 293 of the 813 'taker <=111 ms after our send' losses, Jito's would-fail arrived before the taker existed. The 'speed is about 53% of losses' verdict is therefore overstated, and the binding constraint is at Jito's simulation or in our quote, not the 14 ms state lag.
- The watched universe is MriyaNN8's own pools. meta.json for p10 reads '1014 pools ... MriyaNN8's 844, ours 301'. Mriya taking 70% is partly a consequence of seeding from its pools. The analyst never states this, though it is the most direct lever: pool selection.
- The engine's 'taker' must write both pools of our pair (engine.rs:963-969). A rival or user tx that moves one of our pools via a third pool counts as 'no taker'. In p7-p10, 223 of 501 no-taker would-fail bundles and 136 of 400 late-taker ones had another non-trigger, non-ours tx move a pair pool before Jito's verdict (c6.py on moves.log). 'No taker' therefore does not mean 'the gap persisted'.
- 'Zero lost auctions, so price is not the limit' does not follow. 98% of bundles failed Jito's simulation, which runs before any auction, so they never bid. 63 bundles were accepted and never landed, a likely place for unreported auction losses. 2 of the 18 landed bundles had would-fail as their first verdict, so the first verdict is not final. With tip_share 0.7 and gross_floor, a bundle also fails the on-chain check whenever the realized round trip is below about 70% of the predicted gross.
## REC ISSUES (verifier)
- Rec 1 (make the small-gap niche the target): economically unsupported. The whole niche delivered 632,807 lamports gross round trip across 21 wins in about 5 h, about 181k net of tip and fee, and negative after token-account rent. The 0 wins on large gaps are not shown to be sub-ms takers: 302 of the 1,176 lost >= 1M attempts had no taker at all. Bundles that fail cost nothing, so stopping large-gap bundles saves no money. It only removes the data needed to find out whether large quotes are mispriced.
- Rec 2 (gap-persistence probe via best_cycle on our own store): this cannot tell 'stale Jito state' apart from 'our quote is wrong', because the probe reuses the same pricing that produced the gap. A decisive test is an RPC simulation of the same tx with minContextSlot >= trigger slot, or a later-slot sim. The existing data already leans toward quote error or a gone gap: sims at or after the trigger slot failed the profit check 31 of 31.
- Rec 4 (treat a stale sim as 'unknown' rather than fail): wrong and risky. It has been the behaviour since p6 (exec.rs:640-650). Every segment that ran it with TPU sends lost: p6 56/57 landed failures, p12 74/74, p14 63/63, 0 TPU wins in p12/p14, and 2.37M lamports of failed fees across the three. This recommendation would spend the live budget.
- Rec 5 (raise decoder coverage to avoid the 13.8 ms state lag): unsupported. Decoded triggers sent at about 0.4 ms won 1 of 217 bundles in p8-p10, versus 8 of 1,570 for state triggers. 74 of 75 decoded bundles were rejected even though no both-pool taker arrived for 20 ms or more, so the lag is not the binding loss mechanism in the bot's own data.
- Rec 7 (if TPU racing returns, keep tpu-direct and shyft): refuted by later segments. TPU racing returned in p12 and p14 (the 'w5h hybrid test'), and tpu-direct plus shyft produced 99 landed failures and 0 wins (p12: 40 + 24; p14: 26 + 9). Per-path landing counts only say which simultaneous copy landed first; paths got different copy counts (101 vs 46), so they do not rank path quality. Restarting paid TPU racing on the live wallet is the costliest option in the data.
- Rec 3 (use the engine's taker as primary winner): acceptable as a script change, but not as ground truth. It requires a tx that writes both pools and misses one-pool closes (136 of 400 p7-p10 cases). It also allows window_ms <= 0: 30 lost attempts have a 'taker' that arrived before the trigger. Rec 6 (restore dead feeds): the causes are concrete and different. constantk-prism has an invalid API key, erpc has a TCP connect timeout, and the 15% PoH coverage also comes from the shred PoH clock stopping at any missing data shred (no FEC recovery, shred.rs), which a feed restore alone will not fix.
## RECS
- [now] Stop pricing and sending the large gaps (expected >=1M lamports or size >=2.1 SOL) on the pools where MriyaNN8, 9EwQoN74 and 8oSD5a9E take within 1 ms, or treat them as a separate strategy. Make the small-gap niche (<0.2 SOL, <120k lamports expected), where all 21 wins came from, the explicit target. — 1,188 bundles with >=1M expected and 350 bundles >=2.1 SOL won 0 times; takers within 1 ms (same PoH position as the trigger) hold most of the value and cannot be beaten by reacting to shreds.
- [now] Add a gap-persistence probe after every Jito would-fail: re-run best_cycle on the pair from our own store at +5/+20/+50 ms and log whether the gap still exists. — In 95% of the 553 bundles where nobody arbitraged the pair for >=20 ms after Jito answered, Jito still rejected. We cannot yet tell stale Jito simulation state from our own quote or stale-leg errors, and that split decides whether to fix pricing or change path.
- [now] Fix the operator's attribution scripts. Use the engine's taker (opportunities.jsonl) as the primary winner. Order same-slot candidates by PoH or arrival time, not signature. Start the window at the trigger. Label non-PumpSwap pairs 'unmeasurable' instead of 'nobody profited'. Compare rival landing time with our send time plus our measured landing latency, not with our send time alone. — seg.py currently misses most non-PumpSwap winners, swaps 21% of winners on tie-breaks, counts winners that came before the trigger (45 of 532), and overstates sendable races.
- [next] Make the TPU sim gate refuse to judge when the simulation bank is behind the trigger slot (sim_slot < trigger slot): treat that as 'unknown' and record it, rather than as a fail. — 99% of sims ran one slot behind the trigger, so 856 of 957 TPU attempts were gated against pre-trigger state; the gate's results are not evidence about the gap.
- [next] Raise decoder coverage (aggregator- and bot-routed swaps) so more triggers are decoded from shreds instead of waiting for the Haan account update. — State triggers cost about 13.8 ms (p50) against 0.4 ms on the decoded path; 439 lost attempts (6.1 SOL expected) were taken in exactly that window.
- [next] Restore the dead feeds (raiden, corvus, getblock, constantk-prism, erpc), especially an entries feed for PoH timing. — Only 15% of p10 transactions have PoH positions, so most winner timing still rests on arrival differences.
- [later] If TPU racing returns, keep tpu-direct and shyft (30 and 26 of 99 TPU-race landings, send->seen p50 133/107 ms) and drop bolt (0/46 landed), everstake (1/46) and jito-tx (p50 501 ms). — Inclusion is not the problem, but each landed miss costs about 26k lamports; the slow paths add rate-limit use without landing.
## OPEN Q
- Does Jito's block engine simulate a single-transaction bundle against a state that already includes a same-slot trigger? Decoded-trigger bundles sent 0.4 ms after the shred still failed 99% (215/217 in p8-p10), yet rivals' Jito-tipped takers landed at p50 37 ms.
- How do MriyaNN8, 9EwQoN74 and 8oSD5a9E land at PoH 0.000 ms after the trigger: bundled with it (order flow, possibly paying tips inside their program or in a separate bundle tx that we cannot see), or transactions already waiting in the leader's queue? Only 6 PoH samples exist, because the erpc entries feed is dead.
- Are the 977 lost attempts with no taker (52% of expected value) quote errors, a stale other leg, or gaps closed by ordinary single-pool trades? The engine's predictions.jsonl checks could separate these.
- TPU-direct and bundle outcomes by leader kind (Jito/BAM, distance) exist only for p4-p7 (senders-p4-p7.txt) because they need the leader schedule over RPC; this was not recomputed for p8-p10.
- Why did p9 send only 979 bundles for 1,182 attempts, and why was the p7 +100/+250 ms bundle resend active when no arb-w-p7.toml key enables it? (The code default is empty; possibly the binary of that time differed.)
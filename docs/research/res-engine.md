# Opportunity quality and the funnel: are the gaps real?

## Opportunity quality and the funnel (w5h p1-p10)

**Scope.** Everything comes from the local snapshot `SNAP/root/runs/w5h-p*/`, read-only, and the engine code (`src/engine.rs`, `src/exec.rs`, `src/rpc.rs`). Scripts are in `SNAP/work/engine/` (`funnel2.py`, `caps.py`, `caps2.py`, `checks.py`). I made one light read-only SSH call: tail of the p11 status and the supervisor log. It shows the campaign has moved on: p11 ran only 81 s, p12-p14 ended early, and p15 has been running since 21:07:46 UTC with 35,887,670 lamports of budget left. The snapshot does not contain p11-p15.

### 1. Funnel per segment
Counters come from the last line of `status.jsonl`; outcomes come from joining attempts and outcomes.

| seg | s | triggers | dropped at decode (will-fail/exact-out/unquotable) | quoted | cycle>0 | decoded opps (released/timeout) | state opps | to exec | sent | biggest skip | bundle: would-fail/accepted/no verdict/won | TPU: gated/landed-fail/won | wins |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|p1|1192|6770|2350/29/168 (38%)|4223|751|707 (150/557)|1444|1594|917|pair-lock 645|454/4/0/0|445/13/0|0|
|p2|316|1430|552/20/59 (44%)|799|67|47 (29/18)|307|336|187|pair 137|91/2/0/0|90/3/0|0|
|p3|139|596|188/5/33 (38%)|370|35|26 (14/12)|362|376|149|pair 196|72/2/0/0|69/4/2|2|
|p4|1192|4952|912/35/295 (25%)|3710|182|141 (77/64)|1379|1456|444|implausible 663|220/2/0/0|212/10/0|0|
|p5|340|3649|472/12/66 (15%)|3099|71|45 (13/32)|592|605|143|pair 325|90/2/1/0|40/10/0|0|
|p6|544|5712|557/27/106 (12%)|5022|136|120 (31/89)|269|300|131|pair 162|73/0/0/1|0/56/1|2|
|p7|1192|6303|993/636/361 (32%)|4313|161|105 (54/51)|888|942|381|pair 535|256/3/114/8|–|8|
|p8|103|10674|6207/524/1744 (79%)|2199|92|75 (no confirm)|143|218|115|pair 103|57/0/58/0|–|0|
|p9|440|27926|18380/1503/2440 (80%)|5603|361|290|2861|3151|1182|pair 1797|957/14/209/2|–|2|
|p10|1192|24413|1892/4953/7355 (58%)|10213|541|410|3063|3473|762|cooling 1788|699/19/37/7|–|7|

Across p1-p10: 4,411 sent, 117 landed, 21 wins. The stage arithmetic closes exactly. For example, in p10: 410 + 3,063 decisions = 762 sent + 921 + 1,788 + 2 skipped.

**Where it leaks, stage by stage:**
- **Trigger to quoted.** The will-fail filter dominates p1-p9, and unquotable/exact-out dominate p10. This is junk from a few pools: DHbktet3wt alone produced 19,802 of p9's 26,074 trigger signatures (76%, only 1,740 quoted). HUQ2YZbVjh produced 5,909 trigger signatures in p10 (32%), and none were quoted.
- **Quoted to cycle.** Only 2-18% of quoted triggers open any round trip. That is normal.
- **Decoded opportunity to confirmed.** 823 of 1,191 decoded opportunities in p1-p7 (69%) timed out. They are the phantom triggers: 820 never appeared in a pool update.
- **Decision to send.** Pair lock causes 27-57% of skips, the implausible filter 46% in p4, and token cooling 51% in p10. These skips are mostly duplicate triggers on one pair, not lost gaps.
- **Send to land (the main leak).** Bundles: 2,969 of 3,056 bundle attempts that got a verdict were rejected as "would-fail" (97%). Of these, 80% carry code 0x4e580002, the profit check; most of the rest are uncoded "instruction-error". TPU arm, p1-p5: 856 were sim-gated. In p6 the stale-sim bypass sent 55 trades on our own quote, and 56 of the 57 TPU landings failed.
- **Land to win.** TPU landings won 3 of 99. Bundle landings won 18 of 18 (a failing bundle never lands).
- **Broken quotes.** p1 and p2 sent 140 attempts with an expected profit of about 9.9e12 lamports, all on token 9cRCn9rG, Dlmm>PumpSwap. The filter has caught them since p3.

### 2. Prediction accuracy
- **Trigger effect** (`predictions.jsonl`):
  - PumpSwap: 15,885 of 16,780 checks within 0.01 bp (94.7%).
  - RayAmmV4: 92.5%.
  - DLMM active bin correct: 2,003 of 2,368 (84.6%).
  - DammV2 sqrt price exact: 662 of 758 (87.3%).
- **The simulation is one slot stale.** Of 4,464 sims:
  - 4,414 (98.9%) failed the profit check, 15 were ok, 10 were missing DLMM bin arrays, 24 were RPC errors.
  - 4,409 of the 4,440 completed sims (99.3%) ran on a slot before the trigger's slot, 4,389 of them exactly one slot behind. `simulate_full` uses processed commitment (rpc.rs:240).
  - The shortfall sits entirely on the leg through the trigger pool, median -100 to -156 bps. The other leg matches the prediction at 0 bps median.
  - So `sims.jsonl` and the TPU gate measure how far the RPC lags, not whether the gap is real. Inference: the sim runs on the pool before the trigger. The 31 sims that ran at or after the trigger's slot also all failed.
- **Realized:**
  - The 21 wins predicted 706,900 lamports gross; on chain they made 632,807 (89.5%). After fees and tips that is 181,393 lamports. Wallet profit including token-account rent was -16.2M.
  - Of the 96 landed failures, 95 failed the profit check, with on-chain round trips well below zero. In p6 the TPU landings came 0-2 slots after the trigger, and the gap was already gone.

### 3. Are the gaps real?
| class (opportunities.jsonl) | n | median net (lamports) | predicted net (SOL) |
|---|---|---|---|
|state (trigger confirmed)|11,308|286,422|171.5|
|decoded, trigger landed|791|1,072,853|27.9|
|decoded, trigger never landed (phantom)|1,175 (60% of decoded)|58,594,459|213.2|

- **The biggest gaps are phantoms.** These triggers made it into a block but never moved the pool; my inference is that they failed on chain. With `confirm_trigger_ms = 0` (p8-p10), 44 attempts went out on phantom triggers; in p10 that was 34 of 125 decoded attempts. As bundles they cost no fees, but they use Jito rate, nonces and pair locks.
- **Who took the gaps we lost** (seg.py `report.json`, p4/p6/p7):
  - A profitable rival winner was found for 65%, 55% and 46% of lost attempts.
  - Median expected profit where a winner exists: 1.51M / 1.80M / 1.26M lamports.
  - Where nobody won: 75.6k / 690k / 35.2k lamports.
  - p1 and p2 reports have no `denied` key.
- **Outcome by expected profit, all segments:**

| expected profit | attempts | wins | taker present | no taker |
|---|---|---|---|---|
| <20k | 478 | 8 | 42% | 54% |
| 20k-100k | 941 | 11 | 61% | 36% |
| 100k-1M | 1219 | 2 | 75% | 23% |
| 1M-10M | 1033 | 0 | 74% | 24% |
| >10M | 600 | 0 | 64% | 32% |

- **Gap size relative to trade size.** Gaps returning 0.1-2% are taken 79-80% of the time: real and contested, but worth only 56 SOL of predicted net. Gaps returning 2-50% hold 356 of the 412 SOL, with taker shares of 56% and 37% and heavy phantom content.
- **State vs decoded triggers.** State triggers account for 80-95% of decisions and 20 of the 21 wins. State decisions come about 14-15 ms after the trigger's first shred (p50 in every segment). In p9 and p10 the taker's transaction was already visible before we decided in 38% and 36% of state opportunities.

### 4. Venues, seed lists, sizes, caps
- **Venue pairs:**
  - Dlmm>Dlmm: 3,420 opportunities, 26% taken, median net 48.6k lamports, 13 of the 21 wins.
  - DammV2>DammV2: 2,346 opportunities, 99% taken, 0 wins in 473 attempts (token 2AVjqm was 782 of p9's 1,182 attempts).
  - PumpSwap to/from Dlmm: medians 1.4-2.1M lamports, 69-76% taken, 4 wins in 1,689 attempts.
- **Seed lists.**
  - `seed-pools-w.csv` (979 rows) became 876 pools in p1-p2, then 755 after the transfer-fee filter.
  - `w3` (1,325 rows: +167 bots, +30 bots-token, +163 fresh) booted 1,014 pools in 365 pairs.
  - With w3 the trigger rate went from 4.2-11/s to 20.5-104/s, but 58-80% of triggers were dropped at decode.
- **Sizes.**
  - Attempt size medians are 0.07-0.45 SOL; 274 of 4,411 attempts (6.2%) hit the 4.2 SOL cap.
  - `best_cycle` refines sizes up to twice the top rung (engine.rs:803), so opportunity nets can be priced at 8.4 SOL.
- **caps.jsonl** (deduped episodes over 1.85 h): summed net at the 0.165 / 2.1 / 4.2 / 8.4 / 21 / 42 / 84 SOL caps is 10.0 / 63.5 / 98.7 / 146.3 / 236.6 / 332.4 / 454.7 SOL.
  - Phantom-trigger episodes with no taker account for 39.8 of the 4.2-SOL total and 287.1 of the 84-SOL total.
  - The credible class (trigger confirmed and a taker present) grows from 40.3 SOL at 4.2 to 52.4 at 8.4 and 71.5 at 84.
  - Rivals do realize big-size profits on our pools. MriyaNN8 made +6.59 SOL on one 96 SOL trade in p7, and in p1 rivals took 6.41 SOL in total, of which 2.05 SOL came from trades of 4.2 SOL or less.
  - We capture nothing at or above 1M lamports expected. Until we are faster, more capital does not help.

### 5. Feed health (identical in every segment)
- **Dead feeds.** raiden, corvus and getblock delivered 0/0 transactions. constantk-prism is rejected as "Unauthenticated" (124 reconnect messages per 20 minutes). erpc gets TCP connect timeouts (62 per 20 minutes).
- **Consequences.** No PoH timing: 0 opportunities carry it. The entries archive (`archive_feed = "erpc"`) is presumably empty.
- **Who arrives first, and how late the rest are:**
  - dz-leader: first on 45-60% of triggers, but sees only 46-63% of them.
  - dz-retransmit-eu: first on 40-55%, sees 97-99.9%.
  - astralane-deshred: 2.4-3.9 ms behind (p50).
  - haan-deshred: 8.7-10.7 ms behind.
  - haan-grpc: 15-18 ms behind (PumpSwap only).
- **RPC.** Haan wins 88-97% of calls; Shyft is often slow or rate limited. Engine queue p50 is 0; backlogs appear only at startup and at shutdown.

## CLAIMS
- [high] C1: The free simulation runs on stale state: of the 4,440 completed sims, 4,409 (99.3%) ran on a slot before the trigger's slot, 4,389 of them exactly one slot behind. 4,414 of all 4,464 sims (98.9%) fail the profit check. The shortfall sits on the trigger pool's leg (median -100 to -156 bps), while the other leg matches the prediction at 0 bps median. So the sim cannot tell whether a gap is real.
  EVID: w5h-p1..p10/sims.jsonl (slot vs sim_slot, delivered vs predicted_mid/back) joined with opportunities.jsonl trigger_pool; src/rpc.rs:240 (processed commitment); work/engine/checks.py
  VERDICT: partly — Counts reproduce exactly (my script work/verify-engine/v1_sims.py on w5h-p1..p10/sims.jsonl): 4,464 sims, 4,414 profit-check fails, 24 sim_error; trigger slot minus sim_slot is 1 for 4,389 sims, and 4,409 of the 4,440 completed sims ran before the trigger's slot. The mechanism holds: the sim's context slot is N-1 while the trigger landed in N (exec.rs:364/403, rpc.rs:240 processed). The median sim round trip is -79 bps against +37 bps predicted, which is what a pre-trigger state looks like. Two problems. (a) The leg range is wrong. The trigger leg's median shortfall is -100 to -158 bps only in p1, p6, p8, p9 and p10; in p2-p5 and p7 it is just -6 to -8 bps (v1b.py). Pooled, it is -56 bps when the trigger pool is the buy pool and -107 bps when it is the sell pool. The other leg's median is 0, but only 51-82% of those legs are within 1 bp. (b) The conclusion 'the sim cannot tell whether a gap is real' is contradicted by data the analyst missed. In p6, p12 and p14 the bot ignored stale sims and sent 220 TPU trades on its own quote. 191 landed, 190 failed and 1 won, costing 2,321,390 lamports in fees (w5h-p{6,12,14}.out 'sim stale' lines joined to outcomes.jsonl). The stale sim's 'no' matched what actually happened on chain.
- [high] C2: 60% of decoded opportunities are phantoms: 1,175 of 1,966 never showed their trigger in a pool update within 2 s. Their median predicted net is 58.6M lamports (vs 1.07M for landed decoded and 0.29M for state), and they hold 213 of the 412 SOL of total predicted net. In p1-p7 the 823 confirm timeouts match the 820 phantoms.
  EVID: opportunities.jsonl trigger_landed_slot / trigger_feed / net_lamports, p1-p10; status.jsonl confirm_released/confirm_timeout; work/engine/checks.py
  VERDICT: confirmed — Reproduced from opportunities.jsonl p1-p10: 791 decoded opportunities whose trigger landed and 1,175 phantoms (59.8%). Phantom means no pool update within outcome_watch_ms=2000 (engine.rs:649, 958-990). After removing broken quotes, the median net is 58,566,918 lamports for phantoms, 1,072,853 for landed decoded and 286,422 for state. Predicted net sums are 213.2, 27.9 and 171.5 SOL. Per-segment phantoms in p1-p7 sum to 820 and confirm_timeout to 823. Caveats: the phantom rate depends on the regime, 69% in p1-p7 with confirmation on versus 28%, 39% and 54% in p8-p10. I count 48 phantom attempts in p8-p10 (1+13+34), not the report's 44; the 34 in p10 is right.
- [high] C3: We win only tiny gaps: 21 wins from 4,411 sends, and 19 of them had expected profit under 100k lamports. None of the 1,633 attempts expecting 1M lamports or more won, and 70% of those had a taker who touched both pools after the trigger.
  EVID: attempts.jsonl expected_profit x outcomes.jsonl landed/ok x opportunities.jsonl taker, p1-p10; work/engine/checks.py section 3
  VERDICT: confirmed — Reproduced: 4,411 sent, 21 wins. Wins by expected profit: 8 under 20k, 11 at 20-100k, 2 at 100k-1M, 0 among the 1,633 attempts at 1M or more (1,033 + 600). 1,152 of those 1,633 (70.5%) were lost with a taker present. Stronger still: every win had expected profit of 12,025-117,687 lamports, a trade size of at most 115,271,118 lamports (0.115 SOL) and a return of at most 1.2%.
- [medium] C4: When we land first, our quote holds: the 21 wins predicted 706,900 lamports gross and made 632,807 on chain (89.5%). Net of fees and tips that is 181,393 lamports, with all landed failures costing 2,497,246 lamports in fees. 95 of the 96 landed failures hit the profit check (0x4e580002).
  EVID: outcomes.jsonl round_trip_predicted / round_trip_on_chain / fee_lamports / tip_paid_lamports / code, p1-p10
  VERDICT: confirmed — Exact match from outcomes.jsonl: the 21 wins predicted 706,900 lamports and made 632,807 on chain (89.5%). Fees were 113,670 and tips 337,744, leaving 181,393 net (about $0.02). The 96 landed failures cost 2,497,246 lamports in fees; 95 were 0x4e580002 and 1 was 0x1794. Every landed failure was on the TPU arm. All 95 with a recorded round trip were negative, median -89 bps of trade size.
- [medium] C5: The engine predicts the trigger's effect on its pool accurately: PumpSwap reserves within 0.01 bp in 15,885 of 16,780 checks (94.7%), DLMM active bin correct in 2,003 of 2,368 (84.6%), DammV2 sqrt price exact in 662 of 758 (87.3%).
  EVID: predictions.jsonl err0_bps/err1_bps and match fields, p1-p10
  VERDICT: confirmed — predictions.jsonl p1-p10: PumpSwap 15,885 of 16,780 checks within 0.01 bp on both reserves; DLMM 2,003 of 2,368 matched the active bin; DammV2 662 of 758 matched; RayAmmV4 520 of 562. Caveats. Checks exist only for triggers that landed, and there is one check slot per pool, which a later trigger overwrites (engine.rs:621). DLMM 'active bin correct' is a coarse test. The accuracy also barely affects results: 20 of the 21 wins and 80-95% of decisions came from state triggers, which are priced on live state, not on the prediction.
- [high] C6: The send stage is the dominant leak: 2,969 of the 3,056 bundle attempts that got a Jito verdict were rejected as would-fail (97%), mostly with 0x4e580002. In p6, TPU trades sent past a stale sim gate landed and failed 56 times out of 57.
  EVID: outcomes.jsonl jito.outcome by path_arm; bundles.jsonl code; w5h-p6.out 'gate: ... sim stale ... sent on our quote' (55 lines)
  VERDICT: partly — The ratio holds when recomputed per attempt from the first bundle's verdict in bundles.jsonl: 2,967 would-fail out of 3,033 with a verdict (97.8%), of which 2,396 (80.8%) were 0x4e580002. The jito field in outcomes.jsonl, however, holds the LAST copy's verdict, because exec.rs:692-695 overwrites s.jito in a loop over the copies. In p7 (resends at +100 and +250 ms) and p8 (size variants) it therefore describes resends, and 7 of the 18 bundle wins are recorded as 'would-fail' (example: p7 attempt 62, where the first bundle landed and the last resend got 'Blockhash not found'). p6 is right in substance: 55 stale-bypass TPU trades gave 54 landed failures and 1 win, plus 2 trades that passed the sim and still failed, so 56 of 57 TPU landings failed. Calling this a 'send stage' leak is questionable. Would-fail is about 98% even for bundles sent less than 10 ms after the trigger's first shred and before any taker was seen (318 cases). That points to competition and timing, or to Jito's simulation also running before the trigger lands (the operator's note at exec.rs:555); I have not proven which. It is not a delivery failure.
- [medium] C7: Half the configured feeds are dead in every segment: 5 of 10 (raiden, corvus and getblock deliver 0/0; constantk-prism is Unauthenticated; erpc has TCP connect timeouts). As a result, 0 opportunities carry PoH timing. The two DZ feeds arrive first on about 99.5% of triggers.
  EVID: w5h-pN.out final 'fwd/txs' lines and reconnect messages; arrivals.jsonl first_feed; opportunities.jsonl poh.trigger all null
  VERDICT: partly — The feed facts are confirmed for every segment from the final 'fwd/txs' lines in w5h-pN.out. raiden, corvus, getblock, constantk-prism and erpc are all 0/0. Over a full 20 minutes there are 124 'Unauthenticated' lines and 62 erpc 'deadline has elapsed' lines. DZ feeds arrive first on 99.42-100% of arrivals.jsonl rows, and poh.trigger is null in every opportunity. The causal 'as a result' is only partly right. Shred feeds never attach PoH to arrivals by design (feeds/mod.rs:118 sets poh: None). Instead they write PoH positions to poh.log (shred.rs:247-266). The cached p10 poh.log has 188,301 entries and covers 266 of the 3,473 opportunity triggers (7.7%), 84 of them together with their taker. So some leader-clock timing does exist offline.
- [high] C8: caps.jsonl's money left on the table is mostly phantom: of 98.7 SOL at the 4.2 SOL cap and 454.7 SOL at the 84 SOL cap (1.85 h), phantom-trigger no-taker episodes account for 39.8 and 287.1 SOL. The credible class (state trigger, taker present) is 40.3 SOL at 4.2, 52.4 at 8.4 and 71.5 at 84.
  EVID: caps.jsonl deduped by pair within 5 slots, broken quotes removed, joined to opportunities.jsonl; work/engine/caps.py, caps2.py
  VERDICT: partly — Totals reproduce: 10.0, 63.5, 98.7, 146.3, 236.6, 332.4 and 454.7 SOL at the seven caps over 1.848 h. The class breakdown in caps2.py is deduplicated within each class separately, so the classes overlap: they sum to 118.3 SOL at the 4.2 SOL cap (total 98.7) and 552.6 SOL at the 84 SOL cap (total 454.7). With one deduplication and each episode assigned to the class of its best member (v8.py): phantom with no taker is 38.5 SOL at 4.2 and 285.2 at 84; state with a taker is 38.1, 50.1 and 69.1 SOL at 4.2, 8.4 and 84. 'Mostly phantom' is true at 84 SOL (63%) but not at the current 4.2 SOL cap (39%). Separately, the analyst's 'credible' class leaves out decoded-landed opportunities with a taker (4.2-6.1 SOL).
- [medium] C9: The w3 seed list (p8+) multiplied raw triggers but mostly added junk: 58-80% were dropped at decode. One pool (DHbktet3wt) produced 76% of p9's trigger signatures, and HUQ2YZbVjh produced 5,909 in p10 with none quoted. Its DammV2>DammV2 pairs were taken 99% of the time, with 0 wins in 473 attempts.
  EVID: status.jsonl trigger_* counters; arrivals.jsonl pool counts vs triggers.jsonl; caps.jsonl venues x opportunities taker; data/seed-pools-w.csv vs w3.csv
  VERDICT: partly — The drop rates are confirmed from status counters: 79.4%, 79.9% and 58.2% in p8, p9 and p10. DHbktet3wt made 19,802 of p9's 26,074 trigger signatures (76%) with 1,740 quoted; HUQ2YZbVjh made 5,909 in p10 with 0 quoted. The DammV2>DammV2 sentence is misattributed. HUQ2YZbVjh, DHbktet3wt and AQddxhyh95 are PumpSwap pools. The DammV2>DammV2 pairs (2,346 opportunities, 99% taken, 0 wins in 473 attempts) run on token 2AVjqm through pools 23Ey3XEHwo and BKH29Cr5mZ; that token accounts for 782 of p9's 1,182 attempts across all venue pairs. 'Mostly junk' is also one-sided: 6 of the 9 wins in p9-p10 used at least one pool that is only in seed-pools-w3.csv.
- [medium] C10: State-path decisions come about 14-15 ms after the trigger's first shred (p50 in every segment), and the first send about 14-16 ms after. In p9 and p10 the taker's transaction was already visible before we decided in 38% and 36% of state opportunities.
  EVID: opportunities.jsonl st.decided - min(arrivals), taker.first_seen_ns; copies.jsonl t_sent
  VERDICT: confirmed — Close to the claim, with slightly wider ranges. For state opportunities, decided minus the trigger's first arrival has a p50 of 13.9-15.8 ms per segment (p10 13.9, p7 15.8). The first copy is sent at a p50 of 13.9-16.4 ms. The taker's first_seen_ns came before our decision in 37% of p9 state opportunities (1,069 of 2,861) and 35% of p10's (1,082 of 3,063), against the claimed 38% and 36%. Among state opportunities that had a taker, the share is 47-48%.

## MISSED (verifier)
- The snapshot DOES contain p11-p14: SNAP/root/runs/w5h-p11..p14 folders, their .out files and arb-w-p11..p15.toml. The report says it does not. Those segments are the direct test of the first recommendation. In p12 and p14 the operator turned TPU direct copies back on, and the bot sent 165 trades on its own quote past stale sims. 136 landed, all 136 failed, 0 won, and 1,608,493 lamports went to fees. Counting p6, sending on our own quote produced 220 trades, 191 landings, 190 failures, 1 win (+24,038 lamports) and 2,321,390 lamports of failed fees.
- The stale sim's 'no' was right about what we could actually capture. Its median round trip was -79 bps (sims.jsonl), and the 95 landed failures came in at a median of -89 bps on chain, all negative (outcomes.jsonl). In those failed TPU landings a taker had already touched both pools at or before our slot in 36 of 57 (p6), 68 of 74 (p12) and 48 of 63 (p14) cases. So the gaps were real but gone before a TPU trade could land. The analyst treats 'the sim is one slot behind' as if it meant 'the sim's fail verdict is uninformative', and the data shows that is wrong.
- outcomes.jsonl's jito field is the verdict of the LAST bundle copy (exec.rs:692-695 overwrites s.jito for each copy), not the first. In p7 (resends at +100 and +250 ms) and p8 (size variants), per-attempt verdicts therefore describe resends. 7 of the 18 bundle wins are recorded as 'would-fail' (example: p7 attempt 62, where copy 0 landed and the last resend failed with 'Blockhash not found'). Per-attempt verdict analysis has to key on the first copy's bundle id in bundles.jsonl.
- Jito would-fail runs about 98% regardless of how early we send. It is 98% for bundles sent less than 10 ms after the trigger's first shred, including 318 cases where no taker had been seen before our send. Inference: either Jito's simulation also often lacks the trigger (the operator's own note at exec.rs:555: 222 of 222 first bundles would-fail in seg 4), or the gaps are mispriced. Either way, 'rely on Jito's free verdict' does not escape the staleness problem, and calling this a 'send stage' leak misplaces the cause.
- Capital is not a constraint at all. All 21 wins were at trade sizes of at most 0.115 SOL (115,271,118 lamports) and returns of at most 1.2%; 274 attempts hit the 4.2 SOL cap and none of them won. This supports the capital recommendation more strongly than the analyst's argument does.
- Leader-clock (PoH) timing is not entirely missing. The shred path writes it to poh.log (shred.rs:247-266); opportunities' poh field is null partly because shred arrivals carry poh: None by design (feeds/mod.rs:118). The cached p10 poh.log (SNAP/big/w5h-p10) has 188,301 entries covering 266 of the 3,473 opportunity triggers, 84 of them together with their taker. Low coverage, but usable for latency proofs now. Minor errors: alt_unknown runs from 690 (p8) to 5,773 per segment, not 987-5,773, and the p6 stale-bypass count is 55 unique attempts (56 log lines).
## REC ISSUES (verifier)
- Rec 1 (stop using the RPC sim / TPU sim gate, rely on the engine's own quote; priority 'now') is RISKY for a live wallet and the data contradicts it. Doing exactly this, sending on our own quote when the sim was stale, cost 2,321,390 lamports of failed fees for 1 win in 220 trades across p6, p12 and p14. For bundles it changes nothing: the sim gate applies only to non-bundle arms (exec.rs:617), and sims.jsonl is a record, not a gate. The proposed 'simulate [trigger, ours]' would also over-approve. For state triggers the trigger already ran in slot N, and in 35-37% of p9-p10 state opportunities the taker was visible before we even decided. Simulating on N-1 plus the trigger would ignore that taker.
- Rec 2 (filter phantoms again, 'now'): the priority is unsupported. Phantom attempts in p8-p10 were 48 of 2,059 sends (2.3%), all Jito bundles that cost nothing when they fail. Setting confirm_trigger_ms to 60 makes decoded triggers wait for the pool update, as the state path does, which is the slower path; it would have delayed the only decoded-trigger win (p9 attempt 976, a dz-retransmit-eu trigger). The operator is already alternating confirm_trigger_ms between 60 and 0 in p12-p15. Turning skip_failing_signers on is untested here and could drop real triggers.
- Rec 6 (fix dead feeds because 'every segment has had zero PoH timing'): the premise is overstated. Shred-derived PoH is already written to poh.log (p10: 188k entries, 7.7% of opportunity triggers covered). Fixing credentials for constantk-prism and erpc is reasonable, but the first step is to analyse the existing poh.log data, or to attach shred PoH to arrivals.
- Rec 5 (prune junk pools): pruning DHbktet3wt, HUQ2YZbVjh and AQddxhyh95 is supported, since they had 0-1,740 quoted triggers against thousands of signatures. The supporting text, though, ties the DammV2>DammV2 problem to these PumpSwap pools, which is wrong; that problem is token 2AVjqm through pools 23Ey3XEHwo and BKH29Cr5mZ. The '4-18x' trigger inflation figure was not verified. Since 6 of the 9 wins in p9-p10 used pools that exist only in w3, prune pool by pool and do not revert the w3 list.
- Rec 3 (treat gaps returning more than 2-10% as suspect): the band numbers check out (0.1-2% returns taken 79-80%; 2-50% returns hold 356.1 SOL, taken 56% and 37%). But only 38-41% of those high-return opportunities are phantoms, and failed bundles cost nothing, so the benefit is mainly cleaner reporting. If the threshold is lowered globally in copies() (exec.rs: implausible_gap), it also applies to state triggers. That is harmless to past wins, which were all at most 1.2%, but it should be scoped to decoded triggers that have not yet landed, as the recommendation's wording suggests.
- Rec 4 (do not raise capital above 4.2 SOL) is sound but understated. Every win was at most 0.115 SOL in size, so there is no evidence that even 4.2 SOL of capital is being used productively.
## RECS
- [now] Stop using the RPC sim (sims.jsonl and the TPU sim gate) to judge gaps. Either simulate with the trigger included (bundle simulation of [trigger, ours]) or rely on the engine's own quote plus Jito's free bundle verdict. — 99.3% of sims run one slot behind, so the 98.9% fail rate reflects the RPC's lag, not the gap. The non-trigger leg matches our quote at 0 bps.
- [now] Filter phantom decoded triggers again in p8+ (confirm_trigger_ms is 0): turn skip_failing_signers back on and/or need trigger confirmation for gaps above roughly 2% return. — 60% of decoded opportunities never land, they carry the largest predicted nets, and in p10 34 of 125 decoded attempts were phantoms.
- [next] Treat gaps returning more than about 2-10% with no landed trigger as suspect, not as profit: lower the implausibility threshold or flag them, and exclude them from the caps and money-left-on-the-table numbers. — These high-return gaps hold 356 of the 412 SOL of predicted net, but only 37-56% of them are ever taken, against 79-80% for 0.1-2% gaps.
- [next] Do not raise capital beyond 4.2 SOL until large gaps can be won. — 0 wins in 1,633 attempts expecting 1M lamports or more. Every win was a gap under about 117k lamports, and the credible class grows only from 40.3 to 52.4 SOL going from a 4.2 to an 8.4 SOL cap.
- [next] Prune seed pools whose triggers are almost always dropped (DHbktet3wt, HUQ2YZbVjh, AQddxhyh95), and limit the DammV2>DammV2 pairs on token 2AVjqm. — They inflate the trigger load 4-18x without quotable triggers. The 2AVjqm pairs used Jito rate and nonces at a 99% taken rate with 0 wins.
- [next] Fix or remove the 5 dead feeds (raiden, corvus, getblock, constantk-prism, erpc). In particular, restore one entries feed for PoH timing and the archive. — Every segment has had zero PoH timing, so latency cannot be proven on the leader's clock.
- [later] Retry lookup-table fetches instead of marking a table missing for the whole run (engine.rs:431/522), and count how many dropped transactions touched watched pools. — alt_unknown drops 987-5,773 transactions per segment, and the potential trigger loss is not measured.
## OPEN Q
- Are Jito 'instruction-error' would-fail verdicts (15-40% of bundle failures) also profit-check failures? The verdict carries no code.
- What do the 'no verdict' bundle outcomes in p7-p10 (114/58/209/37) mean? Were Jito results lost because settle_s was 1-3 s?
- Why are all 5,909 HUQ2YZbVjh triggers in p10 unquotable or unsolved (missing pool state vs. swaps too large for the pool)?
- How many alt_unknown transactions were real triggers on watched pools? A failed table fetch is cached as missing for the whole run.
- Is the 'taker' (first transaction touching both pools within 2 s) a good proxy for arbitrage? For p8-p10 there is no report.json (rivals.jsonl / exec.jsonl are not in the snapshot) to check it.
- Segments p11-p15 are not in the snapshot. A live read shows p12/p14 with 75/66 landings, 1/3 wins and 497,170 / 1,117,914 lamports of failed fees, which suggests the TPU arm is back on. What changed in the config?
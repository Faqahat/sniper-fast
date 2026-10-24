# Fresh unbiased audit of the dip bot — independent agent report, 10-24 ~08:05 PKT

(Saved verbatim from the agent's final message; scripts in this folder, results in ./out/ — 1.3 GB.)

## Summary
- **Baseline (MEASURED, wallet SOL changes on chain):** +0.334 SOL from 10-24 02:17 to 07:18 PKT, ~3.8 h live → ~**+2.1 SOL/day** if run 24/7. 69 logged fires, 24 filled (35%), 44 failed on the +5% guard (6042), 1 missed the deadline (6001).
- **The replay matches reality (MEASURED):** an exact curve replay reproduces all 24 fills' curve P&L to the lamport and 68/68 fill/fail outcomes. All counterfactuals below come from it.
- **Main limiter: where our buy lands in the block (MEASURED).** Every guard failure had 1-11 rival buys (0.9-5.7 SOL in total) land between the dump and us, pushing the price 5-29% up. Filled fires had ≤ 4.1% price drift before us.
- **What being earlier is worth** (75 top-2% dumps over 3.68 h of live runs):

| Landing position (block entries after the dump) | Fill rate | P&L (SOL) |
|---|---|---|
| 25 | 99% | +2.76 |
| 50 | 88% | +2.33 |
| 75 | 79% | +1.96 |
| 150 | 45% | +1.22 |
| 300 | 32% | +0.61 |

  Our median is ~140 entries in the same slot; 41% of our fires land in the next slot. HkQ7 lands at ~75-90.

**Top 5 levers (expected SOL/day if run 24/7; each ±50%, results are heavy-tailed)**
1. **Land 10-20 ms earlier: +3.5 to +5.5 SOL/day** (ceiling ~+10 if first after every dump). Measured by shifting our 55 timed fires earlier (+0.43 SOL for 10 ms, +0.66 SOL for 20 ms). Our internal reaction is only 3.1 ms; ~30-37 ms passes between our send and seeing our tx. Where to look (INFERRED, needs an A/B test):
   - Jito leaders: our worst (25% fill, 184 entries median). On Jito leaders, rival bots' copies sent via soyas, flashblock, speedlanding or helius land earlier than their nozomi, astralane or bolt copies.
   - BAM leaders: our BAM-leader fires earned ~0 SOL in replay.
   - The wait for execution confirmation: we wait for the executed-tx feed after the first sighting (median 1.5 ms, p90 5.7, max 13.5).
2. **Bigger size, 0.35 → 0.75-1.0 SOL: +2.3 to +7 SOL/day.** Replay at our real landing positions: +0.73 → +1.66 → +2.21 SOL; pessimistic (every follower carries a 2% price guard, so our bigger buy makes some fail): +0.69 → +1.29 → +1.47. Holds in every run; turns down above 1.5 SOL; risk per trade 2-3x.
3. **Keep r5's 6-slot time exit (done): +0.4 to +2 SOL/day vs the +5% take-profit of r1-r4.** Most of the gap is one trade (CgWwnp); 4-8 slots give about the same → no further exit gain.
4. **Cut our own latency** (fire on the first shred sighting, faster decision; decision 1.2 ms): +0.3 to +1 SOL/day (the noisy, slope-based part of lever 1 under our control).
5. **Pay one tip per landed buy: +0.25 to +0.4 SOL/day.** We send one tx that tips 2-4 relays and all tips are paid when it lands (0.0026 SOL per fill); rivals send one tx per relay, each tipping only its own relay, and let duplicates fail. Fixed costs 0.89 SOL/day ≈ 29% of pre-cost P&L.

**Checked and dismissed**
- Wider guard: flat or worse (+5% → +0.92 SOL, +10% +0.90, +15% +0.90, no guard +0.80).
- Higher priority fee: BAM and Harmonic do sort each arrival batch by fee (higher first in 75-79% of adjacent pairs), but raising ours to 20-100M µL/CU gains only 1 fill of 40 and costs more than it earns.
- Lower model threshold at today's speed: median ~0; positive in only 2 of 5 runs.
- A single fastest relay: none stands out (best forced-path probes nozomi, bolt, landx at 29-31 ms; direct TPU 42.5 ms; helius-swqos (r5) 50 ms).
- Adverse selection: none (if first after the dump, failed picks earn the same as filled ones: +0.035 vs +0.033 SOL per fire).
- Concurrency limits: only 5 of 74 passes skipped.

**Surprises and blind spots**
- The imitated bots are a minority of what beats us: 80% of top-2% picks were bought by them, yet they put in only 20% of the SOL that landed ahead of us; the rest came from 40+ other dip bots.
- Fill rate is highest on far leaders but worth nothing: leaders 40 ms+ from Frankfurt fill 59% of our fires, worth ~+0.07 SOL in total. HkQ7 skips those slots (0.1% of dumps vs 3.6% on near leaders).
- The "fastest" rivals are not reacting: wallets landing 2-10 ms after a dump (CVPz447t, 5k2Ckk) fail 97-98% of their txs — their buys are already sitting there.
- Logging / code issues: some trades fall outside the logged runs (CLjwTQ 06:38 PKT; r5 continuing past the log copy); the bot sent a second sell after the first had already landed (Biiv46, error 3012); the r4 log has no run_end event.
- Model caveats: population estimates with our landing pattern run ~30% optimistic vs the real fires; one trade ≈ 40% of the replayed profit; followers' actual slippage limits not decoded (bracketed with a stress test).

## Details
1. **Why failures happen** (out/fire_chain.txt, out/tape_timing.txt): same-slot landings fill 13/40, next-slot 11/28 (same slot is not enough by itself). On our feed rivals appear after the dump: haqqiUUX median 40 ms, HkQ7 41 ms, us ~40-42 ms (mid-pack). Of 115 rival buys that beat us within the same slot, 53% were seen ≥ 10 ms before ours, 27% within ±2 ms. Population r3 (11.8 h): 74,068 dumps ≥ 1 SOL; half get a rival buy within one slot; the first rival in the same slot lands a median 75 entries after the dump (p25 32).
2. **Send paths and routing** (out/probes.txt, within_bot_paths.txt, paths_by_client.txt, priority_order.txt, cf_cup.txt): forced single-path probes (send → seen, same slot): nozomi 29.2, bolt 29.7, landx 30.9, staked-rpc 32.8, helius 38.5, astralane 42.1, tpu-direct 42.5, haan 49, helius-swqos 50.4 ms (8-18 probes each; ranks rough); live multi-path ~34-37 ms. 53-64% of rival buys landing within 40 entries of a dump paid no relay tip. Rival copies by relay on near leaders (median entries after the dump): Jito leaders — HkQ7 soyas 50 / flashblock 54 / helius 60 vs nozomi 83; DYXDDrZC speedlanding 52 / helius 64 vs astralane 91 / nozomi 106; BAM leaders — helius 63-84 vs nozomi 81-144, astralane 80-120. Our fill by leader type: Harmonic 53%, BAM 39%, Jito 25%, Firedancer 14%; replay P&L at our real positions: BAM ≈ 0.00, Jito +0.25, Harmonic +0.35 SOL. By leader distance from Frankfurt: < 1 ms 31 fires +0.54 SOL; 1-40 ms 17 fires +0.02; ≥ 40 ms 20 fires +0.07.
3. **Size** (out/cf_size.txt, cf_size_stress.txt): ~9% net per fill at all sizes 0.35-1.5 SOL → profit roughly linear until rivals' guards start failing.
4. **Selection** (out/cf_pop_*.txt, sel_target.txt, curve_runs.txt): the imitated bots' buying is the profit source (below the top-8% threshold, dumps they skip lose 0.0145 SOL each even if we were first); within the top 2% the score does not separate P&L; lower tiers positive in total but median ~0, also at faster landing.
5. **Costs** (out/size_cost_tp.txt): pump fees ~1.25% per side (0.19 SOL over the period); buy tx fee 0.0005; sell 0.0006 + 0.001 tip; failed buys pay no tips (0.0005 each).

**Key files:** sim.py (validated replay), extract.py with x/r2 and x/r3 (raw chain → dump / follower / our-tx rows), cf_fires.py, cf_speed.py, cf_curve.py, cf_pop.py, cf_size.py, cf_cup.py, probes.py, comp.py, followers.py, paths_by_client.py; results in out/.

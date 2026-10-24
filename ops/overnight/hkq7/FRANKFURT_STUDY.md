# Why buys reverted on nearby (Frankfurt) leaders — read-only study, 10-24 (PROD dip runs 1-7, 2g wallet)
Files: frankfurt_study.py/.json, ahead_fees.py, 2g_timing.json, replay_reverted.json
- Frankfurt-area landings: 36 (22 reverted). Our tx was in the SAME slot as the dump 68% (reverted) / 86% (filled), always the same
  validator as the dump's. On the leader's PoH clock we landed ~1 ms after the dump (median 1.3 ms reverted, 0.9 ms filled).
- Difference: buyers between the dump and us. Reverted: median 4 buys / 2.33 SOL ahead, price +13% (guard 5%). Filled: 1 buy / 0.15 SOL, +0.8%.
  Ahead of us when reverted (92 buys): cohort bots 40, others 36, haqqiUUX 12, HkQ7 6, DYX 3.
- They paid LESS than us: priority median 0.00015 vs our 0.0005, tip 0.0002 vs our 0.0022; only 9 of 92 paid more; 36 had no tip at all
  (direct / staked), 29 Helius, 12 astralane, 5 Nozomi. => not fees, not distance: arrival order at the leader's block builder.
- Our side: first sight of the dump on Kaldera, reaction ~3 ms, fire -> our tx seen back ~36 ms (median, Frankfurt).
- By host/client: TeraSwitch Jito leaders 6/8 reverted, Latitude.sh Harmonic 2/7.

## How we could have won the reverted ones (howtowin.py / howtowin.json, 50 reverted buys with full positions)
- The trade that pushed the curve past our guard (min_out): 42/50 landed in the SAME slot as us, a median 41 positions ahead; 7/50 in the
  slot before ours (we spilled one slot); only 1/50 had moved before we fired (decision side is fine: reaction ~1.2 ms).
- The crossing buys were sent ~35 ms after our fire on our feed's clock, yet landed ahead of us; they reached our feed a median 14.6 ms
  before our own tx (BAM 11.5, Harmonic 6-13, Jito 52.6 ms). Who: other 16, profitable bots 13, HkQ7 10, haqqiUUX 2, DYX 1.
  Sent: no tip 15, Helius 8, Nozomi 8, astralane 5; priority 0.00013, tip 0.0003 (we paid 0.0005 + 0.0022).
- => we lose ~10-50 ms in TRANSPORT (relay hops; Jito leaders worst). Fix = a direct staked/QUIC path to the leader (+ Helius single path),
  fewer relays on Jito-client leaders; fees/tips are not the lever.

## Does tipping / priority decide the order inside the block? (tip_order.py, 58 full blocks of the lost races)
- Same-block races (42): the buy that beat us paid a HIGHER priority fee in 13/42 and a HIGHER tip in 3/42; medians winner 1.7M µlamports/CU
  + 0.00021 SOL tip vs ours 5.0M + 0.0022. Tipped and untipped txs sit at the same median block position (~50%); top-10% payers not at the top;
  adjacent pairs ordered by priority ~50-53% (= random). See the run output for the tie-corrected rank correlations per client.

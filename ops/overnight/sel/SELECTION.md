# Selection learned from HkQ7hMjy / DYXDDrZC / haqqiUUX (dip buyers) — study log

All replay, local data, free. Data: every >=1 SOL sell ("dump") on pump.fun curves, 10-22 03:08 -> 10-23 18:19 PKT (39.2 h, 115,566 dumps,
~2,950/h). TRAIN = before 10-23 06:00 PKT (26.9 h), TEST = 10-23 06:00 -> 18:19 PKT (12.3 h). Every rule / model / exit chosen on TRAIN only.
Our trade = 0.5 SOL buy landing 35 / 50 / 75 ms after the dump (block-position proxy), skipped if the price is > 2% above the dump price
(failed attempt -0.0002), follower buys with real decoded limits where known, imputed otherwise.

## What they buy (their picks = they bought within 1 s after the dump)
| wallet | dumps/h | % of dumps | style |
|---|---|---|---|
| HkQ7hMjy | 57 | 1.9% | big drops (>= 6%), very young tokens (median 7 s) |
| DYXDDrZC | 75 | 2.5% | active tokens (buys in the last 4 s, several buyers, net inflow), never the first dump |
| haqqiUUX | 150 | 5.1% | snipers / bundle wallets dumping in a token's first ~5 s |
| any of the 3 | 255 | 8.6% | |

Our replay on THEIR picks is profitable (all dumps: loses). ~70% of that comes from their own buys after ours (stress: they never follow).

## Iterations (TEST numbers, 12.3 h)
1. Copy-DYX rule (sell >= 2.7, not insider, buys >= 4.8 SOL last 20 slots, ...): 75/h, win 59%, +6.4 @35 ms — half the profit needs them following.
2. Narrow profit rule (pump +38% then dump >= 4.1 SOL ...): 8/h, win 79%, +2.2 — robust but too few.
3. OR-list of 6 narrow rules: 22/h, win 59% (TRAIN 71%) — overfit.
4. Model trained on "we win" (all ages, then inside their envelope): TEST win 43-61% — overfit / does not transfer.
5. **Model trained on "they will buy this dump" (imitation), inside their envelope: holds on TEST** (AUC 0.83). Frozen as IMIT1.

## Exits (owner: no fixed 4-slot; test TP / SL / time limits)
Best TP/SL/time-limit exits for these picks (chosen on TRAIN) all use a **1.3 s (6-slot) time limit** = HkQ7's measured timer:
top 2%: TP +5% / SL -10% / 1.3 s; top 4%: TP +8% / SL -5% / 1.3 s; top 8%: TP +8% / SL -10% / 1.3 s. Longer holds (>= 3 s) earn less.

## IMIT1 frozen (sel/IMIT1.json, sha c720ed613357) — checked on TEST (12.3 h it never saw)
Real follower limits decoded for 22,288 follower buys (read-only RPC; sel/slip_args_sel.jsonl). Replay with them (sel3r):

| tier | picks/h | 35 ms | 50 ms | 75 ms |
|---|---|---|---|---|
| top 2% (TP +5% / SL -10% / 1.3 s) | 14.6 | +4.34, win 87% | +2.91, win 82% | +1.77, win 80% |
| top 4% (TP +8% / SL -5% / 1.3 s) | 33 | +6.72, win 71% | +4.75, win 67% | +3.04, win 66% |
| top 8% (TP +8% / SL -10% / 1.3 s) | 75 | +10.31, win 60% | +6.05, win 54% | +3.02, win 51% |

Real-delay check (measured replay-vs-real timing errors; "+15 ms" = every trigger seen 15 ms later, the executed-feed worst case), per day:

| tier | real 20 ms | 35 ms | 50 ms | 75 ms |
|---|---|---|---|---|
| top 2% | 6.7 – 9.2 | 5.4 – 7.5 | 4.0 – 5.6 | 2.5 – 3.6 |
| top 4% | 10.9 – 15.2 | 8.8 – 12.3 | 6.7 – 9.2 | 4.4 – 6.1 |

Hour by hour (top 4%, TEST): we pick ~31 dumps/h (1.2% of dumps, ~27 tokens/h) vs their ~206 dumps/h (7.6%, ~108 tokens/h);
61% of ours are dumps they also bought; 12 of 13 hours positive at 35 ms; 73% of the tokens we filled ended net positive.
Stress: if the three wallets never bought after us, TEST keeps 81-84% of the profit.

Readable gist of what it picks (distilled tree, weaker than the model: TEST 22/h, 64% win, +4.65 @35 ms): price drop > 15% on a token
where the profitable-bot cohort already put in > 4.6 SOL, token <= 13 s old and curve <= 33.6 SOL; or drop 10.7-15% after a +20% run-up.

Next: forward test on data after 18:20 PKT (sel/sel_forward.sh); collector ends 20:43 PKT unless restarted (owner OK needed).

## The three wallets' real last-24 h results (read-only ledgers, ops/overnight/hkq7/)
| wallet | pump-curve trades | failed attempts | net on the curve | notes |
|---|---|---|---|---|
| HkQ7hMjy | +25.9 | −0.56 (4,164) | ≈ +25.4 SOL/day | 0.5 SOL buys, holds ~2 s |
| haqqiUUX | +28.1 | −0.04 (1,026) | ≈ +28 SOL/day | 0.27 SOL median, holds ~6 s; −43 SOL of withdrawals excluded |
| DYXDDrZC | +12.6 | −8.1 (42,972!) | ≈ +4.5 SOL/day | 0.87 SOL median, holds ~17 s; +65.6 more from 457 non-curve txs (likely AMM/DEX sells) |

## Forward test (started 10-23 ~19:45 PKT)
Data after 18:20 PKT: R2 until it stopped (~18:31 PKT) + the new collector run run_20261023_1426 (from 19:26 PKT; 55 min gap).
`sel_forward_loop.sh` re-syncs the new run (read-only), rebuilds, scores with frozen IMIT1, reports tiers + hour-by-hour every 60 min -> `sel_forward.log`.

## More strategies at a 60 ms landing (10-23 ~23:30 PKT; unseen TEST 12.3 h; sel/more_strats.txt, union60.py, run60.txt, firstdev/fd60_search.txt)
- Momentum after >=1 SOL buys (young / older tokens, cohort-imitation or "we win" models): NEGATIVE at every tier (-0.01 to -0.8 SOL/h).
- Dumps on older tokens (6-30 min), cohort imitation: ~0.
- NEW: young-token dumps, model trained on ">=2 profitable-cohort bots buy right after" (top 8%): +0.37 SOL/h at 60 AND 75 ms (0.5 SOL, 54% win).
  Union with IMIT1 wider tier: +0.47/h @60, +0.42/h @75 (0.5 SOL).
- Size (IMIT1 @60 ms): wider tier 2 SOL +0.77/h; top8 1 SOL +0.63/h.
- First-time devs, 60 ms after the bundle, filter (no bundle, description, fresh wallet), sell 5 s: +0.47/h (27% win, optimistic: no follower limits).
- FINAL-2 at 74 ms: negative (live paper -0.54 / 2.3 h).

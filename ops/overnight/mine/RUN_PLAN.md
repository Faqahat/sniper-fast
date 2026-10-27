# Run plan: HOT1 "hot-flow, 1-second" strategy (draft, 10-25)

## What we are running
- **Signal:** a curve trade ≥ 0.3 SOL on a token ≤ 15 min old, scored by the HOT1 model (gradient-boosted trees, 41 features).
  - Features include flow over 1 / 5 / 15 / 60 s, buyers, gap since the last trade, curve level, price change, dev buy/sold, bundle, wallet reputation, and tweet launcher.
  - Buy only if the score is in the top 1% (threshold set on validation).
- **Trade:** buy 1 SOL (smaller while testing), sell on a 1 s timer (~5 slots). The sell is pre-built and fired by the timer, never waiting on RPC.
- **Evidence** (realistic follower limits; trained on day 2, tested on day 3 and today; mine/RESULTS.md):

  | Landing | SOL/day |
  |---|---|
  | ≤ 20 ms | +84 to +95 |
  | 35 ms | +45 to +56 |
  | 50 ms | ≈ 0 |
  | 75 ms | loses |

  So **the whole plan hinges on landing ≤ 35 ms**; every stage below measures that first.

## Stage A — build (offline, free, ~1 day; dev only in /home/moiz/sniper)
1. **Freeze HOT1:** retrain on days 2 + 3 with the realistic 20 / 35 ms labels; export trees, bin edges and the top-1% threshold to JSON in the format `src/dip.rs` `Gbdt::load` already reads.
2. **Reputation file:** wallet → (SOL/day, win %, n) from the census, R1–R3 only.
3. **Engine:** new trigger path next to `--dip` (`src/bin/snipe_engine/dipmode.rs`).
   - Score every ≥ 0.3 SOL trade with the 41 features from the token book, the reputation file, and the launch uri host.
   - Reuse the dip engine's near-leader filter, guard, time exit, timing records and logs.
4. **Parity test:** replay today's recorded tapes through the Rust features and compare with Python scores (pattern: `ops/dip/imit1/export_parity.py`). Pass = ≥ 99% of scores match.

## Stage B — shadow run on the server (free; needs your OK)
- Run with no `--live` for 6–12 h on FRA (and AMS if wanted), near-leader filter on.
- **Logs:**
  - every pick;
  - trigger first-seen time vs the leader's clock (how late we SEE the trigger);
  - decision time;
  - paper result from the real tape afterwards.
- **Pass if:**
  - picks ≈ 70–80/h before the leader filter;
  - paper result ≥ +2% per trade at the measured see-time + send-time;
  - no crashes or memory growth.

## Stage C — landing probes (small cost; needs your OK)
- **What:** unfillable buys on HOT picks (the engine already has `--dip-probe`: min-out = max, the tx reverts, cost ≈ base + priority fee).
- **Size:** ~200 probes at near leaders ≈ 0.1 SOL total.
- **Measures:** the real landing delay after the trigger, per route and per leader client. **This tells us which row of the table above is ours.**

## Stage D — send-path upgrade (engine change; needs your explicit OK)
This is what the rivals that beat us do (measured 10-25: 72% durable nonce, one tip per copy, 4–8 relays + a direct copy).
- **Durable nonce pool:** 16–32 nonce accounts (~0.0015 SOL rent each, refundable). The nonce value is re-read in the background, never on the buy/sell path.
- **Copies:** one tx copy per relay, **one tip each** (today ours carries 2–5 tips in one tx).
- **Relays:** the best 4–6 per leader client, plus a no-tip direct copy.
- **CU price:** per leader client (rivals: 1.7–2.5M µlamports with tips, 11–15M without).
- **Then:** re-run Stage C probes, compare landing before and after.

## Stage E — live micro run (you start PROD with the passphrase)
- **Size:** 0.1–0.25 SOL per buy, 1 s timer exit.
- **Guard:** fail cheap if the price is > +3% above the trigger.
- **Limits:**
  - max 2 positions at once;
  - near leaders only;
  - stop at 100 trades or −1 SOL (`--max-buys`, `--max-loss-sol`).
- **Alerts:** Telegram BUY-only; results to a file; report on request.
- **Pass if, after ≥ 100 trades:**
  - realized ≥ +1.5% per trade after all fees;
  - landing median ≤ 35 ms;
  - guard reverts ≤ 40%.
- **Stop early if,** after 30 trades, landing median > 50 ms or realized < −2% per trade.

## Stage F — scale (only after E passes)
- 0.5 SOL, then 1 SOL; add the AMS region with its own wallet/budget and a disjoint near-leader list.
- Daily loss cap −3 SOL; 24 h runs.
- Weekly retrain on fresh days, with the same out-of-sample checks before swapping models.

## Decisions needed from you
1. OK to build Stage A on the host repo.
2. OK for the Stage B shadow run on the server (which region).
3. OK for Stage C probes (~0.1 SOL).
4. OK for the Stage D send-path change (nonce pool + one tip per copy + more relays).
5. Budget, wallet and region for Stage E; you start PROD.

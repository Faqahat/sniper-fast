# Edge Hunt — pump.fun create+1 / race-free PROFITABILITY study
Date 2026-10-14. Host 77.223.215.155, staked RPC (RMR/constantk). Work in /root/edge_hunt.
No live trading — pure historical reconstruction.

## MANDATE
Find a NET-positive edge on pump.fun tokens from a **race-free** entry (create+1 ≈ our reliable ~1.0–1.33x
floor fill, or a graduation/copy entry) that clears pump's ~2% round-trip protocol fee. The proven 3s flip
is already -EV (gross ~0.7% < 2% fee). Hard cost constraint applied throughout: **1%/leg pump protocol fee
(~2% round trip) + ~0.5% curve slippage** ⇒ breakeven gross multiple **~1.0253 (need +2.53% gross)**.
PumpSwap-leg trades use the cheaper realistic **0.3%/leg + 0.2% slip (breakeven ~1.008)**.

## DATA
- **1,141 unbiased create_v2 launches** (reused /root/profit_backtest/creates.json; discovered via the global
  mint-authority PDA = pure, unbiased create stream, no survivorship bias), slots ~456.60M–456.82M (~14 h).
- **NEW long-horizon harvest** (/root/edge_hunt/long_traj/, 1,129 mints): full bonding-curve price paths out
  to create+5,000 slots (~33 min), ~35k+ txs, for the forward-return horizons. (Prior data was ~30-slot/6s.)
- **Graduation state** (/root/edge_hunt/grad_state.json): getAccountInfo `complete` flag on every curve.
- **PumpSwap pools** (/root/edge_hunt/thesis2_pools_v2.json): migration tx + reserve-ratio AMM price paths.
- **Target sniper 4yFAz** 200 landed trades w/ market price paths (reused /root/exit_study/{rows2,paths}.json).

---

## THESIS 1 — longer-horizon hold / trend from create+1.  VERDICT: **NO (-EV).**
Forward-return distribution at 10s/30s/1m/5m/15m from a create+1 entry, across selection filters
(vanilla, dev-buy bands, anti-factory, early buyer-count, early net SOL inflow), slot train/val split, NET.

**Plain create+1 forward returns (NET R), VAL, worsen monotonically with horizon:**
```
selection              10s      30s      1m       5m       15m
ALL                  -0.015   -0.018   -0.012   -0.021   -0.067
vanilla              -0.020   -0.027   -0.018   -0.059   -0.102
van+dev>=1           -0.004   -0.011   +0.024*  -0.074   -0.146    (*tiny, median -0.040, tail-only)
```
No "second leg": the longer you hold, the worse it gets (mean reversion dominates). Every long-horizon
(5m/15m) cell is strongly negative for every selection.

**The one positive-looking signal was a LOOK-AHEAD artifact.** A "strong early net SOL inflow" gate looked
great at create+1 entry — but you cannot know the first-10s inflow at slot +1. Entering at create+1 and
"selecting" on inflow front-runs the inflow itself (= the floor edge we can't get). Corrected to a
**no-look-ahead gated entry** (observe inflow over [create, create+10s], ENTER at the window end, then hold):
```
                                   NAIVE create+1 (LOOK-AHEAD)   HONEST gated entry (no look-ahead)
van+inflow>=5 SOL@10s, hold 10s    VAL mean +0.1097 med +0.076   VAL mean -0.0187 med -0.034   <- flips NEGATIVE
van+inflow>=2 SOL@10s, hold 10s    VAL mean +0.0789 med -0.003   VAL mean +0.0050 med -0.028   (~0, below fee)
van+inflow>=2 SOL@10s, hold 1m     VAL mean +0.0379              VAL mean -0.0423
```
Once the entry is placed AFTER the signal is observable (the only honest option), the edge vanishes and goes
negative — the price has already moved by the amount of the inflow. **No selection×horizon cell is
no-look-ahead net-positive OOS.** Best honest cell (van+inflow>=2@10s, 10s hold) is VAL mean +0.005 but
median -0.028, win 33%, drop-top2 -0.018 → a net loser. Confirmed even near-zero gross (fee ~2.5% > gross).

---

## THESIS 2 — migration / graduation arbitrage.  VERDICT: **NO (not an arb; -EV race-free).**
**Graduation is rare: 29/1,141 = 2.5%** complete the curve (definitive `complete` flag). 12 cleanly priced
on PumpSwap (= 1.1% of launches) — low opportunity frequency on its own.

**There is no structural arbitrage gap.** Pump seeds the PumpSwap pool at the *canonical curve-completion
price* (~3.26e-07 SOL/token, identical across tokens). final-BC → AMM-open gap ≈ 0 by construction. And the
bonding curve DIES at migration, so there is **no simultaneous two-venue window** — this is NOT a cross-venue
arb (our arbx AMM-arb core competency — pricing two live pools against each other — does not apply). It is a
one-sided directional bet on the post-migration move.

**The migration "pop" happens IN the migration slot itself.** The first on-chain AMM swap is already repriced
(e.g. kifZWTMe: seed 3.26e-07 → first swap 9.2e-04, a real ~2,800x pump with ~4,000 SOL of inflow). Capturing
that requires WINNING the first-block race into the pool — exactly the race the mandate excludes.

**A genuinely race-free entry (≥1 slot after migration, at the already-moved price), NET @0.3%/leg:**
```
entry lag    exit +30s            exit +1m             exit +5m
+1 slot      mean -15.7 med -0.2  mean -20.4 med -0.5  mean -21.2 med +0.3   (win~45-50%, min -68%)
+5 slots     mean -11.7 med +0.2  mean -17.0 med +0.4  mean -17.9 med +0.3   (min -77%)
+25 (~10s)   mean  +2.1 med  0.0  mean  -6.2 med +0.1  mean  -6.2 med +0.2   (min -69%)
+75 (~30s)   mean  -6.2 med -0.5  mean  -8.7 med -0.5  mean  -8.5 med -0.2
```
Median ~0 with a brutal left tail (per-token drawdowns −68%, −77%, −79%, −97% observed) → negative mean.
Even the **look-ahead upper bound** (enter +25sl, sell at the exact 5-min peak) is only mean +5.4% / median
+2.6% — barely over the fee hurdle with perfect foresight. Realistic fixed exits are ~0-to-negative.
Per-token race-free (enter +25sl, exit +1m): cluster at 0% (+0.1,−0.5,+0.4,−0.1,+0.7,−0.8), one −68.9%, one
+19.5%. A lottery, not a repeatable >2% capture.

---

## THESIS 3 — copy / ride the proven sniper 4yFAz.  VERDICT: **NO (lag kills it).**
His ACTUAL realized: **mean +0.078 R, 60% win** (profitable). We detect his buy and enter LAG slots later at
the then-current market price, exit on a rule. NET of 2% fee:
```
LAG (behind him)   his_exit            orderflow(ride if r@+10>=1.05)   tgt+10%     tgt+20%
+1 slot (0.2s)     +0.0012 med -0.042  +0.0171 med -0.025 drop2 -0.001  -0.021      -0.016
+2 slots (0.4s)    -0.0010             +0.0120 drop2 -0.005             -0.027      -0.018
+3 slots (0.6s)    -0.0043             +0.0116                          -0.030      -0.022
+4 slots (0.8s)    -0.0070             -0.0025                          -0.035      -0.024
+6 slots (1.2s)    -0.0187             -0.0120                          -0.037      -0.029
```
His **+0.078 edge collapses to ~0 at lag=1 (0.2s behind)** and is clearly negative by realistic lag (2–4
slots). Every cell has a NEGATIVE median and ~30% win. The best, orderflow at lag=1 (+0.017 mean), has
drop-top2 ≈ 0 and median −0.025 → tail-dependent, not a real edge. **Riding only his WINNERS (held >10 slots)
is WORSE, not better** (−0.012 at lag=1, −0.034 at lag=4): his winners are the ones that run fastest in the
first slots, so our lagged entry pays the entire run-up. His alpha is his SAME-SLOT floor entry; it is not
transferable to a follower.

---

## OTHER edges spotted
The only persistent positive signal anywhere in the data — strong early net SOL inflow predicts short-term
(≤30s) price continuation — is capturable ONLY from a pre-inflow (create+1, same-slot) entry, i.e. it IS the
create-slot floor edge. From any race-free entry point it is already priced in and nets negative. No other
create+1-compatible, >2%-net edge found.

## RANKED VERDICT — is there ANY race-free edge that clears the fee?  **NO.**
1. **Thesis 2 (migration)** — closest to a structural story and best infra fit IF it were a two-venue arb, but
   it is not (AMM seeded at completion price, curve dies at migration). Race-free entry ~0 median, fat left
   tail, net-negative; only 2.5% graduate. Most *buildable* only as a first-block race (which we're told to avoid).
2. **Thesis 3 (copy)** — cleanest signal (a known +EV wallet) but lag is fatal: edge gone at 0.2s behind.
3. **Thesis 1 (hold/trend)** — no edge at any horizon; longer holds strictly worse; the apparent signal was look-ahead.

**Root cause (consistent with the prior fillvalue/ourfill/snipe studies): the entire edge lives at the
create-slot floor / same-slot priority.** Every race-free entry — create+1, post-migration, or 1 slot behind a
winner — enters AFTER the move that constitutes the edge, and the ~2% round-trip fee then guarantees a loss.
This is a fill-priority problem, not a selection/horizon/venue problem. None of the three theses clears 2% net OOS.

### Caveats
- One ~14 h market regime, one asset class. Graduation sample is small (29; 12 cleanly priced) — inherent to a
  2.5% base rate, not a harvesting limit. Flat per-leg cost model (no depth curve beyond linear slip). Intra-slot
  order not recoverable (create+1 = first fillable price). Target-wallet copy is 200 trades / ~38 h, one wallet.
- 17/29 graduated tokens failed automatic PumpSwap pool detection (vault-owner heuristic); the 12 priced span
  the full outcome range (−97% to +2,800x) so the qualitative verdict is robust, but exact Thesis-2 percentiles
  rest on n=12.

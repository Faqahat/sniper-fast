# Launch filter — sketch

Which `create_v2` launches to actually snipe, and how big. This is the alpha — entry speed and exit are
mechanical; the filter is what turns them into the sniper's 67%-win / positive-expectancy profile.
Companion skeleton: `sketch/filter.rs`. Not wired; no send-path changes.

## 0. Hard constraint that shapes everything
The sniper buys in the **same slot** the token is created, so the filter must decide from **only what is in
the create_v2 transaction** plus **pre-computed in-memory state**. No RPC, no account fetch, no waiting for
holders/price. That rules out most "token screener" signals and forces a specific design.

## 1. Three tiers (all O(1), slot-0)
**A — Intrinsic (from the create_v2 tx we just decoded):**
- `dev_buy_sol` — the dev's bundled first buy (same tx). The single strongest slot-0 signal; the sniper
  itself conditions on it. Band it: reject near-zero (no conviction) and whale (we'd buy the top).
- `creator_fee_bps` (create_v2 arg) — a high creator fee means the dev extracts on every trade; reject above
  a cap.
- `is_mayhem_mode` (arg) — risk flag; gate or down-weight.
- metadata: `name`/`symbol` non-empty, `uri` present (socials). Optional gate / weight.
- `is_cashback_enabled`, `is_holder_reward` (args) — informational, feed the score.

**B — Creator reputation (in-memory table, fed by exit outcomes):** per creator pubkey (a create_v2 arg):
`launches, sniped, rugs, ewma_pnl, last_slot`. DENY repeat ruggers / strongly-negative EWMA; ALLOW/boost
proven creators; NEUTRAL for unknown (the common case). This closes the loop:
filter → snipe → exit → **outcome updates the creator's stat** → sharper filter.

**C — Global risk controls:** `max_concurrent` positions (exposure), per-creator cooldown, global
launches-per-100-slots rate cap, per-day drawdown **kill-switch**, 1-snipe-per-mint. These keep a bad run
from compounding and are what let the strategy survive variance.

Decision: pass A and C, not DENY in B → a bounded score **sizes** the position (bigger for a stronger
signal, smaller/again-gated for mayhem or weak dev buy).

## 2. What the data says (directional — n=12, NOT fitted)
From the sniper's own snipes (create_v2 features vs realized PnL):
- Dev buy clearly matters and is **not monotone**: a 3.0-SOL dev buy (7oeU) *lost*, a ~1.0-SOL one (FR94)
  *won* — consistent with a mid-band sweet spot rather than "bigger is better." (Full table filled in once
  the feature pass completes; see `/tmp/sniper_report.json` + the features run.)
- creator_fee_bps was 0 on the sampled launches (devs not over-charging) — so the fee gate mostly guards
  against the occasional extractive outlier.
- These 12 points are too few to fit thresholds; they set *direction and shape* (band, not cutoff), and the
  defaults in `filter.rs` encode that. Real thresholds come from §4.

## 3. Sizing
`size = clamp(base_size * score, 0, max_size)`. Score peaks at the dev-buy mid-band, ×1.3 for ALLOW-rep
creators, scaled by positive EWMA, ×0.7 for mayhem. The sniper runs ~3 SOL typical; `base_size` defaults
to 2 SOL, `max` 5. Position size also feeds exit `min_sol_output` floors.

## 4. Calibration (before any live run)
12 live snipes can't fit a filter. The shadow harness does it:
1. Record a large `create_v2` stream from the shred feed (features: dev_buy, creator, fee_bps, mayhem, uri).
2. For each, compute the **counterfactual outcome** by replaying entry (slot-0 buy) + the exit ladder
   (`exit.rs`) against that launch's recorded `bonding_curve` updates — i.e. "what would we have made."
3. Grid/greedy-search the `FilterConfig` thresholds for expectancy (mean PnL/snipe) and tail (max drawdown,
   rug rate), with a train/validation split to avoid overfitting the window.
4. Freeze the config; shadow-run live (decisions logged, **no send**) and confirm the realized feature
   distribution and hit-rate match the backtest. Then — and only then — ask before enabling live sends.

## 5. The loop it closes
`detect_launch` → `Filter::evaluate` (this) → size → durable-nonce buy (launch.rs) → `Exit` ladder
(exit.rs) → outcome → `Reputation::record` → next decision. Each snipe makes the creator table smarter.

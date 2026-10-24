# Dip-backrun: independent check (2026-10-23, ~11:45 PKT)

Analysis only. Everything ran on this host. No trades, no RPC, no trading servers.
Every number is labelled **MEASURED** (computed from data here) or **INFERRED** (a model or a judgement on top of data).
Times are PKT (UTC+5). Data: R1 10-22 03:08 → 18:01 and R2 10-22 20:43 → 10-23 10:29 (28.6 h of data, 31.4 h span).

## Verdict

- **The code and the arithmetic are right.** I rebuilt every event, feature and PnL from the raw chunks with my own decoder. All 29,810 claim events match. PnL matches to 0.00002 SOL on 100% of them. The block CV totals reproduce exactly (+28.21 / +18.07 / +7.74 / −4.05). MEASURED.
- **No look-ahead that matters.** All features use only trades up to the sell. One feature (`snp_seller`) uses wallet labels built on the whole period; removing it costs about 1 SOL at 35 ms. MEASURED.
- **But the +18.1 SOL is an upper estimate.** Three assumptions all lean the same way:
  1. "L ms" is in block-position units. Measured against real arrival times, those gaps run ~7 ms long, so a trade that really landed before us is often counted as behind us. INFERRED from MEASURED pairs.
  2. Followers' slippage limits come from early snipers, not from the dip bots we race. HkQ7hMjy, for one, refuses to buy more than ~2% above the dip price. MEASURED.
  3. 0.0008 SOL per transaction. HkQ7hMjy pays ~0.0011 SOL per buy. MEASURED.
- **Corrected, at a real 35 ms end to end: about +10 SOL over the 28.6 h (≈ 8–9 SOL/day), not +18.1.** Range +9.6 to +11.3 at 0.0008 SOL/tx, and +6 to +8 at 0.002/tx. With a walk-forward model: +5 to +6. INFERRED.
- **It depends entirely on speed.** At a real 50 ms it is about 0 (−1.9 to +2.5). At a real 75 ms it loses 6–7 SOL. Run 2's live buys landed 73–75 ms after the create, so **at today's measured speed the strategy does not hold.** MEASURED (replay) / INFERRED (latency).
- **Size:** 0.5 SOL per trade. At 1 SOL the realistic total does not grow (+10.8 vs +11.3), and the risk goes up. At 0.25 SOL it is about +6. INFERRED.
- **The niche is real for a fast bot.** HkQ7hMjy made +28.0 SOL over the two runs: 1,705 round trips, +0.016 SOL each, ~0.62 SOL per buy, median delay 39 ms after the sell. That is close to the replay's +0.012 per trade at 35 ms. We would be racing it and ~70 other fast backrunners. MEASURED.

## Bugs and their SOL impact (L = 35 ms, 0.5 SOL, 0.0008 SOL/tx)

| # | Issue | Impact | Label |
|---|---|---|---|
| 1 | The exit clock starts at the slot of the **last trade ahead of us**, not at the slot our own buy lands in. Holds are one slot short on 9% of the L35 picks (6% at L20, 15% at L75). | −0.17 SOL on the same picks; −0.78 SOL if the model is retrained on corrected labels (+16.90 vs +17.68). | MEASURED |
| 2 | The mayhem filter `c.get("mayhem")` does nothing: launches.jsonl has no such field. 492 mayhem events (1.7%) are in the set. The vsol filter catches most mayhem launches. Fix: `"InitializeMayhemState" in ixn` or the CreateEvent flag. | 4 L35 picks, +0.01 SOL | MEASURED |
| 3 | `snp_seller` uses gf_wallets.json, built at 08:16 PKT 10-23 from R1 and most of R2, so the wallet labels see the test blocks. | Without the feature: L35 +16.92 (−1.15), L50 +5.08 (−2.66), L20 +28.22 (0), L75 −3.82 (+0.2). This is inside the seed noise (L35 ranges 16.85–18.35 over 7 seeds). | MEASURED |
| 4 | **Latency units (model, not code).** L is a block-position gap. Real gaps are shorter than proxy gaps (median +3 to +8 ms, mean ~+7 ms). PLAN.md calls this "+7 ms pessimistic". That is true for snipe timing against the create. For a backrun it is optimistic, because real competitors get counted as behind us. | At a real 35 ms the L35 picks make +13.9 to +15.6 instead of +18.0 (−2.4 to −4.1). | INFERRED from MEASURED pairs |
| 5 | **Follower limits (model).** The slack list (a8_slack.json) is 711 limits from buys in the first 10 slots of FINAL-2 launches: median slack 42%, so only ~8% of followers are dropped. The fast dip bots behave differently (table below). | Using each fast backrunner's measured tolerance: −4.5 SOL (95th-pct tolerance) to +2.3 SOL (99th pct). | INFERRED from MEASURED |
| 6 | Followers using the exact-tokens `buy` are modelled as "same SOL, fewer tokens" (in reality: same tokens, more SOL). | +0.24 SOL; the claim is conservative here. | MEASURED |

Not bugs (checked): failed transactions, multi-leg transactions, fees, gap repair, graduation, non-SOL curves, event ordering, the busy rule, the CV threshold. Details below.

## 1. Reproduction (task 1)

- **Snapshot.** The claim's files were copied to `snap/` with sha256s; the claim author was still editing dip/ while I worked. dipbuy4.py changed at 11:02 PKT and dipcv.py at 11:03 PKT, but only to add stress-test and comparison options that do not touch ev4_b05 or the CV result.
- **The claim's CV, re-run exactly** (`cv_repro.py`, same seeds). MEASURED.

| L | Claim | Reproduced | Trades | Blocks positive |
|---|---|---|---|---|
| 20 ms | +28.2 | +28.21 | 1,476 | 6/6 |
| 35 ms | +18.1 | +18.07 | 1,467 | 6/6 |
| 50 ms | +7.7 | +7.74 (ev4_b05_slow) | 1,579 | 6/6 |
| 75 ms | −4.1 | −4.05 (ev4_b05_slow) | 1,426 | 1/6 |

- **My own rebuild** (`vx_extract.py` + `vx_replay.py`). It decodes TradeEvents and CreateEvents from the raw chunks of both runs (R2 173 files, R1 193 files). It keeps the first 720 slots of every launch. It never imports core/ or dip/. MEASURED:
  - Every one of the 29,810 claim events is found.
  - With the claim's block sizes, PnL equals the claim's on 100% of matched events at L = 20/35/50/75 (|diff| < 0.00002 SOL), and every feature is identical.
  - With my own block sizes (max index over all raw lines), 99.8% are identical. 13–35 events differ by one trade "ahead"; the sum differs by −0.2 SOL.
  - Systematic differences, all explained:
    - 13 extra events in mine are all mayhem launches. Their vsol only leaves the 25–200 SOL range after my 720-slot window.
    - 245 (L20) and 275 (L35) claim events have no later trade inside my window. Their claim PnL is exactly −0.0140 (a pure round trip). Neither difference is a bias.
- **CV on my rebuild** (claim spec, same CV code), MEASURED:
  - L20 +28.55, L25 +24.45, L35 +17.68, L45 +10.78, L50 +7.75, L75 −2.48.
  - Mayhem launches removed: L35 +17.96.

## 2. Look-ahead and leakage (task 2)

- **Features** (all 35): computed from `tr[:k]` or `tr[:k+1]`, i.e. trades up to and including the sell. Gap-repair trades before the sell are inferred from the sell's own pre-state. **No post-sell information.** MEASURED (code read + identical features in my rebuild).
- **`snp_seller`**: look-ahead wallet labels, see bug 3. `pro_seller` is a fixed 9-wallet list chosen from case studies in the same period. That is mild. INFERRED.
- **Event filter**:
  - The vsol test (min < 25 or max of the first 50 > 200 SOL) reads the whole tape. On standard curves vsol can never leave 30–115 SOL, and no standard-curve event is removed by it. So it is a curve-type filter, not an outcome filter. MEASURED.
- **Selection threshold**: the top-5% cut comes from a random 15% of the *training* blocks. Top 2 / 5 / 10% give +10.3 / +18.1 / +18.3 at L35, so 5% is not a lucky pick. MEASURED.
- **CV split**: 16 launches have events in two blocks; 7 of the L35 picks are on them (+0.09 SOL). MEASURED.
- **The CV trains on future blocks.** Walk-forward (train only on earlier blocks, blocks 1–5), MEASURED:
  - L20: +21.26 vs +22.84 for the same blocks in the claim's CV.
  - L35: +11.87 vs +14.85 (−20%). All 5 blocks are still positive.
  - L50: +3.97 vs +6.76.
  - L75: −6.98 vs −2.99.
- **Exit choice**: 4 slots is the best of the exits tried at L35 (4 / 6 / 8 / 12 slots → +18.1 / +15.5 / +12.0 / +4.5). That is a mild optimism from choosing on the same data. MEASURED.
- **Busy rule** (one event per 20 slots): causal, uses only earlier events. It does mean the replay never looks at a second big sell inside 20 slots; live trading would. Not a leak. MEASURED (code).
- **Event ordering**: tapes are sorted by (slot, index, event index); events by create time + age. Fine. MEASURED.
- **Model noise**: 6 more seeds, MEASURED:
  - L20: 28.65–29.42.
  - L35: 16.85–18.35 (mean of 7 seeds 17.6).
  - L50: 5.29–7.84.
  - L75: −2.62 to −5.96.

## 3. Mechanics (task 3)

### Arrival proxy vs real arrival times (MEASURED, `vx_proxy.py`, `proxy_strict.py`, `proxy_cond.py`)

- **Data.** The shadow engine's own arrival times (scores_v3 "obs", first ~1 s of R2 launches). I matched 134,784 txs in 7,524 launches (successful and failed txs), giving 1.04M pairs.
- **Absolute.** Against the create: correlation 0.95; proxy − real median +15 ms.
- **What matters is the gap from one trade to a later one.**
  - Proxy gap − real gap: median +4 to +10 ms; p10 −17 to −57; p90 +43 to +47.
  - With unambiguous matches only (21,019 anchors): median +3 to +5, mean +7, p10 −15 to −21, p90 +29 to +37 (real gaps 20–75 ms).
- **Who is ahead of a buy sent 35 ms after a trade:**
  - The proxy catches 76% of the trades that really arrived first (88% with unambiguous matches).
  - Of trades the proxy puts 35–50 ms after the sell (behind us in the replay), **44% really arrived within 35 ms.**
- **The decisive margins are a few ms.** In the hand-checks, the backrunners that decide the trade sit 0.1–5 ms either side of our 35 ms mark. The proxy cannot resolve that.
- **Caveat.** Real arrivals exist only for the first second after a create, not for dips at 1–120 s. Block sizes are per slot, so the error should carry over. INFERRED.

### Other mechanics, L35 picks

| Check | Result | Label |
|---|---|---|
| Guard-free entry | 903 of 1,466 picks (62%) have nobody ahead and make +15.8 of the +18.0. A 2% min-tokens guard: +17.1 to +17.4 (L35), about 0 at L75. | MEASURED |
| Exit slot | Bug 1. | MEASURED |
| Sell landing | first in slot +18.49 · 75 ms +18.03 · 150 ms +17.59 | MEASURED |
| Fees | Every dip sell carries 95 + 30 = 125 bps. Buy = 0.5 / (1 + fee) to the curve; sell × (1 − fee). Correct. | MEASURED |
| Multi-leg txs | 2 picks have the sell inside a multi-leg tx (no buy leg). Followers are replayed leg by leg in event order. | MEASURED |
| Failed txs | 25,126 TradeEvents sit inside failed txs in the raw chunks (R2 14,893, R1 10,233). Both pipelines drop them; none move the curve. | MEASURED |
| Collector gaps | 4 picks have a gap-repair trade inside the hold (their PnL −0.04). 15 have a slot with no raw line at all (−0.20). | MEASURED |
| Graduation | 0 picks reach vsol ≥ 110 SOL or a complete curve inside the hold. | MEASURED |
| Mayhem / non-SOL | Bug 2 (4 picks). Non-SOL curves (PUMP-, USDC-quoted…): their trades are not in the SOL TradeEvent stream; 0 events. | MEASURED |

### Who the replay sells into (MEASURED, `backrunners.py`, `bk_tolerance.py`)

- **The fast backrunners.**
  - 70 wallets buy within 150 ms after dips at least 50 times, with a median delay ≤ 100 ms.
  - Median delays: HkQ7hMjy 39 ms, DYXDDrZC 48, haqqiUUX 50, EMKY7r6U 59.
  - Typical fee + tip per buy: median 0.00033 SOL; HkQ7hMjy 0.00114.
- **Their tolerance**, from successful buys and failed txs right after dips:
  - HkQ7hMjy fails 94–96% of the time once the price is ≥ 2% above the post-dip price.
  - Most others accept 5–10%.
- **If none of those 70 bought after us,** the L35 picks would lose 15.8 SOL. That is an extreme bound. The profit is selling into their buys.
  - Removing only HkQ7hMjy's later buys: +16.7.
  - Measured tolerances instead of random slack: +13.5 (95th pct) to +20.3 (99th pct).

## 4. Hand-checks (task 4): 3 winners, 2 losers, R2, L = 35 ms

- All txs were re-read from the raw chunk lines and the TradeEvents decoded again (`handcheck.py`; full step-by-step tables in `out/handcheck.md`).
- Every tape row matched its raw event, and no tx in the windows had failed. MEASURED.

| Trade | Sell | Ahead of us | Curve before → after our buy (vsol) | Followers in hold | vsol at our sell | Mine | Claim |
|---|---|---|---|---|---|---|---|
| [CAQSVSkL](https://gmgn.ai/sol/token/CAQSVSkL8FZ17v9nY4cq8eWcgQtHPzi1XD1y2XAAAjqR) 05:41:52 ([sell tx](https://solscan.io/tx/4KMdDcwHnba1NqgePocuMWBoykTuowJLTLMVwC6kzJw6Yk3ABcmpysYBawWK5KzLi66t6WLu9k1e8qbG7TtLyr4Y)) | 2.851 SOL, −11.1% | none | 47.021 → 47.515 | 2 buys (3.57, 2.39 SOL), 0 dropped | 53.475 | **+0.1152** | +0.1153 |
| [46dNG3kp](https://gmgn.ai/sol/token/46dNG3kpZEQe4r3ZzwfManuv1FgmDyEbLvt7Qgk66q69) 21:41:38 ([sell tx](https://solscan.io/tx/5A5MqajiQrP9hAFQWL2m6Nc9AnCU4ZdtKqUhEijEgwyueHN1oTGmw8ZWx3NbKYtbtTw3wvoJnXX5xjiBFBviTCYt)) | 2.503 SOL, −14.0% | HkQ7hMjy (21.2 ms), ocBBRKb1 (33.4), 3MHgGwdL (34.9) | 33.112 → 33.606 | 3 buys at slot+4 (9–11 ms in), 2 small sells | 35.923 | **+0.0551** | +0.0551 |
| [BZwnJXdr](https://gmgn.ai/sol/token/BZwnJXdrrP4MhMPy73dhWRUikTsT9HRqvrbmBv8PsDVY) 22:27:23 ([sell tx](https://solscan.io/tx/wccGvr3cdCAtg55t2MqeeFoJtfwXVzNZsK2cx2TDsDpdPyAiF1q2HCoMgw7z9263d2BQ4Zm72h5yS48dmX63Fy1)) | 2.050 SOL, −9.1% | none | 41.784 → 42.278 | haqqiUUX (39.9 ms), EMKY7r6U (40.3 ms) + 3 buys | 43.798 | **+0.0215** | +0.0215 |
| [6kgf3DK7](https://gmgn.ai/sol/token/6kgf3DK78zLcS7rF9ez5JD5k7i2sKCnQ8UPN3MKXpump) 00:44:36 ([sell tx](https://solscan.io/tx/3zUvBpRCCKB58LtGk9yqMkLPmmGSzh8S2Lya6CsydhCU9vLUhyUvp65vnPAvWf81W83VfncpwUxkXM2fVZyEKjC1)) | 1.371 SOL, −8.2% | a 0.885 SOL sell (2.8 ms) | 30.646 → 31.140 | none (next trade 14 slots later) | 31.140 | **−0.0139** | −0.0140 |
| [EzwntFtH](https://gmgn.ai/sol/token/EzwntFtHQ18kJEAKnckxHKpiCrkShxirZap3pA1hpump) 22:24:14 ([sell tx](https://solscan.io/tx/4cqvbviWAKifrEJ8T33bXi2h1QYkRdXwupUFBJYQmLPt2ionoed5rwvAmaB4QoKqbzAm5h4NwAGuZygAm3XAXY1g)) | 2.926 SOL by 4yFAz7dp, −16.4% | 3 buys (10.9–17.3 ms) | 33.513 → 34.007 | 2 tiny buys; the two buyers ahead sell 2 slots later | 32.227 | **−0.0633** | −0.0633 |

- In example 3, the two buyers that make the profit arrive 4.9 and 5.3 ms after our proxy landing.
- In example 2, two buyers land 0.1–1.6 ms before it.
- That is far inside the proxy's ±20–40 ms error.

## 5. Robustness (task 5), claim spec unless noted

| Test | L20 | L35 | L50 | L75 | Label |
|---|---|---|---|---|---|
| Claim | +28.2 | +18.1 | +7.7 | −4.1 | MEASURED |
| Bootstrap of the total (launches resampled within blocks), 95% range | +24.3…+32.5 | **+13.9…+22.2** | +3.5…+12.3 | −7.9…+0.1 | MEASURED |
| Per block: share of resamples above 0 | 100% each | **100% each** | 76–100% | 1–95% | MEASURED |
| Without the best 10 launches | +24.9 | **+14.6** | +4.4 | −6.7 | MEASURED |
| 0.002 SOL per tx | +24.7 | **+14.5** | +4.0 | −7.4 | MEASURED |
| 0.003 SOL per tx | +21.8 | **+11.6** | +0.8 | −10.2 | MEASURED |
| Sell first in slot / 75 ms / 150 ms | +29.3 / +28.3 / +27.7 | +18.5 / +18.0 / +17.6 | +8.7 / +7.8 / +7.0 | −2.8 / −4.0 / −4.7 | MEASURED |
| Own-arrival exit slot (bug 1) | +28.3 | +17.9 | +7.6 | −4.2 | MEASURED |
| No follower slippage at all | +35.6 | +24.3 | +13.4 | +0.5 | MEASURED |

- **L sensitivity** (model retrained at each L, my rebuild): 25 / 35 / 45 ms → +24.5 / +17.7 / +10.8. MEASURED.
- **Fixed L35 picks priced at 25 / 35 / 45 ms:** +23.6 / +18.0 / +12.3. MEASURED.
- **Every 10 ms costs about 5 SOL.** MEASURED.

## 6. Corrected numbers (INFERRED)

- **Same picks as the claim.** Re-priced with three fixes:
  - the exit counted from our own landing slot;
  - the 70 fast backrunners following their measured 95th-pct tolerance (others keep the claim's imputed slippage);
  - "L" converted from proxy to real latency using the measured proxy errors.
- Range = all matches … unambiguous matches only. 0.5 SOL per trade. Totals over the 28.6 h of data (`combo.py`, `combo_boot.py`).

| Real latency (sell processed → our buy processed) | 0.0008 SOL/tx | 0.002 SOL/tx | 0.003 SOL/tx | Claim (0.0008) |
|---|---|---|---|---|
| 20 ms | +14.6 … +18.0 | +11.0 … +14.4 | +8.1 … +11.5 | +28.2 |
| **35 ms** | **+9.6 … +11.3** | +6.1 … +7.7 | +3.2 … +4.8 | +18.1 |
| 50 ms | +1.9 … +2.5 | −1.9 … −1.3 | −5.0 … −4.4 | +7.7 |
| 75 ms (Run 2 live landing) | −6.8 … −6.2 | −10.2 … −9.6 | −13.1 … −12.5 | −4.1 |

- **Real 35 ms, 0.0008 SOL/tx:**
  - Bootstrap 95% range: +6.1 … +15.0 (both error sets).
  - Without the best 10 launches: +6.3 … +7.9.
  - Blocks positive in 87–100% of resamples.
- **Walk-forward picks, real 35 ms** (blocks 1–5 only): +5.0 … +6.3.
- **With the looser 99th-pct tolerances:** +17.7 at real 35 ms. That is the upper end.
- **Size, real 35 ms, 0.0008 SOL/tx:**
  - 0.25 SOL: +6.4.
  - 0.5 SOL: +11.3.
  - 1.0 SOL (the claim's own 1 SOL file, its CV says +26.9): +10.8. Without its best 10 launches only +4.7, and −1.9 at 50 ms.

## 7. External reality check (MEASURED, `hk_real.py`)

- **HkQ7hMjy, the wallet the strategy copies,** on launch mints in the first 720 slots:
  - 1,705 closed round trips: R1 +14.15 SOL, R2 +13.83 SOL, after pump fees, its tx fees and tips.
  - +0.0163 SOL per round trip at an average 0.62 SOL buy. Median hold 10 slots.
  - 4,675 failed txs, worth about 0.02–0.07 SOL.
- **So a real bot at ~39 ms (proxy) earns ~2.6% per trade.** The replay at 35 ms says 2.5%. The niche exists; whether we can take a share at our speed is the open question.

## What I could not check

- **Real arrival times at dip ages (1–120 s).** The shadow logs cover only the first ~1 s of each launch.
- **The real slippage limits of dip-time buyers.** The collector keeps no instruction arguments, and RPC was off limits.
- **How competitors would react to us beyond their price guards.** For example, the leader ordering by fee: we would pay 0.0008 against tips of 0.001.
- **Our real dip latency.** I did not measure it. The only live number is Run 2's 73–75 ms (RUN2_RESULTS.md), measured with the same engine clock as the shadow arrivals.
- **A forward test.** fwd_dip.log has only 4 DIP picks so far (+0.11 SOL) and 0 DIP4 picks. Too few to mean anything.

## Files (all in /home/moiz/sniper/ops/overnight/verify_dip/)

- `snap/`: frozen copies of the claim's inputs, with SHA256SUMS.
- Rebuild and comparison:
  - `vx_extract.py` and `work/R1`, `work/R2`: own extraction.
  - `vx_replay.py` → `out/vx_events_*.jsonl.gz`: own events and PnL variants.
  - `vx_compare.py` → `out/compare_*.txt`.
  - `cv_repro.py`, `gb.py` (a copy of gbdt_np.py) → `out/cv_*`, `out/cv/`, `out/seeds/`.
  - `mk_evfile.py`.
- Mechanics, proxy and competitors:
  - `sel_variants.py` → `out/sel_variants_claimsel.txt`.
  - `sel_diag.py`, `guard_fee.py`, `exacttok.py`, `mayhem_check.py`.
  - `vx_proxy.py`, `proxy_strict.py`, `proxy_cond.py` → `out/proxy_*.txt`.
  - `backrunners.py`, `bk_tolerance.py`, `vx_tolstress.py`, `vx_finegrid.py`, `fg_analyze.py`.
- Corrected numbers: `combo.py`, `combo_boot.py` → `out/combo_*`, `out/corrected_table.txt`.
- Hand-checks and HK: `handcheck.py` → `out/handcheck.md`; `hk_real.py` → `out/hk_real.txt`.

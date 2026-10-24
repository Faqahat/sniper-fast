# Dip-backrun: direct triggers, history lag, census, exits — independent check (2026-10-23, 13:40–14:10 PKT)

Analysis only, on this host. No trades, nothing sent, the trading server was not touched. Read-only RPC only: `getTransaction` on ~320 distinct txs, ~1,200 requests including retries; most retries hit v1 txs before I set the version flag. The endpoint was never printed.
Labels: **MEASURED** = computed here from data; **INFERRED** = judgement or scaling on top of data. Times PKT.
All replay P&L is in the claims' own **replay units**: block-position latency "L", follower limits real-or-imputed, 0.5 SOL, 0.0008 SOL/tx, six-block CV, top 5%, 2-slot exit unless noted. The corrections from VERIFY_DIP.md still apply on top (the proxy is ~7 ms optimistic for backruns; follower-limit coverage; backrunner tolerance; tx cost).
Inputs were frozen in `v2_snap/` (SHA256SUMS, SHA256SUMS_ev). This matters: during the check the R2 collector data was re-synced (08:21 UTC) and `core/slip_args.jsonl` kept growing (another job was appending to it). Rebuilt numbers therefore drift by ±1–2 SOL against the claim files.

## Verdicts

| # | Claim | Verdict | Corrected / key numbers |
|---|---|---|---|
| 1 | 76% of trades have no top-level pump ix. 57–71% of picks are direct, carrying 74–86% of P&L. The rule is 99.8% accurate. | **Holds** | Reproduced exactly. Fresh out-of-sample check: the rule agrees on 199/200; the truth labels agree on 100/100. New: 12% of direct triggers are **v1 transactions**. |
| 2 | Direct-only CV: "35" +21.56 (guard +18.24), "50" +12.64 (+10.28), "75" +4.92 (+6.47) | **Holds** (replay units) | Exact reproduction. All 6 blocks positive at every L. Seeds: ±0.5–1 SOL. No label leakage. |
| 3 | DIP_HLAG is correct. HLAG=0 equals dipbuy4. A 100 ms lag barely changes direct-only P&L. | **Holds for code and unguarded P&L; partly for the guard** | 45,223/45,223 rows identical. No leak that matters. 100 ms lag, guarded: −7% / −14% / **−32%** at 35 / 50 / 75 ms. |
| 4 | HkQ7hMjy is ~8 ms slower on routed triggers (36.6 vs 44.2) | **Partly** | Small-sample, not significant (95% CI −0.8…+16.1). On all 44.5k triggers: **+2…+3.5 ms** (+5.6 early in the slot). The first buyer of any wallet: +5.5 ms. |
| 5 | Census: FIFO round-trip P&L. ≥100-trip wallets +293 SOL. Profitable delay band 10–60 ms. | **Per-trip method holds on chain; population claims fail as stated** | 23% of census rows are duplicate copies of one buy. Unsold remainders are valued at 0 (−368 SOL of phantom loss). Corrected: ≥100-trip wallets **+215 (+190 net of tx)**. "Retail −315" is an artifact. The 0–10 ms band is the **best** band, not −99. |
| 6 | The 2-slot exit is best (long holds, TP, ride-with-pro rejected) | **Partly** | Long holds are worse even after fixing a real bias against them (+1…+12 SOL). But 2 vs 4 slots is a tie: on the same picks 4 ≥ 2, and the CV ranking flips between data snapshots. |

---

## 1. Direct vs routed triggers — HOLDS

**Reproduced (MEASURED):**
- `variants.py sample_txs2.jsonl`: 1,133 / 1,500 = 75.5% of trades have no top-level pump ix. The first sample gives 116 / 162 = 72%.
- `trig_analyze.py` output is identical to the PLAN table. Share of picks that are direct: 56.8% / 58.0% / 64.4% / 71.0%.
- P&L, direct vs routed: 35 ms +22.54 vs +8.01; 50 ms +13.90 vs +2.99; 75 ms guarded +6.26 vs +1.05.
- So direct triggers carry 74% / 82% / 86% of the P&L. Base rate: 41.6% of all triggers are direct.
- `direct_rule.py` re-run gives 7,701 / 7,719 = 99.8% in-sample.
  - All 18 errors are direct→routed; there are no routed→direct errors.
  - The whitelist is the standard programs plus `L2TExMFK`.
  - Re-run flags differ from `direct_flags_prelim.json` on 1 of 44,535.
- My own OOF picks on `ev_hlag0` give the same picture: 57% / 58% / 65% direct, carrying 73% / 81% / 86% of P&L.

**Fresh check** (`v2_fresh_cls.py`, own decoder; static + ALT keys; TradeEvent from logs or the self-CPI event; "direct" = a top-level pump ix on the mint whose accounts contain the event's seller):

| Sample | n | Agreement | Direct share |
|---|---|---|---|
| A: random triggers NOT in `trig_tx.jsonl` (label from the rule, never fitted on them) | 200 | **199 / 200 (99.5%)** | 39% |
| B: random OOF picks (35 / 75 ms) with RPC truth | 100 | **100 / 100** | 66% |

- The one miss is a top-level sell in a tx that also calls an unknown program (`troyXT7T…`). The rule marks it routed, the same direction as the in-sample errors (conservative).
- All 144 direct triggers use one of the three discriminators (`33e685a4`, `1c92de77`, `5df6823c`). In all 144, the u64 at offset 8 equals the tokens sold.

**New engine facts (MEASURED):**
- **45% of fresh triggers are version-1 transactions.** getTransaction fails on them unless `maxSupportedTransactionVersion: 1` is passed; 123 of my first 300 calls failed until I set it.
  - They are mostly routed (82 / 122), but **9 / 78 direct triggers (12%)** and **5 / 66 direct picks (8%)** are v1 too.
  - The shred decoder must parse v1 messages, or it loses ~8–12% of the direct triggers.
- 1 of 144 direct triggers has the mint only via an address lookup table.
- In 5 / 144 the seller is not the fee payer. Take the seller from the account position, not from the signer.

## 2. Direct-only CV — HOLDS (replay units)

**Exact reproduction** (`v2_snap/dipcv.py`, the claim's command): +21.56 / +18.24, +12.64 / +10.28, +4.92 / +6.47. MEASURED. My harness `v2_cv.py` keeps all OOF scores and reproduces the same totals.

**Leakage and threshold (code read + MEASURED):**
- The direct flag is not among the 35 features (`FK`). Training uses all labelled triggers, direct and routed.
- The threshold is the top 5% of a random 15% validation slice of the training blocks, over all triggers. The direct filter is applied only to the test block's picks: a decision-time mask, no leakage.
- Rows are restricted to events that have a label (43,727 of 43,954 at 35 ms). The label is a property of the trigger tx, independent of the outcome.
- "thr" mode (top 5% among direct triggers) gives about the same: +20.56 / +12.80 / +5.41.

**Stress, direct-only (MEASURED):**

| | "35 ms" | "50 ms" | "75 ms" (unguarded / guard) |
|---|---|---|---|
| Per block | +2.56 … +4.89, 6/6 positive | +1.19 … +2.89, 6/6 | +0.19 … +1.35, 6/6 / guard +0.58 … +1.56, 6/6 |
| 3 seeds (va split + GBDT seed) | +20.97 … +21.92 | +12.64 … +13.52 | +3.37 … +4.92 / +5.22 … +6.47 |
| Bootstrap 95% (launches within blocks) | +18.2 … +25.1 | +9.6 … +15.7 | +1.7 … +8.1 / +4.1 … +9.1 |
| Without the best 10 launches | +19.0 | +10.4 | +2.7 / +4.5 |
| Rebuilt on today's data and frozen limits (HLAG 100 build) | +20.3 | +11.1 | +4.0 / +4.9 |

- Picks: 1,266 / 1,256 / 1,311 over ~33 h. Mean per trade: +0.017 / +0.010 / +0.004 SOL.
- **INFERRED:** these are replay units. VERIFY_DIP's correction ratio at a real 35 ms was 0.53–0.62. Applied here, it suggests roughly +11…+13 per ~33 h, not +21.6.

## 3. History-lag test (dipbuy5 DIP_HLAG) — HOLDS for the code; PARTLY for "barely changes"

**Code read:**
- `kv` drops every trade whose proxy arrival is within HLAG ms before the trigger.
- Every feature reads `tr[:kv]`.
- The trigger's SOL and drop are recomputed on the stale curve: constant product with the trigger's token amount, gross SOL as in the TradeEvents.
- Labels are untouched. The guard reference (`px`) uses the stale post-sell price, as intended.
- No arithmetic bug found.

**Places where hidden information still enters (MEASURED effect):**
1. **Event selection uses true values.** The tests `sell ≥ 1 SOL` and `vsol < 100` (and the 5-slot spacing they drive) use the true values, not the stale ones the engine would compute.
   - I rebuilt with selection on the stale values (`v2_mods/dipbuy5_stalesel.py`, same data, same frozen limits) and labelled the new events with the same truth / rule.
   - 1–3% of events change: at HLAG 100, 490 drop and 892 enter, out of ~45.2k.
   - P&L is the same or higher:

| Lag | Selection on | 35 ms | 50 ms | 75 ms (unguarded / guard) |
|---|---|---|---|---|
| 100 ms | true values (claim) | +20.31 | +11.12 | +4.03 / +4.89 |
| 100 ms | stale values (engine) | +21.16 | +14.24 | +6.36 / +6.35 |
| 400 ms | true values (claim) | +19.47 | +11.38 | +2.50 / +1.50 |
| 400 ms | stale values (engine) | +21.63 | +14.93 | +4.17 / +2.99 |

   - So this leak does not inflate the result.
2. **Cohort features.** The `coh_*` features still read `tr[:k]`. That is dead code here: `DIP_COHORT_FILE` is unset and the features are not in `FK`.
3. **Wallet labels.** `snp_seller` uses wallet labels from the whole period. This is pre-existing (VERIFY_DIP: ~−1 SOL).

**HLAG=0 identity:** full check over all 512 buckets (the claim checked 453 rows). **45,223 / 45,223 rows are identical** between dipbuy4 and dipbuy5, with frozen limits and the same launch list. MEASURED.

**Effect of a 100 ms lag** (direct-only; mean of 3 seeds each, same files as the claim; MEASURED):

| | 35 ms | 50 ms | 75 ms |
|---|---|---|---|
| Unguarded, 0 → 100 ms | +21.5 → +22.0 | +13.0 → +12.7 | +4.4 → +3.7 (−16%) |
| Guarded, 0 → 100 ms | +18.0 → +16.6 (−7%) | +10.5 → +9.1 (−14%) | **+5.9 → +4.0 (−32%)** |

- "Barely changes" holds for the unguarded version at 35–50 ms.
- At today's speed the strategy relies on the guard (75 ms guarded), and that version loses about a third.
- Note: the PLAN's 400 / 1000 ms rows were built at 08:22–08:29 UTC on newer collector data than the 0–100 ms rows (44,969 vs 44,763 events; possibly newer slippage limits too). Those rows mix the data change with the lag.

## 4. HkQ7hMjy: routed vs direct reaction — PARTLY

| Sample | HkQ7hMjy n (direct / routed) | Median direct / routed (ms, proxy) | Diff | 95% CI | p (perm.) |
|---|---|---|---|---|---|
| Claim's set (10% of triggers, RPC truth) | 58 / 80 | 36.6 / 44.2 | +7.6 | −0.8 … +16.1 | 0.07 |
| **All 44,535 triggers** (truth, else rule) | 634 / 780 | 38.2 / 40.4 | **+2.2** | −0.7 … +4.5 | 0.13 |
| All triggers, OLS with slot position, block size, age and sell size | | | +2.0 ± 1.5 | | |
| All triggers, stratified by the trigger's slot position | | | +3.5 | | |
| All triggers, trigger in the first quarter of its slot | 256 / 275 | 44.4 / 50.0 | +5.6 | +0.9 … +12.0 | |
| First same-slot buy by ANY wallet, stratified | 7,004 / 9,159 | | **+5.5** | each stratum +1.9 … +9.7 | |

**Confounders:**
- **Slot position** is the big one: −43 ms per unit position. A same-slot follower of a late trigger can only show short delays, so delays are censored.
  - The direct triggers that HkQ7hMjy follows sit slightly earlier in their slot (median position 0.34 vs 0.38).
  - They are also bigger (2.9 vs 1.9 SOL).
- Age and block size are balanced.

**Conclusion:**
- Routed sells are followed a few ms later at population level (~4–7 ms, proxy units).
- For HkQ7hMjy the best estimate is **~2–4 ms**, at most ~6 ms early in the slot, not 8 ms. The 8 ms figure is the small-sample point estimate.

## 5. Census of dip backrunners — method right per trip, population claims biased

**Hand-check against the chain** (`v2_census_hand.py`; buy and sell txs; the wallet's SOL and token balance changes): 10 / 10 trips, all fully sold in one sell. MEASURED.
- Token amounts match exactly.
- The census's cost (event SOL × 1.0125) and back (× 0.9875) differ from the wallet's actual SOL change only by tx fee + tip.
- Chain round-trip P&L = census − 0.0009…0.0016 SOL for HkQ7hMjy, and − 0.0026…0.0041 SOL for DYXDDrZC.
- The collector's fee + tips under-counts DYXDDrZC's tips by ~0.0011–0.0015 per trip.

| Wallet | Trip (mint, buy tx) | Delay | Hold | Census P&L | Chain net |
|---|---|---|---|---|---|
| DYXDDrZC | 8m8nKGd6, FxvayKmjYv… | 60.8 ms | 24 slots | −0.1117 | −0.1143 |
| DYXDDrZC | CgYUnf7j, 3z5U7724ft… | 58.7 | 41 | −0.0487 | −0.0528 |
| DYXDDrZC | 8jKGUD34, bXEPktnHev… | 11.3 | 6 | +0.1571 | +0.1531 |
| DYXDDrZC | 5476uWir, 3gEva5sP57… | 8.8 | 19 | +0.1424 | +0.1398 |
| DYXDDrZC | EddV23zN, 2JouvwtPNw… | 38.0 | 205 | −0.0897 | −0.0938 |
| HkQ7hMjy | FuAaRRaD, 2BkxaEQkZV… | 37.2 | 38 | +0.0861 | +0.0852 |
| HkQ7hMjy | By1VzGnD, 4SaFgZ9iDW… | 41.8 | 9 | +0.0198 | +0.0183 |
| HkQ7hMjy | CxKaAm7B, 1HQGsibtYo… | 32.7 | 6 | +0.0267 | +0.0251 |
| HkQ7hMjy | Fk6wtdAq, 58UnRTEQnp… | 38.3 | 24 | +0.0861 | +0.0845 |
| HkQ7hMjy | Fkdqvjx1, Z2mhB8mEh1… | 41.7 | 61 | −0.0139 | −0.0155 |

**The census code reproduces** on a re-run with the same matching (`v2_census.py`): +21.8 on 42,374 rows; ≥100-trip wallets 67, +293.0; 1–10-trip wallets −315.2; delay bands −98.8 / +43.2 / +49.3 / +48.3 / −10.2 / −10.0. But the population numbers have four problems (MEASURED):

1. **Duplicate rows (bug).** The census matches triggers by the slot-derived age. Every ≥1 SOL sell in the event's slot therefore becomes a trigger, and the same follower buy is counted once per such sell.
   - **9,646 of 42,374 rows (23%) are copies** of a buy already counted. They carry +47.7 SOL.
   - Example: DYXDDrZC's buy `pXenmHMD…` is counted 4 times (four sells of 3.29 / 3.31 / 1.67 / 1.84 SOL in one slot).
   - Top wallets' figures shrink accordingly:

| Wallet | Census rows → unique buys | Census P&L → P&L on unique buys |
|---|---|---|
| DYXDDrZC | 1,138 → 934 | +36.6 → **+21.6** |
| HkQ7hMjy | 1,771 → 1,411 | +23.0 → **+17.5** |
| haqqiUUX | 2,030 → 1,805 | +22.9 → +20.1 |
| sssssDdM | 419 → 288 | +22.4 → **+10.4** |

   - The duplicated copies also produce most of the apparent "one sell credited to several trips" cases. After de-duplication, only 142 sells are over-attributed.
2. **Partial trips (unsold remainder valued at 0).** 837 partial trips carry **−367.7 SOL** of phantom loss:
   - −352.9 SOL of it sits in the 1–10-trip wallets;
   - −318.4 SOL in the 0–10 ms band;
   - −174.3 SOL in the "300+ slots, bag holders" bucket.
3. **No-sell trips are dropped.** 4,562 trips (9.7%) never sold within 600 slots.
4. **No tx costs.** Collector fee + tips ≈ 0.0018 SOL per round trip on average (0.0016 for the ≥100-trip wallets; more for DYXDDrZC, see the hand-check).

**Corrected** (`v2_census_fifo.py`: unique buys, per-wallet FIFO over all the wallet's trades on the mint, sells within 600 slots, remainder marked to market at the curve then):

| Item | Census claim | Corrected (MEASURED) |
|---|---|---|
| ≥100-trip wallets | 67 wallets, +292.6, 79% positive | **53 wallets, +214.9; +189.8 net of collector tx costs, 79% positive net** |
| Top wallets (P&L / trips) | DYXDDrZC +36.1 / 1,137; HkQ7hMjy +23.0 / 1,771; haqqiUUX +22.9; sssssDdM +22.4 | DYXDDrZC **+20.4 / 948**; HkQ7hMjy **+17.7 / 1,411**; haqqiUUX +18.5 (+24.2 closed); sssssDdM +10.8; ETwEAQPL +14.0; 5mWe9kLZ +9.5; ssssswdk +9.8 |
| 1–10-trip wallets | −315 SOL, 34% positive | **Not negative:** +58.6 on closed trips (+724 with mark-to-market, which is unreliable for big unsold whale buys) |
| By delay, closed trips, % of SOL in | 0–10 −98.8; 10–60 +1.2…+1.5%; 60–150 slightly negative | **0–10 +7.3% (+204 SOL, the best band)**; 10–25 +2.0%; 25–40 +0.9%; 40–60 +1.6%; 60–100 −0.1%; 100–150 −0.6% |
| By hold, unique full trips | 300+ slots −218.6 (bag holders); 40–100 +74.5 | 300+ **−38.2**; 40–100 +117.8 (+3.7%); 100–300 +92.9 |
| Skill persists? | (claimed "skill game") | **Yes.** 51 wallets positive on R1 (≥30 trips) make +119.8 net on R2, and 85% of them are positive on R2. The 21 R1-negative wallets make +2.4 on R2. |

- **The profitable band:** the upper edge (~60 ms, slightly negative beyond) holds on closed trips. The claim that 0–10 ms loses (−98.8, "pre-queued") is wrong: on closed trips, 0–10 ms is the most profitable band.
- **Downstream numbers inherit the duplicate bug.** These were computed from duplicate-inflated census rows and should be re-derived from unique buys:
  - `pros53.json` and `pros_R1.json`;
  - "DYXDDrZC +9.0 on 202 of our 75-ms picks";
  - the "53 profitable pros".

## 6. Exits — PARTLY

**Code read** (`rt_fixed`, `rt_tp2`, `rt_ev`, `rt_follow`):
- No arithmetic or exit-clock bug found.
- Sell placement is the same for every exit (75 ms into the exit slot).
- TP fires on the position's value net of fees and sells the next slot.

**Bias 1: follower limits penalize long holds.**
- Every follower's slippage limit (real or imputed) was set on a curve **without** our buy.
- The replay applies it however late the follower arrives. A follower 10–80 slots later has seen our buy, and its limit includes it.
- I added `rt_fixed_dw` (`v2_mods/dipbuy5_dw.py`): limits apply only to followers arriving ≤ DW ms after our buy (proxy). Everything else is unchanged.

**Bias 2: each exit has its own model.**
- The claim retrains on each exit's label, so "exit" and "which trades get picked" are confounded.
- A long-hold label is noisy, and its model picks worse trades.

**Same trades for every exit** (the 2-slot model's OOF top 5% on today's build; claim's follower model vs limits only ≤ 1 s after our buy; MEASURED, `v2_out/exit_fixed.txt`):

| Exit | 35 ms claim / ≤1 s | 50 ms claim / ≤1 s | 75 ms guarded claim / ≤1 s |
|---|---|---|---|
| 2 slots | +26.35 / +26.35 | +14.45 / +14.45 | +6.44 / +6.44 |
| **4 slots** | +25.96 / +25.96 | **+16.00 / +16.00** | **+9.47 / +9.47** |
| 8 slots | +20.31 / +22.38 | +9.03 / +11.40 | +3.17 / +4.56 |
| 20 slots | +15.04 / +20.63 | +1.12 / +7.85 | +0.25 / +4.57 |
| 40 slots | +4.94 / +11.98 | −11.52 / −2.90 | −2.84 / +2.95 |
| 80 slots | −17.03 / −9.46 | −27.86 / −18.72 | +0.46 / +6.33 |

**Model retrained on each exit** (same build; the claim's six-block CV; MEASURED):

| Exit | 35 ms | 50 ms | 75 ms guarded |
|---|---|---|---|
| 2 slots | +26.35 | +14.45 | +6.44 |
| 4 slots | +27.28 | +16.23 | +4.49 |
| 8 slots, claim / ≤1 s | +19.81 / +20.98 | +4.90 / +6.22 | −4.61 / −3.11 |
| 20 slots, claim / ≤1 s | +2.81 / +6.91 | −10.14 / −2.91 | −11.89 / −6.73 |
| 40 slots, claim / ≤1 s | −15.32 / −10.46 | −20.94 / −13.59 | −21.84 / −20.58 |

- **Long holds are worse.** The follower bias is real: it costs long holds +1…+12 SOL. Even after fixing it, ≥8-slot holds stay below 2–4 slots at 35–50 ms, whichever model picks the trades. The rejection of long holds and 20-slot TPs stands. (`rt_ev` and `rt_follow` share the same follower model and inherit the same bias; ride-with-pro's list was chosen in-sample, which favours it, and it still lost.)
- **"2-slot is best" is not shown.** On the same trades, 4 slots ≥ 2 slots at every latency, and at 75 ms guarded: +9.5 vs +6.4. With retraining, the order flips between data snapshots:
  - the claim's build: 2 > 4 by 0.2–3.6 SOL;
  - today's build: 4 > 2 by 0.7–2.3 at 35–50 ms, and 2 > 4 at 75 guarded.
  - Treat 2–4 slots as equivalent.

## Other findings

- **Data drift.** The R2 collector data and `core/slip_args.jsonl` changed during this check. Rebuilding from the same code moves totals by ±1–2 SOL. Freeze inputs (as in `v2_snap/`) before quoting decimals.
- **Not modelled: a shred trigger can fail on chain.** A shred-based trigger will also fire on direct ≥1 SOL sells that then fail, so no dump happens. The replay only sees successful sells. I did not size this.

## Commands (all from `/home/moiz/sniper/ops/overnight/verify_dip`; D=`../dip`, S=`../dipshadow`)

```
# snapshot
cp -p $D/{dipcv,gbdt_np,dipbuy4,dipbuy5}.py $S/{direct_flags_prelim.json,direct_rule.py,...} ../core/gf_wallets.json v2_snap/; sha256sum ...
cp ../core/slip_args.jsonl v2_snap/slip_args_snap.jsonl; python3 -I v2_mkmods.py      # patched copies -> v2_mods/
# 1
(cd $S; python3 -I variants.py sample_txs2.jsonl; python3 -I trig_analyze.py trig_sigs.jsonl trig_tx.jsonl)
(cd $S; python3 -I ../verify_dip/v2_snap/direct_rule.py trig_sigs_all.jsonl trig_progs_all.jsonl trig_tx.jsonl ../verify_dip/v2_out/direct_flags_rerun.json)
python3 -I v2_fresh_cls.py; python3 -I v2_fresh_sum.py                      # 300 read-only getTransaction
# 2
DIRECT_FILE=v2_snap/direct_flags_prelim.json DIRECT_MODE=filter EVF=$D/ev_hlag0.jsonl.gz EXIT=2 LATS=35,50,75 GUARDS=1.02 Q=0.05 python3 -I v2_snap/dipcv.py
DIRECT_FILE=v2_snap/direct_flags_prelim.json EVF=$D/ev_hlag{0,100}.jsonl.gz EXIT=2 LATS=35,50,75 [VA_SEED=s GB_SEED=s-1] OUT=v2_out/oof_hlag*.jsonl python3 -I v2_cv.py
python3 -I v2_oof_analyze.py v2_out/oof_hlag*.jsonl
# 3   (env as the claim: RP_PHASEA_R2=phaseA_dry SELL_LAT=75 SLIPIMP=1 DIP_REAL_SLIP=1 DIP_LATS=35,50,75 DIP_B=0.5 DIP_HS=2 DIP_BUSY=5 V2_SLIP=v2_snap/slip_args_snap.jsonl)
DIP_HLAG=0 python3 -I v2_hlag_identity.py
DIP_HLAG={100,400} V2_OUT_BASE=v2_out/evs_hH_true.jsonl.gz V2_OUT_STALE=v2_out/evs_hH_stale.jsonl.gz python3 -I v2_hlag_sel_sig.py
python3 -I v2_label.py v2_out/labels_sel.json v2_out/evs_h*.jsonl.gz; DIRECT_FILE=v2_out/labels_sel.json EVF=v2_out/evs_h*_*.jsonl.gz ... python3 -I v2_cv.py
# 4
python3 -I v2_hk_routed.py; python3 -I v2_hk_routed2.py
# 5
python3 -I v2_census.py $D/ev_hlag0.jsonl.gz v2_out/census_v2.jsonl.gz; python3 -I v2_census_analyze.py; python3 -I v2_census_extra.py
python3 -I v2_census_fifo.py $D/ev_hlag0.jsonl.gz v2_out/census_fifo.jsonl.gz; python3 -I v2_census_fifo_an.py
python3 -I v2_census_hand.py                                                # ~20 read-only getTransaction
# 6
v2_out/run_exit_dw.sh   # dipbuy5_dw build: DIP_HS=2,4,8,10,20,40,80 V2_DWS=0,400,1000, then v2_cv.py EXIT=2 ALLP=1
python3 -I v2_exit_fixed.py; v2_out/run_exit_cv.sh; python3 -I v2_oof_analyze.py v2_out/oof_dw_exit*.jsonl
```

Outputs: `v2_out/` (each table above has its .txt there: `fresh_cls_summary.txt`, `repro_dipcv_hlag0_filter.txt`, `oof_analyze_hlag.txt`, `oof_analyze_sel.txt`, `hlag_identity.txt`, `hk_routed*.txt`, `census_*.txt`, `census_hand.txt`, `exit_fixed.txt`, `exit_cv_summary.txt`).

# Token selection, round 2 (2026-10-22)

**Data:** 20,301 SOL-quoted launches out of 24,889, collected over 15 hours (2026-10-21 22:07 → 2026-10-22 13:00 UTC).

**Validation:**
- Time split: train on the first 50%, validate on the next 25%, test on the last 25%. The test set is untouched until the end.
- Walk-forward over 3-hour periods.

**Costs:** pump fee per side, plus a fixed 0.015 SOL per round trip.

**Size and price math:** 0.5 SOL per trade, priced with an exact replay of the bonding curve.

**Entries:**

| Entry | Meaning |
|---|---|
| E_bundle | First buyer right after the dev's glued bundle |
| E_k1 / E_k2 / E_k3 | Behind 1 / 2 / 3 other buyers |
| E_slot | After the whole create slot |

**New in round 2:**
- Features: dev launch rate, funder clusters, copycat name waves, market heat, launch-tool fingerprint, hour of day.
- Exits: trailing stops and take-profit ladders.
- Model: a boosted-tree model trained on the trade outcome itself.

## 1. Pump ranking works
The model scores launches by "pumps +50% after our entry within 10 minutes":
- Ranking quality (AUC) is 0.88–0.89 on test, at every entry, and stable across walk-forward periods.
- The top 5% of picks pump in 29–33% of cases, against a 5.5–7% base rate, about 5x.
- But "pumps at some point" is not "profitable to trade": the same tokens also dump hard.

## 2. Model trained on the trade outcome (E_bundle, sell after 5 s)
Exit and score threshold were chosen on validation; these are test results.

| Selection | Test n | Mean | Median | Win | PF | Max DD | Walk-forward periods |
|---|---|---|---|---|---|---|---|
| Top 1% of launches | 73 | +13.4% | +6.1% | 56% | 2.65 | 0.41 SOL | +5.8% / +10.8% / +11.8% |
| Top 2% | 146 | +10.6% | −0.6% | 48% | 2.32 | 0.49 SOL | — |

The top 1% is about 20 trades per hour, roughly +0.067 SOL per trade at 0.5 SOL.

**Main features:**

| Feature | Share of model |
|---|---|
| Post-bundle price, i.e. how much dev + bundle bought | 42% |
| Dev buy | 13% |
| Not a mayhem token | 4% |
| Creator idle time | 3% |
| Bundle SOL | 3% |
| Creator launches in the window | 2% |
| Funding amount | 2% |

**What the picks look like** (median, picks vs all launches):

| Feature | Picks | All launches |
|---|---|---|
| Dev buy | 2.96 SOL | 0.10 |
| Glued bundle | 3.4 SOL, 3 wallets | none |
| Creator's last tx before the create | 401 s | 32 s |
| Creator's previous create | 17.5 min | 1 min |
| Creator funded with | 7 SOL | 0.5 SOL |

## 3. Simple filters a sniper can run before buying
All columns are mean per trade at E_bundle, sell after 5 s. The 5 periods are 3 hours each.

| Filter | Train | Val | Test (n) | Test median | Test PF | 5 periods |
|---|---|---|---|---|---|---|
| F4: dev ≥ 2 SOL, bundle ≥ 2 wallets, creator idle ≥ 300 s, not mayhem | +8.6% | −1.2% | +7.3% (161) | −2.8% | 1.73 | +8 +9 +2 +5 +6 |
| F3: dev ≥ 2, bundle ≥ 3 SOL, idle ≥ 300 s, no create by this dev in the last 15 min | +10.0% | −2.7% | +7.0% (112) | −2.8% | 1.66 | +10 +9 −1 +5 +6 |
| F5: dev ≥ 1 SOL, idle ≥ 350 s | +5.6% | +1.5% | +4.5% (303) | −4.9% | 1.56 | +6 +4 +3 +5 +4 |

## 4. Position decides the result
The model's top-1% picks are contested: 74% have other buyers in the create slot (median 2), against 18% of all launches. Same picks, different entry (test, 5 s exit):

| Entry | Mean | Median | Win |
|---|---|---|---|
| First after the bundle | +13.4% | +6.1% | 56% |
| Behind 1 buyer | +4.8% | −4.6% | 42% |
| Behind 2 buyers | +1.8% | −6.2% | 37% |
| After the create slot | +2.2% | −4.6% | 44% |

Models trained directly for the behind-1/2/3 and after-slot entries did not validate.

## 5. What the sniper needs
**Selection, at create-slot speed:**
- dev buy ≥ 2 SOL;
- a glued bundle of at least 2 wallets;
- not mayhem;
- the creator's previous transaction at least 5 minutes before the create. This needs the creator's latest signature: an RPC call of about 20–50 ms, or a local index of wallet activity built from our own feed;
- no create by this dev in the last 15 minutes, from our own create stream.

**Execution:** be the first buyer after the bundle, then sell after about 5 s. On these tokens other snipers arrive in the same slot, so each buyer ahead of us cuts the edge sharply.

## Caveats
- Only 15 hours of data, all one market regime.
- The test set was looked at for several model variants, so there is mild selection; the walk-forward is the stronger evidence.
- Exits are modelled as instant at the exact curve price.
- A forward paper test on new launches is needed before any live run.

## Round 2b: sell-into-snipers exits, ranking, paper test (2026-10-22 evening)

**New exits:**
- sell right after the 1st / 2nd / 3rd / 5th outside buy;
- sell after 1 / 2 / 5 SOL of outside buying;
- sell at the first sell by anyone;
- each also in a realistic "_eos" form: our sell executes at the end of the slot where it triggered;
- fixed holds of 3 s and 10 s.

### Ranking (E_bundle; exit and threshold chosen on validation; test = last 25%, untouched)
| # | Strategy | Test n | Mean | Median | Win | PF | Max DD | Walk-forward |
|---|---|---|---|---|---|---|---|---|
| 1 | Model top 1%, sell at the first sell, delayed to end of slot (fsell_30s_eos) | 67 | +12.5% | +7.8% | 75% | 6.45 | 0.19 SOL | (instant version: +9 / +12 / +11%) |
| 2 | Model top 1%, sell at the first sell, instant | 85 | +11.7% | +8.2% | 72% | 7.56 | 0.16 SOL | +8.8 / +11.8 / +10.7% |
| 3 | Model top 1%, sell after 5 s | 73 | +13.4% | +6.1% | 56% | 2.65 | 0.41 SOL | +5.8 / +10.8 / +11.8% |
| 4 | Model top 2%, fsell_30s_eos | 116 | +9.6% | +6.0% | 67% | 4.64 | — | — |
| 5 | Rule: bundle ≥ 3 wallets AND metadata host meta.uxento.io, sell 3 s | 44 | +7.0% | −3.8% | 41% | 2.67 | — | 5 periods all positive (+5…+11%) |
| 6 | Filter F4 (dev ≥ 2, bundle ≥ 2 wallets, idle ≥ 300 s, not mayhem), sell 5 s | 161 | +7.3% | −2.8% | — | 1.73 | — | 5 periods positive |
| 7 | Rule: creator idle ≥ 352 s AND dev ≥ 1.08 SOL, sell 5 s | 285 | +5.0% | −4.9% | 39% | 1.60 | — | 5 periods positive |
| 8 | Rule: dev ≥ 3 SOL AND bundle ≥ 1.8 SOL, sell at first sell | 369 | +3.1% | −2.1% | 43% | 1.62 | — | 5 periods positive |

**Not profitable:** behind 1 or more buyers (E_k1/E_k2/E_k3), after the create slot, and all delayed entries. The models and rules for those didn't validate or went negative on test.

### Forward paper test (started 2026-10-22 15:43 UTC)
- **Collection:** a new 24 h run on the server, `run_20261022_1543`.
- **Frozen strategies:** both models (fsell_30s_eos and h5s, trained only on run 1) and filters F3/F4/F5. Files: `/home/moiz/sniper-data/collect/paper/frozen_*.json`.
- **Scoring:** `ops/select/paper_cycle.sh` copies the new data, rebuilds and scores every new launch at entries E_bundle / E_k1 / E_k2 / E_slot. It runs every 2 h; results go to `paper/forward.txt`.
- No money is involved.

## Round 2c: more strategy families (2026-10-22 16:xx UTC)
Run-1 data, same 50/25/25 time split, 0.015 SOL fixed cost.

| Family | Result |
|---|---|
| Launch-tool cohorts (metadata host, create variant, fee fingerprint, createdOn) | **Every cohort loses on its own.** Best is meta.uxento.io at about break-even (−0.9% test). |
| Follow known pros, legit version (first outside buyer is a pro, enter right behind them) | **Negative:** test −2.0%. |
| Follow known pros, "≥ 2 pros in the create slot" version | Test showed +3.2%, but this is **look-ahead and invalid:** at the behind-1 entry you can't yet see the second pro. |
| Launches without a glued bundle | **Weak and inconsistent.** dev ≥ 2 AND idle ≥ 300 s: test +3.8% (n=78); train −2%. |
| Model, sell after the 2nd outside buy, end of slot (sk2_10s_eos) | **Strong.** Top 1%: test +7.1% / median +5.2%, win 68%, PF 5.2 (n=91). Top 2%: +6.9% (n=151). All 5 periods positive. |
| Model, sell after the 1st outside buy (sk1_10s_eos) | **Strong.** Top 1%: test +12.2% / +11.5%, win 83% (n=30). Top 2%: +8.9%, win 69% (n=93). |
| Model, sell after 3 s | **Strong.** Top 0.5%: test +12.6% / +6.9% (n=48). Periods +16 / +21 / +14 / +15 / +12%. |
| Model fsell_30s_eos (already in the paper test) | **Consistent at every cut:** top 0.5% +10.4%, top 1% +12.5%, top 2% +9.6%, top 5% +7.3% on test. |
| Size by score (1.5 / 1.0 / 0.5 SOL on the top 0.5% / next 0.5% / next 1%) | **About doubles PnL** on the same 116 test trades: +12.0 SOL vs +5.6 SOL flat (+10.6% on deployed SOL). |

**Added to the forward paper test:**
- S5: model sk2_eos, top 1%.
- S6: model h3s, top 0.5%.
- S7: size by score on the fsell_eos model.

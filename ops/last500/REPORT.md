# LAST-500 SELECTION STUDY — what explains 4yFAz's ~1% selectivity, and does it pay?

Target: 4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3
Question: he attempts ~1% of launches; our filter fires on ~24%. Tightest PRE-BUY selector reproducing his ~1% set, and does being that selective raise EV or cut variance/drawdown OOS?
Data: his real last 505 landed buys (+ full 4,974-buy attempt set incl fails); create-tx features + create-slot-anchored trajectory + econ outcome (entry = floor*1.02, shipped exit ladder, net costs, 0.5 SOL).
Files: his_500.json, feat_500.json, analysis.json (/root/last500). Builds on /root/attempt_filter, /root/mirror, /root/profit_backtest, /root/econ_102.

## HEADLINE
1. He is genuinely, extremely selective — ~1.0% attempt rate (11 of an unbiased 1,141-create sample), confirmed at N=500.
2. His picks are robustly +EV even under OUR mechanical exit: +0.185 R mean, 93% win, +72.6 R total over his last ~500 (n=392 with path). Stable in AND out of the favorable window (+0.184 in / +0.186 out) -> NOT a regime artifact. He chooses wisely.
3. No pre-buy (create-tx) feature reproduces his ~1% tightness. His dev-buy median is only ~1.17 SOL (he fires on plenty of small launches). Pre-buy features (curve dev-buy, vanilla) BOUND his set but are 8-24x looser than his realized rate.
4. His extra tightness is co-snipe / early-flow presence (lift 3.4-4.4, the top separators) — CONTEMPORANEOUS, visible only at/after the create slot, not from the create tx alone.
5. His own selectivity is a VARIANCE/drawdown win at ~equal mean, NOT a mean-EV lift. A different, tighter pre-buy cut we are free to use — raising the curve dev-buy threshold (dev>=3-5 & vanilla) — DOES lift mean EV sharply and also cuts drawdown, and approaches his ~1% coverage.

## STEP 1 — his last-500 landed tape (his_500.json)
- 505 distinct landed mints; create tx recovered for 409; econ outcome for 392. Create-slot span ~97h (4 days), much wider than prior 13h window.
- Entry: delta 0 -> 324, delta 1 -> 85 (always <=1 slot). Same-slot/next-slot every time.
- Curve dev-buy SOL: p25/med/p75 = 0.79/1.17/3.02 (mean 2.58). NOT a high-dev-only buyer.
- Vanilla: 80%. creator_fee==0: 98%.
- Co-snipers in create slot: median 2, mean 2.7, >=1 on 68%.
- Spray: median 1 buy/mint, mean 5.0 (~80% of his buy txs fail Custom-6042 too-late).
- Metadata has image/uri: 62%. Jito tip in the create tx: 20% (the dev's, not his).
- Token peak: median 1.18x, >=2x on 31/392.
- Econ outcome (floor*1.02, shipped ladder, 0.5 SOL): mean +0.1852 R, win 93%, sd 0.213, total +72.6 R, max-DD -0.67 R. (Prior 13h set +0.176/92% reproduced + extended.)
- NOTE: an earlier pass anchored floor to earliest PATH print and got a spurious -0.05 R. Correct floor = create-tx dev-buy price (econ_102 convention); gives +0.185 and is stable across the window. Fixed in his_500.json.

## STEP 2 — selectivity decomposition (attempted vs passed-our-filter-but-ignored)
Population = unbiased 1/16 create sample (n=1,141, 13h). Attempt rate 11/1141 = 1.0%.
Our filter curve dev>=2 & vanilla fires on 96/1141 = 8%; curve dev>=0.5 & vanilla = 24% (the "~24%").
Of the 276 passing dev>=0.5&vanilla he attempted ~4% — throws away ~96% of our-filter passes.

Feature separation — lift = P(feat|attempted)/P(feat|population), ranked:
| feature | P(att) | P(pop) | lift | pre-buy knowable? |
|---|---|---|---|---|
| cosnipe >= 2 (create slot) | 0.64 | 0.15 | 4.35 | NO — contemporaneous |
| dev-buy >= 3.0 SOL (curve) | 0.36 | 0.09 | 3.99 | YES (create tx) |
| cosnipe >= 1 | 0.64 | 0.19 | 3.42 | NO — contemporaneous |
| dev-buy >= 2.0 SOL | 0.45 | 0.14 | 3.24 | YES |
| dev-buy >= 1.0 SOL | 0.64 | 0.22 | 2.85 | YES |
| dev-buy >= 0.5 SOL | 1.00 | 0.36 | 2.78 | YES |
| vanilla | 0.91 | 0.50 | 1.83 | YES |
| earlyflow n>=3 (slot 0-3) | 1.00 | 0.65 | 1.55 | NO — contemporaneous |
| creator_fee == 0 | 1.00 | 0.94 | 1.07 | YES (no info) |

Logit (attempted ~ standardized dev, vanilla, cosnipe, earlyflow): vanilla +0.71, cosnipe +0.46, earlyflow +0.24, dev-buy +0.05. Once vanilla + co-snipe are in, dev-buy LEVEL adds almost nothing — he keys on vanilla launches that draw a co-snipe, not on big dev-buy.

Tightest pre-buy rules — coverage / recall of his attempt set:
| rule | coverage | recall of his set | trades/hr |
|---|---|---|---|
| dev>=0.5 & vanilla | 24% | 91% | 11.5 |
| dev>=1.0 & vanilla | 14% | 55% | 6.8 |
| dev>=2.0 & vanilla | 8% | 36% | 4.0 |
| dev>=3.0 & vanilla | 6% | 36% | 2.7 |
| dev>=5.0 & vanilla | 2% | keeps 9% of his | 1.0 |
(Precision ~4-6% throughout is a sampling artifact: only 11 of his attempts fall in the 1/16 sample. Recall/coverage are the sound metrics.)

Conclusion: the only create-tx features that bound his picks are dev-buy and vanilla, and the loosest cut recalling his set (dev>=0.5&vanilla) still fires 24x his rate. The residual tightening to 1% is co-snipe/early-flow, which is contemporaneous. NO purely pre-buy feature explains his 1%. (Matches prior 13h finding at 2.7x the sample.)

## STEP 3 — does selectivity help? (population, econ_102 ladder, 0.5 SOL, chronological OOS split)
| rule | n | mean R | win | total R | sd | max-DD | trades/hr | VAL mean | VAL win |
|---|---|---|---|---|---|---|---|---|---|
| dev>=0.5 & vanilla (~24%) | 276 | +0.182 | 68% | +50.1 | 0.413 | -0.59 | 11.5 | +0.163 | 65% |
| dev>=1.0 & vanilla | 163 | +0.237 | 73% | +38.6 | 0.489 | -0.59 | 6.8 | +0.220 | 70% |
| dev>=2.0 & vanilla (broad actionable) | 96 | +0.358 | 77% | +34.3 | 0.593 | -0.44 | 4.0 | +0.337 | 73% |
| dev>=3.0 & vanilla | 64 | +0.488 | 81% | +31.2 | 0.673 | -0.41 | 2.7 | +0.487 | 81% |
| dev>=5.0 & vanilla (~his ~1-2% coverage) | 23 | +1.090 | 91% | +25.1 | 0.786 | -0.05 | 1.0 | +1.078 | 92% |
| dev>=1 & vanilla & cosnipe>=1 (~his profile) | 78 | +0.179 | 91% | +14.0 | 0.208 | -0.59 | 3.3 | +0.159 | 87% |
| dev>=3 & vanilla & cosnipe>=1 (tightest) | 37 | +0.223 | 89% | +8.3 | 0.234 | -0.41 | 1.6 | +0.188 | 89% |
| HIS ACTUAL LAST-500 (our ladder) | 392 | +0.185 | 93% | +72.6 | 0.213 | -0.67 | — | — | — |

Two meanings of "selective", pointing opposite ways:
- Raising the pre-buy dev-buy threshold (dev>=2 -> 3 -> 5, vanilla): mean R +0.358 -> +0.488 -> +1.09, win 77 -> 81 -> 91%, DD -0.44 -> -0.41 -> -0.05. A mean-EV lift AND a variance/drawdown win at once; holds OOS in-window. dev>=5&vanilla ~ 1 trade/hr = his selectivity. (Caveat: n=23, fat-tail-driven, in-window regime.)
- Copying HIS actual rule (median-dev + co-snipe gate): +0.179 R ~ his +0.185, win 91%, sd 0.208 (lowest). Vs broad dev>=2 this is LOWER mean but far higher win and ~3x lower variance. His selectivity cuts variance at equal/lower mean, ~20x fewer trades than the loosest filter -> far less fee-bleed and no-runner exposure.

So tighter != automatically higher mean. His own tightness is a variance play; the mean-EV lever is the dev-buy LEVEL, which he does not lean on.

## STEP 4 — VERDICT + CONFIG
1. His actual selector (co-snipe gating at median dev) is a VARIANCE/DRAWDOWN win, not a mean-EV lift. dev>=1 & vanilla & cosnipe>=1 reproduces his profile: +0.179 R, 91% win, sd 0.208, ~3/hr. Same mean as him, ~3x lower variance than our broad filter. But cosnipe>=1 is CONTEMPORANEOUS — usable only if we watch the create slot/block for other snipers before sending.
2. Best PRE-BUY-knowable selector to approach his ~1%: curve dev-buy >= 5 SOL & vanilla — coverage ~2% / ~1 trade/hr (= his rate), mean +1.09 vs broad dev>=2 +0.358 (~3x EV lift), win 91% vs 77%, max-DD -0.05 vs -0.44 (EV lift AND variance win), OOS-stable in-window. Robust higher-n version: dev>=3 & vanilla (+0.488, 81%, 2.7/hr). HONESTY: this is NOT his rule (he keeps only 9% of his own picks at dev>=5; median 1.17); it is a different, higher-EV cut we are free to adopt; n small; absolute +EV is favorable-window — only the ORDERING is robust.
3. If strictly pre-buy (create-tx only), no feature reproduces his 1%. Tightest honest approximation is a dev-buy threshold + vanilla; to get from 24% toward 1% you raise the curve dev-buy cut, which is also the EV lever.

ACTIONABLE FIX that dominates (carried from prior work, reconfirmed): production reads dev-buy from the buy-ix WIRE (max_sol_cost), so most accepted names are u64::MAX "unbounded cap" SENTINELS whose true dev-buy is tiny and which are net LOSERS. Gate on CURVE-TRUTH dev-buy (bonding-curve SOL delta in create tx) — the quantity he effectively keys on — keep vanilla, set threshold by EV-vs-coverage:
- max mean-EV + min drawdown, his-level selectivity: curve dev>=5 & vanilla (~1/hr, +1.09 R, 91%, DD -0.05)
- robust higher-n: curve dev>=3 & vanilla (2.7/hr, +0.488 R, 81%)
- mirror his variance profile (needs create-slot co-snipe observation): dev>=1 & vanilla & cosnipe>=1 (3/hr, +0.179 R, 91%, sd 0.208)

Owner thesis "same creators / he chooses wisely": he DOES choose wisely — the wisdom is same-slot entry on vanilla launches that attract a co-snipe/bundle (93% win / low variance). NOT a creator whitelist (prior: 14-23% recall, no EV, never self-deploys) and NOT a bigger-dev screen (median dev small). Copying him lowers variance at his mean; out-earning him per-trade needs a TIGHTER dev cut than he uses.

### Caveats (brutal honesty)
- Absolute +EV is on/near the favorable regime; disjoint later windows have gone -EV in prior tests. The ORDERING (curve-dev >> wire-sentinel; dev-LEVEL -> mean; co-snipe -> win/variance) is the robust, portable result, not the point estimates.
- dev>=5 cut rests on n=23 (fat-tail-driven); treat +1.09 as directional.
- Precision of any attempt-rule is a 1/16-sampling artifact (11 of his in the sample); recall/coverage are sound.
- co-snipe/early-flow are contemporaneous; a create-tx-only gate cannot reach his 1% — that tightness is timing/flow selection, not a static screen.
- Single wallet, 4-day landed tape (505) + 13h unbiased outcome population; his realized PnL uses his actual discretionary exits (prior mirror: +0.078 R); our ladder figure (+0.185) is our-engine-on-his-picks, create-tx-floor anchored.

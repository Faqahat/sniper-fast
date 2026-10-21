# Non-bundle create-time signals: what else picks winners? (2026-10-21)

Follow-up to FILTERS.md (bundle size, tip, dev buy, host, create time, leader class are not repeated here). Same landing model, same 932 launches, plus 252 new launches from today's live paper log (period D, 10:13–12:37 UTC).

## Summary

- **One strong signal: the creator's own track record (REP).** 26–42% of the launches we watch come from a creator we have already watched (in our gapped logs). If that creator's earlier launches made money on our model (sum of their S+2 PnL > 0), the next launch also tended to make money.
  - Per launch: **+0.112 (A, 26 launches), +0.077 (B, 38), +0.065 (C, 3), +0.045 (D, 45) SOL**. Win rate 49–67%. Positive with a 20 ms slower landing in every period, and without the best 3 launches in A, B and D (C has only 3). Positive in 10 of the 12 logs that had any.
  - Out of sample (B+C+D): **+0.060 SOL per launch, 90% interval +0.033 to +0.093** (86 launches, 32 creators; the interval resamples creators).
  - The opposite also holds: a creator whose earlier launches were net zero or negative lost **−0.026 / −0.044 / −0.011 / −0.035 per launch** (out of sample −0.040, interval −0.049 to −0.032, 209 launches). Negative in all 12 logs.
  - **Frozen-list test** (the way a cache would be used): good/bad creator lists built only from launches before 10:13 today, applied unchanged to today's D: good-list creators **36 launches, +0.062 each (+2.22 SOL)**; bad-list creators 46 launches, −0.035 each; never-seen creators 170, −0.012 each.
  - **It is a market effect, not only a model effect (measured).** REP launches got a median 1.2–3.1 SOL of outside buys in S..S+2, against 0.1–0.3 for bad-history creators. Their price at the end of S+2 was ≥ 1.1x the post-bundle price in 31–63% of launches, against 6–13%. A model-free version of the rule (the creator's last launch rose ≥ 10% by the end of S+2) is also positive in all four periods.
- **Inside rule #2, nothing non-bundle helps.**
  - Reputation does not split rule #2: first-time creators did as well as REP creators. Skipping bad-history creators keeps 37 of 48 out-of-sample rule #2 launches and changes the out-of-sample total from +1.98 to +1.99 SOL.
  - The create tx inside rule #2 is one tool's fingerprint: 63 of 67 rule #2 launches have identical j7tracker defaults (cu 333333/300000, 15 keys, 6 instructions, 1 lookup table, 0.0025 SOL Lunar transfer). No create-tx field can separate its winners from its losers.
  - Text (name/symbol/URI/keywords), dev-buy amount, regime and hour: no split that holds across periods.
  - Rule #2 itself was near break-even today: D 16 launches, **+0.007 SOL each** (A +0.133, B +0.058).
- **REP adds profitable launches outside rule #2.** REP launches that rule #2 does not take: **+0.103 (A, 20), +0.082 (B, 30), +0.058 (C, 2), +0.055 (D, 37)** per launch, about 9–15 launches/h (2.4/h in the quiet C morning). Out of sample **+0.067 per launch (interval +0.038 to +0.101, n = 69)**.
  - Rule #2 OR REP: A 39 launches +4.58 SOL, B 61 +4.25, C 3 +0.20, **D 53 +2.16 (rule #2 alone: 16, +0.11)**.
- **Bad history is a useful SKIP for the wider triggers.** For C7 (no-bundle Harmonic) it removed 29 launches in A, B and D with just 1 winner among them (+0.24 / +0.58 / +0.28 SOL). For C6's added launches it helped in A/B but not today (C6 added launches lost −0.035 each today either way).
- **Leader skip list: real but small.** Five leaders chosen on A (CMPSSdrT and 3JotfSFP on BAM, CQdLgwkm and DrifTrN9 on Harmonic, EvnRmnMr "other") lose out of sample too: −0.025 (B, 64 launches) and −0.040 (D, 39) per launch. They touch only 2 rule #2 launches out of sample. C8Bey3LK is not bad on the model (+0.016 to +0.118 per launch); the model has no leader-specific latency, so this cannot settle whether it is slow for us.
- **On-chain creator history (public RPC) adds little.** Wallet prior tx count, the creator's earlier pump.fun trading (their creator-vault PDA: trades on their earlier coins) and the wallet's first funder do not split launches consistently.
  - The only consistent one is weak: wallets created < 10 min before the create did slightly worse, −0.040 / −0.007 / −0.057 / −0.016 per launch (A/B/C/D) against +0.031 / +0.006 / +0.017 / −0.000 for older wallets (out of sample −0.013 vs +0.004, 113 vs 360 launches). Only 1 rule #2 creator had such a fresh wallet.
  - Funder reputation does not extend REP to first-time creators. One funder (5tzFkiKs…) funded 79 of our 815 creators, about break-even.
  - Caveat: publicnode keeps only ~23 h of address history, so ages and funders of older wallets are approximate.

## Recommendation

- **Paper-test REP now (zero cost), alongside rule #2.**
  - Fire on any watched launch (base filter + close leader) whose creator's earlier watched launches are net positive on the model. The creator list is a cache refreshed by the recorder after each launch settles (~1–2 min). At fire time it is one hash lookup on the creator, so there is no added latency (sketch below).
  - Promote to live only if paper shows **≥ +0.03 SOL per REP launch over ≥ 60 REP launches** (and the +20 ms column stays positive).
  - Confidence: **medium**. It holds in all four periods, in a frozen-list test on today's data, and on a model-free check. But n is 112 launches from 39 creators, and these launch shapes have no measured landing time.
- **Use "bad history" as a skip on any wider trigger** (C6/C7) if one is promoted. Confidence medium; it is cheap.
- **Leave rule #2 unchanged.** No non-bundle signal improves it (confidence medium-high, but rule #2's n is small).
- Optional: add the five-leader skip list to the wider triggers only. Low value for rule #2.
- Text, create-tx details and regime: nothing to implement.

## How it was measured

- **Launches and model.** The same 932 watched launches as FILTERS.md (groups A/B/C: base filter + close leader, priced on the unchanged landing model: landing time per leader type, real block order, 85% cap, all fees, sell at the end of S+2), plus **252 new launches from today's live paper engine log after period C** (group **D**, 10-21 10:13–12:37 UTC, 2.4 h). D was priced with the same `filters.py` code from the paper loop's cached block recordings (`paper_rows.py`, no RPC). A new rule #2 total for D (16 launches, +0.11 SOL) matches the paper loop's own tally (rule #2 17 launches +0.190 including C's one launch at +0.08).
- **Periods.** A = in-sample (10-20 evening). B, C and D are out-of-sample. Nothing in this study was tuned on B, C or D. The reputation rule uses the natural threshold 0 (not tuned); every variant I tried is shown in table 1e, and the leader skip list is the only thing chosen on A.
- **Signals (all known at create time):**
  1. **Creator reputation from our own launches (REP).** For each launch: every EARLIER watched launch by the same creator (any log, strictly before this one), with its modelled S+2 PnL. REP = the creator has at least one earlier launch and their sum is > 0. "Bad history" = at least one earlier launch and a sum ≤ 0. "First-time" = no earlier launch in our logs. The closest earlier launch of the same creator was more than 2 minutes earlier in 106 of the 112 REP launches (median 29 min), so its S+2 result was settled and could have been priced by then.
     - Model-free variant: the creator's last earlier launch's own market response (price at the end of S+2 ÷ price just after the creator's bundle ≥ 1.1x), and the outside-buy SOL it got in S..S+2.
  2. **On-chain creator history (public RPC, `creator_hist.py`).** For each creator wallet, all signatures (up to 4,000) and, for each launch, only the ones BEFORE the create slot: prior tx count and wallet age; the wallet's first funder (the account whose SOL fell the most in the wallet's first tx); and the creator's pump.fun creator-vault PDA (`["creator-vault", creator]`), whose signatures before the create tx are the trades on the creator's EARLIER pump.fun coins (every pump buy/sell pays the creator fee there). Funder reputation = the same REP sum over earlier launches of creators with the same first funder.
  3. **Text:** name length, symbol all-caps, symbol = name, digits, non-ASCII, metadata URI pattern, four keyword families (AI/bot, politics, animal, coin/money).
  4. **Create-tx details:** dev buy amount (multiple of 0.5 SOL or not) and kind, cu_price/cu_limit, size of the largest create transfer, lookup table / v1 / Token-2022, instruction count, signer count.
  5. **Leader identity:** a skip list chosen on A (leaders with ≥ 5 watched launches in A and a mean below −0.02 SOL), tested on B/C/D.
  6. **Regime:** creates the engine saw (DETECT first=1) per minute in the 10 minutes before the create, and UTC hour.
- **Columns** as in FILTERS.md: n, launches/h, distinct creators, total S+2 PnL (SOL), per launch (mean), median, win rate (PnL > 0), worst launch, total if we land 20 ms later, total without the 3 best launches. The bootstrap resamples **creators** (not launches), because one creator's launches are correlated.

## Tables

Groups: A = in-sample (10-20 evening), B = older + overnight, C = 10-21 morning to 10:13, D = today's live paper log 10:13–12:37 UTC. B, C, D are out-of-sample. All PnL in SOL on the realistic landing model (1.5 SOL buy, sell at the end of S+2).

### Data per period

| group | hours | watched launches | /h | rule #2 | /h | distinct creators | launches by a creator seen before (in our logs) |
|---|---|---|---|---|---|---|---|
| A | 1.55 | 325 | 210 | 19 | 12.3 | 267 | 96 (30%) |
| B | 3.40 | 553 | 163 | 31 | 9.1 | 392 | 175 (32%) |
| C | 0.83 | 54 | 65 | 1 | 1.2 | 54 | 14 (26%) |
| D | 2.42 | 252 | 104 | 16 | 6.6 | 178 | 106 (42%) |

### 1a. Creator reputation from OUR OWN earlier launches, all watched launches

Reputation = the sum of the modelled S+2 PnL of the same creator's EARLIER watched launches (any log, strictly before this launch). The creator's previous launch was more than 2 min earlier for 106 of the 112 REP launches (median 29 min), so its S+2 result was settled; REP restricted to those 106 gives +0.121 / +0.083 / +0.065 / +0.047 per launch (A/B/C/D).

| variant | grp | n | /h | creators | PnL S+2 | per launch | median | win | worst | +20 ms S+2 | S+2 w/o best 3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all watched | A | 325 | 209.8 | 267 | -0.13 | -0.000 | -0.049 | 24% | -0.53 | -5.99 | -3.09 |
|  | B | 553 | 162.7 | 392 | +2.63 | +0.005 | -0.042 | 27% | -0.50 | -4.23 | +0.14 |
|  | C | 54 | 65.4 | 54 | +2.12 | +0.039 | -0.050 | 19% | -0.33 | +1.80 | -1.45 |
|  | D | 252 | 104.2 | 178 | -1.37 | -0.005 | -0.038 | 27% | -0.63 | -4.00 | -4.05 |
| first time we see the creator | A | 229 | 147.8 | 229 | -1.26 | -0.005 | -0.050 | 21% | -0.53 | -5.11 | -3.80 |
|  | B | 378 | 111.2 | 378 | +5.78 | +0.015 | -0.038 | 28% | -0.26 | +0.15 | +3.29 |
|  | C | 40 | 48.5 | 40 | +2.05 | +0.051 | -0.050 | 12% | -0.33 | +1.77 | -1.52 |
|  | D | 146 | 60.4 | 146 | -1.26 | -0.009 | -0.043 | 27% | -0.63 | -2.28 | -3.44 |
| creator seen before, earlier launches net POSITIVE (REP) | A | 26 | 16.8 | 16 | +2.92 | +0.112 | +0.014 | 65% | -0.26 | +1.86 | +0.76 |
|  | B | 38 | 11.2 | 22 | +2.94 | +0.077 | +0.042 | 58% | -0.12 | +2.34 | +1.76 |
|  | C | 3 | 3.6 | 3 | +0.20 | +0.065 | +0.080 | 67% | -0.02 | +0.20 | +0.00 |
|  | D | 45 | 18.6 | 16 | +2.04 | +0.045 | -0.010 | 49% | -0.41 | +0.80 | +0.39 |
| creator seen before, earlier launches net zero/negative | A | 70 | 45.2 | 44 | -1.80 | -0.026 | -0.050 | 19% | -0.12 | -2.74 | -2.31 |
|  | B | 137 | 40.3 | 61 | -6.09 | -0.044 | -0.050 | 15% | -0.50 | -6.71 | -6.43 |
|  | C | 11 | 13.3 | 11 | -0.12 | -0.011 | -0.044 | 27% | -0.10 | -0.17 | -0.40 |
|  | D | 61 | 25.2 | 33 | -2.14 | -0.035 | -0.044 | 13% | -0.56 | -2.52 | -2.77 |

### 1b. The same split inside rule #2

| variant | grp | n | /h | creators | PnL S+2 | per launch | median | win | worst | +20 ms S+2 | S+2 w/o best 3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rule #2 | A | 19 | 12.3 | 14 | +2.52 | +0.133 | -0.011 | 47% | -0.26 | +1.41 | -0.12 |
|  | B | 31 | 9.1 | 22 | +1.79 | +0.058 | -0.030 | 35% | -0.11 | +1.30 | +0.09 |
|  | C | 1 | 1.2 | 1 | +0.08 | +0.080 | +0.080 | 100% | +0.08 | +0.08 | +0.00 |
|  | D | 16 | 6.6 | 10 | +0.11 | +0.007 | -0.018 | 38% | -0.41 | -0.11 | -0.52 |
| rule #2, first-time creator | A | 8 | 5.2 | 8 | +1.51 | +0.189 | +0.012 | 50% | -0.05 | +0.59 | -0.13 |
|  | B | 16 | 4.7 | 16 | +1.50 | +0.094 | -0.031 | 38% | -0.11 | +1.31 | -0.13 |
|  | C | 0 | - | - | - | - | - | - | - | - | - |
|  | D | 4 | 1.7 | 4 | -0.06 | -0.016 | -0.051 | 25% | -0.05 | -0.07 | -0.05 |
| rule #2, REP creator | A | 6 | 3.9 | 4 | +0.87 | +0.144 | +0.021 | 50% | -0.26 | +1.06 | -0.32 |
|  | B | 8 | 2.4 | 6 | +0.48 | +0.060 | -0.011 | 38% | -0.04 | +0.25 | -0.11 |
|  | C | 1 | 1.2 | 1 | +0.08 | +0.080 | +0.080 | 100% | +0.08 | +0.08 | +0.00 |
|  | D | 8 | 3.3 | 4 | -0.01 | -0.001 | -0.017 | 38% | -0.41 | -0.22 | -0.54 |
| rule #2, creator with net zero/negative history | A | 5 | 3.2 | 5 | +0.14 | +0.028 | -0.050 | 40% | -0.06 | -0.25 | -0.12 |
|  | B | 7 | 2.1 | 4 | -0.19 | -0.027 | -0.050 | 29% | -0.06 | -0.25 | -0.21 |
|  | C | 0 | - | - | - | - | - | - | - | - | - |
|  | D | 4 | 1.7 | 4 | +0.18 | +0.046 | +0.014 | 50% | -0.05 | +0.18 | -0.05 |
| rule #2 SKIPPING creators with net zero/negative history | A | 14 | 9.0 | 11 | +2.38 | +0.170 | +0.014 | 50% | -0.26 | +1.65 | -0.27 |
|  | B | 24 | 7.1 | 19 | +1.98 | +0.083 | -0.011 | 38% | -0.11 | +1.56 | +0.28 |
|  | C | 1 | 1.2 | 1 | +0.08 | +0.080 | +0.080 | 100% | +0.08 | +0.08 | +0.00 |
|  | D | 12 | 5.0 | 8 | -0.07 | -0.006 | -0.035 | 33% | -0.41 | -0.29 | -0.61 |

### 1c. REP as an ADDITIONAL trigger (outside rule #2) and combined

| variant | grp | n | /h | creators | PnL S+2 | per launch | median | win | worst | +20 ms S+2 | S+2 w/o best 3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| REP minus rule #2 (added launches) | A | 20 | 12.9 | 13 | +2.06 | +0.103 | +0.014 | 70% | -0.05 | +0.79 | +0.47 |
|  | B | 30 | 8.8 | 19 | +2.46 | +0.082 | +0.045 | 63% | -0.12 | +2.09 | +1.38 |
|  | C | 2 | 2.4 | 2 | +0.12 | +0.058 | +0.058 | 50% | -0.02 | +0.12 | +0.00 |
|  | D | 37 | 15.3 | 15 | +2.05 | +0.055 | +0.006 | 51% | -0.05 | +1.03 | +0.48 |
| REP minus rule #2, create <=150 ms | A | 15 | 9.7 | 9 | +1.33 | +0.089 | +0.009 | 67% | -0.05 | +0.07 | +0.02 |
|  | B | 17 | 5.0 | 12 | +1.95 | +0.115 | +0.085 | 71% | -0.03 | +1.78 | +0.92 |
|  | C | 1 | 1.2 | 1 | +0.14 | +0.135 | +0.135 | 100% | +0.14 | +0.14 | +0.00 |
|  | D | 25 | 10.3 | 12 | +1.20 | +0.048 | +0.013 | 60% | -0.05 | +0.42 | +0.25 |
| rule #2 OR REP | A | 39 | 25.2 | 26 | +4.58 | +0.117 | +0.010 | 59% | -0.26 | +2.20 | +1.93 |
|  | B | 61 | 17.9 | 38 | +4.25 | +0.070 | -0.008 | 49% | -0.12 | +3.39 | +2.42 |
|  | C | 3 | 3.6 | 3 | +0.20 | +0.065 | +0.080 | 67% | -0.02 | +0.20 | +0.00 |
|  | D | 53 | 21.9 | 22 | +2.16 | +0.041 | -0.010 | 47% | -0.41 | +0.92 | +0.51 |
| rule #2 OR (REP and create <=150 ms) | A | 34 | 21.9 | 22 | +3.85 | +0.113 | +0.009 | 56% | -0.26 | +1.48 | +1.20 |
|  | B | 48 | 14.1 | 33 | +3.75 | +0.078 | -0.010 | 48% | -0.11 | +3.08 | +1.91 |
|  | C | 2 | 2.4 | 2 | +0.22 | +0.108 | +0.108 | 100% | +0.08 | +0.22 | +0.00 |
|  | D | 41 | 17.0 | 19 | +1.31 | +0.032 | +0.006 | 51% | -0.41 | +0.31 | +0.27 |

### 1d. Per-launch S+2 PnL: mean with a bootstrap 90% interval (resampling CREATORS, 2000x)

| variant | A | B | C | D | B+C+D (out of sample) |
|---|---|---|---|---|---|
| rule #2 | +0.133 [+0.000, +0.273] n=19 | +0.058 [-0.004, +0.136] n=31 | n=1 | +0.007 [-0.047, +0.066] n=16 | +0.041 [-0.001, +0.091] n=48 |
| REP | +0.112 [+0.039, +0.219] n=26 | +0.077 [+0.045, +0.116] n=38 | +0.065 [+0.014, +0.117] n=3 | +0.045 [-0.001, +0.092] n=45 | +0.060 [+0.033, +0.093] n=86 |
| REP minus rule #2 | +0.103 [+0.037, +0.219] n=20 | +0.082 [+0.046, +0.126] n=30 | +0.058 [-0.020, +0.135] n=2 | +0.055 [+0.013, +0.105] n=37 | +0.067 [+0.038, +0.101] n=69 |
| creator history net zero/negative | -0.026 [-0.038, -0.012] n=70 | -0.044 [-0.055, -0.035] n=137 | -0.011 [-0.044, +0.029] n=11 | -0.035 [-0.057, -0.014] n=61 | -0.040 [-0.049, -0.032] n=209 |
| first-time creator | -0.005 [-0.022, +0.012] n=229 | +0.015 [+0.004, +0.028] n=378 | +0.051 [-0.040, +0.187] n=40 | -0.009 [-0.030, +0.015] n=146 | +0.012 [-0.001, +0.026] n=564 |
| rule #2 OR REP | +0.117 [+0.045, +0.208] n=39 | +0.070 [+0.030, +0.111] n=61 | +0.065 [+0.014, +0.117] n=3 | +0.041 [+0.002, +0.079] n=53 | +0.056 [+0.029, +0.084] n=117 |

### 1e. Variants of the reputation rule (all watched launches)

| variant | A: n, per launch, total | B: n, per launch, total | C: n, per launch, total | D: n, per launch, total |
|---|---|---|---|---|
| REP: earlier launches net positive (sum) | 26, +0.112, +2.92 | 38, +0.077, +2.94 | 3, +0.065, +0.20 | 45, +0.045, +2.04 |
| last earlier launch positive | 29, +0.102, +2.95 | 39, +0.057, +2.23 | 2, +0.030, +0.06 | 31, +0.021, +0.65 |
| earlier launches net > +0.05 SOL | 25, +0.118, +2.96 | 29, +0.101, +2.94 | 2, +0.058, +0.12 | 43, +0.043, +1.85 |
| MODEL-FREE: last earlier launch's price at end of S+2 >= 1.1x its post-bundle price | 23, +0.133, +3.06 | 38, +0.055, +2.08 | 3, +0.100, +0.30 | 23, +0.033, +0.76 |
| MODEL-FREE: last earlier launch's price < 1.1x | 73, -0.027, -1.94 | 137, -0.038, -5.23 | 11, -0.021, -0.23 | 83, -0.010, -0.87 |
| MODEL-FREE: an earlier launch got >= 2 SOL outside buys in S..S+2 | 35, +0.087, +3.05 | 57, +0.007, +0.42 | 6, +0.054, +0.32 | 51, +0.033, +1.71 |
| REP, 1 earlier launch | 11, +0.169, +1.86 | 15, +0.165, +2.47 | 1, -0.020, -0.02 | 3, -0.016, -0.05 |
| REP, 2-3 earlier launches | 8, +0.175, +1.40 | 17, +0.035, +0.60 | 0 | 11, -0.012, -0.13 |
| REP, 4+ earlier launches | 7, -0.048, -0.33 | 6, -0.022, -0.13 | 2, +0.108, +0.22 | 31, +0.071, +2.21 |
| REP, no bundle | 7, +0.213, +1.49 | 8, +0.095, +0.76 | 0 | 14, +0.062, +0.87 |
| REP, bundle 2-5 SOL | 9, +0.097, +0.87 | 22, +0.058, +1.28 | 3, +0.065, +0.20 | 30, +0.040, +1.21 |
| REP, bundle > 5 SOL | 9, +0.006, +0.05 | 8, +0.113, +0.90 | 0 | 0 |
| REP, Harmonic leader | 13, +0.129, +1.67 | 19, +0.139, +2.64 | 2, +0.058, +0.12 | 15, +0.091, +1.36 |
| REP, Jito-client leader | 8, +0.174, +1.40 | 12, +0.002, +0.03 | 1, +0.080, +0.08 | 26, +0.029, +0.76 |
| REP, BAM leader | 3, -0.065, -0.19 | 5, +0.056, +0.28 | 0 | 1, -0.031, -0.03 |
| REP, create > 150 ms | 5, +0.145, +0.73 | 13, +0.039, +0.51 | 1, -0.020, -0.02 | 12, +0.070, +0.85 |

REP with other exits/landing (per launch): A: sell at end of S+1 +0.102, S+2 landing +20 ms +0.071; B: sell at end of S+1 +0.069, S+2 landing +20 ms +0.061; C: sell at end of S+1 +0.048, S+2 landing +20 ms +0.065; D: sell at end of S+1 +0.034, S+2 landing +20 ms +0.018

### 1f. Model-free check: the launch's own market response in S..S+2 (price at end of S+2 / post-bundle price)

| set | grp | n | median price ratio | share >= 1.1x | median outside buy SOL S..S+2 |
|---|---|---|---|---|---|
| REP | A | 26 | 1.05 | 31% | 1.36 |
|  | B | 38 | 1.15 | 63% | 3.06 |
|  | C | 3 | 1.10 | 33% | 1.78 |
|  | D | 45 | 1.07 | 33% | 1.22 |
| creator history net zero/negative | A | 70 | 1.01 | 13% | 0.29 |
|  | B | 137 | 1.00 | 6% | 0.11 |
|  | C | 11 | 1.00 | 9% | 0.15 |
|  | D | 61 | 1.01 | 7% | 0.25 |
| first-time creator | A | 229 | 1.01 | 25% | 0.21 |
|  | B | 378 | 1.02 | 28% | 0.41 |
|  | C | 40 | 1.00 | 18% | 0.14 |
|  | D | 146 | 1.01 | 21% | 0.37 |

### 1g. Frozen list: good/bad creator lists built from earlier periods only, applied unchanged later

| variant | grp | n | /h | creators | PnL S+2 | per launch | median | win | worst | +20 ms S+2 | S+2 w/o best 3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| list from A+B+C (10-20 12:40 .. 10-21 10:13) -> D (today): good-list creators (164) | D | 36 | 14.9 | 12 | +2.22 | +0.062 | +0.013 | 56% | -0.41 | +1.01 | +0.57 |
| same, not rule #2 | D | 29 | 12.0 | 11 | +2.17 | +0.075 | +0.013 | 59% | -0.05 | +1.15 | +0.60 |
| bad-list creators (483) | D | 46 | 19.0 | 20 | -1.61 | -0.035 | -0.039 | 13% | -0.56 | -2.00 | -2.24 |
| creators not on either list | D | 170 | 70.3 | 146 | -1.98 | -0.012 | -0.045 | 25% | -0.63 | -3.02 | -4.16 |
| list from A only (10-20 evening) -> later logs (edge3, edge5, night, morning, today): good-list creators (64) | B+C+D | 16 | 3.4 | 10 | +1.30 | +0.081 | +0.017 | 56% | -0.12 | +1.05 | +0.09 |
| same, not rule #2 | B+C+D | 15 | 3.2 | 9 | +1.34 | +0.089 | +0.021 | 60% | -0.12 | +1.11 | +0.13 |
| bad-list creators (203) | B+C+D | 70 | 15.0 | 24 | -3.08 | -0.044 | -0.048 | 19% | -0.50 | -3.37 | -3.38 |
| creators not on either list | B+C+D | 399 | 85.6 | 303 | +3.73 | +0.009 | -0.041 | 28% | -0.63 | -0.95 | -1.09 |

### 1h. Per log (n: S+2 PnL SOL); A = dry1h + run1, B = cov..night, C = morning, D = today

| variant | dry1h | run1 | cov | alt | cad | edge1 | latest | edge2 | edge3 | edge5 | night | morning | today |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rule #2 | 14: +0.90 | 5: +1.62 | 0 | 6: +0.63 | 0 | 4: +0.32 | 7: +0.07 | 9: +0.87 | 1: -0.01 | 1: -0.06 | 3: -0.01 | 1: +0.08 | 16: +0.11 |
| REP | 20: +1.80 | 6: +1.13 | 0 | 1: -0.01 | 3: -0.02 | 1: +0.34 | 6: +0.86 | 11: +1.19 | 7: +0.33 | 2: +0.17 | 7: +0.08 | 3: +0.20 | 45: +2.04 |
| REP minus rule #2 | 17: +1.94 | 3: +0.11 | 0 | 1: -0.01 | 3: -0.02 | 0 | 5: +0.70 | 8: +1.12 | 6: +0.34 | 2: +0.17 | 5: +0.16 | 2: +0.12 | 37: +2.05 |
| creator history net zero/negative | 44: -1.01 | 26: -0.78 | 0 | 7: -0.28 | 4: -0.14 | 7: -0.11 | 20: -0.78 | 29: -1.52 | 27: -0.92 | 7: -0.34 | 36: -2.00 | 11: -0.12 | 61: -2.14 |

### 1i. Concentration: REP launches per creator (top 5 by S+2 total, per group)

- A: 16 creators, total +2.92; top: DWHEZ8 2x +1.06, DBc7UX 1x +0.58, AqwxK9 1x +0.50, GuAKE5 1x +0.50, 49fAsU 2x +0.17; total without the best creator +1.86
- B: 22 creators, total +2.94; top: 6aoG8G 2x +0.60, 5zwN9N 3x +0.53, FiwwHe 1x +0.48, 5RQ1UW 4x +0.23, 49fAsU 1x +0.20; total without the best creator +2.34
- C: 3 creators, total +0.20; top: GeUnv1 1x +0.14, DqeVuN 1x +0.08, 866Srs 1x -0.02; total without the best creator +0.06
- D: 16 creators, total +2.04; top: DWHEZ8 1x +0.84, DqeVuN 6x +0.70, GeUnv1 8x +0.55, 6aoG8G 3x +0.48, 4devFP 1x +0.15; total without the best creator +1.20

### 1j. Bad history as a SKIP on the wider triggers of FILTERS.md (C6 added launches, C7 no-bundle Harmonic)

| variant | grp | n | /h | creators | PnL S+2 | per launch | median | win | worst | +20 ms S+2 | S+2 w/o best 3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C6 added (any tip, bundle 2-5, <=150 ms, not rule #2) | A | 32 | 20.7 | 29 | +0.37 | +0.012 | -0.034 | 22% | -0.06 | -0.82 | -0.81 |
|  | B | 67 | 19.7 | 51 | +0.95 | +0.014 | -0.021 | 34% | -0.50 | +0.62 | -0.75 |
|  | C | 8 | 9.7 | 8 | +0.66 | +0.083 | +0.053 | 50% | -0.33 | +0.62 | -0.33 |
|  | D | 38 | 15.7 | 25 | -1.33 | -0.035 | -0.034 | 32% | -0.63 | -1.87 | -2.07 |
| C6 added, skipping bad-history creators | A | 25 | 16.1 | 24 | +0.60 | +0.024 | -0.028 | 24% | -0.06 | -0.40 | -0.58 |
|  | B | 49 | 14.4 | 43 | +2.78 | +0.057 | -0.011 | 43% | -0.18 | +2.45 | +1.08 |
|  | C | 6 | 7.3 | 6 | +0.53 | +0.088 | +0.053 | 50% | -0.33 | +0.49 | -0.41 |
|  | D | 30 | 12.4 | 22 | -1.32 | -0.044 | -0.030 | 37% | -0.63 | -1.58 | -1.86 |
| C7 (no bundle, Harmonic, <=150 ms) | A | 49 | 31.6 | 47 | +2.76 | +0.056 | -0.030 | 35% | -0.05 | +0.77 | +1.19 |
|  | B | 72 | 21.2 | 62 | +1.23 | +0.017 | -0.031 | 33% | -0.19 | +0.65 | +0.24 |
|  | C | 5 | 6.1 | 5 | -0.25 | -0.050 | -0.050 | 0% | -0.05 | -0.25 | -0.10 |
|  | D | 34 | 14.1 | 32 | +0.20 | +0.006 | -0.039 | 32% | -0.45 | -0.18 | -0.49 |
| C7, skipping bad-history creators | A | 43 | 27.8 | 43 | +3.00 | +0.070 | -0.016 | 40% | -0.05 | +1.05 | +1.43 |
|  | B | 57 | 16.8 | 57 | +1.81 | +0.032 | -0.021 | 40% | -0.19 | +1.27 | +0.83 |
|  | C | 5 | 6.1 | 5 | -0.25 | -0.050 | -0.050 | 0% | -0.05 | -0.25 | -0.10 |
|  | D | 26 | 10.8 | 25 | +0.48 | +0.019 | -0.022 | 42% | -0.45 | +0.13 | -0.21 |

### 2a. Text features, all watched launches with create <= 150 ms

| variant | A: n, per launch, total | B: n, per launch, total | C: n, per launch, total | D: n, per launch, total |
|---|---|---|---|---|
| name length <= 5 | 39, +0.005, +0.21 | 59, +0.001, +0.08 | 4, -0.058, -0.23 | 27, +0.020, +0.53 |
| name length 6-10 | 65, +0.002, +0.10 | 157, +0.015, +2.43 | 9, +0.034, +0.31 | 77, -0.020, -1.55 |
| name length 11-20 | 98, +0.011, +1.08 | 127, +0.017, +2.11 | 15, +0.010, +0.16 | 65, +0.018, +1.16 |
| name length > 20 | 21, +0.016, +0.34 | 27, -0.044, -1.19 | 5, -0.053, -0.27 | 12, -0.036, -0.43 |
| symbol ALL CAPS | 142, -0.012, -1.68 | 242, +0.011, +2.54 | 25, +0.006, +0.15 | 99, +0.003, +0.31 |
| symbol not all caps | 81, +0.042, +3.41 | 128, +0.007, +0.88 | 8, -0.023, -0.18 | 82, -0.007, -0.60 |
| symbol == name | 87, -0.003, -0.25 | 147, +0.002, +0.34 | 9, -0.043, -0.38 | 67, -0.007, -0.48 |
| digits in name/symbol | 14, +0.025, +0.35 | 10, +0.049, +0.49 | 0 | 5, +0.043, +0.21 |
| non-ASCII (emoji, CJK, filler) in name/symbol | 10, -0.001, -0.01 | 13, -0.008, -0.10 | 2, -0.044, -0.09 | 10, -0.024, -0.24 |
| uri j7tracker /metadata/<id>.json | 78, -0.001, -0.10 | 122, +0.010, +1.22 | 10, +0.016, +0.16 | 64, -0.011, -0.74 |
| uri ipfs bafkrei (CIDv1) | 77, -0.002, -0.17 | 133, +0.029, +3.87 | 13, -0.028, -0.37 | 71, +0.016, +1.16 |
| uri ipfs Qm (CIDv0) | 15, +0.012, +0.18 | 32, +0.021, +0.67 | 6, -0.008, -0.05 | 15, +0.026, +0.38 |
| uri uxento | 17, +0.005, +0.09 | 26, -0.051, -1.32 | 2, +0.301, +0.60 | 10, -0.018, -0.18 |
| uri other | 36, +0.048, +1.74 | 57, -0.018, -1.02 | 2, -0.189, -0.38 | 21, -0.044, -0.92 |
| keyword AI/bot | 14, +0.125, +1.75 | 8, -0.020, -0.16 | 4, +0.007, +0.03 | 10, +0.041, +0.41 |
| keyword politics | 2, -0.045, -0.09 | 12, +0.001, +0.02 | 0 | 0 |
| keyword animal | 20, +0.051, +1.02 | 43, -0.010, -0.45 | 6, +0.078, +0.47 | 25, -0.013, -0.32 |
| keyword coin/money | 18, -0.002, -0.03 | 24, +0.030, +0.73 | 0 | 28, +0.065, +1.82 |
| keyword none | 169, -0.005, -0.91 | 283, +0.012, +3.28 | 23, -0.023, -0.53 | 118, -0.019, -2.19 |

### 2b. Text features inside rule #2

| variant | A: n, per launch, total | B: n, per launch, total | C: n, per launch, total | D: n, per launch, total |
|---|---|---|---|---|
| name length <= 5 | 4, +0.215, +0.86 | 5, +0.014, +0.07 | 0 | 2, -0.038, -0.08 |
| name length 6-10 | 4, +0.177, +0.71 | 10, +0.143, +1.43 | 0 | 5, -0.096, -0.48 |
| name length 11-20 | 6, -0.001, -0.00 | 14, +0.021, +0.29 | 1, +0.080, +0.08 | 7, +0.087, +0.61 |
| name length > 20 | 5, +0.191, +0.96 | 2, +0.002, +0.00 | 0 | 2, +0.029, +0.06 |
| symbol ALL CAPS | 12, +0.090, +1.08 | 19, +0.076, +1.45 | 1, +0.080, +0.08 | 8, +0.022, +0.18 |
| symbol not all caps | 7, +0.206, +1.44 | 12, +0.029, +0.34 | 0 | 8, -0.008, -0.07 |
| symbol == name | 7, +0.225, +1.58 | 11, +0.047, +0.51 | 0 | 2, -0.031, -0.06 |
| digits in name/symbol | 1, +0.271, +0.27 | 0 | 0 | 1, -0.052, -0.05 |
| non-ASCII (emoji, CJK, filler) in name/symbol | 1, +0.053, +0.05 | 1, +0.175, +0.18 | 0 | 1, -0.025, -0.02 |
| uri j7tracker /metadata/<id>.json | 17, +0.112, +1.91 | 30, +0.051, +1.52 | 1, +0.080, +0.08 | 15, +0.011, +0.16 |
| uri ipfs bafkrei (CIDv1) | 2, +0.304, +0.61 | 1, +0.271, +0.27 | 0 | 0 |
| uri ipfs Qm (CIDv0) | 0 | 0 | 0 | 0 |
| uri uxento | 0 | 0 | 0 | 1, -0.052, -0.05 |
| uri other | 0 | 0 | 0 | 0 |
| keyword AI/bot | 4, +0.462, +1.85 | 1, -0.093, -0.09 | 0 | 1, -0.010, -0.01 |
| keyword politics | 0 | 1, +0.372, +0.37 | 0 | 0 |
| keyword animal | 2, +0.111, +0.22 | 8, +0.106, +0.85 | 0 | 3, -0.012, -0.03 |
| keyword coin/money | 3, -0.008, -0.02 | 3, -0.014, -0.04 | 0 | 2, +0.111, +0.22 |
| keyword none | 10, +0.047, +0.47 | 18, +0.039, +0.71 | 1, +0.080, +0.08 | 10, -0.007, -0.07 |

### 3a. Create-tx details, all watched launches with create <= 150 ms

| variant | A: n, per launch, total | B: n, per launch, total | C: n, per launch, total | D: n, per launch, total |
|---|---|---|---|---|
| dev buy a multiple of 0.5 SOL | 95, +0.041, +3.91 | 175, +0.013, +2.36 | 18, +0.026, +0.47 | 83, +0.005, +0.39 |
| dev buy any other amount | 128, -0.017, -2.18 | 195, +0.005, +1.06 | 15, -0.034, -0.50 | 98, -0.007, -0.68 |
| dev buy kind 1 (exact SOL in) | 39, +0.058, +2.27 | 68, +0.008, +0.54 | 5, +0.093, +0.47 | 20, +0.049, +0.98 |
| dev buy kind 2 (token amount + SOL cap) | 171, -0.004, -0.65 | 270, +0.009, +2.47 | 22, -0.021, -0.47 | 141, -0.008, -1.16 |
| dev buy kind 3 | 9, +0.006, +0.05 | 28, +0.016, +0.46 | 6, -0.005, -0.03 | 20, -0.006, -0.12 |
| cu 333333 / 300000 (j7tracker default) | 72, +0.013, +0.93 | 122, +0.018, +2.14 | 10, +0.016, +0.16 | 64, -0.012, -0.76 |
| cu_price 0 | 36, -0.025, -0.88 | 67, -0.025, -1.68 | 16, +0.005, +0.08 | 74, +0.005, +0.38 |
| cu_price >= 1,000,000 | 34, +0.069, +2.35 | 48, +0.042, +1.99 | 0 | 5, -0.029, -0.15 |
| largest create transfer 0 | 101, -0.014, -1.39 | 133, -0.003, -0.41 | 8, -0.053, -0.42 | 69, -0.008, -0.56 |
| largest create transfer < 0.0025 | 10, +0.018, +0.18 | 28, -0.031, -0.87 | 3, -0.048, -0.14 | 11, +0.177, +1.95 |
| largest create transfer = 0.0025 (j7 Lunar default) | 46, +0.033, +1.51 | 75, +0.025, +1.91 | 6, +0.016, +0.10 | 35, -0.014, -0.50 |
| largest create transfer 0.0025-0.01 | 23, -0.006, -0.15 | 63, +0.013, +0.84 | 8, -0.018, -0.14 | 26, +0.020, +0.52 |
| largest create transfer > 0.01 | 43, +0.037, +1.58 | 71, +0.027, +1.94 | 8, +0.072, +0.58 | 40, -0.042, -1.69 |
| no lookup table / v1 / Token-2022 (pump create_v2 tools) | 57, -0.029, -1.64 | 87, +0.029, +2.49 | 12, -0.050, -0.60 | 53, -0.013, -0.71 |
| nix >= 7 | 41, +0.004, +0.14 | 65, +0.034, +2.22 | 7, -0.011, -0.08 | 35, +0.025, +0.89 |
| nsig > 2 | 3, -0.048, -0.14 | 8, -0.032, -0.26 | 0 | 0 |

Inside rule #2 the create tx is one tool's fingerprint: of the rule #2 launches, 63 of 67 have cu_price 333333, cu_limit 300000, 15 keys, 6 instructions, 1 lookup table and a 0.0025 SOL Lunar transfer (j7tracker defaults). The rest: B GtNfwP ipfs.io +0.271, A FShDX4 ipfs.io +0.661, A 72K4cK ipfs.io -0.053, D Grorxy uxento -0.052.

### 3b. Dev-buy amount inside rule #2

| variant | A: n, per launch, total | B: n, per launch, total | C: n, per launch, total | D: n, per launch, total |
|---|---|---|---|---|
| dev buy a multiple of 0.5 SOL | 18, +0.143, +2.57 | 27, +0.031, +0.85 | 1, +0.080, +0.08 | 15, +0.011, +0.16 |
| dev buy any other amount | 1, -0.053, -0.05 | 4, +0.236, +0.95 | 0 | 1, -0.053, -0.05 |
| dev buy kind 1 (exact SOL in) | 0 | 0 | 0 | 1, -0.052, -0.05 |
| dev buy kind 2 (token amount + SOL cap) | 19, +0.133, +2.52 | 31, +0.058, +1.79 | 1, +0.080, +0.08 | 15, +0.011, +0.16 |
| dev buy kind 3 | 0 | 0 | 0 | 0 |

### 4. Leader skip list (chosen on A: leaders with >= 5 watched launches in A and mean S+2 < -0.02 SOL)

Skip list: 3JotfSFP (bam, A 6: -0.025), CMPSSdrT (bam, A 6: -0.094), CQdLgwkm (harmonic, A 7: -0.089), DrifTrN9 (harmonic, A 8: -0.046), EvnRmnMr (other, A 13: -0.034)

### 4a. Skip-list leaders vs the rest

| variant | grp | n | /h | creators | PnL S+2 | per launch | median | win | worst | +20 ms S+2 | S+2 w/o best 3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all watched, skip-list leaders | A | 40 | 25.8 | 40 | -2.15 | -0.054 | -0.050 | 18% | -0.53 | -2.03 | -2.89 |
|  | B | 64 | 18.8 | 60 | -1.57 | -0.025 | -0.049 | 22% | -0.26 | -1.87 | -2.09 |
|  | C | 3 | 3.6 | 3 | +0.07 | +0.024 | -0.015 | 33% | -0.05 | +0.07 | +0.00 |
|  | D | 39 | 16.1 | 38 | -1.57 | -0.040 | -0.035 | 36% | -0.63 | -1.81 | -1.81 |
| all watched, other leaders | A | 285 | 184.0 | 236 | +2.02 | +0.007 | -0.048 | 25% | -0.51 | -3.96 | -0.94 |
|  | B | 489 | 143.9 | 361 | +4.20 | +0.009 | -0.040 | 27% | -0.50 | -2.36 | +1.71 |
|  | C | 51 | 61.8 | 51 | +2.04 | +0.040 | -0.050 | 18% | -0.33 | +1.73 | -1.52 |
|  | D | 213 | 88.1 | 147 | +0.20 | +0.001 | -0.038 | 26% | -0.56 | -2.19 | -2.48 |
| rule #2 on skip-list leaders | A | 3 | 1.9 | 3 | -0.28 | -0.093 | -0.060 | 33% | -0.26 | -0.08 | +0.00 |
|  | B | 1 | 0.3 | 1 | -0.01 | -0.011 | -0.011 | 0% | -0.01 | -0.01 | +0.00 |
|  | C | 0 | - | - | - | - | - | - | - | - | - |
|  | D | 1 | 0.4 | 1 | -0.05 | -0.053 | -0.053 | 0% | -0.05 | -0.05 | +0.00 |
| rule #2 without skip-list leaders | A | 16 | 10.3 | 12 | +2.80 | +0.175 | +0.017 | 50% | -0.06 | +1.49 | +0.15 |
|  | B | 30 | 8.8 | 21 | +1.81 | +0.060 | -0.031 | 37% | -0.11 | +1.31 | +0.11 |
|  | C | 1 | 1.2 | 1 | +0.08 | +0.080 | +0.080 | 100% | +0.08 | +0.08 | +0.00 |
|  | D | 15 | 6.2 | 9 | +0.16 | +0.011 | -0.011 | 40% | -0.41 | -0.05 | -0.47 |

### 4b. Leaders the owner asked about (all watched launches; n, per launch, total)

| leader | class | A | B | C | D | rule #2 (all groups) |
|---|---|---|---|---|---|---|
| C8Bey3LK | jito | 15, +0.076, +1.13 | 30, +0.016, +0.49 | 6, +0.100, +0.60 | 11, +0.118, +1.29 | 2, +0.624, +1.25 |
| HEL1USMZ | jito | 26, +0.028, +0.73 | 66, -0.004, -0.23 | 4, -0.046, -0.19 | 35, +0.000, +0.00 | 11, +0.141, +1.55 |
| Fd7btgyS | harmonic | 43, +0.039, +1.67 | 73, +0.029, +2.11 | 10, -0.022, -0.22 | 26, -0.063, -1.65 | 7, +0.047, +0.33 |
| EvnRmnMr | other | 13, -0.034, -0.44 | 26, -0.046, -1.20 | 2, -0.031, -0.06 | 25, -0.025, -0.63 | 1, -0.011, -0.01 |
| JUPiTERr | jito | 16, +0.005, +0.08 | 30, -0.011, -0.33 | 2, -0.041, -0.08 | 14, +0.031, +0.43 | 6, +0.016, +0.09 |
| Awes4Tr6 | harmonic | 23, +0.008, +0.17 | 28, +0.067, +1.88 | 1, -0.050, -0.05 | 9, -0.029, -0.26 | 4, +0.244, +0.98 |
| CMPSSdrT | bam | 6, -0.094, -0.56 | 8, -0.047, -0.38 | 0 | 3, -0.015, -0.04 | 3, -0.093, -0.28 |
| 3JotfSFP | bam | 6, -0.025, -0.15 | 5, -0.045, -0.22 | 0 | 7, -0.136, -0.95 | 1, -0.053, -0.05 |

### 5a. Activity regime and hour, rule #2 launches

| variant | A: n, per launch, total | B: n, per launch, total | C: n, per launch, total | D: n, per launch, total |
|---|---|---|---|---|
| creates seen in the previous 10 min < 30/min | 0 | 0 | 0 | 10, +0.009, +0.09 |
| 30-45/min | 7, +0.089, +0.62 | 8, +0.067, +0.54 | 1, +0.080, +0.08 | 4, +0.008, +0.03 |
| 45-60/min | 10, +0.124, +1.24 | 13, +0.026, +0.34 | 0 | 2, -0.007, -0.01 |
| >= 60/min | 1, +0.910, +0.91 | 7, +0.106, +0.74 | 0 | 0 |
| UTC 00-06 | 0 | 4, -0.017, -0.07 | 0 | 0 |
| UTC 06-12 | 0 | 0 | 1, +0.080, +0.08 | 10, -0.005, -0.05 |
| UTC 12-18 | 0 | 10, +0.094, +0.94 | 0 | 6, +0.026, +0.16 |
| UTC 18-24 | 19, +0.133, +2.52 | 17, +0.054, +0.92 | 0 | 0 |

### 5b. Activity regime and hour, all watched launches with create <= 150 ms

| variant | A: n, per launch, total | B: n, per launch, total | C: n, per launch, total | D: n, per launch, total |
|---|---|---|---|---|
| creates seen in the previous 10 min < 30/min | 0 | 2, -0.012, -0.02 | 27, +0.005, +0.13 | 99, -0.017, -1.68 |
| 30-45/min | 88, +0.002, +0.20 | 130, -0.007, -0.96 | 5, -0.022, -0.11 | 76, +0.015, +1.16 |
| 45-60/min | 95, +0.009, +0.85 | 149, +0.024, +3.54 | 0 | 6, +0.038, +0.23 |
| >= 60/min | 29, +0.021, +0.62 | 51, +0.011, +0.56 | 0 | 0 |
| UTC 00-06 | 0 | 80, +0.002, +0.15 | 0 | 0 |
| UTC 06-12 | 0 | 0 | 33, -0.001, -0.03 | 117, -0.023, -2.68 |
| UTC 12-18 | 0 | 128, +0.011, +1.38 | 0 | 64, +0.037, +2.39 |
| UTC 18-24 | 223, +0.008, +1.73 | 162, +0.012, +1.89 | 0 | 0 |

### 6. On-chain creator history (public RPC; only signatures before the create slot)

Coverage: 1184 of 1184 launches.


### 6a. Creator wallet and creator-vault history, all watched launches with create <= 150 ms

| variant | A: n, per launch, total | B: n, per launch, total | C: n, per launch, total | D: n, per launch, total |
|---|---|---|---|---|
| wallet's prior txs <= 3 (fresh wallet) | 105, -0.011, -1.12 | 168, +0.030, +5.04 | 11, -0.027, -0.29 | 66, -0.002, -0.11 |
| prior txs 4-20 | 27, +0.014, +0.37 | 41, +0.025, +1.01 | 4, -0.131, -0.52 | 20, -0.020, -0.39 |
| prior txs 21-1000 | 86, +0.032, +2.74 | 144, -0.016, -2.27 | 14, +0.050, +0.70 | 73, +0.014, +1.02 |
| prior txs > 1000 (or history not fully listed) | 13, -0.046, -0.60 | 36, +0.029, +1.03 | 4, +0.020, +0.08 | 23, -0.035, -0.81 |
| wallet age < 10 min | 68, -0.040, -2.72 | 60, -0.004, -0.26 | 7, -0.057, -0.40 | 46, -0.016, -0.76 |
| wallet age >= 10 min (history window ~23 h) | 136, +0.031, +4.20 | 211, +0.006, +1.19 | 21, +0.017, +0.36 | 128, -0.000, -0.01 |
| creator vault: no earlier pump trades (first coin) | 120, -0.010, -1.21 | 125, +0.031, +3.89 | 11, -0.050, -0.55 | 69, +0.011, +0.75 |
| vault: 1-99 earlier trades | 33, +0.039, +1.29 | 56, -0.007, -0.38 | 11, +0.009, +0.10 | 39, -0.029, -1.12 |
| vault: 100-999 earlier trades | 34, +0.013, +0.43 | 61, -0.014, -0.83 | 2, -0.050, -0.10 | 24, -0.006, -0.14 |
| vault: >= 1000 earlier trades | 30, +0.051, +1.52 | 63, -0.008, -0.49 | 8, +0.038, +0.30 | 44, +0.010, +0.43 |
| vault: earlier trades in the last hour >= 100 | 29, +0.013, +0.36 | 84, -0.007, -0.62 | 2, +0.003, +0.01 | 41, +0.026, +1.05 |
| vault: earlier trades, none in the last hour | 16, +0.047, +0.75 | 16, +0.027, +0.43 | 7, +0.047, +0.33 | 20, -0.048, -0.95 |

### 6b. The same inside rule #2

| variant | A: n, per launch, total | B: n, per launch, total | C: n, per launch, total | D: n, per launch, total |
|---|---|---|---|---|
| wallet's prior txs <= 3 (fresh wallet) | 4, +0.389, +1.56 | 12, +0.162, +1.95 | 0 | 1, -0.052, -0.05 |
| prior txs 4-20 | 1, +0.071, +0.07 | 2, -0.032, -0.06 | 0 | 0 |
| prior txs 21-1000 | 13, +0.088, +1.15 | 15, -0.004, -0.07 | 1, +0.080, +0.08 | 11, +0.058, +0.64 |
| prior txs > 1000 (or history not fully listed) | 1, -0.257, -0.26 | 8, +0.162, +1.30 | 0 | 4, -0.119, -0.48 |
| wallet age < 10 min | 1, -0.053, -0.05 | 0 | 0 | 0 |
| wallet age >= 10 min (history window ~23 h) | 15, +0.125, +1.88 | 17, -0.008, -0.13 | 1, +0.080, +0.08 | 15, +0.011, +0.16 |
| creator vault: no earlier pump trades (first coin) | 4, +0.389, +1.56 | 1, -0.053, -0.05 | 0 | 0 |
| vault: 1-99 earlier trades | 3, +0.025, +0.07 | 1, -0.011, -0.01 | 0 | 1, -0.052, -0.05 |
| vault: 100-999 earlier trades | 7, +0.015, +0.10 | 10, -0.021, -0.21 | 0 | 9, -0.019, -0.17 |
| vault: >= 1000 earlier trades | 5, +0.157, +0.78 | 7, +0.017, +0.12 | 1, +0.080, +0.08 | 6, +0.056, +0.33 |
| vault: earlier trades in the last hour >= 100 | 6, -0.055, -0.33 | 10, -0.030, -0.30 | 0 | 10, -0.003, -0.03 |
| vault: earlier trades, none in the last hour | 2, -0.050, -0.10 | 0 | 0 | 1, -0.052, -0.05 |

### 6c. Funder reputation: earlier watched launches of creators with the SAME first funder (no look-ahead)

| variant | A: n, per launch, total | B: n, per launch, total | C: n, per launch, total | D: n, per launch, total |
|---|---|---|---|---|
| funder's earlier launches net positive | 32, +0.084, +2.68 | 57, +0.026, +1.49 | 4, +0.003, +0.01 | 65, +0.024, +1.56 |
| funder's earlier launches net zero/negative | 97, -0.025, -2.43 | 114, -0.026, -2.96 | 11, +0.193, +2.13 | 51, -0.040, -2.06 |
| first-time creator, funder net positive | 14, -0.026, -0.37 | 33, +0.019, +0.62 | 2, -0.053, -0.11 | 30, +0.021, +0.62 |
| first-time creator, funder net zero/negative | 48, -0.026, -1.26 | 40, +0.012, +0.49 | 6, +0.369, +2.21 | 8, -0.090, -0.72 |
| first-time creator, funder never seen | 167, +0.002, +0.38 | 305, +0.015, +4.67 | 32, -0.002, -0.06 | 108, -0.011, -1.16 |

First funders: 470 distinct; 16 funded >= 3 of our creators, covering 267 launches.

| funder | creators | launches | A | B | C | D |
|---|---|---|---|---|---|---|
| 5tzFkiKs | 79 | 108 | 36, -0.028 | 44, -0.002 | 3, +0.818 | 25, +0.015 |
| 6LY1JzAF | 14 | 16 | 5, +0.046 | 3, +0.029 | 2, -0.053 | 6, +0.011 |
| DXR2ZQev | 13 | 29 | 3, -0.035 | 18, -0.022 | 1, -0.020 | 7, -0.028 |
| BmFdpraQ | 12 | 12 | 4, -0.059 | 7, -0.039 | 0 | 1, -0.011 |
| iGdFcQoy | 10 | 10 | 3, +0.188 | 4, +0.051 | 0 | 3, -0.037 |
| ASTyfSim | 10 | 10 | 8, -0.022 | 1, -0.008 | 0 | 1, -0.034 |
| HckQ93Xq | 7 | 18 | 3, +0.040 | 5, +0.141 | 0 | 10, -0.016 |
| 9Aq176CZ | 6 | 6 | 2, +0.027 | 4, -0.002 | 0 | 0 |
| AxiomRXZ | 6 | 17 | 0 | 12, -0.050 | 2, -0.051 | 3, -0.021 |
| is6MTRHE | 5 | 5 | 1, -0.053 | 0 | 1, -0.050 | 3, -0.173 |
| 49CfXAr5 | 5 | 5 | 4, -0.054 | 1, -0.053 | 0 | 0 |
| 5W25GRdC | 5 | 17 | 5, -0.022 | 8, -0.006 | 1, -0.019 | 3, -0.021 |

## How REP could be used without adding latency (sketch, not built)

- **Inputs already exist.** The paper loop (`paper_c6.py`) already records every watched launch's blocks S..S+2 after they settle and prices it with this model. Appending `creator → (count, sum of modelled S+2 PnL, last market ratio)` to a small file after each launch is the whole data pipeline. Pricing lag is about 1–2 minutes; only 6 of 112 REP launches came less than 2 minutes after the creator's previous launch.
- **Engine side.** Load the file into a `HashSet<creator>` ("good": sum > 0) and a second set ("bad": count ≥ 1 and sum ≤ 0); reload it in the background every ~30 s. At fire time it is one hash lookup on the creator pubkey, which is already parsed from the create tx. No RPC, no added latency.
- **Use.** (a) Extra trigger: fire on a watched launch (base filter + close leader) whose creator is "good", whatever the bundle or tip. (b) Skip: never fire on a "bad" creator when using any wider trigger (C6/C7); inside rule #2 the skip makes no difference (see 1b).
- **Model-free fallback.** If the engine should not depend on the model, use the creator's last earlier launch's price ratio at the end of S+2 (≥ 1.1x the post-bundle price). It is a little weaker but positive in all four periods (table 1e).

## Caveats (labelled)

- **Small n (measured).** REP has 26 / 38 / 3 / 45 launches in A / B / C / D from 16 / 22 / 3 / 16 creators. 112 REP launches from 39 distinct creators over 8.2 hours of logs; the out-of-sample creator-clustered interval is above zero, but a few dozen creators is a small base.
- **The model is the judge twice (inference).** REP uses the model's PnL of a creator's earlier launches to predict the model's PnL of the next one. If the model has a per-creator bias (for example a creator whose followers our feed misses), REP could partly predict model artefacts. Against this: the model-free market response (table 1f: outside-buy SOL in S..S+2 and price ratio) is also several times higher for REP launches, and the model-free variant of the rule also works (1e).
- **Landing model (inference).** Most REP launches are not rule #2 shapes (no bundle, other tips, Harmonic leaders). Our landing time for them is the per-leader-type median, not a measurement on those launches. The +20 ms column stays positive in every period, but live fills have been worse than the model before (live median fill ~1.25x floor; memory note).
- **Coverage (measured + inference).** REP needs an earlier launch by the same creator that we watched and priced. In our gapped logs 26–42% of watched launches have any history, and REP is 6–18% of them (18% today, where the paper engine ran continuously). A continuously running recorder would see more history; far-leader launches are never priced (no feed timeline), but the model-free price ratio could be computed for them from blocks.
- **Creator behaviour can change (inference).** A creator with good history can dump (rule #2's −0.41 SOL loss today, 866Srs, had a +0.20 history). REP's worst launch was −0.41 (D) and −0.26 (A).
- **Leader skip list (measured).** Chosen on A from 5 leaders; it holds out of sample for all watched launches but touches only 2 rule #2 launches out of sample. The model has no leader-specific latency, so it cannot say whether C8Bey3LK (or any leader) is slower for us in reality.
- **Regime (measured).** Activity counts depend on each log's feed set; regimes are confounded with the day (A/B evening vs C/D morning). Rule #2's per-launch result was lower today (D +0.007) than yesterday evening (A +0.133); with 16 launches this is not distinguishable from noise.
- **On-chain history (measured).** publicnode returns only ~23 h of address history (oldest visible slot 459251988, about 10-20 14:20 UTC). 79 launches before that edge have no visible history, and 70 of 815 creators' histories are cut at it, so wallet age, prior tx count and first funder are lower bounds or approximate for older wallets. Histories are also capped at 4,000 signatures (11 heavy serial-launcher wallets). About 24% of calls errored and were retried; every creator was eventually fetched.

## Reproduce (host only; read-only)

```
W=/tmp/.../scratchpad            # FILTERS.md work dir (filt/launches2.json, leaders2.json, logs/) + today's paper loop copies under f2/paper/
python3 ops/research/paper_rows.py $W/f2/paper $W/run1/tipmap.json          # group D (today) from the paper loop's cached recordings
python3 ops/research/creator_hist.py $W/f2/creators.json $W/filt/launches2.json $W/f2/paper/launches_snapshot.json   # public RPC, 3 threads, ~15 min
python3 ops/research/filters2.py > tables.md                                 # all tables above (f2_load.py joins everything)
python3 ops/research/filters2.py dump ops/research/filters2_rows.json
```

Per-launch joined table: `ops/research/filters2_rows.json` (one row per launch: the FILTERS.md row fields + creator, name/symbol/uri, leader, block time, activity, creator history, market response, RPC history).

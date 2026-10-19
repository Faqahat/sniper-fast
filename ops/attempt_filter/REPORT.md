# Attempt-Selection Filter — what makes 4yFAz FIRE vs IGNORE a launch

Target: 4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3
Question: of all create_v2 launches in a window, which ~1% does he *attempt* (landed OR failed buy =
a decision to fire), and what slot-0 feature(s) separate ATTEMPTED from IGNORED? Pre-buy decision rule,
not the winner/loser question (prior work: unpredictable at entry).

## Data / method
- Window = unbiased create population in /root/profit_backtest/creates.json: 19,365 total create_v2 over
  slots 456,604,917-456,820,114 (~13h), 1,141 evenly subsampled with full slot-0 features + trajectory.
  creates.json is an unbiased 1/16 sample, so fraction-attempted in it estimates his true attempt rate.
- ATTEMPTED = every mint he signed a pump BUY for in-window, landed OR failed. Pulled all his in-window
  sigs (2,566; 588 success / 1,978 error), decoded top-level pump buy (17-acct, buyer=accs[8]); failed
  buys decode fine (buy ix top-level, mint present on failure). => 1,011 buy attempts (115 landed /
  896 failed) on 190 mints = 5.3 buys/mint (he sprays, ~80% fail Custom 6042 = too-late). Features for 186.
- IGNORED = creates.json minus attempted. Outcomes via econ102 shipped ladder (entry=floor*1.02, pump 1%
  + 0.25% slip/leg + fixed priority, SIZE 0.5). Built trajectories for his 186 attempts too (185 usable).

## HEADLINE: ATTEMPT RATE ~ 1%
190 attempted / 19,365 creates = 0.98%. He ignores 99% of launches. Highly selective.

## 1. SLOT-0 FEATURE SEPARATION  (lift = P(X|attempt)/P(X|pop))
| feature | P(X|att) | P(X|pop) | lift |
|---|---|---|---|
| dev_buy >= 3.0 SOL (curve) | 0.25 | 0.09 | 2.79 |
| dev_buy >= 1.0 SOL | 0.57 | 0.22 | 2.60 |
| dev_buy >= 0.5 SOL | 0.87 | 0.35 | 2.45 |
| create_cu_price > 0 | 0.61 | 0.27 | 2.31 |
| vanilla (mayhem/holder/cashback=0) | 0.80 | 0.49 | 1.61 |
| creator_fee == 0 | 0.99 | 0.94 | 1.06 (no info) |

curve-truth dev_buy (bonding-curve SOL delta in create tx): his attempts p25/med/p75 = 0.86/1.01/2.96
vs population 0.06/0.25/0.99. Real dev-buy SIZE is the dominant slot-0 separator; vanilla secondary;
creator_fee==0 almost free. create_cu>0 has lift but is DEBUNKED (create_cu_reval: regime artifact,
net-negative held-out) and is mostly a dev-size proxy.

## 2. CREATOR / DEV dimension (owner thesis) — REAL BUT SECONDARY, NOT an edge
- 13h: 186 mints -> 157 creators; 15 creators hit >1x (24% of attempts); 84% first-time; HHI 0.0095
  (uniform 0.0064); top creator 10 hits (5%).
- 4 days (621 mints): 482 creators, 1.29 mints/creator; 78% first-time; 22% repeat; HHI 0.0044 (~2x
  uniform); top creators 20/17/12 hits. Thin recurring tail; mass is one-and-done.
- Deployer/signer: fee-payer==creator ~76%. NO self-dealing: 0/186 (0/621 over 4d) created by his own
  wallet (the oldest-sig probe flagged his wallet 9x = pagination artifact on heavy mints; verified
  creator arg is never his).

EV of creator-clustering (honest check):
- Repeat-creator attempts net +0.159 vs first-time +0.179 -> repeat creators NOT higher EV.
- Pre-window favored-creator whitelist (37 creators hit >=2x before window): catches only 14% of his
  in-window attempts, and those score +0.145 (LOWER than other 86% at +0.18). Poor recall AND no EV lift.
- His top repeat creators just launch often (frequency, not edge).

Verdict: creator/dev angle is present (20-30% repeat tail) but a frequency byproduct, not his selection
rule and not an edge source. It neither reproduces his pick set (14% recall) nor beats dev-buy selection,
does not persist +EV, and he is not trading his own deploys. He keys on the launch's slot-0 economics
(true dev-buy size + vanilla + draws a bundle/co-snipe), NOT on who the dev is.

## 3. The concrete ATTEMPT RULE (slot-0, from create tx alone)
    ATTEMPT iff  curve dev_buy >~ 0.5 SOL  AND  vanilla (mayhem/holder_reward/cashback == 0)
    [creator_fee==0 implied (99%) but adds ~nothing]
- Recall of his 186 picks: dev>=0.5 = 87%; 80% vanilla.
- Coverage on population: dev>=0.5 & vanilla fires on 276/1140 = 24% -- looser than his realized 1%.
  Create-tx features BOUND his rule but he is TIGHTER than any slot-0 create feature explains. The
  residual selectivity is co-snipe/bundle presence (other snipers in the same create slot), only partly
  knowable at decision time, which lifts his realized win to 92% (= econ102 co-sniped subset +0.17/91%).

## 4. vs OUR CURRENT FILTER + the sentinel bug
| filter (econ102 ladder, SIZE 0.5, backtest regime) | n | net R | win | gross-win |
|---|---|---|---|---|
| ALL population | 1140 | +0.042 | 27% | 32% |
| PRODUCTION: wire-dev>=2 & fee0 | 656 | +0.036 | 25% | 28% |
| -- of which u64::MAX wire-sentinel | 516 | -0.037 | 10% | 13% |
| CURVE-TRUTH dev>=2 & fee0 | 153 | +0.281 | 78% | 82% |
| CURVE dev>=1 & vanilla | 163 | +0.237 | 73% | 82% |
| CURVE dev>=0.5 & vanilla (his rule) | 276 | +0.182 | 68% | 82% |
| HIS ACTUAL ATTEMPTS (13h) | 185 | +0.176 | 92% | 93% |

- Biggest actionable finding: production reads dev-buy from the buy instruction WIRE (max_sol_cost), so
  516/656 accepted are u64::MAX "unbounded cap" sentinels whose real dev-buy is tiny -- and they are net
  LOSERS (-0.037, 10% win), dragging the wire filter to +0.036. Reading CURVE-TRUTH dev-buy (bonding-curve
  SOL delta in create tx, which he effectively keys on) removes that pollution: dev>=2 curve = +0.281/78%.
  This is the lever, not creators.
- His rule is looser on dev (~0.5-1 SOL) but on TRUE dev, + vanilla, + same-slot bundled landing -> 92% win.

## 5. HONEST EV CHECK
- vs our live production (wire) filter: YES, massively better -- but the win is reading TRUE dev-buy
  instead of the wire sentinel, not copying his looseness or creators. Any curve-truth dev cut beats
  +0.036 by 5-8x.
- vs a strict curve dev>=2 cut: NO -- his looser rule (+0.18) has LOWER mean R than dev>=2 (+0.28); it
  trades ~1.8x more names and wins more often (higher win%, lower variance) but lower mean EV. His
  selectivity is lower-variance, not higher mean-EV.
- His 92% win comes from extra co-snipe/bundle selection (not fully pre-buy knowable).

### Caveats
- Regime: all +EV numbers on the favorable backtest window; disjoint later windows go -EV even gross
  (create_cu_reval, bundle_signal). Absolute +EV regime-dependent; the ORDERING (curve-dev >> wire-sentinel;
  dev-size >> creator-identity) is robust.
- Sample: 190 attempts / one 13h window for outcomes; 621 mints / 4d for recurrence; single wallet.
  Repeat-creator counts in-window; even at 4d clustering stays mild and non-EV.
- create_cu>0 shows lift but is prior-debunked (dev-size proxy, net-negative held-out) -- not recommended.

## Bottom line
He fires on ~1% of creates. The pre-buy selector he actually uses is slot-0 launch economics -- real
(curve) dev-buy >~0.5-1 SOL + vanilla flags -- and he lands same-slot on launches that attract a
bundle/co-snipe. The owner's "same creators repeatedly" thesis is only weakly true (~20-30% repeat tail)
and carries NO EV edge: he doesn't self-deploy, repeat-creators don't out-perform, a creator whitelist
neither recalls his picks (14%) nor persists +EV. Action: gate on curve-truth dev-buy (kills the 516
u64::MAX-sentinel net-losers), keep vanilla, relax threshold toward ~0.5-1 SOL to match his coverage;
forget a creator whitelist.

# MIRROR STUDY — Reproducing sniper 4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3 1:1 (paper only)

Goal: a system that buys the SAME tokens the SAME way, measured trade-by-trade vs his results. No live sends.

## TL;DR verdict
- We CAN behave same-to-same on a per-trade basis, but only if (1) we land in his SAME slot (lag 0) and (2) we drop the shipped de-risk leg. Then our per-trade net R ~= his (+0.078 vs +0.078).
- The "it's which devs he trades" thesis is NOT supported. Creator/dev-matching reproduces <=23% of his picks (recall ceiling), ~5% precision, and his repeat-dev tokens UNDER-perform his one-shot-dev tokens (which produced ALL 13 of his 2x+ runners).
- Single biggest risk is LAG, not selection/fill/exit. Same-slot = +0.045 R; one slot late = -0.060 R (win 59%->18%). A 1-slot delay is a -0.105 R swing, 3x the exit gap.
- His edge = same-slot entry at/near floor + exit ladder harvesting a fat-tail regime. Mirror that mechanically and you get his per-trade R; his creator list is not needed and does not help.

## STEP 1 - His ground-truth tape (his_tape.json, n=200)
Join of snipe_study50 (create slot/creator/dev-buy/vanilla) + exit_study (his fill, every sell, realized PnL, peak, price path). Reproduces his headline exactly.
- total realized +38.30 SOL; mean/pos +0.1915 SOL = +0.0784 R; win 59.5% (119W/81L).
- entry: create-slot delta 0 ->157, delta 1 ->35 (all <=1). residual tokens 0 on all 200.
- fill vs floor (last30 clean n=30): median 1.00, p75 1.26, max 1.98; rank-1 16/30, rank<=3 21/30.
- peak: median 1.17x, >=2x only 13/197.

## STEP 2 - Two mirror modes (our pipeline on his exact tokens; net pump 1%/leg + 0.25%/leg slip + 3M-priority fixed; size 0.5 SOL)
Exit = current shipped engine: derisk .30 / ride 1.40 / trail .92 / cut .80 / ladder .25 / cap 40, NO fade (confirmed in snipe_engine.rs).

(A) SELECTION-MIRROR (same create, enter same-slot at his fill, our ladder):
  HIS actual  : n=197 mean +0.0784 R  win 0.594
  OUR shipped : n=197 mean +0.0453 R  win 0.589  corr(his,our)=0.795  sign-agree 0.873
  -> we capture ~58% of his per-trade R; win rate and sign track him tightly.

(B) COPY-TRADE (observe his buy, fire after lag, at curve price then):
  lag 0: entry 1.00x his fill, mean +0.0453 R, win 0.589, total +8.93 R
  lag 1: entry 1.11x,          mean -0.0605 R, win 0.183, total -11.92 R
  lag 2: entry 1.10x,          mean -0.0545 R, win 0.178, total -10.73 R
  -> one slot of lag destroys the edge. The whole thing lives in the create slot.

## STEP 3 - End-to-end match scorecard
SELECTION match (no pre-buy rule reproduces his SET well; his picks are mostly one-shot devs):
  copy ALL his tokens         picks 200  recall 100%  our +0.045 R  his +0.078 R
  CREATOR-match (his devs)    picks  44  recall 23%(ceiling)  our +0.024 (worse)  his +0.052
  generic dev_buy>=2.0        picks  66  recall 33%  our +0.031  his +0.043
  generic dev_buy>=0.3        picks 164  recall 82%  our +0.041  his +0.071
  - creator recurrence recall ceiling = 23% (165 distinct creators / 200 positions; only 17 recur). Other 77% single-launch devs, unknowable pre-buy.
  - creator precision (backtest universe): his favored devs launched 20 tokens in-window, he bought 1 (~5%). He skips most of "his" devs' launches.
  - does "which dev" carry alpha? NO. Repeat-dev: mean +0.139 SOL, 0 of his 2x+ runners. One-shot-dev: mean +0.209 SOL, ALL 13 of the >=2x runners.

FILL match: his median fill-vs-floor 1.00 (rank-1 16/30). Our 3M fill ~= floor*1.02 -> parity same-slot (we ~2% above floor, he ~0%). On contested ramps we can't beat his rank as a peer, so our fill ~= his, not better. Fill is NOT the gap.

EXIT match: shipped ladder +0.045 vs his +0.078 (corr 0.795). The gap is almost entirely the de-risk leg (sells 30% instantly at ~break-even, pays 1% pump fee twice). Dropping it -> +0.078, matching him. Residual = his discretionary hold on the biggest runners; a fixed trail-stop clips the extreme tail.

OUTCOME decomposition (of the +0.078 -> +0.045 gap, -0.033 R):
  Selection (which tokens)   ~0        copying all his tokens = full coverage; any real rule only loses coverage
  Creator/dev selection      NEGATIVE  matching his devs covers 23% at lower R - hurts
  Fill                       ~0        parity same-slot
  Exit params (de-risk leg)  ~ all of it (-0.033)  fully recovered by retune (derisk 0)
  LAG (structural)           DOMINANT risk (-0.105 if 1 slot late)  the real failure mode
  => single biggest factor vs him = same-slot landing (lag); given same-slot, the de-risk leg. Not selection, not fill.

## STEP 4 - Best mirror config
Grid over his tape (net R @0.5 SOL):
  derisk 0.0 / ride 1.40 / trail 0.92 / cut 0.80 / ladder 0.25 / cap 20  -> total +15.3 R, mean +0.078 R, win 0.64
  - drops the de-risk leg, otherwise the shipped ladder; lifts +0.045 -> +0.078 R ~= his +0.078, win 0.59->0.64.
  - cross-check: econ_102 on an UNBIASED sample, same floor*1.02 fill, gives +0.036 R shipped / ~+0.09 retuned - same regime, so not an in-sample fit.

Structurally unmatchable residual:
  1. His same-slot landing - if detect+send can't hit lag 0 we go negative. This is the whole ballgame.
  2. His discretionary tail-hold on the few >=2.5x runners (fixed trail-stop captures most, clips the extreme). ~10-15% of upside.
  3. Size - our per-trade R ~= his when tuned, but his +38 SOL total uses ~1.9 SOL avg size; matching his SOL total needs his size too.

## Honest bottom line
Mirror him exactly (same-slot floor entry on his token set, retuned ladder derisk 0) and we get ~his per-trade R (+0.078), no more. We do NOT need his creator list; keying on "his devs" reproduces <1/4 of his picks, ~5% precise, and skews us to his weaker names. His profit is a same-slot-floor + exit-harvest of a fat-tail regime; the only thing that stops us reproducing it is landing late (lag), with the shipped de-risk leg a distant second. Both fixable in-engine; the creator angle is a dead end.

## Caveats
- One wallet, ~2-day window, N=200 (+30 clean-fill, +190 attempts). Fat-tail by construction; not lifetime.
- KEY DATA FIX: prior exit_study/replay2.py (current paths) wrongly included same-slot PRE-BUY ramp points (dev + earlier co-snipers printing BELOW his fill before his buy), making every fixed-ladder replay look negative (-13 SOL). A sniper cannot sell into a price that printed before his buy; excluding them (dslot==0 & r<1.0) makes the mirror consistent and positive. exit_study REPORT's +42.7 was an earlier path set; corrected numbers are lower but internally consistent.
- Creator precision uses profit_backtest universe (overlaps only 24 of his creators, different sub-window) - direction clear, 5% approximate.
- 3/200 tokens lack a price path; excluded from replay, kept for his-tape PnL.
- Files in /root/mirror: his_tape.json, mirror_results.json, his_creators.json, summary.json, build_tape.py, mirror_sim.py, tune.py, fill_creator.py

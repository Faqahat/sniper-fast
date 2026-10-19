#!/bin/bash
# ============================================================================
# FINAL CONFIG — 4yFAz clone, his-matching selection + his measured exit ladder.
# Ready for a LIVE TEST (does NOT auto-run; owner launches on their OK).
#
# ---- PAPER EVIDENCE (honest) ----
# SELECTION (on-chain verified over his 519 buys): bundled dev buy, 96%; tokens 98% VANILLA;
#   dev spread wide (median 1.6 SOL, p10-p90 0.5-5), he avoids dev~0. Our filter = dev 0.5-8 + vanilla.
# EXIT (measured from his 514 round-trips): 30% immediate clip, time-based ~2s dud-cut (NOT stop-loss),
#   ladder the runner, cap ~40s, never hold past 60s. Encoded below.
# PAPER RESULT — the key caveat:
#   * AT FLOOR entry (same-slot fill): dev>=0.5 vanilla = +0.195 mean, 61% win, ex-top10 +0.10 (ROBUST POSITIVE).
#   * AT REALISTIC entry (our current fills, no floor): NEGATIVE across ALL filters (dev0.5+van -0.013,
#     dead dev<0.5 big loss), over 5000+ broad-collector trades. Every ex-top10 negative.
#   => The edge IS the floor fill. This config is positive ONLY if we land same-slot at the floor.
#      The live test's real purpose = measure whether our execution (close-leader gate + staked + cu5M +
#      dual feed) achieves floor fills on dev>=0.5 tokens. Prior $0.50 tests filled 0/20 at <=1.12x on
#      dev~0 (thin) tokens; dev>=0.5 (deeper curve) is UNTESTED live and is the open question.
#
# ---- SIZE WARNING ----
# Fixed priority fee = cu_price 5M x cu_limit ~120k = ~$0.24/round-trip. At $0.50 that's ~40% drag.
# Use >= ~$5-10 (0.025-0.05 SOL) per buy so fees < 5%. Owner sets --spend-lamports / caps.
# ============================================================================
export PATH=/root/.cargo/bin:$PATH
cd /root/arbx-fast
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}

# ---- EDIT THESE before live ----
SPEND=25000000       # 0.025 SOL (~$5). Raise for lower fee drag. (0.5$ was too small.)
MAXSOL=0.03          # per-buy hard cap
MAXTOTAL=1.0         # cumulative buy-spend cap across the run
MAXLOSS=0.3          # balance kill-switch
MININFLIGHT=20

./target/release/snipe_engine --snipe-once --concurrent --live \
  --close-leaders /root/arbx-fast/close_leaders.txt \
  --min-dev-buy 500000000 --max-dev-buy-sol 8 \
  --fill-cap 1.12 \
  --spend-lamports $SPEND --max-sol $MAXSOL --max-total-sol $MAXTOTAL --max-loss-sol $MAXLOSS --max-inflight $MININFLIGHT \
  --derisk-frac 0.30 --ride-mult 1.15 --trail-frac 0.95 --cut-r 0.0 --ladder-frac 0.25 --exit-cap-ms 40000 \
  --send-path staked-rpc --cu-price-micro 5000000 \
  --config probe_shadow.toml --env-file /root/arbx/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass

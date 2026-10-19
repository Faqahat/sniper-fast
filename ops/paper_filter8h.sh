#!/bin/bash
# 8-HOUR PAPER TRADE — verified 4yFAz FILTER + his MEASURED exit ladder, REALISTIC entry (no floor). Zero cost, no sends.
#
# FILTER (his on-chain selection): bundled dev buy AND dev 0.5-8 SOL (96% of his picks are bundled; p10=0.54 SOL).
# ENTRY: first-readable price (NO --entry-at-floor) = realistic (we do NOT assume a floor fill we can't prove).
# EXIT  (measured from his 514 round-trips):
#   --derisk-frac 0.30   = immediate ~30% clip off the top (his measured value)
#   --demand-window-ms 2000 --demand-min-r 1.05 = dud-cut: if not up ~5% by ~2s, dump the rest (he single-dumps duds by ~2s)
#   --ride-mult 1.15 --trail-frac 0.95 = ride/trail the runner (he sells into strength early)
#   --ladder-frac 0.25   = ladder the runner out in ~25% clips (his 3+ leg decreasing-clip pattern)
#   --exit-cap-ms 40000  = 40s hold cap (his p90 full-exit ~38s, never holds past ~60s); duds cut at 2s
export PATH=/root/.cargo/bin:$PATH
cd /root/arbx-fast
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/arbx-fast/paper_filter8h.log
timeout 29000 ./target/release/snipe_engine --paper-trade \
  --config probe_shadow.toml --env-file /root/arbx/deploy/.env \
  --minutes 480 --max-r-cap 20 \
  --min-dev-buy 500000000 --max-dev-buy-sol 8 \
  --derisk-frac 0.30 --ride-mult 1.15 --trail-frac 0.95 --cut-r 0.0 --ladder-frac 0.25 \
  --demand-window-ms 2000 --demand-min-r 1.05 --exit-cap-ms 40000 \
  --size-sol 1.0 --dump-paths /root/arbx-fast/paths_filter8h.jsonl --max-inflight 48 \
  < /root/.nexus-v2-trading-wallet.pass >> /root/arbx-fast/paper_filter8h.log 2>&1
echo "PAPER_FILTER8H_DONE" >> /root/arbx-fast/paper_filter8h.log

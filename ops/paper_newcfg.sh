#!/bin/bash
# Fresh 20-min paper trade on the NEW config (ride 1.3, trail 0.95, no dead-cut, no scale, dev<=8).
# entry-at-floor = models same-slot floor landing (optimistic vs live +1). ZERO-COST, no send.
export PATH=/root/.cargo/bin:$PATH
cd /root/arbx-fast
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/arbx-fast/paper_newcfg.log
timeout 1320 ./target/release/snipe_engine --paper-trade \
  --config probe_shadow.toml --env-file /root/arbx/deploy/.env \
  --minutes 20 --entry-at-floor --max-r-cap 20 \
  --min-dev-buy 0 --max-dev-buy-sol 8 \
  --ride-mult 1.3 --trail-frac 0.95 --cut-r 0.0 \
  --max-inflight 48 \
  < /root/.nexus-v2-trading-wallet.pass >> /root/arbx-fast/paper_newcfg.log 2>&1
echo "PAPER_NEWCFG_DONE" >> /root/arbx-fast/paper_newcfg.log

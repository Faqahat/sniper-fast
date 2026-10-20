#!/bin/bash
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-fast
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/sniper-fast/probe_gated.log
rm -f /root/sniper-fast/shots_gated.jsonl
timeout 760 ./target/release/snipe_engine --shadow --warm-probe-on-trigger --live \
  --max-sol 0.02 --max-sends 60 --min-dev-buy 0 --duration-s 700 \
  --send-path staked-rpc --land-poll-ms 15 --cu-price-micro 5000000 \
  --probe-cu-limit 450 --dump-shots /root/sniper-fast/shots_gated.jsonl \
  --close-leaders /root/sniper-fast/close_leaders.txt \
  --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass >> /root/sniper-fast/probe_gated.log 2>&1
echo "PROBE_GATED_DONE" >> /root/sniper-fast/probe_gated.log

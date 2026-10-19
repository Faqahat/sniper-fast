#!/bin/bash
export PATH=/root/.cargo/bin:$PATH
cd /root/arbx-fast
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/arbx-fast/probe_gated.log
rm -f /root/arbx-fast/shots_gated.jsonl
timeout 760 ./target/release/snipe_engine --shadow --warm-probe-on-trigger --live \
  --max-sol 0.02 --max-sends 60 --min-dev-buy 0 --duration-s 700 \
  --send-path staked-rpc --land-poll-ms 15 --cu-price-micro 5000000 \
  --probe-cu-limit 450 --dump-shots /root/arbx-fast/shots_gated.jsonl \
  --close-leaders /root/arbx-fast/close_leaders.txt \
  --config probe_shadow.toml --env-file /root/arbx/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass >> /root/arbx-fast/probe_gated.log 2>&1
echo "PROBE_GATED_DONE" >> /root/arbx-fast/probe_gated.log

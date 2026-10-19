#!/bin/bash
export PATH=/root/.cargo/bin:$PATH
cd /root/arbx-fast
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/arbx-fast/probe_inter.log
rm -f /root/arbx-fast/shots_inter.jsonl
timeout 820 ./target/release/snipe_engine --shadow --warm-probe-on-trigger --live \
  --max-sol 0.03 --max-sends 90 --min-dev-buy 0 --duration-s 760 \
  --send-path staked-rpc --land-poll-ms 15 --cu-price-micro 5000000 \
  --probe-cu-limit 450 --dump-shots /root/arbx-fast/shots_inter.jsonl \
  --close-leaders /root/arbx-fast/close_leaders.txt --leader-tag-only \
  --config probe_shadow.toml --env-file /root/arbx/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass >> /root/arbx-fast/probe_inter.log 2>&1
echo "PROBE_INTER_DONE" >> /root/arbx-fast/probe_inter.log

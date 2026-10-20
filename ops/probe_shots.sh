#!/bin/bash
# Self-transfer probe (no real buys) that dumps per-shot create/land/delta to shots.jsonl
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-fast
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/sniper-fast/probe_shots.log
rm -f /root/sniper-fast/shots.jsonl
timeout 700 ./target/release/snipe_engine --shadow --warm-probe-on-trigger --live \
  --max-sol 0.02 --max-sends 60 --min-dev-buy 0 --duration-s 640 \
  --send-path staked-rpc --land-poll-ms 15 --cu-price-micro 5000000 \
  --probe-cu-limit 450 --dump-shots /root/sniper-fast/shots.jsonl \
  --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass >> /root/sniper-fast/probe_shots.log 2>&1
echo "PROBE_SHOTS_DONE" >> /root/sniper-fast/probe_shots.log

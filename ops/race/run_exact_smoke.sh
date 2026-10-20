#!/bin/bash
# 3-minute check of the EXACT fallback paper command from NOTES.md (paper only).
cd /root/sniper-race && set -a && . /root/sniper/deploy/.env && set +a
export KALDERA_TOKEN=$(grep -o "KALDERA_TOKEN=[^ ]*" /root/collect_blfwd.sh | head -1 | cut -d= -f2)
timeout 300 ./target/release/snipe_engine --paper-trade --minutes 3 --max-r-cap 20 \
  --min-dev-buy 500000000 --max-dev-buy-sol 8 --uri-blacklist \
  --derisk-frac 0 --ladder-frac 0 --ride-mult 99 --cut-r 0 --exit-cap-ms 1000 \
  --size-sol 2.0 --dump-paths /root/race/paths_exact.jsonl --max-inflight 48 \
  --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
  --dev-from-cap --race-gate --race-min-dev-sol 3 --race-min-bundle 2 --race-bundle-ms 3 --race-max-name-len 12 \
  --race-pros /root/race/pros.json --race-track-rejects \
  < /root/.nexus-v2-trading-wallet.pass >> /root/race/paper_exact.log 2>&1
echo EXACT_DONE >> /root/race/paper_exact.log

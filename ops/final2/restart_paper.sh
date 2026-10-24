#!/bin/bash
# Restart the server's 24 h shadow paper engine exactly as it ran before the 2026-10-23 landing probe (command saved in
# /root/sniper-shadow/paper_cmdline_20261023.txt from /proc). Output APPENDS to engine.log so the running scorer keeps tailing it.
# Refuses if any snipe_engine is running (e.g. the probe is still going).
cd /root/sniper-shadow || exit 1
if pgrep -x snipe_engine > /dev/null; then echo "REFUSED: a snipe_engine is running"; exit 1; fi
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN
echo "=== restarted $(date -u) after the landing probe" >> engine.log
setsid nohup ./snipe_engine --paper-trade --minutes 1440 --config /root/run1/run1_landing.toml --env-file /root/sniper/deploy/.env \
  --min-dev-buy 0 --max-dev-buy-sol 1000000 --allow-nonvanilla --allow-nonsol-quote --allow-legacy-create --dev-from-cap \
  --race-gate --race-log --race-glued --race-min-bundle-sol 1000000 --race-obs-ms 1000 --max-inflight 4 \
  < /root/.nexus-v2-trading-wallet.pass >> engine.log 2>&1 &
sleep 5
echo "paper engine pid $(pgrep -n -x snipe_engine)"

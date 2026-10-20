#!/bin/bash
# PAPER ONLY (no --live): the exact live-test filter on the final arbx-lat binary, 15 min, to verify fired launches on chain.
cd /root/lat
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=$(grep -o "KALDERA_TOKEN=[^ ]*" /root/collect_blfwd.sh | head -1 | cut -d= -f2)
timeout 1000 /root/sniper-lat/target/release/snipe_engine --paper-trade --minutes 15 --entry-at-floor --max-r-cap 20   --uri-blacklist --min-dev-buy 500000000 --max-dev-buy-sol 8   --dev-from-cap --race-gate --race-min-dev-sol 3 --race-min-bundle 2 --race-bundle-ms 3 --race-max-name-len 12   --race-pros /root/race/pros.json --race-early   --exit-cap-ms 1000 --derisk-frac 0 --ladder-frac 0 --ride-mult 99 --cut-r 0 --size-sol 1.0 --max-inflight 48   --dump-paths /root/bsplit/verify_paths.jsonl --config /root/lat/lat_landing.toml --env-file /root/sniper/deploy/.env   < /root/.nexus-v2-trading-wallet.pass > /root/bsplit/verify_paper.log 2>&1
echo VERIFY_PAPER_DONE >> /root/bsplit/verify_paper.log

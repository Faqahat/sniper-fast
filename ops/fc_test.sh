#!/bin/bash
export PATH=/root/.cargo/bin:$PATH
cd /root/sniper-fast
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
: > /root/fc2.txt
timeout 30 ./target/release/snipe_engine --shadow --feed-compare --config probe_shadow.toml --env-file /root/sniper/deploy/.env --duration-s 24 --min-dev-buy 0 --max-sends 100000 < /root/.nexus-v2-trading-wallet.pass >> /root/fc2.txt 2>&1
echo FC_DONE >> /root/fc2.txt

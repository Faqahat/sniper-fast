#!/bin/bash
cd /root/sniper-fast
./target/release/snipe_engine --shadow --warm-probe-on-trigger --live \
  --max-sol 0.02 --max-sends 40 --min-dev-buy 200000000 --duration-s 1800 \
  --send-path staked-rpc --land-poll-ms 15 --cu-price-micro 5000000 \
  --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass
echo "=== CU5M DONE ==="

#!/bin/bash
cd /root/arbx-fast
./target/release/snipe_engine --shadow --warm-probe-on-trigger --live \
  --max-sol 0.02 --max-sends 40 --min-dev-buy 200000000 --duration-s 1800 \
  --send-path tpu-direct --land-poll-ms 15 \
  --config probe_shadow.toml --env-file /root/arbx/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass
echo "=== INCL DONE ==="

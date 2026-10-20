#!/bin/bash
# LATENCY SCOPE (zero-trade): fire tiny 1-lamport self-transfers timed to small-dev creates,
# measure create->land slot distribution. Tells us if we can land delta-0 (same-slot). No buys.
cd /root/sniper-fast
./target/release/snipe_engine --shadow --warm-probe-on-trigger --live \
  --max-sol 0.02 --max-sends 40 --min-dev-buy 200000000 --duration-s 1800 \
  --send-path tpu-direct --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass
echo "=== LATENCY SCOPE DONE ==="

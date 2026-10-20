#!/bin/bash
# CONCURRENT LIVE SNIPER: fires every qualifying launch in parallel. min-dev-buy 0 (like 4yFAz).
# Bounds: per-buy $1, total spend 0.2 SOL, LOSS kill-switch 0.05 SOL, 6 concurrent, 20 min.
cd /root/sniper-fast
./target/release/snipe_engine --snipe-once --concurrent --live --exit-ladder \
  --config probe_shadow.toml --env-file /root/sniper/deploy/.env --send-path staked-rpc \
  --min-dev-buy 0 --fill-cap 1.12 --cu-price-micro 5000000 \
  --spend-lamports 9500000 --max-sol 0.011 --max-total-sol 0.2 --max-loss-sol 0.05 \
  --max-inflight 6 --minutes 20 < /root/.nexus-v2-trading-wallet.pass
echo "=== CONCURRENT DONE ==="

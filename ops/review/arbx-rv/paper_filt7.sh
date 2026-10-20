#!/bin/bash
cd /root/sniper-fast
./target/release/snipe_engine --paper-trade --config probe_shadow.toml --env-file /root/sniper/deploy/.env \
  --minutes 600 --min-dev-buy 0 --min-early-trades 7 --max-dev-buy-sol 8 --max-inflight 48 \
  < /root/.nexus-v2-trading-wallet.pass

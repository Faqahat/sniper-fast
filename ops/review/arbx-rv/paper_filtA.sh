#!/bin/bash
cd /root/arbx-fast
./target/release/snipe_engine --paper-trade --config probe_shadow.toml --env-file /root/arbx/deploy/.env \
  --minutes 600 --min-dev-buy 0 --min-demand-mult 1.05 --max-dev-buy-sol 8 --max-inflight 48 \
  < /root/.nexus-v2-trading-wallet.pass

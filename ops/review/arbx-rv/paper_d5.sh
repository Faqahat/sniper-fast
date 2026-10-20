#!/bin/bash
cd /root/sniper-fast
./target/release/snipe_engine --paper-trade --config probe_shadow.toml \
  --env-file /root/sniper/deploy/.env --minutes 600 --min-dev-buy 5000000000 \
  < /root/.nexus-v2-trading-wallet.pass

#!/bin/bash
cd /root/arbx-fast
./target/release/snipe_engine --paper-trade --config probe_shadow.toml \
  --env-file /root/arbx/deploy/.env --minutes 600 --min-dev-buy 8000000000 \
  < /root/.nexus-v2-trading-wallet.pass

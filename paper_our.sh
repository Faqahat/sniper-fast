#!/bin/bash
cd /root/arbx-fast
./target/release/snipe_engine --paper-trade --config probe_shadow.toml --env-file /root/arbx/deploy/.env --minutes 600 --min-dev-buy 0 --max-dev-buy-sol 8 --demand-window-ms 650 --demand-min-r 1.01 --max-inflight 48 < /root/.nexus-v2-trading-wallet.pass

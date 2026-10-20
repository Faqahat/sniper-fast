#!/bin/bash
cd /root/sniper-fast
./target/release/snipe_engine --paper-trade --config probe_shadow.toml --env-file /root/sniper/deploy/.env --minutes 600 --min-dev-buy 0 --max-dev-buy-sol 8 --demand-window-ms 650 --demand-min-r 1.01 --ride-mult 1.5 --trail-frac 0.90 --max-inflight 32 < /root/.nexus-v2-trading-wallet.pass

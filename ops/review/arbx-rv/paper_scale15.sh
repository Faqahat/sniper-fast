#!/bin/bash
cd /root/arbx-fast
./target/release/snipe_engine --paper-trade --config probe_shadow.toml --env-file /root/arbx/deploy/.env --minutes 600 --entry-at-floor --max-r-cap 20 --min-dev-buy 0 --max-dev-buy-sol 8 --demand-window-ms 650 --demand-min-r 1.01 --ride-mult 1.3 --trail-frac 0.90 --scale-add-thr 1.5 --scale-add-size 2.0 --max-inflight 32 < /root/.nexus-v2-trading-wallet.pass

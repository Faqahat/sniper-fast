#!/bin/bash
cd /root/arbx-fast
./target/release/snipe_engine --paper-trade --config probe_shadow.toml --env-file /root/arbx/deploy/.env --minutes 600 --entry-at-floor --max-r-cap 20 --min-dev-buy 0 --max-dev-buy-sol 8 --dump-paths /root/arbx-fast/paths.jsonl --max-inflight 48 < /root/.nexus-v2-trading-wallet.pass

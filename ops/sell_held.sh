#!/bin/bash
# Sell the 5 positions left by the Helius landing arm (Helius 429 refused the sells). Via staked-rpc, low fee, closes ATAs.
export PATH=/root/.cargo/bin:$PATH
cd /root/arbx-fast
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=${KALDERA_TOKEN:?set KALDERA_TOKEN in deploy/.env}
./target/release/snipe_engine --live --sell-held 4EAQ2WxiyqRnzZnh2GoXJ5yepHpQruMMiWnMTWzYpump,8hjppvCxQLnNSJHoVpEXagH6EV28ppHGxZVEbLJQKysY,5NQzFcLyLj6CMv1x1gSkxRxFiDwWQrq3iK23ukdmpump,FWqkH6CosAgJRF4WW3cgkP4X4P82RmqRie9wHENBqj2J,3qmUAvfT4Mf3uT1FZiL9HdF4NhwakSsZEQZLWFz3pump \
  --send-path staked-rpc --sell-path staked-rpc --cu-limit 120000 --sell-cu-price-micro 1500000 \
  --config probe_shadow.toml --env-file /root/arbx/deploy/.env < /root/.nexus-v2-trading-wallet.pass

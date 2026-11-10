#!/bin/bash
# FLOOR-FILL TEST: 10 trades, ~$1 size, NEW config (staked-rpc + cu_price 5M + fill-cap 1.04), immediate round-trip.
# Goal: measure our real fill (entry/floor) with the tuned send path. KILL-SWITCH: net down > 0.03 SOL.
set -a; . /root/arbx/deploy/.env; set +a
RPC="https://rpc-frankfurt.constant-k.com/?api-key=$CONSTANTK_TOKEN"
W=FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS
cd /root/arbx-fast
bal(){ curl -s "$RPC" -X POST -H "content-type: application/json" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"getBalance\",\"params\":[\"$W\"]}" | python3 -c "import sys,json;print(json.load(sys.stdin)[\"result\"][\"value\"])"; }
START=$(bal); echo "FLOOR112 START balance: $START ($(python3 -c "print($START/1e9)") SOL)"
for i in $(seq 1 10); do
  echo "=== FLOOR112 attempt $i ==="
  timeout 600 ./target/release/snipe_engine --snipe-once --config probe_shadow.toml \
    --env-file /root/arbx/deploy/.env --send-path staked-rpc \
    --min-dev-buy 200000000 --fill-cap 1.12 --cu-price-micro 5000000 \
    --spend-lamports 9500000 --max-sol 0.011 --live < /root/.nexus-v2-trading-wallet.pass
  CUR=$(bal); DOWN=$((START - CUR))
  echo "--- after $i: balance=$CUR net=$(python3 -c "print(($CUR-$START)/1e9)") SOL ---"
  if [ "$DOWN" -gt 30000000 ]; then echo "KILL-SWITCH: down > 0.03 SOL, stop."; break; fi
done
echo "=== FLOOR112 DONE === final=$(bal) net=$(python3 -c "print(($(bal)-$START)/1e9)") SOL"

#!/bin/bash
# DEV>=8 FILL CHECK: 10 trades, 0.05 SOL, fill-cap 1.04x floor, IMMEDIATE round-trip (no ride).
# Goal: read the REAL fill (entry/floor) under live competition. KILL-SWITCH: net down > 0.07 SOL.
set -a; . /root/arbx/deploy/.env; set +a
RPC="https://rpc-frankfurt.constant-k.com/?api-key=$CONSTANTK_TOKEN"
W=FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS
cd /root/arbx-fast
bal(){ curl -s "$RPC" -X POST -H 'content-type: application/json' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"getBalance\",\"params\":[\"$W\"]}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['result']['value'])"; }
START=$(bal)
echo "DEV8FILL START balance: $START lamports ($(python3 -c "print($START/1e9)") SOL)"
for i in $(seq 1 10); do
  echo "=== DEV8FILL attempt $i ==="
  timeout 600 ./target/release/snipe_engine --snipe-once --config probe_shadow.toml \
    --env-file /root/arbx/deploy/.env --send-path staked-rpc \
    --min-dev-buy 8000000000 --fill-cap 1.04 \
    --spend-lamports 50000000 --max-sol 0.06 --live < /root/.nexus-v2-trading-wallet.pass
  CUR=$(bal); DOWN=$((START - CUR))
  echo "--- after attempt $i: balance=$CUR  net=$(python3 -c "print(($CUR-$START)/1e9)") SOL (cumulative) ---"
  if [ "$DOWN" -gt 70000000 ]; then echo "DEV8FILL KILL-SWITCH: down > 0.07 SOL after $i attempts, stopping."; break; fi
done
echo "=== DEV8FILL DONE === final=$(bal)  net=$(python3 -c "print(($(bal)-$START)/1e9)") SOL"

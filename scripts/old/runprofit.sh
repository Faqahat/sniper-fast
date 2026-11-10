#!/bin/bash
# Live profit run: 0.05 SOL/trade WITH the exit ladder. Kill-switch: stop after 20 trades OR if net down > 0.5 SOL.
set -a; . /root/arbx/deploy/.env; set +a
RPC="https://rpc-frankfurt.constant-k.com/?api-key=$CONSTANTK_TOKEN"
W=FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS
cd /root/arbx-fast
bal(){ curl -s "$RPC" -X POST -H 'content-type: application/json' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"getBalance\",\"params\":[\"$W\"]}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['result']['value'])"; }
START=$(bal)
echo "START balance: $START lamports ($(python3 -c "print($START/1e9)") SOL)"
for i in $(seq 1 20); do
  echo "=== PROFIT $i ==="
  ./target/release/snipe_engine --snipe-once --exit-ladder --config probe_shadow.toml \
    --env-file /root/arbx/deploy/.env --send-path staked-rpc \
    --spend-lamports 50000000 --max-sol 0.1 --live < /root/.nexus-v2-trading-wallet.pass
  CUR=$(bal); DOWN=$((START - CUR))
  echo "--- after trade $i: balance=$CUR  net=$(python3 -c "print(($CUR-$START)/1e9)") SOL ---"
  if [ "$DOWN" -gt 500000000 ]; then echo "KILL-SWITCH TRIPPED: down > 0.5 SOL after $i trades, stopping."; break; fi
done
FINAL=$(bal)
echo "=== PROFIT RUN DONE === final=$FINAL  net=$(python3 -c "print(($FINAL-$START)/1e9)") SOL over the run"

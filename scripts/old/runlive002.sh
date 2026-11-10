#!/bin/bash
# Live run: 12 trades @ 0.02 SOL WITH new exit (no-fading, cut_r 0.80). Kill-switch: stop after 12 OR if net down > 0.3 SOL.
set -a; . /root/arbx/deploy/.env; set +a
RPC="https://rpc-frankfurt.constant-k.com/?api-key=$CONSTANTK_TOKEN"
W=FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS
cd /root/arbx-fast
bal(){ curl -s "$RPC" -X POST -H 'content-type: application/json' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"getBalance\",\"params\":[\"$W\"]}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['result']['value'])"; }
START=$(bal)
echo "START balance: $START lamports ($(python3 -c "print($START/1e9)") SOL)"
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  echo "=== L002 $i ==="
  ./target/release/snipe_engine --snipe-once --exit-ladder --config probe_shadow.toml \
    --env-file /root/arbx/deploy/.env --send-path staked-rpc \
    --spend-lamports 20000000 --max-sol 0.05 --live < /root/.nexus-v2-trading-wallet.pass
  CUR=$(bal); DOWN=$((START - CUR))
  echo "--- after trade $i: balance=$CUR  net=$(python3 -c "print(($CUR-$START)/1e9)") SOL (cumulative) ---"
  if [ "$DOWN" -gt 300000000 ]; then echo "KILL-SWITCH: down > 0.3 SOL after $i, stopping."; break; fi
done
echo "=== L002 DONE === net=$(python3 -c "print(($(bal)-$START)/1e9)") SOL over the run"

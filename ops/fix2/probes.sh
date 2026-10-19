#!/bin/bash
# ZERO COST probes of the FIX2 code: attribution + status polls on OLD final1 signatures/bundles, and --ack-probe (junk only)
cd /root/fix2
set -a; . /root/arbx/deploy/.env; set +a
B=/root/arbx-final2/target/release/snipe_engine
C=/root/fix2/final2_landing.toml
LV="24AFgkZvbJ4JiGxsBVCaMmSJJhwzR7cD42e4rjNzC7niqjuhZEpq9vEZ5ebEi8z6B2pyBkF4EBHwbUARNLUsvuhV:abb9782ac204e0c0e743d1dccae7bafbcfb7baeacf6c743ba5528552d8d5b86c,54eEKm6yCMY5GwaUS6uq6Mg7Tesx4fg1E5juaXmanz4ZvmNfqaZhpa6x4szSxAtjKW7vvHmhkJNHFVF4h2Fj1uce:03998c87d2de579cd1a8217319f42f4f1bc1ee0dacc5edf583245bfb17b0f1fe,W4ddo8VjEP5E9NWr9caCL5Pj67vwhtenAs3zCMiDpAKDhM6t51VQdJj6N2Bxd3e5sjaMrbzTqxCjq2srTJJo913:ab0c66e50e98d4276b70161231b8c901b371c1b0270e9eb09bd28ce9b57b3804,5StY9kiLcSzHFsxyGrUVkjwR6qUbUozjgQcbvzZog7WQ1qUK1ijYqZ9brjCrx1iasX3coQYQqAUx4nME3gN8USur:23bee48c007f111204c6b83a54d332755de1716796248af79b7fba1c323153db,2SSVqhVLz7P9S2vf4YdAVMBEEMHcFLhB8EQENxSsNcteroeYFWMabt7EiWRMvt4ibHYrjJotR3kmz1XdrvWrw3Fp:6bf4ad0ac0855024151fcaebc428e251509a840be45b6f366fb58a519d8fb350,63HUVVAWvEz3ArxCsAhdxbnQ5LEXUr6p1qXJ1E4qPBwnJWcJ8NYzYNqJf7ihH5o3pugpNfFMtxNR1NSDbjH2Kjb7:ce4ca56fa5ae2bbbe6b5f6ca91b396efec5f804c7358517f68b719c83a60903d"
IDS="ab0c66e50e98d4276b70161231b8c901b371c1b0270e9eb09bd28ce9b57b3804,6bf4ad0ac0855024151fcaebc428e251509a840be45b6f366fb58a519d8fb350,62e916786295527bd12341712c51a58208fc21b3e05b274ef2d74db2f82e2904,ffba329b4b4416a23a57e58c6e9d677d8f1da49db8b81194e9eac774f350548d,abb9782ac204e0c0e743d1dccae7bafbcfb7baeacf6c743ba5528552d8d5b86c"
echo "=== landed-via-probe $(date -u)"
taskset -c 0,2,3 $B --landed-via-probe "$LV" --config $C --env-file /root/arbx/deploy/.env < /root/.nexus-v2-trading-wallet.pass 2>&1 | grep -v "^$"
echo "=== jito-poll-probe $(date -u)"
taskset -c 0,2,3 $B --jito-poll-probe "$IDS" --config $C --env-file /root/arbx/deploy/.env < /root/.nexus-v2-trading-wallet.pass 2>&1 | grep -v "^$"
echo "=== ack-probe $(date -u)"
taskset -c 0,2,3 $B --ack-probe 3 --send-path helius --send-log /root/fix2/sends_ackprobe.jsonl --mint 5mWdoVm6PvBizx1feckWuCwy2LCrLncMqhFfvy1epump \
  --route-by-client "bam=jito-bundle+landx-fra3+staked-rpc;harmonic=harmonic-bundle+jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+staked-rpc" \
  --cu-price-micro 30000000 --cu-limit 105000 --spend-lamports 1000000 --config $C --env-file /root/arbx/deploy/.env < /root/.nexus-v2-trading-wallet.pass 2>&1 | grep -v "^$" | grep -v DETECT
echo "=== done $(date -u)"

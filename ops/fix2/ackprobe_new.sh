#!/bin/bash
# ZERO COST probes of the FIX2 code: attribution + status polls on OLD final1 signatures/bundles, and --ack-probe (junk only)
cd /root/fix2
set -a; . /root/sniper/deploy/.env; set +a
B=/root/sniper-final2/target/release/snipe_engine
C=/root/fix2/final2_landing.toml
echo "=== ack-probe $(date -u)"
taskset -c 0,2,3 $B --ack-probe 3 --send-path helius --send-log /root/fix2/sends_ackprobe.jsonl --mint 5mWdoVm6PvBizx1feckWuCwy2LCrLncMqhFfvy1epump \
  --route-by-client "bam=jito-bundle+landx-fra3+staked-rpc;harmonic=harmonic-bundle+jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+staked-rpc" \
  --cu-price-micro 30000000 --cu-limit 105000 --spend-lamports 1000000 --config $C --env-file /root/sniper/deploy/.env < /root/.nexus-v2-trading-wallet.pass 2>&1 | grep -v "^$" | grep -v DETECT
echo "=== done $(date -u)"

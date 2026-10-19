#!/bin/bash
# REVIEW: ZERO-COST ack probe (junk 4-byte requests to every routed path; the multi-tip buy is only simulated). Never --live.
D=/root/review; cd $D
set -a; . /root/arbx/deploy/.env; set +a
ROUTES="bam=jito-bundle+landx-fra3+staked-rpc;harmonic=jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+helius+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+helius+staked-rpc"
timeout 120 /root/arbx-final/target/release/snipe_engine --ack-probe 2 --send-path helius --sell-path staked-rpc --route-by-client "$ROUTES" \
  --cu-price-micro 30000000 --cu-limit 90000 --config /root/lat/final_landing.toml --env-file /root/arbx/deploy/.env \
  < /root/.nexus-v2-trading-wallet.pass > $D/ack.log 2>&1
echo "ACK_DONE $(date -u)" >> $D/ack.log

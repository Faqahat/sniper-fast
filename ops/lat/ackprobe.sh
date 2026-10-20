#!/bin/bash
# ZERO-COST ack probe of the LAT multi-path engine: routing preview, multi-tip buy build + simulateTransaction, then N
# rounds of JUNK (undecodable) requests to every routed path. Nothing can land, nothing is paid. Never add --live here.
# usage: ackprobe.sh <tag> <rounds> <mint> <creator>
TAG=${1:-after}; N=${2:-12}; MINT=$3; CREATOR=$4
cd /root/lat
set -a; . /root/sniper/deploy/.env; set +a
ROUTES="bam=jito-bundle+landx-fra3;jito=jito-bundle+landx-fra3+helius;fd=jito-bundle+astralane+landx-fra3;harmonic=nozomi+astralane+helius;agave=helius+nozomi+landx-fra3;other=helius+nozomi+landx-fra3;default=jito-bundle+helius+nozomi+landx-fra3"
/root/sniper-lat/target/release/snipe_engine --ack-probe $N --config /root/lat/lat_landing.toml --env-file /root/sniper/deploy/.env \
  --send-path helius --sell-path staked-rpc --route-by-client "$ROUTES" --send-log /root/lat/ackprobe_$TAG.jsonl \
  ${MINT:+--mint $MINT} ${CREATOR:+--creator $CREATOR} --spend-lamports 1000000 --cu-limit 90000 --cu-price-micro 10000000 \
  < /root/.nexus-v2-trading-wallet.pass > /root/lat/ackprobe_$TAG.txt 2>&1
echo "ACKPROBE_DONE $(date -u)" >> /root/lat/ackprobe_$TAG.txt

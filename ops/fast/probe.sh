#!/bin/bash
# ZERO COST: --fast-probe N junk fires (signature count 0: never a valid tx) through every path's FAST form. Never --live.
BIN=${1:-/root/sniper-lat/target/release/snipe_engine}; N=${2:-6}; OUT=${3:-/root/fast/probe.txt}; shift 3
cd /root/fast
set -a; . /root/sniper/deploy/.env; set +a
timeout 200 $BIN --snipe-once --concurrent --junk-fanout --fast-send --fast-probe $N --spend-lamports 1000000 --fill-cap 2.5 --cu-price-micro 30000000 --cu-limit 90000 \
  --send-path helius --sell-path staked-rpc --multi-send jito-bundle,landx-fra3,helius,nozomi,astralane,staked-rpc --send-log /root/fast/sends_probe.jsonl \
  --lat-trace /root/fast/trace_probe.jsonl --config /root/lat/lat_landing.toml --env-file /root/sniper/deploy/.env "$@" \
  < /root/.nexus-v2-trading-wallet.pass > $OUT 2>&1
echo "PROBE_EXIT=$?" >> $OUT

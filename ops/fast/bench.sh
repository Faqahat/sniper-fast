#!/bin/bash
# ZERO-NETWORK-SEND microbenchmark of the build stages (--fast-bench N): paths are built and warmed (keep-alives only), nothing is sent
BIN=${1:-/root/arbx-lat/target/release/snipe_engine}; N=${2:-3000}; OUT=${3:-/root/fast/bench.txt}
cd /root/fast
set -a; . /root/arbx/deploy/.env; set +a
ROUTES="bam=jito-bundle+landx-fra3+staked-rpc;harmonic=jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+helius+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+helius+staked-rpc"
timeout 300 $BIN --snipe-once --concurrent --fast-bench $N --spend-lamports 1000000 --fill-cap 2.5 --cu-price-micro 30000000 --cu-limit 90000 \
  --send-path helius --sell-path staked-rpc --route-by-client "$ROUTES" --config /root/lat/lat_landing.toml --env-file /root/arbx/deploy/.env $4 \
  < /root/.nexus-v2-trading-wallet.pass > $OUT 2>&1
echo "BENCH_EXIT=$?" >> $OUT

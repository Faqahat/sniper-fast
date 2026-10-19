#!/bin/bash
# REVIEW: ZERO-COST junk-fanout of the PATCHED review copy (dumps the real signed tx it discards). Base filter only (more fires),
# live send/tip/CU flags verbatim, no busy-poll/pin (core 1 is the other dry run's). Never --live.
MIN=${1:-8}
D=/root/review; cd $D
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=$(grep -o "KALDERA_TOKEN=[^ ]*" /root/collect_blfwd.sh | head -1 | cut -d= -f2)
export RV_DUMP=$D/rawtx.jsonl
ROUTES="bam=jito-bundle+landx-fra3+staked-rpc;harmonic=jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+helius+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+helius+staked-rpc"
timeout $(( MIN * 60 + 120 )) $D/arbx-rv/target/release/snipe_engine --snipe-once --concurrent --junk-fanout \
  --uri-blacklist --min-dev-buy 500000000 --max-dev-buy-sol 8 --dev-from-cap \
  --spend-lamports 1000000 --fill-cap 2.5 --max-sol 0.0015 --max-total-sol 1.0 --max-loss-sol 0.075 --max-inflight 2 --minutes $MIN \
  --cu-price-micro 30000000 --cu-limit 90000 --sell-cu-price-micro 1500000 --land-poll-ms 100 \
  --send-path helius --sell-path staked-rpc --route-by-client "$ROUTES" --send-log $D/sends_dump.jsonl \
  --config /root/lat/final_landing.toml --env-file /root/arbx/deploy/.env \
  --fast-send --jito-h2 --fast-presign --fast-derive --fast-verify --lat-trace $D/trace_dump.jsonl \
  < /root/.nexus-v2-trading-wallet.pass > $D/dump.log 2>&1
echo "DUMP_DONE $(date -u)" >> $D/dump.log

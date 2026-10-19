#!/bin/bash
# ===== LIVE — THE OWNER RUNS THIS, NOBODY ELSE. Real transactions, real SOL. =====
# FINAL engine (2026-10-19): /root/arbx-final (= arbx-lat speed build 9e354927 + --race-glued fix; md5 df3ca55b), feeds
# DZ leader + DZ retrans-eu + Kaldera + turbo-Kaldera + erpc backup (/root/lat/final_landing.toml), speed flags
# --fast-send --jito-h2 --fast-presign --fast-derive --busy-poll --pin-core 1. Validated zero-cost: /root/gap/NOTES.md
# BEFORE RUNNING: stop the processes listed in /root/gap/READY.txt ("STOP BEFORE LIVE") so the engine has its own cores.
# RULE = PREREG_v2 #2 (owner 2026-10-19): bundle >= 1 tx, bundle 3-5 SOL, create tip prefix moon; --race-glued = the
# bundle is the on-chain glued run (verified 0 mismatches on paper, /root/gap/NOTES.md §8.3).
# ONE multi-path landing test (/root/lat/NOTES.md): up to 10 buys of 0.001 SOL (~$0.10) on PREREG_v2 #2 launches only, each
# buy routed by its create-slot leader's client to 2-4 paths at once (ONE signature: it can land once), sold at once
# via staked-rpc. Caps: per-buy 0.0015 SOL, cumulative buy spend 0.010 SOL (= 10 buys, then it stops firing), balance
# kill-switch 0.096 SOL (~$10, owner 2026-10-19), 90 min, 2 in flight. Wallet held 0.1108 SOL at 2026-10-19 09:40 UTC.
# Before: stop any paper/dry engine and build on the box (CPU); nothing else may use the Helius keyless budget.
# usage: live_final.sh <tag>      then: python3 /root/lat/lat_measure.py /root/lat/live_land_<tag>.log /root/lat/sends_<tag>.jsonl
TAG=${1:-final1}
cd /root/lat
set -a; . /root/arbx/deploy/.env; set +a
export KALDERA_TOKEN=$(grep -o 'KALDERA_TOKEN=[^ ]*' /root/collect_blfwd.sh | head -1 | cut -d= -f2)
ROUTES="bam=jito-bundle+landx-fra3+staked-rpc;harmonic=jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+helius+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+helius+staked-rpc"
LOG=/root/lat/live_land_${TAG}.log
: > $LOG
/root/arbx-final/target/release/snipe_engine --snipe-once --concurrent --live \
  --uri-blacklist --min-dev-buy 500000000 --max-dev-buy-sol 8 \
  --dev-from-cap --race-gate --race-min-bundle 1 --race-min-bundle-sol 3 --race-max-bundle-sol 5 --race-create-tip-prefix moon --race-bundle-ms 3 --race-glued \
  --race-pros /root/race/pros.json --race-early \
  --spend-lamports 1000000 --fill-cap 2.5 --max-sol 0.0015 --max-total-sol 0.017 --max-loss-sol 0.170 --max-inflight 2 --minutes 90 \
  --cu-price-micro 30000000 --cu-limit 105000 --sell-cu-price-micro 1500000 --land-poll-ms 100 \
  --send-path helius --sell-path staked-rpc --route-by-client "$ROUTES" --send-log /root/lat/sends_${TAG}.jsonl \
  --config /root/lat/final_landing.toml --env-file /root/arbx/deploy/.env \
  --fast-send --jito-h2 --fast-presign --fast-derive --busy-poll --pin-core 1 --lat-trace /root/lat/trace_${TAG}.jsonl \
  < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1
echo "LIVE_FINAL_DONE $TAG $(date -u)" >> $LOG

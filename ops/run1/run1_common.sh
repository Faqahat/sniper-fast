#!/bin/bash
# RUN 1 of the 5-run plan (ops/comp/RUNPLAN.md, sim: ops/comp/sim_ladder.py). Shared flags for live + dry.
# Rule #2 + gates unchanged from live test 2. Changes vs live_final2.sh (all measured/simulated 2026-10-20):
#   size 1.5 SOL (--spend-lamports), fee ~0.025 SOL/buy: CU 95k x 110M uL = 0.0105 priority + Jito tip 0.012 (toml)
#   + relay tips 0.001; exit = sell ALL after --hold-ms 450 (sim: ~3 slots after landing is best at every landing
#   position; ladders/longer holds lose at our landing); entry cap --fill-cap 1.6 x dev-floor ~= <=15% over the
#   post-bundle quote for 3-5 SOL bundles; sells CU 5M; run kill -0.5 SOL (open positions at cost), profit lock
#   0.3:0 / 0.6:0.3; 20 buys (--max-total-sol 30) or 180 min; 2 in flight.
set -a; . /root/arbx/deploy/.env; set +a
: "${KALDERA_TOKEN:?KALDERA_TOKEN must be set in /root/arbx/deploy/.env}"
B=/root/arbx-run1/target/release/snipe_engine
C=/root/run1/run1_landing.toml
ROUTES="bam=jito-bundle+landx-fra3+staked-rpc;harmonic=jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+helius+staked-rpc"
FLAGS=(--uri-blacklist --min-dev-buy 500000000 --max-dev-buy-sol 8
  --dev-from-cap --race-gate --race-min-bundle 1 --race-min-bundle-sol 3 --race-max-bundle-sol 5 --race-create-tip-prefix moon --race-bundle-ms 3 --race-glued
  --race-pros /root/race/pros.json --race-early
  --close-leaders /root/fix2/close_leaders_5ms.txt --max-create-ms 150
  --spend-lamports 1500000000 --fill-cap 1.6 --max-sol 1.6 --max-total-sol 30 --max-loss-sol 0.5 --lock-tiers 0.3:0,0.6:0.3 --max-inflight 2 --minutes 180
  --cu-price-micro 110000000 --cu-limit 95000 --sell-cu-price-micro 5000000 --hold-ms 450 --land-poll-ms 100
  --sell-robust --sell-retries 2 --sell-retry-s 4 --strict-balance --jito-poll --landed-via
  --send-path helius --sell-path staked-rpc --route-by-client "$ROUTES"
  --config $C --env-file /root/arbx/deploy/.env
  --fast-send --jito-h2 --fast-presign --fast-derive --busy-poll --pin-core 1)

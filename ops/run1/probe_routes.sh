#!/bin/bash
# ===== ROUTE PROBE on the DEV wallet (FRZ) — owner-authorized 2026-10-20 ("go"). =====
# 1-lamport SELF-transfers, ONE route per probe (round-robin over --probe-paths), each carrying that route's own tip
# (probe_routes.toml: minimums, jito-bundle 0.002), the same per-CU priority as Run 1's buy (110M uL/CU), fired on
# pump.fun launches in close-leader slots. The probe's sighting in our shred feed is timed in ms after the create, the
# same way our real buys are. NO token buys. Hard cost cap --max-sol (FRZ holds ~0.109 SOL). Separate binary
# (/root/sniper-probe): the PROD/Run binary is untouched. Usage: probe_routes.sh [tag] [max SOL] [max probes]
TAG=${1:-probe1}; MAXSOL=${2:-0.09}; N=${3:-80}
B=/root/sniper-probe/snipe_engine
if pgrep -x snipe_engine > /dev/null; then echo "REFUSED: a snipe_engine is running"; exit 1; fi
LOG=/root/run1/${TAG}.log; : > $LOG
if [ "${DRY:-0}" = 1 ]; then LIVE=""; else LIVE="--live"; fi   # DRY=1: no sends at all
setsid nohup bash -c "
  $B --shadow --warm-probe-on-trigger $LIVE --max-sol $MAXSOL --max-sends $N --duration-s ${DURATION:-3600} --max-inflight 16 \
     --probe-paths staked-rpc,nozomi,astralane,helius,landx-fra3,jito-bundle --probe-log /root/run1/${TAG}.jsonl \
     --cu-price-micro 110000000 --probe-cu-limit 450 --min-dev-buy 1000000 --land-poll-ms 300 --land-timeout-ms 8000 \
     --close-leaders /root/fix2/close_leaders_5ms.txt --send-path staked-rpc \
     --config /root/run1/probe_routes.toml --env-file /root/sniper/deploy/.env \
     < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1
  echo \"PROBE_DONE ${TAG} \$(date -u)\" >> $LOG" > /dev/null 2>&1 < /dev/null &
sleep 3
echo "started engine pid $(pgrep -n -x snipe_engine) ($LIVE), log $LOG"

#!/bin/bash
# ===== BUY-SHAPED ROUTE PROBE on the DEV wallet (FRZ) — 2026-10-21, owner: "do what u have to do, u have access to FRZ" =====
# On each pump.fun launch in a close-leader slot: a REAL pump buy of that launch (Run 2's 100k CU limit, per-leader-client
# route fan-out and tips) with min_tokens_out = u64::MAX, so it always fails the slippage check on chain: it costs only the
# base + priority fee (tips revert) and never buys a token. Timed in our shred feed (ms after the create) exactly like a
# real buy. Hard caps: --max-sends N and --max-sol. Separate probe binary; the PROD/Run binary is untouched.
# usage: probe_buy.sh [tag] [max SOL] [max probes]   env: CUP (cu price uL, default 30M), DRY=1, CONFIG, DURATION, CLOSE (leader list),
#        PATHS=a,b,c (one path per probe, round-robin, instead of the buy's whole route)
TAG=${1:-pbuy1}; MAXSOL=${2:-0.03}; N=${3:-8}; CUP=${CUP:-30000000}
. /root/run1/run1_common.sh    # ROUTES (Run 2's buy routes)
B=${B:-/root/sniper-probe/snipe_engine}    # override e.g. B=/root/sniper-f2/snipe_engine_final2 (same source, has the probe flags)
if pgrep -x snipe_engine > /dev/null; then echo "REFUSED: a snipe_engine is running"; exit 1; fi
LOG=/root/run1/${TAG}.log; : > $LOG
if [ "${DRY:-0}" = 1 ]; then LIVE=""; else LIVE="--live"; fi
if [ -n "${PATHS:-}" ]; then MODE="--probe-paths $PATHS"; else MODE="--probe-route"; fi
setsid nohup bash -c "
  $B --shadow --warm-probe-on-trigger $LIVE --max-sol $MAXSOL --max-sends $N --duration-s ${DURATION:-3600} --max-inflight 4 \
     $MODE --probe-buy --route-by-client '$ROUTES' --probe-log /root/run1/${TAG}.jsonl \
     --cu-limit 100000 --cu-price-micro $CUP --spend-lamports 1000000 --min-dev-buy 500000000 --land-poll-ms 300 --land-timeout-ms 8000 \
     --close-leaders ${CLOSE:-/root/fix2/close_leaders_5ms.txt} --send-path staked-rpc \
     --config ${CONFIG:-/root/run1/edge_landing_nodz.toml} --env-file /root/sniper/deploy/.env \
     < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1
  echo \"PROBE_DONE ${TAG} \$(date -u)\" >> $LOG" > /dev/null 2>&1 < /dev/null &
sleep 3
echo "started engine pid $(pgrep -n -x snipe_engine) (${LIVE:-dry}), log $LOG"

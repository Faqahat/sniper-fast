#!/bin/bash
# 2026-10-23 PKT: copy of /root/run1/probe_buy.sh with a route override. Owner OK (22:30 PKT): stop the server paper engine for
# ~30 min, run 10 fail-by-design probes from the DEV wallet (FRZ), ~0.03 SOL, then restart the paper engine.
# ROUTES_OVERRIDE = one landing service per leader client, like the best dip bot HkQ7hMjy (Nozomi on BAM / Harmonic / Firedancer,
# Helius on Jito / Agave, LandX otherwise). Everything else exactly as probe_buy.sh: a real pump buy with min_tokens_out =
# u64::MAX, so it always fails on chain (no token bought, tips revert), costs base + priority fee only, timed in our shred feed.
# usage (server, root): ROUTES_OVERRIDE='...' bash /root/run1/probe_buy_hk.sh [tag] [max SOL] [max probes]
TAG=${1:-pbuy_hk1}; MAXSOL=${2:-0.035}; N=${3:-10}; CUP=${CUP:-30000000}
. /root/run1/run1_common.sh
ROUTES=${ROUTES_OVERRIDE:-$ROUTES}
B=/root/sniper-probe/snipe_engine
if pgrep -x snipe_engine > /dev/null; then echo "REFUSED: a snipe_engine is running"; exit 1; fi
LOG=/root/run1/${TAG}.log; : > $LOG
if [ "${DRY:-0}" = 1 ]; then LIVE=""; else LIVE="--live"; fi
echo "routes: $ROUTES" >> $LOG
setsid nohup bash -c "
  $B --shadow --warm-probe-on-trigger $LIVE --max-sol $MAXSOL --max-sends $N --duration-s ${DURATION:-1800} --max-inflight 4 \
     --probe-route --probe-buy --route-by-client '$ROUTES' --probe-log /root/run1/${TAG}.jsonl \
     --cu-limit 100000 --cu-price-micro $CUP --spend-lamports 1000000 --min-dev-buy 500000000 --land-poll-ms 300 --land-timeout-ms 8000 \
     --close-leaders ${CLOSE:-/root/fix2/close_leaders_5ms.txt} --send-path staked-rpc \
     --config ${CONFIG:-/root/run1/edge_landing_nodz.toml} --env-file /root/sniper/deploy/.env \
     < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1
  echo \"PROBE_DONE ${TAG} \$(date -u)\" >> $LOG" > /dev/null 2>&1 < /dev/null &
sleep 3
echo "started engine pid $(pgrep -n -x snipe_engine) (${LIVE:-dry}), log $LOG"

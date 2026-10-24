#!/bin/bash
# Daily retrain of the dip-backrun models (host, read-only on data; nothing is sent anywhere). Current best version (2026-10-23):
# spacing 5 slots, 2-slot exit (4 also tested), entries 35/50/75 ms after the sell, real follower limits where decoded.
#  1. rebuild every dip event from the latest extracted data (dipbuy5 = dipbuy4 + options; HLAG 0)
#  2. OPTIONAL (READ-ONLY RPC, set DECODE=1): decode the real slippage limits of the buys after the current picks
#     (follower_sigs2.py + core/slip_fetch.py), then rebuild, so the labels rest on real limits (estimates were ~20% optimistic)
#  3. six-block CV report, all triggers and direct-only (sanity check before trusting a new model)
#  4. freeze new models frozen_dip2r_L35 / L50 / L75 with sha256 (old ones kept with a date suffix)
# usage: bash dip_retrain.sh            (or DECODE=1 bash dip_retrain.sh; then the forward loops score the new freeze)
set -eu
cd /home/moiz/sniper/ops/overnight/dip
STAMP=$(TZ=Asia/Karachi date +%m%d_%H%M)
EV=/home/moiz/sniper/ops/overnight/dip/ev_retrain_${STAMP}.jsonl.gz
ENVB="RP_PHASEA_R2=phaseA_dry SELL_LAT=75 SLIPIMP=1 DIP_REAL_SLIP=1 DIP_LATS=35,50,75 DIP_B=0.5 DIP_HS=2,4 DIP_BUSY=5 DIP_HLAG=0"
echo "[$(TZ=Asia/Karachi date +%H:%M) PKT] building events -> $EV"
env $ENVB DIP_OUT=$EV timeout 3500 python3 -I dipbuy5.py > retrain_${STAMP}.log 2>&1
if [ "${DECODE:-0}" = "1" ]; then
  echo "[$(TZ=Asia/Karachi date +%H:%M) PKT] decoding follower limits of the current picks (read-only RPC)"
  rm -f sel_retrain_${STAMP}.jsonl
  SEL_OUT=sel_retrain_${STAMP}.jsonl DIRECT_FILE=../dipshadow/direct_flags_prelim.json DIRECT_MODE=filter EVF=$EV EXIT=2 LATS=35,50,75 Q=0.05 \
    timeout 3000 python3 -I dipcv.py > /dev/null 2>&1
  WIN=3 timeout 1800 python3 -I follower_sigs2.py sel_retrain_${STAMP}.jsonl 2>&1 | grep -v -i warn | tail -n 1
  (cd ../core && timeout 5400 python3 -I slip_fetch.py ../dip/follower_sigs2.json 2>&1 | tail -n 1)
  env $ENVB DIP_OUT=$EV timeout 3500 python3 -I dipbuy5.py > retrain_${STAMP}.log 2>&1
fi
echo "[$(TZ=Asia/Karachi date +%H:%M) PKT] six-block CV (2-slot exit, 2% guard): all triggers, then direct-only"
# note: direct flags exist only for triggers labelled so far (dipshadow/direct_flags_prelim.json); new triggers need
# dipshadow/trig_sigs.py + scan_progs.py + direct_rule.py to be labelled (local data only)
EVF=$EV EXIT=2 LATS=35,50,75 GUARDS=1.02 timeout 3000 python3 -I dipcv.py 2>&1 | grep -E "^LAT|all blocks"
DIRECT_FILE=../dipshadow/direct_flags_prelim.json DIRECT_MODE=filter EVF=$EV EXIT=2 LATS=35,50,75 GUARDS=1.02 timeout 3000 python3 -I dipcv.py 2>&1 | grep -E "^LAT|all blocks"
for L in 35 50 75; do
  f=frozen_dip2r_L$L
  [ -f $f.json ] && cp $f.json ${f}_until_${STAMP}.json && cp $f.json.sha256 ${f}_until_${STAMP}.json.sha256 || true
  TAG=dip2r EXIT=2 LAT=$L EVF=$EV timeout 900 python3 -I dipfreeze4.py 2>&1 | grep -v -i warning
done
echo "[$(TZ=Asia/Karachi date +%H:%M) PKT] done. fwd_dip_direct_loop.sh scores only dips after the new freeze time."

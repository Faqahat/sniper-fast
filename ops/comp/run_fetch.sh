#!/bin/bash
# usage: run_fetch.sh SET [TH] [EP_RPS] [LIM] [CAPTX]
cd /root/comp
set -a; . /root/arbx/deploy/.env; set +a
SET=$1; TH=${2:-6}; RPS=${3:-15}; LIM=${4:-100000}; CAP=${5:-3000}
EP_RPS_CK=${CK:-35} EP_RPS_RMR=${RMR:-6} EP_RPS_SHYFT=${SHY:-7} TH=$TH EP_RPS=$RPS LIM=$LIM CAPTX=$CAP setsid nohup nice -n 19 python3 /root/comp/fetch_tapes.py $SET >> /root/comp/fetch_${SET}.log 2>&1 < /dev/null &

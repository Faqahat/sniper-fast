#!/bin/bash
# HOST side: copy the race output back (after the race stopped; safe while running too: a partial copy).
#   bash ck_fetch.sh [RUN_DIR=/home/moiz/sniper-data/preconf/<YYYYMMDD PKT today>]   -> RUN_DIR/ck/
set -euo pipefail
FRA=${FRA:-it@84.32.100.36}; P=${FRA_PORT:-1996}
RD=${1:-/home/moiz/sniper-data/preconf/$(TZ=Asia/Karachi date +%Y%m%d)}
mkdir -p "$RD/ck"
ssh -p "$P" -o ConnectTimeout=10 -o BatchMode=yes "$FRA" "sudo tar -C /root/shreder/ck/out -czf - ." | tar -xzf - -C "$RD/ck"
ls -la "$RD/ck"

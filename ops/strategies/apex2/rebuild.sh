#!/bin/bash
# APEX2: rebuild the probe watchlist from the raw collect tape (read-only on the tape).
# Steps: decode new chunks (cached) -> merge per run -> creator counts -> position sim -> watchlist.json
# usage: rebuild.sh [RUN ...]   (default: every run_* dir in sniper-data/collect that has txs/, oldest first)
set -e
ulimit -v 6000000
A=/home/it/sniper/ops/strategies/apex2; C=/data/tapes/collect; D=/home/it/sniper-data/apex2
RUNS="$@"
[ -z "$RUNS" ] && RUNS=$(cd $C && ls -d run_2026*_* | grep -v '\.' | while read r; do [ -d $C/$r/txs ] && [ "$(ls $C/$r/txs | head -1)" ] && echo $r; done)
ARGS=""; for r in $RUNS; do ARGS="$ARGS $C/$r"; done
python3 $A/x1_extract.py $D/x $ARGS --procs 3 > $D/x1_rebuild.log 2>&1
for r in $RUNS; do python3 $A/b1_build.py $r > /dev/null; done
python3 $A/s0_creators.py
for r in $RUNS; do python3 $A/s1_sim.py $r --procs 3 | grep -E "saved|ERR"; done
python3 $A/w1_watchlist.py A

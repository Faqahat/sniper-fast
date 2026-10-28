#!/bin/bash
# run the r4 grid for the given days (sequentially). usage: run_grid.sh TAG DRAWS CFGFILE DAY [DAY ...]
cd "$(dirname "$0")"
TAG=$1; DR=$2; CF=$3; shift 3
for d in "$@"; do python3 r4_days.py "$d" --cfgs "$(cat "$CF")" --draws "$DR" --tag "$TAG"; done

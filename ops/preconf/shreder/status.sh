#!/bin/bash
# HOST: status of everything on FRA (recorder msgs/s per stream, projected GB/h, CPU, disk, collector lag, CK race).
# usage: status.sh [RUN]   (default: the run started last by start_all.sh)
H=$(dirname "$(readlink -f "$0")")
RUN=${1:-$(cat /home/moiz/sniper-data/preconf/CURRENT_RUN 2>/dev/null)}
echo "== $(TZ=Asia/Karachi date +%H:%M:%S) PKT recorder ($RUN)"
ssh -o BatchMode=yes -o ConnectTimeout=10 -p 1996 it@84.32.100.36 "sudo /root/shreder/rec_status.sh $RUN"
if [ -x "$H/ck/ck_status.sh" ]; then echo "== Constant-K feed race"; bash "$H/ck/ck_status.sh"; fi

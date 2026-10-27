#!/bin/bash
# HOST: stop the recorder (graceful SIGTERM) and the CK race, then take the end clock probe. Deletes nothing.
# (Both stop by themselves after MINUTES anyway; this is for an early stop.)
H=$(dirname "$(readlink -f "$0")")
RUN=${1:-$(cat /home/moiz/sniper-data/preconf/CURRENT_RUN 2>/dev/null)}
DATE=${RUN#trial_}; HD=/home/moiz/sniper-data/preconf/$DATE; mkdir -p "$HD/fra"
ssh -o BatchMode=yes -o ConnectTimeout=10 -p 1996 it@84.32.100.36 "sudo /root/shreder/stop_rec.sh $RUN"
[ -x "$H/ck/ck_stop.sh" ] && bash "$H/ck/ck_stop.sh"
python3 -I "$H/clock_probe.py" "$HD/fra/clock_end.json" --n 40

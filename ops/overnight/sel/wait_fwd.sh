#!/bin/bash
# wait until forward pass number N (counted by its top4 block) is complete in sel_forward.log, then print a compact summary
N=$1; F=/home/moiz/sniper/ops/overnight/sel/sel_forward.log
while true; do
  c=$(grep -c "== top4 hour by hour" $F)
  if [ "$c" -ge "$N" ] && [ "$(awk -v n=$N '/== top4 hour by hour/{k++} k==n && /tokens we got filled/{print "y"}' $F)" = "y" ]; then break; fi
  sleep 30
done
awk -v n=$N '/forward run/{r++} r==n' $F | grep -E "forward run|IMIT1 top|TEST |TOTAL|35 ms: fills|50 ms: fills|75 ms: fills|tokens we got filled" | sed -n '1,40p'

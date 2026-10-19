#!/bin/bash
cd /root/arbx-fast
while true; do
  n=$(grep -c "PAPER launch #" paper_sel.log)
  if [ "$n" -ge 50 ]; then
    pkill -f "snipe_engine --paper-trade"
    pkill -f "paper_sel.sh"
    echo "PAPER_SEL_DONE stopped at tracked=$n $(date -u)" >> paper_sel.log
    break
  fi
  sleep 20
done

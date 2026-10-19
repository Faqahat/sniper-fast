#!/bin/bash
# every 1 s: fd -> what (socket peer from ss, else the /proc fd link: file / eventfd / pipe)
PID=$1; OUT=$2
while kill -0 $PID 2>/dev/null; do
  echo "T $(date +%s%N)" >> $OUT
  ss -tunpH 2>/dev/null | grep "pid=$PID," | sed -E 's/^(tcp|udp) .* ([0-9.:\[\]a-f*]+) +([0-9.:\[\]a-f*]+) +users:.*fd=([0-9]+).*/S \4 \1 \3/' >> $OUT
  for f in /proc/$PID/fd/*; do n=${f##*/}; [ $n -gt 2 ] && echo "L $n $(readlink $f)"; done >> $OUT 2>/dev/null
  sleep 1
done

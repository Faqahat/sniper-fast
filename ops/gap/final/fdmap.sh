#!/bin/bash
# every 2 s: the engine's socket fds -> remote address (tcp + udp), for matching bpftrace writes to send paths
PID=$1; OUT=$2
while kill -0 $PID 2>/dev/null; do
  echo "T $(date +%s%N)" >> $OUT
  ss -tunpH 2>/dev/null | grep "pid=$PID," | sed -E 's/.* ([0-9.:\[\]a-f]+) +([0-9.:\[\]a-f]+) +users:.*fd=([0-9]+).*/\3 \2/' >> $OUT
  sleep 2
done

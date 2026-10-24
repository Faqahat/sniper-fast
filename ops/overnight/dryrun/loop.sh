#!/bin/bash
# dry-run loop: a cycle every 15 minutes until stopped (kill the loop PID in loop.pid)
echo $$ > /home/moiz/sniper/ops/overnight/dryrun/loop.pid
while true; do /home/moiz/sniper/ops/overnight/dryrun/cycle.sh >> /home/moiz/sniper/ops/overnight/dryrun/cycle.log 2>&1; sleep 900; done

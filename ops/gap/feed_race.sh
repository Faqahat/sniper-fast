#!/bin/bash
# Feed race: which shred feed delivers first. ZERO COST: subscribes only, never sends anything.
#   /root/gap/feed_race.sh <minutes> [tag] [feed1,feed2,...]
# Config: /root/gap/feed_race.toml (enable the "constantk" or "constantk-grpc" block there).
# Output: /root/gap/race/race_<tag>.log (raw), live_<tag>.txt (refreshed every 60 s), summary_<tag>.txt (final).
# Secrets: tokens are passed by env var NAME only; nothing here prints them.
set -u
MIN=${1:?usage: feed_race.sh <minutes> [tag] [feeds]}
TAG=${2:-$(date -u +%m%d_%H%M)}
FEEDS=${3:-}
D=/root/gap/race; mkdir -p $D
BIN=${BIN:-/root/gap/bin/feed_race}
CFG=${CFG:-/root/gap/feed_race.toml}
# KALDERA_TOKEN lives in collect_blfwd.sh (export line), not in .env: load it without echoing
eval "$(grep -m1 '^export KALDERA_TOKEN=' /root/collect_blfwd.sh)" 2>/dev/null
# leader book (client class per slot); refresh if older than 6 h
if [ ! -s /root/gap/leaders.json ] || [ $(( $(date +%s) - $(stat -c %Y /root/gap/leaders.json) )) -gt 21600 ]; then
  python3 /root/gap/leaders.py /root/gap/leaders.json 2>&1 | tail -1
fi
# UDP feeds: make sure the port is open (only if a firewall is active; adds an ACCEPT for that port only)
for P in $(grep -A6 'kind *= *"udp-shreds"' $CFG | grep -B6 'enabled *= *true' | grep -o 'bind *= *"[^"]*"' | grep -o '[0-9]*"$' | tr -d '"'); do
  if command -v iptables >/dev/null && iptables -S INPUT 2>/dev/null | grep -q -- '-P INPUT DROP\|-j DROP\|-j REJECT'; then
    iptables -C INPUT -p udp --dport $P -j ACCEPT 2>/dev/null || iptables -I INPUT -p udp --dport $P -j ACCEPT
    echo "firewall: udp $P open"
  fi
done
ARGS=(--config $CFG --out $D/race_$TAG.log --minutes $MIN)
[ -n "$FEEDS" ] && ARGS+=(--feeds $FEEDS)
echo "feed race $TAG: $MIN min -> $D/race_$TAG.log (live report: $D/live_$TAG.txt)"
$BIN "${ARGS[@]}" 2> $D/race_$TAG.err &
PID=$!
echo -500 > /proc/$PID/oom_score_adj 2>/dev/null
trap 'kill -TERM $PID 2>/dev/null' INT TERM
while kill -0 $PID 2>/dev/null; do
  sleep 60
  python3 /root/gap/race_report.py $D/race_$TAG.log > $D/live_$TAG.tmp 2>&1 && mv $D/live_$TAG.tmp $D/live_$TAG.txt
  echo "---- $(date -u +%H:%M:%S) live ($TAG)"; sed -n '/pump.fun CREATES/,/^$/p' $D/live_$TAG.txt | head -14
  grep -h "reconnect\|error" $D/race_$TAG.err | tail -2
done
wait $PID
python3 /root/gap/race_report.py $D/race_$TAG.log > $D/summary_$TAG.txt 2>&1
echo "==== final: $D/summary_$TAG.txt"; cat $D/summary_$TAG.txt

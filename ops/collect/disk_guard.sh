#!/usr/bin/env bash
# Disk guard: container + both servers. Prints one status line.
# Exit 0 = all below 85%; exit 1 = at least one at/above 85% (alert);
# exit 2 = a server could not be read. The 95% cap itself is enforced by
# ops/collect/keeper.sh (it pauses recording copies); this only reports.
set -u
u=$(df --output=pcent /home/moiz | tail -1 | tr -dc '0-9')
f=$(ssh -p 1996 -o ConnectTimeout=10 -o BatchMode=yes it@84.32.100.36 "df --output=pcent / | tail -1 | tr -dc '0-9'" 2>/dev/null)
a=$(ssh -p 1996 -o ConnectTimeout=10 -o BatchMode=yes it@84.32.104.202 "df --output=pcent / | tail -1 | tr -dc '0-9'" 2>/dev/null)
line="container ${u:-?}% | FRA ${f:-?}% | AMS ${a:-?}%"
rc=0
for v in "$u" "$f" "$a"; do
  if [ -z "$v" ]; then rc=2; continue; fi
  if [ "$v" -ge 85 ]; then rc=1; fi
done
if [ -n "$u" ] && [ "$u" -ge 95 ]; then line="$line | CAP: container >= 95%, keeper paused recording copies"; fi
echo "$line"
exit $rc

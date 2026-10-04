#!/bin/bash
# Copy one finished long-run segment from Cherry (everything, raw entries archive included: the backup lives here too)
# once its logs are compressed, then join it (stage1). usage: pull.sh <segment name, e.g. long-1-p1>
set -e
cd /home/moiz/arbed/arb-lab/runs-long
S=$1
for i in $(seq 1 60); do
  st=$(timeout 20 ssh -o BatchMode=yes root@84.32.59.15 "cd ~/arb-lab/runs/$S 2>/dev/null || exit 3; pgrep -f 'name $S( |$)' >/dev/null && echo running; ls exec.jsonl rivals.jsonl txarr.log poh.log moves.log 2>/dev/null | grep -q . && echo busy; ls exec.jsonl.zst rivals.jsonl.zst txarr.log.zst poh.log.zst moves.log.zst >/dev/null 2>&1 && echo packed" || true)
  if echo "$st" | grep -q packed && ! echo "$st" | grep -qE "busy|running"; then break; fi
  sleep 20
done
mkdir -p "$S"
timeout 900 ssh -o BatchMode=yes root@84.32.59.15 "cd ~/arb-lab/runs/$S && nice tar cf - --exclude=entries.zst ." | tar xf - -C "$S"
echo "pulled $S: $(du -sh $S | cut -f1)"
python3 stage1.py "$S"

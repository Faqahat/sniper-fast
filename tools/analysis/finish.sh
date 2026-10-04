#!/bin/bash
# After the long run: pull the last segments, leaders for every slot, all stages, platforms, bundles, report data.
set -x
cd /home/moiz/arbed/arb-lab/runs-long
SEGS=$(ls -d long-1-p* 2>/dev/null | grep -v leaders | sort -V)
for s in $(timeout 30 ssh -o BatchMode=yes root@84.32.59.15 'cd ~/arb-lab/runs && ls -d long-1-p*/ | tr -d /'); do
  [ -f "$s/joined.jsonl.gz" ] || ./pull.sh "$s"
done
SEGS=$(ls -d long-1-p*/ | tr -d / | sort -V)
timeout 1500 ssh -o BatchMode=yes root@84.32.59.15 'cd ~/arb-lab && nice python3 leaders.py long-1 2>&1 | tail -3'
scp -q -o BatchMode=yes root@84.32.59.15:/root/arb-lab/runs/long-1-leaders.json .
python3 stage2.py $SEGS > stage2.out 2>&1
python3 stage3.py long-1-leaders.json $SEGS > stage3.out 2>&1
python3 stage4.py $SEGS > stage4.out 2>&1
python3 race_by_leader.py long-1-leaders.json > race.out 2>&1
# triggers behind the top winners' wins (and a baseline of everyone's) for the platform fingerprint
python3 - <<'PY'
import json, gzip, collections, random
bots = json.load(open("bots.json"))
top = [b["signer"] for b in sorted(bots.values(), key=lambda b: -b["wins"]) if b["kind"] == "winner"][:15]
by = collections.defaultdict(list); allt = []
for l in gzip.open("wins.jsonl.gz", "rt"):
    w = json.loads(l)
    if not w["trig"]: continue
    allt.append(w["trig"]["sig"])
    if w["signer"] in top and len(by[w["signer"]]) < 40: by[w["signer"]].append(w["trig"]["sig"])
random.seed(1); by["ALL WINS (baseline)"] = random.sample(allt, min(200, len(allt)))
json.dump(by, open("trigs.json", "w"))
PY
scp -q -o BatchMode=yes trigs.json root@84.32.59.15:/root/arb-lab/runs/trigs.json
scp -q -o BatchMode=yes platforms.py root@84.32.59.15:/root/arb-lab/platforms.py
timeout 1800 ssh -o BatchMode=yes root@84.32.59.15 'cd ~/arb-lab && nice python3 platforms.py > runs/platforms.out 2>&1; tail -20 runs/platforms.out'
scp -q -o BatchMode=yes root@84.32.59.15:/root/arb-lab/runs/platforms.json .
python3 bundles.py 25 15 > bundles.out 2>&1
echo FINISHED

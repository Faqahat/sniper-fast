#!/bin/bash
# After both overnight PAPER runs end: final on-chain labelling (fast), then every evaluation (READ-ONLY).
cd /root/race
set -a; . /root/sniper/deploy/.env; set +a
for p in $(ps -eo pid,args | grep "[c]hain_loop.sh night" | awk '{print $1}'); do kill $p; done
export NOB_RPS=14
python3 onchain.py /root/race/night_onchain.jsonl 8 /root/race/paper_night.log > final_onchain_night.log 2>&1
# mnight: reuse the night cache for the same mints, fetch the rest
python3 - <<PY
import json, re
want=set(re.findall(r"RACE seen slot=\d+ mint=(\w+)", open("/root/race/paper_mnight.log", errors="replace").read()))
have=set()
try:
    for l in open("/root/race/mnight_onchain.jsonl"):
        have.add(json.loads(l)["mint"])
except FileNotFoundError: pass
with open("/root/race/mnight_onchain.jsonl","a") as fh:
    for l in open("/root/race/night_onchain.jsonl"):
        try: r=json.loads(l)
        except Exception: continue
        if r["mint"] in want and r["mint"] not in have:
            fh.write(l if l.endswith("\n") else l+"\n"); have.add(r["mint"])
print("mnight seeded from night cache:", len(have), "of", len(want))
PY
python3 onchain.py /root/race/mnight_onchain.jsonl 8 /root/race/paper_mnight.log > final_onchain_mnight.log 2>&1
python3 eval_night.py night > eval_night.txt 2>&1
python3 eval_night.py mnight > eval_mnight.txt 2>&1
python3 score_run.py night > score_night.txt 2>&1
python3 score_run.py mnight > score_mnight.txt 2>&1
python3 eval_rank.py night > eval_rank_night.txt 2>&1
python3 eval_rank.py mnight > eval_rank_mnight.txt 2>&1
python3 tweets_fwd.py > tweets_fwd.txt 2>&1
python3 landing_study.py > landing_study.txt 2>&1
echo FINAL_STEPS_DONE > final_steps.done

#!/bin/bash
# READ-ONLY pipeline: snapshot -> build -> search -> agg -> whale -> final -> profile
cd /root/racedeep
cp /root/race/paper_night.log /root/race/night_onchain.jsonl /root/race/paths_night.jsonl snap/
python3 build.py > build.log 2>&1
python3 search.py > search.log 2>&1
python3 agg.py 0.4 > agg_p40.txt 2>&1
python3 agg.py "S1 front" > agg_s1front.txt 2>&1
python3 agg.py "S+100" > agg_s100.txt 2>&1
python3 whale.py > whale.txt 2>&1
python3 whale2.py > whale2.txt 2>&1
python3 final.py > final.txt 2>&1
python3 profile.py > profile.txt 2>&1
date -u > run_all.done

#!/bin/sh
# SPEED TRUTH pipeline (read-only; local files only). Outputs in /home/moiz/sniper-data/speed_truth/
set -e
cd "$(dirname "$0")"
O=/home/moiz/sniper-data/speed_truth
nice python3 a1_engine.py
# a2 needs the raw-file index (first slot per file): rebuild it when new raw files arrived
nice python3 a2_chain.py > $O/a2_chain.log 2>&1
nice python3 a3_timeline.py
nice python3 a4_analysis.py > $O/analysis.txt
nice python3 a5_feedclock.py > $O/feedclock.txt
nice python3 a6_rank.py > $O/rank.txt
nice python3 a7_export.py

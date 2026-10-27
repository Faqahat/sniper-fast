#!/bin/bash
# INSTANT-BOTS study: the whole read-only pipeline for one collector run (local files only).
# usage: bash run_pipeline.sh RUN_DIR TAG     (outputs /home/moiz/sniper-data/presend_instant/<TAG>_*)
set -e
RUN=$1; TAG=$2; D=/home/moiz/sniper-data/presend_instant; S=/home/moiz/sniper/ops/strategies/presend/instant
cd $S
nice -n 15 python3 -I i1_extract.py $RUN $D/x_$TAG 5 | tail -1
nice -n 15 python3 -I i4_census.py $D/x_$TAG $D/$TAG 3
nice -n 15 python3 -I i5_followers.py $D/$TAG 4 0.3 40 > $D/${TAG}_followers_d4_g40.txt
nice -n 15 python3 -I i6_wallet_txs.py $RUN $D/cand_wallets.json $D/${TAG}_wtx.jsonl.gz 5 | tail -1
nice -n 15 python3 -I i7_profiles.py $D/${TAG}_wtx.jsonl.gz $D/${TAG}_followers_d4_g40.json $D/${TAG}_profiles.json > $D/${TAG}_profiles.txt
nice -n 15 python3 -I i8_windows.py $RUN $D/${TAG}_followers_d4_g40.json $D/${TAG}_win.jsonl.gz 5 40 | tail -1
nice -n 15 python3 -I i9_classify.py $D/${TAG}_followers_d4_g40.json $D/${TAG}_win.jsonl.gz $D/${TAG}_classes.json > $D/${TAG}_classes.txt
echo PIPELINE_DONE $TAG

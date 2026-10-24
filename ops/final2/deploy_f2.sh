#!/bin/bash
# COPY ONLY (no start): the FINAL-2 build to the server's /root/sniper-f2. Run from the host. Needs the owner's OK.
# Starts nothing; models + seed are copied from the running shadow (/root/sniper-shadow) on the server.
set -e
H=it@84.32.100.36; P=1996
ssh -p $P $H 'mkdir -p /tmp/f2'
scp -P $P ~/sniper-data/work/final2/snipe_engine_final2 ~/sniper-data/work/final2/scorer.py ~/sniper/ops/shadow/final_config2.json ~/sniper/ops/final2/paper_f2.sh ~/sniper/ops/final2/live_f2.sh $H:/tmp/f2/
ssh -p $P $H 'sudo mkdir -p /root/sniper-f2 && sudo cp /tmp/f2/* /root/sniper-f2/ && sudo chmod +x /root/sniper-f2/snipe_engine_final2 /root/sniper-f2/paper_f2.sh /root/sniper-f2/live_f2.sh && sudo cp /root/sniper-shadow/frozen_live3_fsell.json /root/sniper-shadow/frozen_dump2.json /root/sniper-shadow/frozen_live2_fsell.json /root/sniper-shadow/shadow_seed.json /root/sniper-f2/ && sudo md5sum /root/sniper-f2/snipe_engine_final2'

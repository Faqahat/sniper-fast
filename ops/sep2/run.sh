#!/bin/bash
set -a; . /root/sniper/deploy/.env; set +a
cd /root/sep2
echo "START $(date)" > feat.out
python3 -u feat.py >> feat.out 2>&1
echo "END $(date)" >> feat.out

#!/bin/bash
cd /root/sniper-fast
set -a; . /root/sniper/deploy/.env; set +a
: > /root/sniper-fast/hisbuys_results.jsonl
exec python3 -I /root/hisbuys_paper.py

#!/bin/bash
cd /root/arbx-fast
set -a; . /root/arbx/deploy/.env; set +a
: > /root/arbx-fast/hisbuys_results.jsonl
exec python3 -I /root/hisbuys_paper.py

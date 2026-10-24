#!/bin/bash
# READ-ONLY offline pipeline over the cached txs (+3 RPC reads in final.py). Order matters.
cd /home/moiz/sniper/ops/overnight/dkmjeg
python3 -I parse.py && python3 -I ledger_an.py > ledger_an.txt && python3 -I infra.py > infra.txt && python3 -I exits.py > exits.txt \
 && python3 -I final.py > final.txt && python3 -I crosscheck.py > crosscheck.txt && python3 -I svc_slip.py > svc_slip.txt && echo PIPELINE OK

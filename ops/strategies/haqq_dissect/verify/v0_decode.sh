#!/bin/bash
# verify: link fresh recording chunks (>= 1793131532; the first one is pre-tape context) and decode them (2 procs)
SRC=/home/moiz/sniper-data/collect/run_20261027_1410/txs
V=/home/moiz/sniper-data/haqq_dissect/verify
mkdir -p $V/rec/txs $V/dec && cd $V/rec/txs && for f in $SRC/txs_*.jsonl.gz; do b=$(basename $f); t=${b#txs_}; t=${t%.jsonl.gz}; if [ $t -ge 1793131532 ]; then ln -sf $f $b; fi; done
python3 /home/moiz/sniper/ops/strategies/presend/real/decode.py $V/dec $V/rec --min-age 240 --procs 2

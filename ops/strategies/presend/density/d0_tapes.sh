#!/bin/bash
# DENSITY step 0 (read-only on the raw recordings): chain tapes for AMS runs 24, 25, 26 with the unchanged real/decode.py + real/build.py
# (runs 27 and 28 reuse filter/live27/tab and filter/live28/tab). Chunks = FRA's recording run_20261026_1415, the run span +- 10 min.
set -e
D=/home/moiz/sniper-data/presend_density
REC=/home/moiz/sniper-data/collect/run_20261026_1415
REAL=/home/moiz/sniper/ops/strategies/presend/real
mkdir -p $D/rec/run_20261026_1415/txs $D/dec
# run spans (unix s, from the records' first / last "t"): r24 1793033244-1793051843, r25 1793051917-1793063365, r26 1793066305-1793091790
for f in $REC/txs/txs_*.jsonl.gz; do
  t=$(basename $f .jsonl.gz); t=${t#txs_}
  if [ $t -ge 1793032300 ] && [ $t -le 1793092400 ]; then ln -sf $f $D/rec/run_20261026_1415/txs/; fi
done
ls $D/rec/run_20261026_1415/txs | wc -l
python3 $REAL/decode.py $D/dec $D/rec/run_20261026_1415 --min-age 0 --procs 12 > $D/decode.log 2>&1
for spec in "24 1793032644 1793052443" "25 1793051317 1793063965" "26 1793065705 1793092390"; do
  set -- $spec; r=$1; a=$2; b=$3
  mkdir -p $D/dec_r$r
  for f in $D/dec/*.npz; do
    t=$(basename $f .npz); t=${t##*txs_}
    if [ $((t + 300)) -ge $a ] && [ $t -le $b ]; then ln -sf $f $D/dec_r$r/; fi
  done
  python3 $REAL/build.py $D/dec_r$r $D/tab_r$r > $D/build_r$r.log 2>&1
  cat $D/build_r$r.log
done
echo ALLDONE

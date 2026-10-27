#!/bin/bash
# build M2 rows at each size, extract the picks' rows, delete the big per-size npz (own folder only)
cd /home/moiz/sniper/ops/strategies/haqq_size
D=/home/moiz/sniper-data/haqq_size/m2
for S in 0.25 0.35 0.45 0.65 0.8 1 1.25 1.5; do
  DD_SIZE=$S python3 c0_m2build.py > $D/build_$S.log 2>&1 || { echo "build $S failed"; continue; }
  python3 c1_m2rows.py $D/dd1_HQ_s$S.npz $S >> $D/rows.log 2>&1 && rm -f $D/dd1_HQ_s$S.npz
  echo "size $S done"
done

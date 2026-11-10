#!/bin/bash
# build M2 candidate sets (reuses /home/it/sniper-studies/sniper-m2v4/build.py unchanged) per collect-run tape
D=/home/it/sniper-data/reactguard
for t in $D/tape_*; do r=${t##*tape_}; [ -f $D/c_${r}_cand.npz ] && continue
  python3 /home/it/sniper-studies/sniper-m2v4/build.py $t $D/c_$r 12 >> $D/build.log 2>&1; done
echo DONE >> $D/build.log

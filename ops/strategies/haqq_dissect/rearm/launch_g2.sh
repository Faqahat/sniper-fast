#!/bin/bash
# launch the reduced grid (24 configs x 7 days, 1 draw) in 3 background groups
cd "$(dirname "$0")"
SP=/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/hd_rearm
G=""; for x in any 0.02 0.05; do for g in 10 50; do for a in 30 120; do for k in 2 4; do G="$G,$x:$g:$a:$k:0"; done; done; done; done; echo "${G#,}" > $SP/grid2.txt
D=/home/moiz/sniper-data/haqq_dissect/rearm
nohup ./run_grid.sh g2 1 $SP/grid2.txt 0 3 6 > $D/r4_g2_a.log 2>&1 &
nohup ./run_grid.sh g2 1 $SP/grid2.txt 1 4 > $D/r4_g2_b.log 2>&1 &
nohup ./run_grid.sh g2 1 $SP/grid2.txt 5 2 > $D/r4_g2_c.log 2>&1 &

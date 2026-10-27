#!/bin/bash
# full rebuild of the exit study after the e02 fix (models + every table); logs in /home/moiz/sniper-data/exits/
set -e
cd /home/moiz/sniper/ops/dip/exits
X=/home/moiz/sniper-data/exits
P="nice -n 10 python3 -I"
( $P e04b_learn.py h1248 1,2,4,8 3 1000 20 U 1 > $X/e04b_h1248.log 2>&1; $P e04b_learn.py h1248s3 1,2,4,8 3 1000 20 U 3 > $X/e04b_h1248s3.log 2>&1; $P e04b_learn.py h24816 2,4,8,16 3 1000 20 U 1 > $X/e04b_h24816.log 2>&1 ) &
( $P e04b_learn.py h1248s2 1,2,4,8 3 1000 20 U 2 > $X/e04b_h1248s2.log 2>&1; $P e04b_learn.py h12 1,2 3 1000 20 U 1 > $X/e04b_h12.log 2>&1 ) &
wait
$P e04c_ens.py > $X/e04c.log 2>&1
$P e09_distill.py h1248 > $X/e09.log 2>&1
$P e03_baselines.py > $X/e03.log 2>&1
$P e08_rules.py > $X/e08.log 2>&1
$P e10_select.py > $X/e10.log 2>&1
$P e14_cut.py > $X/e14.log 2>&1
$P e11_theta.py > $X/e11.log 2>&1
$P e12_crowd.py > $X/e12.log 2>&1
$P e13_split.py > $X/e13.log 2>&1
$P e15_reverse.py > $X/e15.log 2>&1
$P e16_final.py > $X/e16.log 2>&1
$P e17_export.py > $X/e17.log 2>&1
$P e07_live_eval.py h1248 > $X/e07.log 2>&1
$P e05_report.py h1248,ENS3 > $X/e05.log 2>&1
echo ALLDONE > $X/run_all.done

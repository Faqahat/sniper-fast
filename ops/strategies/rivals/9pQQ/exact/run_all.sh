#!/bin/bash
# 9pQQ EXACT-RULES: rebuild everything. Read-only on recordings; writes exact/ (this folder) + sniper-data/rivals/9pQQ/exact.
# Needs the first dissection's tape + trips (../run_all.sh). Train 10-28+10-30, choose 10-31, test 11-02.
set -e; cd "$(dirname "$0")"; ulimit -v 7500000
C=/home/moiz/sniper-data/collect; RUNS="run_20261028_1405 run_20261030_1355 run_20261031_1350 run_20261102_1250"
python3 dm_build.py                       # decision moments + labels (buy while flat / sell while holding)
python3 h0_hard.py                        # hard rules
python3 h1_leaders.py && python3 h1_test.py   # H1 leader wallets
python3 h2_fp.py                          # H2 fingerprints, decoded amounts, slippage
python3 t1_timer.py                       # reactive vs timer
python3 p1_txmeta.py $C/run_20261028_1405 $C/run_20261030_1355 $C/run_20261031_1350 $C/run_20261102_1250
python3 p2_join.py && python3 p3_route.py && python3 dm_route.py   # H1b trigger route classes
python3 e1_rules.py final                 # H3 simple exit rules
python3 b1_tree.py 6 yb_imm 0.05 > b1_tree.txt; python3 s1_tree.py 6 ys_imm 0.15 > s1_tree.txt   # H4/H3 rule lists (frozen on 10-31, scored 11-02)
python3 g1_bound.py b rt noglobal final; python3 g1_bound.py s rt noglobal final               # GBDT upper bound
for r in $RUNS; do python3 c1_calib.py $r; done                                                  # P&L machinery calibration
python3 sim.py run_20261028_1405 0.997 0.3 300; python3 sim.py run_20261030_1355 0.997 0.3 300  # reconstructed bot
for a in "0.997 0.3" "0.999 0.2" "0.999 0.5" "0.9995 0.3" "0.99 0.3"; do python3 sim.py run_20261031_1350 $a 600; done
python3 sim.py run_20261102_1250 0.997 0.3 600; python3 sim.py run_20261102_1250 0.9995 0.3 600
python3 s2_split.py /home/moiz/sniper-data/rivals/9pQQ/exact/sim/sim_10-31_0.997_0.3.json run_20261031_1350
python3 z_exact.py

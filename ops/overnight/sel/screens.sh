#!/bin/bash
cd /home/moiz/sniper/ops/overnight/sel
run() { timeout 2400 python3 -I sel_strat.py "$@" 2>&1 | grep -v Warn; }
run mom MOMENTUM-young 1 344 coh1
run mom MOMENTUM-young-2bots 1 344 coh2
run mom MOMENTUM-older 344 1800 coh1
run dip60 DIP-older-cohort 344 1800 coh1
run dip60 DIP-young-cohort 1 344 coh2
run mom MOMENTUM-young-win 1 344 win

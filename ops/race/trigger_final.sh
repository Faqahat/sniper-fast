#!/bin/bash
# start final_steps.sh once both overnight runs have finished
until grep -q PAPER_RACE_DONE /root/race/paper_night.log && grep -q PAPER_RACE_DONE /root/race/paper_mnight.log; do sleep 30; done
/root/race/final_steps.sh > /root/race/final_steps.log 2>&1

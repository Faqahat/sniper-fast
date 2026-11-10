#!/bin/bash
# x1: pull hold_tape / rearm_window / rearm_tape / obs_start records out of the obs files (read-only), runs r37..r42 (DEV+VAL)
R=/home/it/sniper-data/runs/ams/runs
O=/home/it/sniper-data/filters3/obsstrat/ext
one() {
  run=$1; files=$(ls $R/dip_ams_${run}.obs.jsonl.* 2>/dev/null | sort -t. -k4 -n; echo $R/dip_ams_${run}.obs.jsonl)
  LC_ALL=C grep -h -E '"ev":"(hold_tape|rearm_window|rearm_tape|obs_start)"' $files > $O/$run.obs_sel.jsonl
  echo done $run
}
export -f one; export R O
printf "%s\n" r37 r38 r39 r40 r41 r42 | xargs -P 3 -I{} bash -c 'one {}'

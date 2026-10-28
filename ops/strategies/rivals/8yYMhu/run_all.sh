#!/bin/bash
# 8yYMhu: rebuild every table in dependency order (read-only on inputs; writes only /home/moiz/sniper-data/rivals/8yYMhu/)
set -e
cd /home/moiz/sniper/ops/strategies/rivals/8yYMhu
D=/home/moiz/sniper-data/rivals/8yYMhu
for s in t1_tape.py r3_decomp.py r5_rpc.py r4_lots.py a2_trigger.py a3_attempts.py a1_claims.py a4_land.py r6_recon.py r7_days.py a5_ix.py e1_exit.py e2_exit_rule.py e3_bybot.py c1_followers.py s1_universe.py s2_takerate.py s3_rules.py s4_speed.py c2_calib.py c3_delay.py o1_ours.py o2_h2h.py o3_interact.py w1_widen.py r8_bots.py a6_t7.py x1_examples.py; do
  echo "== $s $(date -u +%H:%M:%S)"
  python3 $s > $D/log_${s%.py}.txt 2>&1 || { echo "FAILED $s"; tail -5 $D/log_${s%.py}.txt; exit 1; }
done
echo ALLDONE

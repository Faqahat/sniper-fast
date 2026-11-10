#!/bin/bash
# 9pQQ dissection: rebuild everything (read-only on recordings; writes only to sniper-data/rivals/9pQQ and this folder).
set -e
cd "$(dirname "$0")"
ulimit -v 6000000
D=/home/it/sniper-data/rivals/9pQQ; C=/data/tapes/collect
python3 t0_tape.py $D/tape $C/run_20261028_1405 $C/run_20261030_1355 $C/run_20261031_1350 $C/run_20261102_1250   # full tape, 4 workers
python3 a1_own.py            # its signed txs (from botpnl9 pass-1)
python3 a2_trips.py          # round trips + entry/exit context
python3 a3_clusters.py       # sub-strategies -> clusters.json
python3 a4_reentry_grad.py   # re-entries, graduations, top trades
python3 b1_buyins.py         # reaction delay, fees, tips, fails -> buyins.json
python3 e1_exit.py           # exit state rows
python3 e2_who.py            # per-wallet exit hazard
python3 e3_sellers.py        # exit hazard by seller type
python3 s1_universe.py       # selection universe
python3 s2_takerate.py       # take rates -> takerate.json
python3 s3_imitate.py        # imitation GBDT -> imitate.json
python3 i1_interact.py       # with us / other bots -> interact.json
python3 i2_ours_k.py         # our real trips by 9pQQ token history -> ours_k.json
python3 r1_replica.py        # its picks+exit at our landing -> replica.json
python3 r2_exitrule.py 70    # simple exit rules -> exitrule_70.json
python3 r3_exitml.py 70      # learned exit -> exitml_70.json
python3 r4_exitshift.py      # exit timing sensitivity -> exitshift.json
python3 r5_k9filter.py       # 9pQQ-attention on generic dumps -> k9filter.json
python3 z_summary.py         # -> 9pqq.json

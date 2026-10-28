#!/bin/bash
# run every family ablation in parallel (one process each), main model + rules in another
S=/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/e2x1_select2
cd /home/moiz/sniper/ops/strategies/e2x1_dissect/select2
for f in MKT WAL TX TOK OWN CRE TIM; do NOSIB=1 ABL=$f nice python3 t6_model.py y main > $S/abl_$f.log 2>&1 & done
NOSIB=1 python3 t6_model.py y main > $S/t6_main.log 2>&1
wait; echo ABLDONE >> $S/t6_main.log

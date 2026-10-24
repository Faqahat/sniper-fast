#!/bin/bash
# one dry-run cycle: copy new data from the server (read-only), rebuild trade rows into a dry-run-only dir, refresh
# attempts, evaluate the frozen strategies. Uses phaseA_dry (never touches phaseA_fwd, which other analyses read).
D=/home/moiz/sniper-data/collect; H=/home/moiz/sniper/ops
export RP_PHASEA_R2=phaseA_dry ATTEMPTS_OUT=$H/overnight/dryrun/attempts_dry.json
/home/moiz/sniper-data/work/sync.sh > /home/moiz/sniper-data/work/sync.log 2>&1 || exit 1
rm -rf $D/phaseA_dry.new && nice python3 -I $H/select/a_extract.py $D/run_20261022_1543 $D/phaseA_dry.new 12 > $H/overnight/dryrun/a.log 2>&1 && rm -rf $D/phaseA_dry && mv $D/phaseA_dry.new $D/phaseA_dry
cd $H/overnight/core && python3 -I attempts.py > /dev/null && ATT_ANY_OUT=$H/overnight/dryrun/attempts_ahw_dry.json python3 -I attempts_any.py ahw AHwJSnFNUiAU9FfT5ewW2osqMo938WtL7KhfsJyfpaN2 > /dev/null && cd $H/overnight/dryrun && python3 -I dryrun_eval.py > /dev/null && python3 -I build_list.py > /dev/null && python3 -I build_list_gated.py > /dev/null && echo "cycle ok $(date -u +%H:%M)"

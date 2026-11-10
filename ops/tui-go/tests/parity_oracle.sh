#!/bin/bash
# Parity with the dip42 oracle (dipmon 3.3, the binary that survived the 11-09 drive loss): --snapshot text, --snapshot --json
# --extra and the TUI screens of every local run, new binary vs oracle. DIPMON_V3=1 on the new binary leaves out what v4 added
# (the dip43 sections, the registry's LOG rows), so every run must match the oracle exactly; without it only the dip43 runs
# (r76+) may differ, and only by added lines / rows.
#   sh tests/parity_oracle.sh [NEWBIN]     ORACLE=path  RUNS="dir ..."  OUT=dir  P=4 (processes)  SCREENS=0 (skip the screens)
NEW=${1:-/home/it/sniper-data/tui/v4/dipmon-go}
ORA=${ORACLE:-/home/it/sniper-data/tui/oracle/dipmon-go.dip42}
OUT=${OUT:-$(mktemp -d)}
P=${P:-4}
[ -x "$ORA" ] || { echo "no oracle binary $ORA"; exit 1; }
files() {
  for d in ${RUNS:-/home/it/sniper-data/runs/ams/runs /home/it/sniper-data/runs}; do
    find "$d" -maxdepth 2 -name 'dip_ams_r*.jsonl' ! -name '*obs*'
  done | sort -u
}
one() {
  f=$1; r=$(basename "$f" .jsonl); r=${r#dip_ams_}
  a="--file $f --usd 150 --gcr-seed none"
  $ORA $a --snapshot > "$OUT/o_$r.txt" 2>&1; DIPMON_V3=1 $NEW $a --snapshot > "$OUT/n_$r.txt" 2>&1
  $ORA $a --snapshot --json --extra > "$OUT/o_$r.json" 2>&1; DIPMON_V3=1 $NEW $a --snapshot --json --extra > "$OUT/n_$r.json" 2>&1
  if [ "${SCREENS:-1}" = 1 ]; then
    for t in 1 2 3 4 6 7 8; do  # 5 Health shows this machine's CPU / memory
      $ORA $a --no-anim --screen 200x60 --tab $t | tail -n +2 > "$OUT/o_${r}_s$t.txt" 2>&1
      DIPMON_V3=1 $NEW $a --no-anim --screen 200x60 --tab $t | tail -n +2 > "$OUT/n_${r}_s$t.txt" 2>&1
    done
  fi
}
export -f one; export ORA NEW OUT
files | xargs -P "$P" -I{} bash -c 'one {}'
fail=0
cd "$OUT"
for o in o_*; do
  n=n_${o#o_}
  if ! cmp -s "$o" "$n"; then
    # the screens' header line carries the wall clock; the version differs in --help only
    if [ "${o%.txt}" != "$o" ] && [ "${o#*_s}" != "$o" ] && diff <(tail -n +2 "$o") <(tail -n +2 "$n") >/dev/null; then continue; fi
    echo "DIFF $o"; fail=1
  fi
done
echo "outputs in $OUT"
[ $fail = 0 ] && echo "PARITY OK (every run, text + JSON + screens)" || echo "PARITY: differences above"
exit $fail

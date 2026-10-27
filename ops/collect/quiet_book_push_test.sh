#!/usr/bin/env bash
# Local test of quiet_book_push.sh (no ssh, no server: each "node" is a directory here, QB_LOCAL=1, no sudo).
#   bash ops/collect/quiet_book_push_test.sh [WORKDIR]      (default: a temp dir, removed at the end)
# Checks: a first push installs the book and both lists on every node, an unwritable node fails alone (exit 2); a second push of the
# same bytes sends nothing; ATOMICITY: 20 pushes of a growing book while a reader reads the node's book in a tight loop: every read
# is one complete pushed version (never a mix, never a partial file), no .new file left; the delta (bytes on the wire per push) vs
# the book's size; lists: a changed valid list pushed alone, an invalid one refused (exit 1, the node keeps its list); a stale book
# (exit 1, pushed), a missing book (exit 1, nothing pushed); a push while another holds the lock is skipped.
set -u
PUSH=$(dirname "$(readlink -f "$0")")/quiet_book_push.sh
T=${1:-$(mktemp -d)}; KEEP=${1:+1}
mkdir -p "$T"/lists "$T"/bad && : > "$T"/bad/tmp   # the bad node: its stage dir cannot be made (tmp is a file)
cp /home/moiz/sniper/ops/overnight/sel/cohort_train.json /home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json "$T"/lists/
printf 'n1 h 1 u\nn2 h 1 u\nbad h 1 u\n' > "$T"/nodes3.txt; printf '# two good nodes\nn1 h 1 u\nn2 h 1 u\n' > "$T"/nodes.txt
export QB_LOCAL=1 QB_SUDO= QB_BOOK="$T"/book.jsonl QB_LOG="$T"/push.log QB_WORK="$T"/work QB_COHORT="$T"/lists/cohort_train.json QB_FBOTS="$T"/lists/fbots_frozen.json \
       QB_DEST="$T/{node}/root/dip" QB_STAGE="$T/{node}/tmp/quiet_book" QB_NODES="$T"/nodes.txt
fails=0
check() { if eval "$2"; then echo "  ok   $1"; else echo "  FAIL $1"; fails=$((fails + 1)); fi; }
# a book version k: 24 h of dumps (one every 2 s, ~43k lines, ~5 MB) on a fixed grid, its window moved k x 10 min (as the builder's
# passes: 300 old dumps trimmed, 300 new ones appended); its stop marker AGE min before now (the freshness the push checks)
BASE=$(( $(date +%s) / 600 * 600 - 30 * 600 ))
mkbook() {  # k age_min out
  python3 -I - "$1" "$2" "$3" "$BASE" <<'PY'
import sys, time, os
k, age, out, base = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
end = base + k * 600; t0 = end - 86400
w = ["%044d" % i for i in range(3000)]
L = ['{"k":"start","v":1,"t":%d,"s":%d}' % (t0 * 10**9, (t0 - base) * 5 // 2 + 10**6)]
for t in range(t0 - t0 % 2, end, 2):
    s = (t - base) * 5 // 2 + 10**6
    L.append('{"k":"d","s":%d,"i":%d,"j":0,"t":%d,"w":"%s","n":%d}' % (s, t % 1300, t * 10**9, w[(t * 7) % 3000].replace("0", "1")[:44], (t * 13) % 6))
L.append('{"k":"stop","t":%d,"s":%d}' % ((int(time.time()) - age * 60) * 10**9, (end - base) * 5 // 2 + 10**6))
open(out + ".tmp", "w").write("\n".join(L) + "\n"); os.rename(out + ".tmp", out)
PY
}
shaof() { sha256sum "$1" | cut -c1-64; }
echo "== quiet_book_push local test in $T"
mkbook 0 5 "$T"/book.jsonl
# 1) first push, three nodes, one cannot be written
out=$(QB_NODES="$T"/nodes3.txt bash "$PUSH"); rc=$?; echo "  $out"
check "first push: exit 2 (the bad node)" '[ $rc = 2 ]'
check "the bad node reported, the good ones installed" 'echo "$out" | grep -q "bad book rsync FAILED" && [ "$(shaof "$T"/n1/root/dip/quiet_book.jsonl)" = "$(shaof "$T"/book.jsonl)" ] && [ "$(shaof "$T"/n2/root/dip/quiet_book.jsonl)" = "$(shaof "$T"/book.jsonl)" ]'
check "both lists installed, mode 644" 'cmp -s "$T"/n1/root/dip/cohort_train.json "$T"/lists/cohort_train.json && cmp -s "$T"/n2/root/dip/fbots_frozen.json "$T"/lists/fbots_frozen.json && [ "$(stat -c %a "$T"/n1/root/dip/quiet_book.jsonl)" = 644 ]'
# 2) the same bytes again: nothing sent
out=$(bash "$PUSH"); rc=$?; echo "  $out"
check "same book: exit 0, nothing sent" '[ $rc = 0 ] && echo "$out" | grep -q "n1 book same, lists same (0.0 KB on the wire)"'
# 3) atomicity: 20 pushes of a growing book, a reader in a tight loop on n1's book
: > "$T"/allowed; shaof "$T"/book.jsonl >> "$T"/allowed
( n=0; bad=0; while [ ! -e "$T"/stop ]; do s=$(sha256sum < "$T"/n1/root/dip/quiet_book.jsonl | cut -c1-64); n=$((n + 1)); grep -q "^$s\$" "$T"/allowed || { bad=$((bad + 1)); echo "$s" >> "$T"/badreads; }; echo "$s" >> "$T"/seen; done; echo "$n $bad" > "$T"/reader ) &
rd=$!
wires=()
for k in $(seq 1 20); do
  mkbook "$k" 5 "$T"/next.jsonl; shaof "$T"/next.jsonl >> "$T"/allowed; mv -f "$T"/next.jsonl "$T"/book.jsonl
  out=$(bash "$PUSH") || echo "  push $k: $out"
  wires+=("$(echo "$out" | sed -n 's/.*n1 book pushed[^(]*(\([0-9.]*\) KB on the wire).*/\1/p')")
done
touch "$T"/stop; wait $rd
read -r nreads nbad < "$T"/reader; ndist=$(sort -u "$T"/seen | wc -l)
echo "  reader: $nreads reads, $ndist distinct versions seen, $nbad not a pushed version; book $(stat -c %s "$T"/book.jsonl) bytes, KB on the wire per push: ${wires[*]}"
check "every read = one complete pushed version" '[ "$nbad" = 0 ] && [ "$nreads" -gt 100 ] && [ "$ndist" -ge 3 ]'
check "no .new left, n2 = the last version" '! ls "$T"/n1/root/dip/*.new "$T"/n2/root/dip/*.new 2>/dev/null | grep -q . && [ "$(shaof "$T"/n2/root/dip/quiet_book.jsonl)" = "$(shaof "$T"/book.jsonl)" ]'
npushed=$(printf '%s\n' "${wires[@]}" | grep -c '[0-9]'); med=$(printf '%s\n' "${wires[@]}" | grep '[0-9]' | sort -n | awk '{a[NR] = $1} END {print a[int((NR + 1) / 2)]}')
check "all 20 versions pushed; the delta per push (median $med KB) < 10% of the book" '[ "$npushed" = 20 ] && awk -v w="$med" -v b="$(stat -c %s "$T"/book.jsonl)" "BEGIN {exit !(w * 1000 < b / 10)}"'
# 4) lists: a changed valid list pushed alone; an invalid one refused
python3 -I -c "import json,sys; v=json.load(open(sys.argv[1])); json.dump(v[:-1], open(sys.argv[1], 'w'))" "$T"/lists/cohort_train.json
out=$(bash "$PUSH"); rc=$?; echo "  $out"
check "changed cohort: pushed alone, exit 0" '[ $rc = 0 ] && echo "$out" | grep -q "n1 book same, cohort_train.json pushed" && cmp -s "$T"/n1/root/dip/cohort_train.json "$T"/lists/cohort_train.json'
cp "$T"/n1/root/dip/fbots_frozen.json "$T"/fb_before; echo '["notawallet"]' > "$T"/lists/fbots_frozen.json
out=$(bash "$PUSH"); rc=$?; echo "  $out"
check "invalid fbots: refused, exit 1, the node keeps its list" '[ $rc = 1 ] && echo "$out" | grep -q "fbots_frozen.json INVALID on the host: not pushed" && cmp -s "$T"/n1/root/dip/fbots_frozen.json "$T"/fb_before'
cp "$T"/fb_before "$T"/lists/fbots_frozen.json
# 5) stale, missing
mkbook 21 45 "$T"/book.jsonl
out=$(bash "$PUSH"); rc=$?; echo "  $out"
check "stale book: exit 1, pushed anyway" '[ $rc = 1 ] && echo "$out" | grep -q "STALE" && [ "$(shaof "$T"/n1/root/dip/quiet_book.jsonl)" = "$(shaof "$T"/book.jsonl)" ]'
mv "$T"/book.jsonl "$T"/book.away
out=$(bash "$PUSH"); rc=$?; echo "  $out"
check "missing book: exit 1, nothing pushed" '[ $rc = 1 ] && echo "$out" | grep -q "NO BOOK" && [ "$(shaof "$T"/n1/root/dip/quiet_book.jsonl)" = "$(shaof "$T"/book.away)" ]'
mv "$T"/book.away "$T"/book.jsonl
# 6) the lock
( exec 8> "$T"/work/push.lock; flock 8; sleep 3 ) & lk=$!; sleep 0.5
out=$(bash "$PUSH"); rc=$?; wait $lk
check "a push while another runs: skipped" '[ $rc = 0 ] && echo "$out" | grep -q "another push is running"'
echo "== $fails failure(s); log lines: $(wc -l < "$T"/push.log)"
[ -n "$KEEP" ] || rm -rf "$T"
[ $fails = 0 ]

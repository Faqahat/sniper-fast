#!/bin/sh
# dipmon tests, one command:  sh ops/tui/tests/run_tests.sh
#   QUICK=1          the follow test at 200x (default 50x: ~9 min for the 7 h r26 run)
#   FOLLOW_SPEED=N   any speed;  PERF=0  skips the CPU / RSS measurement (~5 min)
cd "$(dirname "$0")" || exit 1
export PYTHONDONTWRITEBYTECODE=1
fail=0
for t in test_units.py test_totals.py test_curses.py test_follow.py; do
  echo "=== $t"
  python3 "$t" || fail=1
done
if [ "${PERF:-1}" != 0 ]; then
  echo "=== test_perf.py"
  python3 test_perf.py || fail=1
fi
[ "$fail" = 0 ] && echo "ALL PASS" || echo "SOME TESTS FAILED"
exit "$fail"

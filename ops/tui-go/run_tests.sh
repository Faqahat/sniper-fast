#!/bin/sh
# dipmon v3 (Go) tests, one command:  sh ops/tui-go/run_tests.sh
#   QUICK=1          the follow test at 200x (default 50x: ~12 min for r26 + r27)
#   FOLLOW=0         skip the follow test;  PERF=0  skip the CPU / RSS measurement (~5 min);  PERF_PY=1  also measure Python v1
#   DIPMON_DATA=dir  the local run copies (default /home/moiz/sniper-data/runs)
cd "$(dirname "$0")" || exit 1
GO=${GO:-/home/moiz/sdk/go/bin/go}
export GOFLAGS=-mod=vendor GOTOOLCHAIN=local GOPROXY=off GOTELEMETRY=off
export GOCACHE=${GOCACHE:-/home/moiz/sniper-data/tui/.gocache}
export DIPMON_BIN=${DIPMON_BIN:-/home/moiz/sniper-data/tui/dipmon-go}
export PYTHONDONTWRITEBYTECODE=1
fail=0
step() { echo; echo "=== $*"; }
step "build (static linux/amd64, reproducible)"
OUT=$DIPMON_BIN sh build.sh || exit 1
step "go vet"
$GO vet ./... || fail=1
step "go test: units, tail, garbage lines, card identity on every run, today, golden screens (5 sizes x 11 pages), resize + keys + mouse, live events / animations / bell"
$GO test -count=1 ./... || fail=1
step "go test -race: the tail and reader, the price goroutine, the UI"
CGO_ENABLED=1 $GO test -count=1 -race ./internal/... || fail=1
step "parity with the Python dipmon v1 (the oracle, pinned in tests/oracle): every local run + running copies"
python3 tests/parity.py --text || fail=1
if [ "${FOLLOW:-1}" != 0 ]; then
  step "follow: r26 and r27 replayed live with a fake engine (numbers, no regressions, the bell)"
  python3 tests/follow.py || fail=1
fi
if [ "${PERF:-1}" != 0 ]; then
  step "CPU / RSS"
  if [ "${PERF_PY:-0}" = 1 ]; then python3 tests/perf.py --python || fail=1; else python3 tests/perf.py || fail=1; fi
fi
echo
[ "$fail" = 0 ] && echo "ALL PASS" || echo "SOME TESTS FAILED"
exit "$fail"

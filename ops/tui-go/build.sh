#!/bin/sh
# Build dipmon v3 (REWIND): a static linux/amd64 binary, reproducible (pinned toolchain + vendored modules, -trimpath,
# no build id), into /home/moiz/sniper-data/tui/dipmon-go and its .sha256.
#   sh ops/tui-go/build.sh            OUT=path  GO=path/to/go  GOCACHE=dir   to override
set -e
cd "$(dirname "$0")"
GO=${GO:-/home/moiz/sdk/go/bin/go}
OUT=${OUT:-/home/moiz/sniper-data/tui/dipmon-go}
export CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOFLAGS=-mod=vendor GOTOOLCHAIN=local GOPROXY=off GOTELEMETRY=off
export GOCACHE=${GOCACHE:-/home/moiz/sniper-data/tui/.gocache}
mkdir -p "$(dirname "$OUT")"
"$GO" version
"$GO" build -trimpath -ldflags "-s -w -buildid=" -o "$OUT" .
(cd "$(dirname "$OUT")" && sha256sum "$(basename "$OUT")" > "$(basename "$OUT").sha256")
ls -l "$OUT"
cat "$OUT.sha256"

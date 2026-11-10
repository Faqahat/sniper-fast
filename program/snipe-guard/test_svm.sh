#!/usr/bin/env bash
# test_svm.sh: host tests + LiteSVM tests of the BUILT release/snipe_guard.so (run build_sbf.sh first). Cargo home and targets live in
# the folder-local toolchain ($SG_TOOLCHAIN). Re-runnable.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
T="${SG_TOOLCHAIN:-/home/it/sniper-data/plan1110/onchain/toolchain}"
export CARGO_HOME="$T/home/.cargo"
export SNIPE_GUARD_SO="${SNIPE_GUARD_SO:-$HERE/release/snipe_guard.so}"
echo "testing $SNIPE_GUARD_SO sha256 $(sha256sum "$SNIPE_GUARD_SO" | cut -c1-64)"
( cd "$HERE" && CARGO_TARGET_DIR="$T/target-sg-host" nice cargo test --release -j 4 2>&1 | grep -E "^test |test result" )
cd "$HERE/../snipe-guard-svm"
CARGO_TARGET_DIR="$T/target-sg-svm" nice cargo test --release -j 4 -- --nocapture --test-threads=1 2>&1 | grep -vE "^\s+(Compiling|Downloaded|Downloading)" | tail -70

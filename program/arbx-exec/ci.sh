#!/usr/bin/env bash
# arbx-exec: build the programs and run every test, in the order the SVM tests need (REVIEW.md #3).
#   ./ci.sh
# Needs cargo-build-sbf (4.4.0; platform-tools v1.57). Offline: the venue snapshots and ELFs are in tests/fixtures.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/share/solana/install/active_release/bin:$PATH"

echo "== build: arbx-exec (SBF)"
cargo-build-sbf --features onchain
echo "== build: tests/mock-amm (SBF, test-only venue)"
(cd tests/mock-amm && cargo-build-sbf)

echo "== the deployed nexus-arb-v2 reference ELF"
ref=$(md5sum ../nexus-arb-v2/target/deploy/nexus_arb_v2.so | cut -d' ' -f1)
[ "$ref" = "809315befcb9554211f8019bf9df290b" ] || { echo "nexus_arb_v2.so md5 $ref, expected 809315be (rebuild program/nexus-arb-v2)"; exit 1; }

echo "== tests: host, LiteSVM (mainnet features), real venues"
cargo test --release -- --test-threads="$(nproc)"

md5sum target/deploy/arbx_exec.so

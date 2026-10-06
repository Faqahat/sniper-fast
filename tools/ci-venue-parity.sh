#!/bin/bash
# Venue-maths parity (PLAN-ADDENDUM WP-16): the checks that keep the engine's quotes equal to the real venue programs.
# Offline: the venue ELFs and the pool snapshots are in program/venue-harness/fixtures, their copies in testdata/.
#   tools/ci-venue-parity.sh
#   TARGET_BASE=/fast/disk tools/ci-venue-parity.sh     (each crate's target dir under it instead of <crate>/target)
#   SIZING_TARGET=... HARNESS_TARGET=... ENGINE_TARGET=... tools/ci-venue-parity.sh
#                                                       (each crate's own target dir; each wins over TARGET_BASE)
# The harness's sizing-bridge builds go to VENUE_HARNESS_BRIDGE_TARGET, else to the harness's target dir: with a target
# dir given, nothing is built inside the repository (WP-16 review F9).
# Steps:
#   1. arbx-sizing's own suite (all features), its default-feature suite and the no-default build;
#   2. venue-harness with VENUE_HARNESS_REQUIRE_SIZING=1: exactness (every fixture snapshot and byte mutation, and every
#      refusal checked against the venue: a false refusal fails like a mismatch), the adversarial boundary sizes and
#      states, route and basket plans, pins and swaps, all against the dumped mainnet programs in LiteSVM;
#   3. the engine's copy of the oracle is current: testdata/venue-parity/pools equals the harness fixtures, and
#      testdata/venue-parity/real-swaps.json equals what `capture_post` produces from them now; PLAN-ADDENDUM WP-21: the
#      same for the CLMM venues (pools-clmm, real-swaps-clmm.json from `capture_post --clmm`);
#   4. the engine's parity tests on that copy (src/quote/tests.rs: its quotes against the real swaps, the differential
#      against the legacy maths, the accuracy monitor's post-states, every refusal state, the accounts the stream
#      follows, sizing on a recorded route; WP-21 src/quote/clmm_tests.rs: Raydium CLMM and Orca Whirlpool quotes and
#      post-states against the real swaps, the reasons, no panics), the builder's bundle vectors the harness ran in step 2
#      are what it builds now (testdata/builder/bundle-vectors.json, bundle-vectors-clmm.json), and a run with CLMM
#      pools replays identically (scenario S17).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
target() { if [ -n "${TARGET_BASE:-}" ]; then echo "$TARGET_BASE/$1"; else echo "$2/target"; fi; }
sizing="$root/program/arbx-sizing"
harness="$root/program/venue-harness"
sizing_t="${SIZING_TARGET:-$(target arbx-sizing "$sizing")}"
harness_t="${HARNESS_TARGET:-$(target venue-harness "$harness")}"
engine_t="${ENGINE_TARGET:-$(target arbx "$root")}"
bridge_t="${VENUE_HARNESS_BRIDGE_TARGET:-$harness_t}"
echo "targets: arbx-sizing $sizing_t; venue-harness $harness_t (bridges $bridge_t); engine $engine_t"

echo "== 1. arbx-sizing"
(cd "$sizing" && CARGO_TARGET_DIR="$sizing_t" cargo test --release --all-features)
(cd "$sizing" && CARGO_TARGET_DIR="$sizing_t" cargo test --release)
(cd "$sizing" && CARGO_TARGET_DIR="$sizing_t" cargo build --release --no-default-features)

echo "== 2. venue-harness (real programs)"
(cd "$harness" && VENUE_HARNESS_REQUIRE_SIZING=1 VENUE_HARNESS_BRIDGE_TARGET="$bridge_t" CARGO_TARGET_DIR="$harness_t" cargo test --release)
# swaps.rs rewrites its tracked results/swap-runs.json: the runs are deterministic, so it must not change
git -C "$root" diff --quiet -- program/venue-harness/results/swap-runs.json || { echo "results/swap-runs.json changed: the real swaps moved"; exit 1; }

echo "== 3. testdata/venue-parity is the harness's oracle"
diff -r "$harness/fixtures/pools" "$root/testdata/venue-parity/pools" || { echo "testdata/venue-parity/pools differs from the fixtures: copy them again"; exit 1; }
diff -r "$harness/fixtures/pools-clmm" "$root/testdata/venue-parity/pools-clmm" || { echo "testdata/venue-parity/pools-clmm differs from the fixtures: copy them again"; exit 1; }
fresh="$(mktemp)"
trap 'rm -f "$fresh"' EXIT
(cd "$harness" && CARGO_TARGET_DIR="$harness_t" cargo run --release --quiet --bin capture_post > "$fresh")
cmp -s "$fresh" "$root/testdata/venue-parity/real-swaps.json" || { echo "testdata/venue-parity/real-swaps.json is stale: regenerate it with capture_post"; exit 1; }
(cd "$harness" && CARGO_TARGET_DIR="$harness_t" cargo run --release --quiet --bin capture_post -- --clmm > "$fresh")
cmp -s "$fresh" "$root/testdata/venue-parity/real-swaps-clmm.json" || { echo "testdata/venue-parity/real-swaps-clmm.json is stale: regenerate it with capture_post --clmm"; exit 1; }

echo "== 4. the engine's parity tests"
(cd "$root" && CARGO_TARGET_DIR="$engine_t" cargo test --release --lib -- quote:: bundle_vectors scenarios::s17)
echo "venue parity: ok"

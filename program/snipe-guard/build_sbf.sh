#!/usr/bin/env bash
# build_sbf.sh: the reproducible snipe-guard build (dip43). Folder-local toolchain (nothing system-wide; HOME / CARGO_HOME are redirected
# into $SG_TOOLCHAIN). Pinned: agave release v4.4.0 tarball (sha256 below; cargo-build-sbf 4.5.0), platform-tools v1.57 (Rust 1.95.0),
# SBPF v3, the committed Cargo.lock (--locked), paths remapped (no build path can leak into the ELF).
#
#   bash program/snipe-guard/build_sbf.sh            -> program/snipe-guard/release/snipe_guard.so + .sha256, then the strings scan
#
# The release/ copy is what the owner deploys (ops/guard/DEPLOY.md). Re-running on the same toolchain gives the same sha256.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
T="${SG_TOOLCHAIN:-/home/it/sniper-data/plan1110/onchain/toolchain}"
AGAVE_TGZ_SHA256=3363f4728fe786ac7036e342a20df928aa2e3e43f807fbdce67814840538c574
mkdir -p "$T"
cd "$T"
if [ ! -x solana-release/bin/cargo-build-sbf ]; then
  curl -sSL -m 600 -o solana-release.tar.bz2 https://github.com/anza-xyz/agave/releases/download/v4.4.0/solana-release-x86_64-unknown-linux-gnu.tar.bz2
  echo "$AGAVE_TGZ_SHA256  solana-release.tar.bz2" | sha256sum -c -
  tar xjf solana-release.tar.bz2
fi
mkdir -p home
export HOME="$T/home"
export CARGO_HOME="$T/home/.cargo"
export PATH="$T/solana-release/bin:$T/home/.cache/solana/v1.57/platform-tools/rust/bin:/home/it/.rustup/toolchains/stable-x86_64-unknown-linux-gnu/bin:/usr/bin:/bin"
OUT="$T/target-sg-dip43"
export CARGO_TARGET_DIR="$OUT"
# (cargo-build-sbf drops RUSTFLAGS: it sets its own target flags; the ELF carries no path anyway: see the strings scan)
cargo-build-sbf --version
cd "$HERE"
nice cargo-build-sbf --no-rustup-override --tools-version v1.57 --arch v3 --sbf-out-dir "$OUT/deploy" -j 4 -- --locked 2>&1 | tail -20
mkdir -p "$HERE/release"
cp "$OUT/deploy/snipe_guard.so" "$HERE/release/snipe_guard.so"
( cd "$HERE/release" && sha256sum snipe_guard.so | tee snipe_guard.so.sha256 )
echo "size: $(stat -c %s "$HERE/release/snipe_guard.so") bytes"
# the strings scan (the SVM test repeats it with the full word list): printable runs of >= 4 bytes
echo "strings (>= 4 printable bytes):"
strings -n 4 "$HERE/release/snipe_guard.so" | sed 's/^/  | /'
if strings -n 3 "$HERE/release/snipe_guard.so" | grep -iE 'guard|holder|floor|slot|deadline|curve|abort|allow|admin|snipe|pump|error|panic|src/|\.rs' ; then
  echo "STRINGS-SCAN: FAIL (a revealing word is in the ELF)"; exit 1
fi
echo "STRINGS-SCAN: PASS"
echo BUILD-OK

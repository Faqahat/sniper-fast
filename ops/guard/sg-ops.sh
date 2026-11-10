#!/usr/bin/env bash
# sg-ops.sh: the snipe-guard ops tool (src/bin/sg_ops.rs): deploy / verify / smoke / allowlist / decode. See DEPLOY.md.
# Builds it on first use. Runs from the repo root so the default --so path resolves.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
[ -x target/release/sg_ops ] || nice cargo build --release --bin sg_ops -j 4 >&2
exec target/release/sg_ops "$@"

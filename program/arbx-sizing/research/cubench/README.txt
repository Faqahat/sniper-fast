CU micro-benchmark behind DESIGN.md §4.7 (per-operation cost of the integer primitives on SBF).
Build (offline, versions pinned by arbx-exec's lock files):
  cp ../../../arbx-exec/tests/mock-amm/Cargo.lock program/ && cp ../../../arbx-exec/Cargo.lock runner/
  (cd program && PATH=$HOME/.local/share/solana/install/active_release/bin:$PATH cargo-build-sbf --offline)
  (cd runner && cargo run --release --offline -- ../program/target/deploy/cubench.so)
The runner activates the sol_remaining_compute_units feature (5TuppMuto…) in LiteSVM only to MEASURE; that syscall is
not active on mainnet (see arbx-exec review/tests/adversarial.rs), so production code must not call it.
Result 2026-10-04 (platform-tools v1.57, sbpfv3, LiteSVM 0.17, overflow-checks on), CU per op net of the loop:
  u64*u64->u128 52 | u128*u128 61 | u128/u128 (wide divisor) 296 | u128/u64-sized divisor 598 | U256::mul128 263
  U256 div_rem 256/128 3,330 | isqrt u128 Newton (unseeded) 3,567 | DLMM bin step (drain test + fill, exact) 1,057
  CPMM leg exact quote 526 | CPMM-CPMM closed form (u128 + isqrt) 2,633 | 16-byte load 10

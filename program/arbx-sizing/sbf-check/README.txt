SBF build check and CU probe for arbx-sizing (DESIGN.md §4.7, §4.8, §6.4).

sbf-check/   a tiny program shaped like the arbx-exec integration (§4.5): it parses a sizing block, builds the
             borrowed account views, runs plan() and logs the AXZ1 record. Feature `bench` (default): modes 1-9
             repeat one phase for per-op CU (6-9 on a DLMM leg 0: the bare walk, the exact drains, the locator's
             pieces, cap_in + an exact quote). Feature `baseline`: same entrypoint, account borrows, clock read and
             log, without arbx-sizing (the CU and size baseline). Per-venue features select arbx-sizing's features.
cu-runner/   LiteSVM 0.17 runner: real mainnet HOTBOT accounts (tests/data) and synthetic pools (tests/common). Each
             DLMM leg gets the engine's walk budget (max_bins: the bins its exact swap reads at the cap; TIGHT=1: at
             max(e, 1.25·x̂) + 2, x̂ from a host plan; DESIGN §4.3). Exits nonzero (the CI regression of DESIGN §6.4)
             if a route measures above arbx_sizing::cu_bound of its own block, above its recorded budget + 10%, or if
             the few-bin 3-pair DLMM basket exceeds 60k.

Build (any target dir; keep it out of the shared disk quota):
  export PATH=$HOME/.local/share/solana/install/active_release/bin:$PATH CARGO_TARGET_DIR=/tmp/sbf-target
  cargo-build-sbf --sbf-out-dir /tmp/cu && cp /tmp/cu/arbx_sizing_sbf_check.so /tmp/cu/full.so
  cargo-build-sbf --sbf-out-dir /tmp/cu -- --no-default-features --features baseline && cp /tmp/cu/arbx_sizing_sbf_check.so /tmp/cu/baseline.so
  (cd cu-runner && cargo run --release -- /tmp/cu && TIGHT=1 cargo run --release -- /tmp/cu)
  code size without the bench modes: cargo-build-sbf -- --no-default-features --features all-venues
  with LTO: CARGO_PROFILE_RELEASE_LTO=fat CARGO_PROFILE_RELEASE_OPT_LEVEL=z cargo-build-sbf -- --no-default-features --features all-venues

Results 2026-10-04, after the review fixes (platform-tools v1.57, sbpfv3, overflow-checks on, default release profile):
  build: --arch v0 / v2 / v3, and LTO fat + opt-level z, all build with no stack-frame warning; every route below
         executes on v0, v2 and v3 (v2 is ~14% cheaper on the long walks; v0 equals v3).
  size: no bench modes 206,392 B against a 14,584 B baseline (sizing ≈ 192 KB); LTO fat + z: 154,544 B (baseline
        10,496 B); PumpSwap + DLMM only: 137,528 B (LTO + z: 107,096 B); DLMM only: 119,520 B. (Before the fixes:
        184,344 B with the bench modes, LTO + z 140,944 B.)
  sizing CU (full − baseline, same instruction)            cu_bound: budgets at the cap / tight budgets
    CPMM → AMM v4 (closed form)                        7,191    26.5k / 26.5k
    PumpSwap buy → CPMM (closed form)                 11,106    36.7k / 36.7k
    DLMM buy → CPMM, 1 / 2 / 3 bins     13,496 / 15,700 / 16,373    174k - 1.05M / 86k - 98k
    DLMM → DLMM (unprofitable, 2 bins)                18,243    975k / 145k
    HOTBOT GLL3 → 6D4E, real state (NoProfit)         18,072    229k / 95k
    HOTBOT GLL3 → 6D4E, GLL3 quote −12%               26,152    244k / 111k   (sized 2.57 SOL, 4 bins); SHADOW same
    DAMM v2 (b→a) → CPMM                    10,788 - 17,618    104k
    BASKET 3 pairs, 4 DLMM legs, few bins             41,013    1.95M / 184k  (DESIGN target ≤ 60k; was 36,638)
    BASKET PumpSwap + 3 DLMM legs, 34 bins           112,768    1.29M / 337k  (was 176,015)
    DLMM(bin step 1, 3% gap) → CPMM, 90 bins  169,927 / 176,288 (fee rising / falling)   1.05M / 513k
    DLMM(bin step 5, 3% gap) → CPMM, 38 bins   80,304 / 86,665    1.05M / 266k
    DLMM(bin step 25, 5% gap) → CPMM, 16 bins  40,837 / 44,749    1.05M / 160k
    DLMM(bin step 100) reversion arb (REVIEW F6)      19,592    1.05M / 110k  (walks 4 bins; was 64)
    BASKET 3 pairs, 4 bin-step-1 legs, 3% gap: max_bins 255: 1,275,222; max_bins 48: 441,349
  per bin with liquidity (modes 6-9): the walk 352, + the exact drain 607, + the locator's piece 500, + the locate
  step ≈400 (≈1.85k per bin the locator reads); an exact quote ≈1.5k + 0.9-1.4k per bin it reads. Before the fixes:
  260k for the bin-step-1 route while stopping at a 64-bin cap (the optimum is 90 bins out), 159-174k for bin step 5,
  457k for the bin-step-1 basket at 64-bin caps (REVIEW.md F4).

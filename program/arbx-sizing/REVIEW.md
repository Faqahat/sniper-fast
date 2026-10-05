# arbx-sizing adversarial review

Date 2026-10-04. Reviewed `program/arbx-sizing` (DESIGN.md, `src/`, `tests/`, `sbf-check/`) and `program/venue-harness`.
Every number below comes from a run made for this review: the crate's own suite, the harness suites against the dumped
mainnet programs in LiteSVM 0.17, SBF builds (platform-tools v1.57, `--arch v0/v2/v3`), and scratch probes. The crate
itself was not modified. Only harness wiring and test files were added (listed under "Harness changes").

## Verdict

The venue maths is in very good shape. On 45,000+ comparisons against the real binaries, the quote equals the venue to
the unit everywhere except in four classes of state (F1, F2, F5, F8). It also matches on the limit-order layers, all
function types, both DLMM fee modes, bitmap jumps, an empty active array, Clock variations, DAMM v2 range exit at ±2
units, the scheduler edges and the fee cap.

When the DLMM walk budget does not bind, the optimizer finds the brute-force optimum within ≤ 2 units. At route level
on the real HOTBOT pair it is exact: realized profit equals modeled profit to the unit.

**Blocking:**
- **F1** (PumpSwap sell capacity) and **F2** (PumpSwap buy debit) fail the §6.6 exactness gate on mainnet state that
  exists today.
- Before any SELF_SIZE/BASKET bit is set:
  - **F3**: the walk budget breaks the "never worse than e" guarantee and caps sizing;
  - **F4**: sizing CU measured at 260k for one pair and 457k for a basket, against the ≤ 60k design target, with no
    runtime bound.

## Exactness results

| Suite | Cases | exact | both refuse | conservative¹ | aborted² | MISMATCH |
|---|---|---|---|---|---|---|
| `tests/exactness.rs` (snapshots + the 9 mutation families already there) | 22 pools, 16 venue/mutation groups | 7,111 | 256 | 33 | 178 | **1** |
| `tests/adversarial.rs` (new: boundary sizes, Clock variations, 40+ mutations) | 256 case/pool combinations | 38,276 | 2,508 | 134 | 174 | **1,161** (4 classes) |
| `tests/route.rs` (new: `plan` on GLL3 ↔ 6D4E, both directions, 6 gaps, legs run on the real programs) | 6 routes | realized == modeled to the unit in all 6 (incl. at `e`); plan ≥ 96-point grid best | | | | 0 |

¹ "Conservative" means the crate says TooLarge while the venue still swaps. Every one is a DLMM swap past the crate's walk
budget (venue CU 380k–1.07M). The harness counts these as passes, but they are not harmless (F3).

² Aborts are TransferFee (Hmx1 CPMM 300 bps, 2cUM DAMM 100 bps) plus Math aborts from extreme mutations.

**Every mismatch class (pool, size, ours, theirs, diff):**

| # | Pool / state | dir | size | ours | venue | diff |
|---|---|---|---|---|---|---|
| F2 | PumpSwap 6ejg snapshot (creator_fee_bps 200) | buy (1→0) | 10,000,051 | out 98,750,706,143, spent 10,000,051 | out 98,750,706,143, **spent 10,000,050** | spent −1 |
| F2 | PumpSwap CyJw, creator_fee_bps 1000 | buy | 831,210,031 | spent 831,210,031 | spent 831,210,030 | spent −1 |
| F1 | PumpSwap CyJw snapshot (and 10 mutations of it) | sell (0→1) | 3,130,091,978,524,446..448 (crate `cap_in` = …448) | out 2,655,587,452,079 | **fails 6063** InsufficientRealQuoteReserves | Ok vs fail (33 rows) |
| F1 | PumpSwap CyJw, virtual quote = 50·Q | sell | 288,838,078,049..051 | out 2,655,587,452,059..077 | fails 6063 | Ok vs fail |
| F5 | DAMM v2 2E8c, rate limiter in force | b→a | 2 / 11,642,421 / 71,189,780,515 | out 715 / 8,250,380,330 / 23,756,496,147,904 | **fails 6049** FailToValidateSingleSwapInstruction | Ok vs fail (84 rows: 2E8c, 2HFs, 3Bu5) |
| F8 | DLMM 3C6q/3qhd/6D4E/7hvn, pair min/max_bin_id = active ∓ 1 | both | e.g. 3qhd 28,915,524 | out 24,615,786 | **fails 6012** PairInsufficientLiquidity | Ok vs fail (1,042 rows) |

**Selected conservative refusals (F3):**

| Pool | dir | size | ours | venue |
|---|---|---|---|---|
| 3qhd | X→Y | 1,482,790,796 | TooLarge | out 1,106,744,137 (CU 383k) |
| 3qhd | Y→X | 1,297,283,751 | TooLarge | out 1,384,294,597 |
| 6D4E | Y→X | 71,856,448,077 | TooLarge | out 9,260,694,010,098 |

To reproduce:

```
cd program/venue-harness
VENUE_HARNESS_REQUIRE_SIZING=1 cargo test --release --test exactness -- --nocapture     # 1 mismatch (F2)
VENUE_HARNESS_REQUIRE_SIZING=1 cargo test --release --test adversarial -- --nocapture   # F1, F2, F5, F8
VENUE_HARNESS_REQUIRE_SIZING=1 cargo test --release --test route -- --nocapture         # passes
```

Rows are written to `results/exactness.json` and `results/adversarial.json` (the latter is about 18 MB and gitignored).

**Verified clean, with no mismatch at any size including the crate's own boundary sizes ±1, ±2:**
- DLMM:
  - limit orders: open and processed layers, ask 0 and 1;
  - `function_type` 0 (with and without a reward mint), 1 and 2, each changing the output, each exact;
  - `collect_fee_mode` 0 and 1;
  - `va = v_ref = max_va` with `idx_ref` ±25 and +500;
  - Δt ∈ {0, filter−1, filter, decay−1, decay, 10·decay};
  - a bitmap gap, and an empty active array, both with the bitmap-order AND the engine's contiguous array list (the
    program follows the bitmap like the crate's walker; DESIGN §7.4 settled).
- PumpSwap:
  - V negative (−Q/2) and 50·Q;
  - `coin_creator = 0`;
  - `creator_fee_bps` 300 and 1000 (above the configurable max; the program does not clamp);
  - base supply ×1/1000 … ×2000, across the fee tiers.
- CPMM:
  - owed fees 25%;
  - trade fee 1% and 1 ppm;
  - creator fee 3% with `creator_fee_on` 0, 1 and 2;
  - fee-ceil residues.
- AMM v4: fee 30/1e4, 1/3 and 0; status 7.
- DAMM v2:
  - narrow range (`cap_in` ±2 exact in both directions);
  - scheduler period edges and market-cap expiry ±1;
  - volatility 1e9 with `fee_version` 0 and 1 (fee cap);
  - dynamic-fee Δt edges;
  - compounding pools.
- No panic on any input: the bridge quoted about 45k sizes up to `u64::MAX` without crashing.

## Findings

### F1 — blocker (PumpSell). PumpSwap sell ignores the real-reserve set-asides in pool bytes 271..287

- **Location:**
  - `src/venue/pumpswap.rs:156`: `q − lp ≤ Q` check;
  - `pumpswap.rs:198` `cap_in`;
  - `pumpswap.rs:10/123`: the pool is accepted at any length ≥ 270;
  - DESIGN §2.1: "Bytes 270..301 … ignored".
- **Proof.** CyJw's pool has `u64@271 = 1,469,628` and `u64@279 = 2,939,251`. GLL3 and 6ejg hold 0 there. Bisection on
  the real binary gives the exact rule:
  - sell succeeds iff `q − ⌈q·lp/1e4⌉ ≤ Q − (u64@271 + u64@279)`;
  - b = 3,128,959,714,883,203 (q = 2,663,573,768,926) succeeds and b + 1 (q + 1) fails with 6063. That is the rule
    exactly, with R = 4,408,879.
  - The program's own message reads: "BOOST: sell output exceeds the real quote vault … payout is capped at real_vault".
  - The crate's `cap_in` is 1,132,263,641,245 base units too high, so `quote` returns Ok for every size in between.
- **Impact.**
  - In the planner, a PumpSell leg 1 maps its cap into `x_max` (`opt::locate`, `a.inv(b.cap)`).
  - When the optimum sits on that cap (`at_cap`), the exact check accepts it and the route reverts in the venue. The
    "step back" only runs on TooLarge, which the crate never returns here.
  - On today's pools V/Q is small (0.7–5%), so the edge needs huge sells. With V ≫ Q (BOOST launches; the V = 50·Q
    mutation) the edge is at 2% of the base reserve.
- **Fix:**
  - read both u64s (name them from the current pump-amm IDL), and use `Q_avail = Q − (a + b)` (checked; underflow means
    Abort) in `sell_quote` and `cap_in`;
  - gate the pool length at exactly 301 so the next tail extension turns sizing off instead of mispricing (see F9);
  - keep the `adversarial.rs` CyJw rows as the regression.

### F2 — blocker (PumpBuy gate). `buy_quote` reports `spent = x`; the program debits `min(x, eff0 + fees(eff0))`

- **Location:** `src/venue/pumpswap.rs:175`. DESIGN §2.1 says `spent = x`, and §7.1 still lists it as open, although
  `venue-harness/tests/pins.rs` settled it.
- **Proof:** the exactness row 6ejg x = 10,000,051, debit 10,000,050, and the adversarial row CyJw (cr 1000 bps)
  x = 831,210,031, debit 831,210,030. pins.rs: 9 of 16,200 buys.
- **Impact.**
  - The economics are conservative: realized ≥ modeled by 1–3 units.
  - But exactness, the basis of the §6.6 gate, fails. In SHADOW, AXZ1 `profit_e` ≠ AXS1 `quote_delta` on such routes
    trips the per-kind kill switch. For a 200 bps creator-fee pool that is about 1 in 1,800 sizes, so a 300-route gate
    run has roughly a 15% chance of a false alarm.
- **Fix:**
  - in `buy_quote`, `spent = min(x, eff0 + fees(eff0))`;
  - `Quotes::round_trip` (`plan.rs:114`) computes profit as `q1.out − x`; make it `q1.out − q0.spent`, so the modeled
    profit equals the guard's quote delta.

### F3 — major. The DLMM walk budget breaks "never worse than e" and caps sizing

- **Location:**
  - `src/venue/dlmm.rs:18-19,215,227` (`MAX_LIQ_BINS 64`, `MAX_WALK_BINS 210` in the walker shared by `quote`);
  - `src/opt.rs:11,183`: `MAX_STEPS 64` counts breakpoints of BOTH legs;
  - `src/plan.rs:244-252`: `e` enters only through `q.round_trip`.
- **Proof:**
  1. **Exact evaluator.** Past 64 liquid bins `quote` returns TooLarge, but the venue swaps (134 conservative rows,
     e.g. 3qhd x = 1,482,790,796). Scratch probe on a bin-step-1 DLMM → CPMM pair with a 3% gap:
     - e = 2.0e9: E(e) = 38.86M, plan 2.54e9 / 44.07M;
     - e = 3.0e9 and 4.0e9: `quote(e)` is `TooLarge` and `modeled_profit_e = None`. The plan still sizes 2.54e9 (the
       budget end), so `e` was never compared. §3.5's claim "if E(e) = ⊥, realized(e) would have been a revert" is
       false here: the venue fills e.
     - With EARLY_ABORT, a route whose candidates all lie past the budget becomes `NoProfit/INFEASIBLE` and reverts
       although `e` lands.
  2. **Locator.** Two runs of 400 random pairs each were checked against brute force.
     - Every pair that fell short of the optimum by more than 0.1% had hit the walk budget (`bins` 65–66).
     - Those pairs lost 1.8–44% of the optimal profit. Example: DLMM(bs 1) ↔ DLMM(bs 1), 3.2% gap, plan 44.7M
       against an optimum of 78.3M.
     - In DLMM ↔ DLMM, `MAX_STEPS` runs out after about 32 bins per leg, even where the exact evaluator could go to 64.
     - All 281 profitable pairs without a budget hit were within ≤ 2 units of the brute-force optimum.
- **Fix:**
  - make the budget a per-leg descriptor field that the engine sets from its off-chain quote at the cap (it already
    computes the bins crossed for the CU limit), so the budget always covers `e`;
  - give "budget exhausted" its own `QuoteErr` (not TooLarge). When `E(e)` hits it, keep `e` as a fallback candidate
    (Outcome::Fallback with a reason) instead of dropping it;
  - count `MAX_STEPS` per leg;
  - add a harness assertion that no conservative refusal occurs at or below the engine's `e`.

### F4 — major. Sizing CU is unbounded in practice and far above the design target

- **Location:**
  - DESIGN §0/§4.7 (≤ 60k for a 3-pair DLMM basket);
  - `opt.rs` walk, `dlmm.rs` exact walk;
  - `plan.rs` golden section (`max_iters` ≤ 24) over legs that may be DLMM.
- **Proof.** SBF, sbf-check full minus baseline, same instruction:

  | Route | Sizing CU |
  |---|---|
  | DLMM(bin step 1, 3% gap) → CPMM | **260,076** / 274,495 (fee rising / falling along the walk) |
  | DLMM(bs 1, 1%) → CPMM | 108,529 |
  | DLMM(bs 5, 3%) → CPMM | 159,010 / 173,503 |
  | DLMM(bs 25, 5%) → CPMM | 48,157 |
  | 3-pair basket, 4 bin-step-1 DLMM legs, 3% gap | **456,626** |
  | the repo's own PumpSwap + 3 DLMM basket (README) | 176,015 |

  - The locator costs about 1.85k CU per bin and the exact DLMM evaluation about 1.6k per bin per candidate.
  - With SEARCH and a DLMM leg, golden makes up to 26 exact round trips at ≤ 64 bins each (~2.7M CU).
  - Add the chosen pair's DLMM CPIs at 64 bins (~400k each) and the basket reaches about 1.3M of the 1.4M limit.
  - `sol_remaining_compute_units` is unavailable, so the engine must budget the worst case statically.
- **Fix:**
  - the per-leg bin budget from F3, sized from the engine's quote (small for the usual 1–5 bins);
  - the per-step guard (F6);
  - reuse the locator's per-bin `(U, V)` to start the exact walk at the candidate's bin instead of re-walking from the
    active bin;
  - forbid SEARCH on a pair with a DLMM leg;
  - add a CI regression on these mixes (DESIGN §6.4 already asks for it).

### F5 — major. DAMM v2 rate limiter: `quote` is Ok, but the venue refuses the engine's leg (6049)

- **Location:**
  - `src/venue/dammv2.rs:558-573`: `fee_fixed = None`, so `quote` prices per amount;
  - `src/leg.rs:219`: only `model()` refuses;
  - DESIGN §2.5 / §3.6 ("Sizing can still use the exact evaluator in a SEARCH run").
- **Proof.** A rate-limiter base fee (mode 2, in force, b→a) on 2E8c, 2HFs and 3Bu5 fails at every size with
  `FailToValidateSingleSwapInstruction`: 84 rows, e.g. 2E8c x = 11,642,421, ours 8,250,380,330, venue fails. The
  program needs the instructions sysvar as the first remaining account (single-swap validation). The engine's 14-account
  leg does not pass it. a→b is unaffected and exact.
- **Impact.**
  - Without SEARCH: Fallback to `e`, which also reverts (not sizing's fault, but wasted).
  - With SEARCH: golden picks a size on a pair that can never execute. In BASKET that pair can win over a working pair,
    so the route reverts instead of executing the working one.
- **Fix:**
  - `parse` returns `Abort::Damm(RateLimiter)` whenever the limiter is in force for the leg's direction, unless the
    leg's account list carries the instructions sysvar (then the engine must append it);
  - correct DESIGN §2.5 / §3.6.

### F6 — minor (CU). The non-concavity guard is evaluated only on steps that push an optimum

- **Location:** `src/opt.rs:214` (`if pushed { … break }`).
- **Proof:**
  - Once the bound exceeds 1 at the first optimum, later steps are "not rising, not pushed" and never re-check it, so
    the walk runs to `MAX_STEPS` or the end of the arrays.
  - Probe: DLMM(bs 100, shallow bins) buy toward `idx_ref` (a reversion arb), CPMM sell. The optimum is at step 3 with
    the same size as the fee-rising case, but the locator walks **64 steps / 65 bins** instead of 3. That is ~110k extra
    CU with no possible gain.
- **Fix:** after the first optimum, compute `bound_after` on every step and break when ≤ 1. The bound is
  non-increasing, so this is exact.

### F7 — minor (design). BASKET drops `e` when pair 0 aborts

- **Location:** `src/plan.rs:244`: `e` is evaluated only if `live[0]`. DESIGN §2.6 says "only when every pair aborts".
- **Impact.**
  - Pair 0 is the engine's own choice. If any of its legs aborts (state-dependent: Layout after a venue upgrade, DAMM
    limiter, CPMM owed > vault, DLMM status), the plan executes the best other pair or returns NoProfit.
  - That other pair can be worse than `e` on pair 0, and EARLY_ABORT then reverts a route `e` would have landed.
  - Under SELF_SIZE the same abort falls back to `e`, so the two modes disagree.
- **Fix:** keep `(pair 0, e)` as an unmodeled fallback candidate. Execute it unless a modeled candidate clears
  `min_profit`, or require pair 0 to be live for BASKET sizing.

### F8 — minor. DLMM ignores the pair's own `min_bin_id` / `max_bin_id`

- **Location:**
  - `src/venue/dlmm.rs:14-15,202` use ±443,636;
  - the program enforces StaticParameters @24/@28 (±3,516 for bin step 100, ±21,855 for bin step 20 in the fixtures).
- **Proof:** with the bounds mutated to active ∓ 1 the venue fails 6012 PairInsufficientLiquidity: 1,042 rows,
  e.g. 3qhd 28,915,524 (ours 24,615,786). On real pairs this binds only at extreme prices.
- **Fix:** read both and use them in `BinWalker::step`.

### F9 — minor. PumpSwap layout gate is `len ≥ 270`, not the mainnet 301

- **Location:** `src/venue/pumpswap.rs:10,123`; DESIGN §2.0 "Version gates".
- **Impact:** the tail bytes the crate ignores have already turned out to be pricing-relevant (F1). A future extension
  would again be mispriced instead of aborted.
- **Fix:** accept exactly 301 (Abort::Layout otherwise) and decode the full tail.

### F10 — minor. `plan` ignores lamport side effects that the guard counts with COUNT_LAMPORTS

- **Location:** `src/plan.rs:264-265`: NoProfit compares `profit − tip(profit)` with `min_profit`.
- **Impact.**
  - With COUNT_LAMPORTS, arbx-exec's `g` includes lamport deltas (PumpSwap ATA or accumulator rent, wSOL closes), and
    the tip is computed on that `g`.
  - EARLY_ABORT can then pass a route the guard reverts (wasted CU), or abort one it would pass when the lamport delta
    is positive.
- **Fix:** add a signed `lamport_offset` to `PlanIn` supplied by the engine, or disallow EARLY_ABORT together with
  COUNT_LAMPORTS.

### F11 — minor. Code size is 2–4× the estimate

- **Measured:**
  - sbf-check full 184,344 B (v3) and 190,480 B (v0);
  - baseline 14.6 KB, so sizing adds about 170 KB, against DESIGN §4.8's 40–80 KB;
  - LTO + opt-level z gives 141 KB.
- **Impact:** arbx_exec.so grows from 52 KB to about 230 KB, so deploy and upgrade-buffer rent rise accordingly (DESIGN
  §4.8). No SBF stack-frame warnings at v0, v2 or v3, and the 64-bin cases execute on the v0 build.
- **Fix:** build arbx-exec's sizing feature with only the kinds in use, add LTO, and budget the rent.

### F12 — minor. Ok quotes where the vault cannot absorb the input (u64 overflow)

- **Proof:** DAMM 3Bu5 b→a at x ≈ 2^64 − 2: ours out 1,982,317,744,170, venue fails with Token-2022 "Operation
  overflowed" (vault + x > u64::MAX).
- **Impact:** only at sizes far above any cap. `adversarial.rs` skips x > 2^62 for this reason.
- **Fix:** where the vault is in the leg, require `vault_in + x ≤ u64::MAX`, or document the cap ≤ 2^62 as a
  precondition of `plan`.

### F13 — minor. Missing tests (partly closed by this review)

- **Gaps in `tests/exactness.rs`** (DESIGN §6.3), now covered by `tests/adversarial.rs`:
  - no boundary sizes, Clock variations, limit-order or function-type mutations;
  - no bitmap gap or empty active array, no DAMM range edge, limiter or fee cap;
  - no PumpSwap tier, V or coin_creator mutations.
- **Conservative verdicts are not limited** (see F3).
- **Still missing:**
  - route-level tests with arbx-exec (`--features sizing` does not exist yet), DESIGN §6.3 assertions 1, 5, 6 and 7;
  - a BASKET route on real binaries (the fixtures hold only one same-mint pair, GLL3 ↔ 6D4E: add HOTBOT C9xc);
  - CU regression in CI;
  - the descriptor fuzz never runs `plan` on parsed blocks.

### F14 — minor. BASKET evaluates one optimum per pair and steps back once by 1 ppm

- **Location:** `src/plan.rs:223,227-233`.
- **Impact:** if that one optimum fails exact evaluation twice (a DLMM cap mismatch larger than 1 ppm, which is
  possible for x < 2^20 where the step is 1 unit while rounding is up to 2 units per bin), the pair contributes no
  candidate.
- **Fix:** step back to the exact capacity (bisection over `quote`, about 20 evaluations only in that branch), or try
  the next optimum.

### F15 — nit. `LegDesc::kd()` overflows for `n_bin_arrays > 7`

- **Location:** `src/desc.rs:88`. `n_bin_arrays << 5` on u8 panics with overflow-checks, or wraps otherwise.
- **Impact:** host or engine side only (parse rejects > 5).
- **Fix:** assert or mask in the encoder.

## Optimizer notes (no finding)

- Möbius × Möbius and DLMM mixes: 281 random pairs where the budget does not bind (CPMM, AMM v4, PumpSwap buy and
  sell, DLMM with bin steps 1–250, both fee modes, fee falling or rising, jittered depth). The plan's exact profit was
  within ≤ 2 units of the brute-force optimum.
- "Chosen worse than `e`" occurred 0 times wherever `E(e)` was defined.
- Route level on the real binaries (GLL3 ↔ 6D4E):

  | Route | Planned size | Realized = modeled profit |
  |---|---|---|
  | GLL3 −12% buy | 3,970,147,338 | 129,676,513 |
  | 6D4E buy → GLL3 +12% | 3,661,869,785 | 122,414,424 |

  Both beat the best of a 96-point grid. NoProfit was correctly returned at the 0.5–3% gaps, below the fees.
- `Fx` and U256 have no panics. All reads go through `get` + `from_le_bytes` under `#![forbid(unsafe_code)]`, so there
  are no alignment hazards in the crate. The only unsafe surface is the shell's `RefCell::as_ptr` views (DESIGN §4.5),
  which must end before the first CPI.

## Harness changes made by this review

All changes are under `program/venue-harness`:

- **`sizing-bridge/src/main.rs`** (opt-in, so `exactness.rs` is unchanged):
  - **probe mode** quotes the crate's own boundary sizes ±1, ±2: DLMM layer and bin drain thresholds, PumpSell and DAMM
    `cap_in`, fee-ceil residues;
  - **plan mode** runs `arbx_sizing::plan` over engine-layout legs.
- **`tests/adversarial.rs`** (new): the boundary, Clock and mutation matrix above. It fails today on F1, F2, F5 and F8.
- **`tests/route.rs`** (new): planner route checks on the real programs. It passes.
- **`.gitignore`**: `results/adversarial.json`.
- **Probes outside the repo** (scratchpad; reproducible from the descriptions above):
  - random-pair brute force (F3);
  - the walk-length probe (F6);
  - the SBF CU runner with bin-step-1 and basket cases (F4).

## Disposition (2026-10-04, fixes in `arbx-sizing` and `venue-harness`)

Every blocker and major finding is fixed with a regression test; the minor ones are fixed or settled as noted. The
exactness gate now passes with **0 mismatches** on both suites against the real binaries. Sizing CU is bounded
statically from the block alone and measured below that bound on every route.

### Findings

| # | Disposition | Change | Regression test |
|---|---|---|---|
| **F1** blocker | **Fixed** | `pumpswap.rs`: `held_0`/`held_1` (u64 @271, @279) read; a sell pays out at most `Q − (held_0 + held_1)` in `sell_quote` and the exact `cap_in`. The program subtracts them on both instructions (a buy fails 6023 Overflow when they exceed the vault, found by the new mutations), so `held > Q` is `Abort::Pump(HeldExceedsVault)` for both legs. The names come from no IDL: the on-chain IDL predates the virtual reserves; most likely the unswept protocol/creator fee buckets | `review.rs::f1_f9_pumpswap_held_quote_and_layout_gate` (exact capacity at cap / cap+1 over 200 states, price unchanged), `review.rs::f1_plan_respects_the_held_quote_capacity` (planned size executes, sits on the last feasible size, 60 BOOST-like routes); `adversarial.rs` "held quote …" (7 splits × 3 pools, cap ±2): all exact, the CyJw snapshot rows (cap ±2, 11 mutations) all exact |
| **F2** blocker | **Fixed** | `buy_quote` returns `spent = min(x, eff0 + fees(eff0))`; `plan`'s profit is `q1.out − q0.spent` (the guard's quote delta) everywhere, `modeled_profit_e` included | `review.rs::f2_pumpswap_buy_debit_and_plan_profit`; `exactness.rs` 1,000 consecutive 6ejg buys all exact (3,251 PumpSwap rows) |
| **F3** major | **Fixed** | `LegDesc::max_bins` (DLMM descriptor byte; 0 = DescError `BinBudget`), counting bins read; `QuoteErr::Budget` replaces TooLarge past it; `E(e) = Budget` → Fallback at `e` (reason `BUDGET`), never NoProfit; `MAX_STEPS = 704` is per leg (never binds before a leg ends); `DlmmLeg::bins_for(x)` gives the engine the exact budget; the harness verifies every Budget refusal against the unbounded quote and the bins it needs, and TooLarge-while-the-venue-swaps is now a MISMATCH | `review.rs::f3_budget_is_not_a_capacity_and_keeps_e`, `review.rs::f3_dlmm_dlmm_walk_is_not_cut_short` (DLMM ↔ DLMM, >64 steps, at the brute-force best); `route.rs` asserts "the venue fills e ⇒ E(e) evaluated". The reviewer's probe, rerun: e = 3e9 / 4e9 now evaluated, the plan sizes the true optimum 3.54e9 (47.84M vs 44.07M capped before); 1,200 random pairs (3 seeds): worst shortfall 4 units, 0 below `e` |
| **F4** major | **Fixed** | One exact DLMM walk serves the locator and the evaluator (exact drains `D`, `D'`; resumable cursors positioned at each optimum's bin); candidates resume from them and read ≤ `NEAR_BINS = 4` bins, step-backs ≤ 2, only `e` may walk from the active bin; the interior root is computed only when π' crosses 1 inside the interval; widening multiplies replace checked u128 ones on the hot path; golden section never over DLMM; `budget::cu_bound(block)` is a static bound (measured unit costs rounded up) | `review.rs::f4_cu_bound_is_static_and_monotone`; `sbf-check/cu-runner` exits nonzero if any route exceeds the bound of its own block, its recorded budget + 10%, or the few-bin basket exceeds 60k (passes at `--arch v0/v2/v3`) |
| **F5** major | **Fixed (refused)** | `dammv2::parse` returns `Abort::Damm(RateLimiter)` whenever the limiter is in force for the leg's direction; `parse_with_limiter` keeps the exact pricing for off-chain use; DESIGN §2.5/§3.6 corrected. Sizing a limited pool would need the instructions sysvar in the leg and a descriptor position for it | `optimizer.rs::rate_limited_damm_refuses_with_and_without_search`; `adversarial.rs` asserts the limited direction parses as `abort:Damm(RateLimiter)` (2E8c, 2HFs, 3Bu5: 87 aborted rows, 0 mismatches; a→b exact) |
| **F6** minor | **Fixed** | the guard runs on every step once an optimum is known and the profit is not rising | `review.rs::f6_guard_stops_the_walk_after_the_optimum`; probe: the reversion arb walks 4 bins (was 64), cu-runner 19.6k |
| **F7** minor | **Fixed** | pair 0 aborted ⇒ `E(e)` unknown: another pair executes only if it clears `min_profit` (net of tip and lamports), else Fallback at `e` with the abort's reason; never NoProfit | `review.rs::f7_basket_keeps_e_when_pair_0_aborts` (BASKET and SELF_SIZE, with EARLY_ABORT) |
| **F8** minor | **Fixed** | the walker's advance uses the pair's `min_bin_id`/`max_bin_id` (@24/@28) | `review.rs::f8_pair_bin_bounds_cap_the_walk`; `venues.rs::dlmm_properties` (random bounds); `adversarial.rs` "min_bin_id = active−1 …" (4 pools: both refuse, 0 mismatches) |
| **F9** minor | **Fixed; corrected by the WP-16 review** | the pool must be exactly 301 bytes (`Abort::Layout`), unidentified tail bytes 270 and 287..301 must be zero (`Abort::Pump(UnknownTail)`). **2026-10-05 (docs/reviews/WP-16-review.md F1, F2):** right for on-chain sizing, where an abort falls back to `e`, wrong for the engine, where a refusal drops the route: 300-byte pools (14 live, ≈12,000 SOL) and holder-reward pools (byte 270 = `is_holder_reward`, 34 live) trade and the crate is exact on them on the dumped binary. Now: every length the program reads (211..=301, each missing trailing group read as zero, pinned per group), a longer pool `Layout`; byte 270 0 or 1 (another byte `Layout`); 287..301 must still be zero | `f1_f9_…` (lengths, byte 270, the tail), `wp16_short_pools_read_their_missing_groups_as_zero`; `adversarial.rs` "pool cut to L bytes", "is_holder_reward = 1", "byte 270 = 2 (no Borsh bool)" |
| **F10** minor | **Fixed** | new flag `LAMPORTS` (bit 5) carries `lamport_offset: i32` in the block; `PlanIn::lamport_offset`; NoProfit judges `g = profit + offset` net of the tip on `g` | `review.rs::f10_lamport_offset_enters_the_no_profit_verdict`; `desc.rs::rules`/round trip |
| **F11** minor | **Measured; build choice for arbx-exec** | sizing adds ≈192 KB (206,392 B vs 14,584 B baseline); LTO fat + z 154,544 B; PumpSwap + DLMM only 137,528 B (LTO + z 107,096 B). `plan` is now `#[inline(never)]`: the LTO build had merged its parsed legs into the shell's frame (5,184 B > 4 KB) | SBF builds at v0/v2/v3 and LTO without frame warnings |
| **F12** minor | **Documented precondition** | quotes assume `x ≤` the payer's balance (the shell's `cap = min(amount_in, quote balance)` and leg 1's input is what leg 0 delivered), so `vault + x ≤ supply ≤ u64::MAX`; the harness keeps skipping sizes above 2^62, where its wallet is funded beyond the supply | — |
| **F13** minor | **Partly closed** | plan fuzz on parsed blocks (`fuzz_plan.rs`: 40,000 blocks, 12,654 parsed, 4,093 planned, every Sized/NoProfit amount re-checked exactly); a BASKET route on the real binaries (`route.rs::hotbot_basket_on_the_real_programs`); CU regression in the cu-runner. C9xc has no liquidity any more (empty bitmap), so the basket uses both directions of GLL3 ↔ 6D4E. Route tests through arbx-exec (assertions 1, 6, 7) still need its `sizing` feature | `fuzz_plan.rs`, `route.rs` |
| **F14** minor | **Fixed** | a candidate past a capacity or the budget gallops back (×4 from 2^-24·x̂, ≤ 8) and bisects (≤ 8), at most 8 step-backs per plan; BASKET pairs keep their candidate | `review.rs::f14_step_back_reaches_the_capacity` (40 small-size capped routes: planned size feasible and within the tolerance of the last feasible size) |
| **F15** nit | **Fixed** | `kd()` masks `n_bin_arrays & 7` | `desc.rs::kd_masks_the_array_count` |

Also fixed on the way: a DLMM layer's `get_amount_in` is now computed only when the swap reaches the layer with input
left (the program's order; before, an exactly-drained MM layer followed by a limit-order layer whose input does not
fit u64 gave TooLarge), and the DLMM variable fee uses widening multiplies (checked against the u128 formula on 80,000
cases, `primitives.rs::dlmm_rate_fast_path_equals_the_formula`).

### Exactness against the real binaries (final run)

| Suite | exact | both refuse | budget¹ | venue CU limit² | aborted | MISMATCH |
|---|---|---|---|---|---|---|
| `exactness.rs` | 7,145 | 247 | 9 | 0 | 178 | **0** |
| `adversarial.rs` | 39,444 | 2,921 | 160 | 169 | 607 | **0** |
| `route.rs` | 6 routes + 4 baskets: realized == modeled to the unit at the plan and at `e` | | | | | **0** |

Per venue (exactness / adversarial exact rows): PumpSwap 3,753 / 2,763; DLMM 1,005 / 19,870; DAMM v2 1,187 / 9,180;
CPMM 686 / 4,520; AMM v4 514 / 3,111. Aborts: TransferFee (Hmx1, 2cUM), DAMM rate limiter (87), PumpSwap held > vault
and tail byte (mutations), AMM v4 status 7 not open.

¹ `Budget`: a DLMM swap past the leg's 255-bin budget; its unbounded quote matched the venue (or both refuse) and it
really needs more bins. ² The venue itself ran out of the 1.4M transaction CU (from ≈246 bins read; the largest
successful swap read 256): not a maths verdict, and the engine's budgets keep sized routes far below it.

Venues and states sizing refuses (and must): DAMM v2 with the rate limiter in force (b→a); PumpSwap with held amounts
above the vault, a pool length other than 301, or bytes 270 / 287..301 set (plus the existing mayhem, cashback,
disabled, virtual-reserve and fee aborts); Token-2022 transfer fees and hooks; DLMM/DAMM states listed in DESIGN §2.4,
§2.5. A DLMM walk past `max_bins` is not refused but falls back to `e`. (Corrected by the WP-16 review, 2026-10-05:
PumpSwap pools of 211..=301 bytes and byte 270 = 1 are priced, and so are mayhem pools; see the F9 row.)

### CU (sbpfv3, sizing only; full table in DESIGN §4.7)

| Route | before | after | `cu_bound` (cap / tight budgets) |
|---|---|---|---|
| CPMM → AMM v4 | 7,095 | 7,191 | 26.5k |
| DLMM → CPMM, 1 / 2 / 3 bins | 12.9k / 17.5k / 22.5k | 13.5k / 15.7k / 16.4k | ≤1.05M / 86-98k |
| HOTBOT GLL3 → 6D4E, −12% (sized) | 30,674 | 26,152 | 244k / 111k |
| 3-pair DLMM basket, few bins (target ≤ 60k) | 36,638 | 41,013 | 1.95M / 184k |
| PumpSwap + 3 DLMM basket, 34 bins | 176,015 | 112,768 | 1.29M / 337k |
| DLMM(bin step 1, 3% gap) → CPMM | 260,076 (stopped at 64 bins) | 169,927 (to the true optimum, 90 bins) | 1.05M / 513k |
| DLMM(bin step 5, 3% gap) → CPMM | 159,010 / 173,503 | 80,304 / 86,665 | 1.05M / 266k |
| reversion arb (F6) | ≈110k extra | 19,592 | 110k (tight) |
| 3-pair bin-step-1 basket | 456,626 (64-bin caps) | 441,349 (48-bin budgets) / 1,275,222 (255) | 951k / 4.4M |

Per bin read: ≈1.85k for the locator (walk 352 + exact drain 607 + model ≈900), ≈1.5k + 0.9-1.4k per bin for an
exact quote; the venue's own swap ≈5.45k per bin. The few-bin basket costs 4k more than before (the exact drains in
the locator) and stays within the 60k target; every long walk got cheaper and now reaches its optimum.

### SBF build status

`cargo-build-sbf` (platform-tools v1.57) builds the sizing check at `--arch v0`, `v2` and `v3` and with LTO fat +
opt-level z, with no warnings and no stack-frame errors; every cu-runner route executes on v0, v2 and v3 (v2 ≈14%
cheaper on long walks).

### Tests

- `arbx-sizing`: 61 tests with all features (desc 6, differential 6, fuzz_plan 1, mainnet 2, optimizer 10, primitives
  12, review 11, venues 13), 55 with the default features; `cargo build --no-default-features` and the per-venue SBF
  builds compile.
- `venue-harness` (with `VENUE_HARNESS_REQUIRE_SIZING=1`): 16 tests + 1 doctest, all passing (adversarial, api 5,
  exactness, pins 3, route 2, swaps 3).
- Reproduce: `cargo test --release --all-features` (arbx-sizing); `VENUE_HARNESS_REQUIRE_SIZING=1 cargo test --release
  -- --nocapture` (venue-harness); the SBF builds and `cu-runner` (`TIGHT=1` for the tight budgets) per
  `sbf-check/README.txt`.

### Open issues

1. **arbx-exec integration.** Route tests through arbx-exec (DESIGN §6.3 assertions 1, 6, 7) wait for its `sizing`
   feature; the shell must parse the new block fields (`max_bins`, LAMPORTS), pass `lamport_offset`, keep the account
   views out of its own large frames (DESIGN §4.8) and add `cu_bound(block)` to the CU limit.
2. **Engine rules.** The engine must set each DLMM leg's `max_bins` with `DlmmLeg::bins_for` (at least the bins for `e`;
   the tight rule `max(e, 1.25·x̂) + 2` keeps the bound near the measured CU) and set LAMPORTS whenever EARLY_ABORT
   runs with COUNT_LAMPORTS. Budgets from the cap alone give a correct but loose bound (up to ≈1M per 255-bin leg).
3. **Code size** (F11): ≈192 KB of sizing (≈144 KB with LTO); build arbx-exec's feature with only the kinds in use and
   budget the rent.
4. **PumpSwap tail.** `held_0`/`held_1` are named from behaviour, not from an IDL; bytes 270 and 287..301 are refused
   when set. Re-pin when pump.fun publishes a newer IDL. (2026-10-05: byte 270 is `is_holder_reward` in pump.fun's
   public IDL and is priced; 287..301 stay refused when set.)
5. **BASKET CU.** A leg shared by two pairs is walked once per pair; a per-leg walk cache would cut long baskets
   (bin-step-1 legs) by up to a third. Not needed for the few-bin baskets (41k).
6. **Three-pool basket on real binaries.** C9xc is drained; another same-mint pool set is needed for a 3-pair basket
   on the real programs.
7. **Clippy** was not run (the component is not installed and was not installed here); the crate keeps
   `#![forbid(unsafe_code)]`, the `deny` lints are unchanged and the new code uses no unwrap/expect/indexing.

### Files changed

- `arbx-sizing`: `src/{budget.rs (new), desc.rs, error.rs, leg.rs, lib.rs, math.rs, opt.rs, plan.rs,
  venue/{pumpswap,dlmm,dammv2}.rs}`, `tests/{review.rs, fuzz_plan.rs (new), common/mod.rs, desc.rs, differential.rs,
  mainnet.rs, optimizer.rs, primitives.rs, venues.rs}`, `sbf-check/{Cargo.toml, src/lib.rs, README.txt,
  cu-runner/src/main.rs}`, `DESIGN.md` (revision note at the top; §0-§7 updated), this Disposition.
- `venue-harness`: `sizing-bridge/src/main.rs` (budgets, unbounded cross-check, exact DLMM capacity probes, the
  engine's `max_bins` rule in plan mode), `tests/{exactness.rs, adversarial.rs, route.rs}` (Budget and venue-CU
  verdicts, held-amount and tail mutations, the rate-limiter assertion, the BASKET route), `README.md`;
  `fixtures/rpc-cache` gained one read-only response (the PumpSwap on-chain IDL account, fetched to name the tail
  fields).

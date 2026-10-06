# arbx-sizing: on-chain sizing (SELF_SIZE, BASKET) for arbx-exec

Status: implemented in this crate, revised 2026-10-04 after the adversarial review (`REVIEW.md`, Disposition at its
end). Sizing ships **off by default**: the engine sets no SELF_SIZE or BASKET bit until the exactness gates in §6 pass,
venue by venue.

**Revision 2026-10-04 (review fixes), in one list** — each item is detailed in the section named:
- PumpSwap: a sell pays out at most `Q − (held_0 + held_1)` (pool u64 @271, @279), the pool is accepted at exactly
  301 bytes with its unidentified tail clear, and `buy_exact_quote_in` debits `min(x, eff0 + fees(eff0))` (§2.1).
  **Corrected 2026-10-05 (WP-16 review F1, F2):** the pool is read at every length the program reads (211..=301, each
  missing trailing group as zero), byte 270 is `is_holder_reward` (0 or 1, priced), a mayhem pool is priced on the
  fixed 1e15 supply, and the exact-out `buy` has its closed form (host only).
- DLMM: the pair's own `min_bin_id`/`max_bin_id` bound the walk; the walk budget is a per-leg descriptor field
  `max_bins` (bins read) that the engine sizes from its own quote, and a walk past it answers `Budget` ("not
  evaluated"), never TooLarge (§2.4, §4.3).
- DAMM v2: a rate limiter in force refuses the leg (the venue needs the instructions sysvar the engine's leg does not
  pass, 6049 at every size) (§2.5).
- The planner: profit = sell output − buy-leg debit; `E(e)` unknown (pair 0 aborted, or `e` past a walk budget) makes
  `e` the fallback instead of dropping it; a step-back reaches the last feasible size; the NoProfit verdict counts the
  block's lamport offset (§3.5, §3.7, §4.2).
- The locator: the step bound is per leg, the non-concavity guard runs on every step after an optimum, the DLMM bins
  are walked once with their exact drain amounts, and exact evaluations resume from the exact swap states the walk
  passed (§3.4).
- CU: measured, and bounded statically by `budget::cu_bound` from the block alone (§4.7).

**Revision 2026-10-06 (PLAN-ADDENDUM WP-21 phase A, step 1): Raydium CLMM and Orca Whirlpool**, kinds 7 and 8:
- exact swap maths for both concentrated-liquidity venues, exact in and exact out, ported from the deployed commits and
  proven against the deployed binaries in the venue harness: 0 mismatches and 0 false refusals, amounts and post-swap
  pool state, on 20 mainnet pools, their byte mutations and the adversarial states (§2.8, §2.9, §6.3);
- every state the maths does not cover is refused with a typed reason (`Abort::Clmm`, `Abort::Whirl`; a paused or
  default-frozen Token-2022 mint too), never approximated, and each refusal is checked against the venue;
- the locator treats them as piecewise Möbius legs, one piece per exact swap step (§3.4);
- behind the crate features `rayclmm` and `whirlpool` (`clmm` = both), **off by default**: the engine and arbx-exec
  build and behave exactly as before until they integrate the kinds. §9 lists what that integration needs. On-chain
  sizing of these kinds stays off: their `budget` costs are estimates until sbf-check measures them (§4.7).

Inputs:
- `docs/research/redesign-final.md` §3.9 (the v3 layout and the reserved SELF_SIZE/BASKET bits; target of at most ~60k
  extra CU for a 3-pair DLMM basket).
- `docs/research/docs-review-synthesis.md` §4 item 2 (the maths per venue family).
- `docs/research/rival-synthesis.md` (Bgokg3ju, A9pQ1Qsv, 8oSD5a9E, MEViEnsc).
- `verify-all-doc1-report.md` and `verify-all-doc2-report.md` (how MEViEnsc's `optimal_input` and Babq's sizer work).
- The reference maths in `src/venues/{cp,dlmm,dammv2}.rs` and `src/pools.rs`.
- The arbx-exec source as of today (`program/arbx-exec/src/lib.rs`, read only).

Everything marked **verified** in this document was checked for this design. The scripts and their outputs are in
`program/arbx-sizing/research/` (index in §8). All RPC was public mainnet, read-only, rate-limited and cached in
`program/venue-harness/fixtures/rpc-cache/`.

---

## 0. The design in one page

1. **What sizing does.** The program re-quotes the route's pools from accounts the venue CPIs need anyway, at execution
   time. It picks the input `x` (and, with BASKET, the pool pair) that maximises the round-trip profit. It then runs
   the legs exactly as today. The guard (`g ≥ min_profit`, i128) is unchanged and stays the hard backstop, so a sizing
   bug can make a route revert but cannot make it land with less than `min_profit`.
2. **Exact evaluator plus approximate locator.** For each venue the crate carries a quote function that reproduces the
   venue program's integer output to the token unit, including the venue's own rounding. It returns either that
   output or `Abort` (or `Budget` past a DLMM leg's walk budget: not evaluated). The optimizer finds a candidate `x*`
   from a cheap real-valued model of each leg:
   - a Möbius curve `A·u/(B + C·u)` for the constant-product family and for DAMM v2 inside its range;
   - one linear segment per bin for DLMM.

   It solves for `x*` in closed form (§3.3, §3.4). The final choice is made only by **exact evaluation** of a few
   candidates: `x*`, the engine's own amount `e`, and the cap when the solution sits on it.
3. **Never worse than the fixed amount.** `e` is always a candidate, and the choice is the argmax of the exact profit.
   The realized profit is therefore at least what `e` would have made. This rests on exactness, which the harness
   proves (§6.3). See the proof sketch in §3.5. Where `E(e)` cannot be computed (pair 0 aborted; `e` past a DLMM
   walk budget) `e` is kept as the fallback rather than dropped (§3.5).
4. **When the model cannot handle a state, fall back.** If a leg is in a state the model does not cover (an unknown
   layout, a venue feature it does not model, a Token-2022 transfer fee), the program executes pair 0 at the engine's
   amount `e`. That is exactly today's behaviour. The STRICT flag turns this into a revert instead.

   A malformed or inconsistent descriptor (wrong owner, wrong key, wrong direction) is an engine bug, so it always
   reverts.
5. **Encoding.**
   - SELF_SIZE adds a 15-byte block after the v3 leg metas (+4 with the LAMPORTS flag).
   - Each leg's descriptor is 1 byte (kind, direction, number of DLMM bin arrays). PumpSwap adds 1 byte (the
     pool-authority bump), DLMM 1 byte (the walk budget `max_bins`).
   - Default positions of the state accounts are compiled in. They equal the engine's builder layout
     (`src/build.rs`), and explicit positions are optional.
   - BASKET lists up to 3 `(buy_leg, sell_leg)` pairs over up to 6 distinct legs, so pools shared by several pairs are
     encoded once.
   - Unused legs are skipped by prefix-summing account counts. They are never invoked.
6. **Cost (measured on SBF, §4.7; the estimates this replaces were 4-55k).**

   | Route | Sizing CU (measured) |
   |---|---|
   | CPMM-family ↔ CPMM-family | 7-11k |
   | DLMM ↔ CPMM-family, 1-3 bins | 13-16k |
   | DLMM ↔ DLMM, few bins | 18k |
   | DAMM v2 ↔ CPMM | 11-18k |
   | HOTBOT PumpSwap ↔ DLMM (real state, sized) | 26k |
   | 3-pair DLMM basket, few bins | 41k |
   | per DLMM bin the walk reads | ≈1.85k (the venue's own swap: ≈5.45k per bin) |

   Every plan is bounded statically by `budget::cu_bound(block)`, which the engine adds to the CU limit. Size: +15 B for SELF_SIZE, and about +25 B of sizing data
   plus about 2 legs' worth of leg encoding for a 3-pair basket, which needs ALT coverage (§4.6).
7. **Modes for rollout.**
   - SHADOW computes and logs the plan (an AXZ1 record) but executes `e`. It gives production exactness data at zero
     risk.
   - EARLY_ABORT reverts (or no-ops under NOOP_ON_MISS) before any CPI when no size clears `min_profit`.

**Facts established for this design (verified):**

**PumpSwap**
- It has gained features that are all live on mainnet today: virtual quote reserves, a per-pool configurable creator
  fee, a buyback fee and an "eff−1" term in buy_exact_quote_in.
- The model in §2.1 matches the program's own Buy/SellEvents field for field on **112 of 112** mainnet swaps,
  including 23 `buy_exact_quote_in` and 77 virtual-reserve swaps.

**DLMM**
- DLMM is now **v0.12**. Every sampled pair has `function_type = 2` (LimitOrder): bins carry limit-order liquidity at
  the bin price.
- One sampled pair has `collect_fee_mode = 1` (fee on the Y output for X→Y).
- The engine's off-chain DLMM quote models neither feature (§2.7).

**Raydium CPMM**
- With the creator fee charged on the input, the program takes a single ceil of `x·(trade+creator)`.
- The engine charges two separate ceils (§2.7).

**Runtime**
- `sol_remaining_compute_units` is **not active on mainnet** (feature 5TuppMuto…, see arbx-exec
  `review/tests/adversarial.rs`). Sizing must not depend on it at runtime.

---

## 1. Scope

### 1.1 Route shapes

- **SELF_SIZE.** A 2-leg round trip `A → X → A`. A is the quote mint (wSOL or USDC), and X is any mint with no
  Token-2022 transfer fee.
  - Leg 0 spends `x` from the quote account and delivers into the X account.
  - Leg 1 spends exactly what leg 0 delivered (balance chaining, unchanged) and delivers into the quote account.
  - NATIVE legs (pump.fun bonding curve) are excluded. A descriptor that combines them with SELF_SIZE is
    `ERR_SIZING_DESC`.
- **BASKET.** Up to 3 candidate `(buy pool, sell pool)` pairs for one mint X. Each pair is sized independently, and
  the best by exact profit is executed. Only one pair executes, so pools may be shared between pairs.

### 1.2 Leg kinds (venue + instruction)

| kind | Venue / instruction | Allowlist id | amount_offset | Leg accounts (engine layout) |
|---|---|---|---|---|
| 1 `PumpBuy` | PumpSwap `buy_exact_quote_in` (quote in, base out) | 3 | 8 | 23 + tail (pool-v2, buyback, buyback ATA) |
| 2 `PumpSell` | PumpSwap `sell` (base in, quote out) | 3 | 8 | 21 + tail |
| 3 `RayCpmm` | Raydium CPMM `swap_base_input` | 6 | 8 | 13 |
| 4 `RayAmmV4` | Raydium AMM v4 `swap_base_in_v2` (tag 16) | 7 | 1 | 8 |
| 5 `Dlmm` | Meteora DLMM `swap2` (exact in) | 0 | 8 | 16 + 1..=5 bin arrays |
| 6 `DammV2` | Meteora DAMM v2 `swap` (or `swap2` mode 0, ExactIn) | 8 | 8 | 14 |
| 7 `RayClmm` | Raydium CLMM `swap_v2` (exact in, no price limit) | 2 | 8 | 13 + 1..=7 remaining (the bitmap extension when it exists, then the tick arrays) |
| 8 `Whirlpool` | Orca Whirlpool `swap_v2` (exact in, no price limit) | 1 | 8 | 15 + 0..=3 supplemental tick arrays |

Kinds 1-6 are exactly the instructions `src/build.rs::leg()` builds today. Kinds 7 and 8 (PLAN-ADDENDUM WP-21) are
parsed only with the crate features `rayclmm` / `whirlpool`; without them they are `Abort::Unsupported`, and the engine
does not build their legs yet (§9). Kinds 0 and 9-15 are invalid. Whitelisted pre-activation swaps (DAMM v2),
transfer-hook mints and partial-fill modes are out of scope. Exact out is priced host-side only (PumpSwap `buy`, the
CLMM kinds' `quote_exact_out`): the route's legs are exact in.

### 1.3 The guard, defaults and modes

- The guard is not touched.
  - `g = Δquote (+ Δlamports with COUNT_LAMPORTS)`.
  - The route reverts unless `g − tip ≥ min_profit`.
  - With CPI_TIP, maximising `g` also maximises `g − tip(g)`, since `tip` is a clamped fraction (≤ 100%) of `g`.
    Sizing therefore maximises the modeled quote gain.
  - Lamport side effects of a venue (for example PumpSwap creating a fee-recipient ATA paid by the user) do not depend
    on `x`, so they do not move the argmax. They do move the NoProfit verdict under COUNT_LAMPORTS: the block's
    optional `lamport_offset` (LAMPORTS flag, §4.2) carries the engine's modeled lamport delta of the executed legs,
    and `plan` judges `g = profit + lamport_offset` as the guard does (REVIEW.md F10).
- Sizing flags live in the sizing block (§4.2):
  - **STRICT**: revert instead of falling back.
  - **EARLY_ABORT**: revert before any CPI when no candidate clears `min_profit`.
  - **SHADOW**: plan and log, but execute pair 0 at `e`.
  - **SEARCH**: allow the golden-section fallback.
  - **EXPLICIT_POS**: positions are listed explicitly.
  - **LAMPORTS**: the block carries `lamport_offset` (i32).
- The engine keeps sizing off until §6.6 passes. It then enables sizing per venue kind, starting with SHADOW.

### 1.4 What was verified for this document

| Check | How | Result |
|---|---|---|
| Every byte offset in §2 | `research/check_layouts.py` on 11 mainnet pools (2 PumpSwap, 3 DLMM incl. bin arrays, 3 DAMM v2, 2 CPMM, 1 AMM v4) plus GlobalConfig, FeeConfig, mints and the Clock, at slot 453,207,209. It checks owners, sizes, discriminators and cross-references (each vault holds the pool's mint; each bin array's `lb_pair` and `index`; bitmap bits against array existence) | `research/layout-check.txt`: **0 failures** |
| PumpSwap pricing model (§2.1) | `research/pump_events_check.py`: decodes the program's BuyEvent/SellEvent (emit_cpi) from 300 recent signatures and recomputes every field from the event's pre-swap reserves | `research/pump-events-check.txt`: **112/112 events exact** (78 sell, 11 buy, 23 buy_exact_quote_in; 77 with virtual reserves) |
| Venue sources | Public sources at these commits: MeteoraAg/dlmm-sdk `576919e` (2026-09-03; IDL lb_clmm **0.12.0**, `commons/src/quote.rs`), MeteoraAg/damm-v2 `a85c926` (2026-09-08, same commit `src/venues/dammv2.rs` was ported from), raydium-cp-swap `b3187ae` (2026-10-03), raydium-amm `d26944b`, `@pump-fun/pump-swap-sdk` 1.20.0 (2026-09-10; IDL `pump_amm`). PumpSwap is closed source, so its events are the oracle | Formulas in §2 |
| SBF primitive costs (§4.7) | `research/cubench`: an SBF program run in LiteSVM 0.17 (platform-tools v1.57, sbpfv3) | Table in §4.7 |
| Maths of §2.4, §2.5 and §3.3 | `research/math_checks.py`: brute force | `research/math-checks.txt`: DLMM drain tests identical (1.2M cases); DAMM v2 exact capacities 60k/60k; CPMM-CPMM closed-form integer loss ≤ 0.31 × 2ε |

---

## 2. Venue models

### 2.0 Common rules

**Notation.**
- `⌊a/b⌋` is floor and `⌈a/b⌉` is ceil.
- All products are computed in u128 (or U256 where noted) and never overflow silently: every step is `checked_*`, and
  any overflow returns `Abort::Math`.
- `x` is the leg's input and `out` the amount the user's output account gains.

**Token accounts.** Mint at @0, owner at @32, amount u64 at @64, owned by Tokenkeg or Token-2022. A Token-2022 account
may be longer than 165 bytes, so only the first 72 bytes are read.

**Transfer fees.** For every Token-2022 mint a leg touches, scan the TLV list starting at offset 166 (the account type
byte is at 165):
- extension type 1 (TransferFeeConfig) with a nonzero `transfer_fee_basis_points` in either the older or the newer
  fee (each at fee+16, after `epoch u64, maximum_fee u64`) → `Abort::TransferFee`;
- type 14 (TransferHook) → `Abort::TransferHook`.

This is the same rule as `src/pools.rs::has_transfer_fee`. The HOTBOT mint (Token-2022, extensions 18 and 19 only)
passes. A TransferFeeConfig with a nonzero rate but `maximum_fee = 0` charges nothing (Token-2022 caps the fee at
`maximum_fee`); the scan still refuses it, a conservative refusal (§7 item 10).

**Paused and default-frozen mints (kinds 7 and 8).** `token::mint_blocked` also refuses a Token-2022 mint with
extension 26 (Pausable) whose `paused` byte (value + 32) is set — every transfer fails — and one with extension 6
(DefaultAccountState) set to Frozen (2): the token account the leg creates for it is frozen, so the swap fails at every
size (the harness: both refuse, appended or set, on both venues). The kinds 1-6 do not check these yet (§7 item 9).

**Clock.** Read once through the `sol_get_clock_sysvar` syscall: `slot`, `unix_timestamp`, `epoch`. No account is
needed.

**Owner and key checks** run before any field is trusted (failures are `DescError`, §2.6):
- the pool/state account is owned by the leg's venue program;
- the vaults are token accounts whose key equals the key stored in the pool;
- config accounts are owned by the expected program and have the expected discriminator;
- the leg's input account (the quote account for a buy leg, the buy leg's output account for a sell leg) holds the
  mint the pool expects on the input side for the descriptor's direction.

**Version gates.** Every layout is accepted only at the lengths and version bytes listed below. Anything else is
`Abort::Layout`, which falls back to `e`. A venue upgrade that grows an account therefore turns sizing off for that
venue instead of mispricing it. PumpSwap's pool is the one account read at several lengths: every length the program
itself reads, from its original layout up to the current one, the way the program reads it (§2.1; WP-16 review F1).

Each venue section gives:
- **state** (accounts, positions, offsets);
- **exact** (the integer formula the evaluator runs);
- **model** (real-valued parameters for the optimizer);
- **capacity**;
- **abort**.

### 2.1 PumpSwap (`pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`)

**State.** All of these accounts are already in the leg. Positions are from the engine layout
(`src/build.rs::pump_leg`).

| Pos (buy / sell) | Account | Checks / fields read |
|---|---|---|
| 0 | Pool (owner pAMM, disc `sha256("account:Pool")[..8]`, len **211..=301**: the program's original layout up to the current one; mainnet pools are 287, 300 and 301 bytes) | base_mint @43, quote_mint @75, pool_base_token_account @139, pool_quote_token_account @171, creator @11, coin_creator @211, is_mayhem_mode @243, is_cashback_coin @244, **virtual_quote_reserves i128 @245**, **creator_fee_bps u64 @261**, can_edit_creator_fee @269, **is_holder_reward bool @270**, **held_0 u64 @271, held_1 u64 @279**, then 14 unidentified bytes. The IDL fields end at 271 (pump-public-docs `idl/pump_amm.json`, 2026-09-12: `is_holder_reward` appended after `can_edit_creator_fee`); holder rewards only redirect the creator fee ("no changes to any trade instruction", HOLDER_REWARDS_README) and the crate is exact on holder-reward pools on the dumped binary. `held_0 + held_1` (in no IDL) is a quote amount the program holds back from the real vault (most likely the unswept protocol and creator fee buckets, cf. SweepProtocolFee / SweepCreatorFee): nonzero on mainnet (CyJw 1,469,628 + 2,939,251; GLL3 and 6ejg earlier), it does not move the price but bounds a sell's payout (below). **A shorter pool** (written before a trailing field existed) is read as the program reads it, pinned on the dumped binary by cutting pools at every boundary ±1 (venue-harness `tests/adversarial.rs` "pool cut to L bytes"): below 211 bytes it fails InvalidAccountData; above, each trailing group is read only when the pool holds all of it, else as zero / false: coin_creator @211..243, is_mayhem_mode @243, is_cashback_coin @244, the virtual reserve @245..261 (a partial one reads as 0), creator_fee_bps together with can_edit_creator_fee @261..270, is_holder_reward @270, the two held amounts together @271..287. The bools (@243, @244, @269, @270) are Borsh bools: a byte other than 0 or 1 fails the program's deserialization → `Abort::Layout`. A present byte of the unidentified tail 287..301 that is not zero → `Abort::Pump(UnknownTail)` (zero on every pool seen) |
| 2 | GlobalConfig `ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw` = PDA["global_config"] (len **949**, disc `95089ccaa0fcb0d9`) | lp_fee_bps @40, protocol_fee_bps @48, disable_flags @56 (bit 3 buy, bit 4 sell), coin_creator_fee_bps @313, buyback_basis_points @899, **creator_fee_configurable @940**, max_configurable_creator_fee_bps @941 |
| 3 | base mint | supply u64 @36 (market cap); transfer-fee scan |
| 4 | quote mint | key: SOL-like / USDC / other (fee schedule); transfer-fee scan |
| 7, 8 | pool base / quote vaults | key == pool @139 / @171; amount @64 → `B`, `Q` |
| 21 / 19 | FeeConfig `5PHirr8joyTMp9JMm6nW7hNDVyEYdkzDqazxPD7RaTjx` = PDA["fee_config", pAMM] under `pfeeUxB6…` (owner pfee, disc `sha256("account:FeeConfig")`, len **4097**) | Borsh, read sequentially: bump @8, admin @9, flat_fees @41 (lp, protocol, creator: u64 each), `fee_tiers: Vec<{u128 threshold, Fees}>` @65 (u32 length, then 40 B per tier), then `stable_fee_tiers` (same shape), then `exotic_flat_fees` (24 B; all zero means unset, use flat). Mainnet values: 25 tiers, 25 stable tiers, exotic @2073 = (20,5,5), flat (25,5,0). Tiers run from (0: 2/93/30) and (4.2e11: 20/5/95) to (9.824e13: 20/5/5) |

Values on 2026-10-04: lp 20, protocol 5 and coin creator 5 bps in GlobalConfig (used only without a FeeConfig, which
never happens on chain); buyback 5000; creator_fee_configurable on, with a 300 bps maximum. Pool GLL3 has
V = 17,542,101,293. Pool 6ejg has creator_fee_bps = 200.

**Fee selection.** This mirrors pump-amm `compute_fees`, as `computeFeesBps` in SDK 1.20 does.

1. `Qv = Q + V`, where V is the signed i128. Require `0 < Qv < 2^64`; otherwise `Abort::Pump(Virtual)`.
2. `canonical` holds iff `creator == create_program_address(["pool-authority", base_mint, [bump]], 6EF8rrecth…)`. The
   bump comes from the descriptor (§4.3), and this costs one syscall (about 1.5k CU). A descriptor bump of 0 means
   "not canonical" (a real bump of 0 has probability about 2^-255). That claim is trusted, and the guard backstops
   it: the engine reads canonical-ness off chain at boot, as `src/pools.rs` does today.
3. Non-canonical → `flat_fees`. Canonical:
   - SOL-like quote (default key, So111…112, Token-2022 native `9pan9…`) → `fee_tiers` by market cap;
   - USDC (`EPjF…`) → `stable_fee_tiers` (or `fee_tiers` if the stable list is empty);
   - any other quote → `exotic_flat_fees`, or `flat_fees` when exotic is all zero.

   Market cap is `mc = ⌊Qv · S / B⌋`, where `S` = mint supply, or the fixed 1e15 for a mayhem pool (pinned on the
   dumped binary: GxqG priced on 1e15 with its mint's supply scaled ×1/1000 to ×2000; a mayhem pool also takes the
   reserved fee recipients and no buyback, neither of which changes the user's amounts). Pick tier 0 if
   `mc < t0`, otherwise the last tier with `mc ≥ threshold`. This is computed from the PRE-swap reserves, so it is
   constant during the swap.
4. If `creator_fee_configurable && creator_fee_bps > 0`, then `cr = creator_fee_bps`.
5. If `coin_creator == 0`, then `cr = 0`.
6. Require `lp + pr + cr < 10_000`.

The buyback fee (`buyback_basis_points`, 5000 today) is a carve-out of the protocol fee:
`buyback = ⌊protocol_fee · bb / 1e4⌋`, verified on 112/112 events. It **does not change user amounts**, so the model
ignores it.

**Exact, sell (base in `b`, quote out).** All verified 78/78:

```
q   = ⌊Qv·b / (B + b)⌋
lp  = ⌈q·lp/1e4⌉ ; pr = ⌈q·pr/1e4⌉ ; cr = ⌈q·cr/1e4⌉          (each fee rounded up separately)
out = q − lp − pr − cr                                          (cashback coins also subtract ⌈q·cb/1e4⌉: not modelled, see abort)
require: q − lp ≤ Q − (held_0 + held_1)   (else 6063 InsufficientRealQuoteReserves; pinned by bisection on the
                                          dumped binary, REVIEW.md F1: the SDK 1.20 check `q − lp ≤ Q` misses the
                                          held amounts),  out > 0
```

**Exact, buy_exact_quote_in (quote in `x`, base out).** All verified 23/23:

```
F    = lp + pr + cr
eff0 = ⌊x·1e4 / (1e4 + F)⌋
fees(e) = ⌈e·lp/1e4⌉ + ⌈e·pr/1e4⌉ + ⌈e·cr/1e4⌉
eff  = eff0 − max(0, eff0 + fees(eff0) − x)
out  = ⌊B·(eff − 1) / (Qv + eff − 1)⌋              (note the −1: present on chain, absent in src/venues/cp.rs)
spent = min(x, eff0 + fees(eff0))                 (pinned on the binary, venue-harness pins.rs: 9 of 16,200 buys debit
                                                   one unit less than x; REVIEW.md F2)
require: out ≥ 1, out < B, Q ≥ held_0 + held_1    (else the program fails 6023 Overflow on both instructions)
```

**Exact, buy (base out `out` exact; host only, WP-16 review F6).** The exact-out instruction third parties send most
(`PumpLeg::quote_exact_out`; on-chain sizing quotes exact in):

```
q     = ⌈Qv·out / (B − out)⌉                      (the quote that enters the curve)
debit = q + ⌈q·lp/1e4⌉ + ⌈q·pr/1e4⌉ + ⌈q·cr/1e4⌉    (each fee rounded up separately; base out is exactly `out`)
fail:  out = 0 (6001 ZeroBaseAmount), out ≥ B, q or debit past u64 (6024 Truncation, 6023 Overflow)
```

Pinned on the dumped binary (venue-harness `tests/pins.rs` `pumpswap_exact_out_buy_matches_its_closed_form`: 11,477
buys exact to the unit) and in the exactness suite (6,362 rows exact).

**Model.** A Möbius curve `out(u) = A·u/(B' + C·u)`:
- sell: `A = (1 − F/1e4)·Qv`, `B' = B`, `C = 1`;
- buy: `ψ = 1e4/(1e4+F)`, `A = ψ·B`, `B' = Qv`, `C = ψ`.

**Capacity.**
- Sell: the largest `b` with `q(b) − lp(q) ≤ Q − held`, exact in closed form (`PumpLeg::cap_in`). In the model:
  `q_max = (Q − held)/(1 − lp/1e4)`, so `b_max = B·q_max/(Qv − q_max)` (∞ if `q_max ≥ Qv`). On today's pools V/Q is
  0.7-5%, so the edge needs huge sells; with V ≫ Q (BOOST launches) it is at a few % of the base reserve.
- Buy: unbounded (`out < B` always holds for a finite `x`).

**Abort (falls back to `e`):**
- A mayhem pool (@243 = 1) is priced since the WP-16 review: its market cap is on the fixed 1e15 supply (above), and
  the crate is exact on mayhem pools on the dumped binary. `Pump(Mayhem)` is no longer returned (the variant stays so
  that the AXZ1 codes after it do not move).
- `Pump(Cashback)` when @244 = 1: the cashback bps source is not pinned, and the engine's leg cannot execute a
  cashback coin (with a pool_v2 it leaves out the cashback accounts: 6060 / 6061; without one the program refuses its
  buyback recipient, 6053), so the venue refuses it too.
- `Pump(Disabled)` when the disable_flags bit for this direction is set.
- `Pump(Virtual)`.
- `Layout` when the pool length is outside 211..=301, a flag byte (@243, @244, @269, @270) is neither 0 nor 1,
  GlobalConfig ≠ 949 or FeeConfig ≠ 4097.
- `Pump(UnknownTail)` when a present byte of 287..301 is set; `Pump(HeldExceedsVault)` when `held_0 + held_1 > Q`.
- `Pump(FeeTotal)`.
- `TransferFee` on either mint.

### 2.2 Raydium CPMM (`CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C`)

**State.**

| Pos | Account | Fields |
|---|---|---|
| 3 | PoolState (len **637**, disc `sha256("account:PoolState")`) | amm_config @8, token_0_vault @72, token_1_vault @104, token_0_mint @168, token_1_mint @200, status @329 (bit 2 = swap disabled), open_time u64 @373, protocol_fees_0/1 @341/@349, fund_fees_0/1 @357/@365, creator_fee_on @389 (0 both, 1 token0 only, 2 token1 only), enable_creator_fee @390, creator_fees_0/1 @397/@405 |
| 2 | AmmConfig (len **236**, key == pool @8) | trade_fee_rate @12, protocol_fee_rate @20, fund_fee_rate @28, creator_fee_rate @108 (creator_fee_share_rate @116 only splits fees at collection; not read) |
| 6, 7 | input / output vault | key ∈ {pool @72, @104}, consistent with the direction |
| 10, 11 | input / output mint | transfer-fee scan |

**Exact** (`swap_base_input` with `CurveCalculator::swap_base_input`, raydium-cp-swap `b3187ae`):

```
require (status >> 2) & 1 == 0  and  clock.unix_timestamp ≥ open_time
r0 = vault0 − (protocol0 + fund0 + creator0)   r1 = vault1 − (…1)     (checked: underflow → Abort)
(r_in, r_out) by direction; t = trade_fee_rate; c = enable_creator_fee ? creator_fee_rate : 0
on_input = creator_fee_on == 0 || (== 1 && zero_for_one) || (== 2 && !zero_for_one)
if on_input:  net = x − ⌈x·(t + c)/1e6⌉          (ONE ceil on the summed rate; src/venues/cp.rs uses two: off by ≤1)
else:         net = x − ⌈x·t/1e6⌉
gross = ⌊net·r_out / (r_in + net)⌋
out   = on_input ? gross : gross − ⌈gross·c/1e6⌉
require out > 0
```

**Model.**
- Creator fee on input: `γ = 1 − (t+c)/1e6`, `A = γ·r_out`, `B = r_in`, `C = γ`.
- Creator fee on output: `γ = 1 − t/1e6`, `A = (1 − c/1e6)·γ·r_out`, `B = r_in`, `C = γ`.

**Capacity.** None (`out < r_out` always holds).

**Abort:**
- `Cpmm(SwapDisabled)` or `Cpmm(NotOpen)`. The venue would fail too, so the fallback reverts in the venue; that is
  harmless.
- `Cpmm(OwedExceedsVault)`.
- `Cpmm(CreatorFeeOn)` when the field is > 2.
- `TransferFee`.

### 2.3 Raydium AMM v4 (`675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8`)

**State.**

| Pos | Account | Fields |
|---|---|---|
| 1 | AmmInfo (len **752**, no discriminator) | status @0, swap_fee_numerator @176, swap_fee_denominator @184, need_take_pnl_coin @192, need_take_pnl_pc @200, pool_open_time @224, coin_vault @336, pc_vault @368, coin_vault_mint @400, pc_vault_mint @432 |
| 3, 4 | coin / pc vault | key == @336 / @368; SPL Token only (the v2 instruction rejects Token-2022) |

**Exact** (`process_swap_base_in_v2`):

```
require status ∈ {1, 6}  or  (status == 7 and clock.unix_timestamp ≥ pool_open_time)
r_coin = coin_vault − need_take_pnl_coin ; r_pc = pc_vault − need_take_pnl_pc        (checked)
net = x − ⌈x·num/den⌉ ; out = ⌊r_out·net / (r_in + net)⌋ ; require 0 < out < r_out
```

**Model.** `γ = 1 − num/den`, `A = γ·r_out`, `B = r_in`, `C = γ`.

**Abort:** `Amm(Status)`, `Amm(PnlExceedsVault)`, `Amm(Fee)` (`den == 0` or `num ≥ den`).

### 2.4 Meteora DLMM (`LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo`), lb_clmm 0.12.0

**State.**

| Pos | Account | Fields |
|---|---|---|
| 0 | LbPair (len **904**, disc `210b3162b565b10d`), `#[repr(C)]` bytemuck | StaticParameters @8: base_factor u16 @8, filter_period @10, decay_period @12, reduction_factor @14, variable_fee_control u32 @16, max_volatility_accumulator u32 @20, **min/max_bin_id i32 @24/@28** (the walk's bounds), protocol_share @32, base_fee_power_factor u8 @34, **function_type u8 @35**, **collect_fee_mode u8 @36**. VariableParameters @40: volatility_accumulator u32 @40, volatility_reference u32 @44, index_reference i32 @48, last_update_timestamp i64 @56. Then pair_type @75, **active_id i32 @76**, bin_step u16 @80, status @82, activation_type @86, token_x_mint @88, token_y_mint @120, reward_infos[2] @264 (mint @264, @408), **bin_array_bitmap [u64;16] @584** (array indices −512..511, bit = index + 512), activation_point u64 @816, token flags @880/@881, version @882 |
| 6, 7 | mint x / mint y | key == @88 / @120; transfer-fee scan |
| 16 .. 16+n | bin arrays, n = 1..=5 from the descriptor (len **10,136**, disc `5c8e5cdc059446b5`) | index i64 @8, version u8 @16, lb_pair @24 (== pos 0 key), bins[70] @56, 144 B each: amount_x u64 @0, amount_y @8, **price u128 Q64.64 @16**, liquidity_supply @32, **open_order_amount @112**, total_processing_order_amount @120, **processed_order_remaining_amount @128**, order_age u32 @136, **limit_order_ask_side u8 @140** |

Mainnet on 2026-10-04 (HOTBOT pairs 6D4E, C9xc and 7hvn):
- `function_type = 2` on all three, and 13 bins in two arrays carry limit-order fields;
- C9xc has `collect_fee_mode = 1`;
- the pairs are pair_type 3, version 1, with bin arrays at version 2;
- fees are base 2-5% plus variable fees up to the 10% cap;
- no bin with liquidity has `price == 0` (0 of 700).

**Exact.** This follows SDK `quote_exact_in` (dlmm-sdk `576919e`). The deployed binary is the final oracle (§6.3).

```
pre:  status == 0. If pair_type ∈ {1 Permission, 2 CustomizablePermissionless}: point = activation_type==0 ? slot : ts;
      require point ≥ activation_point.
      update_references(ts): elapsed = ts − last_update_ts;
        if elapsed ≥ filter_period { idx_ref = active_id;
          v_ref = elapsed < decay_period ? ⌊va·reduction_factor/1e4⌋ : 0 }       (u32 arithmetic)
      support_lo = function_type == 2 || (function_type == 0 && both reward mints == 0)   (1 → false; other → Abort)
      fee_on_input = collect_fee_mode == 0 ? true : collect_fee_mode == 1 ? !swap_for_y : Abort
      base = base_factor · bin_step · 10 · 10^power
walk: arr = next array WITH LIQUIDITY (bitmap) in the swap direction starting at index(active)  [index = ⌊id/70⌋]
        – none inside ±512 (extension bitmap needed) → CAP here
        – arr not among the passed arrays → CAP here
      if arr ≠ index(active): active = swap_for_y ? arr·70 + 69 : arr·70          (shift_active_bin_if_empty_gap)
      for bins in arr from active, stepping −1 (X→Y) / +1 (Y→X), while left > 0:
        max_out = mm_out + (support_lo ? lo_open + lo_processed : 0)
             mm_out = swap_for_y ? amount_y : amount_x
             (lo_open, lo_processed) = (swap_for_y && ask==0) || (!swap_for_y && ask!=0) ? (@112, @128) : (0, 0)
        if max_out > 0:
          va   = min(v_ref + |idx_ref − active|·1e4, max_va)
          rate = min(base + ⌈vfc·(va·bin_step)²/1e11⌉ , 1e8)                         (out of 1e9)
          (used, out) = bin_quote(left)        ── below
          left −= used ; total_out += out
        if left > 0: active += dir (require the pair's min_bin_id ≤ active ≤ max_bin_id, else 6012
                     PairInsufficientLiquidity → CAP; the SDK's ±443,636 is wrong here, REVIEW.md F8)
      repeat with the next array.
bin_quote(in):
  excl = fee_on_input ? in − ⌈in·rate/1e9⌉ : in
  fill layers [mm_out, lo_processed, lo_open] in this order with `rem = excl`, each layer L > 0 while rem > 0
  (a layer's get_amount_in is computed only once the swap reaches it with input left):
      need = get_amount_in(L)   (X→Y: ⌈L·2^64/P⌉ ; Y→X: ⌈L·P/2^64⌉ ; must fit u64, else the program errors → CAP)
      if rem ≥ need { out += L ; rem −= need }                        (drained: ≥, per SDK 0.12; same user outcome as
                                                                       the older `>` test, §2.7)
      else { out += get_amount_out(rem) (X→Y: ⌊rem·P/2^64⌋ ; Y→X: ⌊rem·2^64/P⌋) ; rem = 0 ; break }
  if rem > 0 (bin drained): excl −= rem ; used = fee_on_input ? excl + ⌈excl·rate/(1e9 − rate)⌉ : excl
  else used = in
  out_user = fee_on_input ? out : out − ⌈out·rate/1e9⌉
```

`P` is the bin's stored price at @16. A bin with liquidity and `P == 0` gives `Abort::Dlmm(ZeroPrice)` (never
observed). `x·P` uses the split 64×128-bit multiply (as `src/venues/dlmm.rs::mul_shr`, exact). `x·2^64/P` is
u128 / u128 (x < 2^64).

**Model.** Each bin with liquidity is one linear segment.
- Slope: `s = (1 − rate/1e9)·P/2^64` for X→Y, `(1 − rate/1e9)·2^64/P` for Y→X. This holds for both fee modes,
  because fee on input and fee on output have the same real-valued slope.
- Input to drain: `D = (Σ layers)·(2^64/P or P/2^64) / (1 − rate/1e9)`.
- Price worsens monotonically along the walk. The rate is not monotone: it falls while the walk moves toward
  `idx_ref` (§3.4 guards this).

**Drained bins and resumable states.** A bin drained whole takes exactly `D = ⌈S·1e9/(1e9 − r)⌉` (fee on output:
`D = S`), `S = Σ⌈get_amount_in(layer)⌉`, and the drained path is taken exactly for inputs `≥ D' = ⌈(S+1)·1e9/(1e9 − r)⌉`
(fee on output: `S + 1`); an input in `[D, D')` is used whole and still empties the bin. So the swap state after `k`
drained bins (`used = ΣD`, `out`, `reach = used_{k−1} + D'_{k−1}`, the walker's position) is a **cursor**: the exact
quote of any `x ≥ reach` resumes from it and equals the quote from the active bin. The locator walks the bins once
with these exact amounts and hands the cursors near its optima to the planner (§3.4).

**Walk budget.** Each DLMM leg's descriptor carries `max_bins` (§4.3): the bins a walk may read (empty bins inside a
visited array included). Past it the evaluator answers `QuoteErr::Budget` — "not evaluated", the venue would still
fill — never TooLarge, and the planner treats `E(e) = Budget` as unknown (§3.5). The passed arrays bound every walk
(≤ 5 × 70 bins) whatever the budget.

**Capacity.** Exact within the budget: `reach − 1` of the state after the last bin before the first CAP condition
(end of the passed arrays, a missing array, an extension-bitmap region, the pair's bin-id bounds, a u64 overflow).

**The venue's CU.** The real program needs ≈5.45k CU per bin crossed: in the harness its swaps run out of the 1.4M
transaction limit from about 246 bins read (the largest successful swap read 256). The engine's
`max_bins` and CU limit keep sized routes well below that (§4.7).

**Abort:** `Dlmm(Status)`, `Dlmm(NotActive)`, `Dlmm(FunctionType)`, `Dlmm(CollectFeeMode)`, `Layout` (pair
version ∉ {1} or bin-array version ∉ {2} until the harness has seen others), `Dlmm(ZeroPrice)`, `TransferFee`.
`max_bins = 0` is a DescError (`BinBudget`).

### 2.5 Meteora DAMM v2 (`cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG`)

**State.**

| Pos | Account | Fields |
|---|---|---|
| 1 | Pool (len **1,112**, disc `f19a6d0411b16dbc`) | The full table is in `src/venues/dammv2.rs::off`. BaseFeeInfo @8 (cliff u64 @8, mode u8 @16, scheduler fields @22..40), protocol_fee_percent @48, compounding_fee_bps @54, DynamicFeeStruct @56 (initialized @56, max_va @64, vfc @68, bin_step @72, filter/decay/reduction @74/76/78, last_update_ts @80, bin_step_u128 @88, sqrt_price_reference @104, volatility_accumulator u128 @120, volatility_reference @136), init_sqrt_price @152, liquidity u128 @360, sqrt_min_price @424, sqrt_max_price @440, sqrt_price @456, activation_point @472, activation_type @480, pool_status @481, token flags @482/@483, collect_fee_mode @484, fee_version @486, token_a_amount @680, token_b_amount @688, layout_version @696 |
| 6, 7 | mint a / mint b | transfer-fee scan when a flag is 1 (Token-2022) |

The vaults are not read: a concentrated pool prices off `liquidity` and `sqrt_price` alone, and a compounding pool off
its tracked amounts.

**Exact.** This is exactly `src/venues/dammv2.rs::swap_exact_in`. It was ported from damm-v2 `a85c926` and is proven
on chain: every vector in `testdata/dammv2-vectors.json` ("chain") is a real swap whose output and whole post-state
match. The crate takes that code as is, with the `String`/`Vec` and std parts removed. In short:
- prepare: status, activation, layout migration, and `update_references` with the Clock's unix time;
- fee numerator = `min(base(scheduler, Clock point) + variable(STORED volatility_accumulator), max(fee_version))`;
- the fee is on the input only for (OnlyB or Compounding) and b→a, otherwise on the output; both are `⌈·fee/1e9⌉`;
- concentrated a→b: `next = ⌈L·P/(L + in·P)⌉`, `out = delta_b(next, P, L, down)`;
- concentrated b→a: `next = P + ⌊(in << 128)/L⌋`, `out = delta_a(P, next, L, down)`;
- compounding: `out = ⌊r_out·in/(r_in + in)⌋`;
- **range exit** (`next < sqrt_min` or `next > sqrt_max`) is `PriceRangeViolation` on chain, which the evaluator
  reports as TooLarge.

**Model.** Inside the range a concentrated pool is a CPMM on virtual reserves `R_a = L/P` and `R_b = L·P/2^128`,
with `P` the Q64.64 integer. Verified: for C8jd, `L/P = 3.6925e13` and `L·P/2^128 = 7.327e9`, against tracked
amounts of 36,924,456,550,153 and 7,327,028,884.
- Fee on output: `A = (1 − f)·R_out`, `B = R_in`, `C = 1`.
- Fee on input: `A = (1 − f)·R_out`, `B = R_in`, `C = 1 − f`.
- Compounding pools: the same, with `R` = tracked amounts.

**Capacity (exact, closed form).**
- a→b: `n_max = ⌈L·(P − Pmin + 1)/((Pmin − 1)·P)⌉ − 1`. This is the largest net input with
  `⌈L·P/(L + n·P)⌉ ≥ Pmin`, computed in U256.
- b→a: `n_max = ⌈(Pmax − P + 1)·L/2^128⌉ − 1`.
- With a fee on input, the gross cap is `x_max = ⌈(n_max + 1)·1e9/(1e9 − f)⌉ − 1`, because
  `x − ⌈x·f/1e9⌉ = ⌊x·(1e9 − f)/1e9⌋`.
- Compounding pools have no range, so no capacity.
- All three closed forms were checked against the swap's own next-price formulas on 60,000 random cases, with 0
  failures (`research/math_checks.py`).

**Abort:**
- `Damm(Status)`, `Damm(NotActive)`.
- `Damm(RateLimiter)` when the base-fee mode is 2 and the limiter is in force for this direction (b→a) and time.
  The program then runs its single-swap validation, which needs the instructions sysvar as the first remaining
  account; the engine's 14-account leg does not pass it, so the venue fails (6049 FailToValidateSingleSwapInstruction)
  at **every** size (REVIEW.md F5, 84 harness rows). `dammv2::parse` therefore refuses the leg, with or without SEARCH;
  `parse_with_limiter` still prices the limiter's amount-dependent fee exactly for off-chain use. Supporting it would
  need the sysvar in the leg and a descriptor position for it.
- `Damm(Mode)` for an unknown base-fee mode, collect-fee mode or layout version.
- `Damm(Fee100)`.
- `TransferFee`.
- The whitelisted vault's pre-activation window is not modeled. Activation is required.

### 2.6 What happens when the model refuses

There are three classes of failure, and they are handled differently.

| Class | Examples | Action | Why |
|---|---|---|---|
| **DescError** (engine bug) | wrong kind for the leg's program id; position out of range; owner or discriminator mismatch on a state account (an unknown length or version with the right discriminator is `Abort::Layout`, not a DescError); vault, config, mint or bin-array key not equal to the key stored in the pool; input mint not matching the direction; the same pool in both legs of a pair; bad pair indexes; `min_size > e` or `e > amount_in` | **always revert**: `ERR_SIZING_DESC` | Executing a route the program cannot describe consistently hides engine bugs. The cost is a free bundle revert |
| **Abort** (state not modeled) | everything listed under "abort" in §2.1-§2.5; `Abort::Math` (checked overflow) | **fall back**: execute pair 0 at `e`, log AXZ1 with the reason. With STRICT, revert `ERR_SIZING_UNSUPPORTED` | The fallback is exactly today's behaviour, and the guard protects it. Sizing can then never make a route worse than sizing off. STRICT exists for experiments that want clean statistics |
| **Infeasible / unprofitable** | no size in `[min_size, x_max]` (capacity below `min_size`, or `π'(0) ≤ 0`); best exact profit below `min_profit` | default: execute the best feasible candidate, or `e` if none, and let the guard decide. With **EARLY_ABORT**: revert `ERR_SIZING_NO_PROFIT` before any CPI, or return `Ok` with no CPI under NOOP_ON_MISS | When the model is exact, EARLY_ABORT gives the guard's own verdict about 100k CU sooner. It is off until §6.6 has shown exactness |

In BASKET a pair whose leg aborts is dropped. When pair 0 itself aborts, `E(e)` is unknown, so `e` stays the fallback:
another pair executes only if its modeled profit clears `min_profit` (net of tip and lamport offset); otherwise the
plan is Fallback (pair 0 at `e`, the abort's reason), never NoProfit, so EARLY_ABORT cannot revert a route `e` might
have landed. SELF_SIZE with an abort falls back the same way (REVIEW.md F7).

### 2.7 Where the engine's reference maths (`src/venues`) differs from the venue programs

These differences matter for the differential tests (§6.2) and are also engine bugs worth fixing. **Fixed in the
engine by PLAN-ADDENDUM WP-16:** the engine now quotes with this crate (`src/quote.rs`, §5.5); its old maths is kept,
tests only, in `src/venues/legacy` as the differential reference, and `src/quote/tests.rs` measures these differences
against real swaps on the venue binaries (testdata/venue-parity): the crate exact on all 1,252 it quotes, the old maths
off on PumpSwap buys (all above the program, ≤ 59 ppm), CPMM creator fees on the input (≤ one input unit's worth) and
DLMM limit-order and fee-on-output pairs (41 of 216, 34 of them above the program, up to 1.2%).

1. **PumpSwap buy_exact_quote_in** (`cp.rs` Fee::Pump buy). It is missing the
   `eff −= max(0, eff0 + fees(eff0) − x)` adjustment and the `−1` in `⌊B·(eff−1)/(Qv+eff−1)⌋`, so it overestimates
   the base out slightly. It also reads the virtual reserve as i64 @245, but the field is i128 (equal while
   `|V| < 2^63`).
2. **PumpSwap pool flags.** `cp.rs:112` refuses `p[270] == 1` as "holder reward". Byte 270 is `is_holder_reward:
   bool` (pump-public-docs `idl/pump_amm.json`, 2026-09-12), 0 or 1 on every live pool (the WP-16 review's census: 355
   and 34), and holder rewards change no trade amount: the refusal is needless and dropped 34 tradable pools. (The
   "nonzero counters 0x97, 0xba" read here earlier were not byte 270: no live pool holds anything but 0 or 1 there, and a
   Borsh bool cannot.) The crate accepts 0 and 1 and refuses any other byte as `Layout` (§2.1). The old engine also read
   only pools of ≥ 253 bytes and the crate, until the WP-16 review, only 301-byte ones: both now read every length the
   program reads.
3. **Raydium CPMM**, creator fee on input: the engine takes two ceils, the program one (an error of at most 1 unit).
   The engine does not check `open_time` either.
4. **DLMM.**
   - Limit-order layers are ignored, so the engine underestimates bin capacity. On a pending swap that consumes limit
     orders it then predicts too large a price move.
   - `collect_fee_mode = 1` is ignored (rounding only).
   - The drain test is `≥ max_in + max_fee` (the old model). SDK 0.12 tests `in − ⌈in·r/1e9⌉ ≥ max_in`. A brute
     force over 1.2M cases, including every threshold ±2, found the two **identical**. The older program's strict
     `>` differs only at equality, and there its partial path also pays out the whole bin, so the user outcome is the
     same.
   - The bitmap jump to the next array with liquidity is not modeled. The engine stops at a missing array instead.
5. **DAMM v2.** None found.

### 2.8 Raydium CLMM (`CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK`), raydium-clmm ed1eb41

PLAN-ADDENDUM WP-21, feature `rayclmm` (`src/venue/raydium_clmm.rs`). The deployed program is raydium-io/raydium-clmm at
ed1eb41 (2026-09-29; programdata last deployed at slot 451,479,902; the dump's sha256 starts `e6963f72991821e2`,
`fixtures/programs/MANIFEST.json`), built with `overflow-checks = true`: an overflow panics, so the port's checked
arithmetic fails exactly where the program does.

**State.** Positions are in the `swap_v2` leg (§9.1).

| Pos | Account | Fields |
|---|---|---|
| 2 | PoolState (owner CAMM, len **1,544**, disc `f7ede3f5d7c3de46`) | amm_config @9, token_mint_0 @73, token_mint_1 @105, token_vault_0 @137, token_vault_1 @169, observation_key @201, tick_spacing u16 @235, liquidity u128 @237, sqrt_price_x64 u128 @253, tick_current i32 @269, fee_growth_global_0/1 u128 @277/@293, protocol_fees_token_0/1 u64 @309/@317, **status u8 @389** (bit 4: swaps disabled), **fee_on u8 @390** (1: the fee in token 0, 2: in token 1, any other value: on the input), **tick_array_bitmap [u64;16] @904** (the default range: arrays −512..511, bit = array index + 512), fund_fees_token_0/1 u64 @1064/@1072, **open_time u64 @1080**, **DynamicFeeInfo @1096** (80 B: filter_period u16 @+0, decay_period @+2, reduction_factor @+4, dynamic_fee_control u32 @+6, max_volatility_accumulator u32 @+10, tick_spacing_index_reference i32 @+14, volatility_reference u32 @+18, volatility_accumulator u32 @+22, last_update_timestamp u64 @+26; all 80 bytes zero = no dynamic fee) |
| 1 | AmmConfig (len **117**, disc `daf42168cbcb2b6f`, key == pool @9) | protocol_fee_rate u32 @43, trade_fee_rate u32 @47, fund_fee_rate u32 @53 (out of 1e6) |
| 5, 6 | input / output vault | key == the pool's vault of the direction; amount @64 (the output vault bounds the payout) |
| 11, 12 | input / output mint | key == the pool's mint of the direction; Token-2022 scan (§2.0) |
| 13 .. 13+n | the remaining accounts, n = 1..=7 (descriptor) | classified by length as the program does, each owned by CAMM with its discriminator and naming this pool (pool_id @8; else DescError): the **TickArrayBitmapExtension** PDA["pool_tick_array_bitmap_extension", pool] (len **1,832**, disc `3c9624db61808b99`: 14 positive bitmaps of 512 bits @40, 14 negative @936) and **TickArrayState** PDA["tick_array", pool, start as i32 big-endian] (len **10,240**, disc `c09b55cd31f9812a`: start_tick_index i32 @40, ticks[60] @44 of 168 B — tick i32 @0, liquidity_net i128 @4, liquidity_gross u128 @20, order_phase u64 @116, orders_amount u64 @124, part_filled_orders_remaining u64 @132, unfilled_ratio_x64 u128 @140 — initialized_tick_count u8 @10,124). An account of any other length ends the list: the program stops reading there |

Real pools carry **limit orders** on ticks (3ucN SOL/USDC: 7 ticks, 2uoK: 1 on 2026-10-06); the walk fills them.

**Exact.** The program's `swap_internal` and its callees, step for step and rounding for rounding:

```
pre:  status bit 4 clear; Clock.unix_timestamp > open_time; tick_spacing ≠ 0; trade_fee_rate ≤ 1e6;
      the default price limit (MIN_SQRT+1 for 0→1, MAX_SQRT−1 for 1→0) strictly beyond the pool's price
      fee side: fee_on 1 → token 0 (on the input of 0→1, on the output of 1→0); 2 → token 1; else the input
      dynamic fee (DynamicFeeInfo not all zero): update_reference(ts): elapsed = ts − last_update;
        < filter: nothing; < decay: idx_ref = ⌊tick/ts⌋, v_ref = ⌊va·reduction/1e4⌋; else idx_ref = ⌊tick/ts⌋, v_ref = 0
first array: the current tick's array when initialized (the default bitmap, or the extension beyond ±ts·60·512 ticks:
      needed for tick spacings below 15), else the next initialized one in the swap direction; it must be passed
loop while remaining > 0 and price ≠ limit:                                    (one OUTER iteration per tick)
  next tick: the next initialized tick (liquidity or resting orders) of the current array; else the first one of the
      next initialized array (bitmap jump, through the extension past the default range), which must be the next
      passed array (the program consumes the passed arrays front to back)
  inner step: to the next tick's price, or under the dynamic fee to the tick-spacing boundary while va < max_va:
      va = min(v_ref + |idx_ref − ts_index|·1e4, max_va); rate = min(trade + ⌈control·(va·ts)²/1e13⌉, 1e5)
      compute_swap: fee on the input: net = ⌊x·(1e6−r)/1e6⌋, fee = ⌈in·r/(1e6−r)⌉ (target reached) or x − in;
        fee on the output: fee = ⌈out·r/1e6⌉ out of the output; amounts between sqrt prices over 256/512-bit
        products (U256/U512 mul-div, ruint semantics), the input rounded up and the output down
      fees: protocol ⌊fee·p/1e6⌋, fund ⌊fee·f/1e6⌋, the rest into fee growth ⌊rest·2^64/L⌋ (wrapping)
  on the tick: its limit orders fill first at the tick's price (the output with the swap's direction rounded down, the
      input with the ORDER's direction, the opposite, rounded up; the part-filled cohort first), and the tick is
      crossed (L ∓ liquidity_net) only once none is left; tick_current = the tick (− 1 after a downward crossing;
      while orders remain on it, on the side the swap came from)
post: the amount met in full (swap_v2 without a price limit: a partial fill fails); in > 0 and out > 0
      (else TooSmallInputOrOutputAmount: ZeroOut); out ≤ the output vault; the owed fees' checked additions
```

Exact out (`is_base_input = 0`) runs the same loop on the output (`quote_exact_out`): the engine's hints.

**Model.** One piece per exact swap step. Within a step the liquidity and the fee rate are constant, so the step is a
CPMM on its virtual reserves `X = L·2^64/P` (token 0) and `Y = L·P/2^64` (token 1): `A = (1 − f)·R_out`, `B = R_in`,
`C = 1 − f` with the fee on the input, `C = 1` on the output (§2.5's model). Each piece starts and ends at the step's
EXACT cumulative input and output (`Steps`, from the same walker as the exact quote), so the model's error does not
accumulate along the walk. A limit-order fill is a line at the tick's price. The bound for the non-concavity guard
after a step is the marginal price at its end net of the trade fee (the dynamic part is never negative).

**Walk budget.** The descriptor's `max_bins` counts **swap steps** (inner steps: ranges, tick crossings, dynamic-fee
sub-steps, limit-order fills). `RayClmmLeg::steps_for(x)` gives the steps of `x`, for the engine's `max_bins` rule
(§4.3). Past the budget a quote is `Budget` (not evaluated), as for DLMM.

**Capacity.** The swap fills every smaller input once it fills a larger one, so `cap_in` bisects the exact quote (host
only). A walk ends (TooLarge) where the program fails: the passed tick arrays end, no initialized array is left in the
direction, the extension is needed and not passed (also when an array's last tick is crossed beyond the default
range: the program flips its bit in the extension), an amount passes u64, or the output vault is too small.

**Abort** (each fails `swap_v2` at every size; the harness checks every refusal against the venue): `Clmm(Status)`,
`Clmm(NotOpen)`, `Clmm(Fee)` (trade fee rate above 1e6), `Clmm(BitmapExtension)` (the current tick beyond the default
range, the extension not passed), `Clmm(NoLiquidity)` (no initialized array in the direction), `Clmm(TickArrays)` (the
first array not passed), `Clmm(PriceLimit)`, `Clmm(State)` (tick spacing 0, the current tick outside the range, a
bitmap the program cannot read), `Clmm(MintPaused)`, `Clmm(MintFrozen)`, `TransferFee`, `TransferHook`, `Layout` (any
other length of the pool or the config).

**The venue's CU** (the deployed binary in LiteSVM, every exact harness swap: §6.3): ≈41.5k + ≈9.1k per tick crossed
+ ≈8.5k per other step (a dynamic-fee sub-step, a limit-order fill). Every swap is within **64k + 10k per step**. The
1.4M transaction limit falls at ≈147 steps (the largest swap that fit: 147 steps, 1,392,658 CU); a dynamic-fee pool far
from its reference reaches 478-774k with no crossing at all (51-87 sub-steps).

### 2.9 Orca Whirlpool (`whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc`), whirlpool 0.9.0

PLAN-ADDENDUM WP-21, feature `whirlpool` (`src/venue/orca_whirlpool.rs`). The deployed program is orca-so/whirlpools at
0e72771 (program 0.9.0; programdata last deployed at slot 440,170,207, 2026-08-19; sha256 `4b5cb126a352f68d…`), built
with **`overflow-checks = false`**: its plain `+ − *` wrap and only its `checked_*` calls and index bounds fail. The port
keeps that (wrapping operations where the program has plain ones). Its own U256 division (`U256Muldiv::div`, Knuth D) is
ported as deployed, including the add-back on the top word that reads out of bounds — the binary panics there, and so
does the port (`None`, TooLarge); upstream fixed it after this deploy (4aac511, 2026-10-06, §7 item 12).

**State.**

| Pos | Account | Fields |
|---|---|---|
| 4 | Whirlpool (owner whirL, len **653**, disc `3f95d10ce1806309`) | tick_spacing u16 @41, fee_tier_index_seed @43, fee_rate u16 @45 (out of 1e6), protocol_fee_rate u16 @47 (out of 1e4), liquidity u128 @49, sqrt_price u128 @65, tick_current_index i32 @81, protocol_fee_owed_a/b u64 @85/@93, token_mint_a @101, token_vault_a @133, fee_growth_global_a u128 @165, token_mint_b @181, token_vault_b @213, fee_growth_global_b @245, **reward_last_updated_timestamp u64 @261** |
| 5, 6 | mint a / mint b | key == @101 / @181; Token-2022 scan (§2.0) |
| 8, 10 | vault a / vault b | key == @133 / @213; amount @64 |
| 11, 12, 13 (+ 15.. supplemental, 0..=3) | tick arrays PDA["tick_array", whirlpool, start as a decimal string] | **fixed** TickArray (len **9,988**, disc `4561bdbe6e0742bb`: start_tick_index i32 @8, ticks[88] @12 of 113 B — initialized u8 @0, liquidity_net i128 @1, liquidity_gross u128 @17 — whirlpool @9,956) or **dynamic** DynamicTickArray (len **148..=10,004**, disc `11d8f68ee1c7da38`: start @8, whirlpool @12, tick_bitmap u128 @44, the ticks from @60, each a Borsh enum: 0 = uninitialized (1 byte) or 1 + 112 bytes; bytes past the account's end read as zero), or the PDA of an array that does not exist (System-owned, empty), which the program reads as **zeroed** when it is the PDA of a start index the swap needs |
| 14 | Oracle PDA["oracle", whirlpool] (len **254**, disc `8bc283b38cb3e5f4`, whirlpool @8), or uninitialized (System, empty: no adaptive fee) | trade_enable_timestamp u64 @40; AdaptiveFeeConstants @48: filter_period u16, decay_period u16, reduction_factor u16, adaptive_fee_control_factor u32, max_volatility_accumulator u32, tick_group_size u16, major_swap_threshold_ticks u16; AdaptiveFeeVariables @82: last_reference_update_timestamp u64, last_major_swap_timestamp u64, volatility_reference u32, tick_group_index_reference i32, volatility_accumulator u32 |

**Exact.** `swap_manager::swap` (0e72771), step for step:

```
pre:  tick_spacing ≠ 0; the default limit (MIN_SQRT_PRICE for a→b, MAX_SQRT_PRICE) strictly beyond the price;
      Clock ≥ reward_last_updated_timestamp (else InvalidTimestamp at every size)
      oracle initialized → trade_enable_timestamp ≤ Clock, and the adaptive fee (FeeRateManager::Adaptive):
        group = ⌊tick/tick_group_size⌋; update_reference(group, ts): ts ≥ max(last_reference_update, last_major_swap)
        (else InvalidTimestamp); ts − last_reference_update > 3,600 → reset (idx_ref = group, v_ref = 0); else by
        elapsed = ts − max(…): < filter: nothing; < decay: v_ref = ⌊va·reduction/1e4⌋; else v_ref = 0
        core range: idx_ref ± ⌈(max_va − v_ref)/1e4⌉ groups (outside it va is at its maximum: no sub-steps)
sequence (SparseSwapTickSequenceBuilder): the start indexes the swap needs — the current tick's array and the next two
      in the direction (b→a starts one array later when the tick is within one tick spacing of its array's end);
      each from an initialized passed array (static or supplemental, any order), else from a passed uninitialized
      PDA of that start index (zeroed), else the sequence stops there; an empty sequence fails every size
loop while remaining > 0 and price ≠ limit:
  next tick: the next initialized tick along the sequence (at its end: the sequence's last tick, or MIN/MAX tick)
  inner step: to that tick's price, bounded at the tick-group boundary inside the core range (adaptive):
      va = min(v_ref + |idx_ref − group|·1e4, max_va); rate = min(fee_rate + ⌈control·(va·tgs)²/1e13⌉, 1e5)
      compute_swap: the fee always on the input: net = ⌊x·(1e6−r)/1e6⌋; fee = ⌈in·r/(1e6−r)⌉ (target reached) or
        remaining − in; amounts over the program's U256Muldiv as deployed (in up, out down)
      fees: protocol ⌊fee·p/1e4⌋ (wrapping), fee growth += ⌊rest·2^64/L⌋ (wrapping)
  on an initialized tick: L ∓ liquidity_net (checked); tick_current = tick (− 1 for a→b)
post: exact out must fill in full (PartialFillError); out > 0; out ≤ the output vault; the oracle's major-swap stamp
      when the price moved past major_swap_threshold_ticks
```

**Model, walk budget, capacity.** As §2.8 (the fee on the input: `C = 1 − f`). The sequence bounds any swap to 3 tick
arrays (≤ 264 tick spacings) whatever the input.

**Abort** (each fails `swap_v2` at every size; checked against the venue): `Whirl(TradeNotEnabled)`, `Whirl(Timestamp)`
(the Clock before the reward update, or before the oracle's reference / major-swap stamps), `Whirl(TickArrays)` (none of
the needed arrays passed), `Whirl(PriceLimit)`, `Whirl(State)` (tick spacing or tick group size 0, a core-range bound
outside the tick range), `Whirl(MintPaused)`, `Whirl(MintFrozen)`, `TransferFee`, `TransferHook`, `Layout` (the pool or
the oracle at another length).

**The venue's CU** (LiteSVM, every exact harness swap): ≈28-30k + ≈7.0k per tick crossed + ≈8.6k per other step (an
adaptive-fee sub-step). Every swap is within **48k + 10k per step**. The 1.4M limit falls at ≈190 steps (the largest
swap that fit: 183 steps, 1,347,253 CU; the smallest that ran out: 232 steps); an adaptive pool 100 groups from its
reference takes 153 sub-steps (1.27M) with no crossing at all.

---

## 3. The optimizer

### 3.1 Problem

For a pair `(L0, L1)` the profit in quote units is `π(x) = out1(out0(x)) − spent0(x)`, for `x ∈ [min_size, x_max]`,
where:
- `x_max = min(amount_in, quote_balance, cap0, out0⁻¹(cap1))`;
- `spent0 = x` for every kind except PumpSwap buy_exact_quote_in, which debits `min(x, eff0 + fees(eff0))` (one unit
  less than `x` for about 1 size in 1,800, §2.1). The planner's profit is the sell output minus that debit, which is
  the guard's quote delta (REVIEW.md F2).

Each leg is non-decreasing in its input. In the real-valued model (§2) each leg is also concave:
- a Möbius curve is concave;
- the DLMM slopes `s_k` fall as the walk goes on, except where the fee drops faster than the price moves (handled in
  §3.4).

The composition of a concave non-decreasing `L1` with a concave `L0` is concave, so `π` is concave and its maximiser
is where `π'` crosses 0.

The exact integer profit is `πZ(x) = πR(x) + η(x)`, where `|η| ≤ ε` collects the venues' floors and ceils:

`ε ≤ 3 + 2·p1 + p0·p1` quote units.

Here `p0` is the leg-0 marginal (X per A) and `p1` the leg-1 marginal (A per X). At an optimum `p0·p1 ≈ 1`, so
`ε ≈ 4 + 2·p1`. For memecoins `p1 ≪ 1` (one raw unit of X is worth far less than a lamport), giving `ε ≈ 4` lamports.

### 3.2 Leg models

- **Möbius.** `M(u) = A·u/(B + C·u)` with `A, B, C > 0`. Then `M'(u) = A·B/(B + C·u)²` and the inverse is
  `M⁻¹(v) = B·v/(A − C·v)` for `v < A/C`.
- **Bins.** A sequence of segments `k`, each with a starting input `U_k`, an output `V_k` and a slope `s_k` over
  `[U_k, U_{k+1})`. They come from the same walker as the exact DLMM evaluator (same bitmap jumps, same CAP
  conditions), in the approximate arithmetic of §3.8.

### 3.3 CPMM family ↔ CPMM family: closed form

Two Möbius legs compose into one Möbius curve:

```
z(x) = A·x / (B + C·x),   A = A0·A1,   B = B0·B1,   C = C0·B1 + C1·A0
π'(x) = A·B/(B + C·x)² − 1
x*   = (√(A·B) − B) / C          if A > B   (round-trip marginal rate at 0 above 1), else no trade
π(x*) = (√A − √B)² / C
```

The square root is taken in the approximate arithmetic of §3.8, about 40 CU. Feasibility is then imposed by clamping:
`x* ← clamp(x*, min_size, x_max)`.

**Integer correction.**
1. `x̂ = ⌊x*⌋`, clamped, is evaluated exactly.
2. If the exact evaluation fails only because of a capacity edge (PumpSwap sell real-reserve check, DAMM range, a
   DLMM walk's end), step back to the last feasible size: gallop down from `x̂ − 2^-24·x̂` (×4 per try, ≤ 8 tries),
   then bisect the last gap down to that step (≤ 8), at most `MAX_BACK = 8` step-back evaluations per plan (REVIEW.md
   F14). Exact closed-form caps (§2.1, §2.5) make this rare.
3. No neighbourhood search. Near `x*`, `πR` is flat (`πR(x*) − πR(x* ± d) = ½·|πR''|·d²`), and `πZ` differs from
   `πR` by at most `ε`. So `πZ(x̂) ≥ max πZ − 2ε − ½·|πR''|`, and a probe of `x̂ ± 1` can gain at most `2ε` (a few
   lamports) for about 2k CU. The `PROBE` build flag (off) does that probe for the harness's statistics.

   Checked by brute force (`research/math_checks.py`): on 285 random profitable AMM-v4-like pairs the best integer
   size beats `⌊x*⌋` by at most 0.31 × `2ε`. The worst case was 64 units, on a pair where one unit of X was worth
   about 100 units of A.

### 3.4 Mixes with DLMM, DAMM v2 or CLMM legs: the marginal walk

The search walks breakpoints in `x`:
- leg 0's own segment ends (`U_k`) if it is piecewise;
- leg 1's segment ends mapped back into `x`: `x = out0⁻¹(V_j)`, using `M⁻¹` for a Möbius leg 0, or
  `U_k + (V_j − V_k)/s_k` inside leg 0's segment `k`;
- the cap.

Between two breakpoints each leg is a single Möbius curve or a single line, so `π'` has a closed-form root:

| Leg 0 on the interval | Leg 1 on the interval | Interior root |
|---|---|---|
| line `s0` (from `(x_k, y_k)`) | Möbius `(A1,B1,C1)` | `y* = (√(s0·A1·B1) − B1)/C1`, `x* = x_k + (y* − y_k)/s0` |
| Möbius `(A0,B0,C0)` | line `s1` | `x* = (√(s1·A0·B0) − B0)/C0` |
| line `s0` | line `s1` | none: `π' = s0·s1 − 1` is constant. If > 0, move to the next breakpoint; otherwise the optimum is the interval start |
| Möbius | Möbius | §3.3 |

The walk itself:

```
x ← 0 ; optima ← []                       (at most 3 kept, best model profit first)
for step in 0..MAX_STEPS:                 (MAX_STEPS = 2 × 350 + 4: every step ends a piece of one leg, and a leg
                                           has ≤ max_bins pieces (≤ 350 in 5 arrays): the bound is per leg and never
                                           cuts a walk short; REVIEW.md F3. A DLMM leg's domain ends at its budget,
                                           like a missing bin array)
    x_next ← min(next breakpoint after x, x_max)
    if π'(x+) > 1:                        (π'(x+) = leg-1 marginal at out0(x) × leg-0 marginal at x)
        if π'(x_next−) > 1: still rising   (no root inside: the root formula is skipped, which saves ~1.4k CU/bin)
        else r ← interior root on (x, x_next) from the table (none for line × line); push(r)
        elif x_next == x_max: push(x_max)
    else:
        push(x)                           (π' is already ≤ 1 where this interval starts)
    if an optimum is known, not rising, and not MAY_RISE(x_next): stop   (checked on EVERY step, not only on the
                                           step that pushed: the bound only falls along the walk; REVIEW.md F6)
    if x_next == x_max: stop
    x ← x_next ; advance every leg segment that ends at x_next
```

**Why the walk is right and why it stops.**
- Correctness: when `πR` is concave, `π'` is non-increasing in `x`. It is continuous inside an interval and only
  jumps down at a breakpoint, where a bin ends. The first point where `π'` falls to 1 is therefore the global
  maximiser. That point is either an interior root or the start of the first interval with `π'(x+) ≤ 1`. The walk
  visits intervals in increasing `x` and records exactly that point.
- Termination: every step either stops or moves `x` to a later breakpoint of a finite list. That list holds at most
  `max_bins` pieces per DLMM leg (≤ 350 in its 5 passed arrays), one per Möbius leg, plus the cap. So the walk ends in
  at most `MAX_STEPS = 704` steps, with no tolerance parameter, and the bound never binds before the legs' own ends.

**Non-concavity guard.** A DLMM leg's slope can rise along the walk when the walk moves toward `idx_ref` and the fee
falls by more than one bin step of price. With the current parameters it does not: on 6D4E the fee changes by at most
0.23% per bin against a 1% bin step. Parameters can change, though. So after the first local optimum the walk
continues only while an upper bound on any later marginal still exceeds 1. That bound is `MAY_RISE(x)`. It uses the
best remaining price, the minimum possible rate (`base + var(v_ref)`) and the other leg's marginal at the current
point, which only falls. For Möbius-only pairs `MAY_RISE` is always false. Every local optimum found is a candidate,
at most 3, kept in order of model profit.

**One walk, exact.** A DLMM stream reads each bin once and builds its line from the bin's EXACT drain amounts (§2.4),
so `U_k`, `V_k` are the integer cumulative input and output, converted to `Fx`. The exact swap state at the start of
the piece holding each optimum (positioned at that bin), the one before it, and the walk's furthest state are
recorded; the planner resumes every exact quote from the furthest recorded state the amount reaches (§3.5), so a
candidate costs one or two bins instead of a walk from the active bin. The guard's bound per bin is computed only when
the guard runs, `out1(y)` only where an optimum is recorded.

**Cost (measured, §4.7).** ≈1.85k CU per bin the walk reads (the walk ≈0.35k, the exact drain ≈0.6k, the model
≈0.9k); a candidate's exact evaluation ≈1.5k plus ≈1k per bin it reads. A typical arb ends in the active bin or one of
the next two, so 1-3 bins. One DLMM bin is a 0.2-1% price step, against arb gaps of tens of bps.

**CLMM legs (kinds 7 and 8, WP-21).** A CLMM leg streams its exact swap of an unbounded input step by step
(`raydium_clmm::Steps`, `orca_whirlpool::Steps`). Each step is one piece, a `Seg`: absolute coordinates `y = v0 +
M(u − u0)` on `[u0, u1)`, where `(u0, v0)` and `(u1, v1)` are the step's EXACT cumulative input and output and `M` is
the step's Möbius curve in local coordinates (§2.8; a limit-order fill is the line `c = 0`). A step that ends inside its
range ends the stream (the input is used up), so does the venue's capacity, and the walk budget ends the domain like a
DLMM leg's. On an interval where a CLMM piece is involved the interior root comes from the same table after re-centring
both pieces at the interval's start (`opt::recentre`, `root_general`): a Möbius `a·u/(b + c·u)` re-centred at `s` is
`a' = a·b/(b + c·s)`, `b' = b + c·s`, `c' = c`, so the CPMM, DLMM and DAMM pieces keep their old formulas and only
the CLMM ones go through the general form. The non-concavity guard uses each step's bound (§2.8). There is no
resumable cursor yet: an exact CLMM evaluation walks from the pool's price, bounded by the leg's budget, which
`budget::cu_bound` charges per evaluation (§4.7). The golden-section fallback never runs over a walking leg (DLMM or
CLMM, `AnyLeg::walks`). Checked on the fixtures (`tests/clmm.rs`): over the Raydium DCAL ↔ Orca 4uny route at four
gaps, the locator's choice matches or beats the best of a 2,000-point grid of exact round trips; on the real programs
(`venue-harness tests/clmm_route.rs`) the realized profit equals the modeled one to the unit and beats `e` and a grid.

### 3.5 Candidates and choice ("never worse than the fixed amount")

```
C = { x̂_i : clamped local optima (≤ 3; BASKET: the best per pair) }  ∪  { e on pair 0 }
for c in C (deduplicated per (leg, amount)): E(c) = exact profit (sell output − buy-leg debit) via the venues' exact
    evaluators, resumed from the locator's cursors; ⊥ if a leg returns Abort/TooLarge/ZeroOut
    a candidate past a capacity or the walk budget steps back to the last feasible size (§3.3)
choose c* = argmax_{E(c) ≠ ⊥} E(c); ties → e, then the smaller x
E(e) unknown — pair 0 aborted, or a leg answered Budget at e — keeps e as the fallback:
    Budget at e            → Fallback (reason BUDGET): the engine's max_bins was too small; e executes
    pair 0 aborted (BASKET) → another pair's c* executes only if it clears min_profit, else Fallback at e
```

Every candidate evaluation may read at most `NEAR_BINS = 4` DLMM bins past the cursor it resumes from (`NEAR_BACK =
2` for a step-back; past that it counts as past the capacity), and only `e` may walk a DLMM leg from its active bin (up
to the budget): the static CU bound of §4.7.

`E(e)` is evaluated even if it is far from `x*`. That costs one more round trip, and it is the comparison that makes
the guarantee hold.

**Claim.** If `E` is exact (it equals the venue's realized outputs), then
`realized(c*) = E(c*) ≥ E(e) = realized(e)`. The executed size is never worse than the engine's fixed amount. If `e`
is infeasible (`E(e) = ⊥`: TooLarge, ZeroOut), `realized(e)` would have been a revert, which is no better. A `Budget`
answer is NOT ⊥ (the venue fills `e`), which is why it falls back to `e` instead (REVIEW.md F3). When pair 0 aborts,
the claim weakens to "the route lands with at least `min_profit`, or executes `e`".

The guarantee rests on three things:
1. **Exactness.** Proven per venue by §6.3, and watched in production by AXZ1 (modeled leg outputs against AXL1
   `delivered`).
2. **The same state.** The plan reads the very accounts and Clock the CPIs then run against, inside the same
   instruction, and nothing else runs in between.
3. **Leg independence.** Leg 1's pool is untouched by leg 0, because a pair's two pools must differ, which is checked.

If exactness fails (an unannounced venue upgrade), the claim degrades to "the guard still holds". The shadow and
production logs show the drift, and the engine turns sizing off for that kind.

### 3.6 Golden-section fallback (SEARCH flag; off by default)

This is for states where the analytic model refuses but the exact evaluator works. Since the DAMM v2 rate limiter
refuses at parse (§2.5), no in-scope state reaches it; it stays as the test oracle and for future refusals. It never
runs over a DLMM leg (its exact evaluations would walk bins: REVIEW.md F4); such a pair aborts.
- Search over integers on `[lo, hi] = [min_size, x_max]` with ratio `φ⁻¹ = 0.6180339887` (as Babq's `0xcfd0`).
- Stop after `max_iters` iterations (descriptor, ≤ 24) or when `hi − lo ≤ max(1, (hi − lo₀) >> 12)`.
- Each iteration is one exact round-trip evaluation, so at most `max_iters + 2` evaluations. Infeasible points count
  as `−∞` (that keeps the bracket inside the feasible prefix, since feasibility is monotone in `x`).
- The search result joins `C` above, so the "never worse" claim is unchanged.

**Convergence sketch.**
- For a unimodal `πR` the bracket shrinks by 0.618 per iteration and always contains the argmax while comparisons are
  correct.
- With noise `|η| ≤ ε` a comparison can be wrong only when `|πR(a) − πR(b)| ≤ 2ε`. For a concave `πR` with probe
  points at the golden ratios, that discards an interval whose best value exceeds the kept probe by at most
  `(φ²)·2ε ≈ 5.2ε`.
- So the result satisfies `πR(x̃) ≥ πR* − O(ε) − ½·|πR''|·w²`, where `w` is the final width.
- Starting from 2^42 lamports, 24 iterations give `w ≈ 2^42·0.618^24 ≈ 4·10^7`, which is fine near a flat optimum.

### 3.7 BASKET choice

1. Run §3.3-§3.5 for each pair, with `e` only in pair 0's candidate set. When pair 0 aborts, `e` is the fallback
   (§2.6, §3.5).
2. The global candidate list is the union over pairs. It holds at most 4 exact round trips: each pair's best `x̂`,
   plus pair 0 at `e`.
3. Pick the argmax of `E`.

Pairs that share a pool reuse that leg's parsed state (parsed once per leg, not per pair). Evaluations are also
deduplicated per `(leg, amount)`.

### 3.8 Approximate arithmetic for the locator (`fx`)

The locator needs a relative precision of about 1e-6 at most. The profit lost to a relative error `δ` in `x*` is about
`π*·δ²`, because the optimum is quadratic.

The crate therefore uses a deterministic integer pseudo-float `Fx { m: u64, e: i16 }`:
- mantissa normalised to `[2^31, 2^32)`, value `m·2^e`;
- `mul`: `(m1·m2) >> 31`, one native u64 multiply;
- `div`: `(m1 << 32)/m2`, one native u64 divide;
- `sqrt`: u64 integer Newton from a bit-length seed;
- `add`/`sub` with alignment.

Each op costs about 10-40 CU. Compare a u128 division at 296-598 CU and a U256 division at 3,330 CU (§4.7). Relative
error is ≤ 2^-30 per op. There are no floats. All values the locator touches (reserves < 2^64, Q64.64 prices,
`L < 2^128`) convert exactly by shifting. The result is converted to u64 by floor and saturation. `Fx` never decides
anything by itself: only exact `E` decides.

---

## 4. Instruction encoding and runtime

### 4.1 Placement in the v3 layout

```
[0] version 3 | [1] flags | [2] n_legs | [3..11] amount_in | [11..19] min_profit
[+8 max_payer_lamport_drop if PAYER_GUARD] [+19 tip block if CPI_TIP]
per leg: 5 B meta (n_accounts, leg_flags, amount_offset, data_len u16)       ← unchanged
SIZING BLOCK (§4.2)                                                         ← new, iff SELF_SIZE
leg data (unchanged)
```

- `SELF_SIZE (0x08)` without `BASKET`: `n_legs == 2`, and the pair is implicitly `(0, 1)`.
- `BASKET (0x10)` requires `SELF_SIZE`: `2 ≤ n_legs ≤ 6`, with the pairs given in the block.
- Both forbid NATIVE leg flags.
- `amount_in` becomes the **cap**. The runtime cap is `min(amount_in, quote_balance_at_entry)`.

arbx-exec's parser computes the start of the leg data from the block's own length. The block is self-delimiting, as
shown below.

### 4.2 Sizing block

| Bytes | Field | Rules |
|---|---|---|
| 1 | `sz_flags` | bit0 STRICT, bit1 EARLY_ABORT, bit2 SHADOW, bit3 SEARCH, bit4 EXPLICIT_POS, bit5 LAMPORTS; bits 6-7 must be 0 |
| 4 | `min_size` u32 (quote units) | `1 ≤ min_size ≤ engine_amount`. A u32 is enough: 4.29 SOL or 4,294 USDC |
| 8 | `engine_amount` u64 (`e`) | `≤ amount_in`. The fixed size the engine would have sent, used for the fallback and for the "never worse" comparison |
| 4 | `lamport_offset` i32 | only if LAMPORTS (bit5): the engine's modeled lamport delta of the executed legs (rent of accounts a venue creates is negative). With COUNT_LAMPORTS the guard's `g` includes lamports; `plan`'s NoProfit verdict uses `g = profit + lamport_offset` (REVIEW.md F10). Engines that set EARLY_ABORT together with COUNT_LAMPORTS must set it |
| 1 | `max_iters` | only if SEARCH; ≤ 24 |
| 1 + 2·k | `n_pairs` + k × (`buy_leg` u8, `sell_leg` u8) | only if BASKET; 1 ≤ k ≤ 3; legs distinct and < n_legs |
| per leg | leg sizing descriptor (§4.3) | `n_legs` entries, in leg order |

**Size.** A SELF_SIZE route (2 legs, no PumpSwap or DLMM) adds 1 + 4 + 8 + 2 = **15 bytes**, plus 1 per PumpSwap leg
and 1 per DLMM leg (+4 with LAMPORTS). A 3-pair basket over 4 legs adds 1 + 4 + 8 + 7 + 4 (+1 per PumpSwap or DLMM
leg) ≈ **25-29 bytes**.

### 4.3 Leg sizing descriptor

```
u8 kd:  bits 0-3 kind (1..=8, §1.2) | bit 4 dir (0 = token0 / x / a / BASE is the input; PumpBuy requires 1, PumpSell 0)
        bits 5-7 n_bin_arrays: DLMM 1..=5 bin arrays at positions 16..; RayClmm 1..=7 remaining accounts at 13.. (the
                 bitmap extension when passed, then the tick arrays); Whirlpool 0..=3 supplemental tick arrays at
                 15..; any other kind 0
u8 bump                      PumpBuy / PumpSell only: pool-authority PDA bump (0 = pool is not canonical) (§2.1)
u8 max_bins                  Dlmm, RayClmm, Whirlpool: the walk budget — DLMM bins, CLMM swap steps — the leg's
                             walks may read (1..=255; 0 is a DescError)
[EXPLICIT_POS] u8 n_pos, n_pos × u8 position                   positions in the kind's order below
```

**The walk budget (`max_bins`).** The engine sets it per DLMM leg from its own exact quote, with this crate's
`DlmmLeg::bins_for` (§5.5):
- at least the bins the leg's swap reads at its input for `e` (a buy leg: `e`; a sell leg: the buy leg's output at
  `e`), so `E(e)` is always evaluated (else the plan falls back to `e`, reason BUDGET);
- the cap rule: the bins at the leg's input for the route's cap (the bins the CU limit already pays for); or the tight
  rule: the bins at `max(e, 1.25·x̂)`, `x̂` from the engine's own off-chain `plan` run, plus 2 — a much smaller
  static CU bound (§4.7) with room for the state to move;
- at most what the transaction's CU allows: `budget::cu_bound` plus the venue CPIs (≈5.45k per bin) must fit 1.4M.

A plan whose optimum lies past the budget sizes at the budget's end (the locator treats it as the domain end).

**Default positions** are compiled in. They equal `src/build.rs` today; the builder and the crate share them through
the crate's `layout` module (§5).

| Kind | Positions read, in order (index into the leg's own account list) |
|---|---|
| PumpBuy | pool 0, global_config 2, base_mint 3, quote_mint 4, base_vault 7, quote_vault 8, fee_config 21 |
| PumpSell | pool 0, global_config 2, base_mint 3, quote_mint 4, base_vault 7, quote_vault 8, fee_config 19 |
| RayCpmm | pool 3, amm_config 2, vault_in 6, vault_out 7, mint_in 10, mint_out 11 |
| RayAmmV4 | amm 1, coin_vault 3, pc_vault 4 |
| Dlmm | lb_pair 0, mint_x 6, mint_y 7, first_bin_array 16 (count from `kd`) |
| DammV2 | pool 1, mint_a 6, mint_b 7 |
| RayClmm | pool 2, amm_config 1, vault_in 5, vault_out 6, mint_in 11, mint_out 12, first remaining 13 (count from `kd`) |
| Whirlpool | whirlpool 4, mint_a 5, mint_b 6, vault_a 8, vault_b 10, tick_array_0 11 (then 12, 13), oracle 14, first supplemental 15 (count from `kd`) |

The leg's program account (`accounts[start+1]`) must be the kind's venue. The `kind ↔ allowlist index` map is
DLMM 0, Whirlpool 1, Raydium CLMM 2, PumpSwap 3, CPMM 6, AMM v4 7, DAMM v2 8 (arbx-exec's `ALLOWLIST_B58`). Constant
keys are checked too (GlobalConfig, FeeConfig).

**Tick arrays for the CLMM kinds** (§9): Raydium CLMM passes the extension when it exists, then the tick arrays in walk
order from the first one the swap reads (`ClmmWalk.arrays`) up to the array where a quote **at the cap** ends, plus
one more initialized array, at most 7 remaining accounts in all — the DLMM rule. Orca Whirlpool passes, as its 3
static tick arrays, the PDAs of the 3 start indexes the program's sequence needs (`needed_starts`, initialized or not;
the last one repeated where fewer than 3 are valid) and no supplemental array: no swap reads beyond them.

**Bin arrays for DLMM.** The engine passes, in the swap's own order:
- the arrays the swap would visit up to the array where a quote **at the cap** ends;
- plus one more array;
- at most 5 in total.

That is today's rule (`dlmm_leg`), with the cap in place of the engine's amount. The walker follows the bitmap
(§2.4), so it does not depend on contiguity. Any array it needs that was not passed caps the domain, where the program
would fail.

### 4.4 BASKET: legs, pairs, accounts

The leg list holds each distinct leg once. A pool used for buying in one pair and selling in another appears as two
legs, because the directions differ.

**Example: HOTBOT (mint 8nnae…, Token-2022), 3 pools.** PumpSwap GLL3 (canonical, wSOL quote), DLMM 6D4E (bin step
100) and DLMM C9xc (bin step 200, fee on Y). In both DLMM pairs X = HOTBOT and Y = wSOL (layout-check: token flags
x/y = 1/0). The engine sees GLL3 as cheap:

```
legs : 0 = GLL3 PumpBuy (dir 1)      1 = 6D4E Dlmm X→Y sell (dir 0)
       2 = C9xc Dlmm X→Y sell (dir 0; fee on the Y output)      3 = C9xc Dlmm Y→X buy (dir 1; fee on the Y input)
pairs: (0,1) (0,2) (3,1)          → 4 legs for 3 pairs instead of 6
```

**Accounts.** These are unchanged in shape:

```
[0] authority  [1] quote account
then for every leg l in leg order: [output account_l, program_l, leg accounts_l …]
start_0 = 2 ; start_{l+1} = start_l + 2 + n_accounts_l     (prefix sums from the 5-byte metas; no account is read to skip)
```

**Rules:**
- **Buy legs.** A leg used as a buy in any pair delivers into the X account. All buy legs share it, so its output slot
  is the same key.
- **Sell legs.** A leg used as a sell delivers into the quote account.
- **Up-front checks.** Every pair is validated before planning: aliasing, allowlist, kind/program, and the sell leg's
  input mint equal to the buy leg's output mint. A malformed unused pair is `ERR_SIZING_DESC`. That is deterministic
  and catches builder bugs even when the pair is never chosen.
- **Unused legs.** Their accounts are part of the instruction and so count toward the transaction's account and size
  budgets. They are **never invoked**: the leg loop runs only `[buy_leg(p*), sell_leg(p*)]`, each with its own
  `start_l`.
- **Payer guard.** PAYER_GUARD token snapshots apply to the executed legs only.

### 4.5 Execution flow in arbx-exec (integration contract)

arbx-exec is owned elsewhere. This is the contract that its parser and `process_instruction` need.

```
route = parse(data)                       // v3: SELF_SIZE/BASKET now accepted when built with feature "sizing";
                                          // the sizing block is parsed and validated (DescError → ERR_SIZING_DESC)
… existing checks: authority signer, quote is a token account, WSOL rules, CPI_TIP accounts …
quote_before = token_amount(quote)
if let Some(sz) = route.sizing {
    starts = prefix sums;   check every leg's program ∈ allowlist and == kind's venue        (ERR_SIZING_DESC)
    clock  = Clock::get()                                                        // ~150 CU
    views  = for each leg: AcctRef{key, owner, data} of its state accounts (layout::positions) + the input account's mint
             — data slices taken with RefCell::as_ptr (no borrow guard), sound because no CPI runs and no RefMut exists
               until the plan returns; every slice is dead before the first invoke (same discipline as invoke_unchecked)
    plan   = arbx_sizing::plan(&PlanIn{ clock, cap: min(amount_in, quote_before), min_size, e, min_profit, tip,
                                         flags, max_iters, lamport_offset: block.lamport_offset,
                                         legs: views, pairs })                           // Err(DescError) → ERR_SIZING_DESC
    sol_log_data(AXZ1(plan))
    match plan.outcome {
        NoProfit  if EARLY_ABORT => return if NOOP_ON_MISS { Ok(()) } else { Err(ERR_SIZING_NO_PROFIT) },
                                  // (never returned while E(e) is unknown: that case is Fallback, §3.5)
        Fallback  if STRICT      => return Err(ERR_SIZING_UNSUPPORTED),
        _ => {}
    }
    exec = SHADOW ? (pairs[0], e) : (pairs[plan.pair], plan.amount)
} else { exec = (all legs, amount_in) }
leg loop over exec.legs, input = exec.amount, cursor = starts[leg]     // body unchanged: allowlist, aliasing, snapshots,
guard (unchanged)                                                      // patch, invoke_unchecked, delivered, AXL1
```

**Proposed error codes.** arbx-exec owns the numbering; today's last code is +12.

| Code | Name | Meaning |
|---|---|---|
| `0x4E58000D` | `ERR_SIZING_DESC` | bad, inconsistent or malformed sizing descriptor or accounts |
| `0x4E58000E` | `ERR_SIZING_UNSUPPORTED` | STRICT and the model refused |
| `0x4E58000F` | `ERR_SIZING_NO_PROFIT` | EARLY_ABORT and no candidate reaches `min_profit` (with CPI_TIP: `g − tip(g)`) |

**AXZ1 record** (76 B, one per sized route, logged even under SHADOW). Layout:

```
magic "AXZ1"[4] outcome u8 pair u8 n_pairs u8 flags u8 reason u16 evals u8 bins u8
x u64 | e u64 | x_star u64 | cap u64 | y_x u64 | y_e u64 | profit_x i64 | profit_e i64
```

- `outcome`: 0 sized, 1 shadow, 2 fallback, 3 no-profit.
- `reason`: the §2.6 code.
- `x` is the planned size.
- `y_x` and `y_e` are the modeled leg-0 outputs at `x` and at `e`; `profit_x` and `profit_e` are the modeled profits.
  The recorder compares the pair for whichever size actually executed (`e` under SHADOW or fallback, `x` otherwise)
  with AXL1 `delivered` and with AXS1 `quote_delta`. Any difference is a model drift alarm.
- `y_e` is 0 and `profit_e` is `i64::MIN` when `e` was infeasible or not evaluated.

AXS1's `amount_in` keeps meaning the instruction's `amount_in` (the cap). The executed size is AXL1 leg 0's `input`.

### 4.6 Transaction size and account budget

**SELF_SIZE** adds 15-17 bytes and no accounts: every state account is already in the leg. Today's copies reach up to
1,209 of 1,232 bytes, with static pool keys. SELF_SIZE therefore fits only where the transaction has at least 17
bytes of headroom. The redesign's plans (ALT coverage of pool accounts, a recent blockhash instead of the nonce) free
10-74+ bytes each. A route that does not fit is sent unsized, which is today's behaviour.

**BASKET** costs the extra legs: per leg, 5 B of meta, 2 + n_accounts B of account indexes, and about 24-28 B of data.

The HOTBOT 4-leg/3-pair example:

| Item | Leg | Bytes / count |
|---|---|---|
| Leg accounts (each leg: 2 + n) | PumpBuy | 2 + 26 |
| | each of the 3 DLMM legs (16 + 4 arrays + 2) | 22 |
| | route instruction total | 2 + 28 + 3·22 = **96 index bytes** |
| Leg data | PumpBuy | 24 |
| | 3 DLMM legs | 3 × 28 |
| | headers, metas, sizing block | 19 + 20 + 26 |
| | route instruction total | ≈ **173 B** |
| Unique accounts | shared (payer, quote, X ATA, 2 mints, 2 token programs, system, ATA, memo, ComputeBudget, arbx-exec, tip account) | ≈ 13 |
| | PumpSwap pool-side | 17 |
| | 6D4E (pair, 2 reserves, oracle, 4 arrays, plus the DLMM program and event authority, shared) | ≈ 10 |
| | C9xc in both directions | ≈ 9 |
| | total | **≈ 49 < 64** |
| Message size | with every non-signer, non-top-level-program key in ≤ 4 ALTs | ≈ 64 (sig) + 3 + 4·32 (static) + 32 + 4·34 + 49 (ALT refs) + ~40 (compute budget, tip, close) + ~275 (route) ≈ **730 B** |

**Conclusions:**
- BASKET requires ALT coverage of pool accounts. Without it, every new pool key costs 32 B, and two extra pools
  already break 1,232.
- BASKET is bounded by the account-lock limit (64 on Agave unless the cluster has raised it: check before relying on
  more) and by `MAX_IX_ACCOUNTS = 255` (here 96).
- The engine keeps "drop to SELF_SIZE, then to unsized" as its size fallback.

### 4.7 CU budget

**Measured primitives** (SBF, LiteSVM 0.17, platform-tools v1.57, `overflow-checks = true`; `research/cubench`,
CU per op net of the loop):

| Operation | CU |
|---|---|
| u64×u64→u128 | 52 |
| u128×u128 | 61 |
| u128 / u128 (divisor > 2^64) | 296 |
| u128 / u128 (divisor < 2^64) | 598 |
| U256::mul128 | 263 |
| U256 div_rem 256/128 (Knuth, `src/venues/dammv2.rs`) | 3,330 |
| isqrt u128 (Newton, power-of-two seed) | 3,567 |
| one exact DLMM bin (drain test + fill, MM layer) | 1,057 |
| one exact CPMM quote | 526 |
| CPMM-CPMM closed form with u128 + isqrt | 2,633 → replaced by `Fx`, about 0.3-0.5k (est.) |

From these:
- `Fx` is required for the locator.
- isqrt, if ever needed exactly, must be seeded from a u64 hardware sqrt-by-Newton (about 0.5-1k).
- U256 division is the DAMM v2 cost driver. A specialised 256/128 → 128 divide (two 128/64 steps) should roughly
  halve it; that is an optimization for after the harness.

**Measured sizing CU** (SBF, `sbf-check` full minus baseline on the same instruction: the shell's account borrows,
clock read and log are excluded; platform-tools v1.57, sbpfv3, overflow checks on; `sbf-check/cu-runner`, 2026-10-04,
after the review fixes):

| Route | Sizing CU | `cu_bound`, budgets at the cap | `cu_bound`, tight budgets |
|---|---|---|---|
| CPMM → AMM v4 (closed form) | 7,191 | 26,500 | 26,500 |
| PumpSwap buy → CPMM (closed form, canonical-PDA syscall) | 11,106 | 36,700 | 36,700 |
| DLMM buy → CPMM, 1 / 2 / 3 bins | 13,496 / 15,700 / 16,373 | 174k / 1.05M / 1.05M | 86k / 95k / 98k |
| DLMM → DLMM (unprofitable, 2 bins) | 18,243 | 975k | 145k |
| HOTBOT GLL3 → 6D4E, real state (NoProfit) | 18,072 | 229k | 95k |
| HOTBOT GLL3 → 6D4E, GLL3 quote −12% (sized, 4 bins; SHADOW identical) | 26,152 | 244k | 111k |
| DAMM v2 (b→a) → CPMM, three vector pools | 10,788 – 17,618 | 104k | 104k |
| BASKET 3 pairs, 4 DLMM legs, few bins (DESIGN target ≤ 60k) | **41,013** | 1.95M | 184k |
| BASKET PumpSwap buy + 3 DLMM legs, 34 bins | 112,768 | 1.29M | 337k |
| DLMM(bin step 1, 3% gap) → CPMM, optimum 90 bins out, fee rising / falling | 169,927 / 176,288 | 1.05M | 513k |
| DLMM(bin step 5, 3% gap) → CPMM, 38 bins | 80,304 / 86,665 | 1.05M | 266k |
| DLMM(bin step 25, 5% gap) → CPMM, 16-17 bins | 40,837 / 44,749 | 1.05M | 160-164k |
| DLMM(bin step 100) reversion arb (fee falling toward idx_ref) | 19,592 | 1.05M | 110k |
| BASKET 3 pairs, 4 bin-step-1 DLMM legs, 3% gap: budgets 255 / 48 | 1,275,222 / 441,349 | 4.43M / 951k | 2.87M / 852k |

Before the fixes (REVIEW.md F4) the bin-step-1 route cost 260k while stopping at a 64-bin budget (the optimum is
90 bins out), the bin-step-5 route 159-174k, the bin-step-1 basket 457k at 64-bin budgets, and nothing bounded a plan.

**Per-unit costs** (cu-runner modes 6-9, per bin with liquidity): the bin walk ≈350, the exact drain ≈610 more, the
locator's model ≈500 more plus ≈400 per step in `locate`: ≈1.85k per bin the locator reads; an exact quote ≈1.5k plus
≈0.9-1.4k per bin it reads. The venue's own swap costs ≈5.45k per bin crossed. The `v2` build is ≈14% cheaper on the
long walks (146k for the bin-step-1 route); `v0` equals `v3`.

**The static bound.** `sol_remaining_compute_units` is not active on mainnet, so the program cannot stop itself;
instead every piece of the work is bounded by the block alone and `budget::cu_bound(block)` adds it up:
`FIXED + Σ parse(leg) + Σ_pairs [LOCATE + LOCATE_BIN·(b0 + b1) + n_cand·(eval(b, NEAR_BINS) + eval(s, NEAR_BINS))]
+ eval(b0, b0) + eval(s0, b1) [e: may walk from the active bin] + MAX_BACK·max_pairs(eval(·, NEAR_BACK))`, with
`b = max_bins` of a DLMM leg (0 otherwise), `n_cand` = 3 (SELF_SIZE) or 1 (BASKET), and per-unit costs measured and
rounded up (`budget::cost`: LOCATE_BIN 2.3k, EXACT_BIN 1.5k, …). The CU runner checks every measured route against
the bound of its own block and fails otherwise (§6.4). The engine adds it to the transaction's CU limit with the venue
CPIs at the cap.

**Choosing the budgets.** The bound is linear in the walk budgets, so the engine's `max_bins` rule (§4.3) decides how
tight it is: budgets from the cap give a bound of up to ≈1M for a single DLMM leg at 255 bins (the walk may in the
worst case rise all the way to the budget's end); the tight rule (bins at `max(e, 1.25·x̂)` + 2) gives 86-111k for the
few-bin routes above. Either way the transaction must also pay the venue CPIs (≈5.45k per bin), so the budgets of a
route whose optimum is hundreds of bins out (bin step 1 against a 3% gap) are capped by what the 1.4M limit allows —
e.g. 48 bins per leg for the 3-pair bin-step-1 basket (441k sizing + two DLMM CPIs ≈ 0.6M).

**CU limit.** The engine computes the transaction's CU limit at the **cap**: overhead + legs at the cap (DLMM bins
crossed at the cap) + `cu_bound(block)`. `x̂ ≤ cap` and crossings are monotone in `x`, so the chosen size never needs
more. With BASKET it takes the maximum over pairs. Bundles pay no priority fee, so a generous limit costs nothing there.

**The CLMM kinds (WP-21): estimates, not measured on SBF.** `budget::cost` charges PARSE_CLMM 4,000 + 600 per tick
array passed, EVAL_CLMM 8,000 + EXACT_STEP 16,000 per step of the walk budget for EVERY exact evaluation (no resumable
cursor yet: each may walk the whole budget), and LOCATE_STEP 20,000 per step for the locator. A step is a few 256-bit
mul-divs (≈3.3k each, above) and a tick ↔ sqrt-price conversion; the figures are rounded well up. With them the bound
of a SELF_SIZE pair CLMM ↔ CPMM is ≈118k + 212k per budget step (4 steps: ≈0.97M), because a plan may evaluate a leg up
to 12 times. So on-chain sizing of kinds 7 and 8 needs, first, exact resumable states per step (as DLMM's cursors, §3.4)
and then the sbf-check measurements; until then arbx-exec keeps the features off and the kinds are used off chain only
(§9). The venues' own CPI costs are measured: Raydium CLMM ≈41.5k + ≈9.1k per tick crossed + ≈8.5k per other step,
Orca Whirlpool ≈28-30k + ≈7.0k per crossing + ≈8.6k per other step (§2.8, §2.9).

### 4.8 SBF limits and discipline

- **No allocation in the crate.** The plan works on borrowed slices and small structs. The shell's view array is
  ≤ 6 legs × ≤ 12 state accounts × 32 B ≈ 2.3 KB. Build it on the heap once (the 32 KB bump allocator never frees; today
  it holds only arbx-exec's reused instruction buffers) or on the stack in its own `#[inline(never)]` frame.
- **Stack.** Design to 4 KB frames whatever the sbpf version:
  - no recursion;
  - every large function `#[inline(never)]`;
  - the per-leg parsed state ≤ 256 B;
  - the DLMM walker holds only slices and indices (no bin table: the locator and the evaluator stream bins);
  - candidate sets are fixed arrays of ≤ 8.
- **Borrow discipline.** Described in §4.5. The plan ends before the first `invoke_unchecked`.
- **No `sol_remaining_compute_units` at runtime.** It is not active on mainnet. Budgets are static bounds (each DLMM
  leg's `max_bins`, `NEAR_BINS`/`NEAR_BACK`, `MAX_BACK`, `max_iters`, the n_bin_arrays limit) that `budget::cu_bound`
  adds up from the block alone, and CU is measured in the harness against that bound (§4.7, §6.4).
- **No panics.** Everything is checked, and a failure becomes `Abort::Math` (§2.6). Release builds keep
  `overflow-checks = true` as a second line of defence.
- **Code size (measured, REVIEW.md F11).** `sbf-check` without its bench modes: 206,392 B against a 14,584 B baseline,
  so sizing adds ≈192 KB (sbpfv3; v2 214 KB, v0 219 KB with the bench modes) — not the 40-80 KB estimated. With
  `lto = "fat"`, `opt-level = "z"`: 154,544 B (≈144 KB of sizing). PumpSwap + DLMM only: 137,528 B (LTO + z: 107,096
  B); DLMM only: 119,520 B. arbx-exec should build its `sizing` feature with only the kinds the engine sizes, with LTO,
  and budget the program and upgrade-buffer rent for ≈150-200 KB more (redesign §3.9).
- **Frames.** `plan` is `#[inline(never)]` so its parsed legs (≈2 KB) never merge into the caller's frame: before
  that, an LTO build inlined it into the shell's `run` and passed the 4 KB frame limit (5,184 B). No stack-frame
  warnings at `--arch v0/v2/v3`, with or without LTO, and the longest routes above execute on all three.

---

## 5. The crate: `program/arbx-sizing`

### 5.1 Layout

```
arbx-sizing/
  Cargo.toml            #![no_std]; no dependencies in the default build
  src/lib.rs            pub use of the API below; #![forbid(unsafe_code)]
  src/desc.rs           sizing block + leg descriptor: parse (no alloc); encode (feature "encode")
  src/layout.rs         compiled-in default positions, constant keys (GlobalConfig, FeeConfig, program ids), discriminators
  src/fx.rs             Fx pseudo-float (§3.8)
  src/math.rs           ceil_div, mul_shr_q64 / shl_div_q64 (split 64×128), checked helpers, isqrt_u64
  src/u256.rs           U256 subset (ported from src/venues/dammv2.rs; same semantics as the ruint ops it replaces),
                        plus the 512-bit product and Knuth division the CLMM kinds need (mul_full, div_512, mul_div_wide)
  src/token.rs          token-account / mint views, Token-2022 TLV scan, paused / default-frozen mints (mint_blocked)
  src/venue/{pumpswap,cpmm,ammv4,dlmm,dammv2}.rs   parse + exact quote + model + capacity, each behind a feature
  src/venue/{raydium_clmm,orca_whirlpool}.rs       the same for kinds 7 and 8 (WP-21), features rayclmm / whirlpool
  src/leg.rs            AnyLeg enum dispatch (no dyn, no generics explosion), LegModel {Mobius | Bins}
  src/opt.rs            closed form, marginal walk, golden section, candidate choice
  src/plan.rs           plan(): descriptor + views → Plan
  tests/                unit, property, differential (dev-dependency on the arbx crate or copies of its quoters)
```

### 5.2 Features

| Feature | Default | Purpose |
|---|---|---|
| `pumpswap`, `cpmm`, `ammv4`, `dlmm`, `dammv2` | on | per-venue code; a kind whose feature is off is `Abort::Unsupported` |
| `rayclmm`, `whirlpool` (`clmm` = both) | off | Raydium CLMM, Orca Whirlpool (kinds 7, 8; WP-21). Their `AnyLeg`, `LegModel` and `Abort` variants exist only with the feature, so a default build (the engine, arbx-exec) is unchanged |
| `search` | on | golden-section fallback (still gated at runtime by the SEARCH flag) |
| `encode` | off | `alloc`-based descriptor encoder for the engine and tests |
| `std` | off | `std::error::Error` impls and `Debug` detail for host builds |
| `trace` | off | per-plan counters (evaluations, bins, locator steps) for CU attribution in the harness |

### 5.3 Public API (signatures; the semantics are the contract)

```rust
pub struct Clock { pub slot: u64, pub unix_timestamp: i64, pub epoch: u64 }
pub struct AcctRef<'a> { pub key: &'a [u8; 32], pub owner: &'a [u8; 32], pub data: &'a [u8] }

#[repr(u8)] pub enum Kind { PumpBuy = 1, PumpSell = 2, RayCpmm = 3, RayAmmV4 = 4, Dlmm = 5, DammV2 = 6,
                            RayClmm = 7, Whirlpool = 8 /* WP-21: parsed with the features rayclmm / whirlpool */ }
pub struct LegDesc { pub kind: Kind, pub base_or_token0_in: bool, pub n_bin_arrays: u8, pub pump_bump: u8,
                     pub max_bins: u8 /* walk budget: DLMM bins, CLMM steps */, pub positions: Option<[u8; 8]> }
pub struct SizingBlock { pub flags: SzFlags, pub min_size: u32, pub engine_amount: u64, pub lamport_offset: i32,
                         pub max_iters: u8, pub pairs: [(u8, u8); 3], pub n_pairs: u8, pub legs: [LegDesc; 6], … }
/// Parse the sizing block at `data[at..]`; returns the block and its length (arbx-exec adds it to the leg-data start).
pub fn parse_block(data: &[u8], at: usize, n_legs: usize, basket: bool, amount_in: u64) -> Result<(SizingBlock, usize), DescError>;
/// The static CU bound of planning this block (§4.7)
pub fn cu_bound(b: &SizingBlock) -> u64;
#[cfg(feature = "encode")] pub fn encode_block(b: &SizingBlock, out: &mut alloc::vec::Vec<u8>);

pub struct LegIn<'a> {
    pub desc: LegDesc,
    pub program: &'a [u8; 32],
    /// the leg's STATE accounts only, in the kind's order of §4.3 (DLMM: lb_pair, mint_x, mint_y, then the n bin
    /// arrays). The shell resolves them with `layout::positions(&desc)`, so the view stays ≤ 8 + 5 entries per leg.
    pub state: &'a [AcctRef<'a>],
    pub input_mint: &'a [u8; 32],     // mint of the account the leg spends from (direction check)
}
pub mod layout { pub fn positions(d: &LegDesc) -> impl Iterator<Item = u8>; /* default or explicit */ }
pub struct PlanIn<'a> {
    pub clock: Clock, pub cap: u64, pub min_size: u64, pub engine_amount: u64, pub min_profit: u64,
    pub tip: Option<TipParams>, pub flags: SzFlags, pub max_iters: u8, pub lamport_offset: i64,
    pub legs: &'a [LegIn<'a>], pub pairs: &'a [(u8, u8)], pub pda: PdaFn,
}
pub enum Outcome { Sized, Shadow, Fallback, NoProfit }
pub struct Plan {
    pub outcome: Outcome, pub reason: Reason, pub pair: u8, pub amount: u64,
    pub x_star: u64, pub modeled_profit: i128, pub modeled_profit_e: Option<i128>,
    pub modeled_y: u64, pub modeled_y_e: Option<u64>,
    pub evals: u8, pub bins: u16,
}
pub fn plan(p: &PlanIn) -> Result<Plan, DescError>;

// Per venue (used by plan, tests, the harness, and the engine off chain):
pub enum Abort { Unsupported /* kind's feature off */, Layout, TransferFee, TransferHook, Math, Pump(PumpWhy), Cpmm(CpmmWhy), Amm(AmmWhy),
                 Dlmm(DlmmWhy), Damm(DammWhy),
                 Clmm(ClmmWhy) /* feature rayclmm, §2.8 */, Whirl(WhirlWhy) /* feature whirlpool, §2.9 */ }
pub enum QuoteErr { Abort(Abort), TooLarge, ZeroOut, Budget /* past a DLMM / CLMM walk budget: not evaluated */ }
pub struct Quote { pub out: u64, pub spent: u64 }
pub enum AnyLeg<'a> { Pump(PumpLeg), Cpmm(CpmmLeg), Amm(AmmLeg), Dlmm(DlmmLeg<'a>), Damm(DammLeg),
                      RayClmm(RayClmmLeg<'a>) /* rayclmm */, Whirl(WhirlLeg<'a>) /* whirlpool */ }
impl<'a> AnyLeg<'a> {
    // outer: engine bug; inner (Parsed.leg): fallback. `pda`: create_program_address (PumpSwap's canonical bump, the
    // PDAs of uninitialized Whirlpool tick arrays)
    pub fn parse(l: &LegIn<'a>, clock: &Clock, pda: PdaFn) -> Result<Parsed<'a>, DescError>;
    pub fn walks(&self) -> bool;                                      // DLMM or CLMM: no golden-section search over it
    pub fn quote(&self, amount_in: u64) -> Result<Quote, QuoteErr>;   // EXACT: equals the venue to the unit
    pub fn model(&self) -> LegModel<'_>;                              // Mobius{a,b,c: Fx} | Bins(walker)
    pub fn cap_in(&self) -> Option<u64>;                              // None = unbounded
}
impl DlmmLeg<'a> {                                // off-chain helpers the engine uses with the same code
    pub fn with_budget(self, bins: u16) -> Self;  // NO_BUDGET = unbounded
    pub fn bins_for(&self, x: u64) -> Option<u16>;            // the max_bins that covers x
    pub fn start(&self) -> Cursor;  pub fn quote_from(&self, c: &Cursor, x: u64) -> Result<Quote, QuoteErr>;
    // WP-16 (host only, never called by plan): the exact swap bin by bin, layer by layer (BinFill: taken / paid per
    // layer, used, out, rate) and its Walk (quote, bins read, bins with liquidity taken from, the bin it ends on).
    // Equal to quote (tests/venues.rs dlmm_fills_equal_the_quote); the engine's DLMM post-state and CU inputs
    pub fn fills(&self, x: u64, f: &mut dyn FnMut(&BinFill)) -> Result<Walk, QuoteErr>;
}
pub mod venue::dammv2 { pub fn parse_with_limiter(..) -> Result<DammLeg, Abort>; }   // prices the rate limiter
pub mod venue::pumpswap { pub fn parse(pool, global, fee_cfg, base_mint, quote_mint, base_vault, quote_vault,
                                       sell: bool, bump: u8) -> Result<PumpLeg, Abort>;
    pub fn pool_len_ok(len: usize) -> bool;                    // POOL_MIN_LEN 211 ..= POOL_LEN 301 (WP-16 review F1)
    pub fn buy_exact_out(base, qv, fees, out) -> Result<(u64, Quote), QuoteErr>;   // the exact-out `buy` (host only, F6)
    impl PumpLeg { pub fn quote_exact_out(&self, out: u64) -> Result<(u64, Quote), QuoteErr>; } }
pub mod venue::raydium_clmm {                                     // feature "rayclmm" (WP-21, §2.8)
    /// `remaining`: the leg's remaining accounts in the order passed (classified by length like the program)
    pub fn parse(pool, cfg, remaining: &[&[u8]], vault0: u64, vault1: u64, zero_for_one: bool, clock: &Clock)
        -> Result<RayClmmLeg, Abort>;
    impl RayClmmLeg<'a> {
        pub fn quote(&self, x: u64) -> Result<Quote, QuoteErr>;               // EXACT (swap_v2 exact in)
        pub fn quote_exact_out(&self, out: u64) -> Result<Quote, QuoteErr>;   // EXACT (swap_v2 exact out)
        // the exact swap step by step (ClmmStep: prices, liquidity, fee rate, amounts, the tick crossed, its limit-order
        // fill, the array read) and its ClmmWalk: quote, steps, ticks crossed, the arrays read in the order the leg must
        // pass them, and the post-swap pool (sqrt price, tick, liquidity, fee growth, owed fees, dynamic fee)
        pub fn fills(&self, amount: u64, exact_out: bool, f: &mut dyn FnMut(&ClmmStep)) -> Result<ClmmWalk, QuoteErr>;
        pub fn steps_for(&self, x: u64) -> Option<u16>;    // the max_bins that covers x
        pub fn with_budget(self, steps: u16) -> Self;      // NO_BUDGET = unbounded
        pub fn cap_in(&self) -> Option<u64>;  pub fn stream(&self) -> Steps;  pub fn has_extension(&self) -> bool;
    }
    pub fn array_start(tick: i32, ts: u16) -> i32;  pub fn sqrt_price_at_tick(t: i32) -> Option<u128>;  … }
pub mod venue::orca_whirlpool {                                   // feature "whirlpool" (WP-21, §2.9)
    /// `arrays`: every tick array the leg passes (start index; bytes, None for a passed PDA that does not exist)
    pub fn parse(pool, oracle: Option<&[u8]>, arrays: &[TickArrayIn], vault_a: u64, vault_b: u64, a_to_b: bool,
                 clock: &Clock) -> Result<WhirlLeg, Abort>;
    pub fn needed_starts(tick: i32, ts: u16, a_to_b: bool) -> ([i32; 3], usize);   // the program's sequence
    pub fn start_seed(start: i32, buf: &mut [u8; 12]) -> &[u8];                     // the tick-array PDA seed
    impl WhirlLeg<'a> { quote, quote_exact_out, fills (→ WhirlWalk: …, arrays_used, post incl. the oracle's
                        variables), steps_for, with_budget, cap_in, stream, sequence() -> ([i32; 3], u8), is_adaptive() }
}
// … one `parse` per venue taking plain byte slices, so the engine can call the same code with its own snapshots.
```

### 5.4 Invariants

- **Purity.** Results depend only on the byte slices and the Clock passed in. No global state, no floats, no
  allocation in `plan` or `quote`, no panics (`#![deny(clippy::unwrap_used, clippy::expect_used, clippy::indexing_slicing)]`
  in `venue/` and `opt/`; slices via `get`).
- **Exactness.** `quote` is exact or errs. A state the code does not understand is an error, never a guess.
- **Monotonicity.** `quote(x).out` is non-decreasing in `x` wherever it is `Ok`. A property test checks this and the
  optimizer relies on it.
- **Bounded work.** Per pair the locator reads at most `max_bins` bins of each DLMM leg (one model step per bin);
  ≤ 3 candidates (1 in BASKET) are evaluated, each resuming from a recorded exact state and reading at most
  `NEAR_BINS = 4` DLMM bins past it; `e` (pair 0) may walk a DLMM leg from its active bin up to the budget; at most
  `MAX_BACK = 8` step-back evaluations per plan, each reading at most `NEAR_BACK = 2` bins past its state; golden
  section (SEARCH, never over DLMM) at most `max_iters + 4` round trips. `budget::cu_bound` adds these up (§4.7).

### 5.5 Who uses it

- **arbx-exec** (feature `sizing`): depends on `arbx-sizing` with the default features. It calls `parse_block` from
  `parse_v3` and `plan` from `process_instruction` (§4.5).
- **The engine** (`arbx`, std): uses `encode_block` and `layout` in the builder, `DlmmLeg::bins_for` for each DLMM
  leg's `max_bins` (§4.3) and `cu_bound` for the CU limit (§4.7) (WP-17). **Since PLAN-ADDENDUM WP-16 it quotes with
  the same `venue::*` code off chain** (`src/quote.rs`: a path dependency with the default features), which removes the
  divergences in §2.7 and makes "the program and the engine agree" true by construction: route pricing and sizing (the
  ladder plus `opt::locate`), the opportunity's legs, the budget caps, the hint checks and the accuracy monitor's
  amounts. Each refusal state (`Abort`, `Budget`, a PumpSwap sell past the held-back quote, the DAMM v2 rate limiter on
  our leg, a Token-2022 transfer fee or hook) is a decision's reason (`sz_*`). The engine's former maths is kept, tests
  only, in `src/venues/legacy` as the differential reference. Kinds 7 and 8 (WP-21) are not used by the engine or
  arbx-exec yet: §9 lists what integrating them needs.

---

## 6. Validation plan

### 6.1 Unit and property tests (host, `cargo test`)

- **`Fx`.** Against u128/f64 references on random operands, error ≤ 2^-29 relative. sqrt/mul/div identities.
- **U256.** Against long division (as `src/venues/dammv2.rs` tests do) and against `num-bigint` in proptest.
- **Venue quotes:**
  - unit vectors from §2: PumpSwap from the 112 events in `research/` (pre-reserves, bps and amounts → expected
    out), the DLMM fee vectors from the spec, the DAMM v2 vectors file;
  - properties: monotone in `x`; `quote(0)` is an error; out ≤ the leg's output reserve; capacity consistent
    (`quote(cap_in)` Ok, `quote(cap_in + 1)` TooLarge, where the cap is exact).
- **Optimizer:**
  - (i) never worse: for random pools and random `e`, `E(chosen) ≥ E(e)`;
  - (ii) near-optimal: on small synthetic pools (reserves ≤ 10^6) compare with brute force over every integer `x`,
    within `2ε`;
  - (iii) on random pairs, the closed form of §3.3 equals the golden-section result within the §3.6 bound;
  - (iv) DLMM walks with fee-decreasing paths (idx_ref ahead of the walk) still find the global optimum on the brute
    force;
  - (v) BASKET picks the brute-force best pair.
- **Descriptors.** `encode → parse` round trip. A fuzz target (cargo-fuzz or proptest over arbitrary bytes): never
  panics, and every accepted block re-encodes to the same bytes.

### 6.2 Differential tests against `src/venues`

Run on the same random and recorded states, with the engine's `cp.rs`, `dlmm.rs` and `dammv2.rs` against this crate:
- equal output everywhere except the documented divergences of §2.7, which are asserted as differences with bounded
  size;
- DAMM v2: identical (the same code), including every vector in `testdata/dammv2-vectors.json`.

When the harness (§6.3) disagrees with the engine's reference, the harness wins and the reference is a bug.

### 6.3 Exactness against the real venue programs (`program/venue-harness`)

This is the decisive test. The venue programs are the oracle.

**Binaries.**
- `solana program dump -u https://api.mainnet-beta.solana.com <id> fixtures/programs/<id>.so` (read-only) for:
  - PumpSwap `pAMMBay6…`;
  - the pump fee program `pfeeUxB6…` (PumpSwap passes it and may CPI it);
  - DLMM `LBUZ…`, DAMM v2 `cpamd…`, Raydium CPMM `CPMMoo8…`, AMM v4 `675kPX…`.
- Plus a `MANIFEST.json` per program: the programdata account's last-deploy slot, the dump's sha256, the fetch date.
- SPL Token, Token-2022, ATA and Memo come from LiteSVM's defaults (check versions against mainnet).

**Snapshots.** For every test pool:
- every account its swap instruction takes (the engine's own leg builder lists them);
- the mints, GlobalConfig, FeeConfig, the bin arrays (active ±3 that exist), the oracle and the bitmap extension;
- the PumpSwap volume accumulators and creator-vault ATAs where they exist;
- the slot and the Clock.

These are stored as `fixtures/accounts/<slot>/<pubkey>.json` (the RPC cache this design used is already in
`fixtures/rpc-cache`).

Pools to cover:
- the HOTBOT trio (GLL3, 6D4E with limit-order bins, C9xc with fee on Y, empty arrays and a bitmap jump);
- 6ejg (configurable creator fee, exotic quote);
- 2 CPMM, 1 AMM v4;
- 3 DAMM v2 (Token-2022 side, OnlyB, dynamic fee);
- at least one pool per DAMM base-fee mode and one compounding pool;
- an older DLMM pair (function_type 0 or 1, version gates).

**Swap runs.** For each pool and direction, a funded user (ATAs created) swaps in LiteSVM with the dumped program, from
the snapshot, at:
- about 40 log-spaced sizes from 1e3 to 1.1× capacity;
- every boundary size the model knows: each DLMM bin's drain threshold and its ±1, each limit-order layer edge, the
  DAMM range-exit `n_max` and its ±1, the PumpSwap real-reserve edge, and fee-ceil edges (`x` with `x·f mod den`
  equal to 0 or `den − 1`).

**Assertion, to the unit:**
- `Ok(q)` ⇔ the swap succeeds;
- the user's output delta == `q.out` and the input delta == `q.spent`;
- `TooLarge`/`ZeroOut` ⇔ the swap fails or delivers 0 (a TooLarge where the venue still swaps is a MISMATCH:
  TooLarge claims a venue capacity; there is no "conservative" verdict any more);
- `Budget`: the same quote without a budget must satisfy the two rules above, and the swap must really read more
  bins than the budget;
- a venue that runs out of the 1.4M transaction CU (a DLMM swap reading ≳246 bins) is recorded as
  "venue CU limit", not as a maths verdict;
- `Abort` is skipped but counted (the per-venue skip rate is a reported metric).

The suites (venue-harness): `tests/exactness.rs` (snapshots, 9 mutation families, ~45 sizes per leg, 1,000
consecutive PumpSwap buys), `tests/adversarial.rs` (the crate's own boundary sizes ±1, ±2 incl. the exact
capacities, Clock variations, 50+ state mutations incl. limit orders, function types, bitmap gaps, the pair's bin
bounds, the PumpSwap held amounts, the DAMM rate limiter and fee cap), `tests/route.rs` (below).

**Clock variations.** For DLMM and DAMM v2: `Δt ∈ {0, filter−1, filter, decay−1, decay, 10·decay}` seconds, and a slot
advance for slot-activated schedulers.

**State mutation.** The real program is the oracle for modes the snapshots lack. Rewrite pool bytes, then compare
again:
- DLMM: `collect_fee_mode` ↔ 0/1; inject `open_order_amount` / `processed_order_remaining_amount` / `ask_side` into
  bins; `va`, `v_ref`, `idx_ref` at extremes; `function_type` 0 and 1 (with and without reward mints).
- CPMM: `enable_creator_fee = 1` with `creator_fee_on` 0, 1, 2; nonzero owed fees.
- AMM v4: `need_take_pnl`.
- PumpSwap: V negative, zero and large; `creator_fee_bps` set and unset; `coin_creator = 0`; market cap across tier
  thresholds (via the base-mint supply); exotic or USDC quote.
- DAMM v2: every base-fee mode with its parameters; `collect_fee_mode` 0, 1, 2; `fee_version` 0 and 1.

A mutation the program rejects is fine: the model must reject it too.

**Pins (§7)** are settled here and recorded as named tests.

**Route level without arbx-exec (done: `venue-harness/tests/route.rs`).** `plan` runs in the bridge with the engine's
`max_bins` rule; each candidate size is executed leg by leg on the dumped programs (leg 1 spends what leg 0
delivered): HOTBOT GLL3 ↔ 6D4E in both directions at six gaps (assertions 2-4, and "the venue fills e ⇒ E(e) was
evaluated"), and a BASKET of both directions as two pairs over four legs at four gaps (assertion 5, and NoProfit with
`min_profit` above the plan). The third HOTBOT pool C9xc has no liquidity any more (empty bitmap), so a 3-pool basket
awaits another same-mint pool set.

**Route level with arbx-exec.** The arbx-exec .so built with `--features sizing`, together with the real venues:
- Two-pool routes from the snapshots (HOTBOT GLL3 ↔ 6D4E, 6D4E ↔ C9xc, DAMM ↔ PumpSwap, CPMM ↔ PumpSwap). A gap is
  created by scaling one pool's reserves or bins.
- Assert:
  1. the executed `x` == `Plan.amount` (AXZ1, AXL1);
  2. realized profit == `modeled_profit` exactly, and leg-0 `delivered` == `modeled_y`;
  3. realized ≥ realized at `e`, from a cloned SVM run;
  4. realized ≥ the best of a 64-point grid of `x`, in cloned SVMs, minus `2ε`;
  5. BASKET: the chosen pair's realized profit ≥ every other pair's realized profit at its own `x̂`, in cloned SVMs;
  6. fallback paths: a mutated unsupported state gives `outcome = Fallback` and execution at `e`; STRICT reverts with
     `ERR_SIZING_UNSUPPORTED`; EARLY_ABORT reverts before any CPI (no venue log lines);
  7. DescError cases (wrong position, wrong owner, swapped direction, same pool twice) revert with `ERR_SIZING_DESC`.

**The CLMM kinds (WP-21): `tests/clmm_exactness.rs`, `tests/clmm_adversarial.rs`, `tests/clmm_route.rs`.**
- **Binaries.** `fixtures/programs/CAMMCzo5….so` (1,523,736 B, sha256 `e6963f72991821e2…`, last deployed at slot
  451,479,902) and `whirLbMi….so` (1,488,104 B, sha256 `4b5cb126a352f68d…`, slot 440,170,207), dumped read-only
  (`MANIFEST.json`).
- **Snapshots** (`fixtures/pool-list-clmm.json` → `fixtures/pools-clmm/`, 20 pools, 1.6 MB, slots 453,942,354-440 on
  2026-10-06): every account `swap_v2` takes, the mints, the AmmConfig, the bitmap extension, the oracle, and the tick
  arrays around the price (Raydium: the current one and 5 initialized ones each way; Orca: the current one and 3 each
  way, fixed or dynamic).
  - Raydium CLMM (10): 3ucN SOL/USDC (tick spacing 1, 0.04%, real limit orders, 2 spacings from its array's end), 2uoK
    SOL/JitoSOL (1, 0.01%: the lowest tier), E8TR (60, 0.25%), dAVk (120, 1%), DCAL (1, dynamic fee, beyond the default
    bitmap: needs the extension), DRW2 (120, fee_on 1, dynamic), HBfk (120, fee_on 2, dynamic), 7tJV (60, fee_on 2; a
    Token-2022 mint with Pausable, DefaultAccountState, a null transfer hook, ScaledUiAmount), ASk8 (120, 3%: the
    highest tier seen; a Token-2022 mint charging a 3% transfer fee), 45ss PUMP/SOL (10; Token-2022 PUMP).
  - Orca Whirlpool (10): Czfq SOL/USDC (4, fixed arrays), Hp53 SOL/JitoSOL (1, 0.01%), 5Kqo (4, adaptive fee, dynamic
    arrays; PYUSD, Token-2022 with a zero transfer fee), FAqh (64, 0.3%), Hxw7 ORCA/SOL (16), G1vH (256, 2%, adaptive;
    its sequence ends in uninitialized arrays), H2yE (a splash pool, tick spacing 32,896), CeaZ cbBTC/SOL (16; the tick
    on its array's first tick), 4uny J6pQ/SOL (8, adaptive, dynamic arrays; DCAL's pair), AfrD (96, 0.65%, dynamic
    arrays).
- **Exactness** (`clmm_exactness`): every snapshot in both directions at ≈45 log-spaced sizes plus the crate's own step
  ends ±1, exact in AND exact out; the output, the input debited and the whole post-swap pool state (sqrt price,
  tick, liquidity, fee growth, owed fees, the dynamic fee's or the oracle's variables) compared to the unit; byte
  mutations: Raydium fee_on 0/1/2, the dynamic fee cleared and set; Orca the adaptive state reset. Every refusal is
  lifted (the crate's maths run without it) and checked against the venue: a refusal where the lifted maths prices
  every venue-swapped size exactly is a FALSE REFUSAL and fails the suite like a mismatch.

  | Venue | exact (post-state exact) | both refuse | venue CU limit | necessary refusals | FALSE | MISMATCH |
  |---|---|---|---|---|---|---|
  | Raydium CLMM | 9,862 (9,862): snapshots 4,362 in / 802 out, mutations 2,292 / 2,406 | 169 | 56 | 1,105 (ASk8's 3% transfer fee) | **0** | **0** |
  | Orca Whirlpool | 6,198 (6,198): snapshots 4,833 / 878, mutations 237 / 250 | 138 | 2 | 0 | **0** | **0** |

- **Adversarial** (`clmm_adversarial`): the crate's step boundaries ±1 and ±2, Clock edges, 30 Raydium and 21 Orca
  state families on every pool: tick arrays missing, reversed, unrelated or only the first; no bitmap extension;
  limit orders (fresh, part-filled, both cohorts, tiny) injected on ticks; liquidity 0; fee rates 0 to the caps;
  protocol and fund rates; owed fees near u64::MAX; status bits; open_time; the dynamic fee at its cap, its reference
  far away, `va = v_ref = max_va`, the Clock past every period; Orca's adaptive control, reference above and below,
  the Clock before the reference, trading not enabled, the reward updated in the future, the needed arrays passed as
  supplemental, only the current array; Token-2022 mints paused, default-frozen (set, or the extension appended) and
  charging 1% (bps and cap set). 88,273 rows: Raydium 48,296 exact, 5,072 both refuse, 366 venue CU limit, 935
  necessary refusals; Orca 29,913 / 3,576 / 68 / 47; **0 FALSE REFUSAL, 0 MISMATCH**. The both-refuse rows by the
  crate's answer (the venue failing too): TooLarge 3,424, ZeroOut 1,196, NotOpen 521, Status 521, Raydium TickArrays
  550, BitmapExtension 58, Orca TickArrays 521, Timestamp 811, TradeNotEnabled 174, TransferFee 526, MintPaused
  115 + 58, MintFrozen 115 + 58.
- **Route** (`clmm_route`): Raydium DCAL ↔ Orca 4uny (the same pair, J6pQ/SOL) with 4uny's price moved ±60 and ±120
  ticks, `plan` in the bridge, every candidate executed leg by leg on the two programs: the realized profit equals the
  modeled one to the unit, is at least the profit at `e` and the best of a grid; a BASKET of the two directions picks
  the profitable pair and is NoProfit with `min_profit` above the plan.

### 6.4 CU measurement

- **Per mix.** Sizing CU = CU(route with SELF_SIZE, SHADOW) − CU(the same route unsized at `x = e`). SHADOW executes
  the same `e`, so the CPIs are identical.
- **Breakdown.** With the `trace` feature, counters attribute evaluations and bins. The `sol_remaining_compute_units`
  feature is enabled in LiteSVM **for measurement builds only**.
- **Report.** A table per venue mix and per bins touched, replacing the estimates in §4.7.
- **Regression.** `sbf-check/cu-runner` exits nonzero if any route measures above the static bound of its own block
  (`cu_bound`), above its recorded budget by more than 10%, or if the few-bin 3-pair DLMM basket exceeds 60k. It runs
  each route with budgets from the cap and (`TIGHT=1`) from the tight rule (§4.3).

### 6.5 Upgrade watch

The harness job re-reads each venue's programdata slot (and the sha256 of a fresh dump) daily. On a change:
1. re-dump the program;
2. rerun §6.3;
3. alert.

The engine treats a changed slot as "sizing off for that kind" until the run passes. This is the sizing-specific form
of redesign §3.8's "programdata change → venue to shadow".

### 6.6 Production rollout gates (per kind)

1. **Harness green.** 100% exact on every swap run and mutation for the kind; route-level assertions 1-7 pass.
2. **SHADOW on live sends.**
   - AXZ1 is logged and `e` is executed. On **every** landed route (target ≥ 300 per kind), AXZ1 `profit_e` must
     equal AXS1 `quote_delta`, and `y_e` must equal leg 0's AXL1 `delivered`.
   - The recorder also reports the median and p90 uplift, `modeled_profit − modeled_profit_e`. That is the evidence
     for or against enabling (docs-review open question 1).
3. **Sized, capped.**
   - `amount_in` (the cap) = min(1 SOL in Stage 2, the configured cap).
   - The SHADOW checks continue, with the realized amount equal to `plan.amount`.
   - Any mismatch disables the kind automatically, through a config kill switch per kind.
4. **EARLY_ABORT** only after 3 has run cleanly. **BASKET** only after SELF_SIZE has passed for every kind it uses,
   and after ALT coverage (§4.6).

---

## 7. Open points to pin in the harness

1. **PumpSwap buy_exact_quote_in debit when `eff + fees(eff) ≠ x`.** Settled (venue-harness pins.rs): the program
   debits `min(x, eff0 + fees(eff0))`; the evaluator now does too (REVIEW.md F2).
2. **PumpSwap cashback coins and mayhem pools.** Mayhem settled (WP-16 review): the market cap is on the fixed 1e15
   supply, pinned on the dumped binary; mayhem pools are priced. Cashback is still open: find the cashback bps source
   (GlobalConfig, FeeConfig or event-only), and the engine's leg must pass the cashback accounts (it cannot execute a
   cashback coin today). Aborted until both are done.
3. **DLMM drain test.** SDK 0.12 uses `rem ≥ need` (fee charged first, on the whole input). The older program used
   `in > max_in + max_fee`. These are equivalent for the user's amounts, including at equality (§2.7). The open
   question is the layered limit-order fill: whether each layer's `need` is rounded up separately on chain, as in SDK
   0.12. Pin it with the layer-edge sizes of §6.3 on the dumped binary.
4. **DLMM bin arrays.** Settled (pins.rs): the program walks the passed arrays with a forward cursor, in walk order,
   skipping arrays it does not need; the walker follows the bitmap like the program (adversarial.rs, both array
   orders).
5. **DLMM version gates.** Collect the pair and bin-array version bytes of older pools, and widen the accepted set
   after harness runs.
6. **PumpSwap bytes 270..301.** Settled but for 287..301: byte 270 is `is_holder_reward: bool` (the public IDL of
   2026-09-12; priced, a non-bool byte is `Layout`), `held_0`/`held_1` (u64 @271, @279) bound a sell's payout (REVIEW.md
   F1), and shorter pools are read as the program reads them (§2.1, pinned per read group). Bytes 287..301 are still
   unidentified (in no IDL; zero on every pool seen; a 300-byte pool holds 13 of them) and refused when set. On the
   dumped binary a pool with them set swaps like one without, so the refusal is a policy (an unknown field turns sizing
   off) that costs no live pool today.
7. **DAMM v2 rate limiter.** Settled: the limited direction cannot execute through the engine's leg (6049 without the
   instructions sysvar), so the leg is refused (§2.5). Sizing it would need the sysvar in the leg first.
8. **Account-lock limit.** Confirm the cluster's `max_tx_account_locks` before planning baskets above 64 unique keys.
9. **Paused and default-frozen mints for kinds 1-6.** Kinds 7 and 8 refuse a paused (Pausable) or DefaultAccountState
   Frozen Token-2022 mint (§2.0); the older kinds do not check them in the crate, so such a route would revert on chain
   instead of being skipped. **Closed in the engine (WP-21):** its shared mint checks (`src/quote.rs` `mints_ok`, and
   PumpSwap's base mint) apply `token::mint_blocked` to every Token-2022 mint of a kind 1-6 pool and refuse the leg
   (`mint_paused`, `mint_frozen`; test `older_venues_refuse_paused_and_default_frozen_mints`). Moving the check into
   the crate's parses still needs the harness's Token-2022 states run on them.
10. **A transfer-fee rate with `maximum_fee = 0`.** `token::scan_extensions` refuses any nonzero rate, although
    Token-2022 caps the fee at `maximum_fee` and so charges nothing there. Conservative (never a wrong price); exempting
    it needs the epoch rule (the newer fee applies from its epoch) pinned in the harness first.
11. **On-chain sizing of kinds 7 and 8.** Their `budget` costs are estimates and an exact evaluation has no resumable
    state, so the static bound is large (§4.7). Before arbx-exec builds the features: per-step resumable states, then
    the sbf-check measurements and the cu-runner gate.
12. **Orca's U256 division.** The deployed 0.9.0 binary panics where `U256Muldiv::div`'s add-back reads past the top
    word, and the port fails there too; upstream fixed it in 4aac511 (2026-10-06) after this deploy. When Orca deploys
    a new binary the upgrade watch (§6.5) must stop the kind until the port follows it and the harness passes again.
    The port "fails" as a refusal, never a panic: `muldiv_div` answers None there (and on a zero divisor), which a swap
    step reads as TooLarge. The engine's test `orca_u256_division_refuses_never_panics` runs the deployed division
    (`muldiv_div_as_deployed`) on 200,000 random and edge-limbed operands against a 256-bit reference: equal wherever it
    answers, None otherwise (722 cases). The engine's `venue_upgraded` refusal is the upgrade watch (WP-21).

---

## 8. Research artefacts (all under `program/arbx-sizing/research/`)

| File | What |
|---|---|
| `solrpc.py` | read-only mainnet RPC (rate-limited, cached in `program/venue-harness/fixtures/rpc-cache/`), base58, PDA derivation |
| `check_layouts.py` → `layout-check.txt` | owners, sizes, discriminators and every offset of §2 on 11 pools, configs, bin arrays and mints at slot 453,207,209: 0 failures |
| `pump_events.py`, `pump_events_check.py` → `pump-events-check.txt` | PumpSwap Buy/SellEvent decoder and the field-by-field check of §2.1 on 300 signatures: 112/112 events exact |
| `math_checks.py` → `math-checks.txt` | brute-force checks: DLMM drain-test equivalence (1.2M cases, 0 differences), DAMM v2 exact capacity closed forms (60k, 0 failures), CPMM-CPMM closed-form integer loss (≤ 0.31 × 2ε) |
| `cubench/` | SBF CU micro-benchmark (program + LiteSVM runner) behind §4.7 |

---

## 9. Engine integration of the CLMM kinds (WP-21: what it needs)

**Status (lane/wp21, 2026-10-06):** done in the engine as listed below (docs/PLAN-ADDENDUM.md WP-21 "Status, phase A").
The deployed nexus-v2 routes both venues' `swap_v2` legs with no upgrade (its allowlist holds both programs; engine-built
routes land through it in LiteSVM, program/venue-harness `tests/arbx_bundle_clmm.rs`).

The crate side is done and proven (§2.8, §2.9, §6.3). Nothing in the engine or arbx-exec uses kinds 7 and 8 yet, and a
default build of either is unchanged. Integrating them into the engine needs the following, per venue. On-chain sizing
(arbx-exec) comes later still (§4.7, §7 item 11): the engine prices and sends these legs exact in at its own amount,
like any unsized leg.

### 9.0 Both venues

1. **The dependency.** `arbx`'s `arbx-sizing` dependency gains `features = ["clmm"]` (or one venue's). That adds the
   `Abort::Clmm` / `Abort::Whirl`, `AnyLeg::RayClmm` / `AnyLeg::Whirl` and `LegModel` variants, so `src/quote.rs`
   needs their arms: `abort_reason` and `REASONS` with one reason (and its counters, `every_reason_has_its_counter`)
   per refusal — `sz_clmm_status`, `sz_clmm_not_open`, `sz_clmm_fee`, `sz_clmm_bitmap_extension`,
   `sz_clmm_no_liquidity`, `sz_clmm_tick_arrays`, `sz_clmm_price_limit`, `sz_clmm_state`, `sz_clmm_mint_paused`,
   `sz_clmm_mint_frozen`, `sz_whirl_trade_not_enabled`, `sz_whirl_timestamp`, `sz_whirl_tick_arrays`,
   `sz_whirl_price_limit`, `sz_whirl_state`, `sz_whirl_mint_paused`, `sz_whirl_mint_frozen` — and `Leg::why` maps
   `Budget` as for DLMM. arbx-exec keeps the default features.
2. **Venue and pool metadata.** `src/venues::Venue` gains `RayClmm` and `Whirlpool` (`engine.rs::amm_programs`
   already names both programs, to recognise rival arbitrage); `PoolMeta` carries the tick spacing, Raydium's
   AmmConfig and observation keys and its extension PDA, and Orca's oracle PDA. Pool discovery lists the pools
   (WSOL-quoted first; `docs/research/venue-census.md`: Whirlpool alone +5.0 points of rival arbs and +10.3 of their
   gross, Raydium CLMM +4.1 / +3.4, both together +19.2 points of arbs).
3. **State following.** Per pool: the pool, the vaults, its Token-2022 mints (scanned at every change: §2.0's transfer
   fee, hook, Pausable, DefaultAccountState), Raydium's AmmConfig and its extension (which may not exist), Orca's oracle
   (which may not exist), and the tick arrays around the price in both directions (Raydium: the current array and the
   next initialized ones by the bitmaps, enough for a swap at the cap, ≥ 3 each way; Orca: the current array and the
   next two each way, as PDAs, initialized or not). The set moves with the price: re-derive it when the current
   array changes. An Orca dynamic tick array changes length as ticks are initialized or freed: follow it by key, never
   by length. The stream must follow every account a quote reads (`the_stream_follows_every_account_a_quote_reads`).
4. **The Clock.** Both read it: Raydium for open_time and the dynamic fee's reference, Orca for the reward and oracle
   stamps and the adaptive fee's reference. Quote with the Clock of the slot being targeted, never older than the
   pool's own stamps: Orca refuses (Timestamp) a Clock before `reward_last_updated_timestamp` or the oracle's last
   update, and both fees depend on the elapsed time.
5. **Quote** (`src/quote.rs::leg`). Raydium: `raydium_clmm::parse(pool, cfg, remaining, vault0, vault1, zfo, clock)`
   with `remaining` = exactly the accounts the leg will pass (route), or every followed array in walk order (a third
   party's swap). Orca: `orca_whirlpool::parse(pool, oracle, arrays, vault_a, vault_b, a_to_b, clock)` with
   `TickArrayIn { start, data: None }` for a followed PDA that does not exist. `fills` gives the walk: `steps`
   (`max_bins`, the CU), `crossed` (the CU table's bucket), the arrays read (the builder's list) and `post` (the
   accuracy monitor). `cap_in` bisects 64 exact quotes: the sizing ladder should use `quote` directly.
   `quote_exact_out` gives the input of a wanted output (hints), as PumpSwap's does.
6. **CU** (`src/cu_table.rs`): key `<venue>|<crossed bucket>` like DLMM's bins; the fallback `Venue::leg_cu` from the
   harness's bounds on every real swap: Raydium 64k + 10k per step, Orca 48k + 10k per step (`steps` from `fills`; a
   dynamic or adaptive fee adds sub-steps without crossings, so bucket by steps, not by crossings alone).
7. **The accuracy monitor** (`src/accuracy.rs`): `PostSwap` against the next observed pool state — Raydium sqrt
   price, tick, liquidity, the fee token's fee growth, protocol and fund fees owed, the dynamic fee's variables; Orca
   sqrt price, tick, liquidity, the input token's fee growth, protocol fee owed, the oracle's variables.
8. **Parity in CI.** Copy `fixtures/pools-clmm` into `testdata/venue-parity` with their real swaps (`capture_post`
   over `Fixtures::load_all`) and extend `tools/ci-venue-parity.sh` steps 3 and 4, so the engine's quotes of these
   venues are checked against the real programs as for the others.
9. **Rollout.** A config switch per venue, off by default: quote only first (the accuracy monitor on third-party
   swaps), then send.

### 9.1 Raydium CLMM leg: `swap_v2` (amount at data offset 8)

| # | Account | Notes |
|---|---|---|
| 0 | payer | signer |
| 1 | amm_config | pool @9 |
| 2 | pool_state | writable |
| 3, 4 | input / output token account | the payer's ATAs; writable |
| 5, 6 | input / output vault | the pool's vaults of the direction; writable |
| 7 | observation_state | pool @201; writable |
| 8, 9, 10 | Token program, Token-2022 program, Memo program | |
| 11, 12 | input mint, output mint | |
| 13.. | the TickArrayBitmapExtension PDA["pool_tick_array_bitmap_extension", pool] when the account exists, then the tick arrays PDA["tick_array", pool, start (i32 big-endian)] in walk order | writable; at most 7 in all (the descriptor's count) |

Data (41 B): `swap_v2` `2b04ed0b1ac91e62`, amount u64, other_amount_threshold u64 (1), sqrt_price_limit_x64 u128 (0:
none, so a partial fill fails), is_base_input u8 (1). 13 + 1..=7 accounts fit the v2 layout's 63 per leg.

- **Tick arrays ahead.** The first array the swap reads (`ClmmWalk.arrays[0]`: the current tick's array when
  initialized, else the next initialized one in the direction), then every array the walk of a quote **at the cap**
  reads (`ClmmWalk.arrays` of `fills(cap)`), then one more initialized array; never an uninitialized one (the program
  jumps over them by the bitmap). With the extension that is at most 6 arrays. A walk at the cap needing more ends the
  leg's domain there (TooLarge past it), so the engine's sizing stops there.
- **The extension.** Needed when the current tick, or any array the walk reaches or empties, lies beyond ±ts·60·512
  ticks (tick spacings below 15): pass it whenever it exists (one account; the program and the crate classify by
  length).
- **CU.** ≈41.5k + ≈9.1k per tick crossed + ≈8.5k per other step; every real swap is within 64k + 10k per step; the
  1.4M limit falls at ≈147 steps.
- **Refusals** (each fails at every size; skip the pool with the reason): §2.8's list — status, not open, the fee rate,
  the extension missing, no liquidity in the direction, the first array not passed, the price at its limit, an
  inconsistent state, a paused or default-frozen mint, a transfer fee or hook, an unknown layout.

### 9.2 Orca Whirlpool leg: `swap_v2` (amount at data offset 8)

| # | Account | Notes |
|---|---|---|
| 0, 1 | token program of mint a, of mint b | |
| 2 | Memo program | |
| 3 | token_authority (payer) | signer |
| 4 | whirlpool | writable |
| 5, 6 | mint a, mint b | the POOL's order (a, b), whatever the direction |
| 7 | token_owner_account_a (the payer's ATA of mint a) | writable |
| 8 | token_vault_a | writable |
| 9 | token_owner_account_b | writable |
| 10 | token_vault_b | writable |
| 11, 12, 13 | tick_array_0..2: PDA["tick_array", whirlpool, start as a decimal string] of `needed_starts(tick, ts, a_to_b)`, initialized or not; the last repeated where fewer than 3 are valid | writable |
| 14 | oracle PDA["oracle", whirlpool], initialized or not | writable |
| 15.. | supplemental tick arrays | none needed |

Data (43 B): `swap_v2` `2b04ed0b1ac91e62`, amount u64, other_amount_threshold u64 (1), sqrt_price_limit u128 (0: the
direction's limit), amount_specified_is_input u8 (1), a_to_b u8, remaining_accounts_info Option (0: None). 15 accounts.

- **Tick arrays ahead.** Exactly the program's sequence: the current array and the next two in the direction (b→a one
  later near the array's end), whatever the size. No swap reads past them, so the leg's domain ends at the third
  array's end — 264 tick spacings, ≈2.7% of price at tick spacing 1 — and a cap beyond that is TooLarge there.
- **CU.** ≈28-30k + ≈7.0k per tick crossed + ≈8.6k per other step (adaptive sub-steps); every real swap is within 48k
  + 10k per step; the 1.4M limit falls at ≈190 steps.
- **Refusals:** §2.9's list — trading not enabled yet, a Clock before the pool's or the oracle's stamps, none of the
  needed arrays passed, the price at its limit, an inconsistent state, a paused or default-frozen mint, a transfer fee
  or hook, an unknown layout.

### 9.3 Next: the CLMM forks

PancakeSwap v3 and Byreal share this maths (a Uniswap v3 / Raydium CLMM lineage). Each needs its own dump, layout
check and harness run on its deployed binary before any of this code prices it; nothing here is assumed to carry over
until the harness shows it.

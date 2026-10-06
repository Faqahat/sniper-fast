# venue-harness

The exactness oracle for `program/arbx-sizing` (DESIGN.md §6.3). The venue programs are the real mainnet ELFs, dumped
read-only into `fixtures/programs`. They run in LiteSVM 0.17 (mainnet feature set) on mainnet account snapshots
stored in `fixtures/pools` (the engine's venues) and `fixtures/pools-clmm` (Raydium CLMM and Orca Whirlpool,
PLAN-ADDENDUM WP-21: priced by arbx-sizing, not traded by the engine yet).

Each swap is a real venue instruction, built byte for byte the way the engine builds it (`src/build.rs::leg`; for the
two CLMM venues, the `swap_v2` layouts DESIGN.md §9 specifies for the engine). A funded test wallet executes it, and
the harness records the exact output and input deltas plus the venue's CU.

## Commands

```
cargo run --release --bin fetch-fixtures              # programs + pools in fixtures/pool-list.json and pool-list-clmm.json (cached: skips what exists)
cargo run --release --bin fetch-fixtures -- --refresh # re-snapshot everything (read-only RPC, <= 2.5 req/s)
cargo run --release --bin fetch-fixtures -- --check   # upgrade watch: programdata last-deploy slot vs MANIFEST.json
cargo run --release --bin venue-swap -- list
cargo run --release --bin venue-swap -- 6D4EWF22 1 1000000 50000000 -v   # pool prefix, 1 = token0 in, sizes
cargo test --release -- --nocapture                   # everything below
VENUE_HARNESS_BRIDGE_TARGET=/scratch/dir cargo test --release   # where the sizing-bridge builds go (default: $CARGO_TARGET_DIR, else target/)
cargo run --release --bin capture_post > ../../testdata/venue-parity/real-swaps.json   # real swaps and their post-states
```

`capture_post` (PLAN-ADDENDUM WP-16) runs every fixture pool, and the byte mutations `tests/exactness.rs` uses, at the
14-size ladder of `tests/swaps.rs` in both directions (DLMM with the engine's 5 bin arrays), and records each swap's
output, debit and every u64 word it changed in the snapshot's accounts. The engine's tests read that file and a copy of
`fixtures/pools` from `testdata/venue-parity/` (I-11): its quotes and its accuracy monitor's post-states are checked
against these real swaps.

`--rpc <url>` points the fetcher at another read-only endpoint. HTTP goes through the system `curl`, so the crate has
no TLS stack.

## Tests

| Test | What it proves |
|---|---|
| `tests/swaps.rs` | Every fixture pool swaps in both directions at 14 log-spaced sizes; at least 10 must succeed per direction (a PumpSwap cashback coin must fail every one: the engine's leg cannot execute it, `venues::engine_leg_executes`). Output is monotone and the input debit is exact. Writes `results/swap-runs.json`. Also fits DLMM CU against bins crossed |
| `tests/pins.rs` | DESIGN §7 pins and the closed-form formulas, settled on the real binaries (below), PumpSwap's exact-out `buy` included |
| `tests/api.rs` | `venue_swap_output`, sessions (state carried between swaps), the clock-mutation hook, CU log parsing |
| `tests/exactness.rs` | The arbx-sizing comparison (below) |
| `tests/adversarial.rs` | The same comparison at the crate's own boundary sizes ±1, ±2 (exact capacities included), under Clock variations and 50+ state mutations (below) |
| `tests/route.rs` | `plan` on real legs, each planned size executed on the real programs: HOTBOT routes in both directions and a 2-pair BASKET (below) |
| `tests/clmm_exactness.rs` | WP-21: the same comparison for Raydium CLMM and Orca Whirlpool (kinds 7, 8), exact in and exact out, amounts and the whole post-swap pool state (below) |
| `tests/clmm_adversarial.rs` | WP-21: their step boundaries ±1, ±2, Clock edges, 51 state families and Token-2022 mint states, every refusal checked against the venue (below) |
| `tests/clmm_route.rs` | WP-21: `plan` over Raydium DCAL ↔ Orca 4uny (the same pair) executed on both programs, and a 2-pair BASKET (below) |

## API

```rust
let fx = Fixtures::load()?;                                     // fixtures/programs + fixtures/pools
let fx = Fixtures::load_clmm()?;                                // fixtures/programs + fixtures/pools-clmm (load_all: both pool sets)
let (out, cu) = venue_swap_output(&fx, &pool, Dir::ZeroForOne, amount_in)?;   // Err(SwapOutcome) when the venue fails
let h = Harness::new(&fx, &pool)?;                              // or Harness::with_patches(&fx, &pool, &[Patch::new(key, off, bytes)])
let o: SwapOutcome = h.swap(dir, x);                            // ok, amount_out, spent, cu_venue, cu_tx, err, logs, events
let o = h.swap_opts(dir, x, &BuildOpts { dlmm_arrays: Some(vec![-8, -9]), ..Default::default() });
let o = h.swap_opts(Dir::OneForZero, base_out, &BuildOpts { exact_out: true, ..Default::default() });   // PumpSwap `buy`
let h = Harness::with_patches(&fx, &pool, &[Patch::resize(pool, 300)])?;   // an account cut (or zero-extended) to 300 bytes
let o = h.swap_with(dir, x, &BuildOpts::default(), |svm| svm.set_sysvar(&clock));   // mutate state first
let o = h.swap_opts(dir, x, &BuildOpts { tick_arrays: Some(vec![-21120, -21180]), clmm_ext: false, ..Default::default() });
                                                                // CLMM: the tick arrays passed, the extension left out
let mut s = h.session(); s.swap(..); s.swap(..);                // swaps that see each other's effects
```

`Dir` is in the pool's own token order: PumpSwap base/quote (ZeroForOne = `sell`, OneForZero = `buy_exact_quote_in`),
CPMM mint0/mint1, AMM v4 coin/pc, DLMM x/y, DAMM v2 a/b, Raydium CLMM token0/token1, Orca Whirlpool a/b.

Each swap runs in a clone of the base state (snapshot + wallet), so swaps are independent and deterministic. About
600 swaps run in 0.3 s.

## Fixtures

- **`fixtures/programs/<id>.so` + `MANIFEST.json`:** PumpSwap, the pump fee program, Raydium CPMM and AMM v4, DLMM,
  DAMM v2, Raydium CLMM (ed1eb41, deployed at slot 451,479,902), Orca Whirlpool (0.9.0, slot 440,170,207), and
  mainnet's SPL Token (p-token), Token-2022 and ATA.
  - Each ELF is cut at its own extent. Upgradeable programs carry zero padding up to their max length; the manifest
    keeps the on-chain size and sha256 alongside.
  - Set `VENUE_HARNESS_LITESVM_SPL=1` to use LiteSVM's bundled token programs instead of the mainnet dumps.
- **`fixtures/pools/<venue>-<pool>.json`:** one snapshot per pool.
  - One `getMultipleAccounts` call returns every account that both swap directions name, plus the Clock and Rent
    sysvars, so all of it is from one slot.
  - It also holds the mints, PumpSwap's GlobalConfig and FeeConfig, and DLMM bin arrays (the active array ±3 plus the
    first 4 arrays with liquidity on each side) along with the bitmap extension.
  - User-derived accounts are not stored: the loader creates them with the real ATA program.
- **`fixtures/pool-list.json`:** the pools to fetch.
  - 12 PumpSwap, 4 DLMM (function_type 2 and 0, collect_fee_mode 0 and 1), 9 DAMM v2 (base-fee modes 0, 1, 3 and 4;
    collect_fee_mode 0, 1 and 2; Token-2022 mints), 3 CPMM and 3 AMM v4.
  - The PumpSwap pools cover the classes of the WP-16 review's mainnet census (docs/reviews/WP-16-review.md): 301-byte
    pools (GLL3, 6ejg with an exotic quote and creator_fee_bps 200, CyJw with held amounts), 300-byte pools (9qKx, the
    largest at 7,134 SOL; FKfR; EBNU, also a holder-reward pool), holder-reward pools (byte 270 = 1: 5PGh and 3KFC with a
    negative virtual reserve, 8ewu with a positive one), a mayhem pool (GxqG), a cashback coin (98ew, which the
    engine's leg cannot execute) and a 287-byte dust pool with a non-SOL quote (DDGN).
  - Edit the list and rerun the fetcher to add pools. A pool that cannot swap is reported and skipped.
- **`fixtures/pool-list-clmm.json` → `fixtures/pools-clmm/`** (WP-21): 10 Raydium CLMM and 10 Orca Whirlpool pools,
  snapshotted at slots 453,942,354-440 (2026-10-06) with every account `swap_v2` takes, the mints, the AmmConfig, the
  bitmap extension, the oracle, and the tick arrays around the price (Raydium: the current one and the first 5
  initialized ones each way; Orca: the current one ±3, fixed or dynamic). They span the fee tiers (0.01% to 3%), tick
  spacings 1 to 32,896 (a splash pool), dynamic and adaptive fees, fee_on 0/1/2, real limit orders (3ucN, 2uoK), a
  pool beyond the default bitmap (DCAL), current ticks at array boundaries, uninitialized arrays in a swap's sequence
  (G1vH) and Token-2022 mints (a 3% transfer fee on ASk8, Pausable and DefaultAccountState on 7tJV, PYUSD on 5Kqo).
- **`fixtures/rpc-cache/`:** the arbx-sizing research cache. It is not used by this crate.

**Mainnet rent is 5,080 lamports per byte.** LiteSVM's default is 6,960. Accounts created on mainnet since the change
hold less than LiteSVM's minimum, and Anchor's rent-exempt constraint then refuses them: PumpSwap 6ejg failed with 2005
until the snapshot's Rent was loaded.

## Pins settled on the real binaries (`tests/pins.rs`)

- **DLMM bin arrays (§7.4).**
  - The program walks the passed arrays with a forward cursor, skipping any array it does not need next. The active
    bin's array must be present.
  - The arrays a swap needs must come in walk order: reversed or swapped lists fail with 3005 AccountNotEnoughKeys.
  - Extra arrays are skipped (a duplicate, the other side's neighbour first, a far one). The output is the same and
    each extra costs about 300-900 CU.
- **PumpSwap `buy_exact_quote_in` debit (§7.1).** The debit is `min(x, eff0 + fees(eff0))`, not always `x`.
  - On an overrun (`eff0 + fees(eff0) > x`), the program lowers `eff` but keeps `fees(eff0)`, so it debits exactly `x`.
  - Otherwise it debits `eff0 + fees(eff0)`, which can be below `x`. This happened 9 times in 16,200 buys, for example
    6ejg at `x = 10,000,051`, which debits 10,000,050.
  - Base out is DESIGN's `floor(B·(eff−1)/(Qv+eff−1))` in every case.
- **PumpSwap sell.** DESIGN §2.1 is exact. Dust sells fail with 6004 or 6023 when `q − fees < 1`.
- **PumpSwap exact-out `buy` (WP-16 review F6).** The base out is exactly the amount asked for and the debit is
  `q + ⌈q·lp/1e4⌉ + ⌈q·pr/1e4⌉ + ⌈q·cr/1e4⌉` with `q = ⌈Qv·out/(B − out)⌉`: 11,477 buys exact to the unit; 0 fails 6001,
  the whole base reserve or a quote past u64 fails too.
- **PumpSwap pool lengths and flags (WP-16 review F1, F2).** Below 211 bytes the program fails InvalidAccountData; from
  211 it reads each trailing group only when whole (adversarial "pool cut to L bytes"); byte 270 is `is_holder_reward`
  (0 and 1 swap alike; another byte fails BorshIoError); a mayhem pool's market cap is on the fixed 1e15 supply and its
  events carry no buyback.
- **CPMM and AMM v4.** DESIGN §2.2 and §2.3 are exact to the unit (500 swaps). The Token-2022 transfer-fee pool is
  excluded.

## Exactness against arbx-sizing (`tests/exactness.rs`)

`sizing-bridge/` is a separate crate with a path dependency on `../../arbx-sizing`. It is not part of this crate's
dependency graph, so the harness builds whatever state the sizing crate is in.

**What the test does:**
1. Skips with a message if the sizing crate is missing or the bridge does not build. Set
   `VENUE_HARNESS_REQUIRE_SIZING=1` to fail instead. Set `VENUE_HARNESS_SIZING_DIR` to point at another copy.
2. Otherwise builds the bridge (`tests/common`) in `$VENUE_HARNESS_BRIDGE_TARGET/sizing-bridge`, else
   `$CARGO_TARGET_DIR/sizing-bridge`, else `target/sizing-bridge` (WP-16 review F9: with a target dir given nothing is
   built inside the repository).
3. Sends it every leg as the engine lays it out (kind, dir, bump, bin-array count, the DLMM walk budget `max_bins`
   (255 here), the leg's account list, the Clock).
4. The bridge resolves state accounts through `layout::check_positions` and calls `AnyLeg::parse` and `quote`.
5. The test compares each quote with the real swap.

**Cases:**
- every snapshot;
- byte-mutated variants:
  - CPMM `enable_creator_fee` with `creator_fee_on` set to 0, 1 and 2;
  - AMM v4 `need_take_pnl`;
  - DLMM `collect_fee_mode` flipped and volatility reset;
  - PumpSwap virtual reserve and `creator_fee_bps` cleared;
  - DAMM v2 `collect_fee_mode` flipped.
- Sizes: about 45 per leg, plus 1,000 consecutive sizes for PumpSwap buys.
- PumpSwap's exact-out `buy` (WP-16 review F6): each pool the engine's leg executes also gets a buy leg quoted by
  `PumpLeg::quote_exact_out` (the bridge's `"exact_out": true`), the amounts being the base out (about 45, plus 500
  consecutive ones), and swapped with `BuildOpts::exact_out`.

**Verdicts:**
- **exact**;
- **both-refuse**: TooLarge or ZeroOut, and the venue fails or pays 0;
- **budget**: the crate says `Budget` (a DLMM swap past the leg's walk budget: not evaluated). The bridge also sends
  the same quote without a budget, which must pass the two rules above, and the bins the swap reads, which must exceed
  the budget;
- **venue CU limit**: the venue ran out of the 1.4M transaction CU (DLMM swaps reading ≳246 bins); not a
  maths verdict;
- **refusals** (an `Abort` at parse or quote; WP-16 review F3): every refused size is swapped on the venue too, and
  counted per reason:
  - **both refuse**: the venue fails or pays nothing as well;
  - **necessary refusal**: the venue swaps, but the crate's maths with the refused state taken out on the crate's side
    only (`tests/common` `lift`: a Token-2022 transfer fee zeroed in the mint) are off at one of the leg's swapped
    sizes at least, so pricing the state would misprice it (the transfer-fee pools Hmx1 and 2cUM);
  - **FALSE REFUSAL**: the venue swaps and the lifted maths are exact at every swapped size, or the refusal has no lift.
    It fails the test like a mismatch;
- **MISMATCH**: fails the test. A TooLarge where the venue still swaps is a MISMATCH (TooLarge claims a capacity).

`results/exactness.json` holds every row.

## Adversarial states and boundary sizes (`tests/adversarial.rs`)

Same bridge, oracle and verdicts, with the bridge's probe mode: every DLMM layer edge and bin drain threshold along
the crate's walk, the exact capacities (`cap_in`: PumpSwap sell, DLMM, DAMM v2), and fee-ceil residues, each ±1, ±2.
States: DLMM Clock deltas (0, filter−1, filter, decay−1, decay, 10·decay), limit orders (both layers, both ask sides,
function types 0/1/2, reward mints), volatility extremes, the pair's `min/max_bin_id` one bin from active, a bitmap gap
and an empty active array (bitmap-order and engine-order array lists); PumpSwap V = −Q/2 and 50·Q, coin_creator 0,
creator_fee_bps 300 and 1000, market-cap tiers, the held quote amounts (u64 @271, @279: six splits up to the whole
vault, and above it), `is_holder_reward` = 1 (byte 270), the flag bytes 243, 244, 269 and 270 set to 2 (no Borsh bool:
the program fails, the crate says Layout), `is_mayhem_mode` = 1 (with its supply ×60: the market cap on 1e15),
`is_cashback_coin` = 1 (the venue refuses the engine's leg), and the pool cut at every read-group boundary ±1 from 210
to 300 bytes with the held amounts made binding (WP-16 review F1: the program reads a pool from 211 bytes, each
trailing group only when whole); CPMM owed fees, fee rates, creator fee sides; AMM v4 fees and status 7; DAMM v2 Clock
and scheduler edges, a narrow price range, the fee cap, the rate limiter in force (the limited direction must be
refused) and zero liquidity. Every refusal is checked against the venue as in `tests/exactness.rs`.
`results/adversarial.json` (≈30 MB, gitignored) holds every row.

## Route level (`tests/route.rs`)

The bridge's plan mode runs `arbx_sizing::plan` over engine-layout legs with the engine's DLMM budget rule (`max_bins`
"auto": the bins at the cap). Each planned size, `e` and a 96-point grid are then executed leg by leg on the dumped
programs (leg 1 spends what leg 0 delivered):
- HOTBOT GLL3 ↔ 6D4E in both directions at six gaps: realized == modeled to the unit at the plan and at `e`, plan ≥
  `e`, plan ≥ the grid's best − 2ε, and `E(e)` evaluated whenever the venue fills `e`;
- a BASKET of both directions (legs GLL3 buy, 6D4E sell, 6D4E buy, GLL3 sell; pairs (0,1), (2,3)) at four gaps: the
  profitable pair is chosen, realizes its modeled profit, beats pair 0 at `e` and each pair at its own planned size;
  `min_profit` above the plan gives NoProfit. (The third HOTBOT pool C9xc has no liquidity any more.)

## Concentrated liquidity: Raydium CLMM and Orca Whirlpool (PLAN-ADDENDUM WP-21)

The builders (`src/venues.rs`) emit each venue's `swap_v2`, the layouts DESIGN.md §9 specifies for the engine:
- **Raydium CLMM:** payer, amm_config, pool, user in/out, vault in/out, observation, Token, Token-2022, Memo, mint in,
  mint out; then the TickArrayBitmapExtension (when it exists; `clmm_ext: false` leaves it out) and the tick arrays in
  walk order (by default the current array and the snapshot's initialized arrays onward; `tick_arrays` overrides);
  data amount, threshold, `sqrt_price_limit` (0: none), is_base_input.
- **Orca Whirlpool:** token programs a/b, Memo, the authority, whirlpool, mints a/b, owner account a, vault a, owner
  account b, vault b, the 3 tick arrays of the program's own sequence (initialized or not), the oracle PDA; tick
  arrays past the third go as supplemental (`remaining_accounts_info` slice type 6); data amount, threshold,
  `sqrt_price_limit`, amount_specified_is_input, a_to_b.

`exact_out: true` swaps exact out on both (the bridge then calls `quote_exact_out`).

**`tests/clmm_exactness.rs`:** every snapshot in both directions, ≈45 log-spaced sizes plus the crate's step ends ±1,
exact in and exact out, and byte mutations (Raydium fee_on 0/1/2, the dynamic fee cleared and set; Orca the adaptive
state reset). The bridge returns the crate's walk (`clmm`: steps, ticks crossed, the arrays read, the post-swap pool),
and the test compares the output, the debit and the post-swap pool (sqrt price, tick, liquidity, fee growth, owed fees,
the dynamic fee's or the oracle's variables) with the venue's accounts after the swap. Verdicts as in
`tests/exactness.rs`, refusals lifted the same way (a Token-2022 transfer fee zeroed). Results (2026-10-06):

| Venue | exact (post-state exact) | both refuse | venue CU limit | necessary refusals | FALSE | MISMATCH |
|---|---|---|---|---|---|---|
| Raydium CLMM | 9,862 (9,862) | 169 | 56 | 1,105 (ASk8's 3% transfer fee) | 0 | 0 |
| Orca Whirlpool | 6,198 (6,198) | 138 | 2 | 0 | 0 | 0 |

**`tests/clmm_adversarial.rs`:** the bridge's probe mode (each step's end, `cap_in`, fee residues, ±1 and ±2) on 30
Raydium and 21 Orca state families per pool — tick arrays missing, reversed, unrelated or only the first; no bitmap
extension; limit orders injected (fresh, part-filled, both cohorts, tiny); liquidity 0; fee, protocol and fund rates;
owed fees near u64::MAX; status bits; open_time; the dynamic fee's cap, reference and Clock edges; Orca's adaptive
control, reference above and below, the Clock before its reference, trading not enabled, the reward updated in the
future, the needed arrays as supplemental, only the current array — and Token-2022 mint states (paused, default
frozen, set or with the extension appended; a 1% transfer fee with its cap lifted). 88,273 rows: Raydium 48,296 exact,
5,072 both refuse, 366 venue CU limit, 935 necessary refusals; Orca 29,913 / 3,576 / 68 / 47; 0 FALSE REFUSAL, 0
MISMATCH. `results/clmm-exactness.json` (≈22 MB) and `results/clmm-adversarial.json` (≈80 MB) hold every row; both are
gitignored.

**`tests/clmm_route.rs`:** Raydium DCAL and Orca 4uny trade the same pair (J6pQ/SOL). With 4uny's price moved by ±60 and
±120 ticks, `plan` runs in the bridge and every planned size is executed leg by leg on the two programs (one Clock, the
later snapshot's, for both: Orca refuses a Clock before its own stamps): realized == modeled to the unit, ≥ the profit
at `e`, ≥ the best of a grid; a BASKET of both directions picks the profitable pair and is NoProfit with `min_profit`
above the plan.

**The venues' CU** (every exact swap above): Raydium CLMM ≈41.5k + ≈9.1k per tick crossed + ≈8.5k per other step
(within 64k + 10k per step; the 1.4M limit at ≈147 steps); Orca Whirlpool ≈28-30k + ≈7.0k per crossing + ≈8.6k per
other step (within 48k + 10k per step; the limit at ≈190 steps). A dynamic or adaptive fee far from its reference adds
sub-steps without crossings (up to 0.77M and 1.27M with no crossing at all).

# FT-009: Raydium CLMM and Orca Whirlpool in shadow, then a dry run (PLAN-ADDENDUM WP-21 phase A)

- **Status:** planned, not run. The number is provisional (FT-008 is WP-22's pool refresh); it runs after Stage 0 closes.
- **Build:** lane/wp21 as merged by the owner (record the binary's git hash and sha256 here at the start).
- **Config:** `deploy/arbx-wp21-shadow.toml` (FT-006's config with `[pools] rayclmm = "quote"`, `whirlpool = "quote"`, the seed list below, `[canary] enabled = false`). Data: `data/seed-pools-wp21-shadow.csv` to `/root/arbx/data/`.
- **Mode:** part 1 shadow (`arbx campaign --mode shadow`), part 2 dry run (`arbx campaign --mode dry-run`, `[dry_run] simulate = true`). Nothing is sent: in `quote` mode a live or canary route through either venue is refused `venue_quote_only`, and this config cannot start a canary.
- **Budget:** 0 lamports.
- **Goal:** show that the engine prices, follows and decides routes through Raydium CLMM and Orca Whirlpool from live state with no phantom or poisoned decision, and that their bundles verify and simulate with no account or CU error.
- **Preconditions:** Stage 0 closed; Haan used by this bot alone (I-3); `arbx check --config deploy/arbx-wp21-shadow.toml` passes on Cherry with the uploaded binary.

## The seed list

`data/seed-pools-wp21-shadow.csv` is the 2026-10-06 list (1,500 rows, unchanged, first) plus 242 SOL pools, verified on chain at 2026-10-06 18:52 UTC (slot 453,987,194) with read-only public RPC:

| Source (`source` column) | Raydium CLMM | Orca Whirlpool | Rule |
|---|---|---|---|
| `wp21:seed-token` | 79 | 102 | the token is traded against SOL by the 2026-10-06 list; at most the 3 deepest pools of each venue |
| `wp21:census:<legs>` | 6 | 15 | a CLMM or Whirlpool SOL pool used in at least 2 rival arbitrage legs of the venue census (docs/research/venue-census.md) |
| `wp21:census-token` | 20 | 20 | the census token's other deepest pools (a route needs two pools) |
| **Total** | **105** | **137** | 181 seed-token, 21 census, 40 census-token |

- **Verified for each pool:** the owner and layout (Raydium PoolState 1,544 bytes, Orca Whirlpool 653), the mints the scan saw, liquidity at the price, swaps enabled and open (Raydium status bit 4, open time), a WSOL side of at least 2 SOL (median 49 SOL), Raydium's AmmConfig, and no Token-2022 mint the engine refuses (a transfer fee, a transfer hook, paused, default frozen). 9 picked pools failed and were left out (7 transfer fees, 2 below 2 SOL).
- **Booted by the engine:** `arbx pools` on the whole list (public RPC) puts all 242 into SOL pairs: 92 pairs hold one, 77 of them with pools of the older venues. Its other drops (115, `transfer_fee`) are the 2026-10-06 list's own.
- Built by a read-only script (/home/moiz/arbx-offload/wp21/seeds/build_seeds.py, `verify.json` beside it: every pool with its checks). Candidates came from the part-1 scans of all SOL-paired Raydium CLMM (1,208) and Orca Whirlpool (1,492) pools, read at 2026-10-06 ~15:20 UTC.

## Part 1: shadow, ≥ 2 h (`arbx campaign --name ft009-shadow --mode shadow --hours 2 --segment-min 30`)

Pass criteria, written before the run:

1. **Boot and following.** At most 5% of the 242 WP-21 pools dropped at boot (each drop has its reason). Every booted CLMM pool follows its parts and tick arrays (`clmm_tick_array` role in accounts.bin); `read_missing` for them is explained by accounts that do not exist (`clmm_absent`).
2. **Priced.** Routes with a Raydium CLMM or Orca Whirlpool leg are priced in both directions (decisions.jsonl routes with `size` and `gross`). `unquotable_clmm_array` and `unquotable_clmm` are each below 5% of those routes' evaluations; the `sz_clmm_*` and `sz_whirl_*` refusals are listed with counts. No `venue_upgraded` (the deployed binaries are the ones proven: deploy slots 451,479,902 and 440,170,207).
3. **No phantom decision.** Every trigger of a decision whose best route has a CLMM or Whirlpool leg landed, finalized, without error, in its recorded slot (`getSignatureStatuses`, as FT-000).
4. **No poisoned decision.** No prediction is ever a priced state, and the priced state equals the recorded account versions: `arbx replay --compare` of a 1 h slice is whole and identical (decisions, commit groups, attempts, both digests); `arbx quote` of a sample of 50 such would-sends at their state versions gives their recorded size and gross.
5. **Accuracy where visible.** The transaction stream follows PumpSwap only (Haan: one filter, one account), so the accuracy monitor scores a CLMM or Whirlpool swap only when a stream delivers it. Every one it scores (predictions.jsonl, `venue` RayClmm or Whirlpool) is exact; the count is reported. A second stream on `whirLbMi…` / `CAMMCzo5…` (OD-1) would score them all.
6. **Real or not there.** For the would-sends with a CLMM or Whirlpool leg: the share closed within 2 s by a winning rival round trip (FT-000's taker method), and their quoted SOL.

## Part 2: dry run, 1 h (`arbx campaign --name ft009-dry --mode dry-run --hours 1 --segment-min 60`)

As FT-002, restricted to bundles with a CLMM or Whirlpool leg:

1. **Volume:** ≥ 50 such would-send bundles signed and recorded in full (attempts.jsonl `dry_run`).
2. **Signed-byte checks (`verify_bundle`):** 0 failures.
3. **Simulation:** every such bundle simulated read-only. Would-fails from gaps already taken are expected (the route's min_profit reverts it). **0 failures caused by our transaction:** no CU exceeded, no loaded-data limit exceeded, no account error (Raydium NotEnoughTickArrayAccount, InvalidFirstTickArrayAccount, MissingTickArrayBitmapExtensionAccount; Orca InvalidTickArraySequence, TickArraySequenceInvalidIndex, DifferentWhirlpoolTickArrayAccount; Anchor 3005 AccountNotEnoughKeys, 3012 AccountNotInitialized), no rent error.
4. **CU:** the simulated CU of each leg within its fallback allowance (`Venue::leg_cu`: Raydium CLMM 64,000 + 10,000 a step, Orca 48,000 + 10,000 a step). LiteSVM through the deployed nexus-v2 measured 29,362–68,666 for Whirlpool legs (1–3 steps) and 47,642–175,354 for Raydium CLMM legs (1–15 steps), every one within it (program/venue-harness `tests/arbx_bundle_clmm.rs`).
5. **No transmission:** no copies or bundles records; frz's signatures unchanged.
6. **Coverage:** CLMM and Whirlpool legs paired with at least two of the older venues, create+close and held-account routes.

## What the lab already showed (lane/wp21)

- **nexus-v2 needs no upgrade.** It CPIs any allowlisted program with the builder's account list and patches the input amount at the leg's offset; the deployed ELF's allowlist holds both programs. Five engine-built routes (Whirlpool ↔ PumpSwap both ways, Raydium CLMM ↔ Whirlpool both ways, Raydium CLMM → AMM v4) land through the deployed nexus-v2 and the real programs in LiteSVM, each leg delivering exactly arbx-sizing's quote; a min_profit the route cannot reach fails 0x4e580002.
- **Exact maths.** 1,988 Raydium CLMM and 691 Orca swaps of the venue-parity fixtures quote exactly as the deployed programs execute them (1,343 exact out), and the accuracy monitor's post-states are exact on all 2,679.
- **Replay.** Scenario S17 (USDC/SOL with both venues' pools) replays identically, would-send included.

## Results

(to be filled in when it runs)

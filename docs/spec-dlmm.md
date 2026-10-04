# Meteora DLMM (LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo): port spec

Extracted 2026-10-03 from the current bot (`/home/moiz/arbed/arbed`, read-only) by a code-map agent. Items marked
**[UPSTREAM]** come from Meteora's lb_clmm source, not the repo; check them against the program.

**Biggest gap:** the current bot quotes DLMM in float64 (`Math.pow(1+binStep/1e4, bin)`), not the program's Q64.64
math, and never reads the bin's stored `price` u128. Its measured error: 0 to +1.89 bps (176 LiteSVM legs,
`src/market/hot-add.ts:62-64`). The Rust port should use the stored Q64.64 price and integer math.

## Venue entry (`src/venues/venues.ts:65-67`)
- Own trades use **swap2** only: discriminator `414b3f4ceb5b5b88`. amount_offset = 8. min_out = 1 (nexus-v2 does the profit check).
- Registry t0 = token_x_mint, t1 = token_y_mint (on-chain order). zeroForOne == swap_for_y (X→Y).

## LbPair layout (904 bytes; discriminator sha256("account:LbPair")[0..8] = `210b3162b565b10d`)
| Off | Type | Field |
|---|---|---|
| 8 | u16 | base_factor |
| 10 | u16 | filter_period |
| 12 | u16 | decay_period |
| 14 | u16 | reduction_factor |
| 16 | u32 | variable_fee_control |
| 20 | u32 | max_volatility_accumulator |
| 24 / 28 | i32 | min_bin_id / max_bin_id |
| 32 | u16 | protocol_share |
| 34 | u8 | base_fee_power_factor (base rate × 10^this) |
| 40 | u32 | volatility_accumulator |
| 44 | u32 | volatility_reference |
| 48 | i32 | index_reference |
| 56 | i64 | last_update_timestamp |
| 76 | i32 | active_id |
| 80 | u16 | bin_step |
| 82 | u8 | status (0 = enabled) |
| 86 | u8 | activation_type (0 slot, 1 unix) |
| 88 | Pubkey | token_x_mint |
| 120 | Pubkey | token_y_mint |
| 152 | Pubkey | reserve_x |
| 184 | Pubkey | reserve_y |
| 552 | Pubkey | oracle |
| 584 | [u64;16] | bin_array_bitmap [UPSTREAM] |
| 816 | u64 | activation_point (swaps refused before it) |
| 880 / 881 | u8 | token_mint_x/y_program_flag [UPSTREAM] |
Screens: status 0; bin_step 1..=400; activation_point passed (slot or unix by activation_type).

## BinArray (10,136 bytes; discriminator `5c8e5cdc059446b5` [UPSTREAM])
- disc(8), index i64 @8, version u8 @16, pad[7], lb_pair Pubkey @24, bins[70] @56, each Bin 144 bytes:
  amount_x u64 @0, amount_y u64 @8, **price u128 @16 (Q64.64)**, liquidity_supply u128 @32, ... [UPSTREAM rest].
- Array index = floor(bin_id / 70) (floor: correct for negatives). Offset = bin − index×70.
- PDA seeds: `["bin_array", lb_pair, i64 LE index]`. Bitmap extension PDA: `["bitmap", lb_pair]`; contents never read; if it
  exists it goes in account slot 1 (writable), else slot 1 = the DLMM program id ("None").
- Current bot loads only the active array for quoting (cross-array walks skipped as inexact) and checks existence of ±1/±2.

## Fee math (rates in 1e9 units, cap MAX_FEE_RATE = 1e8 = 10%)
- base = base_factor × bin_step × 10 × 10^base_fee_power_factor
- variable(va) = 0 if vfc = 0, else ceil(vfc × (va × bin_step)² / 1e11)   (integer: `(n + 99_999_999_999) / 100_000_000_000`)
- total = min(base + variable, 1e8)
- update_references, once per swap with the clock (current bot uses wall clock; the program uses chain Clock):
  elapsed = now − last_update_timestamp; if elapsed ≥ filter_period: index_ref = active_id;
  vol_ref = elapsed < decay_period ? floor(va × reduction_factor / 10_000) : 0
- per bin: va = min(vol_ref + |index_ref − bin_id| × 10_000, max_volatility_accumulator)
- Applying the fee, per bin with liquidity:
  - bin drained: fee on top: max_fee = ceil(max_in × rate / (1e9 − rate))
  - partial: fee out of remaining: f = ceil(remaining × rate / 1e9); in_after = remaining − f
- Test vectors (`test/unit/venues/dlmm-bins.test.ts:24-61`): vfc 40000, bin_step 10, va 350000 → variable 4,900,000; base
  10000×10×10 = 1,000,000 → total 59 bp. update_references({va 300000, ref 123, idx 500, ts 1000, fp 30, dp 600, rf 5000},
  active 510, now 1030) → {ref 150000, idx 510}. accumulator(ref 1218, idx 484, bin 486) = 21218.

## Quote walk (exact-in)
- X→Y (swap_for_y): consumes the bin's amount_y, out = in_after × price, walk DOWN (bin −= 1).
- Y→X: consumes amount_x, out = in_after / price, walk UP.
- Skip empty bins. Loop guard 600. Floor the output.
- [UPSTREAM] on chain: max_in to drain (X→Y) = ceil(amount_y << 64 / price); out = floor(in_after × price >> 64);
  for Y→X: max_in = ceil(amount_x × price >> 64), out = floor(in_after << 64 / price). Check drained vs partial (`>` vs `>=`)
  against lb_clmm `bin.rs`.

## swap2 instruction (own trades)
- Data 28 bytes: disc `414b3f4ceb5b5b88` | amount_in u64 @8 | min_amount_out u64 @16 | remaining_accounts_info Vec len u32 @24 (0).
- Accounts:
| # | Account | W | S |
|---|---|---|---|
| 0 | lb_pair | W | |
| 1 | bin_array_bitmap_extension (PDA if exists, else program id) | W if real | |
| 2 | reserve_x | W | |
| 3 | reserve_y | W | |
| 4 | user_token_in (ATA of payer, mint_in, its token program) | W | |
| 5 | user_token_out | W | |
| 6 | token_x_mint | | |
| 7 | token_y_mint | | |
| 8 | oracle (LbPair @552) | W | |
| 9 | host_fee_in = program id (None) | | |
| 10 | user (payer) | W | S |
| 11 | token_x_program | | |
| 12 | token_y_program | | |
| 13 | memo program `MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr` | | |
| 14 | event_authority PDA ["__event_authority"] = `D1ZN9Wj1fRSUQfCjhvnu1hqDMT7hzjzBBpi12nVniYD6` | | |
| 15 | DLMM program | | |
| 16.. | bin arrays (remaining accounts) | W | |
- Bin-array picks: active index c, then in the direction of travel (X→Y: c, c−1, c−2, c+1, c−3; Y→X: c, c+1, c+2, c−1, c+3),
  keeping only arrays known to exist. Transfer-hook mints are screened out.
- Wrapped in nexus-v2 like every leg: per leg {n_accounts, amount_offset = 8, data_len}; accounts: out ATA (W), program, leg keys.

## Recognising a third party's DLMM swap (`src/strategy/pending.ts`)
- Exact-in (amount_in u64 @8): swap `f8c69e91e17587c8`, swap2 `414b3f4ceb5b5b88`.
- Exact-out (max_in @8, out @16): swap_exact_out `fa49652126cf4bb8`, swap_exact_out2 `2bd7f784893cf351`.
- Not decoded by the current bot: swap_with_price_impact `38ade6d0ade49ccd`, swap_with_price_impact2 `4a62c0d6b1334b33`.
- Accounts 0..10 identical in all four: [0] lb_pair [4] user_token_in [5] user_token_out [10] user.
- Direction: accounts[4] == ATA(user, t0) → X→Y; == ATA(user, t1) → Y→X; otherwise undecodable.
- Exact-out amounts are solved by bisection on the quote.
- The whole tx counts only if every other instruction is "benign" (fully visible).

## Post-trade prediction
- Drain bins on a copy: drained bin → amount_out side = 0, other side += max_in (net, fee not added); partial → out side −= got,
  in side += in_after. New active_id = the bin where the swap ended.
- Current bot does NOT update v_parameters in the prediction. [UPSTREAM] On chain the swap writes the last VA, updated
  references, and last_update_timestamp = now.

## Compute budget
- DLMM leg: base 47,000 + 5,450 per bin crossed with liquidity (incl. the active one). Measured max for a real leg: 61,356.
- Route: (29,000 overhead + Σ legs + 30,000 per ATA created) × 1.10, rounded up to 1,000, clamped 30k..600k.

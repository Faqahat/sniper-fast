# Pump.fun launch detector on the shred-trigger path — sketch

Goal: snipe pump.fun launches in the **same slot** the token is created, reusing arbx-fast's shred
feed + slotfix durable-nonce send. Models sniper `4yFAz7dp…QrG3` (same-slot entry, ~3s holds, wins on
speed not tips). Nothing here is wired into the live build or send path.

Companion skeleton: `sketch/launch.rs`.

## 1. Why the existing feed layer already does the hard part
`feeds/mod.rs` decodes every transaction from raw shreds the instant its last shred arrives, builds a
full `tx::Tx { keys, ixs: Vec<Ix{program, accounts, data}>, .. }`, and forwards it to the engine as
`Event::Tx(Arrival{ tx, slot, t_rx, .. })` **iff** `Interest::wants(&tx)` matches a watched static key.
Program ids are always static keys, so watching the pump program is enough to receive every launch.

We get the create transaction fully parsed, same instant the sniper sees it. No RPC, no mempool.

## 2. Detection (pure, cheap)
`detect_launch(tx, slot)` scans `tx.ixs` for the pump `create` instruction and extracts the launch:

- **create discriminator** `d6 90 4c ec 5f 8b 31 b4` (real mainnet bytes, not a guessed anchor hash).
- From the create ix accounts (verified order): `mint = acct[0]`, `bonding_curve = acct[2]`,
  `assoc_bonding_curve = acct[3]`. **The bonding curve comes free — no derive.**
- **creator** parsed from the create ix data tail (borsh: disc, name, symbol, uri, then 32-byte creator).
- **dev buy**: pump bundles the dev's first buy as a second pump ix (disc `07 05 1d c4 f5 17 65 50`) in
  the *same* create tx. `max_sol = data[16..24]`. This is the single strongest launch-quality signal and
  it costs nothing to read.

## 3. Building the buy with zero RPC — AUTHORITATIVE (pump IDL, `sketch/pump_idl.json`, 2026-10-13)
We send **`buy_exact_sol_in`** (disc `38fc74089edfcd5f`; args `spendable_sol_in u64, min_tokens_out u64,
track_volume OptionBool`) — a fixed SOL spend with built-in slippage protection. `buy` (disc
`66063d1201daebea`) has the identical 16-account list. Detection triggers on **`create_v2`** (disc
`d6904cec5f8b31b4` = `sha256("global:create_v2")`), with legacy `create` (`181ec828051c0777`) as fallback.

Every account is constant, from the create ix, or a zero-RPC `pda.rs` derive. The four PDA derives marked
✅ were reproduced bit-for-bit against a live buy (pure-python `find_program_address` + ed25519 on-curve);
the rest are now IDL-confirmed. **Order is the exact IDL order.**

| # | account | source |
|---|---|---|
| 0 | global | `fpa(["global"], PUMP)` = 4wTV1Ymi ✅ |
| 1 | fee_recipient (W) | `CebN5WGQ` (const, not a PDA) |
| 2 | mint | from create ix |
| 3 | bonding_curve (W) | from create ix; == `fpa(["bonding-curve", mint], PUMP)` ✅ |
| 4 | associated_bonding_curve (W) | `ata(bonding_curve, token_program, mint)` ✅ |
| 5 | associated_user (W) | `ata(user, token_program, mint)` ✅ |
| 6 | user (W,S) | our wallet |
| 7 | system_program | const |
| 8 | token_program | TOKEN-2022 |
| 9 | creator_vault (W) | `fpa(["creator-vault", creator], PUMP)` ✅ **hyphen** |
| 10 | event_authority | `fpa(["__event_authority"], PUMP)` = Ce6TQqe ✅ |
| 11 | program | PUMP |
| 12 | global_volume_accumulator | `fpa(["global_volume_accumulator"], PUMP)` |
| 13 | user_volume_accumulator (W) | `fpa(["user_volume_accumulator", user], PUMP)` |
| 14 | fee_config | `fpa(["fee_config", PUMP], PFEE)` = 8Wf5Ti ✅ |
| 15 | fee_program | PFEE `pfeeUxB` (const) |

**`creator` needs no RPC**: it is a `create_v2` *argument* (name, symbol, uri, **creator**, …) and is
exactly what the buy's `creator_vault` keys on (`bonding_curve.creator`). We read it straight from the
create ix data.

**Findings / corrections:**
1. **`creator-vault` is a HYPHEN** under the bonding-curve program. Repo `src/build.rs` uses
   `[b"creator_vault", ..]` (underscore) under **PUMPSWAP** — AMM seed, different address; don't reuse it.
2. **`user_volume_accumulator` IS in the buy** (corrects last pass — it was merely absent from the sniper's
   reordered *wrapper* list; the IDL has it at idx 13). The earlier "two outstanding fee accounts" were an
   artifact of the sniper's custom FCdY account order, not real unknowns — the IDL set above is complete.
3. The sniper's `associated_user` is a **pre-created non-canonical** token account (a speed trick to skip
   the ATA-create CPI). Our first cut uses the canonical ATA; pump accepts it.

These are **token-2022** mints — ATAs use the token-2022 program; create + later close the buyer account
(the sniper reclaims ~0.002 SOL rent per token via its 5000-fee close txs).

## 4. Hook points (3 edits — not yet made)
1. **`feeds` Interest**: add pump program `6EF8rre…` to `interest.keys`. `Interest::wants` already
   forwards any tx whose static keys include a watched program — so create txs start arriving. (Watch the
   forward rate: pump creates are frequent; the filter in §5 is what keeps volume sane, detection is O(ixs).)
2. **`engine::Engine::on_tx(a: Arrival)`** (engine.rs ~L2094): after the existing arb branch, add a
   parallel branch — `detect_launch(&a.tx, a.slot)` → filter → fire. Mirrors how `arb_like()` turns a
   watched-pool arrival into a trigger; here a create arrival turns into a buy trigger.
3. **`snipe_fire`**: splice `Launch::buy_accounts(&wallet)` into a **pre-signed durable-nonce buy
   template** (slotfix: fixed-size message, advance-nonce first, 1-byte opcode + preset amount like the
   sniper's FCdY program) and submit on the **same slot** via the current exec/send path. No new send code.

## 5. Launch filter (where the real edge is — entry speed is already solved)
On-chain entry is commodity; survival is the filter. Start conservative:
- **dev_buy band**: skip near-zero dev buys (no conviction) and skip whale dev buys (we'd buy the top).
  The sniper's spent-per-trade clusters ~3 SOL; size to the curve, not fixed.
- **creator allow/deny** list (repeat ruggers), 1-snipe-per-mint, global rate cap.
- **hard exit**: TP ladder over 1–12 slots + rug-cut, matching the sniper's 67% win / tiny-loss profile.
  This is as important as entry and should ship with the detector, not after.

## 6. Verify-before-send checklist
- ✅ DONE: full account set resolved from pump's on-chain IDL (`sketch/pump_idl.json`). `create_v2` /
  `buy` / `buy_exact_sol_in` discriminators + all 16 buy accounts + every PDA seed. Four PDAs reproduced
  bit-for-bit against a live buy; nothing outstanding.
- Build `buy_exact_sol_in` from the §3 table (fixed `spendable_sol_in`, `min_tokens_out` = slippage floor).
  No custom pump program needed for a first cut — CPI/submit the plain instruction.
- If we later clone the sniper's FCdY wrapper for ix-size/latency, re-derive its custom account order
  (it reorders + omits some of the IDL set); not required to ship.
- Shadow-test on Cherry first (no live send) — measure detect→send latency and same-slot land rate before
  any live run. Per owner rule: ask before going live.

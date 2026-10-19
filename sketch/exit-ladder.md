# Exit / TP ladder — sketch

The other half of the sniper. Entry speed is solved; this is what produces the 67%-win / tiny-loss
profile. Grounded in `4yFAz…`'s actual per-sell behavior (reconstructed from cached buys+sells,
2026-10-13). Companion skeleton: `sketch/exit.rs`. Not wired; no send-path changes.

## 1. What the sniper actually does (measured, price = multiple of avg buy px)

| token | 1st sell | then | shape |
|---|---|---|---|
| 5WZAp (+1.43) | **30% @slot0, 1.31x** | 17/13/10/7/5/4/3/2% over slots 10–47 as px faded 1.29→1.00x, final 7% @slot55 0.93x | long trailing ladder while px holds |
| 2mBKn (+2.21) | **30% @slot1, 1.25x** | held to slot 39, then 23/15/31% at **1.97/1.97/1.85x** | de-risk, then RIDE the climb, sell big high |
| 5WuTn (+0.67) | **66% @slot0** (two sells, 1.29x) | 11/7/15% at 1.45–1.60x slots 24–31 | de-risk hard, keep ⅓ for the pump |
| ytYp (+0.63) | **30% @slot1, 1.28x** | 23% @slot13 1.24x, 47% @slot19 1.16x | de-risk, exit fully in ~4s as px fades |
| DtE9 (+1.28) | **66% @slot1, 1.49x** | 34% @slot2 1.25x | fast double, out in 2 slots |
| FR94 (+0.23) | **66% @slot0** (1.35x+1.18x) | 11% @slot10 0.80x, 22% @slot15 **0.64x** | de-risked high; tail dumped at a LOSS, still net + |

## 2. The distilled strategy
Four behaviors, in priority order:
1. **Instant de-risk.** Sell a big first tranche (30–66%) in the **same or next slot** at ~1.2–1.5x.
   This alone recovers most/all of the SOL cost — it is *why losers stay tiny*. FR94 netted + even though
   its tail dumped at 0.64x, because the 66% went out at ~1.3x first.
2. **Trailing ladder** on the remainder while price holds ≥ ~1.0x: decaying chunks (~30% of *remaining*
   each), every ~4–6 slots. If price fades below ~1.0x, dump the rest.
3. **Ride if it climbs.** If price pushes to ≥ ~1.6x and is still rising, *stop laddering down* — hold and
   sell big into the higher level (2mBKn's 1.9x). Exit the remainder when it drops a set % off its peak.
4. **Hard stops.** Dump 100% immediately on: price ≤ ~0.85x (rug/fade cut), curve migrating / not sellable,
   or age ≥ ~50 slots (~20s — the observed max hold was 55 slots / 12s).

## 3. Mechanism (reuses arbx-fast machinery)
- **Price feed:** after a snipe, add the launch's `bonding_curve` account to the watched set (we already
  have its pubkey from the create ix). The exit state machine is driven by its updates — the same
  account-follow path the arb engine uses. `px = virtual_quote_reserves / virtual_token_reserves`, parsed
  from the `BondingCurve` account (IDL-confirmed, after the 8-byte disc): `+8 virtual_token_reserves u64`,
  `+16 virtual_quote_reserves u64` (quote = SOL for SOL curves), `+24 real_token`, `+32 real_quote`,
  `+40 total_supply`, `+48 complete bool`, `+49 creator pubkey`, `+81 is_mayhem_mode`, … Adjust for token
  decimals when forming the ratio.
- **Sell ix:** pump `sell` (disc `33e685a4017f83ad`, args `amount u64, min_sol_output u64`), 14 accounts =
  the buy set **minus** the two volume accumulators (order in `exit.rs`). Every account already derived for
  the buy; `min_sol_output` = `expected_sol * (1 - slippage)` is the per-tranche slippage floor.
- **Same-slot de-risk** (the slot-0 first sell) needs a pre-built sell on a **second durable-nonce lane**,
  fired right after the buy. First cut: fire the de-risk at slot+1 (still ~1.25x) and add the same-slot
  lane as an optimization.

## 4. Params (defaults grounded in §1 — all tunable)
```
DERISK_FRAC     = 0.40     # first tranche of original position (data 0.30–0.66)
RIDE_R          = 1.60     # climb to here & rising -> switch to ride mode
LADDER_R_FLOOR  = 1.00     # trailing ladder only while px >= this
LADDER_FRAC     = 0.30     # sell this frac of REMAINING per step
LADDER_STEP     = 4 slots  # cadence
TRAIL_DROP      = 0.15     # ride mode: px off its peak by this -> dump remainder
STOP_R          = 0.85     # dump 100% now
AGE_CAP         = 50 slots # ~20s hard dump
```

## 5. Before live
- Confirm `BondingCurve` field offsets from the IDL (`sketch/pump_idl.json` → accounts) — a wrong offset
  = wrong price = wrong exits.
- Shadow-test on Cherry: replay the state machine against recorded curve updates for past launches, check
  it reproduces a sane ladder and would have been net-positive, before any live send. Ask before going live.

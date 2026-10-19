# Shadow harness — corrected-winner validation (2026-10-13)

Entry anchored at the create-slot floor (the fix). Our exit ladder replayed against each token's **real
observed price path** (price multiple `r` by slot, from the per-sell reconstruction), vs the sniper's
actual realized PnL. Loser tokens included as controls.

## Per-token (BASE ladder: derisk 40%, trail 15%, stop 0.85x, 2 SOL, 10% slippage)
| token | our sim | sniper real | note |
|---|---|---|---|
| 7oeU  | −0.20 | −0.19 | loser — reproduced (control) ✅ |
| FR94  | −0.16 | +0.23 | fader — we lose small; sniper derisked harder (66%) and banked + |
| DtE9  | **+0.42** | +1.28 | was −0.70 with the entry bug → now a win ✅ |
| 2mBKn | **+0.90** | +2.21 | ride mode held to 1.85x ✅ |
| 5WuTn | **+0.50** | +0.67 | close ✅ |
| 5WZAp | **+0.16** | +1.43 | laddered down as px faded — under-extracted |

**Entry fix validated:** winners now simulate as wins (DtE9 −0.70 → +0.42). Direction correct on 5/6.

## Config sweep (same 6 real paths) — the calibration loop
| config | PnL | wins |
|---|---|---|
| sniper real (these 6) | +5.63 | 5/6 |
| BASE (derisk .40, slip 10%, 2 SOL) | +1.61 | 4/6 |
| TUNED (derisk .55, trail .20, stop .90, slip 10%) | +1.68 | 4/6 |
| TUNED, slip 5% | +2.44 | 5/6 |
| TUNED, slip 5%, size 3 SOL | +3.66 | 5/6 |

Tuning (bigger first de-risk, tighter trail/stop, realistic slippage, sniper-comparable size) lifts us to
~65% of the sniper's realized edge on these tokens. The remaining gap is fill quality (intra-slot
execution, size vs curve depth) and exact peak timing — not the ladder's structure.

## Honest caveats (why this is validation, not a profitability claim)
1. **Selection bias:** these 6 are the sniper's *own* snipes. Real expectancy needs the unbiased
   `create_v2` sample — including the launches we'd skip and the ones that rug — which needs unbiased
   discovery + an authed RPC (public RPC can't paginate busy curves to the create slot fast enough).
2. **Sparse/flattering price path:** reconstructed from the sniper's observed trade prices (they sold into
   strength); a full tick series would be less kind.
3. **Crude fills:** flat % slippage, no curve-depth model or priority-fee cost.

## What this establishes
- The entry→exit→PnL pipeline is correct and reproduces reality (loser −0.20 vs −0.19; winners flip to
  wins once entry is at the create-slot floor).
- The ladder is directionally sound (net +, 4–5/6) but **under-extracts vs the sniper** — larger first
  de-risk and better fills are the levers.
- The harness **ranks configs**, which is the calibration mechanism. Next: unbiased sample + grid-search.

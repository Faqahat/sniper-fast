# 5-run live plan (draft 2026-10-19, owner rule: every run >= break-even; no dev/runs until ~03:30 UTC 10-20)

Fixed across runs: rule #2 (bundle 3-5 SOL + Lunar-tipped create) + base filter + --close-leaders 5 ms + --max-create-ms 150 (proven in paper), guard verifies every fire.
Engine already has: --exit-ladder (--derisk-frac --ladder-frac --ride-mult --trail-frac --cut-r --exit-cap-ms --min-others-sol), --spend-lamports, --slip-bps (min_tokens_out cap), --cu-limit/--cu-price-micro, --sell-cu-price-micro, per-path tips in toml.

| Run | Size | Buy fee (prio + tips) | Exit | Limits | Pass |
|---|---|---|---|---|---|
| 1 Pro baseline | 1.5 SOL fixed | ~0.025: CU 95k x 110M = 0.0105 + Jito 0.012 + relays ~0.002 | ladder L1 | 20 buys / 3 h, SL -0.5 SOL, lock 0 at +0.3 | >= 0 |
| 2 Fee step | up-branch 2 SOL / down-branch 1.5 | up ~0.043 (200M x 95k = 0.019 + Jito 0.022 + 0.002) / down ~0.018 | L1 | same | >= 0 |
| 3 Confidence | base = Run 2; confident 2x (<= 4 SOL) | fee scales with size | L1 | SL -0.7 | >= +0.3 |
| 4 Exit tune | +33% if 1-3 net > 0 | as 3 | best replayed variant | SL -0.8 | >= +0.3 |
| 5 Scale/coverage | 2 / 4 SOL | ~2% of size | best | SL -1.0 | >= +0.6 per 3 h ($500/day pace) |

Ladder L1: de-risk 30% on landing; 15% chunks every ~1 s while 1.0-1.3x; ride >= 1.3x with trail 85% of peak; hard cut 0.80x; dead-token dump if no other buyers (min-others-sol); all out by 20 s. Entry cap --slip-bps 1500. Sells CU price ~5M.
Fee-step rule after Run 1: median landing > +25 txs or same-slot < 80% -> up-branch; else down-branch.
Between runs: run >= 0 -> next step; run < 0 -> fix ONE lever (landing / entry / exit from per-trade metrics), repeat the same step at the same size.
Prep after pause: config + small dev in a copy (run-level break-even lock in guard, confidence tier for Run 3), offline sim on rule-#2 tapes (ladder params, slip cap, tier signal, must show Run-1 config >= 0 after all costs), 1 h shadow, optional Run 0 smoke test (3 x 0.1 SOL, low fee).
Windows (rule-#2 launches/h, UTC): 07-12 UTC busiest (64-95/h) -> Run 1 07-10 UTC (12-15 PKT), Run 2 11-14 UTC (16-19 PKT); Runs 3-5 next day same windows.
Wallet: Runs 1-2 ~4-5 SOL, Run 3 ~8 SOL, Run 5 ~10-12 SOL (now 0.199).

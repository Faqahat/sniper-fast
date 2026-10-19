# genuine — Can an ENTRY FILTER beat buy-all by skipping the ~1s instant-dumps?

Historical replay only. **No live trading.** Reuses `econ_102` exit+cost engine (pump 1%/leg + 0.25%/leg
slippage + fixed 360k+5k lamports/leg priority), the unbiased create-slot-anchored price paths
(`profit_backtest/trajectories.json`, 1,141 launches), the shipped size filter (`dev_buy>=2`, `fee==0`)
→ **656 filter-passing launches**. Chrono split by slot (TRAIN 328 / VAL 328, split 456702281); all
numbers reported OOS (VAL) with IS shown alongside. **WINNER exit** per spec: derisk 0 / ladder 0 /
cut_r 0 / ride 2.0 / trail 0.90 / cap 15 slots.

## Entry-fill accounting (the honest part)
- **Baseline buy-all** lands in the create slot first → entry = `floor × 1.02` (priority-fee fill), full path.
- **Every filter** waits to confirm, so it enters LATE at the *observed* later price × 1.02. That observed
  price is already above the floor — **that is the fill penalty**, and it is large:

| delayed entry | n | median fill vs floor | mean | p90 |
|---|---:|---:|---:|---:|
| co-snipe≥2 @ create+1 | 75 | **1.41×** | 1.49× | 1.87× |
| any filter @ create+1 | 558 | 1.00× | 1.10× | 1.40× |
| @ create+2 | 548 | 1.00× | 1.10× | 1.41× |

Confirming a co-snipe means paying **~1.4× the floor** — you buy the crowd's pump.

## Instant-dump base rate — the premise is smaller than it feels
"Instant-dump" = price < 0.8× create-slot floor within 3 slots.

- **Hard instant-dump (<0.8× in 3 slots): only 1.5% of launches** (VAL 1.2%). There is almost nothing to avoid.
- Fuller fate (has-path n=336): dips below floor in first 3 slots **37%**; never reaches 1.1× peak **24%**;
  **ran ≥1.5× peak 42%**.

The owner's "60–80% dump" is **not** a hard <0.8× crash (that's 1.5%); it's "most never pump enough to beat
costs / slowly bleed." Those are **cheap to hold**, not catastrophic — the WINNER exit caps them at a few
percent while riding the 42% that run. You don't dodge them with a pre-buy filter; you survive them with the
cheap floor entry + the capping exit.

## Entry-filter comparison (OOS / VAL, SIZE 0.5 SOL)

| strategy | buy% | dump-rate bought | mean R | win% | total R | maxDD | IS mean R |
|---|---:|---:|---:|---:|---:|---:|---:|
| **BASELINE buy-all @ floor** | 100% | 1.2% | **+0.0933** | 30% | **+30.60** | **−1.39** | +0.0764 |
| _DIAG co-snipe≥2 @ FLOOR_ | 14.6% | 0% | _+0.3728_ | _88%_ | _+17.89_ | _−0.13_ | _+0.4107_ |
| co-snipe ≥1 (real, create+1) | 18% | 0% | −0.0612 | 9% | −3.55 | −4.50 | −0.0525 |
| co-snipe ≥2 (real, create+1) | 14% | 0% | −0.0665 | 9% | −3.06 | −3.19 | −0.0514 |
| co-snipe ≥3 (real, create+1) | 9% | 0% | −0.0742 | 7% | −2.23 | −2.39 | −0.0595 |
| survival N1 thr1.0 | 52% | 0% | −0.0237 | 18% | −4.03 | −5.28 | −0.0544 |
| survival N2 thr1.0 | 50% | 0% | −0.0216 | 18% | −3.54 | −5.09 | −0.0593 |
| survival N2 thr0.9 | 84% | 0% | −0.0398 | 17% | −10.90 | −11.85 | −0.0403 |
| momentum N2 r≥1.1 | 22% | 0% | −0.0571 | 10% | −4.05 | −4.90 | −0.0683 |
| momentum N1 r≥1.3 | 13% | 0% | −0.0493 | 12% | −2.12 | −3.07 | −0.0423 |
| combo K2 + surv N2 t1.0 | 13% | 0% | −0.0578 | 10% | −2.43 | −2.67 | −0.0691 |

Size sweep (VAL mean R, 0.1/0.5/2.0 SOL) barely moves any row (fixed priority cost is immaterial by 0.5 SOL):
baseline +0.088/+0.093/+0.094; every filter stays negative.

## The smoking gun (co-snipe at FLOOR vs at create+1, same tokens)
- Co-snipe≥2 bought **at the floor**: **+0.3728 R, 88% win** (OOS). The co-snipe crowd is a genuine,
  powerful signal — the #1 separator, consistent with `last500`/`his_tape`.
- The **same tokens** entered one slot late (create+1, median 1.41× fill): **−0.0665 R, 9% win**.
- The fill penalty of confirming the crowd **destroys ~0.44 R of edge** and flips the sign.

Every filter is self-defeating for the same reason: the tokens worth buying are exactly the ones that jump
in-slot, so any "wait and confirm" rule buys them *after* the jump. From a 1.4× base the WINNER exit (needs
2× to ride) rarely engages, and you eat trail/cap exits. Filters also have **worse drawdown** than baseline
(−3 to −12 R vs −1.4 R) because they strip out the floor-bought winners that smooth the curve.

## VERDICT
**No. There is no genuine-token entry filter that nets better than buying-all-at-floor.** The fill penalty
always exceeds the dump-avoidance benefit — and the benefit is near-zero to begin with (hard instant-dumps
are 1.5%, and the WINNER exit already caps the slow bleeders). Co-snipe/survival/momentum all net **negative
OOS**, while buy-all-at-floor nets **+0.093 R OOS (30% win, −1.4 R maxDD)**.

- **Best "genuine-token" rule that is actually buyable:** none — buy-all @ floor + WINNER exit is the rule.
- **Implied latency of every filter:** ≥1 slot late (co-snipe confirm = create+1), implied fill **~1.4×
  floor** for the co-snipe set — the killer.
- **The real lever is the opposite of waiting:** the co-snipe signal is only capturable at the floor
  (+0.37 R). The way to "buy genuine tokens" is to **land SAME-SLOT at the floor** (arbx-fast / inshred),
  not to confirm late. Confirmation latency is the enemy, not the filter.

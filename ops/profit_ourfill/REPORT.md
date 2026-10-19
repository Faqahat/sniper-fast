# Can the pump.fun sniper be +EV from OUR REAL FILL (no infra upgrades)? — profit_ourfill

Pure historical / paper replay. **No live trading.** Entry = our realized fill (create+1 curve price,
the first observable/fillable price, median ~1.0x floor on uncongested launches and ~1.33x on co-sniped
ones per the live fill probe). r is measured relative to OUR entry, not the floor. R = net return as a
fraction of position size.

Two samples, both reconstructed from the on-chain bonding-curve trade stream via the global pump
mint-authority PDA (`TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM`), no survivorship bias:
- **Backtest window** — 1,140 unbiased create_v2 launches, slots ~456604–456820 (reused from
  /root/profit_backtest). Shipped filter (dev_buy>=2 SOL, creator_fee==0) -> 656 launches.
- **Paper window (temporal OOS)** — the 258 mints from the 2h live paper run (slots 456878173–456911074,
  DISJOINT and later than the backtest window). Price paths freshly harvested here
  (/root/profit_ourfill/paper_traj.json). dev>=2 usable -> 254.

---

## (a) THE CONTRADICTION — RECONCILED

| measurement | entry basis | cost model | result |
|---|---|---|---|
| 2h LIVE paper (paper_2h.log, 291 pos) | first-readable curve px (~our fill) | **ZERO** (log: "No fees/own-impact modeled") | **+0.0187 R** |
| fillvalue "observed-late" (656) | first trade at slot>=C+1 | **8%/leg sell slippage + fee** | **-0.0785 R** |

**They disagree purely because of the COST MODEL, not the entry basis or the period.** Proven on one
common sample (backtest 656), decomposing entry-basis x cost:

```
                          ZERO cost      fee-only     8%slip+fee (fillvalue)
OUR-FILL (+1, paper proxy)  +0.0069        +0.0055        -0.0750
OBS-LATE  (fillvalue)       +0.0032        +0.0018        -0.0785   <- reproduces fillvalue -0.0785 exactly
```

- **Entry basis is NOT the cause.** our-fill(+1) and observed-late give near-identical entry prices
  (both median 1.00x floor; our-fill mean 1.12x vs obs-late 1.08x) and near-identical PnL in every cost
  column. 123/656 are literally the same price.
- **The cost model IS the entire sign flip.** fillvalue's flat 8%/leg sell slippage shifts the whole
  distribution down ~8 points, turning +0.007 into -0.075. The paper's ZERO cost leaves it positive.
- **Period is a minor second-order effect** (same sign): paper's own window reproduces at +0.0152 R
  zero-cost here (vs its reported +0.0187; small diff = first-readable-curve-read vs create+1-last-trade,
  35% vs 38.8% win). The backtest window is +0.0069 zero-cost. Both positive, both tiny.

### Which number is right? NEITHER as published — both omit the real cost.
The faithful structure is the **paper's**: enter at our real fill, replay the shipped ladder on the real
forward path. But the paper's ZERO cost is too optimistic and fillvalue's flat 8%/leg is calibrated for
a 2.0 SOL size into a thin curve — far above our real cost. **Our actual execution cost** (verified from
the engine + fill probe):
- pump.fun **protocol fee = 1%/leg** (~2% round-trip, more across ladder legs) — the binding cost; both
  prior studies OMITTED it.
- base tx fee 5,000 lamports/leg on the warm TPU path with `cu-price-micro=0` and **no tip** (~0.05% of a
  0.165 SOL position — negligible).
- own curve-impact slippage: <0.5% at our real size (0.01–0.165 SOL), negligible (not 8%).

**True at-fill expectancy of the SHIPPED config, realistic cost, our-fill entry:**

| window | zero-cost (paper) | **realistic cost** |
|---|---|---|
| backtest 656 | +0.0069 | **-0.0180 R** |
| paper 254 (OOS) | +0.0152 | **-0.0098 R** |

At 0.165 SOL that is roughly **-0.002 to -0.003 SOL per snipe** — a small, steady bleed, not a blow-up.
The paper looked positive ONLY because it charged no fees.

---

## (b) GRID SEARCH FROM OUR ENTRY (train/val by slot, OUT-OF-SAMPLE) — realistic cost

648 selection x 480 exit configs, two-stage (select on train, then tune exit), realistic cost, 0.165 SOL.
**No config is +EV out-of-sample.** Best OOS val cell:

```
SELECTION  dev 2–10 SOL, vanilla-only, anti-factory(<=2 launches)
EXIT       derisk 0.0, ride 1.2, trail 0.85, cut 0.95, ladder 0.25, cap 10 slots
  TRAIN mean -0.0160  VAL mean -0.0275  (med -0.0248, win 16%, drop-top2 -0.0312)
```

The grid's directional findings (all still net-negative):
- **de-risk 0.0 beats 0.30** — the entry de-risk sells 30% for ~0 gain and pays the pump fee twice; skip it.
- **lower ride (1.1–1.2) + short cap (10) beats the floor-calibrated 1.4/40** — his thresholds are tuned
  for a floor entry; at our higher basis the headroom is gone, so hold less. But the lift is marginal and
  still negative.
- vanilla-only + anti-factory helps gross by a hair; co-sniper buckets and entry-ratio bands do not rescue it.

### Why nothing works — the gross ceiling is ~0 at our entry
Even with PERFECT, cost-free execution the shipped ladder from our fill yields only **+0.0069 R (ALL)**,
**+0.0003 (vanilla)**, **~0 (co-sniped)** — and that is tail-dependent (drop-top-2 ≈ 0). The edge the
fillvalue study found lives at the **floor** (+0.11–0.13 R on co-sniped launches, same-slot-FIRST); at our
+1 fill the co-snipers have already bid those up ~1.3–1.4x and the edge is annihilated before we trade.

Break-even requires total round-trip cost below ~**1%** (paper window) / ~**0.2%** (backtest window);
pump.fun's own 1%/leg (2% round-trip) alone exceeds it:

```
pump fee/leg  ~round-trip   backtest meanR   paper-window meanR
   0.00%          0%          +0.0022           +0.0105
   0.50%          1%          -0.0079           +0.0003   <- paper window breaks even here
   1.00%          2%          -0.0180           -0.0098   <- actual pump fee: BOTH negative
```

### Momentum-continuation (hold for a 2nd leg) — tested, does NOT help
On the live-usable "still rising at +2 slots" subset, holding (derisk 0, ride 1.1, cap 80) nets
**-0.0192** vs the flip's -0.0085 — holding is WORSE. The rising-at-entry signal does not persist.
The only subset that is +EV is `mom5>1.1` (price still up 5 slots AFTER entry): net +0.043 — but that is
**look-ahead**, not knowable at fill. It confirms an edge exists in the path (perfect-exit net is +0.34 R
ALL), but capturing it needs forward knowledge / a better entry we do not have, not an exit tweak.

---

## (c) VERDICT

**NO.** With our own system and no better fills, the sniper is **not +EV** — it is a small net loser at our
real fill: **-0.010 to -0.018 R per snipe (~-0.002 to -0.003 SOL at 0.165 SOL)** with the shipped config,
confirmed out-of-sample on a disjoint later window, and **no selection/exit tuning crosses zero OOS**
(best found: -0.0275 R val).

The reconciliation settles it: the paper's +0.0187 was real but **cost-free**; once the pump.fun 1%/leg
protocol fee is included (which neither prior study modeled) the same positions are negative. The gross
price-path edge at our entry is only ~+0.007 R and tail-fragile — smaller than the unavoidable ~2%
round-trip protocol fee. The edge is structurally at the **create-slot floor** (same-slot-first fills),
exactly what we do not get. **This is a fill-quality / same-slot-priority problem, not a selection- or
exit-tuning problem** — consistent with the fillvalue and fillprobe studies, now with the correct cost
model and the paper/fillvalue contradiction resolved.

Honest caveats: two ~13h / 2h market regimes, one asset class; flat per-leg cost model (pump 1% + base +
small impact), no depth/size curve beyond a linear impact term; intra-slot order not recoverable so our-fill
= create+1 price (unbiased per-launch, ~1.0x on quiet / ~1.3x on congested). The tiny positive gross is
inside the error bars of zero.

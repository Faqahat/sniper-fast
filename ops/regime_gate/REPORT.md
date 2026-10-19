# Regime Gate for pump.fun sniper — backtest & verdict

Date: 2026-10-14. Work dir: `/root/regime_gate/`. Size 0.5 SOL, entry = floor*1.02,
shipped exit ladder + net costs (econ_102). Net-R recomputation reproduces the
`paper_feat`/`fresh_feat` precomputed `net` exactly (max diff 0.0 at SIZE=0.5) — pipeline validated.

## VERDICT (headline)

A regime gate CANNOT work here. There is no actionable regime persistence, and the
proposed signal (rolling pump-rate) is statistically identical in the +EV and -EV
windows, so no threshold can separate them. Do not build the gate.

The one real structure in the data — the backtest window is +EV and the paper/fresh
windows are -EV — is a between-harvest level shift, not a tradeable regime a rolling
real-time signal can detect. Within every window the pump label is an IID coin flip.

## Data / timeline

Stitched one time-ordered timeline (by slot, ~0.4 s/slot) from the three windows,
deduped by mint. 1586 launches with a measured entry_px.

| window   | n    | mean net/trade | total net | net-win% | pump>=1.2x | pump>=1.4x |
|----------|------|----------------|-----------|----------|-----------|-----------|
| backtest | 1140 | +0.0422        | +48.08    | 26.8%    | 27.6%     | 17.2%     |
| paper    | 254  | -0.0443        | -11.24    | 14.2%    | 27.2%     | 15.7%     |
| fresh    | 192  | -0.0406        | -7.79     | 6.8%     | 21.4%     | 9.4%      |
| OVERALL  | 1586 | +0.0183        | +29.05    | 22.4%    | 26.8%     | —         |

Windows are genuinely separated in time: backtest ends slot 456,820,114; paper starts
456,878,173 (~6.4 h gap); paper->fresh nearly contiguous (~6 min gap). Median
inter-launch gap ~61 s. The mixed-regime -EV story is real: paper+fresh alone = -19.0 SOL.

Caveat: backtest is a mined/harvested set, paper/fresh are passive paper feeds. The
+EV vs -EV level gap is partly confounded with how each window was collected — another
reason the "regime" is not something a live rolling signal can be trusted to re-detect.

## STEP 0 — Regime persistence: NO (fails make-or-break test)

Pump label = peak price within 12 slots of create >= 1.2x entry (also tested 1.4x).

Autocorrelation of the pump label and of net-R, at every actionable lag (1,2,3,5,10,20,50
launches ~1-50 min), is ~zero everywhere — global, within each window, and within the
contiguous paper+fresh quiet stretch:

- lag-1 ac(pump): global -0.011, backtest +0.015, paper -0.051, fresh -0.170, paper+fresh -0.094
- lag-1..20 ac(net): all within +/-0.06, no consistent sign.

Causal rolling-rate predictivity — corr(pump-rate of last K launches, next launch's
pump / next launch's net):

| scope       | K=20 next_pump/next_net | K=50 | K=100 |
|-------------|--------------------------|------|-------|
| global      | +0.016 / +0.038 | +0.005 / +0.021 | -0.019 / -0.026 |
| paper+fresh | -0.034 / -0.067 | -0.010 / -0.020 | -0.015 / +0.001 |
| backtest    | +0.028 / +0.032 | +0.004 / -0.000 | -0.026 / -0.058 |

All ~zero; negative in the quiet stretch. Recent pump-rate does not predict the near future.

Clustering (runs test vs 2000 shuffles): global observed runs 629 vs shuffled 623
(p=0.65, not significant); paper+fresh observed 181 vs shuffled 167, p=0.97 meaning the
quiet stretch is if anything more alternating than random — the opposite of persistence.

The killer: the proposed signal itself carries no regime information. Rolling pump-rate
(K=50) distributions overlap almost completely between +EV and -EV windows:

| window   | regime | mean rate | p10 | p50 | p90 |
|----------|--------|-----------|-----|-----|-----|
| backtest | +EV    | 0.277 | 0.20 | 0.28 | 0.36 |
| paper    | -EV    | 0.268 | 0.20 | 0.28 | 0.32 |
| fresh    | -EV    | 0.219 | 0.16 | 0.20 | 0.30 |

The -EV windows pump >=1.2x just as often as the +EV window — they simply don't PAY
(pumps are smaller / don't hold, so net-win and tail are worse). A pump-rate gate is blind
to the only thing that differs.

## STEP 1-3 — Gate backtest (run anyway, to demonstrate the failure concretely)

Gate: trade launch i iff pump-rate of the K launches before i >= threshold (passive,
real-time computable from the feed); else pause.

In-sample, full timeline: no (K,threshold) beats ungated total net (+29.05). Mean
net/trade stays ~+0.015-0.04 across all thresholds — cutting on the signal ~ random
subsampling. High-mean cells (e.g. K=50/thr=0.40, mean +0.11) have n=58 — noise, and lower
total. Gating only throws away trades; it does not raise EV.

Out-of-sample (chronological 60/40). Train = first 951 launches (all backtest, +EV).
Validate = last 635 (189 backtest + 254 paper + 192 fresh, mostly -EV). Tuning on train
(maximise total net, duty>=0.15) picks K=50, thr=0.20 — i.e. "basically always trade".

| validation (last 40%) | trades | duty | mean net/trade | total net | win% |
|-----------------------|--------|------|----------------|-----------|------|
| ungated               | 635    | 1.00 | -0.0223        | -14.14    | 17.0% |
| gated (K=50,0.20)     | 516    | 0.81 | -0.0223        | -11.52    | 16.5% |

Gated mean net/trade is identical to ungated (-0.0223). The small total improvement is
only from trading 119x less, not from trading better; win% is actually slightly worse.
It avoids just 13.5% of quiet-window losses while staying 85% on. Any threshold high
enough to pause the quiet windows would also pause the profitable backtest launches,
because their rolling-rate distributions overlap.

## Answers to the deliverable questions

(a) Does recent pump-rate predict the near future? NO. Autocorrelation ~0 (+/-0.05) at
all actionable lags; causal corr(rate, next) ~0 and negative in the quiet stretch; no
run-clustering. Pump events are IID within each regime.

(b) Gated-vs-ungated OOS: gate leaves mean net/trade unchanged (-0.0223) and stays
-EV in validation; it cannot turn the mixed timeline +EV. No gate rule is worth shipping.

(c) Does a regime gate make the strategy net +EV across mixed regimes? NO. It is
real-time implementable from the shred feed (the rolling pump-rate is passive and causal),
but it has no predictive content: the +EV and -EV windows produce the same pump-rate
distribution, so the gate cannot tell them apart. The apparent overall +EV (+29 SOL)
comes entirely from the one backtest window; across the quiet windows the gate still loses.

## Honesty notes

- Sample size: only ~3 windows, 2 regime "states"; between-window persistence is n=2 —
  not estimable. The strong-looking macro level shift is a single event, pure overfit risk.
- Stitching artifact: 6.4 h gap between backtest and paper; a rolling window cannot
  bridge it, and backtest vs paper/fresh were harvested differently (mined vs passive), so
  the level gap is partly a collection artifact, not a live, repeatable regime.
- The gate would just overfit the one pump window. Confirmed by OOS: tuned on the pump
  window it degenerates to "always trade" and carries that into the quiet windows and loses.
- The durable edge remains the fill (3M cu_price -> ~1.02x floor), not launch selection
  and not a regime gate. If anything can rescue EV it must raise pump magnitude capture or
  cut per-trade cost — not time the regime, which is unpredictable at our reaction lag.

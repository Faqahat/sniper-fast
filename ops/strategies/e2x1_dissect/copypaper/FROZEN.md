# copypaper — FROZEN strategy (10-28 23:10 PKT, before any forward scoring)

PAPER ONLY (owner OK 10-28 ~23:00 PKT). No live sends, no server writes, no engine changes. Local only.
Code: `/home/moiz/sniper/ops/strategies/e2x1_dissect/copypaper/` (cp_decode.py, cplib.py, cp_score.py, cp_table.py, loop.sh).
Data: `/home/moiz/sniper-data/e2x1_dissect/copypaper/` (cache/ decoded chunks, out/results.jsonl, out/trades.jsonl, out/state.json, out/loop.log, val/ = D0/D1 validation).

## Signal
- A successful pump.fun curve **BUY** by `E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb` or `Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ` (TradeEvent user).
- Normal curve only: curve virtual SOL before their buy in **25–200 SOL**, mint not flagged mayhem in its CreateEvent (when the create is in the loaded tape).
- One position per token per cluster entry: a cluster buy while we hold (entry … median-draw exit clock) is **not** a signal; after our exit a new cluster buy is a new signal. Lockouts carry across 2-h windows (state.json).

## Our buy
- Lands L after their buy: L = our live pre-send landing shape (21 equiprobable quantiles, `delay_q.json` q_pre, median 56 ms) rescaled to **median 66 ms** (ourspeed method). Block clock: slot + tx-index/block-size; a draw that would land before their tx in the same block lands right after it.
- Size = **min(their cost incl. pump fees, 0.5 SOL)**; x = size/(1+f) goes into the curve, f = fee_bps + creator_fee_bps of their buy.
- Guard: revert if we would get fewer than qref/1.05 tokens, qref = tokens for x at the curve state right after their buy (**+5%**).
- Entry state = last recorded trade strictly before our landing position (everyone who landed between them and us is in). Our own impact: constant product, our SOL stays in the curve until we sell.

## Our sell
- L' after we see the **first sell by either wallet** on that token after the signal (curve sell or PumpSwap sell); L' = the same 21 delays paired in reverse order (as o2_sim). If their sell lands before our buy, we sell right after our buy.
- No sell by them within **1800 s** of their buy → sell at the first block ≥ their buy block time + 1800 s (+ L').
- No stop in the main rows. **Variant** reported alongside: **−20 % stop** (sell L' after the first recorded trade that marks our position ≤ 80 % of cost; curve only).
- If the curve completed before our exit: sell on **PumpSwap** at the pool state after the last recorded pool trade before our position (reserves derived from trade amounts, grad/glib.py rule; opening reserves from MigrateV2 if no pool trade yet; pool fee = lp + protocol + creator fee of the nearest sell). Curve complete with no pool recorded yet → position marked at the completion price and counted in `unresolved`.
- Exit price = curve state after the last recorded trade strictly before our sell landing position, with our x still in the curve, pump fee of that trade.

## Costs and rows (all expected values over the 21 draws)
- `raw`: P&L − **2.9 mSOL per filled trip** − **0.3 mSOL per reverted try**.
- `f20fast`: raw with **20 % of other wallets' buy SOL landing within 10 slots after our entry removed** from the curve at exit (ourspeed's phi-20 "fast" row; cluster wallets never count as followers).
- `f20hold`: raw with 20 % of ALL other buy SOL between our entry and exit removed (the brief's literal wording). Reported for information only: over 30-minute holds it removes buys that are not followers of us and is dominated by them (D1: −72 SOL vs raw +7.7), so it is not the pass-bar row.
- `cal`: raw (phi 0) − **max(0, −4.4 + 28.1 × S) mSOL per attempt** (S = our size in SOL; ourspeed/PAPER_VS_LIVE straight-line paper-vs-live gap). Never stacked with f20.
- Per wallet: signals split by which wallet's buy was the signal. Top-5: the 5 best trades by raw.

## Pass bar for the owner (48 fresh hours, 10-28 23:00 → 10-30 23:00 PKT)
1. running **cal > 0**, and
2. running **f20fast > 0**, and
3. with the **top-5 trades removed**, running raw ≥ 0 and running cal ≥ 0.
All on the frozen rules above; the stop variant and f20hold are information only. Anything that is not in this file is not part of the test.

## Validation before freezing (val/, D1 = 10-27 20:00 → 10-28 20:00 PKT, D0 = the 24 h before)
- Replica of ourspeed's **B copy-trade** (his lots, his size, exit = his first sell, no timeout/band/lockout) on my recordings pipeline:
  D1 1,347 signals, 1,169 fills, **raw +11.9 / cal +0.2** vs ourspeed **+13.2 / +1.5**. Per lot (1,340 joined on mint+slot+index): 1,318 identical to < 1 mSOL,
  gross +15.72 vs +16.58; the whole gap is the **22 PumpSwap exits** (−0.86 SOL): ourspeed sold at his realized price per token, I sell into the pool
  after his sell at our own landing with our own impact and the pool fee (correct for a copier that lands 66 ms behind him). The remaining −0.4 is 7 buys
  that are in the recordings but not in his lot table (duplicate-index buys / no sim row).
- D0 replica: 1,325 signals, 1,114 fills, **raw −8.26 / cal −22.46** vs ourspeed **−7.7 / −21.8**; 1,309 of 1,320 joined lots identical to < 1 mSOL,
  non-PumpSwap difference exactly 0.000 SOL, the 11 PumpSwap exits −0.98 SOL (same reason as D1). Fills identical (1,109.7 vs 1,109.7).
- Frozen rules on D0: 1,412 signals, 1,158 fills, raw +1.46, f20fast −11.65, f20hold −80.6, **cal −8.45**, stop raw −0.99 / cal −10.90;
  E2x1 signals raw −1.94 / cal −9.20 (1,025), Grozoe +3.40 / +0.75 (387); top-5 +4.99; ex-top-5 raw −3.53, cal −13.40; 26 timeouts, 12 PumpSwap exits. FAIL on D0 as well.
- Frozen rules on D1 (both wallets, cap 0.5, timeout, band, lockout): 1,435 signals, 1,214 fills, raw +7.69, f20fast −2.32, f20hold −71.9, **cal −0.69**,
  stop: raw +3.94 / cal −4.44; E2x1 signals raw +8.59 / cal +1.94 (1,102), Grozoe −0.89 / −2.63 (333); top-5 = +9.19 (119 % of raw); ex-top-5 raw −1.50, cal −9.84;
  30 timeouts, 23 PumpSwap exits. E2x1-only signals: raw +9.86 / cal +1.83. → On D1 the frozen rules would FAIL the bar (cal < 0, f20fast < 0). The forward test decides.

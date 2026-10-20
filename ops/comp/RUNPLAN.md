# 5-run live plan — v2 (2026-10-20, after the exit sim + dry run). Owner rule: every run >= break-even.

Fixed in every run: rule #2 (creator bundle 3-5 SOL + Lunar-tipped create) + base filter + close-leader gate (5 ms)
+ create <= 150 ms into its slot; guard verifies every fire on chain. Exit = SELL ALL ~450 ms after the buy lands
(sim: best at every landing position; ladders/longer holds lose at our landing — see SIM_LADDER.md).

| Run | Size | Buy fee | Lever tested | Run stop | Pass |
|---|---|---|---|---|---|
| 1 | 1.5 SOL | ~0.025 (CU 95k x 110M = 0.0105 + Jito 0.012 + LandX 0.001) | does the fee move our landing to <= +100? | -0.5 SOL | >= 0 |
| 2 | up: 2 SOL / down: 1.5 | up ~0.045 (CU price 200M + Jito 0.025) / down ~0.018 | fee step from Run 1's landing | -0.5 | >= 0 |
| 3 | base; 2x (<= 4 SOL) on confident picks | scales with size | confidence sizing (signal from sim: dev >= 4 / fresh creator / Lunar tip size) | -0.7 | >= +0.3 |
| 4 | +33% if 1-3 > 0 | as 3 | exit timing 300 / 450 / 650 ms, replayed on our own trades | -0.8 | >= +0.3 |
| 5 | 2 / 4 SOL | ~2% of size | scale + more launches (5-9 SOL bundle band, rapidlaunch if paper-proven) | -1.0 | >= +0.6 per 3 h ($500/day pace) |

Every run: 20 buys or 3 h; entry cap ~15% over the post-bundle price (--fill-cap 1.6); profit lock 0.3:0, 0.6:0.3.
Run 2 rule: Run 1 median landing worse than +100 or > 25% next-slot -> fee UP; landing <= +25 -> fee DOWN 25%.
Between runs: run >= 0 -> next step; run < 0 -> fix ONE lever (landing / entry / exit from per-trade data), repeat.

Sim expectation for Run 1 (20 trades x 1.5 SOL): landing +25 -> ~+1.3 SOL; +100 -> ~+0.5; +200 -> ~0; next slot -> ~-0.15.
Single-run noise is large (one trade swings ~+-0.25 SOL), so a run with a real edge can still end slightly negative.

Status 2026-10-20: Run 1 built (host commit 0d628e0), deployed /root/run1 (run1.sh live — NOT run), zero-cost dry run
clean (2 fires in 20 min, both rule #2 on chain, decide->send 64-70 us). Needs: wallet ~4-5 SOL (has 0.186) + owner go.
Wallet per run: 1-2 ~4-5 SOL, 3 ~8, 5 ~10-12. Alpenglow 2026-10-21 14:50 UTC -> re-check the create-timing gate after it.

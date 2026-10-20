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

Status 2026-10-20 (later): AUDIT FIXES done on the host (/home/moiz/sniper-audit/FIXES.md): C1 open-position accounting,
C2 sell retries + fallback path, H1 SIGTERM drain + guard_run1.py, M1 slip cap re-signed at the decision (+~4 µs),
M2-M7, L1-L11. Server folders renamed: engine /root/sniper-run1/target/release/snipe_engine, env /root/sniper/deploy/.env.
Run-1 flags now: --slip-cap-bps 1500 (fill-cap 1.6 fallback), --land-timeout-ms 3000, --hold-slots 3 (fallback --hold-ms
450), --sell-fallback-path nozomi, --max-buys 20 (budget 31 on landed buys), --fast-verify. NOT deployed, NOT run:
next = deploy, zero-cost dry run (incl. a SIGTERM drain test), CU simulate check, then the owner's go.

Status 2026-10-20 (audit 3, FIXES.md "Audit 3"): H-1 (fallback RPC RMR_RPC_URL for the exit path, cached-blockhash
sells, UNSOLD retried in the background until exit, one more sell at EXIT CHECK), M-1 (SIGHUP = stop + drain), M-2 (real
error of every failed buy, 3 non-slippage failures stop new fires), M-3 (owner-approved: on-chain slot deadline
--buy-max-slot-delta 1 via a Lighthouse clock assertion, verified at start-up or no start), M-4 (--sell-held resolves
router creates), M-5 (owner-approved: every sell to staked-rpc + nozomi, --sell-retry-s 1). NOT deployed, NOT run.

**How to start Run 1: DETACHED.** `bash /root/run1/run1.sh run1` now re-executes itself under `setsid nohup` with stdin
from /dev/null (output /root/run1/run1_run1.out, engine log /root/run1/live_run1.log), so a dropped SSH session cannot
kill it; never start the engine binary directly from an interactive shell. Same for `dry_run1.sh`. (The engine also
treats SIGHUP as stop + drain.)

**"Run stop -0.5 SOL" means: STOP NEW FIRES at a run PnL of -0.5** (balance + open positions at cost, 2 consecutive
polls), not a cap on the loss. Positions already open (<= 2 x 1.5 SOL with --max-inflight 2) still have to be sold:
worst case = -0.5 minus the losses of up to 2 open positions (e.g. two -20% positions: about -1.1). When it trips, the
engine logs `OPEN AT STOP: ... worst case (all to 0) ...` with every open position and its cost.

Status 2026-10-20 (ALT fix + audit 4 + owner's sell-speed rule; FIXES.md): lookup tables of raw-shred txs are resolved
from a cache (HQ4G6Fjm launchpad creates were skipped as non-SOL; --alt-cache-file /root/run1/alt_tables.txt). The SELL
path makes no RPC between the decision and the first write (cached blockhash refreshed from both RPCs every 400 ms, amount
from the landing watch / a background read, else min_out); every exit read races both RPCs (1 s cap). Logs per sell:
SELL-DECISION landing->decision_ms, SELL-TIMING decision->send_us and decision->first_sell_landed_ms. A slot-deadline
failure that landed within create + 1 stops new fires at once; slot-deadline failures count toward the 3-failure stop.

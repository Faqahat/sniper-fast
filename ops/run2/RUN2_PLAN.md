# Run 2 plan (prepared overnight 2026-10-20/21)

**Recommendation: run it.** Same rule and size as Run 1. Two changes: how the buy is sent, and when we sell. Start before 14:00 UTC (Alpenglow upgrade at 14:50 UTC).

```
tmux new -s prod
sudo bash /root/prod/run_prod.sh --size 1.5 --max-buys 20 --max-loss 0.5 --minutes 180 --tag p2 --no-dz
```

Drop `--no-dz` only if DoubleZero is back (`ip link show doublezero1` shows the interface). Stop any time with Ctrl-C in the tmux window.

## Why Run 1 lost, measured
- **The good launches were taken before we landed.**
  - We decide and send 2–5 ms after seeing the create, but our buys landed 57–138 ms after it.
  - The launches worth having went to wallets landing at 17–60 ms (dK, 4yFAz, 9X).
  - We filled only the 2 launches nobody else wanted.
- **The delay was delivery, not decision.** Three causes, from 67 route probes, 9 buy-shaped probes (real pump buys that fail on purpose and never buy a token), our 18 real sends, and peers' buys in 172 launches:
  1. **Jito tip outside a bundle.** A buy carrying a Jito tip that reaches a Jito-client or Harmonic leader outside a bundle lands late (median position 178th). Jito bundles themselves take about 53 ms.
  2. **Multi-route sends on Harmonic.** On Harmonic leaders, every multi-route send took 96–148 ms (7 of 7). The same buy through **one** route took **27–34 ms**.
  3. **Astralane never worked.** Our key was rejected (HTTP 401). The new key works.

## What changes
| | Run 1 | Run 2 |
|---|---|---|
| Harmonic leaders | Jito bundle + nozomi + staked-rpc | **nozomi only** |
| Jito-client leaders | Jito bundle + landx + staked-rpc (+nozomi) | **nozomi + helius + astralane + landx + staked-rpc, no Jito tip** |
| BAM leaders | Jito bundle + landx + staked-rpc | same + nozomi + astralane |
| Sell | 1 slot after landing | **2 slots after landing** |
| Everything else | rule #2, close leaders ≤5 ms, create ≤150 ms, 1.5 SOL, priority 0.011, cap 15%, max 20 buys, kill switch −0.5, profit lock, 180 min | unchanged |

## Landing time (ms after the create, when our buy appears in the feed)
| Leader | Run 1 / old routes | New routes (FRZ, tonight) |
|---|---|---|
| BAM | 19–23 | **17.6, a real buy, first outside buyer** |
| Jito client | 57–133 (Run 1); 9–33 and 132 (edge checks) | 17.4, 51.6 (buy-shaped, new fan-out) |
| Harmonic | 96–148 (7 of 7) | **26.6, 29.5 (nozomi), 31.6, 33.6 (staked-rpc)** (buy-shaped, one route) |

## CORRECTION (2026-10-21 11:00 UTC): more conservative expected numbers
My first what-if (the table below) was too optimistic. Two bugs:
- my block recorder cut creator bundles short when two bundle buys shared one transaction;
- my replay ignored faster buyers whose size our feed under-reports.

The research model (`ops/research/filters.py`, correct bundles and buyer matching; rule #2 rebuilt from the blocks matches 48 of 48 engine fires) gives:

| Rule #2 | Launches | PnL, sell S+2 | Per launch | If we land 20 ms slower |
|---|---|---|---|---|
| Evening (1 h dry run + Run 1) | 19 | +2.52 SOL | **+0.13** | +0.07 |
| Older + overnight (never used for tuning) | 31 | +1.79 SOL | **+0.06** | +0.04 |

**Realistic expectation: +0.05 to +0.10 SOL per launch at 1.5 SOL.** In the evening that's about 12 launches an hour, so about +0.6 to +1.2 SOL an hour.

Live paper trading this morning (same model): 5 trades, +0.074 SOL.

## First what-if (superseded by the correction above; kept for reference)
| Our landing | PnL, sell S+1 | PnL, sell S+2 |
|---|---|---|
| 15 ms | +4.30 SOL | +4.41 |
| 25 ms | +2.58 | +3.08 |
| 35 ms | +2.23 | +2.71 |
| 50 ms | +1.48 | +1.96 |
| 75 ms (about Run 1) | +0.12 | +0.60 |

Per leader type, with tonight's measured landing times (BAM 18, Jito client 35, Harmonic 128 ms): **+3.4 SOL over 31 launches, about +0.11 per launch.**

Risk over a 30-launch run (resampled 20,000 times):

| Landing scenario | Chance of a loss | Chance of hitting the −0.5 kill switch | Median |
|---|---|---|---|
| Measured tonight | 1% | 3% | **+3.2 SOL** |
| Pessimistic (Jito client 52 ms) | 9% | 11% | +1.6 |
| Run 1-like (75 ms) | 27% | 20% | +0.5 |

- **It's a "many small losses, few big wins" strategy.** The median launch is −0.01 to −0.03 SOL, and the top 3 winners carry most of the profit.
- **The price cap keeps losses small.** Only 2 of 31 lost more than 0.1 SOL.
- **Most of the money is on Jito-client leaders** (13 of 31 launches, +2.4 to +3.0 SOL when we land in 35 ms or less).

## Dry run of Run 2's exact setup (zero cost, 25 min, 00:48–01:13 UTC)
- **2 fires; the guard confirmed both against rule #2 on chain.** All 53 presigned buys were identical, with 0 mismatches.
- **Harmonic leader Fd7btgyS: the buy went to nozomi only**, as intended.
- **One wrinkle.** When the create is in a Harmonic leader's **last** slot, the engine adds the next leader's routes, so we get a 5-route send with a Jito tip on a Harmonic leader (seen once: 5ZqveVff → BAM).
  - That's about a quarter of Harmonic launches, which carry little profit; the cost is mostly a refusal (about 0.011 SOL).
  - Fix built and dry-run tested: `--no-union-harmonic` (off unless the flag is given), build `8a9b7b55…` in `/root/sniper-run2/`.
  - The 40-min dry run with it passed: 3 fires on Jito-client leaders (JUPiTERr, 6NDen7aD, HEL1USMZ), all routed nozomi + helius + astralane + landx + staked-rpc with 0.004 tips and no Jito tip, 1040 bytes, sent 0.1–0.2 ms after the decision; 96 presigned buys identical; the guard confirmed all 3. No Harmonic last-slot launch came up, so the flag's branch wasn't exercised.
  - **To use it (your OK):** copy `/root/sniper-run2/snipe_engine` over the Run binary (keep a backup) and add `--no-union-harmonic` to FLAGS in `run1_common.sh`. Without it, Run 2 is fine; it just loses a little on those few launches.

## Watch-outs
- **DoubleZero is down.**
  - At 00:00 UTC our Edge seat's access pass (`AvgA4iDx…`) dropped to "edge_seat: 0 feeds", and the tunnel was removed.
  - That's an account or billing matter with DoubleZero ($1,500/month seat) and needs you.
  - Until it's fixed, start with `--no-dz` (Kaldera/erpc feeds, about 1.4 ms slower). Without the flag the launcher refuses.
- **Alpenglow upgrade at 14:50 UTC today.** Finish Run 2 before it, or wait and re-validate timing after it.
- **Evidence for Jito-client leaders is thin** (2 buy-shaped samples on the new route).
  - Stop rule: if the first ~5 fires on Jito-client leaders land later than about 60 ms (I'll report each fire's landing time), stop and reassess.
  - C8Bey3LK is slow for everyone (dK took 59 ms there too).
- **The sample is small:** 31 launches. The model matched Run 1's actual fills to within about 0.02 SOL per trade.

## Other notes
- FRZ (DEV) is empty: 0.0009 SOL. Top it up with about 0.1 SOL if you want more probe tests.
- The Harmonic bundle route now authenticates, so the whitelist may have come through. It's untested and a candidate for Run 3.
- Ideas for Run 3, once Run 2 confirms the landing times:
  - 2.0 SOL size (+35% in the what-if);
  - test a 30M vs 110M µL/CU priority fee;
  - try the Harmonic bundle route.
- Late creates (150–217 ms into the slot) don't pay in the what-if, so the 150 ms gate stays.

Tools: `ops/run1/landpos.py`, `bundlestudy.py`, `bsagg.py`, `landtime.py`, `probe_routes.sh`, `probe_buy.sh`, `probe_report.py`; `ops/sim/sim_land.py`, `mini_record.py`.

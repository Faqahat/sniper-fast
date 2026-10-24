# Run 2 (PROD p2m), 2026-10-21 16:53–17:33 UTC: result and paper-vs-live check

**Run settings:** 0.5 SOL per buy, rule #2, new routes, exit at S+2, `--create-ms-src wall`. The owner stopped the run.

**Result:** 3 fires, all 3 filled. A 4th launch (yfpXQY1d) was skipped by the create-time gate (created 159 ms into the slot). −0.084 SOL (4.1414 → 4.0574). Every fill sold at the same price it bought; the loss is fees, about 0.028 SOL per trade.

## What was wrong with the paper numbers (measured)

### 1. Landing time
`filters.py` places our buy 35 ms after the create on Jito-client leaders (32 on Harmonic, 20 on BAM). Those values come from the 10-20/21 night test sends, before Alpenglow. Run 2's live buys arrived later:

| Launch | Leader | Our buy seen | Position |
|---|---|---|---|
| LrvusJQD | C8Bey3LK, Jito-client | 73.0 ms after the create | 5 ms behind a 0.36 SOL buyer |
| 93y1xPeF | vu1sGn2f, Jito-client | 75.1 ms | nobody else bought |
| 9PyH8BUn | Fd7btgy, Harmonic | missed slot S, landed in S+1 | behind a 2.96 SOL sniper (Ef3WXs) |

On 9PyH8BUn the create came 133 ms into a ~209 ms slot.

### 2. The model matches live when our buy is placed where it really landed
Same `run()` as before; values in SOL.

| Launch | Model at 35 ms | Model at real landing | Live |
|---|---|---|---|
| LrvusJQD | −0.019 | −0.028 | −0.029 |
| 93y1xPeF | −0.028 | −0.028 | −0.029 |
| 9PyH8BUn | +0.050 (in S, right after the bundle) | (missed slot; S+1 not modelled at 75 ms) | −0.026 |

The fee and curve math is correct. The landing input was wrong.

### 3. Rule #2 at the real landing speed
Script: `scratchpad recon/tsens.py`; same 77 launches as FILTERS3. Values are SOL per launch at 1.5 SOL.

| Landing assumption | All launches | Today (D+E) | In-sample A |
|---|---|---|---|
| 35 ms (old paper) | +0.058 | +0.002 | +0.133 |
| Jito 75 ms | +0.021 | −0.019 | +0.027 |
| All classes +40 ms | +0.000 | −0.020 | — |

At 0.5 SOL, today's launches give −0.008 at 35 ms and −0.015 at 75 ms.

### 4. Why the forecast was high
The Run 2 forecast (a bootstrap over 58 paper trades) had two problems:
- it pooled in the in-sample evening, the data rule #2 was picked on;
- it used the 35 ms landing.

FILTERS3 had already shown rule #2 flat on 10-21 data (D +0.007, E −0.007).

## Exits at the real landing time
`exit_sim.py`, new `T_OVR` / `T_ADD` overrides. 73 rule #2 launches, 1.5 SOL, SOL per launch.

| Exit | Today (C–E) at 35 ms | Held-out (B–E) at 35 ms | Today at Jito 75 / Harmonic 80 | Held-out at Jito 75 / Harmonic 80 |
|---|---|---|---|---|
| S+2 (what we ran) | +0.004 | +0.037 | −0.016 | +0.003 |
| S+3 | +0.022 | +0.052 | +0.001 | +0.010 |
| S+4 | +0.031 | +0.056 | +0.010 | +0.012 |
| S+7 | +0.018 | +0.053 | −0.003 | +0.014 |
| S+20 (~4 s) | −0.137 | −0.053 | −0.159 | −0.090 |
| S+60 (~12 s) | −0.223 | −0.102 | −0.241 | −0.136 |
| Best rule (up at S+1 → hold to S+7, else S+2) | +0.032 | +0.057 | +0.009 | +0.016 |

Longer holds lose on average: the price falls about 7–13% within 4–12 s (−0.09 to −0.24 SOL per launch after fees). Even at 35 ms, today's launches made only +0.00 to +0.03 per launch, so faster landing is necessary but may not be enough.

Run 2's own trades held longer (gross on 0.5 SOL, before about 0.028 fees):

| Trade | ~5 s | ~10 s | ~1 min |
|---|---|---|---|
| 9PyH8BUn | +0.30 | +0.30 | +0.30 (peak 1.81x at 3.6 s) |
| LrvusJQD | −0.05 | −0.10 | −0.14 |
| 93y1xPeF | −0.01 | −0.08 | −0.10 |

## Verdict
At our real landing speed, rule #2 is break-even at best, whatever the exit (about +0.01 per launch, within noise). No more live runs on it.

The same rule at 35 ms was +0.04–0.06 per launch on held-out data, so landing speed is the lever.

**Open question:** why live buys land at about 75 ms when the night test sends landed at 25–35 ms. Possible causes:
- Alpenglow;
- the 5-route fan-out on Jito leaders;
- those particular leaders.

Answering it needs capped FRZ test buys, which needs the owner's OK and a top-up.

## Where the paper profit came from (2026-10-21 evening, `scratchpad recon/window.py`)
The owner's point: we can't beat the dev's bundle, and the 3-block flip fails whether we're early or late.

Checked on all 77 rule #2 launches:
- **Paper never placed us before the creator's bundle.** It always placed us right after it.
- **Many launches have no buyer after us.** With a 35 ms landing, 24 of 77 launches have no outside buying after our buy through S+2. At 75 ms it is 32 of 77. All 5 live fills were like this.
- **The 35 ms vs 75 ms gap** is +4.53 SOL across the 77 launches.
  - +4.38 SOL of it comes from 33 launches where outside buyers landed 35–75 ms after the create, mostly pro snipers (3yrJE1, DRWPSr, 9qz7cW, 4yFAz7, AHwJSn, 9Sh2fd).
  - 3 launches alone (5P2QdrLQ, BcoN3Ee7, 6Ru7g16r) make +3.0 SOL.
  - 5P2QdrLQ was Run 1 fire #1. Live, the pros landed first, the price was 1.76x, and our buy was refused.
- **Without landing ahead of those pros**, i.e. our buy at 75 ms on every class, rule #2 makes −0.001 SOL per launch.
- **Holding longer does not help.** Even with a 35 ms landing, S+20 loses 0.05–0.14 SOL per launch.

**Conclusion:** buying after the bundle and selling within 3 blocks only pays if we land ahead of the pro snipers on the few hot launches. We have never done that live. On every other launch the result is zero or a loss, early or late. Rule #2 is retired.

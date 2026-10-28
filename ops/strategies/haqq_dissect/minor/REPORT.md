# Analyst I (minor bots): footprints proven, picks not reproducible, none worth copying (10-28 ~03:30 PKT)
Saved by the main session from the agent's reply. Code: this folder (m1–m11). Tables: /home/moiz/sniper-data/haqq_dissect/minor/ (m2–m11 .txt). **Examples: examples.json** (6 per claim, GMGN + Solscan links).

## The bots (MEASURED, code-matched lots, 10-22 03:07 → 10-28 01:12)

| Code | Name | Lots | Size | Net SOL [90%] | mSOL/lot | Days > 0 | Fail rate |
|---|---|---|---|---|---|---|---|
| 244 | **Binary-Timer Dipper** | 8,425 | 0.247 (+ a 0.01 tier) | +20.5 [+8.4..+32.9] | +2.4 | 6/6 | ~0% (no limit) |
| 226 | **Band Bouncer** | 1,907 | 0.494 | +12.1 [+7.0..+17.3] | +6.3 | 6/6 | 29% |
| 231 | **Band Bouncer Jr.** | 369 | 0.247 | +3.6 [+1.4..+5.9] | +9.8 | 6/6 | 54% |
| 234 | **Dead-Curve Fisher** | 4,852 | 0.74–1.24 (0.494 from D5) | +5.2 [−6.4..+17.3] | +1.1 | 4/6 | 50% |
| 249 | **Probe-then-Scale Tester** | 606 | 0.01 → 0.395; stopped after D3 | −0.02 | | 1/6 | |
| 251 | **4-Second Momentum Flipper** | 549 | 0.10–0.40 | +0.57 | +1.0 | 3/6 | |
| 252 | **Micro Momentum Probe** | 402 | 0.01 | −0.50 | −1.2 | 0/6 | |

**Footprints:**
- **244:**
  - Entry: 47% within 3 slots of a ≥5% dump on young tokens; the rest on busy young tokens.
  - Exit: BINARY timers at 8 / 16 / 32 / 64 slots; ignores price.
  - 33% of lots sell 50% first. These are the source of haqq's "partials".
- **226:**
  - Entry: 0–5 slots after a dev (52%) or creation-slot bundler (39%) dump, tokens 8–29 slots old; 76% of buys happen while 247/248 hold.
  - Limit: a BAND order, filling between 0.895× and 1.087× the post-dump price.
  - Exit: a 2–7 slot timer, cut short by profit.
- **231:** dev dumps on the newest tokens; band order; exits at 5 / 8 / 20 slots, faster when +20%.
- **234:**
  - Entry: same slot after a sell takes the curve back to the 30-SOL floor (it buys 1.75% of such sells); limit 5%; costs 2.28 mSOL per lot.
  - Exit: take-profit, or a timer of 50 / 100 / 300 / 5,650 / 9,000 slots. Early exits +94.4 SOL; timer exits −89.0. A lottery: the top 10 lots make 66% of its gross.
- **249:** exits at exactly 200–202 slots.
- **251:** buys after heavy outside buying on older tokens; 19–20 slot timer.
- **252:** a 2–3 slot timer with a stop-loss.

**0.01 SOL lots = live paper trading** (INFERRED): a new strategy runs at 0.01, then scales up or stops (249 and 252 were stopped after losing). 244's 0.01 tier is a permanent shadow tier.

## Can a simple rule reproduce their buys? No (fitted D0–D2, tested D3–D5)

| Bot | Precision | Recall |
|---|---|---|
| 244 | 9% | 22% |
| 234 | 16% | 33% |
| 226 | 4–9% | 1% |
| 231 | 6% | 14% |
| 249 / 251 / 252 | ≤ 4% | ≤ 1% |

They buy 0.03–1.1% of dumps; the selection signal is not in the 28 market features.

## For us (dv8 replay, calibrated, held-out D3–D5 total)

| Bot | Explicit rule, NOW | His actual picks (not knowable), NOW → CHEAP | His picks, NOW, 10% fewer followers |
|---|---|---|---|
| 226 | −1.38 | +0.14 → +1.54 | −2.52 |
| 231 | −4.00 | +0.91 → +1.14 | +0.07 |
| 244 | −30.4 | +0.61 → +3.75 | −6.17 |
| 251 | −0.24 | +0.24 → +0.48 | −0.34 |

- His band limit instead of our guard changes nothing.
- **234:** its gross per lot (+3.36 mSOL) is below our cost per fill (3.52).
- **Verdict:** no minor bot adds profit for us.
- **Ideas to note (unproven):**
  - 234's take-profit-or-long-timer exit;
  - 244's 50% partial ladder;
  - **running new strategies live at 0.01 SOL as paper.**

## Reconciliation per day (SOL; rules replayed his way)

| Day | haqq real | 247 + 248 | Minor bots real | Minor-bot rule replays |
|---|---|---|---|---|
| D0 | +38.68 | +30.98 | +7.71 | −6.88 |
| D1 | +45.35 | +35.96 | +9.39 | −9.38 |
| D2 | +49.06 | +40.43 | +8.63 | −7.73 |
| D3 | +21.40 | +18.56 | +2.84 | −11.26 |
| D4 | +30.89 | +26.27 | +4.62 | −16.02 |
| D5 | +28.10 | +20.67 | +7.43 | −20.13 |

The minor bots are 13–26% of his P&L. Explicit rules explain ~0% of it.

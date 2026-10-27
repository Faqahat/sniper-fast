# haqq-style token selector (agent, 10-28 ~00:00 PKT)

Saved by the main session from the agent's reply (the harness blocked the agent's report write). All numbers are also in /home/moiz/sniper-data/haqq_model/.

## Setup
- Tape 10-23 → 10-27 (154k tokens; haqq traded 8.4%). Split by create time: train / validate / held out = the last 24 h (39,657 tokens, haqq 2,960).
- Pre-registered in PREREG.md before modelling.
- Features: chain data up to the decision time only, with haqq's own trades removed. Model: numpy GBDT.

## Match on the held-out day (MEASURED)
| Decision time | AUC | Match | Precision | Picked |
|---|---|---|---|---|
| ~3 s (+14 slots), pre-registered threshold | 0.971 | 78.4% | 57.0% | 10.3% |
| ~3 s, threshold set at 85% on validation (post-hoc) | | 83.4% | 52.9% | 11.8% |

Driver: early non-dev buy SOL (bundles and early buys). "≥ 5.5 SOL non-dev buys by +3 s" alone gives 85.5% match at 44% precision.

## P&L on the held-out 24 h, run-28 config (INFERRED; pre-send 0.50 k4 QUIET + M2 0.55)
| Set | Realistic total (per h) | Calibrated total (per h) |
|---|---|---|
| All tokens | +8.61 (0.36/h) | +3.61 (0.15/h) |
| haqq's tokens (hindsight) | +7.86 (0.33/h) | +4.28 (0.18/h) |
| Knowable "he traded before the trigger" | +3.21 (0.13/h) | +1.41 (0.06/h) |
| **Model, 83.4% match** | **+5.95 (0.25/h)** | **+3.26 (0.14/h)** |

## Why the picks lose in total
- 29% of armable pre-send triggers fire before +3 s, before a 3 s model can decide.
- Later triggers on tokens the model rejects are still positive.
- Per fill the picks are better (+0.0146 vs +0.0104).

## Verdict
- The model matches haqq well (83% at 53% precision, AUC 0.97), but trading only its picks makes less than trading everything.
- Use the score as a sizing or input signal, not a gate. This rests on one held-out day.

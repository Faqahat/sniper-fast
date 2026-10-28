# migpaper scorer validation on the 10-28 test day (done 10-28 23:45 PKT, before the forward run scored anything)

Method: the windowed scorer (`mp_score.py`, 2-h windows 10-28 00:00 → 20:00 PKT, 3-h look-back, 15-min look-ahead, decoded from the local
recorder copies) with the **train-only models** (m2 / m3 fits reproduced exactly: max |p − feat_p.pkl| = 0 on all 8,651 test rows) and the
initial wallet / creator stores, compared row by row (`mp_validate.py`) with migrate's replay (sim_pre_2.0.pkl / sim_react_2.0.pkl, exits
mig+2 / −20 % / 120 s and mig+2 / pd0.3 / 120 s). Outputs: `val/results.jsonl`, `val/trades.jsonl`, `val/recheck_*.jsonl`.

## Result
| 10-28, pre-send 2 SOL −20 % stop | entries | SOL |
|---|---|---|
| REPORT.md (its definition: PKT day 00:00–21:26, non-edge rows) | 54 | **+3.661** |
| replay restricted to the scored windows (00:00–20:00) | 53 | +3.534 |
| scorer, same windows, first pass (float64 features) | 58 | +3.426 |
| scorer, same windows, after the float32 fix (= what the loop runs) | 59 | **+4.129** |

(pd-stop / reactive rows behave the same: report +4.624 / +2.868 / +3.914, replay-in-windows +4.498 / +2.809 / +3.855.)

- 226 entrable V=105 first crossings produced by the scorer in the windows; all 226 join the replay's rows (mint, slot); 231 in the replay.
- **52 rows selected by both: per-row P&L identical to the lamport (max |diff| 0.000) in all four variants; fills and tries identical.**
- Gap 1 (first pass): one row ([JDzUd2tc](https://gmgn.ai/sol/token/JDzUd2tcvsijFkjZNEChkxvPAzK5kJpsWBuEAEmopump), the day's best trade, +0.703)
  scored p30 0.7997 vs 0.8115: every feature was equal up to float32 rounding (m1 stores X as float32; the scorer computed float64) and the
  GBDT splits on the rounded value. **Fixed**: the scorer now casts the feature vector to float32 before predicting; re-scored window
  00:00–02:00 gives p30 0.8115 and +0.7028 for that row, identical to the replay.
- Gap 2 (+0.595, 6 entries 19:06–19:29 PKT): the replay drops "edge" rows within 2,100 s of the recorder hand-over (19:30 PKT tail) by
  convention; the scorer scores them (both recorder runs' chunks are loaded; all 6 graduated and resolved). Not a scorer error; in the
  forward run such rows are flagged `unresolved` only if the tape really ends before resolution.
- Gap 3 (+0.127): one replay entry at 20:00–21:26 PKT, outside the validation windows.
- Look-back: 5 replay entrable rows are missing from the scorer — tokens 7–11.5 h old (older than the 3-h look-back, their create is not in
  the tape). None had p30 ≥ 0.8 (0.06–0.33), so no entry was lost; in the replay only 0.7 % of entries were older than 2 h.
- The remaining difference between scorer and report is therefore convention (edge rows, window range), not computation.

## ARM-gate row (10-29 00:29 PKT, before the forward run scored anything)
Scorer with the ARM-gate (FROZEN.md 10-29 addendum) on 10-28 00:00–20:00 PKT, val models (m2 seed-0 train-only p30), outputs `val/arm_*.jsonl`.
Audit side: the audit's own feature code (`mig_audit/m1fix.py arm`, membership fix off, as the scorer) + the same val p30, replay `sim_pre_2.0` (−20 %).
- 226 of 226 scorer rows join; arm index equal on 226/226; max |p30_arm diff| 5e-05; 0 selection flips; 38 rows selected by both with a replay: per-row P&L identical (max |diff| 0.000).
- ARM-gate 10-28: scorer **41 entries, +3.428 SOL**; audit code **38 entries, +3.246** (non-edge); the +0.182 gap = 3 post-hand-over "edge" rows the replay does not simulate (+0.035, +0.147, −0.000), same convention gap as above.
- Crossing-gate rows unchanged by the edit (59 entries, +4.129, as above).
- For reference: the audit's seed-0 `p_arm.pkl` (model RE-TRAINED on arm features + membership fix) selects 45 rows, +2.171 on the same windows — a different model, not the frozen-model gate tested here.

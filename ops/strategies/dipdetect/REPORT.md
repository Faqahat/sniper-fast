# Better dip detection (agent study, 10-24 ~22:45 → 23:59 PKT)

Offline replay study on the recordings. Haiku not used ($0). MEASURED = replay or chain data; INFERRED = reading.
Scripts: ops/strategies/dipdetect/ (dd1_build.py dataset, dd_lib.py replay, dd5_model.py models, dd8/dd11 tables,
dd3/dd10 skipped-dump analysis, dd12_livecal.py live check).
Outputs (5.4 GB): /home/moiz/sniper-data/strategies/dipdetect/ (model_v3_reg4_nof1.json = chosen model,
dd5_registry.jsonl = every variant, dd14_summary.txt = main tables).

## Bottom line
- **The new detector** is a GBDT trained on R2 only. It predicts what WE would make on each dump (35 ms landing, +5% guard,
  failed buys, all costs) instead of copying 3 bots. Pooled test days (R3 + R1 + R4, 39 h, both servers):

  | Landing | New detector | Now |
  |---|---|---|
  | 35 ms | +43.0 SOL | +8.8 |
  | 50 ms | +23.9 | +4.5 |
  | 75 ms | +5.4 | +2.0 |

- **Stage A, the safer first step:** keep today's envelope and swap the IMIT1 gate for the model (predicted value ≥ 0.010
  SOL), selling after ~0.85 s: +22.1 / +14.0 / +6.2 SOL vs +8.8 / +4.5 / +2.0 at 35 / 50 / 75 ms.
- **Config-only win: sell after ~0.85 s** (4 slots after the entry slot; in the engine roughly `--hold-slots 5`, verify).
  With today's picks: +12.4 / +7.3 vs +8.8 / +4.5 at 35 / 50 ms. Better than 1.3 s on all 3 test days; 4 s was better on
  the R3 night only.
- **Live check:** on the 74 run-10 fires, the replay at 35 ms gave a fill rate of 0.51 vs 0.47 live. On the 23 trades filled
  in both, it gave −0.0105 SOL per fill vs −0.0055 live, so it is not optimistic (small sample).

## Results by split (both servers, 0.55 SOL; SOL, attempts, fill rate, per fill)
| Detector | R2-val 6.5 h | R3 21 h | R1 14.9 h | R4 3.3 h |
|---|---|---|---|---|
| Now (IMIT1 top4, 1.3 s / −10%), 35 ms | +2.18 (123, 64%) | +4.42 (385, 62%) | +4.06 (385, 68%) | +0.34 (78, 51%) |
| Now + 0.85 s exit, 35 / 50 ms | +2.83 / +1.38 | +4.72 / +2.43 | +6.41 / +3.90 | +1.30 / +0.99 |
| Stage A (≥ 0.010, current envelope, 0.85 s), 35 ms | +4.86 (199, 60%) | +11.18 (769, 62%) | +8.55 (625, 69%) | +2.35 (139, 49%) |
| New detector (≥ 0.0041, all dumps, 0.85 s), 35 ms | +9.15 (581, 69%) | +25.30 (2157, 68%) | +13.17 (1586, 76%) | +4.55 (365, 67%) |
| New detector, 50 / 75 ms | +4.44 / +2.44 | +14.35 / +6.00 | +6.92 / −0.97 | +2.64 / +0.38 |

## Robustness
- **Hour-block bootstrap, 90% intervals:** R3 +21.0 [+15.6, +26.6] at 35 ms and +12.4 [+8.5, +16.4] at 50 ms; R1 +7.1
  [+3.8, +11.2] at 35 ms.
- **Without the top 1% of trades:** still R3 +20.0, R1 +8.9.
- **Spread:** 1,528 tokens, at most 8 trades per token; positive in 21 of 22 hours.
- **Cost-proof:** at +0.004 SOL per fill, still +19.5 vs +3.4.
- **Leak-free:** the earner list and Haiku labels were removed.
- **Clean holdouts:** R3 and R4 (R1 overlaps IMIT1's training data).
- **Tries:** 16 model variants and 400 exits. The best-of-16 inflation is at most about 10 SOL, leaving at least +33 / +14
  vs +8.8 / +4.5 (INFERRED).

## What the skipped dumps taught us
- **Round-trip cost is about 0.019 SOL**, so a dip must bounce about 3.5% within the hold to break even.
- **Every coarse group loses on its own** except the IMIT1 top tiers. The value is in combining features.
- **New value on R3:** in-envelope dumps IMIT1 scores too low (+12.7 SOL) and out-of-envelope dumps (+8.3), best with
  3.9–10 s since the last buy and sells of 0.5–1.08 SOL.
- **Not worth widening:** tokens older than 343 s, and drops under 4.65%.
- **KEY:** the new picks are dips the fast bots skip. The 3 IMIT1 wallets buy within 1 s on 26–31% of them vs 57–74% of
  today's picks, so failed buys are 24–33% vs 32–49%.
- **Time of day:** weakest 12–18 PKT, positive in every 3-hour block.

## Proposed changes
| # | Change | Expected gain | How sure |
|---|---|---|---|
| 1 | Sell after ~0.85 s (optional TP +10%) | +1.5 to +2 SOL/24 h with today's picks | Medium |
| 2 | Stage A: model gate ≥ 0.010 in the current envelope + 0.85 s exit | +5 to +8 SOL/24 h at 35–50 ms; about 39 attempts/h vs 22 | Medium (no live data) |
| 3 | Stage B: cut 0.0041, sell ≥ 0.5 SOL, any time since the last buy | +10 to +20 SOL/24 h at 35–50 ms; about 92 attempts/h | Low–medium |
| 4 | Size 1.0 SOL when the predicted value is ≥ 0.010 | about +27% at 35–50 ms | Low |
| 5 | Cheaper sending (nonce fan-out) | each 0.001 SOL saved per fill ≈ +1 to +2.5 SOL/24 h | INFERRED |

A 25-feature version keeps most of the value and is easier to port to the Rust engine.

## Shadow-test plan
1. **Port the model to the engine.** Parity check on the recorded R4 hours: score correlation ≥ 0.99, pick agreement ≥ 95%,
   decision time ≤ 1.5 ms.
2. **24 h shadow on both servers.** Log every ≥ 2% dump with its score and a shadow one-position book; replay the next
   morning. Pass: Stage A ≥ +0.015 per fill and ≥ 2× the baseline.
3. **Probe** (owner OK, about 0.05–0.1 SOL): fail-by-design buys on about 150 Stage-A picks that IMIT1 skips. Pass: ≥ 50%
   would fill.
4. **Live A/B** (owner OK): one server Stage A + 0.85 s, the other as now; swap after 4 h. Caps: 40 trades and 0.3 SOL loss
   per server. Pass: ≥ +0.010 SOL realized per fill over ≥ 60 fills, with a fill rate ≥ 45%.

# Analyst F (bots): 247 "Launch-Dump Sniper" and 248 "Big-Dump Rebounder"; can we be them? Not yet (10-28 ~04:15 PKT)
Saved by the main session from the agent's reply. Code: this folder (b0–b16). Tables: /home/moiz/sniper-data/haqq_dissect/bots/*.txt (b2, b2b, b3, b6, b7, b8b_size, b12, b13, b14, b16).
- examples.json and b9.txt: 12 claims × 6 examples with GMGN and Solscan links;
- decisions.jsonl: 3,802 lines;
- labels.jsonl.gz: 1.08 M envelope sells with bought / score.

**Replay check (M):** replaying their own entries and exits reproduces realized: 247 +66.44 vs +65.67; 248 +69.40 vs +68.44.

## The bots (M)
**247 = Launch-Dump Sniper**
- **Trigger:** buys 0–1 slot after a ≥ 5% sell by the dev (52%) or a creation-slot bundler (94% of sellers were in the creation slot).
- **Token age:** < 5 s for 76% of its buys; at ≥ 15 s it rarely buys (−6.4 mSOL/lot).
- **Curve:** 32–50 SOL after the dump.
- **Size:** 0.40 SOL, no limit.
- **Speed:** dump→buy 38 / 66 / 167 ms; 57% in the same slot; trades ahead 0 / 1 / 3 / 5.
- **Exit:** lots sold < 1 s make +43.6 mSOL/lot and 1–2 s +29.1 (6/6 days); otherwise a 15 / 20 / 25 / 30-slot timer. Lots held 4–8 s lose (0/6 days).

**248 = Big-Dump Rebounder**
- **Trigger:** big dumps; its buy rate rises from 0.6% on 5–7% drops to 10.6% on 20–30% drops; follows busy flow (≥ 20 SOL outside buys over 10 slots); tokens ≤ ~60 s old.
- **One lot per token.** Buys more often when 247 is already in.
- **Size:** 0.25 → 0.30 → 0.40 since 10-25.
- **Speed:** 64 ms; trades ahead 1 / 2 / 4 / 7.
- **Exit:** fast (2–5 slots) or a ~65-slot timer (15–60 s lots +33.4 mSOL/lot). Profits even with ≥ 8 trades ahead (+12.1 mSOL/lot, 6/6 days).

The two bots overlap on only 1,054 dumps (247: 5,699; 248: 7,248).

**Trigger breadth (b2b):**
- 87% / 83% of lots follow a ≥ 5% single sell within 0–2 slots.
- Dev chunk-selling is real: a dev's 2nd sell within 10 slots gets a 5.4% / 4.8% buy rate vs 1.3% / 1.2% for the 1st.
- The non-dump 25% are the same trigger seen late, or 2–5% dips.

**Imitation (causal GBDT, walk-forward):**

| Bot | AUC | Precision | Recall |
|---|---|---|---|
| 247 | 0.95 | 0.24–0.27 | 0.28–0.32 |
| 248 | 0.91–0.93 | 0.27–0.32 | 0.26–0.30 |

About 70% of their picks are not separable from look-alikes with tape features.

## Can we be them?
- **Landing is equal (M, b14/b16):** on 347 shared dumps we landed ahead 60%, and our median k equals theirs. Our real position replayed with THEIR exit: 248 +19.59 mSOL/lot vs +19.85 from their position.
- **The exit and the guard decide it** (248's shared dumps, mSOL/lot):

  | Setup | mSOL/lot |
  |---|---|
  | Their exit, no limit | +19.6 |
  | Their exit, +5% guard | +4.3 |
  | Our 5-slot timer | +6.5 |
  | Wave exit | +6.4 |
  | C's copy of his exit | +10.9 |

- **Their picks are genuinely better (M, b8b; real 0.2–0.6 SOL buyers, no model):** at k 2–3, 247 picks make +2.8% vs +1.0% for look-alikes; 248 picks +3.3% vs +0.5%. At k 4–7: +2.7% vs −0.3%; +2.2% vs −0.4%. 6/6–7/7 days. **SELECTION IS THE EDGE.**
- **Their exact picks at our landing with their exit:** NOW +6.0 / +6.65 SOL/day; CHEAP +8.6 / +9.9. With exits we can run (calibrated): NOW −1.0..−7.3; best CHEAP +1.55 / +2.94. Every variant goes negative with 10% fewer followers.
- **Calibration refit per exit (b6):**
  - +5% guard: a 0.61–0.89, b −0.7..−3.1;
  - no limit: a 0.83–0.96, b −4.0..−5.6 mSOL/fire (on crowded good dumps we land later than the model).

## "Our 247 / our 248" (walk-forward, SOL/day)

| Bot | NOW | S2 | CHEAP | Days > 0 |
|---|---|---|---|---|
| 247 | −0.20 | −0.07 | +0.06 | 0–2 of 4 |
| 248 | +0.05 | +0.11 | +0.08 | 1–2 of 4 |

**Our engine already takes (b12):** M2 fired on 3.2% / 5.5% of their lots and filled 0.9% / 1.3%.

## Verdict
- **"Our 247/248":** ≈ 0.
- **Ceiling:** perfect picks + their exit = +6..+10/day per bot (not achievable today).
- **The owner's point that landing is equal: CONFIRMED.** Selection is the missing piece.
- **Next:** dumper-wallet history and creator/funder clusters (analyst L is on it); dissect their < 2 s winning sells.
- **Paper (zero cost):** shadow-log our would-be landing on every 247/248 dump.

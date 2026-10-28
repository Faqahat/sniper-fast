# Analyst B (limits): is our +5% guard throwing money away? — NO (10-28 ~02:45 PKT)
Saved by the main session from the agent's reply. Code: this folder (l1–l15). Tables: /home/moiz/sniper-data/haqq_dissect/lim/ (l3, l5, l6, l6b, l8, l9, l11–l15 .txt).

## 1. haqq's limits (MEASURED, 10-22 03:08 → 10-28 00:41)
- **Failures:** 40,798 buy txs, 35,015 filled, 5,783 failed. 99.8% of failures are 6042 ("would buy less tokens than min_tokens_out").
- **Size sets the limit:**
  - 0.25 / 0.3 / 0.4 SOL: no limit (min_out = 1), 148 of 151 sampled fills;
  - 0.5: 8%;
  - 0.75–1.25: 2%, loosened to 5% / 7.5% on 10-27.
- **Reference price:** the post-dump state × (1 − limit), the same as ours. 93% match exactly. The pre-dump price never fits.
- **He decides blind to the crowd, like us:** a median 2 outside trades land between his reference and his tx, 80 ms.
- **His dip fills by price paid vs post-dump:**

  | Price paid vs post-dump | Return per SOL |
  |---|---|
  | ≤ 1.05 | +2.2 to +3.8% |
  | 1.05–1.10 | +2.3% |
  | 1.10–1.15 | +1.9% |
  | 1.15–1.30 | ≈ 0 |

- **KEY (l14), behind-crowd lots (price > 1.05 × post-dump):**

  | Lots | Count | Actual | Same lot on a 5-slot timer |
  |---|---|---|---|
  | Never added | 2,551 | −0.09%/SOL (−0.72 SOL) | −0.54% |
  | Added later | 1,637 | +5.23%/SOL (+27.0 SOL) | +1.61% |

  Every day shows the same split. The loose limit is the entry ticket; the edge comes from what he does after entry (adds, holding).

## 2. Our 1,544 live regular fires at their REAL landed position (exact curve; only follower reaction modelled)
- **Checks:** the replay reproduces live fill/fail on 1,540/1,544; on fills, +1.05 vs the wallet's +0.96.
- **Total SOL change vs live +5%** (exit = the run's own; net of 3.52 mSOL per fill and 0.53 per failed fire):

  | Guard | SOL vs live [90%] |
  |---|---|
  | +3.5% | +0.54 [−0.47..+1.54] |
  | +10% | −0.88 [−2.51..+0.90] |
  | +20% | −4.87 [−7.39..−2.18] |
  | No guard | −7.10 [−10.34..−3.84] |
  | No guard, 20% fewer followers | −18.98 |

- **Per extra fill:** −2.7 mSOL at +10%, −5.6 at +15%, −7.5 with no guard.
- **Other exits** (haqq's hold distribution, 15 or 2 slots) and his size don't rescue a looser guard.
- **Pre-send:** 1,142 live fills reproduced exactly. Looser limits lose: +5% −2.11 on bounced tries only, −4.43 when applied to every try; no limit −46.7 / −77.2.

## 3. The contradictions, resolved
- **The 10-25 guard sweep** used modelled landing, so its totals were too optimistic, but its ranking holds. dv8 never tested other guards.
- **"He profits behind the crowd":**
  - his single-lot behind-crowd buys lose too;
  - on the 222 dumps where we failed and he filled, a 5-slot timer gives him −0.92%/SOL against his actual +1.54%, which all comes after entry;
  - his cost is 0.78 vs our 3.52 mSOL.

## 4. Features
- **The price move at landing dominates.** Ours at ≤ 3.5% above post-dump make +5.5..+17 mSOL; 3.5–5% lose −3.9.
- **Send-time features** (dump 16–22%, curve 35–40, age 30–100 slots, early-buyer seller, busy tape) look good in both datasets but fail walk-forward:

  | Policy | Total over 4 test days |
  |---|---|
  | Live | −0.86 |
  | Per-feature guard | −2.56 |
  | haqq-trained buckets, +15% | −2.02 |
  | Global guard chosen on earlier days | −0.79 |

## Recommendation
- Keep +5% for regular fires and keep the pre-send limit; do not loosen either.
- **Optional:** +3.5–4% (`--dip-guard 1.035`), worth ~+0.1–0.25 SOL/day, chosen in hindsight. A send-path change needs owner OK.
- **The real lever:** adding to positions that keep running, plus exits and cost.

## Follow-up (10-28 ~04:00 PKT): loosening ONLY on selected dumps also fails (l16–l19; tables l17, l18, l19)
Method: our measured landed positions, exact curve, timer and wave exits. The replay reproduces the live baselines (regular wave +5.847 vs C's +5.85; pre-send wave +10.95 vs +10.93).

**Why H's adverse-fill pattern doesn't become money (l18, MEASURED):** on dumps worth 30–60 / > 60 mSOL that we failed live, our tries landed at ×1.136 the post-dump price with 3–4 trades ahead. Filling them with no limit (wave exit) gives −12.3 / −5.7 mSOL net. The dump pays only at the front.

**Bots 247/248 on our failed regular dumps (l19):**

| His lots | Count | Return per SOL |
|---|---|---|
| Landed ahead of our copy | 161 | **+6.44%** |
| Landed behind us | 204 | +0.03% |

Their money there comes from landing AHEAD, not from having no limit.

**Regular (Δ SOL vs live +5%, wave exit):**

| Selection | Limit | Δ | 10% fewer followers |
|---|---|---|---|
| Oracle | +10% | +0.41 | +0.09 |
| H selector | +10% | +0.48 | +0.21 |
| Creator seller | +10% | −0.57 | |

No limit loses in every row. Walk-forward: H selector +0.26 total (−0.01 with 10% fewer followers); oracle +0.08; simple rules −0.37.

**Pre-send:**
- Oracle +5%: +0.43; H selector +10%: +0.09; all simple rules: −0.21..−10.8.
- Walk-forward: oracle +0.13, H −0.11, simple rules −0.65.

**Verdict:**
- Keep the limits; optionally tighten regular to +3.5%.
- Selective loosening is worth ~+0.07/day at best: not worth an owner OK.
- **The lever is the wave exit: +2.7 SOL regular and +1.7 SOL pre-send over ~4 days, on the same live fills.**

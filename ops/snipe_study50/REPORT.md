# Target Sniper Pre-Buy Signal Study
Target wallet: `4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3`  via own program `FCdY3UTqSrbKab7ba3V6LDVSwYue2GD1xyq8tPY6Yr3o` / direct pump buys

## Sample
- **100 landed snipes** (status success, wallet = buyer[8] of a pump buy_exact_quote_in_v3).
- Scanned 494 successful txs out of 593 success / 2407 error sigs (80% of this wallet's recent txs ERROR — confirms ~79-80% failed-spray rate).
- Window: 2026-10-13 20:31 .. 2026-10-14 09:10 UTC  (~12.6 h).
- Create tx decoded for **98/100**; 2 undecoded (0 create beyond 16k-sig pagination).

## The PATTERN (pre-buy signals, ranked by consistency across the decoded snipes)
1. **Bundled dev buy present**: 47/98 had dev_buy>=1.0 SOL, 79/98 >=0.5 SOL, 80/98 >=0.3 SOL, 90/98 >=0.01 SOL (real dev buy).  Dev-buy SOL dist: p25=0.693 med=0.991 p75=2.017 (n=98).
2. **Vanilla launch** (mayhem/creator_fee_bps/holder_reward all 0): 80/98 = 82%.
3. **Create-slot entry**: delta(buy_slot - create_slot): 0 -> 80, +1 -> 18, +2 -> 0; <=2 -> 98/98, <=5 -> 98, >5 -> 0.  Delta dist: p25=0.000 med=0.000 p75=0.000 (n=98).
4. **Creator (in-window)**: fresh/single-launch 79/98, repeat(factory) 19/98. Repeat creators: 8 distinct making >1 launch (max 5).
5. **Co-snipers in create slot**: dist p25=0.000 med=1.000 p75=2.000 (n=98); share with >=1 co-sniper: 60/98.

### Buy-side (what HE paid, not a pre-buy filter)
- Buy size SOL: p25=1.507 med=1.936 p75=2.963 (n=100)
- CU price (microlamports): p25=1836749.000 med=238053866.000 p75=821940928.000 (n=57)
- Tx fee (SOL): p25=0.000 med=0.000 p75=0.015 (n=100)

## DECISION RULE a clone can apply at slot 0 from only the create tx
```
ACCEPT a launch to snipe IFF, from its pump create_v2 tx alone:
  (a) launch is VANILLA  (11 trailing flag bytes == 0: mayhem=0, creator_fee_bps=0, holder_reward=0)
  AND (b) bundled dev buy (bonding-curve SOL delta in the create tx) >= ~0.3-0.5 SOL
Then buy in the SAME slot (delta 0) or +1.
```

## OUR COVERAGE OF HIS PICKS
Detector = our shadow/observe fires only on pump create_v2 at create slot. Classification of his decoded create-slot snipes at several --min-dev-buy:

| --min-dev-buy | WOULD-ACCEPT | SKIP non-vanilla | SKIP dev<thr | MISS mid-life(>5) | MISS undecoded |
|---|---|---|---|---|---|
| 0 | 80 | 18 | 0 | 0 | 2 |
| 0.3 SOL | 62 | 18 | 18 | 0 | 2 |
| 0.5 SOL | 61 | 18 | 19 | 0 | 2 |
| 1.0 SOL | 29 | 18 | 51 | 0 | 2 |

- **Vanilla is NOT an absolute filter for him**: he sniped 18/98 NON-vanilla launches (mayhem / creator_fee / holder_reward set). A strict vanilla-only clone filter would MISS those 18 picks.
- Structural detector-misses (bought >5 slots after create = mid-life, our create-detector can't act): 0 (NONE — every decoded snipe was a create-slot/+1 entry, so his picks are all within our detector's structural reach).
- Undecoded: 2 mints whose min-slot tx carried no pump create_v2 (possibly non-pump-create launches); treated as MISS-undecoded, not confirmed structural misses.

### Recommendation
- **Set --min-dev-buy ~= 0.3 SOL.** It keeps 62/98 (and 80/90 of his real-dev-buy vanilla picks) while the accept count only collapses past 0.5 SOL (61 -> 29 at 1.0 SOL). 0.3 is below his dev-buy p25 (0.69 SOL) so it rarely over-filters; raising to >=1.0 SOL would drop more than half his picks.
- Keeping the **vanilla-only** gate (our current filter) costs ~18% of his picks (the non-vanilla ones). If we want his full coverage, relax vanilla to 'creator_fee_bps==0' only and keep dev>=0.3.

### Actual log overlap (our runs)
- Grep of all 100 target mints vs /root/arbx-fast/*.jsonl + *.log: **1 actual-buy overlap** — `3pZnEdRwKsnVwokJwuzh8unuc5BMdebbm9GX7Djdpump` appears in rt1.log as our LIVE round-trip buy (spend 0.01 SOL). This is one of our 4 known live snipes; the target also sniped it. No other mint overlap in shadow_*.jsonl/launches.

## Surprises / contradictions vs prior hypotheses
- Dev buy is REAL and near-universal, but the dev buy uses SEVERAL pump buy discriminators, not just buy_exact_quote_in_v3/classic (b817ee6167c5d33d, 38fc74089edfcd5f seen). Measuring dev buy by the pump buy discriminator alone UNDERCOUNTS; the honest measure is the bonding-curve SOL delta in the create tx.
- Dev-buy median here is ~0.99 SOL (prior guess 0.5-1.0 SOL).
- His own buy size (median ~1.9 SOL) is large/aggressive, not a micro snipe.

## Confidence / caveats
- N=100 landed snipes over ~13h is a solid single-session sample but one wallet, one window; not lifetime behavior.
- 2 creates undecoded: earliest-slot tx carried no pump create_v2 (not a pagination limit; 0 beyond the 16k-sig cap). Excluded from pattern %, counted as MISS-undecoded.
- dev_buy includes ~0.001 SOL account rent (negligible at 0.3-1.0 SOL thresholds).
- Creator fresh/repeat is in-window only (12h); true factory history not checked.
- Outcome/PnL not computed (primary ask was the pre-buy signal).

---

## FILTER ACCEPT TEST — 200 SNIPES (our real logic)
- Sample: his last **200 landed snipes**, window 2026-10-12 20:07..2026-10-14 10:04 UTC (~38 h). Create tx decoded for **192/200** (undecoded excluded below).
- Our wire filter: dev_buy read from the create tx's bundled pump buy instruction data only (6 discriminators; spendable=data[8:16], cap=max_sol_cost data[16:24]; priority spend>finite-cap>u64::MAX-sentinel>0), vanilla from create_v2 flag bytes. ACCEPT = vanilla AND wire_dev>=threshold.
- Vanilla: 147/192 = 77%.  u64::MAX sentinel (always-pass dev) hits: **33/192**.
- Wire dev_buy dist (excl sentinel): p25=0.707 med=1.212 p75=3.300 SOL.  Curve-delta truth dist: p25=0.853 med=1.111 p75=3.025 SOL.

| --min-dev-buy | ACCEPT | SKIP non-vanilla | SKIP dev-too-low | accept-rate |
|---|---|---|---|---|
| 0 | 147 | 45 | 0 | 77% |
| 0.3 SOL | 125 | 45 | 22 | 65% |
| 0.5 SOL | 121 | 45 | 26 | 63% |
| 1.0 SOL | 96 | 45 | 51 | 50% |

### Wire-vs-curve faithfulness (our slot-0 number vs bonding-curve SOL delta truth)
| threshold | over-accept (wire pass, curve<thr) | under-accept (wire skip, curve>=thr) |
|---|---|---|
| 0.3 SOL | 6 | 0 |
| 0.5 SOL | 3 | 0 |
| 1.0 SOL | 31 | 0 |

**Verdict:** at --min-dev-buy 0.3 SOL our filter ACCEPTS 125/192 (65%) of his decoded picks; dropping to 0.5 SOL barely changes it, 1.0 SOL loses ~half. Wire vs curve disagree on 6/192 at 0.3 SOL (mostly over-accept from cap=max_sol_cost>actual), so the wire number is a faithful-enough proxy (cap-family reads the declared max, which slightly over-states spend). Recommend **--min-dev-buy 0.3 SOL**.
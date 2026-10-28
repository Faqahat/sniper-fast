# Analyst L (select): no hidden on-chain selection signal; seller memory adds a little (10-28 ~04:25 PKT)
Saved by the main session from the agent's reply. Code: this folder (s0–s15). Data: /home/moiz/sniper-data/haqq_dissect/select/ (s4_*, s6, s7, s8, s9, s11–s15 .txt; examples.json with 24 examples).

## F's score vs F's score + new features (walk-forward)
**Rate-matched precision, D2–D6:**

| Bot | F alone | + creator / dumper / create-tx / time | + memory of haqq's past picks |
|---|---|---|---|
| 247 | .20–.31 | .24–.33 | .27–.35 |
| 248 | .20–.25 | .19–.27 | .19–.27 |

No variant reaches 0.5 at useful recall without haqq's own state.

**Value at our position (real buyers at k 2–7, +4 s mark):**

| Picks | Union of 247/248 | 248 only |
|---|---|---|
| haqq's actual picks | +2.51% | +2.60% |
| F's score | +1.78% | +1.08% |
| F + new features | +2.17% | +2.32% |

The new features win on 4 of 5 days (union).

**"Our 247/248" walk-forward (calibrated, D3–D5):** every row is negative at NOW / S2 / CHEAP; with 10% fewer followers −12..−50 SOL over the period.

## What explains his selection (MEASURED)
- **Serial launchers:** 247 strongly prefers dumps by wallets with ≥20 creates (+26.5 SOL, +10.5 mSOL/lot, 6/6 days). Creators are 37% of young big dumps but 77% of 247's picks.
  - The market model already captures it (followed / expected = 0.99).
  - 248 has no creator preference.
- **Seller memory** (causal): a seller's past follow rate > 20% gives a 1.07–1.57× lift on every day. Past follow volume ≥ 1.5 SOL → 19–21% followed vs 4.6%. No wallet-list behaviour; some creator avoidance.
- **Create-tx strings / shape:** weak (+0.01..+0.02 precision).
- **haqq's own state** (open lots, time since his last buy): the strongest addition (+0.06..+0.10 precision), but it reflects his capacity, not dump quality.
- **Time of day:** 08–12 PKT 1.40× expected; 20–24 PKT 0.76×.
- **Funding source:** not available in the recordings.
- **Open, needs owner OK:** off-chain token metadata (socials, website) via the URI fetch.

## P&L for us (INFERRED)
- **Regular landing:** every selector ≤ 0.
- **Pre-send-style** (drop ≥ 12%, H's adverse fill, wave exit, NOW):
  - market only +3.6 / +6.7 / +8.8 SOL/day (D3–D5); with new features +4.4 / +8.4 / +10.3;
  - gain +1.33 [−0.23..+2.87] (drop ≥ 8%: +1.67 [+0.43..+3.04]).
  - The absolute values are optimistic (no pre-send calibration, an arming lower bound, 1,600 arms/day ≫ H's 5-token cap). H's engine-level estimate is +2.28/day.

## Verdict
- The selection is not hidden in creator / dumper / create-tx / time data; only memory signals add a little.
- **Recommendation:** add seller-memory and serial-launcher features to H's whale selector and re-run H's engine sim. Don't build a standalone imitator.
- **Engine data:** a rolling per-wallet create counter; a per-seller dump book with follow SOL; creator history; CreateEvent strings; hour of day.

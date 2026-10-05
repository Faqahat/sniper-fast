# Test budget ledger

**Allocation (owner, 2026-10-05):** $3–5 of the frz wallet (`FRZh63L6…`) for fees and tests.
- Hard cap: 34,000,000 lamports (≈ $5 at ≈ $145/SOL).
- Target: ≤ 21,000,000 lamports (≈ $3).
- Starting wallet: ≈ 414,000,000 lamports (0.2230 native + 0.1915 WSOL), measured on 2026-10-05.
- The equity floor in every canary or live config is set from the **remaining** budget.

| Date (UTC) | Test | Fees | Tips | Rent locked | Rent recovered | Trading P&L | Net spend | Cumulative | Remaining (hard cap) |
|---|---|---|---|---|---|---|---|---|---|
| — | (no live test yet) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 34,000,000 |

Net spend = fees + tips + rent locked that cannot be recovered − trading profit. Every figure comes from chain data, either the WP-07 ledger or `getTransaction` balance deltas, never from our own predictions.

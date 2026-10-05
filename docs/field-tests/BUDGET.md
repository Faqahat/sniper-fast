# Test budget ledger

**Allocation (owner, 2026-10-05):** $3–5 of the frz wallet (`FRZh63L6…`) for fees and tests.
- Hard cap: 34,000,000 lamports (≈ $5 at ≈ $145/SOL).
- Target: ≤ 21,000,000 lamports (≈ $3).
- **Starting equity basis** (STAGE1-PLAN review F6): WP-07 measures it from chain data at each campaign's start, on the same basis its stops use.
  - **SOL + WSOL** (≈ 414,000,000 lamports on 2026-10-05: 0.2230 native + 0.1915 WSOL) is what the budget floor and the hourly drop cap watch.
  - **USDC** (22.97 on 2026-10-05) is tracked as a quantity floor, so SOL's price cannot move the floor.
  - **Token-account rent** is recoverable and tracked apart.
  - Total equity was ≈ 576M lamports at that day's prices. That figure is for reference only and is never used for a floor.
- The equity floor in every canary or live config is set from the **remaining** budget.

| Date (UTC) | Test | Fees | Tips | Rent locked | Rent recovered | Trading P&L | Net spend | Cumulative | Remaining (hard cap) |
|---|---|---|---|---|---|---|---|---|---|
| — | (no live test yet) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 34,000,000 |

Net spend = fees + tips + rent locked that cannot be recovered − trading profit. Every figure comes from chain data, either the WP-07 ledger or `getTransaction` balance deltas, never from our own predictions.

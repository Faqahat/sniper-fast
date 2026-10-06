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
| 2026-10-06 | FT-004 (ft004, 1 h canary) | 60,000 | 90,852 | 9,006,840 | 9,006,840 | +187,905 | **−37,053** (profit) | −37,053 | 34,037,053 |

Net spend = fees + tips + rent locked that cannot be recovered − trading profit. Every figure comes from chain data, either the WP-07 ledger or `getTransaction` balance deltas, never from our own predictions.
- **Trading P&L** (WP-07: `ledger::Entry::trade_pnl`) is each route's change of SOL + WSOL and of recoverable rent, plus what it paid in fee, tip and non-recoverable rent. A token a route left behind counts 0 there; its quoted value is reported apart.
- **The owner's own transfers** into or out of frz are not spend. They are listed apart as `owner_transfers`.
- **The same net spend is what the WP-07 stops measure** (review WP-07 #4): the floor (the test budget) and the hourly and daily caps.

Each campaign's row (WP-07):
- `runs/<name>/spend.json` (`arbx.spend/1.1`; MEASUREMENT §4.42) sums its segments' ledgers. It counts each signature once, and only what landed after the campaign's start.
- Its `budget_md_row` gives the row's first eight columns. Rent locked = recoverable + non-recoverable. Cumulative and Remaining follow from the row above.
- `arbx campaign-equity --campaign-dir runs/<name>` prints the campaign's money now: the start, the stop value, the floor, SOL + WSOL, the drops, the net spend, what is left, and the owner's transfers.

**The cumulative budget is enforced, not only written here** (review WP-07 #5). `/root/arbx/runs/budget-state.json` (`arbx.budget/1.0`, src/budget.rs) is the machine copy of this table.
- It holds each sending campaign and manual run with its allotment and its net spend. Entries not final are re-read from their own ledgers.
- Every live or canary start reads it. A start is refused when 34,000,000 less the cumulative spend is not above 0, and is cut to what is left otherwise.
- After each test, copy its row here from spend.json; budget-state.json should then show the same Cumulative.

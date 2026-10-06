# FT-004: first live canary on frz (1 h)

- **Status:** **PASS** (2026-10-06 12:38–13:39 UTC, campaign ft004, build 374fda1, 2 × 30 min).
- **Mode:** canary (`arbx campaign --mode canary`): 2 segments of 30 min, real Jito bundles, bundle-only, fail-closed.
- **Wallet:** frz FRZh63L6… (pre-approved by the owner; never drained).
- **Budget allotment:** **5,000,000 lamports** (0.005 SOL), within the cumulative 34,000,000 hard cap (BUDGET.md). Enforced by WP-07: floor = start equity − allotment, hourly drop cap, staleness stop.
- **Goal:** the first real bundles: prove that sending, landing, settlement, the ledger, the stops and the win alerts all work with real money, and that a landed trade never loses.

## Pass/fail criteria (written before the run)
1. **Bundle-only:** 0 non-bundle copies; **0 failed-landing fees** in the ledger.
2. **Every landed bundle nets > 0** after fee + tip + rent, **with 0 exceptions**. Rent locked = rent reclaimed in the same transaction for every create+close.
3. **Money reconciles:** the reconciliation at each segment stop is within 10,000 lamports on both bases; no `refused_bundle_landed`.
4. **Spend ≤ 5,000,000 lamports**, and no unexpected stop. A designed stop (floor, hour cap) firing is a stop and must be explained.
5. **Alerts:** campaign start and end, and a 💰 win alert per win with the net from chain data ("succeeded", never "profitable" unless net > 0); the watchdog's status messages.
6. **Zero wins is not a failure** in 1 h, given the size cap (about 0.19 SOL) and crowded pools. It moves on to FT-005 if 1–5 hold.

## Results

| Segment | Sent | Landed | Win ratio | Net (chain ledger) |
|---|---|---|---|---|
| p1 (12:38–13:09) | 184 | 5 | 2.7% | +15,884 |
| p2 (13:09–13:39) | 231 | 7 | 3.0% | +21,169 |
| **Total** | **415** | **12** | **2.9%** | **+37,053 lamports** |

1. **Bundle-only:** 0 non-bundle copies, **0 failed-landing fees**. About 400 bundles did not land and cost 0.
2. **Every landed trade nets > 0:** 12 of 12, from +1,296 (min) to +6,873 lamports.
   - Gross 187,905, tips 90,852, fees 60,000.
   - **6 were create+close trades on new mints.** Rent locked equals rent reclaimed in the same transaction on all 6 (1,488,440 / 1,513,840 / 1,539,240): rent-neutral, proven live.
3. **Money reconciles:**
   - stop reconciliations ok, final, residual 0, at both stops;
   - executor vs chain diff 0; no refused bundle landed; 0 provisional;
   - stop snapshots succeeded;
   - equity (SOL + WSOL) 414,481,617 → 414,518,670 = +37,053, equal to the ledger.
4. **Spend ≤ budget:** net spend −37,053 (a profit). `runs/budget-state.json` records ft004 as spent −37,053 against the 34,000,000 hard cap. No stop fired.
5. **Alerts:** a win alert fired for each landing (Telegram, from Cherry); the watchdog posted its status.

**Observations:**
- Wins so far are small: USDC/WSOL and long-tail mints, with a tip of about 45–65% of gross plus the 5,000 fee.
- The bigger new-mint gaps are contested (FT-000: about 75% of the value is taken within 20 ms).
- Profit per win is a Stage 1 lever (X4 tip share, the skip filter, discovery, arbx-exec CPI tips).

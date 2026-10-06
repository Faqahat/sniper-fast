# FT-004: first live canary on frz (1 h)

- **Status:** planned. It runs after the re-soak on the new final build and after FT-002 passes; go-live gate items 1–4.
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
(filled in)

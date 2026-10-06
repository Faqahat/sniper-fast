# FT-005: 12 h canary on frz (Stage 0 exit)

> **Owner, 2026-10-06:** 12 hours instead of 24, then **shortened to 3 h** (part A 13:40–14:26 + part B 15:00–17:14 UTC).
> **Owner, later:** FT-005 is **no longer the Stage 0 exit by itself**. Stage 0 closes **after FT-007**, with the criteria below measured over the whole canary series FT-005 + FT-006 + FT-007 (about 9 h).

- **Status:** running in two parts (owner-requested pool refresh in between).
  - **Part A (`ft005`):** 13:40–14:26 UTC on `seed-pools-ft000s3.csv`, stopped for the refresh. Net spend −93,543 lamports, a profit. Stop reconciliation done.
  - **Pool refresh:** pooldisco 14:26–14:57 UTC (3,313 pools seen, 750 tokens with 2+ pools). New list `data/seed-pools-20261006.csv` (commit 02a45ef): 1,165 kept, led by the 771 active in FT-004/FT-005, plus 335 new discoveries; 335 idle dropped.
  - **Part B (`ft005b`):** from 15:00 UTC for 11.25 h on the fresh list. Boot: 364 SOL pairs with 2+ pools, 1,344 pools (FT-001: 317 pairs, 1,082 pools).
  - The 12 h criteria are measured over part A + part B.
- **Mode:** canary under `arbx campaign` (**12 h**, segments of 60 min), bundle-only.
- **Wallet:** frz FRZh63L6….
- **Budget allotment:** 10,000,000 lamports (0.01 SOL), within the cumulative 34,000,000 hard cap.
- **Goal:** close Stage 0. Meet the plan's exit gate (docs/PLAN.md §6) and the owner-agreed trade-success criteria, and produce the first real numbers: win ratio per send, wins/h, net SOL/h.

## Pass/fail criteria (written before the run)

### A. The plan's Stage 0 exit gate, over the 12 h
- bundle-only with 0 failed-landing fees;
- hourly reconciliation within 10k lamports;
- no prediction pricing (≤ 0.1% `torn_suspect` sends);
- no rent left locked;
- S1–S16 pass;
- a 1 h recording replays identically;
- telemetry populated;
- recording drops within limits;
- `wallet.jsonl` matches `getSignaturesForAddress`;
- provenance;
- deterministic reports.

**Exec coverage ≥ 99%** is **waived for Stage 0** by the owner (2026-10-06, PLAN §9 OD-1): Haan is the only provider for now, and its plan allows one transaction filter. Coverage is still measured and reported. A second provider is to be arranged before Stage 1.

### B. Trade-success criteria (agreed by the owner, 2026-10-06)

| Criterion | Pass mark |
|---|---|
| Every landed trade nets > 0 after fee + tip + rent | 0 exceptions (the on-chain guard makes a landed loss impossible; any loss is a bug) |
| 12 h net (chain ledger) | ≥ 0 SOL |
| Wins in 12 h | ≥ 10. If fewer, extend the canary rather than fail |
| Realised vs quoted profit on wins | median within ±10% |
| Win ratio per bundle sent | ≥ 0.3% (the old bot's level); stretch 0.5% |

### C. The $500 trigger (owner decision, 2026-10-06)
Net positive over 48 h of canary (chain ledger). It is reported to the owner when met; the owner scales the wallet.

## Results
(filled in)

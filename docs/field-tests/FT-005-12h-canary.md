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

## Results (3 h of run time: part A 13:40–14:26 + part B 15:00–17:14 UTC)

| Segment | Sent | Landed | Win ratio | Net (chain ledger) |
|---|---|---|---|---|
| A p1 (13:40–14:26) | 415 | 12 | 2.9% | +93,543 |
| B p1 (15:00–16:00, fresh list) | 745 | 24 | 3.2% | +76,938 |
| B p2 (16:00–17:01) | 815 | 16 | 2.0% | +45,716 |
| B p3 (17:01–17:14) | 103 | 2 | 1.9% | +6,676 |
| **Total** | **2,078** | **54** | **2.6%** | **+222,873 lamports** |

1. **Bundle-only:** **0 failed-landing fees**; the 2,024 bundles that did not land cost 0.
2. **Every landed trade nets > 0:** 54 of 54, the smallest +1,002 lamports.
   - Gross 1,029,727; tips 536,854 (52% of gross); fees 270,000 (26%). We keep 22% of gross.
   - Rent: 38,978,840 locked and recovered in the same transactions (create+close), 0 non-recoverable.
3. **Money reconciles:** the final stop reconciliation is ok in all 4 segments.
   - residual 0; executor vs chain diff 0;
   - no refused bundle landed; 0 provisional; 0 unexplained.
   - `budget-state.json`: ft005 −93,543, ft005b −129,330 (each signature counted once).
4. **Spend ≤ budget:** a net profit; no stop fired.
5. **By leader kind:** Jito-led slots 43 / 1,253 (3.4%), BAM-led 11 / 825 (1.3%). BAM lands at 39% of Jito's rate; FT-006's target is ≥ 70%.
6. **Baseline for FT-006/FT-007's decision rules:**
   - **net +74,600 lamports/h** over 2.99 h of run time;
   - net per win 4,127;
   - win ratio 2.6%.

**Observations:**
- **The win ratio fell from 3.2% to 2.0% within 2 h on the same fresh list.** Pools go stale fast, which is the case for WP-22's automatic refresh.
- **The analysis toolkit counts pre-run rows.** `arbx-report ledger` sums the ledger rows the wallet scanner re-reads at boot (`pre_run: true`, previous segments' signatures) into its totals. ft005b-p1 shows 32 wins / +123,283 there instead of 24 / +76,938. The bot's counters, spend.json and budget-state.json are correct; the toolkit needs a fix.

# Pre-send: tries per block, send paths, 2 positions (agent, 10-27 ~23:55 PKT)

Saved by the main session from the agent's reply (the harness blocks subagent report writes). Full tables are in /home/moiz/sniper-data/presend_density/tables_main.txt.

## Short answer
- **Probe k = 8 with 40 tries/s of send capacity**, one position, everything else as live.
  - INFERRED: +1.66 SOL over the 20 pre-send hours of runs 24–28 = **+0.083 SOL/h** (5–95% +0.063..+0.104).
  - Positive in all 5 runs.
  - With 20% fewer later buyers: +0.041/h. With every try landing 15 ms later: +0.067/h.
  - Extra failed-try fees +0.018 SOL/h, already inside the net.
- **k alone does nothing at 20/s:** k8 −0.05, k16 −0.31. The rate cap refuses most of the extra tries, and a second open window starves.
- **k16 is not better than k8:** +1.63 at 60/s vs k8 +1.85 at 60/s, and it triples failed-try fees.
- **Faster paths add nothing by themselves.** Extra paths pay only through capacity. Best path per client at k4: −0.51, mostly tips.
- **2 positions:** −0.08. Not worth a probe.
- **Calibration:** pooled over r24–r28 the replay is 13% optimistic on net, and the share of dump windows filled is 49% vs 51% live. Factors: wins × 0.99, losses × 1.05.

## Levers (change vs live settings, SOL over 20 h)
| Lever | Total [5–95%] | Per h |
|---|---|---|
| k8, 1 path 20/s | −0.05 [−0.47, +0.37] | −0.002 |
| k16, 1 path 20/s | −0.31 | −0.015 |
| k4, cap 40–60/s | +0.02 | +0.001 |
| **k8, cap 40/s** | **+1.66 [+1.26, +2.08]** | **+0.083** |
| k8, cap 60/s | +1.85 | +0.092 |
| k16, cap 60/s | +1.63 | +0.081 |
| k8, helius-ps + glaive | +1.67 | +0.084 |
| k8, helius-ps + nozomi | +1.41 | +0.070 |
| k4, best path per client | −0.51 | −0.025 |
| 2 positions (k4) | −0.08 | −0.004 |

## Why
- A fill needs a try to land in the short gap between the dump and the bounce.
  - MEASURED in r28: fills land a median 34 ms after the dump; tries that failed on the bounce landed a median 307 ms after.
  - k8 halves the gap between tries, and dump windows filled go from 48% to 55%.
- k8 needs ~38 tries/s per window, so at 20/s most extra tries are refused.

## Recommendation
- **Option 1:** `--presend-live-k 8 --presend-live-max-per-sec 40 --presend-live-path-max-per-sec 40`, if Helius allows 40/s on helius-ps. Helius allows 50/s per region over all paths; mind the sell fan-out's helius-swqos.
- **Option 2:** otherwise, helius-ps + glaive as a second pre-send path, 20/s each.
- **Send-path changes need the owner's OK.**

## Code
`dsim.py`, `drun.py`, `d3_tables.py` in this folder.

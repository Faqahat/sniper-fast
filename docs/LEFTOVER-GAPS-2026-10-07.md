# Leftover gaps with Jito bundles only (2026-10-07, read-only study)

**Verdict: not worth it on its own.**
- Leftover gaps come to about **0.01–0.035 SOL/h net** with bundles only. A miss costs 0, and the tip is 30–50%.
- That is far below the 0.2 SOL/h target.
- About 95–97% of gap value closes within about 80 ms.

**Source:** live arbx run ft012c, segments p2 and p3 (2.0 h), commit-path decisions on committed state, all venues.
- An episode is a route with net > 0 at a size up to 0.2 SOL.
- It ends at the first decision where that route's net is 0 or less.
- The script is `tools/arbx-fast/leftover/ep.py`.

| Gap still open at | Count/h | Median net (lamports) | Gross SOL/h |
|---|---|---|---|
| Opening (all gaps) | ~9,400 | 4–11k | 2.5–2.7 |
| ≥ 80 ms | 3,000–4,000 | 2.5–5k | 0.07–0.11 |
| ≥ 130 ms | 1,900–2,700 | 2.4–4.6k | 0.05 |
| ≥ 250 ms | 850–1,160 | 2.6–4.4k | 0.01–0.02 |
| ≥ 500 ms | 240–400 | 1.9–5k | ~0.003 |

- **How long gaps stay open:** median 51–58 ms, p90 234–279 ms. 66–70% close in their opening slot.
- **The biggest gaps are first-in-line:** the top 10 episodes hold 39–44% of all value.
- **Net SOL/h, bundles only:**
  - same-slot (gaps open ≥ 80 ms): about 0.01–0.035 realistic, 0.035–0.074 if we won everything;
  - next-slot (gaps open ≥ 250 ms): about 0.002–0.007.
- **The persistent leftovers are almost all DLMM pairs:** DLMM with DLMM, PumpSwap, Raydium CLMM or Whirlpool.
  - Top mints: USDC, 4k3Dyjzv, WEN, C1mBfBoD, CARDSccU, METvsvVR.
- **GLiCiNEn already takes this pool**, for about 0.06 SOL/h gross.
- **Leftovers would only grow with breadth:** 3–4-leg routes, a USDC hub, unwatched pools, Tessera V and Whirlpool coverage.
- **The real money is still first-in-line gaps** (~2.5 SOL/h on our pools).

**Caveats:**
- Long-lived DLMM gaps may be overpriced; treat the ≥ 250 ms row as an upper bound.
- The split between leftover and first-in-line gaps is by time, not by position in the block.
- The live arbx pool list (~1,843 pools) was used, not arbx-fast's.
- The sample is 2 hours.

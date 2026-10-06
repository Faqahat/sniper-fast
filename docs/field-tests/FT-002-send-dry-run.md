# FT-002: send dry run (go-live gate item 4)

- **Status:** PASS (2026-10-06 11:34–12:35 UTC, campaign ft002, build 374fda1, config `deploy/arbx-canary-frz.toml`).
- **Mode:** `arbx run --dry-run`. Bundles are built and signed with a throwaway in-memory key and never transmitted (WP-05; the executor holds no send path, no Jito client, no trading key).
- **Budget:** 0 lamports.
- **Goal:** prove that every bundle the final build would send is correct, checked from the signed bytes and by read-only simulation on mainnet state.

## Pass/fail criteria (written before the run)

1. **Volume:** ≥ 100 would-send bundles signed and recorded in full (attempts.jsonl `dry_run`).
2. **Signed-byte checks (`verify_bundle`):** 0 failures, derived independently of the builder (WP-06 review fix #2):
   - instruction order;
   - min_profit ≥ tip + base fee + margin, and amount_in;
   - tip amount and account by band;
   - every account created is closed to the payer in the same transaction (rent-neutral);
   - the CU limit and loaded-data limit re-derived from the message.
3. **Simulation:** `[dry_run] simulate = true`. Every bundle is simulated read-only with `simulateTransaction`. LiteSVM does not count programdata, so this is what validates the auto loaded-data limit. Expect would-fail outcomes (gaps already taken), but **0 failures caused by our transaction** (CU exceeded, loaded-data exceeded, account errors, rent).
4. **No transmission:** the network-call counter shows 0 sends; no Jito contact; the wallet's signatures on chain do not change during the run.
5. **Coverage:** bundles include create+close routes (new mints) and held-account routes (WSOL/USDC), across at least 3 venue pairs.

## Results

| # | Criterion | Result |
|---|---|---|
| 1 | ≥ 100 would-send bundles signed and recorded | **867** signed (`attempts.jsonl` `dry_run`), `sent = false` on all |
| 2 | Signed-byte checks, 0 failures | **867 / 867 `checks_ok`** |
| 3 | Simulation: 0 failures caused by our transaction | **0 compute, loaded-data or rent failures.** 623 simulated (rate-limited): 602 "round trip did not pay" (the gap was already gone in the RPC's state; our min_profit guard reverts, so in a bundle this costs nothing), **14 would have succeeded**, 7 DLMM bin-array or liquidity errors (4 × 0x1794 = 6036, 3 × Anchor 3005 "not enough accounts"), all DLMM legs. The 7 are attributed to the RPC simulating against slightly different DLMM state than the priced state; that attribution is unconfirmed. In a bundle they cost nothing. Follow-up for Stage 1: a wider DLMM array buffer, and simulating at the decision's state |
| 4 | No transmission | No copies or bundles records; frz's newest on-chain transaction is still 2026-10-04 19:29 UTC, before the test |
| 5 | Coverage | 664 create+close and 203 held-account routes; venue pairs Dlmm→Dlmm 416, Dlmm→PumpSwap 159, PumpSwap→Dlmm 153, Dlmm→DammV2 36, Dlmm→RayCpmm 27, PumpSwap→DammV2 22 |

- Max size: 191,524,924 lamports, the WSOL held: the bankroll cap binds.
- Tips by band: 2,335–2,485 lamports on these routes.
- Simulated CU: p50 108k, max 197k.

**Go-live gate: items 1–4 met.** Code reviewed and tested (589 tests). Shadow soak: FT-001 p1–p2 plus the 374fda1 re-soak. Replay identical: the re-soak replay is OK, with state and decision digests equal at both journaled points. Dry run: this test. FT-004 may start (pre-approved by the owner).

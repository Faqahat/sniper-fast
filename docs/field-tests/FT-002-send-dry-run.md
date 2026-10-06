# FT-002: send dry run (go-live gate item 4)

- **Status:** planned, after FT-001 passes.
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
(filled in)

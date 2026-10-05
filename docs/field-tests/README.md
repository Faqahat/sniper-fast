# Field tests

Every test that runs on Cherry (shadow, dry run, canary or live) is documented here before it starts and completed when it ends. Each test can be reproduced from its entry, and its cost appears in [BUDGET.md](BUDGET.md).

## Wallet and budget (owner, 2026-10-05)

- **Wallet:** `FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS` ("frz"), the production wallet. On 2026-10-05 it held about 0.414 SOL (≈ $60): 0.2230 native and 0.1915 WSOL. **Never drain it.**
- **Test budget:** $3–5 for fees and tests, pre-approved by the owner. Tests within the budget need no further approval.
  - Hard cap: **0.034 SOL** (≈ $5 at the ≈ $145/SOL implied by the owner's figure).
  - Target: ≤ 0.021 SOL (≈ $3).
- **What counts against the budget:** fees, tips, non-recoverable rent, and any trading loss, measured on chain (WP-07 ledger, or `getTransaction` deltas).
  - Recoverable rent (token or nonce accounts) is tracked separately and recovered when testing ends.
- **Enforcement:** every canary or live config sets these campaign-wide WP-07 stops before it runs:
  - an equity floor of the starting equity minus the remaining budget;
  - an hourly drop cap (OD-11).

  Crossing either puts the bot in shadow and stops the segment.
- **Prerequisites (owner):**
  - the frz keystore at `/root/arbx/wallets/trading.enc`;
  - a passphrase method: piped on stdin at start, or a mode-600 file the supervisor pipes in for unattended tests;
  - `/root/arbx/deploy/.env` holding `HAAN_API_KEY`, `HAAN_X_TOKEN`, `SHYFT_RPC_URL`, `ASTRALANE_KEY` and `JITO_UUID`.

## Protocol for each test (an entry `FT-NNN-<slug>.md`)

1. **Before:**
   - ID and title;
   - purpose and hypothesis;
   - **pass/fail criteria, written before it runs**;
   - mode (shadow / dry-run / canary / live);
   - budget allotted (lamports);
   - expected cost.
2. **Setup:**
   - build (git hash and binary sha256);
   - config path and sha256 (meta.json records both);
   - the wallet's starting balances (native, WSOL, token accounts);
   - the exact commands.
3. **Run:** UTC start and stop, the stop reason from stop.json, anything abnormal.
4. **Results:**
   - the numbers, each with the record file or `arbx-report` command that produces it;
   - chain checks (signatures, landed or failed).
5. **Spend:** lamports by category (fees, tips, rent locked, rent recovered, trading P&L), and the ending balances. Add a line to BUDGET.md.
6. **Verdict:** pass or fail against the criteria written before the run, the follow-ups, and what changes in code or config.

Records stay in the run directory on Cherry (`/root/arbx/runs/<id>/`). The entry names the run directory and any copies pulled for analysis.

## Planned sequence to go live (docs/PLAN-ADDENDUM.md, "Go-live gate")

| ID | Test | Mode | Budget |
|---|---|---|---|
| FT-001 | Shadow soak ≥ 3 h with the final Stage-0 build, Haan alone; boot under provider errors; replay of a 1 h slice | shadow | 0 |
| FT-002 | Send dry run: ≥ 100 would-send bundles signed (throwaway key) and verified from the signed bytes (min_profit, amount_in, tip, accounts) | dry-run | 0 |
| FT-003 | Wallet prep, if needed: token accounts for the top-N mints of the seed list | live (setup) | rent only (recoverable) |
| FT-004 | First live canary hour: bundle-only, size capped by the bankroll, equity floor armed | canary | ≤ 0.005 SOL |
| FT-005 | 24 h canary with hourly reconciliation (Stage 0 exit) | canary | ≤ 0.01 SOL |

Stage 1 tests (X-series experiments) are added as their work packages land. The budget may run short: the full X12 lane race costs about 0.4 SOL at 0.001 SOL tips. Such tests run only as small pilots within the budget, or wait for the $500 stage.

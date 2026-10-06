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
  - **As WP-07 implements it** (`arbx campaign`, src/supervisor.rs; review STAGE1-PLAN F6; review WP-07 #4):
    - **What the stops measure: the net spend.** The ledger's cumulative net spend since the campaign's start: fees + tips + non-recoverable rent − the routes' trading result (a token a route left behind counts 0; recoverable rent is tracked apart). It comes from the ledger's categories, never from a balance and never at a price.
    - **The floor:** the net spend may not pass the test budget (`equity_floor`). **The hourly cap** (`[supervisor] max_drop_per_hour_sol`, 0.02 SOL): it may not grow by more than that within a rolling hour (`equity_hour`); 0.15 SOL within 24 h (`equity_day`). The starting equity (SOL + WSOL, read from the chain at the campaign's first balance snapshot, recorded with its components in campaign.json) anchors the stop value, start − net spend, that status and campaign.json report.
    - **Tokens:** USDC and any other token held at the start is a quantity floor of its own: what routes move of it may not take it more than `token_floor_tolerance` (0.1%) below its start amount (`token_floor`).
    - A stop ends the campaign (exit 20). A reconciliation miss puts the segment in shadow, and the campaign's later segments record only.
  - **The owner's transfers do not move the stops** (review WP-07 #4). A deposit into frz while a campaign runs does not extend the allowance, and a withdrawal does not trip a stop: neither is spend. Each one the ledger sees is recorded and alerted, never a safety stop:
    - an `owner_transfer` event (events.jsonl) and a Warn notice;
    - the reconciliation window's `owner_transfers`;
    - spend.json's `owner_transfers`.

    Its fee, when frz paid it, counts as spend. A transfer whose record never reaches the ledger shows as a reconciliation miss: shadow, and the later segments record only.
  - **The money view must be fresh** (review WP-07 #3). Balance snapshots run every 10 minutes inside a segment (`[ledger] snapshot_min`), not only at start and stop. The view is stale in any of these cases:
    - its last good snapshot is older than `max_view_age_s` (600 s);
    - `stale_after_failures` snapshots in a row failed (3);
    - a landing found by a status check has waited `max_record_wait_s` (120 s) for its wallet record;
    - the chain-fetch service gave up on a wallet record. A snapshot is asked for at once, and the view stays stale until it lands.

    While the view is stale, nothing is sent. The executor refuses `equity_stale`, and the SendGate is in shadow with reason `equity_stale` (Error notice). When the view is fresh again the gate goes back to live, unless something else (a pause) holds it.
  - **The test budget is cumulative** (review WP-07 #5). The owner's 34,000,000-lamport hard cap covers all tests together. `/root/arbx/runs/budget-state.json` (`arbx.budget/1.0`, src/budget.rs) lists every sending campaign and manual run with its allotment and its net spend.
    - Every live or canary start reads it: `arbx campaign --mode canary|live`, and `arbx run --canary|--live` outside a campaign. A run that was killed is re-read from its own ledger.
    - A start is refused when nothing is left. Otherwise its allotment is the smaller of what it asks for and what is left.
    - A run's allotment is `[supervisor] test_budget_lamports`, lowered by `arbx campaign --test-budget-lamports` or `arbx run --budget-left`. Neither may exceed the hard cap. The frz config holds FT-004's allotment, 5,000,000, so the full cap is never armed by default. FT-005's 10,000,000 needs a copy of the config with that value.
    - A campaign records its spend after every segment and at its end; a manual run at its end.
  - **One bot on frz at a time** (review WP-07 #5, #14). A manual `arbx run --canary` or `--live` takes the same campaign lock as `arbx campaign` (refused while a campaign runs) and runs the same other-bot check:
    - another `arbx … run` or `arb-lab … run`;
    - arbed's bot (`bun bin/arbed.ts run …` under pm2, on the same frz keystore and Haan token);
    - a live segment socket.

    A live or canary segment runs only under a campaign supervisor that holds the lock. Even so, the owner keeps arbed's bot and any other user of the frz key stopped while a test runs (I-3).
  - **Reconciliation at a segment's stop and between segments** (review WP-07 #7, #9). The stop's window that does not pass is searched (getSignaturesForAddress) and decided once more within `recon_grace_s`. If it is still unexplained, it is written `final: false` and the next segment decides it again. The next segment reconciles from that window's start, or from the previous segment's last snapshot, to its own first snapshot, with every record of that span: a late landing passes, missing money is a miss.
- **The key (owner, 2026-10-05): no passphrase needed.** The frz private key is already on Cherry, as the owner's keystore `~/.nexus-v2-trading-wallet.{enc,pass}` that arbed uses.
  - arbx loads that format as `wallet_profile = "trading"` with `wallet_keystore = ""`, unattended.
  - At boot it refuses to start unless the key is `FRZh63L6…`.
  - The files are used in place, never copied or read by anyone but the bot process.
- **Done (owner's instruction, 2026-10-05):** `/root/arbx/deploy/.env` (mode 600) was created on Cherry from the existing server .env. Only the names arbx's two maintained configs reference were copied, and no value was printed.
  - 17 names are set, including the five the canary needs: `HAAN_API_KEY`, `HAAN_X_TOKEN`, `SHYFT_RPC_URL`, `ASTRALANE_KEY`, `JITO_UUID`.
  - Absent from the source and unused by the canary: `BLOXROUTE_KEY`, `FALCON_KEY`, `LANDER_SHYFT_URL`, `LUNAR_KEY`, `NODEONE_KEY`, `ZEROSLOT_KEY`.
- **Shared keys:** the Haan token and the Jito UUID are the same keys arb-lab used. Haan grants its streams to the first process only (I-3), and Jito's rate limit is per key, so arb-lab must not run while arbx tests run.

## Deploying to Cherry (owner rule, 2026-10-05): build artifacts only, never source code

Only these go to `/root/arbx` on Cherry:
- the compiled binary, `bin/arbx-<git short hash>`, release build with debug info stripped (its sha256 goes in each FT entry and in meta.json);
- the config file the run uses (`deploy/<config>.toml`);
- the data files that config references (`data/`: seed list, registry, templates, crowded-pools, validators-meta, ip-geo, and since WP-06 the CU table `data/cu-table.json` at `/root/arbx/data/cu-table.json`, `[builder] cu_table`: a run without it refuses to start).

Never uploaded: `src/`, `program/`, `tools/`, `docs/`, or any script (.py/.sh/.ts). Anything that must run on Cherry, such as a campaign supervisor, becomes a subcommand of the binary (the campaign supervisor is `arbx campaign`, WP-07). Secrets live only in `/root/arbx/deploy/.env` (mode 600).

## Alerts and the watchdog on Cherry (WP-20)

- **Alerts** come from each segment by itself: the maintained configs and the frz canary (`deploy/arbx-canary-frz.toml`) have `[alerts] enabled = true`. They need `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `/root/arbx/deploy/.env` (mode 600). The owner sets them there, never in git or a config. Without them a segment runs as before, with one run.log WARNING (`alerts off: … not set`).
- **What the money alerts say** (integration, integ/stage0): a landing of ours "succeeded" with its net from chain data (the route program's round trip less the fee, tip and rent of the ledger's line for that transaction); never "profitable", and a gain only when that net is above 0. WP-07's stops, reconciliation misses, stale money views and owner transfers come as their notices, deduplicated by kind and subject. `arbx campaign` tells the campaign's start and end, and its campaign-wide stops, from its own process with the same .env (only the two variables are read from it). The daily summary's win ratio is wins ÷ bundles sent, with both numbers.
- **Check the pair** after the .env changes (one test message to the group; it prints `ok: …` or `failed: <why>`, never the token or the chat id; exit 0 or 1):

  ```
  cd /root/arbx && bin/arbx-<hash> alert-test --config deploy/<cfg>.toml
  ```

- **A note to the group** (a field test's goal when it starts, its result when it ends), sent with the same .env, so the operator never sees the token. The first line is the title:

  ```
  cd /root/arbx && bin/arbx-<hash> notify --config deploy/<cfg>.toml --text "FT-001 goal: <one sentence>"
  ```

- **The watchdog** is a separate, long-running process. Start it once, detached from the SSH session:

  ```
  cd /root/arbx && setsid nohup bin/arbx-<hash> watchdog --config deploy/<cfg>.toml >> runs/watchdog.out 2>&1 < /dev/null &
  ```

  - It watches `[watchdog] runs_dir` (`/root/arbx/runs`). It tells the group "✅ running" every `status_min` (60 min), and "❌ NOT running" when no segment process has been alive for more than `grace_s` (120 s) or the running segment's status.jsonl is more than 60 s old. While it stays down, it repeats the reminder every `status_min`; "✅ back up" follows when the bot recovers.
  - Its journal is `runs/watchdog.jsonl`, and `runs/watchdog.out` has the same lines with times.
  - One per runs directory: a second one refuses to start, and `runs/.watchdog.lock` holds the pid of the one running (emptied when it stops).
  - To look once without sending: `bin/arbx-<hash> watchdog --config deploy/<cfg>.toml --once` prints JSON (exit 0 running, 1 not).
  - To stop it: `flock -n runs/.watchdog.lock true || kill $(cat runs/.watchdog.lock)` (it signals only while a watchdog holds the lock, so never a process that reused an old pid). On SIGTERM it says "⏹ watchdog stopped" and exits 0. For a new binary, stop the old watchdog and start the new one with the new hash.
- The watchdog is the binary itself (a subcommand) started from its config, so the owner rule above holds: Cherry gets the binary, its config and its data, never source or scripts.

## Protocol for each test (an entry `FT-NNN-<slug>.md`)

1. **Before:**
   - ID and title;
   - **the goal in one sentence**, posted to the owner's Telegram group when the run starts; the result against that goal is posted when it ends (`arbx notify`, above);
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

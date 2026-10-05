# testdata/scenarios: WP-09 scenario fixtures

Inputs and expected outputs of the scenario tests in `src/scenarios/` (PLAN WP-09 item 4). Every file a test reads is
here or elsewhere in this repository (PLAN-ADDENDUM I-11).

## Files

| File | What | Made by |
|---|---|---|
| `capture.json` | which pools to capture, and why each | by hand |
| `accounts.json` | the captured accounts: real mainnet layouts, never edited | `tools/capture-fixtures.py --scenarios` |
| `expected/<scenario>.json` | each scenario's decisions and commit groups, projected (pools and transactions by name) | the tests, with `ARBX_BLESS=1` |

Inputs (`capture.json`, `accounts.json`) and expected outputs (`expected/`) are kept apart: a change of the venue
maths (WP-16) changes only `expected/`.

## Provenance of accounts.json

- Read on 2026-10-04 at 22:07 UTC from the public endpoint `https://api.mainnet-beta.solana.com` with
  `getMultipleAccounts` (base64, commitment `confirmed`), every account at context slot 453,386,130.
- 7 pools, 36 accounts, 154,680 bytes of account data; 1 derived account does not exist (the bolt DLMM pair's bitmap
  extension), listed in `missing`.
- Each account carries its owner, lamports, context slot, length and the sha256 of its data; the tests check the sha256.

| Pair | Pool | Venue | Why |
|---|---|---|---|
| USDC/SOL | `Gf7sXMoP8iRw4iiXmJ1nq4vxcRycbGXy5RL8a8LnTd3v` | PumpSwap | no creator fee, no virtual reserve; the cmp2 "poisoned" pool (PLAN-ADDENDUM I-8) |
| USDC/SOL | `47hq28mcL7q5GhBg7epyGF2dnuJd4MKFt8QhT7CzYUp4` | Raydium CPMM | the largest WSOL/USDC CPMM pool (getProgramAccounts, 2026-10-04); 1.66 SOL deep |
| USDC/SOL | `58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2` | Raydium AMM v4 | the main USDC/SOL AMM v4 pool (WSOL is token 0) |
| USDC/SOL | `HTvjzsfX3yU6BUodCjZ5vZkUrAxMDTrBs3CJaq43ashR` | Meteora DLMM | bin step 1, with a bitmap extension |
| USDC/SOL | `8Pm2kZpnxD3hoMmt4bjStX2Pw2Z9abpbHzZxMPqxPmie` | Meteora DAMM v2 | |
| 9dSMwFfP/SOL | `5VbavvxS1NLmyNJLS3QbDoRFsUHKn6rBzmfVQdWWSniq` | PumpSwap | the bolt trade's pool (w5h2-p5#648): Token-2022 base with metadata extensions, a 170-byte vault, creator fee, signed virtual reserve |
| 9dSMwFfP/SOL | `HYWKYZ1eA2eKdJdCnMqZKHEfArvmEB8T3SJGDvJZyEUg` | Meteora DLMM | the bolt trade's DLMM pair: bin step 100, no bitmap extension |

With each pool: the accounts arbx follows for it, derived from the pool account as `pools::boot` derives them (CP
vaults, the PumpSwap base mint and global fee config `5PHirr8j...`, the CPMM config, every token mint, the DLMM bitmap
extension and the 7 bin arrays around the active bin), and the Clock sysvar.

## How the tests use them

A scenario boots a registry through the real `pools::boot` (a local mock RPC serves `accounts.json`), boots its run as
`arbx run` boots a segment (accounts.bin, the journal's boot records, engine_init, `pools.json` and `registry-run.json`,
the Stage-0 config as `config.toml`), mutates copies of the accounts with the venues' own maths (`scenarios::swap`: CP
effective reserves, the DLMM bin walk, the DAMM v2 price), asserts its expected result, and replays its run directory
with `replay::replay` (`--compare`): the replay must be whole and give the run's state and decision digests (as the run
recorded them too) and identical decisions and commit groups.

`capture.json` and `accounts.json` are pinned in `testdata/legacy/fixtures.sha256` (`tools/capture-fixtures.py --verify`;
`--manifest` after a new capture). The analysis toolkit reads one scenario run as a recording of arbx's own:
`tools/arbx-report/tests/fixtures/wp09-run/` (written by the test `the_toolkit_fixture_is_this_codes_recording`, which
also checks it is what the code writes).

## Regenerating

- **Expected outputs** after an intended change of the venue maths or the engine (review the diff before committing):

  ```
  ARBX_BLESS=1 cargo test --release --lib scenarios
  git diff testdata/scenarios/expected/
  ```

- **The captured accounts** (new mainnet state: every expected output changes, and S5's search for an aligned split
  re-runs on the new state):

  ```
  python3 tools/capture-fixtures.py --scenarios     # or --rpc-url-env NAME for another endpoint (never written to the file)
  ARBX_BLESS=1 cargo test --release --lib scenarios
  ```

- **The toolkit's recording** (`tools/arbx-report/tests/fixtures/wp09-run/`) after a change of what `arbx run` writes
  there: `ARBX_BLESS=1 cargo test --release --lib toolkit_fixture` (rewritten only when it differs), then
  `cd tools/arbx-report/tests && python3 -m unittest test_wp09_recording`.

- **Inspect a scenario's run directory**: `ARBX_KEEP_SCENARIOS=1 cargo test --release --lib scenarios::s5` keeps
  `$TMPDIR/arbx-scenario-<name>-<pid>-<ns>/` (the run, and its replay in `replay/`); then
  `arbx replay --run <dir> --compare --out <dir>/again` or `arbx quote --run <dir> --route <buy,sell,mint> --version <txn> --size <lamports>`.

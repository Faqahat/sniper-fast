# Legacy (arb-lab) fixtures

These are the offline inputs of the legacy known-answer tests (PLAN WP-00b, review F12). WP-07's golden ledger cases and WP-10's legacy reader read only this directory and `testdata/wallet/`. Nothing here needs the network or Cherry.

## Files

| Path | What | Made by |
|---|---|---|
| `raw/<seg>/*.jsonl.xz` | Full arb-lab v1 files (`attempts`, `outcomes`, `bundles`, `copies`, `status`) of w5h-p1 … w5h-p10 (res-pnl p1-p10), w5h2-p5 (the bolt trade, #648) and w5h3-p2 (mispricing case #664, rival failures #662-#704). The schemas are in MEASUREMENT.md §7. | Preserved on 2026-10-04 during the plan revision; unchanged since |
| `raw.sha256` | sha256 of each `raw/` file, paths relative to `raw/` | as above |
| `wins/<seg>/{outcomes,attempts}.jsonl.xz` | The verbatim v1 lines of the wins only, for the w5h2/w5h3 segments that have no full copy in `raw/`: w5h2-p1, p2, p3, p6 … p11 and w5h3-p1. Together with `raw/w5h2-p5` and `raw/w5h3-p2`, they cover all 24 wins of wallet-synthesis §3. | `tools/capture-fixtures.py --wins` |
| `exec/w5h-p10.slice.jsonl.xz` | 4,353 `exec.jsonl` v1 lines (PumpSwap transactions only): the 15 slots around w5h-p10's 7 landings, from the trigger slot to the landed slot + 1 | `--exec-slice` |
| `signatures.json` | `cases`: 13 ledger cases with their full signatures, the chain values (fee the wallet paid, lamport change, WSOL change, tip, created accounts and their rent) and the v1 outcome line. `landed`: all 119 landed wallet transactions of w5h-p1..p10, 2 of them unrecorded by the bot. `wins_w5h2_w5h3`: the 23 bundle wins and the bolt win of w5h2/w5h3. | Picked by hand from res-pnl and wallet-synthesis; chain values computed from `testdata/wallet/` |
| `expected.json` | The known answers: res-pnl's p1-p10 decomposition (per segment and in total, liquid balances, residuals, fee split, eras, ledger sums), wallet-synthesis §2's bundle-arm and bolt figures, the §4.42 ledger line of every case, and the expected exec slice and pool-bot bins | The research numbers were copied from the documents. The fixtures reproduce every one of them. |
| `pool-bots.json` | The number of distinct arbitrage bots on each pool (1,267 pools) from the patterns scan of w5h-p1..p15. It also lists the 21 pools with 150 or more bots (PATTERNS.md item 10), which are the input of `data/crowded-pools.json` (WP-00). | `--pool-bots` |
| `fixtures.sha256` | sha256 of every fixture file here and in `../wallet/`, paths relative to `testdata/` | `--manifest` |
| `test_legacy_fixtures.py` | Python checks (standard library only) | — |

## Cases

| `id` | Transaction | WP-07 golden case |
|---|---|---|
| `transfer_in_funding` | Creates and funds the wallet (4,349,000,000); paid by another signer | transfer in |
| `nonce_create` | Creates one durable-nonce account (rent 1,056,640) | create only |
| `wsol_ata_create_wrap` | Creates the WSOL ATA and wraps 4.2 SOL | wrap |
| `foreign_failed` | A failed transaction that another signer paid for and that lists the wallet; the wallet does not change | — |
| `landed_fail_compete_bid` | w5h-p2#0, fee 1,305,030 | failed transaction |
| `landed_fail_unrecorded` | w5h-p1#2, fee 7,301; it landed but has no outcome line | failed transaction (chain only) |
| `landed_fail_venue_error` | w5h-p6#44, DLMM 0x1794 | failed transaction |
| `win_no_create` | w5h-p7#96, residual 0 | — |
| `win_negative_trade_net` | w5h-p3#96, round trip 710 against a fee of 8,362 | — |
| `bundle_win_ata_create` | w5h-p10#2, SPL account 1,488,440 left open | bundle win with an ATA create |
| `bundle_win_token2022_create` | w5h-p9#976, Token-2022 account 1,513,840 | Token-2022 create |
| `bundle_win_accumulator_create` | w5h-p6#69, PumpSwap accumulator 1,346,200 (not recoverable) and Token-2022 account 1,513,840 | accumulator creation |
| `bolt_direct_win` | w5h2-p5#648, +27,459,627 | the bolt trade |

The wallet has no **create-and-close** or **unwrap** transaction up to 2026-10-04. WP-07 builds those two cases synthetically from the MEASUREMENT.md §4.42 table.

## Use

```sh
python3 -m unittest testdata/legacy/test_legacy_fixtures.py   # integrity + every known answer, from the files alone
cargo test --release --test legacy_fixtures                    # integrity, cases, landing sums (tests/legacy_fixtures.rs)
python3 tools/capture-fixtures.py --verify                     # sha256 and coverage only
```

- **v1 lines.** In Python, `lzma.open(path, "rt")`, one JSON object per line. In Rust, use the wallet JSON. No xz crate is in the tree.
- **Wallet transactions.** `testdata/wallet/<sig>.json` is the `getTransaction` result: `transaction` = [base64 wire bytes, "base64"], with a JSON `meta`. The account keys are the static keys of the message plus `meta.loadedAddresses.writable` and then `.readonly`. Inner instruction `data` is base58. Both tests carry a small decoder.
- **Signatures.** Every `sig` anywhere in `signatures.json` has a wallet file. A `landed` row with `recorded: false` is a copy signature from `attempts.jsonl` that landed with no outcome line.
- **After changing any fixture,** run `python3 tools/capture-fixtures.py --manifest`. Both tests fail on an unlisted file or a hash mismatch.

## Conventions (`expected.json` → `conventions`)

- `fee` is what the wallet paid. It is 0 when another account is the fee payer.
- `tip` is a System transfer from the wallet, in an ok transaction, to an account that is neither created in that transaction nor a wallet token account.
- `rent` of a created account is its lamports. For the WSOL account, it is the lamports minus the token amount.
- Token and nonce accounts are recoverable (`rent_locked`). The PumpSwap user volume accumulator is not (`rent_nonrecoverable`).
- Only route transactions have a trade:
  - ok: `trade_gross = equity_delta + fee + tip + rent_nonrecoverable`;
  - failed: `trade_gross = 0`, so `trade_net = −fee`.
  - The sum of `trade_net` over the 119 landings is res-pnl's −2,337,448.
- In a non-route transaction, `fee_other` holds the wallet's fee, and any other equity change is `transfer_in` or `transfer_out`.

## Not here

- **The full `exec.jsonl.zst` files** of w5h-p10, p12, p14 and p15 and of w5h2-p1 and p2 are 59-162 MB each, too large for the repository. The authoritative copies are on Cherry under `/root/arb-lab/runs/<seg>/`. The w5h-p10 slice stands in for them in the legacy reader's tests.
- **`seed-pools-w4.csv`** is in `data/` (commit c777f26).

## Provenance

- **`raw/`**
  - Copied from the arb-lab runs (Cherry `/root/arb-lab/runs/<seg>/`) on 2026-10-04.
  - Before copying, every line was checked against API-key, token, bearer, URL and password patterns.
  - `meta.json` and `*.out` were deliberately not copied: v1 meta holds Debug strings of the config.
- **`wins/` and `exec/`**
  - Taken from the same run files, through the session's read-only copy of Cherry.
  - Every kept line was checked against the secret patterns in `tools/capture-fixtures.py`.
- **`testdata/wallet/`**
  - Fetched on 2026-10-04 from the public endpoint `https://api.mainnet-beta.solana.com` with `getTransaction` (`encoding: base64`, `maxSupportedTransactionVersion: 0`, `commitment: finalized`).
  - The fetch was read-only and made by `tools/capture-fixtures.py --wallet`.
- **Completeness of `landed`**
  - The wallet's `getSignaturesForAddress` list shows no other transaction between the first and last landing.
  - `tools/capture-fixtures.py --discover` re-checks the list online with `getSignatureStatuses` over every copy signature.
- **`pool-bots.json`**
  - Built from `scan-w5h-p1.json` … `scan-w5h-p15.json` (Cherry `/root/arb-lab/tmp-patterns/`, scanned 2026-10-03).
  - The sha256 of each scan file is recorded in `pool-bots.json`.

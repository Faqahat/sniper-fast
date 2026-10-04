# Recorded RPC responses (fixtures, PLAN WP-03b)

The chain-fetch tests (`src/chainfetch/tests.rs`) serve these replies from a fake chain (`src/rpc/tests.rs` scripts its HTTP providers instead). Every file
here is a JSON-RPC reply exactly as `https://api.mainnet-beta.solana.com` (solana-core 4.3.0) returned it on 2026-10-04,
read-only, unless marked *cut*. Nothing here holds a key.

| File | Request | Use |
|---|---|---|
| `getBlock-453032285-signatures.json` | `getBlock(453032285, {encoding: "json", transactionDetails: "signatures", rewards: false, commitment: "confirmed", maxSupportedTransactionVersion: 0})` | The slot index: 1,193 signatures. Our wallet's two transactions of the slot sit at positions 29 and 154, their `getTransaction` `transactionIndex` (`testdata/wallet/26qXmMyR….json`, `4RT9wvEg….json`) |
| `getBlock-453034309-skipped.json` | the same for slot 453034309 | A skipped slot: error -32009 ("was skipped, or missing in long-term storage"). `getBlocks(453034000, 453034499)` lists 453034308-453034311 as skipped |
| `getBlock-453034312-signatures-first40.json` | the same for slot 453034312, *cut* to its first 40 signatures | The block after the skipped run: `parentSlot` 453034307 shows the four slots between were skipped (no RPC call needed for them) |
| `getBlock-453032285-full-first30.json` | `getBlock(453032285, {encoding: "base64", transactionDetails: "full", rewards: false, commitment: "confirmed", maxSupportedTransactionVersion: 1})`, *cut* to the block's first 30 transactions (indexes 0-29 kept) | The coverage sampler, and the conversion of RPC transactions (legacy, v0 and v1 / SIMD-0385) into exec.jsonl records. With `maxSupportedTransactionVersion: 0` the provider refuses this block (-32015: it holds 181 v1 transactions). The whole block (6.15 MB: 1,193 transactions, 753 legacy, 259 v0, 181 v1) is not kept (too big; and every file a test reads lives here, PLAN-ADDENDUM I-11). It was checked once, 2026-10-04, from the public RPC: every one of its 1,193 transactions converted with `chainfetch::txjson::from_rpc` (keys = balances, fee and status as the meta says) and sat at its position in `getBlock-453032285-signatures.json` |
| `getSignaturesForAddress-2g7rYv7y-before-4RT9wv.json` | `getSignaturesForAddress("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", {limit: 12, before: "4RT9wvEg…", commitment: "confirmed"})` | Wallet source (d): 12 signatures, each with its `getTransaction` reply in `testdata/wallet/` |
| `getLatestBlockhash.json` | `getLatestBlockhash({commitment: "confirmed"})` | The blockhash poll |

The `getTransaction` replies the tests serve are `testdata/wallet/<sig>.json` (WP-00b; `encoding: "base64"`).

To fetch again: the same requests with `curl -X POST -H 'content-type: application/json'` against any provider; the
full block was cut with `json.load` / `json.dumps` (first 30 entries of `result.transactions`; plain JSON: the repository
ignores `*.zst`).

# Wallet transactions (fixtures)

Each `<sig>.json` file holds one transaction of wallet `2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE`, the arb-lab trading wallet. The file is the `result` object of `getTransaction`, re-serialized with sorted keys.

- **How it was fetched:** `encoding: "base64"`, `maxSupportedTransactionVersion: 0`, `commitment: "finalized"`.
- **The `transaction` field** is `[<base64 wire bytes>, "base64"]`.
- **The `meta` field** is JSON. It holds balances, token balances, logs, and inner instructions with base58 `data`.
- **Other fields:** `slot`, `blockTime`, `transactionIndex` (the position in the block) and `version`.

147 transactions are stored here:
- the 119 landings of w5h-p1..p10;
- the 24 wins of w5h2/w5h3;
- 4 wallet setup transactions: funding, a nonce create, the WSOL ATA create and wrap, and a foreign failed transaction.

`testdata/legacy/signatures.json` lists every one of them with its role. `testdata/legacy/fixtures.sha256` holds their hashes. `testdata/legacy/README.md` describes how they are used.

They were fetched once, on 2026-10-04, from the public endpoint with `python3 tools/capture-fixtures.py --wallet`. The fetch was read-only. To fetch again from a different endpoint, run `--wallet --refetch --rpc-url-env <VAR>` and then `--manifest`.

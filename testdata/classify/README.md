# Transfer classification fixtures (PLAN WP-08 item 3)

Inputs of `src/classify/tests.rs`, the offline acceptance of the transfer classification (MEASUREMENT §4.14 derived
fields, A.4 kinds).

- **`<sig>.json`**: one transaction each, the `result` object of `getTransaction` (`encoding: "base64"`,
  `maxSupportedTransactionVersion: 1`, `commitment: "finalized"`), re-serialized with sorted keys: the same layout as
  `testdata/wallet/`. `signatures.json` lists them with what each one shows (`txs`), and names the two transactions of
  our wallet the tests take from `testdata/wallet/` (`wallet`). They are other signers' transactions, found on
  2026-10-04 by scanning public mainnet blocks for CPI tips, wraps, unwraps, PumpSwap creator fees and Glaive tips, and
  fetched from the public endpoint (read-only). To fetch them again: `python3 tools/capture-fixtures.py --classify`
  (`--refetch` to replace them, `--rpc-url-env NAME` for another endpoint).
- **`cmp2-rival-tips.json`**: the tips that cmp2's arbx (the 2026-10-04 side-by-side shadow run on Cherry,
  `docs/research/cmp2-shadow-comparison.md`) recorded in rivals.jsonl with no sender, by tip account (rows, tips,
  lamports): every account with at least 20 rows, and every account `data/sender-tip-accounts.json` lists. Built once
  by a stream pass over that run's 603 MB rivals.jsonl (849,585 rows; 43,707 with an unnamed tip). The test checks that
  the code's lists (send/mod.rs `code_tip_names`, the map cmp2 ran with) named none of them and that the full map
  (`send::tip_owner_names`, which rivals.jsonl and exec.jsonl now both use) names Glaive's 4,197 rows, Soyas' 458,
  bloXroute's 72 and Solami's 16. About 33,800 rows over about 190 accounts stay unnamed; the largest is AgmLJBMD...
  (4,671 rows), then the eight FAST... accounts (4,158 rows together).

The tests' expected kinds and amounts are checked against the transactions' own balance and token-balance changes (the
test comments give the sums).

# Legacy wallet fixture

`wallet-w5h-p1-p10.jsonl.xz` holds the 123 transactions of wallet `2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE`
whose block time falls in the w5h-p1..p10 window (first attempt - 60 s to last attempt + 120 s): one JSON line
`{"sig": ..., "tx": <getTransaction result>}` per transaction, `json` encoding, sorted by slot.

- Source: the research capture `work/pnl/chain_txs.jsonl` (public Solana RPC, read-only, fetched 2026-10-03 for
  docs/research/res-pnl.md). Public chain data only; no keys or URLs.
- sha256 `3687ee90e2750586a8178f98b128965a815752358c784855e329bc63077e45be` (checked by `tests/test_legacy.py`).
- Used by the res-pnl known-answer test: it supplies the two landed failures the bot never recorded (w5h-p1#2,
  7,301; w5h-p2#8, 14,294) and splits the win rent into token-account rent (15,036,800) and the PumpSwap
  accumulator (1,346,200).

When WP-00b's `testdata/wallet/<sig>.json` exists, the tests read it instead (same transactions; base64 encoding).

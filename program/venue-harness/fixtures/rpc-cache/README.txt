Read-only mainnet RPC responses (api.mainnet-beta.solana.com, 2026-10-04, slot ~453.2M) cached by
program/arbx-sizing/research/solrpc.py: one JSON per request ({request, fetched_at, result}), named
<method>-<sha256(request)[:20]>.json. getMultipleAccounts files hold the pool/config/mint/bin-array snapshots that
DESIGN.md §2 was verified against; getSignaturesForAddress/getTransaction files hold the PumpSwap swaps whose events
verify §2.1. Re-running the research scripts reads from here and never re-queries.

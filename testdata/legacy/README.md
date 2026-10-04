# Legacy (arb-lab) fixtures

`raw/` holds arb-lab run files preserved on 2026-10-04 during the plan revision (docs/reviews/plan-changes.md, F12), because their only local copy was a session-scoped scratch directory that will disappear. The authoritative copies are on Cherry under `/root/arb-lab/runs/<segment>/`.

- Segments: w5h-p1 … w5h-p10 (res-pnl p1-p10), w5h2-p5 (the bolt trade, #648), w5h3-p2 (mispricing case #664, rival failures #662-#704).
- Files per segment: `attempts.jsonl`, `outcomes.jsonl`, `bundles.jsonl`, `copies.jsonl`, `status.jsonl` (arb-lab v1 schemas, MEASUREMENT.md §7), compressed with `xz -9`.
- Checked before copying: no line matches API-key, token, bearer, URL or password patterns. `meta.json` and `*.out` were deliberately not copied (v1 meta holds Debug strings of the config).
- Integrity: `raw.sha256` (sha256 of each `.xz` file, paths relative to `raw/`).

WP-00b (docs/PLAN.md) completes this directory: `signatures.json`, `expected.json`, and the wallet transactions fetched once from public RPC into `testdata/wallet/`.

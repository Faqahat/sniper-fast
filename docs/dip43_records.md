# dip43 records

## Builder C: snipe-guard (C2)

| Record | Field | When written | Content |
|---|---|---|---|
| `presend_attempt` | `guard` | every try, only with `--presend-live-guard deadline\|holders` (absent with the guard off = dip42's record) | snipe-guard try: `{mode: "deadline"\|"holders", n_floors, ix_bytes, keys, arm?: "G" (A/B on), max_viol?, floors?: [[wallet8, floor_whole_tokens], …], age_ms?, reason?: "no_snapshot"\|"stale"\|"few_holders"\|"size", dropped?}`; the A/B's Lighthouse arm: `{mode: "lighthouse", arm: "L"}` |
| `presend_attempt_land` | `res` | each try's result | with the guard on, a snipe-guard try that failed at the guard instruction: `"deadline"` (late, as Lighthouse's), `"guard_abort"` (any other decoded kind, or an unknown code), `"guard_other"` (a non-custom failure at the guard). Lighthouse tries: as dip42 |
| `presend_attempt_land` | `guard_abort` | a snipe-guard try that failed at the guard (only with the guard on) | `{kind: auth\|data\|accounts\|deadline\|curve_high\|curve_deep\|floors\|admin, idx (sub-reason or the worst holder's index in the try's `guard.floors`), cnt (holders below), gap_bucket, gap (words), sub? (auth/data/accounts/admin sub-reason), code: "0x…"}`; an unknown code: `{kind: "unknown", code}`; a non-custom failure: `{raw: err}`. Decoded with `snipe_guard::client::decode` (table: ops/guard/codes.md). Join to the try's `presend_attempt` by `sig`. |

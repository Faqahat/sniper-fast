# r76: snipe-guard flags (dip43 C2) — the owner's choice is open

Prerequisites: the program is deployed on mainnet, `sg_ops verify` and `sg_ops smoke` PASS (ops/guard/DEPLOY.md), and `CYBERjpcrxMLkZyuvP3D3aEKpvuTKHiwwU8cvT5TudiZ` is the
id the deploy printed. The engine accepts the id ONLY from the flag. Without any of these flags the run is dip42's (Lighthouse deadline,
byte for byte). Rollback = drop the flags (or `--presend-live-guard off`) and restart.

The run's wallet must be compiled in (AMS `EgxfYgEb…`, FRA `2g7rYv7y…`, FRZ `FRZh63L6…`): no allowlist flag needed. Any other wallet:
add it to the allowlist PDA and append `--presend-live-guard-allowlist <PDA>` (else the engine refuses to start).

## (a) deadline mode with the landing A/B (recommended first: measures whether a private program costs landing)

Append to the r76 command:

```
--presend-live-guard deadline --presend-live-guard-program CYBERjpcrxMLkZyuvP3D3aEKpvuTKHiwwU8cvT5TudiZ --presend-live-guard-ab on
```

- Odd windows: snipe-guard with the same slot deadline only; even windows: Lighthouse (dip42). Fills, fees, exits unchanged.
- Each `presend_attempt` gets `guard {mode: "deadline", arm: "G", n_floors: 0, ix_bytes: 14, keys: 0}` or `guard {mode: "lighthouse", arm: "L"}`.
- A late snipe-guard try lands as `res: "deadline"` with `guard_abort {kind: "deadline", gap_bucket, gap: "2 slots", …}` on
  `presend_attempt_land`; anything else at the guard is `res: "guard_abort"` (`kind` auth / data / accounts…: a configuration fault).
- Compare per arm: same-slot rate, block index, send → seen ms, fills per 1k tries (gate from the spec: >= 20k tries per arm, no penalty).
- Without `--presend-live-guard-ab on`: every window uses snipe-guard (no A/B).

## (b) holders mode (onchain G-A: abort when MORE THAN 1 of the top 6 holders is below 90% of its balance at signing)

Append to the r76 command:

```
--presend-live-guard holders --presend-live-guard-program CYBERjpcrxMLkZyuvP3D3aEKpvuTKHiwwU8cvT5TudiZ --presend-live-guard-holders 6:0.9:1:1.0 --presend-live-guard-max-age-ms 5000
```

(`6:0.9:1:1.0` and `2000` are the defaults; written out so the command shows them. Add `--presend-live-guard-ab on` to keep a
Lighthouse control arm.)

- N:THETA:MAXLEAVERS:MINPCT = the top N holders by TRUE balance at signing (ours excluded, >= MINPCT % of supply), floor = THETA x
  balance, the try aborts when MORE THAN MAXLEAVERS are below their floor (1 = abort at 2 or more; the verifier: K = 2 leavers
  positive across N 3–10, θ 0.5–0.99, size 0.25–2 %; K = 1 fails).
- **The floors come from the true-balance book (Builder A, A3; wired at the merge 11-10).** Holders mode needs `--presend-live-tbal on`
  (or `--presend-live-cascade on`) and `--presend-live-fam-log` (the arm's RPC read of all the mint's token accounts): the engine refuses
  to start without it. A window's floors are set at its arm, again when the snapshot arrives, and again on every trade of the mint. No
  snapshot yet (`reason: "no_snapshot"`) or one older than `--presend-live-guard-max-age-ms` (default 2000, measured from the snapshot's
  arrival; `reason: "stale"`) signs the deadline only; a send never waits for balances.
- A try that would exceed 1,232 bytes drops floors from the tail (`guard.dropped`); with the default 6 floors it never does (~1,116 bytes:
  the 894-byte dip42 sample try − 2 for the deadline + 6 × 37 per floor); N 10 with the largest tip + the loaded-data limit drops some (tested).
- A floors abort: `res: "guard_abort"`, `guard_abort {kind: "floors", idx: <worst holder #>, cnt: <holders below>, gap_bucket, gap}`;
  the holder list of the try is on its `presend_attempt` (`guard.floors: [[wallet8, floor], …]`).
- CU: the guard costs 330 (deadline only; Lighthouse ~400) .. 1,445 (6 floors) CU (LiteSVM, mainnet features), inside the unchanged 120,000 limit (buys max 102.2k measured).

## Start-up check (both modes)

The engine refuses to start unless: the program account is executable; a try with a deadline 50 slots ahead passes in simulation and
one 50 behind fails at the guard with the decoded deadline code (holders: two empty floors fail with the floors code); the wallet is
compiled in or the allowlist flag is given. Look for `GUARD verified on chain (simulated): …` and the banner line
`GUARD (dip43 snipe-guard) …` in the start log (with no flag the banner says `GUARD (dip43 snipe-guard) off …`).

## 11-10 update
- Deployed: id CYBERjpcrxMLkZyuvP3D3aEKpvuTKHiwwU8cvT5TudiZ (see DEPLOY.md).
- attack75 study: use max-age **5000** ms for holders mode (2000 would have missed the r75 Gt5xJCmX rug: snapshot 3.2 s old).

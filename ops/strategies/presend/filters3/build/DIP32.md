# dip32 build (LOCAL ONLY, not released / not deployed) — 11-03 PKT

Owner 11-03: build the verified filters together with the circuit breaker for the next run; no release of the breaker alone.
Decisions come from FILTERS-3 (filters3/audit, quiet3, tail, ten, verify, tune).

## What is in the engine (src/bin/snipe_engine/pslive.rs, psrearm.rs; 115 bin tests pass)
| flag | live / log | rule | evidence |
|---|---|---|---|
| `--presend-live-cr-loss 2:0.05` | LIVE | skip T2 `cr_loss` / re-arm `rearm_cr_loss` when the token's creator has >= 2 of our earlier positions realizing <= -0.05 SOL together (kept positions only, all-time, state file) | tune: DEV +0.87, VAL w/o attack +1.70, HOLD +0.54, + w/o top 5 everywhere; engine-rule replay r39–r46 +3.08 SOL (173 blocks, 56 winners) |
| `--presend-live-creator-state FILE` | state | creator histories preloaded at start, saved every ~10 min (off the event loop) and at the run's end | seed: /home/moiz/sniper-data/filters3/build/creator_state_seed.json (1,337 creators, r39–r46) |
| `--presend-live-breaker 2:0.2:10:30` | LIVE | after 2 losses <= -0.2 SOL within 10 min: no new buys 30 min | fired only on the 11-02 attack (+1.54); never in DEV / HOLD |
| `--presend-live-f3-log` | LOG | arm/skip records get `f3`: q3a (QUIET3-A: T2, n_120s <= 15 & wh_dumps <= 3), fresh / fresh_n (holders >= 2% with <= 1 hold, not the whale/dumper; TAIL G3 = fresh >= 35%) | QUIET3-A WEAK on holdout; G3 = attack guard (caught all 9 template trades, ~0 cost otherwise) |
| (always with the gate) | LOG | `cr` on arm/skip records: {n, sum, last, unf3} — unf3 = QUIET3-B (creator's last <= 3 in 24 h all not followed) | with the engine's strict follow label: −0.39 on r39–r46 → stays log-only |
| `--presend-live-cr-unfollowed K:H` | built, NOT recommended | QUIET3-B live | not proven on top of the ledger |

Realized records get `cr: {creator, followed}` (the label the engine used).

## Proposed next-run additions (on top of the run 42 config)
```
--presend-live-cr-loss 2:0.05 --presend-live-creator-state /root/dip/creator_state_ams.json --presend-live-breaker 2:0.2:10:30 --presend-live-f3-log
```
(copy creator_state_seed.json to /root/dip/creator_state_ams.json first; needs owner OK to deploy and start)

## Kept as is (live): create-slot skip (+2.6/day est, strongest), QUIET skip + stop, age-1, lone whale.
## Dashboard verdicts (tune): group risk = keep logging; safe timer / holder clock / landing guard / ctx85 = dismiss (still logged by
## the engine; rows can be dropped from dipmon later). New dipmon rows: creator loss / unfollowed (only when they fire), QUIET3-A (log),
## fresh holders >= 35% (log). filters_report.py has the same.

## Expected value (honest): about +1 to +2 SOL/day on normal days, more on attack days. Not 10/day (landing speed is the big lever).

## Pending next build (LOCAL ONLY, not released; owner 11-03: "set up 2,3 as log only for next release, don't release yet")
- `--presend-live-tag-wallets W,W,...` (needs --presend-live-f3-log; <= 8): T2 arm/skip + re-arm arm records get
  "tags": {wallet prefix: {n, hold, rt}} for listed wallets that already traded the token (9pQQ study lead C: "9pQQ round-tripped
  this token before"). Suggested list: 9pQQc1xy..., 8PgC4ngp..., haqq6qnV....
- f3 gets "r41": the T2 trigger's tx ran program 41Pr4XqEcmgV1PqZF9yccpuFvxF7PpKLGfTD9jWJBn1q (9pQQ exact study lead).
- Bin tests 115 pass. Run-script support not added yet (needs a PSV entry for --presend-live-tag-wallets).

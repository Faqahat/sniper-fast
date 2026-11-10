# ASTRA: Astralane VIP1 A/B in AMS run 38 (10-29 PKT)

## In short
- Run 38 sends every armed window's pre-sent tries **alternately** through `helius-ps` and `astralane-ps`. The engine already
  does this (`pslive.rs`: route = `[(n + w) % 2]`), so we get a paired A/B inside one run.
- Read it with `ops/lanes/astra_ab.py`. On run 37 it reproduces the quoted baseline exactly. On a fake split of run 37
  (the same path under two names) it finds no difference.
- Settings for run 38: global 60/s, 40/s per path, `astralane-ps` capped at 19/s, routes 1:1.
  Rate check on run 37's real demand: Astralane refuses 0.9% of its tries. If dip26's re-arm doubles the demand, it refuses 4.2%.
- Rivals: 7 of the 20 active wallets rely on Astralane. **None of the 6 biggest dump-race winners use it.** Expect a small
  effect. The A/B will show the size.
- Nothing has been applied on any server: the config snippet and the run-script patch are files here.

## Before run 38 (the owner does this)
1. Add `ops/lanes/astralane_ps.toml.snippet` to `/root/sniper-dip/dip_edge_ams.toml`, right after the `helius-ps` block.
   The run script copies this base config for `--region ams`. The snippet uses `${ASTRALANE_KEY}` from the `.env`.
2. Optional: apply `ops/lanes/run_script_astra.patch` (needed only for a global cap above 50).
   - Copy the script to `run_dip_prod.sh.new`, patch the copy, run `bash -n`, then `mv`. Never edit the running script in place.
   - Rebase it if dip26 changes the script first.
   - Without the patch, use `--presend-live-max-per-sec 50`. The rate check shows almost no difference (17 global skips in 12 h).
3. Flags to add or change on top of the dip26 command:
   `--presend-live-routes default=helius-ps+astralane-ps --presend-live-max-per-sec 60 --presend-live-path-max-per-sec 40`
   - Do NOT pass `--presend-live-tip-lamports`: it would give both paths the same tip.
   - Keep `k` at 8.
4. Check the start lines:
   - `FAST: path astralane-ps -> own HTTP/1.1 conn (binary)`.
   - `routes default=helius-ps(fast)+astralane-ps(fast)` (the pre-send line).
   - `60 attempts/s (40 per path)`.
   If astralane-ps shows `(async)`, every try takes 2 of its 19 rate slots (about 9.5 tries/s). Stop and tell the owner.

## Hourly check (README)
Copy the files read-only to the host, then run the tool on the host. Never write on the server.
```
ssh -p 1996 it@cyberams 'sudo cat /root/prod/runs/dip_ams_r38.jsonl' > /home/it/sniper-data/lanes/r38.jsonl
ssh -p 1996 it@cyberams 'sudo cat /root/prod/runs/dip_ams_r38.log'   > /home/it/sniper-data/lanes/r38.log
python3 /home/it/sniper/ops/lanes/astra_ab.py /home/it/sniper-data/lanes/r38.jsonl --log /home/it/sniper-data/lanes/r38.log --sol off             # ~5 s
python3 /home/it/sniper/ops/lanes/astra_ab.py /home/it/sniper-data/lanes/r38.jsonl --log /home/it/sniper-data/lanes/r38.log --last-hours 1 --sol off   # last hour only
python3 /home/it/sniper/ops/lanes/astra_ab.py /home/it/sniper-data/lanes/r38.jsonl --sol-boot 100 --json /home/it/sniper-data/lanes/r38_ab.json   # with SOL, ~2 min
```
Read the SUMMARY block at the end first.
- `alternation check` must say `0 differ`, and the tries must split about 50/50.
- `acks not 200` on astralane-ps should stay near 0. Above 1% it is rate limiting or a key problem: tell the owner.
- Look at landed share, same slot, p50/p90 and their CIs (section 5).
- Look at "first to land after each dump" (section 3) and the fill race (section 2).
- Trust P&L by fill path (section 4) last. Token luck dominates it: the fake split showed a false +21 mSOL difference with p = 0.04.
- At the end of the run, the SOL number on the run's own windows needs the recorder tape:
  `astra_ab.py --build-tab r38.jsonl /home/it/sniper-data/lanes/tab_r38`, then
  `astra_ab.py r38.jsonl --sol own --tab /home/it/sniper-data/lanes/tab_r38/tab --sol-boot 100`.

## What the tool reports
1. **Per path, and per path x leader client** (MEASURED):
   - tries, landed share, same-slot share, slots after send, send->land p50/p75/p90;
   - acks (HTTP status and ms), result classes, the tip;
   - skipped ticks per path, inferred from gaps in each window's tick numbers;
   - the engine's `not-sent` counts from the 60 s status lines (all paths together).
2. **Fill race**: fills by path, against each path's share of the window's tries before the fill.
3. **First to land after each dump**: only dumps where both paths had a try in flight. Shows the winner share, each path's
   first-try position, and the paired lead in ms (block clock, INFERRED).
4. **Positions by fill path**: realized P&L, a label-shuffle test, and entry quality (outside trades between the dump and our
   fill, price above the dump's).
5. **Paired per window**: differences with cluster-bootstrap CIs that resample whole windows (90% by default).
6. **SOL (INFERRED)**: each path's measured send->land distribution is fed into the calibrated speed35 replay. Each try's latency
   is replaced, per leader client, by the path's latency at the same rank. It answers "if ALL tries had path X's landing, P&L
   would be ±Y SOL (±Z SOL/day)", against the run's real mix.
   - The CI re-measures each path on resampled windows, so the paths' own noise is included.
   - `base` mode replays the 911 calibrated r36+r37 windows. `own` mode replays the run's own windows (`--tab`).

## Validation on run 37 (MEASURED)
- **Records view** (as the baseline was computed), on the copy with 34,548 tries:
  - 99.7% land records per try, same slot 41.1%, p50/p90 83/207 ms.
  - Per leader client:

    | client | tries | same slot | p50/p90 ms |
    |---|---|---|---|
    | AgaveBam | 10,808 | 34% | 94/214 |
    | JitoLabs | 8,781 | 41% | 110/197 |
    | HarmonicAgave | 7,336 | 50% | 69/181 |
    | HarmonicFiredancer | 3,800 | 42% | 87/164 |
    | Firedancer | 2,206 | 41% | 87/249 |

  This matches the quoted baseline exactly.
- **Correction:** the 99.7% counts `unseen` land records as landed.
  - Per distinct tx: 33,939 txs, 99.2% landed, 0.8% never seen, same slot 42.2%, p50/p75/p90 83/142/207 ms.
  - 609 tries were byte-identical repeats of an earlier try (same blockhash, deadline, limit and tip account, about 265 ms
    later). Each is one tx, so it can land only once; 90 of them have an unclear send time and are left out of the ms numbers.
  - Status lines at the same point: not sent = 154 paused for an open position, 46 `rate_path`, 309 `rate_path_config`.
- **Fake split** (alternate tries renamed `fake-ps` by the engine's own rule):
  - 16,958 / 16,981 tries.
  - Differences, 90% CIs: p50 -0.0 ms [-0.9, +0.6], p90 +0.7 ms [-0.5, +1.8], same slot -0.1 pt [-0.5, +0.3].
  - First after a dump 51.8% / 48.2% (CI 48.8-54.8%). Fills 99 / 95 against 96.7 / 97.3 expected.
  - SOL -0.08 SOL/day [-0.17, +0.11] (base) and -0.08 [-0.20, +0.06] (own). Both CIs contain 0, as they should.
- **One path:** helius-ps against the mix = exactly 0. The replay's "today" equals speed35 (sim +3.280 SOL, 224.6 fills; scenario identical).
- **Positive control:** fake-ps latencies x0.45 (median 35 ms) gives **+0.76 SOL/day [+0.50, +1.01]**. speed35 found +0.85/day
  for a 35 ms median, so the conversion responds the right way and by about the right amount.

## Rate check (run 37's real tick demand, 11.9 h; MEASURED demand, simulated caps)
- Demand: 689 windows, 34,857 ticks.
- One window = 37.7 ticks/s. Two windows overlapped only 1.0% of the armed time.
- The engine's checks run in this order:
  1. `rate_path`: the route entry's bucket.
  2. `rate_global`: the global bucket.
  3. `rate_path_config`: the path's `[[send]]` `max_per_sec`, counted over any 1 s.

  A refused tick sends nothing, and the window's next tick goes to the other path.
- Simulator check: as-run caps give 39 / 0 / 237 skips. The real run had 46 / 0 / 309; trailing skips are not visible in the records.

| setting | helius sent | helius skips p/g/c | astra sent | astra skips p/g/c | astra refused | seconds astra at cap | astra share |
|---|---|---|---|---|---|---|---|
| today's caps (40/40), 1:1, astra 19 | 17,360 | 0/65/0 | 17,271 | 0/68/93 | 0.9% | 27 | 49.9% |
| **global 60, 1:1, astra 19** | 17,425 | 0/0/0 | 17,277 | 0/0/155 | 0.9% | 26 | 49.8% |
| global 60, 1:1, astra 20 | 17,425 | 0/0/0 | 17,295 | 0/0/137 | 0.8% | 25 | 49.8% |
| global 50, 1:1, astra 19 | 17,418 | 0/7/0 | 17,276 | 0/10/146 | 0.9% | 27 | 49.8% |
| global 60, 2:1 (H,H,A), astra 19 | 23,188 | 0/0/47 | 11,592 | 0/0/30 | 0.3% | 5 | 33.3% |
| global 60, 1:1, astra 19 + dip26 re-arm (+102% demand) | 35,013 | 0/8/107 | 33,673 | 0/7/1,456 | 4.2% | 128 | 49.0% |
| global 60, 2:1, astra 19 + dip26 re-arm | 46,059 | 0/21/754 | 22,957 | 0/14/459 | 2.0% | 74 | 33.3% |

- Re-arm demand comes from the r37 observatory's shadow windows (rule R0), so it is an upper bound.
- **Recommendation: 1:1, global 60, 40 per path, astralane-ps 19.**
  - 19 leaves one slot under Astralane's 20 TPS: our window is measured at send time, theirs at arrival.
  - 1:1 keeps 99% of windows within 40-60% astra.
  - 2:1 protects Astralane but costs a third of its sample and makes Helius bind instead.
- **Fallback:** if `acks not 200` on astralane-ps goes above 1%, set its `max_per_sec` to 15, or go 2:1 (`helius-ps+helius-ps+astralane-ps`).
  Both take effect at the next restart.

## Who uses Astralane (recorder, 10-29 08:15-20:15 PKT; code: ops/lanes/astra_census.py; data: sniper-data/lanes/census)
Only landed txs can be classified: failed txs (67% of lines) roll their tips back.
- Overall: Astralane is on 19.7% of tipped pump trades. Helius is on 53.7%, Jito on 16.3%.
- Rely on Astralane (>= 50% of tipped txs): E2x1 74%, 6VzX 59%, DF7e 51%, EprLoV21, EMKY7r6U, BUkpShoE, 9pQQc1xy (7 wallets).
- Use it sometimes: dKMj 43%, 8PgC4ngp, AEgTuy8L, 7PedQZmc (4 wallets).
- Never or under 5% (9 wallets):
  - The 6 biggest dump-race winners: 77shyvx7, 8yYM, ssssswdk, GKd5, haqq (2.3%), omego.
  - Also sssssDdM, A2kc and 9Sz9GUHp.
- Inactive in the window: HkQ7, CZ77, DYXD, ETwE.
- The race (first buyer within 1 slot after a >= 1 SOL dump, 19,782 dumps): Astralane paid on 17.8% of tipped first-racer
  wins, the same as its 17.7-17.8% share in every racer subset.
- Reading (INFERRED): Astralane is a common lane, but it is not what the winners use.

## Run-script patch, in plain words
- `--presend-live-max-per-sec` may now be up to 60, but only when a route path's `[[send]]` kind is not Helius.
  With Helius-only routes it stays 1..50, as before.
- When it is above 50, the script checks that the Helius paths alone cannot exceed 50/s:
  - Helius cap = number of Helius route entries x the per-path cap, or the path's own `max_per_sec` if lower.
  - Today: 1 x 40, and helius-ps `max_per_sec` 40, so 40/s.
- A non-Helius attempt path must have its own `max_per_sec` in the config.
- The per-path cap stays 1..50.
- The start line now prints the caps.
- Tested in a harness on the base config plus the snippet:
  - Accepted: helius+astra at 60/40, and 2:1 at 60/40.
  - Refused: helius-only at 60, and 61.
  - `bash -n` passes.

## Risks and what could spoil the A/B
- `astralane-ps` must run on its FAST connection (see the start line), else its rate is halved.
- The key's 20 TPS is shared with the reactive `astralane` entry: keep it out of the buy routes during run 38.
  Keep-alives are GET /gethealth without the key.
- Re-arm windows (dip26) raise the demand. In busy seconds Helius gets a few more tries than Astralane (49% vs 51%).
  The tool compares within windows and uses each path's share, so this is handled. But the counts in section 1 are not 50/50 by construction.
- One run is ~12 h. The SOL CI is about ±0.15 SOL/day around a true zero (fake split), so a real gap smaller than ~0.2 SOL/day
  will not show.
- The SOL conversion models where our tries land, not how rivals react. Its base windows are r36/r37.
- Run 37 had a ~3-minute Helius drop at 20:06-20:08 PKT: 294 helius-ps tries in 5 windows got HTTP 200 but never appeared
  on any feed. Their blockhash age was normal, so a stale blockhash did not cause it. A second path is cover for exactly this.
  The A/B shows it as "unseen" per path.
- No server was written to. The patch and snippet are not applied.

Files: `ops/lanes/astra_ab.py`, `astra_rate.py`, `astra_census.py`, `astralane_ps.toml.snippet`, `run_script_astra.patch`;
data in `/home/it/sniper-data/lanes/` (r37 validation outputs, `rate_r37.*`, `census/`).

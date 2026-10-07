# WP-19 / X11 review: revert-protected non-Jito senders (lane/wp19 @ cbeb4db, base fd0ce85, against master eda4c31)

Reviewer: independent agent, 2026-10-07 ~14:00-14:50 UTC. Read-only on the lane, on master, on arb-lab and arbed. No
sender service or RPC was contacted, nothing was signed or sent, no .env, key, keystore or wallet file was read.

**Verdict: merge after fixes.**
- **Merging is safe for money.** Nothing changes for today's configs:
  - all 12 existing deploy configs give byte-identical `arbx check` output (normalized sha256 included) on master's
    binary and the lane's, both on master eda4c31's configs (FT-012 part C's x4size included) and on the lane's;
  - with the route off, the executor makes the same calls (same tip, BAM bid, path, endpoint, tip policy, verified tip
    accounts), and the builder adds no instruction (`cu_price` is 0 everywhere but the revert test).
- **The gate holds** against every attack in the brief (a wrong hash, another host, `http://`, another service's
  record, a missing key, a route without a pin, a dry run, shadow mode). By design it cannot tell a hand-written record
  from a real one (#6).
- **The revert test can only lose fees**, never tips or value: at most 5,000 lamports for each send that lands (10,000
  with Helius's priority fee). For 30 sends that is 150,000 lamports (300,000 with Helius), well inside the 750,000 cap.
- **Four should-fixes (#1 to #4) before the first revert test is run.** They are small and local (protected.rs,
  revert.rs, main.rs).
  - Without #1 to #3, a PASS can be recorded that does not show the protection the route relies on.
  - Without #4, the owner's budget can lose a test's spend.
  - If the lane merges first, do not run `arbx senders revert-test` until they land.
- **#5 matters more than the code.** As built, the protected route can carry almost nothing on today's live config,
  and step 4 of the research note cannot be run. Settle this before buying or requesting keys.
  - Every service except BlockRazor floors its tip at 1,000,000 lamports. That limits routable decisions to bands 3-4,
    which master's live config refuses outright.
  - BlockRazor, at 100,000, could carry band-2 decisions only.
- The rest are notes.

How this was checked (details at the end):
- Read the whole diff: 21 files, +3,598 / -54.
- Built both release binaries: master eda4c31 in a detached worktree, and the lane at cbeb4db.
- Ran `arbx check` on 25 config files, with each binary, with a cleared environment and an empty HOME.
- `cargo test --release` on the lane: 707 passed, 0 failed.
- On master eda4c31, the two tests that 5791d92 fixes fail as stated.
- arbx-report: its 110 tests, plus a WP-19-shaped synthetic segment.
- Recounted the research rows with my own scripts.
- Ran `git merge-tree` against wp23, wp24, wp25 and master.

## What holds (one line each)
- **Off by default, nothing serialized.**
  - `protected_services` (skip if empty) and `protected_route` (skip while off) are left out of the normalized JSON:
    config.rs:856-861. The test pins the send-policy key list: config.rs `wp19_protected_kind_and_hash_stability`.
  - The 12 configs' normalized hashes are unchanged, and so is the full check output (cmp, both config sets).
  - exec_init `cfg_sha256` serializes the same `sends` / `send_policy` values (exec.rs:2619-2625), so it is unchanged too.
- **Same decisions with the route off** (exec.rs:1395-1417, :1454, :1484-1486, :1515, :1560, :1609):
  - `protected_tip` is `None` and `tipped` is the old call.
  - The BAM condition gains only `!protected`.
  - `path_ix` is `bundle_path`, the endpoint is `bundle_host`, `tip_policy` is `self.tips`, and
    `want(.., protected=false)` gives the Jito accounts.
  - No `send_route` is written.
  - Computing `margin_floor` before `tipped` changes nothing: it reads the arms, not the tip policy.
- **Same bytes.** `bundle_ixs` pushes a CU price only when `cu_price > 0` (build.rs:509).
  - `cu_price_for(0, _) = 0` (revert.rs:78-79), and `revert_priority` starts at 0 (exec.rs:1044).
  - Only `revert_test_held` calls `set_revert_priority` (main.rs), on a shadow executor.
- **Records.**
  - copies 1.4 / outcomes 2.2 `service` is written only when set (send/mod.rs:954-955, exec.rs:2196).
  - attempts 2.3 `send_route` only with the route on (exec.rs:1495-1499).
  - bundles 2.1 `service: "jito"` is additive (jito.rs:587). The four bumps are minors.
  - arbx-report refuses only unknown majors (streams.py:21-33, 81-86).
  - Its segment report on a synthetic segment rewritten with WP-19's shapes equals master's, except for the file
    inventory (schema, bytes, sha256). Shapes used: bumped headers, `service` on every bundle, one protected copy,
    attempt and outcome, `send_route` on every attempt.
  - The replay skips header lines (replay.rs:1118). `Sent::from_json` reads a 1.3 line as `service: None` (tested).
- **The gate refuses**:
  - a missing record, a wrong sha256, another service's record, a failing or inconclusive record, and a record whose
    `verdict` contradicts its facts (revert.rs:394-408; tests at revert.rs:567-590 and config.rs
    `wp19_the_gate_reads_the_pinned_record`);
  - a record through another host (revert.rs:404-406, `ams1` test). The host comes from the expanded URL; `None` only
    when the URL is wholly an unset variable, and then `Path::new` fails and the start refuses;
  - `http://`, enabled or not, at parse and again after expansion (protected.rs:147, send/mod.rs:550-556);
  - a route without a pin, with a non-protected path, with a priority-fee service (Helius), or with an empty or
    unknown kind (config.rs:1852-1866);
  - in a live or canary start, an enabled protected path that was not built, e.g. a missing key (exec.rs:958-962;
    test `a_sending_start_needs_the_protected_paths_pin_and_build`), and a route whose path was not built
    (exec.rs:464).
- **No bypass through other modes or commands.**
  - The gate runs in `run()` for `--live`/`--canary` (main.rs:1575-1579) and in `Exec::new` for Live/Canary
    (exec.rs:953-954), so campaign segments hit it too.
  - A dry run builds no path (exec.rs `Mode::DryRun`: `ensure!(paths.is_none())`), and shadow fires nothing (would-sends only).
  - The only ungated sender is the manual `arbx senders --raw` (#11).
- **The revert test can only lose fees.**
  - Every send is the executor's own bundle transaction with on-chain `min_profit = 2^62` (revert.rs:46,
    exec.rs:2136-2138).
  - nexus-arb-v2 compares `after - before` in i128 against it (program/nexus-arb-v2/src/lib.rs:231-241), so the route
    instruction always fails ERR_PROFIT.
  - A failed transaction rolls back every instruction (the ATA create and close, the route, and the tip transfer
    wherever it sits) and charges only signatures × 5,000 plus CU limit × CU price.
  - Each transaction is simulated first (signature verified), and is sent only if it fails with custom 0x4e580002
    (main.rs RouteSource, revert.rs:352-361). One that simulates clean stops the test unsent, which also covers a
    replaced program.
  - `worst_fee` counts exactly what a landing can cost (revert.rs:56-75). Nozomi's appended fee transaction is
    Nozomi's own.
- **Caps.**
  - `n ≤ 60` and `budget ≤ 1.5M` (revert.rs:158-163), and the budget is also at most the owner's remaining budget
    (main.rs:1161).
  - `n × first.worst_fee ≤ budget` is checked before anything is sent, and each send is checked again (revert.rs:192-201).
  - `worst_sent` is charged before the send (revert.rs:202), so an unanswered send counts.
- **Stop at the first landing *seen*.** The chain is polled for every signature sent so far during each gap
  (revert.rs:212-228). Three refusals in a row also stop the test (revert.rs:229).
- **Timeouts and partial results.**
  - A send that times out (5 s) is counted as refused, but its signature is still watched (revert.rs:206).
  - The final wait is at most 240 s and is then `waited=false`, which is inconclusive.
  - A final-check error, an unreadable wallet, or any wallet change gives inconclusive (revert.rs:365-385).
  - A landing whose transaction cannot be read is still a fail (revert.rs:289).
- **Lock and budget.**
  - `manual_start` takes `.supervisor.lock` in `out_dir`, which is `/root/arbx/runs`, the live configs' own. It
    refuses while a campaign, a live segment socket or another `arbx run` exists, and when nothing is left
    (budget.rs:134-149).
  - Every refusal (confirm, service, path, n, budget, size, key) comes before the lock and leaves no entry
    (tests/wp19_revert_cli.rs, 10 cases).
- **`--confirm`** must equal the canonical service name, case-sensitive (main.rs:1147).
- **Secrets.**
  - A query key never reaches a message:
    - network errors use `without_url()` (send/mod.rs:380);
    - `Path::new` errors print the unexpanded template;
    - the ping URL is `join(ping_path)`, which drops the query (send/mod.rs:621; tested);
    - copies, attempts and the record carry the host only;
    - `describe()` carries `${VAR}` templates.
  - Header keys:
    - `HeaderValue` errors do not echo the value (send/mod.rs:390);
    - `Path` has no `Debug`;
    - `Spec`, `ProtectedRoute` and `SendPath` hold no expanded secret.
  - Test: `a_protected_path_posts_its_services_request` (no `SECRET9` in the error).
- **The x11 config** equals master's live x4size config (9e6ba63) in every non-comment line, except `[experiments]`
  (removed) and the 8 added protected paths. All 8 are disabled and https-only, with `max_per_sec = 1`.
- **The research numbers reproduce exactly** (my own scripts, not `analyze.py`):
  - **Totals:** 1,869,934 rows, 0 without a schedule.
  - **By path:**

    | Path | Rows | Failed | Failed share |
    |---|---:|---:|---:|
    | nozomi | 65,317 | 65,125 | 99.7% |
    | helius | 125,378 | 105,166 | 83.9% |
    | astralane | 63,852 | 53,264 | 83.4% |
    | bloxroute | 2,539 | 2,260 | 89.0% |
    | blockrazor | 2,729 | 2,348 | 86.0% |
    | nextblock | 1,029 | 1,024 | 99.5% |
    | lunar | 811 | 760 | 93.7% |
    | untipped | 1,166,006 | 238,146 | 20.4% |
    | jito | 404,386 | 10,338 | 2.6% |

  - **By leader kind:** `other` 18,163 rows (52 wins, 6,625 failed); jito 1,200,659; bam 651,112.
  - **Harmonic:** 498,570 rows = 26.7%.
  - **On `other` leaders:** nozomi 1,016 of 1,019 failed, helius 1,005 of 1,192, astralane 889 of 930; 43 of the 52
    wins untipped.
- **The "Harmonic leader" method is sound for what the note claims.**
  - A slot is Harmonic-led when its leader's gossip `clientId` (`getClusterNodes`, recorded in each segment's
    leaders.jsonl by the LeaderBook, leaders.rs:16-25) starts with `Harmonic` (analyze.py `fam`).
  - It is self-reported, but it is the validator's own client.
  - The inference to a Harmonic path rests on three facts together:
    - no tip transfer in the transaction;
    - 97% on Harmonic against a 26.7% base;
    - 0 failures.

    A Jito bundle with its tip in a sibling transaction would not cluster on Harmonic.
  - Caveats are in #15.
- **The two test fixes in 5791d92 are right.**
  - Owner config commits 902d9eb / 3a01d97 set `rayclmm` / `whirlpool = "send"` in the ft013 and x4size configs, and
    `[pool_refresh] enabled = false` in x4size.
  - The old assertions are stale, not masking a code regression (see "How this was checked" for master's run).
  - The wp21 fix keeps the invariant ("off unless the config sets it").
  - For the campaign test, see #14.

## Findings

### 1. Should-fix: any 2xx from Nozomi counts as accepted, so a black hole passes the revert test
- **Where:** `src/send/protected.rs:189-209` (`reply`, `Request::NozomiBundle => Ok(..)`), `src/send/revert.rs:374-384`.
- **The problem:**
  - For Nozomi, any 2xx whose body is not JSON with an `error` or `success:false` is an acceptance: an HTML page, a
    proxy's 200, `{"result":"queued"}`.
  - Every other service must name a valid signature or a bundle id (protected.rs:204-216), which is positive evidence.
  - A pass needs only "30 accepted, 0 landed, 0 paid". A path that delivers nothing gives exactly that.
- **Failure scenario:**
  - A wrong path or front (`/api/sendBundl`, a Cloudflare host answering 200 with a page), or anything else that
    answers 200 without delivering.
  - That gives 30 "accepted", 0 landed, wallet unchanged: **PASS**.
  - The pin then verifies, because it is the same host. The route sends live protected decisions into a void.
  - That costs nothing in fees, but every routed decision is lost, and the "protected" claim stands unproven.
  - Nozomi is #1 in the ranking.
- **Fix:**
  - Accept Nozomi only on 2xx with an **empty** body (its documented reply). Anything else is a refusal with the text.
  - More generally, record each acceptance's reply kind, and require a positive acceptance shape for a pass.

### 2. Should-fix: the expiry wait fails open when the RPC omits `lastValidBlockHeight`
- **Where:**
  - `src/rpc.rs:1248-1251`: `latest_blockhash` reads `lastValidBlockHeight` with `.unwrap_or(0)`.
  - Used at `src/main.rs:1105` (`RouteSource::next`), then `src/send/revert.rs:204` and `:236-238`.
- **The problem:**
  - A missing or non-numeric `lastValidBlockHeight` makes `last_valid_height = 0`, so `lvh_max = 0`.
  - The first `getBlockHeight` is then `> 0 + 5`, so `waited = true`, and the final check runs about 2 s after the
    last send.
  - The facts then say "expiry waited" when it was not.
- **Failure scenario:**
  - A provider or proxy answers `getLatestBlockhash` without the field (or with a string).
  - Sends that land 10-60 s later are never looked for: a **false PASS**, pinned, then routed.
  - It is unlikely with Haan or Shyft today, but it is fail-open in the one check that makes the test meaningful.
- **Fix:**
  - In `RouteSource::next`, refuse a blockhash whose `lvh == 0` or is not above the current block height (stop the
    source: inconclusive).
  - Have `run` set `waited` only when `lvh_max > 0`.
  - Have `latest_blockhash` return an error instead of 0. It is shared, so check its other callers.

### 3. Should-fix: a pass says nothing about the leaders the route will send to
- **Where:**
  - `src/send/revert.rs:205-210`: the send record has no leader.
  - `:329`: `PathService` sends `leader_kind: None`.
  - `src/config.rs:2083-2097` (the gate).
  - `src/exec.rs:466-469`: the route is keyed by leader kind (`kinds`, `takes`).
- **The problem:**
  - Several shortlisted modes route differently by leader:
    - bloXroute: "the Jito block engine **and the Paladin leader**";
    - Helius: "all pathways ... SWQoS";
    - BlockRazor and NextBlock: undocumented.
  - Each send can land for about 150 blocks. The test window covers whichever leaders happened to come up: about 300
    slots, or 75 leader windows, over 2-2.5 minutes.
  - The record does not say which leaders or kinds each send could have reached.
  - The gate cannot check that the kinds a route will send to (`leader_kinds`, e.g. `["bam", "other"]`) were covered.
  - `other` leaders lead 1.2% of slots (3,320 of the 286,571 slots in step 2's schedules, `wp19/slots.json`). A test
    therefore sees no `other`-led slot about 40% of the time. That is exactly where an unprotected TPU or direct-leader
    leg would land a failure.
- **Failure scenario:**
  - bloXroute passes in a window that happened to contain no Paladin-led and no `other`-led slot.
  - It is pinned, and the route is set to `["other"]`. The first `other`-led protected send lands failed.
  - Revocation then takes the route out, for that segment only (#9).
- **Fix:**
  - Record, for every send, the leaders and kinds of the slots between its send and its `last_valid_height`, from the
    LeaderBook or `getSlotLeaders` (read-only). Put the coverage by kind in the record.
  - `verify_pin` (or `protected_gate`, which knows the route) should refuse a route whose kinds the test did not cover
    with at least k sends. Alternatively, the test waits for a window led by the target kind.

### 4. Should-fix: an error after the sends resets the test's spend to 0 in budget-state.json
- **Where:**
  - `src/main.rs:1163-1165`: the error path, `update(&runs, &name, 0, true)`.
  - `:1234-1238`: the spend is recorded, then the record is written with `?`.
  - `src/budget.rs:152-157`: `update` sets `spent`; it does not add.
- **The problem:**
  - `revert_test_held` books the real spend (`paid.max(fell)`), then writes the record.
  - If `create_dir_all(--out's parent)` or `std::fs::write` fails, `revert_test` overwrites the spend with 0 and marks
    the entry final.
  - The verdict lines are printed only after the write, so the result is also lost (only copies.jsonl remains).
- **Failure scenario:**
  - `--out` points at an unwritable place, or Cherry's disk is full (it has been: FT-013 part B's disk stop).
  - The test landed 3 sends (15,000 lamports): budget-state.json says 0, final, and the owner sees no verdict.
- **Fix:**
  - Check `--out` before taking the lock.
  - Print the verdict and reasons before writing.
  - On the error path, zero the entry only when nothing was sent (carry a "sent" flag out of `revert_test_held`, or
    let it book its own spend on every path).

### 5. Should-fix (research note and plan, not code): as built, the route can carry almost nothing on today's live config, and step 4 cannot run as written
- **Where:**
  - `src/exec.rs:459-460`: the protected tip floor is `max([tips] floor, tip_lamports, the service minimum)`, and the
    cap is raised to it.
  - `:1399-1405`: the bar is `expected >= tip + 5,000 + margin`.
  - `:1380`: `band_throttle` runs before routing.
  - master's `deploy/arbx-ft-x4size-frz.toml:456`: `big_band_max_per_sec = 0`, from 9e6ba63.
  - `docs/research/senders-x11.md` §6 step 2.
- **The problem:**
  - Every protected tip is at least 1,000,000 lamports (BlockRazor's 100,000). So only decisions expecting at least
    about 1,005,001 lamports can route: band 3 and up, or band 2 up for BlockRazor.
  - Master's live config now refuses every band-3/4 decision before it reaches the route. `TokenBucket::new(0, _)`
    holds no token: send/budget.rs:40-43.
  - So only BlockRazor's band-2 decisions (100,000-1,000,000 edge) remain routable. The landing study puts bands 2-4 at
    40% of sends with 1 win.
  - The landing study: bands 3-4 made 1,291 sends for 0 wins. Band 0 (edge < 20,000) brings 95% of wins.
  - The note's step 4 says "band-0 decisions first". A band-0 decision can never carry a 1,000,000-lamport tip: it goes
    to Jito as `bar`.
  - Step 2 also says the value is "a second auction on **Harmonic** leaders". The route keys on leader *kind*, and
    Harmonic leaders are kind `jito`. So it cannot target them: `leader_kinds = ["jito"]` would move every Jito-client
    leader (JitoLabs included) off Jito.
  - wp24's `max_send_band` / `max_send_edge_lamports` (a 75,000-100,000 cut-off) would, once set, refuse the same
    decisions.
- **Failure scenario:** the owner obtains keys and runs revert tests and an A/B. The route then carries 0 decisions,
  or only the large-edge ones the study says almost never win.
- **Fix:**
  - Say this in the note and in PLAN-ADDENDUM WP-19 before keys are bought or requested.
  - Step 4 needs either services that take a tip below band 0's edge (ask Nozomi and others whether their minimum is
    per-key negotiable), or a route keyed on the leader's client (Harmonic) that adds a protected copy beside Jito's
    rather than replacing it.
  - Otherwise X11 has nothing to carry.

### 6. Note: the pin proves "this file, unchanged", and binds less than it could
- **Where:** `src/send/revert.rs:394-408`; `src/config.rs:2083-2097`.
- **The problem:**
  - Anyone who edits the config can pin a hand-written record. The tests do exactly this (config.rs
    `wp19_the_gate_reads_the_pinned_record`, tests/wp19_revert_cli.rs). "Re-derives the pass from the facts" only
    catches a record whose `verdict` contradicts its own facts.
  - The pin also does not bind:
    - the request format: the record's `protection.request` against this build's `protected::describe` (a later change
      to `protected::body`, e.g. losing `revertProtection: true`, keeps old pins valid);
    - the URL's path and non-secret query parameters (only the host is recorded, so `/fast` vs another path, or an
      added flag, pass);
    - the wallet;
    - the record's age.
- **Fix:**
  - Store the path and redacted query (parameter names, secret values elided) and a request-format version. Compare
    them, and the wallet, at the gate. Consider a maximum age.
  - Optionally re-check the record's signatures at the start (`getSignatureStatuses` with history: all absent).
  - A signature by a dedicated key would stop hand-written records.

### 7. Note: RPC poll errors do not stop the sends
- **Where:** `src/send/revert.rs:213-227` (`Err(_) => poll_errors += 1`).
- **The problem:** with the read RPC failing, all n sends go out while nothing on chain can be seen. "Stop at the
  first landing" silently becomes "send all 30". The budget still caps the cost, and the verdict is inconclusive.
- **Fix:** stop the test (inconclusive) after 2-3 consecutive failed polls.

### 8. Note: a service that refuses failing transactions at ingress can never pass
- **Where:** `src/send/revert.rs:229`, `:378`.
- **The problem:**
  - Lunar ("all transactions must pass simulation") and Helius Sender Max ("if any fails, the whole bundle is
    rejected") may answer every built-to-fail send with an error.
  - Three refusals end the test as inconclusive, which can never be pinned. These are #2 and #4 of the ranking.
- **Fix:** classify a refusal whose text cites simulation and our ERR_PROFIT (custom 0x4e580002) as "refused at
  ingress". Either give it its own verdict, or say in the note that this test cannot pin such services.

### 9. Note: revocation lasts one process, and each campaign segment turns the route back on
- **Where:** `src/exec.rs:2116-2126`. The alert text says "for the rest of the segment" (alerts.rs:464-467).
- **The problem:**
  - `revoked` lives in the executor. Every 60-minute segment is a new process, so a service whose protection failed
    can pay again in each segment.
  - Each payment is one or more fees, until the first failed landing is seen.
- **Fix:** persist the revocation in the campaign directory (or the runs directory), and have the gate refuse the
  route while it exists, until the owner clears it.

### 10. Note: routing comes after the leader-kind skip and the Jito-token check
- **Where:** `src/exec.rs:343-346` (`input_checks`), before `:1399`.
- **The problem:**
  - The live config's `skip_leader_kinds = ["other", "unknown"]` refuses `other` leaders before the route sees them, so
    a route listing `other` never fires there.
  - `jito_auth_stale` also stops protected sends, which need no Jito token.
  - Nothing warns about either.
- **Fix:**
  - Have the route's check refuse (or warn on) an overlap with `skip_leader_kinds`.
  - Exempt protected decisions from the token check.

### 11. Note: `arbx senders --only <protected path> --raw <tx>` sends through a protected path with no gate
- **Where:** `src/main.rs:1003-1060` (`--only` enables the named paths; `--raw` fires the file through all of them).
- **The problem:** it is a manual tool. The note says "never `--raw`", but the binary does not enforce it.
- **Fix:** refuse `--raw` when any selected path is a protected-bundle path.

### 12. Note: redirects are followed, so "https only" holds for the first hop only
- **Where:** `src/send/mod.rs:629-630`. The client has no `.redirect(Policy::none())`; reqwest follows up to 10. This
  is pre-existing for every path.
- **The problem:**
  - On a cross-host redirect, reqwest drops `authorization` but keeps `apikey` (BlockRazor) and `api_key` (Astralane).
  - A 307/308 re-POSTs the body (our signed transaction) to the new location, `http://` included.
- **Fix:** no redirects on protected paths: a 3xx is a refusal.

### 13. Note: a killed revert test is booked at 0
- **Where:** `src/budget.rs:89-93` (`refresh`), `:100-104` (`spend_of`).
- **The problem:**
  - An entry that is not final is re-read from the run directory's ledger, which a revert test never writes, so it
    reads 0.
  - The fees of a test killed mid-run (at most 150,000-300,000 lamports) are not counted.
- **Fix:** book `worst_fee_sent` as the entry's spend while the test runs, and lower it to the real figure at the end.

### 14. Note: 5791d92's campaign test now mirrors the config instead of pinning FT-012's "off"
- **Where:** `tests/campaign.rs:152-154`.
- **The problem:** the assertion now holds for either value, so an accidental re-enable of the pool refresh in the
  live config (while the CLMM venues send) would pass.
- **Fix:** assert `pool refresh (WP-22): off` and give the FT-012 reason. The wp21 test fix is right as it is.

### 15. Note: research method details (the conclusions hold)
- **"Trades" in §2.3 count directional rows.**
  - `analyze.py` defines trades as win + loss + hidden. The nine-signer numbers (418 of 432) were counted with
    directional rows included.
  - Round trips only: 383 of 395 on Harmonic (97.0%), 0 failed.
  - Dou1Rpra's 14 rows are all directional (no round trip); 3T6gxwpM has 17 directional of 55, b619EzHS 6 of 41.
  - Fix: state the definition, or drop Dou1Rpra from the nine.
- **The CU price is missing from the rows for 6 of the 9 signers.**
  - "No tip transfer, a CU price" is not what the rows show for LionX7R6, 9ZAPm4VS, 3T6gxwpM, b619EzHS, H4arxkST and
    Dou1Rpra. Their `cu_price_micro` is null and `priority_fee` is 0 on almost every untipped row.
  - Their `fee` is above 5,000 a signature (e.g. 15,001, 347,969). So a priority fee was paid, but the exec decoder did
    not extract it.
  - The inference still stands; the sentence should say "a priority fee (in `fee`)".

### 16. Note: small items
- `exec::Exec::protected_route()` is documented as status `exec.protected_route`, but only tests call it. The
  revocation reaches events.jsonl and the counters, not status.jsonl (exec.rs:2130).
- `#[allow(clippy::too_many_arguments)]` is doubled at exec.rs:1598-1599.
- `arbx check` exits 0 for a canary-enabled shadow config whose protected pin fails. It only prints "would refuse". A
  campaign pre-flight would pass, and every segment would then refuse.

## Likely conflicts with the concurrent lanes (list only)
- **lane/wp23 (f5e99d5)** conflicts textually in `src/build.rs`, `src/exec.rs` and `src/exec/tests.rs`:
  - `build::Plan`: WP-19's `cu_price` and WP-23's `ata2` both added, plus 2 test literals in build.rs.
  - `Exec::want`: WP-19's protected tip accounts against WP-23's `mid2` / `ata2` / `r.pools()` / `r.venues()`.
  - `Exec::build`: `cu_price` vs `ata2` in the `Plan` literal.
  - Keep both sides. Watch that `want` keeps `tips` from the protected route, and that every `Plan { .. }` literal
    gets both fields.
  - Semantics: `probe_routes` may return 3-leg routes after WP-23, so the revert test would send them. That is fine:
    the same min_profit revert.
- **lane/wp24 (c94f909)** conflicts textually in `src/config.rs`, `src/exec.rs` and `src/exec/tests.rs`:
  - `SendPolicyCfg`: fields, `Default`, and the `check` block; both lanes add skip-serialized fields.
  - The attempt line: WP-19's `send_route` vs WP-24's `takers` / `slot`.
  - Semantics: WP-24's band and edge cut-offs and its canary slot selection run before and around routing (see #5).
  - WP-24's tools/arbx-report changes do not touch the streams WP-19 bumps.
- **lane/wp25** has no commits beyond master (eda4c31) yet: no conflict now. Its plan (shreder feed, record-only)
  touches feeds, not the send path.
- **master eda4c31:** clean (`git merge-tree` exit 0). Master's changes since fd0ce85 are docs and deploy configs only,
  so the lane binary is the merged binary.

## Order
1. Before the first revert test: #1, #2, #3 and #4. All are local to protected.rs, revert.rs and main.rs, with unit
   tests on the existing fakes.
2. Before keys are requested, or an A/B is planned: settle #5 with the owner.
3. Before a route is enabled live: #9 and #10. #6 is advised.
4. The rest can follow.

## How this was checked
- **The diff:** `git diff fd0ce85..cbeb4db`, read whole. It does not touch the engine or the venues.
  - `Engine::probe_routes` / `refresh_route` / `route_accounts` predate it.
- **Binaries:**
  - master eda4c31 in `/home/moiz/arbx-offload/wp19-review/master` (detached worktree), with `CARGO_TARGET_DIR=targets/wp19-review`;
  - the lane at cbeb4db, `targets/wp19` (rebuilt 14:20).
  - Copies are in `wp19-review/check/arbx-{master,lane}`.
- **`arbx check` identity** (`wp19-review/check/run-check.sh`):
  - each binary on master's 12 deploy configs and on the lane's 13;
  - run with `env -i PATH=… HOME=wp19-review/fakehome`, from each repo root;
  - each output plus its exit code compared with `cmp`;
  - result: 24 of 24 identical; x11 is new, and master refuses it with "unknown variant `protected-bundle`".
  - The live config's line on master now reads "blockhash … at most 60 slots old … >=1M bands at 0/s". The author's
    fd0ce85 baseline predates that; it is the same on both binaries.
- **Tests on master eda4c31** (`targets/wp19-review`): both stale assertions fail, as 5791d92 says.
  - `cargo test --release --test campaign`: 4 passed, 1 failed, `the_x4size_config_passes_arbx_check_with_its_experiments`
    at tests/campaign.rs:152 ("FT-008's refresh kept").
  - The `wp21_shadow_config` test binary: 3 passed, 1 failed, `the_other_configs_keep_the_wp21_venues_off` at :81
    ("deploy/arbx-ft-x4size-frz.toml: venues (WP-21): Raydium CLMM send (traded) ...").
  - The test binary was run directly, because cargo stops at the first failing target.
- **Tests on the lane** (`cargo test --release`, cbeb4db, `targets/wp19`; log in `wp19-review/test-lane.log`):
  - 707 passed, 0 failed, 8 ignored: lib 661 (+7 ignored), main 16, and 30 integration tests (+1 ignored).
  - The 24 WP-19 tests are among them:
    - config: 3;
    - exec: 4;
    - send::protected: 4;
    - send::revert: 9 (the real seams on fakes included);
    - send: 2;
    - tests/wp19_revert_cli.rs: 2.
  - The two tests fixed in 5791d92 pass there.
- **arbx-report:** `python3 -m unittest discover -s .` on a `git archive` copy: 110 tests OK, 4 skipped.
  - `wp19-review/compat/compat.py`: the synthetic segment written twice (master shapes, WP-19 shapes), and
    `arbx-report segment --offline` on both. The only differences are the file inventory's schema, bytes and sha256
    (`compat/base.report.json` vs `compat/wp19.report.json`).
- **Research:** `wp19-review/research/recount.py`, `signers.py`, `signers2.py` and `other_kind.py`, run on
  `wp19/rows.jsonl.gz` and `wp19/slots.json`. Outputs are in `research/*.out*`.
- **Conflicts:** `git merge-tree --write-tree --name-only lane/wp19 <lane>`, with the conflict hunks read from the
  written trees.
- **Not done:**
  - no endpoint, RPC or Cherry contact;
  - no `senders --probe` or `revert-test` against real endpoints;
  - nothing signed or sent;
  - no .env, key, keystore or wallet file read; `arbx check` ran with an empty HOME and no .env present.

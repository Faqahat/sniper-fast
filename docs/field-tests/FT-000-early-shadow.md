# FT-000: early shadow run on the WP-04 build (before Stage 0 is complete)

- **Status:** running (started by Claude, 2026-10-05; the owner asked for testing to start without waiting)
- **Mode:** shadow. Nothing can be sent: this build has no executor in shadow (`exec_on` is false).
- **Budget:** 0 lamports.
- **Wallet:** none used.

## Purpose

Validate on live feeds, hours before the final Stage 0 build, everything already on master:
- WP-04: state consistency, commit groups, the state-health gate, forks, lookup-table retries, per-segment signer stats;
- WP-03b: chain fetch, boot retries, Haan rate limiting;
- WP-08 part 1: leaders, PoH, transfer classification;
- the I-11 standalone setup: arbx's own `.env` and data on Cherry; no arb-lab path.

Problems found here get fixed while WP-05/06/07 are built, not after.

## Pass/fail criteria (written before the run)

1. **Boots** with no fatal error. If boot RPC hits errors, the retries recover (I-1).
2. **The state stream is connected for ≥ 95% of the run:** `state_connected`, slot advancing, store updates growing. Haan alone: arb-lab is not running.
3. **No false outage handling:** if the stream drops, pricing stops (`state_unavailable` reasons), the account re-read happens after the reconnect, and no signer misses are counted while state is unhealthy.
4. **0 core or replay record drops** (status / manifest), and the recorder volume fits the disk (Cherry: 128 GB free).
5. **`decisions.jsonl` and `commits.jsonl` are populated.** No opportunity is priced on a prediction (`hint` records never change a decision).
6. **The chain-fetch service stays within the Haan rate limit:** 429s are counted and retried; no failure is fatal.
7. **Resources:** RSS stays < 8 GB and CPU < 3 of Cherry's 4 cores (resources.jsonl).
8. **Stop:** the segment ends at its deadline with a recorded stop reason.

## Setup

- **Build:** master `735901e` (code from 323e3bf; later commits are docs only), release, built in a clean worktree. `arbx --version` prints `arbx 0.1.0 (git 735901ee…, dirty false, release)`.
- **Upload (build artifacts only):** the debug-stripped binary `bin/arbx-735901e` (sha256 `0b6a78c6a91f0302…`, 16.4 MB), plus `deploy/ft000-shadow.toml` and 6 data files. Each was verified with `sha256sum -c` on Cherry.
- **Config:** `deploy/ft000-shadow.toml` is master's `deploy/arbx-stage0.toml` (sha256 `d48bda02e8d7f107…`) with two changes:
  - `wallet = "FRZh63L6…"`, the production wallet;
  - `wallet_keystore = ""`, so the owner's existing keystore (profile "trading") is used in place. Shadow mode never loads it.
- **Keys:** from arbx's own `/root/arbx/deploy/.env`, which `arbx check` loads.
- **Signer stats:** start empty. The cmp2-polluted file was moved aside to `runs/signer-stats.json.polluted-cmp2`.
- **Pre-flight:** `arbx check` exits 0 on Cherry: only jito-bundle enabled, shadow, the route program's hash checked at start, 21 crowded pools, geo table 872 ranges.

## Segments (chosen by Claude; the owner asked for segmented test runs)

| Segment | Length | Why |
|---|---|---|
| s1 | 30 min | Quick health check: boot, the state gate, the recorder, decisions. Stop if anything is fatal. |
| s2 | 60 min | Stability over an hour: memory growth, rotations, the lookup-table cache, Haan reconnects. Warm start from s1's lookup tables. |
| s3 | 60 min | Repeat for variance, and reconnect behaviour if Haan drops. |

- Each segment starts only after the previous process has fully exited, because Haan grants its streams to the first process (I-3).
- Each segment is analysed while the next one runs.
- Command per segment: `cd /root/arbx && (setsid nohup bin/arbx-735901e run --config deploy/ft000-shadow.toml --minutes N --name ft000-sK > runs/ft000-sK.out 2>&1 < /dev/null &)`

## Observed at s1 + 3.5 min

- **State:**
  - connected, `tier_a_complete`, 1,030 Tier-A pools;
  - last update 19 ms old, 0 reconnects, 1 re-snapshot (boot);
  - `unavailable_total` 1: the boot window. No send while the re-read was pending: "nothing is sent until it has".
- **Recorder:** 0 drops, 0 I/O errors, no dead writers. 199 MB in 3.5 min, about 3.4 GB/h compressed; `exec.jsonl` is the largest stream.
  - Multi-day canaries need old runs moved off Cherry; there are 137 GB free.
- **CPU:** about 0.5 core (user + sys) of 4; load 0.44.
- **RPC:** Haan carried 76% of first replies, getMultipleAccounts p50 0.7 ms, 0 errors.
- **Dead feeds**, as known (OD-6): constantk-prism (401), erpc (timeout), raiden, corvus and getblock (0 transactions). They only add log noise.

## Results: segment 1 (ft000-s1)

- **Run:** 01:09:15.8 UTC to 01:39:32.8 UTC on 2026-10-05 (meta.json `run.started_ns`, stop.json). Booted at +14.3 s, warm at +65.9 s, stop requested at +1,814.4 s.
- **Records:** `/root/arbx/runs/ft000-s1` (2.30 GB) on Cherry.
  - Copies were pulled read-only into the analyst's scratch (not in git): every stream except exec, journal and accounts; then accounts.bin (needed for re-pricing) and one exec file, `exec.055`, as a sample of that stream.
  - Report: `python3 tools/arbx-report segment <copy> --offline` (R0–R12).
- **Chain checks:** 288 read-only calls to the public RPC: 280 `getTransaction`, 7 `getSignatureStatuses` and 1 `getAccountInfo` (the PumpSwap GlobalConfig, for re-pricing).
- **Spend:** 0. Shadow mode: `exec` was null, the send gate was `mode_shadow`, and no attempt was made. BUDGET.md is unchanged.

### Criteria (written before the run)

| # | Verdict | Numbers (source) |
|---|---|---|
| 1 Boots | **PASS** | Booted in 14.3 s. Every boot RPC call succeeded: boot/haan 60/60, boot/shyft 39/39 (run.log role lines). There was no `rpc_boot_retry` event, so the I-1 retry path was not exercised. |
| 2 State connected ≥ 95% | **PASS** | `state.connected_now` was true in 180 of 180 status lines, with 0 reconnects. The newest message was at most 139 ms old (306 ms for an account update). The slot advanced in every line (453,426,778 → 453,433,450), and `store.updates_total` grew from 5,616 to 119,068. The state was unavailable once, at boot, for 248 ms (events.jsonl `state_available.down_ms`). Haan's three streams had 0 errors (feedhealth). |
| 3 No false outage handling | **PASS** (boot only) | The stream never dropped after boot, so the mid-run reconnect path was not tested. At boot the re-read followed the first connection and landed after 51.4 s (`state_resync_done`). While it ran, 8,178 routes (278 decisions) were refused `resync`, and the 11 opportunities priced then got verdict `resync`. `signer_miss_unknown` was 0. The misses counted afterwards are real: 200 of 200 sampled triggers that never produced a state update had failed on chain (`getSignatureStatuses`). |
| 4 No drops; volume fits the disk | **PASS** (volume: S1-5) | In manifest.json: `core_record_loss` false, `dropped_total` 0 in every stream, 0 I/O errors, 0 records lost at close. accounts.bin has 0 aseq holes. The run wrote 2.29 GB in 30 min (4.58 GB/h). That fits FT-000 (about 11.5 GB for 2.5 h) but not a 24 h run (S1-5). |
| 5 Decisions and commits populated; nothing priced on a prediction | **PASS** | decisions.jsonl has 29,061 lines (26,804 `commit`, 2,257 `timeout`); commits.jsonl has 29,550 groups. All 9,068 triggers are `hint_only` with `opp` null. Re-pricing the 1,146 opportunity decisions on the account versions in accounts.bin reproduces the engine's gross to the lamport on 20,576 of their 24,028 priced routes; the rest differ only in WP-16's known deviation classes (below). |
| 6 Chain fetch within Haan's limit | **PASS** (coverage: S1-1) | There were 0 rate-limited answers (429) and 0 errors of any class, on every role and provider (resources.jsonl `rpc`, run.log role lines). `service_ok_now` was true in all 180 lines, and no chain-fetch event fired. But the service was starved (S1-1). |
| 7 RSS < 8 GB, CPU < 3 cores | **PASS** (trend: S1-4) | RSS peaked at 936 MB. CPU was p50 0.36 cores and at most 0.56 (engine thread ≤ 0.14), with load ≤ 0.95 (resources.jsonl). |
| 8 Stops at the deadline | **PASS** | stop.json: `reason` deadline, exit 0, `final_status_seq` 179 (= the last status line). The end came 2.54 s after the request. |

### Opportunities: real; none is a maths artefact; most are taken before we could act

**Totals.** 1,146 opportunities quoting 8.03 SOL of expected net, from 1,062 triggers on 166 pool pairs and 48 mints (R12 merges them into 390 episodes). Verdicts: 1,135 `gate_shadow:mode_shadow` and 11 `resync`.

**Distributions** (opportunities.jsonl, decisions.jsonl):
- **Expected net, lamports:** p10 11,842, p25 49,188, p50 521,645, p75 3.19M, p90 16.2M, p99 92.6M; the largest is 1.309 SOL (opp 303).
- **Size:** p10 0.023, p50 0.51 and p90 4.11 SOL; 112 at the 4.2 SOL cap.
- **Band** (by edge), opportunities (SOL):

  | Band | Edge (lamports) | Opps | SOL |
  |---|---|---|---|
  | 0 | < 20k | 125 | 0.0006 |
  | 1 | 20k–100k | 231 | 0.009 |
  | 2 | 100k–1M | 313 | 0.12 |
  | 3 | 1M–10M | 316 | 1.08 |
  | 4 | ≥ 10M | 161 | 6.81 (85%) |
- **Venue pair:**

  | Pair | Opps | SOL |
  |---|---|---|
  | PumpSwap → DLMM | 587 | 4.04 |
  | DLMM → DLMM | 299 | 1.13 |
  | DLMM → PumpSwap | 108 | 1.24 |
  | DLMM → DAMM v2 | 50 | 1.56 |
  | DAMM v2 → PumpSwap | 42 | 0.004 |
  | DAMM v2 → DLMM | 16 | 0.007 |
  | DLMM → AMM v4 | 15 | 0.001 |
  | AMM v4 → DLMM | 11 | 0.013 |
  | DAMM v2 → DAMM v2 | 11 | 0.03 |
  | 3 others | 7 | 0.0015 |
- **Mint:**
  - `7Vertkg…pump`: 495 opportunities (2.95 SOL); 443 of them came at 01:23–01:26 UTC, 48% of all opportunities in 3 minutes;
  - `2AVjqmGb…`: 26 (1.54 SOL);
  - `C1mBfBoD…`: 31 (0.71);
  - `CbcyNo7m…`: 73 (0.70);
  - `EkFRff9a…`: 6 (0.57);
  - USDC: 208 (0.09).

**Pre-WP-16 maths: 0 artefacts.**
- **Method:**
  - I rebuilt the store at each opportunity decision from accounts.bin: for every account, the newest version received by the decision's `t_commit`, in the store's order.
  - I re-priced every priced route of those decisions (24,028) with lane/wp-16's `arbx-sizing` crate (the worktree as of 2026-10-05, F1/F2 fixes included), using a scratch harness.
- **Validation:** 20,576 routes match the engine's gross to the lamport, including every AMM v4, DAMM v2 → DAMM v2 and DLMM → AMM v4 route. So the reconstructed state is the state the engine priced.
- **Where the old maths differs** (exact minus old, as a share of the size):
  - routes with a PumpSwap buy leg (3,258): typically −0.6 ppm, −54 ppm at p1, −0.18% at most;
  - the other routes (194, mostly DLMM legs): from −0.09% to +0.025%.
  - None of these routes came near the 1.2% DLMM classes.
- **Result:**
  - Every opportunity stays profitable with the exact maths.
  - 3 of them (0.0004 SOL) lose their profit at the recorded size but keep it at another size.
  - 599 were overquoted by 0.012 SOL in all, and 11 were underquoted.
  - The exact total is 8.015 SOL instead of 8.027 (−0.15%).

**Phantom and poisoned (the cmp2 classes): 0 each.**
- **Phantom:** all 1,062 triggers landed, finalized, without error, in the recorded slot (`getSignatureStatuses`).
- **Poisoned:** no prediction is ever a priced state (criterion 5), and the priced state equals the recorded account versions.

**Real or not there.**
- **Takers:** opportunities.jsonl `taker` is the first transaction after the decision that touched both pools.
  - 900 opportunities had one within 2 s: 316 distinct transactions, all landed without error.
  - I fetched 280 of them, covering 844 of the 900 opportunities (99.9% of their quoted SOL).
  - A taker counts as a win when its signer gained SOL + WSOL and spent no other token.
- **Real: 796 opportunities (7.40 SOL, 92% of the quoted SOL)** were closed by a winning rival round trip.
  - These are 259 transactions by 67 signers: 7.47 SOL gross and 3.96 SOL net, after 2.9 SOL of fees (mostly GxDC9e7S's priority fees) and 0.6 SOL of tips.
  - Per winning transaction, rival gross divided by our quoted gross: p25 0.72, p50 1.00, p75 1.00.
- **Who won:**

  | Signer | Wins | Gross SOL | Net SOL | Note |
  |---|---|---|---|---|
  | GxDC9e7S | 17 | 3.97 | 1.40 | Includes opp 303 (quoted 1.309 SOL): taken 6.7 ms before our decision, in the same slot, for 1.32 SOL net. |
  | MriyaNN8 | 36 | 1.34 | 1.18 | 33 of the 36 before our decision. |
  | DtvmxrTA | 13 | 0.37 | | |
  | A9pQ1Qsv | 7 | 0.36 | | |
  | 7dGrdJRY | 10 | 0.30 | | |
  | 8oSD5a9E | 6 | 0.25 | | All before our decision. |
- **Not there or not taken: 350 opportunities (0.63 SOL).**
  - In 48 (0.042 SOL), the two-pool taker gained nothing.
  - 246 (0.58 SOL) had no two-pool taker within 2 s.
    - They are small (p50 39,929 lamports) and mostly DLMM → DLMM (189).
    - Their route was unprofitable again p50 50 ms after our decision, closed by other trades. 158 of the first transactions to touch either pool were not arbitrage-like (rivals.jsonl).
  - 56 (0.005 SOL) have a taker I did not fetch.
- **Speed:**
  - Winning takers were first seen p50 8.8 ms after our decision (p25 −8.4 ms, p75 +40 ms, p90 +116 ms).
  - Our decision came p50 14.7 ms after the trigger's first shred; 13.4 ms of that is the wait for Haan's state update (R5).

**The 20–80 ms band** (cmp2's table, docs/research/sol-trade-sdk-audit.md §4; the band edges are that document's assumption):

| Rival taker first seen | Opps | Quoted SOL | Taken by a winning rival | Distinct winning txs | Rival gross / net SOL |
|---|---|---|---|---|---|
| Before our decision | 339 | 4.70 | 300 | 105 | 6.51 / 3.55 |
| 0–20 ms after | 206 | 1.29 | 179 | 33 | 0.26 / 0.18 |
| **20–80 ms after** | **226** | **1.14** | **216** | **79** | **0.58 / 0.21** |
| ≥ 80 ms after | 129 | 0.32 | 101 | 42 | 0.11 / 0.016 |
| No two-pool taker within 2 s | 246 | 0.58 | – | – | – |

- **The 20–80 ms band:** 2.3 SOL/h quoted. Rivals realized 1.16 SOL/h gross and 0.43 SOL/h net.
- **Under WP-00's crowded-pool skip** (applied offline: an expected ≥ 100k on any of the 21 crowded pools removes 580 opportunities):
  - the band keeps 85 opportunities quoting 0.35 SOL (about 0.7 SOL/h), with 58 winning transactions grossing 0.33 SOL (0.12 SOL net);
  - the ≥ 80 ms band keeps 88 quoting 0.23 SOL, with 31 winning transactions grossing 0.09 SOL (0.007 SOL net).
- **Comparison with cmp2:**
  - cmp2's 20–80 ms band quoted 0.39 SOL per 28 min under the old policy, and 0.011 SOL under arbx's rules.
  - This segment's 0–20 ms and earlier bands (48% of the opportunities, 75% of the SOL) are out of any send lane's reach.
- **Caveat:** the taker is a heuristic (MEASUREMENT §4.33). A closer through only one pool is not seen.

### Accuracy monitor, commit groups, forks

**Accuracy monitor** (predictions.jsonl, status `accuracy`):

| Venue | Scored | Exact (pre-state) | Exact at the hint | Why not exact |
|---|---|---|---|---|
| PumpSwap | 1,884 | 770 (40.9%) | 38.1% | Sells: 730/730 exact. `buy_exact_quote_in`: 0/919 exact, off by at most 0.002 bps at p90; this is the old maths' deviation that WP-16 fixes. Exact-out buys: 40/235 (exact-in maths, WP-16 F6). |
| DLMM | 1,088 | 1,015 (93.3%) | 84.7% | Exact-in 96%, exact-out 82%. 142 more hints had an unknown pre-state. |
| DAMM v2 | 140 | 138 (98.6%) | 97.1% | 392 more hints not scored: 390 of them on one pool (`2owmkibn…`) that the old maths cannot quote (`pred_unquotable`). arbx-report R8 shows them as `pre_state_unknown` (S1-10). |
| AMM v4 | 649 | 645 (99.4%) | 91.1% | |
| CPMM | 123 | 122 (99.2%) | 98.4% | |

Other monitor counters: `pred_not_committed` 1,467, `pred_trigger_failed` 90, queue overflow 0.

**Commit groups** (status `commit`, commits.jsonl):

| Outcome | Groups | Share |
|---|---|---|
| complete | 24,769 | 83.8% |
| superseded | 3 | 0.01% |
| timeout_quiescent (W(T) unknown; 3 ms with no update) | 3,373 | 11.4% |
| timeout_unknown (W(T) known; members still missing after 5 ms) | 1,405 | 4.8% |
| fork_dropped | 0 | 0 |

- **Who supplied W(T):** shred 24,911, tx-stream 1,266, unknown 3,373.
- **Late members, `torn_suspect` and `fork_priced`:** 0 each.
- **Commit lag:** p50 13.4 ms, p90 20.4 ms, p99 36.4 ms. The lag SLO held in all 174 minutes (worst minute p90 27.0 ms).
- **All 1,405 `timeout_unknown` groups were resolved by the timer.** Their missing members never arrived (S1-8).

**Forks: 0 events, but the fork logic was barely exercised:**
- 0 slots abandoned, 0 dead and 0 refetches.
- With no probe.json on Cherry, `slot_statuses = "auto"` became "commitment" (run.log), so no dead or interslot status was received.
- Every one of the 6,709 confirmed slots had parent = slot − 1 (S1-7).

### Lookup tables, chain fetch, recorder, memory

**Lookup tables** (alts.jsonl, alts-final.jsonl, status `alts`):
- None preloaded: s1 is the first segment.
- 11,009 fetched, every one OK at the first try: 0 errors, 0 retries, 0 give-ups, 0 dropped waiters.
- 12,771 learned from the feeds.
- **Waits:** 21,993 transactions waited for a table. Fetch time p50 0.6 s, p90 4.0 s, max 5.5 s, because the requests queue in the RPC token buckets (6,090 of 6,735 engine calls to Haan were throttled).
- **Cache:** 19,143 tables at the end (4.9M addresses, 157 MB of keys), still growing by about 350 tables a minute.
- **RPC load:** the engine role made 11,063 of the run's 14,480 RPC calls (76%): the lookup-table fetches plus the 58 re-read chunks. Each fetch asks for one table (`rpc.accounts(&[table])`, engine.rs:1772), with up to 16 in flight.

**Chain fetch** (status `chainfetch`, `coverage`, txfetch.jsonl, slotidx.jsonl):
- **Haan 429s:** 0.
- **Starved:**
  - The backfill fetched 4 signatures in 30 minutes, against a measured need of p50 15.8/s (p90 22.3/s). Its cap was p50 0.03/s, and 27,431 signatures expired unfetched.
  - The slot index indexed 2,060 of 6,709 confirmed slots (30.7%) and dropped 1,645. It ran 3,005 slots behind from +16 min, and `slotidx_pct` was 0.
  - Exec coverage `watched_with_tx_pct` was p50 59% (p10 35%, p90 82%), all from the PumpSwap transaction stream.
  - These are the OD-1 numbers from the first WP-03b field run (S1-1).
- **Block positions disagree:** 288,592 of 394,225 `idx_check` comparisons (73%) disagree (S1-2).

**Recorder volume** (resources.jsonl `recorder_bytes_delta`; compressed):

| Stream | MB/h | Projected GB/day |
|---|---|---|
| exec | 2,585 | 62.0 |
| journal | 1,642 | 39.4 |
| decisions | 84 | 2.0 |
| txarr | 79 | 1.9 |
| rivals | 69 | 1.7 |
| accounts | 36 | 0.9 |
| commits | 34 | 0.8 |
| slotidx | 13 | 0.3 |
| All others | 38 | 0.9 |
| **Total** | **4,580** | **≈ 110** |

- **Disk:** Cherry's free space went from 137.2 to 134.9 GB during the run. 110 GB/day exhausts the 112 GB above `min_free_gb` (25 GB) in about a day.
- **Estimate vs measured:** MEASUREMENT §5 estimated 1.5–3 GB/h.

**Memory:**
- **Growth:** RSS was 387 MB at +70 s and 936 MB at the end. It grew by 32 MB/min in minutes 2–9, 14 MB/min in minutes 9–20 and 12 MB/min in the last 10 minutes, with no plateau yet.
- **Leak?** Not proven: part of the growth is the unbounded lookup-table cache (≈ 3 MB/min of keys). The chain-fetch maps level off at about 190k entries (S1-4).

### Feeds (R7, txarr: 1,621,238 forwarded signatures)

| Feed | Delivered | First | Behind the first, p50 / p90 |
|---|---|---|---|
| dz-leader | 46.5% | 45.3% | 0.7 / 3.5 ms |
| dz-retransmit-eu | 83.5% | 39.3% | 14.1 / 34.1 ms |
| astralane-deshred | 95.8% | 14.4% | 2.3 / 7.8 ms |
| haan-deshred | 95.8% | 1.0% | 8.7 / 13.1 ms |
| haan-grpc (executed, PumpSwap only) | 73.4% | 0.0% | 14.3 / 23.6 ms |

- **On the 1,062 opportunity triggers:**
  - first arrival: dz-leader 51%, dz-retransmit-eu 40%, astralane-deshred 9%, haan-deshred 0.7%;
  - dz-leader delivered only 546 of the 1,062, but was first on nearly all of those.
- **State stream:** provider lag p50 0.41 ms.
- **Drops:** 0 channel drops and 0 UDP drops on the live feeds.
- **Dead:**
  - raiden, corvus and getblock received 0 packets;
  - constantk-prism failed 183 times with `Unauthenticated: Missing or Invalid API Key`;
  - erpc failed 91 times with a TCP connect timeout to `shreds-fra6-1.erpc.global`.
- **PoH:** none of the 1,146 opportunities has a PoH position (S1-6).

### Abnormal (run.log, the .out file, events.jsonl)

- **The .out file** is run.log without timestamps (725 lines each).
- **The only WARNING:** the boot re-read had not landed 10 s after the connection (8 of 58 chunks). It took 51.4 s in all (S1-3). 1,070 accounts were not found (`read_missing`): PDAs that do not exist.
- **Log noise:** 276 of the 725 lines (38%) are the two dead entries feeds' reconnects (S1-11).
- **Events:** 14 in all: boot state, warm-up and leader refreshes. The 20-minute RTT refresh had 1 failed probe.
- **Signer stats:**
  - per segment, as designed: 1,307 signers, 4,557 ok and 4,121 failed (= `signer_miss` 3,283 + `signer_miss_tx` 838), in the run directory;
  - the shared `runs/signer-stats.json` is still absent: nothing was merged.
- **Wallet history:** the wallet backfill re-read the wallet's last 748 transactions (749 Shyft calls in minutes 1–4, slots back to 452,817,831) (S1-12).

### Issues found in segment 1

| # | Severity | Issue | Fix |
|---|---|---|---|
| S1-1 | High | Chain fetch starved, with no 429s: 4 backfill fetches, 27,431 expired, the slot index 3,005 slots behind with 30.7% of slots indexed, exec coverage p50 59%. Lookup-table fetches, one table per call, took 76% of the 8 req/s that Haan and Shyft share. The boot wallet history took another 749 calls. | WP-04: batch the queued lookup-table fetches (up to 100 per `getMultipleAccounts`), or give them their own budget. WP-03b: guarantee the slot index its 3.7 getBlock/s. Measure the providers' real limits before raising `max_rps` (the 4/s caps look conservative; inference). Owner: OD-1. |
| S1-2 | Medium | The block position from the stream (`idx`) disagrees with getBlock's order in 73% of comparisons, whole slots at a time: every comparison mismatched in 1,458 slots and none in 504. It follows the leader's client: slots of JitoLabs, AgaveBam (BAM), Firedancer, Frankendancer and Agave leaders mismatch; slots of gossip client ids 9 and 10 match. R4's block-order attribution depends on it. | WP-03b: establish which source is right (e.g. against getTransaction) and record both. WP-10. |
| S1-3 | Medium | The boot re-read took 51.4 s (about 1.1 chunks/s), so pricing was partial for the first 66 s of each segment (3.7% of 30 min). It queues behind lookup-table and wallet calls. | WP-04 / WP-03b: give it the boot's critical priority. Preload lookup tables (s2 does). |
| S1-4 | Medium | RSS grew from 387 MB to 936 MB in 29 min (12 MB/min at the end), with no plateau. The lookup-table cache is unbounded: 19,143 tables, about 350 more a minute. Linear growth would reach 8 GB in about 10 h (inference). | WP-04: bound the cache (LRU by `last_used_ns`). Check s2's slope first. |
| S1-5 | Medium | Recorder at 4.58 GB/h (110 GB/day; §5 estimated 1.5–3). exec.jsonl is 56% of it, and in `exec.055` 10,246 of 13,290 rows (72% of the bytes) are PumpSwap transactions that touch no watched account. A 24 h campaign (FT-005) would reach `min_free_gb`. | WP-03: record only stream transactions that touch a watched account, or sample the rest. That gives about 2.7 GB/h (est.). |
| S1-6 | Medium (measurement only) | No PoH timing: 0 of 1,146 opportunities have `poh.trigger`. The shred walks reached 64 ticks in 4 of 10,185 slots (ticks p50 4–7), and both entries feeds are dead. | WP-08 (shred-walk PoH); OD-6. |
| S1-7 | Low–Medium | Fork handling untested: without probe.json the stream used commitment statuses only, so dead slots are invisible. | Ops: run `arbx grpc-probe` on Cherry before s3 / FT-001. |
| S1-8 | Low | W(T) over-predicts: 1,405 groups waited the full 5 ms for members that never came. The missing members were bin arrays (952), mints (915), vaults (834) and pools (703). Inference: a writable account a swap leaves unchanged sends no update. 2,257 decisions (7.8%) are of kind `timeout`. | WP-04: build W(T) from the accounts the instruction writes; drop mints. |
| S1-9 | Low | Pre-WP-16 maths in the monitor: PumpSwap 40.9% exact, DLMM 93.3%, one DAMM v2 pool unquotable. It changed no opportunity's sign (−0.15% of the quoted SOL). | WP-16, and its F6 (exact-out). |
| S1-10 | Low | arbx-report R8 counts `exact: null` as `pre_state_unknown` even when `pre_state.known` is true (the 392 DAMM v2 hints are `pred_unquotable`). | WP-10. |
| S1-11 | Low | Dead feeds make 38% of run.log noise. | OD-6: drop them or fix their keys. |
| S1-12 | Low | Every segment start re-fetches the wallet's last 748 transactions (749 Shyft calls in 3 min). | WP-03b: fetch only what is newer than the last segment. |

**Verdict, segment 1:**
- All 8 criteria pass.
- **The opportunities are real.**
  - None comes from the pre-WP-16 maths.
  - None is phantom or poisoned.
  - Opportunities worth 92% of the quoted SOL were closed by winning rival round trips, whose gross matched our quote (p50 ratio 1.00).
- **But 75% of the quoted SOL** was taken before our decision or within 20 ms of it. Our decision itself waits p50 13.4 ms for Haan's state.
- **Before FT-001:** fix S1-1 and S1-3, and check S1-4's slope in s2. **Before FT-005 (24 h):** fix S1-4 and S1-5. Decide S1-2 before WP-10's R4 uses the block positions.

## Results: segments 2–3 and the overall verdict

(filled in when they end)

## Results: segment 2 (60 min, 01:39–02:40 UTC): PASS

- **Goal:** stability over an hour. Pass means no crash or hang, state connected ≥ 95%, 0 record drops, RSS < 8 GB, and decisions flowing all hour.
- **Stop:** `deadline` ("--minutes 60 reached"), exit 0, no unsettled attempts.
- **State:** connected in 360 of 360 status lines (100%), 0 reconnects, `unavailable_total` 1 (the boot window). The newest update was at most 152 ms old across the watcher's 77 checks.
- **Recorder:** 0 drops, 0 I/O errors, no dead writers.
- **Activity:** decisions rose in every one of 77 watcher intervals (810 → 56,907), with 1,976 opportunities in the hour.
- **Memory:** RSS rose from 60 MB to 1,121 MB with no plateau (about 18 MB/min), under the 8 GB criterion. This is the unbounded lookup-table cache issue from s1, being fixed on lane/ft000-fixes. It must be fixed before any 24 h run.

## gRPC probe between s2 and s3 (02:40–02:43 UTC, Haan alone)

| Subscription | Result |
|---|---|
| accounts_full (8,468 accounts) | accepted, first message after 51 ms |
| slots_interslot | accepted: slot statuses including dead and fork statuses are available |
| blocks_meta | accepted |
| tx_filter_1 | accepted |
| tx_filter_2, tx_filter_5 | **refused by the plan**: `ResourceExhausted: TX_INCLUDE exceeded: 2/1` and `5/1` |
| blocks_account_include | **refused by the plan**: `BLOCK_GROUPS exceeded: 1/0` |
| deshred_5 | accepted on Astralane (first after 9 ms) and on Haan (131 ms) |

- **For OD-1:** the Haan token allows ONE transaction filter and no block subscriptions. Executed-transaction coverage across the five venues therefore needs a bigger Haan plan or a second provider; RPC backfill is limited to about 4 req/s.
- **Probe bug:** `ResourceExhausted … exceeded n/m` is a definite plan refusal, but the probe labelled it inconclusive (exit 3) and did not write probe.json. It is fixed on the FT-000 fixes lane (classify it as `refused_plan_limit`).
- **For s3:** the probe is re-run with `--only` on the accepted subscriptions, so probe.json exists and s3 runs with `slot_statuses = all`, testing fork handling.

## s3 setup: pool refresh (owner request: "for next segment, refresh the pools") and probe re-run

- **Discovery:** `bin/pooldisco-cb88257`, the compiled tools/pooldisco (binary only on Cherry, sha256 `8f3b4074f9ad5008…`).
  - Ran 02:43–03:13 UTC with arbx stopped (Haan grants its streams to one process).
  - Saw 4,873 pools, 746 tokens with 2+ pools, 2,385 arbitrages and 477 gap openings; ranked 592 candidates, 577 in tradeable venues.
  - My orchestration script reported an early stop. That was a false alarm from a failed ssh check; the run completed.
- **New seed list:** `data/seed-pools-ft000s3.csv`, 1,500 pools, built by a local script with read-only public RPC to check every pool still exists:
  - **Kept (1,147):** 548 pools active in s1+s2 (86,655 decisions, 3,131 opportunities read with arbx-report's readers) first, then idle pools that still exist.
  - **New (353):** pooldisco pools in complete token groups (≥ 2 tradeable pools per mint), ranked by opportunity SOL/h and few competitors.
  - **Dropped (248):** w4 pools with zero activity in 1.5 h, cut to the 1,500 cap. No pool was closed on chain.

  | Venue | Kept | New |
  |---|---|---|
  | DAMM v2 | 482 | 113 |
  | DLMM | 371 | 165 |
  | PumpSwap | 227 | 40 |
  | Raydium CPMM | 40 | 20 |
  | Raydium AMM v4 | 27 | 15 |
- **Probe re-run** (03:3x UTC, `--only accounts_full,slots_interslot,blocks_meta,tx_filter_1,deshred_5`): all accepted, and `runs/probe.json` was written. s3 runs with `slot_statuses = all` and block meta on, so fork handling is exercised for the first time.
- **Config:** `deploy/ft000-s3.toml` is ft000-shadow.toml with `seed_csv` pointing at the new list. Same binary `arbx-735901e`. `arbx check` exits 0.
- **s3 goal:** refreshed pools with fork statuses on.
  - No crash or hang, state connected ≥ 95%, 0 dropped records.
  - Coverage up: more pools priced, opportunities/h ≥ s2's 1,976.
  - Fork events recorded and handled: no pricing on abandoned forks.
- **s3 started** 03:41:00 UTC (60 min) under the live watcher.

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

## Results

(filled in when it ends)

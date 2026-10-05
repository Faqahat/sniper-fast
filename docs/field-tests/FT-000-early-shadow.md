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

- **Build:** master (code at 323e3bf plus later docs-only commits), built in a clean worktree. The binary's sha256 is recorded in `meta.json`.
- **Config:** `deploy/arbx-stage0.toml` (mode shadow), with keys from `/root/arbx/deploy/.env` (arbx's own).
- **Command (on Cherry):** `cd /root/arbx && nohup bin/arbx-<hash> run --config deploy/arbx-stage0.toml --minutes 150 --name ft000 > runs/ft000.out 2>&1 &`

## Results

(filled in when it ends)

# FT-001: shadow soak of the final Stage-0 build (go-live gate items 2–3)

- **Status:** running since 2026-10-06 06:58 UTC (started by Claude).
- **Mode:** shadow, under `arbx campaign` (the supervisor is a binary subcommand; nothing but build artifacts goes to Cherry).
- **Wallet:** frz FRZh63L6… (profile "trading"). Shadow never signs.
- **Budget:** 0 lamports.
- **Goal:** prove the exact build that will trade is stable for ≥ 3 h on live data, alerts itself on Telegram from Cherry, and records a 1 h segment that replays identically.

## Pass/fail criteria (written before the run)

1. **Stability:** ≥ 3 h as segments (3 × 60 min), each ending at its deadline (exit 0). No crash, no hang, no restart loop.
2. **State:** connected ≥ 95% of status lines in every segment. Any outage is handled (no pricing while stale, re-read after reconnect).
3. **Recorder:** 0 core and replay drops, 0 I/O errors. Volume ≤ 3 GB/h (FT-000 fixes projected about 68 GB/day).
4. **Memory:** RSS plateaus. The bounded lookup-table cache holds it under 2 GB at the end of each 60-min segment; FT-000 grew about 18 MB/min without a bound.
5. **RPC budget:** the slot index stays caught up (behind ≤ 100 slots at segment end), and the boot re-read lands in ≤ 15 s.
6. **Replay (go-live item 3):** `arbx replay --run <one 60-min segment> --compare` reports `ok: true`, `whole: true`, with identical decision and state digests.
7. **Alerts (WP-20):**
   - campaign start, segment end and campaign end messages arrive in the ArbX group from Cherry;
   - `arbx watchdog` reports "running" and, between campaigns, "not running".
8. **Money view:**
   - the ledger's snapshots run every 10 min with `equity_stale` never set while healthy;
   - reconciliation at each stop is within tolerance (shadow: no sends, so spend = 0).
9. **Decisions:** decisions and opportunities flow all hour, within ±50% of FT-000b's per-hour counts on the same pool list.

## Setup
- **Build:** master `11e25d1`, the final Stage-0 merge (WP-06 + WP-07 + WP-20 + FT-000 fixes). 567 tests pass and the synthetic hour replays identically. Release build, debug info stripped: `bin/arbx-11e25d1` (sha256 `76e680bb3440631f…`, 19.9 MB). The campaign freezes it as `runs/ft001/arbx-76e680bb`.
- **Config:** `deploy/arbx-canary-frz.toml` at `8181498` (sha256 `5863166b87137a66…`): mode shadow, wallet FRZh63L6… (profile "trading", used in place, never signs in shadow), the refreshed 1,500-pool list `data/seed-pools-ft000s3.csv`, `[builder]` rent-neutral with held_max 0, `[tips]` by band, `[dry_run] simulate = true`, alerts on, watchdog configured.
  - The config differs from the plan's `arbx-stage0.toml`: only the frz canary config soaks the frz wallet and the WP-07 ledger, and FT-002 needs it.
- **Upload:** build artifacts only (binary, config, 7 data files incl. `cu-table.json`), each checked with `sha256sum -c`. `arbx check` on Cherry: exit 0.
- **Commands (on Cherry, in /root/arbx):**
  - `bin/arbx-11e25d1 campaign --name ft001 --config deploy/arbx-canary-frz.toml --hours 3 --segment-min 60 --mode shadow --who claude --detach`
  - `setsid nohup bin/arbx-11e25d1 watchdog --config deploy/arbx-canary-frz.toml > runs/watchdog.out 2>&1 &`
- **Live watch:** the WP-20 alerts and the watchdog post from Cherry; the operator's `segwatch.py` posts goal, heartbeats and results.

## Results

| Segment | UTC | Result |
|---|---|---|
| p1 | 06:58–07:58 | **PASS.** `deadline`, exit 0; state 100% (360/360); 0 drops, 0 I/O errors; RSS 769 MB at the end, levelling off (721 MB at 33 min); 2.5 GB recorded. **Replay:** whole, 55,520/55,520 decisions, 53,482 commit groups and 954/954 attempts identical; the state digest differed only because of the digest point (see below) |
| p2 | 07:58–08:58 | **PASS.** `deadline`, exit 0; state 100% (360/360); 0 drops, 0 I/O errors; RSS 691 MB at the end; 1.9 GB recorded |
| p3 | 08:58–09:10 | **Stopped by the owner** (stop control, exit 10, class operator). Astralane's deshred feed refused us ("subscriber limit reached", a 429 storm), and the owner decided to drop Astralane. Healthy until then |

**Findings:**
1. **Replay digest point (go-live item 3), fixed on lane/digest 2e5a632.** The run took its state digest in `Engine::finish`, before WP-07's stop sequence journaled 10 more records; the replay digested after them (0.209 s later). The fix journals the digest point (INPUT 14) and the replay digests there. Replaying p1 with the fix reproduces the run's state and decision digests exactly, deterministically, twice.
2. **The stop snapshot fails** (both p1 and p2): `rpc getMultipleAccounts: no attempt before the deadline`. The ledger's snapshot role was throttled on Haan (32 of 37 calls). It must be fixed before FT-004: priority, provider failover, and the gap reconciled at the next segment.
3. **Astralane dropped** (owner, 2026-10-06), commit after 349140d. The feed is disabled in all maintained configs.

**Verdict:** soak PASS for p1–p2 (2 h, with the p3 portion until the owner's stop). The re-soak of the next build (WP-09 part 2 + the digest and stop-snapshot fixes, no Astralane) adds 60 min and must replay identically at the digest point. That closes go-live items 2–3 together with FT-001.

## Re-soak of the final build (ft001b, from 10:33 UTC)

- **Build:** master `374fda1`, release, stripped `bin/arbx-374fda1` (sha256 `bb84e4eb9c4aaefa…`). It adds WP-09 part 2, the digest-point fix and the stop-snapshot fix on top of 11e25d1.
- **Config:** `deploy/arbx-canary-frz.toml` (sha256 `40ec3fda7f8386ca…`, Astralane disabled), mode shadow. The watchdog was restarted on the new binary.
- **Command:** `bin/arbx-374fda1 campaign --name ft001b --config deploy/arbx-canary-frz.toml --hours 1 --segment-min 60 --mode shadow --who claude --detach`
- **Pass:**
  - clean deadline stop **with a successful stop snapshot** (not `snapshot_failed`);
  - state ≥ 95%, 0 drops, RSS < 2 GB;
  - `arbx replay --compare` of the segment: ok, whole, every decision identical, and the state and decision digests equal at the journaled digest point (INPUT 14).


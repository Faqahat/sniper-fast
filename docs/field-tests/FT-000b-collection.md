# FT-000b: shadow data collection on the refreshed pools (build 735901e), until the final Stage 0 build is ready

- **Status:** running (started by Claude, 2026-10-05 ~04:45 UTC)
- **Mode:** shadow; nothing can be sent.
- **Budget:** 0 lamports.
- **Build and config:** `bin/arbx-735901e` with `deploy/ft000-s3.toml` (the 1,500-pool refreshed list, fork statuses on). Both are unchanged from FT-000 s3.
- **Goal:** collect live records on the refreshed pools for the Stage 1 offline analyses, and keep checking stability over many hours.
  - The analyses: the X1 census of capturable value by pool class; X3 smaller sizes; the 20–80 ms band; and rival behaviour (STAGE1-PLAN).
- **Pass/fail per segment (written before the runs):**
  - no crash or hang;
  - state connected ≥ 95%;
  - 0 record drops;
  - decisions flowing every interval;
  - RSS < 8 GB (memory grows about 18 MB/min on this build, so 60-min segments stay near 1.2 GB).
- **Segments:** c1, c2, … of 60 min, back to back. Each starts only after the previous process exits (I-3), runs under the live watcher (Telegram heartbeats and alerts), and posts its goal at start and its result at the end.
- **Stopping:** when the final Stage 0 build is ready for FT-001, the next segment is not started, Cherry switches builds, and this entry gets a summary.
- **Disk:** about 4.5 GB per segment; Cherry had 128 GB free.

## Segment log
| Segment | UTC | Result |
|---|---|---|
| c1 | 04:46–05:43 | PASS: `deadline` stop, exit 0; state connected, 0 drops at the end. The operator's network was down about 05:25–06:10, so the live checks lapsed; the segment was unaffected |
| c2 | 06:11–07:11 | PASS: `deadline`, exit 0 |
| c3 | 09:42–10:43 | PASS: `deadline`, exit 0. The operator's machine was out of memory about 10:00–11:26, so the watcher lapsed; the segment was unaffected |
| c4 | 11:27–12:28 | PASS: `deadline`, exit 0. Watcher lapse during the operator-side outage about 12:20–13:05 |
| c5 | 13:10–14:10 | PASS: `deadline`, exit 0. At 59 min: 2.94M txs, 73,272 decisions, 1,621 opportunities, state connected |
| c6 | 14:10–15:10 | PASS: `deadline`, exit 0. Last segment before the usage pause; no new segments started |

**Note (2026-10-05):** the operator-side "network outages" were in fact the dev machine running out of memory. /tmp is RAM, and it held build target dirs while four parallel builds ran, so the OOM killer took down processes, DNS among them. Since then there is one build at a time (a global flock) and the target dirs are on disk. Cherry and the segments were never affected.

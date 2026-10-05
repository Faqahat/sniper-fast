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

# sniper-fast

Solana pump.fun **dip engine**. It pre-signs buys and fires them into large holder dumps ("pre-send"), holds for a short timer
(about 2 s / 6 slots, TP/SL ±20%) and sells. The live engine runs on the AMS edge server; this repo is the source of truth.
All development happens on the host (`rewind`); servers only receive built binaries, configs and scripts.

## Versions

| Ref | What |
|---|---|
| `sniper/main` (default) | Current engine = **dip42** (the live `snipe_engine_dip42`) + housekeeping commits |
| `sniper/dip35` … `sniper/dip37` | Original branches pushed before the 11-09 drive loss (dip37b = last pushed build, 11-05) |
| tags `dip38` … `dip42` | Engine builds after dip37b. Their local git history was lost in the drive loss; they were rebuilt from the restored copies and grafted onto `sniper/dip37` (the dip38 commit also carries the 11-05..11-09 ops changes and the 11-10 path rewrite) |
| branches `agent/*` | Snapshots of Claude agent worktrees, kept for reference |
| `dip42`, `snipers` (branches) | Old 11-03 branches from before the loss; despite the name, branch `dip42` is NOT the dip42 build (use the tag) |

**Every new engine build gets a tag and is pushed:** `scripts/release_dip.sh dip43 "what changed"` (see below).

## Layout

| Path | What |
|---|---|
| `src/` | The engine. Main binary `snipe_engine` (`src/bin/snipe_engine.rs` + `src/bin/snipe_engine/`), plus `snipe_fire`, `snipe_shadow`, `feed_race`, `quiet_book`, `obs_soak`, `apex_probe` |
| `program/` | On-chain program and venue test harness |
| `tests/`, `testdata/` | Tests and fixtures (fixtures lost in the 11-09 backup were restored from dip37b). Only `apex_probe`'s two sample `.jsonl` files are gone, so `cargo check --all-targets` fails on that one old probe binary; the engine and its tests check clean |
| `ops/` | Server-side scripts, launchers, configs and research notes (same relative paths as `/root` on the servers). Key folders: `ops/prod/` (launchers `run_dip_prod.sh.*`, edge configs), `ops/dip/` (dip reports, speed studies), `ops/strategies/presend/` (filters, FP-NOBOT preload `flatperfect/fp_preload.py`, briefs `prevent/forward/`), `ops/collect/` (tape recorder and backfill) |
| `deploy/` | Deploy configs (secrets live in `deploy/.env` on each server, never committed) |
| `config/` | Old engine/feed/probe configs. `probe.toml`, `probe_shadow.toml`, `probe_tpu.toml` stay at the root because `src/` refers to them |
| `data/` | Static data (registries, tip accounts, leader lists, reputation files) |
| `docs/` | Specs, plans, reviews |
| `scripts/old/` | Old root-level run scripts from the arbx / early-sniper era (unused) |
| `sketch/`, `tools/` | Prototypes and helper tools |

Outside the repo, on the host: run logs and briefs in `~/sniper-data/runs/ams_rNN/`, study data in `~/sniper-data/overnight`,
research folders in `~/sniper-studies/`, tapes in `/data/tapes/collect/`, handoff notes in `~/sniper-handoff/`.

## Build and deploy

```bash
cargo build --release --bin snipe_engine
```

Copy the binary to the server as a **new name** (for example `/root/sniper-dip/snipe_engine_dip43`); never overwrite a running
binary, launcher or config. Launchers are copied per run (`ops/prod/run_dip_prod.sh.dipNNrMM` with `dip_edge_ams_rMM.toml`).

## Running (owner rules)

- The owner starts and stops live runs; the engine asks for the keystore passphrase at a hidden prompt.
- Every run command includes `--profit-lock 1.0,0.30`. The kill switch is the start balance minus 0.5 SOL.
- Rebuild the FP-NOBOT preload on the host within 30 minutes of each start (`ops/strategies/presend/flatperfect/fp_preload.py`).
- `/root/dip/ledger_control.json` on the server overrides filter modes from the command line; check it before starting.
- Dry runs happen on the server and only after asking.

## Secrets

Never commit secrets. `.env*`, `*.enc`, `target/` and `__pycache__/` are ignored. Keystores, lane keys, RPC URLs and
Telegram tokens live only on the servers (`/root/sniper/deploy/.env`) and in `~/.config/sniper/` on the host.

## Releasing a dip build

```bash
scripts/release_dip.sh dip43 "short description of the change"
```

This commits any pending changes, creates the annotated tag `dip43`, and pushes `sniper/main` plus all tags to `origin`. A
`post-commit` hook on the host also pushes every commit in the background (log: `.git/push.log`).

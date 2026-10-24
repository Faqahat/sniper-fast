# Sniper (pump.fun race sniper) — development lives HERE (the host)

Remote servers are disposable and replicable: they only receive built binaries + configs + scripts, never edits.

- `src/`, `Cargo.toml` — the engine (`snipe_engine` = `src/bin/snipe_engine.rs`). Branch `sniper/main`; the stage
  commits on top of `56544e1` (arbx-fast) are the server copies imported 2026-10-19 (arbx-fast -> det -> race -> merge
  -> lat -> feed -> final -> final2). HEAD = arbx-final2, the engine of live tests 2 and the new-server run.
- `ops/` — server-side scripts, configs, notes from /root on the server (same relative paths as under /root):
  `ops/lat/` live scripts + guard, `ops/fix2/` landing config + notes, `ops/race/`, `ops/comp/` competitor research,
  `ops/indep/common.py` chain helpers, etc. Tokens are read from `deploy/.env` (never committed).
- Build: `cargo build --release --bin snipe_engine` here; deploy the binary to `<server>:/root/<engine-dir>/target/release/`.
- Current server: `ssh -p 1996 it@84.32.100.36` (sudo; files under /root). Secrets on the server only:
  /root/sniper/deploy/.env, /root/.nexus-v2-trading-wallet.{enc,pass}, /root/.config/doublezero/id.json,
  /root/.harmonic-searcher-auth.json, /root/.nexus-v2-jito-auth.json, /root/.flowra-searcher.json.
- `ops/overnight/` — 2026-10-23 strategy study (read-only research): replay engine `core/rp.py` (validated, `core/val_*.py`),
  strategy S4 = copied deployer list + 1% price guard + ~1 s sell (`report/S4_STRATEGY.html`), host dry-run loop
  `dryrun/` (frozen rules `frozen.json`), landing-path study `landing/LANDING_PATHS.md`. Proposed engine flags for S4:
  `ops/s4/s4_flags.sh` (`--deployer-list` gate added to the engine, not deployed).

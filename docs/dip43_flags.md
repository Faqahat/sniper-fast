# dip43 flags and keys

## Builder C: snipe-guard (C2; `src/bin/snipe_engine/ps43_guard.rs`; every flag needs `--presend-live`; all OFF by default)

| Flag | Values | Default | What it does |
|---|---|---|---|
| `--presend-live-guard` | `off` \| `deadline` \| `holders` | `off` | `off` = dip42: every try carries the Lighthouse slot deadline, byte for byte. `deadline` = the snipe-guard program replaces Lighthouse at index 2 with the same slot deadline only. `holders` = deadline + holder floors (onchain G-A). Every other guard flag is refused with `off`. |
| `--presend-live-guard-program` | base58 pubkey | none (required unless off) | the deployed program id (never hardcoded; ops/guard/DEPLOY.md prints it). Checked at start by simulation (fail closed). |
| `--presend-live-guard-holders` | `N:THETA:MAXLEAVERS:MINPCT` | `6:0.9:1:1.0` | holders mode only: the top N (1..10) holders by TRUE balance at signing, ours excluded, >= MINPCT % of supply; floor = THETA x balance (whole tokens); the try aborts when MORE THAN MAXLEAVERS are below (1 = abort at 2 or more). MAXLEAVERS < N. |
| `--presend-live-guard-max-age-ms` | 1..600000 | `2000` | holders mode only: a true-balance snapshot missing or older than this at signing signs the deadline only (`guard.reason` `no_snapshot` / `stale`); never a wait. |
| `--presend-live-guard-ab` | `on` \| `off` | `off` | landing A/B by window-id parity: odd windows snipe-guard, even windows Lighthouse (dip42's try). |
| `--presend-live-guard-allowlist` | base58 PDA | none | for a wallet NOT compiled into the program (AMS/FRA/FRZ are): the allowlist PDA, carried as the guard's last account (+32 bytes). Refused to start without it for such a wallet; ignored (with a line) for a compiled one. |

No hot control key: the guard changes the signed transaction and needs the start-up simulation; it is switched by restart only.
Banner: one line `GUARD (dip43 snipe-guard) …` (mode + settings; `off …` without the flag) after the `DIP PRESEND LIVE` line;
start check line `GUARD verified on chain (simulated): …`.

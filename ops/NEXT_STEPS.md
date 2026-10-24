# Next steps (2026-10-23, updated 14:19 PKT; every step needs the owner's OK)

Summary page: `ops/overnight/report/DECISION.html`. Dip plan: `ops/dip/PLAN.md` (top block). Engine spec: `ops/dip/ENGINE_V1.md`. Status: `ops/overnight/STRATEGIES.md`.

## 0. Decide
- **The candidate is dip-backrun, direct-sell version.**
  - Buy 0.5 SOL right after a ≥1 SOL pump.fun sell on a launch aged 1–120 s, when the model ranks it in its top 3–5%: direct sells from shreds, routed ones from the executed feed (the first forward hours favour routed). 2% price guard; sell 2–4 slots later.
  - At a REAL 35 ms reaction ≈ 8–12 SOL/day (two ways of modelling how the fast bots react to us); at a real 50 ms ≈ 2–8.5; at our ~75 ms today ≈ 0–5. The first forward hours are midday, at the same half rate as yesterday's midday.
- **It is a pro niche:** 53 pro wallets make ≈ +190 SOL net per ~33 h this way, 79% profitable, and the winners repeat.
- **The profit comes from other bots buying right after us** (the ~540 consistently profitable bots). Is that OK under "become them, don't beat them"?

## 1. Speed probe (≤0.25 SOL; buys that fail by design, base + priority fee only)
On the host:

    scp -P 1996 ops/final2/probe_speed.sh ops/final2/probe_to_pnl.py ops/run1/probe_buy.sh it@84.32.100.36:/tmp/

On the server:

    sudo cp /tmp/probe_speed.sh /tmp/probe_to_pnl.py /tmp/probe_buy.sh /root/run1/
    # stop the 24 h paper engine first (probe_buy.sh refuses while any snipe_engine runs)
    # top up the FRZ (DEV) wallet with ~0.3 SOL
    sudo bash /root/run1/probe_speed.sh            # 4 single-route phases + today's multi-route, ≤0.05 SOL each
    python3 /root/run1/probe_report.py /root/run1/ps_*.jsonl
    python3 /root/run1/probe_to_pnl.py /root/run1/ps_*.jsonl   # expected dip SOL/day per route (base and direct-only versions)

**Go** if a single route lands at a median ≤35–45 ms.

## 2. Executed-feed check (zero cost, subscribe only; server run)
- The dip engine's trade history needs an executed transaction stream. Kaldera (Constant-K, our deshred feed today) offers one per its vendor page, so it is probably already paid for.
- Config: `ops/gap/feed_race_exec.toml`; its header has the commands (scp, `CFG=... feed_race.sh 20 exec1`, `race_report.py`).
- Up to ~100 ms late is fine; 1 s is not.

## 3. If fast: build the dip engine
- Shadow mode first, about a day of work (spec `ops/dip/ENGINE_V1.md`):
  - triggers = direct pump sells from shreds (min-out check) plus routed sells from the executed feed, all with the 2% guard;
  - history = executed feed;
  - models `dip/frozen_dip2r_L35/L50.json`.
- Shadow-run on the server (no sends): measure our real trigger→decision times, the false-trigger rate, and feature drift.
- Then a small live test: one landing service per leader client, like HkQ7hMjy (`ops/final2/SEND_DESIGN.md`; HkQ7hMjy suggests `bam=nozomi`, `fd=nozomi`).
- FINAL-2 (snipes) is overnight-only at best; dip is the main edge.

## 4. Keep the data flowing
- The 24 h collector (`/root/sniper-collect`, run_20261022_1543) ends at **20:43 PKT today**. Restart it to keep the forward tests and fresh training data.
- Retrain the dip models daily: `bash ops/overnight/dip/dip_retrain.sh` (host).
  - It rebuilds with spacing 5 and freezes `dip2r` models.
  - Optional: decode the new picks' follower limits first (read-only RPC, see the script).

## Running on the host (read-only analysis)
- `ops/overnight/dryrun/fwd_loop.sh`: FINAL-2 forward test, hourly.
- `ops/overnight/dryrun/fwd_gdm_loop.sh`: GDM forward test, hourly.
- `ops/overnight/dip/fwd_dip_loop7.sh`: dip forward tests (DIP 8-slot, DIP4, DIP4 spacing 5, DIP2 incl. L75), about every 45 min → `dip/fwd_dip.log`.
- `ops/overnight/dip/fwd_dip_direct_loop2.sh`: direct vs routed forward test of the DIP2 and DIP2R models, decoding the picks' follower limits first (read-only RPC), every ~45 min → `dip/fwd_dip_direct.log`.

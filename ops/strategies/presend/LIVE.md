# Pre-send LIVE probe + sell fan-out (engine dip13) — 10-25 ~08:30 PKT

Owner GO 10-25 ~07:05 PKT ("ok lets do the real test"). Sell fan-out: owner OK ~08:05 PKT ("do that Helius SWQoS thing too").
Built and tested on this machine only. Nothing deployed, no server touched, nothing sent (simulation only), nothing committed.
MEASURED = a test, a simulation or a build. INFERRED = my reading.

## Bottom line
- **Binary (not deployed):** `/home/moiz/sniper-data/strategies/presend/bin/snipe_engine_dip13_presend_live`
  - 81,378,688 bytes, sha256 `500c5f8d573ac3aa94a2a02b0e213f8941efa24d35aca1b8a018a85733e14723`.
  - = dip12 (M2, nonce fan-out, pre-send shadow) + `--presend-live` + `--sell-fanout`.
  - Without the new flags it behaves as dip12: every change is additive or behind a new flag (MEASURED: all old tests pass).
- **On-chain simulation (MEASURED):** 11 live pump tokens, 0.2 and 0.55 SOL, as our FRA wallet; sigVerify off, nothing sent.
  - Price above the limit: 6042 in 22 of 22. Below it: filled in 22 of 22.
  - A limit 0.05% either side of the price: the right result in 44 of 44 (the min-out math is exact).
  - ATA already there: fails at the create in 22 of 22, and 11 of 11 as real holders.
  - Deadline passed: fails at the Lighthouse guard in 22 of 22.
- **CU (MEASURED):** a filled attempt 70.6k–88.6k, a 6042 one 54k–72k, a deadline failure 844.
  - Default limit **120,000** (the study's 60k is too low).
  - A failed attempt costs **5,120 lamports** (5,000 + 120k × 1,000 µL/CU).
- **Server config:** add ONE `[[send]]` block, `helius-ps` (a copy of helius-swqos with `max_per_sec = 10`). The sell
  fan-out needs nothing new.
- **Proposed probe:** 0.2 SOL, max 20 fills, fee budget 0.03 SOL, 90 min, routes `default=helius-ps`, k 4. Command below.
- **Main limit (INFERRED):** Helius allows 50/s per region. With helius-ps at 10/s, one armed window gets ~2 attempts per
  slot (not 4); two windows ~1 each.

## What it does
- **Arming:** the shadow's T2 rules, decided on the live feed as trades arrive (the shadow works 2 slots late, sorted).
  - Window: from the trigger + `--presend-live-ms` (50) to the trigger's block-clock slot + `--presend-window-slots` (10);
    or 30 ms after the whale's first sell; or a fill.
  - Create-slot triggers (the create's signer in its own create tx) are skipped by default.
  - One window per token. None while we hold the token, nor until our sell + 300 ms.
  - Every live trigger is matched with the shadow's `presend_arm` (`presend_live_parity` records).
- **Attempts:** a sender THREAD, never the event loop.
  - k per slot, evenly spaced; a late tick does not burst.
  - Each attempt is its own signed tx on the cached recent blockhash (no nonce). Instructions, in order:
    1. CU limit, CU price;
    2. Lighthouse slot deadline = min(current slot + N, the window's last slot);
    3. NON-idempotent Token-2022 ATA create (the double-fill guard);
    4. WSOL ATA (idempotent, as the engine's buy);
    5. pump buy: spend = size, min tokens out at latest price × (1 − drop), pump fee included;
    6. one tip to that attempt's path (reverted with a failed attempt).
  - 893 bytes per attempt (MEASURED).
  - Paths per leader client (`--presend-live-routes`). They must be their OWN `[[send]]` entries: any path a reactive buy or
    a sell uses is refused at start.
  - A global and a per-path rate cap (+ the path's own `max_per_sec`). Over a cap = skipped, never queued.
  - Paused while a reactive position is open (one position per server, default on), while a pre-send position is open,
    while fires are paused (blockhash / balance read), or when the balance is short.
- **Fills:** our buy TradeEvent with an attempt's signature opens a position, at once.
  - The window stops sending.
  - The reactive bot skips the token while armed, while attempts are in flight on it, and while it is held (with one
    position per server: any token while a pre-send position is open).
  - Exit as the shadow: sell when the feed reaches entry slot + `--presend-exit-slots` (2), or at once on a value ≥ +10% /
    ≤ −20%. The engine's own sell loop (`sell_until_zero`, sell path + fallback [+ fan-out]).
  - Any attempt that fills is tracked and sold, even a late one.
  - Backstop: when a window's attempts were not all seen on the feed, its token account is read once (RPC); a held balance
    is sold.
- **Caps (the engine refuses to start without them):**
  - `--presend-live-max-fills N`;
  - `--presend-live-fee-budget-sol X` (the fees of failed attempts, as the feed reports them; the stream stops there).
  - The run's kill switch is balance based, so it sees every lamport. A kill-switch stop also stops the stream.

## Engine flags
| Flag | Default | Meaning |
|---|---|---|
| `--presend-live` | off | the probe; needs `--presend-shadow`; real attempts need `--live` |
| `--presend-live-dry` | off | build + sign + log every attempt, never send (server dry run; no `--live` needed) |
| `--presend-live-max-fills N` | REQUIRED | 1..1000 (script: 1..100) |
| `--presend-live-fee-budget-sol X` | REQUIRED | (0, 1] (script: ≤ 0.1 and ≤ the dip budget left) |
| `--presend-live-routes SPEC` | REQUIRED | `class=path+path;...;default=path` (classes bam/harmonic/jito/fd/agave/other need `--route-by-client`'s leader book) |
| `--presend-live-size-sol X` | 0.55 (shadow's) | ≤ `--max-sol` (script: required, 0.05..1.0) |
| `--presend-live-k N` | 4 | attempts per slot, 1..20 |
| `--presend-live-drop X` | 0.12 (shadow's) | limit = latest price × (1 − X), (0, 0.5] |
| `--presend-live-deadline-slots N` | 1 | guard = min(slot + N, window's last slot), 1..8 |
| `--presend-live-cu-limit N` | 120000 | 20k..400k |
| `--presend-live-cu-price-micro N` | 1000 | ≤ 1,000,000 |
| `--presend-live-tip-lamports N` | the path's `tip_lamports` | ≥ the path kind's minimum; paid only on a fill |
| `--presend-live-max-per-sec N` | 20 | global attempt rate |
| `--presend-live-path-max-per-sec N` | 10 | per attempt path |
| `--presend-live-create-slot on\|off` | off | arm on create-slot triggers too |
| `--presend-live-one-position on\|off` | on | one position per server (reactive + pre-send) |
| `--sell-fanout NAME[,NAME]` | off | see "Sell fan-out" |

- The trigger / window / exit parameters are the shadow's own (`--presend-whale-pct`, `--presend-window-slots`,
  `--presend-live-ms` = the shadow's "goes live after" ms, `--presend-exit-slots`, `--presend-tp`, `--presend-sl`).
- Refused at start (MEASURED by tests and on the built binary): a misspelled flag, a non-number, a stray `--presend-live-*`
  without `--presend-live`, no shadow, real attempts without `--live`, a missing cap, values out of range, an attempt path
  that a reactive buy or sell uses, no `--buy-max-slot-delta` (the verified Lighthouse encoding).

## Run script: `ops/prod/run_dip_prod.sh.new` (original untouched)
- New options: `--presend-live`, `--presend-live-dry`, every `--presend-live-*` above (validated, passed through), and
  `--sell-fanout NAME`.
- Engine `/root/sniper-dip/snipe_engine_dip13` when `--presend-live` or `--sell-fanout` is given; otherwise unchanged
  (dip10 / 11 / 12 as before).
- Checks before start: `--presend` required; the 3 caps required (fills 1..100, fee budget ≤ 0.1 SOL and ≤ the dip
  budget left, size 0.05..1.0); every route path exists in the region's base config and is not a reactive / sell path;
  `--sell-fanout` names exist and are not staked-rpc. `--max-sol` covers the pre-send size.
- Banner adds: `| PRE-SEND LIVE: 0.2 SOL, 4/slot, caps 20 fills + 0.03 SOL fees, routes default=helius-ps | SELL FAN-OUT
  staked-rpc + helius-swqos (one signature)`.
- MEASURED in a sandbox copy (paths redirected, stub engine): 17 cases (each refusal, valid runs, an old run); the engine
  gets the intended arguments.
- Note: an older local `ops/prod/run_dip_prod.sh.new` (10-24 18:42, superseded) was replaced by this one.

## Server config (both servers; I did not touch them)
1. Add the attempt path to each base config (`/root/sniper-dip/dip_probe.toml`, `/root/sniper-dip/dip_edge_ams.toml`): a
   COPY of the `helius-swqos` block with only `name` and `max_per_sec` changed. Everything else stays identical (url with
   `?swqos_only=true` and the key, `tip_lamports`, `no_tls_endpoint`, ...).
   ```bash
   python3 - /root/sniper-dip/dip_probe.toml <<'EOF'
   import re, sys
   p = sys.argv[1]; s = open(p).read()
   assert not re.search(r'(?m)^name *= *"helius-ps"', s), "helius-ps is already there"
   b = next(x for x in re.split(r'(?m)^(?=\[\[)', s) if x.startswith('[[send]]') and re.search(r'(?m)^name *= *"helius-swqos"', x))
   nb = re.sub(r'(?m)^name *= *"helius-swqos"', 'name = "helius-ps"', b)
   nb = re.sub(r'(?m)^max_per_sec *=.*$', 'max_per_sec = 10', nb) if re.search(r'(?m)^max_per_sec', nb) else nb.rstrip('\n') + '\nmax_per_sec = 10\n'
   open(p + '.new', 'w').write(s.rstrip('\n') + '\n\n# PRE-SEND LIVE attempts only (dip13 --presend-live-routes default=helius-ps)\n' + nb.rstrip('\n') + '\n')
   print('wrote', p + '.new')
   EOF
   ```
   Check the `.new` (one more block, nothing else changed), then `mv`. Same on AMS with `dip_edge_ams.toml`.
2. Helius rate budget per region (50/s): `helius` 20 + `helius-swqos` 20 + `helius-ps` 10 = 50.
   - For 4 attempts per slot on one window (~19/s), helius-ps needs ~20/s. Option (owner's call: it changes reactive
     paths' caps): helius 15 + helius-swqos 15 + helius-ps 20.
3. Engine binary: copy `snipe_engine_dip13_presend_live` to `/root/sniper-dip/snipe_engine_dip13` (sha256 above).
4. Run script: deploy `.new` + `mv` as usual.

## Proposed probe (one server first; ~60–90 min)
```bash
sudo bash /root/prod/run_dip_prod.sh --run N --trades T --size S <today's usual options> --presend \
  --presend-live --presend-live-size-sol 0.2 --presend-live-max-fills 20 --presend-live-fee-budget-sol 0.03 \
  --presend-live-routes "default=helius-ps" --presend-live-k 4 --minutes 90 [--sell-fanout helius-swqos]
```
- Server dry run first (no attempt sent; checks rates, signing, records): add `--presend-live-dry`.
- Cost bound: 0.03 SOL of failed attempts ≈ 5,860 attempts. At ~10/s while armed that is ~90 min of windows (INFERRED from
  the study's ~6,000 windows a day).
- Expected fills (INFERRED from the study): ~20–25% of armed windows, so the 20-fill cap may stop the stream in ~30–45 min.
- Loss bound: the run's kill switch (the dip budget left) as today.

## Sell fan-out (`--sell-fanout NAME[,NAME]`)
- Every sell (first try and every retry) goes to the sell path AND each fan-out path, plus `--sell-fallback-path` as
  before.
  - ONE signed tx, one signature: it can sell once only.
  - Each tipped path's tip once (one transfer per tip family, as the buys' fan-out); paid only if the sell lands.
  - The CU limit is raised as the buys' fan-out does (only beyond 2 transfers; the 120k sell limit has room).
  - A path is never sent twice: a fan-out path that is also the fallback is sent once.
  - A fan-out path over its rate at that moment is left out of that sell, with its tip: a sell never waits on Helius.
- With `--sell-fanout helius-swqos` and today's fallback nozomi, a landed sell pays 0.0002 + 0.001 in tips.
- Refused at start: a name that is not a built `[[send]]` path, or the `--sell-path` itself. The start banner prints it.
- Logs per sell: `SELL-FAN sig=.. paths=staked-rpc+helius-swqos+nozomi tips=.. first_accept=..`; each path's own answer
  is its `SEND-ACK` line; the SELL line shows `(fan ...)`.
- Which copy landed: one signature carries every path's tip, so the landed tx's tip accounts cannot name the path. With
  `--landed-via`, the buys' attribution runs for each landed sell (Jito bundle membership: a Helius dual-route / Jito copy
  vs the rest).
- Tests (MEASURED): the tx layout with the tip transfers, one signature, no duplicate path, the over-rate drop, the
  refusals, and flag off = the old fan and the same instructions.
- Server config: none (helius-swqos exists, `max_per_sec` 20).

## Records (`--dip-log`, one JSON line each)
| Record | Main fields |
|---|---|
| `presend_live_arm` | `w`, `trig` {mint, wallet, pct, sig, slot, idx, j, t, a, age_slots, sol, vsol, vtok}, `en_slot`, k, spend, drop |
| `presend_live_skip` | `why` (create_slot / blocked_armed / blocked_position / reactive_position / no_launch_accounts / legacy_create / mayhem / non_vanilla / stopped), `trig` |
| `presend_live_disarm` | `why` (expired / whale_sold / filled / token_gone / stopped), attempts, armed_ms |
| `presend_live_parity` | `kind` live_only / shadow_only and the trigger |
| `presend_attempt` | w, n, sig, tag, path, client, leader, slot, deadline, en_slot, vsol, vtok, `p` (price at signing), `lim`, min_out, tip, cu, `t` (send ns), `w_status`, build_us, write_us, bh_age_ms, bytes, dry |
| `presend_attempt_land` | `res` (ok / 6042 / deadline / ata_exists / buy_<code> / other / unseen), err, fee, slot, **idx** (block index), t (rx), `a` (block clock), poh, first_rx, ms_send_to_rx, ack; `x` (its crossing trade) + ms_after_x_rx / _a / _first / _poh; `d` (the dump: the biggest ≥ 2% one-trade drop in the 2 slots before) + ms_after_d_rx / _a / _first / _poh; `n_between`, `between`, `after`, `instant_before_us`, `instant_after_us`, `ahead_of_instant` |
| `presend_live_fill` | w, n, sig, slot, idx, t, tokens, sol_in, fee, tip, path, client, p_sign, lim, p_entry_pre/post, slots_after_trigger, ms_send_to_rx, window_open |
| `presend_live_exit` / `_sell_land` / `_close` / `_realized` / `_tape` / `_held` / `_stop` | as the dip engine's exit / sell_land / close (+ realized P&L from the chain, the tape of a held token, a token-account backstop, the stream stop) |

- `run_start.presend_live` = the config; `run_end.presend_live` = the totals.
- The 60 s status line adds: `| PRESEND LIVE: triggers armed skips | attempts sent / not sent (why) | results | per path
  sent/ok/6042/deadline/ata/other/unseen | per client | fills | fees | acks | parity | loop / build µs p50 / p99`.
- The failed attempts' block index and error come from a new, OFF-by-default side channel of the executed gRPC feed
  (`src/feeds/mod.rs own_fail_*`; only our wallet's failed txs, only with `--presend-live`).

## Evaluator: `ops/strategies/presend/ps13_live_eval.py`
`python3 ops/strategies/presend/ps13_live_eval.py --jsonl dip_rN.jsonl [dip_ams_rN.jsonl] [--json out.json] [--from "MM-DD HH:MM" --to ...]`
1. parity of the triggers with the shadow;
2. arming, skips, disarms;
3. attempts per path and per leader client, results, acks;
4. **where they land**: ms after the dump and after the crossing trade, on the feed clock, the block-position clock,
   first sighting and PoH (p10 .. p90 and buckets 0-5 / 5-10 / 10-20 / 20-50 ms); trades between the dump and us; ahead
   of / behind the instant bots; per path and per client;
5. fill rate, failed-attempt fees per fill, tips, realized P&L (chain) and net;
6. live vs the shadow's rows a / b / c on the same windows.
- MEASURED: it runs end to end on records exported from the engine's wiring test (parity 180 / 0 / 0).
- Also run `ps11_shadow_eval.py` on the same files for the shadow side.

## Tests (MEASURED)
- `cargo test --release --lib`: 691 passed, 0 failed, 9 ignored (was 684; +7).
  - Live detector = the shadow's triggers on 312 parity tokens: 471 of 471 identical in chain order. With every slot
    reversed (worst-case arrival order): 14 differences.
  - Limit math vs pump's integer curve: fills exactly when the price is at or below the limit, never at ≥ 100 SOL.
  - Pacing: 4 per slot = 53 ms apart, no burst after a stall. Attempt layout + error classification.
  - The failed-tx side channel. The non-consuming rate check.
- `cargo test --release --bin snipe_engine`: 35 passed, 0 failed, 1 ignored (the on-chain sim, run by hand; was 30).
  - Flags + refusals.
  - Rate caps (one window at k 4 against 10/s: ~10/s sent; two windows against 20/s global).
  - The attempt with the real Lighthouse encoding passes the Helius / Jito path checks.
  - Event-loop wiring on 120 parity tokens: trigger parity exact (0 live-only, 0 shadow-only); arming; 6042 results with
    their fee and block index; fills → position, token blocked for the reactive bot, attempts paused, exits; max-fills
    and fee-budget stops; the accounting released.
  - Sell fan-out layout and refusals.
- On-chain: `PRESEND_SIM_MINTS=m1,m2 cargo test --release --bin snipe_engine presend_live_sim -- --ignored --nocapture`.

## Simulation results (MEASURED 10-25 ~08:20 PKT; 11 live tokens; 0.2 and 0.55 SOL; Helius tip 200,000; CU limit 120k)
| Case | Result | CU |
|---|---|---|
| limit = price × 0.88 | 6042 at the buy (ix 5), 22 / 22 | 54k–67k |
| limit = price × 1.03 | filled, 22 / 22 | 70.6k–84.1k (88.6k in an earlier run) |
| limit = price × 0.9995 / × 1.0005 | 6042 / filled, 22 / 22 each | as above |
| ATA created first in the same tx | IllegalOwner at our create, 22 / 22 | 22k–49k |
| as a real holder | IllegalOwner at the create (ix 3), 11 / 11 | 4k–10k |
| deadline = slot − 3 | Lighthouse 6001 at ix 2, 22 / 22 | 844 |
| deadline = the slot read just before | failed too (the simulation bank was ≥ 1 slot ahead) | 844 |
- The Lighthouse encoding is verified on chain at start, as the engine does: disc 15, op 5.
- Found while simulating: some TradeEvents carry no fee fields. The guard formula `(fbps + cbps).max(1)` then gives a
  0.01% fee and the limit ~1.2% too low. The probe uses the shadow's rule (95 / 30 bps when absent); the boundary cases
  passed with it.

## Open risks
- **Attempt rate (INFERRED):** 10/s on helius-ps. One window ~2 attempts per slot, two windows ~1 each. The study's
  4-per-slot row needs ~20/s (see the config option).
- **Deadline + 1 is tight (MEASURED in sim):** a polled slot can lag the leader by ≥ 1 slot. If `deadline` dominates the
  results, use `--presend-live-deadline-slots 2`; that makes attempts live longer (see the next risk).
- **Stale limits (INFERRED):** an attempt lives up to ~2 slots. In a slow decline, an older attempt (signed higher) can
  fill on < 12% vs the current price. The fill record has the signing price and the entry price, so the evaluator can
  flag these.
- **Fee budget / fill cap are stop rules:** attempts already in flight can still land (fees) or fill after the stop. They
  are tracked, recorded and sold.
- **Same-token race (INFERRED, rare):** the reactive bot is blocked on armed / in-flight / held tokens. A reactive buy on
  a token whose window has just ended could still meet a late fill: then both positions are sold (logged
  `reactive_on_mint`).
- **One position per server** pauses the probe while the reactive bot holds a token: fewer windows are measured then.
- **"Instant bot" detection** uses the executed feed's arrival time (within 1 ms of the dump). PoH / first sighting
  (shred feed) are logged when available.
- **Window clock:** the live window ends on a slot (trigger's block-clock slot + 10), the shadow's on the block-position
  time. The comparison is per trigger.
- **Parity:** triggers in the first moments after start can be shadow-only (the shadow starts slightly earlier).
- **Sell fan-out attribution:** which copy landed cannot be read from a one-signature tx; per-path acks and `--landed-via`
  are what we have.

## Files
- New: `src/presend_live.rs` (pure parts + lib tests), `src/bin/snipe_engine/pslive.rs` (engine wiring + tests),
  `ops/strategies/presend/ps13_live_eval.py`, `ops/prod/run_dip_prod.sh.new`, this file.
- Changed, additive / flag-gated:
  - `src/lib.rs` (+1 module);
  - `src/presend.rs` (+`done_slot`);
  - `src/feeds/mod.rs`, `src/feeds/grpc.rs` (the off-by-default failed-tx side channel);
  - `src/send/budget.rs`, `src/send/mod.rs` (a non-consuming rate check);
  - `src/bin/snipe_engine.rs`: flag list, `ALL_PATHS`, fast-ack routing of attempt tags, `--sell-fanout`;
  - `src/bin/snipe_engine/dipmode.rs`: the probe's hooks, all behind `--presend-live`.

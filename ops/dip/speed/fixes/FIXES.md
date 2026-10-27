# SPEED FIXES — engine dip14 (10-25 PKT)

Owner OK 10-25 ~08:45 PKT: "yes do the fixes". Built and tested on this machine only. Nothing deployed, no server touched,
nothing sent, nothing committed. MEASURED = a test, a replay, a log count or a build. INFERRED = my reading.

## Bottom line
- **Binary (not deployed):** `/home/moiz/sniper-data/speed_fixes/bin/snipe_engine_dip14`
  - 83,130,408 bytes, sha256 `e349fb362782a5f9b451ae59113409005e0222a4a4ba7abd8c037c25a099dd01`.
  - = dip13 + the flags below. Every flag is off by default; without them it behaves as dip13 (all old tests pass).
- **B1 shred fire works on 14.8 h of real chain data (MEASURED, 10-24 19:25 → 10-25 10:11 PKT):**
  - 62,143 of 62,143 big sells priced exactly from the token's book (SOL out, both reserves).
  - On 58,019 executed dumps: the same dump event, identical IMIT1 and M2 features, identical decisions.
  - With the tx index unknown (the real case), 0 wrong decisions. Coverage of the executed path's picks: IMIT1 43 %
    (258 / 602), M2 gate 62 % (660 / 1,064). The rest wait for the executed feed, as today.
- **What it saves (INFERRED from SPEED_TRUTH):** the executed-feed wait on the covered picks, FRA 2.2 ms median (p90 7.8),
  AMS 0.7, Firedancer leaders 6.8.
- **Main open risk:** phantom dumps. The recording has 1.88 M failed sell txs on followed tokens (37 / s). A shred fire on one is
  a cheap 6042 fail (~0.0005 SOL) but holds the one-position slot. The shadow run measures this (`dump_failed`).
- **B3:** not our engine (MEASURED). Most likely the FRA server / Constant-K Frankfurt load from the 24/7 raw recorder
  (INFERRED). New `--dip-feed-lag` records settle it.
- **D1:** PoH no longer measures time since Alpenglow (MEASURED). `--dip-clock2` adds the clocks that still work.
- **Next step (owner's call):** a 2 h shadow on one server, then the probes, then live. Commands below.

## Flags (engine; all off by default)
| Flag | What |
|---|---|
| `--dip-shred-fire shadow\|live` | B1. Decide each dump on its first shred sighting. shadow = log only; live = buy then (needs `--live`) |
| `--dip-shred-index exact\|window` | exact (default): the decision must hold for every index the dump can have. window: [exec progress − margin, + window] |
| `--dip-shred-window N` / `--dip-shred-margin N` | window policy only: 100 / 40 txs by default (1..2000 / 0..400) |
| `--dip-shred-seller-check on\|off` | on (default): a sell bigger than the seller's tokens per the book waits for the executed feed |
| `--dip-skip-clients LIST` | C1. No buy when the dump slot's leader client is listed: clientId (e.g. `Rakurai`) or class (`fd`) |
| `--dip-defer` | B2. dump / pick records after the sends; the route looked up once; the token's ATA keys derived at its create |
| `--dip-busy-poll` [`--pin-core C`] | B2. The event loop spins on the feed channel on its own thread (one core) |
| `--dip-clock2` | D1. Timing records with both block indexes, PoH position, real block size, entries and per-feed arrivals |
| `--dip-feed-lag` | B3. A `feed_lag` record every 60 s |
| `--dip-probe-clients LIST` | Probes only on these leader clients (needs `--dip-probe`) |
| `--dip-probe-tipless on\|off` | D3. Each probe also sends a tipless twin through the same one path (needs `--dip-probe-paths`) |

Refused at start (MEASURED by tests and on the built binary): misspelled flags, non-numbers, out-of-range values, a
`--dip-shred-*` / probe flag without its parent, `--dip-shred-fire live` without `--live`, shred fire with `--dip-probe`,
the tipless twin without one path per probe, client filters without the leader book.

## B1 — fire on the first shred sighting
**How it decides** (src/dip_shred.rs, src/bin/snipe_engine/shredfire.rs):
- Classify each shred tx once (first sighting on any feed; later copies ignored). Each followed token it touches:
  - only decodable pump sells (the 3 layouts validated on real triggers) → priceable;
  - any other pump instruction, a router or an unknown program → the tx is "pending" on that token.
- Pending: a shred-seen tx on the token not yet confirmed (ok or failed) by the executed feed. A dump behind one waits for the
  executed feed (the book may be stale). Never-executed txs are dropped after 2 s.
- Price: pump's integer sell on the book's newest state. MEASURED rule: SOL = floor(tokens × vsol / (vtok + tokens)); fees
  ceil(SOL × bps / 10,000). The fee pair is guessed from the token's last trade: right 99.84 %; when wrong, min_out moves ≤ 1.2 %.
- Skip a sell that cannot succeed: min SOL above what the curve pays (gross, or net of fees).
- Decide with the same rule as the executed path (envelope, launch filter, IMIT1 threshold or the M2 gate), on a speculative
  copy of the token's books that is rolled back exactly.
- **The tx index** is the one input shreds don't give. Three IMIT1 features (slotpos, prev_sell_ms, since_buy) and two M2
  features move with it; all are monotone in it. The GBDTs are scored on intervals: a pick for every possible index fires, a
  no-pick for every index is a skip, anything else waits for the executed feed.
- A pick goes through the executed path's own checks in order (spacing, launch kind, guard min_out on the shred-priced curve,
  route, near leaders, skipped clients, open positions, pauses, balance), then its FIRE code (nonce variants, records with
  `"via": "shred"`).
- No double buy: when the executed feed delivers a dump bought on shreds, the executed path logs `pick_skip shred_fired`.
- A mismatch (shred-priced trade ≠ the executed one): `shred_fallback`, and that token is decided by the executed path for the
  rest of the run.
- A failed dump tx → `shred_parity` `dump_failed`. A decided dump never delivered → `shred_unseen`.

**Records** (`--dip-log`, one JSON line each):

| record | when |
|---|---|
| `shred_dump` | every shred decision: what (pick / nopick / depends / skip:why), prices, fee guess, index range, bounds, seller_short |
| `shred_parity` | the executed feed's verdict: `executed` (inputs equal, decision equal, true index in range / window, ms saved), `dump_failed`, `no_exec_dump`, `exec_only` (+ why) |
| `shred_unseen` / `shred_fallback` | a decided dump never executed / a token moved to the executed path after a mismatch |
| `fire` with `"via": "shred"` | a buy fired on shreds (same fields as today's fire record) |
| `run_end.shred` | the totals (also in the 60 s status line) |

**Parity on the raw recording** (MEASURED; `cargo test --release --lib shred_parity_on_recording -- --ignored`;
`/home/moiz/sniper-data/speed_fixes/shred_parity_full.json`). 172 files, 36.2 M rows, 28,271 tokens created in the window,
2.35 M trades on them, every one through the engine's own books:

| check | result |
|---|---|
| big sells (≥ 1 SOL, the tx's first trade of the token) | 63,599 |
| book continuous before it (no trade missing from the recording) | 62,143 |
| shred price = executed sol / vsol / vtok | **62,143 / 62,143** |
| fee pair guess right | 62,046 (97 wrong; min_out ≤ 1.22 % off) |
| executed dump events | 58,019; the shred eval finds the same event on all |
| index known: IMIT1 features / M2 features / decisions (both modes) | identical on all (M2: 25,726 in the envelope) |
| index unknown, IMIT1: pick / no-pick / depends / **wrong** | 258 / 57,252 / 509 / **0** (executed picks 602) |
| index unknown, M2 gate: pick / no-pick / depends / **wrong** | 660 / 56,581 / 778 / **0** (executed picks 1,064) |
| index known to [true − 40, true + W], W = 10 / 20 / 40 / 80 / 160: picks covered | IMIT1 566 / 550 / 530 / 498 / 434; gate 976 / 947 / 892 / 843 / 782 |
| same-token trade within 5 / 10 / 20 / 40 txs before the dump (likely pending → waits) | 14 / 18 / 21 / 25 % of dumps |
| seller holds fewer tokens than sold, per the book | 3.1 % of dumps; 12 % of IMIT1 picks; 4 % of gate picks |
| failed sell txs listing a followed token | 1,880,766 (phantom risk; sizes unknown in the recording) |
| shred decision time (IMIT1 + M2 + bounds), this machine | 72 µs p50, 355 µs p99 |

- The window rows say what an index estimate could add (~90 % of picks). Window mode is opt-in: the shadow records whether
  the true index fell inside, so W can be set from data.
- Seller check: the default (on) can give up to 12 % of IMIT1 picks (4 % of gate picks) back to the executed path, to avoid
  phantom fires. The shadow records both.

**Engine wiring test** (MEASURED, M2 parity tapes, IMIT1 + M2 gate): 3,818 big sells seen on shreds; 2,871 decided
(78 robust picks, all executed picks too); 0 decisions differ; 0 inputs differ on exact books (2 behind tape gaps);
544 waited behind an unconfirmed buy; duplicates, a failed dump and the no-double-buy rule checked.

## B2 — work off the hot path
MEASURED before (live fire records, runs 10–15, µs p50): queue 58–147 (p90 400–800), book 26–30, score 106–140,
checks + logs 265–550 (floor 124–296), prepare 152–245, all writes 288–560.

| change | flag | MEASURED here | on the servers |
|---|---|---|---|
| dump + pick records written after the sends (same bytes, same order: test) | `--dip-defer` | 5.2 → 2.5 µs per buy (build only before the send) | INFERRED most of the 124–296 µs floor: the code there costs ~5 µs here, so the servers' write syscalls dominate (one write takes 23 µs p50 / 52 p90 there: HTTP writes in the fire records) |
| route looked up once (not again in prepare) | `--dip-defer` | — | route + tips 22 µs p50 (ops/fast/NOTES.md) |
| ATA keys derived at the token's create | `--dip-defer` | 9.8 µs dalek / 5.5 fast | 24 µs p50, 613 µs p99 in a live loop (ops/fast/NOTES.md) |
| busy-poll event loop (no bridge thread, no wake-up) | `--dip-busy-poll` | — | INFERRED: most of the 58–147 µs queue (p90 400–800); the snipe engine's busy-poll measured 13 µs p50 dequeue → decision (ops/fast/NOTES.md) |
| M2 shadow scoring after the sends | none | already so in dip13 | the shred path scores M2 only when M2 is the gate |
| shred decision instead of exec wait + book + score | `--dip-shred-fire` | 72 µs p50 | saves the exec wait: FRA 2.2 ms p50 |

- Gated behind flags even though the record bytes and order are proven identical (`defer_records_identical`): the timing
  of the writes changes, and the next run should show `lat_us.checks_logs` / `lat_us.queue` before vs after.
- Not done: signing the later nonce variants on another thread (~20 µs each); the per-socket prewarm before the writes
  (kept: changing it is a send-path change).

## C1 — skip leader clients
- `--dip-skip-clients Rakurai`: no buy (executed or shred path) when the dump slot's leader is Rakurai. MEASURED in
  SPEED_TRUTH: 7 of 8 Rakurai attempts spilled to the next slot (212 ms median).
- Matches a clientId (any case) or a class (`bam`, `harmonic`, `jito`, `fd`, `agave`, `other`).

## B3 — why FRA's executed feed slowed since run 13
**Not our engine** (MEASURED):
- The wait is the difference of two feed stamps taken in the feed tasks, before the event loop sees anything. Event-loop
  work (M2, pre-send shadow) cannot move it.
- Run 13 had neither M2 nor the pre-send shadow and was already at 3.5 ms. Runs 11 and 13 ran the same binary (dip10,
  nonce), 10 min apart: 1.3 ms → 3.5 ms (run 11 has only 5 fires).
- AMS ran the same binaries in the same hours: 0.9 (r13, dip11) and 1.0 ms (r14, dip12).
- FRA's own engine metrics stayed flat in every run: runtime ticker p50 1.07 ms, queue p50 58–116 µs, RPC p50 1.6–1.8 ms,
  relay acks unchanged (nozomi 0.27–0.32 ms).
- Higher in every leader class (bam 0.85 → 1.9–3.2; jito 1.37 → 1.9–3.9; harmonic 1.13 → 2.5–3.4): not the leader mix.
- It grows inside a run: r14 1.6 → 5.1 ms over 4.5 h; r15 2.5 → 4.5 over 2 h. r10 rose from ~1.0 to ~2.0 after 21:15 PKT.

**Likely cause** (INFERRED): FRA-side load.
- The 24/7 raw recorder runs on the FRA server. It pulls every block with getBlock, partly from Constant-K, which also serves
  FRA's executed feed. R4 started 10-24 19:25 PKT; R3's heavy final pass overlapped until ~22:52.
- FRA's Constant-K endpoints were unhealthy all along: RPC timeouts 20–140 / h and staked-rpc half-dead resets. AMS: 0.
- No correlation in 30-min bins between the wait and RPC timeouts (0.09): the RPC health alone does not explain it.

**What settles it:** `--dip-feed-lag`. Every minute it logs the executed feed's lag behind the first shred sighting of every
pump tx (thousands of samples, not just fires), by feed, plus the providers' own message stamps → our receipt.
- Provider lag flat while the wait grows → the provider sends late.
- Provider lag grows too → our receive side or the network.
- Optional (owner's OK): 30 min with the recorder paused (`touch /root/sniper-collect/ROTATE_OFF` stops new runs only).

**Fix in our code:** none found. B1 takes the decision off this wait for the covered picks.

## D1 — PoH since Alpenglow
MEASURED on 309 live attempts:
- Within one slot, our tx's PoH "ms" ÷ the dump's = our block index ÷ the dump's. Log-ratio correlation 0.987 on 148
  same-slot pairs, median residual 0.8 %.
- PoH difference vs the feed-clock difference: correlation −0.003. Block index vs feed clock: 0.47–0.59.
- So the hash count now counts position in the block (entries / txs), not leader time. The 0–3 "ms" values are that position
  ÷ the previous slot's hash total ÷ 64.

**Fix** (`--dip-clock2`; timing record field `clock2`):
- `dump_idx`, `buy_idx` (our failed tx's from the executed feed's side channel), both slots, the slots' real sizes.
- `dump_pos`, `buy_pos`: PoH hashes ÷ the slot's own total = the fraction of the block (the "fixed PoH"); `land_ms_pos`.
- `land_ms_b400`, `land_ms_bmix`: the study's block clocks, with the real block size.
- `land_ms_ent`: the entries feed's arrival of our tx minus the dump's. The closest thing to leader time left.
- `feeds`: every feed's own arrival of both txs and the difference.
- Leader-side time itself is not recoverable from the feeds we have (INFERRED). The Alpenglow block footer
  (`block_producer_time_nanos`) gives one leader stamp per block, if the provider streams it.

## Probes: send-leg plan (fix A, the biggest lever)
- `--dip-probe` fires buys that cannot fill (min out = u64::MAX → pump 6042; tips revert). Cost per landed probe = 5,000 +
  100,000 CU × 5,000,000 µL = **505,000 lamports (~0.0005 SOL)**. A copy that never lands costs 0.
- New: `--dip-probe-clients` (only Jito, only Harmonic…), one forced path per probe (already `--dip-probe-paths`), D3
  twins, `tag` in the record, and `--dip-clock2` timing (the run script forces it with `--probe`).
- Evaluator: `python3 ops/dip/speed/fixes/probe_eval.py --jsonl dip_rN.jsonl --log dip_rN.log --propose`. Per path and leader
  class: landed %, same-slot share, landing ms (feed, first sighting, B400, Bmix, PoH position, entries), block index and
  distance, cost; D3 tipped vs tipless; a proposed ROUTES string.

Already known for D3 (MEASURED, the 10-24 probes probeA–E, 190 single-path can't-fill probes, 190 `probe_land` records):
every tipped copy landed as a failed tx: helius 18 / 18, nozomi 18 / 18, bolt 18 / 18, helius-swqos 8 / 8, landx 10 / 10,
astralane 10 / 10, haan 10 / 10. So single tipped copies are NOT dropped on those relays. Still open: jito-bundle, and the
nonce race (only one variant can land).

**Commands** (FRA; AMS: `--region ams`, `landx-ams2` instead of `landx-fra3`). Run inside tmux; owner's OK first.
```bash
# P1  Jito leaders, 6 paths x 20 (~15-30 min); staked-rpc = the tipless control
sudo bash /root/prod/run_dip_prod.sh --run <N> --trades 1 --size 0.05 --fallback ck \
  --near /root/sniper-dip/near_leaders_5ms.txt --minutes 60 \
  --probe 120 --probe-paths helius,helius-swqos,nozomi,staked-rpc,jito-bundle,bolt --probe-clients jito
# P2  Harmonic leaders, 4 paths x 20
sudo bash /root/prod/run_dip_prod.sh --run <N+1> --trades 1 --size 0.05 --fallback ck \
  --near /root/sniper-dip/near_leaders_5ms.txt --minutes 60 \
  --probe 80 --probe-paths nozomi,helius-swqos,landx-fra3,staked-rpc --probe-clients harmonic
# P3  D3: tipped vs tipless twin on the same dumps, 6 tipped paths x 10 pairs (staked-rpc is refused: no tip)
sudo bash /root/prod/run_dip_prod.sh --run <N+2> --trades 1 --size 0.05 --fallback ck \
  --near /root/sniper-dip/near_leaders_5ms.txt --minutes 60 \
  --probe 60 --probe-paths helius,helius-swqos,nozomi,bolt,jito-bundle,landx-fra3 --probe-tipless on
```
| run | txs | max cost if every copy lands | likely |
|---|---|---|---|
| P1 | 120 | 0.061 SOL | ~0.05 (jito-bundle copies that revert are dropped) |
| P2 | 80 | 0.040 SOL | ~0.04 |
| P3 | 120 (60 + 60 twins) | 0.061 SOL | ≤ 0.03 (tipless copies to tip-only relays are refused) |
| all, one region | 320 | **0.162 SOL** | ~0.12 |

- Time (INFERRED from run 15's 0.47 in-envelope dumps / s, ~30 % on Jito or Harmonic near leaders, 1.5 s gap): P1 and P2
  ~15–30 min each, P3 ~5–10 min. The engine stops 5 s after the last probe.
- The probes' fees count against the dip budget (kill switch as usual).

## Route proposal (owner's decision at deploy; confirm with P1 / P2 first)
From SPEED_TRUTH A1–A3. FRA (AMS: `landx-ams2`):
```
bam=nozomi+helius-swqos+staked-rpc;jito=helius-swqos+helius+nozomi+staked-rpc;harmonic=nozomi+helius-swqos+landx-fra3+staked-rpc;fd=nozomi+landx-fra3+staked-rpc;agave=nozomi+helius-swqos+staked-rpc;other=nozomi+helius-swqos+staked-rpc;default=nozomi+helius-swqos+staked-rpc
```
- Jito: jito-bundle and bolt out, keyed helius-swqos in, helius Sender kept. Harmonic: unchanged until P2.
- bam / agave / other: bolt out (2 of 68 nonce fills). Plus `--skip-clients Rakurai`.
- `probe_eval.py --propose` prints the data-driven version after the probes.

## Run script: `ops/prod/run_dip_prod.sh.new`
- Copied from the deployed version (md5 d918d7cb; a reference copy is `ops/dip/speed/fixes/run_dip_prod.sh.dip13`). New
  md5 `392a5c91b9323fd2913a632de1373e6f`.
- New options: `--shred-fire shadow|live`, `--shred-index`, `--shred-window`, `--shred-margin`, `--shred-seller-check`,
  `--skip-clients LIST`, `--defer`, `--busy-poll [--pin-core C]`, `--clock2`, `--feed-lag`, `--probe N --probe-paths a,b
  [--probe-clients LIST] [--probe-tipless on] [--probe-gap-ms MS]`.
- Engine `/root/sniper-dip/snipe_engine_dip14` when any of them is used; otherwise unchanged (dip10 … dip13).
- MEASURED in a sandbox copy (paths redirected, stub engine): 24 cases. Each refusal; valid shred / all-options / probe /
  D3 runs pass the intended engine arguments; an old run still starts dip10; a pre-send live run still dip13.

## Deploy steps (owner)
1. Copy the binary to both servers as `/root/sniper-dip/snipe_engine_dip14`; check the sha256 above.
2. Deploy the script: copy as `/root/prod/run_dip_prod.sh.new`, check, then `mv` (never overwrite a running script).
3. Shadow first, one server, ~2 h at peak, with today's options plus
   `--shred-fire shadow --clock2 --feed-lag` (and `--defer` to measure B2). Evaluate:
   `python3 ops/dip/speed/fixes/shred_eval.py --jsonl dip_rN.jsonl`. Go / no-go: decision_differ 0; inputs_differ ≈ 0;
   `dump_failed` among picks (the phantom rate); ms saved on picks.
4. Probes P1–P3 (above), then set ROUTES from `probe_eval.py --propose`.
5. Live: `--shred-fire live --defer --skip-clients Rakurai` (+ `--busy-poll --pin-core C` if a core is free).

## Risks
- **Phantom dumps** (the big one). 1.88 M failed sells on followed tokens in 14.8 h. Mitigations: slippage check, seller
  check, pending rule. The shadow measures the rest. A phantom fire costs ~0.0005 SOL plus the position slot for ~0.5–1 s.
- **Coverage:** exact index mode covers 43 % (IMIT1) / 62 % (gate) of picks, minus the pending (14–25 % of dumps) and
  seller-check waits. Window mode covers ~90 % but can be wrong if the estimate misses (the shadow records it).
- **Fee guess:** wrong on 0.16 % of sells; min_out then up to 1.2 % off.
- **Busy-poll** takes a whole core. FRA also runs the raw recorder.
- **Shadow mode adds event-loop work:** classify every pump tx once (~µs) and decide each big sell (~72 µs p50).
- **One always-on change:** the entries feed now keeps each finished slot's hash total (bookkeeping only; no decision or
  record changes without `--dip-clock2`).
- **The landing clocks** (`clock2`) are block-position clocks; PoH no longer gives leader time.
- **B3 is not fixed in code:** the exec-based path still waits on FRA until the cause is found.

## Tests (MEASURED, this machine)
- `cargo test --release --lib`: 698 passed, 0 failed, 10 ignored (was 691 / 9).
  - New: classify, tracker, pricing + guard + index range, the decision rule truth table, speculative push / rollback
    (54,853 on the IMIT1 tapes; M2 on its tapes), time features, interval bounds.
  - Real wire txs (`testdata/dip_sells.json`): 153 sells found exactly as the decoder finds them; 9 single-sell txs priced
    exactly against their own TradeEvent (sol, vsol, vtok; seller = the event's user).
  - Ignored, run by hand: the recording parity above.
- `cargo test --release --bin snipe_engine`: 40 passed, 0 failed, 2 ignored (was 35 / 1).
  - New: shred flags / refusals; the shred wiring on the parity tapes (incl. the token fallback); B2 record identity;
    clock2 record; key cache.
  - Ignored, run by hand: the B2 cost bench.
- `cargo build --release` (under nice): OK.

## Files
- New: `src/dip_shred.rs`, `src/bin/snipe_engine/shredfire.rs`, `ops/dip/speed/fixes/{FIXES.md, probe_eval.py,
  shred_eval.py, run_dip_prod.sh.dip13}`.
- Changed, additive / flag-gated: `src/lib.rs`, `src/dip.rs`, `src/dip_imit.rs`, `src/dip_model.rs`, `src/feeds/entries.rs`,
  `src/feeds/mod.rs`, `src/bin/snipe_engine.rs`, `src/bin/snipe_engine/dipmode.rs`, `ops/prod/run_dip_prod.sh.new`.
- Data: `/home/moiz/sniper-data/speed_fixes/` (binary, parity json + log).

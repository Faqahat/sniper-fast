# FAST: launch detection → buy bytes on the socket (2026-10-19)

Zero cost only:
- `--live` was never passed and no real transaction was sent.
- Measured with junk fan-out runs (real feeds, gates and routing; the signed tx has its signature count set to 0, so it can never be a valid tx), `--fast-bench` and `--fast-probe` (synthetic launches), and a paper smoke.
- Wallet 0.110818539 SOL at the start and end of every run.
- Keys and `.env` untouched; `/root/arbx-fast`, `/root/arbx-merge` and `/root/race` not modified.

## Binary and source

- **Binary:** `/root/arbx-lat/target/release/snipe_engine`, md5 **9e3549272e118301ab0536e5721beb87** (build 7, 12:03 UTC). Same file as `/root/fast/snipe_engine.b7`.
  - Old binary: `/root/arbx-lat.bak_fast/target/release/snipe_engine`, md5 36c4fadb….
- **Source:**
  - full backup: `/root/arbx-lat.bak_fast`;
  - diff: `/root/fast/fast.patch`;
  - new code: `src/fast.rs`, the `mod fastfire` section of `src/bin/snipe_engine.rs`, small accessors in `src/send/mod.rs` and `src/send/jito.rs` (`note_bundle`);
  - Cargo: `webpki-roots` and `httparse` (both already in Cargo.lock).
- **Every new behaviour is behind a flag.** Without the flags the engine is the LAT engine.
- **Recommended flag set** (the one measured in run C):
  `--fast-send --busy-poll --pin-core 1 --jito-h2 --fast-presign --fast-derive`. Add `--fast-verify --lat-trace FILE` for checking.

## Before → after (decision → bytes handed to the kernel)

- **Measured with bpftrace** at `write()`/`sendto()`/`writev()` syscall exit (kernel time), matched to each path's socket.
  - **Before:** old binary, run `before` (15 min), 21 fires.
  - **After:** run `fastC` (20 min), 21 fires.
  - Both runs used the same routes and Gate B flags (`--race-early`).
- **The decision** is when Gate B passes (the tx that completes the creator bundle).
- **Small n:** with 21 fires, p99 is close to the max.

| stage (µs) | before p50 | before p99 | after p50 | after p99 |
|---|---|---|---|---|
| **decision → FIRST path written** | **902** | **2,250** | **46** | **173** |
| decision → LAST path written | 1,278 | 9,170 | 122 | 284 |
| decision → landx-fra3 (UDP) | 841 | 2,385 | 42 | 79 |
| decision → jito-bundle | 1,191 | 9,170 | 84 | 181 |
| decision → nozomi | 1,142 | 8,098 | 103 | 261 |
| decision → helius | 1,051 | 2,681 | 133 | 187 |
| decision → astralane | 2,104 (n=1) | — | 121 | 233 |
| decision → staked-rpc | 1,084 | 2,875 | 122 | 284 |
| deciding tx dequeued → decision | (not measured) | — | 13 | 247 |
| build + sign (on the decision path) | 391 (p90 865) | 1,658 | **0**: done at the create | — |
| build: whole prepare, real loop (cold) | — | — | 73 | 704 |
| build: whole prepare, hot (`--fast-bench`) | 152 (old build) | 534 | 26 | 79 |

**Stages of the prepare** (real loop, 281 creates, p50/p99 µs):

| stage | p50 | p99 |
|---|---|---|
| route + tips + blockhash | 22 | 151 |
| derive 2 ATAs | 24 | 613 |
| template patch | 3 | 25 |
| sign (presign) | 8.5 | 54 |
| encode + frame every path | 12 | 83 |

- 281 of 281 messages were byte-identical to the old full compile (`--fast-verify`), and every signature passed `verify_strict`.

**Hot microbenchmark** (`bench_b6.txt`, µs, p50/p99):

| step | p50 | p99 |
|---|---|---|
| deterministic sign | 38 | 58 |
| presign | 3.5–6 | 12 |
| ATA derivation, dalek | 13.7 | 56 |
| ATA derivation, fast | 7.3 | 35 |

**Each write() itself** (run C, p50 µs):

| path | p50 |
|---|---|
| helius (plain TCP) | 14 |
| nozomi / staked-rpc / astralane (TLS) | 15–18 |
| landx (UDP) | 28 |
| jito-bundle (TLS h2) | 51 |

## What changed (flags)

1. **`--fast-send`: prepare at the create, write at the decision.**
   - When a launch passes the base gates (the race gate decides later), everything is done at once: route, tips, blockhash, the signed tx and every path's framed request.
   - The decision then only writes. Build and sign left the decision path: −391 µs p50.
2. **Template message.**
   - The buy message is compiled once per tip shape, with probe keys.
   - A fire copies it and patches in place the mint, bonding curve, curve ATA (taken from the create tx), the quote ATA of the curve, the user's ATA, the buyback account, the tip accounts, the blockhash and min_out.
   - If any patched key collides with another key (which would change the dedup), it falls back to the full compile.
   - Checked byte for byte against the old compile on 5,000 bench launches and on every real create (177 + 33 + 281, 0 mismatches).
3. **Own send connections** (`arbx::fast::FastConn`).
   - One HTTP/1.1 keep-alive connection per HTTP path (plain or rustls), with TCP_NODELAY.
   - Pre-built headers; one `write()` per request, from the event-loop thread (no task hop, no reqwest/hyper dispatch).
   - A reader thread matches replies (`FAST-ACK` lines plus the send log); a keep-alive thread pings every 2 s.
   - The JSON body is byte-identical to the old serde_json body (self-test at start).
   - A path whose connection is down falls back to the old async send.
4. **`--jito-h2`: Jito SendBundle as raw HTTP/2 frames on our own TLS connection (ALPN h2).**
   - HPACK dynamic-table indexing, so the bearer token is sent once per connection.
   - The bundle id goes to the Jito client (`note_bundle`), so `JITO-RESULT` still joins.
   - Limit: the trailers are not decoded. A refusal reads "rejected (no message)"; the reason (here a deserialize error, seen via tonic) is not shown.
   - The block engine accepted the framing in every run: 1 connect each, no GOAWAY.
5. **LandX UDP** is written from the hot thread first. The second copy goes after every other path's first write.
6. **`--fast-presign`: Ed25519 with pre-computed nonces.**
   - A background pool holds (r, R = r·B), with r from getrandom. Each pair is popped and used once; an empty pool falls back to the deterministic signature.
   - Self-test of 300 signatures plus `--fast-verify`: all pass `verify_strict`.
   - **The message bytes are identical; the signature (and so the tx id) differs from the RFC 8032 deterministic one.** It is a valid Ed25519 signature.
   - Without the flag: the deterministic signature, 38 µs.
7. **`--fast-derive`: the on-curve check of `find_program_address`** is done by a Legendre/Jacobi symbol instead of point decompression, with no allocation.
   - Self-test at start: 200,012 inputs vs dalek and 3,000 ATAs vs `pda::ata`, 0 differences. Otherwise the engine refuses to start.
8. **`--busy-poll` / `--pin-core N`.**
   - The event loop gets its own thread and spins on the feed's crossbeam channel (no bridge thread, no tokio wake-up).
   - The DETECT / RACE log lines go to a logger thread instead of unbuffered stderr writes on the loop. One `eprintln!` was ~10–20 write syscalls.
9. **Tools:**
   - `--lat-trace FILE`: a JSON line per create and per fire, with monotonic ns stamps.
   - `--fast-bench N`, `--fast-probe N` (junk only).
   - `wtan.py` (bpftrace truth), `stages.py`, `dry.sh`, `bench.sh`, `probe.sh`, `wtrace.bt`.

## Correctness (zero cost)

- **Message bytes:** identical to the old compile in every check (5,000 bench + 491 real creates). Gate decisions unchanged: same gate code; only its log lines are deferred.
- **Every provider parses the real-size junk and rejects it only as a decode error:**

  | provider | reply |
  |---|---|
  | nozomi | "Malformed transaction string" |
  | astralane | 400 "failed to parse binary transaction" |
  | helius | 500 "failed to deserialize" |
  | staked-rpc | -32602 "failed to deserialize" |
  | jito | rejected (via tonic: "Transaction had serialization error") |

- **Runs:**
  - fastA (20 min): 30 fires.
  - fastC (20 min): 21 fires; 73/73 writes; no HTTP 429; 0 panics; each connection connected once.
  - Wallet unchanged in both.
- **Paper smoke:** 6 min, 428 DETECT lines, 13 decisions, 0 panics, result printed. Re-run on build 7 (`paper_smoke7.log`): 435 DETECT lines, 8 decisions, 0 panics, result printed.

## Still above budget, and why (honest)

- **The first write still costs ~30–50 µs by itself on this VM.**
  - The virtio NIC charges ~30–50 µs for a send after the TX queue has been idle, against ~8 µs when it is busy (measured).
  - A fire is rare, so its first packet always pays this. It cannot be fixed from inside the guest. A bare-metal box or a host with SR-IOV/vhost polling would remove it.
  - An idle-NIC warm-up experiment showed no gain and was removed.
- **The writes are sequential, at 14–51 µs each, so the last path lands ~120 µs after the decision** (p99 284).
  - Jito's h2 write is the largest (TLS plus 2 frames, ~51 µs).
  - Spreading the writes over several pinned threads would cut this, but costs more spinning cores on a shared 4-vCPU VM. Not done.
- **The real loop is cold.** Fires and creates are rare, so caches and branch predictors are cold.
  - Prepare is 73 µs p50 in the loop vs 26 µs hot, with a heavy tail (p99 704 µs, mostly derivation bumps and cache misses).
  - It is off the decision path, but it can delay a bundle tx that is already queued behind the create.
  - Deciding tx dequeued → decision: 13 µs p50 / 247 µs p99 (race observe + due, cold).
- **Input side** (not changed here): the gRPC deshred feeds stamp t_rx after decode. "Decoded → dequeued" p50 is ~21 µs, but its p90/p99 of 0.3 / 2 ms is mostly txs batched inside one feed message.
  - The `/root/gap` agent measured constant-k raw UDP shreds arriving ~0.67 ms earlier than Kaldera. That is the larger lever.
- **Beyond our side:** RTT to the providers (0.5–1.4 ms warm), their forwarding, and the leader's scheduler (the ~45 ms "we land late" in /root/lat/NOTES.md). None of this changes with local µs.

## Live caveats (not testable at zero cost)

- `round_trip_fast` (live): the buy is written by the fast path, then the existing land poll and exit.
- If every path refuses, the buy now waits out `--land-timeout-ms` instead of failing at once. No money is at risk; it is only slower.
- `--fast-send` requires `--fill-cap` or `--min-tokens-out` (no curve read at the create) and refuses `--demand-window-ms`.

## Incident

- 11:44 UTC: while restarting my own build I killed another agent's cargo build (`/root/gap`, feed_race in `/root/arbx-feed`).
- Its owner had already relaunched it. I left `/root/gap/NOTE_FROM_FAST_AGENT.txt`. Nothing else was touched.

## Files (`/root/fast/`)

| file | what |
|---|---|
| `NOTES.md` | this file |
| `fast.patch` | the source diff |
| `snipe_engine.b1`…`b7` | the builds |
| `dry_before.*`, `wt_before.txt`, `fd_before.txt` | old-binary run |
| `dry_fastA.*`, `dry_fastC.*`, `trace_fast*.jsonl`, `wt_fast*.txt` | fast runs |
| `bench_b*.txt`, `probe_b*.txt` | bench and probe outputs |
| `paper_smoke*.log` | paper smokes |
| scripts | `dry.sh`, `bench.sh`, `probe.sh`, `paper_smoke.sh`, `wtrace.bt`, `wtan.py`, `stages.py` |

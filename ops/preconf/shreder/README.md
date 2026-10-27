# Shreder preconf trial — recorder, run scripts, analysis

Read-only measurement. Nothing here signs or sends a transaction, and nothing touches the engines.

## The trial

- Shreder gives a one-hour trial of **preconfs** (pre-shred transactions from connected leaders) and its normal **Binary** stream (shred-reconstructed).
- Access is an IP allowlist with one IPv4, FRA 84.32.100.36, so everything Shreder runs on FRA. There is no token. AMS has no access.
- The endpoint defaults to `http://fra-allnodes.binary.shreder.xyz:9991`, the docs' preconf example. An optional access file `/root/shreder.key` overrides it, with `endpoint = ...`, `token = ...` and `header = x-token` (or bare lines).
- The endpoint and token are never printed. Logs show only an endpoint id (an FNV hash).

## What was built

| file | what |
|---|---|
| `src/main.rs`, `src/txparse.rs`, `src/util.rs` | `shreder_rec`, the Rust recorder (tonic 0.14). Proto vendored from shreder-rust-example `dc1d367` (`proto/shreder_preconf.proto`). |
| `dist/shreder_rec` (+ `.sha256`) | Release binary, glibc ≥ 2.34 (FRA/AMS have 2.43). Deployed to FRA `/root/shreder/bin/`. |
| `src/bin/shreder_fake.rs` | Local fake Shreder gRPC server, used for tests and CPU runs only. |
| `server/run_rec.sh`, `stop_rec.sh`, `rec_status.sh` | FRA side, installed in `/root/shreder/`. |
| `deploy.sh`, `preflight.sh`, `start_all.sh`, `status.sh`, `stop_all.sh`, `fetch.sh`, `after_hour.sh` | Host side. |
| `clock_probe.py` | FRA↔AMS clock offset (chrony on both + host-hub ssh midpoint bracket) and FRA→AMS ping. |
| `read_rec.py` | Dataset reader (stdlib). `make_catalog.py` writes `catalog.json`. |
| `shreder.key.example` | Access-file template (optional; the trial needs none). |
| `ck/` | Constant-K feed race next to the recorder (other agent): `ck_start.sh`, `ck_status.sh`, `ck_stop.sh`, `ck_fetch.sh`. |
| `analyze.py`, `make_synth.py`, `test_analyze.sh` | Trial analysis: coverage, leads, accuracy, what-ifs (other agent). |
| `ck_compare.py` | Shreder vs Constant-K per-feed comparison (other agent). |

### Recorder behaviour

- **Streams.** The default is `--stream pre:pre:all --stream bin:bin:all`: two subscriptions (preconf=true and preconf=false) with no account filter, each on its own HTTP/2 connection.
  - If the server refuses an unfiltered filter (InvalidArgument/FailedPrecondition twice), or sends nothing for 45 s (90 s on preconf), the stream falls back to the **broad** list: pump.fun, pump AMM, Raydium v4/CPMM/CLMM/LaunchLab, Meteora DLMM/DAMM v2, Orca Whirlpool, Jupiter v6 and the 8 Jito tip accounts.
  - All IDs were checked against the repo constants (Jupiter v6 is the well-known ID).
  - `FILTER=broad` forces the broad list. `PUMP_PAIR=1` adds server-side pump-filtered `fpre`/`fbin` streams.
  - `EXCLUDE_VOTES=1` sets account_exclude=[Vote program] on the unfiltered Binary subscription to cut its volume (not allowed on preconf).
  - `MODE=both` makes ONE subscription carry both sources (filters "pre" preconf=true + "bin" preconf=false); messages are routed by `update.preconf` into the same pre/bin files. Use it only if Shreder refuses a second connection (ResourceExhausted in status): one TCP stream couples the two sources' timing.
- **Receive path.**
  - `rx_ns` (CLOCK_REALTIME) is taken in the gRPC task right after each message is decoded.
  - The message then goes over a bounded queue (100k) to a per-stream writer thread, which does all gzip and disk work.
  - Measured on localhost against the fake server, rx minus the server's send stamp was P50 14 µs and P99 47 µs at 9k msg/s.
- **Output.** All files go to `/root/shreder/data/<RUN>/` on FRA, with HH = the PKT hour:
  - `<stream>_<YYYYMMDD_HH>_<part>.rec.gz`: every message, as gzip members of about 1 s each. Records use struct `'<IQqqQBBHI'`: rec_len, seq, rx_ns, ca_ns, slot, flags (bit0 preconf, bit1 parse error, bit2 empty), n_proto_sigs, reserved, tx_len. They are followed by the raw bincode VersionedTransaction.
  - `<stream>_<YYYYMMDD_HH>_<part>.idx.jsonl`: one line per member (offset, length, seq/rx/slot ranges), for random access.
  - `<stream>_<YYYYMMDD_HH>.jsonl`: the pump view, i.e. txs whose static keys hold the pump.fun program. Fields: `q,t,ca,s,sig,pf,c,v,p` with `p=[[kind,mint,user,a1,a2]]`.
  - `events.jsonl` (connect/subscribe/errors/stream_end/fallback, 30-s status, live pre-vs-bin lead) and `rec.log`.
- **Reconnects** use backoff from 0.5 s up to 10 s. A stall watchdog reconnects after 60 s of silence, and HTTP/2 keepalive runs at 15 s.
- **Stopping.** The recorder stops with `--minutes`/`--until HH:MM` (PKT) or SIGTERM/SIGINT, and flushes and closes cleanly.
- **Disk guard.** Above 80% disk use the raw dataset pauses and the views continue.
- **Process limits.** Runs at nice 10 with ionice best-effort 7 and oom_score_adj 500. The feed race is at 800, so OOM kills the race first, then the recorder, and never collect.py or the engines.

## Constant-K feed race (ck/, built by the CK agent)

- Feeds: `kaldera` and `turbo-kaldera` (SubscribeDeshred) and `kaldera-tx` (Subscribe, processed). These are the 3 Constant-K feeds the engines use, with the FRA endpoints and token env names from `/root/prod/dip_prod.toml` (never printed) and a pump.fun-only filter.
- The harness is a copy of `/root/gap/bin/feed_race`, run at nice 10 with oom_score_adj 800. It stops itself after MIN; a watchdog hard-stops it at MIN+3 or 500 MB RSS. It refuses to start with under 400 MB of memory available.
- Keys: KALDERA_TOKEN equals CONSTANTK_TOKEN (one key). The race adds 2 deshred + 1 Subscribe streams in Frankfurt, far under the per-key per-region limits (15/25 and 75/200). **Start order: engine (if it moves to FRA) first, then `start_all.sh`.**
- `ck_status.sh` should show all 3 feeds connected within about 30 s of the start.

## Commands (host, from `/home/moiz/sniper/ops/preconf/shreder`)

```bash
./preflight.sh                  # read-only: binary sha, disk, mem, endpoint TCP reachability, collector lag
./start_all.sh 75               # START EVERYTHING ON FRA: recorder (75 min) + CK feed race + clock probe + first status
./status.sh                     # msgs/s per stream, ~GB/h, cpu, rss, disk, collector lag, last issue; CK per-feed lines
./stop_all.sh                   # early stop (both stop by themselves after 75 min) + end clock probe
./after_hour.sh                 # verified fetch (sha256) -> catalog.json -> analyze.py -> ck_compare.py (run >=15 min after the hour: chain chunks)
./after_hour.sh --analyze-only  # re-run the analysis later (e.g. once the chain recording covers the hour)
```

Variants:
- `FILTER=broad ./start_all.sh 75`: use the broad list if unfiltered is too heavy.
- `EXCLUDE_VOTES=1 ./start_all.sh 75`: keep unfiltered, but drop vote txs from the Binary stream.
- `MODE=both ./start_all.sh 75`: one connection for both sources, if Shreder allows only one.
- `EXTRA="--endpoint http://fra.binary.shreder.xyz:9991" ./start_all.sh 75`: another endpoint (never printed in logs).
- To restart with other settings: `./stop_all.sh`, then start again (same RUN: files are appended, seq restarts at 1, a new `start` event marks it).
- `NO_CK=1 ...`: run without the CK race.
- `ENGINE_HOST=fra ./after_hour.sh`: use this if the engine ran on FRA for the hour. By default `fetch.sh` snapshots (read-only `sudo cat`) the NEWEST `/root/prod/runs/dip_<host>_r*.jsonl` (+ its `.log`) on that host. AMS r28 ended at 22:03 PKT 10-27 and r30 was live at 22:21, so pass `ENGINE_LOG=<path>` if another run starts after the hour.
- Analysis alone: `python3 analyze.py --run-dir /home/moiz/sniper-data/preconf/<yyyymmdd> --engine-host ams|fra --leaders-rpc [--from 00:30 --to 01:30 --date 2026-10-28]` and `python3 ck_compare.py --run-dir ...`.

Server-side equivalents: `sudo /root/shreder/run_rec.sh RUN MIN`, `sudo /root/shreder/stop_rec.sh RUN` and `sudo /root/shreder/rec_status.sh RUN`. The RUN default is `trial_<PKT yyyymmdd>`, stored in `/home/moiz/sniper-data/preconf/CURRENT_RUN`.

Host data lands in `/home/moiz/sniper-data/preconf/<yyyymmdd>/`:
- `fra/`: recorder files, `MANIFEST.sha256`, and `clock_start.json`/`clock_end.json`;
- `ck/`: the feed race;
- `engine/`: the engine log snapshot;
- `catalog.json`;
- `analysis/`.

Server copies are never deleted by these scripts.

## Tests (all pass, 2026-10-27 22:20 PKT; deployed binary sha256 109786c7deeaf44b2e5150f6e22d71602c042a2cdbf0f39033ebf62eb37c63fb)

Run with `CARGO_TARGET_DIR=<scratch>/target cargo test --release`.

- **Unit tests (8).** Synthetic legacy and v0 txs (with lookup tables), pump summary kinds and mint/user resolution, truncation and garbage rejection, compact-u16, PKT time and rotation keys, access-file forms, secret redaction.
- **`tests/real_fixtures.rs`.** 3 legacy and 3 v0 **real mainnet** pump txs, fetched as wire bytes with `getTransaction(base64)`. The parse matches the RPC's own JSON decode: signature, header, static keys, lookups, every instruction's program, accounts and data.
- **`tests/fake_e2e.rs`** (5 tests) runs the real binary against the fake gRPC server:
  - dataset decodes, seq has no gaps, and the idx counts match;
  - the pump view equals the pump subset;
  - a server-side stream end leads to a reconnect;
  - the live lead estimate sees the injected 5 ms (measured 6.0–6.4 ms; the fake's timers add about 1 ms);
  - a token is accepted, and a missing token gives a clean PermissionDenied with no data;
  - the token and endpoint never appear in the logs;
  - an "unfiltered not allowed" server triggers the broad fallback;
  - a server allowing ONE connection: the default mode logs clean ResourceExhausted refusals, `both` mode records both sources over one connection, routed correctly, with the lead still visible;
  - `--exclude-votes` puts the Vote program in account_exclude on the Binary filter only.
- **Real endpoint from the host (not allowlisted).** `shreder_rec --check` connects and gets a clean `PermissionDenied: Access denied for IP` on both streams.
- **CPU.** With realistic-compressibility random payloads at 8k msg/s Binary plus 3–4.5k msg/s preconf (about 5 MB/s raw), the recorder used **8–9% of one core** and **RSS 73 MB**, at a gzip ratio of about 1.8×. At that rate the projection is about 6.4 GB/h for Binary and 3 GB/h for preconf.

## What to look for right after the start

`./status.sh` about 15 s after `./start_all.sh` (first status at 10 s, then every 30 s):
- `pre .../s` and `bin .../s` both > 0 and `up`: access works. `subscribe refused: grpc PermissionDenied: Access denied for IP` means the allowlist is not active yet; the recorder retries every ≤10 s by itself.
- `ResourceExhausted` on one stream only: Shreder allows one connection -> `./stop_all.sh`, then `MODE=both ./start_all.sh 75`.
- `FALLBACK`: unfiltered was refused or silent; the stream now records the broad program list.
- `~X GB/h` per stream (gzip) and `cpu`: if pre+bin together project more than ~20 GB/h, restart with `EXCLUDE_VOTES=1` (or `FILTER=broad`); the disk guard pauses the raw dataset at 80% anyway.
- `lead[all] ... bin-pre P10/50/90`: the live preconf lead over Binary for the same signatures.
- `collector: lag_slots` should stay where it was before the start (about 35-55).

## Analysis tests (verified 22:25-22:28 PKT)

- `bash test_analyze.sh`: ALL PASS. Synthetic run from a real chain window and the real r28 log, with injected coverage, leads, never-landed share, slots, order, gap, duplicates, truncation and the AMS offset all recovered; plus a variant with FRA only, no engine and the `fpre,fbin` streams.
- `bash ck/test_ck.sh`: RESULT PASS (25/25). Uses a real FRA race log, the real r28 log and chain truth; every injected lead is recovered exactly, and the whale and dump rules match the engine's own triggers 236/236 and 1590/1590.
- `after_hour.sh` ran end to end on a fake-data run fetched back from FRA (verified sha256 copy, engine snapshot, catalog, analyze.py, ck_compare.py).

## Known gaps

- **Real rates and sizes are unknown until the first minute.** It is not known whether Shreder serves unfiltered streams at all, or whether they include votes. The 10-s and 30-s status lines show msgs/s and ~GB/h per stream.
- **Preconf coverage is limited to leaders connected to Shreder.** The pump view uses static keys only: a pump tx that reaches pump only through a lookup-table program id is in the dataset but not in the view. The analysis matches against all dataset sigs for coverage.
- **`rx_ns` is stamped after protobuf decode.** A burst read from one TCP segment is stamped about 1–2 µs apart. `ca_ns` is Shreder's clock, so rx − ca mixes network delay with clock offset.
- **Cross-machine numbers (AMS engine vs FRA recorder) are INFERRED.** At 22:09 PKT, chrony put AMS−FRA at −0.03 ms and the host-hub bracket put it at −0.17 ms. The bracket's worst-case bound is ±7.9 ms. FRA→AMS RTT is 6.8 ms.
- **Self-test leftovers:** FRA `/root/shreder/data/selftest_fetch/` (1.6 MB, fake data from the fetch self-test); not trial data.
- **Memory on FRA is the tight resource.** FRA has 3.9 GB, with 1.2 GB available; the two collect.py processes use about 2 GB. The recorder needs about 75 MB and the race 20–50 MB. Moving the engine to FRA as well would make memory tight.

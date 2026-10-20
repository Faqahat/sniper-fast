# FIX2: landing fixes for the pump.fun sniper (2026-10-19, ~15:50–17:20 UTC)

**Zero cost only.** `--live` was never passed, no `live_*.sh` was run, and no valid transaction was sent. The only sends were junk that providers reject, `simulateTransaction`, `--paper-trade` and `--junk-fanout`.
- Wallet FRZh63L6…: **0.244412778 SOL before and after** (USDC 0.0001 unchanged; 22 token accounts unchanged). Files: `wallet_before.json`, `wallet_after.json`.
- Keys and `.env` were not printed. The new Harmonic keypair is only read by the engine.
- `/root/sniper-final`, `/root/sniper-fast` and every `live_*.sh` are untouched (`live_final.sh` md5 c5c110e6).
- I killed only my own PIDs.

## What was built
- Work copy: `/root/sniper-final2` (`cp -a /root/sniper-final`).
  - Binary: `target/release/snipe_engine`, md5 `0c7eef20…`, also saved as `/root/fix2/snipe_engine.b3`. The paper run used `snipe_engine.b1`; its gate code is identical.
  - Diff: `/root/fix2/fix2.patch`. Originals are in `/root/fix2/orig/`. New file: `src/fast_huff.rs`, the HPACK Huffman table copied from the h2 crate (MIT).
- **Every change sits behind a flag or config. Without the new flags the engine is unchanged.**

| # | Flag / config | What it does |
|---|---|---|
| 1a | `/root/fix2/close_leaders_5ms.txt` (`close5.py`) | Leaders of epochs 1062 + 1063 → gossip / TPU / TPU-QUIC IPs → ICMP min RTT. 190 leaders <5 ms cover **33.7%** of slots; the old 20 ms list covered 60.9%. Only 2% of slots had no reply. Close slots by client: Harmonic 48%, Jito-Solana 45%, Firedancer 27%, BAM 17%. Variant: `close_leaders_12ms.txt` (346 leaders, 64% of slots; adds Amsterdam / London). Per-leader data in `leader_rtt.json` |
| 1b | `--close-leaders` | Already applied before `race.add`, so before prepare and fire on the fast-send / race-early path. Verified in the dry run: 129 far launches skipped and every fire went to a close leader. In `--paper-trade` it is now applied at the decision, with one `GATE` line per decided launch |
| 1c | `--max-create-ms X` (`--max-create-ms-unknown pass\|skip`, default skip; `--log-create-poh`) | The create's in-slot time on the leader's PoH clock. It comes from the shred walk (`feeds::poh_index`, DZ feeds; needs `--race-glued`), with the erpc arrival as fallback. Checked when the race decides. Coverage was 1584/1584 creates (all from `poh-index`) |
| 2 | send kind `harmonic-bundle` | Public JSON-RPC `sendBundle` `[[b64],{"encoding":"base64"}]` on the fast path (own HTTP/1.1 connection) and the slow path. The copy must carry a CU price (Harmonic's tip = the priority fee; no tip account). **With `auth_keypair`**: authenticated `SearcherService.SendBundle`, Jito-style login with role **3**, using `/root/.harmonic-searcher-auth.json` (pubkey 8C1hako7…). A failed login is logged (`HARMONIC AUTH FAILED`) and the path falls back to JSON-RPC; it never blocks other paths. A stale token also falls back |
| 3a | `--jito-poll` | `getInflightBundleStatuses` at +0.5, +2 and +10 s, `getBundleStatuses` at +2 and +10 s, and the stream verdicts **with their detail and decoded error code**. All block-engine JSON-RPC calls are spaced ≥1.1 s apart. Output: `JITO-POLL` lines and `jito_poll` records. `JITO-RESULT` now carries the detail too |
| 3b | (always, jito-h2) | The HTTP/2 trailers are now HPACK-decoded, so refusals read e.g. `rejected grpc-status=3 grpc-message=Transaction had serialization error…` instead of "no message". Every other provider's full error body was already in `FAST-ACK` / the send log |
| 3c | `--landed-via` (`--landed-via-probe`, `--jito-poll-probe` = zero-cost checks) | After a buy lands, bundles.jito.wtf is queried at +8, +30 and +90 s. Result: `our-jito-bundle`, or `other-bundle` with its tx count, tippers and tip (a 2-tx bundle = the Helius Sender wrapper), or `no-jito-bundle` (a non-bundle path; on a Harmonic leader that includes harmonic-bundle) |
| 5 | route string | `bam=` and `jito=` without helius (in `live_final2.sh`) |
| 6 | `--sell-robust`, `--sell-retries N`, `--sell-retry-s S`, `--strict-balance` | **Late landing:** a buy not seen within the land poll is watched for 45 s more, by signature and by ATA. **Balance read:** a token-balance read of 0 or an error is re-read 8× over 2 s; if it is still unreadable on a successful buy, the engine sells `min_tokens_out` without closing the ATA. **Sell retry:** a sell not seen in S s, or failed, is re-sent for the remaining balance, up to N times. **Drain:** the end-of-run drain is extended to match. **Strict balance:** refuses to start without a start balance and prints it (review findings 1–4) |

**Config:** `/root/fix2/final2_landing.toml` = `final_landing.toml` + `[[send]] harmonic-bundle` (url `https://fra.be.harmonic.gg/api/v1/bundles`, `auth_keypair`, 1/s).

## Verification (zero cost)

**PoH estimate vs chain** (`pohval.py`): 220 random creates from the paper run. Truth = (non-vote index + 0.5) / non-vote count × 217 ms.

| measure | result |
|---|---|
| error (engine − chain) | median **+2 ms**, mean +7 ms |
| abs(error) | **p50 9 ms**, p75 20, p90 41, p95 56 ms |
| correlation | 0.89 |
| gate agreement with chain | X=130: 89%, **X=150: 93%** (11 wrong skips, 4 missed late), X=170: 92% |

- **Recommended X = 150.** Caveat: the engine scales PoH to 217 ms per slot (getRecentPerformanceSamples). Same-leader spacing is 203.5 ms, so 150 ≈ 140 ms of real time. That matches the jitolate "first ~140 ms" limit.

**Paper run** (`run/paper_pfx1.log`): 30 min, exact rule-#2 filters + both gates.
- 10 rule-#2 decisions: 3 skipped far, 3 skipped late, **4 fired**.
- `verify_r2b.py`: **4/4 fires pass rule #2 on chain, and all 10 decisions pass on chain. 0 mismatches.**
- 0 panics.

**Junk dry run** (`run/dry_dfx1.log`): 20 min, exactly `live_final2.sh`'s flags plus `--junk-fanout`; harmonic-bundle on the harmonic route.

| check | result |
|---|---|
| fires | 4 (129 far skips, 3 late skips) |
| panics | 0 |
| HTTP 429 | **0, except harmonic-bundle** (2/2 refused "rate limited") |
| decision → first write | **p50 69 µs, p99 103 µs** (n=4) |
| detection → first write | p50 3.0 ms (the glued-run wait) |
| wallet | unchanged |

Per-path junk acks:

| path | ack |
|---|---|
| jito-bundle | 1.0–2.0 ms, with the decoded grpc-message |
| nozomi | 0.5–1.7 ms |
| harmonic-bundle | 0.5–1.8 ms (429) |
| staked-rpc | 5.9–7.3 ms |
| landx | UDP, no reply |

- `JITO-POLL` ran at +0.5, +2 and +10 s on every fire, against the probe ids (old final1 bundles): HTTP 200, `Invalid` (outside the 5-min window).
- **Kernel trace** (`proof.py dfx1`, bpftrace): **0 network writes or connects between detection and the first send write** in all 4 windows; the first write was on the event-loop thread every time.

**Attribution probe** on old final1 signatures:

| tags | result |
|---|---|
| 16, 48 | `our-jito-bundle` |
| 6, 44 | `other-bundle` 2-tx, tip 3,013,000 (the Helius wrapper) |
| 7, 50 | `no-jito-bundle` |

All six match the jitolate table.

**Harmonic:** junk `sendBundle` returned `-32097 rate limited` (HTTP 429) on every request.
- This held from 2 IPs, for JSON-RPC and the public gRPC `BundleService` (grpc-status 8), and for fra, ams and lon. It never lifted over 75 min (`harmonic_poll.log`, every 5 min).
- The authenticated login was attempted with role 3 and got `Pubkey not whitelisted` → fallback.
- So "accepts our format" cannot be shown until we are whitelisted. **harmonic-bundle is OUT of the live route** (`ROUTES`). `ROUTES_HB` in `live_final2.sh` puts it first on Harmonic leaders once the owner confirms the whitelist.

## #4: Jito "would-fail" (tags 72, 110)
- **Cause:** the block engine simulated our buy against state that did not yet contain the creator's create, which only exists in the leader's unfinished bank.
- **Ruled out:**
  - min_out: both txs later landed `ok=true` at a higher price via other paths;
  - account locks: a lock conflict is reported as a lost auction, not a simulation failure;
  - blockhash: a confirmed hash ≤300 ms old.
- **Measured** (`statelag.py`, 159 creates): an RPC node's processed state shows the new mint only **255 ms (p10 237, p90 285) after our detection**, for near and far leaders alike. Any replay-based simulator is that far behind; we send about 3 ms after detection.
- **Both would-fails were BAM leaders 149 ms away.** There the Frankfurt block engine's view of the leader's slot is furthest behind. None of the 6 near or Frankfurt fires got one.
- **Our side:** the <5 ms gate removes those fires. The detail and error code are now logged (`JITO-RESULT`, `JITO-POLL`), so the next run can confirm it. Do NOT add the creator's tx to our bundle: it is already executed, so the bundle would fail as a duplicate.

## Census and expected gain

| source | rule-#2 fires/h | near leader | both gates (X=150) |
|---|---|---|---|
| earlier runs (`census.py`: 6 runs, 1.43 h, 56 fires; chain truth) | 39/h | 12.6/h (32%) | **10.5/h (27%)** |
| this paper run | 20/h | 70% | 8/h |
| this junk run | — | — | 12/h |

- X=130 gives 9.1/h; X=170 gives 11.2/h.
- The 12 ms list would roughly double the near share. It adds Amsterdam / London leaders 6–12 ms away; tag 44 (BAM, 31 ms) did land in S as first outsider.

**Expected landing for fires that pass both gates:**
- **Same slot:** about 50% from final1 (2/4 near + early fires landed in S: tags 16 and 128). The bundle-tick mechanics allow up to ~75% when the path works.
- **First outsider, given same slot:** final1 2/3. RACE obs shows no outsider before +35–50 ms on 47–60% of gated launches (`gain.py`).
- **So ≈25–30% of gated fires should land in S as first outsider**, against 20% of all final1 fires.
  - About 70% of fires, the ones that were doomed (far or late), now cost nothing.
  - Absolute rate: ≈3 such landings per hour (10.5 × 0.28).
- **Caveat: n is small (10 live fires).** The next live test is the real measurement.
- Biggest remaining levers:
  - Harmonic whitelisting (27% of slots, 48% of close slots);
  - the 12 ms leader list;
  - Alpenglow on 10-21, which changes BAM and the PoH ticks. Re-validate the create-ms gate after it.

## Live script (NOT RUN)
- `/root/lat/live_final2.sh` (mode 644, md5 0beeb4ff) = `live_final.sh` with:
  - the arbx-final2 binary and `final2_landing.toml`;
  - `--close-leaders /root/fix2/close_leaders_5ms.txt --max-create-ms 150`;
  - `--sell-robust --sell-retries 2 --sell-retry-s 4 --strict-balance --jito-poll --landed-via`;
  - ROUTES without helius on bam/jito, and harmonic-bundle left out.
- Same caps: 17 buys / 0.017 total / 0.170 kill switch / cu 105k / 90 min / 2 in flight.
- At about 10 fires/h, 90 min gives about 15 buys.
- Before running it, stop all other processes.
- The owner's go is needed.

## Files (`/root/fix2`)
- **Scripts:** `close5.py`, `pohval.py`, `census.py`, `gain.py`, `statelag.py`, `proof.py`, `wallet.py`, `probes.sh`, `dry_fix2.sh`, `paper_fix2.sh`, `harmonic_poll.sh`.
- **Outputs:** `close5.out`, `census_old.txt`, `census_rows.json`, `pohval_pfx1.txt`, `verify_pfx1.txt`, `statelag.out`, `probes.out`, `harmonic_poll.log`, `run/` (logs, send logs, traces, `net_dfx1.txt`).

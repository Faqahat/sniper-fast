# LAT: send side, latency and multi-path (2026-10-19)

**Zero-cost only.** Nothing was sent live and `--live` was never passed. The probes used were:
- pings, keep-alive round trips, and undecodable 4-byte "transactions" that every provider rejects;
- one `simulateTransaction`;
- the old logs, plus on-chain data that was already collected.

Keys and `.env` were untouched. `/root/arbx-fast`, `/root/arbx-merge` and `/root/race` were not modified.

- **Working copy:** `/root/arbx-lat`.
  - Binary: `target/release/snipe_engine`, md5 `36c4fadb…`, built 10:03 UTC, BUILD_EXIT=0.
  - Source diff against arbx-merge: `/root/lat/lat.patch`. The original files are `mod.rs.orig` and `snipe_engine.rs.orig`.
- **Everything else** (scripts, logs, data) is in `/root/lat/`.

## TL;DR

1. **The engine itself is not slow.**
   - Build plus sign takes 0.27–0.35 ms.
   - Every Frankfurt path answers on a warm connection in 0.9–1.4 ms (staked-rpc 2.7 ms).
   - The fan-out reaches all paths within 0.03–0.44 ms of each other.
   - The ~45 ms "we land late" is the **path and the leader's scheduler**, not our network.
2. **Helius alone was the wrong path for most leaders.**
   - On 9,848 outside buys in the create slot, the share landing ≤25 txs behind the create was:

     | leader client | Helius | Jito-tipped |
     |---|---|---|
     | BAM | 5% | 38% |
     | Harmonic | 1% | 25% |
     | Jito-Solana | 13% | 19% |
     | Firedancer | 5% | 24% |

   - The leader client matters more than the leader's distance from us. Even with leaders <3 ms away, we landed in the create slot only 28% of the time.
3. **Built (all flags default off):**
   - one-signature multi-path fan-out with every path's tip in the same tx;
   - per-leader-client routing;
   - a per-path send log with Jito bundle results;
   - a DNS cache;
   - a Jito keep-alive that no longer burns bundle rate tokens;
   - LandX UDP sent twice;
   - a Gate B early decision (`--race-early`: **rx→fire 4.3 → 0.4 ms**, same selection);
   - two zero-cost test modes, `--ack-probe` and `--junk-fanout`.
4. **The landing config prepared overnight could never have started.** `probe_landing.toml` failed on two counts: a TOML parse error (`region`), and the engine's clear-text-secret refusal for astralane, speedlanding and landx. The new `/root/lat/lat_landing.toml` starts; all 6 paths build and warm.
5. **Expected result of the one live test** (other wallets' rates, weighted by the leader mix of the next 20k slots):
   - Before: about 6% of buys land at ≤25 txs (Helius only).
   - After: **about 25–28%** (best path per client).
   - Judge it per leader class with `lat_measure.py` (section 7).

---

## 1. Problems found, and what was fixed

| # | Problem (evidence) | Impact | Fix in `/root/arbx-lat` | Before → after (zero-cost) |
|---|---|---|---|---|
| P1 | **Single path, and the wrong one for most leaders.** Helius reaches d≤25 for 5% (BAM), 1% (Harmonic), 13% (Jito-Solana) and 5% (Firedancer) of buys. Jito-tipped buys: 38/25/19/24%. LandX 24% on BAM (§2.4) | We land d≤25 on 0 of 42 live fires | `--multi-send` and `--route-by-client` (§4) | 1 path → 3–4 paths per buy, picked by the leader's client |
| P2 | `--also-send` handled only 2 paths, joined inside one task | No N-way fan-out, no per-path timing | Each path sends on its own task. The buy proceeds on the **first** accept; each path logs `SEND-ACK t_off_us ack_ms` and a send-log line | Paths start 0.03–0.44 ms apart (p90). A slow or dead path no longer delays the land poll |
| P3 | **`probe_landing.toml` (the landing-test config) cannot start**: `unknown field region` (TOML error), and `config::cleartext_check` bails (even in lenient mode) on astralane `http://…${ASTRALANE_KEY}`, speedlanding `http://…${SPEEDLANDING_KEY}` and landx `udp://` + `token_env` without `no_tls_endpoint` | The planned landing test would have died at start | `/root/lat/lat_landing.toml`: `region` removed, astralane on https, landx marked UDP-only per its docs, speedlanding dropped | Before: parse error. After: 6 paths built and warm (`ackprobe_after1.txt`) |
| P4 | **The Jito keep-alive spent bundle rate tokens.** `Ping::Tips` called `budget.try_now()`, which **takes** one of the jito-bundle path's 2/s tokens, every 2 s | A buy right after a keep-alive could be refused locally | jito-bundle keep-alive every 15 ticks (30 s). The gRPC channel already sends HTTP/2 PINGs every 10 s, which is what keeps it warm. `JITO_KEEPALIVE_TICKS` overrides | 30 GetTipAccounts calls/min → 2/min. Warm RTT unchanged: 1.1–1.3 ms |
| P5 | **Jito's own limit: "1 per second for txn requests"**, burst about 3 (measured: the 4th junk `sendTransaction` within 200 ms got 429). `getTipAccounts` and `getHealth` do **not** count (`jito_rl.txt`) | Sending jito-bundle **and** jito-tx for each buy makes 2 txn requests to the same block engine, and a second buy within 1 s gets 429 | jito-tx removed from the fan-out. Jito is reached once per buy, through jito-bundle (gRPC, with our whitelisted key) | — |
| P6 | **DNS on every new connection.** reqwest resolves on each connect. Cold getaddrinfo takes 3.5–17 ms (helius 9.8, astralane 13.9, landx 17.2, jito 4.3, nozomi 4.0), and TTLs are short (constant-k 5 s, jito 19 s, nozomi 29 s, helius 61 s) | Any reconnect on the hot path pays DNS + TCP + TLS (Jito cold request **54 ms**, Nozomi 10 ms) | `send::DnsCache`: resolved once at path build, answered from memory, refreshed in the background every 60 s. Also 15 s TCP keepalive on the send clients | Reconnect DNS 3.5–17 ms → 0 ms |
| P7 | LandX UDP: one datagram, no reply ever (per its docs) | One dropped packet loses that path silently | 2 copies back to back (same signature, deduplicated). `LANDX_UDP_COPIES` overrides | 0.03 → 0.06 ms |
| P8 | `tokio::join!(getBalance, send_and_poll)` polled getBalance **first** | The balance request was built before the buy left | Send first | ~0.05–0.1 ms |
| P9 | **The Gate B decision waited out the full 3 ms window**, plus the 1 ms loop tick, even though the creator bundle is seen with the create | rx→fire 4.3 ms p50 (5.5 p90) | `--race-early`: pass as soon as the bundle condition, which only grows, is met. The selection is identical | Gate decided at 3.6–4.5 ms → **0.0–0.4 ms**. **rx→fire p50 4.29 → 0.41 ms** (p90 5.45 → 0.60): dry runs 1 vs 2 |
| P10 | No leader-client knowledge in the live engine | Cannot route | Leader book: getLeaderSchedule for this epoch and the next (one u32 per slot) plus getClusterNodes `clientId` (constant-k returns it; 3,905 nodes), refreshed every 10 min. When the create is in its leader's last slot, the next leader's paths are added | Next 20k slots: BAM 38%, Harmonic 27%, Jito-Solana 25%, Firedancer 7% |
| P11 | **The old route idea "Harmonic → Nozomi/Astralane" is contradicted by the data.** On Harmonic leaders d≤25 shares are: Nozomi 6%, Astralane 1%, Helius 1%, Jito-tipped 25%, **no tip 29%** | We would have routed Harmonic to the worst paths | Harmonic → jito-bundle + nozomi + staked-rpc (tipless) | — |
| P12 | **Helius keyless allows 1 req/s, and rejected requests count.** No `HELIUS_API_KEY` | Two buys within 1 s: the 2nd Helius copy is refused | The local 1/s guard stays. In a fan-out the other paths still carry that buy | — |
| P13 | constant-k staked-rpc `getHealth`: 1.4–5.8 ms with spikes of 19 and **173 ms**. Junk-ack p50 2.7, p90 4.8, max 7.7 ms | It is the slowest path | Kept for sells and as a free (tipless) extra buy path | — |
| P14 | Cloudflare-fronted endpoints are slow from here: Helius global 12–19 ms, 0slot `de` 14–42 ms | — | Not used. Regional `fra-sender` (1 ms) is used | — |
| P15 | **Detection, outside this task:** the deshred feeds (kaldera, turbo, haan) read a different quote account than erpc on **6 of 463 creates (1.3%)**: `pumpCmXq…`, `SPCX…`, `EPjF…` vs `sol`. kaldera arrives first about 99% of the time, so those launches are skipped as `skip_quote` | Up to 1.3% of launches lost, or misfires when erpc is first | **Not fixed.** Needs the detection agent: check the create_v2 account[16] index with ALTs on the deshred feed | `dry_report.py` lists them |
| P16 | The shred input: kaldera ≈ turbo-kaldera (tied: when behind, by p50 0.18–0.20 ms) < erpc (+1.7 ms) < haan (+8 ms). 463 creates, 4 feeds | The input side has no more than ~0.2 ms to gain from feeds we already have access to | Nothing to change. Optional: add turbo-kaldera for redundancy | — |
| P17 | tpu-direct: QUIC timeouts under Agave's 8 new conns/min/IP (det §16) | — | Stays disabled. Not in the fan-out | — |

Things measured and found **not** to be a problem:
- the keep-alive cadence (2 s is under every provider's idle timeout, §2.2);
- TCP_NODELAY (already on);
- HTTP/2 (TLS endpoints negotiate h2; plain-http regional ones are HTTP/1.1, with one warm connection each);
- build and sign: 0.27–0.35 ms;
- engine shred→send: <1 ms (det).

## 2. Measurements (from 77.223.215.155, Cherry/Limestone FRA)

### 2.1 Round trips (`net_before.jsonl`, `netprobe.py`)

ICMP / TCP connect / TLS handshake / warm keep-alive request (Python, which adds ~0.3 ms). Times in ms.

| endpoint | IP (DC) | ICMP | TCP | TLS (ALPN) | cold req | warm p50/p90 |
|---|---|---|---|---|---|---|
| helius `fra-sender` (http only, 443 refused) | 64.130.50.91 (TeraSwitch) | 0.47 | 0.62 | — | 4.5 | 1.00/1.17 |
| helius global (Cloudflare) | 104.18.x | 0.62 | 0.99 | 11.3 (h2) | 17 | 12.4/19.4 |
| jito frankfurt | 64.130.32/50.x | 0.47 | 0.65 | 6.4 (h2) | **54** | 1.51/1.79 |
| jito amsterdam / london / dublin | — | 5.9 / 11.4 / 18.9 | — | — | — | 7.0 / 12.4 / 20.0 |
| nozomi fra2 https / http | 64.130.47.135 | 0.48 | 0.59 | 4.7 (h2) | 9.7 / 5.7 | 1.04 / 0.96 |
| nozomi ams1 | — | 5.9 | — | — | — | 6.5 |
| landx fra1 http / fra3 UDP | 64.130.47.233 / 84.32.100.212 (Cherry) | 0.45 / 0.67 | 0.54 | — | 4.2 | 0.96 / (no reply) |
| astralane fr http / https | 185.191.117.97 | 0.68 | 0.80 | 5.7 (h2) | 4.9 / 9.7 | 1.25 / 1.41 |
| bloXroute germany | 64.130.40.x | 0.47 | 0.57 | — | 9.9 | 1.08 (401 without auth) |
| nextblock / blockrazor / node1 / flashblock / everstake | 64.130.x | ~0.47 | ~0.6 | — | 6–8 | 1.0–1.3 |
| lunar / speedlanding / bolt / falcon | 198.13.x | ~0.48 | ~0.6 | — | 5–15 | 0.8–1.1 (falcon 7) |
| 0slot de (Cloudflare) | 172.66.x | 0.53 | 0.83 | — | 34 | 14/26 |
| constant-k rpc / staked-rpc | 64.34.85.119 | 0.58 | 0.78 | 2.8 (h2) | 21 | 1.7 / 1.4–5.8 (spikes 173) |
| kaldera / turbo-kaldera / erpc shreds | 64.34.85.119 / 151.241.178.73 | 0.55 / 0.54 | 0.7 | 2.8 / 4.8 | — | — |

**Location.** Most providers sit in TeraSwitch FRA (64.130.x), ~0.47 ms away; LandX fra3 and Astralane are 0.67 ms. Frankfurt is the right region. Amsterdam is +5.4 ms and London +11 ms.

### 2.2 Keep-alive idle timeouts (`idle_before.jsonl`)

Measured by reusing one connection after idle gaps of 1…121 s. Provider docs [S20, S26, S41, S43] are cited in §3.

| provider | connection survives idle up to |
|---|---|
| **helius fra** | **10–16 s** (docs: ping when idle >5 s) |
| **nozomi fra2 TLS** | **16–31 s** |
| **speedlanding** | **16–31 s** (docs: 75 s) |
| nozomi fra2 http / landx fra1 / lunar | 61–91 s (Nozomi docs: 65 s) |
| bloXroute | 46–61 s |
| astralane / jito / staked-rpc | >121 s |

**The engine's 2 s keep-alive is inside every one of these: OK.** Do not raise it above ~8 s, because of Helius.

### 2.3 Engine numbers (zero cost)

- **WARM-ALL:**

  | path | ms |
  |---|---|
  | helius | 0.58–0.70 |
  | nozomi | 0.65–0.94 |
  | astralane | 0.93–1.12 |
  | jito-bundle | 1.14–1.31 |
  | staked-rpc | 1.09–3.27 |

- **`--ack-probe 12`** (junk to the real send handler, all paths at once; `ackprobe_after1.txt`):

  | path | p50 | p90 |
  |---|---|---|
  | nozomi | 0.86 | 0.93 |
  | helius | 0.91 | 0.98 |
  | jito-bundle (gRPC) | 1.16 | 1.50 |
  | astralane | 1.19 | 1.25 |
  | landx (UDP write) | 0.04 | — |

- **Multi-tip buy, all 5 tips (0.006 SOL), on a live curve** (HZaBf5…pump):
  - 1,042 bytes (limit 1,232);
  - every path's own tip check OK;
  - `simulateTransaction` err=null, **70,257 CU** (limit 90,000 plus 300 per extra tip).
- **Dry run of the live loop** (`--junk-fanout`, 19 min, 463 creates, 18 Gate B fires, `dry_dry1.log`):
  - build + sign 0.35 ms;
  - routes: harmonic 6, bam 6, jito 4, fd 3;
  - junk ack p50:

    | path | ms |
    |---|---|
    | landx | 0.06 |
    | nozomi | 0.88 |
    | helius | 0.98 |
    | astralane | 1.35 |
    | jito-bundle | 1.38 |
    | staked-rpc | 2.73 |

  - fan-out start offsets p90 ≤0.44 ms.

### 2.4 Leader geography vs leader client (`geo_land.txt`, 9,848 outside OK buys in the create slot, plus our 42 live fires)

- **Our fires by the leader's RTT from us:** in the create slot 28% (<3 ms), 50% (3–12 ms), 38% (12–40 ms). **Distance does not explain our misses.**
- **Share landing d≤25, by sender × leader class:**

  | sender | BAM | Harmonic | Jito-Solana | Firedancer |
  |---|---|---|---|---|
  | Jito-tipped | **38%** | **25%** | **19%** | **24%** |
  | no tip | 13% | **29%** | 18% | 16% |
  | LandX | **24%** | 4% | 16% | 15% |
  | Helius | 5% | 1% | 13% | 5% |
  | Nozomi | 5% | 6% | 7% | 18% |
  | Astralane | 5% | 1% | 12% | 19% |

## 3. Research summary (full report with 61 sources: §Sources below)

- **Slots are ~200 ms now** [S1, S2].
- **Alpenglow activates at epoch 1064, ~2026-10-21 14:50 UTC**, and BAM nodes go into maintenance [S1–S4]:
  - ticks leave the shred stream (PoH-based lag metrics stop working);
  - **BAM leaders fall back to the Jito-Agave block engine**: our `bam` route (jito-bundle) still applies;
  - **run the live test before then**, or re-baseline after.
- **Jito** [S12, S13]:
  - Endpoints: `/api/v1/bundles` and `/api/v1/transactions`; `bundleOnly=true` gives revert protection.
  - Limit is 1 req/s/IP/region; we measured burst ~3, with keep-alive methods exempt.
  - Min tip 1,000 lamports; the tip must be **in the same tx** (uncle-bandit risk otherwise). 8 tip accounts. No tip account via ALT.
  - 50 ms auction ticks ranked by tip/CU. Tips do nothing on non-Jito leaders.
  - The BAM interval was tightened to 20 ms on 2026-10-13 [S2].
- **Helius Sender** [S10, S11]:
  - Regional endpoints are HTTP only; `/ping` does not count toward the limit.
  - Keyless: 1 req/s/IP, and rejected requests count. A key gives 50 rps.
  - Sender Max (0.001 SOL) uses every pathway including Jito and Harmonic. `swqos_only` minimum is 0.000005.
  - The tx needs both a tip and a `setComputeUnitPrice`.
- **Nozomi** [S16–S22]:
  - fra2 direct; plain http is fastest; the `sendBatch` binary path is the lowest-overhead one.
  - Min 0.001 SOL; **below it the tx is silently dropped**.
  - 5 rps per key. Ping `/ping`; idle timeout 65 s.
  - It forwards tips to Jito/Harmonic builders.
- **LandX** [S7, S23–S26]: fra3 is **on Cherry Servers** and UDP-only (12-byte key + raw tx, no reply). fra1 has HTTP. Min 0.001.
- **Astralane** [S9, S27–S29]:
  - `fr` gateway; raw-IP QUIC available.
  - Free tier: 0.001 minimum, 5 TPS, no bundles.
  - Recommends sending to the global edge **and** the nearest region.
- **Harmonic** [S50, S53]:
  - Validators run "FBA + priority fee" (50 ms batch auction), FIFO, or MREV.
  - **Its own bundle endpoint is `fra.be.harmonic.gg`: the tip is the priority fee, with no tip account.** This probably explains the 29% "no tip" fast lane on Harmonic.
  - Not wired yet (§8).
- **Agave scheduler** [S51]: priority = fee per requested CU, so **a lower CU limit raises priority**. Firedancer's pack scheduler is reward / cost.
- **Client id** [S54]: AgaveBam = 6, FireBAM = 12, Harmonic = 9/10/11. constant-k's `getClusterNodes` returns `clientId`, verified.
- **Shred input** [S5, S6, S58]:
  - **Jito ShredStream was shut down on 2026-09-05.** Jito points to **DoubleZero Edge**: $450–1,500/IP/month; claims −11.6 ms p50 vs ShredStream and −20.7 ms vs Turbine.
  - ERPC moved to UDP forwarding.
  - What we have now: kaldera ≈ turbo < erpc +1.7 ms < haan +8 ms (§P16).
- **Fast snipers** [S60]: e.g. `0xfnzero/sol-trade-sdk` sends one tx in parallel to 10+ relays and returns on the first accept, which is what we now do.
  - 4yFAz (landing study): sprays p90 45 txs per launch, 91% of them fail, with a high priority fee. Our single-signature fan-out gets the multi-relay part without his failed-tx cost.

## 4. What was built (flags; all default off; no flag = old behaviour)

| flag | what it does |
|---|---|
| `--multi-send a,b,c` | Every **buy** goes to all these paths at once. One signed tx, so it can land only once. It carries **one tip per tip family** (jito-bundle and jito-tx share one). The CU limit gets +300 for each tip beyond 2. Over 1,232 bytes, paths are dropped from the end. **Sells never fan out.** |
| `--route-by-client "bam=..;harmonic=..;jito=..;fd=..;agave=..;other=..;default=.."` | The paths per create-slot leader class, taken from the leader book. If the create is in its leader's last slot, the next leader's paths are added. |
| `--send-log FILE` | JSONL per path per buy: route, leader, client, `t_off_us`, `ack_ms`, ok, status, reply, tx bytes, tips. Plus one line per **Jito bundle result** (`processed@slot#index`, `rejected`, …), which shows whether Jito carried the landing. |
| `--race-early` | Gate B passes the instant its bundle condition holds. Same selection. |
| `--ack-probe N` | Zero cost: routing preview, the multi-tip buy built and simulated (`--mint`), then N rounds of junk to every routed path. |
| `--junk-fanout` | Zero cost: the whole live loop (feeds → gates → routing → real tx built, signed and **discarded**), with only junk sent. Refused together with `--live`. |
| `LANDX_UDP_COPIES`, `JITO_KEEPALIVE_TICKS` | Environment overrides (defaults 2 and 15). |

Logs:
- `SEND-FAN sig= route: slot= leader= client= paths= tips= bytes=`, one `SEND-ACK path= t_off_us= ack_ms=` per path, and `JITO-RESULT` after the land poll.
- Existing `FIRE`, `BUY` and `SELL` lines are unchanged, so `measure_land.py` still works.

**Distinct-signature spray (like 4yFAz): not built, on purpose.**
- Different signatures can **all** land, which means 2–N buys of the same token. That breaks the spend caps and doubles the exposure.
- The only safe version gives every variant the **same durable nonce**: one lands, and the rest fail the nonce check and are never charged. Each variant then carries only its own path's tip, so you pay one tip instead of N.
- The buy builder already takes a `nonce`. What's missing is an on-chain nonce account (a live tx) and a re-read of the nonce after every landing.
- Recommended **only** after the one-signature fan-out has been measured.

## 5. Zero-cost validation

1. **`--ack-probe`** (`ackprobe_after1.txt`):
   - all 6 paths built and warm;
   - routing preview correct;
   - multi-tip buy 1,042 B, every tip check OK, simulate err=null at 70,257 CU;
   - every path answered junk in ~1 ms.
2. **Paper smoke** (`paper_smoke1.log`, 6 min, `--paper-trade` with the Gate B flags + `--race-early`):
   - 315 DETECT lines, 5 Gate B passes decided at **0.0–0.4 ms** (before: 3.6–4.5);
   - 0 panics; the PAPER-TRADE RESULT printed.
3. **Junk fan-out dry runs** of the live loop:
   - `dry_dry1.log`: 19 min, without `--race-early`. 18 fires, rx→fire p50 4.29 ms.
   - `dry_dry2.log`: 25 min, with `--race-early`. See §5.3.

### 5.3 dry2 (with `--race-early`)

`dry_dry2.log`, 25 min, `--junk-fanout --race-early`, with the same routes as the live test:
- **659 creates, 24 Gate B decisions, 19 fires.** 0 panics, 0 HTTP 429s, every junk request answered.
- **Wallet unchanged:** 0.110818539 SOL at start and at end.
- **rx→fire: p50 0.41 ms, p90 0.60 ms** (dry1 without `--race-early`: 4.29 / 5.45 ms). The gate decided at p50 0.10 ms. Build + sign 0.38 ms.
- **Routes:**

  | route | fires |
  |---|---|
  | bam | 5 |
  | harmonic | 3 |
  | jito | 2 |
  | fd | 2 |
  | leader-boundary unions | 8 (e.g. harmonic+jito, bam+harmonic) |

- **Junk ack per path:**

  | path | p50 (ms) | p90 (ms) | note |
  |---|---|---|---|
  | landx | 0.07 | — | UDP write |
  | nozomi | 0.88 | 1.05 | |
  | helius | 1.12 | 1.40 | |
  | jito-bundle | 1.19 | 1.46 | |
  | astralane | 1.39 | — | |
  | staked-rpc | 4.75 | 9.8 | **max 95.7**: constant-k is spiky; harmless in a parallel fan-out, but it should never be the only path |

- Fan-out start offsets: p90 ≤0.19 ms.

## 6. Recommended multi-path config

- **Config:** `/root/lat/lat_landing.toml`.
  - Sends: staked-rpc (sells), jito-bundle 0.002, landx-fra3 0.001, helius 0.001 (1/s), nozomi 0.001 (5/s), astralane 0.001 (5/s, https).
  - Feeds: erpc + kaldera.
- **Routes**, from the §2.4 data (paths in order):

| leader class (share of slots) | paths | tips (SOL) | best single-path d≤25 |
|---|---|---|---|
| bam (38%) | jito-bundle + landx-fra3 + staked-rpc | 0.003 | Jito 38%, LandX 24% |
| harmonic (27%) | jito-bundle + nozomi + staked-rpc | 0.003 | Jito 25%, no-tip 29% |
| jito (25%) | jito-bundle + landx-fra3 + helius + staked-rpc | 0.004 | Jito 19%, LandX 16%, Helius 13% |
| fd (7%) | jito-bundle + astralane + nozomi + staked-rpc | 0.004 | Jito 24%, Astralane 19%, Nozomi 18% |
| agave | helius + nozomi + staked-rpc | 0.002 | no Jito on vanilla Agave |
| other / default | helius + nozomi + landx-fra3 + staked-rpc / jito-bundle + landx-fra3 + helius + staked-rpc | 0.003 / 0.004 | — |

- **Priority fee: 30M µlamports/CU × 90k CU = 0.0027 SOL** (was 100M = 0.009).
  - On 7k buys there was no monotonic gain above 10M; the d6–25 lane's median is 0.05M; Jito, BAM and Nozomi order by the tip.
  - This frees budget for the tips.
- **Sells:** `--sell-path staked-rpc` at 1.5M (never fanned out, never Helius).

## 7. THE ONE LIVE LANDING TEST (owner approves and runs it; I did not)

**Command:**
```
bash /root/lat/live_lat.sh lat1
```

It runs `/root/arbx-lat/target/release/snipe_engine --snipe-once --concurrent --live`:
- Gate B: `--uri-blacklist --min-dev-buy 500000000 --max-dev-buy-sol 8 --dev-from-cap --race-gate --race-min-dev-sol 3 --race-min-bundle 2 --race-bundle-ms 3 --race-max-name-len 12 --race-pros /root/race/pros.json --race-early`
- Size and fees: `--spend-lamports 1000000` (0.001 SOL ≈ $0.10) `--fill-cap 2.5 --cu-price-micro 30000000 --cu-limit 90000 --sell-cu-price-micro 1500000 --land-poll-ms 100`
- Caps: `--max-sol 0.0015 --max-total-sol 0.010` (= **10 buys max**, then it stops firing) `--max-loss-sol 0.075` (balance kill-switch) `--max-inflight 2 --minutes 90`
- Paths: `--send-path helius --sell-path staked-rpc --route-by-client "<§6 routes>" --send-log /root/lat/sends_lat1.jsonl --config /root/lat/lat_landing.toml`
- Log: `/root/lat/live_land_lat1.log`

Before starting:
- stop paper/dry engines and builds (CPU, and the shared Helius keyless budget);
- run it **before 2026-10-21 14:50 UTC** (Alpenglow / BAM maintenance) so it compares with the Oct 18 baseline;
- 10 buys should take ~15–25 min at ~57 Gate B fires/h (dry run).

**Cost:**
- Per buy: ≈0.0027 priority + 0.003–0.004 tips (all tips are paid whichever path lands, because one tx carries them all) + ~0.0002 sell/fees/slippage ≈ **0.006–0.007 SOL**.
- **About 0.065 SOL for 10.** Wallet: 0.1108 SOL.
- A fill-cap revert costs only the priority fee (and nothing at all via Jito: the block engine drops a failing bundle).

**Measure:**
```
python3 /root/lat/lat_measure.py /root/lat/live_land_lat1.log /root/lat/sends_lat1.jsonl
```
- It prints `measure_land.py`'s table (slot, position, creator bundle, outsiders ahead, gap vs the post-bundle price).
- Then, per buy: route, every path's ack (`!REFUSED` marks refusals) and the Jito bundle result.
- Then, **by leader class**: in-S, d≤25, FIRST outsider, median position and gap.
- Also: `grep -E "SEND-FAN|SEND-ACK|JITO-RESULT|429|REFUSED|TX-SIZE" /root/lat/live_land_lat1.log`.

**How to judge it** (n=10 is small, so read it per class and against the baseline):

| | baseline (Helius only, Oct 18, n=42) | pass |
|---|---|---|
| in S (same slot as the create) | 38% | ≥ 70% |
| d≤25 | **0%** | ≥ 2 of 10 (expected 25–28%) |
| FIRST outsider behind the bundle | — | ≥ 3 of 10 |
| median gap vs the post-bundle price | +2.8% (Helius) / +6% (typical) | ≤ +1% |
| refused / 429 buys | Helius 429s on sells | 0 buys with every path refused |

- **If BAM and Jito-Solana buys land d≤25 but Harmonic ones don't**, the next lever is Harmonic's own bundle endpoint (§8).
- **If no class improves**, the gap is reaction or input time (§8: DoubleZero), not the path.

## 8. Not done, and next levers (ranked)

1. **Harmonic bundles (`fra.be.harmonic.gg`, tip = priority fee).**
   - Harmonic is 27% of slots, and its "no tip" lane reaches d≤25 for 29% of buys.
   - Needs a new send kind: a JSON-RPC `sendBundle` without a tip account. Untested API, so it was not built today.
2. **Helius API key:** 50 rps instead of 1, with no 429 cascade. Free; the owner creates it.
3. **The P15 quote disagreement** (detection agent).
4. **Durable-nonce spray** (§4), after the fan-out is measured.
5. **Input side:** DoubleZero Edge (paid; claims −11.6 ms p50 vs ShredStream). Only if the live test shows a reaction gap after the path fix.
6. **After Alpenglow (10-21):** re-measure ordering by client. Ticks leave the shreds (PoH lag metrics), and BAM is in maintenance.

## Files (`/root/lat/`)

| file | what |
|---|---|
| `NOTES.md` | this file |
| `lat.patch` | the source diff |
| `lat_landing.toml` | live config |
| `lat_dry.toml` | dry config, with 2 extra feeds |
| `live_lat.sh` | **LIVE**, owner only |
| `lat_measure.py` | scorer |
| `ackprobe.sh` | zero-cost probe |
| `dry_fanout.sh`, `dry_report.py` | zero-cost dry run and its report |
| `paper_smoke.sh` | paper smoke run |
| `netprobe.py`, `idleprobe.py`, `jito_rl.py`, `geo_land.py` | probes and analysis |
| `net_before.jsonl`, `idle_before.jsonl`, `jito_rl.txt`, `geo_land.txt`, `geo_rtt.json` | probe results |
| `ackprobe_after1.*`, `dry_dry1.log`, `dry_dry2.log`, `sends_dry*.jsonl`, `paper_smoke1.log` | run outputs |
| `snipe_engine.lat_v1` | the binary before `--race-early` |

## Sources

- [S1] https://solana.com/upgrades/alpenglow
- [S2] https://cryptobriefing.com/jito-bam-upgrade-cuts-bundle-delays/
- [S3] https://www.bankless.com/read/news/alpenglow-is-coming-to-solana-mainnet-next-week
- [S4] https://solanacompass.com/news/jito-details-bams-alpenglow-plan-maintenance-mode-for-all-mainnet-nodes-no-firebam-during-the-transition
- [S5] https://docs.jito.wtf/lowlatencytxnfeed/
- [S6] https://erpc.global/en/news/2026/08/21/erpc-solana-shreds-lineup-udp-forwarding-20260821/
- [S7] https://landx-1.gitbook.io/landx-docs/region-endpoints.md
- [S8] https://docs.blockrazor.io/transaction-submission/transaction-sending/solana/endpoint.md
- [S9] https://astralane.gitbook.io/docs/low-latency/endpoints-and-configs.md
- [S10] https://www.helius.dev/docs/sending-transactions/sender
- [S11] https://www.helius.dev/docs/sending-transactions/sender-max.md
- [S12] https://docs.jito.wtf/lowlatencytxnsend/
- [S13] https://chainstack.com/jito-explained-bundles-tips-mev-solana/
- [S14] https://bam.dev/docs/
- [S15] https://bam.dev/docs/bam/bam-overview/
- [S16] https://use.temporal.xyz/nozomi/endpoints.md
- [S17] https://use.temporal.xyz/nozomi/transaction-submission-api-v2.md
- [S18] https://use.temporal.xyz/nozomi/batch-send.md
- [S19] https://use.temporal.xyz/nozomi/transaction-submission-quic.md
- [S20] https://use.temporal.xyz/nozomi/keeping-your-tcp-connection-alive.md
- [S21] https://use.temporal.xyz/nozomi/tipping-and-faq.md
- [S22] https://use.temporal.xyz/nozomi/faq.md
- [S23] https://landx-1.gitbook.io/landx-docs/udp-binary-tx.md
- [S24] https://landx-1.gitbook.io/landx-docs/basic-rules.md
- [S25] https://landx-1.gitbook.io/landx-docs/tip-addresses.md
- [S26] https://landx-1.gitbook.io/landx-docs/keep-alive.md
- [S27] https://astralane.gitbook.io/docs/low-latency/submit-transactions/send-in-binary.md
- [S28] https://astralane.gitbook.io/docs/low-latency/submit-transactions/keep-alive-healthy-ping.md
- [S29] https://astralane.gitbook.io/docs/low-latency/send-txn-fee-tiers.md
- [S31] https://0slot.trade/docs.php
- [S32] https://docs.bloxroute.com/solana/trader-api/introduction/regions
- [S35] https://docs.nextblock.io/getting-started/quickstart.md
- [S41] https://docs.hellomoon.io/reference/lunar-lander
- [S43] https://speedlanding.trade/docs.html
- [S50] https://docs.harmonic.gg/searchers/harmonic-bundles
- [S51] https://forum.solana.com/t/a-practical-overview-of-scheduler-implementations-in-solana-validators/4803
- [S53] https://harmonic.gg/validators
- [S54] https://raw.githubusercontent.com/anza-xyz/agave/master/version/src/client_ids.rs
- [S58] https://doublezero.xyz/jito-shredstream
- [S60] https://github.com/0xfnzero/sol-trade-sdk
- [S61] https://docs.rs/reqwest/latest/reqwest/struct.ClientBuilder.html

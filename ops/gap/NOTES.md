# GAP: where the create → our-buy time goes, and the feed race (2026-10-19)

Zero cost only: subscribe-only feeds, pcap of our own inbound UDP, pings, RPC reads, `--paper-trade`. Nothing sent,
never `--live`. Keys/.env untouched (tokens read by NAME only, never printed). /root/sniper-fast, /root/sniper-merge,
/root/race, /root/sniper-lat not modified. Own copy `/root/sniper-feed` (copied 10:53 UTC with no cargo running; source
backup `/root/gap/arbx-lat-src-backup.tgz`). Clock: chrony stratum 3, offset 0.16 ms, RMS 0.13 ms.

## FINAL ENGINE STATUS (14:20 UTC): `/root/sniper-final` + `/root/lat/final_landing.toml` + `/root/lat/live_final.sh`
(not run) validated zero-cost: rule #2 decisions match the chain 47/47, decision → first send write p50 59 µs /
p99 181 µs, 0 RPC writes on the buy path (kernel trace). Details §8; stop list in READY.txt.

## VERDICT (measured; DoubleZero leader-published shreds as the near-direct reference)

Median of our 16 same-slot live buys: **48.5 ms** (PoH) from the create to our buy. Split (`race/decomp.txt`):

| part | median ms | whose | evidence |
|---|---|---|---|
| **Seeing the create late: 14 ms in total** | | | |
| leader broadcast batching (create recorded → its shreds leave the leader) | **11** (bam 7.4, jito 11.2, harmonic 12.2, fd 19.9) | leader; every shred reader pays it | FEC-set gaps on DZ's **leader-published** stream, time-weighted (`race/residual_dz.txt`); constant-k stream gives the same 10.1 |
| transit leader → us, leader-direct path (DZ) | RTT/2 + ~0.4 (≈0.7 for Frankfurt leaders, ~3–7 for Amsterdam/London) | physics | leader RTTs (geo_rtt), DZ tunnel peer RTT 0.38 ms min |
| extra delay of our feed then (Kaldera) over leader-direct | **1.6** (p90 3.6) | **ours (feed choice)** | dz-leader beats Kaldera by 1.5–1.7 ms at every leader distance and client (`lead_by_rtt.txt`) |
| our processing (Oct 18 build) | 0.4 (now <0.1) | ours | lat notes |
| **After we send: ~32–34 ms** | | | |
| us → provider | ~0.5 | ours (path) | ack RTT 0.9–1.4 ms |
| provider → leader + leader queue/scheduling/auction | **~32** (remainder) | path/route/tip; leader side | Jito BE 50 ms auctions, BAM 20–25 ms, Harmonic 50 ms |

- **Seeing late ≈ 14 ms, of which only ~2 ms was ours** (1.6 ms feed + 0.4 ms engine); ~11 ms is the leader's own
  batching and ~1–5 ms is distance. **After we send ≈ 32–34 ms** — the bulk of the gap is downstream of our send.
- So **the owner's challenge is answered with data: all feeds are NOT equally late by tens of ms.** Leader-published
  DZ shreds arrive only 1.5–1.7 ms before Kaldera (3 ms before erpc) for leaders anywhere; a "Turbine-late" feed would
  trail the leader feed by 10–20 ms, and ours don't (the one that does is DZ's own EU retransmit group: 14 ms behind).
- Error bars: the 48.5 ms total comes from block position (d × 203.5 ms / non-vote txs: assumes txs spread evenly
  in the block; ±10–20 ms per buy, less at the median). Batching is an average per client (±5 ms per buy; it is why
  one Firedancer buy shows a negative remainder). Transit uses RTT/2 (±0.5 ms in Frankfurt). The PoH cross-check
  (`poh_dz.py`) can't pin an absolute zero: PoH↔wall mapping scatters ±25 ms per create, median −6 ms vs the slot's
  first shred (the first shred is itself batched). The per-feed offsets are constant within a slot: lead on creates
  (mid-slot) ≈ lead on the slot's first shred (Kaldera 1.5–1.7 vs 1.4–2.6 ms; erpc 3.1–3.4 vs 2.5–3.1 ms).
- What that means: the feed side has **~1.6 ms** left to win (DZ leader shreds vs Kaldera), the engine **~0.3 ms**;
  the **~32 ms after the send** is where a fix must come from (route by leader client / Jito-BAM bundle path /
  Harmonic bundles: the lat agent's live test), plus the leader's own ~11 ms batching that nobody outside the leader
  (or its block builder) can avoid.

## TL;DR (feeds)
1. **DoubleZero Edge is now the fastest feed.** DZ (dz-leader + dz-retrans-eu, first arrival) is first on **87%** of
   creates, **+1.38–1.45 ms median vs Kaldera** (p90 +3.5), +2.9 ms vs erpc, +2.6 ms on each slot's first shred.
   On slots whose leader publishes to DZ (50% of creates), dz-leader leads Kaldera by **1.5–1.7 ms** at every leader
   distance (<3 ms … >100 ms) and client.
2. constant-k raw UDP (trial 11:07–12:08 UTC, then stopped sending): first on 75–83% of creates, +0.7–0.9 ms vs
   Kaldera. **Indirectly (both vs Kaldera): DZ ≈ 0.6 ms ahead of constant-k** at the median on creates, ~0.2 ms on
   slot first shreds.
3. **Recommended engine feed set: dz-leader + dz-retrans-eu (multicast) + Kaldera + turbo-Kaldera**, first arrival per
   mint (the engine already does this): 0 missed creates in the race (ALL), +1.4 ms vs Kaldera alone. Add constant-k
   UDP if it is bought (+0–0.5 ms on the 13% DZ doesn't win). dz-root carries no decodable data for us (0 creates);
   erpc is never first (≤1%) — keep only as redundancy. Engine paper smoke with DZ ran clean (`paper_pdz1.log`):
   DZ groups first on 77% of DETECTs, Kaldera median 1.5 ms behind the first.
4. Receive path (UDP): p50 0.08–0.11 ms kernel → create decoded; tail p90 0.9–1.3 ms, p99 5–6 ms from CPU contention on
   this 4-vCPU box. Busy-poll pinned to cpu 3 made it far worse (cpu 3 is taken by another agent's engine): don't.
5. A merged assembler for the three DZ groups (one socket, shreds of a data set from any group) gains nothing
   (earlier on 3.9% of creates by <0.04 ms p99): keep them as separate feeds.

## 1. Feed race (harness: /root/gap/feed_race.sh; reports in /root/gap/race/)

### DoubleZero Edge (dz1: 12:12–12:57 UTC, `race/dz1_10min.txt`, `race/dz1_now.txt`, `race/summary_dz1.txt`)
Interface doublezero1 (GRE, device fra-velia), UDP 7733, groups edge-solana-shreds 233.84.178.1 (`dz-leader`,
~130 publishing-validator sources), edge-solana-retrans-eu .12 (`dz-retrans-eu`, 3 sources), edge-solana-root .16
(`dz-root`). Harness kind `udp-multicast` (group/port/interface; or `groups = [...]` for one merged socket).

| creates (n=1,033 at 12:37) | first | lead vs Kaldera med (p10/p90) | vs erpc | misses |
|---|---|---|---|---|
| DZ (leader+retrans+root, first) | 86.7% of the time ahead | **+1.38** (−0.84/+3.51) | +2.91 | 8 (0.8%; mostly ALT-key filter artefacts) |
| dz-leader (only leaders that publish: 49% of creates) | 41.6% overall | **+1.60** (−1.14/+3.60) | +3.15 | n/a (coverage) |
| dz-retrans-eu | 42.8% | −3.5 (huge tail, p90 −27): fast on BAM, 9–10 ms late on Harmonic/FD | | 23 |
| ALL (DZ + Kaldera + turbo + erpc) | — | +1.40 (0.17/3.57) | +2.99 | **0** |

- Slot first shred (2,959 slots, 10 min): DZ +2.60 ms vs Kaldera (p10 0.64, p90 6.99), +3.87 vs erpc; dz-leader vs
  dz-retrans-eu tie (0.2 ms); dz-root 1.7 ms behind DZ.
- dz-leader lead by leader RTT (creates; median/p90): <3 ms: Kaldera 1.53/3.53, turbo 1.73/5.60, erpc 3.26/5.88;
  3–20: 1.67/3.67; 20–100: 1.50/3.97; >100: 1.63/3.29. By client: bam 1.79, harmonic 1.69, jito 1.32, fd 1.66
  (`race/lead_by_rtt.txt`).
- Merged socket (dz2, `race/summary_dz2.txt`): same as the min of the separate groups (ahead on 3.9% of creates,
  p99 0.04 ms).


### constant-k UDP vs the rest — creates

| run | creates | constantk first | constantk vs Kaldera med (p10/p90) | vs turbo-Kaldera | vs erpc | misses (constantk / erpc / Kaldera) |
|---|---|---|---|---|---|---|
| ck1 30-min (11:08–11:32) | 722 | 77.0% | **+0.74** (−0.36/+2.33) | +0.88 | +2.35 | 11* / 9* / 0 |
| ck2a (11:37–11:48) | 415 | 83.1% | **+0.90** (−0.19/+3.18) | +1.06 | +2.69 | 0 / 0 / 0 |
| ck2b busy-poll | see §4 | | | | | |
| ck3 | see below | | | | | |

\* 9 of constantk's 11 "misses" are also erpc misses: creates whose pump/mint-authority keys come through an address
lookup table, which the harness's static-key filter on raw feeds doesn't match (Kaldera resolves ALTs). They are not
feed misses. True constantk misses ≈ 2/722 (0.3%), matching the 0.34% of FEC sets that arrived with a data shred
missing (all 107 of them recoverable from code shreds; §3).

- All pump txs (417k): constantk first 75%, +0.89 ms vs Kaldera, +2.32 ms vs erpc.
- Each slot's FIRST shred (6,876 slots): constantk first 98%, **+2.42 ms vs Kaldera** (p10 0.74, p90 7.39), +3.62 vs erpc.
- By leader client (ck1, creates, constantk first / lead vs Kaldera): bam 70% / 0.51 ms, harmonic 78% / 0.92,
  jito 78% / 0.67, fd 89% / 1.64. By leader RTT and slot third: the same picture (0.5–0.9 ms).
- Kaldera ≈ turbo-Kaldera (tie, 0.06 ms). erpc is 1.5–1.6 ms behind Kaldera. Haan (+8 ms) was dropped.
- Provider `created_at` → our receive: Kaldera 2.5–2.7 ms median (ping 0.55 ms), i.e. ~2 ms of queueing inside
  Kaldera's deshred service, which raw UDP skips.

### COMBO (first arrival across constantk + Kaldera + turbo-Kaldera)
- ck1: 0 misses of 722 creates; +0.70 ms median vs Kaldera alone (p90 +2.29); vs constantk alone: identical at the
  median, ahead in 22% of creates by up to 0.5 ms (p90 0.49).
- ck2a: 0 misses of 415; +0.91 ms vs Kaldera.

## 2. Decomposition (first estimate, before DZ; superseded by the VERDICT table at the top)

The live baseline (race/NOTES "Landing study"): our same-slot buys landed 45–52 ms (PoH time) after the create; other
Helius buyers 56 ms; outside buyers 44–62 ms **whatever the leader's distance from us** (geo_land.txt §2: <3 ms
leaders 51 ms, >100 ms leaders 53 ms) — so the gap is not distance; it is batching at the leader and in the auctions.

| # | component | median ms | ours? | evidence |
|---|---|---|---|---|
| 1 | Leader: create recorded → its shreds broadcast (entry coalescing; Agave flushes up to 50 ms or ~2 FEC sets; Firedancer by size) | **~10** (time-weighted wait; bam 7.7, jito 9.1, harmonic 13.5, fd 16.1) | no — every shred reader pays it | pcap of 2.0M constant-k shreds, 31k FEC sets: gap between a slot's consecutive FEC sets p50 4.9, p90 21.5, p99 42 ms (`race/pcap_fec.txt`, `race/residual.txt`); same-leader first-shred spacing jitters ±23 ms (p10 177 / p90 222 ms around 203) |
| 2 | Leader → relays/Turbine → provider → us | ≥0.3 physical (FRA leader); +2.3 ms spread inside one FEC set (p50; p90 7.8) | **partly**: feed choice is worth 0.7 ms vs Kaldera, 2.4 ms vs erpc | FEC-set first→last shred spread; handover analysis (below) |
| 3 | Our receive path: kernel timestamp of the completing shred → create decoded | 0.08–0.11 (p90 0.9–2.0, p99 6–7 under build load) | **yes** | R lines, §4 |
| 4 | Engine: decoded → buy written to the send path | 0.4 (→ <0.1, other agent) | **yes** | /root/lat NOTES |
| 5 | Us → provider (Frankfurt) | ~0.5 one-way (ack RTT 0.9–1.4) | **yes** (path choice) | /root/lat NOTES |
| 6 | Provider → leader (relay hop; TPU or block engine) | 0.3–1 for FRA leaders; +one-way distance otherwise | path choice | geo |
| 7 | Leader queue: auction/batch + scheduler | **~25–35** (remainder) | only via route/tip/bundle | Jito block engine 50 ms auctions, BAM 20–25 ms batches, Harmonic 50 ms buffer [R3]; Jito-tipped buys reach d≤25 38% on BAM vs Helius 5% (lat §2.4) |
|   | **total** | **45–52** | **ours ≈ 2–4 ms** | |

**Handover check (constant-k first shreds, 6,876 slots, `handover.py`)**: a new leader's first shred reaches us
**+21.8 ms** later than a same-leader continuation when both leaders are <3 ms from us (n=138; +27–34 ms for
nearby pairs, +171 ms when the new leader is >100 ms away ≈ its RTT). That +22 ms is block propagation to the next
leader + replay + its first broadcast batch — i.e. even Frankfurt-to-Frankfurt the shred path is not ~1 ms; it is
dominated by batching and Turbine, which a co-located direct feed (§7) could cut.

Assumptions: PoH time of our landing is from the landing study (d × 217 ms / non-vote txs: assumes txs spread evenly
in the block); a tick is ~3.1 ms (200 ms slots since 2026-10-09; measured same-leader spacing 203.5 ms). The erpc
PoH envelope analysis (`poh_an.py`) found create entries arrive p50 13.8 ms after the slot's best (arrival − PoH)
envelope — consistent with the ~10 ms broadcast batching, but PoH is not exactly linear in wall time (hashing pauses
while recording; within-slot slope gave 190 ms vs 203 ms between slots), so the pcap number is the one to use.
An absolute leader→us delay cannot be measured without a leader-side clock; only the relative/batching parts are.

## 3. Misses: never arrived vs failed to deshred (pcap 11:18:25–11:23:25, 1.99M shreds)
- 31,050 FEC sets (all 32 data + 32 code). **107 sets (0.34%) had a data shred missing, all 107 recoverable from code
  shreds**; 3.5% of slots contain at least one. `sets_failed` = 0 (no parse failures). No kernel drops
  (RcvbufErrors 0, NIC dropped 0 — coordinator check).
- So constantk's real misses come from **our assembler not doing Reed-Solomon recovery** (it waits for the missing
  data shred forever), not from shreds that never arrived. RS recovery would also have made the data available
  earlier: all-data-in vs any-32-in: p50 0.10 ms, p90 1.34 ms, p99 2.5 ms.
- With the COMBO (Kaldera alongside) the miss rate is 0.

## 4. Receive path (constantk UDP; R lines; µs)
| run | stage | p50 | p90 | p99 |
|---|---|---|---|---|
| ck2a (normal; 2 cargo builds running) creates n=242 | kernel → recvmmsg returns | 42 | 899 | 5,941 |
| | queue inside the recvmmsg batch | 5 | 167 | 3,097 |
| | assemble + parse + decode | 23 | 95 | 533 |
| | **total kernel → create decoded** | **108** | **1,268** | **6,362** |
| ck2b (busy-poll, pinned cpu 3; another agent's engine is pinned to cpu 3) creates n=45 | **total** | 75 | **5,188** | **541,716** |
| ck3 (normal; other agents' engines running) creates n=337 | kernel → recvmmsg | 43 | 900 | 5,054 |
| | queue in batch | 5 | 157 | 892 |
| | assemble + decode | 15 | 55 | 179 |
| | **total** | **88** | **1,091** | **5,157** |
| DZ dz-leader (dz1, 5 UDP sockets + 2 other engines on 4 vCPUs) creates n=304 | **total** (kernel → decoded) | **51** | **1,338** | **13,793** |

- The receive-path TAIL (p90 ~1.1–1.3 ms, p99 5–14 ms) is CPU contention on this shared 4-vCPU box (other agents'
  engines, builds, my analyses); it is as large as DZ's whole lead. A dedicated box/cores for the live engine is the fix.
- **Busy-poll on a shared core is harmful here** (p99 0.54 s: the spinning thread and the other engine time-share
  cpu 3). Not recommended without an isolated core (`isolcpus`, which needs a reboot: owner's call).
- Effective lead after our decode (constant-k@dec vs Kaldera, ck3): +0.54 ms median (vs +0.78 on kernel time).
- A SCHED_FIFO receive thread was planned as the next A/B but constant-k stopped first; `chrt -f -p 10 <tid of the
  engine's feed-<name> thread>` is the zero-code way to try it (affects only that thread).

- The decode itself is already "earliest packet": the engine's assembler parses a data set as a stream and hands a
  transaction over the moment the data shred holding its last byte arrives; it never waits for coding shreds or the
  FEC set. So the cut is in scheduling (stage A), not in decoding.
- Box: KVM guest, virtio_net, 1 RX queue (IRQ on cpu 2, TX on cpu 3), GRO on, net.core.busy_poll/busy_read 0,
  rmem_max 4 MB (the harness uses SO_RCVBUFFORCE 128 MB).

## 5. Fixes applied (own copy /root/sniper-feed; nothing in arbx-lat touched)
- `src/bin/feed_race.rs`: the feed race harness (+ busy-poll/pin options, receive-path R lines, assembler gc).
- `src/feeds/udp.rs` (engine UDP feed, opt-in, default unchanged): `UDP_PIN_CPU=n` pins the receive thread,
  `UDP_BUSY_POLL=1` spins on non-blocking recvmmsg. Patch `/root/gap/udp_busy.patch`.
- Engine config with the constantk UDP feed: `/root/gap/probe_feed.toml` (= probe_shadow.toml + `constantk` udp
  feed with `allowed_src = ["64.34.85.119"]` + turbo-kaldera). Paper smoke `pf1`: §6.

## 6. Engine paper smoke (zero cost, `--paper-trade`)
- `probe_feed_test.toml` (constantk on a spare port, 1 min): config accepted by the engine's validator, feeds start.
- **`pdz1` (12 min, `probe_dz.toml` = probe_shadow.toml + 3 DZ multicast feeds + turbo-Kaldera)**: clean run, 585
  creates; first-arrival shares of DETECT: dz-leader 40%, dz-retrans-eu 37%, Kaldera 15%, turbo-Kaldera 7%, erpc 1%;
  Kaldera median 1.5 ms behind the first, erpc 3.0 ms. dz-root never delivered a create.

## 8. FINAL ENGINE for the owner's live test (/root/sniper-final) — zero-cost validation

**Build:** `/root/sniper-final` = `cp -a /root/sniper-lat` (speed agent's finished build md5 9e354927, flags
`--fast-send --jito-h2 --fast-presign --fast-derive --busy-poll --pin-core`), plus:
- the feed-race tool (`src/bin/feed_race.rs`); DoubleZero multicast needs no engine change (`kind = "multicast"` is
  native and was paper-smoked);
- **the race-gate bundle fix (`--race-glued`, below)**: `src/feeds/{mod.rs,shred.rs}` (slot-order index),
  `src/snipe.rs` (`bundle_legs`, `simulate_legs`, `PUMP_FEE_BPS = 125`), `src/bin/snipe_engine.rs` (RaceWatch).
  Originals in `/root/gap/final/orig/`. Every change is behind `--race-glued`; without it the engine is unchanged.
- Config `/root/lat/final_landing.toml` = lat_landing.toml sends + feeds dz-leader, dz-retrans-eu (multicast),
  kaldera, turbo-kaldera, erpc (backup). Live script `/root/lat/live_final.sh` (mode 644, **not run**).

### 8.1 Dry run `fin1` (15 min, `--junk-fanout`, exact live flags, PREREG_v2 #2, before the bundle fix)
- 7 fires (rule #2 is rare), every one junk-written to every routed path; wallet **0.310818539 SOL before and after**;
  0 panics, 0 HTTP 429; the only "errors" are the providers rejecting the junk tx (expected).
- **Decision → first send-path write: p50 69 µs, p99 92 µs (max 93)** (the engine's own trace, confirmed by bpftrace).
- Create detected → first send write: p50 3.86 ms, p99 4.79 ms — that is the 3 ms bundle window of rule #2
  (`--race-max-bundle-sol` disables `--race-early`), not processing.
- Feed first-arrival shares (546 creates): dz-leader 41%, dz-retrans-eu 37%, turbo-Kaldera 14%, Kaldera 6%, erpc 1%.
- busy-poll / pin-core 1: kept for the live run (the live run is to have the box to itself, see READY "STOP BEFORE
  LIVE"); measured harmful only when another process shares the pinned core.

### 8.2 Kernel-level proof: no network round trip between detection and the buy write
bpftrace on every `connect/write/writev/sendto/sendmsg/sendmmsg` of the engine (all threads, CLOCK_MONOTONIC), fd →
peer map from `ss` every second (`/root/gap/final/nettrace.bt`, `proof.py`, output `proof_fin1.txt`):

| fire | route | detect→decide µs | detect→first write µs | decide→first write µs | network writes/connects before the first send write |
|---|---|---|---|---|---|
| 23 | harmonic | 3,773 | 3,857 | 84 | none |
| 43 | fd | 3,204 | 3,273 | 69 | none |
| 51 | bam | 3,947 | 4,009 | 62 | none |
| 52 | jito | 3,418 | 3,456 | 38 | none |
| 82 | harmonic | 4,743 | 4,822 | 79 | none |
| 90 | harmonic | 3,586 | 3,679 | 93 | none |
| 100 | bam | 4,152 | 4,211 | 59 | none |

- **0 writes to rpc-frankfurt / staked-rpc / any non-send socket, 0 connects, in all 7 windows**; the first send write
  is always on the pinned event-loop thread (tid 809162). The RPC socket (fd 11, ~15 writes/s: the blockhash
  refresher) runs on other threads and never inside a window.
- Decision → first write is 38–93 µs: a round trip to any endpoint (≥0.5 ms RTT) cannot fit in it.
- Code check: the buy is prepared at the create (`fastfire::prepare`): the blockhash is read from the in-memory
  `BLOCKHASH_CACHE` (refreshed every 300 ms by a background task), the route from the in-memory leader book
  (`leader_of(slot)`, refreshed every 10 min), ATAs derived locally, presigned; the write at the decision is a
  synchronous `write_all_now` from the event loop. No getBalance / getLatestBlockhash / getSlot on the buy path.

### 8.3 BUG: the race-gate bundle did not match the chain's "glued" bundle — FIXED (`--race-glued`)
- Old: "bundle" = any non-pro tx within 3 ms of our first sight + creator-set signers; cap buys priced roughly.
  Outsiders inside 3 ms counted, late legs missed (AD9eR84iLn: engine 3.16 SOL vs chain 5.78; 8JFMX2cFgZ: 3.83 vs 2.50).
- New, same definition as the labels (race_lib.block_record): the **unbroken run of non-vote txs right after the
  create in the leader's order** that are buys of the mint; it ends at the first other non-vote tx or failed tx.
  - Order: the slot's non-vote tx order as an entries feed (erpc) or shred feed (DZ) walked it from the slot's first
    entry (`feeds::slot_order`, sig8 + forwarded flag). A non-forwarded tx (not pump) ends the run; a forwarded tx
    of another mint ends it; a forwarded tx not yet processed makes the engine wait.
  - SOL per leg, simulated on the curve in order from the create tx's own buys: exact-in = SOL × 10000/10125
    (fee 125 bps), cap buys = curve cost of the tokens; a leg whose slippage limit would be violated ends the run
    (a reverted tx). Calibration on 60 launches / 141 legs vs TradeEvents: **per-leg error p50 0.000%, p90 0.000%,
    max 5.8%** (`calib2.py`).
  - Router-CPI legs (19% of legs in the sample: bundler programs with no top-level pump ix) can't be priced from ix
    data: counted as legs with unknown SOL; a launch with any unknown leg is **rejected** (fail-safe: can only miss
    a fire, never fire wrongly).
  - Decided when the run is closed (or `--race-run-max-ms`, default 40 ms).

**Validation of the fix (paper, zero cost):**
- `pall` (15 min, rule #2 bundle bounds without the tip prefix, so every base-filter launch is decided):
  133 launches decided, 114 verifiable on chain (`verify_g.py`, `verify_pall.txt`):
  - **bundle SOL |engine − chain| / chain: median 0.00%, p90 0.01% (n=68 with a bundle)**; glued leg count equal on
    112/114 (the 2 others differ without changing the 3–5 SOL condition);
  - **bundle-condition mismatches (engine vs chain, both directions): 0 of 114**;
  - every engine pass has exactly the chain's legs/SOL (25/25); the 5 of them failing rule #2 on chain fail only the
    Lunar tip, which this run did not require;
  - slot order found for 133/133; run closed 132/133; decision after first sight p50 2.9 ms, p90 5.5, max 42 ms
    (it waits for the run to close instead of a fixed 3 ms).

### 8.4 LandX key (owner, 2026-10-19)
- The owner put a NEW LandX key in `.env` as `LANDX_KEY` (the old key was dead).
- JSON-RPC auth on **fra1 now succeeds**; the **binary `/txb` endpoint answers "api-key does not exist" for every key**.
- Our route uses **`landx-fra3` = the UDP endpoint** (12-byte key + raw tx, never answers), so its acceptance can't be
  checked zero-cost. If LandX's UDP shares /txb's key store, the landx-fra3 copy of every BAM/Jito-route buy is
  silently dropped. The other paths on those routes (jito-bundle, staked-rpc, helius) still carry the buy.
  Owner options: ask LandX to enable the key for UDP/binary, or switch the route's landx path to fra1 JSON-RPC
  (http; a send-path change, owner's call).
- **`pr2` (30 min, the exact rule #2 flags + `--race-glued`, `final_landing.toml`)**: 47 launches decided, 24 fired;
  **every decision verified on chain (47/47): 0 bundle-condition mismatches, all 24 fires pass rule #2 on chain
  (glued bundle 3–5 SOL and the Lunar `moon…` System-transfer tip)**; engine bundle SOL = chain TradeEvent SOL on
  all 40 launches with a bundle (median and p90 error 0.00%); leg count equal on 46/47; 0 router-CPI legs met;
  decision after first sight p50 2.8 ms, p90 5.2, max 40 ms. 0 panics. (`verify_pr2.txt`)
- **`fin2` (15 min `--junk-fanout`, exact `live_final.sh` flags incl. `--race-glued`)**: 6 fires, wallet
  0.310818539 SOL before and after; **decision → first send write p50 59 µs, p99 181 µs**; detection → first
  write 0.55–7.5 ms (= waiting for the glued run to close); **0 network writes/connects between detection and the first
  send write in all 6 windows** (`proof_fin2.txt`); first-arrival shares (548 creates): dz-leader 40%, dz-retrans-eu
  35%, Kaldera 14%, turbo-Kaldera 10%, erpc 2%. 0 panics, 0 HTTP 429.
- `verify_r2.py`'s tip check (largest balance delta) was replaced in `verify_g.py` by the System-transfer
  destinations from `common.tx_summary` (as asked).
- `/root/lat/live_final.sh` now carries `--race-glued` (validated above). **Not run.**

## 7. Paid / owner options (ranked by expected gain for us; prices from vendor pages, Oct 2026)

What a better feed can and cannot buy: it can cut row 2 (relay/Turbine: the 2.3 ms in-set spread, part of the
~22 ms FRA→FRA handover). It cannot cut row 1 (leader broadcast batching, ~10 ms) or row 7 (auction batching).

| # | option | cost | expected gain vs constantk UDP | notes |
|---|---|---|---|---|
| 1 | **OrbitFlare raw UDP shreds, free 60-min trial** [R12] | $0 trial; Frankfurt "premium" $1,000/mo | unknown → measure | zero-cost: point it at 77.223.215.155:20002, add a `udp-shreds` block, run feed_race 30 min |
| 2 | **ERPC Epic Shreds "Direct"** (NIC-to-IP raw UDP from a >200k SOL validator, same DC) [R6,R7] | **€7.29/hour** (launch), €498–980/mo plans | likely 0–3 ms (staked validator = Turbine layer 1) | the cheapest real test: 1 hour of the harness costs €7.29 |
| 3 | **DoubleZero Edge** leader-direct shreds (GRE tunnel + doublezerod, UDP 7733) [R1–R3] | **$1,500/seat/mo** in Frankfurt | claims −20.7 ms p50 vs Turbine, −11.6 ms vs Jito ShredStream; only ~43% of stake publishes | the only real "leader-direct" product; gain applies to covered leaders only; validator 90-day trial |
| 4 | Helius shred delivery (raw UDP) [R8] | $1,000/IP/mo ($800 on Pro) | unknown | beta, no trial |
| 5 | Everstake ($500/mo, one region; $1,100 six) [R11], BlockRazor ($500/stream) [R13], Corvus (trial on onboarding) [R14], Triton multicast (on request) [R9], bloXroute (no public price) [R10], Thor [R15] | $500–1,100/mo | unknown; vendor claims only | race any of them with feed_race before paying |
| 6 | Shyft RabbitStream / Triton Deshred (gRPC deshred) | $199+/mo | ≤0 (deshred is later than raw UDP: Kaldera is 0.7 ms behind constantk; Triton quotes 6.3 ms p50 deshred after shreds) | not useful |
| 7 | **Not a feed: getting into the create's auction batch** — Jito bundle path on BAM/Jito leaders, Harmonic bundles (`fra.be.harmonic.gg`), BAM Direct Bundle Ingest (whitelist only) [R16] | tips | the big lever: row 7 is ~25–35 ms | already in the lat agent's live test |
| 8 | Own staked validator / co-location in leader DCs | $$$ | Turbine layer-1 position; does not remove leader batching | not worth it for this |

## Research (sources)
- **Leader batching.** Agave coalesces entries up to 50 ms (`ENTRY_COALESCE_DURATION`) before shredding; a batch
  closes early at ~2 FEC sets, at slot end or on a marker; FEC sets are 32 data + 32 coding shreds [R17, R18].
  Firedancer batches microblocks by size and flushes at block end / new slot [R19] (unverified detail). Our pcap
  agrees: consecutive FEC sets of a slot are p50 4.9 ms, p90 21.5 ms, p99 42 ms apart.
- **PoH vs wall time.** Hashing and recording share one thread; hashing pauses while recording and spins when ahead,
  so PoH tracks wall time only on average [R20]. Slots are 200 ms since epoch 1053 (2026-10-09), 64 ticks [R21].
- **Turbine.** Fanout 200: leader → root → layer 1 (≤200 nodes) → layer 2. A new stake-weighted shuffle per shred;
  unstaked nodes always last (layer 2) [R22–R24]. No independent per-layer measurement found; DoubleZero claims
  −20.7 ms p50 / −209 ms p95 vs Turbine [R3].
- **Jito ShredStream was shut down on 2026-09-05**; Jito points to DoubleZero Edge [R1].
- **Auctions.** Jito block engine 50 ms auctions [R25]; BAM 25 ms batch auctions (20 ms per lat notes) [R26];
  Harmonic 50 ms buffer [R27]. SWQoS gives staked connections 80% of TPU capacity [R28].
- **How the 1–11 ms lane happens (inference).** A buy recorded ≤10 ms after the create cannot have been triggered by
  the create's shreds when the create's own broadcast waits ~10 ms (row 1) plus relay and auction time. So the fast
  lane is either bundled with the create (launch-tool bundlers: the d≤5 wallets that are always there) or reaches the
  same auction batch through pre-broadcast visibility. A faster shred feed cannot get us there.
- **Alpenglow (epoch 1064, ~2026-10-21 15:00 UTC)**: leaders stop sending ticks (the PoH analyses here stop working),
  BAM goes into maintenance (falls back to the Jito block engine), Turbine unchanged [R21, R26].

[R1] https://docs.jito.wtf/lowlatencytxnfeed/ · [R2] https://docs.doublezero.xyz/solana/edge/subscribe/ ·
[R3] https://doublezero.xyz/jito-shredstream · [R4] https://doublezero.xyz/journal/doublezero-edge-beta-is-live ·
[R6] https://erpc.global/en/news/2026/03/18/erpc-epic-shreds-launch-202603/ · [R7] https://prtimes.jp/main/html/rd/p/000000465.000105962.html ·
[R8] https://www.helius.dev/docs/shred-delivery · [R9] https://docs.triton.one/chains/solana/shred-streaming ·
[R10] https://docs.bloxroute.com/solana/optimized-feed-relay/shred-stream.md · [R11] https://blockspace.everstake.com/ ·
[R12] https://orbitflare.com/pricing , https://orbitflare.com/blog/developers/jito-shredstream-shutdown-migration-guide , https://orbitflare.com/benchmarks ·
[R13] https://blockrazor.io/docs_en/streams/block-stream/solana/shred-stream/ · [R14] https://docs.corvus-labs.io/platform/shredstream ·
[R15] https://www.thornode.io/thor-shredstream/ · [R16] https://solanacompass.com/news/jito-announces-bam-direct-bundle-ingest-routing-solana-bundles-past-the-block-engines-50ms-hop ·
[R17] https://raw.githubusercontent.com/anza-xyz/agave/master/turbine/src/broadcast_stage/broadcast_utils.rs ·
[R18] https://raw.githubusercontent.com/anza-xyz/agave/master/ledger/src/shred.rs ·
[R19] https://raw.githubusercontent.com/firedancer-io/firedancer/main/src/disco/shred/fd_shred_tile.c ·
[R20] https://raw.githubusercontent.com/anza-xyz/agave/master/poh/src/poh_service.rs · [R21] https://solana.com/upgrades/reduced-slot-times , https://solana.com/upgrades/alpenglow ·
[R22] https://raw.githubusercontent.com/anza-xyz/agave/master/turbine/src/cluster_nodes.rs · [R23] https://docs.anza.xyz/consensus/turbine-block-propagation ·
[R24] https://raw.githubusercontent.com/anza-xyz/agave/master/gossip/src/weighted_shuffle.rs · [R25] https://docs.jito.wtf/lowlatencytxnsend/ ·
[R26] https://www.tokenpost.com/news/technology/31530 · [R27] https://blockworks.com/newsletter/0xresearch/issue/post_f3a5adde-8a8f-4803-bbc6-827f51659331 ·
[R28] https://solana.com/docs/defi/stake-weighted-qos · also constant-k ShredPrism https://www.constant-k.com/solana-shredstream/ ,
Shyft https://docs.shyft.to/solana-shredstreaming/rabbitstream-overview , Triton deshred https://blog.triton.one/deshred-transactions-the-fastest-path-to-solana-data/

## Files (/root/gap)
| file | what |
|---|---|
| `READY.txt` | harness run command, what a provider must give, recommended engine feed setup |
| `feed_race.sh`, `feed_race.toml`, `feed_race_busy.toml`, `bin/feed_race` | harness (source `/root/sniper-feed/src/bin/feed_race.rs`) |
| `race_report.py`, `rpath.py`, `misses.py`, `handover.py`, `poh_an.py`, `pcap_fec.py`, `residual.py`, `leaders.py` | analyses |
| `race/summary_*.txt`, `race/ck1_10min.txt`, `race/ck1_30min.txt`, `race/pcap_fec.txt`, `race/residual.txt` | results |
| `race/ck_shreds.pcap` | 5 min of constant-k shred headers (snaplen 128) |
| `probe_feed.toml`, `paper_feed.sh` | engine config with constantk UDP + paper smoke |
| `udp_busy.patch` | opt-in UDP_PIN_CPU / UDP_BUSY_POLL in the engine's udp.rs (arbx-feed only) |

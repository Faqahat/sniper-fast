# Solana landing latency: web research notes (2026-10-07)

Scope: why a Frankfurt arb bot sees ~59 ms send-to-land on jito-relayer leaders and ~176 ms on Jito BAM leaders, and which levers exist for < 50 ms.
Convention: "INFERENCE" marks my own reasoning, not a published fact. Source code was read from public GitHub master branches on 2026-10-07 (copies in `landing-research/src/`).

---

## A. Jito BAM (Block Assembly Marketplace)

### Architecture and how traffic reaches a BAM leader
- A BAM node (in a TEE) takes in transactions and bundles, validates them, sequences them, and streams them to the connected leader over a bidirectional gRPC stream. The validator must execute them "in that exact order". One BAM node serves many validators. A validator connects to one BAM node at a time. Source: jito-omnidocs `bam/bam-overview/index.md` (github.com/jito-foundation/jito-omnidocs). The same text is at https://bam.dev/docs/bam/bam-overview/
- **A BAM validator's gossip TPU address is the BAM node's TPU, not the validator's own.** In jito-solana `core/src/proxy/fetch_stage_manager.rs`, `get_next_tpu_state()` reads: "BAM has the highest priority. We'll always advertise BAM TPU even if relayer-url is set." It advertises `bam_tpu_info` +6 port offset. `bam_tpu_info` is filled from the BAM node's `ConfigResponse.bam_config.tpu_sock/tpu_fwd_sock` (`core/src/bam_manager.rs::update_tpu_config`; `bam_types.proto` `BamConfig`, github.com/jito-labs/bam-protos).
  - So a direct-to-leader TPU QUIC send aimed at a BAM leader's gossip TPU actually lands at the BAM node.
- BAM docs FAQ: "Direct TPU flow: Transactions sent directly to your TPU port are processed through BAM before execution". Also: "RPC flow: If your validator is connected to BAM and scheduled to be a leader soon, transactions submitted via RPC are routed through BAM" (bam-overview).
- Steelman blog: "When validators connect to BAM, their TPU is pointed to BAM, which schedules transactions and delivers them for execution. There is no such thing as 'BAM transactions' versus 'non-BAM transactions'" (https://bam.dev/blog/realities-myths-and-misconceptions-of-bam-a-steelman-exploration/).
- Bundles: "The BAM Node creates one connection to the Block Engine in lieu of each connected validator in order to maintain backwards compatibility" (bam-overview). Jito block-engine bundles therefore go Block Engine -> BAM node -> validator. "AgaveBAM and FireBAM sequence both normal transactions and Jito Bundles."
- **BAM DBI ("Direct Bundle Ingest")** is a BAM-native bundle path that skips the Block Engine. It is named only in https://bam.dev/blog/update-on-bam-readiness-for-alpenglow-on-mainnet/ (2026-10-05): "DBI users: use the legacy Block Engine bundle-submission path". No public docs or endpoint found. INFERENCE: it is permissioned or onboarding-only.
- BAM receives shreds from the leader (`BamConfig.shred_socks`: "Socket(s) for forwarding leader and near-leader shreds"). It also gets leader-state messages (`LeaderState`, "Sent by the validator to the builder when it becomes the leader"). Source: bam_types.proto.

### Scheduling: batch auctions
- BAM runs **periodic batch auctions**:
  - Maker-plugin docs: "Every auction round (~50 ms), BAM assembles a batch… Phase 1 drains all maker priority plugin transactions… Within Phase 2, bundles and regular transactions compete on the same priority score under the same scheduling logic." Source: jito-omnidocs `bam/maker-plugin/how-it-works/index.md`. This means BAM orders by priority score (fee/tip) within a batch, not FIFO.
  - The newer BAM Changelog (2026-09-24, https://bam.dev/blog/bam-changelog-sept-9-24/) says: "BAM now schedules an increment to the permissionless Market Tick program at the start of every **25ms batch auction**, giving on-chain programs roughly 10 sub-slot timing updates per slot". INFERENCE: the cadence went from 50 ms to 25 ms. 25 ms x 10 = 250 ms, which matches the new 250 ms slot (see G).
  - Lightspeed podcast digest (2026-05-08): "batches and sequences them in 50ms auctions" (https://alearesearch.io/podcast-digest/lightspeed/inside-jitos-new-solana-plugin-strategy-or-eric-and-hayden).
  - Helius BAM explainer: "periodic intra-block auctions… subdividing the block into N slots and equally allocating CUs across each auction" (https://www.helius.dev/blog/block-assembly-marketplace-bam).
  - Anza (2026-02-11) saw block-position data where "AgaveBAM demonstrates prominent spikes which could be explained by 50ms batches", with a "step-like pattern in AgaveBam" (https://www.anza.xyz/blog/transaction-landing-on-tpu).
- On the validator side, the jito-solana `BamScheduler` (`core/src/banking_stage/transaction_scheduler/bam_scheduler.rs`) "pulls batches off the container, and then schedules them to workers in a FIFO, account-aware manner". It executes BAM's order. `AtomicTxnBatch` carries `seq_id` and `max_schedule_slot` (bam_types.proto).
- MPP explorer API example (bam-plugins `maker-priority/README.md`): `batch_start_time 1781136355462961432` to `batch_end_time 1781136355473540361` is a ~10.6 ms batch window in that sample. MPP "received" events exist "only if the packet arrived at the BAM node with an upcoming or current connected leader slot". "If a transaction was not forwarded, it was likely received too late in the leader rotation." (github.com/jito-foundation/bam-plugins)
- Stated direction: "BAM aims to support a pacing-based scheduler (i.e. it distributes transactions evenly across the slot)" (https://bam.dev/blog/supporting-ibrl-fast-and-predictable-execution-on-solana/, 2025-10-23).

### Published latencies and reliability
- No published end-to-end send-to-inclusion numbers for BAM.
- Claims: TEE overhead "2–5%" (Helius explainer). "vast majority of nodes can maintain latency under 5ms round trip" to validators (steelman blog). Preconfirmations give a "5-10ms advantage at the p50… versus shred-based signals" (https://solanacompass.com/news/jito-bam-preconfirmations-go-live-on-solana-covering-34-of-network-stake).
- Anza measured that "Regardless of the tool's location, most lost transactions were sent to the AgaveBAM client". The losses were isolated, not due to full blocks (40M CU used vs ~109M reserved) (Anza blog above).
- BAM mainnet node regions (https://bam.dev/validators/): ams, iad, dfw, dub, **fra (fra.mainnet.bam.jito.wtf)**, hkg, lon, lax, ewr, pit, slc, sea, sqq (Šiauliai), sin, tyo. A BAM Registry (auto-connect to the lowest-latency node) passed testnet testing on 2026-09-18, with mainnet "planned" (changelog 09-24).
  - INFERENCE: a validator may be on a BAM node in a different region from the validator itself, which adds RTT.

### Fastest submission method into a BAM leader's block
- Nothing published ranks the paths. INFERENCE from the architecture:
  - (1) Staked QUIC to the BAM node's TPU (the gossip TPU of a BAM leader), from Frankfurt to the fra BAM node. This skips the Block Engine's own 50 ms auction tick and reaches the BAM batch directly.
  - (2) DBI, if access can be obtained. Block-engine bundles take the BE auction (50 ms ticks) plus the BAM batch, so two queueing stages.
  - Expected queueing inside BAM is about half a batch interval (12.5 ms at 25 ms, 25 ms at 50 ms), plus BAM-to-validator gRPC RTT, plus execution.
  - BAM orders within a batch by priority score, so fee/tip matters on BAM leaders (unlike Agave FIFO-ish arrival).
- Astralane says its `sendTransaction` "provides direct routing to leading block builders like Harmonic and BAM" (https://astralane.gitbook.io/docs/low-latency/submit-transactions.md). This is the only sender found that explicitly claims a BAM route.

### Stake share
- "Total BAM stake has surpassed 34% of the network" (BAM changelog, 2026-09-11, https://bam.dev/blog/bam-changelog-sept-11/). 34.1% across 383 of 665 validators at preconfirmations launch, 2026-09-09 (solanacompass link above). Q1 2026: 28%.
- FireBAM (Firedancer/Frankendancer BAM) is live. Minimum versions: AgaveBAM v4.3.0, FireBAM v26.09.4 (changelog 09-24).
- **Alpenglow transition: Jito will put all mainnet BAM nodes in maintenance mode in the days before Alpenglow activation (mid-October 2026). "Validators connected to BAM will revert back to ordinary Jito-Agave Block Engine mode"; MPP and DBI unavailable; "Bundles from Block Engine will continue to work as usual."** (https://bam.dev/blog/update-on-bam-readiness-for-alpenglow-on-mainnet/, 2026-10-05).
  - INFERENCE: for that window, current BAM leaders should behave like plain Jito-Agave leaders. Re-measure then.

---

## B. jito-relayer and jito-solana BundleStage

- **Relayer packet delay**: `transaction-relayer/src/main.rs`, arg `packet_delay_ms` ("Packet delay in milliseconds"), `#[arg(long, env, default_value_t = 50)]` (github.com/jito-foundation/jito-relayer, master).
  - It was 200 ms until commit ef96e0ef31 "change default delay to 50ms (#151)" on 2025-06-17, shipped in v0.4.1/v0.4.2 (2025-06-19/20). Latest release v0.4.2. The repo was last pushed 2025-12-30.
- Mechanism: `transaction-relayer/src/forwarder.rs::start_forward_and_delay_thread` ("Delays transactions for packet_delay_ms before forwarding them to the validator").
  - Every verified TPU batch is (a) immediately `try_send` to the Block Engine handler, with `expiration: packet_delay_ms`, unless `--disable-mempool`, and (b) pushed into a `VecDeque` stamped with `Instant::now()`.
  - Batches are released to the validator only once `stamp.elapsed() >= packet_delay`. Loop wakes every `SLEEP_DURATION = 5 ms` (recv_timeout).
  - So plain TPU transactions reach the validator **≥ packet_delay_ms (default 50 ms) + up to ~5 ms** after the relayer receives them.
- Relayer forwards only to leaders within `slot_lookahead` (default 5) unless `--forward-all` (which the code notes is "required to be true for SWQOS"). Other defaults: `max_unstaked_quic_connections` 500, `max_staked_quic_connections` 2000, `--staked-nodes-overrides` supported (main.rs; relayer/src/relayer.rs `forward_packets`).
- Jito history (https://bam.dev/blog/supporting-ibrl-fast-and-predictable-execution-on-solana/): "The relayer allowed validators to speedbump transactions by 200ms… In June 2025, improvements to Jito software reduced both the Block Engine auction tick and relayer speedbump to 50ms… Jito turned off its self-hosted relayers in early August, which eliminated the speedbump for validators connected to its infrastructure."
  - INFERENCE: leaders still behind a relayer in 2026 run their own (self-hosted) relayer, mostly at the 50 ms default. That matches the ~59 ms median measured (50 ms hold + network + execution).
- Block Engine auction: "Parallel auctions are run at 50ms ticks… Bundle orderings within a single auction are prioritized… based on requested tip/cus-requested efficiency" (github.com/jito-labs/jito-docs `docs/source/lowlatencytxnsend.md`). Frankfurt BE: `https://frankfurt.mainnet.block-engine.jito.wtf`. `bundleOnly=true` turns sendTransaction into a 1-tx bundle.
- jito-solana validator side:
  - The `FetchStageManager` switches gossip TPU to the relayer only after `RELAYER_TPU_ENABLE_DELAY = 60 s` of heartbeats. It reverts if heartbeats stop for `MAX_TIME_BETWEEN_RELAYER_HEARTBEATS = 1500 ms` (`core/src/proxy/fetch_stage_manager.rs`).
  - `BundleStage` (`core/src/bundle_stage.rs`): `MAX_BUNDLE_RETRY_DURATION = 40 ms`, `SLOT_BOUNDARY_CHECK_PERIOD = 10 ms`, BUNDLE_WINDOW_SIZE 10. Tip-program crank runs at the first bundle of each slot.
  - I found no code constant that reserves the start of the slot for bundles. Bundles and banking-stage transactions run in parallel stages that compete for account locks. Unverified: older jito-solana versions reserved block CU for bundles at slot start.
- Frankendancer "revenue" mode puts "TPU transactions at the end of the slot, while Jito bundles are added to the first ¾ of the block" (Anza blog). That is a place where bundles do get early-slot priority.

---

## C. Send services

| Service | Delivery (published) | Notes / numbers | Source |
|---|---|---|---|
| Helius Sender | "submits your transaction across all pathways (Helius, Jito, Harmonic, Rakurai, etc.) simultaneously". Sender Max (≥0.001 SOL tip) also "enters a **priority tip buffer** for top of block". `?swqos_only=true` (≥0.000005 SOL) = "single fast SWQOS path". Needs a priority fee ≥5,000 lamports. Regional `http://fra-sender.helius-rpc.com/fast`, `/ping` for warm connections. 50 rps/key/region. | No ms claims. INFERENCE: a "buffer" that ranks by tip may add holding latency, so A/B test Max vs swqos_only. Tips <0.001 SOL "do not enter the priority tip buffer… sent… through fewer pathways". | https://www.helius.dev/docs/sending-transactions/sender.md, sender-max.md, sender-swqos-only.md |
| Astralane Iris | "fast and lightweight TPU client that tracks leader schedule and sends transactions directly to the leaders also utilizing staked connection"; "dynamically routed to our partner peers which are closest to the leader". Routes "through our partner SWQoS clients, including Jito and Paladin… direct routing to… Harmonic and **BAM**… custom schedulers such as Rakurai". Params `swqos-only`, `mev-protect`; methods sendTransaction, sendBundle, sendIdeal, sendPaladin. QUIC on IPv4 endpoints. Routers "run in pure FIFO mode". Frankfurt: `fr.gateway.astralane.io/iris` (recommended), `fr2`. | Claims: "500ms latency improvement vs standard RPC", "40-50ms overhead reduction in processed transaction receipts", "0–1 slot P90". Min tip 0.001 SOL (free), 0.0001 SOL at VIP1. | https://astralane.gitbook.io/docs/low-latency/quickstart.md ; .../submit-transactions.md ; .../send-txn-fee-tiers.md |
| Raiden Bolt | "Submit signed Solana transactions through regional endpoints on dedicated infrastructure". HTTP JSON-RPC, binary `sendRawTransaction`, QUIC (on request; `fra.bolt.raiden.wtf:4433` UDP). "Jito / MEV routing: Available" on paid plans. Routing to leaders (SWQoS or not) **not disclosed**. Suggests sending to 2+ regions. | Claims "< 1ms average landing latency" (INFERENCE: edge processing time, not chain inclusion). Min tip 0.001 SOL; free 5 TPS; $49/$199/$499 tiers. | https://raiden.wtf/bolt ; https://raiden-4.gitbook.io/raiden.wtf.docs/llms-full.txt |
| Nozomi (Temporal) | "automatically routes single transactions to current and upcoming leaders, using staked connections"; bids tips into block-builder paths (Jito, Harmonic). Frankfurt `http://fra2.nozomi.temporal.xyz` (direct) or `https://fra.nozomi.temporal.xyz` (Cloudflare). | Min tip 0.001 SOL; "equal tips favor earlier arrival". No sub-50 ms claim; recommends API v2 / Batch Send over warm connection. | https://use.temporal.xyz/nozomi (GitBook ask answer citing readme/endpoints/tipping) |
| bloXroute Trader API | `useStakedRPCs`: "use weighted stake QoS to submit your transaction to the Leader" (tip ≥0.001 SOL). SP_LOW = "submitted directly to Jito without delay"; SP_MEDIUM/HIGH deliberately **delay** to avoid risky leaders. `allowBackRun` -> OFA. | No ms claims. Avoid submitProtection > LOW for latency. | https://docs.bloxroute.com/solana/trader-api/api-endpoints/core-endpoints/submit |
| 0slot | "Largest SWQoS Pool", "Dedicated SWQoS" per user; Frankfurt, Amsterdam, NY, Tokyo, LA; tip ≥0.001 SOL. | Marketing "0 slot". | https://0slot.trade |
| NextBlock | "largest SWQoS stake pool in Solana" | no numbers | https://docs.nextblock.io |
| Node1 | no public technical docs found | — | — |
| Harmonic | Alternate block engine + "Remote TPU" proxy for Harmonic validators. Searcher bundles over Jito-compatible gRPC (whitelist needed; revert protection). Frankfurt BE `https://fra.auction.harmonic.gg`, Remote TPU `https://fra.tpu.harmonic.gg`. Builder strategies: **50ms FBA** (double-buffered 50 ms batches sorted by priority fee+tip), **FIFO** (continuous), **MREV** (revenue-max, "higher per-transaction inclusion latency"). | Anza: Harmonic validators "consistently place transactions near the end of the slot". | https://docs.harmonic.gg/concepts/scheduling-strategies.md ; .../run-a-validator/endpoints.md ; .../searchers/harmonic-bundles.md |

- Explicit BAM support: only **Astralane** says it routes to BAM. Helius is a BAM preconfirmation distribution partner, but the Sender docs list Helius/Jito/Harmonic/Rakurai paths, not BAM.
- Other published numbers:
  - RPCFast "Beam" landed "330 ms on average against 457 ms on a standard RPC path" (https://rpcfast.com/blog/solana-swqos-staked-connections).
  - QuickNode Fastlane "0.43 average slot latency… 50.6% land instantly" (search snippet, marketplace.quicknode.com).
  - Anza staked TPU from Amsterdam: mean **0.29 slot** latency, 0.25±0.9 slot to EU Jito-Labs validators (Anza blog).

---

## D. Stake-weighted QoS (SWQoS)

Agave master (github.com/anza-xyz/agave):
- `streamer/src/quic.rs`:
  - `DEFAULT_MAX_STAKED_CONNECTIONS = 2000`, `DEFAULT_MAX_UNSTAKED_CONNECTIONS = 3000`
  - `DEFAULT_MAX_QUIC_CONNECTIONS_PER_STAKED_PEER = 16`, `..._PER_UNSTAKED_PEER = 8`
  - `DEFAULT_MAX_STREAMS_PER_MS = 500` (about 500k TPS capacity)
  - `DEFAULT_MAX_CONNECTIONS_PER_IPADDR_PER_MINUTE = 8`
- `streamer/src/nonblocking/swqos.rs`:
  - `QUIC_MAX_UNSTAKED_CONCURRENT_STREAMS = 128`, `QUIC_MIN_STAKED_CONCURRENT_STREAMS = 128`, `QUIC_MAX_STAKED_CONCURRENT_STREAMS = 512`
  - RTT scaling (`REFERENCE_RTT_MS = 50`, `MAX_RTT_MS = 350`)
- `streamer/src/nonblocking/stream_throttle.rs`:
  - Unstaked peer: `MAX_UNSTAKED_TPS = 400` while total load < `UNSTAKED_THROTTLING_ON_LOAD_THRESHOLD_RATIO = 0.70`, otherwise `MIN_UNSTAKED_TPS = 100`.
  - Staked peers switch to stake-proportional quotas only when staked load > `STAKED_THROTTLING_ON_LOAD_THRESHOLD_RATIO = 0.76` of capacity, with floor `MIN_STAKED_TPS = 210`.
  - Throttle interval `STREAM_THROTTLING_INTERVAL_MS = 100`. Load EMA over 40×5 ms "to absorb a burst… over ~40 ms".
  - Comment: 0.76 "is the previous trip point of 95% of an 80% staked share". So the classic "80% of capacity reserved for staked" now applies only as a load-triggered fallback.
- Triton (updated 2026-05-05): staked pool 2,000 separate from the unstaked pool. Static 80/20 "no longer applies continuously". Agave 4.0 removed staked TPS throttling under normal load. Agave 4.1 uses QUIC flow control, "~10,000 TPS per connection… regardless of stake size". (https://blog.triton.one/evolution-of-solanas-stake-weighted-quality-of-service-from-the-agave-side/)
- **Leader-side forwarding only forwards staked traffic**: `core/src/forwarding_stage.rs::initial_packet_meta_filter` = `!meta.discard() && !meta.forwarded() && meta.is_from_staked_node()`, with `NUM_LOOKAHEAD_LEADERS = 3`. So unstaked TPU packets that reach a non-leader or a late leader are never forwarded.
- Firedancer: `[tiles.quic]` defaults `max_concurrent_connections = 131072`, `max_concurrent_handshakes = 4096`, `retry = true`. No stake-tiering knobs in the QUIC tile config or `fd_quic_tile.c` (src/app/firedancer/config/default.toml; src/disco/quic/fd_quic_tile.c). INFERENCE: on Firedancer leaders, staked vs unstaked matters less at ingest; pack ordering is by fee/CU.
- Ways for a non-validator to get SWQoS:
  - (1) A staked validator adds your QUIC client identity pubkey to its `--staked-nodes-overrides` YAML (`staked_map_id: {pubkey: stake}`). This gives "virtual" stake at that validator only.
  - (2) Your client presents a staked identity (your own validator keypair). Anza: "To establish a staked connection, users need to provide a staked validator identity."
  - (3) Use a provider whose senders hold stake or peering deals (Helius, Astralane, 0slot, NextBlock, Nozomi, bloXroute).
  - INFERENCE: overrides only help with the specific leaders that configured them. Sitting behind another validator's RPC path (`--rpc-send-transaction-tpu-peer`) adds a hop.
- Published prices: Everstake SWQoS "from $500/month for RPC-based access and $1,300/month for QUIC-based access"; €100/month add-on on dedicated nodes (search snippet of https://everstake.one/products/swqos). RPCFast Beam on all tiers, 5 credits per send (rpcfast blog). Helius Sender is credit-free with a tip.

---

## E. DoubleZero (DZ)

- Modes (https://docs.doublezero.xyz/glossary/):
  - **IBRL** = "connect to DoubleZero without restarting their blockchain clients. IBRL uses the existing public IP address and establishes an overlay tunnel to the nearest DZD".
  - **Multicast** has publisher and subscriber roles ("Publish shreds (Edge)", "Subscribe to shreds (Edge)").
- Non-validators: "User onboarding is currently permissioned for non-validators and RPCs… fill out this form… There may be fees associated with Permissioned User usage in the future." Then `doublezero connect ibrl` (https://docs.doublezero.xyz/Permissioned%20Connection/).
- No product called "transaction submission" or "tx relay". Edge-filtering of inbound transactions is described, but: "This feature is not yet functional" (https://docs.doublezero.xyz/).
  - INFERENCE: a permissioned IBRL user's unicast packets to the public IP of another DZ-connected node (for example a leader's TPU) would ride the DZ overlay. That only helps for far-away leaders. Frankfurt to Frankfurt or Amsterdam leaders is already ~1–8 ms over the internet. For BAM leaders the TPU is the BAM node, which is a different host from the validator.
- Stake on DZ: 59% / 462 validators at end of Q2 2026; 62.6% at 2026-08-22, with 58% of stake publishing shreds to Edge (https://solanacompass.com/news/doublezero-foundation-turns-two-626-solana-stake-sec-no-action-letter).
- Latency claims:
  - Edge shreds "tens of milliseconds" faster in Europe, ">80 ms" in the US vs public internet (same source).
  - "~11%" lower average latency for geographic expansion (https://doublezero.xyz/journal/extending-solanas-network-performance-to-the-edge).
  - BAM plans to "migrate to DoubleZero" (steelman blog).
- Cost: validators pay a flat 5% of block signature rewards and priority fees, from epoch 859 (Oct 2025) (search result on 2Z fee, airdropalert/atomicwallet summaries; not verified on primary docs). Edge shreds are a paid subscription (~50+ paying Edge subscribers). Permissioned-user fees are "may be… in the future".

---

## F. Firedancer / Frankendancer

- Pack tile (`src/disco/pack/fd_pack_tile.c`, github.com/firedancer-io/firedancer):
  - Builds microblocks continuously during the leader slot, sent to execle (bank) tiles. `MICROBLOCK_DURATION_NS 0L` ("Pace microblocks, but only slightly"). `CUS_PER_MICROBLOCK = 1.6M`. Votes first (`VOTE_FRACTION = 1.0`).
  - Stores up to `max_pending_transactions = 65524` while waiting to be leader.
  - "leader transitions are typically short (<15 millis)".
- Pacing (`src/disco/pack/fd_pack_pacing.h`): "Without pacing… lucrative transactions that arrive… towards the end of a block will have to be delayed". It assumes ~9 ns/CU and makes "the 1 bank line end 5% before t_end", so pack finishes scheduling about 5% of the slot (~12.5 ms at 250 ms) before slot end.
- Strategies (default.toml `[tiles.pack].schedule_strategy`):
  - "perf": fill as fast as possible with highest-paying transactions.
  - "balanced" (default): "fill the block at a rate that is just fast enough to fill it by the end".
  - INFERENCE: under balanced pacing, a low-fee transaction may wait inside the slot until CU budget opens up. Higher priority fee helps on FD leaders.
- Bundles: Firedancer has a native `bundle` tile that "receives bundles from a remote block engine and forwards them for atomic execution to the pack tile" (`[tiles.bundle]`, `src/disco/bundle/fd_bundle_tile.c`). So Firedancer leaders can be Jito block-engine leaders. FireBAM: a "dedicated bam tile… Pack tile handles BAM bundle assembly/scheduling… when BAM is unhealthy… falls back to normal QUIC/bundle ingestion" (https://bam.dev/blog/introducing-firebam-bam-expands-to-firedancer/).
- Measured behaviour (Anza 2026-02): Frankendancer "revenue" nodes put TPU transactions at end of slot (bundles in first ¾). Firedancer sample "similar to Frankendancer Revenue". FD had the second-highest drop rate (skips, misconfig, mid-window drops).
- Stake: full Firedancer ~11–14%, Firedancer family 14–26% (mid/late 2026) (https://cryptobriefing.com/jump-firedancer-ends-frankendancer-support/, 2026-09-11). Jump: "Frankendancer will not have an Alpenglow-compatible release and will be unsupported after activation" (BAM changelog 09-24). FireBAM operators need v26.10+ after Alpenglow.

---

## G. Timing: slots, Alpenglow, in-slot inclusion, forwarding

### Why mainnet slots are ~255–275 ms now (answer to the 260–275 ms measurement)
- **SIMD-0525 "Reduce Slot Times"** (Anza, Brennan Watt) cuts the target slot time in four feature-gated steps. Each step "becomes effective one epoch after activation". Source: github.com/solana-foundation/solana-improvement-documents `proposals/0525-reduce-slot-times.md`.

  | Step | Feature gate | Mainnet effective date |
  |---|---|---|
  | 350 ms | `iBRL5RuWhw4yqaAZu96RUULHckHTZAoe2b77qaV38JZ` | 2026-08-21, epoch 1020 |
  | 300 ms | `iBRLL3k18HST852F1Mf3Lv83waTNQmmqvKDxvYGwQFL` | 2026-08-28, epoch 1024 |
  | **250 ms** | `iBRLMc81UjRa8fn8A6eE8bJTnRbgQoPTynM51akENCV` | **2026-09-18, epoch 1037 (current target)** |
  | 200 ms | `iBRLjhJnkmDZgNoZRDMW11d8ZV7HvsL3vAyRjZB5npW` | "Scheduled epoch 1052" |

  Dates from https://solana.com/upgrades/reduced-slot-times.
  - INFERENCE: at ~30 h per epoch, epoch 1052 is about now (early October). Check `getEpochInfo` and `getFeatureActivation` on the 200 ms gate.
  - The measured ~265 ms = 250 ms target plus normal slot stretch.
- What changes:
  - `ticks_per_slot` stays 64. `hashes_per_tick` scales (62,500 at 400 ms down to 31,250 at 200 ms). **Leader windows stay 4 consecutive slots** ("Keep leader windows fixed at 4 slots"), so a leader window is now ~1.0 s, and 0.8 s at 200 ms.
  - Block limits scale: 60M -> 52.5M -> 45M -> **37.5M (250 ms)** -> 30M CUs. Writable-account limit 24M -> 15M at 250 ms. If SIMD-0286 (100M) is active, the 250 ms limit is 62.5M.
  - Blockhash queue unchanged at 150 blocks, so ~37–40 s wall-clock validity at 250 ms (~30 s at 200 ms).
  - Agave SDK `DEFAULT_MS_PER_SLOT` is now 300 (solana-sdk `clock/src/lib.rs`), with constants for 400/350/300/250/200 ms.

### Alpenglow status
- SIMD-0326. Activation switch ships in Agave 4.3. Mainnet target "mid-October" 2026 (BAM post 2026-10-05). Testnet activated 2026-09-24. Not yet on mainnet as of early October (https://www.techtimes.com/articles/324490/20260814/solana-confirms-alpenglow-activates-october-agave-43-carries-switch.htm; cryptoticker / forklog summaries).
- Changes:
  - Votor replaces TowerBFT: votes become off-chain UDP messages with BLS certificates; finality ~100–150 ms (testnet median 54 ms reported).
  - Vote transactions leave blocks.
  - **Rotor (Turbine replacement) is deferred** pending separate governance.
  - Migration via "Alpenswitch" (SIMD-0384).
  - Under Alpenglow, SIMD-0525 does not reduce `hashes_per_tick` (one hash per tick, low-power PoH). Leader decisions use a slot clock: Agave `core/src/banking_stage/decision_maker.rs::make_decision_alpenglow` "PoH tick height no longer advances after Alpenglow activation".
  - Alpenglow keeps 4-slot leader windows (SIMD-0525 VAT scaling text assumes it).
  - INFERENCE: inclusion mechanics inside the leader (banking/pack) do not change at activation. Freed vote space reduces block contention, and the BAM maintenance window (A) temporarily changes BAM leaders to plain Jito-Agave.

### In-slot inclusion, hold, and forwarding (Agave)
- Agave holds or forwards by distance to its own leader slot:
  - `FORWARD_TRANSACTIONS_TO_LEADER_AT_SLOT_OFFSET = 2`, `HOLD_TRANSACTIONS_SLOT_OFFSET = 20` (solana-sdk clock).
  - `decision_maker.rs`: within 2 slots of leading -> `Hold`; within 20 -> `ForwardAndHold`; otherwise `Forward`. While leader (working bank) -> `Consume`.
  - Transactions that arrive just before the leader slot are buffered and consumed from slot start.
- Forwarding: `ForwardingStage` forwards only staked-origin packets to the leader up to `NUM_LOOKAHEAD_LEADERS = 3` windows ahead (`forwarding_stage.rs`). Unstaked sends must target the right leader themselves.
- Late arrivals: Anza saw a spike of transactions landing in the first ~2 ticks of the next slot, "most likely caused by transactions that were received in the previous slot and carried over" (Anza blog).
  - Jito-Labs validators had "the most uniform distribution". In-region sends land "early in the slot".
  - Utah->EU included after ~tick 20 (≈125 ms) and Tokyo->EU after ~tick 28 (≈175 ms), mostly explained by one-way delay.
- Recommended fan-out (Anza `tpu-client-next` dynamic fanout): "sent only to the current leader when the estimated slot is within the first three slots of the leader window, and to both the current and next leader when the estimated slot is the final slot of the window". Connect to the next leaders 4–8 slots ahead (pre-warm QUIC). Track slots with FirstShredReceived/Completed events.
  - INFERENCE: with 250 ms slots the last slot of a window is the risky one. Fan out to next leader during it.

---

## Implications for landing < 50 ms (Frankfurt) — mostly INFERENCE

1. **Jito-relayer leaders**: a self-hosted relayer holds every TPU packet for `packet_delay_ms`, default 50 ms (was 200 ms), released on a 5 ms poll.
   - Plain TPU sends to these leaders cannot beat ~50 ms + RTT + execution. The 59 ms median is close to that floor.
   - A Block Engine bundle has its own 50 ms auction tick, so that is not obviously faster.
   - The < 50 ms goal is effectively unreachable on relayer leaders unless the operator lowered the delay. Treat them as ~55–60 ms best case.
2. **BAM leaders (~34% of stake)**: all TPU traffic goes to the BAM node (gossip TPU = BAM node). It is batched in 25 ms (formerly 50 ms) auctions, ordered by priority score, then streamed via gRPC to a validator that may be in another region.
   - Best guess for the fastest path: staked QUIC directly to the leader's gossip TPU (= BAM node; fra.mainnet.bam.jito.wtf if that is the node), with a meaningful priority fee/tip. Avoid the Block Engine path (two auction stages). Try Astralane's BAM route, or ask Jito about DBI.
   - The 176 ms median looks too large for one 25–50 ms batch. Investigate whether the BAM node holds or drops transactions until the leader's window is "current" (MPP docs: "received too late in the leader rotation"). Also check whether the leader's BAM node is outside Frankfurt, and whether Anza's elevated AgaveBAM drop rate causes retries.
   - BAM goes into maintenance mode around Alpenglow (mid-Oct 2026). Re-measure then, when those leaders run plain Jito-Agave.
3. **Plain Agave / Jito-Agave leaders without a relayer, and Firedancer leaders**: there is no hold.
   - Staked QUIC from Frankfurt to an EU leader is the fastest path (Anza: 0.25–0.29 slot mean from Amsterdam, ≈60–70 ms at 250 ms slots, including slot-position effects).
   - Sub-50 ms is plausible only for sends during the leader's slot with a pre-warmed staked connection and enough priority fee to beat Firedancer "balanced" pacing.
   - Unstaked connections get only 100–400 TPS/peer and are never forwarded by other validators.
4. **Avoid deliberate-delay features**: bloXroute SP_MEDIUM/HIGH, possibly Helius Sender Max's "priority tip buffer" (A/B against `swqos_only=true`), and Harmonic MREV/FBA leaders (50 ms buffers or end-of-slot placement).
5. **Slot timing**: slots are now 250 ms (200 ms gate pending, possibly at epoch 1052). Leader windows are 4 slots (~1 s). Late-slot arrivals roll to the next slot (+~250 ms). Fan out to the next leader during the last slot of a window.
6. **DoubleZero** is unlikely to matter for Frankfurt-to-EU leaders (sub-10 ms anyway). Its unicast IBRL access for non-validators is permissioned and has no transaction-relay product.

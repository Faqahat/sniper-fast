# How each leader client orders our dip buy, and what to change

10-25 PKT. Read-only study of the clients' public source code and docs, checked against our live data.
The owner asked about 10:55 PKT: "the validators code like bam jito etc is open source, why don't we download it, study each, see what they are doing, how we can improve our landing with each".

Labels: **MEASURED** = our data · **CODE** = source (file:line) · **DOC** = docs/blog (Sources, §9) · **INFERRED** = my reading.
All changes below are recommendations. Any send-path change needs the owner's OK.

---

## 0. Verdict

**What decides our place after the dump (all clients):**
- **Arrival at the scheduler decides.** Fee only orders the txs that arrive inside the same batch window.
  - The windows: Jito/Agave none (continuous), Firedancer none, BAM ~20 ms auction rounds, Harmonic 50 ms buffers, Rakurai a hold of about a slot for our copies.
  - MEASURED (189k sells ≥ 1 SOL, 2 days of chain data): in pairs of reacting buys ≤ 5 txs apart, the higher CU price came first:

    | BAM | FireBAM | Harmonic | Firedancer | Jito |
    |---|---|---|---|---|
    | 79% | 78% | 66% | 62% | 57% |

  - When CU price and total fee disagree, CU price predicts the order: BAM 74%, Harmonic 65–69%, Firedancer 67%, Jito 53% (a coin flip).
- **Slots are 200 ms now** (since 10-09), and **Alpenglow has run since ~10-21** (DOC).
  - CODE: on every client, block 1 of each 4-slot leader window records for **≤ 144 ms**; blocks 2–4 get 200 ms (`block_creation_loop.rs:455`).
  - That short first block explains the "turn-start spills" (Jito spill by window slot: 15/24, 8/21, 6/23, 3/24). On BAM we land fast enough that it barely shows (2/23 in slot 1).
- **Four things in our own send setup cost us time:**
  1. **Jito relayer.** 39 of 146 Jito leaders (27% of Jito slots) front their TPU with a Jito relayer that holds every plain tx **50 ms** (CODE). MEASURED: there we land at 72 ms vs 43 ms on the other Jito leaders.
  2. **Helius tip of 0.001.** It puts our copy in Helius's "priority tip buffer for top of block" (DOC). MEASURED: those copies landed at 121 ms median on Jito, 8 of 14 in the next slot.
  3. **Rakurai.** Its closed scheduler holds TPU packets unless they come via a relayer or from whitelisted IPs (CODE). MEASURED: 7 of 8 of our buys landed one slot later.
  4. **Harmonic.** The builder only sees txs that reach it; helius swqos-only and staked-rpc go the slow way round. MEASURED: on Harmonic, nozomi 23 fills / 3 fails; staked-rpc 2 / 29; helius-swqos 0 / 3.
- **Biggest new lever: see the dump before the shreds.**
  - BAM preconfirmations (via Helius) arrive "p50 5–10 ms" before shreds (DOC).
  - Harmonic Preconfs (via Triton) arrive "the moment it is selected, before it is packed into a shred" (DOC).
  - Together these cover ~2/3 of leader slots. Test in shadow first (log only).

### Top changes per client (ranked; gains INFERRED unless MEASURED)

**BAM (AgaveBam 36.5% of leader slots + FireBAM 1.6%; our best: 29 ms vs first rival 18–21)**
1. **Trigger on BAM preconfirmations** (Helius `preconfSubscribe`, source "bam"). DOC says 5–10 ms before shreds; 29 → ~20–24 ms would be about +8–12 fills per 309 attempts (guard curve, SPEED_TRUTH). Shadow-log the lead first. Cost: 10 Helius credits per message, so filter to watched tokens.
2. **Land in the first 20 ms round after the dump.** Keep nozomi as the main BAM copy (MEASURED 17 fills of 19, 30 ms). Map each leader's BAM node (17 node IPs in gossip) and send from the nearer server.
3. **Win inside the round.** BAM ranks by (priority fee + Jito tip) ÷ requested CU (DOC).
   - On the copy that needs no provider tip (staked-rpc), pay part of the bid as a **Jito tip** instead of CU price. Same rank, but a failed buy reverts its tip and pays only the lower priority fee. Example: 1M µL/CU + 0.0004 tip ranks like 5M with no tip.
   - Set `SetLoadedAccountsDataSizeLimit`.
   - Small landing gain; cheaper failed buys.
   - Cost note (MEASURED): our staked-rpc copies on BAM landed 18 failures and 2 fills; nozomi 2 failures and 17 fills (INFERRED: nozomi's BAM copy is revert-protected).
4. **Apply for BAM Direct Bundle Ingest (DBI)**: a single-tx bundle straight to the BAM node. It is revert-protected, so failed buys cost 0 (now 0.0005 each), and it skips the block engine's ~50 ms hop (DOC). Allowlist only.
5. **Check the 20 ms round effect**: bin our BAM landing delays. A step pattern means a few ms earlier only helps when it crosses a round.

**Jito (JitoLabs 23%; our worst: 54 ms vs first rival 26)**
1. **Relayer-fronted Jito leaders** (gossip TPU on the relayer's default port :11228: 28 on the validator's IP, 11 on another host; 39 of 146).
   - Every plain copy waits 50–55 ms (CODE). MEASURED: 72 vs 43 ms, and our staked-rpc copy never landed first there (0 of 16 single-copy landings).
   - Test a copy that skips the relayer: Jito block-engine `sendTransaction` (CODE: block-engine packets enter the validator without the hold).
   - Also test the providers that are fast there market-wide: solami_beam 16 ms, soyas 22, glaive 26 (median, mixes bot quality).
   - If nothing beats ~45 ms, skip these leaders (6% of all slots).
2. **Stop using the 0.001 Helius tier on Jito.**
   - 0.001 = "Sender Max", which enters a tip buffer (DOC); we measured 121 ms there.
   - Use helius **swqos-only with our API key**. Its minimum tip is 0.000005; we pay 0.0002. Keyless is 1 request/s per IP, which caused our 429s (DOC).
3. **Treat window slot 1 as ≤ 144 ms.** It is structural; no path fixes it.
   - In the engine: time left = block deadline − now (block 1: 144 ms, blocks 2–4: 200 ms from the window start).
   - Log first. Do not judge paths on slot-1 spills; spills still fill often (SPEED_TRUTH §4).
4. **Fees and tips don't buy position on Jito plain txs** (CODE: priority ignores tips; MEASURED: of 68 txs right before our Jito buys, 1 paid more). Keep the CU price, add no tips to Jito-bound plain copies, and look for speed only in path and timing.
5. **Rank our Jito paths with one-path probes** (`--dip-probe-paths`, Jito leaders only): staked-rpc (and log Constant-K's route header), helius swqos-only (keyed), nozomi, glaive/speedlanding if we add them.
   - MEASURED: nozomi on Jito landed only failures (15 of 15): 10 on relayer leaders at 62–131 ms, 5 on own-TPU leaders at 12–143 ms. INFERRED: Nozomi's server-side retries plus the relayer.

**Harmonic (HarmonicAgave 21.1% + HarmonicFiredancer 8.6%; 41 ms vs 27)**
1. **Arrival at the builder decides.**
   - Builders run 50 ms batch auctions by default ("FBA": every 50 ms the buffer is sorted by priority fee + tips). 77 of 87 Harmonic validators use it (DOC, explorer).
   - Within a buffer we usually rank first (CU price 5M); we lose when a rival makes the earlier buffer.
   - **Keep nozomi as the main Harmonic copy.** Nozomi has a "block builder (Jito or Harmonic)" path (DOC) and won 23 of 26 fills (MEASURED).
2. **Trigger on Harmonic Preconfs** (Triton gRPC; the builder's selections before shreds). Shadow-log the lead; cost unknown.
3. **Stop sending helius swqos-only and the tipless staked-rpc copy on Harmonic leaders.**
   - Both go to the Harmonic relay, the advertised TPU (INFERRED from the docs), and land late, mostly as failures (MEASURED 0/3 and 2/29).
   - Only Helius Sender Max reaches the Harmonic pathway (DOC), and it has the tip buffer.
4. **Test speedlanding and astralane on Harmonic.**
   - Market median 35 ms for speedlanding (first-place lift 1.3–1.5).
   - Astralane documents "direct routing to block builders like Harmonic and BAM".
5. **Direct Harmonic block-engine single-tx bundle** (public `fra.be.harmonic.gg/api/v1/bundles`; failed buys cost 0) only after our fail rate drops. Harmonic cuts off flow that "consistently reverts" (DOC); ours fails ~58%.

**Firedancer (6.8%; we already beat the first rival: 23 vs 29 ms)**
1. **Never send a Jito-bundle copy that shares the nonce to Firedancer leaders.** In pack, a waiting bundle copy blocks every normal copy with that nonce (CODE `fd_pack.c:1508-1514, 1683-1698`).
2. Firedancer has **no stake-weighted QoS and accepts UDP TPU** (port 9001) (CODE, DOC). A direct UDP or warm-QUIC copy to the leader's gossip TPU is a cheap extra path. Our UDP landx copy already lands at 24 ms there.
3. Leave fees as they are; contention is rare (CODE: pack is first-come unless txs wait together).

**Rakurai (1.1%)**
1. **Skip Rakurai leaders** (`--dip-skip-clients rakurai`, already in dip14). Cheapest; 7 of 8 spilled.
2. Only if we want them back: Jito bundle / Helius Sender Max / a TIN landing service, plus a Rakurai tip (it adds "virtual priority", DOC).

**Agave (1.1%)**: same rules as an own-TPU Jito leader without bundles. Nothing specific.

**All clients (measurement first)**
1. **Lock-only probes.** Today's probe (min_out = MAX, always fails) can never land through revert-protected paths (Jito bundles, Sender Max's Jito leg, DBI, Harmonic block engine), so it cannot rank them.
   - A tx that only write-locks the token's bonding curve (e.g. a 0-lamport self-transfer listing it writable) always succeeds and conflicts exactly like our buy.
   - About 0.00002 SOL on tipless paths vs 0.0005 now. Engine change, needs OK.
2. **Log Constant-K's `X-CK-Tx-Route` header per send.** Over the plan's staked sends per second (1/5/20 per region by plan), CK silently sends from its own node and rebroadcasts every 420 ms (DOC). That would explain "staked-rpc lands often but late".
3. **Add the Helius API key** (24 attempts got 429).
4. **Nozomi says builders "may deprioritize durable-nonce transactions" and "a high failure rate lowers your priority"** (DOC). A/B the nozomi copy with and without the nonce.
5. **Don't re-send identical bytes.** Every layer dedups them (Agave 2 s, Firedancer by signature, CK 60 s), and Nozomi lowers our priority (DOC). A second wave only helps at window ends, to the next leader.

### What this changes in the current fix plan (SPEED_TRUTH §6, FIXES.md)
- **A1, Jito route** (helius-swqos keyed + no-tip staked + nozomi; drop jito-bundle):
  - Keep "drop jito-bundle". It also avoids blocking our other copies on Firedancer leaders.
  - On relayer-fronted Jito leaders the no-tip staked copy and nozomi wait 50 ms. They need a non-relayer path (block-engine `sendTransaction`, or the fast private routes) or a skip.
- **A2, Harmonic** (test keyed helius-swqos): swqos-only is the wrong Helius tier for Harmonic; it never reaches the builder pathway. Test speedlanding, astralane and the Harmonic block engine instead; nozomi stays first.
- **A3, direct no-tip copy everywhere:**
  - Helps on own-TPU Jito, Agave and Firedancer.
  - On BAM it ranks by its CU price like any copy (a Jito tip would add to that), and it is the copy that lands our failures.
  - On Harmonic it goes the slow way through the relay and lands mostly failures.
- **C1, skip Rakurai:** confirmed by code (TPU hold).
- **C3, Jito turn-start spills "structural":** confirmed by code. Block 1 records ≤ 144 ms on every client.
- **D1, PoH clock:** under Alpenglow, Firedancer writes every entry with 1 hash (CODE `discof/motor/fd_motor_tile.c:14-24`). FIXES.md found the same in our data on all clients: the hash count tracks block position, not time. So the PoH count cannot be a clock; use ms since the window's first shred instead.

---

## 1. One table: how each client orders txs

| Client | Batch window | What ranks inside it | Tips count? |
|---|---|---|---|
| Jito, Agave | none (passes of ≤ 64 txs, back to back) | fee ÷ requested cost, but only txs waiting together | no |
| BAM, FireBAM | BAM node rounds, ~20 ms | (priority fee + Jito tip) ÷ requested CU | Jito tips yes |
| Harmonic (FBA) | builder buffer, 50 ms | priority fee + tips ("tips are priority fees") | as priority fee |
| Firedancer | none (pack, 1 tx per microblock) | fee ÷ requested cost, when contended | no |
| Rakurai | closed; our TPU copies held ~1 slot | base priority + Rakurai "virtual priority" tip | Rakurai tips |

Sources: CODE `agave/core/src/banking_stage/transaction_scheduler/greedy_scheduler.rs`, `transaction_priority.rs:32-66`; DOC bam.dev DBI post; DOC docs.harmonic.gg scheduling-strategies; CODE `firedancer/src/disco/pack/fd_pack.c`; CODE `rakurai-validator/core/src/proxy/fetch_stage_manager.rs:514-533`.

---

## 2. Agave base (also inside Jito, AgaveBam, Harmonic Salsa, Rakurai)

**Ingestion (CODE, agave v4.3.2)**
- QUIC TPU with stake-weighted QoS. Unstaked: 8 connections per IP, **20 streams per 100 ms per IP**; over quota, the connection sleeps for the rest of the 100 ms (`streamer/src/nonblocking/stream_throttle.rs:16-32, 233-271`). Staked: far more.
- DOC (Triton): from Agave 4.0, staked and unstaked share capacity unless the TPU is ~90% loaded. Measured p50 is the same.
- No coalescing delay before sigverify (`core/src/tpu.rs:190`: FetchStage coalesce = None).
- **Forwarding is off by default** in 4.3 (`validator/src/commands/run/execute.rs:893`). A tx that misses a leader's window is not passed on unless the sender also sent it to the next leader.

**Scheduling (CODE)**
- One greedy scheduler (`core/src/validator.rs:215-237`; `banking_stage.rs:588-593`).
- Priority = (priority fee + 50% of base fee) × 1e6 ÷ cost (`transaction_priority.rs:32-66`).
  - Cost = 720/sig + 300/writable account + data/4 + **requested** CU limit + 8 per 32 KiB of the loaded-data limit (default 64 MiB → **16,384**).
  - **Tips count for nothing.**
- Passes run back to back, ≤ 64 txs or ~4.6 KB per batch, nothing waits to fill (`greedy_scheduler.rs:26-30, 82-238`). Price only orders txs that are waiting in the same pass.
- **Pacer:** budget = block limit × ms since the slot started ÷ 150 ms − used. At 200 ms slots that is 200k CU per ms, **0 in the first ms** (`scheduler_controller.rs:520-545`). Queues, and so price, matter at slot start, window start and in busy blocks.
- **Conflicts:** a tx whose write-locked accounts sit on two worker threads is skipped this pass, while a lower-fee tx on the same coin can go (`thread_aware_account_locks.rs:126-203`).
  - INFERRED: every extra hot shared writable account (a busy tip account) raises that chance a little.
- **Durable nonce:** a leader keeps one queued tx per nonce account. A later copy is dropped unless it has strictly higher priority and the first one is still queued (`receive_and_buffer.rs:465-518`). Our variants differ only by tip; the tipless one has the best priority.

**Slot timing (CODE)**
- `block_timeout` = 200 ms × (index in window + 1) − 6 ms − 50 ms, from the window clock (`core/src/block_creation_loop.rs:78, 84, 455-461`).
  - **Block 1 ends 144 ms after the window starts**, block 2 at 344, block 3 at 544, block 4 at 744.
  - The clock starts at ParentReady (`votor/src/consensus_pool_service.rs:469`) or at fast handover (`core/src/replay_stage.rs:4413`). Block 1 also waits for the parent's replay (`block_creation_loop.rs:1108-1240`).
- Leaders buffer txs that arrive up to 20 slots (~4 s) before their window and schedule them by priority once it starts (`decision_maker.rs:62-102`). This is where our higher CU price helps: copies sent ahead to the next leader at a window boundary.

**CU (CODE)**
- At 200 ms slots: **30M CU per block, 12M per writable account** (`runtime/src/slot_params.rs:171-181`). A tx over the limit waits for the next slot.
- Our buy scores ≈ 4.2M against haqq's ≈ 1.4–1.8M (5M µL × 100k vs 0.00012 SOL × 66k). **We already outbid them ~3×; they win by arriving first.**

---

## 3. Jito (JitoLabs)

**How a tx gets in (CODE unless marked)**
- Gossip TPU priority: BAM node > Jito relayer (after 60 s of heartbeats) > own TPU (`jito-solana/core/src/proxy/fetch_stage_manager.rs:265-307`).
  - While BAM or relayer is advertised, packets to the validator's own TPU are dropped (`:424-426`).
- **Relayer:** `packet_delay_ms` default **50** (`jito-relayer/transaction-relayer/src/main.rs:132-134`). Each packet is held that long, the loop wakes every 5 ms, so 50–55 ms (`forwarder.rs:113-129`). The block engine gets the packet at once.
  - It only forwards to validators leading within 5 slots (`relayer/src/relayer.rs:512-516`). Default relayer TPU port 11228 (`main.rs:78`).
- **Block engine** (closed source): bundles in **50 ms auction ticks**, ranked by tip ÷ requested CU (DOC docs.jito.wtf). Block-engine packets enter the validator **without** the relayer hold (`core/src/proxy/block_engine_stage.rs:970-1009`).
- **Bundles:** one thread, block-engine order. Up to 10 queued bundles pre-lock their accounts and the normal scheduler skips any tx touching them (`bundle_stage.rs:629-700`, `greedy_scheduler.rs:271-302`). All-or-nothing.
- **Slot 1 of a window:** under fast handover, bundles and the tip crank wait for ParentReady; plain txs do not (`block_creation_loop.rs:609, 960`; `decision_maker.rs:70-84`).

**What our data shows (MEASURED)**

| | Jito own TPU (107 leaders) | Jito relayer (39) |
|---|---|---|
| our attempts | 66 | 26 |
| our same-slot landing (feed) | **43 ms** | **72 ms** |
| send → seen (same slot) | 39 ms | 66 ms |
| first reacting rival (block clock) | 26.5 ms | 24.9 ms |

- Single-copy landings (nonce runs):
  - Own-TPU Jito: staked-rpc landed 21 (1 fill; typical 38–54 ms), helius 10 (10 fills; half at 27–47 ms, half at 119–176 ms), nozomi 5 (0 fills).
  - Relayer Jito: nozomi 10 (0 fills, 62–131 ms), helius 4 (3 fills), staked-rpc 0.
- Block 1 is the smallest block of the window on Jito only (median 295 vs ~340 txs on own-TPU leaders; 246 vs ~335 on relayer leaders; 38k blocks). BAM, Harmonic and Firedancer have their *largest* block in slot 1.
- Market-wide, fastest reacting-buy paths on Jito leaders (median, block clock; mixes path speed with bot quality):
  - own TPU: glaive 28, flashblock 31, soyas 34, helius 35, speedlanding 37, nozomi 38, none 42, jito 53.
  - relayer: solami_beam 16, soyas 22, glaive 26, speedlanding 36, nozomi 43, helius 47, none 48, jito 48.

**Reading (INFERRED)**
- Our TPU copies to relayer leaders pay the 50 ms hold.
- Our 0.001 Helius copy is "Sender Max": its Jito leg is a revert-protected bundle (so it only ever lands fills) and it passes a tip buffer, hence late.
- Nozomi copies on Jito land failures late: staked leg through the relayer, plus Nozomi's server-side retries "until confirmed or expired" (DOC). With a durable nonce that means until our nonce moves.
- Turn-start spills: block 1 is short (CODE) and on Jito also thin.

---

## 4. BAM (AgaveBam, FireBAM)

**How a tx gets in**
- CODE: gossip TPU = the BAM node's (+6 port). The validator's own TPU, the relayer and the block-engine stage are all off while BAM is connected (`fetch_stage_manager.rs:265-276`; `scheduler_controller.rs:315-331`; `block_engine_stage.rs:247-250`).
- CODE: the gossip label AgaveBam is shown only while BAM is connected (`bam_manager.rs:132-165`).
- MEASURED (gossip): 17 BAM node IPs serve 360 AgaveBam leaders.
- DOC: the BAM node runs auction rounds (25 → **20 ms** since the 200 ms slots).
  - Maker-plugin txs always go first. Then bundles and plain txs compete on **(priority fee + Jito tip) ÷ requested CU**.
  - Bundles are simulated and dropped if any tx fails.
  - Block-engine bundles and `sendTransaction` are forwarded straight to BAM (DBI), skipping the block engine's ~50 ms hop.
- CODE: the validator executes the node's batches in **strict arrival (FIFO) order**: `next_fifo_priority` (`banking_stage/transaction_scheduler/bam_receive_and_buffer.rs:906-916`), at most 8 batches in flight (`bam_scheduler.rs:63, 347`). Standalone txs have `revert_on_error = false`, so a failing buy lands and pays its fee.
- CODE (FireBAM): pack drops non-vote TPU txs and runs BAM batches strictly in order (`firebam/src/disco/pack/fd_pack_tile_bam.c:967-977`, `fd_pack_bam.c:194-300`).
- DOC: the BAM node drops validators whose gRPC round trip is above 30 ms, so a node sits near its validators.

**What our data shows (MEASURED)**
- Our BAM attempts: same-slot 90%, landing 29 ms (25 same-slot), fills 48%. Spill by window slot 2/23, 3/23, 2/23, 2/20 (no turn effect).
- Copies: nozomi 19 landed / 17 fills (30.5 ms); staked-rpc 20 / 2 (32.8 ms).
  - INFERRED: nozomi's BAM copies are revert-protected (it lands almost only fills), so failures land via the unprotected staked-rpc copy.
- Of the txs right before our landed BAM buys, 38% paid a higher CU price (Jito: 1%), i.e. they won inside our round; 98% of those right after paid less.
- AMS at 15M µL/CU vs 5M on BAM: same-slot landing 29 vs 23 ms (n=16/31). No sign that more fee helps; rivals are in an earlier round.

**Preconfirmations (DOC)**
- Emitted when the leader commits a batch, "before those transactions are shredded", "p50 advantage of 5–10ms" over shred streams.
- Sold via Helius (`preconfSubscribe`, WebSocket `wss://beta.helius-rpc.com`, paid plans, 10 credits per message, 300 minimum per billed slot) and Triton.
- BAM messages carry no execution status (it is a commit, not a result).

---

## 5. Harmonic (Salsa = HarmonicAgave, Samba = HarmonicFiredancer)

**How a tx gets in**
- CODE: gossip TPU = Harmonic's relay, the "Remote TPU" (`salsa/harmonic-scheduler/src/admin_rpc.rs:156-236`). DOC hosts `{fra,ams,lon,ewr,tyo,sgp,slc}.tpu.harmonic.gg`.
  - The relay fans flow to the validator and every connected builder. No delay is documented ("no artificial latency").
- CODE: the validator's own TPU copies are used only in fallback (`harmonic-scheduler/src/validator/scheduler.rs:476-531`).
- DOC: one builder per validator, streaming microbatches. Strategies `fifo | fba | mrev`, default **fba** (CODE `config.rs:45-57`).
  - **FBA:** "collects all incoming transactions over a 50ms buffer", sorted "by descending priority fees and tips"; "if two transactions arrive 1ms apart inside the same 50ms window, they are treated as if they arrived simultaneously".
  - 77 of 87 Harmonic validators run FBA, 6 MREV (DOC explorer, via the web pass).
- CODE: the builder's stream must start by **50% of the slot** (`BLOCK_STAGE_TIMEOUT_PERCENT`, `scheduler.rs:34-36`; 75% on the newer `master-harmonic` branch), otherwise the validator schedules its own copies first-in-first-out. Votes join at 94%.
  - Builder txs run in builder order (`block_stage.rs:87-124`); bundles are revert-protected, standalone txs land failed (`block_engine.rs:213-233`).
- CODE (Samba): in block mode pack schedules only the builder stream, strictly in order. It falls back mid-slot if no block started (`samba/src/disco/pack/fd_pack.c:2826-2877`).
- DOC: "Harmonic tips are simply priority fees". There is a public bundle endpoint `https://fra.be.harmonic.gg/api/v1/bundles`. Single-tx revert protection is kept "only while maintaining a high success rate".

**What our data shows (MEASURED)**
- HarmonicAgave: 38 ms (36 same-slot), fills 50%. HarmonicFiredancer: 48.5 ms, fills 34%; window slot 1 spilled 4 of 6.
- Copies on Harmonic: nozomi 23 fills / 3 fails (43.5 ms); staked-rpc 2 / 29 (78 ms); helius-swqos 0 / 3 (108 ms).
- Market-wide fastest reacting paths (median): speedlanding 35, nozomi 37, astralane 42, none 42, helius 43, jito 65.
- Order by CU price inside close pairs: 66% (≤ 5 txs apart), 70% (6–20 apart). Partial sorting, as FBA buffers predict.
- Our neighbours: 34% of the txs right before our landed buys paid more; 91% of those after paid less.

**Reading (INFERRED)**
- With 50 ms buffers, a rival that reaches the builder before the buffer tick lands one buffer (up to 50 ms) ahead of us, whatever the fee.
- Nozomi is fast here; a Harmonic co-founder also co-founded Temporal, which runs Nozomi (DOC chaincatcher).
- Preconfs would let us see the dump when its batch is selected, which is before it executes.

---

## 6. Firedancer (and the Firedancer side of FireBAM, Samba)

**How a tx gets in (CODE, firedancer v26.10.4)**
- QUIC 9007 and **UDP 9001**. **No stake-weighted QoS** ("Firedancer does not apply receive limits for TPU-QUIC nor TPU-UDP", DOC).
- QUIC retry is on, so a cold connection costs ~2 round trips (`app/firedancer/config/default.toml:1496-1544`).
- No batching wait before pack. No forwarding: a non-leader keeps up to 65,524 txs for its own slot.
- Jito bundle tile: block-engine bundles and packets go into pack (`disco/bundle/fd_bundle_client.c:207-245, 726-754`).

**Pack (CODE `src/disco/pack/fd_pack.c`)**
- Priority = rewards ÷ requested cost (same parts as Agave, incl. the 16,384 default loaded-data cost). Tips not counted.
- One tx per microblock; each loop schedules the best tx onto an idle execution tile. Default strategy "balanced" holds only when the block runs ahead of its fill line.
  - So: **first come, first served unless txs wait together** (busy tile, window start, an account with > 64 waiting txs goes to a side queue).
- **Nonce:** one waiting tx per (nonce account, authority). An equal-or-better later copy replaces it, a worse one is rejected, and **a waiting bundle copy blocks every normal copy** (`fd_pack.c:1508-1514, 1683-1698`).
- Instruction errors (our guard fail) land with fees. Bundles are all-or-nothing.
- **Shreds leave in ~61.6 KB bursts with no time flush** (`disco/shred/fd_shred_batch.h:59`), so everyone sees a Firedancer leader's txs in lumps.
- Slot timing under Alpenglow: the same 144 / 344 / 544 / 744 ms deadlines (`discof/replay/fd_replay_tile.c:1784-1792`).

**What our data shows (MEASURED)**
- 23 ms (first rival 29); same-slot 92%. landx (UDP) 5 landings / 2 fills at 24 ms; nozomi 2 / 0 at 16 ms.
- Order by CU price in close pairs 62%. Market-wide fastest: nozomi 42, jito 45, 0slot 45, astralane 46.

---

## 7. Rakurai

**CODE (`rakurai-validator`, a jito-solana fork; the scheduler is a closed library)**
- Packets get a "don't delay" flag only if they come via a Jito relayer (`core/src/proxy/relayer_stage.rs:426-428`) or from an IP in `quic_config.json` (`fetch_stage_manager.rs:514-533`). The flag is `PacketFlags::DELAY` (`rakurai-solana-sdk/packet/src/lib.rs:56, 274`).
  - INFERRED: everything else is held by the closed scheduler. It is linked as `rak_scheduler_*` (`core/build.rs:46-109`).
- Bundles from the Jito block engine and from TIN landing services ("validators connect to all registered landing services", DOC), in a priority queue. Zero-tip bundles are dropped (`bundle_stage/bundle_storage.rs:883-911`).
- A Rakurai tip adds "virtual priority" (DOC). P2C streams other people's txs to paying searchers (DOC).

**MEASURED**
- 7 of 8 of our buys landed one slot later, 191–224 ms after the dump, even with ≥ 80 ms left in the block. The one same-slot landing was in the window's last slot.
- Rivals got into the dump's block via helius (haqq at 0.0002), astralane, jito and speedlanding, plus a zero-fee, no-tip group (DF7e, HLU8: bundles or backruns).
- Market-wide: Rakurai's block 1 is tiny (median 174 txs) and block 4 huge (498). The first reacting buy lands in the dump's slot only 26–33% of the time in window slots 1–3, vs ~40% on other clients.

---

## 7b. Our measured gaps, explained

| What we saw (MEASURED) | Why (CODE / DOC → INFERRED) |
|---|---|
| Jito slow (54 ms vs 26) | 27% of Jito slots hold plain txs 50 ms in the relayer; the 0.001 Helius copy sits in a tip buffer; block 1 ≤ 144 ms |
| Nozomi on Jito lands only failures (15 of 15; the 10 on relayer leaders at 62–131 ms) | staked leg held by the relayer + Nozomi retries until confirmed/expired (nonce keeps it valid); its builder leg (Jito bundle) cannot land a failure, and on fills it is slower than our helius copy |
| jito-bundle landed 1 of 54 Jito fires | 50 ms block-engine ticks; bundles wait for ParentReady in block 1; all-or-nothing, so a failing buy never lands |
| helius-swqos never won on Harmonic | swqos-only = "single SWQoS path" → Harmonic relay → builder, slower than nozomi's builder path; keyless 1 req/s → our 429s (15 of 24 were swqos) |
| staked-rpc lands mostly failures (BAM 18/20, Harmonic 29/31) | the nozomi copy there is revert-protected, so it lands only fills; when the buy fails, only the unprotected staked copy can land. Also possible: CK fallback route over its staked cap |
| Rakurai 7/8 next slot | closed scheduler holds TPU packets not from a relayer or whitelisted IP |
| Turn-start spills (Jito 15/24) | block 1 of a window records ≤ 144 ms (all Agave-family and Firedancer) |
| BAM is our best (29 ms) | no relayer; BAM node within 30 ms of its validator; 20 ms rounds rank our high CU price well |
| Firedancer fast (23 ms) | no stake QoS, UDP accepted, pack is first-come; no relayer |

## 7b2. Our providers → which door they use (DOC where quoted, else INFERRED)
- **Helius Sender Max (tip ≥ 0.001)**: "all pathways (Helius, Jito, Harmonic, Rakurai, etc.)" plus a "priority tip buffer for top of block" (DOC).
  - Jito: staked TPU + block-engine bundle (revert-protected).
  - BAM: BAM node.
  - Harmonic: its Harmonic pathway.
  - Rakurai: TIN.
  - Our 0.001 "helius" copy is this tier.
- **Helius swqos-only (min 0.000005)**: "single SWQoS path" (DOC), i.e. the leader's gossip TPU: relayer, BAM node or Harmonic relay. Keyless = 1 request/s per IP per region (DOC).
- **Nozomi**: "block builder (Jito or Harmonic)" plus "staked connections" (DOC); the tip drives builder ordering. It retries server-side and warns that nonces may be deprioritized.
  - INFERRED: its builder leg is why it lands only fills on BAM and Harmonic.
- **Constant-K staked**: SWQoS to "the next 4 leaders", one attempt; over the plan's staked cap it falls back to CK's own node, rebroadcasting every 420 ms (DOC).
- **Jito block engine**: bundles in 50 ms ticks. `sendTransaction` "forwards your transaction directly to the validator" (DOC) and skips the relayer (CODE). On BAM leaders, both are forwarded into BAM (DBI).
- **Bolt**: dedicated SWQoS, "ordering purely tip-based", no Amsterdam region (DOC).
- **Astralane**: "direct routing to leading block builders like Harmonic and BAM" (DOC).
- **SpeedLanding**: dedicated SWQoS over QUIC, fra/ams (DOC).
- **0slot**: dedicated SWQoS (DOC). Slow everywhere in market data (median 45–69 ms).
- **LandX, soyas, solami_beam, flashblock**: no public docs. LandX is UDP from our side.

## 7c. CU limit (all clients)
- **Priority uses the requested CU, not consumed CU,** on Agave/Jito/Rakurai (`transaction_priority.rs`), Firedancer (`fd_pack_cost.h:505-564`), BAM (DOC "per requested compute") and Nozomi ("requesting more compute units than your transaction uses dilutes it", DOC).
- At a fixed CU price, the CU limit barely moves priority (fee and cost scale together).
- At a fixed total spend, a lower limit means a higher CU price, which is what BAM, Harmonic and Firedancer rank by (MEASURED 65–74% when per-CU and total disagree).
- **Free gain: set `SetLoadedAccountsDataSizeLimit`.** Without it, cost carries +16,384 for the 64 MiB default, so the same fee buys ~14% more priority on Agave and Firedancer (CODE). Too small a value fails the tx: measure our loaded bytes first.
- **Fit:** 30M CU per block and 12M per writable account at 200 ms slots. The requested CU is reserved until execution, then corrected (Agave) or rebated (Firedancer). Only a hot coin with many large-limit spam txs gets near 12M; an earlier study found no account-limit spills.
- **Our buy needs up to ~93k CU** (one out-of-CU at 100k), so the limit cannot drop much.
  - The bigger saving is the tx shape. Most rivals create no token account in the buy (21 of 22 in the tx-anatomy study); haqq uses a plain InitializeAccount3. We use the ATA program (GetAccountDataSize / InitializeImmutableOwner / InitializeAccount3).
  - INFERRED: ~10–20k fewer CU means a higher per-CU bid at the same cost. This touches the sell path too, so it needs OK.

---

## 8. How to test (cheap first)

**A. Free, data only (no sends)**
1. Re-label each attempt by its leader's TPU front at the time (gossip): relayer / own / BAM node / Harmonic relay.
2. Bin landing delays by client to look for BAM 20 ms rounds and Harmonic 50 ms buffers.
3. Read the Harmonic leader's strategy memo ("FBA"/"MRV"/"FIF") from its tip-crank tx and split Harmonic results by strategy.
4. Engine log fields: dump's window slot (slot % 4), ms since the window's first shred, Constant-K `X-CK-Tx-Route`, Helius status codes.

**B. Shadow feeds (no sends, owner OK for spend)**
5. BAM preconfirmations (Helius) and Harmonic Preconfs (Triton): log, per dump on those leaders, how far ahead of our shred feed it appears.
   - Go live only if the median lead ≥ 5 ms.

**C. Probes (fail-by-design, ~0.0005 SOL each; dip14 flags)**
6. One path per probe, one client per run, ~20 per path:

       --dip-probe 80 --dip-probe-clients jito --dip-probe-paths staked-rpc,helius-swqos,nozomi,<new> --dip-probe-tipless on

   - Same for `harmonic` and `bam`. ~0.04 SOL per client (0.08 with tipless twins).
   - These flags are in the dip14 build (fixes agent; built, not deployed). It also needs `--route-by-client --fast-send` and the usual config.
   - A probe that never lands through a path means "revert-protected", not "slow". The tipless twin (D3) tests exactly that.
7. Then **lock-only probes** (needs an engine change): they also measure the protected paths, at ~0.00002 SOL each.

**D. Live A/B (one server each, owner OK)**
8. Per-client route table from A–C: BAM tip → Jito tip account; Jito → keyed helius swqos-only, no Sender Max; Harmonic → nozomi first, no swqos/staked; Firedancer → no bundle copy; Rakurai skipped.
   - Pass if the median landing per client drops and the fill rate rises at an equal or lower cost per fill.

## 8b. Experiment cards (ranked within each client; effects INFERRED)
Fill gains use the SPEED_TRUTH guard curve: landing 10 ms → 85–93% pass, 20 → 76–81%, 30 → 61–68%, 40 → 43–59%, 50 → 38–47%.

**BAM**
- **B1 Preconf trigger.**
  - Effect: −5 to −10 ms on 37% of slots → +8–12 fills / 309.
  - Cost: Helius credits (≥ 300 per billed slot; a broad 2 h shadow is a few million credits; check the plan).
  - Risk: a committed dump can still fail. Our +5% guard then fails our buy (0.0005).
  - Measure: shadow lead vs shred feed, then A/B fill rate on BAM leaders.
- **B2 Bid split on the staked copy** (Jito tip instead of CU price).
  - Effect: same rank; a failed landing costs ~0.0001 instead of 0.0005.
  - Cost: none. Risk: if the BAM node is down, a Jito tip does nothing for a plain tx.
  - Measure: fail cost per attempt, landing unchanged.
- **B3 DBI single-tx bundle.**
  - Effect: failed buys free; maybe a few ms.
  - Cost: allowlist form. Risk: "for testing", may change.
  - Measure: which copy lands, latency.
- **B4 Drop staked-rpc on BAM.**
  - Effect: saves ~18 failure fees / 309 (~0.009 SOL); loses ≤ 2 fills.
  - Measure: fills and fail cost, A/B.

**Jito**
- **J1 Relabel by TPU front** (free).
  - Effect: confirms the +29 ms on relayer leaders with more data; decides J2/J3.
- **J2 Block-engine `sendTransaction` copy on relayer leaders.**
  - Effect: up to −50 ms there (6% of slots) → +3–8 fills / 309.
  - Cost: ≥ 1000-lamport tip per landed tx. Risk: block-engine hold unknown (closed).
  - Measure: one-path probes on relayer Jito leaders.
- **J3 Helius copy on Jito = keyed swqos-only (tip 0.000005) instead of Sender Max (0.001).**
  - Effect: the slow 119–176 ms helius landings should go; −0.001 SOL per helius fill.
  - Risk: loses Sender Max's revert protection on Jito.
  - Measure: probes, then A/B.
- **J4 Window-slot-1 timer** (log only).
  - Effect: no fills by itself; stops blaming paths for structural spills; feeds the EV model.
- **J5 Skip relayer-fronted Jito leaders**, only if J2 fails.
  - Effect: −26 attempts / 309 (they filled 9).
  - Risk: loses those fills; check their P&L first.

**Harmonic**
- **H1 Preconf trigger (Triton).**
  - Effect: up to one 50 ms buffer earlier on 30% of slots.
  - Cost: unknown (Triton). Measure: shadow lead.
- **H2 Drop helius-swqos and staked-rpc on Harmonic.**
  - Effect: saves ~29 failure fees / 309; loses ≤ 2 fills.
  - Measure: A/B fills and fail cost.
- **H3 Speedlanding / astralane copy.**
  - Effect: may join an earlier buffer.
  - Cost: their minimum tips (0.001 / ~0.00001).
  - Measure: one-path probes on Harmonic leaders.
- **H4 Harmonic block-engine single-tx bundle.**
  - Effect: failed buys free.
  - Risk: access cut if reverts stay high. Low volume only.

**Firedancer**
- **F1 No Jito-bundle copy to Firedancer leaders.**
  - Effect: removes a nonce-blocking case. Cost: none. Measure: same-slot rate.
- **F2 Direct UDP copy to the leader TPU (:9001).**
  - Effect: a few ms on 7% of slots. Cost: none. Risk: none on the chain side.

**Rakurai**
- **R1 Skip** (flag exists). Effect: −8 attempts / 309, of which 3 filled late. Cost: none.

**All**
- **X1 Lock-only probes** (engine work): ranks protected paths at ~1/25 of today's probe cost.
- **X2 Constant-K route header and Helius key** (log/config): explains the late staked landings; ends the 429s.
- **X3 Leaner buy tx** (no ATA program): ~10–20k CU less → higher per-CU bid at the same cost (BAM, Harmonic, Firedancer). Touches the sell path.


---

## 9. Sources

**Code** (shallow, read-only, `/home/moiz/sniper-data/clients_src/`, ~650 MB; nothing built or run):

| folder | repo @ version |
|---|---|
| agave | anza-xyz/agave @ v4.3.2 |
| jito-solana | jito-foundation/jito-solana @ v4.3.2-jito (Jito + AgaveBam) |
| jito-relayer | jito-foundation/jito-relayer @ master |
| mev-protos, bam-protos, bam-plugins, bam-dbi, jito-docs | Jito protocol defs and docs @ master |
| firedancer | firedancer-io/firedancer @ v26.10.4 |
| firebam | jito-foundation/firebam @ v26.10.4 |
| salsa | harmonic/salsa @ v4.3.2-harmonic.1 |
| samba | harmonic/samba @ v26.10.4-harmonic |
| harmonic-validator-protos, harmonic-searcher-protos, harmonic-tx-sender | Harmonic @ main |
| rakurai-validator | rakurai-io/rakurai-validator @ release/v4.3.2-rakurai.0 |
| rakurai-solana-sdk | rakurai-io/solana-sdk, sparse (packet flags) |
| rakurai-tin-samples | rakurai-io/tin_sample_servers @ development |

**Docs**
- Slots and Alpenglow:
  - 200 ms slots: solanacompass.com/news/solanas-200ms-slot-time-is-live-on-mainnet-at-epoch-1053-completing-simd-0525
  - Alpenglow live: solanacompass.com/news/solana-alpenglow-is-live-on-mainnet-as-anza-retires-towerbft-at-slot-459653000
- Jito / BAM:
  - docs.jito.wtf/lowlatencytxnsend (50 ms ticks, sendTransaction, tips)
  - bam.dev/blog/introducing-bams-direct-bundle-ingest/ (rank = fees + Jito tips per requested CU; ~50 ms block-engine hop)
  - bam.dev/blog/bam-changelog-sept-23-oct-9/ (20 ms rounds; first-slot BBR delay fix)
  - bam.dev/blog/update-on-bam-readiness-for-alpenglow-on-mainnet/ (maintenance mode)
  - bam.dev/docs/bam/preconfirmations/
  - helius.dev/docs/pre-confirmations/overview
- Harmonic:
  - docs.harmonic.gg (concepts/scheduling-strategies, streaming-mode, harmonic-architecture; searchers/harmonic-bundles; run-a-validator/setup, endpoints)
  - harmonic.gg/preconfs
- Rakurai: docs.rakurai.io (transaction_inclusion: readme, setup_guide, tips, post_pack)
- Firedancer: docs.firedancer.io/guide/protocol/transaction_ingress.html
- Providers:
  - Helius: helius.dev/docs/sending-transactions/sender (Sender Max ≥ 0.001 = "priority tip buffer for top of block"; swqos-only min 0.000005; keyless 1 req/s, key 50 req/s)
  - Nozomi: use.temporal.xyz/nozomi/tipping-and-faq and /nozomi/troubleshooting (tip drives builder ordering; nonces may be deprioritized; failure rate lowers priority; server-side retries)
  - Constant-K: docs.constant-k.com/rpc/sending-transactions/ (staked caps per second, fallback, `X-CK-Tx-Route`)
  - Others: astralane.gitbook.io, 0slot.trade/docs.html, glaive.trade/docs, speedlanding.trade/docs.html, bolttx.io/en/docs
- Third-party (LOW TRUST): github.com/EvgeniuGlinsky/inside-the-block (10-22 probes: sent 30 ms apart → arrival decides on every client; sent together on a shared account → fee decides).

**Our analysis** (scripts in `ops/dip/speed/clients/`, output in `/home/moiz/sniper-data/clients_study/`)

| script | what it does |
|---|---|
| c1_tables.py | per client: turn slot, path, time left |
| c2_rakurai.py | Rakurai attempts tx by tx |
| c3_market.py → market.json | 485 recording files, 189k sells ≥ 1 SOL, 678k blocks |
| c4/c5/c7/c12 | relayer vs own TPU |
| c6_market_tables.py → market_tables.txt | same-slot share, paths, order vs price, block sizes |
| c8/c10/c13 | order vs CU price |
| c9, c11 | next-slot index, time-left model |

**Our data:** `/home/moiz/sniper-data/speed_truth/attempts.csv` (309 live attempts) and `chain_txs.json`; leader books `ops/dip/speed/leaders/leader_rtt_new.json` and `ops/region/leader_rtt_ams.json` (gossip snapshot 10-23).

**Caveats**
- Leader client and TPU front come from one gossip snapshot (10-23). Labels can change; AgaveBam shows only while BAM is connected.
- BAM nodes were in maintenance around Alpenglow (~10-21). Our BAM ordering signature (79%) and our fast BAM landings say BAM was up for our window, but this is unconfirmed (DOC).
- Market path medians mix path speed with bot quality, and the block clock is an index clock.

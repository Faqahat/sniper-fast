# Market scan: what we can buy to land faster in Frankfurt / Amsterdam

10-25 ~20:45 PKT. Public web and docs only: no sign-ups, keys, purchases, forms or contact. Nothing on our servers or code was touched.
Owner's ask (10-25 ~19:15 PKT): "explore our realistic options to reduce our landing time, idc what it takes ... infra upgrades or services, whatever it takes."

**Labels**
- **MEASURED-us**: our own data. Mostly the two sister studies in this folder (WHERE_TIME_GOES.md, HOW_PROS_LAND.md) and CLIENTS.md.
- **MEASURED-by-X**: someone else measured it.
- **CLAIMED**: the vendor says so.
- **3P-SDK**: endpoint or tip account read from an open-source bot SDK, not from the vendor [34].
- **INFERRED**: my reading.
- **NOT FOUND**: searched, not public.

[n] = sources in §9. SOL ≈ $100.6 (CoinGecko, 10-25 [87]). "Near" slots = leaders under 2 ms from one of our servers (our gossip snapshot of 10-23).

---

## 0. Verdict

**For about $4K a month, the best 3 moves are:**
1. **Fast lanes per leader type.** Cost: tips only, maybe +$0.2K/month.
   - Add soyas, glaive, Solami Beam and Falcon copies. Run the staged jito-tx, flashblock and speedlanding paths, plus 0slot for Firedancer leaders.
   - Pros' landed copies through these lanes take 18–32 ms on Jito leaders (MEASURED-us, HOW_PROS_LAND E2). We take 58 ms on own-TPU Jito leaders, 94 ms on relayer-fronted ones and 69 ms on Firedancer.
   - Expected: **−20 to −30 ms on own-TPU Jito leaders, −50 to −70 ms on relayer-fronted ones, about −30 ms on Firedancer, and −3 to −7 ms on BAM / Harmonic** (INFERRED: that we get the same speed).
   - Worth about **+1.2 to +4.0 SOL/day** (WHERE_TIME_GOES §8).
2. **Harmonic preconfirmations from Triton.** About $2.7K/month for Frankfurt only, $3.6K for FRA + AMS, if streamed 24/7.
   - Triton measured Harmonic preconfs at ~15 ms ahead of Geyser (p50, 99% of the time) [30]. Our shreds are ~2 ms ahead of Geyser, so the lead is **about −13 ms on Harmonic slots** (INFERRED).
   - Harmonic is 30% of stake and 19.5% of our near slots. It runs 50 ms batches, so this lead can move us a whole batch earlier.
   - Buy only after a shadow log shows a lead of 10 ms or more. Triton needs a sales call (your decision).
3. **Constant-K raw UDP shreds (ShredQuasar).** $299/month for one region, about $499 for two [52].
   - **−0.7 to −0.9 ms on every slot** (MEASURED-us, 10-19 trial). That is most of DoubleZero's 1.4 ms at a fifth of the price.

**Free, and worth doing first** (send-path changes need your OK):
- **Helius:** get an API key and use `swqos_only` on Jito leaders instead of Sender Max.
  - Without a key the limit is 1 request/s per IP per region, and 429s count against it [18]. We hit 24 of them.
  - Sender Max goes into a "priority tip buffer for top of block" [18]. Our Sender Max fills on Jito took ~120 ms. Pros using Helius on Jito land at 34 ms (MEASURED-us).
- **bolt:** BoltTx turns `anti_mev` on and retries 3 times by default [41]. Our bolt landings took 138–214 ms (MEASURED-us). Turn anti-MEV off or drop the path. Also check which service our "bolt" really is (§8).
- **Allowlist forms:**
  - BAM Direct Bundle Ingest [6]: bundles are revert-protected, so a failed BAM buy would cost 0 instead of ~0.0005 SOL.
  - Harmonic authenticated bundles [10].
  - Both are free.
- **Firedancer:** add a direct UDP copy to the leader's TPU port 9001. Firedancer has no stake QoS (CLIENTS.md §6).

**Optional, roughly break-even on today's numbers (test first):**
- Helius BAM preconfs: ~−6 ms on BAM, $1.2–3K/month.
- DoubleZero Edge: −1.4 ms, $1,500 per seat per region.
- Dedicated bare metal in Frankfurt: maybe −1.5 ms median on FRA's feed wait, ~€400/month.
- A London edge server: London is ~8–10% of slots and 5.7 ms from our Amsterdam box; ~$1.5K/month.

**Don't buy:**
- **A host move inside FRA/AMS.** Our Cherry boxes are 0.10–0.18 ms from the main relays (MEASURED-us) over Cherry's direct link to TeraSwitch [70], where nearly all relays sit [89]. Gain ≤ 0.3 ms.
- **Stake, rented SWQoS or our own validator.**
  - Since Agave 4.0, stake only matters near 95% of TPU capacity [79], and Triton found staked ≈ unstaked at p50 [28].
  - A validator pays 0.8 SOL per epoch in VAT (about 24 SOL/month) [69], plus hardware, and needs ≥ 8.5K SOL of stake [79].
- **bloXroute** ($1,250+/month) and **NextBlock** ($249+/month). Neither is among the fast routes on chain.
- **Paladin** (dead), **Raiku** (1 validator) and **Rakurai TIN** (1.1% of slots).
- **Jito ShredStream**: shut down Sep 5, 2026 [2].

**Things that changed this month:**
- **Jito ShredStream** is gone. Jito points users to DoubleZero Edge [2].
- **Jito relayers:** Jito switched off its own relayers in Aug 2025 [4], and the relayer repo is archived [5].
  - The 50 ms hold now exists only where an operator runs its own relayer: 5.7% of slots near us, 4.4% in AMS and 1.3% in FRA (gossip 10-23).
- **BAM:** nodes went into maintenance for Alpenglow and come back "gradually", with no public date [7][8].
  - Our gossip at 10-23 21:17 UTC still showed AgaveBam on 36.5% of slots, with BAM-node TPUs. That means connected (CODE, CLIENTS.md §4).
- **Harmonic** is now 30.4% of stake (88 validators) [12], up from 16.8% in Feb [92].

---

## 1. Ranked moves for our case

"Worth" = WHERE_TIME_GOES §8 SOL/day (INFERRED, for ranking only, not a forecast). Near slots from our 10-23 gossip.

| # | Move | Where it hits | Expected gain (evidence) | Worth | $/month | Effort | Risk | Cheap check first |
|---|---|---|---|---|---|---|---|---|
| 1 | **Fast lanes**: soyas, glaive, Solami Beam, Falcon + staged jito-tx, flashblock, speedlanding; 0slot on Firedancer | Jito own 11.7%, Jito relayer 5.7%, Firedancer ~2% of near slots; extra copies on BAM/Harmonic | Jito relayer 94 → ~22–45 ms; Jito own 58 → ~25–35; Firedancer 69 → ~36–40; BAM/Harmonic −3 to −7 (pros' landed copies, MEASURED-us; same speed for us INFERRED) | +1.2 to +4.0 SOL/day | tips only: 0.0001–0.001 SOL per landed buy (failed copies refund the tip); optional speedlanding Pro $199 | M: 4 sign-ups, QUIC clients, routes | L–M: young, opaque services | P1/P2 probes (PROBES_V2.md) plus the 4 new lanes, ~0.0005 SOL per landed probe |
| 2 | **Free fixes**: keyed Helius `swqos_only` on Jito; bolt anti-MEV off; DBI and Harmonic allowlists; Firedancer UDP :9001 | Jito, BAM, Firedancer | helius copy on Jito ~120 → ~34 ms (pros' helius); failed BAM buys cost 0 with DBI | included in #1 | 0 | L | L | in the same probes |
| 3 | **Harmonic preconfs** (Triton) | Harmonic 19.5% of near slots | ~−13 ms (INFERRED from Triton's ~15 ms p50 vs Geyser [30]) | ~+0.5 to +2.5 SOL/day (~¾ of the preconf row) | ~$2.7K (FRA) – $3.6K (FRA+AMS) 24/7; less if streamed only during runs | M: gRPC client + trigger | M: sales call; cost scales with slots; 33% share cap | metered trial, 2–4 h shadow log (~$5/h) |
| 4 | **Constant-K ShredQuasar** raw shreds | all slots | −0.7 to −0.9 ms (MEASURED-us 10-19) | ~+0.15 to +0.6 SOL/day (scaled from the DZ row) | $299 one region, ~$499 two | L (we already read UDP shreds) | L | 1-hour vendor trial in our feed-race harness |
| 5 | **BAM preconfs** (Helius `preconfSubscribe`) | BAM 16.5% of near slots | ~−6 ms (INFERRED from Triton's ~8 ms p50 vs Geyser; BAM CLAIMS 5–10 ms vs shreds [9]) | ~+0.15 to +0.8 SOL/day | ~$1.2K (FRA BAM only) – $3K (FRA+AMS) + $49 plan | M | M | self-serve 2–4 h shadow (~$4/h) |
| 6 | **Bare metal for FRA** (same Cherry site, if FRA is a VPS) | FRA fires (~80% of ours) | FRA feed wait 2.4 ms p50 / 8.3 p90 vs AMS 0.9 / 3.0 (MEASURED-us); maybe −1.5 ms p50 (INFERRED) | up to part of the engine row (+0.5 to +3.1) | €369–419 [71] | M | L | free: CPU steal + `--dip-feed-lag` on FRA |
| 7 | **DoubleZero Edge** seat again | all slots | −1.4 ms vs Kaldera, ~−0.6 ms over #4 (MEASURED-us 10-19) | +0.3 to +1.1 SOL/day | $1,500 per seat; FRA + AMS $3,000 [58] | L | L | only after #4, same harness |
| 8 | **More regions**: London edge first, then New York | London ~8–10% of slots (5.7 ms from AMS); far leaders ~⅓ of slots | London 5.7 → ~0.2 ms; on US/Asia leaders the best pros' fastest 10% land at 21–25 ms (MEASURED-us) | replay first | London ~$1.5K (box ~$450 + LON shreds $900 + gRPC) | M | M | free replay of London-leader dumps |
| – | **Not worth it**: host move in FRA/AMS; stake / SWQoS / own validator; bloXroute, NextBlock; Paladin, Raiku, Rakurai TIN | – | ≤ 0.3 ms; ~0 ms at p50 | ~0 | $450+; ~$2.4K VAT + HW + ≥ 8.5K SOL; $249–15K | – | – | – |

**How the value compares with the cost (INFERRED):**
- Moves 1–2 cost almost nothing and are worth the most.
- Move 3 pays only if the lead is near Triton's figure.
- Moves 5 and 7 are about break-even.
- Moves 3 and 5 both depend on shadow logs that cost ~$5 an hour.

---

## 2. Our baseline (what a purchase must beat), MEASURED-us

**Our landing vs the pros, by leader type** (block clock, HOW_PROS_LAND)

| Leader | Share of all slots (gossip 10-23) | Near us | Us | Fastest pro routes (median ms) |
|---|---|---|---|---|
| Jito, relayer-fronted | ~6% | 5.7% (AMS 4.4) | ~94 ms | solami 18.5, soyas 21.7, glaive 22.0 |
| Jito, own TPU | ~17% | 11.7% (FRA 10.3) | ~58 ms | glaive 24.4, falcon 28.9, soyas 30.2, flashblock 31.7, helius 34.3 |
| Firedancer | ~7% | ~2% | ~69 ms | 0slot 35.7, jito 35.9, flashblock 39.2, astralane 40.0 |
| BAM | ~38% | 16.5% | at par via nozomi (~29–34 ms) | nozomi 36.4, speedlanding 37.4, glaive 38.1 |
| Harmonic | ~30% | 19.5% | at par via nozomi (~31–32 ms) | speedlanding 35.2, soyas 35.6, nozomi 36.4 |

- These path medians mix path speed with bot quality.
- **Distance is not our problem** (WHERE_TIME_GOES §7):
  - relays 0.10–0.18 ms away; leaders' fronts 0.13 ms (median);
  - Constant-K is 0.62–0.65 ms from FRA;
  - co-located for 94% of fires.
- **Our engine** sends 3.2 ms after the first shred (median); 2.1 ms of that is waiting for the executed feed. A fix is staged (dip14/15).
- **Spills:** 24% of our buys land one block late.

---

## 3. Endpoints in Frankfurt / Amsterdam (for routes and probes)

| Service | Frankfurt | Amsterdam | Interface | Min tip | Tip accounts |
|---|---|---|---|---|---|
| soyas | `fra.landing.soyas.xyz:9000` (3P-SDK) | `ams.landing.soyas.xyz:9000` (3P-SDK) | QUIC only; client cert from a keypair; whitelisted [34][35] | 0.001 (3P-SDK) | 10, `soyas…` |
| glaive | `fra.glaive.trade` | `ams1.glaive.trade`, `ams2.glaive.trade` | JSON-RPC `/`, `/plain`, `/binary`; QUIC UDP 4000 (ALPN `solana-tpu`, SNI `glaive-intake`) [36] | 0.0001 | 6 |
| Solami Beam | `beam.solami.dev:11000` (QUIC), `beam-http.solami.dev` | same hosts (regional hosts unconfirmed) | QUIC (keypair cert, SNI `solami-beam`, 3P-SDK) + HTTP [37] | 0.0001 | 10–15, `…beam` |
| Falcon (Corvus) | `fra.falcon.wtf` | `ams.falcon.wtf` | HTTP :80 (`/binary`, `/plaintext`), QUIC :5000, raw UDP :9000 (key = first 16 bytes) [42] | 0.001 | 10, `Fa1con1…` |
| speedlanding | `fra.speedlanding.trade` | `ams.speedlanding.trade` | HTTP :80 (`/sendTx`, binary `/v1/sendTx`), QUIC :17778, `/ping` every 30 s [38] | 0.001 | 8, `spee…` |
| flashblock | `fra.flashblock.trade` (3P-SDK) | `ams.flashblock.trade` (3P-SDK) | HTTP POST `/api/v2/submit-batch`, token in `Authorization` (3P-SDK); QUIC docs 403 [39] | 0.0001 (3P-SDK) | 10, `FLaSh…` |
| 0slot | `de.0slot.trade` (SDK uses `de2.`) | `ams.0slot.trade` | HTTP; behind Cloudflare (extra hop, INFERRED) [40][55] | 0.001 | 22 |
| Lunar Lander | `fra.lunar-lander.hellomoon.io/send` | `ams.lunar-lander.hellomoon.io/send` | HTTP; QUIC :16888 (3P-SDK) [43] | 0.001 | 10, `moon…` |
| Node1 | `fra.node1.me` | `ams.node1.me` | HTTP, QUIC, UDP [44] | 0.001 (docs) / 0.0001 (3P-SDK) | `Node1…` |
| Stellium | `fra1.flashrpc.com` (3P-SDK) | `ams1.flashrpc.com` (3P-SDK) | JSON-RPC, token in path | 0.0001 | 5, `ste11…` |
| NextBlock | `frankfurt.nextblock.io` | `amsterdam.nextblock.io` | HTTP/gRPC; QUIC :11100 (fire-and-forget, no flags) [27] | NOT FOUND (samples 0.001) | 8, `Nextb…` |
| BlockRazor | `frankfurt.solana.blockrazor.xyz:443` (+ `-allnodes`, `-cherryservers`, `-aws`) | `amsterdam…`, `amsterdam-cherryservers…` | HTTP; gRPC :80 [33] | 0.0001 | 15 |
| Astralane | `fr.gateway.astralane.io`, `fr2` | `ams.gateway.astralane.io`, `ams2` | JSON-RPC, binary `/irisb`, QUIC :7000 [32] | 0.001 free tier | 17, `astra…` |
| Nozomi | `fra2.nozomi.temporal.xyz` (direct), `fra.` (Cloudflare) | `ams1.` (direct), `ams.` | binary `/api/sendBatch` on warm `http://` is fastest [24] | 0.001 | 17 |
| Helius Sender | `http://fra-sender.helius-rpc.com/fast` | `http://ams-sender.helius-rpc.com/fast` | HTTP; `?swqos_only=true` [18] | 0.001 Max / 0.000005 swqos | 10 |
| Jito block engine | `frankfurt.mainnet.block-engine.jito.wtf` | `amsterdam.mainnet.block-engine.jito.wtf` | JSON-RPC `sendTransaction` / `sendBundle` [1] | 1,000 lamports (bundles) | 8 |
| Harmonic bundles | `fra.be.harmonic.gg` | `ams.be.harmonic.gg` | gRPC + JSON-RPC, Jito-compatible [10] | "tips are priority fees" | Jito's tip programs |
| ERPC SWQoS | `swqos-fra2.erpc.global` | `swqos-ams1.erpc.global` | HTTP [48] | – | – |
| Everstake SWQoS | `fra-swqos.everstake.com` | `ams-swqos.everstake.com` | HTTP open 10 TPS; QUIC allowlisted [49] | 0.001 | – |
| OrbitFlare Apex | `fra.apex.orbitflare.com` | `ams.apex.orbitflare.com` | HTTP, QUIC [47] | 0.001 | – |
| bloXroute | `germany.solana.dex.blxrbdn.com` | `amsterdam.solana.dex.blxrbdn.com` | HTTP, WS, gRPC; QUIC needs mTLS [26] | 0.001 | 17, `bLx…` |
| ZAN | `fra.zan.top:21000` | none | QUIC, cert + key [50] | 0.0003 | 9 |

- **Security:** speedlanding's API key is a Solana keypair **secret** [38]. The soyas, Solami Beam and glaive QUIC certificates are built from a keypair. Use throwaway keypairs, never a trading wallet.
- **Tip labels to add** to our catalogue for the chain studies: `Fa1con1…`, `…beam`, `Node1…`, `ste11…`, `moon…`, `zan…`, `spee…`.
  - SVS Lightspeed uses single-holder, time-limited tip addresses, so it can't be labelled [51].

---

## 4. Send side: landing services

### 4.1 The lanes that win on Jito leaders (none has an independent 2026 benchmark)

**soyas** [35][34]
- New: about Dec 2025. Hubs in FRA, AMS, NY, LON and TYO. Partner of MonkeyKingBot and AKBotPro.
- Reaches leaders via "our high-stake infrastructure" / "staked nodes" (CLAIMED). Stake size and any Jito or relayer path: NOT FOUND.
- Pricing: tips only, no subscription (CLAIMED; read from the search engine's copy of soyas.xyz). "private QUIC endpoints and whitelisted access".
- Rate limits, trial, revert protection and nonce policy: NOT FOUND.
- Pros' soyas copies (MEASURED-us): 21.7 ms on relayer-fronted Jito leaders (14 wallets), 30.2 ms on own-TPU Jito, 35.6 ms on Harmonic.

**glaive** [36]
- Keeps "persistent connections to current and upcoming slot leaders" and fans out to several upcoming leaders.
- Ranks by priority fee "in short auction intervals" (length NOT FOUND): "your priority fee matters more than the Glaive tip".
- Access: UUID key; new keys get 10 TPS (429 when over). MEV protection is off by default.
- Price: no plan listed (NOT FOUND); min tip 0.0001.
- Pros' glaive copies (MEASURED-us): 22.0 ms on relayer-fronted Jito leaders, 24.4 on own-TPU Jito, 38.1 on BAM.

**Solami Beam** [37]
- "Stake-weighted priority transaction routing. Free to use with a 0.0001 SOL minimum tip." "Over 5 million SOL of validator stake backs the Beam routing lane."
- Solami, LLC was founded 2026-03-04.
- A third-party repo reads a per-tx Beam record that includes a "Jito path" field and the hold time (example: "held 2 ms"). Whether Beam uses Jito: INFERRED, weak.
- Optional RPC plans run $0–999/month.
- Pros (MEASURED-us): 18.5 ms on relayer-fronted Jito leaders, but only 1 wallet. Treat as unproven.

**Falcon (Corvus Labs)** [42]
- Sends over stake-weighted QoS "backed by more than 1,000,000 SOL", and "in parallel through the Jito and Harmonic bundle engines".
- Nine metros. UUID keys. Raw UDP on :9000. Resending the same signed tx is safe.
- Price: NOT FOUND. Min tip 0.001.
- Pros (MEASURED-us): 28.9 ms on own-TPU Jito leaders.

**speedlanding** [38]
- "Dedicated SWQoS connections … directly to the current slot leader."
- Its own validator holds 32.8K SOL, in Tokyo, so most of its stake must come from partners (INFERRED).
- Plans: Free, Plus $49, Pro $199/month. Pro adds "lower latency routing" and a "dedicated priority lane". Min tip 0.001.
- Pros (MEASURED-us): 35.2 ms on Harmonic (n = 1,071), 37.4 on BAM, but only 39.7–45.4 on Jito.

**flashblock**
- "Private relay network" (CLAIMED, from an X snippet). The official docs return 403 to fetches [39].
- Free beta in 2025 (stale). Min tip 0.0001 (3P-SDK).
- Pros (MEASURED-us): 31.7 ms on own-TPU Jito, 39.2 on Firedancer.

**How do these beat the relayer's 50 ms hold?** NOT FOUND publicly.
- INFERRED: most likely through the Jito block engine, which "forwards your transaction directly to the validator" [1]. Block-engine packets also skip the relayer hold in the code (CLIENTS.md §3).
- jito-tx is that same path, already staged for the probes.

### 4.2 Paths we already use: what their docs tell us

**Helius Sender** [18][19][20][21]
- **Sender Max:** min tip 0.001; "Routed across every pathway and entered into a priority tip buffer for top of block — tip more to land first". An SDK release (dated Aug 20, year not shown) says the minimum rose from 0.0002 [20].
- **swqos_only:** min tip 0.000005, a single SWQoS path, no buffer. Tips between the two minimums go "best-effort, through fewer pathways".
- No credits are used: you pay only the tip, on any plan including Free.
- Rate limits: keyless 1 request/s per egress IP per region, and 429s count; any key gets 50/s per region.
- Plans: Developer $49 (10M credits), Business $499, Professional $999; extra credits $5 per million [21]. The pricing page is stamped 2025-01-20.
- Usage: 2.04M tipped txs/day, #2 after Jito [56].

**Nozomi (Temporal)** [24][25]
- Reaches leaders through "custom hardware and staked connections". It "orders the transactions it holds by tip" and bids with the Jito and Harmonic builders. Hold time and BAM path: NOT FOUND.
- Tips below 0.001 SOL are "silently dropped". New keys get 5 requests/s; raises depend on landing rate.
- Retries server-side until confirmed or expired.
- Durable nonces: "Do not race two paths with the same durable nonce", builders "may deprioritize durable-nonce transactions", and "a high failure rate lowers your priority".
- Billing conflict: "pay only on landing" vs "a reverted transaction that includes the tip still pays".
- CLAIMED: "0 slots median landing".
- Ours (MEASURED-us): our best copy on BAM and Harmonic; on Jito it landed only failures, late.

**Astralane** [32]
- Reaches leaders through "SWQoS partners including Jito and Paladin, direct routing to block builders Harmonic and BAM", and Rakurai.
- Routers run "in pure FIFO mode".
- Tiers by 7-day tip volume:
  - Free: 0.001 SOL min, 5 TPS;
  - VIP1 (4 SOL/week): 0.0001, 20 TPS;
  - VIP3 (8 SOL/week): 0.00001, 80 TPS.
- "Ghost" transactions (invite-only) carry the tip as a request field. Rebates are bigger for flow sent only to them and without a nonce.
- CLAIMED: 72% land in the target slot.
- Hosting: FRA `fr` is on Cherry, our host [89].
- Pros (MEASURED-us): 39–48 ms on every client. A middle path.

**BoltTx** [41]
- Regions: "LA main, NJ, FR, SG". No Amsterdam listed; only `bolttx.io/v1/send` is documented.
- Defaults: **`anti_mev` true, `max_retries` 3**. "Free forever" tiers with min tips of 0.0001–0.001.
- Nonce support is explicit: "do not submit the same nonce transaction to fewer than 2 paths".

**LandX**
- No public site or docs (NOT FOUND). Arct pinged its AMS endpoint at 0.117 ms [54].
- Pros' landx copies: 41 ms on own-TPU Jito, 84 ms on Firedancer (MEASURED-us).

**Constant-K staked sends** [52]
- 1, 5 or 20 SWQoS sends/s on the Operator, Blade Runner ($99) and Nexus ($299) plans.
- Vendor-measured: 46% slot+0 staked vs 39% unstaked (FRA, Oct 2026).
- Over the plan's cap it falls back to its own node and rebroadcasts every 420 ms (CLIENTS.md, DOC).

### 4.3 Protocol paths

**Jito block engine** [1][3][4][5][85][90]
- **`sendTransaction`:** "forwards your transaction directly to the validator", with MEV protection by default. With `bundleOnly=true` it becomes a revert-protected 1-tx bundle.
- **Bundles:** 50 ms auction ticks, up to 5 txs, min tip 1,000 lamports, 8 tip accounts. "Tips do not prioritize transactions for validators that are not Jito-Solana leaders". Jito keeps 6% of tips [90].
- **Tip floor** (10-25 14:30 UTC) [3]: p25 1,009 · p50 2,628 · p75 12,639 · p95 58,004 · p99 94,516 lamports.
- **Rate limit:** 1 request/s per IP per region by default. Higher limits need a ticket; the key goes in `x-jito-auth`.
- **Relayers:**
  - Jito "turned off its self-hosted relayers in early August" 2025 [4]. The repo is archived; its default delay is 50 ms [5].
  - Holds now remain only on operator-run relayers. MEASURED-us: 72 vs 43 ms (CLIENTS.md), and pros' no-tip copies there wait ~92 ms.
- **Alpenglow:** bundles are "held before and during the leader window" and wait for a resolved bank [85]. INFERRED: so a window's first slot is late for bundles.

**BAM** [6][7][8][9][84][91]
- Node hosts are `fra/ams/lon/dub/sqq.mainnet.bam.jito.wtf` [91]. Rounds went from 25 to 20 ms with 200 ms slots [7].
- Inside a round, plain txs and bundles share one rank: (priority fee + Jito tip) ÷ requested CU [6].
- "Authenticated bundles and sendTransaction traffic received by the Block Engine are now directly forwarded to BAM through DBI." This skips "an extra hop of roughly 50ms" and the block-engine auction [6].
- **DBI (Direct Bundle Ingest):**
  - QUIC (Ed25519 key) or JSON-RPC (UUID); revert-protected.
  - "Live on mainnet for an early cohort"; access by allowlist form. "Once whitelisted, you can start sending immediately" [6].
  - Endpoints, limits and price: NOT FOUND.
- **Maintenance:** BAM went into maintenance for Alpenglow and comes back "gradually" [7][8].
  - A Linux BBR issue delayed some windows' first slot by 90–330 ms; partly fixed [7].
  - Open bug: after a BAM disconnect, the TPU is not switched back to the relayer [84].

**Harmonic** [10][11][12][17][86]
- **Size:** 30.37% of stake, 88 validators (10-25 14:15 UTC). Of the top 20: FRA 7, LON 5, AMS 5 [12].
- **Scheduling:** FBA is the default: 50 ms double buffers sorted by priority fee + tips, and "arrivals within the same buffer are treated equally" [11]. About 24% of all stake runs FBA [17].
- **Bundles:**
  - The public endpoint has "stricter" limits; the authenticated one needs a whitelist form. 0% cut; "tips are just priority fees" [10].
  - Revert protection for single txs lasts "only while maintaining a high success rate". Repeated reverts get you blacklisted back to the Remote TPU [10].
  - Our buys fail ~58% of the time, so use this at low volume only.
- **Fix:** v4.3.2-harmonic.1 (Oct 19) fixed an Alpenglow clock reset that left the 4th slot of a window empty [86].

**Others**
- **Rakurai** (1.1%): a landing-service network (TIN); Rakurai tips go on top of the priority fee [14]. Already skipped in dip14.
- **Paladin:** blank site; last release Dec 2025 [15].
- **Raiku:** CLAIMED ~40 ms "JIT" inclusion, but live only on its own validator; price not disclosed [16].

### 4.4 Other services (scanned, lower priority)

- **bloXroute** [26]
  - Modes: `useStakedRPCs` (min tip 0.001), front-running protection, and revert protection (their slowest mode).
  - Price: Enterprise $1,250, Elite $5,000, Ultra $15,000 per month (page footer says ©2025).
  - Usage: 7.4K tipped txs/day [56].
- **NextBlock** [27]
  - Trial: 1 tx per 10 s.
  - Price: $249 (5 TPS), $749 (20 TPS), $1,749 (50 TPS). All tiers say "Dedicated SWQoS".
  - Usage: 3.5K txs/day [56].
- **BlockRazor** [33]: free, 3 TPS. Nonces are forbidden in its sandwich-protection mode. Pros' copies take 40–47 ms on Jito (MEASURED-us).
- **0slot** [40]
  - Each user gets "dedicated SWQoS". First week free; 5 sends/s; publishes a nonce cookbook.
  - Usage: 51.5K txs/day [56].
  - Pros' copies: 35.7 ms on Firedancer (MEASURED-us).
- **Triton Jet** [28][29]
  - Cascade retired Feb 28, 2026; staked sending is free for customers.
  - Price: $10 per million calls, $125 deposit.
  - No builder path found.
- **Jupiter Beam** [45]: staked QUIC + Jito. Min tip 0.001; "tipping more does not improve landing".
- **Sanctum Gateway** [46]: a router over the other services, 50,000 lamports per tx.
- **SVS Lightspeed** [51]: validator pool + optional Jito forward. FRA/AMS: NOT FOUND.
- **Everstake, OrbitFlare Apex, ERPC SWQoS, ZAN** [47]–[50]: see the endpoint table (§3).
- **QuickNode Lil' JIT** from $89/month (Jito only) and **Chainstack Warp** ($0.15 per tx, via bloXroute) [93].

### 4.5 Independent evidence on landing

- **inside-the-block** [53]: an independent developer, 10-22, after Alpenglow. 632 unstaked probes sent over QUIC straight to leader TPUs:

  | Client | Sent | Landed in the target leader's block | Refused | Never landed |
  |---|---|---|---|---|
  | JitoLabs | 112 | 80 | 8 | 24 |
  | AgaveBam | 104 | 44 | 14 | 46 |
  | Firedancer | 100 | 92 | 0 | 8 |
  | HarmonicAgave | 112 | 76 (+36 in another leader's block, ~24 slots later) | 0 | 0 |

  - Probes sent 30 ms apart were ordered by arrival on every client. Conflicting probes were ordered by fee.
  - INFERRED: plain direct TPU works on Firedancer and on own-TPU Jito leaders, and is poor on BAM.
- **Anza** [57] (Feb 2026, 400 ms slots, so the timing is stale; staked sender in AMS):
  - mean 0.29 slots to inclusion; ~2% lost;
  - AgaveBAM "spikes which could be explained by 50ms batches";
  - Harmonic puts txs "near the end of the slot".
- **Ping only** [54][55]: every FRA/AMS sender endpoint is 0.05–0.9 ms away (Arct AMS 06-16; OrbitServers 10-25). 0slot is the slowest (0.56 ms, behind Cloudflare).
- **Usage, not speed** [56] (24 h to 10-25 14:22 UTC): Jito 5.84M, Helius 2.04M, Astralane 76.6K, Nozomi 57.6K, 0slot 51.5K, bloXroute 7.4K, NextBlock 3.5K tipped txs.
- **Vendor-only claims:** Astralane 72% in the target slot [32]; Constant-K 46% vs 39% [52]; Nozomi "0 slots median" [25]; Helius "≤1.5 slots" [18].
- **Not found anywhere:** independent landing data for soyas, glaive, speedlanding, flashblock, Beam, LandX or bolt. Our chain labelling (HOW_PROS_LAND) is the best evidence.

---

## 5. Data side: seeing the dump earlier

### 5.1 Preconfirmations (the only big step ahead of shreds)

| Product | Covers | Lead | Price | Access |
|---|---|---|---|---|
| **Triton Preconfs** [29][30][31] | Harmonic (7 regions incl. fra, ams, lon) + BAM (15 incl. fra, ams, lon, dub, sqq) | MEASURED-by-Triton vs Geyser: Harmonic ~99% ahead, ~15 ms p50 (~75 p95); BAM ~91% ahead, ~8 ms p50 (~34 p95) | the greater of **$0.0015 per slot** or $50 per million messages. On Harmonic, every slot the stream is open counts, "whether or not a transaction matched". | "not self-serve … after a conversation"; gRPC `preconfs.rpcpool.com` with x-token |
| **Helius `preconfSubscribe`** [22][23] | BAM + "stake forwarding to Helius" (the docs' sample shows 45.8% of stake) | no figure in the docs; CLAIMED "5–50 ms before shredding" [23] | per subscription, per slot with ≥ 1 delivered message: the greater of 300 credits or 10 per message. Empty slots are free. = $0.0015/slot at $5 per million credits [21] | every paid plan since Oct 16 (Developer $49 and up); self-serve; `wss://beta.helius-rpc.com`; filters include `regionInclude`, accounts, signers, instruction memcmp |
| BAM itself [9] | – | CLAIMED p50 5–10 ms ahead of shred streams | set by the distributors | – |
| Shreder Preconfs [60] | add-on to Binary ($1,000+/month) | CLAIMED 5–50 ms | contact | free trial on plans |

**Cost for our near leaders** (INFERRED; our 10-23 gossip shares, ~12.2M slots/month at 213 ms):
- **Harmonic** (FRA 14.8% + AMS 4.7%): ~2.4M slots → **~$3.6K/month** (FRA only: ~$2.7K).
- **BAM** (FRA 6.7% + AMS 9.8%): ~2.0M slots → **~$3.0K/month**. Helius-forwarding slots come on top.
- **Shadow test:** about $4–5 per hour per feed.
- **Streaming only while the bot runs** cuts these costs in proportion.
- **The floor dominates** while a filter delivers ≤ 30 messages per slot. Filter on the pump.fun program plus the sell instruction.
  - Program IDs are always static keys, so Triton's "ALT-loaded accounts are not matched" rule doesn't bite (INFERRED).
- **Triton cap:** your matches may be at most 33% of what a region's feed publishes; stay over it and the stream ends [31].

**Message content:**
- Helius marks BAM status as "unknown" [22].
- Triton reports a BAM outcome "when the node reports it", and Harmonic success / failed / fees-only [31].
- A buy triggered by a dump that later fails just fails our +5% guard (~0.0005 SOL).

**Why Harmonic first** (INFERRED): of our 155 BAM + Harmonic fires, 94 were on Harmonic, where the lead is ~2× BAM's (~13 vs ~6 ms after our 2 ms shred lead). That puts ~¾ of the preconf value on Harmonic.

### 5.2 Raw shred feeds in FRA / AMS

| Feed | Price | Lead evidence | Access |
|---|---|---|---|
| **Constant-K ShredQuasar** [52] | $299 USDC/month; "save $99 with 2 regions"; NY / FRA / AMS | MEASURED-us 10-19: first on 75–83% of creates; +0.7–0.9 ms vs Kaldera, +2.3 ms vs erpc | 1-hour trial; crypto only |
| **DoubleZero Edge** [58] | per seat (one IPv4) per month: FRA / AMS $1,500; LON / NY / SGP / TYO $900; other cities $450 | MEASURED-us 10-19: +1.4 ms vs Kaldera, ~0.6 ms ahead of Constant-K. CLAIMED "6 ms faster on average". MEASURED-by-RPC Fast (a reseller, FRA, Jul 2026): 94.7% wins; 1.15 ms p50 / 6.97 ms p95 lag without DZ [59] | apply; GRE + PIM multicast, UDP 7733 |
| **Shreder Binary** [60] | from $1,000/month | MEASURED-by-Shreder (vendor, FRA2): beat DZ in 81% of races; DZ lagged 1.69 ms p50 / 15.1 ms p95; Jito ShredStream 4.6 / 38.5 ms | free trial |
| **Triton shred streaming** [29] | FRA / AMS $1,500/month, or **$0.59 per 15 min** pay-as-you-go ($125 deposit) | NOT FOUND | pay-as-you-go suits a 1-day A/B |
| Helius raw shreds [67] | $1,000 per IP/month ($800 on Professional) | MEASURED-by-Shreder: 2.31 ms p50 behind Shreder | self-serve |
| bloXroute OFR shreds [61] | $500/month per IP:port per region | NOT FOUND | page ©2025 |
| BlockRazor shreds [65] | $500/month or $50/day | NOT FOUND | – |
| ERPC Direct Shreds [63] | €398/month (AMS sold out Feb 2026) | CLAIMED >90% reliability | – |
| OrbitFlare raw UDP [62] | $1,000/month/region (FRA, AMS, LON) | CLAIMED <1 ms added | 1-hour trial via Discord ticket |
| Jito ShredStream [2] | **shut down Sep 5, 2026** | – | – |

### 5.3 Decoded / gRPC streams (behind raw shreds; for completeness)

- **Kaldera** (what we use): Blade Runner $99, Nexus $299. SubscribeDeshred on both; Turbo pre-execution on Nexus [52].
- **Triton Deshred** (beta): CLAIMED ~6.3 ms p50 "from the moment shreds arrive" [66].
- **Helius `preprocessedSubscribe`:** pre-execution txs, 0.1 credit per message. CLAIMED ~8 ms ahead of "processed" [67].
- **Helius LaserStream:** Business plan and up; Shreder measured it 2.9 ms behind its Fastlane [60][67].
- **Shyft RabbitStream:** $199–649/month. Vendor bench: ~5.5–6 ms ahead of Jito ShredStream [64].

### 5.4 Alpenglow / Rotor

- Votor is live since epoch 1064 (Oct 21).
- Rotor, which replaces Turbine, is "planned for a later release, not yet scheduled" [68]. So shred feeds keep their value for now.
- When Rotor ships (INFERRED): Turbine-position feeds lose their edge. Leader-direct feeds (DZ leader shreds) and preconfs keep theirs.

---

## 6. Location and hosting

**Where our servers are** [78][71]
- 84.32.100.36 = Cherry Servers DE (AS213896), Frankfurt; Cherry says Equinix FR13.
- 84.32.104.202 = Cherry Servers NL (AS59642), Amsterdam; Equinix AM4.
- VPS or bare metal is not visible publicly.

**Where the relays are** (DNS + ipinfo lookups [89])
- On TeraSwitch (AS20326): the Jito block engines FRA / AMS, BAM FRA, Harmonic FRA / AMS, Helius Sender FRA / AMS, Nozomi fra2 / ams1 and bloXroute.
- Astralane `fr` / `ams2` are on Cherry.
- "Jito's regional block engines all run on TeraSwitch bare metal" [76].
- TeraSwitch sites: FRA = Equinix FR2 / FR5; AMS = Equinix AM3 / AM4, Digital Realty AMS17, Iron Mountain AMS-1, Nikhef [74].

**Where the leaders are** (our gossip, share of slots)
- TeraSwitch FRA 23.3%, AMS 16.3%, LON 8.1%; Cherry Šiauliai 5.1%; Allnodes Fechenheim 2.8%.
- Public: TeraSwitch held 27.1% of stake (Jul 2026); a 33-minute TeraSwitch outage on Aug 12 took 28.8% of stake offline [82].
- Frankfurt has 28.3% of stake and 35.3% of slots (Sep 2026) [83].

**RTT**
- Cherry's private link to TeraSwitch: FRA "under 0.25ms" to Jito, AMS "just 0.1ms" (CLAIMED, 2025) [70].
- MEASURED-us: relays 0.10–0.18 ms; leaders' fronts 0.13 ms.
- FRA ↔ AMS on the public internet: 10.1–10.6 ms (MEASURED-by-WonderNetwork, Oct 11–25) [77]; our boxes see 5.8–7.5 ms.

**Prices** (CLAIMED list prices)
- Cherry FRA: EPYC 9254P 24 cores €369, 9354P 32 cores €419, 9554P 64 cores €669/month.
- Cherry AMS: 7313P 16 cores €135, 7543 32 cores €152/month [71].
- TeraSwitch: 24 cores 2×25G ~$449–460, 32 cores $490, 64 cores $665; hourly billing (aggregator listing, Oct 2026) [72].
- Latitude.sh: 16 cores 2×10G $456 [73].
- Equinix Metal ended Jun 30, 2026.

**Verdict:** moving into TeraSwitch saves ≤ 0.1–0.3 ms (INFERRED). Not worth it.

**What may be worth it:**
- **Frankfurt bare metal**, only if FRA is a VPS under load.
  - FRA's executed-feed wait is 2.4 ms p50 / 8.3 p90, vs AMS 0.9 / 3.0 (MEASURED-us). It grew since run 13.
  - Check CPU steal and `--dip-feed-lag` first (free). The staged shred-fire fix also removes this wait for covered picks.
- **A London edge.**
  - London leaders are ~8–10% of slots, 5.7 ms from AMS and 11.3 ms from FRA (MEASURED-us).
  - All key lanes have London endpoints: Helius `lon-sender`, Jito london, Nozomi lon, Harmonic `lon.be`, glaive, soyas, speedlanding.
  - Constant-K has no London feed, so the feed would cost $900 (DZ or Triton).
  - About $1.5K/month all-in (INFERRED).
  - Then New York: on US leaders the best pros' fastest 10% land at 21–25 ms, ours at 87 ms (HOW_PROS_LAND item 5).

---

## 7. Stake / SWQoS / own node

- **How SWQoS works now:**
  - Agave 4.0 "removes TPS throttling for staked senders entirely under normal load". Stake-proportional allocation comes back only at ~95% of capacity.
  - Counting as staked needs ~1/50,000 of stake, about 8,500 SOL.
  - In a 3-week mainnet test the fallback "was never triggered" [79].
  - Triton: "At p50, staked and unstaked sending perform nearly the same" [28].
- **Renting SWQoS buys ~0 ms at p50 for us** (INFERRED). Our relays already send over staked connections.
- **Who sells it:**
  - Triton staked sending is free for customers [28].
  - ERPC: 1 TPS per 4.2 elSOL held, or +1,000 SOL of allocation for €100/month [48].
  - Constant-K: 1 / 5 / 20 staked sends per second, by plan [52].
  - NextBlock: "dedicated SWQoS" from $249 [27].
- **Our own staked validator:**
  - The VAT is 0.8 SOL per epoch, charged since Oct 21, and only the top 2,000 validators by stake are admitted [69]. That is ~24 SOL/month at ~1-day epochs (INFERRED).
  - Hardware: 12+ cores and 512 GB RAM [88].
  - It needs ≥ 8.5K SOL of stake.
  - Reaching turbine's first layer needs roughly top-200 stake (INFERRED).
  - The Foundation delegation program needs a hosting ASN under 25% of stake, so TeraSwitch (~27%) is out [81].
- **Verdict:** skip.

---

## 8. Conflicts and open questions

- **BAM after Alpenglow:** public sources say only "back gradually" [7][8]. Our gossip (10-23 21:17 UTC) showed AgaveBam on 36.5% of slots with BAM-node TPUs. Re-snapshot before paying for BAM preconfs or DBI.
- **Stake shares:** Triton's "JitoBAM 60%, Harmonic 16%" (May) [28] counts all Jito-family clients. Ours on 10-23: Jito-family 61.1%, Harmonic 29.7%, which fits harmonic.gg's 30.4% today [12].
- **Preconf status field:** Helius says BAM status is unknown [22]; Triton reports it "when the node reports it" [31].
- **Nozomi billing:** "pay only on landing" vs "reverted tx with tip still pays" [24].
- **Harmonic bundles:** one page says send to the closest region, the FAQ says send to all regions [10].
- **Solami Beam:** regional hosts and key needs are unclear; 1 pro wallet uses it [37].
- **Our "bolt" path:** our config points at `*.bolt.raiden.wtf`. The public BoltTx docs show only `bolttx.io` and no Amsterdam region. Check which service it is (could not verify: the web search budget ran out).
- **Nobody publishes** how soyas, glaive or Beam skip the 50 ms relayer hold, or the length of the holds in Nozomi's, Helius Max's and glaive's buffers. Probes settle it.

---

## 9. Sources

**Our data (MEASURED-us)**
- [U1] ops/dip/speed/truth/SPEED_TRUTH.md
- [U2] ops/dip/speed/clients/CLIENTS.md
- [U3] ops/overnight/soyas/jitowin.txt
- [U4] ops/dip/WHY_LIVE_LOSES.md
- [U5] ops/dip/speed/leaders/leader_rtt_new.json (gossip 10-23 21:17 UTC), ops/region/leader_rtt_ams.json (10-24), ops/dip/speed/leaders/leader_geo.json (10-20)
- [U6] 10-19 feed race (/root/gap on the old server; memory note gap-feed-race)
- [U7] ops/dip/speed/fixes/FIXES.md
- this folder: WHERE_TIME_GOES.md, HOW_PROS_LAND.md, PROBES_V2.md, CLIENT_ACTIONS.md

**Web** (read 10-25)

Jito, BAM, Harmonic and other block builders:
1. https://docs.jito.wtf/lowlatencytxnsend/
2. https://docs.jito.wtf/lowlatencytxnfeed/
3. https://bundles.jito.wtf/api/v1/bundles/tip_floor
4. https://bam.dev/blog/supporting-ibrl-fast-and-predictable-execution-on-solana/
5. https://github.com/jito-foundation/jito-relayer/releases
6. https://bam.dev/blog/introducing-bams-direct-bundle-ingest/
7. https://bam.dev/blog/bam-changelog-sept-23-oct-9/
8. https://bam.dev/blog/update-on-bam-readiness-for-alpenglow-on-mainnet/
9. https://bam.dev/docs/bam/preconfirmations/
10. https://docs.harmonic.gg/searchers/harmonic-bundles.md
11. https://docs.harmonic.gg/concepts/scheduling-strategies.md
12. https://harmonic.gg/network
13. https://harmonic.gg/preconfs
14. https://docs.rakurai.io/
15. https://solanacompass.com/projects/paladin
16. https://www.raiku.com/news/the-engineering-contract
17. https://schedulerwar.vercel.app/

Helius:

18. https://www.helius.dev/docs/sending-transactions/sender
19. https://www.helius.dev/docs/sending-transactions/sender-max
20. https://github.com/helius-labs/helius-sdk/releases
21. https://www.helius.dev/pricing
22. https://www.helius.dev/docs/pre-confirmations/preconf-subscribe · https://www.helius.dev/docs/api-reference/pre-confirmations/getpreconfcoverage.md
23. https://solanacompass.com/news/helius-opens-solana-preconfirmations-to-all-paid-plans-and-adds-four-new-filters

Mainstream senders:

24. https://use.temporal.xyz/nozomi/tipping-and-faq · /nozomi/faq · /nozomi/troubleshooting.md · /nozomi/endpoints · /nozomi/batch-send.md
25. https://www.temporal.xyz/services/nozomi
26. https://docs.bloxroute.com/solana/trader-api/api-endpoints/core-endpoints/submit · https://bloxroute.com/pricing/
27. https://docs.nextblock.io/pricing-and-rate-limits.md · https://docs.nextblock.io/getting-started/quickstart
28. https://blog.triton.one/swqos-for-everyone-why-we-retired-cascade-marketplace/ · https://triton.one/products/transactions
29. https://triton.one/pricing
30. https://triton.one/products/triton-preconfs
31. https://docs.triton.one/chains/solana/preconfirmations-grpc.md
32. https://astralane.gitbook.io/docs/low-latency/send-txn-fee-tiers.md · https://astralane.gitbook.io/docs/low-latency/submit-transactions · https://astralane.gitbook.io/docs/low-latency/endpoints-and-configs.md · https://astralane.io/
33. https://docs.blockrazor.io/transaction-submission/transaction-sending/solana/send-transaction.md

Niche lanes:

34. https://raw.githubusercontent.com/0xfnzero/sol-trade-sdk/main/src/constants/swqos.rs (third-party SDK)
35. https://medium.com/feed/@soyas
36. https://glaive.trade/docs
37. https://solami.dev/llms.txt · https://api.solami.dev/pricing · https://github.com/MHVVD/Tripwire · https://github.com/sadiqsaidu/tipwise
38. https://speedlanding.trade/ · https://speedlanding.trade/docs.html · https://validators.solutions/en/validators/3DaifGfDESUzer5ggUeo6UDjqEKMkCpdNSrrvyuggHVe/
39. https://doc.flashblock.trade/
40. https://0slot.trade/docs.html
41. https://bolttx.io/ · https://bolttx.io/en/docs/api/send · https://bolttx.io/en/docs/advanced/durable-nonce
42. https://docs.corvus-labs.io/falcon.mdx · /falcon/regions.mdx · /falcon/tips.mdx
43. https://docs.hellomoon.io/reference/lunar-lander
44. https://node1.gitbook.io/node1-docs/solana/fast-landing/endpoints
45. https://developers.jup.ag/docs/transaction/submit
46. https://sanctum.so/blog/sanctum-gateway-v1-update-solana-transaction-infrastructure
47. https://apex.orbitflare.com/
48. https://erpc.global/en/doc/rpc/durable-nonce-send-transaction/ · https://erpc.global/en/faq/qos/general/
49. https://docs.blockspace.everstake.com/swqos/api
50. https://docs.zan.top/docs/quic
51. https://docs.solanavibestation.com/services/solana-node-services/lightspeed-transactions
52. https://www.constant-k.com/pricing/ · https://www.constant-k.com/

Landing evidence:

53. https://raw.githubusercontent.com/EvgeniuGlinsky/inside-the-block/main/REPORT.md
54. https://www.arct.cloud/blog/solana-trading-vps
55. https://orbitservers.io/benchmarks/solana-sender-latency
56. https://openchainbench.com/benchmarks/solana-tx-landing
57. https://www.anza.xyz/blog/transaction-landing-on-tpu

Data feeds:

58. https://doublezero.xyz/dz-edge · https://docs.doublezero.xyz/solana/edge/subscribe/ · https://doublezero.xyz/jito-shredstream
59. https://rpcfast.com/blog/doublezero-solana-private-fiber-latency
60. https://shreder.xyz/benchmarks/ · https://shreder.xyz/pricing/
61. https://docs.bloxroute.com/solana/optimized-feed-relay/shred-stream · https://bloxroute.com/pricing/
62. https://docs.orbitflare.com/shredstream · https://orbitflare.com/pricing
63. https://erpc.global/en/price/
64. https://www.shyft.to/solana-shreds-rabbitstream · https://docs.shyft.to/solana-shredstreaming/rabbitstream-vs-jito-shredstream-benchmarks
65. https://docs.blockrazor.io/streams/block-stream/solana/shred-stream
66. https://blog.triton.one/deshred-transactions-the-fastest-path-to-solana-data/
67. https://www.helius.dev/docs/laserstream · https://www.helius.dev/docs/shred-delivery/raw-shreds · https://www.helius.dev/docs/preprocessed-transactions/overview.md

Network upgrades:

68. https://solana.com/upgrades/alpenglow
69. https://solana.com/upgrades/bls-pubkey-vat

Hosting and location:

70. https://www.cherryservers.com/blog/pni-with-teraswitch
71. https://www.cherryservers.com/bare-metal-dedicated-servers/germany · https://www.cherryservers.com/bare-metal-dedicated-servers/netherlands
72. https://www.whtop.com/plans/teraswitch.com/158528 (aggregator)
73. https://www.latitude.sh/pricing
74. https://www.peeringdb.com/asn/20326
75. https://www.validators.app/data-centers?network=mainnet
76. https://latency.glassnode.com/solana/about
77. https://wondernetwork.com/pings/Frankfurt/Amsterdam
78. https://rdap.db.ripe.net/ip/84.32.100.36 · https://ipinfo.io/84.32.100.36 · https://rdap.db.ripe.net/ip/84.32.104.202 · https://ipinfo.io/84.32.104.202

Stake and SWQoS:

79. https://blog.triton.one/evolution-of-solanas-stake-weighted-quality-of-service-from-the-agave-side/
80. https://raw.githubusercontent.com/anza-xyz/agave/master/streamer/src/nonblocking/stream_throttle.rs
81. https://solana.org/delegation-criteria

Other:

82. https://forklog.com/en/solana-nears-transaction-finalization-halt-due-to-teraswitch-outage/
83. https://cryptobriefing.com/europe-solana-leader-slots-germany-dominance/
84. https://github.com/jito-foundation/jito-solana/issues/1142
85. https://github.com/jito-foundation/jito-solana/pull/1706
86. https://github.com/harmonic/salsa/releases · https://github.com/harmonic/salsa/pull/79
87. https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd
88. https://docs.anza.xyz/operations/requirements
89. DNS lookups via https://dns.google/resolve?name=fra-sender.helius-rpc.com&type=A (and the other relay hosts), with ipinfo pages such as https://ipinfo.io/64.130.50.91 · https://ipinfo.io/198.13.141.173 · https://ipinfo.io/63.254.167.80 · https://ipinfo.io/185.191.117.97
90. https://jito-foundation.gitbook.io/mev/jito-solana/faqs.md
91. https://bam.dev/validators/
92. https://app.blockworks.com/report/solana-s-block-building-wars?from=bwr (third-party report)
93. https://www.quicknode.com/add-ons · https://docs.chainstack.com/docs/solana-trader-nodes · https://chainstack.com/pricing/

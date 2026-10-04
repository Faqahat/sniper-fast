# Solana transaction senders: public-docs comparison (2026-10-03)

Sources: vendors' public docs, GitHub READMEs and announcements only. Nothing was signed up for or sent. Full per-service detail (verbatim tip lists, every EU host, features, pricing, doc URLs) is in `sender-tip-accounts.json`.

- **How the tip lists were checked.** Every address was pulled by script from the raw page (curl), not retyped or summarised. Each one decodes to a 32-byte key.
- **"In our map"** compares each list with `known_tip_accounts` / `tip_owner_names` in `arb-lab/src/send/mod.rs`.

## Comparison

| Service | Tip accts | In our map | Min tip (SOL) | EU endpoint (Frankfurt first) | SWQoS | Bundles | MEV protect / revert protect | Access / price | Doc date |
|---|---|---|---|---|---|---|---|---|---|
| Jito block engine | 8 | yes | 0.000001 (bundles) | `frankfurt.mainnet.block-engine.jito.wtf` | no (block-engine auction) | yes (<=5 tx) | jitodontfront marker / yes (bundleOnly=true / bundles) | free, 1 req/s/IP/region | 2026-09-09 |
| Helius Sender | 10 | yes | 0.001 Max / 0.000005 SWQoS-only | `fra-sender.helius-rpc.com` | yes | yes (Max, <=4 tx) | opt-in mev-protect / no | free on all plans, 50 TPS | fetched 2026-10-03 |
| Temporal Nozomi | 17 | yes | 0.001 | `fra2.nozomi.temporal.xyz` | yes | yes (1-4 atomic) | separate MEV Protect key / bundles only | free self-serve key | fetched 2026-10-03 |
| Astralane Iris | 17 | yes | 0.001 free / 0.0001 VIP1-2 / 0.00001 VIP3 | `fr.gateway.astralane.io` | yes | yes (VIP tiers only) | mev-protect option / not documented | free tier 5 TPS (key required) | fetched 2026-10-03 |
| bloXroute Trader API | 17 | yes | 0.001 | `germany.solana.dex.blxrbdn.com` | yes (useStakedRPCs) | yes | frontRunningProtection flag / not documented | free tier (60 credits/min) | fetched 2026-10-03 |
| NextBlock | 8 | yes | not stated (~0.001) | `frankfurt.nextblock.io` | yes (dedicated) | yes (bundle sample) | frontRunningProtection flag / revertOnFail flag | trial 1 tx/10 s; $249+/mo | fetched 2026-10-03 |
| 0slot | 21 | yes | 0.001 (0.0001 Advanced) | `de.0slot.trade` | yes (dedicated) | not documented | anti-mev option / not documented | trial week 5 TPS; plans via sales | fetched 2026-10-03 |
| BlockRazor | 14 | yes | 0.0001 | `frankfurt.solana.blockrazor.xyz` | yes (own edge network) | yes (<=4, on request) | sandwichMitigation mode / bundles all-or-nothing | free key, 3 TPS | fetched 2026-10-03 |
| Falcon (Corvus) | 10 | yes | 0.001 | `fra.falcon.wtf` | yes (>1M SOL stake) | no user bundles | no / no | no (key via onboarding) | fetched 2026-10-03 |
| FlashBlock | 10 | yes | 0.0001 | `fra.flashblock.trade` | not stated | yes | not documented / not documented | free trial key | capture 10-03 06:32Z (site now 403) |
| Node1 | 6 | yes | 0.001 | `fra.node1.me` | not stated | not documented | not documented / not documented | free self-serve key | fetched 2026-10-03 |
| Stellium | 9 | **NEW** | 0.001 | `on request (Frankfurt region)` | yes | no | no / no | contact | fetched 2026-10-03 |
| Lunar Lander (Hello Moon) | 10 | yes | 0.001 | `fra.lunar-lander.hellomoon.io` | not stated | yes (Send Bundle API) | not documented / bundles | key via Discord | fetched 2026-10-03 |
| Raiden Bolt | 9 | yes | 0.001 | `fra.bolt.raiden.wtf` | not stated | no | no / no | free 5 tx/s | fetched 2026-10-03 |
| Everstake SWQoS | 10 | yes | 0.001 | `fra-swqos.everstake.one` | yes | no | no / no | keyless, 10 TPS | repo 2026-09-16 |
| Jupiter tx.jup.ag | 16 | **NEW** | 0.001 | `tx.jup.ag (global)` | yes | no | no / no | portal key | 2026-07-29 |
| SVS Lightspeed | 1 | **NEW** | 0.001 | `basic.swqos.ams1.solanavibestation.com` | yes | Jito forward upstream | no / no | no (paid tiers) | 2026-10-02 |
| P2P Syncro Sender | 9 | **NEW** | 0.0002 public / 0.00015 private | `fra.sender.syncro.p2p.org:8080` | yes | no | no / no | public: no key, 1 TPS | fetched 10-03 (blog 2026-03-31) |
| RPC Fast Beam | 18 | partial (2/18) | 0.0001 Astralane route / 0.001 others | `beam.rpcfast.com (global)` | via providers | yes (Astralane/bloXroute routes) | mev_protect mode / no | RPC Fast plan | fetched 2026-10-03 |
| QuickNode Lil' JIT | 8 (=Jito) | yes | Jito floor | `QuickNode endpoint, region=frankfurt` | no | yes (<=5 tx) | via Jito markers / bundleOnly=true | no ($89+/mo) | fetched 2026-10-03 |
| QuickNode Fastlane (gone) | 8 | **NEW** (stale) | 0.001 (historical) | `none (NYC only)` | yes | Jito routing | yes (frontrunning protection) / no | was $0 at 10 req/s | Wayback 2026-01-21 |
| Triton (Cascade/Jet) | 0 | – | none | `per-customer GeoDNS` | yes (all customers) | no (simulateBundle only) | Shield allow/deny policies / no | PAYG ($125 deposit) | fetched 10-03 (blog 2026-03-05) |
| Chainstack Warp | 0 | – | none | `fra2 node (private host)` | yes (via bloXroute) | no | disabled / no | no (Growth plan+) | fetched 2026-10-03 |
| ERPC SWQoS | 0 | – | none | `Frankfurt (private domain)` | yes | no | no / no | no (elSOL-based) | fetched 2026-10-03 |
| Shyft | 0 | – | none | `rpc.shyft.to (GeoDNS)` | yes (paid plans) | no | no / no | free plan without SWQoS | fetched 2026-10-03 |
| Haan Digital | 0 | – | – | `Frankfurt (private)` | claimed | optional Jito | not documented / not documented | contact | 2026-09-25 |
| Syndica | 0 | – | – | `none` | n/a | n/a | n/a / n/a | retired | fetched 2026-10-03 |
| Harmonic | 0 | – | none | `fra.be.harmonic.gg` | no (block engine) | yes (gRPC, whitelist) | dontfront markers + bundle privacy / yes (bundles) | free (whitelist) | ≤2026-09-25 |
| Paladin P3 | 0 | – | – | `none (leader IP:4819)` | PAL-stake QoS (unverified) | no | no / no | n/a | fetched 2026-10-03 |
| Sanctum Gateway | 0 | – | 0.00005 fee/tx | `not published` | via routed providers | via Jito route | no / no | pay per tx | blog 2025-10-14 (docs 404) |
| Rakurai TIN | 8 | **NEW** | optional (rec. 0.001) | `none public` | n/a (validator client) | via your block engine | no / no | n/a | ~2026-09-26 |
| Jito BAM | 0 | – | as Jito | `frankfurt.mainnet.block-engine.jito.wtf (classic)` | n/a | via Jito block engine | as Jito / as Jito | n/a | 2026-09-09 (blog) |
| GetBlock LandFirst | 0 | – | – | `not published` | yes | via Jito | no / no | sales only | fetched 2026-10-03 |
| Figment Accelerator | 0 | – | – | `not published` | claimed | no | no / no | sales only | fetched 2026-10-03 |

More EU hosts:
- Jito: `amsterdam.` / `london.` / `dublin.mainnet.block-engine.jito.wtf`
- Helius: `ams-sender` / `lon-sender.helius-rpc.com`
- Nozomi: `ams1` / `lon1.nozomi.temporal.xyz`. These are the direct hosts; the Cloudflare ones are `fra` / `ams` / `lon`.
- Astralane: `fr2`, `ams` (recommended), `ams2`, `lon.gateway.astralane.io`
- bloXroute: `amsterdam` / `uk.solana.dex.blxrbdn.com`
- NextBlock: `amsterdam` / `london` / `dublin.nextblock.io`
- 0slot: `ams.0slot.trade`
- BlockRazor: `frankfurt-cherryservers`, `frankfurt-allnodes`, `amsterdam(-cherryservers)`, `london.solana.blockrazor.xyz`
- Falcon: `ams` / `lon.falcon.wtf`
- FlashBlock: `ams` / `london` / `lithuanian.flashblock.trade`
- Node1: `fra2` / `ams` / `lon` / `dub.node1.me`
- Lunar Lander: `ams` / `lon.lunar-lander.hellomoon.io`
- Bolt: `ams` / `lnd.bolt.raiden.wtf`
- Everstake: `ams-swqos` / `lon-swqos.everstake.one`
- Syncro: `ams3.sender.syncro.p2p.org:8080`
- Harmonic: `ams` / `lon.be.harmonic.gg`

## What is new compared with our map

**All tip lists already in `mod.rs` are still exact matches**, with no additions or removals today: Jito 8, Helius 10, Nozomi 17, Astralane 17, bloXroute 17, NextBlock 8, 0slot 21, BlockRazor 14, Falcon 10, FlashBlock 10, Node1 6, Lunar 10, Bolt 9, Everstake 10. QuickNode Lil' JIT uses Jito's 8.

**67 published tip accounts are not in the map**, so a rival paying them is currently recorded as unattributed:
- **RPC Fast Beam: 16.** The map has only Beam's 2 Astralane-route accounts. Missing are 3 `rfB…` (bloXroute route), 8 for the Nozomi route, and 5 `rfC…` (Falcon route). Beam's accounts are its own and differ from the providers' public lists.
- **Jupiter tx.jup.ag: 16.**
- **Stellium: 9** (`ste11…`).
- **P2P.org Syncro Sender: 9.** A new service, launched 2026-03-31.
- **Rakurai TIN: 8.** An optional "virtual priority boost" tip; mainnet list only.
- **Solana Vibe Station Lightspeed: 1** (`svsMo…`). SVS also hands out per-user, time-limited "stealth" addresses, which can never be attributed from docs.
- **QuickNode Fastlane: 8.** The product is no longer listed. These come from a Wayback copy of the official page dated 2026-01-21 and are marked `unverified`. Keep them for attributing older transactions only.
- **bloXroute legacy wallet `HWEoBxYs7ssKuudEjzjmpfJVX7Dvi7wescFsVx2L5yoY`.** It appears in bloXroute SDK samples marked "as of 2/12/2024" and is not on today's tip page. It is stored as `legacy_tip_accounts_unverified`.

Of this morning's two unattributed "extra" addresses:
- `BPZrt…` is Syncro Sender's first tip account.
- `HWEoBx…` is the bloXroute legacy wallet above.

## Notes and caveats

- **Cheapest tips per landed transaction:**

  | Service | Minimum tip (lamports) | Condition |
  |---|---|---|
  | Jito bundles | 1,000 | |
  | Helius Sender SWQoS-only | 5,000 | plus a priority fee |
  | Astralane | 10,000 | VIP3 tier only |
  | BlockRazor, FlashBlock, Beam-Astralane route | 100,000 | |
  | Astralane | 100,000 | VIP1/2 tier |
  | Syncro | 150,000–200,000 | |
  | Most others | 1,000,000 (0.001 SOL) | |

  Harmonic, Triton, Chainstack Warp, ERPC and Shyft take no SOL tip.
- **The docs contradict each other in places:**
  - **Syncro minimum tip:** the docs say 200k public / 150k private lamports; the launch guide said 100k / 1M. Trust the `-32602` error message.
  - **Astralane VIP1 threshold:** the prose says 3 SOL and the table says 4.
  - **Jito minimum tip:** Jito's own doc still says 1,000 lamports for bundles; QuickNode says there is no minimum.
  - **NextBlock:** no explicit minimum; use its tip-floor API.
  - **Harmonic:** the docs say both "send to the nearest region" and "send to all regions".
- **Products retired or changed:**
  - **Syndica:** RPC retired; no sender.
  - **QuickNode Fastlane:** no longer listed.
  - **Triton Cascade Marketplace:** retired 2026-02-28. SWQoS is now included for every Triton customer at no extra cost. Triton claims staked and unstaked sending are about equal at p50 (a vendor claim).
  - **Sanctum Gateway:** the docs return 404, so its tip accounts couldn't be verified. Fees per the blog: 0.00005 SOL per tx for Gateway, 0.0001 SOL per tx for Sanctum Sender.
- **Hosts that aren't public:**
  - Stellium: given on request. A third-party repo uses `fra1.flashrpc.com` (unverified).
  - Triton, Chainstack and ERPC: per-customer hosts.
  - Haan: no public docs. Paladin: send to the leader's IP on P3 port 4819 or 4820.
- **No Frankfurt site:** Jupiter is one global host (`tx.jup.ag`); SVS is in Amsterdam only (AMS1); QuickNode Fastlane was NYC-only.
- **Not found:** Soyas, LandX and Blocksmith have no public product.
  - `soyas…` tip addresses do appear in rivals' transactions (research log S-011).
  - Venum is only a wrapper around Jito bundles.
  - GetBlock LandFirst and Figment's Transaction Accelerator are sales-only, with no tips or hosts published.
- **Jito BAM** has no separate searcher API or tip accounts. Keep using the classic block engine and the 8 Jito tip accounts. The `*.mainnet.bam.jito.wtf` hosts are for validators. BAM preconfirmations (live 2026-09-09, via Helius and Triton) are a data feed reported 5–10 ms ahead of shreds; they don't help with sending.
- **Tips must be plain, top-level System transfers to an account in the transaction's static keys** for most senders (Falcon, SVS and Jito say so explicitly). Don't put tip accounts in lookup tables, and don't split one tip across several transfers.

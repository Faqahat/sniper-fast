# Landing faster: every action from the validator-client study (CLIENTS.md), with status

10-25 ~19:45 PKT. The owner asked for anything in the client study that can make us land faster. Source: ops/dip/speed/clients/CLIENTS.md (code + docs + our data).

Status checked against the live configs (FRA dip_probe.toml, AMS dip_edge_ams.toml) and run 16's routes:
```
jito     -> helius (Sender Max, 0.001 tip) + nozomi + jito-bundle (0.001) + staked-rpc
bam      -> nozomi + helius-swqos + bolt + staked-rpc
harmonic -> nozomi + helius-swqos + landx-fra3 + staked-rpc
fd       -> nozomi + landx-fra3 + staked-rpc
```
Configured but unused paths: astralane (free tier, 5 tx/s), harmonic-bundle, tpu-direct, haan.

## A. Route changes (config only, no new code; send-path changes = owner's OK)

| # | Change | Why (study) | Gain | Status |
|---|---|---|---|---|
| A1 | Jito: replace `helius` (Sender Max 0.001) with keyed `helius-swqos` | Sender Max sits in a "top of block" tip buffer: half of its Jito landings at 119–176 ms | removes the slow landings; −0.001 SOL per helius fill | not done (probe first) |
| A2 | Jito: drop `jito-bundle` | landed 1 of 54; 50 ms auction ticks; all-or-nothing | saves its tip; no loss | not done |
| A3 | Harmonic: drop `helius-swqos` + `staked-rpc` | they reach the slow relay, land mostly failures (0/3, 2/29) | ~29 failure fees saved / 309 tries; ≤ 2 fills lost | not done |
| A4 | BAM: drop `staked-rpc` (or pay its bid as a Jito tip) | it lands our failures (18 of 20); nozomi lands the fills | ~18 failure fees saved / 309 | not done |
| A5 | Skip Rakurai leaders always | closed scheduler holds our txs ~1 slot (7 of 8 late) | 1.1% of slots, no late fills | flag in dip14/15; only used in FRA run 16 |

## B. Speed tests (probes: fees only, ~0.04 SOL per client)

| # | Test | Gain if it works | Status |
|---|---|---|---|
| B1 | Jito block-engine `sendTransaction` copy on the 39 relayer-fronted Jito leaders | up to −50 ms on 6% of all slots (the relayer holds every plain tx 50 ms) | not done |
| B2 | Astralane (already configured) on Harmonic + BAM ("direct routing to builders") | may join an earlier 50 ms Harmonic buffer | not done |
| B3 | New providers on Jito / Harmonic: speedlanding, glaive, soyas, solami_beam (fastest market-wide there) | Jito-relayer leaders: solami_beam 16, soyas 22, glaive 26 ms vs us 72 | need accounts / tips |
| B4 | Nozomi with vs without the durable nonce | Nozomi docs: builders "may deprioritize durable-nonce txs", "high failure rate lowers priority"; nozomi is our main path on BAM / Harmonic | not done |
| B5 | Firedancer: direct UDP copy to the leader TPU :9001 (tpu-direct exists) | a few ms on 7% of slots | not done |

## C. Engine changes (free; build + owner OK)

| # | Change | Gain | Status |
|---|---|---|---|
| C1 | Set `SetLoadedAccountsDataSizeLimit` | ~14% more priority for the same fee on Agave / Jito / Firedancer (default adds 16,384 cost) | not done |
| C2 | Leaner buy tx (no ATA program; plain InitializeAccount3 like haqq) | ~10–20k CU less → higher per-CU bid where BAM / Harmonic / FD rank by it | not done (touches the sell path) |
| C3 | Log Constant-K `X-CK-Tx-Route` | if we exceed our plan's staked sends/s, CK silently falls back and rebroadcasts every 420 ms; would explain "staked-rpc lands often but late" | not done; also check our CK plan's cap |
| C4 | Window-slot-1 timer (log only) | stops blaming paths for structural spills (block 1 ≤ 144 ms) | not done |
| C5 | Lock-only probes (always-succeed tx that write-locks the curve) | ranks revert-protected paths at ~1/25 of today's probe cost | not done |

## D. Paid / sign-up (see the market scan)

| # | Item | Gain | Cost |
|---|---|---|---|
| D1 | BAM preconfirmations (Helius `preconfSubscribe`) | dumps seen 5–10 ms earlier on ~38% of slots → +8–12 fills / 309 | Helius credits (10 per message, paid plan) |
| D2 | Harmonic preconfs (Triton) | up to one 50 ms buffer earlier on ~30% of slots | unknown |
| D3 | BAM Direct Bundle Ingest allowlist | revert-protected single tx straight to the BAM node: failed buys free, skips the ~50 ms block-engine hop | free form, allowlist |
| D4 | Harmonic block-engine single-tx bundle (path configured) | failed buys free | access cut if reverts stay high |

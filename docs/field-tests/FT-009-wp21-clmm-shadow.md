# FT-009: Raydium CLMM and Orca Whirlpool in shadow, then a dry run (PLAN-ADDENDUM WP-21 phase A)

- **Status:** part 1 (shadow) ran 2026-10-07 02:19–04:20 UTC: all 8 criteria pass, one latency problem found (Results). Part 2 (dry run) not run yet. The number is provisional (FT-008 is WP-22's pool refresh); it runs after Stage 0 closes.
- **Build:** lane/wp21 as merged by the owner (record the binary's git hash and sha256 here at the start). Part 1: master 221a2d8, bin/arbx-221a2d8 (sha256 `d0bec83bb49115c5…`).
- **Config:** `deploy/arbx-wp21-shadow.toml` (FT-006's config with `[pools] rayclmm = "quote"`, `whirlpool = "quote"`, the seed list below, `[canary] enabled = false`). Data: `data/seed-pools-wp21-shadow.csv` to `/root/arbx/data/`.
- **Mode:** part 1 shadow (`arbx campaign --mode shadow`), part 2 dry run (`arbx campaign --mode dry-run`, `[dry_run] simulate = true`). Nothing is sent: in `quote` mode a live or canary route through either venue is refused `venue_quote_only`, and this config cannot start a canary.
- **Budget:** 0 lamports.
- **Goal:** show that the engine prices, follows and decides routes through Raydium CLMM and Orca Whirlpool from live state with no phantom or poisoned decision, and that their bundles verify and simulate with no account or CU error.
- **Preconditions:**
  - Stage 0 closed; Haan used by this bot alone (I-3); `arbx check --config deploy/arbx-wp21-shadow.toml` passes on Cherry with the uploaded binary.
  - Both venue programs at the deploy slots their ports were proven on (Raydium CLMM 451,479,902, Orca Whirlpool 440,170,207). The binary checks this itself at every segment's start: a changed or unreadable programdata switches that venue off for the segment, with a WARNING in run.log (review F5). meta.json `clmm_deploy` holds the start's and the end's reads: both `ok` in every segment.
  - `[pool_refresh]` stays off (it is, in this config): WP-22's refresh does not read these venues' swaps, so it would drop their rows as idle.
  - The pools are the seed list's: registry.json rows of these venues are never candidates (review F1). With the real registry the boot gives exactly 105 Raydium CLMM and 137 Whirlpool pools (checked with `arbx pools`, public RPC, 2026-10-06 20:37 UTC: 2,417 candidates, 1,600 pools in 386 SOL pairs, 92 of them with a CLMM or Whirlpool pool, 84 of those with older venues' pools).

## The seed list

`data/seed-pools-wp21-shadow.csv` is the 2026-10-06 list (1,500 rows, unchanged, first) plus 242 SOL pools, verified on chain at 2026-10-06 18:52 UTC (slot 453,987,194) with read-only public RPC:

| Source (`source` column) | Raydium CLMM | Orca Whirlpool | Rule |
|---|---|---|---|
| `wp21:seed-token` | 79 | 102 | the token is traded against SOL by the 2026-10-06 list; at most the 3 deepest pools of each venue |
| `wp21:census:<legs>` | 6 | 15 | a CLMM or Whirlpool SOL pool used in at least 2 rival arbitrage legs of the venue census (docs/research/venue-census.md) |
| `wp21:census-token` | 20 | 20 | the census token's other deepest pools (a route needs two pools) |
| **Total** | **105** | **137** | 181 seed-token, 21 census, 40 census-token |

- **Verified for each pool:** the owner and layout (Raydium PoolState 1,544 bytes, Orca Whirlpool 653), the mints the scan saw, liquidity at the price, swaps enabled and open (Raydium status bit 4, open time), a WSOL side of at least 2 SOL (median 49 SOL), Raydium's AmmConfig, and no Token-2022 mint the engine refuses (a transfer fee, a transfer hook, paused, default frozen). 9 picked pools failed and were left out (7 transfer fees, 2 below 2 SOL).
- **Booted by the engine:** `arbx pools` on the whole list (public RPC) puts all 242 into SOL pairs: 92 pairs hold one, 77 of them with pools of the older venues. Its other drops (115, `transfer_fee`) are the 2026-10-06 list's own.
- Built by a read-only script (/home/moiz/arbx-offload/wp21/seeds/build_seeds.py, `verify.json` beside it: every pool with its checks). Candidates came from the part-1 scans of all SOL-paired Raydium CLMM (1,208) and Orca Whirlpool (1,492) pools, read at 2026-10-06 ~15:20 UTC.

## Part 1: shadow, ≥ 2 h (`arbx campaign --name ft009-shadow --mode shadow --hours 2 --segment-min 30`)

Pass criteria, written before the run:

1. **Boot and following.** At most 5% of the 242 WP-21 pools dropped at boot (each drop has its reason). Every booted CLMM pool follows its parts and tick arrays (`clmm_tick_array` role in accounts.bin); `read_missing` for them is explained by accounts that do not exist (`clmm_absent`).
2. **Priced.** Routes with a Raydium CLMM or Orca Whirlpool leg are priced in both directions (decisions.jsonl routes with `size` and `gross`). `unquotable_clmm_array` and `unquotable_clmm` are each below 5% of those routes' evaluations; the `sz_clmm_*` and `sz_whirl_*` refusals are listed with counts. No `venue_upgraded` (the deployed binaries are the ones proven: deploy slots 451,479,902 and 440,170,207).
3. **No phantom decision.** Every trigger of a decision whose best route has a CLMM or Whirlpool leg landed, finalized, without error, in its recorded slot (`getSignatureStatuses`, as FT-000).
4. **No poisoned decision.** No prediction is ever a priced state, and the priced state equals the recorded account versions: `arbx replay --compare` of a 1 h slice is whole and identical (decisions, commit groups, attempts, both digests); `arbx quote` of a sample of 50 such would-sends at their state versions gives their recorded size and gross.
5. **Accuracy where visible.** The transaction stream follows PumpSwap only (Haan: one filter, one account) and the deshred feeds name no CLMM program, so the accuracy monitor will most likely score no CLMM or Whirlpool swap here (no hints): whatever it scores (predictions.jsonl, `venue` RayClmm or Whirlpool) is exact, and the count is reported. The quotes are checked against the programs in part 2 instead (criterion 7). A second stream on `whirLbMi…` / `CAMMCzo5…` (OD-1) would score them all.
6. **Real or not there.** For the would-sends with a CLMM or Whirlpool leg: the share closed within 2 s by a winning rival round trip (FT-000's taker method), and their quoted SOL.
7. **Latency (review F2).** `state_engine_to_decided` p99 and p99.9 (status.jsonl) within twice FT-006's. The lab's engine benchmark, per transaction: Stage-0 shape without CLMM p99 19-34 µs, p99.9 73-127 µs; CLMM shape (20 CLMM + 60 AMM v4 pools) p99 70 µs, p99.9 102 µs at aligned prices, p99 262 µs, p99.9 343 µs in the worst case (made-up prices: every route sized through long walks).
8. **Following.** `clmm_absent_confirmed` against `clmm_absent` (review F6: an array read missing is priced as absent only once a second read confirms it), the follow sets' moves per hour, and `read_missing` explained.

## Part 2: dry run, 1 h (`arbx campaign --name ft009-dry --mode dry-run --hours 1 --segment-min 60`)

As FT-002, restricted to bundles with a CLMM or Whirlpool leg:

1. **Volume:** ≥ 50 such would-send bundles signed and recorded in full (attempts.jsonl `dry_run`).
2. **Signed-byte checks (`verify_bundle`):** 0 failures.
3. **Simulation:** every such bundle simulated read-only. Would-fails from gaps already taken are expected (the route's min_profit reverts it). **0 failures caused by our transaction:** no CU exceeded, no loaded-data limit exceeded, no account error (Raydium NotEnoughTickArrayAccount, InvalidFirstTickArrayAccount, MissingTickArrayBitmapExtensionAccount; Orca InvalidTickArraySequence, TickArraySequenceInvalidIndex, DifferentWhirlpoolTickArrayAccount; Anchor 3005 AccountNotEnoughKeys, 3012 AccountNotInitialized), no rent error.
4. **CU:** the simulated CU of each leg within its fallback allowance (`Venue::leg_cu`: Raydium CLMM 64,000 + 10,000 a step, Orca 48,000 + 10,000 a step; a CLMM leg from a measured CU table never asks less: review F7). LiteSVM through the deployed nexus-v2 measured 29,362–68,666 for Whirlpool legs (1–3 steps) and 47,642–175,354 for Raydium CLMM legs (1–15 steps), every one within it (program/venue-harness `tests/arbx_bundle_clmm.rs`).
5. **No transmission:** no copies or bundles records; frz's signatures unchanged.
6. **Coverage:** CLMM and Whirlpool legs paired with at least two of the older venues, create+close and held-account routes.
7. **Each leg as quoted (review F10).** For every simulated bundle that succeeded or failed only on the profit check: the amounts each leg delivered (nexus-v2's NXV2OUT records in the simulation's logs, `proglog::delivered_from_logs`) against the quoted `mid` and `back` of its attempt. On the decision's state they are equal (the lab: every leg exactly); against the RPC's later state, report the differences per venue.
8. **Size (review F11).** `oversized` refusals by venue pair. The lab, the vectors' five routes: with no lookup table 2 of 5 are oversized (PumpSwap ↔ Whirlpool, 1,382 and 1,448 bytes) and Raydium CLMM ↔ Whirlpool fits by one byte (1,231); with the default `[exec] alts` as they are on chain (10 of 12 tables exist; they hold both CLMM programs, the token programs, Memo and nexus-v2, and 28 of the 242 pools) all fit, 707-1,119 bytes; `alt_index` adds learned tables. A Raydium leg naming 6 tick arrays and the extension adds about 6 keys (192 bytes) over these vectors, so some Raydium routes can still be oversized: if they are more than 5% of this part's CLMM bundles, an owner lookup table of the WP-21 pools' fixed accounts (pool, vaults, AmmConfig, extension or oracle, observation: about 6 a pool, about 1,450 addresses for the 242, so 6 tables) closes it. Its rent is about 0.0583 SOL per 256-address table, about 0.35 SOL for the 6, recovered when they are closed; that is the owner's decision.

## What the lab already showed (lane/wp21)

- **nexus-v2 needs no upgrade.** It CPIs any allowlisted program with the builder's account list and patches the input amount at the leg's offset; the deployed ELF's allowlist holds both programs. Five engine-built routes (Whirlpool ↔ PumpSwap both ways, Raydium CLMM ↔ Whirlpool both ways, Raydium CLMM → AMM v4) land through the deployed nexus-v2 and the real programs in LiteSVM, each leg delivering exactly arbx-sizing's quote; a min_profit the route cannot reach fails 0x4e580002.
- **Exact maths.** 1,988 Raydium CLMM and 691 Orca swaps of the venue-parity fixtures quote exactly as the deployed programs execute them (1,343 exact out), and the accuracy monitor's post-states are exact on all 2,679.
- **Replay.** Scenario S17 (USDC/SOL with both venues' pools) replays identically, would-send included; in a canary run of the same state the CLMM routes are priced but held back (`venue_quote_only`) and the best route of the venues that send is sent (review F3).

## Results

### Part 1: shadow (2 h: 2026-10-07 02:19:36–04:20:00 UTC)

- **Run:** `arbx campaign --name ft009-shadow --mode shadow --hours 2 --segment-min 30` on Cherry, 4 segments: p1 02:19:36–02:50:02, p2 –03:20:28, p3 –03:50:52, p4 –04:20:00 (28.7 min, the campaign's time left). Every segment stopped `deadline`, exit 0, class natural; the campaign ended "time up".
- **Build:** bin/arbx-221a2d8, frozen by the campaign as `runs/ft009-shadow/arbx-d0bec83b` (git 221a2d8e, clean, release; sha256 `d0bec83bb49115c5…`).
- **Config and data:** `deploy/arbx-wp21-shadow.toml` (sha256 `3464fe4ae8e716a8…`; the frozen copy is byte-identical to the repo's), seed list `data/seed-pools-wp21-shadow.csv` (sha256 `58bf65e0e81e785e…`), registry.json `7d4d05c8…`.
- **Records:** `/root/arbx/runs/ft009-shadow/` (1.4–1.7 GB a segment). Read-only copies were pulled to `/home/moiz/arbx-offload/ft009/`: the small streams, decisions, accounts.bin, commits and rivals of all 4 segments, and the journal of p4 for the replay. The big streams were deleted after the analysis.
- **Health:**
  - the state stream was connected in every status line (180 / 181 / 181 / 173), with 0 reconnects; the boot re-read took 14.1–14.7 s;
  - the recorder had 0 drops and 0 records lost at close;
  - RSS stayed ≤ 1,061 MB and CPU ≤ 0.63 core;
  - `clmm_deploy` was `ok` at the start and the end of all 4 segments, and `overrides` was empty (no venue switched off).
- **Nothing was sent:** all 3,509 attempts are `sent: false` (shadow), there are no copies or bundles files, and the send path reports "sent 0". Spend 0; BUDGET.md is unchanged.
- **Chain checks:** read-only, on the public RPC (api.mainnet-beta.solana.com, paced; it answered 429 at times, retried): 504 `getSignatureStatuses` (searchTransactionHistory, 256 signatures a call), 641 `getTransaction` and 4 `getMultipleAccounts`.

| # | Verdict | Numbers (source) |
|---|---|---|
| 1 Boot and following | **PASS** | All 242 WP-21 pools booted in every segment (105 Raydium CLMM, 137 Whirlpool, all in SOL pairs), with 0 dropped. meta.json `pools.dropped` lists 263 `transfer_fee` drops, all of the older venues (DLMM 159, DAMM v2 67, CPMM 37). 1,600 pools in 386 SOL pairs. accounts.bin: each of the 242 has its pool account, both vaults and ≥ 1 `clmm_tick_array` (role 14). That is 1,504–1,515 tick arrays a segment, 1–17 a pool (median 6). `read_missing` was 1,955 / 1,956 / 1,957 / 1,962. Its CLMM part is `clmm_absent` (227 / 225 / 224 / 227): the Oracle PDA of the 94 Whirlpools without the adaptive fee and 129–131 tick arrays at boot, then 0–2 newly followed tick arrays, each counted at its first read and again at the read that confirmed it. All 238 distinct accounts held absent still do not exist on chain (`getMultipleAccounts` at slots 454,120,878 and 454,124,727). The other ~1,730 are PDAs of the older venues and the wallet that do not exist: 385 wallet token accounts, 378 DLMM bitmap extensions and about 960 followed DLMM bin arrays. FT-006 had the same class (1,679–1,682). |
| 2 Priced | **PASS** | There were 9,467,986 route evaluations with a CLMM or Whirlpool leg. 8,673,409 of them (91.6%) were priced with `size` and `gross`: with the CLMM leg buying 3,930,973 of 4,227,947 (93.0%), selling 3,817,667 of 4,227,947 (90.3%), and both legs CLMM 924,769 of 1,012,092 (91.4%). All 24 venue pairs with a CLMM leg were priced both ways (84.7–97.6% each). `unquotable_clmm`: 5,889 (0.062%; 77% of the pool mentions on 4 pools: Whirlpool Ecjn9eVB and Ckp1kwZq, Raydium 8GKgXyJh and 2AXXcN6o). `unquotable_clmm_array`: 1,190 (0.013%). Both are far below 5%, at most 0.096% and 0.018% in any segment, and the decisions' counts equal status.jsonl's `reject_*` counters. `sz_clmm_*` and `sz_whirl_*`: 0 of every kind. `venue_upgraded`: 0. The other unpriced routes were refused by the state gate (`pending_commit` 422,894, `resync` 125,703) or by their other leg (`unquotable_dlmm_liquidity` 105,425, `pump_quote_not_sol` 72,749). |
| 3 No phantom decision | **PASS** (one trigger on an abandoned fork that priced nothing) | 142,470 decisions had a CLMM or Whirlpool best route; 3,304 of them were opportunities and 2,020 would-sends. They had 128,737 distinct triggers: 128,736 were finalized, without error, in the recorded slot. The other one, `5rtRUfdS…` (p4), was in slot 454,108,426, which the engine itself recorded as abandoned 113 ms after the decision (`fork_abandoned`, `not_ancestor`). Of that trigger's 4 decisions, 3 were refused `fork_pending`. The fourth (8991, Whirlpool → DLMM) was `below_min_profit` (−55,599), priced on state of slot ≤ 454,108,325 (`sv`), with nothing from the abandoned slot. Every trigger of the 3,304 opportunities and 2,020 would-sends landed. |
| 4 No poisoned decision | **PASS** (one 28.7-min segment, not the planned 1 h) | **No hint is ever priced state:** 46,482 triggers, every one `hint_only` with `opp` null, among them 2,655 Raydium CLMM and 3,561 Whirlpool hints. **Replay** of p4 with target/release/arbx 221a2d8 (same source as the run; not the same binary, because Cherry's is stripped): `ok` and whole. 47,040 / 47,040 decisions, 44,907 / 44,907 commit groups and 753 / 753 attempts identical; state and decision digests equal at `run_end` and `stop_end`; 0 gaps, 0 missing accounts, 0 verdict mismatches (24.5 s, 70× real time). The brief allowed one segment's records (disk), so the plan's 1 h slice was not replayed. **`arbx quote`** of 50 CLMM would-sends of p4 (every venue pair once, then random), each at the accounts.bin aseq the journal had handled when the decision was made: the 36 decisions resolved by a commit group give their recorded size, gross, net and CU, and the state they read ends at the decision's `sv`. The 14 resolved by a timer (13 timeout, 1 quiescent) cannot be quoted at an aseq: right after the last account record their group is still pending, so the arrays it writes are left out (`unquotable_clmm_array` 12, `unquotable_dlmm_array` 2), and `arbx quote` has no version for the state after a TIMER record. In the replay's own pass (`--reprice-sizes opt`), all 667 CLMM opportunities of p4, the 452 would-sends included, re-price at their decision's state to the recorded gross and net, and the size search returns the recorded size. |
| 5 Accuracy where visible | **PASS** | The plan expected no CLMM score, but the shred feeds (dz-leader, dz-retransmit-eu) decode both programs' swaps. The monitor scored 3,368 post-states (predictions.jsonl): Raydium CLMM 1,230 / 1,230 exact, Whirlpool 2,134 / 2,138 (p1 726 / 727, p2 611 / 611, p3 408 / 411, p4 389 / 389). 3 more had an unknown pre-state and were not scored. **The 4 misses** (Dsxt7wUi in p1; Czfq3xZZ and BofA2ViU twice in p3) have the price, tick, fee growth and protocol fees exact; only the liquidity differs (+0.002% to +2.5%). Each transaction swaps and then adds liquidity to the same pool: its events are Traded, then LiquidityIncreased (3 of them with PositionOpened before it), per `getTransaction`. That deposit is outside the swap model, not a quote error. |
| 6 Real or not there | **Measured: real** | **Volume:** 2,020 would-sends with a CLMM or Whirlpool leg, quoting 1.0642 SOL net (1.1084 gross) at the decision's size. The executor's attempts, capped at frz's 0.195 SOL of WSOL, expected 0.2418 SOL (median size 0.033 SOL). **FT-000's taker method:** the taker is the first transaction touching both pools within 2 s; 621 such transactions were fetched, all landed without error; one counts as a win when its signer gained SOL + WSOL and spent no other token. **859 would-sends (42.5%) were closed by a winning rival round trip, 0.3192 SOL (30.0% of the quoted SOL).** 109 more (0.0447 SOL) were taken without a gain, and 1,052 (0.7003 SOL, 65.8%) had no two-pool taker. Per win, rival gross ÷ our quoted gross was p25 0.91, p50 1.00, p75 1.00. Winning takers were first seen before our decision for 119, 0–20 ms after it for 129, 20–80 ms for 266 and ≥ 80 ms for 316 (29 unknown). Top winners: GLiCiNEn 75, FUEL3Te8 53, 9ZAPm4VS 41. **The ones with no taker were real too:** all 1,052 routes re-priced below min profit within 2 s (p50 49 ms after our decision; 2,016 of all 2,020). Of the 16 largest (0.605 SOL), 10 (0.263 SOL) were closed by winning round trips through another pool (MriyaNN8 +0.173 SOL on `Ce2gx9…pump`) and 5 by ordinary trades. The largest, JUP sold into the CPMM pool BakaWq (0.297 SOL), was taken by a JUP seller 0.4 ms after its trigger, in the same slot. **With those, at least 869 would-sends (0.582 SOL, 54.7%) were closed by winning rival round trips.** |
| 7 Latency | **PASS** (p99 and p99.9), but the median regressed (problem below) | **p99:** `state_engine_to_decided` (status.jsonl, run) 7,176 / 6,868 / 6,960 / 6,668 µs against FT-006's 6,027 / 6,053 / 6,034: at most 1.19×. **p99.9:** status.jsonl has none, so it was computed from decisions.jsonl's stage times (`t_decided − t_update_recv`), the same way for both runs. After warm-up: 8,947 µs against 7,423 (1.21×). Counting the boot window it is 456.6 ms against 8.1 ms: decisions before `warmup_ready` wait up to 2.5 s for the boot re-read, and they are 1.3% of FT-009's evaluations (30-min segments) against 0.8% of FT-006's (60-min); nothing is sent then. Pricing alone (`engine→priced`) was p50 141, p99 2,102, p99.9 3,707 µs against 75 / 1,300 / 2,523 (at most 1.9×). **The median moved:** p50 333–700 µs against 103–131 (3–6×) and p90 5,343–5,617 against 1,019–1,337 (4–5×). That is the commit wait. |
| 8 Following | **PASS** | `clmm_absent_confirmed` was 2 / 1 / 0 / 1 against `clmm_absent` 227 / 225 / 224 / 227; the rest is the boot read. The follow sets moved 17 times in 2 h (8.5 an hour; accounts.bin MARK `watch_list_changed`), adding 21 tick arrays (15 Whirlpool, 6 Raydium). Every one of those marks named CLMM tick arrays only. `read_missing` is explained in criterion 1. |

**CLMM decision counts** (decisions.jsonl):

| Segment | Evaluations | CLMM-leg routes priced | Decisions with a CLMM best route | CLMM opportunities (SOL) | CLMM would-sends / all (SOL) |
|---|---|---|---|---|---|
| p1 | 77,453 | 3,222,523 of 3,559,812 | 50,105 | 1,096 (0.8397) | 668 / 1,056 (0.2802) |
| p2 | 63,002 | 2,050,389 of 2,216,358 | 37,962 | 792 (0.3070) | 453 / 846 (0.1277) |
| p3 | 55,921 | 1,750,816 of 1,907,428 | 29,543 | 749 (0.4166) | 447 / 854 (0.1833) |
| p4 | 47,040 | 1,649,681 of 1,784,388 | 24,860 | 667 (0.8674) | 452 / 753 (0.4730) |
| **Total** | **243,416** | **8,673,409 of 9,467,986** | **142,470** | **3,304 (2.4307)** | **2,020 / 3,509 (1.0642)** |

- CLMM routes made 57% of the would-sends and of the opportunities (3,304 of 5,801).
- **Biggest pairs by count:** DLMM → Raydium CLMM 337, Raydium CLMM → DLMM 286, Whirlpool → Raydium CLMM 279, Whirlpool → DLMM 266, DLMM → Whirlpool 251.
- **Quoted SOL is concentrated:** the 3 largest would-sends quote 45% of it, none with a two-pool taker; criterion 6 covers them.
- **Sizes:** the shadow executor builds every bundle up to the signature. CLMM bundles were 579–1,171 bytes; none was oversized (limit 1,232). The CU is the fallback formula (the CU table has no CLMM legs).

**Problem found: a transaction through a CLMM pool makes its commit group wait the full timeout.**
- **How many:** 94,940 commit groups touched a Raydium CLMM or Whirlpool pool in 2 h, and 47,484 of them (50.0%) ended `timeout_unknown`. Other groups: 4.4% (FT-006: 3–4%). The commit wait was p50 5,001 µs for these groups against 25 µs for the others (commits.jsonl, `t_commit − t_first_update`).
- **What is missing:** 97.5% of those timeouts missed only CLMM accounts:
  - the Whirlpool Oracle PDA, 38,588 times; 94 of the 137 do not exist;
  - tick arrays: Whirlpool 11,675, Raydium 640;
  - the Raydium AmmConfig, 3,307 times. Routers mark it writable (getTransaction of three such transactions: `routeUGW…`, `proVF4pM…`), but a swap never writes it;
  - the Raydium tick-array bitmap extension, 111 times.

  The AmmConfig is shared by many pools. It alone also made 1,210 groups of the older venues time out: their transaction marked a watched AmmConfig writable, most likely by routing through an unlisted Raydium CLMM pool with the same config.
- **Why:** `write_set` (src/engine.rs) puts every writable part of a watched pool into W(T). A transaction marks these accounts writable without always writing them:
  - the Oracle may not exist;
  - a swap never writes the AmmConfig;
  - a tick array changes only when a tick is crossed, and the extension only when it is.

  FT-000 S1-8 fixed the same pattern for PumpSwap mints.
- **Cost:** correctness is untouched (the replay is identical and the quotes are exact), but:
  - half the commit groups of CLMM transactions wait the full 5 ms, and so do the decisions they trigger; that is criterion 7's p50 and p90;
  - pools wait on groups that never complete, so `pending_commit` refusals rose to 2.5–3.65% of the routes priced or refused that way, from 0.37–0.76% in FT-006.

  FT-000 found 75% of the quoted SOL taken before our decision or within 20 ms of it.
- **Fix, before any CLMM route is sent (phase B):** leave out of W(T) the parts a transaction may leave unwritten:
  - accounts the engine holds absent;
  - CLMM tick arrays;
  - the Raydium AmmConfig and bitmap extension;
  - the Whirlpool Oracle.

  Make it a journaled engine knob like `wt_skip_pump_mints`, so older runs replay as recorded. A write that does come still joins its group, or arrives as a late member. Then measure p50 and p90 against FT-006 again in a short shadow run.

**Other observations:**
- **`broken_quote`:** 118 routes in one p4 decision (5843), all selling USDC into the CPMM pool 47hq28mc right after a trade there; 10 of them have a CLMM buy leg. The guard refused round trips returning over twice their input, as designed. It is not a CLMM matter.
- **`arbx quote` and timers:** it cannot name a state resolved by a timer (criterion 4). A version by journal `seq` would close that gap.
- **One fork:** p4 had the run's only abandoned slot (`fork_versions_dropped` 72, `fork_pending` 442 routes); criterion 3 covers it.

**Verdict, part 1: pass.** All 8 criteria pass. Criterion 3 has one trigger, on a fork the engine itself abandoned, that priced nothing. Criterion 4 was replayed on one 28.7-min segment. Criterion 6 is a measure: the CLMM would-sends are real. One problem was found: the commit wait on CLMM transactions (latency and coverage, not correctness).

**Part 2 (dry run):** it can go ahead on the same build and config with `--mode dry-run`; the config already has `[dry_run] simulate = true` at 2 a second. Part 1 found nothing in the bundle path that part 2 tests: the shadow executor built all 2,020 CLMM bundles up to the signature with no build refusal, and none was oversized. At about 1,000 CLMM would-sends an hour, part 2's 50 bundles come easily. Run it after FT-010 ends, because Haan serves one process (I-3). The commit-wait fix is needed before phase B, not for part 2.

## Results, part 2: dry run (2026-10-07 07:28–08:29 UTC, bin/arbx-4c6f2c9 with the commit-wait fix, 2 × 30 min, nothing sent)

- **Bundles:** 1,050 would-sends, and **1,050 `dry_run_ok`**: every bundle passed `verify_bundle` (bytes, accounts, tip, min_profit) and was simulated.
- **Simulations** (sims.jsonl, both segments):
  - No account, CU or loaded-data error on any bundle.
  - **Through a Raydium CLMM or Orca Whirlpool leg:** 386 simulated. 376 ended in our own profit check (`0x4e580002`, "every leg ran, the round trip did not pay": the gap had moved by simulation time) and 10 passed.
  - **Older-venue bundles:** the same pattern, plus 3 venue errors (6036 and 3005) on older pools.
  - So every CLMM/Whirlpool leg executed with the engine's account lists and data.
- **The commit-wait fix (p2, 41,660 groups):**
  - groups touching a CLMM pool: `timeout_unknown` **8.0%** (FT-009 part 1: 50%);
  - other groups: 5.3%;
  - 0 late members, 0 `torn_suspect` decisions (review finding 1's case did not occur).
- **Verdict: part 2 passes.** The owner allowed live sends through both venues ("Yes u can", 2026-10-07). The live config is pending the owner's permission setting (see the session).

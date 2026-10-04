# Breadth-first selective arbitrage: a design built on coverage and selectivity

## Summary

The bot wins where faster bots are absent. It covers more routes than they do, prices them exactly, and attempts only the gaps that a faster rival is unlikely to have taken already.

The evidence does not suggest this is a large market. The thesis rests on three bets:

- **Bet 1.** Some gaps survive longer than one slot, or sit on routes the fast bots don't model.
- **Bet 2.** Our two binding limits on those gaps are coverage and pricing accuracy, not latency. Both can be fixed with engineering.
- **Bet 3.** Bundle misses cost nothing. So being selective costs only Jito rate (5 bundles/s), not lamports.

Before we build anything live, a measured go/no-go census decides whether the larger universe is worth chasing.

---

## 1. Thesis: which money, why we can win it, and SOL/h

### Money we will not target

- **Rungs 0-1.** These are backruns sequenced or bundled with the opener: 41% of big-win SOL, about 11.5 SOL/h. Reacting to shreds cannot reach them, because the winners see the opener before it executes.
- **Contested rung-3 gaps on crowded DLMM↔PumpSwap pairs.** Bgokg3ju and A9pQ1Qsv profit here using on-chain sizing, conditional tips and 600-750 SOL of WSOL. Sprayers lose money here.

### Money we will target (market gross to winners, estimates)

| Segment | Evidence | Market SOL/h |
|---|---|---|
| **A. Slow or persistent big gaps (gap age ≥150 ms) on the current pools** | PATTERNS #6: 34 wins in 2.47 h, 1.0 gross. rival-synthesis p10-p15: 1.47 SOL in 0.915 h, of which ≥0.42 is within the 4.2 SOL cap. We had **no opportunity for 18 of 23**, and **9 of 23 touched pools we never priced**. | 0.6-1.6 gross; 0.2-0.46 within cap |
| **B. Big wins where one leg is unwatched** | PATTERNS: 71 wins, 3.78 SOL in 2.47 h; 25% at ≥150 ms | about 1.5 total; about 0.4 slow |
| **C. Rung-3 gaps that use a leg venue we don't support** (Raydium CLMM, Whirlpool, DAMMv1) | PATTERNS venue sets: 3.91 SOL in 2.47 h. My recheck of w5h2-p1/p2 exec + rivals, PumpSwap-measured only: 0.4-1.2 SOL/h (`venuemix2.py`) | 0.4-1.6, possibly up to 2x with non-PumpSwap legs |
| **D. Small, uncontested Jito-style wins** (where our 23 wins came from) | Small Jito wins 1.18 SOL in 2.47 h; the slow small slice is only 0.094 | about 0.48 |
| **E. Routes outside our universe:** USDC/USDT triangles, Manifest, prop-AMM legs, stale and new pools | 8oSD5a9E's USDC trio: about 10 SOL in one slot, via an unwatched USDC DLMM pool that had been idle for 37,958 slots, at 220-270% returns. DtvmxrTA's best trades were 3-4 hops (0.488 and 0.665 gross). Babq used Manifest in 18 of 95 successes. 4BQ6 has 44% of its backruns on pools we don't watch. | **Unmeasured, heavy-tailed** |

### Why we can win A-E

**Persistence filters out fast rivals by definition.** On these gaps our 15 ms decision lag and 66-79 ms bundle landing are not decisive. Two things have been: we did not see the routes, and when we saw them we priced them wrong. Persistent priced gaps were about 6x overpriced: our expected 0.076 SOL against the takers' 0.0124 SOL gross.

**Where a gap is real and uncontested, our math is already exact.**
- 18 of 22 bundle wins matched the prediction to the lamport.
- The closers' takes matched our quotes within 40 lamports (MriyaNN8 50,407,617 vs our 50,407,577).
- The fix is breadth plus a verification oracle, not a new pricing method.

**The winners of the slow slice bid only about 33% of gross** (priority p50 670k lamports). We can pay that.

### Counter-evidence (taken seriously)

- **Crowding.** Pools with 1-5 arb bots carried 0.04 SOL of market wins over the whole night. Where nobody competes, there is no flow and so no money.
- **The top bot is present even on old gaps.** MriyaNN8 takes about a third of slow-slice wins.
- **The fast bots already do multi-hop:** Mriya (2-5 hops), 9EwQ (USDC, Manifest, Tessera), DtvmxrTA (Manifest), R32xAccF (12+ venues).

Therefore breadth must be **flow-anchored**. We add unusual counter-legs (USDC pools, CLMM, CLOB, prop AMMs, stale pools) to tokens whose main pools carry heavy flow. We do not add quiet pools.

### SOL/h estimate (labelled estimate)

| Stage | Our net SOL/h | Range |
|---|---|---|
| Stage 2 (current venues + CLMM family + 3-hop via hubs) | about 0.1 | 0.03-0.25 |
| Stage 3 (+ CLOB, prop AMMs, stale sweeps) | about 0.25 | 0.05-0.6 |
| Stage 4 (+ on-chain sizing) | about 0.4 | 0.1-0.8 |

- **Reference point:** today the bundle arm makes about 0.00005 SOL/h before rent, while failed direct copies cost about 0.0065 SOL/h.
- **Judgement:** about a 35% chance that the census (experiment E1) shows segment E is too small, which would cap us near the Stage 2 level.

---

## 2. Off-chain architecture

### Data flow

```
Shreds (dz-leader, dz-retransmit-eu, astralane) ──► TxDecoder ──► ActivityMap (flow, competitors, hot tokens)
                                                       └──► PendingWrites (which watched accounts each tx writes)
gRPC accounts (Haan; owner filters per venue) ──► VersionedStore (slot, write_version, last_writer_sig)
gRPC tx+meta (all venues; our wallet) ──────────► Census/Closer audit, Ledger
                     │
Discovery ──► UniverseGraph (mints × pools × hubs) ──► CycleIndex (pool → cycles)
                     │
VersionedStore + CycleIndex ──► Pricer (native integer math: search) ──► Verifier (local SVM: truth, CU, size)
                                                                              │
                         Selector (EV, competition map, rate budget) ◄────────┘
                                │
                         Builder (v0, ALT index, ATA create/close, tip) ──► Sender (Jito bundle; per-leader policy)
                                                                              │
                         Ledger/Reconciler ◄── bundle status + wallet tx stream + hourly balances
                         Supervisor (equity stops, quarantine, kill-switch)
```

### 2.1 Discovery and universe (keep and generalise `tools/pooldisco`)

**Inputs:**
- gRPC account subscriptions filtered by owner and discriminator (or data size) for every venue's pool accounts. One subscription per program gives every pool, including idle ones.
- Tx-stream decoding of pool-creation instructions: PumpSwap create_pool and migrations, DLMM/DAMMv2 initialize, Raydium CLMM/Whirlpool/CPMM create, Manifest market create, LaunchLab and DBC graduations.

**Graph.** Mints are nodes and pools are edges. Hub tokens are WSOL, USDC and USDT; LSTs come later. Cycles are SOL-anchored:
- 2-cycles: SOL→X→SOL across different pools.
- 3-cycles: SOL→X→USDC→SOL and SOL→X→USDT→SOL, plus the reverses.
- The hub leg (USDC/SOL) uses the best few SOL/USDC venues we can quote. Prop AMMs are usually the tightest.

**Tiers:**

| Tier | Size | What we stream | Use |
|---|---|---|---|
| A, hot | ≤1,500 pools | Full state: pool account, vaults, DLMM bin arrays ±2, CLMM tick arrays ±2, bitmap extensions | Reactive and persistent evaluation |
| B, warm | ≤10,000 pools | Pool account only | DAMMv2 and CLMM quote exactly within range from the pool account alone; DLMM gives its price from the active bin; PumpSwap and CPMM vaults are subscribed only for tokens with flow |
| C, cold | everything else | Cached pool accounts (pushed only when they change) | An idle pool's cached state is re-priced whenever a pool for the same token moves. This is how stale-pool gaps like the trio are found. |

- **Promotion:** B or C → A when the marginal-rate prefilter flags a gap, or when hot-token ranking says so. We fetch the missing arrays and vaults with getMultipleAccounts (about 50-150 ms), then verify. That is acceptable for persistent gaps.
- **Hot-token ranking:** a rolling 10-minute score built from flow volume and arb-like transactions (2+ pools of one mint, no net token change, as pooldisco detects), plus our census results.
- **Junk filter:**
  - Token-2022 mints with transfer fees, transfer hooks or a permanent delegate.
  - A freeze authority, unless the mint is allowlisted.
  - TVL below 5 SOL per side.
  - Pools whose triggers are almost all undecodable. DHbktet3wt produced 76% of p9's trigger signatures with almost none quoted.
  - Anything the SVM cannot execute.

### 2.2 State model: keeping post-trigger state consistent

This removes the two engine bugs behind 10 of the 16 biggest losses.

1. **No predictions on the money path.** Pricing reads only on-chain account state from the gRPC stream.
   - Failed transactions produce no account writes, so a phantom gap from a failed decoded swap cannot appear.
   - Decoded swaps from shreds feed only the ActivityMap (competition and flow) and prefetching.
   - This deletes `self.preds` (engine.rs:641), whose leftovers fed the DreMAMRc, 4pANrqEv and AwmaWjsR losses.
2. **Transaction-atomic application.**
   - Every update carries its slot, write_version and `txn_signature` (already parsed at grpc.rs:398).
   - PendingWrites holds, for each transaction T seen in shreds, the watched writable accounts it touches (message keys plus resolved ALTs).
   - An account updated by T stays "pending" until every other watched account that T writes has arrived, or 5 ms pass.
   - A route can be priced only when none of its accounts are pending and all of its parts are within 1 slot of each other.
   - Today the PumpSwap exemption skips the parts-skewed check (store.rs:66). It is removed.
   - This blocks the torn split-route reads, such as the AgmLJBMD trigger (6 losses, plus the bolt win, which was itself priced on a torn read).
3. **Tx with an unknown ALT.** If we cannot resolve the transaction's lookup table, we fall back to quiescence: no update to the route's accounts for 3 ms after the last write. The ALT fetch is retried rather than cached as missing for the whole run (fixing engine.rs:431).
4. **Forks.** On a slot-status rollback we invalidate state newer than the fork point and refetch.
5. **Warm-up gate.** Nothing is sent until every Tier-A pool is complete and the store is within 2 slots of the chain tip. This prevents the 3.0-3.8 s late sends at segment start.

### 2.3 Pricing: native search plus local-SVM truth (the core competency)

**Native integer math, used for search and sizing:**

| Family | Venues | Status |
|---|---|---|
| CPMM | PumpSwap (fee tiers, creator fee), Raydium CPMM, AMM v4, DAMMv1 incl. stable/LST virtual price | Keep cp.rs, dlmm.rs, dammv2.rs |
| DLMM | Bin walk with dynamic fee on the chain clock; input capped to the bins we hold | Keep |
| DAMMv2 | Uses the chain clock, not local time | Keep, fix clock |
| CLMM | Tick-array walk shared by Raydium CLMM, Whirlpool, Byreal and Pancake; per-program layouts and fee rules | New |
| CLOB | Manifest and Phoenix book walk | New |
| Bonding curves | pump.fun, LaunchLab, DBC | Low priority |

**Local SVM verifier.** An embedded program runtime loaded with:
- the real ELFs of every venue and of our program, fetched at boot and re-fetched when a programdata account changes;
- the token and ATA programs;
- Clock and Rent sysvars set from the latest slot.

For each candidate it executes our **exact signed-shape transaction** against cached accounts and returns success or failure, the full-transaction change in payer SOL+WSOL (fees, tip and rent included), CU used and logs.

**What the verifier gives us:**
- **Truth before sending.** It catches DLMM 0x1794 (19 failures), liquidity exhaustion (0x1771), CU exhaustion (5 failures), fee-tier quirks and paused or frozen pools, at zero cost.
- **The only way to quote closed-source prop AMMs** (HumidiFi, Tessera V, SolFi, ZeroFi, GoonFi). Babq and MEViEnsc route through them.
- **CU limit = measured + 10%.** Today we request p50 206k and use 140k.
- **Exact final sizing for persistent gaps:** golden-section search over size, 5-8 SVM runs.

**Latency budget (inference, to be measured in E2):** about 0.3-3 ms per execution.
- Persistent gaps: the SVM is the gate.
- Reactive candidates: native and SVM run in parallel, and we send only if they agree within 1 bp.

**Accuracy monitors:**
- **Live prediction check.** For every successful swap on a Tier-A pool, predict the next state (native and SVM) and compare it with the actual account update. A venue or pool below 99.5% exact over its last 200 swaps is quarantined to shadow.
- **Closer audit.** For every gap someone else closes, compare their realized profit (from transaction meta, on all venues, not just PumpSwap as exec.jsonl was) with our quote at their pre-state.

### 2.4 Decision: the Selector

**Candidate.** A route at the SVM-optimal size ≤ cap, with SVM net ≥ min_profit + margin.

**Expected value.** EV = P̂(land and gap still there) × E[net] − miss cost − λ.
- Bundle miss cost is 0 lamports.
- λ is the shadow price of a Jito send slot. It is 0 while fewer than 4 sends/s are queued, and otherwise equals the lowest queued EV.

**P̂: a Beta-binomial table by route class, not machine learning.** Its cells are:
- Route class: venue tuple × hop count × hub.
- Competition state of the weakest leg:
  - "fast-covered" means a closer with gap-age p50 under 20 ms took 3 or more gaps on this pool in the last 6 h;
  - whether a rung 0-1 bot (Mriya, 9EwQ, 8oSD, 4BQ6) traded this mint in the last hour.
- Gap age at decision: under 20 ms, 20-150 ms, or 150 ms or more.
- Trigger type: none or sweep, user swap, or another bot's arb leftover.
- Leader kind for the target slot: Jito, BAM or other.

**Priors from the evidence:**
- Bundles under 0.05 SOL: 1.44%.
- Pools with 5-20 bots: 0.9%; pools with 150+ bots: 0.4%.
- Persistent, SVM-verified gaps: Beta(2,8), an unknown about 20%.

**Hard gates:**
- Return above 3% of size requires every leg's state updated within 2 slots, plus SVM success.
- No sending into a route already in flight until its bundle resolves or 2 slots pass.
- A route is re-sent only if its state version has changed. This replaces the 400 ms pair lock, which failed to stop duplicates #245 and #246.

**Rate allocation.** Under the 5/s limit, 2 slots/s are reserved for persistent-gap candidates and the rest are filled by EV.

### 2.5 Transaction construction

**Instruction order:**
1. CU limit (SVM CU × 1.1)
2. CU price 0 on bundles
3. SetLoadedAccountsDataSizeLimit
4. Idempotent create of the intermediate ATA, if not already held
5. Route instruction
6. CloseAccount on that ATA, if created in this transaction
7. Top-level tip transfer

**Rent is neutral by construction.**
- Each leg spends exactly what the previous leg delivered, so a freshly created intermediate account ends at 0 and closes in the same transaction.
- If it doesn't end at 0, the close fails, the bundle doesn't land, and nothing is lost.
- The SVM checks the whole-transaction lamport change.
- Hot mints keep a held ATA, capped at 40 accounts (about 0.06 SOL).
- WSOL, USDC and USDT ATAs are permanent.

**ALT index.** Copies already reach 1,209 of 1,232 bytes (median 1,068), mainly because pool accounts are static keys.
- We index every lookup table seen in shreds: address → (ALT, index). This includes Jupiter's and the winners' tables; Mriya's DiPcRv8w is used by 15 signers.
- Per transaction, a greedy set cover picks at most 4 ALTs.
- Our own 1-2 ALTs hold wallet ATAs, our program, tip accounts, programs and sysvars.
- Our own ALTs for uncovered Tier-A pool accounts are created on promotion, never in the hot path (new entries need a slot to become usable). Their rent budget is 0.3 SOL and recoverable.
- Third-party ALT risk: deactivation makes our simulation fail, so the bundle doesn't land, at zero cost.
- If a transaction is still over 1,232 bytes: try another hub pool, then a held ATA, then drop the route.

**Blockhash.** Recent blockhash from our slot and blockhash stream. Single-path bundles need no nonce, which ends nonce starvation and "Blockhash not found" on consumed nonces.

### 2.6 Sending

- **Default:** single-transaction Jito bundles from Frankfurt. A miss is free.
- **Per-leader policy:**
  - Jito leaders: bundle.
  - BAM leaders (38% of slots, where we landed only 3 of 23 wins): bundle, with landing tracked separately (E9).
  - Non-Jito leaders (1.3%): skip.
- **Direct path off by default.** It returned 1 win in 969 attempts against 24.2M of fees. An optional experiment allows zero-priority direct shots (about 5,000 lamports each) only for SVM-verified gaps 3 or more slots old, under a 1M-lamport budget.
- **Tip = clamp(share × (gross − fees), 1,000, cap).**

  | Route class | Starting tip share |
  |---|---|
  | Persistent or uncovered | 0.30 |
  | Contested, gross under 20k lamports | 0.16 |
  | Contested, 20k-100k | 0.47 |
  | Contested, 100k-1M | 0.54 |
  | Contested, 1M-10M | 0.64 |

  The contested shares are the winners' medians. Each share is tuned online with an A/B test (E4).

### 2.7 Accounting and reconciliation

**Ledger keyed by our transaction signature.** Sources:
- Jito bundle status;
- the gRPC transaction stream filtered to our payer, which shows every landed transaction, success or failure, with exact fee, tip and balance changes;
- an hourly wallet snapshot covering native SOL, all token accounts, ALTs and nonce accounts.

**Categories:** trading gross, tips, fees on wins, fees on failures, rent locked and unlocked, inventory P&L (USDC/USDT at the SOL/USDC mid), and stranded tokens (should be 0).

**Reconciliation.** The change in wallet equity must equal the sum of categories within 10k lamports, or an alert fires. The supervisor budgets on mark-to-market equity, not on self-reported counters. Today's `failed_fees_lamports` and `profit_lamports` are wrong in both directions.

### 2.8 Supervisor and safety

**Stops:**
- Hourly equity drawdown of 0.05 SOL, or a daily drawdown of 0.15 SOL.
- Rent locked above 0.4 SOL.
- Any stranded token held more than 60 s, which triggers an automatic unwind through the best route.
- Venue quarantine on accuracy alarms or a programdata change.
- A per-attempt size cap: 0.2 SOL at canary, 1 SOL in Stage 2, 4.2 SOL once Stage 3 gates pass.

**Hygiene:**
- `deny_unknown_fields` on the config.
- Build hash, config hash and dirty-diff hash in meta.
- Shadow → canary → live promotion, each with its own gate.
- The trading key never holds the upgrade authority.

---

## 3. On-chain program: nexus-arb-v3 (an evolution of the deployed 8K8uyQDt)

The current program already does balance-chained 1-8 leg routes into any quote token, opaque CPI legs with amount patching, native legs, NXV2LEG/NXV2OUT logs and the optional payer guard. The 2-leg WSOL limit is in the engine (exec.rs:339), not the program. v3 is a targeted upgrade, not a rewrite.

### 3.1 Instruction data layout (v3)

| Offset | Field | Notes |
|---|---|---|
| 0 | u8 version = 3 | |
| 1 | u8 flags | bit0 PAYER_GUARD, bit1 CPI_TIP, bit2 QUOTE_IS_WSOL (lamports count in net) |
| 2 | u8 n_legs (1..=6) | |
| 3 | u64 amount_in | |
| 11 | u64 min_profit | In quote base units |
| 19 | [u64 max_payer_lamport_drop] | Only if PAYER_GUARD |
| … | [u16 tip_bps, u64 tip_floor, u8 tip_acct_ix] | Only if CPI_TIP |
| per leg, 5 B | u8 n_accounts (full 8 bits), u8 leg_flags (NATIVE_IN, NATIVE_OUT), u8 amount_offset, u8 data_len, u8 reserved | Fixes the latent bug where a leg with 64+ accounts collides with the NATIVE flag bits |
| then | leg data | Venue minimum-out patched to 0/1; the end-of-route guard is the economic protection |

**Accounts:** [0] authority (signer, writable), [1] quote account (writable), then per leg [out_acct, venue_program, leg accounts…]. If CPI_TIP is set, the system program and the tip account follow.

### 3.2 Guard maths

```
Q0 = quote.amount; L0 = authority.lamports            (at ix entry)
… legs (each spends previous leg's delivered delta; delivered==0 → LEG_ERR+i) …
g  = (Q1−Q0) + (QUOTE_IS_WSOL ? (L1−L0) : 0)          // native legs and in-ix lamport moves count
if CPI_TIP: tip = max(tip_floor, g·tip_bps/10⁴); system_transfer(authority→tip_acct, tip); g −= tip
require g ≥ min_profit   (else ERR_PROFIT 0x4E580002, full revert)
if PAYER_GUARD: authority lamport drop ≤ max_drop; per-leg token-account guard; no foreign signer
```

- **Top-level tip (default):** min_profit = tip + base fee + priority (0 on bundles) + margin. The margin starts at max(2,000, 2% of SVM net); A9pQ uses tip + 15k as a reference.
- **CPI tip (optional, after E7):** min_profit = fees + margin. The tip then scales with *realized* profit, so a gap partly closed by a rival still lands with a smaller tip instead of reverting. This suits residual gaps.
- **Rent** is outside the instruction and neutral: create and close happen in the same transaction, and the SVM confirms the whole-transaction change. It is never added to min_profit.
- **min_profit = 0 stays rejected.**
- **USDC-anchored routes (Stage 3)** have min_profit in USDC units, set off-chain at send time as (tip + fee) × SOL/USDC mid × 1.02.

### 3.3 Sizing and miss behaviour

- **No on-chain sizing in Stages 1-3.** Persistent gaps are sized exactly by the SVM against fresh state.
- **Stage 4 (only if E6 passes):** a "self-size" leg mode for 2-leg routes whose venues can be quoted from a few accounts (CPMM family closed form, DAMMv2 single range, DLMM bin walk across the passed arrays). The off-chain amount_in becomes a cap. MEViEnsc's 1.66 MB engine is not copied.
- **On a miss: revert.** A bundle that would revert never lands, so it costs nothing. The direct experiment pays its fee only.
- **No no-ops in bundles.** A no-op still pays an unconditional tip.

### 3.4 Venues and security

**Allowlist.** Keep it compiled in, so new venues need one batched upgrade. Add these after verifying their IDs from chain:
- Manifest MNFSTqtC…
- Phoenix
- DAMMv1
- Tessera V TessVdML…
- ZeroFi ZERor4xh…
- HumidiFi, SolFi, GoonFi (IDs from the DOC1 table)

Each one has to pass E8 first.

**Payer guard trailer** is on for every route. All 12 currently allowlisted venues are upgradeable by PDA authorities, so a malicious upgrade is the threat the guard defends against. It costs 8 bytes.

**Keys and funds:**
- The upgrade authority is cold and separate from the trading wallet.
- The program owns no PDAs and holds no funds.
- The trading wallet signs every swap.

**Tests:**
- Host unit tests for parse, guard and tip arithmetic.
- SVM integration tests per venue using captured mainnet account snapshots.
- Finish the truncated evil-venue test, which currently stops at 1,414 bytes.

---

## 4. Keep and discard

**Keep:**
- Integer venue math: cp.rs, dlmm.rs, dammv2.rs.
- Third-party swap decoders, repurposed for ActivityMap and competition.
- Shred assembler, gRPC feeds, and store.rs (extended with versioning and PendingWrites).
- send/jito.rs, the keystore (wallet.rs), compile_v0 and ALT plumbing (build.rs), pda.rs.
- record.rs, refocused as the census.
- pooldisco, refocused as the Discovery service.
- The on-chain core: chaining, logs, error range, payer guard.

**Discard or replace:**

| Today | Replacement |
|---|---|
| Prediction-based pricing (`preds`), confirm_trigger_ms, skip_failing_signers toggles | Account-state pricing only |
| RPC sim gate and its stale-override branch (exec.rs:646-650) | Local SVM |
| Multi-path direct fan-out, 20-nonce pool, settle_s logic | Bundle status plus wallet tx stream |
| Pair lock | State-versioned in-flight lock |
| Static Mriya-seeded CSVs (844 of 1,014 pools) | Dynamic discovery |
| `profit_lamports`, failed-fee-only budget | Equity ledger |
| 2-leg WSOL restriction at exec.rs:339 | Multi-hop routes |
| Boot-time DLMM bitmap-extension check (pools.rs) | Per-send check |
| Paid sender services | None |

---

## 5. Build plan (engineer-days, one engineer familiar with the code; estimates)

| Stage | Contents | Days | Exit gate |
|---|---|---|---|
| **0. Hygiene** | Bundle-only; direct arm off; pricing on account state only; tx-atomic store; warm-up gate; equity ledger; per-send DLMM extension check | 5-7 | 24 h live with 0 failure fees and the ledger reconciled within 10k lamports |
| **1. Shadow census** | Discovery tiers A/B/C; universe graph and cycle index; CLMM/Whirlpool native math; local SVM verifier; census of gap episodes and closer audit on all venues; gRPC load test | 20-25 | Experiments E1, E2 and E5 decided |
| **2. Live breadth v1** | Multi-hop SOL-anchored routes via USDC/USDT; CLMM family (already allowlisted); ALT index; ATA create/close; Selector v1; tip tiers; canary at 0.2 SOL, then 1 SOL | 15-18 | E3 and E4 pass; net positive over 48 h |
| **3. Program v3 and new venues** | v3 upgrade (allowlist, flags byte, lamport-inclusive guard, optional CPI tip); Manifest/Phoenix books; prop AMMs via the SVM; stale-pool sweeps; hot-token promotion; USDC inventory (about 0.85 SOL equivalent) with revaluation | 22-28 | E7 and E8 pass; E1 projection confirmed live |
| **4. Optional** | On-chain self-size for 2-leg routes; BAM path; cap raised to 4.2+ | 15-20 | E6 and E9 |

---

## 6. Experiments and go/no-go thresholds

| # | When | What | Go | No-go action |
|---|---|---|---|---|
| E1 | End of Stage 1, 48 h shadow | Capturable gross: SVM-verified episodes with net ≥ 50k lamports after a 30% tip at size ≤ 4 SOL, whose lifetime ≥ our detection time + 1 slot + 70 ms, with no rung 0-1 closer. Broken down by route class and tier. | ≥ 0.5 SOL/h capturable gross on the expanded universe | < 0.2 SOL/h: stop expanding breadth and keep the pricing core |
| E2 | Stage 1 | Accuracy per venue: SVM vs next state; native vs SVM; closer-audit agreement (n ≥ 200) | SVM ≥ 99.9% exact; native ≥ 99.5% within 1 bp; closers within 2% | Venue stays shadow |
| E3 | Stage 2 | 100 canary bundles (≤ 0.2 SOL) on SVM-verified gaps 1 slot or older | Land ≥ 25%, realized/expected ≥ 0.8 | < 10%: the persistent segment is not real for us |
| E4 | Stage 2 | Tip share 0.3 vs 0.6 on uncovered routes | Adopt 0.3 if the land-rate drop is < 20% relative | Keep 0.6 |
| E5 | Stage 1 | Size fit of 3-hop routes with the ALT index | ≥ 95% compile within 1,232 bytes | Restrict to 2-hop plus held hub ATAs |
| E6 | Stage 2 | Re-run would-fail candidates through the SVM at smaller sizes | ≥ 30% still positive at a smaller size | Skip Stage 4 sizing |
| E7 | Stage 3 | 5 tiny bundles whose tip is paid by CPI | All land and are auctioned like top-level tips | Keep top-level tips |
| E8 | Stage 3 | Each prop AMM / CLOB: SVM run plus 1 canary CPI from our program | CPI succeeds and matches the SVM | Drop that venue |
| E9 | Stage 2-3 | Bundle land rate on BAM vs Jito leaders (≥ 200 eligible) | BAM ≥ 50% of the Jito rate | Investigate BAM submission |
| E10 | After 500 live attempts | Selector calibration | Predicted vs realized within ±30% per decile | Re-bucket the classes |

---

## 7. Risks and how it fails

1. **The pot is small (main risk).**
   - Evidence: the slow slice is 0.6-1.6 SOL/h; uncontested pools carry little money; small slow wins are 0.094 SOL/h.
   - E1 is built to fail fast, after about 4 weeks and with zero trading loss.
2. **The fast multi-hop bots cover the same routes.** Mriya, 9EwQ, DtvmxrTA and R32xAccF all route multi-hop. The competition map measures this directly, and the Selector stops attempting routes that are fast-covered.
3. **Jackpot dependence.** Segment E is heavy-tailed: one 10 SOL trio-type event can be a whole day's P&L. Report medians alongside means, and do not scale capital on a single event.
4. **A persistent gap may be fake:** a honeypot, frozen mint, transfer hook, paused pool, or stale cache.
   - The SVM on fresh, consistent state catches most of these. It cannot predict a freeze that happens later.
   - The mint junk filter and the stranded-token unwind cover the rest.
5. **SVM fidelity:** feature-gate drift, venue upgrades, clock-dependent fees.
   - Mitigations: watch programdata accounts and auto-quarantine; the E2 live comparison.
   - A prop-AMM upgrade can break quoting at any time.
6. **Infrastructure limits:** Haan gRPC subscription limits and rate limits (297 rate-limits in p12). Tier B/C volume must pass the Stage 1 load test.
7. **Jito limits:** 5 bundles/s and the BAM under-landing. The rate budget handles the first; E9 tests the second.
8. **Losses are bounded.** Every send is a bundle that reverts on a miss. Remaining exposure is rent (capped at 0.4 SOL, recoverable), held USDC (FX, about 0.85 SOL), and SVM-blind state changes between verification and landing, which revert in bundles.

---

## 8. Expected economics per stage

**Assumptions:**
- SOL = 119.7 USD, the value the evidence uses.
- Blended tips 40% of gross.
- Fees on wins about 10k lamports.
- Bundle misses free.
- Fixed costs for infrastructure and feeds are not in the evidence; the operator must net them.

| Stage | Gross capture SOL/h | Tips | Fees | **Net SOL/h** | Capital locked |
|---|---|---|---|---|---|
| 0 | ≈0.0001 | ≈0 | ≈0 | **≈0** (stops about 0.0065 SOL/h of failure bleed; recovers about 0.06 SOL of rent in empty token accounts and nonce accounts) | — |
| 1 | 0 (shadow) | 0 | 0 | **0** | — |
| 2 | 0.05-0.4 (central 0.17) | 0.07 | <0.005 | **0.03-0.25 (central 0.1)** | ALTs ≤ 0.3 SOL; hub ATAs about 0.006 SOL (both recoverable) |
| 3 | 0.1-1.0 (central 0.42) | 0.17 | 0.01 | **0.05-0.6 (central 0.25)** | + about 0.85 SOL of USDC inventory |
| 4 | 0.2-1.4 (central 0.67) | 0.27 | 0.01 | **0.1-0.8 (central 0.4)** | 4.2 SOL cap within the current 4.23 SOL WSOL |

**How the Stage 2 central figure is built:**
- 25% of the within-cap slow slice (about 0.46) = 0.115
- 10% of small Jito wins (about 0.48) = 0.048
- about 3% of venue-gap rung-3 = 0.03

Total about 0.19 gross, so about 0.1-0.12 net.

**Stage 3** adds a 25% capture of whatever capturable gross E1 measures (assumed 0.5-1.5 SOL/h) and the jackpot tail (0.01-0.15 SOL/h on average).

All figures are estimates. The single number that decides the strategy is E1's capturable-gross measurement.

---

Two caveats on the evidence behind §1:

- **My venue-mix check is rough.** I used an approximate claims filter (dropped pump.fun and Jupiter rows, and anything over 2 SOL); the farmnFYo "claims" wins in w5h2-p2 still pass it. Read it only as a range.
- **Wins on unwatched PumpSwap pools are not a big hidden market.** They are dominated by DeFG8i8z, a sprayer that PATTERNS shows netting −6.1 SOL.

Scratch scripts (read-only analyses) are in `/tmp/claude-1000/-home-moiz-arbed-arb-lab/5e4b11f2-122d-406a-b161-b66016d99287/scratchpad/cherry/work/redesign-coverage-breadth/`:
- `venuemix.py`
- `venuemix2.py`
- `unwatched.py`
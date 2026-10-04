# Final redesign recommendation: arb-lab and Nexus

**Date:** 2026-10-04. **Status:** design only; nothing was changed, built or sent. Amounts are in lamports unless marked SOL. USD figures use 119.7 USD per SOL. "(est.)" marks an estimate and "(inf.)" an inference.

## 1. Executive summary

**Recommendation.** Fix the bot first, measure second, and build new capability only where a measured pot clears break-even. Keep the deployed Nexus program (8K8uyQDt) and most of arb-lab.

- **Stage 0** fixes the engine defects that caused our losses. It makes the bot send only Jito bundles, makes it rent-neutral and accounts for it by wallet equity.
- **Stage 1** spends about two weeks on cheap measurements that settle the open questions.
- At that gate the owner chooses between two capability tracks that share one core:
  - **Track A, breadth and persistence.** Price routes other bots miss: USDC/USDT 3-hop routes, the CLMM family, and later order books. Attempt only gaps that last longer than our latency.
  - **Track B, reactive sizing.** Nexus v3 sizes trades on chain over a small basket of pools. It is fed post-trigger state, computed by running the trigger transaction locally.

**What money we target, and what we do not.**

| Segment | Market SOL/h on our ~1,000 pools | Our stance |
|---|---|---|
| Rungs 0-1 (backruns sequenced or bundled with the opener) | ≈11.5. Within our 4.2 SOL cap and without MriyaNN8, ≈1.2 gross (est.) | Out of reach by reacting. Reachable only through order-flow admission (a parallel business track) |
| Rung 3, same-slot reactive | ≈10.6, of which 3.4 has a gap above RTT + 2 ms | Track B, if Stage 1 shows that sizing and state, not speed, are what we lack |
| Slow gaps (route-wide age ≥ ~354 ms) within cap | 0.12-0.46 gross | The core of Track A |
| Unusual routes (USDC triangles, CLMM legs, stale pools) | Unmeasured, heavy-tailed | Track A, only if the census measures it |
| Small uncontested Jito gaps (where all 23 bundle wins came from) | ≈0.48 net to winners; the slow part is 0.094 | Keep, cheaply |

**Why we can win.** When a gap is real and nobody else takes it, our maths is exact:
- 18 of 23 wins matched the prediction to the lamport, and 22 were within 12 lamports.
- On three gaps MriyaNN8 took, its realised take was within 40 lamports of our quote.
- Nexus is not the bottleneck. It costs 11.6-18.5k CU of overhead, and its profit check reverted every losing trade that reached it.

Most of our losses are our own doing, and they can be fixed:
- Two engine bugs explain 10 of the 16 biggest losses. Failed swaps decoded from shreds left phantom predicted prices, and trigger state was read before it had fully updated.
- The direct arm won 1 of 989 attempts and paid 24.4M in failure fees.
- Rent turned the bundle arm's +163,187 into −17,926,693.
- 0 of 1,869 bundles expecting 1M or more landed.

The profitable rung-3 bots (Bgokg3ju +1.71 SOL/h, A9pQ1Qsv +0.82) are one inclusion cycle ahead of us. Their transactions are already on chain 14-15 ms after the opener, while we are still deciding. But the share of our bundles that Jito rejects as would-fail stays at 80-94% at every send delay we measured, from under 5 ms to 100 ms. It is still 86% when no rival took the gap. On current evidence, bad state, bad pricing and fixed sizing hurt us at least as much as speed does. Experiments X2 and X3 separate the two.

**Expected economics (all est.).**

| Stage | Net SOL/h | Range | Notes |
|---|---|---|---|
| Today | Bundle arm +0.00005 excluding rent; direct-arm failure fees −0.0065 | — | Over the 3.66 h window the wallet fell 14.8M, including 19.6M of recoverable rent |
| Stage 0-1 | ≈0 | 0-0.002 | Stops the failure-fee bleed; ≈0.06 SOL of rent can be recovered by an owner action |
| Track A, Stage 2 | ≈0.05 | 0.01-0.15 | The judges' recomputation of the proposal's 0.1 |
| Track A plus new venues | ≈0.1 | 0.03-0.4 | Depends on the census |
| Track B at 4.2 SOL | 0.05-0.3 | Speculative | Competes head-on with Bgokg3ju and A9pQ1Qsv; limited by capital |
| Order flow, if admitted | 0.03-0.1 | Option value | Chance of admission unknown |

How the central figures are built:
- **Track A:** the ≥354 ms slow slice within cap (0.12-0.3 gross) × 25% capture × 0.65 after tips ≈ 0.02-0.05. Add 0.005-0.01 from small gaps and an unknown tail.
- **Track B:** Bgokg3ju's trades of 4.2 SOL or less are worth ≈0.79 SOL/h (46% of 1.71). Capturing 5-25% of that pool gives the range.
- **Order flow:** 10-20% of the ≈1.2 SOL/h pot, minus channel bids of 60-75%.

At 0.1 SOL/h net, the bot earns ≈$290/day before infrastructure costs, which the evidence does not cover. My judgement is a ~40% chance that Stage 1 shows neither track clears break-even. In that case the answer is a lean bundle-only bot or a stop. We would know after about four weeks, with near-zero trading loss.

**What we stop doing now:**
- The direct/TPU arm and paid copies through several sender services.
- Pricing from predictions based on swaps decoded from shreds.
- The override that sends anyway when the simulation is stale (exec.rs:646-650).
- Unthrottled state-trigger bundles expecting 1M or more.
- Leaving new token accounts open.
- Durable nonces on bundles.
- A budget that counts only failed-transaction fees.
- Swapping binaries and configs mid-campaign by SIGINT, with no logged reason.
- The 400 ms pair lock.
- Spending 49% of attempts on the 21 pools with 150 or more bots.

## 2. Proposals, scores and grafts

| Proposal | Economics | Engineering | Latency | Mean | What it delivered |
|---|---|---|---|---|---|
| coverage-breadth | 6 | 6.5 | 6 | **6.2** | The only full design: architecture, program v3, stages, ten experiments |
| hardening-first | 1 | 3 | 1 | 1.7 | arms.py: 0 of 1,869 bundles expecting ≥1M landed; 1,020 attempts lost to the 5/s limit |
| orderflow-priority | 1 | 2 | 1 | 1.3 | rung.py and rung2.py: the rung 0-1 pot is 81% MriyaNN8, and 66% of it comes from trades over 10 SOL |
| reactive-bundler | 1 | 1.5 | 1 | 1.2 | timing.py: would-fail 80-94% at every send delay, and 86% where no rival took the gap |
| clean-slate | 0 | 0.5 | 0 | 0.2 | Nothing |

**Why coverage-breadth won.** It was the only proposal that delivered a design, and the design held up under checking:
- Its code citations are correct:
  - engine.rs:641 `preds`
  - the store.rs:60 exemption that skips the parts-skewed check for PumpSwap
  - grpc.rs:398 `txn_signature`
  - the exec.rs:339 2-leg WSOL route
  - the exec.rs:646-650 stale-simulation branch
- Most of its evidence figures reproduce.
- Its losses are bounded by design: bundle-only sending, rent-neutral transactions and stops based on equity.
- Every stage has a numeric gate.

It lost points for:
- putting its go/no-go census behind a 20-25 day build;
- optimistic capture rates;
- padding the unusual-route segment with evidence that is rung-0 or one-off: 4BQ6's exclusive FLASHX8D order flow, 8oSD's single USDC trio, and DtvmxrTA's trade above our cap;
- underestimating a local SVM in a codebase that has no solana-sdk dependency;
- unstated assumptions about how much load Haan can carry.

**Read the scores with care.** Four proposals were cut off before they wrote a design, so their scores rate what they delivered, not their ideas. The economics judge said hardening-first, delivered as titled, would likely have ranked first. Their scratch analyses turned out to be the most useful evidence for these decisions. The recommendation therefore uses hardening-first's order of work and coverage-breadth's architecture, gated by the other proposals' measurements.

**Grafts, and where each came from.**
1. Stage 0 fixes before any new capability (coverage-breadth §5, which matches hardening-first's intent).
2. A recorder of gRPC account updates and a deterministic replay harness (engineering judge).
3. An offline census that runs in days, before any build, with its go threshold tied to break-even (economics judge).
4. The census counts a gap only if its route-wide age is at least detection + 1 slot + 70 ms ≈ 354 ms (latency judge).
5. The store applies writes per transaction, keyed by the gRPC `txn_signature`. Shreds are only hints, because 5 of 10 feeds are dead (latency judge).
6. Throttle bundles expecting ≥1M (hardening-first, arms.py).
7. No spending on latency until a delay test run after the fixes justifies it (reactive-bundler, timing.py).
8. No on-chain sizing until a replay at smaller sizes (E6) justifies it (docs review, economics judge).
9. Size the order-flow pot at ≈1.2 SOL/h within cap without MriyaNN8, and file the applications now (orderflow-priority).
10. Treat Jito send slots as a priced resource, and re-send persistent gaps when the leader changes (coverage-breadth, latency judge).
11. Per-leader telemetry from Stage 0, not Stage 2 (latency judge).
12. Program v3 as a targeted upgrade, with tips paid from inside the program (CPI tips) only after an acceptance test (all judges). The clean-slate rewrite is rejected because the current program is verified and is not the bottleneck.

## 3. Target architecture

### 3.1 Components and data flow

```
Shreds (dz-leader, dz-retransmit-eu, astralane-deshred) ─► TxDecoder ─► Hints (expected writes, trigger detection)
                                                                     └► ActivityMap (flow, competitors, hot tokens)
Haan gRPC conn 1: Tier-A accounts (explicit list) + tx/meta stream (watched programs, our wallet) ─► TxAtomicStore
Separate gRPC conn/provider 2: owner-filtered discovery streams, snapshots ─► Discovery ─► UniverseGraph ─► CycleIndex
TxAtomicStore + CycleIndex ─► Pricer (native integer maths) ─► Verifier sidecar (local SVM, Stage 1+) ─► Selector
Selector ─► Builder (v0, ALTs, ATA create/close, recent blockhash, CU) ─► Sender (Jito BE Frankfurt, per-leader policy)
Bundle status + wallet tx stream ─► Ledger/Reconciler ─► Supervisor (equity stops, quarantine, kill switch)
All of the above ─► Recorder ─► Replay harness, census, experiments
```

**Kept:**
- the venue maths (cp.rs, dlmm.rs, dammv2.rs);
- the shred assembler and the gRPC feeds;
- store.rs, extended;
- send/jito.rs and the wallet.rs keystore;
- the compile_v0 and lookup-table (ALT) code in build.rs, and pda.rs;
- record.rs, extended;
- pooldisco, reused as Discovery.

**Removed from the path that decides and sends trades:**
- `preds`;
- confirm_trigger_ms;
- the RPC simulation gate and its stale branch;
- the direct fan-out over many send paths;
- the 20-nonce pool;
- accounting by `settle_s`;
- the pair lock;
- `profit_lamports` as P&L.

### 3.2 State consistency model

The goal is to price only states that actually existed on chain, and never half of one.

1. **Committed state is account state only.**
   - Every update carries slot, write_version and txn_signature, which grpc.rs:398 already parses.
   - Failed transactions write nothing, so a failed decoded swap cannot create a gap. 681 of 822 decoded triggers with a priced opportunity of ≥0.1 SOL failed on chain.
   - This rule removes the phantom quotes behind:
     - DreMAMRc>AwmaWjsR (54 of the 96 failures in w5h3-p2);
     - the 4pANrqEv cases;
     - the stacked failed sells (p6#364, p11#132, w5h3-p2#662-#704).
2. **Commit groups.**
   - For each transaction T, the set W(T) of watched writable accounts it touches comes from the gRPC tx stream. That stream is authoritative and includes addresses loaded from lookup tables. Decoding T from shreds only registers W(T) earlier.
   - An update stamped T stays *pending* until every account in W(T) has an update stamped T or a newer write_version, or until 5 ms pass.
   - A route can be priced only when none of its accounts is pending and its parts are at most 1 slot apart.
   - The PumpSwap exemption from the parts-skewed check (store.rs:60) is removed.
   - This blocks the half-updated reads of split-route trades on AgmLJBMD triggers (p2#750, #1238, #1326, p9#12, p10#444, #596). It would also have priced the bolt trade (w5h2-p5#648) on its true state, where it loses 103M.
3. **Timeout fallback.**
   - If W(T) is still unknown at 5 ms (T not yet seen in either stream, or a lookup table not yet resolved), require quiescence: no write to the route's accounts for 3 ms.
   - Failed lookup-table fetches are retried with backoff. Today they are cached as missing for the rest of the run (engine.rs:446/537).
4. **Forks and health.**
   - On a slot rollback, invalidate newer versions and refetch.
   - Warm-up gate: nothing is sent until every Tier-A pool is complete and the store is within 2 slots of the chain tip. This stops the 3.0-3.8 s late sends at segment start.
   - Service target, checked every minute: lag from first shred to committed state p50 ≤ 16 ms and p90 ≤ 30 ms. Today p50 is 14.87 ms.
5. **Speculative state (Track B only).** This is the only approved way to act before Haan's state arrives.
   - Start from committed state. In the local SVM, run in shred order every transaction seen in shreds that writes the route's accounts after their last committed write, including the trigger.
   - A transaction that fails changes nothing.
   - A transaction that succeeds produces a speculative version, tagged with its signature. The committed writes replace it when they arrive.
   - Decoder guesses never become state.
   - It is allowed only if X9 shows SVM p99 ≤ 3 ms, and the replay harness shows speculative and committed states agree on at least 99.5% of triggers.

### 3.3 Pricing and verification

**Native integer maths, used for search and sizing:**
- CPMM family: PumpSwap (with fee tiers and creator fee), Raydium CPMM and AMM v4.
- DLMM: a walk over bins, with the dynamic fee taken from the chain clock.
- DAMMv2: priced on the chain clock. Today it uses local time (inf.).
- New for Track A: one walk over CLMM ticks, shared by Raydium CLMM, Whirlpool, PancakeSwap v3 and Byreal. All four are already allowlisted.
- Input is capped to the liquidity in the bin or tick arrays we hold.

The 19 DLMM 0x1794 failures can be read two ways. The error name says the bitmap extension account was not passed, yet none of the 11 pools involved has one. Together, that points to the swap running past the liquidity we held (inf.). The input cap fixes the problem under either reading. The builder also passes the extension whenever one exists, checked on every send rather than once at boot.

**Verifier sidecar.** A separate process runs a local Solana runtime (LiteSVM or Agave's SVM). arb-lab has no solana-sdk dependency today. Keeping the Agave crates in their own binary keeps the latency-critical binary small.
- It loads the real venue programs and re-fetches them whenever their programdata account changes.
- It runs our exact signed transaction on committed state.
- It returns success or failure, the change in wallet equity over the whole transaction (fees, tip and rent included), the CU used and the logs.

Uses, in rollout order:
1. Replay and census (Stage 1).
2. Live gate for persistent candidates (Track A).
3. CU limit = measured × 1.1. Today we request a median of 206k and use 140k, and 5 failures ran out of CU.
4. Exact sizing of persistent gaps by golden-section search (5-8 runs).

Effort (est.): 8-12 days, more than the proposal assumed.

**Accuracy monitors.**
- For every successful swap on a Tier-A pool, compare our predicted next state with the committed one. Quarantine any venue or pool that is exact on fewer than 99.5% of its last 200 swaps.
- Check closers on all venues: when a rival closes a gap, compare its realised take with our quote at the state just before its trade. Today only PumpSwap could be measured.

### 3.4 Decision: the Selector

- **Candidate:** a route at its verified (or native) optimal size, within the cap, whose net profit clears min_profit plus a margin.
- **Expected value:** EV = P̂(lands and the gap is still there) × E[net] − miss cost − λ.
  - A bundle that misses costs 0 lamports.
  - λ is the shadow price of a Jito send slot. It is 0 while fewer than 4 sends/s are queued. Otherwise it equals the lowest EV in the queue.
  - Today 1,020-1,027 of 7,643 bundle attempts got no verdict because of the 5/s limit. Meanwhile the 1,869 attempts expecting ≥1M landed nothing.
- **P̂ is a Beta-binomial table, not a model.** Its cells are:
  - route class: venue tuple × hops × hub token;
  - competition on the weakest leg: a fast closer (median gap age under 20 ms) took 3 or more gaps on this pool in the last 6 h, or a rung 0-1 bot traded this mint in the last hour;
  - gap age: under 20 ms, 20-150 ms, or 150 ms or more;
  - trigger: none, a user swap, or what is left after a rival's arbitrage;
  - leader kind: Jito or BAM.

  Starting values from the evidence:
  - bundles under 0.05 SOL win 1.44% of the time;
  - pools with 5-20 bots, 0.9%; pools with 150 or more, 0.4%;
  - verified persistent gaps start at Beta(2,8).
- **Band throttle, from Stage 0:** state-trigger bundles expecting ≥1M are capped at 0.5 sends/s and queue behind every candidate under 1M. This holds until X2/X3 or Track B shows they can land.
- **In-flight lock keyed by (route, state version).** Nothing is re-sent into a bundle that has not resolved, for 2 slots. A re-send is allowed when the state version changes, when the leader changes, or at each new slot while the verifier still confirms the gap. Persistent gaps also fail to land for infrastructure reasons: the 130 bundles that Jito first accepted and then marked would-fail never landed, while all 17 bundles that were only accepted did.
- **Rate reservation:** in Track A, 2 of the 5 sends/s are reserved for persistent candidates.

### 3.5 Transaction construction

**Instruction order:**
1. CU limit: verified CU × 1.1. Until the verifier exists, use the p99 of observed CU for the route class + 10%.
2. CU price 0 on bundles.
3. SetLoadedAccountsDataSizeLimit.
4. Create the token account (ATA) for the intermediate mint, idempotently and only if we don't already hold one.
5. The Nexus route.
6. CloseAccount on that ATA, if this transaction created it.
7. A top-level System transfer for the tip.

**Rent-neutral by design.**
- Each leg spends exactly what the previous leg delivered, so the intermediate account ends at exactly zero and closes in the same transaction. If it doesn't, the close fails and the bundle never lands.
- A held set of at most 40 accounts (≈0.06 SOL) covers hot mints. The WSOL, USDC and USDT accounts are permanent.
- Mints with transfer fees or transfer hooks stay filtered out.

**Recent blockhash for bundles,** taken from the gRPC block-meta stream. Bundles sent on a single path need no durable nonce. This removes the 12 "Blockhash not found" verdicts and the nonce shortages, and frees about 10-74 bytes per transaction (est.).

**Size budget.**
- Copies already reach 1,209 of the 1,232-byte limit. The median is 1,068, and p99 for copies that create an ATA is 1,177.
- CloseAccount adds about 7 bytes when its accounts are already in the message (est.), so 2-leg routes fit.
- For 3-hop and basket routes:
  - index every lookup table seen in shreds, as address → (table, position);
  - choose at most 4 tables per transaction with a greedy cover;
  - add our own tables for hot pools, created when a pool is promoted to Tier A and never on the hot path.
- If a transaction is still too large: try another hub pool, then a held ATA, then drop the route.

### 3.6 Send layer: per-leader routing and tip policy

| Leader kind (share of slots) | Policy |
|---|---|
| Jito, not BAM (60.8%) | One-transaction Jito bundle through the Frankfurt block engine |
| BAM (37.6%) | Jito bundle, with landing tracked separately. We landed 3 of 23 wins on BAM, while Bgokg3ju lands 54% of its bundles there. Dropping the durable nonce is one untested explanation |
| Non-Jito (1.3%) | Skip |

- **Direct arm off.** It produced 1 win in 989 attempts for 24.4M of fees, and that win (the bolt trade) cannot be repeated. A later experiment may allow direct sends with zero priority fee (about 5,000 lamports each), only for verified gaps 3 or more slots old, under a 1M-lamport budget.
- **Per-leader telemetry from day one.** For every attempt, record the leader's identity, kind, region and RTT, the sequence of Jito verdicts (accepted, would-fail, none) and whether it landed. This separates lost races from infrastructure drops.
- **Tip = clamp(share × (verified gross − fees), 1,000, cap).**
  - Starting share for persistent or uncovered routes: 0.30.
  - Contested gaps use the winners' median share for their size band: 0.16 under 20k, 0.47 at 20k-100k, 0.54 at 100k-1M, 0.64 at 1M-10M.
  - Today we pay floor(0.7 × (expected − 5,000)), which is 58.8% of the gross on our bundle wins, even though nobody else competed for those wins. X4 tests 0.35.
  - The live cap of 100,000 stays until bundles in a band above it start landing.
  - Fix the config drift: tip_share is 0.5 in deploy/arb.toml and 0.7 live.
- **Jito key.** Confirm whether arbed shares our 5/s key. If it does, give the bot its own key, or ask Jito for a higher limit through its normal process.

### 3.7 Accounting and reconciliation

**A ledger keyed by transaction signature,** built from three sources:
- bundle statuses;
- the gRPC tx stream filtered to our payer, which shows every landed transaction, success or failure, with its exact fee, tip and balance changes;
- an hourly snapshot of native SOL, every token account, the nonce accounts and our lookup tables.

**Categories:**
- trade gross;
- tips;
- fees on wins;
- fees on failures;
- rent locked;
- rent reclaimed;
- inventory revaluation (USDC/USDT at the SOL/USDC mid);
- stranded tokens (target 0).

**Reconciliation.** Every hour, the change in equity must equal the sum of the categories within 10,000 lamports. If it doesn't, live sending pauses. The supervisor budgets on mark-to-market equity, never on the bot's own counters. Today's counters are wrong in both directions:
- `failed_fees_lamports` is a running total. It missed 16 landings in the w5h2/w5h3 window (419,911 lamports) and leaves out rent.
- `profit_lamports` mixes rent into P&L.

### 3.8 Supervisor and safety

**Stops:**
- Equity down 0.05 SOL within an hour: switch to shadow.
- Equity down 0.15 SOL within a day: stop.
- Rent locked above 0.1 SOL: create no new accounts.
- Native SOL below 0.02: unwrap 0.05 WSOL.
- Any stranded token held more than 60 s: sell it through the best verified route, accepting a loss of at most max(2%, 2M lamports). Above that, alert instead.
- A programdata change on any venue: move that venue to shadow.

**Size caps:**
- 0.2 SOL at canary.
- 1 SOL in Stage 2.
- 4.2 SOL once the gates pass.
- Above 4.2 SOL only by owner decision (§6).

**Provenance:**
- Build hash, config hash and a hash of uncommitted changes in meta.json.
- `deny_unknown_fields` on the config.
- One frozen config per campaign.
- A control socket that logs who stopped what, and why. Today every early segment end in w5h was an operator SIGINT with no logged reason, and the binary was swapped three times in 30 minutes.

**Promotion:** shadow, then canary, then live, each with a written gate. The trading key never holds the program's upgrade authority.

### 3.9 On-chain program: Nexus v3 (an upgrade of 8K8uyQDt)

v2 already does the following:
- chains 1-8 legs into any quote token;
- patches the amount for each leg;
- supports native-SOL legs;
- logs NXV2LEG/NXV2OUT;
- rejects min_profit = 0;
- has an optional payer guard.

v3 keeps the v2 parser (version byte 2) unchanged, so rolling back is an engine switch.

**Instruction data (version 3):**

| Offset | Field | Notes |
|---|---|---|
| 0 | u8 version = 3 | v2 still accepted |
| 1 | u8 flags | bit0 PAYER_GUARD, bit1 CPI_TIP, bit2 COUNT_LAMPORTS, bit3 SELF_SIZE, bit4 BASKET, bit5 NOOP_ON_MISS; bits 6-7 must be 0 |
| 2 | u8 n_legs | 1..=8 |
| 3 | u64 amount_in | A cap when SELF_SIZE is set |
| 11 | u64 min_profit | In quote units, > 0 |
| 19 | u64 max_payer_lamport_drop | Only with PAYER_GUARD |
| next | u16 tip_bps, u64 tip_floor, u64 tip_cap, u8 tip_acct_ix | Only with CPI_TIP (19 B) |
| next | Per leg, 5 B: u8 n_accounts (1..=255), u8 leg_flags (NATIVE_IN, NATIVE_OUT), u8 amount_offset, u16 data_len | Fixes the v2 bug where a leg with 64 or more accounts collides with the NATIVE flag bits (N_ACCOUNTS_MASK 0x3F) |
| next | Sizing descriptors | Only with SELF_SIZE or BASKET (Stage 2B) |
| next | Leg data | Each venue's minimum-out is set to 0 or 1; the guard is the protection |

**Accounts:**
- [0] authority (signer, writable);
- [1] quote token account (writable);
- then, per leg, [output account, venue program, leg accounts…];
- with CPI_TIP, the System program and the tip account last.

**Guard maths:**
```
Q0 = quote.amount; L0 = authority.lamports                      // at instruction entry
x  = SELF_SIZE ? clamp(optimal_input(pools), MIN_SIZE, amount_in) : amount_in
legs: leg i spends what leg i-1 delivered; delivered == 0 → LEG_ERR + i
g  = (Q1 − Q0) + (COUNT_LAMPORTS ? (L1 − L0) : 0)                   // i128; native legs count
if CPI_TIP: tip = min(tip_cap, max(tip_floor, g × tip_bps / 10_000))
            require g − tip ≥ min_profit; System transfer authority → tip account
else:       require g ≥ min_profit                                  // else ERR_PROFIT 0x4E580002, full revert
if PAYER_GUARD: L0 − L_end ≤ max_drop + tip; per-leg token-account guard; no foreign signer
```

How the engine sets min_profit:
- **With a top-level tip:** tip + base fee + priority fee (0 on bundles) + margin, where margin = max(2,000, 2% of verified net). For reference, A9pQ1Qsv uses tip + 15k.
- **With a CPI tip:** base fee + margin.
- **Rent is never part of min_profit.** The ATA create before the route instruction and the close after it cancel out within the transaction, and the verifier checks the whole-transaction change.
- **Routes that start and end in USDC:** min_profit in USDC units = (tip + fee + margin) × SOL/USDC mid × 1.02.

**Sizing and basket (Track B only).**
- SELF_SIZE applies to 2-leg A→X→A routes where each leg is one of:
  - CPMM family: closed form;
  - DAMMv2 within one price range: closed form for that range;
  - DLMM: a walk over the passed bin arrays, with a bounded number of iterations.
- The sizing descriptors give, for each leg, the pool kind and the positions of its reserve, vault or bin accounts, which are already in that leg's account list.
- BASKET carries up to 3 candidate (buy pool, sell pool) pairs for one mint. The program quotes each pair at its optimal size and executes the best. If none clears min_profit, it reverts.
- CU budget: v2 overhead is 11.6-18.5k CU per 2-leg route. The target is at most 60k extra for a 3-pair DLMM basket (est., to be verified in tests).
- We do not copy MEViEnsc's 1.66 MB on-chain engine.

**What happens on a miss.**
- Revert by default. A bundle that would revert never lands, so a miss costs nothing.
- NOOP_ON_MISS is allowed only inside someone else's backrun bundle (the order-flow track). There a revert would drop the user's transaction too. Any payment made regardless of outcome is priced as the cost of a miss.
- No plain no-ops in our own bundles, because they still pay the tip.

**Security and upgrade hygiene.**
- The allowlist stays compiled in. All 12 venues on it today can be upgraded by their own PDA authorities.
- Manifest, Phoenix and others are added only after their program IDs are verified on chain and they pass E8. Proprietary AMMs come last, and only with PAYER_GUARD.
- The builder adds the payer-guard trailer to every route. It costs 8 bytes; today it was used in 0 of 1,000 transactions.
- The program owns no PDAs and holds no funds. The trading wallet signs every swap.
- The upgrade authority (GNv76A95) stays cold and off Cherry.
- Upgrades go through a buffer account. Before it is set, its hash is checked against a reproducible build.
- The engine leaves v3 features switched off until the tests pass.
- The buffer needs about 0.3-0.45 SOL of temporary rent, paid from the cold wallet (est.).

**Tests:**
- Host tests for parsing (fuzzed), and for guard and tip arithmetic, including i128 edge cases.
- SVM integration tests for each venue, on captured mainnet account snapshots.
- Finish the truncated test against a malicious venue.
- Regression tests for CU and transaction size.

## 4. Staged roadmap

Effort is in engineer-days for one engineer who knows the code (est.).

### Stage 0: immediate fixes and safety, no program change (9-13 days)

**Day 0, config only:**
- Turn the direct arm off.
- Turn off sends on decoded triggers (a one-line gate if no config option exists).
- Throttle bundles expecting ≥1M.
- Set `skip_failing_signers=true` as a stopgap.

**Engine (3-4 days):**
- Take `preds` out of the path that decides trades.
- Commit groups keyed on `txn_signature`.
- Remove the PumpSwap exemption from the parts-skewed check.
- Retry failed lookup-table fetches.
- Warm-up gate.
- Fail closed on any RPC call in the send path, with no 3 s Shyft backoff.

**Builder (2 days):**
- Recent blockhash on bundles.
- ATA create plus close in the same transaction.
- A table of CU limits per route class.
- DLMM input cap, and the extension check on every send.
- SetLoadedAccountsDataSizeLimit.

**Ledger and supervisor (2-3 days):** as described in §3.7 and §3.8.

**Recorder and replay (2-3 days):**
- Record gRPC account updates (slot, write_version, txn_sig, data), the tx stream, our decisions and per-leader telemetry.
- Write scenario tests that reproduce the catalogued kinds of loss: half-updated reads of split-route trades, stacked failed sells, and leftovers from failed rival arbitrage. They are needed because the catalogued cases happened before account updates were recorded.

| | Stage 0 |
|---|---|
| **Entry** | The owner approves the risk limits (§6) |
| **Exit** | 24 h live, bundle-only, with 0 fees from failed landings; hourly reconciliation within 10k lamports; 0 sends priced on predictions; rent locked not growing beyond the held cap; scenario tests pass; telemetry populated |
| **Metrics** | Would-fail rate by profit band and by send delay; accepted→landed by leader kind; wins/h; net/h |
| **Kill / rollback** | A reconciliation miss, or equity falling more than 0.05 SOL/h: switch to shadow |

### Stage 1: measure before building (8-12 days, about two weeks of calendar time)

Run:
- the offline census (X1);
- the verifier sidecar, offline;
- the delay test (X2);
- the replay at smaller sizes (X3);
- the tip A/B (X4);
- BAM telemetry (X5);
- the size fit (X6);
- the Haan isolation test (X8);
- the verifier latency test (X9).

The bot keeps running bundle-only, as in Stage 0, throughout.

- **Exit:** a decision memo giving each experiment's go or no-go. The owner then chooses Track A, Track B, both, a lean bot, or a stop.
- **Kill:** if X1's capturable gross is under 0.2 SOL/h and both X2 and X3 fail, stop work on new capability.

### Stage 2A: breadth and persistence (15-25 days)

- Discovery tiers, on a separate gRPC connection or provider:
  - Tier A: up to 1,500 pools with full state.
  - Tier B: up to 10,000 pool accounts, used as a prefilter.
  - Tier C: cached, and re-priced whenever another pool of the same token moves.
- Hot-token ranking.
- A flow-anchored breadth rule: add unusual counter-legs only for tokens with heavy trading flow. Pools with 1-5 bots carried only 0.04 SOL all night.
- Multi-hop routes through USDC/USDT, in the engine only (no program change).
- CLMM family maths.
- The lookup-table index.
- Selector v1.
- The verifier as the live gate.

| | Stage 2A |
|---|---|
| **Entry** | X1 says go |
| **Exit** | Canary: 100 bundles of at most 0.2 SOL, on verified gaps at least 1 slot old, land ≥ 25% of the time with realised/expected ≥ 0.8; trading net is positive over 48 h |
| **Kill** | A land rate under 10%, or a negative net over 48 h |

### Stage 2B: reactive sizing (20-30 days)

Program v3 with SELF_SIZE and BASKET, speculative state from running the trigger locally, and bundles carrying two routes.

| | Stage 2B |
|---|---|
| **Entry** | X2 shows the would-fail rate falls as delay falls, or X3 finds ≥ 30% of would-fails still profitable at a smaller size; X9 also passes |
| **Exit** | At least 50 sized bundles landed, realised/expected ≥ 0.8, and a would-fail rate on the targeted class at least 15 points below a fixed-size control over ≥ 1,000 attempts |
| **Kill** | No improvement after 1,000 attempts |

### Stage 3: venues, tips, capital (15-25 days)

- Add venues to the v3 allowlist, each after it passes E8.
- Order-book maths (Manifest, Phoenix).
- Regular sweeps of stale pools.
- CPI tips, after E7.
- A USDC inventory (about 0.85 SOL equivalent), revalued hourly.
- A cap above 4.2 SOL only on owner decision and with evidence that sizing works.

**Exit:** the census projection is confirmed live within ±30% over 7 days.

### Business track (in parallel, owner time)

Apply to Helius's backrun rebates and Astralane's backrun program through their normal channels. Engineering starts only after admission, once the terms are known.

## 5. Experiments to run first

| ID | When and cost | Measurement | Go | No-go |
|---|---|---|---|---|
| X1 Offline census | Stage 1; read-only; 5-7 days | Take the Stage-0 recordings plus a chain sweep of rivals' successful arbitrage on our hot tokens. Record gross, size, route class, route-wide gap age (time since the last write to any account in the route), the winner's rung and the leader kind. A gap counts as capturable if size ≤ 4.2 SOL, age ≥ 354 ms, the winner is not a rung 0-1 bot, and we can support the venue | Capturable gross ≥ max(0.5 SOL/h, B/0.15), where B is break-even SOL/h (§6) | Under 0.2 SOL/h: no Track A |
| X2 Delay test | Stage 1; live bundles; free | Add a random delay of 0, 5, 10 or 20 ms to each state-trigger bundle. Measure would-fail, accepted and landed by delay and band, with ≥ 400 attempts per arm (about 1 h at ~2,090 bundle attempts/h) | Would-fail falls by ≥ 5 points for each 10 ms of delay removed (one-sided p < 0.05) | No latency spending: no new feeds, no speculative state |
| X3 Replay at smaller sizes (E6) | Stage 1; offline | Re-price each would-fail on the recorded post-trigger state at s/2, s/4, s/8 and the optimum | ≥ 30% are profitable at a smaller size, and their summed net is ≥ 0.05 SOL/h at ≤ 4.2 SOL | No on-chain sizing |
| X4 Tip share | From Stage 1; live | 0.7 vs 0.35 on the band under 100k, assigned at random; net per attempt and land rate | Land rate drops less than 20% relative: adopt 0.35 | Keep 0.7 |
| X5 BAM landing | From Stage 0; telemetry | Accepted→landed by leader kind, over ≥ 200 eligible attempts, before and after the nonce is dropped | BAM lands at ≥ 50% of the Jito rate | Investigate how BAM receives our bundles before Track B |
| X6 Size fit | Stage 0; offline | Recompile past attempts with the Stage-0 instruction set | ≥ 99% within 1,232 bytes | Use held ATAs for the affected mints |
| X7 CPI tip (E7) | Stage 2B or 3; 5 tiny bundles | Acceptance and landing on Jito and BAM leaders | All land, and the tip is counted in the auction | Keep top-level tips |
| X8 Haan isolation | Stage 1 | Tier-A lag from first shred to committed state, with discovery off vs on (on a separate connection) | p50 rises ≤ 1 ms, p90 rises ≤ 5 ms, no 429s on the Tier-A connection | A second provider for discovery, or no Tier B/C |
| X9 Verifier latency | Stage 1 | p50 and p99 per 2-leg and 3-leg route | p99 ≤ 3 ms: reactive use allowed | Persistent gaps only |
| E8 Venue canary | Stage 3 | An SVM run plus one canary CPI for each new venue | The CPI result matches the SVM | Drop the venue |

The cheapest decisive pair is X2 and X3. Both run on Stage-0 traffic at no trading cost. Together they decide whether Track B, which goes after the largest reachable money, is worth building.

## 6. Decisions the owner must make

| Decision | Options | Trade-off |
|---|---|---|
| Capital | (a) Stay at 4.23 SOL WSOL. (b) Add 10-20 SOL after the Stage 2B gates | 54% of Bgokg3ju's gains and 75% of MriyaNN8's come from trades above 4.2 SOL. More capital helps only once sizing works; today we have 0 wins among attempts expecting ≥ 1M |
| Order flow | (a) Apply now. (b) Defer | Applying costs little. The pot is ≈1.2 SOL/h market gross within cap, excluding MriyaNN8 (est.). Wins tipped through Astralane totalled 0.66 SOL across all searchers. Terms and admission are unknown. Needs NOOP_ON_MISS, with fixed payments priced as the cost of a miss |
| Infrastructure | Fix or drop the 5 dead feeds; add a second gRPC connection or provider for discovery; get our own Jito key or a higher limit | Haan carries everything today, with 297 rate limits in p12. Discovery traffic must not slow Tier A |
| Break-even B | The owner supplies the monthly fixed cost C; B = C / (730 × 119.7) SOL/h | $1,500/month gives 0.017 SOL/h; $5,000/month gives 0.057. Add engineering cost spread over time |
| Risk limits | Equity drawdown limits of 0.05 SOL per hour and 0.15 SOL per day; rent ≤ 0.1 SOL; canary size 0.2 SOL | Tighter limits slow learning, but every bundle that misses is free |
| Engineering budget | Fund Stage 0-1 only (about 17-25 days), then decide; or commit to Track A or B up front | Committing early risks building for a pot that X1-X3 may show is too small |
| Operations | One frozen config per campaign, with changes only between campaigns | Swaps mid-run produced short, confounded samples (p8 112 s, p11 68 s, p13 83 s) |
| Rent sweep | Close the empty token and nonce accounts (≈0.06 SOL) between campaigns | This writes to the live wallet; harvest Token-2022 withheld fees first |

## 7. Risks, mitigations, and what we will not build

| Risk | Mitigation |
|---|---|
| The reachable pot is small (the main risk) | X1-X3 decide at about four weeks with near-zero trading loss. Report medians beside means. Do not scale on a single jackpot: 8oSD's trio was 10 SOL in one slot |
| The fixes don't lower the would-fail rate, because the cause is lag inside Jito or faster rivals | X2 and X3 separate the causes. If so, stop at a lean bot |
| Fast multi-hop bots (MriyaNN8, 9EwQoN74, DtvmxrTA, R32xAccF) cover the same routes | The competition cells in P̂ push routes that fast bots already cover down the queue automatically |
| One data provider (Haan), rate limits, dead feeds | A separate connection for discovery; a send path that fails closed; alarms on the lag target |
| The local SVM differs from the chain: feature gates, venue upgrades, fees that depend on the clock | Watch programdata accounts and quarantine on change; compare predicted and committed next states live |
| A program upgrade breaks trading | Keep the v2 path; check the buffer hash; leave features off until tests pass; keep the authority cold |
| A venue ships a malicious upgrade | Payer guard always on; allowlist; no PDAs and no funds in the program |
| Others copy our trades (BGghhU9j matched one of our sizes within 25,032 lamports, inf.) | Bundle-only sending reveals nothing until the trade lands |
| Jito's 5/s limit, and bundles under-landing on BAM | Priced send slots; our own key; X5 |

**What we will not build:**
- **A clean-slate rewrite.** The deployed program is byte-identical to its source and has been verified, and its maths matched closers to the lamport.
- **Volume spraying, or a standing queue of no-op transactions.** These lose money: CzYQ2kFn −1.20 SOL/h, HiP about −0.25, 4Qv3 −0.18.
- **Paid copies through several sender services, or direct copies with priority fees.**
- **Flash loans.** Only 2 of 1,189 Kamino flash-loan transactions succeeded.
- **Racing rungs 0-1 from shreds.**
- **A MEViEnsc-style 1.66 MB on-chain engine, or anti-clone hashing.**
- **Funds or PDAs held by the program.**
- **One tip share for every trade.**
- **Moving the server or adding senders** before sequencing or admission is solved.
- **Anything that trades ahead of user orders.** We take only atomic, self-funded arbitrage and backruns.

**Evidence:** wallet-synthesis.md, rival-synthesis.md, docs-review-synthesis.md, the verify-all-doc1/2/3 reports, res-*.md and PATTERNS.md. The analyses I re-ran are under /tmp/claude-1000/-home-moiz-arbed-arb-lab/5e4b11f2-122d-406a-b161-b66016d99287/scratchpad/cherry/work/:
- redesign-hardening-first/arms.py
- redesign-reactive-bundler/timing.py
- redesign-judge-latency/acc_land.py
- redesign-orderflow-priority/rung2.py, run from x-latency/

The working copy used for the word count is /tmp/claude-1000/-home-moiz-arbed-arb-lab/5e4b11f2-122d-406a-b161-b66016d99287/scratchpad/cherry/work/redesign-final/draft.txt.
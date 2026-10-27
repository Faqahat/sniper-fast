# haqq (haqqiUUX…) — how it gets buys and sells landed

10-25 PKT. Read-only study. The data is the collector recording (all four runs, 10-22 03:08 → 10-25 06:15 PKT) plus 540 read-only `getTransaction` calls and 1 `getLeaderSchedule` call.

Labels: MEASURED = counted from the data. INFERRED = my reading, not proven.

## 1. Verdict

- **Cheap and wide.** MEASURED: one small Helius tip (0.0002 SOL), a fixed priority fee of 0.00012 SOL, and a tight CU limit. Almost every small buy and every sell goes out this way.
- **Who lands it.**
  - Buys under 0.5 SOL: Helius 66%, the copy with no tip 28%, 0slot 5%.
  - Sells: Helius 72%, no tip 21%, 0slot 6%.
  - Buys of 0.5 SOL or more use a different recipe: nozomi or Astralane with a 0.001–0.002 tip and a priority fee 10× lower. Those fail half the time.
- **Helius mode is SWQoS-only.** MEASURED: the Helius tip is exactly 0.0002 SOL on 12,472 of 12,500 Helius buys and on all 16,642 Helius sells. INFERRED: that is below the 0.001 Sender Max minimum, so it uses the `swqos_only` tier.
- **The leader's client decides the winner.** MEASURED: Harmonic → Helius wins 87%. Firedancer → the no-tip copy wins 63% and lands in the dump's slot 85% of the time. Jito → Helius 55%, no tip 28%, 0slot 13%. BAM → Helius 61%, no tip 28%.
- **Tips do not move with competition.** MEASURED: the tip is fixed by size class (0.0002 small, 0.001–0.002 big). There is no per-moment bidding.
- **Sells almost never fail.** MEASURED: 15 failed sells against 23,273 landed (0.1%). Buys fail with pump 6042 (slippage) 11–15% of the time on every client (3% for buys under 0.5 SOL, 48% for bigger ones).
- **Speed.** MEASURED (block-position proxy): its dip buys land a median 52 ms after the dump, 64% in the dump's own slot. Leaders under 20 ms from Frankfurt: 45–48 ms. Leaders 120 ms or more away: 168 ms. INFERRED: it sends from Europe.

## 2. Evidence

### Landed path per tx (tip account of the landed copy; MEASURED, 45,043 landed txs)

| path | buys | sells | tip it pays |
|---|---|---|---|
| Helius | 12,500 (57%) | 16,642 (72%) | 0.0002 (a few 0.015–0.0175) |
| no tip (staked / direct) | 5,760 (26%) | 4,960 (21%) | – |
| Astralane | 1,227 (6%) | 99 | 0.002 or 0.001 |
| nozomi | 1,128 (5%) | 51 | 0.002 or 0.001 |
| 0slot | 1,020 (5%) | 1,432 (6%) | 0.0001 |
| Jito | 135 (1%) | 89 | 0.000001 (1,000 lamports) |

The mix is stable across the four runs (Helius 56–58% of buys in every run).

### Buy size picks the recipe (MEASURED)

| buy size | landed buys | top paths | priority fee | 6042 fail rate |
|---|---|---|---|---|
| < 0.5 SOL | 18,830 | Helius 66%, no tip 28%, 0slot 5% | 120,000 lamports | 3% |
| ≥ 0.5 SOL | 2,940 | Astralane 42%, nozomi 38%, no tip 15% | 12,000 lamports | 48% |

- The 6042 rate is failed ÷ (failed + landed) for txs that landed on chain.
- INFERRED: the big buys are its slow "snipe a dead curve" profile (see SELL_SIGNALS.md). Cheap priority there costs it half its attempts.

### Fees (MEASURED)

| | buys < 0.5 | buys ≥ 0.5 | sells |
|---|---|---|---|
| priority fee | 0.00012 SOL | 0.000012 SOL | 0.00012 SOL |
| CU limit (median) | 65,689 | similar | 57,001 |
| CU used (median) | 57,374 | similar | 49,592 |
| CU price | ~1.8–2.1M µL/CU | ~180k µL/CU | ~2.1M µL/CU |

- It fixes the fee in lamports and sets the CU limit about 15% above use. The CU price looks high only because the limit is tight.
- Sells pay the same as small buys.

### Path by leader client (buys + sells; MEASURED)

| client | landed | Helius | no tip | 0slot | Astralane | nozomi |
|---|---|---|---|---|---|---|
| BAM | 16,767 | 61% | 28% | 4% | 5% | 1% |
| Jito | 10,314 | 55% | 28% | 13% | 2% | 2% |
| Harmonic | 13,686 | 87% | 5% | 1% | 1% | 6% |
| Firedancer | 3,227 | 28% | 63% | 6% | 3% | 1% |
| Agave | 426 | 16% | 55% | 25% | 2% | 1% |

- By distance (RTT from Frankfurt): the no-tip share rises from 19% (< 5 ms) to 36% (≥ 120 ms), and 0slot from 3% to 12%.

### Speed of its dip buys (block-position ms after the ≥ 1 SOL dump; MEASURED, 13,564 buys)

| client × path | buys | median ms | in dump's slot |
|---|---|---|---|
| Harmonic × no tip | 363 | 41 | 87% |
| Harmonic × nozomi | 390 | 43 | 70% |
| Harmonic × Helius | 3,222 | 51 | 64% |
| BAM × Astralane | 429 | 52 | 70% |
| BAM × Helius | 2,864 | 53 | 64% |
| BAM × no tip | 1,375 | 88 | 45% |
| Jito × Helius | 1,546 | 53 | 66% |
| Jito × no tip | 1,012 | 54 | 61% |
| Jito × 0slot | 332 | 88 | 60% |
| Firedancer × no tip | 803 | 55 | 85% |
| Firedancer × Helius | 171 | 62 | 30% |

- By path, all clients: Helius 52 ms, Astralane 49, nozomi 50, no tip 65, 0slot 76.
- Block position (index ÷ block size), median: Helius 0.38, no tip 0.39, 0slot 0.42, nozomi 0.47, Astralane 0.52.

### Transaction shape (RPC sample of 540 txs from R3/R4; MEASURED)

- Every tx: AdvanceNonce first, one signer, address lookup tables, three compute-budget instructions, and one call to its router `haqqqMGN…`. pump runs through CPI.
- At most ONE tip transfer per tx. 70% of landed buys carry one, and 30% carry none.
- Nonce accounts seen: 93 distinct in 300 failed buys, 67 in 120 landed buys, and 20 in 120 sells. INFERRED: there may be a smaller pool for sells.
- Failed buys (300 sampled): 69% are the no-tip copy, 13% nozomi, 6% 0slot, 6% Jito. Their fee is mostly the cheap tier.

### Copies per trade: what can and can't be measured

- MEASURED: a landed tx carries 0 or 1 tip and never two. Across trades the winners are Helius, no tip, 0slot and Jito for small buys and sells, plus Astralane and nozomi for big buys.
- INFERRED: each small buy or sell goes out as at least 4 copies on one nonce (Helius 0.0002, no tip, 0slot 0.0001, Jito 1,000 lamports). Big buys go out as about 6 copies.
- NOT measurable: copies that lost the race. The nonce kills them, so they never reach the chain. A path's win share mixes its speed with how often haqq sends on it.

## 3. Versus us (FRA 2g7rYv7y… / AMS EgxfYgEb…)

| | haqq | us (runs 9–15) |
|---|---|---|
| buy priority fee | 0.00012 SOL (CU limit ~66k, used 57k) | 0.0005 SOL (5M µL × 100k; used ~75k) |
| sell priority fee | 0.00012 SOL | 0.0006 SOL (5M µL × 120k; used ~48k) |
| main buy paths | Helius-swqos 0.0002, no tip, 0slot | nozomi (FRA 24 of 42, AMS 14 of 20), Helius, staked |
| sell paths | Helius-swqos + no tip + 0slot (fan-out) | staked-rpc, nozomi retry |
| landing after the dump (proxy) | 52 ms median, 64% same slot (all landed buys) | 40 ms median, 82% same slot (fills only) |
| failed buys | 3% (small buys) | 58% of fires miss (the +5% guard) |

- Our 40 ms counts only the fills. The 58% of fires that missed were mostly late, so the two delay numbers are not like for like.
- Like for like (H2H.md, all 278 attempts in runs 9–14, same clock): our median is 52 ms, the same as haqq's. On dumps we both went for: us 57 ms, haqq 56 ms, haqq first 47% of the time.
- haqq accepts prices up to about +17% (95th percentile), so it rarely fails. We cap at +5%.

## 4. What we could copy (recommendations only; any send-path change needs the owner's OK)

1. **Sells: fan out like it does.** Send a Helius-swqos copy (0.0002) and a no-tip copy on one nonce, with about 0.00012 SOL priority and a tight CU limit. That combination lands 93% of its sells, and 0.1% fail. Ours go through staked-rpc only.
2. **Fees: fix the priority fee in lamports and size the CU limit from simulation (+15%).**
   - Its 0.00012 SOL fee still gives a high CU price, because the limit is tight.
   - Saving: about 0.0004 SOL on each of our buys and sells. That is small money.
   - INFERRED: a tight limit may also help the leader schedule us. Test it before claiming it.
3. **Firedancer and Agave leaders: rely on the no-tip staked copy.** Its no-tip copy wins 63% (Firedancer) and 55% (Agave), and lands in the dump's slot 85% of the time on Firedancer. Its Helius copy on Firedancer is in-slot only 30% of the time.
4. **Harmonic: keep Helius-swqos in the set.** It wins 87% there for haqq.
5. **Do not copy:**
   - the big-buy recipe: cheap priority with nozomi/Astralane at 0.002 fails 48%;
   - Jito at 1,000 lamports: it lands 1%;
   - 0slot: slow, 76–88 ms medians.

## 5. Method and caveats

- Paths come from the recording's `tips` field (tip-account map `sniper-data/work/tipmap.json`). Leaders come from:
  - epoch schedules 1064 (`landing/work/rpc/leaders.json`), 1065 (fetched with 1 read-only call), 1066 and 1067;
  - the client per validator from a cluster-nodes snapshot (10-23 05:43 PKT) and `leader_rtt_new.json`.
- Times are a block-position proxy (slot × 212 ms + index ÷ block size × 212 ms), not a wall clock. Distance is RTT from our Frankfurt server.
- Failed-copy paths come from 300 sampled `getTransaction` calls; a failed tx's tip transfer reverts, but the instruction stays.
- Scripts: `ops/haqq/p0_sched.py`, `p1_paths.py`, `p2_paths.py`, `p3_rpc_sample.py`, `p4_fees.py`, `p5_ours.py`. Outputs: `sniper-data/haqq/p*_*.txt`, `paths1.json`, `rpc_sample.jsonl`.
